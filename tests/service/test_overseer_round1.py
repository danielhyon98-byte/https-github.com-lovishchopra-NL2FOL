"""Service regressions from the overseer round-1 findings: nested self-certification, the
server-controlled memory budget, duplicate envelope keys and bounded pipeline failures."""
from __future__ import annotations

import json
import subprocess
import sys

from .conftest import AUTH, V, cmp, transitivity_problem
from .test_app import assert_clean_error


def quotation_problem(verified=True) -> dict:
    grounding = {"kind": "quotation", "source_refs": [{"document_id": "doc", "excerpt": "the court washed the blood from the verdict"}]}
    if verified is not None:
        grounding["verified"] = verified
    return {
        "problem_id": "p1", "request_id": "req1", "claim_id": "c1", "query": "entailment",
        "symbols": [{"name": "q", "sort": "Bool"}, {"name": "p", "sort": "Bool"}],
        "premises": [
            {"id": "A", "expr": V("q"), "grounding": grounding},
            {"id": "L", "expr": {"op": "implies", "left": V("q"), "right": V("p")}, "grounding": {"kind": "specialist_inference"}},
        ],
        "conclusion": {"id": "C", "expr": V("p")},
    }


def test_nested_verified_true_is_rejected_with_e505(client):
    r = client.post("/v1/verify", json={"problem": quotation_problem(True)}, headers=AUTH)
    body = assert_clean_error(r, 400, "E505")
    assert "premises[0].grounding.verified" in body["message"]
    symbol_level = transitivity_problem(symbols=[{"name": "x", "sort": "Int", "grounding": {"kind": "quotation", "verified": True}}, {"name": "y", "sort": "Int"}, {"name": "z", "sort": "Int"}])
    assert_clean_error(client.post("/v1/verify", json={"problem": symbol_level}, headers=AUTH), 400, "E505")


def test_unchecked_quotation_premise_is_ungrounded_in_the_signed_result(client):
    r = client.post("/v1/verify", json={"problem": quotation_problem(None)}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ENTAILED" and sorted(body["ungrounded_dependencies"]) == ["A", "L"] and body["signature"]
    weak = client.post("/v1/verify", json={"problem": quotation_problem(False)}, headers=AUTH).json()
    assert sorted(weak["ungrounded_dependencies"]) == ["A", "L"]


def test_client_memory_budget_is_refused(client):
    for value in (16, 128, 4096):
        r = client.post("/v1/verify", json={"problem": transitivity_problem(), "config": {"memory_max_mb": value}}, headers=AUTH)
        body = assert_clean_error(r, 400, "E100")
        assert "memory_max_mb" in body["message"] and "server-controlled" in body["message"]
    ok = client.post("/v1/verify", json={"problem": transitivity_problem(), "config": {"timeout_ms": 3000}}, headers=AUTH)
    assert ok.status_code == 200 and ok.json()["status"] == "ENTAILED"


_SUBPROCESS_CASE = r'''
from fastapi.testclient import TestClient
from epinoic_logic.service import ServiceSettings, create_app
TOKEN = "overseer-service-token-0123456789abcdef"
KEY = bytes.fromhex("ffeeddccbbaa99887766554433221100ffeeddccbbaa99887766554433221100")
AUTH = {"Authorization": f"Bearer {TOKEN}"}
c = TestClient(create_app(ServiceSettings(service_token=TOKEN, signing_key=KEY, signing_key_id="svc")), raise_server_exceptions=False)
P = {"problem_id": "p1", "request_id": "req1", "claim_id": "c1", "query": "entailment",
     "symbols": [{"name": "p", "sort": "Bool"}, {"name": "q", "sort": "Bool"}],
     "premises": [{"id": "A", "expr": {"op": "var", "name": "p"}}, {"id": "B", "expr": {"op": "implies", "left": {"op": "var", "name": "p"}, "right": {"op": "var", "name": "q"}}}],
     "conclusion": {"id": "C", "expr": {"op": "var", "name": "q"}}}
r = c.post("/v1/verify", json={"problem": P, "config": {"memory_max_mb": 16}}, headers=AUTH)
print("request1", r.status_code, r.json().get("code"))
r = c.post("/v1/verify", json={"problem": P}, headers=AUTH)
print("request2", r.status_code, r.json().get("status"))
r = c.post("/v1/verify", json={"problem": P}, headers=AUTH)
print("request3", r.status_code, r.json().get("status"))
'''


def test_memory_budget_request_followed_by_normal_requests_leaves_the_process_alive():
    proc = subprocess.run([sys.executable, "-I", "-c", _SUBPROCESS_CASE], capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, (proc.returncode, proc.stderr[-500:])
    assert proc.stdout.strip().splitlines() == ["request1 400 E100", "request2 200 ENTAILED", "request3 200 ENTAILED"]


def test_duplicate_keys_in_the_envelope_or_problem_are_rejected(client):
    good = json.dumps({"problem": transitivity_problem()})
    inside_problem = good.replace('"problem_id": "p1"', '"problem_id": "p1", "problem_id": "p2"')
    r = client.post("/v1/verify", content=inside_problem.encode(), headers={**AUTH, "Content-Type": "application/json"})
    assert_clean_error(r, 400, "E100")
    envelope = good[:-1] + ', "problem": {}}'
    assert_clean_error(client.post("/v1/verify", content=envelope.encode(), headers={**AUTH, "Content-Type": "application/json"}), 400, "E100")
    assert client.post("/v1/verify", content=good.encode(), headers={**AUTH, "Content-Type": "application/json"}).status_code == 200


def test_outcomes_route_turns_a_deeply_nested_fixture_into_a_bounded_outcome(client):
    from .test_outcomes import maths_report

    payload = {"report": maths_report().model_dump(mode="json"), "claim_id": "k1", "fixture_responses": {"k1": "[" * 100_000}}
    r = client.post("/v1/outcomes", json=payload, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["display_status"] == "INVALID_FORMALIZATION" and body["translation"]["status"] == "INVALID_FORMALIZATION"
    assert any("too deep" in d for d in body["translation"]["diagnostics"])
