"""Example plugin: windowed Shannon entropy of the raw bytes. Walkthrough: docs/PLUGINS.md.

Deliberately small but complete. It shows every part of the contract:

* a validated ``PluginMeta`` (method + mandatory limitations),
* a ``ConfigModel`` (turned into a form by the UI) and a ``SummaryModel``,
* streaming reads through ``ctx.open_evidence()`` with progress reporting,
* findings with a location and an honest confidence level,
* a derived artifact written through ``ctx.output_path()``.

It is registered as a third-party plugin, never as a built-in::

    [project.entry-points."spectra.plugins"]
    byte_entropy = "examples.byte_entropy_plugin:ByteEntropyPlugin"
"""

from __future__ import annotations

import csv
import math
from collections import Counter

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

HIGH_ENTROPY_CAVEAT = (
    "High entropy is the normal state of compressed and encrypted data (PNG/JPEG/ZIP payloads, archives, "
    "media streams). It is not evidence of hidden content by itself; compare with what the format predicts."
)


def shannon_entropy(counts: Counter[int], total: int) -> float:
    """Shannon entropy in bits per byte (0.0 for constant data, 8.0 for a perfectly uniform byte stream)."""
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        p = c / total
        h -= p * math.log2(p)
    return h


class ByteEntropyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_bytes: int = Field(default=4096, ge=64, le=1_048_576, description="Window size in bytes")
    high_threshold_bits: float = Field(
        default=7.5,
        gt=0,
        le=8,
        description="Windows at or above this entropy (bits per byte) are reported as high-entropy",
    )
    max_findings: int = Field(default=20, ge=1, le=1000, description="Upper bound on reported regions")


class ByteEntropySummary(BaseModel):
    overall_entropy_bits: float
    windows: int
    min_window_entropy_bits: float | None
    max_window_entropy_bits: float | None
    high_entropy_windows: int
    high_entropy_regions: int


class ByteEntropyPlugin(AnalysisPlugin):
    meta = PluginMeta(
        id="example.byte_entropy",
        name="Windowed byte entropy",
        version="1.0.0",
        description="Measures Shannon entropy per fixed-size window and reports regions of high entropy.",
        category="structure",
        supported_formats=["*"],
        method="Reads the original once in fixed-size windows, counts byte values per window and computes "
        "H = -sum(p * log2(p)) in bits per byte. Adjacent windows at or above the threshold are merged "
        "into one region. A per-window CSV profile is written as an artifact.",
        limitations=[
            "Entropy cannot tell encrypted or compressed data from hidden payloads; many legitimate "
            "formats are high-entropy by design.",
            "Low-entropy payloads (plain text, simple encodings) are invisible to a high-entropy filter.",
            "Window size trades resolution for noise: windows below a few hundred bytes cannot reach "
            "8 bits per byte even for random data.",
            "A trailing partial window is counted in the overall figure but not analysed separately.",
        ],
        deterministic=False,  # the measurement is exact, the interpretation is a heuristic
    )
    ConfigModel = ByteEntropyConfig
    SummaryModel = ByteEntropySummary

    def run(self, ctx: PluginContext, config: ByteEntropyConfig) -> PluginResult:
        window = config.window_bytes
        size = ctx.evidence.size_bytes
        overall: Counter[int] = Counter()
        total = 0
        profile: list[tuple[int, int, float]] = []  # (offset, length, entropy)
        warnings: list[str] = []

        with ctx.open_evidence() as fh:
            offset = 0
            while block := fh.read(window):
                counts = Counter(block)
                overall.update(counts)
                total += len(block)
                if len(block) == window:
                    profile.append((offset, window, shannon_entropy(counts, window)))
                else:
                    warnings.append(
                        f"The last {len(block)} bytes are shorter than the window ({window}); they are "
                        "included in the overall entropy but not analysed as a window."
                    )
                offset += len(block)
                if len(profile) % 256 == 0:
                    ctx.report_progress(min(offset / max(size, 1), 1.0), f"{offset} of {size} bytes")

        if total == 0:
            warnings.append("The evidence file is empty; there is nothing to measure.")
        elif not profile:
            warnings.append("The file is smaller than one window; no per-window profile was produced.")

        # artifact: the full per-window profile, for plotting or diffing outside SPECTRA
        with ctx.output_path("entropy_profile.csv").open("w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["offset", "length", "entropy_bits"])
            for off, length, h in profile:
                writer.writerow([off, length, f"{h:.6f}"])

        # merge adjacent high-entropy windows into regions
        regions: list[tuple[int, int, list[float]]] = []  # (start, end, entropies)
        for off, length, h in profile:
            if h < config.high_threshold_bits:
                continue
            if regions and regions[-1][1] == off:
                regions[-1] = (regions[-1][0], off + length, [*regions[-1][2], h])
            else:
                regions.append((off, off + length, [h]))

        overall_h = shannon_entropy(overall, total)
        findings = [
            FindingDraft(
                kind=FindingKind.INFO,
                confidence=Confidence.INFO,
                title=f"Overall byte entropy: {overall_h:.4f} bits per byte",
                description="Entropy of the whole file: 0 means constant data, 8 means uniform bytes.",
                data={"overall_entropy_bits": round(overall_h, 6), "bytes": total},
            )
        ]
        for start, end, entropies in regions[: config.max_findings]:
            mean_h = sum(entropies) / len(entropies)
            findings.append(
                FindingDraft(
                    kind=FindingKind.STATISTICAL_ANOMALY,
                    # a heuristic can be suggestive, never conclusive: LOW, and VERIFIED is forbidden anyway
                    confidence=Confidence.LOW,
                    title=f"High-entropy region at bytes {start}-{end - 1}",
                    description=f"{len(entropies)} consecutive window(s) of {window} bytes have entropy of "
                    f"{config.high_threshold_bits} bits per byte or more (mean {mean_h:.4f}).",
                    location={"byte_offset": start, "length": end - start},
                    data={"mean_entropy_bits": round(mean_h, 6), "windows": len(entropies)},
                    limitations=HIGH_ENTROPY_CAVEAT,
                )
            )
        if len(regions) > config.max_findings:
            warnings.append(
                f"{len(regions)} regions found; only the first {config.max_findings} are reported as "
                "findings. The CSV artifact lists every window."
            )

        entropies_all = [h for _, _, h in profile]
        summary = ByteEntropySummary(
            overall_entropy_bits=round(overall_h, 6),
            windows=len(profile),
            min_window_entropy_bits=round(min(entropies_all), 6) if entropies_all else None,
            max_window_entropy_bits=round(max(entropies_all), 6) if entropies_all else None,
            high_entropy_windows=sum(len(r[2]) for r in regions),
            high_entropy_regions=len(regions),
        )
        return PluginResult(summary=summary.model_dump(), findings=findings, warnings=warnings)
