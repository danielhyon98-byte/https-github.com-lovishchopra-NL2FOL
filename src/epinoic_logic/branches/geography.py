"""The Geography pack (D9/D10, decision D35): the subject's own arithmetic as engine problems, on the ``geography`` branch.

The branch keeps the generic parser (claim ids, roles and materiality as on the generic branch) and runs the shared core pack first
(with the shared self-certification gate, CORE-SELF-001); this pack adds deterministic readers whose statements the engine decides.
Every reader reads one sentence (with the sentence before it in the same paragraph for an operand the sentence does not state), over
a closed grammar of figures, scale words, currency signs, units of area and rates per 1,000; nothing is evaluated. Each determination
reaches the receipt through codes that already exist (INT-SUBJ-001 / INT-SUBJ-004 for a failed check, CORE-QNT-001 for a rate read
but not built, CORE-SRC-002 for a figure credited to an unsupplied map or graph):

========================  ======================================================================  ==========================
kind                      statement read                                                          failure
========================  ======================================================================  ==========================
``geo_density``           a density with its population and area (area units converted exactly)   INT-SUBJ-001
``geo_rate_per_thousand`` a crude rate with its count and population ('24 per 1,000')              INT-SUBJ-001
``geo_natural_increase``  birth and death rates per 1,000 with the natural increase (or growth)    INT-SUBJ-001
``geo_doubling_time``     a growth rate r % a year with a doubling time (69/r to 73/r, r <= 10)     INT-SUBJ-001
``geo_per_capita``        a total and a population with a figure per capita / person / head        INT-SUBJ-001
``geo_growth_rate``       V0 in Y0 to V1 in Y1 with an average annual growth rate (simple or        INT-SUBJ-001
                          compound reading; fails only when neither holds)
``geo_mean``              a mean of listed values                                                  INT-SUBJ-001
``geo_sampling``          systematic sampling: sites at an interval over a stated distance         INT-SUBJ-004
``geo_table_count``       a count of the rows of a supplied table ('the table shows ten sites')    INT-SUBJ-004
``supplied_figure``       a figure of a supplied attribute table (no year axis), by row and column INT-SUBJ-001 credited,
                                                                                                    INT-SUBJ-004 otherwise
``geo_case_consistency``  one case quantity stated twice with different values                    INT-SUBJ-004
``geo_significance``      a coefficient against a stated critical value and verdict                INT-SUBJ-001
``worked_arithmetic``     every worked equation, as on the generic branch                          as there
========================  ======================================================================  ==========================

Tolerance (arithmetic kinds): ``|C - S| <= h + tau * |C|``, h half a unit of the last digit written of the stated figure, tau 1 %
(5 % after an approximation word). Comparative bounds ('more than', 'under') turn the stated figure into a one-sided bound. Every
reader is bounded (statements per kind and per report, word lengths, table caps) and linear in the answer; questions are skipped.
A check proves a property of its encoding only: that the figures as written do or do not stand in the stated relation.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from ..translate.contracts import SpecialistReport, StructuralFinding, SuppliedText
from .base import FormalCheck

__all__ = ["GeographyPack", "decided_statements", "unknown_supports_findings"]

#: Bounds: statements read per kind and per report, and the answer's characters read.
MAX_PER_KIND = 64
MAX_PER_REPORT = 200
MAX_TEXT = 200_000
#: Tolerances: 1 per cent of the computed value, 5 per cent after an approximation word (grounded_figures.RATIO_APPROX).
TAU = Fraction(1, 100)
TAU_APPROX = Fraction(1, 20)
#: Doubling time: the band of the rule of 70, the rule of 72 and exact compounding for a rate of at most 10 per cent a year.
DOUBLING_LOW = Fraction(69)
DOUBLING_HIGH = Fraction(73)
DOUBLING_MAX_RATE = Fraction(10)
#: The compound reading of an average annual growth rate is built for at most this many years (the IR's whole-power limit).
MAX_COMPOUND_YEARS = 200

_GROUND = {"kind": "supplied_text", "verified": True}
_RULE = "tolerance: |computed - stated| <= half a unit of the last digit written + {tau}% of the computed value"

# ------------------------------------------------------------------------------------------------------------------ figures
_NUM = r"\d{1,3}(?:,\d{3})++(?:\.\d{1,8})?|\d{1,12}(?:\.\d{1,8})?"
_SCALE_WORDS = {"thousand": Fraction(10**3), "million": Fraction(10**6), "billion": Fraction(10**9), "trillion": Fraction(10**12),
                "m": Fraction(10**6), "bn": Fraction(10**9), "k": Fraction(10**3)}
_SCALE = r"(?:\s*+(?P<{g}s>thousand|million|billion|trillion)\b|(?<=\d)(?P<{g}c>bn|m|k)\b(?=[^²2\w]|$))?"
_APPROX_RE = re.compile(r"(?:\b(?:about|around|roughly|approximately|approx\.|nearly|almost|some|c\.|ca\.|circa)|~)\s*+$", re.IGNORECASE)
_LOWER_RE = re.compile(r"\b(?:more\s+than|over|at\s+least|above|in\s+excess\s+of)\s*+$", re.IGNORECASE)
_UPPER_RE = re.compile(r"\b(?:fewer\s+than|less\s+than|under|up\s+to|at\s+most|below)\s*+$", re.IGNORECASE)
_WORD_NUMBERS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                                            "sixteen seventeen eighteen nineteen twenty".split())}
_WORD_NUMBER = r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"


def _num_re(g: str, *, currency: bool = False, scale: bool = True) -> str:
    cur = rf"(?:(?P<{g}cur>[$£€¥])\s*+)?" if currency else ""  # blanks only after a sign: a blank run is never rescanned
    sc = _SCALE.format(g=g) if scale else ""
    return rf"(?<![\d.,]){cur}(?P<{g}>{_NUM})(?![\d,]\d|\.\d){sc}"


@dataclass(frozen=True)
class Fig:
    """A stated figure: its value (scale applied), as written, half a unit of its last digit (scaled), its qualifier."""
    value: Fraction
    shown: str
    half: Fraction
    approx: bool = False
    side: str = "both"   # 'lower' (more than X: X is a lower bound), 'upper' (under X), 'both'
    currency: str = ""
    start: int = 0
    end: int = 0


def _fig(m: "re.Match[str]", g: str, text: str) -> Fig:
    """The figure of group ``g`` of ``m`` (with its optional scale-word group ``<g>s``, scale-letter group ``<g>c`` and currency group
    ``<g>cur``), read in ``text``: its approximation word or comparative bound is the text right before it."""
    raw = m.group(g)
    digits = raw.replace(",", "")
    places = len(digits.split(".")[1]) if "." in digits else 0
    word = _grp(m, f"{g}s") or _grp(m, f"{g}c")
    scale = _SCALE_WORDS[word.lower()] if word else Fraction(1)
    cur = _grp(m, f"{g}cur") or ""
    start = m.start(g)
    lead = m.start(f"{g}cur") if cur else start
    before = text[max(0, lead - 40):lead]
    approx = _APPROX_RE.search(before) is not None
    side = "lower" if _LOWER_RE.search(before) else "upper" if _UPPER_RE.search(before) else "both"
    shown = f"{cur}{raw}" + (f" {_grp(m, f'{g}s')}" if _grp(m, f"{g}s") else "") + (_grp(m, f"{g}c") or "")
    return Fig(Fraction(digits) * scale, shown, Fraction(1, 2) / Fraction(10) ** places * scale, approx, side, cur, start, m.end())


def _grp(m: "re.Match[str]", name: str) -> Optional[str]:
    try:
        return m.group(name)
    except IndexError:
        return None


def _real(x: Fraction) -> dict:
    return {"op": "real", "value": f"{x.numerator}/{x.denominator}" if x.denominator != 1 else str(x.numerator)}


def _var(name: str) -> dict:
    return {"op": "var", "name": name}


def _fmt(x: Fraction) -> str:
    from .quant import _fmt as fmt
    return fmt(x)


def _abs(e: dict) -> dict:
    from .quant import _abs as absolute
    return absolute(e)


def band(expr: dict, stated: Fig, tau: Optional[Fraction] = None) -> dict:
    """``expr`` (the computed value) against the stated figure: ``|expr - S| <= h + tau |expr|`` (both sides), or the one-sided bound a
    comparative word sets (more than S: ``expr >= S - h``; under S: ``expr <= S + h``)."""
    t = tau if tau is not None else (TAU_APPROX if stated.approx else TAU)
    diff = {"op": "sub", "left": expr, "right": _real(stated.value)}
    if stated.side == "lower":
        return {"op": "ge", "left": diff, "right": _real(-stated.half)}
    if stated.side == "upper":
        return {"op": "le", "left": diff, "right": _real(stated.half)}
    slack = {"op": "add", "args": [_real(stated.half), {"op": "mul", "args": [_real(t), _abs(expr)]}]}
    return {"op": "le", "left": _abs(diff), "right": slack}


def make_check(report: SpecialistReport, *, check_id: str, kind: str, inputs: list[tuple[str, Fraction, str]], conclusion: dict, label: str,
               description: str, claim_ids: tuple[str, ...], severity: str = "error", defect: Optional[str] = None, sort: str = "Real") -> FormalCheck:
    """One engine problem: each input a symbol fixed by a premise (grounded in the answer as written or a supplied text, verified: a
    deterministic reading), the stated relation the conclusion. Linear (constant divisors only)."""
    from ..ir.schema import Problem
    symbols, premises = [], []
    for name, value, meaning in inputs:
        symbols.append({"name": name, "sort": sort, "meaning": meaning[:1000]})
        right = _real(value) if sort == "Real" else {"op": "int", "value": str(int(value))}
        premises.append({"id": name.upper(), "expr": {"op": "eq", "left": _var(name), "right": right}, "label": f"{meaning} = {_fmt(value)}"[:1000],
                         "grounding": _GROUND})
    prob = {"problem_id": f"{check_id}-{report.report_id}"[:128], "request_id": report.request_id, "claim_id": f"{report.report_id}:{check_id}"[:128],
            "query": "entailment", "symbols": symbols, "premises": premises, "conclusion": {"id": kind.upper(), "expr": conclusion, "label": label[:1000]}}
    return FormalCheck(check_id=check_id, kind=kind, description=description[:1500], problem=Problem.model_validate(prob), claim_ids=claim_ids[:8],
                       policy="linear", failure_severity="error" if severity == "error" else "warning", defect=defect)


def unknown_supports_findings(report: SpecialistReport) -> list[StructuralFinding]:
    from .packs import unknown_supports
    return unknown_supports(report)


# ------------------------------------------------------------------------------------------------------------------ sentences
_QUESTION_END_RE = re.compile(r"\?\s*+[)\]\"'”’»]*+\s*+$")


@dataclass(frozen=True)
class _Sentence:
    paragraph: int
    number: int
    text: str
    before: str          # the sentence before it in the same paragraph ('' when none)


def _sentences(text: str) -> list[_Sentence]:
    """The answer's sentences (the shared splitter, each cut at line breaks too), skipping questions and table rows; bounded."""
    from .packs import _sentences_with_paragraph
    out: list[_Sentence] = []
    prev_para, prev = -1, ""
    for pi, si, sent, _para in _sentences_with_paragraph(text[:MAX_TEXT]):
        for line in sent.split("\n"):
            line = line.strip()
            if not line:
                continue
            if pi != prev_para:
                prev = ""
                prev_para = pi
            if "|" in line or _QUESTION_END_RE.search(line):
                prev = "" if "|" in line else prev
                continue
            out.append(_Sentence(pi, si, line, prev))
            prev = line
            if len(out) >= 4000:
                return out
    return out


def _claims(report: SpecialistReport, statement: str, phrase: str) -> tuple[str, ...]:
    from .packs import _claims_for_statement, _claims_mentioning
    return tuple(_claims_for_statement(report, statement, phrase) or _claims_for_statement(report, phrase, phrase) or _claims_mentioning(report, statement))


def _excerpt(text: str, width: int = 220) -> str:
    t = " ".join(text.split())
    return t if len(t) <= width else t[:width - 3] + "..."


# ------------------------------------------------------------------------------------------------------------------ readers
_AREA_UNITS = {"km²": Fraction(1), "km2": Fraction(1), "km^2": Fraction(1), "sq km": Fraction(1), "sq. km": Fraction(1), "square kilometre": Fraction(1),
               "square kilometres": Fraction(1), "square kilometer": Fraction(1), "square kilometers": Fraction(1), "ha": Fraction(1, 100),
               "hectare": Fraction(1, 100), "hectares": Fraction(1, 100), "m²": Fraction(1, 10**6), "m2": Fraction(1, 10**6),
               "square metre": Fraction(1, 10**6), "square metres": Fraction(1, 10**6), "square meter": Fraction(1, 10**6), "square meters": Fraction(1, 10**6)}
_AREA = r"(?:km²|km2|km\^2|sq\.?\s?km|square\s+kilomet(?:re|er)s?|hectares?|ha|m²|m2|square\s+met(?:re|er)s?)(?![\w²])"
_UNCONVERTED_AREA = r"(?:square\s+miles?|sq\.?\s?mi|mi²|acres?)(?![\w²])"
_PEOPLE = r"(?:people|persons|inhabitants|residents)"
_DENSITY_RE = re.compile(_num_re("d") + rf"\s*+(?:{_PEOPLE}\s*+)?(?:per|/|an?|every)\s*+(?:(?P<du>{_AREA})|(?P<dx>{_UNCONVERTED_AREA}))", re.IGNORECASE)
_AREA_FIG_RE = re.compile(_num_re("a") + rf"\s*+(?:(?P<au>{_AREA})|(?P<ax>{_UNCONVERTED_AREA}))", re.IGNORECASE)
_POP_FIG_RE = re.compile(_num_re("p") + rf"\s*+{_PEOPLE}\b(?!\s*+(?:per|/))|\bpopulation\s++(?:of\s++|is\s++|was\s++)?(?:about\s++|around\s++|roughly\s++|some\s++)?"
                         + _num_re("q"), re.IGNORECASE)
_PER_AREA_RE = re.compile(rf"\b(?:per|/)\s*+{_AREA}", re.IGNORECASE)
_DENSITY_WORD_RE = re.compile(r"\bdensit(?:y|ies)\b", re.IGNORECASE)


def _unit_key(u: str) -> str:
    return " ".join(u.lower().replace(".", "").split())


def _area_factor(u: str) -> Optional[Fraction]:
    k = _unit_key(u)
    return _AREA_UNITS.get(k) or _AREA_UNITS.get(k.replace("sq km", "sq km"))


def _pop_figs(text: str) -> list[Fig]:
    out = []
    for m in _POP_FIG_RE.finditer(text):
        out.append(_fig(m, "p", text) if m.group("p") else _fig(m, "q", text))
    return out


@dataclass
class _Ctx:
    report: SpecialistReport
    checks: list
    findings: list
    decided: set
    counts: dict
    #: statements the bounds left unread, by kind (attack round 3: a statement past MAX_PER_KIND or MAX_PER_REPORT is named on
    #: the receipt by :func:`_bound_finding`, never dropped silently)
    dropped: dict = field(default_factory=dict)

    def room(self, kind: str) -> bool:
        return self.counts.get(kind, 0) < MAX_PER_KIND and len(self.checks) < MAX_PER_REPORT

    def skip(self, kind: str, n: int = 1) -> None:
        self.dropped[kind] = self.dropped.get(kind, 0) + n

    def add(self, kind: str, build) -> None:
        if not self.room(kind):
            self.skip(kind)
            return
        self.counts[kind] = self.counts.get(kind, 0) + 1
        n = sum(1 for c in self.checks if c.kind == kind) + 1
        self.checks.append(build(f"geography-{kind.replace('geo_', '').replace('_', '-')}-{n}"))

    def undecided(self, s: _Sentence, phrase: str, reason: str) -> None:
        if sum(1 for f in self.findings if f.code == "CORE-QNT-001") >= MAX_PER_KIND:
            self.skip("undecided")
            return
        self.findings.append(StructuralFinding(
            code="CORE-QNT-001", severity="warning", claim_ids=list(_claims(self.report, s.text, phrase))[:8],
            message=(f"paragraph {s.paragraph}, sentence {s.number} states a derived figure ('{_excerpt(phrase, 120)}') that could not be checked: "
                     f"{reason}; the stated arithmetic was not checked"),
            rule_source="Geography pack: a Geography rate read but not built is named undecided"))


def _density(ctx: _Ctx, s: _Sentence) -> None:
    if not (_DENSITY_WORD_RE.search(s.text) or _PER_AREA_RE.search(s.text)):
        return
    stated = list(_DENSITY_RE.finditer(s.text))
    if not stated:
        return
    m = stated[-1]
    d = _fig(m, "d", s.text)
    if m.group("dx"):
        ctx.undecided(s, m.group(0), "the density's area unit is not one the pack converts (km², ha, m²)")
        return
    areas = [x for x in _AREA_FIG_RE.finditer(s.text) if x.start() != m.start() and not re.search(r"(?:per|/)\s*+$", s.text[max(0, x.start() - 6):x.start()])
             and not (m.start() <= x.start() < m.end())]
    pops = [p for p in _pop_figs(s.text) if not (m.start() <= p.start < m.end())]
    if not areas and s.before:
        areas = [x for x in _AREA_FIG_RE.finditer(s.before) if not re.search(r"(?:per|/)\s*+$", s.before[max(0, x.start() - 6):x.start()])]
        src_a = s.before
    else:
        src_a = s.text
    if not pops and s.before:
        pops = _pop_figs(s.before)
    if len(areas) != 1 or len(pops) != 1:
        return
    am = areas[0]
    if am.group("ax"):
        ctx.undecided(s, m.group(0), "the area's unit is not one the pack converts (km², ha, m²)")
        return
    a = _fig(am, "a", src_a)
    p = pops[0]
    fa, fd = _area_factor(am.group("au")), _area_factor(m.group("du"))
    if not fa or not fd or a.value == 0:
        return
    # D (per the density's unit) = P / (A * fa / fd)
    divisor = a.value * fa / fd
    phrase = m.group(0)
    ctx.decided.add(" ".join(s.text.split()))
    expr = {"op": "div", "left": _var("population"), "right": _real(divisor)}
    ctx.add("geo_density", lambda cid: make_check(
        ctx.report, check_id=cid, kind="geo_density", inputs=[("population", p.value, f"the population stated ({p.shown})")],
        conclusion=band(expr, d), label=f"stated density {d.shown} per {m.group('du')} against population / area ({p.shown} / {a.shown} {am.group('au')})",
        description=f"{_excerpt(s.text)} [population density = population / area, the area converted to the density's unit; {_RULE.format(tau=5 if d.approx else 1)}]",
        claim_ids=_claims(ctx.report, s.text, phrase), defect="stem_arithmetic_slip"))


_PER_THOUSAND = r"(?:per\s*+(?:1,000|1000|thousand)|‰)"
_RATE_RE = re.compile(_num_re("r", scale=False) + rf"\s*+{_PER_THOUSAND}", re.IGNORECASE)
_EVENT = r"(?:live\s+births|births|infant\s+deaths|deaths|migrants|immigrants|emigrants|arrivals|departures)"
_EVENT_RE = re.compile(_num_re("n") + rf"\s++(?P<ev>{_EVENT})\b|\b(?P<ev2>{_EVENT})\s*+:\s*+" + _num_re("o"), re.IGNORECASE)
_LIVE_BIRTHS_RE = re.compile(_num_re("l") + r"\s++live\s++births\b", re.IGNORECASE)


#: A rate written in per cent ("a crude birth rate of 2.4%"), read like a rate per 1,000 with 100 for 1,000 (attack round 3, ge-t16).
_RATE_PCT_RE = re.compile(r"\brate\b[^.;\d]{0,30}?" + _num_re("r", scale=False) + r"\s*+(?:%|per\s*+cent\b|percent\b)", re.IGNORECASE)


def _rate_per_thousand(ctx: _Ctx, s: _Sentence) -> None:
    rates = list(_RATE_RE.finditer(s.text))
    base = 1000
    if not rates:
        rates = list(_RATE_PCT_RE.finditer(s.text))
        base = 100
    # (a death toll stated per 1,000, "the death toll was 3 per 1,000", is a rate too: attack round 3)
    if not rates or not re.search(r"\brate\b|‰|\btoll\b", s.text, re.IGNORECASE):
        return
    events = list(_EVENT_RE.finditer(s.text))
    if any("infant" in (e.group("ev") or e.group("ev2") or "").lower() for e in events):
        events = [e for e in events if "live" not in (e.group("ev") or e.group("ev2") or "").lower()]  # live births are the denominator
    if len(events) != 1:
        return
    e = events[0]
    ev = (e.group("ev") or e.group("ev2") or "").lower()
    n = _fig(e, "n", s.text) if e.group("n") else _fig(e, "o", s.text)
    if "infant" in ev:
        dens = [_fig(x, "l", s.text) for x in _LIVE_BIRTHS_RE.finditer(s.text)]
        what = "live births"
    else:
        dens = [p for p in _pop_figs(s.text)]
        what = "population"
    if len(dens) != 1 or dens[0].value == 0 or len(rates) != 1:
        return
    p = dens[0]
    r = _fig(rates[0], "r", s.text)
    ctx.decided.add(" ".join(s.text.split()))
    expr = {"op": "mul", "args": [_real(Fraction(base)), {"op": "div", "left": _var("count"), "right": _real(p.value)}]}
    per = "1,000" if base == 1000 else "100 (per cent)"
    ctx.add("geo_rate_per_thousand", lambda cid: make_check(
        ctx.report, check_id=cid, kind="geo_rate_per_thousand", inputs=[("count", n.value, f"the {ev} stated ({n.shown})")],
        conclusion=band(expr, r), label=f"stated rate {r.shown} per {per} against {base} x {n.shown} / {p.shown}",
        description=f"{_excerpt(s.text)} [a rate per {per} = {base} x count / {what}; {_RULE.format(tau=5 if r.approx else 1)}]",
        claim_ids=_claims(ctx.report, s.text, rates[0].group(0)), defect="stem_arithmetic_slip"))


_RATE_LABEL = r"\s*+(?:is|of|was|were|stands\s+at|=|:)?\s*+(?:about\s+|around\s+|roughly\s+|approximately\s+)?"
_BIRTH_RE = re.compile(r"\b(?:crude\s+)?birth\s+rate" + _RATE_LABEL + _num_re("b", scale=False) + rf"\s*+{_PER_THOUSAND}", re.IGNORECASE)
_DEATH_RE = re.compile(r"\b(?:crude\s+)?death\s+rate" + _RATE_LABEL + _num_re("d", scale=False) + rf"\s*+{_PER_THOUSAND}", re.IGNORECASE)
_MIGRATION_RE = re.compile(r"\bnet\s+migration(?:\s+rate)?" + _RATE_LABEL + r"(?P<sg>[−-])?" + _num_re("m", scale=False) + rf"\s*+{_PER_THOUSAND}", re.IGNORECASE)
_NI_RE = re.compile(r"\b(?P<w>natural\s+(?:increase|growth|decrease)|(?:population\s+)?growth)(?:\s+rate)?" + _RATE_LABEL + r"(?P<sg>[−-])?"
                    + _num_re("k", scale=False) + rf"\s*+(?P<u>%|per\s*+cent\b|percent\b|{_PER_THOUSAND})", re.IGNORECASE)


def _natural_increase(ctx: _Ctx, s: _Sentence) -> None:
    b, d = _BIRTH_RE.search(s.text), _DEATH_RE.search(s.text)
    if b is None or d is None:
        return
    for ni in _NI_RE.finditer(s.text):
        k = _fig(ni, "k", s.text)
        if ni.group("sg"):
            k = Fig(-k.value, "−" + k.shown, k.half, k.approx, k.side, k.currency, k.start, k.end)
        word = ni.group("w").lower()
        mig = _MIGRATION_RE.search(s.text)
        if word.endswith("growth") and not word.startswith("natural") and mig is None:
            continue
        if word.startswith("natural") and "decrease" in word:
            k = Fig(-abs(k.value), k.shown, k.half, k.approx, k.side)
        bv, dv = _fig(b, "b", s.text), _fig(d, "d", s.text)
        inputs = [("birth_rate", bv.value, f"the birth rate per 1,000 ({bv.shown})"), ("death_rate", dv.value, f"the death rate per 1,000 ({dv.shown})")]
        expr: dict = {"op": "sub", "left": _var("birth_rate"), "right": _var("death_rate")}
        what = "birth rate - death rate"
        if not word.startswith("natural") and mig is not None:
            mv = _fig(mig, "m", s.text)
            sign = -1 if mig.group("sg") else 1
            inputs.append(("migration", sign * mv.value, f"the net migration rate per 1,000 ({'−' if sign < 0 else ''}{mv.shown})"))
            expr = {"op": "add", "args": [expr, _var("migration")]}
            what += " + net migration rate"
        per_cent = "%" in ni.group("u") or "cent" in ni.group("u").lower()
        if per_cent:
            expr = {"op": "div", "left": expr, "right": _real(Fraction(10))}
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_natural_increase", lambda cid, inputs=inputs, expr=expr, k=k, per_cent=per_cent, what=what, ni=ni: make_check(
            ctx.report, check_id=cid, kind="geo_natural_increase", inputs=inputs, conclusion=band(expr, k),
            label=f"stated {ni.group('w')} {k.shown}{'%' if per_cent else ' per 1,000'} against ({what}){' / 10' if per_cent else ''}",
            description=(f"{_excerpt(s.text)} [{ni.group('w')} = {what} (per 1,000){'; in per cent, divided by 10' if per_cent else ''}; "
                         f"{_RULE.format(tau=5 if k.approx else 1)}]"),
            claim_ids=_claims(ctx.report, s.text, ni.group(0)), defect="stem_arithmetic_slip"))
        return


_GROWTH_RATE_RE = re.compile(r"\b(?:growth\s+rate\s+(?:of|is|was|=)?|growing\s+at|grows\s+at|grew\s+at|growth\s+of|increasing\s+at|rising\s+at|grows\s+by|growing\s+by)\s*+"
                             r"(?:about\s+|around\s+|roughly\s+|approximately\s+)?" + _num_re("r", scale=False)
                             + r"\s*+(?:%|per\s*+cent\b|percent\b)\s*+(?:a|per|each|every)\s++(?:year|annum)\b", re.IGNORECASE)
_DOUBLE_RE = re.compile(r"\b(?:doubl(?:es?|ed|ing)\s+(?:in|within|after|every)|doubling\s+time\s+(?:of|is|was|=)?)\s*+"
                        r"(?:about\s+|around\s+|roughly\s+|approximately\s+|nearly\s+|just\s+over\s+|over\s+|under\s+|less\s+than\s+|more\s+than\s+)?"
                        + _num_re("t", scale=False) + r"\s*+years?\b", re.IGNORECASE)


def _doubling(ctx: _Ctx, s: _Sentence) -> None:
    g, dbl = _GROWTH_RATE_RE.search(s.text), _DOUBLE_RE.search(s.text)
    if g is None or dbl is None:
        return
    r = _fig(g, "r", s.text)
    t = _fig(dbl, "t", s.text)
    if r.value <= 0:
        return
    if r.value > DOUBLING_MAX_RATE:
        ctx.undecided(s, dbl.group(0), f"the growth rate of {r.shown}% a year is outside the rule's band (at most {DOUBLING_MAX_RATE}% a year)")
        return
    lo, hi = DOUBLING_LOW / r.value - t.half, DOUBLING_HIGH / r.value + t.half
    conclusion = {"op": "and", "args": [{"op": "ge", "left": _var("doubling"), "right": _real(lo)}, {"op": "le", "left": _var("doubling"), "right": _real(hi)}]}
    if t.side == "lower":
        conclusion = {"op": "ge", "left": _real(hi), "right": _var("doubling")}
    elif t.side == "upper":
        conclusion = {"op": "le", "left": _real(lo), "right": _var("doubling")}
    ctx.decided.add(" ".join(s.text.split()))
    ctx.add("geo_doubling_time", lambda cid: make_check(
        ctx.report, check_id=cid, kind="geo_doubling_time", inputs=[("doubling", t.value, f"the doubling time stated in years ({t.shown})")],
        conclusion=conclusion, label=f"stated doubling time {t.shown} years at {r.shown}% a year within 69/r to 73/r years",
        description=(f"{_excerpt(s.text)} [doubling time at r% a year lies between 69/r and 73/r years (the rule of 70, the rule of 72 and exact "
                     f"compounding agree within this band for r up to 10), widened by half a unit of the last digit written]"),
        claim_ids=_claims(ctx.report, s.text, dbl.group(0)), defect="stem_arithmetic_slip"))


_FOLD_WORDS = {"twofold": 2, "threefold": 3, "fourfold": 4, "fivefold": 5, "sixfold": 6, "sevenfold": 7, "eightfold": 8, "ninefold": 9,
               "tenfold": 10, "two-fold": 2, "three-fold": 3, "four-fold": 4, "five-fold": 5, "six-fold": 6, "ten-fold": 10}
#: An n-fold word with the ratio the same sentence works out beside it ("a threefold increase (16.2 ÷ 5.4 = 3.0)"): the word names the
#: ratio's value, so a fold word that differs from the worked ratio is a slip (attack round 2 of c3b: "fourfold ... = 3.0" passed).
_FOLD_RE = re.compile(r"\b(?P<w>(?:two|three|four|five|six|seven|eight|nine|ten)-?fold|(?P<d>\d{1,3})-fold)\b[^.;\n]{0,60}?"
                      r"(?P<a>\d{1,9}(?:\.\d{1,6})?)\s*+(?:÷|/)\s*+(?P<b>\d{1,9}(?:\.\d{1,6})?)\s*+=\s*+(?P<v>\d{1,9}(?:\.\d{1,6})?)",
                      re.IGNORECASE)


def _fold(ctx: _Ctx, s: _Sentence) -> None:
    m = _FOLD_RE.search(s.text)
    if m is None:
        return
    word = m.group("w").casefold()
    n = Fraction(int(m.group("d"))) if m.group("d") else Fraction(_FOLD_WORDS.get(word, 0))
    if not n:
        return
    v = Fraction(m.group("v"))
    places = len(m.group("v").split(".")[1]) if "." in m.group("v") else 0
    half = Fraction(1, 2 * 10 ** places)
    ctx.decided.add(" ".join(s.text.split()))
    ctx.add("geo_fold", lambda cid: make_check(
        ctx.report, check_id=cid, kind="geo_fold", inputs=[("ratio", v, f"the ratio the sentence works out ({m.group('v')})")],
        conclusion={"op": "and", "args": [{"op": "ge", "left": _var("ratio"), "right": _real(n - half)},
                                          {"op": "le", "left": _var("ratio"), "right": _real(n + half)}]},
        label=f"'{m.group('w')}' against the worked ratio {m.group('a')} ÷ {m.group('b')} = {m.group('v')}",
        description=(f"{_excerpt(s.text)} [an n-fold change names the ratio of the new value to the old one: the word's n equals the ratio "
                     f"the sentence works out, within half a unit of its last digit]"),
        claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


_PER_CAPITA_RE = re.compile(r"\bper\s++(?:capita|person|head)\s*+(?:of|is|was|=|:|,|at)?\s*+(?:about\s+|around\s+|roughly\s+|approximately\s+)?"
                            + _num_re("x", currency=True)
                            + r"|" + _num_re("y", currency=True) + r"\s++(?:per\s++(?:capita|person|head)|a\s++head)\b", re.IGNORECASE)
_TOTAL_RE = re.compile(_num_re("v", currency=True), re.IGNORECASE)


def _per_capita(ctx: _Ctx, s: _Sentence) -> None:
    pcs = list(_PER_CAPITA_RE.finditer(s.text))
    if len(pcs) != 1:
        return
    pm = pcs[0]
    x = _fig(pm, "x", s.text) if pm.group("x") else _fig(pm, "y", s.text)
    pops = [p for p in _pop_figs(s.text) if not (pm.start() <= p.start < pm.end())]
    if len(pops) != 1 or pops[0].value == 0:
        return
    p = pops[0]
    totals = [_fig(m, "v", s.text) for m in _TOTAL_RE.finditer(s.text) if m.group("vcur") and not (pm.start() <= m.start("v") < pm.end())]
    if x.currency:
        totals = [t for t in totals if t.currency == x.currency]
    if len(totals) != 1:
        return
    tot = totals[0]
    ctx.decided.add(" ".join(s.text.split()))
    expr = {"op": "div", "left": _var("total"), "right": _real(p.value)}
    ctx.add("geo_per_capita", lambda cid: make_check(
        ctx.report, check_id=cid, kind="geo_per_capita", inputs=[("total", tot.value, f"the total stated ({tot.shown})")],
        conclusion=band(expr, x), label=f"stated figure per capita {x.shown} against {tot.shown} / {p.shown}",
        description=f"{_excerpt(s.text)} [a figure per capita = total / population, scale words applied; {_RULE.format(tau=5 if x.approx else 1)}]",
        claim_ids=_claims(ctx.report, s.text, pm.group(0)), defect="stem_arithmetic_slip"))


_YEAR = r"(?P<{g}>1[89]\d{{2}}|20\d{{2}})"
_FROM_TO_RE = re.compile(r"\bfrom\s++(?:about\s++)?" + _num_re("v0") + r"(?:\s++[a-z]{1,20}){0,3}?\s++in\s++" + _YEAR.format(g="y0")
                         + r"\s++to\s++(?:about\s++)?" + _num_re("v1") + r"(?:\s++[a-z]{1,20}){0,3}?\s++in\s++" + _YEAR.format(g="y1") + r"\b", re.IGNORECASE)
_ANNUAL_RE = re.compile(r"\b(?:average\s+)?annual\s+(?:average\s+)?(?:population\s+)?growth(?:\s+rate)?\s*+(?:of|is|was|=|:)?\s*+(?:about\s+|around\s+|roughly\s+)?"
                        + _num_re("g", scale=False) + r"\s*+(?:%|per\s*+cent\b|percent\b)"
                        r"|\b(?:grew|rose|increased|growing)\s+(?:by\s+)?(?:an\s+average\s+of\s+|on\s+average\s+)?(?:about\s+)?" + _num_re("h", scale=False)
                        + r"\s*+(?:%|per\s*+cent\b|percent\b)\s*+(?:a|per|each)\s++year\b", re.IGNORECASE)


def _growth_rate(ctx: _Ctx, s: _Sentence) -> None:
    ft, an = _FROM_TO_RE.search(s.text), _ANNUAL_RE.search(s.text)
    if ft is None or an is None:
        return
    v0, v1 = _fig(ft, "v0", s.text), _fig(ft, "v1", s.text)
    g = _fig(an, "g", s.text) if an.group("g") else _fig(an, "h", s.text)
    n = int(ft.group("y1")) - int(ft.group("y0"))
    if n <= 0 or v0.value <= 0:
        return
    simple = {"op": "mul", "args": [_real(Fraction(100)), {"op": "div", "left": {"op": "sub", "left": _var("later"), "right": _var("earlier")},
                                                           "right": _real(v0.value * n)}]}
    options = [band(simple, g)]
    note = "the simple reading (V1 - V0) / V0 / n"
    if n <= MAX_COMPOUND_YEARS:
        lo_rate, hi_rate = (g.value - g.half) / 100, (g.value + g.half) / 100
        tau = TAU_APPROX if g.approx else TAU
        # the bounds of (1 + g)^n, rounded outward to 12 decimals (the IR's literals are at most 40 digits; the band only widens)
        lo_f = Fraction(math.floor((1 + lo_rate) ** n * 10**12), 10**12)
        hi_f = Fraction(math.ceil((1 + hi_rate) ** n * 10**12), 10**12)
        compound = {"op": "and", "args": [
            {"op": "le", "left": {"op": "mul", "args": [_real(lo_f), _var("earlier")]}, "right": {"op": "mul", "args": [_real(1 + tau), _var("later")]}},
            {"op": "ge", "left": {"op": "mul", "args": [_real(hi_f), _var("earlier")]}, "right": {"op": "mul", "args": [_real(1 - tau), _var("later")]}}]}
        options.append(compound)
        note += " or the compound reading V0 (1 + g)^n = V1"
    else:
        note += f"; the compound reading was not built ({n} years is beyond the whole-power limit of {MAX_COMPOUND_YEARS})"
    ctx.decided.add(" ".join(s.text.split()))
    ctx.add("geo_growth_rate", lambda cid: make_check(
        ctx.report, check_id=cid, kind="geo_growth_rate",
        inputs=[("earlier", v0.value, f"the figure in {ft.group('y0')} ({v0.shown})"), ("later", v1.value, f"the figure in {ft.group('y1')} ({v1.shown})")],
        conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
        label=f"stated average annual growth {g.shown}% from {v0.shown} ({ft.group('y0')}) to {v1.shown} ({ft.group('y1')})",
        description=f"{_excerpt(s.text)} [{note}; either reading holding is enough]",
        claim_ids=_claims(ctx.report, s.text, an.group(0)), defect="stem_arithmetic_slip"))


_MEAN_RE = re.compile(r"\b(?:mean|average)\b(?:\s++of)?(?:\s++the)?(?:\s++(?P<n>" + _WORD_NUMBER + r"|\d{1,2})(?=\s++[a-z]))?(?:\s++[a-z]{1,20}){0,3}?\s*+[(:]?\s*+"
                      # (a list closed by its bracket needs no "and": "(24, 22, 23, ..., 9, 11)", attack round 3)
                      r"(?P<list>(?:" + _NUM + r")(?:\s*+,\s*+(?:" + _NUM + r")){0,30}+(?:\s*+,?\s*+(?:and|&)\s++(?:" + _NUM + r")|(?=\s*+\))))"
                      r"(?:\s++[a-z]{1,20}){0,2}?\s*+\)?\s*+(?:,|is|was|=|:|gives|equals|of)\s*+(?:about\s+|around\s+|roughly\s+|approximately\s+)?"
                      + _num_re("m", scale=False), re.IGNORECASE)
_LIST_NUM_RE = re.compile(_NUM)


def _mean(ctx: _Ctx, s: _Sentence) -> None:
    for m in _MEAN_RE.finditer(s.text):
        values = [Fraction(v.replace(",", "")) for v in _LIST_NUM_RE.findall(m.group("list"))]
        if len(values) < 2:
            continue
        stated = _fig(m, "m", s.text)
        nw = (m.group("n") or "").lower()
        if nw:
            n = _WORD_NUMBERS.get(nw, int(nw) if nw.isdigit() else None)
            if n is not None and n != len(values):
                ctx.undecided(s, m.group(0), f"the statement names {nw} values but lists {len(values)}")
                continue
        inputs = [(f"v{i + 1}", v, f"listed value {i + 1}") for i, v in enumerate(values)]
        expr = {"op": "div", "left": {"op": "add", "args": [_var(f"v{i + 1}") for i in range(len(values))]}, "right": _real(Fraction(len(values)))}
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_mean", lambda cid, inputs=inputs, expr=expr, stated=stated, values=values, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_mean", inputs=inputs, conclusion=band(expr, stated),
            label=f"stated mean {stated.shown} against the sum of the {len(values)} listed values / {len(values)}",
            description=f"{_excerpt(s.text)} [mean = sum of the listed values / their number; {_RULE.format(tau=5 if stated.approx else 1)}]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


_LEN_UNITS = {"m": Fraction(1), "metres": Fraction(1), "meters": Fraction(1), "metre": Fraction(1), "meter": Fraction(1), "km": Fraction(1000),
              "kilometres": Fraction(1000), "kilometers": Fraction(1000), "kilometre": Fraction(1000), "kilometer": Fraction(1000)}
_LEN = r"(?:m|metres|meters|metre|meter|km|kilometres|kilometers|kilometre|kilometer)\b"
_SITES = r"(?:sites|sampling\s+points|points|stations|quadrats|locations|sample\s+points)"
_COUNT = r"(?P<{g}>" + _WORD_NUMBER + r"|\d{{1,3}})"
_SAMPLING_RE = re.compile(_COUNT.format(g="n") + r"\s++" + _SITES + r"\s++(?:at|every|spaced)\s++" + _num_re("i", scale=False) + r"\s*+(?P<iu>" + _LEN + r")"
                          r"(?:\s++(?:intervals?|apart))?\s++(?:from|between)\s++" + _num_re("s", scale=False) + r"\s*+(?P<su>" + _LEN + r")\s++(?:to|and)\s++"
                          + _num_re("e", scale=False) + r"\s*+(?P<eu>" + _LEN + r")", re.IGNORECASE)
_TRANSECT_RE = re.compile(r"\b(?:an?\s+)?" + _num_re("l", scale=False) + r"[\s-]*+(?P<lu>" + _LEN + r")\s*+(?:long\s+)?transect\b[^.;\n]{0,60}?\bevery\s++"
                          + _num_re("i", scale=False) + r"\s*+(?P<iu>" + _LEN + r")[^.;\n]{0,40}?\b" + _COUNT.format(g="n") + r"\s++" + _SITES, re.IGNORECASE)


def _count_value(w: str) -> Optional[int]:
    w = (w or "").lower()
    return _WORD_NUMBERS.get(w, int(w) if w.isdigit() else None)


def _sampling(ctx: _Ctx, s: _Sentence) -> None:
    m = _SAMPLING_RE.search(s.text)
    t = None if m else _TRANSECT_RE.search(s.text)
    if m is None and t is None:
        return
    if m is not None:
        n = _count_value(m.group("n"))
        i = Fraction(m.group("i").replace(",", "")) * _LEN_UNITS[m.group("iu").lower()]
        length = (Fraction(m.group("e").replace(",", "")) * _LEN_UNITS[m.group("eu").lower()]) - Fraction(m.group("s").replace(",", "")) * _LEN_UNITS[m.group("su").lower()]
        phrase = m.group(0)
    else:
        n = _count_value(t.group("n"))
        i = Fraction(t.group("i").replace(",", "")) * _LEN_UNITS[t.group("iu").lower()]
        length = Fraction(t.group("l").replace(",", "")) * _LEN_UNITS[t.group("lu").lower()]
        phrase = t.group(0)
    if n is None or i <= 0 or length <= 0:
        return
    by = length / i
    conclusion = {"op": "or", "args": [{"op": "eq", "left": _var("sites"), "right": _real(by + 1)}, {"op": "eq", "left": _var("sites"), "right": _real(by)}]}
    ctx.decided.add(" ".join(s.text.split()))
    ctx.add("geo_sampling", lambda cid: make_check(
        ctx.report, check_id=cid, kind="geo_sampling", inputs=[("sites", Fraction(n), "the number of sites stated")], conclusion=conclusion,
        label=f"{n} sites at {_fmt(i)} m over {_fmt(length)} m: length / interval + 1 = {_fmt(by + 1)} or length / interval = {_fmt(by)}",
        description=(f"{_excerpt(s.text)} [systematic sampling: sites = length / interval + 1 (both ends sampled) or length / interval; conventions vary, "
                     f"so a failure is a warning]"),
        claim_ids=_claims(ctx.report, s.text, phrase), severity="warning", defect="stem_arithmetic_slip"))


_SIGNIF_R_RE = re.compile(r"(?<![\w])(?:r\s*+[_ₛ]?\s*+s|rₛ|r_s|rs|spearman['’]?s?\s+(?:rank\s+)?(?:correlation\s+)?(?:coefficient)?|r)\s*+(?:=|of|is|was)\s*+"
                          r"(?P<sg>[−-])?(?P<r>0?\.\d{1,6}|1(?:\.0{1,6})?)\b", re.IGNORECASE)
_CRITICAL_RE = re.compile(r"\bcritical\s+value\s*+(?:of|is|=|:)?\s*+(?:\([^)]{0,30}\)\s*+(?:(?:of|is|=|:)\s*+)?)?(?P<cv>0?\.\d{1,6}|1(?:\.0{1,6})?)\b",
                          re.IGNORECASE)
# (the optional bracket is a bracket, '(n = 10, p = 0.05)': with its parentheses optional it took 'of 0.648 at the' as a bracket and read
# the significance level after it as the critical value, attack round 1 of c3b)
_VERDICT_RE = re.compile(r"\b(?P<neg>not\s+(?:statistically\s+)?significant|insignificant|accept(?:ed)?\s+the\s+null|cannot\s+reject|fail\s+to\s+reject)\b"
                         r"|\b(?P<pos>(?:statistically\s+)?significant|reject(?:ed)?\s+the\s+null)\b", re.IGNORECASE)


def _significance(ctx: _Ctx, s: _Sentence) -> None:
    rm, cm = _SIGNIF_R_RE.search(s.text), _CRITICAL_RE.search(s.text)
    if rm is None or cm is None:
        return
    verdicts = list(_VERDICT_RE.finditer(s.text))
    if not verdicts:
        return
    v = verdicts[-1]
    significant = v.group("pos") is not None
    r = Fraction(rm.group("r")) * (-1 if rm.group("sg") else 1)
    cv = Fraction(cm.group("cv"))
    big = {"op": "or", "args": [{"op": "ge", "left": _var("coefficient"), "right": _real(cv)}, {"op": "le", "left": _var("coefficient"), "right": _real(-cv)}]}
    conclusion = big if significant else {"op": "not", "arg": big}
    ctx.decided.add(" ".join(s.text.split()))
    ctx.add("geo_significance", lambda cid: make_check(
        ctx.report, check_id=cid, kind="geo_significance", inputs=[("coefficient", r, "the coefficient stated")], conclusion=conclusion,
        label=f"|{_fmt(r)}| {'>=' if significant else '<'} {_fmt(cv)} (the stated verdict: {'significant' if significant else 'not significant'})",
        description=(f"{_excerpt(s.text)} [the verdict follows from |coefficient| against the stated critical value; the critical value itself (its table, "
                     f"tails and degrees of freedom) is not decided]"),
        claim_ids=_claims(ctx.report, s.text, rm.group(0))))


# ------------------------------------------------------------------------------------------------------------------ supplied tables
_MAX_TABLES = 8
_MAX_ROWS = 60
_MAX_COLS = 8
_MAX_CELL = 80
_CREDIT_RE = re.compile(r"\b(?:(?:the|your|my|our)\s+(?:data\s+)?table\s+(?:shows?|gives?|has|had|lists?|records?|states?|contains?)|according\s+to\s+(?:the|your|my)\s+"
                        r"(?:data|table|results)|(?:the|your|my|our)\s+data\s+(?:shows?|gives?|records?)|(?:in|from)\s+(?:the|your|my)\s+(?:data\s+)?table)\b", re.IGNORECASE)
_STOPWORDS = frozenset("the and of in on at for by to from with per out total mean number share data value values use".split())


@dataclass(frozen=True)
class _AttrTable:
    document_id: str
    row_noun: str                                  # the first header's first word ('site'), '' when none
    rows: tuple[tuple[str, tuple[str, ...]], ...]  # (row label as written, the row's cells)
    columns: tuple[tuple[str, frozenset[str]], ...]  # (header as written, its distinctive content stems)


def _stem(w: str) -> str:
    return w.lower().strip("'’-")[:5]


def _attribute_tables(texts: list[SuppliedText]) -> list[_AttrTable]:
    """The supplied pipe tables WITHOUT a year axis (grounded_figures reads the year-keyed ones): rows by their first cell, columns by the
    content words of their header. The caps of grounded_figures (8 tables, 60 rows, 8 columns, 80-character cells)."""
    from .grounded_figures import _cells, _YEAR_RE, _SEPARATOR_RE
    out: list[_AttrTable] = []
    for t in texts:
        if (t.document_id or "").startswith("peer:"):
            continue
        lines = (t.text or "")[:60_000].split("\n")
        i = 0
        while i < len(lines) and len(out) < _MAX_TABLES:
            if lines[i].count("|") < 1 or _SEPARATOR_RE.match(lines[i]):
                i += 1
                continue
            header = [c[:_MAX_CELL] for c in _cells(lines[i])]
            rows: list[list[str]] = []
            j = i + 1
            while j < len(lines) and len(rows) < _MAX_ROWS:
                if _SEPARATOR_RE.match(lines[j]):
                    j += 1
                    continue
                if lines[j].count("|") < 1:
                    break
                cells = _cells(lines[j])
                if len(cells) != len(header):
                    break
                rows.append(cells)
                j += 1
            if 2 <= len(header) <= _MAX_COLS and len(rows) >= 2 and not all(_YEAR_RE.match(h) for h in header[1:]) and not all(_YEAR_RE.match(r[0]) for r in rows):
                words = [[w for w in re.findall(r"[A-Za-z][A-Za-z'’-]{1,30}", re.sub(r"\([^)]*\)", "", h)) if w.lower() not in _STOPWORDS] for h in header]
                stems = [frozenset(_stem(w) for w in ws) for ws in words]
                cols = []
                for k in range(1, len(header)):
                    others = frozenset().union(*(stems[x] for x in range(1, len(header)) if x != k)) if len(header) > 2 else frozenset()
                    cols.append((header[k], frozenset(stems[k] - others - stems[0])))
                noun = words[0][0].lower() if words[0] else ""
                out.append(_AttrTable(t.document_id, noun, tuple((r[0], tuple(r)) for r in rows), tuple(cols)))
            i = max(j, i + 1)
    return out


_CLAUSE_RE = re.compile(r"[^;]{1,600}")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'’-]{0,30}|\d{1,3}(?:,\d{3})++(?:\.\d{1,6})?|\d{1,9}(?:\.\d{1,6})?")


def _row_named(table: _AttrTable, clause: str) -> list[int]:
    found = []
    low = clause.lower()
    listed: set[str] = set()
    if table.row_noun:
        # a list of row labels after the row noun ("Sites 1, 2 and 3"): every label of it is named, so no single row is
        for lm in re.finditer(rf"\b{re.escape(table.row_noun)}s?\s++([a-z0-9]{{1,3}}(?:\s*+,\s*+[a-z0-9]{{1,3}}){{0,20}}+\s*+,?\s*+(?:and|or|&|to)\s++"
                              rf"[a-z0-9]{{1,3}})\b", low):
            listed.update(x for x in re.split(r"\s*+(?:,|and|or|&|to)\s*+", lm.group(1)) if x)
    for k, (label, _cells) in enumerate(table.rows):
        lab = label.strip().lower()
        if not lab:
            continue
        if lab in listed:
            found.append(k)
            continue
        pats = []
        if table.row_noun and re.fullmatch(r"[a-z0-9]{1,3}", lab):
            pats.append(rf"\b{re.escape(table.row_noun)}s?\s++{re.escape(lab)}\b")
        elif len(lab) >= 3:
            pats.append(rf"(?<![\w-]){re.escape(lab)}(?![\w-])")
        if any(re.search(p, low) for p in pats):
            found.append(k)
    return found


def _table_figures(ctx: _Ctx, s: _Sentence, tables: list[_AttrTable]) -> None:
    from .grounded_figures import _half, _number
    credited = _CREDIT_RE.search(s.text) is not None
    for table in tables:
        rows = _row_named(table, s.text)
        if len(rows) != 1:
            if len(rows) > 1:
                _table_cells(ctx, s, table, credited)  # two rows in one sentence: each figure is read with its own row (attack round 3)
            continue
        label, cells = table.rows[rows[0]]
        toks = list(_TOKEN_RE.finditer(s.text))
        stems = [_stem(t.group(0)) if t.group(0)[0].isalpha() else None for t in toks]
        cols = [k for k, (_h, st) in enumerate(table.columns) if st and any(x in st for x in stems if x)]
        if len(cols) != 1:
            if len(cols) > 1:
                _table_cells(ctx, s, table, credited)  # two columns named: each figure is read with its own column (attack round 3)
            continue
        col = cols[0]
        header, colstems = table.columns[col]
        cell = _number(cells[col + 1])
        if cell is None:
            continue
        held, held_shown, _sign = cell
        # the figure: the number nearest after a column word (within four tokens), or right before it ('97 pedestrians')
        figure = None
        for idx, st in enumerate(stems):
            if st is None or st not in colstems:
                continue
            cands = [idx - 1] + list(range(idx + 1, min(len(toks), idx + 5)))
            for c in cands:
                if 0 <= c < len(toks) and toks[c].group(0)[0].isdigit():
                    tok = toks[c]
                    before = s.text[max(0, tok.start() - 12):tok.start()]
                    if re.search(r"(?:per|/)\s*+$", before, re.IGNORECASE) or re.search(r"[=≈]\s*+$", before):
                        continue
                    if re.search(rf"\b{re.escape(table.row_noun)}s?\s*+$", before, re.IGNORECASE) if table.row_noun else False:
                        continue
                    if _NOT_A_CELL_AFTER_RE.match(s.text[tok.end():tok.end() + 40]) or \
                            _DERIVED_BEFORE_RE.search(s.text[max(0, tok.start() - 48):tok.start()]):
                        continue  # a share of a maximum, a derived change: no cell (attack round 5)
                    figure = tok
                    break
            if figure is not None:
                break
        if figure is None:
            _table_cells(ctx, s, table, credited)  # a figure further from its column word ("66% of ground-floor units at Site 4")
            continue
        shown = figure.group(0)
        try:
            stated = Fraction(shown.replace(",", ""))
        except (ValueError, ZeroDivisionError):
            continue
        half_s = _half(shown.replace(",", ""))
        half_c = _half(held_shown.replace(",", ""))
        width = max(half_s, half_c)
        severity = "error" if credited else "warning"
        conclusion = {"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _var("cell")}, "right": _real(width)},
                                            {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _var("cell")}, "right": _real(-width)}]}
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("supplied_figure", lambda cid, held=held, stated=stated, label=label, header=header, shown=shown, held_shown=held_shown, severity=severity,
                conclusion=conclusion, table=table: make_check(
                    ctx.report, check_id=cid, kind="supplied_figure",
                    inputs=[("stated", stated, f"the figure the answer states ({shown})"), ("cell", held, f"the supplied figure of {label} | {header}")],
                    conclusion=conclusion,
                    label=f"the figure {shown} equals the supplied figure it is taken from ({held_shown} in {table.document_id}, row {label}, column {header})",
                    description=(f"a figure taken from a supplied table: {shown} in '{_excerpt(s.text, 200)}' against {table.document_id}, row {label}, column "
                                 f"{header}: {held_shown} ({'the clause credits the table' if credited else 'the clause names the row and the column'}) "
                                 f"[rule: a figure taken from a supplied table equals it within half a unit of the last digit written of either]"),
                    claim_ids=_claims(ctx.report, s.text, shown), severity=severity, defect="source_mismatch"))


#: Numbers that are no cell of the table: a rate's base ("per 10 minutes"), a maximum ("out of 30"), a multiple ("five times"), a row label.
_NOT_A_CELL_BEFORE_RE = re.compile(r"(?:\bper|/|\bout\s+of|\bof\s+the|\bby|\bagainst|\bversus|\bvs\.?|\bthan|\bcompared\s+with|[=≈×x÷])\s*+\(?\s*+$",
                                   re.IGNORECASE)
_NOT_A_CELL_AFTER_RE = re.compile(r"^\s*+(?:times|fold|x\b|-fold|minutes?\b|min\b|hours?\b|seconds?\b|against\b|versus\b|vs\b|[×÷+=−-]\s*+\d|"
                                  # a share of a maximum or a total ("80% of the maximum score", "30% of the maximum": attack round 5)
                                  r"(?:%|\s*+per\s+cent|\s*+percent)?\s*+of\s++(?:the\s++)?(?:maximum|max|total|possible|whole|highest)|"
                                  # a comparison with another figure ("28 fewer than Site 1's 214", "6 below Site 1's 24", "9% of
                                  # that at Site 1"): a difference or a ratio derived from two cells, never a cell (attack round 6)
                                  r"(?:%|\s*+per\s+cent|\s*+percent|\s*+percentage\s+points?|\s*+points?)?\s*+(?:\w+\s+){0,2}?"
                                  r"(?:fewer|less|lower|higher|more|greater|above|below|smaller|larger|bigger|under|over)\b|"
                                  r"(?:%|\s*+per\s+cent|\s*+percent)\s*+of\s++(?:that|those|the\s+\w+)\s++(?:at|in|for|of)\b)",
                                  re.IGNORECASE)
#: A figure derived from cells, after the change it measures ("a fall of about 91%", "a drop of 32 percentage points": attack round
#: 5): computed, never a cell of the table (the from-to and change checks decide it).
_DERIVED_BEFORE_RE = re.compile(r"\b(?:an?\s++)?(?:fall|rise|drop|decrease|increase|decline|change|reduction|gain|loss|difference|"
                                r"fall-off|growth)\s++of\s++(?:(?:about|around|roughly|approximately|nearly|almost|some|just\s+over|"
                                r"just\s+under)\s++)?\(?\s*+$|\b(?:fell|falls|fall|rose|rises|rise|dropped|drops|declined|declines|"
                                r"decreased|decreases|increased|increases|grew|grows)\s++by\s++"
                                r"(?:(?:about|around|roughly|approximately|nearly|almost)\s++)?$", re.IGNORECASE)
#: A figure placed at a row: "214 at Site 1", "60% at Site 4", "300 m at Site 4" (its unit between figure and row allowed).
_AT_ROW_RE = re.compile(r"\s*+(?:%|per\s+cent|percent|m|km|metres?|meters?)?\s*+(?:at|in|for|of)\s*+", re.IGNORECASE)


def _table_cells(ctx: _Ctx, s: _Sentence, table: _AttrTable, credited: bool) -> None:
    """Attack round 3 (ge-t14): every figure of a sentence that names rows and columns of a supplied attribute table, each read with
    its own row and column: the row mention nearest to it (by tokens, the label's own digits never a figure) and the column word
    within four tokens of it (the nearest; a tie leaves the figure unread), or, in a figure after a row mention with no column word
    near ("and Site 7 had 24", "to 14 at Site 10"), the column the sentence last named. A rate's base, a maximum, a multiple and a
    worked operand are no cells. Compared like any figure taken from a supplied table."""
    if not table.row_noun:
        return
    noun = table.row_noun
    if re.search(rf"\b{re.escape(noun)}s\s++[a-z0-9]{{1,3}}\s*+(?:,|and|or|&|to)\s*+[a-z0-9]", s.text, re.IGNORECASE):
        return  # a list of rows ("Sites 1 and 2 had 214 and 186"): no figure has one row of its own
    # each clause of a contrast is read alone ("... at Site 10, while retail use fell from 92% to 0%")
    at = 0
    for part in _CONTRAST_SPLIT_RE.split(s.text):
        if part.strip():
            _table_cells_clause(ctx, s, table, credited, part)
        at += len(part)


_UNIT_WORDS = {"m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m", "km": "km", "kilometres": "km", "%": "%", "per cent": "%",
               "percent": "%", "min": "min", "minutes": "min"}


def _header_unit(header: str) -> str:
    """The unit a column header gives in brackets ("Distance from central square (m)" -> "m", "(%)" -> "%"), or ""."""
    m = re.search(r"\(([^()]{1,20})\)\s*$", header)
    if not m:
        return ""
    u = m.group(1).strip().lower()
    return _UNIT_WORDS.get(u, "")


def _figure_unit(after: str) -> str:
    """The unit written right after a figure ("300 m", "92%", "45 per cent"), or ""."""
    m = re.match(r"\s*+(%|per\s+cent\b|percent\b|m\b|metres?\b|meters?\b|km\b|kilometres?\b)", after, re.IGNORECASE)
    return _UNIT_WORDS.get(" ".join(m.group(1).lower().split()), "") if m else ""


_CONTRAST_SPLIT_RE = re.compile(r";|,\s*+(?:while|whereas|but|although|though|yet)\b|\s(?:whereas|but|although)\s", re.IGNORECASE)


def _table_cells_clause(ctx: _Ctx, s: _Sentence, table: _AttrTable, credited: bool, text: str) -> None:
    from .grounded_figures import _half, _number
    noun = table.row_noun
    toks = list(_TOKEN_RE.finditer(text))
    if len(toks) > 400:
        return
    mentions: list[tuple[int, int, int]] = []  # (first token, last token, row)
    labels = {lab.strip().lower(): k for k, (lab, _c) in enumerate(table.rows) if lab.strip()}
    for i, t in enumerate(toks[:-1]):
        w = t.group(0).lower()
        if (w == noun or w == noun + "s") and toks[i + 1].group(0).lower() in labels:
            mentions.append((i, i + 1, labels[toks[i + 1].group(0).lower()]))
    if not mentions:
        return
    in_mention = {j for a, b, _r in mentions for j in range(a, b + 1)}
    # coordinated rows then coordinated figures ("between Site 7 and Site 8 the count rose, from 42 to 45", "Site 1 and Site 10 had 214
    # and 19"): each figure takes its row in order (attack round 4)
    respective: dict[int, int] = {}
    group = [mentions[0]]
    for prev_m, m in zip(mentions, mentions[1:]):
        between = [x.group(0).lower() for x in toks[prev_m[1] + 1:m[0]]]
        if all(w in ("and", "or", "between", "to") for w in between):
            group.append(m)
        else:
            group = [m]
    if len(group) >= 2:
        figs = []
        j = group[-1][1] + 1
        while j < len(toks) and len(figs) <= len(group):
            w = toks[j].group(0)
            if w[0].isdigit():
                figs.append(j)
            elif figs and w.lower() not in ("and", "to", "or", "respectively", "m", "km", "per", "cent", "percent"):
                break
            j += 1
        if len(figs) == len(group):
            respective = {f: g[2] for f, g in zip(figs, group)}
    colunit = {k: _header_unit(h) for k, (h, _st) in enumerate(table.columns)}
    colstem = {}
    for k, (_h, st) in enumerate(table.columns):
        for x in st:
            colstem.setdefault(x, set()).add(k)
    colpos = [(i, next(iter(colstem[_stem(t.group(0))]))) for i, t in enumerate(toks)
              if t.group(0)[0].isalpha() and len(colstem.get(_stem(t.group(0)), ())) == 1]
    last_col = None
    for i, t in enumerate(toks):
        if i in in_mention or not t.group(0)[0].isdigit():
            continue
        shown = t.group(0)
        if re.fullmatch(r"(?:1[89]\d{2}|20\d{2})", shown):
            continue
        before = text[max(0, t.start() - 14):t.start()]
        after = text[t.end():t.end() + 12]
        if _NOT_A_CELL_BEFORE_RE.search(before) or _NOT_A_CELL_AFTER_RE.match(text[t.end():t.end() + 40]) or \
                _DERIVED_BEFORE_RE.search(text[max(0, t.start() - 48):t.start()]):
            continue
        near = sorted((abs(j - i), c) for j, c in colpos if abs(j - i) <= 4)
        if near and len(near) > 1 and near[0][0] == near[1][0] and near[0][1] != near[1][1]:
            continue
        col = near[0][1] if near else None
        # a figure written with its unit belongs to the column of that unit ("Site 4 (300 m)" is a distance, never a count)
        unit = _figure_unit(text[t.end():t.end() + 12])
        if unit:
            by_unit = [k for k, u in colunit.items() if u == unit]
            if len(by_unit) == 1:
                col = by_unit[0]
            elif col is not None and colunit.get(col) and colunit[col] != unit:
                continue
        if col is None:
            prev = [m for m in mentions if m[1] < i]
            nxt = [m for m in mentions if m[0] > i]
            row_adjacent = (prev and i - prev[-1][1] <= 2) or (nxt and nxt[0][0] - i <= 2)
            if last_col is None or not (row_adjacent or i in respective):
                continue
            col = last_col
        last_col = col
        dist = sorted((min(abs(a - i), abs(b - i)), a, r) for a, b, r in mentions)
        linked_after = [r for a, _b, r in mentions if a > i and _AT_ROW_RE.fullmatch(text[t.end():toks[a].start()])]
        before = [m for m in mentions if m[1] < i]
        if i in respective:
            row = respective[i]
        elif linked_after:
            row = linked_after[0]  # "214 at Site 1": the row it is placed at
        elif before and len({r for _a, _b, r in mentions}) > 1:
            row = before[-1][2]  # "Site 4 had 97 and Site 5 had 88": the row its own clause names before it
        elif len(dist) > 1 and dist[0][0] == dist[1][0] and dist[0][2] != dist[1][2]:
            # a figure between two rows: the one it is placed at ("from 24 at Site 1 to 14 at Site 10"), else unread
            linked = [r for d, a, r in dist[:2] if a > i and _AT_ROW_RE.fullmatch(text[t.end():toks[a].start()])]
            if len(linked) != 1:
                continue
            row = linked[0]
        elif len({r for _d, _a, r in dist}) > 1 and dist[0][0] > 8:
            continue  # two rows, neither near
        else:
            row = dist[0][2]
        label, cells = table.rows[row]
        cell = _number(cells[col + 1])
        if cell is None:
            continue
        held, held_shown, _sign = cell
        try:
            stated = Fraction(shown.replace(",", ""))
        except (ValueError, ZeroDivisionError):
            continue
        header = table.columns[col][0]
        width = max(_half(shown.replace(",", "")), _half(held_shown.replace(",", "")))
        severity = "error" if credited else "warning"
        conclusion = {"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _var("cell")}, "right": _real(width)},
                                            {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _var("cell")}, "right": _real(-width)}]}
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("supplied_figure", lambda cid, held=held, stated=stated, label=label, header=header, shown=shown, held_shown=held_shown,
                severity=severity, conclusion=conclusion: make_check(
                    ctx.report, check_id=cid, kind="supplied_figure",
                    inputs=[("stated", stated, f"the figure the answer states ({shown})"), ("cell", held, f"the supplied figure of {label} | {header}")],
                    conclusion=conclusion,
                    label=f"the figure {shown} equals the supplied figure it is taken from ({held_shown} in {table.document_id}, row {label}, column {header})",
                    description=(f"a figure taken from a supplied table: {shown} in '{_excerpt(s.text, 200)}' against {table.document_id}, row {label}, column "
                                 f"{header}: {held_shown} ({'the clause credits the table' if credited else 'the sentence names the row and the column'}) "
                                 f"[rule: each figure is read with its nearest row and column; a figure taken from a supplied table equals it within half a "
                                 f"unit of the last digit written of either]"),
                    claim_ids=_claims(ctx.report, s.text, shown), severity=severity, defect="source_mismatch"))


_TABLE_COUNT_RE = re.compile(r"\b(?:(?:the|your|my|our)\s+(?:data\s+)?table\s+(?:shows?|has|lists?|gives?|contains?|records?|covers?)|data\s+from|my|our|there\s+are)\s++"
                             r"(?P<n>" + _WORD_NUMBER + r"|\d{1,3})\s++(?P<noun>[a-z]{2,20})\b", re.IGNORECASE)


def _table_count(ctx: _Ctx, s: _Sentence, tables: list[_AttrTable]) -> None:
    flat = None
    for m in _TABLE_COUNT_RE.finditer(s.text):
        if not ctx.room("geo_table_count"):
            ctx.skip("geo_table_count")
            break  # (the kind is full: reading on would only re-join the sentence per match, quadratic on a long one)
        noun = m.group("noun").lower()
        n = _count_value(m.group("n"))
        if n is None:
            continue
        hits = [t for t in tables if t.row_noun and (noun == t.row_noun or noun.rstrip("s") == t.row_noun.rstrip("s"))]
        if len(hits) != 1:
            continue
        rows = len(hits[0].rows)
        if flat is None:
            flat = " ".join(s.text.split())
            ctx.decided.add(flat)
        ctx.add("geo_table_count", lambda cid, n=n, rows=rows, t=hits[0], m=m: make_check(
            ctx.report, check_id=cid, kind="geo_table_count", inputs=[("stated", Fraction(n), f"the number of {noun} stated")],
            conclusion={"op": "eq", "left": _var("stated"), "right": _real(Fraction(rows))},
            label=f"{n} {noun} against the {rows} rows of the supplied table ({t.document_id})",
            description=f"{_excerpt(s.text)} [a count of the rows of a supplied table equals the number of its rows ({rows} in {t.document_id})]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="warning", defect="source_mismatch"))


# ------------------------------------------------------------------------------------------------------------------ aggregates
_CHANGE_VERB = r"fell|falls|rose|rises|dropped|drops|declined|declines|decreased|decreases|increased|increases|grew|grows|went\s+(?:up|down)|goes\s+(?:up|down)"
_CHANGE_BY_RE = re.compile(r"\b(?:" + _CHANGE_VERB + r")\s++by\s++(?P<ap>about\s++|around\s++|roughly\s++|approximately\s++)?(?P<n>" + _NUM + r")\s*+"
                           r"(?P<u>%|per\s*+cent\b|percentage\s+points?\b|points?\b)?", re.IGNORECASE)
_PAIR_FROM_RE = re.compile(r"\bfrom\s++(?P<a>" + _NUM + r")(?P<ap>\s*+%)?(?:\s++[^;]{0,40}?)?\s++to\s++(?P<b>" + _NUM + r")(?P<bp>\s*+%)?", re.IGNORECASE)
_PAIR_PAREN_RE = re.compile(r"\bbetween\s++[^();\d]{0,40}?(?:\d{1,3}\s*+)?\((?P<a>" + _NUM + r")\s*+(?P<ap>%)?\)\s++and\s++[^();\d]{0,40}?(?:\d{1,3}\s*+)?"
                            r"\((?P<b>" + _NUM + r")\s*+(?P<bp>%)?\)", re.IGNORECASE)
_TIMES_PAIR_RE = re.compile(r"(?P<ap>\babout\s++|\baround\s++|\broughly\s++|\bnearly\s++|\balmost\s++)?(?P<n>" + _WORD_NUMBER + r"|" + _NUM + r")\s++times\s++"
                            r"(?:as\s++(?:many|much|high|large|great|big)|more|higher|larger|greater)\b[^.;]{0,80}?\((?P<a>" + _NUM + r")\s++"
                            r"(?:against|vs\.?|versus|to|compared\s+with)\s++(?P<b>" + _NUM + r")\)", re.IGNORECASE)


#: "about 160 times Christchurch's 185 deaths (300,000 ÷ 185)": a multiple with its division in brackets.
_TIMES_DIV_RE = re.compile(r"(?P<ap>\babout\s++|\baround\s++|\broughly\s++|\bnearly\s++|\balmost\s++)?(?P<n>" + _WORD_NUMBER + r"|" + _NUM + r")\s++times\b"
                           r"[^.;()]{0,80}?\(\s*+(?P<a>" + _NUM + r")\s*+(?:÷|/)\s*+(?P<b>" + _NUM + r")\s*+\)", re.IGNORECASE)


def _num(x: str) -> Fraction:
    return Fraction(x.replace(",", ""))


def _change_by(ctx: _Ctx, s: _Sentence) -> None:
    """Attack round 3 (ge-t14): a change stated "by N" (a difference, a per cent or percentage points) with its pair written in the same
    sentence ("falls by 195, from 214 at Site 1 to 19 at Site 10"; "fell by 91% between Site 1 (214) and Site 10 (19)")."""
    from bisect import bisect_left
    from .grounded_figures import _half
    changes = list(_CHANGE_BY_RE.finditer(s.text))
    if not changes:
        return
    # the pairs are found once per sentence and each change takes the first pair after it (else the first one before it): one pass
    # each, never a scan of the sentence per change (attack round 4: a long sentence of "rose by N" with no pair was quadratic)
    froms = list(_PAIR_FROM_RE.finditer(s.text))
    parens = list(_PAIR_PAREN_RE.finditer(s.text))
    from_starts = [p.start() for p in froms]
    paren_starts = [p.start() for p in parens]
    for m in changes:
        k = bisect_left(from_starts, m.end())
        pair = froms[k] if k < len(froms) else None
        if pair is None:
            k2 = bisect_left(paren_starts, m.end())
            pair = parens[k2] if k2 < len(parens) else None
        if pair is None and froms and froms[0].end() <= m.start():
            pair = froms[0]
        if pair is None:
            continue
        a, b = _num(pair.group("a")), _num(pair.group("b"))
        n = _num(m.group("n"))
        unit = (m.group("u") or "").casefold()
        if unit.startswith(("%", "per")) and not unit.startswith("percentage"):
            if a == 0:
                continue
            value = abs(b - a) / a * 100
            what = "per cent"
            tol = max(Fraction(1, 2), value * Fraction(1, 50)) if m.group("ap") else max(_half(m.group("n").replace(",", "")), Fraction(1, 2))
        else:
            value = abs(b - a)
            what = "percentage points" if unit else "difference"
            tol = value * Fraction(1, 20) if m.group("ap") else _half(m.group("n").replace(",", ""))
        if not ctx.room("geo_change_by"):
            ctx.skip("geo_change_by")
            return
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_change_by", lambda cid, n=n, value=value, tol=tol, m=m, pair=pair, what=what: make_check(
            ctx.report, check_id=cid, kind="geo_change_by", inputs=[("stated", n, f"the change stated ({m.group(0).strip()})")],
            conclusion={"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _real(value)}, "right": _real(tol)},
                                              {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _real(value)}, "right": _real(-tol)}]},
            label=f"the change by {m.group('n')} ({what}) against its pair {pair.group('a')} and {pair.group('b')}",
            description=f"{_excerpt(s.text)} [a change stated by its size equals the {what} between the pair the sentence states]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


def _times_pair(ctx: _Ctx, s: _Sentence) -> None:
    """Attack round 3 (ge-t14): "N times as many ... (A against B)": the multiple equals A / B (within 10% after "about", else half a
    unit of the multiple written)."""
    from .grounded_figures import _half
    for m in list(_TIMES_PAIR_RE.finditer(s.text)) + list(_TIMES_DIV_RE.finditer(s.text)):
        w = m.group("n")
        n = Fraction(_WORD_NUMBERS[w.lower()]) if w.lower() in _WORD_NUMBERS else _num(w)
        a, b = _num(m.group("a")), _num(m.group("b"))
        if b == 0:
            continue
        value = a / b
        tol = value / 10 if m.group("ap") else _half(w.replace(",", "")) if w[0].isdigit() else Fraction(1, 2)
        if not ctx.room("geo_times_pair"):
            ctx.skip("geo_times_pair")
            return
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_times_pair", lambda cid, n=n, value=value, tol=tol, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_times_pair", inputs=[("stated", n, f"the multiple stated ({w} times)")],
            conclusion={"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _real(value)}, "right": _real(tol)},
                                              {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _real(value)}, "right": _real(-tol)}]},
            label=f"{w} times against {m.group('a')} / {m.group('b')}",
            description=f"{_excerpt(s.text)} [a multiple stated with its pair equals their ratio: within 10% after 'about', else half a unit]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


_UNIT_RUN = r"(?:\s*+[^\d\s,;.()]{1,10}){0,3}?"
#: (a point of a from-to pair: a year, a numbered storm, site, year, week or day, a named one; "before Storm 1" and "after Storm 2"
#: name points as well: attack round 6)
_AT_POINT = (r"(?:\s++(?:in|at|during|for|on|before|after|by)\s++(?:\d{4}|(?:Storm|Site|Year|Week|Day)\s++\d{1,3}|the\s+[a-z]{3,15}"
             r"(?:\s++(?:Storm|Site|Year|Week|Day)\s++\d{1,3})?))?")
#: "from 5.4 m³ s⁻¹ in 2006 to 16.2 m³ s⁻¹ in 2024, an increase of 300%": a pair with its units and points, then the relative change.
_FROM_TO_PCT_RE = re.compile(r"\bfrom\s++(?P<a>" + _NUM + r")" + _UNIT_RUN + _AT_POINT + r"\s++to\s++(?P<b>" + _NUM + r")" + _UNIT_RUN + _AT_POINT +
                             r"\s*+,?\s++(?:which\s+is\s+)?(?:an?\s+)?(?:(?P<up>increase|rise|growth|gain)|(?P<down>fall|decrease|drop|decline|reduction))\s++of\s++"
                             r"(?P<ap>about\s++|around\s++|roughly\s++)?(?P<p>" + _NUM + r")\s*+(?:%|per\s*+cent\b|percent\b)", re.IGNORECASE)
_FOLD_VERB_RE = re.compile(r"\b(?P<v>doubled|tripled|trebled|quadrupled|halved)\b[^.;]{0,40}?\bfrom\s++(?P<a>" + _NUM + r")" + _UNIT_RUN + _AT_POINT +
                           r"\s++to\s++(?P<b>" + _NUM + r")", re.IGNORECASE)
_FOLD_VERBS = {"doubled": Fraction(2), "tripled": Fraction(3), "trebled": Fraction(3), "quadrupled": Fraction(4), "halved": Fraction(1, 2)}


#: "54% of supply was imported, up from 38% in 2005, a relative increase of 52%": the later figure, "up/down from" the earlier one, then
#: the relative change (attack round 4).
_UP_FROM_PCT_RE = re.compile(r"(?<![\d.,])(?P<b>" + _NUM + r")" + _UNIT_RUN + r"[^.;\d]{0,60}?,?\s++(?:(?P<upw>up)|(?P<downw>down))\s++from\s++(?P<a>" + _NUM + r")"
                             + _UNIT_RUN + _AT_POINT + r"\s*+,\s*+(?:an?\s+)?(?:relative\s+|proportional\s+)?(?:(?P<up>increase|rise|growth|gain)|"
                             r"(?P<down>fall|decrease|drop|decline|reduction))\s++of\s++(?P<ap>about\s++|around\s++|roughly\s++)?(?P<p>" + _NUM + r")\s*+"
                             r"(?:%|per\s*+cent\b|percent\b)", re.IGNORECASE)


def _from_to_percent(ctx: _Ctx, s: _Sentence) -> None:
    """Attack round 3 (ge-p9c): a from-to pair written with units and points, then its relative change ("rose from 5.4 m³ s⁻¹ in 2006
    to 16.2 m³ s⁻¹ in 2024, an increase of 300%"): the per cent equals (b − a) / a × 100 within half a unit of its last digit, 1% of
    the value or a tenth of a point, whichever is widest (operands are taken as written: a rounding band on them admitted a wrong 6.3%)."""
    from .grounded_figures import _half
    for m in list(_FROM_TO_PCT_RE.finditer(s.text)) + list(_UP_FROM_PCT_RE.finditer(s.text)):
        a, b, p = _num(m.group("a")), _num(m.group("b")), _num(m.group("p"))
        if a == 0 or not ctx.room("geo_from_to_percent"):
            continue
        value = (b - a) / a * 100
        stated = -p if m.group("down") else p
        tol = max(_half(m.group("p").replace(",", "")), abs(value) / 100, Fraction(1, 10))
        if m.group("ap"):
            tol = max(tol, abs(value) / 20)
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_from_to_percent", lambda cid, stated=stated, value=value, tol=tol, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_from_to_percent", inputs=[("stated", stated, f"the change stated ({m.group('p')}%)")],
            conclusion={"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _real(value)}, "right": _real(tol)},
                                              {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _real(value)}, "right": _real(-tol)}]},
            label=f"{'a fall' if m.group('down') else 'an increase'} of {m.group('p')}% against ({m.group('b')} − {m.group('a')}) / {m.group('a')} × 100",
            description=f"{_excerpt(s.text)} [a relative change after its from-to pair equals (later − earlier) / earlier × 100; operands as written]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))
    for m in _FOLD_VERB_RE.finditer(s.text):
        a, b = _num(m.group("a")), _num(m.group("b"))
        k = _FOLD_VERBS[m.group("v").lower()]
        if a == 0 or not ctx.room("geo_fold_verb"):
            continue
        ratio = b / a
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_fold_verb", lambda cid, ratio=ratio, k=k, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_fold_verb", inputs=[("ratio", ratio, f"the ratio of the pair ({m.group('b')} / {m.group('a')})")],
            conclusion={"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("ratio"), "right": _real(k)}, "right": _real(k / 20)},
                                              {"op": "ge", "left": {"op": "sub", "left": _var("ratio"), "right": _real(k)}, "right": _real(-k / 20)}]},
            label=f"'{m.group('v')}' (x{_fmt(k)}) against {m.group('b')} / {m.group('a')}",
            description=f"{_excerpt(s.text)} [a fold verb ('doubled', 'tripled', 'halved') states the ratio of its pair, within 5%]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


_BY_PERIOD_RE = re.compile(r"\b(?:" + _CHANGE_VERB + r")\s++by\s++(?P<ap>about\s++|around\s++|roughly\s++)?(?P<n>" + _NUM + r")\s*+"
                           r"(?P<u>percentage\s+points?\b|points?\b|million\b|billion\b|thousand\b)?[^.;\d]{0,30}?\b(?:between\s++(?P<y1>\d{4})\s++and\s++(?P<y2>\d{4})|"
                           r"from\s++(?P<z1>\d{4})\s++to\s++(?P<z2>\d{4}))", re.IGNORECASE)
_BY_ALONE_RE = re.compile(r"\b(?:" + _CHANGE_VERB + r")\s++by\s++(?P<ap>about\s++|around\s++|roughly\s++)?(?P<n>" + _NUM + r")\s*+(?P<u>percentage\s+points?\b)",
                          re.IGNORECASE)


def _table_change_by(ctx: _Ctx, s: _Sentence, year_tables: list) -> None:
    """Attack round 3 (ge-t15): a change of a supplied year table's row stated by its size, over a period the sentence names ("grew by 330
    PJ between 2005 and 2025", "grew by 4.5 million between 2005 and 2025") or, in percentage points, over the row's two years ("The coal
    share fell by 16 percentage points"): the size equals the difference of the row's two cells (in the row's unit; a scale word the row
    states is the row's own)."""
    from .grounded_figures import _entity_at, _half, _word_positions
    hits = [(m, True) for m in _BY_PERIOD_RE.finditer(s.text)] + [(m, False) for m in _BY_ALONE_RE.finditer(s.text)
                                                                 if not _BY_PERIOD_RE.search(s.text)]
    if not hits:
        return
    where = _word_positions(s.text)
    for table in year_tables:
        for m, dated in hits:
            entity, _count = _entity_at(table, where, m.start())
            if not entity:
                continue
            cells = {c.year: c for c in table.cells if c.entity == entity and c.year is not None}
            if dated:
                y1, y2 = int(m.group("y1") or m.group("z1")), int(m.group("y2") or m.group("z2"))
            elif len(cells) == 2:
                y1, y2 = sorted(cells)
            else:
                continue
            if y1 not in cells or y2 not in cells:
                continue
            unit = (m.group("u") or "").lower()
            if unit.startswith(("percentage", "point")) and cells[y1].unit != "%":
                continue
            if unit in ("million", "billion", "thousand") and unit not in cells[y1].unit.lower():
                continue  # a scale the row does not state: left to the other readers
            diff = abs(cells[y2].value - cells[y1].value)
            n = _num(m.group("n"))
            tol = max(_half(m.group("n").replace(",", "")), cells[y1].half + cells[y2].half)
            if m.group("ap"):
                tol = max(tol, diff / 20)
            if not ctx.room("geo_table_change"):
                return
            ctx.decided.add(" ".join(s.text.split()))
            ctx.add("geo_table_change", lambda cid, n=n, diff=diff, tol=tol, m=m, entity=entity, y1=y1, y2=y2, table=table: make_check(
                ctx.report, check_id=cid, kind="geo_table_change", inputs=[("stated", n, f"the change stated ({m.group('n')})")],
                conclusion={"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _real(diff)}, "right": _real(tol)},
                                                  {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _real(diff)}, "right": _real(-tol)}]},
                label=f"the change by {m.group('n')} against the row '{entity}' of {table.document_id} from {y1} to {y2}",
                description=f"{_excerpt(s.text)} [a change of a supplied table's row equals the difference of its cells for the two years]",
                claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="error", defect="source_mismatch"))
            return


_MEAN_WORD_RE = re.compile(r"\b(?:mean|average)\b", re.IGNORECASE)
_AGG_STATED_RE = re.compile(r"\b(?:is|was|of|=|:|comes\s+to|came\s+to)\s*+(?:about\s+|around\s+|roughly\s+|approximately\s+)?(?P<n>" + _NUM + r")\b"
                            r"(?!\s*+(?:sites|rows|points|minutes?\b|mins?\b|counts?\b|readings?\b|measurements?\b|samples?\b|times\b|seconds?\b|hours?\b|days?\b))",
                            re.IGNORECASE)
#: "Each pedestrian figure in your table is the mean of three counts": how each cell was made (the table's method), no mean stated.
_EACH_IS_MEAN_RE = re.compile(r"\b(?:each|every)\b[^.;]{0,60}?\b(?:is|was|are|were)\s+(?:the\s+|an?\s+)?(?:mean|average)\s+of\b", re.IGNORECASE)
_INTERVAL_RE = re.compile(r"(?P<c>" + _WORD_NUMBER + r"|\d{1,3})\s++" + _SITES + r"\s++(?:at|every|spaced)\s++(?P<i>" + _NUM + r")\s*+(?:m|metres?|meters?)\b",
                          re.IGNORECASE)
_TRANSECT_LEN_RE = re.compile(r"\b(?P<l>" + _NUM + r")\s*+(?:-\s*+)?(?:m|metres?|meters?)\s++(?:long\s+)?transect\b", re.IGNORECASE)
#: The length the sampled sites cover, stated with their interval ("Ten sites at 100 m intervals cover 1,200 m of the main road"):
#: the span of the transect too, first site to last (attack round 6: only the fit of ten sites in it was read).
_COVER_LEN_RE = re.compile(r"\b(?:cover|covers|covered|covering|span|spans|spanned|spanning|stretch(?:es|ed)?\s+over|extend(?:s|ed)?\s+over|"
                           r"run(?:s)?\s+over)\s++(?:about\s+|around\s+|roughly\s+)?(?P<l>" + _NUM + r")\s*+(?:m|metres?|meters?)\b", re.IGNORECASE)


_SUPERLATIVE_RE = re.compile(r"\b(?P<noun>[A-Za-z]{3,12})\s++(?P<lab>[A-Za-z0-9]{1,3})\s++(?:has|had|shows|showed|records?|recorded|is|was)\s++the\s++"
                             r"(?P<sup>lowest|highest|smallest|largest|greatest|least|most|fewest)\b(?P<rest>[^.;]{0,60})", re.IGNORECASE)
_LOW_WORDS = frozenset(("lowest", "smallest", "least", "fewest"))


def _table_superlative(ctx: _Ctx, s: _Sentence, tables: list[_AttrTable]) -> None:
    """Attack round 4 (ge-t14): "Site 7 has the lowest EQS of the ten sites": the named row's cell of the named column is the column's
    minimum (or maximum) over the supplied table's rows."""
    from .grounded_figures import _number
    for m in _SUPERLATIVE_RE.finditer(s.text):
        for table in tables:
            if not table.row_noun or m.group("noun").lower().rstrip("s") != table.row_noun.rstrip("s"):
                continue
            row = next((k for k, (lab, _c) in enumerate(table.rows) if lab.strip().lower() == m.group("lab").lower()), None)
            stems = {_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z'’-]{1,30}", m.group("rest"))}
            cols = [k for k, (_h, st) in enumerate(table.columns) if st and st & stems]
            if row is None or len(cols) != 1:
                continue
            col = cols[0]
            vals = [_number(cells[col + 1]) for _l, cells in table.rows]
            if any(v is None for v in vals) or not ctx.room("geo_table_superlative"):
                continue
            low = m.group("sup").lower() in _LOW_WORDS
            extreme = min(v[0] for v in vals) if low else max(v[0] for v in vals)
            cell = vals[row][0]
            header = table.columns[col][0]
            ctx.decided.add(" ".join(s.text.split()))
            ctx.add("geo_table_superlative", lambda cid, cell=cell, extreme=extreme, m=m, header=header, table=table, low=low: make_check(
                ctx.report, check_id=cid, kind="geo_table_superlative",
                inputs=[("cell", cell, f"the supplied figure of {m.group('noun')} {m.group('lab')} | {header}")],
                conclusion={"op": "eq", "left": _var("cell"), "right": _real(extreme)},
                label=f"{m.group('noun')} {m.group('lab')} has the {m.group('sup')} {header}: its cell against the column's {'minimum' if low else 'maximum'} "
                      f"({_fmt(extreme)}) in {table.document_id}",
                description=f"{_excerpt(s.text)} [the row named as the column's lowest (highest) holds the column's minimum (maximum)]",
                claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="error" if _CREDIT_RE.search(s.text) or "your" in s.text.lower() else "warning",
                defect="source_mismatch"))
            break


#: "(45) is lower than at 600 m (42)": a comparison of two figures the sentence writes in brackets.
_BRACKET_CMP_RE = re.compile(r"\((?P<a>" + _NUM + r")\s*+[^()\d]{0,12}\)\s++(?:is|was|are|were)\s++(?:(?:much|far|slightly|a\s+little)\s+)?"
                             r"(?P<cmp>lower|higher|less|more|greater|smaller|larger|fewer|bigger)\s++than\b[^.;()]{0,50}?\((?P<b>" + _NUM + r")\s*+[^()\d]{0,12}\)",
                             re.IGNORECASE)


def _bracket_comparison(ctx: _Ctx, s: _Sentence) -> None:
    """Attack round 4 (ge-t14): "the pedestrian count at 700 m (45) is lower than at 600 m (42)": the comparison holds of the two
    figures the sentence itself writes."""
    for m in _BRACKET_CMP_RE.finditer(s.text):
        if not ctx.room("geo_comparison"):
            return
        a, b = _num(m.group("a")), _num(m.group("b"))
        op = "lt" if m.group("cmp").lower() in ("lower", "less", "smaller", "fewer") else "gt"
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_comparison", lambda cid, a=a, b=b, op=op, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_comparison", inputs=[("first", a, f"the first figure ({m.group('a')})"), ("second", b, f"the second figure ({m.group('b')})")],
            conclusion={"op": op, "left": _var("first"), "right": _var("second")},
            label=f"{m.group('a')} is {m.group('cmp')} than {m.group('b')}",
            description=f"{_excerpt(s.text)} [a comparison of two figures the sentence writes holds of them]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


def _table_aggregates(ctx: _Ctx, s: _Sentence, tables: list[_AttrTable]) -> None:
    """Attack round 3 (ge-t14): a supplied table read as a whole: the mean of one column over every row ("The mean EQS across your ten
    sites is 16.3"), and the spacing and length of a transect against the table's distance column ("ten sites at 100 m intervals", "a
    900 m transect"). A sentence that names a row or lists its own values is left to the other readers."""
    from .grounded_figures import _half, _number
    for table in tables:
        toks = list(_TOKEN_RE.finditer(s.text))
        stems = {_stem(t.group(0)) for t in toks if t.group(0)[0].isalpha()}
        cols = [k for k, (_h, st) in enumerate(table.columns) if st and st & stems]
        values = [[_number(cells[k + 1]) for _l, cells in table.rows] for k in range(len(table.columns))]
        if _MEAN_WORD_RE.search(s.text) and len(cols) == 1 and not _row_named(table, s.text) and "(" not in s.text[_MEAN_WORD_RE.search(s.text).end():] \
                and not _EACH_IS_MEAN_RE.search(s.text):
            col = cols[0]
            vals = values[col]
            m = _AGG_STATED_RE.search(s.text, _MEAN_WORD_RE.search(s.text).end())
            if m is not None and all(v is not None for v in vals) and ctx.room("geo_table_mean"):
                mean = sum(v[0] for v in vals) / len(vals)
                n = _num(m.group("n"))
                tol = _half(m.group("n").replace(",", ""))
                header = table.columns[col][0]
                ctx.decided.add(" ".join(s.text.split()))
                ctx.add("geo_table_mean", lambda cid, n=n, mean=mean, tol=tol, header=header, m=m, table=table: make_check(
                    ctx.report, check_id=cid, kind="geo_table_mean", inputs=[("stated", n, f"the mean stated ({m.group('n')})")],
                    conclusion={"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _real(mean)}, "right": _real(tol)},
                                                      {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _real(mean)}, "right": _real(-tol)}]},
                    label=f"the mean {m.group('n')} of column {header} against the mean of its {len(table.rows)} rows in {table.document_id}",
                    description=f"{_excerpt(s.text)} [the mean of a supplied table's column equals the mean of its rows, within half a unit of the figure written]",
                    claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="error" if _CREDIT_RE.search(s.text) or "your" in s.text.lower() else "warning",
                    defect="stem_arithmetic_slip"))
        dist = next((k for k, (h, st) in enumerate(table.columns) if "dista" in st), None)
        if dist is None or any(v is None for v in values[dist]):
            continue
        d = sorted(v[0] for v in values[dist])
        steps = {b - a for a, b in zip(d, d[1:])}
        for m in _INTERVAL_RE.finditer(s.text):
            if len(steps) != 1 or _count_value(m.group("c")) != len(table.rows) or not ctx.room("geo_transect"):
                continue
            step = next(iter(steps))
            ctx.decided.add(" ".join(s.text.split()))
            ctx.add("geo_transect", lambda cid, m=m, step=step: make_check(
                ctx.report, check_id=cid, kind="geo_transect", inputs=[("stated", _num(m.group("i")), f"the interval stated ({m.group('i')} m)")],
                conclusion={"op": "eq", "left": _var("stated"), "right": _real(step)},
                label=f"the interval {m.group('i')} m against the spacing of the supplied distance column ({_fmt(step)} m)",
                description=f"{_excerpt(s.text)} [the interval between sites equals the spacing of the supplied table's distance column]",
                claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="warning", defect="source_mismatch"))
        lengths = list(_TRANSECT_LEN_RE.finditer(s.text))
        if _INTERVAL_RE.search(s.text):
            lengths += list(_COVER_LEN_RE.finditer(s.text))
        for m in lengths:
            if not ctx.room("geo_transect"):
                break
            span = d[-1] - d[0]
            ctx.decided.add(" ".join(s.text.split()))
            ctx.add("geo_transect", lambda cid, m=m, span=span: make_check(
                ctx.report, check_id=cid, kind="geo_transect", inputs=[("stated", _num(m.group("l")), f"the transect length stated ({m.group('l')} m)")],
                conclusion={"op": "eq", "left": _var("stated"), "right": _real(span)},
                label=f"the transect length {m.group('l')} m against the span of the supplied distance column ({_fmt(span)} m)",
                description=f"{_excerpt(s.text)} [a transect's length equals the span of the supplied table's distance column, first site to last]",
                claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="warning", defect="source_mismatch"))


# ------------------------------------------------------------------------------------------------------------------ case figures
_HEAD_NOUNS = {"deaths": "deaths", "dead": "deaths", "killed": "deaths", "died": "deaths", "fatalities": "deaths", "injured": "injured", "injuries": "injured",
               "displaced": "displaced", "homeless": "displaced", "homes": "homes", "houses": "homes", "buildings": "buildings", "claims": "claims"}
_CASE_FIG_RE = re.compile(r"(?P<pre>(?:more\s+than|over|at\s+least|fewer\s+than|less\s+than|under|up\s+to|about|around|roughly|approximately|nearly|almost|some)\s+)?"
                          r"(?<![\d.,])(?P<n>\d{1,3}(?:,\d{3})++|\d{1,9})(?![\d,]\d|\.\d)(?:\s++(?P<sc>thousand|million))?\s++(?:people\s++)?(?P<noun>deaths|dead|fatalities|injured|injuries|"
                          r"displaced|homeless|homes|houses|buildings|claims)\b(?!\s++of\s++them)"
                          r"|\b(?P<verb>killed|injured|displaced)\s++(?P<pre2>(?:more\s+than|over|at\s+least|about|around|nearly|almost|some)\s+)?(?<![\d.,])(?P<m>\d{1,3}(?:,\d{3})++|\d{1,9})"
                          r"(?![\d,]\d|\.\d)(?:\s++(?P<sc2>thousand|million))?\s++people\b", re.IGNORECASE)
#: More case quantities (attack round 3, ge-t16): an earthquake's magnitude, and "N of them" after its head noun in the sentence
#: ("damaged so many homes that the government later bought and cleared about 8,000 of them").
_MAGNITUDE_RE = re.compile(r"\bmagnitude(?:\s+of)?\s++(?:M\s*+)?(?P<n>\d(?:\.\d)?)\b|\bM\s?(?P<m>\d\.\d)\b", re.IGNORECASE)
_OF_THEM_RE = re.compile(r"(?P<pre>(?:more\s+than|over|at\s+least|fewer\s+than|less\s+than|under|up\s+to|about|around|roughly|approximately|nearly|almost|some)\s+)?"
                         r"(?<![\d.,])(?P<n>\d{1,3}(?:,\d{3})++|\d{1,9})(?![\d,]\d|\.\d)\s++of\s++them\b", re.IGNORECASE)
_HEAD_BEFORE_RE = re.compile(r"\b(deaths|dead|fatalities|injured|injuries|displaced|homeless|homes|houses|buildings|claims)\b", re.IGNORECASE)
_PROPER_RE = re.compile(r"(?<![\w'’-])([A-Z][a-zà-ÿ'’-]{2,40}(?:[ -][A-Z][a-zà-ÿ'’-]{1,40}){0,2})(?![\w'’-])")
_NOT_PLACES = frozenset("""The This That These Those It Its In On At By And But Yet So Here There When While However Even Overall Comparing Higher Development
    Economic Shaking Depth No Add Next Sources Step January February March April May June July August September October November December Monday Tuesday
    Wednesday Thursday Friday Saturday Sunday Earthquake Commission Government State Paper Option Geography Haiti's""".split())


def _places(text: str) -> list[tuple[int, str]]:
    """The proper names of ``text`` that can anchor a case figure, with their offsets, read once. A capitalised function word before
    a name ("The Haiti earthquake", "The Darfield earthquake") is set aside, never the name with it (attack round 4); a sentence's
    first word is a name only as a line's label ("Haiti: magnitude 7.0")."""
    out = []
    for m in _PROPER_RE.finditer(text):
        words = m.group(1).split()
        start = m.start()
        def plain(w: str) -> str:
            return re.sub(r"['’]s?$", "", w)
        while words and plain(words[0]) in _NOT_PLACES:
            start = text.find(words[1], start + len(words[0])) if len(words) > 1 else -1
            words = words[1:]
        if not words or start < 0 or all(plain(w) in _NOT_PLACES for w in words):
            continue
        if start == 0 and not text[len(words[0]):].lstrip().startswith(":") and len(words) == len(m.group(1).split()):
            continue
        out.append((start, " ".join(words)))
    return out


#: Event nouns of a case study: a clause that names one of its own is about that event.
_OWN_EVENT_RE = re.compile(r"\b(?:aftershocks?|foreshocks?|earthquakes?|quakes?|tremors?|eruptions?|tsunamis?|storms?|floods?|cyclones?|"
                           r"hurricanes?|typhoons?|droughts?|landslides?|wildfires?|fires?)\b", re.IGNORECASE)


def _anchor(text: str, at: int, para_before: str, places: Optional[list[tuple[int, str]]] = None,
            fallback: Optional[list[Optional[str]]] = None, bounds: Optional[list[int]] = None) -> Optional[str]:
    """The proper name nearest to ``at`` in the sentence (the first of two at the same distance), else the last of the paragraph
    before it. ``places`` (from :func:`_places`) and ``fallback`` (a one-item memo) are read once per sentence by the caller: a scan
    per figure was O(figures x names) on a long sentence."""
    import bisect
    if places is None:
        places = _places(text)
    if places:
        # the places of the figure's own clause first ("The Darfield earthquake was magnitude 7.1; the Christchurch aftershock was
        # magnitude 6.2": each magnitude is its own clause's event, attack round 4)
        # (the clause bounds, ";" and line breaks, are read once per sentence by the caller and found by bisection; the names of
        # the clause are an index range of ``places``, never a copied slice: attack round 7 measured the per-figure scans and slices
        # as quadratic on one long sentence)
        if bounds is None:
            bounds = [i for i, c in enumerate(text) if c in ";\n"]
        b = bisect.bisect_left(bounds, at)
        lo = bounds[b - 1] + 1 if b > 0 else 0
        hi = bounds[b] if b < len(bounds) else len(text)
        a_lo = bisect.bisect_left(places, (lo, ""))
        a_hi = bisect.bisect_left(places, (hi, ""))
        if a_hi > a_lo:
            first, last = a_lo, a_hi
        elif (lo > 0 or hi < len(text)) and _OWN_EVENT_RE.search(text, lo, hi):
            return ""  # a clause naming an event of its own and no place ("; the February 2011 aftershock was magnitude 6.2": attack
            # round 5): never the event a place in another clause names
        else:
            first, last = 0, len(places)
        k = bisect.bisect_left(places, (at, ""), first, last)
        cands = [places[j] for j in (k - 1, k) if first <= j < last]
        best = min(cands, key=lambda p: (abs(p[0] - at), p[0]))
        return best[1]
    if fallback is not None and fallback:
        return fallback[0]
    last = None
    for m in _PROPER_RE.finditer(para_before[-2000:]):
        if m.group(1).split()[0] not in _NOT_PLACES:
            last = m.group(1)
    if fallback is not None:
        fallback.append(last)
    return last


def _case_consistency(ctx: _Ctx, sentences: list[_Sentence], text: str) -> None:
    from .packs import _paragraphs
    paras = dict(_paragraphs(text[:MAX_TEXT]))
    index: dict[tuple[str, str], list[tuple[Fraction, Fraction, str, _Sentence, str]]] = {}
    placeless: list[tuple[str, tuple]] = []
    for s in sentences:
        para = paras.get(s.paragraph, "")
        upto = para[:max(0, para.find(s.text))] if s.text in para else ""
        places: Optional[list[tuple[int, str]]] = None
        bounds: Optional[list[int]] = None
        fallback: list[Optional[str]] = []
        found = []
        for m in _CASE_FIG_RE.finditer(s.text):
            found.append((m, m.group("n") or m.group("m"), _HEAD_NOUNS[(m.group("noun") or m.group("verb")).lower()],
                          (m.group("pre") or m.group("pre2") or "").strip().lower(), (m.group("sc") or m.group("sc2") or "").lower()))
        for m in _OF_THEM_RE.finditer(s.text):
            heads = list(_HEAD_BEFORE_RE.finditer(s.text, 0, m.start()))
            if heads:
                found.append((m, m.group("n"), _HEAD_NOUNS[heads[-1].group(1).lower()], (m.group("pre") or "").strip().lower(), ""))
        for m in _MAGNITUDE_RE.finditer(s.text):
            found.append((m, m.group("n") or m.group("m"), "magnitude", "", ""))
        for m, raw, noun, pre, sc in found:
            if places is None:
                places = _places(s.text)
                bounds = [i for i, c in enumerate(s.text) if c in ";\n"]
            v = Fraction(raw.replace(",", "")) * (_SCALE_WORDS[sc] if sc else 1)
            if pre in ("more than", "over", "at least"):
                lo, hi = v, None
            elif pre in ("fewer than", "less than", "under", "up to"):
                lo, hi = Fraction(0), v
            elif pre in ("about", "around", "roughly", "approximately", "nearly", "almost", "some"):
                lo, hi = v * Fraction(95, 100), v * Fraction(105, 100)
            else:
                lo, hi = v, v
            anchor = _anchor(s.text, m.start(), upto, places, fallback, bounds)
            if anchor == "":
                continue  # an event of its own with no place named: compared with nothing
            if anchor is None:
                placeless.append((noun, (lo, hi if hi is not None else Fraction(-1), m.group(0), s, raw)))
                continue
            key = (anchor, noun)
            if len(index) >= 64 and key not in index:
                continue
            bucket = index.setdefault(key, [])
            if len(bucket) < 16:
                bucket.append((lo, hi if hi is not None else Fraction(-1), m.group(0), s, raw))
    # a case quantity stated with no place (its sentence and paragraph name none) belongs to the one place the answer gives that
    # quantity for, when there is exactly one ("The Earthquake Commission's 407,000 claims ..." after "... received more than 470,000
    # claims" of New Zealand; attack round 3)
    for noun, item in placeless:
        keys = [k for k in index if k[1] == noun]
        if len(keys) == 1 and len(index[keys[0]]) < 16:
            index[keys[0]].append(item)
    for (anchor, noun), items in index.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                lo1, hi1, p1, s1, r1 = items[i]
                lo2, hi2, p2, s2, r2 = items[j]
                h1 = None if hi1 < 0 else hi1
                h2 = None if hi2 < 0 else hi2
                disjoint = (h1 is not None and h1 < lo2) or (h2 is not None and h2 < lo1)
                if not disjoint:
                    continue
                v1, v2 = Fraction(r1.replace(",", "")), Fraction(r2.replace(",", ""))
                ctx.add("geo_case_consistency", lambda cid, v1=v1, v2=v2, p1=p1, p2=p2, s1=s1, s2=s2, anchor=anchor, noun=noun: make_check(
                    ctx.report, check_id=cid, kind="geo_case_consistency",
                    inputs=[("first", v1, f"the {noun} of {anchor} first stated ({p1})"), ("second", v2, f"the {noun} of {anchor} stated again ({p2})")],
                    conclusion={"op": "eq", "left": _var("first"), "right": _var("second")},
                    label=f"the {noun} of {anchor}: '{p1}' and '{p2}' state one quantity",
                    description=(f"one case quantity stated twice: '{_excerpt(s1.text, 160)}' and '{_excerpt(s2.text, 160)}' ({noun}, {anchor}) "
                                 f"[the two statements must agree; bounds ('more than') are compared as intervals and a pair is built only when they cannot meet]"),
                    claim_ids=tuple(dict.fromkeys(_claims(ctx.report, s1.text, p1) + _claims(ctx.report, s2.text, p2))), severity="warning", defect="contradiction"))
                break


# ------------------------------------------------------------------------------------------------------------------ the pack
_FIGURE_SOURCE_RE = re.compile(r"\b(?P<src>(?:the\s+)?(?:population\s+pyramid|hydrograph|choropleth(?:\s+map)?|map|graph|photograph|photo|figure\s*+\d{1,2}|fig\.\s*+\d{1,2}))"
                               r"\s+(?:shows?|gives?|indicates?|suggests?|reveals?|records?|displays?)\b", re.IGNORECASE)
_SOURCES_LINE_RE = re.compile(r"^[ \t]*+\**+(?:sources?|references?|bibliography)[ \t]*+\**+[ \t]*+:", re.IGNORECASE | re.MULTILINE)
_YEAR_IN_RE = re.compile(r"\b(?:1[89]\d{2}|20\d{2})\b")
_NON_YEAR_FIG_RE = re.compile(r"(?<![\d.,])(?!(?:1[89]\d{2}|20\d{2})\b)\d{1,3}(?:,\d{3})++|(?<![\d.,])(?!(?:1[89]\d{2}|20\d{2})\b)\d{2,9}(?:\.\d+)?\b")


@dataclass
class _Built:
    checks: list
    findings: list
    decided: frozenset


_CACHE: dict[tuple, _Built] = {}
_CACHE_MAX = 32


def _inputs_key(report: SpecialistReport, request_text: Optional[str]) -> str:
    """A digest of everything the build reads: the response, every claim's text, the request and every supplied text's content,
    title and author (a cache keyed by ids alone served one document's verdict for another's figures)."""
    import hashlib
    h = hashlib.sha256()
    for part in ([report.original_response or "", request_text or "", str(report.task_type or "")] +
                 [getattr(c, "claim_text", "") or "" for c in report.claims] +
                 [f"{t.document_id}\x1f{t.title or ''}\x1f{getattr(t, 'author', '') or ''}\x1f{t.text}" for t in report.supplied_texts]):
        h.update(part.encode("utf-8", "surrogatepass"))
        h.update(b"\x1e")
    return h.hexdigest()


def _build(report: SpecialistReport, request_text: Optional[str]) -> _Built:
    key = (report.report_id, report.response_sha256, _inputs_key(report, request_text))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    text = report.original_response or ""
    ctx = _Ctx(report, [], [], set(), {})
    sentences = _sentences(text)
    tables = _attribute_tables(list(report.supplied_texts)) if report.supplied_texts else []
    from .grounded_figures import supplied_tables
    year_tables = supplied_tables(list(report.supplied_texts)) if report.supplied_texts else []
    for k, s in enumerate(sentences):
        if len(ctx.checks) >= MAX_PER_REPORT:
            ctx.skip("sentence", sum(1 for t in sentences[k:] if re.search(r"\d", t.text)))
            break
        if not re.search(r"\d", s.text):
            continue
        for reader in (_density, _rate_per_thousand, _natural_increase, _doubling, _per_capita, _growth_rate, _mean, _sampling, _significance,
                       _fold, _change_by, _times_pair, _from_to_percent, _bracket_comparison):
            _guarded(ctx, reader.__name__.strip("_"), lambda reader=reader: reader(ctx, s))
        if year_tables:
            _guarded(ctx, "table_change_by", lambda: _table_change_by(ctx, s, year_tables))
        if tables:
            _guarded(ctx, "table_figures", lambda: _table_figures(ctx, s, tables))
            _guarded(ctx, "table_aggregates", lambda: _table_aggregates(ctx, s, tables))
            _guarded(ctx, "table_superlative", lambda: _table_superlative(ctx, s, tables))
    if tables:
        for s in sentences:
            _guarded(ctx, "table_count", lambda s=s: _table_count(ctx, s, tables))
    _guarded(ctx, "case_consistency", lambda: _case_consistency(ctx, sentences, text))
    if ctx.dropped:
        ctx.findings.append(_bound_finding(ctx.dropped))
    built = _Built(ctx.checks, ctx.findings, frozenset(ctx.decided))
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = built
    return built


def _bound_finding(dropped: dict) -> StructuralFinding:
    """CORE-QNT-001 (warning) naming the statements the pack's bounds left unread (attack round 3): the receipt never implies that
    every stated figure was checked when the bound stopped the reading."""
    n = sum(dropped.values())
    kinds = ", ".join(f"{k.replace('geo_', '').replace('_', ' ')} ({v})" for k, v in sorted(dropped.items()))
    return StructuralFinding(
        code="CORE-QNT-001", severity="warning", claim_ids=[],
        message=(f"the Geography pack's reading bound was reached ({MAX_PER_KIND} checks of a kind, {MAX_PER_REPORT} in all): {n} further "
                 f"statement(s) or figure(s) were left unread and are not checked [{kinds}]"),
        rule_source="Geography pack: a statement the bound leaves unread is named undecided, never dropped silently")


def _guarded(ctx: _Ctx, stage: str, fn) -> None:
    """Run one reader on its own: an arithmetic edge it cannot read (a zero divisor) is no statement; any other failure adds BR-INTERNAL-001
    naming the pack and the stage (once per stage), and every other reader still runs."""
    try:
        fn()
    except ArithmeticError:
        return
    except Exception as exc:  # noqa: BLE001 - reported on the receipt, never silent
        if any(f.code == "BR-INTERNAL-001" and f"during {stage}" in f.message for f in ctx.findings):
            return
        ctx.findings.append(StructuralFinding(code="BR-INTERNAL-001", severity="warning",
                                              message=(f"pack 'geography' failed internally ({type(exc).__name__}) during {stage}; its findings and checks are "
                                                       "missing from this receipt, and the router must not treat the pack as passed"),
                                              rule_source="branch infrastructure: a pack failure is named, never silent"))


def decided_statements(report: SpecialistReport) -> set[str]:
    """The statements (whitespace-normalised sentences) whose figures the Geography pack decided, so the core pack's undecided reader
    never names one of them beside a verdict (``packs.pack_decided_equations``)."""
    try:
        return set(_build(report, None).decided)
    except Exception:  # noqa: BLE001 - the pack's own run names a failure (PACK-INTERNAL-001); nothing decided here
        return set()


class GeographyPack:
    """The Geography pack: GEN-STR-001 (unknown supporting claims), CORE-QNT-001 for a Geography rate read but not built, CORE-SRC-002
    for a figure credited to an unsupplied map, graph or figure and for an uncredited case-study figure, and the formal checks of the
    module docstring. It never reads, filters or re-words a self-report: the core pack before it holds the one shared gate."""
    name = "geography"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f = list(unknown_supports_findings(report))
        out: list[StructuralFinding] = []
        for what, fn in (("undecided Geography rates", lambda: list(_build(report, request_text).findings)),
                         ("unsupplied figures", lambda: self._unsupplied_figures(report, request_text))):
            try:
                out += fn()
            except Exception as exc:  # noqa: BLE001 - reported, never silent
                out.append(StructuralFinding(code="BR-INTERNAL-001", severity="warning",
                                             message=f"pack 'geography' failed internally ({type(exc).__name__}) during {what}; its findings are missing from this "
                                                     "receipt, and the router must not treat the pack as passed",
                                             rule_source="branch infrastructure: a pack failure is named, never silent"))
        return f + out

    @staticmethod
    def _unsupplied_figures(report: SpecialistReport, request_text: Optional[str]) -> list[StructuralFinding]:
        from .packs import _labels_figures_from_memory, _unsourced_world_figures
        text = report.original_response or ""
        named: set[str] = set()
        for x in _unsourced_world_figures(report, request_text):
            named.update(x.claim_ids)
        titles = " ".join(f"{t.document_id} {t.title or ''}" for t in report.supplied_texts).lower()
        out: list[StructuralFinding] = []
        rule = "Geography: the specialist cannot see figures, maps or graphs that were not supplied; a value read from one cannot be checked (working rule)"
        for s in _sentences(text):
            m = _FIGURE_SOURCE_RE.search(s.text)
            if m is None or not _NON_YEAR_FIG_RE.search(s.text):
                continue
            src = " ".join(m.group("src").lower().replace("the ", "").split())
            if src and src in titles:
                continue
            ids = [c for c in _claims(report, s.text, m.group(0)) if c not in named]
            if not ids:
                continue
            named.update(ids)
            out.append(StructuralFinding(code="CORE-SRC-002", severity="info", claim_ids=ids[:8], rule_source=rule,
                                         message=f"paragraph {s.paragraph}: a figure credited to '{m.group('src')}': the figure's source was not supplied; a value "
                                                 "read from an unsupplied figure cannot be checked"))
            if len(out) >= 32:
                return out
        if report.supplied_texts or _SOURCES_LINE_RE.search(text) or _labels_figures_from_memory(text):
            return out
        for s in _sentences(text):
            if not _YEAR_IN_RE.search(s.text) or not _NON_YEAR_FIG_RE.search(s.text) or _anchor(s.text, 0, "") is None:
                continue
            ids = [c for c in _claims(report, s.text, s.text[:60]) if c not in named]
            if not ids:
                continue
            named.update(ids)
            out.append(StructuralFinding(code="CORE-SRC-002", severity="info", claim_ids=ids[:8],
                                         rule_source="Geography: a case-study figure needs a supplied source, a credit or a from-memory label (working rule)",
                                         message=f"paragraph {s.paragraph}: a case-study figure (a named place, a year and a figure) with no supplied source, no credit "
                                                 "and no from-memory label; it cannot be checked"))
            if len(out) >= 32:
                break
        return out

    def formal_checks_for(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[FormalCheck]:
        from .packs import _worked_checks
        out = list(_build(report, request_text).checks)
        try:
            out += _worked_checks(report, "geography-worked", set())
        except Exception:  # noqa: BLE001 - the core pack's undecided reader still names every worked equation
            pass
        return out

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return self.formal_checks_for(report, None)
