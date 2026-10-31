"""The delivery policy's fallback (``docs/DELIVERY.md``): when the formal path does not complete, overseer agents built
from the EXPORTED knowledge pack review every candidate through the package's runner and the self-duplicating pool; every
verdict is validated as in production; the policy scores each candidate (the share of its material claims the validated
verdicts confirm accurate) and delivers the best one only when that share is ABOVE 0.90. Fake clock, scripted overseer
providers and fixture verifiers only (no model, no network).

Covered: the more accurate candidate preferred over the canonical one; ties to the consolidation's canonical choice;
exactly 0.90 (and below) withheld, above 0.90 delivered, exactly (no floating point); a candidate whose material claim a
signed engine result refutes excluded while another has none; a verdict that contradicts a signed engine result rejected
(none of its reviews counts) while an honest instance's counts; an accusation a check refutes lowering no score; the
overseer stage's own deadline (withheld by default, NOT CHECKED only when configured); a single candidate; duplicated
instances and a repeated fault (two pool instances, the excluded answers never delivered); labels that never claim
verification; and that no fallback changes what any claim says."""
from __future__ import annotations

import socket
from fractions import Fraction

import pytest

from epinoic_logic.integrity.contracts import payload_hash
from epinoic_logic.overseer import load_pack, verify_audit
from epinoic_logic.overseer.delivery_policy import DeliveryConfig, DeliveryPolicy, accuracy_above, verify_delivered_answer, verify_delivery_receipt
from epinoic_logic.overseer.export import export_pack
from epinoic_logic.translate.contracts import SpecialistReport

from .conftest import DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, english_report, make_plan, point_problem, problems_fn
from .delivery_support import (
    ESSAY, ESSAY_QUESTION, REFUTED_TEXT, Agents, FakeClock, Verifier, acc, assert_honest, contest, essay_report, physics_report, ptr,
    refuted_outcome, response_of, run_task, silent, state_results, verdict,
)
from .test_consolidation_repeats import bad_answer

AGENT = "physics-specialist"
EN_AGENTS = ["english-1", "english-2", "english-3", "english-specialist", "history-specialist", "combinator"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover - only hit if a test leaks a connection
        raise AssertionError("network access attempted in a unit test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    """The overseer agents are built from the pack EXPORTED with the exporter and loaded back from the zip."""
    return load_pack(export_pack(tmp_path_factory.mktemp("export"), zip_archive=True).zip_path)


@pytest.fixture
def clock():
    return FakeClock()


def policy_with(clock, pack, reply=silent, *, config=None, delay=0.0, replies=None):
    agents = Agents(clock, reply, delay=delay, replies=replies)
    return DeliveryPolicy(clock=clock, pack=pack, provider_factory=agents, config=config), agents


def essays(*specs, verify=None, policy=None):
    """Run the essay task: each spec is ``(agent, n points, kwargs of essay_report)``."""
    answers = [(agent, essay_report(agent, f"rep-{agent}", n, prefix=agent.replace("writer-", "w"), **kw)) for agent, n, kw in specs]
    return run_task(policy, answers, verify=verify, question=ESSAY_QUESTION, ids=ESSAY)


def cand(rec, agent):
    return next(c for c in rec.fallback.candidates if c.agent_id == agent)


def journal_payload(run, message_id):
    view = run.hub.auditor.view(run.session.channel.channel_uid)
    return view.by_message[message_id].payload


def journal_state(run):
    """What the router holds of the task: every transfer's kind and payload digest, and every receipt as issued."""
    view = run.hub.auditor.view(run.session.channel.channel_uid)
    transfers = [(t.seq, t.kind, t.message_id, t.envelope.get("payload_sha256") if t.envelope else None) for t in view.transfers]
    receipts = [r.model_dump(mode="json") for r in run.session.channel.receipts]
    return transfers, receipts


# ============================================================================================ accuracy and the selection
def test_the_overseer_prefers_the_more_accurate_candidate_over_the_canonical_one(clock, pack):
    """writer-1 answers first (the canonical rank) but one of its twelve points is contested (an accusation no check
    decides: unresolved, never confirmed accurate): 11/12. writer-2's twelve points are all confirmed: 12/12."""
    policy, agents = policy_with(clock, pack, contest(("rep-writer-1", "w1.3")))
    run = essays(("writer-1", 12, {}), ("writer-2", 12, dict(variant="memory")), policy=policy)
    try:
        d, rec = run.decision, run.receipt
        assert d.mode == "overseer_selected" and d.delivered and rec.fallback.chosen_message_id == d.message_id == run.message_of("writer-2")
        w1, w2 = cand(rec, "writer-1"), cand(rec, "writer-2")
        assert (w1.accuracy_fraction, w1.canonical_rank, w1.above_threshold) == ("11/12", 0, True)
        assert (w2.accuracy_fraction, w2.canonical_rank, w2.above_threshold) == ("12/12", 1, True)
        contested = [c for c in w1.claims if c.assessment != "accurate"]
        assert [(c.claim_id, c.assessment) for c in contested] == [("w1.3", "contested")]
        assert any("unresolved" in e and "overseer-pool-1" in e for e in contested[0].evidence)
        # integration step: the essays' receipt carries a named defect at warning (INT-ARG-001, ARG-BARE-001), a risk signal that
        # escalates the review to two independent instances (rewritten from one instance to the stricter planning rule)
        assert all(c.assessment == "accurate" and c.evidence for c in w2.claims) and w2.reviewed_by == ["overseer-pool-1", "overseer-pool-2"]
        assert "12/12 material claims accurate, above the 0.9 threshold" in d.label and d.label.startswith("OVERSEER-SELECTED (not formally checked, not verified)")
        assert rec.fallback.why == rec.formal.reasons and any("CONFLICTING" in r for r in rec.formal.reasons)
        assert agents.calls == ["overseer-pool-1", "overseer-pool-2"] and rec.fallback.overseer.instances == ["overseer-pool-1", "overseer-pool-2"]
        assert rec.fallback.overseer.plan_reasons == ["one instance by default", "1 dossier(s) with risk signals (named_defect): each goes to 2 independent instances (a signal only ever escalates oversight)"]
        assert_honest(d)
        assert verify_delivery_receipt(rec, run.keyring) and verify_delivered_answer(d.answer, rec, run.keyring)
        # the delivered answer carries why the formal path did not complete and the selection evidence, from the receipt
        assert d.answer.formal_reasons == rec.formal.reasons and d.answer.formal_reasons
        assert d.answer.selection == rec.fallback.selection and d.answer.accuracy_fraction == "12/12"
        assert not verify_delivered_answer(d.answer.model_copy(update={"accuracy_fraction": "11/12"}), rec, run.keyring)
    finally:
        run.close()


def test_a_tie_goes_to_the_consolidations_canonical_choice(clock, pack):
    policy, _ = policy_with(clock, pack)
    run = essays(("writer-1", 12, {}), ("writer-2", 12, dict(variant="memory")), policy=policy)
    try:
        d, rec = run.decision, run.receipt
        assert d.mode == "overseer_selected" and d.message_id == run.message_of("writer-1")
        assert [c.accuracy_fraction for c in rec.fallback.candidates] == ["12/12", "12/12"]
        assert any(s.startswith("tie at 12/12") and "canonical choice" in s for s in rec.fallback.selection)
    finally:
        run.close()


@pytest.mark.parametrize("n,contested,delivered", [
    (10, 1, False),   # 9/10 = 0.90 exactly: not above the threshold, withheld
    (10, 2, False),   # 8/10: below, withheld
    (20, 2, False),   # 18/20 = 0.90 exactly
    (11, 1, True),    # 10/11 = 0.909...: above, delivered
    (20, 1, True),    # 19/20 = 0.95
    (12, 0, True),    # 12/12
])
def test_the_best_candidate_is_delivered_only_above_ninety_percent(clock, pack, n, contested, delivered):
    targets = [("rep-writer-1", f"w1.{i}") for i in range(1, contested + 1)]
    policy, _ = policy_with(clock, pack, contest(*targets))
    run = essays(("writer-1", n, {}), policy=policy)
    try:
        d, rec = run.decision, run.receipt
        [c] = rec.fallback.candidates
        assert c.accuracy_fraction == f"{n - contested}/{n}" and c.above_threshold is delivered
        assert Fraction(c.accurate, c.material_claims) == Fraction(n - contested, n)
        if delivered:
            assert d.mode == "overseer_selected" and d.delivered and d.message_id == c.message_id
        else:
            assert d.mode == "withheld" and not d.delivered and rec.fallback.chosen_message_id is None
            assert any(f"has accuracy {n - contested}/{n}, not above 0.9: withheld, never delivered as selected" in s for s in rec.fallback.selection)
            assert "no acceptable candidate's validated accuracy is above the threshold" in d.label
        assert_honest(d)
    finally:
        run.close()


def test_the_threshold_is_compared_exactly():
    assert not accuracy_above(9, 10, 0.90) and not accuracy_above(18, 20, 0.9) and not accuracy_above(900, 1000, 0.9)
    assert accuracy_above(10, 11, 0.90) and accuracy_above(901, 1000, 0.9) and accuracy_above(1, 1, 0.9)
    assert not accuracy_above(0, 0, 0.9) and not accuracy_above(0, 1, 0.9)
    assert not accuracy_above(19, 20, 0.95) and accuracy_above(20, 21, 0.95) is True  # 20/21 = 0.952...


def test_an_operator_may_raise_the_threshold(clock, pack):
    policy, _ = policy_with(clock, pack, contest(("rep-writer-1", "w1.1")), config=DeliveryConfig(min_selected_accuracy=0.95))
    run = essays(("writer-1", 11, {}), policy=policy)  # 10/11 = 0.909: above 0.90, not above 0.95
    try:
        assert run.decision.mode == "withheld" and run.receipt.min_selected_accuracy == 0.95
        assert run.receipt.fallback.candidates[0].above_threshold is False
    finally:
        run.close()


def test_an_unassessed_claim_is_never_accurate(clock, pack):
    """A verdict that reviews no transfer examines nothing: every claim stays unassessed, 0 of n, withheld."""
    policy, _ = policy_with(clock, pack, lambda d: verdict(d, transfers_reviewed=[]))
    run = essays(("writer-1", 12, {}), policy=policy)
    try:
        d, rec = run.decision, run.receipt
        [c] = rec.fallback.candidates
        assert c.accuracy_fraction == "0/12" and all(x.assessment == "unassessed" for x in c.claims) and c.reviewed_by == []
        assert d.mode == "withheld"
    finally:
        run.close()


def test_an_accusation_a_check_refutes_lowers_no_score_and_the_verdict_still_counts(clock, pack):
    """The agent says point w1.2 is not in the response; the deterministic check finds it there (refuted, by a check,
    not by a signed result): the accusation is set aside, the verdict counts, the point is accurate."""
    def false_accusation(d):
        t = response_of(d, "rep-writer-1")
        return verdict(d, [acc("a1", "claim_not_in_response", [{"pointer": ptr(d, "claim", "w1.2") + "/claim_text"}],
                               message_ids=[t["message_id"]], claim_ids=["w1.2"], report_ids=["rep-writer-1"])])
    policy, _ = policy_with(clock, pack, false_accusation)
    run = essays(("writer-1", 12, {}), policy=policy)
    try:
        rec = run.receipt
        # integration step: the named defect on the essays' receipt sends the dossier to two independent instances, each giving
        # the same false accusation (rewritten from one verdict to the stricter planning rule: each is set aside and counts)
        verdicts = rec.fallback.overseer.verdicts
        assert len(verdicts) == 2 and all(s.valid and s.counted and s.accusations == 1 for s in verdicts)
        assert rec.fallback.candidates[0].accuracy_fraction == "12/12" and run.decision.mode == "overseer_selected"
    finally:
        run.close()


# ============================================================================================ signed engine results
def test_a_signed_engine_refutation_excludes_a_candidate_while_another_has_none(clock, pack):
    """writer-1 scores higher (19 of 20: the seventh point is a quantitative claim the engine refutes, COUNTEREXAMPLE,
    signed) than writer-2 (11 of 12: one point contested), but a candidate with a refuted material claim is never
    delivered while another has none."""
    verify = Verifier(clock, outcomes={"w1.7": refuted_outcome})
    policy, _ = policy_with(clock, pack, contest(("rep-writer-2", "w2.5")))
    run = essays(("writer-1", 20, dict(refuted=[7])), ("writer-2", 12, dict(variant="memory")), verify=verify, policy=policy)
    try:
        d, rec = run.decision, run.receipt
        w1, w2 = cand(rec, "writer-1"), cand(rec, "writer-2")
        assert (w1.accuracy_fraction, w1.refuted, w1.above_threshold) == ("19/20", True, True)
        assert (w2.accuracy_fraction, w2.refuted, w2.above_threshold) == ("11/12", False, True)
        assert Fraction(19, 20) > Fraction(11, 12)  # the refuted candidate is the more accurate one ...
        assert d.mode == "overseer_selected" and d.message_id == w2.message_id  # ... and is still excluded
        [refuted] = [c for c in w1.claims if c.claim_id == "w1.7"]
        rc = run.receipts[w1.message_id]
        [o] = [o for o in rc.outcomes if o.claim_id == "w1.7"]
        assert o.display_status.value == "COUNTEREXAMPLE" and o.verification.signature
        assert refuted.assessment == "inaccurate" and refuted.refuted_by_signed_result
        assert any(o.verification.result_id in e and "COUNTEREXAMPLE" in e for e in refuted.evidence)
        assert any("never delivered while another candidate has no refuted claim" in s and w1.message_id in s for s in rec.fallback.selection)
        payload = SpecialistReport.model_validate(d.answer.payload)
        assert REFUTED_TEXT not in payload.original_response
    finally:
        run.close()


def test_a_verdict_contradicting_a_signed_result_is_rejected(clock, pack):
    """The formal path is unresolved (no fidelity review); the only overseer agent states the claim's signed result
    wrongly: production validation refutes the engine statement (OVS-AGENT-001) and none of the verdict's reviews
    counts, so nothing is confirmed accurate and the answer is withheld. The same verdict with the right status counts."""
    for wrong, mode in ((True, "withheld"), (False, "overseer_selected")):
        policy, _ = policy_with(clock, pack, state_results(wrong=wrong))
        run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, reviewer=False))
        try:
            d, rec = run.decision, run.receipt
            [standing] = rec.fallback.overseer.verdicts
            assert standing.valid and standing.counted is (not wrong) and d.mode == mode, (wrong, standing)
            [c] = rec.fallback.candidates
            if wrong:
                assert any("contradicts the stored result" in r and "OVS-AGENT-001" in r for r in standing.reasons)
                assert c.reviewed_by == [] and c.claims[0].assessment == "unassessed" and c.accuracy_fraction == "0/1"
                # the production validation recorded it in the signed verdicts audit
                audit = d.review.reviews[run.session.channel.channel_uid].audit
                assert audit.audit_id == rec.fallback.overseer.verdicts_audit_id and verify_audit(audit, run.keyring)
                assert any(f.code == "OVS-AGENT-001" for f in audit.report.findings)
            else:
                assert c.reviewed_by == ["overseer-pool-1"] and c.accuracy_fraction == "1/1"
                assert any("ENTAILED (encoding only)" in e for e in c.claims[0].evidence)
            assert_honest(d)
        finally:
            run.close()


# ============================================================================================ the overseer stage's deadline
def test_the_overseer_deadline_withholds_by_default(clock, pack):
    policy, agents = policy_with(clock, pack, delay=300.0)  # the agent replies after 300 s; the stage has 240 s
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, reviewer=False))
    try:
        d, rec = run.decision, run.receipt
        stage = rec.fallback.overseer
        assert stage.timed_out and stage.elapsed_s == 300.0 and [c["state"] for c in stage.provider_calls] == ["late"]
        assert d.mode == "withheld" and "the overseer stage established no accuracy" in d.label and rec.overseer_s == 300.0
        assert any("ran out of its budget" in s for s in rec.fallback.selection)
        assert all(r["status"] != "ok" for r in stage.runs) and stage.verdicts == []  # the late reply was never counted
        assert_honest(d)
    finally:
        run.close()


def test_the_overseer_deadline_delivers_the_canonical_answer_not_checked_only_when_configured(clock, pack):
    cfg = DeliveryConfig(on_overseer_timeout="deliver_canonical_not_checked")
    policy, _ = policy_with(clock, pack, delay=300.0, config=cfg)
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, reviewer=False))
    try:
        d, rec = run.decision, run.receipt
        assert d.mode == "not_checked" and d.delivered and d.message_id == next(iter(run.receipts))
        assert d.label.startswith("NOT CHECKED (not formally checked, not verified, no accuracy established): the overseer stage ran out of its budget")
        assert rec.fallback.overseer.timed_out and "labelled NOT CHECKED" in rec.fallback.selection[-1]
        assert_honest(d)
        assert verify_delivered_answer(d.answer, rec, run.keyring)
        assert d.answer.accuracy_fraction is None and d.answer.selection == rec.fallback.selection and d.answer.formal_reasons
    finally:
        run.close()


def test_after_the_overseer_deadline_no_further_instance_is_called(clock, pack):
    """Two instances (a repeated fault in the task): the first replies after 300 s (late, never counted); the second
    would start after the 240 s deadline, so its provider is never called. Nothing is established: withheld."""
    text, claims = bad_answer()
    policy, agents = policy_with(clock, pack, delay=300.0)
    run = english_task(policy, [english("english-1", 1, text, claims), english("english-2", 2, text, claims), english("english-3", 3)])
    try:
        stage = run.receipt.fallback.overseer
        assert stage.instances == ["overseer-pool-1", "overseer-pool-2"]
        assert [(c["agent_id"], c["state"]) for c in stage.provider_calls] == [("overseer-pool-1", "late"), ("overseer-pool-2", "skipped_budget")]
        assert agents.made["overseer-pool-1"].calls == ["overseer-pool-1"] and agents.made["overseer-pool-2"].calls == []
        assert stage.timed_out and stage.verdicts == [] and run.decision.mode == "withheld"
        assert_honest(run.decision)
    finally:
        run.close()


def test_a_longer_overseer_budget_lets_the_slow_agent_count(clock, pack):
    policy, _ = policy_with(clock, pack, delay=300.0, config=DeliveryConfig(overseer_budget_s=400.0))
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, reviewer=False))
    try:
        assert run.decision.mode == "overseer_selected" and not run.receipt.fallback.overseer.timed_out and run.receipt.overseer_s == 300.0
    finally:
        run.close()


def test_without_overseer_agents_not_checked_needs_the_configuration_and_a_canonical_answer(clock):
    cfg = DeliveryConfig(on_overseer_timeout="deliver_canonical_not_checked")
    run = run_task(DeliveryPolicy(clock=clock, config=cfg), [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, reviewer=False))
    try:
        assert run.decision.mode == "not_checked" and "no overseer agent is configured" in run.decision.label
        assert_honest(run.decision)
    finally:
        run.close()
    # two conflicting answers: the consolidation has no canonical answer, so even this configuration withholds
    run = essays(("writer-1", 3, {}), ("writer-2", 3, dict(variant="memory")), policy=DeliveryPolicy(clock=clock, config=cfg))
    try:
        assert run.decision.mode == "withheld" and any("there is none (consolidation CONFLICTING)" in s for s in run.receipt.fallback.selection)
    finally:
        run.close()


# ============================================================================================ candidates
def test_a_single_candidate_is_scored_and_delivered_only_above_the_threshold(clock, pack):
    policy, agents = policy_with(clock, pack)
    run = essays(("writer-1", 12, {}), policy=policy)
    try:
        d, rec = run.decision, run.receipt
        [c] = rec.fallback.candidates
        assert c.canonical and c.canonical_rank == 0 and c.deliverable and c.accuracy_fraction == "12/12"
        assert d.mode == "overseer_selected" and d.message_id == c.message_id and rec.fallback.non_candidates == []
        # integration step: the receipt's named defect at warning (INT-ARG-001, ARG-BARE-001) escalates the review (rewritten from
        # "one instance by default" alone to the stricter planning rule)
        assert agents.calls == ["overseer-pool-1", "overseer-pool-2"] and rec.fallback.overseer.plan_reasons == ["one instance by default", "1 dossier(s) with risk signals (named_defect): each goes to 2 independent instances (a signal only ever escalates oversight)"]
    finally:
        run.close()


def english(agent, n, text=EN_TEXT, claims=None):
    return (agent, english_report(text=text, claims=[dict(c) for c in (claims if claims is not None else EN_CLAIMS)], report_id=f"rep-{agent}-{n}", agent=agent))


def english_task(policy, answers):
    plan = make_plan(selected_agent_ids=EN_AGENTS)
    return run_task(policy, answers, verify=problems_fn({"en-point": point_problem()}), question=EN_INPUT, plan=plan, supplied=[DOC])


def test_duplicated_instances_are_every_one_a_candidate_and_a_tie_goes_to_the_groups_canonical_member(clock, pack):
    policy, _ = policy_with(clock, pack)
    run = english_task(policy, [english("english-1", 1), english("english-2", 2), english("english-3", 3)])
    try:
        d, rec = run.decision, run.receipt
        assert rec.consolidation_status == "CONSOLIDATED" and len(rec.fallback.candidates) == 3
        assert len({c.group_id for c in rec.fallback.candidates}) == 1
        assert [(c.agent_id, c.canonical, c.canonical_rank) for c in rec.fallback.candidates] == [("english-1", True, 0), ("english-2", False, 1), ("english-3", False, 2)]
        assert d.mode == "overseer_selected" and d.message_id == run.message_of("english-1")
    finally:
        run.close()


def test_a_repeated_fault_gets_two_pool_instances_and_the_excluded_answers_are_never_delivered(clock, pack):
    text, claims = bad_answer()
    policy, agents = policy_with(clock, pack)
    run = english_task(policy, [english("english-1", 1, text, claims), english("english-2", 2, text, claims), english("english-3", 3)])
    try:
        d, rec = run.decision, run.receipt
        stage = rec.fallback.overseer
        assert stage.instances == ["overseer-pool-1", "overseer-pool-2"] and len(stage.instances) <= 4 and sorted(agents.calls) == stage.instances
        bad1, bad2, good = cand(rec, "english-1"), cand(rec, "english-2"), cand(rec, "english-3")
        assert not bad1.deliverable and "INT-REQ-003" in bad1.answer_level_faults and bad1.faulted
        assert not bad2.deliverable and any("OVS-REP-001" in r for r in bad2.integrity_reasons)
        assert good.deliverable and good.accuracy_fraction == "1/1" and good.reviewed_by == ["overseer-pool-1", "overseer-pool-2"]
        assert d.mode == "overseer_selected" and d.message_id == good.message_id
    finally:
        run.close()


def test_an_honest_instance_counts_where_a_lying_instance_is_rejected(clock, pack):
    text, claims = bad_answer()
    replies = {"overseer-pool-1": state_results(wrong=True), "overseer-pool-2": silent}
    policy, _ = policy_with(clock, pack, replies=replies)
    run = english_task(policy, [english("english-1", 1, text, claims), english("english-2", 2, text, claims), english("english-3", 3)])
    try:
        rec = run.receipt
        standing = {v.agent_id: v.counted for v in rec.fallback.overseer.verdicts}
        assert standing == {"overseer-pool-1": False, "overseer-pool-2": True}
        assert cand(rec, "english-3").reviewed_by == ["overseer-pool-2"] and run.decision.mode == "overseer_selected"
    finally:
        run.close()
    replies = {"overseer-pool-1": state_results(wrong=True), "overseer-pool-2": state_results(wrong=True)}
    policy, _ = policy_with(clock, pack, replies=replies)
    run = english_task(policy, [english("english-1", 1, text, claims), english("english-2", 2, text, claims), english("english-3", 3)])
    try:
        assert run.decision.mode == "withheld" and cand(run.receipt, "english-3").accuracy_fraction == "0/1"
    finally:
        run.close()


# ============================================================================================ the fallback never edits
@pytest.mark.parametrize("scenario", ["overseer_selected", "not_checked", "withheld"])
def test_no_fallback_changes_what_a_claim_says(clock, pack, scenario):
    """Whatever the fallback decides, the claims are the journaled ones: the delivered payload is byte for byte the
    chosen answer's (no claim edited, no figure widened, no premise added, no claim dropped); nothing is translated
    again, no transfer is added to the journal and no receipt changes."""
    report = physics_report(AGENT, "rep-a", (("p1.1", "The speed is 15 km/h."), ("p1.2", "The car therefore covers 15 km in every hour of its journey.")))
    verify = Verifier(clock, reviewer=False)
    if scenario == "overseer_selected":
        policy, _ = policy_with(clock, pack)
    elif scenario == "not_checked":
        policy, _ = policy_with(clock, pack, delay=300.0, config=DeliveryConfig(on_overseer_timeout="deliver_canonical_not_checked"))
    else:
        policy, _ = policy_with(clock, pack, contest(("rep-a", "p1.2")))
    run = run_task(policy, [(AGENT, report)], verify=verify, decide=False)
    try:
        before = journal_state(run)
        calls = list(verify.calls)
        d = run.session.decide(request_message_ids=run.mids, receipts=run.receipts)
        assert d.mode == scenario and journal_state(run) == before and verify.calls == calls
        [mid] = list(run.receipts)
        if d.delivered:
            assert d.answer.payload == run.messages[mid].payload and payload_hash(d.answer.payload) == run.messages[mid].payload_sha256
            delivered = SpecialistReport.model_validate(d.answer.payload)
            assert delivered == report
            assert [(c.claim_id, c.claim_text, c.materiality) for c in delivered.claims] == [(c.claim_id, c.claim_text, c.materiality) for c in report.claims]
            assert verify_delivered_answer(d.answer, d.receipt, run.keyring)
            d.answer.payload["claims"][1]["claim_text"] = "The speed is at least 10 km/h."  # the router's copy is its own
            assert run.messages[mid].payload["claims"][1]["claim_text"] == "The speed is 15 km/h."
            assert SpecialistReport.model_validate(journal_payload(run, mid)) == report
        for c in d.receipt.fallback.candidates:
            assert [x.claim_id for x in c.claims] == ["p1.1", "p1.2"]  # every material claim is scored: none dropped
        assert_honest(d)
    finally:
        run.close()
