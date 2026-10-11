"""Grounding after the round-3 arena: a quotation spanning two stanzas written with ' / ' or
' // ' is found (a blank line renders as ' // ' and slash runs compare leniently), and the
shared excerpt check reports a long elision as its own located status instead of 'not found'."""
from __future__ import annotations

from epinoic_logic.adapters.sources import FOUND_STATUSES, check_excerpt
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.grounding import (
    NOTE_LINEBREAK_SLASH, _fold_slash_runs, _normalize_indexed, check_claim_sources, locate_quotation, locate_quotation_inexact,
)

from .conftest import make_claim

STANZAS = ("Half sunk a shattered visage lies, whose frown,\nAnd wrinkled lip, and sneer of cold command,\n\n"
           "Tell that its sculptor well those passions read\nWhich yet survive, stamped on these lifeless things,")


def test_a_blank_line_renders_as_a_double_mark_and_slash_runs_fold_to_one():
    rendered, idx = _normalize_indexed(STANZAS, newline_as_slash=True)
    assert "cold command, // Tell that" in rendered and "whose frown, / And wrinkled" in rendered and " / / " not in rendered
    folded, folded_idx = _fold_slash_runs(rendered, idx)
    assert "cold command, / Tell that" in folded and len(folded) == len(folded_idx) and folded_idx == sorted(folded_idx)
    assert _fold_slash_runs("a / / b")[0] == "a / b" and _fold_slash_runs("a // b")[0] == "a / b" and _fold_slash_runs("a / b")[0] == "a / b"


def test_a_quotation_across_a_stanza_break_is_found_with_one_or_two_marks():
    for excerpt in ("sneer of cold command, / Tell that its sculptor", "sneer of cold command, // Tell that its sculptor", "sneer of cold command, / / Tell that its sculptor"):
        m = locate_quotation(excerpt, STANZAS)
        assert m is not None and m.note == NOTE_LINEBREAK_SLASH and STANZAS[m.start:m.end] == "sneer of cold command,\n\nTell that its sculptor", excerpt
    within = locate_quotation("whose frown, // And wrinkled lip", STANZAS)  # two marks for a single line break: still the document's words
    assert within is not None and STANZAS[within.start:within.end] == "whose frown,\nAnd wrinkled lip"
    assert locate_quotation("whose / frown", STANZAS) is None and locate_quotation_inexact("whose / frown", STANZAS) is not None  # a mark where no break is: a form difference
    claim = make_claim("c-st", "q", "evidence", source_refs=[{"document_id": "doc-s", "excerpt": "sneer of cold command, / Tell that its sculptor"}])
    check = check_claim_sources(claim, [SuppliedText(document_id="doc-s", text=STANZAS)])[0]
    assert check.verified is True and "line breaks" in check.detail


def test_check_excerpt_reports_a_long_elision_as_located_and_not_ok():
    text = "The lamp stays unlit in the hall. " + "the clock ticks on and the yard stays grey. " * 20 + "Nothing moves outside."
    docs = {"d": SuppliedText(document_id="d", text=text)}
    far = check_excerpt("The lamp stays unlit ... Nothing moves outside", "d", docs)
    assert far.status == "found_long_elision" and far.located and not far.ok and "found_long_elision" in FOUND_STATUSES
    assert "elides about" in far.detail and "long elision, not an invented quotation" in far.detail and "characters 0-" in far.detail
    assert check_excerpt("The lamp stays unlit ... nothing moves inside", "d", docs).status == "not_found"  # a changed word is still a miss
    assert check_excerpt("The lamp ... hall", "d", docs).status == "found_elided"  # within the window: the existing status
