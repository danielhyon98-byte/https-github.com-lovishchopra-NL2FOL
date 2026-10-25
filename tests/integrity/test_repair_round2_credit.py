"""Repair round 2 (combinator-faults-5 variant): verbs of showing and stressing ("shows", "indicates", "demonstrates",
"highlights") credit a quotation to their subject like verbs of saying, so a colleague's words presented as a table's or an
article's are a misattributed quotation (INT-LEDGER-025's reader). Controls: the words the credited text holds, and a
quotation credited in another clause."""
from __future__ import annotations

import pytest

from epinoic_logic.integrity.ledger import misattributed_quotations
from epinoic_logic.translate.contracts import SuppliedText

TABLE = SuppliedText(document_id="doc-tab", title="Table 2: household waste (supplied table)", author=None,
                     text="Table 2: household waste (kg per week). 2019: 12.1. 2023: 9.8.")
ARTICLE = SuppliedText(document_id="doc-art", title="Article: the cost of waste", author=None, text="Councils spend more each year on collection.")
REPORT = SuppliedText(document_id="report:r2", title="Economics specialist report", author="economics-specialist",
                      text="In my view waste is a silent tax on every family, and councils pay it.")


@pytest.mark.parametrize("verb", ["shows", "indicates", "demonstrates", "illustrates", "highlights", "emphasises", "stresses", "says", "suggests"])
def test_a_colleagues_words_credited_to_the_table_by_any_crediting_verb_are_misattributed(verb):
    [d] = misattributed_quotations(f'The table {verb} that "waste is a silent tax on every family".', {TABLE.document_id: TABLE, REPORT.document_id: REPORT})
    assert f"The table {verb}" in d and "report r2" in d


def test_the_article_credited_with_a_colleagues_words_is_misattributed():
    [d] = misattributed_quotations('The article shows that "waste is a silent tax on every family".', {ARTICLE.document_id: ARTICLE, REPORT.document_id: REPORT})
    assert "doc-art" in d


@pytest.mark.parametrize("text", [
    'The table shows that "household waste" fell.',                                                     # the table holds the words
    'The article shows that "Councils spend more each year".',                                          # the article holds them
    'The table shows a fall, and the economist calls waste "a silent tax on every family".',            # credited in another clause
])
def test_words_the_credited_text_holds_or_credited_elsewhere_are_not_misattributed(text):
    docs = {d.document_id: d for d in (TABLE, ARTICLE, REPORT)}
    assert misattributed_quotations(text, docs) == []
