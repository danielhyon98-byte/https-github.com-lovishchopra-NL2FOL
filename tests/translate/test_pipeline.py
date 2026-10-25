"""Translator pipeline with the fixture provider: every status path, retries, grounding, request content."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.translate import Translator, TranslationStatus, prompts
from epinoic_logic.translate.contracts import EligibilityClass as C
from epinoic_logic.translate.providers import FixtureTranslationProvider, ProviderError
from epinoic_logic.translate.providers.rendering import render_translation_user_prompt
from epinoic_logic.translate.subjects import prompt_profile_text, resolve_profile
from epinoic_logic.version import POLICY_VERSION, TRANSLATOR_VERSION

from .conftest import I, V, chain_problem, cmp, make_claim, make_report, provider_output


def translate(responses, claims, report, claim_id="c-point", **kw):
    provider = FixtureTranslationProvider(responses)
    return Translator(provider, **kw).translate(claims[claim_id], report), provider


def test_translated_sets_verified_flags_and_bookkeeping(english_claims, english_report):
    result, provider = translate({"c-point": provider_output(chain_problem())}, english_claims, english_report)
    assert result.status is TranslationStatus.TRANSLATED
    assert result.problem is not None and result.interpretation is not None
    assert result.problem.premises[0].grounding.verified is True            # quotation checked by code
    assert result.problem.premises[1].grounding.verified is None            # inference not checkable
    assert result.problem.symbols[0].grounding.verified is True
    assert any(c.method == "verbatim_match" and c.verified for c in result.grounding_checks)
    assert result.provider.provider_name == "fixture" and result.provider.attempts == 1
    # rewritten (12 Oct 2026 review fixes): the prompt changed, so its version did; the rule is the same, the record names
    # the prompt in use (translate_v3 since the argument diagnosis, rules argdiag-1), and translate_v1 and translate_v2 stay
    # packaged unchanged (test_stem_subjects pins their digests)
    assert result.provider.prompt_version == prompts.TRANSLATE_PROMPT_VERSION == "translate_v3"
    assert result.translator_version == TRANSLATOR_VERSION and result.policy_version == POLICY_VERSION
    assert result.eligibility.eligibility_class is C.PROPOSITIONAL_ARGUMENT
    assert result.claim_id == "c-point" and result.request_id == "req-1" and result.report_id == "rep-1"
    assert result.translation_id.startswith("tr-") and result.created_at.endswith("Z")
    assert len(provider.calls) == 1
    json.loads(result.model_dump_json())  # serialisable for the Overseer


def test_request_carries_supporting_claims_texts_and_subject_profile(english_claims, english_report):
    _, provider = translate({"c-point": provider_output(chain_problem())}, english_claims, english_report)
    request = provider.calls[0]
    assert [c.claim_id for c in request.supporting_claims] == ["c-ev", "c-link"]
    assert [t.document_id for t in request.supplied_texts] == ["doc-1"]
    assert request.prior_diagnostics == [] and request.ir_version == "1.0"
    assert request.subject_profile_text == prompt_profile_text(resolve_profile("English A: Literature"))
    prompt = render_translation_user_prompt(request)
    assert "<<<DATA subject_profile>>>" in prompt and "<<<DATA prior_diagnostics>>>" not in prompt
    assert "English A: Literature" in prompt and "PROPOSITIONAL_ARGUMENT" in prompt


def test_invalid_then_valid_retries_once_with_prior_diagnostics(english_claims, english_report):
    bad = chain_problem()
    bad["premises"][0]["expr"] = {"op": "exec", "code": "import os"}  # unknown operator -> schema violation
    result, provider = translate({"c-point": [provider_output(bad), provider_output(chain_problem())]}, english_claims, english_report)
    assert result.status is TranslationStatus.TRANSLATED and result.provider.attempts == 2
    assert len(provider.calls) == 2 and provider.calls[1].prior_diagnostics
    assert any("does not match the schema" in d for d in result.diagnostics)
    assert "<<<DATA prior_diagnostics>>>" in render_translation_user_prompt(provider.calls[1])


def test_always_invalid_is_invalid_formalization(english_claims, english_report):
    bad = chain_problem()
    bad["premises"][0]["expr"] = cmp("gt", V("q"), I(1))  # Bool compared with Int -> sort error from the validator
    result, provider = translate({"c-point": provider_output(bad)}, english_claims, english_report)
    assert result.status is TranslationStatus.INVALID_FORMALIZATION and result.problem is None
    assert result.provider.attempts == 2 and len(provider.calls) == 2
    assert len([d for d in result.diagnostics if d.startswith("attempt ")]) >= 2 and any("E102" in d for d in result.diagnostics)


def test_mismatched_claim_id_is_invalid_without_retry(english_claims, english_report):
    result, provider = translate({"c-point": provider_output(chain_problem(claim_id="c-other"))}, english_claims, english_report)
    assert result.status is TranslationStatus.INVALID_FORMALIZATION
    assert len(provider.calls) == 1 and result.provider.attempts == 1
    assert any("do not match the claim" in d for d in result.diagnostics)


def test_mismatched_request_id_is_invalid_without_retry(english_claims, english_report):
    result, provider = translate({"c-point": provider_output(chain_problem(request_id="req-other"))}, english_claims, english_report)
    assert result.status is TranslationStatus.INVALID_FORMALIZATION and len(provider.calls) == 1


def test_ambiguous_flag_true(english_claims, english_report):
    flags = [{"code": "SCOPE", "message": "the point could be the thesis", "alternatives": ["point", "thesis"]}]
    result, _ = translate({"c-point": provider_output(chain_problem(), ambiguous=True, flags=flags)}, english_claims, english_report)
    assert result.status is TranslationStatus.AMBIGUOUS_TRANSLATION
    assert result.problem is not None and result.interpretation.ambiguity_flags[0].code == "SCOPE"


def test_ambiguity_flags_alone_make_it_ambiguous(english_claims, english_report):
    flags = [{"code": "REF", "message": "which room 'the room' is"}]
    result, _ = translate({"c-point": provider_output(chain_problem(), ambiguous=False, flags=flags)}, english_claims, english_report)
    assert result.status is TranslationStatus.AMBIGUOUS_TRANSLATION


def test_ambiguous_true_without_flags_is_noted(english_claims, english_report):
    result, _ = translate({"c-point": provider_output(chain_problem(), ambiguous=True)}, english_claims, english_report)
    assert result.status is TranslationStatus.AMBIGUOUS_TRANSLATION
    assert any("without listing ambiguity flags" in d for d in result.diagnostics)


def test_problem_null_is_unsupported_without_retry(english_claims, english_report):
    result, provider = translate(
        {"c-point": provider_output(None, unsupported_reason="needs quantification over every reader")},
        english_claims, english_report,
    )
    assert result.status is TranslationStatus.UNSUPPORTED and result.problem is None
    assert len(provider.calls) == 1 and any("needs quantification over every reader" in d for d in result.diagnostics)


def test_validator_policy_rejection_is_unsupported_without_retry(english_claims, english_report):
    problem = {
        "ir_version": "1.0", "problem_id": "p-nl", "request_id": "req-1", "claim_id": "c-struct", "query": "entailment",
        "symbols": [{"name": "a", "sort": "Int"}, {"name": "b", "sort": "Int"}],
        "premises": [{"id": "P", "expr": cmp("gt", {"op": "mul", "args": [V("a"), V("b")]}, I(0))}],
        "conclusion": {"id": "C", "expr": cmp("gt", V("a"), I(0))},
    }
    claim = make_claim("c-struct", "The two strands multiply to more than zero.", "structural")
    report = make_report([claim])
    result, provider = translate({"c-struct": provider_output(problem, glossary=[])}, {"c-struct": claim}, report, claim_id="c-struct")
    assert result.status is TranslationStatus.UNSUPPORTED and len(provider.calls) == 1
    assert any("E201" in d for d in result.diagnostics)


@pytest.mark.parametrize("claim_id", ["c-ev", "c-interp"])
def test_ineligible_claims_never_reach_the_provider(english_claims, english_report, claim_id):
    result, provider = translate({claim_id: provider_output(chain_problem(claim_id=claim_id))}, english_claims, english_report, claim_id=claim_id)
    assert result.status is TranslationStatus.NOT_ELIGIBLE and provider.calls == [] and result.provider is None
    assert result.problem is None and result.diagnostics == list(result.eligibility.reasons)


def test_provider_error_is_translation_failed(english_claims, english_report):
    result, provider = translate({}, english_claims, english_report)  # no fixture for the claim
    assert result.status is TranslationStatus.TRANSLATION_FAILED and result.problem is None
    assert result.provider is not None and result.provider.provider_name == "fixture" and result.provider.attempts == 1
    assert any("provider error" in d for d in result.diagnostics) and len(provider.calls) == 1


def test_provider_error_on_retry_is_translation_failed_with_two_attempts(english_claims, english_report):
    bad = chain_problem()
    bad["symbols"][0]["sort"] = "Complex"
    result, provider = translate({"c-point": [provider_output(bad), ProviderError("upstream unavailable", transient=True)]}, english_claims, english_report)
    assert result.status is TranslationStatus.TRANSLATION_FAILED and result.provider.attempts == 2 and len(provider.calls) == 2


def test_non_json_text_is_retried_then_accepted(english_claims, english_report):
    result, provider = translate({"c-point": ["Sure! Here is the problem:", provider_output(chain_problem())]}, english_claims, english_report)
    assert result.status is TranslationStatus.TRANSLATED and result.provider.attempts == 2
    assert any("not valid JSON" in d or "empty" in d for d in result.diagnostics)
    assert provider.calls[1].prior_diagnostics and len(provider.calls[1].prior_diagnostics) == 1


def test_fenced_json_is_accepted(english_claims, english_report):
    text = "```json\n" + json.dumps(provider_output(chain_problem())) + "\n```"
    result, _ = translate({"c-point": text}, english_claims, english_report)
    assert result.status is TranslationStatus.TRANSLATED and result.provider.attempts == 1


def test_missing_keys_and_bad_ambiguous_type_are_invalid(english_claims, english_report):
    missing = {"problem": chain_problem(), "interpretation": {"reading": "x"}}
    bad_flag = provider_output(chain_problem())
    bad_flag["ambiguous"] = "false"
    result, provider = translate({"c-point": [missing, bad_flag]}, english_claims, english_report)
    assert result.status is TranslationStatus.INVALID_FORMALIZATION and len(provider.calls) == 2
    assert any("missing required key" in d for d in result.diagnostics) and any("JSON boolean" in d for d in result.diagnostics)


def test_invalid_interpretation_is_invalid_formalization(english_claims, english_report):
    out = provider_output(chain_problem())
    out["interpretation"] = {"reading": "x", "glossary": "not a list"}
    result, provider = translate({"c-point": out}, english_claims, english_report)
    assert result.status is TranslationStatus.INVALID_FORMALIZATION and len(provider.calls) == 2
    assert any("interpretation does not match the schema" in d for d in result.diagnostics)


def test_hallucinated_quotation_is_translated_but_flagged(english_claims, english_report):
    result, _ = translate({"c-point": provider_output(chain_problem(excerpt="the lamp burns brightly"))}, english_claims, english_report)
    assert result.status is TranslationStatus.TRANSLATED
    assert result.problem.premises[0].grounding.verified is False
    assert any(c.verified is False for c in result.grounding_checks)
    assert any("grounding check(s) failed" in d for d in result.diagnostics)


def test_max_attempts_is_respected(english_claims, english_report):
    bad = chain_problem()
    bad["symbols"][0]["sort"] = "Complex"
    result, provider = translate({"c-point": provider_output(bad)}, english_claims, english_report, max_attempts=3)
    assert result.status is TranslationStatus.INVALID_FORMALIZATION and len(provider.calls) == 3 and result.provider.attempts == 3
    with pytest.raises(ValueError):
        Translator(FixtureTranslationProvider({}), max_attempts=0)


def test_claim_must_belong_to_report(english_claims, english_report):
    stray = make_claim("c-stray", "x", "point", report_id="rep-other", supporting_claim_ids=["a"])
    with pytest.raises(ValueError):
        Translator(FixtureTranslationProvider({})).translate(stray, english_report)


def test_fixture_provider_bookkeeping():
    provider = FixtureTranslationProvider({"a": ["one", {"two": 2}], "b": 3})
    claim = make_claim("a", "x", "point", supporting_claim_ids=["y"])
    from epinoic_logic.translate.eligibility import decide_eligibility
    from epinoic_logic.translate.providers import TranslationRequest
    request = TranslationRequest(claim=claim, eligibility=decide_eligibility(claim), prompt_version="translate_v1", ir_version="1.0")
    assert provider.propose(request).raw_text == "one"
    assert provider.propose(request).raw_text == '{"two": 2}'
    assert provider.propose(request).raw_text == '{"two": 2}' and provider.served("a") == 3  # last entry repeats
    bad_request = request.model_copy(update={"claim": make_claim("b", "x", "point", supporting_claim_ids=["y"])})
    with pytest.raises(ProviderError):
        provider.propose(bad_request)
    with pytest.raises(ProviderError):
        provider.propose(request.model_copy(update={"claim": make_claim("zzz", "x", "point")}))
