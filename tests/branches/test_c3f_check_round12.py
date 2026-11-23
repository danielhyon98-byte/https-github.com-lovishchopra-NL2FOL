"""Follow-up c3f, check round 12 (the check fixer) on the Geography and Language B branches, each expected value fixed here.

A wrong figure is never ENTAILED and a correct one never a counterexample:

* regressions of the c3f row index: 'a 28% share and supplied 294.0 PJ' never names the imported share's row ('share' before 'and'
  and a verb continues no list of rows); a numeric apposition between the row and its verb ('Nuclear power, which had a 4% share,
  supplied 63.0 PJ') no longer drops the subject's row, so the wrong PJ figure is charged again;
* a stated difference of two printed cells is checked against the printed cells (13 − 1 = 12, so 11 is wrong), never within the
  cells' own rounding band;
* every change of a sentence is read with its own clause's column; a figure is read with the column its own clause names;
* 'per person, 1,050 PJ shared among 24.9 million people, was about 42 GJ': the figure after the comma is the total divided;
* a cue fronted after 'and,' ('and, after coal declined, about 42 GJ in 2025') orders no two years of the sentence;
* the request's peak times restated wrongly, in a sentence or in a worked difference of times, are named;
* from-to per cents of a share row named by its head take the table's two years;
* Language B: a figure of a line about the present ('Hoy ...') is the text's present one; a figure with its noun elided after a
  coordinated figure ('... a 268 en 2015') is read with that noun, and a population figure under another of its nouns;
* the stall of the change reader: linear in the sentence.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import time

import pytest

from . import d9d10_hub as H

_BASE: dict = {}


def _new(name: str, sentence: str, *, inplace: tuple[str, str] | None = None):
    """(new error and warning codes, new non-entailed checks, new entailed checks) of the recorded answer with ``sentence`` appended
    (or with ``inplace`` = (old, new) replaced)."""
    if name not in _BASE:
        _BASE[name] = H.recorded(name)
    b = _BASE[name]
    ans = H.RECORDED[name][0]
    if inplace is not None:
        assert ans.count(inplace[0]) == 1
        text = ans.replace(*inplace)
    else:
        text = ans + "\n\n" + sentence
    rc = H.recorded(name, text)
    old = {(f.code, f.severity, f.message[:140]) for f in b.findings}
    new = [f.code for f in rc.findings if f.severity in ("error", "warning") and (f.code, f.severity, f.message[:140]) not in old]
    old_checks = H.checks(b)
    checks = [c for c in H.checks(rc) if c[1] != "ENTAILED" and c not in old_checks]
    entailed = [c for c in H.checks(rc) if c[1] == "ENTAILED" and c not in old_checks]
    return new, checks, entailed


def _fam(checks, prefix):
    return [c for c in checks if c[0].startswith(prefix)]


@pytest.mark.parametrize("sentence", [
    "Coal had a 28% share and supplied 294.0 PJ in 2025.",
    "Oil kept a 27% share and supplied 283.5 PJ in 2025.",
    "Nuclear power's share and supply both grew: it supplied 42.0 PJ in 2025.",
    "Nuclear power, which had a 4% share, supplied 42.0 PJ in 2025.",
    "In 2025 nuclear power, which had a 4% share, supplied 42.0 PJ.",
    "The share of wind and solar power rose by 12 percentage points.",
    "The share of supply that is imported rose from 38% to 54%.",
    "Energy supply per person, 1,050 PJ shared among 24.9 million people, was about 42 GJ in 2025.",
    "Energy supply per person was about 38 GJ in 2005 and, after coal declined, about 42 GJ in 2025.",
])
def test_ge_t15_correct_figures_draw_no_counterexample(sentence):
    new, checks, entailed = _new("c2/ge-t15", sentence)
    assert checks == [] and new == [], (checks, new)
    assert entailed, sentence  # (each is checked, not left unread)


@pytest.mark.parametrize("sentence, family, code", [
    ("Nuclear power, which had a 4% share, supplied 63.0 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("Nuclear power, with a 4% share, supplied 63.0 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("Nuclear power, at 4%, supplied 63.0 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("Coal, which had a 28% share, supplied 377.2 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("Oil, at 27% of the mix, supplied 294.0 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("Hydroelectric power (6% in 2025) supplied 41.0 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("Imported energy, at 54% of supply, was 294.0 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("In 2025 nuclear power, which had a 4% share, supplied 63.0 PJ.", "geography-table-derived", "INT-SUBJ-004"),
    ("Wind and solar power, 13% of the total, supplied 42.0 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("The share of supply that is imported rose from 38% to 46%.", "geography-table-derived", "INT-SUBJ-004"),
    ("The imported share rose from 38% to 46%.", "geography-table-derived", "INT-SUBJ-004"),
    ("The share of wind and solar power rose by 11 percentage points.", "geography-table-change", "INT-SUBJ-001"),
    ("The imported share rose by 15 percentage points between 2005 and 2025.", "geography-table-change", "INT-SUBJ-001"),
    ("The coal share fell by 17 percentage points.", "geography-table-change", "INT-SUBJ-001"),
    ("The share of oil fell by 3 percentage points between 2005 and 2025.", "geography-table-change", "INT-SUBJ-001"),
    ("Ostrel's population grew by 3.6 million between 2005 and 2025.", "geography-table-change", "INT-SUBJ-001"),
])
def test_ge_t15_wrong_figures_are_charged_never_entailed(sentence, family, code):
    new, checks, entailed = _new("c2/ge-t15", sentence)
    assert ("COUNTEREXAMPLE" in {c[1] for c in _fam(checks, family)}) and code in new, (checks, new)
    if family == "geography-table-change":
        assert _fam(entailed, family) == [], entailed


def test_ge_t15_a_wrong_per_capita_figure_after_a_shared_total_is_charged():
    new, checks, _e = _new("c2/ge-t15", "Energy supply per person, 1,050 PJ shared among 24.9 million people, was about 52 GJ in 2025.")
    assert ("geography-per-capita-1", "COUNTEREXAMPLE") in checks and "INT-SUBJ-001" in new


def test_ge_t14_every_change_is_read_with_its_own_column():
    new, checks, entailed = _new("c1/ge-t14", "Pedestrian counts fell by 195 from Site 1 to Site 10, while the EQS fell by 3 points.")
    assert [c[1] for c in _fam(checks, "geography-supplied-figure")] == ["COUNTEREXAMPLE"] and "INT-SUBJ-004" in new
    assert len(_fam(entailed, "geography-supplied-figure")) == 1
    new, checks, entailed = _new("c1/ge-t14", "Pedestrian counts fell by 195 from Site 1 to Site 10, while the EQS fell by 13 points.")
    assert checks == [] and new == [] and len(_fam(entailed, "geography-supplied-figure")) == 2


@pytest.mark.parametrize("sentence, ok", [
    ("The pedestrian count at site 4 was 97, and the EQS fell by 13 points from Site 1 to Site 10.", True),
    ("The pedestrian count at site 4 was 97.", True),
    ("The pedestrian count at site 4 was 151.", False),
    ("The EQS at Site 4 was 22.", False),
])
def test_ge_t14_a_figure_takes_the_column_its_own_clause_names(sentence, ok):
    new, checks, entailed = _new("c1/ge-t14", sentence)
    if ok:
        assert checks == [] and new == [] and entailed
    else:
        assert "COUNTEREXAMPLE" in {c[1] for c in checks} and "INT-SUBJ-004" in new


@pytest.mark.parametrize("sentence, wrong", [
    ("Storm 1 peaked at 22:30.", True),
    ("Storm 1 peaked at 21:30.", False),
    ("Storm 2 peaked at 15:00, 4.5 hours after the peak rainfall.", True),
    ("Storm 2 peaked at 14:00, 4.5 hours after the peak rainfall.", False),
    ("In Storm 1 the river peaked at 20:30.", True),
    ("In Storm 1 the rainfall peaked at 09:30.", False),
    ("In Storm 1 the rainfall peaked at 21:30.", True),
])
def test_ge_p9c_a_peak_time_restated_from_the_request_is_checked(sentence, wrong):
    new, checks, _e = _new("c2/ge-p9c", sentence)
    if wrong:
        assert ("geography-request-figure-1", "COUNTEREXAMPLE") in checks and "INT-SUBJ-004" in new, (checks, new)
    else:
        assert checks == [] and new == [], (checks, new)


def test_ge_p9c_a_misread_time_in_a_worked_difference_is_named():
    new, checks, _e = _new("c2/ge-p9c", "", inplace=("Storm 1: 21:30 − 09:30 = 12 hours", "Storm 1: 22:30 − 09:30 = 13 hours"))
    assert ("geography-request-figure-1", "COUNTEREXAMPLE") in checks and "INT-SUBJ-004" in new


@pytest.mark.parametrize("sentence, wrong", [
    ("Hoy, con 268 vecinos, la escuela tiene cien alumnos.", True),
    ("Hoy, con 268 vecinos, la escuela tiene catorce alumnos.", False),
    ("La población pasó de 1.250 habitantes en 1960 a 268 en 2015.", True),
    ("La población pasó de 1.250 habitantes en 1960 a 212 en 2015.", False),
])
def test_sp_t14_present_and_elided_figures_are_read_against_their_cell(sentence, wrong):
    new, checks, entailed = _new("c1/sp-t14", sentence)
    if wrong:
        assert "COUNTEREXAMPLE" in {c[1] for c in _fam(checks, "language-b-supplied-figure")} and "INT-SUBJ-004" in new, (checks, new)
    else:
        assert checks == [] and new == [] and len(_fam(entailed, "language-b-supplied-figure")) >= 1, (checks, new, entailed)


def test_sp_t14_a_number_word_with_its_noun_elided_is_read():
    old = "1. 1.250 habitantes en 1960 y 212 vecinos en 2015."
    new, checks, _e = _new("c1/sp-t14", "", inplace=(old, "1. 1.250 habitantes en 1960 y doscientos veintiuno en 2015."))
    assert "COUNTEREXAMPLE" in {c[1] for c in _fam(checks, "language-b-supplied-figure")} and "INT-SUBJ-001" in new
    new, checks, _e = _new("c1/sp-t14", "", inplace=(old, "1. 1.250 habitantes en 1960 y doscientos doce en 2015."))
    assert checks == [] and new == []


@pytest.mark.parametrize("line", [
    '- You wrote "El primer semana fue difícil"; write "La primera semana fue difícil" instead (semana',
    '- Escribiste «El primer semana fue difícil»; escribe «La primera semana fue difícil» (semana',
])
def test_sp_t16_a_you_wrote_line_counts_as_a_correction_line(line):
    new, checks, _e = _new("c3/sp-t16", "", inplace=('- "El primer semana fue difícil" → "La primera semana fue difícil" (semana', line))
    assert checks == [] and new == [], (checks, new)


def test_the_change_by_reader_stays_linear():
    # check round 12 of c3f (a stall): 'the coal share fell by 18 percentage points, ' * k searched the whole sentence once per change
    # (1.95, 7.11 and 28.8 s at 25k, 50k and 100k characters); whether the sentence states a period is now decided once
    from epinoic_logic.branches import geography
    _answer, question, subject, agent, task_type, docs = H.RECORDED["c2/ge-t15"]
    took = []
    unit = "the coal share fell by 18 percentage points, "
    for n in (20_000, 40_000):
        text = "In short, " + (unit * (n // len(unit) + 1))[:n] + "."
        rep = H.report(subject, agent, text, task_type=task_type, docs=docs,
                       claims=[dict(claim_id="c1", claim_text=text[:3000], claim_role="point", materiality="material")])
        t0 = time.process_time()
        geography._build(rep, question)
        took.append(time.process_time() - t0)
    assert took[1] < 5.0 and took[1] <= 3 * max(took[0], 0.2), took


@pytest.mark.parametrize("name, sentence, wrong", [
    # an area of a part of the catchment, and another object's dimensions, are no restatement of the request's figure
    ("c2/ge-p9c", "The built-up area of the 24 km² catchment was about 1.9 km² in 2006.", False),
    ("c2/ge-p9c", "The built-up area was about 1.9 km² of the catchment in 2006.", False),
    ("c2/ge-p9c", "The bridge is 12 m long and 3 m wide, which is small for a 24 km² catchment.", False),
    ("c2/ge-p9c", "The channel was 1.6 m deep.", True),
    ("c2/ge-p9c", "The channel was 7.0 m wide.", True),
    ("c2/ge-p9c", "The river drains a catchment of 42 km².", True),
    # each count read against its own clause's noun and event
    ("c3/sp-t16", "You returned to England two weeks ago, after an exchange of three weeks.", False),
    ("c3/sp-t16", "You returned to England three weeks ago, after an exchange of three weeks.", True),
    ("c3/sp-t16", "You returned to England two weeks ago, after an exchange of two weeks.", True),
])
def test_a_figure_of_another_thing_draws_no_counterexample_and_a_misread_one_does(name, sentence, wrong):
    new, checks, _e = _new(name, sentence)
    if wrong:
        assert "COUNTEREXAMPLE" in {c[1] for c in checks} and "INT-SUBJ-004" in new, (checks, new)
    else:
        assert checks == [] and new == [], (checks, new)


@pytest.mark.parametrize("name, sentence, family, wrong", [
    # a difference and a multiple of one column between two rows of the supplied attribute table (ge-t14: 186 − 151 = 35; 214 / 19 = 11.3)
    ("c1/ge-t14", "Site 2 had 28 more pedestrians per 10 minutes than Site 3.", "geography-supplied-figure", True),
    ("c1/ge-t14", "Site 2 had 35 more pedestrians per 10 minutes than Site 3.", "geography-supplied-figure", False),
    ("c1/ge-t14", "Pedestrian counts at Site 1 were about fifteen times those at Site 10.", "geography-supplied-figure", True),
    ("c1/ge-t14", "Pedestrian counts at Site 1 were about eleven times those at Site 10.", "geography-supplied-figure", False),
    # a figure stated as a multiple of another figure the sentence writes (ge-t16: 300,000 / 185 = 1,622)
    ("c3/ge-t16", "The Haitian government's estimate of 300,000 deaths is about 160 times Christchurch's 185.", "geography-times-pair", True),
    ("c3/ge-t16", "The Haitian government's estimate of 300,000 deaths is about 1,600 times Christchurch's 185.", "geography-times-pair", False),
    # a part stated with its share of the whole and the whole (ge-p9c: 8% of 24 km² is 1.92 km²)
    ("c2/ge-p9c", "In 2006, 8% of the 24 km² catchment, about 2.9 km², was built up.", "geography-share-part", True),
    ("c2/ge-p9c", "In 2006, 8% of the 24 km² catchment, about 1.9 km², was built up.", "geography-share-part", False),
])
def test_a_comparison_of_two_rows_or_two_stated_figures_is_checked(name, sentence, family, wrong):
    new, checks, entailed = _new(name, sentence)
    if wrong:
        assert [c[1] for c in _fam(checks, family)] == ["COUNTEREXAMPLE"] and new, (checks, new)
    else:
        assert checks == [] and new == [] and len(_fam(entailed, family)) == 1, (checks, new, entailed)
