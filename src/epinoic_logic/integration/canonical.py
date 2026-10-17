"""Strict JSON and the canonical form of ``epinoic.integration.v1`` (``integration/PROTOCOL.md`` section 1).

Standard library only, so the JavaScript side (``integration/website/src/verify/canonical-json.js``) can be checked
against it byte for byte on the golden vectors in ``integration/vectors/canonical/``.

Rules:

* **Strict parsing.** UTF-8 only; no NaN or Infinity; no duplicate keys; no floats (a protocol message carries integers
  and strings only); no lone surrogate in any string or key; nesting at most :data:`MAX_DEPTH`.
* **Canonical JSON.** Keys sorted by code point (all protocol keys are ASCII, so code-point and UTF-16 order agree, and
  the JavaScript side sorts by code point for any other key); separators ``,`` and ``:`` with no whitespace; non-ASCII
  written raw; integers only, within the IEEE double safe range so both sides read the same value. The form is
  byte-identical to :func:`epinoic_logic.ir.canonical.canonical_json` on every value this module accepts.
* **Digests** are lowercase hex SHA-256: of the canonical JSON for an object, of the exact UTF-8 bytes for a text.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Union

__all__ = [
    "MAX_DEPTH", "MAX_SAFE_INTEGER", "CanonicalError", "loads_strict", "check_value", "canonical_json", "canonical_bytes",
    "sha256_text", "sha256_json", "has_lone_surrogate",
]

MAX_DEPTH = 64
#: ``Number.MAX_SAFE_INTEGER``: the largest integer both sides represent exactly.
MAX_SAFE_INTEGER = 2 ** 53 - 1


class CanonicalError(ValueError):
    """A value or a document outside the protocol's JSON rules. The message names the rule, never the content."""


def has_lone_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def _no_constant(name: str) -> Any:
    raise CanonicalError(f"non-finite JSON constant {name} is not allowed")


def _no_float(text: str) -> Any:
    raise CanonicalError("a JSON number with a fraction or an exponent is not allowed (integers only)")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CanonicalError("a JSON object repeats a key")
        out[key] = value
    return out


def loads_strict(data: Union[str, bytes, bytearray]) -> Any:
    """Parse one protocol document. Raises :class:`CanonicalError` for anything the rules above refuse."""
    if isinstance(data, (bytes, bytearray)):
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            raise CanonicalError("the document is not UTF-8") from None
    elif isinstance(data, str):
        text = data
    else:
        raise CanonicalError("the document must be text or bytes")
    try:
        value = json.loads(text, parse_constant=_no_constant, parse_float=_no_float, object_pairs_hook=_pairs)
    except CanonicalError:
        raise
    except RecursionError:
        raise CanonicalError("the document nests too deeply") from None
    except ValueError:
        raise CanonicalError("the document is not valid JSON") from None
    check_value(value)
    return value


def check_value(value: Any, _depth: int = 0) -> None:
    """Raise :class:`CanonicalError` unless ``value`` is a protocol JSON value (iterative over containers' children)."""
    stack: list[tuple[Any, int]] = [(value, _depth)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise CanonicalError(f"the value nests deeper than {MAX_DEPTH} levels")
        if node is None or node is True or node is False:
            continue
        if type(node) is int:
            if not -MAX_SAFE_INTEGER <= node <= MAX_SAFE_INTEGER:
                raise CanonicalError("an integer is outside the safe range (|n| <= 2^53 - 1)")
            continue
        if isinstance(node, float):
            raise CanonicalError("a float is not allowed (integers only)")
        if type(node) is str:
            if has_lone_surrogate(node):
                raise CanonicalError("a string holds a lone surrogate")
            continue
        if isinstance(node, (list, tuple)):
            stack.extend((child, depth + 1) for child in node)
            continue
        if isinstance(node, dict):
            for key, child in node.items():
                if type(key) is not str:
                    raise CanonicalError("an object key is not a string")
                if has_lone_surrogate(key):
                    raise CanonicalError("an object key holds a lone surrogate")
                stack.append((child, depth + 1))
            continue
        raise CanonicalError(f"a value of type {type(node).__name__} is not JSON")


def canonical_json(value: Any) -> str:
    """The canonical text of ``value`` (module docstring). Raises :class:`CanonicalError` for a non-protocol value."""
    check_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_text(text: str) -> str:
    """SHA-256 of the exact UTF-8 bytes of ``text`` (a lone surrogate is refused, never replaced)."""
    if type(text) is not str:
        raise CanonicalError("a text digest needs a string")
    if has_lone_surrogate(text):
        raise CanonicalError("a text with a lone surrogate has no UTF-8 form")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
