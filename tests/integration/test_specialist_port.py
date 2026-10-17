"""The specialist port on real runtime outputs (agents repository v0.1.0, the website's vendored v0.2.0) and on the
website's own ChatResult shapes: the envelope wraps the runtime's answer without changing it, and every other shape is
refused with its named code, never coerced."""
from __future__ import annotations

import copy

import pytest

from epinoic_logic.integration.canonical import sha256_json, sha256_text
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.specialist_port import check_answer, envelope_for, log_projection
from tests.integration.helpers import answer_envelope, runtime_fixture, website_fixture


def _code(fn) -> str:
    with pytest.raises(IntegrationError) as exc:
        fn()
    return exc.value.code


@pytest.mark.parametrize("version", [1, 2])
def test_an_answer_is_wrapped_unchanged_and_round_trips(version):
    rec = runtime_fixture(version)["answer"]
    env = envelope_for(rec["result"], rec["log"], agent_id="history")
    assert env["answer"] == rec["result"]["answer"]
    assert env["answer_sha256"] == sha256_text(rec["result"]["answer"])
    assert env["result_sha256"] == sha256_json(rec["result"])
    assert env["runtime"] == {"schema": rec["result"]["schema"], "contract_version": rec["result"]["contractVersion"]}
    assert "turn" not in env["log"] and "usage" not in env["log"]
    assert env["log"] == log_projection(rec["log"])
    assert env["log"]["provenance"]["claims"] is None
    assert check_answer(env, slug="history").model_dump(mode="json", by_alias=True) == env


@pytest.mark.parametrize("version,case", [(1, "refusal"), (1, "declined"), (1, "incomplete"), (1, "gate_failed"),
                                          (2, "declined"), (2, "gate_unverifiable"), (2, "incomplete")])
def test_every_runtime_outcome_other_than_answer_is_never_enveloped(version, case):
    rec = runtime_fixture(version)[case]
    assert rec["result"]["outcome"] != "answer" and rec["result"]["answer"] is None
    assert _code(lambda: envelope_for(rec["result"], rec["log"], agent_id="history")) == "KIT-REQ-012"


def test_the_website_chat_results_are_not_specialist_results():
    for scenario, out in website_fixture().items():
        result = out["result"]
        assert _code(lambda: envelope_for(result, {}, agent_id="history")) == "KIT-REQ-010", scenario
    mock = website_fixture()["answer-history"]["result"]
    assert mock["review"] == "passed"  # the mock's label is never an actual review, and never a specialist result


def _env(version=1):
    return copy.deepcopy(answer_envelope(version))


@pytest.mark.parametrize("edit,code", [
    (lambda e: e.update(status="verified"), "KIT-REQ-005"),
    (lambda e: e.update(verified=True), "KIT-REQ-005"),
    (lambda e: e.update(schema="epinoic.integration.specialist-answer.v2"), "KIT-REQ-001"),
    (lambda e: e["runtime"].update(schema="epinoic.specialist-turn-result.v3"), "KIT-REQ-010"),
    (lambda e: e["runtime"].update(contract_version="epinoic.specialist-runtime.v0.2.0"), "KIT-REQ-011"),
    (lambda e: e["log"].update(schema="epinoic.specialist-turn-log.v2"), "KIT-REQ-010"),
    (lambda e: e["log"].update(contractVersion="epinoic.specialist-runtime.v0.2.0"), "KIT-REQ-011"),
    (lambda e: e["log"].update(turn={"conversationId": "c"}), "KIT-REQ-001"),
    (lambda e: e["log"].update(usage={"inputTokens": 1}), "KIT-REQ-001"),
    (lambda e: e["log"].update(outcome="refusal"), "KIT-REQ-012"),
    (lambda e: e["log"].update(answerPresent=False), "KIT-REQ-012"),
    (lambda e: e["log"]["gate"].update(status="unverifiable"), "KIT-REQ-013"),
    (lambda e: e["log"]["provenance"].update(claims=[{"claim": "self-made"}]), "KIT-REQ-011"),
    (lambda e: e.update(answer="x" * 49153), "KIT-REQ-006"),
    (lambda e: e.update(answer=e["answer"] + " (edited after the runtime)"), "KIT-REQ-014"),
    (lambda e: e.update(answer_sha256="0" * 64), "KIT-REQ-014"),
    (lambda e: e.update(agent_id="History Specialist"), "KIT-REQ-001"),
    (lambda e: e.update(extra=1), "KIT-REQ-001"),
    (lambda e: e.update(result_sha256="not-a-digest"), "KIT-REQ-001"),
])
def test_every_out_of_contract_envelope_is_refused_with_its_code(edit, code):
    e = _env(1)
    edit(e)
    assert _code(lambda: check_answer(e, slug="history")) == code


def test_the_slug_must_be_the_subject_maps():
    assert _code(lambda: check_answer(_env(2), slug="mathematics-aa")) == "KIT-REQ-015"
    assert check_answer(_env(2), slug=None).agent_id == "history"


def test_a_v2_log_with_v1_runtime_pair_is_refused_as_another_contract():
    e = _env(2)
    e["runtime"]["contract_version"] = "epinoic.specialist-runtime.v0.1.0"
    assert _code(lambda: check_answer(e, slug="history")) == "KIT-REQ-011"
