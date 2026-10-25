"""Close round 1, arena r1 hi-t1 synthesis (INT-LEDGER-023): repair round 5 read a figure whose words before it copy the
statement of a figure the source gives earlier as a swap of the two, so a summary that skips an intermediate figure ("from
4.1 per cent ... in 2015 to 22.6 per cent and 64 seats in 2023", when the source lists 11.8 per cent in 2019 between them)
was charged a changed figure. A figure whose words after it, to the end of its clause, are a source's own statement of that
same figure (with a figure or a date of that statement among them) keeps its own words: no swap. A swap of two parallel
statements' figures is still a change. Wording of this round's own."""
from __future__ import annotations

from epinoic_logic.integrity.ledger import aligned_differences, context_swaps

SOURCE = ("Support for the Reform League rose steadily: from 4.1 per cent and three seats in June 2015, to 11.8 per cent and 31 seats "
          "in May 2019, and to 22.6 per cent and 64 seats in July 2023, when it became the second party.")


def test_a_summary_that_skips_an_intermediate_figure_is_no_swap():
    synthesis = ("Support for the Reform League rose from 4.1 per cent and three seats in June 2015 to 22.6 per cent and 64 seats in "
                 "July 2023, a steep climb.")
    assert context_swaps(synthesis, [SOURCE]) == []
    figures, _meaning = aligned_differences(synthesis, [SOURCE])
    assert not [f for f in figures if "put in place of" in f]


def test_control_a_figure_put_in_another_statements_words_is_still_a_swap():
    # 22.6 in the words that state the May 2019 figure, with that statement's own seats and date after it
    synthesis = "Support for the Reform League rose from 4.1 per cent and three seats in June 2015, to 22.6 per cent and 31 seats in May 2019."
    assert any("22.6" in d and "11.8" in d for d, _tail in context_swaps(synthesis, [SOURCE]))


def test_control_parallel_statements_with_their_figures_exchanged_are_still_changes():
    source = ["In 2019 the mean wage in the north rose by 2.4 per cent, while in 2022 the mean wage in the north rose by 5.1 per cent."]
    synthesis = "In 2019 the mean wage in the north rose by 5.1 per cent, while in 2022 the mean wage in the north rose by 2.4 per cent."
    assert len(context_swaps(synthesis, source)) == 2
