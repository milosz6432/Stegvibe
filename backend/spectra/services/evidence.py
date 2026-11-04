"""Evidence import and read access."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from spectra.container import Container
from spectra.core.errors import InvalidRequestError, NotFoundError
from spectra.core.security import declared_extension, sanitize_filename
from spectra.db.base import new_id
from spectra.db.models import Evidence
from spectra.schemas.evidence import EvidenceOut, HexRow, HexView
from spectra.services.cases import require_writable_case


def require_evidence(s: Session, evidence_id: str) -> Evidence:
    ev = s.get(Evidence, evidence_id)
    if ev is None:
        raise NotFoundError("Evidence not found.", code="evidence_not_found")
    return ev


def _duplicates(s: Session, ev: Evidence) -> list[str]:
    stmt = (
        select(Evidence.id)
        .where(Evidence.case_id == ev.case_id, Evidence.sha256 == ev.sha256, Evidence.id != ev.id)
        .order_by(Evidence.imported_at)
    )
    return list(s.execute(stmt).scalars())


def to_out(s: Session, ev: Evidence) -> EvidenceOut:
    out = EvidenceOut.model_validate(ev)
    out.duplicate_of = _duplicates(s, ev)
    return out


async def import_evidence(
    c: Container,
    s: Session,
    case_id: str,
    raw_filename: str,
    chunks: AsyncIterator[bytes],
    declared_length: int | None,
) -> EvidenceOut:
    require_writable_case(s, case_id)  # fail before reading a multi-GB body
    filename = sanitize_filename(raw_filename)
    evidence_id = new_id()
    result = await c.store.ingest(case_id, evidence_id, chunks, declared_length=declared_length)
    try:
        ev = Evidence(
            id=evidence_id,
            case_id=case_id,
            kind="original",
            original_filename=filename,
            declared_extension=declared_extension(filename),
            size_bytes=result.size,
            md5=result.md5,
            sha1=result.sha1,
            sha256=result.sha256,
            mime_hint=result.mime_hint,
            storage_relpath=c.store.relpath(result.path),
        )
        s.add(ev)
        s.commit()
    except BaseException:
        s.rollback()
        result.path.unlink(missing_ok=True)
        raise
    out = to_out(s, ev)
    c.audit.record(
        "evidence.imported",
        case_id=case_id,
        evidence_id=evidence_id,
        details={
            "filename": filename,
            "raw_filename": raw_filename if raw_filename != filename else None,
            "size_bytes": result.size,
            "md5": result.md5,
            "sha1": result.sha1,
            "sha256": result.sha256,
            "mime_hint": result.mime_hint,
            "duplicate_of": out.duplicate_of,
        },
    )
    return out


def list_evidence(s: Session, case_id: str) -> list[EvidenceOut]:
    from spectra.services.cases import require_case

    require_case(s, case_id)
    rows = list(
        s.execute(
            select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.imported_at)
        ).scalars()
    )
    by_hash: dict[str, list[str]] = {}
    for e in rows:
        by_hash.setdefault(e.sha256, []).append(e.id)
    outs = []
    for e in rows:
        o = EvidenceOut.model_validate(e)
        o.duplicate_of = [i for i in by_hash[e.sha256] if i != e.id]
        outs.append(o)
    return outs


def get_evidence(s: Session, evidence_id: str) -> EvidenceOut:
    return to_out(s, require_evidence(s, evidence_id))


def evidence_file(c: Container, s: Session, evidence_id: str) -> tuple[Evidence, Path]:
    ev = require_evidence(s, evidence_id)
    path = c.store.original_path(ev.case_id, ev.id)
    if not path.is_file():
        raise NotFoundError("The evidence file is missing from the store.", code="evidence_file_missing")
    return ev, path


def hex_view(c: Container, s: Session, evidence_id: str, offset: int, length: int) -> HexView:
    ev, path = evidence_file(c, s, evidence_id)
    if offset > ev.size_bytes:
        raise InvalidRequestError("offset is beyond the end of the file", code="offset_out_of_range")
    data = c.store.read_range(path, offset, length)
    return HexView(
        evidence_id=ev.id,
        offset=offset,
        length=len(data),
        total_size=ev.size_bytes,
        rows=[HexRow(**r) for r in c.store.hex_rows(data, offset)],
    )
