"""The fifth repair of the translator merge, finding (d) of the re-test: pack 1.3's D30 said the STEM translator "follows
fixed rules" and listed among them two that are only instructions to the model (``translate.subjects.
STEM_ENCODING_GUIDANCE``): one symbol per quantity named after its claim (``s2_1_g``), and stated values substituted for
the symbols. No code checks either, so an agent reading D30 would expect every STEM translation to follow them and could
accuse one that does not.

The corrected pack says what the code ENFORCES as holding for every translation (a numeral is an exact integer, fraction
or decimal with no exponent; the IR has no operator for a square root, a power or a trigonometric function), and every
other part of the guidance as what the translator IS TOLD, with no fault for departing from it alone. These tests pin the
pack beside the code and the guidance, so the three cannot drift.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from epinoic_logic.ir.schema import ALLOWED_OPS, IntConst, RealConst
from epinoic_logic.overseer.pack import installed_pack_dir
from epinoic_logic.translate.subjects import STEM_ENCODING_GUIDANCE

#: Sentences of pack 1.3 before the fifth repair that present the STEM translator's instructions as rules every
#: translation follows. None may come back.
STEM_INSTRUCTIONS_AS_RULES = (
    "For these subjects the translator follows fixed rules",
    "each quantity has one symbol, named after its claim",
    "the values the answer states are put in place of the symbols they bind",
    "A STEM translation writes every number exactly",
    "A line of working is encoded with the stated values put in place of its symbols",
    "that is the translator's rule, not a fault",
    "The translator records a unit as an assumption",
)
#: What the corrected pack must say (file, words).
STEM_RULES = (
    ("02-dossier.md", "Two things hold for every translation, because the code enforces them"),
    ("02-dossier.md", "These are instructions to the model; no code checks them, so a translation may not follow them"),
    ("02-dossier.md", "to use one symbol per quantity, prefixed with the claim it comes from (g in claim s2.1 as s2_1_g)"),
    ("02-dossier.md", "to put the values the answer states in place of the symbols they bind"),
    ("02-dossier.md", "A translation that departs from these instructions is no fault for that alone"),
    ("03-inspection.md", "The translator is told to write every number of a STEM answer exactly"),
    ("03-inspection.md", "The translator is told to encode a line of working with the stated values put in place of its symbols"),
    ("03-inspection.md", "a symbol not prefixed with its claim, or a stated value left as a symbol"),
    ("master_prompt.txt", "No code checks these instructions, so a translation that departs from one is no fault for that alone"),
)
FILES = ("02-dossier.md", "03-inspection.md", "06-kinds-and-codes.md", "07-examples.md", "master_prompt.txt")


def _problems(d) -> list[str]:
    texts = {f: (d / f).read_text(encoding="utf-8") for f in FILES}
    out = [f"{f} still says {s!r}" for f, t in texts.items() for s in STEM_INSTRUCTIONS_AS_RULES if s in t]
    out += [f"{f} does not say {s!r}" for f, s in STEM_RULES if s not in texts[f]]
    d30 = texts["02-dossier.md"].split("**D30 ", 1)[1].split("\n- **D31", 1)[0]
    if "follows" in d30.split("For STEM subjects the translator is also told", 1)[0]:
        out.append("D30 says the translator follows something before it says what it is told")
    return out


def test_the_installed_pack_presents_the_stem_guidance_as_instructions_and_the_enforced_rules_as_rules():
    assert _problems(installed_pack_dir("1.3")) == []


@pytest.mark.parametrize("sentence", STEM_INSTRUCTIONS_AS_RULES)
def test_a_pack_that_presents_an_instruction_as_a_rule_again_is_refused(tmp_path, sentence):
    """Each refused sentence put back into a copy of the pack is found (the check is not vacuous)."""
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    target = d / "02-dossier.md"
    target.write_text(target.read_text(encoding="utf-8") + f"\n- {sentence}.\n", encoding="utf-8")
    assert any(sentence in why for why in _problems(d))


@pytest.mark.parametrize("name, words", STEM_RULES)
def test_a_pack_that_drops_a_stem_statement_is_refused(tmp_path, name, words):
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    text = (d / name).read_text(encoding="utf-8")
    assert words in text
    (d / name).write_text(text.replace(words, "(removed)"), encoding="utf-8")
    assert f"{name} does not say {words!r}" in _problems(d)


def test_what_d30_says_the_code_enforces_the_code_enforces():
    """D30's two enforced rules, held against the IR: a numeral is an exact integer, fraction or decimal with no exponent
    (6.67e-11 is refused, its exact decimal accepted), and no operator for a square root, a power or a trigonometric or
    exponential function exists."""
    for bad in ("6.67e-11", "3.0E8", "1e5", "6.67 × 10⁻¹¹", "0x10"):
        with pytest.raises(ValidationError):
            RealConst(op="real", value=bad)
        with pytest.raises(ValidationError):
            IntConst(op="int", value=bad)
    assert RealConst(op="real", value="0.0000000000667").value == "0.0000000000667"
    assert RealConst(op="real", value="-7/2").value == "-7/2" and IntConst(op="int", value="300000000").value == "300000000"
    assert not {"sqrt", "root", "pow", "power", "exp", "log", "ln", "sin", "cos", "tan", "abs"} & set(ALLOWED_OPS)


def test_what_d30_says_the_translator_is_told_is_the_translator_s_guidance_and_only_that():
    """Each instruction D30 lists is in the translator's guidance (model-facing text, :data:`STEM_ENCODING_GUIDANCE`), in
    the guidance's own terms, and the guidance is the only place they come from: no code checks the symbol prefix or the
    substitution (a translation whose symbols carry no claim prefix and whose values are left as symbols validates)."""
    g = STEM_ENCODING_GUIDANCE
    for words in ("write every numeral as an exact integer or decimal string with no exponent", "substitute the stated values for the symbols they bind",
                  "use one symbol per quantity and prefix it with the claim it comes from (s<claim>_v)", "record a unit as an assumption, never inside an expression",
                  "encode a square root or a trigonometric value as a squared comparison, or report UNSUPPORTED"):
        assert words in g, words
    from epinoic_logic.engine.validator import parse_and_validate
    import json
    free = {"problem_id": "p", "request_id": "req", "claim_id": "s2.1", "query": "entailment",
            "symbols": [{"name": "g", "sort": "Real", "meaning": "g"}, {"name": "m", "sort": "Real", "meaning": "the mass"}],
            "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": "g"}, "right": {"op": "div", "left": {"op": "var", "name": "m"},
                                                                                                          "right": {"op": "real", "value": "2"}}}}],
            "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "g"}, "right": {"op": "real", "value": "0"}}}}
    problem, diagnostics = parse_and_validate(json.dumps(free))
    assert problem is not None, diagnostics  # an unprefixed symbol and a value left as a symbol are valid IR: nothing enforces either
