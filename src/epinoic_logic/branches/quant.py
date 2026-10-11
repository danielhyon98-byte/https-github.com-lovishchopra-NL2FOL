"""Deterministic extraction of a report's own quantitative statements and formal
self-consistency checks on them. No model is involved: regular expressions find
figures the specialist stated, and the engine decides whether the derived figures
the specialist also stated actually follow (percentage changes, percentage-point
differences, word fractions, fold changes, shares, totals). A specialist that writes
"rose from 1.4 million to 6 million, a threefold increase" is caught by arithmetic,
not by opinion.

Shapes read from a from/to pair (``from 381 in September 1929 to about 41 in July
1932``; dated figures may carry a day, a month, ``early``/``late`` and a year):

* shared-unit elision: when only the second figure carries a unit (``from 15 to 45
  million``, ``from 3.2 to 24.9 per cent``) the unit applies to both figures;
* units: scales (million, thousand, ...), per cent, rates (``per thousand``,
  ``per 100,000``, ``per head``), seats and votes;
* derived figures: ``a fall of 50 per cent``, ``fell by a third``, ``a rise of 25
  percentage points``, ``doubled``/``doubling``, ``halved``, ``threefold``.

Tolerance rule (:data:`TOLERANCE_RULE`): the stated derived figure must lie within
``tolerance`` (default 5 per cent) of the value computed from the report's own figures.
The band is symmetric around the COMPUTED value, not around the stated one, so a
specialist who understates a change does not earn a wider band than one who overstates
it. Per-cent and percentage-point figures also pass when within 0.5 points of the
computed value (rounding to the nearest whole per cent is never a finding). ``more
than``/``over`` before a stated change makes the check one-sided (a lower bound only),
``under``/``less than`` an upper bound only. The rule is repeated in every check's
``rule`` field so the receipt says how the figure was judged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from ..ir.schema import Problem

_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?!\d|,\d|\.\d)"  # never split a thousands group or a decimal
_PCT_UNIT = r"(?:per cent|percent(?!age)|%)"  # 'percentage points' is a difference, not a per-cent unit
_RATE_UNIT = r"per (?:thousand|1,?000|10,?000|100,?000|million|head|capita)"
_UNIT = rf"(?:\s*(million|billion|thousand|{_RATE_UNIT}|per cent|percent(?!age)|%|seats|votes|m|bn|k)\b)?"
_QUAL = r"(?:about|around|roughly|nearly|almost|some|approximately|an estimated|over|more than|less than|under|at least|at most|up to|just over|just under)"
_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?"
#: An optional date after a figure: 'in 1928', 'by early 1932', 'in September 1929', 'on 18 June 1815', 'in January 30, 1933'.
_DATE = (rf"(?:\s+(?:in|by|of|on|at|during|for)\s+(?:the\s+)?(?:(?:early|late|mid|the end of|the start of|the beginning of|the middle of)[\s-]*)?"
         rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?(?:{_MONTH}\s+)?(?:\d{{1,2}},?\s+)?(?:1[0-9]{{3}}|20[0-9]{{2}}))?")
_FROM_TO_RE = re.compile(rf"\b(?:from|of)\s+(?:{_QUAL}\s+)?{_NUM}{_UNIT}{_DATE}\s+(?:to|and)\s+(?:{_QUAL}\s+)?{_NUM}{_UNIT}", re.IGNORECASE)
_FALL_WORDS = frozenset({"fall", "decrease", "decline", "drop", "reduction", "cut", "loss", "contraction", "fell", "dropped", "declined", "decreased", "shrank", "contracted", "slumped", "collapsed", "halved", "halving"})
_DIR_NOUN = r"(increase|rise|fall|decrease|decline|drop|growth|reduction|cut|gain|loss|expansion|contraction)"
_DIR_VERB = r"(rose|grew|increased|expanded|climbed|fell|dropped|declined|decreased|shrank|contracted|slumped|collapsed)"
_PCT_CHANGE_RE = re.compile(
    rf"(?:an?\s+)?{_DIR_NOUN}\s+of\s+(?:({_QUAL})\s+)?(\d+(?:\.\d+)?)\s*{_PCT_UNIT}(?!\s*points?\b)"
    rf"|(?:an?\s+)?(?:({_QUAL})\s+)?(\d+(?:\.\d+)?)\s*{_PCT_UNIT}\s+{_DIR_NOUN}"
    rf"|{_DIR_VERB}\s+by\s+(?:({_QUAL})\s+)?(\d+(?:\.\d+)?)\s*{_PCT_UNIT}(?!\s*points?\b)",
    re.IGNORECASE)
# 'a fall of 4.2 percentage points' / 'rose by 3 points' between two per-cent figures: an absolute difference.
_POINTS_CHANGE_RE = re.compile(
    rf"(?:an?\s+)?{_DIR_NOUN}\s+of\s+(?:({_QUAL})\s+)?(\d+(?:\.\d+)?)\s*(?:percentage\s+)?points?\b"
    rf"|(?:an?\s+)?(?:({_QUAL})\s+)?(\d+(?:\.\d+)?)\s*(?:percentage\s+)?points?\s+{_DIR_NOUN}"
    rf"|{_DIR_VERB}\s+by\s+(?:({_QUAL})\s+)?(\d+(?:\.\d+)?)\s*(?:percentage\s+)?points?\b",
    re.IGNORECASE)
_FRAC = r"((?:a|one)\s+(?:half|third|quarter|fifth|tenth)|two[- ]thirds|three[- ]quarters|two[- ]fifths|three[- ]fifths|four[- ]fifths|half)"
_FRACTION_CHANGE_RE = re.compile(rf"(?:an?\s+)?{_DIR_NOUN}\s+of\s+(?:({_QUAL})\s+)?{_FRAC}\b|{_DIR_VERB}\s+by\s+(?:({_QUAL})\s+)?{_FRAC}\b", re.IGNORECASE)
_FRACTION_WORDS = {"half": Fraction(1, 2), "third": Fraction(1, 3), "quarter": Fraction(1, 4), "fifth": Fraction(1, 5), "tenth": Fraction(1, 10),
                   "two thirds": Fraction(2, 3), "three quarters": Fraction(3, 4), "two fifths": Fraction(2, 5), "three fifths": Fraction(3, 5), "four fifths": Fraction(4, 5)}
_FOLD_RE = re.compile(r"(?:\b(more than|over|nearly|almost|about|roughly|just over|just under)\s+)?\b(doubl(?:ed|ing)|trebl(?:ed|ing)|tripl(?:ed|ing)|quadrupl(?:ed|ing)|halv(?:ed|ing)|(\d+(?:\.\d+)?)-fold|(two|three|four|five|six|seven|eight|nine|ten)-?fold)\b", re.IGNORECASE)
_FOLD_STEMS = {"doubl": Fraction(2), "trebl": Fraction(3), "tripl": Fraction(3), "quadrupl": Fraction(4), "halv": Fraction(1, 2)}
_FOLD_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_YEAR_LIKE_RE = re.compile(r"^(?:1[0-9]{3}|20[0-9]{2})$")
_PCT_WORDS = frozenset({"per cent", "percent", "%"})
_SHARE_RE = re.compile(rf"\b{_NUM}\s*{_PCT_UNIT}\s+of\s+(?:the\s+)?(?:about|around|roughly)?\s*{_NUM}{_UNIT}(?:\s+[a-z]+){{0,2}}?(?:\s*,\s*(?:or|i\.e\.|that is)?|\s+(?:or|was|is|=|that is|i\.e\.)|\s*\()\s*(?:about|around|roughly|some)?\s*{_NUM}{_UNIT}", re.IGNORECASE)
_TOTAL_RE = re.compile(rf"{_NUM}{_UNIT}\s+(?:and|plus)\s+(?:[a-z][a-z ]{{0,40}}?\s)?{_NUM}{_UNIT}[^.;]{{0,60}}?(?:a total of|totalling|together|in total|making|giving|totals?)\s+(?:about|around|roughly)?\s*{_NUM}{_UNIT}", re.IGNORECASE)
_SCALE = {"million": 10**6, "m": 10**6, "billion": 10**9, "bn": 10**9, "thousand": 10**3, "k": 10**3}
_SENT_RE = re.compile(r"(?<=[.?!;])\s+")
_LOWER_ONLY = frozenset({"more than", "over", "at least", "just over"})
_UPPER_ONLY = frozenset({"less than", "under", "at most", "up to", "just under"})
#: Half a percentage point: a per-cent figure rounded to the nearest whole number always passes.
POINT_FLOOR = Fraction(1, 2)
TOLERANCE_RULE = ("tolerance: the stated figure must lie within {tol}% of the value computed from the report's own figures; the band is symmetric "
                  "around the computed value (understating a change earns no wider band){floor}{side}")


@dataclass(frozen=True)
class QuantCheck:
    check_id: str
    kind: str                 # percent_change | points_change | fraction_change | fold_change | share | total
    sentence: str
    problem: Problem
    expected_if_consistent: str = "ENTAILED"
    rule: str = ""            # the tolerance rule applied, for the receipt


def _frac(num: str, unit: Optional[str]) -> Fraction:
    f = Fraction(num.replace(",", ""))
    if unit:
        u = unit.lower()
        if u in _SCALE:
            f *= _SCALE[u]
    return f


def _real(f: Fraction) -> dict:
    return {"op": "real", "value": f"{f.numerator}/{f.denominator}" if f.denominator != 1 else str(f.numerator)}


def _v(n):
    return {"op": "var", "name": n}


def _year_like(num: str, unit: Optional[str]) -> bool:
    """A unitless integer in 1000-2099 with no separator reads as a year, not a quantity."""
    return not unit and bool(_YEAR_LIKE_RE.match(num))


def _is_pct(unit: Optional[str]) -> bool:
    return bool(unit) and unit.lower().replace("percent", "per cent") in _PCT_WORDS


def _side(qualifier: Optional[str]) -> str:
    q = (qualifier or "").lower()
    return "lower" if q in _LOWER_ONLY else "upper" if q in _UPPER_ONLY else "both"


def _rule_text(tolerance: Fraction, floor: Fraction, side: str) -> str:
    return TOLERANCE_RULE.format(tol=f"{float(tolerance) * 100:g}",
                                 floor=f", or within {float(floor):g} percentage points of it" if floor else "",
                                 side=" (one-sided: the stated figure is a lower bound)" if side == "lower" else " (one-sided: the stated figure is an upper bound)" if side == "upper" else "")


def _within(expr: dict, stated: Fraction, tolerance: Fraction, floor: Fraction = Fraction(0), side: str = "both") -> dict:
    """``expr`` within the tolerance band around itself that contains ``stated``:
    |computed - stated| <= tolerance * computed, or <= floor. Linear in ``expr``."""
    lo = min(stated / (1 + tolerance), stated - floor)
    hi = max(stated / (1 - tolerance), stated + floor)
    ge = {"op": "ge", "left": expr, "right": _real(lo)}
    le = {"op": "le", "left": expr, "right": _real(hi)}
    if side == "lower":
        return ge
    if side == "upper":
        return le
    return {"op": "and", "args": [ge, le]}


def _problem(pid: str, claim_id: str, request_id: str, symbols: list[tuple[str, str]], premises: list[tuple[str, dict, str]], conclusion: tuple[str, dict, str]) -> Problem:
    return Problem.model_validate({
        "problem_id": pid, "request_id": request_id, "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": n, "sort": "Real", "meaning": m} for n, m in symbols],
        "premises": [{"id": i, "expr": e, "label": l, "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}} for i, e, l in premises],
        "conclusion": {"id": conclusion[0], "expr": conclusion[1], "label": conclusion[2], "grounding": {"kind": "supplied_text", "verified": True}},
    })


def _direction(word: str) -> str:
    return "fall" if word.lower() in _FALL_WORDS else "rise"


def _pct_change(sent: str) -> Optional[tuple[str, Fraction, str]]:
    """(direction, stated per cent, side) for a stated relative change, or None."""
    m = _PCT_CHANGE_RE.search(sent)
    if not m:
        return None
    if m.group(1):
        return _direction(m.group(1)), Fraction(m.group(3)), _side(m.group(2))
    if m.group(6):
        return _direction(m.group(6)), Fraction(m.group(5)), _side(m.group(4))
    return _direction(m.group(7)), Fraction(m.group(9)), _side(m.group(8))


def _points_change(sent: str) -> Optional[tuple[str, Fraction, str]]:
    m = _POINTS_CHANGE_RE.search(sent)
    if not m:
        return None
    if m.group(1):
        return _direction(m.group(1)), Fraction(m.group(3)), _side(m.group(2))
    if m.group(6):
        return _direction(m.group(6)), Fraction(m.group(5)), _side(m.group(4))
    return _direction(m.group(7)), Fraction(m.group(9)), _side(m.group(8))


def _fraction_change(sent: str) -> Optional[tuple[str, Fraction, str, str]]:
    """(direction, fraction, side, words) for 'a fall of about a half' / 'fell by two-thirds'."""
    m = _FRACTION_CHANGE_RE.search(sent)
    if not m:
        return None
    word, qual, frac = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
    key = re.sub(r"^(?:a|one)\s+", "", frac.lower()).replace("-", " ")
    return _direction(word), _FRACTION_WORDS[key], _side(qual), frac


def _fold(sent: str) -> Optional[tuple[Fraction, str, str]]:
    """(factor, side, words) for 'doubled', 'doubling', 'halved', 'threefold', '2.5-fold'."""
    m = _FOLD_RE.search(sent)
    if not m:
        return None
    word = m.group(2).lower()
    factor = next((f for stem, f in _FOLD_STEMS.items() if word.startswith(stem)), None)
    if factor is None:
        factor = Fraction(m.group(3)) if m.group(3) else Fraction(_FOLD_WORDS[m.group(4).lower()])
    return factor, _side(m.group(1)), m.group(0).strip()


def extract_quant_checks(text: str, *, request_id: str, claim_id: str, tolerance: Fraction = Fraction(1, 20)) -> list[QuantCheck]:
    """Find sentences stating a from/to pair together with a derived figure and build an
    exact entailment problem for each. ``tolerance`` is the relative slack allowed for
    rounding (default 5 per cent of the computed value; see :data:`TOLERANCE_RULE`)."""
    checks: list[QuantCheck] = []
    n = 0
    before_after = [("before", "the earlier figure as stated"), ("after", "the later figure as stated")]
    for sent in _SENT_RE.split(text):
        ft = _FROM_TO_RE.search(sent)
        if not ft:
            continue
        u1, u2 = ft.group(2), ft.group(4)
        if not u1 and u2:
            u1 = u2  # shared-unit elision: 'from 15 to 45 million', 'from 3.2 to 24.9 per cent'
        if _year_like(ft.group(1), u1) and _year_like(ft.group(3), u2):
            continue  # 'from 1928 to 1930' is a date span, not a before/after pair
        a, b = _frac(ft.group(1), u1), _frac(ft.group(3), u2)
        shown_a, shown_b = f"{ft.group(1)} {u1 or ''}".strip(), f"{ft.group(3)} {u2 or ''}".strip()
        premises = [("BEFORE", {"op": "eq", "left": _v("before"), "right": _real(a)}, f"before = {shown_a}"), ("AFTER", {"op": "eq", "left": _v("after"), "right": _real(b)}, f"after = {shown_b}")]
        pts, pc, frac, fold = _points_change(sent), _pct_change(sent), _fraction_change(sent), _fold(sent)
        if pts and _is_pct(u1) and _is_pct(u2):
            # both figures are shares and the sentence states their difference in points: |after - before| = stated
            n += 1
            direction, stated, side = pts
            diff = {"op": "sub", "left": _v("after"), "right": _v("before")}
            if direction == "fall":
                diff = {"op": "neg", "arg": diff}
            checks.append(QuantCheck(f"quant-{n}", "points_change", sent.strip(), _problem(f"quant-points-{n}", claim_id, request_id,
                [("before", "the earlier share as stated (per cent)"), ("after", "the later share as stated (per cent)")], premises,
                ("STATED_POINTS", _within(diff, stated, tolerance, POINT_FLOOR, side), f"stated {direction} of {stated} percentage points against the computed difference")),
                rule=_rule_text(tolerance, POINT_FLOOR, side)))
        elif pc and a != 0:
            n += 1
            direction, stated, side = pc
            change = {"op": "mul", "args": [_real(Fraction(100)), {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(a)}]}
            if direction == "fall":
                change = {"op": "neg", "arg": change}
            checks.append(QuantCheck(f"quant-{n}", "percent_change", sent.strip(), _problem(f"quant-pct-{n}", claim_id, request_id, before_after, premises,
                ("STATED_CHANGE", _within(change, stated, tolerance, POINT_FLOOR, side), f"stated {direction} of {stated} per cent against the computed change")),
                rule=_rule_text(tolerance, POINT_FLOOR, side)))
        elif frac and a != 0:
            n += 1
            direction, stated, side, words = frac
            change = {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(a)}
            if direction == "fall":
                change = {"op": "neg", "arg": change}
            checks.append(QuantCheck(f"quant-{n}", "fraction_change", sent.strip(), _problem(f"quant-frac-{n}", claim_id, request_id, before_after, premises,
                ("STATED_FRACTION", _within(change, stated, tolerance, Fraction(0), side), f"stated {direction} of '{words}' (= {stated}) against the computed change")),
                rule=_rule_text(tolerance, Fraction(0), side)))
        elif fold and a != 0:
            n += 1
            factor, side, words = fold
            ratio = {"op": "div", "left": _v("after"), "right": _real(a)}
            checks.append(QuantCheck(f"quant-{n}", "fold_change", sent.strip(), _problem(f"quant-fold-{n}", claim_id, request_id, before_after, premises,
                ("STATED_FOLD", _within(ratio, factor, tolerance, Fraction(0), side), f"stated '{words}' (factor {factor}) against the computed ratio")),
                rule=_rule_text(tolerance, Fraction(0), side)))
    for sent in _SENT_RE.split(text):
        sh = _SHARE_RE.search(sent)
        if sh:
            n += 1
            pct, whole, part = Fraction(sh.group(1).replace(",", "")), _frac(sh.group(2), sh.group(3)), _frac(sh.group(4), sh.group(5))
            computed = {"op": "div", "left": {"op": "mul", "args": [_real(pct), _v("whole")]}, "right": _real(Fraction(100))}  # constant * variable: linear
            checks.append(QuantCheck(f"quant-{n}", "share", sent.strip(), _problem(f"quant-share-{n}", claim_id, request_id,
                [("pct", "stated percentage"), ("whole", "stated whole")],
                [("PCT", {"op": "eq", "left": _v("pct"), "right": _real(pct)}, "percentage"), ("WHOLE", {"op": "eq", "left": _v("whole"), "right": _real(whole)}, "whole")],
                ("STATED_PART", _within(computed, part, tolerance), f"stated part {sh.group(4)} {sh.group(5) or ''}".strip())),
                rule=_rule_text(tolerance, Fraction(0), "both")))
        tot = _TOTAL_RE.search(sent)
        if tot:
            n += 1
            x, y, z = _frac(tot.group(1), tot.group(2)), _frac(tot.group(3), tot.group(4)), _frac(tot.group(5), tot.group(6))
            s = {"op": "add", "args": [_v("x"), _v("y")]}
            checks.append(QuantCheck(f"quant-{n}", "total", sent.strip(), _problem(f"quant-total-{n}", claim_id, request_id,
                [("x", "first addend"), ("y", "second addend")],
                [("X", {"op": "eq", "left": _v("x"), "right": _real(x)}, "x"), ("Y", {"op": "eq", "left": _v("y"), "right": _real(y)}, "y")],
                ("STATED_TOTAL", _within(s, z, tolerance), f"stated total {tot.group(5)} {tot.group(6) or ''}".strip())),
                rule=_rule_text(tolerance, Fraction(0), "both")))
    return checks
