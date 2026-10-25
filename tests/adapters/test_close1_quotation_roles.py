"""Close round 1, rerun-verify6-weakened-negated-quotation-mention: repair round 5 (ADV5-08) read any span of up to three
words after a negated verb as a mention ('The king does not "rule with mercy", as the chronicle claims'), so an invented or
altered span presented as the source's words was never checked. The negated-verb frame is now a mention only for one
quoted word, the ADV5-08 class ('the speaker is not "afraid"'), and a credit to a source right after a span (", as the
chronicle claims", "(as the poet puts it)") keeps it a quotation whatever frame stands before it. Wording of this round's
own; the positives were checked to fail on the tree before the round."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import find_quotation_spans, quotation_role, quotation_task

from ..evidence_support import deliver
from .test_repair_round4_quotations import _case, _codes, _poem_case


def _roles(text: str, task: str = "analytical_paragraph") -> list[tuple[str, str]]:
    with quotation_task(task):
        return [(inner, quotation_role(text, s, e)) for s, e, inner in find_quotation_spans(text)]


@pytest.mark.parametrize("text, expected", [
    ('The willows are not "bowed by grief" in this extract.', [("bowed by grief", "quotation")]),
    ('The river does not "keep its secrets", as the poem claims.', [("keep its secrets", "quotation")]),
    ('The water is not "restless", as the poet puts it.', [("restless", "quotation")]),
    ('The trees do not "bend" (as the poem says).', [("bend", "quotation")]),
])
def test_a_longer_span_after_a_negated_verb_or_a_credited_span_stays_a_quotation(text, expected):
    assert _roles(text) == expected


@pytest.mark.parametrize("text, expected", [
    ('The willows are not "angry" in this extract.', [("angry", "mention")]),       # one word after a negated verb (ADV5-08)
    ('The water does not "rush" at all.', [("rush", "mention")]),
])
def test_control_one_word_the_writer_says_the_text_lacks_stays_a_mention(text, expected):
    assert _roles(text) == expected


def test_one_word_after_a_negated_reporting_verb_is_a_quotation():
    """Rewritten stricter in close round 3 (INV-QR-1): this case was a control of the test above (a mention); a word right
    after a reporting verb under a negation is an attribution and is checked, as on the committed base, since the reading
    that made it a mention also read 'not only writes "..."' and 'does not just say "..."' as absences."""
    assert _roles('The poet never writes "roared", so the water stays quiet.') == [("roared", "quotation")]


_CHRONICLE = ("Annals of the Abbey (extract)\n\nThe duke governs with patience and keeps the roads safe. "
              "The merchants trust his word.")


def _chronicle_case(answer: str) -> dict:
    return _case("close1-annals", answer, subject="History", task_type="source_analysis", agent="history-specialist",
                 request="Analyse how the source presents the duke. Use quotations. [4 marks]",
                 texts=[{"document_id": "annals", "title": "Annals of the Abbey (extract)", "author": "a monk", "text": _CHRONICLE}])


def _span_findings(rc, span: str) -> list:
    """The findings that check a quoted span against the supplied texts and name it (not found, altered or uncredited)."""
    return [f for f in [*rc.findings, *rc.structural_findings] if f.code in ("INT-REQ-003", "CORE-SRC-003", "HI-SRC-001") and span in f.message]


def test_an_invented_span_after_a_negation_and_credited_to_the_source_is_checked_and_named():
    _case_, rc = deliver(_chronicle_case('The annals present a patient ruler. The duke does not "rule by terror", as the annals claim; '
                                         '"The merchants trust his word".'), "text")
    assert _span_findings(rc, "rule by terror")


def test_control_the_genuine_span_after_a_negation_raises_no_invented_quotation():
    _case_, rc = deliver(_chronicle_case('The annals present a respected ruler: the merchants do not "trust his word" lightly, and he '
                                         '"keeps the roads safe".'), "text")
    assert "INT-REQ-003" not in _codes(rc) and not _span_findings(rc, "trust his word")


def test_an_altered_span_after_a_negated_verb_in_an_analysis_is_named():
    _case_, rc = deliver(_poem_case('The willows are not "bowed by grief": they "read what the slow water writes", which suggests calm.'), "text")
    assert "INT-REQ-003" in _codes(rc)
