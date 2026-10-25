"""Re-run review findings in the engine runner (each test is the finding's own reproduction, with a clean control).

* correctness-1: a COUNTEREXAMPLE that has both coverage shapes is checked for E111 even when the W110 shape fired, so a
  free symbol a source states withholds the verdict (as it does without the definition); E110 still skips the E111 check;
  two advisories are both reported.
* correctness-7: a vacuous ENTAILED (an empty premise core) serialises its raw core record when it is asked for.
* fidelity-4: a writer's own premise that restates the conclusion in a trivially different form (operands swapped, a
  comparison written the other way round, ``x <= a and x >= a`` for ``x = a``, double negation, ``iff true``) is circular
  (E112), in the engine and in the translation pipeline, exactly as the same text written identically is.
* formal-robustness-2: the coverage checks run inside the decision's documented bound and their time is recorded.
* formal-robustness-5 and robustness-and-contracts-5: a payload that never becomes a Problem (None, a list, a number, a
  dict nested beyond the recursion limit, holding a lone surrogate or an integer too long for decimal text) is bound to a
  digest of what was sent and keeps the validator's INVALID_FORMALIZATION, never INTERNAL_ERROR.

These results prove properties of the encoding and of this code only.
"""
from __future__ import annotations

import hashlib
import json
import time

import pytest
import z3

from epinoic_logic.engine import runner
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.results import SolverConfig, UnsatCore
from epinoic_logic.engine.runner import circular_premises, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.canonical import canonical_json
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, TranslationStatus as T, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"rerun-review-runner-key-0123456789"


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


def codes(result) -> list[str]:
    return [d.code for d in result.diagnostics]


# ============================================================================ correctness-1: both coverage shapes

STATED_Y = {"kind": "supplied_text", "verified": True, "source_refs": [{"document_id": "doc", "excerpt": "y = 9"}]}


def _two_shapes(y_grounding=None, b_grounding=None, with_definition=True) -> Problem:
    y = {"name": "y", "sort": "Int", **({"grounding": y_grounding} if y_grounding else {})}
    symbols = [{"name": "x", "sort": "Int"}, y]
    premises = [{"id": "P", "expr": op("eq", V("x"), I(5)), "label": "x is 5"}]
    conclusion = op("lt", V("x"), V("y"))
    if with_definition:
        symbols += [{"name": "b", "sort": "Bool", **({"grounding": b_grounding} if b_grounding else {})}, {"name": "n", "sort": "Int"}]
        premises.append({"id": "D", "expr": op("iff", V("b"), op("eq", V("n"), I(17))), "label": "b means the count n is 17"})
        conclusion = op("or", V("b"), conclusion)
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": symbols,
                                   "premises": premises, "conclusion": {"id": "C", "expr": conclusion}})


def test_a_source_stated_free_symbol_withholds_the_verdict_although_the_definition_shape_also_fired():
    """The finding's encoding: P x = 5, D b <-> (n = 17), conclusion b or x < y, and a check verified that a source states
    y. Without D the result is E111; with D it was only the advisory W110, so the counterexample y = 0 was displayed as the
    verdict although the source states y = 9."""
    plain = verify(_two_shapes(STATED_Y, with_definition=False), CFG)
    assert plain.status is S.COUNTEREXAMPLE and codes(plain) == ["E111"]
    both = verify(_two_shapes(STATED_Y), CFG)
    assert both.status is S.COUNTEREXAMPLE and codes(both) == ["E111"], codes(both)
    assert "y" in both.diagnostics[0].message and "W110" not in codes(both)  # the advisory that says the counterexample stands is not carried


def test_without_source_evidence_both_shapes_stay_advisory_and_the_counterexample_stands():
    """Control: no check verified a source statement, so each shape is the advisory warning and the verdict stands."""
    r = verify(_two_shapes(), CFG)
    assert r.status is S.COUNTEREXAMPLE and sorted(codes(r)) == ["W110", "W111"] and r.counterexample is not None
    alone = verify(_two_shapes(with_definition=False), CFG)
    assert codes(alone) == ["W111"]


def test_an_unasserted_figure_a_source_states_still_skips_the_unencoded_reason_check():
    """Control: E110 already withholds the verdict, so the E111 check is not run (and no W111 is added beside it)."""
    stated_b = {"kind": "supplied_text", "verified": True, "source_refs": [{"document_id": "doc", "excerpt": "the count is 17"}]}
    r = verify(_two_shapes(b_grounding=stated_b), CFG)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E110"]
    assert not any(t.stage.startswith(runner.PROBE_REASON_STAGE) for t in r.timings)


def _claim_and_report(claim_text: str, support: tuple[str, ...]):
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Mathematics", task_type="algebra")
    supporting = [ClaimRecord(**ids, claim_id=f"s{i}", claim_text=t, claim_role="evidence") for i, t in enumerate(support)]
    claim = ClaimRecord(**ids, claim_id="c", claim_text=claim_text, claim_role="quantitative", proposed_claim_kind="arithmetic",
                        supporting_claim_ids=[c.claim_id for c in supporting])
    body = " ".join([claim_text, *support])
    report = SpecialistReport(**ids, original_response=body, response_sha256=sha256_text(body), claims=[claim, *supporting], supplied_texts=[],
                              created_at="2026-10-16T00:00:00Z")
    return claim, report


def _output(problem: dict) -> dict:
    return {"problem": problem, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
            "unsupported_reason": None}


def _translated_two_shapes(with_definition: bool) -> dict:
    symbols = [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}]
    premises = [{"id": "P", "expr": op("eq", V("x"), I(5)), "label": "x equals 5", "grounding": {"kind": "task_setting"}}]
    conclusion = {"id": "C", "expr": op("lt", V("x"), V("y")), "label": "x is less than y"}
    if with_definition:
        symbols += [{"name": "b", "sort": "Bool", "meaning": "the count n is 17"}, {"name": "n", "sort": "Int", "meaning": "the count"}]
        premises.append({"id": "D", "expr": op("iff", V("b"), op("eq", V("n"), I(17))), "label": "b holds exactly when the count n is 17"})
        conclusion = {"id": "C", "expr": op("or", V("b"), op("lt", V("x"), V("y"))), "label": "the count is 17 or x is less than y"}
    return {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": symbols,
            "premises": premises, "conclusion": conclusion}


@pytest.mark.parametrize("with_definition", [False, True])
def test_end_to_end_the_translation_layer_and_the_engine_make_the_same_coverage_decision(with_definition: bool):
    """The finding's end-to-end reproduction: claim 'x is less than y.' with the supporting claim 'Here x = 5 and y = 9.'.
    The translation's own coverage note says a source asserts y; the signed result now carries E111 with the definition
    too, so the display is INVALID_FORMALIZATION (it was COUNTEREXAMPLE with y = 0)."""
    claim, report = _claim_and_report("x is less than y.", ("Here x = 5 and y = 9.",))
    problem = _translated_two_shapes(with_definition)
    provider = FixtureTranslationProvider({"c": [_output(problem), _output(problem)]})
    outcome = verify_claim(claim, report, Translator(provider, config=CFG), config=CFG, signing_key=KEY, key_id="k")
    notes = [(n.kind, n.source_asserted, n.evidence_symbols) for n in outcome.translation.coverage]
    assert ("unconstrained_symbol", True, ["y"]) in notes
    assert outcome.verification is not None and "E111" in codes(outcome.verification) and "W110" not in codes(outcome.verification)
    assert outcome.display_status is S.INVALID_FORMALIZATION


# ============================================================================ correctness-7: the core record of a vacuous ENTAILED


def _tautology(flag: bool):
    p = {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": [{"name": "x", "sort": "Int"}],
         "premises": [{"id": "P1", "expr": op("gt", V("x"), I(0))}],
         "conclusion": {"id": "C", "expr": op("or", op("gt", V("x"), I(3)), op("le", V("x"), I(3)))}}
    return verify(json.dumps(p), SolverConfig(produce_unsat_core=flag))


def test_a_vacuous_entailed_serialises_its_empty_core_record_when_asked():
    r = _tautology(True)
    assert r.status is S.ENTAILED and codes(r) == ["E108"] and r.premises_relied_on == []
    assert r.unsat_core == UnsatCore(premise_ids=[], includes_negated_conclusion=True)
    assert r.model_dump(mode="json")["unsat_core"] == {"premise_ids": [], "includes_negated_conclusion": True}


def test_the_core_record_is_still_left_out_when_not_asked_and_a_used_core_is_unchanged(transitivity):
    """Controls: the flag off still serialises no record; a proof that used premises names exactly them."""
    assert _tautology(False).unsat_core is None
    r = verify(transitivity, SolverConfig(produce_unsat_core=True))
    assert r.status is S.ENTAILED and r.unsat_core == UnsatCore(premise_ids=["P1", "P2"], includes_negated_conclusion=True)


# ============================================================================ fidelity-4: restatement in a trivially different form

WRITER = {"grounding": {"kind": "specialist_inference", "certainty": "established"}}


def _restating(premise: dict, conclusion: dict, symbols: list[tuple[str, str]], grounding: dict = WRITER) -> Problem:
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": n, "sort": s} for n, s in symbols],
                                   "premises": [{"id": "p1", "expr": premise, **grounding}],
                                   "conclusion": {"id": "concl", "expr": conclusion}})


DT = [("dt", "Int")]
AB = [("a", "Bool"), ("b", "Bool")]
RESTATEMENTS = {
    "operands swapped": (op("eq", I(41), V("dt")), op("eq", V("dt"), I(41)), DT),
    "both bounds for an equality": (op("and", op("le", V("dt"), I(41)), op("ge", V("dt"), I(41))), op("eq", V("dt"), I(41)), DT),
    "double negation": (op("not", op("not", op("and", V("a"), V("b")))), op("and", V("a"), V("b")), AB),
    "iff true": (op("iff", op("and", V("a"), V("b")), {"op": "bool", "value": True}), op("and", V("a"), V("b")), AB),
    "conjuncts reordered": (op("and", V("b"), V("a")), op("and", V("a"), V("b")), AB),
    "disjuncts reordered": (op("or", V("b"), V("a")), op("or", V("a"), V("b")), AB),
    "comparison the other way round": (op("lt", I(5), V("dt")), op("gt", V("dt"), I(5)), DT),
    "negated comparison": (op("not", op("lt", V("dt"), I(5))), op("ge", V("dt"), I(5)), DT),
    "literal written differently": (op("eq", V("x"), R("0.50")), op("eq", V("x"), R("1/2")), [("x", "Real")]),
    "repeated disjunct": (op("or", V("a"), V("a")), V("a"), AB),
}


@pytest.mark.parametrize("name", sorted(RESTATEMENTS))
def test_a_writer_premise_restating_the_conclusion_in_another_form_is_circular(name: str):
    premise, conclusion, symbols = RESTATEMENTS[name]
    problem = _restating(premise, conclusion, symbols)
    assert circular_premises(problem) == ["p1"]
    r = verify(problem, CFG)
    assert r.status is S.ENTAILED and "E112" in codes(r), (name, codes(r))


def test_the_restatement_written_identically_was_and_stays_circular():
    problem = _restating(op("eq", V("dt"), I(41)), op("eq", V("dt"), I(41)), DT)
    assert circular_premises(problem) == ["p1"] and "E112" in codes(verify(problem, CFG))


@pytest.mark.parametrize("name", sorted(RESTATEMENTS))
def test_a_restatement_a_check_verified_is_a_transcription_not_a_circle(name: str):
    """Control: a premise a check in this process verified against the task is a transcription, whatever its form."""
    premise, conclusion, symbols = RESTATEMENTS[name]
    verified = {"grounding": {"kind": "task_setting", "verified": True, "source_refs": [{"document_id": "task", "excerpt": "given"}]}}
    r = verify(_restating(premise, conclusion, symbols, verified), CFG)
    assert r.status is S.ENTAILED and "E112" not in codes(r)


def _two_premises(p1, p2, conclusion, symbols):
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": n, "sort": s} for n, s in symbols],
                                   "premises": [{"id": "p1", "expr": p1, **WRITER}, {"id": "p2", "expr": p2, **WRITER}],
                                   "conclusion": {"id": "concl", "expr": conclusion}})


@pytest.mark.parametrize("problem", [
    # modus ponens
    _two_premises(V("a"), op("implies", V("a"), V("b")), V("b"), AB),
    # a weaker comparison derived from a stronger one is no restatement
    _two_premises(op("gt", V("dt"), I(41)), op("lt", V("dt"), I(50)), op("ge", V("dt"), I(41)), DT),
], ids=["modus ponens", "weaker comparison"])
def test_genuine_derivations_are_not_read_as_restatements(problem: Problem):
    r = verify(problem, CFG)
    assert r.status is S.ENTAILED and "E112" not in codes(r) and circular_premises(problem) == []


def test_two_bounds_of_the_writers_own_that_together_restate_the_point_are_circular():
    """Rewritten to the stricter rule of repair round 4 (fidelity-4 variant): this case was a control above ("a derivation
    from two premises, each bound alone restates nothing"), but "dt <= 41" and "dt >= 41", held only by the writer, say
    together exactly the point "dt = 41", as the one premise "dt <= 41 and dt >= 41" does, which is circular. The normal
    form still reads each premise alone (``circular_premises`` stays empty); the engine decides the conjunction's
    equivalence itself, so the ENTAILED carries E112. The other two controls stay controls."""
    problem = _two_premises(op("le", V("dt"), I(41)), op("ge", V("dt"), I(41)), op("eq", V("dt"), I(41)), DT)
    r = verify(problem, CFG)
    assert circular_premises(problem) == []
    assert r.status is S.ENTAILED and "E112" in codes(r)


def test_a_derived_value_whose_one_premise_restates_the_point_is_circular():
    """Rewritten to the stricter rule of repair round 2 (fidelity-4 variant): this case was a control above ("a sum written
    in another order and a different literal value"), but ``dt + 1 = 42``, held only by the writer, is the point
    ``dt = 41`` in other terms. It is no rewrite of the normal form (``circular_premises`` stays empty), and the engine
    decides the equivalence itself, so the ENTAILED carries E112."""
    problem = _two_premises(op("eq", op("add", V("dt"), I(1)), I(42)), op("ge", V("dt"), I(0)), op("eq", V("dt"), I(41)), DT)
    r = verify(problem, CFG)
    assert circular_premises(problem) == []
    assert r.status is S.ENTAILED and "E112" in codes(r)


def test_a_negated_comparison_that_is_not_equivalent_restates_nothing():
    """Control: not (dt < 5) is dt >= 5, not dt > 5; the normal form never claims more than the rewrites it lists."""
    problem = _restating(op("not", op("lt", V("dt"), I(5))), op("gt", V("dt"), I(5)), DT)
    assert circular_premises(problem) == []
    assert verify(problem, CFG).status is S.COUNTEREXAMPLE


def _pipeline_outcome(premise: dict, conclusion: dict, symbols: list[tuple[str, str]]):
    claim, report = _claim_and_report("The doubling time is 41 years.", ("The doubling time was computed as 41 years.",))
    problem = {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
               "symbols": [{"name": n, "sort": s} for n, s in symbols],
               "premises": [{"id": "p1", "expr": premise, "label": "the doubling time is 41 years", **WRITER}],
               "conclusion": {"id": "concl", "expr": conclusion, "label": "the doubling time is 41 years"}}
    provider = FixtureTranslationProvider({"c": [_output(problem), _output(problem)]})
    return verify_claim(claim, report, Translator(provider, config=CFG), config=CFG, signing_key=KEY, key_id="k")


@pytest.mark.parametrize("name", ["operands swapped", "both bounds for an equality"])
def test_the_pipeline_refuses_the_restatement_as_it_refuses_the_identical_text(name: str):
    """The finding's pipeline reproduction (pr6_same was refused, pr6_swap and pr6_lege were displayed ENTAILED)."""
    premise, conclusion, symbols = RESTATEMENTS[name]
    same = _pipeline_outcome(conclusion, conclusion, symbols)
    other = _pipeline_outcome(premise, conclusion, symbols)
    for outcome in (same, other):
        assert outcome.translation.status is T.INVALID_FORMALIZATION and outcome.display_status is S.INVALID_FORMALIZATION
        assert any("E112" in d for d in outcome.translation.diagnostics)


# ============================================================================ formal-robustness-2: probes inside the bound


def _hard_two_shapes(k: int = 8) -> dict:
    """A definition whose figure chain is hard for the nonlinear solver, and free conclusion figures w and v: both probes
    run, and each can use a whole solver timeout."""
    symbols = [("b", "Bool"), ("x", "Real"), ("w", "Real"), ("v", "Real")] + [(f"y{i}", "Real") for i in range(1, k + 1)]
    parts = [op("eq", V("y1"), op("mul", V("x"), V("x")))] + [op("eq", V(f"y{i}"), op("mul", V(f"y{i-1}"), V(f"y{i-1}"))) for i in range(2, k + 1)]
    parts.append(op("eq", V(f"y{k}"), R(2)))
    conclusion = op("or", V("b"), op("eq", op("mul", V("w"), V("w"), V("v"), V("v")), op("add", V("w"), R(2))))
    return {"problem_id": "p1", "request_id": "r1", "claim_id": "c1", "query": "entailment", "symbols": [{"name": n, "sort": s} for n, s in symbols],
            "premises": [{"id": "p0", "expr": op("iff", V("b"), op("and", *parts))}], "conclusion": {"id": "concl", "expr": conclusion}}


def test_the_coverage_probes_run_inside_the_decision_bound_and_are_timed():
    """The finding: the probes ran after the procedure with a whole timeout each and were left out of the timings, so a
    verdict the solver reached in milliseconds held the engine for up to three more timeouts while its timings showed
    milliseconds. Now the procedure and the probes share one deadline of twice the timeout, and each probe is timed."""
    timeout_ms = 600
    config = policy_config("nonlinear", SolverConfig(timeout_ms=timeout_ms, memory_max_mb=None))
    started = time.perf_counter()
    r = verify(_hard_two_shapes(), config, limits=policy_limits("nonlinear"))
    wall = time.perf_counter() - started
    assert r.status is S.COUNTEREXAMPLE
    stages = [t.stage for t in r.timings]
    assert any(s.startswith(runner.PROBE_FIGURE_STAGE) for s in stages) and any(s.startswith(runner.PROBE_REASON_STAGE) for s in stages)
    solver_ms = sum(t.ms for t in r.timings if t.stage in ("consistency", "entailment") or t.stage.startswith("coverage_probe"))
    assert solver_ms <= runner.DECISION_SOLVER_CALLS * timeout_ms + 250, r.timings  # the documented bound, with scheduling slack
    assert sum(t.ms for t in r.timings) >= 0.5 * wall * 1000.0, (wall, r.timings)  # the time spent is the time reported


def test_a_probe_gets_only_what_is_left_of_the_bound(monkeypatch):
    """The probes' solver calls are bounded by what the procedure left (never more than the timeout each): the figure probe
    by half of it for each of its two calls, the reason probe by what the figure probe left."""
    seen: dict[str, list[int]] = {"figure_probe": [], "solver_timeouts": []}
    real = runner._PROCEDURES["entailment"]

    def spy(compiled, config):
        if any(pid.startswith("asserted_figure_") for pid in compiled.premises):
            seen["figure_probe"].append(int(config.timeout_ms))
        return real(compiled, config)

    class SpySolver(z3.Solver):
        def set(self, *args, **kwargs):
            if args[:1] == ("timeout",):
                seen["solver_timeouts"].append(int(args[1]))
            return super().set(*args, **kwargs)

    monkeypatch.setitem(runner._PROCEDURES, "entailment", spy)
    monkeypatch.setattr(runner.z3, "Solver", SpySolver)
    monkeypatch.setattr(runner, "_remaining_ms", lambda deadline: 900)
    r = verify(_two_shapes(), SolverConfig(timeout_ms=4000, memory_max_mb=None))
    assert sorted(codes(r)) == ["W110", "W111"]
    assert seen["figure_probe"] == [450]
    # the procedure's two calls at the timeout, the figure probe's two at half of what is left, the reason probe's one at all of it
    assert seen["solver_timeouts"] == [4000, 4000, 450, 450, 900]


def test_a_probe_with_nothing_left_is_skipped_and_decides_nothing(monkeypatch):
    """A spent bound skips both probes (recorded as skipped), and a skipped probe decides nothing. Rewritten to a stricter
    rule in repair round 1 (re-run review INV-4): the counterexample stood with no coverage diagnostic although a source
    states the free symbol y, so a spent bound let a verdict stand that the probe could have withheld. With source-linked
    evidence the skipped probe now withholds the verdict (E111, "undecided"); without it the counterexample stands as
    before (the control below)."""
    monkeypatch.setattr(runner, "_remaining_ms", lambda deadline: 0)
    r = verify(_two_shapes(STATED_Y), CFG)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E111"] and "undecided" in r.diagnostics[0].message and "skipped" in r.diagnostics[0].message
    stages = [t.stage for t in r.timings]
    assert runner.PROBE_FIGURE_STAGE + "_skipped" in stages and runner.PROBE_REASON_STAGE + "_skipped" in stages


def test_a_skipped_probe_without_source_evidence_leaves_the_counterexample_standing(monkeypatch):
    """Control (INV-4): no check verified a source statement on the free symbols, so a skipped probe changes nothing: with
    the probe the result would be the advisory W110/W111 at most, and the counterexample stands either way."""
    monkeypatch.setattr(runner, "_remaining_ms", lambda deadline: 0)
    r = verify(_two_shapes(), CFG)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == [] and r.counterexample is not None


def test_a_skipped_figure_probe_with_a_stated_figure_withholds_the_verdict(monkeypatch):
    """INV-4, the E110 shape: a source states the defined count, and the re-run that would decide E110 is skipped."""
    stated_b = {"kind": "supplied_text", "verified": True, "source_refs": [{"document_id": "doc", "excerpt": "the count is 17"}]}
    monkeypatch.setattr(runner, "_remaining_ms", lambda deadline: 0)
    r = verify(_two_shapes(b_grounding=stated_b), CFG)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E110"] and "undecided" in r.diagnostics[0].message
    assert not any(t.stage == runner.PROBE_REASON_STAGE for t in r.timings)   # E110 withholds it, so E111 is not probed


def test_an_undecided_reason_probe_with_a_stated_symbol_withholds_the_verdict(monkeypatch):
    """INV-4: the probe ran but the solver left it undecided (unknown): with a source stating y, no verdict either."""
    class UnknownSolver(z3.Solver):
        def check(self, *args):
            if any("ForAll" in str(a) or z3.is_quantifier(a) for a in self.assertions()):
                return z3.unknown
            return super().check(*args)

    monkeypatch.setattr(runner.z3, "Solver", UnknownSolver)
    r = verify(_two_shapes(STATED_Y, with_definition=False), CFG)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E111"] and "undecided within its bound" in r.diagnostics[0].message


# ============================================================================ formal-robustness-5, robustness-and-contracts-5


def _deep(levels: int) -> dict:
    e = V("b")
    for _ in range(levels):
        e = {"op": "not", "arg": e}
    return {"problem_id": "p1", "request_id": "r1", "claim_id": "c1", "query": "entailment", "symbols": [{"name": "b", "sort": "Bool"}],
            "premises": [{"id": "p0", "expr": V("b")}], "conclusion": {"id": "concl", "expr": e}}


def test_a_payload_nested_beyond_the_recursion_limit_keeps_the_validators_verdict():
    first, second = verify(_deep(50_000), CFG, signing_key=KEY, key_id="k"), verify(_deep(50_000), CFG)
    assert first.status is S.INVALID_FORMALIZATION and codes(first) == ["E303"]
    assert len(first.binding.problem_digest) == 64 and first.binding.problem_digest == second.binding.problem_digest


BASE = {"problem_id": "p1", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": [{"name": "x", "sort": "Real"}],
        "premises": [{"id": "P", "expr": op("eq", V("x"), R(2))}], "conclusion": {"id": "C", "expr": op("eq", V("x"), R(2))}}


@pytest.mark.parametrize("raw", [None, [BASE], 5, 1.5, True, {**BASE, "notes": "\ud83d"}, {"problem_id": "\ud83d"}, {**BASE, "notes": 10 ** 5000},
                                 {**BASE, "notes": object()}],
                         ids=["none", "list", "int", "float", "bool", "surrogate-value", "surrogate-id", "huge-integer", "non-json-value"])
def test_a_malformed_payload_is_an_invalid_formalization_bound_to_what_was_sent(raw):
    r = verify(raw, CFG, signing_key=KEY, key_id="k")
    assert r.status is S.INVALID_FORMALIZATION and "E900" not in codes(r) and codes(r)[:1] == ["E100"], codes(r)
    assert r.binding.problem_digest != "unavailable" and len(r.binding.problem_digest) == 64
    assert verify(raw, CFG).binding.problem_digest == r.binding.problem_digest  # deterministic


def test_the_digest_of_a_payload_canonical_json_can_write_is_unchanged():
    """Control: text, bytes and a serialisable dict are digested exactly as before (the bound digest of a rejection does
    not move), and a list, a number or None as its JSON text would be."""
    bad = {**BASE, "query": "nonsense"}
    assert verify(bad, CFG).binding.problem_digest == hashlib.sha256(canonical_json(bad).encode("utf-8")).hexdigest()
    text = json.dumps(bad)
    assert verify(text, CFG).binding.problem_digest == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert verify(text.encode(), CFG).binding.problem_digest == hashlib.sha256(text.encode()).hexdigest()
    assert verify([1, 2], CFG).binding.problem_digest == hashlib.sha256(b"[1,2]").hexdigest()
    assert verify(None, CFG).binding.problem_digest == hashlib.sha256(b"null").hexdigest()
