"""Canonical media format identifiers shared by evidence records and plugin metadata.

Phase 2 (identification) is responsible for *assigning* these ids to evidence. Phase 1 only defines
the vocabulary so that plugins can declare what they support.
"""

from __future__ import annotations

IMAGE_FORMATS = ("png", "jpeg", "bmp", "tiff", "gif", "webp", "ico", "heic")
AUDIO_FORMATS = ("wav", "mp3", "flac", "ogg", "opus", "aac", "m4a", "aiff")
VIDEO_FORMATS = ("mp4", "mkv", "avi", "mov", "webm", "mpeg")

CATEGORY_OF: dict[str, str] = {
    **dict.fromkeys(IMAGE_FORMATS, "image"),
    **dict.fromkeys(AUDIO_FORMATS, "audio"),
    **dict.fromkeys(VIDEO_FORMATS, "video"),
}
CATEGORY_WILDCARDS = {f"{c}:*" for c in ("image", "audio", "video")}
ANY = "*"


def is_valid_format_token(token: str) -> bool:
    """A plugin may declare a canonical format id, a category wildcard (``image:*``) or ``*``."""
    return token == ANY or token in CATEGORY_WILDCARDS or token in CATEGORY_OF


def token_matches(token: str, fmt: str | None) -> bool:
    """Does a plugin's declared token cover an evidence file of format ``fmt``?"""
    if token == ANY:
        return True
    if fmt is None:
        return False
    if token == fmt:
        return True
    if token in CATEGORY_WILDCARDS:
        return CATEGORY_OF.get(fmt) == token.split(":", 1)[0]
    return False
