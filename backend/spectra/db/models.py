"""ORM models (schema version 1). See docs/ARCHITECTURE.md §5."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from spectra.db.base import Base, UTCDateTime, new_id, utcnow


class SchemaMeta(Base):
    __tablename__ = "schema_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_case_sha256", "case_id", "sha256"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="original")  # original | derived
    original_filename: Mapped[str] = mapped_column(String(255))
    declared_extension: Mapped[str | None] = mapped_column(String(16), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    md5: Mapped[str] = mapped_column(String(32))
    sha1: Mapped[str] = mapped_column(String(40))
    sha256: Mapped[str] = mapped_column(String(64))
    # Preliminary libmagic guess recorded at import. NOT the identification result (Phase 2).
    mime_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Filled by the Phase 2 identification stage.
    detected_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    format_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    storage_relpath: Mapped[str] = mapped_column(String(512))
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True
    )
    derivation: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), index=True)
    plugin_id: Mapped[str] = mapped_column(String(128))
    plugin_version: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    # queued | running | succeeded | failed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    # timeout | memory | plugin_error | crashed | interrupted | invalid_result
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    progress_message: Mapped[str] = mapped_column(String(500), default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    memory_limit_mb: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True)
    plugin_id: Mapped[str] = mapped_column(String(128))
    plugin_version: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    # Configuration of the producing job and the evidence hash it ran against: makes the finding reproducible.
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence.id", ondelete="CASCADE"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class AuditEntry(Base):
    """Append-only, hash-chained log. Deliberately has no foreign keys so history outlives purged cases."""

    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    ts: Mapped[str] = mapped_column(String(32))  # ISO-8601 UTC, stored verbatim for hashing
    actor: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    evidence_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details_json: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))


def init_db(engine) -> None:
    """Create tables and record the schema version. Idempotent."""
    from spectra import SCHEMA_VERSION

    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        row = s.get(SchemaMeta, "schema_version")
        if row is None:
            s.add(SchemaMeta(key="schema_version", value=str(SCHEMA_VERSION)))
            s.commit()
        elif int(row.value) > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema v{row.value} is newer than this SPECTRA build (v{SCHEMA_VERSION})."
            )
