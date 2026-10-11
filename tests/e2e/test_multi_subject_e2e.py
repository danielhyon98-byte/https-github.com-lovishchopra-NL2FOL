"""End to end across IB subjects: every multi-subject fixture yields its expected status through the real engine."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.fixtures_multi_subject import FIXTURES, SubjectFixture, by_name, fixture_responses
from epinoic_logic.engine.provenance import verify_signature
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.statuses import DEFINITIVE, SCOPE_STATEMENT, VerificationStatus as S
from epinoic_logic.translate import Translator, TranslationStatus as T, verify_claim
from epinoic_logic.translate.providers import FixtureTranslationProvider
from epinoic_logic.translate.subjects import UNKNOWN, resolve_profile

CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)
KEY = b"multi-subject-key-0123456789abcd"


def run(fixture: SubjectFixture):
    provider = FixtureTranslationProvider(fixture_responses(fixture))
    outcome = verify_claim(fixture.claim, fixture.report, Translator(provider), config=CFG, signing_key=KEY, key_id="ms")
    return outcome, provider


def test_fixtures_cover_several_subject_groups():
    groups = {resolve_profile(f.subject).group for f in FIXTURES}
    assert {"mathematics", "sciences", "individuals_societies", "language_literature"} <= groups
    assert all(resolve_profile(f.subject) is not UNKNOWN for f in FIXTURES)
    assert len({f.name for f in FIXTURES}) == len(FIXTURES) == 9


@pytest.mark.parametrize("fixture", FIXTURES, ids=[f.name for f in FIXTURES])
def test_fixture_yields_its_expected_status(fixture: SubjectFixture):
    outcome, provider = run(fixture)
    assert outcome.display_status is fixture.expected_display_status
    assert outcome.translation.status is fixture.expected_translation_status
    e = outcome.translation.eligibility
    assert e.eligibility_class is fixture.expected_eligibility_class
    assert e.route_to == fixture.expected_route
    if fixture.expected_reason_fragment:
        assert any(fixture.expected_reason_fragment in r for r in e.reasons), e.reasons
    assert provider.served(fixture.claim.claim_id) == (1 if fixture.provider_called else 0)
    assert outcome.summary.endswith(SCOPE_STATEMENT) and f"display status {fixture.expected_display_status.value}" in outcome.summary
    v = outcome.verification
    if fixture.provider_called:
        assert v is not None and verify_signature(v, KEY) and v.status is fixture.expected_display_status
        assert v.claim_id == fixture.claim.claim_id and v.request_id == fixture.claim.request_id
        if fixture.expected_relied_on:
            assert set(v.premises_relied_on) == set(fixture.expected_relied_on)
        assert sorted(v.ungrounded_dependencies) == sorted(fixture.expected_ungrounded)
    else:
        assert v is None and outcome.translation.provider is None and outcome.display_status not in DEFINITIVE


def test_physics_counterexample_reports_exact_values():
    outcome, _ = run(by_name("physics_counterexample"))
    values = {a.symbol: a.value for a in outcome.verification.counterexample.assignments}
    assert values["d"] == "120" and values["t"] == "8" and values["v"] == "15"  # exact, not 15.0


def test_economics_elasticity_is_exact_rational():
    fixture = by_name("economics_entailed")
    assert fixture.provider_output["problem"]["conclusion"]["expr"]["right"] == {"op": "real", "value": "1/2"}
    outcome, _ = run(fixture)
    assert outcome.display_status is S.ENTAILED


def test_history_links_are_named_in_the_summary():
    outcome, _ = run(by_name("history_entailed"))
    assert "L1 (specialist_inference, probable)" in outcome.summary and "L2 (specialist_inference, probable)" in outcome.summary
    assert all(c.verified is True for c in outcome.translation.grounding_checks if c.kind == "quotation")


def test_english_quantitative_is_downgraded_by_subject_policy_not_by_the_provider():
    fixture = by_name("english_quantitative")
    outcome, provider = run(fixture)
    assert outcome.translation.status is T.NOT_ELIGIBLE and provider.calls == []
    assert any("not allowed for subject profile english_a_literature" in r for r in outcome.translation.eligibility.reasons)
    # the same claim in a quantitative subject is eligible and reaches the provider
    maths_claim = fixture.claim.model_copy(update={"subject": "Mathematics: Analysis and Approaches"})
    maths_report = fixture.report.model_copy(update={"subject": maths_claim.subject, "claims": [maths_claim]})
    provider2 = FixtureTranslationProvider({})
    outcome2 = verify_claim(maths_claim, maths_report, Translator(provider2), config=CFG)
    # the provider IS asked (one call) and, having no fixture, fails -> TRANSLATION_FAILED -> INTERNAL_ERROR display
    assert len(provider2.calls) == 1 and provider2.calls[0].claim.claim_id == maths_claim.claim_id
    assert outcome2.translation.status is T.TRANSLATION_FAILED and outcome2.display_status is S.INTERNAL_ERROR


def test_each_definitive_fixture_has_a_distinct_binding():
    digests = set()
    for fixture in FIXTURES:
        outcome, _ = run(fixture)
        if outcome.verification is not None:
            digests.add(outcome.verification.binding.binding_digest)
    assert len(digests) == sum(1 for f in FIXTURES if f.provider_called)
