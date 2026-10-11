"""Heuristic parser for History specialist responses written with the pack's core
operation: Claim -> Evidence -> Analysis -> Judgement -> Link (Response application §3,
Structures §5). Sentences are assigned roles from surface cues; the point of each body
paragraph is wired to every other claim in that paragraph. Heuristic by design: the
generic structured adapter is the contract future agents should emit directly.
"""
from __future__ import annotations

import re
from typing import Optional

from ...ir.schema import SourceRef
from ...translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from ...translate.grounding import find_quotation

_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"'(])")
_DATE_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_FIGURE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:per cent|percent|%|million|thousand|seats|votes|laws|decrees)\b|\b\d{1,3}(?:,\d{3})+\b", re.IGNORECASE)
_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), start=1)}
_MONTH_YEAR_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(1[0-9]{3}|20[0-9]{2})\b")
_QUOTE_RE = re.compile(r"\"([^\"]{4,})\"|“([^”]{4,})”")
_COUNTER = ("the counter-case", "against this", "the distinction is right", "however", "on the other hand", "it could be argued")
_JUDGEMENT = ("by the criterion", "weighs more", "holds for", "decisive even if", "remains the precondition", "was therefore responsible", "fails, because", "does not shift the weight", "necessary; it was not sufficient", "necessary but not sufficient", "to a degree")
_ANALYSIS = ("mattered because", "the mechanism was", "this shows", "which shows", "this mattered", "meant that", "so that", "revealed", "explains why", "this matters")
_LINK = ("therefore", "thus", "in sum", "ultimately")
_PERSPECTIVE = ("historians who", "one historian", "some historians", "others describe", "historians argue", "has argued")
_ESTABLISHED = ("shows", "establishes", "demonstrates", "made", "led to", "was decisive", "proves", "was responsible")
_PROBABLE = ("suggests", "indicates", "is consistent with", "points to", "arguably")
_POSSIBLE = ("can be read as", "may have", "some historians argue", "it is possible that", "perhaps")


_INITIAL_RE = re.compile(r"(?:^|\s)[A-Z]\.$")


def split_sentences(paragraph: str) -> list[str]:
    """Sentence split that does not break after initials such as 'A. J. P.'."""
    parts = [s.strip() for s in _SENT_RE.split(paragraph.strip()) if s.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and _INITIAL_RE.search(merged[-1]):
            merged[-1] = merged[-1] + " " + part
        else:
            merged.append(part)
    return merged


def has_dated_item(sentence: str) -> bool:
    return bool(_DATE_RE.search(sentence) or _FIGURE_RE.search(sentence))


def certainty_of(sentence: str) -> str:
    low = sentence.lower()
    if any(c in low for c in _POSSIBLE):
        return "possible"
    if any(c in low for c in _PROBABLE):
        return "probable"
    return "established"


def classify(sentence: str, index: int, is_body: bool) -> str:
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


def month_index(month_name: str, year: str) -> int:
    return int(year) * 12 + _MONTHS[month_name.lower()]


def chronology_findings_in(sentence: str) -> Optional[tuple[int, int]]:
    """For a sentence of the form '... came only after ...' with two month-year dates,
    return (later_claimed, earlier_claimed) month indices when the stated order is violated."""
    low = sentence.lower()
    if " after " not in low:
        return None
    dates = _MONTH_YEAR_RE.findall(sentence)
    if len(dates) < 2:
        return None
    first, second = month_index(*dates[0]), month_index(*dates[1])
    # "X in <date1> ... came only after ... <date2>": date1 must be later than date2
    return (first, second) if first <= second else None


class HistorySpecialistAdapter:
    agent_id = "history-specialist"

    def structural_checks(self, report: SpecialistReport):
        from .structural import structural_checks
        return structural_checks(report)

    def parse_response(self, text: str, *, request_id: str, task_id: str, report_id: str, subject: str = "History", task_type: str = "essay",
                       supplied_texts: list[SuppliedText] = (), course_level: str = "unknown", agent_version: Optional[str] = None, agent_id: Optional[str] = None) -> SpecialistReport:
        agent = agent_id or self.agent_id
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
        multi = len(paragraphs) >= 3
        claims: list[ClaimRecord] = []
        n = 0
        for pi, para in enumerate(paragraphs):
            is_intro = multi and pi == 0
            is_concl = multi and pi == len(paragraphs) - 1
            is_body = not (is_intro or is_concl)
            sentences = split_sentences(para)
            para_ids: list[str] = []
            point_id: Optional[str] = None
            for si, sent in enumerate(sentences):
                n += 1
                cid = f"h{pi + 1}.{si + 1}"
                role = "thesis" if is_intro else ("judgement" if is_concl else classify(sent, si, is_body))
                refs = []
                for m in _QUOTE_RE.finditer(sent):
                    excerpt = m.group(1) or m.group(2)
                    doc = next((t.document_id for t in supplied_texts if find_quotation(excerpt, t.text)), None) or (supplied_texts[0].document_id if supplied_texts else None)
                    if doc:
                        refs.append(SourceRef(document_id=doc, excerpt=excerpt))
                    role = "evidence" if role in ("analysis", "evidence") else role
                claims.append(ClaimRecord(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, agent_version=agent_version, subject=subject,
                                          course_level=course_level, task_type=task_type, claim_id=cid, claim_text=sent, claim_role=role,
                                          proposed_claim_kind="arithmetic" if role in ("evidence", "counter_evidence") and has_dated_item(sent) else ("interpretive" if role in ("analysis", "perspective") else "unknown"),
                                          certainty=certainty_of(sent), source_refs=refs, materiality="material" if role in ("point", "judgement", "link", "thesis") else "supporting"))
                para_ids.append(cid)
                if role == "point" and point_id is None:
                    point_id = cid
            if point_id is not None:
                idx = next(i for i, c in enumerate(claims) if c.claim_id == point_id)
                claims[idx] = claims[idx].model_copy(update={"supporting_claim_ids": [c for c in para_ids if c != point_id]})
        return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level,
                                task_type=task_type, original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts), claims=claims, created_at=_now())


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
