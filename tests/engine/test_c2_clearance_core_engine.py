"""Engine behaviour found wanting by the round-9 clearance overseers (integrated round c2), fixed by the core fixer:

* critical: every COUNTEREXAMPLE displayed in c2 was a false verdict on a correct claim, produced by an encoding that left
  out what its own link or definition needs: ess-p9c s4.1 (a link's condition "share2_pct > share1_pct" on shares no premise
  gives, so the countermodel made them equal; no coverage diagnostic fired) and ch-p9b s5.3 (the defining relation c = n/V
  written in the conclusion, so the countermodel gave c another value; only the advisory W111 fired). Such a COUNTEREXAMPLE
  is now no verdict (E111, rule omitted-condition); a counterexample that survives the omitted condition or definition (a
  wrong figure, a wrong step), a Bool link the claim never established (the missing link ARG-NS-002 names) and an atom the
  translator declared keep their verdict;
* the class sweep (input stall): the new probe stays inside the coverage probes' one shared timeout on the largest problems
  the IR admits, so it adds no unbounded work.

The recorded material is in ``tests/channel/data/c2_core_material.json`` (copied verbatim from the round)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.runner import OMITTED_CONDITION, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.outcome import display_status_for

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
C2 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "c2_core_material.json").read_text())


def recorded(task: str, cid: str) -> Problem:
    return Problem.model_validate(C2["translations"][task][cid]["problem"])


def codes(r) -> list[str]:
    return [d.code for d in r.diagnostics]


def omitted(r) -> list:
    return [d for d in r.diagnostics if d.code == "E111" and d.message.startswith(OMITTED_CONDITION)]


@pytest.mark.parametrize("task,cid,what", [("ess-p9c", "s4.1", "condition of a link on symbol(s) share1_pct, share2_pct"),
                                           ("ch-p9b", "s5.3", "defines symbol(s) c_stock")])
def test_a_counterexample_only_through_what_the_encoding_left_out_is_no_verdict(task, cid, what):
    r = verify(recorded(task, cid), CFG)
    assert r.status is S.COUNTEREXAMPLE
    [d] = omitted(r)
    assert what in d.message and "W111" not in codes(r), codes(r)


def _shares(cond_kind: str = "arithmetic_fact", with_values: bool = False, *, second: str = "410000/864000") -> Problem:
    """The ess-p9c s4.1 shape at its smallest: a link 'reduced storage and a larger share mean more surface flow'."""
    V = lambda n: {"op": "var", "name": n}
    premises = [{"id": "ev", "expr": V("storage_reduced")},
                {"id": "link", "expr": {"op": "implies", "left": {"op": "and", "args": [V("storage_reduced"), {"op": "gt", "left": V("share2"), "right": V("share1")}]},
                                        "right": V("more_flow")}}]
    if with_values:
        premises += [{"id": "s1", "expr": {"op": "eq", "left": V("share1"), "right": {"op": "real", "value": "182000/912000"}}},
                     {"id": "s2", "expr": {"op": "eq", "left": V("share2"), "right": {"op": "real", "value": second}}}]
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "s4.1", "query": "entailment",
                                   "symbols": [{"name": "storage_reduced", "sort": "Bool"}, {"name": "more_flow", "sort": "Bool"},
                                               {"name": "share1", "sort": "Real", "grounding": {"kind": cond_kind}},
                                               {"name": "share2", "sort": "Real", "grounding": {"kind": cond_kind}}],
                                   "premises": premises, "conclusion": {"id": "c", "expr": V("more_flow")}})


def test_the_omitted_condition_rule_keeps_every_real_verdict():
    assert omitted(verify(_shares(), CFG))                                    # the shares are declared stated figures, none is given
    assert verify(_shares(with_values=True), CFG).status is S.ENTAILED         # the encoding that states them proves the claim
    # stated values that make the condition false: a genuine refutation, kept
    r = verify(_shares(with_values=True, second="10/864000"), CFG)
    assert r.status is S.COUNTEREXAMPLE and not omitted(r)
    # a condition on symbols the translation declares the specialist's own (no stated figure promised): left to the argument rules
    r = verify(_shares("specialist_inference"), CFG)
    assert r.status is S.COUNTEREXAMPLE and not omitted(r)


def test_a_bool_missing_link_keeps_its_counterexample():
    """f02 of the argument corpus: 'direction changes' is stated, 'velocity changes -> accelerating' is the link, the bridge is
    missing: the COUNTEREXAMPLE is the claim's own gap (ARG-NS-002), never an omitted condition."""
    V = lambda n: {"op": "var", "name": n}
    p = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                "symbols": [{"name": "dir_changes", "sort": "Bool"}, {"name": "vel_changes", "sort": "Bool"}, {"name": "acc", "sort": "Bool"}],
                                "premises": [{"id": "e_dir", "expr": V("dir_changes")}, {"id": "l", "expr": {"op": "implies", "left": V("vel_changes"), "right": V("acc")}}],
                                "conclusion": {"id": "c", "expr": V("acc")}})
    r = verify(p, CFG)
    assert r.status is S.COUNTEREXAMPLE and not omitted(r)


def test_a_wrong_figure_with_its_definition_in_the_conclusion_keeps_its_counterexample():
    data = C2["translations"]["ch-p9b"]["s5.3"]["problem"]
    wrong = json.loads(json.dumps(data).replace('"0.9835"', '"0.9935"').replace('"0.9845"', '"0.9945"'))
    r = verify(Problem.model_validate(wrong), CFG)
    assert r.status is S.COUNTEREXAMPLE and not omitted(r)


def test_the_census_counterexample_still_stands_with_its_advisory():
    """The arena's History fixture (tests/e2e): a conclusion atom the translator declared (general_knowledge) and no premise
    mentions keeps its COUNTEREXAMPLE with the advisory W111."""
    gk = {"kind": "general_knowledge", "certainty": "probable"}
    p = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "h1.1", "query": "entailment",
                                "symbols": [{"name": "largest_city", "sort": "Bool", "grounding": gk}, {"name": "near_million", "sort": "Bool", "grounding": gk}],
                                "premises": [{"id": "pr", "expr": {"op": "var", "name": "largest_city"}, "grounding": gk}],
                                "conclusion": {"id": "c", "expr": {"op": "and", "args": [{"op": "var", "name": "largest_city"}, {"op": "var", "name": "near_million"}]}}})
    r = verify(p, CFG)
    assert r.status is S.COUNTEREXAMPLE and "W111" in codes(r) and not omitted(r)


# ------------------------------------------------- the class sweep: the round-9 probe on the largest problems the IR admits


def _v(n: str) -> dict:
    return {"op": "var", "name": n}


def _r(v) -> dict:
    return {"op": "real", "value": str(v)}


def _antecedent_shape(n: int = 60) -> Problem:
    """60 numeric symbols (the IR admits 64) each only inside the conditions of 58 links, the conclusion one of the links'
    consequences: the probe adds every omitted condition at once."""
    fact = {"kind": "arithmetic_fact", "certainty": "established"}
    links = [{"id": f"p{i}", "expr": {"op": "implies", "left": {"op": "and", "args": [
        {"op": "gt", "left": {"op": "add", "args": [_v(f"x{i}"), _v(f"x{i + 1}")]}, "right": _v(f"x{i + 2}")},
        {"op": "lt", "left": _v(f"x{i}"), "right": _r(i + 1)}]}, "right": {"op": "gt", "left": _v("y"), "right": _r(i)}}} for i in range(n - 2)]
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": f"x{i}", "sort": "Real", "grounding": fact} for i in range(n)] + [{"name": "y", "sort": "Real"}],
                                   "premises": links, "conclusion": {"id": "c", "expr": {"op": "gt", "left": _v("y"), "right": _r(n - 4)}}})


def _definition_shape(n: int = 30) -> Problem:
    """30 conclusion symbols no premise mentions, each defined in the conclusion over a premise symbol (32 conjuncts, the
    IR's widest conjunction)."""
    defs = [{"op": "eq", "left": {"op": "mul", "args": [_r("0.25"), _v(f"c{i}")]}, "right": _v(f"a{i}")} for i in range(n)]
    rest = {"op": "gt", "left": {"op": "add", "args": [_v(f"c{i}") for i in range(n)]}, "right": _r(0)}
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": f"a{i}", "sort": "Real"} for i in range(n)] + [{"name": f"c{i}", "sort": "Real"} for i in range(n)],
                                   "premises": [{"id": f"p{i}", "expr": {"op": "eq", "left": _v(f"a{i}"), "right": _r(i + 2)}} for i in range(n)],
                                   "conclusion": {"id": "c", "expr": {"op": "and", "args": [*defs, rest]}}})


@pytest.mark.parametrize("shape", [_antecedent_shape, _definition_shape], ids=["omitted conditions", "definitions in the conclusion"])
def test_sweep_the_round_9_engine_probe_stays_within_the_probes_budget(shape):
    """The class sweep of the round-9 engine code (input stall): the omitted-condition probe runs at most one solver call per
    shape inside the coverage probes' one shared timeout, so a problem as large as the IR admits is decided in bounded time
    (CPU under the core sweep's bound) and the probes' recorded time stays within the timeout."""
    import time as _time
    from epinoic_logic.engine.runner import PROBE_STAGES
    from ..core_hostile import BOUND
    cfg = SolverConfig(timeout_ms=1000, memory_max_mb=None)
    t0 = _time.process_time()
    r = verify(shape(), cfg)
    spent = _time.process_time() - t0
    assert spent < BOUND, spent
    assert r.status is S.COUNTEREXAMPLE and omitted(r), codes(r)
    assert sum(t.ms for t in r.timings if t.stage in PROBE_STAGES) <= 1000 + 250
