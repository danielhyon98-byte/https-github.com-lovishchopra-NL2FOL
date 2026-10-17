"""The figure and exactness reader stays linear in an untrusted text (integration of the 12 October 2026 review fixes).

The translation layer reads every figure of the claim, its supporting claims, the supplied texts and the task record
(``translate.quantities``) to decide stated precision, task authority and coverage. A supplied text is untrusted input of
up to 400,000 characters. As first integrated, four steps rescanned what they had already found, so their cost grew with
the square of the text: deduplicating cues (every cue against every earlier one), excluding the numerals of precision
cues (every numeral against every such cue), locating a figure's sentence (every sentence) and choosing the cue that
governs a figure (every cue of its sentence). Reading every figure of the 100,000-character texts below took 3.6 s to
107 s that way (351 s for one of them at 200,000 characters). They now look up an index (a coverage map, a bisection, the
cues near the figure) and take well under a second; the readings are the same (the tests below pin them), and the bound
is measured under the suite's timing conditions (``tests/timing.py``), never relaxed.
"""
from __future__ import annotations

import pytest

from epinoic_logic.translate import quantities as q
from epinoic_logic.translate.quantities import SourceText, figures_in, sentence_of, stated_exactness

from ..timing import measure

#: Pathological texts: one sentence (no capital after the full stops) holding thousands of figures and precision cues,
#: and one clause after another separated by commas, the shapes on which the earlier rescans were quadratic.
PATHOLOGICAL = {
    "one sentence of figures and cues": "x is 0.5 to 2 decimal places. ",
    "clauses joined by commas": "0.5, approximately, 0.5, about ",
    "cues packed around figures": "0.5 ≈ 0.5 ~ 0.5 about ",
    "exactness cues against rounding cues": "exactly rounded to 2 d.p. and 3 s.f.; ",
}


def _text(unit: str, n: int) -> str:
    return (unit * (n // len(unit) + 1))[:n]


@pytest.mark.parametrize("name", list(PATHOLOGICAL))
def test_reading_every_figure_of_a_long_untrusted_text_stays_linear(name):
    """100,000 characters: every figure read and every reading's exactness decided under 2 s (the earlier rescans took
    3.6 s to 107 s on these shapes). Measured as in tests/timing.py: a warm-up, then the median of five runs, each a first
    reading (the module's caches emptied) with the earlier heap frozen."""
    text = _text(PATHOLOGICAL[name], 100_000)

    def read_all():
        figures = figures_in(SourceText("supplied_text", "long", text))
        return len(figures), [stated_exactness(f, text).kind for f in figures]

    timing = measure(read_all, bound=2.0, label=name)
    assert timing.holds, timing
    count, kinds = timing.results[0]
    assert all(r == timing.results[0] for r in timing.results), "every run reads the same figures the same way"
    if name == "exactness cues against rounding cues":
        assert count <= 1  # the numerals of precision cues are no figures
    else:
        assert count > 3_000 and kinds and set(kinds) <= {"exact", "rounded", "unstated", "conflicting"}


def test_the_cue_nearest_the_figure_in_its_clause_decides_with_exactness_first_on_a_tie():
    text = "the share is about 5 exactly and then roughly 7, while 9 is given to 2 decimal places"
    figs = {f.numeral: f for f in figures_in(SourceText("claim", "c", text))}
    # 5: 'about' (one character before) and 'exactly' (one character after) are equally near; exactness wins the tie
    assert stated_exactness(figs["5"], text).kind == "exact"
    # 7: 'roughly' is nearest in its clause
    assert stated_exactness(figs["7"], text).kind == "rounded"
    # 9: its own clause states the precision
    nine = stated_exactness(figs["9"], text)
    assert nine.kind == "rounded" and nine.precision == "2 decimal places"


def test_a_cue_in_the_clause_next_to_a_figure_governs_it_across_the_comma():
    after = "x is 0.33, to 2 decimal places"
    before = "to 2 decimal places, x is 0.33"
    exact_after = "then x is 0.33, without rounding"
    for text, kind in ((after, "rounded"), (before, "rounded"), (exact_after, "exact")):
        [fig] = [f for f in figures_in(SourceText("claim", "c", text)) if f.numeral == "0.33"]
        assert stated_exactness(fig, text).kind == kind, text
    # a word between the comma and the cue breaks the adjacency: no cue governs the figure
    text = "x is 0.33, and y is to 2 decimal places"
    [fig] = [f for f in figures_in(SourceText("claim", "c", text)) if f.numeral == "0.33"]
    assert stated_exactness(fig, text).kind == "unstated"


def test_sentences_and_clauses_are_found_by_bisection_with_the_same_spans():
    text = "First, 3 rose. Second, 4 fell; then 5,000 stayed, roughly.\nLast 6."
    starts = q._sentence_starts(text)
    assert list(starts) == [a for a, _b in q._sentences(text)]
    for i in range(len(text)):
        a, b = sentence_of(text, i, i + 1)
        assert a <= i < max(b, i + 1)
        assert not any(a < s <= i for s in starts), "the sentence found is the last one starting at or before the position"
    five = text.index("5,000")
    sentence = sentence_of(text, five, five + 5)
    left, right = q._clause_of(text, sentence, five, five + 5)
    assert text[left:right].strip() == "then 5,000 stayed"  # the comma inside 5,000 splits nothing


def test_the_coverage_check_reads_each_sentence_once_however_many_figures_it_asserts():
    """The coverage check (``translate.coverage.asserting_spans``) looks for a source sentence that asserts a figure the
    encoding leaves open. It read the whole sentence again for every matching figure: on one 100,000-character sentence
    asserting 17 six thousand times it took 45 s. It now reads each sentence once (under 2 s, measured as in
    tests/timing.py), and every match is still listed with its span and the one reference to its sentence."""
    from fractions import Fraction

    from epinoic_logic.translate.coverage import asserting_spans

    text = "In 1960 seventeen states and 17 more and 17 again " * 2000
    timing = measure(lambda: asserting_spans(Fraction(17), None, [SourceText("supplied_text", "long", text)]), bound=2.0, label="asserting_spans")
    assert timing.holds, timing
    spans = timing.results[0]
    assert len(spans) == 6000 and len({(r.document_id, r.locator) for _t, r in spans}) == 1
    assert spans[0][0].startswith("supplied text long characters 8-17 ('seventeen') in 'In 1960 seventeen states")
    # a sentence that defines or supposes asserts nothing, however many figures it holds
    supposed = "Suppose that 17 states and 17 more " * 200
    assert asserting_spans(Fraction(17), None, [SourceText("supplied_text", "s", supposed)]) == []
