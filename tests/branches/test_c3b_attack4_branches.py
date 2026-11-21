"""Attack round 4 of the c3b fix: the Geography and Language B findings the round reproduced on the working tree, each with its
expected value fixed here (the inputs are the attack's own).

* Geography: the change-by reader is linear in the answer (the pairs of a sentence are found once, never once per change); each
  figure of a supplied table is read with the row its own clause names (a figure after "Site 4" is Site 4's, coordinated rows take
  coordinated figures in order) and with the column of its unit ("Site 4 (300 m)" is a distance); "each figure is the mean of three
  counts" restates the table's method, no column mean; a magnitude belongs to the event of its own clause, and a capitalised "The"
  before a name never hides the name; a year before a bracket of parts is a date, and a total worked from its parts in brackets is no
  table cell.
* Language B: a figure restated after "es decir" is worked out, never one copied from the text; the size of a change stated after its
  from-to pair is checked against their difference.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches.geography import GeographyPack

from . import d9d10_hub as H
from . import d9d10_texts as T


def _geo_report(text: str):
    claims = [dict(claim_id="c1", claim_text=text[:200], claim_role="point", materiality="material")]
    return H.report(*H.GEO, text, claims=claims)


@pytest.mark.parametrize("unit", ["rose by 12 percentage points from 1% to ", "average annual growth rate of 2% grew by 2% a year "])
def test_the_change_by_reader_is_linear_in_the_answer(unit):
    times = []
    for n in (25_000, 200_000):
        text = (unit * (n // len(unit) + 1))[:n]
        rep = _geo_report(text)
        t0 = time.perf_counter()
        GeographyPack().formal_checks_for(rep, "Answer the question.")
        times.append(time.perf_counter() - t0)
    # eight times the answer: the quadratic reader took about 60 times as long (63 s at 200 kB); a linear one about eight
    assert times[1] < max(6.0, 14 * times[0]), times


@pytest.mark.parametrize("record, sentence", [
    ("c1/ge-t14", "In your table, Site 4 (300 m) had 97 pedestrians and Site 5 (400 m) had 88."),
    ("c1/ge-t14", "Site 4 (300 m) had 97 pedestrians and Site 5 (400 m) had 88."),
    ("c1/ge-t14", "In your table, between Site 7 and Site 8 the count rose slightly, from 42 to 45."),
    ("c1/ge-t14", "According to your table, Site 10 had an EQS of 11, and Site 9 had an EQS of 9."),
    ("c1/ge-t14", "Each pedestrian figure in your table is the mean of three counts of 10 minutes each."),
    ("c3/ge-t16", "The Darfield earthquake was magnitude 7.1; the Christchurch aftershock was magnitude 6.2."),
    ("c3/ge-t16", "The Haiti earthquake (magnitude 7.0) and the Darfield earthquake (magnitude 7.1) were of similar size."),
    ("c3/ge-t16", "Haiti: magnitude 7.0, 12 January 2010.\nDarfield: magnitude 7.1, 4 September 2010.\nChristchurch: magnitude 6.2, 22 February 2011."),
    ("c2/ge-t15", "Domestic sources supplied 62% of primary energy in 2005 (100 − 38) and 46% in 2025 (100 − 54)."),
    ("c2/ge-t15", "Fossil fuels (coal, oil and gas) made up 92% of supply in 2005 (46 + 31 + 15) and 77% in 2025 (28 + 27 + 22)."),
    ("c1/sp-t14", "Según el texto, llegó una pareja de traductores con tres hijos, es decir, cinco personas."),
    ("c1/sp-t14", "En 1960 la escuela tenía más de cien alumnos; hoy tiene catorce alumnos, es decir, unos 86 alumnos menos como mínimo."),
    ("c1/sp-t14", "La población cayó de 1.250 a 212 habitantes, es decir, en 1.038 personas."),
])
def test_a_correct_figure_draws_no_new_finding(record, sentence):
    base = H.recorded(record)
    text = getattr(T, record.split("/")[1].upper().replace("-", "_"))
    rc = H.recorded(record, text + "\n\n" + sentence)
    assert set(H.codes(rc)) <= set(H.codes(base)), H.codes(rc)
    base_bad = [c for c in H.checks(base) if c[1] == "COUNTEREXAMPLE"]
    assert [c for c in H.checks(rc) if c[1] == "COUNTEREXAMPLE" and c not in base_bad] == []


@pytest.mark.parametrize("record, sentence", [
    ("c1/ge-t14", "In your table, Site 4 (300 m) had 79 pedestrians and Site 5 (400 m) had 88."),
    ("c1/ge-t14", "In your table, between Site 7 and Site 8 the count rose slightly, from 42 to 54."),
    ("c1/ge-t14", "According to your table, Site 10 had an EQS of 9, and Site 9 had an EQS of 9."),
    ("c1/ge-t14", "In your table, Site 1 and Site 10 had 214 and 91 pedestrians."),
    ("c1/sp-t14", "La población cayó de 1.250 a 212 habitantes, es decir, en 1.138 personas."),
])
def test_a_misread_or_miscalculated_figure_is_still_named(record, sentence):
    text = getattr(T, record.split("/")[1].upper().replace("-", "_"))
    rc = H.recorded(record, text + "\n\n" + sentence)
    assert H.failed(rc, "INT-SUBJ-001"), H.codes(rc)


#: Misses of round 4 now decided: a product in brackets, "up from" with its relative change, a superlative over a supplied table's
#: column, a comparison of two figures the sentence writes, a Spanish perfect-tense change with its per cent. (record, how, text, wrong?)
DECIDED = [
    ("c2/ge-t15", "add", "Natural gas supply rose from 123.0 PJ (0.15 × 820) in 2005 to 241.0 PJ (0.22 × 1,050) in 2025.", True),
    ("c2/ge-t15", "add", "Natural gas supply rose from 123.0 PJ (0.15 × 820) in 2005 to 231.0 PJ (0.22 × 1,050) in 2025.", False),
    ("c2/ge-t15", "rep", ("311.6 PJ (0.38 × 820 PJ)", "321.6 PJ (0.38 × 820 PJ)"), True),
    ("c2/ge-t15", "add", "In 2025, 54% of supply was imported, up from 38% in 2005, a relative increase of 52%.", True),
    ("c2/ge-t15", "add", "In 2025, 54% of supply was imported, up from 38% in 2005, a relative increase of 42%.", False),
    ("c1/ge-t14", "add", "In your table, Site 7 has the lowest EQS of the ten sites.", True),
    ("c1/ge-t14", "add", "In your table, Site 9 has the lowest EQS of the ten sites.", False),
    ("c1/ge-t14", "add", "In your table, the pedestrian count at 700 m (45) is lower than at 600 m (42).", True),
    ("c1/ge-t14", "add", "In your table, the pedestrian count at 700 m (45) is higher than at 600 m (42).", False),
    ("c1/sp-t14", "add", "Desde 2015 la población ha crecido un 36 %, de 212 a 268 personas.", True),
    ("c1/sp-t14", "add", "Desde 2015 la población ha crecido un 26 %, de 212 a 268 personas.", False),
    ("c3/ge-t16", "add", "Haiti's estimated toll was about 1,600 times Christchurch's 185 deaths (300,000 ÷ 185).", False),
    ("c1/sp-t14", "add", "Entre 2015 y hoy el pueblo ganó 66 vecinos.", True),
    ("c1/sp-t14", "add", "Entre 2015 y hoy el pueblo ganó 56 vecinos.", False),
    ("c1/sp-t14", "add", "Entre 1960 y 2015 Valdeoca perdió 1.138 habitantes.", True),
    ("c1/sp-t14", "add", "Entre 1960 y 2015 el pueblo perdió más de mil habitantes.", False),
]


@pytest.mark.parametrize("record, how, change, wrong", DECIDED)
def test_a_round4_statement_is_decided(record, how, change, wrong):
    text = getattr(T, record.split("/")[1].upper().replace("-", "_"))
    if how == "add":
        new_text = text + "\n\n" + change
    else:
        assert change[0] in text
        new_text = text.replace(*change)
    base = H.recorded(record)
    rc = H.recorded(record, new_text)
    named = bool(H.failed(rc, "INT-SUBJ-001")) or bool([f for f in rc.findings if f.code == "INT-SUBJ-004" and
                                                         f.message not in {g.message for g in base.findings}])
    assert named is wrong, [(f.code, f.message[:160]) for f in rc.findings if f.code.startswith("INT-SUBJ")]
