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

_SURROGATE_RE = re.compile("[\ud800-\udfff]")

#: A run of a fence's language tag characters (``json``, ``c++``, ``x-y``: ASCII letters, digits, ``_``, ``+``, ``-``)
#: and a run of spaces or tabs. Each is matched at one given index only (a single class repeated, nothing after it), so
#: reading a run costs its length and never backtracks.
_TAG_RUN = re.compile(r"[A-Za-z0-9_+-]*")
_BLANK_RUN = re.compile(r"[ \t]*")
#: The opener of a line fence (three backticks, a language tag, spaces or tabs, a line break) and the end of its body
#: (a line break, spaces or tabs, three backticks). Each starts with a literal, and the runs it reads after one start
#: (the tag and blanks after three backticks, the blanks after a line break) belong to that start alone, so one search
#: over the whole text is linear.
_LINE_OPENER_RE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\r?\n")
_LINE_CLOSER_RE = re.compile(r"\n[ \t]*```")
_FENCE = "```"


class ProviderOutputError(ValueError):
    """The provider's text is not a single JSON object."""


def _after_tag_and_blanks(text: str, i: int) -> int:
    """The index after the language tag and the spaces or tabs that start at ``i``."""
    return _BLANK_RUN.match(text, _TAG_RUN.match(text, i).end()).end()


def _line_closer(text: str, b: int) -> int:
    """The end of a line fence's body that starts at ``b``: the first index ``e >= b`` where a line break (LF or CR LF),
    spaces or tabs and three backticks follow. ``-1`` when the body is never closed. One linear search."""
    m = _LINE_CLOSER_RE.search(text, b)
    if m is None:
        return -1
    nl = m.start()
    return nl - 1 if nl - 1 >= b and text[nl - 1] == "\r" else nl


def strip_code_fences(text: str) -> str:
    """Return the body of the first Markdown code fence in ``text``, or ``text`` itself.

    Any prose outside the fence is discarded. Without a fence the text is returned
    unchanged (surrounding whitespace is left for the caller to strip).

    A line fence (three opening backticks with an optional language tag and a line break, a body, then a line break and
    three closing backticks) is taken first; failing that, an inline fence (the first three backticks with an optional
    tag, up to the next three). The text is read in linear time: only the first line opener can have a closer (a closer
    after a later opener closes the first one too), so one opener search and one closer search decide the result at any
    size the parser accepts (a lazy pattern searched from every opener with no closer was quadratic: 12 s at 80 KB,
    minutes at 320 KB).
    """
    opener = _LINE_OPENER_RE.search(text)
    if opener is not None:
        e = _line_closer(text, opener.end())
        if e >= 0:
            return text[opener.end() : e]
    first = text.find(_FENCE)
    if first < 0:
        return text
    b = _after_tag_and_blanks(text, first + 3)
    e = text.find(_FENCE, b)
    if e < 0:
        return text
    return text[b:e]


def _reject_constant(name: str) -> Any:
    raise ProviderOutputError(f"non-finite JSON constant {name!r} is not allowed")


def _strict_fence_body(stripped: str) -> str | None:
    """The body of a reply that is exactly one fence (``stripped`` has no surrounding whitespace): three opening
    backticks with an optional language tag, spaces or tabs and an optional line break; the body; an optional line
    break, spaces or tabs and the three closing backticks that end the text. ``None`` when the reply is not one fence. Linear:
    the opener and the closer are read once each from their ends (a backtracking pattern over the same shape was
    cubic on a run of spaces, 22 s at 4 KB)."""
    n = len(stripped)
    if n < 6 or not stripped.startswith(_FENCE) or not stripped.endswith(_FENCE):
        return None
    k = _after_tag_and_blanks(stripped, 3)
    if stripped.startswith("\r\n", k):
        k += 2
    elif stripped.startswith("\n", k):
        k += 1
    c = n - 3  # the closing fence
    if k > c:
        return None
    s0 = k + len(stripped[k:c].rstrip(" \t"))  # the spaces or tabs before the closing fence start here
    e = s0
    if s0 - 2 >= k and stripped[s0 - 2 : s0] == "\r\n":
        e = s0 - 2
    elif s0 - 1 >= k and stripped[s0 - 1] == "\n":
        e = s0 - 1
    return stripped[k:e]


def _strict_body(text: str) -> str:
    """The JSON text of a strict reply: the bare object, or the body of exactly one fence that opens and closes the
    text (only whitespace outside it). Anything else raises."""
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped
    body = _strict_fence_body(stripped)
    if body is None:
        raise ProviderOutputError("the reply is neither one bare JSON object nor exactly one code fence around one (text outside the object is refused)")
    return body


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
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:  # a lone surrogate: not valid Unicode text, so no JSON object of it is taken
        raise ProviderOutputError("provider output is not valid Unicode text (it holds a lone UTF-16 surrogate code point)") from None
    if size > max_bytes:
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
                    _refuse_surrogates(obj)
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
    _refuse_surrogates(obj)
    return obj


def _refuse_surrogates(obj: Any) -> None:
    """Raise :class:`ProviderOutputError` when a string of the parsed object (a key or a value) holds a lone surrogate:
    JSON's ``\\ud83d`` escape decodes to one, and no contract, digest or signature downstream can take it. An iterative
    walk (the parser already bounded the depth)."""
    stack = [obj]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and _SURROGATE_RE.search(k):
                    raise ProviderOutputError("provider output holds a lone UTF-16 surrogate code point in a key (not valid Unicode text)")
                stack.append(v)
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str) and _SURROGATE_RE.search(node):
            raise ProviderOutputError("provider output holds a lone UTF-16 surrogate code point in a string (not valid Unicode text)")


# --------------------------------------------------------------------------------------------- argument diagnosis record

#: The most ``verified`` paths :func:`asserted_verified_paths` reports (the walk itself is bounded by the parse limits).
MAX_ASSERTED_PATHS = 256


def asserted_verified_paths(raw: Any) -> list[str]:
    """The paths (``problem.premises[2].grounding``, ...) where the provider's parsed JSON object wrote ``verified: true``
    on a grounding. Only checks in this process set ``verified``; every path found is recorded in
    ``TranslationResult.asserted_verified`` and as the translation diagnostic "E505: the translation asserted verified=true
    at <path>; discarded: only checks set it". A grounding is any object held under a ``grounding`` key (a symbol's, a
    premise's, the conclusion's, a glossary entry's). The walk is iterative over dicts and lists, so it is bounded by what
    the parser accepted (its byte bound and nesting depth), and at most :data:`MAX_ASSERTED_PATHS` paths are reported.
    ``verified: false`` or ``null`` claims no authority and is not reported. Nothing is evaluated."""
    out: list[str] = []
    stack: list[tuple[Any, str, bool]] = [(raw, "", False)]
    while stack and len(out) < MAX_ASSERTED_PATHS:
        node, path, is_grounding = stack.pop()
        if isinstance(node, dict):
            if is_grounding and node.get("verified") is True:
                out.append(path or "grounding")
            children = [(v, f"{path}.{k}" if path else str(k), k == "grounding") for k, v in node.items() if isinstance(v, (dict, list))]
            stack.extend(reversed(children))
        elif isinstance(node, list):
            stack.extend(reversed([(v, f"{path}[{i}]", False) for i, v in enumerate(node) if isinstance(v, (dict, list))]))
    return out
