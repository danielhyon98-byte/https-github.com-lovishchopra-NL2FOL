"""The twofold (N_FOLD) review of a combined answer (architecture step 3; design section 52; ``twofold.py``).

A synthesis that combines N >= 2 specialists' delivered answers is reviewed in N + 1 parts: one dossier per specialist's
own transfers, before combination, reviewed in parallel; then the merged review of the combinator's output with the
bounded, request-scoped temporary context of what validation accepted from the source reviews, discarded afterwards.

- the layout is read from the journal: the sources in delivery order, each part's own transfers and every transfer they
  depend on; the part views are copies, and the full view is never touched;
- on a two-subject combined answer (English and History): a fault in one source that the synthesis keeps is confirmed
  (``synthesis_carries_fault``, through the source fault's own confirming finding), one it drops is refuted, one it adds
  is named by the synthesis receipt and escalates the merged review (an accusation of it as carried is unresolved), and a
  faithful control gives nothing; no review changes a clearance;
- a fault of a report its specialist then revised under the same claim ids is never confirmed through a citation the
  synthesis's ledger scope resolves to the revision, or to two reports (unresolved: human review), whether the source
  accusation named the report or the claim alone (its fault is pinned to the one report its confirming finding names);
- the temporary context holds only structured records of validated outcomes, never agent text or finding codes; it is
  bounded (cut from the end and counted), scoped to its channel, task and request (the intake refuses it anywhere else),
  recorded in the signed audit and discarded after the request, also when the merged review fails;
- three specialists give three source reviews; the waves never give one agent two open issues of one task;
- the plan: the floor reviews a combined answer N_FOLD; the flash router plans it N_FOLD and the overseer admits it; a
  router that bounds the context below the floor's 65,536 bytes is refused (KIT-RT-020), and a pool port 1.1 router is
  refused for a batch with a combined answer (KIT-RT-015); the floor plan runs in both;
- a part dossier is never issued under a pack that does not teach the N_FOLD review (1.x);
- deterministic: the same journal gives the same layout, plan and context.
"""
from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path

import pytest

from epinoic_logic.api.integrity import LedgerEntry, SynthesizedClaim
from epinoic_logic.api.integrity import AgentRole
from epinoic_logic.api.ir import SourceRef
from epinoic_overseer import OverseerPool, PoolConfig, load_pack, verify_audit
from epinoic_overseer.export import export_pack
from epinoic_overseer.floor import CONTEXT_MAX_BYTES, below_floor
from epinoic_overseer.intake import IntakeRefused
from epinoic_overseer.pack import PACK_DIGESTS, installed_pack_dir
from epinoic_overseer.twofold import (
    CONTEXT_FORMAT, TemporaryContext, _waves, combined_layout, part_view, pool_item, review_scope, run_twofold, teaches_n_fold,
)
from epinoic_overseer.verdicts import PackIdentity

from .conftest import DOC, EN_CLAIMS, EN_INPUT, HI_INPUT, HI_TEXT, default_synthesis, english_report, int_problem, make_plan, point_problem, problems_fn
from .flash_router_support import attach, attach_in_process, flash_router_src
from .test_hook_hub import audited_hub
from .test_hook_review import Scripted, verdict
from .test_protocol_validate import acc, ptr

#: A claim the English specialist did not write in its response (the extract states it; the response does not): its
#: source review's quotation_absent is confirmed by OVS-FID-002.
INSERTED = dict(claim_id="en-ev2", claim_text="the town grew rich on their silence", claim_role="evidence", materiality="supporting",
                source_refs=[SourceRef(document_id="doc-mill", excerpt="the town grew rich on their silence")])
EC_INPUT = "Explain one economic effect of the Factory Act of 1833 on mill owners. Write no more than 80 words."
EC_TEXT = "Shorter hours for children raised the mill owners' labour costs."
CASES = ("keeps", "drops", "adds", "faithful")


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


# ----------------------------------------------------------------------------------------------- the combined answers
def _synthesis(case: str, *, three: bool = False, reports: tuple[str, ...] = ("rep-en-1", "rep-hi-1")):
    if case == "keeps":
        claims = [SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried"),
                  SynthesizedClaim(claim_id="s2", text="The Factory Act of 1833 banned the employment of children under nine in textile mills.",
                                   source_claim_ids=["h1.1"], transformation="carried"),
                  SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"],
                                   transformation="carried"),
                  SynthesizedClaim(claim_id="s4", text="the town grew rich on their silence", source_claim_ids=["en-ev2"], transformation="carried")]
        ledger = [LedgerEntry(source_claim_ids=["en-ev1", "en-an"], transformation="dropped", reason="supporting evidence summarised by the carried point"),
                  LedgerEntry(source_claim_ids=["h1.2"], transformation="dropped", reason="supporting detail beyond the synthesis's scope")]
        return default_synthesis(claims=claims, ledger=ledger, source_report_ids=reports)
    if case == "adds":  # "under ten" where the History source says "under nine": a figure no source states
        claims = [SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried"),
                  SynthesizedClaim(claim_id="s2", text="The Factory Act of 1833 banned the employment of children under ten in textile mills.",
                                   source_claim_ids=["h1.1"], transformation="carried"),
                  SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"],
                                   transformation="carried")]
        return default_synthesis(claims=claims)
    if three:
        claims = [SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried"),
                  SynthesizedClaim(claim_id="s2", text="The Factory Act of 1833 banned the employment of children under nine in textile mills.",
                                   source_claim_ids=["h1.1"], transformation="carried"),
                  SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"],
                                   transformation="carried"),
                  SynthesizedClaim(claim_id="s4", text=EC_TEXT, source_claim_ids=["g1.1@economics-specialist"], transformation="carried")]
        return default_synthesis(claims=claims, source_report_ids=("rep-en-1", "rep-hi-1", "rep-ec-1"))
    return default_synthesis()


def _combined(case: str = "faithful", *, three: bool = False):
    """A hub with one combined answer: the English and the History specialists' delivered answers (and the Economics
    specialist's with ``three``), joined by the combinator. ``keeps`` and ``drops`` deliver an English claim its response
    does not carry (en-ev2), which the synthesis carries (keeps) or drops (drops); ``adds`` gives the synthesis a figure
    no source states."""
    plan = make_plan() if not three else make_plan(
        selected_agent_ids=["english-specialist", "history-specialist", "economics-specialist", "combinator"],
        agent_subjects={"history-specialist": "History", "economics-specialist": "Economics"},
        agent_task_types={"history-specialist": "short_answer", "economics-specialist": "short_answer"})
    hub = audited_hub()
    ch = hub.open_task(plan)
    ch.verify_claim_fn = problems_fn({"en-point": point_problem()})
    m, _r, _rq = hub.dispatch(plan.task_id, "english-specialist", EN_INPUT, [DOC])
    claims = [INSERTED if (case in ("keeps", "drops") and c["claim_id"] == "en-ev2") else dict(c) for c in EN_CLAIMS]
    hub.receive(plan.task_id, m.message_id, english_report(claims=claims))
    ch.verify_claim_fn = problems_fn({"h1.1": int_problem("h1.1", "min_age", 9, op="ge", bound=9)})
    m2, _r2, _rq2 = hub.dispatch(plan.task_id, "history-specialist", HI_INPUT, [])
    hub.receive(plan.task_id, m2.message_id, HI_TEXT, agent_id="history-specialist", report_id="rep-hi-1")
    if three:
        ch.verify_claim_fn = problems_fn({})
        m3, _r3, _rq3 = hub.dispatch(plan.task_id, "economics-specialist", EC_INPUT, [])
        hub.receive(plan.task_id, m3.message_id, EC_TEXT, agent_id="economics-specialist", report_id="rep-ec-1")
    ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis(case, three=three))
    return hub, plan, ch


def _revised(cites: str):
    """The English specialist revises its answer: rep-en-1 carries a claim its response does not (en-ev2, INSERTED: a
    source fault the source review confirms), then rep-en-2 the same claim ids with en-ev2's faithful text (a revision
    keeps its claims' ids: INT-HANDOFF-009); the History answer; a synthesis carrying en-ev2 (s4) that lists ``cites``."""
    plan = make_plan()
    hub = audited_hub()
    ch = hub.open_task(plan)
    ch.verify_claim_fn = problems_fn({"en-point": point_problem()})
    m, _r, _rq = hub.dispatch(plan.task_id, "english-specialist", EN_INPUT, [DOC])
    hub.receive(plan.task_id, m.message_id, english_report(claims=[INSERTED if c["claim_id"] == "en-ev2" else dict(c) for c in EN_CLAIMS]))
    m1, _r1, _rq1 = hub.dispatch(plan.task_id, "english-specialist", EN_INPUT, [DOC])
    hub.receive(plan.task_id, m1.message_id, english_report(claims=[dict(c) for c in EN_CLAIMS], report_id="rep-en-2", created_at="2026-10-11T11:05:00Z"))
    ch.verify_claim_fn = problems_fn({"h1.1": int_problem("h1.1", "min_age", 9, op="ge", bound=9)})
    m2, _r2, _rq2 = hub.dispatch(plan.task_id, "history-specialist", HI_INPUT, [])
    hub.receive(plan.task_id, m2.message_id, HI_TEXT, agent_id="history-specialist", report_id="rep-hi-1")
    ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis("keeps", reports=(cites, "rep-hi-1")))
    return hub, plan, ch


def _replies(case: str, *, merged_report: str = "rep-en-1", seen: list | None = None, bare: bool = False):
    """The scripted instances (test code reading the dossier as data, never a model): source 1's review accuses the
    inserted claim in ``keeps`` and ``drops`` (``bare``: naming the claim and its document only, no report or message);
    the merged review accuses a synthesized claim of carrying a source fault (s4 citing en-ev2 in ``keeps``, s1 in
    ``drops``, s2 citing h1.1 in ``adds``)."""
    def reply(d: dict) -> dict:
        r = d.get("review") or {}
        if seen is not None:
            seen.append((d["agent_id"], json.dumps(r, sort_keys=True), "temporary_context" in d))
        if r.get("role") == "source" and r.get("source") == 1 and case in ("keeps", "drops"):
            t = next(t for t in d["transfers"] if t["kind"] == "response")
            return verdict(d, [acc("a1", "quotation_absent", [{"pointer": ptr(d, "claim", "en-ev2") + "/claim_text", "quote": "the town grew rich on their silence"},
                                                               {"pointer": t["at"] + "/payload/original_response"}],
                                   message_ids=[] if bare else [t["message_id"]], claim_ids=["en-ev2"], report_ids=[] if bare else ["rep-en-1"],
                                   document_ids=["doc-mill"])])
        if r.get("role") == "merged":
            syn = next(t for t in d["transfers"] if t["kind"] == "relay_synthesis")
            target = {"keeps": ["s4", "en-ev2"], "drops": ["s1", "en-ev2"], "adds": ["s2", "h1.1"]}.get(case)
            if target:
                src = "rep-hi-1" if case == "adds" else merged_report
                return verdict(d, [acc("m1", "synthesis_carries_fault",
                                       [{"pointer": ptr(d, "synthesized_claim", target[0]) + "/source_claim_ids"},
                                        {"pointer": "/temporary_context/sources/0/confirmed"}],
                                       message_ids=[syn["message_id"]], receipt_ids=[syn["receipt_id"]], claim_ids=target, report_ids=[src])])
        return verdict(d)
    return reply


def _review(case: str, pack, *, router=None, three: bool = False, max_instances: int = 4, merged_report: str = "rep-en-1", seen=None):
    hub, plan, ch = _combined(case, three=three)
    states_before = {r.message_id: hub.clearance(plan.task_id, r.message_id).state for r in ch.receipts}
    pool = OverseerPool(pack, lambda agent_id: Scripted(_replies(case, merged_report=merged_report, seen=seen)),
                        config=PoolConfig(max_instances=max_instances), router=router)
    pr = hub.review_pool([plan.task_id], pool)
    states_after = {r.message_id: hub.clearance(plan.task_id, r.message_id).state for r in ch.receipts}
    return hub, plan, ch, pr, pr.reviews[ch.channel_uid], states_before, states_after


def _outcomes(part) -> list[tuple[str, str]]:
    return sorted((x.kind, x.outcome) for a in part.assessments for x in a.accusations)


# ----------------------------------------------------------------------------------------------- the layout
def test_the_layout_of_a_combined_answer_is_read_from_the_journal_and_every_part_link_resolves_inside_it():
    hub, plan, ch = _combined()
    try:
        view = hub.auditor.view(ch.channel_uid)
        lay = combined_layout(view)
        assert lay is not None and lay.n == 2 and (lay.task_id, lay.request_id) == (plan.task_id, plan.request_id)
        kinds = {t.seq: t.kind for t in view.transfers}
        (en, hi) = lay.sources
        assert (en.index, en.agent_id, en.report_ids, hi.index, hi.agent_id, hi.report_ids) == (
            1, "english-specialist", ("rep-en-1",), 2, "history-specialist", ("rep-hi-1",))
        assert [kinds[s] for s in en.own_seqs] == ["request", "response"] and [kinds[s] for s in hi.own_seqs] == ["request", "response_text"]
        assert [kinds[s] for s in lay.merged_own] == ["relay_synthesis"] and lay.synthesis_ids == ("syn-1",)
        # the merged part holds the synthesis and the deliveries it cites, with their requests: every source answer it cites
        assert set(lay.merged_seqs) == set(en.seqs) | set(hi.seqs) | set(lay.merged_own)
        for seqs in (en.seqs, hi.seqs, lay.merged_seqs):
            part = part_view(view, seqs)
            assert [t.seq for t in part.transfers] == sorted(seqs)
            assert all(dep in part.by_seq for t in part.transfers for dep in t.depends_on), "every link of a part resolves inside it"
        # the full view is untouched by the parts: its links are those it had
        assert view.by_seq[lay.merged_own[0]].cited_delivery_seqs and combined_layout(hub.auditor.view(ch.channel_uid)) == lay
        # a channel with one specialist's answer, or no synthesis, is no combined answer
        assert combined_layout(part_view(view, en.seqs)) is None
    finally:
        hub.close()


def test_the_pool_reads_each_part_with_its_own_risk_and_size():
    hub, plan, ch = _combined("adds")
    try:
        view = hub.auditor.view(ch.channel_uid)
        item, lay = pool_item(view, ch.channel_uid, 0, {})
        assert lay is not None and len(item.sources) == 2 and item.merged is not None and item.features.transfers == len(view.transfers)
        assert "integrity_error" in item.merged.risk_signals, "the synthesis receipt's INT-LEDGER-023 is the merged part's own risk"
        assert all(p.features.chars > 0 for p in (*item.sources, item.merged)) and item.merged.features.chars < item.features.chars + 1
    finally:
        hub.close()


# ----------------------------------------------------------------------------------------------- the four cases
@pytest.mark.parametrize("case", CASES)
def test_twofold_on_a_two_subject_combined_answer(case, pack):
    hub, plan, ch, pr, rv, before, after = _review(case, pack)
    try:
        tw = rv.twofold
        assert tw is not None and pr.plan.twofold[ch.channel_uid].context_max_bytes == CONTEXT_MAX_BYTES == 65536
        src1, src2 = tw.sources
        rec = tw.context_record
        assert rec["format"] == CONTEXT_FORMAT and rec["complete"] is True and rec["omitted"] == 0 and rec["bytes"] <= rec["max_bytes"] == 65536
        assert (rec["scope"]["task_id"], rec["scope"]["request_id"]) == (plan.task_id, plan.request_id) and tw.context_discarded
        merged = _outcomes(tw.merged)
        if case in ("keeps", "drops"):
            # the source fault is confirmed in source 1's review, and the context lists it as a structured record
            assert set(_outcomes(src1)) == {("quotation_absent", "confirmed")} and _outcomes(src2) == []
            [fault] = rec["sources"][0]["confirmed"]
            assert (fault["kind"], fault["claim_ids"], fault["report_ids"]) == ("quotation_absent", ["en-ev2"], ["rep-en-1"]) and rec["sources"][1]["confirmed"] == []
        else:
            assert _outcomes(src1) == _outcomes(src2) == [] and all(s["confirmed"] == [] for s in rec["sources"])
        if case == "keeps":
            assert merged == [("synthesis_carries_fault", "confirmed")]
            [a] = [x for v in tw.merged.assessments for x in v.accusations]
            assert a.checks == ["carried-fault"] and [c.code for c in a.confirming] == ["OVS-FID-002"]
            assert a.covered_identifiers["claim_ids"] == ["s4", "en-ev2"] and tw.carried[0]["claim_ids"] == ["s4", "en-ev2"]
        elif case == "drops":
            assert merged == [("synthesis_carries_fault", "refuted")] and tw.carried == ()
        elif case == "adds":
            assert "INT-LEDGER-023" in {f.code for f in ch.receipts[-1].findings}, "the synthesis receipt names the added figure"
            assert len(pr.plan.twofold[ch.channel_uid].merged) == 2, "the synthesis's own risk signal escalates the merged review"
            assert set(merged) == {("synthesis_carries_fault", "unresolved")} and tw.carried == ()
        else:
            assert merged == [] and len(pr.plan.twofold[ch.channel_uid].merged) == 1 and tw.carried == ()
        # agents never gate clearance, and the signed audit states the task audit's states
        assert before == after and verify_audit(rv.audit, hub.auditor.keyring)
        assert dict(rv.audit.transfer_states) == dict(rv.task_audit.transfer_states)
        notes = "\n".join(rv.audit.coverage.notes)
        assert f"N_FOLD review of a combined answer of 2 sources" in notes and f"temporary context sha256 {tw.context_sha256}" in notes
        assert "discarded after the request" in notes and "temporary context as issued to the merged review: {" in notes
        assert all(code.startswith("OVS-AGENT-") for code in {f.code for f in rv.audit.report.findings})
    finally:
        hub.close()


def test_the_carried_fault_names_the_source_report_or_the_synthesis_alike(pack):
    """Example 41 names the source's report; naming the synthesis instead decides the same."""
    hub, _plan, _ch, _pr, rv, _b, _a = _review("keeps", pack, merged_report="syn-1")
    try:
        assert _outcomes(rv.twofold.merged) == [("synthesis_carries_fault", "confirmed")]
    finally:
        hub.close()


@pytest.mark.parametrize("bare", [False, True], ids=["named-report", "bare-claim"])
@pytest.mark.parametrize("cites, holders", [("rep-en-2", ["rep-en-2"]), ("rep-en-1", ["rep-en-1", "rep-en-2"])])
def test_a_fault_of_a_report_its_specialist_revised_is_never_confirmed_through_the_same_claim_id(cites, holders, bare, pack):
    """A revision keeps its claims' ids, so a context record names the report whose claim the source review confirmed
    faulty (rep-en-1: the one report its confirming finding names, also when the source accusation names the claim
    alone), and rule carried-fault confirms only a citation the synthesis's ledger scope resolves to that report's claim.
    A synthesis listing the revision (rep-en-2) carries its faithful en-ev2; one listing the superseded report cites an id
    two reports of its scope hold (the ledger's collision). Neither is confirmed: human review. The control is the four
    cases' ``keeps`` (and its bare variant below): the same accusation, the citation resolved to rep-en-1, confirmed."""
    hub, plan, ch = _revised(cites)
    try:
        pool = OverseerPool(pack, lambda agent_id: Scripted(_replies("keeps", merged_report=cites, bare=bare)), config=PoolConfig(max_instances=4))
        before = {r.message_id: hub.clearance(plan.task_id, r.message_id).state for r in ch.receipts}
        rv = hub.review_pool([plan.task_id], pool).reviews[ch.channel_uid]
        tw = rv.twofold
        assert tw is not None and [p.report_ids for p in tw.layout.sources] == [(cites,), ("rep-hi-1",)]
        assert set(_outcomes(tw.sources[0])) == {("quotation_absent", "confirmed")}
        [fault] = tw.context_record["sources"][0]["confirmed"]
        assert (fault["kind"], fault["claim_ids"], fault["report_ids"]) == ("quotation_absent", ["en-ev2"], ["rep-en-1"])
        merged = [x for v in tw.merged.assessments for x in v.accusations]
        assert merged and {(x.kind, x.outcome) for x in merged} == {("synthesis_carries_fault", "unresolved")} and tw.carried == ()
        assert all(x.checks == ["carried-fault"] and f"that id is held by report(s) {holders}" in x.reasons[0] for x in merged)
        assert before == {r.message_id: hub.clearance(plan.task_id, r.message_id).state for r in ch.receipts}
    finally:
        hub.close()


def test_a_bare_source_accusation_is_pinned_to_the_report_its_confirming_finding_names(pack):
    """The control of the bare variant: one English report, the source accusation naming the claim alone. Its fault is
    pinned to the one report its confirming finding (OVS-FID-002) names, the record shows that report, and the carried
    fault is confirmed as in ``keeps``."""
    hub, plan, ch = _combined("keeps")
    try:
        pool = OverseerPool(pack, lambda agent_id: Scripted(_replies("keeps", bare=True)), config=PoolConfig(max_instances=4))
        tw = hub.review_pool([plan.task_id], pool).reviews[ch.channel_uid].twofold
        [fault] = tw.context_record["sources"][0]["confirmed"]
        assert (fault["claim_ids"], fault["report_ids"], fault["message_ids"]) == (["en-ev2"], ["rep-en-1"], [])
        assert _outcomes(tw.merged) == [("synthesis_carries_fault", "confirmed")] and tw.carried[0]["claim_ids"] == ["s4", "en-ev2"]
    finally:
        hub.close()


def test_a_confirmed_fault_is_pinned_to_one_report_or_to_none():
    """``twofold._pinned_reports``: of the reports carrying the claim in the source dossier, those the confirming findings
    name (all, when they name none), when exactly one remains; a finding about other claims says nothing of this one."""
    from types import SimpleNamespace as NS
    from epinoic_overseer.twofold import _pinned_reports

    def accn(crep, *refs):
        return NS(claim_report_ids=crep, confirming=[NS(claim_ids=list(c), report_ids=list(r)) for c, r in refs])

    assert _pinned_reports(accn({"c": ["r1", "r2"]}, (["c"], ["r1"])), ["c"]) == {"c": "r1"}
    assert _pinned_reports(accn({"c": ["r1", "r2"]}, (["c"], [])), ["c"]) == {}, "two reports carry it and no finding says which"
    assert _pinned_reports(accn({"c": ["r1"]}, (["c"], [])), ["c"]) == {"c": "r1"}
    assert _pinned_reports(accn({"c": ["r1"]}, (["c"], ["r3"])), ["c"]) == {}, "the finding names another report than the claim's"
    assert _pinned_reports(accn({"c": ["r1", "r2"]}, (["d"], ["r2"]), ([], ["r1"])), ["c"]) == {"c": "r1"}
    assert _pinned_reports(accn({"c": ["r1", "r2"]}, (["c"], ["r1", "r2"])), ["c"]) == {}
    assert _pinned_reports(accn({}, (["c"], ["r1"])), ["c"]) == {}


def test_a_cited_id_resolves_within_the_synthesis_ledger_scope_and_nothing_resolves_past_a_digest_only_report():
    """``validate._synthesis_citations`` on journal-shaped transfers: the scope of a synthesis is every report it lists and
    each agent's latest report delivered before it; a report delivered after it is outside; a scope report journaled
    digest-only leaves every citation of that synthesis unresolved (``None``)."""
    from types import SimpleNamespace as NS
    from epinoic_overseer.validate import _synthesis_citations

    def rep(rid, agent, *claims, digest_only=False):
        report = None if digest_only else NS(agent_id=agent, claims=[NS(claim_id=c) for c in claims])
        return NS(kind="response", delivered=True, report_id=rid, report=report, sender_agent_id=agent, synthesis=None)

    def syn(sid, listed, cites):
        claims = [NS(claim_id=f"s{i}", source_claim_ids=list(c)) for i, c in enumerate(cites, start=1)]
        return NS(kind="relay_synthesis", delivered=True, report_id=None, report=None, sender_agent_id="combinator",
                  synthesis=NS(synthesis_id=sid, source_report_ids=list(listed), claims=claims))

    view = NS(transfers=[rep("ra", "a", "c1", "c2"), rep("rb", "b", "d1"), syn("syn-1", ["ra", "rb"], [["c1"], ["d1", "x9"]]),
                         rep("ra2", "a", "c1"), syn("syn-2", ["ra2", "rb"], [["c1"], ["c2"]]), syn("syn-3", ["ra", "rb"], [["c1"]]),
                         rep("ra3", "a", "c1")])
    out = _synthesis_citations(view)
    assert out[("syn-1", "s1")] == {"c1": {"ra"}} and out[("syn-1", "s2")] == {"d1": {"rb"}, "x9": frozenset()}
    # a revision: listing it resolves c1 to it (the earlier report is outside the scope), listing the earlier one makes
    # c1 an id two reports of the scope hold, and c2 (only in the earlier report) resolves to no report of the scope
    assert out[("syn-2", "s1")] == {"c1": {"ra2"}} and out[("syn-2", "s2")] == {"c2": frozenset()}
    assert out[("syn-3", "s1")] == {"c1": {"ra", "ra2"}}, "ra3 is delivered after syn-3: outside its scope"
    opaque = NS(transfers=[rep("ra", "a", "c1"), rep("rb", "b", "d1", digest_only=True), syn("syn-1", ["ra", "rb"], [["c1"]])])
    assert _synthesis_citations(opaque)[("syn-1", "s1")] == {"c1": None}


def test_each_part_dossier_holds_its_own_transfers_and_only_the_merged_one_the_context(pack):
    seen: list = []
    hub, _plan, ch, pr, rv, _b, _a = _review("keeps", pack, seen=seen)
    try:
        roles = sorted((json.loads(r).get("role"), json.loads(r).get("source"), has) for _agent, r, has in seen)
        lay = pr.plan.twofold[ch.channel_uid]
        want = sorted([("source", 1, False)] * len(lay.sources[0]) + [("source", 2, False)] * len(lay.sources[1]) + [("merged", None, True)] * len(lay.merged))
        assert roles == want
        assert all(json.loads(r)["method"] == "N_FOLD" and json.loads(r)["of"] == 2 for _a2, r, _h in seen)
    finally:
        hub.close()


# ----------------------------------------------------------------------------------------------- the temporary context
def test_the_context_holds_only_structured_validated_outcomes_never_agent_text_or_codes(pack):
    hub, _plan, _ch, _pr, rv, _b, _a = _review("keeps", pack)
    try:
        text = json.dumps(rv.twofold.context_record, sort_keys=True)
        assert "The transfer looks wrong." not in text and "statement" not in text and "notes" not in text
        assert "OVS-" not in text and "INT-" not in text and "quote" not in text
        allowed = {"format", "scope", "task_id", "request_id", "max_bytes", "bytes", "sources", "source", "agent_id", "report_ids", "message_ids",
                   "reviewed", "confirmed", "kind", "claim_ids", "document_ids", "result_ids", "omitted", "complete", "discard", "context_sha256"}

        def keys(x):
            if isinstance(x, dict):
                return set(x) | {k for v in x.values() for k in keys(v)}
            if isinstance(x, list):
                return {k for v in x for k in keys(v)}
            return set()
        assert keys(rv.twofold.context_record) <= allowed
    finally:
        hub.close()


def _keeps_context(pack):
    """The keeps case's layout and the validated source assessments, to build contexts of any bound from."""
    hub, plan, ch, pr, rv, _b, _a = _review("keeps", pack)
    lay = combined_layout(hub.auditor.view(ch.channel_uid))
    return hub, plan, ch, lay, {p.index: list(p.assessments) for p in rv.twofold.sources}


def test_the_context_is_bounded_cut_from_the_end_and_counted(pack):
    hub, _plan, _ch, lay, assessed = _keeps_context(pack)
    try:
        full = TemporaryContext.build(lay, assessed)
        rec = full.record
        assert rec["complete"] and rec["omitted"] == 0 and full.faulted() and rec["bytes"] <= CONTEXT_MAX_BYTES
        skeleton = TemporaryContext.build(lay, {})
        bound = skeleton.record["bytes"]  # room for the sources, none for a fault record
        cut = TemporaryContext.build(lay, assessed, max_bytes=bound)
        crec = cut.record
        assert crec["bytes"] <= crec["max_bytes"] == bound and crec["complete"] is False and crec["omitted"] == 1
        assert all(s["confirmed"] == [] for s in crec["sources"]) and cut.faulted() == {}, "a cut record decides nothing"
        with pytest.raises(ValueError, match="cannot hold its empty record"):
            TemporaryContext.build(lay, assessed, max_bytes=16)
        for bad in (0, CONTEXT_MAX_BYTES + 1):
            with pytest.raises(ValueError, match="bound"):
                TemporaryContext.build(lay, assessed, max_bytes=bad)
        # deterministic: the same assessments give the same record and digest
        assert TemporaryContext.build(lay, assessed).digest == full.digest
    finally:
        hub.close()


def test_the_context_is_scoped_to_its_channel_task_and_request_and_refused_anywhere_else(pack):
    hub, plan, ch, lay, assessed = _keeps_context(pack)
    other_hub, _p2, other_ch = _combined()
    try:
        # round-9 clearance c2b (stricter): each context is built in the blind dossier's own mode, and a context built for an informed
        # review is refused for a blind dossier (the c4f276c push check: the intake did not read the context's mode)
        ctx = TemporaryContext.build(lay, assessed, mode="blind")
        intake = hub.auditor.hub_operations._review_intake(hub)
        view = hub.auditor.view(ch.channel_uid)
        merged = part_view(view, lay.merged_seqs)
        pid = PackIdentity(name=pack.identity.name, version=pack.identity.version, sha256=pack.identity.sha256)
        kw = dict(agent_id="overseer-pool-9", lens="general", mode="blind", pack=pid, review=review_scope("merged", 2))
        with pytest.raises(IntakeRefused) as e0:
            intake.issue(merged, temporary_context=TemporaryContext.build(lay, assessed), **{**kw, "agent_id": "overseer-pool-10"})
        assert e0.value.reason == "temporary_context" and "informed" in str(e0.value)
        d = intake.issue(merged, temporary_context=ctx, **kw)
        assert d["temporary_context"]["context_sha256"] == ctx.digest and d["review"] == {"method": "N_FOLD", "role": "merged", "of": 2}
        # another channel: refused
        other_view = other_hub.auditor.view(other_ch.channel_uid)
        with pytest.raises(IntakeRefused) as e1:
            other_hub.auditor.hub_operations._review_intake(other_hub).issue(part_view(other_view, combined_layout(other_view).merged_seqs),
                                                                               temporary_context=ctx, **{**kw, "agent_id": "overseer-pool-8"})
        assert e1.value.reason == "temporary_context"
        # another task or request: a context built for another scope never reaches this dossier
        import dataclasses
        elsewhere = TemporaryContext.build(dataclasses.replace(lay, request_id="req-other"), assessed, mode="blind")
        with pytest.raises(IntakeRefused) as e2:
            intake.issue(merged, temporary_context=elsewhere, **{**kw, "agent_id": "overseer-pool-7"})
        assert e2.value.reason == "temporary_context"
        # an edited record does not hash to its digest: refused; a discarded one: refused
        edited = TemporaryContext.build(lay, assessed, mode="blind")
        edited._record["sources"][0]["confirmed"] = []
        with pytest.raises(IntakeRefused) as e3:
            intake.issue(merged, temporary_context=edited, **{**kw, "agent_id": "overseer-pool-6"})
        assert e3.value.reason == "temporary_context"
        ctx.discard()
        with pytest.raises(IntakeRefused) as e4:
            intake.issue(merged, temporary_context=ctx, **{**kw, "agent_id": "overseer-pool-5"})
        assert e4.value.reason == "temporary_context" and ctx.record == {} and ctx.faulted() == {} and ctx.digest
        # a temporary context only in a merged review, a merged review only with one
        with pytest.raises(IntakeRefused) as e5:
            intake.issue(merged, temporary_context=TemporaryContext.build(lay, assessed, mode="blind"), **{**kw, "agent_id": "overseer-pool-4",
                                                                                            "review": review_scope("source", 2, 1)})
        assert e5.value.reason == "review"
        with pytest.raises(IntakeRefused) as e6:
            intake.issue(merged, **{**kw, "agent_id": "overseer-pool-3"})
        assert e6.value.reason == "review"
    finally:
        hub.close()
        other_hub.close()


def test_a_part_dossier_is_never_issued_under_a_pack_that_does_not_teach_the_n_fold_review(pack):
    hub, _plan, ch = _combined()
    try:
        older = PackIdentity(name=pack.identity.name, version="1.5", sha256=PACK_DIGESTS[(pack.identity.name, "1.5")])
        assert not teaches_n_fold(older) and teaches_n_fold(pack.identity)
        view = hub.auditor.view(ch.channel_uid)
        lay = combined_layout(view)
        from epinoic_overseer.intake import VerdictIntake
        intake = VerdictIntake(hub.auditor.keyring, accepted_packs={older, pack.identity})  # an intake that accepts 1.5 dossiers at all
        with pytest.raises(IntakeRefused) as e:
            intake.issue(part_view(view, lay.sources[0].seqs), agent_id="overseer-pool-1", lens="general", mode="blind", pack=older,
                         review=review_scope("source", 2, 1))
        assert e.value.reason == "review" and "does not teach the N_FOLD review" in str(e.value)
        # the same pack issues the whole dossier as before (no part)
        assert intake.issue(view, agent_id="overseer-pool-2", lens="general", mode="blind", pack=older)["pack"]["version"] == "1.5"
        assert load_pack(installed_pack_dir("1.5")).identity == older
    finally:
        hub.close()


def test_the_context_is_discarded_after_the_request_even_when_the_merged_review_fails(pack):
    hub, plan, ch = _combined("keeps")
    try:
        pool = OverseerPool(pack, lambda agent_id: Scripted(_replies("keeps")))
        view = hub.auditor.view(ch.channel_uid)
        item, lay = pool_item(view, ch.channel_uid, 0, {})
        pplan = pool.plan([item])
        runners = {r.agent_id: r for r in pool.runners_for(pplan, ch.channel_uid)}
        ops = hub.auditor.hub_operations
        intake = ops._review_intake(hub)
        task_audit = ops._reference_audit(hub.auditor, ch.channel_uid, view)
        from epinoic_overseer.combine import combine_verdicts
        from epinoic_overseer.validate import validate_overseer_verdict
        built: list = []
        real_build = TemporaryContext.build

        def spy(*a, **k):
            built.append(real_build(*a, **k))
            return built[-1]

        def validate(message, ctx):
            if ctx is not None:
                raise RuntimeError("the merged validation fails")
            return validate_overseer_verdict(message, view, hub.auditor.store, task_audit, hub.auditor, intake=intake, live=ch)
        TemporaryContext.build = staticmethod(spy)  # type: ignore[method-assign]
        try:
            with pytest.raises(RuntimeError, match="merged validation fails"):
                run_twofold(layout=lay, view=view, plan_twofold=pplan.twofold[ch.channel_uid], runners=runners, intake=intake, mode="blind",
                            task_audit=task_audit, consolidations=(), validate=validate, combine=lambda xs: combine_verdicts(xs, intake=intake))
        finally:
            TemporaryContext.build = real_build  # type: ignore[method-assign]
        [ctx] = built
        assert ctx.discarded and ctx.record == {} and ctx.faulted() == {} and not ctx.verifies()
    finally:
        hub.close()


# ----------------------------------------------------------------------------------------------- N sources and the waves
def test_three_specialists_give_three_source_reviews_then_one_merged_review(pack):
    hub, plan, ch, pr, rv, before, after = _review("faithful", pack, three=True)
    try:
        lay = pr.plan.twofold[ch.channel_uid]
        assert len(lay.sources) == 3 and rv.twofold.layout.n == 3 and [p.index for p in rv.twofold.sources] == [1, 2, 3]
        assert [s["agent_id"] for s in rv.twofold.context_record["sources"]] == ["english-specialist", "history-specialist", "economics-specialist"]
        assert all(p.assessments for p in rv.twofold.sources) and rv.twofold.merged.assessments and before == after
        decision = next(d for d in pr.plan.admission.decisions if d.key == ch.channel_uid)
        assert (decision.method, decision.approach) == ("N_FOLD", "duplication") and "floor_n_fold" in decision.reasons
    finally:
        hub.close()


def test_the_waves_never_give_one_agent_two_open_issues_of_one_task():
    assert _waves([(1, ["a", "b"]), (2, ["a", "c"]), (3, ["a"])]) == [[(1, "a"), (1, "b"), (2, "c")], [(2, "a")], [(3, "a")]]
    assert _waves([(1, ["a"]), (2, ["b"])]) == [[(1, "a"), (2, "b")]]


def test_instances_review_the_parts_in_turn_when_the_pool_has_fewer_than_they_need(pack):
    """The pool's smallest maximum, two: both sources call for two reviews (four instances needed at once), so the two
    instances review source 1, then source 2, then the merged review, each in its own wave (one open issue per agent and
    task), and every review still runs."""
    seen: list = []
    hub, plan, ch, pr, rv, before, after = _review("keeps", pack, max_instances=2, seen=seen)
    try:
        lay = pr.plan.twofold[ch.channel_uid]
        both = ("overseer-pool-1", "overseer-pool-2")
        assert lay.sources == (both, both) and len(lay.merged) == 1 and pr.plan.capped and len(pr.plan.instances) == 2
        order = [(a, json.loads(r).get("role"), json.loads(r).get("source")) for a, r, _h in seen]
        for agent in both:
            mine = [(role, src) for a, role, src in order if a == agent]
            assert mine[:2] == [("source", 1), ("source", 2)], mine
        assert all(len(p.assessments) == 2 for p in rv.twofold.sources)
        assert _outcomes(rv.twofold.merged) == [("synthesis_carries_fault", "confirmed")] and before == after
    finally:
        hub.close()


# ----------------------------------------------------------------------------------------------- the plan: router and floor
def test_the_floor_reviews_a_combined_answer_n_fold_and_keeps_the_context_bound():
    from epinoic_overseer.floor import floor_part_reviewers
    hub, plan, ch = _combined()
    try:
        uid = ch.channel_uid
        item, _lay = pool_item(hub.auditor.view(uid), uid, 0, {})
        want = [floor_part_reviewers(p, item) for p in item.sources]
        merged_want = floor_part_reviewers(item.merged, item)
        pool_ids = [f"i{n}" for n in range(1, 9)]
        at_floor = {"sources": [pool_ids[2 * k:2 * k + w] for k, w in enumerate(want)], "merged": pool_ids[:merged_want],
                    "context_max_bytes": CONTEXT_MAX_BYTES}
        assert below_floor({}, [item], twofold={uid: at_floor}) is None
        # reviewed whole instead of N_FOLD, a source short of its reviews, a merged review short of its reviews, a smaller bound
        assert "which the floor reviews N_FOLD" in below_floor({uid: ["i1", "i2"]}, [item])
        short = dict(at_floor, sources=[at_floor["sources"][0][:want[0] - 1] or [], *at_floor["sources"][1:]])
        assert "source 1 of combined answer" in below_floor({}, [item], twofold={uid: short})
        assert "the merged review of combined answer" in below_floor({}, [item], twofold={uid: dict(at_floor, merged=[])})
        assert "bounded at 4096 bytes" in below_floor({}, [item], twofold={uid: dict(at_floor, context_max_bytes=4096)})
        assert "has 2 sources" in below_floor({}, [item], twofold={uid: dict(at_floor, sources=at_floor["sources"][:1])})
    finally:
        hub.close()


def test_the_flash_router_plans_the_combined_answer_n_fold_and_the_overseer_admits_it(pack):
    router = attach_in_process()
    assert router.attached, router.detail
    hub, plan, ch, pr, rv, before, after = _review("keeps", pack, router=router)
    try:
        a = pr.plan.admission
        assert (a.origin, a.refusal, a.port_version) == ("router", None, "1.2")
        d = next(x for x in a.decisions if x.key == ch.channel_uid)
        assert (d.origin, d.method, d.approach) == ("router", "N_FOLD", "duplication") and "combined_n_fold" in d.reasons
        assert [p["part"] for p in d.router["parts"]] == ["source", "source", "merged"]
        assert pr.plan.twofold[ch.channel_uid].context_max_bytes == CONTEXT_MAX_BYTES
        assert _outcomes(rv.twofold.merged) == [("synthesis_carries_fault", "confirmed")] and before == after
    finally:
        hub.close()


def _scratch_router(tmp_path: Path, monkeypatch, edit) -> str:
    src = flash_router_src() / "epinoic_flash_router"
    dest = tmp_path / "src" / "epinoic_flash_router"
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    edit(dest / "data")
    monkeypatch.syspath_prepend(str(tmp_path / "src"))
    return "epinoic_flash_router.port"


def test_a_router_that_bounds_the_context_below_the_floor_is_refused_and_the_floor_runs(tmp_path, monkeypatch, pack):
    def smaller_context(data: Path):
        m = json.loads((data / "MANIFEST.json").read_text(encoding="utf-8"))
        f = data / m["current"]["rules"]
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc["parameters"]["context_max_bytes"] = 4096
        f.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    router = attach(_scratch_router(tmp_path, monkeypatch, smaller_context))
    assert router.attached, router.detail
    hub, plan, ch, pr, rv, before, after = _review("keeps", pack, router=router)
    try:
        a = pr.plan.admission
        assert (a.origin, a.refusal) == ("floor", "KIT-RT-020") and "bounded at 4096 bytes" in a.detail and a.router == router.identity
        assert pr.plan.twofold[ch.channel_uid].context_max_bytes == CONTEXT_MAX_BYTES
        assert _outcomes(rv.twofold.merged) == [("synthesis_carries_fault", "confirmed")] and before == after
        assert "KIT-RT-020" in "\n".join(rv.audit.coverage.notes)
    finally:
        hub.close()


def test_a_pool_port_1_1_router_is_refused_for_a_batch_with_a_combined_answer(tmp_path, monkeypatch, pack):
    def released_0_2_0(data: Path):
        m = json.loads((data / "MANIFEST.json").read_text(encoding="utf-8"))
        m["current"] = {"rules": "rules-2.json", "cost_data": "cost-data-2.json"}
        (data / "MANIFEST.json").write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")
    router = attach(_scratch_router(tmp_path, monkeypatch, released_0_2_0))
    assert router.attached and router.hello.port_version == "1.1", router.detail
    hub, plan, ch, pr, rv, before, after = _review("faithful", pack, router=router)
    try:
        a = pr.plan.admission
        assert (a.origin, a.refusal) == ("floor", "KIT-RT-015") and ch.channel_uid in pr.plan.twofold and rv.twofold is not None
        assert before == after
    finally:
        hub.close()


# ----------------------------------------------------------------------------------------------- determinism
def test_the_same_journal_gives_the_same_layout_plan_and_context(pack):
    hub, plan, ch = _combined("keeps")
    try:
        view = hub.auditor.view(ch.channel_uid)
        a, b = pool_item(view, ch.channel_uid, 0, {}), pool_item(hub.auditor.view(ch.channel_uid), ch.channel_uid, 0, {})
        assert a[0] == b[0] and a[1] == b[1]
        pool = OverseerPool(pack, lambda agent_id: Scripted(_replies("keeps")))
        p1, p2 = pool.plan([a[0]]), pool.plan([b[0]])
        assert p1.plan_id == p2.plan_id and p1.twofold == p2.twofold
        r1 = hub.review_pool([plan.task_id], pool).reviews[ch.channel_uid]
        r2 = hub.review_pool([plan.task_id], pool).reviews[ch.channel_uid]
        rec1, rec2 = (dict(r.twofold.context_record) for r in (r1, r2))
        assert rec1 == rec2 and r1.twofold.context_sha256 == r2.twofold.context_sha256
        assert _outcomes(r1.twofold.merged) == _outcomes(r2.twofold.merged) == [("synthesis_carries_fault", "confirmed")]
    finally:
        hub.close()
