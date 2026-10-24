"""Reading view and masked views (docs/STEM_DESIGN.md, section 4.1)."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.stem.normalize import MASK_FILL, MASK_HEAD, blank_ranges, masked_view, prose_view, reading_view


@pytest.mark.parametrize("text", [
    "", "v = 5.0 m s⁻¹", "x − 3 = 0", "a b c d", "zero​width⁠joiner﻿", "F = m⋅a ∙ b ∗ c",
    "R = 5 Ω", "3–5 s", "x = –4", "H–H", "naïve café ΔH° ½gt² √2 ≤ ≥ ≠", "line one\nline two\r\n", "\U0001d465 = 3",
    "co‑operate",
])
def test_reading_view_is_a_one_to_one_character_map(text):
    view = reading_view(text)
    assert len(view) == len(text)
    for a, b in zip(text, view):
        if a == "\n":
            assert b == "\n"


def test_reading_view_normalisations():
    assert reading_view("x − 3") == "x - 3"
    assert reading_view("1 000") == "1 000"
    assert reading_view("a​b") == "a b"                 # a hidden character can split, never join
    assert reading_view("m⋅a") == "m·a" and reading_view("m∙a") == "m·a"
    assert reading_view("a∗b") == "a*b"
    assert reading_view("5 Ω") == "5 Ω"
    assert reading_view("co‑operate") == "co-operate"


def test_en_dash_is_a_minus_only_in_minus_context():
    assert reading_view("x = –4") == "x = -4"
    assert reading_view("(–3)") == "(-3)"
    assert reading_view("3–5 s") == "3–5 s"            # a range between numbers stays a dash
    assert reading_view("H–H") == "H–H"                # a bond stays a dash
    assert reading_view("– and then") == "– and then"  # a dash before a space is punctuation
    assert reading_view("–x") == "-x"                  # at the start, before a letter


def test_other_scripts_are_left_alone():
    # a Cyrillic а that looks like a Latin a is never read as one
    assert reading_view("а = 3") == "а = 3"
    assert reading_view("１２") == "１２"   # full-width digits are not folded


def test_masked_view_keeps_length_and_newlines():
    text = "Then v = 5.0 m s⁻¹.\nNext a = 2.0 m s⁻²."
    a, b = text.index("v"), text.index(".\n")
    c, d = text.index("a ="), len(text) - 1
    view = masked_view(text, [(a, b), (c, d)])
    assert len(view) == len(text)
    assert view[a] == MASK_HEAD and set(view[a + 1:b]) == {MASK_FILL}
    assert view[:a] == text[:a] and view[b:c] == text[b:c] and view[d:] == "."
    span = masked_view("ab\ncd", [(0, 5)])
    assert span == "Xx\nXx"                             # a new line starts a new placeholder head


def test_masked_view_merges_overlaps_and_clips():
    text = "0123456789"
    assert masked_view(text, [(2, 5), (4, 7)]) == "01Xxxxx789"
    assert masked_view(text, [(-5, 2), (8, 50)]) == "Xx234567Xx"
    assert masked_view(text, []) == text
    assert masked_view(text, [(5, 5), (6, 3)]) == text   # empty and reversed ranges are ignored


def test_placeholder_has_no_sentence_punctuation():
    view = masked_view("a 5.0 m. b 'q' \"r\" 1′2″", [(0, 23)])
    assert not any(ch in view for ch in ".!?'\"′″0123456789 ")


def test_blank_ranges_and_prose_view():
    text = "**Answer:** v = 5.0 m s⁻¹"
    blanked = blank_ranges(text, [(0, 2), (9, 11)])
    assert blanked == "  Answer:   v = 5.0 m s⁻¹" and len(blanked) == len(text)
    assert blank_ranges("a\nb", [(0, 3)]) == " \n "
    v = text.index("v")
    prose = prose_view(reading_view(text), [(v, len(text))], [(0, 2), (9, 11)])
    assert prose == "  Answer:   " + "X" + "x" * (len(text) - v - 1)


def test_views_are_linear_on_large_input():
    text = ("x − 3 = 0 – 4 ⋅ y " * 20000)[:300000]
    t = time.perf_counter()
    view = reading_view(text)
    masked = masked_view(view, [(i, i + 5) for i in range(0, len(text), 10)])
    assert len(view) == len(masked) == len(text)
    assert time.perf_counter() - t < 2.0
