"""Variants of the STEM findings that the repair round 1 review re-ran (each with its clean control):

* ss4: a Boolean AND dot written with spaces ('A . B') is the whole product, so a false identity fails and the
  distributive law and De Morgan hold;
* ss11: a root lost by dividing by x ('Dividing by x, x² = 4') is a failed step;
* ss12: wrong arithmetic with space-grouped numerals ('1 500 × 2 = 30') is checked and fails;
* ss1: a prefixed or non-SI unit that comes from a binding ('m = 500 g', 't = 2.0 min') fails the unit companion;
* sp8: a comparison the answer itself calls false ('2 <= 1, which is false') is no asserted comparison;
* sp4: a rounding labelled with the wrong precision ('4380 = 4400 (1 s.f.)') fails;
* ps13: a direction stated with scientific-notation figures ('rose from 3.2e4 to 7.5e3') is checked;
* ss4-hub: a correct simplification of the request's own expression is no restatement of the request;
* INV-6: a root stated for a request to solve the equation claims the full solution set ('x² = 4^{1.5}, so x = 2√2'
  loses −2√2), and bare values that continue a stated root are members of the set ('x = 0, 2 or −2'), so a set
  stated in that form is decided on every member it states, and a step to it concludes the set, not its first value;
  a set that goes on with a value not read as a plain number, or a root the statement calls one of several, claims no
  full set.
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

from .argdiag_hub import decided

CS, MAA, MAI = "computer_science", "mathematics_aa", "mathematics_ai"
KEY = b"repair-round1-stem-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def _verdicts(text, request=None, profile="physics") -> dict:
    return {cid: ok for cid, (_pc, ok) in decided(text, request, profile).items()}


@pytest.mark.parametrize("text, profile, check, expected", [
    ("A . B = B . C", CS, "stem-bool-1", False),                                   # ss4: a false identity
    ("A . B + A . C = A . (B + C)", CS, "stem-bool-1", True),                     # control: the distributive law
    ("NOT A . NOT B = NOT(A + B)", CS, "stem-bool-1", True),                      # control: De Morgan
    ("NOT(A . B) = NOT A + NOT B", CS, "stem-bool-1", True),
    ("x³ = 4x\nDividing by x, x² = 4, so x = ±2", MAA, "stem-alg-1", False),       # ss11: the root x = 0 is lost
    ("x³ = 4x\nx(x² − 4) = 0, so x = 0 or x = ±2", MAA, "stem-alg-1", True),       # control: factorised, no root lost
    ("1 500 × 2 = 30", MAI, "stem-eq-1", False),                                   # ss12
    ("12 000 × 0.15 = 1 900", MAI, "stem-eq-1", False),
    ("1 500 × 2 = 3 000", MAI, "stem-eq-1", True),                                 # control
    ("12 000 × 0.15 = 1 800", MAI, "stem-eq-1", True),
    ("m = 500 g and a = 2.0 m s⁻², so F = ma = 500 × 2.0 = 1000 N", "physics", "stem-eq-1u", False),         # ss1: grams from a binding
    ("d = 1500 m and t = 2.0 min, so v = d/t = 1500/2.0 = 750 m s⁻¹", "physics", "stem-eq-1u", False),       # minutes from a binding
    ("The condition low <= high becomes 2 <= 1, which is true, so the loop continues.", CS, "stem-cmp-1", False),   # sp8 control
    ("The condition low <= high becomes 2 <= 1, which is false, so the loop stops.", CS, "stem-cmp-1", True),       # sp8
    ("Cost = 365 × 12 = 4380 = 4400 (1 s.f.)", MAI, "stem-eq-2", False),           # sp4: 4400 is the 2 s.f. rounding
    ("Cost = 365 × 12 = 4380 = 4000 (1 s.f.)", MAI, "stem-eq-2", True),            # control
    ("Cost = 365 × 12 = 4380 = 4400 (2 s.f.)", MAI, "stem-eq-2", True),            # control
])
def test_each_variant_is_decided_as_its_working_reads(text, profile, check, expected):
    v = _verdicts(text, None, profile)
    assert v.get(check) is expected, v


@pytest.mark.parametrize("text", ["m = 500 g and a = 2.0 m s⁻², so F = ma = 0.500 × 2.0 = 1.0 N",
                                  "d = 1500 m and t = 2.0 min = 120 s, so v = d/t = 1500/120 = 12.5 m s⁻¹"])
def test_clean_control_a_converted_binding_holds_every_check(text):
    v = _verdicts(text)
    assert v and set(v.values()) == {True}, v


def _send(subject: str, agent: str, request: str, answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _req, _rc = hub.dispatch("t", agent, request)
    return hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")[1]


@pytest.mark.parametrize("answer, holds", [("Debt rose from 3.2e4 to 7.5e3 between 1980 and 1990.", False),     # ps13
                                           ("Debt rose from 32000 to 7500 between 1980 and 1990.", False),
                                           ("Debt rose from 7.5e3 to 3.2e4 between 1980 and 1990.", True)])     # control
def test_a_direction_with_scientific_notation_figures_is_checked(answer, holds):
    rc = _send("Economics", "economics-specialist", "Describe how the debt changed between 1980 and 1990.", answer)
    assert [(c.constraint_id, c.satisfied) for c in rc.formal_checks] == [("core-quant-1", holds)]
    assert ("INT-SUBJ-001" in {f.code for f in rc.findings}) is (not holds)


def test_a_simplification_of_the_requests_expression_is_no_restatement():
    request = "Simplify the Boolean expression A.B + A.C."
    rc = _send("Computer Science", "computer-science-specialist", request, "A.B + A.C = A.(B + C)")
    assert "INT-REQ-011" not in {f.code for f in rc.findings} and [(c.constraint_id, c.satisfied) for c in rc.formal_checks] == [("stem-bool-1", True)]
    restated = _send("Computer Science", "computer-science-specialist", request, request)       # control: the request said back
    assert "INT-REQ-011" in {f.code for f in restated.findings}


# ------------------------------------------------------------------ the new STEM codes: ST-REF-002 and ST-GIVEN-003

def _codes(text, request=None, profile="physics") -> list[str]:
    from .argdiag_hub import plan
    doc, p = plan(text, request, profile)
    return [f.code for f in list(doc.findings) + list(p.findings)]


KE_REQUEST = "A ball of mass 2.0 kg moves at 3.0 m s⁻¹. Calculate its kinetic energy."


def test_a_law_with_the_booklet_variables_that_differs_as_a_function_is_st_ref_002():
    assert "ST-REF-002" in _codes("E_k = mv² = 2.0 × 3.0² = 18 J", KE_REQUEST)        # the ½ dropped: same variables and dimension


def test_clean_control_the_booklet_law_itself_names_nothing():
    codes = _codes("E_k = ½mv² = 0.5 × 2.0 × 3.0² = 9.0 J", KE_REQUEST)
    assert "ST-REF-002" not in codes and "ST-REF-001" not in codes


P_REQUEST = "Events A and B have P(A) = 0.5, P(B) = 0.4 and P(A ∩ B) = 0.1. Find P(A ∪ B)."


@pytest.mark.parametrize("answer", ["Since A and B are mutually exclusive, P(A ∪ B) = 0.5 + 0.4 = 0.9",       # against P(A ∩ B) = 0.1
                                    "Since A and B are independent, P(A ∩ B) = 0.5 × 0.4 = 0.2",            # 0.5 × 0.4 is not 0.1
                                    "P(A ∪ B) = 0.5 + 0.4 + 0.3 = 1.2"])                                     # a probability above 1
def test_a_probability_the_givens_cannot_bear_is_st_given_003(answer):
    assert "ST-GIVEN-003" in _codes(answer, P_REQUEST, MAI)


@pytest.mark.parametrize("answer", ["P(A ∪ B) = P(A) + P(B) − P(A ∩ B) = 0.5 + 0.4 − 0.1 = 0.8",
                                    "A and B are not mutually exclusive, so P(A ∪ B) = 0.5 + 0.4 − 0.1 = 0.8"])
def test_clean_control_the_addition_rule_with_the_stated_intersection_names_nothing(answer):
    assert "ST-GIVEN-003" not in _codes(answer, P_REQUEST, MAI)


def test_a_given_the_working_contradicts_is_st_given_002():
    wrong = "Given d = 100 m, t = 10.0 s and a constant speed of v = 12 m s⁻¹. Using v = d/t, v = 100/10.0 = 10 m s⁻¹"
    assert "ST-GIVEN-002" in _codes(wrong, None, "sports_science")
    right = "Given d = 100 m, t = 10.0 s and a constant speed of v = 10 m s⁻¹. Using v = d/t, v = 100/10.0 = 10 m s⁻¹"      # control
    assert "ST-GIVEN-002" not in _codes(right, None, "sports_science")


def test_a_fitted_proportional_model_with_a_unit_is_no_wrong_formula():
    request = "A spring stretches as loads are added: 1 N gives 2.0 cm, 2 N gives 4.0 cm, 3 N gives 6.0 cm. Find the extension for 2.5 N."
    assert "ST-REF-001" not in _codes("The extension rises by 2.0 cm per newton, so x = 2.0F.", request)
    wrong = "Given m = 2.0 kg and v = 3.0 m s⁻¹. Using E_k = ½mv, E_k = 0.5 × 2.0 × 3.0 = 3.0 J."      # positive: a law of the wrong dimension
    assert "ST-REF-001" in _codes(wrong, KE_REQUEST)


# ------------------------------------------------------------------ the solution set (INV-6) and how its members are read

MATH = ("Mathematics: Analysis and Approaches", "mathematics-aa-specialist")


def _sol_checks(request: str, answer: str) -> tuple[dict, set[str]]:
    rc = _send(*MATH, request, answer)
    return ({c.constraint_id: c.satisfied for c in rc.formal_checks if c.constraint_id.startswith("stem-sol")},
            {f.code for f in rc.findings if f.severity == "error"})


@pytest.mark.parametrize("request_text, answer", [
    ("Solve the equation.", "x² = 4^{1.5}, so x = 2√2."),                     # INV-6: the root −2√2 is lost
    ("Solve x³ = 4x.", "x(x² − 4) = 0, giving x = 0 or 2"),                   # a bare member is read; −2 is lost
    ("Show your working.", "x² − 5x + 6 = 0, so x = 2 or 4"),                 # a bare member that is no root
    ("Solve x³ = 4x.", "x³ = 4x\nx(x² − 4) = 0, so x = 0 or x² = 4, giving x = 0, 2 or 4"),   # the set concluded from the factors
])
def test_an_incomplete_or_wrong_solution_set_fails(request_text, answer):
    sol, errors = _sol_checks(request_text, answer)
    assert sol and False in sol.values() and "INT-SUBJ-001" in errors, (sol, errors)


@pytest.mark.parametrize("request_text, answer", [
    ("Solve the equation.", "x² = 4^{1.5}, so x = 2√2 or x = −2√2."),
    ("Solve x³ = 4x.", "x(x² − 4) = 0, giving x = 0, 2 or −2"),             # the full set, its members bare after the first
    ("Solve x³ = 4x.", "x(x² − 4) = 0 ⇒ x = 0, 2 or −2"),
    ("Show your working.", "x(x² − 4) = 0\nx = 0, 2 or −2"),
    ("Solve x³ = 4x.", "x(x² − 4) = 0, giving x = 0, ±2"),
    ("Solve x² − 5x + 6 = 0.", "x² − 5x + 6 = 0, so x = 2 or 3"),
    # a step to a listed set concludes the set, not its first value ('x² = 4' to 'x = 0' alone failed on this correct work)
    ("Solve x³ = 4x.", "x³ = 4x\nx(x² − 4) = 0, so x = 0 or x² = 4, giving x = 0, 2 or −2"),
])
def test_clean_control_a_complete_set_in_any_layout_holds(request_text, answer):
    sol, errors = _sol_checks(request_text, answer)
    assert sol and set(sol.values()) == {True} and not errors, (sol, errors)


@pytest.mark.parametrize("request_text, answer", [
    ("Solve the equation.", "x² = 9, so x = 3 is one solution."),             # the statement calls the root one of several
    ("Solve x² = 2.", "x² = 2, so x = 1.41 or −1.41 (3 s.f.)"),               # the set goes on past what is read as a value
    ("Solve the equation.", "x² = 8, so x = 2√2 or −2√2"),                    # a member written as a surd after the first
])
def test_clean_control_no_full_set_is_claimed_that_the_statement_does_not_make_or_the_reading_does_not_hold(request_text, answer):
    sol, errors = _sol_checks(request_text, answer)
    assert sol and set(sol.values()) == {True} and not errors, (sol, errors)


def test_the_same_root_line_gets_the_same_verdict_in_prose_and_in_latex():
    prose = _sol_checks("Evaluate.", "x² = 9, so x = 3.")
    latex = _sol_checks("Evaluate.", "$x^2 = 9 \\text{ so } x = 3$")
    assert prose == latex == ({"stem-sol-1": True}, set())
