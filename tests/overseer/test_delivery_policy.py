"""The delivery policy's formal path and its budget (``docs/DELIVERY.md``): the founder's four-minute translation budget,
measured on an injected fake monotonic clock, with fixture translators and reviewers only (no model, no network).

Covered here: a fast clean answer delivered FORMALLY CHECKED with a signed delivery receipt (and no overseer call); a slow
translator (no fallback while the formal stage is inside 240 s, the fallback after it: a claim finishing after the
deadline is late, a claim the deadline reaches unstarted is never started); every way the formal path ends unresolved
(no or a negative fidelity review, an ambiguous, invalid or unsupported translation, no outcome, a solver cut-off, a
substituted figure, a refuted claim, nothing eligible) falling back with the cause named; the labels and the receipt
(signed, tamper-evident, the scope statement kept, the times recorded); the configuration's floor; and the session
mechanics (the channel's verifier restored, a decision made once, the policy's own failure withheld)."""
from __future__ import annotations

import socket
import threading

import pytest
from pydantic import ValidationError

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.hub import AuditorNotAttached
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.statuses import SCOPE_STATEMENT
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.integrity.contracts import payload_hash
from epinoic_logic.overseer import load_pack
from epinoic_logic.overseer.delivery_policy import (
    DELIVERY_SCOPE_STATEMENT, FOUNDER_MIN_SELECTED_ACCURACY, FOUNDER_TRANSLATION_BUDGET_S, DeadlineVerifier, DeliveredAnswer, DeliveryConfig,
    DeliveryPolicy, TranslationStage, is_fallback_label_honest, verify_delivered_answer, verify_delivery_receipt,
)
from epinoic_logic.overseer.export import export_pack
from epinoic_logic.overseer.keys import DELIVERY_KEY_ID
from epinoic_logic.translate.contracts import SpecialistReport

from .conftest import CFG, KEY, make_keyring
from .delivery_support import (
    ESSAY, ESSAY_QUESTION, PHYSICS, Agents, FakeClock, ScriptedOverseer, Verifier, assert_honest, essay_report, physics_report, refuted_outcome,
    run_task, silent, speed_translation,
)

THREE = (("p1.1", "The speed is 15 km/h."), ("p1.2", "Its average speed is 15 km/h."), ("p1.3", "The car moves at 15 km/h."))
AGENT = "physics-specialist"


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


def with_agents(clock, pack, **kw):
    agents = Agents(clock, **{k: v for k, v in kw.items() if k in ("reply", "delay")})
    policy = DeliveryPolicy(clock=clock, pack=pack, provider_factory=agents, **{k: v for k, v in kw.items() if k not in ("reply", "delay")})
    return policy, agents


# ============================================================================================ the formal path
def test_the_founders_budget_and_threshold_are_the_defaults():
    cfg = DeliveryConfig()
    assert cfg.translation_budget_s == FOUNDER_TRANSLATION_BUDGET_S == 240.0
    assert cfg.min_selected_accuracy == FOUNDER_MIN_SELECTED_ACCURACY == 0.90
    assert cfg.on_overseer_timeout == "withhold" and cfg.overseer_budget_s == 240.0


def test_a_fast_clean_answer_is_delivered_formally_checked_with_a_signed_receipt(clock):
    verifier = Verifier(clock, delays={"*": 5})
    run = run_task(DeliveryPolicy(clock=clock), [(AGENT, physics_report(AGENT, "rep-a"))], verify=verifier)
    try:
        d, rec = run.decision, run.receipt
        assert d.mode == "formally_checked" and d.delivered
        [mid] = list(run.receipts)
        assert d.message_id == mid == rec.delivered_message_id and rec.delivered_agent_id == AGENT and rec.delivered_report_id == "rep-a"
        assert d.label.startswith("FORMALLY CHECKED within the 240 s translation budget") and "properties of the encodings only" in d.label
        assert_honest(d)
        # the formal path: the one material eligible claim is clean (translated, ENTAILED, release permitted), within budget
        assert rec.formal.complete and rec.formal.within_budget and rec.formal.reasons == [] and rec.formal.receipt_error_codes == []
        [claim] = rec.formal.claims
        assert (claim.claim_id, claim.eligible, claim.outcome, claim.translation_status, claim.display_status) == ("p1.1", True, "clean", "TRANSLATED", "ENTAILED")
        assert claim.result_id and claim.reasons == [] and rec.formal.clearance == "AUDIT_PASSED"
        # the times: two verifier calls of 5 s each (the evidence claim and the material claim); no overseer stage
        assert rec.translation_s == rec.time_to_decision_s == 10.0 and rec.overseer_s is None and rec.fallback is None
        assert rec.translation_budget_s == 240.0 and rec.consolidation_status in ("CONSOLIDATED", "CONSOLIDATED_WITH_FINDINGS")
        # the receipt is signed under the delivery key and keeps the scope statement; the payload is the journaled one
        assert verify_delivery_receipt(rec, run.keyring) and rec.signature_key_id == DELIVERY_KEY_ID == "overseer-delivery"
        assert rec.scope_statement == DELIVERY_SCOPE_STATEMENT and rec.scope_statement.startswith(SCOPE_STATEMENT)
        assert verify_delivered_answer(d.answer, rec, run.keyring)
        assert d.answer.payload == run.messages[mid].payload and d.answer.payload_sha256 == run.messages[mid].payload_sha256
        assert (d.answer.formal_reasons, d.answer.selection, d.answer.accuracy_fraction) == ([], [], None)
    finally:
        run.close()


def test_the_formal_path_makes_no_overseer_call(clock, pack):
    policy, agents = with_agents(clock, pack)
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, delays={"*": 1}))
    try:
        assert run.decision.mode == "formally_checked" and agents.made == {} and agents.calls == []
    finally:
        run.close()


def test_a_report_with_several_claims_is_formally_checked_only_when_every_one_is_clean(clock, pack):
    policy, agents = with_agents(clock, pack)
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a", THREE))], verify=Verifier(clock, delays={"*": 10}))
    try:
        rec = run.receipt
        assert run.decision.mode == "formally_checked" and [c.outcome for c in rec.formal.claims] == ["clean"] * 3
        assert "each of the 3 material eligible claim(s)" in run.decision.label and rec.translation_s == 40.0 and agents.calls == []
    finally:
        run.close()
    # one of the three unresolved (an unfaithful review): the formal path does not complete
    policy, agents = with_agents(clock, pack)
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a", THREE))], verify=Verifier(clock, reviews={"p1.2": "unfaithful"}))
    try:
        rec = run.receipt
        assert run.decision.mode != "formally_checked" and not rec.formal.complete
        assert [c.outcome for c in rec.formal.claims] == ["clean", "unresolved", "clean"]
        assert any(r.startswith("claim p1.2: unresolved") and "unfaithful" in r for r in rec.formal.reasons) and agents.calls
    finally:
        run.close()


# ============================================================================================ the budget
@pytest.mark.parametrize("seconds", [1.0, 200.0, 239.0, 240.0])
def test_inside_the_budget_there_is_no_fallback(clock, pack, seconds):
    """A translation that ends at or before 240 s on the policy's clock: the formal path decides, no overseer agent runs."""
    policy, agents = with_agents(clock, pack)
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, delays={"p1.1": seconds}))
    try:
        rec = run.receipt
        assert run.decision.mode == "formally_checked" and rec.formal.within_budget and rec.translation_s == seconds
        assert rec.fallback is None and agents.made == {} and rec.overseer_s is None
    finally:
        run.close()


@pytest.mark.parametrize("seconds", [240.5, 241.0, 300.0, 1000.0])
def test_a_slow_translator_falls_back_after_the_budget(clock, pack, seconds):
    """The claim's verification ends after 240 s: its outcome is late (kept on the receipt, never counted as the formal
    path), and the overseer stage starts only after the budget is spent."""
    policy, agents = with_agents(clock, pack)
    verifier = Verifier(clock, delays={"p1.1": seconds})
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=verifier)
    try:
        d, rec = run.decision, run.receipt
        assert d.mode == "overseer_selected" and not rec.formal.complete and not rec.formal.within_budget
        [claim] = rec.formal.claims
        assert claim.outcome == "late" and claim.finished_s == seconds and claim.display_status == "ENTAILED"  # the late outcome stays recorded
        assert rec.formal.late_claims == ["rep-a#p1.1"] and rec.formal.skipped_claims == []
        assert any(f"took {seconds:g} s, past the 240 s translation budget" in r for r in rec.formal.reasons)
        # the fallback ran after the budget: every overseer call started at or after 240 s on the policy's clock
        stage = rec.fallback.overseer
        assert stage.ran and stage.started_at_s == seconds >= 240.0 and agents.calls == ["overseer-pool-1"]
        assert all(c["state"] == "in_time" for c in stage.provider_calls)
        assert rec.translation_s == seconds and rec.time_to_decision_s == seconds and rec.overseer_s == 0.0
        assert_honest(d)
        assert verify_delivery_receipt(rec, run.keyring)
    finally:
        run.close()


def test_at_the_deadline_no_new_claim_is_started_and_the_fallback_follows(clock, pack):
    """130 s per claim: the first ends in time (130 s), the second ends late (260 s), the third is reached at 260 s and
    is never started (NOT_ATTEMPTED, ``skipped_budget``): the translator is not called for it."""
    policy, agents = with_agents(clock, pack)
    verifier = Verifier(clock, delays={"p1.1": 130, "p1.2": 130, "p1.3": 130})
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a", THREE))], verify=verifier)
    try:
        rec = run.receipt
        assert [c[1] for c in verifier.calls] == ["p1.0", "p1.1", "p1.2"]  # p1.3 was never started
        assert [(c.claim_id, c.outcome) for c in rec.formal.claims] == [("p1.1", "clean"), ("p1.2", "late"), ("p1.3", "skipped_budget")]
        assert rec.formal.late_claims == ["rep-a#p1.2"] and rec.formal.skipped_claims == ["rep-a#p1.3"]
        rc = run.receipts[run.decision.receipt.formal.deliverable_message_id]
        assert "p1.3" not in {o.claim_id for o in rc.outcomes}  # no outcome: the claim is NOT_ATTEMPTED, never a success
        assert rec.fallback.overseer.started_at_s == 260.0 and agents.calls == ["overseer-pool-1"]
        assert run.decision.mode == "overseer_selected" and rec.translation_s == 260.0
    finally:
        run.close()


def test_a_claim_reached_exactly_at_the_deadline_is_not_started(clock, pack):
    policy, agents = with_agents(clock, pack)
    verifier = Verifier(clock, delays={"p1.1": 240})
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a", THREE))], verify=verifier)
    try:
        rec = run.receipt
        assert [c[1] for c in verifier.calls] == ["p1.0", "p1.1"] and rec.formal.skipped_claims == ["rep-a#p1.2", "rep-a#p1.3"]
        assert rec.formal.claims[0].outcome == "clean" and rec.formal.late_claims == [] and run.decision.mode != "formally_checked"
        assert any("ran out before claim(s) rep-a#p1.2, rep-a#p1.3 were started" in r for r in rec.formal.reasons)
    finally:
        run.close()


def test_a_configured_budget_replaces_the_default(clock, pack):
    policy, agents = with_agents(clock, pack, config=DeliveryConfig(translation_budget_s=60.0))
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, delays={"p1.1": 61}))
    try:
        assert run.decision.mode == "overseer_selected" and run.receipt.translation_budget_s == 60.0 and run.receipt.formal.claims[0].outcome == "late"
        assert "within the" not in run.decision.label
    finally:
        run.close()


def test_the_stage_starts_when_the_session_opens_not_at_the_decision(clock, pack):
    """Time spent before the first answer reaches the hub is not the translator's; time between answers is."""
    policy, agents = with_agents(clock, pack)
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock), decide=False)
    try:
        clock.advance(241)  # the router waits 241 s before deciding: the formal stage is out of budget
        d = run.session.decide(request_message_ids=run.mids, receipts=run.receipts)
        assert d.mode == "overseer_selected" and not d.receipt.formal.within_budget and d.receipt.translation_s == 241.0
        assert any("took 241 s, past the 240 s" in r for r in d.receipt.formal.reasons)
    finally:
        run.close()


# ============================================================================================ unresolved outcomes
CUT = SolverConfig(timeout_ms=3000, rlimit=1, memory_max_mb=None)
UNRESOLVED = {
    "no fidelity review": (dict(reviewer=False), "no semantic-fidelity review"),
    "unfaithful review": (dict(reviews={"p1.1": "unfaithful"}), "the fidelity review is unfaithful"),
    "uncertain review": (dict(reviews={"p1.1": "uncertain"}), "the fidelity review is uncertain"),
    "ambiguous translation": (dict(translations={"p1.1": speed_translation("p1.1", ambiguous=True)}), "AMBIGUOUS_TRANSLATION"),
    "invalid translation": (dict(translations={"p1.1": speed_translation("p1.1", broken=True)}), "INVALID_FORMALIZATION"),
    "untranslatable claim": (dict(translations={"p1.1": speed_translation("p1.1", unsupported="no encoding of this claim")}), "UNSUPPORTED"),
    "no outcome": (dict(none=["p1.1"]), "NOT_ATTEMPTED"),
    "solver cut-off": (dict(config=CUT), "display status TIMEOUT"),
    "substituted figure": (dict(translations={"p1.1": speed_translation("p1.1", distance=160, speed=20)}), "failed grounding checks: D"),
    "refuted claim": (dict(outcomes={"p1.1": refuted_outcome}), "COUNTEREXAMPLE"),
}


#: The cases whose receipt carries a risk signal (integration step: the pool sends their dossier to two instances).
ESCALATED_CASES = frozenset({"substituted figure"})


@pytest.mark.parametrize("case", sorted(UNRESOLVED))
def test_an_unresolved_formal_path_falls_back_and_names_the_cause(clock, pack, case):
    kw, cause = UNRESOLVED[case]
    policy, agents = with_agents(clock, pack)
    verifier = Verifier(clock, **kw)
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=verifier, config=kw.get("config", CFG))
    try:
        d, rec = run.decision, run.receipt
        assert d.mode != "formally_checked" and not rec.formal.complete and rec.formal.within_budget  # inside the budget: unresolved, not late
        assert any(cause in r for r in rec.formal.reasons), rec.formal.reasons
        # integration step: a receipt carrying a risk signal (the substituted figure's claim rests on a task premise its task
        # refutes: INT-ARG-001, EVD-SRC-005, an unchecked source) goes to two independent instances; the other causes carry
        # none (rewritten from one instance in every case to the stricter planning rule)
        want = ["overseer-pool-1", "overseer-pool-2"] if case in ESCALATED_CASES else ["overseer-pool-1"]
        assert rec.fallback is not None and rec.fallback.why == rec.formal.reasons and agents.calls == want
        assert rec.fallback.overseer.started_at_s == 0.0  # an unresolved path falls back at once: no wait for the budget
        if case == "refuted claim":
            # the only candidate's one material claim is refuted by a signed engine result: 0/1, withheld
            [cand] = rec.fallback.candidates
            assert cand.refuted and cand.accuracy_fraction == "0/1" and d.mode == "withheld"
        else:
            # the claim itself is not at fault (its translation is): the overseer's validated review gives 1/1
            [cand] = rec.fallback.candidates
            assert cand.accuracy_fraction == "1/1" and d.mode == "overseer_selected" and d.answer.payload == run.messages[d.message_id].payload
        assert_honest(d)
        assert verify_delivery_receipt(rec, run.keyring)
    finally:
        run.close()


@pytest.mark.parametrize("case", sorted(UNRESOLVED))
def test_without_overseer_agents_an_unresolved_formal_path_is_withheld(clock, case):
    kw, cause = UNRESOLVED[case]
    run = run_task(DeliveryPolicy(clock=clock), [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, **kw), config=kw.get("config", CFG))
    try:
        d, rec = run.decision, run.receipt
        assert d.mode == "withheld" and not d.delivered and rec.fallback.overseer.configured is False
        assert rec.fallback.overseer.error == "no overseer agent is configured (no knowledge pack and provider factory)"
        assert d.label.startswith("WITHHELD (not formally checked, not verified)") and "established no accuracy" in d.label
        assert all(c.assessment == "unassessed" or c.assessment == "inaccurate" for cand in rec.fallback.candidates for c in cand.claims)
        assert_honest(d)
    finally:
        run.close()


def test_an_answer_with_nothing_eligible_is_never_formally_checked(clock, pack):
    """Vacuous success is no success: an answer none of whose material claims is eligible for the formal check falls back."""
    policy, agents = with_agents(clock, pack)
    run = run_task(policy, [("writer-1", essay_report("writer-1", "rep-w1", 5, prefix="w1"))], question=ESSAY_QUESTION, ids=ESSAY)
    try:
        rec = run.receipt
        assert all(c.outcome == "not_eligible" and not c.eligible for c in rec.formal.claims) and len(rec.formal.claims) == 5
        assert "the deliverable has no material eligible claim: nothing was formally checked" in rec.formal.reasons
        assert run.decision.mode == "overseer_selected" and rec.fallback.candidates[0].accuracy_fraction == "5/5"
    finally:
        run.close()


def test_a_verifier_that_raises_records_the_failure_and_never_delivers_formally(clock, pack):
    """The channel turns the exception into a warning (INT-REQ-006); the shadow channel cannot reproduce it, so the
    transfer audit fails (OVS-RCPT-008) and the consolidation excludes the answer: nothing is delivered, whatever the
    overseer agents say (recorded as a finding for the bug-testing phase in ``docs/DELIVERY.md``)."""
    policy, agents = with_agents(clock, pack)
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, raises=["p1.1"]))
    try:
        d, rec = run.decision, run.receipt
        assert d.mode == "withheld" and rec.consolidation_status == "NO_DELIVERABLE_OUTPUT"
        [cand] = rec.fallback.candidates
        assert not cand.deliverable and any("the consolidation excludes it" in r for r in cand.integrity_reasons)
        assert "no candidate is acceptable: withheld" in rec.fallback.selection
        assert_honest(d)
    finally:
        run.close()


# ============================================================================================ labels and receipts
def test_the_label_check_refuses_every_claim_of_checking_outside_the_formal_path():
    assert is_fallback_label_honest("formally_checked", "FORMALLY CHECKED within the 240 s translation budget: ...")
    assert not is_fallback_label_honest("formally_checked", "OVERSEER-SELECTED ...")
    honest = "OVERSEER-SELECTED (not formally checked, not verified): advisory."
    assert is_fallback_label_honest("overseer_selected", honest)
    for bad in ("OVERSEER-SELECTED: verified by the overseer agents.", "FORMALLY CHECKED by the overseer.",
                "OVERSEER-SELECTED (not formally checked): verified.", "WITHHELD (not verified)", honest + " Verified."):
        assert not is_fallback_label_honest("overseer_selected", bad), bad
        assert not is_fallback_label_honest("withheld", bad), bad


def test_a_tampered_receipt_or_payload_no_longer_verifies(clock):
    run = run_task(DeliveryPolicy(clock=clock), [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock))
    try:
        d, rec, keyring = run.decision, run.receipt, run.keyring
        assert verify_delivery_receipt(rec, keyring) and verify_delivered_answer(d.answer, rec, keyring)
        for change in ({"mode": "overseer_selected"}, {"label": rec.label + " "}, {"time_to_decision_s": 1.0}, {"delivered_message_id": "m-other"},
                       {"signature_key_id": "overseer-audit"}, {"signature": None}):
            assert not verify_delivery_receipt(rec.model_copy(update=change), keyring), change
        other = make_keyring()  # same engine keys, same secret: verifies; another secret does not
        assert verify_delivery_receipt(rec, other)
        from epinoic_logic.overseer import EngineKey, KeyRing
        stranger = KeyRing({"hub": EngineKey(KEY)}, b"another-overseer-secret-0123456789abcdef")
        assert not verify_delivery_receipt(rec, stranger) and not verify_delivery_receipt(rec.model_dump(), keyring)
        # a payload edited after the decision (a claim reworded, a figure widened) no longer matches the receipt
        edited = dict(d.answer.payload)
        claims = [dict(c) for c in edited["claims"]]
        claims[1]["claim_text"] = "The speed is about 15 km/h."
        edited["claims"] = claims
        forged = DeliveredAnswer(**{**d.answer.model_dump(), "payload": edited, "payload_sha256": payload_hash(edited)})
        assert not verify_delivered_answer(forged, rec, keyring)
        relabelled = d.answer.model_copy(update={"label": "FORMALLY CHECKED by everyone"})
        assert not verify_delivered_answer(relabelled, rec, keyring)
        for change in ({"formal_reasons": ["none"]}, {"selection": ["selected by the agents"]}, {"accuracy_fraction": "1/1"}):
            assert not verify_delivered_answer(d.answer.model_copy(update=change), rec, keyring), change
    finally:
        run.close()


def test_the_receipt_records_the_three_times(clock, pack):
    """Time to decision = translation (formal stage) + the fallback's overseer stage, on the policy's clock."""
    policy, agents = with_agents(clock, pack, delay=30.0)
    run = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, delays={"p1.1": 20}, reviewer=False))
    try:
        rec = run.receipt
        assert rec.translation_s == 20.0 and rec.overseer_s == 30.0 and rec.time_to_decision_s == 50.0
        assert rec.fallback.overseer.started_at_s == 20.0 and rec.fallback.overseer.elapsed_s == 30.0
        assert [c["state"] for c in rec.fallback.overseer.provider_calls] == ["in_time"]
    finally:
        run.close()


# ============================================================================================ configuration and session
def test_the_configuration_never_goes_below_the_founders_threshold_and_is_validated():
    for bad in (dict(min_selected_accuracy=0.85), dict(min_selected_accuracy=0.8999), dict(min_selected_accuracy=1.0), dict(translation_budget_s=0),
                dict(translation_budget_s=-1.0), dict(overseer_budget_s=0), dict(translation_budget_s="240"), dict(on_overseer_timeout="deliver"),
                dict(clearance_wait_ms=10_000), dict(budget=240)):
        with pytest.raises(ValidationError):
            DeliveryConfig(**bad)
    assert DeliveryConfig(min_selected_accuracy=0.95).min_selected_accuracy == 0.95
    with pytest.raises(TypeError):
        DeliveryPolicy(config={"translation_budget_s": 10})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DeliveryPolicy(clock=240.0)  # type: ignore[arg-type]


def test_overseer_agents_need_both_a_pack_and_a_provider_factory(pack):
    with pytest.raises(ValueError):
        DeliveryPolicy(pack=pack)
    with pytest.raises(ValueError):
        DeliveryPolicy(provider_factory=lambda aid: None)
    assert "overseer=configured" in repr(DeliveryPolicy(pack=pack, provider_factory=lambda aid: ScriptedOverseer(silent)))
    assert "overseer=none" in repr(DeliveryPolicy())


def test_the_policy_decides_only_with_the_transfer_auditor_attached():
    hub = RouterHub(signing_key=KEY, config=CFG)
    try:
        plan = WorkPlan(plan_id="plan-x", selected_agent_ids=[AGENT], **PHYSICS)
        hub.open_task(plan)
        with pytest.raises(AuditorNotAttached):
            DeliveryPolicy().start(hub, plan.task_id)
    finally:
        hub.close()


def test_the_session_restores_the_channels_verifier_and_decides_once(clock):
    verifier = Verifier(clock)
    run = run_task(DeliveryPolicy(clock=clock), [(AGENT, physics_report(AGENT, "rep-a"))], verify=verifier, decide=False)
    try:
        ch = run.session.channel
        assert isinstance(ch.verify_claim_fn, DeadlineVerifier) and ch.verify_claim_fn.inner is verifier
        first = run.session.decide(request_message_ids=run.mids, receipts=run.receipts)
        assert ch.verify_claim_fn is verifier  # restored
        clock.advance(500)
        again = run.session.decide(request_message_ids=run.mids, receipts=run.receipts)
        assert again is first and first.mode == "formally_checked"
    finally:
        run.close()


def test_a_decision_never_waits_for_another_deliverables_overseer_stage(clock, pack):
    """One policy, two deliverables: while A's overseer agent is still working, B's formal path is decided at once
    (FORMALLY CHECKED, no translation time spent waiting); A is decided when its agent replies."""
    gate, entered = threading.Event(), threading.Event()

    def slow(d):
        entered.set()
        gate.wait(30)
        return silent(d)
    policy, agents = with_agents(clock, pack, reply=slow)
    a = run_task(policy, [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock, reviewer=False), decide=False)
    b = run_task(policy, [(AGENT, physics_report(AGENT, "rep-b"))], verify=Verifier(clock), decide=False)
    out: dict = {}
    try:
        ta = threading.Thread(target=lambda: out.setdefault("a", a.session.decide(request_message_ids=a.mids, receipts=a.receipts)))
        ta.start()
        assert entered.wait(30)  # A's overseer stage is under way
        tb = threading.Thread(target=lambda: out.setdefault("b", b.session.decide(request_message_ids=b.mids, receipts=b.receipts)))
        tb.start()
        tb.join(30)
        assert not tb.is_alive() and "a" not in out, "B waited for A's overseer stage"
        assert out["b"].mode == "formally_checked" and out["b"].receipt.translation_s == 0.0
        gate.set()
        ta.join(30)
        assert out["a"].mode == "overseer_selected" and agents.calls == ["overseer-pool-1"]
    finally:
        gate.set()
        a.close()
        b.close()


def test_the_deadline_verifier_calls_the_inner_verifier_as_the_channel_would(clock):
    stage = TranslationStage(clock, 240.0)
    seen = []

    def two_args(claim, report):
        seen.append(("two", claim.claim_id))
        return None

    def with_task(claim, report, task=None):
        seen.append(("task", task))
        return None

    rep = physics_report(AGENT, "rep-a")
    DeadlineVerifier(two_args, stage)(rep.claims[1], rep, task="the task")
    DeadlineVerifier(with_task, stage)(rep.claims[1], rep, task="the task")
    assert seen == [("two", "p1.1"), ("task", "the task")]
    assert [t.state for t in stage.timings] == ["no_outcome", "no_outcome"]
    clock.advance(240)
    assert DeadlineVerifier(two_args, stage)(rep.claims[1], rep) is None and len(seen) == 2 and stage.timings[-1].state == "skipped_budget"


def test_the_policys_own_failure_is_withheld_never_delivered(clock, monkeypatch):
    run = run_task(DeliveryPolicy(clock=clock), [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock), decide=False)
    try:
        def boom(*a, **k):
            raise RuntimeError("the policy broke")
        monkeypatch.setattr(DeliveryPolicy, "_formal", boom)
        d = run.session.decide(request_message_ids=run.mids, receipts=run.receipts)
        assert d.mode == "withheld" and not d.delivered and "failed internally (RuntimeError)" in d.receipt.reasons[0]
        assert "the delivery policy failed internally" in d.label and verify_delivery_receipt(d.receipt, run.keyring)
        assert_honest(d)
    finally:
        run.close()


def test_no_input_with_an_answer_is_withheld(clock):
    run = run_task(DeliveryPolicy(clock=clock), [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock), decide=False)
    try:
        d = run.session.decide(request_message_ids=["no-such-message"], receipts=run.receipts)
        assert d.mode == "withheld" and "no input with an answer" in d.label and d.receipt.formal.reasons[0].startswith("no deliverable:")
        assert_honest(d)
    finally:
        run.close()


def test_the_delivered_payload_is_the_journaled_report(clock):
    run = run_task(DeliveryPolicy(clock=clock), [(AGENT, physics_report(AGENT, "rep-a"))], verify=Verifier(clock))
    try:
        d = run.decision
        delivered = SpecialistReport.model_validate(d.answer.payload)
        assert delivered == physics_report(AGENT, "rep-a") and payload_hash(d.answer.payload) == run.messages[d.message_id].payload_sha256
    finally:
        run.close()
