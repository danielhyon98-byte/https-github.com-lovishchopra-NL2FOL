"""Repair round 2, STEM classes of the generalisation review (each with its positive and its clean control, delivered
through the hub as a specialist's raw answer):

* a length or time given in another unit and used unconverted in symbolic working, its result read in the unit the prose
  states (ST-UNIT-003, stem_unit_error);
* a rounded value said to meet a target the unrounded value misses ("89.76% ≈ 90%, so the batch passes the above-90%
  requirement": stem_rounding_changes_conclusion);
* set counts the request states that cannot all hold, and stated values of uniform motion that break its law
  (ST-GIVEN-004, stem_contradictory_givens);
* two's complement place values and Boolean evaluation chains read and checked (a slip in either is an arithmetic slip);
* a regression line the request states, evaluated past the data range it gives (ST-RANGE-001, stem_extrapolation);
* one symbol bound to two values in one part with nothing saying which object each is about: used with values of two
  objects at once (ST-SCOPE-002), or rebound against the value the request states and the new value used (ST-GIVEN-002);
* pressure in physics is in the closed reference, so "P = F × A" for a pressure is stem_wrong_formula (ST-REF-001);
* further shapes of the same classes from the round's own fresh probes: a mass in grams or a current in milliamperes put
  into a symbolic law unconverted, a dated linear trend in mathematics evaluated past its years, a free fall whose stated
  values break v = u + gt, a rounded value said to satisfy the condition a request sets ("acceptable only if ... at least"),
  and the values of two unlabelled resistors used together.
"""
from __future__ import annotations

import re

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"repair-round-2-stem-classes-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
PHYS = ("Physics", "physics-specialist")
CHEM = ("Chemistry", "chemistry-specialist")
MAI = ("Mathematics: Applications and Interpretation", "maths-specialist")
ESS = ("Environmental Systems and Societies", "ess-specialist")
CS = ("Computer Science", "cs-specialist")


def receive(answer: str, request: str, subject: str = "Physics", agent: str = "physics-specialist"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent],
                           allowed_document_ids=[]))
    m, _, _ = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def flagged(rc) -> set[tuple[str, str]]:
    """``(code, defect)`` of every warning or error finding (the defect '' when the finding names none)."""
    return {(f.code, getattr(f, "defect", None) or "") for f in list(rc.findings) + list(rc.structural_findings) if f.severity in ("warning", "error")}


def defects(rc) -> set[str]:
    return set(re.findall(r'"defect":"([a-z_]+)"', rc.model_dump_json()))


def clean(rc) -> bool:
    return not flagged(rc)


# ------------------------------------------------------------------------------------------------------- units in symbolic working
SPRING = "A spring of stiffness 400 N m⁻¹ is stretched by 5.0 cm. Calculate the elastic potential energy stored. [2 marks]"
KETTLE = "A 1500 W kettle runs for 4.0 minutes. Calculate the energy it transfers."


@pytest.mark.parametrize("answer, task", [
    ("E = ½kx² = ½ × 400 × 5.0² = 5000. The elastic potential energy stored is 5000 J.", SPRING),
    ("E = Pt = 1500 × 4.0 = 6000. The kettle transfers 6000 J.", KETTLE),
])
def test_a_value_used_in_its_given_unit_in_symbolic_working_is_a_unit_error(answer, task):
    rc = receive(answer, task, *PHYS)
    assert any(d == "stem_unit_error" for _c, d in flagged(rc)), flagged(rc)


@pytest.mark.parametrize("answer, task", [
    ("E = ½kx² = ½ × 400 × 0.050² = 0.50. The elastic potential energy stored is 0.50 J.", SPRING),
    ("x = 5.0 cm = 0.050 m. E = ½kx² = ½ × 400 × 0.050² = 0.50. The energy stored is 0.50 J.", SPRING),
    ("E = Pt = 1500 × 240 = 360000. The kettle transfers 360000 J.", KETTLE),
])
def test_the_converted_value_is_clean(answer, task):
    assert clean(receive(answer, task, *PHYS))


# ------------------------------------------------------------------------------------------------------- rounding against a target
YIELD = ("A preparation has a theoretical yield of 6.25 g. The batch is accepted only if the percentage yield is above 90%. The actual yield "
         "was 5.61 g. Is the batch accepted? [2 marks]")
MOTOR = "A motor uses 500 J and delivers 347 J of useful energy. The motor meets the standard only if its efficiency is at least 70%. Does it meet the standard?"


@pytest.mark.parametrize("answer, task, subject", [
    ("Percentage yield = 5.61 / 6.25 × 100 = 89.76% ≈ 90%. The yield is 90%, so the batch passes the above-90% requirement.", YIELD, CHEM),
    ("Efficiency = 347 / 500 × 100 = 69.4% ≈ 70%, so the motor meets the at-least-70% standard.", MOTOR, PHYS),
])
def test_a_rounded_value_said_to_meet_a_target_its_unrounded_value_misses_is_named(answer, task, subject):
    rc = receive(answer, task, *subject)
    assert any(d == "stem_rounding_changes_conclusion" for _c, d in flagged(rc)), flagged(rc)


@pytest.mark.parametrize("answer, task, subject", [
    ("Percentage yield = 5.61 / 6.25 × 100 = 89.76%, which is below 90%, so the batch fails the requirement.", YIELD, CHEM),
    ("Efficiency = 347 / 500 × 100 = 69.4% ≈ 69%, so the motor does not meet the standard.", MOTOR, PHYS),
    ("Efficiency = 347 / 500 × 100 = 69.4%. Rounded to the nearest whole number this is 69%, so the motor fails the standard.", MOTOR, PHYS),
])
def test_a_target_judged_on_the_unrounded_value_is_not_named(answer, task, subject):
    rc = receive(answer, task, *subject)
    assert "stem_rounding_changes_conclusion" not in {d for _c, d in flagged(rc)}, flagged(rc)


# ------------------------------------------------------------------------------------------------------- contradictory givens
CLUB_BAD = "In a club of 90 members, 50 play tennis, 45 play squash, 15 play both and 5 play neither. Find the number who play tennis only. [2 marks]"
CLUB_OK = "In a club of 90 members, 50 play tennis, 45 play squash, 15 play both and 10 play neither. Find the number who play tennis only. [2 marks]"
CYCLE_BAD = "A cyclist accelerates uniformly from rest at 2.0 m s⁻² for 5.0 s, reaching a speed of 12 m s⁻¹. Calculate the distance travelled. [2 marks]"
CYCLE_OK = "A cyclist accelerates uniformly from rest at 2.0 m s⁻² for 5.0 s, reaching a speed of 10 m s⁻¹. Calculate the distance travelled. [2 marks]"


def test_set_counts_that_cannot_all_hold_are_contradictory_givens():
    rc = receive("n(T only) = n(T) − n(T ∩ S) = 50 − 15 = 35. So 35 members play tennis only.", CLUB_BAD, *MAI)
    assert ("ST-GIVEN-004", "stem_contradictory_givens") in flagged(rc)
    assert clean(receive("n(T only) = n(T) − n(T ∩ S) = 50 − 15 = 35. So 35 members play tennis only.", CLUB_OK, *MAI))
    # an answer that says the counts are inconsistent has seen it
    assert clean(receive("50 + 45 − 15 + 5 = 85, so the counts are inconsistent with 90 members. Taking the set counts as given, n(T only) = "
                         "50 − 15 = 35.", CLUB_BAD, *MAI))


def test_values_that_break_the_law_of_uniform_motion_are_contradictory_givens():
    rc = receive("u = 0, a = 2.0 m s⁻², t = 5.0 s, v = 12 m s⁻¹. s = (u + v)t/2 = (0 + 12) × 5.0 / 2 = 30 m. The cyclist travels 30 m.", CYCLE_BAD, *PHYS)
    assert ("ST-GIVEN-004", "stem_contradictory_givens") in flagged(rc)
    assert clean(receive("u = 0, a = 2.0 m s⁻², t = 5.0 s, v = 10 m s⁻¹. s = (u + v)t/2 = (0 + 10) × 5.0 / 2 = 25 m. The cyclist travels 25 m.",
                         CYCLE_OK, *PHYS))
    assert clean(receive("u = 0, a = 2.0 m s⁻², t = 5.0 s, v = 12 m s⁻¹. These values are inconsistent, since u + at = 10 m s⁻¹. Using s = ut + "
                         "½at², s = 25 m.", CYCLE_BAD, *PHYS))


# ------------------------------------------------------------------------------------------------------- two's complement and Boolean chains
TWOS = "Convert the 8-bit two's complement number 11010011 to denary, showing your method. [2 marks]"
DEMORGAN = "Using A = 1 and B = 0, verify that NOT (A AND B) = (NOT A) OR (NOT B). [2 marks]"


def test_twos_complement_place_values_are_read_and_checked():
    assert clean(receive("The place values are −128, 64, 32, 16, 8, 4, 2, 1. 11010011 = −128 + 64 + 16 + 2 + 1 = −45.", TWOS, *CS))
    rc = receive("The place values are −128, 64, 32, 16, 8, 4, 2, 1. 11010011 = −128 + 64 + 16 + 2 + 1 = −47.", TWOS, *CS)
    assert ("INT-SUBJ-001", "stem_arithmetic_slip") in flagged(rc)
    assert clean(receive("01010011 = 64 + 16 + 2 + 1 = 83.", "Convert the 8-bit two's complement number 01010011 to denary.", *CS))


def test_a_boolean_evaluation_chain_is_checked_link_by_link():
    assert clean(receive("NOT (A AND B) = NOT (1 AND 0) = NOT 0 = 1. (NOT A) OR (NOT B) = 0 OR 1 = 1. Both sides equal 1.", DEMORGAN, *CS))
    rc = receive("NOT (A AND B) = NOT (1 AND 0) = NOT 1 = 0. (NOT A) OR (NOT B) = 0 OR 1 = 1. So the two sides differ.", DEMORGAN, *CS)
    assert ("INT-SUBJ-001", "stem_arithmetic_slip") in flagged(rc)
    assert clean(receive("A + AB = A(1 + B) = A.", "Simplify A + AB.", *CS))
    assert ("INT-SUBJ-001", "stem_arithmetic_slip") in flagged(receive("A + AB = A(1 + B) = B.", "Simplify A + AB.", *CS))


# ------------------------------------------------------------------------------------------------------- a stated model past its data
LINE = ("For ten students, hours of practice h (from 1 to 8 hours) and test score s give the regression line s = 6.5h + 30. Use the line to "
        "predict the score of a student who practises for 20 hours. [2 marks]")
ALGAE = ("For eight ponds with nitrate concentrations between 2 mg/l and 12 mg/l, algal cover A (%) fits the line A = 3.5N + 10, where N is the "
         "nitrate concentration in mg/l. Use the line to estimate the algal cover at 30 mg/l.")


@pytest.mark.parametrize("answer, task, subject", [
    ("s = 6.5 × 20 + 30 = 130 + 30 = 160. The student would score 160.", LINE, MAI),
    ("A = 3.5 × 30 + 10 = 105 + 10 = 115%. The algal cover at 30 mg/l is 115%.", ALGAE, ESS),
])
def test_a_request_model_evaluated_past_the_range_it_states_is_an_extrapolation(answer, task, subject):
    assert ("ST-RANGE-001", "stem_extrapolation") in flagged(receive(answer, task, *subject))


@pytest.mark.parametrize("answer, task, subject", [
    ("s = 6.5 × 5 + 30 = 32.5 + 30 = 62.5. The student would score about 63.", LINE.replace("for 20 hours", "for 5 hours"), MAI),
    ("s = 6.5 × 20 + 30 = 160, but 20 hours is far outside the data, so this extrapolation may be unreliable.", LINE, MAI),
    ("A = 3.5 × 8 + 10 = 28 + 10 = 38%. The algal cover at 8 mg/l is 38%.", ALGAE.replace("at 30 mg/l", "at 8 mg/l"), ESS),
])
def test_the_model_inside_its_range_or_with_its_caveat_is_not_an_extrapolation(answer, task, subject):
    assert "stem_extrapolation" not in {d for _c, d in flagged(receive(answer, task, *subject))}


# ------------------------------------------------------------------------------------------------------- one symbol, two objects
BALLS = "Ball A (0.50 kg) moves at 4.0 m/s and ball B (0.20 kg) moves at 6.0 m/s. Calculate the momentum of ball A. [2 marks]"
CYCLIST = "A cyclist accelerates uniformly from 2.0 m/s to 8.0 m/s in 3.0 s. Calculate the acceleration. [2 marks]"


def test_values_of_two_unlabelled_objects_used_together_are_a_symbol_conflict():
    rc = receive("m = 0.50 kg and v = 4.0 m/s, and m = 0.20 kg and v = 6.0 m/s. p = mv = 0.50 × 6.0 = 3.0 kg m/s.", BALLS, *PHYS)
    assert ("ST-SCOPE-002", "stem_symbol_conflict") in flagged(rc)
    assert sum(1 for c, _d in flagged(rc) if c == "ST-SCOPE-002") == 1        # one finding for the pair of symbols


@pytest.mark.parametrize("answer", [
    "m = 0.50 kg and v = 4.0 m/s, and m = 0.20 kg and v = 6.0 m/s. p = mv = 0.50 × 4.0 = 2.0 kg m/s.",
    "For A, p = mv = 0.50 × 4.0 = 2.0 kg m/s. For B, p = mv = 0.20 × 6.0 = 1.2 kg m/s.",
])
def test_values_kept_to_one_object_are_no_symbol_conflict(answer):
    assert "stem_symbol_conflict" not in {d for _c, d in flagged(receive(answer, BALLS, *PHYS))}


def test_a_given_rebound_against_the_request_and_used_is_contradictory_givens():
    rc = receive("u = 2.0 m/s, v = 8.0 m/s, t = 3.0 s, and t = 2.0 s. a = (v − u)/t = 6.0 / 2.0 = 3.0 m/s².", CYCLIST, *PHYS)
    assert ("ST-GIVEN-002", "stem_contradictory_givens") in flagged(rc)
    # controls: the request's own time used; two times the request both states
    assert clean(receive("u = 2.0 m/s, v = 8.0 m/s, t = 3.0 s. a = (v − u)/t = 6.0 / 3.0 = 2.0 m/s².", CYCLIST, *PHYS))
    both = ("A cyclist accelerates from rest for 3.0 s and then brakes for 2.0 s. Calculate the acceleration while braking from 6.0 m/s to "
            "rest. [2 marks]")
    assert "stem_contradictory_givens" not in {d for _c, d in flagged(receive("t = 3.0 s, and t = 2.0 s. a = (v − u)/t = (0 − 6.0) / 2.0 = "
                                                                               "−3.0 m/s².", both, *PHYS))}


# ------------------------------------------------------------------------------------------------------- pressure in the closed reference
PRESSURE = "A box of weight 600 N rests on a base of area 0.30 m². Calculate the pressure on the floor. [2 marks]"


@pytest.mark.parametrize("answer", ["P = F × A = 600 × 0.30 = 180 Pa.", "p = F × A = 600 × 0.30 = 180 Pa."])
def test_a_pressure_law_with_the_wrong_dimension_is_a_wrong_formula(answer):
    rc = receive(answer, PRESSURE, *PHYS)
    assert ("ST-REF-001", "stem_wrong_formula") in flagged(rc)


@pytest.mark.parametrize("answer, task", [
    ("P = F/A = 600 / 0.30 = 2000 Pa.", PRESSURE),
    ("P = W/t = 600/120 = 5.0 W.", "A motor does 600 J of work in 120 s. Calculate its power."),
    ("p = mv = 2.0 × 3.0 = 6.0 kg m/s.", "A 2.0 kg trolley moves at 3.0 m/s. Calculate its momentum."),
])
def test_pressure_power_and_momentum_with_their_own_laws_are_clean(answer, task):
    assert "stem_wrong_formula" not in defects(receive(answer, task, *PHYS))


# ------------------------------------------------------------------------------------------------------- further shapes (own fresh probes)
DROP = "A 250 g mass falls through a height of 2.0 m. Calculate the gravitational potential energy it loses. Use g = 9.8 N kg⁻¹. [2 marks]"
SHUNT = "A current of 300 mA flows through a 20 Ω resistor. Calculate the potential difference across it. [2 marks]"


@pytest.mark.parametrize("answer, task", [
    ("ΔEp = mgΔh = 250 × 9.8 × 2.0 = 4900 J.", DROP),
    ("V = IR = 300 × 20 = 6000 V.", SHUNT),
])
def test_a_mass_or_current_used_in_its_given_submultiple_is_a_unit_error(answer, task):
    assert any(d == "stem_unit_error" for _c, d in flagged(receive(answer, task, *PHYS)))


@pytest.mark.parametrize("answer, task", [
    ("ΔEp = mgΔh = 0.250 × 9.8 × 2.0 = 4.9 J.", DROP),
    ("V = IR = 0.300 × 20 = 6.0 V.", SHUNT),
])
def test_the_submultiple_converted_is_clean(answer, task):
    assert clean(receive(answer, task, *PHYS))


TOWN = "A town's population was 20 000 in 2010 and grew steadily to 25 000 in 2020. Assuming a linear trend, estimate the population in 2060."
SALES = "A firm sold 1200 units in 2018 and 1500 units in 2021. Assuming a linear model, estimate the sales in 2030."


@pytest.mark.parametrize("answer, task", [
    ("P = 20 000 + 500(t − 2010), so in 2060 P = 20 000 + 500 × 50 = 45 000.", TOWN),
    ("Sales rise by 100 per year, so S = 1200 + 100(t − 2018) and in 2030 S = 1200 + 100 × 12 = 2400.", SALES),
])
def test_a_dated_trend_evaluated_past_its_years_is_an_extrapolation(answer, task):
    assert ("ST-RANGE-001", "stem_extrapolation") in flagged(receive(answer, task, *MAI))


@pytest.mark.parametrize("answer, task", [
    ("P = 20 000 + 500(t − 2010), so in 2015 P = 20 000 + 500 × 5 = 22 500.", TOWN.replace("2060", "2015")),
    ("Sales rise by 100 per year, so S = 1200 + 100(t − 2018) and in 2020 S = 1200 + 100 × 2 = 1400.", SALES.replace("2030", "2020")),
    ("Sales rise by 100 per year, so S = 1200 + 100(t − 2018) and in 2030 S = 1200 + 100 × 12 = 2400, although this extrapolates beyond the "
     "data and may be unreliable.", SALES),
    # amounts of money and terms of a sequence are no dated years
    ("V = 1000 × 1.05¹⁰ = 1628.89 dollars.", "An investment of 1000 dollars earns 5% compound interest per year. Find its value after 10 years."),
    ("u10 = 2010 + 9 × 5 = 2055.", "The arithmetic sequence 2010, 2015, 2020, ... continues. Find the 10th term."),
])
def test_a_dated_trend_inside_its_years_or_no_dated_trend_is_no_extrapolation(answer, task):
    assert "stem_extrapolation" not in {d for _c, d in flagged(receive(answer, task, *MAI))}


STONE = "A stone is dropped from rest and falls for 2.0 s, reaching 25 m/s. Calculate the distance it falls. Take g = 9.8 m/s². [2 marks]"
BALL = "A ball is released from rest and falls freely for 3.0 s, reaching 40 m/s. Calculate the distance it falls. Take g = 9.8 m/s². [2 marks]"


@pytest.mark.parametrize("answer, task", [
    ("u = 0, a = 9.8 m/s², t = 2.0 s, v = 25 m/s. s = (u + v)t/2 = (0 + 25) × 2.0 / 2 = 25 m.", STONE),
    ("u = 0, a = 9.8 m/s², t = 3.0 s, v = 40 m/s. s = (u + v)t/2 = (0 + 40) × 3.0 / 2 = 60 m.", BALL),
])
def test_a_free_fall_whose_values_break_its_law_is_contradictory_givens(answer, task):
    assert ("ST-GIVEN-004", "stem_contradictory_givens") in flagged(receive(answer, task, *PHYS))


@pytest.mark.parametrize("answer, task", [
    ("u = 0, a = 9.8 m/s², t = 2.0 s, v = 19.6 m/s. s = (u + v)t/2 = (0 + 19.6) × 2.0 / 2 = 19.6 m.", STONE.replace("25 m/s", "19.6 m/s")),
    ("u = 0, a = 9.8 m/s², t = 2.0 s, v = 25 m/s. These values are inconsistent, since u + at = 19.6 m/s. Using s = ut + ½at², s = 19.6 m.", STONE),
    # a fall against air resistance is not uniform: v = u + gt is no law of it
    ("u = 0, a = 9.8 m/s², t = 2.0 s, v = 25 m/s. s = (u + v)t/2 = (0 + 25) × 2.0 / 2 = 25 m.",
     "A skydiver falls from rest against air resistance and reaches 25 m/s after 2.0 s. Calculate the distance fallen, taking the average "
     "speed as half the final speed. Take g = 9.8 m/s². [2 marks]"),
])
def test_a_consistent_resisted_or_acknowledged_fall_is_not_contradictory(answer, task):
    assert "stem_contradictory_givens" not in {d for _c, d in flagged(receive(answer, task, *PHYS))}


TITRE = ("Three repeat titres were 24.42, 24.48 and 24.44 cm³. The method is acceptable only if the mean titre is at least 24.45 cm³. Is it "
         "acceptable?")
BRIDGE = "A load of 4999.6 N is applied. The bridge is safe only if the load is less than 5000 N. Is the bridge safe?"


@pytest.mark.parametrize("answer, task, subject", [
    ("Mean = (24.42 + 24.48 + 24.44) / 3 = 24.447 ≈ 24.45 cm³, so the method is acceptable.", TITRE, CHEM),
    ("Load = 4999.6 N ≈ 5000 N, so the bridge is not safe.", BRIDGE, PHYS),
    ("Load = 4999.6 N ≈ 5000 N, so the bridge is unsafe.", BRIDGE, PHYS),
])
def test_a_rounded_value_said_to_satisfy_the_requests_condition_is_named(answer, task, subject):
    assert ("INT-SUBJ-004", "stem_rounding_changes_conclusion") in flagged(receive(answer, task, *subject))


@pytest.mark.parametrize("answer, task, subject", [
    ("Mean = (24.42 + 24.48 + 24.44) / 3 = 24.447 cm³, which is below 24.45 cm³, so the method is not acceptable.", TITRE, CHEM),
    ("Mean = (24.42 + 24.48 + 24.44) / 3 = 24.447 ≈ 24.4 cm³, so the method is not acceptable.", TITRE, CHEM),
    ("Mean = (24.42 + 24.48 + 24.44) / 3 = 24.447 ≈ 24.45 cm³, so the method is unacceptable.", TITRE, CHEM),
    ("Mean = (24.46 + 24.48 + 24.47) / 3 = 24.47 ≈ 24.5 cm³, so the method is acceptable.",
     TITRE.replace("24.42, 24.48 and 24.44", "24.46, 24.48 and 24.47"), CHEM),
])
def test_a_condition_judged_on_the_value_before_the_rounding_is_not_named(answer, task, subject):
    assert "stem_rounding_changes_conclusion" not in {d for _c, d in flagged(receive(answer, task, *subject))}


RESISTORS = "Resistor A (10 Ω) carries 2.0 A; resistor B (20 Ω) carries 0.50 A. Calculate the potential difference across resistor A. [2 marks]"


def test_values_of_two_unlabelled_resistors_used_together_are_a_symbol_conflict():
    rc = receive("R = 10 Ω and I = 2.0 A, and R = 20 Ω and I = 0.50 A. V = IR = 0.50 × 10 = 5.0 V.", RESISTORS, *PHYS)
    assert ("ST-SCOPE-002", "stem_symbol_conflict") in flagged(rc)
    assert clean(receive("R = 10 Ω and I = 2.0 A, and R = 20 Ω and I = 0.50 A. V = IR = 2.0 × 10 = 20 V.", RESISTORS, *PHYS))


TITRE_TARGET = "Three repeat titres were 24.42, 24.48 and 24.44 cm³. The target is a mean titre of at least 24.45 cm³. Is the target met?"


def test_a_bare_value_before_the_rounding_is_read_in_the_rounded_values_unit():
    # '= 24.447 ≈ 24.45 cm³' writes the unit once: 24.447 is in cm³ too, so the comparison with 24.45 cm³ is made in one unit
    # (read in SI against 24.45 cm³ in m³, the bare 24.447 met every target and the control was a false alarm)
    assert ("INT-SUBJ-004", "stem_rounding_changes_conclusion") in flagged(receive(
        "Mean = (24.42 + 24.48 + 24.44) / 3 = 24.447 ≈ 24.45 cm³, so the target of at least 24.45 cm³ is met.", TITRE_TARGET, *CHEM))
    assert "stem_rounding_changes_conclusion" not in {d for _c, d in flagged(receive(
        "Mean = (24.42 + 24.48 + 24.44) / 3 = 24.447 ≈ 24.4 cm³, so the target of at least 24.45 cm³ is not met.", TITRE_TARGET, *CHEM))}
    # the per cent sign written once: '× 100 = 78.96 ≈ 79%' has 78.96 in per cent (its unit companion fails on its own, by
    # the per cent rule of ST-UNIT-003); a fraction converted in the rounding step ('= 0.7896 ≈ 79%') keeps its own scale
    motor = "A motor takes in 500 J and gives out 394.8 J of useful work. The design target is an efficiency of at least 79%. Does it meet it?"
    assert ("INT-SUBJ-004", "stem_rounding_changes_conclusion") in flagged(receive(
        "Efficiency = 394.8 / 500 × 100 = 78.96 ≈ 79%, so the target of at least 79% is met.", motor, *PHYS))
    assert ("INT-SUBJ-004", "stem_rounding_changes_conclusion") in flagged(receive(
        "Efficiency = 394.8 / 500 = 0.7896 ≈ 79%, so the target of at least 79% is met.", motor, *PHYS))
    for answer in ("Efficiency = 394.8 / 500 × 100 = 78.96 ≈ 79%, so the target of at least 79% is not met.",
                   "Efficiency = 394.8 / 500 = 0.7896 ≈ 79%, so the target of at least 79% is not met."):
        assert "stem_rounding_changes_conclusion" not in {d for _c, d in flagged(receive(answer, motor, *PHYS))}
