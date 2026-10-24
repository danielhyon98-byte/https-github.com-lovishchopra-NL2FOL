"""Round 6 (results-audit major): a translation that defines each stated figure as ``b <-> (n = k)`` but never asserts it
is no verdict on the claim. The engine's COUNTEREXAMPLE for such a problem merely sets the figure to 2, 3 or 4, so it
carries ``E110`` (unasserted figure), the translator rejects the output as INVALID_FORMALIZATION with that diagnostic
(fed back once), and an engine result carrying E110 is displayed as INVALID_FORMALIZATION, never as COUNTEREXAMPLE.

The eight problems are the recorded r6 translator fixtures: hi-t12 h1.2, h1.4, h1.5 and h1.7 ('The decisive turning
point was 1960.'), hi-t11 h1.3 and h1.4, and hi-p5 h1.2 and h1.5 (hi-t12 h1.5, hi-t11 h1.3 and hi-p5 h1.2 are
AMBIGUOUS, with vague_quantity flags that say the literal equality "is encoded")."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.runner import unasserted_figure_definitions, verify
from epinoic_logic.engine.statuses import VerificationStatus
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Assertion, Problem, Var
from epinoic_logic.translate.contracts import TranslationStatus
from epinoic_logic.translate.outcome import compose_outcome, display_status_for, verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

DATA = json.loads((Path(__file__).parent / "data" / "r6_unasserted_figures.json").read_text())
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"round6-unasserted-figure-key-0123456789"
CASES = [(task, cid) for task, v in DATA["tasks"].items() for cid in v["claims"]]
AMBIGUOUS = {("hi-t12", "h1.5"), ("hi-t11", "h1.3"), ("hi-p5", "h1.2")}


def _fixture(task: str, cid: str) -> dict:
    return DATA["tasks"][task]["claims"][cid]


def _problem(task: str, cid: str) -> Problem:
    return Problem.model_validate(_fixture(task, cid)["problem"])


def _report(task: str):
    v = DATA["tasks"][task]
    branch, _profile = default_registry().for_subject(v["subject"])
    request_id = next(iter(v["claims"].values()))["problem"]["request_id"]
    return branch.parser().parse_response(v["response_text"], request_id=request_id, task_id=task, report_id=v["report_id"], subject=v["subject"],
                                          task_type=v["task_type"], supplied_texts=[], agent_id=v["agent_id"])


def _asserting_definitions(problem: Problem) -> Problem:
    extra = [Assertion(id=f"assert_{d.atom}", expr=Var(op="var", name=d.atom), label=d.label) for d in unasserted_figure_definitions(problem)]
    return problem.model_copy(update={"premises": list(problem.premises) + extra})


def test_the_eight_r6_fixtures_are_the_ones_recorded():
    assert len(CASES) == 8
    assert {c for c in CASES if _fixture(*c).get("ambiguous")} == AMBIGUOUS


@pytest.mark.parametrize("task,cid", CASES)
def test_the_engine_names_the_unasserted_figure_on_the_counterexample(task, cid):
    problem = _problem(task, cid)
    defs = unasserted_figure_definitions(problem)
    assert defs, "the fixture defines a stated figure by a biconditional over a numeric symbol no premise constrains"
    res = verify(problem, CFG)
    assert res.status is VerificationStatus.COUNTEREXAMPLE
    e110 = [d for d in res.diagnostics if d.code == "E110"]
    assert len(e110) == 1
    msg = e110[0].message
    assert any(d.premise_id in msg and d.atom in msg for d in defs), msg
    assert "no premise asserts or constrains" in msg and "ENTAILED" in msg
    # The cause, shown: with the defined atoms asserted (as the labels state them) the conclusion is ENTAILED.
    fixed = verify(_asserting_definitions(problem), CFG)
    assert fixed.status is VerificationStatus.ENTAILED
    assert not [d for d in fixed.diagnostics if d.code == "E110"]


@pytest.mark.parametrize("task,cid", CASES)
def test_the_translator_rejects_the_fixture_as_invalid_formalization_naming_the_figure(task, cid):
    report = _report(task)
    claim = next(c for c in report.claims if c.claim_id == cid)
    provider = FixtureTranslationProvider({cid: json.dumps(_fixture(task, cid))})
    translator = Translator(provider, config=CFG)
    out = verify_claim(claim, report, translator, config=CFG, signing_key=KEY)
    assert out.translation.status is TranslationStatus.INVALID_FORMALIZATION
    assert out.display_status is VerificationStatus.INVALID_FORMALIZATION
    assert out.display_status is not VerificationStatus.COUNTEREXAMPLE
    assert any("E110" in d and "unasserted figure" in d for d in out.translation.diagnostics), out.translation.diagnostics
    assert len(provider.calls) == 2, "the E110 diagnostic is fed back once, like any other invalid formalization"
    assert "E110" in "\n".join(provider.calls[1].prior_diagnostics)
    assert out.verification is None


@pytest.mark.parametrize("task,cid", [("hi-t12", "h1.7"), ("hi-t11", "h1.4")])
def test_an_engine_result_carrying_e110_is_displayed_as_invalid_formalization(task, cid):
    """The outcome layer's own rule, independent of the translator: a TRANSLATED problem whose signed result carries E110."""
    report = _report(task)
    claim = next(c for c in report.claims if c.claim_id == cid)
    provider = FixtureTranslationProvider({cid: json.dumps(_fixture(task, cid))})
    tr = Translator(provider, config=CFG, max_attempts=1).translate(claim, report)
    problem = _problem(task, cid)
    translated = tr.model_copy(update={"status": TranslationStatus.TRANSLATED, "problem": problem, "diagnostics": []})
    res = verify(problem, CFG, signing_key=KEY, key_id="k")
    assert res.status is VerificationStatus.COUNTEREXAMPLE
    assert display_status_for(translated, res, signing_key=KEY, key_id="k") is VerificationStatus.INVALID_FORMALIZATION
    outcome = compose_outcome(claim, translated, res, None, (), signing_key=KEY, key_id="k")
    assert outcome.display_status is VerificationStatus.INVALID_FORMALIZATION
    assert "Unasserted figure" in outcome.summary and "E110" in outcome.summary


def test_a_figure_that_is_asserted_keeps_its_verdict():
    """Control: the same hi-t12 h1.7 problem with the defined atoms asserted is ENTAILED and displayed so."""
    problem = _asserting_definitions(_problem("hi-t12", "h1.7"))
    assert not unasserted_figure_definitions(problem) or verify(problem, CFG).status is VerificationStatus.ENTAILED
    fx = dict(_fixture("hi-t12", "h1.7"), problem=json.loads(problem.model_dump_json(exclude_none=True)))
    report = _report("hi-t12")
    claim = next(c for c in report.claims if c.claim_id == "h1.7")
    out = verify_claim(claim, report, Translator(FixtureTranslationProvider({"h1.7": json.dumps(fx)}), config=CFG), config=CFG, signing_key=KEY)
    assert out.translation.status is TranslationStatus.TRANSLATED
    assert out.display_status is VerificationStatus.ENTAILED


def test_a_counterexample_that_does_not_rest_on_the_definition_stands_and_the_flag_mismatch_is_noted():
    """Control: the conclusion fails for a reason of its own (an atom no premise supports), so the counterexample is a
    verdict as encoded. The unasserted definition is recorded as a note, and an ambiguity flag that says the literal
    equality "is encoded" is named as not matching the IR."""
    fx = json.loads(json.dumps(_fixture("hi-t12", "h1.5")))
    p = fx["problem"]
    p["symbols"].append({"name": "unrelated_atom", "sort": "Bool", "meaning": "an atom no premise supports",
                         "grounding": {"kind": "specialist_inference", "certainty": "probable"}})
    p["premises"].append({"id": "pr_extra_assert", "expr": {"op": "var", "name": "flow_slowed"}, "label": "the flow slowed"})
    p["conclusion"] = {"id": "concl", "expr": {"op": "var", "name": "unrelated_atom"}, "label": "an unrelated statement"}
    problem = Problem.model_validate(p)
    res = verify(problem, CFG)
    assert res.status is VerificationStatus.COUNTEREXAMPLE and not [d for d in res.diagnostics if d.code == "E110"]
    report = _report("hi-t12")
    claim = next(c for c in report.claims if c.claim_id == "h1.5")
    tr = Translator(FixtureTranslationProvider({"h1.5": json.dumps(fx)}), config=CFG).translate(claim, report)
    assert tr.status is TranslationStatus.AMBIGUOUS_TRANSLATION
    assert any(d.startswith("unasserted figure definition(s)") and "pr_states_1961_68_15" in d for d in tr.diagnostics), tr.diagnostics
    assert any("does not match the IR" in d and "vague_quantity" in d for d in tr.diagnostics), tr.diagnostics


def test_through_the_hub_the_genuine_hi_t12_shows_no_counterexample_verdict():
    """End to end: the r6 hi-t12 answer and its fixtures cross the hub; the four claims whose stated figures are only
    defined are INVALID_FORMALIZATION on the receipt, and none is displayed as COUNTEREXAMPLE."""
    v = DATA["tasks"]["hi-t12"]
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="plan-hi-t12", request_id="req-hi-t12", task_id="hi-t12", subject=v["subject"], task_type=v["task_type"],
                                selected_agent_ids=[v["agent_id"]]))
    provider = FixtureTranslationProvider({cid: json.dumps(fx) for cid, fx in v["claims"].items()})
    translator = Translator(provider, config=CFG)
    ch.verify_claim_fn = lambda claim, report: verify_claim(claim, report, translator, config=CFG, signing_key=KEY) if claim.claim_id in v["claims"] else None
    msg, _req, _rq = hub.dispatch("hi-t12", v["agent_id"], v["question"], [])
    reply, rc = hub.receive("hi-t12", msg.message_id, v["response_text"], agent_id=v["agent_id"], report_id=v["report_id"])
    assert reply is not None
    shown = {o.claim_id: o.display_status for o in rc.outcomes}
    assert shown == {cid: VerificationStatus.INVALID_FORMALIZATION for cid in v["claims"]}, shown
    assert "COUNTEREXAMPLE" not in rc.summary and "'INVALID_FORMALIZATION': 4" in rc.summary, rc.summary
    for o in rc.outcomes:
        assert "E110" in o.summary and "nothing was submitted to the solver" in o.summary
