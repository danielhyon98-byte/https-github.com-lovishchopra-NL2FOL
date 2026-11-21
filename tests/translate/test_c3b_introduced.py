"""Round-10 leftover R10-CORE-INTRODUCED-FIGURES: the translator named an introduced figure only in an assignment premise ('x = 4.2');
a decimal or a constant the translation computed inside a premise's expression ('y = 0.4244 × m') went unnamed, while the transfer
auditor's OVS-TRN-005 names both. Now it is named (a note: it decides nothing on its own, since a constant the translation writes for
a symbol the claim names, such as π, is no figure of the claim's)."""
from __future__ import annotations

from epinoic_logic.api.ir import Problem
from epinoic_logic.translate.pipeline import introduced_figures
from epinoic_logic.translate.quantities import SourceText


def _problem(kind: str = "specialist_inference") -> Problem:
    m, y = {"op": "var", "name": "m"}, {"op": "var", "name": "y"}
    return Problem.model_validate({
        "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "m", "sort": "Real"}, {"name": "y", "sort": "Real"}],
        "premises": [{"id": "P_m", "expr": {"op": "eq", "left": m, "right": {"op": "real", "value": "50"}}, "grounding": {"kind": kind}},
                     {"id": "P_y", "expr": {"op": "eq", "left": y, "right": {"op": "mul", "args": [{"op": "real", "value": "0.4244"}, m]}},
                      "grounding": {"kind": kind}}],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": y, "right": {"op": "real", "value": "20"}}}})


def test_a_figure_inside_a_premise_expression_no_source_states_is_named():
    sources = [SourceText("claim", "c", "The mass is 50 g, so the yield is over 20 g.")]
    assert introduced_figures(_problem(), sources) == ["P_y (0.4244 in its expression)"]


def test_control_a_stated_figure_or_a_task_authority_premise_is_not_named():
    stated = [SourceText("claim", "c", "The mass is 50 g and the factor is 0.4244, so the yield is over 20 g.")]
    assert introduced_figures(_problem(), stated) == []
    assert introduced_figures(_problem("task_setting"), [SourceText("claim", "c", "nothing stated")]) == []
