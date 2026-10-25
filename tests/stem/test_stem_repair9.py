"""STEM repair 9: the ninth independent test of the STEM completion found classes the front end did not decide as the pack says. Each
is fixed at its cause in the STEM front end, for its whole class, and every new reading has a clean control (correct working is never
flagged):

* rule ``part-answer``: a correct line at the end of a part ('As a check, ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V.', 'The lost volts are
  4.14 A × 0.50 Ω = 2.07 V.') took the words of the part's question, so a later change stated from the part's result ('… rises, from
  9.9 V to 10.7 V') was set against that line's value: a false INT-SUBJ-004 (rule named-change). The part's answer is now the last value
  it computes that is no check and names no other quantity;
* rule ``named-result``: a wrong rearrangement evaluated consistently ('So r = (ε + V)/I = (12 V + 9.93 V)/4.14 A = 5.3 Ω.') gave a
  quantity the request names a contradicting value, and only its arithmetic was checked. The value a line gives a quantity the request
  names (by the prose before its value, its label, or a symbol the answer substituted the request's value for) is set against the
  request's value of it; the request names a quantity by the words after a preposition too ('a battery of emf 12 V' names the emf), and
  nothing by words ending in a preposition and an article ('the horizontal component of a 10 N force');
* rule ``given-function``: a Given of a function's value ('Given: v(1) = 4 m s⁻¹.') or of a function ('Given: v(t) = 6t − 2t².') had
  neither a check nor an ST code, while the pack said every Given has one or the other. It is set against the request's function, or
  named ST-UNDEC-003;
* rule ``row-terms``: a trial copied wrongly into the mean over a supplied row's trials ('(33.1 s + 43.0 s + 32.5 s) ÷ 3', the cell being
  34.0) was neither checked nor named. The terms of a sum over a row's repeats are set against the row's repeats;
* rule ``decay-law``: a decay over a stated number of half-lives written without a power of ½ ('5 half-lives, C = 1600 counts min⁻¹ ÷ 5 =
  320 counts min⁻¹') was named by nothing. The line's value is set against the decay law over that number;
* rule ``statistics``: a wrong median, in any form, was neither checked nor named. A median, a mode, a range or a mean stated for listed
  values or a supplied column is set against the statistic the STEM pack forms; any other statistic is named ST-UNDEC-001;
* rule ``rounded-digits``: a value restated at a stated rounding without being rounded ('60.4% to 2 s.f.') passed within the rounding's
  half-width. The place its digits are written to is set against the place the rounding names.
"""
from __future__ import annotations

import pytest

from epinoic_logic.stem import build_document, clear_document_cache

from .test_stem_repair5 import SPEC, decide, failing, holds, new, replaced, task, warnings

#: anchors in the recorded r7 answers
PH_B = "I = 12 V / 2.9 Ω = 4.1 A"
PH_C = "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
PH_E = "from 9.9 V to 10.7 V."
MA_END = "Marks shown are a provisional allocation."
CH_R = "Two reminders."
PB_D = "32 h is 4 half-lives, so C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹."
BI_END = "which makes ATP. [1 spare]"
ES_A = "= 60.4% decrease [1]"
CHECK_LINE = "As a check, ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V."


def _after(tid: str, anchor: str, line: str) -> str:
    return replaced(tid, anchor, anchor + "\n" + line)


def _rule(checks, rule: str) -> list:
    return [c for c in checks if f"rule {rule})" in c[3] or f"rule {rule};" in c[3]]


def _quoting(checks, text: str) -> list:
    return [c for c in checks if f"'{text}" in c[3].split(" [claims")[0]]


# ============================================================================================ rule part-answer
@pytest.mark.parametrize("line", [CHECK_LINE, "The lost volts are 4.14 A × 0.50 Ω = 2.07 V.", "So the emf is 9.93 V + 4.14 A × 0.50 Ω = 12.0 V.",
                                  "ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V",
                                  "The potential difference across the internal resistance is 4.14 A × 0.50 Ω = 2.07 V."])
def test_a_correct_line_at_the_end_of_a_part_is_no_answer_of_that_part(line):
    """The tester's controls (a false INT-SUBJ-004 on s3.3 and s5.4 before): the change part (e) states from part (c)'s result is still
    set against its 9.9 V, and holds; nothing new fails or warns."""
    text = _after("ph-t13", PH_C, line)
    checks, findings = new("ph-t13", text)
    assert not failing(checks) and not warnings(findings), (failing(checks), warnings(findings))
    every, _f = task("ph-t13", text)
    change = [c for c in _rule(every, "named-change") if "'9.9 V'" in c[3]]
    assert len(change) == 1 and holds(change[0]) and "[claims s3.2, s5.4]" in change[0][3], change  # part (c)'s line and the change


def test_a_change_stated_from_a_wrong_value_is_still_set_against_the_part_s_answer():
    """With the check line at the end of part (c), 'from 9.0 V' is set against part (c)'s 9.9 V, never the check's 12.0 V: it fails."""
    text = replaced("ph-t13", PH_C, PH_C + "\n" + CHECK_LINE).replace(PH_E, "from 9.0 V to 10.7 V.")
    every, _f = task("ph-t13", text)
    change = [c for c in _rule(every, "named-change") if "'9.0 V'" in c[3]]
    assert len(change) == 1 and change[0][1] == "COUNTEREXAMPLE" and change[0][2] == "warning", change
    assert "[claims s3.2, s5.4]" in change[0][3], change  # set against part (c)'s line, never the check line


def test_a_check_line_at_the_end_of_part_b_leaves_the_changed_current_its_substitution():
    """Before, the check line took part (b)'s question words, so the change 'from 4.1 A to 2.7 A' was not recorded and the substitution
    of 2.7 A in part (e) failed against 4.1 A (a false INT-SUBJ-001)."""
    text = replaced("ph-t13", PH_B, PH_B + "\nAs a check, 4.1 A × 2.9 Ω = 11.9 V, close to the emf.")
    text = text.replace(PH_E, PH_E + "\nWith the resistor removed, V = 12 V − 2.7 A × 0.50 Ω = 10.65 V.")
    checks, findings = new("ph-t13", text)
    assert not failing(checks) and not warnings(findings), (failing(checks), warnings(findings))
    sub = [c for c in _quoting(checks, "V = 12 V − 2.7 A × 0.50 Ω") if c[0] == "sub"]
    assert len(sub) == 1 and holds(sub[0]) and "(rule changed-value)" in sub[0][3], checks


# ============================================================================================ rule named-result
@pytest.mark.parametrize("line, how", [
    ("So r = (ε + V)/I = (12 V + 9.93 V)/4.14 A = 5.3 Ω.", "by the symbol r, for which the answer substituted the request's value"),
    ("r = (12 V + 9.93 V)/4.14 A = 5.3 Ω", "by the symbol r, for which the answer substituted the request's value"),
    ("So the internal resistance is (12 V + 9.93 V)/4.14 A = 5.3 Ω.", "by its words"),
    ("Internal resistance: r = (12 V + 9.93 V)/4.14 A = 5.3 Ω", "by its label"),
    ("So r = 5.3 Ω.", "by the symbol r, for which the answer substituted the request's value"),
])
def test_a_value_a_line_gives_a_quantity_the_request_names_is_set_against_the_request(line, how):
    """The tester's three plants of a wrong rearrangement evaluated (u9-eq-ph-r-eval, u9b-eq-r-value, u9b-eq-r-value-prose) and the shapes
    of the class: one stem_given check at warning severity, matched as its detail says, against the request's 0.50 ohm; it fails, while
    the line's own arithmetic holds."""
    checks, findings = new("ph-t13", _after("ph-t13", PH_C, line))
    named = _rule(checks, "named-result")
    assert len(named) == 1 and named[0][0] == "giv" and named[0][1] == "COUNTEREXAMPLE" and named[0][2] == "warning", checks
    assert f"(matched {how}: rule named-result)" in named[0][3] and "'5.3 Ω'" in named[0][3]
    assert "the value the answer gives the internal resistance against the request's internal resistance" in named[0][3]
    assert all(holds(c) for c in checks if c is not named[0]) and not warnings(findings), (checks, findings)


@pytest.mark.parametrize("line", ["So r = (ε − V)/I = (12 V − 9.93 V)/4.14 A = 0.50 Ω.", "So the internal resistance is (12 V − 9.93 V)/4.14 A = 0.50 Ω.",
                                  "So the emf is 9.93 V + 4.14 A × 0.50 Ω = 12.0 V."])
def test_the_right_value_of_a_quantity_the_request_names_holds(line):
    checks, findings = new("ph-t13", _after("ph-t13", PH_C, line))
    assert not failing(checks) and not warnings(findings) and len(_rule(checks, "named-result")) == 1, (checks, findings)


def test_a_given_statement_and_a_relay_are_never_read_by_rule_named_result():
    """A Given statement is set against the request as a Given (rule given-kinds); a report with no request reads nothing against one."""
    checks, _f = new("ph-t13", _after("ph-t13", PH_C, "Given: r = 5.3 Ω."))
    assert checks and not _rule(checks, "named-result") and all(c[0] == "giv" for c in checks), checks
    relay, _f = decide(SPEC["ph-t13"]["response_text"].replace(PH_C, PH_C + "\nSo r = 5.3 Ω."), None, "physics")
    assert not _rule(relay, "named-result")


@pytest.mark.parametrize("request_text, value, words", [
    ("A battery of emf 12 V and internal resistance 0.50 ohm drives a current.", "12 V", ("emf",)),
    ("A battery of emf 12 V and internal resistance 0.50 ohm drives a current.", "0.50 ohm", ("internal", "resistance")),
    ("Find the horizontal component of a 10 N force at 30° to the horizontal.", "10 N", None),
    ("Find the power dissipated in the 6.0 ohm resistor.", "6.0 ohm", None),
])
def test_how_the_request_names_a_quantity(request_text, value, words):
    """The words after a preposition name the quantity ('a battery of emf 12 V' names the emf, not 'battery emf'); a preposition and an
    article right before the value open a noun phrase that names nothing of the value (before, the 10 N force was named 'horizontal
    component', a false alarm on a correct answer that stated the component)."""
    clear_document_cache()
    doc = build_document("x = 1", request_text, "physics")
    named = {request_text[a:b]: tuple(w) for _n, a, b, w in doc.request.named_quantities}
    if words is None:
        assert not any(value in shown for shown in named), named
    else:
        assert any(value in shown and w == words for shown, w in named.items()), named


# ============================================================================================ rule given-function
@pytest.mark.parametrize("line, status", [("Given: v(1) = 4 m s⁻¹.", "COUNTEREXAMPLE"), ("Given: v(1) = 3 m s⁻¹.", "ENTAILED"),
                                          ("Given: v(1) = 300 cm s⁻¹.", "ENTAILED"), ("Given: v(1) = 4.", "COUNTEREXAMPLE"),
                                          ("Given: v(1) = 3.", "ENTAILED")])
def test_a_given_of_a_function_s_value_is_set_against_the_request_s_function(line, status):
    """The tester's 'Given: v(1) = 4 m s⁻¹.' (the request's v(t) = 6t − 3t² gives 3) had neither a check nor an ST code: an agent's true
    finding_missing was refuted. Its check is a stem_arithmetic entry at warning severity, every written digit counting, in the unit the
    request states for v (compared in SI), as written for a bare value."""
    checks, findings = new("maa-t13", _after("maa-t13", MA_END, line))
    assert [(c[0], c[1], c[2]) for c in checks] == [("eq", status, "warning")] and findings == [], (checks, findings)
    d = checks[0][3]
    assert d.startswith("the request's function at the Given's argument, against the Given value") and "(rule given-function)" in d
    assert "rule given-digits" in d and ("its values in m s^-1 as the request states" in d) == ("m s" in line or "cm s" in line)


@pytest.mark.parametrize("line, status", [("Given: v(t) = 6t − 2t².", "COUNTEREXAMPLE"), ("Given: v(t) = 6t − 3t².", "ENTAILED"),
                                          ("Given: v = 6t − 2t².", "COUNTEREXAMPLE"), ("Given: v(x) = 6x − 3x².", "ENTAILED"),
                                          ("Given: v(x) = 6x − 2x².", "COUNTEREXAMPLE")])
def test_a_given_function_is_set_against_the_request_s_function_for_every_value(line, status):
    """The tester's 'Given: v(t) = 6t − 2t².' gave nothing: a stem_algebra entry now sets it against the request's function, its variable
    renamed, for every value of the variable, at warning severity."""
    checks, findings = new("maa-t13", _after("maa-t13", MA_END, line))
    assert [(c[0], c[1], c[2]) for c in checks] == [("alg", status, "warning")] and findings == [], (checks, findings)
    assert checks[0][3].startswith("the Given function against the request's function") and "(rule given-function)" in checks[0][3]


@pytest.mark.parametrize("line, why", [
    ("Given: a(t) = 6 − 4t.", "the request defines no function a of one variable"),
    ("Given: a(1) = 0.", "the request defines no function a of one variable"),
    ("Given: v(1) = 4 kg.", "its unit is not of the dimension of the request's unit for v"),
])
def test_a_given_function_the_request_cannot_set_is_named_st_undec_003(line, why):
    """u9b-giv-ma-a ('Given: a(t) = 6 − 4t.') had nothing; a Given of a function the request does not define, or with a unit of another
    dimension than the request states for its values, is named ST-UNDEC-003 with why, and nothing is checked against the request."""
    checks, findings = new("maa-t13", _after("maa-t13", MA_END, line))
    assert checks == [] and [(c, s) for c, s, _m in findings] == [("ST-UNDEC-003", "warning")], (checks, findings)
    assert why in findings[0][2], findings


@pytest.mark.parametrize("line, kind, status", [("Given: v(1/2) = 2.25 m s⁻¹.", "eq", "ENTAILED"), ("Given: v(1/2) = 2.5 m s⁻¹.", "eq", "COUNTEREXAMPLE"),
                                                ("Given: v(−1) = −9.", "eq", "ENTAILED"), ("Given: v(2 − 1) = 3.", "eq", "ENTAILED"),
                                                ("Given: v(t) = 4.", "alg", "COUNTEREXAMPLE")])
def test_a_number_written_as_an_expression_and_a_constant_function_are_read_too(line, kind, status):
    """The argument may be any number however written; a constant Given function is a function too, set against the request's for every
    value of its variable (v(t) = 4 is not 6t − 3t²)."""
    checks, findings = new("maa-t13", _after("maa-t13", MA_END, line))
    assert [(c[0], c[1], c[2]) for c in checks] == [(kind, status, "warning")] and findings == [], (checks, findings)
    assert "(rule given-function)" in checks[0][3]


@pytest.mark.parametrize("line, why", [
    ("Given: v(t + 1) = 4 m s⁻¹.", "its argument holds a symbol, so it names no value of the request's v"),
    ("Given: v(2t) = 4.", "its argument holds a symbol, so it names no value of the request's v"),
    ("Given: v(1 s) = 3 m s⁻¹.", "its argument is written with a unit, while the request's variable t is written bare"),
    ("Given: v(t) = 4 m s⁻¹.", "its expression is written with a unit"),
    ("Given: v(t) = 6t − 3t² + c.", "its expression has symbols other than its variable t"),
])
def test_a_given_of_the_request_s_function_it_cannot_set_is_named_with_why(line, why):
    checks, findings = new("maa-t13", _after("maa-t13", MA_END, line))
    assert checks == [] and [(c, s) for c, s, _m in findings] == [("ST-UNDEC-003", "warning")] and why in findings[0][2], (checks, findings)


def test_a_given_of_a_function_s_value_is_no_equation_a_later_line_steps_from():
    """Read as the product v·1 = 3, a correct Given made the correct evaluation 'v(2) = 6(2) − 3(2)²' a failing algebra step from it
    (INT-SUBJ-001 on correct working); it is the function's value now, data, and the line's arithmetic alone is checked."""
    request = "Its velocity, v m s^-1, at time t seconds is given by v(t) = 6t - 3t^2. Find v(2)."
    for given, status in (("Given: v(1) = 3.", "ENTAILED"), ("Given: v(1) = 4.", "COUNTEREXAMPLE")):
        checks, findings = decide(given + "\n\nSo v(2) = 6(2) − 3(2)² = 0", request, "mathematics_aa")
        # STEM repair 11 (rule function-value): the evaluation 'v(2) = 6(2) − 3(2)²' is also set against the request's v at 2 (a warning: that
        # it is the request's function is a reading), and holds
        assert [(c[0], c[1], c[2]) for c in checks] == [("eq", status, "warning"), ("eq", "ENTAILED", "warning"), ("eq", "ENTAILED", "error")] \
            and findings == [], (checks, findings)
        assert "(rule given-function)" in checks[0][3] and checks[2][3].startswith("the written arithmetic: '6(2) − 3(2)² = 0'")
        assert checks[1][3].startswith("the function's value at the written argument, against the value stated: 'v(2) = 6(2) − 3(2)²'") \
            and "rule function-value" in checks[1][3], checks[1]
    checks, findings = new("ph-p7b", replaced("ph-p7b", PB_D, PB_D + "\nGiven: C(8) = 820 counts min⁻¹."))
    assert checks == [] and [(c, s) for c, s, _m in findings] == [("ST-UNDEC-003", "warning")], (checks, findings)
    assert "the request defines no function C of one variable" in findings[0][2]


def test_a_given_value_of_f_g_or_h_is_the_written_arithmetic_of_the_application():
    """f, g and h applied to a number are applications in the grammar: a Given of such a value is checked as the written arithmetic of the
    request's function applied (an error when it fails, as any written arithmetic), with no ST code; a Given f(x) is rule given-function's."""
    request = "The function f is defined by f(x) = 2x + 1. Find f(3)."
    for given, status in (("Given: f(2) = 5.", "ENTAILED"), ("Given: f(2) = 6.", "COUNTEREXAMPLE")):
        checks, findings = decide(given + "\n\nf(3) = 2(3) + 1 = 7", request, "mathematics_aa")
        own = [c for c in checks if c[3].startswith(f"the written arithmetic: '{given[7:-1]}'")]
        assert [(c[0], c[1], c[2]) for c in own] == [("eq", status, "error")] and findings == [], (checks, findings)
    checks, _f = decide("Given: f(x) = 2x + 2.\n\nf(3) = 2(3) + 1 = 7", request, "mathematics_aa")
    assert [(c[0], c[1], c[2]) for c in checks if "(rule given-function)" in c[3]] == [("alg", "COUNTEREXAMPLE", "warning")], checks


def test_a_given_function_is_read_only_against_a_request():
    checks, findings = decide("Given: v(1) = 4 m s⁻¹.", None, "mathematics_aa")
    assert not [c for c in checks if "(rule given-function)" in c[3]] and not [f for f in findings if f[0] == "ST-UNDEC-003"]


# ============================================================================================ rule row-terms
@pytest.mark.parametrize("line, term, rule", [
    ("Mean time at 30.0 °C = (33.1 s + 43.0 s + 32.5 s) ÷ 3 = 36.2 s.", "'43.0 s'", "rule table-terms; rule row-terms"),
    ("Mean time at 30.0 °C = (33.1 + 43.0 + 32.5) ÷ 3 = 36.2 s.", "'43.0'", "rule table-terms; rule row-terms"),
    ("Mean time at 30.0 °C = (33.1 s + 17.6 s + 32.5 s) ÷ 3 = 27.7 s.", "'17.6 s'", "rule table-operands; rule row-terms"),
])
def test_a_term_of_a_mean_over_a_row_s_trials_is_set_against_the_row(line, term, rule):
    """The tester's trial copied wrongly (u9b-wg-ch-cell: 43.0 for the 30.0 °C row's 34.0), the same written bare, and another row's trial:
    one stem_given check at warning severity naming rule row-terms, which fails, while the line's arithmetic holds."""
    checks, findings = new("ch-t13", replaced("ch-t13", CH_R, line + "\n\n" + CH_R))
    rows = _rule(checks, "row-terms")
    assert len(rows) == 1 and rows[0][0] == "giv" and rows[0][1] == "COUNTEREXAMPLE" and rows[0][2] == "warning", checks
    assert term in rows[0][3] and f"({rule})" in rows[0][3]
    assert [holds(c) for c in checks if c[0] == "eq"] == [True] and not warnings(findings), (checks, findings)


@pytest.mark.parametrize("line", ["Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s.", "Mean time at 30.0 °C = (32.5 s + 33.1 s + 34.0 s) ÷ 3 = 33.2 s."])
def test_the_row_s_own_trials_hold_in_any_order(line):
    checks, findings = new("ch-t13", replaced("ch-t13", CH_R, line + "\n\n" + CH_R))
    assert not failing(checks) and not warnings(findings) and not _rule(checks, "row-terms"), (checks, findings)


def test_two_unaccounted_terms_are_not_read_by_rule_row_terms():
    """Two terms copied wrongly leave no single repeat each stands for: only the arithmetic is checked, as for rule table-terms."""
    checks, _f = new("ch-t13", replaced("ch-t13", CH_R, "Mean time at 30.0 °C = (33.1 s + 43.0 s + 42.5 s) ÷ 3 = 39.5 s.\n\n" + CH_R))
    assert not _rule(checks, "row-terms") and [c[0] for c in checks] == ["eq"], checks


# ============================================================================================ rule decay-law
@pytest.mark.parametrize("line, status", [
    ("At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 5 = 320 counts min⁻¹.", "COUNTEREXAMPLE"),
    ("After 5 half-lives, C = 1600 counts min⁻¹ × 5/32 = 250 counts min⁻¹.", "COUNTEREXAMPLE"),
    ("At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 32 = 50 counts min⁻¹.", "ENTAILED"),
    ("At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 2⁵ = 50 counts min⁻¹.", "ENTAILED"),
])
def test_a_decay_over_stated_half_lives_with_no_power_of_a_half_is_set_against_the_decay_law(line, status):
    """The tester's 'C = 1600 counts min⁻¹ ÷ 5' after '5 half-lives' (u9-form-pb-div) had only ST-SCOPE-001 (info): the decay law over the
    5 half-lives, 1600 × (½)⁵ = 50, is set against the line's value at warning severity; the line's arithmetic is checked as before."""
    checks, _f = new("ph-p7b", replaced("ph-p7b", PB_D, PB_D + "\n" + line))
    decay = _rule(checks, "decay-law")
    assert len(decay) == 1 and decay[0][0] == "eq" and decay[0][1] == status and decay[0][2] == "warning", checks
    assert "1600 [counts min⁻¹] × (½)^5" in decay[0][3] and decay[0][3].startswith("the decay over the half-lives the prose states")
    assert [holds(c) for c in checks if c[0] == "eq" and c is not decay[0]] == [True], checks


def test_a_power_of_a_half_is_checked_by_rule_half_lives_alone():
    """With a power of ½ written after the count, rule half-lives sets its exponent against the count, as before, and rule decay-law plans
    nothing (the tester's '× (1/2)⁴' variant, u9b-form-pb-pow, named so already)."""
    checks, _f = new("ph-p7b", replaced("ph-p7b", PB_D, PB_D + "\nAt t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹."))
    assert not _rule(checks, "decay-law") and [c[1] for c in _rule(checks, "half-lives")] == ["COUNTEREXAMPLE"], checks


# ============================================================================================ rule statistics
@pytest.mark.parametrize("tid, line, status", [
    ("bi-t13", "The median of 18, 27, 40, 58, 80, 92 and 61 is 61.", "COUNTEREXAMPLE"),
    ("bi-t13", "The median of 18, 27, 40, 58, 80, 92 and 61 is 58.", "ENTAILED"),
    ("bi-t13", "Median uptake = 61 mm³ per g per hour", "COUNTEREXAMPLE"),
    ("bi-t13", "Median uptake = 58 mm³ per g per hour", "ENTAILED"),
    ("bi-t13", "The median uptake is 61 mm³ per g per hour.", "COUNTEREXAMPLE"),
    ("bi-t13", "Median of 18, 27, 40, 58, 80, 92 and 61 = 61", "COUNTEREXAMPLE"),
    ("bi-t13", "Median of 18, 27, 40, 58, 80, 92 and 61 = 58", "ENTAILED"),
    ("bi-t13", "The median of 18, 27, 40 and 58 is 40.", "COUNTEREXAMPLE"),
    ("bi-t13", "The median of 18, 27, 40 and 58 is 33.5.", "ENTAILED"),
    ("bi-t13", "The range of 18, 27 and 40 is 23.", "COUNTEREXAMPLE"),
    ("bi-t13", "The range of 18, 27 and 40 is 22.", "ENTAILED"),
    ("bi-t13", "The mode of 18, 27, 27 and 40 is 18.", "COUNTEREXAMPLE"),
    ("bi-t13", "The mode of 18, 27, 27 and 40 is 27.", "ENTAILED"),
    ("bi-t13", "Mean of 18, 27 and 40 = 29.3", "COUNTEREXAMPLE"),
    ("bi-t13", "Mean of 18, 27 and 40 = 28.3", "ENTAILED"),
    ("maa-t13", "The median of 0, 2 and 3 is 3.", "COUNTEREXAMPLE"),
    ("maa-t13", "The median of 0, 2 and 3 is 2.", "ENTAILED"),
])
def test_a_statistic_of_listed_values_or_a_supplied_column_is_set_against_the_one_the_pack_forms(tid, line, status):
    """The tester's wrong median in three forms (u9-maths-median, u9b-maths-median-eq, u9b-maths-median-list: the median is 58), and the
    class's other statistics: one eq check at warning severity, the statistic formed by the STEM pack from the values as written."""
    anchor = BI_END if tid == "bi-t13" else MA_END
    checks, findings = new(tid, _after(tid, anchor, line))
    stats = _rule(checks, "statistics")
    assert [(c[0], c[1], c[2]) for c in stats] == [("eq", status, "warning")] and not warnings(findings), (checks, findings)
    assert ", formed by the STEM pack, against the stated value" in stats[0][3]
    assert all(holds(c) for c in checks if c is not stats[0]), checks


@pytest.mark.parametrize("line, why", [("The standard deviation of 18, 27 and 40 is 9.0.", "a statistic (standard deviation)"),
                                       ("The interquartile range of 18, 27, 40 and 58 is 20.", "a statistic (interquartile range)"),
                                       ("The mode of 18, 27 and 40 is 27.", "a mode the values do not have as one value (no value occurs twice)")])
def test_a_statistic_the_pack_does_not_form_is_named_st_undec_001(line, why):
    checks, findings = new("bi-t13", _after("bi-t13", BI_END, line))
    assert checks == [] and [(c, s) for c, s, _m in findings] == [("ST-UNDEC-001", "warning")] and why in findings[0][2], (checks, findings)


def test_a_row_s_value_and_a_list_named_otherwise_are_no_statistic():
    """'The mean uptake at C is …' names a row's value (a preposition among its words), never the column's statistic; a list named by a
    word that is no statistic is a relation written partly in words, as before."""
    checks, findings = decide("Sum of 18, 27 and 40 = 85", None, "biology")
    assert checks == [] and [c for c, _s, _m in findings] == ["ST-PARSE-001"]
    checks, _f = new("bi-t13", _after("bi-t13", BI_END, "The mean uptake at 30 °C is 80 mm³ per g per hour."))
    assert not _rule(checks, "statistics"), checks


# ============================================================================================ rule rounded-digits
@pytest.mark.parametrize("tid, old, new_text, status", [
    ("ess-t13", ES_A, "= 60.4% decrease, which is 60.4% to 2 s.f. [1]", "COUNTEREXAMPLE"),
    ("ess-t13", ES_A, "= 60.4% decrease, so 60.4% to 2 s.f. [1]", "COUNTEREXAMPLE"),
    ("ess-t13", ES_A, "= 60.4% decrease, so 60.40% to 3 s.f. [1]", "COUNTEREXAMPLE"),
    ("ess-t13", ES_A, "= 60.4% decrease, which is 60% to 2 s.f. [1]", "ENTAILED"),
    ("ess-t13", ES_A, "= 60.4% decrease, so 60.4% to 3 s.f. [1]", "ENTAILED"),
    ("ph-t13", PH_E, PH_E + "\nTo 3 s.f. the external resistance is 2.4 Ω.", "COUNTEREXAMPLE"),
    ("ph-t13", PH_E, PH_E + "\nTo 3 s.f. the external resistance is 2.40 Ω.", "ENTAILED"),
    ("ph-t13", PH_E, PH_E + "\nTo 3 s.f., R = 2.4 Ω.", "COUNTEREXAMPLE"),
    ("ph-t13", PH_E, PH_E + "\nTo 3 s.f., R = 2.40 Ω.", "ENTAILED"),
])
def test_a_value_stated_with_a_rounding_is_written_to_the_place_it_names(tid, old, new_text, status):
    """The tester's values restated at a rounding without being rounded (u9-prec-ess-sf, u9b-prec-so, u9b-prec-ph-3sf): a check of its
    own at warning severity sets the place the rounding names against the place the value is written to, exactly."""
    checks, _f = new(tid, replaced(tid, old, new_text))
    rd = _rule(checks, "rounded-digits")
    assert [(c[0], c[1], c[2]) for c in rd] == [("eq", status, "warning")], checks
    assert rd[0][3].startswith("the place the rounding the prose states names, against the place the value is written to")


@pytest.mark.parametrize("chain, tail", [("4773.74", "so 4774 euros to the nearest euro"), ("4773.74", "so 4780 to the nearest ten euros"),
                                         ("4773.7401", "so 4773.74 euros to the nearest cent")])
def test_a_whole_number_s_trailing_zeros_and_a_part_of_a_unit_are_read_as_places(chain, tail):
    checks, _f = new("mai-t13", replaced("mai-t13", "Next step: rework (a)", f"Check: 4000 × 1.036⁵ = {chain}, {tail}.\n\nNext step: rework (a)"))
    assert [(c[1], c[2]) for c in _rule(checks, "rounded-digits")] == [("ENTAILED", "warning")], checks


def test_the_recorded_answers_plan_no_check_of_the_new_rules():
    """Every recorded r7 STEM answer reads as before: none is written in a shape a rule of this repair reads. STEM repair 10: mai-t13's
    value restated after a value cut with an ellipsis ('4787.58… = 4788', to the nearest euro) is read now (rule ellipsis-rounding), so
    rule rounded-digits sets its place against the rounding's: that one check, holding, is the only one."""
    rules = ("part-answer", "named-result", "given-function", "row-terms", "decay-law", "statistics", "rounded-digits")
    for tid in ("ph-t13", "ph-p7b", "maa-t13", "mai-t13", "bi-t13", "ess-t13", "ch-t13", "cs-t13"):
        checks, findings = task(tid, SPEC[tid]["response_text"])
        got = [c for c in checks for r in rules if f"rule {r}" in c[3]]
        if tid == "mai-t13":
            assert [(c[0], c[1], c[2]) for c in got] == [("eq", "ENTAILED", "warning")] and "(rule rounded-digits)" in got[0][3] \
                and "'4788'" in got[0][3], got
        else:
            assert not got, tid
        assert not [f for f in findings for r in rules if f"rule {r}" in f[2]], tid
