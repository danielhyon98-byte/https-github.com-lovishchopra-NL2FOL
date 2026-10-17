"""The exact-value table and rational enclosures for π, e and the functions (design D4, section 7.5).

Two kinds of value come out of this module, and only these two:

* **Exact values** from the table: the sine, cosine and tangent of multiples of 30° and 45°
  (and of the same angles in radians, written as rational multiples of π), as ``q`` or
  ``q·√2`` or ``q·√3`` with ``q`` rational (:func:`exact_trig`); ``log₁₀`` of an exact power of
  ten and ``log_b`` of an exact power of an integer base ``b`` (:func:`exact_log`); ``ln 1 = 0``
  and ``exp 0 = 1``; a rational power ``b^(p/q)`` of a positive rational whose numerator and
  denominator are exact ``q``-th powers (``16^(3/4) = 8``, ``4^1.5 = 8``, ``(8/27)^(2/3) = 4/9``:
  :func:`exact_real_power`). ``sin 30° = 1/2`` stays exact, and a surd is encoded exactly by the
  caller (an auxiliary ``sq ≥ 0, sq·sq = 2``).
* **Enclosures** for everything else: π, e, and sin, cos, tan, arcsin, arccos, arctan, ln,
  log₁₀, log_b and exp of a closed argument. :func:`enclose` returns a rational interval
  ``[lo, hi]`` that contains the true value, of width at most ``10⁻¹⁵·max(1, |mid|)``. The
  engine then decides the stated relation over every value in the interval (Form S), so an
  enclosure can never fail correct work. Agreement is established to the enclosure's width
  only, never as an exact identity between transcendental values.

Method. Interval arithmetic over exact ``Fraction`` endpoints, every operation rounded
outward to :data:`BITS` significant bits, so the true value always stays inside and the
numbers stay small. Series with explicit remainder bounds: Machin's formula for π, the
exponential series after halving the argument, the inverse-hyperbolic-tangent series for the
logarithm after reduction by powers of two, Taylor series for sine and cosine after
reduction modulo 2π (with the sine and cosine Lipschitz bound for an interval argument),
Euler's accelerated series for the arctangent. Every series stops after at most
``max_series_terms`` terms (section 4.9).

Bounds (section 4.9): trigonometric arguments of magnitude at most :data:`MAX_TRIG_ARGUMENT`
(reduced modulo 2π); ln and log₁₀ over ``[10⁻¹⁰⁰, 10¹⁰⁰]``; exp over ``|x| ≤ 700``. Beyond a
bound, :class:`EnclosureError` with code ST-UNDEC-001; outside a function's domain (the
logarithm of a non-positive value, arcsin of 1.5, the tangent at a pole) it carries
ST-UNDEF-001.

Cross-check. :func:`cross_check` compares an enclosure with the standard ``math`` module
(``lo ≤ libm(x) ≤ hi`` within 10⁻⁹ relative). A mismatch means this module is wrong, not
the answer: the caller reports ST-INTERNAL-001 and builds no check. ``math`` is used for
nothing else.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Optional

__all__ = [
    "BITS", "EnclosureError", "ExactTrig", "Interval", "MAX_TRIG_ARGUMENT", "cross_check", "e_interval", "enclose", "exact_log", "exact_real_power",
    "exact_trig", "pi_interval", "width_ok",
]

#: significant bits kept by every outward-rounded operation
BITS = 192
#: largest |x| (in radians) a trigonometric argument may have
MAX_TRIG_ARGUMENT = Fraction(10) ** 9
_MAX_TERMS = 400
_LOG_BOUND = Fraction(10) ** 100
_EXP_BOUND = Fraction(700)
#: absolute slack added to every series tail: covers the outward rounding of partial sums and terms (at most a few hundred roundings of
#: 2^-BITS relative each, on sums bounded by e^4)
_SLACK = Fraction(1, 1 << (BITS - 16))


class EnclosureError(ValueError):
    """An argument outside the bounds (ST-UNDEC-001) or outside the function's domain (ST-UNDEF-001)."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


# --------------------------------------------------------------------------- outward rounding


def _rd(x: Fraction, bits: int = BITS) -> Fraction:
    """``x`` rounded toward −∞ to ``bits`` significant bits."""
    if x == 0:
        return x
    e = abs(x.numerator).bit_length() - x.denominator.bit_length()
    shift = bits - e
    if shift >= 0:
        return Fraction((x.numerator << shift) // x.denominator, 1 << shift)
    return Fraction((x.numerator // (x.denominator << -shift)) << -shift, 1)


def _ru(x: Fraction, bits: int = BITS) -> Fraction:
    return -_rd(-x, bits)


@dataclass(frozen=True)
class Interval:
    """A closed rational interval ``[lo, hi]`` (``lo <= hi``). Arithmetic rounds outward."""

    lo: Fraction
    hi: Fraction

    @staticmethod
    def point(x: Fraction) -> "Interval":
        x = Fraction(x)
        return Interval(x, x)

    @property
    def mid(self) -> Fraction:
        return (self.lo + self.hi) / 2

    @property
    def width(self) -> Fraction:
        return self.hi - self.lo

    @property
    def is_point(self) -> bool:
        return self.lo == self.hi

    def contains(self, x: Fraction) -> bool:
        return self.lo <= x <= self.hi

    def contains_zero(self) -> bool:
        return self.lo <= 0 <= self.hi

    def __add__(self, o: "Interval") -> "Interval":
        return Interval(_rd(self.lo + o.lo), _ru(self.hi + o.hi))

    def __sub__(self, o: "Interval") -> "Interval":
        return Interval(_rd(self.lo - o.hi), _ru(self.hi - o.lo))

    def __neg__(self) -> "Interval":
        return Interval(-self.hi, -self.lo)

    def __mul__(self, o: "Interval") -> "Interval":
        ps = (self.lo * o.lo, self.lo * o.hi, self.hi * o.lo, self.hi * o.hi)
        return Interval(_rd(min(ps)), _ru(max(ps)))

    def __truediv__(self, o: "Interval") -> "Interval":
        if o.contains_zero():
            raise EnclosureError("ST-UNDEF-001", "a division by a value that may be zero")
        qs = (self.lo / o.lo, self.lo / o.hi, self.hi / o.lo, self.hi / o.hi)
        return Interval(_rd(min(qs)), _ru(max(qs)))

    def scale(self, k: Fraction) -> "Interval":
        return self * Interval.point(Fraction(k))

    def abs(self) -> "Interval":
        if self.lo >= 0:
            return self
        if self.hi <= 0:
            return -self
        return Interval(Fraction(0), max(-self.lo, self.hi))

    def power(self, n: int) -> "Interval":
        """``self**n`` for an integer ``n`` (``0 ** 0`` and ``0 ** −n`` are refused)."""
        if n == 0:
            if self.contains_zero():
                raise EnclosureError("ST-UNDEF-001", "0⁰ is undefined")
            return Interval.point(Fraction(1))
        if n < 0:
            return Interval.point(Fraction(1)) / self.power(-n)
        result = Interval.point(Fraction(1))
        base = self
        k = n
        while k:
            if k & 1:
                result = result * base
            k >>= 1
            if k:
                base = base * base
        if n % 2 == 0 and result.lo < 0:  # an even power is never negative; tighten what interval multiplication loses
            return Interval(Fraction(0), result.hi)
        return result

    def hull(self, o: "Interval") -> "Interval":
        return Interval(min(self.lo, o.lo), max(self.hi, o.hi))

    def widen(self, r: Fraction) -> "Interval":
        return Interval(_rd(self.lo - r), _ru(self.hi + r))


def _isqrt_down(x: Fraction, bits: int = BITS) -> Fraction:
    """A rational ``s <= sqrt(x)`` within ``2^-bits`` relative (``x >= 0``)."""
    if x <= 0:
        return Fraction(0)
    e = abs(x.numerator).bit_length() - x.denominator.bit_length()
    k = max(0, bits - e // 2 + 2)
    n = (x.numerator << (2 * k)) // x.denominator
    return Fraction(math.isqrt(n), 1 << k)


def _isqrt_up(x: Fraction, bits: int = BITS) -> Fraction:
    if x <= 0:
        return Fraction(0)
    e = abs(x.numerator).bit_length() - x.denominator.bit_length()
    k = max(0, bits - e // 2 + 2)
    num = x.numerator << (2 * k)
    n = -((-num) // x.denominator)  # ceiling
    r = math.isqrt(n)
    if r * r < n:
        r += 1
    return Fraction(r, 1 << k)


def isqrt_interval(x: Interval) -> Interval:
    """``sqrt`` of an interval (``x.lo`` must be ``>= 0``)."""
    if x.hi < 0:
        raise EnclosureError("ST-UNDEF-001", "the square root of a negative value")
    return Interval(_isqrt_down(max(x.lo, Fraction(0))), _isqrt_up(x.hi))


# --------------------------------------------------------------------------- constants


def _atan_inv(n: int, terms: int) -> Interval:
    """``arctan(1/n)`` for an integer ``n >= 2`` by its alternating series (partial sums bracket it)."""
    s = Fraction(0)
    prev = Fraction(0)
    n2 = n * n
    power = Fraction(1, n)
    for j in range(terms):
        prev = s
        term = power / (2 * j + 1)
        s = s + term if j % 2 == 0 else s - term
        power /= n2
    lo, hi = (prev, s) if prev < s else (s, prev)
    return Interval(_rd(lo), _ru(hi))


@lru_cache(maxsize=1)
def pi_interval() -> Interval:
    """π by Machin's formula, ``16·arctan(1/5) − 4·arctan(1/239)``."""
    a = _atan_inv(5, 50)
    b = _atan_inv(239, 16)
    return a.scale(Fraction(16)) - b.scale(Fraction(4))


def _exp_small(y: Fraction) -> Interval:
    """``exp(y)`` for ``|y| <= 1/2`` by the Taylor series; the tail after the last term is at most
    twice the next term, because each later term is at most half the one before."""
    s = Fraction(0)
    term = Fraction(1)
    k = 0
    while k < _MAX_TERMS:
        s += term
        k += 1
        term = term * y / k
        if abs(term) < Fraction(1, 1 << (BITS + 8)):
            break
        if k % 8 == 0:
            term = _ru(term) if term > 0 else _rd(term)
            s = _rd(s)
    tail = 2 * abs(term) + _SLACK
    return Interval(_rd(s - tail), _ru(s + tail))


@lru_cache(maxsize=1)
def e_interval() -> Interval:
    """Euler's number ``e = exp(1)`` (``exp(1/2)²``)."""
    h = _exp_small(Fraction(1, 2))
    return h * h


def _atanh_series(z: Fraction) -> Interval:
    """``atanh(z)`` for ``0 <= z <= 1/3``: ``Σ z^(2j+1)/(2j+1)``, remainder at most
    ``z^(2n+3)/((2n+3)(1−z²))``."""
    if z == 0:
        return Interval.point(Fraction(0))
    s = Fraction(0)
    z2 = z * z
    power = z
    j = 0
    while j < _MAX_TERMS:
        s += power / (2 * j + 1)
        power *= z2
        j += 1
        if j % 8 == 0:
            power = _ru(power)
            s = _rd(s)
        if power < Fraction(1, 1 << (BITS + 8)):
            break
    tail = power / ((2 * j + 1) * (1 - z2)) + _SLACK
    return Interval(_rd(s - tail), _ru(s + tail))


@lru_cache(maxsize=1)
def _ln2() -> Interval:
    return _atanh_series(Fraction(1, 3)).scale(Fraction(2))


@lru_cache(maxsize=1)
def _ln10() -> Interval:
    return _ln_point(Fraction(10))


# --------------------------------------------------------------------------- point functions


def _ln_point(x: Fraction) -> Interval:
    if x <= 0:
        raise EnclosureError("ST-UNDEF-001", "the logarithm of a non-positive value")
    if x > _LOG_BOUND or x < 1 / _LOG_BOUND:
        raise EnclosureError("ST-UNDEC-001", "a logarithm of an argument beyond 10^±100")
    k = abs(x.numerator).bit_length() - x.denominator.bit_length()
    m = x / (Fraction(2) ** k) if k >= 0 else x * (Fraction(2) ** -k)
    while m >= 2:
        m /= 2
        k += 1
    while m < 1:
        m *= 2
        k -= 1
    z = (m - 1) / (m + 1)
    lnm = _atanh_series(z).scale(Fraction(2))
    return lnm + _ln2().scale(Fraction(k))


def _exp_point(x: Fraction) -> Interval:
    if abs(x) > _EXP_BOUND:
        raise EnclosureError("ST-UNDEC-001", "an exponential of an argument beyond |x| <= 700")
    s = 0
    y = x
    while abs(y) > Fraction(1, 2) and s < 16:
        y /= 2
        s += 1
    r = _exp_small(y)
    for _ in range(s):
        r = r * r
    return r


def _sin_cos_small(m: Fraction) -> tuple[Interval, Interval]:
    """``(sin m, cos m)`` for a rational ``|m| <= 4`` by the Taylor series with the Lagrange remainder
    ``|m|^(n+1)/(n+1)!``."""
    s = Fraction(0)
    c = Fraction(0)
    term = Fraction(1)  # m^k / k!
    k = 0
    while k < _MAX_TERMS:
        r = k % 4
        if r == 0:
            c += term
        elif r == 1:
            s += term
        elif r == 2:
            c -= term
        else:
            s -= term
        k += 1
        term = term * m / k
        if k % 8 == 0:
            term = _ru(term) if term > 0 else _rd(term)
            s, c = _rd(s), _rd(c)
        if abs(term) < Fraction(1, 1 << (BITS + 8)) and k > 4:
            break
    tail = abs(term) * 2 + _SLACK
    return Interval(_rd(s - tail), _ru(s + tail)), Interval(_rd(c - tail), _ru(c + tail))


def _clip(iv: Interval, lo: Fraction, hi: Fraction) -> Interval:
    return Interval(max(iv.lo, lo), min(iv.hi, hi))


def _sin_cos(x: Interval) -> tuple[Interval, Interval]:
    """``(sin x, cos x)`` for an interval argument: reduce the midpoint modulo 2π, evaluate at a
    rational point and widen by the reduction error plus half the width (sine and cosine are
    1-Lipschitz)."""
    if abs(x.lo) > MAX_TRIG_ARGUMENT or abs(x.hi) > MAX_TRIG_ARGUMENT:
        raise EnclosureError("ST-UNDEC-001", "a trigonometric argument beyond |x| <= 10^9 radians")
    pi = pi_interval()
    two_pi = pi.scale(Fraction(2))
    mid = x.mid
    n = math.floor(mid / two_pi.mid + Fraction(1, 2))
    reduced = Interval.point(mid) - two_pi.scale(Fraction(n))
    m = reduced.mid
    s, c = _sin_cos_small(m)
    spread = reduced.width / 2 + x.width / 2
    one = Fraction(1)
    return _clip(s.widen(spread), -one, one), _clip(c.widen(spread), -one, one)


def _atan_point(x: Fraction) -> Interval:
    """``arctan x`` for a rational ``x``: Euler's series for ``|x| <= 1`` (terms all of the sign of
    ``x``, each at most ``x²/(1+x²) <= 1/2`` times the one before, so the tail is at most twice the
    next term), and ``±π/2 − arctan(1/x)`` beyond."""
    if x == 0:
        return Interval.point(Fraction(0))
    if abs(x) > 1:
        half_pi = pi_interval().scale(Fraction(1, 2))
        inner = _atan_point(1 / x)
        return (half_pi - inner) if x > 0 else (-half_pi - inner)
    x2 = x * x
    d = 1 + x2
    term = x / d
    s = Fraction(0)
    n = 0
    while n < _MAX_TERMS:
        s += term
        n += 1
        term = term * (2 * n * x2) / ((2 * n + 1) * d)
        if n % 8 == 0:
            term = _ru(term) if term > 0 else _rd(term)
            s = _rd(s) if s > 0 else _ru(s)
        if abs(term) < Fraction(1, 1 << (BITS + 8)):
            break
    tail = 2 * abs(term) + _SLACK
    return Interval(_rd(s - tail), _ru(s + tail))


def _monotone(f, x: Interval) -> Interval:
    """An increasing function of an interval: ``[f(lo).lo, f(hi).hi]``."""
    if x.is_point:
        return f(x.lo)
    return Interval(f(x.lo).lo, f(x.hi).hi)


def _asin(x: Interval) -> Interval:
    if x.lo < -1 or x.hi > 1:
        raise EnclosureError("ST-UNDEF-001", "arcsin or arccos of a value outside [-1, 1]")

    def at(v: Fraction) -> Interval:
        if v == 1 or v == -1:
            return pi_interval().scale(Fraction(v, 2))
        root = isqrt_interval(Interval.point(1 - v * v))
        quotient = Interval.point(v) / root
        return _monotone(_atan_point, quotient)

    return _monotone(at, x)


# --------------------------------------------------------------------------- public API

_FUNCTIONS = ("sin", "cos", "tan", "arcsin", "arccos", "arctan", "ln", "log10", "log", "exp", "pi", "e")


def enclose(name: str, x: Optional[Interval] = None, *, base: Optional[int] = None) -> Interval:
    """The enclosure of ``name`` at ``x`` (an :class:`Interval`, a point when the argument is exact).
    ``name`` is ``pi`` or ``e`` (no argument), or one of ``sin cos tan`` (``x`` in radians),
    ``arcsin arccos arctan`` (result in radians), ``ln``, ``log10``, ``log`` (``base`` an integer
    ``>= 2``; ``None`` means base 10) or ``exp``. Raises :class:`EnclosureError` outside the bounds or
    the domain."""
    if name == "pi":
        return pi_interval()
    if name == "e":
        return e_interval()
    if x is None:
        raise EnclosureError("ST-UNDEC-001", f"{name} needs an argument")
    if name in ("sin", "cos", "tan"):
        s, c = _sin_cos(x)
        if name == "sin":
            return s
        if name == "cos":
            return c
        if c.contains_zero():
            raise EnclosureError("ST-UNDEF-001", "the tangent at (or too near) a pole")
        return s / c
    if name == "arctan":
        return _monotone(_atan_point, x)
    if name == "arcsin":
        return _asin(x)
    if name == "arccos":
        return pi_interval().scale(Fraction(1, 2)) - _asin(x)
    if name == "exp":
        return _monotone(_exp_point, x)
    if name in ("ln", "log10", "log"):
        if x.lo <= 0:
            raise EnclosureError("ST-UNDEF-001", "the logarithm of a non-positive value")
        ln = _monotone(_ln_point, x)
        if name == "ln":
            return ln
        if name == "log10" or base in (None, 10):
            return ln / _ln10()
        if base < 2:
            raise EnclosureError("ST-UNDEF-001", f"a logarithm to the base {base}")
        return ln / _ln_point(Fraction(base))
    raise EnclosureError("ST-UNDEC-001", f"no enclosure for the function {name!r}")


def width_ok(iv: Interval) -> bool:
    """The design's width bound: ``hi − lo <= 10⁻¹⁵·max(1, |mid|)``."""
    return iv.width <= Fraction(1, 10 ** 15) * max(Fraction(1), abs(iv.mid))


def cross_check(name: str, x: Optional[Interval], iv: Interval, *, base: Optional[int] = None, exponent: Optional[Interval] = None) -> bool:
    """``lo <= libm(x) <= hi`` within 10⁻⁹ relative, using the standard ``math`` module at the
    midpoint of ``x`` (for ``pow``, ``x`` is the base and ``exponent`` the exponent: ``math.pow`` at both midpoints,
    within 10⁻⁹ of the value itself). Returns False on a mismatch (the caller reports ST-INTERNAL-001). An argument
    whose float conversion overflows is accepted as not checkable (True)."""
    try:
        if name == "pi":
            ref = math.pi
        elif name == "e":
            ref = math.e
        elif name == "pow":
            assert x is not None and exponent is not None
            ref = math.pow(float(x.mid), float(exponent.mid))
        else:
            assert x is not None
            v = float(x.mid)
            ref = {
                "sin": math.sin, "cos": math.cos, "tan": math.tan, "arcsin": math.asin, "arccos": math.acos, "arctan": math.atan,
                "ln": math.log, "log10": math.log10, "exp": math.exp,
            }.get(name, None)(v) if name != "log" else (math.log(v, base) if base not in (None, 10) else math.log10(v))
    except (OverflowError, ValueError, ZeroDivisionError, TypeError):
        return True
    if math.isinf(ref) or math.isnan(ref):
        return True
    if name == "pow":
        # math.pow is accurate to a few units in the last place: the value at the midpoints lies in the enclosure of any
        # interval arguments (b^x is monotone in each), so the slack is relative to the value however small it is
        slack = 1e-9 * abs(ref)
    else:
        slack = 1e-9 * max(1.0, abs(ref))
        if x is not None and not x.is_point:
            slack += float(x.width) * 10.0  # an interval argument: the function moves by at most a few times its width here
    return float(iv.lo) - slack <= ref <= float(iv.hi) + slack


# --------------------------------------------------------------------------- the exact-value table


@dataclass(frozen=True)
class ExactTrig:
    """An exact table value ``coefficient · √radicand`` (radicand 1, 2 or 3)."""

    coefficient: Fraction
    radicand: int = 1

    @property
    def is_rational(self) -> bool:
        return self.radicand == 1 or self.coefficient == 0


_SQ2, _SQ3 = 2, 3
#: sin and cos of the special angles in [0, 360) degrees, as (coefficient, radicand)
_SIN_TABLE: dict[int, tuple[Fraction, int]] = {
    0: (Fraction(0), 1), 30: (Fraction(1, 2), 1), 45: (Fraction(1, 2), _SQ2), 60: (Fraction(1, 2), _SQ3), 90: (Fraction(1), 1),
    120: (Fraction(1, 2), _SQ3), 135: (Fraction(1, 2), _SQ2), 150: (Fraction(1, 2), 1), 180: (Fraction(0), 1), 210: (Fraction(-1, 2), 1),
    225: (Fraction(-1, 2), _SQ2), 240: (Fraction(-1, 2), _SQ3), 270: (Fraction(-1), 1), 300: (Fraction(-1, 2), _SQ3), 315: (Fraction(-1, 2), _SQ2),
    330: (Fraction(-1, 2), 1),
}
#: tan of the special angles (None at the poles 90° and 270°)
_TAN_TABLE: dict[int, Optional[tuple[Fraction, int]]] = {
    0: (Fraction(0), 1), 30: (Fraction(1, 3), _SQ3), 45: (Fraction(1), 1), 60: (Fraction(1), _SQ3), 90: None, 120: (Fraction(-1), _SQ3),
    135: (Fraction(-1), 1), 150: (Fraction(-1, 3), _SQ3), 180: (Fraction(0), 1), 210: (Fraction(1, 3), _SQ3), 225: (Fraction(1), 1),
    240: (Fraction(1), _SQ3), 270: None, 300: (Fraction(-1), _SQ3), 315: (Fraction(-1), 1), 330: (Fraction(-1, 3), _SQ3),
}


def exact_trig(name: str, degrees: Fraction) -> Optional[ExactTrig]:
    """The exact value of ``sin``, ``cos`` or ``tan`` at an angle in degrees, when the angle is a
    multiple of 30° or 45°; None otherwise. Raises :class:`EnclosureError` (ST-UNDEF-001) for the
    tangent at a pole."""
    if name not in ("sin", "cos", "tan") or degrees.denominator != 1:
        return None
    d = int(degrees) % 360
    if name == "cos":
        d = (d + 90) % 360  # cos x = sin(x + 90°)
        name = "sin"
    if name == "sin":
        hit = _SIN_TABLE.get(d)
        return None if hit is None else ExactTrig(hit[0], hit[1] if hit[0] != 0 else 1)
    if d not in _TAN_TABLE:
        return None
    hit_t = _TAN_TABLE[d]
    if hit_t is None:
        raise EnclosureError("ST-UNDEF-001", f"tan {d}° is undefined (a pole)")
    return ExactTrig(hit_t[0], hit_t[1] if hit_t[0] != 0 else 1)


def _exact_power(x: Fraction, base: int, limit: int = 400) -> Optional[int]:
    """``k`` with ``base^k == x`` exactly (``k`` may be negative), or None."""
    if x <= 0 or base < 2:
        return None
    if x.numerator == 1 and x.denominator != 1:
        k = _exact_power(Fraction(x.denominator), base, limit)
        return None if k is None else -k
    if x.denominator != 1:
        return None
    n = x.numerator
    k = 0
    while n % base == 0 and k < limit:
        n //= base
        k += 1
    return k if n == 1 else None


#: the most digits the numerator or the denominator of an exact power may have (a larger value is enclosed instead)
EXACT_POWER_MAX_DIGITS = 30


def _integer_root(n: int, q: int) -> Optional[int]:
    """``r`` with ``r**q == n`` exactly (``n >= 0``, ``q >= 1``), or None. Integer bisection over at most
    ``n.bit_length() / q + 2`` steps; no float is used."""
    if n < 2 or q == 1:
        return n
    if q > n.bit_length():
        return None  # 2**q > n: only 0 and 1 are exact q-th powers this small
    lo, hi = 1, 1 << (n.bit_length() // q + 1)
    while lo <= hi:
        mid = (lo + hi) // 2
        m = mid ** q
        if m == n:
            return mid
        if m < n:
            lo = mid + 1
        else:
            hi = mid - 1
    return None


def exact_real_power(base: Fraction, exponent: Fraction) -> Optional[Fraction]:
    """``base ** exponent`` when it is rational: ``base`` positive and its numerator and denominator exact ``q``-th
    powers for the exponent ``p/q`` in lowest terms (``16^(3/4) = 8``, ``4^1.5 = 8``, ``(8/27)^(2/3) = 4/9``,
    ``8^(−2/3) = 1/4``), and ``1^x = 1``. None otherwise (``10^0.4`` and ``2^(−3.5)`` are irrational: the caller
    encloses them), and None when the value would have more than :data:`EXACT_POWER_MAX_DIGITS` digits in its
    numerator or denominator. Exact integer arithmetic only."""
    if base <= 0:
        return None
    if base == 1:
        return Fraction(1)
    p, q = exponent.numerator, exponent.denominator
    rn, rd = _integer_root(base.numerator, q), _integer_root(base.denominator, q)
    if rn is None or rd is None:
        return None
    if abs(p) * max(rn.bit_length(), rd.bit_length()) > EXACT_POWER_MAX_DIGITS * 10 // 3:
        return None  # 2**(10/3 bits per digit): the value would be too long to stay exact here
    value = Fraction(rn, rd) ** p
    if len(str(value.numerator)) > EXACT_POWER_MAX_DIGITS or len(str(value.denominator)) > EXACT_POWER_MAX_DIGITS:
        return None
    return value


def exact_log(name: str, x: Fraction, base: Optional[int] = None) -> Optional[Fraction]:
    """``log₁₀ x`` (``name`` ``log10``, or ``log`` with base None or 10) or ``log_b x`` when ``x`` is an
    exact integer power of the base; ``ln 1 = 0``. None otherwise (the caller encloses)."""
    if name == "ln":
        return Fraction(0) if x == 1 else None
    b = 10 if (name == "log10" or base is None) else base
    if name not in ("log", "log10"):
        return None
    k = _exact_power(x, b)
    return None if k is None else Fraction(k)
