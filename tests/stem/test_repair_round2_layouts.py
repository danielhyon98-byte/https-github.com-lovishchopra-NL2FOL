"""Repair round 2, STEM layouts that hid a defect (holdout2 classes, measured on probes written for this round), each with
a positive and a clean control, delivered through the hub as a specialist's raw answer:

* a computation set out over lines ('v = 8.4 / 2.0', then 'v = 5.2 m/s') is the chain it spells: its arithmetic is
  checked, and a working that repeats a length given in centimetres as metres is a unit error, also when the law stands
  on a line of its own;
* a product of quantity letters written with spaces ('E = ½ k x²', 'F = k x') is read as the product, so the working is
  checked and the request item is addressed; a bare letter after a number at the end of a sentence is not read;
* two objects told apart by a label ('trolley A', 'trolley B'), or named after the value ('m = 2.0 kg (trolley A)', 'Let
  m = 2.0 kg be the mass of trolley A'), are two quantities, so one symbol bound to both is a symbol conflict;
* a rounded value the answer says meets a target is checked with the value before the rounding;
* a rearranged dilution law (c₁V₁ = c₂V₂) that is a different function of its symbols is a wrong formula;
* a symbol right after a condition's value heads the equation the condition evaluates ('At t = 5.0 min T = …'): it is
  neither a unit of the value (tesla) nor dropped, while a compound unit of a plain value ('2.0 N m = 2.0 J') is kept.
"""
from __future__ import annotations

import re

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document

KEY = b"repair-round-2-stem-layout-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
CHEM = ("Chemistry", "chemistry-specialist")


def receive(answer: str, request: str, subject: str = "Physics", agent: str = "physics-specialist"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent],
                           allowed_document_ids=[]))
    m, _, _ = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def found(rc) -> set[tuple[str, str]]:
    return {(f.code, f.severity) for f in rc.findings}


def defects(rc) -> set[str]:
    return set(re.findall(r'"defect":"([a-z_]+)"', rc.model_dump_json()))


def structural(rc) -> set[str]:
    return {f.code for f in rc.structural_findings}


BALL = "A ball moves 8.4 m in 2.0 s. Calculate its average speed. [2 marks]"
SPRING = "A spring has a spring constant of 250 N m⁻¹. It is extended by 4.0 cm. Calculate the elastic potential energy stored. [2 marks]"


# ----------------------------------------------------------------------------------------------- a computation over lines


@pytest.mark.parametrize("answer, task", [("v = 8.4 / 2.0\nv = 4.2 m/s", BALL), ("v = d/t\nv = 8.4 / 2.0\nv = 4.2 m/s", BALL),
                                             ("v = 10.0 / 3.0\nv = 3.33 m/s", BALL), ("E = ½kx²\nE = ½ × 250 × 0.040²\nE = 0.20 J", SPRING)])
def test_the_right_value_after_its_computation_is_clean(answer, task):
    assert found(receive(answer, task)) == set()


@pytest.mark.parametrize("text", ["(a) v = 8.4 / 2.0\n(b) v = 5.0 m/s", "v = 8.4 / 2.0\na = 5.2 m/s²"])
def test_another_part_or_another_symbol_continues_nothing(text):
    doc = build_document(text, BALL, "physics")
    assert not [r for r in doc.relations if r.kind == "eq" and r.head_gap]


@pytest.mark.parametrize("answer", ["Elastic potential energy E = ½kx²\nk = 250 N/m, x = 4.0 cm\nE = ½ × 250 × 4.0² = 2000 J"])
def test_a_length_in_centimetres_used_as_metres_is_a_unit_error_whatever_the_layout(answer):
    rc = receive(answer, SPRING)
    assert ("INT-SUBJ-004", "warning") in found(rc) and "stem_unit_error" in defects(rc)


@pytest.mark.parametrize("answer", ["Elastic potential energy E = ½kx²\nk = 250 N/m, x = 0.040 m\nE = ½ × 250 × 0.040² = 0.20 J",
                                    "E = ½kx²\nE = ½ × 250 × 0.040²\nE = 0.20 J"])
def test_the_length_converted_to_metres_is_clean(answer):
    assert found(receive(answer, SPRING)) == set()


# ----------------------------------------------------------------------------------------------- spaced products


@pytest.mark.parametrize("text, read", [("So E = 5 k.", "E = 5"), ("We get v = 3 t then", "v = 3"), ("E = ½ k e² is wrong", "E = ½")])
def test_a_bare_letter_after_a_number_or_a_letter_outside_the_reference_is_not_read(text, read):
    doc = build_document(text, SPRING, "physics")
    assert text[doc.items[0].start:doc.items[0].end] == read


# ----------------------------------------------------------------------------------------------- one symbol for two objects

TROLLEYS = ("Trolley A of mass 2.0 kg moves at 3.0 m/s and collides with trolley B of mass 1.0 kg, which is at rest. They stick together. "
            "Calculate their common velocity after the collision. [3 marks]")


@pytest.mark.parametrize("answer", [
    "The mass of trolley A is m = 2.0 kg and the mass of trolley B is m = 1.0 kg.\nMomentum before = m × u = 2.0 × 3.0 = 6.0 kg m/s.\n"
    "After the collision the total mass is 2m = 2 × 1.0 = 2.0 kg, so v = 6.0 / 2.0 = 3.0 m/s.",
    "m = 2.0 kg (trolley A), u = 3.0 m/s, m = 1.0 kg (trolley B).\nTotal momentum p = m u = 2.0 × 3.0 = 6.0 kg m/s\n"
    "v = p / (m + m) = 6.0 / (1.0 + 1.0) = 3.0 m/s",
])
def test_one_symbol_for_two_labelled_objects_is_a_symbol_conflict(answer):
    rc = receive(answer, TROLLEYS)
    assert "ST-SCOPE-002" in structural(rc) and "stem_symbol_conflict" in defects(rc)


@pytest.mark.parametrize("answer", [
    "m₁ = 2.0 kg, m₂ = 1.0 kg, u = 3.0 m/s\nv = m₁u / (m₁ + m₂) = 2.0 × 3.0 / 3.0 = 2.0 m/s",
    "The mass of trolley A is m = 2.0 kg.\nMomentum before = m × u = 2.0 × 3.0 = 6.0 kg m/s.\nTotal mass M = 2.0 + 1.0 = 3.0 kg, so v = 6.0 / 3.0 = 2.0 m/s.",
])
def test_distinct_symbols_or_one_object_are_no_symbol_conflict(answer):
    assert "ST-SCOPE-002" not in structural(receive(answer, TROLLEYS))


# ----------------------------------------------------------------------------------------------- a rounded value against a target

YIELD_LOW = ("The theoretical yield of a reaction is 12.5 g and the actual yield is 9.87 g. Calculate the percentage yield and state whether the "
             "process meets its target of at least 80%. [3 marks]")
YIELD_HIGH = YIELD_LOW.replace("9.87 g", "10.3 g")
MOTOR = "A motor's input is 500 J and its useful output is 348 J. Calculate its efficiency and say whether it reaches the required minimum of 0.70. [3 marks]"


@pytest.mark.parametrize("answer, task, subject", [
    ("Percentage yield = 9.87 / 12.5 × 100 = 78.96% ≈ 80%, so the target of at least 80% is met.", YIELD_LOW, CHEM),
    ("Percentage yield = 9.87 / 12.5 × 100 = 78.96% ≈ 80%, which meets the target.", YIELD_LOW, CHEM),
    ("Percentage yield = (9.87 / 12.5) × 100 = 78.96%. To 1 s.f. this is 80%, which meets the 80% target.", YIELD_LOW, CHEM),
    ("Efficiency = 348 / 500 = 0.696 ≈ 0.70, so it reaches the required minimum.", MOTOR, ("Physics", "physics-specialist")),
])
def test_a_rounded_value_said_to_meet_a_target_it_misses_unrounded_is_named(answer, task, subject):
    rc = receive(answer, task, *subject)
    assert ("INT-SUBJ-004", "warning") in found(rc) and "stem_rounding_changes_conclusion" in defects(rc)


@pytest.mark.parametrize("answer, task, subject", [
    ("Percentage yield = 10.3 / 12.5 × 100 = 82.4% ≈ 82%, so the target of at least 80% is met.", YIELD_HIGH, CHEM),
    ("Percentage yield = 10.3 / 12.5 × 100 = 82.4% ≈ 82%, which meets the target.", YIELD_HIGH, CHEM),
    ("Percentage yield = 9.87 / 12.5 × 100 = 78.96% ≈ 79%, so the target of at least 80% is not met.", YIELD_LOW, CHEM),
    ("Percentage yield = 9.87 / 12.5 × 100 = 78.96%, which is below 80%, so the target is not met.", YIELD_LOW, CHEM),
    ("Percentage yield = 9.87 / 12.5 × 100 = 78.96% ≈ 80%, so the process falls short of the target.", YIELD_LOW, CHEM),
    ("Efficiency = 348 / 500 = 0.696 ≈ 0.70, so it does not reach the required minimum of 0.70.", MOTOR, ("Physics", "physics-specialist")),
])
def test_a_target_statement_that_holds_unrounded_is_clean(answer, task, subject):
    assert "stem_rounding_changes_conclusion" not in defects(receive(answer, task, *subject))


# ----------------------------------------------------------------------------------------------- a dilution solved wrongly

DILUTION = ("25.0 cm³ of 2.00 mol dm⁻³ hydrochloric acid is diluted with water to a total volume of 250.0 cm³. Calculate the concentration "
            "of the diluted acid. [2 marks]")


@pytest.mark.parametrize("answer", ["c₂ = c₁V₂/V₁ = 2.00 × 250.0 / 25.0 = 20.0 mol dm⁻³", "c2 = c1 × V2 / V1 = 2.00 × 250.0 / 25.0 = 20.0 mol dm-3"])
def test_an_inverted_dilution_law_is_a_wrong_formula(answer):
    rc = receive(answer, DILUTION, *CHEM)
    assert "ST-REF-002" in structural(rc) and "stem_wrong_formula" in defects(rc)


@pytest.mark.parametrize("answer", ["c₂ = c₁V₁/V₂ = 2.00 × 25.0 / 250.0 = 0.200 mol dm⁻³",
                                    "c₁V₁ = c₂V₂, so c₂ = c₁V₁/V₂ = 2.00 × 25.0 / 250.0 = 0.200 mol dm⁻³"])
def test_the_dilution_law_solved_correctly_is_clean(answer):
    rc = receive(answer, DILUTION, *CHEM)
    assert "ST-REF-002" not in structural(rc) and found(rc) == set()


# ----------------------------------------------------------------------------------------------- an equation after a condition

COOLING = ("The temperature of a cooling liquid is T = 80 − 4t °C, with t in minutes, for 0 ≤ t ≤ 10. Find the temperature after 5.0 minutes. "
           "[2 marks]")


@pytest.mark.parametrize("text, items", [
    ("The torque is 2.0 N m = 2.0 J.", ["2.0 N m = 2.0 J"]),
])
def test_a_symbol_after_a_conditions_value_heads_its_own_equation(text, items):
    doc = build_document(text, "", "physics")
    assert [text[it.start:it.end] for it in doc.items] == items


def test_the_evaluated_equation_is_checked_and_no_false_error_remains():
    assert found(receive("At t = 5.0 min T = 80 − 4 × 5.0 = 60 °C.", COOLING)) == set()
    assert ("INT-SUBJ-001", "error") in found(receive("At t = 5.0 min T = 80 − 4 × 5.0 = 62 °C.", COOLING))
