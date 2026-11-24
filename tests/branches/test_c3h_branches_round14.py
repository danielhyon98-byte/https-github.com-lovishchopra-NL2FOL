"""Follow-up 6 (c3h), check round 14 of the branch packs: what the check after the c3h fixes still reproduced, each expected value fixed
here and each fault pinned with its correct twin.

1. A figure that the modifier's own words make the WHOLE ('Coal, which made up 28% of the 42 GJ per person supplied in 2025, declined.',
   'Coal (28% of 1,050 PJ in 2025) declined.') is the total its clause names, never the head noun's row: the c3h modifier reading had
   charged the correct total (COUNTEREXAMPLE plus INT-SUBJ-004 on 'the share of Coal × total per person'). A part of no stated size
   ('a share of the 42 GJ', 'part of the 42 GJ') leaves open whether the figure is the whole or the part's own amount: no check.
2. A figure in a verbless modifier whose opener the modifier list did not know ('Coal, still about 42 GJ per person in 2025, declined.',
   'with about', 'just over', 'worth about', ...) was read against the total row: a wrong 42 GJ ENTAILED and its correct twin charged,
   on both the head of the branch and the c3h tree. It is read as a known opener is, against the noun's row.
3. A figure its own words place at another row after it ('Site 2, which had more pedestrians than the 97 counted at site 4, stood out.'
   on c1/ge-t14) was read against the row named before it and charged (pre-existing). Its row is not determined by the clause before
   it: no check.
4. Language B (c1/sp-t14): the replaced half of a correction written with labels ('Incorrecto: ... cien alumnos. Correcto: ... catorce
   alumnos.') is never read as a claim by the supplied-figure reader either (it had charged 'cien'); its corrected half is checked.

Table of c2/ge-t15: total 1,050 PJ / 24.9 M = 42.2 GJ per person in 2025; coal 28% = 11.8, oil 27% = 11.4, natural gas 22% = 9.3,
nuclear 4% = 1.7, hydroelectric 6% = 2.5, wind and solar 13% = 5.5. Never weakened: an expected value here is never relaxed.
"""
from __future__ import annotations

import time

import pytest

from . import d9d10_hub as H

_NEUTRAL = {"c2/ge-t15": "The answer uses the supplied table.", "c1/ge-t14": "The answer uses the supplied fieldwork data.",
            "c1/sp-t14": "6. La escuela está en Valdeoca."}
_BASE: dict = {}


def _one(record: str, sentence: str, prefix: str = ""):
    """(statuses of the checks whose id starts with ``prefix``, codes) of ``sentence`` delivered alone as the recorded answer's agent;
    codes net of a neutral one-line answer's."""
    _a, question, subject, agent, task_type, docs = H.RECORDED[record]
    rc = H.through_hub(sentence, question, subject, agent, task_type, docs)
    if record not in _BASE:
        _BASE[record] = set(H.codes(H.through_hub(_NEUTRAL[record], question, subject, agent, task_type, docs)))
    return sorted({st for c, st in H.checks(rc) if c.startswith(prefix)}), sorted(set(H.codes(rc)) - _BASE[record])


# ------------------------------------------------------------------------------------------------- 1. the whole in the modifier
@pytest.mark.parametrize("sentence,expected", [
    # the total per person (42.2 GJ) and the total (1,050 PJ) as the modifier's whole: ENTAILED, no finding
    ("Coal, which made up 28% of the 42 GJ per person supplied in 2025, declined.", (["ENTAILED"], [])),
    ("Coal, which supplied 28% of the 42 GJ per person in 2025, declined.", (["ENTAILED"], [])),
    ("Coal, at 28% of about 42 GJ per person in 2025, declined.", (["ENTAILED"], [])),
    ("Coal (28% of about 42 GJ per person in 2025) declined.", (["ENTAILED"], [])),
    ("Coal, 28% of the 42 GJ per person total in 2025, declined.", (["ENTAILED"], [])),
    ("Coal, about a quarter of the 42 GJ per person total in 2025, declined.", (["ENTAILED"], [])),
    ("Coal, a quarter of the 42 GJ per person in 2025, declined.", (["ENTAILED"], [])),
    ("Coal, which supplied about 11.8 of the 42 GJ per person in 2025, declined.", (["ENTAILED"], [])),
    ("Oil, which made up 27% of the 42 GJ per person supplied in 2025, held steady.", (["ENTAILED"], [])),
    ("Coal, which made up 28% of the 1,050 PJ supplied in 2025, declined.", (["ENTAILED"], [])),
    ("Coal (28% of 1,050 PJ in 2025) declined.", (["ENTAILED"], [])),
    # a wrong whole is still charged against the total
    ("Coal, which made up 28% of the 99 GJ per person supplied in 2025, declined.", (["COUNTEREXAMPLE", "ENTAILED"], ["INT-SUBJ-004"])),
    # a part of no stated size: whole or part, no check of the figure (never a charge, never ENTAILED)
    ("Coal, a share of the 42 GJ per person supplied in 2025, declined.", ([], [])),
    ("Coal, part of the 42 GJ per person supplied in 2025, declined.", ([], [])),
    ("Coal, a share of about 11.8 GJ per person in 2025, mattered.", ([], [])),
    ("Coal, a share of about 42 GJ per person in 2025, mattered.", ([], [])),
])
def test_a_whole_in_a_modifier_is_the_total(sentence, expected):
    assert _one("c2/ge-t15", sentence) == expected


# ------------------------------------------------------------------------------------------------- 2. every opener of a modifier
_ROWS15 = [("Coal", "11.8"), ("Oil", "11.4"), ("Natural gas", "9.3"), ("Nuclear power", "1.7"), ("Hydroelectric power", "2.5"),
           ("Wind and solar power", "5.5")]
_OPENERS = ["still about", "then about", "with about", "or about", "just over", "only about", "now about", "down to about",
            "up to about", "its supply about", "with a supply of about", "worth about", "nearly", "falling to", "rising to", "at just",
            "around", "some", "which gave about", "providing nearly", "accounting for about", "contributing about", "roughly"]
GRID_OPENERS = [(f"{r}, {o} {v} GJ per person in 2025, mattered.", right)
                for o in _OPENERS for r, w in _ROWS15 for v, right in (("42", False), (w, True))]


def test_grid_openers_has_276_cells():
    assert len(GRID_OPENERS) == 276 and len(set(GRID_OPENERS)) == 276


@pytest.mark.parametrize("sentence,right", GRID_OPENERS)
def test_a_figure_after_any_opener_is_its_nouns(sentence, right):
    # (every opener is read: the wrong 42 GJ is charged against the noun's row, the correct value ENTAILED; never the total row)
    expected = (["ENTAILED"], []) if right else (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])
    assert _one("c2/ge-t15", sentence, "geography-table-derived") == expected


@pytest.mark.parametrize("sentence,expected", [
    ("Coal, still about 42 GJ per person in 2025, declined.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Coal, still about 11.8 GJ per person in 2025, mattered.", (["ENTAILED"], [])),
    ("Coal, with about 11.8 GJ per person in 2025, declined.", (["ENTAILED"], [])),
    ("Coal, with about 42 GJ per person in 2025, declined.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    # a clause of its own after the delimiter keeps its own reading
    ("In 2025, coal supplied about 11.8 GJ per person.", (["ENTAILED"], [])),
    ("In 2025, coal supplied about 42 GJ per person.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
])
def test_opener_lines(sentence, expected):
    assert _one("c2/ge-t15", sentence, "geography-table-derived") == expected


# ------------------------------------------------------------------------------------------------- 3. a figure placed at another row
@pytest.mark.parametrize("sentence,expected", [
    ("Site 2, which had more pedestrians than the 97 counted at site 4, stood out.", ([], [])),
    ("Site 2, with nearly double the 97 pedestrians of site 4, stood out.", ([], [])),
    ("Site 2 (about twice the 97 pedestrians of site 4) stood out.", ([], [])),
    ("Site 2 had more pedestrians than the 97 counted at site 4.", ([], [])),
    # the row its own clause names keeps its check
    ("Site 2, which had a pedestrian count of 186, stood out.", (["ENTAILED"], [])),
    ("Site 2, which had a pedestrian count of 97, stood out.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
])
def test_a_figure_placed_at_another_row_is_not_charged(sentence, expected):
    assert _one("c1/ge-t14", sentence) == expected


# ------------------------------------------------------------------------------------------------- 4. Language B: the replaced half
@pytest.mark.parametrize("sentence,expected", [
    ("Incorrecto: la escuela reabrió con cien alumnos. Correcto: la escuela reabrió con catorce alumnos.", (["ENTAILED"], [])),
    ("Mal: la escuela reabrió con cien alumnos. Bien: la escuela reabrió con catorce alumnos.", (["ENTAILED"], [])),
    ("Incorrecto: la escuela reabrió con veinte alumnos. Correcto: la escuela reabrió con catorce alumnos.", (["ENTAILED"], [])),
    ("Incorrecto: la escuela reabrió con catorce alumnos. Correcto: la escuela reabrió con cien alumnos.",
     (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    # the unlabelled controls
    ("6. La escuela reabrió con cien alumnos.", (["COUNTEREXAMPLE"], ["INT-SUBJ-001"])),
    ("6. La escuela reabrió con catorce alumnos.", (["ENTAILED"], [])),
])
def test_the_replaced_half_of_a_label_pair_is_no_figure(sentence, expected):
    assert _one("c1/sp-t14", sentence, "language-b-supplied-figure") == expected


# ------------------------------------------------------------------------------------------------- hostile input stays linear
def test_the_whole_and_opener_readings_are_linear():
    """Hostile input: 200 kB of modifiers with wholes and unknown openers is read once each (the whole is looked for in the 40
    characters before each figure only)."""
    unit = "Coal, still about 11.8 GJ per person in 2025, and a share of the 42 GJ per person in 2025, "
    text = "In 2025 " + unit * (200_000 // len(unit) + 1) + "declined."
    t0 = time.perf_counter()
    _one("c2/ge-t15", text)
    assert time.perf_counter() - t0 < 120
