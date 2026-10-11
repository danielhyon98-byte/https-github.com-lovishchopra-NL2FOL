"""Fallback parser for subjects without a dedicated adapter: one claim per sentence,
roles from shared cues (first sentence of a body paragraph is the point; dated or
figured sentences are evidence; verdict cues are judgements; 'therefore' links).

Markdown furniture and pasted JSON blocks are removed before segmentation, a newline
followed by a list marker ends a sentence, note sentences (from-memory labels,
self-certification, task notes) are roled ``other`` and never material, a paragraph
with a self-certifying sentence is a note paragraph as a whole, a substantive sentence
that carries an inline label ("(figures from memory; check your notes)") keeps its role
with the label recorded as an assumption, quotations are found in double marks of any
kind (straight, curly, guillemet, mixed) and in single marks around two or more words,
claim texts respect the contract limit, and sentences beyond the report's claim limit
are merged into one ``other`` claim with an unresolved issue rather than crashing or
vanishing. ``original_response`` is always verbatim."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from ..adapters.base import AdapterError
from ..adapters.markdown import (
    dangling_quote_offset, find_quotation_spans, is_note_sentence, is_self_certification, split_list_items, split_note_clauses,
    strip_markup, truncate_claim_text,
)
from ..ir.schema import SourceRef
from ..translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from ..translate.grounding import find_quotation

_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9\"'(“‘«„])")
_NUM_RE = re.compile(r"\d")
_MIN_QUOTE_CHARS = 4
_JUDGE = ("therefore", "overall", "to a large extent", "on balance", "in conclusion", "recommend", "should", "outweigh")
_MAX_CLAIMS = 512
_TAIL_CLAIM_ID = "g.tail"
_SELF_REPORT = "self-certified in the response text"


def split_sentences(paragraph: str) -> list[str]:
    out: list[str] = []
    for item in split_list_items(paragraph):
        out.extend(s.strip() for s in _SENT_RE.split(item.strip()) if s.strip())
    return out


def quotations_in(sentence: str) -> list[str]:
    """The quoted excerpts of ``sentence``: double marks of any kind (paired around the
    dangling mark of an unbalanced sentence) and single marks around two or more words."""
    return [inner for _s, _e, inner in find_quotation_spans(sentence) if len(inner.strip()) >= _MIN_QUOTE_CHARS]


class GenericTextParser:
    def __init__(self, agent_id: str = "specialist") -> None:
        self.agent_id = agent_id

    def parse_response(self, text: str, *, request_id: str, task_id: str, report_id: str, subject: str, task_type: str, supplied_texts: list[SuppliedText] = (),
                       course_level: str = "unknown", agent_version: Optional[str] = None, agent_id: Optional[str] = None) -> SpecialistReport:
        if not text or not text.strip():
            raise AdapterError("the specialist answer is empty")
        agent = agent_id or self.agent_id
        base = dict(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level, task_type=task_type)
        pending: list[dict] = []
        points: list[tuple[str, list[str]]] = []
        unresolved: list[str] = []
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", strip_markup(text).strip()) if p.strip()]
        for pi, para in enumerate(paragraphs):
            sents = split_sentences(para)
            # a paragraph with a self-certifying sentence is a note paragraph as a whole: none of it counts as material
            note_paragraph = any(is_self_certification(s) for s in sents)
            if note_paragraph and len(sents) > 1:
                unresolved.append(f"paragraph {pi + 1} contains verification-status language; the whole paragraph was treated as a note and none of its sentences counts as material")
            ids: list[str] = []
            point_id: Optional[str] = None
            body_index = 0
            for si, sent in enumerate(sents):
                refs: list[SourceRef] = []
                assumptions: list[str] = []
                excerpts = quotations_in(sent)
                for ex in excerpts:
                    doc = next((t.document_id for t in supplied_texts if find_quotation(ex, t.text)), None) or (supplied_texts[0].document_id if supplied_texts else None)
                    if doc:
                        refs.append(SourceRef(document_id=doc, excerpt=ex[:2000]))
                    else:
                        assumptions.append(f"quotation with no supplied text to check it against: \"{ex[:200]}\"")
                if dangling_quote_offset(sent) is not None:
                    assumptions.append("the sentence has an unbalanced quotation mark; the span it opens or closes was not treated as a quotation and was not checked")
                core, notes = split_note_clauses(sent)
                if core:  # a substantive sentence keeps its role; the inline label travels as an assumption
                    for note in notes:
                        assumptions.append(f"inline label recorded, not part of the claim: {note[:200]}")
                low = core.lower()
                if note_paragraph or not core or is_note_sentence(core):
                    role = "other"
                elif body_index == 0 and len(sents) > 1:
                    role = "point"
                elif any(k in low for k in _JUDGE):
                    role = "judgement"
                elif refs or excerpts:
                    role = "evidence"
                elif _NUM_RE.search(core):
                    role = "quantitative"
                else:
                    role = "analysis"
                if role != "other":
                    body_index += 1
                cid = f"g{pi + 1}.{si + 1}"
                pending.append(dict(claim_id=cid, claim_text=truncate_claim_text(sent), claim_role=role, proposed_claim_kind="arithmetic" if role == "quantitative" else ("factual" if role == "evidence" and not refs else "unknown"),
                                    source_refs=refs, assumptions=assumptions[:32], materiality="material" if role in ("point", "judgement") else "supporting",
                                    advisory_verification_status=_SELF_REPORT if is_self_certification(sent) else None))
                ids.append(cid)
                if role == "point" and point_id is None:
                    point_id = cid
            if point_id is not None and len(ids) > 1:
                points.append((point_id, [c for c in ids if c != point_id]))
        if not pending:
            raise AdapterError("the specialist answer yields no sentences")
        if len(pending) > _MAX_CLAIMS:
            head, tail = pending[: _MAX_CLAIMS - 1], pending[_MAX_CLAIMS - 1:]
            head.append(dict(claim_id=_TAIL_CLAIM_ID, claim_text=truncate_claim_text(" ".join(p["claim_text"] for p in tail)), claim_role="other", proposed_claim_kind="unknown", source_refs=[], assumptions=[], materiality="supporting", advisory_verification_status=None))
            unresolved.append(f"{len(tail)} sentences beyond the report's claim limit ({_MAX_CLAIMS}) were merged into claim {_TAIL_CLAIM_ID} and were not individually roled or checked")
            pending = head
        kept = {p["claim_id"] for p in pending}
        supports = {pid: [s for s in sids if s in kept] for pid, sids in points}
        claims = [ClaimRecord(**base, **{**p, "supporting_claim_ids": supports.get(p["claim_id"], [])}) for p in pending]
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level,
                                task_type=task_type, original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts), claims=claims,
                                unresolved_issues=unresolved[:64], created_at=now)
