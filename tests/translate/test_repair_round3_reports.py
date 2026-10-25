"""Repair round 3: how a delivered answer's argument structure is read (eligibility, the text parsers, the report rules).

* ADV3-01: an argument written in one sentence ("A, so B", "B, which shows that ...") states its own reason, so its claim
  is translated even with no supporting claim; a sentence that opens with a conclusion lead ("So ...", "This shows that
  ...") after another rests on the sentences before it, in both text parsers.
* V3-H2 (invented figure, text delivery): a sentence that opens with a ground phrase pointing back to the sentence before
  ("With turnover that high, ...", "Given figures this stark, ...") is drawn from it, as a reason clause that restates it
  is; the text delivery then reads the argument as the structured report does.
* V3-LEAP-INFO-ONLY: a writer's link that joins a reason about one named thing to a conclusion about another with only a
  bare connective, where no sentence states the connection, is an unbridged leap (ARG-NS-003, warning).
* V3-H2 (bare assertion, report delivery): a report that links no claim to any other gives a ranking judgement ("the most
  effective technique") no reason by its structure, so its describing neighbours are no support by their role alone.

Each rule has its clean controls."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import grounded_on_earlier, opens_with_conclusion, states_own_reason
from epinoic_logic.branches.registry import default_registry
from epinoic_logic.named import is_blocking
from epinoic_logic.translate import diag_argument
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text
from epinoic_logic.translate.diag_core import report_diagnostics
from epinoic_logic.translate.eligibility import decide_eligibility

from ..argdiag_hub import run_case


def _parse(text: str, subject: str, task_type: str = "essay") -> list[ClaimRecord]:
    branch, _profile = default_registry().for_subject(subject)
    return list(branch.parser().parse_response(text, request_id="q", task_id="t", report_id="r", subject=subject, task_type=task_type).claims)


# ------------------------------------------------------------------ ADV3-01: an argument in one sentence

@pytest.mark.parametrize("sentence, connective", [
    ("Britain had the largest navy in 1914, so Britain was certain to win the war.", "so"),
    ("Prices rose sharply, which shows that demand was strong.", "which shows"),
])
def test_a_sentence_that_argues_states_its_own_reason(sentence, connective):
    assert states_own_reason(sentence) == connective


@pytest.mark.parametrize("sentence", ["So far the policy has worked.", "The firm grew so fast that it ran short of cash.",
                                      "Britain had the largest navy in 1914."])
def test_control_no_reason_is_read_where_none_is_stated(sentence):
    assert states_own_reason(sentence) is None


def test_a_one_sentence_argument_is_translated_and_a_bare_point_is_not():
    [argued] = _parse("Britain had the largest navy in 1914, so Britain was certain to win the war.", "History")
    decision = decide_eligibility(argued)
    assert not argued.supporting_claim_ids and decision.eligibility_class.value == "PROPOSITIONAL_ARGUMENT"
    assert "states its own reason" in decision.reasons[-1]
    [bare] = _parse("Britain was certain to win the war.", "History")
    assert decide_eligibility(bare).eligibility_class.value != "PROPOSITIONAL_ARGUMENT"


@pytest.mark.parametrize("text, subject", [
    ("Prices rose sharply in 2022. So the central bank raised interest rates.", "Economics"),
    ("Prices rose sharply in 2022. This shows that the central bank was too slow to act.", "Economics"),
    ("Source A shows unemployment rose to 6 million by 1932. So the republic lost support.", "History"),
])
def test_a_sentence_that_opens_with_a_conclusion_lead_rests_on_the_one_before(text, subject):
    first, second = _parse(text, subject)
    assert second.supporting_claim_ids == [first.claim_id] and opens_with_conclusion(second.claim_text)


# ------------------------------------------------------------------ V3-H2: a ground phrase that points back

EARLIER = ["The case study reports staff turnover of 23% a year at Fenwick Tea Rooms."]


@pytest.mark.parametrize("sentence", [
    "With turnover that high, staffing a third branch would be a serious risk.",
    "Given turnover this high, staffing a third branch would be a serious risk.",
    "With staff turnover so high, the owner should wait.",
    "Given this, staffing a third branch would be a serious risk.",
    "Because of these figures, staffing a third branch would be a serious risk.",
    "In light of that, the owner should wait.",
    "With this in mind, the owner should wait.",
])
def test_a_ground_phrase_pointing_back_draws_on_the_sentence_before(sentence):
    assert grounded_on_earlier(sentence, EARLIER)


@pytest.mark.parametrize("sentence", [
    "With the war over, the owner should wait.",            # no back-reference
    "With that said, the owner should wait.",               # a discourse marker
    "With that, the owner left.",                           # a time: 'thereupon'
    "Because of this law, prices rose.",                    # names what no earlier sentence mentions
    "Given that turnover is high, staffing would be risky.",  # a reason clause, read by leading_reason_clause
    "With rents that high in Ravensby, a third branch is risky.",  # another subject, the degree said of it
])
def test_control_no_ground_phrase_pointing_back(sentence):
    assert not grounded_on_earlier(sentence, EARLIER)


def test_the_text_parsers_rest_a_ground_phrase_on_the_sentence_before():
    figure, risk = _parse(EARLIER[0] + " With turnover that high, staffing a third branch would be a serious risk.", "Business Management",
                          "short_answer")
    assert risk.claim_role == "judgement" and risk.supporting_claim_ids == [figure.claim_id] and not figure.supporting_claim_ids
    claims = _parse("The republic lost support. Source A shows unemployment rose to 6 million by 1932. Given figures this stark, the "
                    "republic lost the middle classes.", "History")
    assert claims[-1].claim_role == "link" and set(claims[-1].supporting_claim_ids) == {claims[0].claim_id, claims[1].claim_id}


def test_control_a_sentence_that_starts_a_new_subject_supports_the_point():
    point, other = _parse(EARLIER[0] + " With rents that high in Ravensby, a third branch is risky.", "Business Management", "short_answer")
    assert other.claim_role != "judgement" and not other.supporting_claim_ids


# ------------------------------------------------------------------ ARG-NS-003: an unbridged leap

ANTE = "the Wall Street Crash of 1929 caused mass unemployment in Germany"
CONS = "the Treaty of Versailles was the main reason the Nazis rose to power"


def test_a_leap_between_two_named_things_joined_only_by_so_is_read():
    text = f"The Wall Street Crash of 1929 caused mass unemployment in Germany, so the Treaty of Versailles was the main reason the Nazis rose to power."
    assert diag_argument.unbridged_leap_reading([text], ANTE, CONS) is not None


@pytest.mark.parametrize("text, ante, cons", [
    # the answer states the connection in a sentence of its own
    ("The Wall Street Crash of 1929 caused mass unemployment in Germany. The Treaty of Versailles shaped how the Crash and mass "
     "unemployment hit Germany. So the Treaty of Versailles was the main reason the Nazis rose to power.", ANTE, CONS),
    # the two sides share a content word: no leap between two things
    ("Germany lost the war, so Germany signed the Treaty of Versailles.", "Germany lost the war", "Germany signed the Treaty of Versailles"),
    # a side names no thing
    ("Prices rose, so demand fell.", "prices rose", "demand fell"),
    # a control cue warrants the step
    ("Patients at Leeds were randomly assigned to the Drug Trial with a control group, so the Ward Programme was effective.",
     "patients at Leeds took part in the Drug Trial", "the Ward Programme was effective"),
])
def test_control_no_unbridged_leap(text, ante, cons):
    assert diag_argument.unbridged_leap_reading([text], ante, cons) is None


def test_the_rule_names_the_dev_leap_and_stays_silent_on_a_valid_argument():
    leap = run_case("f01b_non_sequitur_so", "text")
    named = [d for o in leap.receipt.outcomes for d in o.named_diagnostics if d.code == "ARG-NS-003"]
    assert named and all(is_blocking(d) and d.defect == "leap_in_logic" for d in named)
    clean = run_case("c01_modus_ponens", "text")
    assert not [d for o in clean.receipt.outcomes for d in o.named_diagnostics if d.code == "ARG-NS-003"]


# ------------------------------------------------------------------ ARG-BARE-001 in a report that links nothing

IDS = dict(request_id="req-b", task_id="task-b", report_id="rep-b", agent_id="english-specialist", subject="English Language and Literature",
           task_type="essay")
ITEMS = [type("Item", (), {"item_id": "i1", "text": "Analyse the techniques used in the article.", "command_term": "analyse", "level": 3})()]


def _report(claims: list[tuple[str, str, str, list[str]]]) -> SpecialistReport:
    records = [ClaimRecord(**IDS, claim_id=cid, claim_text=text, claim_role=role, supporting_claim_ids=sup) for cid, text, role, sup in claims]
    body = " ".join(c.claim_text for c in records)
    return SpecialistReport(**IDS, original_response=body, response_sha256=sha256_text(body), claims=records, created_at="2026-10-23T00:00:00Z")


def _bare(report: SpecialistReport) -> list:
    return [d for d in report_diagnostics(report, None, (), items=ITEMS).diagnostics if d.code == "ARG-BARE-001"]


DESCRIBING = [("c1", "The article opens with a statistic about the plastic that reaches the sea every minute.", "evidence", []),
              ("c2", "It closes with a question addressed to the reader.", "evidence", [])]


def test_a_ranking_judgement_in_a_report_that_links_nothing_is_a_bare_assertion():
    report = _report(DESCRIBING + [("c3", "The opening statistic is clearly the most effective technique in the article.", "judgement", [])])
    [d] = _bare(report)
    assert d.claim_ids == ["c3"] and d.severity == "warning"


@pytest.mark.parametrize("judgement", [
    ("c3", "The opening statistic is clearly the most effective technique in the article.", "judgement", ["c1"]),   # linked
    ("c3", "The opening statistic is the most effective technique, because it shocks the reader.", "judgement", []),  # its own reason
    ("c3", "The opening statistic is effective.", "judgement", []),                                                     # ranks nothing
])
def test_control_a_linked_reasoned_or_unranked_judgement_is_no_bare_assertion(judgement):
    assert _bare(_report(DESCRIBING + [judgement])) == []
