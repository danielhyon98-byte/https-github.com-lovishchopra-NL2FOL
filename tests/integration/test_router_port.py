"""The flash-router port ``epinoic.integration.router-port.v1``: round trips, every out-of-contract plan refused with a
named code, a below-floor plan refused (the floor runs), the router absent or failing (the floor runs), and the floor's
own rules (risk signals only escalate; a combined answer's floor is N_FOLD)."""
from __future__ import annotations

import copy
import json

import pytest
from hypothesis import given, settings as hsettings, strategies as st

from epinoic_logic.integration import router_port as R
from epinoic_logic.integration.canonical import canonical_json
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.protocol import dump
from tests.integration.helpers import (
    NFOLD_CONTEXT, ROUTER_IDENTITY, combined_request, output_features, plan_for, router_hello, routing_request, write_router_module,
)

HELLO = R.check_hello(router_hello())


def _code(fn) -> str:
    with pytest.raises(IntegrationError) as exc:
        fn()
    return exc.value.code


# ----------------------------------------------------------------------------------------------- round trips


def test_request_round_trip_is_exact_and_its_digest_is_stable():
    raw = routing_request([output_features("m-1"), output_features("m-2", agent_id="history")], topology={"kind": "duplicate", "sources": [], "synthesis": None})
    req = R.check_request(raw)
    assert dump(req) == raw
    assert R.check_request(canonical_json(raw)) == req
    assert R.request_digest(req) == R.request_digest(raw)


def test_hello_round_trip():
    assert dump(HELLO) == router_hello()
    assert R.check_hello(json.dumps(router_hello())) == HELLO


def test_plan_round_trip_for_an_in_contract_plan_at_the_floor():
    req = R.check_request(routing_request())
    raw = plan_for(routing_request(), [{"transfer_key": "m-1"}])
    plan = R.check_plan(raw, req, hello=HELLO)
    assert dump(plan) == raw
    assert R.check_plan(canonical_json(raw), req, hello=HELLO) == plan


def test_combined_plan_round_trip_with_n_fold():
    raw_req = combined_request()
    req = R.check_request(raw_req)
    raw = plan_for(raw_req, [{"transfer_key": "m-h"}, {"transfer_key": "m-e"},
                             {"transfer_key": "m-s", "method": "N_FOLD", "sources": ["m-h", "m-e"], "context": NFOLD_CONTEXT, "reasons": ["topology_combined"], "features_used": ["topology"]}])
    plan = R.check_plan(raw, req, hello=HELLO)
    assert [t.method for t in plan.transfers] == ["IN_DEPTH", "IN_DEPTH", "N_FOLD"]


# ----------------------------------------------------------------------------------------------- requests and hellos out of contract


@pytest.mark.parametrize("mutate,code", [
    (lambda r: r.update(extra=1), "KIT-RT-014"),
    (lambda r: r["outputs"][0].update(text="the answer itself"), "KIT-RT-011"),
    (lambda r: r["outputs"][0]["receipt"]["error_codes"].append("OVS-FID-003"), "KIT-RT-011"),
    (lambda r: r.update(auditor={"state": "AUDIT_FAILED"}), "KIT-RT-011"),
    (lambda r: r["outputs"][0]["engine_statuses"].update(VERIFIED=1), "KIT-RT-014"),
    (lambda r: r["outputs"].append(output_features("m-1")), "KIT-RT-014"),
    (lambda r: r.update(topology={"kind": "combined", "sources": ["m-1"], "synthesis": None}), "KIT-RT-014"),
    (lambda r: r["limits"].update(max_instances=65), "KIT-RT-014"),
    (lambda r: r["outputs"][0]["size"].update(chars=1.5), "KIT-RT-014"),
    (lambda r: r.update(port_version="2.0"), "KIT-RT-014"),
])
def test_requests_out_of_contract_are_refused_with_a_named_code(mutate, code):
    raw = routing_request()
    mutate(raw)
    assert _code(lambda: R.check_request(raw)) == code


@pytest.mark.parametrize("changes", [{"tier": "standard"}, {"deterministic": False}, {"methods": ["IN_DEPTH", "EXPENSIVE"]},
                                     {"port_version": "2.0"}, {"model": "any"}, {"router": {**ROUTER_IDENTITY, "name": "Has Spaces"}}])
def test_hellos_out_of_contract_are_refused_with_kit_rt_015(changes):
    assert _code(lambda: R.check_hello(router_hello(**changes))) == "KIT-RT-015"


# ----------------------------------------------------------------------------------------------- plans out of contract


def _plan_code(raw_req, raw_plan, hello=HELLO):
    return _code(lambda: R.check_plan(raw_plan, R.check_request(raw_req), hello=hello))


def _base():
    raw_req = routing_request([output_features("m-1"), output_features("m-2", errors=("INT-SUBJ-001",))],
                              topology={"kind": "duplicate", "sources": [], "synthesis": None})
    plan = plan_for(raw_req, [{"transfer_key": "m-1"}, {"transfer_key": "m-2", "method": "DUPLICATE", "reviews": 2, "reasons": ["risk_error_findings"]}])
    return raw_req, plan


def test_the_base_plan_is_in_contract():
    raw_req, plan = _base()
    assert R.check_plan(plan, R.check_request(raw_req), hello=HELLO).origin == "router"


def _edit(path_value_pairs):
    def f(p):
        for path, value in path_value_pairs:
            node = p
            for k in path[:-1]:
                node = node[k]
            if value is _DELETE:
                del node[path[-1]]
            else:
                node[path[-1]] = value
    return f


_DELETE = object()


@pytest.mark.parametrize("edit,code", [
    (lambda p: "not json {", "KIT-RT-001"),
    (lambda p: p.update(extra=True), "KIT-RT-001"),
    (_edit([(("schema",), "epinoic.integration.routing-plan.v2")]), "KIT-RT-001"),
    (_edit([(("transfers", 0, "estimated_cost"), _DELETE), (("totals",), {"instances": 3, "estimated_cost": {"tokens": 60000, "seconds": 45}})]), "KIT-RT-013"),
    (_edit([(("request_sha256",), "0" * 64)]), "KIT-RT-002"),
    (_edit([(("ids", "request_id"), "a_other")]), "KIT-RT-002"),
    (_edit([(("router", "version"), "9.9")]), "KIT-RT-003"),
    (_edit([(("origin",), "floor")]), "KIT-RT-003"),
    (_edit([(("transfers", 0, "transfer_key"), "m-9")]), "KIT-RT-004"),
    (lambda p: p["transfers"].pop(0) and p["totals"].update(instances=2, estimated_cost={"tokens": 60000, "seconds": 45}), "KIT-RT-005"),
    (lambda p: p["transfers"].append(copy.deepcopy(p["transfers"][1])), "KIT-RT-006"),
    (_edit([(("transfers", 0, "reviews"), 2), (("transfers", 0, "instances"), 2), (("totals", "instances"), 4)]), "KIT-RT-007"),
    (_edit([(("transfers", 0, "method"), "SPLIT")]), "KIT-RT-007"),
    (_edit([(("transfers", 1, "reviews"), 1), (("transfers", 1, "instances"), 1), (("totals", "instances"), 2)]), "KIT-RT-007"),
    (_edit([(("transfers", 1, "instances"), 3), (("totals", "instances"), 4)]), "KIT-RT-007"),
    (_edit([(("transfers", 0, "method"), "N_FOLD"), (("transfers", 0, "sources"), ["m-2"]), (("transfers", 0, "context"), NFOLD_CONTEXT)]), "KIT-RT-007"),
    (_edit([(("transfers", 0, "sources"), ["m-2"])]), "KIT-RT-007"),
    (_edit([(("transfers", 0, "method"), "TRIPLE")]), "KIT-RT-007"),
    (_edit([(("transfers", 1, "reviews"), 4), (("transfers", 1, "parts"), 3), (("transfers", 1, "instances"), 12), (("totals", "instances"), 13)]), "KIT-RT-008"),
    (_edit([(("transfers", 0, "tier"), "strongest")]), "KIT-RT-009"),
    (_edit([(("transfers", 0, "model"), "any-model")]), "KIT-RT-009"),
    (_edit([(("transfers", 0, "profile"), "deluxe")]), "KIT-RT-010"),
    (_edit([(("transfers", 0, "reasons"), ["OVS-FID-003 seen in the audit"])]), "KIT-RT-011"),
    (_edit([(("transfers", 0, "auditor"), {"findings": []})]), "KIT-RT-011"),
    (_edit([(("transfers", 0, "reasons"), ["because the router said so"])]), "KIT-RT-012"),
    (_edit([(("transfers", 0, "reasons"), ["cost_cheapest", "cost_cheapest"])]), "KIT-RT-012"),
    (_edit([(("transfers", 0, "features_used"), ["gold_label"])]), "KIT-RT-012"),
    (_edit([(("transfers", 0, "estimated_cost"), {"tokens": -1, "seconds": 1})]), "KIT-RT-013"),
    (_edit([(("totals", "estimated_cost"), {"tokens": 1, "seconds": 1})]), "KIT-RT-013"),
    (_edit([(("totals", "instances"), 9)]), "KIT-RT-013"),
])
def test_every_out_of_contract_plan_is_refused_with_its_named_code(edit, code):
    raw_req, plan = _base()
    out = edit(plan)
    if isinstance(out, str):
        plan = out
    assert _plan_code(raw_req, plan) == code


def test_a_method_the_hello_does_not_declare_is_refused():
    raw_req, plan = _base()
    hello = R.check_hello(router_hello(methods=["IN_DEPTH", "DUPLICATE"]))
    plan["transfers"][0].update(method="SPLIT", parts=2, instances=2)
    plan["totals"]["instances"] = 4
    assert _plan_code(raw_req, plan, hello) == "KIT-RT-007"


def test_a_profile_the_overseer_does_not_offer_is_refused():
    raw_req = routing_request(profiles=("standard",))
    assert _plan_code(raw_req, plan_for(raw_req, [{"transfer_key": "m-1", "profile": "fast"}])) == "KIT-RT-010"


# ----------------------------------------------------------------------------------------------- below the floor


@pytest.mark.parametrize("risk", [dict(errors=("INT-SUBJ-001",)), dict(status="REJECTED"), dict(repeated=1),
                                  dict(statuses={"COUNTEREXAMPLE": 1}), dict(stem=True, branch="sciences", statuses={"NOT_ATTEMPTED": 1}),
                                  dict(stem=True, branch="mathematics", warnings=("INT-SUBJ-002",))])
def test_a_single_review_of_a_risky_transfer_is_below_the_floor(risk):
    raw_req = routing_request([output_features("m-1", **risk)])
    for entry in ({"transfer_key": "m-1"}, {"transfer_key": "m-1", "method": "SPLIT", "parts": 4}):
        assert _plan_code(raw_req, plan_for(raw_req, [entry])) == "KIT-RT-020"
    ok = plan_for(raw_req, [{"transfer_key": "m-1", "method": "DUPLICATE", "reviews": 2, "reasons": ["risk_error_findings"]}])
    assert R.check_plan(ok, R.check_request(raw_req), hello=HELLO).transfers[0].reviews == 2


def test_a_combined_answer_below_its_n_fold_floor_is_refused():
    raw_req = combined_request()
    # the combinator's output reviewed once, without the per-source reviews being folded in: below the floor
    plan = plan_for(raw_req, [{"transfer_key": "m-h"}, {"transfer_key": "m-e"},
                              {"transfer_key": "m-s", "method": "N_FOLD", "sources": ["m-h", "m-e"], "context": NFOLD_CONTEXT}])
    assert R.check_plan(plan, R.check_request(raw_req), hello=HELLO)  # at the floor: adopted
    risky = combined_request()
    risky["outputs"][2]["receipt"]["error_codes"] = ["INT-LEDGER-005"]
    plan = plan_for(risky, [{"transfer_key": "m-h"}, {"transfer_key": "m-e"},
                            {"transfer_key": "m-s", "method": "N_FOLD", "sources": ["m-h", "m-e"], "context": NFOLD_CONTEXT}])
    assert _plan_code(risky, plan) == "KIT-RT-020"
    # the combinator's output reviewed as an ordinary transfer is out of contract (the floor's method is N_FOLD)
    plan = plan_for(raw_req, [{"transfer_key": "m-h"}, {"transfer_key": "m-e"}, {"transfer_key": "m-s", "method": "DUPLICATE", "reviews": 2}])
    assert _plan_code(raw_req, plan) == "KIT-RT-007"


def test_above_floor_plans_are_adopted():
    raw_req = routing_request([output_features("m-1", chars=40000)])
    for entry in ({"transfer_key": "m-1", "method": "SPLIT", "parts": 4, "reasons": ["volume_split"]},
                  {"transfer_key": "m-1", "method": "DUPLICATE", "reviews": 3, "profile": "standard"}):
        adm = R.admit_plan(R.check_request(raw_req), plan_for(raw_req, [entry]), hello=HELLO)
        assert (adm.origin, adm.refusal) == ("router", None)


# ----------------------------------------------------------------------------------------------- admission, absence, failure


def test_without_a_router_the_floor_plan_runs():
    req = R.check_request(routing_request([output_features("m-1", errors=("INT-REQ-003",))]))
    adm = R.admit_plan(req, None, hello=None)
    assert (adm.origin, adm.refusal, adm.router) == ("floor", None, None)
    assert adm.effective == adm.floor == R.floor_plan(req)
    assert adm.effective.transfers[0].method == "DUPLICATE" and adm.effective.transfers[0].reviews == 2
    assert R.route(req, None).effective == adm.effective
    assert R.route(req, R.attach_router("none")).origin == "floor"


def test_a_refused_plan_runs_the_floor_and_names_the_refusal():
    raw_req = routing_request([output_features("m-1", errors=("INT-REQ-003",))])
    adm = R.admit_plan(R.check_request(raw_req), plan_for(raw_req, [{"transfer_key": "m-1"}]), hello=HELLO)
    assert (adm.origin, adm.refusal) == ("floor", "KIT-RT-020")
    assert adm.effective.transfers[0].reviews == 2 and adm.router == HELLO.router
    rec = adm.record()
    assert rec["origin"] == "floor" and rec["refusal"] == "KIT-RT-020" and "transfers" not in rec


def test_an_attached_router_module_is_called_with_json_and_its_plan_admitted(tmp_path, monkeypatch):
    name = write_router_module(tmp_path, monkeypatch, "flash_router_for_test")
    att = R.attach_router(name)
    assert att.attached and att.hello.router.name == "test-flash-router"
    req = R.check_request(routing_request([output_features("m-1"), output_features("m-2", errors=("INT-SUBJ-001",))],
                                          topology={"kind": "duplicate", "sources": [], "synthesis": None}))
    adm = R.route(req, att)
    assert (adm.origin, adm.refusal) == ("router", None)
    assert [t.reviews for t in adm.effective.transfers] == [1, 2]


@pytest.mark.parametrize("body,refusal", [
    ("    raise RuntimeError('router bug')\n", "KIT-RT-016"),
    ("    return None\n", "KIT-RT-016"),
    ("    return 'not json'\n", "KIT-RT-001"),
    ("    return json.dumps({'schema': 'epinoic.integration.routing-plan.v1'})\n", "KIT-RT-001"),
])
def test_a_failing_or_misbehaving_router_never_fails_the_review_the_floor_runs(tmp_path, monkeypatch, body, refusal):
    name = write_router_module(tmp_path, monkeypatch, f"bad_router_{abs(hash(body)) % 10**8}", plan_body=body)
    req = R.check_request(routing_request())
    adm = R.route(req, R.attach_router(name))
    assert (adm.origin, adm.refusal) == ("floor", refusal)
    assert adm.effective == R.floor_plan(req)


def test_an_absent_router_module_is_reported_not_required():
    att = R.attach_router("epinoic_flash_router_that_is_not_installed.port")
    assert not att.attached and att.refusal is None and "not importable" in att.detail
    assert R.attach_router("not a module path!").refusal == "KIT-RT-015"


# ----------------------------------------------------------------------------------------------- the floor's rules


def test_the_floor_without_signals_is_one_in_depth_review_on_the_standard_profile():
    plan = R.floor_plan(R.check_request(routing_request()))
    t = plan.transfers[0]
    assert (t.method, t.reviews, t.instances, t.profile, t.tier) == ("IN_DEPTH", 1, 1, "standard", "cheapest")
    assert plan.origin == "floor" and plan.router == R.FLOOR_IDENTITY and t.reasons == ["baseline_single_review", "profile_standard"]
    assert plan.router.rules_sha256 == R.FLOOR_RULES_SHA256


def test_the_floor_of_a_combined_answer_is_n_fold_over_its_sources():
    plan = R.floor_plan(R.check_request(combined_request()))
    by = {t.transfer_key: t for t in plan.transfers}
    assert by["m-s"].method == "N_FOLD" and by["m-s"].sources == ["m-h", "m-e"] and by["m-s"].context.scope == "request"
    assert by["m-s"].context.max_bytes == R.CONTEXT_MAX_BYTES and by["m-s"].context.discard == "after_request"
    assert by["m-h"].method == "IN_DEPTH" and "topology_source" in by["m-h"].reasons


def test_the_floor_is_deterministic():
    raw = combined_request()
    assert R.floor_plan(R.check_request(raw)) == R.floor_plan(R.check_request(copy.deepcopy(raw)))
    assert R.floor_plan(R.check_request(raw)).plan_id == R.floor_plan(R.check_request(raw)).plan_id


_signal = st.fixed_dictionaries({
    "errors": st.sampled_from([(), ("INT-SUBJ-001",)]), "status": st.sampled_from(["ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED"]),
    "repeated": st.integers(min_value=0, max_value=2), "stem": st.booleans(),
    "statuses": st.dictionaries(st.sampled_from(["ENTAILED", "COUNTEREXAMPLE", "UNKNOWN", "NOT_ATTEMPTED", "NOT_ELIGIBLE"]), st.integers(0, 3), max_size=3),
})


@hsettings(max_examples=150, deadline=None)
@given(_signal, _signal)
def test_risk_signals_only_escalate(a, b):
    """Adding the signals of ``b`` to ``a`` never lowers the floor's reviews of a transfer."""
    def out(sig):
        return output_features("m-1", branch="sciences" if sig["stem"] else "history", **sig)
    merged = {"errors": tuple(set(a["errors"]) | set(b["errors"])), "status": "REJECTED" if "REJECTED" in (a["status"], b["status"]) else a["status"],
              "repeated": max(a["repeated"], b["repeated"]), "stem": a["stem"] or b["stem"],
              "statuses": {k: max(a["statuses"].get(k, 0), b["statuses"].get(k, 0)) for k in set(a["statuses"]) | set(b["statuses"])}}
    base = R.floor_plan(R.check_request(routing_request([out(a)]))).transfers[0].reviews
    more = R.floor_plan(R.check_request(routing_request([out(merged)]))).transfers[0].reviews
    assert more >= base
    assert base in (1, 2) and more in (1, 2)
