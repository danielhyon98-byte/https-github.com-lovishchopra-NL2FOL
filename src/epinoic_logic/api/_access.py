"""Accessors of the public API that read a record the translator produced (``docs/PUBLIC_API.md``).

Each reads one field of a record as the record holds it and adds no reading of its own: it never re-derives, relabels or
releases anything.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

__all__ = ["labelled_text"]


def labelled_text(event: Any) -> Optional[str]:
    """The text the meaning label of a channel event read (``ChannelEvent.labelled_text``, exactly the text it labelled), or None
    when the event holds none, holds something other than text, holds no SHA-256 beside it (``labelled_text_sha256``), or holds a
    text whose SHA-256 differs from that one: a text that is not bound to its digest is never handed on as if it were the labelled
    one (check round of stage 2a: an absent digest skipped the check), and the caller treats None as a missing record (the label
    gate withholds). Never raises."""
    try:
        text = getattr(event, "labelled_text", None)
        if not isinstance(text, str):
            return None
        digest = getattr(event, "labelled_text_sha256", None)
        if not isinstance(digest, str) or hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest() != digest:
            return None
        return text
    except Exception:  # noqa: BLE001 - an unreadable event holds no labelled text
        return None
