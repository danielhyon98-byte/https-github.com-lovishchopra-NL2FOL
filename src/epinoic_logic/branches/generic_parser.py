"""Fallback parser for subjects without a dedicated adapter: one claim per sentence,
roles from shared cues (first sentence of a body paragraph is the point; dated or
figured sentences are evidence; verdict cues are judgements; 'therefore' links)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from ..ir.schema import SourceRef
from ..translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from ..translate.grounding import find_quotation

_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"'(])")
_NUM_RE = re.compile(r"\d")
_QUOTE_RE = re.compile(r"\"([^\"]{4,})\"|“([^”]{4,})”")
_JUDGE = ("therefore", "overall", "to a large extent", "on balance", "in conclusion", "recommend", "should", "outweigh")


class GenericTextParser:
    def __init__(self, agent_id: str = "specialist") -> None:
        self.agent_id = agent_id

    def parse_response(self, text: str, *, request_id: str, task_id: str, report_id: str, subject: str, task_type: str, supplied_texts: list[SuppliedText] = (),
                       course_level: str = "unknown", agent_version: Optional[str] = None, agent_id: Optional[str] = None) -> SpecialistReport:
        agent = agent_id or self.agent_id
        claims: list[ClaimRecord] = []
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
        for pi, para in enumerate(paragraphs):
            sents = [s.strip() for s in _SENT_RE.split(para) if s.strip()]
            ids = []
            for si, sent in enumerate(sents):
                low = sent.lower()
                refs = []
                for m in _QUOTE_RE.finditer(sent):
                    ex = m.group(1) or m.group(2)
                    doc = next((t.document_id for t in supplied_texts if find_quotation(ex, t.text)), None) or (supplied_texts[0].document_id if supplied_texts else None)
                    if doc:
                        refs.append(SourceRef(document_id=doc, excerpt=ex))
                if si == 0 and len(sents) > 1:
                    role = "point"
                elif any(k in low for k in _JUDGE):
                    role = "judgement"
                elif refs:
                    role = "evidence"
                elif _NUM_RE.search(sent):
                    role = "quantitative"
                else:
                    role = "analysis"
                cid = f"g{pi + 1}.{si + 1}"
                claims.append(ClaimRecord(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level,
                                          task_type=task_type, claim_id=cid, claim_text=sent, claim_role=role, proposed_claim_kind="arithmetic" if role == "quantitative" else "unknown", source_refs=refs,
                                          materiality="material" if role in ("point", "judgement") else "supporting"))
                ids.append(cid)
            if len(ids) > 1:
                claims[-len(ids)] = claims[-len(ids)].model_copy(update={"supporting_claim_ids": ids[1:]})
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level,
                                task_type=task_type, original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts), claims=claims, created_at=now)
