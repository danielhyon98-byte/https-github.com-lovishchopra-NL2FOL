"""Subject profiles narrow eligibility: the same claim is treated differently per IB subject."""
from __future__ import annotations

from epinoic_logic.translate import Translator, TranslationStatus, apply_subject_policy
from epinoic_logic.translate.contracts import EligibilityClass as C
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.providers import FixtureTranslationProvider
from epinoic_logic.translate.subjects import UNKNOWN, prompt_profile_text, resolve_profile, route_for

from .conftest import I, V, chain_problem, cmp, make_claim, make_report, physics_problem, provider_output

QUANT_TEXT = "Average speed v = 120 / 8 = 15."


def test_quantitative_claim_in_literature_is_downgraded_to_not_eligible_other():
    claim = make_claim("c-v", QUANT_TEXT, "quantitative", subject="English A: Literature")
    report = make_report([claim])
    provider = FixtureTranslationProvider({"c-v": provider_output(physics_problem())})
    result = Translator(provider).translate(claim, report)
    assert result.status is TranslationStatus.NOT_ELIGIBLE
    assert result.eligibility.eligibility_class is C.NOT_ELIGIBLE_OTHER and not result.eligibility.eligible
    assert result.eligibility.route_to == "unresolved"
    assert "class QUANTITATIVE_CLAIM not allowed for subject profile english_a_literature" in result.eligibility.reasons
    assert provider.calls == [] and result.provider is None and result.problem is None


def test_same_claim_in_physics_is_quantitative_and_translated():
    claim = make_claim("c-v", QUANT_TEXT, "quantitative", subject="Physics", agent_id="physics-specialist")
    report = make_report([claim], subject="Physics", agent_id="physics-specialist")
    assert decide_eligibility(claim).eligibility_class is C.QUANTITATIVE_CLAIM
    provider = FixtureTranslationProvider({"c-v": provider_output(physics_problem(), glossary=[{"symbol": "v", "meaning": "speed"}])})
    result = Translator(provider).translate(claim, report)
    assert result.status is TranslationStatus.TRANSLATED
    assert result.eligibility.eligibility_class is C.QUANTITATIVE_CLAIM and result.eligibility.eligible
    assert len(provider.calls) == 1
    assert provider.calls[0].subject_profile_text == prompt_profile_text(resolve_profile("Physics"))
    assert {s.sort for s in result.problem.symbols} == {"Real"}


def test_unknown_subject_uses_conservative_profile():
    claim = make_claim("c-v", QUANT_TEXT, "quantitative", subject="Underwater Basket Weaving")
    assert resolve_profile(claim.subject) is UNKNOWN
    result = Translator(FixtureTranslationProvider({})).translate(claim, make_report([claim], subject=claim.subject))
    assert result.status is TranslationStatus.NOT_ELIGIBLE and result.eligibility.eligibility_class is C.NOT_ELIGIBLE_OTHER
    assert any("subject profile unknown" in r for r in result.eligibility.reasons)


def test_arithmetic_constraint_is_allowed_in_literature():
    claim = make_claim("c-words", "The paragraph runs to 320 words, under the 350-word guide.", "structural")
    report = make_report([claim])
    problem = {
        "ir_version": "1.0", "problem_id": "p-words", "request_id": "req-1", "claim_id": "c-words", "query": "entailment",
        "symbols": [{"name": "words", "sort": "Int"}],
        "premises": [{"id": "W", "expr": cmp("eq", V("words"), I(320)), "grounding": {"kind": "task_setting"}}],
        "conclusion": {"id": "C", "expr": cmp("le", V("words"), I(350))},
    }
    provider = FixtureTranslationProvider({"c-words": provider_output(problem, glossary=[])})
    result = Translator(provider).translate(claim, report)
    assert result.status is TranslationStatus.TRANSLATED and result.eligibility.eligibility_class is C.ARITHMETIC_CONSTRAINT
    assert len(provider.calls) == 1


def test_real_sort_rejected_by_argument_only_profile():
    claim = make_claim("c-point", supporting_claim_ids=["c-ev"])
    report = make_report([claim])
    problem = chain_problem(extra_symbols=[{"name": "w", "sort": "Real"}], extra_premises=[{"id": "W", "expr": cmp("ge", V("w"), {"op": "real", "value": "0"})}])
    provider = FixtureTranslationProvider({"c-point": provider_output(problem)})
    result = Translator(provider).translate(claim, report)
    assert result.status is TranslationStatus.INVALID_FORMALIZATION
    assert any("not permitted by subject profile english_a_literature" in d for d in result.diagnostics)
    assert len(provider.calls) == 2 and provider.calls[1].prior_diagnostics  # retried with the policy diagnostic


def test_apply_subject_policy_identity_cases():
    allowed = decide_eligibility(make_claim(claim_role="point", supporting_claim_ids=["x"]))
    assert apply_subject_policy(allowed, resolve_profile("English A: Literature")) is allowed
    ineligible = decide_eligibility(make_claim(claim_role="interpretation"))
    assert apply_subject_policy(ineligible, resolve_profile("Physics")) is ineligible
    # History now allows exact date/figure consistency checks (History pack); Philosophy stays argument-only.
    downgraded = apply_subject_policy(decide_eligibility(make_claim(claim_role="quantitative", claim_text="x = 15")), resolve_profile("Philosophy"))
    assert downgraded.eligibility_class is C.NOT_ELIGIBLE_OTHER and downgraded.route_to == route_for(C.NOT_ELIGIBLE_OTHER) == "unresolved"
    assert downgraded.reasons[:-1] == list(decide_eligibility(make_claim(claim_role="quantitative", claim_text="x = 15")).reasons)
