"""Repair round 5, the engine's argument rules, each with a clean control:

* ADV5-15 (a): a universal drawn from tested cases named by a list ("the inputs 2, 5 and 9") or by one label ("input 7",
  "trial 2") is a hasty generalisation; a fact about every possible input is none.
* ADV5-15 (b): a cause read into a correlation with a causative verb ("the new goggles make swimmers faster") is a causal
  leap; the same link warranted by a controlled comparison, and a comparison that reads no cause, are not.
* INV-LINK-1: a figure relation (``x > y``: a relation between quantities, no implication, biconditional or either/or)
  states no step from a reason to the point, so it is listed with the facts no check established (ARG-FACT-001) and is
  never named the writer's leap with an empty consequent; an implication the writer adds is still ARG-LINK-001.
* ADV5-13: a derived run made only of bound premises skips its consistency check when the engine found the bound premises
  consistent (a subset of a satisfiable set is satisfiable), and decides exactly as before; a run that adds a step is still
  checked for consistency first."""
from __future__ import annotations

import pytest

from epinoic_logic.engine import argument as argument_module
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem

from .test_argument_diagnostics import CFG, CMP, B, IMP, P, V, codes, problem, run

ALL = "the function returns the correct output for every input"


def _generalised(fact: str) -> dict:
    meanings = B(t=fact, all_=ALL)
    return codes(run(problem([P("e", V("t"), fact, kind="general_knowledge"), P("l", IMP(V("t"), V("all_")), "so it works for every input", note="link: so")],
                             V("all_"), meanings)))


@pytest.mark.parametrize("fact", ["the function returned the correct output for the inputs 2, 5 and 9",
                                  "the function returned the correct output for input 7", "in trial 2 the function returned the correct output"])
def test_a_universal_drawn_from_tested_cases_is_a_hasty_generalisation(fact):
    assert _generalised(fact).get("ARG-HG-001") == "warning"


def test_control_a_fact_about_every_possible_input_is_no_instance():
    assert "ARG-HG-001" not in _generalised("the function returned the correct output for every possible input")


def _caused(fact: str, point: str) -> dict:
    meanings = B(c=fact, k=point)
    return codes(run(problem([P("e", V("c"), fact, kind="general_knowledge"), P("l", IMP(V("c"), V("k")), "so " + point, note="link: so")], V("k"), meanings)))


def test_a_cause_read_into_a_correlation_with_a_causative_verb_is_a_causal_leap():
    assert _caused("swimmers who used the new goggles recorded faster lap times", "the new goggles make swimmers faster").get("ARG-CL-001") == "warning"


@pytest.mark.parametrize("fact, point", [
    ("swimmers randomly assigned the new goggles recorded faster lap times than a control group", "the new goggles make swimmers faster"),
    ("swimmers who used the new goggles recorded faster lap times", "swimmers with the new goggles are faster than swimmers without them"),
], ids=["controlled comparison", "a comparison reads no cause"])
def test_control_a_warranted_link_or_a_plain_comparison_is_no_causal_leap(fact, point):
    assert "ARG-CL-001" not in _caused(fact, point)


def _chain(extra_link: bool = False) -> Problem:
    x = lambda n: {"op": "var", "name": n}  # noqa: E731
    premises = [{"id": "P1", "expr": CMP("gt", x("x"), x("y"))}, {"id": "P2", "expr": CMP("gt", x("y"), x("z"))}]
    symbols = [{"name": n, "sort": "Int"} for n in "xyz"] + ([{"name": "b", "sort": "Bool", "meaning": "the order holds"}] if extra_link else [])
    if extra_link:
        premises.append({"id": "L", "expr": {"op": "implies", "left": CMP("gt", x("x"), x("z")), "right": x("b")}, "label": "so the order holds"})
    concl = x("b") if extra_link else CMP("gt", x("x"), x("z"))
    return Problem.model_validate({"ir_version": "1.0", "problem_id": "p1", "request_id": "req1", "claim_id": "c1", "query": "entailment",
                                   "symbols": symbols, "premises": premises, "conclusion": {"id": "C", "expr": concl}})


def test_a_figure_relation_is_listed_with_the_facts_never_named_a_leap():
    r = run(_chain())
    assert r.status is S.ENTAILED
    named = {d.code: d for d in r.named_diagnostics or []}
    assert "ARG-LINK-001" not in named
    fact = named["ARG-FACT-001"]
    assert fact.defect == "lack_of_evidence" and fact.assertion_ids == ["P1", "P2"] and "relate quantities" in fact.message


def test_control_an_implication_beside_the_relations_is_still_the_writers_link():
    r = run(_chain(extra_link=True))
    link = [d for d in r.named_diagnostics or [] if d.code == "ARG-LINK-001"]
    assert link and link[0].assertion_ids == ["L"] and link[0].missing_link.consequent


def _runs(p: Problem, consistent: bool):
    from epinoic_logic.engine.policies import LINEAR_LIMITS
    runs = argument_module._Runs.of(p, CFG, LINEAR_LIMITS, None)
    runs.consistent = consistent
    return runs


def test_a_run_of_bound_premises_decides_the_same_with_and_without_its_consistency_check():
    p = _chain()
    concl = p.conclusion.expr.model_dump(mode="json", exclude_none=True)
    for ids in (["P1", "P2"], ["P1"], []):
        a, b = _runs(p, True).entail(ids, concl, "t"), _runs(p, False).entail(ids, concl, "t")
        assert a.status is b.status and a.digest == b.digest


def test_control_a_run_that_adds_a_step_is_still_checked_for_consistency():
    p = _chain()
    concl = p.conclusion.expr.model_dump(mode="json", exclude_none=True)
    contradiction = CMP("lt", {"op": "var", "name": "x"}, {"op": "var", "name": "y"})        # x < y beside x > y
    assert _runs(p, True).entail(["P1", "P2"], concl, "t", [contradiction]).status is S.INCONSISTENT_PREMISES
