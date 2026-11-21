"""Attack round 3 of the c3b fix: the branch and routing findings the round reproduced on the working tree, each with its expected value
fixed here.

* Routing: a label that names another subject first keeps that subject's branch ("Chemistry: ab initio methods", "Psychology: language
  acquisition", "Extended essay in Spanish B"); only a label whose subject is a Language B or ab initio course routes to language_b.
* Language B: the address-form reader folds the production once per build (linear in the answer); checks past the reading bound are
  named (CORE-QNT-001), never dropped silently; a figure worked out from the text's figures (a difference, the size of a change, a bound
  on a change, a figure of today against dated ones) is never compared with a figure the text states; a numeral grouped by blanks
  ("1 250") is one number.
* Geography: statements past the reading bound are named (CORE-QNT-001), never dropped silently.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches.language_b import LanguageBPack
from epinoic_logic.translate.subjects import resolve_profile

from . import d9d10_hub as H
from . import d9d10_texts as T


# ------------------------------------------------------------------------------------------------------------------ routing
@pytest.mark.parametrize("label, key", [
    ("Chemistry: ab initio methods", "chemistry"),
    ("Biology: language acquisition and the brain", "biology"),
    ("Psychology: language acquisition", "psychology"),
    ("Psychology (language acquisition)", "psychology"),
    ("Philosophy of language acquisition", "philosophy"),
    ("TOK essay on language acquisition", "tok"),
    ("Computer science: Spanish B app", "computer_science"),
    ("Extended essay in Spanish B", "extended_essay"),
    ("Spanish B", "language_b"),
    ("Language B: Spanish", "language_b"),
    ("Language acquisition: Spanish", "language_b"),
    ("French ab initio", "language_b"),
    ("IB Spanish B HL", "language_b"),
    ("English B", "language_b"),
    ("Lengua B: Español", "language_b"),
])
def test_a_label_routes_by_the_subject_it_names_first(label, key):
    assert resolve_profile(label).key == key


# ------------------------------------------------------------------------------------------------------------------ Language B
def _reading_report(text: str):
    claims = [dict(claim_id="c1", claim_text=text[:200], claim_role="point", materiality="material")]
    return H.report(*H.SPB, text, task_type="reading_comprehension", docs=(T.SP_T14_DOC,), claims=claims)


def test_the_address_form_reader_is_linear_in_a_reading_answer():
    unit = 'You use tú ("¿Y tú qué opinas?"). '
    times = []
    for n in (25_000, 200_000):
        text = (unit * (n // len(unit) + 1))[:n]
        rep = _reading_report(text)
        t0 = time.perf_counter()
        LanguageBPack().formal_checks_for(rep, "Read the article and answer.")
        times.append(time.perf_counter() - t0)
    # eight times the answer: the quadratic reader took about 25 times as long (15 s at 200 kB); a linear one about eight
    assert times[1] < max(4.0, 14 * times[0]), times


def test_language_b_checks_past_the_bound_are_named():
    good = "Según el texto, hoy viven 268 personas en Valdeoca."
    bad = "Según el texto, en una semana recibieron más de trescientas solicitudes."
    rc = H.recorded("c1/sp-t14", T.SP_T14 + "\n\n" + "\n\n".join([good] * 230) + "\n\n" + bad)
    named = [f for f in list(rc.findings) + list(rc.structural_findings or []) if f.code == "CORE-QNT-001" and "reading bound" in f.message]
    assert named, sorted({f.code for f in rc.findings})


@pytest.mark.parametrize("sentence", [
    "Según el texto, hoy viven 56 personas más que en 2015.",
    "Según el texto, entre 1960 y 2015 el pueblo perdió más de mil habitantes.",
    "Entre 2015 y hoy la población creció en 56 personas.",
    "Entre 1960 y 2015 Valdeoca perdió 1.038 habitantes.",
    "La población cayó de 1.250 a 212 habitantes, es decir, en 1.038 personas.",
    "De las dos panaderías de 1960 queda abierta una: había 2 panaderías y hoy hay 1 panadería.",
])
def test_a_figure_worked_out_from_the_text_is_not_read_as_one_taken_from_it(sentence):
    rc = H.recorded("c1/sp-t14", T.SP_T14 + "\n\n" + sentence)
    assert not [c for c in H.checks(rc, "language-b-supplied-figure") if c[1] != "ENTAILED"], H.checks(rc, "language-b")


@pytest.mark.parametrize("sentence", [
    "Según el texto, en una semana recibieron más de trescientas solicitudes.",
    "Según el texto, hoy viven 286 personas en Valdeoca.",
])
def test_a_figure_misread_from_the_text_is_still_named(sentence):
    rc = H.recorded("c1/sp-t14", T.SP_T14 + "\n\n" + sentence)
    assert H.failed(rc, "INT-SUBJ-001"), H.codes(rc)


def test_a_numeral_grouped_by_blanks_is_one_number():
    assert "1. 1.250 habitantes en 1960" in T.SP_T14
    base = H.recorded("c1/sp-t14")
    rc = H.recorded("c1/sp-t14", T.SP_T14.replace("1. 1.250 habitantes en 1960", "1. 1 250 habitantes en 1960"))
    assert H.codes(rc) == H.codes(base)
    assert not [c for c in H.checks(rc) if c[1] == "COUNTEREXAMPLE" and "figure" in c[0]]


# ------------------------------------------------------------------------------------------------------------------ Geography
def test_geography_statements_past_the_bound_are_named():
    good = "Town {i} had 1,000 people on 10 km², a density of 100 people per km²."
    bad = "Town Z had 1,000 people on 10 km², a density of 900 people per km²."
    text = "\n\n".join(good.format(i=i) for i in range(70)) + "\n\n" + bad
    rc = H.through_hub(text, "Calculate the densities.", *H.GEO)
    named = [f for f in list(rc.findings) + list(rc.structural_findings or []) if f.code == "CORE-QNT-001" and "reading bound" in f.message]
    assert named and "7 further" in named[0].message, [f.message for f in named]


def test_geography_below_the_bound_still_names_the_wrong_density():
    good = "Town {i} had 1,000 people on 10 km², a density of 100 people per km²."
    bad = "Town Z had 1,000 people on 10 km², a density of 900 people per km²."
    rc = H.through_hub("\n\n".join(good.format(i=i) for i in range(10)) + "\n\n" + bad, "Calculate the densities.", *H.GEO)
    assert H.failed(rc, "INT-SUBJ-001")


# ------------------------------------------------------------------------------------------------------------------ Language B: changes
#: (sentence appended to the recorded sp-t14 answer, wrong?) A change stated with a per cent before its from-to pair, a dated noun phrase
#: between the two figures, a per cent over a period with no pair, a difference against a dated figure and a fold comparison: each decided
#: against the article's figures (1.250 habitantes en 1960, 212 vecinos en 2015, 268 personas hoy); a per cent after "más del" is a bound.
DATED = [
    ("Entre 2015 y hoy la población creció un 36 %, de 212 a 268 personas.", True),
    ("Entre 2015 y hoy la población creció un 26 %, de 212 a 268 personas.", False),
    ("La población pasó de 212 vecinos en 2015 a 268 personas hoy, un aumento del 46 %.", True),
    ("La población pasó de 212 vecinos en 2015 a 268 personas hoy, un aumento del 26 %.", False),
    ("La población pasó de 1.250 habitantes en 1960 a 212 en 2015, una caída del 73 %.", True),
    ("La población pasó de 1.250 habitantes en 1960 a 212 en 2015, una caída del 83 %.", False),
    ("Según el texto, la población de Valdeoca bajó un 73 % entre 1960 y 2015.", True),
    ("Según el texto, la población de Valdeoca bajó un 83 % entre 1960 y 2015.", False),
    ("De 1960 a 2015 la población bajó un 93 %.", True),
    ("De 1960 a 2015 la población bajó un 83 %.", False),
    ("Según el texto, hoy viven 268 personas, 66 más que en 2015.", True),
    ("Según el texto, hoy viven 268 personas, 56 más que en 2015.", False),
    ("Hoy viven 268 personas: 56 más que en 2015 y 892 menos que en 1960.", True),
    ("Hoy viven 268 personas: 56 más que en 2015 y 982 menos que en 1960.", False),
    ("Hoy viven en Valdeoca 268 personas, más del doble que los 212 vecinos de 2015.", True),
    ("Entre 1960 y 2015 Valdeoca perdió más del 80 % de sus habitantes.", False),
    ("Entre 1960 y 2015 Valdeoca perdió más del 90 % de sus habitantes.", True),
    ("La población bajó de 1.250 a 212 habitantes, un 63 % menos.", True),
    ("La población bajó de 1.250 a 212 habitantes, un 83 % menos.", False),
]


@pytest.mark.parametrize("sentence, wrong", DATED)
def test_a_change_over_the_texts_dated_figures_is_decided(sentence, wrong):
    rc = H.recorded("c1/sp-t14", T.SP_T14 + "\n\n" + sentence)
    bad = [c for c in H.checks(rc, "language-b") if c[1] != "ENTAILED"]
    named = [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    if wrong:
        assert bad and named, (H.checks(rc, "language-b"), H.codes(rc))
    else:
        assert not bad and not named, (bad, H.codes(rc))


# ------------------------------------------------------------------------------------------------------------------ Language B: figures
#: Figures taken from the Valdeoca article, appended to the recorded sp-t14 answer (or replacing its own line): a small count before a
#: plural noun ("tres hijos", "diez viviendas"), an age or span in years, a figure the article dates by its sentence's one year, a figure
#: whose number the article states under another noun ("doce" is the article's count of desks, not of homes), a figure opening its
#: sentence, the article's figure dated with another year, an event's year, and "veintiún". (sentence, wrong?)
FIGURES = [
    ("Según el texto, Julián Pardo ha sido pastor durante cincuenta años.", True),
    ("Según el texto, Julián Pardo ha sido pastor durante cuarenta años.", False),
    ("Según el texto, la escuela llevaba cerrada desde 2010.", True),
    ("Según el texto, la escuela llevaba cerrada desde 2009.", False),
    ("Según el texto, la fibra óptica llegó en 2019.", True),
    ("Según el texto, la fibra óptica llegó en 2021.", False),
    ("Según el texto, en 1960 la escuela tenía más de doscientos alumnos.", True),
    ("Según el texto, en 1960 la escuela tenía más de cien alumnos.", False),
    ("Según el texto, en 2015 la mayoría de los vecinos tenía más de sesenta años.", True),
    ("Según el texto, la pareja de traductores tiene cuatro hijos.", True),
    ("Según el texto, la pareja de traductores tiene tres hijos.", False),
    ("Según el texto, el ayuntamiento prepara doce viviendas de alquiler.", True),
    ("Según el texto, el ayuntamiento prepara 16 viviendas de alquiler.", True),
    ("Según el texto, el ayuntamiento prepara diez viviendas de alquiler.", False),
    ("Según el texto, en 1960 Valdeoca tenía tres panaderías.", True),
    ("Según el texto, en 1960 Valdeoca tenía dos panaderías.", False),
    ("Quince alumnos volvieron a la escuela en septiembre, según el texto.", True),
    ("Catorce alumnos volvieron a la escuela en septiembre, según el texto.", False),
    ("Según el texto, Julián Pardo ha sido pastor durante cuatro décadas.", False),
    ("Según el texto, recibieron más de 400 solicitudes en siete días.", False),
    ("Según el texto, hoy ha reabierto una de las dos panaderías.", False),
    ("De las dos panaderías de 1960 queda abierta una: había 2 panaderías y hoy hay 1 panadería.", False),
]
REPLACED = [
    ("212 vecinos en 2015.", "doscientos veintiún vecinos en 2015.", True),
    ("212 vecinos en 2015.", "doscientos doce vecinos en 2015.", False),
    ("compartido con doce puestos.", "compartido con once puestos.", True),
    ("1. 1.250 habitantes en 1960", "1. 1.250 habitantes en 1950", True),
]


def _named(rc) -> list:
    return [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]


@pytest.mark.parametrize("sentence, wrong", FIGURES)
def test_a_figure_taken_from_the_article_is_read(sentence, wrong):
    rc = H.recorded("c1/sp-t14", T.SP_T14 + "\n\n" + sentence)
    assert bool(_named(rc)) is wrong, ([f.message[:160] for f in _named(rc)], H.checks(rc, "language-b"))


@pytest.mark.parametrize("old, new, wrong", REPLACED)
def test_a_figure_of_the_answers_own_line_is_read(old, new, wrong):
    assert old in T.SP_T14
    rc = H.recorded("c1/sp-t14", T.SP_T14.replace(old, new))
    assert bool(_named(rc)) is wrong, [f.message[:160] for f in _named(rc)]


def test_the_recorded_reading_answer_draws_no_figure_finding():
    assert not _named(H.recorded("c1/sp-t14"))


# ------------------------------------------------------------------------------------------------------------------ Language B: speakers
#: A quotation of the Valdeoca article credited to a speaker: the article credits «Pusimos un anuncio ...» and «En una semana ...» to the
#: mayor, Carmen Ortega, and «Ellos nos trajeron ...» to Julián Pardo. (sentence, wrong?)
SPEAKERS = [
    ("«Ellos nos trajeron la vida, pero también las prisas», dice la alcaldesa, Carmen Ortega.", True),
    ("La alcaldesa, Carmen Ortega, dice: «Ellos nos trajeron la vida, pero también las prisas».", True),
    ("Según la alcaldesa, «Ellos nos trajeron la vida, pero también las prisas».", True),
    ("«Pusimos un anuncio en internet sin muchas esperanzas», cuenta Julián Pardo.", True),
    ("Julián Pardo cuenta: «En una semana recibimos más de cuatrocientas solicitudes».", True),
    ("As the shepherd Julián Pardo puts it, «Pusimos un anuncio en internet sin muchas esperanzas».", True),
    ("The mayor, Carmen Ortega, says that the newcomers \"nos trajeron la vida, pero también las prisas\".", True),
    ("«Ellos nos trajeron la vida, pero también las prisas», dice Julián Pardo.", False),
    ("La alcaldesa, Carmen Ortega, cuenta: «Pusimos un anuncio en internet sin muchas esperanzas».", False),
    ("Según la alcaldesa, «En una semana recibimos más de cuatrocientas solicitudes».", False),
    ("The mayor says «Pusimos un anuncio en internet sin muchas esperanzas».", False),
]


@pytest.mark.parametrize("sentence, wrong", SPEAKERS)
def test_a_quotation_keeps_the_speaker_the_article_gives_it(sentence, wrong):
    rc = H.recorded("c1/sp-t14", T.SP_T14 + "\n\n" + sentence)
    assert bool(_named(rc)) is wrong, ([f.message[:160] for f in _named(rc)], H.checks(rc, "language-b-quote"))


# ------------------------------------------------------------------------------------------------------------------ Geography: table cells
#: Sentences appended to the recorded ge-t14 answer that read two columns or two rows of the supplied fieldwork table in one clause, a
#: distance, a figure placed away from its column word, and a from-to pair across rows. (sentence, wrong?) The table: Site 4 is 300 m
#: out with 97 pedestrians, EQS 18 and 60% retail; Site 5 has 88 pedestrians; Site 7 is 600 m out with 42; Site 8 has 45; Site 10 has
#: 19 and EQS 11.
CELLS = [
    ("Site 4 (300 m from the square) had 97 pedestrians per 10 minutes and an EQS of 21.", True),
    ("Site 4 (300 m from the square) had 97 pedestrians per 10 minutes and an EQS of 18.", False),
    ("According to your table, Site 10 is 900 m from the square and had 91 pedestrians per 10 minutes.", True),
    ("According to your table, Site 10 is 900 m from the square and had 19 pedestrians per 10 minutes.", False),
    ("At Site 5, 400 m from the square, your table records 98 pedestrians per 10 minutes.", True),
    ("At Site 5, 400 m from the square, your table records 88 pedestrians per 10 minutes.", False),
    ("According to your table, Site 8 had 45 pedestrians per 10 minutes and Site 7 had 24.", True),
    ("According to your table, Site 8 had 45 pedestrians per 10 minutes and Site 7 had 42.", False),
    ("According to your table, Site 7 is 700 m from the central square.", True),
    ("According to your table, Site 7 is 600 m from the central square.", False),
    ("According to your table, 66% of ground-floor units at Site 4 are in retail use.", True),
    ("According to your table, 60% of ground-floor units at Site 4 are in retail use.", False),
    ("Your table shows that Site 8 (54 pedestrians) breaks the trend, with more pedestrians than Site 7 (42).", True),
    ("Your table shows that Site 8 (45 pedestrians) breaks the trend, with more pedestrians than Site 7 (42).", False),
    ("Your table shows the EQS falling from 24 at Site 1 to 14 at Site 10.", True),
    ("Your table shows the EQS falling from 24 at Site 1 to 11 at Site 10.", False),
    ("Sites 1 and 2 had 214 and 186 pedestrians.", False),
    ("Pedestrian counts fell from 214 at Site 1 to 19 at Site 10, while retail use fell from 92% to 0%.", False),
    ("Your table gives Site 9 an EQS of 9 out of 30.", False),
]


@pytest.mark.parametrize("sentence, wrong", CELLS)
def test_each_figure_of_a_table_sentence_is_read_with_its_own_row_and_column(sentence, wrong):
    rc = H.recorded("c1/ge-t14", T.GE_T14 + "\n\n" + sentence)
    named = [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004") and "supplied" in f.message]
    assert bool(named) is wrong, [f.message[:200] for f in named]


# ------------------------------------------------------------------------------------------------------------------ Geography: aggregates
#: A supplied table read as a whole, and a change or multiple stated with its pair: the mean of a column (EQS 16.3, pedestrians 92.6), a
#: difference, per cent and multiple between two rows (214 and 19: 195, 91%, about 11 times), a bracketed list's mean, and the transect's
#: spacing and length (100 m, 900 m). (sentence, wrong?)
AGGREGATES = [
    ("The mean EQS across your ten sites is 18.3.", True),
    ("The mean EQS across your ten sites is 16.3.", False),
    ("The mean pedestrian count across your ten sites is 102.6 people per 10 minutes.", True),
    ("The mean pedestrian count across your ten sites is 92.6 people per 10 minutes.", False),
    ("According to your table, the pedestrian count falls by 185, from 214 at Site 1 to 19 at Site 10.", True),
    ("According to your table, the pedestrian count falls by 195, from 214 at Site 1 to 19 at Site 10.", False),
    ("Pedestrian flow fell by 81% between Site 1 (214) and Site 10 (19).", True),
    ("Pedestrian flow fell by 91% between Site 1 (214) and Site 10 (19).", False),
    ("Site 1 had about five times as many pedestrians as Site 10 (214 against 19).", True),
    ("Site 1 had about 11 times as many pedestrians as Site 10 (214 against 19).", False),
    ("The mean of the ten EQS values (24, 22, 23, 18, 15, 16, 12, 13, 9, 11) is 17.3.", True),
    ("The mean of the ten EQS values (24, 22, 23, 18, 15, 16, 12, 13, 9, 11) is 16.3.", False),
    ("You sampled ten sites every 100 m along a 1,000 m transect.", True),
    ("You sampled ten sites every 100 m along a 900 m transect.", False),
    ("You chose ten sites at 200 m intervals along one road.", True),
    ("You chose ten sites at 100 m intervals along one road.", False),
]


@pytest.mark.parametrize("sentence, wrong", AGGREGATES)
def test_a_table_aggregate_or_a_change_with_its_pair_is_decided(sentence, wrong):
    rc = H.recorded("c1/ge-t14", T.GE_T14 + "\n\n" + sentence)
    named = [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    assert bool(named) is wrong, [f.message[:200] for f in named]


def test_a_change_by_percentage_points_is_read_as_points_not_per_cent():
    # the recorded ge-t15 answer's "rose by 12 percentage points, from 1% in 2005 to 13% in 2025" holds
    rc = H.recorded("c2/ge-t15")
    assert ("geography-change-by-1", "ENTAILED") in H.checks(rc, "geography-change-by")


# ------------------------------------------------------------------------------------------------------------------ Geography: year tables
#: Credited figures of the year-keyed ge-t15 table (Coal 46 → 28, Hydroelectric power 5 → 6, total supply 820 → 1,050 PJ, imported 38 →
#: 54 %, population 21.4 → 24.9 million): a scale word the row states in the plural, two rows named by the same first words told apart by
#: the word only one holds, a possessive, and a from-to pair with no year read as the row's two years. (sentence, wrong?)
YEAR_TABLE = [
    ("Ostrel's population grew from 21.4 million in 2005 to 29.4 million in 2025.", True),
    ("Ostrel's population grew from 21.4 million in 2005 to 24.9 million in 2025.", False),
    ("The table gives Ostrel's population as 21.4 million in 2005 and 26.9 million in 2025.", True),
    ("According to the table, total primary energy supply was 1,150 PJ in 2025.", True),
    ("According to the table, total primary energy supply was 1,050 PJ in 2025.", False),
    ("According to the table, 48% of primary energy supply was imported in 2005.", True),
    ("According to the table, 38% of primary energy supply was imported in 2005.", False),
    ("According to the table, hydroelectric power's share rose from 5% in 2005 to 7% in 2025.", True),
    ("According to the table, hydroelectric power's share rose from 5% in 2005 to 6% in 2025.", False),
    ("Coal fell from 46% to 26% of supply.", True),
    ("Coal fell from 46% to 28% of supply.", False),
    ("Total supply rose from 820 PJ to 1,050 PJ.", False),
]


@pytest.mark.parametrize("sentence, wrong", YEAR_TABLE)
def test_a_figure_of_a_year_keyed_table_is_read(sentence, wrong):
    rc = H.recorded("c2/ge-t15", T.GE_T15 + "\n\n" + sentence)
    named = [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    assert bool(named) is wrong, [f.message[:200] for f in named]


def test_the_recorded_coal_pair_with_no_years_is_read_against_both_years():
    assert "coal down from 46% to 28%)" in T.GE_T15
    rc = H.recorded("c2/ge-t15", T.GE_T15.replace("coal down from 46% to 28%)", "coal down from 46% to 26%)"))
    assert [f for f in rc.findings if f.code == "INT-SUBJ-001"]


# ------------------------------------------------------------------------------------------------------------------ Geography: essay arithmetic
#: Appended to the recorded ge-t16 essay: a crude rate written in per cent, a death toll per 1,000, a multiple with its division in brackets,
#: and the rule of 70 worked after a clause that states the growth rate. (sentence, wrong?)
ESSAY = [
    ("There were 4,800 births in a population of 200,000, a crude birth rate of 4.2%.", True),
    ("There were 4,800 births in a population of 200,000, a crude birth rate of 2.4%.", False),
    ("With 600 deaths in a town of 80,000 people, the crude death rate was 0.95%.", True),
    ("With 600 deaths in a town of 80,000 people, the crude death rate was 0.75%.", False),
    ("With 300,000 deaths in a population of 10 million, the death toll was 3 per 1,000.", True),
    ("With 300,000 deaths in a population of 10 million, the death toll was 30 per 1,000.", False),
    ("Haiti's estimated toll was about 160 times Christchurch's 185 deaths (300,000 ÷ 185).", True),
    ("Haiti's estimated toll was about 1,600 times Christchurch's 185 deaths (300,000 ÷ 185).", False),
    ("By the rule of 70, a growth rate of 2% a year gives a doubling time of 70 ÷ 2 = 45 years.", True),
    ("By the rule of 70, a growth rate of 2% a year gives a doubling time of 70 ÷ 2 = 35 years.", False),
    ("The rule of 70 says 70 ÷ 2 = 45 years.", True),
]


@pytest.mark.parametrize("sentence, wrong", ESSAY)
def test_the_essays_arithmetic_is_decided(sentence, wrong):
    rc = H.recorded("c3/ge-t16", T.GE_T16 + "\n\n" + sentence)
    named = [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    assert bool(named) is wrong, [f.message[:200] for f in named]


def test_of_after_a_quantity_word_still_takes_part_in_the_arithmetic():
    from epinoic_logic.branches import worked as W
    for text in ("Half of 6,000 ÷ 2 = 1,500.", "The sum of 2 + 3 = 5."):
        assert all(r is None for _p, _s, r, _w in W._reads(text)), text


# ------------------------------------------------------------------------------------------------------------------ Geography: changes
#: (record, sentence appended, wrong?) A from-to pair written with units and points then its relative change (operands as written), a
#: fold verb with its pair, and a change of a supplied year-table row stated by its size over a period or in percentage points.
CHANGES = [
    ("c2/ge-p9c", "Peak discharge rose from 5.4 m³ s⁻¹ in 2006 to 16.2 m³ s⁻¹ in 2024, an increase of 300%.", True),
    ("c2/ge-p9c", "Peak discharge rose from 5.4 m³ s⁻¹ in 2006 to 16.2 m³ s⁻¹ in 2024, an increase of 200%.", False),
    ("c2/ge-p9c", "Base flow fell from 1.2 m³ s⁻¹ in 2006 to 1.1 m³ s⁻¹ in 2024, a fall of 20%.", True),
    ("c2/ge-p9c", "Base flow fell from 1.2 m³ s⁻¹ in 2006 to 1.1 m³ s⁻¹ in 2024, a fall of 8.3%.", False),
    ("c2/ge-p9c", "Rainfall fell from 38 mm in Storm 1 to 36 mm in Storm 2, a fall of 6.3%.", True),
    ("c2/ge-p9c", "Rainfall fell from 38 mm in Storm 1 to 36 mm in Storm 2, a fall of 5.3%.", False),
    ("c2/ge-p9c", "Peak discharge doubled, from 5.4 m³ s⁻¹ to 16.2 m³ s⁻¹.", True),
    ("c2/ge-p9c", "Peak discharge tripled, from 5.4 m³ s⁻¹ to 16.2 m³ s⁻¹.", False),
    ("c2/ge-t15", "Total primary energy supply grew by 330 PJ between 2005 and 2025.", True),
    ("c2/ge-t15", "Total primary energy supply grew by 230 PJ between 2005 and 2025.", False),
    ("c2/ge-t15", "Ostrel's population grew by 4.5 million between 2005 and 2025.", True),
    ("c2/ge-t15", "Ostrel's population grew by 3.5 million between 2005 and 2025.", False),
    ("c2/ge-t15", "The coal share fell by 16 percentage points.", True),
    ("c2/ge-t15", "The coal share fell by 18 percentage points between 2005 and 2025.", False),
]


@pytest.mark.parametrize("record, sentence, wrong", CHANGES)
def test_a_change_with_its_pair_or_its_table_row_is_decided(record, sentence, wrong):
    answer = {"c2/ge-p9c": T.GE_P9C, "c2/ge-t15": T.GE_T15}[record]
    rc = H.recorded(record, answer + "\n\n" + sentence)
    named = [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    assert bool(named) is wrong, [f.message[:200] for f in named]


#: Case quantities of the recorded ge-t16 essay stated again: a magnitude, "N of them" after its head noun (8,000 homes), and a quantity
#: stated with no place when the essay gives it for one place only (more than 470,000 claims). (sentence, wrong?)
CASES = [
    ("The magnitude 7.4 Darfield earthquake of 4 September 2010 caused no deaths.", True),
    ("The magnitude 7.1 Darfield earthquake of 4 September 2010 caused no deaths.", False),
    ("In Christchurch about 18,000 homes were later bought and cleared by the government.", True),
    ("In Christchurch about 8,000 homes were later bought and cleared by the government.", False),
    ("The Earthquake Commission's 407,000 claims show how widely insurance spread the cost.", True),
    ("The Earthquake Commission's 480,000 claims show how widely insurance spread the cost.", False),
    ("Haiti's 2010 earthquake was magnitude 7.0.", False),
]


@pytest.mark.parametrize("sentence, wrong", CASES)
def test_a_case_quantity_stated_twice_agrees(sentence, wrong):
    rc = H.recorded("c3/ge-t16", T.GE_T16 + "\n\n" + sentence)
    named = [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    assert bool(named) is wrong, [f.message[:200] for f in named]
