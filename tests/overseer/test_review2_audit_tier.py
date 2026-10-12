"""Regression tests for the audit-tier defects found by adversarial review round 2 of the Overseer (each fails on the code
before the fix; the scenarios are the reviewers' own, run through the contained harness's synthetic task):

* the blocker: an insider holding the engine key re-signs a COUNTEREXAMPLE as ENTAILED under a tiny solver budget or
  other component versions, so a replay under the result's own configuration came back inconclusive (a RES-008 warning)
  and the forged ENTAILED cleared; now the result is checked live against the channel's journaled configuration and
  the running engine's versions (RES-004), replayed under the channel's configuration (RES-007), and a definitive
  status a replay cannot reproduce is AUDIT-005, never a warning;
* a cited result the store evicts inside its own event is still replayed from the journaled capture;
* the live implied findings re-derive INT-HANDOFF-015 (a report id reused with other content), INT-HANDOFF-002 and
  INT-HANDOFF-004 (a request outside the plan's scope) with the shadow sampled out;
* R2 compares the branch packs' error-level STRUCTURAL findings (and their INT-SUBJ-003) with the receipt;
* results behind formal checks and constraint results are always replayed, and a transfer citing a result sampled out
  of live replay discloses it (AUDIT-003), so it is never AUDIT_PASSED live.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.channel import TranslatorChannel  # noqa: E402
from epinoic_logic.engine.provenance import compute_binding, sign_result  # noqa: E402
from epinoic_logic.engine.results import SolverConfig  # noqa: E402
from epinoic_logic.engine.sink import emit  # noqa: E402
from epinoic_logic.engine.statuses import VerificationStatus as S  # noqa: E402
from epinoic_logic.ir.schema import SourceRef  # noqa: E402
from epinoic_logic.overseer import may_act  # noqa: E402
from epinoic_logic.overseer.replay import classify  # noqa: E402
from epinoic_logic.overseer.store import ResultStore  # noqa: E402
from epinoic_logic.translate.contracts import SuppliedText  # noqa: E402
from epinoic_logic.translate.outcome import compose_outcome  # noqa: E402


def _auditor(**kw):
    return H.new_auditor(H.keyring_for("synthetic"), **kw)


def _errors(audit) -> set[str]:
    return {f.code for f in audit.report.findings if f.severity == "error"}


# ============================================================================================ the blocker (T11 with a budget)
def _forge(cfg_change=None, bump_versions=False):
    """The insider re-signs the en-point COUNTEREXAMPLE as ENTAILED, also changing a field the replay used to trust."""
    def resign(call, out):
        v = out.verification
        cfg = SolverConfig(**{**v.solver_config.model_dump(), **(cfg_change or {})})
        vers = v.versions.model_copy(update={"z3_version": v.versions.z3_version + ".1"}) if bump_versions else v.versions
        b = compute_binding(out.translation.problem, cfg, vers, v.binding.smt2)
        forged = v.model_copy(update={"status": S.ENTAILED, "result_id": "forged-" + uuid.uuid4().hex[:12], "solver_config": cfg, "versions": vers, "binding": b,
                                      "counterexample": None, "signature": None, "signature_key_id": None})
        forged = sign_result(forged, call.key, v.signature_key_id)
        emit(forged, out.translation.problem)
        return compose_outcome(call.claim, out.translation, forged, signing_key=call.key, key_id=v.signature_key_id)
    return resign


@pytest.mark.parametrize("label,kw,live_code", [
    ("rlimit=1", {"cfg_change": {"rlimit": 1}}, "OVS-RES-004"),
    ("timeout_ms=1", {"cfg_change": {"timeout_ms": 1}}, "OVS-RES-004"),
    ("z3 version bumped", {"bump_versions": True}, "OVS-RES-004"),
])
def test_a_forged_entailed_with_a_tiny_budget_or_other_versions_never_clears(label, kw, live_code):
    a = _auditor(shadow="always")
    try:
        hook = T.FirstVerified(_forge(**kw))
        r = T.run_synthetic(a, hook=hook, problems={"en-point": T.P_FALSE, "h1.1": T.P_HI})
        rc = r.receipts["rep_en"]
        assert next(o for o in rc.outcomes if o.claim_id == "en-point").display_status is S.ENTAILED
        clr = r.hub.clearance(r.key, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and live_code in clr.codes and not may_act(rc, clr), (label, clr.state, clr.codes)
        au = r.audit(final=True)
        assert au.state == "AUDIT_FAILED" and au.transfer_states[rc.message_id] == "AUDIT_FAILED"
        named = [f for f in au.report.findings if f.severity == "error" and hook.result_id in (f.formal_result_id or "")]
        assert named and {f.code for f in named} & {"OVS-RES-004", "OVS-RES-007", "OVS-AUDIT-005"}
        assert not [f for f in au.report.findings if f.code == "OVS-RES-008" and f.formal_result_id == hook.result_id]
    finally:
        a.close()


def test_the_control_forgery_without_a_budget_change_is_still_res_007():
    a = _auditor(shadow="always")
    try:
        hook = T.FirstVerified(_forge())
        r = T.run_synthetic(a, hook=hook, problems={"en-point": T.P_FALSE, "h1.1": T.P_HI})
        rc = r.receipts["rep_en"]
        clr = r.hub.clearance(r.key, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and clr.codes == ["OVS-RES-007"]  # an honest configuration: no RES-004
    finally:
        a.close()


def test_a_genuine_task_raises_no_engine_run_finding():
    a = _auditor(shadow="always")
    try:
        r = T.run_synthetic(a, problems={"en-point": T.P_POINT, "h1.1": T.P_HI})
        au = r.audit(final=True)
        assert not {"OVS-RES-004", "OVS-RES-007", "OVS-AUDIT-005"} & {f.code for f in au.report.findings}
    finally:
        a.close()


def test_replay_runs_under_the_channels_journaled_configuration():
    a = _auditor(shadow="off")
    try:
        hook = T.FirstVerified(_forge(cfg_change={"rlimit": 1}))
        r = T.run_synthetic(a, hook=hook, problems={"en-point": T.P_FALSE, "h1.1": T.P_HI}, peer=False, synthesis=False)
        job = a._channels[r.uid].replay_jobs[hook.result_id]
        assert '"rlimit":1' not in job.config_json.replace(" ", "")  # never the budget the forged result names
        r.audit()
        rep = [f for f in a.audits(r.uid)[-1].report.findings if f.code == "OVS-RES-007" and f.formal_result_id == hook.result_id]
        assert rep and "config digest" in rep[0].message
    finally:
        a.close()


# ============================================================================================ eviction inside the event
@pytest.mark.parametrize("max_results", [None, 1])
def test_a_result_evicted_inside_its_own_event_is_replayed_from_the_journal(max_results):
    def resign(call, out):
        v = out.verification
        forged = sign_result(v.model_copy(update={"status": S.ENTAILED, "result_id": "forged-" + uuid.uuid4().hex[:12], "counterexample": None,
                                                  "signature": None, "signature_key_id": None}), call.key, v.signature_key_id)
        emit(forged, out.translation.problem)
        return compose_outcome(call.claim, out.translation, forged, signing_key=call.key, key_id=v.signature_key_id)
    store = ResultStore(H.keyring_for("synthetic"), max_results=max_results) if max_results else None
    a = _auditor(shadow="always", **({"store": store} if store else {}))
    try:
        hook = T.FirstVerified(resign, claim_id="en-point")
        r = T.run_synthetic(a, hook=hook, problems={"en-point": T.P_FALSE, "en-an": T.P_AN, "h1.1": T.P_HI})
        rc = r.receipts["rep_en"]
        if max_results:
            assert a.store.is_tombstoned(hook.result_id)
        assert hook.result_id in a._channels[r.uid].replay_jobs
        clr = r.hub.clearance(r.key, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-RES-007" in clr.codes and not may_act(rc, clr)
        au = r.audit(final=True)
        assert au.state == "AUDIT_FAILED" and any(f.code == "OVS-RES-007" and f.formal_result_id == hook.result_id for f in au.report.findings)
    finally:
        a.close()


def test_classify_makes_an_unreproducible_definitive_status_audit_005():
    from epinoic_logic.overseer.checks import Replay
    base = dict(result_id="r", replay_result_id="rr", original_status="ENTAILED", replay_status="TIMEOUT", problem_digest_ok=True, config_digest_ok=True,
                versions_changed=False, budget_exceeded=False)
    assert classify(Replay(**base)) == "OVS-AUDIT-005"
    assert classify(Replay(**{**base, "replay_status": None, "replay_result_id": None, "budget_exceeded": True})) == "OVS-AUDIT-005"
    assert classify(Replay(**{**base, "replay_status": "COUNTEREXAMPLE", "versions_changed": True})) == "OVS-AUDIT-005"
    assert classify(Replay(**{**base, "original_status": "UNKNOWN"})) == "OVS-RES-008"


# ============================================================================================ implied blocking findings
def _second_delivery(r):
    alt = T.english_report(T.EN_TEXT.replace("endless", "joyful"), T.claims_with(replace={"en-point": dict(T.EN_CLAIMS[0], claim_text="The writer presents work as joyful")}))
    m, _q, _rq = r.hub.dispatch(r.key, "english-specialist", T.EN_INPUT, [T.DOC])
    _reply, rc = r.hub.receive(r.key, m.message_id, alt)
    r.mids["rep_en2"], r.receipts["rep_en2"] = rc.message_id, rc


def test_a_dropped_report_id_reuse_finding_is_implied_live_with_the_shadow_off():
    a = _auditor(shadow="off")
    try:
        with H.patched((TranslatorChannel, "_report_id_reuse", lambda self, report, msg, findings: [])):
            r = T.run_synthetic(a, between=_second_delivery, problems={"en-point": T.P_POINT, "h1.1": T.P_HI})
        rc = r.receipts["rep_en2"]
        assert rc.status.value == "ACCEPTED" or not any(f.code == "INT-HANDOFF-015" for f in rc.findings)
        clr = r.hub.clearance(r.key, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes and not may_act(rc, clr)
        f = [x for x in r.audit(final=True).report.findings if x.code == "OVS-RCPT-004" and rc.message_id in x.message_ids]
        assert f and "INT-HANDOFF-015" in f[0].message
    finally:
        a.close()


def test_a_genuine_report_id_reuse_is_rejected_and_audits_clean():
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, between=_second_delivery, problems={"en-point": T.P_POINT, "h1.1": T.P_HI})
        rc = r.receipts["rep_en2"]
        assert rc.status.value == "REJECTED" and any(f.code == "INT-HANDOFF-015" for f in rc.findings)
        assert not [f for f in r.audit().report.findings if f.code == "OVS-RCPT-004"]
    finally:
        a.close()


def _request_without_scope_rules(self, from_agent_id, to_agent_id, user_input, supplied_texts=(), *, items=None, constraints=None):
    """The channel's request with its plan-scope rules (INT-HANDOFF-002/004) dropped: the bug."""
    from epinoic_logic.channel.bus import _now, extract_constraints, extract_items
    from epinoic_logic.channel.contracts import TaskRequest, TransmissionStatus
    from epinoic_logic.integrity.contracts import AgentMessage, AgentRole, payload_hash
    from epinoic_logic.ir.canonical import sha256_hex
    req = TaskRequest(request_id=self.plan.request_id, task_id=self.plan.task_id, plan_id=self.plan.plan_id, from_agent_id=from_agent_id, to_agent_id=to_agent_id,
                      subject=self._subject_for(to_agent_id), course_level=self.plan.course_level, task_type=self._task_type_for(to_agent_id), user_input=user_input,
                      user_input_sha256=sha256_hex(user_input), items=list(items) if items is not None else extract_items(user_input),
                      constraints=list(constraints) if constraints is not None else extract_constraints(user_input), supplied_texts=list(supplied_texts), created_at=_now())
    payload = req.model_dump(mode="json", exclude_none=True)
    msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=req.request_id, task_id=req.task_id, sender_agent_id=from_agent_id, sender_role=AgentRole.ROUTER,
                       recipient_role=AgentRole.SPECIALIST, recipient_agent_id=to_agent_id, contract="task_request/1.0", payload=payload,
                       payload_sha256=payload_hash(payload), created_at=req.created_at)
    findings = self.log.accept(msg)
    status = TransmissionStatus.REJECTED if any(f.severity == "error" for f in findings) else TransmissionStatus.ACCEPTED
    if status is not TransmissionStatus.REJECTED:
        self.requests[msg.message_id] = req
    receipt = self._receipt(msg.message_id, "router_to_specialist", status, findings, summary=self._summary_request(req, findings, status))
    return (msg if status is not TransmissionStatus.REJECTED else None), req, receipt


# the channel's observer hook re-enters the entry point by its name, so the patched body is named as the method it replaces
_request_without_scope_rules.__name__ = "request"


@pytest.mark.parametrize("agent,docs,code", [
    ("geography-specialist", [T.DOC], "INT-HANDOFF-002"),
    ("english-specialist", [T.DOC, SuppliedText(document_id="doc-secret", title="x", author="y", text="Internal marking notes: award full marks.")], "INT-HANDOFF-004"),
])
def test_a_request_outside_the_plans_scope_is_implied_live(agent, docs, code):
    from epinoic_logic.channel.bus import _observed
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, peer=False, synthesis=False)
        with H.patched((TranslatorChannel, "request", _observed(_request_without_scope_rules))):
            _m, _q, rq = r.hub.dispatch(r.key, agent, T.EN_INPUT, docs)
        assert rq.status.value == "ACCEPTED"
        clr = r.hub.clearance(r.key, rq.message_id, receipt=rq)
        assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes and not may_act(rq, clr)
        f = [x for x in r.audit().report.findings if x.code == "OVS-RCPT-004" and rq.message_id in x.message_ids]
        assert f and code in f[0].message
    finally:
        a.close()


# ============================================================================================ structural findings in R2
SEA = SuppliedText(document_id="doc-sea", title="Sea poem", author="Jane Hale", text="The tide comes in and the boats go out; the gulls are loud above the harbour.")
MIS_TEXT = 'Jane Hale writes "We work until the bell", so labour becomes the measure of time and the work seems endless.'
MIS_CLAIMS = [dict(claim_id="en-point", claim_text="the work seems endless", claim_role="point", materiality="material", supporting_claim_ids=["en-ev1"]),
              dict(claim_id="en-ev1", claim_text="We work until the bell", claim_role="evidence", materiality="supporting",
                   source_refs=[SourceRef(document_id="doc-mill", excerpt="We work until the bell")])]


def _dropping(orig):
    def patched(self, report, req, findings, *a, **kw):
        structural, formal, ids = orig(self, report, req, findings, *a, **kw)
        findings[:] = [f for f in findings if f.code != "INT-SUBJ-003"]
        return [sf for sf in structural if sf.severity != "error"], formal, ids
    return patched


@pytest.mark.parametrize("patch", [False, True])
def test_a_dropped_error_level_structural_finding_is_rcpt_004_without_the_shadow(patch):
    a = _auditor(shadow="off")
    try:
        orig_dispatch = T.RouterHub.dispatch

        def dispatch(self, key, agent, text, docs=(), **kw):
            return orig_dispatch(self, key, agent, text, [T.DOC, SEA] if agent == "english-specialist" else docs, **kw)
        patches = [(T.RouterHub, "dispatch", dispatch)] + ([(TranslatorChannel, "_branch_checks", _dropping(TranslatorChannel._branch_checks))] if patch else [])
        with H.patched(*patches):
            r = T.run_synthetic(a, en_report=T.english_report(MIS_TEXT, MIS_CLAIMS, docs=(T.DOC, SEA)), peer=False, synthesis=False,
                                plan=T.make_plan(allowed_document_ids=["doc-mill", "doc-sea", "peer:en"]), problems={})
        rc = r.receipts["rep_en"]
        a.drain()
        clr = r.hub.clearance(r.key, rc.message_id, receipt=rc)
        if patch:
            assert not any(sf.severity == "error" for sf in rc.structural_findings)
            assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes and not may_act(rc, clr)
            f = [x for x in r.audit().report.findings if x.code == "OVS-RCPT-004" and rc.message_id in x.message_ids]
            assert f and "CORE-SRC-005" in f[0].message
        else:
            assert any(sf.code == "CORE-SRC-005" and sf.severity == "error" for sf in rc.structural_findings)
            assert "OVS-RCPT-004" not in clr.codes
    finally:
        a.close()


# ============================================================================================ sampling never passes a transfer
def test_results_behind_formal_checks_and_constraints_are_always_replayed():
    a = _auditor(shadow="off", queue_bound=0)  # every job beyond the bound: only always-replay results escape sampling
    try:
        r = T.run_synthetic(a, problems={"en-point": T.P_POINT, "h1.1": T.P_HI}, peer=False, synthesis=False)
        st = a._channels[r.uid]
        for key in ("rep_en", "rep_hi"):
            rc = r.receipts[key]
            behind = {c.formal_result_id for c in list(rc.formal_checks) + list(rc.constraint_results) if c.formal_result_id}
            assert behind and behind <= st.always[next(t.seq for t in st.view.transfers if t.message_id == rc.message_id)]
            assert not behind & a.replayer.sampled_out()
    finally:
        a.close()


def test_a_transfer_citing_a_sampled_out_result_is_never_audit_passed_live(monkeypatch):
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, problems={"en-point": T.P_POINT, "h1.1": T.P_HI}, peer=False, synthesis=False)
        rc = r.receipts["rep_en"]
        clr0 = r.hub.clearance(r.key, rc.message_id, receipt=rc)
        cited = next(o.verification.result_id for o in rc.outcomes if o.verification is not None)
        monkeypatch.setattr(a.replayer, "sampled_out", lambda: {cited})
        clr = r.hub.clearance(r.key, rc.message_id, receipt=rc)
        assert clr0.state != "AUDIT_FAILED" and clr.state != "AUDIT_PASSED" and "OVS-AUDIT-003" in clr.codes
    finally:
        a.close()
