"""Repair round 5, STEM: each wrong answer below was delivered with no named defect before the round (or, for the controls,
with a false finding), and each control stays clean.

* ADV5-03: a mass the request gives in grams, substituted unconverted into Q = mcΔT with a specific heat per kilogram that
  only the request states, is a missing conversion (stem_unit_error); the working with the mass in kilograms holds.
* ADV5-04: a given written inline in the substitution ("F = ma = 4.0 kg × ...") that contradicts the value the request
  states is a contradictory given (stem_contradictory_givens); the request's own value is clean.
* ADV5-05: a conclusion drawn from a rounded value ("20.4 kN ≈ 20 kN, so the beam is safe" against "at most 20 kN") is
  stem_rounding_changes_conclusion; the conclusion drawn from the unrounded value is clean.
* ADV5-06: a formula written as adjacent letters ("½mv", "1/2 mv", "2πrh" for a volume) is read as the product it writes,
  so a wrong kinetic-energy formula is stem_wrong_formula, never only "'mv' has no stated value"; ½mv² is clean.
* ADV5-07: one symbol used for two quantities, and the later step using the wrong one, is stem_symbol_conflict; two
  symbols kept apart are clean.
* ADV5-10: a reasoned proof of a property ("Show that 14 is even, giving your reason") is no missing working; a bare
  property or a bare numeric answer to a calculation is still ST-WORK-001.
* ADV5-16: a unit word that also writes a short English word ("at", "as") never continues a unit already begun, so a
  prediction far beyond the measured range is stem_extrapolation; an interpolation is clean.
* ADV5-18: a count the request states in a sentence ("contains 600 undecayed nuclei") is the value of N₀.
* rerun-stem-soundness-10: a '±' step inside a chain ("x + 2 = ±3 ⇒ x = 1 or x = −5") is two equations, so the correct
  roots raise no error; a wrong root is still charged."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"argdiag-stem-test-key-round5-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
AGENTS = {"Chemistry": "chemistry-specialist", "Physics": "physics-specialist", "Mathematics: Analysis and Approaches": "maths-specialist"}
MAA = "Mathematics: Analysis and Approaches"


def _receipt(subject: str, request: str, answer: str):
    agent = AGENTS[subject]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _req, _rq = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return rc


def _defects(rc) -> set[str]:
    return {d.defect for d in (rc.named_diagnostics or []) if d.severity in ("warning", "error")}


def _stem_flags(rc) -> list:
    out = [(f.code, f.severity) for f in rc.structural_findings if f.code.startswith("ST-") and f.severity in ("warning", "error")]
    out += [(f.code, f.severity) for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    out += [(c.constraint_id, "failed") for c in rc.formal_checks if c.satisfied is False and c.constraint_id.startswith("stem-")]
    return out


# ------------------------------------------------------------------------------------------- ADV5-03: a unit only the task gives

BLOCK = "A 300 g aluminium block is heated from 25 °C to 45 °C. Calculate the energy supplied. (c = 900 J kg⁻¹ K⁻¹) [2 marks]"


def test_grams_substituted_against_a_specific_heat_per_kilogram_is_a_missing_conversion():
    assert "stem_unit_error" in _defects(_receipt("Physics", BLOCK, "Q = mcΔT = 300 × 900 × 20 = 5 400 000 J."))


def test_control_the_mass_in_kilograms_is_clean():
    assert _stem_flags(_receipt("Physics", BLOCK, "Q = mcΔT = 0.300 × 900 × 20 = 5400 J.")) == []


# ------------------------------------------------------------------------------------------- ADV5-04: a contradictory given inline

TROLLEY = "A resultant force accelerates a 5.0 kg trolley at 3.0 m s⁻². Calculate the force. [2 marks]"


def test_a_given_written_inline_that_contradicts_the_request_is_named():
    assert "stem_contradictory_givens" in _defects(_receipt("Physics", TROLLEY, "F = ma = 4.0 kg × 3.0 m s⁻² = 12 N."))


def test_control_the_requests_own_value_inline_is_clean():
    assert _stem_flags(_receipt("Physics", TROLLEY, "F = ma = 5.0 kg × 3.0 m s⁻² = 15 N.")) == []


# ------------------------------------------------------------------------------------------- ADV5-05: rounding that decides

BEAM = "A beam is safe when the load on it is at most 20 kN. The load is 20.4 kN. Is the beam safe? Explain. [2 marks]"


def test_a_conclusion_drawn_from_a_rounded_value_is_named():
    assert "stem_rounding_changes_conclusion" in _defects(_receipt("Physics", BEAM, "20.4 kN ≈ 20 kN, so the beam is safe."))


def test_control_the_conclusion_from_the_unrounded_value_is_clean():
    rc = _receipt("Physics", BEAM, "20.4 kN is more than 20 kN, so the beam is not safe.")
    assert "stem_rounding_changes_conclusion" not in _defects(rc)


# ------------------------------------------------------------------------------------------- ADV5-06: adjacent letters

RUNNER = "A 60 kg runner moves at 5.0 m s⁻¹. Calculate the runner's kinetic energy. [2 marks]"


@pytest.mark.parametrize("answer", [
    "E_k = ½mv = 0.5 × 60 × 5.0 = 150 J.",
    "KE = 1/2 mv = 1/2 × 60 × 5.0 = 150 J.",
    "m = 60 kg and v = 5.0 m s⁻¹, so E_k = ½ m v = 0.5 × 60 × 5.0 = 150 J.",
], ids=["one-half glyph", "slash half", "spaced letters"])
def test_a_wrong_formula_written_as_adjacent_letters_is_a_wrong_formula(answer):
    rc = _receipt("Physics", RUNNER, answer)
    assert "stem_wrong_formula" in _defects(rc), sorted(_defects(rc))


def test_control_the_kinetic_energy_formula_is_clean():
    assert _stem_flags(_receipt("Physics", RUNNER, "E_k = ½mv² = 0.5 × 60 × 5.0² = 750 J.")) == []


# ------------------------------------------------------------------------------------------- ADV5-07: one symbol, two quantities

PRESS = ("A force of 300 N acts on an area of 0.60 m². A motor does 1800 J of work in 6.0 s. Calculate the pressure, the power "
         "of the motor, and the force the same pressure exerts on an area of 0.20 m². [4 marks]")


def test_one_symbol_for_two_quantities_used_in_the_wrong_sense_is_named():
    answer = "P = F/A = 300 / 0.60 = 500 Pa. P = W/t = 1800 / 6.0 = 300 W. F = PA = 300 × 0.20 = 60 N."
    assert "stem_symbol_conflict" in _defects(_receipt("Physics", PRESS, answer))


def test_control_two_symbols_kept_apart_are_clean():
    answer = "p = F/A = 300 / 0.60 = 500 Pa. P = W/t = 1800 / 6.0 = 300 W. F = pA = 500 × 0.20 = 100 N."
    assert "stem_symbol_conflict" not in _defects(_receipt("Physics", PRESS, answer))


# ------------------------------------------------------------------------------------------- ADV5-10: a reasoned proof

EVEN = "In this question, an even number is a whole number that 2 divides exactly. Show that 14 is even, giving your reason. [2 marks]"


@pytest.mark.parametrize("request_text, answer", [
    ("Show that √5 is irrational, given that it is not rational. [2 marks]", "Every real number is either rational or irrational. √5 is not rational, so √5 is irrational."),
    (EVEN, "2 divides 14 exactly, and 14 is a whole number, so by the definition 14 is even."),
], ids=["a dichotomy", "a definition"])
def test_a_reasoned_proof_of_a_property_is_no_missing_working(request_text, answer):
    assert "ST-WORK-001" not in {f.code for f in _receipt(MAA, request_text, answer).structural_findings}


@pytest.mark.parametrize("request_text, answer", [(EVEN, "14 is even."), ("Calculate the area of a circle of radius 3.0 cm. [2 marks]", "28.3 cm².")],
                         ids=["a bare property", "a bare result"])
def test_control_a_bare_answer_still_lacks_its_working(request_text, answer):
    assert "ST-WORK-001" in {f.code for f in _receipt(MAA, request_text, answer).structural_findings}


# ------------------------------------------------------------------------------------------- ADV5-16: extrapolation

RATES = ("The initial rate of a reaction was measured at concentrations of 0.20, 0.40, 0.60 and 0.80 mol dm⁻³ as 0.010, 0.020, "
         "0.030 and 0.040 mol dm⁻³ s⁻¹. Predict the initial rate at {c} mol dm⁻³. [2 marks]")


def test_a_prediction_far_beyond_the_measured_range_is_named():
    answer = "The rate is proportional to the concentration, 0.050 s⁻¹ times it, so at 6.0 mol dm⁻³ the rate is 0.050 × 6.0 = 0.30 mol dm⁻³ s⁻¹."
    assert "stem_extrapolation" in _defects(_receipt("Chemistry", RATES.format(c="6.0"), answer))


def test_control_an_interpolation_is_clean():
    answer = "The rate is proportional to the concentration, 0.050 s⁻¹ times it, so at 0.50 mol dm⁻³ the rate is 0.050 × 0.50 = 0.025 mol dm⁻³ s⁻¹."
    assert "stem_extrapolation" not in _defects(_receipt("Chemistry", RATES.format(c="0.50"), answer))


# ------------------------------------------------------------------------------------------- ADV5-18: a count in a sentence

DECAY = "A sample contains 600 undecayed nuclei. The half-life is 5.0 days. Calculate the number of undecayed nuclei after 15 days. [2 marks]"


def test_a_count_the_request_states_in_a_sentence_is_the_value_of_n0():
    rc = _receipt("Physics", DECAY, "15 days is 15 / 5.0 = 3 half-lives, so N = N₀ × (½)³ = 600 / 8 = 75 nuclei.")
    assert not [f for f in rc.structural_findings if f.code == "ST-UNDEC-002" and "N" in f.message], [f.message for f in rc.structural_findings]
    assert _stem_flags(rc) == []


def test_control_a_wrong_count_is_still_charged():
    rc = _receipt("Physics", DECAY, "15 days is 15 / 5.0 = 3 half-lives, so N = N₀ × (½)³ = 600 / 8 = 85 nuclei.")
    assert _stem_flags(rc) != []


# ------------------------------------------------------------------------------------------- '±' inside a chain

def test_a_plus_minus_step_inside_a_chain_is_two_equations():
    rc = _receipt(MAA, "Solve (x + 2)^2 = 9. [2 marks]", "(x + 2)² = 9 ⇒ x + 2 = ±3 ⇒ x = 1 or x = −5.")
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"], [f.message for f in rc.findings]


def test_control_a_wrong_root_after_the_plus_minus_step_is_charged():
    rc = _receipt(MAA, "Solve (x + 2)^2 = 9. [2 marks]", "(x + 2)² = 9 ⇒ x + 2 = ±3 ⇒ x = 1 or x = −1.")
    assert _stem_flags(rc) != []
