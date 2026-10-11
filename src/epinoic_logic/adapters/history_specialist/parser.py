"""Heuristic parser for History specialist responses written with the pack's core
operation: Claim -> Evidence -> Analysis -> Judgement -> Link (Response application §3,
Structures §5). Sentences are assigned roles from surface cues; the point of each body
paragraph is wired to every other claim in that paragraph. Heuristic by design: the
generic structured adapter is the contract future agents should emit directly.

Paragraph classification is decided by content, never by paragraph count alone:

* a ``note`` paragraph is one whose sentences are all labels about the text (a
  from-memory disclaimer, a self-certification line) or a short undated aside with no
  argument cue; its claims are roled ``other`` and are never material, and it does
  not make the answer "multi-paragraph";
* with three or more prose paragraphs, the first is the ``intro`` only when it has
  no dated item while a later paragraph does, and the last is the ``conclusion`` only
  when it has two or more sentences or opens with a concluding cue;
* everything else is a ``body`` paragraph whose first non-note sentence is the point.

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
from ..markdown import is_memory_label, is_self_certification, split_list_items, strip_markup, truncate_claim_text

ParagraphKind = Literal["intro", "body", "conclusion", "note"]

_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9\"'(“‘])")
_DATE_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_FIGURE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:per cent|percent|%|million|thousand|seats|votes|laws|decrees)\b|\b\d{1,3}(?:,\d{3})+\b", re.IGNORECASE)
_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), start=1)}
_MONTH_NAMES = "January|February|March|April|May|June|July|August|September|October|November|December"
_MONTH_YEAR_RE = re.compile(rf"\b({_MONTH_NAMES})\s+(1[0-9]{{3}}|20[0-9]{{2}})\b")
_DAY_MONTH_RE = re.compile(rf"\b\d{{1,2}}\s+(?:{_MONTH_NAMES})\b|\b(?:{_MONTH_NAMES})\s+\d{{1,2}}\b")
_QUOTE_RE = re.compile(r"\"([^\"]{4,})\"|“([^”]{4,})”")
_COUNTER = ("the counter-case", "against this", "the distinction is right", "however", "on the other hand", "it could be argued")
_JUDGEMENT = ("by the criterion", "weighs more", "holds for", "decisive even if", "remains the precondition", "was therefore responsible", "fails, because", "does not shift the weight", "necessary; it was not sufficient", "necessary but not sufficient", "to a degree")
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
_MAX_CLAIMS = 512
_TAIL_CLAIM_ID = "h.tail"
_SELF_REPORT = "self-certified in the response text"


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


def is_note_sentence(sentence: str) -> bool:
    """A label about the text rather than part of the argument."""
    return is_memory_label(sentence) or is_self_certification(sentence)


def is_note_paragraph(paragraph: str) -> bool:
    """All sentences are labels, or the paragraph is a short undated aside with no argument cue."""
    sentences = split_sentences(paragraph)
    if not sentences:
        return False
    if all(is_note_sentence(s) for s in sentences):
        return True
    low = paragraph.lower()
    return len(sentences) == 1 and _word_count(paragraph) < _MAX_ASIDE_WORDS and not has_dated_item(paragraph) and not any(c in low for c in _ARGUMENT_CUES)


def certainty_of(sentence: str) -> str:
    low = sentence.lower()
    if any(c in low for c in _POSSIBLE):
        return "possible"
    if any(c in low for c in _PROBABLE):
        return "probable"
    return "established"


def classify(sentence: str, index: int, is_body: bool) -> str:
    if is_self_certification(sentence) or is_memory_label(sentence):
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


def month_index(month_name: str, year: str) -> int:
    return int(year) * 12 + _MONTHS[month_name.lower()]


_AFTER_PHRASE_RE = re.compile(
    r"\b(?:came|happened|followed|occurred|arrived|fell|rose|began|ended)\s+(?:only\s+)?after\b|\bonly after\b",
    re.IGNORECASE,
)
_CLAUSE_BREAK_RE = re.compile(r";|,\s+(?:and|but|while|whereas)\b|\bbut\b")
_RELATIVE_CLAUSE_RE = re.compile(r"\b(?:which|who|whom|whose|that)\b", re.IGNORECASE)


def date_in_aside(before: str, date: "re.Match[str]") -> bool:
    """True when ``date`` sits inside a relative clause that closes before the ordering
    verb: ``The party, which had been founded in January 1919, was banned after ...``.
    The clause opens with a relative marker after the last comma before the date and a
    comma follows the date. ``The vote fell in November 1931, which came only after
    ...`` is not an aside: the marker follows the date and makes it the ordered event."""
    pre = before[: date.start()]
    opener = pre[max(pre.rfind(","), pre.rfind(";")) + 1:]
    return bool(_RELATIVE_CLAUSE_RE.search(opener)) and "," in before[date.end():]


def chronology_findings_in(sentence: str) -> Optional[tuple[int, int]]:
    """Structural proxy for one chronology pattern inside a single sentence.

    The pattern is ``<event> in <date1> ... (came|happened|followed|occurred) [only]
    after ... <date2>``: ``date1`` is the nearest month-year before the ``after``
    phrase and ``date2`` the nearest one after it, with no other date, no clause
    boundary (``;``, ``, and``, ``but``) and no relative-clause marker (``which``,
    ``who``, ``that``, ``whose``) in between. The sentence then asserts
    ``date1 > date2``; return ``(date1, date2)`` as month indices when the dates it
    gives violate that order, else ``None``. Dates that belong to different clauses of
    a long sentence (``... in March 1930 ..., and his successor ... after ... July
    1930``) or to an aside (``The party, which had been founded in January 1919, was
    banned after the putsch of November 1923``) are not paired. Cross-sentence
    chronology is left to the formal path.
    """
    m = _AFTER_PHRASE_RE.search(sentence)
    if m is None:
        return None
    before, after = sentence[: m.start()], sentence[m.end():]
    earlier_dates = list(_MONTH_YEAR_RE.finditer(before))
    if not earlier_dates:
        return None
    date1 = earlier_dates[-1]
    if _CLAUSE_BREAK_RE.search(before[date1.end():]) or date_in_aside(before, date1):
        return None
    date2 = _MONTH_YEAR_RE.search(after)
    if date2 is None or _CLAUSE_BREAK_RE.search(after[: date2.start()]):
        return None
    first, second = month_index(*date1.groups()), month_index(*date2.groups())
    return (first, second) if first <= second else None


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
        base = dict(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level, task_type=task_type)
        pending: list[dict] = []
        points: list[tuple[str, list[str]]] = []
        for pi, (kind, para) in enumerate(paragraphs):
            sentences = split_sentences(para)
            para_ids: list[str] = []
            point_id: Optional[str] = None
            body_index = 0
            for si, sent in enumerate(sentences):
                cid = f"h{pi + 1}.{si + 1}"
                note = is_note_sentence(sent)
                if note or kind == "note":
                    role = "other"
                elif kind == "intro":
                    role = "thesis"
                elif kind == "conclusion":
                    role = "judgement"
                else:
                    role = classify(sent, body_index, True)
                    body_index += 1
                refs: list[SourceRef] = []
                assumptions: list[str] = []
                quoted = False
                for m in _QUOTE_RE.finditer(sent):
                    excerpt = m.group(1) or m.group(2)
                    quoted = True
                    doc = next((t.document_id for t in supplied_texts if find_quotation(excerpt, t.text)), None) or (supplied_texts[0].document_id if supplied_texts else None)
                    if doc:
                        refs.append(SourceRef(document_id=doc, excerpt=excerpt[:2000]))
                    else:
                        assumptions.append(f"quotation with no supplied text to check it against: \"{excerpt[:200]}\"")
                    if role in ("analysis", "evidence"):
                        role = "evidence"
                if role in ("evidence", "counter_evidence") and has_dated_item(sent):
                    proposed = "arithmetic"
                elif role == "evidence" and quoted:
                    proposed = "factual"
                elif role in ("analysis", "perspective"):
                    proposed = "interpretive"
                else:
                    proposed = "unknown"
                pending.append(dict(claim_id=cid, claim_text=truncate_claim_text(sent), claim_role=role, proposed_claim_kind=proposed, certainty=certainty_of(sent),
                                    source_refs=refs, assumptions=assumptions[:32], materiality="material" if role in ("point", "judgement", "link", "thesis") else "supporting",
                                    advisory_verification_status=_SELF_REPORT if is_self_certification(sent) else None))
                para_ids.append(cid)
                if role == "point" and point_id is None:
                    point_id = cid
            if point_id is not None:
                points.append((point_id, [c for c in para_ids if c != point_id]))
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
        supports = {pid: [s for s in ids if s in kept] for pid, ids in points}
        claims = [ClaimRecord(**base, **{**p, "supporting_claim_ids": supports.get(p["claim_id"], [])}) for p in pending]
        if any(k == "note" for k, _ in paragraphs):
            unresolved.append("the answer contains note paragraphs (a from-memory label or self-certification); their sentences are roled 'other' and are not material")
        return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level,
                                task_type=task_type, original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts), claims=claims,
                                unresolved_issues=unresolved, created_at=_now())


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
