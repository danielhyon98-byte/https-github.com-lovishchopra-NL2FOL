"""Corrections after the round-7 simulation: OVS-TRN-006 severity by engine evidence (rule ``restatement-necessity``).

A translation whose conclusion occurs among its premises was always OVS-TRN-006 (an error). The recorded round r7 showed
three genuine translations of that shape, and they are not alike:

* bm-t13 g2.1 restates the contribution per loaf ($2.00) as a premise, although the quoted price and costs already give
  it (4.00 - (1.10 + 0.90) = 2.00): the restatement is redundant;
* cs-t13 g11.3 and ess-t13 g4.3 have the conclusion as their only premise (p proves p): the result rests on the claim
  assumed.

The auditor now decides which, with the engine: a fresh run of the IR with the restating premise(s) removed, through the
engine's own validator, compiler and procedures, signed under the auditor's run key and stored. ENTAILED: OVS-TRN-010, a
warning naming the premise, which fails no transfer. COUNTEREXAMPLE, INCONSISTENT_PREMISES, an undecided status, no
signed run or a failed run: OVS-TRN-006, the error, as before (uncertainty never resolves toward clearance). An agent's
``translation_circular`` accusation follows the check: confirmed on a circular translation, refuted on a redundant
restatement (the check ran on it and decided it is not circular), never by a signed result (no contradiction is recorded
against the agent, whose dossier gives it no engine run to read).
"""
from __future__ import annotations

import copy
import json

import pytest

from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.overseer.checks import translation as T
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from .conftest import CFG, KEY, make_auditor, new_channel
from .test_protocol_validate import review
from .test_translation_agents import outcome_of, tr_acc
from .test_translation_oversight import INFER, POINT, V, genuine_problem, proposal, run, trn

# ============================================================================================ a Business Management task (the bm-t13 shape)
BM_CASE = ("Hollin & Daughters (fictional case written for this exercise)\n\nHollin & Daughters is a family-owned bakery. The cafes pay $4.00 per loaf.\n\n"
           "Table 1: Cost data per month, 2025\nDirect materials per loaf: $1.10\nDirect labour per loaf: $0.90\nRent: $2,500")
BM_DOC = SuppliedText(document_id="doc-hollin", title="Hollin & Daughters (case study)", author="Task data", text=BM_CASE)
BM_INPUT = "Calculate the contribution per loaf for Hollin & Daughters from the supplied case. Show your working."
BM_CLAIM = "Contribution per loaf = selling price − variable cost per loaf = $4.00 − ($1.10 + $0.90) = $4.00 − $2.00 = $2.00 per loaf"
BM_TEXT = "(a) [4]\n\n" + BM_CLAIM
CID = "g2.1"
SUBJECT = "Business Management"
AGENT = "business-management-specialist"


def _quoted(excerpt: str) -> dict:
    return {"kind": "quotation", "source_refs": [{"document_id": "doc-hollin", "excerpt": excerpt}], "certainty": "established"}


def _real(v: str) -> dict:
    return {"op": "real", "value": v}


_INF = {"kind": "specialist_inference", "source_refs": [], "certainty": "established"}


def bm_problem(*, restate: bool = True, derive: bool = True) -> dict:
    """The recorded round-7 translation of bm-t13 g2.1, ids adapted to this task: the quoted price and costs (a_p, a_vm,
    a_vl), the variable cost (d_vc), the contribution's definition (d_contrib) and, with ``restate``, the restating
    premise d_contrib_val (contrib = 2.00). Without ``derive`` the definition is left out, so only the restatement gives
    the contribution (a chain whose restated premise is load-bearing)."""
    sym = [{"name": "p", "sort": "Real", "meaning": "selling price per loaf: $4.00", "grounding": _quoted("The cafes pay $4.00 per loaf.")},
           {"name": "vm", "sort": "Real", "meaning": "direct materials per loaf: $1.10", "grounding": _quoted("Direct materials per loaf: $1.10")},
           {"name": "vl", "sort": "Real", "meaning": "direct labour per loaf: $0.90", "grounding": _quoted("Direct labour per loaf: $0.90")},
           {"name": "vc", "sort": "Real", "meaning": "variable cost per loaf", "grounding": _INF},
           {"name": "contrib", "sort": "Real", "meaning": "contribution per loaf", "grounding": _INF}]
    prem = [{"id": "a_p", "expr": {"op": "eq", "left": V("p"), "right": _real("4.00")}, "label": "selling price per loaf: $4.00",
             "grounding": _quoted("The cafes pay $4.00 per loaf.")},
            {"id": "a_vm", "expr": {"op": "eq", "left": V("vm"), "right": _real("1.10")}, "label": "direct materials per loaf: $1.10",
             "grounding": _quoted("Direct materials per loaf: $1.10")},
            {"id": "a_vl", "expr": {"op": "eq", "left": V("vl"), "right": _real("0.90")}, "label": "direct labour per loaf: $0.90",
             "grounding": _quoted("Direct labour per loaf: $0.90")},
            {"id": "d_vc", "expr": {"op": "eq", "left": V("vc"), "right": {"op": "add", "args": [V("vm"), V("vl")]}}, "label": "variable cost per loaf",
             "grounding": _INF}]
    if derive:
        prem.append({"id": "d_contrib", "expr": {"op": "eq", "left": V("contrib"), "right": {"op": "sub", "left": V("p"), "right": V("vc")}},
                     "label": "contribution per loaf", "grounding": _INF})
    if restate:
        prem.append({"id": "d_contrib_val", "expr": {"op": "eq", "left": V("contrib"), "right": _real("2.00")}, "label": "the contribution per loaf is $2.00",
                     "grounding": _INF})
    return {"problem_id": "bm_t13_g2_1", "request_id": "req-bm", "claim_id": CID, "query": "entailment", "symbols": sym, "premises": prem,
            "conclusion": {"id": "C_bm_t13_g2_1", "expr": {"op": "eq", "left": V("contrib"), "right": _real("2.00")}, "label": "contribution per loaf is $2.00",
                           "grounding": _INF}}


def bm_report() -> SpecialistReport:
    claim = ClaimRecord(claim_id=CID, request_id="req-bm", task_id="task-bm", report_id="rep-bm-1", agent_id=AGENT, subject=SUBJECT,
                        task_type="structured_question", claim_text=BM_CLAIM, claim_role="quantitative", proposed_claim_kind="arithmetic", materiality="material")
    return SpecialistReport(report_id="rep-bm-1", request_id="req-bm", task_id="task-bm", agent_id=AGENT, subject=SUBJECT, task_type="structured_question",
                            original_response=BM_TEXT, response_sha256=sha256_text(BM_TEXT), supplied_texts=[BM_DOC], claims=[claim],
                            created_at="2026-10-12T09:00:00Z")


def run_bm(problem: dict, auditor):
    """One Business Management request and structured report; claim g2.1 translated by the pipeline from ``problem``
    (the fixture provider) and decided by the engine inside the channel call."""
    plan = WorkPlan(plan_id="plan-bm", request_id="req-bm", task_id="task-bm", subject=SUBJECT, task_type="structured_question",
                    selected_agent_ids=[AGENT], allowed_document_ids=["doc-hollin"])
    ch = new_channel(auditor, plan)
    translator = Translator(FixtureTranslationProvider({CID: json.dumps({"problem": problem, "interpretation": {
        "reading": "contribution is price minus variable cost per loaf", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None})}))
    ch.channel.verify_claim_fn = lambda claim, rep: verify_claim(claim, rep, translator, config=CFG, signing_key=KEY, key_id="t") if claim.claim_id == CID else None
    m, _req, _rq = ch.request("router", AGENT, BM_INPUT, [BM_DOC])
    _reply, rc = ch.respond(m.message_id, bm_report())
    assert rc.status is not TransmissionStatus.REJECTED
    return ch, rc


@pytest.fixture
def aud():
    a = make_auditor(shadow="off")
    yield a
    a.close()


def _outcome(rc):
    return next(o for o in rc.outcomes if o.claim_id == CID)


# ============================================================================================ the bm-t13 shape: a warning
def test_the_bm_t13_restatement_is_redundant_a_warning_naming_the_premise(aud):
    ch, rc = run_bm(bm_problem(), aud)
    o = _outcome(rc)
    assert o.translation.status.value == "TRANSLATED" and o.verification.status.value == "ENTAILED"
    assert o.verification.premises_relied_on == ["d_contrib_val"]  # the outcome's own core names only the restatement
    a = aud.audit(ch.uid)
    assert trn(a, "OVS-TRN-006") == []
    (w,) = trn(a, "OVS-TRN-010")
    assert w.severity == "warning" and w.claim_ids == [CID] and "d_contrib_val" in w.message and w.formal_result_id == o.verification.result_id
    assert "relied only on the restatement" in w.message  # the misleading core is named
    run_rec = aud.store.get(w.related_result_ids[0])
    signed = aud.store.parsed(w.related_result_ids[0])
    assert run_rec.origin == "auditor_run" and run_rec.key_id == "overseer-run" and run_rec.signature_ok_at_put
    assert signed.status.value == "ENTAILED" and set(signed.premises_relied_on) == {"a_p", "a_vm", "a_vl", "d_vc", "d_contrib"}
    assert "d_contrib_val" not in {p["id"] for p in json.loads(run_rec.problem_json)["premises"]}
    assert a.transfer_states[rc.message_id] == "AUDIT_PASSED_WITH_FINDINGS" and a.state != "AUDIT_FAILED"
    assert not [f for f in a.report.findings if f.severity == "error"]


# ============================================================================================ errors: load-bearing restatements
def test_p_proves_p_is_circular_an_error(aud):
    """The cs-t13 g11.3 / ess-t13 g4.3 shape: the conclusion is the only premise. Without it nothing gives the claim."""
    p = genuine_problem()
    p["premises"] = [{"id": "a_point", "expr": V("endless"), "label": "the writer presents work as endless", "grounding": INFER}]
    aud, ch, rc = run({POINT: proposal(p)}, auditor=aud)
    o = next(x for x in rc.outcomes if x.claim_id == POINT)
    assert o.verification.status.value == "ENTAILED" and o.display_status.value == "ENTAILED"
    a = aud.audit(ch.uid)
    (e,) = trn(a, "OVS-TRN-006")
    assert e.severity == "error" and e.claim_ids == [POINT] and "a_point" in e.message and "COUNTEREXAMPLE" in e.message
    signed = aud.store.parsed(e.related_result_ids[0])
    assert signed.status.value == "COUNTEREXAMPLE" and signed.premises_relied_on == [] and not json.loads(aud.store.get(signed.result_id).problem_json)["premises"]
    assert trn(a, "OVS-TRN-010") == [] and a.state == "AUDIT_FAILED" and a.transfer_states[rc.message_id] == "AUDIT_FAILED"


def test_a_chain_whose_restated_premise_is_load_bearing_is_an_error(aud):
    """The bm-t13 chain without the contribution's definition: the quoted figures are there, but only the restatement
    gives the contribution, so the result rests on the claim assumed."""
    ch, rc = run_bm(bm_problem(derive=False), aud)
    o = _outcome(rc)
    assert o.verification.status.value == "ENTAILED"
    a = aud.audit(ch.uid)
    (e,) = trn(a, "OVS-TRN-006")
    assert e.severity == "error" and e.claim_ids == [CID] and "d_contrib_val" in e.message and "COUNTEREXAMPLE" in e.message
    assert aud.store.parsed(e.related_result_ids[0]).status.value == "COUNTEREXAMPLE"
    assert trn(a, "OVS-TRN-010") == [] and a.transfer_states[rc.message_id] == "AUDIT_FAILED"


def test_without_a_restatement_there_is_no_necessity_run(aud):
    ch, rc = run_bm(bm_problem(restate=False), aud)
    a = aud.audit(ch.uid)
    assert trn(a, "OVS-TRN-006") == [] and trn(a, "OVS-TRN-010") == []
    assert not [r for r in aud.store.results_of(ch.uid) if r.origin == "auditor_run"]  # no engine run was needed


# ============================================================================================ undecidable: the error stays
def _starved(real):
    def run(raw, config):
        return real(raw, config.model_copy(update={"rlimit": 1}))  # a real engine run that cannot decide (deterministic cutoff)
    return run


@pytest.mark.parametrize("how", ["timeout", "invalid", "raises", "no_run"])
def test_an_undecidable_necessity_run_keeps_the_error(monkeypatch, how):
    real = T._engine_verify
    if how == "timeout":
        monkeypatch.setattr(T, "_engine_verify", _starved(real))
    elif how == "invalid":
        monkeypatch.setattr(T, "_engine_verify", lambda raw, config: real("{\"not\": \"an IR problem\"}", config))
    elif how == "raises":
        def boom(raw, config):
            raise RuntimeError("engine unavailable")
        monkeypatch.setattr(T, "_engine_verify", boom)
    else:  # an engine call that emits no result into the capture: nothing signed to rely on
        from epinoic_logic.engine.results import VerificationResult  # noqa: F401
        monkeypatch.setattr(T, "_engine_verify", lambda raw, config: None)
    a0 = make_auditor(shadow="off")
    try:
        ch, rc = run_bm(bm_problem(), a0)  # redundant when decided: here the run cannot decide it
        a = a0.audit(ch.uid)
        (e,) = trn(a, "OVS-TRN-006")
        assert e.severity == "error" and e.claim_ids == [CID] and "could not be decided" in e.message and "d_contrib_val" in e.message
        assert trn(a, "OVS-TRN-010") == [] and a.transfer_states[rc.message_id] == "AUDIT_FAILED"
        if how == "timeout":
            assert "TIMEOUT" in e.message and a0.store.parsed(e.related_result_ids[0]).status.value == "TIMEOUT"
        if how == "invalid":
            assert "INVALID_FORMALIZATION" in e.message
        if how in ("raises", "no_run"):
            assert e.related_result_ids == []
        assert not [f for f in a.report.findings if f.code == "OVS-AUDIT-001"]  # handled, never an internal failure
    finally:
        a0.close()


def test_a_vacuous_entailment_without_the_restatement_does_not_clear_it():
    """E108 (no premise used) is a verdict the engine withholds: it never makes a restatement redundant."""
    nec = T.Necessity(removed=("P",), status="ENTAILED", result_id="r1", diagnostics=("E108",), reason="E108: vacuous")
    assert not nec.follows and "withholds" in nec.describe()
    assert T.Necessity(removed=("P",), status="ENTAILED", result_id="r1", diagnostics=("E505",)).follows
    assert not T.Necessity(removed=("P",), status="ENTAILED", result_id=None).follows
    assert not T.Necessity(removed=("P",), status="INCONSISTENT_PREMISES", result_id="r1").follows


def test_without_premises_removes_whole_premises_and_never_mutates_the_input():
    p = bm_problem()
    before = copy.deepcopy(p)
    out = T.without_premises(p, ["d_contrib_val", "no-such-premise"])
    assert p == before and [x["id"] for x in out["premises"]] == ["a_p", "a_vm", "a_vl", "d_vc", "d_contrib"]
    assert out["conclusion"] == p["conclusion"] and out["symbols"] == p["symbols"]
    res = verify(json.dumps(out), SolverConfig())
    assert res.status.value == "ENTAILED"


# ============================================================================================ agents follow the check
def test_translation_circular_on_a_redundant_restatement_is_refuted_by_the_check_not_by_a_signed_result(aud):
    p = genuine_problem()
    p["premises"].append({"id": "P_assumed", "expr": V("endless"), "grounding": INFER})
    aud, ch, _rc = run({POINT: proposal(p)}, auditor=aud)
    r = review(aud, ch.uid)
    o = outcome_of(r.run([tr_acc(r.dossier, "translation_circular")]))
    assert o.outcome == "refuted" and o.code == "OVS-AGENT-001" and o.refuted_by == "deterministic_check"


def test_translation_circular_on_p_proves_p_is_confirmed(aud):
    p = genuine_problem()
    p["premises"] = [{"id": "a_point", "expr": V("endless"), "label": "the writer presents work as endless", "grounding": INFER}]
    aud, ch, _rc = run({POINT: proposal(p)}, auditor=aud)
    r = review(aud, ch.uid)
    o = outcome_of(r.run([tr_acc(r.dossier, "translation_circular")]))
    assert o.outcome == "confirmed" and [c.code for c in o.confirming] == ["OVS-TRN-006"]


def test_the_code_table_gives_the_redundant_restatement_a_warning_and_no_accusation_kind():
    from epinoic_logic.overseer.codes import OVS_CODES
    from epinoic_logic.overseer.verdicts import KIND_CHECKS
    assert OVS_CODES["OVS-TRN-010"][0] == "warning" and OVS_CODES["OVS-TRN-006"][0] == "error"
    assert "restatement-necessity" in OVS_CODES["OVS-TRN-006"][2] and "restatement-necessity" in OVS_CODES["OVS-TRN-010"][2]
    assert KIND_CHECKS["translation_circular"] == ("OVS-TRN-006",)
    assert not any("OVS-TRN-010" in codes for codes in KIND_CHECKS.values())
