"""The two routes of the integration profiles go through the service's existing gates unchanged (PROTOCOL.md section 14.1, "Service
routes"): bearer authentication (401 E502), the per-token rate limit (429 E503), the body-size limit (413 E306), strict
JSON with a closed key set (400 E100), self-certification (400 E505) and non-blocking concurrency (503 E504). An
in-contract request that is out of the protocol's contract is answered 400 with its KIT-REQ code. The ``engine`` profile
exposes no new route."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from epinoic_logic.integration.protocol import Capabilities
from epinoic_logic.integration.runtime import build_runtime
from epinoic_logic.service import ServiceSettings, create_app
from tests.integration.helpers import ENGINE_KEY_HEX, TOKEN, FixtureProbes, answer_envelope, settings, turn_request

CORPUS = Path(__file__).resolve().parents[2] / "integration" / "sim" / "corpus" / "synthetic" / "s1"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _item(name: str) -> dict:
    return json.loads((CORPUS / "specialists" / f"{name}.json").read_text(encoding="utf-8"))


def _service(**overrides):
    values = dict(service_token=TOKEN, signing_key=bytes.fromhex(ENGINE_KEY_HEX), signing_key_id="default")
    values.update(overrides)
    clock = values.pop("clock", None)
    runtime = build_runtime(settings(FIXTURE_DIR=str(CORPUS)), probes=FixtureProbes())
    kw = {"clock": clock} if clock is not None else {}
    return TestClient(create_app(ServiceSettings(**values), integration=runtime, **kw), raise_server_exceptions=False)


def _body(**changes) -> dict:
    item = _item("hi-s1")
    body = turn_request([answer_envelope(1, answer=item["response_text"])], user_text=item["question"])
    body.update(changes)
    return body


def _code(r) -> str:
    data = r.json()
    return data.get("code") or (data.get("error") or {}).get("code") or (data.get("detail") or {}).get("code")


def test_the_engine_profile_exposes_no_new_route():
    plain = TestClient(create_app(ServiceSettings(service_token=TOKEN, signing_key=bytes.fromhex(ENGINE_KEY_HEX))), raise_server_exceptions=False)
    assert plain.get("/v1/capabilities", headers=AUTH).status_code == 404
    assert plain.post("/v1/turns/check", headers=AUTH, json=_body()).status_code == 404
    paths_plain = {getattr(r, "path", None) for r in plain.app.routes}
    paths_kit = {getattr(r, "path", None) for r in _service().app.routes}
    assert paths_kit - paths_plain == {"/v1/capabilities", "/v1/turns/check"} and paths_plain <= paths_kit


def test_capabilities_need_the_bearer_token_and_report_the_router_without_requiring_it():
    c = _service()
    r = c.get("/v1/capabilities")
    assert r.status_code == 401 and _code(r) == "E502"
    r = c.get("/v1/capabilities", headers=AUTH)
    assert r.status_code == 200
    caps = Capabilities.model_validate(r.json())
    assert caps.selftest.passed and caps.ports.router.required is False and caps.ports.router.attached is False
    assert TOKEN not in r.text and ENGINE_KEY_HEX not in r.text


def test_a_turn_check_runs_behind_the_same_gates_and_returns_a_signed_verdict():
    c = _service()
    r = c.post("/v1/turns/check", json=_body())
    assert r.status_code == 401 and _code(r) == "E502"
    r = c.post("/v1/turns/check", headers=AUTH, json=_body())
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["delivery"]["decision"] == "deliver" and v["signature"]["alg"] == "hmac-sha256"


@pytest.mark.parametrize("raw,status,code", [
    (b'{"schema": 1, "schema": 2}', 400, "E100"),             # strict JSON: a repeated key
    (b'[1, 2]', 400, "E100"),                                 # not an object
    (b'{"schema": "x", "extra": 1}', 400, "E100"),            # a closed key set
    (b'{"verified": true}', 400, "E505"),                     # self-certification at the top level
    (b'{"status": "ENTAILED"}', 400, "E505"),
])
def test_strict_json_and_self_certification_are_refused_before_the_protocol(raw, status, code):
    r = _service().post("/v1/turns/check", headers={**AUTH, "Content-Type": "application/json"}, content=raw)
    assert r.status_code == status and _code(r) == code


def test_the_body_limit_is_read_before_the_body():
    c = _service(max_body_bytes=2048)
    r = c.post("/v1/turns/check", headers={**AUTH, "Content-Type": "application/json"}, content=json.dumps(_body()).encode())
    assert r.status_code == 413 and _code(r) == "E306"


def test_the_rate_limit_applies_per_token():
    now = [0.0]
    c = _service(rate_per_minute=1, clock=lambda: now[0])
    assert c.get("/v1/capabilities", headers=AUTH).status_code == 200
    r = c.post("/v1/turns/check", headers=AUTH, json=_body())
    assert r.status_code == 429 and _code(r) == "E503"


def test_concurrency_is_non_blocking():
    c = _service(max_concurrency=1)
    semaphore = c.app.state.semaphore
    asyncio.run(semaphore.acquire())  # hold the single slot from outside the app
    try:
        r = c.post("/v1/turns/check", headers=AUTH, json=_body())
        assert r.status_code == 503 and _code(r) == "E504"
    finally:
        semaphore.release()
    assert c.post("/v1/turns/check", headers=AUTH, json=_body()).status_code == 200


@pytest.mark.parametrize("changes,code", [
    ({"mode": "combined"}, "KIT-REQ-002"),        # not offered before a combinator is connected
    ({"policy": "verified-v2"}, "KIT-REQ-003"),
    ({"budget_ms": 10}, "KIT-REQ-007"),
    ({"ids": {"task_id": "t 1", "request_id": "a_1"}}, "KIT-REQ-004"),
    ({"protocol": "epinoic.integration.v2"}, "KIT-REQ-001"),
])
def test_an_out_of_contract_request_is_answered_400_with_its_kit_code(changes, code):
    r = _service().post("/v1/turns/check", headers=AUTH, json=_body(**changes))
    assert r.status_code == 400 and r.json()["code"] == code and r.json()["message"]
