"""Decimal-exponent factoring (docs/STEM_DESIGN.md, section 7.3): the factoring identity on random
monomials and sums, literals of at most 40 digits, and ST-LIM-001 beyond.

The IR terms are interpreted here, in the test only, by a small exact walker over the IR data
(literals are read with ``Fraction``); nothing in the package evaluates anything."""
from __future__ import annotations

import random
from fractions import Fraction

import pytest

from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.scaling import (
    MAX_LITERAL_DIGITS, LiteralTooLong, Term, add_terms, digit_count, div_literal, floor_log10, frame_for, int_power, lit, literal_in_frame,
    literal_text, mul_terms, nary, neg_term, split, sub_terms, to_frame, var_term,
)


def value(expr: dict, env: dict | None = None) -> Fraction:
    op = expr["op"]
    if op == "real":
        return Fraction(expr["value"])
    if op == "var":
        return (env or {})[expr["name"]]
    if op == "add":
        return sum((value(a, env) for a in expr["args"]), Fraction(0))
    if op == "mul":
        out = Fraction(1)
        for a in expr["args"]:
            out *= value(a, env)
        return out
    if op == "sub":
        return value(expr["left"], env) - value(expr["right"], env)
    if op == "neg":
        return -value(expr["arg"], env)
    if op == "div":
        return value(expr["left"], env) / value(expr["right"], env)
    raise AssertionError(op)


def term_value(t: Term, env: dict | None = None) -> Fraction:
    return value(t.expr, env) * Fraction(10) ** t.k


def literals(expr: dict):
    if expr["op"] == "real":
        yield expr["value"]
    for key in ("left", "right", "arg"):
        if key in expr:
            yield from literals(expr[key])
    for a in expr.get("args", []):
        yield from literals(a)


def test_floor_log10_is_exact():
    rng = random.Random(7)
    for _ in range(400):
        num = rng.randint(1, 10 ** rng.randint(1, 40))
        den = rng.randint(1, 10 ** rng.randint(1, 40))
        x = Fraction(num, den)
        k = floor_log10(x)
        assert Fraction(10) ** k <= x < Fraction(10) ** (k + 1)
        assert floor_log10(-x) == k
    with pytest.raises(ValueError):
        floor_log10(Fraction(0))


def test_split():
    m, k = split(Fraction(662607015, 10 ** 42))
    assert k == -34 and m == Fraction(662607015, 10 ** 8)
    assert split(Fraction(0)) == (Fraction(0), None)
    m, k = split(Fraction(-25))
    assert m == Fraction(-25, 10) and k == 1


@pytest.mark.parametrize("v,text", [(Fraction(7), "7"), (Fraction(-7), "-7"), (Fraction(1, 4), "0.25"), (Fraction(-1, 8000), "-0.000125"),
                                    (Fraction(5, 18), "5/18"), (Fraction(0), "0"), (Fraction(12345, 100), "123.45")])
def test_literal_text_is_exact(v, text):
    assert literal_text(v) == text
    assert Fraction(text) == v


def test_short_literals_stay_as_written_and_long_ones_are_split():
    t = lit(Fraction(20))
    assert t.expr == {"op": "real", "value": "20"} and t.k == 0
    t = lit(Fraction(4, 1) / 10 * 10 + Fraction(1, 10))
    assert t.k == 0
    planck = lit(Fraction(662607015, 10 ** 42))
    assert planck.k == -34 and planck.expr["value"] == "6.62607015"
    assert term_value(planck) == Fraction(662607015, 10 ** 42)
    assert lit(Fraction(0)).zero


def _random_value(rng: random.Random) -> Fraction:
    mantissa = Fraction(rng.randint(1, 9999), 10 ** rng.randint(0, 3))
    if rng.random() < 0.3:
        mantissa = -mantissa
    return mantissa * Fraction(10) ** rng.randint(-40, 40)


def test_the_factoring_identity_on_random_monomials():
    rng = random.Random(11)
    for _ in range(300):
        n = rng.randint(1, 5)
        vals = [_random_value(rng) for _ in range(n)]
        t, nonlinear = mul_terms([lit(v) for v in vals])
        assert not nonlinear
        expected = Fraction(1)
        for v in vals:
            expected *= v
        assert term_value(t) == expected
        assert all(digit_count(s) <= MAX_LITERAL_DIGITS for s in literals(t.expr))
        d = _random_value(rng)
        q = div_literal(t, lit(d))
        assert term_value(q) == expected / d
        p, _nl = int_power(lit(vals[0]), rng.randint(2, 4))
        assert term_value(p) == vals[0] ** (len(p.expr["args"]) if p.expr["op"] == "mul" else 1)


def test_the_factoring_identity_on_random_sums():
    rng = random.Random(13)
    for _ in range(300):
        vals = []
        base = rng.randint(-30, 30)
        for _ in range(rng.randint(2, 6)):
            vals.append(Fraction(rng.randint(-9999, 9999), 10 ** rng.randint(0, 3)) * Fraction(10) ** (base + rng.randint(-6, 6)))
        t = add_terms([lit(v) for v in vals])
        assert term_value(t) == sum(vals, Fraction(0))
        assert all(digit_count(s) <= MAX_LITERAL_DIGITS for s in literals(t.expr))
        s = sub_terms(lit(vals[0]), lit(vals[1]))
        assert term_value(s) == vals[0] - vals[1]
        assert term_value(neg_term(lit(vals[0]))) == -vals[0]


def test_sums_with_variables_align_by_an_exact_power_of_ten():
    x = var_term("x", -20)
    t = add_terms([x, lit(Fraction(3) * Fraction(10) ** -18)])
    for xv in (Fraction(1), Fraction(-7, 3)):
        assert term_value(t, {"x": xv}) == xv * Fraction(10) ** -20 + 3 * Fraction(10) ** -18
    m, nonlinear = mul_terms([x, var_term("y", 5)])
    assert nonlinear and m.k == -15


def test_frames_are_exact():
    rng = random.Random(17)
    for _ in range(200):
        v = _random_value(rng)
        t = lit(v)
        for f in (0, t.k, t.k - 3, t.k + 3):
            try:
                e = to_frame(t, f)
            except LiteralTooLong:
                continue
            assert value(e) * Fraction(10) ** f == v
            assert Fraction(literal_in_frame(v, f)["value"]) * Fraction(10) ** f == v
    x = var_term("x", 3)
    e = to_frame(x, 0)
    assert value(e, {"x": Fraction(2)}) == 2000
    e = to_frame(x, 5)
    assert value(e, {"x": Fraction(2)}) * 10 ** 5 == 2000


def test_frame_for_prefers_the_written_frame():
    assert frame_for(lit(Fraction(5)), Fraction(6)) == 0
    planck_product, _ = mul_terms([lit(Fraction(662607015, 10 ** 42)), lit(Fraction(5) * 10 ** 14)])
    f = frame_for(planck_product, Fraction(33, 10) * Fraction(1, 10 ** 19))
    assert -40 <= f <= 0


def test_a_literal_beyond_forty_digits_after_factoring_is_refused():
    with pytest.raises(LiteralTooLong):
        add_terms([lit(Fraction(1, 10 ** 60)), lit(Fraction(10) ** 60)])
    with pytest.raises(LiteralTooLong):
        literal_in_frame(Fraction(10) ** 60, -10)


def test_nary_nests_beyond_32_arguments():
    args = [{"op": "real", "value": str(i)} for i in range(100)]
    node = nary("add", args)
    assert len(node["args"]) <= 32
    assert value(node) == sum(range(100))

    def widest(n):
        return max([len(n.get("args", []))] + [widest(a) for a in n.get("args", [])])
    assert widest(node) <= 32


def test_st_lim_001_is_reported_for_a_sum_that_cannot_be_aligned():
    doc = build_document("P = 1.0 × 10⁻⁶⁰ W + 1.0 × 10⁶⁰ W = 1.0 × 10⁶⁰ W", None, "physics")
    plan = build_checks(doc, report_id="r", request_id="q")
    f = plan.finding_for("stem-eq-1")
    assert f is not None and f.code == "ST-LIM-001" and f.severity == "warning"
    assert plan.check("stem-eq-1") is None


def test_planck_scale_arithmetic_is_decided_with_small_literals():
    doc = build_document("E = hf = 6.62607015 × 10⁻³⁴ × 5.0 × 10¹⁴ = 3.3 × 10⁻¹⁹ J", None, "physics")
    plan = build_checks(doc, report_id="r", request_id="q")
    pc = plan.check("stem-eq-1")
    assert pc is not None
    for p in pc.problem["premises"] + [pc.problem.get("conclusion") or {"expr": {"op": "bool", "value": True}}]:
        for s in literals(p["expr"]):
            assert digit_count(s) <= MAX_LITERAL_DIGITS
