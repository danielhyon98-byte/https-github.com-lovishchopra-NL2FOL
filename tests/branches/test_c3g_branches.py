"""Follow-up 5 (c3g) of the branch packs: the push check of 08c4a36b.

1. A row or column is named only by its figure's own clause. A word inside an insertion (a subordinate clause opened by 'while',
   'whereas', 'as', 'since', 'although', 'when', 'after', 'because', 'despite', 'with' and the like, a relative clause, a bracket, a pair
   of dashes, a comma-delimited apposition) never names it wherever the insertion stands, and the verb of an insertion is never the
   subject's verb (:mod:`epinoic_logic.branches.insertions`). 08c4a36b read 'Energy supply per person, while coal declined, was about
   11.8 GJ in 2025.' as the Coal row's figure: ENTAILED, and its correct 42 GJ twin a COUNTEREXAMPLE (c2/ge-t15; true value 1,050 PJ /
   24.9 M = 42.2 GJ). The readings-diff lens's 88-cell grid and the branches-policy lens's 42 clause pairs are rebuilt here: every wrong
   cell a COUNTEREXAMPLE with INT-SUBJ-004, every correct cell ENTAILED with no finding.
2. The same class on the attribute-table column lookup (c1/ge-t14) and the Language B clause of a count (c3/sp-t16, 'El intercambio,
   según la consigna, duró dos semanas.': a regression of 08c4a36b's comma-bounded clause, restored).
3. Language B (c1/sp-t14): a check that accepts either of two differing figures of a noun is no check. An undated figure is read only
   against the figure its own line places (a reopening, 'en septiembre': the school reopened with catorce alumnos; 'más de cien' is the
   1960 figure), else it gets no check.
4. Language B correction lines with labels and no quotation marks, ticks and crosses, or a label on each of two lines are counted
   (check round 12 of c3f: the answer's correct counts of its corrections drew COUNTEREXAMPLEs).

Every expected value is fixed here; each fault is pinned with its correct twin.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import geography
from epinoic_logic.branches.insertions import insertion_spans, masked

from . import d9d10_hub as H


def _one(record: str, sentence: str):
    """(statuses, codes) of ``sentence`` delivered alone as the recorded answer's agent, with its request and supplied texts; codes net of
    those a neutral one-line answer draws (request coverage)."""
    _a, question, subject, agent, task_type, docs = H.RECORDED[record]
    rc = H.through_hub(sentence, question, subject, agent, task_type, docs)
    base = H.through_hub(_NEUTRAL[record], question, subject, agent, task_type, docs)
    return sorted({st for _c, st in H.checks(rc)}), sorted(set(H.codes(rc)) - set(H.codes(base)))


_NEUTRAL = {"c2/ge-t15": "The answer uses the supplied table.", "c1/ge-t14": "The answer uses the supplied fieldwork data.",
            "c1/sp-t14": "6. La escuela está en Valdeoca.", "c3/sp-t16": "Your email answers the task."}


# ------------------------------------------------------------------------------------------------- 1. the readings-diff lens's grid
_CLAUSES = [("while imports rose", "22.8"), ("as imports grew", "22.8"), ("though imported energy rose", "22.8"),
            ("with natural gas expanding", "9.3"), ("as gas use rose", "9.3"), ("even as coal use fell", "11.8"),
            ("as oil demand eased", "11.4"), ("with nuclear power doubling", "1.7"), ("as hydroelectric power grew", "2.5"),
            ("as wind and solar power spread", "5.5"), ("as the population grew", "22.8")]
_FRAMES = ["Energy supply per person, {c}, reached about {v} GJ in 2025.",
           "In 2025, {c}, energy supply per person was about {v} GJ.",
           "Energy supply per person was about {v} GJ in 2025, {c}.",
           "Energy supply per person ({c}) was about {v} GJ in 2025."]
GRID_88 = [(f.format(c=c, v=v), right) for f in _FRAMES for c, w in _CLAUSES for v, right in ((w, False), ("42", True))]


def test_grid_has_88_cells():
    assert len(GRID_88) == 88 and len(set(GRID_88)) == 88


@pytest.mark.parametrize("sentence,right", GRID_88)
def test_readings_diff_grid(sentence, right):
    statuses, codes = _one("c2/ge-t15", sentence)
    if right:
        assert (statuses, codes) == (["ENTAILED"], [])
    else:
        assert (statuses, codes) == (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])


# ------------------------------------------------------------------------------------------------- 1. the branches-policy lens's pairs
# (the lens's own 42 pairs, as its generator drew them: a connector, a row's clause and a frame each; wrong = the row's per-person figure)
PAIRS_42 = [
    ('Energy supply per person, because coal declined, was about 11.8 GJ in 2025.', False),
    ('Energy supply per person, because coal declined, was about 42 GJ in 2025.', True),
    ('Energy supply per person, after oil prices rose, was about 11.4 GJ in 2025.', False),
    ('Energy supply per person, after oil prices rose, was about 42 GJ in 2025.', True),
    ('Energy supply per person, once natural gas grew, was about 9.3 GJ in 2025.', False),
    ('Energy supply per person, once natural gas grew, was about 42 GJ in 2025.', True),
    ('Energy supply per person, while nuclear capacity grew, was about 1.7 GJ in 2025.', False),
    ('Energy supply per person, while nuclear capacity grew, was about 42 GJ in 2025.', True),
    ('Energy supply per person, as wind and solar power spread, was about 5.5 GJ in 2025.', False),
    ('Energy supply per person, as wind and solar power spread, was about 42 GJ in 2025.', True),
    ('Energy supply per person, as hydroelectric output rose, was about 2.5 GJ in 2025.', False),
    ('Energy supply per person, as hydroelectric output rose, was about 42 GJ in 2025.', True),
    ('Energy supply per person, because imports climbed, was about 22.8 GJ in 2025.', False),
    ('Energy supply per person, because imports climbed, was about 42 GJ in 2025.', True),
    ('Energy supply per person was, while coal declined, about 11.8 GJ in 2025.', False),
    ('Energy supply per person was, while coal declined, about 42 GJ in 2025.', True),
    ('Energy supply per person was, although oil prices rose, about 11.4 GJ in 2025.', False),
    ('Energy supply per person was, although oil prices rose, about 42 GJ in 2025.', True),
    ('Energy supply per person was, while natural gas grew, about 9.3 GJ in 2025.', False),
    ('Energy supply per person was, while natural gas grew, about 42 GJ in 2025.', True),
    ('Energy supply per person was, as nuclear capacity grew, about 1.7 GJ in 2025.', False),
    ('Energy supply per person was, as nuclear capacity grew, about 42 GJ in 2025.', True),
    ('Energy supply per person was, once wind and solar power spread, about 5.5 GJ in 2025.', False),
    ('Energy supply per person was, once wind and solar power spread, about 42 GJ in 2025.', True),
    ('Energy supply per person was, once hydroelectric output rose, about 2.5 GJ in 2025.', False),
    ('Energy supply per person was, once hydroelectric output rose, about 42 GJ in 2025.', True),
    ('Energy supply per person was, as imports climbed, about 22.8 GJ in 2025.', False),
    ('Energy supply per person was, as imports climbed, about 42 GJ in 2025.', True),
    ('In 2025, although coal declined, energy supply per person was about 11.8 GJ.', False),
    ('In 2025, although coal declined, energy supply per person was about 42 GJ.', True),
    ('In 2025, as oil prices rose, energy supply per person was about 11.4 GJ.', False),
    ('In 2025, as oil prices rose, energy supply per person was about 42 GJ.', True),
    ('In 2025, once natural gas grew, energy supply per person was about 9.3 GJ.', False),
    ('In 2025, once natural gas grew, energy supply per person was about 42 GJ.', True),
    ('In 2025, while nuclear capacity grew, energy supply per person was about 1.7 GJ.', False),
    ('In 2025, while nuclear capacity grew, energy supply per person was about 42 GJ.', True),
    ('In 2025, as wind and solar power spread, energy supply per person was about 5.5 GJ.', False),
    ('In 2025, as wind and solar power spread, energy supply per person was about 42 GJ.', True),
    ('In 2025, although hydroelectric output rose, energy supply per person was about 2.5 GJ.', False),
    ('In 2025, although hydroelectric output rose, energy supply per person was about 42 GJ.', True),
    ('In 2025, while imports climbed, energy supply per person was about 22.8 GJ.', False),
    ('In 2025, while imports climbed, energy supply per person was about 42 GJ.', True),
    ('Energy supply per person was about 11.8 GJ in 2025 (once coal declined).', False),
    ('Energy supply per person was about 42 GJ in 2025 (once coal declined).', True),
    ('Energy supply per person was about 11.4 GJ in 2025 (while oil prices rose).', False),
    ('Energy supply per person was about 42 GJ in 2025 (while oil prices rose).', True),
    ('Energy supply per person was about 9.3 GJ in 2025 (although natural gas grew).', False),
    ('Energy supply per person was about 42 GJ in 2025 (although natural gas grew).', True),
    ('Energy supply per person was about 1.7 GJ in 2025 (while nuclear capacity grew).', False),
    ('Energy supply per person was about 42 GJ in 2025 (while nuclear capacity grew).', True),
    ('Energy supply per person was about 5.5 GJ in 2025 (after wind and solar power spread).', False),
    ('Energy supply per person was about 42 GJ in 2025 (after wind and solar power spread).', True),
    ('Energy supply per person was about 2.5 GJ in 2025 (since hydroelectric output rose).', False),
    ('Energy supply per person was about 42 GJ in 2025 (since hydroelectric output rose).', True),
    ('Energy supply per person was about 22.8 GJ in 2025 (once imports climbed).', False),
    ('Energy supply per person was about 42 GJ in 2025 (once imports climbed).', True),
    ('Energy supply per person (after coal declined) was about 11.8 GJ in 2025.', False),
    ('Energy supply per person (after coal declined) was about 42 GJ in 2025.', True),
    ('Energy supply per person (as oil prices rose) was about 11.4 GJ in 2025.', False),
    ('Energy supply per person (as oil prices rose) was about 42 GJ in 2025.', True),
    ('Energy supply per person (since natural gas grew) was about 9.3 GJ in 2025.', False),
    ('Energy supply per person (since natural gas grew) was about 42 GJ in 2025.', True),
    ('Energy supply per person (after nuclear capacity grew) was about 1.7 GJ in 2025.', False),
    ('Energy supply per person (after nuclear capacity grew) was about 42 GJ in 2025.', True),
    ('Energy supply per person (as wind and solar power spread) was about 5.5 GJ in 2025.', False),
    ('Energy supply per person (as wind and solar power spread) was about 42 GJ in 2025.', True),
    ('Energy supply per person (although hydroelectric output rose) was about 2.5 GJ in 2025.', False),
    ('Energy supply per person (although hydroelectric output rose) was about 42 GJ in 2025.', True),
    ('Energy supply per person (because imports climbed) was about 22.8 GJ in 2025.', False),
    ('Energy supply per person (because imports climbed) was about 42 GJ in 2025.', True),
    ('Energy supply per person was about 38 GJ in 2005; as coal declined, it was about 11.8 GJ in 2025.', False),
    ('Energy supply per person was about 38 GJ in 2005; as coal declined, it was about 42 GJ in 2025.', True),
    ('Energy supply per person was about 38 GJ in 2005; as oil prices rose, it was about 11.4 GJ in 2025.', False),
    ('Energy supply per person was about 38 GJ in 2005; as oil prices rose, it was about 42 GJ in 2025.', True),
    ('Energy supply per person was about 38 GJ in 2005; while natural gas grew, it was about 9.3 GJ in 2025.', False),
    ('Energy supply per person was about 38 GJ in 2005; while natural gas grew, it was about 42 GJ in 2025.', True),
    ('Energy supply per person was about 38 GJ in 2005; although nuclear capacity grew, it was about 1.7 GJ in 2025.', False),
    ('Energy supply per person was about 38 GJ in 2005; although nuclear capacity grew, it was about 42 GJ in 2025.', True),
    ('Energy supply per person was about 38 GJ in 2005; when wind and solar power spread, it was about 5.5 GJ in 2025.', False),
    ('Energy supply per person was about 38 GJ in 2005; when wind and solar power spread, it was about 42 GJ in 2025.', True),
    ('Energy supply per person was about 38 GJ in 2005; once hydroelectric output rose, it was about 2.5 GJ in 2025.', False),
    ('Energy supply per person was about 38 GJ in 2005; once hydroelectric output rose, it was about 42 GJ in 2025.', True),
    ('Energy supply per person was about 38 GJ in 2005; because imports climbed, it was about 22.8 GJ in 2025.', False),
    ('Energy supply per person was about 38 GJ in 2005; because imports climbed, it was about 42 GJ in 2025.', True),
]


def test_pairs_are_42():
    assert len(PAIRS_42) == 84 and len({s for s, _r in PAIRS_42}) == 84


@pytest.mark.parametrize("sentence,right", PAIRS_42)
def test_branches_policy_clause_pairs(sentence, right):
    statuses, codes = _one("c2/ge-t15", sentence)
    if right:
        assert (statuses, codes) == (["ENTAILED"], [])
    else:
        assert "COUNTEREXAMPLE" in statuses and codes == ["INT-SUBJ-004"]


@pytest.mark.parametrize("sentence,expected", [
    # the push check's named forms, each with its correct twin
    ("Energy supply per person, while coal declined, was about 11.8 GJ in 2025.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Energy supply per person, while coal declined, was about 42 GJ in 2025.", (["ENTAILED"], [])),
    ("Energy supply per person, whereas coal declined, stood at about 11.8 GJ in 2025.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Energy supply per person, whereas coal declined, stood at about 42 GJ in 2025.", (["ENTAILED"], [])),
    ("Energy supply per person, while imports rose, reached about 22.8 GJ in 2025.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Energy supply per person, while imports rose, reached about 42 GJ in 2025.", (["ENTAILED"], [])),
    ("Energy supply per person (as gas use rose) was about 9.3 GJ in 2025.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Energy supply per person (as gas use rose) was about 42 GJ in 2025.", (["ENTAILED"], [])),
    # the insertion with no delimiter, and between dashes
    ("Energy supply per person as gas use rose was about 9.3 GJ in 2025.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Energy supply per person as gas use rose was about 42 GJ in 2025.", (["ENTAILED"], [])),
    ("Energy supply per person – as coal use fell – was about 11.8 GJ in 2025.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Energy supply per person – as coal use fell – was about 42 GJ in 2025.", (["ENTAILED"], [])),
    # an opening year written with its comma is the year ('In 2025, ...': the figure had no year and no check)
    ("In 2025, energy supply per person was about 22.8 GJ.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("In 2025, energy supply per person was about 42 GJ.", (["ENTAILED"], [])),
])
def test_named_row_forms(sentence, expected):
    assert _one("c2/ge-t15", sentence) == expected


@pytest.mark.parametrize("sentence,expected", [
    # a figure inside an insertion keeps its own clause's row; the figure outside it takes the subject's
    ("Nuclear power, which had a 4% share, supplied 42.0 PJ in 2025.", "ENTAILED"),
    ("Nuclear power, which had a 4% share, supplied 63.0 PJ in 2025.", "COUNTEREXAMPLE"),
    ("Imported energy, mostly oil and gas, was about 567 PJ in 2025.", "ENTAILED"),
    ("Imported energy, mostly oil and gas, was about 294 PJ in 2025.", "COUNTEREXAMPLE"),
])
def test_figures_inside_and_beside_an_insertion(sentence, expected):
    statuses, _codes = _one("c2/ge-t15", sentence)
    assert expected in statuses and (expected == "COUNTEREXAMPLE" or statuses == ["ENTAILED"])


# ------------------------------------------------------------------------------------------------- 2. columns (c1/ge-t14)
@pytest.mark.parametrize("sentence,expected", [
    ("The pedestrian count, as retail use fell, was 60 at site 4.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),  # (true 97)
    ("The pedestrian count, as retail use fell, was 97 at site 4.", (["ENTAILED"], [])),
    ("At site 2 the EQS, with pedestrian numbers high, was 186.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),  # (true 22)
    ("At site 2 the EQS, with pedestrian numbers high, was 22.", (["ENTAILED"], [])),
    ("The EQS at site 4, as retail use fell, was 60.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),  # (true 18)
    ("The EQS at site 4, as retail use fell, was 18.", (["ENTAILED"], [])),
    ("The pedestrian count at site 2, although the EQS was low, was 22.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),  # (true 186)
    ("The pedestrian count at site 2, although the EQS was low, was 186.", (["ENTAILED"], [])),
    ("At site 2 the pedestrian count – although the EQS was low – was 22.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("At site 2 the pedestrian count – although the EQS was low – was 186.", (["ENTAILED"], [])),
    ("Retail use at site 6 (where the pedestrian count was low) was 61%.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),  # (true 30)
    ("Retail use at site 6 (where the pedestrian count was low) was 30%.", (["ENTAILED"], [])),
    # a contrast clause at the end keeps its own figures
    ("The pedestrian count fell to 19 at site 10, while retail use fell from 92% to 0%.", (["ENTAILED"], [])),
])
def test_column_lookup_reads_the_figures_own_clause(sentence, expected):
    statuses, codes = _one("c1/ge-t14", sentence)
    assert (sorted(set(statuses) - {"ENTAILED"} if expected[0] == ["COUNTEREXAMPLE"] else statuses), codes) == expected


# ------------------------------------------------------------------------------------------------- 2. Language B: the count's clause
@pytest.mark.parametrize("sentence,expected", [
    ("El intercambio, según la consigna, duró dos semanas.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),  # (the task: tres semanas)
    ("El intercambio, según la consigna, duró tres semanas.", ([], [])),
    ("El intercambio (según la consigna) duró dos semanas.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("The exchange, according to the task, lasted two weeks.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("The exchange, according to the task, lasted three weeks.", ([], [])),
    # the count of another clause stays that clause's (check round 12 of c3f)
    ("You returned to England two weeks ago, after an exchange of three weeks.", ([], [])),
])
def test_language_b_count_clause_reads_past_an_insertion(sentence, expected):
    assert _one("c3/sp-t16", sentence) == expected


# ------------------------------------------------------------------------------------------------- 3. Language B: undated figures
@pytest.mark.parametrize("sentence,expected", [
    # the push check's forms (the school reopened with catorce alumnos), each with its correct twin
    ("6. Al reabrir, la escuela acogió a cien alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
    ("6. Al reabrir, la escuela acogió a catorce alumnos.", (["ENTAILED"], [])),
    ("6. La escuela reabrió con cien alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
    ("6. La escuela reabrió con catorce alumnos.", (["ENTAILED"], [])),
    ("6. La escuela volvió a abrir sus puertas con cien alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
    ("6. La escuela volvió a abrir sus puertas con catorce alumnos.", (["ENTAILED"], [])),
    ("6. La escuela abrió en septiembre con más de cien alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
    ("6. La escuela abrió en septiembre con catorce alumnos.", (["ENTAILED"], [])),
    ("6. Tras su reapertura, la escuela recibió a cien alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
    ("6. Tras su reapertura, la escuela recibió a catorce alumnos.", (["ENTAILED"], [])),
    ("6. Cuando reabrió, la escuela tenía más de cien alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
    ("6. En septiembre la escuela tenía cien alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
    # nothing in the line places the figure: either figure of the noun would match, so no check (never ENTAILED)
    ("6. La escuela tenía cien alumnos.", ([], [])),
    ("6. La escuela tenía catorce alumnos.", ([], [])),
    # a line of the present ('Hoy ...') places its figure among the text's figures of the present (it went unread)
    ("6. Hoy la escuela tiene más de cien alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
    ("6. Hoy la escuela tiene catorce alumnos.", (["ENTAILED"], [])),
    # a figure the line dates keeps the dated reading
    ("6. En 1960 la escuela tenía más de cien alumnos.", (["ENTAILED"], [])),
    ("6. En 1960 la escuela tenía catorce alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
])
def test_language_b_undated_figure_is_placed_by_its_line(sentence, expected):
    assert _one("c1/sp-t14", sentence) == expected


# ------------------------------------------------------------------------------------------------- 4. Language B: correction lines
_SP16_LINE = '- "El primer semana fue difícil" → "La primera semana fue difícil" (semana is feminine; primer is shortened only before a masculine singular noun).'
_EXPL = " (semana is feminine; primer is shortened only before a masculine singular noun)."
_FORMS = [
    "- Mal: El primer semana fue difícil. Bien: La primera semana fue difícil" + _EXPL,
    "- Incorrecto: El primer semana fue difícil. Correcto: La primera semana fue difícil" + _EXPL,
    '- ✗ "El primer semana fue difícil" ✓ "La primera semana fue difícil"' + _EXPL,
    "- ✗ El primer semana fue difícil ✓ La primera semana fue difícil" + _EXPL,
    "- Mal: «El primer semana fue difícil»\n  Bien: «La primera semana fue difícil»" + _EXPL,
    "- Mal: El primer semana fue difícil.\n  Bien: La primera semana fue difícil" + _EXPL,
    '- Mal: "El primer semana fue difícil". Bien: "La primera semana fue difícil"' + _EXPL,
    "- Escribiste «El primer semana fue difícil»; lo correcto es «La primera semana fue difícil»" + _EXPL,
    '- Escribiste "El primer semana fue difícil"; lo correcto es "La primera semana fue difícil"' + _EXPL,
    "- Antes: El primer semana fue difícil. Después: La primera semana fue difícil" + _EXPL,
    "- Before: El primer semana fue difícil. After: La primera semana fue difícil" + _EXPL,
    '- You wrote "El primer semana fue difícil"; write "La primera semana fue difícil" instead' + _EXPL,
    "- You wrote «El primer semana fue difícil»; write «La primera semana fue difícil» instead" + _EXPL,
]


def _listed(answer: str) -> list[tuple[str, str]]:
    rc = H.recorded("c3/sp-t16", answer)
    return [c for c in H.checks(rc) if c[0].startswith("language-b-listed-count")]


@pytest.mark.parametrize("form", _FORMS)
def test_label_correction_lines_are_counted(form):
    base = H.RECORDED["c3/sp-t16"][0]
    assert _SP16_LINE in base
    assert {st for _c, st in _listed(base.replace(_SP16_LINE, form))} == {"ENTAILED"}
    # the faulty twin: the answer's count of its corrections made wrong ('six points' -> 'seven points') is named
    wrong = base.replace(_SP16_LINE, form).replace("fix the six points", "fix the seven points")
    assert "fix the seven points" in wrong
    assert ("language-b-listed-count-1", "COUNTEREXAMPLE") in _listed(wrong)


def test_a_replaced_label_alone_is_no_correction_line():
    from epinoic_logic.branches.language_b import _correction_lines
    assert _correction_lines("- Mal: El primer semana fue difícil.\nNext step: fix it.") == []
    assert len(_correction_lines("- Mal: El primer semana.\n  Bien: La primera semana.\n- ✗ x ✓ y")) == 2


# ------------------------------------------------------------------------------------------------- the insertion reader itself
@pytest.mark.parametrize("text,blank", [
    ("Energy supply per person, while coal declined, was about 11.8 GJ in 2025.", "Energy supply per person was about 11.8 GJ in 2025."),
    ("Energy supply per person (as gas use rose) was about 9.3 GJ in 2025.", "Energy supply per person was about 9.3 GJ in 2025."),
    ("Energy supply per person as gas use rose was about 9.3 GJ in 2025.", "Energy supply per person was about 9.3 GJ in 2025."),
    ("Imported energy, mostly oil and gas, was about 567 PJ", "Imported energy was about 567 PJ"),
    ("Energy supply per person, coal aside, was about 42 GJ.", "Energy supply per person was about 42 GJ."),
    ("El intercambio, según la consigna, duró dos semanas.", "El intercambio duró dos semanas."),
    # no insertion: a list, a comparison
    ("Coal, oil, and gas supplied 77%.", "Coal, oil, and gas supplied 77%."),
    ("Energy supply per person was as high as 42 GJ in 2025.", "Energy supply per person was as high as 42 GJ in 2025."),
])
def test_insertion_spans(text, blank):
    assert " ".join(masked(text, insertion_spans(text)).split()) == blank


@pytest.mark.parametrize("unit", ["Energy supply per person, while coal declined, ", "Energy supply while coal declined ",
                                  "Supply (as gas rose) ", "Supply – as gas rose – ", "about 38 GJ in 2005, ", "with gas with coal ",
                                  "as high as ", "Mal: x, según y, "])
def test_insertion_reader_is_linear(unit):
    """Hostile input: the whole sentence is walked a fixed number of times, each insertion's end found by bisection (no cap leaves an
    insertion unread)."""
    def run(k: int) -> float:
        text = unit * k + "was about 42 GJ in 2025."
        t0 = time.perf_counter()
        insertion_spans.__wrapped__(text)
        geography._YtIndex(text)
        return time.perf_counter() - t0
    run(50)
    small, large = min(run(500) for _ in range(3)), min(run(4000) for _ in range(3))
    assert large < small * 8 * 3 + 0.05  # 8 times the input: well under quadratic growth
    spans = insertion_spans.__wrapped__("Energy supply per person, while coal declined, " * 300 + "was 42 GJ.")
    assert len(spans) >= 299  # every insertion read, none dropped past a cap


# ------------------------------------------------------------------------------------------------- 5. Language B: the corrected half
@pytest.mark.parametrize("record,line,charged", [
    # the corrected half presents the text's wording altered: checked as a quotation of the text, and named
    ("c3/sp-p10d", "Mal: «échale ganas, hijo». Bien: «échale ganas, mi hijo».", True),
    ("c3/sp-t16", "Mal: «Ya hace dos semana que volví». Bien: «Ya hace tres semanas que volví a Inglaterra».", True),
    # its correct twin restores the text's exact wording: the replaced half is the writer's own example, never charged
    ("c3/sp-p10d", "Mal: «échale ganas, hijo». Bien: «échale ganas, mijo».", False),
    ("c3/sp-t16", "Mal: «Ya hace dos semana que volví». Bien: «Ya hace dos semanas que volví a Inglaterra».", False),
])
def test_language_b_corrected_half_is_read_against_the_source(record, line, charged):
    answer = H.RECORDED[record][0]
    base = set(H.codes(H.recorded(record)))
    rc = H.recorded(record, answer + "\n\n" + line)
    assert ("INT-REQ-003" in set(H.codes(rc)) - base) is charged


@pytest.mark.parametrize("sentence,wrong", [
    # the shared table reader and the change readers read the figure's own clause too (HEAD of 08c4a36b: the first and third wrong
    # forms were ENTAILED and their correct twins charged)
    ("According to the table, imports, while coal declined, made up 28% of supply in 2025.", True),
    ("According to the table, imports, while coal declined, made up 54% of supply in 2025.", False),
    ("Coal, as imports rose, fell from 38% to 54% between 2005 and 2025.", True),
    ("Coal, as imports rose, fell from 46% to 28% between 2005 and 2025.", False),
    ("The coal share, as imports rose, fell by 16 percentage points between 2005 and 2025.", True),
    ("The coal share, as imports rose, fell by 18 percentage points between 2005 and 2025.", False),
    ("According to the table, imports, while the share of primary energy supply from coal declined, made up 28% in 2025.", True),
    ("According to the table, imports, while the share of primary energy supply from coal declined, made up 54% in 2025.", False),
])
def test_other_table_readers_read_the_figures_own_clause(sentence, wrong):
    statuses, codes = _one("c2/ge-t15", sentence)
    if wrong:
        assert "COUNTEREXAMPLE" in statuses and set(codes) & {"INT-SUBJ-001", "INT-SUBJ-004"}
    else:
        assert statuses == ["ENTAILED"] and codes == []


# ------------------------------------------------------------------------------------------------- 6. a c3f leftover on ge-p9c
@pytest.mark.parametrize("sentence,wrong", [
    # the request's 'base flow before the storm 1.2 m³ s⁻¹' is a base flow (a time qualifier between the noun and its figure), so a
    # wrong restated base flow is compared with it (it went unread: the request's figure had been keyed 'storm')
    ("Before Storm 2 the base flow was 1.2 m³ s⁻¹.", True),
    ("Before Storm 2 the base flow was 1.1 m³ s⁻¹.", False),
    ("Before Storm 1 the base flow was 1.1 m³ s⁻¹.", True),
    ("Before Storm 1 the base flow was 1.2 m³ s⁻¹.", False),
])
def test_request_base_flow_is_keyed_by_its_noun(sentence, wrong):
    answer = H.RECORDED["c2/ge-p9c"][0]
    base = H.recorded("c2/ge-p9c")
    rc = H.recorded("c2/ge-p9c", answer + "\n\n" + sentence)
    new = [c for c in H.checks(rc) if c not in set(H.checks(base))]
    codes = sorted(set(H.codes(rc)) - set(H.codes(base)))
    if wrong:
        assert ("geography-request-figure-1", "COUNTEREXAMPLE") in new and codes == ["INT-SUBJ-004"]
    else:
        assert not [c for c in new if c[1] != "ENTAILED"] and codes == []
