"""Translation-layer regressions from the overseer round-1 findings: grounding of excerpts under
any kind, the elision window, strict provider-output parsing, self-support, subject resolution,
and signature verification in the outcome composer."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine import verify as engine_verify
from epinoic_logic.engine.provenance import sign_result, verify_signature
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import Translator, TranslationStatus as T, compose_outcome, display_status_for, verify_claim
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.grounding import ELISION_WINDOW_CHARS, check_problem_grounding, locate_quotation, locate_quotation_inexact
from epinoic_logic.translate.parsing import ProviderOutputError, parse_json_object
from epinoic_logic.translate.providers import FixtureTranslationProvider
from epinoic_logic.translate.subjects import PROFILES, UNKNOWN, resolve_profile

from .conftest import DOC_ID, TEXT, V, chain_problem, make_claim, make_report, provider_output

CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)
DOCS = [SuppliedText(document_id=DOC_ID, text=TEXT, locator_scheme="none")]
KEY = b"overseer-round1-signing-key-0123"


# ------------------------------------------------------------------ grounding


def test_excerpt_under_a_non_quotation_kind_is_still_checked():
    data = chain_problem()
    data["premises"][0]["grounding"] = {"kind": "supplied_text", "source_refs": [{"document_id": DOC_ID, "excerpt": "the lamp burns brightly"}]}
    checked, checks = check_problem_grounding(Problem.model_validate(data), DOCS)
    e1 = [c for c in checks if c.target_id == "E1"]
    assert e1 and e1[0].kind == "supplied_text" and e1[0].verified is False and "not found" in e1[0].detail
    assert checked.premises[0].grounding.verified is False
    data["premises"][0]["grounding"]["source_refs"][0]["excerpt"] = "The lamp stays unlit"
    checked2, checks2 = check_problem_grounding(Problem.model_validate(data), DOCS)
    assert checked2.premises[0].grounding.verified is True and [c for c in checks2 if c.target_id == "E1"][0].method == "verbatim_match"
    # without an excerpt the kind stays not checkable
    data["premises"][0]["grounding"] = {"kind": "supplied_text"}
    _, checks3 = check_problem_grounding(Problem.model_validate(data), DOCS)
    assert [c for c in checks3 if c.target_id == "E1"][0].method == "not_checkable"


def test_invented_excerpt_under_supplied_text_kind_reaches_the_outcome(english_claims, english_report):
    data = chain_problem()
    data["premises"][0]["grounding"] = {"kind": "supplied_text", "source_refs": [{"document_id": DOC_ID, "excerpt": "the lamp burns brightly"}]}
    outcome = verify_claim(english_claims["c-point"], english_report, Translator(FixtureTranslationProvider({"c-point": provider_output(data)})), config=CFG)
    assert outcome.display_status is S.ENTAILED
    assert "E1" in outcome.verification.ungrounded_dependencies and "Failed grounding checks" in outcome.summary


def test_inexact_match_sets_detail_but_never_verified(english_claims, english_report):
    data = chain_problem(excerpt="the lamp stays unlit")  # text has "The lamp"
    result = Translator(FixtureTranslationProvider({"c-point": provider_output(data)})).translate(english_claims["c-point"], english_report)
    e1 = [c for c in result.grounding_checks if c.target_id == "E1"][0]
    assert e1.verified is False and "differs in form" in e1.detail and "initial capital" in e1.detail
    assert result.problem.premises[0].grounding.verified is False


def test_elision_is_bounded_by_a_window():
    far_text = "The lamp stays unlit. " + ("Filler sentence here. " * 40) + "The clock ticks on."
    assert len(far_text) > ELISION_WINDOW_CHARS + 40
    assert locate_quotation("The lamp ... ticks on", far_text) is None
    assert locate_quotation("The lamp ... ticks on", TEXT) is not None  # a short span still matches
    assert locate_quotation_inexact("the lamp stays unlit", TEXT)[1] == "differs only in the initial capital"
    assert locate_quotation_inexact("the lamp stays lit", TEXT) is None


# ------------------------------------------------------------------ parsing


def test_deeply_nested_provider_output_is_a_status_not_an_exception(english_claims, english_report):
    deep = "[" * 100_000
    with pytest.raises(ProviderOutputError, match="too deep"):
        parse_json_object(deep)
    result = Translator(FixtureTranslationProvider({"c-point": deep})).translate(english_claims["c-point"], english_report)
    assert result.status is T.INVALID_FORMALIZATION and any("too deep" in d for d in result.diagnostics)
    outcome = verify_claim(english_claims["c-point"], english_report, Translator(FixtureTranslationProvider({"c-point": deep})), config=CFG)
    assert outcome.display_status is S.INVALID_FORMALIZATION


def test_duplicate_keys_in_provider_output_are_rejected(english_claims, english_report):
    good = json.dumps(provider_output(chain_problem()))
    duplicated = good[:-1] + ', "problem": null}'
    with pytest.raises(ProviderOutputError, match="duplicate key"):
        parse_json_object(duplicated)
    result = Translator(FixtureTranslationProvider({"c-point": duplicated})).translate(english_claims["c-point"], english_report)
    assert result.status is T.INVALID_FORMALIZATION and any("duplicate key" in d for d in result.diagnostics)


# ------------------------------------------------------------------ self-support


def test_self_supporting_point_never_reaches_the_provider():
    claim = make_claim("c-self", "Justice is laundered.", "point", supporting_claim_ids=["c-self"])
    report = make_report([claim])
    provider = FixtureTranslationProvider({"c-self": provider_output(chain_problem(claim_id="c-self"))})
    result = Translator(provider).translate(claim, report)
    assert result.status is T.NOT_ELIGIBLE and provider.calls == []
    assert any("self-reference" in r for r in result.eligibility.reasons)


def test_self_reference_is_dropped_from_supporting_claims_sent_to_the_provider(english_claims, english_report):
    point = english_claims["c-point"].model_copy(update={"supporting_claim_ids": ["c-point", "c-ev", "c-link"]})
    report = english_report.model_copy(update={"claims": [point if c.claim_id == "c-point" else c for c in english_report.claims]})
    provider = FixtureTranslationProvider({"c-point": provider_output(chain_problem())})
    result = Translator(provider).translate(point, report)
    assert result.status is T.TRANSLATED
    assert [c.claim_id for c in provider.calls[0].supporting_claims] == ["c-ev", "c-link"]


# ------------------------------------------------------------------ subjects


def test_every_profile_resolves_from_its_own_display_name():
    for key, profile in PROFILES.items():
        assert resolve_profile(profile.display_name) is profile, key
        assert resolve_profile(profile.display_name + " HL") is profile, key
    assert resolve_profile("Sports Exercise and Health Science SL").key == "sports_science"


def test_sports_science_quantitative_claim_is_translated():
    from .conftest import physics_problem

    claim = make_claim("c-v", "Average speed v = 120 / 8 = 15.", "quantitative", subject="Sports, Exercise and Health Science", agent_id="sehs-specialist")
    report = make_report([claim], subject=claim.subject, agent_id="sehs-specialist")
    provider = FixtureTranslationProvider({"c-v": provider_output(physics_problem(), glossary=[])})
    result = Translator(provider).translate(claim, report)
    assert result.status is T.TRANSLATED and result.eligibility.eligibility_class.value == "QUANTITATIVE_CLAIM" and len(provider.calls) == 1


@pytest.mark.parametrize("label", ["Spanish A: Literature", "German A: Language and Literature HL", "French A Literature"])
def test_other_language_a_labels_resolve_to_language_a_other(label):
    assert resolve_profile(label).key == "language_a_other"
    assert resolve_profile("English A: Literature").key == "english_a_literature"
    assert resolve_profile("Underwater Basket Weaving") is UNKNOWN


# ------------------------------------------------------------------ outcome signature


def _translated(problem: Problem, claim):
    from epinoic_logic.translate.contracts import EligibilityDecision, ProviderInfo, TranslationResult

    return TranslationResult(
        translation_id="tr-sig", claim_id=claim.claim_id, request_id=claim.request_id, report_id=claim.report_id, status=T.TRANSLATED,
        eligibility=EligibilityDecision(eligibility_class="PROPOSITIONAL_ARGUMENT", eligible=True, decided_by="deterministic", reasons=["r"], policy_version="p"),
        problem=problem, provider=ProviderInfo(provider_name="fixture"), translator_version="t", policy_version="p", created_at="2026-10-11T00:00:00Z",
    )


def test_forged_status_is_rejected_when_the_composer_holds_the_key():
    claim = make_claim(supporting_claim_ids=["c-ev"])
    problem = Problem.model_validate(chain_problem(with_l2=False))
    honest = engine_verify(problem, CFG, signing_key=KEY, key_id="p")
    assert honest.status is S.COUNTEREXAMPLE and verify_signature(honest, KEY)
    forged = honest.model_copy(update={"status": S.ENTAILED, "counterexample": None})
    assert not verify_signature(forged, KEY)
    translation = _translated(problem, claim)
    assert display_status_for(translation, forged) is S.ENTAILED  # without the key the composer cannot tell
    assert display_status_for(translation, forged, signing_key=KEY) is S.INTERNAL_ERROR
    outcome = compose_outcome(claim, translation, forged, signing_key=KEY, key_id="p")
    assert outcome.display_status is S.INTERNAL_ERROR and "signature does not verify (E501)" in outcome.summary
    unsigned = engine_verify(problem, CFG)
    assert compose_outcome(claim, translation, unsigned, signing_key=KEY).display_status is S.INTERNAL_ERROR
    assert compose_outcome(claim, translation, honest, signing_key=KEY, key_id="other").display_status is S.INTERNAL_ERROR
    good = compose_outcome(claim, translation, honest, signing_key=KEY, key_id="p")
    assert good.display_status is S.COUNTEREXAMPLE and "verified by this layer" in good.summary


def test_summary_never_claims_an_unverified_signature_was_checked():
    claim = make_claim(supporting_claim_ids=["c-ev"])
    problem = Problem.model_validate(chain_problem())
    signed = engine_verify(problem, CFG, signing_key=KEY, key_id="p")
    without_key = compose_outcome(claim, _translated(problem, claim), signed)
    assert "carries a signature (key p) that this layer did not verify" in without_key.summary and "is signed" not in without_key.summary


def test_vacuous_engine_result_is_displayed_as_invalid_formalization(english_claims, english_report):
    taut = {
        "ir_version": "1.0", "problem_id": "p-taut", "request_id": "req-1", "claim_id": "c-point", "query": "entailment",
        "symbols": [{"name": "p", "sort": "Bool", "meaning": "the point"}], "premises": [],
        "conclusion": {"id": "C", "expr": {"op": "or", "args": [V("p"), {"op": "not", "arg": V("p")}]}, "label": "p or not p"},
    }
    outcome = verify_claim(english_claims["c-point"], english_report, Translator(FixtureTranslationProvider({"c-point": provider_output(taut, glossary=[])})), config=CFG)
    assert outcome.verification.status is S.ENTAILED and outcome.display_status is S.INVALID_FORMALIZATION
    assert "Vacuous result" in outcome.summary and "E108" in outcome.summary and "display status INVALID_FORMALIZATION" in outcome.summary


def test_unverified_dependencies_are_named_and_never_summarised_as_none(english_claims, english_report):
    data = chain_problem()
    for premise in data["premises"][1:]:
        premise["grounding"] = {"kind": "supplied_text", "certainty": "established"}
    outcome = verify_claim(english_claims["c-point"], english_report, Translator(FixtureTranslationProvider({"c-point": provider_output(data)})), config=CFG)
    assert outcome.display_status is S.ENTAILED and outcome.verification.ungrounded_dependencies == []
    assert sorted(outcome.verification.unverified_dependencies) == ["L1", "L2"]
    assert "Unverified dependencies (asserted by the translation, checked by no procedure): L1 (supplied_text, established)" in outcome.summary
    assert "Ungrounded dependencies: none" not in outcome.summary
    circular = {
        "ir_version": "1.0", "problem_id": "p-circ", "request_id": "req-1", "claim_id": "c-point", "query": "entailment",
        "symbols": [{"name": "p", "sort": "Bool", "meaning": "the point"}],
        "premises": [{"id": "P", "expr": V("p"), "label": "the point, asserted", "grounding": {"kind": "supplied_text"}}],
        "conclusion": {"id": "C", "expr": V("p"), "label": "the point"},
    }
    circ = verify_claim(english_claims["c-point"], english_report, Translator(FixtureTranslationProvider({"c-point": provider_output(circular, glossary=[])})), config=CFG)
    assert circ.display_status is S.ENTAILED and circ.verification.unverified_dependencies == ["P"] and "Unverified dependencies" in circ.summary
