"""Attack round 8 of the c3c fix: the Geography and Language B items the round reproduced on the working tree, and the two items the push
check listed as still partial (a wrong Spanish percentage written with the euro sign or in number words; a Geography doubling time in the
70/r form), each with its expected value fixed here (the inputs are the round's own).

* Shared bracket reader: a figure that names something ("than Storm 1 did (12 − 4.5)", "Sites 1 and 2"), the denominator of a rate ("per
  10 minutes") or the maximum of a score ("21 out of 30") is no stated result: the stated figure is the one before it, so a wrong figure is
  named on itself. In a Spanish statement a point groups thousands in the bracket too ("1.038 ... (1.250 − 212)").
* Shared worked-line reader: working in brackets after a chain's result ("= 16.2 m³ s⁻¹ (10.8 × 1.5 = 17.2)") is its own equation.
* Geography: a per-cent change of a table row is relative (a share's change may be relative or in points); a period of two years is no
  value pair; a comparison stated before the pair it rests on ("15% lower ... (36 mm against 38 mm)", "(130 of 185)", "three times as
  deep as ... (10 km against 5 km)"); a multiple of two labelled figures of the request; a figure or a date of the request restated;
  a unit conversion; a formula in n with n given; a word count of the answer and a word figure credited to the request; a figure per
  person in energy units; a growth rate between two years with its pair after; a figure credited to a year table by the row's own
  words; a doubling time with any yearly rate (the 70/r form included); an earthquake's depth by its event.
* Language B: the change readers read a currency sign and Spanish number words; "opens with", "says", the byline, the closing question,
  a count of the model's proposals, of a text's paragraphs, stanzas and lines, of a form's occurrences, of a text's ordinals, of the
  answer's corrections by category; a speaker of a paraphrase or of unquoted words; a duration with a quoted form; a count across
  languages (a closed bilingual gloss); a paraphrase located at a line; an event's year in English or uncredited.
* Core figure reader: "56 vecinos más que en 2015" is a difference; a figure the text gives only for another time is no figure of this year.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import geography as G
from epinoic_logic.branches import language_b as L
from epinoic_logic.branches import quant as Q
from epinoic_logic.branches import worked as W

from . import d9d10_hub as H
from . import d9d10_texts as T


def _text(record: str) -> str:
    return getattr(T, record.split("/")[1].upper().replace("-", "_"))


def _variant(record: str, change) -> str:
    base = _text(record)
    if isinstance(change, tuple):
        assert change[0] in base
        return base.replace(change[0], change[1], 1)
    if change.startswith("@ins "):
        anchor = "Depth, distance, ground conditions and time of day therefore decided the impact within one high-income country."
        return base.replace(anchor, anchor + change[4:], 1)
    return base + "\n\n" + change


_BASE: dict = {}


def _new(record: str, change) -> tuple[list, list]:
    """The new error and warning findings and the new non-ENTAILED checks of a variant against its recorded answer."""
    if record not in _BASE:
        _BASE[record] = H.recorded(record)
    base = _BASE[record]
    rc = H.recorded(record, _variant(record, change))
    seen = {(f.code, f.message[:140]) for f in base.findings}
    findings = [(f.code, f.severity) for f in rc.findings if f.severity in ("error", "warning") and (f.code, f.message[:140]) not in seen]
    bad = [c for c in H.checks(base) if c[1] != "ENTAILED"]
    checks = [c for c in H.checks(rc) if c[1] != "ENTAILED" and c not in bad]
    return findings, checks


# (record, wrong, right, the prefix of the check that names the wrong one)
NAMED = [
    # shared bracket reader: labels, denominators, maxima, Spanish thousands
    ("c2/ge-p9c", "Storm 2 peaked 6.5 hours sooner after its rainfall peak than Storm 1 did (12 − 4.5).",
     "Storm 2 peaked 7.5 hours sooner after its rainfall peak than Storm 1 did (12 − 4.5).", "geography-worked"),
    ("c2/ge-p9c", "Storm 2 brought 3 mm less rain than Storm 1 (38 − 36).", "Storm 2 brought 2 mm less rain than Storm 1 (38 − 36).", "geography-worked"),
    ("c1/ge-t14", "Sites 1 and 2 together had 410 pedestrians per 10 minutes (214 + 186).",
     "Sites 1 and 2 together had 400 pedestrians per 10 minutes (214 + 186).", "geography-worked"),
    ("c3/sp-t16", "Your provisional total is 21 out of 30 (7 + 9 + 6).", "Your provisional total is 21 out of 30 (7 + 9 + 5).", "language-b-worked"),
    ("c1/sp-t14", "Valdeoca perdió 1.138 habitantes entre 1960 y 2015 (1.250 − 212).", "Valdeoca perdió 1.038 habitantes entre 1960 y 2015 (1.250 − 212).",
     "language-b-worked"),
    # shared worked-line reader
    ("c2/ge-p9c", ("Q = 10.8 m² × 1.5 m s⁻¹ = 16.2 m³ s⁻¹\n", "Q = 10.8 m² × 1.5 m s⁻¹ = 16.2 m³ s⁻¹ (10.8 × 1.5 = 17.2)\n"),
     ("Q = 10.8 m² × 1.5 m s⁻¹ = 16.2 m³ s⁻¹\n", "Q = 10.8 m² × 1.5 m s⁻¹ = 16.2 m³ s⁻¹ (10.8 × 1.5 = 16.2)\n"), "geography-worked"),
    # Geography
    ("c2/ge-t15", "Ostrel's population grew by about 26% between 2005 and 2025 (from 21.4 million to 24.9 million).",
     "Ostrel's population grew by about 16% between 2005 and 2025 (from 21.4 million to 24.9 million).", "geography-table-change"),
    ("c2/ge-t15", "Total primary energy supply rose by 38% between 2005 and 2025.", "Total primary energy supply rose by 28% between 2005 and 2025.",
     "geography-table-change"),
    ("c2/ge-t15", "Natural gas's share rose by about 60% between 2005 and 2025 (15% to 22%).",
     "Natural gas's share rose by about 47% between 2005 and 2025 (15% to 22%).", "geography-table-change"),
    ("c2/ge-t15", "Ostrel's population rose by 26.4% from 2005 to 2025.", "Ostrel's population rose by 16.4% from 2005 to 2025.", "geography-table-change"),
    ("c2/ge-p9c", "Rainfall was about 15% lower in Storm 2 than in Storm 1 (36 mm against 38 mm).",
     "Rainfall was about 5% lower in Storm 2 than in Storm 1 (36 mm against 38 mm).", "geography-pair-comparison"),
    ("c2/ge-p9c", "Storm 2's peak discharge was two and a half times that of Storm 1.", "Storm 2's peak discharge was three times that of Storm 1.",
     "geography-pair-comparison"),
    ("c2/ge-p9c", "The gauging station at Marsh Lane Bridge drains a catchment of 42 km².",
     "The gauging station at Marsh Lane Bridge drains a catchment of 24 km².", "geography-request-figure"),
    ("c2/ge-p9c", "Storm 1 fell on 21 October 2006.", "Storm 1 fell on 14 October 2006.", "geography-request-figure"),
    ("c2/ge-p9c", "Storm 1's lag time of 12 hours is 620 minutes.", "Storm 1's lag time of 12 hours is 720 minutes.", "geography-conversion"),
    ("c2/ge-t15", "In 2025 Ostrel's energy supply per person was about 48 GJ (1,050 PJ ÷ 24.9 million people).",
     "In 2025 Ostrel's energy supply per person was about 42 GJ (1,050 PJ ÷ 24.9 million people).", "geography-per-capita"),
    ("c2/ge-t15", "Total primary energy supply grew at an average annual rate of about 2.4% between 2005 and 2025 (820 PJ to 1,050 PJ).",
     "Total primary energy supply grew at an average annual rate of about 1.2% between 2005 and 2025 (820 PJ to 1,050 PJ).", "geography-growth-rate"),
    ("c2/ge-t15", "According to the table, 45% of supply was imported in 2025.", "According to the table, 54% of supply was imported in 2025.",
     "geography-table-figure"),
    ("c1/ge-t14", "With six pairs, n³ − n = 216.", "With six pairs, n³ − n = 210.", "geography-n-formula"),
    ("c3/ge-t16", "@ins  The aftershock was 1.9 magnitude units smaller than the Darfield earthquake (6.2 against 7.1).",
     "@ins  The aftershock was 0.9 magnitude units smaller than the Darfield earthquake (6.2 against 7.1).", "geography-pair-comparison"),
    ("c3/ge-t16", "@ins  At least 80% of the aftershock's deaths came in the two collapsed buildings (130 of 185).",
     "@ins  At least 70% of the aftershock's deaths came in the two collapsed buildings (130 of 185).", "geography-pair-comparison"),
    ("c3/ge-t16", "@ins  At about 15 km deep, the aftershock was half as deep as the Darfield earthquake.",
     "@ins  At about 5 km deep, the aftershock was half as deep as the Darfield earthquake.", "geography-case-consistency"),
    ("c3/ge-t16", "@ins  Darfield's epicentre lay about 25 km further from its main city than Haiti's did (40 km against 25 km).",
     "@ins  Darfield's epicentre lay about 15 km further from its main city than Haiti's did (40 km against 25 km).", "geography-pair-comparison"),
    ("c3/ge-t16", "The Darfield earthquake was about three times as deep as the aftershock (10 km against 5 km).",
     "The Darfield earthquake was about twice as deep as the aftershock (10 km against 5 km).", "geography-pair-comparison"),
    ("c3/ge-t16", "(Word count: about 950.)", "(Word count: about 520.)", "geography-word-count"),
    ("c3/ge-t16", "(About 800 words.)", "(About 500 words.)", "geography-word-count"),
    ("c1/ge-t14", "Your analysis and conclusion together should stay close to the 1,900 words you planned.",
     "Your analysis and conclusion together should stay close to the 900 words you planned.", "geography-request-figure"),
    # the push check's 70/r doubling forms
    ("c2/ge-t15", "Doubling time = 70/r = 25 years for r = 2.", "Doubling time = 70/r = 35 years for r = 2.", "geography-doubling-time"),
    ("c2/ge-t15", "At 2% a year the population doubles in 25 years (rule of 70).", "At 2% a year the population doubles in 35 years (rule of 70).",
     "geography-doubling-time"),
    ("c2/ge-t15", "Total primary energy supply grew by about 1.2% a year; at that rate it would take 48 years to double.",
     "Total primary energy supply grew by about 1.2% a year; at that rate it would take 58 years to double.", "geography-doubling-time"),
    ("c2/ge-t15", "Total primary energy supply grew by about 1.2% a year, so it would double in roughly 48 years.",
     "Total primary energy supply grew by about 1.2% a year, so it would double in roughly 58 years.", "geography-doubling-time"),
    # Language B: the push check's euro sign and number words
    ("c2/sp-t15", "El alquiler medio pasó de 600 € a 900 €, una subida del 30 %.", "El alquiler medio pasó de 600 € a 900 €, una subida del 50 %.",
     "language-b-percent-change"),
    ("c2/sp-t15", "El alquiler medio pasó de €600 a €900, una subida del 30 %.", "El alquiler medio pasó de €600 a €900, una subida del 50 %.",
     "language-b-percent-change"),
    ("c2/sp-t15", "El alquiler medio pasó de seiscientos a novecientos euros, una subida del treinta por ciento.",
     "El alquiler medio pasó de seiscientos a novecientos euros, una subida del cincuenta por ciento.", "language-b-percent-change"),
    # Language B round-8 misses
    ("c2/sp-t15", "The article opens with \"Cada año, nuestra ciudad se llena de turistas\".", None, "language-b-quoted-form"),
    ("c2/sp-t15", "The closing question addresses the reader as usted (\"¿Y usted qué opina?\").",
     "The closing question addresses the reader as tú (\"¿Y tú qué opinas?\").", "language-b-address-form"),
    ("c2/sp-t15", "The model says the terraces stay open \"hasta las cuatro de la madrugada\".",
     "The model says the terraces stay open \"hasta las tres de la madrugada\".", "language-b-quoted-form"),
    ("c2/sp-t15", "The byline names Marta Ruiz Pérez as the author.", "The byline names Marta Ruiz Salas as the author.", "language-b-quoted-form"),
    ("c2/sp-t15", "The article proposes three measures.", "The article proposes two measures.", "language-b-listed-count"),
    ("c1/sp-t14", "In 1960 Valdeoca had three bakeries.", "In 1960 Valdeoca had two bakeries.", "language-b-supplied-figure"),
    ("c1/sp-t14", "The school had been closed since 2003.", "The school had been closed since 2009.", "language-b-supplied-figure"),
    ("c1/sp-t14", "La fibra óptica llegó en 2012.", "La fibra óptica llegó en 2021.", "language-b-supplied-figure"),
    ("c1/sp-t14", ("1. 1.250 habitantes en 1960 y 212 vecinos en 2015.", "1. 1.250 habitantes en 1960 y 268 vecinos en 2015."), None, "core-figure"),
    ("c3/sp-t16", "Daniel volvió a Inglaterra hace tres semanas.", "Daniel volvió a Inglaterra hace dos semanas.", "language-b-supplied-figure"),
    ("c3/sp-t16", "Tu correo da cuatro cosas que aprendiste.", "Tu correo da tres cosas que aprendiste.", "language-b-listed-count"),
    ("c3/sp-t16", "In your email your father says that Tomás can stay at your house.",
     "In your email your mother says that Tomás can stay at your house.", "language-b-quote-speaker"),
    ("c3/sp-t16", "In your email your grandmother says that Tomás can stay at your house.", None, "language-b-quote-speaker"),
    ("c3/sp-t16", ("subjunctive after wish and hope phrases (two)", "subjunctive after wish and hope phrases (three)"), None, "language-b-listed-count"),
    ("c3/sp-t16", "There are six corrections above: four for agreement, two for the subjunctive and one for ser/estar.",
     "There are six corrections above: three for agreement, two for the subjunctive and one for ser/estar.", "language-b-listed-count"),
    ("c3/sp-t16", "Your email has seven paragraphs between the greeting and the sign-off.",
     "Your email has five paragraphs between the greeting and the sign-off.", "language-b-structure-count"),
    ("c3/sp-p10d", "\"¡Ojo, que quema!\" is said by Doña Celia.", "\"¡Ojo, que quema!\" is said by Rubén.", "language-b-quote-speaker"),
    ("c3/sp-p10d", "The poem has five stanzas.", "The poem has four stanzas.", "language-b-structure-count"),
    ("c3/sp-p10d", "The poem has twenty lines in four stanzas of six lines.", "The poem has twenty lines in four stanzas of five lines.",
     "language-b-structure-count"),
    ("c3/sp-p10d", "The narrator was \"el nuevo\" for a month.", "The narrator was \"el nuevo\" for a week.", "language-b-supplied-figure"),
    ("c3/sp-p10d", "\"ándale\" appears three times in a row in the poem.", "\"ándale\" appears twice in a row in the poem.", "language-b-occurrence-count"),
    ("c3/sp-p10d", "El narrador aprendió tres palabras al quemarse la mano.", "El narrador aprendió dos palabras al quemarse la mano.",
     "language-b-supplied-figure"),
    ("c3/sp-p10d", "The narrator puts a whole arm into the oven in the last line.", "The narrator puts a whole arm into the sink in the last line.",
     "language-b-quoted-form"),
]


@pytest.mark.parametrize("record, wrong, right, prefix", NAMED)
def test_a_wrong_statement_is_named_and_its_correct_twin_is_not(record, wrong, right, prefix):
    findings, checks = _new(record, wrong)
    assert any(c[0].startswith(prefix) and c[1] == "COUNTEREXAMPLE" for c in checks), (wrong, checks)
    assert findings, wrong
    if right is not None:
        assert _new(record, right) == ([], []), right


# correct statements that drew a finding: the boundary frames (each must stay free of any new error or warning)
FREE = [
    ("c1/sp-t14", "Valdeoca perdió 1.038 habitantes entre 1960 y 2015 (1.250 − 212)."),  # the regression: Spanish thousands in the bracket
    ("c1/sp-t14", "La población bajó en 1.038 personas entre 1960 y 2015 (1.250 − 212)."),
    ("c2/ge-p9c", "Peak discharge rose by 10.8 m³ s⁻¹ in Storm 2 (16.2 − 5.4)."),
    ("c2/ge-p9c", "At its peak, Storm 2's discharge was 15.1 m³ s⁻¹ above its base flow (16.2 − 1.1)."),
    ("c2/ge-t15", "Ostrel's population rose by about 16% from 2005 to 2025."),
    ("c1/sp-t14", "Hoy hay 56 vecinos más que en 2015 (268 − 212)."),
    ("c1/ge-t14", "For your ten sites, n³ − n = 10³ − 10 = 990."),
    ("c1/sp-t14", "La fibra óptica llegó seis años después de 2015."),  # a year as the reference of a relative date is no event year
    ("c3/sp-t16", "El intercambio duró tres semanas."),  # a count of another event than the text's "hace dos semanas que volví"
    ("c3/sp-t16", "You spent three weeks, or twenty-one days, with the family."),
    ("c3/sp-t16", ('- "El primer semana fue difícil" → "La primera semana fue difícil" (semana',
                   '- Wrong: "El primer semana fue difícil". Right: "La primera semana fue difícil" (semana')),
]


@pytest.mark.parametrize("record, change", FREE)
def test_a_correct_statement_draws_no_new_check_failure(record, change):
    findings, checks = _new(record, change)
    assert checks == [], (change, checks)
    # (the subject checks' findings; INT-REQ-003, CORE-SELF-001 and INT-ARG-001 belong to the channel, the shared gate and the argument
    # diagnostics, handed over by this fix)
    assert [f for f in findings if f[0].startswith("INT-SUBJ")] == [], (change, findings)


def test_the_bracket_reader_takes_the_figure_before_a_label_as_the_stated_result():
    reads = W._breakdown_reads("Storm 2 peaked 6.5 hours sooner after its rainfall peak than Storm 1 did (12 − 4.5).")
    assert [r[0] for r in reads] == ["6.5 hours sooner after its rainfall peak than Storm 1 did (12 − 4.5)"]
    assert [r[0] for r in W._breakdown_reads("Your provisional total is 21 out of 30 (7 + 9 + 5).")] == ["21 out of 30 (7 + 9 + 5)"]
    assert W._breakdown_reads("Site 4 (12 + 3) had a high score.") == []


def test_working_in_brackets_after_a_chain_result_is_an_equation_of_its_own():
    eqs = [w.phrase for w in Q.worked_equations("Q = 10.8 m² × 1.5 m s⁻¹ = 16.2 m³ s⁻¹ (10.8 × 1.5 = 17.2)")]
    assert eqs == ["10.8 m² × 1.5 m s⁻¹ = 16.2 m³ s⁻¹", "10.8 × 1.5 = 17.2"]


def test_spanish_figures_are_normalised_for_the_change_readers():
    assert L._normalise_es_figures("pasó de 600 € a 900 €, una subida del 30 %.") == "pasó de 600 a 900 , una subida del 30 %."
    assert L._normalise_es_figures("pasó de seiscientos a novecientos euros, una subida del treinta por ciento.") == \
        "pasó de 600 a 900 euros, una subida del 30 %."


# ---------------------------------------------------------------------------------------------------- linearity (not a stress test)
def _cpu(fn) -> float:
    best = None
    for _ in range(2):
        t = time.process_time()
        fn()
        dt = time.process_time() - t
        best = dt if best is None else min(best, dt)
    return best


def _short(text: str) -> list:
    """One claim holding the answer's first 200 characters (a claim's text is at most 4,000 characters)."""
    return [dict(claim_id="c1", claim_text=text[:200], claim_role="point", materiality="material")]


def _fill(unit: str, n: int) -> str:
    return (unit * (n // len(unit) + 1))[:n]


@pytest.mark.parametrize("unit", ["a" * 50 + "1 ", "Rainfall was 15% lower in Storm 2 than in Storm 1 (36 mm against 38 mm) ",
                                  "7.5 hours sooner than Storm 1 did per 10 minutes out of 30 (7 + 9 + 5) ", "12 hours is 620 minutes n³ − n = 216 ",
                                  "grew by 1.2% a year, it would take 48 years to double r = 2 "])
def test_the_new_geography_readers_are_linear_on_one_long_sentence(unit):
    facts, dates = G._request_facts(T.GE_P9C_Q)

    def run(n: int):
        text = _fill(unit, n)
        rep = H.report("Geography", "geography-specialist", text, claims=_short(text))
        ctx = G._Ctx(rep, [], [], set(), {})
        s = G._Sentence(1, 1, text, "")
        return lambda: [G._pair_comparison(ctx, s), G._conversion(ctx, s), G._n_formula(ctx, s), G._request_figures(ctx, s, facts, dates),
                        G._labelled_fold(ctx, s, facts, {}), G._doubling(ctx, s), G._from_to_percent(ctx, s), W._breakdown_reads(text),
                        Q.worked_equations(text)]
    small = _cpu(run(25_000))
    large = _cpu(run(200_000))
    assert large < max(0.05, small) * 16, (unit[:30], small, large)  # (a quadratic reader gives about 64 for 8 times the text)


@pytest.mark.parametrize("unit", ["The poem has twenty lines in four stanzas of six lines \"ándale\" appears three times in a row in the poem ",
                                  "four for agreement, two for the subjunctive and one for ser/estar agreement (three) ",
                                  "your father says that Tomás can stay at your house \"¡Ojo, que quema!\" is said by Doña Celia ",
                                  "three bakeries tres palabras hace tres semanas for a month in the last line ",
                                  "pasó de seiscientos € a novecientos €, una subida del treinta por ciento "])
def test_the_new_language_b_readers_are_linear(unit):
    def run(n: int, tt: str, docs, req: str):
        text = _fill(unit, n)
        rep = H.report("Language B: Spanish", "language-b-spanish-specialist", text, task_type=tt, docs=docs, claims=_short(text))
        task = L.classify_task(rep, req)
        regions = L.model_regions(text, task=task, supplied=tuple(rep.supplied_texts), request_text=req, spanish_context=True)
        ctx = L._Ctx(rep, req, task, regions, text)
        st = L._statements(regions, text)
        return lambda: [L._structural_counts(ctx, st), L._occurrence_counts(ctx, st), L._enumerated_counts(ctx, st), L._category_counts(ctx, st),
                        L._paraphrase_speakers(ctx, st), L._unquoted_speakers(ctx, st), L._quote_durations(ctx, st), L._cross_counts(ctx),
                        L._line_paraphrases(ctx, st), L._percent_changes(ctx), L._event_years(ctx)]
    for tt, docs, req in (("marking_feedback", (T.SP_T16_DOC,), T.SP_T16_Q), ("language_notes", (T.SP_P10D_DOC,), T.SP_P10D_Q)):
        small = _cpu(run(25_000, tt, docs, req))
        large = _cpu(run(200_000, tt, docs, req))
        assert large < max(0.05, small) * 16, (unit[:30], tt, small, large)
