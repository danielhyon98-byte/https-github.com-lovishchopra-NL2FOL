"""Integration gate, round 4 (before arena round 8): the shadow replay and the channel's STEM check budget.

major, ``checks/shadow.py``: the channel decides a report's STEM checks under a wall-clock budget
(``channel.bus.STEM_CHECK_BUDGET_S``, 8 s, or the smaller per-channel ``stem_budget_s`` the integration checks port sets
from what its deadline leaves) and states every check left when it is spent as not run (``satisfied`` null, no result,
INT-SUBJ-002 "check budget"). On a loaded machine the hub's receipt honestly stated the late checks so; the shadow replay,
with time to decide them, accused the faithful transfer with one OVS-RCPT-004 per check ("raises INT-SUBJ-001 ... which
its receipt lacks") and OVS-RCPT-005, so the audit was AUDIT_FAILED depending on machine load (the lens reported three
parallel audited Physics hubs on 1,200 wrong steps, one of which failed). Rule ``budget-cut`` (decision 87) replays the receipt's cut
instead, when it is the image of the channel's budget rule, and compares everything else as before:

* a cut under the module budget is a note, and the audit passes (the verdict does not depend on machine load);
* a cut under a smaller budget is a note when the plan's deadline accounts for it, else OVS-RES-008 (a warning, never an
  accusation): the requested regression, a channel whose ``stem_budget_s`` is 0 for one transfer;
* checks the shadow's own budget left undecided that the receipt decided are OVS-RES-008 (the auditor's environment);
* a specialist's report relayed to the combinator, whose branch checks the relay runs again, is replayed the same way;
* a cut whose INT-SUBJ-002 was dropped is still OVS-RCPT-004; a cut that is not the channel's budget rule (a check in
  the middle, a budget the journal's timing refutes, a budget above the module's, two budgets) is compared as the
  shadow decides it, so the failure it hides is OVS-RCPT-004.

A loaded machine is simulated deterministically: the channel's clock (``channel.bus.time``) advances 3 s per reading, so
the budget is spent after the second check, and the journal's event clock (``channel.events.time``) stamps the transfer
100 s after the one before it, as a transfer that spent its budget is stamped.
"""
from __future__ import annotations

import time
import types
from datetime import datetime, timedelta, timezone

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, bus, events
from epinoic_logic.channel.contracts import ConstraintResult, TransmissionStatus
from epinoic_logic.integrity import IntegrityFinding, WorkPlan
from epinoic_overseer.checks import shadow as SH

from .timing import measure
from .conftest import CFG, KEY, make_auditor

PHYSICS = ("Physics", "physics-specialist")
CHEMISTRY = ("Chemistry", "chemistry-specialist")
#: Five wrong steps: each is a STEM arithmetic check that fails (INT-SUBJ-001 on claims s1.1 to s1.5) when it is decided.
WRONG = "x = 20/4.0 = 6.0. " * 5
CHEM_WRONG = "n = 0.50 × 2.0 = 2.0 mol. " * 2
CODES = ("OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-008")


class _Clock:
    """A clock that advances ``step`` seconds per reading (the channel's budget loop reads it once per STEM check)."""

    def __init__(self, step: float) -> None:
        self.now, self.step = 0.0, step

    def perf_counter(self) -> float:
        self.now += self.step
        return self.now


def _loaded(mp) -> None:
    """The live channel's machine is loaded: its STEM checks run past the budget after the second one, and the journal
    stamps the transfer 100 s after the one before it."""
    mp.setattr(bus, "time", types.SimpleNamespace(perf_counter=_Clock(3.0).perf_counter))
    mp.setattr(events, "time", types.SimpleNamespace(monotonic_ns=lambda: time.monotonic_ns() + 100_000_000_000))


def _hub(agents=(PHYSICS,), deadline_at=None):
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    subject = agents[0][0]
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[a for _s, a in agents],
                           agent_subjects={a: s for s, a in agents[1:]}, deadline_at=deadline_at))
    mids = {a: hub.dispatch("t", a, "Answer the question.")[0].message_id for _s, a in agents}
    return hub, mids


def _receive(hub, mids, agent: str, answer: str, report_id: str):
    _msg, rc = hub.receive("t", mids[agent], answer, agent_id=agent, report_id=report_id)
    return rc


def _found(audit, code: str, message_id=None) -> list:
    return [f for f in audit.report.findings if f.code == code and (message_id is None or message_id in f.message_ids)]


def _accusations(audit) -> list:
    return [f for f in audit.report.findings if f.code in CODES]


def _by_id(rc) -> dict:
    return {c.constraint_id: c for c in rc.formal_checks}


def _cut_ids(rc) -> list[str]:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is None and c.formal_result_id is None and "STEM check budget" in c.detail]


#: The module budget as the channel writes it, and the checks of ``WRONG`` the loaded clock leaves (the k-th STEM check is
#: reached 3k s after the budget started, so it is left when 3k exceeds the budget: from the third on under 8 s).
MODULE = f"{bus.STEM_CHECK_BUDGET_S:g}"
LOADED_CUT = [f"stem-eq-{k}" for k in range(1, 6) if 3 * k > bus.STEM_CHECK_BUDGET_S]
#: A budget above the module's, which no channel can have used.
ABOVE = f"{bus.STEM_CHECK_BUDGET_S + 1:g}"


# ============================================================================================ the requested regression
def test_a_channel_stem_budget_of_zero_for_one_transfer_is_never_rcpt_004():
    """The channel's ``stem_budget_s`` set to 0 for one transfer: every STEM check of that report is stated not run; the
    audit names the reduced budget the plan does not account for (OVS-RES-008, a warning) and accuses nothing, while the
    next transfer, decided under the channel's own budget, is compared check by check as before."""
    hub, mids = _hub(agents=(PHYSICS, CHEMISTRY))
    try:
        hub.channels["t"].stem_budget_s = 0
        rc1 = _receive(hub, mids, "physics-specialist", WRONG, "r1")
        hub.channels["t"].stem_budget_s = None
        rc2 = _receive(hub, mids, "chemistry-specialist", CHEM_WRONG, "r2")
        stem1 = [c for c in rc1.formal_checks if c.detail.startswith("stem_")]
        assert stem1 and all(c.satisfied is None and c.formal_result_id is None and "STEM check budget (0 s) was spent" in c.detail for c in stem1)
        budget_warnings = [f for f in rc1.findings if f.code == "INT-SUBJ-002" and "check budget" in f.message]
        assert len(budget_warnings) == len(stem1) and not [f for f in rc1.findings if f.code == "INT-SUBJ-001"]
        assert [f for f in rc2.findings if f.code == "INT-SUBJ-001"]  # decided under the channel's own budget
        audit = hub.audit("t")
        assert audit.coverage.shadow_run == "run"
        assert not _accusations(audit), [(f.code, f.message[:160]) for f in _accusations(audit)]
        res = _found(audit, "OVS-RES-008", rc1.message_id)
        assert len(res) == 1 and res[0].severity == "warning"
        assert "0 s" in res[0].message and "the plan states no deadline" in res[0].message and "rule budget-cut" in res[0].message
        assert not _found(audit, "OVS-RES-008", rc2.message_id)
        assert audit.state == "AUDIT_PASSED_WITH_FINDINGS"
    finally:
        hub.close()


# ============================================================================================ the bug: load on the hub
def test_control_the_shadow_compares_every_check_of_an_uncut_receipt():
    hub, mids = _hub()
    try:
        rc = _receive(hub, mids, "physics-specialist", WRONG, "r1")
        assert len([f for f in rc.findings if f.code == "INT-SUBJ-001"]) == 5 and not _cut_ids(rc)
        audit = hub.audit("t")
        assert audit.state == "AUDIT_PASSED" and not audit.report.findings
        assert not [n for n in audit.coverage.notes if "budget-cut" in n]
    finally:
        hub.close()


def test_a_receipt_cut_by_the_module_budget_on_a_loaded_machine_passes_with_a_note():
    """The reported failure: the hub's receipt states the late checks not run under the 8 s budget, the shadow decides
    them; with rule budget-cut the audit passes (no OVS-RCPT-004, -005, -008 and no warning) and a note names the cut."""
    hub, mids = _hub()
    try:
        with pytest.MonkeyPatch.context() as mp:
            _loaded(mp)
            rc = _receive(hub, mids, "physics-specialist", WRONG, "r1")
        assert LOADED_CUT and _cut_ids(rc) == LOADED_CUT
        assert all(f"STEM check budget ({MODULE} s) was spent" in _by_id(rc)[c].detail for c in _cut_ids(rc))
        assert sorted(tuple(f.claim_ids) for f in rc.findings if f.code == "INT-SUBJ-001") == [(f"s1.{k}",) for k in range(1, 6) if f"stem-eq-{k}" not in LOADED_CUT]
        audit = hub.audit("t")
        assert audit.coverage.shadow_run == "run"
        assert not audit.report.findings, [(f.code, f.message[:160]) for f in audit.report.findings]
        assert audit.state == "AUDIT_PASSED"
        note = [n for n in audit.coverage.notes if "rule budget-cut" in n and rc.message_id in n]
        assert note and f"{len(LOADED_CUT)} STEM check(s) undecided under a STEM check budget of {MODULE} s" in note[0] and LOADED_CUT[0] in note[0]
    finally:
        hub.close()


def test_the_shadows_own_budget_is_res_008_never_an_accusation():
    """The auditor's machine is the loaded one: the shadow's channel leaves checks undecided that the receipt decided; those
    are not compared, the audit says so (OVS-RES-008) and accuses nothing."""
    hub, mids = _hub()
    try:
        rc = _receive(hub, mids, "physics-specialist", WRONG, "r1")
        assert not _cut_ids(rc)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bus, "time", types.SimpleNamespace(perf_counter=_Clock(3.0).perf_counter))
            audit = hub.audit("t")
        assert not _accusations(audit)
        res = _found(audit, "OVS-RES-008", rc.message_id)
        assert len(res) == 1 and f"own STEM check budget ({MODULE} s)" in res[0].message and LOADED_CUT[0] in res[0].message
        assert audit.state == "AUDIT_PASSED_WITH_FINDINGS"
    finally:
        hub.close()


def test_a_relay_whose_checks_the_budget_cut_is_replayed_too():
    """A specialist's report relayed to the combinator has its branch checks run again under the channel's budget (a
    router's forward does not): a relay made while the channel's budget is 0 states every STEM check not run, and the
    shadow replays that cut on the relay as on a response (OVS-RES-008 for the reduced budget, no accusation), while the
    delivery before it, decided, is compared check by check."""
    from epinoic_logic.integrity import AgentRole
    from epinoic_logic.translate.contracts import SpecialistReport
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer",
                               selected_agent_ids=["physics-specialist", "combinator"]))
        m = hub.dispatch("t", "physics-specialist", "Answer the question.")[0]
        reply, rc = hub.receive("t", m.message_id, WRONG, agent_id="physics-specialist", report_id="r1")
        assert len([f for f in rc.findings if f.code == "INT-SUBJ-001"]) == 5
        ch = hub.channels["t"]
        ch.stem_budget_s = 0
        _msg, rr = ch.relay("physics-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, SpecialistReport.model_validate(reply.payload))
        ch.stem_budget_s = None
        assert rr.status is not TransmissionStatus.REJECTED and _cut_ids(rr) and not [f for f in rr.findings if f.code == "INT-SUBJ-001"]
        audit = hub.audit("t")
        assert not _accusations(audit), [(f.code, f.message[:160]) for f in _accusations(audit)]
        res = _found(audit, "OVS-RES-008", rr.message_id)
        assert len(res) == 1 and "0 s" in res[0].message and "relay_report" in res[0].message
        assert not _found(audit, "OVS-RES-008", rc.message_id)
    finally:
        hub.close()


# ============================================================================================ a cut the rule does not explain away
def _drop_budget_warnings(orig):
    def dropped(self, message_id, direction, status, findings_, **kw):
        return orig(self, message_id, direction, status, [f for f in findings_ if not (f.code == "INT-SUBJ-002" and "check budget" in f.message)], **kw)
    return dropped


def test_a_cut_whose_not_run_warning_was_dropped_is_still_rcpt_004():
    hub, mids = _hub()
    try:
        with pytest.MonkeyPatch.context() as mp:
            _loaded(mp)
            mp.setattr(TranslatorChannel, "_receipt", _drop_budget_warnings(TranslatorChannel._receipt))
            rc = _receive(hub, mids, "physics-specialist", WRONG, "r1")
        assert _cut_ids(rc) == LOADED_CUT and not [f for f in rc.findings if f.code == "INT-SUBJ-002"]
        audit = hub.audit("t")
        f4 = [f for f in _found(audit, "OVS-RCPT-004", rc.message_id) if "INT-SUBJ-002" in f.message]
        assert sorted(tuple(f.claim_ids) for f in f4) == [(f"s1.{c.rsplit('-', 1)[1]}",) for c in LOADED_CUT] and all(f.severity == "error" for f in f4)
        assert audit.state == "AUDIT_FAILED"
    finally:
        hub.close()


def _forge_cut(budgets: dict[str, str]):
    """A channel patched to state the named decided checks as not run under the given STEM check budgets, exactly in the
    channel's form (the check's detail and its INT-SUBJ-002), the failure finding of each dropped."""
    orig = TranslatorChannel._receipt

    def forged(self, message_id, direction, status, findings_, **kw):
        branch_formal = list(kw.get("branch_formal") or ())
        if direction != "specialist_to_router" or not branch_formal:
            return orig(self, message_id, direction, status, findings_, **kw)
        findings_ = list(findings_)
        out = []
        for cr in branch_formal:
            b = budgets.get(cr.constraint_id)
            if b is None or not cr.formal_result_id:
                out.append(cr)
                continue
            head = cr.detail.rsplit("; solver ", 1)[0]
            kind = SH._kind(cr)
            where = SH._where(cr.claim_ids)
            body = head[len(f"{kind}{where}: "):]
            out.append(ConstraintResult(constraint_id=cr.constraint_id, satisfied=None, method="formal", claim_ids=list(cr.claim_ids),
                                        detail=f"{head}; not run: the report's STEM check budget ({b} s) was spent"))
            findings_ = [f for f in findings_ if f.formal_result_id != cr.formal_result_id]
            findings_.append(IntegrityFinding(code="INT-SUBJ-002", severity="warning", claim_ids=list(cr.claim_ids), report_ids=["r1"], agent_ids=["physics-specialist"],
                                              message=f"{kind} check{where} undecided (check budget: the report's STEM checks ran past {b} s; not run): {body}"))
        kw["branch_formal"] = out
        return orig(self, message_id, direction, status, findings_, **kw)
    return forged


FORGED = [
    pytest.param({"stem-eq-2": "8"}, [("s1.2",)], "stated otherwise", id="a-check-in-the-middle"),
    pytest.param({"stem-eq-4": "8", "stem-eq-5": "8"}, [("s1.4",), ("s1.5",)], "less than the 8 s budget", id="a-budget-the-journal-timing-refutes"),
    pytest.param({"stem-eq-4": "8", "stem-eq-5": "7"}, [("s1.4",), ("s1.5",)], "different budgets", id="two-budgets"),
    pytest.param({"stem-eq-4": ABOVE, "stem-eq-5": ABOVE}, [("s1.4",), ("s1.5",)], None, id="a-budget-above-the-modules"),
    pytest.param({"stem-eq-4": "8.0", "stem-eq-5": "8.0"}, [("s1.4",), ("s1.5",)], None, id="a-budget-the-channel-does-not-write"),
]


@pytest.mark.parametrize("budgets,hidden,why", FORGED)
def test_a_cut_that_is_not_the_channels_budget_rule_hides_no_failure(budgets, hidden, why):
    """A receipt stating decided checks as not run in a way the channel's budget rule cannot produce is compared as the
    shadow decides it: each failure the forged cut hides is OVS-RCPT-004, and a note says why the cut was not replayed."""
    hub, mids = _hub()
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(TranslatorChannel, "_receipt", _forge_cut(budgets))
            rc = _receive(hub, mids, "physics-specialist", WRONG, "r1")
        assert sorted(_cut_ids(rc)) == sorted(budgets)
        audit = hub.audit("t")
        f4 = [f for f in _found(audit, "OVS-RCPT-004", rc.message_id) if "INT-SUBJ-001" in f.message]
        assert sorted(tuple(f.claim_ids) for f in f4) == hidden
        assert audit.state == "AUDIT_FAILED"
        notes = [n for n in audit.coverage.notes if "rule budget-cut" in n and rc.message_id in n]
        if why is None:
            assert not notes  # not even read as a cut: no budget the channel can have written
        else:
            assert len(notes) == 1 and why in notes[0] and "compares those checks as it decides them" in notes[0]
        assert not _found(audit, "OVS-RES-008", rc.message_id)
    finally:
        hub.close()


def test_control_a_suffix_cut_in_the_channels_form_on_a_loaded_transfer_is_replayed():
    """The control of the forgeries: the same two checks stated not run under 8 s in the channel's form, on a transfer the
    journal stamps 100 s after the one before it, is the channel's budget rule's image and is replayed (a note, no
    accusation)."""
    hub, mids = _hub()
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(events, "time", types.SimpleNamespace(monotonic_ns=lambda: time.monotonic_ns() + 100_000_000_000))
            mp.setattr(TranslatorChannel, "_receipt", _forge_cut({"stem-eq-4": "8", "stem-eq-5": "8"}))
            rc = _receive(hub, mids, "physics-specialist", WRONG, "r1")
        audit = hub.audit("t")
        assert not _accusations(audit) and not _found(audit, "OVS-RES-008")
        assert [n for n in audit.coverage.notes if "rule budget-cut" in n and rc.message_id in n and "stem-eq-4, stem-eq-5" in n]
    finally:
        hub.close()


# ============================================================================================ reduced budgets and the plan's deadline
def _deadline(seconds: float) -> str:
    """The plan's deadline as the integration checks port writes it (to the second)."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _budget_left(at: str) -> float:
    """The budget the integration checks port gives a transfer's STEM checks just before it: what the deadline leaves, at
    most the module budget (``TurnChecker._check``)."""
    left = (datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()
    return min(bus.STEM_CHECK_BUDGET_S, max(0.0, left))


def test_a_reduced_budget_the_plans_deadline_left_is_a_note():
    at = _deadline(7.0)
    hub, mids = _hub(deadline_at=at)
    try:
        budget = _budget_left(at)
        assert budget < bus.STEM_CHECK_BUDGET_S
        hub.channels["t"].stem_budget_s = budget
        with pytest.MonkeyPatch.context() as mp:
            _loaded(mp)
            rc = _receive(hub, mids, "physics-specialist", WRONG, "r1")
        assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS and _cut_ids(rc)
        audit = hub.audit("t")
        assert not _accusations(audit) and not _found(audit, "OVS-RES-008"), [(f.code, f.message[:200]) for f in audit.report.findings]
        assert [n for n in audit.coverage.notes if "rule budget-cut" in n and rc.message_id in n]
    finally:
        hub.close()


def test_a_reduced_budget_a_distant_deadline_does_not_account_for_is_res_008():
    at = _deadline(3600.0)
    hub, mids = _hub(deadline_at=at)
    try:
        hub.channels["t"].stem_budget_s = 0.5
        with pytest.MonkeyPatch.context() as mp:
            _loaded(mp)
            rc = _receive(hub, mids, "physics-specialist", WRONG, "r1")
        assert _cut_ids(rc)
        audit = hub.audit("t")
        assert not _accusations(audit)
        res = _found(audit, "OVS-RES-008", rc.message_id)
        assert len(res) == 1 and "0.5 s" in res[0].message and "the plan's deadline left" in res[0].message
    finally:
        hub.close()


# ============================================================================================ the channel's forms, read exactly
ANSWER_KINDS = ("The trolley starts from rest, so u = 0. Given v = 20 m s⁻¹ and t = 4.0 s.\n"
                "Using a = (v - u)/t, a = (20 - 0)/4.0 = 6.0 m s⁻².\n"
                "The acceleration is therefore 6.0 m s⁻². 2 km = 2000 m. Since 5 > 3, the speed rose.\n")


def test_every_stem_check_the_channel_cuts_is_read_as_cut_with_its_statement():
    """The forms the rule reads are the channel's own: on a channel run under a budget of 0 s every STEM check (given,
    substitution, arithmetic, result, conversion, comparison) is read as cut under '0', with exactly one INT-SUBJ-002
    statement each; under the channel's own budget none is."""
    for budget, cut in ((0, True), (None, False)):
        hub = RouterHub(signing_key=KEY, config=CFG)
        try:
            hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist"]))
            m = hub.dispatch("t", "physics-specialist", "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.")[0]
            hub.channels["t"].stem_budget_s = budget
            _msg, rc = hub.receive("t", m.message_id, ANSWER_KINDS, agent_id="physics-specialist", report_id="r1")
        finally:
            hub.close()
        stem = [c for c in rc.formal_checks if c.detail.startswith("stem_")]
        kinds = {SH._kind(c) for c in stem}
        assert {"stem_given", "stem_substitution", "stem_arithmetic", "stem_result", "stem_conversion", "stem_comparison"} <= kinds
        read = SH.budget_cut_checks(rc)
        if not cut:
            assert read == {} and SH._cut_statements(rc.findings) == {}
            continue
        assert read == {c.constraint_id: (SH._kind(c), "0") for c in stem}
        statements = SH._cut_statements(rc.findings)
        assert sum(len(v) for v in statements.values()) == len(stem)
        for c in stem:
            assert any(b == "0" for b, _t in statements[f"{SH._kind(c)} check{SH._where(c.claim_ids)}"])


@pytest.mark.parametrize("text,value", [(MODULE, float(bus.STEM_CHECK_BUDGET_S)), ("0", 0.0), ("4.29871", 4.29871), ("1e-05", 1e-05), ("8.0", None), (ABOVE, None), ("-1", None),
                                        ("nan", None), ("inf", None), ("", None), (None, None), ("1" * 40, None), ("08", None)])
def test_a_budget_is_read_only_as_the_channel_writes_one(text, value):
    assert SH._budget_value(text) == value


def test_a_detail_cut_at_the_contract_length_is_read_from_its_finding():
    """A check whose detail the channel cut at the contract length (``...``, the budget sentence lost) is read as cut by the
    INT-SUBJ-002 naming it; without that finding it is not read as cut."""
    head = "stem_arithmetic in claim s1.1: '" + "1 + " * 600
    detail = (head + "'; not run: the report's STEM check budget (8 s) was spent")[: bus._DETAIL_MAX - 3] + "..."
    cr = ConstraintResult(constraint_id="stem-eq-1", satisfied=None, method="formal", claim_ids=["s1.1"], detail=detail)
    f = IntegrityFinding(code="INT-SUBJ-002", severity="warning", claim_ids=["s1.1"], report_ids=["r1"],
                         message="stem_arithmetic check in claim s1.1 undecided (check budget: the report's STEM checks ran past 8 s; not run): " + "1 + " * 300)
    assert SH.budget_cut_checks(types.SimpleNamespace(formal_checks=[cr], findings=[f])) == {"stem-eq-1": ("stem_arithmetic", "8")}
    assert SH.budget_cut_checks(types.SimpleNamespace(formal_checks=[cr], findings=[])) == {}


@pytest.mark.parametrize("fill", [" ", "\t", "\n", ".", ")", "]", "(A1)", "(", "[", "```", "two and three and ", "= ", "- ",
                                  "; not run: the report's STEM check budget (", " undecided (check budget: the report's STEM checks ran past "])
def test_the_cut_reader_is_linear_on_hostile_journaled_text(fill):
    """The rule reads journaled receipt text with prefix and suffix tests, one search per message bounded after its marker and
    an anchored, bounded kind pattern: about 20,000 characters of each hostile run, followed by a character that defeats the
    match, in 200 checks and 200 findings, read well within the bound."""
    run = (fill * (20_000 // len(fill) + 1))[:20_000] + "\x00"
    checks = [types.SimpleNamespace(constraint_id=f"c{i}", satisfied=None, method="formal", formal_result_id=None, formal_status=None, claim_ids=["s1.1"],
                                    detail=f"stem_arithmetic in claim s1.1: {run}") for i in range(200)]
    msgs = [types.SimpleNamespace(code="INT-SUBJ-002", formal_result_id=None, severity="warning", claim_ids=["s1.1"], report_ids=["r1"],
                                  message=f"stem_arithmetic check in claim s1.1{run}") for _ in range(200)]
    receipt = types.SimpleNamespace(formal_checks=checks, findings=msgs)
    timing = measure(lambda: (SH.budget_cut_checks(receipt), SH._cut_statements(receipt.findings)), bound=2.0, repeat=3, label=f"budget-cut reader, {fill!r}")
    assert timing.holds, str(timing)
    assert all(r[0] == {} for r in timing.results)
