from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    evidence_id: str
    plugin_id: str
    config: dict[str, Any] = {}
    timeout_seconds: int | None = Field(default=None, ge=1)
    memory_limit_mb: int | None = Field(default=None, ge=0)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    evidence_id: str
    plugin_id: str
    plugin_version: str
    config: dict[str, Any]
    status: str
    error_code: str | None
    error_message: str | None
    progress: float
    progress_message: str
    timeout_seconds: int
    memory_limit_mb: int
    result: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    evidence_id: str
    job_id: str | None
    plugin_id: str
    plugin_version: str
    kind: str
    confidence: str
    title: str
    description: str
    location: dict[str, Any] | None
    data: dict[str, Any]
    config: dict[str, Any]
    evidence_sha256: str
    limitations: str | None
    created_at: datetime


class FindingPage(BaseModel):
    items: list[FindingOut]
    total: int
