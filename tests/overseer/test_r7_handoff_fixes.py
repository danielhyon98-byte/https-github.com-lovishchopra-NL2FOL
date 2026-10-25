"""Round-7 hand-offs applied on the Overseer's side (the core fixer's changes outside its paths).

* security-1: every signature comparison of the Overseer (the consolidated response, the signed audit, the key ring's
  MACs) is total on untrusted input. ``hmac.compare_digest(str, str)`` raises ``TypeError`` for a forged signature
  holding a non-ASCII or surrogate character; each comparison now reads False and never raises
  (``engine.provenance.signature_matches``).
* security-3 mirror: the channel checks quotations against the router's texts only and names a report text that is not
  byte-identical to a request text with INT-REQ-002 (also when the request sent none). The Overseer's re-derivations read
  the same rule: rule ``request-quotation`` reads only the request's texts, and the receipt expectation for INT-REQ-002
  is the channel's rule, so a channel that fails to reject is caught (OVS-RCPT-004).
* router-envelope-2: a dependent agent's claim stating a check result credited to the system or to a report is a
  self-report (advisory), never evidence. The channel names it with INT-REQ-014; the Overseer's FID-009 reads the same
  statements and names one the receipt does not (a relayed check result is never read as checked).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.overseer import verify_audit, verify_consolidated
from epinoic_logic.overseer.checks.formal import request_quoted_claims
from epinoic_logic.translate.contracts import SuppliedText

from .conftest import DOC, EN_TEXT, HI_INPUT, HI_TEXT, english_report, findings, make_auditor, make_keyring, new_channel, run_task
from .test_consolidation_consolidate import Dup
from .test_hook_hub import audited_hub

FORGED = ("é" * 64, "\ud83d" * 64, "\udc00" + "0" * 63, "A" * 64, "0" * 63, "")


# ============================================================================================ security-1
def test_a_forged_consolidation_signature_holding_non_ascii_text_reads_false_and_never_raises():
    hub = audited_hub()
    try:
        d = Dup(hub)
        d.answer("english-1", name="a")
        r = d.consolidate()
        kr = hub.auditor.keyring
        assert verify_consolidated(r, kr)  # control: the genuine response verifies
        for sig in FORGED:
            assert verify_consolidated(r.model_copy(update={"signature": sig}), kr) is False, repr(sig)
    finally:
        hub.close()


def test_a_forged_audit_signature_holding_non_ascii_text_reads_false_and_never_raises(auditor, keyring):
    audit = run_task(auditor, synthesis=False).audit()
    assert verify_audit(audit, keyring)  # control
    for sig in FORGED:
        assert verify_audit(audit.model_copy(update={"signature": sig}), keyring) is False, repr(sig)


def test_a_key_ring_mac_holding_non_ascii_text_reads_false_and_never_raises():
    kr = make_keyring()
    genuine = kr.mac("journal", "entry")
    assert kr.mac_ok("journal", "entry", genuine)  # control
    for mac in FORGED + (None, 5, b"0" * 64):
        assert kr.mac_ok("journal", "entry", mac) is False, repr(mac)
    assert kr.mac_ok("journal", "entr\ud83d", genuine) is False  # a text with a lone surrogate never raises either


# ============================================================================================ security-3 mirror
FABRICATED = SuppliedText(document_id="doc-fab", title="A text the specialist supplied", author="Anonymous",
                          text="Some say the river carried every secret of the town.")
QUOTE_CLAIMS = [dict(claim_id="en-q", claim_text="the river carried every secret", claim_role="evidence", materiality="supporting",
                     source_refs=[SourceRef(document_id="doc-fab", excerpt="the river carried every secret")])]


def test_rule_request_quotation_reads_only_the_requests_texts_never_a_text_the_report_supplies():
    rep = english_report(text='The question asks whether "the river carried every secret" is a fair reading.', claims=QUOTE_CLAIMS, docs=(FABRICATED,))
    req = SimpleNamespace(user_input='Is "the river carried every secret" a fair reading of the extract?', supplied_texts=[])
    # the fabricated text is no source: the excerpt is found only in the request's words, as the channel counts it
    assert request_quoted_claims(rep, req) == {"en-q"}
    # control: an excerpt the request's own text holds is verified there and is no request quotation
    rep2 = english_report(text='The extract says "We work until the bell".',
                          claims=[dict(claim_id="en-ev1", claim_text="We work until the bell", claim_role="evidence", materiality="supporting",
                                       source_refs=[SourceRef(document_id="doc-mill", excerpt="We work until the bell")])])
    req2 = SimpleNamespace(user_input='Discuss "We work until the bell".', supplied_texts=[DOC])
    assert request_quoted_claims(rep2, req2) == set()


def _send(auditor, report, *, texts, request):
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", request, list(texts))
    _msg, rc = ch.respond(m.message_id, report)
    return rc, auditor.audit(ch.uid)


@pytest.mark.parametrize("texts, docs", [((), (DOC,)), ((DOC,), (SuppliedText(document_id="doc-mill", title="Mill extract", author="Anonymous",
                                                                                  text=DOC.text + " We work until the bell."),))],
                         ids=["the request sent no texts", "a supplied text replaced"])
def test_the_receipt_expectation_for_int_req_002_is_the_channels_rule(monkeypatch, texts, docs):
    request = "Analyse how the writer presents work. Write no more than 80 words."
    a = make_auditor()
    try:
        rc, audit = _send(a, english_report(docs=docs), texts=texts, request=request)
        assert rc.status.value == "REJECTED" and "INT-REQ-002" in [f.code for f in rc.findings]  # the channel's catch
        assert not [f for f in findings(audit, "OVS-RCPT-004") if "INT-REQ-002" in f.message]
    finally:
        a.close()
    # a channel that fails to reject: the Overseer re-derives INT-REQ-002 from the journaled request and report
    monkeypatch.setattr(TranslatorChannel, "_supplied_text_mismatch", staticmethod(lambda *a, **kw: []))
    a = make_auditor()
    try:
        rc, audit = _send(a, english_report(docs=docs), texts=texts, request=request)
        assert rc.status.value != "REJECTED" and "INT-REQ-002" not in [f.code for f in rc.findings]
        named = [f for f in findings(audit, "OVS-RCPT-004") if "INT-REQ-002" in f.message]
        assert named and "doc-mill" in named[0].message and named[0].message_ids == [rc.message_id]
    finally:
        a.close()


# ============================================================================================ router-envelope-2
PEER = SuppliedText(document_id="peer:en", title="English specialist report", author="english-specialist", text=EN_TEXT)
RELAYED = HI_TEXT + " A formal check failed the English report's point, so its reading does not hold."


def _history(auditor, text: str, texts):
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "history-specialist", HI_INPUT, list(texts))
    _msg, rc = ch.respond_text(m.message_id, text, agent_id="history-specialist", report_id="rep-hi-1")
    return rc, auditor.audit(ch.uid)


def test_fid_009_names_a_relayed_check_result_that_no_int_req_014_names(monkeypatch):
    a = make_auditor()
    try:
        rc, audit = _history(a, RELAYED, [PEER])
        f014 = [f for f in rc.findings if f.code == "INT-REQ-014"]
        assert f014 and f014[0].severity == "warning"  # the channel names it ...
        relayed_ids = set(f014[0].claim_ids)
        assert not [f for f in findings(audit, "OVS-FID-009") if set(f.claim_ids) & relayed_ids]  # ... so the Overseer adds nothing
    finally:
        a.close()
    monkeypatch.setattr(TranslatorChannel, "_relayed_check_results", staticmethod(lambda *a, **kw: []))
    a = make_auditor()
    try:
        rc, audit = _history(a, RELAYED, [PEER])
        assert "INT-REQ-014" not in [f.code for f in rc.findings]
        f9 = [f for f in findings(audit, "OVS-FID-009") if set(f.claim_ids) == relayed_ids]
        assert f9 and f9[0].severity == "warning" and "self-report" in f9[0].message and "formal check" in f9[0].message
    finally:
        a.close()


def test_control_the_same_statement_with_no_peer_text_and_a_quoted_check_result_are_not_fid_009(monkeypatch):
    monkeypatch.setattr(TranslatorChannel, "_relayed_check_results", staticmethod(lambda *a, **kw: []))
    a = make_auditor()
    try:
        _rc, audit = _history(a, RELAYED, [])  # no dependent agent: the channel's rule does not apply, nor does the mirror
        assert not [f for f in findings(audit, "OVS-FID-009") if "check result" in f.message]
        quoted = HI_TEXT + ' The pamphlet boasted that "a formal check failed every rival claim".'
        _rc, audit = _history(a, quoted, [PEER])  # the check result is quoted, not stated: masked
        assert not [f for f in findings(audit, "OVS-FID-009") if "check result" in f.message]
    finally:
        a.close()
