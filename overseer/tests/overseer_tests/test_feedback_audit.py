"""The audit's ``feedback`` stage (OVS-FB-001, design section 53): a revision block that does not verify under the
overseer feedback key, does not bind to the journaled answer, carries another rendered digest, or names a flaw no record
holds, fails the request and the answer replying to it, and consolidation excludes that answer; genuine blocks raise no
false alarm, and the shadow channel agrees on revision transfers."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from epinoic_logic.api.channel import RevisionEvidence, RevisionFlaw, render_instruction, rendered_digest, revision_id_of
from epinoic_overseer import feedback as F

from .conftest import EN_CLAIMS, EN_TEXT, english_report
from .feedback_support import english_case
from .translator_checkout import require_translator_root

ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None
SHADOW_CODES = {"OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-008"}


def _resigned(block, keyring):
    b = block.model_copy(update={"rendered_sha256": rendered_digest(block)})
    return F.sign_revision(b.model_copy(update={"revision_id": revision_id_of(b)}), keyring)


def _base(case):
    return F.build_revision_request(case.auditor.view(case.uid), case.a.message_id, task_audit=case.hub.audit(case.task_id, shadow=True),
                                    keyring=case.auditor.keyring).block


def _issue(case, block):
    ch = case.hub.channels[case.task_id]
    orig = ch.requests[case.m.message_id]
    return ch.request("router", "english-specialist", orig.user_input, list(orig.supplied_texts), items=list(orig.items), constraints=list(orig.constraints),
                      revision=block)


def _fb(audit):
    return [f for f in audit.report.findings if f.code == "OVS-FB-001"]


# ============================================================================================ genuine blocks
def test_a_genuine_revision_request_and_its_revision_audit_without_a_feedback_or_shadow_finding():
    case = english_case()
    try:
        issue = case.ask()
        assert issue.allowed
        audit = case.hub.audit(case.task_id, shadow=True)
        assert not _fb(audit) and not (SHADOW_CODES & {f.code for f in audit.report.findings}) and audit.coverage.shadow_run == "run"
        assert "feedback" in audit.report.checks_run and audit.transfer_states[issue.message.message_id] != "AUDIT_FAILED"
        a2, _rc2 = case.deliver(issue, english_report(EN_TEXT, EN_CLAIMS, report_id="rep-en-2"), report_id="rep-en-2")
        audit2 = case.hub.audit(case.task_id, shadow=True)
        assert not _fb(audit2) and not (SHADOW_CODES & {f.code for f in audit2.report.findings})
        assert audit2.transfer_states[a2.message_id] in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")
        clearance = case.hub.clearance(case.task_id, issue.message.message_id)
        assert clearance.state != "AUDIT_FAILED"
    finally:
        case.close()


def test_an_audit_without_revision_requests_runs_no_feedback_stage():
    case = english_case(EN_TEXT, EN_CLAIMS)
    try:
        assert "feedback" not in case.hub.audit(case.task_id, shadow=True).report.checks_run
    finally:
        case.close()


# ============================================================================================ OVS-FB-001
def _signed_under_another_key(case, block):
    keyring = case.auditor.keyring
    return block.model_copy(update={"signature": keyring.mac("audit", F.revision_signable_text(block.model_copy(update={"signature": None, "signature_key_id": None})))})


def _fabricated_flaw(case, block):
    """A flaw the channel cannot check (an audit-basis one) that no signed audit holds, in a block re-signed under the
    right key: only the auditor's binding check can catch it."""
    fake = RevisionFlaw(flaw_id=f"f{len(block.flaws) + 1}", code="OVS-FID-004", severity="error", flaw_class="fidelity", basis="audit", rule="src.quote_not_found",
                        params={}, instruction=render_instruction("src.quote_not_found", {}), removal_ok=True,
                        claims=[block.flaws[0].claims[0].model_copy(update={"claim_id": "en-ev1", "text": "We work until the bell"})],
                        evidence=[RevisionEvidence(kind="audit_finding", ref=f"{block.task_audit_id}#000000000000")], signature="c" * 64)
    from epinoic_logic.api.channel import keep_list, named_claim_ids
    flaws = [*block.flaws, fake]
    view = case.auditor.view(case.uid)
    b = block.model_copy(update={"flaws": flaws, "must_not_change": keep_list(view.by_message[case.m.message_id].request,
                                                                               view.by_message[case.a.message_id].report, *named_claim_ids(flaws))})
    return _resigned(b, case.auditor.keyring)


@pytest.mark.parametrize("tamper,accepted", [("unsigned", False), ("another key", True), ("fabricated flaw", True), ("rendered digest", False)])
def test_a_block_that_does_not_verify_or_bind_is_ovs_fb_001_and_nothing_passes(tamper, accepted):
    case = english_case()
    try:
        base = _base(case)
        block = {"unsigned": lambda: base.model_copy(update={"signature": None, "signature_key_id": None}),
                 "another key": lambda: _signed_under_another_key(case, base),
                 "fabricated flaw": lambda: _fabricated_flaw(case, base),
                 "rendered digest": lambda: base.model_copy(update={"rendered_sha256": "d" * 64})}[tamper]()
        m2, _req, rq = _issue(case, block)
        assert (m2 is not None) is accepted, [f.message for f in rq.findings]
        audit = case.hub.audit(case.task_id, shadow=True)
        fb = _fb(audit)
        assert fb and rq.message_id in fb[0].message_ids and audit.transfer_states[rq.message_id] == "AUDIT_FAILED"
        if accepted:
            a2, _rc2 = case.hub.receive(case.task_id, m2.message_id, english_report(EN_TEXT, EN_CLAIMS, report_id="rep-en-2"))
            audit2 = case.hub.audit(case.task_id, shadow=True)
            assert audit2.transfer_states[a2.message_id] == "AUDIT_FAILED"
            resp = case.hub.consolidate(case.task_id, request_message_ids=[case.m.message_id, m2.message_id])
            assert a2.message_id in resp.excluded_message_ids()
    finally:
        case.close()


def test_the_feedback_check_names_why_a_block_does_not_bind():
    case = english_case()
    try:
        view = case.auditor.view(case.uid)
        block = _base(case)
        _m2, _req, rq = _issue(case, block)
        view = case.auditor.view(case.uid)
        t = view.by_message[rq.message_id]
        audits = case.auditor.audits(case.uid)
        assert F.check_revision_request(view, t, case.auditor.keyring, audits) == []
        assert any("no signed task audit" in r for r in F.check_revision_request(view, t, case.auditor.keyring, []))
    finally:
        case.close()


# ============================================================================================ the recorded rounds (when present)
@pytest.mark.parametrize("rd", ["r2", "r3", "r4", "r5", "r6", "r7"])
def test_genuine_blocks_on_a_recorded_round_raise_no_false_alarm_and_the_shadow_agrees(rd):
    """Every genuine first answer of a recorded round (peer-dependent ones aside) through an audited hub: an infrastructure-built revision
    request wherever a flaw is allowlisted, the original text delivered again as its revision under a new report id; no
    request is refused by the channel, no block is OVS-FB-001 and the shadow raises nothing on any revision transfer."""
    if ROUNDS is None or not (ROUNDS / rd / "specialists").is_dir():
        pytest.skip(f"the recorded round {rd} is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
    # the translator's arena tools, reached through the translator checkout (EPINOIC_TRANSLATOR_ROOT in a standalone copy of
    # the sub-project), never by climbing above the sub-project: a standalone copy has no translator above it
    arena = str(require_translator_root() / "scripts" / "arena")
    sys.path.insert(0, arena)
    try:
        import run_arena as RA
    finally:
        sys.path.remove(arena)
    from epinoic_logic.api.branches import RouterHub
    from .conftest import CFG, KEY, make_auditor
    items = [i for i in RA.load_items(ROUNDS / rd / "specialists") if not i.get("peer_of")]
    issued = 0
    for it in items:
        aud = make_auditor()
        hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=aud)
        try:
            plan = RA.group_plan(items, RA.group_of(it))
            hub.open_task(plan)
            m, _r, _q = hub.dispatch(plan.task_id, it["agent_id"], it["question"], RA.supplied(it))
            a, rc = hub.receive(plan.task_id, m.message_id, it["response_text"], agent_id=it["agent_id"], report_id=f"rep-{it['task_id']}-0")
            if a is None:
                continue
            issue = hub.request_revision(plan.task_id, a.message_id)
            assert issue.reason in ("issued", "no_actionable_flaw"), (it["task_id"], issue.reason, issue.receipt and [f.message for f in issue.receipt.findings])
            if not issue.allowed:
                continue
            issued += 1
            hub.receive(plan.task_id, issue.message.message_id, it["response_text"], agent_id=it["agent_id"], report_id=f"rep-{it['task_id']}-rev1")
            audit = hub.audit(plan.task_id, shadow=True)
            assert not _fb(audit), it["task_id"]
            assert not [f for f in audit.report.findings if f.code in SHADOW_CODES], (it["task_id"], [f.message[:200] for f in audit.report.findings if f.code in SHADOW_CODES])
        finally:
            hub.close()
    assert issued >= (1 if rd == "r7" else 0)
