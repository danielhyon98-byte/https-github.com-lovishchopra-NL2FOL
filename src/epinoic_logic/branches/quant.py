"""Deterministic extraction of a report's own quantitative statements and formal
self-consistency checks on them. No model is involved: regular expressions find
figures the specialist stated, and the engine decides whether the derived figures
the specialist also stated actually follow (percentage changes, fold changes,
shares, totals, date ordering). A specialist that writes "rose from 1.4 million to
6 million, a threefold increase" is caught by arithmetic, not by opinion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from ..ir.schema import Problem

_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
_UNIT = r"(?:\s*(million|billion|thousand|per cent|percent|%|seats|votes|m|bn|k))?"
_FROM_TO_RE = re.compile(rf"\b(?:from|of)\s+(?:about|around|roughly|nearly|over|more than|almost)?\s*{_NUM}{_UNIT}\s+(?:to|and)\s+(?:about|around|roughly|nearly|over|more than|almost)?\s*{_NUM}{_UNIT}", re.IGNORECASE)
_PCT_CHANGE_RE = re.compile(r"(?:an?\s+)?(increase|rise|fall|decrease|decline|drop|growth)\s+of\s+(?:about|around|roughly|nearly|some)?\s*(\d+(?:\.\d+)?)\s*(?:per cent|percent|%)", re.IGNORECASE)
_FOLD_RE = re.compile(r"\b(doubled|trebled|tripled|quadrupled|halved|(\d+(?:\.\d+)?)-fold|(two|three|four|five|six|seven|eight|nine|ten)fold)\b", re.IGNORECASE)
_SHARE_RE = re.compile(rf"\b{_NUM}\s*(?:per cent|percent|%)\s+of\s+(?:the\s+)?(?:about|around|roughly)?\s*{_NUM}{_UNIT}\s*(?:[,(]|\bwas\b|\bis\b|\bor\b|\bthat is\b|\bi\.e\.)\s*(?:about|around|roughly|some)?\s*{_NUM}{_UNIT}", re.IGNORECASE)
_TOTAL_RE = re.compile(rf"{_NUM}{_UNIT}\s+(?:and|plus)\s+(?:[a-z][a-z ]{{0,40}}?\s)?{_NUM}{_UNIT}[^.;]{{0,60}}?(?:a total of|totalling|together|in total|making|giving|totals?)\s+(?:about|around|roughly)?\s*{_NUM}{_UNIT}", re.IGNORECASE)
_FOLD_WORDS = {"doubled": 2, "trebled": 3, "tripled": 3, "quadrupled": 4, "halved": Fraction(1, 2), "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_SCALE = {"million": 10**6, "m": 10**6, "billion": 10**9, "bn": 10**9, "thousand": 10**3, "k": 10**3}
_SENT_RE = re.compile(r"(?<=[.?!;])\s+")


@dataclass(frozen=True)
class QuantCheck:
    check_id: str
    kind: str                 # percent_change | fold_change | share | total
    sentence: str
    problem: Problem
    expected_if_consistent: str = "ENTAILED"


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


def _problem(pid: str, claim_id: str, request_id: str, symbols: list[tuple[str, str]], premises: list[tuple[str, dict, str]], conclusion: tuple[str, dict, str]) -> Problem:
    return Problem.model_validate({
        "problem_id": pid, "request_id": request_id, "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": n, "sort": "Real", "meaning": m} for n, m in symbols],
        "premises": [{"id": i, "expr": e, "label": l, "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}} for i, e, l in premises],
        "conclusion": {"id": conclusion[0], "expr": conclusion[1], "label": conclusion[2], "grounding": {"kind": "supplied_text", "verified": True}},
    })


def extract_quant_checks(text: str, *, request_id: str, claim_id: str, tolerance: Fraction = Fraction(1, 20)) -> list[QuantCheck]:
    """Find sentences stating a from/to pair together with a derived figure and build an
    exact entailment problem for each. ``tolerance`` is the relative slack allowed for
    rounded percentages (default 5 percent of the stated change)."""
    checks: list[QuantCheck] = []
    n = 0
    for sent in _SENT_RE.split(text):
        ft = _FROM_TO_RE.search(sent)
        if not ft:
            continue
        a, b = _frac(ft.group(1), ft.group(2)), _frac(ft.group(3), ft.group(4))
        pc = _PCT_CHANGE_RE.search(sent)
        fold = _FOLD_RE.search(sent)
        if pc and a != 0:
            n += 1
            stated = Fraction(pc.group(2))
            lo, hi = stated * (1 - tolerance), stated * (1 + tolerance)
            # conclusion: 100*|b-a|/a within [lo, hi]
            change = {"op": "mul", "args": [_real(Fraction(100)), {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(a)}]}
            if pc.group(1).lower() in ("fall", "decrease", "decline", "drop"):
                change = {"op": "neg", "arg": change}
            concl = {"op": "and", "args": [{"op": "ge", "left": change, "right": _real(lo)}, {"op": "le", "left": change, "right": _real(hi)}]}
            checks.append(QuantCheck(f"quant-{n}", "percent_change", sent.strip(), _problem(f"quant-pct-{n}", claim_id, request_id,
                [("before", "the earlier figure as stated"), ("after", "the later figure as stated")],
                [("BEFORE", {"op": "eq", "left": _v("before"), "right": _real(a)}, f"before = {ft.group(1)} {ft.group(2) or ''}".strip()), ("AFTER", {"op": "eq", "left": _v("after"), "right": _real(b)}, f"after = {ft.group(3)} {ft.group(4) or ''}".strip())],
                ("STATED_CHANGE", concl, f"stated {pc.group(1)} of {pc.group(2)} per cent (±{float(tolerance) * 100:.0f}% of that)"))))
        elif fold and a != 0:
            n += 1
            word = fold.group(1).lower()
            factor = _FOLD_WORDS.get(word) or (Fraction(fold.group(2)) if fold.group(2) else _FOLD_WORDS.get((fold.group(3) or "").lower()))
            if factor is None:
                continue
            factor = Fraction(factor)
            lo, hi = factor * (1 - tolerance), factor * (1 + tolerance)
            ratio = {"op": "div", "left": _v("after"), "right": _real(a)}
            concl = {"op": "and", "args": [{"op": "ge", "left": ratio, "right": _real(lo)}, {"op": "le", "left": ratio, "right": _real(hi)}]}
            checks.append(QuantCheck(f"quant-{n}", "fold_change", sent.strip(), _problem(f"quant-fold-{n}", claim_id, request_id,
                [("before", "the earlier figure as stated"), ("after", "the later figure as stated")],
                [("BEFORE", {"op": "eq", "left": _v("before"), "right": _real(a)}, "before"), ("AFTER", {"op": "eq", "left": _v("after"), "right": _real(b)}, "after")],
                ("STATED_FOLD", concl, f"stated '{fold.group(1)}' (factor {factor})"))))
    for sent in _SENT_RE.split(text):
        sh = _SHARE_RE.search(sent)
        if sh:
            n += 1
            pct, whole, part = Fraction(sh.group(1).replace(",", "")), _frac(sh.group(2), sh.group(3)), _frac(sh.group(4), sh.group(5))
            lo, hi = part * (1 - tolerance), part * (1 + tolerance)
            computed = {"op": "div", "left": {"op": "mul", "args": [_real(pct), _v("whole")]}, "right": _real(Fraction(100))}  # constant * variable: linear
            concl = {"op": "and", "args": [{"op": "ge", "left": computed, "right": _real(lo)}, {"op": "le", "left": computed, "right": _real(hi)}]}
            checks.append(QuantCheck(f"quant-{n}", "share", sent.strip(), _problem(f"quant-share-{n}", claim_id, request_id,
                [("pct", "stated percentage"), ("whole", "stated whole")],
                [("PCT", {"op": "eq", "left": _v("pct"), "right": _real(pct)}, "percentage"), ("WHOLE", {"op": "eq", "left": _v("whole"), "right": _real(whole)}, "whole")],
                ("STATED_PART", concl, f"stated part {sh.group(4)} {sh.group(5) or ''}".strip()))))
        tot = _TOTAL_RE.search(sent)
        if tot:
            n += 1
            x, y, z = _frac(tot.group(1), tot.group(2)), _frac(tot.group(3), tot.group(4)), _frac(tot.group(5), tot.group(6))
            lo, hi = z * (1 - tolerance), z * (1 + tolerance)
            s = {"op": "add", "args": [_v("x"), _v("y")]}
            concl = {"op": "and", "args": [{"op": "ge", "left": s, "right": _real(lo)}, {"op": "le", "left": s, "right": _real(hi)}]}
            checks.append(QuantCheck(f"quant-{n}", "total", sent.strip(), _problem(f"quant-total-{n}", claim_id, request_id,
                [("x", "first addend"), ("y", "second addend")],
                [("X", {"op": "eq", "left": _v("x"), "right": _real(x)}, "x"), ("Y", {"op": "eq", "left": _v("y"), "right": _real(y)}, "y")],
                ("STATED_TOTAL", concl, f"stated total {tot.group(5)} {tot.group(6) or ''}".strip()))))
    return checks
