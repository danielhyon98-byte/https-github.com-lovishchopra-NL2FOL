"""Re-run review finding robustness-and-contracts-3: RouterHub.dispatch raised into the router (ValidationError, TypeError,
AttributeError) for an empty or blank request, one over 400,000 characters, a None or int request, a None sender or
recipient, and a task or agent id holding a lone surrogate, although the hub promises that nothing raises into the router.
Each such call now gets a REJECTED receipt naming why, nothing is sent and nothing is registered. The same holds for the
hub's other entry points (receive, receipts) on malformed calls. These are checks on the call's shape only."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText

KEY = b"rerun-review-hub-key-0123456789abc"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
AGENT = "history-specialist"
GOOD = "Explain the causes of the 1929 crash."
ANSWER = "The crash of 1929 followed speculative excess. Margin buying had inflated prices for years."


def hub(agents=(AGENT,)) -> RouterHub:
    h = RouterHub(signing_key=KEY, config=CFG)
    h.open_task(WorkPlan(plan_id="pl", request_id="rq", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=list(agents)))
    return h


BAD_DISPATCH = {
    "empty request": (("t", AGENT, ""), {}, "empty"),
    "blank request": (("t", AGENT, "   \n\t"), {}, "blank"),
    "request over the bound": (("t", AGENT, "Explain the crash. " * 30000), {}, "570,000 characters"),
    "None request": (("t", AGENT, None), {}, "None, not text"),
    "int request": (("t", AGENT, 5), {}, "type int"),
    "None recipient": (("t", None, GOOD), {}, "recipient agent id is None"),
    "None sender": (("t", AGENT, GOOD), {"from_agent_id": None}, "sender agent id is None"),
    "recipient with a lone surrogate": (("t", "\ud83d", GOOD), {}, "surrogate"),
    "recipient over 128 characters": (("t", "a" * 300, GOOD), {}, "300 characters"),
    "supplied texts that are not a list": (("t", AGENT, GOOD, None), {}, "supplied texts are None"),
    "supplied texts that are not records": (("t", AGENT, GOOD, [1, 2]), {}, "not SuppliedText"),
    "too many supplied texts": (("t", AGENT, GOOD, [SuppliedText(document_id=f"d{i}", text="x") for i in range(17)]), {}, "17 supplied texts"),
}


@pytest.mark.parametrize("name", sorted(BAD_DISPATCH))
def test_a_call_outside_the_request_contract_is_rejected_not_raised(name: str):
    args, kwargs, why = BAD_DISPATCH[name]
    h = hub()
    channel = h.channels["t"]
    message, request, receipt = h.dispatch(*args, **kwargs)
    assert message is None and receipt.status is TransmissionStatus.REJECTED
    assert [f.code for f in receipt.findings] == ["INT-REQ-009"] and why in receipt.findings[0].message, receipt.findings[0].message
    assert channel.requests == {} and h.receipts("t") == [receipt]
    assert request.items == [] and request.constraints == [] and request.supplied_texts == []  # the placeholder carries none of the input
    # the channel is unharmed: the next well-formed request is carried as before
    message2, _request2, receipt2 = h.dispatch("t", AGENT, GOOD)
    assert message2 is not None and receipt2.status is TransmissionStatus.ACCEPTED and len(channel.requests) == 1


def test_a_well_formed_request_is_carried_unchanged():
    """Control."""
    h = hub()
    message, request, receipt = h.dispatch("t", AGENT, GOOD)
    assert message is not None and receipt.status is TransmissionStatus.ACCEPTED and receipt.findings == []
    assert request.user_input == GOOD and request.items


def test_a_request_the_channel_cannot_build_is_rejected_not_raised():
    """A text whose items exceed the channel's own bound (64 per request) is refused by the hub if the channel raises,
    or carried if the channel bounds it itself; either way the router gets a receipt."""
    h = hub()
    text = " ".join(f"Explain cause number {i} of the crash." for i in range(80))
    message, _request, receipt = h.dispatch("t", AGENT, text)
    assert receipt.status in (TransmissionStatus.REJECTED, TransmissionStatus.ACCEPTED, TransmissionStatus.ACCEPTED_WITH_FINDINGS)
    assert (message is None) is (receipt.status is TransmissionStatus.REJECTED)


def test_an_unopened_task_with_a_lone_surrogate_gets_its_receipt():
    h = hub()
    message, request, receipt = h.dispatch("\ud83d", AGENT, GOOD)
    assert message is None and receipt.status is TransmissionStatus.REJECTED and [f.code for f in receipt.findings] == ["INT-HANDOFF-001"]
    assert h.receipts("\ud83d") == [receipt] and request.to_agent_id == AGENT


def test_an_unopened_task_with_a_malformed_call_names_both_faults():
    h = hub()
    message, _request, receipt = h.dispatch("no-such-task", AGENT, "")
    assert message is None and [f.code for f in receipt.findings] == ["INT-HANDOFF-001", "INT-REQ-009"]
    assert "no-such-task" in receipt.findings[0].message and h.receipts("no-such-task") == [receipt]


BAD_RECEIVE = {
    "no request message id": lambda m: ("t", None, ANSWER, dict(agent_id=AGENT, report_id="r1")),
    "an int request message id": lambda m: ("t", 5, ANSWER, dict(agent_id=AGENT, report_id="r1")),
    "an int agent id": lambda m: ("t", m.message_id, ANSWER, dict(agent_id=5, report_id="r1")),
    "an agent id over 128 characters": lambda m: ("t", m.message_id, ANSWER, dict(agent_id="a" * 300, report_id="r1")),
    "an unopened task with a lone surrogate": lambda m: ("\ud83d", m.message_id, ANSWER, dict(agent_id=AGENT, report_id="r1")),
    "an unopened task and an agent id with a lone surrogate": lambda m: ("nope", m.message_id, ANSWER, dict(agent_id="\ud83d", report_id="r1")),
}


@pytest.mark.parametrize("name", sorted(BAD_RECEIVE))
def test_a_malformed_reply_is_rejected_not_raised(name: str):
    h = hub()
    message, _request, _receipt = h.dispatch("t", AGENT, GOOD)
    task, request_message_id, payload, kwargs = BAD_RECEIVE[name](message)
    reply, receipt = h.receive(task, request_message_id, payload, **kwargs)
    assert reply is None and receipt.status is TransmissionStatus.REJECTED and receipt.findings
    assert h.channels["t"].transmitted_reports == {}
    if name in ("an int agent id", "an agent id over 128 characters"):  # refused by the hub itself, before the channel
        assert "INT-REQ-009" in [f.code for f in receipt.findings]


def test_a_long_agent_id_is_never_cut_into_another_agents_id():
    """An id is refused, not shortened: 200 characters of 'a' never deliver as the agent of 128 'a's the plan selected."""
    plan_agent = "a" * 128
    h = hub(agents=(plan_agent,))
    message, _request, _receipt = h.dispatch("t", plan_agent, GOOD)
    reply, receipt = h.receive("t", message.message_id, ANSWER, agent_id="a" * 200, report_id="r1")
    assert reply is None and receipt.status is TransmissionStatus.REJECTED
    reply2, receipt2 = h.receive("t", message.message_id, ANSWER, agent_id=plan_agent, report_id="r1")
    assert reply2 is not None and receipt2.status is not TransmissionStatus.REJECTED  # control: the agent itself is carried


def test_a_well_formed_reply_is_delivered_unchanged():
    """Control."""
    h = hub()
    message, _request, _receipt = h.dispatch("t", AGENT, GOOD)
    reply, receipt = h.receive("t", message.message_id, ANSWER, agent_id=AGENT, report_id="r1")
    assert reply is not None and receipt.status is not TransmissionStatus.REJECTED


@pytest.mark.parametrize("task_id", [["t"], None, 5, "never-seen"])
def test_receipts_never_raises(task_id):
    assert hub().receipts(task_id) == []
