"""The argument-diagnosis port onto the integrated translator: a lone yes or no is no bare assertion (ARG-BARE-001).

The integrated parsers deliver the answer to a question the text asks itself as a claim of its own (the STEM parser reads
"Is 38 = 67? No." in a trace as the claims "Is 38 = 67?" and "No.", the second a material point), so ARG-BARE-001 named
the answer of a correct trace as a judgement with no reason (the overseer's STEM probe ``boolean-question-control``). A
lone "Yes." or "No." states no judgement of its own; a judgement with no reason is still named."""
from __future__ import annotations

import pytest

from epinoic_logic.translate.diag_argument import bare_yes_no
from epinoic_logic.translate.diag_core import report_diagnostics

from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

from .test_repair_round3_reports import DESCRIBING, IDS, ITEMS


def _report(claims) -> SpecialistReport:
    """As the parsers deliver it: (id, text, role, supports[, materiality])."""
    records = [ClaimRecord(**IDS, claim_id=c[0], claim_text=c[1], claim_role=c[2], supporting_claim_ids=c[3],
                           materiality=c[4] if len(c) > 4 else "material") for c in claims]
    body = " ".join(c.claim_text for c in records)
    return SpecialistReport(**IDS, original_response=body, response_sha256=sha256_text(body), claims=records, created_at="2026-10-23T00:00:00Z")


def _bare(report) -> list:
    return [d for d in report_diagnostics(report, None, (), items=ITEMS).diagnostics if d.code == "ARG-BARE-001"]


@pytest.mark.parametrize("text", ["No.", "Yes.", "no", "YES!", "  No. "])
def test_a_lone_yes_or_no_is_read_as_an_answer(text):
    assert bare_yes_no(text)


@pytest.mark.parametrize("text", ["No, the statistic is the most effective technique.", "Not at all.", "Nobody.", "None.", ""])
def test_control_a_sentence_is_no_lone_yes_or_no(text):
    assert not bare_yes_no(text)


def test_the_answer_to_a_question_the_text_asks_is_no_bare_assertion():
    # as the STEM parser delivers "Is 38 = 67? No.": the question a supporting note, its answer a material point
    report = _report(DESCRIBING + [("c3", "Is the opening statistic the most effective technique in the article?", "other", [], "supporting"),
                                   ("c4", "No.", "point", [])])
    assert [d.claim_ids for d in _bare(report)] == []


def test_control_a_ranking_judgement_beside_the_answer_is_still_a_bare_assertion():
    report = _report(DESCRIBING + [("c3", "The opening statistic is clearly the most effective technique in the article.", "judgement", []),
                                   ("c4", "No.", "point", [])])
    assert [d.claim_ids for d in _bare(report)] == [["c3"]]
