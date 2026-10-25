"""Repair round 2 (formal-robustness-1 variant): a problem whose exact arithmetic can reach numbers of tens of thousands of
digits is refused before it compiles (``E307``, INVALID_FORMALIZATION), because the solver cannot be stopped at its timeout
inside arithmetic on such numbers. The bound is read from the IR alone (:func:`coefficient_digits`). Controls: the same
chain kept short, and the largest ordinary problems the default limits admit, are decided as before."""
from __future__ import annotations

import time

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine import identity as identity_mod
from epinoic_logic.engine.policies import MAX_COEFFICIENT_DIGITS, coefficient_digits
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem

CFG = SolverConfig(timeout_ms=2000, memory_max_mb=None)
THIRTY = "7" * 30


def _v(n):
    return {"op": "var", "name": n}


def _r(v):
    return {"op": "real", "value": v}


def _problem(symbols, premises, conclusion) -> Problem:
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": n, "sort": s} for n, s in symbols],
                                   "premises": [{"id": f"p{i}", "expr": e} for i, e in enumerate(premises)],
                                   "conclusion": {"id": "C", "expr": conclusion}})


def _chain(links: int) -> Problem:
    """y_i = (a product of 25 thirty-digit literals) * y_(i-1) + 1.25, from x = 777...7.5: each link multiplies the
    coefficients the solver works with by about 10**750."""
    premises = [{"op": "eq", "left": _v("x"), "right": _r(THIRTY + ".5")}]
    prev = "x"
    for i in range(1, links + 1):
        product = {"op": "mul", "args": [_r(THIRTY)] * 25 + [_v(prev)]}
        premises.append({"op": "eq", "left": _v(f"y{i}"), "right": {"op": "add", "args": [product, _r("1.25")]}})
        prev = f"y{i}"
    symbols = [("x", "Real")] + [(f"y{i}", "Real") for i in range(1, links + 1)]
    return _problem(symbols, premises, {"op": "lt", "left": _v(prev), "right": _r("0")})


def test_a_chain_whose_numbers_outgrow_the_bound_is_refused_before_the_solver_runs():
    t0 = time.perf_counter()
    r = verify(_chain(40), CFG)
    elapsed = time.perf_counter() - t0
    assert r.status is S.INVALID_FORMALIZATION and [d.code for d in r.diagnostics] == ["E307"]
    assert "limit is 16000" in r.diagnostics[0].message and r.diagnostics[0].path == "premises[1].expr"
    assert [t.stage for t in r.timings] == ["validate"]          # nothing was compiled or solved
    assert elapsed < 1.0


def test_the_same_chain_kept_short_is_decided_by_the_solver():
    r = verify(_chain(10), CFG)
    assert "E307" not in {d.code for d in r.diagnostics}
    assert "entailment" in {t.stage for t in r.timings}


def test_the_largest_ordinary_problems_stay_far_below_the_bound():
    literal = ("1234567890" * 4)[:39] + ".5"                    # a 40-digit literal, the longest the default limits admit
    symbols = [(f"x{i}", "Real") for i in range(64)]
    premises = [{"op": "eq", "left": _v(f"x{i % 64}"), "right": {"op": "add", "args": [_v(f"x{(i + 1) % 64}"), _r(literal)]}} for i in range(127)]
    problem = _problem(symbols, premises, {"op": "lt", "left": _v("x0"), "right": _r("0")})
    digits, _where = coefficient_digits(problem)
    assert digits < MAX_COEFFICIENT_DIGITS // 4
    assert "E307" not in {d.code for d in verify(problem, CFG).diagnostics}


def test_the_bound_reads_literals_products_and_divisions():
    one = _problem([("x", "Real")], [{"op": "eq", "left": _v("x"), "right": _r("1.25")}], {"op": "gt", "left": _v("x"), "right": _r("1")})
    digits, where = coefficient_digits(one)
    assert where == "premises[0].expr" and digits < 20
    product = _problem([("x", "Real")], [{"op": "eq", "left": _v("x"), "right": {"op": "mul", "args": [_r("9" * 40)] * 10 + [_r("2")]}}],
                       {"op": "gt", "left": _v("x"), "right": _r("1")})
    assert coefficient_digits(product)[0] >= 400                  # a product of ten 40-digit literals has 400 digits
    divided = _problem([("x", "Real")], [{"op": "eq", "left": {"op": "div", "left": _v("x"), "right": _r("3" * 40)}, "right": _r("1")}],
                       {"op": "gt", "left": _v("x"), "right": _r("1")})
    assert coefficient_digits(divided)[0] >= 40
    booleans = _problem([("a", "Bool")], [_v("a")], _v("a"))
    assert coefficient_digits(booleans) == (0, None)


def test_the_bound_is_part_of_the_bound_policy():
    assert identity_mod.policy_manifest()["max_coefficient_digits"] == MAX_COEFFICIENT_DIGITS
