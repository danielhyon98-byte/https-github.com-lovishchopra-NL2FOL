"""The STEM tolerance rule R1 to R10 (docs/STEM_DESIGN.md, section 5.2): the half-width and slack
computed from written digits, the band as IR data, and each rule decided by the engine on a
minimal answer, including the integer trailing-zero rule and the observed case."""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.numbers import scan_number
from epinoic_logic.stem.tolerance import (
    SHORT_RULE, STEM_SCOPE, STEM_TOLERANCE_RULE, TAU_APPROX, TAU_EQUAL, band_expr, half_width, is_measured, tau_for,
)

CFG = SolverConfig(timeout_ms=10000, memory_max_mb=None)


def num(text: str):
    s = scan_number(text, 0)
    assert s is not None and s.number is not None
    return s.number


def outcome(pc):
    res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy))
    if res.status.value == pc.expected_if_sound and not any(d.code == "E108" for d in res.diagnostics):
        return True, res
    if res.status.value in ("ENTAILED", "COUNTEREXAMPLE", "SATISFIABLE", "UNSATISFIABLE"):
        return False, res
    return None, res


def decide(text: str, check_id: str, request: str | None = None, profile: str = "physics"):
    doc = build_document(text, request, profile)
    plan = build_checks(doc, report_id="r", request_id="q")
    pc = plan.check(check_id)
    assert pc is not None, (check_id, [c.check_id for c in plan.checks], plan.findings)
    return outcome(pc)[0], pc


def test_rule_texts():
    assert len(SHORT_RULE) <= 300
    for k in range(1, 12):  # R11 (the central value of S ± u) since STEM repair 3
        assert f"R{k}" in STEM_TOLERANCE_RULE
    assert "S ± u, is set against C at its central value S" in STEM_TOLERANCE_RULE
    assert "encoding only" in STEM_SCOPE and "does not establish" in STEM_SCOPE


# --------------------------------------------------------------------------- R1 and R2 from the digits


@pytest.mark.parametrize("text,h", [("5.0", Fraction(1, 20)), ("1.20 × 10³", Fraction(5)), ("0", Fraction(0)), ("0.0", Fraction(1, 20)),
                                    ("25", Fraction(1, 2)), ("1200", Fraction(50)), ("6.0E-3", Fraction(5, 100000)), ("10⁻³", Fraction(0))])
def test_r1_half_width(text, h):
    assert half_width(num(text)) == h


@pytest.mark.parametrize("min_sf,h", [(2, Fraction(50)), (3, Fraction(5)), (4, Fraction(1, 2)), (1, Fraction(50)), (None, Fraction(50))])
def test_r1_integer_trailing_zero_rule(min_sf, h):
    assert half_width(num("1200"), min_sig_figs=min_sf) == h


def test_r1_exact_mode_and_measurement():
    assert half_width(num("5.0"), exact_mode=True) == 0
    assert is_measured(num("5.0"), False) and is_measured(num("5"), True) and not is_measured(num("5"), False)


def test_r2_slack():
    assert tau_for("eq", approx=False, exact_mode=False) == TAU_EQUAL == Fraction(1, 100)
    assert tau_for("eq", approx=True, exact_mode=False) == TAU_APPROX == Fraction(1, 20)
    assert tau_for("eq", approx=False, exact_mode=True) == 0
    for kind in ("cnv", "cmp", "res", "sub-match", "sol-root"):
        assert tau_for(kind, approx=False, exact_mode=False) == 0


def test_band_is_ir_data():
    c, r = {"op": "var", "name": "c"}, {"op": "var", "name": "r"}
    b = band_expr(c, r, {"op": "real", "value": "0.05"}, Fraction(1, 100))
    assert b["op"] == "le" and b["left"]["op"] == "ite" and b["right"]["op"] == "add"
    b0 = band_expr(c, r, {"op": "real", "value": "0.05"}, Fraction(0))
    assert b0["right"] == {"op": "real", "value": "0.05"}


# --------------------------------------------------------------------------- the observed case and R4


def test_the_observed_case_fails_with_c_5_and_r_6():
    ok, pc = decide("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². The acceleration is therefore 6.0 m s⁻².",
                    "stem-eq-1")
    assert ok is False and pc.failure_severity == "error" and pc.form == "E"
    res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy))
    model = {a.symbol: a.value for a in res.counterexample.assignments}
    assert model["c"] == "5" and model["r"] == "6"


@pytest.mark.parametrize("stated,expected", [("5.0", True), ("5.04", True), ("5.1", True), ("5.2", False), ("6.0", False), ("4.9", True), ("4.8", False)])
def test_r4_band_around_the_computed_value(stated, expected):
    ok, _pc = decide(f"a = (20 - 0)/4.0 = {stated} m s⁻²", "stem-eq-1")
    assert ok is expected


@pytest.mark.parametrize("stated,expected", [("-19.6", True), ("-19.62", True), ("19.6", False), ("-20.5", False)])
def test_r4_sign_aware(stated, expected):
    ok, _pc = decide(f"v = u + at = 0 + (-9.81)(2.0) = {stated} m s⁻¹", "stem-eq-1")
    assert ok is expected


def test_r4_zero():
    assert decide("F = 2.0 × 3.0 - 6.0 = 0 N", "stem-eq-1")[0] is True
    assert decide("F = 2.0 × 3.0 - 5.0 = 0 N", "stem-eq-1")[0] is False


def test_r2_approx_widens_to_five_per_cent():
    assert decide("s = 2.0 × 21 ≈ 44 m", "stem-eq-1")[0] is True        # 42 vs 44: within 5 %
    assert decide("s = 2.0 × 21 = 44 m", "stem-eq-1")[0] is False       # but not within 1 % + h
    assert decide("s = 2.0 × 21 ≈ 48 m", "stem-eq-1")[0] is False


def test_r2_exact_mode():
    assert decide("7/3 = 2", "stem-eq-1", profile="mathematics_aa")[0] is False
    assert decide("√2 = 1.41", "stem-eq-1", profile="mathematics_aa")[0] is True
    assert decide("640 × ½³ = 80", "stem-eq-1", profile="mathematics_aa")[0] is True


def test_r1_trailing_zeros_follow_the_operands():
    assert decide("F = 3.0 × 410 = 1200 N", "stem-eq-1")[0] is True    # 2 s.f. operands: h(1200) = 50
    assert decide("F = 3.00 × 410 = 1200 N", "stem-eq-1")[0] is False  # 3 s.f.: h(1200) = 5, |1230 − 1200| = 30


# --------------------------------------------------------------------------- R3 to R10


def test_r3_carried_intermediate():
    text = "a = 9.7/2.0 = 4.85 m s⁻² ≈ 5 m s⁻². So F = ma = 3.0 × 5 = 14.6 N."
    ok, pc = decide(text, "stem-eq-2")
    assert ok is True and pc.form == "S"


def test_r3_written_constant():
    ok, pc = decide("W = 40 × 9.8 = 392 N", "stem-eq-1")
    assert ok is True and pc.form == "S" and "written constant" in pc.description


def test_r5_conversions_are_exact():
    assert decide("d = 2.5 km = 2500 m", "stem-cnv-1")[0] is True
    assert decide("d = 2.5 km = 2700 m", "stem-cnv-1")[0] is False
    # 2.5 km is [2450, 2550] m and 2600 m (2 s.f.) is [2550, 2650] m: the rounding intervals touch, so it holds
    assert decide("d = 2.5 km = 2600 m", "stem-cnv-1")[0] is True
    assert decide("d = 2.50 km = 2600 m", "stem-cnv-1")[0] is False
    assert decide("v = 72 km h⁻¹ = 20 m s⁻¹", "stem-cnv-1")[0] is True
    assert decide("T = 25 °C = 298 K", "stem-cnv-1")[0] is True
    assert decide("T = 25 °C = 398 K", "stem-cnv-1")[0] is False


def test_r6_comparisons_are_exact():
    assert decide("The amount of Al is 0.25 mol < 0.30 mol.", "stem-cmp-1", profile="chemistry")[0] is True
    assert decide("The amount of Al is 0.30 mol < 0.30 mol.", "stem-cmp-1", profile="chemistry")[0] is False


def test_r7_substitution_matches_as_written_or_in_si():
    req = "A car travels 2.5 km in 100 s."
    assert decide("Given d = 2.5 km.\nv = d/t = 2500/100 = 25 m s⁻¹", "stem-sub-1", request=req)[0] is True
    assert decide("Given d = 2.5 km.\nv = d/t = 2.5/100 = 0.025 km s⁻¹", "stem-sub-1", request=req)[0] is True
    assert decide("Given d = 2.5 km.\nv = d/t = 3500/100 = 35 m s⁻¹", "stem-sub-1", request=req)[0] is False


def test_r8_restatement():
    text = "I = V/R = 12/2.4 = 5.0 A. The current is therefore 5.0 A."
    assert decide(text, "stem-res-1")[0] is True
    text = "I = V/R = 12/2.4 = 5.0 A. The current is therefore 0.50 A."
    assert decide(text, "stem-res-1")[0] is False


def test_r10_roots():
    assert decide("x² = 2 ⇒ x = 1.41 or x = −1.41", "stem-sol-1", profile="mathematics_aa")[0] is True
    assert decide("x² = 2 ⇒ x = 1.47 or x = −1.41", "stem-sol-1", profile="mathematics_aa")[0] is False
    assert decide("x² − 5x + 6 = 0 ⇒ x = 2 or x = 3", "stem-sol-1", profile="mathematics_aa")[0] is True
