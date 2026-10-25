"""The external STEM review of 12 October 2026: findings S1, S2, S5 and S7 and the policy on part scope, reproduced with
the reviewer's probes and fixed where the reading went wrong. Every test states the reviewer's expected behaviour with
negative controls: the correct answer still passes, and a really wrong answer still fails.

* S1: a grouped temperature such as ``(20 + 5) °C`` lost the Celsius offset (``= 25 K`` passed, ``= 298.15 K`` failed). A
  temperature on an offset scale is now converted once, on the value its side states (a unit written after a group applies
  to the evaluated group), never term by term; the same holds for a comparison, a restatement, a Given value and a symbol
  bound to such a temperature. Where it cannot be established whether a term is a temperature or a difference, the
  relation is undecided, never decided under a guess.
* S2: "Calculate 1/2 exactly, without rounding." accepted ``1/2 = 0.51``. Stated exactness (in the request, or in the
  answer beside the relation) makes the comparison exact; a stated decimal over exact operands is read as rounded to its
  last digit and earns no relative slack from its spelling, so ``0.51`` and ``51/100`` get the same verdict; a rounded
  request keeps its tolerance; every check records the policy that decided it.
* S5: ``x² = 4 ⇒ x = −2 or x = 2`` was an error while ``x = 2 or x = −2`` and ``x = ±2`` passed. A root set is checked as a
  set (``stem-sol``), whatever order or spelling its members take.
* S7: ``|−2| = 2`` was masked as a table. Bars that open a line are a table only with a table's structure.
* Part scope: a binding stated in one part validated a calculation in another (``(a) x = 2, y = x + 1 = 5`` passed with
  part (b)'s ``x = 4``). Bindings now hold in their own part from where they are stated.
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.nodes import Neg, Num, Quantity, Sym, WithUnit, BinOp
from epinoic_logic.stem.numbers import exact_integer
from epinoic_logic.stem.to_ir import affine_role
from epinoic_logic.stem.tolerance import SHORT_RULE, exactness_phrase, rounding_phrase
from epinoic_logic.stem.units import parse_unit

KEY = b"stem-review-checks-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
PHYS = "Physics"
MAA = "Mathematics: Analysis and Approaches"


def receive(subject: str, request: str, answer: str):
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    msg, _req, _rq = hub.dispatch("t", agent, request)
    _reply, rc = hub.receive("t", msg.message_id, answer, agent_id=agent, report_id="r1")
    return rc


def errors(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]


def checks(rc) -> dict[str, tuple]:
    return {c.constraint_id: (c.satisfied, c.formal_status) for c in rc.formal_checks}


def decide(text: str, profile: str = "physics", request: str | None = None) -> dict[str, tuple[bool | None, str, str]]:
    """Every planned check of ``text`` decided by the engine: id -> (holds, status, failure severity)."""
    doc = build_document(text, request, profile)
    plan = build_checks(doc, report_id="r", request_id="q")
    out: dict[str, tuple[bool | None, str, str]] = {}
    for pc in plan.checks:
        res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy))
        status = res.status.value
        holds = True if status == pc.expected_if_sound else (False if status in ("ENTAILED", "COUNTEREXAMPLE", "SATISFIABLE", "UNSATISFIABLE") else None)
        out[pc.check_id] = (holds, status, pc.failure_severity)
    return out


def findings(text: str, profile: str = "physics", request: str | None = None) -> list[str]:
    doc = build_document(text, request, profile)
    plan = build_checks(doc, report_id="r", request_id="q")
    return [f.code for f in doc.findings] + [f.code for f in plan.findings]


def holds(text: str, profile: str = "physics", request: str | None = None) -> bool:
    """Every check holds (and there is at least one)."""
    out = decide(text, profile, request)
    return bool(out) and all(v[0] is True for v in out.values())


def fails(text: str, profile: str = "physics", request: str | None = None) -> bool:
    """Some check fails."""
    return any(v[0] is False for v in decide(text, profile, request).values())


# =============================================================================================== S1: temperatures on an offset scale

S1_REQUEST = "Convert the absolute temperature (20 + 5) °C to kelvin."


def test_s1_a_grouped_celsius_temperature_keeps_its_offset_like_the_literal():
    right = receive(PHYS, S1_REQUEST, "T = (20 + 5) °C = 298.15 K.")
    assert not errors(right) and checks(right) == {"stem-eq-1": (True, "ENTAILED")} and right.status.value == "ACCEPTED"
    wrong = receive(PHYS, S1_REQUEST, "T = (20 + 5) °C = 25 K.")
    [err] = errors(wrong)
    assert err.claim_ids == ["s1.1"] and checks(wrong) == {"stem-eq-1": (False, "COUNTEREXAMPLE")}
    assert "c = 5963/20" in err.message and "r = 25" in err.message          # 298.15 K computed, 25 K stated
    literal = receive(PHYS, S1_REQUEST, "T = 25 °C = 298.15 K.")             # the literal control is unchanged
    assert not errors(literal) and checks(literal) == {"stem-cnv-1": (True, "ENTAILED")}


@pytest.mark.parametrize("answer,ok", [
    ("T = (20 + 5) °F = 269.261 K.", True), ("T = (20 + 5) °F = 25 K.", False), ("T = 25 °F = 269.261 K.", True), ("T = 25 °F = 25 K.", False),
    ("T = (100 − 5) °C = 368.15 K", True), ("T = (100 − 5) °C = 95 K", False), ("T = −(5) °C = 268.15 K", True), ("T = (20 + 5) °C = 77 °F", True),
    ("T = (20 + 5) °C = 25 °F", False),
])
def test_s1_fahrenheit_and_signed_groups_convert_on_the_evaluated_value(answer, ok):
    assert (holds(answer) if ok else fails(answer)), (answer, decide(answer))


def test_s1_the_offset_is_never_applied_term_by_term():
    # a temperature combined with other terms against another scale: whether each term is a temperature or a difference
    # cannot be established, so the relation is undecided (never an error, never a pass)
    for text in ("20 °C + 5 °C = 298.15 K", "20 °C + 5 °C = 25 K", "40 °C − 20 °C = 20 K"):
        assert decide(text) == {} and "ST-UNDEC-001" in findings(text), text
    # with a bare number the relation is still read as written, and since its SI reading is not established a failure is a
    # warning (INT-SUBJ-004), never an error; the common spelling of the conversion passes as written
    assert decide("2 × 10 °C = 293.15 K") == {"stem-eq-1": (False, "COUNTEREXAMPLE", "warning")}
    assert holds("T = 25 °C + 273 = 298 K")
    # the statement says it is a change: every °C is a difference
    assert holds("ΔT = 40 °C − 20 °C = 20 K") and fails("ΔT = 40 °C − 20 °C = 293 K")
    assert holds("The temperature rise is ΔT = 20 °C = 20 K.") and fails("ΔT = 20 °C = 293 K")
    # every temperature on one scale: compared on that scale, where the offset cancels
    assert holds("20 °C + 5 °C = 25 °C") and fails("20 °C + 5 °C = 28 °C")
    # inside a compound unit °C is an interval: specific heat is unchanged
    assert holds("Q = mcΔT = 2.0 kg × 4200 J kg⁻¹ °C⁻¹ × 10 °C = 84000 J") and fails("Q = mcΔT = 2.0 kg × 4200 J kg⁻¹ °C⁻¹ × 10 °C = 8400 J")


def test_s1_comparisons_restatements_givens_and_symbols_keep_the_offset():
    assert holds("30 °C > 295 K") and fails("30 °C < 295 K") and holds("25 °C < 300.0 K")
    assert holds("T₁ = 30 °C and T₂ = 295 K, so T₁ > T₂.") and fails("T₁ = 30 °C and T₂ = 295 K, so T₁ < T₂.")
    assert holds("T = 20 + 5 = 25 °C. The temperature is therefore 298 K.")
    assert fails("T = 20 + 5 = 25 °C. The temperature is therefore 25 K.")
    assert holds("Given: T = 25 °C.", request="The gas is at 298.15 K.")
    given = decide("Given: T = 25 °C.", request="The gas is at 310 K.")
    assert given == {"stem-giv-1": (False, "COUNTEREXAMPLE", "warning")}
    # a value substituted for a temperature symbol: in kelvin with the offset (pV = nRT with T = 25 °C written as 298)
    assert holds("T = 25 °C. n = pV/(RT) = 101000 × 0.0010/(8.31 × 298) = 0.0408 mol")


def test_s1_the_encoder_reads_a_side_as_a_whole():
    c = parse_unit("°C")
    k = parse_unit("K")
    n5 = Num(exact_integer(5), 0, 1)
    q = Quantity(exact_integer(25), c, 0, 5)
    assert affine_role(q) == "point" and affine_role(Neg(q)) == "point"
    assert affine_role(WithUnit(BinOp("+", Num(exact_integer(20)), n5), c)) == "point"          # (20 + 5) °C
    assert affine_role(BinOp("+", q, Quantity(exact_integer(5), c))) == "nested"               # 20 °C + 5 °C
    assert affine_role(BinOp("*", n5, q)) == "nested"                                          # 5 × 25 °C
    assert affine_role(Quantity(exact_integer(298), k)) == "none"
    assert affine_role(Sym("T"), frozenset({"T"})) == "point" and affine_role(BinOp("+", Sym("T"), n5), frozenset({"T"})) == "nested"


# =============================================================================================== symbols bound with units

def test_symbols_bound_with_units_are_compared_in_si():
    # m₁ = 500 g and m₂ = 1.0 kg are 0.5 kg and 1.0 kg, never 500 and 1.0 as written
    assert holds("m₁ = 500 g and m₂ = 1.0 kg, so m₁ < m₂.") and fails("m₁ = 500 g and m₂ = 1.0 kg, so m₁ > m₂.")


# =============================================================================================== S2: exactness is task intent

S2_REQUEST = "Calculate 1/2 exactly, without rounding."


@pytest.mark.parametrize("answer,ok", [("1/2 = 0.51", False), ("Exactly 1/2 = 0.51.", False), ("1/2 = 51/100", False), ("1/2 = 0.50", True),
                                       ("1/2 = 0.5", True), ("1/2 = 50/100", True)])
def test_s2_requested_exactness_makes_the_comparison_exact(answer, ok):
    rc = receive(MAA, S2_REQUEST, answer)
    if ok:
        assert not errors(rc) and rc.status.value == "ACCEPTED" and checks(rc) == {"stem-eq-1": (True, "ENTAILED")}
    else:
        [err] = errors(rc)
        assert err.claim_ids == ["m1.1"] and checks(rc) == {"stem-eq-1": (False, "COUNTEREXAMPLE")}


@pytest.mark.parametrize("request_text", [S2_REQUEST, "Calculate 1/2.", "Calculate 1/2 to 2 decimal places.", None])
def test_s2_equivalent_spellings_get_the_same_verdict_under_one_policy(request_text):
    wrong = [decide(f"1/2 = {s}", "mathematics_aa", request_text)["stem-eq-1"][0] for s in ("0.51", "51/100")]
    right = [decide(f"1/2 = {s}", "mathematics_aa", request_text)["stem-eq-1"][0] for s in ("0.5", "0.50", "50/100", "5/10")]
    assert wrong == [False, False] and right == [True] * 4, (request_text, wrong, right)


def test_s2_a_rounded_request_keeps_its_tolerance():
    req = "Calculate 1/3 to 2 decimal places."
    assert holds("1/3 = 0.33", "mathematics_aa", req) and fails("1/3 = 0.34", "mathematics_aa", req)
    # a request that asks for both keeps the rounded tolerance
    assert holds("1/3 = 0.33", "mathematics_aa", "Find the exact value of 1/3, then give it to 2 decimal places.")
    # the same answer under a request for exactness fails
    assert fails("1/3 = 0.33", "mathematics_aa", "Calculate 1/3 exactly.") and holds("1/3 = 1/3", "mathematics_aa", "Calculate 1/3 exactly.")


def test_s2_under_a_stated_rounding_every_spelling_of_the_value_is_a_rounding():
    # a rounding stated by the request or beside the relation reads the stated value as a rounding whatever its spelling:
    # no exact mode, an integer keeps R1's half-width and a fraction that of its decimal expansion (33/100 as 0.33)
    req = "Calculate 1/3 to 2 decimal places."
    assert [holds(f"1/3 = {s}", "mathematics_aa", req) for s in ("0.33", "33/100")] == [True, True]
    assert [fails(f"1/3 = {s}", "mathematics_aa", req) for s in ("0.34", "34/100")] == [True, True]
    req = "Calculate 7/3 to the nearest integer."
    assert holds("7/3 = 2", "mathematics_aa", req) and fails("7/3 = 3", "mathematics_aa", req)
    assert holds("1000/3 = 333", "mathematics_aa", "Calculate 1000/3 to the nearest whole number.")
    assert holds("22/7 = 157/50", "mathematics_aa", "Calculate 22/7 to 3 significant figures.")
    assert holds("7/3 = 2 (to the nearest integer)", "mathematics_aa") and holds("1/3 = 33/100 (to 2 d.p.)", "mathematics_aa")
    # the same in an evaluation under a binding and in a step
    req = "Calculate y to the nearest integer."
    assert holds("x = 7\ny = x/3 = 2", "mathematics_aa", req) and fails("x = 7\ny = x/3 = 3", "mathematics_aa", req)
    req = "Solve 3x = 7, giving x to the nearest integer."
    assert holds("3x = 7 ⇒ x = 2", "mathematics_aa", req) and fails("3x = 7 ⇒ x = 3", "mathematics_aa", req)
    # negative controls: with no rounding stated, an integer or a fraction is an exact claim, and a decimal a rounding
    for text in ("7/3 = 2", "1/3 = 33/100", "x = 7\ny = x/3 = 2", "3x = 7 ⇒ x = 2"):
        assert fails(text, "mathematics_aa"), text
    assert holds("1/3 = 0.33", "mathematics_aa")
    [pc] = build_checks(build_document("7/3 = 2", "Calculate 7/3 to the nearest integer.", "mathematics_aa"), report_id="r", request_id="q").checks
    assert pc.tolerance.startswith("rounded, as the request asks ('nearest')") and "whatever its spelling" in pc.tolerance


def test_s2_a_rounded_value_in_a_step_earns_no_slack_from_its_spelling():
    # R2 in an algebra step: over exact operands a stated decimal is a rounding to its last digit and no more, as a fraction is
    for text in ("2x = 1 ⇒ x = 0.51", "2x = 1 ⇒ x = 51/100", "3x = 1 ⇒ x = 0.34", "x² = 2 ⇒ x = ±1.42"):
        assert fails(text, "mathematics_aa"), text
    for text in ("2x = 1 ⇒ x = 0.5", "2x = 1 ⇒ x = 1/2", "3x = 1 ⇒ x = 0.33", "3x = 1 ⇒ x = 0.333", "x² = 2 ⇒ x = ±1.41"):
        assert holds(text, "mathematics_aa"), text
    # a measured operand keeps the 1 % slack: 0.505 is 0.5 within 1 %, not within its last digit
    assert holds("2.0x = 1.0 ⇒ x = 0.505", "mathematics_aa") and fails("2x = 1 ⇒ x = 0.505", "mathematics_aa")
    # under a stated exactness the step is exact
    assert fails("2x = 1 ⇒ x = 0.51", "mathematics_aa", "Solve 2x = 1 exactly.")
    assert holds("2x = 1 ⇒ x = 0.5", "mathematics_aa", "Solve 2x = 1 exactly.")


def test_s2_the_answer_s_own_words_and_the_part_decide():
    assert fails("1/3 = 0.333 exactly", "mathematics_aa")
    assert holds("1/3 = 0.33 (to 2 d.p.)", "mathematics_aa", "Find 1/3 exactly.")      # the answer states a rounded value
    req = "(a) Calculate 1/2 exactly. (b) Calculate 1/3 to 3 decimal places."
    assert holds("(a) 1/2 = 0.5\n(b) 1/3 = 0.333", "mathematics_aa", req)
    assert decide("(a) 1/2 = 0.51\n(b) 1/3 = 0.333", "mathematics_aa", req) == {
        "stem-eq-1": (False, "COUNTEREXAMPLE", "error"), "stem-eq-2": (True, "ENTAILED", "error")}
    # "exactly" before a count, or negated, states no exactness
    assert holds("Give exactly two reasons. 2/3 = 0.67", "mathematics_aa", "Give exactly two reasons and calculate 2/3.")
    # a request's exactness does not make a measured quantity exact; the answer's own slack for measured data is kept
    assert holds("t = 2.0/3.0 = 0.67 s", "physics", "Calculate exactly how long it takes.")
    assert holds("v = 2.0/4.0 = 0.51 m/s", "physics")


def test_s2_over_exact_operands_a_stated_decimal_earns_no_slack_from_its_spelling():
    for text in ("1/2 = 0.51", "2/3 = 0.66", "5/3 = 1.6"):                    # not roundings of the computed value
        assert fails(text, "mathematics_aa"), text
    for text in ("1/3 = 0.33", "1/3 = 0.333", "2/3 = 0.67", "√2 = 1.41", "100/7 = 14.29", "π × 5² = 78.5", "ln 2 = 0.693", "2/3 = 66.7%"):
        assert holds(text, "mathematics_aa"), text
    # rounded intermediates written on the stated side are measured values: their slack stays
    assert holds("ln 50 / ln 2 = 3.912/0.6931 = 5.64", "mathematics_aa")


def test_s2_every_check_records_the_policy_that_decided_it():
    def plan(text, profile="mathematics_aa", request=None):
        return build_checks(build_document(text, request, profile), report_id="r", request_id="q").checks

    expected = {
        ("1/2 = 0.51", S2_REQUEST): "exact, as the request states ('exactly')",
        ("Exactly 1/2 = 0.51.", None): "exact, as the answer states ('exactly')",
        ("1/3 = 0.33", "Calculate 1/3 to 2 decimal places."): "rounded, as the request asks ('decimal places')",
        ("1/2 = 0.51", None): "rounded to its stated digits, by the written form",
        ("1/2 = 1/2", None): "exact, by the written form",
        ("v = 2.0/4.0 = 0.51 m/s", None): "measured, by the written form",
        ("1/2 ≈ 0.51", None): "approximate",
    }
    for (text, request), start in expected.items():
        [pc] = plan(text, request=request)
        assert pc.tolerance.startswith(start), (text, pc.tolerance)
        assert f"tolerance policy: {pc.tolerance}" in pc.description and f"tolerance policy: {pc.tolerance}" in pc.problem["notes"]
    # every kind records one, written into the signed problem
    text = "x² − 5x + 6 = 0\n(x − 2)(x − 3) = 0\nx = 2 or x = 3\nm = 2.0 kg, a = 3.0 m s⁻², F = ma = 2.0 × 3.0 = 6.0 N. So F = 6.0 N."
    for pc in plan(text, "physics"):
        assert pc.tolerance and "tolerance policy:" in pc.problem["notes"], pc.check_id
    assert "measured data" in SHORT_RULE and "stated exactness" in SHORT_RULE and len(SHORT_RULE) <= 300


@pytest.mark.parametrize("text,exact,rounded", [
    ("Calculate 1/2 exactly, without rounding.", "exactly", ""), ("Find the exact value of sin 60°.", "exact value", ""),
    ("Do not round your answer.", "do not round", ""), ("Leave your answer unrounded.", "unrounded", ""),
    ("Give exactly two reasons.", "", ""), ("Give your answer to exactly 3 significant figures.", "", "significant figures"),
    ("It need not be exact.", "", ""), ("The answer is not exactly 0.5.", "", ""), ("Calculate 1/3 to 2 decimal places.", "", "decimal places"),
    ("Round to the nearest integer.", "", "nearest"), ("Calculate the speed.", "", ""),
])
def test_s2_the_phrase_readers(text, exact, rounded):
    assert exactness_phrase(text) == exact and rounding_phrase(text) == rounded


# =============================================================================================== S5: a root set is a set

@pytest.mark.parametrize("answer", ["x² = 4 ⇒ x = -2 or x = 2", "x² = 4 ⇒ x = 2 or x = -2", "x² = 4 ⇒ x = ±2", "x² = 4\nx = -2 or x = 2"])
def test_s5_a_root_set_gets_one_verdict_in_any_order_or_spelling(answer):
    rc = receive(MAA, "Solve the quadratic equation.", answer)
    assert not errors(rc) and rc.status.value == "ACCEPTED", [f.message[:160] for f in rc.findings]
    assert checks(rc)["stem-sol-1"] == (True, "ENTAILED")
    assert not [f for f in rc.structural_findings if f.code == "ST-ALG-001"]        # the full set is stated: no lost-root note


@pytest.mark.parametrize("answer", ["x² = 4 ⇒ x = -2 or x = 3", "x² = 4 ⇒ x = 3 or x = -2", "x² = 4 ⇒ x = 3 or x = -3", "x² = 4 ⇒ x = ±3"])
def test_s5_a_wrong_root_set_still_fails_in_any_order(answer):
    rc = receive(MAA, "Solve the quadratic equation.", answer)
    assert errors(rc) and checks(rc)["stem-sol-1"] == (False, "COUNTEREXAMPLE")


@pytest.mark.parametrize("answer", ["x² = 2 ⇒ x = -1.41 or x = 1.41", "x² = 2 ⇒ x = 1.41 or x = -1.41", "x² = 2 ⇒ x = ±1.41",
                                    "x² = 2\nx = ±1.41"])
def test_s5_rounded_roots_get_one_verdict_in_any_order_or_spelling(answer):
    # '±1.41' states two rounded roots: the step to it reads each sign's value within its last digit, as the set check does
    out = decide(answer, "mathematics_aa")
    assert out and all(v[0] is True for v in out.values()), out
    assert "ST-ALG-001" not in findings(answer, "mathematics_aa")


@pytest.mark.parametrize("answer", ["x² = 2 ⇒ x = -1.42 or x = 1.42", "x² = 2 ⇒ x = 1.42 or x = -1.42", "x² = 2 ⇒ x = ±1.42", "x² = 2 ⇒ x = ±1.5"])
def test_s5_wrong_rounded_roots_fail_in_any_order_or_spelling(answer):
    assert fails(answer, "mathematics_aa")


def test_s5_a_lone_root_and_the_singleton_step():
    # one root only: the lost root is still named, with the principal-root note
    rc = receive(MAA, "Solve the quadratic equation.", "x² = 4 ⇒ x = -2")
    assert errors(rc) and [f for f in rc.structural_findings if f.code == "ST-ALG-001"]
    # the step to one member of a stated set is context, and names the set's check
    doc = build_document("x² = 4 ⇒ x = -2 or x = 2", None, "mathematics_aa")
    [case] = [r for r in doc.relations if r.kind == "case"]
    assert case.outcome == "context" and "stem-sol" in case.reason and not case.principal_root
    assert [r.check_id for r in doc.checks] == ["stem-sol-1"]


# =============================================================================================== S7: bars that open a line

def test_s7_plain_absolute_value_is_checked_like_its_latex_twin():
    req = "Calculate the absolute value of negative two."
    for answer in ("|-2| = 2", "$|-2| = 2$"):
        rc = receive(MAA, req, answer)
        assert rc.status.value == "ACCEPTED" and checks(rc) == {"stem-eq-1": (True, "ENTAILED")}, answer
        assert not [f for f in rc.findings if f.code == "INT-REQ-012"], answer
    for answer in ("|-2| = 3", "$|-2| = 3$", "a = |-2| = 3"):
        rc = receive(MAA, "Evaluate the absolute value.", answer)
        assert [e.claim_ids for e in errors(rc)] == [["m1.1"]] and checks(rc) == {"stem-eq-1": (False, "COUNTEREXAMPLE")}, answer
    rc = receive(MAA, "Calculate the absolute value of negative two and add two and two.", "|-2| = 3\n2 + 2 = 4.")
    assert [e.claim_ids for e in errors(rc)] == [["m1.1"]] and checks(rc) == {"stem-eq-1": (False, "COUNTEREXAMPLE"), "stem-eq-2": (True, "ENTAILED")}
    assert holds("|3 − 5| = 2", "mathematics_aa") and fails("|3 − 5| = −2", "mathematics_aa")


def test_s7_tables_keep_their_structure():
    def kinds(text, profile="physics"):
        return [sp.kind for sp in build_document(text, None, profile).spans.spans]

    assert kinds("| t | v |\n|---|---|\n| 0 | 0 |") == ["table"]
    assert kinds("| A | B | Q |\n| :-: | :-: | :-: |\n| 0 | 1 | 1 |", "computer_science") == ["table"]
    # a truth table written without a delimiter row is still read and checked
    tt = "| A | B | A AND B |\n| 0 | 0 | 0 |\n| 0 | 1 | 0 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |"
    assert kinds(tt, "computer_science") == ["table"] and holds(tt, "computer_science")
    assert fails(tt.replace("| 1 | 1 | 1 |", "| 1 | 1 | 0 |"), "computer_science")
    # bars around an expression are maths: absolute values, norms; a determinant's rows are never a check
    assert "table" not in kinds("|a + b| ≤ |a| + |b|", "mathematics_aa") and "table" not in kinds("|-2| = 2", "mathematics_aa")
    assert "table" not in kinds("| x | y |\n| 1 | 2 |")                       # no delimiter row and no truth table
    assert decide("|2 3|\n|1 4| = 5", "mathematics_aa") == {}


# =============================================================================================== invariance (the review's recommendation)

def verdict(text: str, profile: str) -> str:
    out = decide(text, profile)
    return "none" if not out else ("pass" if all(v[0] is True for v in out.values()) else "fail")


@pytest.mark.parametrize("plain,variant,profile,expected", [
    ("2 + 3 = 5", "(2 + 3) = 5", "mathematics_aa", "pass"), ("2 + 3 = 6", "((2 + 3)) = 6", "mathematics_aa", "fail"),
    ("1/2 = 0.5", "(1/2) = 0.5", "mathematics_aa", "pass"), ("1/2 = 0.51", "1/2 = (0.51)", "mathematics_aa", "fail"),
    ("x² = 4 ⇒ x = -2 or x = 2", "x² = 4 ⇒ x = (-2) or x = 2", "mathematics_aa", "pass"),
    ("x² = 4 ⇒ x = -2 or x = 3", "x² = 4 ⇒ x = (-2) or x = 3", "mathematics_aa", "fail"),
    ("|-2| = 2", "|(-2)| = 2", "mathematics_aa", "pass"), ("|-2| = 3", "|(-2)| = 3", "mathematics_aa", "fail"),
    ("T = 25 °C = 298.15 K", "T = (25) °C = 298.15 K", "physics", "pass"), ("T = 25 °C = 25 K", "T = (25) °C = 25 K", "physics", "fail"),
    ("F = 2.0 × 3.0 = 6.0 N", "F = (2.0)(3.0) = 6.0 N", "physics", "pass"),
])
def test_harmless_parentheses_keep_the_verdict(plain, variant, profile, expected):
    # parentheses around a value, a group or a whole side change nothing; the wrong twin of each pair still fails
    assert verdict(plain, profile) == verdict(variant, profile) == expected, (plain, variant)


# =============================================================================================== part scope

def test_part_scope_a_binding_of_one_part_never_validates_another():
    swapped = receive(MAA, "Calculate y in each part.", "(a) x = 2\ny = x + 1 = 5\n(b) x = 4\ny = x + 1 = 3")
    assert sorted(e.claim_ids[0] for e in errors(swapped)) == ["m1.2", "m1.4"]
    assert checks(swapped) == {"stem-sub-1": (False, "COUNTEREXAMPLE"), "stem-sub-2": (False, "COUNTEREXAMPLE")}
    # ST-SCOPE-001 notes stay informative (info level) and say how bindings are scoped
    notes = [f for f in swapped.structural_findings if f.code == "ST-SCOPE-001"]
    assert notes and all(f.severity == "info" and "in force in its own part" in f.message for f in notes)
    right = receive(MAA, "Calculate y in each part.", "(a) x = 2\ny = x + 1 = 3\n(b) x = 4\ny = x + 1 = 5")
    assert not errors(right) and checks(right) == {"stem-sub-1": (True, "ENTAILED"), "stem-sub-2": (True, "ENTAILED")}
    single = receive(MAA, "Evaluate y.", "x = 2\ny = x + 1 = 5")
    assert errors(single) and checks(single) == {"stem-sub-1": (False, "COUNTEREXAMPLE")}


def test_part_scope_written_substitutions_are_scoped_too():
    # each part substitutes the other part's value: both fail (before, each matched the other part's binding)
    assert decide("(a) x = 7\ny = 2x = 2 × 9 = 18\n(b) x = 9\ny = 2x = 2 × 7 = 14", "mathematics_aa") == {
        "stem-sub-1": (False, "COUNTEREXAMPLE", "error"), "stem-eq-1": (True, "ENTAILED", "error"),
        "stem-sub-2": (False, "COUNTEREXAMPLE", "error"), "stem-eq-2": (True, "ENTAILED", "error")}
    assert holds("(a) x = 7\ny = 2x = 2 × 7 = 14\n(b) x = 9\ny = 2x = 2 × 9 = 18", "mathematics_aa")


def test_part_scope_follows_statement_order():
    # a value stated after the calculation does not validate it
    assert decide("x = 2\ny = x + 1 = 5\nx = 4", "mathematics_aa") == {"stem-sub-1": (False, "COUNTEREXAMPLE", "error")}
    # the value is in force where it is stated: a rebinding in the part leaves which value was meant to a reading, so the
    # failure of the second calculation is a warning (INT-SUBJ-004), never an error, and the first stays an error
    assert decide("x = 2\ny = x + 1 = 5\nx = 4\ny = x + 1 = 3", "mathematics_aa") == {
        "stem-sub-1": (False, "COUNTEREXAMPLE", "error"), "stem-sub-2": (False, "COUNTEREXAMPLE", "warning")}
    assert holds("x = 2\ny = x + 1 = 3\nx = 4\ny = x + 1 = 5", "mathematics_aa")
    # a value given in the same statement, after the calculation, is in scope
    assert holds("y = x + 1 = 3, where x = 2", "mathematics_aa") and fails("y = x + 1 = 5, where x = 2", "mathematics_aa")


def test_part_scope_an_order_relation_compares_values_of_its_own_part():
    # 't > 40' in part (c) solves an inequality: t is given several values elsewhere (the request's 'at t = 0 and t = 8'),
    # so it is a variable, and the relation is no comparison of stated values (it used to pass only by accident)
    doc = build_document("(c) Solve for t.\nt > 40", "Use the rates at t = 0 and t = 8.", "mathematics_aa")
    assert not doc.checks and any(r.op == ">" and r.outcome == "context" for r in doc.relations)
    assert decide("(a) x = 2\n(b) x = 5\n(c) x > 3", "mathematics_aa") == {}
    # one value carried from another part, or given by the request, is still compared; a value of its own part too
    assert holds("(a) T₁ = 310 K\n(b) T₂ = 350 K, so T₂ > T₁") and fails("(a) T₁ = 310 K\n(b) T₂ = 250 K, so T₂ > T₁")
    assert holds("Since v > 10 m/s, the car is fast.", request="A car travels at v = 20 m/s.")
    assert fails("Since v > 30 m/s, the car is fast.", request="A car travels at v = 20 m/s.")
    assert fails("x = 2\nx > 3", "mathematics_aa") and holds("x = 4\nx > 3", "mathematics_aa")


def test_part_scope_a_value_carried_forward_still_passes():
    # the answer carries part (a)'s result into part (b), written out or by its symbol
    assert holds("(a) m = 2.0 kg, a = 3.0 m s⁻², F = ma = 2.0 × 3.0 = 6.0 N\n(b) W = F × d = 6.0 × 5.0 = 30 J")
    assert holds("(a) F = 6.0 N\n(b) d = 5.0 m\nW = Fd = 30 J") and fails("(a) F = 6.0 N\n(b) d = 5.0 m\nW = Fd = 35 J")
    # a symbol reused for two states in one part, with the value written out: the written value shows which one was meant
    assert holds("At the top v = 20 m/s; at the bottom v = 25 m/s. KE at the top = ½mv² = ½ × 2.0 × 20² = 400 J")
    # the request's values hold in every part
    req = "A 2.0 kg mass is lifted 5.0 m."
    assert holds("(a) W = mgh = 2.0 × 9.81 × 5.0 = 98.1 J\n(b) W = mgh = 2.0 × 9.81 × 5.0 = 98.1 J", request=req)
