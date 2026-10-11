"""L3 results and L4/R2 formal checks: every cited result is a signed engine run of the problem it names, inside this
task, reported as the signed result has it, on the problem the payload yields."""
from __future__ import annotations

import dataclasses

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel.contracts import ConstraintResult
from epinoic_logic.engine import verify
from epinoic_logic.engine.provenance import sign_result
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.overseer import EngineKey, KeyRing, ResultStore
from epinoic_logic.translate.outcome import compose_outcome

from .conftest import (
    CFG, DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, HI_TEXT, KEY, OTHER_KEY, SECRET, english_report, findings, int_problem, make_auditor, make_keyring,
    new_channel, outcome_for, ovs_errors, problems_fn, translation_for,
)

P_POINT = int_problem("en-point", "work_hours", 12, op="gt", bound=8)       # ENTAILED
P_FALSE = int_problem("en-point", "work_hours", 5, op="gt", bound=8)        # COUNTEREXAMPLE
P_AN = int_problem("en-an", "fuel", 3, op="ge", bound=1)                     # ENTAILED


def _exchange(auditor, verify_fn, report=None, *, ch=None):
    ch = ch or new_channel(auditor)
    ch.channel.verify_claim_fn = verify_fn
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    msg, rc = ch.respond(m.message_id, report or english_report())
    return ch, rc


def _codes_for(audit, mid):
    return {f.code for f in audit.report.findings if mid in f.message_ids}


# ------------------------------------------------------------------------------------------- controls
def test_genuine_outcomes_pass_l3(auditor):
    ch, rc = _exchange(auditor, problems_fn({"en-point": P_POINT, "en-an": P_AN}))
    assert {o.display_status.value for o in rc.outcomes} == {"ENTAILED"}
    audit = auditor.audit(ch.uid)
    assert not ovs_errors(audit, allow=()), [(f.code, f.message) for f in audit.report.findings]
    assert audit.coverage.results_signature_verified >= 2


# ------------------------------------------------------------------------------------------- RES
def test_t3_another_claims_result_is_res_004_and_res_009(auditor):
    def swap(out, claim, report):
        if claim.claim_id != "en-point":
            return out
        other_claim = next(c for c in report.claims if c.claim_id == "en-an")
        other = outcome_for(other_claim, report, P_AN)
        return out.model_copy(update={"verification": other.verification, "display_status": other.verification.status})
    ch, rc = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=swap))
    audit = auditor.audit(ch.uid)
    f4, f9 = findings(audit, "OVS-RES-004"), findings(audit, "OVS-RES-009")
    assert f4 and f4[0].claim_ids == ["en-point"] and f4[0].message_ids == [rc.message_id] and "another" in f4[0].message
    assert f9 and f9[0].claim_ids == ["en-point"] and "INTERNAL_ERROR" in f9[0].message
    assert audit.transfer_states[rc.message_id] == "AUDIT_FAILED"


def test_t3b_a_result_from_another_task_is_res_005(auditor):
    ch1, rc1 = _exchange(auditor, problems_fn({"en-point": P_POINT}))
    foreign = rc1.outcomes[0].verification

    def reuse(_out, claim, report):
        return compose_outcome(claim, translation_for(claim, report, P_POINT), foreign, signing_key=KEY, key_id="t")
    ch2, rc2 = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=reuse))
    f = findings(auditor.audit(ch2.uid), "OVS-RES-005")
    assert f and f[0].formal_result_id == foreign.result_id and "another channel" in f[0].message and f[0].claim_ids == ["en-point"]
    assert not findings(auditor.audit(ch1.uid), "OVS-RES-005")


def test_a_caching_translator_reusing_an_identical_result_is_recorded_not_accused(auditor):
    cache = {}

    def caching(out, claim, report):
        if claim.claim_id not in cache:
            cache[claim.claim_id] = out.verification
            return out
        return compose_outcome(claim, translation_for(claim, report, P_POINT), cache[claim.claim_id], signing_key=KEY, key_id="t")
    ch, rc1 = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=caching))
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT + " Again.", [DOC])
    _msg, rc2 = ch.respond(m.message_id, english_report(report_id="rep-en-2", created_at="2026-10-11T11:30:00Z"))
    rid = rc1.outcomes[0].verification.result_id
    assert rc2.outcomes[0].verification.result_id == rid
    audit = auditor.audit(ch.uid)
    assert not findings(audit, "OVS-RES-005") and rid in audit.coverage.reused_results


def test_t3c_an_old_result_reused_for_a_changed_claim_text(auditor, monkeypatch):
    cache = {}
    text2 = EN_TEXT.replace("as endless", "as relentless")

    def stale(out, claim, report, *, digest):
        if claim.claim_id not in cache:
            cache[claim.claim_id] = out.verification
            return out
        tr = translation_for(claim, report, P_POINT, text_digest=digest)
        return compose_outcome(claim, tr.model_copy(update={"claim_text_sha256": None}), cache[claim.claim_id], signing_key=KEY, key_id="t").model_copy(update={"translation": tr})
    claims2 = [dict(c) for c in EN_CLAIMS]
    claims2[0] = dict(claims2[0], claim_text="The writer presents work as relentless")
    # (a) no text digest on the translation: the channel cannot tell; the reuse of an earlier event's result is RES-005
    ch, _rc1 = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=lambda o, c, r: stale(o, c, r, digest=None)))
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT + " Again.", [DOC])
    _msg, rc2 = ch.respond(m.message_id, english_report(text2, claims2, report_id="rep-en-2", created_at="2026-10-11T11:30:00Z"))
    f5 = [f for f in findings(auditor.audit(ch.uid), "OVS-RES-005") if rc2.message_id in f.message_ids]
    assert f5 and f5[0].claim_ids == ["en-point"] and "another text" in f5[0].message
    # (b) the translation carries the OLD text's digest and the channel's stale check is patched out: RES-010
    monkeypatch.setattr(TranslatorChannel, "_stale_translation", staticmethod(lambda *a, **k: None))
    from epinoic_logic.translate.contracts import sha256_text
    cache.clear()
    old_digest = sha256_text("The writer presents work as endless")
    ch2, _rc = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=lambda o, c, r: stale(o, c, r, digest=old_digest)))
    m2, _r2, _q2 = ch2.request("router", "english-specialist", EN_INPUT + " Again.", [DOC])
    _msg2, rc3 = ch2.respond(m2.message_id, english_report(text2, claims2, report_id="rep-en-2", created_at="2026-10-11T11:30:00Z"))
    f10 = [f for f in findings(auditor.audit(ch2.uid), "OVS-RES-010") if rc3.message_id in f.message_ids]
    assert f10 and f10[0].claim_ids == ["en-point"] and "claim text" in f10[0].message


def test_t4_stripped_signature_and_entailed_written_is_res_003_and_res_009(auditor):
    def forge(out, claim, report):
        v = out.verification.model_copy(update={"signature": None, "signature_key_id": None, "status": S.ENTAILED})
        return out.model_copy(update={"verification": v, "display_status": S.ENTAILED})
    ch, rc = _exchange(auditor, problems_fn({"en-point": P_FALSE}, transform=forge))
    assert rc.outcomes[0].display_status is S.ENTAILED  # the channel delivers it (G5)
    audit = auditor.audit(ch.uid)
    assert {"OVS-RES-003", "OVS-RES-009"} <= _codes_for(audit, rc.message_id)
    f3 = findings(audit, "OVS-RES-003")[0]
    assert "unsigned" in f3.message and f3.formal_result_id == rc.outcomes[0].verification.result_id and f3.message_ids == [rc.message_id]
    assert not findings(audit, "OVS-RES-006")  # the forged copy is named by RES-003, not double-counted
    assert audit.transfer_states[rc.message_id] == "AUDIT_FAILED"


def test_t4b_signed_with_a_wrong_key_is_res_003(auditor):
    def wrong_key(out, claim, report):
        v = sign_result(out.verification.model_copy(update={"signature": None, "signature_key_id": None}), OTHER_KEY, "t")
        return out.model_copy(update={"verification": v})
    ch, rc = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=wrong_key))
    f = findings(auditor.audit(ch.uid), "OVS-RES-003")
    assert f and "does not verify" in f[0].message and f[0].message_ids == [rc.message_id]


def test_t4c_a_result_signed_outside_the_engine_path_is_res_001(auditor):
    pre = verify(P_POINT, CFG, signing_key=KEY, key_id="t")  # outside any channel call: never captured

    def outside(_out, claim, report):
        return compose_outcome(claim, translation_for(claim, report, P_POINT), pre, signing_key=KEY, key_id="t")
    ch, rc = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=outside))
    f = findings(auditor.audit(ch.uid), "OVS-RES-001")
    assert f and f[0].formal_result_id == pre.result_id and f[0].claim_ids == ["en-point"]


def test_an_undeclared_key_id_is_res_003(auditor):
    def undeclared(out, claim, report):
        v = verify(P_POINT, CFG, signing_key=KEY, key_id="mystery")
        return compose_outcome(claim, translation_for(claim, report, P_POINT), v, signing_key=KEY, key_id="mystery")
    ch, rc = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=undeclared))
    f = findings(auditor.audit(ch.uid), "OVS-RES-003")
    assert f and "undeclared" in f[0].message


def test_a_declared_key_without_a_secret_is_audit_004():
    ring = KeyRing({"hub": EngineKey(KEY), "integrity": EngineKey(KEY), "t": EngineKey(None)}, SECRET)
    auditor = make_auditor(keyring=ring)
    try:
        ch, rc = _exchange(auditor, problems_fn({"en-point": P_POINT}))
        audit = auditor.audit(ch.uid)
        f = findings(audit, "OVS-AUDIT-004")
        assert f and f[0].severity == "error" and "'t'" in f[0].message
        assert not findings(audit, "OVS-RES-003")  # not verifiable is reported as such, never as forged
        assert audit.state == "AUDIT_FAILED"
    finally:
        auditor.close()


def test_a_receipt_copy_that_is_validly_signed_but_different_is_res_006(auditor):
    def resign(out, claim, report):
        v = sign_result(out.verification.model_copy(update={"reason_unknown": "edited after the run", "signature": None, "signature_key_id": None}), KEY, "t")
        return out.model_copy(update={"verification": v})
    ch, rc = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=resign))
    audit = auditor.audit(ch.uid)
    f = findings(audit, "OVS-RES-006")
    assert f and f[0].formal_result_id == rc.outcomes[0].verification.result_id and not findings(audit, "OVS-RES-003")


def test_an_evicted_result_is_res_002_not_an_accusation():
    kr = make_keyring()
    auditor = make_auditor(keyring=kr, store=ResultStore(kr, max_results=1))
    try:
        ch, rc = _exchange(auditor, problems_fn({"en-point": P_POINT}))
        audit = auditor.audit(ch.uid)
        f = findings(audit, "OVS-RES-002")
        assert f and all(x.severity == "warning" for x in f) and "evicted" in f[0].message
        assert not {"OVS-RES-001", "OVS-RES-005", "OVS-RCPT-006"} & {x.code for x in audit.report.findings}
    finally:
        auditor.close()


# ------------------------------------------------------------------------------------------- FORM
_LONG_TEXT = EN_TEXT + " " + " ".join(["The labour never stops and the hours repeat."] * 9)


def test_t5b_entailed_written_over_a_counterexample_is_form_001_and_form_002(auditor, monkeypatch):
    orig = TranslatorChannel._constraints

    def rosy(self, req, report):
        results, ids = orig(self, req, report)
        return [c.model_copy(update={"formal_status": "ENTAILED", "satisfied": True}) if c.formal_status == "COUNTEREXAMPLE" else c for c in results], ids
    monkeypatch.setattr(TranslatorChannel, "_constraints", rosy)
    ch, rc = _exchange(auditor, None, english_report(_LONG_TEXT))
    assert all(c.satisfied is not False for c in rc.constraint_results)
    audit = auditor.audit(ch.uid)
    f1, f2 = findings(audit, "OVS-FORM-001"), findings(audit, "OVS-FORM-002")
    assert f1 and f2 and f1[0].message_ids == [rc.message_id] and "COUNTEREXAMPLE" in f1[0].message
    assert f1[0].formal_result_id == f2[0].formal_result_id


def test_control_genuine_counterexample_constraint_is_not_accused(auditor):
    ch, rc = _exchange(auditor, None, english_report(_LONG_TEXT))
    assert any(c.satisfied is False for c in rc.constraint_results)
    assert not ovs_errors(auditor.audit(ch.uid), allow=())


def test_t5c_constraint_encoded_with_a_wrong_measurement_is_form_003(auditor, monkeypatch):
    import epinoic_logic.channel.bus as bus
    monkeypatch.setattr(bus, "count_answer_words", lambda text: (7, 0))
    ch, rc = _exchange(auditor, None, english_report())
    audit = auditor.audit(ch.uid)
    f = findings(audit, "OVS-FORM-003")
    assert f and f[0].message_ids == [rc.message_id] and "MEASURED" in f[0].message


def _history(auditor, patch=None, monkeypatch=None):
    ch = new_channel(auditor)
    if patch is not None:
        monkeypatch.setattr(TranslatorChannel, "_branch_checks", patch)
    m, _r, _q = ch.request("router", "history-specialist", "Explain the Factory Act of 1833.", [])
    _msg, rc = ch.respond_text(m.message_id, HI_TEXT, agent_id="history-specialist", report_id="rep-hi-1")
    return ch, rc


def test_history_control_has_a_sound_chronology_check(auditor):
    ch, rc = _history(auditor)
    assert [(c.constraint_id, c.formal_status, c.satisfied) for c in rc.formal_checks] == [("core-chronology-1", "ENTAILED", True)]
    assert not ovs_errors(auditor.audit(ch.uid), allow=())


def test_t5d_a_suppressed_pack_check_is_form_004(auditor, monkeypatch):
    orig = TranslatorChannel._branch_checks

    def suppress(self, report, req, findings, *a, **kw):
        structural, formal, ids = orig(self, report, req, findings, *a, **kw)
        return structural, [], []
    ch, rc = _history(auditor, suppress, monkeypatch)
    f = findings(auditor.audit(ch.uid), "OVS-FORM-004")
    assert f and "core-chronology-1" in f[0].message and f[0].message_ids == [rc.message_id]


def test_branch_satisfied_flipped_is_form_002_from_r2(auditor, monkeypatch):
    orig = TranslatorChannel._branch_checks

    def flip(self, report, req, findings, *a, **kw):
        structural, formal, ids = orig(self, report, req, findings, *a, **kw)
        return structural, [c.model_copy(update={"satisfied": None}) for c in formal], ids
    ch, rc = _history(auditor, flip, monkeypatch)
    f = findings(auditor.audit(ch.uid), "OVS-FORM-002")
    assert f and "expected_if_sound ENTAILED" in f[0].message


def test_a_formal_check_decided_on_another_problem_is_form_003(auditor, monkeypatch):
    orig = TranslatorChannel._branch_checks

    def other_problem(self, report, req, findings, *a, **kw):
        structural, formal, ids = orig(self, report, req, findings, *a, **kw)
        res = verify(int_problem("rep-hi-1:chronology-1", "later_event", 2, op="gt", bound=1, request_id=report.request_id, problem_id="chron-rep-hi-1-1"),
                     self.config, signing_key=self.key, key_id=self.key_id)
        return structural, [c.model_copy(update={"formal_result_id": res.result_id}) for c in formal], [res.result_id]
    ch, rc = _history(auditor, other_problem, monkeypatch)
    f = findings(auditor.audit(ch.uid), "OVS-FORM-003")
    assert f and "core-chronology-1" in f[0].message


def test_two_contents_captured_under_one_result_id_is_res_006(auditor):
    from epinoic_logic.engine.sink import emit

    def twin(out, claim, report):
        twin_result = sign_result(out.verification.model_copy(update={"reason_unknown": "a second content", "signature": None, "signature_key_id": None}), KEY, "t")
        emit(twin_result, P_POINT)  # an insider puts a second content under the same id into the capture
        return out
    ch, rc = _exchange(auditor, problems_fn({"en-point": P_POINT}, transform=twin))
    f = findings(auditor.audit(ch.uid), "OVS-RES-006")
    assert f and f[0].formal_result_id == rc.outcomes[0].verification.result_id and "two different contents" in f[0].message
