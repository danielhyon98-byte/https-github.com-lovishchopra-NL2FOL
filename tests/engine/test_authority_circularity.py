"""Issue 1 in the engine: only a check in this process confers authority, for circularity too. A premise that restates the
conclusion is the writer's own unless a check established it (``engine.authority.assumed_grounding`` is ``not
has_authority``), so "p, therefore p" with nothing but a source or task LABEL behind p is circular (E112) under every kind
that claims a source's or the task's authority, and a transcription only when a check verified the premise against the
supplied text or the task record. The pipeline's circularity refusal reads the same rule (policy 2026.10-v5)."""
from __future__ import annotations

import pytest

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.authority import assumed_grounding, dependency_policy, has_authority
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Grounding, Problem
from epinoic_logic.translate.contracts import SuppliedText, TaskRecord
from epinoic_logic.translate.grounding import check_problem_grounding

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
#: The kinds that claim a text's or the task's authority (every kind that is not the writer's own).
NON_WRITER_KINDS = ("quotation", "supplied_text", "knowledge_document", "library_source", "task_setting", "rubric_rule", "arithmetic_fact")
TEXT = SuppliedText(document_id="doc-1", title="Extract", author=None, text="Extract: The forces on the box are balanced.")
TASK = TaskRecord.of("t", "r", "A box rests on a table and the forces on the box are balanced. Explain whether it accelerates.")


def _p_proves_p(kind: str, refs: list[dict] | None = None, verified=None) -> Problem:
    grounding: dict = {"kind": kind, "certainty": "established"}
    if refs is not None:
        grounding["source_refs"] = refs
    if verified is not None:
        grounding["verified"] = verified
    return Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "balanced", "sort": "Bool", "meaning": "the forces on the box are balanced"}],
        "premises": [{"id": "P", "expr": {"op": "var", "name": "balanced"}, "label": "the forces on the box are balanced", "grounding": grounding}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "balanced"}, "label": "the forces are balanced"}})


def _codes(problem: Problem) -> list[str]:
    r = verify(problem, CFG)
    assert r.status is S.ENTAILED
    return [d.code for d in r.diagnostics]


@pytest.mark.parametrize("kind", NON_WRITER_KINDS)
def test_p_proves_p_with_only_a_label_is_circular_under_every_non_writer_kind(kind):
    label_only = _p_proves_p(kind)                         # in process: verified None, no check ran
    assert label_only.premises[0].grounding.verified is None
    assert assumed_grounding(label_only.premises[0].grounding)
    assert "E112" in _codes(label_only)
    grounded, _checks = check_problem_grounding(label_only, [], task=None)   # checking it with no record changes nothing
    assert grounded.premises[0].grounding.verified is not True and "E112" in _codes(grounded)


@pytest.mark.parametrize("kind", NON_WRITER_KINDS)
def test_the_same_premise_a_check_verified_is_a_transcription_not_a_circle(kind):
    excerpt = [{"document_id": "doc-1", "excerpt": "The forces on the box are balanced"}]
    grounded, checks = check_problem_grounding(_p_proves_p(kind, refs=excerpt), [TEXT], task=TASK)
    assert grounded.premises[0].grounding.verified is True, [(c.method, c.verified, c.detail) for c in checks if c.target_id == "P"]
    assert has_authority(grounded.premises[0].grounding) and not assumed_grounding(grounded.premises[0].grounding)
    assert "E112" not in _codes(grounded)


@pytest.mark.parametrize("kind", ("task_setting", "rubric_rule"))
def test_a_task_premise_the_task_record_states_is_a_transcription_and_label_only_is_a_circle(kind):
    task_excerpt = [{"document_id": "task", "excerpt": "the forces on the box are balanced"}]
    grounded, _checks = check_problem_grounding(_p_proves_p(kind, refs=task_excerpt), [], task=TASK)
    assert grounded.premises[0].grounding.verified is True and "E112" not in _codes(grounded)
    other = TaskRecord.of("t", "r", "A box rests on a table. Explain whether it accelerates.")
    grounded, _checks = check_problem_grounding(_p_proves_p(kind, refs=task_excerpt), [], task=other)
    assert grounded.premises[0].grounding.verified is not True and "E112" in _codes(grounded)


@pytest.mark.parametrize("kind", ("assumption", "specialist_inference", "general_knowledge"))
def test_the_writers_own_kinds_stay_circular(kind):
    assert "E112" in _codes(_p_proves_p(kind))


def test_a_refuted_premise_is_the_writers_own_and_a_premise_derived_from_others_is_no_circle():
    assert assumed_grounding(Grounding(kind="quotation", verified=False)) and assumed_grounding(None)
    derived = Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "a", "sort": "Bool"}, {"name": "b", "sort": "Bool"}],
        "premises": [{"id": "A", "expr": {"op": "var", "name": "a"}, "grounding": {"kind": "task_setting"}},
                     {"id": "L", "expr": {"op": "implies", "left": {"op": "var", "name": "a"}, "right": {"op": "var", "name": "b"}},
                      "grounding": {"kind": "specialist_inference"}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}}})
    assert "E112" not in _codes(derived)                    # nothing restates the point: no circle, whatever the labels


def test_the_policy_records_the_rule():
    policy = dependency_policy()
    assert policy["assumed_for_circularity"] == "not_established" and policy["authority"] == "verified-in-process-only"
