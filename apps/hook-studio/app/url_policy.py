from __future__ import annotations

from urllib.parse import urlsplit


def is_sendable_media_url(value: object) -> bool:
    """Single source of truth for media URLs allowed to cross the Kernel boundary."""

    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        return False
    parsed = urlsplit(value.strip())
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )
