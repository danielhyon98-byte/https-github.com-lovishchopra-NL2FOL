"""Data-booklet constants: values, accepted written forms, units, profiles, ambiguous letters.

Design decision D3 (docs/STEM_DESIGN.md, section 2) uses this table in exactly two ways,
and never to supply data the answer did not write:

* **D3a, a written constant widens.** A literal the answer wrote that matches a table
  constant at its written precision (``9.8`` for g, ``6.6 × 10⁻³⁴`` for Planck's constant,
  ``3.00 × 10⁸`` for the speed of light) may take any value in the hull of its rounding
  interval ``[w − h(w), w + h(w)]`` and the constant's accepted values. This only ever
  widens what the engine accepts, so it can never cause a false error.
  :func:`match_written` decides the match (significant figures, dimension, rounding
  interval), and :meth:`ConstantMatch.interval` gives the hull.
* **D3b, an unstated standard symbol may take its booklet value.** An unbound symbol whose
  name is a table symbol (``h``, ``c``, ``G``, ``N_A`` ...) may take the hull of its accepted
  values, but only when a dimension check against the stated result confirms the reading
  (the caller supplies the dimension the symbol must have; :func:`booklet_reading`). The
  check that uses it carries ``failure_severity="warning"`` and grounds the reading as an
  ``assumption``, so the engine lists it in ``ungrounded_dependencies`` and a failure is
  INT-SUBJ-004, never an error.

Every value is an exact ``Fraction`` built from integer pairs. The table holds the IB data
booklet values (physics and chemistry) together with the exact SI values (since 2019) or
the CODATA 2018 values, so a hull covers whichever an answer used. Letters that name
something else in ordinary use are recorded in ``ambiguous`` (``h`` is also a height or an
hour, ``c`` a specific heat capacity, ``e`` Euler's number, ``R`` a resistance ...). The
dimension guard is what keeps those readings apart. Molar masses and other substance data
are not here: they are data, and data go to the evidence service (section 7.8).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from .units import DIMENSIONLESS, Dimension, parse_unit

__all__ = ["CONSTANTS", "Constant", "ConstantMatch", "BookletReading", "booklet_reading", "constant_by_key", "constants_for_symbol", "match_written"]


def _f(mantissa: str, exponent: int = 0) -> Fraction:
    """``mantissa × 10^exponent`` from a validated digit string (no evaluation of text: the digits are table data)."""
    neg = mantissa.startswith("-")
    body = mantissa[1:] if neg else mantissa
    if "." in body:
        whole, frac = body.split(".")
    else:
        whole, frac = body, ""
    value = Fraction(int(whole + frac), 10 ** len(frac)) * (Fraction(10) ** exponent)
    return -value if neg else value


@dataclass(frozen=True)
class Constant:
    """One table constant. ``value`` is the booklet value in SI; ``accepted`` lists every other
    accepted SI value (the exact SI or CODATA value, other booklet roundings). ``unit`` is the
    SI unit as text and ``dim`` its dimension. ``symbols`` are the names the front end gives the
    constant's usual symbols; ``profiles`` restricts the unstated-symbol reading (D3b) to some
    STEM profiles (None: every STEM profile). ``written`` lists additional written values the
    D3a match accepts even when the rounding interval would not contain the booklet value
    (``10`` for g, only together with a unit of the right dimension)."""

    key: str
    name: str
    symbols: tuple[str, ...]
    value: Fraction
    accepted: tuple[Fraction, ...]
    unit: str
    dim: Dimension
    profiles: Optional[frozenset[str]] = None
    ambiguous: str = ""
    written: tuple[Fraction, ...] = ()

    @property
    def values(self) -> tuple[Fraction, ...]:
        return (self.value,) + tuple(v for v in self.accepted if v != self.value)

    @property
    def hull(self) -> tuple[Fraction, Fraction]:
        vs = self.values
        return min(vs), max(vs)


_SCI = frozenset({"physics", "chemistry", "biology", "ess", "sports_science", "design_technology", "stem"})
_PHYS = frozenset({"physics", "stem", "design_technology", "sports_science"})
_CHEM = frozenset({"chemistry", "biology", "ess", "stem", "physics"})


def _dim(unit: str) -> Dimension:
    u = parse_unit(unit)
    if u is None or u.unknown or u.dim is None:  # pragma: no cover - the table is checked by tests
        raise ValueError(f"constant unit {unit!r} is not readable")
    return u.dim


def _c(key: str, name: str, symbols: tuple[str, ...], value: Fraction, accepted: tuple[Fraction, ...], unit: str, profiles: Optional[frozenset[str]] = None,
       ambiguous: str = "", written: tuple[Fraction, ...] = ()) -> Constant:
    return Constant(key, name, symbols, value, accepted, unit, _dim(unit) if unit else DIMENSIONLESS, profiles, ambiguous, written)


#: the table (IB physics and chemistry data booklets; exact SI and CODATA 2018 values as accepted alternatives)
CONSTANTS: tuple[Constant, ...] = (
    _c("g", "acceleration of free fall near the Earth's surface", ("g", "g_0", "g_E"), _f("9.81"), (_f("9.80665"), _f("9.8"), _f("9.807")), "m s^-2",
       _SCI, ambiguous="g is also the gram after a number", written=(Fraction(10),)),
    _c("G", "gravitational constant", ("G",), _f("6.67", -11), (_f("6.6743", -11), _f("6.674", -11)), "N m^2 kg^-2", _PHYS),
    _c("N_A", "Avogadro constant", ("N_A", "NA", "L"), _f("6.02", 23), (_f("6.02214076", 23), _f("6.022", 23)), "mol^-1", _SCI,
       ambiguous="L is also a length, a latent heat or the litre"),
    _c("R", "molar gas constant", ("R",), _f("8.31", 0), (_f("8.314462618"), _f("8.314"), _f("8.3145")), "J K^-1 mol^-1", _SCI,
       ambiguous="R is also a resistance or a radius"),
    _c("k_B", "Boltzmann constant", ("k_B", "k"), _f("1.38", -23), (_f("1.380649", -23), _f("1.381", -23)), "J K^-1", _PHYS,
       ambiguous="k is also the Coulomb constant, a spring constant or a rate constant"),
    _c("sigma", "Stefan-Boltzmann constant", ("σ",), _f("5.67", -8), (_f("5.670374419", -8),), "W m^-2 K^-4", _PHYS,
       ambiguous="σ is also a stress or a conductivity"),
    _c("k_e", "Coulomb constant", ("k", "k_e"), _f("8.99", 9), (_f("8.9875517923", 9),), "N m^2 C^-2", _PHYS),
    _c("eps_0", "permittivity of free space", ("ε_0", "ϵ_0"), _f("8.85", -12), (_f("8.8541878128", -12),), "C^2 N^-1 m^-2", _PHYS),
    _c("mu_0", "permeability of free space", ("μ_0",), _f("1.26", -6), (_f("1.25663706212", -6), _f("1.257", -6)), "T m A^-1", _PHYS),
    _c("c", "speed of light in a vacuum", ("c", "c_0"), _f("3.00", 8), (Fraction(299792458), _f("2.998", 8)), "m s^-1", _SCI,
       ambiguous="c is also a specific heat capacity, a concentration or a coefficient"),
    _c("h", "Planck constant", ("h",), _f("6.63", -34), (_f("6.62607015", -34), _f("6.626", -34)), "J s", _SCI,
       ambiguous="h is also a height or the hour"),
    _c("e", "elementary charge", ("e",), _f("1.60", -19), (_f("1.602176634", -19), _f("1.602", -19)), "C", _SCI,
       ambiguous="e is also Euler's number"),
    _c("m_e", "electron rest mass", ("m_e",), _f("9.110", -31), (_f("9.1093837015", -31), _f("9.11", -31)), "kg", _PHYS),
    _c("m_p", "proton rest mass", ("m_p",), _f("1.673", -27), (_f("1.67262192369", -27),), "kg", _PHYS),
    _c("m_n", "neutron rest mass", ("m_n",), _f("1.675", -27), (_f("1.67492749804", -27),), "kg", _PHYS),
    _c("u", "unified atomic mass unit", ("u",), _f("1.661", -27), (_f("1.66053906660", -27),), "kg", _PHYS, ambiguous="u is also an initial speed"),
    _c("b_W", "Wien's displacement constant", ("b",), _f("2.90", -3), (_f("2.897771955", -3), _f("2.9", -3)), "m K", _PHYS),
    _c("F", "Faraday constant", ("F",), Fraction(96500), (_f("96485.33212"), Fraction(96485)), "C mol^-1", _CHEM, ambiguous="F is also a force"),
    _c("V_m", "molar volume of an ideal gas at STP", ("V_m",), _f("22.7", -3), (_f("22.71095464", -3), _f("22.4", -3)), "m^3 mol^-1", _CHEM),
    _c("c_water", "specific heat capacity of water", ("c_w", "c_water"), Fraction(4180), (Fraction(4186), Fraction(4184), Fraction(4200), _f("4.18", 3)),
       "J kg^-1 K^-1", _SCI),
    _c("K_w", "ionic product of water at 298 K", ("K_w", "Kw"), _f("1.00", -14), (_f("1.0", -14),), "", _CHEM),
)

_BY_KEY = {c.key: c for c in CONSTANTS}


def constant_by_key(key: str) -> Constant:
    return _BY_KEY[key]


def constants_for_symbol(name: str, profile_key: str = "") -> tuple[Constant, ...]:
    """Table constants whose usual symbol is ``name`` and whose profiles include ``profile_key``
    (every profile when ``profile_key`` is empty)."""
    out = []
    for c in CONSTANTS:
        if name not in c.symbols:
            continue
        if profile_key and c.profiles is not None and profile_key not in c.profiles:
            continue
        out.append(c)
    return tuple(out)


@dataclass(frozen=True)
class BookletReading:
    """D3b: the booklet reading of an unstated standard symbol. ``lo``/``hi`` (SI) is the hull of
    the constant's accepted values; the check that uses it fails only at warning severity."""

    symbol: str
    constant: Constant
    lo: Fraction
    hi: Fraction

    @property
    def note(self) -> str:
        return (f"data-booklet value supplied by the STEM pack for '{self.symbol}' ({self.constant.name}, {_show(self.constant.value)} "
                f"{self.constant.unit or '(dimensionless)'}); the report did not state it")


def booklet_reading(name: str, profile_key: str, required: Optional[Dimension]) -> Optional[BookletReading]:
    """D3b. The booklet reading of the unbound symbol ``name`` when exactly one table constant with
    that symbol has the dimension ``required`` (the dimension the stated relation forces on the
    symbol). None when the dimension is unknown, no constant fits, or two would (the letter is
    ambiguous between them): the relation is then undecided (ST-UNDEC-002), never guessed."""
    if required is None:
        return None
    fits = [c for c in constants_for_symbol(name, profile_key) if c.dim.same_physical(required) and c.dim.angle == required.angle]
    if len(fits) != 1:
        return None
    c = fits[0]
    lo, hi = c.hull
    return BookletReading(name, c, lo, hi)


@dataclass(frozen=True)
class ConstantMatch:
    """D3a: a written literal that matches a table constant at its written precision."""

    constant: Constant
    written_si: Fraction
    half_width_si: Fraction

    def interval(self) -> tuple[Fraction, Fraction]:
        """The hull of the rounding interval ``[w − h, w + h]`` and the constant's accepted values that
        lie near it (within the rounding interval, or listed as accepted written forms)."""
        lo, hi = self.written_si - self.half_width_si, self.written_si + self.half_width_si
        for v in self.constant.values:
            if lo <= v <= hi or self.written_si in self.constant.written:
                lo, hi = min(lo, v), max(hi, v)
        return lo, hi

    @property
    def note(self) -> str:
        return (f"data-booklet constant: the written {_show(self.written_si)} reads as {self.constant.name}; it ranges over its rounding "
                f"interval and the booklet value {_show(self.constant.value)}")


def match_written(value_si: Fraction, half_width_si: Fraction, sig_figs: int, dim: Optional[Dimension], *, unit_given: bool, profile_key: str = "") -> Optional[ConstantMatch]:
    """D3a. The table constant a written literal stands for, or None.

    A literal matches a constant when it has at least two significant figures (a bare ``3`` or
    ``10`` is no constant), its rounding interval ``[w − h, w + h]`` (SI) contains one of the
    constant's accepted values, and, when the literal carries a unit, the unit's dimension is the
    constant's. A literal listed in ``written`` (``10`` for g) matches only with a unit of the
    right dimension. The constant's profiles are respected. Matching only ever widens."""
    if value_si == 0:
        return None
    for c in CONSTANTS:
        if profile_key and c.profiles is not None and profile_key not in c.profiles:
            continue
        if unit_given:
            if dim is None or not (c.dim.same_physical(dim) and c.dim.angle == dim.angle):
                continue
        elif c.dim.is_dimensionless:
            continue  # a bare number that happens to equal a dimensionless constant (K_w) is no evidence of the constant
        if value_si in c.written and unit_given:
            return ConstantMatch(c, value_si, half_width_si)
        if sig_figs < 2:
            continue
        lo, hi = value_si - half_width_si, value_si + half_width_si
        if any(lo <= v <= hi for v in c.values):
            return ConstantMatch(c, value_si, half_width_si)
    return None


def _show(v: Fraction) -> str:
    """A short display of an exact value (used in notes; never parsed back)."""
    if v == 0:
        return "0"
    sign = "-" if v < 0 else ""
    a = abs(v)
    k = 0
    ten = Fraction(10)
    while a >= 10 and k < 400:
        a /= ten
        k += 1
    while a < 1 and k > -400:
        a *= ten
        k -= 1
    digits = int(a * 10 ** 9)
    s = str(digits)
    mant = (s[0] + "." + s[1:]).rstrip("0").rstrip(".")
    return f"{sign}{mant}" + (f" × 10^{k}" if k else "")
