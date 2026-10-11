"""Heuristic parser for the English specialist's analytical prose.

The English specialist writes PETAL-style paragraphs: a point, then strands of
evidence (quotations) each carried through device, interpretation and effect,
closed by a link. It does not emit structured claims, so this adapter proposes
them from the prose with deterministic text rules. Everything it produces is a
*proposal*: roles, links and certainty are advisory inputs that the eligibility
policy and the engine treat as untrusted data.

Segmentation rules
------------------
* Blocks are separated by blank lines; CRLF and a lone CR are line breaks, so a CR-only
  paragraph break is a paragraph break, as the channel counts paragraphs. Each block is
  classified by content:

  - ``meta``: a block that is a pasted JSON receipt or payload; a block whose every
    sentence is self-certification, narration of internal steps ("I have checked
    ...") or JSON-shaped, quotation marks or not; a quotation-free block whose every
    sentence is a note about the text (from-memory label, task-setting note),
    whatever its length; or a short block (at most 25 words, no quotation) that is a
    label such as ``VERIFIED: ...`` or ``Word count: 341`` or an all-caps label
    followed by a colon. Meta blocks are never part of the argument: they propose no
    claims and support nothing. The structural checks flag them (``ES-META-001``).
    A JSON span glued to prose inside a block does not make the block meta: the
    span is one ``other`` sentence of its own and the prose before and after it is
    segmented as prose (see the sentence rules).
  - ``list``: a heading (``**bold**``, a short line ending with ``:``, or a short
    line with no sentence punctuation) or a bullet list. Consecutive list blocks
    form one ``list`` paragraph. Quotations in a list are still recorded as
    evidence and source-checked; no point, device or link claims are proposed and
    the paragraph working rules (P7, P13) do not apply.
  - everything else is prose. Among the prose paragraphs: a single one is a body
    paragraph; the first of two is the thesis only when it has no quotation and is
    shorter than the second; the first of three or more is the thesis unless it
    carries two or more quotations (then it is a body paragraph wherever it
    stands); with three or more, a last paragraph that opens with a concluding
    signpost (``Ultimately``, ``Thus``, ``In conclusion`` ...) and has fewer than
    two quotations is the conclusion.

* Sentences end at ``.``, ``!`` or ``?`` (closing quotation marks may follow) when
  the next word starts with a capital letter; one-letter tokens and common
  abbreviations (``l.``, ``ll.``, ``p.``, ``Mr.`` ...) never end a sentence, and a
  boundary inside an open quotation never splits it, so a quoted span that contains
  a full stop stays one quotation in one sentence. A pasted JSON span glued to the
  prose (:func:`~epinoic_logic.adapters.markdown.find_json_spans`) is one sentence of
  its own, cut from the prose before and after it, and a ``}`` or ``]`` followed by
  a capital ends a sentence too, so a receipt pasted mid-paragraph never swallows the
  sentences around it and the quotations after it are still grounded.
* Quotations are double-quoted spans and single-quoted spans of at least two words
  that open after whitespace or a bracket and close before whitespace or
  punctuation. Single marks are paired by context: an apostrophe inside a word
  (don't, Scrooge's, Ne'er), an aphetic form ('tis, 'Change) and a plural possessive
  followed by more of the sentence are not marks, so possessives and contractions are
  not quotations and a quotation containing them ('I don't know what a door-nail is')
  is still one quotation, checked against the supplied text. Every double
  mark is one class, curly, straight, guillemet or low-9, so a span opened with one
  kind and closed with another is still a quotation; two adjacent double marks that
  together open or close a quotation (dialogue copied verbatim with its own marks
  inside the writer's) are one nested mark. The strings of a pasted JSON span are
  not quotations. When a paragraph's double marks cannot be paired, the one dangling
  mark is set aside and the remaining marks are paired around it
  (:func:`~epinoic_logic.adapters.markdown.dangling_quote_offset`); the text the
  dangling mark opens (or closes), and every pair around it whose marks contradict
  their context, is recorded as an *undelimited* quotation that is not attributed to
  any text and not checked (:func:`~epinoic_logic.adapters.markdown.undelimited_quote_spans`),
  so the writer's own prose between quotations is never delivered as a quotation nor
  reported as an invented one. Sentence punctuation written inside the closing mark
  (``"legitimate defense,"``) is not part of the quoted words and is stripped from the
  recorded excerpt.

Role rules (body paragraphs)
----------------------------
* a sentence that certifies the answer's own checking (``SELF_CERT_RE``, including
  the semantic rule of :func:`~epinoic_logic.adapters.markdown.is_self_certification`),
  narrates an internal step (``META_NARRATION_RE``) or is JSON-shaped -> ``other``
  with no source reference, wherever it stands, first sentence or not, quotation
  marks or not; the self-report travels in ``advisory_verification_status``;
* a quotation-free sentence that is nothing but a note about the text (a from-memory
  label, a disclaimer, a task-setting note: :func:`is_note_only`) -> ``other``,
  wherever it stands, so a disclaimer is never the paragraph's material point; a
  substantive sentence that carries the label inline (a parenthetical, a
  sentence-initial "From memory,", a comma-bounded ", from memory", a trailing
  ", a figure I give from memory") keeps its role and records the label as an
  assumption. Labels are read outside quotations, so a sentence quoting a colleague's
  label ("whose "dates and figures" are, in its own words, "from memory ..."") is the
  writer's analysis with no label assumption, and "from memory" as part of the
  argument ("The speaker recalls the scene from memory, which ...") is not a label;
* the first remaining sentence (neither meta nor a note) -> ``point``;
* a sentence opening with ``Effectively``, ``Thus``, ``Ultimately``,
  ``Therefore``, ``Consequently`` or ``Hence``, or with a lead that draws the
  strands together (``Read together``, ``Taken together``, ``Together``, ``In this
  light``, ``Read against``: :data:`LINK_LEADS`) -> ``link``; in a single-paragraph
  answer the closing argued sentence that draws a claim over the paragraph's evidence
  without quoting ("... suggest that the poem captures a suspended morning") is the
  ``link`` too, so a combinator that drops it is named (``INT-LEDGER-002``);
* a sentence naming device vocabulary (diction, metaphor, paradox, juxtaposition,
  irony, imagery, syntax, semantic field, pronoun, verb, adjective, adverb, noun,
  declarative, parallel structure, employs) -> ``device``;
* every other sentence -> ``interpretation``;
* every quotation -> an ``evidence`` claim, attributed by the rule every parser shares
  (:func:`~epinoic_logic.adapters.sources.attribute_excerpt`): a ``SourceRef`` into the
  supplied text that contains it (in any recognised form); when several contain it, the
  one the sentence names (by title, author or, for a relayed peer report, the peer
  specialist) wins. When none contains it, the sentence's named text is cited when it
  names exactly one; when it names several, the one that governs the quotation in the
  sentence (its possessive, "the History specialist's "..."", else the speaker of the
  reporting clause, else the text named nearest before it); when it names none, the one literary (non-peer) text under analysis
  is cited, since an English analytical answer quotes the text it analyses; either way the
  claim records the assumption that the excerpt was found in none of the supplied texts
  (all ids listed) so the hub's own check runs and reports it (``INT-REQ-003``). Otherwise
  (several literary texts and none named, or only peer reports supplied and none
  named) the quotation is credited to NO text: the claim carries no ``SourceRef`` and the
  assumption ``quotation with no supplied text to check it against: "..."``, which the core
  pack reports as unverifiable (``CORE-SRC-003``). A text is never cited for being supplied
  first. A quotation located only in a text other than the one the sentence names keeps the
  located reference and records the discrepancy (``ES-SRC-008`` names it).

Thesis sentences get role ``thesis`` and are supported by the body points;
conclusion sentences get role ``link`` and are likewise supported by the points.
A point is supported by its paragraph's evidence, device and interpretation
claims; a device or interpretation sentence is supported by the quotations it
contains; a link is supported by the point and the rest of its paragraph.

Claim ids are stable functions of position: ``p{paragraph}-point``,
``p{paragraph}-s{sentence}`` and ``p{paragraph}-q{quotation}``. Claims beyond the
report's claim limit are folded into one ``other`` claim (``p-tail``) with an
unresolved issue rather than rejected: interpretation and note claims are folded
before evidence claims and evidence before material claims, and the source references
of any evidence claim folded all the same are carried on the tail claim so the hub
still checks those quotations; the issue states how many claims and quotations were
merged.
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from typing import Iterator, Literal, Optional

from ...ir.schema import SourceRef
from ...translate.common import utc_now_rfc3339
from ...translate.contracts import ClaimRecord, ClaimRole, SpecialistReport, SuppliedText, sha256_text
from ...translate.grounding import locate_long_elision
from ..base import AdapterError
from ..markdown import (
    find_json_spans, find_quotation_spans, is_json_block, is_json_shaped, is_note_sentence, is_self_certification, mask_json_spans,
    split_note_clauses, undelimited_quote_span, undelimited_quote_spans,
)
from ..sources import attribute_excerpt, check_excerpt, strip_trailing_punctuation, word_count

__all__ = [
    "AGENT_ID", "DEFAULT_SUBJECT", "ParagraphKind", "Quotation", "Sentence", "Paragraph",
    "segment", "split_sentences", "find_quotations", "strip_quotations", "parse_response", "LINK_SIGNPOSTS", "LINK_LEADS",
    "is_meta_block", "is_list_block", "is_meta_sentence", "is_note_only", "documents_named", "is_peer_document", "text_under_analysis", "META_LABEL_RE", "META_NARRATION_RE",
    "TAIL_CLAIM_ID", "excerpt_located", "long_elision_of",
]

AGENT_ID = "english-specialist"
DEFAULT_SUBJECT = "English A: Literature"
ParagraphKind = Literal["thesis", "body", "conclusion", "meta", "list"]

LINK_SIGNPOSTS: tuple[str, ...] = ("Effectively", "Thus", "Ultimately", "Therefore", "Consequently", "Hence")
#: Sentence leads that draw the paragraph's strands together ("Read together, the clear air ... suggest that ..."): a link
#: inside a body paragraph. They do not make a paragraph the conclusion.
LINK_LEADS: tuple[str, ...] = ("Read together", "Taken together", "Seen together", "Considered together", "Together", "In this light", "Read against")
_CONCLUSION_SIGNPOSTS: tuple[str, ...] = LINK_SIGNPOSTS + ("In conclusion", "Overall", "In sum", "To conclude", "Finally")
_LINK_RE = re.compile(r"^(?:" + "|".join(re.escape(w) for w in LINK_SIGNPOSTS + LINK_LEADS) + r")\b")
#: A closing sentence that draws a claim over the paragraph's evidence ("... suggest that the poem captures ...").
_CLOSING_CLAIM_RE = re.compile(r"\b(?:suggests?|shows?|reveals?|indicates?|demonstrates?|implies|imply)\s+that\b", re.IGNORECASE)
_CONCLUSION_RE = re.compile(r"^(?:" + "|".join(re.escape(w) for w in _CONCLUSION_SIGNPOSTS) + r")\b")
_DEVICE_RE = re.compile(
    r"\b(?:diction|metaphor\w*|paradox\w*|juxtapos\w*|iron(?:y|ic\w*)|imagery|syntax|syntactic\w*|"
    r"semantic field\w*|pronouns?|verbs?|adjectives?|adverbs?|nouns?|declaratives?|parallel structure|employs)\b",
    re.IGNORECASE,
)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
_ALPHA_RE = re.compile(r"[^\W\d_]")
#: A sentence ends at ``.``, ``!`` or ``?`` (closing marks may follow), or at the ``}`` / ``]`` that closes a
#: pasted JSON fragment, when the next word starts with a capital or opens a JSON object (``{"``).
_BOUNDARY_RE = re.compile(r"(?:[.!?]+[\"”’')\]»]*|[}\]])(?=\s+(?:[\"“‘(\[«„]?[A-ZÀ-ÖØ-Þ]|[{\[]\s*\"))")
_TERMINAL_RE = re.compile(r"[.!?][\"”’')\]»]*$")
_LAST_WORD_RE = re.compile(r"([A-Za-zÀ-ÿ]+)\.?$")
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "st", "vs", "etc", "cf", "no", "l", "ll", "p", "pp", "ch", "vol", "ed", "eds",
    "trans", "fig", "sc", "e.g", "i.e", "ibid", "op", "cit", "prof", "sr", "jr",
})
#: A label line that narrates checking rather than analysing (``VERIFIED: all claims checked``).
META_LABEL_RE = re.compile(
    r"^(?:VERIFIED|CHECKED|CONFIRMED|VALIDATED|FACT[- ]?CHECKED|NOTE|STATUS|SELF[- ]?CHECK|WORD ?COUNT|DISCLAIMER|"
    r"TITLE|SUMMARY OF CHECKS|CHECKS?|VERIFICATION)\b[^:\n]{0,40}:",
    re.IGNORECASE,
)
_ALLCAPS_LABEL_RE = re.compile(r"^[A-Z][A-Z0-9 /&'-]{2,}:")
#: Narration of internal steps or of an assurance the writer cannot give.
META_NARRATION_RE = re.compile(
    r"\b(?:as an? (?:ai|language model|assistant)|i have (?:checked|verified|confirmed|validated|fact[- ]checked)|"
    r"all claims (?:have been |were |are )?(?:checked|verified|confirmed|validated)|fact[- ]checked|self[- ]check(?:ed)?|"
    r"verification complete|checked and confirmed)\b",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+")
_HEADING_RE = re.compile(r"^\*\*[^*\n]+\*\*\s*$|^#{1,6}\s")
#: Generic ways a sentence names the one literary text supplied (never a relayed peer report).
_TEXT_CUE_RE = re.compile(r"\bthe (?:poem|sonnet|extract|passage|novel|play|story|source text|supplied text)\b", re.IGNORECASE)
_PEER_DOCUMENT_PREFIX = "peer:"
_MAX_META_WORDS = 25
_MAX_HEADING_WORDS = 12
_MAX_EXCERPT_CHARS = 2000
_MAX_CLAIM_TEXT_CHARS = 4000
_MAX_CLAIMS = 512
TAIL_CLAIM_ID = "p-tail"
_SELF_REPORT = "self-certified in the response text"


@dataclass(frozen=True)
class Quotation:
    """A quoted span inside a sentence."""

    text: str      #: the words as written between the quotation marks
    excerpt: str   #: the words without trailing sentence punctuation
    start: int     #: offset of the opening mark within the sentence
    end: int       #: offset just past the closing mark
    delimited: bool = True  #: False when one of the span's marks is the paragraph's dangling mark: the span is unchecked

    @property
    def words(self) -> int:
        """Number of words in the excerpt."""
        return word_count(self.excerpt)


@dataclass(frozen=True)
class Sentence:
    """One sentence of a paragraph with its proposed role and quotations."""

    index: int                      #: 1-based position within the paragraph
    text: str
    role: ClaimRole                 #: proposed role
    quotations: tuple[Quotation, ...]
    notes: tuple[str, ...] = ()     #: the method's own labels carried inline (from-memory, task note), kept out of the role


@dataclass(frozen=True)
class Paragraph:
    """One paragraph of the answer, classified as thesis, body, conclusion, meta or list."""

    index: int                      #: 1-based position within the answer
    kind: ParagraphKind
    text: str
    sentences: tuple[Sentence, ...]

    @property
    def word_count(self) -> int:
        """Whitespace-token count of the paragraph."""
        return word_count(self.text)

    @property
    def quotations(self) -> tuple[Quotation, ...]:
        """Every quotation in the paragraph, in order of appearance."""
        return tuple(q for s in self.sentences for q in s.quotations)

    @property
    def is_prose(self) -> bool:
        """True for thesis, body and conclusion paragraphs (the argument proper)."""
        return self.kind in ("thesis", "body", "conclusion")


# --------------------------------------------------------------- quotations


def _iter_quotes(text: str) -> Iterator[tuple[int, int, str]]:
    """Yield ``(start, end, inner)`` for every delimited quotation span of ``text`` in order."""
    yield from find_quotation_spans(text)


def find_quotations(sentence: str) -> tuple[Quotation, ...]:
    """Quoted spans of ``sentence`` in order (see the module docstring for the rules).

    When the sentence holds the paragraph's dangling double mark, the text it opens
    (or closes) is returned too, as an undelimited quotation (``delimited=False``)."""
    found: list[Quotation] = []
    for start, end, inner in _iter_quotes(sentence):
        excerpt = strip_trailing_punctuation(inner)
        if not excerpt or len(excerpt) > _MAX_EXCERPT_CHARS:
            continue
        found.append(Quotation(text=inner, excerpt=excerpt, start=start, end=end))
    # the span the dangling mark opens or closes, and in an unbalanced sentence every pair whose marks
    # contradict their context: recorded, attributed to no text, never reported as invented
    for start, end, inner in undelimited_quote_spans(sentence):
        excerpt = strip_trailing_punctuation(inner)
        if excerpt and len(excerpt) <= _MAX_EXCERPT_CHARS and _ALPHA_RE.search(excerpt):
            found.append(Quotation(text=inner, excerpt=excerpt, start=start, end=end, delimited=False))
    found.sort(key=lambda q: q.start)
    return tuple(found)


def strip_quotations(text: str) -> str:
    """``text`` with every quotation span replaced by a placeholder."""
    out: list[str] = []
    cursor = 0
    for start, end, _inner in _iter_quotes(text):
        out.append(text[cursor:start])
        out.append(" [quotation] ")
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


# --------------------------------------------------------------- sentences


#: How far before a boundary the abbreviation test reads: longer than any abbreviation with its closing marks,
#: so a word cut at the window's edge is known to be neither an abbreviation nor a one-letter token.
_ABBREVIATION_WINDOW = 48


def _is_abbreviation(prefix: str) -> bool:
    """True when ``prefix`` ends in an abbreviation or a one-letter token (closing marks
    ignored). Only the last :data:`_ABBREVIATION_WINDOW` characters are read: a word that
    runs past the window's edge is longer than any abbreviation, so the answer is the same."""
    tail = prefix[-_ABBREVIATION_WINDOW:].rstrip("\"”’')]»")
    m = _LAST_WORD_RE.search(tail)
    if m is None:
        return False
    if m.start() == 0 and len(prefix) > _ABBREVIATION_WINDOW:
        return False  # the word reaches the window's edge: longer than any abbreviation, not one letter
    word = m.group(1)
    return len(word) == 1 or word.lower() in _ABBREVIATIONS


def _span_index(spans: list[tuple[int, int]]) -> tuple[list[int], list[int]]:
    """``(starts, furthest_end)`` over ``spans`` sorted by start: ``furthest_end[i]`` is the
    largest close offset among ``spans[: i + 1]``, so whether a boundary lies inside an open
    quotation (it would cut the quotation in two) is one bisection whatever the number of
    quotations in the paragraph."""
    starts: list[int] = []
    furthest: list[int] = []
    best = -1
    for s, e in spans:
        starts.append(s)
        best = max(best, e)
        furthest.append(best)
    return starts, furthest


def split_sentences(paragraph: str) -> list[str]:
    """Split ``paragraph`` into sentences (see module docstring).

    A pasted JSON span glued to the prose (``... answers. {"receipt_id": ...} The narrator
    ...``) is one sentence of its own: the prose before it and after it are split as prose,
    and the JSON's strings are not read as quotation marks."""
    text = " ".join(paragraph.split())
    if not text:
        return []
    json_spans = sorted(find_json_spans(text))
    masked = mask_json_spans(text) if json_spans else text
    spans = sorted((s, e) for s, e, _ in _iter_quotes(masked))
    starts, furthest_end = _span_index(spans)
    json_starts, json_furthest = _span_index(json_spans)
    json_cuts = sorted({c for a, b in json_spans for c in (a, b)})
    cuts: set[int] = set(json_cuts)
    last_cut = 0  # the latest boundary cut so far; boundaries are visited in order, so it is the nearest one
    for m in _BOUNDARY_RE.finditer(masked):
        if spans and bisect_left(starts, m.start()) > 0 and furthest_end[bisect_left(starts, m.start()) - 1] > m.end():
            continue  # inside an open quotation
        if json_spans and bisect_left(json_starts, m.start()) > 0 and json_furthest[bisect_left(json_starts, m.start()) - 1] > m.start():
            continue  # inside a pasted JSON span
        k = bisect_right(json_cuts, m.start())
        prev = max(last_cut, json_cuts[k - 1] if k else 0)
        if _is_abbreviation(masked[prev:m.start()]):
            continue
        cuts.add(m.end())
        last_cut = m.end()
    pieces: list[str] = []
    start = 0
    for cut in sorted(cuts):
        piece = text[start:cut].strip()
        if piece:
            pieces.append(piece)
        start = cut
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return [p for p in pieces if p]


# --------------------------------------------------------------- blocks


def _block_quotations(block: str) -> int:
    return sum(1 for _ in _iter_quotes(" ".join(block.split())))


def is_meta_sentence(sentence: str) -> bool:
    """True for a sentence that is never part of the argument wherever it stands: it
    certifies the answer's own checking (``SELF_CERT_RE`` and the semantic rule), narrates
    an internal step (``META_NARRATION_RE``) or has the shape of JSON. The vocabulary is
    searched with the sentence's quotations masked, so quoting a colleague's label is not
    the quoter's self-report; the JSON shape is judged on the full text."""
    if is_json_shaped(sentence):
        return True
    plain = strip_quotations(sentence)
    return is_self_certification(plain) or bool(META_NARRATION_RE.search(plain))


def is_note_only(sentence: str) -> bool:
    """True for a sentence that is nothing but a label about the text (a from-memory
    disclaimer, a task-setting note, a self-certification) and carries no quotation: its
    substance is empty once the label clauses are removed (:func:`~epinoic_logic.adapters.markdown.split_note_clauses`).
    A substantive sentence with the label inline is not a note; it keeps its role and the
    label travels as an assumption."""
    if _iter_quotes_any(sentence):
        return False
    core, _notes = split_note_clauses(sentence)
    return not core


def _iter_quotes_any(sentence: str) -> bool:
    return any(True for _ in _iter_quotes(sentence))


def is_meta_block(block: str) -> bool:
    """True for a pasted JSON block, a block whose every sentence is meta-text, a
    quotation-free block whose every sentence is a note about the text (from-memory label,
    task-setting note, self-certification; whatever its length), or a short quotation-free
    block that is a check label or narrates internal steps."""
    s = block.strip()
    if not s:
        return False
    if is_json_block(s):
        return True
    sentences = split_sentences(s)
    if sentences and all(is_meta_sentence(x) for x in sentences):
        return True
    if _block_quotations(s):
        return False
    # a block that is only notes about the text: no word cap, a long disclaimer is still not an argument
    if sentences and all(is_note_only(x) for x in sentences):
        return True
    if word_count(s) > _MAX_META_WORDS:
        return False
    return bool(META_LABEL_RE.match(s) or _ALLCAPS_LABEL_RE.match(s) or META_NARRATION_RE.search(s))


def is_list_block(block: str) -> bool:
    """True for a bullet list, a markdown heading, or a short title-like line."""
    lines = [line for line in block.splitlines() if line.strip()]
    if lines and all(_BULLET_RE.match(line) for line in lines):
        return True
    s = block.strip()
    if _HEADING_RE.match(s):
        return True
    if _block_quotations(s):
        return False
    words = word_count(s)
    if s.endswith(":") and words <= _MAX_HEADING_WORDS:
        return True
    return words <= _MAX_HEADING_WORDS and not _TERMINAL_RE.search(s)


def _role_for(index: int, sentence: str, kind: ParagraphKind) -> ClaimRole:
    """Role of the ``index``-th (1-based) non-meta sentence of a paragraph of ``kind``."""
    if kind == "thesis":
        return "thesis"
    if kind == "conclusion":
        return "link"
    if kind in ("meta", "list"):
        return "other"
    if index == 1:
        return "point"
    if _LINK_RE.match(sentence):
        return "link"
    if _DEVICE_RE.search(strip_quotations(sentence)):
        return "device"
    return "interpretation"


def _list_sentences(block: str) -> list[str]:
    """Sentences of a list/heading paragraph: one or more per line, bullet markers removed."""
    out: list[str] = []
    for line in block.splitlines():
        stripped = _BULLET_RE.sub("", line).strip()
        if stripped:
            out.extend(split_sentences(stripped))
    return out


def _prose_kinds(blocks: list[str]) -> list[ParagraphKind]:
    """Thesis / body / conclusion decision over the prose blocks only (see module docstring)."""
    n = len(blocks)
    kinds: list[ParagraphKind] = ["body"] * n
    if n < 2:
        return kinds
    quotes = [_block_quotations(b) for b in blocks]
    words = [word_count(b) for b in blocks]
    if quotes[0] < 2 and (n >= 3 or (quotes[0] == 0 and words[0] < words[1])):
        kinds[0] = "thesis"
    if n >= 3 and quotes[-1] < 2 and _CONCLUSION_RE.match(blocks[-1].lstrip()):
        kinds[-1] = "conclusion"
    return kinds


def segment(text: str) -> tuple[Paragraph, ...]:
    """Deterministically segment an answer into paragraphs, sentences and quotations."""
    # CRLF and a lone CR are line breaks (a CR-only paragraph break is a paragraph break, as the channel counts it);
    # a byte-order mark is not a word
    normalised = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    raw = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(normalised) if p.strip()]
    units: list[tuple[ParagraphKind, str]] = []
    for block in raw:
        if is_meta_block(block):
            units.append(("meta", block))
        elif is_list_block(block):
            if units and units[-1][0] == "list":
                units[-1] = ("list", units[-1][1] + "\n\n" + block)
            else:
                units.append(("list", block))
        else:
            units.append(("body", block))
    prose_kinds = iter(_prose_kinds([b for k, b in units if k == "body"]))
    single_prose = sum(1 for k, _b in units if k == "body") == 1
    paragraphs: list[Paragraph] = []
    for i, (kind, block) in enumerate(units, start=1):
        if kind == "body":
            kind = next(prose_kinds)
        raw_sentences = _list_sentences(block) if kind == "list" else split_sentences(block)
        sentences: list[Sentence] = []
        argued = 0  # sentences that are neither meta nor a note: the first of them is the point
        for j, s in enumerate(raw_sentences, start=1):
            notes: tuple[str, ...] = ()
            if kind in ("thesis", "body", "conclusion") and is_meta_sentence(s):
                role: ClaimRole = "other"
            elif kind in ("thesis", "body", "conclusion") and is_note_only(s):
                role = "other"  # a label about the text is never the point, wherever it stands
            else:
                if kind in ("thesis", "body", "conclusion"):
                    notes = tuple(split_note_clauses(s)[1])  # an inline label is kept out of the role
                argued += 1
                role = _role_for(argued, s, kind)
            sentences.append(Sentence(index=j, text=s, role=role, quotations=find_quotations(s), notes=notes))
        if kind == "body" and single_prose:
            sentences = _closing_link(sentences)
        paragraphs.append(Paragraph(index=i, kind=kind, text=block, sentences=tuple(sentences)))
    return tuple(paragraphs)


def _closing_link(sentences: list[Sentence]) -> list[Sentence]:
    """In a single-paragraph answer, the closing argued sentence that draws a claim over the
    paragraph's evidence ("... the clear air, the sleeping houses and the calm suggest that the poem
    captures a suspended morning ...") is the paragraph's link, signpost or not, as long as it is
    the writer's own claim (no quotation) and not the point."""
    argued = [k for k, s in enumerate(sentences) if s.role != "other"]
    if len(argued) < 3:
        return sentences
    k = argued[-1]
    last = sentences[k]
    if last.role in ("interpretation", "device") and not last.quotations and _CLOSING_CLAIM_RE.search(last.text):
        sentences = list(sentences)
        sentences[k] = replace(last, role="link")
    return sentences


# -------------------------------------------------------------------- claims


def is_peer_document(doc: SuppliedText) -> bool:
    """True for a colleague's report relayed through the hub (``peer:<task>``, authored by a specialist agent)."""
    return doc.document_id.startswith(_PEER_DOCUMENT_PREFIX) or bool(doc.author and doc.author.endswith("-specialist"))


def _document_names(doc: SuppliedText) -> list[str]:
    """The ways a sentence can name ``doc``: its author (full name and surname), its title
    (up to any parenthesis or comma) and, for a relayed peer report, the specialist's
    name with the hyphen spelled as a space ("history-specialist" -> "history specialist")."""
    names: list[str] = []
    if doc.author:
        author = doc.author.strip()
        names.append(author)
        if author.endswith("-specialist"):
            names.append(author.replace("-", " "))
        parts = author.split()
        if len(parts) > 1 and len(parts[-1]) >= 3 and parts[-1][0].isupper():
            names.append(parts[-1])
    if doc.title and not is_peer_document(doc):
        title = re.split(r"[(:,]", doc.title)[0].strip()
        if len(title) >= 3:
            names.append(title)
    return [n for n in names if n]


def documents_named(plain_sentence: str, docs: dict[str, SuppliedText]) -> list[str]:
    """Ids of the supplied texts that ``plain_sentence`` (quotations already masked) names,
    by author, surname, title or peer-specialist name, in supplied order. A generic cue
    ("the poem", "the extract") names the one literary (non-peer) text when exactly one
    was supplied."""
    named: list[str] = []
    for doc_id, doc in docs.items():
        for name in _document_names(doc):
            if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", plain_sentence, re.IGNORECASE):
                named.append(doc_id)
                break
    literary = [doc_id for doc_id, doc in docs.items() if not is_peer_document(doc)]
    if len(literary) == 1 and literary[0] not in named and _TEXT_CUE_RE.search(plain_sentence):
        named.append(literary[0])
    return named


def long_elision_of(excerpt: str, document_id: str, docs: dict[str, SuppliedText]) -> Optional[str]:
    """When ``excerpt`` is an elided quotation whose fragments all occur in order in the
    supplied text ``document_id`` but span more than the elision window, the difference as
    the grounding module words it (``locate_long_elision``); else ``None``. The words occur, so
    this is a form difference (the channel's INT-REQ-010), never an invented quotation."""
    doc = docs.get(document_id)
    if doc is None:
        return None
    check = check_excerpt(excerpt, document_id, docs)
    if check.status == "found_long_elision":  # the shared check names the case itself
        return check.detail
    if check.status != "not_found":
        return None
    found = locate_long_elision(check.excerpt_checked or excerpt, doc.text, document_id=document_id)
    if found is None:
        return None
    near, difference = found
    return f"the words occur in the document (characters {near.start}-{near.end}) but the quotation {difference}"


def excerpt_located(excerpt: str, document_id: str, docs: dict[str, SuppliedText]) -> bool:
    """True when ``excerpt`` was located in ``document_id`` in any recognised form, a long elision included."""
    return check_excerpt(excerpt, document_id, docs).located or long_elision_of(excerpt, document_id, docs) is not None


def text_under_analysis(docs: dict[str, SuppliedText]) -> Optional[str]:
    """The one literary (non-peer) supplied text, which an English analytical answer is about,
    or None when there are none or several. A relayed colleague's report is never it."""
    literary = [doc_id for doc_id, doc in docs.items() if not is_peer_document(doc)]
    return literary[0] if len(literary) == 1 else None


def _attribute(excerpt: str, named: list[str], docs: dict[str, SuppliedText], sentence: Optional[str] = None) -> tuple[Optional[str], list[str]]:
    """``(document_id, assumptions)`` for a quotation, by the rule every parser shares
    (:func:`~epinoic_logic.adapters.sources.attribute_excerpt`): the located text wins (the
    named one when several hold the words, the discrepancy recorded when the named one does
    not); a quotation located nowhere is credited to the one text the sentence names; when the
    sentence names several, to the one that governs the quotation in ``sentence`` (its
    possessive, the speaker of the reporting clause, the text named nearest before it:
    ``sources.governing_document``), so an altered quotation of a colleague in a sentence that
    also names the poet is still refuted by the hub; when the sentence names none, to the one
    literary text under analysis (so an altered quotation of the poem is still refuted by the
    hub); otherwise to no text, with the assumption that the core pack reports as unverifiable
    (``CORE-SRC-003``). Never to a text for being supplied first."""
    return attribute_excerpt(excerpt, named, docs, text_under_analysis=text_under_analysis(docs), sentence=sentence)


def _claim_text(text: str) -> str:
    return text if len(text) <= _MAX_CLAIM_TEXT_CHARS else text[: _MAX_CLAIM_TEXT_CHARS - 3] + "..."


def _note_assumptions(sentence: Sentence) -> list[str]:
    """The inline labels of ``sentence`` as claim assumptions (one per distinct label)."""
    return [f"the sentence carries the method's own label inline ('{n[:200]}'); the label is kept out of the claim's role and is not part of the argument"
            for n in sentence.notes]


#: Which claims are folded first when an answer exceeds the report's claim limit: a claim with a
#: source reference (a quotation the hub must check) is kept over interpretation and notes, and a
#: material claim (a point, thesis or link) is kept over both.
_FOLD_PRIORITY = {"material": 0, "evidence": 1, "supporting": 2}
#: A claim's source references are capped by the contract; the tail claim carries this many.
_MAX_TAIL_SOURCE_REFS = 32


def _fold_rank(claim: ClaimRecord) -> int:
    if claim.materiality == "material":
        return _FOLD_PRIORITY["material"]
    if claim.source_refs or claim.claim_role == "evidence":
        return _FOLD_PRIORITY["evidence"]
    return _FOLD_PRIORITY["supporting"]


def _fold_tail(claims: list[ClaimRecord], ids: dict[str, object]) -> tuple[list[ClaimRecord], list[str]]:
    """Fold the claims beyond the report's limit into one ``other`` tail claim and prune
    links to the folded claims, so an oversized answer is delivered, not rejected.

    Interpretation, device and note claims are folded before evidence claims, and evidence
    before material claims, each group from the end of the answer, so a quotation placed
    late in an oversized answer is still delivered as its own evidence claim and checked.
    When evidence claims must be folded all the same, their source references are carried
    on the tail claim (up to the contract's cap) so the hub still checks those quotations;
    the unresolved issue states how many claims and quotations were merged and how many
    quotations, if any, could not be carried.
    """
    if len(claims) <= _MAX_CLAIMS:
        return claims, []
    excess = len(claims) - (_MAX_CLAIMS - 1)
    order = sorted(range(len(claims)), key=lambda i: (-_fold_rank(claims[i]), -i))  # lowest priority first, latest first
    folded_idx = set(order[:excess])
    head = [c for i, c in enumerate(claims) if i not in folded_idx]
    tail = [c for i, c in enumerate(claims) if i in folded_idx]
    kept = {c.claim_id for c in head} | {TAIL_CLAIM_ID}
    pruned = [
        c.model_copy(update={
            "supporting_claim_ids": [s for s in c.supporting_claim_ids if s in kept],
            "parent_claim_id": c.parent_claim_id if c.parent_claim_id in kept else None,
        }) for c in head
    ]
    refs: list[SourceRef] = []
    seen_refs: set[tuple[str, str]] = set()
    for c in tail:
        for r in c.source_refs:
            key = (r.document_id, r.excerpt or "")
            if key not in seen_refs:
                seen_refs.add(key)
                refs.append(r)
    carried, dropped = refs[:_MAX_TAIL_SOURCE_REFS], refs[_MAX_TAIL_SOURCE_REFS:]
    folded_evidence = sum(1 for c in tail if c.claim_role == "evidence")
    assumptions: list[str] = []
    if carried:
        assumptions.append(f"{len(carried)} quotation(s) of the merged claims are carried as this claim's source references so the hub still checks them")
    if dropped:
        assumptions.append(f"{len(dropped)} further quotation(s) of the merged claims could not be carried and were not checked")
    pruned.append(ClaimRecord(
        **ids, claim_id=TAIL_CLAIM_ID, claim_text=_claim_text(" ".join(c.claim_text for c in tail)), claim_role="other",  # type: ignore[arg-type]
        proposed_claim_kind="unknown", materiality="supporting", certainty="possible", source_refs=carried, assumptions=assumptions,
    ))
    issue = (f"{len(tail)} claims beyond the report's claim limit ({_MAX_CLAIMS}) were merged into claim {TAIL_CLAIM_ID} "
             f"and were not individually roled or checked: {folded_evidence} of them were evidence claims with {len(refs)} quotation(s); "
             + (f"{len(carried)} quotation(s) are carried on the tail claim's source references for checking" if carried else "no quotation was merged")
             + (f" and {len(dropped)} quotation(s) were merged unchecked" if dropped else ""))
    return pruned, [issue]


def parse_response(
    text: str,
    *,
    request_id: str,
    task_id: str,
    report_id: str,
    subject: str = DEFAULT_SUBJECT,
    task_type: str,
    supplied_texts: list[SuppliedText],
    course_level: str = "unknown",
    agent_version: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> SpecialistReport:
    """Parse an English specialist answer into an immutable :class:`SpecialistReport`.

    ``text`` is kept verbatim as ``original_response`` and hashed. ``agent_id`` is the
    identity the hub states for the sender and is carried into the report unchanged
    (default ``english-specialist``), so the channel's identity checks see who actually
    answered. Claims are proposed by the rules in the module docstring; meta blocks
    propose none and list blocks propose evidence only. Raises :class:`AdapterError`
    when the text is empty or yields no sentences; claims beyond the report's limit are
    folded into a tail claim.
    """
    if not text or not text.strip():
        raise AdapterError("the specialist answer is empty")
    paragraphs = segment(text)
    if not any(p.sentences for p in paragraphs):
        raise AdapterError("the specialist answer yields no sentences")
    agent = agent_id or AGENT_ID
    docs = {t.document_id: t for t in supplied_texts}
    ids: dict[str, object] = dict(
        request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, agent_version=agent_version,
        subject=subject or DEFAULT_SUBJECT, course_level=course_level, task_type=task_type,
    )
    claims: list[ClaimRecord] = []
    unresolved: list[str] = []
    undelimited_paragraphs: list[int] = []

    def add(claim_id: str, claim_text: str, role: ClaimRole, *, at: Optional[int] = None, **fields: object) -> ClaimRecord:
        """Append (or insert at ``at``) one claim record built from the report identifiers."""
        claim = ClaimRecord(**ids, claim_id=claim_id, claim_text=_claim_text(claim_text), claim_role=role, **fields)  # type: ignore[arg-type]
        if at is None:
            claims.append(claim)
        else:
            claims.insert(at, claim)
        return claim

    pending_thesis: list[tuple[str, str, list[str]]] = []
    pending_conclusion: list[tuple[str, str, list[str]]] = []
    body_point_ids: list[str] = []
    inline_notes: dict[str, list[str]] = {}  # per sentence id: the method's own labels carried inline, recorded as assumptions

    for para in paragraphs:
        if not para.sentences or para.kind == "meta":
            continue  # meta-text is never part of the argument
        point_sentence = next((s for s in para.sentences if s.role == "point"), None) if para.kind == "body" else None
        point_id = f"p{para.index}-point" if point_sentence is not None else None
        paragraph_start = len(claims)
        evidence_ids: dict[str, str] = {}
        support_ids: list[str] = []
        pending_links: list[tuple[str, str, list[str]]] = []
        quotation_count = 0
        for sentence in para.sentences:
            sid = f"p{para.index}-s{sentence.index:02d}"
            if para.is_prose and sentence.role == "other":
                # self-certification, narrated checking or a JSON-shaped line: recorded, never argued, no source reference
                add(sid, sentence.text, "other", proposed_claim_kind="unknown", materiality="supporting", certainty="possible", parent_claim_id=None,
                    advisory_verification_status=_SELF_REPORT if (is_json_shaped(sentence.text) or is_self_certification(strip_quotations(sentence.text))) else None)
                continue
            plain = strip_quotations(sentence.text)
            named = documents_named(plain, docs)
            quote_ids: list[str] = []
            for q in sentence.quotations:
                qid = evidence_ids.get(q.excerpt)
                if qid is None:
                    quotation_count += 1
                    qid = f"p{para.index}-q{quotation_count:02d}"
                    if q.delimited:
                        doc_id, notes = _attribute(q.excerpt, named, docs, sentence.text)
                        refs = [SourceRef(document_id=doc_id, excerpt=q.excerpt)] if doc_id else []
                    else:
                        doc_id, refs = None, []
                        notes = ["the paragraph has an unbalanced quotation mark; this span could not be delimited and was not attributed to or checked against any text"]
                        if para.index not in undelimited_paragraphs:
                            undelimited_paragraphs.append(para.index)
                    add(
                        qid, f'"{q.text}"', "evidence",
                        proposed_claim_kind="factual", materiality="supporting", certainty="established" if q.delimited else "possible",
                        source_refs=refs, assumptions=notes, parent_claim_id=point_id,
                    )
                    evidence_ids[q.excerpt] = qid
                    support_ids.append(qid)
                quote_ids.append(qid)
            if para.kind == "list":
                continue  # lists propose evidence only
            if sentence is point_sentence:
                continue  # the point is inserted once its supports are known
            if quote_ids and not _ALPHA_RE.search(plain.replace("[quotation]", "")):
                continue  # a sentence that is nothing but a quotation is already the evidence claim; no interpretation to propose
            if not quote_ids and is_note_only(sentence.text):
                add(sid, sentence.text, "other", proposed_claim_kind="unknown", materiality="supporting", certainty="possible", parent_claim_id=point_id,
                    advisory_verification_status=_SELF_REPORT if is_self_certification(sentence.text) else None)
                continue  # a label about the text (from-memory note, task-setting note) is recorded but is not part of the argument
            inline_notes[sid] = _note_assumptions(sentence)
            if para.kind == "thesis":
                pending_thesis.append((sid, sentence.text, quote_ids))
            elif para.kind == "conclusion":
                pending_conclusion.append((sid, sentence.text, quote_ids))
            elif sentence.role == "link":
                pending_links.append((sid, sentence.text, quote_ids))
            else:
                add(
                    sid, sentence.text, sentence.role,
                    proposed_claim_kind="interpretive", materiality="supporting", certainty="probable",
                    supporting_claim_ids=quote_ids, parent_claim_id=point_id, assumptions=inline_notes[sid],
                )
                support_ids.append(sid)
        if point_id is not None and point_sentence is not None:
            add(
                point_id, point_sentence.text, "point", at=paragraph_start,
                proposed_claim_kind="unknown", materiality="material", certainty="probable",
                supporting_claim_ids=support_ids[:_MAX_CLAIMS],  # a point supports at most a report's worth of claims
                assumptions=_note_assumptions(point_sentence),
            )
            body_point_ids.append(point_id)
            for sid, stext, _quote_ids in pending_links:
                add(
                    sid, stext, "link",
                    proposed_claim_kind="unknown", materiality="material", certainty="probable",
                    supporting_claim_ids=[point_id, *support_ids][:_MAX_CLAIMS], parent_claim_id=point_id, assumptions=inline_notes.get(sid, []),
                )
    for sid, stext, quote_ids in pending_thesis:
        add(
            sid, stext, "thesis",
            proposed_claim_kind="unknown", materiality="material", certainty="probable",
            supporting_claim_ids=[*body_point_ids, *quote_ids][:_MAX_CLAIMS], assumptions=inline_notes.get(sid, []),
        )
    for sid, stext, quote_ids in pending_conclusion:
        add(
            sid, stext, "link",
            proposed_claim_kind="unknown", materiality="material", certainty="probable",
            supporting_claim_ids=[*body_point_ids, *quote_ids][:_MAX_CLAIMS], assumptions=inline_notes.get(sid, []),
        )

    assumptions = [
        "claims were proposed from prose by the english-specialist adapter's deterministic text rules; "
        "roles, links and certainty are parser proposals, not agent assertions",
        "a quoted span (double marks of any kind, or single marks around two or more words) is treated as a quotation of the "
        "supplied text; sentence punctuation inside the closing mark is not part of the recorded excerpt",
        "headings, bullet lists and meta-text blocks (labels such as 'VERIFIED:', pasted receipts) propose no argument claims; "
        "quotations inside lists are still recorded as evidence",
    ]
    if not docs and any(p.quotations for p in paragraphs):
        unresolved.append("no supplied text was given: quotations could not be attributed to a document")
    if any(p.kind == "meta" for p in paragraphs):
        unresolved.append("the answer contains meta-text (a check label, a narrated step or a pasted receipt); it was excluded from the argument")
    if undelimited_paragraphs:
        shown = ", ".join(str(i) for i in undelimited_paragraphs[:8])
        unresolved.append(f"paragraph(s) {shown} carry an unbalanced quotation mark; the span it opens or closes was recorded as an undelimited quotation and not checked against any text")
    claims, folded = _fold_tail(claims, ids)
    unresolved += folded
    return SpecialistReport(
        report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, agent_version=agent_version,
        subject=subject or DEFAULT_SUBJECT, course_level=course_level, task_type=task_type,  # type: ignore[arg-type]
        original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts),
        claims=claims, assumptions=assumptions, unresolved_issues=unresolved[:64], created_at=utc_now_rfc3339(),
    )
