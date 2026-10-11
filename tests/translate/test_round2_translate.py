"""Grounding tiers and translation binding added after the round-2 arena: nested quotation
marks folded to one class, verse line breaks written as slashes, a long elision told apart
from an invented quotation, and a translation bound to the exact claim text it read."""
from __future__ import annotations

import pytest

from epinoic_logic.translate import Translator
from epinoic_logic.translate.contracts import SuppliedText, TranslationStatus, sha256_text
from epinoic_logic.translate.grounding import (
    NOTE_LINEBREAK_SLASH, NOTE_QUOTES_FOLDED, check_claim_sources, locate_long_elision, locate_quotation, locate_quotation_inexact,
)
from epinoic_logic.translate.outcome import compose_outcome
from epinoic_logic.translate.providers import FixtureTranslationProvider

from .conftest import chain_problem, make_claim, provider_output

POEM = ("I met a traveller from an antique land,\nWho said—“Two vast and trunkless legs of stone\nStand in the desert. . . . Near them, on the sand,\n"
        "Half sunk a shattered visage lies, whose frown,\nAnd wrinkled lip, and sneer of cold command,")


def test_nested_quotation_marks_are_folded_not_invented():
    m = locate_quotation("Who said—'Two vast and trunkless legs of stone'", POEM)
    assert m is not None and m.method == "normalized_match" and m.note == NOTE_QUOTES_FOLDED and POEM[m.start:m.end].startswith("Who said—“Two vast")
    assert locate_quotation("Who said—'Two vast and trunkless legs of iron'", POEM) is None  # a changed word is still a miss
    claim = make_claim("c-q", "q", "evidence", source_refs=[{"document_id": "doc-ozy", "excerpt": "Who said—'Two vast and trunkless legs of stone'"}])
    check = check_claim_sources(claim, [SuppliedText(document_id="doc-ozy", text=POEM)])[0]
    assert check.verified is True and "folded" in check.detail


def test_verse_line_breaks_written_as_slashes_match_the_document():
    m = locate_quotation("whose frown, / And wrinkled lip, and sneer of cold command", POEM)
    assert m is not None and m.note == NOTE_LINEBREAK_SLASH and "\n" in POEM[m.start:m.end]
    assert locate_quotation("whose / frown", POEM) is None  # a slash where the document has no line break is not a match
    assert locate_quotation_inexact("whose / frown", POEM) is not None  # but a form difference, never an invented quotation
    claim = make_claim("c-v", "q", "evidence", source_refs=[{"document_id": "doc-ozy", "excerpt": "whose frown, / And wrinkled lip, and sneer of cold command"}])
    check = check_claim_sources(claim, [SuppliedText(document_id="doc-ozy", text=POEM)])[0]
    assert check.verified is True and "line breaks" in check.detail


def test_long_elision_is_a_form_difference_naming_the_span():
    text = "The lamp stays unlit in the hall. " + "the clock ticks on and the yard stays grey. " * 20 + "Nothing moves outside."
    excerpt = "The lamp stays unlit ... Nothing moves outside"
    assert locate_quotation(excerpt, text) is None and locate_quotation_inexact(excerpt, text) is None
    far = locate_long_elision(excerpt, text)
    assert far is not None and far[0].elided and "elides about" in far[1] and "long elision" in far[1]
    assert locate_long_elision("The lamp stays unlit ... nothing moves inside", text) is None
    claim = make_claim("c-l", "q", "evidence", source_refs=[{"document_id": "doc-x", "excerpt": excerpt}])
    check = check_claim_sources(claim, [SuppliedText(document_id="doc-x", text=text)])[0]
    assert check.verified is False and "differs in form" in check.detail and "elides about" in check.detail


def test_translation_is_bound_to_the_claim_text(english_claims, english_report):
    provider = FixtureTranslationProvider({"c-point": provider_output(chain_problem())})
    result = Translator(provider).translate(english_claims["c-point"], english_report)
    assert result.status is TranslationStatus.TRANSLATED and result.claim_text_sha256 == sha256_text(english_claims["c-point"].claim_text)
    restated = make_claim("c-point", "The setting conveys neglect and decay.", "point", supporting_claim_ids=["c-ev", "c-link"])
    with pytest.raises(ValueError, match="different text"):
        compose_outcome(restated, result)
    assert compose_outcome(english_claims["c-point"], result).claim_id == "c-point"


def test_fixture_provider_refuses_a_stale_fixture_when_it_knows_the_text(english_claims, english_report):
    stale = FixtureTranslationProvider({"c-point": provider_output(chain_problem())}, claim_text_sha256={"c-point": sha256_text("The setting conveys neglect and decay.")})
    result = Translator(stale).translate(english_claims["c-point"], english_report)
    assert result.status is TranslationStatus.TRANSLATION_FAILED and any("stale fixture" in d for d in result.diagnostics)
    exact = FixtureTranslationProvider({"c-point": provider_output(chain_problem())}, claim_text_sha256={"c-point": sha256_text(english_claims["c-point"].claim_text)})
    assert Translator(exact).translate(english_claims["c-point"], english_report).status is TranslationStatus.TRANSLATED
    plain = FixtureTranslationProvider({"c-point": provider_output(chain_problem())})
    assert Translator(plain).translate(english_claims["c-point"], english_report).status is TranslationStatus.TRANSLATED
