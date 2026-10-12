"""How an answer is laid out in lines: part labels, mark annotations, bullets, table rows and the lines one claim
may span (docs/STEM_DESIGN.md, section 4.3, as merged with the generic branch's round-7 reading).

The STEM branches deliver the claims round 7 verified on the generic branch for the same answers, so the rules
that decide where a claim starts and ends are the generic parser's (``branches/generic_parser.py``):

* a line that opens with ``=`` or ``≈`` continues the equation of the line before it; a line that ends on a comma or
  a connective ("..., so") and a soft-wrapped prose line (the next line opens with a lower-case word, neither line is
  working) continue the line before them; every other line break ends a claim, so each line of working, each list
  item, each table row and each result is a claim of its own;
* part labels are structure, not claims: a line that is only a part label with or without its mark allocation
  ("(a) [2]", "(i) [2 marks]", "Part (a) — find — 3 marks", "3.") opens a part and proposes no claim;
* mark annotations ("[1]", "[1 spare]", "[2 marks]", "M1" or "A1" after two spaces, "(M1)") are no part of a
  claim: at the end of a line or of a sentence they are left out of the claim, and a fragment that is nothing else is
  no claim; a table's separator row is furniture.

This module re-states the generic parser's patterns because the STEM package imports nothing from ``branches``
(tests/stem/test_front_end_safety.py); tests/stem/test_layout.py asserts the two sets of patterns are the same. It
only locates furniture in a line: it reads no maths and evaluates nothing.
"""
from __future__ import annotations

import re
from typing import Optional

__all__ = [
    "ANNOTATION_ONLY_RE", "BULLET_RE", "CONNECTIVE_END_RE", "CONTINUATION_RE", "LABEL_ONLY_REST_RE", "MARK_ALLOC", "MARK_CODE", "PART_LEAD_RE",
    "SENT_RE", "SOFT_WRAP_NEXT_RE", "TABLE_ROW_RE", "TABLE_SEPARATOR_RE", "TERMINAL_PUNCT_RE", "TRAILING_ANNOTATION_RE", "annotation_ranges",
    "is_working", "joins_previous", "label_only_rest", "plain_line", "EMPHASIS_RE",
]

ROMAN = r"(?:i{1,3}|iv|vi{0,3}|ix|x)"
#: A part label: "(a)", "a)", "(iii)", "iv)", "(2)", "2.", "2)", "3. a)", "3. (b)".
LABEL_TOKEN = rf"(?:\(\s*(?:[a-h]|{ROMAN}|\d{{1,2}})\s*\)|(?:[a-h]|{ROMAN})\)|\d{{1,2}}[.)](?:\s*(?:\(\s*[a-h]\s*\)|[a-h]\)))?)"
PART_LEAD_RE = re.compile(rf"^\s*(?:(?:part|question|q)\s*)?(?P<label>{LABEL_TOKEN})(?=\s|$)", re.IGNORECASE)
#: A mark allocation: "[2]", "[1 spare]", "[2 marks]", "(3 marks)".
MARK_ALLOC = r"(?:\[\s*\d{1,2}(?:\s*(?:marks?|spare))?\s*\]|\(\s*\d{1,2}\s*marks?\s*\))"
#: What may follow a part label on a label-only line: a command term between dashes and a mark allocation ("— find — 3 marks").
LABEL_ONLY_REST_RE = re.compile(rf"\s*(?:[—–:-]\s*)?(?:[A-Za-z][A-Za-z ]{{0,30}}?\s*[—–-]\s*)?(?:{MARK_ALLOC}|\d{{1,2}}\s*marks?)?\s*[:.]?\s*", re.IGNORECASE)
#: Markscheme codes: "M1", "A1", "R1", "N2", "AG", bare after two spaces or a tab, or in brackets.
MARK_CODE = r"(?:[MARN]\d{1,2}|AG)"
TRAILING_ANNOTATION_RE = re.compile(rf"(?:\s*{MARK_ALLOC}|(?:\s{{2,}}|\t)\(?{MARK_CODE}\)?|\s*\({MARK_CODE}\))+(?=[.;,]?\s*$)")
ANNOTATION_ONLY_RE = re.compile(rf"\s*(?:(?:{MARK_ALLOC}|\(?{MARK_CODE}\)?)\s*)+[.;,]?\s*")
BULLET_RE = re.compile(r"^\s*[-*•–—]\s+")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
#: A sentence ends at ``.``, ``?`` or ``!`` (a closing quotation mark may follow) or at the ``}`` / ``]`` closing a
#: bracket, before a capital, a digit, an opening mark or an opening bracket.
SENT_RE = re.compile(r"(?:(?<=[.?!\]}])|(?<=[.?!][\"”»’]))\s+(?=[A-Z0-9\"'(“‘«„{\[])")
#: A relation or an arithmetic expression: the shape of a line of working.
RELATION_RE = re.compile(r"(?<![=<>!])(?:=|≈|≠|≤|≥|⇒|→|<=|>=)(?!=)|\s[<>]\s")
ARITHMETIC_RE = re.compile(r"\d\s*[×÷*^]\s*[\d($]|\d\s+[+−-]\s+[\d$(]|\d\s*/\s*\d")
TERMINAL_PUNCT_RE = re.compile(r"[.!?…][\"'”’»)\]]*\s*$")
CONTINUATION_RE = re.compile(r"^\s*\$?\s*[=≈]")
CONNECTIVE_END_RE = re.compile(r"(?:,|\b(?:so|and|or|but|then|because|since|that|which|where|whereas|hence|thus|therefore|giving))\s*$", re.IGNORECASE)
SOFT_WRAP_NEXT_RE = re.compile(r"^\s*[a-z][a-z]")
#: Emphasis markers around a stretch of one line (``**...**``, ``__...__``, ``*...*``, ``_..._``), as the shared markdown
#: helper removes them before the generic branch segments an answer (``adapters.markdown.EMPHASIS_RE``, backticks aside:
#: inline code is a span of its own here).
EMPHASIS_RE = re.compile(r"(?<!\w)(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1(?!\w)")
#: Paired double quotation marks of one line (straight, curly, guillemets): a quoted equation is the quoted text's, not working.
_QUOTED_RE = re.compile(r"\"[^\"\n]{1,2000}\"|“[^”\n]{1,2000}”|«[^»\n]{1,2000}»|„[^“”\n]{1,2000}[“”]")
#: How far an annotation is looked for: one line at most this long is scanned (a bound on the work per line).
_MAX_LINE = 20_000


def plain_line(line: str) -> tuple[str, list[int]]:
    """``line`` with its emphasis markers removed (:data:`EMPHASIS_RE`, applied as the markdown helper applies it), and
    the offset in ``line`` of every character kept: what the generic branch reads the line as."""
    out: list[str] = []
    index: list[int] = []
    pos = 0
    for m in EMPHASIS_RE.finditer(line):
        out.append(line[pos:m.start()])
        index.extend(range(pos, m.start()))
        out.append(m.group(2))
        index.extend(range(m.start(2), m.end(2)))
        pos = m.end()
    out.append(line[pos:])
    index.extend(range(pos, len(line)))
    return "".join(out), index


def _mask_quoted(line: str) -> str:
    return _QUOTED_RE.sub(lambda m: " " * len(m.group(0)), line)


def is_working(line: str) -> bool:
    """A line (quoted spans aside) that holds a relation or an arithmetic expression."""
    masked = _mask_quoted(line)
    return bool(RELATION_RE.search(masked) or ARITHMETIC_RE.search(masked))


def strip_trailing_annotations(text: str) -> str:
    return TRAILING_ANNOTATION_RE.sub("", text).rstrip()


def joins_previous(prev: str, line: str) -> bool:
    """True when the physical ``line`` continues the logical line ``prev`` (both with their mark annotations and
    markup removed): an equation continued on a line that opens with ``=`` or ``≈``, a line after one that ends on a
    comma or a connective, or a soft-wrapped prose line. A part lead, a bullet or a table row never continues a line."""
    if PART_LEAD_RE.match(line) or BULLET_RE.match(line) or TABLE_ROW_RE.match(line):
        return False
    if CONTINUATION_RE.match(line):
        return True
    if CONNECTIVE_END_RE.search(strip_trailing_annotations(prev)) and not TABLE_ROW_RE.match(prev):
        return True
    return bool(SOFT_WRAP_NEXT_RE.match(line) and not TERMINAL_PUNCT_RE.search(prev.rstrip(":;")) and not prev.rstrip().endswith((":", ";"))
                and not is_working(prev) and not is_working(line))


def label_only_rest(line: str) -> Optional[int]:
    """When ``line`` (markup removed) opens with a part label and holds nothing else but its mark allocation (and a
    command term between dashes), the offset where the label's rest starts; None otherwise."""
    m = PART_LEAD_RE.match(line)
    if m is None:
        return None
    return m.end() if LABEL_ONLY_REST_RE.fullmatch(line[m.end():]) else None


def _sentence_spans(line: str) -> list[tuple[int, int]]:
    """``(start, end)`` of the sentences of one line as the generic parser cuts them (:data:`SENT_RE`)."""
    out: list[tuple[int, int]] = []
    pos = 0
    for m in SENT_RE.finditer(line):
        out.append((pos, m.start()))
        pos = m.end()
    out.append((pos, len(line)))
    return [(a, b) for a, b in out if line[a:b].strip()]


def annotation_ranges(line: str) -> list[tuple[int, int]]:
    """Offsets (in ``line``) of the mark annotations the generic parser leaves out of claims: those closing the line,
    those closing one of its sentences (before the sentence's final ``.``, ``;`` or ``,``), and sentences that are
    nothing but annotations. Each range covers the whitespace before the annotation, as the generic parser removes it."""
    if not line or len(line) > _MAX_LINE or not any(ch in line for ch in "[(MARNG"):
        return []
    out: list[tuple[int, int]] = []
    for a, b in _sentence_spans(line):
        sent = line[a:b]
        if ANNOTATION_ONLY_RE.fullmatch(sent):
            k = a
            while k > 0 and line[k - 1] in " \t":
                k -= 1
            out.append((k, b))
            continue
        m = TRAILING_ANNOTATION_RE.search(sent)
        if m is not None and m.end() > m.start():
            out.append((a + m.start(), a + m.end()))
    m = TRAILING_ANNOTATION_RE.search(line)
    if m is not None and m.end() > m.start():
        out.append((m.start(), m.end()))
    out.sort()
    merged: list[tuple[int, int]] = []
    for a, b in out:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged
