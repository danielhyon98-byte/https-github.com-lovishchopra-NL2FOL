"""Repair round 3, evidence family: what supports a figure, and which link rests on a label alone.

* V3-E2E-NEW-EVD-FALSE-WARNINGS: a figure is introduced by the answer (EVD-FIG-001; EVD-LACK-001 for an assignment no
  record supports) only when no record states it, no working of the answer derives it and it is no date. The reading of
  the answer's working covers a chain over lines ("= $960" on the next line), ", which is" and a product in words; a
  record's rounded figure states the ends of its interval; a figure the answer never writes is the translation's own, not
  an introduction by the answer.
* ADV3-13 (e): a link that cites only excerpts stating no link ("Britain", the question the task asks, "Explain your
  answer.") rests on its source label alone: EVD-SRC-001 names it. A link whose excerpt can state it (a rule's words, or
  words of both its sides) is not named."""
from __future__ import annotations

import json
from typing import Optional

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText, TaskRecord
from epinoic_logic.translate.grounding import assignment_support
from epinoic_logic.translate.quantities import SourceText

from ..contract.helpers import make_report, output, problem_dict, run_claim
from ..evidence_support import deliver, diagnostics
from .test_evidence_diagnostics import _revenue_case

X = {"op": "var", "name": "x"}


def _support(expr: dict, meaning: str, records: list[str], answers: list[str], sort: str = "Real"):
    p = Problem.model_validate({"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                "symbols": [{"name": "x", "sort": sort, "meaning": meaning}], "premises": [{"id": "P", "expr": expr}],
                                "conclusion": {"id": "C", "expr": {"op": "gt", "left": X, "right": {"op": "real", "value": "0"}}}})
    recs = [SourceText("supplied_text", f"d{i}", t) for i, t in enumerate(records)]
    [found] = assignment_support(p.premises[0].expr, {s.name: s for s in p.symbols}, None, recs, answers)
    return found.status


def _eq(value: str, kind: str = "real") -> dict:
    return {"op": "eq", "left": X, "right": {"op": kind, "value": value}}


SALES = ["The firm sold 120 units at $8 each."]


@pytest.mark.parametrize("answer", ["Its revenue was 120 × $8 = $960.", "120 units at $8 each gives 120 × 8, which is 960 dollars.",
                                    "Revenue = 120 × 8\n= 960 dollars"])
def test_a_figure_the_answers_working_derives_is_worked(answer):
    assert _support(_eq("960"), "the firm's revenue ($)", SALES, [answer]) == "worked"


def test_a_year_the_meaning_names_as_a_date_is_no_quantity():
    assert _support(_eq("2019", "int"), "the year the plan began", ["The plan began in spring."], ["The plan began in 2019."], sort="Int") == "date"


def test_the_ends_of_a_rounded_record_figure_are_stated():
    bounds = {"op": "and", "args": [{"op": "ge", "left": X, "right": {"op": "real", "value": "2.45"}},
                                    {"op": "lt", "left": X, "right": {"op": "real", "value": "2.55"}}]}
    assert _support(bounds, "the rod's length (m)", ["The rod is about 2.5 m long."], []) == "stated"
    assert _support(bounds, "the rod's length (m)", ["The rod is 2.5 m long."], []) != "stated"   # an exact figure states no interval


def test_a_figure_the_answer_never_writes_is_the_translations_own():
    assert _support(_eq("777"), "the firm's revenue ($)", SALES, ["Its revenue exceeded the target."]) == "not_in_answer"


def test_control_a_bare_figure_no_record_or_working_gives_is_introduced():
    assert _support(_eq("960"), "the firm's revenue ($)", ["The firm set a revenue target of $900."], ["Its revenue was $960."]) == "introduced"


@pytest.mark.parametrize("answer", ["Selling 120 units at $8 each gives 120 × 8, which is $960, so it exceeded the target.",
                                    "Its revenue was 120 × $8\n= $960, so it exceeded the target."])
def test_a_worked_figure_is_neither_invented_nor_unsupported(answer):
    _case, rc = deliver(_revenue_case(answer), "report")
    assert [d.code for d in diagnostics(rc, prefix="EVD-")] == []


def test_a_figure_a_record_states_needs_no_source_reference():
    case = _revenue_case("Its revenue was 120 × $8 = $960, so it exceeded the target.")
    case["translations"][0]["proposal"]["problem"]["premises"][1]["grounding"] = {"kind": "specialist_inference", "certainty": "established"}
    _case, rc = deliver(case, "report")
    assert diagnostics(rc, "EVD-LACK-001") == []        # the $900 target is the extract's own figure


def test_control_a_bare_figure_is_invented_and_unsupported():
    _case, rc = deliver(_revenue_case("Its revenue was $960, so it exceeded the target."), "report")
    assert {(d.code, tuple(d.assertion_ids)) for d in diagnostics(rc, prefix="EVD-")} == {("EVD-FIG-001", ("P_rev",)), ("EVD-LACK-001", ("P_rev",))}


# ------------------------------------------------------------------ ADV3-13 (e): a link whose excerpt states no link

TASK = "Was Britain certain to win the First World War? Britain had the largest navy in 1914. Explain your answer."
SOURCE = "Source: Britain was certain to win the war, some newspapers claimed in 1914. Historians disagree."


def _link_outcome(link_grounding: dict):
    data = problem_dict(
        [{"id": "f1", "expr": {"op": "var", "name": "navy"}, "label": "Britain had the largest navy in 1914",
          "grounding": {"kind": "task_setting", "source_refs": [{"document_id": "task", "excerpt": "Britain had the largest navy in 1914"}]}},
         {"id": "l1", "expr": {"op": "implies", "left": {"op": "var", "name": "navy"}, "right": {"op": "var", "name": "win"}}, "label": "so",
          "grounding": link_grounding}],
        {"id": "C", "expr": {"op": "var", "name": "win"}, "label": "Britain was certain to win the war"},
        [{"name": "navy", "sort": "Bool", "meaning": "Britain had the largest navy in 1914"},
         {"name": "win", "sort": "Bool", "meaning": "Britain was certain to win the war"}])
    claim, report = make_report("Britain had the largest navy in 1914, so Britain was certain to win the war.", subject="History", role="point",
                                texts=(("src-1", SOURCE),))
    task = TaskRecord.of(report.task_id, report.request_id, TASK)
    return run_claim(claim, report, json.dumps(output(data)), task=task)


def _named(outcome, code: str) -> list:
    return [d for d in list(outcome.named_diagnostics) + list(outcome.verification.named_diagnostics or []) if d.code == code]


@pytest.mark.parametrize("grounding", [
    {"kind": "task_setting", "source_refs": [{"document_id": "task", "excerpt": "Britain"}]},
    {"kind": "task_setting", "source_refs": [{"document_id": "task", "excerpt": "Was Britain certain to win the First World War?"}]},
    {"kind": "rubric_rule", "source_refs": [{"document_id": "task", "excerpt": "Explain your answer."}]},
    {"kind": "supplied_text", "source_refs": [{"document_id": "src-1", "excerpt": "Britain was certain to win the war"}]},
])
def test_a_link_that_cites_only_excerpts_stating_no_link_rests_on_its_label(grounding):
    o = _link_outcome(grounding)
    assert _named(o, "EVD-SRC-001") and o.release is not None and not o.release.permitted


def test_control_a_link_whose_excerpt_names_both_sides_is_not_charged_as_label_only():
    task_rule = "If a country has the largest navy, it is certain to win a war."
    claim_texts = (("src-1", SOURCE + " " + task_rule),)
    data = problem_dict(
        [{"id": "f1", "expr": {"op": "var", "name": "navy"}, "label": "Britain had the largest navy in 1914",
          "grounding": {"kind": "task_setting", "source_refs": [{"document_id": "task", "excerpt": "Britain had the largest navy in 1914"}]}},
         {"id": "l1", "expr": {"op": "implies", "left": {"op": "var", "name": "navy"}, "right": {"op": "var", "name": "win"}},
          "label": "a country with the largest navy is certain to win a war",
          "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "src-1", "excerpt": task_rule.rstrip(".")}]}}],
        {"id": "C", "expr": {"op": "var", "name": "win"}, "label": "Britain was certain to win the war"},
        [{"name": "navy", "sort": "Bool", "meaning": "Britain had the largest navy in 1914"},
         {"name": "win", "sort": "Bool", "meaning": "Britain was certain to win the war"}])
    claim, report = make_report("Britain had the largest navy in 1914, so Britain was certain to win the war.", subject="History", role="point",
                                texts=claim_texts)
    o = run_claim(claim, report, json.dumps(output(data)), task=TaskRecord.of(report.task_id, report.request_id, TASK))
    assert not [d for d in _named(o, "EVD-SRC-001") if "l1" in d.assertion_ids]
