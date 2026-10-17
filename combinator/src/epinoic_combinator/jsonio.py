"""Strict JSON and the canonical form of the integration protocol (``integration/PROTOCOL.md`` section 1 of the
translator), restated with the standard library so the combinator reads and writes exactly what the port accepts.

* **Strict parsing.** UTF-8 only; no NaN or Infinity; no duplicate keys; no floats (port messages carry integers and
  strings only); no lone surrogate in a string or a key; nesting at most :data:`MAX_DEPTH`.
* **Canonical JSON.** Keys sorted by code point; separators ``,`` and ``:`` with no whitespace; non-ASCII written raw;
  integers only, within the IEEE double safe range. Byte-identical to the translator's
  ``epinoic_logic.integration.canonical.canonical_json`` (the sub-project's tests run the translator's canonical
  vectors, ``tests/vectors/canonical/``).
* **Digests** are lowercase hex SHA-256: of the canonical JSON for an object, of the exact UTF-8 bytes for a text.

Every error names the rule it broke, never the content.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Union

__all__ = ["MAX_DEPTH", "MAX_SAFE_INTEGER", "JsonError", "loads_strict", "check_value", "canonical_json", "sha256_text",
           "sha256_bytes", "sha256_json", "has_lone_surrogate"]

MAX_DEPTH = 64
MAX_SAFE_INTEGER = 2 ** 53 - 1


class JsonError(ValueError):
    """A value or a document outside the protocol's JSON rules. The message names the rule, never the content."""


def has_lone_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def _no_constant(name: str) -> Any:
    raise JsonError(f"non-finite JSON constant {name} is not allowed")


def _no_float(text: str) -> Any:
    raise JsonError("a JSON number with a fraction or an exponent is not allowed (integers only)")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise JsonError("a JSON object repeats a key")
        out[key] = value
    return out


def loads_strict(data: Union[str, bytes, bytearray]) -> Any:
    """Parse one protocol document. Raises :class:`JsonError` for anything the rules above refuse."""
    if isinstance(data, (bytes, bytearray)):
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            raise JsonError("the document is not UTF-8") from None
    elif isinstance(data, str):
        text = data
    else:
        raise JsonError("the document must be text or bytes")
    try:
        value = json.loads(text, parse_constant=_no_constant, parse_float=_no_float, object_pairs_hook=_pairs)
    except JsonError:
        raise
    except RecursionError:
        raise JsonError("the document nests too deeply") from None
    except ValueError:
        raise JsonError("the document is not valid JSON") from None
    check_value(value)
    return value


def check_value(value: Any) -> None:
    """Raise :class:`JsonError` unless ``value`` is a protocol JSON value (iterative over containers' children)."""
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise JsonError(f"the value nests deeper than {MAX_DEPTH} levels")
        if node is None or node is True or node is False:
            continue
        if type(node) is int:
            if not -MAX_SAFE_INTEGER <= node <= MAX_SAFE_INTEGER:
                raise JsonError("an integer is outside the safe range (|n| <= 2^53 - 1)")
            continue
        if isinstance(node, float):
            raise JsonError("a float is not allowed (integers only)")
        if type(node) is str:
            if has_lone_surrogate(node):
                raise JsonError("a string holds a lone surrogate")
            continue
        if isinstance(node, (list, tuple)):
            stack.extend((child, depth + 1) for child in node)
            continue
        if isinstance(node, dict):
            for key, child in node.items():
                if type(key) is not str:
                    raise JsonError("an object key is not a string")
                if has_lone_surrogate(key):
                    raise JsonError("an object key holds a lone surrogate")
                stack.append((child, depth + 1))
            continue
        raise JsonError(f"a value of type {type(node).__name__} is not JSON")


def canonical_json(value: Any) -> str:
    """The canonical text of ``value``. Raises :class:`JsonError` for a value outside the protocol's rules."""
    check_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """SHA-256 of the exact UTF-8 bytes of ``text`` (a lone surrogate is refused, never replaced)."""
    if type(text) is not str:
        raise JsonError("a text digest needs a string")
    if has_lone_surrogate(text):
        raise JsonError("a text with a lone surrogate has no UTF-8 form")
    return sha256_bytes(text.encode("utf-8"))


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))
