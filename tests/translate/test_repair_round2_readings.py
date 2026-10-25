"""Repair round 2, readings fixed at their causes in the round's own probes, each with its positive and its clean control:

* a unit of two or three words after a numeral ("21 m³ s⁻¹", "4200 J kg⁻¹ K⁻¹") is read whole, the longest reading first,
  where "21 m³ s⁻¹" was read as 21 m³ (``translate.quantities``);
* a per-cent change stated across sentences rests on the pair of the sentence before it, whose own sub-clause holds the
  years; a later clause's year ("with a sharp dip in 2020") picks no other pair (``branches.quant``);
* a request item answered by working in the branch's own notation is addressed: the pH from its definition, a Boolean
  identity verified by evaluation, and a formula the item states ("Simpson's diversity index D = 1 − ..."), while an answer
  that does not address the item is still INT-REQ-004 (``channel.bus`` coverage, ``stem.hub_hooks``).
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.quant import extract_quant_checks
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.quantities import SourceText, figures_in

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"repair-round-2-readings-key-0123456789abcd"


# ------------------------------------------------------------------------------------------------------- units of several words
@pytest.mark.parametrize("text, unit", [
    ("The peak discharge was 21 m³ s⁻¹ after the storm.", "m³ s⁻¹"),
    ("Water has a specific heat capacity of 4200 J kg⁻¹ K⁻¹.", "J kg⁻¹ K⁻¹"),
    ("The train ran at 90 km h⁻¹ for an hour.", "km h⁻¹"),
])
def test_a_unit_of_several_words_is_read_whole(text, unit):
    [figure] = figures_in(SourceText("claim", "c", text))
    assert figure.unit == unit and figure.written.endswith(unit)


@pytest.mark.parametrize("text, unit", [("The tank holds 21 m³ of water.", "m³"), ("It was 21 m from the wall.", "m")])
def test_a_one_word_unit_before_prose_stays_one_word(text, unit):
    [figure] = figures_in(SourceText("claim", "c", text))
    assert figure.unit == unit


# ------------------------------------------------------------------------------------------------------- the pair a change rests on
VISITORS = ("Visitors rose from 2.0 million in 2012 to 3.0 million in 2022, despite a slump to 0.9 million in 2020. Over the whole "
            "period visitors grew by about {pct}%, with a sharp dip in 2020.")


def _percent_checks(text: str):
    return [c for c in extract_quant_checks(text, request_id="r", claim_id="c") if c.kind == "percent_change"]


def test_a_change_across_sentences_rests_on_the_pair_of_the_sentence_before():
    checks = _percent_checks(VISITORS.format(pct=50))
    assert checks and {verify(c.problem, CFG).status.value for c in checks} == {"ENTAILED"}


def test_the_wrong_change_on_that_pair_still_fails():
    checks = _percent_checks(VISITORS.format(pct=80))
    assert checks and "COUNTEREXAMPLE" in {verify(c.problem, CFG).status.value for c in checks}


# ------------------------------------------------------------------------------------------------------- request items answered in notation
def _receive(answer: str, request: str, subject: str, agent: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent],
                           allowed_document_ids=[]))
    m, _, _ = hub.dispatch("t", agent, request, [])
    return hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")[1]


def _unaddressed(rc) -> bool:
    return any(f.code == "INT-REQ-004" for f in rc.findings)


@pytest.mark.parametrize("answer, task, subject, agent", [
    ("pH = −log₁₀[H⁺] = −log₁₀(0.0025) = 2.60.", "Calculate the pH of a solution in which [H⁺] = 0.0025 mol dm⁻³. [1 mark]",
     "Chemistry", "chemistry-specialist"),
    ("NOT (A AND B) = NOT (1 AND 0) = NOT 0 = 1. (NOT A) OR (NOT B) = 0 OR 1 = 1. Both sides equal 1.",
     "Using A = 1 and B = 0, verify that NOT (A AND B) = (NOT A) OR (NOT B). [2 marks]", "Computer Science", "cs-specialist"),
    ("N = 10 + 6 + 4 = 20. Σn(n − 1) = 10 × 9 + 6 × 5 + 4 × 3 = 132. N(N − 1) = 20 × 19 = 380. D = 1 − 132/380 = 0.653.",
     "A sample contains three species with 10, 6 and 4 individuals. Calculate Simpson's diversity index D = 1 − Σn(n − 1)/(N(N − 1)).",
     "Environmental Systems and Societies", "ess-specialist"),
])
def test_an_item_answered_in_the_branchs_notation_is_addressed(answer, task, subject, agent):
    assert not _unaddressed(_receive(answer, task, subject, agent))


def test_an_answer_that_does_not_address_the_item_is_still_unaddressed():
    rc = _receive("The solution is acidic because it contains hydrogen ions.",
                  "Calculate the pH of a solution in which [H⁺] = 0.0025 mol dm⁻³. [1 mark]", "Chemistry", "chemistry-specialist")
    assert _unaddressed(rc)


def test_the_change_reads_the_unit_value_exactly():
    # the figure keeps its exact value: the multi-word unit changes what is read after the numeral, not the numeral
    [figure] = figures_in(SourceText("claim", "c", "The peak discharge was 21.5 m³ s⁻¹."))
    assert figure.value == Fraction(43, 2) and figure.places == 1
