"""Repair round 3, STEM: each test failed before its fix and passes after it, with a control that the fix does not turn
correct work into an error.

* stem-soundness-11 variant: a common factor cancelled ("Cancelling x, x = 5") divides both sides by it, as "Dividing by x"
  does: the root line after the equation claims the full set, so the lost root x = 0 fails it, and the step is recorded
  (ST-STEP-002). Control: the factorised working that keeps both roots holds.
* ADV3-03: a percentage written bare and then rounded with its sign ("131 / 250 × 100 = 52.4 ≈ 52%") is one quantity
  written in one unit: no unit companion charges the bare 52.4 against 0.52, so correct working is not withheld. The defect
  of the same shape (a rounding that flips a pass mark) is still named for what it is, never as a unit error.
* ADV3-09 and V3-H2-STEM-MISSES: givens that a reference relation of the subject over-determines (v = u + at with the
  answer's u, v, a and t; ρ = m/V with its ρ, V and m) and contradict it are named (ST-GIVEN-004); a rounding that flips a
  comparison written with the symbol ("5.97 ≈ 6.0 Ω. R is not below 6.0 Ω") is checked (stem-rnd); a rewrite inside a chain
  whose two sides differ at a sample point of the unknown ("log₁₀ x + log₁₀ 2 = log₁₀(x + 2)") is an invalid step
  (ST-STEP-003); a bare answer to a request that asks for the method ("showing your method", "Show that") is missing
  working (ST-WORK-001); a fitted line the request states with its range, used outside it, is an extrapolation in any
  subject (ST-RANGE-001, Geography). Each has its control: consistent givens, a rounding that keeps the verdict, a valid
  rewrite and a valid expansion, worked answers and a request that asks for no method, an estimate inside the range."""
from __future__ import annotations

import pytest

from .argdiag_hub import decided, deliver, plan, stem_flags

MAA = "mathematics_aa"


def _verdicts(text, request=None, profile="physics") -> dict:
    return {cid: ok for cid, (_pc, ok) in decided(text, request, profile).items()}


def _codes(text, request=None, profile="physics") -> list[str]:
    doc, p = plan(text, request, profile)
    return [f.code for f in list(doc.findings) + list(p.findings)]


@pytest.mark.parametrize("text", ["x² = 5x\nCancelling x, x = 5", "x² = 3x\nCancelling x, x = 3", "y² = 7y\nCancelling the y, y = 7",
                                  "x² = 4x\ncancelling a factor of x, x = 4"])
def test_a_root_lost_by_cancelling_the_unknown_fails_like_dividing_by_it(text):
    assert _verdicts(text, None, MAA).get("stem-sol-1") is False
    assert "ST-STEP-002" in _codes(text, None, MAA)


def test_cancelling_control_the_factorised_working_keeps_both_roots():
    assert _verdicts("x² = 5x\nx(x − 5) = 0, so x = 0 or x = 5", None, MAA).get("stem-sol-1") is True


@pytest.mark.parametrize("text", ["131 / 250 × 100 = 52.4 ≈ 52%", "53 / 80 × 100 = 66.25 ≈ 66%", "Score = 41 / 60 × 100 = 68.3 ≈ 68%"])
def test_a_percentage_rounded_with_its_sign_is_no_unit_error(text):
    v = _verdicts(text, None, MAA)
    assert not [cid for cid, ok in v.items() if cid.endswith("u") and ok is False], v
    assert "ST-UNIT-003" not in _codes(text, None, MAA)


def test_a_percentage_rounded_to_another_value_is_still_an_arithmetic_error():
    v = _verdicts("131 / 250 × 100 = 52.4 ≈ 57%", None, MAA)
    assert False in v.values(), v


# ------------------------------------------------------------------ ADV3-09 and V3-H2-STEM-MISSES

SUVAT_REQUEST = "A runner accelerates uniformly from rest. Calculate the distance. [3 marks]"
DENSITY_REQUEST = "A block of density 3000 kg m⁻³ has volume 0.0020 m³. Calculate its weight. Take g = 9.8 N kg⁻¹. [3 marks]"


@pytest.mark.parametrize("text, req", [
    ("Given u = 0 m s⁻¹, v = 12 m s⁻¹, a = 2.0 m s⁻² and t = 5.0 s. s = (u + v)t/2 = (0 + 12) × 5.0 / 2 = 30 m.", SUVAT_REQUEST),
    ("Given ρ = 3000 kg m⁻³, V = 0.0020 m³ and m = 4.0 kg. W = mg = 4.0 × 9.8 = 39 N.", DENSITY_REQUEST),
])
def test_givens_that_contradict_a_reference_relation_are_named(text, req):
    assert "ST-GIVEN-004" in _codes(text, req)


@pytest.mark.parametrize("text, req", [
    ("Given u = 0 m s⁻¹, v = 10 m s⁻¹, a = 2.0 m s⁻² and t = 5.0 s. s = (u + v)t/2 = (0 + 10) × 5.0 / 2 = 25 m.", SUVAT_REQUEST),
    ("Given ρ = 3000 kg m⁻³, V = 0.0020 m³ and m = 6.0 kg. W = mg = 6.0 × 9.8 = 59 N.", DENSITY_REQUEST),
])
def test_control_givens_that_satisfy_the_relation_are_not_named(text, req):
    assert "ST-GIVEN-004" not in _codes(text, req) and False not in _verdicts(text, req).values()


RESISTANCE_REQUEST = ("A part must have a resistance below 6.0 Ω. Resistors of 3.0 Ω and 2.97 Ω are in series. Is the total below the "
                      "limit? [2 marks]")


def test_a_rounding_that_flips_a_comparison_written_with_the_symbol_is_checked():
    v = _verdicts("R = 3.0 + 2.97 = 5.97 ≈ 6.0 Ω. R is not below 6.0 Ω, so the part fails the test.", RESISTANCE_REQUEST)
    assert any(cid.startswith("stem-rnd") and ok is False for cid, ok in v.items()), v


def test_control_the_comparison_read_from_the_unrounded_value_holds():
    v = _verdicts("R = 3.0 + 2.97 = 5.97 Ω. R is below 6.0 Ω, so the part passes the test.", RESISTANCE_REQUEST)
    assert False not in v.values() and not [cid for cid in v if cid.startswith("stem-rnd")]


LOG_REQUEST = "Solve log₁₀ x + log₁₀ 2 = 1. [3 marks]"


def test_a_rewrite_whose_sides_differ_at_a_sample_point_is_an_invalid_step():
    assert "ST-STEP-003" in _codes("log₁₀ x + log₁₀ 2 = log₁₀(x + 2) = 1, so x + 2 = 10 and x = 8.", LOG_REQUEST, MAA)


@pytest.mark.parametrize("text, req", [
    ("log₁₀ x + log₁₀ 2 = log₁₀(2x) = 1, so 2x = 10 and x = 5.", LOG_REQUEST),
    ("(x + 3)² = x² + 6x + 9 = 25, so x² + 6x − 16 = 0, (x + 8)(x − 2) = 0 and x = 2 or x = −8.", "Solve (x + 3)² = 25. [3 marks]"),
])
def test_control_a_valid_rewrite_is_no_invalid_step(text, req):
    assert "ST-STEP-003" not in _codes(text, req, MAA) and False not in _verdicts(text, req, MAA).values()


CONVERT = "Convert the 8-bit two's complement number 11001010 to denary, showing your method. [2 marks]"
SHOW = "Show that the curve y = x³ − 3x has a local minimum at the point (1, −2). [4 marks]"


@pytest.mark.parametrize("case_id, answer, req", [
    ("e2e-B2-cs", "−54", CONVERT),
    ("e2e-B2-maa", "The curve has a local minimum at (1, −2).", SHOW),
])
def test_a_bare_answer_to_a_request_for_the_method_is_missing_working(case_id, answer, req):
    assert ("ST-WORK-001", "warning") in stem_flags(deliver(case_id, answer=answer, request=req))


@pytest.mark.parametrize("case_id, answer, req", [
    ("e2e-B2-cs", "11001010 = −128 + 64 + 8 + 2 = −54", CONVERT),
    ("e2e-B2-cs", "−54", "Convert the 8-bit two's complement number 11001010 to denary. [1 mark]"),
    ("e2e-B2-maa", "dy/dx = 3x² − 3 = 3(x − 1)(x + 1), which is 0 at x = 1. At x = 1, y = 1 − 3 = −2. d²y/dx² = 6x = 6 > 0 at x = 1, "
                   "so (1, −2) is a local minimum.", SHOW),
])
def test_control_worked_answers_and_requests_for_no_method_are_not_missing_working(case_id, answer, req):
    assert not [f for f in stem_flags(deliver(case_id, answer=answer, request=req)) if f[0] == "ST-WORK-001"]


RUNOFF = ("For nine storms with rainfall totals between 5 mm and 35 mm, the peak discharge Q (m³ s⁻¹) fits the line Q = 2.5R + 6, "
          "where R is the storm rainfall in mm. Use the line to estimate the peak discharge for a storm of {} mm. [2 marks]")


def test_a_fitted_line_used_outside_the_range_the_request_states_is_an_extrapolation_in_geography():
    rc = deliver("e2e-B21-ge", answer="Q = 2.5 × 120 + 6 = 300 + 6 = 306 m³ s⁻¹. A 120 mm storm will give a peak discharge of 306 m³ s⁻¹.",
                 request=RUNOFF.format(120))
    assert ("ST-RANGE-001", "warning") in stem_flags(rc)


def test_control_an_estimate_inside_the_range_is_no_extrapolation():
    rc = deliver("e2e-B21-ge", answer="Q = 2.5 × 20 + 6 = 50 + 6 = 56 m³ s⁻¹. A 20 mm storm will give a peak discharge of 56 m³ s⁻¹.",
                 request=RUNOFF.format(20))
    assert stem_flags(rc) == []
