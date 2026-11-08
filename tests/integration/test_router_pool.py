"""The router port's pool operation (``router_pool``; PROTOCOL.md section 7b): the contract the overseer pool and the
flash router share, as data.

- a pool request carries positions and risk classes only: nothing a blind dossier hides, no key, no text;
- the version handshake: a pool hello at a pool port version the overseer does not speak, without the ``pool-plan``
  capability, naming a model or the floor's reserved identity is refused (``KIT-RT-015``);
- a pool plan is refused with the code of the first rule it breaks (001 to 013), never raises for anything a router
  returns, and holds no floor of its own (the overseer's floor decides ``KIT-RT-020``);
- the router's own process runs the pool's two operations only for a module that offers them (the capability), and the
  service's two operations as before.
"""
from __future__ import annotations

import copy
import json

import pytest

from epinoic_logic.integration import router_child as C
from epinoic_logic.integration import router_pool as RP
from epinoic_logic.integration.canonical import canonical_json, sha256_json
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.protocol import dump

IDENTITY = {"name": "test-pool-router", "version": "1.0", "rules_sha256": "a1" * 32, "cost_data_sha256": "b2" * 32}
HELLO = {"schema": RP.POOL_HELLO_SCHEMA, "protocol": "epinoic.integration.v1", "port_version": "1.1", "router": IDENTITY,
         "capabilities": ["pool-plan"], "methods": ["IN_DEPTH", "DUPLICATE"], "profiles": ["standard"], "tier": "cheapest", "deterministic": True}


def _req(items=None, **limits) -> RP.PoolRoutingRequest:
    """A pool port 1.1 request: these tests hold the 1.1 contract (its hello and plans below), which the overseer still speaks
    beside 1.2 (``tests/integration/test_router_pool_n_fold.py``)."""
    items = items if items is not None else [{"repeated_faults": 1}, {"repeated_faults": 0, "risk_signals": ["named_defect"]}, {"repeated_faults": 0}]
    return RP.build_pool_request(items, max_instances=limits.get("max_instances", 4), per_instance_quota=limits.get("quota", 8), port_version="1.1")


def _plan(req: RP.PoolRoutingRequest) -> dict:
    """A plan at the floor: every escalated dossier to instances 1 and 2, every other one to instance 1."""
    esc = [bool(it.repeated_faults or it.risk_signals or it.advised) for it in req.items]
    n = (2 if any(esc) else 1) if req.items else 0
    assignments = [{"item_id": it.item_id, "method": "DUPLICATE" if e else "IN_DEPTH", "instances": [1, 2] if e else [1]} for it, e in zip(req.items, esc)]
    loads = [sum(1 for a in assignments if k + 1 in a["instances"]) for k in range(n)]
    reasons = [{"code": "pool_baseline"} if req.items else {"code": "pool_empty"}]
    repeated = [it for it in req.items if it.repeated_faults]
    if repeated:
        reasons.append({"code": "pool_repeated_faults", "count": len(repeated), "reviewers": 2})
    return {"schema": RP.POOL_PLAN_SCHEMA, "protocol": "epinoic.integration.v1", "port_version": "1.1", "origin": "router", "plan_id": "pool-plan-1",
            "request_sha256": sha256_json(dump(req)), "router": IDENTITY, "profile": "standard", "instances": n, "assignments": assignments,
            "loads": loads, "review_units": sum(loads), "needed_instances": n, "capped": False, "over_quota": False, "reasons": reasons,
            "estimated_cost": None}


def _check(plan: dict, req: RP.PoolRoutingRequest | None = None):
    req = req or _req()
    return RP.check_pool_plan(json.dumps(plan), req, hello=RP.check_pool_hello(HELLO))


# ----------------------------------------------------------------------------------------------- the request
def test_a_pool_request_carries_positions_and_risk_classes_only():
    req = _req()
    assert [it.item_id for it in req.items] == ["d1", "d2", "d3"] and req.port_version == "1.1" and req.port_version in RP.POOL_PORT_VERSIONS
    raw = dump(req)
    for bad, code in ((dict(raw, items=[dict(raw["items"][0], item_id="d2"), *raw["items"][1:]]), "KIT-RT-014"),
                      (dict(raw, items=[dict(raw["items"][0], risk_signals=["not_a_class"])]), "KIT-RT-014"),
                      (dict(raw, items=[dict(raw["items"][0], risk_signals=["rejection", "contradiction"])]), "KIT-RT-014"),
                      (dict(raw, items=[dict(raw["items"][0], key="r2/en-t3::invented_quotation")]), "KIT-RT-014"),
                      (dict(raw, variant="invented_quotation"), "KIT-RT-011"),
                      (dict(raw, limits=dict(raw["limits"], max_instances=65)), "KIT-RT-014")):
        with pytest.raises(IntegrationError) as exc:
            RP.check_pool_request(bad)
        assert exc.value.code == code
    assert RP.check_pool_request(canonical_json(raw)) == req


# ----------------------------------------------------------------------------------------------- the handshake
@pytest.mark.parametrize("change,detail", [
    ({"port_version": "1.0"}, "pool port version 1.0"),
    ({"port_version": "2.0"}, "pool port version 2.0"),
    ({"capabilities": ["plan"]}, "pool-plan capability"),
    ({"router": dict(IDENTITY, name="haiku-router")}, "names no model"),
    ({"router": dict(IDENTITY, name="minimum-oversight-floor")}, "reserved identity"),
    ({"tier": "largest"}, "does not validate"),
    ({"deterministic": False}, "does not validate"),
    ({"extra": 1}, "does not validate"),
])
def test_the_version_handshake_refuses_a_pool_hello_out_of_contract(change, detail):
    with pytest.raises(IntegrationError, match=detail) as exc:
        RP.check_pool_hello(dict(HELLO, **change))
    assert exc.value.code == "KIT-RT-015"
    assert RP.check_pool_hello(json.dumps(HELLO)).router.name == "test-pool-router"


# ----------------------------------------------------------------------------------------------- the plan
def test_a_plan_at_the_floor_is_in_contract():
    plan = _check(_plan(_req()))
    assert plan.instances == 2 and [a.method for a in plan.assignments] == ["DUPLICATE", "DUPLICATE", "IN_DEPTH"]
    empty = _req([])
    assert _check(_plan(empty), empty).instances == 0


def _with(plan: dict, **changes) -> dict:
    out = copy.deepcopy(plan)
    out.update(changes)
    return out


def test_every_rule_of_the_plan_has_its_code():
    req = _req()
    p = _plan(req)
    a = p["assignments"]
    cases = [
        ("not json", "KIT-RT-001"),
        (_with(p, extra=1), "KIT-RT-001"),
        (_with(p, verdicts=[]), "KIT-RT-011"),
        (_with(p, reasons=[{"code": "pool_baseline"}, {"code": "pool_repeated_faults", "count": 1, "reviewers": 2, "note": "OVS-FID-001"}]), "KIT-RT-011"),
        (_with(p, plan_id="claude-plan"), "KIT-RT-009"),
        (_with(p, model="any"), "KIT-RT-009"),
        (_with(p, request_sha256="0" * 64), "KIT-RT-002"),
        (_with(p, router=dict(IDENTITY, version="2.0")), "KIT-RT-003"),
        (_with(p, router=dict(IDENTITY, name="minimum-oversight-floor-x")), "KIT-RT-003"),
        (_with(p, assignments=[*a, {"item_id": "d4", "method": "IN_DEPTH", "instances": [1]}]), "KIT-RT-004"),
        (_with(p, assignments=a[:2]), "KIT-RT-005"),
        (_with(p, assignments=[*a, a[2]]), "KIT-RT-006"),
        (_with(p, assignments=[a[0], a[1], dict(a[2], method="SPLIT")]), "KIT-RT-007"),
        (_with(p, assignments=[a[0], a[1], dict(a[2], method="N_FOLD")]), "KIT-RT-007"),
        (_with(p, assignments=[a[0], a[1], dict(a[2], instances=[1, 2])]), "KIT-RT-007"),
        (_with(p, assignments=[dict(a[0], instances=[1, 1]), a[1], a[2]]), "KIT-RT-007"),
        (_with(p, assignments=[a[0], a[1], dict(a[2], instances=[3])]), "KIT-RT-008"),
        (_with(p, instances=5, needed_instances=5, loads=[3, 2, 0, 0, 0]), "KIT-RT-008"),
        (_with(p, profile="fast"), "KIT-RT-010"),
        (_with(p, reasons=[{"code": "pool_baseline"}, {"code": "pool_baseline"}]), "KIT-RT-012"),
        (_with(p, reasons=[{"code": "pool_baseline", "count": 1}]), "KIT-RT-012"),
        (_with(p, reasons=[{"code": "pool_baseline"}, {"code": "pool_repeated_faults", "count": 2, "reviewers": 2}]), "KIT-RT-012"),
        (_with(p, reasons=[{"code": "pool_baseline"}, {"code": "pool_risk_signals", "count": 1, "classes": ["rejection"], "reviewers": 2}]), "KIT-RT-012"),
        (_with(p, reasons=[{"code": "pool_baseline"}, {"code": "pool_capped", "maximum": 4, "needed": 2}]), "KIT-RT-012"),
        (_with(p, reasons=[{"code": "pool_empty"}]), "KIT-RT-012"),
        (_with(p, loads=[1, 1]), "KIT-RT-013"),
        (_with(p, loads=[3]), "KIT-RT-013"),
        (_with(p, review_units=1), "KIT-RT-013"),
        (_with(p, capped=True), "KIT-RT-013"),
        (_with(p, over_quota=True), "KIT-RT-013"),
        (_with(p, needed_instances=3), "KIT-RT-013"),
        (_with(p, estimated_cost={"tokens": -1, "seconds": 0}), "KIT-RT-013"),
    ]
    hello = RP.check_pool_hello(HELLO)
    for raw, code in cases:
        with pytest.raises(IntegrationError) as exc:
            RP.check_pool_plan(raw if isinstance(raw, str) else json.dumps(raw), req, hello=hello)
        changed = raw if isinstance(raw, str) else {k: raw.get(k) for k in raw if raw.get(k) != p.get(k)}
        assert exc.value.code == code, (changed, exc.value.code, exc.value.detail)


def test_the_contract_holds_no_floor_a_plan_below_it_is_the_overseers_to_refuse():
    req = _req()
    p = _plan(req)
    cheap = _with(p, instances=1, needed_instances=1, loads=[3], review_units=3,
                  assignments=[{"item_id": it.item_id, "method": "IN_DEPTH", "instances": [1]} for it in req.items])
    assert _check(cheap, req).instances == 1  # in contract; the overseer's floor (epinoic_overseer.floor) refuses it with KIT-RT-020


# ----------------------------------------------------------------------------------------------- attachment and the router's process
def test_a_router_module_is_attached_for_the_pool_only_with_the_capability(tmp_path, monkeypatch):
    (tmp_path / "service_only_router_for_pool.py").write_text("def hello():\n    return '{}'\ndef plan(r):\n    return '{}'\n")
    (tmp_path / "pool_router_for_pool.py").write_text(
        "import json, hashlib\n"
        f"HELLO = {HELLO!r}\n"
        "def hello():\n    return '{}'\n"
        "def plan(r):\n    return '{}'\n"
        "def pool_hello():\n    return json.dumps(HELLO)\n"
        "def pool_plan(request_json):\n    return json.dumps({'not': 'a plan'})\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert RP.attach_pool_router(None).refusal is None and not RP.attach_pool_router("none").attached
    refused = RP.attach_pool_router("service_only_router_for_pool")
    assert (refused.attached, refused.refusal) == (False, "KIT-RT-015") and "pool's capability" in refused.detail
    att = RP.attach_pool_router("pool_router_for_pool")
    assert att.attached and att.identity.name == "test-pool-router" and not att.in_process
    answer = RP.ask_pool_router(_req(), att)
    assert answer.refusal is None and answer.data == {"not": "a plan"}
    with pytest.raises(IntegrationError) as exc:
        RP.check_pool_plan(answer.data, _req(), hello=att.hello)
    assert exc.value.code == "KIT-RT-001"
    missing = RP.attach_pool_router("no_such_router_module_for_pool")
    assert missing.refusal == "KIT-RT-016"


def test_the_routers_process_runs_each_pair_of_operations_for_its_own_capability(tmp_path, monkeypatch):
    (tmp_path / "pair_router_for_ops.py").write_text("def hello():\n    return 'h'\ndef plan(r):\n    return 'p:' + r\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert C.launch("pair_router_for_ops", "hello", None, 30) == "h" and C.launch("pair_router_for_ops", "plan", "x", 30) == "p:x"
    for op in ("pool_hello", "pool_plan"):
        with pytest.raises(C.RouterFailure) as exc:
            C.launch("pair_router_for_ops", op, "{}", 30)
        assert exc.value.code == "KIT-RT-015" and "pool_hello() and pool_plan" in exc.value.detail
    with pytest.raises(C.RouterFailure) as exc:
        C.launch("pair_router_for_ops", "anything_else", "{}", 30)
    assert exc.value.code == "KIT-RT-016"
    assert set(C.OPERATIONS) == {"hello", "plan", "pool_hello", "pool_plan"}


def test_ask_never_raises_for_anything_an_in_process_router_does():
    hello = lambda: json.dumps(HELLO)  # noqa: E731
    for plan_fn, code in ((lambda r: 1 / 0, "KIT-RT-016"), (lambda r: 7, "KIT-RT-016"), (lambda r: "not json", "KIT-RT-016"),
                          (lambda r: (_ for _ in ()).throw(SystemExit(1)), "KIT-RT-016")):
        att = RP.attach_pool_router_in_process(hello, plan_fn)
        assert att.attached and att.in_process
        assert RP.ask_pool_router(_req(), att).refusal == code
    assert RP.attach_pool_router_in_process(lambda: 1 / 0, lambda r: "{}").refusal == "KIT-RT-016"
    assert RP.attach_pool_router_in_process(lambda: json.dumps(dict(HELLO, port_version="2.0")), lambda r: "{}").refusal == "KIT-RT-015"
    assert RP.ask_pool_router(_req(), RP.attach_pool_router_in_process(hello, lambda r: "{}"), timeout_s=0).refusal == "KIT-RT-016"
