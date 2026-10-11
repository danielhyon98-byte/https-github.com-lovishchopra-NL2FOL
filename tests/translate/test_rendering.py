"""Prompt rendering is deterministic and places every input inside labelled data blocks."""
from __future__ import annotations

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import Interpretation
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.providers import ReviewRequest, TranslationRequest
from epinoic_logic.translate.providers.rendering import render_review_user_prompt, render_translation_user_prompt
from epinoic_logic.translate.subjects import prompt_profile_text, resolve_profile

from .conftest import chain_problem, make_claim


def request(**over) -> TranslationRequest:
    claim = make_claim(supporting_claim_ids=["c-ev"])
    data = dict(claim=claim, eligibility=decide_eligibility(claim), prompt_version="translate_v1", ir_version="1.0")
    data.update(over)
    return TranslationRequest(**data)


def test_subject_profile_block_is_optional():
    without = render_translation_user_prompt(request())
    assert "<<<DATA subject_profile>>>" not in without and "<<<DATA claim>>>" in without and "<<<END claim>>>" in without
    text = prompt_profile_text(resolve_profile("History"))
    with_profile = render_translation_user_prompt(request(subject_profile_text=text))
    assert "<<<DATA subject_profile>>>" in with_profile and "<<<END subject_profile>>>" in with_profile
    assert "History" in with_profile and "Encode only within that scope" in with_profile


def test_prior_diagnostics_block_only_on_retry():
    first = render_translation_user_prompt(request())
    retry = render_translation_user_prompt(request(prior_diagnostics=["E102: sort mismatch at premises[0].expr"]))
    assert "<<<DATA prior_diagnostics>>>" not in first and "<<<DATA prior_diagnostics>>>" in retry
    assert "do not change the meaning of the claim" in retry


def test_rendering_is_deterministic_and_ends_with_output_instruction():
    a, b = render_translation_user_prompt(request()), render_translation_user_prompt(request())
    assert a == b and a.rstrip().endswith("Return exactly one JSON object and nothing else.")


def test_review_prompt_blocks():
    claim = make_claim(supporting_claim_ids=["c-ev"])
    req = ReviewRequest(claim=claim, problem=Problem.model_validate(chain_problem()), interpretation=Interpretation(reading="r"))
    text = render_review_user_prompt(req)
    for label in ("claim", "problem", "interpretation"):
        assert f"<<<DATA {label}>>>" in text and f"<<<END {label}>>>" in text
    assert text.endswith("Return exactly one JSON object and nothing else.")
