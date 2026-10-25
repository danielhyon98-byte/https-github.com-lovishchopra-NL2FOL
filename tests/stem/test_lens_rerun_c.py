"""Regression tests of the STEM findings of the rerun lens review (soundness, precision and parser safety): each failed
before its fix and passes after it, with a control that the fix does not turn correct work into an error.
"""
from __future__ import annotations

import random
import time

import pytest

from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.stem.hub_hooks import STEM_HOOKS
from epinoic_logic.stem.layout import EMPHASIS_RE, emphasis_spans, plain_line

from .argdiag_hub import decided, plan

MAA, MAI = "mathematics_aa", "mathematics_ai"


def _verdicts(text, request=None, profile="physics") -> dict:
    return {cid: ok for cid, (_pc, ok) in decided(text, request, profile).items()}


def _codes(text, request=None, profile="physics") -> list[str]:
    doc, p = plan(text, request, profile)
    return [f.code for f in list(doc.findings) + list(p.findings)]


# ------------------------------------------------------------------ stem-soundness-1: a prefix or % on one side only


@pytest.mark.parametrize("text,profile", [
    ("Total mass = 3 × 2.0 kg = 6.0 g.", "biology"), ("Efficiency = 300/400 = 0.75 %.", "physics"), ("25 % of 80: 80 × 25 % = 2000.", MAI),
    ("P = 2.0 kW × 3.0 = 6.0 W", "physics"), ("d = 2.0 km × 3 = 6.0 m", "physics"), ("I = 2 × 1.5 mA = 3.0 A", "physics"), ("m = 4.0 g / 2 = 2.0 kg", "physics"),
])
def test_ss1_a_value_out_by_a_prefix_or_per_cent_fails_its_unit_companion(text, profile):
    v = _verdicts(text, None, profile)
    assert v.get("stem-eq-1u") is False, (text, v)


def test_ss1_control_the_same_working_with_its_units_right_holds():
    assert set(_verdicts("Total mass = 3 × 2.0 kg = 6.0 kg.", None, "biology").values()) == {True}
    assert set(_verdicts("Efficiency = 300/400 = 0.75 = 75 %.").values()) == {True}


# ------------------------------------------------------------------ stem-soundness-2 and 3: matching tolerances, coefficients


@pytest.mark.parametrize("text,request_text,profile,check", [
    ("Given: m = 20 kg and a = 3.0 m s⁻².\nF = ma = 30 × 3.0 = 90 N", None, "physics", "stem-sub-1"),
    ("Given: m = 3 kg and a = 2 m s⁻².\nF = ma = 4 × 2 = 8 N", None, "physics", "stem-sub-1"),
    ("Let x = 3.\nThen y = 2x + 1 = 2 × 4 + 1 = 9", None, MAA, "stem-sub-1"),
    ("I = V/R = 12/2.4 = 5 A. The current is therefore 6 A.", None, "physics", "stem-res-1"),
    ("Given: m = 3 kg.\nW = mg = 3 × 9.81 = 29.4 N.", "A 2 kg mass hangs at rest. Take g = 9.81 m s⁻².", "physics", "stem-giv-1"),
    ("Let x = 4.\nThen y = 4x + 1 = 4 × 9 + 1 = 37", None, MAA, "stem-sub-1"),        # ss3: the 4 is the law's own coefficient
])
def test_ss2_ss3_the_next_value_in_the_last_digit_or_a_coefficient_is_no_match(text, request_text, profile, check):
    assert _verdicts(text, request_text, profile)[check] is False


def test_ss2_ss3_controls_the_bound_value_substituted_holds():
    assert set(_verdicts("Given: m = 20 kg and a = 3.0 m s⁻².\nF = ma = 20 × 3.0 = 60 N").values()) == {True}
    assert set(_verdicts("Let x = 4.\nThen y = 4x + 1 = 4 × 4 + 1 = 17", None, MAA).values()) == {True}


# ------------------------------------------------------------------ stem-precision-2: a value in the sibling unit


@pytest.mark.parametrize("text", [
    "V = 25.0 cm³ and c = 0.100 mol dm⁻³, so n = cV = 0.100 × 0.0250 = 2.50 × 10⁻³ mol",
    "V = 25.0 cm³ and c = 0.100 mol dm⁻³, so n = cV = 0.100 × 25.0 / 1000 = 2.50 × 10⁻³ mol",
    "V = 250 cm³ and n = 0.0428 mol, so c = n/V = 0.0428/0.250 = 0.171 mol dm⁻³",
])
def test_sp2_a_volume_substituted_in_the_unit_of_the_concentration_holds(text):
    assert set(_verdicts(text, None, "chemistry").values()) == {True}


def test_sp2_control_a_wrong_volume_still_fails():
    assert _verdicts("V = 25.0 cm³ and c = 0.100 mol dm⁻³, so n = cV = 0.100 × 0.0350 = 3.50 × 10⁻³ mol", None, "chemistry")["stem-sub-1"] is False


# ------------------------------------------------------------------ stem-soundness-4: the Computer Science AND dot


@pytest.mark.parametrize("text,holds", [("A.B + A.C = A.(B + C)", True), ("A.B = A.B", True), ("(A + B).C = A.C + B.C", True),
                                        ("A.B = B.C", False), ("X.Y = Y.Z", False)])
def test_ss4_the_and_dot_is_read_as_and(text, holds):
    v = _verdicts(text, None, "computer_science")
    assert list(v) == ["stem-bool-1"] and v["stem-bool-1"] is holds


def test_ss4_control_a_full_stop_stays_a_full_stop():
    doc, _p = plan("The answer is B. Then x = 2.", None, "computer_science")
    assert [r.kind for r in doc.relations] == ["binding"]


# ------------------------------------------------------------------ stem-soundness-5 and 11: systems, roots on the next line


def test_ss5_a_stated_solution_is_checked_against_the_whole_system():
    assert _verdicts("2x + y = 7 and x − y = 2, so x = 5 and y = 3", None, MAA) == {"stem-sys-1": False}
    assert _verdicts("2x + y = 7 and x − y = 2, so x = 3 and y = 1", None, MAA) == {"stem-sys-1": True}


@pytest.mark.parametrize("text", ["x² = 3x\nDividing by x, x = 3", "x² − 4 = 0\nx = 2"])
def test_ss11_a_root_lost_on_the_next_line_fails_as_after_an_arrow(text):
    assert _verdicts(text, None, MAA) == {"stem-sol-1": False}


def test_ss11_control_the_full_root_set_on_the_next_line_holds():
    assert _verdicts("x² − 4 = 0\nx = 2 or x = −2", None, MAA) == {"stem-sol-1": True}


# ------------------------------------------------------------------ already fixed before this round: ss10, sp4 (evidence kept)


def test_ss10_plus_minus_roots_hold_and_a_wrong_pair_fails():
    request = "Solve x^2 = 2, giving your answers to 3 s.f."
    assert set(_verdicts("x² = 2 ⇒ x = ±1.41", request, MAA).values()) == {True}
    assert _verdicts("x² = 2 ⇒ x = ±1.51", request, MAA)["stem-sol-1"] is False


@pytest.mark.parametrize("text,profile", [("N = 2 × 1234 = 2470 (3 s.f.)", MAA), ("The area is 37 × 41 = 1517 = 1520 (3 s.f.)", MAA),
                                          ("Population = 250 × 7 = 1750 = 1800 (2 s.f.)", MAI), ("Mean = (412 + 398) / 2 = 405 = 410 (2 s.f.)", "biology"),
                                          ("q = 149 = 100 (1 s.f.)", "physics")])
def test_sp4_a_rounding_stated_beside_integer_working_holds(text, profile):
    assert set(_verdicts(text, None, profile).values()) == {True}


def test_sp4_control_a_wrong_rounding_fails():
    assert _verdicts("N = 2 × 1234 = 2480 (3 s.f.)", None, MAA)["stem-eq-1"] is False


# ------------------------------------------------------------------ stem-soundness-6: approximation words


@pytest.mark.parametrize("text,profile", [("The speed increases linearly, so v = 2.0 × 3.0 = 6.3 m/s", "physics"),
                                          ("Mix thoroughly; then n = 2.0 × 3.0 = 6.3 mol", "chemistry"),
                                          ("The ball moves for about 3 s, and v = 2.0 × 3.0 = 6.3 m/s", "physics"),
                                          ("Around the bend, v = 2.0 × 3.0 = 6.3 m/s", "physics")])
def test_ss6_a_word_that_does_not_qualify_the_relation_gives_no_slack(text, profile):
    assert _verdicts(text, None, profile)["stem-eq-1"] is False


@pytest.mark.parametrize("text", ["v = 2.0 × 3.0 ≈ 6.3 m/s", "Approximately, v = 2.0 × 3.0 = 6.3 m/s", "We estimate that v = 2.0 × 3.0 = 6.3 m/s"])
def test_ss6_control_an_approximation_the_relation_carries_keeps_its_slack(text):
    assert _verdicts(text)["stem-eq-1"] is True


# ------------------------------------------------------------------ stem-soundness-8 and 9: angles


@pytest.mark.parametrize("text,holds", [("θ = 30° = 0.524 rad.", True), ("2 rad = 115° (to 3 s.f.).", True), ("180° = π rad.", True),
                                        ("x = 60° = π/3 rad", True), ("θ = 30° = 0.6 rad.", False), ("2 rad = 125°.", False), ("x = 60° = π/4 rad", False)])
def test_ss8_degrees_against_radians_convert_with_pi(text, holds):
    assert _verdicts(text)["stem-eq-1"] is holds


def test_ss9_an_angle_the_request_writes_in_degrees_is_read_in_degrees():
    request = "Calculate the horizontal component of a 10 N force at 60° to the horizontal."
    assert _verdicts("The horizontal component is F cos θ = 10 cos 60 = −9.5 N.", request)["stem-eq-1"] is False
    assert _verdicts("The horizontal component is F cos θ = 10 cos 60 = 5.0 N.", request)["stem-eq-1"] is True


def test_ss9_control_an_angle_written_in_no_unit_keeps_both_readings():
    assert _verdicts("x = 0.10 cos(2.0) = −0.042 m")["stem-eq-1"] is True   # an argument in radians (ωt), as the physics of SHM reads it


# ------------------------------------------------------------------ stem-soundness-12: forms that were dropped silently


@pytest.mark.parametrize("text,request_text,holds", [
    ("Factorising, x² + 5x + 6 = (x + 2)(x + 4).", "Factorise x^2 + 5x + 6.", False),
    ("Factorising, x² + 5x + 6 = (x + 2)(x + 3).", "Factorise x^2 + 5x + 6.", True),
    ("(a + b)² = a² + b²", "Expand (a + b)^2.", False),
    ("(a + b)² = a² + 2ab + b²", "Expand (a + b)^2.", True),
])
def test_ss12_a_named_identity_is_checked_for_every_value(text, request_text, holds):
    assert _verdicts(text, request_text, MAA) == {"stem-alg-1": holds}


def test_ss12_control_an_equation_to_solve_is_no_identity():
    assert _verdicts("2x + 3 = x + 7", "Solve 2x + 3 = x + 7.", MAA) == {}
    assert _verdicts("2x + 3 = x + 7, so x = 4", "Solve 2x + 3 = x + 7.", MAA) == {"stem-alg-1": True}   # the step, not an identity


def test_ss12_bits_bytes_and_binomial_coefficients_are_read():
    assert _verdicts("32 bits = 8 bytes", None, "computer_science") == {"stem-cnv-1": False}
    assert _verdicts("32 bits = 4 bytes", None, "computer_science") == {"stem-cnv-1": True}
    assert _verdicts("⁵C₂ = 20 ways.", None, MAI) == {"stem-eq-1": False}
    assert _verdicts("⁵C₂ = 10 ways.", None, MAI) == {"stem-eq-1": True}


def test_ss12_inequalities_and_nuclear_equations_are_named_not_dropped():
    assert _codes("|x − 1| < 3, so −3 < x − 1 < 3, giving −2 < x < 5.", "Solve |x - 1| < 3.", MAA).count("ST-UNDEC-001") >= 2
    assert "ST-UNDEC-001" in _codes("²³⁸₉₂U → ²³⁴₉₁Th + ⁴₂He")
    assert "ST-UNDEC-001" not in _codes("For 0 < t < 2, both factors are positive, so v > 0.", None, MAA)


# ------------------------------------------------------------------ stem-precision-11: a line of working is answer proper


@pytest.mark.parametrize("line", ["21 131.40 − 18 000.00 = 3 131.40", "1 000 000 × 0.05 = 50 000", "21'131.40 − 18'000 = 3131.40"])
def test_sp11_a_line_of_grouped_working_counts_as_one_maths_word(line):
    assert STEM_HOOKS.word_count_view(line, MAI).split() == ["Xmath"]


def test_sp11_truncated_numerals_are_read_and_checked():
    assert _verdicts("3.14159… × 2 = 6.28318…", None, MAA) == {"stem-eq-1": True}
    assert _verdicts("3.14159... × 2 = 6.38318...", None, MAA) == {"stem-eq-1": False}


# ------------------------------------------------------------------ parser safety: bounded work on adversarial input


def test_ps1_an_overlong_superscript_run_is_bounded_and_the_rest_is_still_checked():
    text = "(a) The speed is v = d / t = 120 m / 4.0 s = 50 m s⁻¹.\n\nNote: the scale factor is k = 2" + "²" * 4301 + ".\n"
    doc, p = plan(text, "A car travels 120 m in 4.0 s. Calculate its speed.")
    assert not [f for f in doc.findings if f.code == "ST-INTERNAL-001"]
    assert _verdicts(text, "A car travels 120 m in 4.0 s. Calculate its speed.")["stem-eq-1"] is False


def test_ps5_the_emphasis_scan_is_the_regex_s_reading_in_linear_time():
    rng = random.Random(7)
    pieces = ["*", "**", "_", "__", "a", "b", " ", "x1", ".", "\n", "é", "-"]
    for _ in range(20000):
        s = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 14)))
        assert emphasis_spans(s) == [(m.start(), m.end(), m.start(2), m.end(2)) for m in EMPHASIS_RE.finditer(s)], s
    assert plain_line("**What the question wants:** the value") == ("What the question wants: the value", plain_line("**What the question wants:** the value")[1])
    t = time.perf_counter()
    plain_line("**a " * 100_000)
    assert time.perf_counter() - t < 5.0


def test_ps5_the_same_linear_reading_gives_the_markdown_helpers_emphasis_with_backticks():
    # the markdown helper's pattern adds the backtick; adapters/markdown.py (another owner's file) can strip emphasis with
    # this reading instead of its quadratic EMPHASIS_RE.sub (handed over to the integration step)
    from epinoic_logic.adapters.markdown import EMPHASIS_RE as MD_EMPHASIS_RE
    markers = ("**", "__", "*", "_", "`")

    def stripped(s: str) -> str:
        out, pos = [], 0
        for start, end, b0, b1 in emphasis_spans(s, markers):
            out += [s[pos:start], s[b0:b1]]
            pos = end
        return "".join(out) + s[pos:]

    rng = random.Random(11)
    pieces = ["*", "**", "_", "__", "`", "``", "a", "b", " ", "x1", ".", "\n", "é", "-"]
    for _ in range(20000):
        s = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 14)))
        assert emphasis_spans(s, markers) == [(m.start(), m.end(), m.start(2), m.end(2)) for m in MD_EMPHASIS_RE.finditer(s)], s
        assert stripped(s) == MD_EMPHASIS_RE.sub(r"\2", s), s
    t = time.perf_counter()
    stripped("`a " * 100_000)
    assert time.perf_counter() - t < 5.0


@pytest.mark.parametrize("text", ["**a " * 50_000, "5 plus " * 28_571 + "5 making 10", "- x = 1\n" * 25_000])
def test_ps5_ps10_ps11_the_front_end_stays_linear_on_adversarial_answers(text):
    clear_document_cache()
    t = time.perf_counter()
    build_document(text, None, "physics")
    assert time.perf_counter() - t < 15.0   # the quadratic scans took minutes at this size
