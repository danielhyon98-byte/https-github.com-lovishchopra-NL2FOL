"""Heuristic parser for the English specialist's analytical prose.

The English specialist writes PETAL-style paragraphs: a point, then strands of
evidence (quotations) each carried through device, interpretation and effect,
closed by a link. It does not emit structured claims, so this adapter proposes
them from the prose with deterministic text rules. Everything it produces is a
*proposal*: roles, links and certainty are advisory inputs that the eligibility
policy and the engine treat as untrusted data.

Segmentation rules
------------------
* Paragraphs are separated by blank lines. A single paragraph is a body paragraph.
  In a multi-paragraph answer the first paragraph is the thesis; when there are at
  least three paragraphs and the last opens with a concluding signpost
  (``Ultimately``, ``Thus``, ``In conclusion`` ...) it is the conclusion.
* Sentences end at ``.``, ``!`` or ``?`` (closing quotation marks may follow) when
  the next word starts with a capital letter; one-letter tokens and common
  abbreviations (``l.``, ``ll.``, ``p.``, ``Mr.`` ...) never end a sentence.
* Double-quoted spans (straight or curly) are quotations. Sentence punctuation
  written inside the closing mark (``"legitimate defense,"``) is not part of the
  quoted words and is stripped from the recorded excerpt.

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
from typing import Literal, Optional

from ...ir.schema import SourceRef
from ...translate.common import utc_now_rfc3339
from ...translate.contracts import ClaimRecord, ClaimRole, SpecialistReport, SuppliedText, sha256_text
from ..base import AdapterError
from ..sources import check_excerpt, strip_trailing_punctuation, word_count

__all__ = [
    "AGENT_ID", "DEFAULT_SUBJECT", "ParagraphKind", "Quotation", "Sentence", "Paragraph",
    "segment", "split_sentences", "find_quotations", "strip_quotations", "parse_response", "LINK_SIGNPOSTS",
]

AGENT_ID = "english-specialist"
DEFAULT_SUBJECT = "English A: Literature"
ParagraphKind = Literal["thesis", "body", "conclusion"]

LINK_SIGNPOSTS: tuple[str, ...] = ("Effectively", "Thus", "Ultimately", "Therefore", "Consequently", "Hence")
_CONCLUSION_SIGNPOSTS: tuple[str, ...] = LINK_SIGNPOSTS + ("In conclusion", "Overall", "In sum", "To conclude", "Finally")
_LINK_RE = re.compile(r"^(?:" + "|".join(re.escape(w) for w in LINK_SIGNPOSTS) + r")\b")
_CONCLUSION_RE = re.compile(r"^(?:" + "|".join(re.escape(w) for w in _CONCLUSION_SIGNPOSTS) + r")\b")
_DEVICE_RE = re.compile(
    r"\b(?:diction|metaphor\w*|paradox\w*|juxtapos\w*|iron(?:y|ic\w*)|imagery|syntax|syntactic\w*|"
    r"semantic field\w*|pronouns?|verbs?|adjectives?|adverbs?|nouns?|declaratives?|parallel structure|employs)\b",
    re.IGNORECASE,
)
_QUOTE_RE = re.compile(r'"([^"\n]+)"|“([^”\n]+)”')
_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
_BOUNDARY_RE = re.compile(r"[.!?]+[\"”’')\]]*(?=\s+[\"“‘(\[]?[A-ZÀ-ÖØ-Þ])")
_LAST_WORD_RE = re.compile(r"([A-Za-zÀ-ÿ]+)\.?$")
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "st", "vs", "etc", "cf", "no", "l", "ll", "p", "pp", "ch", "vol", "ed", "eds",
    "trans", "fig", "sc", "e.g", "i.e", "ibid", "op", "cit", "prof", "sr", "jr",
})
_MAX_EXCERPT_CHARS = 2000
_MAX_CLAIM_TEXT_CHARS = 4000
_MAX_CLAIMS = 512


@dataclass(frozen=True)
class Quotation:
    """A double-quoted span inside a sentence."""

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
    """One paragraph of the answer, classified as thesis, body or conclusion."""

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


# --------------------------------------------------------------- segmentation


def find_quotations(sentence: str) -> tuple[Quotation, ...]:
    """Double-quoted spans of ``sentence`` in order (straight or curly marks)."""
    found: list[Quotation] = []
    for m in _QUOTE_RE.finditer(sentence):
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        excerpt = strip_trailing_punctuation(inner)
        if not excerpt or len(excerpt) > _MAX_EXCERPT_CHARS:
            continue
        found.append(Quotation(text=inner, excerpt=excerpt, start=m.start(), end=m.end()))
    return tuple(found)


def strip_quotations(text: str) -> str:
    """``text`` with every double-quoted span replaced by a placeholder."""
    return _QUOTE_RE.sub(" [quotation] ", text)


def _is_abbreviation(prefix: str) -> bool:
    m = _LAST_WORD_RE.search(prefix.rstrip("\"”’')]"))
    if m is None:
        return False
    word = m.group(1)
    return len(word) == 1 or word.lower() in _ABBREVIATIONS


def split_sentences(paragraph: str) -> list[str]:
    """Split ``paragraph`` into sentences (see module docstring)."""
    text = " ".join(paragraph.split())
    if not text:
        return []
    pieces: list[str] = []
    start = 0
    for m in _BOUNDARY_RE.finditer(text):
        if _is_abbreviation(text[start:m.start()]):
            continue
        pieces.append(text[start:m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return [p for p in pieces if p]


def _role_for(index: int, sentence: str, kind: ParagraphKind) -> ClaimRole:
    if kind == "thesis":
        return "thesis"
    if kind == "conclusion":
        return "link"
    if index == 1:
        return "point"
    if _LINK_RE.match(sentence):
        return "link"
    if _DEVICE_RE.search(strip_quotations(sentence)):
        return "device"
    return "interpretation"


def segment(text: str) -> tuple[Paragraph, ...]:
    """Deterministically segment an answer into paragraphs, sentences and quotations."""
    raw = [p for p in _PARAGRAPH_SPLIT_RE.split(text.replace("\r\n", "\n")) if p.strip()]
    kinds: list[ParagraphKind] = ["body"] * len(raw)
    if len(raw) >= 2:
        kinds[0] = "thesis"
    if len(raw) >= 3 and _CONCLUSION_RE.match(raw[-1].lstrip()):
        kinds[-1] = "conclusion"
    paragraphs: list[Paragraph] = []
    for i, (block, kind) in enumerate(zip(raw, kinds), start=1):
        sentences = tuple(
            Sentence(index=j, text=s, role=_role_for(j, s, kind), quotations=find_quotations(s))
            for j, s in enumerate(split_sentences(block), start=1)
        )
        paragraphs.append(Paragraph(index=i, kind=kind, text=block.strip(), sentences=sentences))
    return tuple(paragraphs)


# -------------------------------------------------------------------- claims


def _document_for(excerpt: str, docs: dict[str, SuppliedText]) -> Optional[str]:
    """The supplied text that contains ``excerpt`` (exactly or as joined spans), else the first one."""
    for doc_id in docs:
        if check_excerpt(excerpt, doc_id, docs).status in ("found", "found_joined"):
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
    proposed by the rules in the module docstring. Raises :class:`AdapterError`
    when the text is empty, yields no sentences, or yields more claims than a
    report may carry.
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
        if not para.sentences:
            continue
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
        "a double-quoted span is treated as a quotation of the supplied text; sentence punctuation inside the "
        "closing mark is not part of the recorded excerpt",
    ]
    unresolved: list[str] = []
    if not docs and any(p.quotations for p in paragraphs):
        unresolved.append("no supplied text was given: quotations could not be attributed to a document")
    return SpecialistReport(
        report_id=report_id, request_id=request_id, task_id=task_id, agent_id=AGENT_ID, agent_version=agent_version,
        subject=subject or DEFAULT_SUBJECT, course_level=course_level, task_type=task_type,  # type: ignore[arg-type]
        original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts),
        claims=claims, assumptions=assumptions, unresolved_issues=unresolved, created_at=utc_now_rfc3339(),
    )
