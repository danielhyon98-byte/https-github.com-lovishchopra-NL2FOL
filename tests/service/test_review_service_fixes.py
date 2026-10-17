"""The engine findings of the external review of 2026-10-12, through the HTTP boundary.

* finding 3: ``config.produce_unsat_core`` changes neither dependencies, vacuity nor release eligibility over HTTP;
* finding 2: a model-chosen trusted grounding kind in a submitted problem is an unverified dependency in the signed
  result (a client cannot certify a grounding: nested ``verified: true`` is refused, E505);
* findings 5 and 8: ``POST /v1/results/release-check`` applies the engine's current-policy release check under the
  service key, so a genuine result of an earlier release stays inspectable (its signature verifies) but is never
  eligible, and a result decided under other validation limits is eligible only for a receiver that requires them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from epinoic_logic.engine.policies import NONLINEAR_LIMITS
from epinoic_logic.engine.provenance import binding_digest_of, sign_result, versions_digest
from epinoic_logic.engine.results import SolverConfig, VerificationResult
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem

from .conftest import AUTH, KEY, KEY_ID, I, V, cmp, make_client, make_settings
from .test_app import assert_clean_error

DATA = Path(__file__).resolve().parents[1] / "engine" / "data"


def chain(kind: str | None) -> dict[str, Any]:
    meta = {} if kind is None else {"grounding": {"kind": kind}}
    return {"problem_id": "p1", "request_id": "req1", "claim_id": "c1", "query": "entailment",
            "symbols": [{"name": "p", "sort": "Bool"}, {"name": "q", "sort": "Bool"}],
            "premises": [{"id": "P", "expr": V("p"), **meta}, {"id": "L", "expr": {"op": "implies", "left": V("p"), "right": V("q")}, **meta}],
            "conclusion": {"id": "C", "expr": V("q")}}


def tautology() -> dict[str, Any]:
    return {"problem_id": "p2", "request_id": "req1", "claim_id": "c2", "query": "entailment", "symbols": [{"name": "p", "sort": "Bool"}],
            "premises": [], "conclusion": {"id": "C", "expr": {"op": "or", "args": [V("p"), {"op": "not", "arg": V("p")}]}}}


def inconsistent() -> dict[str, Any]:
    return {"problem_id": "p3", "request_id": "req1", "claim_id": "c3", "query": "entailment", "symbols": [{"name": "x", "sort": "Int"}],
            "premises": [{"id": "A", "expr": cmp("gt", V("x"), I(3)), "grounding": {"kind": "rubric_rule"}},
                         {"id": "B", "expr": cmp("lt", V("x"), I(2)), "grounding": {"kind": "assumption"}}],
            "conclusion": {"id": "C", "expr": cmp("eq", V("x"), I(0))}}


def release(client, result: dict[str, Any], problem: dict[str, Any] | None = None, policy: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"result": result}
    if problem is not None:
        body["problem"] = problem
    if policy is not None:
        body["policy"] = policy
    r = client.post("/v1/results/release-check", json=body, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


PROBLEMS = {"assumption-chain": lambda: chain("assumption"), "arithmetic-chain": lambda: chain("arithmetic_fact"),
            "task-chain": lambda: chain("task_setting"), "rubric-chain": lambda: chain("rubric_rule"),
            "tautology": tautology, "inconsistent": inconsistent}


@pytest.mark.parametrize("name", sorted(PROBLEMS))
def test_core_output_changes_no_evidence_vacuity_or_release_eligibility_over_http(client, name: str):
    problem = PROBLEMS[name]()
    bodies = {}
    for core in (True, False):
        r = client.post("/v1/verify", json={"problem": problem, "config": {"produce_unsat_core": core}}, headers=AUTH)
        assert r.status_code == 200
        bodies[core] = r.json()
    on, off = bodies[True], bodies[False]
    for field in ("status", "premises_relied_on", "ungrounded_dependencies", "unverified_dependencies"):
        assert on[field] == off[field], field
    assert [d["code"] for d in on["diagnostics"]] == [d["code"] for d in off["diagnostics"]]
    assert off["unsat_core"] is None
    checks = {core: release(client, body, problem) for core, body in bodies.items()}
    assert checks[True]["eligible"] == checks[False]["eligible"] and checks[True]["reasons"] == checks[False]["reasons"]


def test_the_tautology_is_vacuous_over_http_with_core_output_off(client):
    off = client.post("/v1/verify", json={"problem": tautology(), "config": {"produce_unsat_core": False}}, headers=AUTH).json()
    assert off["status"] == "ENTAILED" and [d["code"] for d in off["diagnostics"]] == ["E108"]
    assert not release(client, off, tautology())["eligible"]


@pytest.mark.parametrize("kind", ["arithmetic_fact", "task_setting", "rubric_rule"])
def test_a_trusted_kind_is_an_unverified_dependency_over_http(client, kind: str):
    body = client.post("/v1/verify", json={"problem": chain(kind)}, headers=AUTH).json()
    assert body["status"] == "ENTAILED" and body["ungrounded_dependencies"] == [] and body["unverified_dependencies"] == ["P", "L"]
    check = release(client, body, chain(kind))
    assert not check["eligible"] and any("authority not validated" in why for why in check["reasons"])
    # a client cannot grant the authority itself
    certified = chain(kind)
    certified["premises"][0]["grounding"]["verified"] = True
    assert_clean_error(client.post("/v1/verify", json={"problem": certified}, headers=AUTH), 400, "E505")


def test_an_application_verified_result_is_release_eligible_over_http(client):
    """Negative control: a result whose premises a check in this process verified, signed with the service key."""
    data = chain("task_setting")
    for premise in data["premises"]:
        premise["grounding"]["verified"] = True
    problem = Problem.model_validate(data)
    r = verify(problem, SolverConfig(memory_max_mb=None), signing_key=KEY, key_id=KEY_ID)
    check = release(client, json.loads(r.model_dump_json()), data)
    assert check["eligible"] is True and check["reasons"] == []
    assert set(check["current"]) >= {"engine_version", "policy_version", "build_id", "schema_id", "policy_id"}


def test_another_build_or_an_earlier_release_is_never_eligible_over_http():
    entry = json.loads((DATA / "release_0_3_0_signed_results.json").read_text())["trusted_kind_chain"]
    client = make_client(make_settings(signing_key=b"upgrade-test-key-0123456789abcdef", signing_key_id="upgrade"))
    sig = client.post("/v1/results/verify-signature", json={"result": entry["result"]}, headers=AUTH).json()
    assert sig == {"valid": True}                                              # inspectable: a genuine record of 0.3.0
    check = release(client, entry["result"], entry["problem"])
    assert not check["eligible"] and any(why.startswith("stale:") for why in check["reasons"])
    assert not any(why.startswith("unauthenticated") for why in check["reasons"])


def test_unchanged_versions_with_another_build_identity_are_stale_over_http(client):
    data = chain("task_setting")
    for premise in data["premises"]:
        premise["grounding"]["verified"] = True
    r = verify(Problem.model_validate(data), SolverConfig(memory_max_mb=None), signing_key=KEY, key_id=KEY_ID)
    other = r.versions.model_copy(update={"build_id": "f" * 64})
    vd = versions_digest(other)
    forged = sign_result(r.model_copy(update={"versions": other, "binding": r.binding.model_copy(update={
        "versions_digest": vd, "binding_digest": binding_digest_of(r.binding.problem_digest, r.binding.config_digest, vd)})}), KEY, KEY_ID)
    check = release(client, json.loads(forged.model_dump_json()), data)
    assert not check["eligible"] and any("build_id" in why for why in check["reasons"])


def test_the_required_validation_policy_is_named_by_the_receiver(client):
    problem = Problem.model_validate({"problem_id": "p4", "request_id": "req1", "claim_id": "c4", "query": "satisfiability",
                                      "symbols": [{"name": "x", "sort": "Int"}],
                                      "premises": [{"id": "P", "expr": cmp("eq", {"op": "mul", "args": [V("x"), V("x")]}, I(4))}]})
    r = verify(problem, SolverConfig(memory_max_mb=None), NONLINEAR_LIMITS, signing_key=KEY, key_id=KEY_ID)
    raw = json.loads(r.model_dump_json())
    default = release(client, raw)
    assert not default["eligible"] and any("required policy" in why for why in default["reasons"])
    nonlinear = release(client, raw, policy="nonlinear")
    assert nonlinear["eligible"] is True, nonlinear
    assert not release(client, raw, policy="joint")["eligible"]


def test_the_release_check_envelope_is_strict(client):
    raw = json.loads(verify(Problem.model_validate(chain(None)), SolverConfig(memory_max_mb=None), signing_key=KEY, key_id=KEY_ID).model_dump_json())
    assert_clean_error(client.post("/v1/results/release-check", json={"result": raw, "policy": "permissive"}, headers=AUTH), 400, "E100")
    assert_clean_error(client.post("/v1/results/release-check", json={"result": raw, "extra": 1}, headers=AUTH), 400, "E100")
    assert_clean_error(client.post("/v1/results/release-check", json={"result": raw, "status": "ENTAILED"}, headers=AUTH), 400, "E505")
    assert client.post("/v1/results/release-check", json={"result": raw}).status_code == 401
    bad = client.post("/v1/results/release-check", json={"result": {"status": "ENTAILED"}}, headers=AUTH).json()
    assert bad["eligible"] is False and "schema" in bad["reasons"][0]
    tampered = {**raw, "ungrounded_dependencies": []}
    check = release(client, tampered)
    assert not check["eligible"] and any(why.startswith("unauthenticated") for why in check["reasons"])
    assert isinstance(VerificationResult.model_validate(raw), VerificationResult)
