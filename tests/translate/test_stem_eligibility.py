"""Eligibility rule 4 with a mathematical relation sign (docs/STEM_DESIGN.md, section 9.3): a quantitative or structural
claim that states a relation between operands is eligible in a profile that allows quantitative claims, and only there;
superscript and subscript digits are numerals."""
from __future__ import annotations

import pytest

from epinoic_logic.translate.contracts import EligibilityClass as C
from epinoic_logic.translate.eligibility import decide_eligibility, has_numeral, has_relation_sign
from epinoic_logic.translate.pipeline import apply_subject_policy
from epinoic_logic.translate.subjects import resolve_profile

from .conftest import make_claim


@pytest.mark.parametrize("text", ["F = ma", "x ≤ y", "E ≈ hf", "a ≠ b", "p < q", "v > u", "E <= mc", "a >= b", "n(H2O) = m/M", "(v − u) = at", "x=y"])
def test_relation_signs_between_operands(text):
    assert has_relation_sign(text)


@pytest.mark.parametrize("text", ["a == b", "=>", "p -> q", "x->y", "the cost of living", "a <== b", "= 5", "rose <"])
def test_not_relation_signs(text):
    assert not has_relation_sign(text)


@pytest.mark.parametrize("text", ["x²", "v₀", "⁻³", "H₂O"])
def test_superscript_and_subscript_digits_are_numerals_for_rule_4(text):
    assert has_numeral(text, scripts=True)
    d = decide_eligibility(make_claim(claim_role="quantitative", claim_text=f"the value {text}", subject="Physics"))
    assert d.eligible and any("numerals" in r for r in d.reasons)


def test_script_digits_change_nothing_for_argument_only_profiles_or_other_rules():
    assert not has_numeral("the footnote¹ says so")  # the default reading of every other rule is unchanged
    d = decide_eligibility(make_claim(claim_role="quantitative", claim_text="the footnote¹ says so", subject="English A: Literature"))
    assert not d.eligible and d.eligibility_class is C.NOT_ELIGIBLE_OTHER
    ev = decide_eligibility(make_claim(claim_role="evidence", claim_text="the footnote¹ says so", subject="History"))
    assert ev.eligibility_class is C.NOT_ELIGIBLE_FACTUAL


@pytest.mark.parametrize("subject", ["Physics", "Chemistry", "Mathematics: Analysis and Approaches", "Computer Science", "General Science", "Economics", "History"])
@pytest.mark.parametrize("role,cls", [("quantitative", C.QUANTITATIVE_CLAIM), ("structural", C.ARITHMETIC_CONSTRAINT)])
def test_a_relation_with_no_numeral_is_eligible_where_quantitative_claims_are(subject, role, cls):
    d = decide_eligibility(make_claim(claim_role=role, claim_text="F = ma", subject=subject))
    assert d.eligible and d.eligibility_class is cls
    assert any("a mathematical relation sign" in r for r in d.reasons)


@pytest.mark.parametrize("subject", ["English A: Literature", "Philosophy", "Theory of Knowledge", "Underwater Basket Weaving"])
def test_argument_only_profiles_are_unchanged(subject):
    d = decide_eligibility(make_claim(claim_role="quantitative", claim_text="F = ma", subject=subject))
    assert not d.eligible and d.eligibility_class is C.NOT_ELIGIBLE_OTHER and d.reasons[-1] == "no numerals or comparatives in claim text"


def test_numerals_and_comparatives_still_decide_first():
    d = decide_eligibility(make_claim(claim_role="quantitative", claim_text="x = 15", subject="Philosophy"))
    assert d.eligible and any("numerals" in r for r in d.reasons) and not any("relation sign" in r for r in d.reasons)
    # and the subject policy still narrows it where quantitative claims are not allowed
    narrowed = apply_subject_policy(d, resolve_profile("Philosophy"))
    assert not narrowed.eligible


def test_a_derivation_step_from_the_stem_parser_is_eligible():
    d = decide_eligibility(make_claim(claim_role="quantitative", claim_text="v² = u² + 2as", subject="Physics"))
    assert d.eligible and d.eligibility_class is C.QUANTITATIVE_CLAIM
