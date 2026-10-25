"""E2E B15: a payload that certifies its own grounding (``verified: true``) is handled two ways, and the integration
contract states both. In process, ``engine.verify`` discards the assertion and records diagnostic E505: the premise it
was meant to certify stays an unverified dependency. Over HTTP, ``POST /v1/verify`` refuses the request with 400 E505
before anything runs (no result, no solver call): the stricter behaviour, kept. The contract names this file."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.statuses import VerificationStatus as S

from .conftest import AUTH, V, I, cmp, transitivity_problem

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "integration-contract.md"


def self_certified_problem() -> dict:
    grounding = {"kind": "supplied_text", "source_refs": [{"document_id": "d1", "excerpt": "x is 3"}], "certainty": "established", "verified": True}
    return {"problem_id": "p-e505", "request_id": "req1", "claim_id": "c1", "query": "entailment", "symbols": [{"name": "x", "sort": "Int"}],
            "premises": [{"id": "P1", "expr": cmp("eq", V("x"), I(3)), "grounding": grounding}],
            "conclusion": {"id": "C", "expr": cmp("gt", V("x"), I(2))}}


@pytest.mark.parametrize("form", ["dict", "json text", "bytes"])
def test_in_process_the_assertion_is_discarded_with_E505(form):
    raw = self_certified_problem()
    payload = raw if form == "dict" else json.dumps(raw) if form == "json text" else json.dumps(raw).encode()
    res = verify(payload, SolverConfig())
    assert res.status is S.ENTAILED                                    # the verdict on the encoding is unchanged
    assert "E505" in {d.code for d in res.diagnostics}                 # the discard is recorded
    assert res.unverified_dependencies == ["P1"]                       # the premise it meant to certify is not established


def test_without_the_assertion_no_E505_is_recorded():
    raw = self_certified_problem()
    del raw["premises"][0]["grounding"]["verified"]
    res = verify(raw, SolverConfig())
    assert res.status is S.ENTAILED and "E505" not in {d.code for d in res.diagnostics}


def test_over_http_the_request_is_refused_with_400_E505_before_anything_runs(client, monkeypatch):
    from epinoic_logic.service import app as app_module
    calls: list = []
    real = app_module.verify

    def spy(*a, **k):
        calls.append(a)
        return real(*a, **k)

    monkeypatch.setattr(app_module, "verify", spy)
    r = client.post("/v1/verify", json={"problem": self_certified_problem()}, headers=AUTH)
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "E505" and "status" not in body and "result_id" not in body
    assert calls == []                                                 # nothing ran
    ok = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH)
    assert ok.status_code == 200 and ok.json()["status"] == "ENTAILED" and len(calls) == 1   # the spy sees a real run


def test_the_contract_states_both_behaviours_and_names_this_test():
    text = CONTRACT.read_text(encoding="utf-8")
    section2 = " ".join(text[text.index("## 2. Input"):text.index("## 3. Validation")].split())
    assert "discarded, with diagnostic E505" in section2
    assert "400 E505" in section2 and "POST /v1/verify" in section2
    assert "tests/service/test_e505_contract_b15.py" in section2
