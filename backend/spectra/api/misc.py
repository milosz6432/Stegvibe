"""Notes, audit log and plugin catalogue endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from spectra.api.deps import get_container, get_session
from spectra.container import Container
from spectra.plugins.registry import PluginRegistry
from spectra.schemas.misc import AuditOut, AuditVerifyOut, NoteCreate, NoteOut, NoteUpdate
from spectra.schemas.plugins import PluginInfo
from spectra.services import notes as notes_svc

router = APIRouter(prefix="/api", tags=["notes", "audit", "plugins"])


# ---- notes ------------------------------------------------------------------
@router.post("/cases/{case_id}/notes", response_model=NoteOut, status_code=201)
def create_note(
    case_id: str, body: NoteCreate, c: Container = Depends(get_container), s: Session = Depends(get_session)
):
    return notes_svc.create_note(c, s, case_id, body.body, body.evidence_id)


@router.get("/cases/{case_id}/notes", response_model=list[NoteOut])
def list_notes(case_id: str, evidence_id: str | None = None, s: Session = Depends(get_session)):
    return notes_svc.list_notes(s, case_id, evidence_id)


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: str, body: NoteUpdate, c: Container = Depends(get_container), s: Session = Depends(get_session)
):
    return notes_svc.update_note(c, s, note_id, body.body)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: str, c: Container = Depends(get_container), s: Session = Depends(get_session)):
    notes_svc.delete_note(c, s, note_id)
    return Response(status_code=204)


# ---- audit ------------------------------------------------------------------
@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    case_id: str | None = None,
    evidence_id: str | None = None,
    job_id: str | None = None,
    action_prefix: str | None = Query(None, max_length=64),
    limit: int = Query(100, ge=1, le=1000),
    before_seq: int | None = Query(None, ge=1),
    c: Container = Depends(get_container),
):
    return c.audit.list(
        case_id=case_id,
        evidence_id=evidence_id,
        job_id=job_id,
        action_prefix=action_prefix,
        limit=limit,
        before_seq=before_seq,
    )


@router.get("/audit/verify", response_model=AuditVerifyOut)
def verify_audit(c: Container = Depends(get_container)):
    """Recompute the whole hash chain. Tamper-evident, not tamper-proof (see docs/ARCHITECTURE.md §5)."""
    return c.audit.verify().__dict__


# ---- plugins ----------------------------------------------------------------
@router.get("/plugins", response_model=list[PluginInfo])
def list_plugins(format: str | None = Query(None, max_length=32), c: Container = Depends(get_container)):
    reg: PluginRegistry = c.registry
    return reg.list_info(format)


@router.get("/plugins/{plugin_id}", response_model=PluginInfo)
def get_plugin(plugin_id: str, c: Container = Depends(get_container)):
    return c.registry.info(c.registry.get(plugin_id))
