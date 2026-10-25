"""formal-robustness-4: a formalization that is invalid inside the joint problem (a product of two unknowns under the
joint limits) made the whole joint consistency check UNSUPPORTED, so a contradiction between the other claims went
unreported. The invalid claim is still charged (INT-GLOSSARY-007), and the others are checked together without it.
"""
from __future__ import annotations

from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.integrity.cross_check import check_cross_report_consistency
from epinoic_logic.ir.schema import Problem

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)


def _var(n):
    return {"op": "var", "name": n}


def _problem(cid: str, symbols, premises, conclusion) -> Problem:
    return Problem.model_validate({
        "problem_id": "pr-" + cid, "request_id": "req1", "claim_id": cid, "query": "entailment",
        "symbols": [{"name": n, "sort": s} for n, s in symbols],
        "premises": [{"id": f"p{i}", "expr": e} for i, e in enumerate(premises)],
        "conclusion": {"id": "concl", "expr": conclusion}})


def _claims():
    a = _problem("ca", [("x", "Int")], [{"op": "eq", "left": _var("x"), "right": {"op": "int", "value": "3"}}],
                 {"op": "gt", "left": _var("x"), "right": {"op": "int", "value": "0"}})
    b = _problem("cb", [("x", "Int")], [{"op": "eq", "left": _var("x"), "right": {"op": "int", "value": "4"}}],
                 {"op": "gt", "left": _var("x"), "right": {"op": "int", "value": "0"}})
    c = _problem("cc", [("y", "Real"), ("z", "Real")],
                 [{"op": "eq", "left": {"op": "mul", "args": [_var("y"), _var("z")]}, "right": {"op": "real", "value": "6"}},
                  {"op": "eq", "left": _var("y"), "right": {"op": "real", "value": "2"}}],
                 {"op": "eq", "left": _var("z"), "right": {"op": "real", "value": "3"}})
    return a, b, c


def test_a_contradiction_beside_an_invalid_claim_is_still_named():
    a, b, c = _claims()
    _res, findings = check_cross_report_consistency([a, b, c], request_id="req1", config=CFG, signing_key=b"k" * 32)
    assert [f.claim_ids for f in findings if f.code == "INT-GLOSSARY-007"] == [["cc"]]
    [conflict] = [f for f in findings if f.code == "INT-CONFLICT-001"]
    assert sorted(conflict.claim_ids) == ["ca", "cb"] and conflict.severity == "error"


def test_control_the_pair_alone_gives_the_same_conflict_and_a_consistent_rest_gives_none():
    a, b, c = _claims()
    _res, findings = check_cross_report_consistency([a, b], request_id="req1", config=CFG, signing_key=b"k" * 32)
    assert [sorted(f.claim_ids) for f in findings if f.code == "INT-CONFLICT-001"] == [["ca", "cb"]]
    _res, findings = check_cross_report_consistency([a, c], request_id="req1", config=CFG, signing_key=b"k" * 32)
    assert [f.code for f in findings] == ["INT-GLOSSARY-007"]
