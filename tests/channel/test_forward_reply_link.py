"""A router forward replies to the delivery it carries on (repair round 1, re-run review re-5): with no ``in_reply_to``
the channel ties it to the report's first delivery to the router, and now names the gap (INT-HANDOFF-018, warning), so a
forward cut loose from its delivery is never passed on silently. Control: a forward that names its delivery carries no
such finding; one that names another message is still refused (INT-HANDOFF-013)."""
from __future__ import annotations

from epinoic_logic.branches import RouterHub
from epinoic_logic.integrity import AgentRole
from epinoic_logic.translate.contracts import SpecialistReport

from . import test_peer_exchange as P


def _setup():
    hub = RouterHub(signing_key=P.KEY, config=P.CFG)
    hub.open_task(P.two_subject_plan())
    m, _req, reply, _rc = P.deliver_history(hub)
    return hub.channels[P.TASK], m, reply


def test_a_forward_with_no_reply_link_is_tied_and_named():
    ch, _m, reply = _setup()
    msg, rc = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(reply.payload))
    assert msg is not None and msg.in_reply_to == reply.message_id          # tied to the delivery it carries on
    [f] = [f for f in rc.findings if f.code == "INT-HANDOFF-018"]
    assert f.severity == "warning" and reply.message_id in f.message and reply.message_id in f.message_ids


def test_clean_control_a_forward_that_names_its_delivery_is_not_named():
    ch, _m, reply = _setup()
    msg, rc = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(reply.payload),
                       in_reply_to=reply.message_id)
    assert msg is not None and "INT-HANDOFF-018" not in {f.code for f in rc.findings}


def test_control_a_forward_that_names_another_message_is_still_refused():
    ch, m, reply = _setup()
    msg, rc = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(reply.payload),
                       in_reply_to=m.message_id)
    assert msg is None and "INT-HANDOFF-013" in {f.code for f in rc.findings} and "INT-HANDOFF-018" not in {f.code for f in rc.findings}
