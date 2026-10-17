"""STEM subject profiles (docs/STEM_DESIGN.md, section 10.1): the ``stem`` profile, what the STEM profiles say the
formal layer can and cannot establish, the STEM encoding guidance in the model-facing profile text, and the pinned
prompt version left unchanged."""
from __future__ import annotations

import pytest

from epinoic_logic.translate.contracts import EligibilityClass
from epinoic_logic.translate.subjects import (
    PROFILES, SCIENCE_SUBJECTS, STEM_ENCODING_GUIDANCE, STEM_PROFILE_KEYS, UNKNOWN, prompt_profile_text, resolve_profile,
)
from epinoic_logic.version import POLICY_VERSION, TRANSLATOR_VERSION

STEM_KEYS = ("physics", "chemistry", "biology", "ess", "sports_science", "design_technology", "stem", "mathematics_aa", "mathematics_ai",
             "mathematics", "computer_science")


def test_the_stem_profile():
    p = PROFILES["stem"]
    assert p.group == "sciences" and not p.argument_only and p.numeric_sorts == frozenset({"Int", "Real"})
    assert p.allows(EligibilityClass.QUANTITATIVE_CLAIM) and p.allows(EligibilityClass.ARITHMETIC_CONSTRAINT)
    assert resolve_profile(p.display_name) is p and resolve_profile("Physics/Chemistry") is p
    assert set(SCIENCE_SUBJECTS) == {"physics", "chemistry", "biology", "ess", "sports_science", "design_technology"}
    assert STEM_PROFILE_KEYS == frozenset(STEM_KEYS)


@pytest.mark.parametrize("key", STEM_KEYS)
def test_stem_profiles_state_the_truth_about_what_is_checked(key):
    p = PROFILES[key]
    assert "deterministic STEM checks decide" in p.can_check and "written arithmetic" in p.can_check
    assert "do not check units" in p.can_check  # the model translator's formalisations
    for never in ("physical validity", "truth of laws", "diagrams or graphs", "calculus"):
        assert never in p.cannot_check, (key, never)
    assert "units and significant figures (v1)" not in p.cannot_check  # the old text no longer applies to STEM


def test_profile_specific_checks_are_named():
    assert "Boolean identities" in PROFILES["computer_science"].can_check and "program behaviour" in PROFILES["computer_science"].cannot_check
    assert "balances" in PROFILES["chemistry"].can_check and "stated roots" in PROFILES["mathematics_aa"].can_check
    assert "statistical inference" in PROFILES["mathematics_ai"].cannot_check


@pytest.mark.parametrize("key", STEM_KEYS)
def test_stem_profile_text_carries_the_encoding_guidance(key):
    text = prompt_profile_text(PROFILES[key])
    assert text.endswith(STEM_ENCODING_GUIDANCE)
    for phrase in ("no exponent", "substitute the stated values", "s<claim>_v", "unit as an assumption", "UNSUPPORTED"):
        assert phrase in STEM_ENCODING_GUIDANCE


@pytest.mark.parametrize("key", ["history", "english_a_literature", "economics", "philosophy", "tok"])
def test_non_stem_profile_text_is_unchanged(key):
    p = PROFILES[key]
    text = prompt_profile_text(p)
    assert STEM_ENCODING_GUIDANCE not in text
    classes = ", ".join(sorted(c.value for c in p.eligible_classes))
    expected = (f"Subject: {p.display_name} (IB group: {p.group}). Formalizable claim classes: {classes}. The formal check can establish: {p.can_check}. "
                f"It can never establish: {p.cannot_check}. "
                + ("Numeric claims are not expected in this subject; encode argument structure only. " if p.argument_only else
                   f"Numeric sorts in use: {', '.join(sorted(p.numeric_sorts))}; keep Int and Real distinct and write numerals as exact strings. "))
    assert text == expected


def test_versions_are_bumped_and_the_pinned_prompt_is_unchanged():
    import hashlib

    from epinoic_logic.translate import prompts
    # The STEM bump (0.3.0, 2026.10-v3) was followed by the review-fix bump of 2026-10-12 (version.py history); the pin
    # moves with each release and stays exact.
    assert TRANSLATOR_VERSION == "0.4.0" and POLICY_VERSION == "2026.10-v4"
    # rewritten (12 Oct 2026 review fixes), stricter: the prompt in use moved to translate_v2 (exactness, task authority,
    # definitions), and the pinned translate_v1 the STEM work left unchanged is still packaged byte for byte, so every
    # recorded prompt_version names the exact instructions it was produced with
    assert prompts.TRANSLATE_PROMPT_VERSION == "translate_v2"
    digest = hashlib.sha256(prompts.load_prompt("translate_v1").encode("utf-8")).hexdigest()
    assert digest == "02c40eaf48709c838359763725fd2ac4c931e2e9b52272020565d198a9cc469b"
    assert hashlib.sha256(prompts.load_prompt("review_v1").encode("utf-8")).hexdigest() == "224f42bf0bf6c1f6cde358b9f48c7050156447ef7af8af8827c2b15fdbed8f9b"


def test_unknown_stays_the_most_conservative_profile():
    assert resolve_profile("Underwater Basket Weaving") is UNKNOWN and UNKNOWN.argument_only
    assert not UNKNOWN.allows(EligibilityClass.QUANTITATIVE_CLAIM)
