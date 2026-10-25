"""Regression tests for the audit-tier defects found by adversarial review round 3 of the Overseer (each fails on the code
before the fix; the scenarios are the reviewers' own, run through the contained harness's synthetic task):

* the plan, solver configuration, key id and branch are pinned at the channel's first event (rule ``pinned-setup``): a
  plan or configuration changed mid-task is CUST-002 on every transfer issued under it, every rule applies the first
  ones, and the channel holds its own copy of the plan;
* a starved configuration turns a violated word bound into an undecided one no longer: RES-004 live, and R2's integer
  arithmetic decides the bound (RES-007);
* coverage records are re-derived live with the channel's coverage rule (one INT-REQ-004 per unaddressed item), and the
  shadow compares finding multisets and the structured fields;
* the relay path's blocking rules, ROLE_CONTRACTS and INT-REQ-002 are implied live;
* a captured signed INCONSISTENT cross-report run with no conflict named is RCPT-004 live, and the joint runs are
  always replayed;
* a request whose bounds are weaker than its own user input states is RCPT-004;
* R2 reads an evicted formal check's problem from the journaled capture (FORM-003, or AUDIT-005 when nothing holds it);
* a false conflict padded with an unpooled claim is JOINT-003;
* a held clearance is refused once the auditor's word on the transfer changed (``may_act(..., auditor=)``);
* the journal counts a captured result the receipt carries once, sizes its bound from the plan, and a digest-only
  transfer is AUDIT-005 without a JOINT-004 accusation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.channel import TranslatorChannel  # noqa: E402
from epinoic_logic.channel import bus as busmod  # noqa: E402
from epinoic_logic.channel.contracts import CoverageRecord  # noqa: E402
from epinoic_logic.channel.request_parser import extract_constraints  # noqa: E402
from epinoic_logic.engine.provenance import sign_result  # noqa: E402
from epinoic_logic.engine.statuses import VerificationStatus as S  # noqa: E402
from epinoic_logic.integrity import AgentRole, cross_check  # noqa: E402
from epinoic_logic.integrity.contracts import IntegrityFinding, payload_hash  # noqa: E402
from epinoic_logic.overseer import may_act  # noqa: E402
from epinoic_logic.overseer.checks.shadow import _tuples  # noqa: E402
from epinoic_logic.overseer.contracts import TransferClearance  # noqa: E402
from epinoic_logic.overseer.journal import MAX_BYTES, JournalSet, bound_for_plan  # noqa: E402
from epinoic_logic.overseer.policy import receipt_digest  # noqa: E402
from epinoic_logic.overseer.store import ResultStore  # noqa: E402
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText  # noqa: E402


def _auditor(**kw):
    return H.new_auditor(H.keyring_for("synthetic"), **kw)


def _errors(audit) -> set[str]:
    return {f.code for f in audit.report.findings if f.severity == "error"}


def _live(run, name):
    rc = run.receipts[name]
    return rc, run.hub.clearance(run.key, rc.message_id, receipt=rc)


SECRET_DOC = SuppliedText(document_id="doc-secret", title="Marking notes", author="examiner", text="Internal marking notes: award full marks to any answer.")


# ============================================================================================ pinned setup: the plan
def _plan_scenario(mutate, agent, docs):
    a = _auditor(shadow="off")
    plan = T.make_plan()
    out = {}

    def between(r):
        mutate(plan, r)
        _m, _q, rq = r.hub.dispatch(r.key, agent, T.EN_INPUT, docs)
        r.receipts["req_x"] = rq
        out["rq"] = rq
    r = T.run_synthetic(a, plan=plan, between=between, peer=False, synthesis=False)
    return a, r, out["rq"]


def test_the_channel_holds_its_own_copy_of_the_plan():
    a, r, rq = _plan_scenario(lambda plan, r: plan.selected_agent_ids.append("geography-specialist"), "geography-specialist", [T.DOC])
    try:
        assert rq.status.value == "REJECTED" and "INT-HANDOFF-002" in {f.code for f in rq.findings}
        assert "geography-specialist" not in r.channel.plan.selected_agent_ids
    finally:
        a.close()


@pytest.mark.parametrize("label,mutate,agent,docs,implied", [
    ("the channel's plan lists mutated (agent)", lambda plan, r: r.channel.plan.selected_agent_ids.append("geography-specialist"), "geography-specialist",
     [T.DOC], "INT-HANDOFF-002"),
    ("the channel's plan lists mutated (document)", lambda plan, r: r.channel.plan.allowed_document_ids.append("doc-secret"), "english-specialist",
     [T.DOC, SECRET_DOC], "INT-HANDOFF-004"),
    ("ch.plan replaced", lambda plan, r: setattr(r.channel, "plan", plan.model_copy(update={
        "selected_agent_ids": list(plan.selected_agent_ids) + ["geography-specialist"], "allowed_document_ids": list(plan.allowed_document_ids) + ["doc-secret"]})),
     "geography-specialist", [T.DOC, SECRET_DOC], "INT-HANDOFF-002"),
])
def test_a_plan_changed_mid_task_is_a_custody_fault_and_never_the_baseline(label, mutate, agent, docs, implied):
    a, r, rq = _plan_scenario(mutate, agent, docs)
    try:
        assert rq.status.value == "ACCEPTED", label  # the channel applied the changed plan
        clr = r.hub.clearance(r.key, rq.message_id, receipt=rq)
        assert clr.state == "AUDIT_FAILED" and "OVS-CUST-002" in clr.codes and "OVS-RCPT-004" in clr.codes, label
        assert not may_act(rq, clr)
        audit = r.audit(final=True)
        assert {"OVS-CUST-002", "OVS-RCPT-004"} <= _errors(audit), label
        assert any(f.code == "OVS-RCPT-004" and implied in f.message for f in audit.report.findings), label
        v = r.view()
        seq = v.by_message[rq.message_id].seq
        assert seq > 1 and v.plan_at(seq) is v.plan and "geography-specialist" not in v.plan_at(seq).selected_agent_ids
        assert "doc-secret" not in v.plan_at(seq).allowed_document_ids
    finally:
        a.close()


# ============================================================================================ pinned setup: the configuration
def _starved_hub(a, starve):
    hub = T.RouterHub(signing_key=T.KEY, key_id="hub", config=T.CFG, auditor=a)
    real = hub.dispatch

    def dispatch(task_id, to_agent_id, user_input, supplied_texts=(), **kw):
        out = real(task_id, to_agent_id, user_input, supplied_texts, **kw)
        if starve:
            ch = hub.channels[task_id]
            ch.config = ch.config.model_copy(update={"rlimit": 1})
        return out
    hub.dispatch = dispatch
    return hub


def test_a_starved_configuration_swapped_in_mid_task_never_clears():
    a = _auditor(shadow="always")
    try:
        r = T.run_synthetic(a, hub=_starved_hub(a, True), en_report=T.english_report(T.LONG_TEXT), peer=False, synthesis=False, problems={})
        rc, clr = _live(r, "rep_en")
        c1 = next(c for c in rc.constraint_results if c.constraint_id == "c1")
        assert c1.formal_status == "TIMEOUT" and c1.satisfied is None and not [f for f in rc.findings if f.code == "INT-REQ-005"]
        assert clr.state == "AUDIT_FAILED" and {"OVS-CUST-002", "OVS-RES-004"} <= set(clr.codes)
        audit = r.audit(final=True)
        assert {"OVS-CUST-002", "OVS-RES-004", "OVS-RES-007"} <= _errors(audit)
        assert any(f.code == "OVS-RES-007" and "reported as undecided" in f.message for f in audit.report.findings)
    finally:
        a.close()


def test_the_genuine_configuration_keeps_its_counterexample():
    a = _auditor(shadow="always")
    try:
        r = T.run_synthetic(a, hub=_starved_hub(a, False), en_report=T.english_report(T.LONG_TEXT), peer=False, synthesis=False, problems={})
        rc, clr = _live(r, "rep_en")
        assert ("INT-REQ-005", "error") in {(f.code, f.severity) for f in rc.findings}
        assert clr.state != "AUDIT_FAILED" and not _errors(r.audit(final=True))
    finally:
        a.close()


# ============================================================================================ coverage re-derived
HI3 = ("Explain the significance of the Factory Act of 1833. Assess the impact of the Mines Act of 1842 on coal miners. "
       "Compare the Poor Law Amendment Act with the Chartist petitions. Write no more than 120 words.")
_ORIG_COV = TranslatorChannel._coverage


def _flip_one(self, req, report, *, echoed=False):
    out, done = [], False
    for c in _ORIG_COV(self, req, report, echoed=echoed):
        if not c.addressed and not done:
            c = CoverageRecord(item_id=c.item_id, addressed=True, addressed_by_claim_ids=[report.claims[-1].claim_id], method=c.method)
            done = True
        out.append(c)
    return out


def _flip_all(self, req, report, *, echoed=False):
    return [CoverageRecord(item_id=c.item_id, addressed=True, addressed_by_claim_ids=c.addressed_by_claim_ids or [report.claims[-1].claim_id], method=c.method)
            for c in _ORIG_COV(self, req, report, echoed=echoed)]


def _hi3_run(a, patch):
    hub = T.RouterHub(signing_key=T.KEY, key_id="hub", config=T.CFG, auditor=a)
    orig = T.HI_INPUT
    T.HI_INPUT = HI3
    try:
        with H.patched((TranslatorChannel, "_coverage", patch)) if patch else H.patched():
            return T.run_synthetic(a, hub=hub, peer=False, synthesis=False)
    finally:
        T.HI_INPUT = orig


@pytest.mark.parametrize("label,patch", [("one item flipped", _flip_one), ("every item flipped", _flip_all)])
def test_coverage_records_and_their_int_req_004_are_re_derived_live(label, patch):
    a = _auditor(shadow="off")
    try:
        r = _hi3_run(a, patch)
        rc, clr = _live(r, "rep_hi")
        assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes, label
        assert not may_act(rc, clr)
        audit = r.audit(final=True)
        assert any(f.code == "OVS-RCPT-004" and "INT-REQ-004" in f.message for f in audit.report.findings), label
    finally:
        a.close()


def test_the_genuine_three_item_answer_passes_and_the_shadow_agrees():
    a = _auditor(shadow="always")
    try:
        r = _hi3_run(a, None)
        rc, clr = _live(r, "rep_hi")
        assert [f.code for f in rc.findings if f.code == "INT-REQ-004"] == ["INT-REQ-004", "INT-REQ-004"]
        assert clr.state != "AUDIT_FAILED" and not _errors(r.audit(final=True))
    finally:
        a.close()


def test_the_shadow_compares_finding_multisets_and_structured_fields():
    two = [IntegrityFinding(code="INT-REQ-004", severity="warning", message="request item i2 appears unaddressed", claim_ids=[]),
           IntegrityFinding(code="INT-REQ-004", severity="warning", message="request item i3 appears unaddressed", claim_ids=[])]
    assert _tuples(two)[("INT-REQ-004", "warning", (), ())] == 2 and _tuples(two[:1])[("INT-REQ-004", "warning", (), ())] == 1
    a = _auditor(shadow="always")
    try:
        r = _hi3_run(a, _flip_one)
        audit = r.audit(final=True)
        assert "OVS-RCPT-008" in _errors(audit)  # the coverage records differ from the shadow's
    finally:
        a.close()


# ============================================================================================ relay rules and INT-REQ-002
_ORIG_BLOCK = busmod._is_blocking
_ORIG_FINISH = TranslatorChannel._finish


def _missing_rule(codes):
    codes = set(codes)

    def is_blocking(findings):
        return _ORIG_BLOCK([f for f in findings if f.code not in codes])

    def finish(self, msg, direction, findings, *a, **kw):
        return _ORIG_FINISH(self, msg, direction, [f for f in findings if f.code not in codes], *a, **kw)
    return [(busmod, "_is_blocking", is_blocking), (TranslatorChannel, "_finish", finish)]


EXTRA = SuppliedText(document_id="doc-extra", title="My own notes", author="english-specialist", text="We work until the bell, and the bell is our only god.")


def _case_req002(a):
    rep = T.english_report(docs=(T.DOC, EXTRA))
    return T.run_synthetic(a, en_report=rep, peer=False, synthesis=False, plan=T.make_plan(allowed_document_ids=["doc-mill", "peer:en", "doc-extra"])), "rep_en"


def _case_fwd_unselected(a):
    def before(r):
        reply = r.messages["rep_en"]
        _m, rf = r.channel.relay("router", AgentRole.ROUTER, "geography-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(reply.payload),
                                 in_reply_to=reply.message_id)
        r.receipts["x"] = rf
    return T.run_synthetic(a, peer=False, synthesis=False, before_synthesis=before), "x"


def _syn_case(sender, role, **update):
    def run(a):
        s = T.default_synthesis().model_copy(update=update) if update else T.default_synthesis()

        def before(r):
            ms, rs = r.channel.relay(sender, role, "router", AgentRole.ROUTER, s)
            r.receipts["x"], r.messages["x"] = rs, ms
        return T.run_synthetic(a, synthesis=False, before_synthesis=before), "x"
    return run


@pytest.mark.parametrize("label,case,codes", [
    ("INT-REQ-002: a report supplying a text the request did not", _case_req002, ["INT-REQ-002"]),
    ("INT-HANDOFF-002: a forward to an unselected agent", _case_fwd_unselected, ["INT-HANDOFF-002"]),
    ("INT-HANDOFF-002: a synthesis by an unselected combinator", _syn_case("rogue-combinator", AgentRole.COMBINATOR, combinator_agent_id="rogue-combinator"),
     ["INT-HANDOFF-002"]),
    ("INT-HANDOFF-001: a synthesis of another request", _syn_case("combinator", AgentRole.COMBINATOR, request_id="req-other", task_id="task-other"),
     ["INT-HANDOFF-001", "INT-LEDGER-008"]),
    ("INT-ENV-007: a synthesis sent in the specialist role", _syn_case("combinator", AgentRole.SPECIALIST), ["INT-ENV-007"]),
])
def test_blocking_relay_and_response_rules_are_implied_live(label, case, codes):
    a = _auditor(shadow="off")
    try:
        with H.patched(*_missing_rule(codes)):
            r, name = case(a)
        rc, clr = _live(r, name)
        assert rc.status.value != "REJECTED", label  # the channel without the rule delivered it
        assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes, label
        assert not may_act(rc, clr)
    finally:
        a.close()


@pytest.mark.parametrize("case", [_case_req002, _case_fwd_unselected, _syn_case("rogue-combinator", AgentRole.COMBINATOR, combinator_agent_id="rogue-combinator")])
def test_the_genuine_channel_rejects_them_and_the_audit_passes(case):
    a = _auditor(shadow="off")
    try:
        r, name = case(a)
        rc, clr = _live(r, name)
        assert rc.status.value == "REJECTED" and clr.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")
    finally:
        a.close()


# ============================================================================================ the joint insider
_REAL_VERIFY = cross_check.verify


def _insider_verify(problem, cfg, limits=None, *, signing_key=None, key_id=None, **kw):
    res = _REAL_VERIFY(problem, cfg, limits, signing_key=signing_key, key_id=key_id, **kw)
    if problem.problem_id.startswith("joint-") and res.status is S.INCONSISTENT_PREMISES:
        res = sign_result(res.model_copy(update={"status": S.CONSISTENT, "unsat_core": None, "signature": None, "signature_key_id": None}), signing_key, key_id)
    return res


def test_a_captured_inconsistent_joint_run_with_no_conflict_named_fails_live():
    a = _auditor(shadow="off")
    try:
        with H.patched((cross_check, "verify", _insider_verify)):
            r = T.run_synthetic(a, problems=dict(T.CONFLICT), synthesis=False)
        rc, clr = _live(r, "rep_hi")
        assert not [f for f in rc.findings if f.code.startswith("INT-CONFLICT")]
        assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes
        st = a._channels[r.uid]
        seq = r.view().by_message[rc.message_id].seq
        joint = [c.result_id for c in r.view().by_seq[seq].event.captured if '"joint-cross-report"' in c.result_json]
        assert joint and set(joint) <= st.always[seq]  # always replayed
    finally:
        a.close()


def test_a_named_conflict_satisfies_the_joint_rule():
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, problems=dict(T.CONFLICT), synthesis=False)
        rc, clr = _live(r, "rep_hi")
        assert "INT-CONFLICT-001" in {f.code for f in rc.findings} and "OVS-RCPT-004" not in clr.codes
    finally:
        a.close()


# ============================================================================================ request constraints
def test_a_request_whose_bound_is_weaker_than_its_user_input_is_rcpt_004():
    a = _auditor(shadow="always")
    hub = T.RouterHub(signing_key=T.KEY, key_id="hub", config=T.CFG, auditor=a)
    real = hub.dispatch

    def dispatch(task_id, to_agent_id, user_input, supplied_texts=(), *, from_agent_id="router"):
        ch = hub.channels[task_id]
        if to_agent_id == "english-specialist":
            cons = [c.model_copy(update={"value": "800"}) if c.kind == "max_words" else c for c in extract_constraints(user_input)]
            return ch.request(from_agent_id, to_agent_id, user_input, list(supplied_texts), constraints=cons)
        return real(task_id, to_agent_id, user_input, supplied_texts, from_agent_id=from_agent_id)
    hub.dispatch = dispatch
    try:
        r = T.run_synthetic(a, hub=hub, en_report=T.english_report(T.LONG_TEXT), peer=False, synthesis=False)
        rq, clr = _live(r, "req_en")
        assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes
        _rc, clr2 = _live(r, "rep_en")
        assert clr2.state == "AUDIT_FAILED"  # the answer depends on the request
        assert any(f.code == "OVS-RCPT-004" and "max_words 80" in f.message for f in r.audit(final=True).report.findings)
    finally:
        a.close()


# ============================================================================================ evicted pack checks (R2)
HI2 = ("The Factory Act of 1833 banned the employment of children under nine in textile mills. "
       "The Ten Hours Act of 1847 followed the Factory Act of 1833. "
       "The Mines Act of 1842 came after the Ten Hours Act of 1847. "
       "On balance, the Act mattered most because it established inspection.")
_ORIG_BRANCH = TranslatorChannel._branch_checks


def _swapper(self, report, req, findings, *a, **kw):
    structural, formal, ids = _ORIG_BRANCH(self, report, req, findings, *a, **kw)
    if len(formal) >= 2:
        x, y = formal[0], formal[1]
        formal = [x.model_copy(update={"formal_result_id": y.formal_result_id, "formal_status": y.formal_status, "satisfied": y.satisfied, "detail": y.detail}),
                  y.model_copy(update={"formal_result_id": x.formal_result_id, "formal_status": x.formal_status, "satisfied": x.satisfied, "detail": x.detail})] + formal[2:]
        findings[:] = [f for f in findings if f.code != "INT-SUBJ-001"]
        for c in formal:
            if c.satisfied is False:
                findings.append(IntegrityFinding(code="INT-SUBJ-001", severity="error", message="the report's own chronology statement does not hold",
                                                 formal_result_id=c.formal_result_id, deterministic=False))
    return structural, formal, ids


def test_swapped_pack_checks_are_form_003_after_the_store_evicted_their_results():
    problems = {"en-point": T.P_POINT, "h1.1": T.P_HI, "h1.2": T.int_problem("h1.2", "y", 1847, op="gt", bound=1833),
                "h1.3": T.int_problem("h1.3", "z", 1842, op="gt", bound=1833), "h1.4": T.int_problem("h1.4", "w", 3, op="ge", bound=1)}
    a = _auditor(shadow="off", store=ResultStore(H.keyring_for("synthetic"), max_results=3))
    try:
        with H.patched((TranslatorChannel, "_branch_checks", _swapper)):
            r = T.run_synthetic(a, hi_text=HI2, peer=False, synthesis=False, problems=problems)
        rc, clr = _live(r, "rep_hi")
        assert all(a.store.is_tombstoned(c.formal_result_id) for c in rc.formal_checks[:2])
        assert clr.state == "AUDIT_FAILED" and "OVS-FORM-003" in clr.codes
        assert "OVS-FORM-003" in _errors(r.audit(final=True))
    finally:
        a.close()


# ============================================================================================ padded false conflict
_REAL_CONSISTENCY = busmod.check_cross_report_consistency


def _fabricate(extra):
    def fn(problems, **kw):
        res, fs = _REAL_CONSISTENCY(problems, **kw)
        cids = sorted(p.claim_id for p in problems)
        if len(cids) >= 2:
            fs = list(fs) + [IntegrityFinding(code="INT-CONFLICT-001", severity="error", message="specialist claims contradict each other", claim_ids=cids + extra,
                                              formal_result_id=res.result_id if res is not None else None, deterministic=False)]
        return res, fs
    return fn


@pytest.mark.parametrize("extra", [[], ["h1.3"]])
def test_a_false_conflict_padded_with_an_unpooled_claim_is_joint_003(extra):
    a = _auditor(shadow="off")
    try:
        with H.patched((busmod, "check_cross_report_consistency", _fabricate(extra))):
            r = T.run_synthetic(a, problems=dict(T.CONSISTENT), synthesis=False, peer=False)
        audit = r.audit(final=True)
        assert audit.state == "AUDIT_FAILED" and "OVS-JOINT-003" in _errors(audit)
        if extra:
            assert any(f.code == "OVS-JOINT-003" and "no formalization" in f.message for f in audit.report.findings)
    finally:
        a.close()


# ============================================================================================ a held clearance
def test_a_held_clearance_is_refused_once_the_auditors_word_changed():
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, synthesis=False, peer=False)
        rc, held = _live(r, "rep_en")
        assert held.state == "AUDIT_PASSED" and may_act(rc, held, auditor=a) and may_act(rc, held)
        # (c) a clearance built by router code
        forged = TransferClearance(clearance_id="x", message_id=rc.message_id, receipt_id=rc.receipt_id, receipt_sha256=receipt_digest(rc), task_id="task-tamper",
                                   channel_uid=r.uid, seq=5, state="AUDIT_PASSED", final=True, codes=[], finding_count=0, created_at="2026-10-12T00:00:00Z")
        assert not may_act(rc, forged) and not may_act(rc, forged, auditor=a)
        # (a) the payload edited after the clearance, no fresh clearance asked for
        m = r.channel.log.get(rc.message_id)
        m.payload["claims"][0]["claim_text"] = "The writer presents work as joyful"
        object.__setattr__(m, "payload_sha256", payload_hash(m.payload))
        assert not may_act(rc, held) and not may_act(rc, held, auditor=a)
    finally:
        a.close()


def test_a_clearance_taken_before_a_failing_task_audit_is_refused():
    a = _auditor(shadow="off")
    try:
        with H.patched((busmod, "check_cross_report_consistency", lambda *x, **k: (None, []))):
            r = T.run_synthetic(a, problems=dict(T.CONFLICT), synthesis=False, peer=False)
        rc, held = _live(r, "rep_hi")
        assert may_act(rc, held, auditor=a)
        audit = r.audit()
        assert audit.transfer_states.get(rc.message_id) == "AUDIT_FAILED"
        assert not may_act(rc, held) and not may_act(rc, held, auditor=a)
    finally:
        a.close()


# ============================================================================================ the journal bound
def test_a_captured_result_the_receipt_carries_is_counted_once():
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, synthesis=False, peer=False)
        t = r.view().by_message[r.receipts["rep_en"].message_id]
        ev = t.event
        held = {o.verification.result_id for o in t.receipt.outcomes if o.verification is not None and o.translation.problem is not None}
        assert held and held <= {c.result_id for c in ev.captured}
        strings = sum(len(s) for s in (ev.plan_json, ev.channel_json, ev.envelope_json, ev.receipt_json, ev.raw_text, ev.call_json) if s)
        others = sum(len(c.result_json) + len(c.problem_json or "") for c in ev.captured if c.result_id not in held)
        assert ev.content_size() == strings + others
    finally:
        a.close()


def test_the_bound_is_sized_from_the_plan():
    assert bound_for_plan(MAX_BYTES, 16) == 2 * MAX_BYTES and bound_for_plan(MAX_BYTES, 3) == MAX_BYTES and bound_for_plan(10, None) == 10
    a = _auditor(shadow="off")
    try:
        plan = T.make_plan(selected_agent_ids=[f"agent-{i}" for i in range(13)] + ["english-specialist", "history-specialist", "combinator"])
        r = T.run_synthetic(a, plan=plan, synthesis=False, peer=False)
        assert a.journal(r.uid).max_bytes == bound_for_plan(MAX_BYTES, 16) > MAX_BYTES
    finally:
        a.close()


def test_a_digest_only_transfer_is_audit_005_without_a_joint_004_accusation():
    a = H.new_auditor(H.keyring_for("synthetic"), shadow="off", journals=JournalSet(H.keyring_for("synthetic"), max_bytes=12_000))
    try:
        r = T.run_synthetic(a, synthesis=False, peer=False)
        t = r.view().by_message[r.receipts["rep_hi"].message_id]
        assert t.digest_only
        audit = r.audit(final=True)
        assert "OVS-AUDIT-005" in _errors(audit)
        assert not [f for f in audit.report.findings if f.code == "OVS-JOINT-004"]
    finally:
        a.close()
