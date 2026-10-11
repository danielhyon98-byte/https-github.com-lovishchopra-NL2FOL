"""Deterministic eligibility rules, per role and proposed kind."""
from __future__ import annotations

import pytest

from epinoic_logic.translate.contracts import EligibilityClass as C
from epinoic_logic.translate.eligibility import decide_eligibility, has_comparative, has_numeral
from epinoic_logic.version import POLICY_VERSION

from .conftest import make_claim


def test_kind_rubric_judgment_wins_over_role():
    d = decide_eligibility(make_claim(claim_role="point", proposed_claim_kind="rubric_judgment", supporting_claim_ids=["x"]))
    assert d.eligibility_class is C.NOT_ELIGIBLE_RUBRIC_JUDGMENT and not d.eligible
    assert d.route_to == "subject_evaluator" and d.decided_by == "deterministic" and d.policy_version == POLICY_VERSION


def test_kind_factual_routes_to_evidence_service():
    d = decide_eligibility(make_claim(claim_role="point", proposed_claim_kind="factual", supporting_claim_ids=["x"]))
    assert d.eligibility_class is C.NOT_ELIGIBLE_FACTUAL and d.route_to == "evidence_service"


@pytest.mark.parametrize("role", ["point", "thesis", "link"])
def test_argument_roles_need_supporting_claims(role):
    with_support = decide_eligibility(make_claim(claim_role=role, supporting_claim_ids=["c-ev"]))
    assert with_support.eligibility_class is C.PROPOSITIONAL_ARGUMENT and with_support.eligible and with_support.route_to is None
    alone = decide_eligibility(make_claim(claim_role=role))
    assert alone.eligibility_class is C.NOT_ELIGIBLE_OTHER and not alone.eligible and alone.route_to == "unresolved"
    assert any("no supporting claims" in r for r in alone.reasons)


def test_structural_role_with_numerals_is_arithmetic_constraint():
    d = decide_eligibility(make_claim(claim_role="structural", claim_text="The paragraph has 320 words."))
    assert d.eligibility_class is C.ARITHMETIC_CONSTRAINT and d.eligible


def test_quantitative_role_with_comparative_cue():
    d = decide_eligibility(make_claim(claim_role="quantitative", claim_text="Average speed exceeds the limit."))
    assert d.eligibility_class is C.QUANTITATIVE_CLAIM and d.eligible


def test_count_roles_without_cues_are_not_eligible():
    d = decide_eligibility(make_claim(claim_role="structural", claim_text="The paragraph is well organised."))
    assert d.eligibility_class is C.NOT_ELIGIBLE_OTHER and d.route_to == "unresolved"


@pytest.mark.parametrize("role", ["interpretation", "effect", "device"])
def test_standalone_interpretive_roles(role):
    d = decide_eligibility(make_claim(claim_role=role, claim_text="The diction is clinical."))
    assert d.eligibility_class is C.NOT_ELIGIBLE_INTERPRETIVE and d.route_to == "subject_evaluator"


def test_evidence_role_routes_to_grounding_not_solver():
    d = decide_eligibility(make_claim(claim_role="evidence", claim_text='"The lamp stays unlit"'))
    assert d.eligibility_class is C.NOT_ELIGIBLE_FACTUAL and d.route_to == "evidence_service"


@pytest.mark.parametrize(
    "kind,text,expected,eligible",
    [
        ("formal_logic", "If A then B; A; so B.", C.PROPOSITIONAL_ARGUMENT, True),
        ("arithmetic", "2x = 1 has no integer solution", C.QUANTITATIVE_CLAIM, True),
        ("arithmetic", "the sum is large", C.NOT_ELIGIBLE_OTHER, False),
        ("interpretive", "the tone is bleak", C.NOT_ELIGIBLE_INTERPRETIVE, False),
        ("unknown", "something else", C.NOT_ELIGIBLE_OTHER, False),
    ],
)
def test_other_role_by_kind(kind, text, expected, eligible):
    d = decide_eligibility(make_claim(claim_role="other", claim_text=text, proposed_claim_kind=kind))
    assert d.eligibility_class is expected and d.eligible is eligible


def test_agent_self_report_is_recorded_but_ignored():
    says_eligible = decide_eligibility(make_claim(claim_role="interpretation", advisory_verification_eligibility=True))
    assert not says_eligible.eligible
    assert any("advisory and was not used" in r for r in says_eligible.reasons)
    says_not = decide_eligibility(make_claim(claim_role="point", supporting_claim_ids=["x"], advisory_verification_eligibility=False))
    assert says_not.eligible


def test_lexical_cues():
    assert has_numeral("twelve lines") and has_numeral("3 strands") and not has_numeral("many lines")
    assert has_comparative("at least two") and has_comparative("fewer than") and not has_comparative("some")


def test_policy_version_is_bound():
    d = decide_eligibility(make_claim(claim_role="point", supporting_claim_ids=["x"]), policy_version="test-policy")
    assert d.policy_version == "test-policy"
