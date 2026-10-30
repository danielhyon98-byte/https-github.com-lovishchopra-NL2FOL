"""Repair round 2, grounding: the subject of a figure (a figure stated for another quantity in the same clause is never the
premise's, and a unit or scale word is no subject word), figures the answer derives anywhere in its working (and only by a
calculation that gives them), and a quotation that differs from its source only in form (it is no source mismatch). Each
positive has a clean control.

Ported onto the integrated translator without three tests (docs/ARGUMENT_DIAGNOSTICS.md, section "Port onto the integrated
translator"): the figure-subject refutation of a figure cited to another quantity's clause and the figures the answer
derives in its own working (``answer_derived_figures``) are the feature line's versions of grounding fixes the integrated
translator makes its own way."""
from __future__ import annotations

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.contracts import SuppliedText, TaskRecord
from epinoic_logic.translate.grounding import check_problem_grounding
from epinoic_logic.translate.quantities import SourceText

from ..evidence_support import deliver, diagnostics


def _v(n):
    return {"op": "var", "name": n}


def _r(v):
    return {"op": "real", "value": v}


def _ground(premises, symbols, conclusion, docs=(), task=None):
    p = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": symbols,
                                "premises": premises, "conclusion": {"id": "C", "expr": conclusion}})
    grounded, checks = check_problem_grounding(p, list(docs), task=task)
    return {x.id: x.grounding.verified for x in grounded.premises}, checks


# ------------------------------------------------------------------------------------------------------- subject of a figure

def test_a_p_value_stated_after_the_significance_level_in_one_clause_is_the_p_values():
    task = TaskRecord.of("t1", "r1", "A chi-squared test at the 1% significance level returns a p-value of 0.0072. State whether the result is "
                                     "significant.")
    verified, checks = _ground([{"id": "Pp", "expr": {"op": "eq", "left": _v("p"), "right": _r("0.0072")}, "label": "the p-value is 0.0072",
                                 "grounding": {"kind": "task_setting", "source_refs": [{"document_id": "t1"}], "certainty": "established"}}],
                               [{"name": "p", "sort": "Real", "meaning": "the p-value of the chi-squared test"}],
                               {"op": "lt", "left": _v("p"), "right": _r("0.01")}, task=task)
    assert verified == {"Pp": True}, [(c.method, c.verified, c.detail) for c in checks]


TRADE = SuppliedText(document_id="d", title="Trade", author=None,
                     text="In 2021 the region's exports were 62 million tonnes and its imports were 48 million tonnes.")
EXPORTS = [{"name": "ex", "sort": "Real", "meaning": "the region's exports in 2021 (million tonnes)"}]


def test_the_exports_figure_cited_to_the_exports_clause_is_verified():
    verified, _checks = _ground([{"id": "E1", "expr": {"op": "eq", "left": _v("ex"), "right": _r("62")}, "label": "exports were 62 million tonnes",
                                  "grounding": {"kind": "quotation", "source_refs": [{"document_id": "d", "excerpt": "exports were 62 million tonnes"}],
                                                "certainty": "established"}}], EXPORTS, {"op": "gt", "left": _v("ex"), "right": _r("40")}, [TRADE])
    assert verified == {"E1": True}


# ------------------------------------------------------------------------------------------------------- derived figures

EXTRACT = "Extract: The firm sells each candle for £5.00. Each candle costs £3.00 to make, and the firm's fixed costs are £4,000 a month."
RECORDS = [SourceText("supplied_text", "extract-1", EXTRACT)]


def _break_even_case(first: str, contribution: str, output: str) -> dict:
    """A constructed text-mode answer: the first sentence works out the contribution per candle; the second (the claim) uses
    it in a relation premise whose excerpts state only the price and the cost."""
    second = f"With fixed costs of £4,000 a month, the firm therefore breaks even at {int(output):,} candles a month."
    problem = {"ir_version": "1.0", "problem_id": "p-be", "request_id": "x", "claim_id": "x", "query": "entailment",
               "symbols": [{"name": "fc", "sort": "Real", "meaning": "the firm's monthly fixed costs (£)"},
                           {"name": "be", "sort": "Real", "meaning": "the firm's break-even output (candles a month)"}],
               "premises": [
                   {"id": "P_fc", "expr": {"op": "eq", "left": _v("fc"), "right": _r("4000")}, "label": "fixed costs are £4,000 a month",
                    "grounding": {"kind": "quotation", "certainty": "established",
                                  "source_refs": [{"document_id": "extract-1", "excerpt": "fixed costs are £4,000 a month"}]}},
                   {"id": "P_be", "expr": {"op": "eq", "left": {"op": "mul", "args": [_v("be"), _r(contribution)]}, "right": _v("fc")},
                    "label": f"at break-even, output times the £{contribution} contribution per candle covers the fixed costs",
                    "grounding": {"kind": "quotation", "certainty": "established",
                                  "source_refs": [{"document_id": "extract-1", "excerpt": "sells each candle for £5.00"},
                                                  {"document_id": "extract-1", "excerpt": "costs £3.00 to make"}]}}],
               "conclusion": {"id": "C", "expr": {"op": "eq", "left": _v("be"), "right": _r(output)}, "label": "the break-even output"}}
    return {"case_format": "argdiag-corpus/1", "id": "derived-figure", "family": "evidence", "expected_label": "none", "acceptable_labels": [],
            "title": "derived figure", "subject": "Business Management", "task_type": "data_response", "agent_id": "business-management-specialist",
            "request": "Using the extract, calculate the firm's monthly break-even output. [3 marks]", "answer": f"{first} {second}",
            "supplied_texts": [{"document_id": "extract-1", "title": "Extract", "text": EXTRACT}],
            "ids": {"task_id": "task-be", "request_id": "req-be", "report_id": "rep-be", "plan_id": "plan-be"},
            "modes": [{"name": "text", "delivery": "text", "synthesis": "carried"}], "report_claims": [],
            "translations": [{"contains": "the firm therefore breaks even at", "proposal": {
                "problem": problem, "interpretation": {"reading": "as written", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
                "unsupported_reason": None}}],
            "fidelity_review": "faithful"}


def _point(rc):
    [o] = [o for o in rc.outcomes if o.translation is not None]
    return o


@pytest.mark.parametrize("first, contribution, output", [
    ("Each candle sells for £5.00 and costs £3.00 to make, so its contribution is £5.00 − £3.00 = £2.50.", "2.50", "1600"),   # a wrong step
    ("Each candle sells for £5.00 and costs £3.00 to make, so its contribution is £2.00.", "2.00", "2000")])                  # no working
def test_a_figure_no_calculation_of_the_answer_gives_is_not_derived(first, contribution, output):
    _case, rc = deliver(_break_even_case(first, contribution, output), "text")
    o = _point(rc)
    [failed] = [c for c in o.translation.grounding_checks if c.verified is False]
    assert failed.target_id == "P_be" and failed.method == "figures_in_excerpt"
    assert [d.code for d in diagnostics(rc, "EVD-SRC-003")] == ["EVD-SRC-003"]


# ------------------------------------------------------------------------------------------------------- a quotation's form

def _quotation_case(excerpt: str) -> dict:
    answer = f"Penguins lay eggs. The extract states that \"{excerpt}\" and that \"penguins are birds\", so penguins lay eggs."
    problem = {"ir_version": "1.0", "problem_id": "p-q", "request_id": "x", "claim_id": "x", "query": "entailment",
               "symbols": [{"name": "bird", "sort": "Bool", "meaning": "penguins are birds"}, {"name": "eggs", "sort": "Bool", "meaning": "penguins lay eggs"}],
               "premises": [
                   {"id": "r1", "expr": {"op": "implies", "left": _v("bird"), "right": _v("eggs")}, "label": "every bird lays eggs", "materiality": "material",
                    "grounding": {"kind": "quotation", "source_refs": [{"document_id": "bio", "excerpt": excerpt}], "certainty": "established"}},
                   {"id": "f1", "expr": _v("bird"), "label": "penguins are birds", "materiality": "material",
                    "grounding": {"kind": "quotation", "source_refs": [{"document_id": "bio", "excerpt": "penguins are birds"}], "certainty": "established"}}],
               "conclusion": {"id": "C", "expr": _v("eggs"), "label": "Penguins lay eggs."}}
    return {"case_format": "argdiag-corpus/1", "id": "quotation-form", "family": "evidence", "expected_label": "none", "acceptable_labels": [],
            "title": "quotation form", "subject": "Biology", "task_type": "short_answer", "agent_id": "biology-specialist",
            "request": "Using the extract, explain whether penguins lay eggs.", "answer": answer,
            "supplied_texts": [{"document_id": "bio", "title": "Extract",
                                "text": "Extract: Every bird lays eggs, including those that cannot fly; penguins are birds that cannot fly."}],
            "ids": {"task_id": "task-q", "request_id": "req-q", "report_id": "rep-q", "plan_id": "plan-q"},
            "modes": [{"name": "text", "delivery": "text", "synthesis": "none"}], "report_claims": [],
            "translations": [{"contains": "Penguins lay eggs.", "proposal": {
                "problem": problem, "interpretation": {"reading": "as written", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
                "unsupported_reason": None}}],
            "fidelity_review": "faithful"}


def test_a_quotation_that_differs_only_in_its_initial_capital_is_no_source_mismatch():
    _case, rc = deliver(_quotation_case("every bird lays eggs"), "text")
    assert diagnostics(rc, "EVD-SRC-003") == []
    assert "INT-REQ-010" in {f.code for f in rc.findings}     # the form difference is still named, and the grounding stays unverified
    o = _point(rc)
    assert any(c.verified is False and "differs in form" in (c.detail or "") for c in o.translation.grounding_checks)


def test_a_quotation_with_a_changed_word_is_a_source_mismatch():
    _case, rc = deliver(_quotation_case("every bird lays two eggs"), "text")
    [d] = diagnostics(rc, "EVD-SRC-003")
    assert d.defect == "source_mismatch" and d.severity == "warning" and d.assertion_ids == ["r1"]


# ------------------------------------------------------------------------------------------------------- notation in words
# ADV2-11: a task_setting premise that writes the task's notation in words ("x squared is greater than 0" for "x² > 0") says
# what the task says. The grounding check read it as words the task lacks and refuted it (GROUNDING:FAILED, a false alarm
# on a clean answer); the label's words, in order, are a run of the task sentence read with its signs in words, so the
# content_in_task check validates it. Controls: a label that drops or changes the notation is still refuted, and the same
# label under a supposition is not validated.

def _notation_premise(label: str):
    return ([{"id": "f1", "expr": _v("sq"), "label": label, "grounding": {"kind": "task_setting", "source_refs": [], "certainty": "established"}}],
            [{"name": "sq", "sort": "Bool", "meaning": label}, {"name": "zero", "sort": "Bool", "meaning": "x is zero"}],
            {"op": "not", "arg": _v("zero")})


@pytest.mark.parametrize("label", ["x squared is greater than 0", "the task states that x squared is more than 0"])
def test_a_task_label_that_writes_the_notation_in_words_is_validated_by_the_task_sentence(label):
    task = TaskRecord.of("t1", "r1", "The real number x satisfies x² > 0. Explain whether x can be 0.")
    verified, checks = _ground(*_notation_premise(label), task=task)
    assert verified["f1"] is True, [(c.method, c.verified, c.detail) for c in checks]
    [check] = [c for c in checks if c.target_id == "f1"]
    assert check.method == "content_in_task" and "notation in words" in check.detail


@pytest.mark.parametrize("label", ["x is greater than 0", "x squared is less than 0", "x cubed is greater than 0"])
def test_a_task_label_that_does_not_write_the_notation_is_still_refuted(label):
    task = TaskRecord.of("t1", "r1", "The real number x satisfies x² > 0. Explain whether x can be 0.")
    verified, checks = _ground(*_notation_premise(label), task=task)
    assert verified["f1"] is False, [(c.method, c.verified, c.detail) for c in checks]


def test_the_notation_under_a_supposition_validates_nothing_and_refutes_nothing():
    task = TaskRecord.of("t1", "r1", "Suppose x² > 0. Explain whether x can be 0.")
    verified, _checks = _ground(*_notation_premise("x squared is greater than 0"), task=task)
    assert verified["f1"] is None


def test_the_notation_reader_matches_a_contiguous_run_only():
    from epinoic_logic.translate.grounding import spells_notation
    assert spells_notation("x squared is greater than 0", "The real number x satisfies x² > 0.")
    assert spells_notation("y is not equal to 3", "We know that y ≠ 3.")
    assert not spells_notation("x is greater than 0", "The real number x satisfies x² > 0.")
    assert not spells_notation("x squared is greater than 0", "The real number x satisfies x squared, which is positive.")  # no sign
    assert not spells_notation("x", "x² > 0")  # one word reads nothing
