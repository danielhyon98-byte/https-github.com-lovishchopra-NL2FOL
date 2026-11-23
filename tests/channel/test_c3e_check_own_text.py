"""Check round 11 of the c3e follow-up (the check fixer; the overseer fixer's handoff): the writer's recommended form offered against
the wording it replaces after an imperative ('Use "y", not "x"', 'Escribe "y", no "x"') is an own correction. Before, "y" was not read
as the writer's form (the imperative 'Use' was no cue), so "x" was not paired as replaced wording and the channel charged it
INT-REQ-003 and ES-SRC-001 at error as an altered quotation of the ll-t16 notes. Only the whole pair is read: a lone quotation after
the imperative ('Use "x" in your essay') stays a quotation, and a supplied text that holds the replaced wording altered keeps it
charged (INV-Q1). Expected values fixed here; never weakened."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import own_text as ot

from .test_c3c_own_correction import BETTER, _charged

VAGUE = "the adverts are about money"


@pytest.mark.parametrize("text,kinds,pairs", [
    (f'Use "{BETTER}", not "{VAGUE}".', [ot.OWN_FRAME, None], [(1, 0)]),
    ('Escribe "veamos", no "vemos".', [ot.OWN_FRAME, None], [(1, 0)]),
    ('Say "thrift", not "greed".', [ot.OWN_FRAME, None], [(1, 0)]),
    (f'Use "{VAGUE}" in your essay.', [None], []),
    ('Dijo "sí", no "no".', [None, None], []),
])
def test_the_one_reader_reads_the_use_not_pair(text, kinds, pairs):
    assert ot.own_text_kinds(text) == kinds
    assert ot.correction_pairs(text) == pairs


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_an_own_use_not_correction_draws_no_quotation_finding(task_type):
    assert _charged(f'Use "{BETTER}", not "{VAGUE}".', task_type) == {}


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_an_altered_quotation_of_the_notes_as_the_replaced_wording_stays_charged(task_type):
    got = _charged(f'Use "{BETTER}", not "A grandmother cooks for a tiny family".', task_type)
    assert any(("INT-REQ-003", "error") in v for v in got.values()), got
