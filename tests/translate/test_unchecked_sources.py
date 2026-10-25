"""Issue 1 at the claim layer: a premise whose only support is a source label that no check verified is named
``unchecked_source`` (EVD-SRC-001), a provider's own ``verified: true`` is recorded where it was written and named
(EVD-SRC-004, with the translation diagnostic E505), and a figureless task premise is unvalidated, never refuted (so the
true task facts of c02-mt and c03-dich give no GROUNDING:FAILED). Cases from the development set (argdiag-1)."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import TaskRecord
from epinoic_logic.translate.diag_evidence import source_bound
from epinoic_logic.translate.grounding import check_problem_grounding
from epinoic_logic.translate.parsing import MAX_ASSERTED_PATHS, asserted_verified_paths

from ..evidence_support import assert_message_hygiene, blocking, deliver, diagnostics, failed_groundings, outcome


# ------------------------------------------------------------------------------------------------------- positives

@pytest.mark.parametrize("case_id, claim_id, premise", [("e04a_source_mismatch_paraphrase", "h2", "P_accept"),
                                                        ("e08b_self_certified_premise_provider", "h2", "P_object")])
def test_a_label_only_source_premise_is_named_unchecked_source_at_warning_in_a_source_bound_task(case_id, claim_id, premise):
    case, rc = deliver(case_id, "report")
    assert source_bound(case["request"])                    # "What does Source A suggest ..."
    [d] = [d for d in diagnostics(rc, "EVD-SRC-001") if claim_id in d.claim_ids]
    assert d.defect == "unchecked_source" and d.severity == "warning" and d.capped_from is None
    assert premise in d.assertion_ids and d.derivation == "grounding_record"
    o = outcome(rc, claim_id)
    assert not o.release.permitted                          # a diagnostic only ever makes a result less releasable
    assert_message_hygiene([d])


def test_the_providers_own_verified_flag_is_recorded_named_and_discarded():
    _case, rc = deliver("e08b_self_certified_premise_provider", "report")
    o = outcome(rc, "h2")
    assert o.translation.asserted_verified == ["problem.symbols[0].grounding", "problem.premises[0].grounding"]
    assert any(d.startswith("E505: the translation asserted verified=true at problem.premises[0].grounding; discarded") for d in o.translation.diagnostics)
    [d] = [d for d in diagnostics(rc, "EVD-SRC-004") if "h2" in d.claim_ids]
    assert d.severity == "info" and d.defect == "unchecked_source" and d.assertion_ids == ["P_object"]
    premise = next(p for p in o.translation.problem.premises if p.id == "P_object")
    assert premise.grounding.verified is not True          # only a check sets it; no check verified this one
    assert_message_hygiene([d])


# ------------------------------------------------------------------------------------------------------- controls

@pytest.mark.parametrize("case_id", ["c02_modus_tollens", "c03_true_dichotomy"])
def test_true_task_facts_are_unvalidated_not_refuted_and_give_no_evidence_warning(case_id):
    case, rc = deliver(case_id, "text")
    assert not source_bound(case["request"])
    assert failed_groundings(rc) == []                      # no GROUNDING:FAILED: a figureless task premise is never refuted
    evd = diagnostics(rc, prefix="EVD-")
    assert blocking(evd) == []                              # info only: the task is not source-bound
    assert all(d.capped_from in (None, "warning") for d in evd)


def test_a_proposal_without_a_verified_flag_gives_no_evd_src_004():
    _case, rc = deliver("e04a_source_mismatch_paraphrase", "report")
    assert diagnostics(rc, "EVD-SRC-004") == []
    assert all(o.translation.asserted_verified == [] for o in rc.outcomes)


# ------------------------------------------------------------------------------------------------------- the recorder

def test_asserted_verified_paths_reports_only_true_flags_on_groundings():
    obj = {"problem": {"symbols": [{"name": "p", "grounding": {"kind": "supplied_text", "verified": True}}],
                       "premises": [{"id": "P", "grounding": {"kind": "quotation", "verified": False}},
                                    {"id": "Q", "grounding": {"kind": "quotation", "verified": None}},
                                    {"id": "R", "grounding": {"kind": "task_setting", "verified": True}, "verified": True}],
                       "conclusion": {"id": "C", "grounding": {"verified": "true"}}},
           "glossary": [{"symbol": "p", "grounding": {"verified": True}}]}
    # a string "true", a top-level flag outside a grounding, False and None claim no authority and are not reported
    assert asserted_verified_paths(obj) == ["problem.symbols[0].grounding", "problem.premises[2].grounding", "glossary[0].grounding"]
    assert asserted_verified_paths({"problem": None}) == [] and asserted_verified_paths([]) == []


def test_asserted_verified_paths_is_bounded():
    obj = {"problem": {"premises": [{"id": f"P{i}", "grounding": {"verified": True}} for i in range(MAX_ASSERTED_PATHS + 50)]}}
    assert len(asserted_verified_paths(obj)) == MAX_ASSERTED_PATHS


def test_a_figureless_task_premise_with_no_excerpt_is_unvalidated_and_a_conflicting_figure_still_refutes():
    """Rewritten rule (policy 2026.10-v5): with no excerpt and no figure no record was checked, so the check records
    ``verified=None`` ("no excerpt and no figure"), never a refutation. A stated figure the task contradicts is still
    refuted."""
    task = TaskRecord.of("t", "r", "A box rests on a table and the forces on it are balanced. Its mass is 2 kg.")
    problem = Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "balanced", "sort": "Bool"}, {"name": "m", "sort": "Real", "meaning": "the box's mass (kg)"}],
        "premises": [{"id": "B", "expr": {"op": "var", "name": "balanced"}, "grounding": {"kind": "task_setting"}},
                     {"id": "M", "expr": {"op": "eq", "left": {"op": "var", "name": "m"}, "right": {"op": "real", "value": "3"}},
                      "grounding": {"kind": "task_setting"}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "balanced"}}})
    grounded, checks = check_problem_grounding(problem, [], task=task)
    by_id = {p.id: p.grounding.verified for p in grounded.premises}
    assert by_id == {"B": None, "M": False}
    [b] = [c for c in checks if c.target_id == "B"]
    assert b.verified is None and "no excerpt and no figure" in b.detail and "no record was checked" in b.detail


def test_the_provider_text_is_recorded_from_json_only():
    # the recorder walks the parsed object; nothing in the text is evaluated
    text = json.dumps({"problem": {"premises": [{"id": "P", "grounding": {"kind": "quotation", "verified": True, "note": "__import__('os')"}}]}})
    assert asserted_verified_paths(json.loads(text)) == ["problem.premises[0].grounding"]
