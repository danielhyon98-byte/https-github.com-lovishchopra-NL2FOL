"""Close round 2 of the argument-diagnosis regression review, REG-CIRC-TASK-PROPOSITION: a proposition the task quotes for
the student to weigh ("'X.' Discuss.", "X. To what extent do you agree?") was read as the task asserting X. A task_setting
premise restating X with no excerpt was validated by the stricter reading repair round 4 gave a premise that shares an atom
with the point (``content_in_task``), so 'X, as the question states; therefore X' (p proves p) cleared: no E112, no
ARG-CIRC-001, releasable. The committed base refuted that premise and the engine named the circle (E112). The task-fact
reading had been narrowed by close round 1, so under close round 2's convergence rule the point-sharing validation is
reverted for its whole class: a premise that shares an atom with the point is never validated by a task sentence and is left
to the circularity rules, as on the base. A task fact that grounds another point is validated as before.

Wording of this round's own; each positive was checked to fail on the tree before the round."""
from __future__ import annotations

import pytest

from epinoic_logic.engine.release import release_check
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import TaskRecord
from epinoic_logic.translate.grounding import check_problem_grounding

KEY = b"close2-task-proposition-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
X = "the Industrial Revolution improved the lives of most workers"


def _run(task_text: str, premise_meaning: str, point_meaning: str, *, kind: str = "task_setting"):
    same = premise_meaning == point_meaning
    symbols = [{"name": "p", "sort": "Bool", "meaning": premise_meaning}]
    if not same:
        symbols.append({"name": "q", "sort": "Bool", "meaning": point_meaning})
    premises = [{"id": "P", "expr": {"op": "var", "name": "p"}, "label": premise_meaning, "grounding": {"kind": kind, "certainty": "established"}}]
    if not same:
        premises.append({"id": "L", "expr": {"op": "implies", "left": {"op": "var", "name": "p"}, "right": {"op": "var", "name": "q"}},
                         "label": f"if {premise_meaning}, then {point_meaning}", "grounding": {"kind": "specialist_inference"}})
    problem = Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": symbols,
        "premises": premises, "conclusion": {"id": "C", "expr": {"op": "var", "name": "p" if same else "q"}, "label": point_meaning}})
    grounded, checks = check_problem_grounding(problem, [], task=TaskRecord.of("t", "r", task_text))
    result = verify(grounded, CFG, signing_key=KEY, key_id="k")
    release = release_check(result, grounded, signing_key=KEY, key_id="k")
    return grounded.premises[0].grounding.verified, result, release


PROMPTS = [
    f"'{X[0].upper() + X[1:]}.' Discuss. [15 marks]",
    f"{X[0].upper() + X[1:]}. To what extent do you agree? [15 marks]",
    f"{X[0].upper() + X[1:]}. How far do you agree with this view? [15 marks]",
    f"“{X[0].upper() + X[1:]}.” Evaluate this claim. [15 marks]",
]


@pytest.mark.parametrize("task_text", PROMPTS)
@pytest.mark.parametrize("kind", ["task_setting", "rubric_rule"])
def test_a_proposition_the_task_quotes_for_discussion_never_grounds_its_own_restatement(task_text, kind):
    verified, result, release = _run(task_text, X, X, kind=kind)
    assert verified is not True
    assert "E112" in [d.code for d in result.diagnostics]   # p proves p: the circle is named
    assert not release.eligible


def test_control_a_task_fact_that_grounds_another_point_is_validated():
    task = "Parliament repealed the Corn Laws. Explain one consequence of the repeal for the price of bread. [4 marks]"
    verified, result, _release = _run(task, "Parliament repealed the Corn Laws", "bread became cheaper in Britain")
    assert verified is True
    assert "E112" not in [d.code for d in result.diagnostics]


def test_control_a_reported_view_restated_as_the_point_stays_a_circle():
    verified, result, release = _run(f"Many historians say that {X}. Discuss. [15 marks]", X, X)
    assert verified is not True and "E112" in [d.code for d in result.diagnostics] and not release.eligible
