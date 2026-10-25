"""A report or a synthesis handed to the channel as a mapping (JSON as received) is validated strictly, as the IR and the
service's report route are: "yes" is no boolean and "1" no integer (security hardening handed over by the evidence-family
fixes: the report and synthesis mappings of ``channel/bus.py``). The mapping is read as the JSON it is, so strings stay
valid for enumerations and timestamps; a mapping with a coerced value is REJECTED with INT-REQ-009 naming the field, and
never delivered. A mapping with the right types is delivered as before."""
from __future__ import annotations

import pytest

from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.integrity import AgentRole
from epinoic_logic.translate.contracts import SpecialistReport

from .test_lens_round_d import TASK, delivered, history_hub


def _report_mapping(rep: SpecialistReport, **claim_over) -> dict:
    data = rep.model_dump(mode="json", exclude_none=True)
    data["claims"] = [{**data["claims"][0], **claim_over}, *data["claims"][1:]]
    return data


@pytest.mark.parametrize("value", ["yes", "true", 1])
def test_a_report_mapping_with_a_coerced_boolean_is_refused_on_the_relay_path(value):
    hub, ch = history_hub("english-specialist")
    _m, reply, rep = delivered(hub, ch)
    msg, rc = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST,
                       _report_mapping(rep, advisory_verification_eligibility=value), in_reply_to=reply.message_id)
    assert msg is None and rc.status is TransmissionStatus.REJECTED
    err = next(f for f in rc.findings if f.code == "INT-REQ-009")
    assert "advisory_verification_eligibility" in err.message


def test_control_the_report_mapping_as_delivered_is_relayed():
    """Control: the delivered report's own mapping (every value of its JSON type) is forwarded as before."""
    hub, ch = history_hub("english-specialist")
    _m, reply, rep = delivered(hub, ch)
    msg, rc = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, _report_mapping(rep), in_reply_to=reply.message_id)
    assert msg is not None and rc.status is not TransmissionStatus.REJECTED and "INT-REQ-009" not in {f.code for f in rc.findings}


def test_a_report_mapping_with_a_coerced_boolean_is_refused_as_a_response():
    hub, ch = history_hub()
    _m, _reply, rep = delivered(hub, ch)
    m, _req, _rq = hub.dispatch(TASK, rep.agent_id, "Explain the causes of the 1929 crash in one more paragraph.")
    again = {**_report_mapping(rep, advisory_verification_eligibility="yes"), "report_id": "r2"}
    again["claims"] = [{**c, "report_id": "r2"} for c in again["claims"]]
    reply, rc = hub.receive(TASK, m.message_id, again)
    assert reply is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in {f.code for f in rc.findings}


def test_control_the_same_response_mapping_with_a_boolean_is_delivered():
    hub, ch = history_hub()
    _m, _reply, rep = delivered(hub, ch)
    m, _req, _rq = hub.dispatch(TASK, rep.agent_id, "Explain the causes of the 1929 crash in one more paragraph.")
    again = {**_report_mapping(rep, advisory_verification_eligibility=True), "report_id": "r2"}
    again["claims"] = [{**c, "report_id": "r2"} for c in again["claims"]]
    reply, rc = hub.receive(TASK, m.message_id, again)
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED and "INT-REQ-009" not in {f.code for f in rc.findings}
