"""The translation prompt ``translate_v3``: ``translate_v2`` plus the ten rules that mark the writer's own links for the
argument diagnosis. It is packaged, in use and bound into every translation; the earlier prompts stay packaged byte for
byte, so a recorded ``prompt_version`` always names the exact instructions it was produced with."""
from __future__ import annotations

import hashlib
import re

import pytest

from epinoic_logic.translate import prompts
from epinoic_logic.translate.subjects import ARGUMENT_MARKING_GUIDANCE, PROFILES, STEM_ENCODING_GUIDANCE, STEM_PROFILE_KEYS, prompt_profile_text

from ..contract.helpers import make_report, output, run_claim, speed_problem

V1_SHA256 = "02c40eaf48709c838359763725fd2ac4c931e2e9b52272020565d198a9cc469b"
V2_SHA256 = "5fc96b9c2ac0bd1137a5562a0c94ea44c9e1a44c2632cf58184e6cbccdc7ba93"
REVIEW_V2_SHA256 = "ff929b606e8d70beb3e70b42e54cda8900ce85de815883a75df3eb9bddbc66ed"


def _sha(name: str) -> str:
    return hashlib.sha256(prompts.load_prompt(name).encode("utf-8")).hexdigest()


def test_v3_is_packaged_and_in_use_and_the_earlier_prompts_are_byte_identical():
    assert prompts.TRANSLATE_PROMPT_VERSION == "translate_v3" and prompts.REVIEW_PROMPT_VERSION == "review_v2"
    assert prompts.load_prompt("translate_v3").startswith("# Epinoic logic translator — system instructions (translate_v3)\n")
    assert _sha("translate_v1") == V1_SHA256 and _sha("translate_v2") == V2_SHA256 and _sha("review_v2") == REVIEW_V2_SHA256


def test_v3_is_v2_with_the_marking_section_added():
    v2 = prompts.load_prompt("translate_v2").split("\n")
    v3 = prompts.load_prompt("translate_v3").split("\n")
    assert v2[0].endswith("(translate_v2)") and v3[0].endswith("(translate_v3)")
    heading = v3.index("## Marking the writer's links (translate_v3)")
    added = len(v3) - len(v2)
    at = heading - 1                                                        # the blank line that opens the section
    assert v3[at] == "" and added > 30
    assert v3[1:at] == v2[1:at]                                             # every line of v2 before the new section, unchanged
    assert v3[at + added:] == v2[at:]                                       # and every line after it


def test_the_version_is_bound_into_every_translation():
    claim, report = make_report("The speed is 15 km/h.")
    out = run_claim(claim, report, output(speed_problem()))
    assert out.translation.provider.prompt_version == "translate_v3"


#: One phrase per marking rule (A.8.3 of the design): the project's own wording.
RULES = {
    1: ('grounding kind "specialist_inference"', '"link: <the connective exactly as written>"', "quotes the writer's own words for the step"),
    2: ('kind\n   "general_knowledge" and the note "rule"',),
    3: ("carries that source's kind and\n   the exact excerpt",),
    4: ("Never add a step the writer did not state",),
    5: ("One proposition, one symbol.",),
    6: ("One word used in two senses gets two symbols", 'code "EQUIVOCATION"'),
    7: ('Keep scope words ("all", "every", "each", "some", "most", "never", "always")', "An instance fact keeps its instance"),
    8: ("Link every conjunct of the conclusion to the claim's stated reasons",),
    9: ('"document_id" set to the supplied text, or to "task"',),
    10: ('premise of kind "assumption"', 'Never write "verified" anywhere: only code sets it.'),
}


@pytest.mark.parametrize("number", sorted(RULES))
def test_the_ten_marking_rules_are_present(number):
    section = prompts.load_prompt("translate_v3").split("## Marking the writer's links (translate_v3)", 1)[1]
    assert re.search(rf"(?m)^ {{0,1}}{number}\. ", section), number
    flat = " ".join(section.split())                                         # the prompt wraps its lines
    for phrase in RULES[number]:
        assert " ".join(phrase.split()) in flat, (number, phrase)


def test_the_marking_section_names_no_provider_session_path_or_other_project():
    section = prompts.load_prompt("translate_v3").split("## Marking the writer's links (translate_v3)", 1)[1].casefold()
    for word in ("anthropic", "openai", "nl2fol", "session", "/tmp", "/home", "scratch"):
        assert word not in section, word


def test_argued_profiles_carry_the_marking_guidance_and_stem_profiles_do_not():
    for key, profile in PROFILES.items():
        text = prompt_profile_text(profile)
        if key in STEM_PROFILE_KEYS:
            assert text.endswith(STEM_ENCODING_GUIDANCE) and ARGUMENT_MARKING_GUIDANCE not in text
        else:
            assert text.endswith(ARGUMENT_MARKING_GUIDANCE) and STEM_ENCODING_GUIDANCE not in text
    for phrase in ("scope words", "causal verbs", "led to", "keep an instance fact's instance", "'link: <the connective as written>'"):
        assert phrase in ARGUMENT_MARKING_GUIDANCE


@pytest.mark.parametrize("name", ["translate_v3\n", "translate_v3 ", "../translate_v3", "Translate_v3", "", "x" * 65])
def test_a_prompt_name_is_matched_whole(name):
    with pytest.raises(ValueError):
        prompts.load_prompt(name)
