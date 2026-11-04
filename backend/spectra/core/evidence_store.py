"""On-disk evidence storage: streaming ingest, read-only originals, bounded range reads.

Layout (see docs/ARCHITECTURE.md §6)::

    <data>/tmp/                                       upload staging
    <data>/cases/<case_id>/originals/<evidence_id>    immutable original bytes (mode 0444)
    <data>/cases/<case_id>/derived/<job_id>/...       anything produced by analysis
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import stat
import tempfile
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from spectra.config import Settings
from spectra.core.errors import (
    InsufficientStorageError,
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
)
from spectra.core.security import resolve_within


@dataclass(frozen=True)
class IngestResult:
    path: Path
    size: int
    md5: str
    sha1: str
    sha256: str
    mime_hint: str | None


def _hasher(name: str):
    # MD5/SHA-1 are recorded only because forensic tooling and CTF writeups still quote them.
    return hashlib.new(name, usedforsecurity=False)


def _write_and_hash(fh, chunk: bytes, hashers: tuple) -> None:
    fh.write(chunk)
    for h in hashers:
        h.update(chunk)


class EvidenceStore:
    def __init__(self, settings: Settings):
        self.settings = settings

    # ---- layout --------------------------------------------------------
    def originals_dir(self, case_id: str) -> Path:
        return resolve_within(self.settings.cases_dir, case_id, "originals")

    def original_path(self, case_id: str, evidence_id: str) -> Path:
        return resolve_within(self.settings.cases_dir, case_id, "originals", evidence_id)

    def derived_dir(self, case_id: str, job_id: str) -> Path:
        return resolve_within(self.settings.cases_dir, case_id, "derived", job_id)

    def relpath(self, path: Path) -> str:
        return path.resolve().relative_to(self.settings.data_dir.resolve()).as_posix()

    # ---- ingest --------------------------------------------------------
    def _check_capacity(self, declared_length: int | None) -> None:
        limit = self.settings.max_upload_bytes
        if declared_length is not None and declared_length > limit:
            raise PayloadTooLargeError(
                f"Upload of {declared_length} bytes exceeds the configured limit of {limit} bytes."
            )
        free = shutil.disk_usage(self.settings.data_dir).free
        needed = (declared_length or 0) + self.settings.min_free_disk_bytes
        if free < needed:
            raise InsufficientStorageError(
                f"Not enough free disk space ({free} bytes free, {needed} required including reserve)."
            )

    async def ingest(
        self,
        case_id: str,
        evidence_id: str,
        chunks: AsyncIterator[bytes],
        *,
        declared_length: int | None = None,
    ) -> IngestResult:
        """Stream ``chunks`` to disk while hashing.

        Atomic: either the original exists in full or not at all.
        """
        self._check_capacity(declared_length)
        final = self.original_path(case_id, evidence_id)
        final.parent.mkdir(parents=True, exist_ok=True)
        self.settings.tmp_dir.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(prefix="upload-", suffix=".part", dir=self.settings.tmp_dir)
        tmp = Path(tmp_name)
        md5, sha1, sha256 = _hasher("md5"), _hasher("sha1"), _hasher("sha256")
        hashers = (md5, sha1, sha256)
        size = 0
        buf = bytearray()
        limit = self.settings.max_upload_bytes
        threshold = self.settings.upload_buffer_bytes
        try:
            with os.fdopen(fd, "wb") as fh:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > limit:
                        raise PayloadTooLargeError(f"Upload exceeds the configured limit of {limit} bytes.")
                    buf += chunk
                    if len(buf) >= threshold:
                        await asyncio.to_thread(_write_and_hash, fh, bytes(buf), hashers)
                        buf.clear()
                if buf:
                    await asyncio.to_thread(_write_and_hash, fh, bytes(buf), hashers)
                    buf.clear()
                fh.flush()
                os.fsync(fh.fileno())
            if size == 0:
                raise InvalidRequestError("The uploaded file is empty.", code="empty_file")
            os.replace(tmp, final)
            os.chmod(final, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0444
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            if getattr(exc, "errno", None) == 28:  # ENOSPC
                raise InsufficientStorageError("Disk full while storing evidence.") from exc
            raise
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return IngestResult(
            path=final,
            size=size,
            md5=md5.hexdigest(),
            sha1=sha1.hexdigest(),
            sha256=sha256.hexdigest(),
            mime_hint=self.detect_mime_hint(final),
        )

    @staticmethod
    def detect_mime_hint(path: Path) -> str | None:
        """Preliminary libmagic guess from the first 8 KiB. A hint only; Phase 2 does real identification."""
        try:
            import magic  # imported lazily: needs the system libmagic
        except Exception:
            return None
        try:
            with open(path, "rb") as fh:
                head = fh.read(8192)
            return magic.from_buffer(head, mime=True) or None
        except Exception:
            return None

    # ---- reads ---------------------------------------------------------
    def read_range(self, path: Path, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0:
            raise InvalidRequestError("offset and length must be non-negative")
        length = min(length, self.settings.max_hex_read_bytes)
        if not path.is_file():
            raise NotFoundError("Evidence file is missing from the store.", code="evidence_file_missing")
        with open(path, "rb") as fh:
            fh.seek(offset)
            return fh.read(length)

    @staticmethod
    def hex_rows(data: bytes, base_offset: int, width: int = 16) -> list[dict]:
        rows = []
        for i in range(0, len(data), width):
            part = data[i : i + width]
            rows.append(
                {
                    "offset": base_offset + i,
                    "hex": part.hex(" "),
                    "ascii": "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in part),
                }
            )
        return rows

    # ---- maintenance ---------------------------------------------------
    def purge_case_files(self, case_id: str) -> None:
        target = resolve_within(self.settings.cases_dir, case_id)
        if not target.exists():
            return

        def _force(func, p, exc):  # originals are 0444; make writable so removal works everywhere
            try:
                os.chmod(p, stat.S_IWUSR | stat.S_IRUSR)
                func(p)
            except OSError:
                pass

        shutil.rmtree(target, onexc=_force)

    def remove_derived(self, case_id: str, job_id: str) -> None:
        target = self.derived_dir(case_id, job_id)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

    def cleanup_stale_tmp(self) -> int:
        """Remove abandoned upload staging files. Returns the number removed."""
        removed = 0
        cutoff = time.time() - self.settings.stale_tmp_max_age_seconds
        if not self.settings.tmp_dir.exists():
            return 0
        for p in self.settings.tmp_dir.glob("upload-*.part"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                continue
        return removed
