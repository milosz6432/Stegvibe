"""Jobs, derived artifacts and findings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from spectra.api.deps import get_container, get_session
from spectra.container import Container
from spectra.core.errors import NotFoundError
from spectra.core.security import resolve_within
from spectra.db.models import Finding, Job
from spectra.schemas.jobs import FindingOut, FindingPage, JobCreate, JobOut

router = APIRouter(prefix="/api", tags=["jobs", "findings"])


@router.post("/jobs", response_model=JobOut, status_code=202)
def create_job(body: JobCreate, c: Container = Depends(get_container)):
    """Queue a plugin run. Returns immediately; poll ``GET /api/jobs/{id}`` for progress."""
    return c.jobs.submit(
        evidence_id=body.evidence_id,
        plugin_id=body.plugin_id,
        config=body.config,
        timeout_seconds=body.timeout_seconds,
        memory_limit_mb=body.memory_limit_mb,
    )


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    case_id: str | None = None,
    evidence_id: str | None = None,
    status: str | None = Query(None, pattern="^(queued|running|succeeded|failed|cancelled)$"),
    limit: int = Query(100, ge=1, le=500),
    s: Session = Depends(get_session),
):
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if case_id:
        stmt = stmt.where(Job.case_id == case_id)
    if evidence_id:
        stmt = stmt.where(Job.evidence_id == evidence_id)
    if status:
        stmt = stmt.where(Job.status == status)
    return list(s.execute(stmt).scalars())


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, c: Container = Depends(get_container)):
    return c.jobs.get(job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, c: Container = Depends(get_container)):
    return c.jobs.cancel(job_id)


@router.get("/jobs/{job_id}/artifacts/{name:path}")
def download_artifact(job_id: str, name: str, c: Container = Depends(get_container)):
    """Download a file a plugin derived from the evidence (never the original)."""
    job = c.jobs.get(job_id)
    listed = {a["name"] for a in ((job.result or {}).get("artifacts") or [])}
    if name not in listed:
        raise NotFoundError("No such artifact for this job.", code="artifact_not_found")
    path = resolve_within(c.store.derived_dir(job.case_id, job.id), name)
    if path.is_symlink() or not path.is_file():
        raise NotFoundError("Artifact file is missing.", code="artifact_not_found")
    c.audit.record(
        "artifact.downloaded",
        case_id=job.case_id,
        evidence_id=job.evidence_id,
        job_id=job.id,
        details={"name": name},
    )
    return FileResponse(
        path, media_type="application/octet-stream", filename=path.name, content_disposition_type="attachment"
    )


@router.get("/findings", response_model=FindingPage)
def list_findings(
    case_id: str | None = None,
    evidence_id: str | None = None,
    job_id: str | None = None,
    kind: str | None = None,
    confidence: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    s: Session = Depends(get_session),
):
    conds = []
    if case_id:
        conds.append(Finding.case_id == case_id)
    if evidence_id:
        conds.append(Finding.evidence_id == evidence_id)
    if job_id:
        conds.append(Finding.job_id == job_id)
    if kind:
        conds.append(Finding.kind == kind)
    if confidence:
        conds.append(Finding.confidence == confidence)
    total = s.scalar(select(func.count()).select_from(Finding).where(*conds)) or 0
    rows = s.execute(
        select(Finding).where(*conds).order_by(Finding.created_at.desc()).limit(limit).offset(offset)
    ).scalars()
    return FindingPage(items=[FindingOut.model_validate(r) for r in rows], total=total)


@router.get("/findings/{finding_id}", response_model=FindingOut)
def get_finding(finding_id: str, s: Session = Depends(get_session)):
    f = s.get(Finding, finding_id)
    if f is None:
        raise NotFoundError("Finding not found.", code="finding_not_found")
    return f
