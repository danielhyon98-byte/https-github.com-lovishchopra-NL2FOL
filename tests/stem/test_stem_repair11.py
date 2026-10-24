"""STEM repair 11: the eleventh independent test of the STEM completion found seven problems. Six are in the STEM front end; each is fixed
at its cause, for its whole class, and every new reading has a clean control (correct working is never flagged):

* rules ``exact-rounding`` and ``result-rounding`` (high): exact mode (every operand and the stated value exact, '=') set h = 0 and τ = 0,
  and a rounding the line states for its own result was read for restatements only, so correct working whose operands are whole and whose
  result is a rounded quotient ('(92 − 18) ÷ 18 × 100 = 411%', '1,000 ÷ 3 = 333', '= 34% to 2 s.f.') failed (INT-SUBJ-001). In exact mode
  a stated value of two or more significant figures closing rational written arithmetic has half a unit in its last written digit, every
  trailing zero counting (a whole computed value is still stated exactly, '17 × 23 = 392' fails), and a stated rounding of the result gives
  its half-width; a one-figure value shows no rounding ('7/3 = 2' still fails);
* rule ``given-data`` (high): a Given one unit off in its last digit held (R7's inclusive band |w − b| ≤ h(b) + h(w)). The request's
  values, and a Given that restates them, are data taken as written: a value matches one only when one of the two is the other rounded to
  its own last written digit, |w − b| ≤ max(h(w), h(b)), for a Given and for a substitution alike ('0.49 Ω' for 0.50 ohm fails, '0.5 Ω' and
  '9.81' for 9.8 hold); the answer's own computed values keep R7's band;
* rules ``part-condition`` and ``root-statement`` (medium): a letter bound in another part's question ('(a) … when t = 1') was given
  everywhere, so part (b)'s '6t − 3t² = 0' had no unknown: a wrong factorisation or wrong roots had no check. A letter's values stated in a
  part are given in that part only, and a root statement leaves the equation it solves as the relation the next line steps from;
* rules ``function-value``, ``inequality-solution`` and ``derivative`` (medium): a function's value stated in prose ('v(1) = 4'), a wrong
  restatement of an inequality's solution ('n > 13.28…') and a wrong derivative were unchecked (the derivative only ST-UNDEC-001). Each is
  decided now: the value against the function the request (warning) or the answer (error) defines, the bound against the relation before
  it solved exactly (its cut values read as cut or rounded digits), the derivative against the one the STEM pack forms by the power rule;
* rules ``same-shape`` and ``unbound-substitution`` (medium): a wrong given substituted where no symbol is bound to it ('$4500(1.036)^{11} =
  6640.03$', '2.4 Ω + 0.40 Ω' for r) had no check. A numeral in the place where the answer's other evaluation of the same expression writes
  the request's value, and a value substituted for a symbol the answer gives no value but substitutes the request's value for elsewhere,
  are set against that value (warnings: each is a reading);
* rule ``prose-base`` (low): a base phrase opening the clause ('In binary, 1000 is 1111101100.') was not read.

The seventh (the knowledge pack's size) is the overseer's: tests/overseer/test_stem_repair11.py.
"""
from __future__ import annotations

import pytest

from .test_stem_repair5 import SPEC, after, clean, decide, failing, holds, new, replaced, task, warnings

BI_D = "which makes ATP. [1 spare]"
ES_W = "Water temperature was between 17 °C and 18 °C at every site, so it does not explain the difference."
CS_END = "Next step: trace"
MA_LAST = "    Distance travelled = 8 m  A1"
MA_PART_B = "    6t − 3t² = 0\n"
MI_11 = "$4000(1.036)^{11} = 5902.25$"
PH_A = "(a) [2]\n"
PH_RR = "R + r = 2.4 Ω + 0.50 Ω = 2.9 Ω"
PH_C = "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
CH_END = "so I cannot give one yet."


def _alone(text: str, profile: str, request=None):
    return decide(text, request, profile)


def _rule(checks, rule: str) -> list:
    return [c for c in checks if f"rule {rule}" in c[3]]


# ============================================================================================ rules exact-rounding and result-rounding
@pytest.mark.parametrize("text,profile", [
    ("(92 − 18) ÷ 18 × 100 = 411%", "biology"), ("700 ÷ 3 = 233", "biology"), ("2 ÷ 3 × 100 = 67%", "biology"),
    ("1,000 ÷ 3 = 333 items", "computer_science"), ("29 ÷ 3 = 10", "biology"), ("1 ÷ 3 × 100 = 33%", "biology"),
    ("(40 − 18) ÷ 18 × 100 = 122%", "biology"), ("(34 − 9) ÷ 34 × 100 = 74%", "ess"), ("7/3 = 2.33", "mathematics_aa"),
])
def test_a_rounded_quotient_of_whole_numbers_holds(text, profile):
    """The tester's correct working and the class: before, exact mode gave h = 0 and every such line failed as an error."""
    checks, findings = _alone(text, profile)
    assert checks and not failing(checks) and not warnings(findings), (checks, findings)


@pytest.mark.parametrize("text,profile", [
    ("(92 − 61) ÷ 92 × 100 = 34% to 2 s.f.", "biology"), ("(92 − 61) ÷ 92 × 100 = 34% (to the nearest whole number).", "biology"),
    ("1000 ÷ 3 = 330 to 2 s.f.", "biology"), ("To 2 s.f., 1000 ÷ 3 = 330.", "biology"), ("(92 − 61) ÷ 92 × 100 = 30% to 1 s.f.", "biology"),
])
def test_a_rounding_stated_for_the_line_s_own_result_gives_its_half_width(text, profile):
    checks, findings = _alone(text, profile)
    eq = [c for c in checks if c[0] == "eq" and c[3].startswith("the written arithmetic")]
    assert len(eq) == 1 and holds(eq[0]) and "(rule result-rounding)" in eq[0][3] and not failing(checks), (checks, findings)


def test_a_rounding_that_closes_an_earlier_restatement_is_no_rounding_of_the_next_chain():
    """The eleventh tester's control: '…, so 5902 euros to the nearest euro, and $4000(1.036)^{12} = 6114.73$' had 6114.73 read as rounded
    to the nearest euro (a false INT-SUBJ-004 by rule rounded-digits, and the arithmetic's band widened to half a euro): a rounding before
    a chain is its result's only when it opens the chain's clause, with no number before it."""
    clean("mai-t13", replaced("mai-t13", MI_11, MI_11 + ", so 5902 euros to the nearest euro,"))
    checks, _f = new("mai-t13", replaced("mai-t13", MI_11, MI_11 + ", so 5903 euros to the nearest euro,"))
    assert [(c[0], c[2]) for c in failing(checks)] == [("res", "error")] and "'5903'" in failing(checks)[0][3], checks
    checks, _f = _alone("So 5903 euros to the nearest euro, and 4000 × 1.036 = 4144.00.", "biology")
    assert checks and not failing(checks) and not _rule(checks, "result-rounding") and not _rule(checks, "rounded-digits"), checks


@pytest.mark.parametrize("text,profile", [
    ("1000 ÷ 2 = 501", "biology"), ("17 × 23 = 392", "biology"), ("(92 − 18) ÷ 18 × 100 = 412%", "biology"), ("1000 ÷ 3 = 330", "biology"),
    ("700 ÷ 3 = 234", "biology"), ("(92 − 61) ÷ 92 × 100 = 40% to 1 s.f.", "biology"), ("(92 − 61) ÷ 92 × 100 = 33% to 2 s.f.", "biology"),
    ("7/3 = 2", "mathematics_aa"), ("5/2 = 2", "mathematics_aa"), ("√8 = 3", "mathematics_aa"), ("23 div 4 = 6", "computer_science"),
    ("1 ÷ 3 = 0", "biology"), ("5 ÷ 2 = 3", "biology"),
])
def test_exact_work_still_fails_a_wrong_value(text, profile):
    """A whole computed value must be stated exactly; a value that is not whole may be stated to the last written digit only (every trailing
    zero counting: '330' is no 2-s.f. value unless the line says so), and a one-figure value shows no rounding at all."""
    checks, _f = _alone(text, profile)
    bad = failing(checks)
    assert bad and all(c[2] == "error" for c in bad), checks


@pytest.mark.parametrize("line,ok", [
    ("From 10 °C to 35 °C the uptake rises by (92 − 18) ÷ 18 × 100 = 411%.", True),
    ("From 10 °C to 35 °C the uptake rises by (92 − 18) ÷ 18 × 100 = 311%.", False),
    ("From 35 °C to 40 °C the uptake falls by (92 − 61) ÷ 92 × 100 = 34% to 2 s.f.", True),
    ("From 10 °C to 20 °C the uptake rises by (40 − 18) ÷ 18 × 100 = 122%.", True),
])
def test_the_tester_s_biology_lines_in_the_recorded_answer(line, ok):
    text = after("bi-t13", BI_D, line)
    if ok:
        clean("bi-t13", text)
    else:
        checks, _f = new("bi-t13", text)
        assert [c[2] for c in failing(checks)] == ["error"], checks


def test_the_tester_s_ess_and_computer_science_lines_in_the_recorded_answers():
    clean("ess-t13", after("ess-t13", ES_W, "From A to B the nymph count falls by (34 − 9) ÷ 34 × 100 = 74%."))
    clean("cs-t13", replaced("cs-t13", "That is still far fewer than 1,000.", "That is still far fewer than 1,000.\nOn average a linear search "
                             "compares 1,000 ÷ 2 = 500 items, and 1,000 ÷ 3 = 333 items is a third of the list."))


# ============================================================================================ rule given-data
@pytest.mark.parametrize("tid,anchor,line", [
    ("ph-t13", PH_A, "Given: ε = 12 V, r = 0.49 Ω, R₁ = 4.0 Ω, R₂ = 6.0 Ω.\n"), ("ph-t13", PH_A, "Given: r = 0.51 Ω.\n"),
    ("ph-t13", PH_A, "Given: ε = 11 V.\n"), ("ph-t13", PH_A, "Given: ε = 13 V.\n"), ("ph-t13", PH_A, "Given: R₁ = 4.1 Ω.\n"),
    ("mai-t13", "**Part (a) — find — 3 marks**", "Given: P = 4000 euros and r = 3.5%.\n\n"),
    ("mai-t13", "**Part (a) — find — 3 marks**", "Given: P = 4000 euros and r = 3.7%.\n\n"),
])
def test_a_given_one_unit_off_the_request_s_data_fails(tid, anchor, line):
    """Before, |w − b| ≤ h(b) + h(w) held each (0.49 against 0.50: 0.01 ≤ 0.005 + 0.005)."""
    checks, _f = new(tid, replaced(tid, anchor, anchor + line if anchor == PH_A else line + anchor))
    giv = [c for c in failing(checks) if c[0] == "giv"]
    assert giv and all(c[2] == "warning" and "(rule given-data)" in c[3] for c in giv), checks


@pytest.mark.parametrize("tid,anchor,line", [
    ("ph-t13", PH_A, "Given: ε = 12 V, r = 0.50 Ω, R₁ = 4.0 Ω, R₂ = 6.0 Ω.\n"), ("ph-t13", PH_A, "Given: ε = 12.0 V, r = 0.5 Ω, R₁ = 4 Ω, R₂ = 6.00 Ω.\n"),
    ("ph-t13", PH_A, "Given: r = 500 mΩ.\n"), ("ph-t13", PH_A, "Given: ε = 12 V, r = 0.500 Ω.\n"),
    ("mai-t13", "**Part (a) — find — 3 marks**", "Given: P = 4000 euros and r = 3.6%.\n\n"),
])
def test_a_given_that_is_the_data_or_a_rounding_of_it_holds(tid, anchor, line):
    clean(tid, replaced(tid, anchor, anchor + line if anchor == PH_A else line + anchor))


@pytest.mark.parametrize("text,req,ok", [
    ("I = ε/(R + r) = 12 V / (2.4 Ω + 0.49 Ω) = 4.2 A", "A cell has ε = 12 V and r = 0.50 Ω; R = 2.4 Ω. Find I.", False),
    ("I = ε/(R + r) = 12 V / (2.4 Ω + 0.5 Ω) = 4.1 A", "A cell has ε = 12 V and r = 0.50 Ω; R = 2.4 Ω. Find I.", True),
    ("I = ε/(R + r) = 12 V / (2.4 Ω + 0.50 Ω) = 4.1 A", "A cell has ε = 12 V and r = 0.50 Ω; R = 2.4 Ω. Find I.", True),
    ("W = mg = 2.1 kg × 9.81 m s⁻² = 20.6 N", "A mass m = 2.0 kg; take g = 9.81 m s⁻². Find W.", False),
    ("W = mg = 2 kg × 9.81 m s⁻² = 19.6 N", "A mass m = 2.0 kg; take g = 9.81 m s⁻². Find W.", True),
    ("W = mg = 2.0 kg × 9.8 m s⁻² = 19.6 N", "A mass m = 2.0 kg; take g = 9.81 m s⁻². Find W.", True),
    ("W = mg = 2.0 kg × 9.81 m s⁻² = 19.6 N", "A mass m = 2.0 kg; take g = 9.8 m s⁻². Find W.", True),
])
def test_a_value_substituted_for_the_request_s_data_is_set_against_it_as_written(text, req, ok):
    checks, _f = _alone(text, "physics", req)
    sub = [c for c in checks if c[0] == "sub"]
    assert len(sub) == 1 and holds(sub[0]) is ok and "(rule given-data)" in sub[0][3], checks
    if not ok:
        assert sub[0][2] == "error"


@pytest.mark.parametrize("text,ok", [
    ("Given: r = 0.50 Ω, R = 2.4 Ω.\nR + r = 2.4 Ω + 0.49 Ω = 2.89 Ω", False), ("Given: r = 0.50 Ω, R = 2.4 Ω.\nR + r = 2.4 Ω + 0.5 Ω = 2.9 Ω", True),
    ("Given: I = 4.1 A, r = 0.50 Ω.\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", True),
    ("I = 12 V / 2.9 Ω = 4.1 A\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", True),
])
def test_a_given_the_answer_restates_is_data_and_a_computed_value_keeps_its_band(text, ok):
    """A Given the answer writes restates the data; a value it computes ('I = 4.1 A', carried as 4.14 A) keeps R7's band."""
    checks, _f = _alone(text, "physics")
    assert bool(checks) and (not failing(checks)) is ok, checks


# ============================================================================================ rules part-condition and root-statement
@pytest.mark.parametrize("old,new_text,kinds", [
    (MA_PART_B, "    6t − 3t² = 0\n    so t(6 − 2t) = 0\n", ["alg", "alg"]),
    ("    3t(2 − t) = 0  M1", "    3t(2 + t) = 0  M1", ["alg", "sol"]),
    ("    t = 0 or t = 2  A1", "    t = 0 or t = 3  A1", ["sol"]),
    ("    3t(2 − t) = 0  M1", "    3t(3 − t) = 0  M1", ["alg", "sol"]),
    ("keeps t = 0.", "keeps t = 1.", ["sol"]),
])
def test_a_wrong_factorisation_or_wrong_roots_in_another_part_fail(old, new_text, kinds):
    """maa-t13: '(a) … when t = 1' had bound t for the whole answer, so part (b)'s equation had no unknown and nothing in it was checked."""
    checks, _f = new("maa-t13", replaced("maa-t13", old, new_text))
    assert sorted(c[0] for c in failing(checks)) == sorted(kinds) and all(c[2] == "error" for c in failing(checks)), checks


def test_the_recorded_part_b_and_a_right_factorisation_are_clean():
    """The recorded part (b) is checked now: the factorisation '3t(2 − t) = 0' as a step from '6t − 3t² = 0', and the roots 't = 0 or t =
    2' against it; both hold, and a right factorisation written another way adds nothing that fails."""
    every, _f = task("maa-t13", SPEC["maa-t13"]["response_text"])
    assert not failing(every), failing(every)
    step = [c for c in every if c[0] == "alg" and "'3t(2 − t) = 0'" in c[3]]
    roots = [c for c in every if c[0] == "sol" and "'t = 0 or t = 2'" in c[3]]
    assert len(step) == 1 and len(roots) == 1, every
    # each names the readings it rests on: t is part (b)'s unknown although part (a)'s question gives it a value, and the step is from the
    # equation the root statement 'keeps t = 0' leaves as the relation the next line steps from
    assert "(rule part-condition)" in step[0][3] and "(rule root-statement)" in step[0][3], step
    assert "(rule part-condition)" in roots[0][3] and "part (a)" in roots[0][3], roots
    clean("maa-t13", replaced("maa-t13", MA_PART_B, "    6t − 3t² = 0\n    so t(6 − 3t) = 0\n"))


def test_rule_part_condition_reads_mathematics_only():
    """A science symbol is a quantity whose value a later part may use: a value in part (a)'s question stays given in part (b), and no
    check names the reading; in mathematics the same layout makes the letter part (b)'s unknown."""
    req = "A resistor in a circuit. (a) Calculate the current when R = 4.0 Ω and V = 12 V. (b) Calculate the power dissipated in the resistor."
    checks, findings = decide("(a) I = V/R = 12 V / 4.0 Ω = 3.0 A\n(b) P = I²R = (3.0 A)² × 4.0 Ω = 36 W", req, "physics")
    assert checks and not failing(checks) and not _rule(checks, "part-condition") and not warnings(findings), (checks, findings)
    reqm = "A particle moves with velocity v = 6t − 3t² m s⁻¹. (a) Find v when t = 1. (b) Find the values of t for which the particle is at rest."
    checks, findings = decide("(a) v = 6(1) − 3(1)² = 3\n(b) 6t − 3t² = 0\n3t(2 − t) = 0\nt = 0 or t = 2", reqm, "mathematics_aa")
    assert [c[0] for c in _rule(checks, "part-condition")] == ["alg", "sol"] and not failing(checks), checks


def test_a_step_or_roots_of_a_letter_no_other_part_gives_a_value_name_no_part_condition():
    """The reading is named only where it applies: with no request, nothing gives t a value in another part."""
    checks, _f = _alone("6t − 3t² = 0\n3t(2 − t) = 0\nt = 0 or t = 2", "mathematics_aa")
    assert checks and not failing(checks) and not any("(rule part-condition)" in c[3] for c in checks), checks


@pytest.mark.parametrize("text,ok", [
    ("6t − 3t² = 0\n3t(2 + t) = 0", False), ("6t − 3t² = 0\n3t(2 − t) = 0\nt = 0 or t = 3", False),
    ("x² − 5x + 6 = 0, so (x − 2)(x − 4) = 0", False), ("6t − 3t² = 0\n3t(2 − t) = 0\nt = 0 or t = 2", True),
])
def test_factorisations_and_roots_alone(text, ok):
    checks, _f = _alone(text, "mathematics_aa")
    assert checks and (not failing(checks)) is ok, checks


# ============================================================================================ rule function-value
@pytest.mark.parametrize("line,ok", [
    ("    The velocity at t = 1 is v(1) = 4 m s⁻¹.", False), ("    The velocity at t = 1 is v(1) = 3 m s⁻¹.", True),
    ("    At t = 2 the particle is at rest: v(2) = 1.", False), ("    At t = 2 the particle is at rest: v(2) = 0.", True),
])
def test_a_value_of_the_request_s_function_stated_in_prose_is_checked(line, ok):
    """maa-t13's request defines v(t) = 6t − 3t²: a value of it the prose states is set against it (a warning: that it is the request's
    function is a reading). Before, only a Given of it was read (rule given-function)."""
    checks, findings = new("maa-t13", after("maa-t13", "    a = 0 m s⁻²  A1", line))
    fv = _rule(checks, "function-value")
    assert len(fv) == 1 and holds(fv[0]) is ok and fv[0][2] == "warning" and not warnings(findings), (checks, findings)


@pytest.mark.parametrize("text,ok", [("v(t) = 6t − 3t²\nv(1) = 4", False), ("v(t) = 6t − 3t²\nv(1) = 3", True),
                                     ("Let f(x) = x² + 1.\nThen f(2) = 6.", False), ("Let f(x) = x² + 1.\nThen f(2) = 5.", True)])
def test_a_value_of_the_answer_s_own_function_is_checked_as_an_error(text, ok):
    checks, _f = _alone(text, "mathematics_aa")
    assert len(checks) == 1 and holds(checks[0]) is ok and checks[0][2] == "error", checks


def test_a_letter_applied_with_no_definition_is_no_function_value():
    assert _alone("The ball is at k(2) = 5.", "mathematics_aa")[0] == []


# ============================================================================================ rule inequality-solution
@pytest.mark.parametrize("old,new_text", [
    ("so $n > 11.28\\ldots$ (A1)", "so $n > 13.28\\ldots$ (A1)"), ("$12n > 135.36\\ldots$, so $n > 11.28\\ldots$ (3)", "$12n > 135.36\\ldots$, so $n > 12.28\\ldots$ (3)"),
    ("so $n > 11.28\\ldots$ (A1)", "so $n < 11.28\\ldots$ (A1)"),
])
def test_a_wrong_solution_of_an_inequality_fails(old, new_text):
    checks, _f = new("mai-t13", replaced("mai-t13", old, new_text))
    assert [c[2] for c in failing(checks)] == ["error"], checks


def test_the_recorded_solutions_of_the_inequality_hold():
    every, _f = task("mai-t13", SPEC["mai-t13"]["response_text"])
    solved = _rule(every, "inequality-solution")
    assert len(solved) == 2 and all(holds(c) for c in solved) and not failing(every), solved


@pytest.mark.parametrize("text,ok", [
    ("Given n = 11.46 earlier.\n3n − 2 > 31, so n > 11.", True), ("Given n = 11.46 earlier.\n3n − 2 > 31, so n > 12.", False),
    ("−2x > 6, so x < −3.", True), ("−2x > 6, so x > −3.", False), ("x = 5 is used later.\n4x + 1 = 21, so x = 5.", True),
    ("x = 5 is used later.\n4x + 1 = 21, so x = 6.", False),
])
def test_the_solution_of_a_linear_relation_is_checked_where_its_letter_has_a_value_elsewhere(text, ok):
    checks, _f = _alone(text, "mathematics_aa")
    assert checks and (not failing(checks)) is ok, checks


# ============================================================================================ rule derivative
@pytest.mark.parametrize("text,ok", [
    ("d/dx (x²) = 2x", True), ("d/dx (x²) = x", False), ("f(x) = x³, so f′(x) = 2x²", False), ("f(x) = x³ − 2x\nf′(x) = 3x² − 2", True),
    ("d/dx (x³) = 2x²", False), ("d/dx (x³ − 4x) = 3x² − 4", True), ("s = 4t³ − t\nd²s/dt² = 24t", True), ("s = 4t³ − t\nd²s/dt² = 12t", False),
    ("$y = x^2 + 3x$, so $\\frac{dy}{dx} = 2x + 3$", True), ("$y = x^2 + 3x$, so $\\frac{dy}{dx} = 2x + 2$", False),
    ("f(x) = x³\nf′(2) = 12", True), ("f(x) = x³\nf′(2) = 8", False),
])
def test_a_derivative_of_a_polynomial_is_set_against_the_power_rule(text, ok):
    """Before, every one of these was named ST-UNDEC-001 'a derivative' and never failed."""
    checks, findings = _alone(text, "mathematics_aa")
    der = [c for c in checks if "the derivative formed by the power rule" in c[3]]
    assert len(der) == 1 and holds(der[0]) is ok and der[0][2] == "error", checks
    assert not [f for f in findings if f[0] == "ST-UNDEC-001" and "derivative" in f[2]], findings


def test_the_tester_s_derivative_plant_fails_and_its_control_holds():
    checks, _f = new("maa-t13", after("maa-t13", MA_LAST, "    Also d/dt (3t²) = 3t."))
    assert [(c[0], c[2]) for c in failing(checks)] == [("alg", "error")], checks
    clean("maa-t13", after("maa-t13", MA_LAST, "    Also d/dt (3t²) = 6t."))


def test_a_derivative_of_the_request_s_function_fails_as_a_warning():
    """dv/dt of the request's v(t) = 6t − 3t²: that the letter differentiated is the request's function is a reading."""
    old = "a = dv/dt = 6 − 6t  M1\n    At t = 1: a = 6 − 6(1) = 0\n    a = 0 m s⁻²"
    checks, _f = new("maa-t13", replaced("maa-t13", old, "a = dv/dt = 6 − 3t  M1\n    At t = 1: a = 6 − 3(1) = 3\n    a = 3 m s⁻²"))
    der = [c for c in failing(checks) if "the derivative formed by the power rule" in c[3]]
    assert [(c[0], c[2]) for c in der] == [("alg", "warning")], checks


@pytest.mark.parametrize("text", ["d/dx (sin x) = cos x", "d/dx (ln x) = 1/x", "Also θ′(t) = 2"])
def test_a_derivative_outside_the_power_rule_stays_undecided(text):
    checks, findings = _alone(text, "mathematics_aa")
    assert checks == [] and [f[0] for f in findings] == ["ST-UNDEC-001"] and "a derivative" in findings[0][2], (checks, findings)


# ============================================================================================ rules same-shape and unbound-substitution
@pytest.mark.parametrize("new_text,value", [("$4500(1.036)^{11} = 6640.03$", "4500"), ("$4000(1.037)^{11} = 5928.94$", "1.037")])
def test_a_wrong_given_in_a_line_with_no_symbol_is_set_against_the_model_s_value(new_text, value):
    checks, _f = new("mai-t13", replaced("mai-t13", MI_11, new_text))
    giv = [c for c in failing(checks) if c[0] == "giv"]
    assert len(giv) == 1 and giv[0][2] == "warning" and "(rule same-shape)" in giv[0][3] and f"'{value}'" in giv[0][3], checks


@pytest.mark.parametrize("new_text", [
    "if Kai had invested 4500 euros instead, $4500(1.036)^{11} = 6640.03$",
    MI_11 + " Year by year: $4000(1.036)^5 = 4773.74$ and $4000(1.036)^6 = 4945.59$.",
])
def test_a_hypothesis_or_another_argument_of_the_model_is_no_wrong_given(new_text):
    clean("mai-t13", replaced("mai-t13", MI_11, new_text))


@pytest.mark.parametrize("old,new_text,value", [
    (PH_RR, "R + r = 2.4 Ω + 0.40 Ω = 2.8 Ω", "0.40 Ω"), (PH_RR, "R + r = 2.4 Ω + 0.49 Ω = 2.89 Ω", "0.49 Ω"),
    (PH_C, "V = 12 V − (4.14 A × 0.49 Ω) = 9.97 V", "0.49 Ω"),
])
def test_a_wrong_value_for_a_symbol_the_answer_substitutes_the_request_s_value_for_elsewhere_fails(old, new_text, value):
    checks, _f = new("ph-t13", replaced("ph-t13", old, new_text))
    giv = [c for c in failing(checks) if c[0] == "giv"]
    assert len(giv) == 1 and giv[0][2] == "warning" and "(rule unbound-substitution)" in giv[0][3] and f"'{value}'" in giv[0][3], checks


@pytest.mark.parametrize("tid,old,new_text", [
    ("ph-t13", PH_RR, "R + r = 2.4 Ω + 0.5 Ω = 2.9 Ω"),
    # a value the working derives without stating it (50.0 cm³ + 5.0 cm³) put for a symbol with no other value
    ("ch-t13", CH_END, CH_END + "\n\nn = cV\nc = 0.0050 mol ÷ 0.0550 dm³ = 0.091 mol dm⁻³"),
    # R stands for each of the request's two resistors in turn: no one value ties it
    ("ph-t13", "R = 2.4 Ω (the external resistance)\n", ""),
])
def test_a_rounding_a_derived_value_or_a_symbol_reused_is_no_wrong_given(tid, old, new_text):
    clean(tid, replaced(tid, old, new_text))


# ============================================================================================ rule prose-base
@pytest.mark.parametrize("line,ok", [("In binary, 1000 is 1111101100.", False), ("In binary, 1000 is 1111101000.", True)])
def test_a_base_phrase_opening_the_clause_is_read(line, ok):
    text = replaced("cs-t13", CS_END, line + "\n\n" + CS_END)
    if ok:
        clean("cs-t13", text)
    else:
        checks, _f = new("cs-t13", text)
        assert [(c[0], c[2]) for c in failing(checks)] == [("base", "error")], checks


@pytest.mark.parametrize("text,ok", [("In base 2, 13 is 1101.", True), ("In base 2, 13 is 1011.", False), ("In hexadecimal, 255 is 377.", False),
                                     ("In octal, 64 is 100.", True), ("Written in binary, 6 is 110.", True)])
def test_every_base_phrase_opening_a_clause(text, ok):
    checks, _f = _alone(text, "computer_science")
    assert len(checks) == 1 and holds(checks[0]) is ok, checks


@pytest.mark.parametrize("text", ["The loop runs 1000 times, so 1000 is the bound.", "In binary, the value is stored; 10 is 12."])
def test_no_base_phrase_no_base_check(text):
    assert _alone(text, "computer_science")[0] == []


# ============================================================================================ every recorded STEM answer
@pytest.mark.parametrize("tid", ["ph-t13", "ph-p7b", "maa-t13", "maa-p7b", "mai-t13", "bi-t13", "ess-t13", "ch-t13", "cs-t13"])
def test_no_recorded_answer_fails_any_check(tid):
    """The new readings add only checks that hold to the recorded answers, and none of them fails anything."""
    every, findings = task(tid, SPEC[tid]["response_text"])
    assert not failing(every), failing(every)
    assert not [f for f in findings if f[0] in ("ST-DIM-001", "ST-DIM-002", "INT-SUBJ-004")], findings
