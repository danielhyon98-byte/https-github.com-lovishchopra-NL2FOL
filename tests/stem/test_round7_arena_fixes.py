"""The round-7 arena's STEM findings, each reproduced and fixed at its cause, with clean controls (a correct line that must hold and a
wrong one that must still fail):

* stem-soundness-1: the reading as written ignored unit prefixes and per cent on one side ('3 × 2.0 kg = 6.0 g', '300/400 = 0.75 %');
* stem-soundness-2: an exact integer binding in Mathematics matched the next integer ('Let x = 3' substituted as 4);
* stem-soundness-3: a symbol matched a coefficient the formula writes itself ('y = 4x + 1 = 4 × 9 + 1' with x = 4);
* stem-soundness-4: the Computer Science AND dot ('A.B') was read as a full stop, so Boolean identities were checked as fragments;
* stem-soundness-5: the stated solution of simultaneous equations was not checked against the system;
* stem-soundness-6: approximation words switched on τ = 1/20 as substrings and anywhere before the relation ('linearly');
* stem-soundness-8: degree/radian conversions were compared as written (30 against 0.524);
* stem-soundness-9: a trigonometric function of a bare number passed under radians when the angle was given in degrees;
* stem-soundness-10: roots written '±' failed their algebra step under the principal root;
* stem-soundness-11: a root on the line after its equation claimed no full solution set;
* stem-soundness-12: a wrong factorisation, an identity, a chained or absolute inequality step, bits and bytes, a nuclear equation
  had no check and no finding;
* stem-precision-1: a prose value naming another quantity ('the degrees of freedom are 3') was checked as a restatement;
* stem-precision-2: a value substituted in another unit of its dimension (cm³ put in as dm³) never matched its binding;
* stem-precision-3: a substitution writing a conversion factor ('× 60') was checked only as written;
* stem-precision-5: a compound quantity ('4 min 30 s') was read as its last part;
* stem-precision-6: a bracketed per cent restating a value ('0.870 (87%)') was read as a factor;
* stem-precision-8: a comparison the text says is false was checked as asserted;
* stem-precision-9: '4 categories − 1 = 3' was read as '− 1 = 3';
* stem-precision-10: a binary numeral in nibbles ('1011 0110₂') was split;
* parser-safety-1: an overlong superscript run raised in int() and emptied the document.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.lexer import lex

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"round7-arena-stem-fixes-key-0123456789"
_DEFINITE = {"ENTAILED", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE"}


def _holds(pc, res):
    s = res.status.value
    if s == pc.expected_if_sound and not any(d.code == "E108" for d in res.diagnostics):
        return True
    if s in _DEFINITE and s != pc.expected_if_sound:
        return None if (s == "INCONSISTENT_PREMISES" and not pc.inconsistent_is_failure) else False
    return None


def decide(text: str, profile: str = "physics", request: str | None = None):
    """Every planned check of ``text`` decided by the engine: ``(check id, holds, description)``, and the codes of the findings."""
    doc = build_document(text, request, profile)
    plan = build_checks(doc, report_id="r1", request_id="q1")
    out = []
    for pc in plan.checks:
        res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy))
        out.append((pc.check_id, _holds(pc, res), pc.description))
    return out, [f.code for f in list(doc.findings) + list(plan.findings)]


def held(text: str, profile: str = "physics", request: str | None = None, prefix: str = "stem-") -> list:
    checks, _f = decide(text, profile, request)
    return [h for cid, h, _d in checks if cid.startswith(prefix)]


def receive(subject: str, answer: str, request: str = "Answer the question."):
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def engine_errors(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]


# ----------------------------------------------------------------------------------------------- stem-soundness-1
@pytest.mark.parametrize("wrong, right", [
    ("P = 2.0 kW × 3.0 = 6.0 W", "P = 2.0 kW × 3.0 = 6.0 kW"),
    ("d = 2.0 km × 3 = 6.0 m", "d = 2.0 km × 3 = 6.0 km"),
    ("I = 2 × 1.5 mA = 3.0 A", "I = 2 × 1.5 mA = 3.0 mA"),
    ("m = 4.0 g / 2 = 2.0 kg", "m = 4.0 g / 2 = 2.0 g"),
    ("Total mass = 3 × 2.0 kg = 6.0 g", "Total mass = 3 × 2.0 kg = 6.0 kg"),
    ("Efficiency = 300/400 = 0.75 %", "Efficiency = 300/400 = 75 %"),
    ("80 × 25 % = 2000", "80 × 25 % = 20"),
])
def test_the_reading_as_written_needs_consistent_units(wrong, right):
    assert held(wrong, prefix="stem-eq") == [False], wrong
    assert held(right, prefix="stem-eq") == [True], right


@pytest.mark.parametrize("line", [
    "m = 2.5 kg × 1000 = 2500 g",        # a written conversion factor
    "t = 4.5 min × 60 = 270 s",
    "v = 20 m/s × 3.6 = 72 km/h",
    "Efficiency = 300/400 × 100 = 75 %",  # × 100 makes the per cent
    "v = 120/4.0 = 30 km/h",             # bare operands standing in km and h
    "d = 20 × 25 = 0.5 km",              # bare operands in SI
    "1620 × 2% = 32.4 counts min⁻¹",
])
def test_the_reading_as_written_is_kept_where_the_units_agree(line):
    assert held(line, prefix="stem-eq") == [True], line


def test_a_prefix_slip_reaches_the_router_as_an_engine_error():
    [slip] = engine_errors(receive("Biology", "Total mass = 3 × 2.0 kg = 6.0 g.", "Calculate the total mass of three 2.0 kg samples."))
    assert "3 × 2.0 kg = 6.0 g" in slip.message
    assert not engine_errors(receive("Biology", "Total mass = 3 × 2.0 kg = 6.0 kg.", "Calculate the total mass of three 2.0 kg samples."))


# ----------------------------------------------------------------------------------------------- stem-soundness-2
def test_an_exact_integer_binding_in_mathematics_matches_only_itself():
    assert held("Let x = 3.\nThen y = 2x + 1 = 2 × 4 + 1 = 9", "mathematics_aa", prefix="stem-sub") == [False]
    assert held("Let x = 3.\nThen y = 2x + 1 = 2 × 3 + 1 = 7", "mathematics_aa", prefix="stem-sub") == [True]
    assert held("Let n = 5.\nThen s = 2n = 2 × 6 = 12", "computer_science", prefix="stem-sub") == [False]


# ----------------------------------------------------------------------------------------------- stem-soundness-3
def test_a_symbol_never_stands_for_a_coefficient_the_formula_writes():
    assert held("Let x = 4.\nThen y = 4x + 1 = 4 × 9 + 1 = 37", "mathematics_aa", prefix="stem-sub") == [False]
    assert held("Let x = 4.\nThen y = 4x + 1 = 4 × 4 + 1 = 17", "mathematics_aa", prefix="stem-sub") == [True]
    assert held("Let x = 9.\nThen y = 4x + 1 = 9 × 4 + 1 = 37", "mathematics_aa", prefix="stem-sub") == [True]  # another order still matches
    assert held("Given m = 2.0 kg and v = 3.0 m/s.\nE = ½mv² = 0.5 × 2.0 × 3.0² = 9.0 J", prefix="stem-sub") == [True]
    rc = receive("Mathematics: Analysis and Approaches", "Let x = 4. Then y = 4x + 1 = 4 × 9 + 1 = 37.", "Given x = 4, evaluate y = 4x + 1.")
    assert [f for f in engine_errors(rc) if "4x + 1 = 4 × 9 + 1" in f.message]


# ----------------------------------------------------------------------------------------------- stem-soundness-4
def test_the_computer_science_dot_is_and():
    assert [t.text for t in lex("A.B + A.C", cs=True).tokens] == ["A", "·", "B", "+", "A", "·", "C"]
    assert [t.kind for t in lex("A.B", cs=False).tokens] == ["IDENT", "PUNCT", "IDENT"]  # elsewhere a full stop, as before
    assert [t.kind for t in lex("e.g. The", cs=True).tokens][:3] == ["IDENT", "PUNCT", "IDENT"]
    assert held("A.B = B.C", "computer_science", prefix="stem-bool") == [False]
    assert held("A.B + A.C = A.(B + C)", "computer_science", prefix="stem-bool") == [True]
    assert held("(A + B).(A + C) = A + B.C", "computer_science", prefix="stem-bool") == [True]
    assert held("A'.B' = (A + B)'", "computer_science", prefix="stem-bool") == [True]
    rc = receive("Computer Science", "A.B + A.C = A.(B + C)", "Simplify the Boolean expression A.B + A.C.")
    assert not engine_errors(rc) and [c.satisfied for c in rc.formal_checks if c.constraint_id.startswith("stem-bool")] == [True]


def test_a_relation_glued_to_a_longer_expression_by_a_full_stop_is_withheld():
    checks, findings = decide("Ab.B = B.C", "computer_science")
    assert not checks and "ST-PARSE-001" in findings


# ----------------------------------------------------------------------------------------------- stem-soundness-5
@pytest.mark.parametrize("text, holds", [
    ("2x + y = 7 and x − y = 2, so x = 5 and y = 3", False),
    ("2x + y = 7 and x − y = 2, so x = 3 and y = 1", True),
    ("2x + y = 7 and x − y = 2, so x = 3 and y = 2", False),  # the right x, a wrong y: never a premise for x
    ("Solving the simultaneous equations\n2x + y = 7\nx − y = 2\nx = 3, y = 2", False),
    ("Solving the simultaneous equations\n2x + y = 7\nx − y = 2\nx = 3, y = 1", True),
    ("2x + y = 8 and x − y = 2, so x = 3.33 and y = 1.33", True),   # rounded values: some point of their intervals solves the system
    ("2x + y = 8 and x − y = 2, so x = 3.33 and y = 1.43", False),
])
def test_a_stated_solution_is_checked_against_every_equation_of_the_system(text, holds):
    checks, _f = decide(text, "mathematics_aa")
    sol = [(h, d) for cid, h, d in checks if cid.startswith("stem-sol")]
    assert [h for h, _d in sol] == [holds], checks
    assert "against every equation of the system" in sol[0][1]
    assert not [cid for cid, h, _d in checks if cid.startswith("stem-alg") and h is False], checks  # no false step from one equation


def test_simultaneous_equations_through_the_hub():
    rc = receive("Mathematics: Analysis and Approaches", "2x + y = 7 and x − y = 2, so x = 5 and y = 3.",
                 "Solve the simultaneous equations 2x + y = 7 and x - y = 2.")
    assert engine_errors(rc)
    rc = receive("Mathematics: Analysis and Approaches", "2x + y = 7 and x − y = 2, so x = 3 and y = 1.",
                 "Solve the simultaneous equations 2x + y = 7 and x - y = 2.")
    assert not engine_errors(rc) and [c.satisfied for c in rc.formal_checks if c.constraint_id.startswith("stem-sol")] == [True]


def test_a_rearrangement_in_two_letters_is_still_a_step():
    # no word names a system: the line after an equation in two letters is a step from it, as before
    assert held("2x + y = 10\n2x = 10 − y", "mathematics_aa", prefix="stem-alg") == [True]
    assert held("2x + y = 10\n2x = 10 + y", "mathematics_aa", prefix="stem-alg") == [False]
    assert held("x + 2y = 10\n2x + 4y = 20", "mathematics_aa", prefix="stem-alg") == [True]


# ----------------------------------------------------------------------------------------------- stem-soundness-6
@pytest.mark.parametrize("text", [
    "The speed increases linearly, so v = 2.0 × 3.0 = 6.3 m/s",
    "The ball moves for about 3 s, and v = 2.0 × 3.0 = 6.3 m/s",
    "Around the bend, v = 2.0 × 3.0 = 6.3 m/s",
    "v = 2.0 × 3.0 = 6.3 m/s",
])
def test_an_approximation_word_must_qualify_the_relation_itself(text):
    assert held(text, prefix="stem-eq") == [False], text


def test_an_approximation_word_before_the_relation_still_gives_its_slack():
    assert held("The speed is about 2.0 × 3.0 = 6.3 m/s", prefix="stem-eq") == [True]
    assert held("v ≈ 2.0 × 3.0 ≈ 6.3 m/s", prefix="stem-eq") == [True]
    assert held("Mix thoroughly; then n = 2.0 × 3.0 = 6.3 mol", "chemistry", prefix="stem-eq") == [False]


# ----------------------------------------------------------------------------------------------- stem-soundness-8
@pytest.mark.parametrize("text, holds", [
    ("θ = 30° = 0.524 rad.", True), ("θ = 30.0° = 0.600 rad.", False), ("2 rad = 115° (to 3 s.f.).", True), ("2.0 rad = 125°", False),
    ("180° = π rad.", True), ("90° = π rad.", False),
])
def test_a_degree_radian_conversion_is_compared_in_radians(text, holds):
    checks, _f = decide(text)
    assert [h for cid, h, _d in checks if cid == "stem-eq-1"] == [holds], checks
    assert "a degree read as π/180 rad" in next(d for cid, _h, d in checks if cid == "stem-eq-1")


def test_angles_in_degrees_on_both_sides_keep_their_reading():
    assert held("α = 90° − 30° = 60°", prefix="stem-eq") == [True]
    assert held("sin 30° = 0.5", prefix="stem-eq") == [True]


# ----------------------------------------------------------------------------------------------- stem-soundness-9
def test_a_radian_mode_slip_fails_when_the_angle_is_in_degrees():
    req = "Calculate the horizontal component of a 10 N force at 60° to the horizontal."
    assert held("The horizontal component is F cos θ = 10 cos 60 = −9.5 N.", request=req, prefix="stem-eq") == [False]
    assert held("The horizontal component is F cos θ = 10 cos 60 = 5.0 N.", request=req, prefix="stem-eq") == [True]
    assert held("cos 60 = −0.95", prefix="stem-eq") == [False]  # a whole number of radians beyond a full turn is no bare angle
    assert held("cos 60 = 0.50", prefix="stem-eq") == [True]
    assert held("sin 0.5 = 0.479", prefix="stem-eq") == [True]  # a small argument may be in radians, as before
    [slip] = engine_errors(receive("Physics", "The horizontal component is F cos θ = 10 cos 60 = −9.5 N.", req))
    assert "10 cos 60 = −9.5 N" in slip.message


# ----------------------------------------------------------------------------------------------- stem-soundness-10
def test_roots_written_with_plus_minus_hold_their_step():
    checks, _f = decide("x² = 2 ⇒ x = ±1.41", "mathematics_aa")
    assert sorted((cid.rsplit("-", 1)[0], h) for cid, h, _d in checks) == [("stem-alg", True), ("stem-sol", True)]
    checks, _f = decide("x² = 2 ⇒ x = ±1.51", "mathematics_aa")
    assert sorted((cid.rsplit("-", 1)[0], h) for cid, h, _d in checks) == [("stem-alg", False), ("stem-sol", False)]
    rc = receive("Mathematics: Analysis and Approaches", "x² = 2 ⇒ x = ±1.41", "Solve x^2 = 2, giving your answers to 3 s.f.")
    assert not engine_errors(rc)


# ----------------------------------------------------------------------------------------------- stem-soundness-11
@pytest.mark.parametrize("text, holds", [
    ("x² = 3x\nDividing by x, x = 3", False),
    ("x² − 4 = 0\nx = 2", False),
    ("x² − 4 = 0\nx = 2\nx = −2", True),          # the roots on consecutive lines are one stated set
    ("x² − 4 = 0\nx = 2 or x = −2", True),
    ("x² − 5x + 6 = 0\n(x − 2)(x − 3) = 0\nx = 2\nx = 3", True),
    ("x² − 4 = 0\nOne root is x = 2", True),      # a line giving one root of several claims no set
    ("x² − 4 = 0\nSince x is a length, x = 2", True),
])
def test_roots_on_the_line_after_their_equation_claim_the_solution_set(text, holds):
    checks, _f = decide(text, "mathematics_aa")
    assert [h for cid, h, _d in checks if cid.startswith("stem-sol")] == [holds], checks


# ----------------------------------------------------------------------------------------------- stem-soundness-12
@pytest.mark.parametrize("wrong, right", [
    ("Factorising, x² + 5x + 6 = (x + 2)(x + 4).", "Factorising, x² + 5x + 6 = (x + 2)(x + 3)."),
    ("Expanding, (a + b)² = a² + b²", "Expanding, (a + b)² = a² + 2ab + b²"),
])
def test_a_stated_factorisation_or_expansion_is_an_identity(wrong, right):
    assert held(wrong, "mathematics_aa", prefix="stem-alg") == [False]
    assert held(right, "mathematics_aa", prefix="stem-alg") == [True]
    assert held("(a + b)² = a² + b²", "mathematics_aa", request="Expand (a + b)^2.", prefix="stem-alg") == [False]
    assert held("x² + 5x + 6 = (x + 2)(x + 4)", "mathematics_aa", prefix="stem-alg") == []  # no word names an identity: an equation, as before


def test_bits_and_bytes_are_units():
    assert held("32 bits = 8 bytes", "computer_science", prefix="stem-cnv") == [False]
    assert held("32 bits = 4 bytes", "computer_science", prefix="stem-cnv") == [True]
    assert held("2 KiB = 2048 bytes", "computer_science", prefix="stem-cnv") == [True]


def test_chained_and_absolute_inequalities_and_nuclear_equations_are_named():
    _c, findings = decide("|x − 1| < 3, so −3 < x − 1 < 3, giving −2 < x < 5.", "mathematics_aa")
    assert "ST-UNDEC-001" in findings
    _c, findings = decide("²³⁸₉₂U → ²³⁴₉₁Th + ⁴₂He")
    assert "ST-UNDEC-001" in findings
    _c, findings = decide("For 0 < t < 2, both factors are positive.", "mathematics_aa")
    assert "ST-UNDEC-001" not in findings  # a condition, not a step


def test_a_line_opening_with_an_absolute_value_is_no_table():
    doc = build_document("|x − 1| < 3", None, "mathematics_aa")
    assert not [s for s in doc.spans.spans if s.kind == "table"]
    doc = build_document("| a | b |\n| 1 | 2 |", None, "mathematics_aa")
    assert [s for s in doc.spans.spans if s.kind == "table"]


# ----------------------------------------------------------------------------------------------- stem-precision-1
def test_a_prose_value_naming_another_quantity_is_no_restatement():
    for text in ("χ² = 104.976 + 87.616 + 99.856 + 92.416 = 384.864. There are four classes, so the degrees of freedom are 3.",
                 "r = 0.035/12 = 0.0029167. Payments are monthly, so the loan lasts 60 months."):
        assert held(text, "mathematics_ai", prefix="stem-res") == [], text
    assert held("x = 15/3 = 5. Therefore the answer is 6.", "mathematics_aa", prefix="stem-res") == [False]
    assert held("x = 15/3 = 5. Therefore the answer is 5.", "mathematics_aa", prefix="stem-res") == [True]
    assert held("n = 24/8.0 = 3. So there are 4 half-lives.", "mathematics_aa", prefix="stem-res") == [False]


# ----------------------------------------------------------------------------------------------- stem-precision-2 and -3
@pytest.mark.parametrize("text, holds", [
    ("V = 25.0 cm³ and c = 0.100 mol dm⁻³, so n = cV = 0.100 × 0.0250 = 2.50 × 10⁻³ mol", True),
    ("V = 25.0 cm³ and c = 0.100 mol dm⁻³, so n = cV = 0.100 × 0.0350 = 3.50 × 10⁻³ mol", False),
    ("V = 25.0 cm³ and c = 0.100 mol dm⁻³, so n = cV = 0.100 × 25.0 / 1000 = 2.50 × 10⁻³ mol", True),
    ("V = 250 cm³ and n = 0.0428 mol, so c = n/V = 0.0428/0.250 = 0.171 mol dm⁻³", True),
    ("V = 250 cm³ and n = 0.0428 mol, so c = n/V = 0.0428/0.350 = 0.122 mol dm⁻³", False),
    ("P = 2200 W and t = 4.5 min, so E = Pt = 2200 × 4.5 × 60 = 5.94 × 10⁵ J", True),
    ("P = 2.2 kW, t = 4.5 min, so E = Pt = 2.2 × 10³ × 4.5 × 60 = 5.94 × 10⁵ J", True),
    ("P = 2200 W and t = 4.5 min, so E = Pt = 2200 × 5.5 × 60 = 7.26 × 10⁵ J", False),
])
def test_a_substitution_in_another_unit_or_with_its_conversion_factor(text, holds):
    assert held(text, "chemistry" if "mol" in text else "physics", prefix="stem-sub") == [holds], text


# ----------------------------------------------------------------------------------------------- stem-precision-5
@pytest.mark.parametrize("text, holds", [
    ("t = 4 min 30 s = 270 s", True), ("t = 4 min 30 s = 34 s", False), ("The mass is 1 kg 250 g = 1.25 kg", True),
    ("The mass is 1 kg 250 g = 251 g", False), ("t = 1 h 2 min 3 s = 3723 s", True), ("d = 5 m 20 cm = 5.20 m", True),
])
def test_a_compound_quantity_is_the_sum_of_its_parts(text, holds):
    assert held(text, prefix="stem-") == [holds], text


def test_a_compound_quantity_in_a_longer_conversion_line():
    assert held("Convert the time first: 4 min 30 s = (4 × 60 + 30) s = 270 s") == [True, True]


# ----------------------------------------------------------------------------------------------- stem-precision-6
def test_a_bracketed_per_cent_after_a_value_restates_it():
    assert held("η = 0.5166/0.594 = 0.870 (87%)", prefix="stem-eq") == [True]
    assert held("p = 3/8 = 0.375 (37.5%)", "mathematics_aa", prefix="stem-eq") == [True]
    assert held("η = 0.5166/0.594 = 0.770 (77%)", prefix="stem-eq") == [False]
    assert held("x = 2 (3 + 4) = 14", "mathematics_aa", prefix="stem-eq") == [True]  # a bracket of arithmetic is still a factor


# ----------------------------------------------------------------------------------------------- stem-precision-8
@pytest.mark.parametrize("text, holds", [
    ("The condition low <= high becomes 2 <= 1, which is false, so the loop stops.", True),
    ("Since 5 > 8 is false, the else branch runs.", True),
    ("the final test (2 <= 1) fails before the body runs.", True),
    ("Since 5 > 3 is false, the else branch runs.", False),   # the negation is checked: 5 ≤ 3 does not hold
    ("Since 5 > 3, the if branch runs.", True),
])
def test_a_comparison_stated_false_is_checked_negated(text, holds):
    checks, _f = decide(text, "computer_science")
    assert [h for cid, h, _d in checks if cid.startswith("stem-cmp")] == [holds], checks


# ----------------------------------------------------------------------------------------------- stem-precision-9
def test_a_count_noun_before_a_sign_withholds_the_cut_relation():
    for text in ("The degrees of freedom are 4 categories − 1 = 3.", "degrees of freedom = 4 categories − 1 = 3"):
        checks, findings = decide(text, "biology")
        assert not [h for _c, h, _d in checks if h is False] and "ST-PARSE-001" in findings, text
    assert held("so −2x > 4", "mathematics_aa") == []  # a sign after a short word opens an expression, as before


# ----------------------------------------------------------------------------------------------- stem-precision-10
def test_a_numeral_in_nibbles_is_one_based_numeral():
    text = ("128 + 32 + 16 + 4 + 2 = 182₁₀. Grouping the bits in fours from the right, 1011 is B and 0110 is 6, so 1011 0110₂ = B6₁₆.")
    assert held(text, "computer_science", prefix="stem-base") == [True, True]
    assert held("1011 0110₂ = B7₁₆", "computer_science", prefix="stem-base") == [False]
    assert held("1011 0110₂ = 182₁₀", "computer_science", prefix="stem-base") == [True]


# ----------------------------------------------------------------------------------------------- parser-safety-1
def test_an_overlong_superscript_run_is_bounded_and_the_rest_still_read():
    bomb = "Energy E = 2" + "²" * 4301 + " J."
    doc = build_document(bomb, None, "physics")
    assert "ST-LIM-001" in [f.code for f in doc.findings] and "ST-INTERNAL-001" not in [f.code for f in doc.findings]
    t = time.perf_counter()
    lex("2" + "²" * 50_000)
    assert time.perf_counter() - t < 2.0
    answer = "(a) The speed is v = d / t = 120 m / 4.0 s = 50 m s⁻¹.\n\nNote: the scale factor is k = 2" + "²" * 4301 + ".\n"
    rc = receive("Physics", answer, "A car travels 120 m in 4.0 s. Calculate its speed.")
    assert [f for f in engine_errors(rc) if "120 m / 4.0 s = 50" in f.message]
    assert not [f for f in rc.structural_findings if f.code == "ST-INTERNAL-001"]
