"""Check round 11 of the c3e follow-up on the Geography and Language B branches (the check fixer), each expected value fixed here.

A wrong figure is never ENTAILED and a correct one never a counterexample:

* Geography, intervals in words: "twelve and a half hours" is read to the half hour (as "12.5 hours" is) and a whole hour never covers
  a true half hour from both sides ("four hours" and "five hours" for a true 4.5 hours), so each is a counterexample.
* Geography, areas: a result verb ("so", "giving", "which is") binds only the area figure that is its own object ("giving 12.8 m²",
  "so the area is 12.8 m²"), never an area figure inside another phrase ("so the catchment of 24 km² drains ...").
* Geography, a change of an AMOUNT of a share row's item ("Energy from oil fell by about 13% ...") is checked against the share ×
  the total of each year, never against the share itself.
* Geography, the row of a derived figure is the one its own clause names ("total energy supply", "Imported energy, mostly oil and
  gas, was ..."), never a row named in a contrast or a comparison ("Although population grew, ...", "..., faster than population").
* Geography, a figure in a unit of measure the table's cell does not state ("about 42 GJ" per person against a total in PJ) is no
  reading of that cell.
* Language B, a share's part is a number of the same total: never a year, an age, a rating or a count of another noun.
* Language B, a person's age is no duration of the bracketed years.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

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
    old_checks = [c for c in H.checks(b) if c[1] != "ENTAILED"]
    checks = [c for c in H.checks(rc) if c[1] != "ENTAILED" and c not in old_checks]
    entailed = [c for c in H.checks(rc) if c[1] == "ENTAILED" and c not in H.checks(b)]
    return new, checks, entailed


#: (record, faulty statement, its check family, finding code); each faulty statement draws a COUNTEREXAMPLE of that family.
FAULTY = [
    ("c2/ge-p9c", "Storm 1 had a lag of twelve and a half hours.", "geography-clock-interval", "INT-SUBJ-001"),
    ("c2/ge-p9c", "Storm 1 had a lag of eleven and a half hours.", "geography-clock-interval", "INT-SUBJ-001"),
    ("c2/ge-p9c", "Storm 2 had a lag of four hours.", "geography-clock-interval", "INT-SUBJ-001"),
    ("c2/ge-p9c", "Storm 2 had a lag of five hours.", "geography-clock-interval", "INT-SUBJ-001"),
    ("c2/ge-p9c", "Storm 2 peaked 4 hours after its rainfall peak.", "geography-clock-interval", "INT-SUBJ-001"),
    ("c2/ge-p9c", "The channel measures 6.0 m by 1.8 m, giving 12.8 m².", "geography-dimension-area", "INT-SUBJ-001"),
    ("c2/ge-p9c", "The channel measures 6.0 m by 1.8 m, so the area is 12.8 m².", "geography-dimension-area", "INT-SUBJ-001"),
    ("c2/ge-t15", "Energy from oil fell by about 13% between 2005 and 2025.", "geography-table-change", "INT-SUBJ-001"),
    ("c2/ge-t15", "The amount of energy from coal fell by about 39% between 2005 and 2025.", "geography-table-change", "INT-SUBJ-001"),
    ("c2/ge-t15", "The amount of energy from natural gas rose by about 47% between 2005 and 2025.", "geography-table-change",
     "INT-SUBJ-001"),
    ("c2/ge-t15", "Although population grew, total energy supply showed a relative rise of about 16%.", "geography-table-derived",
     "INT-SUBJ-004"),
    ("c2/ge-t15", "Total supply showed a relative rise of about 16%, faster than population.", "geography-table-derived",
     "INT-SUBJ-004"),
    ("c2/ge-t15", "Imported energy, mostly oil and gas, was about 283.5 PJ in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "Each Ostrel resident used about 52 GJ of primary energy in 2025.", "geography-table-derived", "INT-SUBJ-004"),
    ("c2/ge-t15", "The imported share rose by 16 percentage points, a relative rise of about 16%.", "geography-table-derived",
     "INT-SUBJ-004"),
    ("c1/sp-t14", "El 25 % de 80 es 30.", "language-b-share", "INT-SUBJ-001"),
    ("c2/sp-t15", "Vivió diez años en Bogotá (de 2009 a 2021).", "language-b-dated-change", "INT-SUBJ-004"),
]
#: (record, correct statement, the check family that must hold no counterexample for it, whether that family must be ENTAILED).
CORRECT = [
    ("c2/ge-p9c", "Storm 1 had a lag of twelve hours.", "geography-clock-interval", True),
    ("c2/ge-p9c", "Storm 2 had a lag of four and a half hours.", "geography-clock-interval", True),
    ("c2/ge-p9c", "Storm 2 peaked 4.5 h after its rainfall peak.", "geography-clock-interval", True),
    ("c2/ge-p9c", "The channel measures 6.0 m by 1.8 m, giving 10.8 m².", "geography-dimension-area", True),
    ("c2/ge-p9c", "The channel measures 6.0 m by 1.8 m, so the catchment of 24 km² drains into a small channel.",
     "geography-dimension-area", False),
    ("c2/ge-p9c", "The channel is 6.0 m wide and 1.8 m deep, so water from the whole 24 km² catchment passes through it.",
     "geography-dimension-area", False),
    ("c2/ge-p9c", "The plot measured 2 m by 3 m, so the 24 km² catchment is much larger.", "geography-dimension-area", False),
    ("c2/ge-p9c", "Each quadrat was 1 m by 1 m, giving a sample of 24 km² in total coverage.", "geography-dimension-area", False),
    ("c2/ge-t15", "Energy from oil rose by about 12% between 2005 and 2025.", "geography-table-change", True),
    ("c2/ge-t15", "The amount of energy from coal fell by about 22% between 2005 and 2025.", "geography-table-change", True),
    ("c2/ge-t15", "The amount of energy from natural gas rose by about 88% between 2005 and 2025.", "geography-table-change", True),
    ("c2/ge-t15", "Natural gas supply rose by about 88% between 2005 and 2025, from 123 PJ to 231 PJ.", "geography-table-change", True),
    # (rewritten to the stricter rule of the push check of a9129c78: 'fell by about 39%' of a share fixes neither the relative change
    # (39%) nor the change in points (18), so the figure that fits one reading is never shown as checked; it was ENTAILED here)
    ("c2/ge-t15", "The share of coal fell by about 39% between 2005 and 2025.", "geography-table-change", False),
    ("c2/ge-t15", "Total supply showed a relative rise of about 28%, faster than population.", "geography-table-derived", True),
    ("c2/ge-t15", "Compared with coal, total supply showed a relative rise of about 28%.", "geography-table-derived", True),
    ("c2/ge-t15", "Imported energy, mostly oil and gas, was about 567 PJ in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", "Each Ostrel resident used about 42 GJ of primary energy in 2025.", "geography-table-derived", True),
    ("c2/ge-t15", "The imported share rose by 16 percentage points, a relative rise of about 42%.", "geography-table-derived", True),
    ("c2/ge-t15", "Each Ostrel resident used about 42 GJ of primary energy in 2025.", "core-figure", False),
    ("c1/sp-t14", "El 25 % de 80 es 20.", "language-b-share", True),
    ("c1/sp-t14", "Más del 40 % de 25 hoteles son 4 estrellas.", "language-b-share", False),
    ("c1/sp-t14", "El 20 % de los 150 hoteles, o sea 300 camas, está en el centro.", "language-b-share", False),
    ("c1/sp-t14", "El 10 % de los 300 vecinos son 65 años o más.", "language-b-share", False),
    ("c1/sp-t14", "En 2023 los jóvenes eran el 25 % de los 80 vecinos.", "language-b-share", False),
    ("c1/sp-t14", "In 2023 young people were 25% of the 80 residents.", "language-b-share", False),
    ("c1/sp-t14", "About 40% of 30 students were 18 or older.", "language-b-share", False),
    ("c1/sp-t14", "In 2021, 30% of 50 pupils were 16 years old.", "language-b-share", False),
    ("c1/sp-t14", "Around 40% of 25 hotels are 4 stars.", "language-b-share", False),
    ("c2/sp-t15", "El 25 % de los 80 alumnos, es decir 20 alumnos, estudia francés.", "language-b-share", True),
    ("c2/sp-t15", "Mi tía, de 40 años, vivió en Bogotá (de 2009 a 2021).", "language-b-dated-change", False),
    ("c2/sp-t15", "Con 30 años se fue a Madrid, donde trabajó en un hotel (2009-2021).", "language-b-dated-change", False),
    ("c2/sp-t15", "Vivió doce años en Bogotá (de 2009 a 2021).", "language-b-dated-change", True),
]


@pytest.mark.parametrize("name,sentence,family,code", FAULTY)
def test_a_wrong_figure_is_named_and_never_entailed(name, sentence, family, code):
    found, checks, entailed = _new(name, sentence)
    assert code in found and any(c[0].startswith(family) and c[1] == "COUNTEREXAMPLE" for c in checks), (sentence, found, checks)
    assert not any(c[0].startswith(family) for c in entailed), (sentence, entailed)


@pytest.mark.parametrize("name,sentence,family,entailed_expected", CORRECT)
def test_a_correct_figure_is_never_a_counterexample(name, sentence, family, entailed_expected):
    found, checks, entailed = _new(name, sentence)
    assert not any(c[0].startswith(family) for c in checks), (sentence, found, checks)
    assert any(c[0].startswith(family) for c in entailed) is entailed_expected, (sentence, entailed)


def test_the_case_consistency_reader_stays_linear_on_a_long_sentence_of_of_them_phrases():
    # check round 11 of c3e (a stall): "185 people, 50 of the 185 deaths, more than 130 of them, " repeated took 0.41, 1.38, 4.84 and
    # 18.8 s at 25k, 50k, 100k and 200k characters (each "of them" looked for its head noun from the sentence's start); now the head
    # is looked for in a bounded window, so the time grows with the length (each doubling at most 3 times the time, a 5 s ceiling)
    import time

    from epinoic_logic.branches import geography
    _answer, question, subject, agent, task_type, docs = H.RECORDED["c3/ge-t16"]
    unit = "185 people, 50 of the 185 deaths, more than 130 of them, "
    took = []
    for n in (50_000, 100_000):
        text = (unit * (n // len(unit) + 1))[:n]
        rep = H.report(subject, agent, text, task_type=task_type, docs=docs,
                       claims=[dict(claim_id="c1", claim_text=text[:3000], claim_role="point", materiality="material")])
        t0 = time.process_time()
        geography._build(rep, question)
        took.append(time.process_time() - t0)
    assert took[1] < 5.0 and took[1] <= 3 * max(took[0], 0.2), took
