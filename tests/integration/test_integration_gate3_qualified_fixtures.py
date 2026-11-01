"""Integration gate 3, handoff fixer: the kit's fixture provider serves the hub's agent-qualified claim ids.

Since integration gate 3 the History and English parsers qualify a report's claim ids with its agent when a report of
another agent on the task already holds them (the STEM parsers since integration gate 1). In the checks port's
``duplicate`` mode the second instance of one specialist is such a report ('h1.1@history-specialist-b-cc7267dc' for
'history@b'), and the kit's fixture provider (``integration.verifier.FixtureCorpus``) served a fixture by the bare claim id
only: the second instance's claims got no outcome (INT-REQ-006), so a duplicate-mode History turn was refused as incomplete
(KIT-DL-011; ``tests/integration/test_turn_checker.py::test_duplicate_mode_delivers_the_answer_the_overseer_chose``), and so,
unnoticed since gate 1, were the qualified claims of a second Physics instance. The provider now serves a fixture recorded
under the other form of the report's own claim id, as ``scripts/arena/run_arena.py`` serves it (``other_id_form``,
``fixture_for_claim``, ``qualification_tag``), and only for the report's own agent: the kit's fixture verifier and the arena
still serve the same fixtures to the same claims (PROTOCOL.md section 14.1).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

from epinoic_logic.integration import verifier as V
from epinoic_logic.translate.contracts import SpecialistReport

from tests.integration.helpers import RecordingPort
import tests.integration.test_turn_checker as T

ROOT = Path(__file__).resolve().parents[2]
ARENA = ROOT / "scripts" / "arena"


@pytest.fixture(scope="module")
def ra():
    sys.path.insert(0, str(ARENA))
    import run_arena
    return run_arena


def test_the_kits_id_forms_are_the_arenas(ra):
    rng = random.Random(17)
    ids = ["h1.1", "p1-point", "s1.2", "m3.4", "g1.1@economics-specialist", "h.tail", "s.tail@physics-specialist", "h1.1@x@y", "", "@"]
    tags = [None, "history-specialist", "physics-specialist", "history-specialist-b-cc7267dc", "economics-specialist"]
    for _ in range(4000):
        cid = rng.choice(ids)
        tag = rng.choice(tags)
        if rng.random() < 0.5 and tag:
            cid = cid + "@" + tag
        assert V.other_id_form(cid, tag) == ra.other_id_form(cid, tag), (cid, tag)
    fixtures = [{"problem": {"claim_id": "h1.1", "request_id": "req-x"}, "interpretation": {}}, {"problem": {"claim_id": "h1.2"}},
                json.dumps({"problem": {"claim_id": "h1.1"}}), "```json\n" + json.dumps({"problem": {"claim_id": "h1.1"}}) + "\n```", "not json", 7]
    for value in fixtures:
        assert V.fixture_for_claim(value, "h1.1", "h1.1@history-specialist") == ra.fixture_for_claim(value, "h1.1", "h1.1@history-specialist"), value
    for subject, agent in (("History", "history-specialist@b"), ("English A: Literature", "english-a-literature-specialist"), ("Physics", "physics-specialist@b"),
                           ("Economics", "economics-specialist"), ("Geography", "geography-specialist")):
        report = SpecialistReport.model_validate(_report(subject, agent))
        assert V.qualification_tag(report) == ra.qualification_tag({"subject": subject, "agent_id": agent}), subject


def _report(subject: str, agent: str) -> dict:
    from epinoic_logic.translate.contracts import sha256_text
    text = "x"
    return {"report_id": "r", "request_id": "q", "task_id": "t", "agent_id": agent, "subject": subject, "task_type": "short_answer",
            "original_response": text, "response_sha256": sha256_text(text), "claims": [], "created_at": "2026-11-01T00:00:00Z"}


@pytest.mark.parametrize("names,slug", [(["hi-s1", "hi-s3"], "history"), (["ph-s1", "ph-s2"], "physics")])
def test_a_duplicate_mode_turn_serves_the_second_instances_qualified_claims(names, slug):
    rt, port = T._checker(RecordingPort(representative=1))
    req, _envs = T._request(rt, names, mode="duplicate")
    verdict = rt.checker.check(req)
    (first, rc1), (second, rc2) = port.replies
    assert first is not None and second is not None
    first_ids = [c["claim_id"] for c in first.payload["claims"]]
    second_ids = [c["claim_id"] for c in second.payload["claims"]]
    assert all("@" not in i for i in first_ids) and all("@" in i for i in second_ids), (first_ids, second_ids)
    # every claim the corpus holds a fixture for got an outcome, under either form of its id; none is left NOT_ATTEMPTED
    for rc in (rc1, rc2):
        assert "INT-REQ-006" not in {f.code for f in rc.findings}, [(f.code, f.message[:160]) for f in rc.findings]
    served = {o.claim_id for o in rc2.outcomes}
    assert served and served <= set(second_ids)
    if slug == "history":  # the clean pair: the overseer's choice is delivered
        assert verdict["delivery"]["decision"] == "deliver" and verdict["delivery"]["deliverable"]["agent_id"] == "history@b"
    else:  # ph-s2 holds a wrong step: refused on the engine's finding, never as incomplete
        assert "KIT-DL-011" not in verdict["delivery"]["reasons"], verdict["delivery"]


def test_control_a_fixture_is_never_served_under_another_agents_tag():
    corpus = V.FixtureCorpus({"a" * 64: "item"}, {"item": {"claims": {"h1.1@other-agent": {"problem": {"claim_id": "h1.1@other-agent"}}},
                                                           "claim_text_sha256": {"h1.1@other-agent": "0" * 64}}})
    fn, _provider = corpus.verifier_for("a" * 64, config=None, signing_key=b"k" * 32)

    class _Claim:
        claim_id = "h1.1@history-specialist"

    report = SpecialistReport.model_validate(_report("History", "history-specialist"))
    assert fn(_Claim(), report) is None  # neither form of this agent's id is recorded: no outcome, as the arena serves none
    assert V.other_id_form("h1.1@other-agent", V.qualification_tag(report)) is None
