"""Rule ``non-material-text`` (``docs/DELIVERY.md`` 6b, attack round 3 on rule meta-note): every stretch of the answer that
the branch's own parser does not read as a claim of the answer must be positively read by one of three closed readers, or
the answer never travels under the FORMALLY CHECKED label.

Rounds 1 and 2 gave rule ``self-report-disclosed`` readers for what a closed list of leads opens (rule ``meta-note`` on the
paragraphs the English pack names ES-META-001, rule ``lead-blocks`` on every block a note or sources lead opens). Attack
round 3 showed that a closed list of LEADS cannot close condition 6b: an assurance still travelled under the label through a
note lead the parsers read and the list did not (a word joiner, a bracket or a dash after "Note on", "N.  B."), through the
parsers' other channels for text they keep out of the claims (the English parser's marking-feedback furniture, "Task:" or
"Provisional marks:" read as layout; its answer notes, any sentence holding "send me" or "paste ... here"; a label-shaped
"from memory" sentence), and through note-like leads no list holds. This rule INVERTS the reading: it lists no lead. It
takes the branch parser's own segmentation and roles and reads everything the parser sets aside.

* **The parser's reading** (:func:`parser_units`). The deliverable's journaled answer is read again, deterministically, by
  the parser of the branch that serves its agent, with the arguments the channel gives it: the English branch by its own
  segmentation and sentence roles (``english_specialist.parser.segment``); every other branch (History, the generic
  branches, the three STEM branches) by its ``parse_response``, whose claims stand in the order of the answer. A unit is a
  CLAIM when the parser gives it a role other than ``other`` (thesis, point, interpretation, device, link, judgement,
  perspective, evidence, quantitative, analysis, structural, ...), whatever its materiality: the formal path decides the
  material ones and the packs check the others. A unit of role ``other`` (a note, meta-text, a self-report, a source list,
  a heading, a question, layout furniture, an English list item) is no claim, and neither is any text the parser leaves out
  of every unit (a heading line, a fenced block, a pasted JSON block, a part label, a mark annotation, a bullet).
* **The text no claim covers** (:func:`covered_spans`). Each claim is found in the answer, in the order the parser read
  it, word by word: the answer and each unit are cut into words (runs of letters and digits, read in NFKC and case-folded;
  a format character, another default-ignorable code point, a combining mark and the emphasis marks "*", "_", "`", "~"
  split no word), and each unit's words are looked for, whole words only, after the place where the unit before it was
  found. The claims' words are COVERED; everything else is the answer's non-material text. A claim that cannot be found,
  or more than a few units of role ``other`` that cannot, make the whole answer unread (fail closed). Text is only ever
  covered by a claim, so a stretch the parser reads as no claim is never taken out of the reading by this step.
* **Blocks** (:func:`non_material_blocks`). The non-material text is cut at paragraph ends (as the English parser cuts
  paragraphs), at every claim, and before every lead a reader reads (a note lead, a sources lead or a layout label, at a
  paragraph's or a line's start or after a sentence's end, read on the text's confusable skeleton since attack round 4:
  :func:`~epinoic_overseer.meta_notes.lead_starts`, :func:`~epinoic_overseer.meta_notes.skeleton`). Each
  block that holds anything but layout marks (blanks and a closed set of punctuation and markdown marks: the stop and
  closing quotation mark after a claim, a bullet, a table rule) must be read AS A WHOLE by one of three closed readers:
  rule ``meta-note``'s note allowlist (:func:`~epinoic_overseer.meta_notes.read_meta_paragraph`), the strict
  source-list reader (rule ``source-list``, :func:`~epinoic_overseer.meta_notes.read_source_list`) or the strict
  layout reader (rule ``layout``, :func:`read_layout`): a bare label from the parsers' own closed label sets (the English
  feedback layout's "Task:", "Provisional marks:", "What the task wants:", "What the question asks for:"; the generic
  branch's "Answer:", "Result(s):", "Final answer:", "Total:", "Why:", "Reason(s):", "Reasoning:", "Because:",
  "Justification:", "Assumption(s):", "Measure:", "Working:" and diagram labels; the STEM structure heads "Given:",
  "Data:", "Known values:", "Working(s):", "Solution:", "Method:", "Calculation(s):", with at most a part id of the parsers'
  own part-label grammar, :data:`_PART_ID`: one letter a to h, a roman numeral up to viii, or a number of one or two digits
  with an optional letter, in the parsers' own brackets, "Working (b):", "Solution 2b):"), a part label with at most its
  mark allocation ("(a)", "Part (b) [2 marks]", "3."), a run of mark allocations ("[2]", "[1 spare]", "(3 marks)"; never a
  markscheme code, "M1", "A1", "N2", "AG": the mark the answer awards its own working) or a table rule, with nothing after
  it but blanks, or a closed label followed only by the task's own wording copied verbatim (the whole wording, one of its
  lines or one of its sentences, :func:`task_wordings`, read once for the answer). Every reader first reads the text
  normalised (NFKC, every format character and every other default-ignorable code point removed, every combining mark that
  does not belong to a letter removed: :func:`~epinoic_overseer.meta_notes.reader_text`), cuts blocks at leads read
  case-insensitively whatever punctuation, bracket or dash follows them, and refuses a block holding a sentence any shared
  self-report reader names (the auditor's structural detector ``flags_self_certification`` included). Since attack round 5
  each reader reads its block AS A WHOLE from its first character: before a lead or a label only blanks, at most one list
  mark of a closed set and the lead's own emphasis (:data:`~epinoic_overseer.meta_notes.LEAD_REGION`; rule layout's
  :func:`~epinoic_overseer.meta_notes.lead_region_end`), never "### Working:", "> Answer:" or "👍 Task:". Every reader that
  frees a block reads its lead or label as written: a lead or label only the skeleton reads ("Tаsk:" with a Cyrillic а) cuts
  a block but frees none.
* **Attack round 4** found three open slots in these readers and closed each at its cause: the STEM structure heads took
  the STEM parser's own part-id slot of four letters or digits ("Working (fine):", "Method (good):", "Data (true):",
  "Working ok:", "Known good:" were layout); a run of markscheme codes was layout ("(A1) (A1) (A1) (A1)", "(N2)" after an
  answer); the source list took words that name no source (``meta_notes``). Look-alike letters hid a lead from every
  reader ("Nоte:", "Ν.Β.", "ɴᴏᴛᴇ:"), and the task's wording was read again for every block.
* **The refusal.** Any block no reader reads keeps the answer from the FORMALLY CHECKED label; the delivery policy names it
  by its paragraph, line, whether it stands inside a line and the rule that refused it, never by its words. An answer the
  parser cannot read, a claim that cannot be found, a reader that fails, or more than :data:`MAX_BLOCKS` blocks that need a
  reader refuse the answer as a whole. The rule can only remove the label: it never frees what another rule refuses.

Out of scope of this rule: an assurance the parser reads as a claim of the answer. Since attack round 5 the delivery
policy's rule ``unverified-claims`` narrows that channel (a claim no signed engine result decides positively is refused; a
parser claim whose whole text no journaled claim holds, :func:`parser_claims`, :func:`claim_key`, is refused too); it does
not close it: assurances inside or as verified or eligible claims stay open to the formal path, and only condition 6d (rule
``formal-label-withheld``, attack round 6) keeps them off the label. A MATERIAL claim (a point,
thesis, link or judgement: "Final note: there is nothing to fix in this answer, not a single slip." as a paragraph of its
own is the English parser's material point) is the formal path's to decide, and the formal path marks it ``not_eligible``
(no encoding decides it), so it never blocks; a SUPPORTING claim of the argument (an English interpretation or device
sentence, a STEM quantitative or analysis step: the same sentence at the end of a body paragraph; an emoji or a code glued
to a claim; a STEM structure head the STEM parser's own open slot reads as a 'structural' claim, "Working (fine):") is read
by the packs and by no 6b reader. Reading every supporting claim as non-material text would refuse the label to every
answer that argues (the English parser's own interpretation sentences, and the STEM parser reads the Physics fixture's
result "The speed is 15 km/h." as a supporting quantitative step), so the line between a claim and a note is the parser's
role ``other``. At the published base 16d5a4a such an assurance was FORMALLY CHECKED on an answer without a closing note
and withheld on one with a genuine note (that note's ES-META-001); rule meta-note frees the note, so the channel is
reachable on note-carrying answers since the clearance commit (``tests/overseer_tests/data/meta_note_attack_round4.json``).

Linear and bounded: the parser is the branch's own (its readers are linear, its claims at most 512, the answer at most the
channel's size); the words are read once, each claim is found by one forward search from where the last one was found (a
failed search ends the reading), the task's wording is read once for the answer, the blocks are cut by one scan of each
piece for its leads (each character's skeleton a bounded memo), and each block is read once by each linear reader, in time
linear in the block. Like every check, the rule proves a property of the text and this code only.
"""
from __future__ import annotations

import re
import unicodedata
from bisect import bisect_left
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from epinoic_logic.api.adapters import MAX_CLAIM_TEXT_CHARS
from epinoic_logic.api.stem import ANNOTATION_ONLY_LINEAR_RE, MARK_ALLOC, MARK_CODE, PART_LEAD_RE, TABLE_SEPARATOR_RE, annotation_ranges
from .meta_notes import (
    MAX_LEAD_BLOCKS, _ignorable, answer_paragraphs, hides_text, lead_region_end, lead_starts, normalised_answer, read_meta_paragraph, read_source_list,
    reader_text,
)

__all__ = ["NON_MATERIAL_RULE", "LAYOUT_RULE", "MAX_BLOCKS", "ParserUnit", "LayoutReading", "TextBlock", "english_units", "report_units",
           "parser_units", "parser_claims", "claim_key", "held_claims", "covered_spans", "non_material_blocks", "unread_non_material_blocks",
           "read_layout", "layout_marks_only", "task_wordings"]

NON_MATERIAL_RULE = "non-material-text"
LAYOUT_RULE = "layout"
#: The most blocks one answer is read for beyond the layout reader's (an answer holds a handful of notes and source lists; more
#: is refused unread, fail closed). Blocks the layout reader reads (a part label, a mark annotation) are not counted.
MAX_BLOCKS = MAX_LEAD_BLOCKS
#: The most units of role ``other`` that may fail to be found before the answer is refused unread (a claim that cannot be
#: found refuses it at once).
_MAX_UNFOUND = 8


@dataclass(frozen=True)
class ParserUnit:
    """One unit of the branch parser's reading, in the order of the answer: a sentence (English) or a claim (every other
    branch); ``claim`` when the parser gives it a role other than ``other``."""

    text: str
    claim: bool


@dataclass(frozen=True)
class LayoutReading:
    """How rule ``layout`` read a block: ``ok`` when it is a bare closed label, a part label, a run of mark annotations, a
    table rule or a closed label followed only by the task's own wording; otherwise the rule that refused it and why."""

    ok: bool
    rule: str = ""
    detail: str = ""
    #: The block has a layout form the reader refused for what it holds (a run of annotations holding a markscheme code):
    #: rule ``layout`` names it.
    form: bool = False


@dataclass(frozen=True)
class TextBlock:
    """One block of the answer's non-material text (rule ``non-material-text``): its paragraph (1-based, as the English
    parser cuts paragraphs; 0 for the answer as a whole), the 1-based line of that paragraph it starts on, whether it starts
    inside its line, its text, whether a closed reader ``read`` it and which (``meta-note``, ``source-list`` or ``layout``),
    and when none did, the rule that refused it and what it read (the detail holds the answer's words: it never reaches a
    reason)."""

    paragraph: int
    line: int
    inline: bool
    text: str
    read: bool
    reader: str = ""
    rule: str = ""
    detail: str = ""

    def where(self) -> str:
        """The block named by position and rule only (no word of the answer): the delivery policy's reason."""
        at = f"paragraph {self.paragraph}" if self.paragraph else "the answer as a whole"
        if self.line > 1:
            at += f" line {self.line}"
        if self.inline:
            at += " inside the line"
        return f"{at} (rule {self.rule or NON_MATERIAL_RULE})"


class _Unread(Exception):
    """The parser's reading cannot be laid on the answer: the whole answer is refused (fail closed)."""


# ============================================================================================ the parser's reading
def english_units(text: str) -> list[ParserUnit]:
    """The English parser's own segmentation and sentence roles (``segment``): every sentence of every paragraph in order,
    a claim when its role is not ``other``."""
    from epinoic_logic.api.adapters import segment
    return [ParserUnit(s.text, s.role != "other") for p in segment(text) for s in p.sentences]


def report_units(report: Any) -> list[ParserUnit]:
    """The claims of a report a branch parser built, in the order the parser wrote them (the order of the answer), each a
    claim when its role is not ``other``."""
    return [ParserUnit(str(c.claim_text), c.claim_role != "other") for c in list(report.claims)]


def parser_units(text: str, parser: Any, **kwargs: Any) -> list[ParserUnit]:
    """The reading of the answer ``text`` by the branch parser ``parser`` (the channel's arguments in ``kwargs``): the
    English parser by :func:`english_units` (an answer whose report would fold claims into its tail is refused: the tail is
    no claim), every other parser by its ``parse_response`` (:func:`report_units`). Raises when the parser cannot read it."""
    from epinoic_logic.api.adapters import TAIL_CLAIM_ID
    from epinoic_logic.api.branches import EnglishParserWrapper as _EnglishParserWrapper
    if isinstance(parser, _EnglishParserWrapper):
        report = parser.parse_response(text, **kwargs)
        if any(str(c.claim_id).startswith(TAIL_CLAIM_ID) for c in report.claims):
            raise _Unread("the English report folds claims into its tail")
        return english_units(text)
    return report_units(parser.parse_response(text, **kwargs))


# ============================================================================================ the text no claim covers
def _words(text: str) -> tuple[list[str], list[int], list[int]]:
    """The words of ``text`` (maximal runs of letters and digits, each character read in NFKC and case-folded) with each
    word's start and end offsets in ``text``. A format character, another default-ignorable code point, a combining mark and
    the emphasis marks "*", "_", "`" and "~" are read as nothing, so none splits a word (the parsers remove the emphasis
    marks before they cut claims). One linear pass."""
    words: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    cur: list[str] = []
    first = last = 0
    for i, ch in enumerate(text):
        if ch in "*_`~":
            continue
        if ch.isascii():
            piece = ch.lower()
        elif _ignorable(ch) or unicodedata.category(ch)[0] == "M":
            continue
        else:
            piece = unicodedata.normalize("NFKC", ch).casefold()
        for c in piece:
            if c.isalnum():
                if not cur:
                    first = i
                cur.append(c)
                last = i + 1
            elif cur:
                words.append("".join(cur))
                starts.append(first)
                ends.append(last)
                cur = []
    if cur:
        words.append("".join(cur))
        starts.append(first)
        ends.append(last)
    return words, starts, ends


def _unannotated(text: str) -> str:
    """``text`` with every mark annotation the parsers leave out of a claim blanked, character for character (the STEM
    layout's own reader, line by line: ``stem.layout.annotation_ranges``): a claim that spans lines loses the "M1" or "[2]"
    closing each of its lines, so the answer's words are read without them too. Linear."""
    if not any(ch in text for ch in "[(MARNG"):
        return text
    out: list[str] = []
    for line in text.split("\n"):
        ranges = annotation_ranges(line)
        if ranges:
            chars = list(line)
            for a, b in ranges:
                chars[a:b] = " " * (b - a)
            line = "".join(chars)
        out.append(line)
    return "\n".join(out)


def _edge_marks(unit: str) -> tuple[str, str]:
    """The marks a unit's text writes before its first word and after its last one (blanks and emphasis marks left out):
    "%." after "15", the quotation mark before "Just"."""
    i, j = 0, len(unit)
    while i < j and not unit[i].isalnum():
        i += 1
    while j > i and not unit[j - 1].isalnum():
        j -= 1
    keep = lambda part: [c for c in part if not c.isspace() and c not in "*_`~"]  # noqa: E731
    return "".join(keep(unit[:i])), "".join(keep(unit[j:]))


_SEP = "\x00"
#: The marks a claim's own words open and close with: the quotation mark or bracket before its first word, and the stop,
#: comma, colon, quotation mark or bracket after its last word belong to the claim.
_OPENERS = frozenset("\"'“‘«([{")
_CLOSERS = frozenset(".!?…,;:\"'”’»)]}")


def claim_key(text: str) -> str:
    """A claim's WHOLE text as rule ``unverified-claims`` compares it: NFKC, every run of blanks one space, stripped; every
    other character kept (a symbol, an emoji, a format or tag character, an emphasis mark), so a claim unit whose text says
    more than a journaled claim's ("The speed is 15 km/h. 👍" beside "The speed is 15 km/h.") is no claim the report holds."""
    return " ".join(unicodedata.normalize("NFKC", str(text)).split())


def parser_claims(text: str, parser: Any, **kwargs: Any) -> list[tuple[str, str, str]]:
    """The claims the branch parser ``parser`` reads in the answer ``text`` with the channel's arguments ``kwargs`` (rule
    ``unverified-claims`` of the delivery policy): ``(claim_id, role, claim_text)`` for every claim of its ``parse_response``
    with a role other than ``other``, whatever its materiality. Raises when the parser cannot read the answer."""
    report = parser.parse_response(text, **kwargs)
    return [(str(c.claim_id), str(c.claim_role), str(c.claim_text)) for c in list(report.claims) if c.claim_role != "other"]


def held_claims(report: Any) -> frozenset[tuple[str, ...]]:
    """The words of every claim of the journaled ``report`` with a role other than ``other`` (mark annotations blanked):
    the claims the delivery holds. A parser claim covers its text only when the report holds the same claim, so text an
    agent's own report never claims (a report delivered as an object, whose ``original_response`` says more than its claims)
    is read as non-material text, whatever the parser would make of it."""
    return frozenset(tuple(_words(_unannotated(str(c.claim_text)))[0]) for c in list(getattr(report, "claims", None) or [])
                     if c.claim_role != "other")


def covered_spans(text: str, units: Sequence[ParserUnit], held: Optional[frozenset] = None) -> list[tuple[int, int]]:
    """The spans of ``text`` (offsets ``[start, end)``) that the claims among ``units`` cover: each unit's words are looked
    for, whole words only, after the place where the unit before it was found (the units stand in the order of the answer);
    a claim's words are covered, with the marks its own text writes before and after them, when ``held`` (the claims of the
    journaled report, :func:`held_claims`) is None or holds the same words. A claim of at least the contract's length is
    looked for without its last word (the cut may fall inside it). Raises :class:`_Unread` when a claim cannot be found, or
    more than :data:`_MAX_UNFOUND` other units cannot (fail closed). Linear: each search starts where the last one ended and
    a failed search ends the reading."""
    words, starts, ends = _words(_unannotated(text))
    joined = _SEP + _SEP.join(words) + _SEP
    offsets: list[int] = []  # the position in ``joined`` of each word's first character
    pos = 1
    for w in words:
        offsets.append(pos)
        pos += len(w) + 1
    covered: list[tuple[int, int]] = []
    pointer = 0
    unfound = 0
    for u in units:
        uw = _words(_unannotated(u.text))[0]
        if len(u.text) >= MAX_CLAIM_TEXT_CHARS - 3:
            uw = uw[:-1]
        if not uw:
            continue
        pattern = _SEP + _SEP.join(uw) + _SEP
        j = joined.find(pattern, pointer)
        if j < 0:
            if u.claim:
                raise _Unread("a claim the parser read was not found in the answer")
            unfound += 1
            if unfound > _MAX_UNFOUND:
                raise _Unread("units the parser read were not found in the answer")
            continue
        k = bisect_left(offsets, j + 1)
        if u.claim and (held is None or tuple(uw) in held):
            a, b = starts[k], ends[k + len(uw) - 1]
            head, tail = _edge_marks(u.text)
            for mark in reversed(head):  # the marks the claim writes before its first word, as the answer writes them
                x = a - 1
                while x >= 0 and (text[x] in " \t*_`~"):
                    x -= 1
                if x < 0 or text[x] != mark:
                    break
                a = x
            for mark in tail:  # and after its last word ("%." after "15")
                x = b
                while x < len(text) and (text[x] in " \t*_`~"):
                    x += 1
                if x >= len(text) or text[x] != mark:
                    break
                b = x + 1
            while a > 0 and text[a - 1] in _OPENERS:
                a -= 1
            while b < len(text) and text[b] in _CLOSERS:
                b += 1
            covered.append((a, b))
        pointer = j + len(pattern) - 1  # the separator that ends this match opens the next one
    return covered


# ============================================================================================ rule layout
#: The marks a layout block may hold and nothing else: blanks, the stops, commas and closing marks around a claim, quotation
#: marks, brackets, dashes, the markdown marks (a heading, a quote, emphasis, a bullet, a table's bars and rules) and the
#: bullets. No letter, no digit, no symbol (a check mark, a star, an emoji, a percent sign) is a layout mark.
_LAYOUT_MARKS = frozenset(".,;:!?…\"'“”‘’«»„‟‚‹›()[]{}-–—‒―‐‑*_#>|~`+=/\\•·◦‣▪")


def layout_marks_only(text: str) -> bool:
    """Whether ``text`` holds nothing but blanks and layout marks (:data:`_LAYOUT_MARKS`)."""
    return all(ch.isspace() or ch in _LAYOUT_MARKS for ch in text)


#: The closed labels of the parsers' own label sets (each a closed alternative of the parser's pattern; the tests hold each
#: one read by that pattern): the English marking-feedback layout's furniture (``FEEDBACK_LABEL_RE``, never its open "any
#: short label" alternative), the generic branch's line leads (answer, why, assumption, measure and working, diagram lines)
#: and the STEM structure heads with a part id ("Working (b):").
_ENGLISH_LABELS = r"task\s*[—–:-]|provisional\s+marks?\s*:|what\s+the\s+(?:task|question)\s+(?:wants|asks(?:\s+for)?)\s*:"
_GENERIC_LABELS = (r"(?:results?|answers?|final\s+answers?|total)\s*:|(?:why|reasons?|reasoning|because|justification)\s*:"
                   r"|assum(?:ption|ptions|ed|ing)\s*:|(?:measure|working)\s*:"
                   r"|(?:axes|axis|curves?|change|shifts?|equilibri(?:um|a)|areas?|labels?|key|arrows?)\s*:")
#: The part id a STEM structure head may carry (attack round 4: the STEM parser's own slot, "\(?[a-z0-9]{1,4}\)?", is open,
#: so "Working (fine):", "Method (good):", "Data (true):", "Solution (done):", "Working ok:" and "Known good:" were read as
#: layout): the parsers' own part-label grammar only (``stem.layout.LABEL_TOKEN``), one letter a to h, a roman numeral up to
#: viii, or a number of one or two digits with an optional letter, in the parsers' own brackets ("(b)", "b)", "(iii)",
#: "(2)", "(2b)"; no blank inside them, as the STEM parser reads none), and nothing else: every part id it takes is one the
#: STEM parser's own head pattern reads too.
_PART_ID = r"(?:[a-h]|i{1,3}|iv|vi{0,3}|\d{1,2}[a-h]?)"
_STEM_LABELS = (r"(?:given|data|known(?:\s+(?:data|values|quantities))?|working|workings|solution|method|calculations?)"
                r"(?:\s*+(?:\(" + _PART_ID + r"\)|" + _PART_ID + r"\)))?\s*:")
#: A closed label at the start of a block (after its marks), matched on the normalised text; also a lead that cuts the
#: non-material text into blocks (:func:`~epinoic_overseer.meta_notes.lead_starts`).
LAYOUT_LABEL_RE = re.compile(r"(?:" + _ENGLISH_LABELS + r"|" + _STEM_LABELS + r"|" + _GENERIC_LABELS + r")", re.IGNORECASE)
#: What may follow a part label (``stem.layout.PART_LEAD_RE``: "(a)", "Part (b)", "3.", "Question (2)"): at most its mark
#: allocation and a closing colon or stop ("(b) [2 marks]"), never the command term the generic parser also reads on a
#: label-only line ("(a) — find — 3 marks": an open slot).
_PART_ONLY_RE = re.compile(r"\s*+(?:" + MARK_ALLOC + r"|\d{1,2}\s*+marks?)?\s*+[:.]?\s*+", re.IGNORECASE)
_SENTENCE_CUT_RE = re.compile(r"(?<=[.!?…])\s+")
#: A markscheme code ("M1", "A1", "R1", "N2", "AG"; ``stem.layout.MARK_CODE``): the mark the answer awards its own working, a
#: self-grade in code form (attack round 4: "(A1) (A1) (A1) (A1)" after an answer was read as layout). A run of annotations
#: is layout only when it holds mark allocations alone ("[2]", "[1 spare]", "(3 marks)"); a code the parser keeps inside a
#: claim stays the claim's (the claim channel, recorded for round 9).
_MARK_CODE_RE = re.compile(r"(?<![A-Za-z0-9])(?:" + MARK_CODE + r")(?![A-Za-z0-9])")


def _plain(text: str) -> str:
    """``text`` for comparing with the task's wording: normalised (:func:`reader_text`), its emphasis marks removed, its
    blanks collapsed, case-folded, without the marks around it."""
    t = reader_text(text)
    t = "".join(ch for ch in t if ch not in "*_`~")
    return " ".join(t.split()).casefold().strip(" \"'“”‘’«»")


def task_wordings(task_wording: str) -> frozenset[str]:
    """The task's own wording as a layout label may quote it: the whole wording, each of its lines and each of its
    sentences, compared plain (:func:`_plain`). Read once per answer (attack round 4: read again for every block, the cost
    was the blocks times the task's length). Linear in the wording."""
    if not task_wording or not task_wording.strip():
        return frozenset()
    pieces = {task_wording}
    for line in task_wording.splitlines():
        pieces.add(line)
        pieces.update(_SENTENCE_CUT_RE.split(line))
    return frozenset(p for p in (_plain(x) for x in pieces) if p)


def read_layout(text: str, task_wording: str = "", *, pieces: Optional[frozenset] = None) -> LayoutReading:
    """Rule ``layout`` on one block of non-material text (module docstring): the block, normalised and with the markdown
    marks around it set aside, is a bare closed label (:data:`LAYOUT_LABEL_RE`, a STEM structure head with at most a part
    id of the parsers' own grammar) with nothing after it but blanks, a part label with at most its mark allocation, a run
    of mark allocations (never a markscheme code), a table rule, or a closed label followed only by the task's own wording
    copied verbatim (``task_wording``, or ``pieces``, its :func:`task_wordings` read once for the answer: the whole wording,
    one of its lines or one of its sentences); it holds no sentence a shared self-report reader names. Anything else, and
    anything the reader cannot read, is refused. Never raises; linear in the block (each pattern is anchored and reads its
    blanks possessively; the task's wording is read once by the caller)."""
    try:
        return _read_layout(text, task_wordings(task_wording) if pieces is None else pieces)
    except Exception as exc:  # noqa: BLE001 - a reader that fails frees nothing (fail closed)
        return LayoutReading(False, LAYOUT_RULE, f"the reader failed ({type(exc).__name__})")


def _read_layout(text: str, pieces: frozenset) -> LayoutReading:
    from epinoic_logic.api.adapters import is_meta_sentence, split_sentences
    from epinoic_logic.api.adapters import self_cert_vocabulary, verification_label
    from .checks.selfcert import flags_self_certification
    if not text or len(text) > 20_000:
        return LayoutReading(False, LAYOUT_RULE, "empty or over the bound")
    if hides_text(text):
        return LayoutReading(False, LAYOUT_RULE, "a tag character (text no reader is shown)")
    t = reader_text(text).strip()
    for s in split_sentences(t):
        if is_meta_sentence(s) or self_cert_vocabulary(s) is not None or verification_label(s) is not None or flags_self_certification(s):
            return LayoutReading(False, LAYOUT_RULE, f"a sentence a shared self-report reader names: {s[:120]!r}")
    if layout_marks_only(t):
        return LayoutReading(True)
    # the block AS A WHOLE (attack round 5): before a label only the closed lead region (blanks, at most one list mark, the label's own
    # emphasis: :data:`~epinoic_overseer.meta_notes.LEAD_REGION`); a heading or quote mark, a second bullet, an emoji or a symbol
    # before it leaves the block unread ("👍 Task:", "### Working:", "> Answer:")
    core = t[lead_region_end(t):]
    core = core.rstrip(" \t\n*_|")
    if TABLE_SEPARATOR_RE.match(core):
        return LayoutReading(True)
    if ANNOTATION_ONLY_LINEAR_RE.fullmatch(core):
        if _MARK_CODE_RE.search(core):
            return LayoutReading(False, LAYOUT_RULE, "a markscheme code: a mark the answer awards its own working", form=True)
        return LayoutReading(True)
    m = PART_LEAD_RE.match(core)
    if m is not None and _PART_ONLY_RE.fullmatch(core, m.end()):
        return LayoutReading(True)
    m = LAYOUT_LABEL_RE.match(core)
    if m is None:
        return LayoutReading(False, LAYOUT_RULE, "no closed label of the parsers' own sets")
    rest = core[m.end():]
    if not rest.strip(" \t*_"):
        return LayoutReading(True)
    if _plain(rest) in pieces:
        return LayoutReading(True)
    return LayoutReading(False, LAYOUT_RULE, "a closed label followed by more than the task's own wording")


# ============================================================================================ the blocks
def _read_block(block: str, grounding: frozenset, task_wording: str, layout: LayoutReading) -> tuple[bool, str, str, str]:
    """``(read, reader, rule, detail)`` of one block the layout reader did not read (``layout``): read by rule meta-note's
    note allowlist or rule ``source-list``; when neither reads it, the rule of the reader whose lead opens it (none: rule
    ``non-material-text``)."""
    note = read_meta_paragraph(block)
    if note.note:
        return True, "meta-note", "", ""
    sources = read_source_list(block, grounding)
    if sources.ok:
        return True, "source-list", "", ""
    leads = lead_starts(block, LAYOUT_LABEL_RE)
    kind = leads[0][1] if leads and leads[0][0] == 0 else ""
    if kind == "note":
        return False, "", note.rule, note.detail
    if kind == "sources":
        return False, "", sources.rule, sources.detail
    if kind == "extra" or layout.form:
        return False, "", layout.rule, layout.detail
    return False, "", NON_MATERIAL_RULE, "it opens with no note, sources or layout lead"


def non_material_blocks(text: str, units: Sequence[ParserUnit], *, grounding: Iterable[str] = (), task_wording: str = "",
                        held: Optional[frozenset] = None) -> list[TextBlock]:
    """Rule ``non-material-text`` on the answer ``text`` read by the parser as ``units`` (module docstring): every block of
    the text no claim covers, cut at paragraph ends, at claims and before every lead a reader reads, and how it was read
    (``grounding``: the words of the supplied texts' titles and authors, for rule ``source-list``; ``task_wording``: the
    task as the request carried it, for rule ``layout``; ``held``: the claims of the journaled report, :func:`held_claims`,
    when a claim covers its text only if the report holds it). A block of layout marks only is read as layout. Raises
    :class:`_Unread` when the reading cannot be laid on the answer and ``OverflowError`` past :data:`MAX_BLOCKS` blocks that
    need a reader."""
    ground = frozenset(grounding)
    pieces = task_wordings(task_wording)  # read once for the answer, never once per block
    norm = normalised_answer(text)
    spans = covered_spans(norm, units, held)
    out: list[TextBlock] = []
    needing = 0
    si = 0
    for paragraph, (ps, pe, para) in enumerate(answer_paragraphs(text), start=1):
        while si < len(spans) and spans[si][1] <= ps:
            si += 1
        gaps: list[tuple[int, int]] = []
        cur = ps
        k = si
        while k < len(spans) and spans[k][0] < pe:
            a, b = max(spans[k][0], ps), min(spans[k][1], pe)
            if a > cur:
                gaps.append((cur, a))
            cur = max(cur, b)
            k += 1
        if cur < pe:
            gaps.append((cur, pe))
        line, counted = 1, ps
        for a, b in gaps:
            piece = norm[a:b]
            if not piece.strip():
                continue
            cuts = [0] + [s for s, *_rest in lead_starts(piece, LAYOUT_LABEL_RE) if s > 0] + [len(piece)]
            for c0, c1 in zip(cuts, cuts[1:]):
                raw = piece[c0:c1]
                block = raw.strip()
                if not block:
                    continue
                start = a + c0 + (len(raw) - len(raw.lstrip()))
                line += norm.count("\n", counted, start)
                counted = start
                j = start - 1
                while j >= ps and norm[j] in " \t":
                    j -= 1
                inline = j >= ps and norm[j] != "\n"
                if layout_marks_only(block):  # blanks and layout marks only: no word, no symbol, no hidden character
                    out.append(TextBlock(paragraph, line, inline, block, True, LAYOUT_RULE))
                    continue
                layout = read_layout(block, pieces=pieces)  # the strictest reader first: a label, a part label, an annotation
                if layout.ok:
                    out.append(TextBlock(paragraph, line, inline, block, True, LAYOUT_RULE))
                    continue
                needing += 1
                if needing > MAX_BLOCKS:
                    raise OverflowError(f"more than {MAX_BLOCKS} blocks of non-material text that no layout reading reads")
                read, reader, rule, detail = _read_block(block, ground, task_wording, layout)
                out.append(TextBlock(paragraph, line, inline, block, read, reader, rule, detail))
    return out


def unread_non_material_blocks(text: str, units: Sequence[ParserUnit], *, grounding: Iterable[str] = (), task_wording: str = "",
                               held: Optional[frozenset] = None) -> list[TextBlock]:
    """The blocks of :func:`non_material_blocks` no closed reader reads; one block naming the answer as a whole when the
    answer cannot be read (the parser's reading cannot be laid on it, more than :data:`MAX_BLOCKS` blocks, a reader that
    fails): fail closed. Never raises."""
    try:
        return [b for b in non_material_blocks(text, units, grounding=grounding, task_wording=task_wording, held=held) if not b.read]
    except Exception as exc:  # noqa: BLE001 - a reading that fails frees nothing
        if isinstance(exc, OverflowError):
            why = "more than the bound of blocks"
        elif isinstance(exc, _Unread):
            why = f"the parser's reading could not be laid on the answer: {exc}"
        else:
            why = f"the reader failed ({type(exc).__name__})"
        return [TextBlock(0, 0, False, "", False, "", NON_MATERIAL_RULE, why)]
