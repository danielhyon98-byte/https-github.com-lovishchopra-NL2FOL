"""Round-7 english/history handoffs 3-4 to the parsers' owner: note leads beyond the History parser.

The History parser reads 'Limit:' and 'Caveat:' as bare note leads and a caveat about the answer's own sources as a note; the shared
lead (``markdown.NOTE_LEAD_RE``, read by the English and generic parsers and by the channel's note clauses) had neither. A sentence opened
by 'Limit:' or 'Caveat:' is now a note on every branch; a paragraph a bare lead opens (``markdown.BARE_NOTE_LEAD_RE``,
``markdown.opens_note_paragraph``) is a note as a whole on the generic branch, as on the History branch; and the generic branch roles a
source caveat with no figure ('My sources do not confirm the exact total, ...') as a note. 'Limitation:' stays content on the shared
lead: it opens an evaluation point of a study or a model ('Limitation: the sample was 30 students'). The channel's word and paragraph
bounds (``channel.request_parser``, another owner's file) are handed off to read ``opens_note_paragraph``.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import BARE_NOTE_LEAD_RE, NOTE_LEAD_RE, is_note_sentence, opens_note_paragraph
from epinoic_logic.branches.generic_parser import GenericTextParser


@pytest.mark.parametrize("sentence", [
    "Limit: no approved source here confirms the 1950 figure.",
    "Limits: the textbook library was unavailable.",
    "Caveat: the totals are estimates.",
    "Caveats: both figures are rounded.",
    "Note: the totals come from a textbook table I could not check.",
])
def test_limit_and_caveat_are_note_leads(sentence):
    assert NOTE_LEAD_RE.match(sentence)
    assert is_note_sentence(sentence)


@pytest.mark.parametrize("sentence", [
    "Limitation: the sample was 30 students, so the findings may not generalise.",  # an evaluation point
    "Note that the Wall closed the border overnight.",                              # an argument's signpost
    "The limit of the model is its fixed price.",
    '"Limit: none," the poster said.',                                              # a quoted lead is the quoted text's
])
def test_content_is_not_a_note_lead(sentence):
    assert not NOTE_LEAD_RE.match(sentence) or sentence.startswith('"')
    assert not is_note_sentence(sentence)


@pytest.mark.parametrize("paragraph,expected", [
    ("Note: the totals for 1953 and 1961 come from a textbook table I could not check. Departures rose from about 144,000 in 1959.", True),
    ("Limit: no approved source here confirms the exact total. The figure is given as millions.", True),
    ("Caveat: both figures are rounded. Output rose from 2 to 3 million.", True),
    ("N.B. the dates are from memory. The Wall went up in 1961.", True),
    ("Note on the method: the model assumes constant growth.", False),   # introduces a discussion
    ("The Wall was built in 1961. It closed the border.", False),
])
def test_a_bare_note_lead_opens_a_note_paragraph(paragraph, expected):
    assert opens_note_paragraph(paragraph) is expected
    assert bool(BARE_NOTE_LEAD_RE.match(paragraph)) is expected


def _roles(text: str, subject: str = "Geography", agent: str = "geography-specialist") -> list[tuple[str, str, str]]:
    rep = GenericTextParser(agent_id=agent).parse_response(text, request_id="r", task_id="t", report_id="rep", subject=subject, task_type="short_answer")
    return [(c.claim_text, c.claim_role, c.materiality) for c in rep.claims]


def test_the_generic_branch_roles_a_caveat_paragraph_as_a_note_as_a_whole():
    body = "The birth rate fell from 31 to 11 per 1,000 between 1990 and 2020."
    roles = _roles(body + "\n\nCaveat: both rates are rounded. The 2020 figure is a provisional estimate of 11 per 1,000.")
    note = [r for r in roles if not r[0].startswith("The birth rate")]
    assert note and all(role == "other" and mat != "material" for _t, role, mat in note), note
    assert [r for r in roles if r[0].startswith("The birth rate")][0][1] != "other"


def test_the_generic_branch_roles_a_source_caveat_as_a_note():
    body = "The birth rate fell from 31 to 11 per 1,000 between 1990 and 2020."
    roles = _roles(body + " My sources do not confirm the exact 1990 rate, so treat it as approximate.")
    caveat = [r for r in roles if r[0].startswith("My sources")]
    assert caveat and caveat[0][1] == "other"
    roles_nf = _roles(body + " My sources do not confirm the exact emigration total, so the figure is given as 'millions'.")
    assert [r for r in roles_nf if r[0].startswith("My sources")][0][1] == "other"
    # a sentence that states a figure keeps its substance: the caveat reading never drops a figure
    roles2 = _roles(body + " My sources confirm a rate of 11 per 1,000 in 2020.")
    assert [r for r in roles2 if r[0].startswith("My sources")][0][1] != "other"
