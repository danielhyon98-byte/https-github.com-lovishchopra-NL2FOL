"""Fallback parser for subjects without a dedicated adapter: one claim per sentence,
roles from shared cues (first sentence of a body paragraph is the point; dated or
figured sentences are evidence; verdict cues are judgements; 'therefore' links).

Markdown furniture is removed before segmentation, a newline followed by a list marker
ends a sentence, note sentences (from-memory labels, self-certification) are roled
``other`` and never material, claim texts respect the contract limit, and sentences
beyond the report's claim limit are merged into one ``other`` claim with an unresolved
issue rather than crashing or vanishing. ``original_response`` is always verbatim."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from ..adapters.base import AdapterError
from ..adapters.markdown import is_note_sentence, is_self_certification, split_list_items, strip_markup, truncate_claim_text
from ..ir.schema import SourceRef
from ..translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from ..translate.grounding import find_quotation

_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9\"'(“‘])")
_NUM_RE = re.compile(r"\d")
_QUOTE_RE = re.compile(r"\"([^\"]{4,})\"|“([^”]{4,})”")
_JUDGE = ("therefore", "overall", "to a large extent", "on balance", "in conclusion", "recommend", "should", "outweigh")
_MAX_CLAIMS = 512
_TAIL_CLAIM_ID = "g.tail"
_SELF_REPORT = "self-certified in the response text"


def split_sentences(paragraph: str) -> list[str]:
    out: list[str] = []
    for item in split_list_items(paragraph):
        out.extend(s.strip() for s in _SENT_RE.split(item.strip()) if s.strip())
    return out


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
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", strip_markup(text).strip()) if p.strip()]
        for pi, para in enumerate(paragraphs):
            sents = split_sentences(para)
            ids: list[str] = []
            point_id: Optional[str] = None
            body_index = 0
            for si, sent in enumerate(sents):
                low = sent.lower()
                refs: list[SourceRef] = []
                assumptions: list[str] = []
                for m in _QUOTE_RE.finditer(sent):
                    ex = m.group(1) or m.group(2)
                    doc = next((t.document_id for t in supplied_texts if find_quotation(ex, t.text)), None) or (supplied_texts[0].document_id if supplied_texts else None)
                    if doc:
                        refs.append(SourceRef(document_id=doc, excerpt=ex[:2000]))
                    else:
                        assumptions.append(f"quotation with no supplied text to check it against: \"{ex[:200]}\"")
                if is_note_sentence(sent):
                    role = "other"
                elif body_index == 0 and len(sents) > 1:
                    role = "point"
                elif any(k in low for k in _JUDGE):
                    role = "judgement"
                elif refs or assumptions:
                    role = "evidence"
                elif _NUM_RE.search(sent):
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
        unresolved: list[str] = []
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
                                unresolved_issues=unresolved, created_at=now)
