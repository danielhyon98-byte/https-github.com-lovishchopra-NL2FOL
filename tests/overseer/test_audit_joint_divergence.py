"""The cross-agent pool as journaled (JOINT-004), undecidable joint checks (JOINT-002), and B4 rule divergence with its
classification and exclusions (DIV-001, DIV-002, T18)."""
from __future__ import annotations

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.integrity import SynthesizedClaim
from epinoic_logic.ir.schema import Assertion, Problem

from .conftest import (
    DOC, EN_INPUT, HI_TEXT, default_synthesis, english_report, findings, int_problem, make_plan, new_channel, ovs_errors, problems_fn, run_task,
)


def _real_problem(claim_id: str, symbol: str, value: str) -> Problem:
    V = {"op": "var", "name": symbol}
    return Problem.model_validate({
        "problem_id": f"p-{claim_id}", "request_id": "req-ovs", "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": symbol, "sort": "Real", "meaning": f"the {symbol} the claim states"}],
        "premises": [{"id": "GIVEN", "expr": {"op": "eq", "left": V, "right": {"op": "real", "value": value}}, "grounding": {"kind": "arithmetic_fact"}}],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": V, "right": {"op": "real", "value": "0"}}},
    })


def _two_responses(auditor, en_problem, hi_problem, between=None):
    ch = new_channel(auditor)
    ch.channel.verify_claim_fn = problems_fn({"en-point": en_problem})
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc1 = ch.respond(m.message_id, english_report())
    if between is not None:
        between(ch)
    ch.channel.verify_claim_fn = problems_fn({"h1.1": hi_problem})
    m2, _r2, rq2 = ch.request("router", "history-specialist", "Explain the Factory Act of 1833.", [])
    _msg2, rc2 = ch.respond_text(m2.message_id, HI_TEXT, agent_id="history-specialist", report_id="rep-hi-1")
    return ch, rc1, rq2, rc2


# ------------------------------------------------------------------------------------------- JOINT-004
def test_t19_a_pooled_claim_popped_between_transfers_is_joint_004(auditor):
    ch, rc1, rq2, _rc2 = _two_responses(auditor, int_problem("en-point", "x", 7, op="gt", bound=5), int_problem("h1.1", "x", 2, op="lt", bound=3),
                                        between=lambda ch: ch.channel.formalized.pop("en-point"))
    audit = auditor.audit(ch.uid)
    f = findings(audit, "OVS-JOINT-004")
    assert f and f[0].claim_ids == ["en-point"] and rq2.message_id in f[0].message_ids and rc1.message_id in f[0].message_ids
    # the contradiction the channel could no longer see: the shadow channel, fed the journaled inputs, raises it
    f4 = [x for x in findings(audit, "OVS-RCPT-004") if "INT-CONFLICT-001" in x.message]
    assert f4 and sorted(f4[0].claim_ids) == ["en-point", "h1.1"] and f4[0].message_ids == [_rc2.message_id]


def test_a_pooled_problem_other_than_the_outcomes_is_joint_004(auditor, monkeypatch):
    orig = TranslatorChannel._verify_claims

    def swap(self, report, findings_, **kw):
        out = orig(self, report, findings_, **kw)
        if "en-point" in self.formalized:
            self.formalized["en-point"] = int_problem("en-point", "work_hours", 3, op="gt", bound=8)
        return out
    monkeypatch.setattr(TranslatorChannel, "_verify_claims", swap)
    ch = new_channel(auditor)
    ch.channel.verify_claim_fn = problems_fn({"en-point": int_problem("en-point", "work_hours", 12, op="gt", bound=8)})
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, english_report())
    f = findings(auditor.audit(ch.uid), "OVS-JOINT-004")
    assert f and f[0].claim_ids == ["en-point"] and f[0].message_ids == [rc.message_id] and "no outcome" in f[0].message


def test_the_live_pool_changed_after_the_last_transfer_is_joint_004_at_clearance(auditor):
    task = run_task(auditor, synthesis=False)
    task.ch.channel.formalized.pop("h1.1")
    clr = auditor.clearance(task.uid, task.mids["rep_hi"])
    assert "OVS-JOINT-004" in clr.codes and clr.state == "AUDIT_FAILED"


def test_control_pool_unchanged_gives_no_joint_finding(auditor):
    task = run_task(auditor)
    assert not [f for f in task.audit().report.findings if f.code.startswith("OVS-JOINT")]


# ------------------------------------------------------------------------------------------- JOINT-002
def test_a_joint_check_that_cannot_be_built_is_joint_002(auditor):
    ch, _rc1, _rq2, rc2 = _two_responses(auditor, int_problem("en-point", "x", 7, op="gt", bound=5), _real_problem("h1.1", "x", "2.5"))
    assert any(f.code == "INT-GLOSSARY-001" for f in rc2.findings)  # the channel names the sort clash
    audit = auditor.audit(ch.uid)
    f = findings(audit, "OVS-JOINT-002")
    assert f and f[0].severity == "warning" and "INT-GLOSSARY-001" in f[0].message
    assert not findings(audit, "OVS-JOINT-001")


# ------------------------------------------------------------------------------------------- B4, T18
def _merged_synthesis(with_conclusion: bool = False, created_at=None):
    concl = Assertion.model_validate({"id": "S", "expr": {"op": "gt", "left": {"op": "var", "name": "work_hours"}, "right": {"op": "int", "value": "8"}}}) if with_conclusion else None
    claims = [SynthesizedClaim(claim_id="s1", text="The writer presents work as endless; the Factory Act of 1833 banned the employment of children under nine in textile mills.",
                               source_claim_ids=["en-point", "h1.1"], transformation="merged", formal_conclusion=concl),
              SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"], transformation="carried")]
    return default_synthesis(claims=claims, created_at=created_at)


def test_t18_a_merged_material_claim_without_a_formal_conclusion_is_div_001_rule_ownership(auditor):
    task = run_task(auditor, synthesis_obj=_merged_synthesis())
    audit = task.audit()
    f = [x for x in findings(audit, "OVS-DIV-001") if "INT-SYNTH-006" in x.message]
    assert f and f[0].severity == "error" and "s1" in f[0].claim_ids and task.mids["syn"] in f[0].message_ids
    d = [x for x in audit.divergences if x.int_code == "INT-SYNTH-006"]
    assert d and d[0].classification == "rule_ownership" and d[0].owner == "integrity" and d[0].severity == "error"
    assert audit.transfer_states[task.mids["syn"]] == "AUDIT_FAILED"  # the router must not act on what the Overseer's rules reject


def test_t18_int_synth_006_is_excluded_when_the_receipt_shows_the_check_was_performed(auditor):
    task = run_task(auditor, synthesis_obj=_merged_synthesis(with_conclusion=True))
    assert any(f.code == "INT-LEDGER-011" and f.formal_result_id for f in task.receipts["syn"].findings)
    audit = task.audit()
    assert not [x for x in audit.divergences if x.int_code == "INT-SYNTH-006"]


def test_t18_a_harness_clock_before_the_reports_is_div_002_time_dependent(auditor):
    task = run_task(auditor, synthesis_obj=default_synthesis(created_at="2020-01-01T00:00:00Z"))
    audit = task.audit()
    f = [x for x in findings(audit, "OVS-DIV-002") if "INT-HANDOFF-016" in x.message]
    assert f and f[0].severity == "warning"
    d = [x for x in audit.divergences if x.int_code == "INT-HANDOFF-016"]
    assert d and d[0].classification == "time_dependent" and d[0].owner == "harness"
    assert not ovs_errors(audit, allow=())


def test_the_combinator_is_not_a_missing_report_and_a_missing_specialist_is(auditor):
    task = run_task(auditor)
    assert not task.audit().divergences  # the combinator sent a synthesis and no report: removed from the plan
    plan = make_plan(selected_agent_ids=["english-specialist", "history-specialist", "combinator", "physics-specialist"])
    task2 = run_task(auditor, plan=plan)
    d = [x for x in task2.audit().divergences if x.int_code == "INT-HANDOFF-007"]
    assert d and "physics-specialist" in d[0].message and d[0].classification == "rule_ownership"
    task3 = run_task(auditor, plan=plan, synthesis=False)
    assert not [x for x in task3.audit().divergences if x.int_code == "INT-HANDOFF-007"]  # nothing to diverge from before a synthesis
