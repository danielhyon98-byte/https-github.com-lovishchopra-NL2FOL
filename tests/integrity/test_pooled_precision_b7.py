"""B7: a figure two claims derive by different routes, each stating it at a precision, is pooled at that precision.

ph s2.1 derives R = 230/9.57 = 24.033 and s2.2 derives R = 230²/2200 = 24.045; both state 24.0 Ω (3 s.f.), so each
concludes 23.95 <= R < 24.05. Pooled exactly under one symbol the two routes contradicted each other (INT-CONFLICT-001 on
correct work). Each later route now gets its own copy of the symbol, linked to the first by |R1 − R2| <= h1 + h2: routes that
agree at their stated precision never conflict, and routes that do not (24.0 against 26.0) still do.
"""
from __future__ import annotations

import copy

from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity.cross_check import check_cross_report_consistency, check_synthesis_entailment, split_by_precision, stated_interval
from epinoic_logic.ir.schema import Assertion, Problem

from .. import argdiag_cases as C

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)


def _routes() -> list[Problem]:
    case = C.load_case("e2e-B7-ph")
    by_id = {t["claim_id"]: t for t in case["translations"] if "claim_id" in t}
    return [Problem.model_validate(copy.deepcopy(by_id[cid]["proposal"]["problem"])) for cid in ("s2.1", "s2.2")]


def _second_route_at(value_lo: str, value_hi: str, coefficient: str) -> Problem:
    data = _routes()[1].model_dump(mode="json", exclude_none=True)
    data["premises"][2]["expr"]["left"]["args"][0]["value"] = coefficient       # coefficient × R = 52900
    data["conclusion"]["expr"]["args"][0]["right"]["value"] = value_lo
    data["conclusion"]["expr"]["args"][1]["right"]["value"] = value_hi
    return Problem.model_validate(data)


def test_two_routes_stated_as_24_0_do_not_conflict():
    res, findings = check_cross_report_consistency(_routes(), request_id="req-ph-e1", config=CFG)
    assert res is not None and res.status is S.CONSISTENT
    assert not [f for f in findings if f.code.startswith("INT-CONFLICT")]


def test_control_routes_that_differ_beyond_their_precision_still_conflict():
    r1, _r2 = _routes()
    r2 = _second_route_at("25.95", "26.05", "2034.615")                            # R = 52900 / 2034.615 = 26.0
    res, findings = check_cross_report_consistency([r1, r2], request_id="req-ph-e1", config=CFG)
    assert res is not None and res.status is S.INCONSISTENT_PREMISES
    [f] = [f for f in findings if f.code == "INT-CONFLICT-001"]
    assert f.severity == "error" and sorted(f.claim_ids) == ["s2.1", "s2.2"]


def test_the_split_links_the_routes_by_their_half_widths():
    r1, r2 = _routes()
    assert stated_interval(r1, "heater_res") is not None and stated_interval(r2, "heater_res") is not None
    split, routes = split_by_precision([r1, r2])
    [(first, c1, h1), (second, c2, h2)] = routes["heater_res"]
    assert (first, c1, c2) == ("heater_res", "s2.1", "s2.2") and second != first and h1 == h2 == "1/20"
    link = [a for a in split[1].premises if a.id.startswith("precision_")]
    assert len(link) == 1 and {s.name for s in split[1].symbols} >= {"heater_res", second}


def test_control_one_route_or_no_stated_precision_is_pooled_exactly():
    r1, r2 = _routes()
    assert split_by_precision([r1])[1] == {}
    exact = r2.model_dump(mode="json", exclude_none=True)
    exact["conclusion"] = {"id": "claim_r2", "expr": {"op": "eq", "left": {"op": "var", "name": "heater_res"}, "right": {"op": "real", "value": "24.0"}}}
    assert split_by_precision([r1, Problem.model_validate(exact)])[1] == {}


def test_a_synthesis_citing_both_routes_follows_at_the_stated_precision():
    concl = Assertion.model_validate({"id": "synth_r", "expr": {"op": "and", "args": [
        {"op": "ge", "left": {"op": "var", "name": "heater_res"}, "right": {"op": "real", "value": "23.95"}},
        {"op": "lt", "left": {"op": "var", "name": "heater_res"}, "right": {"op": "real", "value": "24.05"}}]}})
    res, findings = check_synthesis_entailment(_routes(), concl, request_id="req-ph-e1", synthesized_claim_id="syn-1", config=CFG)
    assert res is not None and res.status is S.ENTAILED
    assert not [f for f in findings if f.code.startswith("INT-CONFLICT")]
