"""STEM repair 10: the tenth independent test of the STEM completion found classes the front end did not decide as the pack says. Each
is fixed at its cause in the STEM front end, for its whole class, and every new reading has a clean control (correct working is never
flagged):

* rule ``prose-conversion``: whether a restated value ends its clause was read in a window of the whole text, so a wrong conversion written
  with 'is', 'is equal to', 'gives' or ', about' was checked only when it ended the answer; it is read in its own statement;
* rule ``table-operands``: a line that names its rows and its column ('The nitrate rise from site A to site D is (8.4 − 1.2) ÷ 1.2 × 100')
  in a part whose question names another column was read in no column (two named); it is read in its own;
* rule ``row-value``: a value at a site's row restated wrongly went unnamed in common shapes ('Site A has 43 mayfly nymphs per kick sample.',
  'At site A, mayfly nymphs = 43.', '… number 43', 'the most nymphs (43)', 'and only 7'); each is read;
* rule ``named-component``: the other resistor's value substituted for the resistor a sentence names ('The power dissipated in the 4.0 Ω
  resistor is P = (9.93 V)² / 6.0 Ω') held; it is set against the named component;
* rule ``condition-result``: a wrong law evaluated right ('Using C = C₀ − λt, C = … = 1597 counts min⁻¹ at 32 h.') held while part (d) had
  computed 100 counts min⁻¹ at 32 h; the two values of C under one condition are set against each other;
* rule ``prose-base``: a wrong base conversion in prose ('The binary number 110010₂ is 48 in denary.') had neither a check nor an ST code;
* rule ``definite-integral``: a definite integral of a polynomial and an evaluation bracket ('∫₀¹ 6t dt = [3t²]₀¹ = 6') were named
  ST-UNDEC-001 whatever their value; they are checked;
* rule ``operand-precision`` for given data: a numeral that writes a value the request states is exact, so a slip under 1/100 on a power of
  the request's rate ('4000(1.036)^{12} = 6141.73') fails; a stated side of rounded numerals carries their rounding;
* rule ``ellipsis-rounding``: a value restated from a value written with an ellipsis ('= 4787.58…' then '= 4787 euros, to the nearest
  euro') was named ST-UNDEC-001; it is set against the cut digits.
"""
from __future__ import annotations

import pytest

from .test_stem_repair5 import SPEC, decide, failing, holds, new, replaced, task, warnings

#: anchors in the recorded r7 answers
CH_R = "Two reminders."
ES_W = "Water temperature was between 17 °C and 18 °C at every site, so it does not explain the difference."
PH_E = "from 9.9 V to 10.7 V."
PB_E = "Both effects make the count rate smaller than the activity."
CS_END = "Next step: trace"
MA_END = "Marks shown are a provisional allocation."
MI_12 = "$4000(1.036)^{12} = 6114.73$"
MI_R = "$= 4788$ euros, to the nearest euro (A1)"


def _rule(checks, rule: str) -> list:
    return [c for c in checks if f"rule {rule})" in c[3] or f"rule {rule};" in c[3]]


def _ch(line: str, sep: str = "\n\n") -> str:
    return replaced("ch-t13", CH_R, line + sep + CH_R)


def _es(line: str) -> str:
    return replaced("ess-t13", ES_W, line)


def _ph(line: str) -> str:
    return replaced("ph-t13", PH_E, PH_E + "\n" + line)


def _pb(line: str) -> str:
    return replaced("ph-p7b", PB_E, PB_E + "\n" + line)


def _cs(line: str) -> str:
    return replaced("cs-t13", CS_END, line + "\n\n" + CS_END)


def _ma(line: str) -> str:
    return replaced("maa-t13", MA_END, line + "\n\n" + MA_END)


def _named(tid: str, text: str, kind: str, rule: str, severity: str) -> list:
    c, _f = new(tid, text)
    bad = [x for x in failing(c) if x[0] == kind and x[2] == severity and (f"rule {rule})" in x[3] or f"rule {rule};" in x[3])]
    assert bad, (failing(c), c)
    return bad


def _clean(tid: str, text: str) -> list:
    c, f = new(tid, text)
    assert not failing(c) and not warnings(f), (failing(c), warnings(f))
    return c


# ============================================================================================ rule prose-conversion
@pytest.mark.parametrize("sep", ["\n\n", "\n", " "])
@pytest.mark.parametrize("line", ["A time of 45 s is 0.45 min.", "The volume of 55.0 cm³ is 0.550 dm³.", "The volume of 55.0 cm³ is equal to 0.550 dm³.",
                                  "Converting 55.0 cm³ to dm³ gives 0.550 dm³.", "The flask holds 55.0 cm³, about 0.6 dm³."])
def test_a_wrong_prose_conversion_followed_by_another_statement_fails(line, sep):
    """The tester's shapes before 'Two reminders.', separated by a blank line, a line break or a space (before: no check, no ST code: the
    clause end was read in a window of the whole text, which the next statement filled)."""
    bad = _named("ch-t13", _ch(line, sep), "cnv", "prose-conversion", "error")
    assert len(bad) == 1, bad


@pytest.mark.parametrize("sep", ["\n\n", " "])
@pytest.mark.parametrize("line", ["A time of 45 s is 0.75 min.", "The volume of 55.0 cm³ is 0.0550 dm³.", "Converting 55.0 cm³ to dm³ gives 0.0550 dm³."])
def test_the_same_conversions_written_right_hold_when_followed(line, sep):
    c = _clean("ch-t13", _ch(line, sep))
    assert [x for x in c if x[0] == "cnv" and "rule prose-conversion" in x[3]], c


@pytest.mark.parametrize("line", ["A length of 2.0 km is 500 m more than 1.5 km.", "The 50.0 cm³ portion is 0.0500 dm³ of the solution."])
def test_a_value_its_clause_goes_on_after_is_still_no_conversion_when_followed(line):
    c, _f = new("ch-t13", _ch(line))
    assert not [x for x in c if "rule prose-conversion" in x[3]], c


# ============================================================================================ rule table-operands
@pytest.mark.parametrize("line, wrong", [("The nitrate rise from site A to site D is (8.4 − 1.2) ÷ 1.2 × 100 = 600%.", "'8.4'"),
                                         ("From A to D the nitrate falls by (8.4 − 4.1) ÷ 8.4 × 100 = 51.2%.", "'8.4'"),
                                         ("The percentage decrease in nitrate from B to D = (8.4 − 2.3) ÷ 8.4 × 100 = 72.6%.", "'2.3'")])
def test_a_line_naming_its_rows_and_column_is_read_in_its_own_column(line, wrong):
    """In part (c), whose question names the dissolved oxygen: before, the line's nitrate and the question's oxygen were two columns, so
    nothing was read; now the line's own column is, and another row's cell fails at warning severity."""
    bad = _named("ess-t13", _es(line), "giv", "table-operands", "warning")
    assert [b for b in bad if wrong in b[3]], bad


@pytest.mark.parametrize("line", ["The nitrate rise from site A to site D is (4.1 − 1.2) ÷ 1.2 × 100 = 242%.",
                                  "The percentage decrease in nitrate from B to D = (8.4 − 4.1) ÷ 8.4 × 100 = 51.2%."])
def test_the_rows_own_cells_in_the_lines_column_hold(line):
    c = _clean("ess-t13", _es(line))
    assert len(_rule(c, "table-operands")) == 2, c


def test_a_line_whose_numbers_are_no_cells_of_its_named_column_is_read_as_before():
    """'Oxygen falls from A to C as nitrate rises: (9.6 − 3.8) …': the line's words name the nitrate alone (no 'dissolved'), and its numbers
    are no nitrate cells, so the line and the question still name two columns and nothing of the table is read (no false INT-SUBJ-004)."""
    c = _clean("ess-t13", _es("Oxygen falls from A to C as nitrate rises: (9.6 − 3.8) ÷ 9.6 × 100 = 60.4%."))
    assert not _rule(c, "table-operands"), c


# ============================================================================================ rule row-value
@pytest.mark.parametrize("line, value", [("Site A has 43 mayfly nymphs per kick sample.", "'43'"), ("At site A, mayfly nymphs = 43.", "'43'"),
                                         ("The mayfly nymphs at site A number 43.", "'43'"), ("There were 7 mayfly nymphs at site B.", "'7'"),
                                         ("The river has a nitrate concentration of 9.6 mg dm⁻³ at site C.", "'9.6 mg dm⁻³'"),
                                         ("Site A has 2.1 mg dm⁻³ of nitrate.", "'2.1 mg dm⁻³'"), ("At site A, nitrate = 2.1 mg dm⁻³.", "'2.1 mg dm⁻³'"),
                                         ("At site A, the mayfly nymph count = 43.", "'43'")])
def test_a_value_at_a_sites_row_is_read_in_its_new_shapes(line, value):
    bad = _named("ess-t13", _es(line), "giv", "row-value", "warning")
    assert [b for b in bad if value in b[3]], bad


@pytest.mark.parametrize("line, value", [("Site A has 34 mayfly nymphs per kick sample.", "34"), ("At site A, mayfly nymphs = 34.", "34"),
                                         ("The mayfly nymphs at site A number 34.", "34"), ("There were 9 mayfly nymphs at site B.", "9"),
                                         ("The river has a nitrate concentration of 6.9 mg dm⁻³ at site C.", "6.9 mg dm⁻³"),
                                         ("Site A has 1.2 mg dm⁻³ of nitrate.", "1.2 mg dm⁻³")])
def test_the_same_shapes_written_right_hold(line, value):
    _clean("ess-t13", _es(line))
    every, _f = task("ess-t13", _es(line))
    mine = [c for c in _rule(every, "row-value") if f"'{value}' [claims s3.4]" in c[3]]  # the planted line, in place of part (c)'s s3.4
    assert len(mine) == 1 and holds(mine[0]), _rule(every, "row-value")


@pytest.mark.parametrize("old, new_text, value", [("the most nymphs (34)", "the most nymphs (43)", "'43'"), ("and only 9 [1]", "and only 7 [1]", "'7'")])
def test_the_recorded_counts_restated_wrongly_are_named(old, new_text, value):
    """The recorded part (b): a column joined to the clause's first ('… and the most nymphs (34)', named by its last word) and a count the
    clause leaves its column out of ('… and only 9': the table's only column with no unit)."""
    bad = _named("ess-t13", replaced("ess-t13", old, new_text), "giv", "row-value", "warning")
    assert [b for b in bad if value in b[3]], bad


def test_the_recorded_ess_answer_gains_its_two_counts_and_they_hold():
    every, findings = task("ess-t13", SPEC["ess-t13"]["response_text"])
    rows = [c for c in _rule(every, "row-value") if "[claims s2.1]" in c[3]]
    assert sorted(c[3].split("'")[1] for c in rows) == ["1.2", "34", "8.4", "9"], rows
    assert all(holds(c) for c in rows) and not failing(every), failing(every)


# ============================================================================================ rule named-component
@pytest.mark.parametrize("line", ["The power dissipated in the 4.0 Ω resistor is P = (9.93 V)² / 6.0 Ω = 16.4 W.",
                                  "The current through the 4.0 Ω resistor is I = 9.93 V / 6.0 Ω = 1.66 A.",
                                  "The current in the 4.0 Ω resistor is I = 12 V / (6.0 Ω + 0.50 Ω) = 1.8 A."])
def test_another_components_value_substituted_for_the_named_component_fails(line):
    bad = _named("ph-t13", _ph(line), "giv", "named-component", "warning")
    assert "'6.0 Ω'" in bad[0][3] and "the 4.0 Ω resistor" in bad[0][3], bad


@pytest.mark.parametrize("line", ["The power dissipated in the 4.0 Ω resistor is P = (9.93 V)² / 4.0 Ω = 24.7 W.",
                                  "The current through the 4.0 Ω resistor is I = 12 V / 4.5 Ω = 2.7 A.",
                                  "The current in the 4.0 Ω resistor is I = 12 V / (4.0 Ω + 0.50 Ω) = 2.7 A.",
                                  "With the 6.0 Ω resistor removed, I = 12 V / 4.5 Ω = 2.7 A.",
                                  "The current in the 4.0 Ω resistor equals that in the 6.0 Ω resistor: I = 9.93 V / 6.0 Ω = 1.66 A."])
def test_the_named_value_a_computed_total_and_two_named_components_are_not_flagged(line):
    """The named value itself, a total the answer computed (no value the request states), the named value beside another, a component named
    by a word other than a preposition ('With the … removed'), and two components named (which one the working is of is not read)."""
    c = _clean("ph-t13", _ph(line))
    assert not _rule(c, "named-component"), c


# ============================================================================================ rule condition-result
@pytest.mark.parametrize("line", ["Using C = C₀ − λt, C = 1600 − 0.087 × 32 = 1597 counts min⁻¹ at 32 h.",
                                  "At t = 32 h, C = 1600 − 0.087 × 32 = 1597 counts min⁻¹."])
def test_a_value_computed_under_a_condition_is_set_against_the_value_computed_there_before(line):
    bad = _named("ph-p7b", _pb(line), "res", "condition-result", "warning")
    assert "'1597 counts min⁻¹'" in bad[0][3], bad


@pytest.mark.parametrize("line", ["Using C = C₀(½)ⁿ, C = 1600 × (1/2)⁴ = 100 counts min⁻¹ at 32 h.", "At t = 32 h, C = 1600 × (1/2)⁴ = 100 counts min⁻¹."])
def test_the_same_value_computed_again_under_the_condition_holds(line):
    c = _clean("ph-p7b", _pb(line))
    assert _rule(c, "condition-result"), c


def test_another_condition_is_not_read():
    c = _clean("ph-p7b", _pb("C = 1600 × (1/2)³ = 200 counts min⁻¹ at 24 h."))
    assert not _rule(c, "condition-result"), c


# ============================================================================================ rule prose-base
@pytest.mark.parametrize("line", ["The binary number 110010₂ is 48 in denary.", "110010 in binary is 48 in denary.", "The denary number 50 is 110011 in binary.",
                                  "The binary representation of 50 is 110011.", "In hexadecimal, 2F₁₆ is 45 in denary.", "50 in denary is 110011₂."])
def test_a_wrong_base_conversion_in_prose_fails(line):
    _named("cs-t13", _cs(line), "base", "prose-base", "error")


@pytest.mark.parametrize("line", ["The binary number 110010₂ is 50 in denary.", "110010 in binary is 50 in denary.", "The denary number 50 is 110010 in binary.",
                                  "The binary representation of 50 is 110010.", "In hexadecimal, 2F₁₆ is 47 in denary."])
def test_the_same_conversions_written_right_hold(line):
    c = _clean("cs-t13", _cs(line))
    assert _rule(c, "prose-base"), c


@pytest.mark.parametrize("line", ["110010₂ is 50 more than 0.", "The binary search makes at most 10 passes.", "A pass makes 2 comparisons in binary search."])
def test_what_states_no_second_base_is_not_read(line):
    c, _f = new("cs-t13", _cs(line))
    assert not _rule(c, "prose-base"), c


@pytest.mark.parametrize("line", ["10 in binary is 1010.", "11 in binary is 1011.", "100 in octal is 144.", "100 in hexadecimal is 64.",
                                  "1010 in binary is 10.", "50 in binary is 110010."])
def test_a_base_named_right_after_the_first_numeral_is_read_both_ways_and_correct_working_holds(line):
    """'10 in binary is 1010' converts 10 into binary; '1010 in binary is 10' names the first numeral's base. Reading the first numeral only
    in the named base had failed the conversions written the first way (a false INT-SUBJ-001): either reading now holds the check."""
    c = _clean("cs-t13", _cs(line))
    assert [(x[0], x[1]) for x in _rule(c, "prose-base")] == [("base", "ENTAILED")], c


@pytest.mark.parametrize("line", ["10 in binary is 1011.", "50 in binary is 110011.", "1010 in binary is 11.", "100 in octal is 145.",
                                  "10 in binary is 10."])
def test_a_wrong_conversion_with_the_base_named_after_the_first_numeral_fails_both_ways(line):
    _named("cs-t13", _cs(line), "base", "prose-base", "error")


def test_a_base_named_for_neither_numeral_stays_unread():
    c, _f = new("cs-t13", _cs("10 in denary is 1010."))
    assert not _rule(c, "prose-base"), c


# ============================================================================================ rule definite-integral
@pytest.mark.parametrize("line", ["Also ∫₀¹ 6t dt = [3t²]₀¹ = 6.", "Also ∫₀¹ 6t dt = 6.", "Also ∫₀¹ 6t dt = [6t²]₀¹ = 6.", "Also ∫₀² t² dt = 2.6.",
                                  "Also $\\int_0^2 3t^2\\,dt = [t^3]_0^2 = 9$."])
def test_a_wrong_definite_integral_fails(line):
    c, _f = new("maa-t13", _ma(line))
    bad = [x for x in failing(c) if "rule definite-integral" in x[3] and x[2] == "error"]
    assert bad, (failing(c), c)


@pytest.mark.parametrize("line", ["Also ∫₀¹ 6t dt = [3t²]₀¹ = 3.", "Also ∫₀¹ 6t dt = 3.", "Also ∫₀² t² dt = 2.67.", "Also $\\int_0^2 3t^2\\,dt = [t^3]_0^2 = 8$."])
def test_the_same_integrals_written_right_hold_and_nothing_is_left_undecided(line):
    c = _clean("maa-t13", _ma(line))
    assert [x for x in c if "rule definite-integral" in x[3]], c


def test_the_recorded_brackets_are_checked_and_the_integral_of_a_symbol_stays_undecided():
    every, findings = task("maa-t13", SPEC["maa-t13"]["response_text"])
    brackets = [c for c in every if c[3].startswith("the antiderivative evaluated between its limits")]
    assert len(brackets) == 2 and all(holds(c) for c in brackets), brackets
    und = [m for code, _s, m in findings if code == "ST-UNDEC-001"]
    assert not [m for m in und if m.startswith("a relation outside the encodings: the evaluation of an antiderivative")], und
    assert len([m for m in und if "an integral; the evaluation of an antiderivative between limits" in m]) == 2, und  # '∫₀² v dt': v no polynomial
    bad = _named("maa-t13", replaced("maa-t13", "= (12 − 8) − 0 = 4", "= (12 − 8) − 1 = 3"), "eq", "definite-integral", "error")
    assert "(12 − 8) − 1" in bad[0][3], bad


@pytest.mark.parametrize("text, status", [("∫₀¹ x dx = 1/2", "ENTAILED"), ("∫₀¹ x dx = 1/3", "COUNTEREXAMPLE")])
def test_a_definite_integral_of_a_polynomial_is_checked(text, status):
    """'∫₀¹ x dx = 1/2' was the example of tests/stem/test_relations.py's undecided relations (before: ST-UNDEC-001 'an integral')."""
    checks, findings = decide(text, None, "mathematics_aa")
    assert [(k, s) for k, s, _sev, _d in checks] == [("eq", status)] and not findings, (checks, findings)


@pytest.mark.parametrize("text", ["∫₀¹ √x dx = 2/3", "∫_0^{1.5} x dx = 1.125", "∫₀¹ 6t dt = [3t²]₀² = 12"])
def test_an_integral_outside_the_reading_stays_named_undecided(text):
    """A root in the integrand, a limit that is no whole number, and an integral set against a bracket between other limits: named
    ST-UNDEC-001 'an integral', never failed. (A limit with a sign is read: the test below.)"""
    checks, findings = decide(text, None, "mathematics_aa")
    assert not failing(checks) and [f for f in findings if f[0] == "ST-UNDEC-001" and "an integral" in f[2]], (checks, findings)


# ============================================================================================ rule operand-precision, given data
@pytest.mark.parametrize("value", ["6141.73", "6114.74"])
def test_a_slip_on_a_power_of_the_requests_rate_fails(value):
    """4000 × 1.036¹² = 6114.7268…: the request's 3.6% makes 1.036 exact, so the band is the stated value's half-width alone (before: the
    rounding of 1.036 left τ at 1/100, and a 0.44% slip held)."""
    _c, _f = new("mai-t13", replaced("mai-t13", MI_12, MI_12.replace("6114.73", value)))
    bad = [x for x in failing(_c) if x[0] == "eq" and x[2] == "error" and value in x[3]]
    assert bad and "rule operand-precision" in bad[0][3], (failing(_c), _c)


def test_the_recorded_powers_of_the_rate_hold_with_tau_zero():
    every, _f = task("mai-t13", SPEC["mai-t13"]["response_text"])
    powers = [c for c in every if "4000(1.036)^{1" in c[3]]
    assert len(powers) == 2 and all(holds(c) for c in powers), powers
    assert all("τ = 0: twice the largest relative change" in c[3] for c in powers), powers


@pytest.mark.parametrize("line, ok", [("Also $4000(1.036)^{3} = 4447.74$.", True), ("Also $4000(1.036)^{3} = 4447.79$.", False)])
def test_a_power_of_the_rate_in_a_new_line(line, ok):
    text = replaced("mai-t13", "**Part (b) — find — 3 marks**", line + "\n\n**Part (b) — find — 3 marks**")
    c, f = new("mai-t13", text)
    assert (not failing(c) and not warnings(f)) if ok else [x for x in failing(c) if "4447.79" in x[3]], (c, f)


def test_a_stated_side_of_rounded_numerals_carries_their_rounding():
    """Found closing the class: '1/4.0 Ω + 1/6.0 Ω = 0.250 Ω⁻¹ + 0.167 Ω⁻¹' (the recorded ph-t13) holds once 4.0 and 6.0 are the request's
    exact values only because the stated side's rounding is in the band (it had failed: τ = 0, the stated side no half-width)."""
    every, _f = task("ph-t13", SPEC["ph-t13"]["response_text"])
    line = [c for c in every if "'1/4.0 Ω + 1/6.0 Ω = 0.250 Ω⁻¹ + 0.167 Ω⁻¹'" in c[3]]
    assert len(line) == 1 and holds(line[0]), line
    _clean("ph-t13", _ph("Also 1/6.0 Ω + 1/6.0 Ω = 0.167 Ω⁻¹ + 0.167 Ω⁻¹ = 0.333 Ω⁻¹."))


# ============================================================================================ rule ellipsis-rounding
@pytest.mark.parametrize("new_text", ["$= 4787$ euros, to the nearest euro (A1)", "$= 4787.5$ (A1)"])
def test_a_wrong_restatement_of_a_cut_value_fails(new_text):
    bad = _named("mai-t13", replaced("mai-t13", MI_R, new_text), "res", "ellipsis-rounding", "error")
    assert "4787.58" in bad[0][3], bad


def test_the_recorded_rounding_of_the_cut_value_holds_and_its_power_stays_undecided():
    """The recorded restatement of 4787.58… to the nearest euro holds, and so does the recorded '\\dfrac{\\ln 1.5}{\\ln 1.003} = 135.36\\ldots'
    (135.357…, within the cut digits and their rounded reading), the computed value set against its cut value.

    Rewritten by the merge of the overseer build into the translator, to a stricter assertion: the development branch's end-to-end
    detection fixes read a closed base raised to an integer beyond 12 as one value (``RealPower``, docs/STEM_DESIGN.md section 33, item 4),
    so the recorded powers of 1.003 are no longer outside the encodings: before, this test pinned two ST-UNDEC-001 findings on s6.1 naming
    'an integer power beyond 12 (60)'; now each line holding such a power is checked against its cut value and must hold, and no such
    finding may remain. Every assertion about the checks it pinned before is kept exactly."""
    every, findings = task("mai-t13", SPEC["mai-t13"]["response_text"])
    res = [c for c in _rule(every, "ellipsis-rounding") if c[0] == "res"]
    assert len(res) == 1 and holds(res[0]) and "'to the nearest euro'" in res[0][3], res
    # STEM repair 11 (rule inequality-solution): the two recorded steps '12n > 135.36…, so n > 11.28…' are checked now too, their cut values
    # read as rule ellipsis-rounding reads them; both hold, and the cut value's own check is still the one it was
    cut = [c for c in _rule(every, "ellipsis-rounding") if c[0] == "eq" and "rule inequality-solution" not in c[3]]
    logs = [c for c in cut if "135.36" in c[3]]
    assert len(logs) == 1 and holds(logs[0]) and "digits cut" in logs[0][3], cut
    # the closed powers beyond 12 the merged translator decides: s6.1's 1.003^60 and s12.3's 1.003^132 and 1.003^144, each against its cut
    # value, and nothing else
    powers = [c for c in cut if c is not logs[0]]
    assert len(cut) == 4 and len(powers) == 3 and all(holds(c) and "digits cut" in c[3] for c in powers), cut
    assert sorted(next(p for p in ("^{60}", "^{132}", "^{144}") if p in c[3]) for c in powers) == ["^{132}", "^{144}", "^{60}"], powers
    solved = [c for c in _rule(every, "inequality-solution") if c[0] == "eq"]
    assert len(solved) == 2 and all(holds(c) for c in solved) and all("11.28" in c[3] for c in solved), solved
    und = [m for code, _s, m in findings if code == "ST-UNDEC-001" and ("s6.1" in m or "integer power beyond 12" in m)]
    assert und == [], und
    _clean("mai-t13", replaced("mai-t13", MI_R, "$= 4787.6$, to 1 d.p. (A1)"))


# ============================================================================================ every recorded STEM answer
@pytest.mark.parametrize("tid", ["ph-t13", "ph-p7b", "maa-t13", "maa-p7b", "mai-t13", "bi-t13", "ess-t13", "ch-t13", "cs-t13"])
def test_no_recorded_answer_fails_any_check(tid):
    """The new readings add only checks that hold to the recorded answers (ess-t13 two counts, maa-t13 two brackets, mai-t13 the rounding of
    its cut value and its digits), and none of them fails anything."""
    every, findings = task(tid, SPEC[tid]["response_text"])
    assert not failing(every), failing(every)
    assert not [f for f in findings if f[0] in ("ST-DIM-001", "ST-DIM-002", "INT-SUBJ-004")], findings


# ============================================================================================ found closing the classes (STEM repair 10)
# rule row-value, the clause reading: a value at a row stated in any order of its row, its column and its verb
@pytest.mark.parametrize("line", ["Dissolved oxygen was 3.9 mg dm⁻³ at site C.", "At site C dissolved oxygen is 3.9 mg dm⁻³.",
                                  "Dissolved oxygen at site C, 3.9 mg dm⁻³, is the lowest.", "Dissolved oxygen at site C is only 3.9 mg dm⁻³.",
                                  "Site C's dissolved oxygen is 3.9 mg dm⁻³.", "The dissolved oxygen of site C is 3.9 mg dm⁻³.",
                                  "Dissolved oxygen is 3.9 mg dm⁻³ at C."])
def test_a_wrong_value_at_a_row_is_named_in_any_order_of_its_clause(line):
    """Site C's dissolved oxygen is 3.8 mg dm⁻³: each line had neither a check nor an ST code (the shapes fixed the order of the row, the
    column and the verb)."""
    bad = _named("ess-t13", _es(line), "giv", "row-value", "warning")
    assert len(bad) == 1 and "'3.9 mg dm⁻³'" in bad[0][3], bad


@pytest.mark.parametrize("line", ["Dissolved oxygen was 3.8 mg dm⁻³ at site C.", "Site C's dissolved oxygen is 3.8 mg dm⁻³.",
                                  "At site C dissolved oxygen is 3.8 mg dm⁻³."])
def test_the_same_clauses_written_right_hold(line):
    c = _clean("ess-t13", _es(line))
    assert [x for x in c if x[0] == "giv" and "rule row-value" in x[3]], c


@pytest.mark.parametrize("line", ["Dissolved oxygen at site C is 5.8 mg dm⁻³ lower than at A.", "The nitrate at B is 7.2 mg dm⁻³ higher than at A.",
                                  "Nitrate at B is 7 times that at A.", "Dissolved oxygen falls by 5.8 mg dm⁻³ at site C."])
def test_a_difference_or_a_ratio_stated_at_a_row_is_no_cell(line):
    """Each is correct (9.6 − 3.8, 8.4 − 1.2, 8.4 ÷ 1.2): before, the first three were set against the row's cell and failed (a false
    INT-SUBJ-004); a value followed by a comparison or an operation is no cell."""
    c = _clean("ess-t13", _es(line))
    assert not [x for x in c if "rule row-value" in x[3]], c


# a numbered row ('at 12 h', 'at t = 12 h') and a column told apart by its number ('trial 2')
@pytest.mark.parametrize("line", ["The detector gave a measured count rate of 568 counts min⁻¹ at 12 h.", "At 12 h, measured count rate = 568 counts min⁻¹.",
                                  "The measured count rate was 568 counts min⁻¹ at 12 h.", "At 12 h the measured count rate is 568 counts min⁻¹.",
                                  "The measured count rate at t = 12 h is 568 counts min⁻¹."])
def test_a_wrong_value_at_a_numbered_row_is_named(line):
    """The table's 586 counts per minute at 12 h, copied as 568: before, these shapes read only a site's letter, and the key 't = 12 h'
    was no row key; nothing was planned."""
    bad = _named("ph-p7b", _pb(line), "giv", "row-value", "warning")
    assert len(bad) == 1 and "'568 counts min⁻¹'" in bad[0][3], bad


@pytest.mark.parametrize("line", ["The detector gave a measured count rate of 586 counts min⁻¹ at 12 h.", "At 12 h, measured count rate = 586 counts min⁻¹.",
                                  "The measured count rate was 586 counts min⁻¹ at 12 h."])
def test_the_same_numbered_rows_written_right_hold(line):
    c = _clean("ph-p7b", _pb(line))
    assert [x for x in c if x[0] == "giv" and "rule row-value" in x[3]], c


@pytest.mark.parametrize("line", ["The corrected count rate at 12 h is 566 counts min⁻¹.", "The count rate at 12 h is 566 counts min⁻¹ after correction.",
                                  "The corrected rate falls from 1131 counts min⁻¹ at 4 h to 566 counts min⁻¹ at 12 h.", "The decay rate at 12 h is 0.087 h⁻¹."])
def test_a_processed_quantity_or_another_quantity_at_a_row_is_no_cell(line):
    """Each is correct: the corrected rates (measured − 20) and the decay constant. Before, rule row-value and rule table-data set the first
    three against the measured column (586, 1151) and the last against it too ('rate', one dimension), each a false INT-SUBJ-004; and rule
    named-change set the 1131 at 4 h against part (d)'s 100 counts min⁻¹ at 32 h. A word of a processed quantity the column's name lacks,
    a modifier of another quantity, and a value the change states under a condition of its own are not read."""
    c = _clean("ph-p7b", _pb(line))
    assert not [x for x in c if "rule row-value" in x[3] or "rule table-data" in x[3] or "rule named-change" in x[3]], c


def test_a_change_from_a_value_with_no_condition_is_still_set_against_the_earlier_value():
    bad = _named("ph-p7b", _pb("The corrected count rate falls from 120 counts min⁻¹ to 60 counts min⁻¹ over the next half-life."), "res",
                 "named-change", "warning")
    assert len(bad) == 1, bad
    _clean("ph-p7b", _pb("The corrected count rate falls from 100 counts min⁻¹ to 50 counts min⁻¹ over the next half-life."))


@pytest.mark.parametrize("line, status", [("At 30.0 °C, trial 2 took 43.0 s.", "COUNTEREXAMPLE"), ("At 30.0 °C, trial 2 took 34.0 s.", "ENTAILED"),
                                          ("The time for trial 2 at 30.0 °C is 43.0 s.", "COUNTEREXAMPLE")])
def test_a_column_told_apart_by_its_number_is_read(line, status):
    """'Time, trial 1 / s', 'Time, trial 2 / s' and 'Time, trial 3 / s' share every word: before, no column was read."""
    c, _f = new("ch-t13", _ch(line))
    got = [x for x in c if x[0] == "giv" and "rule row-value" in x[3]]
    assert [(x[1], x[2]) for x in got] == [(status, "warning")], c


# rule table-data: the clause is the value's own statement
def test_a_neighbouring_statement_naming_another_column_no_longer_hides_the_line():
    """Part (d)'s first sentence rewritten to name the dissolved oxygen: before, the 160 characters before 'from 1.2 mg dm⁻³ at A' crossed
    into it, two columns were named, and the line's values were read in none (so B's nitrate written 6.1 went unnamed)."""
    first = "(d) Upgrading the sewage treatment works to remove nitrate controls the release at source."
    other = "(d) Upgrading the sewage treatment works also raises the dissolved oxygen downstream."
    text = replaced("ess-t13", first, other)
    c, _f = task("ess-t13", text)
    assert len([x for x in c if x[0] == "giv" and "rule table-data" in x[3] and "rule row-value" not in x[3]]) == 2 and not failing(c), c
    wrong = text.replace("to 8.4 mg dm⁻³ at B, across", "to 6.1 mg dm⁻³ at B, across")
    c, _f = task("ess-t13", wrong)
    assert [(x[1], x[2]) for x in failing(c)] == [("COUNTEREXAMPLE", "warning")] and "'6.1 mg dm⁻³'" in failing(c)[0][3], c


# rule definite-integral: a limit with a sign, and limits after '_' and '^' in plain text
@pytest.mark.parametrize("text, status", [("∫₋₁¹ x dx = 0", "ENTAILED"), ("∫₋₁¹ x dx = 1", "COUNTEREXAMPLE"),
                                          ("$\\int_{-1}^{1} x^2\\,dx = 2/3$", "ENTAILED"), ("∫_{-2}^{-1} 2x dx = −3", "ENTAILED"),
                                          ("∫₋₂⁻¹ 2x dx = 3", "COUNTEREXAMPLE"), ("∫_0^1 6t dt = 3", "ENTAILED"), ("∫_0^1 6t dt = 6", "COUNTEREXAMPLE"),
                                          ("∫_{0}^{2} 3x² dx = 8", "ENTAILED")])
def test_a_definite_integral_with_a_signed_or_a_caret_limit_is_checked(text, status):
    """Before, a subscript minus ('₋₁') or limits written after '_' and '^' in plain text ended the span reader at the limit: the relation had
    no check and no ST code at all (a silent miss); with LaTeX, a signed limit was ST-UNDEC-001."""
    checks, findings = decide(text, None, "mathematics_aa")
    assert [(k, s) for k, s, _sev, _d in checks] == [("eq", status)] and not findings, (checks, findings)
    assert "(rule definite-integral)" in checks[0][3]


# rule ellipsis-rounding: a value written with its digits cut in plain text, and a computed value set equal to it
@pytest.mark.parametrize("text, status", [("8/3 = 2.66…", "ENTAILED"), ("8/3 = 2.67…", "ENTAILED"), ("8/3 = 2.65…", "COUNTEREXAMPLE"),
                                          ("8/3 = 2.68...", "COUNTEREXAMPLE"), ("$\\frac{8}{3} = 2.66\\ldots$", "ENTAILED"), ("2/3 = 0.666…", "ENTAILED")])
def test_a_computed_value_set_equal_to_a_cut_value_is_checked_within_its_digits(text, status):
    """Before, a plain '…' or '...' after a decimal was punctuation that ended the run, so '2.66' was read as a rounded value: '8/3 = 2.66…'
    failed (a false INT-SUBJ-001), and with '\\ldots' the link was ST-UNDEC-001 whatever its value."""
    checks, findings = decide(text, None, "mathematics_aa")
    assert [(k, s) for k, s, _sev, _d in checks] == [("eq", status)] and not findings, (checks, findings)
    assert "(rule ellipsis-rounding)" in checks[0][3]


@pytest.mark.parametrize("line, status", [("Also 8/3 = 2.66… = 2.6, to 2 s.f.", "COUNTEREXAMPLE"), ("Also 8/3 = 2.66… = 2.7, to 2 s.f.", "ENTAILED"),
                                          ("Also 8/3 = 2.66... = 2.6, to 2 s.f.", "COUNTEREXAMPLE")])
def test_a_restatement_of_a_cut_value_in_plain_text_is_checked(line, status):
    c, _f = new("maa-t13", _ma(line))
    assert [(x[1], x[2]) for x in c if x[0] == "res" and "rule ellipsis-rounding" in x[3]] == [(status, "error")], c
    assert not [x for x in failing(c) if x[0] != "res"], c


# rule operand-precision for given data: the slip the earlier test data carried
def test_the_slip_the_earlier_test_data_carried_is_named():
    """4000 × 1.036⁵ = 4773.740074…: '4773.7406' slips in its fourth decimal (4773.7401). With the request's 3.6% exact it fails (before:
    it held within the rounding 1.036 was taken to carry); the repair-4 tests and probes that wrote it now write 4773.7401, which holds."""
    line = "Check: 4000 × 1.036⁵ = {}, so 4773.74 euros to the nearest cent.\n\nNext step: rework (a)"
    c, _f = new("mai-t13", replaced("mai-t13", "Next step: rework (a)", line.format("4773.7406")))
    assert [(x[0], x[1], x[2]) for x in failing(c)] == [("eq", "COUNTEREXAMPLE", "error")] and "4773.7406" in failing(c)[0][3], c
    c, _f = new("mai-t13", replaced("mai-t13", "Next step: rework (a)", line.format("4773.7401")))
    assert not failing(c), c


# rule ellipsis-rounding, closing the class: the cut value on either side, an approximate link, and a cut value inside an expression
@pytest.mark.parametrize("text, status", [("0.333… = 1/3", "ENTAILED"), ("0.333… = 1/4", "COUNTEREXAMPLE"), ("2.66… = 8/3", "ENTAILED"),
                                          ("2.68… = 8/3", "COUNTEREXAMPLE"), ("$0.333\\ldots = \\frac{1}{3}$", "ENTAILED"),
                                          ("$0.343\\ldots = \\frac{1}{3}$", "COUNTEREXAMPLE")])
def test_a_cut_value_set_equal_to_a_computed_value_on_its_left_is_checked(text, status):
    """The cut value may stand on the left of the closed expression it states the digits of ('0.333… = 1/3'): before, the plain form was
    read as no relation at all (the '…' ended the run, a silent miss) and the LaTeX form ST-UNDEC-001, whatever its value."""
    checks, findings = decide(text, None, "mathematics_aa")
    assert [(k, s) for k, s, _sev, _d in checks] == [("eq", status)] and not findings, (checks, findings)
    assert "(rule ellipsis-rounding)" in checks[0][3]


@pytest.mark.parametrize("text, status", [("8/3 ≈ 2.66…", "ENTAILED"), ("8/3 ≈ 2.86…", "COUNTEREXAMPLE"), ("4787.58… ≈ 4788", "ENTAILED"),
                                          ("4787.58… ≈ 5100", "COUNTEREXAMPLE"), ("$4787.58\\ldots \\approx 4788$", "ENTAILED")])
def test_an_approximate_link_to_a_cut_value_is_checked_with_the_approximate_tolerance(text, status):
    """'8/3 ≈ 2.66…' had been read as '8/3 ≈ 2.66' (the plain '…' ending the run) and held; reading the ellipsis must not leave it, nor the
    LaTeX form, unchecked: the cut value's band with τ = 1/20 (R2), so a value 7% off fails."""
    checks, findings = decide(text, None, "mathematics_aa")
    assert [(k, s) for k, s, _sev, _d in checks] == [("eq", status)] and not findings, (checks, findings)
    assert "(rule ellipsis-rounding)" in checks[0][3] and "τ = 1/20" in checks[0][3], checks


@pytest.mark.parametrize("text", ["0.333… × 3 = 1", "$0.333\\ldots \\times 3 = 1$", "0.333… + 0.666… = 1", "0.333… × 3 = 1.5"])
def test_a_cut_value_inside_an_expression_is_named_undecided_never_failed(text):
    """The ellipsis after a decimal takes nothing after it: '0.333… × 3' is the cut value times 3, an expression the rule does not read, so
    the relation is named ST-UNDEC-001 whatever its value (before this was closed, the marker took '× 3' as its operand and the correct line
    was read as '0.333…' restated as 1 and failed: a false INT-SUBJ-001)."""
    checks, findings = decide(text, None, "mathematics_aa")
    assert checks == [] and [f[0] for f in findings] == ["ST-UNDEC-001"], (checks, findings)


@pytest.mark.parametrize("text", ["x = 2.66…", "$x = 2.66\\ldots$"])
def test_a_symbol_set_equal_to_a_cut_value_is_named_undecided_as_in_latex(text):
    """A symbol set equal to a cut decimal binds nothing the checks can carry: ST-UNDEC-001, the LaTeX form's reading before and after this
    repair (the plain form, before, bound the symbol to the digits as if rounded)."""
    checks, findings = decide(text, None, "mathematics_aa")
    assert checks == [] and [f[0] for f in findings] == ["ST-UNDEC-001"], (checks, findings)


# rule row-value, closing the class: a value stated under a condition, a hypothesis, a target, a bound or a modal verb is no cell
@pytest.mark.parametrize("tid, line", [
    ("ess-t13", "A target of 9.0 mg dm⁻³ of dissolved oxygen at site C would need less sewage."),
    ("ess-t13", "If nitrate at site B fell to 4.0 mg dm⁻³, oxygen there might rise."),
    ("ess-t13", "Dissolved oxygen at site C would have to rise to 6.0 mg dm⁻³ for mayfly to return."),
    ("ess-t13", "Dissolved oxygen of 6.0 mg dm⁻³ at site C would allow mayfly to return."),
    ("ess-t13", "Dissolved oxygen at site C is below 4.0 mg dm⁻³."),
    ("ess-t13", "Nitrate at site B exceeds 8.0 mg dm⁻³."),
    ("ph-p7b", "If the count rate at 12 h were 600 counts min⁻¹, the half-life would be longer."),
    ("ch-t13", "Had trial 2 at 30.0 °C taken 36.0 s, the mean would be 33.9 s."),
])
def test_a_value_under_a_condition_a_target_a_bound_or_a_modal_verb_at_a_row_is_no_cell(tid, line):
    """Each is correct working: no value the row has. The clause reading set the target, the hypothetical values and the bounds against the
    cell (a false INT-SUBJ-004 each; 'If nitrate at site B fell to 4.0 mg dm⁻³' already did on the staged tree, through the shape that reads
    'falls to')."""
    text = {"ess-t13": _es, "ph-p7b": _pb}[tid](line) if tid != "ch-t13" else _ch(line)
    c = _clean(tid, text)
    assert not [x for x in c if "rule row-value" in x[3] or "rule table-data" in x[3]], c


@pytest.mark.parametrize("tid, line, value", [
    ("ess-t13", "Nitrate at E (2.4 mg dm⁻³) stays above the upstream value at A.", "'2.4'"),
    ("ess-t13", "Site C's dissolved oxygen is only 3.9 mg dm⁻³, a level that would stress mayfly.", "'3.9 mg dm⁻³'"),
    ("ess-t13", "Dissolved oxygen at site C is 3.9 mg dm⁻³ and mayfly could not survive there.", "'3.9 mg dm⁻³'"),
])
def test_a_wrong_value_at_a_row_is_still_named_beside_a_bound_or_a_modal_verb_of_another_clause(tid, line, value):
    """The control: a bound after the value, and a modal verb after the value's clause, leave the value stated, so a wrong one still fails."""
    bad = _named(tid, _es(line), "giv", "row-value", "warning")
    assert len(bad) == 1 and value in bad[0][3], bad
