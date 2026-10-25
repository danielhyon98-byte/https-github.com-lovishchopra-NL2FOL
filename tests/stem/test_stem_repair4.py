"""STEM repair 4: the fourth independent test of the STEM completion found two false errors on correct work and five fault forms
the STEM front end did not read (the eighth problem, the contained run's adjudication gate, is tested with the overseer). Each
is fixed at its cause in the STEM front end, for its whole class, and every new reading has a clean control (correct working is
never flagged):

* rule ``boolean-values``: a Boolean expression evaluated under the values its statement gives its inputs ('With A = 1 and B = 0,
  NOT A OR B = 0.') was read as an identity over every assignment and failed (INT-SUBJ-001 on correct work); it is now decided
  under those values (an input given none stays free), with the values set up by an earlier statement of the paragraph that sets
  them up ('Let …', 'With …', a colon, a statement of nothing but the values, 'Then …' right after), or by a setup ending with a
  colon over the Boolean display lines after it; a statement that says more than the values sets nothing up, and a relation no
  statement gives a value stays an identity;
* rule ``changed-value``: a substitution in a later part that takes the value the prose gives a symbol at the end of a change it
  states ('the current from the cell falls, from 4.1 A to 2.7 A') was set against the symbol's earlier values only and failed
  (INT-SUBJ-001 on correct work); it may now take that value when it stands after the change, in its statement or in its part,
  never in an earlier part;
* rule ``given-uncertainty`` for '±' and '%': a Given uncertainty written '±3%' (or '+/-3%') had neither its check nor an ST code;
  it is set against the uncertainties the request and its supplied texts state, and the uncertainty written with a Given value
  ('T = 20.0 ± 0.5 °C', '1620 ± 2%') is too; a Given with its uncertainty after the part's formula of its symbol is a Given, never
  the formula evaluated; a Given in a maths span the branch cannot read whole is never read in part (its ST-PARSE code names it);
* rule ``rounding-cue`` with a unit word: a result restated after ', so' with a word after the number ('so 4775 euros to the
  nearest euro', 'so 5903 to the nearest euro', 'so 4775 euros.', 'to the nearest ten euros') was never read; it is checked when
  the word names the value's unit (the word the task writes after its numbers, or the value's unit spelled out), and a rounding
  may name the whole unit, a place with the unit after it, or a part of the unit ('to the nearest cent' for euros, 'to the
  nearest penny' for pounds, 'to the nearest milliampere' for a value in A);
* rule ``row-value``: a value a statement or the prose gives at a lettered row of a supplied table ('Dissolved oxygen at site C =
  3.8 g dm⁻³.', 'At site C, dissolved oxygen is …', '… where it reaches 3.8 g dm⁻³') was never set against the table; it is, in SI,
  when the row and one column are read (a column of counts by the words before its 'per');
* rule ``exact-carry`` for exact working: a written number carrying an exact result ('T = ln 2 ÷ ((ln 2)/8) = 8') ranged over a
  rounding interval, which passed a 12% slip ('8 ln 2 ÷ ln(1568/816) ≈ 9.5 h');
* rules ``stated-uncertainty`` and ``operand-precision``: an uncertainty written with a corrected value against the rule the answer
  states for it ('2% of the measured value'), and τ for '=' bounded by what the rounding of the written operands can move the
  computed value, so a slip under 1/100 that their rounding cannot explain fails ('4000 × 1.036³ = 4467.74').
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

R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))
SPEC: dict[str, dict] = R7["specialists"]
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
PROFILE = {"ph-t13": "physics", "ph-p7b": "physics", "maa-t13": "mathematics_aa", "maa-p7b": "mathematics_aa", "mai-t13": "mathematics_ai",
           "bi-t13": "biology", "ess-t13": "ess", "ch-t13": "chemistry", "cs-t13": "computer_science"}
#: what a check expects when it holds, per relation kind (a Boolean check is decided over its negation)
HOLDS = {"bool": "UNSATISFIABLE"}


def _data(tid: str) -> tuple[str, ...]:
    return tuple(t["text"] for t in SPEC[tid].get("supplied_texts") or [])


def task(tid: str, text: str):
    """(checks as (kind, status, severity, description), findings as (code, severity, message)) for ``text`` answering ``tid``."""
    clear_document_cache()
    doc = build_document(text, SPEC[tid]["question"], PROFILE[tid], **({"data": _data(tid)} if _data(tid) else {}))
    plan = build_checks(doc, report_id="r", request_id="q")
    checks = [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy)).status.value,
               pc.failure_severity, pc.description) for pc in plan.checks]
    return checks, [(f.code, f.severity, f.message) for f in list(doc.findings) + list(plan.findings)]


def holds(check) -> bool:
    kind, status = check[0], check[1]
    return status == HOLDS.get(kind, "ENTAILED") or (kind != "bool" and status == "SATISFIABLE")


def new(tid: str, text: str):
    """The checks and findings ``text`` has beyond the recorded answer's (by kind, status, severity and statement head)."""
    def key(c):
        return (c[0], c[1], c[2], c[3].split(" [claims")[0])
    base_c, base_f = task(tid, SPEC[tid]["response_text"])
    got_c, got_f = task(tid, text)
    bc = [key(c) for c in base_c]
    out_c = []
    for c in got_c:
        if key(c) in bc:
            bc.remove(key(c))
        else:
            out_c.append(c)
    bf = [(c, s, m.split(" in s")[0]) for c, s, m in base_f]
    out_f = []
    for c, s, m in got_f:
        k = (c, s, m.split(" in s")[0])
        if k in bf:
            bf.remove(k)
        else:
            out_f.append((c, s, m))
    return out_c, out_f


def before(tid: str, anchor: str, line: str, sep: str = "\n\n") -> str:
    text = SPEC[tid]["response_text"]
    assert text.count(anchor) == 1, anchor
    return text.replace(anchor, line + sep + anchor)


def after(tid: str, anchor: str, line: str, sep: str = "\n") -> str:
    text = SPEC[tid]["response_text"]
    assert text.count(anchor) == 1, anchor
    return text.replace(anchor, anchor + sep + line)


def replaced(tid: str, old: str, new_text: str) -> str:
    text = SPEC[tid]["response_text"]
    assert text.count(old) == 1, old
    return text.replace(old, new_text)


def failing(checks) -> list:
    return [c for c in checks if not holds(c)]


# ============================================================================================ rule boolean-values
CS = "Next step: trace"


@pytest.mark.parametrize("line", [
    # the independent test's correct lines (each was INT-SUBJ-001)
    "With A = 1 and B = 0, NOT A OR B = 0.", "When A = 0 and B = 1, A AND B = 0.", "If A = 1, then NOT A = 0.", "For A = 1 and B = 1, A XOR B = 0.",
    "With A = 1 and B = 0, A OR B = 1.",
    # the values after the relation, in an earlier statement that sets them up, across a colon, symbols for the operators
    "NOT A OR B = 0 when A = 1 and B = 0.", "Let A = 1 and B = 0. Then NOT A OR B = 0.", "Inputs A = 1, B = 0:\n\nNOT A OR B = 0.",
    "Test case: A = 1, B = 0. Expected output: NOT A OR B = 0.", "A = 1 and B = 0. NOT A OR B = 0.", "Here A = 1 and B = 0. NOT A OR B = 0.",
    "Now set A = 0. A OR B = B.", "With A = 1 and B = 0, ¬A ∨ B = 0.",
    # an input given no value stays free: the relation must hold for each of its values
    "With A = 1, A OR B = 1.",
    # a defined name given a value under stated inputs is its definition evaluated there
    "Let X = A AND B. With A = 1 and B = 1, X = 1.",
])
def test_a_correct_boolean_evaluation_under_stated_values_holds(line):
    checks, findings = new("cs-t13", before("cs-t13", CS, line))
    assert [c[0] for c in checks] == ["bool"], checks
    assert checks[0][1] == "UNSATISFIABLE" and "the Boolean evaluation" in checks[0][3] and "(rule boolean-values)" in checks[0][3], checks
    assert findings == [], findings


@pytest.mark.parametrize("line", [
    "With A = 1 and B = 0, NOT A OR B = 1.", "When A = 1 and B = 1, A AND B = 0.", "If A = 1, then NOT A = 1.", "For A = 1 and B = 1, A XOR B = 1.",
    "NOT A OR B = 1 when A = 1 and B = 0.", "Let A = 1 and B = 0. Then NOT A OR B = 1.", "Inputs A = 1, B = 0:\n\nNOT A OR B = 1.",
    "With A = 0, A OR B = 1.", "Let X = A AND B. With A = 1 and B = 0, X = 1.", "With A = 1 and B = 0, ¬A ∨ B = 1.",
])
def test_a_wrong_boolean_evaluation_under_stated_values_fails(line):
    checks, _findings = new("cs-t13", before("cs-t13", CS, line))
    assert [(c[0], c[1], c[2]) for c in checks] == [("bool", "SATISFIABLE", "error")], checks
    assert "(rule boolean-values)" in checks[0][3]


def test_two_evaluations_in_one_statement_each_take_their_own_values():
    checks, _f = new("cs-t13", before("cs-t13", CS, "When A = 0, NOT A = 1, and when A = 1, NOT A = 0."))
    assert [(c[0], c[1]) for c in checks] == [("bool", "UNSATISFIABLE")] * 2
    checks, _f = new("cs-t13", before("cs-t13", CS, "When A = 0, NOT A = 1, and when A = 1, NOT A = 1."))
    assert [(c[0], c[1]) for c in checks] == [("bool", "UNSATISFIABLE"), ("bool", "SATISFIABLE")]


@pytest.mark.parametrize("line, status", [
    # no statement gives a value: an identity, as before
    ("By absorption, A OR (A AND B) = A.", "UNSATISFIABLE"), ("By absorption, A OR (A AND B) = B.", "SATISFIABLE"),
    ("For every A, A OR NOT A = 1.", "UNSATISFIABLE"),
    # a statement that says more than the values sets nothing up: the relation after it stays an identity, so a wrong one fails
    ("The register holds A = 1 and B = 1 after the reset. A AND B = A.", "SATISFIABLE"),
    ("A = 0 is the reset state. A AND B = A.", "SATISFIABLE"),
    ("A = 1 is the flag. NOT A OR A = 1.", "UNSATISFIABLE"),
])
def test_a_relation_no_statement_gives_values_stays_an_identity(line, status):
    checks, _f = new("cs-t13", before("cs-t13", CS, line))
    assert [(c[0], c[1]) for c in checks] == [("bool", status)], checks
    assert "the Boolean identity" in checks[0][3] and "(rule boolean-values)" not in checks[0][3]


def test_an_evaluation_in_words_and_a_truth_table_are_unchanged():
    assert new("cs-t13", before("cs-t13", CS, "With A = 1 and B = 0, the condition NOT A OR B is 0, so the loop stops.")) == ([], [])
    table = "| A | B | A XOR B |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 1 |\n| 1 | 0 | 1 |\n| 1 | 1 | {r} |"
    checks, _f = new("cs-t13", before("cs-t13", CS, table.format(r=0)))
    assert [(c[0], c[1]) for c in checks] == [("tt", "ENTAILED")]
    checks, _f = new("cs-t13", before("cs-t13", CS, table.format(r=1)))
    assert [(c[0], c[1]) for c in checks] == [("tt", "COUNTEREXAMPLE")]


# ============================================================================================ rule changed-value
PH_END = "from 9.9 V to 10.7 V."


@pytest.mark.parametrize("text", [
    after("ph-t13", PH_END, "V = 12 V − 2.7 A × 0.50 Ω = 10.65 V"),
    after("ph-t13", PH_END, "V = 12 V − 2.67 A × 0.50 Ω = 10.67 V"),
    after("ph-t13", PH_END, "V = 12 V − 2.67 A × 0.50 Ω = 10.665 V, so 10.7 V to three significant figures."),
    # in the change's own statement, and earlier in its part
    replaced("ph-t13", "From ε = I(R + r), the current from the cell falls, from 4.1 A to 2.7 A.",
             "V = 12 V − 2.7 A × 0.50 Ω = 10.65 V, because the current from the cell falls, from 4.1 A to 2.7 A."),
    replaced("ph-t13", "With the 6.0 Ω resistor removed, only the 4.0 Ω resistor remains.",
             "With the 6.0 Ω resistor removed, only the 4.0 Ω resistor remains. V = 12 V − 2.7 A × 0.50 Ω = 10.65 V."),
    # the other ways a change states its end
    replaced("ph-t13", "the current from the cell falls, from 4.1 A to 2.7 A.", "the current from the cell falls to 2.7 A.\nV = 12 V − 2.7 A × 0.50 Ω = 10.65 V."),
    replaced("ph-t13", "the current from the cell falls, from 4.1 A to 2.7 A.", "the current from the cell becomes 2.7 A.\nV = 12 V − 2.7 A × 0.50 Ω = 10.65 V."),
    replaced("ph-t13", "the current from the cell falls, from 4.1 A to 2.7 A.", "the current from the cell is now 2.7 A.\nV = 12 V − 2.7 A × 0.50 Ω = 10.65 V."),
])
def test_a_substitution_of_the_value_a_stated_change_ends_at_holds(text):
    checks, findings = new("ph-t13", text)
    subs = [c for c in checks if c[0] == "sub"]
    assert subs and all(c[1] == "ENTAILED" for c in subs), checks
    assert failing(checks) == [] and not [f for f in findings if f[1] == "error"], (checks, findings)
    assert any("(rule changed-value)" in c[3] for c in subs)


@pytest.mark.parametrize("text", [
    after("ph-t13", PH_END, "V = 12 V − 3.7 A × 0.50 Ω = 10.15 V"),           # a current the answer never states
    replaced("ph-t13", "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "V = 12 V − (2.7 A × 0.50 Ω) = 10.65 V"),  # part (c) takes part (e)'s current
])
def test_a_value_no_binding_and_no_earlier_change_gives_still_fails(text):
    checks, _f = new("ph-t13", text)
    assert ("sub", "COUNTEREXAMPLE", "error") in [(c[0], c[1], c[2]) for c in checks], checks


def test_the_arithmetic_of_a_line_that_takes_the_new_value_is_still_checked():
    checks, _f = new("ph-t13", after("ph-t13", PH_END, "V = 12 V − 2.7 A × 0.50 Ω = 11.65 V"))
    assert ("eq", "COUNTEREXAMPLE") in [(c[0], c[1]) for c in checks] and ("sub", "ENTAILED") in [(c[0], c[1]) for c in checks]


# ============================================================================================ rule given-uncertainty: '±', '%' and '+/-'
PB_END = "Both effects make the count rate smaller than the activity."
PB_A = "(a) [2]\nCorrected count rate"


@pytest.mark.parametrize("text, status", [
    (after("ph-p7b", PB_END, "Given: count rate uncertainty = ±3%.", "\n\n"), "COUNTEREXAMPLE"),
    (after("ph-p7b", PB_END, "Given: count rate uncertainty = ±2%.", "\n\n"), "ENTAILED"),
    (before("ph-p7b", PB_A, "Given: uncertainty in each measured count rate = ±3%."), "COUNTEREXAMPLE"),
    (before("ph-p7b", PB_A, "Given: uncertainty in each measured count rate = ±2%."), "ENTAILED"),
    (after("ph-p7b", PB_END, "Given: count rate uncertainty = +/-3%.", "\n\n"), "COUNTEREXAMPLE"),
    (after("ph-p7b", PB_END, "Given: count rate uncertainty = +/-2%.", "\n\n"), "ENTAILED"),
    (after("ch-t13", "so I cannot give one yet.", "Given: stopwatch uncertainty = ±0.05 s.", "\n\n"), "COUNTEREXAMPLE"),
    (after("ch-t13", "so I cannot give one yet.", "Given: stopwatch uncertainty = ±0.01 s.", "\n\n"), "ENTAILED"),
])
def test_a_given_uncertainty_written_with_plus_minus_is_set_against_the_stated_uncertainty(text, status):
    tid = "ch-t13" if "stopwatch" in text else "ph-p7b"
    checks, findings = new(tid, text)
    assert [(c[0], c[1], c[2]) for c in checks] == [("giv", status, "warning")], checks
    assert "(rule given-uncertainty)" in checks[0][3] and findings == []


@pytest.mark.parametrize("line, statuses", [
    ("Given: count rate at t = 0 h = 1620 ± 2%.", ["ENTAILED", "ENTAILED"]),
    ("Given: count rate at t = 0 h = 1620 counts min⁻¹ ± 2%.", ["ENTAILED", "ENTAILED"]),
    ("Given: count rate at t = 0 h = 1620 counts min⁻¹ ± 3%.", ["ENTAILED", "COUNTEREXAMPLE"]),
])
def test_a_given_value_with_its_relative_uncertainty_is_read_at_both(line, statuses):
    checks, findings = new("ph-p7b", before("ph-p7b", PB_A, line))
    assert [(c[0], c[1]) for c in checks] == [("giv", s) for s in statuses] and findings == [], (checks, findings)
    assert "(rule given-uncertainty)" in checks[1][3]


def test_a_given_with_its_uncertainty_after_the_part_s_formula_is_a_given():
    """'Given: ε = 12 ± 0.1 V.' after part (e)'s 'ε = I(R + r)' was the formula evaluated at it: no stem_given check and no ST code."""
    checks, findings = new("ph-t13", after("ph-t13", PH_END, "Given: ε = 12 ± 0.1 V.", "\n\n"))
    assert [(c[0], c[1]) for c in checks] == [("giv", "ENTAILED")] and findings == [], (checks, findings)
    checks, _f = new("ph-t13", after("ph-t13", PH_END, "Given: ε = 9.0 ± 0.1 V.", "\n\n"))
    assert [(c[0], c[1]) for c in checks] == [("giv", "COUNTEREXAMPLE")], checks


def test_a_given_in_a_span_the_branch_cannot_read_whole_is_never_read_in_part():
    """'1620 ± 2% counts min⁻¹' (a unit after a per cent sign) is outside the grammar: its condition 't = 0 h' had been read as a
    Given and failed against the request's t = 32 h. Now its ST-PARSE-001 names the statement and nothing of it is checked."""
    checks, findings = new("ph-p7b", before("ph-p7b", PB_A, "Given: count rate at t = 0 h = 1620 ± 2% counts min⁻¹."))
    assert checks == [] and "ST-PARSE-001" in [f[0] for f in findings], (checks, findings)


def test_plus_minus_in_ascii_is_read_only_before_a_number():
    checks, _f = new("ph-p7b", replaced("ph-p7b", "t = 4 h: 1151 − 20 = 1131 ± 23", "t = 4 h: 1151 − 20 = 1131 +/- 23"))
    assert failing(checks) == [] and ("eq", "ENTAILED") in [(c[0], c[1]) for c in checks]
    assert new("cs-t13", before("cs-t13", CS, "The +/- buttons change the step size.")) == ([], [])


def test_the_uncertainty_written_with_a_given_value_is_checked_when_one_of_its_kind_is_stated():
    checks, _f = new("ch-t13", after("ch-t13", "so I cannot give one yet.", "Given: T = 20.0 ± 0.2 °C.", "\n\n"))
    assert [(c[0], c[1]) for c in checks] == [("giv", "ENTAILED"), ("giv", "COUNTEREXAMPLE")]
    assert "the uncertainty of the Given value of T, written with it" in checks[1][3]
    checks, findings = new("ph-t13", after("ph-t13", PH_END, "Given: uncertainty in the emf = ±2%.", "\n\n"))
    assert checks == [] and [f[0] for f in findings] == ["ST-UNDEC-003"]  # no uncertainty in per cent is stated: named


# ============================================================================================ rule rounding-cue with a unit word
MI = "Next step: rework (a)"
MI_B = "$4000(1.036)^{11} = 5902.25$ and"


@pytest.mark.parametrize("text, value, status", [
    (before("mai-t13", MI, "Check: 4000 × 1.036⁵ = 4773.74, so 4775 euros to the nearest euro."), "4775", "COUNTEREXAMPLE"),
    (before("mai-t13", MI, "Check: 4000 × 1.036⁵ = 4773.74, so 4774 euros to the nearest euro."), "4774", "ENTAILED"),
    (replaced("mai-t13", MI_B, "$4000(1.036)^{11} = 5902.25$, so 5903 euros to the nearest euro, and"), "5903", "COUNTEREXAMPLE"),
    (replaced("mai-t13", MI_B, "$4000(1.036)^{11} = 5902.25$, so 5902 euros to the nearest euro, and"), "5902", "ENTAILED"),
    (replaced("mai-t13", MI_B, "$4000(1.036)^{11} = 5902.25$, so 5903 to the nearest euro, and"), "5903", "COUNTEREXAMPLE"),
    (replaced("mai-t13", MI_B, "$4000(1.036)^{11} = 5902.25$, so 5902 to the nearest euro, and"), "5902", "ENTAILED"),
    (before("mai-t13", MI, "Check: 4000 × 1.036⁵ = 4773.74, so 4775 euros."), "4775", "COUNTEREXAMPLE"),
    (before("mai-t13", MI, "Check: 4000 × 1.036⁵ = 4773.74, so 4774 euros."), "4774", "ENTAILED"),
    (before("mai-t13", MI, "Check: 4000 × 1.036⁵ = 4773.74, so 4780 to the nearest ten euros."), "4780", "COUNTEREXAMPLE"),
    (before("mai-t13", MI, "Check: 4000 × 1.036⁵ = 4773.74, so 4770 to the nearest ten euros."), "4770", "ENTAILED"),
    (before("mai-t13", MI, "Check: 135.36 ÷ 12 = 11.28, so 12 years to the nearest year."), "12", "COUNTEREXAMPLE"),
    (before("mai-t13", MI, "Check: 135.36 ÷ 12 = 11.28, so 11 years to the nearest year."), "11", "ENTAILED"),
])
def test_a_result_restated_after_so_with_its_unit_word_and_rounding_is_checked(text, value, status):
    checks, _f = new("mai-t13", text)
    res = [c for c in checks if c[0] == "res"]
    assert [(c[1], c[2]) for c in res] == [(status, "error")], checks
    assert f"the restated result: '{value}'" in res[0][3]


@pytest.mark.parametrize("value, status", [("4 A", "ENTAILED"), ("5 A", "COUNTEREXAMPLE")])
def test_a_rounding_to_the_nearest_unit_spelled_out_is_read(value, status):
    checks, _f = new("ph-t13", replaced("ph-t13", "I = 12 V / 2.9 Ω = 4.1 A", f"I = 12 V / 2.9 Ω = 4.14 A, so {value} to the nearest ampere"))
    assert [(c[1], c[3].split(" [claims")[0]) for c in checks if c[0] == "res"] == [(status, f"the restated result: '{value}'")]


@pytest.mark.parametrize("line", ["Check: 4000 × 1.036⁵ = 4773.74, so 2 years of interest are missing.",
                                  "Check: 4000 × 1.036⁵ = 4773.7401, so 4773.74 euros to the nearest dollar."])
def test_a_consequence_or_a_rounding_to_another_unit_is_no_restatement(line):
    # a dollar is neither the unit the value counts in nor a part of it ('to the nearest cent' is read: the test below)
    checks, _f = new("mai-t13", before("mai-t13", MI, line))
    assert [c[0] for c in checks] == ["eq"] and failing(checks) == []


@pytest.mark.parametrize("line, value, status", [
    ("Check: 4000 × 1.036⁵ = 4773.7401, so 4773.74 euros to the nearest cent.", "4773.74", "ENTAILED"),
    ("Check: 4000 × 1.036⁵ = 4773.7401, so 4773.75 euros to the nearest cent.", "4773.75", "COUNTEREXAMPLE"),
    ("Check: 4000 × 1.036⁵ = 4773.7401, so 4783.74 euros to the nearest cent.", "4783.74", "COUNTEREXAMPLE"),
    ("Check: 4000 × 1.036⁵ = 4773.7401, so 4773.74 to the nearest cent.", "4773.74", "ENTAILED"),
    ("Check: 4000 × 1.036⁵ = 4773.7401, so 4773.84 to the nearest cent.", "4773.84", "COUNTEREXAMPLE"),
])
def test_a_rounding_to_a_part_of_the_unit_is_read(line, value, status):
    """'to the nearest cent' for a value the task counts in euros names a part of that unit: half a cent. It had read nothing, so
    a wrong value restated to the cent sat on a claim whose only check, the arithmetic before it, held."""
    checks, _f = new("mai-t13", before("mai-t13", MI, line))
    res = [c for c in checks if c[0] == "res"]
    assert [(c[1], c[2]) for c in res] == [(status, "error")], checks
    assert f"the restated result: '{value}'" in res[0][3] and "rounded as the prose states (to the nearest cent): h = 1/200" in res[0][3]


@pytest.mark.parametrize("value, status", [("4.138 A", "ENTAILED"), ("4.148 A", "COUNTEREXAMPLE")])
def test_a_rounding_to_another_unit_of_the_value_s_dimension_is_read(value, status):
    checks, _f = new("ph-t13", replaced("ph-t13", "I = 12 V / 2.9 Ω = 4.1 A", f"I = 12 V / 2.9 Ω = 4.1379 A, so {value} to the nearest milliampere"))
    res = [c for c in checks if c[0] == "res"]
    assert [(c[1], c[3].split(" [claims")[0]) for c in res] == [(status, f"the restated result: '{value}'")]
    assert "rounded as the prose states (to the nearest milliampere): h = 1/2000" in res[0][3]


#: STEM repair 9 (rule rounded-digits): a value restated with a rounding the prose reads is also set against that rounding's place (the
#: penny, 0.01, for both restated values written to the hundredths: it holds); the cent is no part of a pound, so no rounding is read there
@pytest.mark.parametrize("answer, kinds", [
    ("500 × 1.02³ = 530.604, so 530.60 pounds to the nearest penny.", [("eq", "ENTAILED"), ("res", "ENTAILED"), ("eq", "ENTAILED")]),
    ("500 × 1.02³ = 530.604, so 530.61 pounds to the nearest penny.", [("eq", "ENTAILED"), ("res", "COUNTEREXAMPLE"), ("eq", "ENTAILED")]),
    ("500 × 1.02³ = 530.604, so 530.61 pounds to the nearest cent.", [("eq", "ENTAILED")]),  # a cent is no part of a pound
])
def test_a_part_of_a_unit_is_read_only_for_the_unit_it_is_part_of(answer, kinds):
    clear_document_cache()
    doc = build_document(answer, "A loan of 500 pounds grows at 2% a year. Find its value after 3 years, to the nearest penny.", "mathematics_ai")
    plan = build_checks(doc, report_id="r", request_id="q")
    got = [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy)).status.value)
           for pc in plan.checks]
    assert got == kinds and list(doc.findings) + list(plan.findings) == []
    assert all("(rule rounded-digits)" in pc.description for pc in plan.checks[2:]) and len(plan.checks) == len(kinds)


# ============================================================================================ rule row-value
ESS_END = "seasonal runoff peaks [1]."
ESS_W = "Water temperature was between 17 °C and 18 °C at every site, so it does not explain the difference."


@pytest.mark.parametrize("text, status", [
    (after("ess-t13", ESS_END, "Dissolved oxygen at site C = 3.8 g dm⁻³.", " "), "COUNTEREXAMPLE"),
    (after("ess-t13", ESS_END, "Dissolved oxygen at site C = 3.8 mg dm⁻³.", " "), "ENTAILED"),
    (after("ess-t13", ESS_END, "Dissolved oxygen at site C = 0.0038 g dm⁻³.", " "), "ENTAILED"),
    (after("ess-t13", ESS_END, "The nitrate at site E = 4.1 mg dm⁻³.", " "), "COUNTEREXAMPLE"),
    (after("ess-t13", ESS_END, "The nitrate at site E = 2.3 mg dm⁻³.", " "), "ENTAILED"),
    (replaced("ess-t13", ESS_W, "At site C, dissolved oxygen is 3.8 g dm⁻³."), "COUNTEREXAMPLE"),
    (replaced("ess-t13", ESS_W, "At site C, dissolved oxygen is 3.8 mg dm⁻³."), "ENTAILED"),
    (replaced("ess-t13", ESS_W, "At site E, nitrate is 4.1 mg dm⁻³."), "COUNTEREXAMPLE"),
    (replaced("ess-t13", ESS_W, "At site E, nitrate is 2.3 mg dm⁻³."), "ENTAILED"),
    (after("ess-t13", ESS_END, "The mayfly nymphs at site D = 9.", " "), "COUNTEREXAMPLE"),
    (after("ess-t13", ESS_END, "The mayfly nymphs at site D = 5.", " "), "ENTAILED"),
])
def test_a_value_at_a_lettered_row_is_set_against_the_table(text, status):
    checks, findings = new("ess-t13", text)
    assert [(c[0], c[1], c[2]) for c in checks] == [("giv", status, "warning")] and findings == [], (checks, findings)
    assert "(rule table-data, rule row-value)" in checks[0][3]


@pytest.mark.parametrize("old, new_text, status", [
    ("where it reaches 3.8 mg dm⁻³, not at B", "where it reaches 3.8 g dm⁻³, not at B", "COUNTEREXAMPLE"),
    ("where it reaches 3.8 mg dm⁻³, not at B", "where it reaches 0.0038 g dm⁻³, not at B", "ENTAILED"),
    ("nitrate at E (2.3 mg dm⁻³) stays above", "nitrate at E (4.1 mg dm⁻³) stays above", "COUNTEREXAMPLE"),
    ("recovers by D (6.4 mg dm⁻³)", "recovers by D (8.7 mg dm⁻³)", "COUNTEREXAMPLE"),
    ("site A has the least nitrate (1.2 mg dm⁻³)", "site A has the least nitrate (2.3 mg dm⁻³)", "COUNTEREXAMPLE"),
])
def test_a_recorded_value_at_a_row_restated_wrongly_fails_its_row_check(old, new_text, status):
    checks, _f = new("ess-t13", replaced("ess-t13", old, new_text))
    assert [(c[0], c[1]) for c in checks] == [("giv", status)], checks


@pytest.mark.parametrize("line", ["The value at site C = 3.8 mg dm⁻³.", "Let C = 3.8 mg dm⁻³ be the lowest value."])
def test_no_row_value_without_one_column_or_a_row(line):
    assert new("ess-t13", after("ess-t13", ESS_END, line, " ")) == ([], [])


# ============================================================================================ rule exact-carry for exact working
@pytest.mark.parametrize("new_text, holds_", [("≈ 9.5 h", False), ("= 9.5 h", False), ("≈ 100 h", False), ("≈ 8.4 h", True), ("= 8.49 h", True)])
def test_a_number_carrying_an_exact_result_has_no_rounding_interval(new_text, holds_):
    checks, _f = new("maa-p7b", replaced("maa-p7b", "≈ 8.5 h", new_text))
    eq = [c for c in checks if c[0] == "eq" and "8 ln 2 ÷ ln(1568/816)" in c[3]]
    assert len(eq) == 1 and holds(eq[0]) is holds_, checks


def test_a_number_carrying_a_rounded_result_keeps_its_interval():
    checks, _f = new("maa-p7b", replaced("maa-p7b", "T = ln 2 ÷ ((ln 2)/8) = 8", "T = 0.693 ÷ 0.0866 = 8.0"))
    assert ("eq", "SATISFIABLE") in [(c[0], c[1]) for c in checks if "0.693/8.0 h = 0.087 h⁻¹" in c[3]] and failing(checks) == []


# ============================================================================================ rules stated-uncertainty and operand-precision
@pytest.mark.parametrize("unc, status", [("33", "COUNTEREXAMPLE"), ("23.0", "ENTAILED"), ("20", "ENTAILED"), ("22.6", "COUNTEREXAMPLE")])
def test_an_uncertainty_written_with_a_corrected_value_is_set_against_the_answer_s_rule(unc, status):
    """'each corrected value has an absolute uncertainty of 2% of the measured value': 2% of 1151 is 23.02."""
    checks, _f = new("ph-p7b", replaced("ph-p7b", "t = 4 h: 1151 − 20 = 1131 ± 23", f"t = 4 h: 1151 − 20 = 1131 ± {unc}"))
    giv = [c for c in checks if c[0] == "giv"]
    assert [(c[1], c[2]) for c in giv] == [(status, "warning")] and "(rule stated-uncertainty)" in giv[0][3], checks
    assert [c[1] for c in checks if c[0] == "eq"] == ["ENTAILED"]


@pytest.mark.parametrize("value, holds_", [("4467.74", False), ("4492.00", False), ("4547.74", False), ("4447.74", True), ("4447.7", True),
                                           ("4448", True), ("4450", True)])
def test_a_slip_the_rounding_of_the_written_operands_cannot_explain_fails(value, holds_):
    checks, _f = new("mai-t13", before("mai-t13", MI, f"A geometric sequence check: u₄ = 4000 × 1.036³ = {value}."))
    assert [c[0] for c in checks] == ["eq"] and holds(checks[0]) is holds_, checks


def test_operand_precision_is_stated_in_the_check_and_leaves_a_whole_number_s_zeros_to_tau():
    checks, _f = new("mai-t13", before("mai-t13", MI, "A geometric sequence check: u₄ = 4000 × 1.036³ = 4467.74."))
    assert "(rule operand-precision)" in checks[0][3] and "twice the largest relative change the rounding of the written operands" in checks[0][3]
    checks, _f = new("ph-t13", after("ph-t13", PH_END, "W = 1000 J ÷ 3 = 330 J"))
    assert [(c[0], c[1]) for c in checks] == [("eq", "ENTAILED")] and "τ = 1/100" in checks[0][3] and "operand-precision" not in checks[0][3]
    checks, _f = new("ph-t13", after("ph-t13", PH_END, "E = 2.718 × 3.141 = 8.60"))
    assert [(c[0], c[1]) for c in checks] == [("eq", "COUNTEREXAMPLE")]
    checks, _f = new("ph-t13", after("ph-t13", PH_END, "E = 2.718 × 3.141 = 8.54"))
    assert [(c[0], c[1]) for c in checks] == [("eq", "ENTAILED")]


# ============================================================================================ the clean control on genuine work
_RULES = ("(rule boolean-values)", "(rule changed-value)", "(rule given-uncertainty)", "rule row-value", "(rule stated-uncertainty)",
          "(rule operand-precision)")


@pytest.mark.parametrize("tid", sorted(PROFILE))
def test_on_the_recorded_answers_every_new_reading_holds_and_names_nothing(tid):
    """On every recorded STEM answer of round 7 each check a repair-4 rule plans holds, every check holds, and no answer gains a
    finding."""
    checks, findings = task(tid, SPEC[tid]["response_text"])
    assert failing(checks) == [], failing(checks)
    assert not {"ST-UNDEC-003", "ST-PARSE-001", "ST-DIM-001"} & {c for c, _s, _m in findings}, findings
    rows = [c for c in checks if any(r in c[3] for r in _RULES)]
    assert all(holds(c) for c in rows), rows
    if tid == "ess-t13":
        # STEM repair 10: 'the most nymphs (34)' and 'only 9' of part (b) are read too (each holding): eight
        assert len([c for c in rows if "rule row-value" in c[3]]) == 8
    if tid == "ph-p7b":
        assert len([c for c in rows if "(rule stated-uncertainty)" in c[3]]) == 7
