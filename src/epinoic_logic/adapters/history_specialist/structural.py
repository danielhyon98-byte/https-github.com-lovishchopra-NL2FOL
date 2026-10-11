"""Deterministic structural and source-integrity checks for History specialist output.

Rule sources are the pack's own working rules (Response application §3, §5, §8;
Structures P6, P7, P9, P15; Sources L5), never official IB rules. Paragraphs are
classified exactly as the parser classifies them (``classify_paragraphs``), so the
findings and the claim roles always agree: note paragraphs (from-memory labels, task
notes, self-certification lines or forged receipt fragments, short undated asides) are
not body paragraphs and are not held to the body-paragraph rules.

``HI-SRC-001`` reads every source reference through the same grounding check the channel
uses (``check_claim_sources``), so it can never contradict the channel: an excerpt the
channel finds in a different form (``INT-REQ-010``) is a WARNING here, an excerpt found
nowhere is an error, and both name the excerpt and the documents searched.

``HI-CHR-001`` reads the sentence's dated orderings from the same extractor as the core
pack's formal chronology check (``history_specialist.chronology``), with the paragraph
as context for a day-month date whose year the sentence does not state.

``HI-STR-003`` (opens with evidence rather than a claim) is decided from the parsed role of
the paragraph's first claim that is not a note: evidence or counter evidence opens with
evidence; the positional point does only when the parser's own predicate
(``parser.opens_with_fact``) reads it as a bare dated fact, and the finding says so, so the
finding never contradicts a point that makes a claim ('a major but partial cause of ...').

``HI-STR-001`` (no judgement move) is decided from the parsed roles first: a paragraph
with a judgement-role claim that states its criterion (``by the criteria of``, ``weighed
by``), or a counter-case (role ``counter_evidence`` or a counter cue) together with a
judgement or verdict cue, has made the move; failing that, the paragraph's own words are
searched for the move's vocabulary. The History pack drops the finding when the
request's command term asks for no verdict (level 1-2, or no verdict term).
"""
from __future__ import annotations

import re

from ...translate.contracts import SpecialistReport, StructuralFinding
from ...translate.grounding import check_claim_sources
from ..markdown import MEMORY_LABEL_RE as _MEMORY_LABEL_RE
from .chronology import chronology_relations
from .parser import COUNTER_CUES, CRITERION_CUES, JUDGEMENT_CUES, VERDICT_CUES, classify_paragraphs, has_dated_item, opens_with_fact, split_sentences

# Name tokens are Unicode-aware: 'Jürgen Falter argued' is an attribution exactly as 'Karl Bracher argued' is.
_NAME = r"[A-ZÀ-ÖØ-Þ][^\W\d_]+"
_HISTORIAN_RE = re.compile(rf"\b([A-Z]\.(?:\s?[A-Z]\.)*\s?{_NAME}|{_NAME}\s{_NAME})\s+(?:has\s+)?(?:argue[sd]|prove[sd]|show[s]?|claim[s]?|concluded|demonstrated)\b")
_RULE = "history_specialist/{} (working rule, not an official IB rule)"
_FORM_DIFFERS = "differs in form"
#: The paragraph-level vocabulary of the judgement move (counter-case weighed by a criterion), searched when the roles do not settle it.
_JUDGEMENT_MOVE_WORDS = ("counter-case", "against this", "however", "on the other hand", "weigh") + CRITERION_CUES
_EXCERPT_CHARS = 80


def _shown(excerpt: str) -> str:
    return excerpt[:_EXCERPT_CHARS] + ("..." if len(excerpt) > _EXCERPT_CHARS else "")


def judgement_move_present(paragraph: str, roles: list[str]) -> bool:
    """True when the paragraph has made the judgement move: a judgement-role claim stating a
    criterion, a counter-case weighed (counter role or cue plus a judgement/verdict cue), or
    the move's own vocabulary."""
    low = paragraph.lower()
    judgement = "judgement" in roles or any(c in low for c in JUDGEMENT_CUES)
    verdict = judgement or any(c in low for c in VERDICT_CUES)
    criterion = any(c in low for c in CRITERION_CUES)
    counter = "counter_evidence" in roles or any(c in low for c in COUNTER_CUES)
    if ("judgement" in roles and criterion) or (counter and verdict):
        return True
    return any(k in low for k in _JUDGEMENT_MOVE_WORDS)


def _opening(first_sentence: str, para_claims: list) -> tuple[bool, list[str], str]:
    """HI-STR-003 from the parsed role of the paragraph's first claim (notes aside), so the finding and
    the role always agree: ``(opens with evidence, claim ids, how)``. An evidence or counter-evidence
    opening is evidence; a judgement, thesis or link opening is a claim; the point, which the parser
    takes by position, is a claim unless the parser's own predicate (``parser.opens_with_fact``) reads
    it as a bare dated fact with no causal or evaluative word ('The sonnet was printed in January
    1818.'); 'The Treaty of Versailles was a major but partial cause of ...' is a claim. Only when no
    claim of the report stands in the paragraph (a structured report from another parser) is the
    first sentence read alone."""
    first = next((c for c in para_claims if c.claim_role != "other"), None)
    if first is None:
        return opens_with_fact(first_sentence), [], "its first sentence states a dated fact with no claim"
    if first.claim_role in ("evidence", "counter_evidence"):
        return True, [first.claim_id], f"its first claim is roled {first.claim_role}"
    if first.claim_role == "point" and opens_with_fact(first.claim_text):
        return True, [first.claim_id], "its first sentence, the paragraph's point by position, states a dated fact with no causal or evaluative word"
    return False, [first.claim_id], ""


def structural_checks(report: SpecialistReport) -> list[StructuralFinding]:
    f: list[StructuralFinding] = []
    text = report.original_response
    paragraphs = classify_paragraphs(text)
    prose = [(pi, kind, para) for pi, (kind, para) in enumerate(paragraphs) if kind != "note"]
    multi = any(kind in ("intro", "conclusion") for _, kind, _ in prose)
    docs = {t.document_id: t for t in report.supplied_texts}
    searched = ", ".join(docs) or "no supplied text"

    for c in report.claims:
        for ref, g in zip(c.source_refs, check_claim_sources(c, report.supplied_texts)):
            if not ref.excerpt or g.verified is not False or ref.document_id not in docs:
                continue  # found, or no excerpt, or a document the channel names itself (INT-REQ-003)
            detail = g.detail or ""
            if _FORM_DIFFERS in detail:
                f.append(StructuralFinding(code="HI-SRC-001", severity="warning", claim_ids=[c.claim_id], rule_source=_RULE.format("application.md §8.2"),
                                           message=f"quotation '{_shown(ref.excerpt)}' cited to {ref.document_id} occurs there in a different form ({detail}); the words occur, so this is a form difference, not an invented quotation (searched: {searched})"))
            else:
                f.append(StructuralFinding(code="HI-SRC-001", severity="error", claim_ids=[c.claim_id], rule_source=_RULE.format("application.md §8.2"),
                                           message=f"quotation '{_shown(ref.excerpt)}' cited to {ref.document_id} was not found in the supplied source (searched: {searched})"))
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
        para_claims = [c for c in report.claims if c.claim_text in para]
        ids = [c.claim_id for c in para_claims]
        if not judgement_move_present(para, [c.claim_role for c in para_claims]):
            f.append(StructuralFinding(code="HI-STR-001", severity="warning", message=f"body paragraph {pi + 1} has no judgement move (counter-case weighed by a criterion)", claim_ids=ids, rule_source=_RULE.format("structures.md P9")))
        if sum(1 for s in sents if has_dated_item(s)) < 2:
            f.append(StructuralFinding(code="HI-STR-002", severity="info", message=f"body paragraph {pi + 1} has fewer than two dated or figured items", claim_ids=ids, rule_source=_RULE.format("structures.md P7")))
        evidence_first, first_ids, how = _opening(sents[0], para_claims) if sents else (False, [], "")
        if evidence_first:
            f.append(StructuralFinding(code="HI-STR-003", severity="info", message=f"body paragraph {pi + 1} opens with evidence rather than a claim: {how}", claim_ids=first_ids or ids[:1], rule_source=_RULE.format("structures.md P6")))
        for s in sents:
            # The same extractor decides the core pack's formal chronology check, so the proxy and the engine agree.
            for rel in chronology_relations(s, para):
                if rel.violated:
                    f.append(StructuralFinding(code="HI-CHR-001", severity="warning", message=f"a sentence says one dated event came after another ('{rel.cue}'), but the dates it gives are not in that order: {rel.later_text} is not later than {rel.earlier_text}" + (f" ({rel.reason})" if rel.reason else ""), claim_ids=[c.claim_id for c in report.claims if c.claim_text == s], rule_source=_RULE.format("application.md EV2 (exact, dated items)")))

    words = len(re.findall(r"\b[\w'’-]+\b", " ".join(para for _, _, para in prose)))
    if multi and report.task_type == "essay" and not (800 <= words <= 1100):
        f.append(StructuralFinding(code="HI-STR-004", severity="info", message=f"essay length {words} words is outside the pack's exam-length guide (800-1,000 for Paper 2)", rule_source=_RULE.format("structures.md P15")))
    return f
