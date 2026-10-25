"""Round-7 hand-off from the parsers (r7 english/history handoffs 3-4, major): a paragraph opened by a bare note lead is
left out of the word and paragraph bounds as a whole.

The parsers role every sentence of a paragraph whose first sentence opens with a bare note lead ("Note:", "N.B.",
"Next step:", "Limit:", "Caveat:"; ``adapters.markdown.opens_note_paragraph``) as a note, never material. The channel's
bounds still counted the paragraph's later sentences as answer words and the paragraph as a paragraph, so a short
answer with such a note was charged words and a paragraph the parsers say it never wrote. The bounds now leave out the
whole paragraph, its words counted as notes. "Note on ...:" and "Confidence:" open a note sentence only, and a note lead
inside a paragraph changes nothing."""
from __future__ import annotations

import pytest

from epinoic_logic.channel import request_parser as rp

B = "The Wall was built in 1961 to stop emigration. It closed the border overnight."


@pytest.mark.parametrize("tail", [
    "\n\nNote: the totals for 1953 and 1961 come from a textbook table I could not check. Departures rose from about 144,000 in 1959 to about 200,000 in 1960.",
    "\n\nLimit: no approved source here confirms the exact total. The figure is given as millions.",
    "\n\nCaveat: both figures are rounded. Output rose from 2 to 3 million.",
    "\n\nN.B. both figures are rounded. Output rose from 2 to 3 million.",
], ids=["note", "limit", "caveat", "nb"])
def test_a_paragraph_opened_by_a_bare_note_lead_counts_for_no_answer_word_and_no_paragraph(tail):
    assert rp.count_answer_words(B) == (14, 0) and rp.count_paragraphs(B) == 1
    answer, notes = rp.count_answer_words(B + tail)
    assert answer == 14 and notes == rp.count_words(tail.strip())
    assert rp.count_paragraphs(B + tail) == 1
    assert rp.measure_answer_words(B + tail)[0] == 14


def test_control_content_stays_content():
    # a note sentence opened by "Note on ...:" leaves the rest of its paragraph as content
    assert rp.count_answer_words(B + "\n\nNote on the method: the model assumes constant growth. Output rose from 2 to 3 million.")[0] > 14
    assert rp.count_paragraphs(B + "\n\nNote on the method: the model assumes constant growth. Output rose from 2 to 3 million.") == 2
    # "Limitation:" opens an evaluation point (Psychology, Economics), never a note
    assert rp.count_answer_words(B + "\n\nLimitation: the sample was 30 students, so the findings may not generalise.")[0] > 14
    # "Confidence:" is a note sentence, not a note paragraph
    assert rp.count_answer_words(B + "\n\nConfidence: high. Output rose from 2 to 3 million.")[0] > 14
    # no lead: "Note that ..." is prose, and a lead inside a paragraph opens no note paragraph
    assert rp.count_paragraphs(B + "\n\nNote that the Wall closed the border overnight.") == 2
    assert rp.count_answer_words(B + "\n\nThe totals are rounded. Note: both come from a table.")[0] > 14
