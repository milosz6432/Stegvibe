"""Hash-chained, append-only audit log.

Each entry's hash covers the previous entry's hash, so editing, deleting or re-ordering rows in the
middle of the log is detectable. This is *tamper-evident*, not tamper-proof: anyone who can rewrite the
database file can recompute the whole chain, and truncating the tail is invisible without an external
anchor (reports print the head hash for that purpose).

Rules for callers:
* Record an audit entry only AFTER committing the business transaction. ``record()`` opens its own short
  transaction; calling it while another write transaction is open on the same database would deadlock.
* Worker subprocesses never write audit entries; the API process does it on their behalf.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from spectra.db.models import AuditEntry

GENESIS_HASH = "0" * 64
_SEP = "\x1f"


def canonical_json(details: dict[str, Any] | None) -> str:
    return json.dumps(details or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def compute_entry_hash(
    prev_hash: str,
    seq: int,
    ts: str,
    actor: str,
    action: str,
    case_id: str | None,
    evidence_id: str | None,
    job_id: str | None,
    details_json: str,
) -> str:
    payload = _SEP.join(
        [prev_hash, str(seq), ts, actor, action, case_id or "", evidence_id or "", job_id or "", details_json]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class AuditVerification:
    valid: bool
    entries_checked: int
    head_hash: str
    first_invalid_seq: int | None = None
    reason: str | None = None


class AuditService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory
        self._lock = threading.Lock()

    def record(
        self,
        action: str,
        *,
        actor: str = "user",
        case_id: str | None = None,
        evidence_id: str | None = None,
        job_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        details_json = canonical_json(details)
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with self._lock:
            for attempt in range(8):  # retries only matter if another process shares the database
                with self._sf() as s:
                    last = s.execute(
                        select(AuditEntry.seq, AuditEntry.entry_hash).order_by(AuditEntry.seq.desc()).limit(1)
                    ).first()
                    seq = (last.seq + 1) if last else 1
                    prev = last.entry_hash if last else GENESIS_HASH
                    entry = AuditEntry(
                        seq=seq,
                        ts=ts,
                        actor=actor,
                        action=action,
                        case_id=case_id,
                        evidence_id=evidence_id,
                        job_id=job_id,
                        details_json=details_json,
                        prev_hash=prev,
                        entry_hash=compute_entry_hash(
                            prev, seq, ts, actor, action, case_id, evidence_id, job_id, details_json
                        ),
                    )
                    s.add(entry)
                    try:
                        s.commit()
                        return entry
                    except IntegrityError:
                        s.rollback()
                        if attempt == 7:
                            raise
        raise RuntimeError("unreachable")  # pragma: no cover

    def verify(self) -> AuditVerification:
        prev_hash = GENESIS_HASH
        expected_seq = 1
        checked = 0
        with self._sf() as s:
            for row in s.execute(select(AuditEntry).order_by(AuditEntry.seq)).scalars().yield_per(500):
                if row.seq != expected_seq:
                    return AuditVerification(
                        False,
                        checked,
                        prev_hash,
                        row.seq,
                        f"sequence gap: expected {expected_seq}, found {row.seq} (entry removed or inserted)",
                    )
                if row.prev_hash != prev_hash:
                    return AuditVerification(False, checked, prev_hash, row.seq, "previous-hash link broken")
                recomputed = compute_entry_hash(
                    row.prev_hash,
                    row.seq,
                    row.ts,
                    row.actor,
                    row.action,
                    row.case_id,
                    row.evidence_id,
                    row.job_id,
                    row.details_json,
                )
                if recomputed != row.entry_hash:
                    return AuditVerification(
                        False, checked, prev_hash, row.seq, "entry content does not match its hash"
                    )
                prev_hash = row.entry_hash
                expected_seq += 1
                checked += 1
        return AuditVerification(True, checked, prev_hash)

    def list(
        self,
        *,
        case_id: str | None = None,
        evidence_id: str | None = None,
        job_id: str | None = None,
        action_prefix: str | None = None,
        limit: int = 100,
        before_seq: int | None = None,
    ) -> list[AuditEntry]:
        stmt = select(AuditEntry).order_by(AuditEntry.seq.desc()).limit(limit)
        if case_id:
            stmt = stmt.where(AuditEntry.case_id == case_id)
        if evidence_id:
            stmt = stmt.where(AuditEntry.evidence_id == evidence_id)
        if job_id:
            stmt = stmt.where(AuditEntry.job_id == job_id)
        if action_prefix:
            stmt = stmt.where(AuditEntry.action.startswith(action_prefix, autoescape=True))
        if before_seq:
            stmt = stmt.where(AuditEntry.seq < before_seq)
        with self._sf() as s:
            return list(s.execute(stmt).scalars())
