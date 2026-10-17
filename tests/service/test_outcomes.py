"""End-to-end claim outcomes through the service and the CLI (fixture provider, no network).

These tests need the translation pipeline, outcome composer, fixture provider and
adapter registry, which are built by other work streams; they are skipped until
those modules import.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("epinoic_logic.translate.pipeline")
pytest.importorskip("epinoic_logic.translate.outcome")
pytest.importorskip("epinoic_logic.translate.providers.fixture")
pytest.importorskip("epinoic_logic.adapters.base")

import epinoic_logic.cli as cli  # noqa: E402
from epinoic_logic.engine.provenance import verify_signature  # noqa: E402
from epinoic_logic.engine.results import VerificationResult  # noqa: E402
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text  # noqa: E402

from .conftest import AUTH, KEY, V, cmp, I  # noqa: E402

MATHS_TEXT = "If x > 2 and y > x then y > 2."
ENGLISH_TEXT = "The imagery of the closed door conveys the speaker's isolation."


def _report(subject: str, claim_text: str, **claim_fields: Any) -> SpecialistReport:
    ids = dict(request_id="req-o1", task_id="task-o1", report_id="rep-o1")
    claim = ClaimRecord(**ids, agent_id="generic-structured", subject=subject, task_type="worked_solution", claim_id="k1", claim_text=claim_text, **claim_fields)
    return SpecialistReport(
        **ids, agent_id="generic-structured", subject=subject, task_type="worked_solution",
        original_response=claim_text, response_sha256=sha256_text(claim_text), claims=[claim],
        created_at="2026-10-11T00:00:00Z",
    )


def maths_report() -> SpecialistReport:
    return _report("Mathematics: Analysis and Approaches", MATHS_TEXT, claim_role="other", proposed_claim_kind="formal_logic")


def english_report() -> SpecialistReport:
    return _report("English A: Literature", ENGLISH_TEXT, claim_role="interpretation", proposed_claim_kind="interpretive")


def maths_fixture() -> dict[str, Any]:
    problem = {
        "problem_id": "k1-p1", "request_id": "req-o1", "claim_id": "k1", "query": "entailment",
        "symbols": [{"name": "x", "sort": "Int", "meaning": "x"}, {"name": "y", "sort": "Int", "meaning": "y"}],
        "premises": [
            {"id": "P1", "expr": cmp("gt", V("x"), I(2)), "label": "x > 2", "grounding": {"kind": "arithmetic_fact", "verified": True}},
            {"id": "P2", "expr": cmp("gt", V("y"), V("x")), "label": "y > x", "grounding": {"kind": "arithmetic_fact", "verified": True}},
        ],
        "conclusion": {"id": "C", "expr": cmp("gt", V("y"), I(2)), "label": "y > 2"},
    }
    interpretation = {"reading": "Read as: from x > 2 and y > x it follows that y > 2 over the integers.", "glossary": [{"symbol": "x", "meaning": "x"}, {"symbol": "y", "meaning": "y"}], "ambiguity_flags": []}
    return {"k1": {"problem": problem, "interpretation": interpretation, "ambiguous": False, "unsupported_reason": None}}


def test_outcomes_endpoint_returns_a_signed_entailed_outcome(client):
    payload = {"report": maths_report().model_dump(mode="json"), "claim_id": "k1", "fixture_responses": maths_fixture()}
    r = client.post("/v1/outcomes", json=payload, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["display_status"] == "ENTAILED"
    assert body["translation"]["status"] == "TRANSLATED"
    assert body["translation"]["provider"]["provider_name"] == "fixture"
    verification = VerificationResult.model_validate(body["verification"])
    assert verification.status.value == "ENTAILED" and verify_signature(verification, KEY)
    assert body["summary"] and "ENTAILED" in body["summary"]
    assert body["summary"].rstrip().endswith("advisory.")


def test_outcomes_endpoint_never_calls_the_provider_for_ineligible_claims(client):
    payload = {"report": english_report().model_dump(mode="json"), "claim_id": "k1", "fixture_responses": {}}
    r = client.post("/v1/outcomes", json=payload, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["display_status"] == "NOT_ELIGIBLE" and body["translation"]["status"] == "NOT_ELIGIBLE"
    assert body["verification"] is None and body["translation"]["provider"] is None


def test_outcomes_endpoint_rejects_unknown_claims_and_malformed_reports(client):
    report = maths_report().model_dump(mode="json")
    r = client.post("/v1/outcomes", json={"report": report, "claim_id": "nope", "fixture_responses": {}}, headers=AUTH)
    assert r.status_code == 400 and r.json()["code"] == "E100"
    tampered = {**report, "original_response": "edited after the fact"}
    r = client.post("/v1/outcomes", json={"report": tampered, "claim_id": "k1", "fixture_responses": {}}, headers=AUTH)
    assert r.status_code == 400 and r.json()["code"] == "E100" and "edited" not in r.text


def test_check_report_cli_prints_outcomes_json(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    fixtures_path = tmp_path / "fixtures.json"
    report_path.write_text(json.dumps(maths_report().model_dump(mode="json")), encoding="utf-8")
    fixtures_path.write_text(json.dumps(maths_fixture()), encoding="utf-8")
    rc = cli.main(["check-report", str(report_path), "--fixtures", str(fixtures_path), "--adapter", "generic-structured", "--signing-key-hex", KEY.hex(), "--key-id", "cli-key"])
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert rc == 0, err
    outcomes = json.loads(out)
    assert isinstance(outcomes, list) and len(outcomes) == 1
    assert outcomes[0]["display_status"] == "ENTAILED" and outcomes[0]["claim_id"] == "k1"
    assert verify_signature(VerificationResult.model_validate(outcomes[0]["verification"]), KEY)


@pytest.mark.parametrize("adapter_id", ["english_specialist.parser", "stem_specialist", "base", "markdown", "../x", "history_specialist",
                                        "generic_structured", "HISTORY-SPECIALIST", ""])
def test_outcomes_endpoint_refuses_an_adapter_outside_the_closed_list_before_any_import(client, adapter_id):
    """V3-L7: an ``adapter_id`` outside the closed list (the adapters the package registers on import) is 400 "unknown
    adapter_id", and no module is imported for it: the id is looked up, never turned into a module name."""
    import sys
    before = set(sys.modules)
    report = maths_report().model_dump(mode="json")
    r = client.post("/v1/outcomes", json={"report": report, "claim_id": "k1", "fixture_responses": maths_fixture(), "adapter_id": adapter_id},
                    headers=AUTH)
    assert r.status_code == 400 and "unknown adapter_id" in r.text
    assert not {m for m in set(sys.modules) - before if m.startswith("epinoic_logic.adapters")}


def test_outcomes_endpoint_accepts_each_registered_adapter(client):
    from epinoic_logic.service.app import OUTCOME_ADAPTER_IDS
    from epinoic_logic.adapters.base import registered_ids
    assert OUTCOME_ADAPTER_IDS == set(registered_ids()) == set(cli.ADAPTER_IDS)
    report = maths_report().model_dump(mode="json")
    r = client.post("/v1/outcomes", json={"report": report, "claim_id": "k1", "fixture_responses": maths_fixture(), "adapter_id": "generic-structured"},
                    headers=AUTH)
    assert r.status_code == 200, r.text
