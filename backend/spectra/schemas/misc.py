from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    evidence_id: str | None = None


class NoteUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    evidence_id: str | None
    body: str
    created_at: datetime
    updated_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    ts: str
    actor: str
    action: str
    case_id: str | None
    evidence_id: str | None
    job_id: str | None
    details: dict[str, Any] = Field(validation_alias="details_json")
    prev_hash: str
    entry_hash: str

    @field_validator("details", mode="before")
    @classmethod
    def _parse(cls, v: Any) -> Any:
        return json.loads(v) if isinstance(v, str) else v


class AuditVerifyOut(BaseModel):
    valid: bool
    entries_checked: int
    head_hash: str
    first_invalid_seq: int | None = None
    reason: str | None = None


class StatsOut(BaseModel):
    cases: int
    archived_cases: int
    evidence: int
    evidence_bytes: int
    findings: int
    findings_by_kind: dict[str, int]
    jobs_by_status: dict[str, int]
    audit_entries: int
