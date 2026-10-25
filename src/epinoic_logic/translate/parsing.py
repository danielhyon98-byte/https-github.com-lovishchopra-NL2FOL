"""Strict parsing of model-provider output.

Provider text is untrusted data. It is parsed with :func:`json.loads` only; nothing
in it is ever evaluated or executed. The only leniency granted is stripping a
Markdown code fence around the JSON object, because models frequently add one.

Bounds. Provider text is refused before parsing when it is larger than
:data:`MAX_PROVIDER_TEXT_BYTES` (64 KiB; :class:`ProviderOutputTooLarge`, or "nesting is too
deep" when its first 64 KiB already nest deeper than :data:`MAX_JSON_DEPTH`) or is not valid
Unicode text (a lone surrogate); the fence is found by one linear scan
(:func:`strip_code_fences`), so no input makes the scan quadratic (a long run of unclosed
openers once took seconds). The largest recorded translation is about a third of the bound.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..ir.canonical import strict_object_pairs

#: The largest provider output read (UTF-8 bytes): 64 KiB. The largest translation recorded in the repository's fixtures
#: and runs is about 22 KB (35 KB pretty-printed); a larger output is refused before it is parsed.
MAX_PROVIDER_TEXT_BYTES = 64 * 1024
#: JSON nesting deeper than this is refused (the IR's own depth bound, 40, needs about two JSON levels per node). Read on the
#: bounded prefix of an over-size output, so a runaway bracket run is named as such rather than only as too large.
MAX_JSON_DEPTH = 512
#: The most ``verified`` paths :func:`asserted_verified_paths` reports (the walk itself is bounded by the parse limits).
MAX_ASSERTED_PATHS = 256
#: A fence's language tag and the spaces after it.
_LANG_TAIL_RE = re.compile(r"[A-Za-z0-9_+-]*[ \t]*")
#: A run of backticks (a plain character class: it cannot backtrack).
_BACKTICK_RUN_RE = re.compile(r"`+")


class ProviderOutputError(ValueError):
    """The provider's text is not a single JSON object."""


class ProviderOutputTooLarge(ProviderOutputError):
    """The provider's text is larger than the bound it is read under (refused before parsing)."""


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


def _lang_end(text: str, j: int) -> int:
    """The end of the fence's language tag and the spaces after it, from ``j`` (two disjoint character classes matched
    at ``j``: nothing to backtrack)."""
    return _LANG_TAIL_RE.match(text, j).end()  # type: ignore[union-attr]


def _block_body(text: str) -> "str | None":
    """The body of the first fenced block: an opener ("```", a language tag, spaces, a line break) and the first later
    line that starts (after spaces or tabs) with "```". One forward scan: if the first opener has no closer, no later
    opener has one (every closer of a later opener is also after the first one), so the scan stops there."""
    n = len(text)
    p = text.find("```")
    while p >= 0:
        # Within a run of backticks only its last three can open a fence: every earlier "```" is followed by a backtick,
        # which is no language tag, space or line break. Skipping to them keeps a long run to one step.
        run_end = _BACKTICK_RUN_RE.match(text, p).end()  # type: ignore[union-attr]
        p = run_end - 3
        j = _lang_end(text, p + 3)
        if j < n and text[j] == "\r" and j + 1 < n and text[j + 1] == "\n":
            j += 1
        if j < n and text[j] == "\n":
            start = j + 1
            q = text.find("```", start)
            while q >= 0:
                k = q - 1
                while k >= start and text[k] in " \t":
                    k -= 1
                if k >= start and text[k] == "\n":
                    end = k - 1 if k - 1 >= start and text[k - 1] == "\r" else k
                    return text[start:end]
                # only the first "```" of a run of backticks can follow a line break and spaces: skip the rest of the run
                q = text.find("```", _BACKTICK_RUN_RE.match(text, q).end())  # type: ignore[union-attr]
            return None
        p = text.find("```", run_end)
    return None


def _inline_body(text: str) -> "str | None":
    """The body of the first inline fence ("```", a language tag, spaces, then everything up to the next "```")."""
    p = text.find("```")
    if p < 0:
        return None
    j = _lang_end(text, p + 3)
    q = text.find("```", j)
    return text[j:q] if q >= 0 else None


def strip_code_fences(text: str) -> str:
    """Return the body of the first Markdown code fence in ``text``, or ``text`` itself.

    Any prose outside the fence is discarded. Without a fence the text is returned
    unchanged (surrounding whitespace is left for the caller to strip). The fence is found
    by a linear scan (each opener and closer is looked for with ``str.find``), never by a
    regular expression that could backtrack over unclosed openers.
    """
    body = _block_body(text)
    if body is None:
        body = _inline_body(text)
    return text if body is None else body


def _nesting_exceeds(text: str, limit: int) -> bool:
    """Whether JSON brackets outside strings nest deeper than ``limit`` in ``text`` (one linear scan; ``text`` is already
    bounded by the caller)."""
    depth = 0
    in_string = escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return True
        elif ch in "]}" and depth:
            depth -= 1
    return False


def _reject_constant(name: str) -> Any:
    raise ProviderOutputError(f"non-finite JSON constant {name!r} is not allowed")


def parse_json_object(text: str, max_bytes: int = MAX_PROVIDER_TEXT_BYTES) -> dict[str, Any]:
    """Parse ``text`` as exactly one JSON object.

    Raises :class:`ProviderOutputError` when the text is empty, too large
    (:class:`ProviderOutputTooLarge`, before anything is parsed), not valid Unicode text (a
    lone surrogate), not valid JSON, nested too deeply to parse, repeats a key inside an
    object, contains NaN/Infinity, or decodes to something other than an object.
    """
    if not isinstance(text, str):
        raise ProviderOutputError("provider output is not text")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ProviderOutputError("provider output is not valid Unicode text (it holds a lone surrogate)") from None
    if size > max_bytes:
        if _nesting_exceeds(text[:max_bytes], MAX_JSON_DEPTH):
            raise ProviderOutputError(f"provider output nesting is too deep (more than {MAX_JSON_DEPTH} levels), and it exceeds the "
                                      f"{max_bytes}-byte bound")
        raise ProviderOutputTooLarge(f"provider output too large: {size} bytes exceeds the {max_bytes}-byte bound")
    body = strip_code_fences(text).strip()
    if not body:
        raise ProviderOutputError("provider output is empty")
    try:
        obj = json.loads(body, parse_constant=_reject_constant, object_pairs_hook=strict_object_pairs)
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
