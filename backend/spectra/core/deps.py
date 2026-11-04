"""Dependency adapters: truthful availability reporting for every library and binary SPECTRA may use.

Nothing here imports heavy analysis libraries into the API process. Python packages are located with
``importlib.util.find_spec`` and versioned from package metadata; ``deep=True`` additionally proves the
package imports by doing so in a throw-away isolated subprocess.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass(frozen=True)
class DepSpec:
    name: str  # stable id used by plugin metadata
    kind: str  # "python" | "binary"
    module: str | None = None  # import name (python)
    dists: tuple[str, ...] = ()  # distribution names to read the version from
    binary: str | None = None
    version_args: tuple[str, ...] = ("--version",)
    required: bool = False  # required for the core application to run
    used_in: tuple[str, ...] = ()
    purpose: str = ""
    install_hint: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


KNOWN: tuple[DepSpec, ...] = (
    DepSpec(
        "fastapi", "python", "fastapi", ("fastapi",), required=True, used_in=("core",), purpose="HTTP API"
    ),
    DepSpec(
        "sqlalchemy",
        "python",
        "sqlalchemy",
        ("SQLAlchemy",),
        required=True,
        used_in=("core",),
        purpose="Metadata database",
    ),
    DepSpec(
        "pydantic",
        "python",
        "pydantic",
        ("pydantic",),
        required=True,
        used_in=("core",),
        purpose="Schemas and validation",
    ),
    DepSpec(
        "python-magic",
        "python",
        "magic",
        ("python-magic",),
        required=True,
        used_in=("core", "phase 2"),
        purpose="libmagic file-type hints",
        install_hint="pip install python-magic; apt install libmagic1",
        aliases=("magic", "libmagic"),
    ),
    DepSpec(
        "pillow",
        "python",
        "PIL",
        ("pillow",),
        used_in=("phase 3",),
        purpose="Image decoding",
        install_hint="pip install 'spectra-stego[image]'",
        aliases=("PIL",),
    ),
    DepSpec(
        "numpy",
        "python",
        "numpy",
        ("numpy",),
        used_in=("phase 3", "phase 4", "phase 5"),
        purpose="Array maths",
        install_hint="pip install 'spectra-stego[image]'",
    ),
    DepSpec(
        "scipy",
        "python",
        "scipy",
        ("scipy",),
        used_in=("phase 3", "phase 4"),
        purpose="Statistics, STFT, filtering",
        install_hint="pip install 'spectra-stego[image]'",
    ),
    DepSpec(
        "opencv",
        "python",
        "cv2",
        ("opencv-python-headless", "opencv-python", "opencv-contrib-python"),
        used_in=("phase 3", "phase 5"),
        purpose="Image/video frame processing",
        install_hint="pip install opencv-python-headless",
        aliases=("cv2",),
    ),
    DepSpec(
        "scikit-image",
        "python",
        "skimage",
        ("scikit-image",),
        used_in=("phase 3",),
        purpose="Image statistics",
        install_hint="pip install scikit-image",
        aliases=("skimage",),
    ),
    DepSpec(
        "pillow-heif",
        "python",
        "pillow_heif",
        ("pillow-heif",),
        used_in=("phase 3",),
        purpose="HEIC/HEIF decoding",
        install_hint="pip install pillow-heif",
    ),
    DepSpec(
        "librosa",
        "python",
        "librosa",
        ("librosa",),
        used_in=("phase 4",),
        purpose="Audio analysis / spectrograms",
        install_hint="pip install 'spectra-stego[audio]'",
    ),
    DepSpec(
        "soundfile",
        "python",
        "soundfile",
        ("soundfile",),
        used_in=("phase 4",),
        purpose="PCM audio I/O (needs libsndfile)",
        install_hint="pip install soundfile",
    ),
    DepSpec(
        "mutagen",
        "python",
        "mutagen",
        ("mutagen",),
        used_in=("phase 2", "phase 4"),
        purpose="Audio tags",
        install_hint="pip install mutagen",
    ),
    DepSpec(
        "pyav",
        "python",
        "av",
        ("av",),
        used_in=("phase 5",),
        purpose="Video demuxing/decoding",
        install_hint="pip install av",
        aliases=("av",),
    ),
    DepSpec(
        "construct",
        "python",
        "construct",
        ("construct",),
        used_in=("phase 2", "phase 3"),
        purpose="Binary structure parsing",
        install_hint="pip install construct",
    ),
    DepSpec(
        "yara-python",
        "python",
        "yara",
        ("yara-python",),
        used_in=("phase 6",),
        purpose="Signature rules",
        install_hint="pip install yara-python",
        aliases=("yara",),
    ),
    DepSpec(
        "ffmpeg",
        "binary",
        binary="ffmpeg",
        version_args=("-version",),
        used_in=("phase 4", "phase 5"),
        purpose="Media decoding/extraction",
        install_hint="apt install ffmpeg",
    ),
    DepSpec(
        "ffprobe",
        "binary",
        binary="ffprobe",
        version_args=("-version",),
        used_in=("phase 2", "phase 4", "phase 5"),
        purpose="Container/stream inspection",
        install_hint="apt install ffmpeg",
    ),
    DepSpec(
        "exiftool",
        "binary",
        binary="exiftool",
        version_args=("-ver",),
        used_in=("phase 2",),
        purpose="Comprehensive metadata extraction",
        install_hint="apt install libimage-exiftool-perl",
    ),
    DepSpec(
        "binwalk",
        "binary",
        binary="binwalk",
        version_args=("--help",),
        used_in=("phase 3", "phase 7"),
        purpose="Embedded file signature scanning",
        install_hint="pip install binwalk  (or cargo install binwalk for v3)",
    ),
)

_BY_NAME = {s.name: s for s in KNOWN}
for _s in KNOWN:
    for _a in _s.aliases:
        _BY_NAME.setdefault(_a, _s)


class DependencyStatus(BaseModel):
    name: str
    kind: str
    available: bool
    version: str | None = None
    location: str | None = None
    required: bool = False
    used_in: list[str] = []
    purpose: str = ""
    install_hint: str = ""
    error: str | None = None
    verified_by_import: bool = False


def _python_version(spec: DepSpec) -> str | None:
    for dist in spec.dists:
        try:
            return importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def _check_python(spec: DepSpec, deep: bool) -> DependencyStatus:
    assert spec.module
    base = dict(
        name=spec.name,
        kind="python",
        required=spec.required,
        used_in=list(spec.used_in),
        purpose=spec.purpose,
        install_hint=spec.install_hint,
    )
    try:
        found = importlib.util.find_spec(spec.module)
    except (ImportError, ValueError) as exc:
        return DependencyStatus(**base, available=False, error=f"{type(exc).__name__}: {exc}")
    if found is None:
        return DependencyStatus(**base, available=False, error=f"module '{spec.module}' not installed")

    version = _python_version(spec)
    location = found.origin if found.origin and found.origin != "built-in" else None

    # python-magic can be installed while the native libmagic is absent, so always prove it imports.
    needs_import_proof = deep or spec.module == "magic"
    verified = False
    if needs_import_proof:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", f"import {spec.module}"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return DependencyStatus(
                **base, available=False, version=version, location=location, error="import timed out"
            )
        if proc.returncode != 0:
            tail = _first_line(
                proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "import failed"
            )
            return DependencyStatus(
                **base,
                available=False,
                version=version,
                location=location,
                error=f"installed but fails to import: {tail}",
            )
        verified = True
    return DependencyStatus(
        **base, available=True, version=version, location=location, verified_by_import=verified
    )


def _check_binary(spec: DepSpec) -> DependencyStatus:
    assert spec.binary
    base = dict(
        name=spec.name,
        kind="binary",
        required=spec.required,
        used_in=list(spec.used_in),
        purpose=spec.purpose,
        install_hint=spec.install_hint,
    )
    path = shutil.which(spec.binary)
    if not path:
        return DependencyStatus(**base, available=False, error=f"'{spec.binary}' not found on PATH")
    version = None
    try:
        proc = subprocess.run(
            [path, *spec.version_args],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        version = _first_line(proc.stdout or proc.stderr) or None
    except (subprocess.TimeoutExpired, OSError) as exc:
        return DependencyStatus(
            **base, available=False, location=path, error=f"found but could not run: {exc}"
        )
    return DependencyStatus(**base, available=True, location=path, version=version)


class DependencyChecker:
    """Cached, thread-safe availability checks."""

    def __init__(self, ttl_seconds: float = 60.0):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, bool], tuple[float, DependencyStatus]] = {}

    def check_spec(self, spec: DepSpec, *, deep: bool = False, refresh: bool = False) -> DependencyStatus:
        key = (spec.name, deep)
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and not refresh and now - hit[0] < self._ttl:
                return hit[1]
        status = _check_binary(spec) if spec.kind == "binary" else _check_python(spec, deep)
        with self._lock:
            self._cache[key] = (now, status)
        return status

    def check_all(self, *, deep: bool = False, refresh: bool = False) -> list[DependencyStatus]:
        with ThreadPoolExecutor(max_workers=6) as pool:
            return list(pool.map(lambda s: self.check_spec(s, deep=deep, refresh=refresh), KNOWN))

    def check_named(self, name: str, kind: str) -> DependencyStatus:
        """Check a plugin-declared dependency; unknown names fall back to a generic check by kind."""
        spec = _BY_NAME.get(name)
        if spec is None:
            spec = (
                DepSpec(name, "binary", binary=name)
                if kind == "binary"
                else DepSpec(name, "python", module=name, dists=(name,))
            )
        elif spec.kind != kind:
            return DependencyStatus(
                name=name,
                kind=kind,
                available=False,
                error=f"'{name}' is known as a {spec.kind} dependency, not {kind}",
            )
        return self.check_spec(spec)

    def summarize(self, statuses: Iterable[DependencyStatus]) -> dict:
        statuses = list(statuses)
        return {
            "total": len(statuses),
            "available": sum(s.available for s in statuses),
            "missing_required": [s.name for s in statuses if s.required and not s.available],
            "missing_optional": [s.name for s in statuses if not s.required and not s.available],
        }
