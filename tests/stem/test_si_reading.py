"""``stem.si_reading``: the reading type, the same-length views, the STEM statements, the number and unit readers of
the SI reading (docs/STEM_DESIGN.md, section 12), and adversarial input that never raises and stays fast."""
from __future__ import annotations

import re
import time
from dataclasses import FrozenInstanceError
from fractions import Fraction

import pytest

from epinoic_logic.stem import build_document
from epinoic_logic.stem.si_reading import (
    SI_READING, SI_SCALES, QuantReading, mask_number_marks, si_digits_pattern, si_number, si_prose_view, si_quant_view, si_quote_view, si_statements,
    si_unit, si_unit_pattern,
)

MIXED = ("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻².\n\n"
         "The mass rose from 500 g to 1.0 kg, a doubling.\n\n```python\nprint(\"not a quotation at all\")\n```")


def test_the_reading_is_frozen_and_hashable():
    with pytest.raises(FrozenInstanceError):
        SI_READING.si = False  # type: ignore[misc]
    assert {SI_READING: 1}[QuantReading(name="si", si=True, profile="stem")] == 1
    general = QuantReading(name="general")
    assert general.for_profile("physics") is general and not general.si
    assert SI_READING.for_profile("chemistry") == QuantReading(name="si", si=True, profile="chemistry")
    assert SI_READING.for_profile("not-a-profile").profile == "stem"


@pytest.mark.parametrize("text,expected", [
    ('The ruler is 12" long.', 'The ruler is 12X long.'),
    ('An arc of 30′ and 12″.', 'An arc of 30X and 12X.'),
    ('He wrote "printed in 1802" here.', 'He wrote "printed in 1802" here.'),           # a closing mark after a year stays
    ('A 0.5" rod and "a quote" here.', 'A 0.5X rod and "a quote" here.'),
    ('"Open quote\n\nA 12" ruler.', '"Open quote\n\nA 12X ruler.'),                       # a blank line ends the open quotation
    ('No marks at all.', 'No marks at all.'),
    ('', ''),
])
def test_number_marks(text, expected):
    out = mask_number_marks(text)
    assert out == expected and len(out) == len(text)


def test_views_have_the_texts_length_and_mask_what_they_should():
    q, p, quote = si_quant_view(MIXED), si_prose_view(MIXED), si_quote_view(MIXED)
    assert len(q) == len(p) == len(quote) == len(MIXED)
    assert "(20 - 0)/4.0" not in q and "500 g" in q and "1.0 kg" in q            # maths masked, quantities kept for the prose extractor
    assert "500 g" not in p and "u = 0" not in p and "The mass rose from" in p      # the prose view masks quantities too
    assert "not a quotation" not in quote and "(20 - 0)/4.0" in quote             # the quotation view masks code only
    assert "−" not in si_quant_view("a fall of −20 per cent") and "-20" in si_quant_view("a fall of −20 per cent")


def test_statements_are_the_documents_numbered_as_the_claims():
    stmts = si_statements(MIXED)
    doc = build_document(MIXED, None, "stem")
    assert [(f"s{p}.{n}", a, b) for p, n, a, b in stmts] == [(st.id, st.start, st.end) for st in doc.statements if st.kind != "code"]
    assert all(MIXED[a:b].strip() for _p, _n, a, b in stmts)


@pytest.mark.parametrize("text,value", [
    ("1.5e-6", Fraction(3, 2_000_000)), ("6.67 × 10⁻¹¹", Fraction(667, 10 ** 13)), ("3.0 x 10^8", Fraction(3 * 10 ** 8)), ("1.2*10**6", Fraction(1_200_000)),
    ("6.0E-3", Fraction(3, 500)), ("1.2×10^{6}", Fraction(1_200_000)), ("-4.0", Fraction(-4)), ("−2.5", Fraction(-5, 2)), ("+3", Fraction(3)),
    ("1,200", Fraction(1200)), ("12", Fraction(12)), (".5", Fraction(1, 2)),
])
def test_si_numbers(text, value):
    assert si_number(text) == value


@pytest.mark.parametrize("text", ["x", "", "-", "1e999", "1.0 × 10^999", "7" * 10_000, "12 apples", "1.2.3", "∞"])
def test_si_numbers_refuse_what_is_not_one_bounded_numeral(text):
    assert si_number(text) is None


def test_the_scientific_pattern():
    rx = re.compile(si_digits_pattern())
    for good in ("1.5e-6", "6.67 × 10⁻¹¹", "3.0 x 10^8", "2e5", "1.2*10**6", "1.2·10^{-3}"):
        assert rx.fullmatch(good), good
    for bad in ("1.5e", "10", "2 x 3", "1e2.5"):
        assert not rx.fullmatch(bad), bad


@pytest.mark.parametrize("text,factor,dim_name,affine", [
    ("mm", Fraction(1, 1000), "length", False), ("km/h", Fraction(5, 18), "speed", False), ("m s⁻²", Fraction(1), "acceleration", False),
    ("kg", Fraction(1), "mass", False), ("g", Fraction(1, 1000), "mass", False), ("A", Fraction(1), "current", False), ("K", Fraction(1), "temperature", False),
    ("°C", Fraction(1), "temperature", True), ("mol dm⁻³", Fraction(1000), "concentration", False), ("kJ", Fraction(1000), "energy", False),
    ("µm", Fraction(1, 10 ** 6), "length", False), ("Ω", Fraction(1), "resistance", False),
])
def test_si_units(text, factor, dim_name, affine):
    u = si_unit(text)
    assert u is not None and u.factor == factor and u.dimension == dim_name and u.affine is affine


@pytest.mark.parametrize("text", ["", None, "apples", "kg apples", "xyz"])
def test_unknown_units_are_none(text):
    assert si_unit(text) is None


def test_the_unit_pattern_is_case_sensitive_and_ends_at_a_word_boundary():
    rx = re.compile("(?-i:" + si_unit_pattern() + ")", re.IGNORECASE)
    assert rx.match("K to").group(0) == "K" and rx.match("mm and").group(0) == "mm" and rx.match("m s⁻² then").group(0) == "m s⁻²"
    for not_a_unit in ("marks", "am", "students", "tonnes", "M", "%"):
        m = rx.match(not_a_unit)
        assert m is None or m.group(0) != not_a_unit, not_a_unit
    assert re.compile("(?-i:" + si_unit_pattern(tonne=True) + ")").match("t of").group(0) == "t"


def test_scale_words_are_spelled_out_only():
    assert set(SI_SCALES) == {"thousand", "million", "billion", "bn", "trillion", "quadrillion"}


ADVERSARIAL = [
    ("nested_500", "x = " + "(" * 500 + "1" + ")" * 500 + ' and 12" long.'),
    ("tower", "y = 10^10^10 = " + "10^" * 3000 + "10"),
    ("digits", "x = " + "7" * 10_000 + ' m s⁻¹ "' * 3),
    ("latex", "$$\\begin{align} x &= \\frac{{{ \\left( \\sqrt[ \\text{ \\unknown{ $$ " * 300),
    ("confusables", "а = 3 ν = 2 х = 5 Ꮪ = 1 ０ = １ ‮x = 3 ″′\"" * 200),
    ("quotes", '1" 2" 3" "a" ' * 3000),
]


@pytest.mark.parametrize("name,text", ADVERSARIAL, ids=[n for n, _t in ADVERSARIAL])
def test_adversarial_views_never_raise_and_keep_the_length(name, text):
    t0 = time.perf_counter()
    for view in (si_quant_view, si_prose_view, si_quote_view):
        assert len(view(text)) == len(text)
    assert all(a < b for _p, _n, a, b in si_statements(text))
    assert time.perf_counter() - t0 < 5.0
