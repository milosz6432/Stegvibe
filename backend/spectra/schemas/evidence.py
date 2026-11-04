from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    kind: str
    original_filename: str
    declared_extension: str | None
    size_bytes: int
    md5: str
    sha1: str
    sha256: str
    mime_hint: str | None
    detected_format: str | None
    format_confidence: str | None
    parent_id: str | None
    derivation: dict[str, Any] | None
    imported_at: datetime
    duplicate_of: list[str] = []


class HexRow(BaseModel):
    offset: int
    hex: str
    ascii: str


class HexView(BaseModel):
    evidence_id: str
    offset: int
    length: int
    total_size: int
    rows: list[HexRow]
