"""Job queue and supervisor.

One supervisor thread per running job (bounded by ``max_concurrent_jobs``) owns one spawned worker process.
The supervisor is the only writer of job state; workers cannot touch the database or the audit log.
"""

from __future__ import annotations

import hashlib
import json
import logging
import multiprocessing
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from spectra.config import Settings
from spectra.core.audit import AuditService
from spectra.core.errors import ConflictError, InvalidRequestError, NotFoundError
from spectra.core.evidence_store import EvidenceStore
from spectra.db.base import utcnow
from spectra.db.models import Case, Evidence, Finding, Job
from spectra.jobs.worker import worker_main
from spectra.plugins.base import Confidence, PluginResult
from spectra.plugins.registry import PluginRegistry

log = logging.getLogger(__name__)

TERMINAL = {"succeeded", "failed", "cancelled"}
MIN_MEMORY_LIMIT_MB = 256


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def scan_artifacts(output_dir: Path, max_files: int) -> tuple[list[dict[str, Any]], bool]:
    """List regular files a plugin produced.

    Symlinks are ignored (they could point at evidence or the host).
    """
    artifacts: list[dict[str, Any]] = []
    truncated = False
    if not output_dir.is_dir():
        return artifacts, truncated
    root = output_dir.resolve()
    for dirpath, _dirs, files in os.walk(output_dir, followlinks=False):
        for fname in sorted(files):
            p = Path(dirpath) / fname
            if p.is_symlink() or not p.is_file():
                continue
            if len(artifacts) >= max_files:
                truncated = True
                return artifacts, truncated
            artifacts.append(
                {
                    "name": p.resolve().relative_to(root).as_posix(),
                    "size_bytes": p.stat().st_size,
                    "sha256": _sha256_file(p),
                }
            )
    return artifacts, truncated


class JobManager:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        registry: PluginRegistry,
        store: EvidenceStore,
        audit: AuditService,
    ):
        self.settings = settings
        self._sf = session_factory
        self.registry = registry
        self.store = store
        self.audit = audit
        self._pool = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_jobs, thread_name_prefix="spectra-job"
        )
        self._cancel: dict[str, threading.Event] = {}
        self._guard = threading.Lock()
        self._closing = False
        self._mp = multiprocessing.get_context("spawn")

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def submit(
        self,
        *,
        evidence_id: str,
        plugin_id: str,
        config: dict | None,
        timeout_seconds: int | None = None,
        memory_limit_mb: int | None = None,
    ) -> Job:
        if self._closing:
            raise ConflictError("The server is shutting down.", code="shutting_down")
        entry = self.registry.get(plugin_id)
        available, reason, _ = self.registry.availability(entry)
        if not available:
            raise ConflictError(f"Plugin '{plugin_id}' is unavailable: {reason}", code="plugin_unavailable")

        timeout = (
            timeout_seconds if timeout_seconds is not None else self.settings.default_job_timeout_seconds
        )
        if not 1 <= timeout <= self.settings.max_job_timeout_seconds:
            raise InvalidRequestError(
                f"timeout_seconds must be between 1 and {self.settings.max_job_timeout_seconds}"
            )
        memory = memory_limit_mb if memory_limit_mb is not None else self.settings.default_job_memory_limit_mb
        if memory != 0 and memory < MIN_MEMORY_LIMIT_MB:
            raise InvalidRequestError(
                f"memory_limit_mb must be 0 (unlimited) or at least {MIN_MEMORY_LIMIT_MB}"
            )

        try:
            cfg = entry.cls.ConfigModel.model_validate(config or {}).model_dump(mode="json")
        except ValidationError as exc:
            raise InvalidRequestError(
                "Invalid plugin configuration.",
                details=json.loads(exc.json(include_url=False, include_context=False)),
                code="invalid_plugin_config",
            ) from None

        with self._sf() as s:
            ev = s.get(Evidence, evidence_id)
            if ev is None:
                raise NotFoundError("Evidence not found.", code="evidence_not_found")
            case = s.get(Case, ev.case_id)
            if case is not None and case.archived:
                raise ConflictError("This case is archived and read-only.", code="case_archived")
            if not self.registry.supports_format(entry, ev.detected_format):
                if ev.detected_format is None:
                    raise InvalidRequestError(
                        f"Plugin '{plugin_id}' only handles specific formats and this evidence has not been "
                        "format-identified yet (identification arrives in Phase 2).",
                        code="format_not_identified",
                    )
                raise InvalidRequestError(
                    f"Plugin '{plugin_id}' does not support format '{ev.detected_format}'.",
                    code="format_not_supported",
                )
            job = Job(
                case_id=ev.case_id,
                evidence_id=ev.id,
                plugin_id=entry.meta.id,
                plugin_version=entry.meta.version,
                config=cfg,
                status="queued",
                timeout_seconds=timeout,
                memory_limit_mb=memory,
            )
            s.add(job)
            s.commit()
            snapshot = _detach(job)

        with self._guard:
            self._cancel[job.id] = threading.Event()
        self.audit.record(
            "job.created",
            case_id=job.case_id,
            evidence_id=job.evidence_id,
            job_id=job.id,
            details={
                "plugin_id": job.plugin_id,
                "plugin_version": job.plugin_version,
                "config": cfg,
                "timeout_seconds": timeout,
                "memory_limit_mb": memory,
            },
        )
        self._pool.submit(self._run, job.id)
        return snapshot

    def cancel(self, job_id: str, wait_seconds: float = 3.0) -> Job:
        with self._sf() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise NotFoundError("Job not found.", code="job_not_found")
            status = job.status
        if status in TERMINAL:
            return self.get(job_id)

        with self._guard:
            event = self._cancel.get(job_id)
        if event:
            event.set()

        if status == "queued":  # never started: cancel immediately without waiting for a pool slot
            with self._sf() as s:
                res = s.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.status == "queued")
                    .values(
                        status="cancelled",
                        error_code="cancelled",
                        finished_at=utcnow(),
                        error_message="Cancelled before it started.",
                    )
                )
                s.commit()
                won = res.rowcount == 1
            if won:
                j = self.get(job_id)
                self.audit.record(
                    "job.cancelled",
                    case_id=j.case_id,
                    evidence_id=j.evidence_id,
                    job_id=job_id,
                    details={"was": "queued"},
                )
                return j

        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            j = self.get(job_id)
            if j.status in TERMINAL:
                return j
            time.sleep(0.05)
        return self.get(job_id)

    def get(self, job_id: str) -> Job:
        with self._sf() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise NotFoundError("Job not found.", code="job_not_found")
            return _detach(job)

    def active_count(self, case_id: str | None = None) -> int:
        with self._sf() as s:
            stmt = select(Job.id).where(Job.status.in_(("queued", "running")))
            if case_id:
                stmt = stmt.where(Job.case_id == case_id)
            return len(s.execute(stmt).all())

    def recover_interrupted(self) -> int:
        """Jobs left queued/running by a previous process can never finish; mark them failed (and say why)."""
        with self._sf() as s:
            rows = list(s.execute(select(Job).where(Job.status.in_(("queued", "running")))).scalars())
            for j in rows:
                j.status = "failed"
                j.error_code = "interrupted"
                j.error_message = "The server stopped while this job was queued or running."
                j.finished_at = utcnow()
            s.commit()
            details = [(j.id, j.case_id, j.evidence_id) for j in rows]
        for jid, cid, eid in details:
            self.store.remove_derived(cid, jid)
            self.audit.record("job.interrupted", actor="system", case_id=cid, evidence_id=eid, job_id=jid)
        return len(details)

    def shutdown(self) -> None:
        self._closing = True
        with self._guard:
            for ev in self._cancel.values():
                ev.set()
        self._pool.shutdown(wait=True, cancel_futures=True)

    # ------------------------------------------------------------------
    # supervision
    # ------------------------------------------------------------------
    def _run(self, job_id: str) -> None:
        with self._guard:
            event = self._cancel.get(job_id) or threading.Event()
        try:
            self._run_inner(job_id, event)
        except Exception as exc:  # noqa: BLE001 - never let a supervisor thread die silently
            log.exception("supervisor failure for job %s", job_id)
            self._finish(
                job_id, "failed", error_code="supervisor_error", error_message=f"{type(exc).__name__}: {exc}"
            )
        finally:
            with self._guard:
                self._cancel.pop(job_id, None)

    def _run_inner(self, job_id: str, event: threading.Event) -> None:
        with self._sf() as s:
            res = s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "queued")
                .values(status="running", started_at=utcnow())
            )
            s.commit()
            if res.rowcount != 1:
                return  # cancelled while queued
            job = s.get(Job, job_id)
            ev = s.get(Evidence, job.evidence_id)
            assert job is not None and ev is not None
            job_snap, ev_snap = _detach(job), _detach(ev)

        self.audit.record(
            "job.started",
            actor="system",
            case_id=job_snap.case_id,
            evidence_id=job_snap.evidence_id,
            job_id=job_id,
            details={"plugin_id": job_snap.plugin_id},
        )
        entry = self.registry.get(job_snap.plugin_id)
        output_dir = self.store.derived_dir(job_snap.case_id, job_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        spec = {
            "entrypoint": entry.entrypoint,
            "config": job_snap.config,
            "output_dir": str(output_dir),
            "memory_limit_mb": job_snap.memory_limit_mb,
            "cpu_seconds": job_snap.timeout_seconds,
            "evidence": {
                "id": ev_snap.id,
                "case_id": ev_snap.case_id,
                "filename": ev_snap.original_filename,
                "size_bytes": ev_snap.size_bytes,
                "md5": ev_snap.md5,
                "sha1": ev_snap.sha1,
                "sha256": ev_snap.sha256,
                "detected_format": ev_snap.detected_format,
                "path": str(self.store.original_path(ev_snap.case_id, ev_snap.id)),
            },
        }

        kind, data = self._supervise(job_id, spec, job_snap.timeout_seconds, event)

        if kind == "result":
            self._finish_success(job_snap, ev_snap, entry, data, output_dir)
            return
        # every non-success path discards partial derived output
        self.store.remove_derived(job_snap.case_id, job_id)
        if kind == "cancelled":
            self._finish(job_id, "cancelled", error_code="cancelled", error_message="Cancelled by the user.")
        elif kind == "timeout":
            self._finish(
                job_id,
                "failed",
                error_code="timeout",
                error_message=f"Exceeded the time limit of {job_snap.timeout_seconds} s and was terminated.",
            )
        elif kind == "error":
            self._finish(
                job_id,
                "failed",
                error_code=data.get("code", "plugin_error"),
                error_message=data.get("message", "unknown error"),
                extra={"traceback": data.get("traceback", "")},
            )
        else:  # crashed
            self._finish(job_id, "failed", error_code="crashed", error_message=str(data))

    def _supervise(self, job_id: str, spec: dict, timeout: int, event: threading.Event) -> tuple[str, Any]:
        parent_conn, child_conn = self._mp.Pipe(duplex=False)
        proc = self._mp.Process(
            target=worker_main, args=(spec, child_conn), name=f"spectra-worker-{job_id[:8]}"
        )
        proc.start()
        child_conn.close()  # parent keeps only the read end so EOF is observable
        deadline = time.monotonic() + timeout
        last_db_write = 0.0
        try:
            while True:
                if event.is_set():
                    self._kill(proc)
                    return "cancelled", None
                if time.monotonic() > deadline:
                    self._kill(proc)
                    return "timeout", None
                try:
                    ready = parent_conn.poll(0.1)
                except (OSError, EOFError):
                    ready = False
                if ready:
                    try:
                        msg = parent_conn.recv()
                    except (EOFError, OSError):
                        break  # child closed its end without a final message
                    tag = msg[0]
                    if tag == "progress":
                        now = time.monotonic()
                        if now - last_db_write >= 0.25 or msg[1] >= 1.0:
                            last_db_write = now
                            self._set_progress(job_id, msg[1], msg[2])
                    elif tag == "result":
                        return "result", msg[1]
                    elif tag == "error":
                        return "error", msg[1]
                elif not proc.is_alive():
                    if parent_conn.poll(0):
                        continue  # drain messages that raced with process exit
                    break
            proc.join(timeout=5)
            code = proc.exitcode
            if code is not None and code < 0:
                try:
                    name = signal.Signals(-code).name
                except ValueError:
                    name = str(-code)
                return "crashed", f"The worker process was killed by signal {name}."
            return (
                "crashed",
                f"The worker process exited unexpectedly (exit code {code}) without producing a result.",
            )
        finally:
            parent_conn.close()
            if proc.is_alive():
                proc.join(timeout=5)
                if proc.is_alive():
                    self._kill(proc)

    @staticmethod
    def _kill(proc) -> None:
        """Terminate the worker and everything in its process group (POSIX), escalating to SIGKILL."""
        pid = proc.pid
        if pid is None:
            return
        if hasattr(os, "killpg"):
            try:
                os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
            proc.join(timeout=2.0)
            try:
                os.killpg(pid, signal.SIGKILL)  # stragglers that ignore SIGTERM
            except (ProcessLookupError, PermissionError):
                pass
            if proc.is_alive():
                proc.kill()
            proc.join(timeout=5)
        else:  # pragma: no cover - Windows: helper processes may outlive the worker (documented)
            proc.terminate()
            proc.join(timeout=2.0)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=5)

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def _set_progress(self, job_id: str, fraction: float, message: str) -> None:
        with self._sf() as s:
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "running")
                .values(progress=max(0.0, min(1.0, fraction)), progress_message=message[:500])
            )
            s.commit()

    def _finish(
        self,
        job_id: str,
        status: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        extra: dict | None = None,
    ) -> None:
        with self._sf() as s:
            job = s.get(Job, job_id)
            if job is None or job.status in TERMINAL:
                return
            job.status = status
            job.error_code = error_code
            job.error_message = error_message
            job.finished_at = utcnow()
            if extra:
                job.result = {"diagnostics": extra}
            s.commit()
            cid, eid = job.case_id, job.evidence_id
        self.audit.record(
            f"job.{status}",
            actor="system",
            case_id=cid,
            evidence_id=eid,
            job_id=job_id,
            details={"error_code": error_code, "error_message": error_message} if error_code else {},
        )

    def _finish_success(self, job, ev, entry, payload: dict, output_dir: Path) -> None:
        try:
            result = PluginResult.model_validate(payload)
            if not entry.meta.deterministic:
                bad = [f.title for f in result.findings if f.confidence == Confidence.VERIFIED]
                if bad:
                    raise ValueError(
                        "heuristic plugins may not emit 'verified' findings (offending: "
                        + "; ".join(bad[:3])
                        + ")"
                    )
            artifacts, truncated = scan_artifacts(output_dir, self.settings.max_artifacts_per_job)
        except Exception as exc:  # noqa: BLE001
            self.store.remove_derived(job.case_id, job.id)
            self._finish(
                job.id, "failed", error_code="invalid_result", error_message=f"{type(exc).__name__}: {exc}"
            )
            return

        warnings = list(result.warnings)
        if truncated:
            warnings.append(f"Artifact list truncated at {self.settings.max_artifacts_per_job} files.")
        with self._sf() as s:
            row = s.get(Job, job.id)
            if row is None or row.status in TERMINAL:
                return
            for f in result.findings:
                s.add(
                    Finding(
                        case_id=job.case_id,
                        evidence_id=job.evidence_id,
                        job_id=job.id,
                        plugin_id=entry.meta.id,
                        plugin_version=entry.meta.version,
                        kind=f.kind.value,
                        confidence=f.confidence.value,
                        title=f.title,
                        description=f.description,
                        location=f.location,
                        data=f.data,
                        config=job.config,
                        evidence_sha256=ev.sha256,
                        limitations=f.limitations,
                    )
                )
            row.status = "succeeded"
            row.progress = 1.0
            row.finished_at = utcnow()
            row.result = {
                "summary": result.summary,
                "warnings": warnings,
                "finding_count": len(result.findings),
                "artifacts": artifacts,
            }
            s.commit()
        self.audit.record(
            "job.succeeded",
            actor="system",
            case_id=job.case_id,
            evidence_id=job.evidence_id,
            job_id=job.id,
            details={"findings": len(result.findings), "artifacts": len(artifacts)},
        )


def _detach(obj):
    """Expunge-safe copy semantics: sessions here use expire_on_commit=False, so attributes stay readable."""
    return obj
