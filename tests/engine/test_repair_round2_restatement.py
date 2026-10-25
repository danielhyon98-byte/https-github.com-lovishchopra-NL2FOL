"""Repair round 2 (fidelity-4 variant): a premise of the writer's own that is the conclusion in other terms is circular
whatever its arithmetic form. ``2 x dt = 82``, ``dt + 1 = 42`` and ``40 < dt < 42`` (over Int) for ``dt = 41`` are no
rewrite of the engine's normal form, so the engine decides the equivalence itself (``runner.equivalent_premises``): the
ENTAILED carries E112, and the translator rejects the encoding as INVALID_FORMALIZATION with E112 fed back for repair,
as it does for the forms the normal form reads. Controls: a step of working, a premise a check verified, a weaker or
different statement, and a derivation from two premises."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.runner import RESTATEMENT_STAGE, circular_premises, equivalent_premises
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, TranslationStatus, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
WRITER = {"kind": "specialist_inference", "certainty": "established"}


def _v(n):
    return {"op": "var", "name": n}


def _i(v):
    return {"op": "int", "value": str(v)}


def _r(v):
    return {"op": "real", "value": str(v)}


def _cmp(op, a, b):
    return {"op": op, "left": a, "right": b}


POINT = _cmp("eq", _v("dt"), _i(41))
RESTATEMENTS = {
    "scaled": _cmp("eq", {"op": "mul", "args": [_i(2), _v("dt")]}, _i(82)),
    "shifted": _cmp("eq", {"op": "add", "args": [_v("dt"), _i(1)]}, _i(42)),
    "between": {"op": "and", "args": [_cmp("lt", _i(40), _v("dt")), _cmp("lt", _v("dt"), _i(42))]},
}


def _problem(premises, conclusion=POINT, symbols=(("dt", "Int"),)) -> Problem:
    return Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": n, "sort": s, "meaning": "the doubling time in years" if n == "dt" else n} for n, s in symbols],
        "premises": [{"id": pid, "expr": e, "label": "the doubling time in other words", "grounding": g} for pid, e, g in premises],
        "conclusion": {"id": "C", "expr": conclusion, "label": "the doubling time is 41 years"}})


@pytest.mark.parametrize("name", sorted(RESTATEMENTS))
def test_an_arithmetic_restatement_held_by_the_writer_alone_is_e112(name):
    problem = _problem([("p1", RESTATEMENTS[name], WRITER)])
    assert circular_premises(problem) == []                    # beyond the normal form
    assert equivalent_premises(problem) == ["p1"]
    r = verify(problem, CFG)
    assert r.status is S.ENTAILED and "E112" in {d.code for d in r.diagnostics}
    assert RESTATEMENT_STAGE in {t.stage for t in r.timings}  # the test is timed inside the decision bound


@pytest.mark.parametrize("name", sorted(RESTATEMENTS))
def test_the_translator_rejects_an_arithmetic_restatement_for_repair(name):
    text = "The doubling time is 41 years."
    problem = _problem([("p1", RESTATEMENTS[name], WRITER)]).model_dump(mode="json", exclude_none=True)
    obj = {"interpretation": {"reading": "as written", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None,
           "problem": problem}
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="geography-specialist", subject="Geography", task_type="data_response")
    claim = ClaimRecord(**ids, claim_id="c", claim_text=text, claim_role="quantitative")
    report = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), claims=[claim], supplied_texts=[],
                              created_at="2026-10-17T10:00:00Z")
    outcome = verify_claim(claim, report, Translator(FixtureTranslationProvider({"c": json.dumps(obj)}), config=CFG), config=CFG)
    assert outcome.translation.status is TranslationStatus.INVALID_FORMALIZATION
    assert any("E112" in d and "in other terms" in d for d in outcome.translation.diagnostics)
    assert outcome.display_status is S.INVALID_FORMALIZATION


# ------------------------------------------------------------------------------------------------------- controls

def test_a_step_of_working_is_no_circle():
    rate = _problem([("w", _cmp("eq", _v("rate"), {"op": "add", "args": [_r("2.0"), {"op": "mul", "args": [_r("0.40"), _r("60")]}]}), WRITER)],
                    _cmp("eq", _v("rate"), _r("26")), (("rate", "Real"),))
    assert equivalent_premises(rate) == []
    assert "E112" not in {d.code for d in verify(rate, CFG).diagnostics}


def test_a_restatement_a_check_verified_is_a_transcription():
    verified = {"kind": "task_setting", "verified": True, "certainty": "established", "source_refs": [{"document_id": "task", "excerpt": "2dt = 82"}]}
    problem = _problem([("p1", RESTATEMENTS["scaled"], verified)])
    assert equivalent_premises(problem) == []
    assert "E112" not in {d.code for d in verify(problem, CFG).diagnostics}


@pytest.mark.parametrize("premise, conclusion", [
    (_cmp("gt", _v("dt"), _i(41)), _cmp("ge", _v("dt"), _i(41))),          # a stronger statement: entails, is not equivalent
    (_cmp("eq", {"op": "mul", "args": [_i(2), _v("dt")]}, _i(82)), _cmp("gt", _v("dt"), _i(40))),
])
def test_a_premise_that_entails_the_point_without_restating_it_is_no_circle(premise, conclusion):
    problem = _problem([("p1", premise, WRITER)], conclusion)
    assert equivalent_premises(problem) == []
    r = verify(problem, CFG)
    assert r.status is S.ENTAILED and "E112" not in {d.code for d in r.diagnostics}


def test_two_bounds_of_the_writers_own_that_together_restate_the_point_are_a_circle():
    """Rewritten to the stricter rule of repair round 4 (fidelity-4 variant): this was a control ("a derivation from two
    premises is no circle"), but the two bounds, held only by the writer, say together exactly the point, as one premise
    holding both does (E112). The joint equivalence is decided once, after no single premise restated the point."""
    problem = _problem([("p1", _cmp("le", _v("dt"), _i(41)), WRITER), ("p2", _cmp("ge", _v("dt"), _i(41)), WRITER)])
    assert equivalent_premises(problem) == ["p1", "p2"]
    assert "E112" in {d.code for d in verify(problem, CFG).diagnostics}


def test_control_two_premises_that_entail_the_point_without_restating_it_are_no_circle():
    """Control of the joint rule: two bounds of the writer's own that entail the point but say more than it ("dt > 41" and
    "dt < 50" for "dt >= 41") restate nothing."""
    problem = _problem([("p1", _cmp("gt", _v("dt"), _i(41)), WRITER), ("p2", _cmp("lt", _v("dt"), _i(50)), WRITER)], _cmp("ge", _v("dt"), _i(41)))
    assert equivalent_premises(problem) == []
    assert "E112" not in {d.code for d in verify(problem, CFG).diagnostics}


def test_no_budget_decides_nothing():
    problem = _problem([("p1", RESTATEMENTS["scaled"], WRITER)])
    assert equivalent_premises(problem, budget_ms=0) == []
