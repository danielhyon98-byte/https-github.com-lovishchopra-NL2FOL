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
    "strip_trailing_annotations", "trailing_annotation_span",
    "is_working", "joins_previous", "label_only_rest", "plain_line", "EMPHASIS_RE", "emphasis_spans",
]

ROMAN = r"(?:i{1,3}|iv|vi{0,3}|ix|x)"
#: A part label: "(a)", "a)", "(iii)", "iv)", "(2)", "2.", "2)", "3. a)", "3. (b)".
LABEL_TOKEN = rf"(?:\(\s*(?:[a-h]|{ROMAN}|\d{{1,2}})\s*\)|(?:[a-h]|{ROMAN})\)|\d{{1,2}}[.)](?:\s*(?:\(\s*[a-h]\s*\)|[a-h]\)))?)"
PART_LEAD_RE = re.compile(rf"^\s*(?:(?:part|question|q)\s*)?(?P<label>{LABEL_TOKEN})(?=\s|$)", re.IGNORECASE)
#: A mark allocation: "[2]", "[1 spare]", "[2 marks]", "(3 marks)".
MARK_ALLOC = r"(?:\[\s*\d{1,2}(?:\s*(?:marks?|spare))?\s*\]|\(\s*\d{1,2}\s*marks?\s*\))"
#: What may follow a part label on a label-only line: a command term between dashes and a mark allocation ("— find — 3 marks").
#: Its blank runs are read possessively (rule linear-readers, integration gate 1): each run of blanks stands between two
#: parts that open with a character no blank reads (a dash, a letter, a bracket, a digit, a stop), so whichever ``\s*`` of
#: the written pattern took a run, the full match took all of it, and the same strings match. As written, a label followed
#: by a long run of blanks and a word tried every split of the run among its four ``\s*``: cubic ('(a)' + 800 blanks + 'x':
#: 0.67 s). The generic parser holds the same pattern (tests/stem/test_layout.py).
LABEL_ONLY_REST_RE = re.compile(rf"\s*+(?:[—–:-]\s*+)?(?:[A-Za-z][A-Za-z ]{{0,30}}?\s*+[—–-]\s*+)?(?:{MARK_ALLOC}|\d{{1,2}}\s*+marks?)?\s*+[:.]?\s*+", re.IGNORECASE)
#: Markscheme codes: "M1", "A1", "R1", "N2", "AG", bare after two spaces or a tab, or in brackets.
MARK_CODE = r"(?:[MARN]\d{1,2}|AG)"
TRAILING_ANNOTATION_RE = re.compile(rf"(?:\s*{MARK_ALLOC}|(?:\s{{2,}}|\t)\(?{MARK_CODE}\)?|\s*\({MARK_CODE}\))+(?=[.;,]?\s*$)")
#: Rule linear-readers (integration gate 1): :data:`TRAILING_ANNOTATION_RE` searched as written restarts at every annotation
#: and every blank of a run and re-reads the rest of the run, so a line of n annotations that ends no sentence cost n² steps.
#: This pattern finds a maximal run of the same annotations once: it starts only where no blank precedes it (a run that can
#: start inside a blank run can start at its first character, which a search reaches first), its blanks are taken
#: possessively and the run atomically. Each annotation ends on a character the lookahead cannot read (a bracket, a digit,
#: the G of "AG"), so the pattern can match only a whole maximal run, and only when :data:`_ANNOTATION_TAIL_RE` holds at its
#: end; :func:`trailing_annotation_span` gives the same span as the search (a test holds them equal).
_ANNOTATION_RUN_RE = re.compile(rf"(?<!\s)(?>(?:\s*+{MARK_ALLOC}|(?:\s{{2,}}+|\t)\(?{MARK_CODE}\)?|\s*+\({MARK_CODE}\))+)")
#: The lookahead of :data:`TRAILING_ANNOTATION_RE`: what may follow the run (a closing mark, blanks, the end).
_ANNOTATION_TAIL_RE = re.compile(r"[.;,]?\s*$")
ANNOTATION_ONLY_RE = re.compile(rf"\s*(?:(?:{MARK_ALLOC}|\(?{MARK_CODE}\)?)\s*)+[.;,]?\s*")
BULLET_RE = re.compile(r"^\s*[-*•–—]\s+")
#: Blank and dash runs read possessively, the cells atomically (rule linear-readers): the same lines match (a blank run is
#: followed by a bar, a colon, a dash or the end; a dash run by a colon, a blank, a bar or the end), and a line of many blanks
#: or dashes that is no separator no longer tries every split of its runs (quadratic as written: 0.98 s at 8,000 blanks).
TABLE_SEPARATOR_RE = re.compile(r"^\s*+\|?\s*+:?-{2,}+:?\s*+(?:\|\s*+:?-{2,}+:?\s*+)*+\|?\s*+$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
#: A sentence ends at ``.``, ``?`` or ``!`` (a closing quotation mark may follow) or at the ``}`` / ``]`` closing a
#: bracket, before a capital, a digit, an opening mark or an opening bracket.
SENT_RE = re.compile(r"(?:(?<=[.?!\]}])|(?<=[.?!][\"”»’]))\s+(?=[A-Z0-9\"'(“‘«„{\[])")
#: A relation or an arithmetic expression: the shape of a line of working.
RELATION_RE = re.compile(r"(?<![=<>!])(?:=|≈|≠|≤|≥|⇒|→|<=|>=)(?!=)|\s[<>]\s")
ARITHMETIC_RE = re.compile(r"\d\s*[×÷*^]\s*[\d($]|\d\s+[+−-]\s+[\d$(]|\d\s*/\s*\d")
TERMINAL_PUNCT_RE = re.compile(r"[.!?…][\"'”’»)\]]*\s*$")
#: Blank runs read possessively (rule linear-readers): the same lines match (only blanks, and a dollar sign, stand before the
#: sign), and a line opening with many blanks no longer tries every split of them between the two ``\s*`` (quadratic as
#: written: 0.60 s at 8,000 blanks, once per line).
CONTINUATION_RE = re.compile(r"^\s*+\$?\s*+[=≈]")
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


#: The markers :data:`EMPHASIS_RE` tries at a position, in its alternation's order.
_EMPHASIS_MARKERS = ("**", "__", "*", "_")


def _is_word_char(ch: str) -> bool:
    """``\\w`` of a str pattern: a letter, a digit or a numeric character of any script, or the underscore."""
    return ch.isalnum() or ch == "_"


def emphasis_spans(line: str) -> list[tuple[int, int, int, int]]:
    """``(start, body start, body end, end)`` of every match of ``EMPHASIS_RE.finditer(line)``, found in one pass.

    The pattern's lazy body reads to the end of the line from every opener that has no closer, so a line of n openers with
    none closed (``'**a ' * k``) cost n² steps (integration gate 1, parser-safety-5). Whether a marker closes an emphasis
    does not depend on where the emphasis opened: it is preceded by a non-blank and followed by no word character. So the
    closers of each marker are found once, and an opener takes the first closer of its marker after its first body
    character and before the next line break (the body reads no line break), which is where the lazy body stops. Openers
    are tried in the pattern's order at each position the search reaches (none inside a match already made), so the
    matches are the pattern's, offset for offset (tests/stem/test_integration_gate1_handoff.py holds them equal)."""
    if "*" not in line and "_" not in line:
        return []
    n = len(line)
    closers: dict[str, list[int]] = {}
    for marker in _EMPHASIS_MARKERS:
        found: list[int] = []
        at = line.find(marker, 1)
        while at >= 0:
            end = at + len(marker)
            if not line[at - 1].isspace() and (end == n or not _is_word_char(line[end])):
                found.append(at)
            at = line.find(marker, at + 1)
        closers[marker] = found
    cursor = dict.fromkeys(_EMPHASIS_MARKERS, 0)
    breaks = [k for k, ch in enumerate(line) if ch == "\n"]
    nb = 0  # the first line break at or after the body being read (bodies only move right)
    out: list[tuple[int, int, int, int]] = []
    i = 0
    while i < n:
        if line[i] not in "*_" or (i and _is_word_char(line[i - 1])):
            i += 1
            continue
        for marker in _EMPHASIS_MARKERS:
            body = i + len(marker)
            if not line.startswith(marker, i) or body >= n or line[body].isspace():
                continue
            found, k = closers[marker], cursor[marker]
            while k < len(found) and found[k] < body + 1:  # positions only grow, so each list is read once
                k += 1
            cursor[marker] = k
            while nb < len(breaks) and breaks[nb] < body:
                nb += 1
            if k < len(found) and (nb == len(breaks) or found[k] < breaks[nb]):
                out.append((i, body, found[k], found[k] + len(marker)))
                i = found[k] + len(marker)
                break
        else:
            i += 1
    return out


def plain_line(line: str) -> tuple[str, list[int]]:
    """``line`` with its emphasis markers removed (:data:`EMPHASIS_RE`, applied as the markdown helper applies it, read in
    one pass by :func:`emphasis_spans`), and the offset in ``line`` of every character kept: what the generic branch reads
    the line as."""
    out: list[str] = []
    index: list[int] = []
    pos = 0
    for start, body, body_end, end in emphasis_spans(line):
        out.append(line[pos:start])
        index.extend(range(pos, start))
        out.append(line[body:body_end])
        index.extend(range(body, body_end))
        pos = end
    out.append(line[pos:])
    index.extend(range(pos, len(line)))
    return "".join(out), index


def _mask_quoted(line: str) -> str:
    return _QUOTED_RE.sub(lambda m: " " * len(m.group(0)), line)


def is_working(line: str) -> bool:
    """A line (quoted spans aside) that holds a relation or an arithmetic expression."""
    masked = _mask_quoted(line)
    return bool(RELATION_RE.search(masked) or ARITHMETIC_RE.search(masked))


def trailing_annotation_span(text: str) -> Optional[tuple[int, int]]:
    """The span of ``TRAILING_ANNOTATION_RE.search(text)`` (None when it finds none), read in linear time: each maximal run
    of annotations is found once and the pattern's lookahead tested at its end (rule linear-readers)."""
    if not text or not any(ch in text for ch in "[(MARNG"):
        return None
    for m in _ANNOTATION_RUN_RE.finditer(text):
        if _ANNOTATION_TAIL_RE.match(text, m.end()):
            return m.start(), m.end()
    return None


def strip_trailing_annotations(text: str) -> str:
    """``TRAILING_ANNOTATION_RE.sub("", text).rstrip()``, in linear time. The pattern matches at most once in a text (a
    match is followed by nothing but a closing mark and blanks), so the substitution removes :func:`trailing_annotation_span`."""
    span = trailing_annotation_span(text)
    if span is not None:
        text = text[:span[0]] + text[span[1]:]
    return text.rstrip()


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
        span = trailing_annotation_span(sent)  # TRAILING_ANNOTATION_RE.search(sent), linear
        if span is not None and span[1] > span[0]:
            out.append((a + span[0], a + span[1]))
    span = trailing_annotation_span(line)
    if span is not None and span[1] > span[0]:
        out.append(span)
    out.sort()
    merged: list[tuple[int, int]] = []
    for a, b in out:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged
