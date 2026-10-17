"""STEM fault injection for the arena harness (run_arena.py): contained multi-agent runs on STEM subjects.

Three mutations, applied only to answers of STEM subjects (the subjects the registry routes to the ``sciences``,
``mathematics`` or ``computer_science`` branch), each with the code that must name it on the receipt:

``stem_arithmetic_slip``   one stated result of a worked chain changed (``(20 − 0)/4.0 = 5.0`` → ``= 8.0``):
                           INT-SUBJ-001 (an engine check of the report's own arithmetic does not hold).
``stem_wrong_unit``        the unit of a stated result replaced by a unit of another dimension (``= 15 m s⁻¹`` →
                           ``= 15 m s⁻²``) in a link whose operands carry units: ST-DIM-001 (or ST-DIM-002), a warning.
``stem_substitution``      a value the request gives, substituted into a calculation, written as another value
                           (``…/4.0`` → ``…/7.0`` with 4.0 s in the request): INT-SUBJ-001.

The sites are found with bounded regular expressions over the answer's own text, independently of the STEM front end
under test, and every change moves the leading significant digit of a number by 3 (d + 3 for d ≤ 6, else d − 3): a
change of at least three units in the leading place, which no rounding of the written figures can absorb. A figure
written as the exponent of a power of ten (``10^(−8.2)``, or of e-notation: ``6.31e-9``) is the one exception: moving its leading digit in the units
place multiplies the power by exactly 10³, the factor of a unit prefix (mol dm⁻³ against mol m⁻³) that the documented SI
reading of a stated unit absorbs, so its first decimal digit moves by 3 instead (``10^(−8.5)``: a factor 10^0.3), and
an exponent of ten written with no decimal digit is no site. A mutation with no site in an answer is skipped
(``None``), as ``altered_quotation`` is for an answer with no quotation. The marker (the mutated stretch a finding's
claim must carry) stays inside one statement: it stops at the end of its sentence and leaves a part label ("(b) ") and a
closing mark annotation ("  M1", "(A1)", "[2]") out, as every claim does.

Applicability (``not_applicable``). An injection no finding names is a miss unless the changed figure lies in an
expression in symbols: for a slip, the computed side of the changed relation; for a substitution, the stretch that holds
the changed figure. A written calculation (of figures, and of symbols the answer or the request states a value for:
``x = 5``, ``P₀ = 250``, each root of ``x = 2 or x = 3``) is always applicable, whether or not a value is stated beside it.
Only an expression that holds a symbol no statement gives a value (``P(t + 4) = P₀e^(k(t + 1))``, an identity in the
function P; ``18 000 = M × …``, an equation in the unknown M) is a candidate, and run_arena.py reports it NOT APPLICABLE
only when the change also moved none of the receipt's formal checks (each holds, fails or stays undecided as on the
genuine answer). The round-7 identities in symbols that stem-sub, stem-alg and stem-sol checks name (``low = mid + 4``
with ``mid = 1`` stated, ``800 = 1600 e^(−5k)`` with k stated) are written calculations in this reading, so they would
be misses if no finding named them. A symbol here is a letter (with its subscript) that is not a unit written after a
figure, a function name, π, Euler's e under a power, a LaTeX command of arithmetic or layout, or a mark annotation; a
run of prose words before or after the expression is not part of it. The reading is the harness's own, independent of
the front end under test, and errs towards applicable: a figure it cannot place, or a symbol it reads as stated by
mistake, makes the injection count. Nothing here evaluates text.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional

STEM_MUTATIONS = ("stem_arithmetic_slip", "stem_wrong_unit", "stem_substitution")
#: codes that name each STEM mutation on a receipt
STEM_EXPECTED = {
    "stem_arithmetic_slip": ("INT-SUBJ-001",),
    "stem_wrong_unit": ("ST-DIM-001", "ST-DIM-002"),
    "stem_substitution": ("INT-SUBJ-001",),
}
STEM_BRANCHES = frozenset({"sciences", "mathematics", "computer_science"})

_MAX_SCAN = 200_000
#: the longest operand stretch before a relation sign that is examined (a bound on the work per sign)
_WINDOW = 200
_OPERATOR_CHARS = frozenset("×*/÷+−-·")
_OPERATOR_WORDS = ("\\times", "\\cdot")
#: unit swaps: a result unit and one of another dimension (unicode, ASCII and LaTeX spellings), longest first
_UNIT_SWAPS = sorted([
    ("m s⁻²", "m s⁻¹"), ("m s⁻¹", "m s⁻²"), ("m/s^2", "m/s"), ("m/s²", "m/s"), ("m/s", "m/s^2"), ("km h⁻¹", "km h⁻²"),
    ("kg m s⁻¹", "kg m s⁻²"), ("mol dm⁻³", "mol dm⁻²"), ("g mol⁻¹", "g mol"), ("N", "J"), ("J", "N"), ("kJ", "kN"), ("W", "J"), ("Pa", "N"),
    ("kPa", "kN"), ("V", "A"), ("A", "V"), ("Ω", "V"), ("Hz", "s"), ("kg", "mol"), ("mol", "kg"), ("g", "mol"), ("K", "J"), ("s", "m"), ("m", "s"),
    ("m³", "m²"), ("m²", "m³"), ("cm³", "cm²"), ("dm³", "dm²"),
], key=lambda p: -len(p[0]))
_UNIT_TAIL = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789⁰¹²³⁴⁵⁶⁷⁸⁹⁻^/_")
#: mark annotations closing a stretch ("  M1", "(A1)", "[2]", "[1 spare]"): marking furniture, which no claim carries
_ANNOTATION_TAIL_RE = re.compile(r"(?:(?:[ \t]{2,}|\t)\(?[MARN]\d{1,2}\)?|[ \t]*\([MARN]\d{1,2}\)|[ \t]*\[[ \t]*\d{1,2}(?:[ \t]*(?:marks?|spare))?[ \t]*\])+[ \t]*$")
#: the end of a sentence inside a line: a full stop, question or exclamation mark, then a space and a capital or a figure
_SENTENCE_END_RE = re.compile(r"[.?!](?=[ \t]+[A-Z0-9(\[])")
#: a part label opening a line ("(b) ", "(a)(ii) ", "2. ", "b) ", "Part (c): "): structure, which no claim carries
_PART_LABEL_RE = re.compile(r"[ \t]*(?:(?:part|question|q)[ \t]*)?(?:\([ \t]*(?:[a-h]|[ivx]{1,4}|\d{1,2})[ \t]*\)|(?:[a-h]|[ivx]{1,4})\)|\d{1,2}[.)])"
                            r"(?:[ \t]*\([ \t]*(?:[a-h]|[ivx]{1,4})[ \t]*\))?[ \t]*[:.]?[ \t]+", re.IGNORECASE)
#: a power of ten written just before a figure: "10^", "10^(", "10^{", "10**", with an optional sign before the figure
_TEN_POWER_RE = re.compile(r"(?<![\d.])10[ \t]*(?:\^|\*\*)[ \t]*[({]?[ \t]*[-−+]?[ \t]*$")
#: the exponent of scientific e-notation just before a figure: "6.31e-", "2E+", a mantissa's last digit or point then e or E
_E_EXPONENT_RE = re.compile(r"[0-9.][eE][-−+]?$")


def _number_at(text: str, i: int, end: int) -> int:
    """The end of a decimal number starting at ``i`` (digits, optionally a point and digits), or ``i`` when none starts there."""
    k = i
    while k < end and text[k].isdigit() and text[k].isascii():
        k += 1
    if k == i:
        return i
    if k + 1 < end and text[k] == "." and text[k + 1].isdigit() and text[k + 1].isascii():
        k += 1
        while k < end and text[k].isdigit() and text[k].isascii():
            k += 1
    return k


def _has_operator_between_figures(seg: str) -> bool:
    """A figure, then an arithmetic operator, then a figure (units may stand between): one pass over ``seg``."""
    seen_digit = seen_op = False
    i, n = 0, len(seg)
    while i < n:
        ch = seg[i]
        if ch.isdigit():
            if seen_op:
                return True
            seen_digit = True
        elif seen_digit and (ch in _OPERATOR_CHARS or seg.startswith(_OPERATOR_WORDS, i)):
            seen_op = True
        i += 1
    return False


def _unit_at(text: str, i: int, end: int) -> str:
    """The table unit written at ``i`` and ending there (not followed by more unit characters), or ''."""
    for unit, _other in _UNIT_SWAPS:
        j = i + len(unit)
        if j <= end and text.startswith(unit, i) and (j == end or text[j] not in _UNIT_TAIL):
            return unit
    return ""


def _has_quantity(seg: str) -> bool:
    """A figure followed (after at most one space) by a table unit: bounded by ``len(seg)`` times the table size."""
    for i, ch in enumerate(seg):
        if ch.isdigit() and i + 1 < len(seg) and not seg[i + 1].isdigit():
            k = i + 1 + (1 if seg[i + 1] == " " else 0)
            if _unit_at(seg, k, len(seg)):
                return True
    return False


def _relations(text: str):
    """``(operand start, sign index, value start, value end)`` for every '=' followed by a number, line by line: the operand
    is the stretch since the previous sign (at most ``_WINDOW`` characters). Linear in the text."""
    n = min(len(text), _MAX_SCAN)
    line_start = 0
    prev = -1
    i = 0
    while i < n:
        ch = text[i]
        if ch == "\n":
            line_start, prev = i + 1, -1
        elif ch == "=":
            lo = max(line_start, prev + 1, i - _WINDOW)
            j = i + 1
            while j < n and text[j] == " ":
                j += 1
            sign = j < n and text[j] in "−-"
            k = _number_at(text, j + (1 if sign else 0), n)
            if k > j + (1 if sign else 0):
                yield lo, i, j + (1 if sign else 0), k
            prev = i
        i += 1


class StemInjection(NamedTuple):
    """A mutated answer, the codes that must name the fault, the mutated text a finding's claim must carry, the mutation
    kind and the offsets of the changed stretch in ``text`` (``site``)."""
    text: str
    expected: tuple[str, ...]
    marker: str
    kind: str = ""
    site: tuple[int, int] = (0, 0)


def leading_digit_slip(number: str) -> str:
    """``number`` with its leading significant digit moved by 3 (d + 3 for d ≤ 6, else d − 3)."""
    for i, ch in enumerate(number):
        if ch in "123456789":
            d = int(ch)
            return number[:i] + str(d + 3 if d <= 6 else d - 3) + number[i + 1:]
    raise ValueError(f"no significant digit in {number!r}")


def _digit_moved(d: str) -> str:
    v = int(d)
    return str(v + 3 if v <= 6 else v - 3)


def figure_change(text: str, a: int, b: int) -> Optional[str]:
    """The figure ``text[a:b]`` as the injection writes it: the leading significant digit moved by 3, except for a figure
    written as the exponent of a power of ten (``10^(−8.2)``, or of e-notation: ``6.31e-9``), whose leading digit in the
    units place or above would change the power by an exact power of ten (a unit prefix's factor, which the SI reading
    of a stated unit absorbs): its first decimal digit moves by 3 instead (``8.2`` → ``8.5``: a factor 10^0.3). None
    when such an exponent has no decimal digit (no change there escapes every unit factor) or the figure has no
    significant digit."""
    num = text[a:b]
    if not any(c in "123456789" for c in num):
        return None
    if _TEN_POWER_RE.search(text, max(0, a - 12), a) is None and _E_EXPONENT_RE.search(text, max(0, a - 3), a) is None:
        return leading_digit_slip(num)
    point = num.find(".")
    lead = next(i for i, c in enumerate(num) if c in "123456789")
    if point < 0 or lead > point:
        return leading_digit_slip(num) if point >= 0 else None  # 0.4 -> 0.7 already moves by 10^0.3; an integer exponent has no site
    if point + 1 >= len(num):
        return None
    return num[:point + 1] + _digit_moved(num[point + 1]) + num[point + 2:]


def is_stem_subject(subject: str) -> bool:
    """True when the registry routes ``subject`` to a STEM branch (the routing the hub itself applies)."""
    from epinoic_logic.branches.registry import default_registry
    return default_registry().for_subject(subject)[0].key in STEM_BRANCHES


def _line_bounds(text: str, a: int) -> tuple[int, int]:
    """The line around ``a``, at most ``_WINDOW`` characters each way."""
    s = text.rfind("\n", max(0, a - _WINDOW), a) + 1 or max(0, a - _WINDOW)
    s = max(s, a - _WINDOW)
    e = text.find("\n", a, a + _WINDOW)
    return s, min(len(text), a + _WINDOW) if e < 0 else e


def _link_marker(text: str, a: int, b: int, *, through_next_relation: bool = False) -> str:
    """The mutated link as a marker: from the relation sign before the operand that holds ``[a, b)`` (``through_next``:
    the operand alone, up to the next relation sign) — a stretch inside one statement, so the claim that carries it is
    found by its text. Bounded by the line, and by the sentence that holds the operand ("low = mid + 4 is safe. In an
    unsorted list ..." gives "mid + 4 is safe"); a mark annotation closing the stretch ("6 − 9t  M1") is left out, as
    every claim leaves it out."""
    s, e = _line_bounds(text, a)
    label = _PART_LABEL_RE.match(text, s) if s == 0 or text[s - 1] == "\n" else None
    if label is not None and label.end() <= a:
        s = label.end()  # a part label opening the line is structure: no claim carries it
    if through_next_relation:
        left = text.rfind("=", s, a)
        right = text.find("=", b, e)
        lo = (left + 1) if left >= 0 else s
        hi = right if right >= 0 else e
        end = _SENTENCE_END_RE.search(text, b, hi)
        if end is not None:
            hi = end.start()
        tail = _ANNOTATION_TAIL_RE.search(text, b, hi)
        if tail is not None:
            hi = tail.start()
    else:
        eq = text.rfind("=", s, a)
        left = text.rfind("=", s, eq) if eq >= 0 else -1
        lo = (left + 1) if left >= 0 else s
        hi = b
    for stop in (". ", "; ", ", "):
        k = text.rfind(stop, lo, a)
        if k >= 0:
            lo = k + len(stop)
    return text[lo:hi].strip(" $\t")


def arithmetic_slip(text: str) -> Optional[StemInjection]:
    """The first stated result of a worked chain (an operator between figures before ``=``) with its leading digit moved
    (:func:`figure_change`)."""
    for lo, _sign, a, b in _relations(text):
        if not _has_operator_between_figures(text[lo:_sign]):
            continue
        new = figure_change(text, a, b)
        if new is None:
            continue
        mutated = text[:a] + new + text[b:]
        return StemInjection(mutated, STEM_EXPECTED["stem_arithmetic_slip"], _link_marker(mutated, a, a + len(new)), "stem_arithmetic_slip",
                             (a, a + len(new)))
    return None


def wrong_unit(text: str) -> Optional[StemInjection]:
    """The unit of the first stated result whose left side carries quantities with units and an operator, replaced by a
    unit of another dimension (the left side's units fix the dimension, so the mismatch is visible to a dimension check)."""
    swaps = dict(_UNIT_SWAPS)
    n = min(len(text), _MAX_SCAN)
    for lo, sign, _a, b in _relations(text):
        k = b + (1 if b < n and text[b] == " " else 0)
        unit = _unit_at(text, k, n)
        lhs = text[lo:sign]
        if not unit or not _has_quantity(lhs) or not any(c in _OPERATOR_CHARS for c in lhs):
            continue
        mutated = text[:k] + swaps[unit] + text[k + len(unit):]
        return StemInjection(mutated, STEM_EXPECTED["stem_wrong_unit"], _link_marker(mutated, k, k + len(swaps[unit])), "stem_wrong_unit",
                             (k, k + len(swaps[unit])))
    return None


def _numbers(text: str):
    """``(start, end)`` of every decimal number not glued to another figure or point, in one pass."""
    n = min(len(text), _MAX_SCAN)
    i = 0
    while i < n:
        if text[i].isdigit() and text[i].isascii() and (i == 0 or not (text[i - 1].isdigit() or text[i - 1] == ".")):
            k = _number_at(text, i, n)
            if not (k < n and (text[k].isdigit() or text[k] == ".")):
                yield i, k
            i = max(k, i + 1)
        else:
            i += 1


def _given_values(question: str) -> set[str]:
    return {question[a:b] for a, b in _numbers(question) if any(c in "123456789" for c in question[a:b])}


def substitution(text: str, question: str) -> Optional[StemInjection]:
    """A value the request gives, written in the answer as an operand of an arithmetic operator (a substitution in a
    calculation, not a ``Given`` line or a stated value), with its leading digit moved. Only that occurrence changes, so
    the substituted value no longer matches the request and the chain's arithmetic no longer holds."""
    givens = _given_values(question)
    if not givens:
        return None
    for a, b in _numbers(text):
        num = text[a:b]
        if num not in givens:
            continue
        before = text[max(0, a - 40):a]
        before = before[before.rfind("\n") + 1:].rstrip(" (")
        after = text[b:b + 40]
        after = after[:after.find("\n")] if "\n" in after else after
        after = after.lstrip(" )")
        beside_op = (before[-1:] in _OPERATOR_CHARS or before.endswith(_OPERATOR_WORDS)) or (after[:1] in _OPERATOR_CHARS or after.startswith(_OPERATOR_WORDS))
        if not beside_op or before.lstrip().lower().startswith(("given", "data")):
            continue
        stripped = before.rstrip()
        if stripped.endswith("=") and stripped[:-1].rstrip()[-1:].isalpha():
            continue  # 'x = 8.0 …': a value stated for a symbol, not a substitution
        line_end = text.find("\n", b, b + _WINDOW)
        if "=" not in text[a:(line_end if line_end >= 0 else b + _WINDOW)] and "=" not in before:
            continue
        new = figure_change(text, a, b)
        if new is None:
            continue
        mutated = text[:a] + new + text[b:]
        return StemInjection(mutated, STEM_EXPECTED["stem_substitution"], _link_marker(mutated, a, a + len(new), through_next_relation=True),
                             "stem_substitution", (a, a + len(new)))
    return None


def mutate_stem(text: str, question: str, kind: str) -> Optional[StemInjection]:
    """The STEM mutation ``kind`` of ``text`` (an answer to ``question``), or None when the answer has no site for it."""
    if kind == "stem_arithmetic_slip":
        return arithmetic_slip(text)
    if kind == "stem_wrong_unit":
        return wrong_unit(text)
    if kind == "stem_substitution":
        return substitution(text, question)
    raise ValueError(kind)


# --- applicability: does the changed figure lie in a written calculation? ---------------------------------------------
#
# The harness's own reading, independent of the STEM front end under test (module docstring). It is asked only about an
# injection that no finding named. A changed figure inside a written calculation (of figures, and of symbols the answer
# or the request states a value for) is a miss. One that lies in an expression holding a symbol no statement gives a
# value (an identity, an equation in an unknown) is a candidate for NOT APPLICABLE, which run_arena.py grants only when
# the change also moved none of the receipt's formal checks; anything the reading cannot place is applicable.

#: function names a written calculation may apply to figures
_FUNCTION_WORDS = frozenset({"sin", "cos", "tan", "arcsin", "arccos", "arctan", "ln", "log", "lg", "exp", "sqrt"})
#: Greek-letter LaTeX commands: symbols (``\pi`` is the constant π)
_LATEX_GREEK = frozenset({"alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta", "vartheta", "iota", "kappa", "lambda",
                          "mu", "nu", "xi", "rho", "varrho", "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega", "Gamma", "Delta",
                          "Theta", "Lambda", "Xi", "Sigma", "Upsilon", "Phi", "Psi", "Omega"})
#: LaTeX commands whose braced group is text (a unit after a figure, otherwise a word)
_LATEX_TEXT_GROUPS = frozenset({"text", "mathrm", "operatorname", "textrm", "rm", "mbox", "textit", "mathit", "textbf"})
#: LaTeX relation commands (an operand ends at each)
_LATEX_RELATIONS = frozenset({"approx", "simeq", "neq", "ne", "leq", "le", "geq", "ge", "lt", "gt", "Rightarrow", "implies", "to", "rightarrow",
                              "therefore", "equiv", "sim"})
_RELATION_CHARS = frozenset("=≈≃≠≤≥<>⇒→∴≡")
_PREFIXES = ("", "k", "M", "G", "m", "µ", "μ", "n", "p", "c", "d", "h")
_BASE_UNITS = ("m", "g", "s", "A", "K", "mol", "N", "J", "W", "Pa", "Hz", "C", "V", "Ω", "F", "T", "Wb", "H", "S", "L", "l", "eV", "Bq", "Gy", "Sv",
               "cd", "lm", "lx", "M", "Da", "b", "B")
#: unit atoms read after a figure (or after another unit): SI units with prefixes and the common units of the IB subjects
_UNIT_ATOMS = frozenset({p + u for p in _PREFIXES for u in _BASE_UNITS} | {
    "min", "h", "hr", "hrs", "d", "day", "days", "yr", "yrs", "year", "years", "month", "months", "week", "weeks", "hour", "hours", "minute",
    "minutes", "second", "seconds", "t", "ppm", "ppb", "atm", "bar", "mmHg", "rad", "sr", "deg", "dB", "cal", "kcal", "u", "ohm", "ohms", "bit",
    "bits", "byte", "bytes", "KB", "kB", "MB", "GB", "TB", "marks", "counts", "items", "people", "students", "cells", "individuals", "metres",
    "meters", "grams", "kilograms", "joules", "watts", "volts", "amps", "newtons", "euros", "euro", "dollars", "pounds", "percent", "per"})
_TOKEN_RE = re.compile(
    r"(?P<cmd>\\[A-Za-z]+)"
    r"|(?P<space>\\[,;:! ]|[ \t~$]+)"
    r"|(?P<num>[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
    r"|(?P<sup>[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻₀₁₂₃₄₅₆₇₈₉½]+)"
    r"|(?P<word>[^\W\d_⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉½]+)"
    r"|(?P<open>[({\[])"
    r"|(?P<close>[)}\]])"
    r"|(?P<op>\*\*|[+\-−×÷*/·^√])"
    r"|(?P<punct>[,;:])"
    r"|(?P<other>.)", re.DOTALL)
#: a subscript written after a symbol, part of its name (P₀, R₁, T½, v_0, R_{1}); a superscript is a power, never a name
_SUBSCRIPT_RE = re.compile(r"[₀₁₂₃₄₅₆₇₈₉ₐₑₒₓₕₖₗₘₙₚₛₜ½]+|_\{[^{}\n]{1,12}\}|_[0-9A-Za-z]")
_SUBSCRIPT_PLAIN = str.maketrans("₀₁₂₃₄₅₆₇₈₉ₐₑₒₓₕₖₗₘₙₚₛₜ", "0123456789aeoxhklmnpst")
#: a value stated for a symbol (the harness's reading of a binding: ``x = 5``, ``P₀ = 250``, ``v_0 = 2.0 m s⁻¹``,
#: ``\lambda ≈ 0.087``, each root of ``x = 2 or x = 3``): a symbol of one to three letters or a LaTeX command, an optional
#: subscript, a relation sign, then a figure. A spurious reading only makes an injection applicable (counted).
_BINDING_RE = re.compile(r"(?<![\w\\])(\\[A-Za-z]+|[^\W\d_⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉½]{1,3})((?:[₀₁₂₃₄₅₆₇₈₉ₐₑₒₓₕₖₗₘₙₚₛₜ½]+|_\{[^{}\n]{1,12}\}|_[0-9A-Za-z])?)"
                         r"[ \t$]*(?:=|≈|\\approx)[ \t$]*[-−]?[ \t]*(?=[0-9]|\.[0-9])")
#: a mark annotation written as a code ("M1", "A1", "R1", "M1A1")
_MARK_CODE_RE = re.compile(r"(?:[MARN][0-9]{1,2})+")
_BINARY_OPS = frozenset({"+", "×", "÷", "*", "/", "·", "^", "**", "\\times", "\\cdot", "\\div"})


class _Tok(NamedTuple):
    cls: str        # figure, bound (a symbol with a stated value), unit, func, const, op, open, close, punct, word, other
    start: int
    end: int
    text: str


def _symbol_key(name: str) -> str:
    """One spelling of a symbol's name: ``P₀``, ``P_0`` and ``P_{0}`` are the same symbol."""
    m = re.match(r"(\\[A-Za-z]+|[^_₀₁₂₃₄₅₆₇₈₉ₐₑₒₓₕₖₗₘₙₚₛₜ½]+)(.*)", name, re.DOTALL)
    head, sub = (m.group(1), m.group(2)) if m else (name, "")
    sub = sub.lstrip("_").strip("{}").translate(_SUBSCRIPT_PLAIN)
    return head + ("_" + sub if sub else "")


def bound_symbols(*texts: str) -> frozenset[str]:
    """The symbols ``texts`` (the answer and the request) state a value for, spelt as :func:`_symbol_key` spells them.
    One pass over each text, bounded by ``_MAX_SCAN``."""
    out: set[str] = set()
    for t in texts:
        for m in _BINDING_RE.finditer(t or "", 0, min(len(t or ""), _MAX_SCAN)):
            out.add(_symbol_key(m.group(1) + (m.group(2) or "")))
    return frozenset(out)


def _is_bound(name: str, bound: frozenset[str]) -> bool:
    """A symbol the answer or the request states a value for; a run of two or three such one-letter symbols (``at``
    with a and t stated) is their product."""
    if _symbol_key(name) in bound:
        return True
    return 2 <= len(name) <= 3 and name.isascii() and name.isalpha() and all(c in bound for c in name)


def _classify(text: str, s: int, e: int, bound: frozenset[str] = frozenset()) -> list[list[_Tok]]:
    """The operands of ``text[s:e]`` (split at relation signs), each a list of classified tokens. A letter (with its
    subscript) is a ``word`` (a symbol, or prose) unless it is a function name, π, Euler's e under a power, a mark code, a
    ``\text`` group, a unit atom written after a figure or a unit (with a space; glued to a figure only when it has two
    letters or more: ``9t`` is 9·t, ``2kg`` is two kilograms), or a symbol in ``bound`` (``bound``: a value). Linear in
    ``e − s``."""
    operands: list[list[_Tok]] = [[]]
    cur = operands[0]
    after_value = False   # the last significant token was a figure, a unit, a constant, a stated symbol or a closing bracket
    unit_slash = False    # '/' or '·' right after a unit: a unit may follow ("m/s")
    i = s
    while i < e:
        m = _TOKEN_RE.match(text, i, e)
        if m is None:  # pragma: no cover - the pattern matches any character
            break
        kind, tok, j = m.lastgroup, m.group(0), m.end()
        if kind == "space":
            i = j
            continue
        if (kind == "other" and tok in _RELATION_CHARS) or (kind == "cmd" and tok[1:] in _LATEX_RELATIONS):
            cur = []
            operands.append(cur)
            after_value = unit_slash = False
            i = j
            continue
        if kind == "cmd":
            name = tok[1:]
            if name in _LATEX_TEXT_GROUPS and j < e and text[j] == "{":
                close = text.find("}", j, min(e, j + 200))
                j = close + 1 if close >= 0 else j
                cur.append(_Tok("unit" if (after_value or unit_slash) else "word", i, j, text[i:j]))
            elif name in _LATEX_GREEK:
                sub = _SUBSCRIPT_RE.match(text, j, e)
                j = sub.end() if sub is not None else j
                cls = "bound" if _is_bound(text[i:j], bound) else "word"
                cur.append(_Tok(cls, i, j, text[i:j]))
                after_value = cls == "bound"
            elif name == "pi":
                cur.append(_Tok("const", i, j, tok))
                after_value = True
            elif name in _FUNCTION_WORDS:
                cur.append(_Tok("func", i, j, tok))
                after_value = False
            else:  # \frac, \times, \left, \right, \cdot, \sqrt, \ldots: arithmetic and layout
                cur.append(_Tok("op", i, j, tok))
                after_value = name in ("ldots", "cdots", "dots")
            unit_slash = False
            i = j
            continue
        if kind == "word":
            code = _MARK_CODE_RE.match(text, i, e)
            if code is not None and code.end() > j:
                cur.append(_Tok("other", i, code.end(), text[i:code.end()]))  # a mark annotation: never a symbol
                i = code.end()
                continue
            sub = _SUBSCRIPT_RE.match(text, j, e)
            if sub is not None:  # a subscript is part of the symbol's name
                j = sub.end()
                tok = text[i:j]
            nxt = text[j:j + 2]
            glued = bool(cur) and cur[-1].cls == "figure" and cur[-1].end == i
            if tok in _FUNCTION_WORDS:
                cls = "func"
            elif tok in ("π", "pi") or (tok == "e" and (nxt[:1] in "^⁰¹²³⁴⁵⁶⁷⁸⁹⁻" or nxt == "**")):
                cls = "const"
            elif (after_value or unit_slash) and tok in _UNIT_ATOMS and not (glued and len(tok) == 1):
                cls = "unit"
            elif tok in ("x", "X") and after_value and not glued and re.match(r"[ \t]*[0-9]", text[j:j + 8]):
                cls = "op"  # '2 x 3': a times sign between figures
            elif _is_bound(tok, bound):
                cls = "bound"
            else:
                cls = "word"
            cur.append(_Tok(cls, i, j, tok))
            after_value = cls in ("unit", "const", "bound")
            unit_slash = False
            i = j
            continue
        if kind == "num":
            cur.append(_Tok("figure", i, j, tok))
            after_value, unit_slash = True, False
        elif kind == "sup":
            cur.append(_Tok("other", i, j, tok))  # an exponent or an index: part of what it follows
        elif kind == "open":
            cur.append(_Tok("open", i, j, tok))
            after_value = unit_slash = False
        elif kind == "close":
            cur.append(_Tok("close", i, j, tok))
            after_value, unit_slash = True, False
        elif kind == "op":
            unit_slash = tok in ("/", "·") and bool(cur) and cur[-1].cls == "unit"
            cur.append(_Tok("op", i, j, tok))
            after_value = False
        elif kind == "punct":
            cur.append(_Tok("punct", i, j, tok))
            after_value = unit_slash = False
        else:
            cur.append(_Tok("other", i, j, tok))  # %, °, …: part of what they follow
        i = j
    return operands


def _is_stop(t: _Tok) -> bool:
    """A word (a symbol with no stated value, or prose) or a clause mark: what no written calculation holds."""
    return t.cls == "word" or t.cls == "punct"


def _is_calculation(toks: list[_Tok]) -> bool:
    """A complete expression over values: a figure or a stated symbol, no word, balanced brackets, no binary operator at
    either end."""
    if not toks or not any(t.cls in ("figure", "bound") for t in toks) or any(_is_stop(t) for t in toks):
        return False
    depth = 0
    for t in toks:
        depth += 1 if t.cls == "open" else -1 if t.cls == "close" else 0
        if depth < 0:
            return False
    return depth == 0 and toks[0].text not in _BINARY_OPS and toks[-1].text not in _BINARY_OPS


def _words(toks: list[_Tok], *classes: str) -> list[str]:
    return list(dict.fromkeys(t.text for t in toks if t.cls in (classes or ("word",))))


def _shown(text: str, toks: list[_Tok]) -> str:
    if not toks:
        return ""
    stretch = " ".join(text[toks[0].start:toks[-1].end].split())
    return stretch if len(stretch) <= 90 else stretch[:87] + "…"


def _statement_operands(text: str, a: int, b: int, bound: frozenset[str] = frozenset()) -> list[list[_Tok]]:
    """The operands of the statement that holds ``[a, b)``: its line (a part label opening the line left out), cut at the
    sentences around the stretch and before a closing mark annotation."""
    s, e = _line_bounds(text, a)
    label = _PART_LABEL_RE.match(text, s) if s == 0 or text[s - 1] == "\n" else None
    if label is not None and label.end() <= a:
        s = label.end()
    before = [m.end() for m in _SENTENCE_END_RE.finditer(text, s, a)]
    if before:
        s = before[-1]
    after = _SENTENCE_END_RE.search(text, b, e)
    if after is not None:
        e = after.start()
    tail = _ANNOTATION_TAIL_RE.search(text, b, e)
    if tail is not None:
        e = tail.start()
    return _classify(text, s, e, bound)


def not_applicable(inj: StemInjection, question: str = "") -> str:
    """Why the changed figure lies in no written calculation, or '' when it does (module docstring, Applicability).

    The changed statement is read as operands between relation signs; inside an operand, words (symbols with no stated
    value, prose) and clause marks separate stretches, and a symbol the answer or ``question`` (the request) states a value
    for counts as a value. For ``stem_arithmetic_slip`` the changed figure is a stated result: the stretch of the operand
    before its relation sign that ends at the sign must be a calculation. For ``stem_substitution`` the stretch that holds
    the changed figure must be one. A reason is given only when the operand holds a symbol with no stated value: it is
    a candidate for NOT APPLICABLE, which run_arena.py grants only when the change moved none of the receipt's formal
    checks. ``stem_wrong_unit``, a figure the reading cannot place and anything else are applicable. Bounded by the
    statement (one line, one sentence)."""
    if inj.kind not in ("stem_arithmetic_slip", "stem_substitution"):
        return ""
    text = inj.text
    a, b = inj.site
    bound = bound_symbols(text, question)
    operands = _statement_operands(text, a, b, bound)
    k = next((i for i, op in enumerate(operands) if op and op[0].start <= a < op[-1].end), None)
    if k is None:
        return ""  # the harness cannot place the figure: never reported as not applicable

    def glued(op: list[_Tok], lo: int, hi: int) -> bool:
        """A word written against the stretch ``op[lo:hi]`` (``9t``, ``x3``): a factor of it, so it is no calculation."""
        return (hi < len(op) and hi > lo and op[hi].cls == "word" and op[hi].start == op[hi - 1].end) or \
               (0 < lo < hi and op[lo - 1].cls == "word" and op[lo - 1].end == op[lo].start)

    def trailing(op: list[_Tok]) -> list[_Tok]:
        stops = [i for i, t in enumerate(op) if _is_stop(t)]
        lo = stops[-1] + 1 if stops else 0
        return [] if glued(op, lo, len(op)) else op[lo:]

    def why(prefix: str, toks: list[_Tok], what: str) -> str:
        unstated = _words(toks)
        if not unstated:
            return ""  # every symbol has a stated value: a calculation the reading cannot delimit is still counted
        held = _words(toks, "word", "bound")
        return (f"{prefix} '{_shown(text, toks)}', which is no written calculation (it holds {', '.join(repr(w) for w in held)}; no value is "
                f"stated for {', '.join(repr(w) for w in unstated)}): the {what} lies in an expression in symbols")

    op = operands[k]
    if inj.kind == "stem_arithmetic_slip":
        if k == 0 or _is_calculation(trailing(operands[k - 1])):
            return ""  # a result with no relation sign before it is not placed: applicable
        return why("the changed result is stated for", operands[k - 1], "slip")
    at = next(i for i, t in enumerate(op) if t.start <= a < t.end or t.start >= a)
    lo = max((i for i in range(at) if _is_stop(op[i])), default=-1) + 1
    hi = min((i for i in range(at, len(op)) if _is_stop(op[i])), default=len(op))
    if not glued(op, lo, hi) and _is_calculation(op[lo:hi]):
        return ""
    return why("the changed figure lies in", op, "substitution")
