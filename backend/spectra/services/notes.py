"""Case and evidence notes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from spectra.container import Container
from spectra.core.errors import InvalidRequestError, NotFoundError
from spectra.db.base import utcnow
from spectra.db.models import Evidence, Note
from spectra.services.cases import require_case, require_writable_case


def _require_note(s: Session, note_id: str) -> Note:
    note = s.get(Note, note_id)
    if note is None:
        raise NotFoundError("Note not found.", code="note_not_found")
    return note


def create_note(c: Container, s: Session, case_id: str, body: str, evidence_id: str | None) -> Note:
    require_writable_case(s, case_id)
    if evidence_id is not None:
        ev = s.get(Evidence, evidence_id)
        if ev is None or ev.case_id != case_id:
            raise InvalidRequestError("evidence_id does not belong to this case", code="evidence_not_in_case")
    note = Note(case_id=case_id, evidence_id=evidence_id, body=body)
    s.add(note)
    s.commit()
    c.audit.record(
        "note.created",
        case_id=case_id,
        evidence_id=evidence_id,
        details={"note_id": note.id, "chars": len(body)},
    )
    return note


def list_notes(s: Session, case_id: str, evidence_id: str | None) -> list[Note]:
    require_case(s, case_id)
    stmt = select(Note).where(Note.case_id == case_id).order_by(Note.created_at.desc())
    if evidence_id:
        stmt = stmt.where(Note.evidence_id == evidence_id)
    return list(s.execute(stmt).scalars())


def update_note(c: Container, s: Session, note_id: str, body: str) -> Note:
    note = _require_note(s, note_id)
    require_writable_case(s, note.case_id)
    note.body = body
    note.updated_at = utcnow()
    s.commit()
    c.audit.record(
        "note.updated", case_id=note.case_id, evidence_id=note.evidence_id, details={"note_id": note.id}
    )
    return note


def delete_note(c: Container, s: Session, note_id: str) -> None:
    note = _require_note(s, note_id)
    require_writable_case(s, note.case_id)
    cid, eid = note.case_id, note.evidence_id
    s.delete(note)
    s.commit()
    c.audit.record("note.deleted", case_id=cid, evidence_id=eid, details={"note_id": note_id})
