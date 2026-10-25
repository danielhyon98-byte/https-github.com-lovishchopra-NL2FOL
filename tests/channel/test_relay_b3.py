"""E2E B3: a peer-dependent specialist is shown its peer's delivered report and nothing of the router's side, and an
answer that still hands a system check result to the student is named (INT-REQ-017, a warning).

In the end-to-end run the arena's relay file carried the router's receipt of the peer's delivery beside the payload;
hi-e1a read the receipt's (false) formal-check findings and told the student that the Mathematics report's lines "do not
hold" and not to copy them. ``run_arena.relay_peer`` now writes the payload alone to ``relayed/<task>.json`` and the
receipt to ``relayed/<task>.router.json``, which no specialist bundle includes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText

from ..argdiag_cases import load_case
from .dev_case_hub import run_case

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"

HISTORY = {
    "task_id": "hi-z1", "subject": "History", "agent_id": "history-specialist", "task_type": "short_answer", "group": "z1",
    "question": "In one paragraph of no more than 200 words, outline the historical context of London in 1802 for a student "
                "reading a sonnet written that year.",
    "supplied_texts": [],
    "response_text": "London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801. "
                     "Coal smoke from homes and workshops hung over the city for much of the year. "
                     "The Peace of Amiens, signed in March 1802, briefly ended the war with France.",
}
ENGLISH = {
    "task_id": "en-z1", "subject": "English A: Literature", "agent_id": "english-specialist", "task_type": "analytical_paragraph", "group": "z1",
    "peer_of": "hi-z1",
    "question": "Write one analytical paragraph of no more than 200 words on how the History specialist's context changes a reading "
                "of the sonnet's calm. Quote the relayed report exactly.",
    "supplied_texts": [],
    "response_text": "The History specialist's report says that \"Coal smoke from homes and workshops hung over the city for much of the year.\" "
                     "Read against that, the calm of the sonnet is an exception rather than the rule.",
}


@pytest.fixture()
def arena():
    sys.path.insert(0, str(ARENA))
    try:
        import run_arena  # noqa: PLC0415 - the harness lives beside the scripts, not in the package
        yield run_arena
    finally:
        sys.path.remove(str(ARENA))


def test_the_relayed_file_holds_the_delivered_payload_and_no_receipt(arena, tmp_path):
    (tmp_path / "specialists").mkdir()
    for item in (HISTORY, ENGLISH):
        (tmp_path / "specialists" / f"{item['task_id']}.json").write_text(json.dumps(item))
    out = arena.relay_peer(tmp_path, "en-z1")
    shown = json.loads((tmp_path / "relayed" / "en-z1.json").read_text())
    router = json.loads((tmp_path / "relayed" / "en-z1.router.json").read_text())
    assert shown["delivered"] is True and set(shown) == {"task_id", "peer_of", "delivered", "document_id", "payload"}
    assert "peer_receipt" not in shown and "relay" not in shown and "request" not in shown
    assert shown["payload"]["report_id"] == "rep-hi-z1-0" and shown["payload"]["original_response"] == HISTORY["response_text"]
    assert not any(k in json.dumps(shown) for k in ("INT-", "receipt_id", "formal_checks"))   # nothing of the hub's checks
    assert router["peer_receipt"]["status"] in ("ACCEPTED", "ACCEPTED_WITH_FINDINGS") and "findings" in router["peer_receipt"]
    assert router["relay"]["functional"] is True and out["router"] == router
    # what reads the relay still finds the payload
    recorded = arena.load_recorded_relays(tmp_path, arena.load_items(tmp_path / "specialists"))
    assert recorded["en-z1"]["payload"] == shown["payload"]


def _int_req_017(run):
    return [f for f in run.receipt.findings if f.code == "INT-REQ-017"]


def test_an_answer_that_hands_a_check_result_to_the_student_is_named():
    run = run_case("e2e-B4-hi")                                        # hi-e1a: "... do not copy those two lines ..."
    found = _int_req_017(run)
    assert found and all(f.severity == "warning" for f in found)
    assert any("do not copy those" in f.message or "own checks" in f.message for f in found)
    assert all(f.document_ids == ["peer:maa-e1a"] and f.claim_ids for f in found)
    assert run.receipt.status.value == "ACCEPTED_WITH_FINDINGS"        # a warning: delivered, never withheld for it


def test_a_peer_answer_quoting_the_peers_figures_is_not_named():
    case = load_case("e2e-B4-hi")
    start = case["answer"].index("Limit: the Mathematics report")
    end = case["answer"].index("Next step:")
    case["answer"] = case["answer"][:start] + case["answer"][end:]
    assert "5.51 × 10⁷ marks" in case["answer"] and "≈ 1.55 per month" in case["answer"]   # the peer's own figures, quoted
    run = run_case("e2e-B4-hi", case=case)
    assert not _int_req_017(run)


def _english_hub(answer: str, *, with_peer: bool):
    plan = WorkPlan(plan_id="p", request_id="r", task_id="t", subject="English A: Literature", task_type="analytical_paragraph",
                    selected_agent_ids=["history-specialist", "english-specialist"], agent_subjects={"history-specialist": "History"},
                    agent_task_types={"history-specialist": "short_answer"}, allowed_document_ids=["peer:hi"])
    hub = RouterHub(signing_key=b"b3-channel-key-0123456789abcdef0123")
    ch = hub.open_task(plan)
    docs = []
    if with_peer:
        m, _req, _rq = hub.dispatch("t", "history-specialist", HISTORY["question"])
        reply, _rc = hub.receive("t", m.message_id, HISTORY["response_text"], agent_id="history-specialist", report_id="rep-hi")
        rep = SpecialistReport.model_validate(reply.payload)
        ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, rep, in_reply_to=reply.message_id)
        docs = [SuppliedText(document_id="peer:hi", title="History report", author="history-specialist", text=rep.original_response)]
    m, _req, _rq = hub.dispatch("t", "english-specialist", ENGLISH["question"], docs)
    return hub.receive("t", m.message_id, answer, agent_id="english-specialist", report_id="rep-en")[1]


@pytest.mark.parametrize("sentence", [
    "The History report's formal check failed its census figure, so treat it with care.",
    "The engine found that the 1801 figure does not hold.",
    "Its INT-SUBJ-001 finding means the census line is wrong.",
])
def test_each_kind_of_system_result_is_named_on_a_peer_answer(sentence):
    rc = _english_hub(ENGLISH["response_text"] + " " + sentence, with_peer=True)
    assert [f for f in rc.findings if f.code == "INT-REQ-017"]


@pytest.mark.parametrize("answer, with_peer", [
    (ENGLISH["response_text"] + " The steam engine had not yet changed the city's air.", True),              # subject words stay content
    (ENGLISH["response_text"] + " The formal checks and balances of later reform did not yet exist.", True),  # a history phrase
    (ENGLISH["response_text"] + " The speaker's \"formal check\" on her feelings fails at the turn.", True),  # quoted words are the text's
    (ENGLISH["response_text"] + " The engine found that the 1801 figure does not hold.", False),            # no peer: not this rule
])
def test_subject_content_quotations_and_answers_without_a_peer_are_not_named(answer, with_peer):
    rc = _english_hub(answer, with_peer=with_peer)
    assert not [f for f in rc.findings if f.code == "INT-REQ-017"]
