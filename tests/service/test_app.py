"""Service boundary tests: authentication, limits, signing, self-certification, error hygiene."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

import epinoic_logic.service.app as app_module
from epinoic_logic.engine.provenance import verify_signature
from epinoic_logic.engine.results import VerificationResult
from epinoic_logic.service.app import HttpError, TokenBucketLimiter, _read_body

from .conftest import AUTH, KEY, KEY_ID, TOKEN, make_client, make_settings, nonlinear_problem, transitivity_problem

FORBIDDEN_FRAGMENTS = ("Traceback", 'File "', "raise ", ".py")


def assert_clean_error(response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"code", "message", "request_id"}
    assert body["code"] == code
    text = response.text
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in text, fragment
    assert response.headers["x-request-id"] == body["request_id"]
    return body


# --- health -------------------------------------------------------------------------

def test_healthz_is_unauthenticated_and_reports_versions_only(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert set(body["versions"]) == {"ir_version", "engine_version", "policy_version", "translator_version", "z3_version"}
    assert set(body) == {"ok", "versions"}
    assert TOKEN not in r.text and KEY.hex() not in r.text and KEY_ID not in r.text
    assert len(r.headers["x-request-id"]) == 32


# --- authentication -----------------------------------------------------------------

@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token-0123456789abcdef"},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": "Bearer"},
        {"Authorization": f"Bearer {TOKEN}x"},
    ],
)
def test_verify_requires_the_exact_bearer_token(client, headers):
    r = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers={**headers, "X-Request-Id": "trace-401"})
    body = assert_clean_error(r, 401, "E502")
    assert body["request_id"] == "trace-401"
    assert r.headers["www-authenticate"] == "Bearer"


def test_every_v1_route_is_authenticated(client):
    for path, payload in (
        ("/v1/verify", {"problem": transitivity_problem()}),
        ("/v1/results/verify-signature", {"result": {}}),
        ("/v1/outcomes", {"report": {}, "claim_id": "c", "fixture_responses": {}}),
    ):
        assert_clean_error(client.post(path, json=payload), 401, "E502")


# --- verify: signed results ---------------------------------------------------------

def test_verify_returns_signed_entailed_result_that_verifies_with_the_key(client):
    r = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ENTAILED"
    assert body["signature"] and body["signature_key_id"] == KEY_ID
    assert sorted(body["premises_relied_on"]) == ["P1", "P2"]
    assert body["scope_statement"].startswith("This result concerns only the formal encoding")
    result = VerificationResult.model_validate(body)
    assert verify_signature(result, KEY)
    assert not verify_signature(result, b"another-key-another-key-another-")


def test_verify_signature_endpoint_true_then_false_after_tampering(client):
    signed = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH).json()
    ok = client.post("/v1/results/verify-signature", json={"result": signed}, headers=AUTH)
    assert ok.status_code == 200 and ok.json() == {"valid": True}

    tampered_status = {**signed, "status": "COUNTEREXAMPLE"}
    r = client.post("/v1/results/verify-signature", json={"result": tampered_status}, headers=AUTH)
    assert r.status_code == 200 and r.json()["valid"] is False

    tampered_binding = json.loads(json.dumps(signed))
    tampered_binding["binding"]["problem_digest"] = "0" * 64
    assert client.post("/v1/results/verify-signature", json={"result": tampered_binding}, headers=AUTH).json()["valid"] is False

    tampered_premises = {**signed, "premises_relied_on": ["P1"]}
    assert client.post("/v1/results/verify-signature", json={"result": tampered_premises}, headers=AUTH).json()["valid"] is False

    unsigned = {**signed, "signature": None, "signature_key_id": None}
    assert client.post("/v1/results/verify-signature", json={"result": unsigned}, headers=AUTH).json()["valid"] is False

    foreign_key = {**signed, "signature_key_id": "someone-else"}
    assert client.post("/v1/results/verify-signature", json={"result": foreign_key}, headers=AUTH).json()["valid"] is False

    not_a_result = client.post("/v1/results/verify-signature", json={"result": {"status": "ENTAILED"}}, headers=AUTH)
    assert not_a_result.status_code == 200 and not_a_result.json()["valid"] is False

    assert_clean_error(client.post("/v1/results/verify-signature", json={"result": "x"}, headers=AUTH), 400, "E100")
    assert_clean_error(client.post("/v1/results/verify-signature", json={"nope": {}}, headers=AUTH), 400, "E100")


def test_unsigned_test_mode_never_reports_a_signature_as_valid():
    client = make_client(make_settings(signing_key=None, allow_unsigned_for_tests=True))
    body = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH).json()
    assert body["status"] == "ENTAILED" and body["signature"] is None
    r = client.post("/v1/results/verify-signature", json={"result": body}, headers=AUTH)
    assert r.json()["valid"] is False


# --- verify: non-success statuses are results, not HTTP errors ------------------------

def test_invalid_problem_is_a_signed_200_invalid_formalization_result(client):
    r = client.post("/v1/verify", json={"problem": {"problem_id": "p", "request_id": "r", "claim_id": "c"}}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "INVALID_FORMALIZATION"
    assert body["diagnostics"] and all(d["code"] == "E100" for d in body["diagnostics"])
    assert body["binding"]["problem_digest"] and body["signature"]
    assert verify_signature(VerificationResult.model_validate(body), KEY)

    sort_error = transitivity_problem(symbols=[{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Real"}, {"name": "z", "sort": "Int"}])
    body = client.post("/v1/verify", json={"problem": sort_error}, headers=AUTH).json()
    assert body["status"] == "INVALID_FORMALIZATION" and any(d["code"] == "E102" for d in body["diagnostics"])


def test_unsupported_problem_is_a_signed_200_unsupported_result(client):
    body = client.post("/v1/verify", json={"problem": nonlinear_problem()}, headers=AUTH).json()
    assert body["status"] == "UNSUPPORTED"
    assert any(d["code"] == "E201" for d in body["diagnostics"])
    assert verify_signature(VerificationResult.model_validate(body), KEY)


def test_config_is_applied_and_bound_into_the_result(client):
    body = client.post("/v1/verify", json={"problem": transitivity_problem(), "config": {"timeout_ms": 5000, "produce_smt2": False}}, headers=AUTH).json()
    assert body["status"] == "ENTAILED"
    assert body["solver_config"]["timeout_ms"] == 5000 and body["binding"]["smt2"] is None
    default = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH).json()
    assert default["binding"]["config_digest"] != body["binding"]["config_digest"]


# --- envelope errors ----------------------------------------------------------------

@pytest.mark.parametrize(
    "content, code",
    [
        (b"{not json", "E100"),
        (b'{"problem": NaN}', "E100"),
        (b"[1, 2]", "E100"),
        (b'"a string"', "E100"),
        (b"{}", "E100"),
        (b'{"problem": "not an object"}', "E100"),
        (b'{"problem": {}, "extra": 1}', "E100"),
        (b'{"problem": {}, "config": {"timeout_ms": 0}}', "E100"),
        (b'{"problem": {}, "config": 5}', "E100"),
        (b'{"problem": {}, "config": {"unknown_option": true}}', "E100"),
        (b"\xff\xfe{}", "E100"),
        (b"[" * 100_000, "E303"),  # parser recursion limit -> TOO_DEEP, as in the validator
    ],
    ids=[
        "malformed", "nan", "array", "string", "missing-problem", "problem-not-object", "unknown-key",
        "config-timeout-zero", "config-not-object", "config-unknown-option", "not-utf8", "deeply-nested",
    ],
)
def test_envelope_errors_are_400_without_echoing_the_body(client, content, code):
    r = client.post("/v1/verify", content=content, headers={**AUTH, "Content-Type": "application/json"})
    body = assert_clean_error(r, 400, code)
    assert "NaN" not in body["message"] and "not an object" not in body["message"]


# --- self-certification -------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(app_module.SELF_CERTIFICATION_KEYS))
def test_self_certification_keys_at_top_level_are_rejected_with_E505(client, key):
    r = client.post("/v1/verify", json={"problem": transitivity_problem(), key: "ENTAILED"}, headers=AUTH)
    body = assert_clean_error(r, 400, "E505")
    assert key in body["message"] and "ENTAILED" not in body["message"]


def test_self_certification_inside_the_problem_is_rejected_with_E505(client):
    r = client.post("/v1/verify", json={"problem": {**transitivity_problem(), "verified": True}}, headers=AUTH)
    assert_clean_error(r, 400, "E505")


def test_self_certification_is_rejected_on_the_outcomes_route(client):
    r = client.post("/v1/outcomes", json={"report": {}, "claim_id": "c", "fixture_responses": {}, "self_certified": True}, headers=AUTH)
    assert_clean_error(r, 400, "E505")


# --- size limit ---------------------------------------------------------------------

def test_oversize_body_is_rejected_with_413_before_verification():
    client = make_client(make_settings(max_body_bytes=2048))
    big = {"problem": {**transitivity_problem(), "notes": "a" * 2048}}
    r = client.post("/v1/verify", json=big, headers=AUTH)
    body = assert_clean_error(r, 413, "E306")
    assert "2048" in body["message"]
    small = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH)
    assert small.status_code == 200 and small.json()["status"] == "ENTAILED"


class _StubRequest:
    """Minimal stand-in for starlette.Request: headers mapping plus a chunked stream."""

    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}
        self._chunks = chunks

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


def test_streamed_body_without_content_length_is_capped_while_reading():
    request = _StubRequest([b"x" * 600, b"y" * 600])
    with pytest.raises(HttpError) as info:
        asyncio.run(_read_body(request, 1000))
    assert info.value.status_code == 413 and info.value.code.value == "E306"
    assert asyncio.run(_read_body(_StubRequest([b"ab", b"cd"]), 1000)) == b"abcd"
    with pytest.raises(HttpError) as info:
        asyncio.run(_read_body(_StubRequest([b""], {"content-length": "nine"}), 1000))
    assert info.value.status_code == 400


# --- rate limit ---------------------------------------------------------------------

def test_rate_limit_returns_429_after_the_bucket_is_exhausted_and_refills():
    now = [1000.0]
    client = make_client(make_settings(rate_per_minute=2), clock=lambda: now[0])
    payload = {"problem": transitivity_problem()}
    assert client.post("/v1/verify", json=payload, headers=AUTH).status_code == 200
    assert client.post("/v1/verify", json=payload, headers=AUTH).status_code == 200
    r = client.post("/v1/verify", json=payload, headers=AUTH)
    assert_clean_error(r, 429, "E503")
    assert r.headers["retry-after"] == "1"
    # unauthenticated requests never consume or bypass the bucket
    assert client.post("/v1/verify", json=payload).status_code == 401
    assert client.get("/healthz").status_code == 200
    now[0] += 30.0  # 2 per minute -> one token back after 30 s
    assert client.post("/v1/verify", json=payload, headers=AUTH).status_code == 200
    assert client.post("/v1/verify", json=payload, headers=AUTH).status_code == 429


def test_token_bucket_limiter_is_per_key_and_capped_at_capacity():
    now = [0.0]
    limiter = TokenBucketLimiter(3, clock=lambda: now[0])
    assert [limiter.try_acquire("a") for _ in range(4)] == [True, True, True, False]
    assert limiter.try_acquire("b") is True
    now[0] += 600.0
    assert [limiter.try_acquire("a") for _ in range(4)] == [True, True, True, False]
    with pytest.raises(ValueError):
        TokenBucketLimiter(0)


# --- concurrency --------------------------------------------------------------------

def test_concurrency_limit_returns_503_while_the_only_slot_is_held():
    settings = make_settings(max_concurrency=1)
    client = make_client(settings)
    semaphore = client.app.state.semaphore
    asyncio.run(semaphore.acquire())  # hold the single slot from outside the app
    try:
        r = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH)
        assert_clean_error(r, 503, "E504")
        assert r.headers["retry-after"] == "1"
        assert client.get("/healthz").status_code == 200
    finally:
        semaphore.release()
    ok = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH)
    assert ok.status_code == 200 and ok.json()["status"] == "ENTAILED"
    assert not semaphore.locked()


# --- error hygiene and request ids --------------------------------------------------

def test_unexpected_engine_failure_is_a_bare_500_without_internals(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr(app_module, "verify", boom)
    r = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers={**AUTH, "X-Request-Id": "trace-500"})
    body = assert_clean_error(r, 500, "E900")
    assert body["request_id"] == "trace-500" and body["message"] == "internal error"
    assert "secret-internal-detail" not in r.text and "RuntimeError" not in r.text


def test_no_error_body_contains_a_stack_trace(client, monkeypatch):
    responses = [
        client.post("/v1/verify", json={"problem": transitivity_problem()}),
        client.post("/v1/verify", content=b"{", headers=AUTH),
        client.post("/v1/verify", json={"problem": transitivity_problem(), "status": "x"}, headers=AUTH),
        client.get("/v1/verify", headers=AUTH),
        client.get("/does-not-exist"),
    ]
    oversize = make_client(make_settings(max_body_bytes=1024))
    responses.append(oversize.post("/v1/verify", json={"problem": {"notes": "n" * 2000}}, headers=AUTH))
    for r in responses:
        assert r.status_code >= 400
        for fragment in FORBIDDEN_FRAGMENTS:
            assert fragment not in r.text, (r.status_code, fragment)
        assert r.headers["x-request-id"]


def test_request_id_is_echoed_or_generated_on_every_response(client):
    ok = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers={**AUTH, "X-Request-Id": "abc.def:123-X"})
    assert ok.status_code == 200 and ok.headers["x-request-id"] == "abc.def:123-X"
    denied = client.post("/v1/verify", json={}, headers={"X-Request-Id": "abc"})
    assert denied.status_code == 401 and denied.headers["x-request-id"] == "abc" == denied.json()["request_id"]
    missing = client.get("/no-such-route", headers={"X-Request-Id": "r404"})
    assert missing.status_code == 404 and missing.headers["x-request-id"] == "r404"
    generated = client.get("/healthz")
    assert len(generated.headers["x-request-id"]) == 32 and all(c in "0123456789abcdef" for c in generated.headers["x-request-id"])
    for bad in ("has space", "x" * 129, "semi;colon", ""):
        r = client.get("/healthz", headers={"X-Request-Id": bad})
        assert r.headers["x-request-id"] != bad and len(r.headers["x-request-id"]) == 32


def test_interactive_docs_are_disabled(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_outcomes_route_reports_501_when_the_pipeline_cannot_be_imported(client, monkeypatch):
    real_import = app_module.importlib.import_module

    def missing(name, *args, **kwargs):
        if name.startswith("epinoic_logic.translate.pipeline"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(app_module.importlib, "import_module", missing)
    r = client.post("/v1/outcomes", json={"report": {}, "claim_id": "c", "fixture_responses": {}}, headers=AUTH)
    assert_clean_error(r, 501, "E900")
