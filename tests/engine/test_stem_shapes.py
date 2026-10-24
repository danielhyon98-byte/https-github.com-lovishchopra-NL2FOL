"""Every STEM encoding shape (docs/STEM_DESIGN.md, sections 5 and 7) through ``verify`` under
its named policy, with the status it must reach.

The problems below are written by hand as IR data, in the form the STEM checks build:

* Form E: ``C_DEF: c = <written expression>``, ``R: r = <stated value>``, conclusion
  ``|c - r| <= h + tau*|c|``. ``|.|`` is an ``ite``, so the band is sign-aware.
* Form S: interval premises ``X_LO``/``X_HI`` (and ``ENC_LO``/``ENC_HI`` for enclosures), the
  definitions, and the band as a premise. SATISFIABLE means that some admissible reading
  gives the stated value.
* Auxiliaries ``q`` (quotient), ``sq`` (root), ``enc`` (enclosure). Symbolic divisors are
  guarded with ``!= 0``. The engine never divides by a variable.

Each nonlinear shape must be UNSUPPORTED (E201) under the linear policy, and each linear
shape must be decided identically under both policies. Every counterexample and witness
with rational values is re-checked in exact ``Fraction`` arithmetic against the IR, so a
definitive status is shown to be backed by a genuine model. The IR is only ever walked here;
nothing is evaluated from text.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Mapping, Optional

import pytest

from epinoic_logic.engine.policies import (
    LINEAR,
    NONLINEAR,
    NONLINEAR_LIMITS,
    NONLINEAR_MAX_DEGREE,
    NONLINEAR_RLIMIT,
    max_degree,
    policy_config,
    policy_limits,
    required_policy,
)
from epinoic_logic.engine.results import SolverConfig, VerificationResult
from epinoic_logic.engine.runner import verify
from epinoic_logic.engine.statuses import VerificationStatus as S, is_definitive
from epinoic_logic.ir.schema import Problem

CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)
SCOPE = (
    "STEM check: proves a property of its encoding only (the written arithmetic, substitution, conversion, "
    "algebraic step, balance or Boolean identity under the stated premises, the documented readings and the "
    "STEM tolerance rule); not that a law applies, that data are true, or that the answer is what was asked."
)

# --------------------------------------------------------------------------- IR builders (data only)


def V(name: str) -> dict:
    return {"op": "var", "name": name}


def R(value: Any) -> dict:
    return {"op": "real", "value": str(value)}


def I(value: Any) -> dict:
    return {"op": "int", "value": str(value)}


def B(value: bool) -> dict:
    return {"op": "bool", "value": value}


def add(*args: dict) -> dict:
    return {"op": "add", "args": list(args)}


def mul(*args: dict) -> dict:
    return {"op": "mul", "args": list(args)}


def sub(left: dict, right: dict) -> dict:
    return {"op": "sub", "left": left, "right": right}


def neg(arg: dict) -> dict:
    return {"op": "neg", "arg": arg}


def div(left: dict, right: dict) -> dict:
    return {"op": "div", "left": left, "right": right}


def cmp(op: str, left: dict, right: dict) -> dict:
    return {"op": op, "left": left, "right": right}


def eq(left: dict, right: dict) -> dict:
    return cmp("eq", left, right)


def ite(cond: dict, then: dict, otherwise: dict) -> dict:
    return {"op": "ite", "cond": cond, "then": then, "otherwise": otherwise}


def and_(*args: dict) -> dict:
    return {"op": "and", "args": list(args)}


def or_(*args: dict) -> dict:
    return {"op": "or", "args": list(args)}


def not_(arg: dict) -> dict:
    return {"op": "not", "arg": arg}


def iff(left: dict, right: dict) -> dict:
    return {"op": "iff", "left": left, "right": right}


def absv(x: dict) -> dict:
    return ite(cmp("ge", x, R(0)), x, neg(x))


def band(c: dict, r: dict, h: str, tau: str) -> dict:
    """|c - r| <= h + tau*|c| (rule R4): symmetric around the computed value and sign-aware."""
    return cmp("le", absv(sub(c, r)), add(R(h), mul(R(tau), absv(c))))


def _g(kind: str, note: Optional[str] = None, verified: Optional[bool] = None) -> dict:
    g: dict = {"kind": kind}
    if note:
        g["note"] = note
    if verified is not None:
        g["verified"] = verified
    return {"grounding": g}


FIGURE = _g("supplied_text", "figure stated in the report itself", True)
DEVICE = _g("arithmetic_fact", "encoding device: defines the auxiliary as the written expression; not a claim of the report")
ENCLOSURE = _g("arithmetic_fact", "enclosure computed by the STEM pack; the engine decides the stated relation over every admissible value")
GUARD = _g("assumption", "side condition of the step")
LAW = _g("specialist_inference")
TASK = _g("task_setting", "domain restriction stated in the request", True)


def problem(pid: str, query: str, symbols: list[tuple[str, str]], premises: list[tuple[str, dict, dict]],
            conclusion: Optional[tuple[str, dict]] = None, policy: str = LINEAR) -> Problem:
    data: dict = {
        "problem_id": f"stem-{pid}"[:128],
        "request_id": "stem-shapes",
        "claim_id": f"r1:{pid}"[:128],
        "query": query,
        "symbols": [{"name": n, "sort": s} for n, s in symbols],
        "premises": [{"id": i, "expr": e, **meta} for i, e, meta in premises],
        "notes": SCOPE + (" policy: nonlinear" if policy == NONLINEAR else ""),
    }
    if conclusion is not None:
        data["conclusion"] = {"id": conclusion[0], "expr": conclusion[1]}
    return Problem.model_validate(data)


def form_e(pid: str, computed: dict, stated: dict, h: str, tau: str, *, symbols: tuple = (), premises: tuple = (),
           policy: str = LINEAR) -> Problem:
    syms = [("c", "Real"), ("r", "Real"), *symbols]
    prem = [*premises, ("C_DEF", eq(V("c"), computed), FIGURE), ("R", eq(V("r"), stated), FIGURE)]
    return problem(pid, "entailment", syms, prem, ("STATED", band(V("c"), V("r"), h, tau)), policy)


def form_s(pid: str, computed: dict, stated: dict, h: str, tau: str, *, intervals: tuple = (), enclosures: tuple = (),
           symbols: tuple = (), premises: tuple = (), policy: str = LINEAR) -> Problem:
    syms = [("c", "Real"), ("r", "Real"), *[(n, "Real") for n, _, _ in intervals + enclosures], *symbols]
    prem: list = []
    for n, lo, hi in intervals:
        prem += [(f"X_LO_{n}", cmp("ge", V(n), R(lo)), FIGURE), (f"X_HI_{n}", cmp("le", V(n), R(hi)), FIGURE)]
    for n, lo, hi in enclosures:
        prem += [(f"ENC_LO_{n}", cmp("ge", V(n), R(lo)), ENCLOSURE), (f"ENC_HI_{n}", cmp("le", V(n), R(hi)), ENCLOSURE)]
    prem += [*premises, ("C_DEF", eq(V("c"), computed), FIGURE), ("R", eq(V("r"), stated), FIGURE),
             ("BAND", band(V("c"), V("r"), h, tau), FIGURE)]
    return problem(pid, "satisfiability", syms, prem, None, policy)


# Rational enclosures of width at most 1e-15 (relative), as the STEM pack computes them.
PI = ("enc_1", "3.1415926535897932", "3.1415926535897933")
LN2 = ("enc_1", "0.6931471805599453", "0.6931471805599454")

# --------------------------------------------------------------------------- the shapes


@dataclass(frozen=True)
class Shape:
    name: str
    policy: str
    expected: S
    problem: Problem
    model: Mapping[str, str] = field(default_factory=dict)  # exact values the model must show


def _surd(name: str, radicand: dict) -> tuple[str, dict, dict]:
    """sq >= 0 and sq*sq = x: the exact square root as an auxiliary (nonlinear)."""
    return (f"S_SQ_{name}", and_(cmp("ge", V(name), R(0)), eq(mul(V(name), V(name)), radicand)), DEVICE)


def _quotient(name: str, numerator: dict, divisor: dict) -> list[tuple[str, dict, dict]]:
    """q*b = a with the guard b != 0; never a division by a variable."""
    return [(f"Q_DEF_{name}", eq(mul(V(name), divisor), numerator), DEVICE), (f"GUARD_{name}", cmp("ne", divisor, R(0)), GUARD)]


def _balance(pid: str, coefficients: dict[str, str], tallies: dict[str, tuple[dict, dict]], sort: str = "Int") -> Problem:
    """Coefficients pinned; tally symbols per element (and charge) defined from them; conclusion: every tally balances."""
    lit = I if sort == "Int" else R
    symbols = [(k, sort) for k in coefficients] + [(f"t_{e}_{side}", sort) for e in tallies for side in ("l", "r")]
    premises = [(f"K_{k}", eq(V(k), lit(v)), FIGURE) for k, v in coefficients.items()]
    for e, (left, right) in tallies.items():
        premises += [(f"T_{e}_L", eq(V(f"t_{e}_l"), left), DEVICE), (f"T_{e}_R", eq(V(f"t_{e}_r"), right), DEVICE)]
    conclusion = and_(*[eq(V(f"t_{e}_l"), V(f"t_{e}_r")) for e in tallies]) if len(tallies) > 1 else eq(V(f"t_{next(iter(tallies))}_l"), V(f"t_{next(iter(tallies))}_r"))
    return problem(pid, "entailment", symbols, premises, ("BALANCE", conclusion))


def _boolean_identity(pid: str, lhs: dict, rhs: dict) -> Problem:
    """NEG: not(lhs <=> rhs); UNSATISFIABLE proves the identity, a witness distinguishes the sides."""
    return problem(pid, "satisfiability", [("a", "Bool"), ("b", "Bool")], [("NEG", not_(iff(lhs, rhs)), FIGURE)])


def _truth_table(pid: str, rows: list[tuple[bool, bool, bool]]) -> Problem:
    """Stated outputs pinned; conclusion: each row's output equals A AND B on that row's inputs."""
    symbols = [(f"o_{i}", "Bool") for i in range(1, len(rows) + 1)]
    premises = [(f"O_{i}", V(f"o_{i}") if out else not_(V(f"o_{i}")), FIGURE) for i, (_a, _b, out) in enumerate(rows, 1)]
    conclusion = and_(*[iff(V(f"o_{i}"), and_(B(a), B(b))) for i, (a, b, _o) in enumerate(rows, 1)])
    return problem(pid, "entailment", symbols, premises, ("ROWS", conclusion))


def _int_equal(pid: str, computed: dict, stated: int) -> Problem:
    return problem(pid, "entailment", [("c", "Int"), ("r", "Int")],
                   [("C_DEF", eq(V("c"), computed), FIGURE), ("R", eq(V("r"), I(stated)), FIGURE)], ("STATED", eq(V("c"), V("r"))))


def _comparison(pid: str, t1: str, t2: str) -> Problem:
    return problem(pid, "entailment", [("t_1", "Real"), ("t_2", "Real")],
                   [("B_T1", eq(V("t_1"), R(t1)), FIGURE), ("B_T2", eq(V("t_2"), R(t2)), FIGURE)], ("STATED", cmp("gt", V("t_1"), V("t_2"))))


def _step(pid: str, previous: dict, conclusion: dict, *, symbols: tuple = (("x", "Real"),), extra: tuple = (), policy: str = LINEAR) -> Problem:
    """An algebra or inequality step: the preceding relation (and side conditions) entail the next one."""
    return problem(pid, "entailment", list(symbols), [("PREV", previous, LAW), *extra], ("STEP", conclusion), policy)


def _five_interval(pid: str, stated: str) -> Problem:
    """(a*b*c)/(d*e) = S where every operand is a carried intermediate ranging over its rounding interval."""
    intervals = (("x_a", "2.45", "2.55"), ("x_b", "3.15", "3.25"), ("x_c", "1.55", "1.65"), ("x_d", "3.95", "4.05"), ("x_e", "0.75", "0.85"))
    return form_s(pid, V("q_1"), R(stated), "1/20", "1/100", intervals=intervals, symbols=(("q_1", "Real"),),
                  premises=tuple(_quotient("q_1", mul(V("x_a"), V("x_b"), V("x_c")), mul(V("x_d"), V("x_e")))), policy=NONLINEAR)


def _q(x: Fraction) -> dict:
    return R(f"{x.numerator}/{x.denominator}")


def _decimal_root(pid: str, poly: dict, root: str, h: str) -> Problem:
    """R10: a real root of the equation lies within the stated decimal's rounding interval."""
    lo, hi = Fraction(root) - Fraction(h), Fraction(root) + Fraction(h)
    return problem(pid, "satisfiability", [("x", "Real")], [
        ("X_LO_x", cmp("ge", V("x"), _q(lo)), FIGURE),
        ("X_HI_x", cmp("le", V("x"), _q(hi)), FIGURE),
        ("EQ", eq(poly, R(0)), FIGURE),
    ], None, NONLINEAR)


def _sign_change(pid: str, coeffs: tuple[int, int, int], root: str, h: str) -> Problem:
    """A linear alternative for a simple decimal root: a*x^2 + b*x + c evaluated (as closed IR) at both
    ends of the rounding interval changes sign. SATISFIABLE proves a root inside (intermediate value theorem);
    UNSATISFIABLE says only that there is no sign change (a double root, or two roots inside)."""
    lo, hi = Fraction(root) - Fraction(h), Fraction(root) + Fraction(h)
    a, b, c = (R(v) for v in coeffs)

    def at(x: Fraction) -> dict:
        return add(mul(a, _q(x), _q(x)), mul(b, _q(x)), c)

    return problem(pid, "satisfiability", [("c_lo", "Real"), ("c_hi", "Real")], [
        ("C_LO", eq(V("c_lo"), at(lo)), DEVICE),
        ("C_HI", eq(V("c_hi"), at(hi)), DEVICE),
        ("SIGN", or_(and_(cmp("le", V("c_lo"), R(0)), cmp("ge", V("c_hi"), R(0))),
                     and_(cmp("ge", V("c_lo"), R(0)), cmp("le", V("c_hi"), R(0)))), FIGURE),
    ])


QUADRATIC = add(sub(mul(V("x"), V("x")), mul(R(5), V("x"))), R(6))      # x^2 - 5x + 6
GOLDEN = add(sub(mul(V("x"), V("x")), mul(R(3), V("x"))), R(1))         # x^2 - 3x + 1
ROOT2 = sub(mul(V("x"), V("x")), R(2))                                    # x^2 - 2
SUVAT_PREV = eq(mul(V("v"), V("v")), add(mul(V("u"), V("u")), mul(R(2), V("a"), V("s"))))  # v^2 = u^2 + 2as
KE_PREV = eq(V("e_k"), mul(R("1/2"), V("m"), V("v"), V("v")))            # E = 1/2 m v^2
OHM_DIVISOR = add(div(R(1), R("4.0")), div(R(1), R("6.0")))              # 1/4.0 + 1/6.0 (closed, compound)
SUVAT = (("v", "Real"), ("u", "Real"), ("a", "Real"), ("s", "Real"), ("q_1", "Real"))
KINEMATIC = (("v", "Real"), ("u", "Real"), ("a", "Real"), ("t", "Real"), ("q_1", "Real"))
ENERGY = (("e_k", "Real"), ("m", "Real"), ("v", "Real"), ("q_1", "Real"), ("sq_1", "Real"))

LINEAR_SHAPES: list[Shape] = [
    # Form E: the observed case and its correction.
    Shape("form_e_pass", LINEAR, S.ENTAILED, form_e("eq-pass", div(sub(R(20), R(0)), R("4.0")), R("5.0"), "1/20", "1/100")),
    Shape("form_e_fail_observed_case", LINEAR, S.COUNTEREXAMPLE, form_e("eq-fail", div(sub(R(20), R(0)), R("4.0")), R("6.0"), "1/20", "1/100"),
          {"c": "5", "r": "6"}),
    # Sign-aware band: -9.8 against a computed -9.81 passes; a sign error does not.
    Shape("band_negative_pass", LINEAR, S.ENTAILED, form_e("neg-pass", neg(mul(R(2), R("4.905"))), R("-9.8"), "1/20", "1/100")),
    Shape("band_negative_sign_error", LINEAR, S.COUNTEREXAMPLE, form_e("neg-fail", neg(mul(R(2), R("4.905"))), R("9.8"), "1/20", "1/100"),
          {"c": "-981/100", "r": "49/5"}),
    # Zero: exact zero, decimal zero, and a non-zero result stated as exact zero.
    Shape("zero_exact_pass", LINEAR, S.ENTAILED, form_e("zero-exact", sub(R(20), R(20)), R(0), "0", "0")),
    Shape("zero_decimal_pass", LINEAR, S.ENTAILED, form_e("zero-dec", sub(R("3.0"), R("3.0")), R("0.0"), "1/20", "1/100")),
    Shape("zero_fail", LINEAR, S.COUNTEREXAMPLE, form_e("zero-fail", sub(R("3.0"), R("2.9")), R(0), "0", "1/100"), {"c": "1/10", "r": "0"}),
    # Exact mode (tau = 0, h = 0): 7/3 = 2 fails, 7/3 = 7/3 holds.
    Shape("exact_mode_pass", LINEAR, S.ENTAILED, form_e("exact-pass", div(R(7), R(3)), R("7/3"), "0", "0")),
    Shape("exact_mode_fail", LINEAR, S.COUNTEREXAMPLE, form_e("exact-fail", div(R(7), R(3)), R(2), "0", "0"), {"c": "7/3", "r": "2"}),
    # A closed compound divisor through the auxiliary q: 1/(1/4.0 + 1/6.0) = 2.4.
    Shape("aux_closed_divisor_pass", LINEAR, S.ENTAILED, form_e("qdiv-pass", V("q_1"), R("2.4"), "1/20", "1/100", symbols=(("q_1", "Real"),),
                                                                premises=tuple(_quotient("q_1", R(1), OHM_DIVISOR)))),
    Shape("aux_closed_divisor_fail", LINEAR, S.COUNTEREXAMPLE, form_e("qdiv-fail", V("q_1"), R("2.5"), "1/20", "1/100", symbols=(("q_1", "Real"),),
                                                                      premises=tuple(_quotient("q_1", R(1), OHM_DIVISOR))), {"c": "12/5", "r": "5/2"}),
    # Element and charge balance over Int (Real for a fractional coefficient).
    Shape("int_balance_pass", LINEAR, S.ENTAILED, _balance("chem-pass", {"k_1": "2", "k_2": "1", "k_3": "2"},
                                                           {"h": (mul(I(2), V("k_1")), mul(I(2), V("k_3"))), "o": (mul(I(2), V("k_2")), V("k_3"))})),
    Shape("int_balance_fail", LINEAR, S.COUNTEREXAMPLE, _balance("chem-fail", {"k_1": "1", "k_2": "1", "k_3": "1"},
                                                                 {"h": (mul(I(2), V("k_1")), mul(I(2), V("k_3"))), "o": (mul(I(2), V("k_2")), V("k_3"))}),
          {"t_o_l": "2", "t_o_r": "1"}),
    Shape("charge_balance_pass", LINEAR, S.ENTAILED, _balance("charge-pass", {"k_1": "1", "k_2": "1", "k_3": "1"},
                                                              {"fe": (V("k_1"), V("k_3")), "q": (sub(mul(I(3), V("k_1")), V("k_2")), mul(I(2), V("k_3")))})),
    Shape("charge_balance_fail", LINEAR, S.COUNTEREXAMPLE, _balance("charge-fail", {"k_1": "1", "k_2": "2", "k_3": "1"},
                                                                    {"fe": (V("k_1"), V("k_3")), "q": (sub(mul(I(3), V("k_1")), V("k_2")), mul(I(2), V("k_3")))}),
          {"t_q_l": "1", "t_q_r": "2"}),
    Shape("fractional_balance_pass", LINEAR, S.ENTAILED, _balance("frac-pass", {"k_1": "1", "k_2": "1/2", "k_3": "1"},
                                                                  {"h": (mul(R(2), V("k_1")), mul(R(2), V("k_3"))), "o": (mul(R(2), V("k_2")), V("k_3"))}, "Real")),
    # Boolean identity by satisfiability of its negation.
    Shape("boolean_identity_pass", LINEAR, S.UNSATISFIABLE, _boolean_identity("bool-pass", not_(and_(V("a"), V("b"))), or_(not_(V("a")), not_(V("b"))))),
    Shape("boolean_identity_fail", LINEAR, S.SATISFIABLE, _boolean_identity("bool-fail", not_(and_(V("a"), V("b"))), and_(not_(V("a")), not_(V("b"))))),
    Shape("truth_table_pass", LINEAR, S.ENTAILED, _truth_table("tt-pass", [(False, False, False), (False, True, False), (True, False, False), (True, True, True)])),
    Shape("truth_table_fail", LINEAR, S.COUNTEREXAMPLE, _truth_table("tt-fail", [(False, False, False), (False, True, False), (True, False, True), (True, True, True)]),
          {"o_3": "true"}),
    Shape("base_conversion_pass", LINEAR, S.ENTAILED, _int_equal("base-pass", add(mul(I(15), I(16)), I(15)), 255)),
    Shape("base_conversion_fail", LINEAR, S.COUNTEREXAMPLE, _int_equal("base-fail", add(mul(I(15), I(16)), I(15)), 254), {"c": "255", "r": "254"}),
    # Stated order between values, and linear inequality steps (dividing by a negative flips the sign).
    Shape("comparison_pass", LINEAR, S.ENTAILED, _comparison("cmp-pass", "300", "250")),
    Shape("comparison_fail", LINEAR, S.COUNTEREXAMPLE, _comparison("cmp-fail", "250", "300"), {"t_1": "250", "t_2": "300"}),
    Shape("inequality_step_pass", LINEAR, S.ENTAILED, _step("ineq-pass", cmp("lt", add(mul(R(2), V("x")), R(3)), R(7)), cmp("lt", V("x"), R(2)))),
    Shape("inequality_step_negative_pass", LINEAR, S.ENTAILED, _step("ineq-neg-pass", cmp("lt", mul(R(-2), V("x")), R(4)), cmp("gt", V("x"), R(-2)))),
    Shape("inequality_step_negative_fail", LINEAR, S.COUNTEREXAMPLE, _step("ineq-neg-fail", cmp("lt", mul(R(-2), V("x")), R(4)), cmp("lt", V("x"), R(-2)))),
    # Enclosures (Form S): 2*pi*3.0 = 18.8, and t_half = ln 2 / 0.0250 = 27.7.
    Shape("enclosure_pi_pass", LINEAR, S.SATISFIABLE, form_s("enc-pi-pass", mul(R(2), V("enc_1"), R("3.0")), R("18.8"), "1/20", "1/100", enclosures=(PI,))),
    Shape("enclosure_pi_fail", LINEAR, S.UNSATISFIABLE, form_s("enc-pi-fail", mul(R(2), V("enc_1"), R("3.0")), R("19.8"), "1/20", "1/100", enclosures=(PI,))),
    Shape("enclosure_ln2_pass", LINEAR, S.SATISFIABLE, form_s("enc-ln-pass", div(V("enc_1"), R("0.0250")), R("27.7"), "1/20", "1/100", enclosures=(LN2,))),
    Shape("enclosure_ln2_fail", LINEAR, S.UNSATISFIABLE, form_s("enc-ln-fail", div(V("enc_1"), R("0.0250")), R("28.7"), "1/20", "1/100", enclosures=(LN2,))),
    # One carried intermediate (0.5, really 0.46) times an exact factor: Form S with one interval stays linear.
    Shape("carried_interval_pass", LINEAR, S.SATISFIABLE, form_s("carry-pass", mul(V("x_w"), R(100)), R(46), "1/2", "1/100", intervals=(("x_w", "0.45", "0.55"),))),
    Shape("carried_interval_fail", LINEAR, S.UNSATISFIABLE, form_s("carry-fail", mul(V("x_w"), R(100)), R(40), "1/2", "1/100", intervals=(("x_w", "0.45", "0.55"),))),
    # An exact stated root, checked by substituting it into the equation (linear membership).
    Shape("root_membership_pass", LINEAR, S.ENTAILED, form_e("sol-mem-pass", add(sub(mul(R(2), R(2)), mul(R(5), R(2))), R(6)), R(0), "0", "0")),
    Shape("root_membership_fail", LINEAR, S.COUNTEREXAMPLE, form_e("sol-mem-fail", add(sub(mul(R(4), R(4)), mul(R(5), R(4))), R(6)), R(0), "0", "0"),
          {"c": "2", "r": "0"}),
    # A conversion with an exact factor and no relative slack: 72 km/h = 20 m/s.
    Shape("conversion_pass", LINEAR, S.ENTAILED, form_e("cnv-pass", mul(R(72), R("5/18")), R(20), "1/2", "0")),
    Shape("conversion_fail", LINEAR, S.COUNTEREXAMPLE, form_e("cnv-fail", mul(R(72), R("5/18")), R(25), "1/2", "0"), {"c": "20", "r": "25"}),
    # Decimal exponent factored: hc/lambda with 10^-19 taken out, so every literal is small.
    Shape("decimal_exponent_factored_pass", LINEAR, S.ENTAILED,
          form_e("scale-pass", div(mul(R("6.62607015"), R("2.99792458")), R("5.0")), R("3.97"), "1/200", "1/100")),
    Shape("decimal_exponent_factored_fail", LINEAR, S.COUNTEREXAMPLE,
          form_e("scale-fail", div(mul(R("6.62607015"), R("2.99792458")), R("5.0")), R("4.97"), "1/200", "1/100")),
    # A simple decimal root by sign change (linear): the smaller root of x^2 - 3x + 1 at 0.38.
    Shape("decimal_root_sign_change_pass", LINEAR, S.SATISFIABLE, _sign_change("root-sign", (1, -3, 1), "0.38", "1/200")),
]

NONLINEAR_SHAPES: list[Shape] = [
    # Exact surds: sqrt 8 = 2 sqrt 2 is proved, not approximated; sqrt 2 = 1.41 holds within the band.
    Shape("surd_exact_pass", NONLINEAR, S.ENTAILED, form_e("surd-pass", V("sq_1"), mul(R(2), V("sq_2")), "0", "0", symbols=(("sq_1", "Real"), ("sq_2", "Real")),
                                                           premises=(_surd("sq_1", R(8)), _surd("sq_2", R(2))), policy=NONLINEAR)),
    Shape("surd_exact_fail", NONLINEAR, S.COUNTEREXAMPLE, form_e("surd-fail", V("sq_1"), mul(R(3), V("sq_2")), "0", "0", symbols=(("sq_1", "Real"), ("sq_2", "Real")),
                                                                 premises=(_surd("sq_1", R(8)), _surd("sq_2", R(2))), policy=NONLINEAR)),
    Shape("surd_decimal_pass", NONLINEAR, S.ENTAILED, form_e("surd-dec-pass", V("sq_1"), R("1.41"), "1/200", "1/100", symbols=(("sq_1", "Real"),),
                                                             premises=(_surd("sq_1", R(2)),), policy=NONLINEAR)),
    Shape("surd_decimal_fail", NONLINEAR, S.COUNTEREXAMPLE, form_e("surd-dec-fail", V("sq_1"), R("1.5"), "1/20", "1/100", symbols=(("sq_1", "Real"),),
                                                                   premises=(_surd("sq_1", R(2)),), policy=NONLINEAR)),
    # A symbolic divisor: v = u + at  =>  a = (v - u)/t, with the guard t != 0.
    Shape("symbolic_divisor_pass", NONLINEAR, S.ENTAILED, _step("alg-div-pass", eq(V("v"), add(V("u"), mul(V("a"), V("t")))), eq(V("a"), V("q_1")),
                                                                symbols=KINEMATIC, extra=tuple(_quotient("q_1", sub(V("v"), V("u")), V("t"))), policy=NONLINEAR)),
    Shape("symbolic_divisor_fail", NONLINEAR, S.COUNTEREXAMPLE, _step("alg-div-fail", eq(V("v"), add(V("u"), mul(V("a"), V("t")))), eq(V("a"), V("q_1")),
                                                                      symbols=KINEMATIC, extra=tuple(_quotient("q_1", add(V("v"), V("u")), V("t"))), policy=NONLINEAR)),
    # Rearrangements: v^2 = u^2 + 2as  =>  s = (v^2 - u^2)/(2a); dropping the 2 is caught.
    Shape("rearrangement_pass", NONLINEAR, S.ENTAILED, _step("alg-pass", SUVAT_PREV, eq(V("s"), V("q_1")), symbols=SUVAT,
                                                             extra=tuple(_quotient("q_1", sub(mul(V("v"), V("v")), mul(V("u"), V("u"))), mul(R(2), V("a")))), policy=NONLINEAR)),
    Shape("rearrangement_fail", NONLINEAR, S.COUNTEREXAMPLE, _step("alg-fail", SUVAT_PREV, eq(V("s"), V("q_1")), symbols=SUVAT,
                                                                   extra=tuple(_quotient("q_1", sub(mul(V("v"), V("v")), mul(V("u"), V("u"))), V("a"))), policy=NONLINEAR)),
    # E = 1/2 m v^2  =>  v = sqrt(2E/m), with the principal-root side condition v >= 0.
    Shape("rearrangement_root_pass", NONLINEAR, S.ENTAILED, _step("alg-root-pass", KE_PREV, eq(V("v"), V("sq_1")), symbols=ENERGY, policy=NONLINEAR,
                                                                  extra=(*_quotient("q_1", mul(R(2), V("e_k")), V("m")), ("SIDE_v", cmp("ge", V("v"), R(0)), GUARD), _surd("sq_1", V("q_1"))))),
    Shape("rearrangement_root_fail", NONLINEAR, S.COUNTEREXAMPLE, _step("alg-root-fail", KE_PREV, eq(V("v"), V("sq_1")), symbols=ENERGY, policy=NONLINEAR,
                                                                        extra=(*_quotient("q_1", V("e_k"), V("m")), ("SIDE_v", cmp("ge", V("v"), R(0)), GUARD), _surd("sq_1", V("q_1"))))),
    # Completeness of a stated solution set (the equation entails the disjunction of the roots).
    Shape("completeness_pass", NONLINEAR, S.ENTAILED, _step("sol-pass", eq(QUADRATIC, R(0)), or_(eq(V("x"), R(2)), eq(V("x"), R(3))), policy=NONLINEAR)),
    Shape("completeness_missing_root", NONLINEAR, S.COUNTEREXAMPLE, _step("sol-lost", eq(QUADRATIC, R(0)), eq(V("x"), R(2)), policy=NONLINEAR), {"x": "3"}),
    Shape("completeness_domain_pass", NONLINEAR, S.ENTAILED, _step("sol-domain", eq(mul(V("x"), V("x")), R(9)), eq(V("x"), R(3)), policy=NONLINEAR,
                                                                   extra=(("DOMAIN", cmp("gt", V("x"), R(0)), TASK),))),
    Shape("completeness_without_domain_fail", NONLINEAR, S.COUNTEREXAMPLE, _step("sol-nodomain", eq(mul(V("x"), V("x")), R(9)), eq(V("x"), R(3)), policy=NONLINEAR),
          {"x": "-3"}),
    # x^2 + 4 = 0 has no real root: INCONSISTENT_PREMISES, never a vacuous ENTAILED (design D13: undecided).
    Shape("completeness_complex_roots", NONLINEAR, S.INCONSISTENT_PREMISES,
          _step("sol-complex", eq(add(mul(V("x"), V("x")), R(4)), R(0)), eq(V("x"), R(2)), policy=NONLINEAR)),
    # Decimal roots (R10): some real root lies within the stated decimal's rounding interval.
    Shape("decimal_root_pass", NONLINEAR, S.SATISFIABLE, _decimal_root("root-pass", ROOT2, "1.41", "1/200")),
    Shape("decimal_root_fail", NONLINEAR, S.UNSATISFIABLE, _decimal_root("root-fail", ROOT2, "1.42", "1/200")),
    Shape("decimal_root_quadratic_pass", NONLINEAR, S.SATISFIABLE, _decimal_root("root-q-pass", GOLDEN, "0.38", "1/200")),
    Shape("decimal_root_quadratic_fail", NONLINEAR, S.UNSATISFIABLE, _decimal_root("root-q-fail", GOLDEN, "2.63", "1/200")),
    # Form S with five interval operands multiplied and divided.
    Shape("five_interval_pass", NONLINEAR, S.SATISFIABLE, _five_interval("five-pass", "4.0")),
    Shape("five_interval_fail", NONLINEAR, S.UNSATISFIABLE, _five_interval("five-fail", "5.0")),
    # pi r^2 with r a carried intermediate: an enclosure times an interval operand squared.
    Shape("interval_enclosure_product_pass", NONLINEAR, S.SATISFIABLE,
          form_s("area-pass", mul(V("enc_1"), V("x_r"), V("x_r")), R("19.6"), "1/20", "1/100", intervals=(("x_r", "2.45", "2.55"),), enclosures=(PI,), policy=NONLINEAR)),
    Shape("interval_enclosure_product_fail", NONLINEAR, S.UNSATISFIABLE,
          form_s("area-fail", mul(V("enc_1"), V("x_r"), V("x_r")), R("21.0"), "1/20", "1/100", intervals=(("x_r", "2.45", "2.55"),), enclosures=(PI,), policy=NONLINEAR)),
]

SHAPES = LINEAR_SHAPES + NONLINEAR_SHAPES


def run(shape: Shape, policy: Optional[str] = None, config: SolverConfig = CFG) -> VerificationResult:
    name = policy or shape.policy
    return verify(shape.problem, policy_config(name, config), policy_limits(name))


# --------------------------------------------------------------------------- exact re-check of models


def _value(text: str, sort: str) -> Any:
    return text == "true" if sort == "Bool" else Fraction(text)


def evaluate(node: Any, env: Mapping[str, Any], tol: Fraction = Fraction(0)) -> Any:
    """Meaning of an IR node under an assignment (test oracle; walks data, evaluates no text).

    With ``tol == 0`` everything is exact. A positive ``tol`` is used only for models Z3 reports
    approximately (``~a/b``): a comparison then holds within ``tol``."""
    op = node.op
    ev = lambda n: evaluate(n, env, tol)  # noqa: E731
    if op == "var":
        return env[node.name]
    if op == "bool":
        return node.value
    if op in ("int", "real"):
        return Fraction(node.value)
    if op == "not":
        return not ev(node.arg)
    if op in ("and", "or"):
        values = [ev(a) for a in node.args]
        return all(values) if op == "and" else any(values)
    if op == "implies":
        return (not ev(node.left)) or ev(node.right)
    if op == "iff":
        return ev(node.left) == ev(node.right)
    if op == "ite":
        return ev(node.then) if ev(node.cond) else ev(node.otherwise)
    if op == "add":
        return sum((ev(a) for a in node.args), Fraction(0))
    if op == "mul":
        out = Fraction(1)
        for a in node.args:
            out *= ev(a)
        return out
    if op == "sub":
        return ev(node.left) - ev(node.right)
    if op == "neg":
        return -ev(node.arg)
    if op == "div":
        return ev(node.left) / ev(node.right)
    if op == "to_real":
        return ev(node.arg)
    left, right = ev(node.left), ev(node.right)
    return {"eq": abs(left - right) <= tol, "ne": abs(left - right) > tol, "lt": left < right + tol, "le": left <= right + tol,
            "gt": left > right - tol, "ge": left >= right - tol}[op]


#: Shapes whose model holds an irrational algebraic number; Z3 reports it as '~a/b' (about 1e-24 precise).
IRRATIONAL_MODELS = frozenset({"surd_exact_fail", "surd_decimal_fail", "rearrangement_root_fail", "decimal_root_pass", "decimal_root_quadratic_pass"})


def model_values(assignments) -> tuple[dict[str, Any], bool]:
    """The model as Fractions (and Booleans), and whether any value was an approximation."""
    approximate = any(a.value.startswith("~") for a in assignments)
    return {a.symbol: _value(a.value.lstrip("~"), a.sort) for a in assignments}, approximate


# --------------------------------------------------------------------------- the tests


def test_shape_catalogue_is_complete_and_named_uniquely():
    names = [s.name for s in SHAPES]
    assert len(names) == len(set(names))
    assert {s.policy for s in LINEAR_SHAPES} == {LINEAR} and {s.policy for s in NONLINEAR_SHAPES} == {NONLINEAR}
    # Every expected outcome class of the design appears: passes and failures in both forms.
    assert {S.ENTAILED, S.COUNTEREXAMPLE, S.SATISFIABLE, S.UNSATISFIABLE} <= {s.expected for s in LINEAR_SHAPES}
    assert {S.ENTAILED, S.COUNTEREXAMPLE, S.SATISFIABLE, S.UNSATISFIABLE, S.INCONSISTENT_PREMISES} <= {s.expected for s in NONLINEAR_SHAPES}


@pytest.mark.parametrize("shape", SHAPES, ids=lambda s: s.name)
def test_shape_is_decided_as_expected_under_its_policy(shape: Shape):
    r = run(shape)
    assert r.status is shape.expected, (r.status, r.diagnostics, r.reason_unknown)
    assert is_definitive(r.status)
    assert not any(d.code == "E108" for d in r.diagnostics), r.diagnostics  # never vacuous
    assert r.scope_statement and SCOPE.split(":")[0] in (shape.problem.notes or "")
    if shape.policy == NONLINEAR:
        assert r.limits == NONLINEAR_LIMITS and r.solver_config.rlimit == NONLINEAR_RLIMIT
    else:
        assert r.limits is None and r.solver_config == CFG  # the linear policy runs exactly as the default
    model = r.counterexample.assignments if r.counterexample else (r.witness_model or [])
    if shape.expected in (S.COUNTEREXAMPLE, S.SATISFIABLE):
        assert model, "a failure or witness must show its model"
    shown = {a.symbol: a.value for a in model}
    for symbol, value in shape.model.items():
        assert shown.get(symbol) == value, (symbol, shown)


@pytest.mark.parametrize("shape", [s for s in SHAPES if s.expected in (S.COUNTEREXAMPLE, S.SATISFIABLE)], ids=lambda s: s.name)
def test_every_model_really_satisfies_the_premises(shape: Shape):
    """A COUNTEREXAMPLE must satisfy every premise and violate the conclusion; a SATISFIABLE witness
    must satisfy every premise. Re-checked over the IR in exact Fraction arithmetic; only the pinned
    irrational models are compared within 1e-12 (their approximations are about 1e-24 precise)."""
    r = run(shape)
    assignments = r.counterexample.assignments if r.counterexample else r.witness_model
    env, approximate = model_values(assignments)
    assert approximate == (shape.name in IRRATIONAL_MODELS), shape.name
    tol = Fraction(1, 10 ** 12) if approximate else Fraction(0)
    assert set(env) == {s.name for s in shape.problem.symbols}
    for premise in shape.problem.premises:
        assert evaluate(premise.expr, env, tol) is True, premise.id
    if shape.problem.conclusion is not None:
        assert evaluate(shape.problem.conclusion.expr, env, tol) is False


def test_irrational_counterexample_values_are_marked_approximate_not_dropped():
    """sqrt 8 = 3 sqrt 2 fails with irrational values: Z3 reports each as '~a/b', a rational
    approximation marked with '~', so nothing reads it as an exact value."""
    r = run(next(s for s in NONLINEAR_SHAPES if s.name == "surd_exact_fail"))
    assert r.status is S.COUNTEREXAMPLE
    values = {a.symbol: a.value for a in r.counterexample.assignments}
    assert {"c", "r", "sq_1", "sq_2"} <= set(values)
    approx = {k: Fraction(v[1:]) for k, v in values.items() if v.startswith("~")}
    assert {"c", "r", "sq_1", "sq_2"} <= set(approx)
    assert abs(approx["sq_2"] - Fraction(14142135623730951, 10 ** 16)) < Fraction(1, 10 ** 12)
    assert abs(approx["c"] - 2 * approx["sq_2"]) < Fraction(1, 10 ** 12) and abs(approx["r"] - 3 * approx["sq_2"]) < Fraction(1, 10 ** 12)


@pytest.mark.parametrize("shape", NONLINEAR_SHAPES, ids=lambda s: s.name)
def test_nonlinear_shape_is_unsupported_under_the_linear_policy(shape: Shape):
    r = run(shape, LINEAR)
    assert r.status is S.UNSUPPORTED and not is_definitive(r.status)
    codes = {d.code for d in r.diagnostics}
    assert "E201" in codes and all(c.startswith("E2") for c in codes), codes
    assert r.counterexample is None and r.witness_model is None and r.unsat_core is None
    assert r.limits is None  # decided under the default Limits: nothing recorded


@pytest.mark.parametrize("shape", LINEAR_SHAPES, ids=lambda s: s.name)
def test_linear_shape_is_decided_identically_under_the_nonlinear_policy(shape: Shape):
    assert run(shape, NONLINEAR).status is shape.expected


@pytest.mark.parametrize("shape", SHAPES, ids=lambda s: s.name)
def test_required_policy_is_exactly_the_shapes_policy(shape: Shape):
    assert required_policy(shape.problem) == shape.policy
    degree, _ = max_degree(shape.problem)
    assert (degree <= 1) == (shape.policy == LINEAR)
    assert degree <= NONLINEAR_MAX_DEGREE


@pytest.mark.parametrize("shape", NONLINEAR_SHAPES, ids=lambda s: s.name)
def test_nonlinear_shapes_decide_within_a_tenth_of_the_rlimit(shape: Shape):
    """Calibration headroom: NONLINEAR_RLIMIT is at least ten times what any STEM shape needs."""
    r = run(shape, config=SolverConfig(timeout_ms=5000, rlimit=NONLINEAR_RLIMIT // 10, memory_max_mb=None))
    assert r.status is shape.expected, (r.status, r.reason_unknown)


#: Shapes measured above the 50 ms design target, each with its own ceiling. Z3 5.1.0 spends
#: about 100 to 180 ms (with only about 1,900 rlimit units) finding the SMALLER root of a quadratic
#: such as x^2 - 3x + 1 inside a narrow interval: 0.38, 0.46 and 0.21 are slow, while 2.62, 1.41,
#: 0.71 and every wrong root take 2 to 15 ms. The linear sign-change form below decides the same
#: correct root in about 13 ms. Reported to stage `checks`.
KNOWN_SLOW_MS: dict[str, float] = {"decimal_root_quadratic_pass": 600.0}


def test_median_time_per_shape_is_below_50_ms():
    run(SHAPES[0])  # warm the solver once
    slow: dict[str, float] = {}
    for shape in SHAPES:
        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            run(shape)
            times.append((time.perf_counter() - t0) * 1000.0)
        median = statistics.median(times)
        if median >= KNOWN_SLOW_MS.get(shape.name, 50.0):
            slow[shape.name] = median
    assert not slow, slow
    assert set(KNOWN_SLOW_MS) <= {s.name for s in SHAPES}


def test_a_decimal_root_with_a_sign_change_is_decided_linearly_and_fast():
    """Intermediate value theorem: p(lo) and p(hi) of opposite signs prove a root in [lo, hi].
    With closed values substituted the encoding is linear. It decides the slow correct root above in a few ms."""
    shape = _shape("decimal_root_sign_change_pass")
    run(shape)
    t0 = time.perf_counter()
    assert run(shape).status is S.SATISFIABLE
    assert (time.perf_counter() - t0) * 1000.0 < 50.0


def _nested_root(depth: int, stated: str) -> Problem:
    """sqrt applied ``depth`` times to 2, each level an exact sq auxiliary (a chain of degree-2 equations)."""
    premises = [_surd("sq_1", R(2))] + [_surd(f"sq_{k}", V(f"sq_{k - 1}")) for k in range(2, depth + 1)]
    return form_e(f"nested-{depth}", V(f"sq_{depth}"), R(stated), "1/20000", "1/100",
                  symbols=tuple((f"sq_{k}", "Real") for k in range(1, depth + 1)), premises=tuple(premises), policy=NONLINEAR)


def test_nested_exact_roots_decide_to_depth_three_and_are_cut_off_beyond_never_as_success():
    """Measured: depth 3 decides in about 50 ms when correct. A wrong depth-3 value is a COUNTEREXAMPLE but
    takes about 1.2 s, most of it building irrational models outside the timeout (see engine/README.md),
    so it is not run here. From depth 4 Z3 runs to the wall-clock timeout (the rlimit does not bind in
    this projection), so the checks stage must cap exact nested roots."""
    assert run(Shape("x", NONLINEAR, S.ENTAILED, _nested_root(3, "1.0905"))).status is S.ENTAILED  # 2^(1/8) = 1.09051
    t0 = time.perf_counter()
    deep = run(Shape("x", NONLINEAR, S.TIMEOUT, _nested_root(4, "1.0443")), config=SolverConfig(timeout_ms=250, memory_max_mb=None))
    assert deep.status in (S.TIMEOUT, S.UNKNOWN) and not is_definitive(deep.status)
    assert deep.counterexample is None and deep.unsat_core is None
    assert time.perf_counter() - t0 < 3.0


def test_a_double_root_has_no_sign_change_so_the_nonlinear_form_stays_the_fallback():
    """x^2 - 2x + 1 = 0 at 1.0: p >= 0 on both ends, so the sign-change form cannot see the root
    (UNSATISFIABLE says only that no sign change exists). Form S under the nonlinear policy decides it."""
    double = add(sub(mul(V("x"), V("x")), mul(R(2), V("x"))), R(1))
    no_change = _sign_change("root-double-sign", (1, -2, 1), "1.0", "1/20")
    assert run(Shape("x", LINEAR, S.UNSATISFIABLE, no_change)).status is S.UNSATISFIABLE
    assert run(Shape("x", NONLINEAR, S.SATISFIABLE, _decimal_root("root-double", double, "1.0", "1/20"))).status is S.SATISFIABLE


# --------------------------------------------------------------------------- why each encoding device is needed


def _without(p: Problem, *premise_ids: str) -> Problem:
    kept = [x for x in p.premises if x.id not in premise_ids]
    assert len(kept) == len(p.premises) - len(premise_ids)
    return p.model_copy(update={"premises": kept})


def _shape(name: str) -> Shape:
    return next(s for s in SHAPES if s.name == name)


def test_form_s_with_an_unbounded_symbol_would_be_vacuously_satisfiable():
    """Builder invariant (R4): every Form S symbol is pinned, bounded or defined. One missing bound
    turns a wrong value into SATISFIABLE, which is why the STEM builder must never emit one."""
    wrong = _shape("five_interval_fail")
    assert run(wrong).status is S.UNSATISFIABLE
    assert run(Shape("x", NONLINEAR, S.SATISFIABLE, _without(wrong.problem, "X_HI_x_a"))).status is S.SATISFIABLE


def _governed_symbol(premise: Any, premises: Mapping[str, Any]) -> Optional[str]:
    """The symbol a Form S premise pins, bounds or defines, by the builder's premise-id convention."""
    e = premise.expr
    if premise.id.startswith(("X_LO_", "ENC_LO_")):
        upper = premises.get(premise.id.replace("_LO_", "_HI_"))
        assert upper is not None and upper.expr.left.name == e.left.name, premise.id  # both ends of the interval
        return e.left.name
    if premise.id in ("C_DEF", "R", "C_LO", "C_HI"):
        return e.left.name                       # x = <closed or defined expression>
    if premise.id.startswith("Q_DEF_"):
        return e.left.args[0].name               # q * b = a
    if premise.id.startswith("S_SQ_"):
        return e.args[0].left.name               # sq >= 0 and sq * sq = x
    return None


def test_every_form_s_symbol_is_pinned_bounded_or_defined():
    """The builder invariant of R4, checked on every Form S shape: no free symbol can make it vacuously SATISFIABLE."""
    checked = 0
    for shape in SHAPES:
        p = shape.problem
        if p.query != "satisfiability" or shape.name.startswith("boolean"):
            continue
        by_id = {x.id: x for x in p.premises}
        governed = {name for name in (_governed_symbol(x, by_id) for x in p.premises) if name}
        assert governed >= {s.name for s in p.symbols}, (shape.name, {s.name for s in p.symbols} - governed)
        checked += 1
    assert checked >= 10


def test_a_symbolic_divisor_needs_its_guard():
    proved = _shape("symbolic_divisor_pass")
    r = run(Shape("x", NONLINEAR, S.COUNTEREXAMPLE, _without(proved.problem, "GUARD_q_1")))
    assert r.status is S.COUNTEREXAMPLE
    assert {a.symbol: a.value for a in r.counterexample.assignments}["t"] == "0"


def test_a_principal_root_step_needs_its_side_condition():
    proved = _shape("rearrangement_root_pass")
    r = run(Shape("x", NONLINEAR, S.COUNTEREXAMPLE, _without(proved.problem, "SIDE_v")))
    assert r.status is S.COUNTEREXAMPLE
    v = {a.symbol: a.value for a in r.counterexample.assignments}["v"]
    assert v.startswith("-") or v.startswith("~-")


def test_the_band_must_be_sign_aware():
    """With tau*c instead of tau*|c| the band is negative for a negative result, and correct work
    (-9.8 against -9.81) would become a false error. The encoding uses |c| (an ite)."""
    naive = problem("neg-naive", "entailment", [("c", "Real"), ("r", "Real")],
                    [("C_DEF", eq(V("c"), neg(mul(R(2), R("4.905")))), FIGURE), ("R", eq(V("r"), R("-9.8")), FIGURE)],
                    ("STATED", cmp("le", absv(sub(V("c"), V("r"))), add(R("1/20"), mul(R("1/100"), V("c"))))))
    assert verify(naive, CFG).status is S.COUNTEREXAMPLE
    assert run(_shape("band_negative_pass")).status is S.ENTAILED


def test_form_e_would_flag_correctly_rounded_work_that_form_s_accepts():
    """0.5 x 100 = 46 where 0.5 is a carried intermediate (really 0.46): exact Form E fails it,
    Form S over the rounding interval accepts it. That is why carried values use Form S."""
    as_exact = form_e("carry-exact", mul(R("0.5"), R(100)), R(46), "1/2", "1/100")
    assert verify(as_exact, CFG).status is S.COUNTEREXAMPLE
    assert run(_shape("carried_interval_pass")).status is S.SATISFIABLE


def test_unfactored_planck_literal_exceeds_the_digit_bound_under_every_policy():
    """h = 6.62607015e-34 written out has 43 digits (> max_const_digits = 40). No policy raises
    that bound, which is why the STEM checks factor out powers of ten (D7)."""
    planck = "0." + "0" * 33 + "662607015"
    p = form_e("scale-raw", div(mul(R(planck), R("299792458")), R("0.0000005")), R("0.000000000000000000397"), "1/2000000000000000000000", "1/100")
    for name in (LINEAR, NONLINEAR):
        r = verify(p, policy_config(name, CFG), policy_limits(name))
        assert r.status is S.INVALID_FORMALIZATION and "E305" in {d.code for d in r.diagnostics}


def test_form_e_proofs_rest_on_the_written_figures():
    r = run(_shape("form_e_pass"))
    assert {"C_DEF", "R"} <= set(r.premises_relied_on)
    assert r.ungrounded_dependencies == []  # figures stated in the report itself, verified in-process


def test_algebra_steps_report_the_law_and_guards_they_relied_on():
    r = run(_shape("rearrangement_pass"))
    assert r.status is S.ENTAILED
    assert {"PREV", "GUARD_q_1", "Q_DEF_q_1"} <= set(r.premises_relied_on)
    assert {"PREV", "GUARD_q_1"} <= set(r.ungrounded_dependencies)  # a stated law and a side condition
    assert "Q_DEF_q_1" not in r.ungrounded_dependencies  # an encoding device, given with the task


def test_the_counterexample_names_the_unbalanced_tallies():
    r = run(_shape("int_balance_fail"))
    values = {a.symbol: a.value for a in r.counterexample.assignments}
    assert values["t_h_l"] == values["t_h_r"] == "2" and (values["t_o_l"], values["t_o_r"]) == ("2", "1")


def test_a_wrong_boolean_identity_yields_a_distinguishing_assignment():
    shape = _shape("boolean_identity_fail")
    r = run(shape)
    env = {a.symbol: a.value == "true" for a in r.witness_model}
    lhs = not (env["a"] and env["b"])
    rhs = (not env["a"]) and (not env["b"])
    assert lhs != rhs
