"""Strict parsing of model-provider output.

Provider text is untrusted data. It is parsed with :func:`json.loads` only; nothing
in it is ever evaluated or executed. The only leniency granted is stripping a
Markdown code fence around the JSON object, because models frequently add one.

A text that is itself exactly one JSON object is parsed as it is: a fence is looked
for only when the text is not one (so a string value that quotes ``` never cuts the
object). ``strict=True`` (the Overseer's verdict intake) tolerates nothing else: the
text is the bare object, or exactly one fence that opens the text and closes it.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..ir.canonical import strict_object_pairs

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


_STRICT_FENCE_RE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*(?:\r?\n)?(?P<body>.*?)(?:\r?\n)?[ \t]*```", re.DOTALL)


def _strict_body(text: str) -> str:
    """The JSON text of a strict reply: the bare object, or the body of exactly one fence that opens and closes the
    text (only whitespace outside it). Anything else raises."""
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped
    m = _STRICT_FENCE_RE.fullmatch(stripped)
    if m is None:
        raise ProviderOutputError("the reply is neither one bare JSON object nor exactly one code fence around one (text outside the object is refused)")
    return m.group("body")


def _loads(body: str) -> Any:
    return json.loads(body, parse_constant=_reject_constant, object_pairs_hook=strict_object_pairs)


def parse_json_object(text: str, max_bytes: int = 2_000_000, *, strict: bool = False) -> dict[str, Any]:
    """Parse ``text`` as exactly one JSON object.

    Raises :class:`ProviderOutputError` when the text is empty, too large, not valid
    JSON, nested too deeply to parse, repeats a key inside an object, contains
    NaN/Infinity, or decodes to something other than an object. A text that already
    is one JSON object is never searched for a fence; with ``strict`` a fence must
    open and close the whole text (prose around it, or a second fence, is refused).
    """
    if not isinstance(text, str):
        raise ProviderOutputError("provider output is not text")
    if len(text.encode("utf-8")) > max_bytes:
        raise ProviderOutputError(f"provider output exceeds {max_bytes} bytes")
    if strict:
        body = _strict_body(text).strip()
    else:
        body = text.strip()
        if body.startswith("{"):
            try:  # the text is itself the object: a ``` inside a string value is data, never a fence
                obj = _loads(body)
            except (json.JSONDecodeError, RecursionError, ValueError):
                body = strip_code_fences(text).strip()
            else:
                if isinstance(obj, dict):
                    return obj
                raise ProviderOutputError(f"provider output must be a JSON object, got {type(obj).__name__}")
        else:
            body = strip_code_fences(text).strip()
    if not body:
        raise ProviderOutputError("provider output is empty")
    try:
        obj = _loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderOutputError(
            f"provider output is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from None
    except RecursionError:
        raise ProviderOutputError("provider output nesting is too deep") from None
    except ValueError as exc:  # duplicate keys (strict pairs) or a rejected constant
        raise ProviderOutputError(f"provider output is not acceptable JSON: {exc}") from None
    if not isinstance(obj, dict):
        raise ProviderOutputError(f"provider output must be a JSON object, got {type(obj).__name__}")
    return obj
