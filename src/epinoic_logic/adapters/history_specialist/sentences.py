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
  follows the point.

``split_sentences`` is the parser's reading (the next sentence must open with a capital,
a digit or an opening mark); ``split_clauses`` is the arithmetic extractor's reading
(clauses after ``;`` are separate statements and the next character is unconstrained).
``strip_json_spans`` removes brace-balanced JSON fragments pasted into prose so their
strings are never read as quotations.
"""
from __future__ import annotations

import re

from ..markdown import DOUBLE_QUOTE_MARKS, JSON_KEY_RE, find_quotation_spans, is_json_block

__all__ = ["ABBREVIATIONS", "is_abbreviation_before", "sentence_boundaries", "split_clauses", "split_sentences", "strip_json_spans"]

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


def is_abbreviation_before(prefix: str) -> bool:
    """True when ``prefix`` (the text up to and including a full stop) ends in an
    abbreviation or a single-letter initial, so the stop is not a sentence end."""
    stripped = prefix.rstrip(_CLOSERS)
    if not stripped.endswith("."):
        return False
    m = _LAST_WORD_RE.search(stripped)
    if m is None:
        return False
    word = m.group(1)
    if len(word) == 1:
        return True  # an initial ('A. J. P.'), 'c.', 'p.'
    return word.lower() in ABBREVIATIONS


def _quotation_spans(text: str) -> list[tuple[int, int]]:
    if not any(ch in text for ch in DOUBLE_QUOTE_MARKS) and "'" not in text and "‘" not in text:
        return []
    return [(s, e) for s, e, _inner in find_quotation_spans(text)]


def sentence_boundaries(text: str, *, semicolons: bool = False, capital_next: bool = True) -> list[int]:
    """Offsets in ``text`` at which a new sentence (or, with ``semicolons``, a new
    clause) starts. A boundary inside a quotation is ignored, as is one after an
    abbreviation or initial; with ``capital_next`` the next sentence must open with a
    capital, a digit or an opening mark."""
    spans = _quotation_spans(text)
    out: list[int] = []
    pattern = re.compile(rf"[.?!;]+[{_CLOSERS}]*(?=\s+\S)") if semicolons else _END_RE
    for m in pattern.finditer(text):
        if any(s < m.start() and m.end() < e for s, e in spans):
            continue
        if m.group(0)[0] != ";" and is_abbreviation_before(text[: m.end()]):
            continue
        nxt = _WS_RE.match(text, m.end())
        start = nxt.end() if nxt else m.end()
        if start >= len(text):
            continue
        if capital_next and m.group(0)[0] != ";" and not _STARTS_SENTENCE_RE.match(text, start):
            continue
        out.append(start)
    for m in _JSON_END_RE.finditer(text):
        if any(s < m.start() and m.end() < e for s, e in spans):
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
    year ``[1788]``, prose braces) is kept. Returns ``(text, number_removed)``."""
    out: list[str] = []
    i, removed = 0, 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "{[":
            end = _balanced_end(text, i)
            if end is not None and JSON_KEY_RE.search(text[i:end]) and is_json_block(text[i:end]):
                removed += 1
                i = end
                continue
        out.append(ch)
        i += 1
    return "".join(out), removed


def _balanced_end(text: str, start: int) -> "int | None":
    """Offset just past the bracket matching ``text[start]``, skipping JSON strings; None when unbalanced."""
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
