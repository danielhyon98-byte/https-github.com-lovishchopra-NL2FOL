"""Integration gate 1, handoff fixer: the overseer reads the channel's new rules as the channel does (core handoff 2a, 2b, 2c).

Core handoff 2c: OVS-FID-009 read the union of two patterns (a check word and an outcome word) on every claim of a dependent
agent, so ordinary subject content about checks ("Automated checks fail when the sensor data are missing", "The receipt
shows the payment failed") was accused although the channel, whose rule now asks for a check of this exchange as the
statement's object, names nothing (INT-REQ-014). The overseer now calls the channel's own rule
(``bus.check_result_statement``) with the object words the channel derives from the peer documents, and reads a peer report
the router supplied under another id, byte-identical to a report delivered on the task, as a peer document too. An
accusation is advisory, but the delivery policy's formal path refuses an answer the task audit names in OVS-FID-009 (rule
``self-report-disclosed``), so a false one withheld a correct answer from the formal label.

Core handoff 2a: a verifier may now declare a claim outside its scope (``channel.bus.CLAIM_OUT_OF_SCOPE``: the channel names
nothing), where ``None`` means it produced no outcome (NOT_ATTEMPTED, INT-REQ-006). The delivery policy's deadline-bound
verifier recorded any value other than ``None`` as ``verified``, so a material claim no check ever reached counted as checked
on the formal path. It is recorded ``no_outcome`` and passed on unchanged, and such an answer is never FORMALLY CHECKED.

Core handoff 2b: the audit's shadow channel served ``None`` for every claim it held no journaled translation for, so it named
NOT_ATTEMPTED where the live channel had named nothing (no verifier, or a claim declared out of scope): OVS-RCPT-008 and
AUDIT_FAILED on a clean transfer. It now leaves unserved exactly the claims the receipt named NOT_ATTEMPTED.
"""
from __future__ import annotations

import pytest

from epinoic_logic.api.channel import TranslatorChannel, CLAIM_OUT_OF_SCOPE
from epinoic_overseer.delivery_policy import DeadlineVerifier, DeliveryPolicy, TranslationStage
from epinoic_logic.api.translate import SuppliedText

from .conftest import EN_TEXT, HI_INPUT, HI_TEXT, findings, make_auditor, new_channel
from .delivery_support import FakeClock, Verifier, physics_report, run_task

PEER = SuppliedText(document_id="peer:en", title="English specialist report", author="english-specialist", text=EN_TEXT)
ORDINARY = [HI_TEXT + " Automated checks fail when the sensor data are missing.",
            HI_TEXT + " The receipt shows the payment failed."]
RELAYED = HI_TEXT + " A formal check failed the English report's point, so its reading does not hold."


def _history(auditor, text: str, texts):
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "history-specialist", HI_INPUT, list(texts))
    _msg, rc = ch.respond_text(m.message_id, text, agent_id="history-specialist", report_id="rep-hi-1")
    return rc, auditor.audit(ch.uid)


def test_ordinary_content_about_checks_is_no_relayed_check_result_for_the_channel_or_the_overseer():
    for text in ORDINARY:
        a = make_auditor()
        try:
            rc, audit = _history(a, text, [PEER])
            assert "INT-REQ-014" not in [f.code for f in rc.findings], text
            assert not [f for f in findings(audit, "OVS-FID-009") if "check result" in f.message], (text, [f.message[:160] for f in findings(audit, "OVS-FID-009")])
        finally:
            a.close()


def test_the_overseer_still_names_a_relayed_check_result_the_channel_failed_to_name(monkeypatch):
    a = make_auditor()
    try:
        rc, _audit = _history(a, RELAYED, [PEER])
        named = {cid for f in rc.findings if f.code == "INT-REQ-014" for cid in f.claim_ids}
        assert named
    finally:
        a.close()
    monkeypatch.setattr(TranslatorChannel, "_relayed_check_results", staticmethod(lambda *a, **kw: []))
    a = make_auditor()
    try:
        _rc, audit = _history(a, RELAYED, [PEER])
        f9 = [f for f in findings(audit, "OVS-FID-009") if set(f.claim_ids) == named]
        assert f9 and "self-report" in f9[0].message and "formal check" in f9[0].message
    finally:
        a.close()


def test_a_claim_the_inner_verifier_declares_out_of_scope_is_recorded_without_outcome_never_verified():
    clock = FakeClock()
    stage = TranslationStage(clock, 240.0)
    rep = physics_report("physics-specialist", "rep-a")
    out = DeadlineVerifier(lambda claim, report: CLAIM_OUT_OF_SCOPE, stage)(rep.claims[1], rep)
    assert out is CLAIM_OUT_OF_SCOPE  # passed on unchanged: the channel names nothing where the verifier asked it not to
    assert [(t.claim_id, t.state) for t in stage.timings] == [("p1.1", "no_outcome")] and stage.labels("verified") == []


def test_an_answer_whose_material_claim_is_outside_the_verifiers_scope_is_never_formally_checked():
    clock = FakeClock()
    verifier = Verifier(clock, outcomes={"p1.1": lambda claim, report: CLAIM_OUT_OF_SCOPE})
    run = run_task(DeliveryPolicy(clock=clock), [("physics-specialist", physics_report("physics-specialist", "rep-a"))], verify=verifier)
    try:
        d, rec = run.decision, run.receipt
        assert d.mode != "formally_checked" and not rec.formal.complete, (d.mode, rec.formal.reasons)
        assert any("NOT_ATTEMPTED" in r for r in rec.formal.reasons), rec.formal.reasons
        [claim] = [c for c in rec.formal.claims if c.claim_id == "p1.1"]
        assert claim.outcome != "clean"
        [rc] = run.receipts.values()
        assert not [f for f in rc.findings if f.code == "INT-REQ-006"], rc.findings  # out of scope: the channel names nothing
    finally:
        run.close()


@pytest.mark.parametrize("verifier", ["no outcome", "out of scope", "no verifier"])
def test_the_shadow_channel_names_not_attempted_exactly_where_the_live_channel_did(verifier):
    fn = {"no outcome": lambda claim, report: None, "out of scope": lambda claim, report: CLAIM_OUT_OF_SCOPE, "no verifier": None}[verifier]
    a = make_auditor()
    try:
        ch = new_channel(a, verify_claim_fn=fn)
        m, _r, _q = ch.request("router", "history-specialist", HI_INPUT)
        _msg, rc = ch.respond_text(m.message_id, HI_TEXT, agent_id="history-specialist", report_id="rep-hi-1")
        named = [f for f in rc.findings if f.code == "INT-REQ-006" and "NOT_ATTEMPTED" in f.message]
        assert bool(named) is (verifier == "no outcome"), rc.findings  # the live channel names only a claim its verifier failed to reach
        audit = a.audit(ch.uid)
        assert not findings(audit, "OVS-RCPT-008"), [f.message[:200] for f in findings(audit, "OVS-RCPT-008")]
    finally:
        a.close()
