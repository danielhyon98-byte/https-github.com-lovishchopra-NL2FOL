"""The c3d follow-up (push check of af6dfe04 and the c3c run's open items), the overseer's side (expected values fixed here):

* every release path reads the same self-report (rule ``self-certification-gate``): the task audit's OVS-FID-005 and OVS-FID-009
  (any severity, :func:`epinoic_overseer.meta_notes.audit_self_reports`) are read by the router's documented decision
  (``consolidate.delivery_decision`` through ``self_report_at_delivery``) and by the synthesis release (``policy.release_decision``
  through ``_synthesis_self_report``) as the delivery policy's fallback already read them. The c3c run found the router allowing an
  answer the fallback withheld by OVS-FID-009 (tab-separated letters); the same split held for a structured report whose content
  claim carries the contract's advisory self-report fields, reproduced here end to end on History, Geography and Spanish B;
* the reasons the new reads give map onto the port's closed refusals (``not_deliverable``), never ``internal_error``;
* a task audit the decision cannot find is a refusal (fail closed).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from epinoic_logic.api.branches import RouterHub
from epinoic_logic.api.integrity import WorkPlan
from epinoic_logic.api.translate import ClaimRecord, SpecialistReport, sha256_text
from epinoic_overseer.consolidate import delivery_decision, self_report_at_delivery
from epinoic_overseer.delivery_policy import SELF_REPORT_AUDIT_CODES, DeliveryPolicy
from epinoic_overseer.meta_notes import SELF_REPORT_AUDIT_CODES as META_AUDIT_CODES, audit_self_reports
from epinoic_overseer.policy import _synthesis_self_report
from epinoic_overseer.port import refusal_label

from .conftest import CFG, KEY, make_auditor
from .delivery_support import FakeClock

CREATED = "2026-11-21T00:00:00Z"
#: (subject, agent, task type, two sentences of correct work)
STRUCTURED = [
    ("History", "history-specialist", "short_answer",
     ("The Treaty of Versailles was signed in 1919.", "It imposed reparations on Germany, which fuelled resentment in the 1920s.")),
    ("Geography", "geography-specialist", "short_answer",
     ("Urban heat islands raise city temperatures above the surrounding countryside.", "Dark surfaces absorb more solar radiation.")),
    ("Spanish B", "spanish-b-specialist", "short_answer",
     ("La ciudad recibe muchos turistas en verano.", "Los vecinos piden más espacios verdes.")),
]
IDS = [s[0] for s in STRUCTURED]
ADVISORY = [{"advisory_verification_eligibility": True}, {"advisory_verification_status": "verified"}]


def _report(subject: str, agent: str, task_type: str, sentences, field: dict) -> SpecialistReport:
    ids = dict(request_id="r-c3d", task_id="t-c3d", subject=subject, task_type=task_type)
    text = " ".join(sentences)
    claims = [ClaimRecord(**ids, report_id="rep-c3d", agent_id=agent, claim_id=f"c{k}", claim_text=s, claim_role="point", materiality="material",
                          **(field if k == 1 else {})) for k, s in enumerate(sentences, start=1)]
    return SpecialistReport(**ids, report_id="rep-c3d", agent_id=agent, original_response=text, response_sha256=sha256_text(text), claims=claims,
                            created_at=CREATED)


def _both_paths(subject: str, agent: str, task_type: str, sentences, field: dict):
    """The structured report through an audited hub: the delivery policy's fallback candidate, the router's decision on the
    consolidation, and the task audit's self-report codes (with their severities)."""
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        plan = WorkPlan(plan_id="p-c3d", request_id="r-c3d", task_id="t-c3d", subject=subject, task_type=task_type, selected_agent_ids=[agent])
        hub.open_task(plan)
        m, _req, rq = hub.dispatch(plan.task_id, agent, "Answer the question.", [])
        assert m is not None, rq.findings
        session = DeliveryPolicy(clock=FakeClock()).start(hub, plan.task_id)
        session.install()
        _reply, rc = hub.receive(plan.task_id, m.message_id, _report(subject, agent, task_type, sentences, field))
        decision = session.decide(request_message_ids=[m.message_id], receipts={rc.message_id: rc})
        resp = hub.consolidate(plan.task_id)
        routed = delivery_decision(resp, hub.auditor.keyring, hub=hub)
        audit = [a for a in hub.auditor.audits(resp.channel_uid) if a.scope == "task"][-1]
        codes = sorted({(f.code, f.severity) for f in audit.report.findings if f.code in SELF_REPORT_AUDIT_CODES})
        [candidate] = decision.receipt.fallback.candidates
        return candidate, routed, codes
    finally:
        hub.close()


def test_the_release_paths_share_one_set_of_audit_codes():
    assert SELF_REPORT_AUDIT_CODES is META_AUDIT_CODES
    assert META_AUDIT_CODES == frozenset({"OVS-FID-005", "OVS-FID-009"})


@pytest.mark.parametrize("field", ADVISORY, ids=["eligibility", "status"])
@pytest.mark.parametrize("subject,agent,task_type,sentences", STRUCTURED, ids=IDS)
def test_the_router_refuses_what_the_task_audit_names_as_the_fallback_does(subject, agent, task_type, sentences, field):
    """c3c open item (a): the task audit names the structured content claim OVS-FID-009 (warning); the fallback withheld it while
    the router's decision allowed it. Both refuse it now, the router by rule self-certification-gate on the audit's code."""
    candidate, routed, codes = _both_paths(subject, agent, task_type, sentences, field)
    assert codes == [("OVS-FID-009", "warning")], codes
    assert candidate.deliverable is False and any("OVS-FID-009" in r for r in candidate.integrity_reasons), candidate.integrity_reasons
    assert routed.allowed is False and "self-certification-gate" in routed.reason, routed.reason
    if "advisory_verification_eligibility" in field:  # nothing but the audit names it: the reason is the audit's
        assert routed.reason.startswith("the task audit names a self-report the deliverable answer carries as content (OVS-FID-009 (claims c1))"), routed.reason
    assert refusal_label(routed.reason) == "not_deliverable"


@pytest.mark.parametrize("subject,agent,task_type,sentences", STRUCTURED, ids=IDS)
def test_control_the_same_report_without_the_fields_is_delivered_on_both_paths(subject, agent, task_type, sentences):
    candidate, routed, codes = _both_paths(subject, agent, task_type, sentences, {})
    assert codes == []
    assert candidate.deliverable is True, candidate.integrity_reasons
    assert routed.allowed is True, routed.reason


def _finding(code: str, severity: str, message_ids, claim_ids=()):
    return SimpleNamespace(code=code, severity=severity, message_ids=list(message_ids), claim_ids=list(claim_ids))


def _audit(*findings):
    return SimpleNamespace(report=SimpleNamespace(findings=list(findings)))


def test_the_audit_reading_names_both_codes_at_any_severity_and_only_for_the_message():
    audit = _audit(_finding("OVS-FID-009", "warning", ["m1"], ["c2", "c1"]), _finding("OVS-FID-005", "error", ["m1"]),
                   _finding("OVS-FID-004", "error", ["m1"], ["c3"]), _finding("OVS-FID-009", "info", ["m2"], ["c9"]))
    assert audit_self_reports(audit, "m1") == ["OVS-FID-005", "OVS-FID-009 (claims c1, c2)"]
    assert audit_self_reports(audit, "m2") == ["OVS-FID-009 (claims c9)"]
    assert audit_self_reports(audit, "m3") == []
    assert audit_self_reports(None, "m1") == []


def _synthesis(findings=()):
    receipt = SimpleNamespace(message_id="syn-1", findings=list(findings))
    message = SimpleNamespace(payload={"claims": [{"claim_id": "s1", "text": "The treaty was signed in 1919."}],
                                       "text": "The treaty was signed in 1919."})
    return receipt, message


def test_the_synthesis_release_reads_the_task_audits_self_report():
    """Rewritten to the stricter value of stage 2a of the meaning check: the gate is called here with no journaled event (``None``),
    so the synthesis carries no meaning-label record, and a synthesis with no record is never released unlabelled (rule
    meaning-label-unavailable, ``selfcert_label_unavailable``). Before stage 2a these two calls returned None (released); the
    task audit's self-report is still read first and named as before."""
    receipt, message = _synthesis()
    unlabelled = "the synthesis has no usable meaning label (missing): it is not released unlabelled (rule meaning-label-unavailable)"
    assert _synthesis_self_report(receipt, None, message, _audit()) == unlabelled
    assert _synthesis_self_report(receipt, None, message, _audit(_finding("OVS-FID-009", "warning", ["other"], ["s1"]))) == unlabelled
    assert refusal_label(unlabelled) == "selfcert_label_unavailable"
    why = _synthesis_self_report(receipt, None, message, _audit(_finding("OVS-FID-009", "warning", ["syn-1"], ["s1"])))
    assert why == ("the task audit names a self-report the synthesis carries as content (OVS-FID-009 (claims s1)): a released answer never "
                   "contains a claim that it was checked or verified (rule self-certification-gate)")
    assert refusal_label(why) == "not_deliverable"


def test_the_synthesis_release_fails_closed_on_an_unreadable_audit():
    receipt, message = _synthesis()
    why = _synthesis_self_report(receipt, None, message, SimpleNamespace(report=None))
    assert why == "the task audit cannot be read for rule self-certification-gate"
    assert refusal_label(why) == "not_deliverable"


def test_the_routers_gate_fails_closed_when_the_consolidations_task_audit_is_missing(monkeypatch):
    subject, agent, task_type, sentences = STRUCTURED[0]
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        plan = WorkPlan(plan_id="p-c3d", request_id="r-c3d", task_id="t-c3d", subject=subject, task_type=task_type, selected_agent_ids=[agent])
        hub.open_task(plan)
        m, _req, _rq = hub.dispatch(plan.task_id, agent, "Answer the question.", [])
        hub.receive(plan.task_id, m.message_id, _report(subject, agent, task_type, sentences, {}))
        resp = hub.consolidate(plan.task_id)
        assert self_report_at_delivery(resp, resp.deliverable_message_id, hub) is None
        auditor = hub._require_auditor()
        monkeypatch.setattr(auditor, "audits", lambda _uid: [])
        why = self_report_at_delivery(resp, resp.deliverable_message_id, hub)
        assert why == "rule self-certification-gate could not read the deliverable answer (LookupError)"
        assert refusal_label(why) == "not_deliverable"
    finally:
        hub.close()
