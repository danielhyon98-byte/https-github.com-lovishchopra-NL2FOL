"""Repair round 2 (combinator-faults-8 variant): a minus sign is read the same whatever its glyph. U+2212 (and the small and
full-width hyphen-minus) sign a figure exactly as the ASCII hyphen-minus does, and a hyphen or en dash signs it in a sign's
place (after a space or bracket with no figure before it), so a synthesis that drops the sign of a source figure is a change
in every spelling. Controls: the same figure in two spellings of the sign, and dashes that mark a range or a difference."""
from __future__ import annotations

import pytest

from epinoic_logic.integrity.ledger import _figure_differences


@pytest.mark.parametrize("signed, unsigned", [
    ("The gradient is −0.5.", "The gradient is 0.5."),
    ("The change was −12 K.", "The change was 12 K."),
    ("PMT = −352.19", "PMT = 352.19"),
    ("The gradient is -0.5.", "The gradient is 0.5."),            # the ASCII form, as before
    ("The change was –12 K.", "The change was 12 K."),            # an en dash in a sign's place
    ("Real growth was (－2) per cent.", "Real growth was (2) per cent."),
])
def test_a_dropped_sign_is_a_change_in_every_spelling(signed, unsigned):
    introduced, dropped, _ = _figure_differences(signed, [unsigned])
    assert introduced and dropped
    introduced, dropped, _ = _figure_differences(unsigned, [signed])
    assert introduced and dropped


@pytest.mark.parametrize("a, b", [
    ("PMT = −352.19", "PMT = -352.19"),
    ("PMT = -352.19", "PMT = −352.19"),
    ("The change was –12 K.", "The change was -12 K."),
    ("Output rose 2010–2020 by 5.", "Output rose 2010-2020 by 5."),          # a range
    ("Output rose 2010 –2020 by 5.", "Output rose 2010 to 2020 by 5."),      # a range written with a space
    ("The scores were 3 –5.", "The scores were 3 to 5."),                    # a figure before the dash
    ("The fall was 5−3 = 2 units.", "The fall was 5 - 3 = 2 units."),        # a difference
])
def test_one_figure_in_two_spellings_of_its_sign_or_a_range_is_no_change(a, b):
    assert _figure_differences(a, [b])[:2] == ([], [])


@pytest.mark.parametrize("restated, source", [
    ("Quantity demanded fell 12.50% while price rose 18.75%.", "Percentage change in quantity = −12.50%; in price = 18.75%."),
    ("Quantity demanded fell by 12.50%.", "Percentage change in quantity = -12.50%."),
    ("A 12.50% drop in quantity demanded.", "Percentage change in quantity = −12.50%."),
])
def test_a_sign_stated_in_words_restates_the_signed_figure(restated, source):
    assert _figure_differences(restated, [source])[:2] == ([], [])


@pytest.mark.parametrize("restated", ["Quantity demanded rose 12.50%.", "The change was 12.50%."])
def test_the_opposite_direction_or_no_direction_is_still_a_change(restated):
    introduced, dropped, _ = _figure_differences(restated, ["Percentage change in quantity = −12.50%."])
    assert introduced and dropped
