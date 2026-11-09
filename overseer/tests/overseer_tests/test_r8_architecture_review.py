"""The overseer's fixes from the architecture review after arena round 8 (the twofold review and its validation).

- ``synthesis_ledger_fault`` is refuted only for what its checks decide (``validate._synthesis_ledger_gap``). A claim the
  synthesis adds while citing an unrelated source (rule ``ledger-content``: the ledger reads accounting, the certainty
  field, figures, quotations, names and comparison directions, never added content) and a fault the synthesis receipt
  already names (rule ``receipt-named``: OVS-SYN-002 names only what a receipt lacks) are unresolved (human review),
  never recorded against the agent; on two- and three-subject combined answers; a true accusation of a verbatim carry is
  still refuted when nothing is wrong, and confirmed through OVS-SYN-002 when the receipt lacks the fault;
- a blind merged review's temporary context never carries a fault only a signature, replay or custody check decides
  (``twofold.BLIND_HIDDEN_KINDS``), and the review passes its mode to the context;
- a source part on which no verdict was assessed is noted NOT reviewed in the signed audit, with what each instance did;
- the recorded decision on escalation: a dropped hedge the translator names only at warning level (INT-LEDGER-026) is no
  risk signal, so the merged review is not escalated for it; inflated certainty (INT-LEDGER-003, an error) is.

Agents never gate clearance in any of these: the clearances are the same before and after every review.
"""
from __future__ import annotations

import socket
from types import SimpleNamespace as NS

import pytest

from epinoic_logic.api.integrity import AgentRole
from epinoic_logic.api.integrity import LedgerEntry, SynthesizedClaim
from epinoic_overseer import OverseerPool, PoolConfig, load_pack
from epinoic_overseer import floor as floor_mod
from epinoic_overseer.export import export_pack
from epinoic_overseer.twofold import BLIND_HIDDEN_KINDS, CombinedLayout, SourcePart, TemporaryContext, pool_item
from epinoic_overseer.verdicts import KIND_CHECKS

from .conftest import DOC, EN_CLAIMS, EN_INPUT, HI_INPUT, default_synthesis, english_report, make_plan, point_problem, problems_fn
from .test_hook_hub import audited_hub
from .test_hook_review import Scripted, verdict
from .test_protocol_validate import acc, ptr

PLAIN_HI = ("The Factory Act of 1833 banned the employment of children under nine in textile mills. "
            "The Ten Hours Act of 1847 followed the Factory Act of 1833. "
            "On balance, the Act mattered most because it established inspection.")
HEDGED_HI = ("The Factory Act of 1833 banned the employment of children under nine in textile mills. "
             "The Ten Hours Act of 1847 followed the Factory Act of 1833. "
             "On balance, the Act probably mattered most because it may have established inspection.")
EC_INPUT = "Explain one economic effect of the Factory Act of 1833 on mill owners. Write no more than 80 words."
EC_TEXT = "Shorter hours for children raised the mill owners' labour costs."

S1 = SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried")
S2 = SynthesizedClaim(claim_id="s2", text="The Factory Act of 1833 banned the employment of children under nine in textile mills.", source_claim_ids=["h1.1"],
                      transformation="carried")
S3 = SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"], transformation="carried")
S4_EC = SynthesizedClaim(claim_id="s4", text=EC_TEXT, source_claim_ids=["g1.1@economics-specialist"], transformation="carried")
#: The review's case: a claim no source states, citing a source claim it has nothing to do with (h1.2 is about the Ten
#: Hours Act following the Factory Act), as a paraphrase.
ADDED_CITED = SynthesizedClaim(claim_id="s9", text="The Act also ended child labour in coal mines.", source_claim_ids=["h1.2"], transformation="paraphrased")
LEDGER_NO_H12 = [LedgerEntry(source_claim_ids=["en-ev1", "en-ev2", "en-an"], transformation="dropped", reason="supporting evidence summarised by the carried point")]
#: The hedged source h1.3 ('possible') carried word for word but with the certainty field 'established': INT-LEDGER-003.
S3_VERBATIM_INFLATED = SynthesizedClaim(claim_id="s3", text="On balance, the Act probably mattered most because it may have established inspection.",
                                        source_claim_ids=["h1.3"], transformation="carried")
#: The hedge dropped in words and the certainty field inflated: INT-LEDGER-003, INT-LEDGER-026 and INT-SYNTH-012.
S3_QUALIFIER_DROPPED = SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"],
                                        transformation="paraphrased")
#: The hedge dropped in words only, the certainty field kept at the source's: INT-LEDGER-026 and INT-SYNTH-012, warnings.
S3_HEDGE_DROPPED_TEXT_ONLY = SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.",
                                              source_claim_ids=["h1.3"], transformation="paraphrased", certainty="possible")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover - only hit if a test leaks a connection
        raise AssertionError("network access attempted in a unit test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    """Every instance is built from the installed pack exported with the exporter and loaded back from the zip."""
    return load_pack(export_pack(tmp_path_factory.mktemp("export"), zip_archive=True).zip_path)


def _combined(hi_text: str, claims, ledger=None, *, three: bool = False):
    """A hub with one combined answer of the English and History specialists' delivered answers (and the Economics
    specialist's with ``three``), joined by a synthesis of ``claims``."""
    plan = make_plan() if not three else make_plan(
        selected_agent_ids=["english-specialist", "history-specialist", "economics-specialist", "combinator"],
        agent_subjects={"history-specialist": "History", "economics-specialist": "Economics"},
        agent_task_types={"history-specialist": "short_answer", "economics-specialist": "short_answer"})
    hub = audited_hub()
    ch = hub.open_task(plan)
    ch.verify_claim_fn = problems_fn({"en-point": point_problem()})
    m, _r, _rq = hub.dispatch(plan.task_id, "english-specialist", EN_INPUT, [DOC])
    hub.receive(plan.task_id, m.message_id, english_report(claims=[dict(c) for c in EN_CLAIMS]))
    ch.verify_claim_fn = problems_fn({})
    m2, _r2, _rq2 = hub.dispatch(plan.task_id, "history-specialist", HI_INPUT, [])
    hub.receive(plan.task_id, m2.message_id, hi_text, agent_id="history-specialist", report_id="rep-hi-1")
    reports = ("rep-en-1", "rep-hi-1")
    if three:
        m3, _r3, _rq3 = hub.dispatch(plan.task_id, "economics-specialist", EC_INPUT, [])
        hub.receive(plan.task_id, m3.message_id, EC_TEXT, agent_id="economics-specialist", report_id="rep-ec-1")
        reports = ("rep-en-1", "rep-hi-1", "rep-ec-1")
    ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, default_synthesis(claims=claims, ledger=ledger, source_report_ids=reports))
    return hub, plan, ch


def _merged_accuses(target: str, kind: str = "synthesis_ledger_fault"):
    """Scripted instances (test code reading the dossier as data, never a model): every merged review accuses the
    synthesized claim ``target`` (I101: a claim no source states, or one more certain than its weakest source, is
    ``synthesis_ledger_fault`` by K5); the source reviews accuse nothing."""
    def reply(d: dict) -> dict:
        if (d.get("review") or {}).get("role") == "merged":
            syn = next(t for t in d["transfers"] if t["kind"] == "relay_synthesis")
            return verdict(d, [acc("m1", kind, [{"pointer": ptr(d, "synthesized_claim", target) + "/text"}],
                                   message_ids=[syn["message_id"]], receipt_ids=[syn["receipt_id"]], claim_ids=[target])])
        return verdict(d)
    return reply


def _review(hub, plan, ch, pack, reply, *, mode: str = "informed", auditor_finds: bool = False):
    """Review the task through the pool. No agent's verdict changes a clearance; only the auditor's own batch audit does
    (``auditor_finds``: each changed transfer is named by a deterministic ``OVS-*`` finding of the latest signed task
    audit, never by an ``OVS-AGENT-*`` one)."""
    before = {r.message_id: hub.clearance(plan.task_id, r.message_id).state for r in ch.receipts}
    pool = OverseerPool(pack, lambda agent_id: Scripted(reply), config=PoolConfig(max_instances=6, mode=mode))
    pr = hub.review_pool([plan.task_id], pool)
    rv = pr.reviews[ch.channel_uid]
    after = {r.message_id: hub.clearance(plan.task_id, r.message_id).state for r in ch.receipts}
    if not auditor_finds:
        assert before == after, "an agent's verdict never changes a clearance"
    else:
        changed = {m for m in after if after[m] != before[m]}
        latest = [a for a in hub.auditor.audits(ch.channel_uid) if a.scope == "task"][-1]
        assert changed and all(any(m in f.message_ids and not f.code.startswith("OVS-AGENT-") for f in latest.report.findings) for m in changed)
        assert not any(f.code.startswith("OVS-AGENT-") for f in latest.report.findings)
    return pr, rv


def _merged(rv) -> list:
    return [x for a in rv.twofold.merged.assessments for x in a.accusations]


# ============================================================================================ synthesis_ledger_fault
@pytest.mark.parametrize("three", [False, True], ids=["two-subjects", "three-subjects"])
def test_a_claim_the_synthesis_adds_citing_an_unrelated_source_is_never_refuted(three, pack):
    """The review's probe: the merged review rightly accuses s9 (added, citing h1.2) of ``synthesis_ledger_fault``. The
    receipt carries only warnings (INT-LEDGER-024, INT-SYNTH-012), so neither OVS-SYN-001 nor OVS-SYN-002 can decide
    added content; before the fix the accusation was refuted (OVS-AGENT-001, recorded against the agent) by checks that do
    not decide it. Now it is unresolved: human review."""
    claims = [S1, S2, S3, ADDED_CITED] + ([S4_EC] if three else [])
    hub, plan, ch = _combined(PLAIN_HI, claims, LEDGER_NO_H12, three=three)
    try:
        receipt = {f.code for f in ch.receipts[-1].findings}
        assert receipt <= {"INT-LEDGER-024", "INT-SYNTH-012"} and not any(f.severity == "error" for f in ch.receipts[-1].findings), receipt
        _pr, rv = _review(hub, plan, ch, pack, _merged_accuses("s9"))
        merged = _merged(rv)
        assert merged and {(x.kind, x.outcome, x.code) for x in merged} == {("synthesis_ledger_fault", "unresolved", "OVS-AGENT-004")}
        assert all(x.refuted_by is None and "rule ledger-content" in x.reasons[0] and "s9 ('paraphrased'" in x.reasons[0] for x in merged)
        codes = {f.code for f in rv.audit.report.findings}
        assert "OVS-AGENT-001" not in codes and "OVS-AGENT-004" in codes, codes
        assert rv.combined is not None and rv.combined.review_queue, "an unresolved accusation always reaches human review"
    finally:
        hub.close()


def test_an_accusation_of_a_verbatim_carry_with_nothing_wrong_is_still_refuted(pack):
    """The control: s2 carries h1.1 word for word and nothing is wrong, so the checks of the kind decide it and the
    accusation is refuted, as before."""
    hub, plan, ch = _combined(PLAIN_HI, [S1, S2, S3])
    try:
        assert not ch.receipts[-1].findings
        _pr, rv = _review(hub, plan, ch, pack, _merged_accuses("s2"))
        merged = _merged(rv)
        assert merged and {(x.kind, x.outcome, x.refuted_by) for x in merged} == {("synthesis_ledger_fault", "refuted", "deterministic_check")}
    finally:
        hub.close()


@pytest.mark.parametrize("claim, rules", [
    (S3_VERBATIM_INFLATED, ("rule receipt-named",)),                           # content decided: only the receipt's own finding
    (S3_QUALIFIER_DROPPED, ("rule ledger-content", "rule receipt-named")),     # the review's qualifier_dropped case
], ids=["verbatim-certainty-inflated", "qualifier-dropped"])
def test_an_accusation_of_a_fault_the_synthesis_receipt_names_is_not_refuted(claim, rules, pack):
    """K9 sends a merged reviewer to a certainty the synthesis changed whatever the receipt says; OVS-SYN-002 names only a
    ledger fault the receipt LACKS, so before the fix the true accusation was refuted (OVS-AGENT-001) because the receipt
    already named it (INT-LEDGER-003). Now it agrees with the channel's own finding and is unresolved, never refuted."""
    hub, plan, ch = _combined(HEDGED_HI, [S1, S2, claim])
    try:
        assert ("INT-LEDGER-003", "error") in {(f.code, f.severity) for f in ch.receipts[-1].findings}
        _pr, rv = _review(hub, plan, ch, pack, _merged_accuses("s3"))
        merged = _merged(rv)
        assert merged and {(x.kind, x.outcome) for x in merged} == {("synthesis_ledger_fault", "unresolved")}
        for x in merged:
            assert all(r in x.reasons[0] for r in rules) and "INT-LEDGER-003 (error) on s3" in x.reasons[0], x.reasons
        assert "OVS-AGENT-001" not in {f.code for f in rv.audit.report.findings}
    finally:
        hub.close()


def test_a_fault_the_receipt_lacks_is_still_confirmed_through_syn_002(pack, monkeypatch):
    """The control of rule receipt-named: the same inflated certainty with the channel's ledger silenced, so the receipt
    lacks INT-LEDGER-003; the auditor's own ledger re-check finds it (OVS-SYN-002, which fails the synthesis transfer in
    the batch audit) and confirms the accusation through that finding."""
    import epinoic_logic.channel.bus as bus
    monkeypatch.setattr(bus, "check_synthesis_ledger", lambda *a, **k: [])
    hub, plan, ch = _combined(HEDGED_HI, [S1, S2, S3_VERBATIM_INFLATED])
    try:
        assert "INT-LEDGER-003" not in {f.code for f in ch.receipts[-1].findings}
        _pr, rv = _review(hub, plan, ch, pack, _merged_accuses("s3"), auditor_finds=True)
        merged = _merged(rv)
        assert merged and {(x.kind, x.outcome) for x in merged} == {("synthesis_ledger_fault", "confirmed")}
        assert all({c.code for c in x.confirming} == {"OVS-SYN-002"} for x in merged)
    finally:
        hub.close()


# ============================================================================================ the blind context
def _layout() -> CombinedLayout:
    return CombinedLayout(channel_uid="ch", task_id="t", request_id="r",
                          sources=(SourcePart(1, "history-specialist", ("rep-hi-1",), ("m1",), (1, 2), (1, 2)),
                                   SourcePart(2, "english-specialist", ("rep-en-1",), ("m2",), (3, 4), (3, 4))),
                          synthesis_ids=("syn-1",), synthesis_message_ids=("m5",), merged_own=(5,), merged_seqs=(1, 2, 3, 4, 5))


def _confirmed(kind: str, claim: str, code: str, result_ids=()) -> NS:
    ref = NS(code=code, claim_ids=[claim], report_ids=["rep-hi-1"])
    return NS(outcome="confirmed", kind=kind, covered_identifiers={"claim_ids": [claim], "report_ids": ["rep-hi-1"], "result_ids": list(result_ids),
                                                                     "message_ids": ["m1"]},
              identifiers={}, confirming=[ref], claim_report_ids={claim: ["rep-hi-1"]})


def test_a_blind_merged_review_is_never_told_a_signature_replay_or_custody_outcome():
    """The review's probe: the context of a blind review listed {kind: result_unsigned_or_forged, result_ids: [res-42]},
    which only a signature check (OVS-RES-003, OVS-RES-009) confirms and a blind dossier never shows. In blind mode the
    context leaves out every kind only a signature, replay or custody check decides; informed mode keeps them; a content
    fault (quotation_absent) is in both, since the merged review exists to see whether the synthesis carries it."""
    assessed = {1: [NS(valid=True, accusations=[_confirmed("result_unsigned_or_forged", "h1.1", "OVS-RES-003", ["res-42"]),
                                                 _confirmed("quotation_absent", "h1.2", "OVS-FID-002")])], 2: []}
    blind = TemporaryContext.build(_layout(), assessed, mode="blind")
    informed = TemporaryContext.build(_layout(), assessed, mode="informed")
    assert [f["kind"] for f in blind.record["sources"][0]["confirmed"]] == ["quotation_absent"]
    assert "res-42" not in str(blind.record) and set(blind.faulted()) == {("rep-hi-1", "h1.2")}, "nothing hidden decides anything either"
    assert sorted(f["kind"] for f in informed.record["sources"][0]["confirmed"]) == ["quotation_absent", "result_unsigned_or_forged"]
    assert blind.record["complete"] is True and blind.verifies() and blind.digest != informed.digest
    assert TemporaryContext.build(_layout(), assessed).digest == informed.digest, "the default is the informed context it always was"
    with pytest.raises(ValueError):
        TemporaryContext.build(_layout(), assessed, mode="half")
    for kind in sorted(BLIND_HIDDEN_KINDS):  # each is decided only by signature, replay or custody checks
        assert KIND_CHECKS[kind] and all(c.startswith(("OVS-RES-", "OVS-CUST-", "OVS-RCPT-", "OVS-TRN-007")) for c in KIND_CHECKS[kind]), kind
    assert {"quotation_absent", "figure_changed", "claim_not_in_response", "synthesis_carries_fault"}.isdisjoint(BLIND_HIDDEN_KINDS)


def test_the_twofold_review_builds_the_context_in_its_own_mode(pack, monkeypatch):
    """The hub's N_FOLD review hands its mode to the context: a blind pool builds a blind context."""
    seen: list[str] = []
    real = TemporaryContext.build.__func__

    def spy(cls, layout, assessments, **kw):
        seen.append(kw.get("mode", "<default>"))
        return real(cls, layout, assessments, **kw)
    monkeypatch.setattr(TemporaryContext, "build", classmethod(spy))
    for mode in ("blind", "informed"):
        hub, plan, ch = _combined(PLAIN_HI, [S1, S2, S3])
        try:
            _review(hub, plan, ch, pack, lambda d: verdict(d), mode=mode)
        finally:
            hub.close()
    assert seen == ["blind", "informed"]


# ============================================================================================ an unreviewed source part
@pytest.mark.parametrize("failure", ["raise", "junk"])
def test_a_source_part_no_verdict_was_assessed_on_is_noted_not_reviewed(failure, pack):
    """The review's probe: every instance of both source reviews failed (a provider error) or answered something that is
    not a verdict, yet the signed audit noted each source 'reviewed before combination, in parallel'. A non-success is
    never worded as a success: the note says NOT reviewed, with what each instance did."""
    def reply(d: dict):
        if (d.get("review") or {}).get("role") == "source":
            if failure == "raise":
                raise RuntimeError("provider down")
            return {"not": "a verdict"}
        return verdict(d)
    hub, plan, ch = _combined(PLAIN_HI, [S1, S2, S3])
    try:
        _pr, rv = _review(hub, plan, ch, pack, reply)
        notes = rv.audit.coverage.notes
        status = "provider_error" if failure == "raise" else "invalid"
        for k, agent in ((1, "english-specialist"), (2, "history-specialist")):
            [note] = [n for n in notes if n.startswith(f"source {k} of 2 ({agent}")]
            assert "NOT reviewed before combination: no verdict was assessed on it" in note and f": {status}" in note, note
            assert "reviewed before combination, in parallel" not in note
        [ctx_note] = [n for n in notes if n.startswith("temporary context sha256")]
        assert "source(s) 1, 2 NOT reviewed (reviewed 0" in ctx_note
        assert [s["reviewed"] for s in rv.twofold.context_record["sources"]] == [0, 0]
    finally:
        hub.close()


def test_a_reviewed_source_part_keeps_its_note(pack):
    """The control: a source part with an assessed verdict is noted reviewed, as before."""
    hub, plan, ch = _combined(PLAIN_HI, [S1, S2, S3])
    try:
        _pr, rv = _review(hub, plan, ch, pack, lambda d: verdict(d))
        notes = [n for n in rv.audit.coverage.notes if n.startswith("source ")]
        assert len(notes) == 2 and all("reviewed before combination, in parallel, by" in n and "NOT reviewed" not in n for n in notes)
        assert not any("NOT reviewed" in n for n in rv.audit.coverage.notes)
    finally:
        hub.close()


# ============================================================================================ escalation: the recorded decision
@pytest.mark.parametrize("claim, signals, merged_instances", [
    (S3_HEDGE_DROPPED_TEXT_ONLY, (), 1),            # INT-LEDGER-026 and INT-SYNTH-012, warnings only: no risk signal
    (S3_QUALIFIER_DROPPED, ("integrity_error",), 2),  # INT-LEDGER-003, an error: escalated to two instances
], ids=["hedge-dropped-in-words-only", "certainty-inflated"])
def test_a_hedge_named_only_at_warning_level_does_not_escalate_the_merged_review(claim, signals, merged_instances, pack):
    """The decision recorded after arena round 8's architecture review (floor rule 2, the README, design section 52): risk
    signals stay what blocks release or names a fault at error level, the named families, contradictions and rejections.
    A hedge the translator names as dropped only by its lexical reading (INT-LEDGER-026, a warning) is on the receipt the
    merged review reads, but it does not escalate; the same claim with its certainty field inflated (INT-LEDGER-003, an
    error) does."""
    hub, plan, ch = _combined(HEDGED_HI, [S1, S2, claim])
    try:
        codes = {(f.code, f.severity) for f in ch.receipts[-1].findings}
        assert ("INT-LEDGER-026", "warning") in codes and ("INT-SYNTH-012", "warning") in codes
        assert (("INT-LEDGER-003", "error") in codes) is bool(signals)
        view = hub.auditor.view(ch.channel_uid)
        item, layout = pool_item(view, ch.channel_uid, 0, {})
        assert layout is not None and tuple(item.merged.risk_signals) == signals
        plan_ = OverseerPool(pack, lambda a: Scripted(lambda d: verdict(d)), config=PoolConfig(max_instances=6)).plan([item])
        assert len(plan_.twofold[ch.channel_uid].merged) == merged_instances
    finally:
        hub.close()
    assert "INT-LEDGER-026" in (floor_mod.__doc__ or ""), "the floor's rules state the decision"
