"""Integration gate, round 1: the engine's findings (formal-robustness-1, formal-robustness-2, the undecided coverage probe,
the argument stage's model extraction and budget, the argument stage on undecided results, the vacuous ENTAILED's core).

* formal-robustness-1 (critical): a model value was converted to text outside the solver's timeout and without a bound, twice
  per call (the discarded consistency precheck's model and the counterexample's): a linear problem within the validation
  limits held a solver slot for 5 to 8 s with 24,840-digit values. Every value is now checked on the solver's own numbers
  before it is converted (``procedures.MAX_MODEL_VALUE_DIGITS``); a value beyond the bound makes the answer UNKNOWN (never a
  success) and the extraction is timed as its own stage.
* formal-robustness-2 (critical): the two coverage probes after a COUNTEREXAMPLE each ran with the full timeout and outside
  the result's timings. They now share one budget (the configuration's timeout in all) and each is timed.
* An undecided coverage probe was read as "decided: nothing to name": at small budgets the COUNTEREXAMPLE stood with an
  ARG-INV-001 warning, at larger ones it was E110 (no verdict). An undecided probe is now recorded: with source-linked
  evidence it withholds the counterexample (E110 or E111, the message says the probe was undecided), and the argument stage
  records ``incomplete:coverage_probe_undecided`` and fires nothing.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.engine import procedures as procedures_module
from epinoic_logic.engine import runner as runner_module
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.procedures import MAX_MODEL_VALUE_DIGITS, MODEL_OUT_OF_RANGE
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.runner import PROBE_STAGES, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.named import rules_state

from ..timing import measure

KEY = b"k" * 32
BIG = "9" * 40


def V(n):
    return {"op": "var", "name": n}


def I(v):
    return {"op": "int", "value": str(v)}


def R(v):
    return {"op": "real", "value": str(v)}


def op(o, *a):
    if o in ("not", "neg", "to_real"):
        return {"op": o, "arg": a[0]}
    if o in ("and", "or", "add", "mul"):
        return {"op": o, "args": list(a)}
    return {"op": o, "left": a[0], "right": a[1]}


def problem(symbols, premises, conclusion=None, query="entailment"):
    d = {"problem_id": "p1", "request_id": "r1", "claim_id": "c1", "query": query,
         "symbols": [s if isinstance(s, dict) else {"name": s[0], "sort": s[1]} for s in symbols],
         "premises": [p if "id" in p else {"id": f"p{i}", "expr": p} for i, p in enumerate(premises)]}
    if conclusion is not None:
        d["conclusion"] = {"id": "concl", "expr": conclusion}
    return Problem.model_validate(d)


def run(p, policy="linear", timeout_ms=2000, **kw):
    cfg = policy_config(policy, SolverConfig(timeout_ms=timeout_ms))
    return verify(p, cfg, limits=policy_limits(policy), signing_key=KEY, key_id="t", **kw)


def big_chain(n: int, query="entailment"):
    """x = 99..9 (40 digits), y_i = (99..9)^31 * y_(i-1): every constant within the limits, y_n about 1,240 n digits."""
    syms = [("x", "Int")] + [(f"y{i}", "Int") for i in range(1, n + 1)]
    prem = [op("eq", V("x"), I(BIG))]
    prev = "x"
    for i in range(1, n + 1):
        prem.append(op("eq", V(f"y{i}"), op("mul", *([I(BIG)] * 31 + [V(prev)]))))
        prev = f"y{i}"
    return problem(syms, prem, op("lt", V(prev), I(0)) if query == "entailment" else None, query=query)


# ============================================================================================ formal-robustness-1
def test_a_model_of_huge_values_is_never_converted_and_the_call_returns_within_a_bound():
    p = big_chain(20)  # the finding's input: 24,840-digit values, 5 to 8 s per call before the fix
    timing = measure(lambda: run(p), bound=2.0, repeat=3, label="verify, 20-link chain of 40-digit constant products")
    assert timing.holds, timing
    for r in timing.results:
        assert r.status is S.UNKNOWN and r.counterexample is None and r.witness_model is None
        assert MODEL_OUT_OF_RANGE in (r.reason_unknown or "") and [d.code for d in r.diagnostics] == ["E401"]
        assert "could not be reported" in r.diagnostics[0].message
        stages = [t.stage for t in r.timings]
        assert stages.count("model") == 1 and stages.index("model") > stages.index("entailment")  # timed; the precheck extracts none
        assert len(r.model_dump_json()) < 200_000


@pytest.mark.parametrize("query", ["consistency", "satisfiability"])
def test_a_witness_of_huge_values_is_unknown_too(query):
    r = run(big_chain(3, query=query))
    assert r.status is S.UNKNOWN and r.witness_model is None and MODEL_OUT_OF_RANGE in r.reason_unknown


def test_values_within_the_bound_are_reported_exactly_as_before():
    # a 1,000-digit value is within the bound and reported exactly; the precheck of an entailment run extracts no model
    edge = "9" * MAX_MODEL_VALUE_DIGITS
    p = problem([("x", "Int"), ("y", "Int")], [op("eq", V("x"), I(BIG)), op("eq", V("y"), op("mul", I(BIG), I(BIG), V("x")))], op("lt", V("y"), I(0)))
    r = run(p)
    assert r.status is S.COUNTEREXAMPLE and {a.symbol: a.value for a in r.counterexample.assignments}["y"] == str(int(BIG) ** 3)
    assert [t.stage for t in r.timings].count("model") == 1
    within = procedures_module._within_bound
    import z3
    ctx = z3.Context()
    bound = z3.IntVal("1" + "0" * MAX_MODEL_VALUE_DIGITS, ctx)
    assert within(z3.IntVal(edge, ctx), bound) and not within(z3.IntVal(edge + "9", ctx), bound)
    assert within(z3.RealVal(f"1/{edge}", ctx), bound) and not within(z3.RealVal(f"1/{edge}9", ctx), bound)


def test_the_argument_stage_reports_a_huge_counterexample_as_incomplete_within_its_budget():
    # the argument stage's R0 run extracted the counterexample of the established premises outside its budget (2,029 ms of a
    # 400 ms stage at timeout_ms=100); a value beyond the bound is not converted and the diagnosis says why it is incomplete
    syms = [("x", "Int"), ("b", "Bool")] + [(f"y{i}", "Int") for i in range(1, 21)]
    fact = {"kind": "arithmetic_fact", "verified": True}
    prem = [{"id": "p0", "expr": op("eq", V("x"), I(BIG)), "grounding": fact}]
    prev = "x"
    for i in range(1, 21):
        prem.append({"id": f"p{i}", "expr": op("eq", V(f"y{i}"), op("mul", *([I(BIG)] * 31 + [V(prev)]))), "grounding": fact})
        prev = f"y{i}"
    prem.append({"id": "w1", "expr": op("implies", op("gt", V(prev), I(0)), V("b")), "grounding": {"kind": "specialist_inference"}})
    p = problem(syms, prem, V("b"))
    timing = measure(lambda: run(p, timeout_ms=100), bound=2.0, repeat=3, label="argument stage over a 20-link chain")
    assert timing.holds, timing
    for r in timing.results:
        assert r.status is S.ENTAILED and rules_state(r.argument_rules) == ("incomplete", "model_out_of_range")
        assert not r.named_diagnostics


def test_a_run_that_overruns_the_argument_stage_budget_makes_the_diagnosis_incomplete(monkeypatch):
    from epinoic_logic.engine import argument as argument_module
    original = argument_module._Runs._decide

    def slow(self, *a, **k):
        out = original(self, *a, **k)
        self.started -= 10.0  # as if the run (its extraction included) had taken ten seconds
        return out

    monkeypatch.setattr(argument_module._Runs, "_decide", slow)
    p = problem([("x", "Int"), ("b", "Bool")], [{"id": "w1", "expr": op("implies", op("gt", V("x"), I(0)), V("b")), "grounding": {"kind": "assumption"}},
                                                {"id": "f1", "expr": op("eq", V("x"), I(5)), "grounding": {"kind": "assumption"}}], V("b"))
    r = run(p)
    assert r.status is S.ENTAILED and rules_state(r.argument_rules) == ("incomplete", "budget_exhausted")


# ============================================================================================ formal-robustness-2
def _defined_chain(k: int):
    """b <-> (y1 = x*x and y2 = y1*y1 ... and y_k = 2), conclusion b: the E110 shape; its re-run is hard for the solver."""
    syms = [("b", "Bool"), ("x", "Real")] + [(f"y{i}", "Real") for i in range(1, k + 1)]
    parts = [op("eq", V("y1"), op("mul", V("x"), V("x")))]
    for i in range(2, k + 1):
        parts.append(op("eq", V(f"y{i}"), op("mul", V(f"y{i - 1}"), V(f"y{i - 1}"))))
    parts.append(op("eq", V(f"y{k}"), R(2)))
    return problem(syms, [op("iff", V("b"), op("and", *parts))], V("b"))


def test_the_coverage_probes_share_one_timeout_and_are_timed():
    p = _defined_chain(8)  # the finding's input: 2.24 s wall at timeout_ms=2000, timings summing to 57 ms
    timing = measure(lambda: run(p, "nonlinear", timeout_ms=1000), bound=2.6, repeat=3, label="coverage probes after a COUNTEREXAMPLE")
    assert timing.holds, timing
    for r in timing.results:
        assert r.status is S.COUNTEREXAMPLE
        probes = [t for t in r.timings if t.stage in PROBE_STAGES]
        assert probes and sum(t.ms for t in probes) <= 1000 + 250  # one timeout in all, with a margin for the call itself
        # the whole call is accounted for: decision, probes and diagnosis are in the timings
        assert sum(t.ms for t in r.timings) >= 0.5 * max(t.ms for t in probes)


def test_a_probe_with_no_time_left_is_undecided_and_never_read_as_decided(monkeypatch):
    monkeypatch.setattr(runner_module, "_probe_deadline", lambda config: time.perf_counter() - 1.0)  # the probes' budget already spent
    vg = {"kind": "task_setting", "verified": True}
    p = problem([{"name": "b", "sort": "Bool"}, {"name": "n", "sort": "Int", "grounding": vg}],
                [{"id": "def_b", "expr": op("iff", V("b"), op("eq", V("n"), I(17))), "grounding": vg}], V("b"))
    r = run(p)
    assert r.status is S.COUNTEREXAMPLE and [d.code for d in r.diagnostics] == ["E110"]
    assert "probe undecided" in r.diagnostics[0].message
    assert rules_state(r.argument_rules) == ("incomplete", "coverage_probe_undecided") and not r.named_diagnostics
    # with time left the same problem is decided: E110 from the re-run, and the diagnosis completes
    monkeypatch.undo()
    r2 = run(p)
    assert r2.status is S.COUNTEREXAMPLE and [d.code for d in r2.diagnostics] == ["E110"] and "probe undecided" not in r2.diagnostics[0].message
    assert rules_state(r2.argument_rules)[0] == "complete"


def test_an_undecided_probe_without_source_evidence_leaves_the_counterexample_and_records_it(monkeypatch):
    monkeypatch.setattr(runner_module, "_probe_deadline", lambda config: time.perf_counter() - 1.0)
    p = problem([("b", "Bool"), ("n", "Int")], [op("iff", V("b"), op("eq", V("n"), I(17)))], V("b"))
    r = run(p)
    assert r.status is S.COUNTEREXAMPLE and r.diagnostics == []  # W110 needs the decided re-run; nothing withholds the verdict
    assert rules_state(r.argument_rules) == ("incomplete", "coverage_probe_undecided") and not r.named_diagnostics


def test_the_finding_case_gives_one_diagnostic_whatever_the_budget():
    """b, x, y, z verified; b <-> (x^3 + y^3 + z^3 = 3 and x*y*z = 1/2); conclusion b. Before the fix: at 50 ms a
    COUNTEREXAMPLE with an ARG-INV-001 warning, at 120 ms E110 (no verdict)."""
    vg = {"kind": "task_setting", "verified": True}
    x, y, z = V("x"), V("y"), V("z")
    cmp = op("and", op("eq", op("add", op("mul", x, x, x), op("mul", y, y, y), op("mul", z, z, z)), R(3)), op("eq", op("mul", x, y, z), R("1/2")))
    p = problem([{"name": "b", "sort": "Bool", "grounding": vg}] + [{"name": n, "sort": "Real", "grounding": vg} for n in "xyz"],
                [{"id": "def_b", "expr": op("iff", V("b"), cmp)}], V("b"))
    for timeout_ms in (50, 200):
        r = run(p, "nonlinear", timeout_ms=timeout_ms)
        assert r.status is S.COUNTEREXAMPLE and [d.code for d in r.diagnostics] == ["E110"], timeout_ms
        assert not any(d.code == "ARG-INV-001" for d in r.named_diagnostics or []), timeout_ms
        state = rules_state(r.argument_rules)
        assert state[0] == "complete" or state == ("incomplete", "coverage_probe_undecided"), timeout_ms


# ============================================================================================ argument stage on undecided results
def test_an_undecided_result_carries_no_diagnosis_and_never_reads_none_found():
    from epinoic_logic.named import diagnosis_section
    p = problem([("x", "Int"), ("y", "Int")], [op("gt", V("x"), V("y"))], op("gt", op("add", V("x"), I(1)), V("y")))
    r = verify(p, SolverConfig(rlimit=1), signing_key=KEY, key_id="t")
    assert r.status in (S.TIMEOUT, S.UNKNOWN)
    assert r.argument_rules is None and rules_state(r.argument_rules) == ("not_computed", None) and not r.named_diagnostics
    lines = diagnosis_section([], engine_state=rules_state(r.argument_rules)[0])
    assert lines and "not computed" in lines[0] and not any("none found" in x for x in lines)


# ============================================================================================ correctness-7
def test_a_vacuous_entailed_carries_its_core_when_the_flag_is_set():
    p = problem([("x", "Int")], [op("gt", V("x"), I(0))], op("or", op("gt", V("x"), I(3)), op("le", V("x"), I(3))))
    r = verify(p, SolverConfig(produce_unsat_core=True))
    assert r.status is S.ENTAILED and [d.code for d in r.diagnostics] == ["E108"]
    assert r.unsat_core is not None and r.unsat_core.premise_ids == [] and r.unsat_core.includes_negated_conclusion is True
    off = verify(p, SolverConfig(produce_unsat_core=False))
    assert off.unsat_core is None and off.premises_relied_on == r.premises_relied_on == []
