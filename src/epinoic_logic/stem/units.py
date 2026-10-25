"""Units: table, prefixes, dimension vectors, unit-expression parser, ambiguity readings.

Section 6 of docs/STEM_DESIGN.md.

* **Dimensions** are 7-tuples of integers over (m, kg, s, A, K, mol, cd) plus an angle
  exponent. Bare numbers carry no dimension at all ("unitless as written"), which is not
  the same as dimensionless: :class:`Dimension` is only ever built from units.
* **The table** holds the SI base and derived units, the accepted units (min, h, d, L, l,
  t, eV, u, Da, Å, AU, ly, pc, bar, atm, mmHg, °, ′, ″, %, ppm), the affine temperatures
  (°C, °F) and spelled-out names (metre, seconds, newtons, "metres per second squared",
  "per cent", ...). Every SI factor is an exact ``Fraction``; where no exact rational
  factor exists (the degree, which is π/180 rad, and the parsec) the factor is ``None``
  and the unit still has a dimension.
* **Prefixes** Q R Y Z E P T G M k h da d c m µ μ u n p f a z y r q, applied by longest
  match and only to units that take a prefix. SI binding applies: ``ms`` is a millisecond,
  ``m s`` is metre second, ``Nm`` and ``N m`` are newton metre (``N`` is no prefix).
* **Unit expressions**: atoms separated by a space, ``·``, ``⋅``, ``*``, LaTeX spacing
  (``\\,``, ``\\;``, ``\\ ``), ``\\cdot``, or ``/`` (what follows a slash is inverted:
  ``m/s/s``, ``kg·m/s²``, ``J/(mol K)``); exponents ``⁻²``, ``^-2``, ``^{-2}``, ``**-2``;
  ``\\text{}``, ``\\mathrm{}`` and ``\\operatorname{}`` wrappers are read through
  (``\\text{m s}^{-1}``, ``\\mathrm{mol\\,dm^{-3}}``).
* **Readings** (section 6.3): one reading per profile, two where an ambiguity matters:
  a bare ``M`` after a number is molar in chemistry and biology, molar or mega in physics
  (two readings, ST-UNIT-002 info); a glued two-unit token with a negative exponent
  (``ms⁻¹``) is read both by SI binding (per millisecond) and as the writer's evident
  metre per second; ``t`` is the tonne in ESS and Design Technology only.
* **Affine units**: the offset (273.15 for °C, 459.67 for °F) is carried on the reading
  of an expression that is exactly one affine atom to the first power; it is applied only
  by explicit °C/K conversion checks, never to a Δ-prefixed symbol or a change (the checks
  stage decides that). Inside a compound expression (``J kg⁻¹ °C⁻¹``) °C is a temperature
  interval, like K.

Nothing here evaluates text: unit strings are matched against the table character by
character, and factors are table constants.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from typing import Optional

from .numbers import SUPERSCRIPT_DIGITS, SUPERSCRIPT_SIGNS, is_ascii_digit, superscript_int

__all__ = [
    "BASE_NAMES", "DIMENSIONLESS", "Dimension", "ENGLISH_NOT_UNITS", "GLUED_UNITS", "GREEK_PREFIXABLE", "PREFIXES", "UNITS", "UnitAtom", "UnitDef", "UnitExpr", "UnitReading",
    "compound_part", "dimension_name", "english_word_atom", "is_unit_atom", "lookup_atom", "parse_unit", "prefixed_greek_unit", "unit_dimension",
    "unit_group",
]

BASE_NAMES = ("m", "kg", "s", "A", "K", "mol", "cd")


@dataclass(frozen=True)
class Dimension:
    """Exponents over (m, kg, s, A, K, mol, cd) and an angle exponent."""

    exps: tuple[int, int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0, 0)
    angle: int = 0

    def __mul__(self, other: "Dimension") -> "Dimension":
        return Dimension(tuple(a + b for a, b in zip(self.exps, other.exps)), self.angle + other.angle)  # type: ignore[arg-type]

    def __truediv__(self, other: "Dimension") -> "Dimension":
        return Dimension(tuple(a - b for a, b in zip(self.exps, other.exps)), self.angle - other.angle)  # type: ignore[arg-type]

    def power(self, n: int) -> "Dimension":
        return Dimension(tuple(a * n for a in self.exps), self.angle * n)  # type: ignore[arg-type]

    @property
    def is_dimensionless(self) -> bool:
        return not any(self.exps)

    def same_physical(self, other: "Dimension") -> bool:
        """Equal over the seven base dimensions (the angle is a supplementary dimension: rad·s⁻¹ and s⁻¹ agree)."""
        return self.exps == other.exps

    def __str__(self) -> str:
        parts = [f"{n}^{e}" if e != 1 else n for n, e in zip(BASE_NAMES, self.exps) if e]
        if self.angle:
            parts.append(f"angle^{self.angle}" if self.angle != 1 else "angle")
        return " ".join(parts) or "dimensionless"


def _d(m: int = 0, kg: int = 0, s: int = 0, a: int = 0, k: int = 0, mol: int = 0, cd: int = 0, angle: int = 0) -> Dimension:
    return Dimension((m, kg, s, a, k, mol, cd), angle)


DIMENSIONLESS = _d()


@dataclass(frozen=True)
class UnitDef:
    """One unit of the table. ``factor`` is the exact SI factor of the unprefixed unit (None when
    no exact rational factor exists); ``offset`` is the affine offset in the unit's own scale
    (SI value = factor·(x + offset)); ``profiles`` restricts the unit to some STEM profiles."""

    symbol: str
    name: str
    dim: Dimension
    factor: Optional[Fraction]
    prefixable: bool = True
    offset: Fraction = Fraction(0)
    affine: bool = False
    profiles: Optional[frozenset[str]] = None
    angle_degrees: Optional[Fraction] = None  # for angle units: the size in degrees


#: SI prefixes with their exact factors; 'u' is the ASCII micro sign
PREFIXES: dict[str, Fraction] = {
    "Q": Fraction(10) ** 30, "R": Fraction(10) ** 27, "Y": Fraction(10) ** 24, "Z": Fraction(10) ** 21, "E": Fraction(10) ** 18,
    "P": Fraction(10) ** 15, "T": Fraction(10) ** 12, "G": Fraction(10) ** 9, "M": Fraction(10) ** 6, "k": Fraction(10) ** 3,
    "h": Fraction(10) ** 2, "da": Fraction(10), "d": Fraction(1, 10), "c": Fraction(1, 100), "m": Fraction(1, 1000),
    "µ": Fraction(1, 10 ** 6), "μ": Fraction(1, 10 ** 6), "u": Fraction(1, 10 ** 6), "n": Fraction(1, 10 ** 9), "p": Fraction(1, 10 ** 12),
    "f": Fraction(1, 10 ** 15), "a": Fraction(1, 10 ** 18), "z": Fraction(1, 10 ** 21), "y": Fraction(1, 10 ** 24),
    "r": Fraction(1, 10 ** 27), "q": Fraction(1, 10 ** 30),
}
_PREFIX_ORDER = sorted(PREFIXES, key=len, reverse=True)
_PREFIX_WORDS = {"kilo": Fraction(10) ** 3, "mega": Fraction(10) ** 6, "giga": Fraction(10) ** 9, "tera": Fraction(10) ** 12,
                 "milli": Fraction(1, 1000), "micro": Fraction(1, 10 ** 6), "nano": Fraction(1, 10 ** 9), "pico": Fraction(1, 10 ** 12),
                 "centi": Fraction(1, 100), "deci": Fraction(1, 10)}

_LENGTH, _MASS, _TIME, _CURRENT, _TEMP, _AMOUNT, _LUM = _d(m=1), _d(kg=1), _d(s=1), _d(a=1), _d(k=1), _d(mol=1), _d(cd=1)
_ANGLE = _d(angle=1)


def _units() -> dict[str, UnitDef]:
    u: dict[str, UnitDef] = {}

    def add(sym: str, name: str, dim: Dimension, factor: Optional[Fraction], **kw: object) -> None:
        u[sym] = UnitDef(sym, name, dim, factor, **kw)  # type: ignore[arg-type]

    add("m", "metre", _LENGTH, Fraction(1))
    add("g", "gram", _MASS, Fraction(1, 1000))
    add("s", "second", _TIME, Fraction(1))
    add("A", "ampere", _CURRENT, Fraction(1))
    add("K", "kelvin", _TEMP, Fraction(1))
    add("mol", "mole", _AMOUNT, Fraction(1))
    add("cd", "candela", _LUM, Fraction(1))
    add("N", "newton", _d(m=1, kg=1, s=-2), Fraction(1))
    add("J", "joule", _d(m=2, kg=1, s=-2), Fraction(1))
    add("W", "watt", _d(m=2, kg=1, s=-3), Fraction(1))
    add("Pa", "pascal", _d(m=-1, kg=1, s=-2), Fraction(1))
    add("Hz", "hertz", _d(s=-1), Fraction(1))
    add("C", "coulomb", _d(s=1, a=1), Fraction(1))
    add("V", "volt", _d(m=2, kg=1, s=-3, a=-1), Fraction(1))
    add("Ω", "ohm", _d(m=2, kg=1, s=-3, a=-2), Fraction(1))
    add("F", "farad", _d(m=-2, kg=-1, s=4, a=2), Fraction(1))
    add("H", "henry", _d(m=2, kg=1, s=-2, a=-2), Fraction(1))
    add("T", "tesla", _d(kg=1, s=-2, a=-1), Fraction(1))
    add("Wb", "weber", _d(m=2, kg=1, s=-2, a=-1), Fraction(1))
    add("S", "siemens", _d(m=-2, kg=-1, s=3, a=2), Fraction(1))
    add("Bq", "becquerel", _d(s=-1), Fraction(1))
    add("Gy", "gray", _d(m=2, s=-2), Fraction(1))
    add("Sv", "sievert", _d(m=2, s=-2), Fraction(1))
    add("lm", "lumen", _LUM, Fraction(1))
    add("lx", "lux", _d(m=-2, cd=1), Fraction(1))
    add("rad", "radian", _ANGLE, Fraction(1))
    add("sr", "steradian", _d(angle=2), Fraction(1))
    add("min", "minute", _TIME, Fraction(60), prefixable=False)
    add("h", "hour", _TIME, Fraction(3600), prefixable=False)
    add("d", "day", _TIME, Fraction(86400), prefixable=False)
    add("L", "litre", _d(m=3), Fraction(1, 1000))
    add("l", "litre", _d(m=3), Fraction(1, 1000))
    add("t", "tonne", _MASS, Fraction(1000), profiles=frozenset({"ess", "design_technology"}))
    add("eV", "electronvolt", _d(m=2, kg=1, s=-2), Fraction(1602176634, 10 ** 28))  # exact since the 2019 SI
    add("u", "atomic mass unit", _MASS, Fraction(166053906660, 10 ** 38), prefixable=False)  # CODATA 2018 value
    add("Da", "dalton", _MASS, Fraction(166053906660, 10 ** 38))
    add("Å", "ångström", _LENGTH, Fraction(1, 10 ** 10), prefixable=False)
    add("AU", "astronomical unit", _LENGTH, Fraction(149597870700), prefixable=False)
    add("ly", "light year", _LENGTH, Fraction(9460730472580800), prefixable=False)
    add("pc", "parsec", _LENGTH, None, prefixable=True)
    add("bar", "bar", _d(m=-1, kg=1, s=-2), Fraction(10 ** 5))
    add("atm", "atmosphere", _d(m=-1, kg=1, s=-2), Fraction(101325), prefixable=False)
    add("mmHg", "millimetre of mercury", _d(m=-1, kg=1, s=-2), Fraction(133322387415, 10 ** 9), prefixable=False)
    add("°", "degree", _ANGLE, None, prefixable=False, angle_degrees=Fraction(1))
    add("′", "arc minute", _ANGLE, None, prefixable=False, angle_degrees=Fraction(1, 60))
    add("″", "arc second", _ANGLE, None, prefixable=False, angle_degrees=Fraction(1, 3600))
    add("%", "per cent", DIMENSIONLESS, Fraction(1, 100), prefixable=False)
    add("ppm", "part per million", DIMENSIONLESS, Fraction(1, 10 ** 6), prefixable=False)
    add("count", "count (a number of events or items)", DIMENSIONLESS, Fraction(1), prefixable=False)  # 'counts min⁻¹', 'counts per minute'
    # stem-soundness-12 (round 7): amounts of data, a count of bits ('32 bits = 4 bytes'); the binary multiples only, whose factor is exact
    # (a kilobyte is 1000 or 1024 bytes by convention, so it stays unread)
    add("bit", "bit", DIMENSIONLESS, Fraction(1), prefixable=False)
    add("byte", "byte (8 bits)", DIMENSIONLESS, Fraction(8), prefixable=False)
    add("KiB", "kibibyte (1024 bytes)", DIMENSIONLESS, Fraction(8 * 1024), prefixable=False)
    add("MiB", "mebibyte (1024² bytes)", DIMENSIONLESS, Fraction(8 * 1024 ** 2), prefixable=False)
    add("GiB", "gibibyte (1024³ bytes)", DIMENSIONLESS, Fraction(8 * 1024 ** 3), prefixable=False)

    add("°C", "degree Celsius", _TEMP, Fraction(1), prefixable=False, offset=Fraction(27315, 100), affine=True)
    add("°F", "degree Fahrenheit", _TEMP, Fraction(5, 9), prefixable=False, offset=Fraction(45967, 100), affine=True)
    add("M", "molar", _d(m=-3, mol=1), Fraction(1000), prefixable=False)  # mol dm⁻³; read only per profile (see parse_unit)
    return u


#: unit symbol -> definition. ``M`` (molar) is in the table but read only through the profile's bare-M rule.
UNITS: dict[str, UnitDef] = _units()
_OHM_ALIASES = {"ohm": "Ω", "ohms": "Ω", "Ω": "Ω", "Ω": "Ω"}

#: spelled-out unit words -> (symbol, power); plurals and both spellings
_WORDS: dict[str, str] = {}
for _sym, _names in (
    ("m", ("metre", "meter")), ("g", ("gram", "gramme")), ("s", ("second", "sec")), ("A", ("ampere", "amp")), ("K", ("kelvin",)),
    ("mol", ("mole",)), ("N", ("newton",)), ("J", ("joule",)), ("W", ("watt",)), ("Pa", ("pascal",)), ("Hz", ("hertz",)),
    ("C", ("coulomb",)), ("V", ("volt",)), ("Ω", ("ohm",)), ("F", ("farad",)), ("T", ("tesla",)), ("L", ("litre", "liter")),
    ("min", ("minute",)), ("h", ("hour",)), ("d", ("day",)), ("rad", ("radian",)), ("Bq", ("becquerel",)), ("eV", ("electronvolt",)),
):
    for _n in _names:
        _WORDS[_n] = _sym
        _WORDS[_n + "s"] = _sym
_WORDS["hertz"] = "Hz"
_WORDS["kelvins"] = "K"
_WORDS["percent"] = "%"
_WORDS["bits"] = "bit"
_WORDS["bytes"] = "byte"
_WORDS["counts"] = "count"  # a count rate: '1600 counts min⁻¹' (STEM repair 1: an unread word ended the maths span)
_WORDS["degrees"] = "°"
_WORDS["degree"] = "°"


def dimension_name(dim: Dimension) -> str:
    """A plain name for common dimensions (used in descriptions)."""
    names = {
        _LENGTH: "length", _MASS: "mass", _TIME: "time", _CURRENT: "current", _TEMP: "temperature", _AMOUNT: "amount of substance",
        _d(m=1, s=-1): "speed", _d(m=1, s=-2): "acceleration", _d(m=1, kg=1, s=-2): "force", _d(m=2, kg=1, s=-2): "energy",
        _d(m=2, kg=1, s=-3): "power", _d(m=-1, kg=1, s=-2): "pressure", _d(s=-1): "frequency", _d(s=1, a=1): "charge",
        _d(m=2, kg=1, s=-3, a=-1): "potential difference", _d(m=2, kg=1, s=-3, a=-2): "resistance", _d(m=3): "volume",
        _d(m=-3, mol=1): "concentration", _d(m=1, kg=1, s=-1): "momentum", DIMENSIONLESS: "dimensionless",
    }
    return names.get(Dimension(dim.exps, 0), str(dim))


@dataclass(frozen=True)
class UnitAtom:
    """One atom of a unit expression as written, resolved against the table (``unit`` is None
    for an unknown atom)."""

    text: str
    unit: Optional[UnitDef]
    prefix: str = ""
    power: int = 1

    @property
    def known(self) -> bool:
        return self.unit is not None

    @property
    def factor(self) -> Optional[Fraction]:
        if self.unit is None or self.unit.factor is None:
            return None
        base = self.unit.factor * (PREFIXES.get(self.prefix, Fraction(1)) if self.prefix not in _PREFIX_WORDS else _PREFIX_WORDS[self.prefix])
        return base ** self.power

    @property
    def dim(self) -> Optional[Dimension]:
        return None if self.unit is None else self.unit.dim.power(self.power)


@dataclass(frozen=True)
class UnitReading:
    """One reading of a unit expression: its atoms, dimension and exact SI factor. ``dim`` and
    ``factor`` are None when an atom is unknown; ``factor`` is also None when an atom has no
    exact rational factor (the degree). ``affine`` is ``(factor, offset)`` for an expression that
    is exactly °C or °F; ``note`` names the reading (``"per millisecond"``)."""

    atoms: tuple[UnitAtom, ...]
    dim: Optional[Dimension]
    factor: Optional[Fraction]
    affine: Optional[tuple[Fraction, Fraction]] = None
    note: str = ""

    @property
    def is_angle(self) -> bool:
        return self.dim is not None and self.dim.angle != 0 and not any(self.dim.exps)


@dataclass(frozen=True)
class UnitExpr:
    """A parsed unit expression: one or two readings, the unknown atoms (ST-UNIT-001) and the
    ambiguity that produced a second reading (ST-UNIT-002 when it is the bare M)."""

    text: str
    readings: tuple[UnitReading, ...]
    unknown: tuple[str, ...] = ()
    ambiguity: str = ""
    ambiguity_code: str = ""

    @property
    def known(self) -> bool:
        return not self.unknown and bool(self.readings)

    @property
    def dim(self) -> Optional[Dimension]:
        """The dimension when every reading agrees on it, else None."""
        dims = {r.dim for r in self.readings}
        if len(dims) == 1:
            return next(iter(dims))
        return None


#: English words that a rare prefix reads as a unit atom ('as' an attosecond, 'am' an attometre, 'at' an attotonne in ESS):
#: the table keeps the atoms, but a word written apart after a number ('x = 5 as before', '10 am', '5 at D') is never read as a
#: unit there (STEM repair 1, the unit reading's class of the prefixed-ohm repair: :func:`english_word_atom`)
ENGLISH_NOT_UNITS = frozenset({"as", "am", "at"})


def english_word_atom(word: str) -> bool:
    """A letter run that is an English word the table would read as a rarely prefixed unit (:data:`ENGLISH_NOT_UNITS`)."""
    return word in ENGLISH_NOT_UNITS


def _resolve(word: str, profile_key: str = "", bare_m: tuple[str, ...] = ("mega",), tonne: bool = False) -> list[tuple[UnitDef, str]]:
    """Every (unit, prefix) reading of a letter run, best first: an exact symbol, then prefix +
    symbol (longest prefix first). The bare ``M`` and the tonne follow the profile."""
    out: list[tuple[UnitDef, str]] = []
    if word in _OHM_ALIASES:
        return [(UNITS["Ω"], "")]
    if word == "M":
        for r in bare_m:
            if r == "molar":
                out.append((UNITS["M"], ""))
            elif r == "mega":
                out.append((UnitDef("M", "mega (a factor of 10⁶)", DIMENSIONLESS, Fraction(10) ** 6, prefixable=False), ""))
        return out
    if word == "t" and not tonne:
        return []
    u = UNITS.get(word)
    if u is not None and word != "M":
        out.append((u, ""))
    if not out:
        for p in _PREFIX_ORDER:
            if word.startswith(p) and len(word) > len(p):
                rest = word[len(p):]
                v = UNITS.get(rest) if rest not in ("M",) else None
                if rest in _OHM_ALIASES:
                    v = UNITS["Ω"]
                if v is not None and v.prefixable and (rest != "t" or tonne):
                    out.append((v, p))
                    break
    if not out:
        low = word.lower()
        if low in _WORDS:
            out.append((UNITS[_WORDS[low]], ""))
        else:
            for pw, _f in _PREFIX_WORDS.items():
                if low.startswith(pw) and low[len(pw):] in _WORDS:
                    v = UNITS[_WORDS[low[len(pw):]]]
                    if v.prefixable:
                        out.append((v, pw))
                        break
    return out


#: glued runs read as two or three unit atoms. Only these: a free split would read English words as units ('has' as hour
#: attosecond), so a glued run outside this list is no unit unless it is one atom.
GLUED_UNITS = frozenset({"Nm", "kWh", "Wh", "MWh", "Ns", "Ah", "mAh", "VA", "kVA", "ms"})


def _glued(word: str, tonne: bool) -> Optional[list[tuple[UnitDef, str, str]]]:
    """Split a glued run of :data:`GLUED_UNITS` into its atoms (``Nm`` -> N, m; ``kWh`` -> kW, h;
    ``ms`` -> m, s). Returns the atoms or None."""
    n = len(word)
    if n < 2 or n > 8 or word not in GLUED_UNITS:
        return None
    return _glued_split(word, tonne)


def _glued_split(word: str, tonne: bool) -> Optional[list[tuple[UnitDef, str, str]]]:
    n = len(word)
    best: Optional[list[tuple[UnitDef, str, str]]] = None
    for i in range(1, n):
        a, b = word[:i], word[i:]
        ra = _resolve(a, tonne=tonne) if a != "M" else []
        if not ra:
            continue
        rb = _resolve(b, tonne=tonne) if b != "M" else []
        if rb:
            cand = [(ra[0][0], ra[0][1], a), (rb[0][0], rb[0][1], b)]
        else:
            sub = _glued_split(b, tonne) if len(b) >= 2 else None
            if not sub or len(sub) > 2:
                continue
            cand = [(ra[0][0], ra[0][1], a)] + sub
        if best is None or len(cand) < len(best):
            best = cand
    return best


def lookup_atom(word: str, profile_key: str = "", *, bare_m: tuple[str, ...] = ("mega",), tonne: bool = False) -> list[UnitAtom]:
    """Readings of one letter run as a single unit atom (power 1): empty when the run is no unit."""
    return [UnitAtom(word, u, p) for u, p in _resolve(word, profile_key, bare_m, tonne)]


#: unit symbols of the table that are not Latin letters and take an SI prefix (the ohm). The lexer reads a Greek letter as
#: a token of its own, so a Latin prefix written right before one ('kΩ', 'MΩ', 'mΩ', 'GΩ') is two tokens that the parser
#: and the span scanner join into one unit atom (:func:`prefixed_greek_unit`); the micro sign before a Latin unit ('μF')
#: is the other way round and is joined the same way.
GREEK_PREFIXABLE = frozenset(sym for sym, u in UNITS.items() if u.prefixable and not sym.isascii())


def prefixed_greek_unit(prefix: str, symbol: str) -> bool:
    """Whether a Latin SI prefix written right before a non-Latin unit symbol is one prefixed unit atom: ``k`` + ``Ω`` is
    the kilo-ohm, ``M`` + ``Ω`` the megaohm (never the molar ``M``: a prefix is read only on a unit that takes one), ``m``
    + ``Ω`` the milliohm. Table lookups only; nothing is evaluated."""
    return symbol in GREEK_PREFIXABLE and prefix.isascii() and prefix in PREFIXES and bool(_resolve(prefix + symbol))


def is_unit_atom(word: str, *, bare_m: tuple[str, ...] = ("mega",), tonne: bool = False, glued: bool = True) -> bool:
    """True when ``word`` reads as a unit atom (exact, prefixed, spelled out) or, with ``glued``,
    as two or three glued atoms (``Nm``)."""
    if not word:
        return False
    if _resolve(word, "", bare_m, tonne):
        return True
    return glued and _glued(word, tonne) is not None


# --------------------------------------------------------------------------- unit-expression parser

_WRAPPERS = ("\\text{", "\\mathrm{", "\\operatorname{", "\\rm{", "\\textrm{", "\\mbox{")
_SPACERS = ("\\,", "\\;", "\\:", "\\!", "\\ ", "\\quad", "\\cdot", "~")
_GREEK_UNIT = {"\\Omega": "Ω", "\\mu": "µ", "\\%": "%", "\\circ": "°", "\\degree": "°", "\\AA": "Å"}
_MAX_UNIT_CHARS = 160
#: glued runs whose SI-binding reading (a prefixed unit) and two-atom reading are both plausible when a negative exponent
#: follows: 'ms⁻¹' is per millisecond by SI binding but metre per second as evidently meant. 'dm⁻³', 'cm⁻³' and 'mm⁻¹' are not
#: ambiguous: nobody writes day metre or centi... as two atoms.
_GLUED_AMBIGUOUS = frozenset({"ms"})
_MAX_ATOMS = 12


#: the most digits a unit exponent may have (parser-safety-1: a longer superscript run is unreadable, never converted)
_MAX_EXPONENT_DIGITS = 6


@dataclass
class _Lex:
    items: list = field(default_factory=list)  # ('atom', text) | ('sep', ' ') | ('div',) | ('pow', int) | ('open',) | ('close',)
    error: str = ""


def _lex_unit(text: str, ascii_exponents: bool = False) -> _Lex:
    """The items of a unit expression. With ``ascii_exponents`` an exponent written in ASCII with no caret, glued to its
    atom, is read as the atom's power: a hyphen-minus (or plus) and one digit (``s-1``, ``dm-3``, ``mol-1``), or one digit
    2 to 9 right after an atom (``cm3``, ``dm3``, ``m2``). The parser asks for it only where it has seen such an exponent end a
    unit after a number (``parser._ascii_unit_exponent``); every other caller reads a digit inside a unit as malformed."""
    out = _Lex()
    s = text
    n = len(s)
    i = 0
    depth_wrappers: list[int] = []  # brace depth markers for \text{...}
    brace = 0
    while i < n:
        ch = s[i]
        if ch in " \t   ":
            out.items.append(("sep",))
            i += 1
            continue
        matched = False
        for w in _WRAPPERS:
            if s.startswith(w, i):
                brace += 1
                depth_wrappers.append(brace)
                out.items.append(("sep",))
                i += len(w)
                matched = True
                break
        if matched:
            continue
        for sp in _SPACERS:
            if s.startswith(sp, i):
                out.items.append(("sep",))
                i += len(sp)
                matched = True
                break
        if matched:
            continue
        for g, rep in _GREEK_UNIT.items():
            if s.startswith(g, i) and not (i + len(g) < n and s[i + len(g)].isalpha()):
                if rep == "°" and out.items and out.items[-1][0] == "pow_open":
                    out.items.pop()
                out.items.append(("atom", rep))
                i += len(g)
                matched = True
                break
        if matched:
            continue
        if ch == "{":
            brace += 1
            out.items.append(("open",))
            i += 1
            continue
        if ch == "}":
            if depth_wrappers and depth_wrappers[-1] == brace:
                depth_wrappers.pop()
                out.items.append(("sep",))
            else:
                out.items.append(("close",))
            brace -= 1
            i += 1
            continue
        if ch in "·⋅*.":
            if ch == "*" and s.startswith("**", i):
                j = i + 2
                j, val = _ascii_exponent(s, j, n)
                if val is None:
                    out.error = "unreadable exponent"
                    return out
                out.items.append(("pow", val))
                i = j
                continue
            out.items.append(("sep",))
            i += 1
            continue
        if ch == "/":
            out.items.append(("div",))
            i += 1
            continue
        if ch == "(":
            out.items.append(("open",))
            i += 1
            continue
        if ch == ")":
            out.items.append(("close",))
            i += 1
            continue
        if ch == "^":
            j = i + 1
            if s.startswith("\\circ", j) or s.startswith("{\\circ}", j):
                out.items.append(("atom", "°"))
                i = j + (5 if s.startswith("\\circ", j) else 7)
                continue
            j, val = _ascii_exponent(s, j, n)
            if val is None:
                out.error = "unreadable exponent"
                return out
            out.items.append(("pow", val))
            i = j
            continue
        if ch in SUPERSCRIPT_DIGITS or ch in SUPERSCRIPT_SIGNS:
            j, digits = superscript_int(s, i, n)
            if digits is None:
                out.error = "a superscript sign with no digits"
                return out
            if len(digits) - digits.startswith("-") > _MAX_EXPONENT_DIGITS:
                out.error = "an exponent of too many digits"  # parser-safety-1: bounded before int()
                return out
            out.items.append(("pow", int(digits)))
            i = j
            continue
        if ch == "°":
            if i + 1 < n and s[i + 1] in "CF":
                out.items.append(("atom", "°" + s[i + 1]))
                i += 2
            else:
                out.items.append(("atom", "°"))
                i += 1
            continue
        if ch in "%′″'\"":
            out.items.append(("atom", {"'": "′", '"': "″"}.get(ch, ch)))
            i += 1
            continue
        if ch.isalpha() or ch in "µμΩΩÅ":
            j = i
            while j < n and (s[j].isalpha() or s[j] in "µμΩΩÅ") and s[j] not in "°":
                j += 1
            word = s[i:j]
            out.items.append(("atom", word))
            i = j
            continue
        if ascii_exponents and out.items and out.items[-1][0] == "atom" and i > 0 and (s[i - 1].isalpha() or s[i - 1] in "µμΩΩÅ"):
            # an ASCII exponent glued to its atom: 's-1', 'dm-3' (a sign and one digit), 'cm3' (one digit, 2 to 9)
            j = i + 1 if ch in "-+" else i
            if j < n and is_ascii_digit(s[j]) and not (j + 1 < n and (is_ascii_digit(s[j + 1]) or s[j + 1] == ".")) and s[j] != "0" \
                    and (ch in "-+" or s[j] != "1"):
                out.items.append(("pow", -int(s[j]) if ch == "-" else int(s[j])))
                i = j + 1
                continue
        if is_ascii_digit(ch):
            out.error = f"a digit inside the unit ({ch!r})"
            return out
        out.error = f"unexpected character {ch!r} in the unit"
        return out
    return out


def _ascii_exponent(s: str, j: int, n: int) -> tuple[int, Optional[int]]:
    close = ""
    if j < n and s[j] in "{(":
        close = "}" if s[j] == "{" else ")"
        j += 1
    sign = 1
    if j < n and s[j] in "-−":
        sign = -1
        j += 1
    elif j < n and s[j] == "+":
        j += 1
    k = j
    while k < n and is_ascii_digit(s[k]) and k - j < 3:
        k += 1
    if k == j or (k < n and is_ascii_digit(s[k])):
        return j, None
    val = sign * int(s[j:k])
    if close:
        if k >= n or s[k] != close:
            return j, None
        k += 1
    return k, val


def parse_unit(text: str, *, bare_m: tuple[str, ...] = ("mega",), tonne: bool = False, profile_key: str = "",
               ascii_exponents: bool = False) -> Optional[UnitExpr]:
    """Parse a unit expression as written (``"m s⁻²"``, ``"kg·m/s²"``, ``"J mol⁻¹ K⁻¹"``,
    ``"\\text{m s}^{-1}"``, ``"ms⁻¹"``, ``"kJ m⁻² yr⁻¹"``). Returns None when the text is not
    a unit expression at all (empty, malformed, a digit inside, too long, no known atom).
    Unknown atoms are kept and listed in ``unknown`` (ST-UNIT-001). With ``ascii_exponents`` an
    exponent glued to its atom with no caret is read too (``"m s-1"``, ``"mol dm-3"``, ``"cm3"``,
    ``"g/cm3"``; :func:`_lex_unit`)."""
    return _parse_unit_cached(text, bare_m, tonne, ascii_exponents)


@lru_cache(maxsize=1024)
def _parse_unit_cached(text: str, bare_m: tuple[str, ...], tonne: bool, ascii_exponents: bool = False) -> Optional[UnitExpr]:
    if not text or len(text) > _MAX_UNIT_CHARS:
        return None
    lx = _lex_unit(text, ascii_exponents)
    if lx.error:
        return None
    # atoms with their signed powers: after '/', the next atom or parenthesised group is inverted
    atoms: list[tuple[str, int]] = []
    pending_div = False
    group_signs: list[int] = []
    for item in lx.items:
        kind = item[0]
        if kind == "atom":
            sign = -1 if pending_div else 1
            for g in group_signs:
                sign *= g
            atoms.append((item[1], sign))
            pending_div = False
        elif kind == "pow":
            if not atoms or atoms[-1][0].lower() in ("per", "squared", "cubed"):
                return None
            name, p = atoms[-1]
            atoms[-1] = (name, p * item[1])
        elif kind == "div":
            if pending_div or not atoms:
                return None
            pending_div = True
        elif kind == "open":
            group_signs.append(-1 if pending_div else 1)
            pending_div = False
        elif kind == "close":
            if not group_signs:
                return None
            group_signs.pop()
        if len(atoms) > _MAX_ATOMS:
            return None
    if group_signs or pending_div or not atoms:
        return None
    # resolve each atom into its alternatives (a list of atom sequences); 'per', 'squared', 'cubed' are words
    choices: list[list[list[UnitAtom]]] = []
    unknown: list[str] = []
    notes: list[str] = []
    code = ""
    per = False
    for word, power in atoms:
        low = word.lower()
        if low == "per":
            if per:
                return None
            per = True
            continue
        if low in ("squared", "cubed"):
            if not choices:
                return None
            mult = 2 if low == "squared" else 3
            choices[-1] = [seq[:-1] + [UnitAtom(seq[-1].text, seq[-1].unit, seq[-1].prefix, seq[-1].power * mult)] for seq in choices[-1]]
            continue
        if per:
            power = -power
            per = False
        direct = [UnitAtom(word, u, p, power) for u, p in _resolve(word, "", bare_m, tonne)]
        glued = _glued(word, tonne) if word != "M" else None
        if direct and glued and power < 0 and word in _GLUED_AMBIGUOUS and len(glued) == 2 and direct[0].prefix and len(direct) == 1:
            # 'ms⁻¹': by SI binding a millisecond to the power -1; as evidently meant, metre second⁻¹
            alt = [UnitAtom(glued[0][2], glued[0][0], glued[0][1], 1), UnitAtom(glued[1][2], glued[1][0], glued[1][1], power)]
            choices.append([[direct[0]], alt])
            notes.append(f"'{word}' with exponent {power} reads as ({direct[0].prefix}{direct[0].unit.symbol})^{power} by SI binding "
                         f"or as {glued[0][2]} {glued[1][2]}^{power}")
            code = code or "ST-UNIT-002"
        elif direct:
            choices.append([[a] for a in direct])
            if len(direct) > 1:
                notes.append(f"'{word}' after a number reads as " + " or ".join(a.unit.name for a in direct if a.unit))
                code = "ST-UNIT-002"
        elif glued:
            choices.append([[UnitAtom(t, u, p, power if idx == len(glued) - 1 else 1) for idx, (u, p, t) in enumerate(glued)]])
        else:
            choices.append([[UnitAtom(word, None, "", power)]])
            unknown.append(word)
    if per or not choices or all(seq[0].unit is None for alts in choices for seq in alts):
        return None
    combos: list[list[UnitAtom]] = [[]]
    labels: list[str] = [""]
    for alts in choices:
        nxt: list[list[UnitAtom]] = []
        nlab: list[str] = []
        for combo, lab in zip(combos, labels):
            for k, seq in enumerate(alts):
                nxt.append(combo + seq)
                nlab.append(lab if len(alts) == 1 else (lab + ("; " if lab else "") + ("first reading" if k == 0 else "second reading")))
        combos, labels = nxt[:4], nlab[:4]
    readings = tuple(_reading(c, lab) for c, lab in zip(combos, labels))
    return UnitExpr(text=text, readings=readings, unknown=tuple(unknown), ambiguity="; ".join(notes), ambiguity_code=code if len(readings) > 1 else "")


def _reading(atoms: list[UnitAtom], note: str) -> UnitReading:
    dim: Optional[Dimension] = DIMENSIONLESS
    factor: Optional[Fraction] = Fraction(1)
    for a in atoms:
        if a.unit is None:
            dim, factor = None, None
            break
        dim = dim * a.dim if dim is not None and a.dim is not None else None
        f = a.factor
        factor = factor * f if (factor is not None and f is not None) else None
    affine = None
    if len(atoms) == 1 and atoms[0].unit is not None and atoms[0].unit.affine and atoms[0].power == 1:
        affine = (atoms[0].unit.factor or Fraction(1), atoms[0].unit.offset)
    return UnitReading(atoms=tuple(atoms), dim=dim, factor=factor, affine=affine, note=note)


def unit_dimension(text: str, **kw: object) -> Optional[Dimension]:
    """The dimension of a unit expression when it is read unambiguously, else None."""
    u = parse_unit(text, **kw)  # type: ignore[arg-type]
    return None if u is None or u.unknown else u.dim


def unit_group(toks, a: int, b: int, profile) -> bool:
    """Tokens ``[a, b)`` (the inside of a bracket) are a unit expression only: unit atoms (or an unknown atom of two
    or more letters, such as 'yr'), exponents (``²``, ``^2``, ``^-1``, ``**2``, and glued to an atom in ASCII: ``K-1``,
    ``m2`` as the lexer reads it, ``cm3``) and product signs. Bounded by ``b - a``."""
    if b <= a:
        return False
    atoms = 0
    k = a
    while k < b:
        t = toks[k]
        prev = toks[k - 1] if k > a else None
        if t.kind == "IDENT" and not t.delta and not t.primes and (not t.sub or (len(t.sub) == 1 and "2" <= t.sub <= "9" and len(t.text) == 1)):
            if not (is_unit_atom(t.text, bare_m=profile.bare_m, tonne=profile.tonne) or (len(t.text) >= 2 and t.text.isascii() and t.text.isalpha())):
                return False
            atoms += 1
        elif t.kind == "OP" and t.text in "-+" and not t.space and prev is not None and prev.kind == "IDENT" and k + 1 < b \
                and toks[k + 1].kind == "NUM" and not toks[k + 1].space and len(toks[k + 1].text) == 1 and "1" <= toks[k + 1].text <= "9":
            k += 1  # an ASCII exponent glued to its atom: 'K-1'
        elif t.kind == "NUM" and not t.space and prev is not None and prev.kind == "IDENT" and len(prev.text) >= 2 and len(t.text) == 1 \
                and "2" <= t.text <= "9":
            pass  # 'cm3'
        elif t.kind == "SUP" and not t.space:
            pass
        elif t.kind in ("CARET", "DSTAR") and not t.space:
            if k + 1 < b and toks[k + 1].kind == "OP" and toks[k + 1].text in "-−+":
                k += 1
            if k + 1 >= b or toks[k + 1].kind != "NUM":
                return False
            k += 1
        elif t.kind == "OP" and t.text in ("·", "*", "⋅"):
            pass
        else:
            return False
        k += 1
    return atoms > 0


def compound_part(toks, k: int) -> bool:
    """The numeral at ``k`` and the unit atom after it continue the quantity whose unit atom stands right before ``k`` ('4 min 30 s',
    '1 kg 250 g', '1 h 2 min'): both single atoms of one dimension, the second strictly smaller, exact and with no offset
    (stem-precision-5)."""
    if k < 1 or k + 1 >= len(toks) or toks[k - 1].kind != "IDENT" or toks[k + 1].kind != "IDENT" or not toks[k + 1].space:
        return False
    if k + 2 < len(toks) and toks[k + 2].kind in ("SUP", "CARET") and not toks[k + 2].space:
        return False
    a, b = parse_unit(toks[k - 1].text), parse_unit(toks[k + 1].text)
    if a is None or b is None or len(a.readings) != 1 or len(b.readings) != 1 or a.unknown or b.unknown:
        return False
    ra, rb = a.readings[0], b.readings[0]
    if len(ra.atoms) != 1 or len(rb.atoms) != 1 or ra.dim is None or ra.dim != rb.dim or not any(ra.dim.exps):
        return False
    if ra.factor is None or rb.factor is None or ra.affine is not None or rb.affine is not None:
        return False
    return rb.factor < ra.factor
