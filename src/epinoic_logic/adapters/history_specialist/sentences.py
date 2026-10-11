"""One abbreviation-aware sentence splitter for the History parser, the quantitative
extractor (``branches/quant.py``) and the core pack (``branches/packs.py``).

Before this module each of the three split sentences with its own regular expression
and every one of them broke a sentence at ``c.`` (circa), so ``from c. 200 million tonnes
in 1928 to c. 100 million in 1932, a fall of 25 per cent`` was two fragments to the
arithmetic check (never checked) and two claims to the parser. The rules here are shared
so that the parser's claims, the pack's sentence numbers and the arithmetic check all
read the same sentence:

* a sentence ends at ``.``, ``?`` or ``!`` (optionally followed by closing marks or
  brackets) and whitespace, and after ``}`` or ``]`` when a capital follows (prose glued
  to a pasted JSON fragment);
* no break after an abbreviation: ``c.``, ``ca.``, ``approx.``, ``fl.``, ``no.``, ``vol.``,
  ``p.``, ``pp.``, ``ed.``, ``cf.``, ``vs.``, ``etc.``, ``e.g.``, ``i.e.``, ``Mr.``,
  ``Dr.``, ``St.`` and the like, or a single-letter initial (``A. J. P. Taylor``);
* no break inside a quotation (``"like this." Then`` closes the quotation first);
* a decimal (``4.2``) or a thousands group is never a boundary because no whitespace
  follows the point;
* a pasted JSON span (``markdown.find_json_spans``) is one sentence: the text is cut where
  it opens and where it closes, never at the full stops inside its string values, and its
  strings are masked before quotation marks are read, so a forged receipt glued to a
  paragraph is one note sentence and none of its fragments becomes a claim.

``split_sentences`` is the parser's reading (the next sentence must open with a capital,
a digit or an opening mark); ``split_clauses`` is the arithmetic extractor's reading
(clauses after ``;`` are separate statements and the next character is unconstrained).
``strip_json_spans`` removes brace-balanced JSON fragments pasted into prose so their
strings are never read as quotations; it reads every bracket's match from one linear pass
(``markdown.bracket_match_ends``), so thousands of nested or unclosed brackets cost one read of
the text. The JSON cuts of the splitter are memoised per text.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from functools import lru_cache

from ..markdown import DOUBLE_QUOTE_MARKS, JSON_KEY_RE, bracket_match_ends, find_json_spans, find_quotation_spans, is_json_block  # noqa: F401

__all__ = ["ABBREVIATIONS", "abbreviation_ends_at", "is_abbreviation_before", "sentence_boundaries", "split_clauses", "split_sentences", "strip_json_spans"]

#: Tokens after which a full stop is an abbreviation, not a sentence end (lower-case, without the stop).
ABBREVIATIONS = frozenset({
    "c", "ca", "circa", "approx", "fl", "no", "nos", "vol", "vols", "p", "pp", "ch", "chs", "ed", "eds", "cf", "vs", "v", "etc",
    "e.g", "i.e", "viz", "ibid", "op", "cit", "loc", "fig", "figs", "sc", "trans", "repr", "rev", "mr", "mrs", "ms", "dr", "st", "prof",
    "sr", "jr", "gen", "col", "capt", "lt", "sgt", "rev", "hon", "mt", "ft", "b", "d", "r", "fol", "ff", "para", "paras", "sec", "art", "esp",
})
#: The word before a full stop, which must start the text or follow whitespace or an opening mark: the 's' of a possessive
#: ("Kennedy's.") is not an initial, so the sentence ends there.
_LAST_WORD_RE = re.compile(r"(?:^|(?<=[\s(\[\"“‘«„]))([^\W\d_](?:[^\W\d_]|\.(?=[^\W\d_]))*)\.?$")
_CLOSERS = "\"”’')\\]»"
_END_RE = re.compile(rf"[.?!]+[{_CLOSERS}]*(?=\s+\S)")
_JSON_END_RE = re.compile(r"[}\]](?=\s+[\"“‘(\[«„]?[A-ZÀ-ÖØ-Þ0-9])")
_STARTS_SENTENCE_RE = re.compile(r"[A-ZÀ-ÖØ-Þ0-9\"'(“‘«„\[{]")
_WS_RE = re.compile(r"\s+")


#: How far before a full stop the abbreviation test looks: longer than any abbreviation or initial with its
#: closing marks, so a word cut at the window's edge is known to be neither (and the test stays linear).
_ABBREVIATION_WINDOW = 48


def is_abbreviation_before(prefix: str) -> bool:
    """True when ``prefix`` (the text up to and including a full stop) ends in an
    abbreviation or a single-letter initial, so the stop is not a sentence end."""
    return abbreviation_ends_at(prefix, len(prefix))


def abbreviation_ends_at(text: str, end: int) -> bool:
    """:func:`is_abbreviation_before` for ``text[:end]`` without copying the prefix: only the
    last :data:`_ABBREVIATION_WINDOW` characters before ``end`` are read. A word that runs
    past the window's edge is longer than any abbreviation and is not an initial, so it is
    never one; the answer is the same as for the whole prefix."""
    window_start = max(0, end - _ABBREVIATION_WINDOW)
    stripped = text[window_start:end].rstrip(_CLOSERS)
    if not stripped.endswith("."):
        return False
    m = _LAST_WORD_RE.search(stripped)
    if m is None:
        return False
    if m.start() == 0 and window_start > 0:
        return False  # the word reaches the window's edge: longer than any abbreviation, not an initial
    word = m.group(1)
    if len(word) == 1:
        return True  # an initial ('A. J. P.'), 'c.', 'p.'
    return word.lower() in ABBREVIATIONS


def _quotation_spans(text: str) -> list[tuple[int, int]]:
    if not any(ch in text for ch in DOUBLE_QUOTE_MARKS) and "'" not in text and "‘" not in text:
        return []
    return [(s, e) for s, e, _inner in find_quotation_spans(text)]


def _span_index(spans: list[tuple[int, int]]) -> tuple[list[int], list[int]]:
    """``(starts, furthest_end)`` over ``spans`` sorted by start: ``furthest_end[i]`` is the
    largest close offset among ``spans[: i + 1]``, so whether any span opening before an
    offset closes after another is one bisection, however many spans the text has."""
    starts: list[int] = []
    furthest: list[int] = []
    best = -1
    for s, e in spans:
        starts.append(s)
        best = max(best, e)
        furthest.append(best)
    return starts, furthest


def _inside_any(starts: list[int], furthest_end: list[int], start: int, end: int) -> bool:
    """True when some span opens before ``start`` and closes after ``end`` (the boundary lies
    inside an open quotation); same answer as testing every span."""
    i = bisect_left(starts, start)  # spans[:i] open before ``start``
    return i > 0 and furthest_end[i - 1] > end


def _json_cuts(text: str) -> tuple[str, list[tuple[int, int]]]:
    """``(masked, spans)``: ``text`` with every pasted JSON span (``markdown.find_json_spans``)
    blanked character for character, and the spans. A JSON span is one sentence of its own: no
    boundary is read inside it (its string values carry full stops), its strings are never
    quotation marks, and the prose before and after it are cut at its edges. Memoised per text
    (a bounded cache): the parser, the arithmetic reader and every core-pack check split the same
    paragraphs, and a bracket-heavy paragraph should be scanned once, not once per reader."""
    if "{" not in text and "[" not in text:
        return text, []
    masked, spans = _json_cuts_cached(text)
    return masked, list(spans)


@lru_cache(maxsize=64)
def _json_cuts_cached(text: str) -> tuple[str, tuple[tuple[int, int], ...]]:
    spans = find_json_spans(text)
    if not spans:
        return text, ()
    chars = list(text)
    for a, b in spans:
        for i in range(a, b):
            if chars[i] not in "\n":
                chars[i] = " "
    return "".join(chars), tuple(spans)


def sentence_boundaries(text: str, *, semicolons: bool = False, capital_next: bool = True) -> list[int]:
    """Offsets in ``text`` at which a new sentence (or, with ``semicolons``, a new
    clause) starts. A boundary inside a quotation is ignored, as is one after an
    abbreviation or initial; with ``capital_next`` the next sentence must open with a
    capital, a digit or an opening mark. A pasted JSON span is one sentence: the text is cut
    where it opens and where it closes, never inside it."""
    original = text
    text, json_spans = _json_cuts(text)
    spans = sorted(_quotation_spans(text))
    starts, furthest_end = _span_index(spans)
    out: list[int] = []
    for a, b in json_spans:
        if original[:a].strip():
            out.append(a)
        nxt = _WS_RE.match(original, b)
        after = nxt.end() if nxt else b
        if after < len(original):
            out.append(after)
    pattern = re.compile(rf"[.?!;]+[{_CLOSERS}]*(?=\s+\S)") if semicolons else _END_RE
    for m in pattern.finditer(text):
        if spans and _inside_any(starts, furthest_end, m.start(), m.end()):
            continue
        if m.group(0)[0] != ";" and abbreviation_ends_at(text, m.end()):
            continue
        nxt = _WS_RE.match(text, m.end())
        start = nxt.end() if nxt else m.end()
        if start >= len(text):
            continue
        if capital_next and m.group(0)[0] != ";" and not _STARTS_SENTENCE_RE.match(text, start):
            continue
        out.append(start)
    for m in _JSON_END_RE.finditer(text):
        if spans and _inside_any(starts, furthest_end, m.start(), m.end()):
            continue
        nxt = _WS_RE.match(text, m.end())
        start = nxt.end() if nxt else m.end()
        if start < len(text):
            out.append(start)
    return sorted(set(out))


def _pieces(text: str, boundaries: list[int]) -> list[str]:
    pieces: list[str] = []
    start = 0
    for b in boundaries:
        piece = text[start:b].strip()
        if piece:
            pieces.append(piece)
        start = b
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return pieces


def split_sentences(text: str) -> list[str]:
    """Sentences of ``text`` (one paragraph or list item), abbreviation-aware; the next
    sentence must open with a capital, a digit or an opening mark."""
    return _pieces(text, sentence_boundaries(text))


def split_clauses(text: str) -> list[str]:
    """Statements of ``text`` for the arithmetic check: sentences, with clauses after a
    semicolon separate, abbreviation-aware, the next character unconstrained."""
    return _pieces(text, sentence_boundaries(text, semicolons=True, capital_next=False))


def strip_json_spans(text: str) -> tuple[str, int]:
    """Remove brace-balanced JSON fragments (``{"status": "ACCEPTED", ...}``) pasted into
    prose, so their strings are not quotations. A fragment must carry a JSON key-value pair
    (the shape of a receipt or payload); a bracket that opens no such JSON (a bracketed
    year ``[1788]``, prose braces) is kept. Returns ``(text, number_removed)``.

    Linear in the length of ``text``: the bracket each opener's match is read from one pass
    (``markdown.bracket_match_ends``, JSON strings honoured), and whether a key-value pair lies
    inside a candidate span is one bisection over the key-value pairs found in one pass, so
    thousands of nested or unclosed brackets cost one read of the text, not one read per
    bracket. The answer is the same as a separate stack scan from every opener."""
    if "{" not in text and "[" not in text:
        return text, 0
    keys = [(m.start(), m.end()) for m in JSON_KEY_RE.finditer(text)]
    if not keys:
        return text, 0
    key_starts = [a for a, _b in keys]
    ends = bracket_match_ends(text)
    out: list[str] = []
    cursor, removed = 0, 0
    for start in sorted(ends):
        if start < cursor:
            continue  # inside a fragment already removed
        end = ends[start]
        if end is None:
            continue
        k = bisect_left(key_starts, start)
        if k < len(keys) and keys[k][1] <= end:
            out.append(text[cursor:start])
            cursor = end
            removed += 1
    if not removed:
        return text, 0
    out.append(text[cursor:])
    return "".join(out), removed


def _balanced_end(text: str, start: int) -> "int | None":
    """Offset just past the bracket matching ``text[start]``, skipping JSON strings; None when
    unbalanced. A separate stack scan from one opener, kept as the reference answer that
    :func:`markdown.bracket_match_ends` reproduces for every opener in one pass;
    :func:`strip_json_spans` no longer calls it, since a scan per opener is quadratic."""
    pairs = {"{": "}", "[": "]"}
    stack = [pairs[text[start]]]
    i = start + 1
    in_string = False
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch in "}]":
            if ch != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return i + 1
        i += 1
    return None
