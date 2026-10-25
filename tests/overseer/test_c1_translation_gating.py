"""Regression tests for the contained round c1 judges' translator-oversight findings (each fails on the code before the
fix):

* the eligibility re-derivation (TRN-002) and the number and quotation tracing (TRN-005) ran only when the translation
  recorded a provider, so the tampering suite's T22c (a claim the policy rules out forced into IR) and T22f (an invented
  number) cleared with the provider removed, displayed ENTAILED;
* a translation of the model pipeline that carries a problem but no provider is itself reported, unless its translator
  was declared hand-built to the auditor (a configured allowlist the audit records), never because a field is absent;
* the synthetic task's clean baseline now carries faithful translations, so it raises no translation finding.
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

from epinoic_logic.translate.contracts import TranslationStatus  # noqa: E402


def _auditor(**kw):
    return H.new_auditor(H.keyring_for("synthetic"), shadow="off", **kw)


def _stripped(hook):
    """``hook`` with the ProviderInfo removed from every translation it returns (what the judges' J2 and J2b did)."""
    def strip(call):
        out = hook(call) if hook is not None else call.genuine()
        if out is None or out.translation.provider is None:
            return out
        return T.recompose(call, out, provider=None)
    return strip


def _run(name: str, *, strip: bool, **auditor_kw):
    resp, hook, kw = T._trn_variant(name)
    a = _auditor(**auditor_kw)
    run = T.run_synthetic(a, translator_responses=resp, hook=_stripped(hook) if strip else hook, **kw)
    return a, run


def _codes(audit, claim_id: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in audit.report.findings:
        if claim_id in f.claim_ids:
            out.setdefault(f.code, []).append(f)
    return out


@pytest.mark.parametrize("strip", [False, True])
def test_t22c_a_claim_the_policy_rules_out_forced_into_ir_is_trn002_with_or_without_a_provider(strip):
    a, run = _run("T22c", strip=strip)
    try:
        audit = run.audit()
        mid = run.mids["rep_en"]
        f = _codes(audit, "en-an").get("OVS-TRN-002", [])
        assert f and f[0].severity == "error" and "forced into IR" in f[0].message
        assert ("model-path translation without provider" in f[0].message) is strip
        assert audit.transfer_states[mid] == "AUDIT_FAILED"
        rec = next(r for r in audit.translations if r.claim_id == "en-an")
        assert {"eligibility", "trace"} <= set(rec.checks_run)
    finally:
        a.close()


@pytest.mark.parametrize("strip", [False, True])
def test_t22f_an_invented_number_is_trn005_with_or_without_a_provider(strip):
    a, run = _run("T22f", strip=strip)
    try:
        audit = run.audit()
        mid = run.mids["rep_en"]
        f = _codes(audit, "en-point").get("OVS-TRN-005", [])
        assert f and f[0].severity == "warning"
        rec = next(r for r in audit.translations if r.claim_id == "en-point")
        assert "trace" in rec.checks_run and "eligibility" in rec.checks_run
        assert audit.transfer_states[mid] != "AUDIT_PASSED"
        if strip:  # the missing provider is an error of its own: the transfer cannot pass
            assert [x for x in _codes(audit, "en-point").get("OVS-TRN-002", []) if "model-path translation without provider" in x.message]
            assert audit.transfer_states[mid] == "AUDIT_FAILED"
    finally:
        a.close()


def test_a_declared_hand_built_translator_is_recorded_in_the_audit_and_still_traced():
    a = _auditor()
    try:
        run = T.run_synthetic(a, problems={"en-point": T.int_problem("en-point", "work_hours", 12, op="gt", bound=8), "h1.1": T.P_HI})
        audit = run.audit()
        assert audit.coverage.hand_built_translators == list(H.HAND_BUILT_TRANSLATORS)
        assert not _codes(audit, "en-point").get("OVS-TRN-002")  # declared: no provider needed
        assert _codes(audit, "en-point").get("OVS-TRN-005")       # still traced: 12 and 8 are stated nowhere
    finally:
        a.close()
    b = _auditor(hand_built_translators=())  # the same hand-built translation, undeclared
    try:
        run = T.run_synthetic(b, problems={"en-point": T.P_POINT, "h1.1": T.P_HI})
        audit = run.audit()
        assert audit.coverage.hand_built_translators is None
        f = _codes(audit, "en-point").get("OVS-TRN-002", [])
        assert f and "model-path translation without provider" in f[0].message and "'harness'" in f[0].message
    finally:
        b.close()


def test_the_synthetic_baseline_translations_are_faithful_and_raise_no_translation_finding():
    a = _auditor()
    try:
        run = T.run_synthetic(a, problems={"en-point": T.P_POINT, "en-an": T.P_AN, "h1.1": T.P_HI})
        audit = run.audit()
        assert not [f for f in audit.report.findings if f.code.startswith("OVS-TRN")]
        rc = run.receipts["rep_en"]
        shown = {o.claim_id: o.display_status.value for o in rc.outcomes}
        assert shown.get("en-point") == "ENTAILED" and shown.get("en-an") == "ENTAILED"
    finally:
        a.close()
    b = _auditor()
    try:  # the missing link left out: the engine reports it, and that is the honest result, not a translation fault
        run = T.run_synthetic(b, problems={"en-point": T.P_FALSE, "h1.1": T.P_HI})
        rc = run.receipts["rep_en"]
        assert {o.claim_id: o.display_status.value for o in rc.outcomes}.get("en-point") == "COUNTEREXAMPLE"
        assert not [f for f in run.audit().report.findings if f.code.startswith("OVS-TRN")]
    finally:
        b.close()


def test_status_faults_keeps_its_earlier_keyword_but_no_longer_gates_on_it():
    """``status_faults(..., model_proposed=...)`` is still accepted (callers of the earlier signature) and changes
    nothing: the re-derivation depends on the policy version only."""
    from epinoic_logic.overseer.checks.translation import status_faults
    resp, hook, _kw = T._trn_variant("T22c")
    a = _auditor()
    try:
        run = T.run_synthetic(a, translator_responses=resp, hook=hook)
        tr = next(t for t in run.transfers("response") if t.message_id == run.mids["rep_en"])
        o = next(o for o in tr.receipt.outcomes if o.claim_id == "en-an")
        claim = next(c for c in tr.report.claims if c.claim_id == "en-an")
        assert o.translation.status is TranslationStatus.TRANSLATED
        for flag in (True, False, None):
            faults, rederived = status_faults(o, claim, model_proposed=flag)
            assert rederived and any("forced into IR" in x for x in faults)
    finally:
        a.close()
