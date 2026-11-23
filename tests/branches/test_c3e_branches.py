"""The c3e follow-up on the Geography and Language B branches, each expected value fixed here.

(1) A function word never names a table row: on c2/ge-t15 the word 'and' of 'Wind and solar power' named that row in "Energy supply
per person was about 38 GJ in 2005 and about 5.5 GJ in 2025.", so the wrong 5.5 GJ was checked as the wind-and-solar share per person
and ENTAILED, while the correct 42 GJ drew a COUNTEREXAMPLE. A row is now named only by its distinctive content words.

(2) The branch misses of the 2be42c48 push check and the check round 10 leftovers, each read by a widened frame and pinned beside its
correct twin: an area given by a result verb or a cross-section, a relative or absolute difference of two labelled figures (the noun
before the label, 'rainfall' as the request's 'rain', a from-to bracket pair), a labelled possessive figure, a volume in powers of ten,
intervals in words (lag times, event intervals), the label itself as an interval's subject; a Spanish or English share of a total, a
period 'desde' a year with a present perfect, the present perfect of a change, Spanish and cleft paraphrase speakers, the task's
scenario in the same language and hyphenated counts, a duration with its bracketed years, a year in Spanish words, the course range
of a Paper 1 task that sets none, and the model text's word count.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from . import d9d10_hub as H

_BASE: dict = {}


def _new(name: str, sentence: str):
    """The error and warning codes and the non-entailed checks that ``sentence``, appended to the recorded answer ``name``, adds."""
    if name not in _BASE:
        _BASE[name] = H.recorded(name)
    b = _BASE[name]
    rc = H.recorded(name, H.RECORDED[name][0] + "\n\n" + sentence)
    old = {(f.code, f.severity, f.message[:140]) for f in b.findings}
    new = [f.code for f in rc.findings if f.severity in ("error", "warning") and (f.code, f.severity, f.message[:140]) not in old]
    old_checks = [c for c in H.checks(b) if c[1] != "ENTAILED"]
    checks = [c for c in H.checks(rc) if c[1] != "ENTAILED" and c not in old_checks]
    entailed = [c for c in H.checks(rc) if c[1] == "ENTAILED" and c not in H.checks(b)]
    return new, checks, entailed


# ------------------------------------------------------------------------------------------------------------------ (1) the and-row lead
AND_ROW_FAULTY = [
    "Energy supply per person was about 38 GJ in 2005 and about 5.5 GJ in 2025.",
    "Each person used about 38 GJ in 2005 and about 5 GJ in 2025.",
    "It is clear that energy supply per person was about 23 GJ in 2025.",
]
AND_ROW_CORRECT = [
    "Energy supply per person was about 38 GJ in 2005 and about 42 GJ in 2025.",
    "Each person used about 38 GJ in 2005 and about 42 GJ in 2025.",
    "It is clear that energy supply per person was about 42 GJ in 2025.",
]


@pytest.mark.parametrize("sentence", AND_ROW_FAULTY)
def test_a_wrong_figure_per_person_is_never_entailed_through_a_function_word(sentence):
    found, checks, entailed = _new("c2/ge-t15", sentence)
    assert "INT-SUBJ-004" in found and any(c[0].startswith("geography-table-derived") and c[1] == "COUNTEREXAMPLE" for c in checks), \
        (sentence, found, checks)
    # the wrong 2025 figure is never the one an ENTAILED check holds: its check fails
    assert len([c for c in checks if c[0].startswith("geography-table-derived")]) == 1, (sentence, checks, entailed)


@pytest.mark.parametrize("sentence", AND_ROW_CORRECT)
def test_the_correct_figure_per_person_is_entailed(sentence):
    found, checks, entailed = _new("c2/ge-t15", sentence)
    assert found == [] and checks == [] and any(c[0].startswith("geography-table-derived") for c in entailed), (sentence, found, checks, entailed)


def test_no_function_word_names_a_row():
    from epinoic_logic.branches import geography
    from epinoic_logic.branches.grounded_figures import FUNCTION_WORDS
    assert {"and", "that", "is", "or", "the", "of"} <= FUNCTION_WORDS
    assert geography._row_words("Wind and solar power") == {"wind", "solar", "power"}
    assert geography._row_words("Share of primary energy supply that is imported (%)") == {"share", "primary", "energy", "supply", "imported"}


# ------------------------------------------------------------------------------------------------------------------ (2) branch misses
#: (recorded answer, faulty sentence, its correct twin, the code the faulty one draws, the check family that fails)
MISSES = [
    # Geography: an area by a result verb or a cross-section ('an area of' alone was read)
    ("c2/ge-p9c", "At the peak, the channel measures 6.0 m by 1.8 m, giving 12.8 m².", "At the peak, the channel measures 6.0 m by 1.8 m, giving 10.8 m².",
     "INT-SUBJ-001", "geography-dimension-area"),
    ("c2/ge-p9c", "The channel was 6.0 m wide and 1.8 m deep, giving a cross-section of 9.8 m².",
     "The channel was 6.0 m wide and 1.8 m deep, giving a cross-section of 10.8 m².", "INT-SUBJ-001", "geography-dimension-area"),
    # a relative or absolute difference of two labelled figures ('rainfall' is the request's 'rain'; the noun before the label)
    ("c2/ge-p9c", "Storm 1 got roughly 10% more rainfall than Storm 2.", "Storm 1 got roughly 6% more rainfall than Storm 2.", "INT-SUBJ-001",
     "geography-pair-comparison"),
    ("c2/ge-p9c", "The rainfall of Storm 2 was 2 mm higher than that of Storm 1.", "The rainfall of Storm 2 was 2 mm lower than that of Storm 1.",
     "INT-SUBJ-001", "geography-pair-comparison"),
    ("c2/ge-p9c", "Storm 1 had 3 mm more rain than Storm 2.", "Storm 1 had 2 mm more rain than Storm 2.", "INT-SUBJ-001", "geography-pair-comparison"),
    ("c2/ge-p9c", "The peak discharge of Storm 2 was 11.8 m³/s higher than that of Storm 1.",
     "The peak discharge of Storm 2 was 10.8 m³/s higher than that of Storm 1.", "INT-SUBJ-001", "geography-pair-comparison"),
    # a from-to bracket pair after a relative difference
    ("c2/ge-p9c", "Storm 2's rainfall was about 8.3% lower than Storm 1's (from 38 mm to 36 mm).",
     "Storm 2's rainfall was about 5.3% lower than Storm 1's (from 38 mm to 36 mm).", "INT-SUBJ-001", "geography-pair-comparison"),
    # a labelled possessive figure is that label's figure of its unit
    ("c2/ge-p9c", "Storm 1's 36 mm over 24 km² is about 864,000 m³.", "Storm 1's 38 mm over 24 km² is about 912,000 m³.", "INT-SUBJ-004",
     "geography-request-figure"),
    # a volume in powers of ten
    ("c2/ge-p9c", "Storm 1's 38 mm over the 24 km² catchment is 9.12 × 10⁴ m³ of water.",
     "Storm 1's 38 mm over the 24 km² catchment is 9.12 × 10⁵ m³ of water.", "INT-SUBJ-001", "geography-depth-volume"),
    # intervals in words, and the label itself as an interval's subject
    ("c2/ge-p9c", "Storm 1 had a lag of ten hours.", "Storm 1 had a lag of twelve hours.", "INT-SUBJ-001", "geography-clock-interval"),
    ("c2/ge-p9c", "Storm 2 had a lag of five and a half hours.", "Storm 2 had a lag of four and a half hours.", "INT-SUBJ-001",
     "geography-clock-interval"),
    ("c2/ge-p9c", "Storm 2 peaked 5.5 h after its rainfall peak.", "Storm 2 peaked 4.5 h after its rainfall peak.", "INT-SUBJ-001",
     "geography-clock-interval"),
    ("c3/ge-t16", "The Christchurch aftershock struck a year and a half after the Darfield quake.",
     "The Christchurch aftershock struck about five and a half months after the Darfield quake.", "INT-SUBJ-001", "geography-event-relation"),
    ("c3/ge-t16", "The aftershock struck two years after the Darfield earthquake.", "The aftershock struck half a year after the Darfield earthquake.",
     "INT-SUBJ-001", "geography-event-relation"),
    # Language B: a share of a total, Spanish and English
    ("c1/sp-t14", "El 25 % de 80 es 30.", "El 25 % de 80 es 20.", "INT-SUBJ-001", "language-b-share"),
    ("c2/sp-t15", "El 25 % de los 80 alumnos, es decir 30 alumnos, estudia francés.", "El 25 % de los 80 alumnos, es decir 20 alumnos, estudia francés.",
     "INT-SUBJ-001", "language-b-share"),
    ("c1/sp-t14", "El veinticinco por ciento de ochenta es treinta.", "El veinticinco por ciento de ochenta es veinte.", "INT-SUBJ-001", "language-b-share"),
    ("c3/sp-t16", "Your provisional total is 75% of the available marks (21/30).", "Your provisional total is 70% of the available marks (21/30).",
     "INT-SUBJ-001", "language-b-share"),
    # a period 'desde' a year with a present perfect runs to today; the present perfect of a change
    ("c1/sp-t14", "Desde 2015 la población ha crecido un 36 %.", "Desde 2015 la población ha crecido un 26 %.", "INT-SUBJ-004", "language-b-dated-change"),
    ("c1/sp-t14", "Desde 2015 la población ha crecido un treinta y seis por ciento.", "Desde 2015 la población ha crecido un veintiséis por ciento.",
     "INT-SUBJ-004", "language-b-dated-change"),
    ("c1/sp-t14", "Desde 2015 el pueblo ha ganado 66 vecinos.", "Desde 2015 el pueblo ha ganado 56 vecinos.", "INT-SUBJ-004", "language-b-dated-change"),
    # a duration with its bracketed years
    ("c1/sp-t14", "La fibra óptica llegó diez años después del cierre de la escuela (de 2009 a 2021).",
     "La fibra óptica llegó doce años después del cierre de la escuela (de 2009 a 2021).", "INT-SUBJ-004", "language-b-dated-change"),
    # a year in Spanish words
    ("c1/sp-t14", "La fibra óptica llegó en dos mil veintidós.", "La fibra óptica llegó en dos mil veintiuno.", "INT-SUBJ-004", "language-b-supplied-figure"),
    # the speaker of a paraphrase in Spanish, and a cleft
    ("c3/sp-t16", "Tu abuelo dijo que los colores de las casas eran preciosos.", "Tu abuela dijo que los colores de las casas eran preciosos.",
     "INT-SUBJ-004", "language-b-quote-speaker"),
    ("c3/sp-t16", 'It is your grandmother who says that Tomás "puede quedarse en nuestra casa".',
     'It is your mother who says that Tomás "puede quedarse en nuestra casa".', "INT-SUBJ-004", "language-b-quote-speaker"),
    ("c3/sp-t16", "Es tu padre quien dice que Tomás puede quedarse en vuestra casa.", "Es tu madre quien dice que Tomás puede quedarse en vuestra casa.",
     "INT-SUBJ-004", "language-b-quote-speaker"),
    # the task's scenario in the same language, and a hyphenated count
    ("c3/sp-t16", "El intercambio duró dos semanas.", "El intercambio duró tres semanas.", "INT-SUBJ-004", "language-b-supplied-figure"),
    ("c3/sp-t16", "Pasaste cinco semanas en Valparaíso.", "Pasaste tres semanas en Valparaíso.", "INT-SUBJ-004", "language-b-supplied-figure"),
    ("c3/sp-t16", "You describe a two-week stay with the Rojas family.", "You describe a three-week stay with the Rojas family.", "INT-SUBJ-004",
     "language-b-supplied-figure"),
    # the course range of a Paper 1 task that sets none (a convention: a warning)
    ("c3/sp-t16", "The task sets a length of 300 to 450 words.", "The task sets a length of 250 to 400 words.", "INT-SUBJ-004",
     "language-b-word-range-claim"),
    # the model text's word count ('el texto modelo'; its noun left out after a range)
    ("c2/sp-t15", "El texto modelo tiene 300 palabras.", "El texto modelo tiene unas 500 palabras.", "INT-SUBJ-004", "language-b-word-count"),
    ("c2/sp-t15", "La consigna pide entre 450 y 600 palabras, y el texto modelo tiene 300.",
     "La consigna pide entre 450 y 600 palabras, y el texto modelo tiene unas 499.", "INT-SUBJ-004", "language-b-word-count"),
]


@pytest.mark.parametrize("name,faulty,_twin,code,family", MISSES)
def test_the_faulty_statement_is_named(name, faulty, _twin, code, family):
    found, checks, _e = _new(name, faulty)
    assert code in found and any(c[0].startswith(family) and c[1] == "COUNTEREXAMPLE" for c in checks), (faulty, found, checks)


@pytest.mark.parametrize("name,_faulty,twin,_code,family", MISSES)
def test_its_correct_twin_is_not_named(name, _faulty, twin, _code, family):
    found, checks, entailed = _new(name, twin)
    assert found == [] and checks == [], (twin, found, checks)
    if family not in _CHECKED_ON_MISMATCH_ONLY:
        assert any(c[0].startswith(family) for c in entailed), (twin, entailed)  # read and decided, not merely left unread


#: Readers that build a check only when the restated figure differs from its source (an agreeing restatement needs no problem).
_CHECKED_ON_MISMATCH_ONLY = frozenset(("geography-request-figure", "language-b-supplied-figure"))


@pytest.mark.parametrize("name", sorted(H.RECORDED))
def test_the_recorded_answers_still_draw_no_failed_check(name):
    rc = H.recorded(name)
    assert [c for c in H.checks(rc) if c[1] != "ENTAILED"] == [] and "BR-INTERNAL-001" not in H.codes(rc), (name, H.checks(rc), H.codes(rc))


def test_a_plot_inside_a_field_is_no_area_statement():
    # an area unit after two dimensions with no result word ('lies in a 3 km² field') is never read as their product
    found, checks, entailed = _new("c2/ge-p9c", "A plot 40 m by 25 m lies in a 3 km² field.")
    assert not any(c[0].startswith("geography-dimension-area") for c in checks + entailed), (checks, entailed)


#: Runs of the frames the c3e readers read, each about 20,000 characters.
C3E_RUNS = {
    "area results": "6.0 m by 1.8 m, giving 10.8 m², " * 640 + "x",
    "cross-sections": "6.0 m wide and 1.8 m deep, giving a cross-section of " * 380 + "x",
    "labelled differences": "The rainfall of Storm 2 was 2 mm lower than that of Storm 1 and " * 310 + "x",
    "from-to pairs": "about 5.3% lower than Storm 1's (from 38 mm to 36 mm), " * 370 + "x",
    "possessive figures": "Storm 1's 38 mm over 24 km² and " * 650 + "x",
    "powers of ten": "38 mm over 24 km² is 9.12 × 10⁵ m³ and " * 540 + "x",
    "word durations": "a lag of four and a half hours after a year and a half after " * 330 + "x",
    "shares": "El 25 % de los 80 alumnos, es decir 20 alumnos, y " * 420 + "x",
    "share fractions": "70% of the available marks (21/30) and " * 520 + "x",
    "since a year": "Desde 2015 la población ha crecido un 26 % y " * 440 + "x",
    "spanish paraphrases": "Es tu madre quien dice que Tomás puede quedarse. " * 410 + "x",
    "hyphenated counts": "a three-week stay and " * 900 + "x",
    "bracketed years": "doce años después (de 2009 a 2021) y " * 540 + "x",
    "year words": "llegó en dos mil veintiuno y " * 700 + "x",
    "model counts": "palabras, y el texto modelo tiene unas 499, " * 450 + "x",
}


@pytest.mark.parametrize("name", ["c2/ge-p9c", "c2/ge-t15", "c3/ge-t16", "c1/sp-t14", "c2/sp-t15", "c3/sp-t16"])
def test_the_c3e_readers_stay_linear(name):
    from epinoic_logic.branches import geography, language_b

    from ..adapters.hostile_inputs import bounded
    _answer, question, subject, agent, task_type, docs = H.RECORDED[name]
    build = geography._build if subject == "Geography" else language_b._build
    for label, text in C3E_RUNS.items():
        rep = H.report(subject, agent, text, task_type=task_type, docs=docs,
                       claims=[dict(claim_id="c1", claim_text=text[:3000] or "x", claim_role="point", materiality="material")])
        took, error = bounded(lambda t, rep=rep: build(rep, question), text)
        assert error is None and took < 5.0, (name, label, took, error)
