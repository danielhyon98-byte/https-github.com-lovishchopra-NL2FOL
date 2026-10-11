"""Strict parsing of model-provider output.

Provider text is untrusted data. It is parsed with :func:`json.loads` only; nothing
in it is ever evaluated or executed. The only leniency granted is stripping a
Markdown code fence around the JSON object, because models frequently add one.
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL)
_INLINE_FENCE_RE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*(.*?)```", re.DOTALL)


class ProviderOutputError(ValueError):
    """The provider's text is not a single JSON object."""


def strip_code_fences(text: str) -> str:
    """Return the body of the first Markdown code fence in ``text``, or ``text`` itself.

    Any prose outside the fence is discarded. Without a fence the text is returned
    unchanged (surrounding whitespace is left for the caller to strip).
    """
    match = _FENCE_RE.search(text)
    if match is None:
        match = _INLINE_FENCE_RE.search(text)
    if match is None:
        return text
    return match.group(1)


def _reject_constant(name: str) -> Any:
    raise ProviderOutputError(f"non-finite JSON constant {name!r} is not allowed")


def parse_json_object(text: str, max_bytes: int = 2_000_000) -> dict[str, Any]:
    """Parse ``text`` as exactly one JSON object.

    Raises :class:`ProviderOutputError` when the text is empty, too large, not valid
    JSON, contains NaN/Infinity, or decodes to something other than an object.
    """
    if not isinstance(text, str):
        raise ProviderOutputError("provider output is not text")
    if len(text.encode("utf-8")) > max_bytes:
        raise ProviderOutputError(f"provider output exceeds {max_bytes} bytes")
    body = strip_code_fences(text).strip()
    if not body:
        raise ProviderOutputError("provider output is empty")
    try:
        obj = json.loads(body, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ProviderOutputError(
            f"provider output is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from None
    if not isinstance(obj, dict):
        raise ProviderOutputError(f"provider output must be a JSON object, got {type(obj).__name__}")
    return obj
