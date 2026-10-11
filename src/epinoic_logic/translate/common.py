"""Small shared helpers for the translation layer (ids, timestamps, truncation)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def utc_now_rfc3339() -> str:
    """Current UTC time as an RFC 3339 string with second precision and a ``Z`` suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    """Opaque unique identifier with a short, readable prefix (e.g. ``tr-...``)."""
    return f"{prefix}-{uuid.uuid4().hex}"


def truncate(text: str, limit: int) -> str:
    """Cut ``text`` to at most ``limit`` characters, marking the cut with ``...``."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."
