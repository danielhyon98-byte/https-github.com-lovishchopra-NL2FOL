"""Model evaluations (``stem/models.py``, check kind ``mod``): an application of an exponential model the answer or the
request defines (``P(t + 4)`` for ``P = P₀e^(kt)``) is the model's expression at the written argument, and the link must
have a solution: some value of the variables, and of the stated symbols within their stated values, satisfies it.

Every power of an exponent in symbols is read through positive variables (one per base and monomial of the exponents),
so UNSATISFIABLE proves that no value satisfies the link and is the report's own error (INT-SUBJ-001); SATISFIABLE never
proves that the link holds for every value. The reading is narrow, so a misreading never decides anything: a written
decimal, a unit, a space between the letter and its bracket, the sciences reading of e (the elementary charge) and a
model whose variable no application names all keep the old reading. A letter defined as two models is read in each
definition, and the link must hold in one of them.

The parser reads an application of any letter but f, g and h as a product, so consecutive evaluations of a function the
text defines (``N(10) = 200``, then ``N(15) = 100``) were the algebra step ``10N = 200 ⊢ 15N = 100``, refuted: an error on
correct work at 22d6a5b. A letter the text defines as a function is now read as f is: an evaluation at a value is no
step, and a step over an application at an unknown is undecided (ST-UNDEC-001).
"""
from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.stem.models import application_of, denominators, exponent_polynomial, split_runs
from epinoic_logic.stem.nodes import BinOp, Num, Sym, render
from epinoic_logic.stem.numbers import exact_integer
from epinoic_logic.translate.contracts import SuppliedText

KEY = b"model-evaluations-key-0123456789abcdefgh"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
AA, AI = "Mathematics: Analysis and Approaches", "Mathematics: Applications and Interpretation"
MODEL_Q = "Let t be the number of months after January 1923. Use the model P = P₀e^(kt) for the price P."
GIVEN = "P₀ = 250 and k = 2.05 (3 s.f.).\n"
#: a symbolic application names the model's variable (t); a numeric one alone (``P(6)``) could stand for t or for k
NAMED = GIVEN + "P(t + 1) = P₀e^(k(t + 1))\n"
R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))


def receive(answer: str, question: str = MODEL_Q, subject: str = AA, docs=()):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=["stem-specialist"],
                           allowed_document_ids=[d.document_id for d in docs]))
    m, _, _ = hub.dispatch("t", "stem-specialist", question, list(docs))
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="stem-specialist", report_id="rep-t-0")
    return rc


def mod_checks(rc) -> list:
    return [fc for fc in rc.formal_checks if fc.constraint_id.startswith("stem-mod-")]


def errors(rc) -> list:
    return [f for f in rc.findings if f.severity == "error"]


@pytest.mark.parametrize("question, answer", [
    (MODEL_Q, GIVEN + "P(t + 2) = P₀e^(k(t + 1))"),            # the argument moved: e^k = 1 would be needed
    (MODEL_Q, GIVEN + "P(t + 4) = P₀e^(k(t + 1))"),            # the e2e run1 substitution
    (MODEL_Q, GIVEN + "P(t + 1) = 2P₀e^(k(t + 1))"),           # a factor of 2: P₀ = 0 would be needed
    (MODEL_Q, NAMED + "P(6) = 250e^(7k)"),                     # the exponent moved
    (MODEL_Q, NAMED + "P(0) = 2P₀"),
    (MODEL_Q, GIVEN + "P(t)P(1) = P₀e^(k(t + 2))"),             # two applications: P₀²e^(k(t + 1)) against P₀e^(k(t + 2))
    ("A(t) is the amount after t years.", "A(t) = 500 × 2^(t/3)\nA(t + 3) = 1500 × 2^(t/3)"),     # a closed base: 1000, not 1500
    ("N(t) is the number of nuclei.", "N(t) = 800 × (1/2)^(t/5)\nN(10) = 400"),                    # a fraction base, closed: 200
])
def test_a_model_evaluation_with_no_solution_is_an_engine_error(question, answer):
    rc = receive(answer, question)
    failed = [fc for fc in mod_checks(rc) if fc.satisfied is False]
    assert failed and all(fc.formal_status == "UNSATISFIABLE" for fc in failed), [(fc.constraint_id, fc.formal_status) for fc in mod_checks(rc)]
    assert [f for f in errors(rc) if f.code == "INT-SUBJ-001" and "the model evaluation" in f.message]


@pytest.mark.parametrize("question, answer", [
    (MODEL_Q, GIVEN + "P(t + 1) = P₀e^(k(t + 1))"),
    (MODEL_Q, GIVEN + "P(t + 1) = P₀e^(k(t + 1)) = e^(k) × P₀e^(kt)"),
    (MODEL_Q, NAMED + "P(6) = 250e^(6k)"),
    (MODEL_Q, NAMED + "P(0) = P₀"),
    (MODEL_Q, GIVEN + "P(t + 1)/P(t) = e^(k)"),
    (MODEL_Q, GIVEN + "P(t)P(1) = 250P₀e^(k(t + 1))"),
    ("A(t) is the amount after t years.", "A(t) = 500 × 2^(t/3)\nA(t + 3) = 1000 × 2^(t/3)"),
    ("N(t) is the number of nuclei.", "N(t) = 800 × (1/2)^(t/5)\nN(10) = 200"),
    ("C(t) is the count rate.", "C(t) = 1600e^(−kt)\nC(T) = ½ × 1600"),                         # T a variable: the half-life is solved for
])
def test_a_correct_model_evaluation_holds(question, answer):
    rc = receive(answer, question)
    checks = mod_checks(rc)
    assert checks and all(fc.satisfied is True and fc.formal_status == "SATISFIABLE" for fc in checks), [(fc.constraint_id, fc.formal_status, fc.detail[-300:]) for fc in checks]
    assert not [f for f in errors(rc) if "the model evaluation" in f.message]


def test_the_r7_exponential_model_answer_gains_checks_that_all_hold():
    """maa-p7b of round 7 defines its own model C(t) = C0 e^(−kt) and evaluates it at 8, at T and at 40: three ``mod``
    checks, each satisfiable; its definition is no check, and no error is added."""
    it = R7["specialists"]["maa-p7b"]
    peer = R7["specialists"][it["peer_of"]]
    docs = [SuppliedText(**t) for t in it.get("supplied_texts", [])] + [SuppliedText(document_id=f"peer:{it['peer_of']}", title="relayed", author=peer["agent_id"],
                                                                                   text=peer["response_text"])]
    rc = receive(it["response_text"], it["question"], it["subject"], docs)
    checks = mod_checks(rc)
    assert len(checks) == 3 and all(fc.satisfied is True for fc in checks), [(fc.constraint_id, fc.formal_status) for fc in checks]
    assert not [f for f in errors(rc) if "the model evaluation" in f.message]


@pytest.mark.parametrize("question, answer, why", [
    (MODEL_Q, GIVEN + "P (t + 4) = P₀e^(k(t + 1))", "a space between the letter and its bracket: a product"),
    (MODEL_Q, GIVEN + "P(t + 1) = 7.77P(t)", "a written decimal (a rounded figure would need its rounding interval)"),
    (MODEL_Q, GIVEN + "P(t + 1) = P₀e^(k(t + 1)) M1 with P in marks per 1.5 loaves", "no reading beyond the relation"),
    ("Use the model P = 250e^(2.05t).", "P(t + 1) = 250e^(2.05(t + 1))", "a model written with a decimal is no model"),
    ("Use the model P = P₀e^(kt).", "P₀ = 250.\nP(6) = 250e^(6k)", "no application names the variable (6 could stand for t or for k)"),
    ("Let k be the growth constant and t the time. Use the model P = P₀e^(kt).", "P₀ = 250.\nP(6) = 250e^(6k)",
     "a description is not read for the variable: it may name a parameter (here k)"),
    (MODEL_Q, GIVEN + "P(t) > 1000", "an inequality"),
])
def test_a_link_the_model_reading_does_not_cover_keeps_its_old_reading(question, answer, why):
    rc = receive(answer, question)
    assert not [fc for fc in mod_checks(rc) if "P(t + 4)" in fc.detail or "7.77" in fc.detail or "2.05(t + 1)" in fc.detail
                or "P(6)" in fc.detail or "> 1000" in fc.detail], why


def test_a_model_definition_and_the_sciences_reading_of_e_are_no_model_checks():
    rc = receive("C(t) = 1600e^(−kt)", "C(t) is the count rate.")
    assert not mod_checks(rc)  # the definition itself
    rc = receive("N(t) = N₀e^(−λt)\nN(2) = N₀e^(−2λ)", "A sample decays.", subject="Physics")
    assert not mod_checks(rc)  # in the sciences, e may be the elementary charge: no power of e is read


@pytest.mark.parametrize("text, exponent, poly", [
    ("e^(k(t + 1))", "k(t + 1)", {(("k", 1), ("t", 1)): Fraction(1), (("k", 1),): Fraction(1)}),
    ("e^(−kt/2 + 3)", "−kt/2 + 3", {(("k", 1), ("t", 1)): Fraction(-1, 2), (): Fraction(3)}),
])
def test_an_exponent_is_read_as_a_polynomial_with_rational_coefficients(text, exponent, poly):
    doc = build_document(f"y = {text}", None, "mathematics_aa")
    node = next(op.readings[0] for it in doc.items for ch in it.chains for op in ch.operands[1:])
    assert exponent_polynomial(node.arg) == poly


def test_the_step_of_each_positive_variable_keeps_its_powers_small():
    k, kt = (("k", 1),), (("k", 1), ("t", 1))
    assert denominators([{kt: Fraction(1), k: Fraction(4)}, {kt: Fraction(1), k: Fraction(1)}]) == {kt: Fraction(1), k: Fraction(1)}
    assert denominators([{k: Fraction(-40)}]) == {k: Fraction(40)}               # e^(−40k) is one variable
    assert denominators([{k: Fraction(1, 3)}, {k: Fraction(1, 2)}]) == {k: Fraction(1, 6)}


def test_an_application_is_the_letter_glued_to_the_bracket_that_holds_exactly_the_argument():
    text = "P(t + 4) and P (t) and P((t))"
    p1, arg1 = Sym("P", start=0, end=1), BinOp("+", Sym("t", start=2, end=3), Num(exact_integer(4), 6, 7), 2, 7)
    assert application_of(p1, arg1, text)
    p2, arg2 = Sym("P", start=13, end=14), Sym("t", start=16, end=17)
    assert not application_of(p2, arg2, text)  # a space
    p3, arg3 = Sym("P", start=23, end=24), Sym("t", start=26, end=27)
    assert not application_of(p3, arg3, text)  # the bracket holds more than the argument


def test_a_declared_letter_run_is_split_only_into_symbols_in_scope():
    node = Sym("kt")
    assert render(split_runs(node, {"k", "t"})) == "k·t"
    assert render(split_runs(node, {"k"})) == "kt"


TWO_MODELS = "Two models are proposed. Model A: N = 100e^(t/5). Model B: N = 100 × 2^(t/3). Show how N changes."
TWO_MODELS_SWAPPED = "Two models are proposed. Model B: N = 100 × 2^(t/3). Model A: N = 100e^(t/5). Show how N changes."


@pytest.mark.parametrize("question", [TWO_MODELS, TWO_MODELS_SWAPPED])
@pytest.mark.parametrize("answer", ["Model B: N(t + 3) = 2N(t)", "Model A: N(t + 10) = e^2 N(t)"])
def test_a_letter_defined_as_two_models_is_read_in_either_definition(question, answer):
    """Read with the most recent definition only, the line about the other model had no solution (2^(10/3) ≠ e²): a false
    error. Each definition is a reading of the link, so the link holds when it holds under one of them."""
    rc = receive(answer, question)
    checks = mod_checks(rc)
    assert checks and all(fc.satisfied is True and fc.formal_status == "SATISFIABLE" for fc in checks), [(fc.constraint_id, fc.formal_status) for fc in checks]
    assert all("definition 2 of 2" in fc.detail for fc in checks)
    assert not errors(rc)


@pytest.mark.parametrize("question", [TWO_MODELS, TWO_MODELS_SWAPPED])
@pytest.mark.parametrize("answer", ["Model B: N(t + 3) = 3N(t)", "Model A: N(t + 10) = 3N(t)"])
def test_a_link_that_holds_under_neither_definition_is_an_engine_error(question, answer):
    rc = receive(answer, question)
    failed = [fc for fc in mod_checks(rc) if fc.satisfied is False]
    assert failed and all(fc.formal_status == "UNSATISFIABLE" for fc in failed)
    assert [f for f in errors(rc) if f.code == "INT-SUBJ-001" and "the model evaluation" in f.message]


@pytest.mark.parametrize("question, answer", [
    ("N(t) is the number of nuclei.", "N(t) = 800 × (1/2)^(t/5)\nN(10) = 200\nN(15) = 100"),
    ("N(t) is the number of nuclei.", "N(t) = 800 × (1/2)^(t/5)\nN(10) = 200.0\nN(15) = 100.0"),
    ("V(t) is the value of a car.", "V(t) = 20000 × 0.8^t\nV(1) = 16000\nV(2) = 12800"),
    ("V(t) is the value of a car.", "V(t) = 20000 × (4/5)^t\nV(1) = 16000\nV(2) = 12800"),
    ("C(t) is the cost.", "C(t) = 5t + 3\nC(2) = 13\nC(3) = 18"),
    ("N(t) is the number of bacteria.", "N(t) = 100 × 3^t\nN(1) = 300\nN(2) = 900"),
    ("N(t) is the number of bacteria.", "N(t) = 100 × 2^t\nN(t + 1) = 2N(t)\nN(t + 2) = 4N(t)"),
    (MODEL_Q, "P₀ = 250, k = 2.05.\nP(6) = 250e^(6 × 2.05) = 5.49 × 10⁷\nP(10) = 250e^(10 × 2.05) = 2.00 × 10¹¹"),
    ("Use the model P = 250e^(2t).", "P(1) = 250e^2\nP(2) = 250e^4"),
    (TWO_MODELS, "Model A: N(t + 5) = e × N(t)\nModel B: N(t + 3) = 2N(t)"),
])
def test_consecutive_evaluations_of_a_function_the_text_defines_are_no_algebra_step(question, answer):
    """Each was an error at 22d6a5b: the step between the two evaluation lines was read with each application as a
    product (N·10 = 200 ⊢ N·15 = 100) and refuted. No step is read over an application of a letter the text defines as a
    function (``N(t) = …``, or a model of the request), so no algebra or comparison check is built over them."""
    rc = receive(answer, question)
    assert not errors(rc), [(f.code, f.message[:160]) for f in errors(rc)]
    assert not [fc for fc in rc.formal_checks if fc.constraint_id.startswith(("stem-alg-", "stem-cmp-"))]
    assert all(fc.satisfied is True for fc in rc.formal_checks if fc.constraint_id.startswith("stem-"))


def test_a_step_over_an_application_at_an_unknown_is_named_undecided():
    rc = receive("N(t) = 100 × 2^t\nN(t + 1) = 2N(t)\nN(t + 2) = 4N(t)", "N(t) is the number of bacteria.")
    assert [f for f in rc.structural_findings if f.code == "ST-UNDEC-001" and "an application of a function the text defines" in f.message]
    assert len(mod_checks(rc)) == 2 and all(fc.satisfied is True for fc in mod_checks(rc))  # each line is checked by itself


@pytest.mark.parametrize("question, answer", [
    ("N(t) is the number of nuclei.", "N(t) = 800 × (1/2)^(t/5)\nN(10) = 200\nN(15) = 150"),   # N(15) is 100
    ("N(t) is the number of bacteria.", "N(t) = 100 × 3^t\nN(1) = 300\nN(2) = 600"),            # N(2) is 900
    ("N(t) is the number of bacteria.", "N(t) = 100 × 2^t\nN(t + 1) = 2N(t)\nN(t + 2) = 3N(t)"),  # 4N(t)
])
def test_a_fault_in_one_of_the_evaluations_is_still_named_by_its_model_check(question, answer):
    rc = receive(answer, question)
    failed = [fc for fc in mod_checks(rc) if fc.satisfied is False]
    assert failed and all(fc.formal_status == "UNSATISFIABLE" for fc in failed)
    assert [f for f in errors(rc) if f.code == "INT-SUBJ-001" and "the model evaluation" in f.message]


@pytest.mark.parametrize("subject, question, answer", [
    ("Physics", "A cell has emf ε and internal resistance r.", "ε = I(R + r)\nI = ε/(R + r)"),
    ("Physics", "A capacitor of capacitance C.", "Q = C(V₂ − V₁)\nV₂ − V₁ = Q/C"),
    (AA, "Solve the equation.", "3(x + 2) = 12\nx + 2 = 4\nx = 2"),
])
def test_a_bracket_after_a_letter_that_is_no_function_keeps_its_product_reading_and_its_step(subject, question, answer):
    """I(R + r) and C(V₂ − V₁) are products: neither letter is defined as a function, so the algebra step is built and holds."""
    rc = receive(answer, question, subject)
    steps = [fc for fc in rc.formal_checks if fc.constraint_id.startswith("stem-alg-")]
    assert steps and all(fc.satisfied is True and fc.formal_status == "ENTAILED" for fc in steps)
    assert not errors(rc)
