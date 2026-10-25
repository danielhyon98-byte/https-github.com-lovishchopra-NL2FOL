"""E2E B19: one meta-text classifier (``request_parser.is_meta_text``) decides, for word and paragraph counts alike, which
blocks of an answer are notes about the answer rather than answer: a "Limit:" footer about the sources, a word count
("Word count: 249", "(249 words)"), a "Next step:" footer, a "Note:" block about the answer, and a closing one-line note
that addresses the reader about the answer. ll-e1's model paragraph ended with such a note, which was counted as a second
paragraph against "write ONE body paragraph" (a false INT-REQ-005)."""
from __future__ import annotations

import pytest

from epinoic_logic.channel.request_parser import count_paragraphs, is_meta_text, measure_answer_words

from ..argdiag_cases import load_case
from .dev_case_hub import run_case


@pytest.mark.parametrize("block, last", [
    ("Limit: no textbook library is available in this session, so the figures come only from the supplied text.", False),
    ("Word count: 249", False),
    ("(249 words)", False),
    ("Next step: write your own version from this plan.", False),
    ("Note: I used only the extract you pasted; the textbook was not available.", False),
    ("This model is written to the house standard: paste your own paragraph and I will give provisional marks.", True),
])
def test_meta_text_blocks_are_recognised(block, last):
    assert is_meta_text(block, last=last)


@pytest.mark.parametrize("block, last", [
    ("Limit: as x tends to 0, sin x / x tends to 1, so the gradient of sin at the origin is 1.", False),  # a mathematics heading
    ("In 2024 the population was 3.1 million, up from 2.4 million in 1990.", False),                    # figures, no word count
    ("The leaflet therefore moves its reader from guilt to a checklist.", True),                         # a closing sentence of the answer
    ("Paste the extract below.", False),                                                                 # a reader cue, but not the closing block
    ("Note: the poem's speaker is never named, which leaves the reader to take her place.", False),       # a note that states content
])
def test_answer_blocks_stay_answer(block, last):
    assert not is_meta_text(block, last=last)


def test_the_ll_note_is_not_a_paragraph():
    run = run_case("e2e-B19-ll")
    req = list(run.channel.requests.values())[-1]
    by_kind = {c.kind: c for c in req.constraints}
    res = {r.constraint_id: r for r in run.receipt.constraint_results}
    assert res[by_kind["max_paragraphs"].constraint_id].satisfied is True
    assert "measured 1 paragraphs" in res[by_kind["max_paragraphs"].constraint_id].detail
    assert not [f for f in run.receipt.findings if f.code == "INT-REQ-005"]
    answer = load_case("e2e-B19-ll")["answer"]
    assert count_paragraphs(answer) == 1
    words, notes, _ = measure_answer_words(answer)
    assert words == 249 and notes > 0                                   # the note's words are left out of the bound as well


def test_two_real_paragraphs_still_give_the_warning():
    case = load_case("e2e-B19-ll")
    first, rest = case["answer"].split(" The second strategy", 1)
    case["answer"] = first + "\n\nThe second strategy" + rest            # the model paragraph split in two
    run = run_case("e2e-B19-ll", case=case)
    req = list(run.channel.requests.values())[-1]
    cap = next(c for c in req.constraints if c.kind == "max_paragraphs")
    res = next(r for r in run.receipt.constraint_results if r.constraint_id == cap.constraint_id)
    assert res.satisfied is False and "measured 2 paragraphs" in res.detail
    assert [f for f in run.receipt.findings if f.code == "INT-REQ-005" and f.severity == "warning"]


def test_a_meta_label_that_states_content_is_counted():
    answer = "The model holds for small angles.\n\nLimit: as the angle grows, sin θ and θ part company, and the period lengthens."
    assert count_paragraphs(answer) == 2
