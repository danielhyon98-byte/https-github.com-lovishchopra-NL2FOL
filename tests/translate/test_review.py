"""Advisory semantic-fidelity review: verdict parsing never upgrades to faithful on failure."""
from __future__ import annotations

import pytest

from epinoic_logic.translate import SemanticReviewer, Translator, TranslationStatus, prompts
from epinoic_logic.translate.providers import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.providers.rendering import render_review_user_prompt
from epinoic_logic.translate.review import parse_review_output

from .conftest import chain_problem, provider_output


@pytest.fixture
def translated(english_claims, english_report):
    translation = Translator(FixtureTranslationProvider({"c-point": provider_output(chain_problem())})).translate(english_claims["c-point"], english_report)
    assert translation.status is TranslationStatus.TRANSLATED
    return english_claims["c-point"], translation


def test_faithful_review(translated):
    claim, translation = translated
    provider = FixtureReviewProvider({"c-point": {"verdict": "faithful", "issues": []}})
    review = SemanticReviewer(provider).review(claim, translation)
    assert review.verdict == "faithful" and review.issues == [] and review.advisory_only is True
    assert review.translation_id == translation.translation_id and review.review_id.startswith("rv-")
    # rewritten (12 Oct 2026 review fixes): the review prompt in use is review_v2; same rule
    assert review.reviewer.provider_name == "fixture" and review.reviewer.prompt_version == prompts.REVIEW_PROMPT_VERSION == "review_v2"
    assert len(provider.calls) == 1 and provider.calls[0].problem == translation.problem
    assert "<<<DATA interpretation>>>" in render_review_user_prompt(provider.calls[0])


def test_unfaithful_review_keeps_issues(translated):
    claim, translation = translated
    review = SemanticReviewer(FixtureReviewProvider({"c-point": {"verdict": "Unfaithful", "issues": ["conclusion weakened", 42, None]}})).review(claim, translation)
    assert review.verdict == "unfaithful" and review.issues == ["conclusion weakened", "42"]


def test_unparseable_output_is_uncertain(translated):
    claim, translation = translated
    review = SemanticReviewer(FixtureReviewProvider({"c-point": "I think it is fine."})).review(claim, translation)
    assert review.verdict == "uncertain" and any("could not be parsed" in i for i in review.issues)


def test_unknown_verdict_is_uncertain(translated):
    claim, translation = translated
    review = SemanticReviewer(FixtureReviewProvider({"c-point": {"verdict": "verified", "issues": "single string"}})).review(claim, translation)
    assert review.verdict == "uncertain" and review.issues[0] == "single string" and "not one of" in review.issues[1]


def test_provider_error_is_uncertain(translated):
    claim, translation = translated
    review = SemanticReviewer(FixtureReviewProvider({})).review(claim, translation)
    assert review.verdict == "uncertain" and any("reviewer unavailable" in i for i in review.issues)
    assert review.reviewer.provider_name == "fixture"


def test_review_requires_a_problem(english_claims, english_report):
    translation = Translator(FixtureTranslationProvider({})).translate(english_claims["c-interp"], english_report)
    assert translation.problem is None
    with pytest.raises(ValueError):
        SemanticReviewer(FixtureReviewProvider({})).review(english_claims["c-interp"], translation)


def test_review_rejects_foreign_translation(translated, english_claims):
    _, translation = translated
    with pytest.raises(ValueError):
        SemanticReviewer(FixtureReviewProvider({})).review(english_claims["c-link"], translation)


@pytest.mark.parametrize(
    "text,verdict",
    [
        ('{"verdict": "faithful", "issues": []}', "faithful"),
        ('```json\n{"verdict": "uncertain", "issues": ["vague"]}\n```', "uncertain"),
        ('{"verdict": "FAITHFUL"}', "faithful"),
        ('{"issues": []}', "uncertain"),
        ("[]", "uncertain"),
        ("", "uncertain"),
        ('{"verdict": "faithful", "issues": [{"a": 1}]}', "faithful"),
    ],
)
def test_parse_review_output(text, verdict):
    got, issues = parse_review_output(text)
    assert got == verdict
    assert isinstance(issues, list) and all(isinstance(i, str) for i in issues)
