from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class CaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    archived: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class CasePurge(BaseModel):
    confirm_name: str


class CaseOut(BaseModel):
    id: str
    name: str
    description: str
    archived: bool
    created_at: datetime
    updated_at: datetime
    evidence_count: int = 0
    total_bytes: int = 0
    job_count: int = 0
    finding_count: int = 0
