"""A caller names the engine policy over HTTP (end-to-end simulation of 16 October 2026, bug 8).

``POST /v1/verify`` always decided under the default limits, so it could not carry the engine policy the channel used:
8 of 301 genuine-pass engine problems decided differently over HTTP than in the pipeline (seven STEM checks the channel
ran under ``nonlinear`` came back UNSUPPORTED E201, and one cross-agent joint check run under ``joint`` came back
INVALID_FORMALIZATION E300-E302). The request now names an allowlisted policy, never limits of its own.

Pinned here, over HTTP (the service app through its ASGI stack, and once over a real local socket):

* each of the eight recorded problems, posted with the policy its pipeline limits name, decides exactly as the pipeline
  did (status, relied-on premises, core, model, diagnostic codes), never lists fewer unresolved dependencies, and binds
  exactly what the same payload decided in process under the same policy binds; without a policy it decides as before;
* the policy is bound into the result's identity: the limits record and its digest, the configuration digest (the
  nonlinear ``rlimit`` cap, applied by the server), one binding digest per policy, ``named_policy_of`` naming the policy
  back, and a release check that treats the result as current only for a receiver naming the same policy;
* only names are accepted: an unknown name, a case or whitespace variant, null, a number, a list or an object of limits
  is 400 E100 before anything runs, and the envelope has no place for limits;
* authentication, the rate limit, the body-size limit, the self-certification refusal and the server-controlled memory
  budget hold under every policy.
"""
from __future__ import annotations

import copy
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import epinoic_logic.service.app as app_module
from epinoic_logic.engine.policies import JOINT_LIMITS, NAMED_POLICIES, NONLINEAR_LIMITS, NONLINEAR_RLIMIT, named_policy, named_policy_of
from epinoic_logic.engine.provenance import limits_digest, verify_signature
from epinoic_logic.engine.results import SolverConfig, VerificationResult
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Limits, Problem
from epinoic_logic.service import create_app

from .conftest import AUTH, KEY, KEY_ID, I, V, cmp, make_client, make_settings, nonlinear_problem, transitivity_problem
from .test_app import assert_clean_error

DATA = Path(__file__).resolve().parent / "data" / "e2e_policy_problems.json"
RECORDED: list[dict[str, Any]] = json.loads(DATA.read_text(encoding="utf-8"))["problems"]


def sanitize(obj: Any) -> Any:
    """What a backend does before posting a problem the pipeline built: a grounding's ``verified: true`` (set by a check
    in the pipeline's process) is reset to null, since the service refuses a client-asserted verification (E505)."""
    if isinstance(obj, dict):
        return {k: (None if k == "verified" and v is True else sanitize(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


def client_config(config: dict[str, Any]) -> dict[str, Any]:
    """What a backend sends of the configuration the pipeline ran: the server-controlled options
    (``SERVER_CONTROLLED_CONFIG_KEYS``: the process-wide memory budget, and model completion, which the engine always
    applies) are the server's, and a request that names one is refused (400 E100), so they are left out; the server's
    values are the pipeline's (``model_completion`` true)."""
    return {k: v for k, v in config.items() if k not in app_module.SERVER_CONTROLLED_CONFIG_KEYS}


def decision(result: dict[str, Any]) -> dict[str, Any]:
    """The fields of a result that carry its decision (ids, timestamps, timings, dependency lists and signature aside)."""
    core = result.get("unsat_core") or {}
    return {"status": result["status"], "query": result["query"], "premises_relied_on": sorted(result.get("premises_relied_on") or []),
            "unsat_core": sorted(core.get("premise_ids") or []), "negated_conclusion_in_core": core.get("includes_negated_conclusion"),
            "counterexample": sorted((a["symbol"], a["value"]) for a in ((result.get("counterexample") or {}).get("assignments") or [])),
            "witness_model": sorted((a["symbol"], a["value"]) for a in (result.get("witness_model") or [])),
            "diagnostic_codes": sorted(d["code"] for d in result.get("diagnostics") or []), "reason_unknown": result.get("reason_unknown")}


def post(client, body: dict[str, Any], headers: dict[str, str] | None = None):
    return client.post("/v1/verify", json=body, headers=AUTH if headers is None else headers)


def square_problem() -> dict[str, Any]:
    """x*x = 4 over Int: nonlinear, so UNSUPPORTED (E201) under linear and joint, SATISFIABLE under nonlinear."""
    return {"problem_id": "sq", "request_id": "req1", "claim_id": "c-sq", "query": "satisfiability", "symbols": [{"name": "x", "sort": "Int"}],
            "premises": [{"id": "P", "expr": cmp("eq", {"op": "mul", "args": [V("x"), V("x")]}, I(4))}]}


def wide_problem(premises: int = 200) -> dict[str, Any]:
    """A consistency problem with more premises than the default limits allow (128) and fewer than the joint bounds."""
    return {"problem_id": "wide", "request_id": "req1", "claim_id": "c-wide", "query": "consistency", "symbols": [{"name": "x", "sort": "Int"}],
            "premises": [{"id": f"P{i}", "expr": cmp("ge", V("x"), I(i))} for i in range(premises)]}


# =========================================================================== the eight recorded problems


@pytest.mark.parametrize("entry", RECORDED, ids=[e["problem_id"] for e in RECORDED])
def test_each_recorded_problem_decides_over_http_as_in_the_pipeline_under_its_named_policy(client, entry):
    limits = Limits(**entry["pipeline_limits"])
    name = named_policy_of(limits)
    assert name in ("nonlinear", "joint"), "the pipeline's limits are a named policy, so a backend can name it"
    lim, cfg = named_policy(name, SolverConfig(**entry["config"]))
    assert lim == limits and cfg == SolverConfig(**entry["config"]), "the named policy is exactly what the pipeline ran"
    pipeline = json.loads(verify(Problem.model_validate(entry["problem"]), cfg, lim).model_dump_json())  # the pipeline's own path
    assert pipeline["status"] == entry["pipeline_status"]
    sent = sanitize(entry["problem"])

    refused = post(client, {"problem": sent, "config": entry["config"], "policy": name})
    assert refused.status_code == 400 and refused.json()["code"] == "E100", "a server-controlled option is never the client's to send"
    config = client_config(entry["config"])
    assert SolverConfig(**config) == SolverConfig(**entry["config"]), "the server's values of those options are the pipeline's"

    before = post(client, {"problem": sent, "config": config})
    assert before.status_code == 200 and before.json()["status"] == entry["http_status"], "without a policy nothing changed"

    r = post(client, {"problem": sent, "config": config, "policy": name})
    assert r.status_code == 200
    body = r.json()
    assert decision(body) == decision(pipeline), "the same problem gets the same decision in process and over HTTP"
    for field in ("ungrounded_dependencies", "unverified_dependencies"):
        assert set(pipeline[field]) <= set(body[field]), "a caller cannot certify a grounding, so HTTP never lists fewer dependencies"
    result = VerificationResult.model_validate(body)
    assert verify_signature(result, KEY) and result.signature_key_id == KEY_ID
    assert result.limits == limits and result.binding.limits_digest == limits_digest(limits) and named_policy_of(result.limits) == name
    local = verify(sent, cfg, lim)  # the same payload decided in this process under the same policy
    assert result.binding.model_dump() == local.binding.model_dump(), "the result binds the policy as the in-process run does"
    assert result.solver_config == cfg


def test_the_eight_recorded_problems_cover_both_policies_the_pipeline_used():
    assert sorted(named_policy_of(Limits(**e["pipeline_limits"])) for e in RECORDED) == ["joint"] + ["nonlinear"] * 7


# =========================================================================== the policy in the result's identity


def test_the_named_policy_is_bound_into_the_result_identity(client):
    bodies = {name: post(client, {"problem": transitivity_problem(), "policy": name}).json() for name in sorted(NAMED_POLICIES)}
    assert {b["status"] for b in bodies.values()} == {"ENTAILED"}
    assert len({b["binding"]["binding_digest"] for b in bodies.values()}) == 3, "each policy is a different identity"
    assert "limits" not in bodies["linear"] and "limits_digest" not in bodies["linear"]["binding"], "linear is the default record"
    default = post(client, {"problem": transitivity_problem()}).json()
    assert default["binding"]["binding_digest"] == bodies["linear"]["binding"]["binding_digest"]
    for name, body in bodies.items():
        result = VerificationResult.model_validate(body)
        assert named_policy_of(result.limits) == name and verify_signature(result, KEY)
        assert result.binding.limits_digest == limits_digest(NAMED_POLICIES[name])
    assert bodies["nonlinear"]["solver_config"]["rlimit"] == NONLINEAR_RLIMIT and bodies["joint"]["solver_config"]["rlimit"] is None


@pytest.mark.parametrize("decided_under", sorted(NAMED_POLICIES))
def test_a_result_is_current_only_for_a_receiver_that_names_its_policy(client, decided_under):
    body = post(client, {"problem": transitivity_problem(), "policy": decided_under}).json()
    for required in sorted(NAMED_POLICIES):
        r = client.post("/v1/results/release-check", json={"result": body, "problem": transitivity_problem(), "policy": required}, headers=AUTH)
        assert r.status_code == 200
        stale = [why for why in r.json()["reasons"] if why.startswith("stale:")]
        if required == decided_under:
            assert stale == [], stale
        else:
            assert stale and "required policy" in stale[0], (decided_under, required, stale)
        assert not r.json()["eligible"], "its premises are ungrounded, so it is never release-eligible"


def test_the_nonlinear_rlimit_cap_is_applied_by_the_server(client):
    cases = {None: NONLINEAR_RLIMIT, 10 ** 9: NONLINEAR_RLIMIT, NONLINEAR_RLIMIT: NONLINEAR_RLIMIT, 500_000: 500_000}
    for given, applied in cases.items():
        config = {} if given is None else {"rlimit": given}
        body = post(client, {"problem": square_problem(), "config": config, "policy": "nonlinear"}).json()
        assert body["status"] == "SATISFIABLE" and body["solver_config"]["rlimit"] == applied, (given, body["solver_config"])
    linear = post(client, {"problem": transitivity_problem(), "config": {"rlimit": 10 ** 9}, "policy": "linear"}).json()
    assert linear["solver_config"]["rlimit"] == 10 ** 9, "linear is the caller's configuration unchanged"


def test_each_policy_opens_only_what_it_names(client):
    by_policy = {name: post(client, {"problem": square_problem(), "policy": name}).json() for name in sorted(NAMED_POLICIES)}
    assert by_policy["nonlinear"]["status"] == "SATISFIABLE"
    for name in ("linear", "joint"):
        assert by_policy[name]["status"] == "UNSUPPORTED" and "E201" in [d["code"] for d in by_policy[name]["diagnostics"]], name
    wide = {name: post(client, {"problem": wide_problem(), "policy": name}).json() for name in sorted(NAMED_POLICIES)}
    assert wide["joint"]["status"] == "CONSISTENT" and wide["joint"]["limits"] == JOINT_LIMITS.model_dump(mode="json")
    for name in ("linear", "nonlinear"):
        assert wide[name]["status"] == "INVALID_FORMALIZATION" and "E301" in [d["code"] for d in wide[name]["diagnostics"]], name


def test_the_degree_bound_still_holds_under_the_nonlinear_policy(client):
    term: Any = V("x")
    for _ in range(30):
        term = {"op": "mul", "args": [term, V("x")]}
    problem = {**square_problem(), "premises": [{"id": "P", "expr": cmp("eq", term, I(0))}]}
    body = post(client, {"problem": problem, "policy": "nonlinear"}).json()
    assert body["status"] == "UNSUPPORTED" and "E201" in [d["code"] for d in body["diagnostics"]]


# =========================================================================== only names, never limits


class _Recorder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return verify(*args, **kwargs)


@pytest.mark.parametrize("policy", ["Nonlinear", "NONLINEAR", " nonlinear", "nonlinear ", "nonlinear\n", "non-linear", "non_linear", "nonlinear\u200b",
                                    "jo\u0131nt", "unbounded", "default", "pack", "", None, 1, True, ["nonlinear"],
                                    {"allow_nonlinear": True}, {"name": "nonlinear"}, {"max_nodes": 200000}],
                         ids=lambda p: repr(p)[:40])
def test_an_unknown_policy_is_refused_before_anything_runs(monkeypatch, policy):
    recorder = _Recorder()
    monkeypatch.setattr(app_module, "verify", recorder)
    client = make_client()
    r = post(client, {"problem": square_problem(), "policy": policy})
    body = assert_clean_error(r, 400, "E100")
    assert body["message"] == "'policy' must be one of: joint, linear, nonlinear"
    assert recorder.calls == 0, "a refused policy never runs the solver under any policy"


def test_the_envelope_has_no_place_for_limits(client):
    for key in ("limits", "pipeline_limits", "allow_nonlinear"):
        assert_clean_error(post(client, {"problem": square_problem(), "policy": "linear", key: {"allow_nonlinear": True}}), 400, "E100")
    assert_clean_error(post(client, {"problem": square_problem(), "config": {"allow_nonlinear": True}}), 400, "E100")


# =========================================================================== the service's controls hold under every policy


@pytest.mark.parametrize("policy", sorted(NAMED_POLICIES))
def test_authentication_and_self_certification_hold_under_every_policy(client, policy):
    body = {"problem": square_problem(), "policy": policy}
    assert_clean_error(post(client, body, headers={}), 401, "E502")
    assert_clean_error(post(client, body, headers={"Authorization": "Bearer wrong-token-0123456789abcdef"}), 401, "E502")
    assert_clean_error(post(client, {**body, "status": "SATISFIABLE"}), 400, "E505")
    certified = copy.deepcopy(square_problem())
    certified["premises"][0]["grounding"] = {"kind": "task_setting", "verified": True}
    assert_clean_error(post(client, {**body, "problem": certified}), 400, "E505")
    assert_clean_error(post(client, {**body, "config": {"memory_max_mb": 4096}}), 400, "E100")


@pytest.mark.parametrize("policy", sorted(NAMED_POLICIES))
def test_the_body_size_and_rate_limits_hold_under_every_policy(policy):
    small = make_client(make_settings(max_body_bytes=4096))
    big = {"problem": wide_problem(200), "policy": policy}
    assert len(json.dumps(big)) > 4096
    assert_clean_error(post(small, big), 413, "E306")
    now = [1000.0]
    limited = make_client(make_settings(rate_per_minute=1), clock=lambda: now[0])
    assert post(limited, {"problem": transitivity_problem(), "policy": policy}).status_code == 200
    assert_clean_error(post(limited, {"problem": transitivity_problem(), "policy": policy}), 429, "E503")


def test_the_unsupported_default_answer_is_unchanged_without_a_policy(client):
    body = post(client, {"problem": nonlinear_problem()}).json()
    assert body["status"] == "UNSUPPORTED" and "limits" not in body and body["solver_config"]["rlimit"] is None


# =========================================================================== over a real socket


@pytest.fixture
def live_base_url():
    uvicorn = pytest.importorskip("uvicorn")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(create_app(make_settings()), log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        sock.close()
        pytest.skip("a local HTTP server could not be started here")
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()


def test_a_recorded_stem_problem_decides_as_in_the_pipeline_over_a_real_socket(live_base_url):
    httpx = pytest.importorskip("httpx")
    entry = next(e for e in RECORDED if e["problem_id"].startswith("stem-alg-"))
    lim, cfg = named_policy("nonlinear", SolverConfig(**entry["config"]))
    pipeline = json.loads(verify(Problem.model_validate(entry["problem"]), cfg, lim).model_dump_json())
    with httpx.Client(base_url=live_base_url, timeout=60.0, trust_env=False) as http:
        sent = {"problem": sanitize(entry["problem"]), "config": client_config(entry["config"])}
        assert http.post("/v1/verify", json=sent, headers=AUTH).json()["status"] == "UNSUPPORTED"
        r = http.post("/v1/verify", json={**sent, "policy": "nonlinear"}, headers=AUTH)
        assert r.status_code == 200 and r.headers.get("x-request-id")
        assert decision(r.json()) == decision(pipeline) and r.json()["status"] == entry["pipeline_status"] == "ENTAILED"
        assert r.json()["limits"] == NONLINEAR_LIMITS.model_dump(mode="json")
        assert http.post("/v1/verify", json={**sent, "policy": "Nonlinear"}, headers=AUTH).status_code == 400
        assert http.post("/v1/verify", json={**sent, "policy": "nonlinear"}).status_code == 401
        sig = http.post("/v1/results/verify-signature", json={"result": r.json()}, headers=AUTH).json()
        assert sig == {"valid": True}
