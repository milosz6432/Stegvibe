"""Case lifecycle."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from spectra.container import Container
from spectra.core.errors import ConflictError, InvalidRequestError, NotFoundError
from spectra.db.base import utcnow
from spectra.db.models import Case, Evidence, Finding, Job, Note
from spectra.schemas.cases import CaseOut


def require_case(s: Session, case_id: str) -> Case:
    case = s.get(Case, case_id)
    if case is None:
        raise NotFoundError("Case not found.", code="case_not_found")
    return case


def require_writable_case(s: Session, case_id: str) -> Case:
    case = require_case(s, case_id)
    if case.archived:
        raise ConflictError("This case is archived and read-only.", code="case_archived")
    return case


def _counts(s: Session, case_ids: list[str] | None = None) -> dict[str, dict[str, int]]:
    def scoped(stmt, col):
        return stmt.where(col.in_(case_ids)) if case_ids is not None else stmt

    ev = scoped(
        select(Evidence.case_id, func.count(), func.coalesce(func.sum(Evidence.size_bytes), 0)).group_by(
            Evidence.case_id
        ),
        Evidence.case_id,
    )
    jobs = scoped(select(Job.case_id, func.count()).group_by(Job.case_id), Job.case_id)
    fnd = scoped(select(Finding.case_id, func.count()).group_by(Finding.case_id), Finding.case_id)
    out: dict[str, dict[str, int]] = {}
    for cid, n, total in s.execute(ev):
        out.setdefault(cid, {}).update(evidence_count=n, total_bytes=int(total))
    for cid, n in s.execute(jobs):
        out.setdefault(cid, {})["job_count"] = n
    for cid, n in s.execute(fnd):
        out.setdefault(cid, {})["finding_count"] = n
    return out


def to_out(case: Case, counts: dict[str, int] | None = None) -> CaseOut:
    return CaseOut(
        id=case.id,
        name=case.name,
        description=case.description,
        archived=case.archived,
        created_at=case.created_at,
        updated_at=case.updated_at,
        **(counts or {}),
    )


def create_case(c: Container, s: Session, name: str, description: str) -> CaseOut:
    case = Case(name=name, description=description)
    s.add(case)
    s.commit()
    c.audit.record("case.created", case_id=case.id, details={"name": name})
    return to_out(case)


def list_cases(s: Session, include_archived: bool = False) -> list[CaseOut]:
    stmt = select(Case).order_by(Case.updated_at.desc())
    if not include_archived:
        stmt = stmt.where(Case.archived.is_(False))
    cases = list(s.execute(stmt).scalars())
    counts = _counts(s, [x.id for x in cases])
    return [to_out(x, counts.get(x.id)) for x in cases]


def get_case(s: Session, case_id: str) -> CaseOut:
    case = require_case(s, case_id)
    return to_out(case, _counts(s, [case.id]).get(case.id))


def update_case(
    c: Container,
    s: Session,
    case_id: str,
    *,
    name: str | None,
    description: str | None,
    archived: bool | None,
) -> CaseOut:
    case = require_case(s, case_id)
    changes: dict[str, object] = {}
    if name is not None and name != case.name:
        changes["name"] = {"from": case.name, "to": name}
        case.name = name
    if description is not None and description != case.description:
        changes["description"] = "changed"
        case.description = description
    if archived is not None and archived != case.archived:
        changes["archived"] = archived
        case.archived = archived
    if changes:
        case.updated_at = utcnow()
        s.commit()
        action = "case.updated"
        if set(changes) == {"archived"}:
            action = "case.archived" if archived else "case.unarchived"
        c.audit.record(action, case_id=case.id, details=changes)
    return to_out(case, _counts(s, [case.id]).get(case.id))


def purge_case(c: Container, s: Session, case_id: str, confirm_name: str) -> None:
    """Irreversibly delete a case, its evidence files and derived data. The audit trail is kept."""
    case = require_case(s, case_id)
    if confirm_name != case.name:
        raise InvalidRequestError(
            "The confirmation text must exactly match the case name.", code="confirmation_mismatch"
        )
    if c.jobs.active_count(case_id):
        raise ConflictError("Cancel or wait for running jobs before purging this case.", code="jobs_active")

    evidence = [
        {"id": e.id, "filename": e.original_filename, "size_bytes": e.size_bytes, "sha256": e.sha256}
        for e in s.execute(select(Evidence).where(Evidence.case_id == case_id)).scalars()
    ]
    removed = {
        "findings": s.execute(delete(Finding).where(Finding.case_id == case_id)).rowcount,
        "jobs": s.execute(delete(Job).where(Job.case_id == case_id)).rowcount,
        "notes": s.execute(delete(Note).where(Note.case_id == case_id)).rowcount,
    }
    s.execute(delete(Evidence).where(Evidence.case_id == case_id))
    name = case.name
    s.delete(case)
    s.commit()
    c.store.purge_case_files(case_id)
    c.audit.record(
        "case.purged", case_id=case_id, details={"name": name, "evidence": evidence, "deleted_rows": removed}
    )
