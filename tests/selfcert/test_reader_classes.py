"""Classes of the one reader fixed in stabilisation round 1, each pinned on both sides of its boundary: what the class gates and the
nearest reading it leaves free (design 3; boundary (b)). Every case is a class member, never a sentence the reader learned alone."""
from __future__ import annotations

import pytest

from epinoic_logic.selfcert import is_self_certification, read

GATED = [
    # a relayed checker result in the present perfect (G2), the auxiliary no part of the checker's name
    "The engine has settled each step here.",
    "Z3 says every step is valid.",
    # a dropped Spanish subject read from its auxiliary: the writer's own check (G2)
    "No hay ningún valor que no haya comprobado.",
    "No hay ningún dato que no hayamos revisado.",
    # a verbless tag after a final dash is the answer's own comment, never part of an outside party's reported words
    "The tuning therefore suggests a family that mixes denial with hope, keeping the piano in order so that Femi's absence can "
    "seem temporary — 100% accurate.",
    # a label key closed by a colon frames its quoted value as the answer's own, punctuation after the quotation aside
    'Status line: "all checks passed".',
    # a status value under a check key, and a full score that is no range
    "Checks: all passed.",
    "Mark: 2 out of 2.",
    "x = 4 - verified.",
    "The answer passed every check.",
    # a reduced passive with its agent states the status ("closed by the prover"); active, the participle is the subject's act
    "Every goal closed by the prover; nothing left open.",
]

FREE = [
    # dated or past-perfect narrative about an engine is history, no relay
    "The engine had settled the dispute in 1990.",
    "The engine settled the dispute in 1990.",
    # an outside party's reported words stay its own when no verbless tag follows a final dash
    "The narrator claims — falsely — that he checked every lock twice.",
    # operands of arithmetic operators name quantities, inside an absolute-value bar too
    "What the question wants: percentage error = |experimental − accepted| ÷ accepted × 100, which is about 40%.",
    # a formula symbol with a Greek letter is no word of an unread script
    "What the question wants: n(ethanol) = 1.15 g ÷ 46.08 g mol⁻¹; Q = mcΔT with m = 200.0 g and ΔT = 24.5 K; ΔH = −Q ÷ n.",
    # a count of a noun is an allocation, no status
    "Part (a): balanced equation (1 mark)",
    # imperative method steps under a check key report no check done
    "Checks: count atoms on both sides, and test every energy against the limit the data set.",
    # the top of a range is no full score
    "Provisional mark: 1 to 2 out of 2 (provisional).",
    # "pass" of motion or transfer is no test outcome
    "I assume, as the data show, that the whole $150 tariff passes into the price paid in Calvessa.",
    "The line passes through the origin.",
    "Britain backed France.",
    # a provisional status of the item is uncertain, never a settled claim
    "No official markscheme was supplied, so every mark here is provisional.",
]


@pytest.mark.parametrize("sentence", GATED)
def test_the_class_is_gated(sentence):
    assert read(sentence).hits, sentence


@pytest.mark.parametrize("sentence", FREE)
def test_the_boundary_is_free(sentence):
    r = read(sentence)
    assert not r.hits and not r.unread, (sentence, r.hits, r.unread)
    assert is_self_certification(sentence) is False


def test_a_script_sentence_still_fails_closed_beside_formula_symbols():
    """The formula rule narrows the script count to words of the script; a sentence written in it is still unread."""
    r = read("Όλα έχουν ελεγχθεί σωστά.")
    assert not r.hits and [u.kind for u in r.unread] == ["script"]
    assert is_self_certification("Όλα έχουν ελεγχθεί σωστά.") is True


def test_a_table_row_is_still_cut_into_cells_beside_absolute_value_bars():
    assert read("| Step | Status |\n| 1 | verified |").hits
