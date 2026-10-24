"""Symbol scope: names, bindings with provenance, recorded formulas (section 4.6).

* :func:`prescan_names` collects, before anything is parsed, the names a text declares: a
  letter run directly before ``=`` or ``≈`` at the start of a relation (``PV = 5000``,
  ``F_net = ma``, ``pV = nRT``), every subscripted, primed or Δ-prefixed symbol and every
  Greek letter. The parser segments implicit multiplication against these names, so ``PV``
  is one symbol once ``PV = 5000`` is stated, and ``mgh`` is ``m·g·h``.
* :class:`Scope` holds ``symbol -> bindings``. A binding records the value as written, its
  unit, its half-width, where it came from and the statement that states it. Sources:
  ``request`` (the router's request text, read by the same front end), ``given`` (a
  ``Given:`` or ``Data:`` statement), ``let`` (``let``, ``take``, ``taking``, ``using``,
  ``with``), ``result`` (the final value of the answer's own chain), ``statement`` (a bare
  value binding elsewhere in the answer), ``root`` (a stated solution of an equation in the
  symbol: ``x = 5 or x = −2`` is no rebinding) and ``substitution`` (a value substituted into a
  symbol that has no other binding; such a binding only ever widens what a later
  substitution may match and is never a premise of its own check).
* The front end never adds a constant's value to scope: a booklet value is a reading the
  checks stage may take, at warning severity (design D3).
* Rebinding adds a binding; when the value differs beyond rounding from every earlier one
  (``|w − b| ≤ h(w) + h(b)``, in SI when both units are known), an ST-SCOPE-001 info note is
  recorded. A substituted value matches ANY binding of its symbol, so part (b) reusing part
  (a)'s letter is never flagged. Only the last ``max_bindings_per_symbol`` bindings are kept
  for matching; dropping older ones is also noted (ST-SCOPE-001).
* Formulas: a left-hand symbol (or ``f(x)``) maps to the expressions stated for it by
  definition and law links (``F = ma``, ``a = Δv/Δt``), most recent last.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterator, Optional

from .limits import DEFAULT_LIMITS, StemLimits
from .nodes import Node
from .numbers import ExactNumber
from .parser import STEM_NAMES, symbol_name
from .units import UnitExpr

__all__ = ["Binding", "Formula", "Scope", "ScopeNote", "prescan_names", "si_value"]

_LONG_NAME = 4
_STOP = frozenset({"is", "so", "of", "to", "be", "in", "by", "or", "if", "an", "it", "on", "we", "do", "no", "up", "as", "at", "the", "and", "for",
                   "then", "than", "that", "this", "with", "from", "into", "when", "let", "use", "per", "all"})


def si_value(value: Fraction, unit: Optional[UnitExpr], wrapper: str = "") -> Optional[Fraction]:
    """The SI value of a written value when its unit has one exact reading (affine units
    excluded: they are compared only by explicit conversion checks). A per cent is /100."""
    if unit is None:
        return value / 100 if wrapper == "%" else None
    if len(unit.readings) != 1:
        return None
    r = unit.readings[0]
    if r.factor is None or r.affine is not None:
        return None
    return value * r.factor


@dataclass(frozen=True)
class Binding:
    symbol: str
    value: Fraction
    number: ExactNumber
    unit: Optional[UnitExpr]
    source: str
    statement_id: str
    start: int = 0
    end: int = 0
    order: int = 0
    wrapper: str = ""

    @property
    def half_width(self) -> Fraction:
        return self.number.half_width

    @property
    def si(self) -> Optional[Fraction]:
        return si_value(self.value, self.unit, self.wrapper)

    def same_as(self, other: "Binding") -> bool:
        """Equal within rounding: in SI when both have exact unit readings, else as written."""
        tol = self.half_width + other.half_width
        a, b = self.si, other.si
        if a is not None and b is not None and self.unit is not None and other.unit is not None:
            fa = self.unit.readings[0].factor if self.unit.readings else None
            fb = other.unit.readings[0].factor if other.unit.readings else None
            tol_si = self.half_width * (fa or 1) + other.half_width * (fb or 1)
            return abs(a - b) <= tol_si
        return abs(self.value - other.value) <= tol


@dataclass(frozen=True)
class Formula:
    name: str
    expr: Node
    statement_id: str
    source: str  # 'law', 'definition', 'request'
    params: tuple[str, ...] = ()
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class ScopeNote:
    code: str
    message: str
    symbol: str
    statement_ids: tuple[str, ...]


@dataclass
class Scope:
    """Mutable while the document is built; frozen views are exported on the document."""

    limits: StemLimits = DEFAULT_LIMITS
    bindings: dict[str, list[Binding]] = field(default_factory=dict)
    substitutions: dict[str, list[Binding]] = field(default_factory=dict)
    #: rule changed-value (STEM repair 4): the value the prose gives a symbol's quantity at the end of a change it states ('the current
    #: from the cell falls, from 4.1 A to 2.7 A'), source ``change``: a substitution stated after it, in its statement or in its part may
    #: take it, as it takes a binding;
    #: never a premise of its own check, never a binding of the scope (no rebinding note, no carried value)
    changes: dict[str, list[Binding]] = field(default_factory=dict)
    formulas: dict[str, list[Formula]] = field(default_factory=dict)
    notes: list[ScopeNote] = field(default_factory=list)
    names: set[str] = field(default_factory=set)
    _order: int = 0

    def add(self, b: Binding) -> Optional[ScopeNote]:
        """Add a binding; returns the ST-SCOPE-001 note when the value differs from every earlier binding."""
        self._order += 1
        b = Binding(b.symbol, b.value, b.number, b.unit, b.source, b.statement_id, b.start, b.end, self._order, b.wrapper)
        self.names.add(b.symbol)
        if b.source == "substitution":
            self.substitutions.setdefault(b.symbol, []).append(b)
            return None
        prior = self.bindings.setdefault(b.symbol, [])
        note: Optional[ScopeNote] = None
        if b.source == "root":
            pass  # the solutions of an equation (x = 5 or x = −2) are not a rebinding
        elif prior and b.source != "result" and not any(p.same_as(b) for p in prior):
            first = prior[-1]
            note = ScopeNote("ST-SCOPE-001", f"'{b.symbol}' is rebound to {b.number.text}{' ' + b.unit.text if b.unit else ''} in {b.statement_id} "
                                             f"(earlier {first.number.text}{' ' + first.unit.text if first.unit else ''} in {first.statement_id}); "
                                             f"a substituted value matches any binding of the symbol", b.symbol,
                             tuple(dict.fromkeys((first.statement_id, b.statement_id))))
            self.notes.append(note)
        elif prior and b.source == "result" and not any(p.same_as(b) for p in prior) and all(p.statement_id != b.statement_id for p in prior):
            first = prior[-1]
            note = ScopeNote("ST-SCOPE-001", f"'{b.symbol}' takes the value {b.number.text}{' ' + b.unit.text if b.unit else ''} in {b.statement_id} "
                                             f"(earlier {first.number.text}{' ' + first.unit.text if first.unit else ''} in {first.statement_id}); "
                                             f"a substituted value matches any binding of the symbol", b.symbol,
                             tuple(dict.fromkeys((first.statement_id, b.statement_id))))
            self.notes.append(note)
        prior.append(b)
        if len(prior) > self.limits.max_bindings_per_symbol:
            dropped = prior.pop(0)
            self.notes.append(ScopeNote("ST-SCOPE-001", f"'{b.symbol}' has more than {self.limits.max_bindings_per_symbol} bindings; the oldest "
                                                        f"({dropped.number.text} in {dropped.statement_id}) is no longer matched", b.symbol,
                                        (dropped.statement_id,)))
        return note

    def add_change(self, b: Binding) -> None:
        """Rule ``changed-value`` (STEM repair 4): record the value the prose gives ``b.symbol`` after a change it states."""
        self._order += 1
        lst = self.changes.setdefault(b.symbol, [])
        if any(x.statement_id == b.statement_id and x.start == b.start for x in lst):
            return
        lst.append(Binding(b.symbol, b.value, b.number, b.unit, "change", b.statement_id, b.start, b.end, self._order, b.wrapper))
        if len(lst) > self.limits.max_bindings_per_symbol:
            lst.pop(0)

    def add_formula(self, f: Formula) -> None:
        self.names.add(f.name)
        lst = self.formulas.setdefault(f.name, [])
        lst.append(f)
        if len(lst) > self.limits.max_bindings_per_symbol:
            lst.pop(0)

    def bindings_for(self, name: str) -> tuple[Binding, ...]:
        return tuple(self.bindings.get(name, ()))

    def is_bound(self, name: str) -> bool:
        return bool(self.bindings.get(name))

    def is_given(self, name: str) -> bool:
        """Bound by something other than a stated root: a solved-for unknown stays an unknown for the relations that follow."""
        return any(b.source != "root" for b in self.bindings.get(name, ()))

    def has_reading(self, name: str) -> bool:
        """Bound, or given a value by a substitution the answer wrote (``m g = 5.0 × 9.81`` reads m as 5.0)."""
        return bool(self.bindings.get(name)) or bool(self.substitutions.get(name))

    def formula_for(self, name: str) -> Optional[Formula]:
        lst = self.formulas.get(name)
        return lst[-1] if lst else None


_GREEK_LETTERS = frozenset("αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩµϕϵϑ")
_SUBSCRIPT_CHARS = frozenset("₀₁₂₃₄₅₆₇₈₉ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼᵣ∥⊥½")
_BLOCKING = frozenset("+-−×·*/÷^=<>≤≥≈≠~0123456789)]}⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻|√")


#: subscript characters as they appear in a symbol name
_PRESCAN_SUB = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9", "ₐ": "a", "ₑ": "e", "ₒ": "o",
                "ₓ": "x", "ₕ": "h", "ₖ": "k", "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₚ": "p", "ₛ": "s", "ₜ": "t", "ᵢ": "i", "ⱼ": "j", "ᵣ": "r",
                "∥": "par", "⊥": "perp", "½": "half"}


def prescan_names(text: str, *, limits: StemLimits = DEFAULT_LIMITS, cs: bool = False) -> frozenset[str]:
    """Names declared in ``text`` (a reading view): a letter run directly before ``=`` or ``≈`` at
    the start of a relation (after the start of a line, punctuation, a bracket, ``⇒``/``∴`` or a
    prose word; never after an operator, a number or another relation sign), with its subscript,
    primes and Δ prefix. A character-level pass with bounded look-back at each ``=``/``≈``: no
    lexing of the whole text, so the pass is linear with a small constant."""
    names: set[str] = set()
    for k in _relation_positions(text):
        name = _name_before(text, k)
        if name:
            names.add(name)
    return frozenset(names)


def _relation_positions(text: str) -> Iterator[int]:
    """Offsets of ``=`` and ``≈`` that may open a relation, in order (``==``, ``=>``, ``<=``, ``>=``
    and ``!=`` are skipped). Iterative, and each search starts where the last one ended: linear."""
    n = len(text)
    eq = text.find("=")
    ap = text.find("≈")
    while eq >= 0 or ap >= 0:
        if ap < 0 or 0 <= eq < ap:
            k = eq
            if k + 1 < n and text[k + 1] in "=>":
                eq = text.find("=", k + 2)
                continue
            eq = text.find("=", k + 1)
            if k > 0 and text[k - 1] in "<>!=":
                continue
            yield k
        else:
            k = ap
            ap = text.find("≈", k + 1)
            yield k


def _name_before(text: str, k: int) -> str:
    """The symbol name right before the relation sign at ``k`` when it opens the relation, else ''."""
    j = k - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    end = j + 1
    # primes and a standard-state mark
    primes = 0
    while j >= 0 and text[j] in "′'″":
        primes += 2 if text[j] == "″" else 1
        j -= 1
    sub = ""
    if j >= 0 and text[j] == "°":
        sub = "°"  # a standard-state mark: ΔH°
        j -= 1
    # Unicode subscripts
    m = j
    while m >= 0 and text[m] in _SUBSCRIPT_CHARS and j - m < 16:
        m -= 1
    if m < j:
        sub = text[m + 1:j + 1] + sub
        j = m
    elif j >= 0 and text[j] == "}":
        o = text.rfind("_{", max(0, j - 24), j)
        if o >= 0:
            sub = text[o + 2:j]
            j = o - 1
    else:
        # ASCII subscript: letters_alnum
        m = j
        while m >= 0 and (text[m].isascii() and text[m].isalnum()) and j - m < 16:
            m -= 1
        if m >= 0 and m < j and text[m] == "_":
            sub = text[m + 1:j + 1]
            j = m - 1
    if j < 0:
        return ""
    if text[j] in _GREEK_LETTERS and text[j] != "Δ":
        letters = text[j]
        j -= 1
    else:
        m = j
        while m >= 0 and ("a" <= text[m] <= "z" or "A" <= text[m] <= "Z") and j - m < 64:
            m -= 1
        letters = text[m + 1:j + 1]
        j = m
    if not letters:
        return ""
    delta = j >= 0 and text[j] == "Δ"
    if delta:
        j -= 1
    if j >= 0 and ("a" <= text[j] <= "z" or "A" <= text[j] <= "Z" or text[j].isdigit()):
        return ""  # the run is part of a longer word or follows a digit
    # what opens the relation: skip spaces and look at the previous character or word
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j >= 0:
        ch = text[j]
        if ch in _BLOCKING:
            return ""
        if "a" <= ch <= "z" or "A" <= ch <= "Z":
            m = j
            while m >= 0 and ("a" <= text[m] <= "z" or "A" <= text[m] <= "Z") and j - m < 32:
                m -= 1
            word = text[m + 1:j + 1]
            if len(word) <= 2 and word.lower() not in _STOP:
                return ""
    if not delta and not sub and letters.isascii() and (letters.lower() in _STOP or (len(letters) > _LONG_NAME and letters not in STEM_NAMES)):
        return ""
    clean_sub = "".join(_PRESCAN_SUB.get(c, c) for c in sub if c.isalnum() or c in "∥⊥½°") if sub else ""
    return symbol_name(letters if letters != "µ" else "μ", clean_sub, primes, delta)
