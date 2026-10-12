"""Exact-value table and rational enclosures (docs/STEM_DESIGN.md, D4 and section 7.5): width and
containment over grids (special angles included), both ends of every bound, the exact table,
domain errors, and the cross-check against ``math``."""
from __future__ import annotations

import math
import time
from fractions import Fraction

import pytest

from epinoic_logic.stem.enclosures import (
    EnclosureError, ExactTrig, Interval, cross_check, e_interval, enclose, exact_log, exact_trig, isqrt_interval, pi_interval, width_ok,
)

# reference digits (truncated, so the true value lies in [T, T + 10^-50])
PI_50 = Fraction(314159265358979323846264338327950288419716939937510, 10 ** 50)
E_50 = Fraction(271828182845904523536028747135266249775724709369995, 10 ** 50)
LN2_50 = Fraction(69314718055994530941723212145817656807550013436025, 10 ** 50)
SQRT2_50 = Fraction(141421356237309504880168872420969807856967187537694, 10 ** 50)
ULP = Fraction(1, 10 ** 50)


def _overlaps_truth(iv: Interval, truncated: Fraction) -> bool:
    return iv.lo <= truncated + ULP and iv.hi >= truncated


def test_pi_e_ln2_and_sqrt2_contain_the_reference_digits():
    assert _overlaps_truth(pi_interval(), PI_50) and width_ok(pi_interval())
    assert _overlaps_truth(e_interval(), E_50) and width_ok(e_interval())
    ln2 = enclose("ln", Interval.point(Fraction(2)))
    assert _overlaps_truth(ln2, LN2_50) and width_ok(ln2)
    s2 = isqrt_interval(Interval.point(Fraction(2)))
    assert _overlaps_truth(s2, SQRT2_50)
    assert pi_interval().width < Fraction(1, 10 ** 50)


DEGREES = list(range(-360, 721, 7)) + [0, 30, 45, 60, 90, 120, 135, 150, 180, 270, 359, 360]


@pytest.mark.parametrize("name", ["sin", "cos"])
def test_sine_and_cosine_over_a_degree_grid(name):
    pi = pi_interval()
    for d in DEGREES:
        x = pi.scale(Fraction(d, 180))
        iv = enclose(name, x)
        assert width_ok(iv), (name, d)
        assert cross_check(name, x, iv), (name, d)
        ref = getattr(math, name)(math.radians(d))
        assert float(iv.lo) - 1e-12 <= ref <= float(iv.hi) + 1e-12


def test_tangent_over_a_grid_avoiding_poles():
    for d in DEGREES:
        if d % 180 == 90:
            continue
        x = pi_interval().scale(Fraction(d, 180))
        iv = enclose("tan", x)
        assert width_ok(iv) and cross_check("tan", x, iv), d


def test_tangent_at_a_pole_is_undefined():
    with pytest.raises(EnclosureError) as e:
        enclose("tan", pi_interval().scale(Fraction(1, 2)))
    assert e.value.code == "ST-UNDEF-001"


@pytest.mark.parametrize("x", [Fraction(k, 7) for k in range(-70, 71, 3)] + [Fraction(1, 10 ** 12), Fraction(10) ** 9, -Fraction(10) ** 9])
def test_sine_at_rational_radians(x):
    for name in ("sin", "cos"):
        iv = enclose(name, Interval.point(x))
        assert width_ok(iv) and cross_check(name, Interval.point(x), iv), (name, x)


def test_trig_argument_bound():
    with pytest.raises(EnclosureError) as e:
        enclose("sin", Interval.point(Fraction(10) ** 9 + 1))
    assert e.value.code == "ST-UNDEC-001"


@pytest.mark.parametrize("x", [Fraction(1, 10 ** 100), Fraction(1, 10 ** 50), Fraction(1, 3), Fraction(1), Fraction(2), Fraction(10),
                               Fraction(12345, 7), Fraction(10) ** 50, Fraction(10) ** 100])
def test_logarithms_over_their_range(x):
    for name in ("ln", "log10"):
        iv = enclose(name, Interval.point(x))
        assert width_ok(iv) and cross_check(name, Interval.point(x), iv), (name, x)
    iv = enclose("log", Interval.point(x), base=2)
    assert width_ok(iv) and cross_check("log", Interval.point(x), iv, base=2)


@pytest.mark.parametrize("x,code", [(Fraction(0), "ST-UNDEF-001"), (Fraction(-1), "ST-UNDEF-001"), (Fraction(10) ** 100 + 1, "ST-UNDEC-001"),
                                    (Fraction(1, 10 ** 101), "ST-UNDEC-001")])
def test_logarithm_domain_and_bounds(x, code):
    with pytest.raises(EnclosureError) as e:
        enclose("ln", Interval.point(x))
    assert e.value.code == code


@pytest.mark.parametrize("x", [Fraction(-700), Fraction(-50), Fraction(-1, 3), Fraction(0), Fraction(1, 10 ** 9), Fraction(1), Fraction(7, 2),
                               Fraction(100), Fraction(700)])
def test_exponential_over_its_range(x):
    iv = enclose("exp", Interval.point(x))
    assert width_ok(iv) and cross_check("exp", Interval.point(x), iv), x


def test_exponential_bound():
    for x in (Fraction(701), Fraction(-701)):
        with pytest.raises(EnclosureError) as e:
            enclose("exp", Interval.point(x))
        assert e.value.code == "ST-UNDEC-001"


@pytest.mark.parametrize("x", [Fraction(-1), Fraction(-1, 2), Fraction(-1, 7), Fraction(0), Fraction(1, 3), Fraction(1, 2), Fraction(99, 100), Fraction(1)])
def test_inverse_sine_and_cosine(x):
    for name in ("arcsin", "arccos"):
        iv = enclose(name, Interval.point(x))
        assert width_ok(iv) and cross_check(name, Interval.point(x), iv), (name, x)


@pytest.mark.parametrize("x", [Fraction(-10) ** 6, Fraction(-3), Fraction(-1), Fraction(-1, 2), Fraction(0), Fraction(1, 2), Fraction(1), Fraction(3),
                               Fraction(10) ** 6])
def test_inverse_tangent(x):
    iv = enclose("arctan", Interval.point(x))
    assert width_ok(iv) and cross_check("arctan", Interval.point(x), iv)


def test_inverse_sine_outside_its_domain():
    for x in (Fraction(3, 2), Fraction(-11, 10)):
        with pytest.raises(EnclosureError) as e:
            enclose("arcsin", Interval.point(x))
        assert e.value.code == "ST-UNDEF-001"


def test_identities_hold_over_the_enclosures():
    x = Interval.point(Fraction(7, 5))
    s, c = enclose("sin", x), enclose("cos", x)
    one = s * s + c * c
    assert one.contains(Fraction(1))
    y = Fraction(37, 3)
    back = enclose("exp", enclose("ln", Interval.point(y)))
    assert back.contains(y)
    t = enclose("tan", x)
    assert (s / c).lo <= t.hi and t.lo <= (s / c).hi
    z = Interval.point(Fraction(1, 3))
    assert enclose("sin", enclose("arcsin", z)).contains(Fraction(1, 3))


def test_an_interval_argument_contains_the_endpoint_values():
    x = Interval(Fraction(1), Fraction(11, 10))
    iv = enclose("sin", x)
    for v in (Fraction(1), Fraction(21, 20), Fraction(11, 10)):
        p = enclose("sin", Interval.point(v))
        assert iv.lo <= p.lo and p.hi <= iv.hi
    mono = enclose("ln", Interval(Fraction(2), Fraction(3)))
    assert mono.lo <= enclose("ln", Interval.point(Fraction(2))).lo and mono.hi >= enclose("ln", Interval.point(Fraction(3))).hi


def test_outward_rounding_contains_exact_results():
    a = Interval.point(Fraction(1, 3))
    b = Interval.point(Fraction(2, 7))
    assert (a + b).contains(Fraction(13, 21))
    assert (a * b).contains(Fraction(2, 21))
    assert (a / b).contains(Fraction(7, 6))
    assert (a - b).contains(Fraction(1, 21))
    assert a.power(5).contains(Fraction(1, 243))
    assert Interval(Fraction(-2), Fraction(1)).power(2).lo == 0
    with pytest.raises(EnclosureError):
        a / Interval(Fraction(-1), Fraction(1))
    with pytest.raises(EnclosureError):
        Interval(Fraction(0), Fraction(0)).power(0)


# --------------------------------------------------------------------------- the exact table


@pytest.mark.parametrize("name,deg,coef,rad", [
    ("sin", 30, Fraction(1, 2), 1), ("sin", 150, Fraction(1, 2), 1), ("sin", 45, Fraction(1, 2), 2), ("sin", 60, Fraction(1, 2), 3),
    ("sin", 90, Fraction(1), 1), ("sin", 270, Fraction(-1), 1), ("sin", -30, Fraction(-1, 2), 1), ("sin", 390, Fraction(1, 2), 1),
    ("cos", 0, Fraction(1), 1), ("cos", 60, Fraction(1, 2), 1), ("cos", 30, Fraction(1, 2), 3), ("cos", 180, Fraction(-1), 1), ("cos", 90, Fraction(0), 1),
    ("tan", 45, Fraction(1), 1), ("tan", 30, Fraction(1, 3), 3), ("tan", 60, Fraction(1), 3), ("tan", 135, Fraction(-1), 1), ("tan", 0, Fraction(0), 1),
])
def test_exact_trig(name, deg, coef, rad):
    hit = exact_trig(name, Fraction(deg))
    assert hit == ExactTrig(coef, rad)
    # and the enclosure of the same angle contains the exact value
    iv = enclose(name, pi_interval().scale(Fraction(deg, 180)))
    exact = isqrt_interval(Interval.point(Fraction(rad))).scale(coef)
    assert iv.lo <= exact.hi and exact.lo <= iv.hi


def test_exact_trig_misses_and_poles():
    assert exact_trig("sin", Fraction(15)) is None
    assert exact_trig("sin", Fraction(61, 2)) is None
    assert exact_trig("ln", Fraction(30)) is None
    for d in (90, 270, -90):
        with pytest.raises(EnclosureError) as e:
            exact_trig("tan", Fraction(d))
        assert e.value.code == "ST-UNDEF-001"


@pytest.mark.parametrize("name,x,base,expected", [
    ("log", Fraction(1000), None, 3), ("log10", Fraction(1, 100), None, -2), ("log", Fraction(32), 2, 5), ("log", Fraction(1, 8), 2, -3),
    ("ln", Fraction(1), None, 0), ("log", Fraction(1), None, 0), ("log", Fraction(81), 3, 4),
])
def test_exact_logs(name, x, base, expected):
    assert exact_log(name, x, base) == Fraction(expected)


@pytest.mark.parametrize("name,x,base", [("log", Fraction(2), None), ("log", Fraction(0), None), ("ln", Fraction(2), None), ("log", Fraction(30), 2),
                                         ("log", Fraction(-8), 2), ("exp", Fraction(1), None)])
def test_no_exact_log(name, x, base):
    assert exact_log(name, x, base) is None


def test_cross_check_detects_a_wrong_enclosure():
    wrong = Interval(Fraction(1, 2), Fraction(51, 100))
    assert not cross_check("sin", Interval.point(Fraction(1)), wrong)
    assert cross_check("sin", Interval.point(Fraction(1)), enclose("sin", Interval.point(Fraction(1))))


def test_enclosures_are_fast():
    t0 = time.perf_counter()
    for k in range(1, 60):
        x = Interval.point(Fraction(k, 3))
        enclose("sin", x), enclose("ln", x), enclose("exp", x), enclose("arctan", x)
    assert time.perf_counter() - t0 < 3.0
