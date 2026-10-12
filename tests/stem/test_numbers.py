"""ExactNumber and the number scanner (docs/STEM_DESIGN.md, sections 4.4 and 5.1)."""
from __future__ import annotations

import time
from fractions import Fraction

import pytest

from epinoic_logic.stem.limits import StemLimits
from epinoic_logic.stem.numbers import exact_integer, exact_vulgar, is_ascii_digit, scan_based, scan_number


def num(text: str, **kw):
    scan = scan_number(text, 0, **kw)
    assert scan is not None, text
    assert scan.number is not None, (text, scan.error)
    return scan.number


@pytest.mark.parametrize("text, value, sig, last, half", [
    ("5.0", Fraction(5), 2, -1, Fraction(1, 20)),
    ("0.0250", Fraction(1, 40), 3, -4, Fraction(1, 20000)),
    ("6.0", Fraction(6), 2, -1, Fraction(1, 20)),
    ("1.20 × 10³", Fraction(1200), 3, 1, Fraction(5)),
    ("9.81", Fraction(981, 100), 3, -2, Fraction(1, 200)),
    ("0.0", Fraction(0), 1, -1, Fraction(1, 20)),
    ("25", Fraction(25), 2, 0, Fraction(1, 2)),
    ("1200", Fraction(1200), 2, 0, Fraction(50)),
])
def test_significant_figures_last_place_and_half_width(text, value, sig, last, half):
    n = num(text)
    assert n.value == value
    assert n.sig_figs == sig
    assert n.last_place == last
    assert n.half_width == half


def test_bare_zero_is_exact_zero():
    n = num("0")
    assert n.value == 0 and n.exact and n.half_width == 0
    assert num("0.0").half_width == Fraction(1, 20)  # 0.0 is a measurement


def test_exactness_describes_the_written_form():
    assert num("7").exact
    assert num("200").exact
    assert not num("2.0").exact
    assert not num("6.67e-11").exact
    assert exact_vulgar("½").value == Fraction(1, 2) and exact_vulgar("½").half_width == 0
    assert exact_integer(-4).value == -4 and exact_integer(-4).exact


def test_integer_trailing_zero_rule():
    n = num("1200")
    assert n.trailing_zeros == 2
    assert n.half_width_for(2) == 50     # 2-s.f. operands: the zeros are placeholders
    assert n.half_width_for(3) == 5
    assert n.half_width_for(4) == Fraction(1, 2)
    assert n.half_width_for(None) == 50
    assert num("1250").half_width_for(2) == 5  # the written 5 is significant whatever the operands
    assert num("12.0").half_width_for(1) == Fraction(1, 20)  # a point makes the zeros significant


@pytest.mark.parametrize("text, value, exp", [
    ("1.2 × 10⁶", Fraction(1200000), 6),
    ("1.2 x 10^6", Fraction(1200000), 6),
    ("1.2×10^{6}", Fraction(1200000), 6),
    ("1.2*10**6", Fraction(1200000), 6),
    ("1.2e6", Fraction(1200000), 6),
    ("6.0E-3", Fraction(6, 1000), -3),
    ("6.67 × 10⁻¹¹", Fraction(667, 10 ** 13), -11),
    ("6.67e−11", Fraction(667, 10 ** 13), -11),       # a Unicode minus in the exponent
    ("2.250 \\times 10^{-3}", Fraction(9, 4000), -3),
    ("4.0 x 10^-3", Fraction(1, 250), -3),
    ("1.60*10**-19", Fraction(16, 10 ** 20), -19),
    ("3.0 × 10^(−3)", Fraction(3, 1000), -3),
])
def test_scientific_forms(text, value, exp):
    n = num(text)
    assert n.value == value
    assert n.exponent == exp
    assert n.scientific
    assert n.text == text


def test_bare_powers_of_ten_are_exact():
    for text, value in (("10^(−3)", Fraction(1, 1000)), ("10⁻³", Fraction(1, 1000)), ("10^{6}", Fraction(10 ** 6)), ("10**-19", Fraction(1, 10 ** 19))):
        n = num(text)
        assert n.value == value and n.exact and n.power_of_ten and n.half_width == 0


def test_numbers_that_are_not_scientific():
    assert num("4.0 × 10 = 40").text == "4.0"     # no exponent after the ten
    assert num("2.5 × 100").text == "2.5"
    assert num("2e⁻").text == "2"                 # two electrons, not an exponent
    assert num("2e3x").text == "2"                 # 'e3x' is not an exponent


def test_thousands_groups_and_decimal_comma():
    assert num("1,000,000").value == 1_000_000
    assert num("12,345.5").value == Fraction(123455, 10)
    assert num("1,23").value == 1          # one or two digits after a comma are no thousands group
    assert num("1,5", decimal_comma=True).value == Fraction(3, 2)
    assert num("1,500", thousands_comma=False).value == 1   # inside brackets: two numbers
    orig = "1 000 000"
    assert scan_number("1 000 000", 0, orig=orig).number.value == 1_000_000   # thin spaces, read through the original
    assert scan_number("1 000 000", 0).number.value == 1                         # an ordinary space is no separator
    assert num("0,500").value == 0                                               # no thousands group after a leading zero


def test_nested_power_is_never_folded():
    # 10^10^10 is right-associative: the scanner must not read 10^10 and leave ^10 to multiply it
    assert num("10^10^10").text == "10"
    assert num("2 × 10^3^2").text == "2"


def test_digit_and_exponent_bounds():
    long = scan_number("1" * 31, 0)
    assert long.number is None and long.code == "ST-LIM-001" and "31 written digits" in long.error
    ok = scan_number("1" * 30, 0)
    assert ok.number is not None
    big = scan_number("1e100", 0)
    assert big.number is None and big.code == "ST-LIM-001"
    assert scan_number("1e99", 0).number is not None
    huge = scan_number("1.5 × 10^99999999", 0)
    assert huge.number is None and huge.code == "ST-LIM-001"
    custom = scan_number("123456", 0, limits=StemLimits(max_number_digits=5))
    assert custom.number is None


def test_ten_thousand_digit_numeral_is_rejected_fast():
    text = "9" * 10000
    t = time.perf_counter()
    scan = scan_number(text, 0)
    assert time.perf_counter() - t < 0.5
    assert scan.number is None and scan.code == "ST-LIM-001" and scan.end == 10000


def test_only_ascii_digits_are_digits():
    assert is_ascii_digit("7")
    assert not is_ascii_digit("٣")   # Arabic-Indic three
    assert not is_ascii_digit("²")
    assert not is_ascii_digit("１")   # full-width one
    assert scan_number("١٢", 0) is None
    assert scan_number("１２", 0) is None


@pytest.mark.parametrize("text, value, base", [
    ("0xFF", 255, 16), ("0b1010", 10, 2), ("0o17", 15, 8), ("FF₁₆", 255, 16), ("1010₂", 10, 2), ("1010_2", 10, 2), ("FF_{16}", 255, 16),
    ("377₈", 255, 8), ("255₁₀", 255, 10),
])
def test_based_numerals(text, value, base):
    end, n, _digits = scan_based(text, 0)
    assert end == len(text)
    assert n.value == value and n.base == base and n.exact and n.half_width == 0


def test_based_numerals_reject_invalid_digits_and_unbounded_runs():
    assert scan_based("1012₂", 0) is None      # 2 is no binary digit
    assert scan_based("FF", 0) is None          # no base marker
    assert scan_based("0xZZ", 0) is None
    assert scan_based("1" * 100 + "₂", 0) is None   # beyond max_based_digits


def test_scan_without_values_checks_bounds_only():
    s = scan_number("6.67e-11", 0, build=False)
    assert s.number is None and s.error == "" and s.end == 8
    assert scan_number("1e999", 0, build=False).code == "ST-LIM-001"
