"""Stated precision and exactness of the figures an encoding compares (translation side).

A figure's precision is part of what its source states, and only the source's WORDING decides it
(:func:`.quantities.stated_exactness`): the solver never does. Every figure the encoding compares by
equality, or reads as an interval, is tied to the span of the source that states it (the claim, a
supporting claim, a supplied text or the task record, in that order) and read as:

* ``exact``: an exactness cue governs it ("x is exactly 0.33, without rounding"); it is encoded with
  ``eq`` and never widened. An interval in its place weakens the claim: the encoding is rejected
  (``exactness``) and fed back once, so its counterexample, if any, stays the verdict;
* ``given``: a figure of a supplied text or the task with no cue, read exactly as given (a task fact is
  never widened);
* ``rounded``: a rounding cue ("to 2 decimal places", "3 s.f.", "≈", "about": an approximation word or sign
  only for the figure it is written against), or a figure written as the result of a calculation that,
  computed as written, the figure rounds (``−12.50 ÷ 18.75 = −0.67``; the calculation must END at the
  figure's '=': in "If x = 1/3 then x = 0.33" the sign equates 0.33 with the variable x, so no calculation
  states it and it is ``unstated``); it states the values within its tolerance. An exact equality in its place is rejected (``stated precision``)
  when reading it at its stated tolerance changes the verdict, and the retry must give exactly that
  interval: a wider or narrower one is rejected. A written calculation that gives exactly its result
  (``$2.00 − $0.40 = $1.60``) makes the figure ``exact``. One the reader cannot compute is rounded only by the
  convention of written calculation, a presumption: it may explain a failure (an exact equality is rejected
  when the exact reading fails and the stated reading gives another verdict), but a proof that needs the
  result exactly is flagged AMBIGUOUS_TRANSLATION instead of rejected, since the result may be exact;
* ``unstated``: the claim writes a decimal with no cue. Read as written and read to half a unit of its
  last place are both reasonable; when the two readings give different verdicts the translation is
  AMBIGUOUS_TRANSLATION with both readings recorded, never a verdict either way;
* ``conflicting`` (cues of both kinds) is treated as unstated; ``unsourced`` (no source states the figure)
  is read as written.

Three readings refine the interval rule (:func:`decide_precision`); none relaxes it for an interval that is genuinely
wider or narrower than a figure it reads:

* an open precision: a whole number written with trailing zeros and a bare approximation word or sign, with no stated
  precision ("about 100%"), reads at half a unit of its last written digit or, its trailing zeros not significant, of
  its first significant digit. An encoding at either is accepted; when the two readings give different verdicts the
  translation is AMBIGUOUS_TRANSLATION, so neither the wide nor the narrow reading is forced;
* an enclosure (B22): an interval no source states, inside the one stated figure of the claim or a supporting claim
  whose stated interval contains it ([2,294,000, 2,298,000) for "2.3 × 10⁶"), is rejected when the probe at the stated
  interval changes the verdict;
* a closure variant (B16): an interval equal to the stated one except for the closure of an end is accepted when the
  probe at the stated closure gives the same verdict, and rejected otherwise.

:func:`reference_reading` reads each such interval at its stated bounds, so a retry that encodes exactly what a
stated-precision rejection asked for keeps the claim; a rejection names the figure as written, never an interval's
midpoint.

A precision reading may be proposed (in a retry diagnostic) only when the wording supports it, and it is
never chosen because it makes the claim easier to prove. :func:`compare_conclusions` classifies a retry's
conclusion against the earlier one read as its source states it, so a retry that weakens the claim cannot
inherit its approval. Nothing here evaluates model output: problems are rewritten as JSON data and
validated against the IR schema before the engine sees them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Any, Literal, Optional, Sequence

from pydantic import ValidationError

from ..engine.results import SolverConfig
from ..engine.runner import verify as engine_verify
from ..engine.statuses import DEFINITIVE, VerificationStatus
from ..ir.schema import Assertion, Problem, Symbol
from .contracts import AmbiguityFlag, FigureReading
from .quantities import (DeclaredReading, Exactness, Match, SourceText, StatedFigure, declared_reading, figures_in, fraction_text, literal_matches,
                         stated_exactness, tolerance_bounds)

__all__ = ["Site", "Reading", "PrecisionDecision", "collect_sites", "read_sites", "decide_precision", "reference_reading", "compare_conclusions",
           "decimal_text", "rewrite", "added_premise_support"]

#: The status that passes the check, per query kind.
_PASSING_STATUS = {"entailment": VerificationStatus.ENTAILED, "consistency": VerificationStatus.CONSISTENT, "satisfiability": VerificationStatus.SATISFIABLE}
_BOUND_OPS = frozenset({"ge", "gt", "le", "lt"})
_LITERAL_OPS = frozenset({"real", "int"})


def _reading_interval(lo: Fraction, hi: Fraction) -> bool:
    """An interval that can be the reading of one rounded figure: a domain or range constraint with a bound of 0, 1, 10,
    100 or 1000 (0 <= p <= 1, 0 <= pct <= 100) is none."""
    from .quantities import TRIVIAL_VALUES
    return lo < hi and abs(lo) not in TRIVIAL_VALUES and abs(hi) not in TRIVIAL_VALUES


def decimal_text(value: Fraction) -> str:
    """``value`` as an IR real literal: a terminating decimal when it has one, else ``a/b``."""
    if value.denominator == 1:
        return str(value.numerator)
    d = value.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:
        text = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
        return text if "." in text else text + ".0"
    return f"{value.numerator}/{value.denominator}"


def _canonical(node: Any) -> str:
    return json.dumps(node, sort_keys=True, separators=(",", ":"))


@dataclass
class Site:
    """A place where the encoding states a figure: an equality with a real literal (``eq``), or two bounds on one term
    inside a conjunction (``interval``; ``value`` is its midpoint)."""
    path: tuple
    assertion_id: str
    in_conclusion: bool
    kind: Literal["eq", "interval"]
    term: dict
    value: Fraction
    literal: str
    symbol: Optional[str] = None
    lo: Optional[Fraction] = None
    hi: Optional[Fraction] = None
    lo_incl: bool = True
    hi_incl: bool = False
    arg_indices: tuple = ()
    split: bool = False  # the two bounds are two top-level premises (``arg_indices`` are premise indices)
    #: the term the bounds multiply when the interval is written cross-multiplied (``term >= lo * scale and term < hi *
    #: scale``, a ratio ``term / scale`` kept linear): the site reads the ratio, and a rewrite keeps the written form
    scale: Optional[dict] = None


@dataclass
class Reading:
    """How the source states a site's figure.

    ``bounds`` is the interval a rounded figure states; ``alt_bounds`` the second interval the same wording also states
    when its precision is open: a whole number written with trailing zeros and an approximation word with no stated
    precision ("about 100%") reads at half a unit of its last written digit ([99.5, 100.5)) or, its trailing zeros not
    significant, at half a unit of its first significant digit ([50, 150)); neither reading is forced. ``enclosed`` marks
    an interval tied to the one figure of the claim (or a supporting claim) whose stated interval contains it, though the
    figure itself lies outside it (B22: [2,294,000, 2,298,000) for "2.3 × 10⁶")."""
    site: Site
    exactness: Literal["exact", "rounded", "unstated", "given", "conflicting", "unsourced"]
    figure: Optional[StatedFigure] = None
    match: Optional[Match] = None
    stated: Optional[Exactness] = None
    bounds: Optional[tuple[Fraction, Fraction, bool, bool]] = None
    written_bounds: Optional[tuple[Fraction, Fraction, bool, bool]] = None
    source: Optional[SourceText] = None
    alt_bounds: Optional[tuple[Fraction, Fraction, bool, bool]] = None
    enclosed: bool = False
    #: the approximation word denies the last written digit's precision (``alt_bounds``) for this figure: its significant
    #: digits are not a lone 1 (:func:`read_sites`). An encoding at ``bounds`` then stands on its own; one at ``alt_bounds``
    #: is still probed at ``bounds``
    alt_denied: bool = False

    @property
    def stated_bounds(self) -> Optional[tuple[Fraction, Fraction, bool, bool]]:
        """The interval the wording states: a rounded figure's tolerance, else (for an enclosed tie) the half-unit
        enclosure of the figure at its written precision."""
        return self.bounds if self.bounds is not None else (self.written_bounds if self.enclosed else None)

    def written(self) -> str:
        """The figure as the source writes it (never an interval's midpoint)."""
        return self.figure.written if self.figure is not None else decimal_text(self.site.value)

    def where(self) -> str:
        return self.figure.where() if self.figure is not None else "no source text states it"

    def describe(self) -> str:
        if self.exactness == "given":
            return f"{self.where()}, a figure given by the {self.figure.source_kind.replace('_', ' ') if self.figure else 'source'} with no rounding cue"
        if self.stated is not None:
            return f"{self.where()}, {self.stated.describe()}"
        return self.where()


@dataclass
class PrecisionDecision:
    """What the pipeline does with the encoding's figures: reject it (``reject``: reason tag and diagnostic, fed back
    once), flag an ambiguity between two readings the wording allows, or accept it; ``readings`` are recorded either way."""
    reject: Optional[tuple[str, str]] = None
    ambiguity: Optional[AmbiguityFlag] = None
    notes: list[str] = field(default_factory=list)
    readings: list[FigureReading] = field(default_factory=list)


# ------------------------------------------------------------------ sites


def _scaled(node: Any) -> Optional[tuple[dict, dict]]:
    """``(literal, scale)`` for a product of one literal and other factors that are no literal (``5 * p20``,
    ``250 * to_real(e0)``): the literal is the figure, the rest the term it multiplies."""
    if not isinstance(node, dict) or node.get("op") != "mul" or not isinstance(node.get("args"), list) or len(node["args"]) < 2:
        return None
    lits = [a for a in node["args"] if isinstance(a, dict) and a.get("op") in _LITERAL_OPS]
    rest = [a for a in node["args"] if not (isinstance(a, dict) and a.get("op") in _LITERAL_OPS)]
    if len(lits) != 1 or not rest:
        return None
    return lits[0], (rest[0] if len(rest) == 1 else {"op": "mul", "args": rest})


def _bound(arg: Any) -> Optional[tuple[str, str, Fraction, bool, dict, str, Optional[dict]]]:
    """``(term key, 'lower'|'upper', value, inclusive, term, literal, scale)`` for a comparison of a term with a literal,
    or with a literal times another term, the cross-multiplied form of a ratio (``p22 >= 5 * p20``: the ratio ``p22 /
    p20`` bounded below by 5, ``scale`` the divisor; repair round 5, rerun-fidelity-2 variant: an interval written that
    way was never compared with the figure's stated precision)."""
    if not isinstance(arg, dict) or arg.get("op") not in _BOUND_OPS:
        return None
    left, right, op = arg.get("left"), arg.get("right"), arg["op"]
    scale: Optional[dict] = None
    if isinstance(right, dict) and right.get("op") in _LITERAL_OPS and not (isinstance(left, dict) and left.get("op") in _LITERAL_OPS):
        term, lit, flipped = left, right, False
    elif isinstance(left, dict) and left.get("op") in _LITERAL_OPS and not (isinstance(right, dict) and right.get("op") in _LITERAL_OPS):
        term, lit, flipped = right, left, True
    elif _scaled(right) is not None and isinstance(left, dict) and left.get("op") not in _LITERAL_OPS:
        (lit, scale), term, flipped = _scaled(right), left, False
    elif _scaled(left) is not None and isinstance(right, dict) and right.get("op") not in _LITERAL_OPS:
        (lit, scale), term, flipped = _scaled(left), right, True
    else:
        return None
    try:
        value = Fraction(lit["value"])
    except (KeyError, ValueError, ZeroDivisionError):
        return None
    lower = op in ("ge", "gt")
    if flipped:
        lower = not lower
    inclusive = op in ("ge", "le")
    key = _canonical(term) if scale is None else _canonical(term) + "/" + _canonical(scale)
    return key, ("lower" if lower else "upper"), value, inclusive, term, lit["value"], scale


def _walk(node: Any, path: tuple, aid: str, in_concl: bool, out: list[Site]) -> None:
    if isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, path + (i,), aid, in_concl, out)
        return
    if not isinstance(node, dict):
        return
    op = node.get("op")
    if op == "eq":
        for lit_side, term_side in (("right", "left"), ("left", "right")):
            lit, term = node.get(lit_side), node.get(term_side)
            if isinstance(lit, dict) and lit.get("op") == "real" and isinstance(term, dict) and term.get("op") not in _LITERAL_OPS:
                try:
                    value = Fraction(lit["value"])
                except (KeyError, ValueError, ZeroDivisionError):
                    break
                out.append(Site(path, aid, in_concl, "eq", term, value, lit["value"], term.get("name") if term.get("op") == "var" else None))
                break
    if op == "and" and isinstance(node.get("args"), list):
        groups: dict[str, dict[str, list[tuple[int, Fraction, bool, dict, str, Optional[dict]]]]] = {}
        for i, arg in enumerate(node["args"]):
            b = _bound(arg)
            if b is not None:
                key, side, value, incl, term, lit, scale = b
                groups.setdefault(key, {"lower": [], "upper": []})[side].append((i, value, incl, term, lit, scale))
        for key, g in groups.items():
            if len(g["lower"]) == 1 and len(g["upper"]) == 1:
                (li, lo, lo_incl, term, _l, scale), (hi_i, hi, hi_incl, _t, _h, _s) = g["lower"][0], g["upper"][0]
                if _reading_interval(lo, hi):
                    mid = (lo + hi) / 2
                    out.append(Site(path, aid, in_concl, "interval", term, mid, decimal_text(mid),
                                    term.get("name") if term.get("op") == "var" and scale is None else None,
                                    lo, hi, lo_incl, hi_incl, (li, hi_i), scale=scale))
    for k, v in node.items():
        if isinstance(v, (dict, list)):
            _walk(v, path + (k,), aid, in_concl, out)


def collect_sites(problem: Problem) -> list[Site]:
    """Every equality with a real literal and every two-sided interval on one term, in the premises and the conclusion;
    an interval may also be split over two premises, each one bound (the premises are a conjunction)."""
    data = problem.model_dump(mode="json", exclude_none=True)
    out: list[Site] = []
    premises = data.get("premises", [])
    for i, pr in enumerate(premises):
        _walk(pr.get("expr"), ("premises", i, "expr"), pr.get("id", "?"), False, out)
    groups: dict[str, dict[str, list[tuple[int, Fraction, bool, dict, Optional[dict]]]]] = {}
    for i, pr in enumerate(premises):
        b = _bound(pr.get("expr"))
        if b is not None:
            key, side, value, incl, term, _lit, scale = b
            groups.setdefault(key, {"lower": [], "upper": []})[side].append((i, value, incl, term, scale))
    for key, g in groups.items():
        if len(g["lower"]) == 1 and len(g["upper"]) == 1:
            (li, lo, lo_incl, term, scale), (hi_i, hi, hi_incl, _t, _s) = g["lower"][0], g["upper"][0]
            if _reading_interval(lo, hi):
                mid = (lo + hi) / 2
                aid = f"{premises[li].get('id', '?')}+{premises[hi_i].get('id', '?')}"
                out.append(Site(("premises",), aid, False, "interval", term, mid, decimal_text(mid),
                                term.get("name") if term.get("op") == "var" and scale is None else None,
                                lo, hi, lo_incl, hi_incl, (li, hi_i), split=True, scale=scale))
    if data.get("conclusion") is not None:
        _walk(data["conclusion"].get("expr"), ("conclusion", "expr"), data["conclusion"].get("id", "?"), True, out)
    return out


# ------------------------------------------------------------------ readings


def _combine(src: SourceText, matches: list[Match]) -> tuple[str, Match, Optional[Exactness]]:
    """One reading from the occurrences of a figure in one source: exact and rounded statements together are
    conflicting; a statement (a cue, or a written calculation computed as written) outranks the presumption of the
    calculation convention, so an exact statement and a presumed rounding read exact; no cue is unstated (the claim, a
    supporting claim) or given (a supplied text, the task)."""
    pairs = [(m, stated_exactness(m.figure, src.text)) for m in matches]
    exacts = [p for p in pairs if p[1].kind == "exact"]
    rounds = [p for p in pairs if p[1].kind == "rounded"]
    if exacts and any(not p[1].by_convention for p in rounds):
        return "conflicting", exacts[0][0], exacts[0][1]
    if exacts:
        return "exact", exacts[0][0], exacts[0][1]
    if rounds:
        explicit = [p for p in rounds if not p[1].by_convention]
        m, ex = (explicit or rounds)[0]
        return "rounded", m, ex
    m, ex = pairs[0]
    return ("unstated" if src.kind in ("claim", "supporting_claim") else "given"), m, ex


def _is_stated_range(site: Site, sources: Sequence[SourceText], declared: DeclaredReading) -> bool:
    """An interval whose two bounds are both figures the claim or a supporting claim states ('between 10 and 20'): a
    range the source states, not a reading of one rounded figure."""
    if site.kind != "interval" or site.lo is None or site.hi is None:
        return False
    for src in sources:
        if src.kind not in ("claim", "supporting_claim"):
            continue
        figs = figures_in(src)
        if literal_matches(site.lo, figs, declared)[0] and literal_matches(site.hi, figs, declared)[0]:
            return True
    return False


def _reading_of(site: Site, value: Fraction, sources: Sequence[SourceText], declared: DeclaredReading) -> Optional[Reading]:
    """How the sources state ``value`` (the site's figure), by priority: an explicit exactness or rounding cue of the
    claim or a supporting claim (the claim's own wording of its precision); else the figure as the task or a supplied
    text gives it (``given``, or that text's own cue), since a claim that repeats a given value does not make it
    approximate; else the claim's calculation convention; else ``unstated``. None when no source states it."""
    found: list[tuple[SourceText, str, Match, Optional[Exactness]]] = []
    for src in sources:
        matches, _why = literal_matches(value, figures_in(src), declared)
        if matches:
            kind, m, ex = _combine(src, matches)
            found.append((src, kind, m, ex))
    if not found:
        return None
    claim_side = [f for f in found if f[0].kind in ("claim", "supporting_claim")]
    given_side = [f for f in found if f[0].kind in ("supplied_text", "task")]
    explicit = [f for f in claim_side if f[1] in ("exact", "conflicting") or (f[1] == "rounded" and f[3] is not None and not f[3].by_convention)]
    choice = (explicit or given_side or claim_side)[0]
    src, kind, m, ex = choice
    reading = Reading(site, kind, m.figure, m, ex, source=src)  # type: ignore[arg-type]
    if kind == "rounded" and ex is not None:
        reading.bounds = tolerance_bounds(value, ex, m.factor)
        if reading.bounds is not None and _open_trailing_zeros(m.figure, ex):
            half = Fraction(1, 2) * m.factor
            reading.alt_bounds = (value - half, value + half, True, False)
    if m.figure.has_point and m.figure.half_width:
        h = m.figure.half_width * m.factor
        reading.written_bounds = (value - h, value + h, True, False)
    return reading


#: Words of a rounding cue that state a precision ("to the nearest ten", "2 s.f."): a cue with none of them, and no
#: digit, is a bare approximation word or sign ("about", "≈", "roughly").
_PRECISION_WORDS = frozenset({"nearest", "significant", "sig", "decimal", "place", "places", "dp", "sf", "d", "p", "s", "f", "figure", "figures", "whole",
                              "integer", "unit", "units", "ten", "tens", "hundred", "hundreds", "thousand", "thousands", "million", "millions", "down", "up"})


def _open_trailing_zeros(figure: StatedFigure, exactness: Exactness) -> bool:
    """Whether a rounded figure's precision is open between its last written digit and its first significant digit: a
    whole number written with trailing zeros and no point ("100", "1,000", "30%"), stated with a bare approximation word
    or sign and no stated precision, read at the trailing-zero tolerance (wider than half a unit of the last digit)."""
    if exactness.mode != "nearest" or not exactness.half_width or figure.has_point or figure.word:
        return False
    digits = figure.numeral.replace(",", "").replace(" ", "").replace(" ", "").replace(" ", "").lstrip("+-−")
    if not digits.isdecimal() or not digits.endswith("0") or exactness.half_width <= Fraction(1, 2):
        return False
    cue = (exactness.cue or "").casefold()
    if any(ch.isdigit() for ch in cue):
        return False
    words = set(cue.replace(".", " ").replace("-", " ").split())
    return not (words & _PRECISION_WORDS)


def _enclosing_figure(site: Site, sources: Sequence[SourceText], declared: DeclaredReading) -> Optional[Reading]:
    """For an interval no source states and no stated figure lies inside: the one figure of the claim or a supporting claim
    whose stated interval (its tolerance when rounded, else its half-unit enclosure at its written precision) strictly
    contains the interval, in the unit the symbol declares (B22). None when no figure, or more than one, encloses it."""
    if site.lo is None or site.hi is None or not _reading_interval(site.lo, site.hi):
        return None
    found: dict[tuple, Reading] = {}
    negative = site.hi <= 0
    for src in sources:
        if src.kind not in ("claim", "supporting_claim"):
            continue
        for f in figures_in(src):
            for value in {f.value, f.scaled, f.scaled * (f.unit_factor or 1) if f.is_percent_like else f.value}:
                if value == 0:
                    continue
                value = -abs(value) if negative else abs(value)
                reading = _reading_of(site, value, sources, declared)
                if reading is None or reading.figure is None:
                    continue
                stated = reading.bounds if reading.exactness == "rounded" else reading.written_bounds
                if stated is None:
                    continue
                lo, hi, _li, _hi = stated
                if lo <= site.lo and site.hi <= hi and (site.hi - site.lo) < (hi - lo):
                    found.setdefault((reading.figure.source_kind, reading.figure.source_id, reading.figure.start), reading)
    if len(found) != 1:
        return None
    reading = next(iter(found.values()))
    reading.enclosed = True
    return reading


def _contained_figure(site: Site, sources: Sequence[SourceText], declared: DeclaredReading) -> Optional[Reading]:
    """For an interval whose midpoint no source states: the stated figure it reads, when one lies inside it, its bounds
    are no trivial domain bounds (0, 1, 10, 100, 1000) and it is narrower than the figure's own magnitude. The interval
    [0.3, 0.4) read for "0.33 to 2 decimal places" is a (wrong) reading of 0.33; a domain constraint 0 <= p <= 1 is none."""
    if site.lo is None or site.hi is None or not _reading_interval(site.lo, site.hi):
        return None
    for src in sources:  # the first source (the claim before its supporting claims, before the task material) that has one
        best: Optional[tuple[tuple, Reading]] = None
        for f in figures_in(src):
            for value in {f.value, f.scaled, f.scaled * (f.unit_factor or 1) if f.is_percent_like else f.value}:
                if site.lo <= value <= site.hi and value != 0 and (site.hi - site.lo) < abs(value):
                    reading = _reading_of(site, value, sources, declared)
                    if reading is not None:
                        # an interval reads a rounded figure before an exact one, a decimal before a fraction, the nearest first
                        rank = (reading.exactness != "rounded", not f.has_point, abs(value - site.value))
                        if best is None or rank < best[0]:
                            best = (rank, reading)
        if best is not None:
            return best[1]
    return None


#: Operations whose result is a whole number when their operands are (a count: :func:`_takes_whole_values`).
_WHOLE_OPS = frozenset({"add", "sub", "mul", "neg", "idiv", "mod"})
_MAX_TERM_NODES = 256


def _takes_whole_values(term: Any, symbols: dict[str, Symbol]) -> bool:
    """Whether a site's term takes only whole values: a symbol of sort Int, an integer literal, or a sum, difference,
    product, negation, integer quotient or remainder of such terms, perhaps cast to a real (``to_real``): a count. A
    bounded walk over the validated term; nothing is evaluated."""
    stack = [term]
    seen = 0
    while stack:
        seen += 1
        if seen > _MAX_TERM_NODES:
            return False
        node = stack.pop()
        if not isinstance(node, dict):
            return False
        op = node.get("op")
        if op == "var":
            sym = symbols.get(node.get("name"))
            if sym is None or sym.sort != "Int":
                return False
        elif op == "int":
            continue
        elif op == "to_real":
            stack.append(node.get("arg"))
        elif op in _WHOLE_OPS:
            if isinstance(node.get("args"), list):
                stack.extend(node["args"])
            else:
                stack.extend(node.get(k) for k in ("left", "right", "arg") if node.get(k) is not None)
        else:
            return False
    return True


def read_sites(problem: Problem, sources: Sequence[SourceText], sites: Optional[list[Site]] = None) -> list[Reading]:
    """The reading of every site's figure (see :func:`_reading_of`); ``unsourced`` when no source states it.

    The open precision of a trailing-zero whole number (``alt_bounds``) is not read for a count (a term that takes only
    whole values, :func:`_takes_whole_values`, whatever the sort it is compared in): half a unit of its last written digit
    is then the exact count ("about 300 visitors" as exactly 300), which the approximation word denies, so only the reading
    at its first significant digit is stated, as for the same count compared over Int (close round 2, DIFF-06: "about 300"
    for a stated 260, encoded over to_real, was AMBIGUOUS_TRANSLATION and not releasable, where the committed base, and the
    same claim over Int, showed it ENTAILED). For a measured quantity whose significant digits are not a lone 1 the last-digit
    reading is denied as an alternative (``Reading.alt_denied``; accuracy round 1, DV2-08: "about 300 g" for a stated 260 g,
    encoded at [250, 350), was AMBIGUOUS_TRANSLATION where the committed base showed it ENTAILED): the first significant
    digit's interval is then exactly the values that round to the figure there, and "about" denies the last digit's
    precision. An encoding at that interval stands on its own; an encoding at the last written digit is still probed at it
    (ambiguous when the two disagree, as before). A power of ten ("about 100%") keeps both readings
    (:func:`_power_of_ten_numeral`)."""
    symbols: dict[str, Symbol] = {s.name: s for s in problem.symbols}
    out: list[Reading] = []
    for site in collect_sites(problem) if sites is None else sites:
        sym = symbols.get(site.symbol) if site.symbol else None
        declared = declared_reading(sym.meaning if sym is not None else None)
        if _is_stated_range(site, sources, declared):
            continue
        reading = _reading_of(site, site.value, sources, declared)
        if reading is None and site.kind == "interval":
            # the stated figure the interval lies around; its bounds are computed at that figure's value and scale
            reading = _contained_figure(site, sources, declared)
        if reading is None and site.kind == "interval":
            # an interval inside one stated figure's interval, though the figure lies outside it (B22)
            reading = _enclosing_figure(site, sources, declared)
        if reading is not None and reading.alt_bounds is not None and site.scale is None and _takes_whole_values(site.term, symbols):
            reading.alt_bounds = None  # a count: the last-digit reading is the exact count, which "about" denies
        elif reading is not None and reading.alt_bounds is not None and not _power_of_ten_numeral(reading.figure):
            # the first significant digit's interval is exactly the values that round to the figure there ("about 300 g" is [250,
            # 350) for 260 g), and the approximation word denies the last written digit's precision: that reading is no
            # alternative to it (accuracy round 1, DV2-08); a power of ten keeps both ("about 100%": [50, 150) reaches into a
            # decade where one significant figure is finer, so the last-digit reading stays as its check)
            reading.alt_denied = True
        out.append(reading if reading is not None else Reading(site, "unsourced"))
    return out


def _power_of_ten_numeral(figure: Optional[StatedFigure]) -> bool:
    """Whether a figure's significant digits, its trailing zeros set aside, are a lone 1 ("100", "1,000", "10%"): its
    trailing-zero tolerance then reaches below into a decade where one significant figure is a finer step. True when the
    figure is unknown (both readings are then kept, as before)."""
    if figure is None:
        return True
    digits = figure.numeral.replace(",", "").replace(" ", "").replace(" ", "").replace(" ", "").lstrip("+-−")
    return not digits.isdecimal() or digits.rstrip("0").lstrip("0") == "1"


def _bounds_text(b: tuple[Fraction, Fraction, bool, bool]) -> str:
    lo, hi, lo_incl, hi_incl = b
    return f"{'[' if lo_incl else '('}{decimal_text(lo)}, {decimal_text(hi)}{']' if hi_incl else ')'}"


def _bound_ops(b: tuple[Fraction, Fraction, bool, bool]) -> str:
    lo, hi, lo_incl, hi_incl = b
    return f"'{'ge' if lo_incl else 'gt'}' {decimal_text(lo)} and '{'le' if hi_incl else 'lt'}' {decimal_text(hi)}"


def figure_records(readings: Sequence[Reading]) -> list[FigureReading]:
    """The contract records of ``readings`` (one per literal and source span; assertion ids merged)."""
    merged: dict[tuple, FigureReading] = {}
    for r in readings:
        f = r.figure
        key = (r.site.literal, r.site.kind, f.source_kind if f else None, f.source_id if f else None, f.start if f else None)
        if key in merged:
            old = merged[key]
            if r.site.assertion_id not in old.assertion_ids:
                merged[key] = old.model_copy(update={"assertion_ids": [*old.assertion_ids, r.site.assertion_id]})
            continue
        ex = r.stated
        merged[key] = FigureReading(
            literal=r.site.literal, assertion_ids=[r.site.assertion_id], source_kind=f.source_kind if f else "none", source_id=f.source_id if f else None,
            start=f.start if f else None, end=f.end if f else None, written=f.written if f else None, exactness=r.exactness,
            cue=(ex.cue[:300] if ex is not None and ex.cue else None), mode=ex.mode if ex is not None else "nearest",
            precision=ex.precision if ex is not None and r.exactness == "rounded" else None,
            lower=decimal_text(r.stated_bounds[0]) if r.stated_bounds else None, upper=decimal_text(r.stated_bounds[1]) if r.stated_bounds else None,
            unit=f.unit if f else None, derivation=r.match.derivation[:500] if r.match else None,
            encoded_as="exact_equality" if r.site.kind == "eq" else "interval",
            calculated=(fraction_text(ex.computed)[:200] if ex is not None and ex.computed is not None else None),
            by_convention=bool(ex is not None and ex.by_convention and r.exactness == "rounded"))
    return list(merged.values())


# ------------------------------------------------------------------ rewriting


def _get(data: Any, path: tuple) -> Any:
    for k in path:
        data = data[k]
    return data


def _set(data: Any, path: tuple, value: Any) -> None:
    parent = _get(data, path[:-1])
    parent[path[-1]] = value


def _figure_node(value: Fraction, scale: Optional[dict] = None) -> dict:
    """A bound's right side: the literal, or the literal times the site's scale (the cross-multiplied form kept)."""
    lit = {"op": "real", "value": decimal_text(value)}
    return lit if scale is None else {"op": "mul", "args": [lit, scale]}


def _interval_node(term: dict, b: tuple[Fraction, Fraction, bool, bool], scale: Optional[dict] = None) -> dict:
    lo, hi, lo_incl, hi_incl = b
    return {"op": "and", "args": [{"op": "ge" if lo_incl else "gt", "left": term, "right": _figure_node(lo, scale)},
                                  {"op": "le" if hi_incl else "lt", "left": term, "right": _figure_node(hi, scale)}]}


def _bound_nodes(term: dict, b: tuple[Fraction, Fraction, bool, bool], scale: Optional[dict] = None) -> tuple[dict, dict]:
    lo, hi, lo_incl, hi_incl = b
    return ({"op": "ge" if lo_incl else "gt", "left": term, "right": _figure_node(lo, scale)},
            {"op": "le" if hi_incl else "lt", "left": term, "right": _figure_node(hi, scale)})


def rewrite(problem: Problem, widen: Sequence[tuple[Reading, tuple[Fraction, Fraction, bool, bool]]] = (), narrow: Sequence[Reading] = (),
            retarget: Sequence[tuple[Reading, tuple[Fraction, Fraction, bool, bool]]] = ()) -> Optional[Problem]:
    """``problem`` with each ``widen`` equality read as its interval, each ``narrow`` interval read as an equality at
    its midpoint and each ``retarget`` interval given other bounds (its two bounds replaced in place, so the other
    conjuncts of its conjunction stay); None when the rewritten data is not a valid problem."""
    data = problem.model_dump(mode="json", exclude_none=True)
    for r, b in retarget:
        lower, upper = _bound_nodes(r.site.term, b, r.site.scale)
        li, hi_i = r.site.arg_indices
        if r.site.split:
            data["premises"][li]["expr"], data["premises"][hi_i]["expr"] = lower, upper
        else:
            node = _get(data, r.site.path)
            node["args"][li], node["args"][hi_i] = lower, upper
    for r, b in widen:
        _set(data, r.site.path, _interval_node(r.site.term, b, r.site.scale))
    by_and: dict[tuple, list[Reading]] = {}
    for r in narrow:
        if r.site.split:  # two bound premises: each becomes the equality (a repeated premise is harmless)
            for i in r.site.arg_indices:
                data["premises"][i]["expr"] = {"op": "eq", "left": r.site.term, "right": _figure_node(r.site.value, r.site.scale)}
            continue
        by_and.setdefault(r.site.path, []).append(r)
    for path in sorted(by_and, key=len, reverse=True):
        node = _get(data, path)
        drop = {i for r in by_and[path] for i in r.site.arg_indices}
        args = [a for i, a in enumerate(node["args"]) if i not in drop]
        args += [{"op": "eq", "left": r.site.term, "right": _figure_node(r.site.value, r.site.scale)} for r in by_and[path]]
        _set(data, path, args[0] if len(args) == 1 else {"op": "and", "args": args})
    try:
        return Problem.model_validate(data)
    except (ValidationError, ValueError):
        return None


# ------------------------------------------------------------------ the decision


def _verdict(problem: Problem, config: SolverConfig) -> Optional[VerificationStatus]:
    status = engine_verify(problem, config, diagnose=False).status  # an internal probe: no argument diagnosis
    return status if status in DEFINITIVE else None


def _site_bounds(r: Reading) -> tuple[Fraction, Fraction, bool, bool]:
    return r.site.lo, r.site.hi, r.site.lo_incl, r.site.hi_incl  # type: ignore[return-value]


def _stated_text(r: Reading) -> str:
    """The interval(s) the wording states for ``r``, with the operators to encode them."""
    primary = r.alt_bounds if r.alt_bounds is not None else r.stated_bounds
    if primary is None:
        return "no interval"
    text = f"{_bounds_text(primary)} ({_bound_ops(primary)})"
    if r.alt_bounds is not None and r.bounds is not None:
        text += (f", half a unit of its last written digit; or, its trailing zeros read as not significant, {_bounds_text(r.bounds)} "
                 f"({_bound_ops(r.bounds)})")
    return text


def decide_precision(problem: Problem, readings: Sequence[Reading], config: SolverConfig, tag: str) -> PrecisionDecision:
    """Reject, flag or accept the encoding's figures (see the module docstring).

    An interval in place of a rounded figure must be the interval the wording states. Three readings refine that rule,
    and none relaxes it for a genuinely wider or narrower interval of a figure it reads:

    * an interval equal to the stated one except for the closure of an end ("[1.545, 1.555]" for "≈ 1.55", stated
      "[1.545, 1.555)") is accepted when one probe at the stated closure gives the same verdict, and rejected otherwise;
    * an interval tied to a figure only because the figure's stated interval contains it (B22) is rejected when the probe
      at the stated interval changes the verdict;
    * a whole number with trailing zeros and a bare approximation word ("about 100%") states its precision openly: half a
      unit of its last written digit or of its first significant digit. An encoding at either is accepted; when the two
      readings give different verdicts the translation is AMBIGUOUS_TRANSLATION, never a verdict (neither reading is
      forced, and the wider one never earns a proof on its own)."""
    decision = PrecisionDecision(readings=figure_records(readings))
    weakened = [r for r in readings if r.site.kind == "interval" and r.exactness in ("exact", "given")]
    if weakened:
        shown = "; ".join(f"{decimal_text(r.site.value)} ({r.describe()}) is encoded as the interval "
                          f"{_bounds_text((r.site.lo, r.site.hi, r.site.lo_incl, r.site.hi_incl))} in {r.site.assertion_id}" for r in weakened[:6])  # type: ignore[arg-type]
        decision.reject = ("exactness", f"{tag}: exactness: the source states each of these figures exactly, but the encoding widens it: {shown}. A figure stated "
                                        "exactly (or given exactly by the task) is encoded with 'eq' and never widened; if the claim then does not follow, its "
                                        "counterexample is the verdict. An interval is only for a figure the source itself states as rounded")
        return decision
    cache: dict[str, Optional[VerificationStatus]] = {}

    def base_verdict() -> Optional[VerificationStatus]:
        if "base" not in cache:
            cache["base"] = _verdict(problem, config)
        return cache["base"]

    mismatched: list[Reading] = []
    checked: list[tuple[Reading, tuple[Fraction, Fraction, bool, bool]]] = []
    duals: list[tuple[Reading, tuple[Fraction, Fraction, bool, bool]]] = []
    for r in readings:
        if r.site.kind != "interval":
            continue
        site = _site_bounds(r)
        if r.enclosed:
            stated = r.stated_bounds
            if stated is not None and site != stated:
                checked.append((r, stated))
            continue
        if r.exactness != "rounded" or r.bounds is None:
            continue
        options = [r.bounds] + ([r.alt_bounds] if r.alt_bounds is not None else [])
        if site in options:
            # an encoding at the first significant digit of a figure whose last-digit reading is denied stands on its own
            # (accuracy round 1, DV2-08); one at the last written digit is still probed at the stated interval
            if r.alt_bounds is not None and not (r.alt_denied and site == r.bounds):
                duals.append((r, r.alt_bounds if site == r.bounds else r.bounds))
            continue
        closure = next((o for o in options if o[:2] == site[:2]), None)
        if closure is not None:
            checked.append((r, closure))
            continue
        mismatched.append(r)
    if mismatched:
        shown = "; ".join(f"{r.written()} in {r.site.assertion_id} is encoded as {_bounds_text(_site_bounds(r))} but {r.describe()} states {_stated_text(r)}"
                          for r in mismatched[:6])
        decision.reject = ("stated_precision", f"{tag}: stated precision: the interval does not match the precision the source states: {shown}. Encode exactly the "
                                               "stated interval: a wider one weakens the claim and a narrower one strengthens it")
        return decision
    if checked:
        alt = rewrite(problem, retarget=checked)
        stated_verdict = _verdict(alt, config) if alt is not None else None
        base = base_verdict()
        if base is None or stated_verdict is None or base is not stated_verdict:
            outcome = (f"it is {base.value} as encoded but {stated_verdict.value} at the stated interval" if base is not None and stated_verdict is not None
                       else "the verdict at the stated interval could not be compared")
            shown = "; ".join(f"{r.written()} in {r.site.assertion_id} is encoded as {_bounds_text(_site_bounds(r))} but {r.describe()} states {_bounds_text(b)} "
                              f"({_bound_ops(b)})" for r, b in checked[:6])
            decision.reject = ("stated_precision", f"{tag}: stated precision: the interval does not match the precision the source states, and {outcome}: "
                                                   f"{shown}. Encode exactly the stated interval")
            return decision
    if duals:
        alt = rewrite(problem, retarget=duals)
        other = _verdict(alt, config) if alt is not None else None
        base = base_verdict()
        if base is not None and other is not None and base is not other:
            names = ", ".join(f"{r.written()} ({r.where()})" for r, _b in duals[:6])
            decision.ambiguity = AmbiguityFlag(
                code="stated_precision",
                message=(f"(deterministic) the source writes {names} as a whole number with trailing zeros and an approximation word that states no "
                         f"precision: read to half a unit of its last written digit or of its first significant digit, the problem is {base.value} "
                         f"as encoded and {other.value} the other way. The wording does not fix which, so neither reading is shown as a verdict")[:2000],
                alternatives=[f"the figure at the precision encoded: {base.value}"[:200], f"the figure at the other reading: {other.value}"[:200]],
            )
            return decision
    rounded_eq = [r for r in readings if r.site.kind == "eq" and r.exactness == "rounded" and r.bounds is not None]
    explicit = [r for r in rounded_eq if r.stated is not None and not r.stated.by_convention]
    convention = [r for r in rounded_eq if r not in explicit]

    def reject_with(stated: VerificationStatus, figures: Sequence[tuple[Reading, tuple[Fraction, Fraction, bool, bool]]]) -> PrecisionDecision:
        base = base_verdict()
        shown = "; ".join(f"{r.site.literal} in {r.site.assertion_id} ({r.describe()}: {_bound_ops(b)})" for r, b in figures[:8])
        decision.reject = ("stated_precision", f"{tag}: stated precision: the problem is {base.value} as encoded, but {stated.value} once each figure the source "  # type: ignore[union-attr]
                                               f"states as rounded is read at its stated precision: {shown}. Encode each such figure at its stated precision "
                                               "(those bounds), and keep 'eq' for every figure the source states exactly")
        return decision

    if explicit:
        # an explicit rounding cue states the tolerance: whichever way it moves the verdict, the exact equality misstates it
        base = base_verdict()
        wide = [(r, r.bounds) for r in explicit]
        alt = rewrite(problem, widen=wide)  # type: ignore[arg-type]
        stated = _verdict(alt, config) if alt is not None else None
        if any(r.alt_bounds is not None for r in explicit):
            narrow_pairs = [(r, r.alt_bounds if r.alt_bounds is not None else r.bounds) for r in explicit]
            alt2 = rewrite(problem, widen=narrow_pairs)  # type: ignore[arg-type]
            stated2 = _verdict(alt2, config) if alt2 is not None else None
            if stated is not None and stated2 is not None and stated is not stated2:
                names = ", ".join(f"{r.written()} ({r.where()})" for r in explicit if r.alt_bounds is not None)
                decision.ambiguity = AmbiguityFlag(
                    code="stated_precision",
                    message=(f"(deterministic) the source writes {names} as a whole number with trailing zeros and an approximation word that states "
                             f"no precision: read to half a unit of its last written digit the problem is {stated2.value}, read to half a unit of its "
                             f"first significant digit it is {stated.value}. The wording does not fix which, so neither reading is shown as a verdict")[:2000],
                    alternatives=[f"half a unit of the last written digit: {stated2.value}"[:200], f"half a unit of the first significant digit: {stated.value}"[:200]],
                )
                return decision
            if base is not None and stated2 is not None and base is not stated2:
                return reject_with(stated2, narrow_pairs)  # type: ignore[arg-type]
        elif base is not None and stated is not None and base is not stated:
            return reject_with(stated, wide)  # type: ignore[arg-type]
    if convention:
        # the convention of written calculation, for a calculation the reader cannot compute, is a presumption: it may
        # explain a failure (a correct rounded result read as exact), but it never refutes a proof on its own, since the
        # written result may be exact (2³ × 0.5 = 4.0)
        base = base_verdict()
        alt = rewrite(problem, widen=[(r, r.bounds) for r in rounded_eq])  # type: ignore[misc]
        stated = _verdict(alt, config) if alt is not None else None
        passing = _PASSING_STATUS.get(problem.query)
        if base is not None and stated is not None and base is not stated:
            if base is not passing:
                return reject_with(stated, [(r, r.bounds) for r in rounded_eq])  # type: ignore[misc]
            names = ", ".join(f"{r.site.literal} ({r.where()})" for r in convention[:6])
            decision.ambiguity = AmbiguityFlag(
                code="stated_precision",
                message=(f"(deterministic) the source writes {names} as the result of a calculation with no rounding cue: read exactly the problem is "
                         f"{base.value}, read to half a unit of its last written place it is {stated.value}. The proof needs the figure exactly as written, "
                         "which the wording does not state, so it is not shown as verified")[:2000],
                alternatives=[f"figures read exactly as written: {base.value}"[:200], f"figures read at their written precision: {stated.value}"[:200]],
            )
    loose = [r for r in readings if not r.enclosed and r.exactness in ("unstated", "conflicting")
             and ((r.site.kind == "eq" and r.written_bounds is not None) or r.site.kind == "interval")]
    if loose and decision.ambiguity is None:
        widen = [(r, r.written_bounds) for r in loose if r.site.kind == "eq"]
        narrow = [r for r in loose if r.site.kind == "interval"]
        alt = rewrite(problem, widen=widen, narrow=narrow)  # type: ignore[arg-type]
        base = base_verdict()
        other = _verdict(alt, config) if alt is not None else None
        if base is not None and other is not None and base is not other:
            enc = "as written" if not narrow else "as encoded"
            names = ", ".join(f"{r.site.literal} ({r.where()})" for r in loose[:6])
            decision.ambiguity = AmbiguityFlag(
                code="stated_precision",
                message=(f"(deterministic) the source states {names} with no wording that settles how exactly (no exactness or rounding cue, or "
                         "conflicting ones), and the verdict depends on the reading: "
                         f"{base.value} with the figures {enc}, {other.value} with each read the other way (to half a unit of its last written place, or "
                         "exactly). Neither reading is chosen because it is easier to prove; the claim is not shown as verified until its wording fixes one")[:2000],
                alternatives=[f"figures read exactly as written: {base.value}"[:200] if not narrow else f"figures read as encoded: {base.value}"[:200],
                              f"figures read the other way: {other.value}"[:200]],
            )
    return decision


# ------------------------------------------------------------------ retries


def reference_reading(problem: Problem, readings: Sequence[Reading]) -> Problem:
    """``problem`` read as its source states it: rounded equalities widened to their stated tolerance, exact or given
    figures written as intervals narrowed back to equalities, and an interval of a rounded or enclosing figure that differs
    from the interval the wording states given that interval (for an open precision, the reading at the last written
    digit, the prompt's rule). The reference a retry's conclusion is compared with: a retry that encodes exactly what a
    stated-precision rejection asked for keeps the claim."""
    widen = [(r, r.alt_bounds if r.alt_bounds is not None else r.bounds) for r in readings
             if r.site.kind == "eq" and r.exactness == "rounded" and r.bounds is not None]
    narrow = [r for r in readings if r.site.kind == "interval" and r.exactness in ("exact", "given")]
    retarget: list[tuple[Reading, tuple[Fraction, Fraction, bool, bool]]] = []
    for r in readings:
        if r.site.kind != "interval" or r in narrow:
            continue
        site = _site_bounds(r)
        if r.enclosed and r.stated_bounds is not None and site != r.stated_bounds:
            retarget.append((r, r.stated_bounds))
        elif not r.enclosed and r.exactness == "rounded" and r.bounds is not None:
            options = [r.bounds] + ([r.alt_bounds] if r.alt_bounds is not None else [])
            if site not in options:
                retarget.append((r, r.alt_bounds if r.alt_bounds is not None else r.bounds))
    if not widen and not narrow and not retarget:
        return problem
    return rewrite(problem, widen=widen, narrow=narrow, retarget=retarget) or problem  # type: ignore[arg-type]


def _entails(premise_expr: Any, conclusion_expr: Any, symbols: list[dict], config: SolverConfig) -> Optional[bool]:
    try:
        probe = Problem.model_validate({"problem_id": "retry-compare", "request_id": "retry-compare", "claim_id": "retry-compare", "query": "entailment",
                                        "symbols": symbols, "premises": [{"id": "NEW", "expr": premise_expr}], "conclusion": {"id": "REF", "expr": conclusion_expr}})
    except (ValidationError, ValueError):
        return None
    status = engine_verify(probe, config, diagnose=False).status  # an internal probe: no argument diagnosis
    if status is VerificationStatus.ENTAILED:
        return True
    if status in (VerificationStatus.COUNTEREXAMPLE, VerificationStatus.INCONSISTENT_PREMISES):
        return False if status is VerificationStatus.COUNTEREXAMPLE else None
    return None


def compare_conclusions(reference: Problem, new: Problem, config: SolverConfig) -> Literal["unchanged", "equivalent", "stronger", "weaker", "incomparable", "not_compared"]:
    """How a retry's conclusion relates to the earlier conclusion read as its source states it (``reference``):
    ``stronger`` or ``equivalent`` keep the claim; ``weaker`` (implied by the reference, not conversely) and
    ``incomparable`` (neither, or symbols of one name with different sorts) do not."""
    if reference.conclusion is None or new.conclusion is None:
        return "not_compared"
    a = new.conclusion.expr.model_dump(mode="json", exclude_none=True)
    b = reference.conclusion.expr.model_dump(mode="json", exclude_none=True)
    if _canonical(a) == _canonical(b):
        return "unchanged"
    sorts: dict[str, str] = {}
    for sym in [*reference.symbols, *new.symbols]:
        if sorts.setdefault(sym.name, sym.sort) != sym.sort:
            return "incomparable"
    symbols = [{"name": n, "sort": s} for n, s in sorts.items()]
    new_implies_ref = _entails(a, b, symbols, config)
    ref_implies_new = _entails(b, a, symbols, config)
    if new_implies_ref and ref_implies_new:
        return "equivalent"
    if new_implies_ref:
        return "stronger"
    if ref_implies_new:
        return "weaker"
    return "incomparable"


def premise_changes(before: Problem, after: Problem) -> list[str]:
    """Premises a retry added or removed (by expression), each with its grounding kind and check."""
    def key(p: Assertion) -> str:
        return _canonical(p.expr.model_dump(mode="json", exclude_none=True))
    old = {key(p): p for p in before.premises}
    new = {key(p): p for p in after.premises}
    out: list[str] = []
    for k, p in new.items():
        if k not in old:
            g = p.grounding
            state = "no grounding" if g is None else f"{g.kind}, " + {True: "verified", False: "check failed", None: "unchecked"}[g.verified]
            out.append(f"premise {p.id} added ({state})" + (f": {p.label[:120]!r}" if p.label else ""))
    for k, p in old.items():
        if k not in new:
            out.append(f"premise {p.id} removed" + (f": {p.label[:120]!r}" if p.label else ""))
    return out


def added_premise_support(before: Problem, after: Problem, asserted_atoms: Sequence[str], config: SolverConfig) -> list[tuple[Assertion, bool, str]]:
    """``(premise, supported, why)`` for every premise a retry added (by expression) after a rejection for an unasserted
    figure. A premise is supported when a check in this process established it (its grounding is ``verified``), or when
    it follows (Z3, under ``config``) from the rejected attempt's premises with the ``asserted_atoms`` asserted: the atoms
    of the definitions whose figure a source asserts (the rejection's coverage evidence). So the stated figure, the atom,
    and a reformulation of the definition are supported; a figure the source does not assert (another value, an invented
    fact) is not. Undecided, inconsistent or sort-conflicting probes support nothing."""
    def key(p: Assertion) -> str:
        return _canonical(p.expr.model_dump(mode="json", exclude_none=True))
    old = {key(p) for p in before.premises}
    added = [p for p in after.premises if key(p) not in old]
    if not added:
        return []
    sorts: dict[str, str] = {}
    conflict = False
    for sym in [*before.symbols, *after.symbols]:
        if sorts.setdefault(sym.name, sym.sort) != sym.sort:
            conflict = True
    atoms = [a for a in dict.fromkeys(asserted_atoms) if sorts.get(a) == "Bool"]
    givens = [{"id": f"EARLIER_{i}", "expr": p.expr.model_dump(mode="json", exclude_none=True)} for i, p in enumerate(before.premises)]
    givens += [{"id": f"ASSERTED_{i}", "expr": {"op": "var", "name": a}} for i, a in enumerate(atoms)]
    stated = f" with the source-asserted atom(s) {', '.join(atoms)} asserted" if atoms else ""
    out: list[tuple[Assertion, bool, str]] = []
    for p in added:
        g = p.grounding
        if g is not None and g.verified is True:
            out.append((p, True, f"supported: established by a grounding check in this process ({g.kind})"))
            continue
        status: Optional[VerificationStatus] = None
        if not conflict:
            try:
                probe = Problem.model_validate({"problem_id": "retry-support", "request_id": "retry-support", "claim_id": "retry-support",
                                                "query": "entailment", "symbols": [{"name": n, "sort": t} for n, t in sorts.items()],
                                                "premises": givens, "conclusion": {"id": "ADDED", "expr": p.expr.model_dump(mode="json", exclude_none=True)}})
                status = engine_verify(probe, config, diagnose=False).status  # an internal probe: no argument diagnosis
            except (ValidationError, ValueError):
                status = None
        if status is VerificationStatus.ENTAILED:
            out.append((p, True, f"supported: it follows from the rejected attempt's premises{stated} (what the source asserts)"))
        else:
            state = "no grounding" if g is None else f"{g.kind}, " + {True: "verified", False: "check failed", None: "unchecked"}[g.verified]
            out.append((p, False, f"unsupported, NOT what the source asserts ({state}): it does not follow from the rejected attempt's premises{stated}, "
                                  "and no check established it"))
    return out
