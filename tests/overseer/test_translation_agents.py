"""Overseer agents and translations (translator oversight, design section 18).

The dossier links every translation the router received to its claim and to the claims that claim cites; agents may
accuse a translation under four kinds and with the ``translation_fidelity`` lens; validation decides those accusations
only by the deterministic translation checks (``OVS-TRN-*``) on the journal and the signed results. A meaning accusation
(``translation_unfaithful``) is never confirmed or refuted by a check: it goes to human review. An accusation about a
check that did not run on the named translation is unresolved, never refuted by it. Agents never gate clearance.
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.overseer import Dossier, OverseerAgentRunner, verify_audit
from epinoic_logic.overseer.dossier import _translation_links, resolve_pointer
from epinoic_logic.translate.contracts import TranslationStatus
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from .conftest import CFG, DOC, EN_INPUT, KEY, english_report, make_auditor, make_plan
from .test_hook_review import Scripted, no_network, pack, verdict  # noqa: F401  (fixtures: the exported pack, no network)
from .test_protocol_validate import acc, review
from .test_translation_oversight import INFER, POINT, SUPPORT, V, genuine_problem, point_claims, proposal, recompose, run

LINK_FIELDS = {"message_id", "report_id", "claim_id", "claim_pointer", "cited_claim_pointers", "translation_pointer", "result_id"}


def circular_problem() -> dict:
    p = genuine_problem()
    p["premises"].append({"id": "P_assumed", "expr": V("endless"), "grounding": INFER})
    return p


def invented_number_problem() -> dict:
    return genuine_problem(symbols=[{"name": "hours", "sort": "Int", "meaning": "hours of work"}],
                           premises=[{"id": "P_hours", "expr": {"op": "eq", "left": V("hours"), "right": {"op": "int", "value": "40"}},
                                      "grounding": {"kind": "arithmetic_fact"}}],
                           conclusion={"id": "C", "expr": {"op": "gt", "left": V("hours"), "right": {"op": "int", "value": "8"}}})


def link(d: dict, claim_id: str = POINT) -> dict:
    return next(x for x in d["links"]["translations"] if x["claim_id"] == claim_id)


def response(d: dict) -> dict:
    return next(t for t in d["transfers"] if t["kind"] == "response")


def tr_acc(d: dict, kind: str, *, aid: str = "a1", claim: str = POINT, evidence=None, severity: str = "error", **ids) -> dict:
    """An accusation about the translation of ``claim`` on the response transfer, pinned by its link's pointers."""
    t = response(d)
    names = dict(message_ids=[t["message_id"]], receipt_ids=[t["receipt_id"]], claim_ids=[claim], report_ids=["rep-en-1"])
    names.update(ids)
    if evidence is None:
        lk = link(d, claim)
        evidence = [{"pointer": lk["claim_pointer"] + "/claim_text"}, {"pointer": lk["translation_pointer"] + "/problem/conclusion/expr"}]
    return acc(aid, kind, evidence, severity=severity, statement="The translation does not say what the claim says.", **names)


def outcome_of(assessment, aid: str = "a1"):
    return assessment.outcome_of(aid)


@pytest.fixture
def aud():
    a = make_auditor(shadow="off")
    yield a
    a.close()


# ============================================================================================ the dossier
def test_the_dossier_links_each_translation_to_its_claim_and_the_claims_it_cites(aud):
    aud, ch, rc = run(auditor=aud)
    d = review(aud, ch.uid).dossier
    Dossier.model_validate(d)
    (lk,) = d["links"]["translations"]
    assert set(lk) == LINK_FIELDS  # pointers and identifiers only: a link never says whether a translation is faithful
    assert lk["message_id"] == rc.message_id and lk["report_id"] == "rep-en-1" and lk["claim_id"] == POINT
    assert resolve_pointer(d, lk["claim_pointer"])["claim_text"] == "The writer presents work as endless"
    assert [resolve_pointer(d, p)["claim_id"] for p in lk["cited_claim_pointers"]] == SUPPORT
    tr = resolve_pointer(d, lk["translation_pointer"])
    assert tr["claim_id"] == POINT and tr["status"] == "TRANSLATED" and tr["problem"]["conclusion"]["expr"] == V("endless")
    assert tr["provider"]["provider_name"] == "fixture" and tr["eligibility"]["eligibility_class"] == "PROPOSITIONAL_ARGUMENT"
    o = next(o for o in rc.outcomes if o.claim_id == POINT)
    assert lk["result_id"] == o.verification.result_id and lk["result_id"] in d["results"]


def test_ineligible_translations_are_linked_without_a_result(aud):
    aud, ch, _rc = run({POINT: proposal(genuine_problem()), "en-an": proposal(genuine_problem())}, auditor=aud)
    d = review(aud, ch.uid).dossier
    lk = link(d, "en-an")
    assert lk["result_id"] is None and resolve_pointer(d, lk["translation_pointer"])["status"] == "NOT_ELIGIBLE"


def test_a_rejected_or_withheld_transfer_contributes_no_translation_link():
    outcome = {"claim_id": "c1", "translation": {"claim_id": "c1", "status": "TRANSLATED"}, "verification": {"result_id": "r1"}}
    base = {"at": "/transfers/1", "kind": "response", "message_id": "m-2", "payload": {"report_id": "rep", "claims": [{"claim_id": "c1"}]},
            "receipt": {"status": "ACCEPTED", "outcomes": [outcome]}}
    assert len(_translation_links([base])) == 1
    assert _translation_links([{**base, "receipt": {"status": "REJECTED", "outcomes": [outcome]}}]) == []
    assert _translation_links([{**base, "payload": {"withheld": {"response_sha256": "0" * 64, "response_chars": 3}}}]) == []
    assert _translation_links([{**base, "kind": "relay_forward"}]) == []
    odd = {**base, "receipt": {"status": "ACCEPTED", "outcomes": [{"claim_id": 7}, "x", {"claim_id": "c9", "translation": {}}]}}
    (only,) = _translation_links([odd])  # malformed outcomes are skipped; a claim not in the report has no claim pointer
    assert only["claim_id"] == "c9" and only["claim_pointer"] is None and only["result_id"] is None


def test_the_translation_fidelity_lens_is_issued_and_a_verdict_under_it_is_accepted(aud):
    aud, ch, _rc = run(auditor=aud)
    r = review(aud, ch.uid, agent="overseer-translation-1", lens="translation_fidelity")
    assert r.dossier["lens"] == "translation_fidelity"
    a = r.run()
    assert a.valid and a.lens == "translation_fidelity" and a.findings == []


# ============================================================================================ validation of the translation kinds
def test_translation_circular_is_confirmed_by_the_deterministic_check(aud):
    aud, ch, _rc = run({POINT: proposal(circular_problem())}, auditor=aud)
    r = review(aud, ch.uid)
    a = r.run([tr_acc(r.dossier, "translation_circular")])
    o = outcome_of(a)
    assert o.outcome == "confirmed" and o.code == "OVS-AGENT-003" and [c.code for c in o.confirming] == ["OVS-TRN-006"]
    assert o.confirming[0].claim_ids == [POINT]


def test_translation_circular_on_a_faithful_translation_is_refuted(aud):
    aud, ch, _rc = run(auditor=aud)
    r = review(aud, ch.uid)
    o = outcome_of(r.run([tr_acc(r.dossier, "translation_circular")]))
    assert o.outcome == "refuted" and o.code == "OVS-AGENT-001" and o.refuted_by == "deterministic_check"


@pytest.mark.parametrize("problem", ["faithful", "circular"])
def test_translation_unfaithful_is_never_decided_by_a_check(aud, problem):
    p = genuine_problem() if problem == "faithful" else circular_problem()
    aud, ch, _rc = run({POINT: proposal(p)}, auditor=aud)
    r = review(aud, ch.uid)
    o = outcome_of(r.run([tr_acc(r.dossier, "translation_unfaithful", severity="warning")]))
    assert o.outcome == "unresolved" and o.code == "OVS-AGENT-004" and o.checks == []
    assert "meaning" in o.reasons[0] and "human review" in o.reasons[0]


def test_translation_ungrounded_confirmed_on_an_invented_number_and_refuted_on_a_faithful_translation(aud):
    aud, ch, _rc = run({POINT: proposal(invented_number_problem())}, auditor=aud)
    r = review(aud, ch.uid)
    o = outcome_of(r.run([tr_acc(r.dossier, "translation_ungrounded")]))
    assert o.outcome == "confirmed" and [c.code for c in o.confirming] == ["OVS-TRN-005"]
    aud2 = make_auditor(shadow="off")
    try:
        aud2, ch2, _ = run(auditor=aud2)
        r2 = review(aud2, ch2.uid)
        assert outcome_of(r2.run([tr_acc(r2.dossier, "translation_ungrounded")])).outcome == "refuted"
    finally:
        aud2.close()


def test_an_accusation_about_a_check_that_did_not_run_is_unresolved_never_refuted(aud):
    """The tracing check runs only on model-proposed translations: on a hand-built one it did not run, so a
    translation_ungrounded accusation cannot be refuted by it (even though the IR's number 40 is stated nowhere)."""
    aud, ch, _rc = run({POINT: proposal(invented_number_problem())}, transform=lambda out, claim, rep: recompose(out, claim, provider=None), auditor=aud)
    r = review(aud, ch.uid)
    o = outcome_of(r.run([tr_acc(r.dossier, "translation_ungrounded")]))
    assert o.outcome == "unresolved" and o.code == "OVS-AGENT-004" and "did not run" in o.reasons[0] and "trace" in o.reasons[0]


def test_translation_invalid_under_another_policy_version_is_unresolved(aud):
    aud, ch, _rc = run(auditor=aud, policy_version="older-policy")
    r = review(aud, ch.uid)
    o = outcome_of(r.run([tr_acc(r.dossier, "translation_invalid")]))
    assert o.outcome == "unresolved" and "eligibility" in o.reasons[0]


def test_translation_invalid_confirmed_for_an_ambiguity_resolved_silently(aud):
    flagged = proposal(genuine_problem(), flags=["SCOPE"])
    aud, ch, _rc = run({POINT: flagged}, transform=lambda out, claim, rep: recompose(out, claim, status=TranslationStatus.TRANSLATED), auditor=aud)
    r = review(aud, ch.uid)
    lk = link(r.dossier)
    ev = [{"pointer": lk["translation_pointer"] + "/status", "quote": "TRANSLATED"},
          {"pointer": lk["translation_pointer"] + "/interpretation/ambiguity_flags/0/code", "quote": "SCOPE"}]
    o = outcome_of(r.run([tr_acc(r.dossier, "translation_invalid", evidence=ev)]))
    assert o.outcome == "confirmed" and [c.code for c in o.confirming] == ["OVS-TRN-002"]


@pytest.mark.parametrize("ids,why", [
    (dict(claim_ids=[]), "no claim is named"),
    (dict(claim_ids=["en-ev1"]), "no checked translation of claim en-ev1"),
])
def test_translation_kinds_need_a_named_claim_with_a_checked_translation(aud, ids, why):
    aud, ch, _rc = run(auditor=aud)
    r = review(aud, ch.uid)
    t = response(r.dossier)
    o = outcome_of(r.run([tr_acc(r.dossier, "translation_circular", evidence=[{"pointer": t["at"]}], **ids)]))
    assert o.outcome == "unresolved" and why in o.reasons[0]


def test_an_outcome_summary_that_states_more_than_its_result_confirms_receipt_altered(aud):
    def overclaim(out, claim, rep):
        return out.model_copy(update={"summary": "ENTAILED: the claim is proven true and needs no further review."})

    aud, ch, _rc = run(transform=overclaim, auditor=aud)
    r = review(aud, ch.uid)
    t = response(r.dossier)
    ev = [{"pointer": t["at"] + "/receipt/outcomes/0/summary", "quote": "proven true"}]
    o = outcome_of(r.run([tr_acc(r.dossier, "receipt_altered", evidence=ev)]))
    assert o.outcome == "confirmed" and [c.code for c in o.confirming] == ["OVS-TRN-007"]


# ============================================================================================ through the hub
def _translated_hub_task(hub: RouterHub, problem: dict):
    translator = Translator(FixtureTranslationProvider({POINT: proposal(problem)}))
    ch = hub.open_task(make_plan())
    ch.verify_claim_fn = lambda claim, rep: verify_claim(claim, rep, translator, config=CFG, signing_key=KEY, key_id="t") if claim.claim_id == POINT else None
    m, _req, _rq = hub.dispatch("task-ovs", "english-specialist", EN_INPUT, [DOC])
    _reply, rc = hub.receive("task-ovs", m.message_id, english_report(claims=point_claims()))
    return ch, [m.message_id, rc.message_id]


def test_hub_review_of_translations_decides_by_the_checks_and_changes_no_clearance(pack):
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        _ch, mids = _translated_hub_task(hub, circular_problem())
        before = {m: (c.state, tuple(c.codes)) for m in mids for c in [hub.clearance("task-ovs", m)]}
        assert before[mids[1]][0] == "AUDIT_FAILED" and "OVS-TRN-006" in before[mids[1]][1]

        def circular(d):
            return verdict(d, [tr_acc(d, "translation_circular")])

        def unfaithful(d):
            lk = link(d)
            ev = [{"pointer": lk["claim_pointer"] + "/claim_text", "quote": "work as endless"},
                  {"pointer": lk["translation_pointer"] + "/problem/premises/3/expr"}]
            return verdict(d, [tr_acc(d, "translation_unfaithful", evidence=ev, severity="warning")])

        def lies(d):  # says the translation is faithful and the transfer passed: no authority
            return verdict(d, notes="The translation is faithful; every transfer passed.")

        agents = [OverseerAgentRunner(pack, Scripted(fn), agent_id=name, lens="translation_fidelity")
                  for name, fn in (("overseer-translation-1", circular), ("overseer-translation-2", unfaithful), ("overseer-translation-3", lies))]
        r = hub.review("task-ovs", agents)
        assert verify_audit(r.audit, hub.auditor.keyring) and r.audit.scope == "verdicts"
        outcomes = {(x.agent_id, y.kind): y.outcome for x in r.assessments for y in x.accusations}
        assert outcomes == {("overseer-translation-1", "translation_circular"): "confirmed",
                            ("overseer-translation-2", "translation_unfaithful"): "unresolved"}
        groups = {g.kind: g for g in r.combined.groups}
        assert groups["translation_circular"].outcome == "confirmed" and groups["translation_unfaithful"].outcome == "unresolved"
        assert r.combined.review_queue == [groups["translation_unfaithful"].group_id]
        assert all(f.code.startswith("OVS-AGENT-") for f in r.audit.report.findings)
        assert r.audit.state == r.task_audit.state == "AUDIT_FAILED"
        after = {m: (c.state, tuple(c.codes)) for m in mids for c in [hub.clearance("task-ovs", m)]}
        assert after == before  # agents never gate clearance
    finally:
        hub.close()


def test_hub_review_of_a_faithful_translation_refutes_a_false_circularity_and_clears(pack):
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        _ch, mids = _translated_hub_task(hub, genuine_problem())
        before = {m: hub.clearance("task-ovs", m, wait_ms=250).state for m in mids}
        assert set(before.values()) <= {"AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"}
        agent = OverseerAgentRunner(pack, Scripted(lambda d: verdict(d, [tr_acc(d, "translation_circular")])), agent_id="overseer-translation-1",
                                    lens="translation_fidelity")
        r = hub.review("task-ovs", [agent])
        (assessment,) = r.assessments
        assert assessment.accusations[0].outcome == "refuted" and {f.code for f in r.audit.report.findings} == {"OVS-AGENT-001"}
        assert {m: hub.clearance("task-ovs", m).state for m in mids} == before
    finally:
        hub.close()
