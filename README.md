# SPECTRA

**S**teganography **P**robing, **E**xtraction, **C**arving & **T**riage **R**esearch **A**ssistant:
an offline-by-default workbench for finding and extracting hidden data in images, audio and video, built
for CTF players and digital-forensics work.

> ## Status: Phase 1 of 8 (foundation)
>
> **What works today:** investigation workspaces; streaming, hash-verified, read-only evidence import;
> hex viewer with byte inspector; a hash-chained audit log; a sandboxed job system; a plugin framework with
> one built-in plugin (evidence integrity verification); notes; findings with full provenance; a web UI
> for all of it.
>
> **What does not exist yet:** every steganography analysis technique. There is no image, audio or video lab,
> no LSB extraction, no metadata explorer, no flag hunter and no report generator. Those pages are present in
> the UI and clearly marked "not implemented". Nothing in SPECTRA simulates results. If a feature shows
> output, it was computed from your file. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §12 for the roadmap and
> §14 for known gaps.

## Principles

* **Evidence is immutable.** Originals are stored once, mode `0444`, never opened for writing, and
  re-verifiable at any time. Everything derived lives in a separate tree.
* **No certainty from heuristics.** Statistical findings carry a confidence level and a list of limitations.
  `verified` is reserved for deterministic checks and is enforced in code. "No findings" never means "clean".
* **Reproducible.** Each finding records the plugin id and version, the exact configuration and the SHA-256
  of the evidence it came from.
* **Audited.** Every state change and every raw-evidence download is recorded in a tamper-evident log.
* **Offline.** No network client code; a test enforces it. Binds to loopback by default.
* **Untrusted input.** Files are parsed, never executed. Analyses run in resource-limited subprocesses.

## Quick start

Requirements: Python 3.12+, Node.js 22.12+ and npm (20.19+ is enough to build but not to run the frontend tests), and `libmagic` on the system
(`apt install libmagic1`, `brew install libmagic`).

```bash
make setup      # creates .venv, installs the backend (+dev tools) and the frontend dependencies
make build      # builds the frontend into frontend/dist
make run        # serves API + UI at http://127.0.0.1:8000
```

Without `make`:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e "backend[dev]"
(cd frontend && npm install && npm run build)
python -m spectra
```

The Makefile assumes a POSIX shell. SPECTRA has been developed and tested on Linux; macOS should work;
Windows is untested (see Limitations).

Open <http://127.0.0.1:8000>, create an investigation, import a file, and run **Evidence integrity
verification** from the evidence page. The Settings page shows which optional tools are installed and,
for each missing one, what it is needed for and how to install it.

## Development

```bash
make dev-backend    # API with auto-reload on :8000
make dev-frontend   # Vite dev server on :5173, proxies /api to :8000
make test           # backend (pytest) + frontend (vitest)
make lint           # ruff + tsc
```

Backend code is under `backend/spectra`, tests under `backend/tests`. The frontend is React 19, TypeScript,
Vite, Tailwind 4, Zustand and TanStack Query under `frontend/src`.

Optional analysis libraries are grouped by the roadmap phase that needs them and are not required yet:
`pip install -e "backend[image]"`, `[audio]`, `[video]`, `[forensics]`.

## Configuration

Environment variables, all prefixed `SPECTRA_`:

| Variable | Default | Meaning |
|---|---|---|
| `DATA_DIR` | `~/.local/share/spectra` (Linux), platform equivalent elsewhere | Database, evidence, derived output |
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Bind address |
| `ALLOWED_HOSTS` | `["localhost","127.0.0.1","[::1]"]` | Accepted `Host` headers (DNS-rebinding protection) |
| `ALLOWED_ORIGINS` | the Vite dev origins | Extra browser origins allowed to make changes |
| `MAX_UPLOAD_BYTES` | 2 GiB | Evidence size limit |
| `MIN_FREE_DISK_BYTES` | 256 MiB | Free-space reserve; an import is refused up front if its declared size would eat into it |
| `MAX_CONCURRENT_JOBS` | CPU count − 1 | Parallel analysis jobs |
| `DEFAULT_JOB_TIMEOUT_SECONDS`, `MAX_JOB_TIMEOUT_SECONDS` | 600, 3600 | Per-job wall-clock limit |
| `DEFAULT_JOB_MEMORY_LIMIT_MB` | 4096 | Per-job address-space cap; `0` disables (POSIX only) |
| `LOG_LEVEL` | `INFO` | |

List values must be JSON: `SPECTRA_ALLOWED_HOSTS='["localhost","lab.example"]'`.

## Security notes

* **Hostile files.** SPECTRA never executes evidence, and parsing happens in separate processes with time and
  memory limits, but a parser bug in a native library is still a parser bug. For genuinely hostile samples,
  run SPECTRA in a VM or container.
* **No authentication.** It is a single-user local tool. Do not expose it beyond loopback without an
  authenticating reverse proxy in front.
* **Plugins are trusted code.** Process isolation contains crashes and runaway resource use; it does not stop
  a malicious plugin. Install only plugins you have read.
* **The audit log is tamper-evident, not tamper-proof.** Anyone who can write to the database file can rebuild
  the chain. If it matters for your case, record the chain head hash (shown after "Verify chain" on the Dashboard, and returned by `GET /api/audit/verify`) somewhere outside SPECTRA.

## Documentation

* [Architecture, schema, security model, roadmap, acceptance criteria](docs/ARCHITECTURE.md)
* [Writing plugins](docs/PLUGINS.md), with a complete tested example in
  [`backend/examples/byte_entropy_plugin.py`](backend/examples/byte_entropy_plugin.py)

## Limitations

These are inherent to the problem, not just to this phase, and SPECTRA will say so next to the relevant
results. Full list in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §11 and §14.

* Lossy formats (JPEG, MP3, AAC, most video) do not allow bit-exact recovery of pixel or sample LSBs, and
  JPEG-domain embedding needs DCT-level analysis rather than pixel analysis.
* Statistical steganalysis is probabilistic: weak against short payloads and adaptive embedding, prone to
  false positives on noisy images. Keyed tools (steghide, OpenStego, ...) cannot be decrypted without the key.
* Memory/CPU limits use POSIX rlimits; on Windows only the timeout and cancel apply.

## License

Not yet chosen.
