"""core.integrity_verify — re-hash the stored original and compare with the hashes recorded at import."""

from __future__ import annotations

import hashlib
import os
import stat

from pydantic import BaseModel, ConfigDict, Field

from spectra.plugins.base import (
    AnalysisPlugin,
    Confidence,
    FindingDraft,
    FindingKind,
    PluginContext,
    PluginMeta,
    PluginResult,
)


class IntegrityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_size_kib: int = Field(default=1024, ge=4, le=65536, description="Read buffer size in KiB")


class IntegritySummary(BaseModel):
    match: bool
    bytes_hashed: int
    size_matches: bool
    read_only: bool
    algorithms: list[str]


class IntegrityVerifyPlugin(AnalysisPlugin):
    meta = PluginMeta(
        id="core.integrity_verify",
        name="Evidence integrity verification",
        version="1.0.0",
        description="Re-computes MD5, SHA-1 and SHA-256 of the stored original and compares them "
        "with the values recorded when the file was imported.",
        category="integrity",
        supported_formats=["*"],
        method="Streams the original file once, updating all three digests, and compares the results and the "
        "byte count with the import record. Also reports whether the stored file is still read-only.",
        limitations=[
            "Proves the stored bytes equal what was imported; it cannot prove the imported file equals the "
            "original source the user obtained it from.",
            "A matching hash says nothing about whether the file contains hidden data.",
            "An attacker who can rewrite both the file and the database record can defeat this check; "
            "compare against hashes recorded outside SPECTRA (reports, chain-of-custody notes).",
        ],
        deterministic=True,
    )
    ConfigModel = IntegrityConfig
    SummaryModel = IntegritySummary

    def run(self, ctx: PluginContext, config: IntegrityConfig) -> PluginResult:
        ev = ctx.evidence
        md5, sha1, sha256 = (hashlib.new(n, usedforsecurity=False) for n in ("md5", "sha1", "sha256"))
        total = 0
        chunk = config.chunk_size_kib * 1024
        with ctx.open_evidence() as fh:
            while block := fh.read(chunk):
                md5.update(block)
                sha1.update(block)
                sha256.update(block)
                total += len(block)
                ctx.report_progress(
                    min(total / max(ev.size_bytes, 1), 1.0), f"hashed {total} of {ev.size_bytes} bytes"
                )

        actual = {"md5": md5.hexdigest(), "sha1": sha1.hexdigest(), "sha256": sha256.hexdigest()}
        expected = {"md5": ev.md5, "sha1": ev.sha1, "sha256": ev.sha256}
        mismatched = sorted(k for k in actual if actual[k] != expected[k])
        size_ok = total == ev.size_bytes
        mode = os.stat(ev.path).st_mode
        read_only = not (mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        match = not mismatched and size_ok

        warnings = []
        if not read_only:
            warnings.append("The stored original is writable on disk; it should be mode 0444.")

        if match:
            finding = FindingDraft(
                kind=FindingKind.INTEGRITY,
                confidence=Confidence.VERIFIED,
                title="Evidence hashes match the import record",
                description=(
                    "MD5, SHA-1 and SHA-256 of the stored original equal the values recorded at import."
                ),
                data={"actual": actual, "size_bytes": total},
                limitations="Confirms storage integrity only; says nothing about hidden content.",
            )
        else:
            finding = FindingDraft(
                kind=FindingKind.INTEGRITY,
                confidence=Confidence.VERIFIED,
                title="INTEGRITY FAILURE: stored evidence differs from the import record",
                description="The stored original no longer matches what was imported. Treat all "
                "results derived from this evidence as unreliable until the cause is understood.",
                data={
                    "mismatched_algorithms": mismatched,
                    "size_matches": size_ok,
                    "expected": expected,
                    "actual": actual,
                    "expected_size": ev.size_bytes,
                    "actual_size": total,
                },
            )
        return PluginResult(
            summary={
                "match": match,
                "bytes_hashed": total,
                "size_matches": size_ok,
                "read_only": read_only,
                "algorithms": ["md5", "sha1", "sha256"],
            },
            findings=[finding],
            warnings=warnings,
        )
