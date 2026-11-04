# SPECTRA — Architecture & Design

Status: **Phase 1 is implemented and tested.** Phases 2–8 are design only and are marked as such.
Sections 3–10 and 13 describe the code as it exists; §11 (limitations of the problem domain) and §12 (roadmap) look forward.
Section 14 lists known gaps in what is built today.

## 1. Principles

These come straight from the product brief and drive every decision below.

1. **Evidence is immutable.** Originals are stored once, read-only, and never opened for writing. Every derived artifact lives in a separate tree.
2. **Nothing is fabricated.** No simulated results. A heuristic reports a *score and its limitations*, never certainty. "No findings" never means "clean".
3. **Everything is reproducible.** A finding carries the plugin id/version, the exact configuration, and the evidence hash it was produced from.
4. **Everything is audited.** All state-changing actions and every download of evidence or derived artifacts are written to a tamper-evident audit log. (Paging through the hex viewer is not logged; see §14.)
5. **Untrusted input.** Files are parsed, never executed. Parsers run in resource-limited subprocesses. Decompression must be bounded; that limit is a requirement on future archive-handling plugins and is not implemented yet (§9, §14).
6. **Offline by default.** The application contains no network client code. A test enforces this.
7. **Honest dependency handling.** Optional tools (ExifTool, Binwalk, YARA, PyAV, …) are wrapped in adapters; absence is reported, never hidden.

## 2. System overview

```
 Browser (React SPA)  ── HTTP/JSON ──►  FastAPI process (API, DB, audit, job supervisor)
                                              │
                         ┌────────────────────┼─────────────────────────┐
                         ▼                    ▼                         ▼
                   SQLite (WAL)       Evidence store (files)     Worker subprocesses
                   metadata, audit,   originals/  (read-only)    (spawned per job: rlimits,
                   jobs, findings     derived/<job>/             timeout, process-group kill)
                                      tmp/                       run analysis plugins
```

* The API process never runs analysis code. It validates requests, writes metadata, supervises jobs and serves files.
* Workers cannot write to the database. They return a typed `PluginResult`; the supervisor persists it and writes audit entries. This keeps the audit chain single-writer and keeps untrusted parsers away from the DB handle.
* The SPA is served by FastAPI in production (`frontend/dist`) and by Vite in development with an `/api` proxy.

## 3. Directory structure

```
spectra/
├── README.md
├── Makefile
├── docs/
│   ├── ARCHITECTURE.md              this file
│   └── PLUGINS.md                   plugin development guide (its code sample is run by a test)
├── backend/
│   ├── pyproject.toml
│   ├── spectra/
│   │   ├── __main__.py              `python -m spectra` (uvicorn)
│   │   ├── main.py                  app factory, error envelope, middleware order, SPA fallback
│   │   ├── container.py             composition root: builds/closes every service
│   │   ├── config.py                Settings (env prefix SPECTRA_)
│   │   ├── formats.py               canonical format ids + categories
│   │   ├── db/                      base.py (engine, WAL, FK on, UTCDateTime), models.py
│   │   ├── schemas/                 Pydantic API models
│   │   ├── api/                     HTTP only (the only package besides main.py that imports FastAPI)
│   │   │   ├── system.py            health, system info, dependencies, stats
│   │   │   ├── cases.py  evidence.py
│   │   │   ├── jobs.py              jobs, findings, artifact download
│   │   │   ├── misc.py              notes, audit, plugins
│   │   │   ├── deps.py              request-scoped dependencies
│   │   │   └── middleware.py        Host/Origin checks, security headers
│   │   ├── services/                cases.py, evidence.py, notes.py (business rules + audit calls)
│   │   ├── core/
│   │   │   ├── audit.py             hash-chained audit log
│   │   │   ├── evidence_store.py    streaming ingest, layout, hex reads
│   │   │   ├── deps.py              dependency adapters / availability checks
│   │   │   ├── security.py          filename sanitising, path containment (pure, no web imports)
│   │   │   └── errors.py            domain exceptions
│   │   ├── plugins/
│   │   │   ├── base.py              AnalysisPlugin, PluginMeta, PluginResult, context
│   │   │   ├── registry.py          discovery, validation, availability
│   │   │   └── builtin/integrity.py core.integrity_verify (reference plugin)
│   │   └── jobs/
│   │       ├── manager.py           queue, supervisors, cancel/timeout/recovery
│   │       └── worker.py            child entrypoint, rlimits, pipe protocol
│   ├── examples/byte_entropy_plugin.py   documented third-party plugin example (tested, not shipped)
│   └── tests/
├── frontend/
│   ├── package.json  vite.config.ts  tsconfig*.json  components.json
│   └── src/
│       ├── main.tsx  App.tsx
│       ├── api/                     typed client, React Query hooks
│       ├── store/                   Zustand (active case, UI prefs)
│       ├── lib/                     helpers, format metadata
│       ├── components/ui/           shadcn-style primitives over Radix
│       ├── components/              layout shell, hex viewer, schema-driven form, finding card, ...
│       ├── pages/                   Dashboard, Investigations, CaseWorkspace, EvidenceDetail,
│       │                            Findings, Settings, lab placeholders
│       └── __tests__/
└── data/  (runtime, outside the repo by default; see §6)
```

Later phases add `backend/spectra/analyzers/{image,audio,video,metadata}/` (each analyzer is a plugin) and
`backend/spectra/reports/`.

## 4. Backend layering

`api/` (HTTP only) → `services/` (business rules, audit calls) → `core/`, `jobs/`, `plugins/` (domain logic) → `db/` (persistence).
Routers only map requests to service calls and results to responses. **Only `api/` and `main.py` may import
FastAPI/Starlette; a test enforces it.** A second test enforces that the plugin SDK and the worker entrypoint
load no web framework or ORM, so analysis subprocesses start light and keep a small attack surface.
The composition root is `container.build_container()`, which builds the settings-dependent services (session
factory, audit log, evidence store, dependency checker, plugin registry, job manager); `main.create_app()` puts
the container on `app.state`.

## 5. Database schema (SQLite, SQLAlchemy 2.x)

SQLite runs in WAL mode with `foreign_keys=ON` and a busy timeout. A single-writer database is appropriate for a local workbench.
There is no migration framework yet: tables are created with `create_all` and a `schema_meta` row stores the schema version.
Alembic will be introduced with the first schema change after Phase 1 (baseline = version 1).

IDs are UUID4 strings. Timestamps are timezone-aware UTC.

| Table | Status | Purpose |
|---|---|---|
| `schema_meta` | Phase 1 | key/value (schema version) |
| `cases` | Phase 1 | `id, name, description, archived, created_at, updated_at` |
| `evidence` | Phase 1 | `id, case_id→cases, kind(original|derived), original_filename, declared_extension, size_bytes, md5, sha1, sha256, mime_hint, detected_format?, format_confidence?, storage_relpath, parent_id→evidence?, derivation(JSON)?, imported_at` |
| `jobs` | Phase 1 | `id, case_id, evidence_id, plugin_id, plugin_version, config(JSON), status(queued|running|succeeded|failed|cancelled), error_code?, error_message?, progress, progress_message, timeout_seconds, memory_limit_mb, result(JSON), created_at, started_at?, finished_at?` |
| `findings` | Phase 1 | `id, case_id, evidence_id, job_id, plugin_id, plugin_version, kind, confidence, title, description, location(JSON)?, data(JSON), config(JSON), limitations?, evidence_sha256, created_at` |
| `notes` | Phase 1 | `id, case_id, evidence_id?, body, created_at, updated_at` |
| `audit_log` | Phase 1 | `seq(PK), ts, actor, action, case_id?, evidence_id?, job_id?, details_json, prev_hash, entry_hash` — no FKs, so history survives a case purge |
| `payloads` | Phase 7 | extracted bytes: `id, evidence_id, finding_id?, storage_relpath, size, sha256, method, config, location, confidence, derived_evidence_id?` |
| `bookmarks` | Phase 7 | `id, case_id, evidence_id, kind(timestamp|frame|pixel|bitplane|offset), locator(JSON), label, created_at` |
| `reports` | Phase 8 | generated report records |

### Finding vocabulary

`kind`: `integrity`, `structural_anomaly`, `statistical_anomaly`, `metadata_observation`, `extracted_payload`, `flag_candidate`, `info`.
Structural anomalies and statistical anomalies are kept separate from extracted payloads, as the brief requires.

`confidence`: `info` < `low` < `medium` < `high` < `verified`.
`verified` means *a deterministic check passed* (hash compare, CRC valid, archive parsed). It describes the observation, never "steganography is present".
Heuristic detectors must not emit `verified`.

### Audit chain

`entry_hash = SHA-256(prev_hash ‖ seq ‖ ts ‖ actor ‖ action ‖ case_id ‖ evidence_id ‖ job_id ‖ details_json)`, with the canonical JSON string stored verbatim so verification does not depend on JSON round-tripping.
`GET /api/audit/verify` recomputes the chain. This is **tamper-evident, not tamper-proof**: anyone with write access to the database file can recompute the whole chain, and tail truncation is invisible without an external anchor.
Reports (Phase 8) will print the chain head hash so it can be recorded elsewhere.

## 6. Evidence store

Default data directory: `$XDG_DATA_HOME/spectra` (Linux), `~/Library/Application Support/spectra` (macOS), `%APPDATA%\spectra` (Windows); override with `SPECTRA_DATA_DIR`.

```
<data>/spectra.db
<data>/tmp/                                   upload staging (same filesystem ⇒ atomic rename)
<data>/cases/<case_id>/originals/<evidence_id>   original bytes, mode 0444, name = id (never the user filename)
<data>/cases/<case_id>/derived/<job_id>/...      anything a plugin produces
```

Ingest is streaming: chunks are read from the request, written to `tmp/`, and hashed (MD5, SHA-1, SHA-256) in the same pass, with a hard size limit and a free-disk check.
On success the file is atomically renamed into place and made read-only. On any failure the temp file is removed.
User-supplied filenames are sanitised for display only and are never used as path components.
Evidence is always served as `application/octet-stream` with `Content-Disposition: attachment` and `nosniff`, so an HTML or SVG sample can never execute in the SPA origin.

## 7. Plugin architecture

Every analysis technique is a plugin: a class deriving `AnalysisPlugin` with a `meta: PluginMeta`.

```python
class PluginMeta(BaseModel):
    id: str                       # "core.integrity_verify"  (lowercase dotted)
    name: str
    version: str                  # semver
    description: str
    supported_formats: list[str]  # canonical format ids, "image:*" / "audio:*" / "video:*", or "*"
    dependencies: list[Dependency]  # {name, kind: python|binary, optional, purpose}
    method: str                   # human-readable description of the analysis method
    limitations: list[str]        # mandatory; shown in UI and reports
    category: str                 # integrity|structure|metadata|image|audio|video|extraction|ctf
    deterministic: bool = False   # True only for exact computations; only these may emit confidence=verified
    cpu_heavy: bool = False
```

* **Configuration schema** is the JSON Schema of the plugin's `ConfigModel` (Pydantic). The UI renders it and the API validates against it.
* **Output schema**: all plugins return `PluginResult { summary: dict, findings: [FindingDraft], warnings: [str] }`; `summary` is validated by an optional per-plugin `SummaryModel`, whose JSON Schema is published.
* **Execution**: `run(ctx, config) -> PluginResult` is invoked only inside a worker subprocess. `ctx` exposes the evidence reference, a read-only file opener, the job's derived-output directory, and `report_progress()`.
* **Discovery**: built-ins are listed explicitly; third parties register the `spectra.plugins` entry-point group. Arbitrary-directory code loading is intentionally not supported.
* **Availability**: each plugin's dependencies are checked through the same adapters as the Settings page. A plugin with a missing required dependency is listed as unavailable, with the reason, and cannot be run.

See `docs/PLUGINS.md` for the developer guide and `backend/examples/byte_entropy_plugin.py` for a complete example.
The job manager enforces the `verified` rule: a non-deterministic plugin that returns a `verified` finding fails with `invalid_result`.

**Phase 1 gap:** because format identification arrives in Phase 2, evidence has no `detected_format` yet, so only plugins that declare `supported_formats=["*"]` can be run (see §14).

## 8. Job system (implemented in Phase 1)

* `POST /api/jobs` validates evidence, plugin availability, format applicability and config, creates a `queued` row and an audit entry.
* A bounded thread pool (`max_concurrent_jobs`) runs one *supervisor* per job. The supervisor starts a **spawned** subprocess (clean interpreter, no inherited DB connections or threads).
* The worker puts itself in its own process group (POSIX), applies `RLIMIT_AS` (memory) and `RLIMIT_CPU`, validates the config, runs the plugin, and streams `progress` / `result` / `error` messages over a pipe.
* The supervisor enforces a wall-clock timeout, handles cancellation, and on timeout/cancel signals the **whole process group**, so helper binaries launched by a plugin (e.g. FFmpeg) die with it.
* Exit without a result is reported as a crash with the exit code or signal. Out-of-memory is reported as such when detectable.
* On startup, jobs left `queued`/`running` by a previous run are marked `failed` (`error_code=interrupted`) and audited.
* Progress is polled by the UI (React Query). Server-sent events are a possible later optimisation, not needed yet.

## 9. Security model

| Threat | Mitigation (Phase 1) |
|---|---|
| Malicious media triggers parser bug | Parsing only in resource-limited subprocesses; documented residual risk — run in a VM/container for hostile samples |
| Execution of uploaded content | Never executed; stored without extension; served as octet-stream attachment |
| Path traversal via filename | Filename never used in paths; all served paths resolved and checked for containment |
| Decompression / archive bombs | **Not yet mitigated in code**: no Phase 1 plugin decompresses anything. Output size/count caps and expansion-ratio limits will be a requirement for every archive-handling plugin when they arrive (Phase 3/7). Today only the per-job memory/CPU/time limits and `max_artifacts_per_job` apply. |
| DNS rebinding / drive-by access to local API | Host header allow-list; default bind 127.0.0.1 |
| Cross-site request forgery against localhost | `Origin` allow-list on state-changing requests |
| Disk exhaustion | Upload size cap, free-space reserve check, temp cleanup |
| Runaway analysis | Per-job timeout, memory/CPU rlimits, cancellation, bounded concurrency |
| Evidence tampering | Read-only originals, hash recorded at ingest, re-verifiable by `core.integrity_verify`, hash-chained audit log |
| Data exfiltration | No network client code (test-enforced) |

Not covered: multi-user authentication. SPECTRA is a single-user local workbench; if it is exposed beyond loopback, put it behind an authenticating reverse proxy.

## 10. Dependencies

Core (required): Python ≥ 3.12, FastAPI, Uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy 2, python-multipart, python-magic (+ system `libmagic`).

Optional extras, grouped by the phase that needs them (all reported by `/api/system/dependencies`):

| Extra | Packages / binaries | Needed from |
|---|---|---|
| `image` | Pillow, NumPy, SciPy, OpenCV (headless), scikit-image, pillow-heif (HEIC) | Phase 3 |
| `audio` | librosa, soundfile, Mutagen, NumPy, SciPy; FFmpeg | Phase 4 |
| `video` | FFmpeg/FFprobe, OpenCV, PyAV | Phase 5 |
| `forensics` | Construct, ExifTool (binary), Binwalk (binary), yara-python | Phases 2, 3, 6 |
| `dev` | pytest, httpx, ruff | now |

Frontend: React 19, TypeScript 7 (strict, `noUncheckedIndexedAccess`), Vite 8, Tailwind CSS 4, hand-written shadcn/ui-style components over Radix primitives (class-variance-authority, tailwind-merge), Zustand, TanStack Query, React Router 7, lucide-react; tests with Vitest + Testing Library.
The UI is dark-only in Phase 1. No web fonts or CDN assets are used (system font stacks; the FastAPI Swagger UI is disabled because it loads from a CDN), so the UI works fully offline.

## 11. Known technical limitations (design-level)

These are properties of the problem, not of the implementation. The UI and reports surface them next to the relevant results.

1. **Lossy codecs.** Pixel-LSB extraction is meaningful for lossless images (PNG, BMP, lossless WebP, TIFF, GIF indices). For JPEG it only applies to the *decoded* pixels, which are not where JPEG steganography (F5, OutGuess, steghide, J-UNIWARD) hides data — DCT-coefficient analysis would be needed. MP3/AAC/OGG/Opus/lossy video cannot give bit-exact PCM/pixel LSB recovery; this will not be promised.
2. **Statistical steganalysis is probabilistic.** Chi-square, RS and sample-pair analysis work best against sequential full-capacity LSB replacement. They are weak against short payloads, adaptive/content-aware embedding (HUGO, WOW, S-UNIWARD), and produce false positives on noisy or synthetic images.
3. **Keyed tools.** Output of steghide, OpenStego, OutGuess, DeepSound etc. needs the correct passphrase. SPECTRA will detect indicators where they exist, but cannot decrypt without a key; wrapper adapters are possible only where the external binary is installed.
4. **Spectrogram "detection"** is a heuristic over image-like structure. A human decides whether a pattern is a message.
5. **Video.** Hiding in motion vectors, residuals or P/B-frame syntax elements is out of scope. Frame-level analysis applies to decoded frames and is only trustworthy for lossless/near-lossless sources.
6. **Resource limits** use `RLIMIT_AS`/`RLIMIT_CPU`, which exist on Linux/macOS only. On Windows the wall-clock timeout and process kill still apply but memory caps do not, and helper processes may outlive a cancelled job.
7. **HEIC** needs libheif via pillow-heif; reported as unsupported when absent.
8. **Binwalk** exists as a Python (v2) and a Rust (v3) tool with different CLIs. The adapter targets what is installed; when absent, a built-in signature scanner (Phase 3) provides a reduced-capability fallback and says so.
9. **Audit chain** is tamper-evident only (see §5).
10. **SQLite** serialises writers; adequate for one user, not for multi-user deployments.

## 12. Implementation roadmap

| Phase | Scope | Exit criteria (summary) |
|---|---|---|
| **1** | Foundation: DB, API, evidence management, audit log, job system, plugin framework, frontend shell | See §13 — **implemented** |
| 2 | Universal identification: magic + structural format verification, extension mismatch, hashes, trailing data, metadata (EXIF/XMP/IPTC/PNG text/tags/ICC) | Ground-truth corpus identifies every supported format; mismatches and trailing data detected with tests; unsupported formats reported explicitly |
| 3 | Image Lab: PNG chunk/CRC and JPEG marker analysis, LSB extraction with configurable traversal, bit-plane viewer, histograms/entropy/chi-square, embedded-file carving | Planted LSB payloads recovered bit-exactly across channel/bit/order combos; appended ZIP found and safely extracted; clean images do not raise high-confidence findings |
| 4 | Audio Lab: waveform, STFT spectrogram, PCM LSB, FFT/filters, WAV chunk analysis | Known tones/spectrogram text visible at expected coordinates; PCM LSB recovered exactly; lossy-codec limitation shown |
| 5 | Video Lab: ffprobe container analysis, frame extraction, temporal analysis, audio hand-off | Planted-frame payload recovered; duplicate/anomalous frames flagged; extracted audio linked to parent evidence |
| 6 | Analyze Everything engine (intensity levels, executed/skipped report) and CTF Flag Hunter | Pipeline ground-truth integration tests; flag candidates always carry source + extraction config |
| 7 | Payload extractor workspace, bookmarks, comparison, extraction history | Every payload has offset/coordinates, method, config, size, hash, confidence |
| 8 | HTML/JSON/CSV(/PDF) reports, hardening, performance, security review | Reports reproducible; load tests on large files; fuzz-style malformed-input tests |

## 13. Acceptance criteria — Phase 1

| # | Criterion | Verified by |
|---|---|---|
| 1.1 | Starts offline against an empty data dir, creating DB and directories; health endpoint reports DB and storage state | `test_health_cases.py` |
| 1.2 | Case create/list/get/update/archive; purge requires typing the exact case name and leaves the audit trail intact | `test_health_cases.py` |
| 1.3 | Evidence upload is streamed; MD5/SHA-1/SHA-256 equal independently computed values; oversize upload → 413 with no temp residue; stored read-only under `originals/`; duplicates flagged, not blocked | `test_evidence.py` |
| 1.4 | Original bytes are unchanged after any job; download returns identical bytes as an attachment; no path traversal via filenames | `test_evidence.py`, `test_security.py` |
| 1.5 | Every mutating action and every raw-evidence download is audited; chain verifies; edited, deleted, or re-ordered rows are detected | `test_audit.py` |
| 1.6 | Jobs run in a subprocess; progress is reported; queued and running jobs can be cancelled (including grandchild processes); timeout and memory limits are enforced; crashes and interrupted jobs are reported accurately | `test_jobs.py` |
| 1.7 | Plugin registry validates metadata, reports dependency availability, filters by format, publishes config JSON Schema, and loads entry-point plugins | `test_plugins_deps.py` |
| 1.8 | Dependency report is truthful for missing tools and never raises | `test_plugins_deps.py` |
| 1.9 | Host/Origin checks, `nosniff`, octet-stream downloads, no network client imports | `test_security.py` |
| 1.10 | Frontend: type-checks and builds without errors; flow *create case → import → inspect hashes/hex → run integrity job → see finding and audit trail* works against the live API; dark theme; every nav destination reachable, with later-phase labs honestly marked as not yet implemented | `tsc`, `vite build`, vitest, live smoke test |
| 1.11 | The plugin guide is true: its sample plugin is extracted from `PLUGINS.md` and run through the job system; the documented example plugin produces known-answer results (constant data → 0 bits, uniform bytes → 8 bits, 75/25 split → 0.8113 bits), merges regions, discloses truncation and partial windows, and never reports a heuristic above `low` | `test_docs_snippets.py`, `test_example_plugin.py` |
| 1.12 | Layering: only the HTTP layer imports the web framework; the plugin SDK and worker load none | `test_security.py` |

## 14. Known gaps in what is built today (Phase 1)

Stated plainly so nobody mistakes the foundation for the finished product.

1. **No steganography analysis exists yet.** The only built-in plugin verifies evidence integrity. Image, audio and video labs, metadata extraction, payload extraction, the CTF flag hunter and reports are Phases 2–8; their UI pages are labelled as not implemented and do no work.
2. **No format identification** (Phase 2). `detected_format` is never populated, so only plugins declaring `*` are runnable and the UI cannot offer format-specific tools.
3. **No schema migrations.** Tables are created with `create_all`; the first schema change must introduce Alembic with the current schema as the baseline.
4. **Single-user, no authentication.** Protection against other local web pages (Host/Origin checks, loopback binding) is not protection against another user on the same machine.
5. **Worker isolation is fault isolation, not a sandbox** (see `docs/PLUGINS.md` §1). Plugins are trusted code.
6. **Memory/CPU limits are POSIX-only.** Windows gets timeout and cancel, but not rlimits, and has not been tested.
7. **Audit log is tamper-evident, not tamper-proof** (§5). Nothing anchors the chain head outside the database yet.
8. **Archive/decompression limits are unimplemented** because nothing decompresses yet (§9).
9. **Verification scope.** The UI was exercised end to end in headless Chrome driven by Playwright plus unit tests; it has not been manually reviewed across browsers or on touch devices.
10. **Hex-viewer reads are not audited.** Imports, full downloads, artifact downloads, job lifecycle, notes and case changes are; interactive browsing of bytes is not, to keep the log readable. If a case requires a record of what was viewed, that needs a coarser "evidence opened" event, which does not exist yet.
