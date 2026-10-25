"""Service regressions from the round-7 arena fixers' hand-off (owner: core).

* security-1 / robustness-and-contracts-6: /v1/results/verify-signature and /v1/results/release-check returned 500 for a
  result whose signature holds non-ASCII text or whose fields hold a lone surrogate; they answer valid/eligible false.
* security-5: a genuine result posted after an exclude_none round trip was reported as not matching its signature.
* security-4: a client claim_id or result_id holding a line break wrote forged records into the service log.
* robustness-and-contracts-4: provider output holding a lone surrogate made POST /v1/outcomes return 500.
"""
from __future__ import annotations

import json
import logging

import pytest

from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

from .conftest import AUTH, transitivity_problem

FORGED = "\nINFO epinoic_logic.service request_id=FORGED path=/v1/verify http_status=200 result_status=ENTAILED"


def _signed(client) -> dict:
    r = client.post("/v1/verify", headers=AUTH, json={"problem": transitivity_problem()})
    assert r.status_code == 200 and r.json()["status"] == "ENTAILED"
    return r.json()


@pytest.mark.parametrize("signature", ["é" * 64, "\ud83d" * 64, "Z" * 64])
def test_a_forged_signature_of_any_text_is_answered_never_a_server_error(client, signature):
    body = json.dumps({"result": {**_signed(client), "signature": signature}})
    r = client.post("/v1/results/verify-signature", headers={**AUTH, "Content-Type": "application/json"}, content=body)
    assert r.status_code in (200, 400) and r.json().get("valid") is not True
    r = client.post("/v1/results/release-check", headers={**AUTH, "Content-Type": "application/json"}, content=body)
    assert r.status_code in (200, 400) and r.json().get("eligible") is not True


def test_a_result_holding_a_lone_surrogate_is_answered_never_a_server_error(client):
    good = _signed(client)
    body = json.dumps({k: v for k, v in good.items() if k != "claim_id"})[:-1] + ',"claim_id":"\\ud83d"}'
    for path, key in (("/v1/results/verify-signature", "valid"), ("/v1/results/release-check", "eligible")):
        r = client.post(path, headers={**AUTH, "Content-Type": "application/json"}, content='{"result":%s}' % body)
        assert r.status_code in (200, 400) and r.json().get(key) is not True


def test_a_genuine_result_verifies_after_an_exclude_none_round_trip(client):
    good = _signed(client)
    lean = {k: v for k, v in good.items() if v is not None}
    lean["solver_config"] = {k: v for k, v in good["solver_config"].items() if v is not None}
    r = client.post("/v1/results/verify-signature", headers=AUTH, json={"result": lean})
    assert r.status_code == 200 and r.json()["valid"] is True
    r = client.post("/v1/results/verify-signature", headers=AUTH, json={"result": good})
    assert r.status_code == 200 and r.json()["valid"] is True


def test_no_client_id_starts_a_new_log_record(client, caplog):
    caplog.set_level(logging.INFO, logger="epinoic_logic.service")
    r = client.post("/v1/verify", headers=AUTH, json={"problem": transitivity_problem(claim_id="c1" + FORGED)})
    assert r.status_code in (200, 422)
    good = _signed(client)
    client.post("/v1/results/release-check", headers=AUTH, json={"result": {**good, "result_id": "x" + FORGED}})
    records = [rec.getMessage() for rec in caplog.records if rec.name == "epinoic_logic.service"]
    assert records and not any("\n" in m or "\r" in m or "FORGED" in m for m in records)
    assert any("sha256:" in m for m in records)  # a client id that is not a plain id is logged as a digest
    plain = [m for m in records if "claim_id=c1 " in m or m.endswith("claim_id=c1")]
    assert plain  # a plain id is logged as it is


def test_a_provider_output_holding_a_lone_surrogate_is_an_invalid_formalization(client):
    text = "Revenue rose from 100 to 120, an increase of 20."
    ids = dict(request_id="req-r", task_id="task-r", report_id="r1", agent_id="economics-specialist", subject="Economics", task_type="short_answer")
    rep = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), supplied_texts=[], created_at="2026-10-11T11:00:00Z",
                           claims=[ClaimRecord(**ids, claim_id="c1", claim_text=text, claim_role="quantitative")])
    fixture = json.dumps('{"problem": "\ud83d"}')
    body = '{"report": %s, "claim_id": "c1", "fixture_responses": {"c1": %s}}' % (json.dumps(rep.model_dump(mode="json")), fixture)
    r = client.post("/v1/outcomes", headers={**AUTH, "Content-Type": "application/json"}, content=body)
    assert r.status_code == 200, r.text
    assert r.json()["display_status"] == "INVALID_FORMALIZATION"
