"""Outcome composition: display mapping for every translation status, summary content, end-to-end verify_claim."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine import verify as engine_verify
from epinoic_logic.engine.provenance import verify_signature
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.statuses import DEFINITIVE, SCOPE_STATEMENT, VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import (
    SemanticReviewer,
    StructuralFinding,
    Translator,
    TranslationStatus as T,
    compose_outcome,
    display_status_for,
    verify_claim,
)
from epinoic_logic.translate.contracts import EligibilityDecision, ProviderInfo, SemanticFidelityReview, TranslationResult, sha256_text
from epinoic_logic.version import TRANSLATOR_VERSION
from epinoic_logic.translate.outcome import SUMMARY_MAX_CHARS, _fit
from epinoic_logic.translate.providers import FixtureReviewProvider, FixtureTranslationProvider

from .conftest import I, V, chain_problem, cmp, make_claim, make_report, provider_output

CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)


def make_translation(status: T, problem: Problem | None = None, **over) -> TranslationResult:
    # A record as this translator makes it: its version and the digest of the claim text it read (contract 0.2). Any other
    # record is displayed INTERNAL_ERROR whatever its status (re-run review finding correctness-5; see
    # tests/translate/test_rerun_review_records.py).
    data = dict(
        translation_id="tr-test", claim_id="c-point", request_id="req-1", report_id="rep-1", status=status,
        eligibility=EligibilityDecision(eligibility_class="PROPOSITIONAL_ARGUMENT", eligible=True, decided_by="deterministic", reasons=["r"], policy_version="p"),
        problem=problem, provider=ProviderInfo(provider_name="fixture"), translator_version=TRANSLATOR_VERSION, policy_version="p",
        claim_text_sha256=sha256_text(make_claim().claim_text), diagnostics=["d1"], created_at="2026-10-11T00:00:00Z",
    )
    data.update(over)
    return TranslationResult(**data)


@pytest.mark.parametrize(
    "status,expected",
    [
        (T.AMBIGUOUS_TRANSLATION, S.AMBIGUOUS_TRANSLATION),
        (T.NOT_ELIGIBLE, S.NOT_ELIGIBLE),
        (T.UNSUPPORTED, S.UNSUPPORTED),
        (T.INVALID_FORMALIZATION, S.INVALID_FORMALIZATION),
        (T.TRANSLATION_FAILED, S.INTERNAL_ERROR),
    ],
)
def test_display_mapping_for_non_translated_statuses(status, expected):
    claim = make_claim(supporting_claim_ids=["c-ev"])
    problem = Problem.model_validate(chain_problem()) if status is T.AMBIGUOUS_TRANSLATION else None
    translation = make_translation(status, problem)
    verification = engine_verify(problem, CFG) if problem is not None else None
    assert display_status_for(translation, verification) is expected
    outcome = compose_outcome(claim, translation, verification)
    assert outcome.display_status is expected and expected not in DEFINITIVE
    assert outcome.summary.endswith(SCOPE_STATEMENT) and len(outcome.summary) <= SUMMARY_MAX_CHARS
    assert f"display status {expected.value}" in outcome.summary


def test_every_translation_status_is_covered():
    covered = {T.TRANSLATED, T.AMBIGUOUS_TRANSLATION, T.NOT_ELIGIBLE, T.UNSUPPORTED, T.INVALID_FORMALIZATION, T.TRANSLATION_FAILED}
    assert covered == set(T)


def test_translated_takes_engine_status_when_bound():
    problem = Problem.model_validate(chain_problem())
    verification = engine_verify(problem, CFG)
    assert verification.status is S.ENTAILED
    translation = make_translation(T.TRANSLATED, problem)
    assert display_status_for(translation, verification) is S.ENTAILED
    broken = Problem.model_validate(chain_problem(with_l2=False))
    assert display_status_for(make_translation(T.TRANSLATED, broken), engine_verify(broken, CFG)) is S.COUNTEREXAMPLE


def test_translated_without_engine_result_is_internal_error():
    translation = make_translation(T.TRANSLATED, Problem.model_validate(chain_problem()))
    outcome = compose_outcome(make_claim(supporting_claim_ids=["c-ev"]), translation, None)
    assert outcome.display_status is S.INTERNAL_ERROR and "no engine result" in outcome.summary


def test_engine_result_for_a_different_problem_is_rejected():
    problem = Problem.model_validate(chain_problem())
    other = Problem.model_validate(chain_problem(problem_id="p-chain"))  # same id, different label below
    other = other.model_copy(update={"notes": "a changed representation"})
    verification = engine_verify(other, CFG)
    translation = make_translation(T.TRANSLATED, problem)
    outcome = compose_outcome(make_claim(supporting_claim_ids=["c-ev"]), translation, verification)
    assert outcome.display_status is S.INTERNAL_ERROR and "digest mismatch" in outcome.summary
    foreign = engine_verify(Problem.model_validate(chain_problem(claim_id="c-link")), CFG)
    assert display_status_for(translation, foreign) is S.INTERNAL_ERROR


def test_compose_rejects_foreign_translation_and_review():
    claim = make_claim(supporting_claim_ids=["c-ev"])
    with pytest.raises(ValueError):
        compose_outcome(make_claim("c-other"), make_translation(T.NOT_ELIGIBLE))
    review = SemanticFidelityReview(review_id="rv", translation_id="tr-else", verdict="faithful", reviewer=ProviderInfo(provider_name="fixture"), created_at="2026-10-11T00:00:00Z")
    with pytest.raises(ValueError):
        compose_outcome(claim, make_translation(T.NOT_ELIGIBLE), review=review)


def test_verify_claim_end_to_end_entailed(english_claims, english_report):
    claim = english_claims["c-point"]
    translator = Translator(FixtureTranslationProvider({"c-point": provider_output(chain_problem())}))
    reviewer = SemanticReviewer(FixtureReviewProvider({"c-point": {"verdict": "faithful", "issues": []}}))
    findings = [StructuralFinding(code="ES-STR-001", severity="warning", message="paragraph has fewer than two quotations", claim_ids=["c-point"], rule_source="english_specialist/paragraphs.md P7 (working rule, not an official IB rule)")]
    outcome = verify_claim(claim, english_report, translator, reviewer=reviewer, structural=findings, config=CFG, signing_key=b"k" * 32, key_id="test")
    assert outcome.display_status is S.ENTAILED
    assert outcome.verification is not None and outcome.verification.status is S.ENTAILED
    assert verify_signature(outcome.verification, b"k" * 32) and outcome.verification.signature_key_id == "test"
    assert sorted(outcome.verification.ungrounded_dependencies) == ["L1", "L2"]
    assert outcome.verification.binding.problem_digest and outcome.translation.problem is not None
    summary = outcome.summary
    assert summary.endswith(SCOPE_STATEMENT) and len(summary) <= SUMMARY_MAX_CHARS
    assert "Ungrounded dependencies" in summary and "L1 (specialist_inference, probable)" in summary and "L2 (specialist_inference, probable)" in summary
    assert "Premises relied on" in summary and "E1" in summary
    assert "entailment query over 3 symbol(s) and 3 premise(s)" in summary
    assert "Status meaning: the encoded conclusion follows" in summary
    assert "Advisory semantic-fidelity review: faithful (advisory only; not a verification)" in summary
    assert "1 warning(s)" in summary and "is signed (key test)" in summary
    assert outcome.semantic_review is not None and outcome.structural_findings == findings
    assert outcome.request_id == "req-1" and outcome.report_id == "rep-1" and outcome.claim_id == "c-point"
    json.loads(outcome.model_dump_json())


def test_verify_claim_counterexample_lists_assignment(english_claims, english_report):
    translator = Translator(FixtureTranslationProvider({"c-point": provider_output(chain_problem(with_l2=False))}))
    outcome = verify_claim(english_claims["c-point"], english_report, translator, config=CFG)
    assert outcome.display_status is S.COUNTEREXAMPLE
    assert "Counterexample:" in outcome.summary and "p=false" in outcome.summary
    assert "is unsigned" in outcome.summary


def test_verify_claim_hallucinated_quotation_surfaces(english_claims, english_report):
    translator = Translator(FixtureTranslationProvider({"c-point": provider_output(chain_problem(excerpt="the lamp burns brightly"))}))
    outcome = verify_claim(english_claims["c-point"], english_report, translator, config=CFG)
    assert outcome.display_status is S.ENTAILED  # the encoding is still entailed...
    assert "E1" in outcome.verification.ungrounded_dependencies  # ...but the quotation is reported as unverified
    assert "E1 (quotation, established; grounding check failed)" in outcome.summary
    assert "Failed grounding checks:" in outcome.summary


def test_verify_claim_ambiguous_still_runs_engine_but_displays_ambiguous(english_claims, english_report):
    translator = Translator(FixtureTranslationProvider({"c-point": provider_output(chain_problem(), ambiguous=True, flags=[{"code": "SCOPE", "message": "point or thesis", "alternatives": ["point", "thesis"]}])}))
    outcome = verify_claim(english_claims["c-point"], english_report, translator, config=CFG)
    assert outcome.display_status is S.AMBIGUOUS_TRANSLATION
    assert outcome.verification is not None and outcome.verification.status is S.ENTAILED
    assert "returned ENTAILED" in outcome.summary and "not displayed as a result" in outcome.summary
    assert "Ambiguity: SCOPE: point or thesis" in outcome.summary


def test_verify_claim_not_eligible_skips_engine_and_reviewer(english_claims, english_report):
    reviewer = SemanticReviewer(FixtureReviewProvider({}))
    outcome = verify_claim(english_claims["c-interp"], english_report, Translator(FixtureTranslationProvider({})), reviewer=reviewer, config=CFG)
    assert outcome.display_status is S.NOT_ELIGIBLE and outcome.verification is None and outcome.semantic_review is None
    assert "not eligible; routed to subject_evaluator" in outcome.summary and "nothing was submitted to the solver" in outcome.summary


def test_verify_claim_unsupported_and_failed(english_claims, english_report):
    unsupported = verify_claim(english_claims["c-point"], english_report, Translator(FixtureTranslationProvider({"c-point": provider_output(None, unsupported_reason="modal reasoning")})), config=CFG)
    assert unsupported.display_status is S.UNSUPPORTED and "modal reasoning" in unsupported.summary and unsupported.verification is None
    failed = verify_claim(english_claims["c-point"], english_report, Translator(FixtureTranslationProvider({})), config=CFG)
    assert failed.display_status is S.INTERNAL_ERROR and "provider error" in failed.summary


def test_verify_claim_quantitative_false_claim_is_unsatisfiable():
    claim = make_claim("c-2x", "2x = 1 has an integer solution", "quantitative", subject="Mathematics: Analysis and Approaches")
    report = make_report([claim], subject=claim.subject, agent_id="maths-specialist")
    problem = {
        "ir_version": "1.0", "problem_id": "p-2x", "request_id": "req-1", "claim_id": "c-2x", "query": "satisfiability",
        "symbols": [{"name": "x", "sort": "Int"}],
        "premises": [{"id": "P", "expr": cmp("eq", {"op": "mul", "args": [I(2), V("x")]}, I(1)), "grounding": {"kind": "arithmetic_fact"}}],
    }
    outcome = verify_claim(claim, report, Translator(FixtureTranslationProvider({"c-2x": provider_output(problem, glossary=[])})), config=CFG)
    assert outcome.display_status is S.UNSATISFIABLE and "cannot all hold together" in outcome.summary


def test_summary_is_bounded_and_keeps_scope_statement():
    claim = make_claim(supporting_claim_ids=["c-ev"])
    translation = make_translation(T.INVALID_FORMALIZATION, diagnostics=[("diagnostic " + str(i) + " ") * 40 for i in range(12)])
    findings = [StructuralFinding(code=f"X-{i}", severity="error", message=("long finding text " * 30), claim_ids=["c-point"]) for i in range(12)]
    outcome = compose_outcome(claim, translation, structural=findings)
    assert len(outcome.summary) <= SUMMARY_MAX_CHARS and outcome.summary.endswith(SCOPE_STATEMENT)
    assert "[summary truncated]" in outcome.summary
    assert outcome.summary.index("[summary truncated]") < outcome.summary.index(SCOPE_STATEMENT)
    assert _fit("a" * 10_000, "TAIL", limit=100).endswith("\nTAIL") and len(_fit("a" * 10_000, "TAIL", limit=100)) == 100
    assert _fit("short", "TAIL", limit=100) == "short\nTAIL"


def test_non_translated_outcomes_are_never_definitive():
    claim = make_claim(supporting_claim_ids=["c-ev"])
    for status in T:
        if status is T.TRANSLATED:
            continue
        outcome = compose_outcome(claim, make_translation(status))
        assert outcome.display_status not in DEFINITIVE
