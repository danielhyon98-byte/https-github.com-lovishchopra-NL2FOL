"""B23: a figure the REQUEST states as a given (the student's own 1,800 cakes), cited as a quotation of a supplied document
that does not hold it, is re-checked against the task record and verified as task material ("stated by the request, cited
as doc-luma"), never refuted: whether the excerpt is located in the cited document and lacks the figure, or is the
request's own words cited as the document's. It verifies only where the request states it as a given: never inside a
question (the e2e request's "I got 1,800 cakes but my friend got 3,000, which one is right??" is one sentence that ends
in "?"), a condition, a negation or an answer requirement; a figure no record states, and words no record holds, still
fail. "9%" grounds 0.09 through the per-cent derivation, and the e2e case's relation p_student is unverified, not
refuted."""
from __future__ import annotations

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import TaskRecord
from epinoic_logic.translate.grounding import check_problem_grounding

from .. import argdiag_cases as C
from ..evidence_support import blocking, deliver, diagnostics, failed_groundings

CASE = C.load_case("e2e-B23-bm")
DOCS = C.supplied_texts(CASE)
TASK = C.task_record(CASE)
#: The e2e request with its last line written as statements and a separate question.
STATED = TaskRecord.of(TASK.task_id, TASK.request_id, TASK.text.replace(
    "For (b) I got 1,800 cakes but my friend got 3,000, which one is right??",
    "For (b) I got 1,800 cakes. My friend got 3,000. Which one is right?"))
STUDENT = "the student's figure of 1,800 cakes"


def _premise(symbol: str, meaning: str, value: str, excerpt: str) -> Problem:
    return Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": symbol, "sort": "Real", "meaning": meaning}],
        "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": symbol}, "right": {"op": "real", "value": value}},
                      "label": meaning, "grounding": {"kind": "quotation", "certainty": "established",
                                                      "source_refs": [{"document_id": "doc-luma", "excerpt": excerpt}]}}],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": symbol}, "right": {"op": "real", "value": "0"}}}})


def _check(problem: Problem, task: TaskRecord | None = TASK):
    grounded, checks = check_problem_grounding(problem, DOCS, task=task)
    return grounded.premises[0].grounding.verified, [c for c in checks if c.target_id == "P"]


def test_the_students_own_words_cited_to_the_case_study_are_the_requests_given():
    assert "1,800" in STATED.text and "1,800" not in DOCS[0].text
    verified, checks = _check(_premise("student_fig", STUDENT, "1800", "1,800 cakes"), STATED)
    assert verified is True
    [request] = [c for c in checks if c.method == "numeric_in_task"]
    assert request.verified is True and "stated by the request, cited as doc-luma" in request.detail
    assert not [c for c in checks if c.verified is False]           # the excerpt is an imprecise reference, not a refutation
    [ref] = [c for c in checks if c.ref_index == 0]
    assert ref.verified is None and "the request's words" in ref.detail
    assert _check(_premise("student_fig", STUDENT, "1800", "1,800 cakes"), None)[0] is False   # no task record: refuted as before


def test_a_located_excerpt_that_lacks_the_requests_figure_is_re_checked_against_the_request():
    excerpt = "She sells each cake for $4.50"
    assert excerpt in DOCS[0].text
    verified, checks = _check(_premise("student_fig", STUDENT, "1800", excerpt), STATED)
    assert verified is True and [c for c in checks if c.method == "numeric_in_task" and c.verified is True]


def test_the_e2e_request_asks_about_the_figure_in_one_question_so_it_is_no_given():
    verified, checks = _check(_premise("student_fig", STUDENT, "1800", "1,800 cakes"))
    assert verified is False and not [c for c in checks if c.method == "numeric_in_task" and c.verified is True]


def test_words_no_record_holds_still_fail():
    verified, checks = _check(_premise("student_fig", STUDENT, "1800", "the student calculated 1,800 cakes"), STATED)
    assert verified is False and not [c for c in checks if c.method == "numeric_in_task" and c.verified is True]


def test_nine_per_cent_grounds_its_decimal_reading():
    verified, checks = _check(_premise("rate", "the loan's annual interest rate (a fraction)", "0.09", "9% interest per year"))
    assert verified is True and any(c.verified is True and c.method == "figures_in_excerpt" for c in checks)


def test_a_figure_no_record_states_still_fails():
    verified, checks = _check(_premise("student_fig", "the student's figure of 2,400 cakes", "2400", "2,400 cakes"), STATED)
    assert verified is False and not [c for c in checks if c.method == "numeric_in_task" and c.verified is True]


def test_a_request_figure_inside_a_question_does_not_verify():
    question = TaskRecord.of(TASK.task_id, TASK.request_id, "Is the break-even quantity 1,800 cakes or 3,000 cakes? Please show working.")
    verified, checks = _check(_premise("student_fig", STUDENT, "1800", "1,800 cakes"), question)
    assert verified is not True and not [c for c in checks if c.method == "numeric_in_task" and c.verified is True]


def test_a_request_figure_that_counts_words_or_marks_is_no_given():
    limit = TaskRecord.of(TASK.task_id, TASK.request_id, "Keep (e) under 150 words. (b) Calculate the break-even quantity. [2]")
    verified, _checks = _check(_premise("cakes", "the number of cakes sold", "150", "150 cakes"), limit)
    assert verified is not True


def test_e2e_the_relation_p_student_is_unverified_not_refuted():
    _case, rc = deliver("e2e-B23-bm", "text")
    assert failed_groundings(rc) == []                              # was GROUNDING:FAILED on p_student
    o = next(o for o in rc.outcomes if o.claim_id.startswith("g3.1"))
    [p] = [p for p in o.translation.problem.premises if p.id == "p_student"]
    assert p.grounding.verified is None                             # its relation is the translation's own, its figures the record's
    assert not blocking(diagnostics(rc))
