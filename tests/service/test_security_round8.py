"""Review round 8: the security fixes of the argument-diagnosis design (section C) and the boundary's robustness findings.

1. B26 / SEC-1: identifiers, assertion ids and literals are matched whole, so "x\\n" is never a second symbol and "P1\\n"
   never impersonates "P1" (E100, in process and over HTTP); the request id header is matched whole too.
2. SEC-3: the code fence is found by a linear scan, the provider text is bounded (64 KiB) before parsing, and a normal
   fenced reply reads exactly as the previous regular expressions read it.
3. SEC-4: every logged field is escaped and cut, on the service's logger and the translation pipeline's, so a claim id
   holding a line break stays one log line.
4. SEC-6: ``POST /v1/outcomes`` refuses a client's fixture responses (403 E506, before the body is read) unless the
   service allows them.
5. SEC-5: ``model_completion`` is server-controlled (400 E100); in process every counterexample value is a literal.
6. SEC-8: ``adapter_id`` is looked up in a closed allowlist; a refused id imports nothing.
7. B27 and the lone-surrogate findings (robustness-and-contracts-4 and -6): a lone surrogate is an invalid payload
   (E100) to the validator, in provider output and in every HTTP body, never a 500.
8. SEC-7: the diagnosis is Python-only and signed with the result; an undiagnosed result is never released; the derived
   runs stay within their bounds on a problem of 128 premises.
9. robustness-and-contracts-11: ``config`` and the outcome route's ``report`` are validated strictly (``true`` is no
   timeout, ``"100"`` no integer, ``"yes"`` no boolean).
10. formal-robustness-1: a model is built outside the solver's bounds, so its values are bounded before any text of them
    is built (UNKNOWN E401, never a cut value), the consistency precheck builds none, and the extraction is timed.
"""
from __future__ import annotations

import importlib
import json
import logging
import random
import re
import time
from typing import Any

import pytest

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine import procedures
from epinoic_logic.engine.argument import MAX_DERIVED_RUNS, TOTAL_BUDGET_MS
from epinoic_logic.engine.provenance import verify_signature
from epinoic_logic.engine.results import VerificationResult
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.engine.validator import DEFAULT_LIMITS, parse_and_validate
from epinoic_logic.service import ServiceSettings
from epinoic_logic.service import app as app_mod
from epinoic_logic.service.settings import SettingsError
from epinoic_logic.translate import parsing
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from .conftest import AUTH, I, KEY, KEY_ID, TOKEN, V, cmp, make_client, make_settings, transitivity_problem
from .test_outcomes import maths_fixture, maths_report

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def _problem(**fields: Any) -> dict[str, Any]:
    data = {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
            "symbols": [{"name": "x", "sort": "Int"}], "premises": [{"id": "P1", "expr": cmp("gt", V("x"), I(2))}],
            "conclusion": {"id": "C", "expr": cmp("gt", V("x"), I(1))}}
    data.update(fields)
    return data


def _codes(result: VerificationResult) -> set[str]:
    return {d.code for d in result.diagnostics}


# ------------------------------------------------------------------------------------------------ 1. B26 / SEC-1

IMPERSONATIONS = {
    "a second symbol": dict(symbols=[{"name": "x", "sort": "Int"}, {"name": "x\n", "sort": "Int"}]),
    "an impersonating premise id": dict(premises=[{"id": "P1", "expr": cmp("gt", V("x"), I(2))}, {"id": "P1\n", "expr": cmp("gt", V("x"), I(5))}]),
    "a literal with a newline": dict(premises=[{"id": "P1", "expr": cmp("gt", V("x"), {"op": "int", "value": "2\n"})}]),
}


@pytest.mark.parametrize("name", sorted(IMPERSONATIONS))
def test_a_trailing_newline_is_never_part_of_an_identifier_in_process(name):
    r = verify(_problem(**IMPERSONATIONS[name]), CFG)
    assert r.status is S.INVALID_FORMALIZATION and "E100" in _codes(r)


@pytest.mark.parametrize("name", sorted(IMPERSONATIONS))
def test_a_trailing_newline_is_never_part_of_an_identifier_over_http(client, name):
    r = client.post("/v1/verify", json={"problem": _problem(**IMPERSONATIONS[name])}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "INVALID_FORMALIZATION" and "E100" in {d["code"] for d in r.json()["diagnostics"]}


def test_the_request_id_header_is_matched_whole():
    assert app_mod._REQUEST_ID_RE.fullmatch("req-1") and not app_mod._REQUEST_ID_RE.fullmatch("req-1\n")


# ------------------------------------------------------------------------------------------------ 2. SEC-3

_OLD_FENCE_RE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL)
_OLD_INLINE_FENCE_RE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*(.*?)```", re.DOTALL)


def _old_strip(text: str) -> str:
    """The previous reader (two regular expressions), the reference for ordinary replies."""
    m = _OLD_FENCE_RE.search(text) or _OLD_INLINE_FENCE_RE.search(text)
    return text if m is None else m.group(1)


FENCED = [
    '```json\n{"a": 1}\n```', 'Here it is:\n```json\n{"a": 1}\n```\nThanks.', '```\n{"a": 1}\n```', '```json\r\n{"a": 1}\r\n```',
    '```json  \n{"a": 1}\n   ```', '```{"a": 1}```', 'no fence {"a": 1}', '```json\n{"a": "```"}\n```', '```py\nx\n```\n```json\n{"a": 1}\n```',
    'text ```json {"a": 1}``` more', '```json\n{"a": 1}', '```\n\n```', '``` x ``` y ```',
]


@pytest.mark.parametrize("text", FENCED)
def test_an_ordinary_reply_reads_as_before(text):
    assert parsing.strip_code_fences(text) == _old_strip(text)


def test_random_replies_read_as_before():
    """A deterministic differential check against the previous regular expressions over short strings of fence
    characters (200,000 such strings were compared when the scan was written; none differed)."""
    rng = random.Random(20261017)
    alphabet = ["`", "`", "`", "\n", "\r", " ", "\t", "a", "j", "{", "}", "-"]
    for _ in range(20_000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        assert parsing.strip_code_fences(text) == _old_strip(text), repr(text)


@pytest.mark.parametrize("unit", ["```\n", "x```\n", "```json\n", "```", "`", "```a", "aaaaaaa```"])
def test_a_megabyte_of_unclosed_openers_is_scanned_at_once(unit):
    text = unit * (1_000_000 // len(unit))
    start = time.perf_counter()
    parsing.strip_code_fences(text)
    assert time.perf_counter() - start < 1.0   # the regular expressions took seconds on 40 KB (about 0.15 s per MB now)
    best = min(_timed(lambda: _refused(text)) for _ in range(3))
    assert best < 0.05                         # and a reply this large is refused before the scan


def _timed(fn) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def _refused(text: str) -> None:
    with pytest.raises(parsing.ProviderOutputTooLarge):
        parsing.parse_json_object(text)


def test_provider_text_is_bounded_before_parsing():
    limit = parsing.MAX_PROVIDER_TEXT_BYTES
    assert limit == 64 * 1024
    ok = '{"a": "' + "x" * (limit - 9) + '"}'
    assert len(ok.encode()) == limit and parsing.parse_json_object(ok)["a"]
    with pytest.raises(parsing.ProviderOutputTooLarge, match="too large"):
        parsing.parse_json_object('{"a": "' + "x" * (limit - 8) + '"}')       # 64 KiB + 1
    with pytest.raises(parsing.ProviderOutputError, match="too deep"):
        parsing.parse_json_object("[" * (limit + 1))


# ------------------------------------------------------------------------------------------------ 3. SEC-4

FORGED = "c1\nINFO epinoic_logic.service request_id=x path=/v1/verify result_status=ENTAILED claim_id=forged"


def _lines(caplog, logger: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == logger]


def test_a_logged_claim_id_stays_one_line(client, caplog):
    caplog.set_level(logging.INFO)
    r = client.post("/v1/verify", json={"problem": transitivity_problem(claim_id=FORGED)}, headers=AUTH)
    assert r.status_code == 200 and r.json()["claim_id"] == FORGED
    [line] = [m for m in _lines(caplog, "epinoic_logic.service") if "result_status=" in m]   # one record, so one line
    assert "\n" not in line and "\r" not in line and "claim_id=c1\\nINFO epinoic_logic.service" in line


def test_the_pipeline_logger_is_escaped_too(client, caplog):
    caplog.set_level(logging.INFO)
    report = maths_report().model_dump(mode="json")
    report["claims"][0]["claim_id"] = FORGED
    fixtures = {FORGED: maths_fixture()["k1"]}
    fixtures[FORGED]["problem"]["claim_id"] = FORGED
    r = client.post("/v1/outcomes", json={"report": report, "claim_id": FORGED, "fixture_responses": fixtures}, headers=AUTH)
    assert r.status_code == 200, r.text
    lines = _lines(caplog, "epinoic_logic.translate.pipeline")
    assert lines and all("\n" not in m for m in lines) and any("c1\\nINFO" in m for m in lines)


def test_each_field_is_escaped_and_cut():
    assert app_mod._log_safe("a\r\nb\x1b[31m \\\ud800") == "a\\r\\nb\\x1b[31m\\u2028\\\\\\ud800"
    cut = app_mod._log_safe("x" * 500)
    assert cut.startswith("x" * app_mod.LOG_FIELD_MAX_CHARS) and cut.endswith("...(+372 chars)")


# ------------------------------------------------------------------------------------------------ 4. SEC-6

def _outcome_body() -> dict[str, Any]:
    return {"report": maths_report().model_dump(mode="json"), "claim_id": "k1", "fixture_responses": maths_fixture()}


def test_client_fixtures_are_refused_by_default():
    client = make_client(ServiceSettings(service_token=TOKEN, signing_key=KEY, signing_key_id=KEY_ID))
    r = client.post("/v1/outcomes", json=_outcome_body(), headers=AUTH)
    assert r.status_code == 403 and r.json()["code"] == "E506" and "client fixtures disabled" in r.json()["message"]
    r = client.post("/v1/outcomes", content=b"not even json", headers={**AUTH, "content-type": "application/json"})
    assert r.status_code == 403 and r.json()["code"] == "E506"          # refused before the body is read


def test_client_fixtures_are_taken_when_the_service_allows_them():
    r = make_client(make_settings(allow_client_fixtures=True)).post("/v1/outcomes", json=_outcome_body(), headers=AUTH)
    assert r.status_code == 200 and r.json()["display_status"] == "ENTAILED"


@pytest.mark.parametrize("raw, allowed", [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("false", False), ("", False)])
def test_the_environment_switch(raw, allowed):
    env = {"EPINOIC_SERVICE_TOKEN": TOKEN, "EPINOIC_SIGNING_KEY": KEY.hex(), "EPINOIC_ALLOW_CLIENT_FIXTURES": raw}
    assert ServiceSettings.from_env(env).allow_client_fixtures is allowed


def test_an_unreadable_environment_switch_is_refused():
    with pytest.raises(SettingsError, match="ALLOW_CLIENT_FIXTURES"):
        ServiceSettings.from_env({"EPINOIC_SERVICE_TOKEN": TOKEN, "EPINOIC_SIGNING_KEY": KEY.hex(), "EPINOIC_ALLOW_CLIENT_FIXTURES": "maybe"})


# ------------------------------------------------------------------------------------------------ 5. SEC-5

def _free_symbol_problem() -> dict[str, Any]:
    return _problem(symbols=[{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}, {"name": "b", "sort": "Bool"}],
                    premises=[{"id": "P1", "expr": cmp("gt", V("x"), I(0))}], conclusion={"id": "C", "expr": cmp("gt", V("x"), I(1))})


def test_model_completion_is_server_controlled(client):
    r = client.post("/v1/verify", json={"problem": _free_symbol_problem(), "config": {"model_completion": False}}, headers=AUTH)
    assert r.status_code == 400 and r.json()["code"] == "E100" and "model_completion" in r.json()["message"]


@pytest.mark.parametrize("completion", [True, False])
def test_every_counterexample_value_is_a_literal_in_process(completion):
    r = verify(_free_symbol_problem(), SolverConfig(timeout_ms=4000, memory_max_mb=None, model_completion=completion), signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.COUNTEREXAMPLE
    values = {a.symbol: a.value for a in r.counterexample.assignments}
    assert set(values) == {"x", "y", "b"}
    assert re.fullmatch(r"-?\d+", values["x"]) and re.fullmatch(r"-?\d+", values["y"]) and values["b"] in ("true", "false")
    assert verify_signature(r, KEY)


# ------------------------------------------------------------------------------------------------ 6. SEC-8

@pytest.mark.parametrize("adapter_id", ["..x", "service.app", "x" * 5000, "../../etc", "History-Specialist", "x\n", "unknown-adapter"])
def test_an_unlisted_adapter_id_is_refused_and_imports_nothing(client, monkeypatch, adapter_id):
    imported: list[str] = []
    real = importlib.import_module

    def spy(name: str, *args: Any, **kwargs: Any):
        imported.append(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", spy)
    r = client.post("/v1/outcomes", json={**_outcome_body(), "adapter_id": adapter_id}, headers=AUTH)
    assert r.status_code == 400 and r.json()["code"] == "E100"
    assert not [n for n in imported if n.startswith("epinoic_logic.adapters")]


def test_a_registered_adapter_id_is_taken(client):
    assert {"generic-structured", "history-specialist"} <= app_mod._registered_adapter_ids()
    r = client.post("/v1/outcomes", json={**_outcome_body(), "adapter_id": "generic-structured"}, headers=AUTH)
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------------------------------------ 7. lone surrogates

SURROGATE = "\ud83d"


def test_the_validator_refuses_a_lone_surrogate_as_e100():
    """B27, the validator half: _decode_text refuses the payload as E100 (it raised UnicodeEncodeError before). The full
    in-process result also needs the runner's digest of the unparsed payload to accept it: that file is frozen, so the
    change is handed to the integration step and the strict xfail in tests/engine/test_pack_policies.py stays until then."""
    problem, outcome = parse_and_validate(SURROGATE, DEFAULT_LIMITS)
    assert problem is None and outcome.status is S.INVALID_FORMALIZATION
    assert [(d.code, "lone surrogate" in d.message) for d in outcome.diagnostics] == [("E100", True)]


def test_a_lone_surrogate_in_a_problem_payload_is_e100_over_http(client):
    body = json.dumps({"problem": transitivity_problem(claim_id=SURROGATE)})       # written as the escape \\ud83d
    assert "\\ud83d" in body
    r = client.post("/v1/verify", content=body.encode(), headers={**AUTH, "content-type": "application/json"})
    assert r.status_code == 400 and r.json()["code"] == "E100" and "surrogate" in r.json()["message"]


@pytest.mark.parametrize("route", ["/v1/results/verify-signature", "/v1/results/release-check"])
def test_a_result_holding_a_lone_surrogate_is_e100_not_a_500(client, route):
    signed = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH).json()
    signed["claim_id"] = SURROGATE
    body = {"result": signed} if route.endswith("verify-signature") else {"result": signed, "problem": transitivity_problem()}
    r = client.post(route, content=json.dumps(body).encode(), headers={**AUTH, "content-type": "application/json"})
    assert r.status_code == 400 and r.json()["code"] == "E100"


def test_a_lone_surrogate_in_fixture_responses_is_e100_not_a_500(client):
    body = _outcome_body()
    body["fixture_responses"] = {"k1": '{"problem": "' + SURROGATE + '"}'}
    r = client.post("/v1/outcomes", content=json.dumps(body).encode(), headers={**AUTH, "content-type": "application/json"})
    assert r.status_code == 400 and r.json()["code"] == "E100"


def test_provider_output_holding_a_lone_surrogate_is_a_failed_translation_in_process():
    with pytest.raises(parsing.ProviderOutputError, match="lone surrogate"):
        parsing.parse_json_object('{"problem": "' + SURROGATE + '"}')
    text = "If x > 2 and y > x then y > 2."
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="generic-structured", subject="Mathematics", task_type="worked_solution")
    claim = ClaimRecord(**ids, claim_id="c1", claim_text=text, claim_role="other", proposed_claim_kind="formal_logic")
    report = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), claims=[claim], created_at="2026-10-11T00:00:00Z")
    result = Translator(FixtureTranslationProvider({"c1": '{"problem": "' + SURROGATE + '"}'})).translate(claim, report)
    assert result.problem is None and result.status.value != "TRANSLATED"
    assert any("lone surrogate" in d for d in result.diagnostics)


# ------------------------------------------------------------------------------------------------ 8. SEC-7

@pytest.mark.parametrize("key", ["diagnose", "severity_cap", "argument_rules", "named_diagnostics"])
def test_the_diagnosis_is_not_reachable_over_http(client, key):
    r = client.post("/v1/verify", json={"problem": transitivity_problem(), "config": {key: False}}, headers=AUTH)
    assert r.status_code == 400 and r.json()["code"] == "E100"
    r = client.post("/v1/verify", json={"problem": transitivity_problem(), key: False}, headers=AUTH)
    assert r.status_code == 400 and r.json()["code"] == "E100"


def test_the_service_always_diagnoses_and_its_release_route_refuses_an_undiagnosed_result(client):
    """The tamper and rule-9 cases in process are pinned by tests/contract (test_result_fields, test_release_rules); over
    HTTP a client can neither turn the diagnosis off nor pass an undiagnosed result for release (the route gives the
    rule-9 reason for it, and not for the served result)."""
    problem = transitivity_problem()
    served = client.post("/v1/verify", json={"problem": problem}, headers=AUTH).json()
    assert served["status"] == "ENTAILED" and served["argument_rules"]
    rule9 = "argument diagnosis not computed"
    ok = client.post("/v1/results/release-check", json={"result": served, "problem": problem}, headers=AUTH).json()
    assert not any(rule9 in r for r in ok["reasons"])
    undiagnosed = verify(problem, CFG, signing_key=KEY, key_id=KEY_ID, diagnose=False)
    assert undiagnosed.argument_rules is None and verify_signature(undiagnosed, KEY)
    refused = client.post("/v1/results/release-check", json={"result": undiagnosed.model_dump(mode="json"), "problem": problem}, headers=AUTH).json()
    assert refused["eligible"] is False and any(rule9 in r for r in refused["reasons"])


def test_the_derived_runs_stay_within_their_bounds_on_128_premises():
    """128 premises over 64 symbols (the default limits): a chain a0 -> a1 -> ... -> a63 stated twice, once as
    implications and once as disjunctions, from a writer's assumption a0. Whatever the argument rules derive, they stay
    within 24 derived runs and the total budget, and the result is signed with its diagnosis."""
    n = 64
    symbols = [{"name": f"a{i}", "sort": "Bool"} for i in range(n)]
    premises = [{"id": "A0", "expr": V("a0"), "grounding": {"kind": "assumption"}}]
    premises += [{"id": f"L{i}", "expr": {"op": "implies", "left": V(f"a{i - 1}"), "right": V(f"a{i}")}, "grounding": {"kind": "specialist_inference"}}
                 for i in range(1, n)]
    premises += [{"id": f"D{i}", "expr": {"op": "or", "args": [{"op": "not", "arg": V(f"a{i - 1}")}, V(f"a{i}")]},
                  "grounding": {"kind": "specialist_inference"}} for i in range(1, n + 1) if i < n] + [
                 {"id": "D64", "expr": {"op": "or", "args": [V("a0"), {"op": "not", "arg": V("a0")}]}, "grounding": {"kind": "assumption"}}]
    assert len(premises) == 128
    problem = {"ir_version": "1.0", "problem_id": "chain", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": symbols,
               "premises": premises, "conclusion": {"id": "C", "expr": V(f"a{n - 1}")}}
    start = time.perf_counter()
    r = verify(problem, SolverConfig(timeout_ms=4000, memory_max_mb=None), signing_key=KEY, key_id=KEY_ID)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert r.status is S.ENTAILED and verify_signature(r, KEY) and r.argument_rules is not None
    assert all(len(d.derived_problem_digests) <= MAX_DERIVED_RUNS for d in (r.named_diagnostics or []))
    assert elapsed_ms < TOTAL_BUDGET_MS + 30_000                 # the main run plus at most the derived runs' total budget


# ------------------------------------------------------------------------------------------------ 9. strict config

@pytest.mark.parametrize("config", [{"timeout_ms": True}, {"timeout_ms": "100"}, {"timeout_ms": 100.0}, {"produce_unsat_core": "yes"},
                                    {"produce_unsat_core": 1}, {"random_seed": "0"}])
def test_config_is_validated_strictly(client, config):
    r = client.post("/v1/verify", json={"problem": transitivity_problem(), "config": config}, headers=AUTH)
    assert r.status_code == 400 and r.json()["code"] == "E100"


@pytest.mark.parametrize("field, value", [("advisory_verification_eligibility", "yes"), ("advisory_verification_eligibility", 1)])
def test_the_outcome_routes_report_is_validated_strictly(client, field, value):
    body = _outcome_body()
    body["report"]["claims"][0][field] = value
    r = client.post("/v1/outcomes", json=body, headers=AUTH)
    assert r.status_code == 400 and r.json()["code"] == "E100" and "SpecialistReport" in r.json()["message"]


def test_a_well_typed_config_is_taken(client):
    r = client.post("/v1/verify", json={"problem": transitivity_problem(), "config": {"timeout_ms": 1500, "produce_unsat_core": False}}, headers=AUTH)
    assert r.status_code == 200 and r.json()["solver_config"]["timeout_ms"] == 1500


# ------------------------------------------------------------------------------------------------ 10. formal-robustness-1

C40 = "9" * 40


def _chain(n: int) -> dict[str, Any]:
    symbols = [{"name": "x", "sort": "Int"}] + [{"name": f"y{i}", "sort": "Int"} for i in range(1, n + 1)]
    premises = [{"id": "P0", "expr": cmp("eq", V("x"), I(int(C40)))}]
    prev = "x"
    for i in range(1, n + 1):
        premises.append({"id": f"P{i}", "expr": cmp("eq", V(f"y{i}"), {"op": "mul", "args": [I(int(C40))] * 31 + [V(prev)]})})
        prev = f"y{i}"
    return _problem(symbols=symbols, premises=premises, conclusion={"id": "C", "expr": cmp("lt", V(prev), I(0))})


def test_a_model_value_beyond_the_bound_is_unknown_e401_not_a_cut_value():
    start = time.perf_counter()
    r = verify(_chain(6), CFG, signing_key=KEY, key_id=KEY_ID)
    assert time.perf_counter() - start < 10.0
    assert r.status is S.UNKNOWN and r.counterexample is None and "E401" in _codes(r)
    assert procedures.MODEL_TOO_LARGE_REASON in (r.reason_unknown or "")
    assert verify_signature(r, KEY)


def test_a_model_within_the_bound_is_reported_and_its_extraction_is_timed(monkeypatch):
    calls: list[int] = []
    real = procedures.extract_model

    def counted(*args: Any, **kwargs: Any):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(procedures, "extract_model", counted)
    r = verify(_chain(0), CFG)
    assert r.status is S.COUNTEREXAMPLE and {a.symbol: a.value for a in r.counterexample.assignments} == {"x": C40}
    assert calls == [1]                                          # the consistency precheck built no model
    assert "model" in [t.stage for t in r.timings]
