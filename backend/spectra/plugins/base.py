"""The plugin contract. See docs/PLUGINS.md for the developer guide.

A plugin is a class deriving :class:`AnalysisPlugin` with a ``meta`` describing it. ``run`` executes inside a
sandboxed worker subprocess; it must be a pure function of (evidence bytes, config) so that every finding is
reproducible.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any, BinaryIO, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from spectra.core.security import resolve_within
from spectra.formats import is_valid_format_token

PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.+-]+)?$")


class FindingKind(StrEnum):
    INTEGRITY = "integrity"
    STRUCTURAL_ANOMALY = "structural_anomaly"
    STATISTICAL_ANOMALY = "statistical_anomaly"
    METADATA_OBSERVATION = "metadata_observation"
    EXTRACTED_PAYLOAD = "extracted_payload"
    FLAG_CANDIDATE = "flag_candidate"
    INFO = "info"


class Confidence(StrEnum):
    """How strongly the *observation* is supported. ``VERIFIED`` = a deterministic check passed.

    It never means "steganography is present". Plugins with ``meta.deterministic == False`` (heuristics,
    statistical tests) are forbidden from emitting ``VERIFIED``; the job supervisor enforces this.
    """

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


class Dependency(BaseModel):
    name: str
    kind: Literal["python", "binary"]
    optional: bool = False
    purpose: str = ""


class PluginMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    version: str
    description: str
    category: Literal["integrity", "structure", "metadata", "image", "audio", "video", "extraction", "ctf"]
    supported_formats: list[str]
    dependencies: list[Dependency] = []
    method: str  # how the analysis works, in plain language
    limitations: list[str] = Field(min_length=1)  # mandatory: every technique has failure modes
    deterministic: bool = False  # True only for exact computations (hashes, CRC checks, parsing)
    cpu_heavy: bool = False

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not PLUGIN_ID_RE.match(v):
            raise ValueError("plugin id must look like 'vendor.technique_name' (lowercase, dotted)")
        return v

    @field_validator("version")
    @classmethod
    def _version(cls, v: str) -> str:
        if not SEMVER_RE.match(v):
            raise ValueError("version must be semantic (e.g. 1.2.0)")
        return v

    @field_validator("supported_formats")
    @classmethod
    def _formats(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("supported_formats must not be empty (use ['*'] for any format)")
        bad = [t for t in v if not is_valid_format_token(t)]
        if bad:
            raise ValueError(f"unknown format token(s): {bad}")
        return v


class FindingDraft(BaseModel):
    kind: FindingKind
    confidence: Confidence
    title: str = Field(max_length=200)
    description: str = ""
    # Where in the evidence, e.g. {"byte_offset": .., "length": ..} or
    # {"channel": "R", "bit": 0, "x": .., "y": ..}
    location: dict[str, Any] | None = None
    data: dict[str, Any] = {}
    limitations: str | None = None


class PluginResult(BaseModel):
    summary: dict[str, Any] = {}
    findings: list[FindingDraft] = []
    warnings: list[str] = []


class EvidenceRef(BaseModel):
    """What a worker is told about the evidence it analyses (read-only view)."""

    id: str
    case_id: str
    filename: str
    size_bytes: int
    md5: str
    sha1: str
    sha256: str
    detected_format: str | None = None
    path: str


class EmptyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PluginContext:
    """Handed to ``run``. Exposes read-only evidence access, an output sandbox and progress reporting."""

    def __init__(
        self,
        evidence: EvidenceRef,
        output_dir: Path,
        report: Callable[[float, str], None] | None = None,
    ):
        self.evidence = evidence
        self.output_dir = output_dir
        self._report = report

    def open_evidence(self) -> BinaryIO:
        """Open the original for reading. The original must never be opened for writing."""
        return open(self.evidence.path, "rb")

    def output_path(self, name: str) -> Path:
        """A path inside this job's derived-output directory (parents are created)."""
        p = resolve_within(self.output_dir, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def report_progress(self, fraction: float, message: str = "") -> None:
        if self._report:
            self._report(max(0.0, min(1.0, float(fraction))), message)


class AnalysisPlugin(ABC):
    meta: ClassVar[PluginMeta]
    ConfigModel: ClassVar[type[BaseModel]] = EmptyConfig
    SummaryModel: ClassVar[type[BaseModel] | None] = None

    @abstractmethod
    def run(self, ctx: PluginContext, config: Any) -> PluginResult:  # pragma: no cover - interface
        ...

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return cls.ConfigModel.model_json_schema()

    @classmethod
    def summary_schema(cls) -> dict[str, Any] | None:
        return cls.SummaryModel.model_json_schema() if cls.SummaryModel else None
