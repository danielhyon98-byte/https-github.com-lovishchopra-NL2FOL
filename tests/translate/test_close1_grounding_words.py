"""Close round 1, two readings of a quotation premise's excerpt (arena r2 en-t4, r6 en-t11 and run1 ec-e1):

* the placeholder rule of repair round 5 (ADV5-02) refuted an excerpt with no content word ("it was the", "she") even when
  the premise is about those very words ('the repeated formula "it was the" structures the opening', "the narrator uses
  she for her mother"). A literal that quotes the excerpt's words, or names them right after a word of naming, is about
  them: no placeholder. An excerpt of function words cited for a fact about something else is still refuted.
* the subject reading of repair round 5 refuted an excerpt's figure as another quantity's when the record states the
  premise's quantity elsewhere with the same figure (a table cell "Average price per kilo | $2.40") or states a figure for
  the opposite part ("After the levy (June)" for a premise about the price before it). Neither is another figure for the
  premise's quantity now; a record that gives the premise's quantity a different figure still refutes the excerpt.

Wording of this round's own."""
from __future__ import annotations

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.grounding import check_problem_grounding

NOVEL = SuppliedText(document_id="novel", title="Chapter One", text=(
    "It was the coldest winter in memory, it was the year the river froze. She said nothing; I watched her hands."))


def _literal(meaning: str, excerpt: str, doc: SuppliedText = NOVEL):
    problem = Problem.model_validate({
        "request_id": "r", "claim_id": "c", "problem_id": "p", "query": "entailment",
        "symbols": [{"name": "w", "sort": "Bool", "meaning": meaning}, {"name": "z", "sort": "Bool", "meaning": "the opening feels bleak"}],
        "premises": [{"id": "Q", "expr": {"op": "var", "name": "w"}, "label": meaning,
                      "grounding": {"kind": "quotation", "source_refs": [{"document_id": doc.document_id, "excerpt": excerpt}]}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "z"}, "label": "the opening feels bleak"}})
    grounded, checks = check_problem_grounding(problem, [doc])
    return grounded.premises[0].grounding.verified, [c for c in checks if c.target_id == "Q"]


@pytest.mark.parametrize("meaning, excerpt", [
    ('the repeated formula "it was the" builds the opening', "it was the"),
    ("the narrator uses she for her mother", "She"),
    ("the narrator uses I for herself", "I"),
    ('the word "her" recurs in the second sentence', "her"),
])
def test_an_excerpt_of_the_words_the_premise_analyses_is_no_placeholder(meaning, excerpt):
    verified, checks = _literal(meaning, excerpt)
    assert verified is True and not [c for c in checks if c.verified is False]


@pytest.mark.parametrize("meaning, excerpt", [
    ("the river froze in the coldest winter in memory", "it was the"),
    ("the narrator's mother is silent", "She"),
    ("the narrator used the frozen river as a road", "the"),     # a verb of use names only a pronoun: "used the river" names no word
])
def test_control_an_excerpt_of_function_words_cited_for_a_fact_is_still_a_placeholder(meaning, excerpt):
    verified, checks = _literal(meaning, excerpt)
    assert verified is False and any("placeholder" in (c.detail or "") for c in checks)


LEVY = SuppliedText(document_id="levy", title="Extract", text=(
    "Before the levy, a kilo of white sugar sold for $2.40 on average and shoppers bought 30 tonnes a week.\n\n"
    "Indicator | Before the levy (May) | After the levy (June)\n"
    "Average price per kilo | $2.40 | $2.90\n"
    "Weekly sales | 30 tonnes | 26 tonnes"))


def _price(value: str, excerpt: str, doc: SuppliedText = LEVY):
    problem = Problem.model_validate({
        "request_id": "r", "claim_id": "c", "problem_id": "p", "query": "entailment",
        "symbols": [{"name": "p0", "sort": "Real", "meaning": "average price per kilo before the levy, $ (May)"}],
        "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": "p0"}, "right": {"op": "real", "value": value}},
                      "label": f"the average price before the levy was ${value} a kilo",
                      "grounding": {"kind": "quotation", "source_refs": [{"document_id": doc.document_id, "excerpt": excerpt}]}}],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "p0"}, "right": {"op": "real", "value": "1"}}}})
    grounded, checks = check_problem_grounding(problem, [doc])
    return grounded.premises[0].grounding.verified, [c for c in checks if c.target_id == "P"]


def test_a_figure_the_record_also_tabulates_for_the_same_quantity_grounds_the_premise():
    verified, checks = _price("2.40", "a kilo of white sugar sold for $2.40 on average")
    assert verified is True and not [c for c in checks if c.verified is False]


def test_a_figure_the_record_states_for_the_opposite_part_is_not_the_premises_quantity():
    after_only = SuppliedText(document_id="levy", title="Extract", text=(
        "Before the levy, a kilo of white sugar sold for $2.40 on average in the corner shops.\n\n"
        "Indicator | After the levy (June)\n"
        "Average price per kilo | $2.90"))
    verified, checks = _price("2.40", "a kilo of white sugar sold for $2.40 on average", after_only)
    assert verified is True and not [c for c in checks if c.verified is False]


