"""Heuristic parser for History specialist responses written with the pack's core
operation: Claim -> Evidence -> Analysis -> Judgement -> Link (Response application §3,
Structures §5). Sentences are assigned roles from surface cues; the point of each body
paragraph is wired to every other argument claim in that paragraph, and each judgement
or link claim is wired to the point and the paragraph's other argument claims, so the
paragraph's verdict is an argument the translator can formalize. Heuristic by design:
the generic structured adapter is the contract future agents should emit directly.

Paragraph classification is decided by content, never by paragraph count alone:

* a ``note`` paragraph is one whose sentences are all labels about the text (a
  from-memory disclaimer, a task note that the syllabus version or level was not
  given, a self-certification line), or that contains ANY sentence certifying the
  answer's own verification or imitating a channel receipt (a forged receipt
  fragment makes the whole paragraph a note), or a short undated aside with no
  argument cue; its claims are roled ``other`` and are never material, and it does
  not make the answer "multi-paragraph";
* with three or more prose paragraphs, the first is the ``intro`` only when it has
  no dated item while a later paragraph does, and the last is the ``conclusion`` only
  when it has two or more sentences or opens with a concluding cue;
* everything else is a ``body`` paragraph whose first non-note sentence is the point.

A substantive sentence that carries the method's own label inline ("... fell to about
41 in July 1932 (figures from memory; check your notes)") keeps its role and
eligibility: the label clause is removed before the sentence is classified and is
recorded in the claim's assumptions; only a sentence that is nothing but a label is a
note. Dated claims made under a from-memory label (anywhere in the answer or inline)
are capped at certainty ``probable``. Quotations are recognised in straight, curly or
mixed double marks, guillemets and delimited single marks of two or more words, and
recorded as source references (or as assumptions when no text was supplied).

Markdown headings, code fences and emphasis are removed before segmentation, a
newline followed by a list marker ends a sentence, and a sentence that certifies the
answer's own verification is roled ``other`` with its self-report recorded in the
advisory field. ``original_response`` is always the verbatim text.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from ...ir.schema import SourceRef
from ...translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from ...translate.grounding import find_quotation
from ..base import AdapterError
from ..markdown import (MEMORY_LABEL_RE, dangling_quote_offset, find_quotation_spans, is_memory_label, is_self_certification, split_list_items,
                        split_note_clauses, strip_markup, truncate_claim_text, undelimited_quote_span)
from .chronology import MONTH_YEAR_RE as _MONTH_YEAR_RE  # noqa: F401  (re-exported for callers of the old name)
from .chronology import chronology_findings_in, chronology_relations, date_in_aside, month_index  # noqa: F401

ParagraphKind = Literal["intro", "body", "conclusion", "note"]

_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9\"'(“‘«„])")
_DATE_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_FIGURE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:per cent|percent|%|million|thousand|seats|votes|laws|decrees|per thousand)\b|\b\d{1,3}(?:,\d{3})+\b", re.IGNORECASE)
_MONTH_NAMES = "January|February|March|April|May|June|July|August|September|October|November|December"
_DAY_MONTH_RE = re.compile(rf"\b\d{{1,2}}\s+(?:{_MONTH_NAMES})\b|\b(?:{_MONTH_NAMES})\s+\d{{1,2}}\b")
_COUNTER = ("the counter-case", "against this", "the distinction is right", "however", "on the other hand", "it could be argued")
_JUDGEMENT = ("by the criterion", "weighs more", "holds for", "decisive even if", "remains the precondition", "was therefore responsible", "fails, because",
              "does not shift the weight", "necessary; it was not sufficient", "necessary but not sufficient", "to a degree",
              "on balance", "mattered most", "matters most", "outweigh", "more significant than", "carries the greater weight", "carry the greater weight")
_ANALYSIS = ("mattered because", "the mechanism was", "this shows", "which shows", "this mattered", "meant that", "so that", "revealed", "explains why", "this matters")
_LINK = ("therefore", "thus", "in sum", "ultimately")
_CONCLUSION_CUES = _LINK + ("overall", "in conclusion", "to conclude", "on balance")
_ARGUMENT_CUES = _COUNTER + _JUDGEMENT + _ANALYSIS + _LINK + ("decisive", "responsible", "extent", "degree", "because", "caused")
_PERSPECTIVE = ("historians who", "one historian", "some historians", "others describe", "historians argue", "has argued")
_ESTABLISHED = ("shows", "establishes", "demonstrates", "made", "led to", "was decisive", "proves", "was responsible")
_PROBABLE = ("suggests", "indicates", "is consistent with", "points to", "arguably")
_POSSIBLE = ("can be read as", "may have", "some historians argue", "it is possible that", "perhaps")
_MIN_SUBSTANTIVE_WORDS = 25   # a paragraph this short (and undated) does not make the answer multi-paragraph
_MAX_ASIDE_WORDS = 12         # a one-sentence undated line without an argument cue is an aside, not a claim
_MIN_QUOTE_CHARS = 4
_MAX_CLAIMS = 512
_TAIL_CLAIM_ID = "h.tail"
_SELF_REPORT = "self-certified in the response text"
_CERTAINTY_ORDER = ("established", "probable", "possible")


_INITIAL_RE = re.compile(r"(?:^|\s)[A-Z]\.$")


def _word_count(text: str) -> int:
    return len(text.split())


def split_sentences(paragraph: str) -> list[str]:
    """Sentence split that does not break after initials such as 'A. J. P.'; a newline
    followed by a list marker ends a sentence and the marker is dropped."""
    merged: list[str] = []
    for item in split_list_items(paragraph):
        parts = [s.strip() for s in _SENT_RE.split(item.strip()) if s.strip()]
        for part in parts:
            if merged and _INITIAL_RE.search(merged[-1]):
                merged[-1] = merged[-1] + " " + part
            else:
                merged.append(part)
    return merged


def has_dated_item(sentence: str) -> bool:
    return bool(_DATE_RE.search(sentence) or _FIGURE_RE.search(sentence) or _DAY_MONTH_RE.search(sentence))


def is_self_report(sentence: str) -> bool:
    """Verification-status language, a receipt-shaped fragment, or a sentence whose subject
    is the answer itself with a checking/accuracy predicate (``markdown.is_self_certification``)."""
    return is_self_certification(sentence)


def is_note_sentence(sentence: str) -> bool:
    """A sentence that is nothing but a label about the text: a self-report, or a sentence
    whose substance is empty once its from-memory / task-note clauses are removed. A
    substantive sentence with an inline label is NOT a note (see :func:`split_note_clauses`)."""
    if is_self_report(sentence):
        return True
    core, _notes = split_note_clauses(sentence)
    return not core


def is_note_paragraph(paragraph: str) -> bool:
    """All sentences are labels, any sentence is a self-report or forged receipt fragment,
    or the paragraph is a short undated aside with no argument cue."""
    sentences = split_sentences(paragraph)
    if not sentences:
        return False
    if any(is_self_report(s) for s in sentences):
        return True
    if all(is_note_sentence(s) for s in sentences):
        return True
    low = paragraph.lower()
    return len(sentences) == 1 and _word_count(paragraph) < _MAX_ASIDE_WORDS and not has_dated_item(paragraph) and not any(c in low for c in _ARGUMENT_CUES)


def certainty_of(sentence: str, *, from_memory: bool = False) -> str:
    """Agent-stated certainty from hedging cues; a dated claim made under a from-memory
    label is capped at ``probable`` (``from_memory``), since the specialist itself says
    the item is unverified recollection."""
    low = sentence.lower()
    if any(c in low for c in _POSSIBLE):
        level = "possible"
    elif any(c in low for c in _PROBABLE):
        level = "probable"
    else:
        level = "established"
    if from_memory and level == "established":
        level = "probable"
    return level


def classify(sentence: str, index: int, is_body: bool) -> str:
    if is_self_report(sentence) or is_memory_label(sentence):
        return "other"
    low = sentence.lower()
    if is_body and index == 0:
        return "point"
    if any(c in low for c in _PERSPECTIVE):
        return "perspective"
    if any(c in low for c in _COUNTER) and (has_dated_item(sentence) or "voted" in low):
        return "counter_evidence"
    if any(c in low for c in _JUDGEMENT):
        return "judgement"
    if any(low.startswith(c) for c in _LINK) or " therefore " in f" {low} ":
        return "link"
    if has_dated_item(sentence):
        return "evidence"
    if any(c in low for c in _ANALYSIS):
        return "analysis"
    return "analysis"


def classify_paragraphs(text: str) -> list[tuple[ParagraphKind, str]]:
    """Segment ``text`` into paragraphs and decide each one's kind by content (see the
    module docstring). The structural checks use the same classification."""
    blocks = [p.strip() for p in re.split(r"\n\s*\n", strip_markup(text).strip()) if p.strip()]
    kinds: list[ParagraphKind] = ["note" if is_note_paragraph(b) else "body" for b in blocks]
    prose = [i for i, k in enumerate(kinds) if k == "body"]
    substantive = [i for i in prose if _word_count(blocks[i]) >= _MIN_SUBSTANTIVE_WORDS or has_dated_item(blocks[i])]
    if len(substantive) >= 3:
        first, last = prose[0], prose[-1]
        if first in substantive and not has_dated_item(blocks[first]) and any(has_dated_item(blocks[i]) for i in prose[1:]):
            kinds[first] = "intro"
        last_sentences = split_sentences(blocks[last])
        if last != first and last in substantive and last_sentences and (len(last_sentences) >= 2 or last_sentences[0].lower().startswith(_CONCLUSION_CUES)):
            kinds[last] = "conclusion"
    return list(zip(kinds, blocks))


def quotations_in(sentence: str) -> list[str]:
    """Quoted excerpts of ``sentence`` in order: straight, curly or mixed double marks,
    guillemets, and single marks around two or more words; at least four characters."""
    return [inner.strip() for _s, _e, inner in find_quotation_spans(sentence) if len(inner.strip()) >= _MIN_QUOTE_CHARS]


class HistorySpecialistAdapter:
    agent_id = "history-specialist"

    def structural_checks(self, report: SpecialistReport):
        from .structural import structural_checks
        return structural_checks(report)

    def parse_response(self, text: str, *, request_id: str, task_id: str, report_id: str, subject: str = "History", task_type: str = "essay",
                       supplied_texts: list[SuppliedText] = (), course_level: str = "unknown", agent_version: Optional[str] = None, agent_id: Optional[str] = None) -> SpecialistReport:
        """Build a report from the specialist's raw text. Raises :class:`AdapterError`
        (shape only, never the text) when the answer is empty or yields no sentences;
        sentences beyond the report's claim limit are merged into one ``other`` claim
        and recorded as an unresolved issue, so nothing is dropped silently."""
        if not text or not text.strip():
            raise AdapterError("the specialist answer is empty")
        agent = agent_id or self.agent_id
        paragraphs = classify_paragraphs(text)
        has_label = bool(MEMORY_LABEL_RE.search(text))
        base = dict(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level, task_type=task_type)
        pending: list[dict] = []
        supports_of: list[tuple[str, list[str]]] = []
        for pi, (kind, para) in enumerate(paragraphs):
            sentences = split_sentences(para)
            para_claims: list[tuple[str, str]] = []   # (claim id, role)
            point_id: Optional[str] = None
            body_index = 0
            for si, sent in enumerate(sentences):
                cid = f"h{pi + 1}.{si + 1}"
                core, notes = split_note_clauses(sent)
                note = kind == "note" or is_note_sentence(sent)
                body = core or sent   # the substance the role is read from; the claim text stays verbatim
                if note:
                    role = "other"
                elif kind == "intro":
                    role = "thesis"
                elif kind == "conclusion":
                    role = "judgement"
                else:
                    role = classify(body, body_index, True)
                    body_index += 1
                refs: list[SourceRef] = []
                assumptions: list[str] = []
                quoted = False
                for excerpt in quotations_in(sent):
                    quoted = True
                    doc = next((t.document_id for t in supplied_texts if find_quotation(excerpt, t.text)), None) or (supplied_texts[0].document_id if supplied_texts else None)
                    if doc:
                        refs.append(SourceRef(document_id=doc, excerpt=excerpt[:2000]))
                    else:
                        assumptions.append(f"quotation with no supplied text to check it against: \"{excerpt[:200]}\"")
                    if role in ("analysis", "evidence"):
                        role = "evidence"
                if dangling_quote_offset(sent) is not None:
                    span = undelimited_quote_span(sent)
                    shown = (span[2].strip()[:120] if span else "")
                    assumptions.append(f"a quotation mark in this sentence cannot be paired; the span '{shown}' was not delimited, was attributed to no text and was not checked")
                if not note:
                    for n in notes:
                        assumptions.append(f"the sentence carries the method's own label inline ('{n[:200]}'); the label is kept out of the claim's role and its dated items are from memory")
                dated = has_dated_item(body)
                if role in ("evidence", "counter_evidence") and dated:
                    proposed = "arithmetic"
                elif role == "evidence" and quoted:
                    proposed = "factual"
                elif role in ("analysis", "perspective"):
                    proposed = "interpretive"
                else:
                    proposed = "unknown"
                pending.append(dict(claim_id=cid, claim_text=truncate_claim_text(sent), claim_role=role, proposed_claim_kind=proposed,
                                    certainty=certainty_of(body, from_memory=dated and (has_label or bool(notes))),
                                    source_refs=refs[:32], assumptions=assumptions[:32], materiality="material" if role in ("point", "judgement", "link", "thesis") else "supporting",
                                    advisory_verification_status=_SELF_REPORT if is_self_report(sent) else None))
                para_claims.append((cid, role))
                if role == "point" and point_id is None:
                    point_id = cid
            if point_id is not None:
                argument = [c for c, r in para_claims if r != "other"]   # notes are not supports
                supports_of.append((point_id, [c for c in argument if c != point_id]))
                for c, r in para_claims:
                    if r in ("judgement", "link") and c != point_id:
                        supports_of.append((c, [x for x in argument if x != c]))   # the point comes first: it is the first argument claim
        if not pending:
            raise AdapterError("the specialist answer yields no sentences")
        unresolved: list[str] = []
        if len(pending) > _MAX_CLAIMS:
            head, tail = pending[: _MAX_CLAIMS - 1], pending[_MAX_CLAIMS - 1:]
            tail_text = truncate_claim_text(" ".join(p["claim_text"] for p in tail))
            head.append(dict(claim_id=_TAIL_CLAIM_ID, claim_text=tail_text, claim_role="other", proposed_claim_kind="unknown", certainty="possible", source_refs=[], assumptions=[], materiality="supporting", advisory_verification_status=None))
            unresolved.append(f"{len(tail)} sentences beyond the report's claim limit ({_MAX_CLAIMS}) were merged into claim {_TAIL_CLAIM_ID} and were not individually roled or checked")
            pending = head
        kept = {p["claim_id"] for p in pending}
        supports = {pid: [s for s in ids if s in kept] for pid, ids in supports_of}
        claims = [ClaimRecord(**base, **{**p, "supporting_claim_ids": supports.get(p["claim_id"], [])}) for p in pending]
        if any(k == "note" for k, _ in paragraphs):
            unresolved.append("the answer contains note paragraphs (a from-memory label, a task note or self-certification); their sentences are roled 'other' and are not material")
        return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level,
                                task_type=task_type, original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts), claims=claims,
                                unresolved_issues=unresolved, created_at=_now())


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
