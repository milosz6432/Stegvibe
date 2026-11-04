from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from spectra import SCHEMA_VERSION, __version__
from spectra.api.deps import get_container, get_session
from spectra.container import Container
from spectra.core.deps import DependencyStatus
from spectra.db.models import AuditEntry, Case, Evidence, Finding, Job
from spectra.schemas.misc import StatsOut

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(c: Container = Depends(get_container)) -> dict[str, Any]:
    db_ok, db_error = True, None
    try:
        with c.session_factory() as s:
            s.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_ok, db_error = False, str(exc)

    storage_ok, storage_error = True, None
    try:
        with tempfile.NamedTemporaryFile(dir=c.settings.tmp_dir):
            pass
    except OSError as exc:
        storage_ok, storage_error = False, str(exc)
    free = shutil.disk_usage(c.settings.data_dir).free if c.settings.data_dir.exists() else None

    return {
        "status": "ok" if db_ok and storage_ok else "degraded",
        "version": __version__,
        "database": {"ok": db_ok, "error": db_error, "schema_version": SCHEMA_VERSION},
        "storage": {"writable": storage_ok, "error": storage_error, "free_bytes": free},
    }


@router.get("/system/info")
def system_info(c: Container = Depends(get_container)) -> dict[str, Any]:
    s = c.settings
    try:
        import resource  # noqa: F401

        rlimits = True
    except ImportError:
        rlimits = False
    return {
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "data_dir": str(s.data_dir.resolve()),
        "offline": True,  # the server contains no outbound network code (enforced by a test)
        "limits": {
            "max_upload_bytes": s.max_upload_bytes,
            "max_hex_read_bytes": s.max_hex_read_bytes,
            "max_concurrent_jobs": s.max_concurrent_jobs,
            "default_job_timeout_seconds": s.default_job_timeout_seconds,
            "max_job_timeout_seconds": s.max_job_timeout_seconds,
            "default_job_memory_limit_mb": s.default_job_memory_limit_mb,
        },
        "isolation": {
            "worker_subprocess": True,
            "memory_and_cpu_rlimits": rlimits,
            "process_group_kill": hasattr(os, "killpg"),
        },
        "plugins": len(c.registry),
        "plugin_load_errors": c.registry.load_errors,
    }


@router.get("/system/dependencies")
def dependencies(
    deep: bool = False, refresh: bool = False, c: Container = Depends(get_container)
) -> dict[str, Any]:
    items: list[DependencyStatus] = c.deps.check_all(deep=deep, refresh=refresh)
    return {"summary": c.deps.summarize(items), "deep": deep, "items": items}


@router.get("/stats", response_model=StatsOut)
def stats(s: Session = Depends(get_session)) -> StatsOut:
    cases = s.scalar(select(func.count()).select_from(Case)) or 0
    archived = s.scalar(select(func.count()).select_from(Case).where(Case.archived.is_(True))) or 0
    ev_n, ev_bytes = s.execute(select(func.count(), func.coalesce(func.sum(Evidence.size_bytes), 0))).one()
    by_kind = dict(s.execute(select(Finding.kind, func.count()).group_by(Finding.kind)).all())
    by_status = dict(s.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    audit_n = s.scalar(select(func.count()).select_from(AuditEntry)) or 0
    return StatsOut(
        cases=cases,
        archived_cases=archived,
        evidence=ev_n,
        evidence_bytes=int(ev_bytes),
        findings=sum(by_kind.values()),
        findings_by_kind=by_kind,
        jobs_by_status=by_status,
        audit_entries=audit_n,
    )
