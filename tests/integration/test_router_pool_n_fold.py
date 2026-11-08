"""Pool port 1.2 of the router port's pool operation (``router_pool``; PROTOCOL.md section 7b; architecture step 3): a
combined answer's N_FOLD review and the flash decision maker's record of every dossier's review, as data.

- a 1.2 request item may carry its size (``features``) and, for a combined answer, its sources (2 to 16) and its merged
  part, each with its own risk reading and size; a 1.1 request never carries a combined answer (``KIT-RT-014``);
- a 1.2 plan reviews exactly the combined answers N_FOLD (each source by its own instances, then the merged review, with
  a request-scoped temporary context of at most 65,536 bytes discarded after the request) and every other dossier
  IN_DEPTH or DUPLICATE (``KIT-RT-007``); every assignment carries a decision record that states only what the plan and
  the request hold (``KIT-RT-012``): its method and approach, its reviews, the echo of what it read, exactly one chosen
  candidate (the method it runs), ``combined_n_fold`` exactly for a combined answer, and an N_FOLD's parts in order;
- the accounting counts the instances of the source reviews (``KIT-RT-013``), and the reasons name the N_FOLD reviews;
- a 1.2 hello declares N_FOLD; the contract holds no floor of its own (the overseer's floor decides ``KIT-RT-020``).
"""
from __future__ import annotations

import copy
import json

import pytest

from epinoic_logic.integration import router_pool as RP
from epinoic_logic.integration.canonical import sha256_json
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.protocol import dump

IDENTITY = {"name": "test-pool-router", "version": "1.0", "rules_sha256": "a1" * 32, "cost_data_sha256": "b2" * 32}
HELLO = {"schema": RP.POOL_HELLO_SCHEMA, "protocol": "epinoic.integration.v1", "port_version": "1.2", "router": IDENTITY,
         "capabilities": ["pool-plan"], "methods": ["IN_DEPTH", "DUPLICATE", "N_FOLD"], "profiles": ["standard"], "tier": "cheapest", "deterministic": True}
FEATURES = {"transfers": 4, "chars": 40000, "stem": False, "translations": 0}


def _part(**kw) -> dict:
    return {"repeated_faults": 0, "risk_signals": [], "risk_records": [], "features": dict(FEATURES, transfers=2, chars=15000), **kw}


def _items() -> list[dict]:
    return [{"repeated_faults": 0, "risk_signals": [], "risk_records": [], "advised": False, "features": dict(FEATURES)},
            {"repeated_faults": 0, "risk_signals": [], "risk_records": [], "advised": False, "features": dict(FEATURES, transfers=7, chars=60000),
             "sources": [_part(), _part(risk_signals=["rejection"])], "merged": _part()}]


def _req(items=None) -> RP.PoolRoutingRequest12:
    return RP.build_pool_request(items if items is not None else _items(), max_instances=4, per_instance_quota=8, port_version="1.2")


def _read(it) -> dict:
    d = dump(it)
    return {"repeated_faults": d["repeated_faults"], "risk_signals": d["risk_signals"], "risk_records": d["risk_records"], "advised": d["advised"],
            "features": d.get("features"), "sources": len(d.get("sources") or [])}


def _cand(method: str, reviews: int, why: str, keeps: bool) -> dict:
    return {"method": method, "reviews": reviews, "calls": reviews, "tokens": 70000 * reviews, "seconds": 30 * reviews, "keeps_accuracy": keeps, "why": why}


def _plan(req) -> dict:
    """A plan at the floor: the plain dossier IN_DEPTH by instance 1; the combined answer N_FOLD, source 1 by instance 1,
    source 2 (a rejection) by instances 2 and 3, the merged review by instance 1."""
    plain, combined = req.items
    a1 = {"item_id": plain.item_id, "method": "IN_DEPTH", "instances": [1], "sources": [], "context": None,
          "decision": {"approach": "in_depth", "method": "IN_DEPTH", "reviews": 1, "calls": 1, "read": _read(plain), "need_tokens": 70000,
                       "budget_tokens": 200000, "fits": True, "reasons": ["in_depth_cheapest"],
                       "candidates": [_cand("IN_DEPTH", 1, "chosen", True), _cand("DUPLICATE", 2, "costlier", True)], "parts": [],
                       "estimated_cost": {"tokens": 70000, "seconds": 30}}}
    a2 = {"item_id": combined.item_id, "method": "N_FOLD", "instances": [1],
          "sources": [{"method": "IN_DEPTH", "instances": [1]}, {"method": "DUPLICATE", "instances": [2, 3]}],
          "context": {"scope": "request", "contents": "validated_outcomes", "max_bytes": 65536, "discard": "after_request"},
          "decision": {"approach": "duplication", "method": "N_FOLD", "reviews": 1, "calls": 4, "read": _read(combined), "need_tokens": 90000,
                       "budget_tokens": 200000, "fits": True, "reasons": ["agreement_risk", "combined_n_fold"],
                       "candidates": [_cand("N_FOLD", 1, "chosen", True), _cand("IN_DEPTH", 1, "combined_needs_n_fold", False),
                                      _cand("DUPLICATE", 2, "combined_needs_n_fold", False)],
                       "parts": [{"part": "source", "index": 1, "reviews": 1, "need_tokens": 60000, "fits": True, "reasons": ["in_depth_cheapest"]},
                                 {"part": "source", "index": 2, "reviews": 2, "need_tokens": 60000, "fits": True, "reasons": ["agreement_risk"]},
                                 {"part": "merged", "index": 0, "reviews": 1, "need_tokens": 60000, "fits": True, "reasons": ["in_depth_cheapest"]}],
                       "estimated_cost": {"tokens": 4 * 60000, "seconds": 120}}}
    return {"schema": RP.POOL_PLAN_SCHEMA, "protocol": "epinoic.integration.v1", "port_version": "1.2", "origin": "router", "plan_id": "pool-plan-12",
            "request_sha256": sha256_json(dump(req)), "router": IDENTITY, "profile": "standard", "instances": 3, "assignments": [a1, a2],
            "loads": [3, 1, 1], "review_units": 5, "needed_instances": 3, "capped": False, "over_quota": False,
            "reasons": [{"code": "pool_baseline"}, {"code": "pool_n_fold", "count": 1, "sources": 2}],
            "estimated_cost": {"tokens": 70000 + 240000, "seconds": 150}}


def _check(plan, req=None):
    req = req or _req()
    return RP.check_pool_plan(plan if isinstance(plan, str) else json.dumps(plan), req, hello=RP.check_pool_hello(HELLO))


def _assign(p: dict, k: int, **changes) -> dict:
    out = copy.deepcopy(p)
    out["assignments"][k].update(changes)
    return out


def _decide(p: dict, k: int, **changes) -> dict:
    out = copy.deepcopy(p)
    out["assignments"][k]["decision"].update(changes)
    return out


# ----------------------------------------------------------------------------------------------- the request
def test_a_1_2_request_carries_sizes_and_a_combined_answers_parts_and_a_1_1_request_never_a_combined_answer():
    req = _req()
    assert req.port_version == "1.2" and [it.item_id for it in req.items] == ["d1", "d2"] and len(req.items[1].sources) == 2
    raw = dump(req)
    for bad in (dict(raw, items=[raw["items"][0], dict(raw["items"][1], sources=raw["items"][1]["sources"][:1])]),   # one source is no combined answer
                dict(raw, items=[raw["items"][0], {k: v for k, v in raw["items"][1].items() if k != "merged"}]),  # sources without a merged part
                dict(raw, items=[dict(raw["items"][0], merged=raw["items"][1]["merged"]), raw["items"][1]]),     # a merged part without sources
                dict(raw, items=[dict(raw["items"][0], features=dict(FEATURES, chars=-1)), raw["items"][1]])):
        with pytest.raises(IntegrationError) as exc:
            RP.check_pool_request(bad)
        assert exc.value.code == "KIT-RT-014"
    with pytest.raises(IntegrationError) as exc:
        RP.build_pool_request(_items(), max_instances=4, per_instance_quota=8, port_version="1.1")
    assert exc.value.code == "KIT-RT-014"
    assert RP.check_pool_request(json.dumps(raw)) == req


def test_a_1_2_hello_declares_n_fold():
    h = RP.check_pool_hello(HELLO)
    assert h.port_version == "1.2" and "N_FOLD" in h.methods and set(RP.POOL_RUN_METHODS_BY_VERSION["1.2"]) == {"IN_DEPTH", "DUPLICATE", "N_FOLD"}
    assert set(RP.POOL_RUN_METHODS_BY_VERSION["1.1"]) == {"IN_DEPTH", "DUPLICATE"}


# ----------------------------------------------------------------------------------------------- the plan
def test_a_plan_at_the_floor_is_in_contract():
    plan = _check(_plan(_req()))
    plain, combined = plan.assignments
    assert (plain.method, combined.method, [s.method for s in combined.sources]) == ("IN_DEPTH", "N_FOLD", ["IN_DEPTH", "DUPLICATE"])
    assert combined.context.max_bytes == 65536 and combined.decision.parts[-1].part == "merged" and plan.estimated_cost.tokens == 310000


def test_every_n_fold_rule_of_the_plan_has_its_code():
    req = _req()
    p = _plan(req)
    a2 = p["assignments"][1]
    cases = [
        # KIT-RT-007: N_FOLD exactly for a combined answer, its sources in order, its context, the shape of each source
        (_assign(p, 0, method="N_FOLD"), "KIT-RT-007"),
        (_assign(p, 1, method="DUPLICATE", instances=[1, 2], sources=[], context=None), "KIT-RT-007"),
        (_assign(p, 1, sources=a2["sources"][:1]), "KIT-RT-007"),
        (_assign(p, 1, context=None), "KIT-RT-007"),
        (_assign(p, 1, sources=[a2["sources"][0], {"method": "IN_DEPTH", "instances": [2, 3]}]), "KIT-RT-007"),
        (_assign(p, 1, sources=[a2["sources"][0], {"method": "DUPLICATE", "instances": [2, 2]}]), "KIT-RT-007"),
        (_assign(p, 0, sources=a2["sources"]), "KIT-RT-007"),
        (_assign(p, 0, context=a2["context"]), "KIT-RT-007"),
        (_assign(p, 1, context=dict(a2["context"], max_bytes=65537)), "KIT-RT-007"),
        # KIT-RT-012: the decision states only what the plan and the request hold
        (_decide(p, 0, method="DUPLICATE"), "KIT-RT-012"),
        (_decide(p, 0, approach="duplication"), "KIT-RT-012"),
        (_decide(p, 1, reviews=2), "KIT-RT-012"),
        (_decide(p, 0, read=dict(p["assignments"][0]["decision"]["read"], repeated_faults=1)), "KIT-RT-012"),
        (_decide(p, 1, read=dict(a2["decision"]["read"], sources=3)), "KIT-RT-012"),
        (_decide(p, 0, candidates=[_cand("IN_DEPTH", 1, "chosen", True), _cand("DUPLICATE", 2, "chosen", True)]), "KIT-RT-012"),
        (_decide(p, 0, candidates=[_cand("IN_DEPTH", 1, "costlier", True), _cand("DUPLICATE", 2, "chosen", True)]), "KIT-RT-012"),
        (_decide(p, 1, reasons=["agreement_risk"]), "KIT-RT-012"),
        (_decide(p, 0, reasons=["in_depth_cheapest", "combined_n_fold"]), "KIT-RT-012"),
        (_decide(p, 0, reasons=["in_depth_cheapest", "in_depth_cheapest"]), "KIT-RT-012"),
        (_decide(p, 1, parts=a2["decision"]["parts"][:2]), "KIT-RT-012"),
        (_decide(p, 1, parts=[a2["decision"]["parts"][1], a2["decision"]["parts"][0], a2["decision"]["parts"][2]]), "KIT-RT-012"),
        (_decide(p, 0, parts=a2["decision"]["parts"]), "KIT-RT-012"),
        # the reasons name the N_FOLD reviews
        (dict(copy.deepcopy(p), reasons=[{"code": "pool_baseline"}]), "KIT-RT-012"),
        (dict(copy.deepcopy(p), reasons=[{"code": "pool_baseline"}, {"code": "pool_n_fold", "count": 1, "sources": 3}]), "KIT-RT-012"),
        # KIT-RT-013: the accounting counts the source reviews' instances
        (dict(copy.deepcopy(p), loads=[2, 1, 1], review_units=4), "KIT-RT-013"),
        (dict(copy.deepcopy(p), estimated_cost={"tokens": 1, "seconds": 150}), "KIT-RT-013"),
    ]
    hello = RP.check_pool_hello(HELLO)
    for raw, code in cases:
        with pytest.raises(IntegrationError) as exc:
            RP.check_pool_plan(json.dumps(raw), req, hello=hello)
        assert exc.value.code == code, (exc.value.code, exc.value.detail)


def test_a_plan_at_one_version_is_refused_for_a_request_at_the_other():
    req = _req()
    p = _plan(req)
    with pytest.raises(IntegrationError) as exc:
        _check(dict(p, port_version="1.1"), req)
    assert exc.value.code in ("KIT-RT-001", "KIT-RT-002", "KIT-RT-014", "KIT-RT-015")


def test_the_contract_holds_no_floor_the_overseer_refuses_what_is_below_it():
    """In contract, but its escalated source has one instance: the overseer's floor (epinoic_overseer.floor) refuses it with
    KIT-RT-020, and the floor plan runs (overseer/tests/overseer_tests/test_twofold.py)."""
    req = _req()
    p = _plan(req)
    cheap = copy.deepcopy(p)
    a2 = cheap["assignments"][1]
    a2["sources"][1] = {"method": "IN_DEPTH", "instances": [2]}
    a2["decision"]["parts"][1]["reviews"] = 1
    a2["decision"]["calls"] = 3
    a2["decision"]["estimated_cost"] = {"tokens": 3 * 60000, "seconds": 90}
    cheap.update(instances=2, needed_instances=2, loads=[3, 1], review_units=4, estimated_cost={"tokens": 70000 + 180000, "seconds": 120})
    assert _check(cheap, req).assignments[1].sources[1].instances == [2]
