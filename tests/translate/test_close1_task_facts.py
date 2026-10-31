"""Close round 1, INV7-1: a figureless task_setting premise that cites no excerpt is validated by a task sentence that states
it (repair round 2), but the "all but one of four or more" allowance of that reading let a premise that differs from the
sentence only by its time ("next year", "this year" for "last year"), its tense ("will raise" for "raised") or the direction
of its change ("cut" for "raised") be validated, and left the contradicting "cut" unvalidated where it was refuted before.
Such a premise is now refuted (``content_in_task`` False: the task material does not state it), and the stated fact, and a
paraphrase of it in the same time, tense and direction, are still validated. Wording of this round's own."""
from __future__ import annotations

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import TaskRecord
from epinoic_logic.translate.grounding import check_problem_grounding

TASK = "The regional council of Westmere raised parking charges steeply last year. Discuss the likely effect on town-centre trade."


def _verified(meaning: str, task_text: str = TASK):
    problem = Problem.model_validate({
        "request_id": "r", "claim_id": "c", "problem_id": "p", "query": "entailment",
        "symbols": [{"name": "a", "sort": "Bool", "meaning": meaning}, {"name": "b", "sort": "Bool", "meaning": "town-centre trade fell"}],
        "premises": [{"id": "P1", "expr": {"op": "var", "name": "a"}, "label": "the given fact", "grounding": {"kind": "task_setting"}},
                     {"id": "P2", "expr": {"op": "implies", "left": {"op": "var", "name": "a"}, "right": {"op": "var", "name": "b"}},
                      "label": "link", "grounding": {"kind": "assumption"}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}, "label": "So town-centre trade fell."}})
    grounded, checks = check_problem_grounding(problem, [], task=TaskRecord.of("t", "r", task_text))
    p1 = next(p for p in grounded.premises if p.id == "P1")
    return p1.grounding.verified, [c for c in checks if c.target_id == "P1"]


@pytest.mark.parametrize("meaning, why", [
    ("the regional council of Westmere raised parking charges steeply this year", "this year"),
    ("the regional council of Westmere will raise parking charges steeply next year", "next year"),
    ("the regional council of Westmere will raise parking charges steeply", "future"),
    ("the regional council of Westmere cut parking charges steeply last year", "a fall"),
    ("the regional council of Westmere reduced parking charges steeply last year", "a fall"),
])
def test_a_premise_with_another_time_tense_or_direction_is_refuted(meaning, why):
    verified, checks = _verified(meaning)
    assert verified is False
    [check] = [c for c in checks if c.method == "content_in_task"]
    assert check.verified is False and why in check.detail and "does not state it" in check.detail


@pytest.mark.parametrize("meaning", [
    "the regional council of Westmere raised parking charges steeply last year",
    "Westmere's regional council raised parking charges steeply last year",
])
def test_control_the_stated_fact_and_its_paraphrase_are_validated(meaning):
    verified, checks = _verified(meaning)
    assert verified is True and [c.method for c in checks] == ["content_in_task"]


@pytest.mark.parametrize("meaning", [
    "the regional council of Westmere raised parking charges steeply in the past year",
    "the regional council of Westmere raised parking charges steeply in the previous year",
])
def test_control_a_deictic_that_points_to_the_same_time_is_no_conflict(meaning):
    # "the past year" and "the previous year" point where "last year" does: no conflict, so never refuted (the ordered
    # reading leaves the other word unvalidated, as before the round)
    verified, checks = _verified(meaning)
    assert verified is not False and not [c for c in checks if c.verified is False]


def test_control_a_change_in_the_same_direction_in_other_words_is_never_refuted():
    # "increased" for "raised": no conflict of direction, so no refutation (the ordered reading leaves it unvalidated)
    verified, _checks = _verified("the regional council of Westmere increased parking charges steeply last year")
    assert verified is not False


def test_control_a_planned_change_the_task_states_in_the_future_is_validated():
    task = "The regional council of Westmere will raise parking charges next year. Discuss the likely effect on town-centre trade."
    verified, _checks = _verified("the regional council of Westmere will raise parking charges next year", task)
    assert verified is True


def test_control_a_fall_the_task_states_is_validated_and_a_rise_refuted():
    task = "The regional council of Westmere cut parking charges last year. Discuss the likely effect on town-centre trade."
    assert _verified("the regional council of Westmere cut parking charges last year", task)[0] is True
    assert _verified("the regional council of Westmere raised parking charges last year", task)[0] is False


def test_control_a_sentence_that_dates_two_times_states_each_of_them():
    task = ("The regional council of Westmere raised parking charges last year and will raise them again next year. Discuss the "
            "likely effect on town-centre trade.")
    assert _verified("the regional council of Westmere will raise parking charges again next year", task)[0] is not False
    assert _verified("the regional council of Westmere raised parking charges last year", task)[0] is True
