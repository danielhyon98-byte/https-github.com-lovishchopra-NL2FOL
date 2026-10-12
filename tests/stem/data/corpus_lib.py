"""Exact-arithmetic labelling helpers for the STEM corpus (``build_stem_corpus.py``).

Nothing here reads item text for meaning or evaluates it. Every label is computed from
values the builder writes itself, as Python ``Fraction`` arithmetic over decimal strings the
builder chose (``Fraction("2.0")``); the item text is only searched for the step substrings.

The labelling rule is deliberately stricter than the STEM tolerance rule in both directions,
so a label cannot depend on a reading the implementation might choose:

* **A correct step** holds at the written values (the point every admissible reading
  contains: carried intermediates, written constants and enclosures all contain their written
  value): ``|C − S| ≤ h(S)`` with τ = 0 and the narrowest half-width (``h = 0`` when the step
  is exact work, every operand and ``S`` an integer or a fraction with no units).
* **A fault** fails over the widest reading: every decimal operand ranges over
  ``[w − h(w), w + h(w)]`` (integers over their trailing-zero width), every written constant
  over the hull of that and its booklet value, and the band uses the widest half-width
  (trailing zeros of an integer not significant) and τ = 1/20 (the ``≈`` slack). A fault is
  labelled only when no value in that range comes within the band.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction as F
from typing import Callable, Optional, Union

HALF = F(1, 2)
TAU_MAX = F(1, 20)
_SPEC = re.compile(r"^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$")


# ------------------------------------------------------------------------------------------- numbers
@dataclass(frozen=True)
class Written:
    """A number as the builder writes it: ``spec`` is an ASCII decimal (``"6.0"``, ``"2.5e7"``, ``"1200"``, ``"3/4"``)."""
    spec: str
    value: F
    h_narrow: F  # half a unit in the last written digit (0 for an exact integer or fraction)
    h_wide: F    # the same, with an integer's trailing zeros not significant
    exact: bool  # an integer or a fraction with no decimal point


def W(spec: str, *, exact_int: bool = False) -> Written:
    if "/" in spec:
        p, q = spec.split("/")
        return Written(spec, F(int(p), int(q)), F(0), F(0), True)
    m = _SPEC.match(spec)
    if not m:
        raise ValueError(f"bad number spec {spec!r}")
    sign, ip, fp, ex = m.groups()
    e = int(ex) if ex else 0
    val = F(int(ip + (fp or "")), 10 ** len(fp or "")) * F(10) ** e
    if sign == "-":
        val = -val
    if fp is not None:
        h = HALF * F(10) ** (e - len(fp))
        return Written(spec, val, h, h, False)
    if ex:
        h = HALF * F(10) ** e
        return Written(spec, val, h, h, False)
    trailing = len(ip) - len(ip.rstrip("0")) if val != 0 else 0
    if val == 0:
        return Written(spec, val, F(0), F(0), True)
    narrow = F(0) if exact_int else HALF
    return Written(spec, val, narrow, HALF * F(10) ** trailing, True)


def fmt(x: F) -> str:
    """An exact value for a note: an integer, a terminating decimal, or p/q (integer arithmetic only)."""
    x = F(x)
    if x.denominator == 1:
        return str(x.numerator)
    d, k2, k5 = x.denominator, 0, 0
    while d % 2 == 0:
        d //= 2
        k2 += 1
    while d % 5 == 0:
        d //= 5
        k5 += 1
    if d != 1:
        return f"{x.numerator}/{x.denominator}"
    k = max(k2, k5)
    y = (x * 10 ** k).numerator
    sign = "-" if y < 0 else ""
    digits = str(abs(y)).rjust(k + 1, "0")
    return f"{sign}{digits[:-k]}.{digits[-k:]}"


def round_sig(x: F, sf: int) -> str:
    """``x`` rounded half away from zero to ``sf`` significant figures, as a plain decimal spec (no exponent)."""
    if x == 0:
        return "0" if sf <= 1 else "0." + "0" * (sf - 1)
    sign = "-" if x < 0 else ""
    a = abs(x)
    e = 0
    while a >= 10:
        a /= 10
        e += 1
    while a < 1:
        a *= 10
        e -= 1
    # a in [1, 10): keep sf digits
    scaled = a * F(10) ** (sf - 1)
    n = int(scaled)
    if scaled - n >= HALF:
        n += 1
    if n >= 10 ** sf:  # 9.96 -> 10.0
        n //= 10
        e += 1
    dp = sf - 1 - e
    if dp > 0:
        digits = str(n).rjust(dp + 1, "0")
        return f"{sign}{digits[:-dp]}.{digits[-dp:]}"
    return sign + str(n * 10 ** (-dp))


def round_dp(x: F, dp: int) -> str:
    sign = "-" if x < 0 else ""
    scaled = abs(x) * F(10) ** dp
    n = int(scaled)
    if scaled - n >= HALF:
        n += 1
    if dp > 0:
        digits = str(n).rjust(dp + 1, "0")
        return f"{sign}{digits[:-dp]}.{digits[-dp:]}"
    return sign + str(n)


# ------------------------------------------------------------------------------------------ intervals
@dataclass(frozen=True)
class Iv:
    lo: F
    hi: F

    @staticmethod
    def of(x: "Union[Iv, F, int]") -> "Iv":
        if isinstance(x, Iv):
            return x
        return Iv(F(x), F(x))

    def __add__(self, o):
        o = Iv.of(o)
        return Iv(self.lo + o.lo, self.hi + o.hi)

    __radd__ = __add__

    def __neg__(self):
        return Iv(-self.hi, -self.lo)

    def __sub__(self, o):
        return self + (-Iv.of(o))

    def __rsub__(self, o):
        return Iv.of(o) + (-self)

    def __mul__(self, o):
        o = Iv.of(o)
        ps = [self.lo * o.lo, self.lo * o.hi, self.hi * o.lo, self.hi * o.hi]
        return Iv(min(ps), max(ps))

    __rmul__ = __mul__

    def __truediv__(self, o):
        o = Iv.of(o)
        if o.lo <= 0 <= o.hi:
            raise ZeroDivisionError("divisor interval contains zero")
        return self * Iv(1 / o.hi, 1 / o.lo)

    def __rtruediv__(self, o):
        return Iv.of(o) / self

    def __pow__(self, n: int):
        if n == 0:
            return Iv(F(1), F(1))
        if n < 0:
            return Iv(F(1), F(1)) / (self ** (-n))
        cands = [self.lo ** n, self.hi ** n]
        lo, hi = min(cands), max(cands)
        if n % 2 == 0 and self.lo <= 0 <= self.hi:
            lo = F(0)
        return Iv(lo, hi)

    def hull(self, x: F) -> "Iv":
        return Iv(min(self.lo, x), max(self.hi, x))


def isqrt_iv(x: Iv) -> Iv:
    """A rational interval containing √[x.lo, x.hi] (bisection on exact squares; never a float)."""
    def lower(v: F) -> F:
        lo, hi = F(0), max(F(1), v)
        for _ in range(80):
            mid = (lo + hi) / 2
            if mid * mid <= v:
                lo = mid
            else:
                hi = mid
        return lo

    def upper(v: F) -> F:
        lo, hi = F(0), max(F(1), v)
        for _ in range(80):
            mid = (lo + hi) / 2
            if mid * mid >= v:
                hi = mid
            else:
                lo = mid
        return hi

    return Iv(lower(max(x.lo, F(0))), upper(x.hi))


# --------------------------------------------------------------------------------------- valuations
Val = Callable[[str], Union[F, Iv]]


def point(spec: str, *, const: Optional[str] = None) -> F:
    return W(spec).value


def widest(spec: str, *, const: Optional[str] = None) -> Iv:
    w = W(spec)
    iv = Iv(w.value - w.h_wide, w.value + w.h_wide)
    if const is not None:
        iv = iv.hull(F(const))
    return iv


def remap(base: Callable, mapping: dict[str, str]) -> Callable:
    """A valuation that reads ``mapping[spec]`` in place of ``spec`` (a substituted value changed by a mutation)."""
    return lambda spec, const=None: base(mapping.get(spec, spec), const=const)


# ---------------------------------------------------------------------------------------- the bands
def acceptance(S: F, h: F, tau: F) -> tuple[F, F]:
    """The set {C : |C − S| ≤ h + τ|C|} as a closed interval (it is one for τ < 1)."""
    # lower end: the smallest C with |C − S| − τ|C| ≤ h
    if S - h >= 0:
        lo = (S - h) / (1 + tau)
    else:
        lo = (S - h) / (1 - tau)
    if S + h <= 0:
        hi = (S + h) / (1 + tau)
    else:
        hi = (S + h) / (1 - tau)
    return lo, hi


def holds_point(C: F, S: Written, *, exact_work: bool = False, tau: F = F(0)) -> bool:
    h = F(0) if exact_work else S.h_narrow
    return abs(C - S.value) <= h + tau * abs(C)


def fails_widest(Civ: Iv, S: Written, *, tau: F = TAU_MAX) -> bool:
    lo, hi = acceptance(S.value, S.h_wide, tau)
    return Civ.hi < lo or Civ.lo > hi


def proof_eq(C: F, Civ: Iv, S: Written, *, holds: bool, exact_work: bool = False) -> dict:
    if holds:
        ok = holds_point(C, S, exact_work=exact_work)
        h = F(0) if exact_work else S.h_narrow
        return {"rule": "holds at the written values: |C - S| <= h(S), tau = 0", "C": fmt(C), "S": S.spec, "h": fmt(h), "tau": "0", "holds": ok}
    ok = fails_widest(Civ, S)
    lo, hi = acceptance(S.value, S.h_wide, TAU_MAX)
    return {"rule": "fails over the widest reading: no C in [C_lo, C_hi] has |C - S| <= h_wide(S) + |C|/20", "C": fmt(C), "C_lo": fmt(Civ.lo),
            "C_hi": fmt(Civ.hi), "S": S.spec, "h_wide": fmt(S.h_wide), "tau": "1/20", "band": [fmt(lo), fmt(hi)], "fails": ok}


def leading_digit_slip(spec: str) -> str:
    """The same written number with its leading significant digit moved by 3 (d+3 for d ≤ 6, else d−3):
    a change of at least 3 units in the leading place, so it can never round back."""
    for i, ch in enumerate(spec):
        if ch in "123456789":
            d = int(ch)
            nd = d + 3 if d <= 6 else d - 3
            return spec[:i] + str(nd) + spec[i + 1:]
    raise ValueError(f"no significant digit in {spec!r}")


def slip_text(text: str) -> str:
    """The same digit change applied to the first significant digit of a rendered number."""
    return leading_digit_slip(text)
