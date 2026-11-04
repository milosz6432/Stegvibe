from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from spectra.api.deps import get_container, get_session
from spectra.container import Container
from spectra.schemas.cases import CaseCreate, CaseOut, CasePurge, CaseUpdate
from spectra.services import cases as svc

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("", response_model=CaseOut, status_code=201)
def create_case(body: CaseCreate, c: Container = Depends(get_container), s: Session = Depends(get_session)):
    return svc.create_case(c, s, body.name, body.description)


@router.get("", response_model=list[CaseOut])
def list_cases(include_archived: bool = False, s: Session = Depends(get_session)):
    return svc.list_cases(s, include_archived)


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: str, s: Session = Depends(get_session)):
    return svc.get_case(s, case_id)


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: str, body: CaseUpdate, c: Container = Depends(get_container), s: Session = Depends(get_session)
):
    return svc.update_case(
        c, s, case_id, name=body.name, description=body.description, archived=body.archived
    )


@router.post("/{case_id}/purge", status_code=204)
def purge_case(
    case_id: str, body: CasePurge, c: Container = Depends(get_container), s: Session = Depends(get_session)
):
    """Irreversible. The body must repeat the case name exactly."""
    svc.purge_case(c, s, case_id, body.confirm_name)
    return Response(status_code=204)
