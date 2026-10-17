"""The overseer port ``epinoic.integration.overseer-port.v1``: round trips of its messages and the refusal of every
out-of-contract message with a KIT-OP code. Agent codes never affect a clearance; PENDING is never actable; a FINAL audit
carries both scope statements verbatim and is signed under overseer-audit; a delivery decision names a deliverable that
is one of the call's answers."""
from __future__ import annotations

import copy

import pytest

from epinoic_logic.integration import overseer_port as O
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.protocol import PROTOCOL, dump
from tests.integration.helpers import RecordingPort, hello

TASK, MSG, RECEIPT = "t_" + "0" * 31 + "1", "m1", "e5" * 32


def _code(fn) -> str:
    with pytest.raises(IntegrationError) as exc:
        fn()
    return exc.value.code


def clearance(**c):
    d = {"schema": "epinoic.integration.overseer-clearance.v1", "protocol": PROTOCOL, "task_id": TASK, "message_id": MSG,
         "receipt_sha256": RECEIPT, "state": "AUDIT_PASSED", "may_act": True, "error_codes": [], "waited_ms": 0}
    d.update(c)
    return d


def final(**c):
    d = RecordingPort().close(None, TASK)
    d.update(c)
    return d


def delivery(**c):
    d = {"schema": "epinoic.integration.overseer-delivery.v1", "protocol": PROTOCOL, "task_id": TASK, "kind": "consolidation", "allowed": True,
         "refusal": None, "final_audit_id": f"audit-{TASK}", "consolidation": {"id": "cons-1", "status": "CONSOLIDATED", "basis": "single"},
         "deliverable": {"agent_id": "history", "message_id": "m2", "answer_sha256": "f6" * 32}}
    d.update(c)
    return d


ANSWERS = [("history", "m2", "f6" * 32)]


def test_round_trips():
    assert dump(O.check_hello(hello())) == hello()
    assert dump(O.check_clearance(clearance(), task_id=TASK, message_id=MSG, receipt_sha256=RECEIPT)) == clearance()
    assert dump(O.check_final_audit(final(), task_id=TASK)) == final()
    assert dump(O.check_delivery(delivery(), task_id=TASK, final_audit_id=f"audit-{TASK}", answers=ANSWERS)) == delivery()
    ticket = {"schema": "epinoic.integration.overseer-review-ticket.v1", "protocol": PROTOCOL, "ticket_id": "k1", "task_id": TASK,
              "queued": True, "dropped": False, "plan": {"origin": "floor", "plan_id": "floor-1", "refusal": None}}
    assert dump(O.check_review_ticket(ticket, task_id=TASK)) == ticket


@pytest.mark.parametrize("h,code", [
    (hello(port_version="2.0"), "KIT-OP-002"), (hello(pack_digests=[]), "KIT-OP-003"), (hello(pack_digests=["not-a-digest"]), "KIT-OP-003"),
    (hello(replay_mode="inline"), "KIT-OP-004"), (hello(inline_final_release=True), "KIT-OP-005"),
    (hello(key_ids=["overseer-run"]), "KIT-OP-012"), (hello(max_pending_wait_ms=1000), "KIT-OP-001"), (hello(extra=1), "KIT-OP-001"),
    ("not json", "KIT-OP-001"),
])
def test_hellos_out_of_contract(h, code):
    assert _code(lambda: O.check_hello(h)) == code


@pytest.mark.parametrize("c,code", [
    (clearance(state="AUDIT_MAYBE"), "KIT-OP-006"),
    (clearance(error_codes=["OVS-AGENT-001"]), "KIT-OP-008"),
    (clearance(state="AUDIT_PENDING", may_act=True), "KIT-OP-007"),
    (clearance(state="AUDIT_FAILED", may_act=True), "KIT-OP-007"),
    (clearance(error_codes=["OVS-FID-003"], may_act=True), "KIT-OP-007"),
    (clearance(waited_ms=251), "KIT-OP-001"),
    (clearance(message_id="m-other"), "KIT-OP-010"),
    (clearance(receipt_sha256="0" * 64), "KIT-OP-010"),
])
def test_clearances_out_of_contract(c, code):
    assert _code(lambda: O.check_clearance(c, task_id=TASK, message_id=MSG, receipt_sha256=RECEIPT)) == code


def test_a_pending_or_failed_clearance_in_contract_is_never_actable():
    for state in ("AUDIT_PENDING", "AUDIT_FAILED"):
        assert O.check_clearance(clearance(state=state, may_act=False), task_id=TASK, message_id=MSG, receipt_sha256=RECEIPT).may_act is False


@pytest.mark.parametrize("a,code", [
    (final(scope_statement="Results are true."), "KIT-OP-009"),
    (final(audit_scope_statement=None), "KIT-OP-009"),
    (final(signature={"alg": "hmac-sha256", "key_id": "overseer-run", "value": "ab" * 32}), "KIT-OP-012"),
    (final(signature=None), "KIT-OP-012"),
    (final(state="AUDIT_GREAT"), "KIT-OP-006"),
    (final(error_codes=["OVS-AGENT-002"]), "KIT-OP-008"),
    (final(task_id="t_other"), "KIT-OP-010"),
    (final(error_codes=["OVS-RES-001"]), "KIT-OP-011"),
    (final(scope="BATCH"), "KIT-OP-001"),
])
def test_final_audits_out_of_contract(a, code):
    assert _code(lambda: O.check_final_audit(a, task_id=TASK)) == code


@pytest.mark.parametrize("d,code", [
    (delivery(task_id="t_other"), "KIT-OP-010"),
    (delivery(final_audit_id="audit-old"), "KIT-OP-010"),
    (delivery(refusal="stale"), "KIT-OP-011"),
    (delivery(allowed=False), "KIT-OP-011"),
    (delivery(deliverable=None), "KIT-OP-011"),
    (delivery(consolidation=None), "KIT-OP-011"),
    (delivery(consolidation={"id": "c", "status": "CONFLICTING", "basis": "single"}), "KIT-OP-011"),
    (delivery(kind="release"), "KIT-OP-011"),
    (delivery(deliverable={"agent_id": "history", "message_id": "m-forged", "answer_sha256": "f6" * 32}), "KIT-OP-010"),
    (delivery(deliverable={"agent_id": "history", "message_id": "m2", "answer_sha256": "00" * 32}), "KIT-OP-010"),
    (delivery(refusal="because", allowed=False, deliverable=None), "KIT-OP-001"),
])
def test_delivery_decisions_out_of_contract(d, code):
    assert _code(lambda: O.check_delivery(d, task_id=TASK, final_audit_id=f"audit-{TASK}", answers=ANSWERS)) == code


def test_a_refused_delivery_in_contract_names_its_refusal():
    d = O.check_delivery(delivery(allowed=False, refusal="custody_failed", deliverable=None), task_id=TASK, final_audit_id=f"audit-{TASK}", answers=ANSWERS)
    assert (d.allowed, d.refusal) == (False, "custody_failed")


def test_a_review_ticket_is_queued_or_dropped_never_both():
    t = {"schema": "epinoic.integration.overseer-review-ticket.v1", "protocol": PROTOCOL, "ticket_id": "k1", "task_id": TASK,
         "queued": True, "dropped": True, "plan": {"origin": "router", "plan_id": "p", "refusal": None}}
    assert _code(lambda: O.check_review_ticket(t, task_id=TASK)) == "KIT-OP-011"
    assert _code(lambda: O.check_review_ticket({**t, "dropped": False, "plan": {"origin": "router", "plan_id": "p", "refusal": "KIT-XX-1"}}, task_id=TASK)) == "KIT-OP-001"


def test_load_port_refuses_anything_but_a_connectable_adapter():
    for spec in ("", "not a module", "epinoic_overseer_not_installed_here.port"):
        assert _code(lambda: O.load_port(spec, {})) == "KIT-HS-007"
