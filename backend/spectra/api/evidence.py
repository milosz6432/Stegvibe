from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from spectra.api.deps import get_container, get_session
from spectra.container import Container
from spectra.schemas.evidence import EvidenceOut, HexView
from spectra.services import evidence as svc

router = APIRouter(prefix="/api", tags=["evidence"])


@router.post(
    "/cases/{case_id}/evidence",
    response_model=EvidenceOut,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def import_evidence(
    case_id: str,
    request: Request,
    filename: str = Query(
        ..., min_length=1, max_length=2048, description="Original file name (display only)"
    ),
    c: Container = Depends(get_container),
    s: Session = Depends(get_session),
):
    """Import a file as read-only evidence.

    The raw request body is the file; it is streamed and never fully buffered.
    """
    length_header = request.headers.get("content-length")
    declared = int(length_header) if length_header and length_header.isdigit() else None
    return await svc.import_evidence(c, s, case_id, filename, request.stream(), declared)


@router.get("/cases/{case_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(case_id: str, s: Session = Depends(get_session)):
    return svc.list_evidence(s, case_id)


@router.get("/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(evidence_id: str, s: Session = Depends(get_session)):
    return svc.get_evidence(s, evidence_id)


@router.get("/evidence/{evidence_id}/hex", response_model=HexView)
def hex_view(
    evidence_id: str,
    offset: int = Query(0, ge=0),
    length: int = Query(512, ge=1),
    c: Container = Depends(get_container),
    s: Session = Depends(get_session),
):
    """A bounded window of the original's bytes as hex/ASCII rows (length is clamped by server limits)."""
    return svc.hex_view(c, s, evidence_id, offset, length)


@router.get("/evidence/{evidence_id}/download")
def download(evidence_id: str, c: Container = Depends(get_container), s: Session = Depends(get_session)):
    """Exact original bytes. Always an attachment of type application/octet-stream so it can never render."""
    ev, path = svc.evidence_file(c, s, evidence_id)
    c.audit.record(
        "evidence.downloaded",
        case_id=ev.case_id,
        evidence_id=ev.id,
        details={"filename": ev.original_filename, "sha256": ev.sha256},
    )
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=ev.original_filename,
        content_disposition_type="attachment",
    )
