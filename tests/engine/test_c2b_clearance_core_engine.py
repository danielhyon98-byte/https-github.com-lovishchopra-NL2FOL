"""Engine behaviour fixed by the core fixer's second pass of the round-9 clearance:

* minor (restored-environment check, 12 Nov): with pydantic 2.14.3 a problem nested 500 levels deep was still rejected, but
  with E100 ("Recursion error - maximum validation depth exceeded", pydantic's ``recursion_depth_exceeded``) instead of the
  structural bound E303, because pydantic's own recursion limit stopped the validation before the engine's depth check
  ran. The nesting of the parsed JSON is now bounded before the schema library validates it, so E303 decides it whatever
  the library's version, and any recursion error the library reports is E303;
* minor (c2 translation-fidelity, ARG-HG-001 on a definitional link): "a species making over half of the individuals
  means most belong to one species" (ess-t15 s6.2) was a hasty generalisation; a majority read off a share above half is
  the share's definition, never a universal drawn from instances.
"""
from __future__ import annotations

import json
import time

import pytest
from pydantic_core import InitErrorDetails, PydanticCustomError, ValidationError

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine import validator as V
from epinoic_logic.engine.runner import verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import DEFAULT_LIMITS, Problem

from ..channel.c2b_core_support import translation
from ..core_hostile import SHAPES, one, sweep

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def _deep(levels: int) -> dict:
    expr: dict = {"op": "var", "name": "x"}
    for _ in range(levels):
        expr = {"op": "neg", "arg": expr}
    return {"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "consistency", "symbols": [{"name": "x", "sort": "Real"}],
            "premises": [{"id": "P", "expr": {"op": "gt", "left": expr, "right": {"op": "real", "value": "0"}}}]}


@pytest.mark.parametrize("form", ["json text", "mapping"])
def test_a_document_nested_beyond_the_bound_is_e303_before_the_schema_library_runs(form, monkeypatch):
    calls: list[int] = []

    class Watched:
        @staticmethod
        def model_validate(obj, **kw):
            calls.append(1)
            raise AssertionError("the schema library ran on an over-deep document")
    monkeypatch.setattr(V, "Problem", Watched)
    payload = json.dumps(_deep(500)) if form == "json text" else _deep(500)
    problem, outcome = V.parse_and_validate(payload, DEFAULT_LIMITS)
    monkeypatch.undo()
    assert problem is None and calls == [] and [d.code for d in outcome.diagnostics] == ["E303"], outcome.diagnostics
    r = verify(payload, CFG)
    assert r.status is S.INVALID_FORMALIZATION and {d.code for d in r.diagnostics} == {"E303"}


def test_controls_the_deepest_expression_the_limits_admit_still_validates_and_one_level_more_is_the_validators_e303():
    ok = _deep(DEFAULT_LIMITS.max_depth - 2)  # the comparison and the variable make two more levels
    problem, outcome = V.parse_and_validate(json.dumps(ok), DEFAULT_LIMITS)
    assert problem is not None and outcome.ok, outcome.diagnostics
    problem, outcome = V.parse_and_validate(json.dumps(_deep(DEFAULT_LIMITS.max_depth)), DEFAULT_LIMITS)
    assert not outcome.ok and [d.code for d in outcome.diagnostics] == ["E303"] and "exceeds max_depth" in outcome.diagnostics[0].message


def test_the_bound_is_never_below_what_a_valid_problem_needs():
    # an expression at the depth limit written with binary nodes (an args list per level) is the deepest JSON a valid problem has
    expr: dict = {"op": "var", "name": "x"}
    for _ in range(DEFAULT_LIMITS.max_depth - 2):
        expr = {"op": "add", "args": [expr, {"op": "real", "value": "1"}]}
    data = {"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "consistency", "symbols": [{"name": "x", "sort": "Real"}],
            "premises": [{"id": "P", "expr": {"op": "gt", "left": expr, "right": {"op": "real", "value": "0"}}}]}
    assert V.json_nesting_beyond(data, V.json_nesting_bound(DEFAULT_LIMITS)) is None
    problem, outcome = V.parse_and_validate(json.dumps(data), DEFAULT_LIMITS)
    assert problem is not None and outcome.ok, outcome.diagnostics


@pytest.mark.parametrize("kind,msg", [("recursion_loop", "Recursion error - cyclic reference detected"),
                                      ("recursion_depth_exceeded", "Recursion error - maximum validation depth exceeded")])
def test_any_recursion_error_of_the_schema_library_is_e303(kind, msg):
    exc = ValidationError.from_exception_data("Problem", [InitErrorDetails(type=PydanticCustomError(kind, msg), loc=("premises", 0), input=None)])
    [d] = V._pydantic_diagnostics(exc)
    assert d.code == "E303"
    other = ValidationError.from_exception_data("Problem", [InitErrorDetails(type=PydanticCustomError("missing", "Field required"), loc=("query",), input=None)])
    assert [x.code for x in V._pydantic_diagnostics(other)] == ["E100"]


def test_the_nesting_walk_is_linear_and_iterative():
    wide = {"a": [[{"b": [i]} for i in range(20_000)]]}
    t0 = time.process_time()
    assert V.json_nesting_beyond(wide, 10) is None
    deep: object = 0
    for _ in range(50_000):  # deeper than any recursion limit: the walk never recurses
        deep = [deep]
    assert V.json_nesting_beyond(deep, 100) == 101
    assert time.process_time() - t0 < 2.0


# ------------------------------------------------------------------------------ minor: a definitional majority (ARG-HG-001)


def _named(r) -> list[str]:
    return [d.code for d in (r.named_diagnostics or [])]


def test_ess_t15_s6_2_most_read_off_a_share_over_half_is_no_hasty_generalisation():
    p = Problem.model_validate(translation("c2", "ess-t15", "s6.2")["problem"])
    r = verify(p, CFG)
    assert r.status is S.ENTAILED and "ARG-HG-001" not in _named(r), _named(r)


def _majority(antecedent: dict, meaning: str) -> Problem:
    return Problem.model_validate({
        "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "s", "sort": "Real", "meaning": meaning, "grounding": {"kind": "arithmetic_fact"}},
                    {"name": "most", "sort": "Bool", "meaning": "most students in the country passed", "grounding": {"kind": "specialist_inference"}}],
        "premises": [{"id": "d", "expr": {"op": "eq", "left": {"op": "var", "name": "s"}, "right": {"op": "real", "value": "75"}}, "label": "9 of the 12 passed",
                      "grounding": {"kind": "arithmetic_fact"}},
                     {"id": "l", "expr": {"op": "implies", "left": antecedent, "right": {"op": "var", "name": "most"}}, "label": "so most passed",
                      "grounding": {"kind": "specialist_inference"}}],
        "conclusion": {"id": "c", "expr": {"op": "var", "name": "most"}}})


def test_controls_a_majority_drawn_from_a_sample_still_generalises():
    """A share over half of a sample ("9 of 12 students in our class") stated of a wider whole ("most students in the
    country") is still the hasty generalisation: the definitional reading covers only a share whose meaning names the same
    whole; and a threshold under half is no majority."""
    share = {"op": "gt", "left": {"op": "var", "name": "s"}, "right": {"op": "real", "value": "50"}}
    sample = _majority(share, "pass rate of the 12 students in Mrs Lee's class, percent")
    r = verify(sample, CFG)
    assert r.status is S.ENTAILED and "ARG-HG-001" in _named(r), _named(r)  # "most students in the country": a population of its own
    from epinoic_logic.engine.argument import _definitional_majority
    assert _definitional_majority(share, {"s": "share of woodland B's individuals in species 1, percent"})
    assert not _definitional_majority({"op": "gt", "left": {"op": "var", "name": "s"}, "right": {"op": "real", "value": "30"}},
                                      {"s": "share of woodland B's individuals in species 1, percent"})
    assert not _definitional_majority(share, {"s": "the number of beetles counted"})
    assert _definitional_majority({"op": "lt", "left": {"op": "real", "value": "1/2"}, "right": {"op": "var", "name": "s"}}, {"s": "the proportion of voters"})


# --------------------------------------------------------------------------- the new readers are linear (class sweep)


def _entries(text: str):
    from epinoic_logic.engine.argument import _definitional_majority, _widens
    share = {"op": "gt", "left": {"op": "var", "name": "s"}, "right": {"op": "real", "value": "50"}}
    yield "_definitional_majority", lambda: _definitional_majority(share, {"s": text})
    yield "_widens", lambda: _widens("most " + text, ["x", "country", text[:20]])
    yield "json_nesting_beyond", lambda: V.json_nesting_beyond({"notes": text, "list": [text, {"k": text}]}, V.json_nesting_bound(DEFAULT_LIMITS))
    yield "parse_and_validate", lambda: V.parse_and_validate(text)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c2b_engine_readers(shape):
    """Every reader this pass added to the engine, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_entries, texts=one(shape))
