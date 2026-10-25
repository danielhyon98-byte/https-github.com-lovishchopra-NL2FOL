"""Close round 3, DV2-06 (security): the synthesis ledger's figure readers cost more than three times the committed base's
time on hostile answers of 10,000 to 36,000 characters (digit groups spaced as thousands, "1 000 1 000 ..."; a chain of
unit figures, "25 mm / 50 µm = ..."). The causes were three readers that compare every figure with every other: the copied-
context swap reader (``context_swaps``) read again every place of the last copied word for every figure, the figure index
(``_FigureIndex.spelled``, ``carries``) listed every figure of a shared spelling for every figure, and the aligned reading
was made twice for one synthesized claim. Each is now linear in the two texts and gives the old answer: the places of
every run of four source tokens and of every source figure with the words after it are indexed once and extended one token
at a time on demand (``_RunPlaces``, which also reads once what follows every place of a run), a figure with fewer than two
content words before it is not read for a swap (no run before it could hold two), one reading is kept per sequence of
preceding tokens and per figure as written, and the aligned reading is kept per pair of texts. A differential check over
the 780 ledger inputs of every arena round and their swap and repetition variants gave no difference. The timing bounds
are on the readers the round made linear; the difflib alignment (``aligned_changes``) and the figure pairing are the
committed base's readers, at the base's cost, and are not timed here."""
from __future__ import annotations

import time

from epinoic_logic.integrity.ledger import aligned_differences, context_swaps, figure_changes


def _cpu(fn, *args) -> float:
    t = time.process_time()
    fn(*args)
    return time.process_time() - t


def _ledger_reading(syn: str, src: list[str]) -> None:
    """The readers the round made linear: the figure index (through ``figure_changes``) and the swap reader."""
    figure_changes(syn, src)
    context_swaps(syn, src)


def _digit_groups(chars: int) -> str:
    return ("The war began in 1914. " + "1 000 " * (chars // 6))[:chars]


def _unit_chain(chars: int) -> str:
    return ("The war began in 1914. " + "25 mm / 50 µm = " * (chars // 16))[:chars]


def _name(k: int) -> str:
    """A word of letters only, different for every ``k``."""
    out, k = "", k + 1
    while k:
        k, r = divmod(k - 1, 26)
        out = chr(97 + r) + out
    return "q" + out


def _statements(n: int, figure: str) -> str:
    """``n`` statements of the same copied words, each after a word of its own, so no two preceding sequences are the same."""
    return " ".join(f"In region {_name(k)} the price of bread rose by {figure} per cent." for k in range(n))


def test_digit_groups_and_unit_chains_are_read_in_linear_time():
    for make in (_digit_groups, _unit_chain):
        small, large = make(12_000), make(48_000)
        t_small = _cpu(_ledger_reading, small, [small])
        t_large = _cpu(_ledger_reading, large, [large])
        assert t_large < 3.0, (make.__name__, t_large)
        # four times the text costs well under the sixteen times a reading quadratic in it would
        assert t_large < 8 * max(t_small, 0.05), (make.__name__, t_small, t_large)


def test_copied_words_stated_in_many_places_are_read_in_linear_time_with_every_swap_named():
    # every synthesis statement copies one source statement word for word and puts 1.4, a figure the sources state
    # elsewhere, in place of its 3.2: each is a swap, however often the sources repeat the words before the figure
    def pair(n: int) -> tuple[str, list[str]]:
        return _statements(n, "1.4"), [_statements(n, "3.2") + " Later the price of milk rose by 1.4 per cent."]
    small, large = pair(500), pair(2_000)
    t_small = _cpu(context_swaps, *small)
    t_large = _cpu(context_swaps, *large)
    assert len(context_swaps(*small)) == 500 and len(context_swaps(*large)) == 2_000
    assert t_large < 4.0, t_large
    assert t_large < 8 * max(t_small, 0.05), (t_small, t_large)


def test_control_a_figure_spliced_into_another_statements_words_is_still_a_swap():
    source = "In 2019 the price of bread rose by 3.2 per cent, while in 2020 the price of bread rose by 1.4 per cent."
    synthesis = "In 2019 the price of bread rose by 1.4 per cent."
    swaps = context_swaps(synthesis, [source])
    assert len(swaps) == 1 and "'1.4'" in swaps[0][1] and "'3.2'" in swaps[0][1]


def test_control_the_same_statement_with_its_own_figure_is_no_swap():
    source = "In 2019 the price of bread rose by 3.2 per cent, while in 2020 the price of bread rose by 1.4 per cent."
    assert context_swaps("In 2020 the price of bread rose by 1.4 per cent.", [source]) == []


def test_control_copied_words_followed_once_by_the_synthesis_figure_are_no_swap():
    # one place of the copied words is followed by 1.4 itself: the words do not tie the figure to another statement
    source = " ".join(["The price of bread rose by 3.2 per cent."] * 8 + ["The price of bread rose by 1.4 per cent."])
    assert context_swaps("Again the price of bread rose by 1.4 per cent.", [source]) == []
    # control: when every place is followed by another figure, the swap is named
    source = " ".join(["The price of bread rose by 3.2 per cent."] * 8) + " Later the price of milk rose by 1.4 per cent."
    assert context_swaps("Again the price of bread rose by 1.4 per cent.", [source])


def test_control_a_dropped_and_a_changed_figure_are_still_named():
    changes = figure_changes("Sales were 4,000 units in 2021.", ["Sales were 3,500 units in 2021 and 4,100 units in 2022."])
    assert changes.introduced and changes.dropped


def test_the_aligned_reading_is_made_once_per_pair_of_texts():
    syn = "In 2019 the price of bread rose by 1.4 per cent."
    src = ["In 2019 the price of bread rose by 3.2 per cent, while in 2020 the price of bread rose by 1.4 per cent."]
    first = aligned_differences(syn, src)
    first[0].append("changed by a caller")
    again = aligned_differences(syn, src)
    assert "changed by a caller" not in again[0] and again == aligned_differences(syn, list(src))
