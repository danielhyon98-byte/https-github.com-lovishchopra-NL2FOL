"""Heuristic parser for the English specialist's analytical prose.

The English specialist writes PETAL-style paragraphs: a point, then strands of
evidence (quotations) each carried through device, interpretation and effect,
closed by a link. It does not emit structured claims, so this adapter proposes
them from the prose with deterministic text rules. Everything it produces is a
*proposal*: roles, links and certainty are advisory inputs that the eligibility
policy and the engine treat as untrusted data.

Segmentation rules
------------------
* Blocks are separated by blank lines. Each block is classified by content:

  - ``meta``: a short block (at most 25 words, no quotation) that is a label such
    as ``VERIFIED: ...`` or ``Word count: 341``, an all-caps label followed by a
    colon, or narration of internal steps ("I have checked ..."). Meta blocks are
    never part of the argument: they propose no claims and support nothing. The
    structural checks flag them (``ES-META-001``).
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
  a full stop stays one quotation in one sentence.
* Quotations are double-quoted spans (straight or curly) and single-quoted spans of
  at least two words that open after whitespace or a bracket and close before
  whitespace or punctuation (so possessives and contractions are not quotations).
  Sentence punctuation written inside the closing mark (``"legitimate defense,"``)
  is not part of the quoted words and is stripped from the recorded excerpt.

Role rules (body paragraphs)
----------------------------
* first sentence -> ``point``;
* a sentence opening with ``Effectively``, ``Thus``, ``Ultimately``,
  ``Therefore``, ``Consequently`` or ``Hence`` -> ``link``;
* a sentence naming device vocabulary (diction, metaphor, paradox, juxtaposition,
  irony, imagery, syntax, semantic field, pronoun, verb, adjective, adverb, noun,
  declarative, parallel structure, employs) -> ``device``;
* every other sentence -> ``interpretation``;
* every quotation -> an ``evidence`` claim with a ``SourceRef`` into the supplied
  text that contains it (the first supplied text when none does).

Thesis sentences get role ``thesis`` and are supported by the body points;
conclusion sentences get role ``link`` and are likewise supported by the points.
A point is supported by its paragraph's evidence, device and interpretation
claims; a device or interpretation sentence is supported by the quotations it
contains; a link is supported by the point and the rest of its paragraph.

Claim ids are stable functions of position: ``p{paragraph}-point``,
``p{paragraph}-s{sentence}`` and ``p{paragraph}-q{quotation}``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, Literal, Optional

from ...ir.schema import SourceRef
from ...translate.common import utc_now_rfc3339
from ...translate.contracts import ClaimRecord, ClaimRole, SpecialistReport, SuppliedText, sha256_text
from ..base import AdapterError
from ..sources import check_excerpt, strip_trailing_punctuation, word_count

__all__ = [
    "AGENT_ID", "DEFAULT_SUBJECT", "ParagraphKind", "Quotation", "Sentence", "Paragraph",
    "segment", "split_sentences", "find_quotations", "strip_quotations", "parse_response", "LINK_SIGNPOSTS",
    "is_meta_block", "is_list_block", "META_LABEL_RE", "META_NARRATION_RE",
]

AGENT_ID = "english-specialist"
DEFAULT_SUBJECT = "English A: Literature"
ParagraphKind = Literal["thesis", "body", "conclusion", "meta", "list"]

LINK_SIGNPOSTS: tuple[str, ...] = ("Effectively", "Thus", "Ultimately", "Therefore", "Consequently", "Hence")
_CONCLUSION_SIGNPOSTS: tuple[str, ...] = LINK_SIGNPOSTS + ("In conclusion", "Overall", "In sum", "To conclude", "Finally")
_LINK_RE = re.compile(r"^(?:" + "|".join(re.escape(w) for w in LINK_SIGNPOSTS) + r")\b")
_CONCLUSION_RE = re.compile(r"^(?:" + "|".join(re.escape(w) for w in _CONCLUSION_SIGNPOSTS) + r")\b")
_DEVICE_RE = re.compile(
    r"\b(?:diction|metaphor\w*|paradox\w*|juxtapos\w*|iron(?:y|ic\w*)|imagery|syntax|syntactic\w*|"
    r"semantic field\w*|pronouns?|verbs?|adjectives?|adverbs?|nouns?|declaratives?|parallel structure|employs)\b",
    re.IGNORECASE,
)
# Groups: 1 straight double, 2 curly double, 3 straight single, 4 curly single.
_QUOTE_RE = re.compile(
    r'"([^"\n]+)"'
    r"|“([^”\n]+)”"
    r"|(?:(?<=[\s(\[—–-])|^)'([^'\n]{2,}?[^\s'])'(?=[\s.,;:!?)\]]|$)"
    r"|(?:(?<=[\s(\[—–-])|^)‘([^’\n]{2,}?[^\s’])’(?=[\s.,;:!?)\]]|$)"
)
_SINGLE_QUOTE_GROUPS = (3, 4)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
_BOUNDARY_RE = re.compile(r"[.!?]+[\"”’')\]]*(?=\s+[\"“‘(\[]?[A-ZÀ-ÖØ-Þ])")
_TERMINAL_RE = re.compile(r"[.!?][\"”’')\]]*$")
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
_MAX_META_WORDS = 25
_MAX_HEADING_WORDS = 12
_MAX_EXCERPT_CHARS = 2000
_MAX_CLAIM_TEXT_CHARS = 4000
_MAX_CLAIMS = 512


@dataclass(frozen=True)
class Quotation:
    """A quoted span inside a sentence."""

    text: str      #: the words as written between the quotation marks
    excerpt: str   #: the words without trailing sentence punctuation
    start: int     #: offset of the opening mark within the sentence
    end: int       #: offset just past the closing mark

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
    """Yield ``(start, end, inner)`` for every quotation span of ``text`` in order."""
    for m in _QUOTE_RE.finditer(text):
        group = m.lastindex or 1
        inner = m.group(group)
        if inner is None:
            continue
        if group in _SINGLE_QUOTE_GROUPS and len(inner.split()) < 2:
            continue  # a single-quoted single word is too close to an apostrophe to trust
        yield m.start(), m.end(), inner


def find_quotations(sentence: str) -> tuple[Quotation, ...]:
    """Quoted spans of ``sentence`` in order (see the module docstring for the rules)."""
    found: list[Quotation] = []
    for start, end, inner in _iter_quotes(sentence):
        excerpt = strip_trailing_punctuation(inner)
        if not excerpt or len(excerpt) > _MAX_EXCERPT_CHARS:
            continue
        found.append(Quotation(text=inner, excerpt=excerpt, start=start, end=end))
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


def _is_abbreviation(prefix: str) -> bool:
    m = _LAST_WORD_RE.search(prefix.rstrip("\"”’')]"))
    if m is None:
        return False
    word = m.group(1)
    return len(word) == 1 or word.lower() in _ABBREVIATIONS


def _inside_quotation(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """True when a boundary at ``start``-``end`` lies inside an open quotation span
    (it ends before the span's closing mark, so the quotation would be cut in two)."""
    return any(s < start and end < e for s, e in spans)


def split_sentences(paragraph: str) -> list[str]:
    """Split ``paragraph`` into sentences (see module docstring)."""
    text = " ".join(paragraph.split())
    if not text:
        return []
    spans = [(s, e) for s, e, _ in _iter_quotes(text)]
    pieces: list[str] = []
    start = 0
    for m in _BOUNDARY_RE.finditer(text):
        if _inside_quotation(m.start(), m.end(), spans):
            continue
        if _is_abbreviation(text[start:m.start()]):
            continue
        pieces.append(text[start:m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return [p for p in pieces if p]


# --------------------------------------------------------------- blocks


def _block_quotations(block: str) -> int:
    return sum(1 for _ in _iter_quotes(" ".join(block.split())))


def is_meta_block(block: str) -> bool:
    """True for a short quotation-free block that is a check label or narrates internal steps."""
    s = block.strip()
    if not s or _block_quotations(s) or word_count(s) > _MAX_META_WORDS:
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
    raw = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text.replace("\r\n", "\n")) if p.strip()]
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
    paragraphs: list[Paragraph] = []
    for i, (kind, block) in enumerate(units, start=1):
        if kind == "body":
            kind = next(prose_kinds)
        raw_sentences = _list_sentences(block) if kind == "list" else split_sentences(block)
        sentences = tuple(
            Sentence(index=j, text=s, role=_role_for(j, s, kind), quotations=find_quotations(s))
            for j, s in enumerate(raw_sentences, start=1)
        )
        paragraphs.append(Paragraph(index=i, kind=kind, text=block, sentences=sentences))
    return tuple(paragraphs)


# -------------------------------------------------------------------- claims


def _document_for(excerpt: str, docs: dict[str, SuppliedText]) -> Optional[str]:
    """The supplied text in which ``excerpt`` was located (in any form), else the first one."""
    for doc_id in docs:
        if check_excerpt(excerpt, doc_id, docs).located:
            return doc_id
    return next(iter(docs), None)


def _claim_text(text: str) -> str:
    return text if len(text) <= _MAX_CLAIM_TEXT_CHARS else text[: _MAX_CLAIM_TEXT_CHARS - 3] + "..."


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
) -> SpecialistReport:
    """Parse an English specialist answer into an immutable :class:`SpecialistReport`.

    ``text`` is kept verbatim as ``original_response`` and hashed. Claims are
    proposed by the rules in the module docstring; meta blocks propose none and list
    blocks propose evidence only. Raises :class:`AdapterError` when the text is
    empty, yields no sentences, or yields more claims than a report may carry.
    """
    if not text or not text.strip():
        raise AdapterError("the specialist answer is empty")
    paragraphs = segment(text)
    if not any(p.sentences for p in paragraphs):
        raise AdapterError("the specialist answer yields no sentences")
    docs = {t.document_id: t for t in supplied_texts}
    ids: dict[str, object] = dict(
        request_id=request_id, task_id=task_id, report_id=report_id, agent_id=AGENT_ID, agent_version=agent_version,
        subject=subject or DEFAULT_SUBJECT, course_level=course_level, task_type=task_type,
    )
    claims: list[ClaimRecord] = []

    def add(claim_id: str, claim_text: str, role: ClaimRole, *, at: Optional[int] = None, **fields: object) -> ClaimRecord:
        """Append (or insert at ``at``) one claim record built from the report identifiers."""
        if len(claims) >= _MAX_CLAIMS:
            raise AdapterError("the answer yields more claims than a report may carry")
        claim = ClaimRecord(**ids, claim_id=claim_id, claim_text=_claim_text(claim_text), claim_role=role, **fields)  # type: ignore[arg-type]
        if at is None:
            claims.append(claim)
        else:
            claims.insert(at, claim)
        return claim

    pending_thesis: list[tuple[str, str, list[str]]] = []
    pending_conclusion: list[tuple[str, str, list[str]]] = []
    body_point_ids: list[str] = []

    for para in paragraphs:
        if not para.sentences or para.kind == "meta":
            continue  # meta-text is never part of the argument
        point_id = f"p{para.index}-point" if para.kind == "body" else None
        paragraph_start = len(claims)
        evidence_ids: dict[str, str] = {}
        support_ids: list[str] = []
        pending_links: list[tuple[str, str, list[str]]] = []
        quotation_count = 0
        for sentence in para.sentences:
            quote_ids: list[str] = []
            for q in sentence.quotations:
                qid = evidence_ids.get(q.excerpt)
                if qid is None:
                    quotation_count += 1
                    qid = f"p{para.index}-q{quotation_count:02d}"
                    doc_id = _document_for(q.excerpt, docs)
                    add(
                        qid, f'"{q.text}"', "evidence",
                        proposed_claim_kind="factual", materiality="supporting", certainty="established",
                        source_refs=[SourceRef(document_id=doc_id, excerpt=q.excerpt)] if doc_id else [],
                        parent_claim_id=point_id,
                    )
                    evidence_ids[q.excerpt] = qid
                    support_ids.append(qid)
                quote_ids.append(qid)
            if para.kind == "list":
                continue  # lists propose evidence only
            if para.kind == "body" and sentence.index == 1:
                continue  # the point is inserted once its supports are known
            sid = f"p{para.index}-s{sentence.index:02d}"
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
                    supporting_claim_ids=quote_ids, parent_claim_id=point_id,
                )
                support_ids.append(sid)
        if point_id is not None:
            add(
                point_id, para.sentences[0].text, "point", at=paragraph_start,
                proposed_claim_kind="unknown", materiality="material", certainty="probable",
                supporting_claim_ids=support_ids,
            )
            body_point_ids.append(point_id)
            for sid, stext, _quote_ids in pending_links:
                add(
                    sid, stext, "link",
                    proposed_claim_kind="unknown", materiality="material", certainty="probable",
                    supporting_claim_ids=[point_id, *support_ids], parent_claim_id=point_id,
                )
    for sid, stext, quote_ids in pending_thesis:
        add(
            sid, stext, "thesis",
            proposed_claim_kind="unknown", materiality="material", certainty="probable",
            supporting_claim_ids=[*body_point_ids, *quote_ids],
        )
    for sid, stext, quote_ids in pending_conclusion:
        add(
            sid, stext, "link",
            proposed_claim_kind="unknown", materiality="material", certainty="probable",
            supporting_claim_ids=[*body_point_ids, *quote_ids],
        )

    assumptions = [
        "claims were proposed from prose by the english-specialist adapter's deterministic text rules; "
        "roles, links and certainty are parser proposals, not agent assertions",
        "a quoted span (double marks, or single marks around two or more words) is treated as a quotation of the "
        "supplied text; sentence punctuation inside the closing mark is not part of the recorded excerpt",
        "headings, bullet lists and meta-text blocks (labels such as 'VERIFIED:') propose no argument claims; "
        "quotations inside lists are still recorded as evidence",
    ]
    unresolved: list[str] = []
    if not docs and any(p.quotations for p in paragraphs):
        unresolved.append("no supplied text was given: quotations could not be attributed to a document")
    if any(p.kind == "meta" for p in paragraphs):
        unresolved.append("the answer contains meta-text (a check label or narrated step); it was excluded from the argument")
    return SpecialistReport(
        report_id=report_id, request_id=request_id, task_id=task_id, agent_id=AGENT_ID, agent_version=agent_version,
        subject=subject or DEFAULT_SUBJECT, course_level=course_level, task_type=task_type,  # type: ignore[arg-type]
        original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts),
        claims=claims, assumptions=assumptions, unresolved_issues=unresolved, created_at=utc_now_rfc3339(),
    )
