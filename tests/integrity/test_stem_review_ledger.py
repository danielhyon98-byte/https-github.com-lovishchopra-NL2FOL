"""STEM review S6 and the ledger-units policy: the synthesis ledger compares figures as typed quantities
(docs/STEM_DESIGN.md, section 11.5). A value and its significant figures are one spelling, so "3.0e-2 J" and "0.030 J"
are the same figure; a change of value or of significant figures is still an error (INT-LEDGER-023), and the outcomes
are distinct: a value change also drops the source figure (INT-LEDGER-024), a precision change does not. The unit
written after a figure is a separate attribute: "2.0 g" to "2.0 kg" is a changed unit (an error), while "2.0 g" to
"0.0020 kg" is the same quantity in a commensurable unit (no finding), and units of different dimensions never convert."""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.integrity.ledger import canonical_spellings, check_synthesis_ledger, figure_changes, figure_spellings, figure_tokens
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

KEY = b"stem-review-ledger-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def _report(text: str) -> SpecialistReport:
    common = dict(request_id="req", task_id="task", report_id="rep", agent_id="physics-specialist", subject="Physics", task_type="short_answer")
    return SpecialistReport(**common, original_response=text, response_sha256=sha256_text(text), created_at="2026-10-12T00:00:00Z",
                            claims=[ClaimRecord(**common, claim_id="s1.1", claim_text=text, claim_role="quantitative", materiality="material")])


def _synthesis(text: str) -> Synthesis:
    return Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=["rep"],
                     claims=[SynthesizedClaim(claim_id="syn-1", text=text, source_claim_ids=["s1.1"], transformation="paraphrased")],
                     text=text, text_sha256=sha256_hex(text), created_at="2026-10-12T00:00:00Z")


def ledger(source: str, target: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in check_synthesis_ledger([_report(source)], _synthesis(target)):
        if f.code in ("INT-LEDGER-023", "INT-LEDGER-024"):
            out.setdefault(f.code, []).append(f.message)
    return out


# ------------------------------------------------------------------------------------- S6: value and precision


def test_a_change_of_notation_only_is_no_figure_change():
    assert ledger("The energy is 3.0e-2 J.", "The energy is 0.030 J.") == {}
    assert ledger("The energy is 0.030 J.", "The energy is 3.0e-2 J.") == {}
    assert ledger("The energy is 3.0e-2 J.", "The energy is 30e-3 J.") == {}
    assert ledger("c = 3.0 × 10⁸ m s⁻¹", "The speed of light is 300000000 m/s.") == {}  # an integer's trailing zeros may be significant


def test_a_change_of_significant_figures_is_an_error_but_drops_nothing():
    found = ledger("The energy is 3.0e-2 J.", "The energy is 0.03 J.")
    assert list(found) == ["INT-LEDGER-023"]
    assert "changes the precision (significant figures)" in found["INT-LEDGER-023"][0]
    assert "'0.03 J' where the cited sources state 3.0e-2 J (2 significant figures there, 1 significant figure here)" in found["INT-LEDGER-023"][0]
    assert list(ledger("c = 3.0 × 10⁸ m s⁻¹", "c is 3e8 m/s.")) == ["INT-LEDGER-023"]
    assert list(ledger("The rate is 1.50.", "The rate is 1.5.")) == ["INT-LEDGER-023"]


def test_a_change_of_value_is_still_an_introduced_figure_and_a_dropped_one():
    found = ledger("The energy is 3.0e-2 J.", "The energy is 0.031 J.")
    assert set(found) == {"INT-LEDGER-023", "INT-LEDGER-024"}
    assert "states figures or dates ['0.031'] that occur in none of its cited sources" in found["INT-LEDGER-023"][0]
    assert "['3.0e-2']" in found["INT-LEDGER-024"][0]


def test_figures_beyond_the_number_scanners_bounds_are_compared_by_their_written_form():
    assert ledger("The value is 1e100.", "The value is 1e100.") == {}
    assert set(ledger("The value is 1e100.", "The value is 1e999.")) == {"INT-LEDGER-023", "INT-LEDGER-024"}
    assert list(ledger("The value is 1e100.", "The value is 1.0e100.")) == ["INT-LEDGER-023"]  # the same value, more figures
    assert figure_tokens("x = 1e999 and y = 1.0 × 10^999") == set()  # still no exact value, so no token


def test_canonical_spellings_carry_the_significant_figures():
    assert canonical_spellings(Fraction(3, 100), 2, 2) == {"3.0e-2"}
    assert canonical_spellings(Fraction(300), 1, 3) == {"3e2", "3.0e2", "3.00e2"}
    assert canonical_spellings(Fraction(1500), 1, 4) == {"1.5e3", "1.50e3", "1.500e3"}  # a count too small to write it is skipped
    assert canonical_spellings(Fraction(-25, 10), 2, 2) == {"-2.5e0"}
    assert canonical_spellings(Fraction(1, 3), 1, 4) == frozenset() and canonical_spellings(Fraction(0), 1, 1) == frozenset()
    keys = dict(figure_spellings("E = 3.0e-2 J and 0.030 J and 0.03 J"))
    assert keys["3.0e-2"] & keys["0.030"] and not keys["3.0e-2"] & keys["0.03"]


# ------------------------------------------------------------------------------------------------- ledger units


@pytest.mark.parametrize("source,target", [("The mass is 2.0 g.", "The mass is 2.0 kg."), ("The energy is 2.0 J.", "The energy is 2.0 kJ."),
                                           ("The mass is 2.0 g.", "The mass is 2.0 kilograms."), ("The temperature was 25 °C.", "The temperature was 25 K."),
                                           ("The length is 2.0 m.", "The length is 2.0 s.")])
def test_the_same_numeral_with_another_unit_is_a_changed_figure(source, target):
    found = ledger(source, target)
    assert list(found) == ["INT-LEDGER-023"] and "changes the unit of figures" in found["INT-LEDGER-023"][0]


@pytest.mark.parametrize("source,target", [("The mass is 2.0 g.", "The mass is 0.0020 kg."), ("The mass is 2.0 g.", "The mass is 2.0 grams."),
                                           ("It took 1.5 h.", "It took 90 min."), ("It moved at 72 km/h.", "It moved at 20 m/s."),
                                           ("The energy is 2.0 J.", "The energy is 2.0 N m."), ("The temperature was 25 °C.", "The temperature was 298 K."),
                                           ("The mass is 2.0 g.", "The mass is 2.0.")])
def test_the_same_quantity_in_a_commensurable_unit_or_without_its_unit_is_no_change(source, target):
    assert ledger(source, target) == {}


def test_a_conversion_that_changes_the_figures_or_the_value_is_still_flagged():
    precision = ledger("The mass is 2.0 g.", "The mass is 0.002 kg.")
    assert list(precision) == ["INT-LEDGER-023"] and "converts 2.0 g to other significant figures" in precision["INT-LEDGER-023"][0]
    value = ledger("The mass is 2.0 g.", "The mass is 2000 kg.")
    assert set(value) == {"INT-LEDGER-023", "INT-LEDGER-024"} and "['2000']" in value["INT-LEDGER-023"][0]
    assert set(ledger("The temperature was 25 °C.", "The temperature was 300 K.")) == {"INT-LEDGER-023", "INT-LEDGER-024"}


def test_figure_changes_names_each_outcome_separately():
    changes = figure_changes("0.03 J, 2.0 kg, 0.0020 kg and 7.5", ["3.0e-2 J, 2.0 g and 5.5"])
    assert changes.introduced == ["7.5"] and changes.dropped == ["5.5"]
    assert len(changes.reprecised) == 1 and "0.03 J" in changes.reprecised[0]
    assert len(changes.reunited) == 1 and "'2.0 kg' where the cited sources state 2.0 g" in changes.reunited[0]


# ----------------------------------------------------------------------- the reviewer's probe through the channel


def _relay_synthesis(source: str, target: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist", "combinator"]))
    m, _req, _ = hub.dispatch("t", "physics-specialist", "State the value.")
    hub.receive("t", m.message_id, source, agent_id="physics-specialist", report_id="r")
    claim = ch.transmitted_reports["r"].claims[0]
    synth = Synthesis(synthesis_id="syn", request_id="q", task_id="t", combinator_agent_id="combinator", source_report_ids=["r"],
                      claims=[SynthesizedClaim(claim_id="syn1", text=target, source_claim_ids=[claim.claim_id], transformation="paraphrased")],
                      text=target, text_sha256=sha256_hex(target), created_at="2026-10-12T00:00:00Z")
    _msg, receipt = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, synth)
    return sorted({f.code for f in receipt.findings})


def test_the_reviewers_synthesis_probe():
    # only the unchecked-paraphrase warning remains, as for the reviewer's '0.03 J' receipt before the fix (the source's
    # unaddressed-item warning names no claim the synthesis cites, so it stays in the referenced history)
    assert _relay_synthesis("The energy is 3.0e-2 J.", "The energy is 0.030 J.") == ["INT-SYNTH-012"]
    assert "INT-LEDGER-023" in _relay_synthesis("The energy is 3.0e-2 J.", "The energy is 0.031 J.")
    assert "INT-LEDGER-023" in _relay_synthesis("The mass is 2.0 g.", "The mass is 2.0 kg.")
    assert "INT-LEDGER-023" not in _relay_synthesis("The mass is 2.0 g.", "The mass is 0.0020 kg.")
