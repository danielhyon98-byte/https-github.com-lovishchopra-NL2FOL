import json

import pytest

from epinoic_logic.engine.compiler import compile_problem
from epinoic_logic.engine.procedures import run_consistency, run_entailment, run_satisfiability
from epinoic_logic.engine.provenance import verify_signature
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S, is_definitive
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Limits, Problem

from .conftest import I, R, V, cmp, make_problem

CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)


def P(data):
    return Problem.model_validate(data)


def test_entailment_transitivity(transitivity):
    r = verify(P(transitivity), CFG)
    assert r.status is S.ENTAILED and is_definitive(r.status)
    assert sorted(r.premises_relied_on) == ["P1", "P2"]
    assert r.unsat_core is not None and r.unsat_core.includes_negated_conclusion
    assert r.binding.smt2 and "(not" in r.binding.smt2
    assert r.ungrounded_dependencies == ["P1", "P2"]  # no grounding metadata at all -> ungrounded
    assert [t.stage for t in r.timings][:3] == ["validate", "compile", "consistency"]


def test_counterexample_is_exact_and_really_violates_conclusion():
    data = make_problem("entailment", [("x", "Int"), ("y", "Int")], [("P1", cmp("gt", V("x"), V("y")))], ("C", cmp("gt", V("x"), {"op": "add", "args": [V("y"), I(1)]})))
    r = verify(P(data), CFG)
    assert r.status is S.COUNTEREXAMPLE and r.counterexample is not None
    vals = {a.symbol: int(a.value) for a in r.counterexample.assignments}
    assert vals["x"] > vals["y"] and not (vals["x"] > vals["y"] + 1)


def test_inconsistent_premises_with_core_and_vacuous_entailment_guard():
    data = make_problem("entailment", [("x", "Int")], [("P1", cmp("gt", V("x"), I(0))), ("P2", cmp("lt", V("x"), I(0))), ("P3", cmp("gt", V("x"), I(-100)))], ("C", cmp("eq", V("x"), I(42))))
    r = verify(P(data), CFG)
    assert r.status is S.INCONSISTENT_PREMISES
    assert sorted(r.unsat_core.premise_ids) == ["P1", "P2"] and not r.unsat_core.includes_negated_conclusion
    assert r.counterexample is None


def test_int_vs_real_two_x_equals_one():
    over_int = make_problem("satisfiability", [("x", "Int")], [("P", cmp("eq", {"op": "mul", "args": [I(2), V("x")]}, I(1)))])
    over_real = make_problem("satisfiability", [("x", "Real")], [("P", cmp("eq", {"op": "mul", "args": [R(2), V("x")]}, R(1)))])
    assert verify(P(over_int), CFG).status is S.UNSATISFIABLE
    r = verify(P(over_real), CFG)
    assert r.status is S.SATISFIABLE and r.witness_model[0].value == "1/2"


def test_consistency_query():
    data = make_problem("consistency", [("a", "Bool"), ("b", "Bool")], [("P1", {"op": "implies", "left": V("a"), "right": V("b")}), ("P2", V("a"))])
    r = verify(P(data), CFG)
    assert r.status is S.CONSISTENT and {m.symbol: m.value for m in r.witness_model} == {"a": "true", "b": "true"}


def test_timeout_is_not_success():
    # Hard nonlinear integer problem; policy opened for the test only.
    data = make_problem("satisfiability", [("a", "Int"), ("b", "Int"), ("c", "Int")], [
        ("P1", cmp("gt", V("a"), I(1))), ("P2", cmp("gt", V("b"), I(1))), ("P3", cmp("gt", V("c"), I(1))),
        ("P4", cmp("eq", {"op": "add", "args": [{"op": "mul", "args": [V("a"), V("a"), V("a")]}, {"op": "mul", "args": [V("b"), V("b"), V("b")]}]}, {"op": "mul", "args": [V("c"), V("c"), V("c")]})),
        ("P5", cmp("lt", V("c"), I(10 ** 12))),
    ])
    r = verify(P(data), SolverConfig(timeout_ms=30, memory_max_mb=None), Limits(allow_nonlinear=True))
    assert r.status in (S.TIMEOUT, S.UNKNOWN) and not is_definitive(r.status)
    assert r.reason_unknown and any(d.code in ("E400", "E401", "E402") for d in r.diagnostics)


def test_argument_chain_reports_ungrounded_inferences(argument_chain):
    r = verify(P(argument_chain), CFG)
    assert r.status is S.ENTAILED
    assert set(r.premises_relied_on) <= {"E1", "L1", "L2", "S1"} and {"L1", "L2"} <= set(r.premises_relied_on)
    assert sorted(r.ungrounded_dependencies) == ["L1", "L2"]
    # Removing the second link breaks the chain: the point no longer follows.
    broken = dict(argument_chain)
    broken["premises"] = [p for p in argument_chain["premises"] if p["id"] != "L2"]
    r2 = verify(P(broken), CFG)
    assert r2.status is S.COUNTEREXAMPLE
    assert {a.symbol: a.value for a in r2.counterexample.assignments}["p"] == "false"


def test_hallucinated_quotation_flagged_when_relied_on():
    data = make_problem("entailment", [("q", "Bool"), ("p", "Bool")], [
        ("E1", V("q"), {"grounding": {"kind": "quotation", "verified": False}}),
        ("L1", {"op": "implies", "left": V("q"), "right": V("p")}, {"grounding": {"kind": "rubric_rule", "verified": True}}),
    ], ("C", V("p")))
    r = verify(P(data), CFG)
    assert r.status is S.ENTAILED and r.ungrounded_dependencies == ["E1"]


def test_binding_changes_with_representation_and_config(transitivity):
    r1 = verify(P(transitivity), CFG)
    changed = json.loads(json.dumps(transitivity))
    changed["premises"][0]["label"] = "a different gloss"
    r2 = verify(P(changed), CFG)
    assert r1.binding.problem_digest != r2.binding.problem_digest and r1.binding.binding_digest != r2.binding.binding_digest
    r3 = verify(P(transitivity), SolverConfig(timeout_ms=4999, memory_max_mb=None))
    assert r3.binding.problem_digest == r1.binding.problem_digest and r3.binding.config_digest != r1.binding.config_digest


def test_signature_roundtrip_and_tamper(transitivity):
    key = b"k" * 32
    r = verify(P(transitivity), CFG, signing_key=key, key_id="test")
    assert r.signature and verify_signature(r, key)
    assert not verify_signature(r, b"wrong" * 8)
    tampered = r.model_copy(update={"status": S.COUNTEREXAMPLE})
    assert not verify_signature(tampered, key)
    tampered2 = r.model_copy(update={"ungrounded_dependencies": []})
    assert not verify_signature(tampered2, key)


def test_invalid_and_unsupported_payloads_become_results_not_exceptions():
    r = verify(b'{"op": "exec"}', CFG)
    assert r.status is S.INVALID_FORMALIZATION and r.query is None and r.binding.problem_digest
    data = make_problem("consistency", [("x", "Int"), ("y", "Int")], [("P", cmp("gt", {"op": "mul", "args": [V("x"), V("y")]}, I(0)))])
    r = verify(json.dumps(data), CFG)
    assert r.status is S.UNSUPPORTED and r.diagnostics[0].code == "E201"
    r = verify("not json at all", CFG)
    assert r.status is S.INVALID_FORMALIZATION


def test_internal_error_path(monkeypatch, transitivity):
    import epinoic_logic.engine.runner as vmod

    def boom(problem):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(vmod, "compile_problem", boom)
    r = verify(P(transitivity), CFG)
    assert r.status is S.INTERNAL_ERROR and r.diagnostics[0].code == "E900" and "secret" not in r.diagnostics[0].message


def test_procedures_direct(transitivity):
    c = compile_problem(P(transitivity))
    assert run_consistency(c, CFG).status is S.CONSISTENT
    assert run_satisfiability(c, CFG).status is S.SATISFIABLE
    e = run_entailment(c, CFG)
    assert e.status is S.ENTAILED and e.includes_negated_conclusion and e.smt2
