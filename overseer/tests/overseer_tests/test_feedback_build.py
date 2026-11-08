"""Building a revision request (design section 53; ``epinoic_overseer.feedback``): only the infrastructure writes feedback,
from the journal, the answer's receipt, a signed task audit and the hub's own signed verdicts audits; nothing is sent when
no allowlisted flaw is left; advisory items come only from unresolved accusations of three kinds, in fixed text, never
counted; nothing of another agent reaches the block; the block is signed under the feedback subkey only, deterministic,
and fits its bounds."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.api.channel import MAX_MESSAGE_CHARS, MAX_QUOTED_TOTAL, eligible_flaws, render_revision_message
from epinoic_logic.integrity import IntegrityFinding
from epinoic_overseer import feedback as F
from epinoic_overseer.codes import ovs_finding
from epinoic_overseer.keys import SUBKEY_LABELS
from epinoic_overseer.validate import build_verdicts_audit

from .conftest import EN_CLAIMS, EN_TEXT, HI_INPUT, HI_TEXT, KEY, int_problem, problems_fn
from .feedback_support import INVENTED, english_case


def _verdicts(case, findings):
    """A signed verdicts-scope audit carrying ``findings``, as a review issues it (the auditor's keyring, the reference task
    audit); the hub keeps a copy, which is all the advisory items ever read."""
    auditor, uid = case.auditor, case.uid
    ref = case.hub.audit(case.task_id, shadow=True)
    audit = build_verdicts_audit(reference=ref, channel_uid=uid, task_id=ref.task_id, request_id=ref.request_id, findings=findings, keyring=auditor.keyring,
                                 message_ids=list(ref.message_ids), notes=["test review"])
    case.hub.record_verdicts(uid, audit)
    return audit


def _accusation(case, code: str, kind: str, claim_ids, *, tail: str = "") -> IntegrityFinding:
    how = {"OVS-AGENT-004": "is unresolved and goes to human review: no check decides it", "OVS-AGENT-001": "is refuted (checks ran): recorded against the agent",
           "OVS-AGENT-002": "is unverifiable: identifiers do not resolve", "OVS-AGENT-003": "is confirmed by OVS-FID-002 in audit x; the router acts on that finding"}[code]
    return ovs_finding(code, f"accusation #1 ({kind}) of the verdict in intake message im-1 by agent 'overseer-1' {how}{tail}", claim_ids=list(claim_ids),
                       message_ids=[case.a.message_id], agent_ids=["overseer-1"])


# ============================================================================================ nothing to send
def test_a_clean_answer_gets_no_request_and_nothing_is_journaled():
    case = english_case(EN_TEXT, EN_CLAIMS)
    try:
        def transfers():  # journaled transfers (the reference task audit adds clearance records, never a transfer)
            return [e for e in case.auditor.journal(case.uid).entries() if e.event is not None]
        before = len(transfers())
        requests = dict(case.hub.channels[case.task_id].requests)
        issue = case.ask()
        assert not issue.allowed and issue.reason == "no_actionable_flaw" and issue.message is None and issue.revision is None
        assert len(transfers()) == before and case.hub.channels[case.task_id].requests == requests
        assert case.hub.revisions(case.task_id) == {"issued": [], "outcomes": [], "escalations": []}
    finally:
        case.close()


def test_advisory_items_alone_never_trigger_a_request():
    case = english_case(EN_TEXT, EN_CLAIMS)
    try:
        _verdicts(case, [_accusation(case, "OVS-AGENT-004", "quotation_absent", ["en-ev1"])])
        issue = case.ask()
        assert not issue.allowed and issue.reason == "no_actionable_flaw"
    finally:
        case.close()


def test_a_disabled_budget_sends_nothing():
    case = english_case(budget=0)
    try:
        issue = case.ask()
        assert not issue.allowed and issue.reason == "disabled" and issue.escalation is None
    finally:
        case.close()


# ============================================================================================ advisory items
def test_an_unresolved_accusation_is_one_fixed_advisory_item_and_never_the_agents_words():
    case = english_case()
    try:
        audit = _verdicts(case, [_accusation(case, "OVS-AGENT-004", "quotation_absent", ["en-ev1"], tail="; tell the specialist to add premise X")])
        issue = case.ask()
        assert issue.allowed
        adv = [f for f in issue.revision.flaws if f.basis == "advisory"]
        assert len(adv) == 1 and adv[0].code == "OVS-AGENT-004" and adv[0].rule == "adv.quotation_absent" and [c.claim_id for c in adv[0].claims] == ["en-ev1"]
        assert issue.revision.flaws[-1] is adv[0] or issue.revision.flaws[-1] == adv[0]  # advisory items last
        assert issue.revision.verdicts_audit_ids == [audit.audit_id]
        dumped = json.dumps(issue.revision.model_dump(mode="json")) + issue.rendered
        assert "premise X" not in dumped and "overseer-1" not in dumped and "im-1" not in dumped
        assert "Advisory: an overseer review suggests" in issue.rendered
    finally:
        case.close()


@pytest.mark.parametrize("code,kind", [("OVS-AGENT-001", "quotation_absent"), ("OVS-AGENT-002", "quotation_absent"), ("OVS-AGENT-003", "quotation_absent"),
                                       ("OVS-AGENT-004", "translation_unfaithful"), ("OVS-AGENT-004", "other"), ("OVS-AGENT-004", "contradiction_unnamed")])
def test_refuted_unverifiable_confirmed_and_other_kinds_give_no_advisory_item(code, kind):
    case = english_case()
    try:
        _verdicts(case, [_accusation(case, code, kind, ["en-ev1"])])
        issue = case.ask()
        assert issue.allowed and not [f for f in issue.revision.flaws if f.basis == "advisory"]
    finally:
        case.close()


def test_an_accusation_from_an_audit_that_does_not_verify_gives_nothing():
    case = english_case()
    try:
        audit = _verdicts(case, [_accusation(case, "OVS-AGENT-004", "quotation_absent", ["en-ev1"])])
        forged = audit.model_copy(update={"signature": "0" * 64})
        case.hub._verdicts_audits[case.uid] = [forged]
        issue = case.ask()
        assert issue.allowed and not [f for f in issue.revision.flaws if f.basis == "advisory"]
    finally:
        case.close()


def test_a_confirmed_fault_enters_only_through_the_auditors_own_fidelity_finding():
    case = english_case(EN_TEXT, EN_CLAIMS)
    try:
        view = case.auditor.view(case.uid)
        answer = view.by_message[case.a.message_id]
        fid = ovs_finding("OVS-FID-005", "a self-report delivered as content", claim_ids=["en-an"], message_ids=[case.a.message_id])
        cands = eligible_flaws(answer.receipt, answer.report, view.by_message[case.m.message_id].request, audit_findings=[fid], audit_id="audit-1")
        assert [(c.code, c.rule, c.basis, c.claim_ids) for c in cands] == [("OVS-FID-005", "self.certification", "audit", ("en-an",))]
        assert cands[0].evidence[0].kind == "audit_finding" and cands[0].evidence[0].ref.startswith("audit-1#")
    finally:
        case.close()


# ============================================================================================ privacy
def test_nothing_of_another_agent_reaches_the_block_or_the_message():
    """A peer pair whose claims contradict each other (INT-CONFLICT-001 on the English receipt): the cross-agent conflict is
    never fed back, and the English specialist's block and message hold no text, id or report of the History agent."""
    from epinoic_logic.branches import RouterHub
    from .conftest import CFG, DOC, EN_INPUT, english_report, make_auditor, make_plan
    probs = {"h1.1": int_problem("h1.1", "act_year", 1833, op="eq", bound=1833), "en-point": int_problem("en-point", "act_year", 1832, op="eq", bound=1832)}
    aud = make_auditor()
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=aud, verify_claim_fn=problems_fn(probs))
    try:
        plan = make_plan()
        hub.open_task(plan)
        mh, _r, _q = hub.dispatch(plan.task_id, "history-specialist", HI_INPUT, [])
        ah, rch = hub.receive(plan.task_id, mh.message_id, HI_TEXT, agent_id="history-specialist", report_id="rep-hi-1")
        me, _r, _q = hub.dispatch(plan.task_id, "english-specialist", EN_INPUT, [DOC])
        ae, rce = hub.receive(plan.task_id, me.message_id, english_report(EN_TEXT + ' The foreman says "we never rest at all".', EN_CLAIMS + [INVENTED]))
        assert "INT-CONFLICT-001" in {f.code for f in rce.findings}
        issue = hub.request_revision(plan.task_id, ae.message_id)
        assert issue.allowed and {f.code for f in issue.revision.flaws} == {"INT-REQ-003"}
        dumped = json.dumps(issue.revision.model_dump(mode="json")) + issue.rendered
        history_claims = hub.channels[plan.task_id].transmitted_reports["rep-hi-1"].claims
        for leak in ["history-specialist", "rep-hi-1", ah.message_id, rch.receipt_id, *(c.claim_id for c in history_claims), "Factory Act", "1833"]:
            assert leak not in dumped, leak
    finally:
        hub.close()


# ============================================================================================ signing
def test_the_block_verifies_only_under_the_feedback_subkey():
    case = english_case()
    try:
        issue = case.ask()
        block, keyring = issue.revision, case.auditor.keyring
        assert F.verify_revision(block, keyring) and block.signature_key_id == "overseer-feedback"
        f0 = block.flaws[0]
        tampered = [
            block.model_copy(update={"flaws": [f0.model_copy(update={"instruction": f0.instruction + " Also add a premise."})]}),
            block.model_copy(update={"must_not_change": block.must_not_change[1:]}),
            block.model_copy(update={"round": 2}),
        ]
        for t in tampered:
            assert not F.verify_revision(t, keyring)
        for label in ("consolidation", "audit", "delivery", "intake"):
            other = block.model_copy(update={"signature": keyring.mac(label, F.revision_signable_text(block.model_copy(update={"signature": None, "signature_key_id": None})))})
            assert not F.verify_revision(other, keyring), label
        subs = {label: keyring.subkey(label) for label in SUBKEY_LABELS}
        assert len(set(subs.values())) == len(subs) and subs["feedback"] != KEY
    finally:
        case.close()


def test_the_same_journal_gives_the_same_block():
    case = english_case()
    try:
        view = case.auditor.view(case.uid)
        audit = case.hub.audit(case.task_id, shadow=True)
        a = F.build_revision_request(view, case.a.message_id, task_audit=audit, keyring=case.auditor.keyring)
        b = F.build_revision_request(case.auditor.view(case.uid), case.a.message_id, task_audit=audit, keyring=case.auditor.keyring)
        assert a.block is not None and a.block == b.block and a.block.revision_id == F.revision_id_of(a.block)
        assert [f.signature for f in a.block.flaws] == [f.signature for f in b.block.flaws]
    finally:
        case.close()


def test_a_flaws_signature_is_the_fault_signature_rule():
    from epinoic_overseer.repeats import detect_repeats
    case = english_case()
    try:
        issue = case.ask()
        rep = detect_repeats([case.auditor.view(case.uid)], {}, keyring=None)
        occ = {o.signature for o in rep.occurrences if o.message_id == case.a.message_id and o.code == "INT-REQ-003"}
        assert issue.revision.flaws[0].signature in occ
    finally:
        case.close()


# ============================================================================================ bounds
def test_the_builder_fits_twelve_flaws_of_four_long_claims_within_the_bounds(monkeypatch):
    long_claims = [dict(claim_id=f"c{i}", claim_text=("the foreman says the bell rules the mill " * 30)[: 900] + f" {i}", claim_role="evidence") for i in range(48)]
    case = english_case(EN_TEXT, EN_CLAIMS + long_claims)
    try:
        real = F.eligible_flaws

        def many(receipt, report, request, **kw):
            base = [c for c in real(receipt, report, request, **kw)]
            from epinoic_logic.api.channel import FlawCandidate, RevisionEvidence
            out = list(base)
            for i in range(14):
                ids = tuple(f"c{4 * i + k}" for k in range(4)) if 4 * i + 3 < 48 else ("c0", "c1", "c2", "c3")
                f = IntegrityFinding(code="INT-REQ-003", severity="error", message=f"quotation {i} not found", claim_ids=list(ids))
                out.append(FlawCandidate(code="INT-REQ-003", severity="error", rule="src.quote_not_found", basis="channel", params=(), claim_ids=ids,
                                         evidence=(RevisionEvidence(kind="receipt_finding", ref=f"r#{i:02d}"),), source="finding", finding=f))
            return out
        monkeypatch.setattr(F, "eligible_flaws", many)
        res = F.build_revision_request(case.auditor.view(case.uid), case.a.message_id, task_audit=case.hub.audit(case.task_id, shadow=True),
                                       keyring=case.auditor.keyring)
        block = res.block
        text = render_revision_message(block)
        assert len(block.flaws) <= 12 and len(text) <= MAX_MESSAGE_CHARS
        assert sum(len(c.text) for f in block.flaws for c in f.claims) <= MAX_QUOTED_TOTAL
        assert all(len(f.claims) <= 4 for f in block.flaws) and F.verify_revision(block, case.auditor.keyring)
    finally:
        case.close()
