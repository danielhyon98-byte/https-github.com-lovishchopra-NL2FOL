"""Engine regressions from the overseer round-1 findings: trust rules on groundings, vacuous
results, the closed-conclusion check and the process-global Z3 memory budget."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from epinoic_logic.engine.errors import DiagnosticCode
from epinoic_logic.engine.procedures import MEMORY_FLOOR_MB
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.runner import is_ungrounded, is_unverified, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.engine.validator import validate_problem
from epinoic_logic.ir.schema import Grounding, Problem

from .conftest import V, cmp, I, make_problem

CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)


def chain(grounding_e1: dict) -> dict:
    return make_problem("entailment", [("q", "Bool"), ("p", "Bool")], [
        ("E1", V("q"), {"grounding": grounding_e1}),
        ("L1", {"op": "implies", "left": V("q"), "right": V("p")}, {"grounding": {"kind": "specialist_inference", "certainty": "probable"}}),
    ], ("C", V("p")))


def test_unchecked_quotation_is_an_ungrounded_dependency():
    r = verify(Problem.model_validate(chain({"kind": "quotation"})), CFG)
    assert r.status is S.ENTAILED and sorted(r.ungrounded_dependencies) == ["E1", "L1"]
    checked = verify(Problem.model_validate(chain({"kind": "quotation", "verified": True})), CFG)
    assert checked.ungrounded_dependencies == ["L1"]  # an in-process Problem may carry a check result
    assert is_ungrounded(Grounding(kind="quotation")) and not is_ungrounded(Grounding(kind="quotation", verified=True))


def test_raw_payload_asserting_verified_true_is_demoted_and_recorded():
    raw = json.dumps(chain({"kind": "quotation", "verified": True}))
    r = verify(raw, CFG)
    assert r.status is S.ENTAILED and sorted(r.ungrounded_dependencies) == ["E1", "L1"]
    discards = [d for d in r.diagnostics if d.code == DiagnosticCode.SELF_CERTIFICATION_REJECTED.value]
    assert len(discards) == 1 and discards[0].path == "premises[0].grounding"
    # verified=false on the raw path is kept: it only weakens
    weak = verify(json.dumps(chain({"kind": "quotation", "verified": False})).encode(), CFG)
    assert "E1" in weak.ungrounded_dependencies and not [d for d in weak.diagnostics if d.code == "E505"]


def test_asserted_but_unchecked_groundings_are_listed_as_unverified():
    data = make_problem("entailment", [("q", "Bool"), ("p", "Bool")], [
        ("S1", V("q"), {"grounding": {"kind": "supplied_text"}}),
        ("L1", {"op": "implies", "left": V("q"), "right": V("p")}, {"grounding": {"kind": "knowledge_document"}}),
        ("T1", {"op": "or", "args": [V("q"), V("p")]}, {"grounding": {"kind": "task_setting"}}),
    ], ("C", V("p")))
    r = verify(Problem.model_validate(data), CFG)
    assert r.status is S.ENTAILED and r.ungrounded_dependencies == []
    assert sorted(r.unverified_dependencies) == ["L1", "S1"]  # T1 is task-given; nothing is called established silently
    assert is_unverified(Grounding(kind="library_source")) and not is_unverified(Grounding(kind="arithmetic_fact"))
    assert not is_unverified(Grounding(kind="specialist_inference"))  # already ungrounded


def test_vacuous_entailment_and_empty_consistency_carry_e108():
    taut = make_problem("entailment", [("p", "Bool")], [], ("C", {"op": "or", "args": [V("p"), {"op": "not", "arg": V("p")}]}))
    r = verify(Problem.model_validate(taut), CFG)
    assert r.status is S.ENTAILED and r.premises_relied_on == []
    assert [d.code for d in r.diagnostics] == [DiagnosticCode.VACUOUS_RESULT.value] and "no premise" in r.diagnostics[0].message
    empty = make_problem("consistency", [("p", "Bool")], [])
    r2 = verify(Problem.model_validate(empty), CFG)
    assert r2.status is S.CONSISTENT and [d.code for d in r2.diagnostics] == ["E108"]
    # a proof that uses a premise is not vacuous
    data = make_problem("entailment", [("p", "Bool")], [("P", V("p"), {"grounding": {"kind": "supplied_text"}})], ("C", V("p")))
    r3 = verify(Problem.model_validate(data), CFG)
    assert r3.status is S.ENTAILED and r3.premises_relied_on == ["P"] and r3.diagnostics == [] and r3.unverified_dependencies == ["P"]


def test_closed_conclusion_is_invalid_formalization():
    data = make_problem("entailment", [("p", "Bool")], [("P", V("p"))], ("C", {"op": "bool", "value": True}))
    outcome = validate_problem(Problem.model_validate(data))
    assert not outcome.ok and [d.code for d in outcome.diagnostics] == [DiagnosticCode.CLOSED_CONCLUSION.value]
    r = verify(Problem.model_validate(data), CFG)
    assert r.status is S.INVALID_FORMALIZATION and r.diagnostics[0].code == "E109"


def test_memory_budget_floor_is_enforced_by_the_schema():
    with pytest.raises(ValidationError):
        SolverConfig(memory_max_mb=16)
    assert SolverConfig(memory_max_mb=MEMORY_FLOOR_MB).memory_max_mb == MEMORY_FLOOR_MB == 128


_SUBPROCESS_CASE = r'''
import sys, json
import z3
from pydantic import ValidationError
from epinoic_logic.engine import verify
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.procedures import MEMORY_FLOOR_MB
P = {"ir_version": "1.0", "problem_id": "p1", "request_id": "req1", "claim_id": "c1", "query": "entailment",
     "symbols": [{"name": "p", "sort": "Bool"}, {"name": "q", "sort": "Bool"}],
     "premises": [{"id": "A", "expr": {"op": "var", "name": "p"}}, {"id": "B", "expr": {"op": "implies", "left": {"op": "var", "name": "p"}, "right": {"op": "var", "name": "q"}}}],
     "conclusion": {"id": "C", "expr": {"op": "var", "name": "q"}}}
try:
    SolverConfig(memory_max_mb=16)
    print("schema accepted 16")
except ValidationError:
    print("schema rejected 16")
r1 = verify(P, SolverConfig(memory_max_mb=MEMORY_FLOOR_MB))
print("call1", r1.status.value, z3.get_param("memory_max_size"))
r2 = verify(P, SolverConfig())
print("call2", r2.status.value)
r3 = verify(P, SolverConfig(memory_max_mb=None))
print("call3", r3.status.value)
'''


def test_minimum_memory_budget_then_default_requests_never_crash_the_process():
    proc = subprocess.run([sys.executable, "-I", "-c", _SUBPROCESS_CASE], capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, (proc.returncode, proc.stderr[-500:])
    lines = proc.stdout.strip().splitlines()
    assert lines[0] == "schema rejected 16"
    assert lines[1].startswith("call1 ENTAILED") and lines[1].split()[-1] == str(MEMORY_FLOOR_MB)
    assert lines[2] == "call2 ENTAILED" and lines[3] == "call3 ENTAILED"
