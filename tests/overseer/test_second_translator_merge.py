"""Regression tests for the second translator merge: the overseer build joined to the development translator, which had
meanwhile gained the engine's limits-bound result identity, the composer's release assessment, the synthesis self-report
rule (INT-LEDGER-029) and two closed vocabularies of its own (INT-SYNTH-014, INT-CONFLICT-006).

Each test fails on the merge as git first assembled it:

* the audit recomputed a result's binding digest without the limits digest the engine now binds, so every result decided
  under non-default limits (the STEM checks' nonlinear policy among them) was "internally inconsistent" (OVS-RES-004);
* the audit rebuilt an outcome's summary without the release assessment the composer now states, so every genuine
  summary was "not the deterministic statement" (OVS-TRN-007) and every genuine task failed its audit;
* the build's name-substitution error and the translator's self-report warning both used INT-LEDGER-029: the build's rule
  is INT-LEDGER-032 now, and the fixed-severity table holds both with their own severities;
* the merged translator validates a task-authority premise the supplied texts state (no located excerpt), and the overseer
  read that validation as a transcription, against decision 55 (``checks.translation._located_only``, decision 73);
* a synthesis relayed as the JSON the router receives was a report relay to the transfer auditor (OVS-AUDIT-001).
"""
from __future__ import annotations

import pytest

from epinoic_logic.engine.policies import NONLINEAR_LIMITS
from epinoic_logic.engine.provenance import binding_inconsistencies
from epinoic_logic.engine.runner import verify
from epinoic_logic.overseer.checks.receipts import FIXED_SEVERITY
from epinoic_logic.overseer.checks.results import binding_problems
from epinoic_logic.overseer.checks.translation import summary_matches

from .conftest import CFG, KEY, english_report, int_problem, make_auditor, make_keyring, outcome_for, ovs_errors, point_problem, run_task
from .test_c1_name_substitution import ASHLEY, _ashley_run, _auditor


# ============================================================================================ result bindings
@pytest.mark.parametrize("limits", [None, NONLINEAR_LIMITS])
def test_a_result_binds_to_its_problem_under_the_limits_it_was_decided_under(limits):
    p = int_problem("h1.1", "min_age", 9, op="ge", bound=9)
    res = verify(p, CFG, limits, signing_key=KEY, key_id="t") if limits is not None else verify(p, CFG, signing_key=KEY, key_id="t")
    assert binding_inconsistencies(res) == [] and binding_problems(res, p) == []


@pytest.mark.parametrize("forged", [None, "default"])
def test_a_limits_record_stripped_or_swapped_is_still_an_inconsistent_binding(forged):
    from epinoic_logic.ir.schema import DEFAULT_LIMITS
    p = int_problem("h1.1", "min_age", 9, op="ge", bound=9)
    res = verify(p, CFG, NONLINEAR_LIMITS, signing_key=KEY, key_id="t")
    edited = res.model_copy(update={"limits": None if forged is None else DEFAULT_LIMITS})
    assert "binding internally inconsistent" in binding_problems(edited, p)


# ============================================================================================ outcome summaries
def test_the_composers_summary_with_its_release_line_is_the_deterministic_statement():
    report = english_report()
    claim = next(c for c in report.claims if c.claim_id == "en-point")
    oc = outcome_for(claim, report, point_problem())
    assert oc.release is not None and "elease" in oc.summary
    assert summary_matches(oc, claim, oc.verification, make_keyring(), report=report)


@pytest.mark.parametrize("edit", ["release", "status", "tail"])
def test_an_edited_summary_is_still_not_the_deterministic_statement(edit):
    report = english_report()
    claim = next(c for c in report.claims if c.claim_id == "en-point")
    oc = outcome_for(claim, report, point_problem())
    lines = oc.summary.split("\n")
    if edit == "release":
        k = next(i for i, line in enumerate(lines) if "elease" in line)
        lines[k] = lines[k] + " Released."
    elif edit == "status":
        lines[0] = lines[0].replace("display status", "display status (checked)")
    else:
        lines.append("Verified by the overseer.")
    forged = oc.model_copy(update={"summary": "\n".join(lines)})
    assert not summary_matches(forged, claim, forged.verification, make_keyring(), report=report)


def test_a_genuine_task_on_the_merged_translator_raises_no_audit_error():
    a = make_auditor(shadow="off")
    try:
        task = run_task(a)
        audit = task.audit(final=True)
        assert ovs_errors(audit) == [], [(f.code, f.message[:160]) for f in ovs_errors(audit)]
        assert not [f for f in audit.report.findings if f.code in ("OVS-TRN-007", "OVS-RES-004")]
    finally:
        a.close()


# ============================================================================================ two ledger rules, two codes
def test_the_self_report_and_the_name_substitution_keep_their_own_codes_and_severities():
    assert FIXED_SEVERITY["INT-LEDGER-029"] == "warning" and FIXED_SEVERITY["INT-LEDGER-032"] == "error"
    a = _auditor(shadow="off")
    try:
        run = _ashley_run(a, ASHLEY.replace("Lord Ashley", "Robert Peel").rstrip(".") + " (verified).")
        got = {(f.code, f.severity) for f in run.receipts["syn"].findings if f.code in ("INT-LEDGER-029", "INT-LEDGER-032")}
        assert got == {("INT-LEDGER-029", "warning"), ("INT-LEDGER-032", "error")}, got
    finally:
        a.close()


# ============================================================================================ task-authority validation (decision 73)
def _hours(kind: str, excerpt=None) -> "object":
    from epinoic_logic.ir.schema import Problem
    g: dict = {"kind": kind}
    if excerpt is not None:
        g["source_refs"] = [{"document_id": "doc-hours", "excerpt": excerpt}]
    c = {"op": "eq", "left": {"op": "var", "name": "hours"}, "right": {"op": "int", "value": "12"}}
    return Problem.model_validate({"problem_id": "p-h", "request_id": "req-ovs", "claim_id": "en-point", "query": "entailment",
                                   "symbols": [{"name": "hours", "sort": "Int", "meaning": "the hours a day the children worked"}],
                                   "premises": [{"id": "P_hours", "expr": c, "label": "the children worked 12 hours a day", "grounding": g}],
                                   "conclusion": {"id": "C", "expr": c, "label": "the children worked 12 hours a day"}})



def _hours_report():
    """A report that states the figure itself, with a supplied text that states it too."""
    from epinoic_logic.translate.contracts import SuppliedText
    from .conftest import EN_TEXT
    doc = SuppliedText(document_id="doc-hours", title="Mill hours", author="Anonymous", text="In 1830 the children worked 12 hours a day in the mill.")
    return english_report(EN_TEXT + " The children worked 12 hours a day.", docs=(doc,))


@pytest.mark.parametrize("kind", ["task_setting", "arithmetic_fact", "rubric_rule"])
def test_a_task_authority_premise_the_translator_validates_with_no_excerpt_is_no_transcription_for_the_overseer(kind):
    from epinoic_logic.overseer.checks.translation import TRANSCRIPTION, _regrounded, restatement
    from epinoic_logic.translate.grounding import check_problem_grounding
    rep = _hours_report()
    prob = _hours(kind)
    translator, checks = check_problem_grounding(prob, list(rep.supplied_texts))
    assert translator.premises[0].grounding.verified is True and [c.method for c in checks if c.target_id == "P_hours"] == ["numeric_in_task"]
    assert _regrounded(prob, rep).premises[0].grounding.verified is None  # no located excerpt: a number match is no evidence
    rs = restatement(prob, rep, ["Write about the hours: 12 hours a day."])
    assert rs.holds and rs.own == ("P_hours",) and all(kind_ != TRANSCRIPTION for _pid, kind_ in rs.standings)
    assert rs.translator_holds is False  # the translator's own decision, on its own grounding: it delivers the encoding


@pytest.mark.parametrize("kind", ["task_setting", "arithmetic_fact"])
def test_control_a_located_excerpt_stating_the_figure_is_still_a_transcription(kind):
    from epinoic_logic.overseer.checks.translation import _regrounded, restatement
    rep = _hours_report()
    prob = _hours(kind, excerpt="worked 12 hours a day")
    assert _regrounded(prob, rep).premises[0].grounding.verified is True
    rs = restatement(prob, rep, ["Write about the hours: 12 hours a day."])
    assert not rs.holds and rs.grounded == ("P_hours",) and rs.standings == (("P_hours", "transcription"),)


# ============================================================================================ relay events
@pytest.mark.parametrize("payload, kind", [({"synthesis_id": "syn-1", "claims": []}, "relay_synthesis"), ({"report_id": "rep-1"}, "relay_report")])
def test_a_synthesis_relayed_as_json_is_a_synthesis_event(payload, kind):
    from epinoic_logic.channel.events import event_kind
    assert event_kind("relay", (), {"from_role": "combinator", "payload_obj": payload}) == kind
    assert event_kind("relay", (), {"from_role": "router", "payload_obj": {"report_id": "rep-1"}}) == "relay_forward"  # control
