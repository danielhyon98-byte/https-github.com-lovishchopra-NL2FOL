"""Follow-up c3g, the channel fixer's ledger items (the c3f leftovers and the infected lens of the push check of 08c4a36b). Expected
values are fixed here.

1. ``ledger._spanish_word_figures`` (read by ``spanish_lexicon.spanish_number_figures``) read 'entre cuatrocientas y quinientas' as one
   figure, 900, because the run took 'y' as joining any two number words. In Spanish 'y' joins only the tens (from 'veinte' in the
   older spelling, 'treinta' to 'noventa') to a unit; two hundreds joined by 'y' are two figures.
2. ``ledger._self_report_sentences`` exempted a criterion or rubric sentence whole, so a self-report joined to it by a comma ('Evaluation
   rewards verified figures, and every figure was verified by the hub.') drew no INT-LEDGER-029. The exemption now covers the criterion
   and its relative clauses only; any other clause after its object is read as a sentence.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.integrity import ledger as L


@pytest.mark.parametrize("text, figures", [
    ("entre cuatrocientas y quinientas palabras", ["400", "500"]),
    ("La consigna pide entre doscientos y trescientos.", ["200", "300"]),
    ("sesenta y ochocientos", ["60", "800"]),
    ("treinta y treinta", ["30", "30"]),
    # 'y' after the tens joins a unit: one figure, as before
    ("dos mil trescientos cuarenta y cinco", ["2345"]),
    ("ciento treinta y cinco alumnos", ["135"]),
    ("noventa y nueve", ["99"]),
    ("cuarenta y uno", ["41"]),
    ("veinte y cinco", ["25"]),
    ("trescientos sesenta y cinco días", ["365"]),
    ("cincuenta y cinco mil", ["55000"]),
    ("más de cuatrocientas solicitudes", ["400"]),
    ("mil y una noches", ["1000"]),
])
def test_spanish_y_joins_only_tens_to_a_unit(text, figures):
    assert [v for _a, _b, v in L._spanish_word_figures(text)] == figures


def test_the_spanish_figure_reader_stays_linear():
    times = []
    for n in (2000, 8000):
        text = "; ".join(["cuatrocientas y quinientas, noventa y nueve"] * n)
        t = time.perf_counter()
        got = L._spanish_word_figures(text)
        times.append(time.perf_counter() - t)
        assert len(got) == 3 * n
    assert times[1] < 10.0 and times[1] < 8 * max(times[0], 0.02), times


@pytest.mark.parametrize("sentence, read", [
    # a self-report joined to a criterion sentence by a comma is read (was exempt whole)
    ("Evaluation rewards verified figures, and every figure was verified by the hub.", True),
    ("Criterion B requires checked data, all of it checked by two agents.", True),
    ("The rubric credits accuracy, and the engine confirmed every line.", True),
    # the criterion and its relative clauses stay free (the c3f pins, kept)
    ("Conclusion rewards an answer to the research question that follows from the analysis and its uncertainties, and that is compared "
     "with accepted science with sources cited.", False),
    ("Criterion B requires a method that is checked against a second source.", False),
    ("Criterion B requires checked data, which a second source has verified.", False),
    ("The mark scheme credits an answer that verifies its result, including a check by substitution.", False),
    ("Criterion B requires checked data.", False),
])
def test_a_clause_after_a_criterion_is_read_as_a_sentence(sentence, read):
    assert bool(L._self_report_sentences(sentence)) is read
