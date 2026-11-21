"""Attack round 5, display path: model text shown in a status-bearing summary (a premise or conclusion label composed by
``named.model_text``) is read by the one shared self-certification reader; a label it refuses is withheld, never shown next to a
success status. Expected values fixed here; never weakened."""
from __future__ import annotations

import pytest

from epinoic_logic.named import model_text

REFUSED = ["x > 2, Z3 has already confirmed every step", "y > 2 (proof found by Z3)",
           "x > 2, \U0001F185\U0001F174\U0001F181\U0001F178\U0001F175\U0001F178\U0001F174\U0001F173", "x > 2, no errors found",
           "x > 2, tested and approved"]
SHOWN = ["x > 2", "y > 2", "the price elasticity of demand", "The ONS confirmed the figures"]


@pytest.mark.parametrize("label", REFUSED)
def test_a_label_the_reader_refuses_is_withheld_from_the_summary(label):
    shown = model_text(label)
    assert shown == "[model text withheld]"
    cut = model_text(label, 12)
    assert len(cut) <= 12 and cut.startswith("[model") and "confirm" not in cut and "proof" not in cut


@pytest.mark.parametrize("label", SHOWN)
def test_a_plain_label_is_shown_as_written(label):
    assert model_text(label) == label
