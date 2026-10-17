"""The checks-port request ``epinoic.integration.turn-check.v1``: round trip and the refusal of every out-of-contract
request with its KIT-REQ code."""
from __future__ import annotations

import copy
import json

import pytest

from epinoic_logic.integration.canonical import sha256_text
from epinoic_logic.integration.checks_port import RequestLimits, check_request
from epinoic_logic.integration.errors import IntegrationError
from tests.integration.helpers import answer_envelope, turn_request

LIMITS = RequestLimits(modes=("single", "duplicate"), max_body_bytes=1_000_000, checks_min_ms=3000, checks_max_ms=65000)


def _code(raw, limits=LIMITS, env="sim") -> str:
    with pytest.raises(IntegrationError) as exc:
        check_request(raw, limits, service_env=env)
    return exc.value.code


def _single():
    return turn_request([answer_envelope(1)])


def test_a_single_request_round_trips():
    raw = _single()
    req = check_request(raw, LIMITS, service_env="sim")
    assert req.model_dump(mode="json", by_alias=True) == raw
    assert check_request(json.dumps(raw).encode(), LIMITS, service_env="sim") == req


def test_a_duplicate_request_names_its_agents_slug_a_and_b():
    raw = turn_request([answer_envelope(1, agent_id="history@a"), answer_envelope(2, agent_id="history@b")], mode="duplicate")
    assert [a.agent_id for a in check_request(raw, LIMITS, service_env="sim").answers] == ["history@a", "history@b"]
    raw["answers"][1]["agent_id"] = "history@c"
    assert _code(raw) == "KIT-REQ-001"


def _edited(edit):
    raw = copy.deepcopy(_single())
    edit(raw)
    return raw


@pytest.mark.parametrize("edit,code", [
    (lambda r: r.update(status="checked"), "KIT-REQ-005"),
    (lambda r: r["task"].update(grounding={"verified": True}), "KIT-REQ-005"),
    (lambda r: r.update(schema="epinoic.integration.turn-check.v2"), "KIT-REQ-001"),
    (lambda r: r.update(protocol="epinoic.integration.v2"), "KIT-REQ-001"),
    (lambda r: r.update(mode="combined"), "KIT-REQ-002"),
    (lambda r: r.update(mode="triple"), "KIT-REQ-002"),
    (lambda r: r.update(mode="duplicate"), "KIT-REQ-002"),
    (lambda r: r.update(policy="lenient"), "KIT-REQ-003"),
    (lambda r: r.update(policy={"timeout_ms": 1}), "KIT-REQ-003"),
    (lambda r: r.update(ids={"task_id": "t/../x", "request_id": "a_1"}), "KIT-REQ-004"),
    (lambda r: r.update(ids={"task_id": "t_1"}), "KIT-REQ-004"),
    (lambda r: r.update(budget_ms=1000), "KIT-REQ-007"),
    (lambda r: r.update(budget_ms=600000), "KIT-REQ-007"),
    (lambda r: r.update(budget_ms="30000"), "KIT-REQ-007"),
    (lambda r: r["task"].update(user_text="y" * 49153, user_text_sha256=sha256_text("y" * 49153)), "KIT-REQ-006"),
    (lambda r: r["task"].update(user_text_sha256="0" * 64), "KIT-REQ-001"),
    (lambda r: r["task"].update(slug="physics", subject="Physics"), "KIT-REQ-015"),
    (lambda r: r["task"].update(route="english", slug="english-a-literature", subject="English A: Literature") or r["answers"][0].update(agent_id="english-a-literature"), "KIT-REQ-015"),
    (lambda r: r["task"].update(subject="Geography"), "KIT-REQ-015"),
    (lambda r: r["answers"][0].update(agent_id="physics"), "KIT-REQ-001"),
    (lambda r: r["answers"][0]["log"].update(outcome="gate_failed"), "KIT-REQ-012"),
    (lambda r: r["answers"][0]["runtime"].update(schema="epinoic.specialist-turn-result.v9"), "KIT-REQ-010"),
    (lambda r: r["answers"][0].update(answer="changed"), "KIT-REQ-014"),
    (lambda r: r.update(extra=1), "KIT-REQ-001"),
    (lambda r: r.update(budget_ms=3.5e4), "KIT-REQ-001"),
])
def test_every_out_of_contract_request_is_refused_with_its_code(edit, code):
    assert _code(_edited(edit)) == code


def test_the_english_route_maps_only_in_the_sim_environment():
    raw = _edited(lambda r: r["task"].update(route="english", slug="english-a-literature", subject="English A: Literature"))
    raw["answers"][0] = answer_envelope(1, agent_id="english-a-literature")
    raw["answers"][0]["log"]["provenance"]["slug"] = "english-a-literature"
    assert _code(raw, env="development") == "KIT-REQ-015"
    assert check_request(raw, LIMITS, service_env="sim").task.slug == "english-a-literature"


def test_an_oversized_body_and_non_json_are_refused_before_parsing():
    assert _code(b"{" + b" " * 1_000_001 + b"}") == "KIT-REQ-006"
    assert _code(b'{"schema": NaN}') == "KIT-REQ-001"
    assert _code("[]") == "KIT-REQ-001"
