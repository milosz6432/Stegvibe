# Writing SPECTRA plugins

Every analysis in SPECTRA is a plugin, including the built-in integrity check. A plugin is a small
Python class that reads evidence **read-only** and returns **findings**. The platform handles
everything around it: isolation, time and memory limits, progress, persistence, audit logging,
reproducibility metadata and the user interface for its settings.

The complete, tested example used throughout this guide is
[`backend/examples/byte_entropy_plugin.py`](../backend/examples/byte_entropy_plugin.py), exercised by
[`backend/tests/test_example_plugin.py`](../backend/tests/test_example_plugin.py) through the real job
system. If this guide and the code ever disagree, the code and its tests win; please fix the guide.

## 1. Trust model (read this first)

* A job runs in a **separate worker process** with its own process group, a memory cap
  (`RLIMIT_AS`), a CPU cap, no core dumps, a wall-clock timeout and a cancel button. A plugin that
  crashes, hangs, leaks memory or is fed a hostile file takes down only its own job.
* This is **fault isolation, not a security sandbox.** The worker runs as the same OS user as
  SPECTRA, can read the filesystem and can open network connections. **Plugins are trusted code**:
  install only plugins you have reviewed. SPECTRA never executes evidence, but a plugin can do
  whatever Python can do.
* On Windows the memory and CPU rlimits are not available (the process-level timeout and cancel
  still are). `GET /api/system/info` reports `memory_and_cpu_rlimits` so you can see whether the
  caps are enforced on your platform; each job records the `memory_limit_mb` it was given.
* Evidence originals are `chmod 0444` and stored apart from derived output, but a malicious plugin
  running as the same user could still change permissions. The integrity-verification plugin and the
  hash-chained audit log exist to make that *detectable*, not impossible.

## 2. The contract

```python
from spectra.plugins.base import AnalysisPlugin, PluginMeta, PluginContext, PluginResult

class MyPlugin(AnalysisPlugin):
    meta = PluginMeta(...)            # required, validated at import time
    ConfigModel = MyConfig            # optional pydantic model (default: no settings)
    SummaryModel = MySummary          # optional pydantic model validating result.summary

    def run(self, ctx: PluginContext, config: MyConfig) -> PluginResult:
        ...
```

`run` must behave like a **pure function of (evidence bytes, config)**. The same input must give the
same findings, because every finding stores the plugin id and version, the evidence SHA-256 and the
exact config, so that a colleague can reproduce it.

### 2.1 `PluginMeta`

| field | rules |
|---|---|
| `id` | `vendor.technique_name`: lowercase, dotted, e.g. `acme.lsb_chi_square`. Unique. |
| `name`, `description` | Shown in the UI. |
| `version` | Semantic version. **Bump it when results could change.** Stored with each finding. |
| `category` | One of `integrity, structure, metadata, image, audio, video, extraction, ctf`. |
| `supported_formats` | Non-empty. Canonical ids (`png`, `wav`, ...), category wildcards (`image:*`, `audio:*`, `video:*`) or `["*"]`. Unknown tokens are rejected. |
| `dependencies` | List of `Dependency(name, kind="python"|"binary", optional, purpose)`. A missing *required* dependency makes the plugin show as unavailable with the reason; it is never silently skipped. |
| `method` | Plain-language description of how the analysis works. Shown to the user. |
| `limitations` | **At least one entry is mandatory.** Every technique has failure modes (false positives, blind spots); say what they are. Shown in the "Method & limitations" panel on the evidence page and on the plugin list in Settings. |
| `deterministic` | `True` only for exact computations (hashes, CRC checks, parsing). See 2.3. |
| `cpu_heavy` | Hint for scheduling and UI. |

> **Phase 1 limitation: format identification does not exist yet.** Evidence has no `detected_format`
> until Phase 2 lands, so only plugins declaring `supported_formats=["*"]` can be run today. A plugin
> that declares specific formats (`["png"]`, `["image:*"]`) is registered and listed, but creating a job
> for any evidence is refused with `format_not_identified`. Develop format-specific plugins against
> the job API in tests (`tests/plugins_for_tests.py` has `test.png_only`) and expect them to become
> runnable when Phase 2 ships.

### 2.2 Context

`PluginContext` gives you exactly four things:

* `ctx.evidence`: read-only `EvidenceRef` (`id`, `filename` (display only), `size_bytes`, `md5`,
  `sha1`, `sha256`, `detected_format`, `path`).
* `ctx.open_evidence()`: opens the original **for reading**. Stream it; do not assume it fits in memory.
* `ctx.output_path(name)`: a path inside this job's private output directory (parents created).
  Names that would escape the directory are refused. Anything you write there becomes an
  **artifact**: listed in the job result with size and SHA-256, downloadable, and stored apart
  from the originals.
* `ctx.report_progress(fraction, message)`: drives the progress bar. Optional but recommended for
  anything that can take more than a second.

Never write next to the original, never modify it, never `chmod` it, and never use
`ctx.evidence.filename` as a filesystem path (it is untrusted text from the evidence owner).

### 2.3 Findings and honesty

A finding has a `kind`:
`integrity`, `structural_anomaly`, `statistical_anomaly`, `metadata_observation`,
`extracted_payload`, `flag_candidate`, `info`,
and a `confidence`: `info < low < medium < high < verified`.

The confidence describes **how well the observation is supported, not whether steganography is
present.** Rules the platform enforces or expects:

* `verified` means a **deterministic check passed** (hash equality, CRC match, a successfully parsed
  and re-validated structure). A plugin with `deterministic=False` that returns a `verified` finding
  has its whole job **failed with `invalid_result`**. This is deliberate: results from statistical
  tests or heuristics must never read as proof.
* Statistical and heuristic findings should be `low` or `medium`, and should carry a per-finding
  `limitations` string (shown on the finding card) explaining what else would produce the same
  signal. The example does this for entropy.
* Prefer a precise `location` (`{"byte_offset": 4096, "length": 4096}`, or channel/bit/pixel for
  images) so the UI can jump to the hex viewer.
* Put machine-readable detail in `data`, human explanation in `description`.
* Report what you could **not** do in `PluginResult.warnings` (truncated results, skipped windows,
  empty input). Silence reads as "checked and fine".

### 2.4 Config and summary

`ConfigModel` is a pydantic model. SPECTRA exposes its JSON Schema at `GET /api/plugins` and the web
UI renders the run dialog from it (numbers with bounds, booleans, enums, text), so bounds and
descriptions you declare are what the user sees. Use `ConfigDict(extra="forbid")` so typos are
errors rather than silently ignored, and give every numeric field `ge`/`le` bounds. The config is
validated **twice**: when the job is created (HTTP 422, no job is stored) and again inside the
worker.

`SummaryModel` (optional) validates and normalises `result.summary`, and its schema is exposed so
clients can rely on its shape.

## 3. A minimal plugin

```python
from pydantic import BaseModel, ConfigDict, Field
from spectra.plugins.base import (
    AnalysisPlugin, Confidence, FindingDraft, FindingKind,
    PluginContext, PluginMeta, PluginResult,
)

class NullByteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_run: int = Field(default=64, ge=2, le=1_000_000, description="Shortest run of 0x00 to report")

class NullRuns(AnalysisPlugin):
    meta = PluginMeta(
        id="acme.null_runs", name="Long runs of NUL bytes", version="1.0.0",
        description="Reports long zero-filled regions.",
        category="structure", supported_formats=["*"],
        method="Scans the file once and records every run of 0x00 bytes of at least min_run bytes.",
        limitations=["Padding and sparse data legitimately contain zero runs; a run alone proves nothing."],
        deterministic=False,
    )
    ConfigModel = NullByteConfig

    def run(self, ctx: PluginContext, config: NullByteConfig) -> PluginResult:
        findings, run_start, pos = [], None, 0
        with ctx.open_evidence() as fh:
            while block := fh.read(1 << 20):
                for b in block:           # (fine for a sketch; use bytes.find / numpy for real work)
                    if b == 0 and run_start is None:
                        run_start = pos
                    elif b != 0 and run_start is not None:
                        if pos - run_start >= config.min_run:
                            findings.append(self._finding(run_start, pos - run_start))
                        run_start = None
                    pos += 1
        if run_start is not None and pos - run_start >= config.min_run:
            findings.append(self._finding(run_start, pos - run_start))
        return PluginResult(summary={"runs": len(findings)}, findings=findings)

    @staticmethod
    def _finding(start: int, length: int) -> FindingDraft:
        return FindingDraft(
            kind=FindingKind.STRUCTURAL_ANOMALY, confidence=Confidence.LOW,
            title=f"{length} NUL bytes at offset {start}",
            location={"byte_offset": start, "length": length},
        )
```

## 4. Registering a plugin

**Installed package (the normal way).** Declare an entry point in the plugin package's
`pyproject.toml`, install it into the same environment as SPECTRA, restart SPECTRA:

```toml
[project.entry-points."spectra.plugins"]
null_runs = "acme_plugins.null_runs:NullRuns"
```

A plugin that fails to import is **not fatal**: SPECTRA starts, the other plugins work, and the
failure is listed under load errors on the settings page and in the log.

**Requirements enforced at registration:** the class derives `AnalysisPlugin`, defines a valid
`PluginMeta`, has a unique id, and is defined at **module level**. (The worker process re-imports it
by `module:ClassName`; nested or dynamically-created classes cannot be re-imported and are rejected.)

**Built-ins** are added to `BUILTIN_PLUGINS` in `spectra/plugins/builtin/__init__.py`. That list is
explicit on purpose: no directory scanning, no dynamic code loading.

## 5. What happens when a job runs

1. `POST /api/jobs {evidence_id, plugin_id, config, timeout_seconds?, memory_limit_mb?}` validates
   the plugin is available, the evidence format is supported, the case is not archived and the config
   is valid, then stores a `queued` job and audit-logs it.
2. A supervisor thread starts a **spawned** worker process (never `fork`; no inherited state) in its
   own process group, applies the rlimits, imports your class by entry point and calls `run`.
3. Progress, result and errors travel over a pipe. On cancel or timeout the whole **process group**
   gets `SIGTERM`, then `SIGKILL`, so helpers your plugin spawned die too.
4. On success the findings are validated, stored with full provenance (plugin id + version, evidence
   SHA-256, config), artifacts are scanned (symlinks ignored), and everything is audit-logged. On any
   other outcome partial derived output is deleted.

| terminal `error_code` | meaning |
|---|---|
| `plugin_error` | `run` raised. The message is on the job; the traceback tail is kept under `result.diagnostics`. |
| `invalid_result` | Return value or findings were invalid, e.g. `verified` from a non-deterministic plugin. |
| `memory` | `MemoryError` under the memory cap. |
| `timeout` | Wall-clock limit exceeded. |
| `crashed` | The worker died (signal or exit code is recorded). |
| `cancelled` | The user cancelled. |
| `interrupted` | SPECTRA restarted while the job was queued or running. |
| `supervisor_error` | Bug in SPECTRA itself; please report it. |

Limits come from `SPECTRA_DEFAULT_JOB_TIMEOUT_SECONDS`, `SPECTRA_MAX_JOB_TIMEOUT_SECONDS`,
`SPECTRA_DEFAULT_JOB_MEMORY_LIMIT_MB` and `SPECTRA_MAX_ARTIFACTS_PER_JOB`.

## 6. Testing your plugin

Test through the production path, not by calling `run` in-process. That is the only way to catch
import problems, pickling mistakes and limit behaviour. `backend/tests/test_example_plugin.py`
is the template:

```python
@pytest.fixture
def my_client(container, client):
    container.registry.register(NullRuns, source="example")
    return client

def test_finds_the_run(my_client, case):
    ev = upload(my_client, case["id"], b"A" * 10 + b"\x00" * 100 + b"B" * 10)   # tests/conftest.py
    job = wait_for_job(my_client, run_job(my_client, ev.json()["id"], "acme.null_runs")["id"])
    assert job["status"] == "succeeded"
    ...
```

Also test: known-answer inputs computed independently of your code (the example checks a 75/25 byte
split against `0.8112781244591328`), the empty and tiny-file cases, an invalid config (expect 422),
and that anything uncertain is not labelled `high` or `verified`. After writing tests, break the code
on purpose (flip a comparison, change a constant) and confirm a test fails; a test that cannot fail
proves nothing.

## 7. Checklist before you ship a plugin

- [ ] `limitations` says what the technique cannot detect and what causes false positives.
- [ ] `version` bumped if output could differ from the last release.
- [ ] Config fields have bounds and descriptions; `extra="forbid"`.
- [ ] Evidence is streamed; memory use is bounded for a multi-GB file.
- [ ] Only `ctx.output_path()` is written to; the original is only read.
- [ ] Uncertain results are `low`/`medium` with a `limitations` note; `verified` only for exact checks.
- [ ] Truncation, skipped data and empty input appear in `warnings`.
- [ ] Missing optional dependencies degrade gracefully and say so; required ones are declared.
- [ ] Tests run through the job system and include a mutation check.
