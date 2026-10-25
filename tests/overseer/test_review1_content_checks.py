"""Regression tests for the content-check defects found by adversarial review round 1 of the Overseer.

Joint consistency (a delivered outcome the channel never pooled; pool_after precedence for a named conflict; findings
scoped by report when claim ids repeat across reports), peer documents with swapped attributions, a report relayed in
a specialist's name that it never delivered, rule-divergence attribution and performed-entailment evidence, fidelity
(joined list markers, cut claims, sentence parse loss and the auditor's re-parse), external results decided alike in
both tiers, grounded transcriptions under TRN-006, the ledger on STEM notation, number words and the student-facing
text, and the release gate.
"""
from __future__ import annotations

from datetime import datetime, timezone

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.engine import sink, verify
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim
from epinoic_logic.integrity.ledger import check_synthesis_ledger, figure_pairing_differences, figure_spellings
from epinoic_logic.ir.schema import Problem
from epinoic_logic.overseer import EngineKey, may_release
from epinoic_logic.overseer.checks import CheckContext, normalise
from epinoic_logic.overseer.checks.fidelity import claim_occurs, uncut_text
from epinoic_logic.overseer.policy import release_decision
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.outcome import compose_outcome

from .conftest import (
    CFG, DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, HI_INPUT, HI_TEXT, KEY, default_synthesis, english_report, findings, int_problem, make_auditor, make_keyring,
    make_plan, new_channel, problems_fn, run_task, translation_for,
)
from .test_audit_joint_divergence import _merged_synthesis


def _errors(audit) -> set[str]:
    return {f.code for f in audit.report.findings if f.severity == "error"}


# ============================================================================================ joint consistency
def test_a_delivered_outcome_the_channel_never_pooled_is_joint_004_and_its_contradiction_is_checked(auditor, monkeypatch):
    orig = TranslatorChannel._verify_claims

    def unpooled(self, report, findings_, *, pool=True, **kw):  # the merged channel also passes the task record (task=)
        return orig(self, report, findings_, pool=pool and report.agent_id != "history-specialist", **kw)
    monkeypatch.setattr(TranslatorChannel, "_verify_claims", unpooled)
    task = run_task(auditor, en_problems={"en-point": int_problem("en-point", "x", 7, op="gt", bound=5)},
                    hi_problems={"h1.1": int_problem("h1.1", "x", 2, op="lt", bound=3)}, peer=False, synthesis=False)
    rc = task.receipts["rep_hi"]
    assert not any(f.code.startswith("INT-CONFLICT") for f in rc.findings)  # the channel never saw the contradiction
    clr = auditor.clearance(task.uid, rc.message_id, receipt=rc)
    assert clr.state == "AUDIT_FAILED" and "OVS-JOINT-004" in clr.codes
    audit = task.audit(shadow=False)
    j1 = findings(audit, "OVS-JOINT-001")
    assert j1 and set(j1[0].claim_ids) == {"en-point", "h1.1"} and audit.coverage.joint_pool_size == 2


def _self_refuting(claim_id: str) -> Problem:
    V = {"op": "var", "name": "y"}
    return Problem.model_validate({
        "problem_id": f"p-{claim_id}", "request_id": "req-ovs", "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": "y", "sort": "Int", "meaning": "the count the claim states"}],
        "premises": [{"id": "A", "expr": {"op": "eq", "left": V, "right": {"op": "int", "value": "2"}}, "grounding": {"kind": "arithmetic_fact"}},
                     {"id": "B", "expr": {"op": "eq", "left": V, "right": {"op": "int", "value": "3"}}, "grounding": {"kind": "arithmetic_fact"}}],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": V, "right": {"op": "int", "value": "0"}}},
    })


def _two_reports_sharing_claim_ids(auditor):
    """english-specialist delivers rep-a (g1.1 consistent, g1.2), then english-2 delivers rep-b whose g1.1 refutes itself."""
    plan = make_plan(selected_agent_ids=["english-specialist", "english-2", "combinator"], agent_subjects={}, agent_task_types={})
    claims = [dict(claim_id="g1.1", claim_text="The writer presents work as endless", claim_role="point", materiality="material"),
              dict(claim_id="g1.2", claim_text="time itself is paid in fuel", claim_role="interpretation", materiality="supporting")]
    ch = new_channel(auditor, plan)
    ch.channel.verify_claim_fn = problems_fn({"g1.1": int_problem("g1.1", "x", 7, op="gt", bound=5), "g1.2": int_problem("g1.2", "z", 4, op="gt", bound=1)})
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _ra, rca = ch.respond(m.message_id, english_report(claims=claims, report_id="rep-a"))
    ch.channel.verify_claim_fn = problems_fn({"g1.1": _self_refuting("g1.1")})
    m2, _r2, _q2 = ch.request("router", "english-2", EN_INPUT, [DOC])
    _rb, rcb = ch.respond(m2.message_id, english_report(claims=claims[:1], report_id="rep-b", agent="english-2"))
    return ch, rca, rcb


def test_a_named_self_refuting_claim_is_rerun_at_the_version_the_receipt_named(auditor):
    ch, rca, rcb = _two_reports_sharing_claim_ids(auditor)
    assert any(f.code == "INT-CONFLICT-005" and "g1.1" in f.claim_ids for f in rcb.findings)
    audit = auditor.audit(ch.uid)
    assert not findings(audit, "OVS-JOINT-003")  # the pool_before version (rep-a's consistent g1.1) is not what was named
    assert audit.transfer_states[rca.message_id] != "AUDIT_FAILED"


def test_findings_about_a_shared_claim_id_name_only_the_report_they_concern(auditor):
    ch, rca, rcb = _two_reports_sharing_claim_ids(auditor)
    ctx = CheckContext(view=auditor.view(ch.uid), keyring=auditor.keyring, store=auditor.store)
    assert ctx.message_ids_for_claims(["g1.1"], pairs=[("rep-b", "g1.1")])[0] == [rcb.message_id]
    assert ctx.message_ids_for_claims(["g1.1"], report_ids=["rep-a"])[0] == [rca.message_id]
    assert sorted(ctx.message_ids_for_claims(["g1.1"])[0]) == sorted([rca.message_id, rcb.message_id])  # unqualified: every report carrying it


# ============================================================================================ peer documents and relays
def _peer_request(auditor, author: str, document_id: str = "peer:en"):
    task = run_task(auditor, synthesis=False)
    report = SpecialistReport.model_validate(task.messages["rep_en"].payload)
    doc = SuppliedText(document_id=document_id, title="English specialist report", author=author, text=report.original_response)
    m, _r, rq = task.ch.request("router", "history-specialist", HI_INPUT + " Again.", [doc])
    return task, m, rq


def test_a_peer_document_attributed_to_another_author_is_peer_002(auditor):
    task, m, rq = _peer_request(auditor, author="english-2")
    clr = auditor.clearance(task.uid, m.message_id, receipt=rq)
    assert clr.state == "AUDIT_FAILED" and "OVS-PEER-002" in clr.codes
    f = [x for x in findings(task.audit(), "OVS-PEER-002") if m.message_id in x.message_ids]
    assert f and "author" in f[0].message


def test_control_a_peer_document_with_its_own_attribution_is_peer_003_only(auditor):
    task, m, rq = _peer_request(auditor, author="english-specialist")
    clr = auditor.clearance(task.uid, m.message_id, receipt=rq)
    assert clr.state == "AUDIT_PASSED_WITH_FINDINGS" and clr.codes == ["OVS-PEER-003"]


def test_a_report_relayed_in_a_specialists_name_that_it_never_delivered_is_peer_001(auditor):
    """Since the round-7 core fix (router-envelope-3) the channel itself refuses the relay: a specialist cannot relay a
    report it never delivered (INT-HANDOFF-013, REJECTED, no channel state change), which ``checks/peer.py`` reads as the
    channel doing its job (no PEER-001). PEER-001 stays the Overseer's defence against a channel whose state was
    corrupted: with the fabricated report seeded into the channel's ``transmitted_reports`` (the journal still records
    no delivery of it) the relay passes the channel and the audit fails it. (Rewritten to the stricter rule: the channel's
    refusal is asserted in addition to the Overseer's catch.)"""
    task = run_task(auditor, synthesis=False, peer=False)
    claims = [dict(c) for c in EN_CLAIMS]
    claims[0] = dict(claims[0], claim_text="The writer presents work as joyful")
    fake = english_report(EN_TEXT.replace("presents work as endless", "presents work as joyful"), claims, report_id="rep-en-1b")
    _m, rc = task.ch.relay("english-specialist", AgentRole.SPECIALIST, "history-specialist", AgentRole.SPECIALIST, fake)
    assert rc.status.value == "REJECTED" and "INT-HANDOFF-013" in [f.code for f in rc.findings]
    assert fake.report_id not in task.ch.channel.transmitted_reports  # no channel state change
    assert not [f for f in findings(task.audit(), "OVS-PEER-001") if rc.message_id in f.message_ids]
    # a channel whose state was corrupted: the fabricated report is held as if delivered, the journal has no delivery of it
    task.ch.channel.transmitted_reports[fake.report_id] = fake
    _m, rc = task.ch.relay("english-specialist", AgentRole.SPECIALIST, "history-specialist", AgentRole.SPECIALIST, fake)
    assert rc.status.value != "REJECTED"
    clr = auditor.clearance(task.uid, rc.message_id, receipt=rc)
    assert clr.state == "AUDIT_FAILED" and "OVS-PEER-001" in clr.codes


def test_control_a_specialist_handing_on_its_own_delivered_report_is_not_peer_001(auditor):
    task = run_task(auditor, synthesis=False, peer=False)
    held = SpecialistReport.model_validate(task.messages["rep_en"].payload)
    _m, rc = task.ch.relay("english-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, held)
    assert not [f for f in findings(task.audit(), "OVS-PEER-001") if rc.message_id in f.message_ids]


# ============================================================================================ rule divergence
def test_a_synthesis_rule_divergence_names_only_the_synthesis_never_the_genuine_reports(auditor, monkeypatch):
    # review round 2: a channel that states the unperformed check gets DIV-002 (asserted in test_audit_joint_divergence);
    # here the channel states nothing, so the divergence is DIV-001 and must still name the synthesis only
    monkeypatch.setattr(TranslatorChannel, "_state_synthesis_checks", staticmethod(lambda findings, checked: list(findings)))
    monkeypatch.setattr(TranslatorChannel, "_unchecked_paraphrases", staticmethod(lambda *a, **k: []))
    task = run_task(auditor, synthesis_obj=_merged_synthesis())
    audit = task.audit()
    f = [x for x in findings(audit, "OVS-DIV-001") if "INT-SYNTH-006" in x.message]
    assert f and f[0].message_ids == [task.mids["syn"]] and {"en-point", "h1.1"} <= set(f[0].claim_ids)
    for k in ("rep_en", "rep_hi", "fwd", "req_en", "req_hi"):
        assert audit.transfer_states[task.mids[k]] != "AUDIT_FAILED", k
    assert audit.transfer_states[task.mids["syn"]] == "AUDIT_FAILED"


def _borrowing_finish(monkeypatch, donor: dict):
    """The synthesis receipt's INT-LEDGER-011 cites a result borrowed from the English report's delivery (installed after
    that delivery): an id alone, of an earlier event, claiming a check nobody ran on the synthesis."""
    orig = TranslatorChannel._finish

    def fin(self, msg, direction, findings_, *a, **kw):
        findings_ = [f.model_copy(update={"formal_result_id": donor["rid"]}) if f.code == "INT-LEDGER-011" and not f.formal_result_id and donor else f for f in findings_]
        return orig(self, msg, direction, findings_, *a, **kw)

    def before(task):
        donor["rid"] = next(o.verification.result_id for o in task.receipts["rep_en"].outcomes if o.verification is not None)
        monkeypatch.setattr(TranslatorChannel, "_finish", fin)
    return before


def test_a_borrowed_result_id_on_int_ledger_011_is_not_evidence_that_the_entailment_check_ran(auditor, monkeypatch):
    # the translator merge: the merged channel also states a merged claim's content change unchecked (INT-SYNTH-012, a
    # disclosure, so the divergence is DIV-002: the next test). Here the channel states nothing beyond INT-LEDGER-011, as
    # the pre-merge channel did for a merged claim, so the undisclosed divergence is DIV-001 as before
    monkeypatch.setattr(TranslatorChannel, "_unchecked_paraphrases", staticmethod(lambda *a, **k: []))
    donor = {}
    orig = TranslatorChannel._finish

    def fin(self, msg, direction, findings_, *a, **kw):
        findings_ = [f.model_copy(update={"formal_result_id": donor["rid"]}) if f.code == "INT-LEDGER-011" and not f.formal_result_id and donor else f for f in findings_]
        return orig(self, msg, direction, findings_, *a, **kw)

    def before(task):
        donor["rid"] = next(o.verification.result_id for o in task.receipts["rep_en"].outcomes if o.verification is not None)
        monkeypatch.setattr(TranslatorChannel, "_finish", fin)
    task = run_task(auditor, synthesis_obj=_merged_synthesis(), before_synthesis=before)
    assert any(f.code == "INT-LEDGER-011" and f.formal_result_id == donor["rid"] for f in task.receipts["syn"].findings)
    assert not any(f.code == "INT-SYNTH-012" for f in task.receipts["syn"].findings)
    audit = task.audit()
    assert [x for x in findings(audit, "OVS-DIV-001") if "INT-SYNTH-006" in x.message]  # not taken as performed
    assert [x for x in findings(audit, "OVS-RES-005") if x.formal_result_id == donor["rid"] and task.mids["syn"] in x.message_ids]


def test_a_borrowed_result_id_beside_the_merged_channel_s_own_disclosure_is_still_not_evidence(auditor, monkeypatch):
    """The translator merge: the merged channel's receipt states the merged claim's content change NOT checked
    (INT-SYNTH-012, citing no result), so the router was told and the divergence is DIV-002, never silence: the borrowed
    id on INT-LEDGER-011 is still not taken as the check performed (a performed check removes the divergence), and the
    borrowing itself is RES-005."""
    donor: dict = {}
    task = run_task(auditor, synthesis_obj=_merged_synthesis(), before_synthesis=_borrowing_finish(monkeypatch, donor))
    syn = task.receipts["syn"].findings
    assert any(f.code == "INT-LEDGER-011" and f.formal_result_id == donor["rid"] for f in syn)
    assert any(f.code == "INT-SYNTH-012" and not f.formal_result_id and f.claim_ids[0] == "s1" for f in syn)
    audit = task.audit()
    assert not [x for x in findings(audit, "OVS-DIV-001") if "INT-SYNTH-006" in x.message]
    d = [x for x in findings(audit, "OVS-DIV-002") if "INT-SYNTH-006" in x.message]
    assert d and "states the check as NOT performed" in d[0].message and d[0].message_ids == [task.mids["syn"]]
    assert [x for x in findings(audit, "OVS-RES-005") if x.formal_result_id == donor["rid"] and task.mids["syn"] in x.message_ids]
    assert audit.transfer_states[task.mids["syn"]] == "AUDIT_FAILED"  # the borrowed citation fails the synthesis


# ============================================================================================ fidelity
def test_rule_joined_list_markers():
    assert claim_occurs("Why these marks: - A 3: a sound literal grasp of the scene.", normalise("Why these marks:\n- A 3: a sound literal grasp of the scene."))
    assert claim_occurs("The reader feels the scene is playful and menacing. 2.", normalise("1. The reader feels the scene is playful and menacing.\n2. The end."))
    assert normalise("It rose to 7. 2. Then") == "It rose to 7. Then" and normalise("Score: 7.") == "Score: 7."


_LIST_TEXT = ('The writer presents work as endless here. The line "We work until the bell" carries the effect.\n'
              'Why this matters:\n- The words "counted every hour in coal" sound grim.\n- The words "We work until the bell" sound final.\n'
              '1. The reader feels the scene is weary and bleak.\n2. The reader feels the scene is hollow and earnest.')


def test_a_genuine_answer_with_bulleted_and_numbered_lists_gives_no_fidelity_error(auditor):
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _reply, rc = ch.respond_text(m.message_id, _LIST_TEXT, agent_id="english-specialist", report_id="rep-list")
    assert rc.status.value != "REJECTED"
    audit = auditor.audit(ch.uid)
    assert not [f for f in audit.report.findings if f.code in ("OVS-FID-001", "OVS-FID-003")]


def test_rule_contract_cut_reads_no_partial_figure():
    from epinoic_logic.adapters.markdown import MAX_CLAIM_TEXT_CHARS, truncate_claim_text
    sentence = "The district totals were " + ", ".join(str(100000 + i) for i in range(700)) + "."
    cut = truncate_claim_text(sentence)
    assert len(cut) >= MAX_CLAIM_TEXT_CHARS - 3 and cut.endswith("...")
    stated = set().union(*(k for _l, k in figure_spellings(sentence)))
    from epinoic_logic.overseer.checks.fidelity import _claim_figures
    assert all(keys & stated for _label, keys in _claim_figures(cut))
    assert uncut_text("short claim.") == "short claim."


def test_an_adapter_that_drops_a_judgement_sentence_is_named_by_the_reparse_with_the_shadow_off(monkeypatch):
    auditor = make_auditor(shadow="off")
    try:
        orig = TranslatorChannel._branch_for

        def branch_for(self, agent_id):
            b, prof = orig(self, agent_id)
            if agent_id != "history-specialist":
                return b, prof

            class Wrapped:
                def __getattr__(s, n):
                    return getattr(b, n)

                def parser(s):
                    p = b.parser()

                    class P:
                        def parse_response(s2, text, **kw):
                            rep = p.parse_response(text, **kw)
                            return rep.model_copy(update={"claims": [c for c in rep.claims if "On balance" not in c.claim_text]})
                    return P()
            return Wrapped(), prof
        monkeypatch.setattr(TranslatorChannel, "_branch_for", branch_for)
        task = run_task(auditor, peer=False, synthesis=False)
        assert len(task.messages["rep_hi"].payload["claims"]) == 2
        clr = auditor.clearance(task.uid, task.mids["rep_hi"], receipt=task.receipts["rep_hi"], wait_ms=0)
        auditor.drain()
        clr = auditor.clearance(task.uid, task.mids["rep_hi"], receipt=task.receipts["rep_hi"])
        assert clr.state == "AUDIT_FAILED" and "OVS-CUST-006" in clr.codes
        audit = task.audit()
        f6 = findings(audit, "OVS-FID-006")
        assert f6 and "On balance" in f6[0].message
    finally:
        auditor.close()


def test_control_the_reparse_reproduces_a_genuine_parse(auditor):
    task = run_task(auditor, synthesis=False)
    assert not findings(task.audit(), "OVS-CUST-006")


# ============================================================================================ external results
EXT = b"overseer-test-external-engine-key-0123456789"


def _external_task(*, issued_before: bool):
    from epinoic_logic.engine.provenance import sign_result
    kr = make_keyring(remote=EngineKey(EXT, scope="external"))
    auditor = make_auditor(keyring=kr)
    problem = int_problem("en-point", "work_hours", 12, op="gt", bound=8)
    early = verify(problem, CFG, signing_key=EXT, key_id="remote") if issued_before else None

    def fn(claim, report):
        if claim.claim_id != "en-point":
            return None
        tr = translation_for(claim, report, problem)
        token = sink._ACTIVE.set(())  # the external engine runs elsewhere: nothing reaches this process's capture
        try:
            res = early or verify(problem, CFG, signing_key=EXT, key_id="remote")
        finally:
            sink._ACTIVE.reset(token)
        if issued_before:
            res = sign_result(res.model_copy(update={"issued_at": "2020-01-01T00:00:00Z", "signature": None, "signature_key_id": None}), EXT, "remote")
        return compose_outcome(claim, tr, res, signing_key=EXT, key_id="remote")
    ch = new_channel(auditor, verify_claim_fn=fn)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _reply, rc = ch.respond(m.message_id, english_report())
    return auditor, ch, rc


def test_a_genuine_external_result_passes_both_tiers():
    auditor, ch, rc = _external_task(issued_before=False)
    try:
        clr = auditor.clearance(ch.uid, rc.message_id, receipt=rc)
        assert clr.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS") and "OVS-RES-005" not in clr.codes
        final = auditor.audit(ch.uid, final=True)
        assert not findings(final, "OVS-RES-005") and final.transfer_states[rc.message_id] != "AUDIT_FAILED"
        assert any("external results" in n for n in final.coverage.notes)
    finally:
        auditor.close()


def test_an_external_result_issued_before_the_request_is_res_005_live_and_final():
    auditor, ch, rc = _external_task(issued_before=True)
    try:
        clr = auditor.clearance(ch.uid, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-RES-005" in clr.codes
        final = auditor.audit(ch.uid, final=True)
        assert [f for f in findings(final, "OVS-RES-005") if "before the request" in f.message]
    finally:
        auditor.close()


# ============================================================================================ TRN-006 grounded transcription
def test_a_verified_quotation_premise_identical_to_the_conclusion_is_a_transcription_not_circular(monkeypatch):
    from .conftest import withheld_as_circular_by_the_translator, without_the_translators_circularity_gate
    from .test_translation_oversight import POINT, V, genuine_problem, proposal, quoted, run, trn
    aud = make_auditor(shadow="off")
    try:
        p = genuine_problem()
        p["conclusion"] = {"id": "C", "expr": V("bell"), "label": "the foreman says work lasts until the bell", "grounding": quoted("We work until the bell")}
        aud, ch, _rc = run({POINT: proposal(p)}, auditor=aud)
        a = aud.audit(ch.uid)
        assert trn(a, "OVS-TRN-006") == [] and any("transcribes a grounded fact" in n for n in a.coverage.notes)
        p2 = genuine_problem()
        p2["conclusion"] = {"id": "C", "expr": V("endless"), "label": "work is endless", "grounding": {"kind": "specialist_inference"}}
        # rewritten after the round-7 simulation (rule restatement-necessity; the assertion kept): the inference is assumed
        # in place of the specialist's link, so it is load-bearing; appended beside the link it would be redundant
        # (OVS-TRN-010, a warning: test_corrections_trn_necessity.py)
        p2["premises"] = [x for x in p2["premises"] if x["id"] != "P_link"]
        p2["premises"].append({"id": "P_assumed", "expr": V("endless"), "grounding": {"kind": "specialist_inference"}})
        # the translator merge (rule circularity-agreement; the assertion kept): the merged translator withholds the assumed
        # inference itself (E112), with no OVS-TRN finding; delivered past its gate, it stays circular
        aud1 = make_auditor(shadow="off")
        try:
            aud1, ch1, rc1 = run({POINT: proposal(p2)}, auditor=aud1)
            assert withheld_as_circular_by_the_translator(next(o for o in rc1.outcomes if o.claim_id == POINT))
            a1 = aud1.audit(ch1.uid)
            assert trn(a1, "OVS-TRN-006") == [] and trn(a1, "OVS-TRN-010") == []
        finally:
            aud1.close()
        without_the_translators_circularity_gate(monkeypatch)
        aud2 = make_auditor(shadow="off")
        try:
            aud2, ch2, _rc2 = run({POINT: proposal(p2)}, auditor=aud2)
            assert [f.claim_ids for f in trn(aud2.audit(ch2.uid), "OVS-TRN-006")] == [[POINT]]  # an inference assumed stays circular
        finally:
            aud2.close()
    finally:
        aud.close()


# ============================================================================================ ledger
def test_superscript_and_subscript_digits_never_raise_out_of_the_ledger():
    assert figure_pairing_differences("so distance = ∫₀² v dt over the interval", ["x"]) == []
    assert figure_pairing_differences("the area grows as 10² m", ["the area grows as 10 m"]) == []


def test_a_stem_synthesis_with_notation_crosses_the_channel(auditor):
    claims = [SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried"),
              SynthesizedClaim(claim_id="s2", text="The Factory Act of 1833 banned the employment of children under nine in textile mills.", source_claim_ids=["h1.1"],
                               transformation="carried"),
              SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection (an area of 10² m, ∫₀² v dt).",
                               source_claim_ids=["h1.3"], transformation="paraphrased")]
    text = " ".join(c.text for c in claims)
    task = run_task(auditor, synthesis_obj=default_synthesis(claims=claims, text=text))  # raised ValueError out of the channel before the fix
    assert task.receipts["syn"] is not None and task.receipts["syn"].status.value != "REJECTED"
    assert not findings(task.audit(), "OVS-CUST-003")


_H2 = ("The Factory Act of 1833 banned the employment of children under nine in textile mills. "
       "The Ten Hours Act of 1847 limited the working day of women and young people to ten hours.")


def test_number_words_exchanged_between_provisions_are_re_paired_figures():
    src = ["The Factory Act of 1833 banned the employment of children under nine in textile mills.",
           "The Ten Hours Act of 1847 limited the working day of women and young people to ten hours."]
    swapped = ("The Factory Act of 1833 banned the employment of children under ten in textile mills, and the Ten Hours Act of 1847 limited the "
               "working day of women and young people to nine hours.")
    out = figure_pairing_differences(swapped, src)
    assert out and "exchanged" in out[0] and "'nine'" in out[0]
    assert figure_pairing_differences(" ".join(src), src) == []
    assert figure_spellings("the two poems; one of them") == []  # prose counts are not figures


def _hi_report(text: str) -> SpecialistReport:
    from epinoic_logic.translate.contracts import ClaimRecord
    sents = [s.strip() for s in text.split(". ") if s.strip()]
    claims = [ClaimRecord(request_id="req-ovs", task_id="task-ovs", report_id="rep-hi-1", agent_id="history-specialist", subject="History", task_type="short_answer",
                          claim_id=f"h1.{i + 1}", claim_text=s.rstrip(".") + ".", claim_role="point", materiality="material") for i, s in enumerate(sents)]
    return SpecialistReport(report_id="rep-hi-1", request_id="req-ovs", task_id="task-ovs", agent_id="history-specialist", subject="History", task_type="short_answer",
                            original_response=text, response_sha256=sha256_text(text), supplied_texts=[], claims=claims, created_at="2026-10-11T11:00:00Z")


def test_a_student_facing_text_that_re_pairs_the_claims_figures_is_int_ledger_023_and_never_released():
    rep = _hi_report(_H2)
    claims = [SynthesizedClaim(claim_id="s1", text=rep.claims[0].claim_text, source_claim_ids=["h1.1"], transformation="carried"),
              SynthesizedClaim(claim_id="s2", text=rep.claims[1].claim_text, source_claim_ids=["h1.2"], transformation="carried")]
    text = ("The Factory Act of 1847 banned the employment of children under nine in textile mills. "
            "The Ten Hours Act of 1833 limited the working day of women and young people to ten hours.")
    syn = Synthesis(synthesis_id="syn-1", request_id="req-ovs", task_id="task-ovs", combinator_agent_id="combinator", source_report_ids=["rep-hi-1"],
                    claims=claims, ledger=[], text=text, text_sha256=sha256_text(text), created_at="2026-10-11T12:00:00Z")
    found = [(f.code, f.severity) for f in check_synthesis_ledger([rep], syn)]
    assert ("INT-LEDGER-023", "error") in found
    faithful = syn.model_copy(update={"text": " ".join(c.text for c in claims), "text_sha256": sha256_text(" ".join(c.text for c in claims))})
    assert not [f for f in check_synthesis_ledger([rep], faithful) if f.code == "INT-LEDGER-023"]


# ============================================================================================ the release gate
def test_release_is_refused_when_the_synthesis_receipt_carries_an_error(auditor, monkeypatch):
    import epinoic_logic.channel.bus as bus
    from epinoic_logic.integrity.contracts import IntegrityFinding
    orig = bus.check_synthesis_ledger

    def with_error(scope, synthesis, **kw):
        return list(orig(scope, synthesis, **kw)) + [IntegrityFinding(code="INT-LEDGER-023", severity="error", message="re-paired figures (injected)",
                                                                      claim_ids=["s2"])]
    monkeypatch.setattr(bus, "check_synthesis_ledger", with_error)
    task = run_task(auditor)
    assert task.receipts["syn"].status.value == "ACCEPTED_WITH_FINDINGS"
    audit = task.audit(final=True)
    dec = release_decision(task.receipts["syn"], audit, auditor.keyring, audits=auditor.audits(task.uid), journal=auditor.journal(task.uid))
    assert not dec.allowed and "INT-LEDGER-023" in dec.reason


def test_release_re_checks_custody_of_the_synthesis_after_the_final_audit(auditor):
    task = run_task(auditor)
    audit = task.audit(final=True)
    kw = dict(audits=auditor.audits(task.uid), journal=auditor.journal(task.uid))
    assert may_release(task.receipts["syn"], audit, auditor.keyring, **kw)
    assert may_release(task.receipts["syn"], audit, auditor.keyring, message=task.messages["syn"], **kw)
    task.messages["syn"].payload["text"] = task.messages["syn"].payload["text"].replace("1833", "1843")
    dec = release_decision(task.receipts["syn"], audit, auditor.keyring, **kw)
    assert not dec.allowed and "OVS-CUST-001" in dec.reason
    assert not may_release(task.receipts["syn"], audit, auditor.keyring, message=task.messages["syn"], **kw)
    clr = auditor.clearance(task.uid, task.mids["syn"])
    assert clr.state == "AUDIT_FAILED"
