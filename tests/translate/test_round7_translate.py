"""Translation behaviour found wanting by the round-7 overseers (translation-fidelity and results-audit lenses), on the
recorded r7 translator fixtures (tests/channel/data/r7_translations.json):

* rounded figures encoded as exact equalities made correct claims INCONSISTENT_PREMISES or COUNTEREXAMPLE: the pipeline now
  rejects such an encoding (INVALID_FORMALIZATION, fed back once) when reading each figure to its stated precision decides
  the claim, and the prompt says a figure written to n places states its value to half a unit of its last place;
* a translation whose premises restate the conclusion (each conjunct asserted from memory) proved the claim from itself:
  rejected as circular (E112), and the engine marks such a proof so it is never displayed as ENTAILED;
* mark annotations, part labels and named items made headings "quantitative", and a single date made evidence a
  "quantitative claim" whose only encoding restates it;
* an excerpt that does not state a premise's figures verified the premise."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.runner import verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, TranslationStatus, sha256_text
from epinoic_logic.translate.eligibility import decide_eligibility, figure_text
from epinoic_logic.translate.grounding import check_problem_grounding
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator, widen_rounded_literals
from epinoic_logic.translate.prompts import load_prompt
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

TR = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_translations.json").read_text())
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def fixture(task: str, cid: str) -> dict:
    return copy.deepcopy(TR[task]["claims"][cid])


def claim_and_report(obj: dict, text: str, role: str = "quantitative", subject: str = "Economics", supplied=()) -> tuple[ClaimRecord, SpecialistReport]:
    p = obj["problem"]
    ids = dict(request_id=p["request_id"], task_id="t-r7", report_id="rep-r7", agent_id="economics-specialist", subject=subject, task_type="data_response")
    claim = ClaimRecord(**ids, claim_id=p["claim_id"], claim_text=text, claim_role=role)
    report = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), claims=[claim], supplied_texts=list(supplied), created_at="2026-10-11T10:00:00Z")
    return claim, report


def translate(obj: dict, text: str, **kw):
    claim, report = claim_and_report(obj, text, **kw)
    provider = FixtureTranslationProvider({claim.claim_id: json.dumps(obj)})
    return verify_claim(claim, report, Translator(provider, config=CFG), config=CFG)


# ------------------------------------------------------------------ stated precision


@pytest.mark.parametrize("task,cid,text", [
    ("ec-t13", "g2.1", "Value in 2022 = 1 ÷ 8.40 = US$0.1190; value in 2025 = 1 ÷ 7.00 = US$0.1429; the krona appreciated by 20.00%."),
    ("ec-p7a", "g2.1", "PED = −12.50 ÷ 18.75 = −0.67"),
    ("ec-p7a", "g8.1", "Percentage change = −34.50 ÷ 192.00 × 100 = −17.97%"),
])
def test_a_correct_rounded_figure_encoded_as_an_exact_equality_is_rejected_with_the_stated_precision(task, cid, text):
    obj = fixture(task, cid)
    problem = Problem.model_validate(obj["problem"])
    assert verify(problem, CFG).status is S.INCONSISTENT_PREMISES  # as recorded: the rounding read as an exact value
    widened, rounded = widen_rounded_literals(problem)
    assert widened is not None and rounded and verify(widened, CFG).status is S.ENTAILED
    outcome = translate(obj, text)
    assert outcome.translation.status is TranslationStatus.INVALID_FORMALIZATION
    assert any("stated precision" in d for d in outcome.translation.diagnostics)
    assert outcome.display_status is S.INVALID_FORMALIZATION and outcome.verification is None


def test_a_wrong_rounded_figure_is_not_excused_by_its_precision():
    obj = fixture("ec-p7a", "g2.1")
    text = json.dumps(obj["problem"])
    assert '"-0.67"' in text
    obj["problem"] = json.loads(text.replace('"-0.67"', '"-0.60"'))
    widened, _r = widen_rounded_literals(Problem.model_validate(obj["problem"]))
    assert verify(widened, CFG).status is not S.ENTAILED
    outcome = translate(obj, "PED = −12.50 ÷ 18.75 = −0.60")
    assert not any("stated precision" in d for d in outcome.translation.diagnostics)


def test_widening_reads_half_a_unit_of_the_last_stated_place():
    p = Problem.model_validate({"problem_id": "w", "request_id": "r", "claim_id": "c", "query": "consistency", "symbols": [{"name": "q", "sort": "Real"}],
                                "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": "q"}, "right": {"op": "real", "value": "-0.67"}}}]})
    widened, rounded = widen_rounded_literals(p)
    assert rounded == ["-0.67"]
    bounds = widened.premises[0].expr.model_dump(mode="json")
    assert bounds["op"] == "and" and [a["op"] for a in bounds["args"]] == ["ge", "lt"] and [a["right"]["value"] for a in bounds["args"]] == ["-0.675", "-0.665"]
    exact = Problem.model_validate({**p.model_dump(mode="json", exclude_none=True), "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": "q"}, "right": {"op": "real", "value": "2/3"}}}]})
    assert widen_rounded_literals(exact) == (None, [])


# ------------------------------------------------------------------ circularity


def test_premises_that_restate_the_conclusion_from_memory_are_rejected_as_circular():
    obj = fixture("hi-t13", "h1.4")
    outcome = translate(obj, "The Acerbo Law of November 1923 gave two-thirds of the seats to the list with the most votes, provided that list won at least 25 per cent.",
                        role="evidence", subject="History")
    assert outcome.translation.status is TranslationStatus.INVALID_FORMALIZATION
    assert any("E112" in d and "circular" in d for d in outcome.translation.diagnostics)
    assert outcome.display_status is S.INVALID_FORMALIZATION


def test_a_transcription_of_the_task_is_no_circle():
    obj = fixture("ph-t13", "g1.1")  # 'part (a) carries 2 marks' from the task setting: a transcription check
    problem = Problem.model_validate(obj["problem"])
    assert not [d for d in verify(problem, CFG).diagnostics if d.code == "E112"]


# ------------------------------------------------------------------ eligibility


@pytest.mark.parametrize("text,role", [("(a) [2]", "quantitative"), ("(c) [1 spare]", "quantitative"), ("Part (b) [2 marks]", "quantitative"),
                                       ("Paper 1 is the unseen-text paper.", "quantitative"), ("(iii) Round only the final answer.", "quantitative")])
def test_mark_annotations_part_labels_and_named_items_are_not_figures(text, role):
    claim = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Economics", task_type="data_response", claim_id="c", claim_text=text, claim_role=role)
    decision = decide_eligibility(claim)
    assert not decision.eligible and "not figures" in " ".join(decision.reasons)
    assert figure_text("(a) Calculate 25% of 80 [2]").strip().startswith("Calculate 25% of 80")


def test_evidence_with_one_date_is_not_a_quantitative_claim_but_two_related_figures_are():
    base = dict(request_id="r", task_id="t", report_id="rep", agent_id="history-specialist", subject="History", task_type="essay", claim_id="c", claim_role="evidence")
    single = decide_eligibility(ClaimRecord(**base, claim_text="The Acerbo Law was passed in November 1923."))
    assert not single.eligible and any("single date or figure" in r for r in single.reasons)
    pair = decide_eligibility(ClaimRecord(**base, claim_text="The Nazi vote rose from 2.6 per cent in 1928 to 18.3 per cent in 1930."))
    assert pair.eligible and pair.eligibility_class.value == "QUANTITATIVE_CLAIM"


# ------------------------------------------------------------------ grounding: the excerpt must state the figures


def test_an_excerpt_that_does_not_state_the_premises_figures_does_not_verify_it():
    doc = SuppliedText(document_id="doc-scores", text="scores = [12, 19, 23, 31, 42, 55, 67, 78, 84, 96]")
    ref = {"document_id": "doc-scores", "excerpt": "scores = [12, 19, 23"}
    p = Problem.model_validate({"problem_id": "g", "request_id": "r", "claim_id": "c", "query": "consistency", "symbols": [{"name": "it1", "sort": "Int"}],
                                "premises": [{"id": "own", "expr": {"op": "eq", "left": {"op": "var", "name": "it1"}, "right": {"op": "int", "value": "3"}}, "grounding": {"kind": "supplied_text", "source_refs": [ref]}},
                                             {"id": "real", "expr": {"op": "eq", "left": {"op": "var", "name": "it1"}, "right": {"op": "int", "value": "19"}}, "grounding": {"kind": "supplied_text", "source_refs": [ref]}}]})
    checked, checks = check_problem_grounding(p, [doc])
    own, real = checked.premises
    assert own.grounding.verified is False and real.grounding.verified is True
    assert any(c.method == "figures_in_excerpt" and c.target_id == "own" and "'3'" in c.detail for c in checks)


# ------------------------------------------------------------------ the prompt


def test_the_prompt_states_precision_shared_names_all_grounding_kinds_and_the_claims_own_links():
    text = load_prompt("translate_v1")
    for needle in ("Stated precision", "half a unit of its last stated place", "Symbol names are shared across ALL claims", "marks_a",
                   "the ten kinds", "general_knowledge", "knowledge_document", "library_source", "A figure that only the report states is NOT an arithmetic",
                   '"A, so B"', "never encode", "superlative over a finite set", "solution set"):
        assert needle in text, needle
    assert "otherwise flag the ambiguity and encode the literal comparison" not in text


# ------------------------------------------------------------------ a conclusion label that says more than its expression


def test_a_label_figure_the_conclusion_does_not_check_is_named_on_the_receipt():
    from epinoic_logic.translate.pipeline import label_beyond_expression
    obj = fixture("cs-t13", "g9.5")  # 'for [9, 3, 7] with target 9 ... returns -1': the expression checks neither 3 nor 7
    notes = label_beyond_expression(Problem.model_validate(obj["problem"]))
    assert len(notes) == 1 and "'3'" in notes[0] and "'7'" in notes[0] and "'9'" not in notes[0]
    outcome = translate(obj, "For [9, 3, 7] with target 9 the loop ends and returns -1 although 9 is at index 0.", subject="Computer Science")
    assert any("conclusion label states figure(s)" in d for d in outcome.translation.diagnostics)
    assert "conclusion label states figure(s)" in outcome.summary


@pytest.mark.parametrize("label,expr", [
    ("the krona appreciated by 20.00%", {"op": "eq", "left": {"op": "var", "name": "g"}, "right": {"op": "real", "value": "0.2"}}),
    ("PED is -0.67", {"op": "lt", "left": {"op": "var", "name": "g"}, "right": {"op": "real", "value": "-0.666"}}),
    ("output rose to 3,000 loaves", {"op": "ge", "left": {"op": "var", "name": "g"}, "right": {"op": "int", "value": "3000"}}),
])
def test_a_label_whose_figures_the_expression_states_carries_no_note(label, expr):
    from epinoic_logic.translate.pipeline import label_beyond_expression
    sort = "Int" if expr["right"]["op"] == "int" else "Real"
    p = Problem.model_validate({"problem_id": "l", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": [{"name": "g", "sort": sort}],
                                "premises": [{"id": "P", "expr": expr}], "conclusion": {"id": "C", "expr": expr, "label": label}})
    assert label_beyond_expression(p) == []
