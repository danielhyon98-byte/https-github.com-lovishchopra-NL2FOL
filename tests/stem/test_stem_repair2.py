"""STEM repair 2: the independent test of the STEM completion found STEM faults the translator's reading did not see, a
false error on correct integer working, and statements skipped with neither a check nor an ST code. Each is fixed at its
cause in the STEM front end, for its whole class, and every new reading has a clean control (correct working is never
flagged):

* integer arithmetic: a remainder or an integer quotient written with the words ``mod``, ``modulo``, ``div`` (any case),
  the signs ``//`` and, in Computer Science, ``%``, LaTeX ``\\bmod``, a quotient stated with its remainder ("17 ÷ 5 = 3
  remainder 2") and a congruence ("17 ≡ 2 (mod 5)") are read whole and decided in integer arithmetic (IR ``mod`` and
  ``idiv`` under ``to_real``); the reader had dropped the left operand and the word and checked "5 = 2";
* verbal arithmetic ("3 times 4 = 12") is read once, as the verbal span, never also as its tail "4 = 12";
* rule ``fragment``: a relation whose left side continues the words before it ("17 is divided by 5 = 2", "12 over 4 = 3")
  is ST-PARSE-001, never the false check "5 = 2"; rule ``unread-relation``: a relation sign between maths that no span
  reads ("17 % 5 = 2" outside Computer Science) is ST-PARSE-001 too, so no relation is silently unchecked;
* rule ``question``: a relation the answer asks and answers ("Is 67 = 67? No.") is checked as answered, its negation for
  "no"; one with no answer is context;
* rule ``given-kinds``: every Given value is set against the request's values of its kind (the same symbol, the same
  dimension, the percentages, the numbers written with the same word, the request's number a bare Given equals; a row and
  a column of a supplied table) or named unchecked, ST-UNDEC-003, one finding per statement; a bare number the request
  does not state (0.036 for 3.6%, 12 for "monthly") is named unchecked, never failed; zero and a data-booklet constant at
  the booklet's value are neither; rule ``named-given``: a value the prose states for a quantity the request names by its
  words ("The battery's emf is 9.0 V") is set against it;
* rule ``table-operands``: the values a line of working takes from a supplied table are set against the rows the line or
  its part's question names, when the line takes as many different cells as rows are named (a mean of three rows is
  another computation);
* rule ``restated-binding``: a value given to a symbol after "so" right after a chain ("(so C(8) = 800)") is set against
  the chain's value; rule ``exact-carry``: a value the written arithmetic gives exactly carries no rounding interval, so a
  sum of count rates written with units is decided in Form E, not passed in Form S;
* a relation in brackets after a word ("greatest at C (2.0 km = 200 m)"), a relation introduced by a premise word ("From
  c = n/V, n = c/V ...") and a sum in a sentence of prose are read and checked.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.relations import ST_SEVERITY

R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))
SPEC: dict[str, dict] = R7["specialists"]
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
MI_Q, PH_Q = SPEC["mai-t13"]["question"], SPEC["ph-t13"]["question"]


def _data(tid: str) -> tuple[str, ...]:
    return tuple(t["text"] for t in SPEC[tid].get("supplied_texts") or [])


def decided(text: str, profile: str = "physics", request: str = None, data: tuple = ()):
    """(checks as (kind, status, severity, form, description), findings as (code, message)) for ``text``, every check decided."""
    clear_document_cache()
    doc = build_document(text, request, profile, **({"data": data} if data else {}))
    plan = build_checks(doc, report_id="r", request_id="q")
    checks = [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy)).status.value,
               pc.failure_severity, pc.form, pc.description) for pc in plan.checks]
    return checks, [(f.code, f.message) for f in list(doc.findings) + list(plan.findings)]


def statuses(text: str, profile: str = "physics", **kw) -> list[tuple[str, str]]:
    return [(k, st) for k, st, _sev, _form, _d in decided(text, profile, **kw)[0]]


def codes(text: str, profile: str = "physics", **kw) -> list[str]:
    return [c for c, _m in decided(text, profile, **kw)[1]]


# ============================================================================================ integer arithmetic
@pytest.mark.parametrize("text, profile", [
    ("17 mod 5 = 2", "computer_science"), ("17 div 5 = 3", "computer_science"), ("9 div 2 = 4", "computer_science"), ("9 mod 2 = 1", "computer_science"),
    ("17 MOD 5 = 2", "computer_science"), ("17 DIV 5 = 3", "computer_science"), ("17 modulo 5 = 2", "computer_science"), ("17 // 5 = 3", "computer_science"),
    ("17 % 5 = 2", "computer_science"), ("(3 + 4) mod 5 = 2", "computer_science"), ("2^5 mod 7 = 4", "computer_science"), ("a = 17 % 5 = 2", "computer_science"),
    ("The remainder is 17 mod 5 = 2.", "mathematics_aa"), ("$17 \\bmod 5 = 2$", "mathematics_aa"), ("As a check, 17 mod 5 = 2.", "mathematics_ai"),
])
def test_correct_integer_remainders_and_quotients_hold(text, profile):
    """The independent test's false errors: '17 mod 5 = 2' was read '5 = 2' and failed (c = 5, r = 2). Read whole, every correct
    form holds, with no finding, and the check says it decides integer arithmetic."""
    checks, findings = decided(text, profile)
    assert [(k, st) for k, st, *_ in checks] == [("eq", "ENTAILED")], (text, checks)
    assert findings == [], findings
    assert "integer arithmetic:" in checks[0][4] and "exact mode" in checks[0][4]


@pytest.mark.parametrize("text, profile", [("17 mod 5 = 3", "computer_science"), ("17 div 5 = 4", "computer_science"), ("17 // 5 = 4", "computer_science"),
                                           ("17 % 5 = 3", "computer_science"), ("$17 \\bmod 5 = 3$", "mathematics_aa"), ("9 mod 2 = 0", "computer_science")])
def test_an_integer_slip_is_named(text, profile):
    assert statuses(text, profile) == [("eq", "COUNTEREXAMPLE")]


def test_integer_arithmetic_is_encoded_with_the_ir_s_integer_operators():
    clear_document_cache()
    for text, op in (("17 mod 5 = 2", "mod"), ("17 div 5 = 3", "idiv"), ("17 // 5 = 3", "idiv")):
        plan = build_checks(build_document(text, None, "computer_science"), report_id="r", request_id="q")
        [c_def] = [p for p in plan.checks[0].problem["premises"] if p["id"] == "C_DEF"]
        assert c_def["expr"]["right"] == {"op": "to_real", "arg": {"op": op, "left": {"op": "int", "value": "17"}, "right": {"op": "int", "value": "5"}}}, text


@pytest.mark.parametrize("text, why", [("(-7) mod 3 = 2", "negative"), ("7.5 mod 2 = 1.5", "not a whole number"), ("17 mod 0 = 2", "positive whole number")])
def test_an_integer_operation_the_encodings_do_not_decide_is_named_undecided(text, why):
    """Languages round a negative remainder differently, and a remainder of a decimal or by zero is no integer operation: each
    is ST-UNDEC-001 naming why, never a check."""
    checks, findings = decided(text, "computer_science")
    assert checks == [] and [c for c, _m in findings] == ["ST-UNDEC-001"] and why in findings[0][1], findings


def test_a_quotient_with_its_remainder_is_two_integer_checks():
    assert statuses("17 ÷ 5 = 3 remainder 2", "computer_science") == [("eq", "ENTAILED"), ("eq", "ENTAILED")]
    assert statuses("17 ÷ 5 = 3 rem 2", "computer_science") == [("eq", "ENTAILED"), ("eq", "ENTAILED")]
    assert statuses("17 ÷ 5 = 3 remainder 3", "computer_science") == [("eq", "ENTAILED"), ("eq", "COUNTEREXAMPLE")]
    assert statuses("17 ÷ 5 = 4 remainder 2", "computer_science") == [("eq", "COUNTEREXAMPLE"), ("eq", "ENTAILED")]


@pytest.mark.parametrize("text, status", [("17 ≡ 2 (mod 5)", "ENTAILED"), ("17 ≡ 2 mod 5", "ENTAILED"), ("22 ≡ 17 (mod 5)", "ENTAILED"),
                                          ("17 ≡ 3 (mod 5)", "COUNTEREXAMPLE")])
def test_a_congruence_is_an_equality_of_remainders(text, status):
    """'17 ≡ 2 (mod 5)' is 17 mod 5 = 2 mod 5, never the equality 17 = 2 (the bracket is no factor)."""
    assert statuses(text, "mathematics_aa") == [("eq", status)]


@pytest.mark.parametrize("text", ["Use the mod operator to find it.", "Python's divmod(17, 5) returns (3, 2).", "x mod 5", "The answer, 17 mod 5, is 2."])
def test_an_integer_word_outside_a_relation_between_operands_is_no_check(text):
    assert decided(text, "computer_science") == ([], [])


# ============================================================================================ verbal arithmetic, fragments, unread signs
@pytest.mark.parametrize("text, status", [("So 3 times 4 = 12.", "ENTAILED"), ("So 3 times 4 = 13.", "COUNTEREXAMPLE"), ("So 17 plus 5 = 22.", "ENTAILED"),
                                          ("So 17 plus 5 = 23.", "COUNTEREXAMPLE"), ("3 times 4 equals 12", "ENTAILED")])
def test_verbal_arithmetic_is_read_once_as_written(text, status):
    checks, findings = decided(text, "mathematics_aa")
    assert [(k, st) for k, st, *_ in checks] == [("eq", status)] and findings == []
    assert "times" in checks[0][4] or "plus" in checks[0][4]  # the verbal span, never its tail '4 = 12'


@pytest.mark.parametrize("text, word", [("The remainder when 17 is divided by 5 = 2.", "by"), ("20% of 50 = 10", "of"), ("the square root of 16 = 4", "of"),
                                        ("12 over 4 = 3", "over"), ("twice 4 = 8", "twice"), ("Divide by 5 = 2", "by"), ("mod 5 = 2", "mod")])
def test_a_relation_written_partly_in_words_is_named_unchecked(text, word):
    """Rule fragment: these were checked as '5 = 2', '4 = 3', '4 = 8' and failed (errors on correct work); each is now
    ST-PARSE-001 naming the word, and no check."""
    checks, findings = decided(text, "computer_science" if text.startswith("mod") else "mathematics_aa")
    assert checks == [] and [c for c, _m in findings] == ["ST-PARSE-001"], (text, checks, findings)
    assert f"('… {word}')" in findings[0][1] and "written partly in words" in findings[0][1]


@pytest.mark.parametrize("text", ["The value of 3 × 4 = 12.", "The sum of 2 + 3 = 5.", "A mean of 18 = 18", "The total is 5 + 3 = 8 so far."])
def test_a_whole_expression_after_a_word_is_still_checked(text):
    assert statuses(text, "mathematics_aa") == [("eq", "ENTAILED")] and codes(text, "mathematics_aa") == []


def test_a_relation_sign_no_span_reads_is_named_and_signs_between_words_are_not():
    """Rule unread-relation: '%' is the remainder in Computer Science only; elsewhere '17 % 5 = 2' is no maths the reader holds,
    so its relation sign is named (ST-PARSE-001), never silently unchecked. A sign between words, a doubled sign, an arrow and
    a bond glued between letters name no relation of values."""
    checks, findings = decided("As a check, 17 % 5 = 2.", "mathematics_aa")
    assert checks == [] and [c for c, _m in findings] == ["ST-PARSE-001"] and "a relation sign in s1.1 that the branch read no relation at" in findings[0][1]
    for text, profile in (("Corrected count rate = measured count rate − background", "physics"), ("Use the comparison operators (== and <).", "computer_science"),
                          ("The bond O=O is strong.", "chemistry"), ("x -> y => z", "computer_science")):
        assert "ST-PARSE-001" not in codes(text, profile), text


# ============================================================================================ questions
@pytest.mark.parametrize("text, kind, status, decided_rel", [("Is 67 = 67? No.", "cmp", "COUNTEREXAMPLE", "67 ≠ 67"), ("Is 38 = 67? No.", "cmp", "ENTAILED", "38 ≠ 67"),
                                                         ("Is 38 = 67? Yes.", "eq", "COUNTEREXAMPLE", "38 = 67"), ("Is 38 < 67? Yes.", "cmp", "ENTAILED", "38 < 67"),
                                                         ("Is 38 < 67? No.", "cmp", "COUNTEREXAMPLE", "38 ≥ 67")])
def test_a_relation_asked_and_answered_is_checked_as_answered(text, kind, status, decided_rel):
    checks, findings = decided(text, "computer_science")
    assert [(k, st) for k, st, *_ in checks] == [(kind, status)] and findings == []
    assert f"(the relation decided: {decided_rel}) (rule question)" in checks[0][4]


def test_a_relation_asked_with_no_answer_claims_nothing():
    assert decided("Is 38 = 67?", "computer_science") == ([], [])


# ============================================================================================ Givens
@pytest.mark.parametrize("line, status", [
    ("Given: P = 4000, r = 3.9%.", ["ENTAILED", "COUNTEREXAMPLE"]), ("Given: P = 4000, r = 3.6%.", ["ENTAILED", "ENTAILED"]),
    ("Given: P = 5000 euros.", ["COUNTEREXAMPLE"]), ("Given: P = 4000 euros.", ["ENTAILED"]),
    ("Given: t = 6 years.", ["COUNTEREXAMPLE"]), ("Given: t = 5 years.", ["ENTAILED"]),
    ("Given: the nominal annual rate is r = 3.9 per cent.", ["COUNTEREXAMPLE"]), ("Given: the nominal annual rate is r = 3.6 per cent.", ["ENTAILED"]),
    # STEM repair 11 (rule given-data): the request's 3.6% is data, taken as written, so a Given one unit off in its last digit fails: |3.7 − 3.6|
    # > h(3.7) (before, R7's inclusive band h(3.6) + h(3.7) had held it)
    ("Given: r = 3.8%.", ["COUNTEREXAMPLE"]), ("Given: r = 3.7%.", ["COUNTEREXAMPLE"]), ("Given: r = 3.60%.", ["ENTAILED"]),
    ("Given: P = 4000.", ["ENTAILED"]), ("Given: k = 3", ["ENTAILED"]),
])
def test_a_given_is_set_against_the_request_s_values_of_its_kind(line, status):
    """The independent test's Givens contradicting the task (3.9% for 3.6%, 5000 euros for 4000, 6 years for 5, 3.9 per cent)
    had no check and no ST code; each is now a giv check at warning severity naming its kind (rule given-kinds), and the same
    line written as the task states it holds."""
    checks, findings = decided(line, "mathematics_ai", request=MI_Q)
    assert [st for k, st, *_ in checks if k == "giv"] == status and findings == [], (line, checks, findings)
    assert all(sev == "warning" and "(rule given-kinds)" in d for k, _st, sev, _f, d in checks if k == "giv")


def test_a_bare_given_the_request_does_not_state_is_named_unchecked_never_failed():
    """A bare number may be a conversion (0.036 for 3.6%, 12 for "monthly"), so it is never failed against the request's other
    numbers: one ST-UNDEC-003 per statement names each such Given; the request's own 4000 and 5 hold."""
    checks, findings = decided("Given: P = 4000, r = 0.036, n = 12, t = 5.", "mathematics_ai", request=MI_Q)
    assert [(k, st) for k, st, *_ in checks] == [("giv", "ENTAILED"), ("giv", "ENTAILED")]
    assert findings == [("ST-UNDEC-003", "the Given values r = 0.036 (a bare number the request does not state) and n = 12 (a bare number the request does "
                                         "not state) in s1.1 could not be set against the request: they are not checked against the request")]
    checks, findings = decided("Given: P = 5000.", "mathematics_ai", request=MI_Q)
    assert checks == [] and [c for c, _m in findings] == ["ST-UNDEC-003"]


def test_a_given_of_a_kind_the_request_states_no_value_of_is_named_unchecked():
    checks, findings = decided("Given: t = 5.0 s.", request=PH_Q)
    assert checks == [] and findings == [("ST-UNDEC-003", "the Given value t = 5.0 s (the request states no quantity in s, and no supplied table names it) in "
                                                          "s1.1 could not be set against the request: it is not checked against the request")]
    assert [c for c, _m in decided("Given: n = 2 resistors", request=PH_Q)[1]] == ["ST-UNDEC-003"]
    assert [c for c, _m in decided("Given: g = 9.71 m s⁻²", request=PH_Q)[1]] == ["ST-UNDEC-003"]  # not the booklet's g


@pytest.mark.parametrize("line", ["Given: u = 0", "Given: g = 9.81 m s⁻²"])
def test_zero_and_a_booklet_constant_are_neither_checked_nor_named(line):
    """A zero states a condition the request gives in words ('dropped from rest'), and g = 9.81 m s⁻² is the data booklet's."""
    assert decided(line, request=PH_Q) == ([], [])


@pytest.mark.parametrize("line, status", [("Given:\n- P = 4000\n- r = 3.9%", ["ENTAILED", "COUNTEREXAMPLE"]), ("Data: P = 5000 euros", ["COUNTEREXAMPLE"]),
                                          ("We know that t = 6 years.", ["COUNTEREXAMPLE"]), ("Given that P = 5000 euros, find A.", ["COUNTEREXAMPLE"]),
                                          ("Given: P = 4,000 euros", ["ENTAILED"]), ("Given: P = 5,000 euros", ["COUNTEREXAMPLE"])])
def test_every_form_of_a_given_statement_is_read(line, status):
    """A Given statement begins 'Given', 'Data', 'Known' or 'We know', or is an item of the list a line 'Given:' opens."""
    checks, findings = decided(line, "mathematics_ai", request=MI_Q)
    assert [st for k, st, *_ in checks if k == "giv"] == status and findings == [], (line, checks, findings)


def test_a_given_that_may_be_written_with_a_thousands_space_is_named_never_read_in_part():
    """'4 000' may be a thousands group (it was read as P = 4): ST-PARSE-001, never set against the request in part."""
    checks, findings = decided("Given: P = 4 000 euros", "mathematics_ai", request=MI_Q)
    assert checks == [] and findings == [("ST-PARSE-001", "the Given value of P ('4 000') in s1.1 may be a numeral written with a thousands space; it is "
                                                          "not read, and it is not checked against the request")]


@pytest.mark.parametrize("text", ["Given: P = €4000", "After 10 years the investment is worth $7052.99, so the interest earned is $7052.99 − $5000 = $2052.99."])
def test_an_amount_after_a_currency_sign_is_neither_read_nor_named(text):
    """An amount written after a currency sign is no number the reader holds (pack D31 says so): a Given or a relation written with
    one is neither checked nor named. Naming it raised ST-PARSE-001 on the corpus's correct stem-math-019, so it is not done."""
    assert decided(text, "mathematics_ai", request=MI_Q) == ([], [])


def test_with_no_request_no_given_is_set_against_anything():
    assert decided("Given: P = 5000.", "mathematics_ai") == ([], [])


@pytest.mark.parametrize("line, status", [("Given: R1 = 4.0 Ω, R2 = 6.0 Ω, r = 0.50 Ω, ε = 12 V", ["ENTAILED"] * 4), ("The battery's emf is 9.0 V.", ["COUNTEREXAMPLE"]),
                                          ("The battery's emf is 12 V.", ["ENTAILED"])])
def test_a_given_with_a_unit_and_a_value_the_prose_names_are_set_against_the_request(line, status):
    """Rule named-given: the prose names the quantity ('The battery's emf is 9.0 V' for 'a battery of emf 12 V')."""
    checks, findings = decided(line, request=PH_Q)
    assert [st for k, st, *_ in checks if k == "giv"] == status and findings == []


@pytest.mark.parametrize("value, status", [("3.5", "COUNTEREXAMPLE"), ("3.8", "ENTAILED")])
def test_a_given_naming_a_row_and_a_column_of_the_supplied_table_is_set_against_that_cell(value, status):
    checks, findings = decided(f"Given: dissolved oxygen at C = {value} mg dm⁻³.", "ess", request=SPEC["ess-t13"]["question"], data=_data("ess-t13"))
    assert [(k, st) for k, st, *_ in checks] == [("giv", status)] and findings == []
    assert "rule table-data" in checks[0][4] or status == "ENTAILED"


# ============================================================================================ table operands
def test_a_value_taken_from_another_row_of_the_supplied_table_is_named():
    """'(9.6 − 6.1) ÷ 9.6 × 100' for the decrease from A to C took site B's 6.1, the arithmetic right: the table-operands check
    of 6.1 against the rows the part's question names (A: 9.6, C: 3.8) fails; site C's 3.8 holds."""
    q, data = SPEC["ess-t13"]["question"], _data("ess-t13")
    wrong = decided("(a) Percentage decrease = (9.6 − 6.1) ÷ 9.6 × 100 = 36.5% decrease", "ess", request=q, data=data)[0]
    right = decided("(a) Percentage decrease = (9.6 − 3.8) ÷ 9.6 × 100 = 60.4% decrease", "ess", request=q, data=data)[0]
    assert [(k, st) for k, st, *_ in wrong] == [("eq", "ENTAILED"), ("giv", "ENTAILED"), ("giv", "COUNTEREXAMPLE")]
    assert [(k, st) for k, st, *_ in right] == [("eq", "ENTAILED"), ("giv", "ENTAILED"), ("giv", "ENTAILED")]
    assert all(sev == "warning" and "(rule table-operands)" in d and "A: 9.6, C: 3.8" in d for k, _st, sev, _f, d in wrong if k == "giv")
    line = "(a) From A to C the fall is 9.6 − 6.1 = 3.5 mg dm⁻³."
    got = decided(line, "ess", request=q, data=data)[0]
    assert [(k, st) for k, st, *_ in got] == [("giv", "ENTAILED"), ("eq", "ENTAILED"), ("giv", "COUNTEREXAMPLE")]  # in the order of the text
    assert all("against the rows the line names (A: 9.6, C: 3.8)" in d for k, _st, _sev, _f, d in got if k == "giv")
    # the line names its rows, but no column: the table has four columns of numbers, so nothing is read
    assert statuses("From A to C the fall is 9.6 − 6.1 = 3.5 mg dm⁻³.", "ess", request=q, data=data) == [("eq", "ENTAILED")]


def test_a_line_over_another_number_of_cells_than_the_rows_named_is_another_computation():
    """The mean of three rows in a part whose question names two (20 °C and 30 °C) is not read as those rows' values: only the
    percentage line's two operands are set against them. Another row's value in the percentage line (58 for 40) is named."""
    q, data = SPEC["bi-t13"]["question"], _data("bi-t13")
    got = decided("(a) Percentage change = (80 − 40) ÷ 40 × 100 = 100%\n\nMean uptake = (18 + 27 + 40)/3 = 28.3", "biology", request=q, data=data)[0]
    assert [(k, st) for k, st, *_ in got] == [("eq", "ENTAILED"), ("giv", "ENTAILED"), ("giv", "ENTAILED"), ("eq", "ENTAILED")]
    assert [d.split("'")[1] for k, _st, _sev, _f, d in got if k == "giv"] == ["80", "40"]
    wrong = decided("(a) Percentage change = (80 − 58) ÷ 58 × 100 = 37.9%", "biology", request=q, data=data)[0]
    assert [(k, st) for k, st, *_ in wrong] == [("eq", "ENTAILED"), ("giv", "ENTAILED"), ("giv", "COUNTEREXAMPLE")]


# ============================================================================================ restated bindings and exact carries
def test_a_value_taken_after_so_is_set_against_the_chain_before_it():
    """The relay plant '(so C(8) = 820)' after '820 − 20 = 800 ± 16 counts min⁻¹': rule restated-binding sets 820 against the
    chain's central value 800 (a warning: 'so' pairs them), and 800 holds."""
    for value, status in (("820", "COUNTEREXAMPLE"), ("800", "ENTAILED")):
        checks, findings = decided(f"“t = 8 h: 820 − 20 = 800 ± 16 counts min⁻¹” (so C(8) = {value})", "mathematics_aa", request="Q")
        assert [(k, st) for k, st, *_ in checks] == [("eq", "ENTAILED"), ("res", status)] and findings == []
        assert checks[1][2] == "warning" and "(rule restated-binding)" in checks[1][4] and "rule exact-carry" in checks[1][4]


@pytest.mark.parametrize("text, kinds", [("1/R = 1/4.0 + 1/6.0 = 0.417 Ω⁻¹, so R = 2.4 Ω", ["eq", "sol", "alg"]),
                                         ("k = ln 2 / 8.0 h = 0.087 h⁻¹, so k = 0.087 h⁻¹", ["eq"])])
def test_a_symbol_the_chain_solves_for_or_computes_is_no_restated_binding(text, kinds):
    assert [k for k, _st in statuses(text, request="Q")] == kinds


@pytest.mark.parametrize("text, status", [("Check: 100 counts min⁻¹ + 20 counts min⁻¹ = 130 counts min⁻¹.", "COUNTEREXAMPLE"),
                                          ("Check: 100 counts min⁻¹ + 20 counts min⁻¹ = 120 counts min⁻¹.", "ENTAILED"),
                                          ("A measured rate would be 100 + 20 = 130 counts min⁻¹", "COUNTEREXAMPLE"),
                                          ("A measured rate would be 100 + 20 = 120 counts min⁻¹", "ENTAILED")])
def test_a_sum_of_count_rates_is_decided_as_written(text, status):
    """The slip of 10 in a sum written with units passed as SATISFIABLE (Form S over rounding intervals), and the same sum in
    prose had no check: both are decided in Form E now."""
    checks, findings = decided(text, request="Q")
    assert [(k, st, form) for k, st, _sev, form, _d in checks] == [("eq", status, "E")] and findings == []


# ============================================================================================ asides and premise cues
@pytest.mark.parametrize("text, checks_", [("The fall is greatest at C (2.0 km = 200 m).", [("cnv", "COUNTEREXAMPLE")]),
                                           ("The fall is greatest at C (2.0 km = 2000 m).", [("cnv", "ENTAILED")]), ("The fall is greatest at C (2.0 km).", [])])
def test_a_conversion_in_brackets_after_a_word_is_checked(text, checks_):
    assert statuses(text, "ess", request="Q") == checks_ and codes(text, "ess", request="Q") == []


@pytest.mark.parametrize("text, checks_", [("From c = n/V, n = c/V = 0.10 / 0.0500 = 2.0.", [("alg", "COUNTEREXAMPLE"), ("eq", "ENTAILED")]),
                                           ("From c = n/V, n = cV = 0.10 × 0.0500 = 0.0050.", [("alg", "ENTAILED"), ("eq", "ENTAILED")]),
                                           ("Since c = n/V, n = cV = 0.10 × 0.0500 = 0.0050.", [("alg", "ENTAILED"), ("eq", "ENTAILED")])])
def test_a_relation_introduced_by_a_premise_word_is_a_step_from_it(text, checks_):
    """Rule premise-cue: 'From c = n/V, n = c/V' is a rearrangement of the relation the premise word introduces."""
    assert statuses(text, "chemistry", request="Q") == checks_


# ============================================================================================ the codes and the recorded answers
def test_st_undec_003_is_a_warning_of_the_code_table():
    assert ST_SEVERITY["ST-UNDEC-003"] == "warning" and ST_SEVERITY["ST-PARSE-001"] == "warning"


_RULES = ("(rule table-operands)", "(rule restated-binding)", "(rule given-kinds)", "rule named-given", "(rule question)", "integer arithmetic:")


@pytest.mark.parametrize("tid, profile", [("ph-t13", "physics"), ("ph-p7b", "physics"), ("maa-t13", "mathematics_aa"), ("maa-p7b", "mathematics_aa"),
                                          ("mai-t13", "mathematics_ai"), ("bi-t13", "biology"), ("ess-t13", "ess"), ("ch-t13", "chemistry"),
                                          ("cs-t13", "computer_science")])
def test_on_the_recorded_answers_every_new_reading_holds_and_names_nothing(tid, profile):
    """The clean control on genuine work: on every recorded STEM answer of round 7 each check a repair-2 rule plans holds, and no
    ST-UNDEC-003 or ST-PARSE-001 is raised."""
    it = SPEC[tid]
    checks, findings = decided(it["response_text"], profile, request=it["question"], data=_data(tid))
    new = [(k, st) for k, st, _sev, _f, d in checks if any(r in d for r in _RULES)]
    assert all(st == "ENTAILED" for _k, st in new), new
    assert not {"ST-UNDEC-003", "ST-PARSE-001"} & {c for c, _m in findings}, findings
