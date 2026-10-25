"""Review round 8, quotation credit (combinator-faults-5, ``adapters.sources``): a specialist's own prose presented as a
supplied text's words is named when the sentence credits the text by its author's name, whatever description follows the
name in parentheses ("Kestrelford Borough Council (a fictional council)"), or by a non-literary kind ("the leaflet",
"the textbook", "the table", "according to the case study") when exactly one non-peer text was supplied. The text's own
words credited to it are no misattribution, and a word that only begins with a kind ("the post-war", "the textbooks'")
names no text. ("Shows" stays no crediting verb: a table that shows a trend is not quoted.)"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.sources import _names_of, quotation_credit
from epinoic_logic.integrity.ledger import misattributed_quotations
from epinoic_logic.translate.contracts import SuppliedText as T

OWN = "an abstract weight becomes a meal the reader can see"


def _docs(author: str = "Kestrelford Borough Council (a fictional council)", title: str = "Love it? (council leaflet, supplied text)") -> dict:
    return {"doc-leaflet": T(document_id="doc-leaflet", title=title, author=author, text="So why are you throwing away food? Plan your meals."),
            "report:r1": T(document_id="report:r1", title=None, author="english-a-lang-lit-specialist", text=f"Here {OWN}.")}


def test_a_parenthetical_description_is_no_part_of_the_authors_name():
    names = _names_of(_docs()["doc-leaflet"])
    assert "Kestrelford Borough Council" in names and "Council" in names
    assert not [n for n in names if "(" in n or ")" in n]


@pytest.mark.parametrize("sentence", [
    f'Kestrelford Borough Council writes that "{OWN}".',
    f'The leaflet says that "{OWN}".',
    f'The textbook states that "{OWN}".',
    f'According to the case study, "{OWN}".',
    f'The table says that "{OWN}".',
])
def test_the_specialists_prose_credited_to_the_supplied_text_is_named(sentence):
    found = misattributed_quotations(sentence, _docs())
    assert found and OWN[:40] in found[0]


def test_the_texts_own_words_credited_to_it_are_no_misattribution():
    assert misattributed_quotations('Kestrelford Borough Council asks "So why are you throwing away food?"', _docs()) == []
    assert misattributed_quotations('The leaflet asks "So why are you throwing away food?"', _docs()) == []


def test_a_word_that_only_begins_with_a_kind_names_no_text():
    text = f'In the post-war years, "{OWN}".'
    assert quotation_credit(text, text.index('"'), _docs()) is None
