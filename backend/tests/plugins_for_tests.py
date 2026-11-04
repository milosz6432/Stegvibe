"""Plugins used only by the test-suite. Module-level so spawned worker processes can import them."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from spectra.plugins.base import (
    AnalysisPlugin,
    Confidence,
    Dependency,
    FindingDraft,
    FindingKind,
    PluginContext,
    PluginMeta,
    PluginResult,
)


def _meta(plugin_id: str, **kw) -> PluginMeta:
    base = dict(
        name=plugin_id,
        version="1.0.0",
        description="test plugin",
        category="integrity",
        supported_formats=["*"],
        method="test",
        limitations=["test only"],
        deterministic=True,
    )
    base.update(kw)
    return PluginMeta(id=plugin_id, **base)


class NoopPlugin(AnalysisPlugin):
    meta = _meta("test.noop")

    def run(self, ctx: PluginContext, config) -> PluginResult:
        ctx.report_progress(0.5, "half way")
        return PluginResult(
            summary={"size": ctx.evidence.size_bytes, "sha256": ctx.evidence.sha256},
            findings=[
                FindingDraft(
                    kind=FindingKind.INFO,
                    confidence=Confidence.INFO,
                    title="noop finding",
                    location={"byte_offset": 0, "length": 1},
                    data={"k": "v"},
                )
            ],
            warnings=["a warning"],
        )


class SlowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seconds: float = 30.0


class SlowPlugin(AnalysisPlugin):
    meta = _meta("test.slow")
    ConfigModel = SlowConfig

    def run(self, ctx, config: SlowConfig) -> PluginResult:
        start = time.monotonic()
        while (elapsed := time.monotonic() - start) < config.seconds:
            ctx.report_progress(elapsed / config.seconds, f"{elapsed:.1f}s")
            time.sleep(0.05)
        return PluginResult(summary={"slept": config.seconds})


class SpawnConfig(BaseModel):
    pid_file: str


class SpawnChildPlugin(AnalysisPlugin):
    """Starts a helper process (like an ffmpeg call would) and then hangs."""

    meta = _meta("test.spawn_child")
    ConfigModel = SpawnConfig

    def run(self, ctx, config: SpawnConfig) -> PluginResult:
        child = subprocess.Popen(["sleep", "300"])
        Path(config.pid_file).write_text(str(child.pid))
        time.sleep(300)
        return PluginResult()


class ExitPlugin(AnalysisPlugin):
    meta = _meta("test.exit")

    def run(self, ctx, config) -> PluginResult:
        os._exit(3)


class KillSelfPlugin(AnalysisPlugin):
    meta = _meta("test.kill_self")

    def run(self, ctx, config) -> PluginResult:
        os.kill(os.getpid(), signal.SIGKILL)
        return PluginResult()


class RaisePlugin(AnalysisPlugin):
    meta = _meta("test.raise")

    def run(self, ctx, config) -> PluginResult:
        raise ValueError("boom from plugin")


class MemConfig(BaseModel):
    mb: int = 3072


class MemoryHogPlugin(AnalysisPlugin):
    meta = _meta("test.memory")
    ConfigModel = MemConfig

    def run(self, ctx, config: MemConfig) -> PluginResult:
        block = bytearray(config.mb * 1024 * 1024)
        return PluginResult(summary={"allocated": len(block)})


class HeuristicClaimsCertaintyPlugin(AnalysisPlugin):
    """A non-deterministic plugin trying to emit 'verified' — must be rejected by the supervisor."""

    meta = _meta("test.overclaim", deterministic=False)

    def run(self, ctx, config) -> PluginResult:
        return PluginResult(
            findings=[
                FindingDraft(
                    kind=FindingKind.STATISTICAL_ANOMALY,
                    confidence=Confidence.VERIFIED,
                    title="definitely stego",
                )
            ]
        )


class PngOnlyPlugin(AnalysisPlugin):
    meta = _meta("test.png_only", supported_formats=["png"])

    def run(self, ctx, config) -> PluginResult:
        return PluginResult()


class MissingDependencyPlugin(AnalysisPlugin):
    meta = _meta(
        "test.missing_dep", dependencies=[Dependency(name="spectra-no-such-binary-xyz", kind="binary")]
    )

    def run(self, ctx, config) -> PluginResult:
        return PluginResult()


class OptionalMissingDependencyPlugin(AnalysisPlugin):
    meta = _meta(
        "test.optional_dep",
        dependencies=[Dependency(name="spectra-no-such-binary-xyz", kind="binary", optional=True)],
    )

    def run(self, ctx, config) -> PluginResult:
        return PluginResult()


class ArtifactPlugin(AnalysisPlugin):
    meta = _meta("test.artifact")

    def run(self, ctx, config) -> PluginResult:
        ctx.output_path("report.txt").write_text("hello artifact")
        ctx.output_path("nested/data.bin").write_bytes(b"\x00\x01\x02")
        os.symlink("/etc/passwd", ctx.output_dir / "evil")  # must be ignored by the artifact scan
        return PluginResult(summary={"ok": True})


class BoundedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int = Field(default=1, ge=1, le=10)


class BoundedConfigPlugin(AnalysisPlugin):
    meta = _meta("test.bounded")
    ConfigModel = BoundedConfig

    def run(self, ctx, config: BoundedConfig) -> PluginResult:
        return PluginResult(summary={"n": config.n})


class WrongReturnPlugin(AnalysisPlugin):
    meta = _meta("test.wrong_return")

    def run(self, ctx, config):
        return {"not": "a PluginResult"}


ALL_TEST_PLUGINS = [
    NoopPlugin,
    SlowPlugin,
    SpawnChildPlugin,
    ExitPlugin,
    KillSelfPlugin,
    RaisePlugin,
    MemoryHogPlugin,
    HeuristicClaimsCertaintyPlugin,
    PngOnlyPlugin,
    MissingDependencyPlugin,
    OptionalMissingDependencyPlugin,
    ArtifactPlugin,
    BoundedConfigPlugin,
    WrongReturnPlugin,
]
