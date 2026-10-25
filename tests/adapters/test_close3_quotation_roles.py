"""Close round 3, INV-QR-1: repair round 5 (ADV5-08) read a span right after a reporting verb under a negation as a mention,
with one word allowed between the negation and the verb, so 'not only writes "..."', 'does not just say "..."' and 'not
only says "..."', which affirm the attribution, were read as "the text does not say this" and the span was never checked:
an invented quotation put after them passed as the source's words. The mention frames of ADV5-08 had been narrowed by close
round 1, so under the round's convergence rule that reading is reverted for its whole class: a span right after a negated
reporting verb is an attribution and is checked, as on the committed base. A negated report with words between the verb
and the span ('It does not say that the plan has "failed"', 'never calls it "a success"') keeps its mention, as before
repair round 5. Given up: a word the writer says the text never uses, written right after the verb ('never once says "I
love you"'), is checked again and can be named on correct work, as on the base.

Each positive case was checked to fail on the tree before the round; the wording is this round's own."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import find_quotation_spans, quotation_role, quotation_task

from ..evidence_support import deliver
from .test_repair_round4_quotations import _codes, _poem_case

_INVENTED = {"INT-REQ-003", "ES-SRC-001", "INT-LEDGER-025"}
_OPENING = 'The poet presents the willows as wise: they are "patient", and they "read what the slow water writes". '


def _roles(text: str, task: str = "analytical_paragraph") -> list[tuple[str, str]]:
    with quotation_task(task):
        return [(inner, quotation_role(text, s, e)) for s, e, inner in find_quotation_spans(text)]


@pytest.mark.parametrize("text, span", [
    ('The poet not only writes "the river sings at dusk" but lets the dark come in.', "the river sings at dusk"),
    ('The poet not only writes "sings" but lets the dark come in.', "sings"),
    ('The speaker does not just say "the willows weep"; the image shows it.', "the willows weep"),
    ('The poem not only says "the water is wise" but proves it.', "the water is wise"),
    ('The poet never once says "farewell", yet the parting is clear.', "farewell"),
    ('The poet does not write "splashed"; the verb is quiet.', "splashed"),
])
def test_a_span_right_after_a_negated_reporting_verb_is_a_quotation(text, span):
    assert _roles(text) == [(span, "quotation")]


@pytest.mark.parametrize("sentence, word", [
    ('The poet not only writes "the river sings at dusk" but also lets the dark come in.', "sings"),
    ('The speaker does not just say "the willows weep"; the image shows it.', "weep"),
    ('The poem not only says "the water is wise" but proves it.', "wise"),
])
def test_an_invented_quotation_after_an_affirming_negation_is_checked_and_named(sentence, word):
    _case, rc = deliver(_poem_case(_OPENING + sentence), "text")
    named = [f for f in [*rc.findings, *rc.structural_findings] if f.code in _INVENTED and word in f.message]
    assert named, sorted(_codes(rc))


@pytest.mark.parametrize("text, expected", [
    ('It does not say that the plan has "failed".', [("failed", "mention")]),
    ('The source never calls it "a success".', [("a success", "mention")]),
    ('The poet never uses "roared"; the water stays quiet.', [("roared", "mention")]),
])
def test_control_a_negated_report_with_words_before_the_span_keeps_its_mention(text, expected):
    assert _roles(text) == expected


def test_control_a_genuine_quotation_after_an_affirming_negation_raises_no_invented_quotation():
    _case, rc = deliver(_poem_case(_OPENING + 'The poet not only writes "the patient willows bend" but lets the dark come in.'), "text")
    assert not (_INVENTED & _codes(rc)), sorted(_codes(rc))
