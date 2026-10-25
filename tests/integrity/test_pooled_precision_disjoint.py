"""B7 pooling keeps a contradiction between stated figures (repair round 1, re-run review INV-3). Two claims that derive
one figure by their own routes and state it at a precision are pooled at that precision, so routes that agree at it
(24.033 and 24.045, both stated 24.0) never contradict; but claims whose stated intervals do not meet still contradict
each other: 24.0 (read [23.95, 24.05)) against 24.1 ([24.05, 24.15)), each end as strict as the claim states it, and
24.0 against 26.0. The contradiction needs both claims, so it is INT-CONFLICT-001 naming both, never one claim's own."""
from __future__ import annotations

import pytest

from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity.cross_check import _interval_bounds, check_cross_report_consistency, split_by_precision
from epinoic_logic.ir.schema import Problem

CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)


def _route(cid: str, num: int, den: int, lo: str, hi: str, *, lo_op: str = "ge", hi_op: str = "lt") -> Problem:
    """Claim ``cid``: v = 230, r = num/den (its own route), and it states lo <= r < hi."""
    var = lambda n: {"op": "var", "name": n}  # noqa: E731
    return Problem.model_validate({
        "problem_id": f"p-{cid}", "request_id": "req", "claim_id": cid, "query": "entailment",
        "symbols": [{"name": "r", "sort": "Real", "meaning": "the resistance R in ohms"}, {"name": "v", "sort": "Real", "meaning": "voltage"}],
        "premises": [{"id": f"V_{cid}", "expr": {"op": "eq", "left": var("v"), "right": {"op": "real", "value": "230"}}, "grounding": {"kind": "arithmetic_fact"}},
                     {"id": f"R_{cid}", "expr": {"op": "eq", "left": var("r"), "right": {"op": "div", "left": {"op": "real", "value": str(num)},
                                                                                             "right": {"op": "real", "value": str(den)}}},
                      "grounding": {"kind": "specialist_inference"}}],
        "conclusion": {"id": f"C_{cid}", "expr": {"op": "and", "args": [{"op": lo_op, "left": var("r"), "right": {"op": "real", "value": lo}},
                                                                         {"op": hi_op, "left": var("r"), "right": {"op": "real", "value": hi}}]}}})


def _check(*problems: Problem):
    res, findings = check_cross_report_consistency(list(problems), request_id="req", config=CFG, signing_key=b"k" * 32)
    return res.status, sorted({f.code for f in findings if f.code.startswith("INT-CONFLICT")}), findings


@pytest.mark.parametrize("second", [_route("b", 24130, 1000, "24.05", "24.15"), _route("b", 26000, 1000, "25.95", "26.05")])
def test_claims_whose_stated_intervals_do_not_meet_contradict_each_other(second):
    status, codes, findings = _check(_route("a", 24040, 1000, "23.95", "24.05"), second)
    assert status is S.INCONSISTENT_PREMISES and codes == ["INT-CONFLICT-001"]
    [f] = [f for f in findings if f.code == "INT-CONFLICT-001"]
    assert sorted(set(f.claim_ids) & {"a", "b"}) == ["a", "b"]


def test_three_routes_must_share_one_stated_value():
    status, codes, _ = _check(_route("a", 24040, 1000, "23.95", "24.05"), _route("b", 24045, 1000, "23.95", "24.05"),
                              _route("c", 24130, 1000, "24.05", "24.15"))
    assert status is S.INCONSISTENT_PREMISES and codes == ["INT-CONFLICT-001"]


def test_clean_control_routes_that_agree_at_their_stated_precision_do_not_conflict():
    status, codes, _ = _check(_route("a", 24033, 1000, "23.95", "24.05"), _route("b", 24045, 1000, "23.95", "24.05"))
    assert status is S.CONSISTENT and codes == []


def test_clean_control_intervals_that_share_an_end_both_include_meet():
    # 23.95 <= r <= 24.05 and 24.05 <= r <= 24.15 share 24.05: one value can be stated by both
    status, codes, _ = _check(_route("a", 24040, 1000, "23.95", "24.05", hi_op="le"), _route("b", 24060, 1000, "24.05", "24.15"))
    assert status is S.CONSISTENT and codes == []


def test_the_bounds_keep_their_strictness_and_the_first_claim_states_its_own():
    a, b = _route("a", 24040, 1000, "23.95", "24.05"), _route("b", 24130, 1000, "24.05", "24.15")
    assert sorted(op for op, _lit in _interval_bounds(b, "r")) == ["ge", "lt"]
    split, _routes = split_by_precision([a, b])
    assert [p.id for p in split[0].premises if p.id.startswith("stated_")] == ["stated_r"]
    assert len([p for p in split[1].premises if p.id.startswith("stated_")]) == 1
