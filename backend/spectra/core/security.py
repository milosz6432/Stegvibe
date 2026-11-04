"""Filename sanitising and path containment. Pure helpers: no web framework imports.

The plugin SDK imports this module, so it must stay light. HTTP hardening lives in api/middleware.py.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from spectra.core.errors import ForbiddenError

# Bidirectional-control characters are used to spoof extensions ("invoice‮gnp.exe"). Strip them.
_BIDI = set("‎‏؜‪‫‬‭‮⁦⁧⁨⁩")
MAX_FILENAME_LEN = 255


def sanitize_filename(raw: str | None) -> str:
    """Return a display-safe filename. The result is never used to build a filesystem path."""
    name = (raw or "").replace("\x00", "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if c not in _BIDI and unicodedata.category(c) != "Cc")
    name = name.strip()
    if name in {"", ".", ".."}:
        return "unnamed"
    if len(name) > MAX_FILENAME_LEN:
        stem, dot, ext = name.rpartition(".")
        if dot and 0 < len(ext) <= 16:
            name = stem[: MAX_FILENAME_LEN - len(ext) - 1] + "." + ext
        else:
            name = name[:MAX_FILENAME_LEN]
    return name


_EXT_RE = re.compile(r"^[a-z0-9]{1,16}$")


def declared_extension(filename: str) -> str | None:
    """Lower-cased final extension without the dot, or None."""
    _, dot, ext = filename.rpartition(".")
    ext = ext.lower()
    if dot and _EXT_RE.match(ext):
        return ext
    return None


def resolve_within(base: Path, *parts: str) -> Path:
    """Join ``parts`` onto ``base`` and make sure the resolved result cannot escape ``base``."""
    base_resolved = base.resolve()
    candidate = base_resolved.joinpath(*parts).resolve()
    if candidate != base_resolved and not candidate.is_relative_to(base_resolved):
        raise ForbiddenError("path escapes its permitted directory", code="path_traversal")
    return candidate
