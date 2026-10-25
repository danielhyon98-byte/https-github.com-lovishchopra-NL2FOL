"""A quotation credited to a supplied text by the name its title gives or by the kind of text it is (repair round 1,
re-run review cf-5 variant; ``adapters.sources.quotation_credit``):

* a proper name in the title's parenthetical names the text ("The Northern Courier reports that ..." for "Plastic waste
  rising (newspaper article, The Northern Courier, 2021)"), with or without its article;
* a kind of text the title names, with up to three words before it ("the newspaper", "the bread price table"), names
  the one supplied text of that kind, so a specialist's words credited that way are a misattributed quotation.

Clean controls: the source's own words credited by those names are no misattribution; a kind before which a specialist
or a report stands credits the colleague, never the text; a parenthetical that is a year or a description gives no
name."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.sources import _title_parts, quotation_credit
from epinoic_logic.integrity.ledger import misattributed_quotations
from epinoic_logic.translate.contracts import SuppliedText

ARTICLE = SuppliedText(document_id="doc-art", title="Plastic waste rising (newspaper article, The Northern Courier, 2021)", author="J. Okafor (staff reporter)",
                       text="Plastic use rose by 8% last year, and councils warn that bins are overflowing.")
TABLE = SuppliedText(document_id="doc-bread", title="Price of a loaf of bread in Berlin, 1918-1923 (table from the student's History textbook)", author=None,
                     text="1918: 0.53 marks. 1922: 163 marks. 1923: 201,000,000,000 marks.")
PEER = SuppliedText(document_id="report:r3", title=None, author="ess-specialist", text="recycling cannot keep pace with production, and the model is not a good fit for 1923.")


def test_the_title_gives_names_and_kinds():
    names, kinds = _title_parts(ARTICLE)
    assert names == ["The Northern Courier", "Northern Courier"] and kinds == {"newspaper", "article"}
    names, kinds = _title_parts(TABLE)
    assert names == [] and kinds == {"table", "textbook"}
    assert _title_parts(SuppliedText(document_id="d", title="Digging (poem, supplied text)", author=None, text="x")) == ([], frozenset({"poem"}))
    assert _title_parts(SuppliedText(document_id="d", title="Notes (Supplied Text, 2021)", author=None, text="x"))[0] == []


@pytest.mark.parametrize("sentence", [
    'The Northern Courier reports that "recycling cannot keep pace with production".',
    'Northern Courier says "recycling cannot keep pace with production".',
    'The newspaper says "recycling cannot keep pace with production".',
])
def test_a_specialists_words_credited_by_the_title_name_or_kind_are_misattributed(sentence):
    docs = {"doc-art": ARTICLE, "report:r3": PEER}
    [found] = misattributed_quotations(sentence, docs)
    assert "doc-art" in found and "recycling cannot keep pace with production" in found


def test_a_kind_with_words_before_it_names_the_text_of_that_kind():
    docs = {"doc-bread": TABLE, "doc-art": ARTICLE, "report:r3": PEER}
    sentence = "The bread price table says that 'the model is not a good fit for 1923'."
    credit = quotation_credit(sentence, sentence.index("'"), docs)
    assert credit is not None and credit.document_id == "doc-bread" and credit.generic
    [found] = misattributed_quotations(sentence, docs)
    assert "doc-bread" in found


@pytest.mark.parametrize("sentence", [
    'The Northern Courier reports that "councils warn that bins are overflowing".',   # the article's own words
    'The newspaper says "Plastic use rose by 8% last year".',
])
def test_clean_control_the_texts_own_words_are_no_misattribution(sentence):
    assert misattributed_quotations(sentence, {"doc-art": ARTICLE, "report:r3": PEER}) == []


def test_clean_control_a_specialists_table_credits_the_colleague_not_the_text():
    docs = {"doc-bread": TABLE, "report:r3": PEER}
    sentence = "The History specialist's table says that 'the model is not a good fit for 1923'."
    credit = quotation_credit(sentence, sentence.index("'"), docs)
    assert credit is None or credit.document_id != "doc-bread"
    assert misattributed_quotations(sentence, docs) == []


def test_clean_control_two_texts_of_no_named_kind_still_resolve_to_no_document():
    other = SuppliedText(document_id="doc-other", title="Second source", author=None, text="Something else entirely.")
    docs = {"doc-art": ARTICLE, "doc-other": other}
    sentence = 'The passage says "something else entirely".'
    credit = quotation_credit(sentence, sentence.index('"'), docs)
    assert credit is not None and credit.document_id is None
