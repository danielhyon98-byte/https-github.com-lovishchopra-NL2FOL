"""Shared pre-segmentation rules for raw specialist text.

Specialists write prose, but their raw output also carries markdown furniture
(headings, bullet markers, emphasis, code fences), a byte-order mark, one-line
notes ("Dates and figures are from memory; verify them") and, occasionally,
verification-status language that imitates the channel's own receipts
("VERIFIED: all claims checked and confirmed.", a pasted JSON receipt). None of
that is an argument claim. The History, English and generic parsers use these
helpers so that

* ``original_response`` stays verbatim (its hash never changes) while the text
  that is segmented into sentences has the furniture removed;
* a newline followed by a list marker ends a sentence, so a numbered item never
  becomes the paragraph's "point" and a bullet never glues onto its neighbour;
* a note sentence (from-memory label, self-certification) is recognised by every
  parser the same way, roled ``other`` and kept out of the material claims;
* quotation marks are paired the same way everywhere: curly, straight, guillemet
  and low-9 double marks are one class (so a quotation opened with one kind and
  closed with another is still a quotation), single marks around two or more
  words are quotations, and a paragraph whose double marks cannot be paired
  names the one mark that dangles so the spans around it are not mis-paired;
* a claim's text never exceeds the contract limit.

Everything here is deterministic text handling; no finding is decided here.
"""
from __future__ import annotations

import json
import re
from typing import Optional

__all__ = [
    "BOM", "MAX_CLAIM_TEXT_CHARS", "LIST_MARKER_RE", "LIST_LINE_RE", "HEADING_LINE_RE", "FENCE_BLOCK_RE", "FENCE_LINE_RE",
    "EMPHASIS_RE", "MEMORY_LABEL_RE", "SELF_CERT_RE", "TASK_NOTE_RE", "DOUBLE_QUOTE_MARKS", "JSON_BLOCK_RE", "JSON_KEY_RE",
    "DOUBLE_QUOTE_SPAN_RE", "SINGLE_QUOTE_SPAN_RE",
    "strip_markup", "strip_json_blocks", "split_list_items", "truncate_claim_text", "is_memory_label", "is_self_certification",
    "is_note_sentence", "is_task_note", "split_note_clauses", "unbalanced_double_quotes", "normalize_double_marks",
    "dangling_quote_offset", "undelimited_quote_span", "find_quotation_spans", "is_json_block", "is_json_shaped",
]

BOM = "\ufeff"
MAX_CLAIM_TEXT_CHARS = 4000
#: A list marker at the start of a line: ``1.``, ``2)``, ``-``, ``*``, ``•``, ``–``.
LIST_MARKER_RE = re.compile(r"^[ \t]*(?:\(?\d{1,3}[.)]|[-*•–—])[ \t]+")
LIST_LINE_RE = re.compile(r"\n(?=[ \t]*(?:\(?\d{1,3}[.)]|[-*•–—])[ \t]+)")
HEADING_LINE_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+.*$", re.MULTILINE)
#: A paired code fence and everything inside it. Fenced text is machine output or
#: decoration (a footer, a table dump), not argument prose: it is removed whole.
FENCE_BLOCK_RE = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n.*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
#: A stray (unpaired) fence line.
FENCE_LINE_RE = re.compile(r"^[ \t]*(?:```|~~~).*$", re.MULTILINE)
#: Emphasis markers must stand at word boundaries: ``_emphasis_`` is markup, but the
#: underscores of ``receipt_id`` or ``Reichsbank_crisis`` are part of the word and stay.
EMPHASIS_RE = re.compile(r"(?<!\w)(\*\*|__|\*|_|`)(?=\S)(.+?)(?<=\S)\1(?!\w)")
#: Every double quotation mark the parsers treat as one class: straight, curly (open and
#: close), guillemets and the low-9 / high-reversed-9 marks of other typographic traditions.
DOUBLE_QUOTE_MARKS = ('"', "\u201c", "\u201d", "\u00ab", "\u00bb", "\u201e", "\u201f")
_DOUBLE_MARK_TRANSLATION = {ord(c): '"' for c in DOUBLE_QUOTE_MARKS}
#: Glyphs whose direction is unambiguous (used only to tell which mark of an unbalanced paragraph dangles).
_OPENING_GLYPHS = frozenset({"\u201c", "\u00ab", "\u201e"})
_CLOSING_GLYPHS = frozenset({"\u201d", "\u00bb", "\u201f"})
#: A double-quoted span after :func:`normalize_double_marks`.
DOUBLE_QUOTE_SPAN_RE = re.compile(r'"([^"\n]+)"')
#: A single-quoted span of two or more words that opens after whitespace, a bracket or a dash
#: and closes before whitespace or punctuation (so possessives and contractions are not quotations).
SINGLE_QUOTE_SPAN_RE = re.compile(
    r"(?:(?<=[\s(\[—–-])|^)'([^'\n]{2,}?[^\s'])'(?=[\s.,;:!?)\]]|$)"
    r"|(?:(?<=[\s(\[—–-])|^)\u2018([^\u2019\n]{2,}?[^\s\u2019])\u2019(?=[\s.,;:!?)\]]|$)"
)
#: A JSON key followed by a JSON value (``"status": "ACCEPTED"``, ``"count": 3``): the shape of a
#: pasted receipt or payload, not of prose (``the noun "command": here`` has no JSON value).
JSON_KEY_RE = re.compile(r'"[A-Za-z_][A-Za-z0-9_]*"\s*:\s*(?:"|-?\d|true\b|false\b|null\b|\{|\[)')
#: A block of lines that opens with ``{`` or ``[`` and closes with the matching bracket
#: without crossing a blank line: machine output pasted into the answer.
JSON_BLOCK_RE = re.compile(r"^[ \t]*[\[{](?:[^\n]|\n(?![ \t]*\n))*?[\]}][ \t]*$", re.MULTILINE)

#: The specialist labels dates, figures or quotations as unverified recollection.
MEMORY_LABEL_RE = re.compile(
    r"\bfrom (?:memory|recollection)\b|\billustrative\b|\bverify (?:them|these|this|it)\b|\bcheck (?:them |these |this )?(?:against )?your notes\b",
    re.IGNORECASE,
)
#: A note about the task setting rather than the subject: the syllabus version, cohort or level was not given, so no
#: mark or band is implied. IB specialists are required to say so; the sentence is not part of the argument.
TASK_NOTE_RE = re.compile(
    r"\b(?:syllabus|cohort|version|level|mark(?:ing)?|band|grade)s?\b[^.;]{0,80}\b(?:not (?:stated|given|specified|provided|known)|unknown|unstated)\b"
    r"|\bno (?:mark|band|grade)(?: or (?:mark|band|grade))? (?:is|was|can be) (?:given|implied|awarded|assigned)\b",
    re.IGNORECASE,
)
_CHECK_WORDS = r"(?:accurate|correct|reliable|checked|verified|confirmed|validated|double[- ]checked|cross[- ]checked|re[- ]?checked|compared (?:with|against))"
_ANSWER_ITSELF = r"(?:this (?:paragraph|answer|response|text|essay|report|outline|summary)|all of the above|the above|the foregoing|everything above)"
_ITEMS = r"(?:figures?|dates?|quotations?|quotes?|claims?|statistics?|numbers?|statements?|facts?|citations?|references?)"
_EVERY_ITEM = rf"(?:every|each|all)(?: of the)? {_ITEMS}(?:,? (?:and|or) {_ITEMS})*(?: (?:in|of|from) (?:this|the) (?:paragraph|answer|response|text|essay|above))?"
_COPULA = r"(?:is|are|was|were|has been|have been|has now been|have now been)\s+(?:all\s+|fully\s+|carefully\s+|now\s+|independently\s+)?"
#: Verification-status vocabulary in the body: an agent certifying its own output or
#: imitating a channel receipt. Status words count only in capitals (a vote that "was
#: accepted" is history, not a receipt); phrases are matched case-insensitively. The
#: self-referential forms ("every figure in this paragraph is accurate", "all of the above
#: has been cross-checked") require the subject to be the answer itself or its items,
#: immediately followed by a copula and a checking or accuracy word, and no digit in the
#: span, so that an argument about what a court "is correct" to do is not a self-report.
SELF_CERT_RE = re.compile(
    r"\b(?:VERIFIED|ACCEPTED_WITH_FINDINGS|ACCEPTED|REJECTED|ENTAILED|COUNTEREXAMPLE|INCONSISTENT_PREMISES)\b"
    r"|(?i:\ball (?:claims|dates|figures|facts|quotations)(?: and (?:figures|dates|quotations))?(?: (?:have been|were|are|was|is))? ?(?:checked|verified|confirmed|validated)\b"
    r"|\b(?:verified|checked|confirmed|validated) by (?:the )?(?:z3|engine|solver|verifier|translator|overseer)\b"
    r"|\bfact[- ]?checked\b|\bself[- ]?certif\w*|\bverification (?:complete|passed|status)\b|\bchecked and confirmed\b"
    r"|\bdouble[- ]checked\b|\bcross[- ]checked\b|\bcompared (?:with|against) the supplied\b|\bmatch(?:es|ed)? (?:it|them) exactly\b"
    r"|\bno findings\b|\bfindings:\s*none\b|\btransmission (?:accepted|rejected)\b|\bvia branch \w+\b|\bstatus:\s*(?:entailed|accepted|rejected|verified|ok)\b"
    r"|(?:\"|\b)(?:status|receipt_id|transmission_id|formal_checks|structural_findings|findings|codes)\"\s*:"
    rf"|\b{_ANSWER_ITSELF}(?: (?:is|are|was|were|has been|have been)|,? (?:which|and) (?:is|are|has been|have been))\s+(?:all\s+|fully\s+|carefully\s+|now\s+)?{_CHECK_WORDS}\b"
    rf"|\b{_EVERY_ITEM}\s+{_COPULA}{_CHECK_WORDS}\b)",
)
#: The looser semantic rule of :func:`is_self_certification`: the sentence speaks of the answer
#: itself (or of every figure, date or quotation in it) and, anywhere in the sentence, of a
#: checking act or of the reader relying on it. A bare accuracy adjective ("is correct") counts
#: only in the regex's immediate form, so "this paragraph argues that the court is correct to
#: uphold the thesis" stays an argument.
_SELF_SUBJECT_RE = re.compile(rf"\b(?:{_ANSWER_ITSELF}|{_EVERY_ITEM})\b", re.IGNORECASE)
_SELF_PREDICATE_RE = re.compile(
    r"\b(?:checked|verified|confirmed|validated|double[- ]checked|cross[- ]checked|re[- ]?checked|compared (?:with|against))\b"
    r"|\bmatch(?:es|ed)? (?:it|them|the \w+(?: \w+)?) (?:exactly|precisely|word for word)\b"
    r"|\brely (?:on|upon) (?:it|them|these|this)\b|\bmay be relied (?:on|upon)\b|\btrustworthy\b|\berror[- ]free\b|\bfree of errors?\b",
    re.IGNORECASE,
)
#: A year, a capitalised month name (``may`` the modal verb is not a month) or a figure with a unit.
_DATED_ITEM_RE = re.compile(
    r"\b(?:1[0-9]{3}|20[0-9]{2})\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b"
    r"|(?i:\b\d+(?:[.,]\d+)?\s*(?:per cent|percent|%|million|billion|thousand)\b)",
)


def strip_json_blocks(text: str) -> tuple[str, int]:
    """Remove pasted JSON blocks (a receipt, a payload) from ``text``.

    A block is removed when it opens with ``{`` or ``[`` at a line start, closes with
    the matching bracket at a line end without crossing a blank line, and either parses
    as JSON or carries a JSON key-value pair. Returns ``(text, number_removed)``.
    """
    removed = 0

    def take(m: "re.Match[str]") -> str:
        nonlocal removed
        if is_json_block(m.group(0)):
            removed += 1
            return ""
        return m.group(0)

    return JSON_BLOCK_RE.sub(take, text), removed


def strip_markup(text: str) -> str:
    """Return ``text`` without a byte-order mark, CRLF, heading lines, fenced code
    blocks (fence lines and their body), stray fence lines, pasted JSON blocks or
    emphasis markers. Paragraph breaks (blank lines) are preserved. The caller keeps
    the untouched original for ``original_response``; this is only the text to segment."""
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    if s.startswith(BOM):
        s = s[len(BOM):]
    s = s.replace(BOM, "")
    s = HEADING_LINE_RE.sub("", s)
    s = FENCE_BLOCK_RE.sub("", s)
    s = FENCE_LINE_RE.sub("", s)
    s, _removed = strip_json_blocks(s)
    s = EMPHASIS_RE.sub(r"\2", s)
    return s


def split_list_items(paragraph: str) -> list[str]:
    """Split a paragraph at newlines that start a list item and drop the markers.

    A paragraph without list markers is returned as a single item; an item that is
    only a marker is dropped. The item texts are the specialist's words, unchanged
    apart from the marker and surrounding whitespace.
    """
    pieces = LIST_LINE_RE.split(paragraph)
    out: list[str] = []
    for piece in pieces:
        stripped = LIST_MARKER_RE.sub("", piece, count=1).strip() if LIST_MARKER_RE.match(piece) else piece.strip()
        if stripped:
            out.append(stripped)
    return out


def truncate_claim_text(text: str, limit: int = MAX_CLAIM_TEXT_CHARS) -> str:
    """Cut ``text`` to the contract limit, marking the cut with ``...``."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def is_memory_label(sentence: str) -> bool:
    return bool(MEMORY_LABEL_RE.search(sentence))


def is_self_certification(sentence: str) -> bool:
    """True for verification-status vocabulary (:data:`SELF_CERT_RE`), for a sentence shaped
    like a JSON receipt or payload, and for the semantic rule: the sentence's subject is the
    answer itself ("this paragraph", "the above", "all of the above", "every figure and date")
    with a checking or accuracy predicate and no dated item. A sentence that mentions only
    its items ("every figure") needs a checking verb, not a bare accuracy adjective, so a
    remark that "every figure in the painting is exact" stays an argument."""
    if SELF_CERT_RE.search(sentence) or is_json_shaped(sentence):
        return True
    return bool(_SELF_SUBJECT_RE.search(sentence) and _SELF_PREDICATE_RE.search(sentence) and not _DATED_ITEM_RE.search(sentence))


def is_task_note(sentence: str) -> bool:
    return bool(TASK_NOTE_RE.search(sentence))


def is_note_sentence(sentence: str) -> bool:
    """A sentence that is a label about the text (from-memory disclaimer, self-certification,
    or a note that the syllabus version, cohort, level or mark was not given) rather than part of the argument."""
    return is_memory_label(sentence) or is_self_certification(sentence) or is_task_note(sentence)


def is_json_shaped(sentence: str) -> bool:
    """True when ``sentence`` carries the shape of JSON: a quoted key with a JSON value and
    either a bracket or a second key-value pair. Prose that quotes a word before a colon does not qualify."""
    pairs = JSON_KEY_RE.findall(sentence)
    if not pairs:
        return False
    return len(pairs) >= 2 or any(ch in sentence for ch in "{}[]")


def is_json_block(block: str) -> bool:
    """True when ``block`` is a pasted JSON document (parses as an object or array), or opens
    and closes with brackets around at least one JSON key-value pair."""
    s = block.strip()
    if not s or s[0] not in "{[" or s[-1] not in "}]":
        return False
    try:
        parsed = json.loads(s)
        if isinstance(parsed, (dict, list)):
            return True
    except ValueError:
        pass
    return bool(JSON_KEY_RE.search(s))


#: A parenthetical or a clause after a semicolon/dash that can carry a note inside a longer sentence.
_CLAUSE_RE = re.compile(r"\s*\([^()]*\)|\s*[;—–]\s*[^;—–()]+")


def split_note_clauses(sentence: str) -> tuple[str, list[str]]:
    """Separate the note clauses of a sentence from its substance.

    A substantive sentence may carry the method's own label inline, as a parenthetical
    ("(figures from memory; check your notes)") or a clause after a semicolon or dash
    ("...; dates other than the poem's own are from memory"). Returns ``(core, notes)``:
    ``core`` is the sentence with those clauses removed (whitespace tidied) and ``notes``
    the removed clauses in order. A sentence that is nothing but a note returns an empty
    core. Parsers keep the verbatim sentence as the claim text, classify ``core`` and
    record ``notes`` as assumptions; only an empty core makes the sentence a note.
    """
    notes: list[str] = []
    def take(m: "re.Match[str]") -> str:
        clause = m.group(0)
        if is_note_sentence(clause):
            notes.append(clause.strip(" ;—–()"))
            return ""
        return clause
    core = _CLAUSE_RE.sub(take, sentence)
    core = re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s{2,}", " ", core)).strip()
    if core and is_note_sentence(core):  # what remains is itself a label: the whole sentence is a note
        return "", [sentence.strip()]
    if core and not re.search(r"[^\W\d_]", core):
        core = ""
    return core, notes


# ------------------------------------------------------------------ quotation marks


def normalize_double_marks(text: str) -> str:
    """``text`` with every double quotation mark (curly, guillemet, low-9) replaced by the
    straight mark. Character for character, so offsets into the result are offsets into ``text``."""
    return text.translate(_DOUBLE_MARK_TRANSLATION)


def _mark_kind(text: str, pos: int) -> str:
    """``open``, ``close`` or ``either`` for the double mark at ``pos``: unambiguous glyphs
    decide by direction (a left double mark closes a low-9 quotation when the text uses
    that convention), a straight mark by its neighbours (an opener follows whitespace, a
    bracket or a dash and precedes a non-space; a closer follows a non-space and precedes
    whitespace, punctuation, a closing bracket or the end)."""
    ch = text[pos]
    before = text[pos - 1] if pos > 0 else " "
    after = text[pos + 1] if pos + 1 < len(text) else " "
    opens = (before.isspace() or before in "([—–-") and not after.isspace()
    closes = not before.isspace() and (after.isspace() or after in ".,;:!?)]")
    if ch == "\u201c" and "\u201e" in text and closes and not opens:
        return "close"  # the low-9 convention („word“) closes with the mark English opens with
    if ch in _OPENING_GLYPHS:
        return "open"
    if ch in _CLOSING_GLYPHS:
        return "close"
    if opens and not closes:
        return "open"
    if closes and not opens:
        return "close"
    return "either"


def dangling_quote_offset(text: str) -> Optional[int]:
    """Offset of the double quotation mark of ``text`` that cannot be paired, or ``None``.

    Marks are read in order, expected to alternate opener / closer. The first mark whose
    context contradicts the expectation locates the fault: an opener where a closer was
    due means the previous opener never closed (that previous mark dangles); a closer
    where an opener was due has no opener (that mark dangles). With no contradiction and
    an odd count, the last mark dangles. With an even count and no contradiction the
    marks pair and nothing dangles. Pairing the remaining marks around the dangling one
    recovers the quotations the writer did delimit instead of shifting every later pair.
    """
    positions = [i for i, ch in enumerate(text) if ch in DOUBLE_QUOTE_MARKS]
    if not positions:
        return None
    expect_open = True
    for n, pos in enumerate(positions):
        kind = _mark_kind(text, pos)
        if kind == "either":
            expect_open = not expect_open
            continue
        if (kind == "open") == expect_open:
            expect_open = not expect_open
            continue
        if kind == "open":  # an opener where a closer was due: the previous opener never closed
            return positions[n - 1] if n > 0 else pos
        return pos  # a closer with no opener
    if len(positions) % 2 == 1:
        return positions[-1]
    return None


def unbalanced_double_quotes(text: str) -> bool:
    """True when the double quotation marks of ``text`` cannot be paired.

    Straight, curly, guillemet and low-9 marks are one class, so a quotation opened with
    a curly mark and closed with a straight one is balanced. An odd total is unbalanced;
    so is text set entirely in directional marks whose openers and closers differ in number.
    """
    positions = [i for i, ch in enumerate(text) if ch in DOUBLE_QUOTE_MARKS]
    if len(positions) % 2 == 1:
        return True
    glyphs = [text[i] for i in positions]
    if glyphs and '"' not in glyphs:
        return sum(1 for g in glyphs if g in _OPENING_GLYPHS) != sum(1 for g in glyphs if g in _CLOSING_GLYPHS)
    return False


def find_quotation_spans(text: str, *, min_single_words: int = 2) -> list[tuple[int, int, str]]:
    """Quoted spans of ``text`` as ``(start, end, inner)`` in order of appearance.

    Double marks of every kind are paired left to right after the dangling mark of an
    unbalanced text (see :func:`dangling_quote_offset`) is set aside, so one missing
    mark does not turn the prose between later quotations into "quotations". Single
    marks (straight or curly) delimit a quotation only around ``min_single_words`` or
    more words. ``inner`` is the writer's text between the marks, verbatim.
    """
    norm = normalize_double_marks(text)
    skip = dangling_quote_offset(text)
    positions = [i for i, ch in enumerate(norm) if ch == '"' and i != skip]
    spans: list[tuple[int, int, str]] = []
    for a, b in zip(positions[0::2], positions[1::2]):
        inner = text[a + 1:b]
        if inner.strip() and "\n" not in inner:
            spans.append((a, b + 1, inner))
    masked = list(norm)
    for a, b, _inner in spans:
        for i in range(a, b):
            masked[i] = " "
    if skip is not None:
        masked[skip] = " "
    for m in SINGLE_QUOTE_SPAN_RE.finditer("".join(masked)):
        group = m.lastindex or 1
        inner = m.group(group)
        if inner is None or len(inner.split()) < min_single_words:
            continue
        spans.append((m.start(), m.end(), text[m.start(group):m.end(group)]))
    spans.sort(key=lambda s: s[0])
    return spans


def undelimited_quote_span(text: str) -> Optional[tuple[int, int, str]]:
    """The span that the dangling double mark of ``text`` opens or closes, as
    ``(start, end, inner)``, or ``None`` when every mark pairs.

    A dangling opener runs to the end of ``text`` (the writer never closed it); a
    dangling closer runs from the end of the previous paired span, or the start of the
    text, up to the mark. The span is what the writer meant to quote but did not
    delimit: parsers record it without attributing it to any text or checking it.
    """
    d = dangling_quote_offset(text)
    if d is None:
        return None
    kind = _mark_kind(text, d)
    if kind == "either":
        kind = "open" if text[d + 1:].strip() else "close"
    if kind == "open":
        inner = text[d + 1:]
        return (d, len(text), inner) if inner.strip() else None
    prev_end = max((e for _s, e, _inner in find_quotation_spans(text) if e <= d), default=0)
    inner = text[prev_end:d]
    return (prev_end, d + 1, inner) if inner.strip() else None
