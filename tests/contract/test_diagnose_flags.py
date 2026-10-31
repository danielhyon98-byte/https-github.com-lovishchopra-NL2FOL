"""Which engine runs carry the argument diagnosis: the claim's own verification (``verify_claim``, ``POST /v1/verify``,
the CLI) runs it; the internal probes (precision, the pipeline's figure probe), the cross checks and the channel's
code-built checks (branch formal checks, constraint bounds) pass ``diagnose=False``. Pinned twice: every call site in the
source, and spies on real runs."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import epinoic_logic
from epinoic_logic.integrity import cross_check as cross_module
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import outcome as outcome_module
from epinoic_logic.translate import pipeline as pipeline_module
from epinoic_logic.translate import precision as precision_module

from .helpers import CFG, make_report, output, run_claim, speed_problem

SRC = Path(epinoic_logic.__file__).resolve().parent


def _calls(module: str, names: set[str]) -> list[ast.Call]:
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in names]


def _diagnose_kw(call: ast.Call):
    kw = next((k for k in call.keywords if k.arg == "diagnose"), None)
    return None if kw is None else (kw.value.value if isinstance(kw.value, ast.Constant) else "dynamic")


@pytest.mark.parametrize("module, names, count", [
    ("translate/precision.py", {"engine_verify"}, 3),
    ("translate/pipeline.py", {"engine_verify"}, 1),
    ("integrity/cross_check.py", {"verify"}, 9),  # ported: this tree's cross checks make nine code-built runs
    ("channel/bus.py", {"verify"}, 3),
])
def test_every_internal_and_code_built_run_passes_diagnose_false(module, names, count):
    calls = _calls(module, names)
    assert len(calls) == count and all(_diagnose_kw(c) is False for c in calls)


@pytest.mark.parametrize("module, names", [("translate/outcome.py", {"engine_verify"}), ("service/app.py", {"verify"}), ("cli.py", {"verify"})])
def test_the_claims_own_verification_keeps_the_diagnosis(module, names):
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ((isinstance(n.func, ast.Name) and n.func.id in names)
                                                                       or (isinstance(n, ast.Call) and any(isinstance(a, ast.Name) and a.id in names for a in n.args)))]
    assert calls and all(_diagnose_kw(c) is None for c in calls)


def _spy(monkeypatch, module, name: str, seen: list):
    real = getattr(module, name)

    def spy(*a, **k):
        seen.append(k.get("diagnose", True))
        return real(*a, **k)

    monkeypatch.setattr(module, name, spy)


def test_a_real_translation_probes_without_and_verifies_with_the_diagnosis(monkeypatch):
    probes: list = []
    claims: list = []
    _spy(monkeypatch, precision_module, "engine_verify", probes)
    _spy(monkeypatch, pipeline_module, "engine_verify", probes)
    _spy(monkeypatch, outcome_module, "engine_verify", claims)
    claim, report = make_report("If x = 1/3 then x is about 0.33, so x < 0.34.", kind="arithmetic", texts=())
    problem = {"ir_version": "1.0", "problem_id": "p-c", "request_id": "req-ad", "claim_id": "c", "query": "entailment",
               "symbols": [{"name": "x", "sort": "Real"}, {"name": "b", "sort": "Bool"}, {"name": "n", "sort": "Int"}],
               "premises": [{"id": "X", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "0.33"}}},
                            {"id": "D", "expr": {"op": "iff", "left": {"op": "var", "name": "b"},
                                                 "right": {"op": "eq", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": "17"}}}}],
               "conclusion": {"id": "C", "expr": {"op": "lt", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "0.34"}}}}
    out = run_claim(claim, report, output(problem))
    assert probes and all(flag is False for flag in probes)
    assert claims == [True] and out.verification is not None and out.verification.argument_rules == "argdiag-2"


def test_the_cross_checks_run_without_the_diagnosis(monkeypatch):
    seen: list = []
    _spy(monkeypatch, cross_module, "verify", seen)
    p = lambda cid, value: Problem.model_validate({  # noqa: E731
        "problem_id": f"p-{cid}", "request_id": "r", "claim_id": cid, "query": "entailment", "symbols": [{"name": "x", "sort": "Real", "meaning": "the speed"}],
        "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": value}},
                      "grounding": {"kind": "supplied_text", "verified": True}}],
        "conclusion": {"id": "C", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": value}}}})
    cross_module.check_cross_report_consistency([p("c1", "1"), p("c2", "2")], request_id="r", config=CFG, signing_key=b"k" * 32)
    assert seen and all(flag is False for flag in seen)


def test_the_claims_verification_is_diagnosed_end_to_end():
    claim, report = make_report("The average speed of the car is 15 km/h.")
    out = run_claim(claim, report, output(speed_problem()))
    assert out.verification.argument_rules == "argdiag-2"
