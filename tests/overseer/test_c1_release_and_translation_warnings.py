"""Regression tests for the contained round c1 judges' minor findings that the infrastructure decides (each fails on
the code before the fix):

* a FINAL audit whose replays ran inline carried only an OVS-AUDIT-002 warning, so ``may_release`` released on it
  (decision 20: process mode is the only mode a FINAL audit accepts as independent). It is refused now, unless the
  operator configured inline release on the auditor, which the signed audit records;
* a thesis displayed ENTAILED whose premises assert supporting claims that are themselves not successful in the same
  receipt raised nothing (OVS-TRN-008, rule ``sibling-status``);
* a from-memory fact asserted as a premise in one translation and left unsupported in the check of the claim that
  states it raised nothing (OVS-TRN-009, rule ``same-fact-premise``; the recorded round r4 p3 pattern).
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.overseer.audit import INLINE_FINAL_MESSAGE, verify_audit  # noqa: E402
from epinoic_logic.overseer.checks.translation import same_fact_inconsistencies, sibling_status_faults  # noqa: E402
from epinoic_logic.overseer.policy import release_decision  # noqa: E402


def _release(run, audit):
    a = run.auditor
    return release_decision(run.receipts["syn"], audit, a.keyring, audits=a.audits(run.uid), journal=a.journal(run.uid), message=run.messages.get("syn"))


# ============================================================================================ inline FINAL audits
def test_a_final_audit_whose_replays_ran_inline_is_not_released_unless_inline_release_was_configured():
    a = H.new_auditor(H.keyring_for("synthetic"), shadow="off", inline_final_release=False)
    try:
        run = T.run_synthetic(a)
        audit = run.audit(final=True)
        assert any(f.code == "OVS-AUDIT-002" and f.message == INLINE_FINAL_MESSAGE for f in audit.report.findings)
        assert audit.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS") and audit.coverage.inline_final_release is None
        d = _release(run, audit)
        assert not d.allowed and "OVS-AUDIT-002" in d.reason and "inline" in d.reason
    finally:
        a.close()
    b = H.new_auditor(H.keyring_for("synthetic"), shadow="off")  # the harness configures inline release explicitly
    try:
        run = T.run_synthetic(b)
        audit = run.audit(final=True)
        assert audit.coverage.inline_final_release is True and verify_audit(audit, b.keyring)
        assert _release(run, audit).allowed
        # the configuration is part of what the audit key signs: it cannot be added to an audit afterwards
        forged = audit.model_copy(update={"coverage": audit.coverage.model_copy(update={"inline_final_release": None})})
        assert not verify_audit(forged, b.keyring)
    finally:
        b.close()


def test_a_non_final_audit_never_carries_the_inline_warning():
    a = H.new_auditor(H.keyring_for("synthetic"), shadow="off", inline_final_release=False)
    try:
        run = T.run_synthetic(a)
        audit = run.audit()
        assert not any(f.message == INLINE_FINAL_MESSAGE for f in audit.report.findings)
    finally:
        a.close()


# ============================================================================================ OVS-TRN-008 / OVS-TRN-009
def _var(n):
    return {"op": "var", "name": n}


#: The recorded round r4 p3 History report's pattern (symbol meanings and premise labels verbatim): h1.2 asserts the
#: lull as a premise; h1.7's own check leaves it an unsupported conjunct.
R4_H12 = {"symbols": [{"name": "h17_lull", "sort": "Bool", "meaning": "the peace was a lull rather than a settlement"},
                      {"name": "largest_city_europe", "sort": "Bool", "meaning": "London in 1802 was the largest city in Europe"}],
          "premises": [{"id": "pr_h17_lull", "expr": _var("h17_lull"), "label": "the peace was a lull rather than a settlement"}],
          "conclusion": {"id": "C", "expr": _var("largest_city_europe")}}
R4_H17 = {"symbols": [{"name": "lull_not_settlement", "sort": "Bool", "meaning": "the peace was a lull rather than a settlement"},
                      {"name": "war_resumed_may1803", "sort": "Bool", "meaning": "war resumed in May 1803"}],
          "premises": [{"id": "pr_war_resumed_may1803", "expr": _var("war_resumed_may1803"), "label": "war resumed in May 1803"}],
          "conclusion": {"id": "C", "expr": {"op": "and", "args": [_var("lull_not_settlement"), _var("war_resumed_may1803")]}}}


def test_a_fact_asserted_in_one_translation_and_unsupported_in_another_is_trn009():
    assert same_fact_inconsistencies([("h1.2", R4_H12), ("h1.7", R4_H17)]) == [("h1.2", "pr_h17_lull", "h1.7", "lull_not_settlement")]
    # the claim's own fact supported by its own premise: nothing to report
    fixed = dict(R4_H17, premises=R4_H17["premises"] + [{"id": "pr_lull", "expr": _var("lull_not_settlement")}])
    assert same_fact_inconsistencies([("h1.2", R4_H12), ("h1.7", fixed)]) == []
    # an unrelated premise (other words) is not the same fact
    other = dict(R4_H12, symbols=[{"name": "h17_lull", "sort": "Bool", "meaning": "the city grew rich on coal"}] + R4_H12["symbols"][1:],
                 premises=[{"id": "pr_h17_lull", "expr": _var("h17_lull"), "label": "the city grew rich on coal"}])
    assert same_fact_inconsistencies([("h1.2", other), ("h1.7", R4_H17)]) == []
    # one problem alone is never inconsistent with itself
    assert same_fact_inconsistencies([("h1.7", R4_H17)]) == []


class _O:
    def __init__(self, status, problem):
        self.display_status = type("S", (), {"value": status})()
        self.translation = type("Tr", (), {"problem": problem})()


class _C:
    def __init__(self, cid, sup=()):
        self.claim_id, self.supporting_claim_ids = cid, list(sup)


class _P:
    def __init__(self, premises):
        self.premises = [type("Pr", (), {"id": i, "label": lab})() for i, lab in premises]


def test_a_definitive_display_resting_on_unsuccessful_sibling_claims_is_trn008():
    thesis = _P([("pr_sub_p2_point", "(specialist claim) p2-point"), ("pr_sub_p3_point", None)])
    outs = [(_O("ENTAILED", thesis), _C("p1-s01", ["p2-point", "p3-point", "p4-point"])),
            (_O("AMBIGUOUS_TRANSLATION", _P([])), _C("p2-point")), (_O("COUNTEREXAMPLE", _P([])), _C("p3-point")),
            (_O("COUNTEREXAMPLE", _P([])), _C("p4-point"))]
    # p4-point is cited but no premise asserts it: only the asserted siblings count
    assert sibling_status_faults(outs) == [("p1-s01", [("p2-point", "AMBIGUOUS_TRANSLATION"), ("p3-point", "COUNTEREXAMPLE")])]
    ok = [(_O("ENTAILED", thesis), _C("p1-s01", ["p2-point", "p3-point"])), (_O("ENTAILED", _P([])), _C("p2-point")),
          (_O("NOT_ELIGIBLE", None), _C("p3-point"))]
    assert sibling_status_faults(ok) == []  # siblings established, or never checked (NOT_ELIGIBLE)
    shown_false = [(_O("COUNTEREXAMPLE", thesis), _C("p1-s01", ["p2-point"])), (_O("COUNTEREXAMPLE", _P([])), _C("p2-point"))]
    assert sibling_status_faults(shown_false) == []  # no definitive display to rest on anything


def test_trn008_and_trn009_reach_the_audit_as_warnings_on_the_synthetic_task():
    """The thesis-and-points shape on the synthetic task: en-point (displayed ENTAILED) asserts en-an through a premise
    naming it, while en-an's own check leaves its fact unsupported (COUNTEREXAMPLE)."""
    from epinoic_logic.ir.schema import Problem
    point = T.point_problem()
    point["premises"].append({"id": "pr_sub_en_an", "expr": _var("paid_in_fuel"), "label": "time itself is paid in fuel (specialist claim en-an)"})
    point["symbols"].append({"name": "paid_in_fuel", "sort": "Bool", "meaning": "time itself is paid in fuel, the children's hours counted in coal"})
    an = {"problem_id": "p-en-an", "request_id": "req-tamper", "claim_id": "en-an", "query": "entailment",
          "symbols": [{"name": "coal", "sort": "Bool", "meaning": "the children count the hours in coal"},
                      {"name": "fuel_time", "sort": "Bool", "meaning": "time itself is paid in fuel, the children's hours counted in coal"}],
          "premises": [{"id": "P_coal", "expr": _var("coal"), "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc-mill", "excerpt": "counted every hour in coal"}]}}],
          "conclusion": {"id": "C", "expr": {"op": "and", "args": [_var("coal"), _var("fuel_time")]}}}
    a = H.new_auditor(H.keyring_for("synthetic"), shadow="off")
    try:
        run = T.run_synthetic(a, problems={"en-point": Problem.model_validate(point), "en-an": Problem.model_validate(an), "h1.1": T.P_HI})
        shown = {o.claim_id: o.display_status.value for o in run.receipts["rep_en"].outcomes}
        assert shown["en-point"] == "ENTAILED" and shown["en-an"] == "COUNTEREXAMPLE"
        audit = run.audit()
        f8 = [f for f in audit.report.findings if f.code == "OVS-TRN-008"]
        f9 = [f for f in audit.report.findings if f.code == "OVS-TRN-009"]
        assert f8 and f8[0].severity == "warning" and f8[0].claim_ids == ["en-point", "en-an"]
        assert f9 and f9[0].severity == "warning" and set(f9[0].claim_ids) == {"en-point", "en-an"}
        assert audit.transfer_states[run.mids["rep_en"]] == "AUDIT_PASSED_WITH_FINDINGS"  # warnings: never a failure
    finally:
        a.close()
