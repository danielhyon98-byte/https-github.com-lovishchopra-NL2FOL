"""Repair round 3, the ledger's quotation credits and figure readings (rerun-combinator-faults-5 and -8 variants).

Credits: an organisation is named by its leading name words ("Northwind states", "Northwind Shipping writes", "Riverside
says") and by its kind ("the company admits", "the firm states", "the trust says"), and a document by its kind ("the
report says", "the document says", "the minutes record"): a specialist's prose presented in those words as the source's
is a misattributed quotation. A kind credits only the text that carries it (its title or its author), never another
text by default. Controls: the same credits of words the source does hold, and a kind no supplied text carries.

Figures: a figure grouped in thousands with a space, a thin space, a no-break space or a narrow no-break space ("12 500",
"1 250.75") is one figure, so a synthesis writing its source's 12500 that way states no new figure; a changed figure in
the same grouping is still one."""
from __future__ import annotations

import pytest

from epinoic_logic.integrity.ledger import _figure_differences, figure_changes, misattributed_quotations
from epinoic_logic.translate.contracts import SuppliedText as T

PROSE = "the firm is overtrading and cash will run out"
DOCS = {"doc-rep": T(document_id="doc-rep", title="Annual report (company document)", author="Northwind Shipping Ltd (a fictional firm)",
                     text="Revenue grew by 4 per cent. The board expects the firm to stay profitable."),
        "report:r2": T(document_id="report:r2", title=None, author="business-management-specialist", text=f"{PROSE}.")}
MINUTES = {"doc-m": T(document_id="doc-m", title="Minutes of the board meeting", author="Riverside Hospital Trust", text="Waiting times rose in March."),
           "report:r3": T(document_id="report:r3", title=None, author="economics-specialist", text="the trust is chronically underfunded")}


@pytest.mark.parametrize("credit", ["The company admits that", "The firm states that", "Northwind states that", "Northwind Shipping writes that",
                                    "The report says", "The document says"])
def test_a_specialists_prose_credited_to_the_organisation_or_its_document_is_misattributed(credit):
    [found] = misattributed_quotations(f'{credit} "{PROSE}".', DOCS)
    assert "doc-rep" in found and "business-management-specialist" in found


@pytest.mark.parametrize("credit", ["The minutes record that", "The trust says", "Riverside says", "The hospital trust admits that"])
def test_the_same_holds_for_a_trust_and_its_minutes(credit):
    assert misattributed_quotations(f'{credit} "the trust is chronically underfunded".', MINUTES)


@pytest.mark.parametrize("credit", ["The company states that", "Northwind writes that", "The report says"])
def test_words_the_source_does_hold_are_no_misattribution(credit):
    assert misattributed_quotations(f'{credit} "the firm to stay profitable".', DOCS) == []


def test_a_kind_no_supplied_text_carries_credits_no_text():
    poem = {"doc-p": T(document_id="doc-p", title="Dulce et Decorum Est (poem)", author="Wilfred Owen", text="Bent double, like old beggars under sacks"),
            "report:r4": T(document_id="report:r4", title=None, author="history-specialist", text="the war poets rejected heroic rhetoric")}
    assert misattributed_quotations('The company says "the war poets rejected heroic rhetoric".', poem) == []
    assert misattributed_quotations('The poem says "the war poets rejected heroic rhetoric".', poem)   # a literary kind still credits the poem


@pytest.mark.parametrize("written", ["12 500", "12 500", "12 500", "12 500", "12,500"])
def test_a_figure_grouped_in_thousands_is_one_figure(written):
    assert figure_changes(f"The town has {written} residents.", ["The town has 12500 residents."]).introduced == []


def test_a_decimal_grouped_in_thousands_is_one_figure_and_a_signed_one_too():
    assert figure_changes("The balance is 1 250.75 dollars.", ["The balance is 1250.75 dollars."]).introduced == []
    assert _figure_differences("The balance is −1 250.75 dollars.", ["The balance is -1250.75 dollars."]) == ([], [], [])


def test_a_changed_figure_in_the_same_grouping_is_still_introduced():
    assert figure_changes("The town has 12 500 residents.", ["The town has 12600 residents."]).introduced == ["12500"]


def test_a_year_and_a_count_stay_two_figures():
    assert figure_changes("In 2019 500 people came.", ["In 2019 500 people came."]).introduced == []
    assert figure_changes("In 2019 500 people came.", ["In 2019 400 people came."]).introduced == ["500"]
