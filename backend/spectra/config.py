"""Runtime configuration. Every field can be overridden with a ``SPECTRA_*`` environment variable."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "spectra"


def default_frontend_dist() -> Path:
    # <repo>/backend/spectra/config.py: parents[0]=spectra/, parents[1]=backend/, parents[2]=<repo>
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECTRA_", extra="ignore")

    # --- storage -------------------------------------------------------
    data_dir: Path = Field(default_factory=default_data_dir)

    # --- network (loopback by default; there is no authentication layer) ---
    host: str = "127.0.0.1"
    port: int = 8000
    # Host header allow-list (DNS-rebinding protection). Ports are ignored.
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]"]
    # Extra browser origins allowed to make state-changing requests (same-origin is always allowed).
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    serve_frontend: bool = True
    frontend_dist: Path = Field(default_factory=default_frontend_dist)

    # --- limits --------------------------------------------------------
    max_upload_bytes: int = 2 * 1024**3
    min_free_disk_bytes: int = 256 * 1024**2
    max_hex_read_bytes: int = 64 * 1024
    upload_buffer_bytes: int = 1024 * 1024

    # --- jobs ------------------------------------------------------------
    max_concurrent_jobs: int = Field(default_factory=lambda: max(1, (os.cpu_count() or 2) - 1))
    default_job_timeout_seconds: int = 600
    max_job_timeout_seconds: int = 3600
    default_job_memory_limit_mb: int = 4096  # 0 disables the cap (POSIX only)
    max_artifacts_per_job: int = 1000

    # --- misc ----------------------------------------------------------
    log_level: str = "INFO"
    stale_tmp_max_age_seconds: int = 24 * 3600

    @property
    def db_path(self) -> Path:
        return self.data_dir / "spectra.db"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def cases_dir(self) -> Path:
        return self.data_dir / "cases"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.tmp_dir, self.cases_dir):
            d.mkdir(parents=True, exist_ok=True)
