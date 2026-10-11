"""Exact numbers as written: value, significant figures, last place, half-width.

``ExactNumber`` (docs/STEM_DESIGN.md, section 5.1) keeps everything the STEM tolerance
rule needs from a written numeral:

* ``value``: the exact ``Fraction`` (scientific notation expanded exactly);
* ``sig_figs``: leading zeros are not significant, trailing zeros after the point are,
  scientific notation counts the mantissa; the trailing zeros of an integer written
  without a point are not counted (their significance depends on the expression, see
  :meth:`ExactNumber.half_width_for`);
* ``last_place``: the power of ten of the last written digit (``5.0`` -> -1,
  ``1.20 × 10³`` -> 1, ``1200`` -> 0);
* ``half_width``: half a unit in the last written digit (``5.0`` -> 0.05, ``1.20 × 10³``
  -> 5); a bare ``0`` is exact zero (0); an integer written without a point uses its
  trailing zeros (``1200`` -> 50) unless :meth:`half_width_for` is given the expression's
  smallest significant-figure count;
* ``exact``: the written form has no decimal point anywhere (an integer, a vulgar
  fraction, a based numeral, an integer mantissa). This describes the WRITTEN FORM only:
  a number that carries a unit is a measurement, and the checks never put it in exact
  mode because of this flag (``200 km ÷ 3 h = 67 km h⁻¹`` is measured data);
* ``exponent``: the written decimal exponent (0 when none), for decimal-exponent factoring.

:func:`scan_number` is the one number reader of the STEM front end. The lexer calls it,
and other readers (the ledger's figure extraction) may call it. It reads, from an offset,
plain integers and decimals, thousands groups (``,`` or a thin space, groups of exactly
three digits), a decimal comma (1 or 2 digits after it, when the caller allows it), and
every scientific form of section 4.4: ``1.2 × 10⁶``, ``1.2 x 10^6``, ``1.2×10^{6}``,
``1.2*10**6``, ``1.2e6``, ``6.0E-3``, ``2.250 \\times 10^{-3}``, a bare power of ten
(``10^(−3)``, ``10⁻³``), with a Unicode or ASCII minus in mantissa and exponent.
:func:`scan_based` reads base-marked integers (``0xFF``, ``0b1010``, ``0o17``, ``FF₁₆``,
``1010₂``, ``1010_2``, ``FF_{16}``).

Safety: only ASCII digits are accepted (``str.isdigit`` would accept other scripts), a
``Fraction`` is built only from validated digit strings or integer pairs, and the digit
and exponent bounds of :class:`~epinoic_logic.stem.limits.StemLimits` are checked BEFORE
any integer is built, so ``10^999999`` or a 10,000-digit numeral costs one linear scan and
yields a named error, never a huge integer.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from .limits import DEFAULT_LIMITS, StemLimits

__all__ = [
    "ExactNumber", "NumberScan", "SUPERSCRIPT_DIGITS", "SUBSCRIPT_DIGITS", "VULGAR_FRACTIONS", "exact_based", "exact_integer", "exact_vulgar",
    "is_ascii_digit", "scan_based", "scan_number", "superscript_int",
]

_DIGITS = "0123456789"
#: superscript digits and signs as written (⁰ to ⁹, ⁺, ⁻)
SUPERSCRIPT_DIGITS = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9"}
SUPERSCRIPT_SIGNS = {"⁻": "-", "⁺": "+"}
#: subscript digits (₀ to ₉)
SUBSCRIPT_DIGITS = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9"}
#: vulgar fraction characters read as exact fractions
VULGAR_FRACTIONS = {"½": (1, 2), "⅓": (1, 3), "⅔": (2, 3), "¼": (1, 4), "¾": (3, 4), "⅕": (1, 5), "⅛": (1, 8)}
#: characters that may separate thousands groups (checked in the ORIGINAL text: the reading view maps them to a space)
_THIN_SPACES = frozenset({" ", " ", " "})
_MINUS = frozenset({"-", "−"})
_PLUS = frozenset({"+"})
_TIMES = ("\\times", "\\cdot", "×", "·", "*", "x", "X", "⋅")
#: how many characters of spacing the scientific form may carry around its times sign and LaTeX spacing commands
_MAX_SCI_GAP = 6
_BASE_SUBSCRIPTS = {"₂": 2, "₈": 8, "₁₀": 10, "₁₆": 16}
_HEX = "0123456789abcdefABCDEF"


def is_ascii_digit(ch: str) -> bool:
    """True only for the ASCII digits 0 to 9 (``str.isdigit`` accepts other scripts and superscripts)."""
    return len(ch) == 1 and "0" <= ch <= "9"


@dataclass(frozen=True)
class ExactNumber:
    """A numeral as written. See the module docstring for the meaning of each field."""

    text: str
    value: Fraction
    sig_figs: int
    last_place: int
    exact: bool
    exponent: int = 0
    has_point: bool = False
    #: trailing zeros of an integer mantissa written without a point (``1200`` -> 2); 0 otherwise
    trailing_zeros: int = 0
    #: digits of the mantissa as written, leading zeros removed (``0.0250`` -> 3 digits ``250``)
    digit_count: int = 1
    #: 10 for decimal numerals; 2, 8 or 16 for a based numeral
    base: int = 10
    #: written in scientific notation (a mantissa times a power of ten, or an e-form)
    scientific: bool = False
    #: a vulgar fraction character (½)
    vulgar: bool = False
    #: a bare power of ten (``10⁻³``, ``10^(−3)``): an exact value
    power_of_ten: bool = False
    #: written with a base marker (``FF₁₆``, ``0b1010``, ``255₁₀``, ``(255)₁₀``): an exact integer
    based: bool = False

    @property
    def is_zero(self) -> bool:
        return self.value == 0

    @property
    def half_width(self) -> Fraction:
        """Half a unit in the last written digit. A bare integer zero, a vulgar fraction and a
        based numeral are exact (0). An integer written without a point: ½·10^k for its k
        trailing zeros (``25`` -> 1/2, ``1200`` -> 50)."""
        if self.vulgar or self.power_of_ten or self.based or self.base != 10:
            return Fraction(0)
        if self.value == 0 and not self.has_point and not self.scientific:
            return Fraction(0)
        if not self.has_point and not self.scientific:
            return Fraction(1, 2) * Fraction(10) ** self.trailing_zeros
        return Fraction(1, 2) * Fraction(10) ** self.last_place

    def half_width_for(self, min_sig_figs: Optional[int]) -> Fraction:
        """The half-width under the integer trailing-zero rule (section 5.1): the trailing zeros
        of an integer written without a point are significant only up to ``min_sig_figs`` (the
        smallest significant-figure count among the expression's measured operands, at least
        1). ``1200`` with 2-s.f. operands -> 50, with 3 -> 5, with 4 or more -> 1/2. Other forms
        keep :attr:`half_width`."""
        if min_sig_figs is None or self.has_point or self.scientific or self.vulgar or self.power_of_ten or self.base != 10 or self.value == 0:
            return self.half_width
        n = max(1, int(min_sig_figs))
        place = min(self.trailing_zeros, max(self.digit_count - n, 0))
        return Fraction(1, 2) * Fraction(10) ** place


def exact_integer(n: int, text: Optional[str] = None) -> ExactNumber:
    """An exact integer (a coefficient, a count, a based numeral's decimal value)."""
    s = text if text is not None else str(n)
    digits = str(abs(n))
    stripped = digits.rstrip("0") or "0"
    tz = len(digits) - len(stripped) if n != 0 else 0
    return ExactNumber(text=s, value=Fraction(n), sig_figs=max(1, len(stripped.lstrip("0")) or 1), last_place=0, exact=True,
                       trailing_zeros=tz, digit_count=max(1, len(digits)))


def exact_vulgar(ch: str) -> ExactNumber:
    """``½`` and its kin as exact fractions."""
    num, den = VULGAR_FRACTIONS[ch]
    return ExactNumber(text=ch, value=Fraction(num, den), sig_figs=1, last_place=0, exact=True, vulgar=True)


@dataclass(frozen=True)
class NumberScan:
    """The result of :func:`scan_number`: ``end`` is the offset just past what was read.
    ``number`` is None when the numeral breaks a bound; ``error`` then names it and
    ``code`` is ``ST-LIM-001``."""

    start: int
    end: int
    number: Optional[ExactNumber]
    error: str = ""
    code: str = ""


def _run(s: str, i: int, n: int) -> int:
    """End of the run of ASCII digits starting at ``i``."""
    j = i
    while j < n and is_ascii_digit(s[j]):
        j += 1
    return j


def superscript_int(s: str, i: int, n: int) -> tuple[int, Optional[str]]:
    """Read a superscript integer (``⁻¹²``) at ``i``: returns ``(end, signed digit text)`` or
    ``(i, None)`` when there are no superscript digits there."""
    j = i
    sign = ""
    if j < n and s[j] in SUPERSCRIPT_SIGNS:
        sign = SUPERSCRIPT_SIGNS[s[j]]
        j += 1
    k = j
    digits = []
    while k < n and s[k] in SUPERSCRIPT_DIGITS:
        digits.append(SUPERSCRIPT_DIGITS[s[k]])
        k += 1
    if not digits:
        return i, None
    return k, ("-" if sign == "-" else "") + "".join(digits)


def _skip_gap(s: str, i: int, n: int) -> int:
    """Skip spaces and LaTeX spacing commands (``\\,``, ``\\;``, ``\\!``, ``\\ ``) within a bounded gap."""
    j = i
    budget = _MAX_SCI_GAP
    while j < n and budget > 0:
        if s[j] == " ":
            j += 1
        elif s[j] == "\\" and j + 1 < n and s[j + 1] in ",;! ":
            j += 2
        else:
            break
        budget -= 1
    return j


def _exponent_after_ten(s: str, i: int, n: int) -> tuple[int, Optional[str]]:
    """At ``i`` just past a literal ``10``: read ``⁻³``, ``^-3``, ``^{-3}``, ``^(−3)``, ``**-3``,
    ``**(-3)``. Returns ``(end, signed digit text)`` or ``(i, None)``."""
    end, digits = _exponent_after_ten_raw(s, i, n)
    if digits is None:
        return i, None
    # a further power after the exponent (10^10^10) is right-associative: it is not a power of ten, and the parser
    # reads it (and refuses the nested power) instead of folding the first two terms here
    if end < n and (s[end] == "^" or s.startswith("**", end) or s[end] in SUPERSCRIPT_DIGITS or s[end] in SUPERSCRIPT_SIGNS):
        return i, None
    return end, digits


def _exponent_after_ten_raw(s: str, i: int, n: int) -> tuple[int, Optional[str]]:
    if i < n and (s[i] in SUPERSCRIPT_DIGITS or s[i] in SUPERSCRIPT_SIGNS):
        return superscript_int(s, i, n)
    j = i
    if s.startswith("**", j):
        j += 2
    elif j < n and s[j] == "^":
        j += 1
    else:
        return i, None
    close = ""
    if j < n and s[j] in "{(":
        close = "}" if s[j] == "{" else ")"
        j += 1
        while j < n and s[j] == " ":
            j += 1
    sign = ""
    if j < n and (s[j] in _MINUS or s[j] in _PLUS):
        sign = "-" if s[j] in _MINUS else ""
        j += 1
    k = _run(s, j, n)
    if k == j:
        return i, None
    digits = s[j:k]
    if close:
        while k < n and s[k] == " ":
            k += 1
        if k >= n or s[k] != close:
            return i, None
        k += 1
    elif k < n and (s[k] == "." and k + 1 < n and is_ascii_digit(s[k + 1])):
        return i, None  # 10^2.5: not an integer exponent
    return k, sign + digits


def _exponent_value(digits: str, limits: StemLimits) -> Optional[int]:
    """The signed exponent, or None when it breaks ``max_sci_exponent`` (checked on the digit count first)."""
    neg = digits.startswith("-")
    body = digits[1:] if neg else digits
    body = body.lstrip("0") or "0"
    if len(body) > 4:
        return None
    value = int(body)
    if value > limits.max_sci_exponent:
        return None
    return -value if neg else value


def _times_ten(s: str, i: int, n: int) -> tuple[int, Optional[str]]:
    """After a mantissa: `` × 10⁶``, ``x 10^6``, ``*10**6``, ``\\times 10^{6}``, ``\\cdot 10^{6}``.
    Returns ``(end, exponent digit text)`` or ``(i, None)``."""
    j = _skip_gap(s, i, n)
    matched = ""
    for t in _TIMES:
        if s.startswith(t, j):
            if t == "*" and s.startswith("**", j):
                continue
            matched = t
            break
    if not matched:
        return i, None
    if matched in ("x", "X") and j > 0 and s[j - 1] not in " 0123456789":
        return i, None
    j = _skip_gap(s, j + len(matched), n)
    if not s.startswith("10", j) or (j + 2 < n and is_ascii_digit(s[j + 2])):
        return i, None
    end, exp = _exponent_after_ten(s, j + 2, n)
    if exp is None:
        return i, None
    return end, exp


def _e_exponent(s: str, i: int, n: int) -> tuple[int, Optional[str]]:
    """``e6``, ``E-3``, ``e−11`` directly after a mantissa."""
    if i >= n or s[i] not in "eE":
        return i, None
    j = i + 1
    sign = ""
    if j < n and (s[j] in _MINUS or s[j] in _PLUS):
        sign = "-" if s[j] in _MINUS else ""
        j += 1
    k = _run(s, j, n)
    if k == j:
        return i, None
    if k < n and (s[k].isalpha() or s[k] == "_"):
        return i, None  # '2e3x' is not a numeral
    return k, sign + s[j:k]


def scan_number(s: str, i: int, *, limits: StemLimits = DEFAULT_LIMITS, orig: Optional[str] = None, decimal_comma: bool = False,
                thousands_comma: bool = True, scientific: bool = True, build: bool = True) -> Optional[NumberScan]:
    """Read one numeral of ``s`` starting at ``i`` (an ASCII digit, or a point followed by a digit).
    Returns None when no numeral starts at ``i``.

    ``orig`` (same length as ``s``) is consulted for thin-space thousands separators, which the
    reading view maps to a plain space. ``decimal_comma`` allows ``1,5`` (one or two digits after
    the comma, no digit after them, no space after the comma); the lexer allows it only outside
    brackets so coordinate pairs and lists stay separate numbers; for the same reason it turns
    ``thousands_comma`` off inside brackets (``[100,200]`` is two numbers). ``scientific`` reads
    the forms with a times sign and a power of ten. With ``build`` False only the extent and the
    bounds are checked (``number`` stays None and ``error`` empty): the span finder needs no values."""
    n = len(s)
    if i >= n:
        return None
    start = i
    if s[i] == "." and i + 1 < n and is_ascii_digit(s[i + 1]):
        int_digits = ""
        j = i
    elif is_ascii_digit(s[i]):
        j = _run(s, i, n)
        int_digits = s[i:j]
        # thousands groups: an integer part of 1 to 3 digits (no leading zero), then ',ddd' or thin-space 'ddd' groups of exactly three
        if len(int_digits) <= 3 and int_digits[0] != "0":
            parts = [int_digits]
            k = j
            sep_kind = ""
            while k < n:
                sep = s[k]
                thin = orig is not None and k < len(orig) and orig[k] in _THIN_SPACES
                kind = "," if (sep == "," and thousands_comma) else ("thin" if thin else "")
                if not kind or (sep_kind and kind != sep_kind):
                    break
                e = _run(s, k + 1, n)
                if e - (k + 1) != 3:
                    break
                parts.append(s[k + 1:e])
                sep_kind = kind
                k = e
            if len(parts) > 1:
                int_digits = "".join(parts)
                j = k
    else:
        return None
    frac_digits = ""
    has_point = False
    if j < n and s[j] == "." and j + 1 < n and is_ascii_digit(s[j + 1]):
        e = _run(s, j + 1, n)
        frac_digits = s[j + 1:e]
        has_point = True
        j = e
    elif decimal_comma and j < n and s[j] == "," and int_digits and "," not in s[start:j]:
        e = _run(s, j + 1, n)
        if 1 <= e - (j + 1) <= 2 and not (e < n and s[e] in ".,"):
            frac_digits = s[j + 1:e]
            has_point = True
            j = e
    exp_text: Optional[str] = None
    sci = False
    if scientific:
        end, exp_text = _e_exponent(s, j, n)
        if exp_text is None:
            end, exp_text = _times_ten(s, j, n)
        if exp_text is None and int_digits == "10" and not has_point:
            # a bare power of ten: 10⁻³, 10^(−3), 10^{6}, 10**-19
            e2, exp2 = _exponent_after_ten(s, j, n)
            if exp2 is not None:
                return _finish(s, start, e2, "1", "", False, exp2, True, limits, bare_power=True, build=build)
        if exp_text is not None:
            j = end
            sci = True
    return _finish(s, start, j, int_digits, frac_digits, has_point, exp_text, sci, limits, build=build)


def _finish(s: str, start: int, end: int, int_digits: str, frac_digits: str, has_point: bool, exp_text: Optional[str], sci: bool,
            limits: StemLimits, *, bare_power: bool = False, build: bool = True) -> NumberScan:
    digits = int_digits + frac_digits
    if len(digits) > limits.max_number_digits:
        return NumberScan(start, end, None, f"the numeral has {len(digits)} written digits; the bound is {limits.max_number_digits}", "ST-LIM-001")
    exponent = 0
    if exp_text is not None:
        value = _exponent_value(exp_text, limits)
        if value is None:
            return NumberScan(start, end, None, f"the scientific exponent {exp_text[:12]} exceeds the bound |e| <= {limits.max_sci_exponent}", "ST-LIM-001")
        exponent = value
    if not digits:
        return NumberScan(start, end, None, "no digits", "ST-PARSE-001")
    if not build:
        return NumberScan(start, end, None)
    text = s[start:end]
    significant = digits.lstrip("0")
    value_f = Fraction(int(digits), 10 ** len(frac_digits)) * (Fraction(10) ** exponent)
    trailing = 0
    if has_point:
        sig = len(significant) if significant else 1  # '0.0': one written digit
    elif sci:
        sig = max(1, len(significant))  # an integer mantissa counts as written
    else:
        stripped = significant.rstrip("0")
        sig = max(1, len(stripped))
        trailing = len(significant) - len(stripped) if significant else 0
    return NumberScan(start, end, ExactNumber(
        text=text, value=value_f, sig_figs=sig, last_place=-len(frac_digits) + exponent, exact=not has_point, exponent=exponent,
        has_point=has_point, trailing_zeros=trailing, digit_count=max(1, len(significant)), scientific=sci and not bare_power,
        power_of_ten=bare_power,
    ))


def scan_based(s: str, i: int, *, limits: StemLimits = DEFAULT_LIMITS) -> Optional[tuple[int, ExactNumber, str]]:
    """Read a base-marked integer at ``i``: ``0xFF``, ``0b1010``, ``0o17``, or hexadecimal or
    decimal digits followed by a base subscript (``FF₁₆``, ``1010₂``, ``1010_2``, ``FF_{16}``,
    ``377₈``). Returns ``(end, number, digits)`` or None. A digit not valid in the stated base
    (``1012₂``) is no based numeral (None), and a run longer than ``max_based_digits`` is not
    read (None) so the scan stays bounded."""
    n = len(s)
    if i >= n:
        return None
    if s[i] == "0" and i + 2 < n and s[i + 1] in "xXbBoO":
        base = {"x": 16, "b": 2, "o": 8}[s[i + 1].lower()]
        j = i + 2
        k = j
        while k < n and s[k] in _HEX and k - j <= limits.max_based_digits:
            k += 1
        digits = s[j:k]
        if not digits or k - j > limits.max_based_digits or (k < n and (s[k].isalnum() or s[k] == "_")):
            return None
        if not all(int(c, 16) < base for c in digits):
            return None
        return k, _based(s[i:k], digits, base), digits
    if s[i] not in _HEX:
        return None
    k = i
    while k < n and s[k] in _HEX and k - i <= limits.max_based_digits:
        k += 1
    if k - i > limits.max_based_digits:
        return None
    digits = s[i:k]
    base = 0
    end = k
    for sub, b in sorted(_BASE_SUBSCRIPTS.items(), key=lambda kv: -len(kv[0])):
        if s.startswith(sub, k):
            base, end = b, k + len(sub)
            break
    if not base and k < n and s[k] == "_":
        j = k + 1
        brace = j < n and s[j] == "{"
        if brace:
            j += 1
        e = _run(s, j, n)
        if e > j and s[j:e] in ("2", "8", "10", "16"):
            if brace:
                if e < n and s[e] == "}":
                    base, end = int(s[j:e]), e + 1
            else:
                base, end = int(s[j:e]), e
    if not base:
        return None
    if end < n and (s[end].isalnum() or s[end] in SUBSCRIPT_DIGITS):
        return None
    if not all(int(c, 16) < base for c in digits):
        return None
    return end, _based(s[i:end], digits, base), digits


def exact_based(text: str, digits: str, base: int, *, limits: StemLimits = DEFAULT_LIMITS) -> Optional[ExactNumber]:
    """``digits`` (ASCII digits or hexadecimal letters) read in ``base`` (2, 8, 10 or 16) as an
    exact based numeral written as ``text`` (``(1010)₂``). None when a digit is not valid in the
    base, the base is not one of the four, or the run is longer than ``max_based_digits``."""
    if base not in (2, 8, 10, 16) or not digits or len(digits) > limits.max_based_digits:
        return None
    if not all(c in _HEX and int(c, 16) < base for c in digits):
        return None
    return _based(text, digits, base)


def _based(text: str, digits: str, base: int) -> ExactNumber:
    value = int(digits, base)
    return ExactNumber(text=text, value=Fraction(value), sig_figs=len(digits), last_place=0, exact=True, base=base, digit_count=len(digits), based=True)
