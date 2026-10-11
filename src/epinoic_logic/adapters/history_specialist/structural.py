"""Deterministic structural and source-integrity checks for History specialist output.

Rule sources are the pack's own working rules (Response application §3, §5, §8;
Structures P6, P7, P9, P15; Sources L5), never official IB rules. Paragraphs are
classified exactly as the parser classifies them (``classify_paragraphs``), so the
findings and the claim roles always agree: note paragraphs (from-memory labels, task
notes, self-certification lines or forged receipt fragments, short undated asides) are
not body paragraphs and are not held to the body-paragraph rules. ``HI-CHR-001`` reads
the sentence's dated orderings from the same extractor as the core pack's formal
chronology check (``history_specialist.chronology``). ``HI-STR-001`` (no judgement
move) is raised here for every body paragraph; the History pack drops it when the
request's command term asks for no verdict (level 1-2, or no verdict term).
"""
from __future__ import annotations

import re

from ...translate.contracts import SpecialistReport, StructuralFinding
from ...translate.grounding import find_quotation
from ..markdown import MEMORY_LABEL_RE as _MEMORY_LABEL_RE
from .chronology import chronology_relations
from .parser import classify_paragraphs, has_dated_item, split_sentences

# Name tokens are Unicode-aware: 'Jürgen Falter argued' is an attribution exactly as 'Karl Bracher argued' is.
_NAME = r"[A-ZÀ-ÖØ-Þ][^\W\d_]+"
_HISTORIAN_RE = re.compile(rf"\b([A-Z]\.(?:\s?[A-Z]\.)*\s?{_NAME}|{_NAME}\s{_NAME})\s+(?:has\s+)?(?:argue[sd]|prove[sd]|show[s]?|claim[s]?|concluded|demonstrated)\b")
_RULE = "history_specialist/{} (working rule, not an official IB rule)"


def structural_checks(report: SpecialistReport) -> list[StructuralFinding]:
    f: list[StructuralFinding] = []
    text = report.original_response
    paragraphs = classify_paragraphs(text)
    prose = [(pi, kind, para) for pi, (kind, para) in enumerate(paragraphs) if kind != "note"]
    multi = any(kind in ("intro", "conclusion") for _, kind, _ in prose)
    docs = {t.document_id: t for t in report.supplied_texts}

    for c in report.claims:
        for ref in c.source_refs:
            doc = docs.get(ref.document_id)
            if ref.excerpt and doc is not None and find_quotation(ref.excerpt, doc.text) is None:
                f.append(StructuralFinding(code="HI-SRC-001", severity="error", message="quotation not found in the supplied source", claim_ids=[c.claim_id], rule_source=_RULE.format("application.md §8.2")))
        if re.search(r"\bprove[sd]?\b", c.claim_text, re.IGNORECASE) and c.claim_role != "evidence":
            f.append(StructuralFinding(code="HI-SRC-002", severity="warning", message="'proves' used of a historical claim; the pack allows 'establishes' or 'shows' only at certainty 1-2", claim_ids=[c.claim_id], rule_source=_RULE.format("application.md §5")))
        if _HISTORIAN_RE.search(c.claim_text) and not c.source_refs:
            f.append(StructuralFinding(code="HI-SRC-003", severity="warning", message="a named historian is attributed a position without knowledge-document or library grounding", claim_ids=[c.claim_id], rule_source=_RULE.format("application.md §8.2; master prompt resolved conflict 5")))

    dated_claims = [c for c in report.claims if has_dated_item(c.claim_text)]
    if dated_claims and not _MEMORY_LABEL_RE.search(text) and not any(c.source_refs for c in dated_claims):
        f.append(StructuralFinding(code="HI-SRC-004", severity="info", message="dates and figures appear without source references or a from-memory label", claim_ids=[c.claim_id for c in dated_claims][:8], rule_source=_RULE.format("application.md §5; sources.md L5")))

    for pi, kind, para in prose:
        if kind != "body":
            continue
        sents = split_sentences(para)
        low = para.lower()
        ids = [c.claim_id for c in report.claims if c.claim_text in para]
        if not any(k in low for k in ("counter-case", "against this", "however", "by the criterion", "weigh", "on the other hand")):
            f.append(StructuralFinding(code="HI-STR-001", severity="warning", message=f"body paragraph {pi + 1} has no judgement move (counter-case weighed by a criterion)", claim_ids=ids, rule_source=_RULE.format("structures.md P9")))
        if sum(1 for s in sents if has_dated_item(s)) < 2:
            f.append(StructuralFinding(code="HI-STR-002", severity="info", message=f"body paragraph {pi + 1} has fewer than two dated or figured items", claim_ids=ids, rule_source=_RULE.format("structures.md P7")))
        if sents and has_dated_item(sents[0]) and not re.search(r"\b(responsible|because|caused|led|made|turned|created)\b", sents[0], re.IGNORECASE):
            f.append(StructuralFinding(code="HI-STR-003", severity="info", message=f"body paragraph {pi + 1} opens with evidence rather than a claim", claim_ids=ids[:1], rule_source=_RULE.format("structures.md P6")))
        for s in sents:
            # The same extractor decides the core pack's formal chronology check, so the proxy and the engine agree.
            for rel in chronology_relations(s):
                if rel.violated:
                    f.append(StructuralFinding(code="HI-CHR-001", severity="warning", message=f"a sentence says one dated event came after another ('{rel.cue}'), but the dates it gives are not in that order: {rel.later_text} is not later than {rel.earlier_text}", claim_ids=[c.claim_id for c in report.claims if c.claim_text == s], rule_source=_RULE.format("application.md EV2 (exact, dated items)")))

    words = len(re.findall(r"\b[\w'’-]+\b", " ".join(para for _, _, para in prose)))
    if multi and report.task_type == "essay" and not (800 <= words <= 1100):
        f.append(StructuralFinding(code="HI-STR-004", severity="info", message=f"essay length {words} words is outside the pack's exam-length guide (800-1,000 for Paper 2)", rule_source=_RULE.format("structures.md P15")))
    return f
