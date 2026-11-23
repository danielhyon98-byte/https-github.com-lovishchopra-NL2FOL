"""Push check of a9129c78 on the Geography and Language B branches (the c3f follow-up), each expected value fixed here.

A wrong figure is never ENTAILED and a correct one never a counterexample:

* Geography, the row of a derived figure (critical): a row is named only by the figure's own clause (or, when that clause has no
  subject of its own, by the sentence's subject) and by the row's distinctive head ('gas', 'coal', 'imported') or a distinctive
  modifier right before a word of the table ('natural gas', 'nuclear share', 'total supply'); never by a stop word ('share'), a
  function word, a modifier standing alone ('natural growth', 'nuclear capacity') or a row word inside an intervening clause (an
  apposition, a 'with', 'as', 'despite' or 'after' clause). Where no row is named a figure per person is the total's.
* Geography, the same reader stalled (a security item): it is now built once per sentence and each lookup is a few binary searches.
* Geography, a change 'by N%' of a share row: the relative change and the change in points disagree, so the figure is checked only
  under the reading its words fix ('percentage points', 'points', 'relative'); a figure that fits one reading is never shown checked.
* Geography, misses: a year written before the figure in its own clause, the total row's own cells, the sums of listed rows (amounts
  and shares), the totals of the request's labelled figures; false positives of a group figure and of a figure compared with a label.
* Language B, a dated figure (critical): a figure the answer dates matches only a supplied cell of that date; a cell of the text's
  present ('Hoy ...') is dated too; an answer's line with one year dates its figures.
* Language B, shares: fraction words, 'equivale a', 'corresponde a', 'del total de', the total first, the part in brackets or as an
  apposition, and rates ('dos de cada tres', 'one in every four'); their figures are no figures taken from the text.
* The core quant reader: a figure followed by 'and a half' is never read as its whole part.
* An own correction on ll-t16 ('Before: ... After: ...') draws no CORE-SRC-006 or INT-SUBJ-003 (the channel's own-text reader, which
  the core pack calls through ``sources.own_model_words``), while a misquotation of the source stays charged.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import time

import pytest

from . import d9d10_hub as H

_BASE: dict = {}


def _new(name: str, sentence: str):
    """(new error and warning codes, new non-entailed checks, new entailed checks) that ``sentence`` adds to the recorded answer."""
    if name not in _BASE:
        _BASE[name] = H.recorded(name)
    b = _BASE[name]
    rc = H.recorded(name, H.RECORDED[name][0] + "\n\n" + sentence)
    old = {(f.code, f.severity, f.message[:140]) for f in b.findings}
    new = [f.code for f in rc.findings if f.severity in ("error", "warning") and (f.code, f.severity, f.message[:140]) not in old]
    old_checks = H.checks(b)
    checks = [c for c in H.checks(rc) if c[1] != "ENTAILED" and c not in old_checks]
    entailed = [c for c in H.checks(rc) if c[1] == "ENTAILED" and c not in old_checks]
    return new, checks, entailed


PP = "Energy supply per person was about 38 GJ in 2005 and"
#: (record, faulty statement, its check family, finding code); each draws a COUNTEREXAMPLE of that family and no ENTAILED of it.
FAULTY = [
    ("c2/ge-t15", "Each person's share of energy supply was about 22.8 GJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", f"{PP}, with natural growth, about 9.3 GJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", f"{PP}, as nuclear capacity grew, about 1.7 GJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", f"{PP}, despite oil prices, about 11.4 GJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", f"{PP}, after coal declined, about 11.8 GJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", f"{PP} about 5.5 GJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "Energy supply per person, a share that grew, was about 22.8 GJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "Energy supply per person was about 38 GJ in 2005, and in 2025 it was about 5.5 GJ.", "geography-table-derived",
     "INT-SUBJ-004"),
    ("c2/ge-t15", "In 2025 energy supply per person was about 5.5 GJ and imports made up 54 % of supply.", "geography-table-derived",
     "INT-SUBJ-004"),
    ("c2/ge-t15", "Coal and oil together supplied 70 % of primary energy in 2005.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "Total primary energy supply rose from 820 PJ in 2005 to 1,500 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "The nuclear share rose by 2 percentage points, a relative rise of about 50%.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "Hydroelectric power and nuclear power supplied 41.0 PJ in 2005.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "Wind and solar power and nuclear power together made up 19% of supply in 2025.", "geography-table-derived",
     "INT-SUBJ-004"),
    ("c2/ge-t15", "Coal supply was 377.2 PJ in 2005 and 567.0 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "Imported energy was 311.6 PJ in 2005 and 294.0 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "Coal fell by a relative 50% from 2005 to 2025.", "geography-table-change", "INT-SUBJ-001"),
    ("c2/ge-t15", "The coal share fell by about 25% from 2005 to 2025.", "geography-table-change", "INT-SUBJ-001"),
    ("c2/ge-t15", "The coal share fell by about 39 percentage points from 2005 to 2025.", "geography-table-change", "INT-SUBJ-001"),
    ("c2/ge-p9c", "Together the two storms delivered 70 mm of rain.", "geography-request-figure", "INT-SUBJ-004"),
    ("c2/ge-p9c", "Storm 2's peak discharge was four times Storm 1's.", "geography-pair-comparison", "INT-SUBJ-001"),
    ("c1/sp-t14", "6. En 1960 la escuela tenía catorce alumnos.", "language-b-supplied-figure", "INT-SUBJ-001"),
    ("c1/sp-t14", "Valdeoca tenía dos panaderías y una escuela con más de catorce alumnos en 1960.", "language-b-supplied-figure",
     "INT-SUBJ-004"),
    ("c1/sp-t14", "En 2009 la escuela tenía catorce alumnos.", "language-b-supplied-figure", "INT-SUBJ-004"),
    ("c1/sp-t14", "En 1960 Valdeoca tenía 268 personas.", "language-b-supplied-figure", "INT-SUBJ-004"),
    ("c1/sp-t14", "En 2015 el ayuntamiento creó un espacio con doce puestos.", "language-b-supplied-figure", "INT-SUBJ-004"),
    ("c1/sp-t14", "Un 25 % de 80 equivale a 30.", "language-b-share", "INT-SUBJ-001"),
    ("c1/sp-t14", "Una cuarta parte de 80 son 30.", "language-b-share", "INT-SUBJ-001"),
    ("c1/sp-t14", "De los 80 alumnos, el 25 % (30 alumnos) estudia francés.", "language-b-share", "INT-SUBJ-001"),
    ("c1/sp-t14", "El 25 % del total de 80 alumnos corresponde a 30 alumnos.", "language-b-share", "INT-SUBJ-001"),
    ("c1/sp-t14", "Treinta alumnos, el 25 % de 80, estudian francés.", "language-b-share", "INT-SUBJ-001"),
    ("c1/sp-t14", "Veinte de cada ochenta, es decir el 30 %.", "language-b-share", "INT-SUBJ-001"),
    ("c1/sp-t14", "La mitad de los 80 alumnos, es decir 30, estudia francés.", "language-b-share", "INT-SUBJ-001"),
    ("c1/sp-t14", "Uno de cada cuatro alumnos, el 30 %, estudia francés.", "language-b-share", "INT-SUBJ-001"),
    ("c1/sp-t14", "A quarter of 80 is 30.", "language-b-share", "INT-SUBJ-001"),
    # c3e left: an attribute table's column changed between two rows, a share of one row named by its head, the answer's magnitudes
    ("c1/ge-t14", "Retail use fell by 82 percentage points along the transect.", "geography-supplied-figure", "INT-SUBJ-004"),
    ("c1/ge-t14", "Pedestrian counts fell by about 81% from Site 1 to Site 10.", "geography-supplied-figure", "INT-SUBJ-004"),
    ("c1/ge-t14", "The EQS fell by 11 points from Site 1 to Site 10.", "geography-supplied-figure", "INT-SUBJ-004"),
    ("c1/ge-t14", "Retail use fell by about 50% along the transect.", "geography-supplied-figure", "INT-SUBJ-004"),
    ("c2/ge-t15", "Imports made up 54% of supply in 2025, up from 36% in 2005.", "geography-table-derived", "INT-SUBJ-004"),
    ("c3/ge-t16", "The Haiti earthquake was 0.3 magnitude units weaker than Darfield.", "geography-event-relation", "INT-SUBJ-001"),
    ("c3/ge-t16", "The Christchurch aftershock was 1.9 magnitude units smaller than the Darfield earthquake.", "geography-event-relation",
     "INT-SUBJ-001"),    # c3e left: a task's word bound misstated in Spanish number words, with a qualifier before 'task', or as a cap the task 'allows'
    ("c2/sp-t15", "La consigna pide entre cuatrocientas y quinientas palabras.", "language-b-word-range-claim", "INT-SUBJ-001"),
    ("c3/sp-t16", "The SL task sets a range of 150 to 250 words.", "language-b-word-range-claim", "INT-SUBJ-004"),
    ("c3/sp-p10d", "The task allows at most 150 words.", "language-b-word-range-claim", "INT-SUBJ-001"),
]
#: (record, correct statement, the check family that must hold no counterexample for it, whether that family must be ENTAILED).
CORRECT = [
    ("c2/ge-t15", "Each person's share of energy supply was about 42 GJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", f"{PP}, with natural growth, about 42 GJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", f"{PP}, as nuclear capacity grew, about 42 GJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", f"{PP}, despite oil prices, about 42 GJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", f"{PP}, after coal declined, about 42 GJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", f"{PP} about 42 GJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", "Energy supply per person was about 38 GJ in 2005, and in 2025 it was about 42 GJ.", "geography-table-derived", True),
    ("c2/ge-t15", "In 2025 energy supply per person was about 42 GJ and imports made up 54 % of supply.", "geography-table-derived", True),
    ("c2/ge-t15", "Natural growth in supply per person reached 3.9 GJ by 2025.", "geography-table-derived", False),
    ("c2/ge-t15", "Coal and oil together supplied 77 % of primary energy in 2005.", "geography-table-derived", True),
    ("c2/ge-t15", "Total primary energy supply rose from 820 PJ in 2005 to 1,050 PJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", "The nuclear share rose by 2 percentage points, a relative rise of about 100%.", "geography-table-derived", True),
    ("c2/ge-t15", "Hydroelectric power and nuclear power supplied 57.4 PJ in 2005.", "geography-table-derived", True),
    ("c2/ge-t15", "Wind and solar power and nuclear power together made up 17% of supply in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", "Coal supply was 377.2 PJ in 2005 and 294.0 PJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", "Solar and wind supplied 8.2 PJ in 2005 and 136.5 PJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", "Imported energy was 311.6 PJ in 2005 and 567.0 PJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", "Imported energy, mostly oil and gas, was about 567 PJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", "The coal share fell by about 18% from 2005 to 2025.", "geography-table-change", False),
    ("c2/ge-t15", "The coal share fell by about 39% from 2005 to 2025.", "geography-table-change", False),
    ("c2/ge-t15", "The coal share fell by about 18 percentage points from 2005 to 2025.", "geography-table-change", True),
    ("c2/ge-t15", "Coal fell by a relative 39% from 2005 to 2025.", "geography-table-change", True),
    ("c2/ge-t15", "In 2025 natural gas supplied 231 PJ (22% of 1,050 PJ).", "geography-table-derived", False),
    ("c2/ge-p9c", "Together the two storms delivered 74 mm of rain.", "geography-request-figure", True),
    ("c2/ge-p9c", "Storm 2's peak discharge was three times Storm 1's.", "geography-pair-comparison", True),
    ("c2/ge-p9c", "The calculated discharge of 16.2 m³ s⁻¹ is three times Storm 1's peak of 5.4 m³ s⁻¹.", "geography-request-figure",
     False),
    ("c2/ge-p9c", "The lag fell by seven and a half hours, from twelve hours to four and a half hours.", "core-quant", False),
    ("c1/sp-t14", "6. En 1960 la escuela tenía más de cien alumnos.", "language-b-supplied-figure", True),
    ("c1/sp-t14", "Valdeoca tenía dos panaderías y una escuela con más de cien alumnos en 1960.", "language-b-supplied-figure", True),
    ("c1/sp-t14", "Hoy viven en Valdeoca 268 personas.", "language-b-supplied-figure", True),
    ("c1/sp-t14", "En 2015 Valdeoca tenía 212 vecinos.", "language-b-supplied-figure", True),
    ("c1/sp-t14", "En 2021 el ayuntamiento creó un espacio con doce puestos.", "language-b-supplied-figure", True),
    ("c1/sp-t14", "En 2015 la escuela llevaba seis años cerrada.", "language-b-supplied-figure", False),
    ("c1/sp-t14", "Un 25 % de 80 equivale a 20.", "language-b-share", True),
    ("c1/sp-t14", "Una cuarta parte de 80 son 20.", "language-b-share", True),
    ("c1/sp-t14", "De los 80 alumnos, el 25 % (20 alumnos) estudia francés.", "language-b-share", True),
    ("c1/sp-t14", "El 25 % del total de 80 alumnos corresponde a 20 alumnos.", "language-b-share", True),
    ("c1/sp-t14", "Veinte alumnos, el 25 % de 80, estudian francés.", "language-b-share", True),
    ("c1/sp-t14", "Veinte de cada ochenta, es decir el 25 %.", "language-b-share", True),
    ("c1/sp-t14", "La mitad de los 80 alumnos, es decir 40, estudia francés.", "language-b-share", True),
    ("c1/sp-t14", "One in every four pupils, that is 25%, studies French.", "language-b-share", True),
    ("c1/sp-t14", "A quarter of 80 is 20.", "language-b-share", True),
    # the totals, parts and counts of the answer's own shares and rates are no figures taken from the text (c3e left)
    ("c1/sp-t14", "De los 80 alumnos, el 25 % (20 alumnos) estudia francés.", "language-b-supplied-figure", False),
    ("c1/sp-t14", "El 25 % de los 80 alumnos, es decir 20 alumnos, estudia francés.", "language-b-supplied-figure", False),
    ("c1/sp-t14", "En 2023 los jóvenes eran el 25 % de los 80 vecinos.", "language-b-supplied-figure", False),
    ("c1/sp-t14", "Dos de cada tres vecinos son mayores.", "language-b-supplied-figure", False),
    ("c1/ge-t14", "Retail use fell by 92 percentage points along the transect.", "geography-supplied-figure", True),
    ("c1/ge-t14", "Pedestrian counts fell by about 91% from Site 1 to Site 10.", "geography-supplied-figure", True),
    ("c1/ge-t14", "The EQS fell by 13 points from Site 1 to Site 10.", "geography-supplied-figure", True),
    ("c1/ge-t14", "Retail use fell by about 92% along the transect.", "geography-supplied-figure", False),
    ("c2/ge-t15", "Imports made up 54% of supply in 2025, up from 38% in 2005.", "geography-table-derived", True),
    ("c3/ge-t16", "The Haiti earthquake was 0.1 magnitude units weaker than Darfield.", "geography-event-relation", True),
    ("c3/ge-t16", "The Christchurch aftershock was 0.9 magnitude units smaller than the Darfield earthquake.", "geography-event-relation", True),    ("c2/sp-t15", "La consigna pide entre cuatrocientas cincuenta y seiscientas palabras.", "language-b-word-range-claim", True),
    ("c3/sp-t16", "The SL task sets a range of 250 to 400 words.", "language-b-word-range-claim", True),
    ("c3/sp-p10d", "The task allows at most 250 words.", "language-b-word-range-claim", False),
]


@pytest.mark.parametrize("name,sentence,family,code", FAULTY)
def test_a_wrong_figure_is_named_and_never_entailed(name, sentence, family, code):
    found, checks, entailed = _new(name, sentence)
    assert code in found and any(c[0].startswith(family) and c[1] == "COUNTEREXAMPLE" for c in checks), (sentence, found, checks)
    # the one wrong figure's check fails; a sentence of two figures holds one right figure besides it (its own entailed check)
    right = 1 if sentence in ONE_RIGHT_FIGURE else 0
    assert len([c for c in entailed if c[0].startswith(family)]) == right, (sentence, entailed)


#: The faulty statements that also state one right figure (2005's 38 GJ, 820 PJ, 377.2 PJ or 311.6 PJ, or the stated points).
ONE_RIGHT_FIGURE = {s for _n, s, _f, _c in FAULTY if s.startswith((PP, "Energy supply per person was about 38 GJ in 2005,", "Total primary",
                                                                     "Coal supply", "Imported energy was", "Valdeoca tenía dos", "Imports made up"))}


@pytest.mark.parametrize("name,sentence,family,entailed_expected", CORRECT)
def test_a_correct_figure_is_never_a_counterexample(name, sentence, family, entailed_expected):
    found, checks, entailed = _new(name, sentence)
    assert not any(c[0].startswith(family) for c in checks), (sentence, found, checks)
    assert any(c[0].startswith(family) for c in entailed) is entailed_expected, (sentence, entailed)


def test_a_wrong_figure_of_a_per_person_pair_is_the_one_refuted():
    # the wrong 2025 figure of each pair is the counterexample, and the right 2005 figure (38.3 GJ) the entailed check
    for clause in ("with natural growth", "as nuclear capacity grew", "despite oil prices"):
        _found, checks, entailed = _new("c2/ge-t15", f"{PP}, {clause}, about 9.3 GJ in 2025.")
        assert len([c for c in checks if c[0].startswith("geography-table-derived")]) == 1, (clause, checks)
        assert len([c for c in entailed if c[0].startswith("geography-table-derived")]) == 1, (clause, entailed)


@pytest.mark.parametrize("unit", ["about 38 GJ in 2005, ", "about 38 GJ and ", "as nuclear grew, about 9.3 GJ, ", "coal and oil and gas, about 5 PJ ",
                                  "growth of 4 GJ in 2025 and "])
def test_the_year_table_row_lookup_stays_linear(unit):
    # push check of a9129c78 (a stall): 'Energy supply per person was ' + 'about 38 GJ in 2005, ' * k took 1.8, 9.1, 60 and 438 s at 5k,
    # 10k, 20k and 40k characters (each figure walked back over every earlier clause and rebuilt the word positions each step); now the
    # sentence is indexed once and each lookup is a few binary searches (each doubling at most 3 times the time, a 5 s ceiling)
    from epinoic_logic.branches import geography
    _answer, question, subject, agent, task_type, docs = H.RECORDED["c2/ge-t15"]
    took = []
    for n in (20_000, 40_000):
        text = "Energy supply per person was " + (unit * (n // len(unit) + 1))[:n] + "."
        rep = H.report(subject, agent, text, task_type=task_type, docs=docs,
                       claims=[dict(claim_id="c1", claim_text=text[:3000], claim_role="point", materiality="material")])
        t0 = time.process_time()
        geography._build(rep, question)
        took.append(time.process_time() - t0)
    assert took[1] < 5.0 and took[1] <= 3 * max(took[0], 0.2), took


QUOTE_ERRORS = ("CORE-SRC-006", "INT-SUBJ-003")


def _ll_core_codes(extra: str, task_type: str) -> list[str]:
    """The core pack's error-level quotation codes on ll-t16 with ``extra`` appended."""
    from ..channel.c3_core_support import _deliver
    from ..channel.test_c3c_own_correction import LL
    item = dict(LL)
    item["task_type"] = task_type
    hub, _ch, _reply, rc = _deliver(item, None, LL["response_text"] + "\n\n" + extra)
    hub.close()
    return sorted({f.code for f in [*rc.findings, *rc.structural_findings] if f.code in QUOTE_ERRORS and f.severity == "error"})


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_an_own_correction_on_ll_t16_draws_no_core_quotation_error(task_type):
    # push check of a9129c78 (an over-block): CORE-SRC-006 at error plus INT-SUBJ-003 on the answer's own correction
    got = _ll_core_codes('Before: "the adverts are about money". After: "the adverts sell saving as a family duty".', task_type)
    assert got == [], got


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_a_misquotation_of_the_source_in_an_own_correction_stays_charged(task_type):
    # (INV-Q1: the corrected half presents the advert's slogan altered, 'Every kitchen has a story.' quoted as '... a secret.')
    from ..channel.c3_core_support import _deliver
    from ..channel.test_c3c_own_correction import LL
    item = dict(LL)
    item["task_type"] = task_type
    hub, _ch, _reply, rc = _deliver(item, None, LL["response_text"] + '\n\nBefore: "Every kitchen has a story." After: "Every kitchen has a secret."')
    hub.close()
    errors = {f.code for f in [*rc.findings, *rc.structural_findings] if f.severity == "error"}
    assert errors & {"INT-REQ-003", "ES-SRC-001", "CORE-SRC-006"}, errors


SP16_LINE = '- "El primer semana fue difícil" → "La primera semana fue difícil" (semana'


@pytest.mark.parametrize("line", [
    '- Mal: "El primer semana fue difícil". Bien: "La primera semana fue difícil" (semana',
    '- Antes: "El primer semana fue difícil". Después: "La primera semana fue difícil" (semana',
    '- Incorrecto: «El primer semana fue difícil». Correcto: «La primera semana fue difícil» (semana',
    '- Escribiste «El primer semana fue difícil»; lo correcto es «La primera semana fue difícil» (semana',
], ids=["mal-bien", "antes-despues", "incorrecto-correcto", "escribiste"])
def test_the_answers_own_correction_lines_are_counted_in_every_label_form(line):
    # c3e left (sp-t16): with one correction written with a Spanish label, the answer's correct 'fix the six points' and 'agreement
    # (three)' drew COUNTEREXAMPLEs (five correction lines found); the lines are now read with the channel's own-text reader too
    from . import d9d10_texts as T
    assert SP16_LINE in T.SP_T16
    rc = H.recorded("c3/sp-t16", T.SP_T16.replace(SP16_LINE, line))
    got = H.checks(rc, "language-b-listed")
    assert got and all(status == "ENTAILED" for _c, status in got), got
    wrong = H.recorded("c3/sp-t16", T.SP_T16.replace(SP16_LINE, line).replace("fix the six points", "fix the seven points"))
    assert ("language-b-listed-count-1", "COUNTEREXAMPLE") in H.checks(wrong, "language-b-listed"), H.checks(wrong, "language-b-listed")


@pytest.mark.parametrize("sentence,entailed", [
    ("After coal declined, imports made up 28% of supply in 2025.", False),
    ("After coal declined, imports made up 54% of supply in 2025.", False),
    ("Imports made up 54%, after coal declined, in 2025.", False),
    ("Wind and solar power, with natural gas growing, made up 13% of supply in 2025.", True),
    ("Coal supplied 28% in 2025, after a fall from 46%.", True),
])
def test_a_row_named_only_in_an_intervening_clause_never_takes_a_figure_of_the_shared_table_reader(sentence, entailed):
    # the sweep of every row lookup (push check of a9129c78): 'coal' of 'After coal declined' named the row of 'imports made up 28%',
    # which drew core-figure ENTAILED against Coal 2025; 'natural gas' of 'with natural gas growing' took the wind and solar figure
    _found, checks, got = _new("c2/ge-t15", sentence)
    assert not [c for c in checks if c[0].startswith("core-figure")], (sentence, checks)
    assert bool([c for c in got if c[0].startswith("core-figure")]) is entailed, (sentence, got)


def test_a_wrong_share_beside_an_intervening_row_is_refuted_by_the_shared_reader():
    _found, checks, _got = _new("c2/ge-t15", "Wind and solar power, with natural gas growing, made up 22% of supply in 2025.")
    assert any(c[0].startswith("core-figure") and c[1] == "COUNTEREXAMPLE" for c in checks), checks
