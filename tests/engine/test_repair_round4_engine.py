"""Repair round 4, two engine classes of the re-run review:

* formal-robustness-1 (squaring-chain variant): E307 bounded only the linear growth of coefficients, so a chain of squarings
  of a variable fixed to a 40-digit literal (degree 2 per assertion, within the nonlinear degree bound) held one solver call
  for about 37 s under a 2000 ms timeout. The values the products of a nonlinear problem force are now bounded from the IR
  alone (``policies.forced_value_digits``), and a problem above ``MAX_FORCED_VALUE_DIGITS`` is refused before it compiles
  (INVALID_FORMALIZATION, E307), quickly. A short chain, and a product of free unknowns, still decide.
* fidelity-4 (split-restatement variant): premises of the writer's own that only together restate the point ("dt <= 41"
  and "dt >= 41" for "dt = 41") are a circle: E112 on the engine result, and the translator refuses the encoding as
  circular, as it refuses one premise holding both bounds. A modus ponens over two symbols and two bounds that say more
  than the point are no circle."""
from __future__ import annotations

import json
import time

import pytest

from epinoic_logic.engine import identity as identity_mod
from epinoic_logic.engine.policies import MAX_FORCED_VALUE_DIGITS, forced_value_digits, policy_config, policy_limits
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.runner import verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, TranslationStatus as T, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

CFG = SolverConfig(timeout_ms=2000, memory_max_mb=None)
KEY = b"k" * 32


def V(n):
    return {"op": "var", "name": n}


def I(v):
    return {"op": "int", "value": str(v)}


def op(o, *a):
    if o in ("and", "or", "add", "mul"):
        return {"op": o, "args": list(a)}
    return {"op": o, "left": a[0], "right": a[1]}


def _chain(n: int, start: str = "9" * 40, shape: str = "square") -> Problem:
    symbols = [{"name": "x", "sort": "Int"}] + [{"name": f"y{i}", "sort": "Int"} for i in range(1, n + 1)]
    premises = [{"id": "p0", "expr": op("eq", V("x"), I(start))}]
    prev = "x"
    for i in range(1, n + 1):
        expr = op("mul", V(prev), V(prev)) if shape == "square" else op("mul", V(prev), V("x"))
        premises.append({"id": f"p{i}", "expr": op("eq", V(f"y{i}"), expr)})
        prev = f"y{i}"
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": symbols,
                                   "premises": premises, "conclusion": {"id": "C", "expr": op("lt", V(prev), I(0))}})


def _nonlinear(problem: Problem):
    return verify(problem, policy_config("nonlinear", CFG), limits=policy_limits("nonlinear"))


# ------------------------------------------------------------------------------------------- formal-robustness-1

def test_the_digits_a_chain_of_squarings_forces_double_at_each_link():
    assert forced_value_digits(_chain(4))[0] == 640 and forced_value_digits(_chain(8))[0] == 10_240
    assert forced_value_digits(_chain(20, shape="by_x"))[0] == 840                     # a product by the fixed value grows linearly


@pytest.mark.parametrize("n", [6, 8, 16])
def test_a_squaring_chain_beyond_the_bound_is_refused_before_it_compiles(n):
    started = time.perf_counter()
    r = _nonlinear(_chain(n))
    assert time.perf_counter() - started < 2.0
    assert r.status is S.INVALID_FORMALIZATION and [d.code for d in r.diagnostics] == ["E307"]
    assert "force values" in r.diagnostics[0].message and r.diagnostics[0].path.startswith("premises[")


@pytest.mark.parametrize("problem", [_chain(4), _chain(20, shape="by_x")], ids=["short squaring chain", "product by the fixed value"])
def test_control_a_problem_within_the_bound_is_decided(problem):
    assert forced_value_digits(problem)[0] <= MAX_FORCED_VALUE_DIGITS
    r = _nonlinear(problem)
    assert "E307" not in {d.code for d in r.diagnostics} and r.status is not S.INVALID_FORMALIZATION


def test_control_products_of_free_unknowns_force_no_value():
    p = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                "symbols": [{"name": n, "sort": "Real"} for n in ("a", "b", "c")],
                                "premises": [{"id": "p1", "expr": op("eq", V("c"), op("mul", V("a"), V("b")))}],
                                "conclusion": {"id": "C", "expr": op("ge", V("c"), {"op": "real", "value": "0"})}})
    assert forced_value_digits(p) == (0, None)
    assert _nonlinear(p).status is S.COUNTEREXAMPLE


def test_the_bound_is_part_of_the_policy_identity():
    assert identity_mod.policy_manifest()["max_forced_value_digits"] == MAX_FORCED_VALUE_DIGITS


# ------------------------------------------------------------------------------------------- fidelity-4, split restatement

WRITER = {"grounding": {"kind": "specialist_inference", "certainty": "established"}}


def _two(p1, p2, conclusion, symbols):
    return {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
            "symbols": [{"name": n, "sort": s} for n, s in symbols],
            "premises": [{"id": "p1", "expr": p1, "label": "the doubling time is at most 41 years", **WRITER},
                         {"id": "p2", "expr": p2, "label": "the doubling time is at least 41 years", **WRITER}],
            "conclusion": {"id": "concl", "expr": conclusion, "label": "the doubling time is 41 years"}}


def _pipeline(problem: dict):
    text = "The doubling time is 41 years."
    ids = dict(request_id="r", task_id="t", report_id="rep")
    claim = ClaimRecord(**ids, agent_id="geography-specialist", subject="Geography", task_type="short_answer", claim_id="c", claim_text=text,
                        claim_role="quantitative", proposed_claim_kind="arithmetic")
    report = SpecialistReport(**ids, agent_id="geography-specialist", subject="Geography", task_type="short_answer", original_response=text,
                              response_sha256=sha256_text(text), claims=[claim], supplied_texts=[], created_at="2026-10-24T00:00:00Z")
    out = json.dumps({"problem": problem, "interpretation": {"reading": "as written", "glossary": [], "ambiguity_flags": []},
                      "ambiguous": False, "unsupported_reason": None})
    provider = FixtureTranslationProvider({"c": [out, out]})
    return verify_claim(claim, report, Translator(provider, config=CFG), config=CFG, signing_key=KEY, key_id="k")


def test_a_restatement_split_across_two_writer_premises_is_refused_as_circular():
    o = _pipeline(_two(op("le", V("dt"), I(41)), op("ge", V("dt"), I(41)), op("eq", V("dt"), I(41)), [("dt", "Int")]))
    assert o.translation.status is T.INVALID_FORMALIZATION and o.display_status is S.INVALID_FORMALIZATION
    assert any("E112" in d for d in o.translation.diagnostics)
    assert "ARG-CIRC-001" in {d.code for d in (o.named_diagnostics or [])}
    assert o.release is not None and not o.release.permitted


@pytest.mark.parametrize("problem", [
    _two(V("a"), op("implies", V("a"), V("b")), V("b"), [("a", "Bool"), ("b", "Bool")]),
    _two(op("gt", V("dt"), I(41)), op("lt", V("dt"), I(50)), op("ge", V("dt"), I(41)), [("dt", "Int")]),
], ids=["modus ponens", "bounds that say more"])
def test_control_a_derivation_from_two_premises_is_no_circle(problem):
    o = _pipeline(problem)
    assert not any("E112" in d for d in (o.translation.diagnostics or []))
    assert "ARG-CIRC-001" not in {d.code for d in (o.named_diagnostics or [])}
