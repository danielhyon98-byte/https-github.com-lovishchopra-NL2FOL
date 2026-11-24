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
``geo_case_consistency``  one case quantity (or one word limit) stated twice with different values INT-SUBJ-004
``geo_significance``      a coefficient against a stated critical value and verdict                INT-SUBJ-001
``geo_pair_comparison``   a difference, relative difference, multiple or share stated before the   INT-SUBJ-001
                          pair it rests on ('(36 mm against 38 mm)', '(130 of 185)'), or a
                          multiple or relative difference of two labelled figures of the request
                          ('that of Storm 1', '10% less rain than Storm 1')
``geo_request_figure``    a figure, a labelled date or a word figure of the request restated       INT-SUBJ-004
``geo_conversion``        a unit conversion stated outright ('12 hours is 720 minutes')            INT-SUBJ-001
``geo_n_formula``         a formula in n with n given ('With six pairs, n³ − n = 210')             INT-SUBJ-001
``geo_word_count``        a word count the answer states of itself                                 INT-SUBJ-004
``geo_dimension_area``    an area stated with the two dimensions it is the product of              INT-SUBJ-001
``geo_depth_volume``      a volume stated with a depth of water and the area it covers             INT-SUBJ-001
``geo_share_part``        a part stated with its share of a whole and the whole ('8% of the 24 km² INT-SUBJ-001
                          catchment, about 1.9 km²')
``geo_clock_interval``    an interval (or a lag time) between two events whose clock times the     INT-SUBJ-001
                          request gives for one label
``geo_table_derived``     a share row's amount in the total row's unit, a figure per person, a     INT-SUBJ-001 credited,
                          row's relative change, a share row's complement, from a year table       INT-SUBJ-004 otherwise
``geo_table_spacing``     the spacing (and span) of the sites a supplied table lists by distance   INT-SUBJ-004
``geo_event_relation``    an interval or a multiple between two events the answer itself dates,    INT-SUBJ-001
                          or the rest of a total whose part the answer states
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
from bisect import bisect_left, bisect_right
from functools import lru_cache
from typing import Optional

from ..translate.contracts import SpecialistReport, StructuralFinding, SuppliedText
from .base import FormalCheck
from .grounded_figures import FUNCTION_WORDS as _FUNCTION_WORDS
from .insertions import _EN_FINITE_RE, insertion_spans, masked, span_holding

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
    #: the request's text, for a figure's object the request never names with that figure (check round 12 of c3f)
    request_text: str = ""

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


#: A yearly growth rate (attack round 8 widened it from the growth verbs to any per cent a year, and "r = 2"): "growth rate of 2% a year",
#: "grew by about 1.2% a year", "At 2% a year", "2% per annum", "2% annually", "r = 2".
_GROWTH_RATE_RE = re.compile(r"(?:\b(?:growth\s+rate\s+(?:of|is|was|=)?|growing\s+at|grows\s+at|grew\s+at|growth\s+of|increasing\s+at|rising\s+at|grows\s+by|"
                             r"growing\s+by|grew\s+by|rose\s+by|increased\s+by|rate\s+of|at)\s*+)?"
                             r"(?:about\s+|around\s+|roughly\s+|approximately\s+)?" + _num_re("r", scale=False)
                             + r"\s*+(?:%|per\s*+cent\b|percent\b)\s*+(?:(?:a|per|each|every)\s++(?:year|annum)\b|annually\b|p\.a\.)"
                             r"|\br\s*+=\s*+" + _num_re("q", scale=False) + r"(?:\s*+%)?", re.IGNORECASE)
#: A doubling time stated (the rule written out between the words and the figure is read past: "doubling time = 70/r = 25 years",
#: "doubles in 70/2 ="): "doubles in 35 years", "would double in roughly 48 years", "take 48 years to double", "doubling time of 48 years".
_DOUBLE_RE = re.compile(r"\b(?:doubl(?:es?|ed|ing)\s+(?:in|within|after|every)|doubling\s+time\s+(?:of|is|was|=)?|(?:take|takes|took|taking)\s++(?=[^.;]{0,40}?\bto\s+double\b))\s*+"
                        r"(?:(?:69|70|72)\s*+(?:/|÷)\s*+(?:r|g|\d{1,2}(?:\.\d{1,3})?)\s*+(?:%\s*+)?[=≈]\s*+)?"
                        r"(?:about\s+|around\s+|roughly\s+|approximately\s+|nearly\s+|just\s+over\s+|over\s+|under\s+|less\s+than\s+|more\s+than\s+)?"
                        + _num_re("t", scale=False) + r"\s*+years?\b", re.IGNORECASE)


def _doubling(ctx: _Ctx, s: _Sentence) -> None:
    dbl = _DOUBLE_RE.search(s.text)
    if dbl is None:
        return
    # the rate of the sentence, else of the sentence before it ("Ostrel's supply grew by about 1.2% a year. At that rate it would double
    # in roughly 48 years."); a sentence with two rates is not read
    rates = [g for g in _GROWTH_RATE_RE.finditer(s.text) if not (dbl.start() <= g.start() < dbl.end())]
    src = s.text
    if not rates and s.before:
        rates, src = list(_GROWTH_RATE_RE.finditer(s.before)), s.before
    values = {(g.group("r") or g.group("q")) for g in rates}
    if len(values) != 1:
        return
    g = rates[0]
    r = _fig(g, "r", src) if g.group("r") else _fig(g, "q", src)
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


#: Units of a total and of its figure per person that the pack converts exactly (attack round 8: '48 GJ (1,050 PJ ÷ 24.9 million people)').
_QTY_UNITS = {"J": ("J", Fraction(1)), "kJ": ("J", Fraction(10**3)), "MJ": ("J", Fraction(10**6)), "GJ": ("J", Fraction(10**9)), "TJ": ("J", Fraction(10**12)),
              "PJ": ("J", Fraction(10**15)), "EJ": ("J", Fraction(10**18)), "Wh": ("J", Fraction(3600)), "kWh": ("J", Fraction(3_600_000)),
              "MWh": ("J", Fraction(3_600_000_000)), "GWh": ("J", Fraction(3_600_000_000_000)), "TWh": ("J", Fraction(3_600_000_000_000_000)),
              "kg": ("kg", Fraction(1)), "t": ("kg", Fraction(1000)), "tonnes": ("kg", Fraction(1000)), "tonne": ("kg", Fraction(1000)),
              "Mt": ("kg", Fraction(10**9))}
_QTY_UNIT = r"(?P<{g}u>kJ|MJ|GJ|TJ|PJ|EJ|kWh|MWh|GWh|TWh|Wh|J|kg|tonnes?|Mt|t)(?![\w²³])"
_PER_CAPITA_RE = re.compile(r"\bper\s++(?:capita|person|head)\s*+(?:of|is|was|=|:|,|at)?\s*+(?:about\s+|around\s+|roughly\s+|approximately\s+)?"
                            + _num_re("x", currency=True) + r"(?:\s*+" + _QTY_UNIT.format(g="x") + r")?"
                            + r"|" + _num_re("y", currency=True) + r"(?:\s*+" + _QTY_UNIT.format(g="y") + r")?\s++(?:per\s++(?:capita|person|head)|a\s++head)\b", re.IGNORECASE)
#: A total divided among the population right after it ("1,050 PJ shared among 24.9 million people", "divided by 24.9 million").
_SHARED_AMONG_RE = re.compile(r"\s*+(?:shared|divided|spread|split)\s++(?:among|amongst|between|by|over)\s++(?:about\s+|around\s+|roughly\s+)?\d",
                              re.IGNORECASE)
_QTY_TOTAL_RE = re.compile(_num_re("v") + r"\s*+" + _QTY_UNIT.format(g="v"))
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
    xu = pm.group("xu") if pm.group("x") else pm.group("yu")
    factor = Fraction(1)
    if xu:
        # a figure per person in a unit of energy or mass, its total in another of the same kind ('48 GJ ... (1,050 PJ ÷ 24.9 million
        # people)'): the total converted exactly into the figure's unit (attack round 8)
        kind, fx = _QTY_UNITS.get(xu, _QTY_UNITS.get(xu.lower(), (None, None)))
        qt = [(m, _QTY_UNITS.get(m.group("vu"), _QTY_UNITS.get(m.group("vu").lower(), (None, None)))) for m in _QTY_TOTAL_RE.finditer(s.text)
              if not (pm.start() <= m.start("v") < pm.end())]
        qt = [(m, f) for m, (k, f) in qt if k == kind and k is not None]
        if kind is None or len(qt) != 1:
            return
        tot = _fig(qt[0][0], "v", s.text)
        factor = qt[0][1] / fx
        if pm.group("x") and _SHARED_AMONG_RE.match(s.text, pm.end()) and pm.end() <= p.start:
            # 'per person, 1,050 PJ shared among 24.9 million people, was about 42 GJ': the figure after the comma is the total being
            # divided, the other one the figure per person (check round 12 of c3f had charged the correct 42 GJ)
            x, tot = tot, x
            factor = fx / qt[0][1]
    else:
        totals = [_fig(m, "v", s.text) for m in _TOTAL_RE.finditer(s.text) if m.group("vcur") and not (pm.start() <= m.start("v") < pm.end())]
        if x.currency:
            totals = [t for t in totals if t.currency == x.currency]
        if len(totals) != 1:
            return
        tot = totals[0]
    ctx.decided.add(" ".join(s.text.split()))
    expr = {"op": "div", "left": _var("total"), "right": _real(p.value / factor)}
    ctx.add("geo_per_capita", lambda cid: make_check(
        ctx.report, check_id=cid, kind="geo_per_capita", inputs=[("total", tot.value, f"the total stated ({tot.shown})")],
        conclusion=band(expr, x), label=f"stated figure per capita {x.shown} against {tot.shown} / {p.shown}",
        description=f"{_excerpt(s.text)} [a figure per capita = total / population, scale words applied; {_RULE.format(tau=5 if x.approx else 1)}]",
        claim_ids=_claims(ctx.report, s.text, pm.group(0)), defect="stem_arithmetic_slip"))


_YEAR = r"(?P<{g}>1[89]\d{{2}}|20\d{{2}})"
_FROM_TO_RE = re.compile(r"\bfrom\s++(?:about\s++)?" + _num_re("v0") + r"(?:\s++[a-z]{1,20}){0,3}?\s++in\s++" + _YEAR.format(g="y0")
                         + r"\s++to\s++(?:about\s++)?" + _num_re("v1") + r"(?:\s++[a-z]{1,20}){0,3}?\s++in\s++" + _YEAR.format(g="y1") + r"\b", re.IGNORECASE)
#: The period first, its pair in brackets after it (attack round 8): "between 2005 and 2025 (820 PJ to 1,050 PJ)", "from 2005 to 2025 (from 21.4
#: million to 24.9 million)".
_PERIOD_PAIR_RE = re.compile(r"\b(?:between|from)\s++" + _YEAR.format(g="y0") + r"\s++(?:and|to)\s++"
                             + _YEAR.format(g="y1") + r"\s*+[(,]\s*+(?:from\s++)?(?:about\s++)?" + _num_re("v0") + r"(?:\s++[A-Za-z]{1,12}){0,2}?\s++(?:to|→)\s++"
                             r"(?:about\s++)?" + _num_re("v1"), re.IGNORECASE)
_ANNUAL_RE = re.compile(r"\b(?:average\s+)?annual\s+(?:average\s+)?(?:population\s+)?(?:growth\s+)?rate\s*+(?:of|is|was|=|:)?\s*+(?:about\s+|around\s+|roughly\s+)?"
                        + _num_re("k", scale=False) + r"\s*+(?:%|per\s*+cent\b|percent\b)|"
                        r"\b(?:average\s+)?annual\s+(?:average\s+)?(?:population\s+)?growth(?:\s+rate)?\s*+(?:of|is|was|=|:)?\s*+(?:about\s+|around\s+|roughly\s+)?"
                        + _num_re("g", scale=False) + r"\s*+(?:%|per\s*+cent\b|percent\b)"
                        r"|\b(?:grew|rose|increased|growing)\s+(?:by\s+)?(?:an\s+average\s+of\s+|on\s+average\s+)?(?:about\s+)?" + _num_re("h", scale=False)
                        + r"\s*+(?:%|per\s*+cent\b|percent\b)\s*+(?:a|per|each)\s++year\b", re.IGNORECASE)


def _growth_rate(ctx: _Ctx, s: _Sentence) -> None:
    ft, an = _FROM_TO_RE.search(s.text) or _PERIOD_PAIR_RE.search(s.text), _ANNUAL_RE.search(s.text)
    if ft is None or an is None:
        return
    v0, v1 = _fig(ft, "v0", s.text), _fig(ft, "v1", s.text)
    g = _fig(an, "g", s.text) if an.group("g") else _fig(an, "k", s.text) if an.group("k") else _fig(an, "h", s.text)
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
_STOPWORDS = frozenset("the and of in on at for by to from with per out total mean number share data value values use".split()) | _FUNCTION_WORDS


def _row_words(label: str) -> set[str]:
    """The words of three or more letters of a row's label that can name it: never a function word."""
    return {w for w in re.findall(r"[a-z]{3,}", label.lower()) if w not in _FUNCTION_WORDS}


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


@lru_cache(maxsize=64)
def _row_patterns(table: _AttrTable) -> tuple[Optional[re.Pattern], tuple[tuple[int, str, Optional[re.Pattern]], ...]]:
    """The patterns :func:`_row_named` reads ``table``'s rows with: the list of row labels after the row noun (None without a row
    noun), and per row with a label its index, its label in lower case and the pattern that names it (None for a label of fewer than
    three characters with no row noun). They depend on the table alone: built once per table, never again for every sentence (repair
    1 after clearance c3c: rebuilding them for each of thousands of sentences was about two thirds of the pack's time)."""
    listed = None
    if table.row_noun:
        listed = re.compile(rf"\b{re.escape(table.row_noun)}s?\s++([a-z0-9]{{1,3}}(?:\s*+,\s*+[a-z0-9]{{1,3}}){{0,20}}+\s*+,?\s*+(?:and|or|&|to)\s++"
                            rf"[a-z0-9]{{1,3}})\b")
    rows: list[tuple[int, str, Optional[re.Pattern]]] = []
    for k, (label, _cells) in enumerate(table.rows):
        lab = label.strip().lower()
        if not lab:
            continue
        pat = None
        if table.row_noun and re.fullmatch(r"[a-z0-9]{1,3}", lab):
            pat = re.compile(rf"\b{re.escape(table.row_noun)}s?\s++{re.escape(lab)}\b")
        elif len(lab) >= 3:
            pat = re.compile(rf"(?<![\w-]){re.escape(lab)}(?![\w-])")
        rows.append((k, lab, pat))
    return listed, tuple(rows)


def _row_named(table: _AttrTable, clause: str) -> list[int]:
    found = []
    low = clause.lower()
    listed: set[str] = set()
    listed_re, rows = _row_patterns(table)
    if listed_re is not None:
        # a list of row labels after the row noun ("Sites 1, 2 and 3"): every label of it is named, so no single row is
        for lm in listed_re.finditer(low):
            listed.update(x for x in re.split(r"\s*+(?:,|and|or|&|to)\s*+", lm.group(1)) if x)
    for k, lab, pat in rows:
        if lab in listed:
            found.append(k)
            continue
        if pat is not None and pat.search(low):
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
        spans = insertion_spans(s.text)
        if spans:
            # the column word and the row are the figure's own clause's: a figure outside every insertion takes neither from inside one,
            # a figure inside one takes its column word from that one (push check of 08c4a36b: 'The pedestrian count, as retail use
            # fell, was 60 at site 4.'); otherwise each figure is read with its own row and column
            starts_ = [a for a, _b in spans]
            home = span_holding(spans, starts_, figure.start())
            col_home = span_holding(spans, starts_, toks[idx].start())
            row_out = home is not None or rows[0] in _row_named(table, masked(s.text, spans))
            if col_home != home or not row_out:
                _table_cells(ctx, s, table, credited)
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
                                  r"(?:%|\s*+per\s+cent|\s*+percent)\s*+of\s++(?:that|those|the\s+\w+)\s++(?:at|in|for|of)\b|"
                                  # a per cent of another row's figure ("9% of Site 1's (19 ÷ 214)": check round 9 of c3c): a ratio of
                                  # two cells, never a cell
                                  r"(?:%|\s*+per\s+cent|\s*+percent)\s*+of\s++(?:site|station|point|sample|row|zone|area|transect)\s*+\d{1,3}\b)",
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
#: A figure placed at a row named after it, words between ("97 counted at site 4", "97 pedestrians of site 4"): read at its end.
_PLACED_AFTER_RE = re.compile(r"\b(?:at|in|for|of|from)\s*+\Z", re.IGNORECASE)


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
    # each clause of a contrast is read alone ("... at Site 10, while retail use fell from 92% to 0%"); a contrast inserted between a
    # subject and its verb ("The pedestrian count at site 2, although the EQS was low, was 186") is an insertion of the clause around
    # it, which reads it blanked (push check of 08c4a36b)
    spans = insertion_spans(s.text)
    starts_ = [a for a, _b in spans]
    pos = 0
    for m in _CONTRAST_SPLIT_RE.finditer(s.text):
        held = span_holding(spans, starts_, m.start()) if m.group(0) != ";" else None
        if held is not None and s.text[held[1]:].strip(" .!?;:\n") and s.text[:held[1]].rstrip()[-1:] in ",–—-":
            continue  # (an insertion closed by its comma or dash, the main clause going on after it)
        part = s.text[pos:m.start()]
        if part.strip():
            _table_cells_clause(ctx, s, table, credited, part)
        pos = m.end()
    part = s.text[pos:]
    if part.strip():
        _table_cells_clause(ctx, s, table, credited, part)


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
    colpos_all = [(i, next(iter(colstem[_stem(t.group(0))]))) for i, t in enumerate(toks)
                  if t.group(0)[0].isalpha() and len(colstem.get(_stem(t.group(0)), ())) == 1]
    # a figure outside every insertion (a subordinate or parenthetical clause, an apposition) is read with no column word and no row
    # of one, and its clause cuts are read with the insertions blanked ('At site 2 the EQS, with pedestrian numbers high, was 186.' is
    # the EQS: push check of 08c4a36b); a figure inside one keeps its own clause's words
    spans = insertion_spans(text)
    starts_ = [a for a, _b in spans]
    plain_text, plain_mentions = text, mentions
    if spans:
        blank = masked(text, spans)
        inside = [span_holding(spans, starts_, t.start()) is not None for t in toks]
        colpos_out = [(j, c) for j, c in colpos_all if not inside[j]]
        mentions_out = [m for m in mentions if not inside[m[0]]]
        rank_out, n_out = [], 0
        for x in inside:
            rank_out.append(n_out)
            n_out += 0 if x else 1
    rank_all = range(len(toks))
    last_col = None
    for i, t in enumerate(toks):
        if i in in_mention or not t.group(0)[0].isdigit():
            continue
        if spans and not inside[i]:
            colpos, text, mentions, rk = colpos_out, blank, mentions_out, rank_out  # (distances counted in the words outside)
            if not mentions:
                continue
        else:
            colpos, text, mentions, rk = colpos_all, plain_text, plain_mentions, rank_all
        shown = t.group(0)
        if re.fullmatch(r"(?:1[89]\d{2}|20\d{2})", shown):
            continue
        before = text[max(0, t.start() - 14):t.start()]
        after = text[t.end():t.end() + 12]
        if _NOT_A_CELL_BEFORE_RE.search(before) or _NOT_A_CELL_AFTER_RE.match(text[t.end():t.end() + 40]) or \
                _DERIVED_BEFORE_RE.search(text[max(0, t.start() - 48):t.start()]):
            continue
        # a column named after the figure beyond a clause cut is another clause's ('The pedestrian count at site 4 was 97, and the EQS
        # fell by 13 points' reads 97 as the count, never as the EQS: check round 12 of c3f); with no column near, the one its own clause
        # names before it
        near = sorted((abs(rk[j] - rk[i]), c) for j, c in colpos
                      if abs(rk[j] - rk[i]) <= 4 and not (j > i and _CELL_CLAUSE_CUT_RE.search(text, t.end(), toks[j].start())))
        if not near:
            own = [(rk[i] - rk[j], c) for j, c in colpos if rk[i] - 8 <= rk[j] and j < i and not _CELL_CLAUSE_CUT_RE.search(text, toks[j].end(), t.start())]
            near = own[-1:]
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
            row_adjacent = (prev and rk[i] - rk[prev[-1][1]] <= 2) or (nxt and rk[nxt[0][0]] - rk[i] <= 2)
            if last_col is None or not (row_adjacent or i in respective):
                continue
            col = last_col
        last_col = col
        dist = sorted((min(abs(rk[a] - rk[i]), abs(rk[b] - rk[i])), a, r) for a, b, r in mentions)
        linked_after = [r for a, _b, r in mentions if a > i and _AT_ROW_RE.fullmatch(text[t.end():toks[a].start()])]
        before = [m for m in mentions if m[1] < i]
        if i not in respective and not linked_after and before and any(
                r != before[-1][2] and rk[a] - rk[i] <= 4 and not _CELL_CLAUSE_CUT_RE.search(text, t.end(), toks[a].start()) and
                _PLACED_AFTER_RE.search(text, t.end(), toks[a].start()) for a, _b, r in mentions if a > i):
            continue  # (a figure its own words place at another row, "Site 2, which had more pedestrians than the 97 counted at site
            # 4, ...": the row is not determined by the clause before it; no check, never the row named before; c3h check round 14)
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


_CELL_CLAUSE_CUT_RE = re.compile(r"[,;:]|\b(?:while|whilst|whereas|but)\b", re.IGNORECASE)


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

#: "300,000 deaths is about 160 times Christchurch's 185": a figure stated as a multiple of another figure the sentence writes (check
#: round 12 of c3f, ge-t16).
_TIMES_OF_RE = re.compile(r"(?<![\d.,])(?P<a>" + _NUM + r")(?![\d,]\d|\.\d)(?:\s++[a-z]{1,15}){0,2}\s++(?:is|was|are|were)\s++"
                          r"(?P<ap>about\s++|around\s++|roughly\s++|nearly\s++|almost\s++)?(?P<n>" + _WORD_NUMBER + r"|" + _NUM + r")\s++times\s++"
                          r"(?:[A-Z][\w-]{1,30}['’]s\s++|the\s++|that\s++of\s++[A-Z][\w-]{1,30},?\s++)?(?P<b>" + _NUM + r")(?![\d,]\d|\.\d|\s*+[%)])")


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
    # a period ("from 2005 to 2025", "between 2005 (…)") is no pair of values: two years are dates, read by the table readers (attack round 8)
    froms = [p for p in _PAIR_FROM_RE.finditer(s.text) if not (_YEAR_IN_RE.fullmatch(p.group("a")) and _YEAR_IN_RE.fullmatch(p.group("b")))]
    parens = [p for p in _PAIR_PAREN_RE.finditer(s.text) if not (_YEAR_IN_RE.fullmatch(p.group("a")) and _YEAR_IN_RE.fullmatch(p.group("b")))]
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
    for m in list(_TIMES_PAIR_RE.finditer(s.text)) + list(_TIMES_DIV_RE.finditer(s.text)) + list(_TIMES_OF_RE.finditer(s.text)):
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


_BY_PERIOD_RE = re.compile(r"\b(?:" + _CHANGE_VERB + r")\s++by\s++(?P<rel>an?\s++(?:relative|proportional)\s++)?(?P<ap>about\s++|around\s++|roughly\s++)?(?P<n>" + _NUM + r")\s*+"
                           r"(?P<u>percentage\s+points?\b|points?\b|million\b|billion\b|thousand\b|%|per\s*+cent\b|percent\b)?[^.;\d]{0,30}?\b(?:between\s++(?P<y1>\d{4})\s++and\s++(?P<y2>\d{4})|"
                           r"from\s++(?P<z1>\d{4})\s++to\s++(?P<z2>\d{4}))", re.IGNORECASE)
_BY_ALONE_RE = re.compile(r"\b(?:" + _CHANGE_VERB + r")\s++by\s++(?P<rel>(?!))?(?P<ap>about\s++|around\s++|roughly\s++)?(?P<n>" + _NUM + r")\s*+(?P<u>percentage\s+points?\b)",
                          re.IGNORECASE)


#: A word that fixes a change "by N%" of a share row as the relative change, not the change in points.
_RELATIVE_WORD_RE = re.compile(r"\b(?:relative|relatively|proportional|proportionally|in\s+relative\s+terms)\b", re.IGNORECASE)


@lru_cache(maxsize=256)
def _yt_index(text: str) -> "_YtIndex":
    """The row index of a sentence, built once per sentence text for every year-table reader."""
    return _YtIndex(text)


#: What makes a change an AMOUNT of a share row's item: "energy from oil", "the amount of ...", "natural gas supply", "oil use".
_AMOUNT_RE = re.compile(r"\b(?:energy|power|electricity|amount|quantity|volume|supply|supplies|supplied|use|used|consumption|production|"
                        r"produced|output|generation|generated|imports?|exports?)\b", re.IGNORECASE)
_SHARE_RE = re.compile(r"\b(?:share|shares|proportion|percentage|fraction|part|mix)\b", re.IGNORECASE)


def _names_amount(text: str, at: int) -> bool:
    """Whether the clause before ``at`` (the change verb) names an amount of the row's item and no share of it."""
    lo = max(text.rfind(".", 0, at), text.rfind(";", 0, at), 0)
    head = text[lo:at]
    return _AMOUNT_RE.search(head) is not None and _SHARE_RE.search(head) is None


def _yt_total_row(year_tables: list, document_id: str, y1: int, y2: int) -> Optional[tuple]:
    """The values for ``y1`` and ``y2`` of the one total row of the document's year tables (an amount, not a share), or None."""
    found = []
    for t in year_tables:
        if t.document_id != document_id:
            continue
        for entity, words in t.entities:
            if not re.search(r"\btotal\b", entity, re.IGNORECASE):
                continue
            cells = {c.year: c for c in t.cells if c.entity == entity and c.year is not None}
            if y1 in cells and y2 in cells and cells[y1].unit != "%" and cells[y2].unit != "%":
                found.append((cells[y1].value, cells[y2].value))
    return found[0] if len(found) == 1 else None


def _table_change_by(ctx: _Ctx, s: _Sentence, year_tables: list) -> None:
    """Attack round 3 (ge-t15): a change of a supplied year table's row stated by its size, over a period the sentence names ("grew by 330
    PJ between 2005 and 2025", "grew by 4.5 million between 2005 and 2025") or, in percentage points, over the row's two years ("The coal
    share fell by 16 percentage points"): the size equals the difference of the row's two cells (in the row's unit; a scale word the row
    states is the row's own)."""
    from .grounded_figures import _half
    dated_hits = [(m, True) for m in _BY_PERIOD_RE.finditer(s.text)]
    # (whether the sentence states a period is decided once, never once per change: check round 12 of c3f timed the per-match search
    # at 108 s for one 200k-character sentence)
    hits = dated_hits or [(m, False) for m in _BY_ALONE_RE.finditer(s.text)]
    if not hits:
        return
    index = _yt_index(s.text)
    for table in year_tables:
        for m, dated in hits:
            entity = index.row(table, m.start())  # (the row the change's own clause names; push check of a9129c78)
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
            n = _num(m.group("n"))
            v1, v2 = cells[y1].value, cells[y2].value
            if cells[y1].unit == "%" and _names_amount(s.text, m.start()):
                # a change of an AMOUNT of a share row's item ("Energy from oil fell by about 13% ...", "Natural gas supply rose by
                # about 88% ..."): the amount is the share × the document's total for each year, never the share itself; with no
                # total of both years there is no check (check round 11 of c3e: the share's own change had been read)
                totals = _yt_total_row(year_tables, table.document_id, y1, y2)
                if totals is None or unit.startswith(("percentage", "point")):
                    continue
                v1, v2 = v1 * totals[0] / 100, v2 * totals[1] / 100
                if not unit.startswith(("%", "per")):
                    continue  # (an absolute change of the amount is the shared readers' with the amount's unit)
                rel = abs(v2 - v1) / abs(v1) * 100 if v1 else None
                if rel is None or not ctx.room("geo_table_change"):
                    continue
                rtol = max(_half(m.group("n").replace(",", "")), rel / 100, Fraction(1, 10))
                rtol = max(rtol, rel / 20) if m.group("ap") else rtol
                ctx.decided.add(" ".join(s.text.split()))
                ctx.add("geo_table_change", lambda cid, n=n, rel=rel, rtol=rtol, m=m, entity=entity, y1=y1, y2=y2, table=table, totals=totals: make_check(
                    ctx.report, check_id=cid, kind="geo_table_change", inputs=[("stated", n, f"the change stated ({m.group('n')})")],
                    conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(rel)}), "right": _real(rtol)},
                    label=(f"the change by {m.group('n')} against the amount of '{entity}' of {table.document_id} from {y1} to {y2} "
                           f"(the share × the total, {_fmt(totals[0])} and {_fmt(totals[1])})"),
                    description=(f"{_excerpt(s.text)} [a change of an amount of a share row's item is the relative change of the share × the "
                                 f"total for the two years]"),
                    claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="error", defect="source_mismatch"))
                return
            diff = abs(v2 - v1)
            per_cent = unit.startswith(("%", "per")) and not unit.startswith("percentage")
            # the readings of the change stated: a change "by N%" of a row held in an amount (millions, PJ) is relative, (V1 − V0) / V0
            # × 100; of a row of shares it is either the relative change or the change in points (one reading holding is enough); any
            # other change is the difference of the cells (attack round 8: '16%' had been compared with 24.9 − 21.4)
            readings: list[tuple[Fraction, Fraction, str]] = []
            relative = m.group("rel") is not None or _RELATIVE_WORD_RE.search(s.text, _yt_index(s.text).clause_start(m.start()), m.end()) is not None
            if per_cent:
                if v1 == 0:
                    continue
                rel = abs(v2 - v1) / abs(v1) * 100
                rtol = max(_half(m.group("n").replace(",", "")), rel / 100, Fraction(1, 10))
                readings.append((rel, max(rtol, rel / 20) if m.group("ap") else rtol, "the relative change (V1 − V0) / V0 × 100"))
            if not per_cent or (cells[y1].unit == "%" and not relative):
                # the difference of the cells AS PRINTED, to half a unit of the figure stated: a band of the cells' own rounding (±1
                # point for whole-number cells) had shown 'rose by 11 percentage points' as ENTAILED against 13 − 1 = 12 (check round
                # 12 of c3f); a check never shows a figure the printed cells refute as checked
                tol = _half(m.group("n").replace(",", ""))
                readings.append((diff, max(tol, diff / 20) if m.group("ap") else tol, "the difference of its cells"))
            if len(readings) > 1 and any(abs(n - v) <= t for v, t, _w in readings):
                # push check of a9129c78: "The coal share fell by about 18% from 2005 to 2025" holds as the change in points (46 − 28) and
                # not as the relative change (39%); its words fix neither reading ('percentage points' or 'points' for the difference,
                # 'relative' for the ratio), so a figure that fits one of them is never shown as checked; one that fits neither is
                # refuted under both
                continue
            if not ctx.room("geo_table_change"):
                return
            ctx.decided.add(" ".join(s.text.split()))
            options = [{"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _real(v)}, "right": _real(t)},
                                              {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _real(v)}, "right": _real(-t)}]}
                       for v, t, _w in readings]
            what = " or ".join(w for _v, _t, w in readings)
            ctx.add("geo_table_change", lambda cid, n=n, options=options, what=what, m=m, entity=entity, y1=y1, y2=y2, table=table: make_check(
                ctx.report, check_id=cid, kind="geo_table_change", inputs=[("stated", n, f"the change stated ({m.group('n')})")],
                conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
                label=f"the change by {m.group('n')} against the row '{entity}' of {table.document_id} from {y1} to {y2}",
                description=f"{_excerpt(s.text)} [a change of a supplied table's row equals {what} for the two years]",
                claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="error", defect="source_mismatch"))
            return


#: A change of an attribute table's column between two of its rows ("Retail use fell by 92 percentage points along the transect",
#: "Pedestrian counts fell by about 91% from Site 1 to Site 10", "The EQS fell by 13 points from Site 1 to Site 10"); c3e left (ge-t14).
_COL_CHANGE_RE = re.compile(r"\b(?:" + _CHANGE_VERB + r"|shrank|dropped)\s++by\s++(?P<ap>about\s++|around\s++|roughly\s++|nearly\s++|almost\s++|approximately\s++)?"
                            r"(?P<n>" + _NUM + r")\s*+(?P<u>percentage\s+points?\b|points?\b|%|per\s*+cent\b|percent\b)?", re.IGNORECASE)
_COL_SPAN_RE = re.compile(r"\b(?:from|between)\s++(?:the\s+)?(?P<noun>[a-z]{3,12})s?\s++(?P<a>[a-z0-9]{1,3})\s++(?:to|and)\s++(?:(?P=noun)s?\s++)?(?P<b>[a-z0-9]{1,3})\b"
                          r"|\b(?P<along>along\s+the\s+(?:whole\s+)?(?:transect|road|route|street|line)|from\s+the\s+first\s+(?:site|point|station)\s+to\s+the\s+last)\b",
                          re.IGNORECASE)


def _table_column_change(ctx: _Ctx, s: _Sentence, tables: list[_AttrTable]) -> None:
    """c3e left (ge-t14): a change of one column of a supplied attribute table between two of its rows, the rows named by their label
    ('from Site 1 to Site 10') or the whole table ('along the transect': its first and last rows), the column by its distinctive words
    before the change verb. In points (or with no unit) it is the difference of the two cells; 'by N%' of a column held in per cent fixes
    neither the relative change nor the change in points, so a figure that fits one of them is never shown as checked (as for a year
    table's share); 'by N%' of any other column is the relative change."""
    from .grounded_figures import _half, _number
    # every change of the sentence is read, each with the column its own clause names (check round 12 of c3f: 'Pedestrian counts fell
    # by 195 from Site 1 to Site 10, while the EQS fell by 3 points' had shown the first change ENTAILED and left the wrong second one
    # unread)
    prev = 0
    for m in _COL_CHANGE_RE.finditer(s.text):
        _column_change_at(ctx, s, tables, m, prev, _half, _number)
        prev = m.end()


_COL_CLAUSE_CUT_RE = re.compile(r"[,;:]|\b(?:while|whilst|whereas|but|and)\b", re.IGNORECASE)


_APPROX_WORD = r"about\s++|around\s++|roughly\s++|approximately\s++|nearly\s++|almost\s++"
#: "Site 2 had 35 more pedestrians per 10 minutes than Site 3": a difference of one column between two rows named by their label.
_ROW_MORE_RE = re.compile(r"\b(?P<na>[a-z]{3,12})\s++(?P<a>[a-z0-9]{1,3})\s++(?:had|has|recorded|records|saw|sees|showed|shows|counted|scored)\s++"
                          r"(?P<ap>" + _APPROX_WORD + r")?(?P<n>" + _NUM + r")\s++(?P<dir>more|fewer|less|higher|lower)\b(?P<words>[^.;]{0,60}?)"
                          r"\bthan\s++(?:at\s++|in\s++|for\s++)?(?:(?P<nb>[a-z]{3,12})\s++)?(?P<b>[a-z0-9]{1,3})\b(?![.,]\d)", re.IGNORECASE)
#: "Pedestrian counts at Site 1 were about eleven times those at Site 10": a multiple of one column between two rows.
_ROW_TIMES_RE = re.compile(r"\b(?:at|in|for)\s++(?P<na>[a-z]{3,12})\s++(?P<a>[a-z0-9]{1,3})\s++(?:was|were|is|are)\s++(?P<ap>" + _APPROX_WORD + r")?"
                           r"(?P<n>" + _WORD_NUMBER + r"|" + _NUM + r")\s++times\s++(?:those|that|the\s+[a-z]{3,15}|as\s+(?:high|many|much|large)\s+as)\s++"
                           r"(?:at|in|for|of)\s++(?:(?P<nb>[a-z]{3,12})\s++)?(?P<b>[a-z0-9]{1,3})\b(?![.,]\d)", re.IGNORECASE)


def _row_pair_comparison(ctx: _Ctx, s: _Sentence, tables: list[_AttrTable]) -> None:
    """Check round 12 of c3f (ge-t14): a difference ('Site 2 had 35 more pedestrians than Site 3') or a multiple ('Pedestrian counts at
    Site 1 were about eleven times those at Site 10') of one column of a supplied attribute table between two rows named by their
    label, the column named by the distinctive words of the clause (after the comparison word for a difference, before 'at' for a
    multiple). Read only when exactly one column is named and both rows are rows of the table under its row noun."""
    from .grounded_figures import _half, _number
    if " than " not in s.text and " times " not in s.text:
        return
    cuts: Optional[list] = None  # (the clause cuts, found once per sentence: never a scan of the sentence per comparison)
    for kind, rx in (("more", _ROW_MORE_RE), ("times", _ROW_TIMES_RE)):
        for m in rx.finditer(s.text):
            if kind == "more":
                words = m.group("words")
            else:
                if cuts is None:
                    cuts = [c.end() for c in _COL_CLAUSE_CUT_RE.finditer(s.text)]
                k = bisect_right(cuts, m.start())
                words = s.text[cuts[k - 1] if k else 0:m.start()]
            head = {_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z'’-]{1,30}", words) if w.lower() not in _STOPWORDS}
            for table in tables:
                if not table.row_noun or not m.group("na").lower().startswith(table.row_noun[:4]):
                    continue
                if m.group("nb") and not m.group("nb").lower().startswith(table.row_noun[:4]):
                    continue
                cols = [k for k, (_h, st) in enumerate(table.columns) if st and st & head]
                if len(cols) != 1:
                    continue
                labels = [lab.strip().lower() for lab, _cells in table.rows]
                a, b = m.group("a").lower(), m.group("b").lower()
                if a not in labels or b not in labels or a == b:
                    continue
                col = cols[0] + 1
                ca, cb = _number(table.rows[labels.index(a)][1][col]), _number(table.rows[labels.index(b)][1][col])
                if ca is None or cb is None:
                    continue
                va, vb = ca[0], cb[0]
                w = m.group("n")
                n = Fraction(_WORD_NUMBERS[w.lower()]) if w.lower() in _WORD_NUMBERS else _num(w)
                h = _half(w.replace(",", "")) if w[0].isdigit() else Fraction(1, 2)
                if kind == "more":
                    value = (va - vb) if m.group("dir").lower() in ("more", "higher") else (vb - va)
                    tol = max(h, abs(value) / 20) if m.group("ap") else h
                    what = "the difference of the two rows' cells"
                else:
                    if vb == 0:
                        continue
                    value = va / vb
                    tol = max(h, value / 10) if m.group("ap") else h
                    what = "the ratio of the two rows' cells"
                if not ctx.room("supplied_figure"):
                    ctx.skip("supplied_figure")
                    return
                header = table.columns[cols[0]][0]
                ctx.decided.add(" ".join(s.text.split()))
                ctx.add("supplied_figure", lambda cid, n=n, value=value, tol=tol, m=m, header=header, table=table, va=va, vb=vb, what=what: make_check(
                    ctx.report, check_id=cid, kind="supplied_figure", inputs=[("stated", n, f"the comparison stated ({m.group(0).strip()})")],
                    conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(value)}), "right": _real(tol)},
                    label=(f"{m.group('n')} against '{header}' of {table.document_id}, row {m.group('a')} ({_fmt(va)}) and row "
                           f"{m.group('b')} ({_fmt(vb)})"),
                    description=f"{_excerpt(s.text)} [a comparison of two rows of a supplied table's column equals {what}]",
                    claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="warning", defect="source_mismatch"))
                break


def _column_change_at(ctx: _Ctx, s: _Sentence, tables: list[_AttrTable], m: "re.Match[str]", prev: int, _half, _number) -> None:
    """One change of :func:`_table_column_change`: its column named by the words of its own clause (from the last cut before it, or
    from the previous change), else, for the sentence's first change, by every word before it."""
    span = _COL_SPAN_RE.search(s.text, m.end()) or _COL_SPAN_RE.search(s.text)
    if span is None:
        return
    cuts = [c.end() for c in _COL_CLAUSE_CUT_RE.finditer(s.text, prev, m.start())]
    lo = max([prev] + cuts)

    def stems(a: int) -> set:
        return {_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z'’-]{1,30}", s.text[a:m.start()]) if w.lower() not in _STOPWORDS}

    own, wide = stems(lo), (stems(0) if prev == 0 else None)
    for table in tables:
        head = own
        if not any(st and st & own for _h, st in table.columns):
            if wide is None:
                continue
            head = wide
        cols = [k for k, (_h, stems) in enumerate(table.columns) if stems and stems & head]
        if len(cols) != 1:
            continue
        col = cols[0] + 1
        labels = [lab.strip().lower() for lab, _cells in table.rows]
        if span.group("along"):
            ia, ib = 0, len(table.rows) - 1
        else:
            if table.row_noun and not span.group("noun").lower().startswith(table.row_noun[:4]):
                continue
            a, b = span.group("a").lower(), span.group("b").lower()
            if a not in labels or b not in labels:
                continue
            ia, ib = labels.index(a), labels.index(b)
        ca, cb = _number(table.rows[ia][1][col]), _number(table.rows[ib][1][col])
        if ca is None or cb is None or not ctx.room("supplied_figure"):
            continue
        v0, v1 = ca[0], cb[0]
        header = table.columns[cols[0]][0]
        pct_col = "%" in header or "per cent" in header.lower()
        unit = (m.group("u") or "").lower()
        n = _num(m.group("n"))
        h = _half(m.group("n").replace(",", ""))
        readings: list[tuple[Fraction, Fraction, str]] = []
        if unit.startswith("%") or (unit.startswith("per") and not unit.startswith("percentage")):
            if v0 != 0:
                rel = abs(v1 - v0) / abs(v0) * 100
                readings.append((rel, max(h, rel / 100, rel / 20 if m.group("ap") else Fraction(0)), "the relative change (V1 − V0) / V0 × 100"))
            if pct_col:
                d = abs(v1 - v0)
                readings.append((d, max(h, d / 20 if m.group("ap") else Fraction(0)), "the difference of the cells in points"))
            if len(readings) > 1 and any(abs(n - v) <= t for v, t, _w in readings):
                continue  # (an ambiguous reading is never shown as checked)
        else:
            d = abs(v1 - v0)
            readings.append((d, max(h, d / 20 if m.group("ap") else Fraction(0)), "the difference of the cells"))
        if not readings:
            continue
        ctx.decided.add(" ".join(s.text.split()))
        options = [{"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(v)}), "right": _real(t)} for v, t, _w in readings]
        what = " or ".join(w for _v, _t, w in readings)
        ctx.add("supplied_figure", lambda cid, n=n, options=options, what=what, header=header, ia=ia, ib=ib, table=table, v0=v0, v1=v1: make_check(
            ctx.report, check_id=cid, kind="supplied_figure", inputs=[("stated", n, f"the change stated ({m.group(0).strip()})")],
            conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
            label=(f"the change by {m.group('n')} of '{header}' of {table.document_id} from row {table.rows[ia][0]} ({_fmt(v0)}) to row "
                   f"{table.rows[ib][0]} ({_fmt(v1)})"),
            description=f"{_excerpt(s.text)} [a change of a supplied table's column between two rows equals {what}]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="warning", defect="source_mismatch"))
        return


#: A figure credited to a supplied table with years (attack round 8: "According to the table, 45% of supply was imported in 2025.").
_YT_CREDIT_RE = re.compile(r"\b(?:according\s+to\s+(?:the|your|my)\s+(?:data\s+)?table|(?:the|your|my)\s+(?:data\s+)?table\s+(?:shows?|gives?|records?|states?|lists?)|"
                           r"(?:in|from)\s+(?:the|your)\s+(?:data\s+)?table)\b", re.IGNORECASE)
_YT_FIG_RE = re.compile(r"(?<![\d.,])(?P<n>\d{1,3}(?:,\d{3})++(?:\.\d{1,6})?|\d{1,9}(?:\.\d{1,6})?)(?![\d,]\d|\.\d)\s*+(?P<p>%|per\s*+cent\b|percent\b)?")


def _year_table_credited(ctx: _Ctx, s: _Sentence, year_tables: list) -> None:
    """A figure the sentence credits to a supplied table with years, of a row the sentence names by its distinctive words only (the row's
    words no other row has: 'imported' of 'Share of primary energy supply that is imported (%)'), against that row's cell for the year
    the sentence names. A row the sentence names by all its words is the shared table reader's; this reader takes only the rest."""
    from .grounded_figures import _entity_at, _half, _intervening_spans, _outside, _word_positions
    if not _YT_CREDIT_RE.search(s.text):
        return
    years = {int(y) for y in re.findall(r"(?<![\d.,])(1[89]\d{2}|20\d{2})(?![\d,]\d|\.\d)", s.text)}
    figs = [m for m in _YT_FIG_RE.finditer(s.text) if not _YEAR_IN_RE.fullmatch(m.group("n"))]
    if len(years) != 1 or len(figs) != 1:
        return
    year, f = years.pop(), figs[0]
    where = _word_positions(s.text)
    spans = _intervening_spans(s.text)
    if spans:
        where = _outside(where, spans, f.start())  # (a row named only inside an insertion is not the figure's: push check of 08c4a36b)
    for table in year_tables:
        entity, _n = _entity_at(table, where, f.start())
        if entity:
            return  # a row named by all its words: the shared reader decides it
        index = _yt_index(s.text)  # (by its head or modifier in the figure's own clause, before or after it; push check of a9129c78)
        entity = index.row(table, f.start()) or index.row_after(table, f.end())
        if entity is None:
            continue
        cell = next((c for c in table.cells if c.entity == entity and c.year == year), None)
        if cell is None or (cell.unit == "%") != bool(f.group("p")) or not ctx.room("geo_table_figure"):
            continue
        v = Fraction(f.group("n").replace(",", ""))
        tol = max(_half(f.group("n").replace(",", "")), cell.half)
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_table_figure", lambda cid, v=v, cell=cell, tol=tol, f=f, entity=entity, table=table, year=year: make_check(
            ctx.report, check_id=cid, kind="supplied_figure", inputs=[("stated", v, f"the figure credited to the table ({f.group(0).strip()})")],
            conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(cell.value)}), "right": _real(tol)},
            label=f"{f.group(0).strip()} against the row '{entity}' of {table.document_id} for {year} ({cell.shown})",
            description=f"{_excerpt(s.text)} [a figure credited to a supplied table is its cell for the row and year the sentence names]",
            claim_ids=_claims(ctx.report, s.text, f.group(0)), severity="error", defect="source_mismatch"))
        return


# ------------------------------------------------------------------------------------------------------------------ c3d: year-table derivations
#: The energy units an amount of a year table's total row or a per-person figure is written in (joules), and the scale words of a row
#: of people ('Population (millions)').
_ENERGY_J = {"kj": Fraction(10**3), "mj": Fraction(10**6), "gj": Fraction(10**9), "tj": Fraction(10**12), "pj": Fraction(10**15), "ej": Fraction(10**18)}
_PEOPLE_SCALE = {"thousands": Fraction(10**3), "thousand": Fraction(10**3), "millions": Fraction(10**6), "million": Fraction(10**6),
                 "billions": Fraction(10**9), "billion": Fraction(10**9)}
#: The closed complements of a share row's distinctive word: 'domestic' sources supply what is not 'imported'; 'non-X' and 'not X' too.
_COMPLEMENTS = {"imported": ("domestic", "domestically", "home-produced", "indigenous", "home"), "urban": ("rural",), "rural": ("urban",),
                "renewable": ("non-renewable", "fossil"), "exported": ("retained",)}
_YT_AMOUNT_RE = re.compile(r"(?<![\d.,])(?P<n>" + _NUM + r")(?![\d,]\d|\.\d)\s*+(?P<u>[A-Za-z]{1,12})\b")
_YT_PCT_RE = re.compile(r"(?<![\d.,])(?P<n>" + _NUM + r")(?![\d,]\d|\.\d)\s*+(?:%|per\s*+cent\b|percent\b)", re.IGNORECASE)
_YT_YEAR_AFTER_RE = re.compile(r"[^.;\d]{0,24}?\b(?:in|for|during|by)?\s*+\(?(?P<y>1[89]\d{2}|20\d{2})\b")
_PER_PERSON_RE = re.compile(r"\bper\s+(?:person|capita|head|inhabitant|resident)\b|\beach\s+(?:[A-Z][\w-]{1,20}\s+)?(?:person|inhabitant|resident)\b",
                            re.IGNORECASE)  # ("each Ostrel resident": a demonym before the noun; c3e)
_REL_CHANGE_RE = re.compile(r"\b(?:relative|proportional)\s+(?P<dir>rise|increase|growth|gain|fall|decrease|decline|drop|reduction|change)\s++of\s++"
                            r"(?P<ap>(?:about|around|roughly|approximately|nearly|some)\s++)?(?P<n>" + _NUM + r")\s*+(?:%|per\s*+cent\b|percent\b)"
                            r"|(?P<ap2>(?:about|around|roughly|approximately|nearly|some)\s++)?(?P<n2>" + _NUM + r")\s*+(?:%|per\s*+cent\b|percent\b)\s++"
                            r"(?:relative|proportional)\s+(?P<dir2>rise|increase|growth|gain|fall|decrease|decline|drop|reduction|change)\b", re.IGNORECASE)
_DOWN_WORDS = ("fall", "decrease", "decline", "drop", "reduction")


@dataclass(frozen=True)
class _YtDoc:
    """The year tables of one supplied document read as one: a share table and an 'Other data' table of totals and population."""
    document_id: str
    cells: tuple
    entities: tuple


def _yt_documents(year_tables: list) -> list[_YtDoc]:
    return list(_yt_documents_of(tuple(year_tables)))


@lru_cache(maxsize=32)
def _yt_documents_of(year_tables: tuple) -> tuple[_YtDoc, ...]:
    """Read once per set of tables, never again for every sentence."""
    by: dict[str, list] = {}
    for t in year_tables:
        by.setdefault(t.document_id, []).append(t)
    out = []
    for doc, ts in by.items():
        ents = dict(e for t in ts for e in t.entities)
        out.append(_YtDoc(doc, tuple(c for t in ts for c in t.cells), tuple(ents.items())))
    return tuple(out)


@lru_cache(maxsize=32)
def _yt_rows(table) -> dict:
    """``{entity: {year: cell}}`` of a year table (read once per table; callers never change it)."""
    rows: dict = {}
    for c in table.cells:
        if c.year is not None:
            rows.setdefault(c.entity, {})[c.year] = c
    return rows


#: Where the clause of a figure starts: a comma, a semicolon, a colon, a bracket, a dash between spaces, or a word that opens another
#: clause, a comparison or an intervening phrase ("Although population grew, ...", "..., faster than population", "and, with natural
#: growth, about 9.3 GJ", "as nuclear capacity grew", "despite oil prices", "after coal declined").
_YT_CLAUSE_CUT_RE = re.compile(r"[,;:()]|\s[-–—]\s|\b(?:although|though|while|whilst|whereas|but|than|because|since|as|with|despite|after|before|"
                               r"when|unless|once|until|compared)\b", re.IGNORECASE)
_YT_OPENER_RE = re.compile(r"\s*+(?:although|though|while|whilst|whereas|because|since|as|with|despite|after|before|when|unless|once|until|"
                           r"compared|given|if|in\s+spite\s+of)\b", re.IGNORECASE)
_YT_VERB_RE = re.compile(r"\b(?:was|were|is|are|rose|rises|fell|falls|grew|grows|showed|shows|reached|reaches|stood|stands|made|makes|came|"
                         r"amounted|amounts|totalled|totaled|totals|supplied|supplies|provided|provides|used|uses|increased|decreased|dropped|"
                         r"declined|went|accounted|accounts|equalled|equaled|equals)\b", re.IGNORECASE)
_YT_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]{0,30}")
_YT_DIGIT_RE = re.compile(r"\d")
_YT_NUMBER_RE = re.compile(r"(?<![\d.,])\d++(?:[,.]\d++)*+")  # (never a trailing comma or stop: "In 2025, ..." is a year)
#: Working in brackets right after a figure ("251 PJ (22% of 1,050 PJ)", "123 PJ in 2005 (0.15 × 820)"): the figure is the worked reader's.
_YT_WORKING_AFTER_RE = re.compile(r"[^.;()\d]{0,24}\(\s*+[^()]{0,40}?\d")
#: Words that never make a clause's own subject: function words, approximators, verbs of stating a figure and pronouns ("and in 2025
#: it was about 5.5 GJ" has no subject of its own, so the figure is the sentence subject's).
_YT_NOT_SUBJECT = frozenset("""about around roughly approximately nearly almost some just only also still then later again further
    was were is are rose fell grew showed reached stood made came amounted totalled totaled went it they this that there here
    year years each""".split()) | _FUNCTION_WORDS
#: A change of a level, not the level itself, stated before a figure in its own clause ("Natural growth in supply per person reached
#: 9.3 GJ", "rose by about 4 GJ"): a figure per person or an amount there is not the year's level.
_YT_CHANGE_BEFORE_RE = re.compile(r"\b(?:growth|rise|increase|fall|drop|decline|decrease|change|difference|gain|loss|reduction|"
                                  r"(?:rose|grew|fell|increased|decreased|dropped|declined|went\s+(?:up|down))\s++by)\b", re.IGNORECASE)


_YT_OPENING_YEAR_RE = re.compile(r"\s*+(?:in|by|during)\s++(?P<y>1[89]\d{2}|20\d{2})\b", re.IGNORECASE)
#: The opening of a modifier that holds a figure and belongs to the noun before it (push check of 67bc64ec): a relative clause ('Coal,
#: which supplied about 11.8 GJ per person in 2025, declined'), a 'whose' clause, an 'at' phrase, a participle phrase ('Nuclear power,
#: supplying about 1.7 GJ ...', 'Coal, supplied at about 11.8 GJ ...'), an apposition opened by an article ('Coal, a source that ...') and
#: a bare figure in a comma pair, a bracket or a pair of dashes ('Oil (about 11.4 GJ per person in 2025) changed least').
_YT_MODIFIER_OPEN_RE = re.compile(r"[\s,;(\[–—-]*+(?P<w>[A-Za-z][A-Za-z'’-]*|\d|~)", re.IGNORECASE)
_YT_MODIFIER_WORDS = frozenset("which that who whom whose at a an the about around roughly approximately approx nearly almost some circa "
                               "ca c".split())
_YT_DELIMITED_RE = re.compile(r"\s*+(?:,|\(|\[|[-–—])")
#: A part of no stated size before "of" and the figure ("a share of about 42 GJ", "part of the 42 GJ"): the figure may be the whole or
#: the part's own amount, so its row is not determined by its own words and it gets no check (c3h check round 14; fail closed).
_YT_VAGUE_PART_BEFORE_RE = re.compile(r"\b(?:share|shares|part|parts|fraction|proportion|portion|bit|some)\s++of\s++(?:the\s++|about\s++|"
                                      r"around\s++|roughly\s++|approximately\s++|nearly\s++|almost\s++|some\s++)*+\Z", re.IGNORECASE)
#: The figure right after a part of a stated size and "of" (with an article or an approximation between), the whole the part is taken
#: of ("28% of the 42 GJ", "a quarter of about 42 GJ", "11.8 of the 42 GJ", "28% of 1,050 PJ"); "a supply of about 42 GJ" names no part.
#: Read at the end of the stretch before the figure.
_YT_WHOLE_BEFORE_RE = re.compile(r"(?:%|\bper\s?cent|\b(?:quarter|quarters|third|thirds|half|fifth|fifths|tenth|tenths)|\d)\s++of\s++"
                                 r"(?:the\s++|a\s++total\s++of\s++|about\s++|around\s++|roughly\s++|approximately\s++|"
                                 r"nearly\s++|almost\s++|some\s++|just\s++(?:over|under)\s++)*+\Z", re.IGNORECASE)


def _yt_word(w: str) -> str:
    w = w.lower().strip("'’-")
    return w[:-2] if w.endswith(("'s", "’s")) else w


@dataclass(frozen=True)
class _YtRow:
    entity: str
    words: frozenset           # the label's content words (the shared reader's: every one named means the row is named)
    alone: frozenset           # stems of the row's distinctive head words: each names the row by itself ('gas', 'coal', 'imported')
    modifiers: frozenset       # stems of its distinctive modifiers: each names the row only before a word of the table ('natural gas')


@lru_cache(maxsize=64)
def _yt_row_vocab(table) -> tuple[tuple[_YtRow, ...], frozenset]:
    """The naming words of each row of a year table (read once per table). A row is named by ALL its content words (the shared rule);
    by a word only it holds that is its head (the label's last content word, or the word of a one-word label: 'Natural gas' by 'gas',
    'Coal' by 'coal', 'Share of primary energy supply that is imported' by 'imported'); or by a word only it holds that modifies a word of
    the table right after it ('natural gas', 'nuclear share', 'total supply', 'wind and solar power'). A stop word ('share', 'total'), a
    function word or a modifier standing alone ('natural growth', 'nuclear capacity') never names a row (push check of a9129c78)."""
    labels = {e: [w for w in (_yt_word(x) for x in _YT_WORD_RE.findall(re.sub(r"\([^)]*\)", "", e))) if len(w) >= 3 and w not in _FUNCTION_WORDS]
              for e, _w in table.entities}
    held: dict[str, int] = {}
    for ws in labels.values():
        for st in {_stem(w) for w in ws}:
            held[st] = held.get(st, 0) + 1
    vocab = frozenset(_stem(w) for ws in labels.values() for w in ws)
    rows = []
    for e, words in table.entities:
        ws = labels[e]
        own = [w for w in ws if held[_stem(w)] == 1]
        head = ws[-1] if ws else ""
        alone = frozenset(_stem(w) for w in own if w not in _STOPWORDS and w == head)
        mods = frozenset(_stem(w) for w in own) - alone
        rows.append(_YtRow(e, frozenset(words), alone, mods))
    return tuple(rows), vocab


class _YtIndex:
    """One sentence read once for the row lookups of the year-table readers: its words with their positions, its clause cuts, a running
    count of the words that can be a clause's own subject, and the span of the sentence's own subject. Each lookup is then a few binary
    searches per row, so a sentence of k figures costs O(k log n), never a walk back over every earlier clause (the push check of
    a9129c78 timed 'Energy supply per person was ' + 'about 38 GJ in 2005, ' * k at 438 s for 40k characters)."""

    def __init__(self, text: str, _outer: bool = False):
        self.text = text
        # the sentence with its insertions blanked (subordinate and parenthetical clauses, appositions: push check of 08c4a36b, where
        # 'Energy supply per person, while coal declined, was about 11.8 GJ' read 'coal' as the subject): a figure outside every insertion
        # is read on it, so no word of an insertion names its row and no verb of one is the subject's; a figure inside one keeps its own
        # clause's reading here
        self._spans = () if _outer else insertion_spans(text)
        self._span_starts = [a for a, _b in self._spans]
        self._out = _YtIndex(masked(text, self._spans), _outer=True) if self._spans else None
        self.toks = [(m.start(), _yt_word(m.group(0))) for m in _YT_WORD_RE.finditer(text)]
        self.starts = [p for p, _w in self.toks]
        cuts = list(_YT_CLAUSE_CUT_RE.finditer(text))
        self.cuts = [m.end() for m in cuts]
        self.cut_starts = [m.start() for m in cuts]
        run, acc = [0], 0
        for _p, w in self.toks:
            acc += 1 if (len(w) >= 3 and w not in _YT_NOT_SUBJECT and not _YT_VERB_RE.fullmatch(w)) else 0
            run.append(acc)
        self.subject_run = run
        # the sentence's own subject: the words before its first verb in that verb's clause ("Result: coal supply fell by 22.1%, from
        # ..."), after an opening subordinate clause ("Although population grew, total energy supply showed ..."); when that clause opens
        # with its verb, the sentence's first clause ("Imported energy, mostly oil and gas, was about 567 PJ")
        s0 = 0
        if _YT_OPENER_RE.match(text):
            k = text.find(",")
            s0 = k + 1 if k >= 0 else len(text)
        v = _YT_VERB_RE.search(text, s0)
        self.subject = (0, 0)
        if v is not None:
            c = max(self.clause_start(v.start()), s0)
            if self._has_subject(c, v.start()):
                span = (c, v.start())
            else:
                k = bisect_right(self.cut_starts, s0)
                end = self.cut_starts[k] if k < len(self.cut_starts) else v.start()
                span = (s0, min(end, v.start()))
            # a figure in the subject's own words makes it no subject; one inside an apposition between the subject and its verb does
            # not ('Nuclear power, which had a 4% share, supplied 63.0 PJ', 'Hydroelectric power (6% in 2025) supplied 41.0 PJ': check
            # round 12 of c3f, where the PJ figure had lost its row and its check)
            if not any(not _YEAR_IN_RE.fullmatch(n) for n in _YT_NUMBER_RE.findall(text, span[0], span[1])):
                self.subject = span
        if self._out is not None:
            self.subject = self._out.subject  # (the subject read with the insertions blanked)
        self._named: dict = {}

    def _outside(self, at: int) -> Optional["_YtIndex"]:
        """The blanked reading for a figure at ``at`` outside every insertion; None when there is none or the figure is inside one."""
        if self._out is None or span_holding(self._spans, self._span_starts, at) is not None:
            return None
        return self._out

    def attached(self, table, at: int) -> Optional[list]:
        """The rows of the noun a modifier holding the figure at ``at`` belongs to (push check of 67bc64ec: 'Coal, which supplied about
        42 GJ per person in 2025, declined.' was read against the total row): None when the figure stands in no modifier of a noun
        phrase (its clause's readings apply); else the one row (or the listed rows) the modifier's own words name before the figure,
        else those the noun phrase before it names, and [] when no row is determined that way (the figure then gets no check: never
        the total row by default). A modifier is a relative or 'whose' clause, an 'at' phrase, a participle phrase, an apposition
        opened by an article, or a bare figure in a comma pair, a bracket or a pair of dashes, right after a noun phrase with no verb."""
        out = self._outside(at)
        if out is not None:
            return out.attached(table, at)
        span = span_holding(self._spans, self._span_starts, at) if self._spans else None
        if span is not None:
            a = span[0]
        else:
            k = bisect_right(self.cuts, at) - 1
            if k < 0:
                return None
            a = self.cut_starts[k]
        if not _YT_DELIMITED_RE.match(self.text, a):
            return None  # (a clause opened by a conjunction, or a mid-clause insertion: its own clause's readings)
        m = _YT_MODIFIER_OPEN_RE.match(self.text, a, at + 1)
        if m is None:
            return None
        w = m.group("w").lower().strip("'’-")
        if m.start("w") == at:
            w = "about"  # (the figure itself opens the modifier: a bare figure)
        lo = self.clause_start(a)
        head_has_verb = _YT_VERB_RE.search(self.text, lo, a) is not None or _EN_FINITE_RE.search(self.text, lo, a) is not None
        if head_has_verb:
            return None  # (a modifier after a whole clause: the clause readings, unchanged)
        if _YT_VAGUE_PART_BEFORE_RE.search(self.text[max(a, at - 40):at]):
            return []  # (whole or part, not determined by the modifier's own words: no check)
        if _YT_WHOLE_BEFORE_RE.search(self.text[max(a, at - 40):at]):
            return None  # (the figure the modifier's own words make the whole, "28% of the 42 GJ per person", "a share of the 42 GJ":
            # the total its clause names, never the head noun's row; c3h check round 14: a correct total was charged)
        if not (w in _YT_MODIFIER_WORDS or (len(w) > 4 and w.endswith(("ing", "ed"))) or w[:1].isdigit() or w == "~"):
            if _YT_VERB_RE.search(self.text, a, at) is not None or _EN_FINITE_RE.search(self.text, a, at) is not None:
                return None  # (a clause of its own after the delimiter, "In 2025, coal supplied 11.8 GJ ...": its own readings)
            # (an opener the list does not know, in a modifier with no verb, "Coal, still about 42 GJ per person in 2025, declined.",
            # "Coal, with about 11.8 GJ ...": read as a known opener is, against the noun's row, or no check; never the total row by
            # default; c3h check round 14)
        for lo_, hi_ in ((m.start("w"), at), (lo, a)):
            found = self._rows_in(table, lo_, hi_)
            if not found:
                continue
            if self._is_list(found, hi_):
                return [e for _p, e in found]
            if len(found) > 1 and found[-1][0] == found[-2][0]:
                return []
            return [found[-1][1]]
        return []

    def _numbers(self) -> tuple[list[int], list[bool]]:
        """The start of each number of the sentence and whether it is a year (read once)."""
        if not hasattr(self, "_nums"):
            ms = list(_YT_NUMBER_RE.finditer(self.text))
            self._nums = ([m.start() for m in ms], [bool(_YEAR_IN_RE.fullmatch(m.group(0))) for m in ms])
            self._changes = [m.start() for m in _YT_CHANGE_BEFORE_RE.finditer(self.text)]
        return self._nums

    def clause_start(self, at: int) -> int:
        k = bisect_right(self.cuts, at) - 1
        return self.cuts[k] if k >= 0 else 0

    def _has_subject(self, lo: int, at: int) -> bool:
        i, j = bisect_left(self.starts, lo), bisect_left(self.starts, at)
        return self.subject_run[j] - self.subject_run[i] > 0

    def _events(self, table) -> tuple:
        """(rows, {row index: sorted positions where its head, or its modifier before a word of the table, names it}, {word: positions})."""
        got = self._named.get(id(table))
        if got is not None and got[0] is table:
            return got[1]
        rows, vocab = _yt_row_vocab(table)
        heads = {st: r for r, row in enumerate(rows) for st in row.alone}
        mods = {st: r for r, row in enumerate(rows) for st in row.modifiers}
        events: dict[int, list[int]] = {}
        where: dict[str, list[int]] = {}
        toks = self.toks
        for i, (p, w) in enumerate(toks):
            where.setdefault(w, []).append(p)
            st = _stem(w)
            r = heads.get(st)
            if r is None and st in mods:
                # a modifier names its row only right before a word of the table, or before another modifier of a listed row
                # ('wind and solar power', 'Solar and wind supplied')
                k = i + 1
                if k < len(toks) and toks[k][1] in ("and", "or", "&") and "," not in self.text[p:toks[k][0]]:
                    # across 'and' only another row's own word continues the list ('wind and solar', 'Solar and wind'); a shared word
                    # or a verb there opens a new clause ('a 28% share and supplied 294.0 PJ', 'share and supply both grew' never
                    # name the imported share's row: check round 12 of c3f)
                    k += 1
                    if k < len(toks) and _stem(toks[k][1]) not in mods and _stem(toks[k][1]) not in heads:
                        k = len(toks)
                if k < len(toks) and _stem(toks[k][1]) in vocab:
                    r = mods[st]
            if r is not None:
                events.setdefault(r, []).append(p)
        out = (rows, events, where)
        self._named[id(table)] = (table, out)
        return out

    def _rows_in(self, table, lo: int, at: int) -> list[tuple[int, str]]:
        """(position, row) of each row named in [lo, at): where its head or its modifier names it last there, else where the last of all
        its content words stands."""
        rows, events, where = self._events(table)
        found = []
        for r, row in enumerate(rows):
            best = -1
            ps = events.get(r)
            if ps:
                j = bisect_left(ps, at) - 1
                if j >= 0 and ps[j] >= lo:
                    best = ps[j]
            if best < 0 and row.words:
                last = -1
                for w in row.words:
                    qs = where.get(w)
                    j = bisect_left(qs, at) - 1 if qs else -1
                    if j < 0 or qs[j] < lo:
                        last = -1
                        break
                    last = max(last, qs[j])
                best = last
            if best >= 0:
                found.append((best, row.entity))
        found.sort()
        return found

    def _is_list(self, found: list, at: int) -> bool:
        """Whether the rows found are listed for one figure: two or more, no figure among them, each joined to the next by 'and', a comma
        or '&' and never by a contrast ('Hydroelectric power and nuclear power supplied 57.4 PJ', 'Coal and oil together ...')."""
        if len(found) < 2:
            return False
        starts, _years = self._numbers()
        if bisect_left(starts, at) > bisect_left(starts, found[0][0]):
            return False  # (a number among the rows: each has its own figure)
        for (p0, _e0), (p1, _e1) in zip(found, found[1:]):
            gap = self.text[p0:p1]
            if p0 == p1 or not re.search(r",|\band\b|&|\bplus\b", gap) or re.search(r"\b(?:than|but|while|whereas|not)\b", gap, re.IGNORECASE):
                return False
        return True

    def group(self, table, at: int) -> list[str]:
        """The rows a figure at ``at`` is stated for as a list of two or more (its own clause's rows, as :meth:`_is_list` reads them); []
        otherwise."""
        out = self._outside(at)
        if out is not None:
            return out.group(table, at)
        att = self.attached(table, at)
        if att is not None:
            return att if len(att) >= 2 else []
        found = self._rows_in(table, self.clause_start(at), at)
        return [e for _p, e in found] if self._is_list(found, at) else []

    def row(self, table, at: int) -> Optional[str]:
        """The row the figure at ``at`` is stated for: the row its own clause names (the words after the clause's cut), the one named
        last before it; with no row and no subject of its own there ("and, with natural growth, about 9.3 GJ in 2025", "and in 2025 it
        was about 5.5 GJ", ", a relative rise of about 16%"), the row the sentence's own subject names ("Imported energy, mostly oil and
        gas, was about 567 PJ"). A row named only inside another clause (an apposition, a 'with', 'as', 'despite' or 'after' clause, a
        contrast or a comparison) never takes the figure; None when no one row is named (none, a list of rows, or two rows named by the
        same words)."""
        out = self._outside(at)
        if out is not None:
            return out.row(table, at)
        att = self.attached(table, at)
        if att is not None:
            return att[0] if len(att) == 1 else None
        lo = self.clause_start(at)
        found = self._rows_in(table, lo, at)
        if not found:
            if self._has_subject(lo, at):
                return None
            s0, s1 = self.subject
            if s1 > lo or s0 >= s1:
                return None
            lo, at = s0, s1
            found = self._rows_in(table, s0, s1)
            if not found:
                return None
        if self._is_list(found, at) or (len(found) > 1 and found[-1][0] == found[-2][0]):
            return None
        return found[-1][1]

    def row_after(self, table, at: int) -> Optional[str]:
        """The one row the figure's own clause names after it, up to the clause's next cut ("45% of supply was imported in 2025")."""
        out = self._outside(at)
        if out is not None:
            return out.row_after(table, at)
        k = bisect_right(self.cut_starts, at)
        hi = self.cut_starts[k] if k < len(self.cut_starts) else len(self.text)
        found = self._rows_in(table, at, hi)
        return found[0][1] if len({e for _p, e in found}) == 1 else None

    def changes_before(self, at: int) -> bool:
        """Whether the figure's own clause states a change before it ('growth in supply per person reached 9.3 GJ')."""
        out = self._outside(at)
        if out is not None:
            return out.changes_before(at)
        self._numbers()
        ps = self._changes
        j = bisect_left(ps, at) - 1
        return j >= 0 and ps[j] >= self.clause_start(at)

    def year_before(self, at: int) -> Optional[int]:
        """The year a figure's own clause writes before it, when that clause states no other number ('and in 2025 it was about 5.5 GJ',
        'In 2025 energy supply per person was about 5.5 GJ'); None otherwise."""
        lo = self.clause_start(at)
        starts, years = self._numbers()
        i, j = bisect_left(starts, lo), bisect_left(starts, at)
        if j - i == 1 and years[i]:
            m = _YT_NUMBER_RE.match(self.text, starts[i])
            return int(m.group(0))
        if j == i:
            # the sentence's opening year, when it writes no other ('In 2025 nuclear power, which had a 4% share, supplied 63.0 PJ':
            # check round 12 of c3f, where the PJ figure had no year and no check)
            o = _YT_OPENING_YEAR_RE.match(self.text)
            if o is not None and sum(years) == 1:
                return int(o.group("y"))
        return None


def _yt_years(text: str, figs: list, years: list, index: Optional["_YtIndex"] = None) -> Optional[list]:
    """The year each figure of a clause is stated for: the year written right after it ('62% of energy in 2005'), else the one year its
    own clause writes before it with no other number ('and in 2025 it was about 5.5 GJ'), else, for a from-to pair of a table with two
    years and no year written, the earlier and the later year. A figure with no year is None in the list; None when no figure has one."""
    out = []
    for f in figs:
        y = _YT_YEAR_AFTER_RE.match(text, f.end())
        yr = int(y.group("y")) if y and not _YT_PCT_RE.search(text, f.end(), y.start("y")) and not _YT_AMOUNT_RE.search(text, f.end(), y.start("y")) else None
        if yr is None and index is not None:
            yr = index.year_before(f.start())
        out.append(yr)
    if all(y is not None for y in out):
        return out
    if len(figs) == 2 and len(years) == 2 and not _YEAR_IN_RE.search(text) and re.search(r"\bfrom\b", text[:figs[0].start()], re.IGNORECASE) \
            and re.search(r"\bto\b", text[figs[0].end():figs[1].start()], re.IGNORECASE):
        return sorted(years)
    return out if any(y is not None for y in out) else None


def _yt_check(ctx: _Ctx, s: _Sentence, kind: str, f: "re.Match[str]", value: Fraction, what: str, table, credited: bool) -> None:
    from .grounded_figures import _half
    approx = bool(_APPROX_RE.search(s.text[max(0, f.start() - 20):f.start()]))
    stated = Fig(_num(f.group("n")), f.group("n"), _half(f.group("n").replace(",", "")), approx)
    if not ctx.room(kind):
        ctx.skip(kind)
        return
    ctx.decided.add(" ".join(s.text.split()))
    ctx.add(kind, lambda cid: make_check(
        ctx.report, check_id=cid, kind=kind, inputs=[("stated", stated.value, f"the figure stated ({f.group(0).strip()})")],
        conclusion=_stated_band(value, stated),
        label=f"{f.group(0).strip()} against {what} ({_fmt(value)}) of {table.document_id}",
        description=f"{_excerpt(s.text)} [{what}, from the supplied table's cells as written; {_RULE.format(tau=1)}]",
        claim_ids=_claims(ctx.report, s.text, f.group(0)), severity="error" if credited else "warning", defect="source_mismatch"))


def _year_table_derived(ctx: _Ctx, s: _Sentence, year_tables: list) -> None:
    """c3d (ge-t15): figures a sentence derives from a supplied year table's rows without writing the working ('=' or '×' lines are the
    worked reader's): an amount of a share row in the unit of the table's total row ('Wind and solar supply rose from 8.2 PJ to 163.5 PJ':
    share × total), a figure per person (the total, or a share row's amount, over the population row, units converted: 'Energy supply per
    person rose from about 34 GJ in 2005 to about 42 GJ in 2025'), the relative change of a row ('a relative rise of about 16%': (V1 − V0)
    / V0 × 100) and a share row's complement ('Domestic sources supplied 62% ... in 2005 and 56% in 2025': 100 − the imported share).
    Each figure is checked for the year written after it (or the table's two years for a from-to pair)."""
    if re.search(r"[=×÷]", s.text):
        return
    credited = bool(_YT_CREDIT_RE.search(s.text))
    index = _yt_index(s.text)
    for table in _yt_documents(year_tables):
        rows = _yt_rows(table)
        years = sorted({y for r in rows.values() for y in r})
        shares = {e for e, r in rows.items() if all(c.unit == "%" for c in r.values())}
        totals = {e: set(re.findall(r"[a-z]+", next(iter(r.values())).unit.lower())) for e, r in rows.items() if e not in shares and r}
        people = [e for e in totals if "population" in e.lower()]
        energy_total = [e for e, units in totals.items() if units & set(_ENERGY_J)]

        def share_of(at: int, y: int) -> tuple[Optional[Fraction], str]:
            """The share (a fraction) of the row, or the listed rows, the figure at ``at`` is stated for in year ``y``: 1 for the total
            or no share row; None when a listed or named share row has no cell for ``y``."""
            group = [e for e in index.group(table, at) if e in shares]
            if len(group) >= 2:
                if any(y not in rows[e] for e in group):
                    return None, ""
                return sum((rows[e][y].value for e in group), Fraction(0)) / 100, " + ".join(f"'{e}'" for e in group)
            if index.attached(table, at) == []:
                return None, ""  # (a figure in a modifier whose noun names no one row: no check, never the total row by default)
            row = index.row(table, at)
            if row in shares:
                return (rows[row][y].value / 100, f"'{row}'") if y in rows[row] else (None, "")
            return Fraction(1), ""
        # a figure per person
        if _PER_PERSON_RE.search(s.text) and len(people) == 1 and len(energy_total) == 1:
            figs = [f for f in _YT_AMOUNT_RE.finditer(s.text) if f.group("u").lower() in _ENERGY_J]
            ys = _yt_years(s.text, figs, years, index) if figs else None
            if ys:
                tot, pop = energy_total[0], people[0]
                tunit = next(iter(totals[tot] & set(_ENERGY_J)))
                pscale = next((v for k, v in _PEOPLE_SCALE.items() if k in totals[pop]), Fraction(1))
                for f, y in zip(figs, ys):
                    if y is None or y not in rows[tot] or y not in rows[pop] or rows[pop][y].value == 0 or not ctx.room("geo_table_derived"):
                        continue
                    if index.changes_before(f.start()) or _YT_WORKING_AFTER_RE.match(s.text, f.end()):
                        continue  # a change of the level per person, not the level ('growth in supply per person reached 9.3 GJ'), or a
                        # figure with its working in brackets after it (the worked reader's)
                    share, named = share_of(f.start(), y)
                    if share is None:
                        continue
                    value = share * rows[tot][y].value * _ENERGY_J[tunit] / (rows[pop][y].value * pscale) / _ENERGY_J[f.group("u").lower()]
                    _yt_check(ctx, s, "geo_table_derived", f, value, f"the {f'share of {named} × ' if share != 1 else ''}total per person for {y}",
                              table, credited)
            continue
        # an amount of a share row (or of a list of share rows, or the total row itself) in the total row's unit
        if totals:
            figs = [f for f in _YT_AMOUNT_RE.finditer(s.text) if sum(1 for e, u in totals.items() if f.group("u").lower() in u and e not in people) == 1]
            ys = _yt_years(s.text, figs, years, index) if figs else None
            for f, y in zip(figs, ys or []):
                if y is None or not ctx.room("geo_table_derived") or index.changes_before(f.start()) or _YT_WORKING_AFTER_RE.match(s.text, f.end()):
                    continue  # (a figure with its working in brackets, "251 PJ (22% of 1,050 PJ)", is the worked reader's)
                tot = next(e for e, u in totals.items() if f.group("u").lower() in u and e not in people)
                if y not in rows[tot]:
                    continue
                group = [e for e in index.group(table, f.start()) if e in shares]
                row = None if len(group) >= 2 else index.row(table, f.start())
                if len(group) >= 2:
                    if any(y not in rows[e] for e in group):
                        continue
                    value = sum((rows[e][y].value for e in group), Fraction(0)) / 100 * rows[tot][y].value
                    what = f"the shares of {' + '.join(repr(e) for e in group)} × '{tot}' for {y}"
                elif row == tot:
                    value, what = rows[tot][y].value, f"the row '{tot}' for {y}"  # (the total row's own cell: 'rose from 820 PJ to 1,500 PJ')
                elif row in shares and y in rows[row]:
                    value, what = rows[row][y].value / 100 * rows[tot][y].value, f"the share of '{row}' × '{tot}' for {y}"
                else:
                    continue
                _yt_check(ctx, s, "geo_table_derived", f, value, what, table, credited)
        # a share stated for a list of share rows ('Coal and oil together supplied 77 % of primary energy in 2005'): the sum of their
        # cells; and a share of one share row its clause names only by its head ('Imports made up 54% of supply in 2025, up from 38% in
        # 2005'), which the shared table reader (every word of the row named) leaves unread: its cell (c3e left)
        words = {w for _p, w in index.toks}
        pcts = list(_YT_PCT_RE.finditer(s.text))
        # (the years of the sentence's per cents read together: a from-to pair with no year written takes the table's two years,
        # "The share of supply that is imported rose from 38% to 46%"; check round 12 of c3f, where each was read alone and none had
        # a year)
        pct_years = (_yt_years(s.text, pcts, years, index) or [None] * len(pcts)) if pcts else []
        for f_i, f in enumerate(pcts):
            group = [e for e in index.group(table, f.start()) if e in shares]
            if len(group) < 2:
                row = index.row(table, f.start())
                if row not in shares or not ctx.room("geo_table_derived") or index.changes_before(f.start()):
                    continue
                if next((r for r in _yt_row_vocab(table)[0] if r.entity == row and r.words and r.words <= words), None) is not None:
                    continue  # (every word of the row named: the shared reader's)
                y = pct_years[f_i]
                if y is None or y not in rows[row]:
                    continue
                _yt_check(ctx, s, "geo_table_derived", f, rows[row][y].value, f"the cell of '{row}' for {y}", table, credited)
                continue
            if not ctx.room("geo_table_derived"):
                continue
            y = pct_years[f_i]
            if y is None or any(y not in rows[e] for e in group):
                continue
            _yt_check(ctx, s, "geo_table_derived", f, sum((rows[e][y].value for e in group), Fraction(0)),
                      f"the sum of the shares of {' + '.join(repr(e) for e in group)} for {y}", table, credited)
        # the relative change of a row
        for m in _REL_CHANGE_RE.finditer(s.text):
            row = index.row(table, m.start())
            if row is None or row not in rows:
                continue
            ys_ = sorted({int(y) for y in _YEAR_IN_RE.findall(s.text)} & set(rows[row])) or sorted(rows[row])
            if len(ys_) != 2 or rows[row][ys_[0]].value == 0:
                continue
            v0, v1 = rows[row][ys_[0]].value, rows[row][ys_[1]].value
            down = (m.group("dir") or m.group("dir2") or "").lower().startswith(_DOWN_WORDS)
            value = (v0 - v1 if down else v1 - v0) / v0 * 100
            g = "n" if m.group("n") else "n2"

            class _F:  # the stated per cent as a match-like figure
                def __init__(self, mm, grp):
                    self.mm, self.grp = mm, grp

                def group(self, k):
                    return self.mm.group(self.grp) if k == "n" else self.mm.group(0)

                def start(self):
                    return self.mm.start(self.grp)
            _yt_check(ctx, s, "geo_table_derived", _F(m, g), value, f"the relative change of '{row}' from {ys_[0]} to {ys_[1]}", table, credited)
        # a share row's complement
        lower = s.text.lower()
        for row in shares:
            own = [w for w in re.findall(r"[a-z]{3,}", row.lower()) if w not in _FUNCTION_WORDS and sum(1 for o in rows if w in o.lower()) == 1]
            comp = [c for w in own for c in (_COMPLEMENTS.get(w, ()) + (f"non-{w}", f"not {w}"))]
            if not comp or any(re.search(r"(?<![\w-])" + re.escape(w) + r"\b", lower) for w in own):
                continue
            if not any(re.search(r"(?<![\w-])" + re.escape(c) + r"\b", lower) for c in comp):
                continue
            figs = list(_YT_PCT_RE.finditer(s.text))
            ys = _yt_years(s.text, figs, years) if figs else None
            for f, y in zip(figs, ys or []):
                if y in rows[row]:
                    _yt_check(ctx, s, "geo_table_derived", f, 100 - rows[row][y].value, f"the complement (100 − '{row}') for {y}", table, credited)


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


#: A pair of figures in brackets that a comparison stated before it rests on (attack round 8): "(36 mm against 38 mm)", "(6.2 against
#: 7.1)", "(130 of 185)", "(10 km vs 5 km)". Up to two unit tokens after each figure; nothing else stands in the bracket.
_PAIR_SEP = r"against|vs\.?|versus|compared\s+(?:with|to)|to|and|of|out\s+of|÷"
_PAIR_UNIT = r"(?:\s*+(?!(?:" + _PAIR_SEP + r")\b)[^\d\s(),;:÷]{1,8}){0,2}"
_BRACKET_PAIR_RE = re.compile(r"\(\s*+(?P<from>from\s++)?(?P<a>" + _NUM + r")(?P<au>" + _PAIR_UNIT + r")\s++(?P<sep>" + _PAIR_SEP + r")\s++(?P<b>" + _NUM + r")(?P<bu>"
                              + _PAIR_UNIT + r")\s*+\)", re.IGNORECASE)
_CMP_WORD = (r"more|less|fewer|smaller|larger|bigger|greater|higher|lower|further|farther|nearer|closer|sooner|later|earlier|deeper|shallower|"
             r"longer|shorter|wider|narrower|heavier|lighter|older|younger|warmer|colder|cooler|faster|slower|stronger|weaker|wetter|drier|"
             r"steeper|gentler|bigger|richer|poorer")
#: The stated figure of a share before an "(A of B)" pair: "At least 80% of the aftershock's deaths ... (130 of 185)".
_SHARE_STATED_RE = re.compile(_num_re("n", scale=False) + r"\s*+(?:%|per\s*+cent\b|percent\b)\s++of\b", re.IGNORECASE)
#: A relative comparison before a pair: "about 15% lower in Storm 2 than in Storm 1 (36 mm against 38 mm)".
_PCT_CMP_RE = re.compile(_num_re("n", scale=False) + r"\s*+(?:%|per\s*+cent\b|percent\b)\s++(?:" + _CMP_WORD + r")\b[^.;()]{0,120}?\bthan\b", re.IGNORECASE)
#: A difference before a pair: "1.9 magnitude units smaller than the Darfield earthquake (6.2 against 7.1)", "about 25 km further ... than".
_DIFF_CMP_RE = re.compile(_num_re("n", scale=False) + r"(?!\s*+(?:%|per\s*+cent|percent|times)\b)(?:\s++[^\d\s(),;.]{1,12}){0,3}?\s++(?:" + _CMP_WORD
                          + r")\b[^.;()]{0,120}?\bthan\b", re.IGNORECASE)
#: A multiple before a pair: "about three times as deep as the aftershock (10 km against 5 km)", "two and a half times that of",
#: "twice as deep as", "half as deep as".
_FOLD_K = (r"(?P<k>(?:(?:" + _WORD_NUMBER + r"|\d{1,3}(?:\.\d{1,3})?)(?:\s++and\s++a\s++(?:half|quarter))?\s++times)|twice|half|a\s+third|a\s+quarter|"
           r"one\s+third|one\s+quarter)")
_FOLD_CMP_RE = re.compile(r"(?P<ap>\b(?:about|around|roughly|nearly|almost|approximately)\s++)?\b" + _FOLD_K + r"\s++(?:as\s++[a-z]{2,20}\s++as|that\s++of|those\s++of|"
                          r"(?:" + _CMP_WORD + r")\s++than|the\s++[a-z]{2,20}\s++of)\b", re.IGNORECASE)
_THAN_RE = re.compile(r"\bthan\b", re.IGNORECASE)
#: After "than ...": a phrase that starts a new noun before the pair ("than Storm 1 from similar rainfall (...)"), or more than six words.
_PAIR_DETACHED_RE = re.compile(r"\b(?:from|with|despite|because|although|though|while|whereas|given|after|before|during|for|on|over|under|"
                               r"which|who|where|when|but|and)\b|^(?:\s*+\S++){7}", re.IGNORECASE)
_FOLD_FRACTIONS = {"half": Fraction(1, 2), "twice": Fraction(2), "a third": Fraction(1, 3), "one third": Fraction(1, 3), "a quarter": Fraction(1, 4),
                   "one quarter": Fraction(1, 4)}


def _fold_value(k: str) -> tuple[Optional[Fraction], Fraction]:
    """The multiple a fold phrase states and its tolerance: "three times" 3 (half a unit), "two and a half times" 2.5 (a quarter), "2.5
    times" (half a unit of its last digit), "twice" 2, "half" 1/2 (5%)."""
    from .grounded_figures import _half
    k = " ".join(k.lower().split())
    if k in _FOLD_FRACTIONS:
        v = _FOLD_FRACTIONS[k]
        return v, v / 20
    m = re.fullmatch(r"(\S+)(?: and a (half|quarter))? times", k)
    if m is None:
        return None, Fraction(0)
    base = m.group(1)
    v = Fraction(_WORD_NUMBERS[base]) if base in _WORD_NUMBERS else Fraction(base) if re.fullmatch(r"\d{1,3}(?:\.\d{1,3})?", base) else None
    if v is None:
        return None, Fraction(0)
    if m.group(2):
        return v + (Fraction(1, 2) if m.group(2) == "half" else Fraction(1, 4)), Fraction(1, 8 if m.group(2) == "half" else 16)
    return v, (_half(base) if base[0].isdigit() else Fraction(1, 2))


def _stated_band(value: Fraction, stated: Fig, tau: Optional[Fraction] = None) -> dict:
    """The stated figure (the symbol ``stated``) against a value computed from figures as written: ``|stated − value| <= h + tau |value|``,
    or the one-sided bound a comparative word sets ('at least 80%': ``stated − value <= h``; 'under 80%': ``stated − value >= −h``)."""
    t = tau if tau is not None else (TAU_APPROX if stated.approx else TAU)
    d = {"op": "sub", "left": _var("stated"), "right": _real(value)}
    if stated.side == "lower":
        return {"op": "le", "left": d, "right": _real(stated.half)}
    if stated.side == "upper":
        return {"op": "ge", "left": d, "right": _real(-stated.half)}
    return {"op": "le", "left": _abs(d), "right": _real(stated.half + t * abs(value))}


def _pair_comparison(ctx: _Ctx, s: _Sentence) -> None:
    """Attack round 8 (ge-p9c, ge-t16): a comparison stated before the pair of figures it rests on, in brackets: a difference ("1.9 magnitude
    units smaller than ... (6.2 against 7.1)": |A − B|), a relative difference ("about 15% lower ... than ... (36 mm against 38 mm)": |A − B|
    over either figure), a multiple ("three times as deep as ... (10 km against 5 km)": the larger over the smaller, or its inverse for a
    fraction), a share ("At least 80% of ... (130 of 185)": A / B × 100). The figures are the sentence's own; a pair of years is a period."""
    if "(" not in s.text:
        return
    for pm in _BRACKET_PAIR_RE.finditer(s.text):
        a, b = _num(pm.group("a")), _num(pm.group("b"))
        if _YEAR_IN_RE.fullmatch(pm.group("a")) and _YEAR_IN_RE.fullmatch(pm.group("b")):
            continue
        lo = max(s.text.rfind(";", 0, pm.start()), s.text.rfind(")", 0, pm.start()), s.text.rfind("(", 0, pm.start()), pm.start() - 240) + 1
        pre = s.text[lo:pm.start()]
        than = list(_THAN_RE.finditer(pre))
        if than and _PAIR_DETACHED_RE.search(pre, than[-1].end()):
            continue  # "a peak 200% higher than Storm 1 from similar rainfall (36 mm against 38 mm)": the pair is the later phrase's, not
            # the comparison's (attack round 8)
        if any(t.end() == pm.end() - lo + lo and t.start() >= lo for t in _TIMES_PAIR_RE.finditer(s.text, lo, pm.end())):
            continue  # "N times as many ... (A against B)": read by the multiple reader
        sep = " ".join(pm.group("sep").lower().split())
        found = None
        if sep in ("of", "out of", "÷"):
            # ("about 9% of Site 1's (19 ÷ 214)": a share worked out in brackets; check round 9 of c3c)
            sh = list(_SHARE_STATED_RE.finditer(pre))
            if sh and b != 0:
                found = ("share", sh[-1], [a / b * 100], f"{pm.group('a')} / {pm.group('b')} × 100")
        elif sep not in ("and", "to") or (sep == "to" and pm.group("from")):  # "(from 38 mm to 36 mm)": the pair a change compares (c3e)
            fold = list(_FOLD_CMP_RE.finditer(pre))
            pct = list(_PCT_CMP_RE.finditer(pre))
            diff = list(_DIFF_CMP_RE.finditer(pre))
            last = max([(x.start(), "fold", x) for x in fold] + [(x.start(), "pct", x) for x in pct] + [(x.start(), "diff", x) for x in diff],
                       default=None, key=lambda t: t[0])
            if last is not None:
                _pos, kind, x = last
                if kind == "fold" and a > 0 and b > 0:
                    k, ktol = _fold_value(x.group("k"))
                    if k is not None:
                        hi, low = max(a, b), min(a, b)
                        found = ("fold", x, [hi / low if k >= 1 else low / hi], f"the ratio of {pm.group('a')} and {pm.group('b')}", k, ktol)
                elif kind == "pct" and a != 0 and b != 0:
                    found = ("pct", x, [abs(a - b) / b * 100, abs(a - b) / a * 100], f"|{pm.group('a')} − {pm.group('b')}| over either figure × 100")
                elif kind == "diff":
                    found = ("diff", x, [abs(a - b)], f"|{pm.group('a')} − {pm.group('b')}|")
        if found is None or not ctx.room("geo_pair_comparison"):
            continue
        kind, x, values, what = found[0], found[1], found[2], found[3]
        if kind == "fold":
            k, ktol = found[4], found[5]
            if x.group("ap"):
                ktol = max(ktol, k / 10)
            stated = Fig(k, x.group("k"), ktol, False, "both")
            options = [{"op": "le", "left": _abs({"op": "sub", "left": _real(v), "right": _var("stated")}), "right": _real(ktol)} for v in values]
            shown = x.group("k")
        else:
            stated = _fig(x, "n", pre)
            options = [_stated_band(v, stated) for v in values]
            shown = stated.shown + ("%" if kind in ("share", "pct") else "")
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_pair_comparison", lambda cid, stated=stated, options=options, what=what, shown=shown, kind=kind, pm=pm, x=x: make_check(
            ctx.report, check_id=cid, kind="geo_pair_comparison", inputs=[("stated", stated.value, f"the {kind} stated ({shown})")],
            conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
            label=f"the {kind} stated ({shown}) against {what}",
            description=(f"{_excerpt(s.text)} [a comparison stated before the pair it rests on holds of that pair: a difference |A − B|, a relative "
                         f"difference |A − B| over either figure, a multiple the larger over the smaller, a share A / B × 100; {_RULE.format(tau=1)}]"),
            claim_ids=_claims(ctx.report, s.text, x.group(0) + " " + pm.group(0)), defect="stem_arithmetic_slip"))


_YEARS_APART_RE = re.compile(r"\b(?P<n>\d{1,3})\s+years?\s+(?:apart|between\s+them)\b[^.;()]{0,40}?\(\s*(?P<a>(?:1[5-9]|20)\d{2})\s*(?:and|to|–|-|—|&)\s*"
                             r"(?P<b>(?:1[5-9]|20)\d{2})\s*\)", re.IGNORECASE)


def _years_apart(ctx: _Ctx, s: _Sentence) -> None:
    """Check round 9 of c3c (ge-p9c): an interval in years stated before the two years it spans ("The two storms were 16 years apart
    (2006 and 2024)."): the difference of the years."""
    for m in _YEARS_APART_RE.finditer(s.text):
        n, a, b = int(m.group("n")), int(m.group("a")), int(m.group("b"))
        if not ctx.room("geo_pair_comparison"):
            return
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_pair_comparison", lambda cid, n=n, a=a, b=b, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_pair_comparison", inputs=[("stated", Fraction(n), f"the interval stated ({m.group('n')} years)")],
            conclusion={"op": "eq", "left": _var("stated"), "right": _real(Fraction(abs(b - a)))},
            label=f"the interval stated ({n} years) against {max(a, b)} − {min(a, b)} = {abs(b - a)}",
            description=f"{_excerpt(s.text)} [an interval in years stated before the two years it spans is their difference]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


_LEN_M = {"mm": Fraction(1, 1000), "cm": Fraction(1, 100), "m": Fraction(1), "metres": Fraction(1), "meters": Fraction(1), "km": Fraction(1000),
          "kilometres": Fraction(1000), "kilometers": Fraction(1000)}
_AREA_M2 = {"mm²": Fraction(1, 10**6), "mm2": Fraction(1, 10**6), "cm²": Fraction(1, 10**4), "cm2": Fraction(1, 10**4), "m²": Fraction(1), "m2": Fraction(1),
            "square metres": Fraction(1), "square meters": Fraction(1), "km²": Fraction(10**6), "km2": Fraction(10**6), "square kilometres": Fraction(10**6),
            "square kilometers": Fraction(10**6), "ha": Fraction(10**4), "hectares": Fraction(10**4)}
_LEN_U = r"(?:kilomet(?:re|er)s|metres|meters|km|cm|mm|m)(?![\w²³])"
_AREA_U = r"(?:square\s+kilomet(?:re|er)s|square\s+met(?:re|er)s|km²|km2|cm²|cm2|mm²|mm2|m²|m2|hectares|ha)(?![\w²³])"
_DIM_WORD = r"(?:wide|deep|long|high|tall|across)"
#: What introduces the area two dimensions give: the word 'area', a cross-section or surface, or a result verb before an area unit (c3e:
#: "measures 6.0 m by 1.8 m, giving 12.8 m²", "giving a cross-section of 9.8 m²"; only 'an area of' was read).
_AREA_RESULT = (r"(?:\barea\b|\bcross[-\s]?section(?:al)?s?\b|\bsurface\b|\bfootprint\b|\b(?:giv(?:ing|es?)|gave|mak(?:ing|es?)|made|produc(?:ing|es?)|"
                r"yield(?:ing|s)?|hence|thus|so|which\s+(?:is|was|gives?|makes?)|that\s+is|i\.e\.)"
                # (the area figure is the result's own object, "giving 12.8 m²", "so the area is 10.8 m²", "giving a cross-section of 9.8
                # m²"; a result verb before any other phrase that holds an area figure binds nothing: "so the catchment of 24 km² drains
                # ...", "giving a sample of 24 km²", "which is small for a 24 km² catchment"; check round 11 of c3e)
                r"(?=(?:\s*+,)?\s++(?:(?:(?:a|an|the|its)\s++)?(?:(?:total|cross[-\s]?sectional|surface|channel|plan|wetted)\s++)?"
                r"(?:area|cross[-\s]?section)\s++(?:(?:of|is|was|=)\s++)?)?(?:(?:about|around|roughly|approximately|nearly)\s++)?(?<![\d.,])(?:"
                + _NUM + r")(?![\d,]\d|\.\d)\s*+" + _AREA_U + r"))")
#: Two dimensions with the area they give (c3d, ge-p9c: "The channel was 6.0 m wide and 2.8 m deep, an area of 10.8 m²."): "A m wide and
#: B m deep", "A m by B m", "A m × B m", then the area within the sentence.
_DIM_AREA_RE = re.compile(r"(?<![\d.,])(?P<a>" + _NUM + r")\s*+(?P<ua>" + _LEN_U + r")(?:\s++" + _DIM_WORD + r")?\s*+(?:,\s*+)?(?:and|by|×|x|,)\s*+"
                          r"(?:(?:a|an|the)\s+(?:mean\s+|average\s+)?(?:depth|width|length|height)\s+of\s+)?(?<![\d.,])(?P<b>" + _NUM + r")\s*+(?P<ub>" + _LEN_U
                          + r")(?:\s++" + _DIM_WORD + r")?(?P<mid>[^.;\d=]{0,60}?)" + _AREA_RESULT + r"[^.;\d=]{0,40}?(?P<ap>(?:about|around|roughly|approximately|nearly)\s++)?"
                          r"(?<![\d.,])(?P<c>" + _NUM + r")(?![\d,]\d|\.\d)\s*+(?P<uc>" + _AREA_U + r")", re.IGNORECASE)


def _dimension_area(ctx: _Ctx, s: _Sentence) -> None:
    """c3d (ge-p9c): an area stated with the two dimensions it is the product of ("6.0 m wide and 2.8 m deep, an area of 10.8 m²", "a plot
    40 m by 25 m, an area of 0.1 ha"): the area equals the product, units converted exactly; half a unit of its last digit and 1% (5%
    after an approximation word), operands as written. A sentence that writes the product as an equation is the worked reader's."""
    from .grounded_figures import _half
    if not re.search(r"²|\b(?:m2|km2|cm2|mm2|ha|hectares|square)\b", s.text):
        return
    for m in _DIM_AREA_RE.finditer(s.text):
        fa, fb = _LEN_M.get(m.group("ua").lower()), _LEN_M.get(m.group("ub").lower())
        fc = _AREA_M2.get(" ".join(m.group("uc").lower().split()))
        if fa is None or fb is None or fc is None or not ctx.room("geo_dimension_area"):
            continue
        value = _num(m.group("a")) * fa * _num(m.group("b")) * fb / fc
        stated = Fig(_num(m.group("c")), m.group("c"), _half(m.group("c").replace(",", "")), bool(m.group("ap")))
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_dimension_area", lambda cid, value=value, stated=stated, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_dimension_area", inputs=[("stated", stated.value, f"the area stated ({m.group('c')} {m.group('uc')})")],
            conclusion=_stated_band(value, stated),
            label=f"{m.group('a')} {m.group('ua')} × {m.group('b')} {m.group('ub')} is {_fmt(value)} {m.group('uc')}",
            description=f"{_excerpt(s.text)} [an area stated with its two dimensions equals their product, units converted exactly; {_RULE.format(tau=1)}]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))



#: "8% of the 24 km² catchment, about 1.9 km², was built up": a part stated with its share of a whole and the whole (check round 12 of
#: c3f, ge-p9c): the part equals share × whole, in the whole's unit.
_SHARE_PART_RE = re.compile(r"(?<![\d.,])(?P<p>" + _NUM + r")\s*+(?:%|per\s*+cent\b|percent\b)\s++of\s++(?:the\s++|its\s++|a\s++|an\s++)?"
                            r"(?<![\d.,])(?P<a>" + _NUM + r")(?![\d,]\d|\.\d)\s*+(?P<ua>" + _AREA_U + r")(?:\s++[a-z]{3,15}){0,2},?\s++"
                            r"(?:or\s++|that\s+is\s++|i\.e\.\s*+)?(?P<ap>(?:about|around|roughly|approximately|nearly|some)\s++)?(?<![\d.,])(?P<c>" + _NUM + r")"
                            r"(?![\d,]\d|\.\d)\s*+(?P<uc>" + _AREA_U + r")", re.IGNORECASE)


def _share_part(ctx: _Ctx, s: _Sentence) -> None:
    """Check round 12 of c3f (ge-p9c): a part stated with its share of a whole and the whole ("8% of the 24 km² catchment, about
    1.9 km²"): the part equals share / 100 × whole, units converted exactly; half a unit of its last digit and 1% (5% after an
    approximation word)."""
    from .grounded_figures import _half
    if "%" not in s.text and "cent" not in s.text.lower():
        return
    for m in _SHARE_PART_RE.finditer(s.text):
        fa = _AREA_M2.get(" ".join(m.group("ua").lower().split()))
        fc = _AREA_M2.get(" ".join(m.group("uc").lower().split()))
        if fa is None or fc is None or not ctx.room("geo_share_part"):
            continue
        value = _num(m.group("p")) / 100 * _num(m.group("a")) * fa / fc
        stated = Fig(_num(m.group("c")), m.group("c"), _half(m.group("c").replace(",", "")), bool(m.group("ap")))
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_share_part", lambda cid, value=value, stated=stated, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_share_part", inputs=[("stated", stated.value, f"the part stated ({m.group('c')} {m.group('uc')})")],
            conclusion=_stated_band(value, stated),
            label=f"{m.group('p')}% of {m.group('a')} {m.group('ua')} is {_fmt(value)} {m.group('uc')}",
            description=f"{_excerpt(s.text)} [a part stated with its share and its whole equals share × whole, units converted exactly; {_RULE.format(tau=1)}]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))

_VOL_M3 = {"m³": Fraction(1), "m3": Fraction(1), "cubic metres": Fraction(1), "cubic meters": Fraction(1), "km³": Fraction(10**9), "km3": Fraction(10**9),
           "litres": Fraction(1, 1000), "liters": Fraction(1, 1000), "l": Fraction(1, 1000), "megalitres": Fraction(1000), "megaliters": Fraction(1000),
           "ml": Fraction(1000)}
_VOL_SCALE = {"thousand": Fraction(10**3), "million": Fraction(10**6), "billion": Fraction(10**9)}
#: A depth of rain (or water) over an area with the volume it gives (c3d, ge-p9c: "Storm 1's 38 mm over 24 km² is about 91,200 m³ of
#: water"): the volume is depth × area, units converted exactly.
_DEPTH_VOLUME_RE = re.compile(r"(?<![\d.,])(?P<d>" + _NUM + r")\s*+(?P<ud>mm|cm|m)(?![\w²³])\s++(?:of\s++(?:rain(?:fall)?|water|precipitation|runoff)\s++)?"
                              r"(?:over|on|across|onto|on\s+to|falling\s+on|falling\s+over|spread\s+over)\s++(?:(?:a|an|the|its|whole|entire)\s++){0,2}"
                              r"(?:[a-z]{3,15}\s++){0,2}?(?:of\s++)?(?<![\d.,])(?P<a>" + _NUM + r")\s*+(?P<ua>" + _AREA_U + r")(?P<mid>[^.;=\d]{0,60}?)"
                              r"(?P<ap>(?:about|around|roughly|approximately|nearly|some)\s++)?(?<![\d.,])(?P<v>" + _NUM + r")(?![\d,]\d|\.\d)"
                              r"(?:\s*+[×x*]\s*+10\s*+(?:\^\s*+(?P<ex>[−-]?\d{1,2})|(?P<sup>[⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,2})))?\s*+"
                              r"(?P<sc>thousand|million|billion)?\s*+(?P<uv>m³|m3|cubic\s+met(?:re|er)s|km³|km3|megalit(?:re|er)s|litres|liters|ML|l)(?![\w²³])",
                              re.IGNORECASE)


def _depth_volume(ctx: _Ctx, s: _Sentence) -> None:
    """c3d (ge-p9c): a volume stated with the depth of water and the area it falls on ("38 mm over 24 km² is about 912,000 m³"): the volume
    equals depth × area, units converted exactly; half a unit of its last digit and 1% (5% after an approximation word)."""
    from .grounded_figures import _half
    for m in _DEPTH_VOLUME_RE.finditer(s.text):
        fd = _LEN_M.get(m.group("ud").lower())
        fa = _AREA_M2.get(" ".join(m.group("ua").lower().split()))
        uv = " ".join(m.group("uv").split())
        fv = _VOL_M3.get(uv if uv == "ML" else uv.lower()) if uv != "ML" else Fraction(1000)
        if fd is None or fa is None or fv is None or not ctx.room("geo_depth_volume"):
            continue
        scale = _VOL_SCALE.get((m.group("sc") or "").lower(), Fraction(1))
        # c3e: a volume in powers of ten ("9.12 × 10⁴ m³") is the mantissa times its power, its half-unit scaled with it
        ex = m.group("ex") or (m.group("sup") or "").translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-"))
        power = Fraction(10) ** int(ex.replace("−", "-")) if ex else Fraction(1)
        value = _num(m.group("d")) * fd * _num(m.group("a")) * fa / fv / scale
        stated = Fig(_num(m.group("v")) * power, m.group("v") + (f" × 10^{ex}" if ex else ""), _half(m.group("v").replace(",", "")) * power,
                     bool(m.group("ap")))
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_depth_volume", lambda cid, value=value, stated=stated, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_depth_volume", inputs=[("stated", stated.value, f"the volume stated ({m.group('v')} {(m.group('sc') or '') + ' ' if m.group('sc') else ''}{m.group('uv')})")],
            conclusion=_stated_band(value, stated),
            label=f"{m.group('d')} {m.group('ud')} over {m.group('a')} {m.group('ua')} is {_fmt(value)} {(m.group('sc') or '') + ' ' if m.group('sc') else ''}{m.group('uv')}",
            description=f"{_excerpt(s.text)} [a volume stated with a depth of water and the area it covers equals depth × area, units converted exactly; {_RULE.format(tau=1)}]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


@lru_cache(maxsize=64)
def _column_values(table: _AttrTable) -> tuple[tuple, ...]:
    """Per column of ``table``, the number of each row's cell (``grounded_figures._number``, None for a cell that is not one number).
    The values depend on the table alone: read once per table, never again for every sentence (repair 1 after clearance c3c: a
    hostile answer of thousands of sentences with digits read the whole supplied table again for each, about half the pack's time)."""
    from .grounded_figures import _number
    return tuple(tuple(_number(cells[k + 1]) for _l, cells in table.rows) for k in range(len(table.columns)))


def _table_aggregates(ctx: _Ctx, s: _Sentence, tables: list[_AttrTable]) -> None:
    """Attack round 3 (ge-t14): a supplied table read as a whole: the mean of one column over every row ("The mean EQS across your ten
    sites is 16.3"), and the spacing and length of a transect against the table's distance column ("ten sites at 100 m intervals", "a
    900 m transect"). A sentence that names a row or lists its own values is left to the other readers."""
    from .grounded_figures import _half
    for table in tables:
        toks = list(_TOKEN_RE.finditer(s.text))
        stems = {_stem(t.group(0)) for t in toks if t.group(0)[0].isalpha()}
        cols = [k for k, (_h, st) in enumerate(table.columns) if st and st & stems]
        values = _column_values(table)
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
#: An earthquake's depth (attack round 8): "at a depth of about 5 km", "about 10 km deep".
_DEPTH_RE = re.compile(r"\b(?:at\s+a\s+)?(?:depth|focus)\s+of\s++(?P<pre>(?:about|around|roughly|approximately|nearly|almost|some)\s+)?(?<![\d.,])"
                       r"(?P<n>\d{1,3}(?:\.\d)?)\s*+km\b|(?P<pre2>\b(?:about|around|roughly|approximately|nearly|almost|some)\s+)?(?<![\d.,])"
                       r"(?P<m>\d{1,3}(?:\.\d)?)\s*+(?:km|kilomet(?:re|er)s?)\s++(?:deep|below\s+the\s+surface)\b", re.IGNORECASE)
#: The event a sentence names first: "the Darfield earthquake", "a magnitude 6.2 aftershock", "the aftershock".
_EVENT_PHRASE_RE = re.compile(r"(?:\b(?P<name>[A-Z][a-zà-ÿ'’-]{2,30})\s+)?\b(?P<ev>earthquake|aftershock|quake|eruption|tremor)s?\b")
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


#: How far before "of them" its head noun is looked for (characters).
_OF_THEM_WINDOW = 400


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
            # (the head noun "of them" refers to, looked for in a bounded window before it: a scan from the sentence's start for each
            # match was quadratic in a long sentence of such phrases; check round 11 of c3e)
            heads = list(_HEAD_BEFORE_RE.finditer(s.text, max(0, m.start() - _OF_THEM_WINDOW), m.start()))
            if heads:
                found.append((m, m.group("n"), _HEAD_NOUNS[heads[-1].group(1).lower()], (m.group("pre") or "").strip().lower(), ""))
        for m in _MAGNITUDE_RE.finditer(s.text):
            found.append((m, m.group("n") or m.group("m"), "magnitude", "", ""))
        depths = list(_DEPTH_RE.finditer(s.text))
        if depths:
            # an earthquake's depth belongs to the event its sentence names first ("a magnitude 6.2 aftershock struck ... at a depth of
            # about 5 km"; "At about 15 km deep, the aftershock was ..."), never to the place nearest the figure (attack round 8)
            ev = _EVENT_PHRASE_RE.search(s.text)
            if ev is not None:
                name = ev.group("name")
                key = (name.lower() if name and name not in _NOT_PLACES else ev.group("ev").lower(), "depth")
                for m in depths:
                    raw = m.group("n") or m.group("m")
                    pre = (m.group("pre") or m.group("pre2") or "").strip().lower()
                    v = Fraction(raw.replace(",", ""))
                    lo_, hi_ = (v * Fraction(95, 100), v * Fraction(105, 100)) if pre else (v, v)
                    if len(index) < 64 or key in index:
                        bucket = index.setdefault(key, [])
                        if len(bucket) < 16:
                            bucket.append((lo_, hi_, m.group(0), s, raw))
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


# ------------------------------------------------------------------------------------------------------------------ attack round 8
#: A labelled thing a request or an answer gives figures for: "Storm 1", "Site 4", "Station 2".
_FACT_LABEL_RE = re.compile(r"\b(?:Storm|Site|Station|Zone|Area|Sample|Quadrat|Transect|Point|Plot|Event|Well|Borehole|Village|Town|Ward|District|Region)\s\d{1,3}\b")
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(r"\b(?P<d>\d{1,2})\s++(?P<mo>" + _MONTHS + r")\s++(?P<y>1[89]\d{2}|20\d{2})\b|\b(?P<mo2>" + _MONTHS + r")\s++(?P<d2>\d{1,2}),?\s++"
                      r"(?P<y2>1[89]\d{2}|20\d{2})\b")
#: The units a stated fact is compared in (closed); a fact is compared only with a fact of the same unit as written.
_FACT_UNITS = {"km²": "km2", "km2": "km2", "km^2": "km2", "sq km": "km2", "m²": "m2", "m2": "m2", "ha": "ha", "hectares": "ha", "mm": "mm", "cm": "cm",
               "km": "km", "m": "m", "m³ s⁻¹": "cumec", "m3 s-1": "cumec", "m³/s": "cumec", "m3/s": "cumec", "cumecs": "cumec", "°c": "degc",
               "pj": "pj", "gj": "gj", "mj": "mj", "tonnes": "t", "kg": "kg"}
_FACT_FIG_RE = re.compile(r"(?<![\d.,])(?P<n>" + _NUM + r")(?![\d,]\d|\.\d)\s*+(?P<u>km²|km2|km\^2|sq\s?km|m³\s?s⁻¹|m3\s?s-1|m³/s|m3/s|cumecs|m²|m2|"
                          r"hectares|ha|mm|cm|km|m|°C|PJ|GJ|MJ|tonnes|kg)(?![\w²³⁻/])", re.IGNORECASE)
#: Words a fact's noun is never: the frame words of a change, a comparison or a period (a figure after them is derived, never restated).
_FACT_SKIP = frozenset("of is was were are a an the about approximately around roughly some its their his her this that at with".split())
_FACT_FRAME = frozenset("from to by than between and or rose fell grew increased decreased dropped declined changed difference more less over under "
                        "nearly almost per each every within than up down only just".split())
_FACT_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]{0,30}|[^\sA-Za-z]")


#: After a figure: a comparison or a change it measures, or its working in brackets (a derived figure, never a restated fact).
# (a total is derived too, "74 mm of rain in total (38 + 36)", and so is a figure a worked bracket follows a few words later:
# check round 10 of c3d, a correct sum of the request's two figures was compared with each of them)
_FACT_DERIVED_AFTER_RE = re.compile(r"[^.;(]{0,40}?\b(?:above|below|more|less|fewer|higher|lower|greater|smaller|larger|than|up|down|over|under|ahead|behind|"
                                    r"short|increase|rise|fall|drop|change|difference|sooner|later|earlier|further|faster|slower|"
                                    r"total|totals|altogether|combined|together|sum)\b|[^.;()]{0,40}?\([^()]{0,60}[+−×÷/*-]",
                                    re.IGNORECASE)


#: The noun a figure names AFTER it, which outranks the word before it (c3d, ge-p9c): a dimension adjective ('6.0 m wide and 2.8 m deep'
#: -> width, depth; the 'and' before '2.8' left it with no noun, so a depth against the request's 'mean depth of 1.8 m' was never
#: compared) or an 'of' phrase ('38 mm of rain' -> rain, where a colon before the figure left none).
_FACT_AFTER_RE = re.compile(r"\s*+(?:(?P<dim>wide|deep|long|high|tall|thick|across|in\s+diameter)\b|of\s++(?:the\s++)?(?P<of>[a-z]{3,20})\b)", re.IGNORECASE)
_FACT_DIMENSIONS = {"wide": "width", "across": "width", "deep": "depth", "long": "length", "high": "height", "tall": "height", "thick": "thickness",
                    "in diameter": "diameter"}


#: The nouns of one quantity under another name (closed): a fact of '38 mm of rain' is the rainfall of the same storm (c3e: "Storm 1 got
#: roughly 10% more rainfall than Storm 2" was never compared, the request's facts being 'rain').
_FACT_SAME_NOUN = {"rainfall": "rain", "precipitation": "rain", "rains": "rain"}


def _fact_noun(w: str) -> str:
    """A fact's noun as compared: singular, and under the one name of its quantity."""
    w = w.lower()
    w = _FACT_SAME_NOUN.get(w, w)
    return w[:-1] if w.endswith("s") and len(w) > 4 else w


def _fact_key(text: str, at: int, end: Optional[int] = None) -> Optional[str]:
    """The noun a figure at ``at`` restates: a noun the figure names after it (``end``, past its unit: :data:`_FACT_AFTER_RE`), else the
    content word right before it, past function words ('drains a catchment of 24 km²' -> 'catchment', 'peak discharge 5.4' ->
    'discharge'); None after a punctuation mark, a figure or a frame word ('rose by', 'from')."""
    if end is not None:
        after = _FACT_AFTER_RE.match(text, end)
        if after is not None:
            if after.group("dim"):
                return _FACT_DIMENSIONS[" ".join(after.group("dim").lower().split())]
            w = after.group("of").lower()
            if w not in _FACT_SKIP and w not in _FACT_FRAME:
                return _fact_noun(w)
    toks = _FACT_WORD_RE.findall(text[max(0, at - 80):at])
    skip_to = None
    for k in range(len(toks) - 1, -1, -1):
        if skip_to is not None and k >= skip_to:
            continue
        t = toks[k]
        w = t.lower().strip("'’-")
        if not w or not w[0].isalpha():
            return None
        if w in _FACT_SKIP:
            continue
        # a time qualifier between the noun and its figure ('base flow before the storm 1.2 m³ s⁻¹'): the noun is the word before it
        # (c3f left, ge-p9c: the request's base flows were keyed 'storm', so a wrong restated base flow was never compared)
        q = k - 1 - (1 if k >= 1 and toks[k - 1].lower() in ("the", "a", "an", "each", "every") else 0)
        if q >= 1 and toks[q].lower() in ("before", "after", "during") and toks[q - 1][:1].isalpha():
            skip_to = q
            continue
        if w in _FACT_FRAME or w == "s":
            return None  # (c3e: the 's of a possessive, "Storm 1's 36 mm", is no noun; the labelled possessive is read by the caller)
        return _fact_noun(w)
    return None


def _labels_at(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(0)) for m in _FACT_LABEL_RE.finditer(text)]


def _label_before(labels: list[tuple[int, str]], at: int, lo: int) -> Optional[str]:
    """The last label at or after ``lo`` and before ``at`` (``labels`` in text order), by bisection: a scan of every label per figure was
    quadratic on one long sentence of labels and figures."""
    import bisect
    k = bisect.bisect_left(labels, (at, "")) - 1
    return labels[k][1] if k >= 0 and labels[k][0] >= lo else None


def _request_facts(request_text: str) -> tuple[dict, dict]:
    """The request's stated facts: ``{(label, noun, unit): [(value, half, shown)]}`` and its dates ``{label: (date, shown)}`` (a label
    reaches to the end of its sentence: "Storm 1, on 14 October 2006: 38 mm of rain, ...; peak discharge 5.4 m³ s⁻¹ at 21:30.")."""
    from .grounded_figures import _half
    facts: dict = {}
    dates: dict = {}
    text = request_text[:20_000]
    labels = _labels_at(text)
    starts = [0] + [m.end() for m in re.finditer(r"[.!?]\s", text)]
    import bisect
    for m in _FACT_FIG_RE.finditer(text):
        lo = starts[bisect.bisect_right(starts, m.start()) - 1]
        key = _fact_key(text, m.start(), m.end())
        unit = _FACT_UNITS.get(" ".join(m.group("u").lower().split()))
        if key is None or unit is None or len(facts) >= 256:
            continue
        lab = _label_before(labels, m.start(), lo)
        facts.setdefault((lab, key, unit), []).append((Fraction(m.group("n").replace(",", "")), _half(m.group("n").replace(",", "")), m.group(0)))
    for m in _DATE_RE.finditer(text):
        lo = starts[bisect.bisect_right(starts, m.start()) - 1]
        lab = _label_before(labels, m.start(), lo)
        if lab is not None and lab not in dates:
            dates[lab] = (_date_value(m), m.group(0))
    return facts, dates


def _date_value(m: "re.Match[str]") -> tuple[int, int, int]:
    months = _MONTHS.split("|")
    if m.group("d"):
        return int(m.group("y")), months.index(m.group("mo")) + 1, int(m.group("d"))
    return int(m.group("y2")), months.index(m.group("mo2")) + 1, int(m.group("d2"))


_POSS_LABEL_BEFORE_RE = re.compile(r"\b(?P<l>(?:Storm|Site|Station|Zone|Area|Sample|Quadrat|Transect|Point|Plot|Event|Well|Borehole|Village|Town|Ward|District|"
                                   r"Region)\s\d{1,3})['’]s\s*+$")


_SPREAD_OVER_RE = re.compile(r"\s++(?:of\s++(?:rain(?:fall)?|water|precipitation|runoff)\s++)?(?:over|across|on|onto)\s++(?:(?:a|an|the|its|whole|entire)\s++){0,2}"
                             r"(?:[a-z]{3,15}\s++){0,2}?(?:of\s++)?(?<![\d.,])(?:" + _NUM + r")\s*+" + _AREA_U + r"(?![^.;]{0,40}?\b(?:more|less|fewer|higher|lower|"
                             r"greater|smaller|larger|than|above|below)\b)", re.IGNORECASE)


#: A comparison between a figure and a label after it; a group or a total of the labelled events.
_REQ_CMP_BETWEEN_RE = re.compile(r"\b(?:times|than|compared\s+(?:with|to)|against|versus|vs\.?|relative\s+to|as\s+much\s+as|more|less|higher|lower|"
                                 r"greater|smaller|larger)\b", re.IGNORECASE)
_REQ_GROUP_RE = re.compile(r"\b(?:together|combined|altogether|in\s+total|in\s+all|between\s+them|both|the\s+two|all\s+(?:the\s+)?[a-z]{3,15}s|"
                           r"total|sum)\b", re.IGNORECASE)


#: The request-fact units of an area (as ``_FACT_UNITS`` names them).
_FACT_AREA_UNITS = frozenset(("km2", "m2", "ha", "hectares"))
_REQ_SUBJECT_RE = re.compile(r"\b(?:the|a|an)\s+(?P<n>[A-Za-z]{3,30})\b(?:\s+(?:at|in|near|on)\s+(?:(?!\b(?:the|a|an)\b)[^,.;:]){0,40}?)?\s+"
                             r"(?:was|is|were|are|measured|measures|had|has)\b", re.IGNORECASE)
_SUBJECT_HEAD_RE = re.compile(r"^\W*(?:the|a|an|this|its|their)\s+(?P<n>[A-Za-z]{3,30})\s+(?:is|was|are|were|has|had|measures|measured)\b",
                              re.IGNORECASE)


def _not_the_requests_object(ctx: _Ctx, text: str, m: "re.Match[str]", key: str, unit: Optional[str], facts: dict) -> bool:
    """Check round 12 of c3f (ge-p9c, false counterexamples on correct figures): a figure that measures another thing than the request's
    figure of its noun is no restatement of it: an area of a part of the noun's area ('about 1.9 km² of the catchment', or the same
    sentence also writing the request's own '24 km² catchment'), and a dimension of an object the request never names ('The bridge is 12
    m long and 3 m wide')."""
    from .grounded_figures import _half
    if unit in _FACT_AREA_UNITS and re.match(r"\s*of\s+(?:the|this|its|their)\s", text[m.end():m.end() + 12], re.IGNORECASE):
        return True  # (an area 'of the catchment': a part of it)
    cands = [c for (l2, k2, u2), xs in facts.items() if k2 == key and u2 == unit for c, _ch, _s in xs]
    v = Fraction(m.group("n").replace(",", ""))
    if cands and all(v != c for c in cands):
        for m2 in _FACT_FIG_RE.finditer(text):
            if m2.start() == m.start() or _FACT_UNITS.get(" ".join(m2.group("u").lower().split())) != unit:
                continue
            v2 = Fraction(m2.group("n").replace(",", ""))
            if any(abs(v2 - c) <= _half(m2.group("n").replace(",", "")) for c in cands):
                return True  # (the request's own figure of that noun written in the sentence too: this one measures something else)
    if key in _FACT_DIMENSIONS.values() and ctx.request_text:
        sh = _SUBJECT_HEAD_RE.match(text)
        if sh is not None and sh.end() <= m.start():
            noun = sh.group("n").lower().rstrip("s")
            # (the words the request writes before each of its figures of that dimension: the object it measures)
            near = set()
            for r in _FACT_FIG_RE.finditer(ctx.request_text):
                if _fact_key(ctx.request_text, r.start(), r.end()) == key:
                    # (the subject of the request's clause that states the dimension: "the channel at Marsh Lane Bridge was 6.0 m")
                    subj = list(_REQ_SUBJECT_RE.finditer(ctx.request_text, max(0, r.start() - 120), r.start()))
                    if subj:
                        near.add(subj[-1].group("n").lower().rstrip("s"))
            if near and noun not in near:
                return True  # (a dimension of another object than the one the request measures: "The bridge is 12 m long")
    return False


#: A change of a request's figure from its first label's value to its second's, the unit written after the second ("Base flow fell
#: from 1.2 to 1.0 m³ s⁻¹ between the two storms"; check round 13 of c3g).
_REQ_FROM_TO_RE = re.compile(r"\b(?P<verb>fell|rose|dropped|increased|decreased|declined|went|changed|grew|shrank|climbed|was|were)\s++"
                             r"(?:\w+\s+){0,2}?from\s++(?P<a>" + _NUM + r")\s++to\s++(?P<b>" + _NUM + r")\s*+"
                             r"(?P<u>km²|km2|m³\s?s⁻¹|m3\s?s-1|m³/s|m3/s|cumecs|m²|m2|hectares|ha|mm|cm|km|m|°C|PJ|GJ|MJ|tonnes|kg)(?![\w²³⁻/])",
                             re.IGNORECASE)


def _request_from_to(ctx: _Ctx, s: _Sentence, facts: dict) -> None:
    """A from-to pair of a request's figure across its two labels ("Base flow fell from 1.2 to 1.0 m³ s⁻¹ between the two storms"):
    when the first figure is the first label's value, the second is read against the second label's (a misread second figure is named,
    never left with only its direction checked). A pair in any other order is not read."""
    from .grounded_figures import _half
    for m in _REQ_FROM_TO_RE.finditer(s.text):
        unit = _FACT_UNITS.get(" ".join(m.group("u").lower().split()))
        key = _fact_key(s.text, m.start("verb"))
        if unit is None or key is None:
            continue
        per: dict = {}
        for (l2, k2, u2), xs in facts.items():
            if k2 == key and u2 == unit and l2 is not None:
                per.setdefault(l2, []).extend(xs)
        if len(per) != 2 or any(len(xs) != 1 for xs in per.values()):
            continue
        order = sorted(per, key=lambda lab: (re.sub(r"\d", "", lab), int(re.search(r"\d+", lab).group(0)) if re.search(r"\d+", lab) else 0))
        (c1, h1, sh1), (c2, h2, sh2) = per[order[0]][0], per[order[1]][0]
        a, b = Fraction(m.group("a").replace(",", "")), Fraction(m.group("b").replace(",", ""))
        ha, hb = _half(m.group("a").replace(",", "")), _half(m.group("b").replace(",", ""))
        if abs(a - c1) > max(ha, h1) or abs(b - c2) <= max(hb, h2) or not ctx.room("geo_request_figure"):
            continue
        lab2 = order[1]
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_request_figure", lambda cid, b=b, m=m, c2=c2, tol=max(hb, h2), sh2=sh2, key=key, lab2=lab2: make_check(
            ctx.report, check_id=cid, kind="geo_request_figure", inputs=[("stated", b, f"the figure restated ({m.group('b')} {m.group('u')})")],
            conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(c2)}), "right": _real(tol)},
            label=f"the {key} of {lab2} restated as {m.group('b')} {m.group('u')} against the request's {sh2}",
            description=f"{_excerpt(s.text)} [a change from the first label's figure to the second's restates the second label's figure]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="warning", defect="source_mismatch"))


def _request_figures(ctx: _Ctx, s: _Sentence, facts: dict, dates: dict) -> None:
    """A figure of the request restated in the answer (attack round 8, ge-p9c): 'drains a catchment of 42 km²' against the request's
    'drains a catchment of 24 km²', 'Storm 1 fell on 21 October 2006' against 'Storm 1, on 14 October 2006'. A figure is compared only
    with the request's figures of the same noun (the content word right before it) and unit, and of the same label when both name one;
    a figure after a change or comparison word is derived, never compared. The restated figure must be one of them (half a unit)."""
    from .grounded_figures import _half
    _request_from_to(ctx, s, facts)
    labels = _labels_at(s.text)
    distinct = {lab for _p, lab in labels}
    grouped = _REQ_GROUP_RE.search(s.text) is not None  # (read once per sentence)
    for m in _FACT_FIG_RE.finditer(s.text):
        key = _fact_key(s.text, m.start(), m.end())
        unit = _FACT_UNITS.get(" ".join(m.group("u").lower().split()))
        if key is None and unit is not None:
            # c3e: a figure right after a labelled possessive ("Storm 1's 36 mm over 24 km²") is that label's one figure of its unit
            pm = _POSS_LABEL_BEFORE_RE.search(s.text, max(0, m.start() - 40), m.start())
            keys = {k2 for (l2, k2, u2) in facts if pm and l2 == pm.group("l") and u2 == unit}
            key = keys.pop() if len(keys) == 1 else None
        if key is None or unit is None or (_FACT_DERIVED_AFTER_RE.match(s.text, m.end()) and not _SPREAD_OVER_RE.match(s.text, m.end())):
            continue  # ("15.1 m³ s⁻¹ above its base flow (16.2 − 1.1)": a figure worked out from others, never one restated; c3e: a depth
            # 'over' an area is spread on it, "36 mm over 24 km²", never a comparison)
        if _not_the_requests_object(ctx, s.text, m, key, unit, facts):
            continue
        lab = _label_before(labels, m.start(), 0)
        if lab is None and len(distinct) == 1:
            # the sentence's one label, unless it stands after the figure on the other side of a comparison ("The calculated discharge of
            # 16.2 m³ s⁻¹ is three times Storm 1's peak": the figure is not Storm 1's; c3e left)
            at = labels[0][0]
            if not (m.end() < at <= m.end() + 160 and _REQ_CMP_BETWEEN_RE.search(s.text, m.end(), at)):
                lab = next(iter(distinct))
        if lab is None and grouped:
            # a figure of a group or a total ("Together the two storms delivered 74 mm of rain"): no one label's figure, but the sum of
            # the labels' figures of its noun and unit when each label has one (c3e left: the sums of the request's figures)
            per = {}
            for (l2, k2, u2), xs in facts.items():
                if k2 == key and u2 == unit and l2 is not None:
                    per.setdefault(l2, []).extend(xs)
            if len(per) < 2 or any(len(xs) != 1 for xs in per.values()) or not ctx.room("geo_request_figure"):
                continue
            total = sum((xs[0][0] for xs in per.values()), Fraction(0))
            tol = max(_half(m.group("n").replace(",", "")), sum((xs[0][1] for xs in per.values()), Fraction(0)))
            v = Fraction(m.group("n").replace(",", ""))
            shown = " + ".join(f"{xs[0][2]} ({l2})" for l2, xs in sorted(per.items()))
            ctx.decided.add(" ".join(s.text.split()))
            ctx.add("geo_request_figure", lambda cid, v=v, m=m, total=total, tol=tol, shown=shown, key=key: make_check(
                ctx.report, check_id=cid, kind="geo_request_figure", inputs=[("stated", v, f"the total stated ({m.group(0)})")],
                conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(total)}), "right": _real(tol)},
                label=f"the {key} of all the request's labels together stated as {m.group(0)} against {shown} = {_fmt(total)}",
                description=f"{_excerpt(s.text)} [a total of the request's labelled figures is their sum (half a unit of each)]",
                claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="warning", defect="source_mismatch"))
            continue
        cands = facts.get((lab, key, unit)) if lab else None
        if not cands:
            cands = [x for (l2, k2, u2), xs in facts.items() if k2 == key and u2 == unit and (lab is None or l2 is None) for x in xs]
        if not cands or not ctx.room("geo_request_figure"):
            continue
        v = Fraction(m.group("n").replace(",", ""))
        h = _half(m.group("n").replace(",", ""))
        if any(abs(v - c) <= max(h, ch) for c, ch, _shown in cands):
            continue
        shown = ", ".join(dict.fromkeys(c[2] for c in cands))
        ctx.decided.add(" ".join(s.text.split()))
        options = [{"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(c)}), "right": _real(max(h, ch))} for c, ch, _s in cands]
        ctx.add("geo_request_figure", lambda cid, v=v, m=m, options=options, shown=shown, key=key, lab=lab: make_check(
            ctx.report, check_id=cid, kind="geo_request_figure", inputs=[("stated", v, f"the figure restated ({m.group(0)})")],
            conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
            label=f"the {key}{' of ' + lab if lab else ''} restated as {m.group(0)} against the request's {shown}",
            description=f"{_excerpt(s.text)} [a figure the request gives, restated, is the request's figure of the same noun and unit (half a unit)]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="warning", defect="source_mismatch"))
    for m in _DATE_RE.finditer(s.text):
        lab = _label_before(labels, m.start(), 0) or (next(iter(distinct)) if len(distinct) == 1 else None)
        if lab is None or lab not in dates or not ctx.room("geo_request_figure"):
            continue
        want, shown = dates[lab]
        got = _date_value(m)
        if got == want:
            continue
        ctx.decided.add(" ".join(s.text.split()))
        ordinal = lambda d: d[0] * 10_000 + d[1] * 100 + d[2]  # noqa: E731
        ctx.add("geo_request_figure", lambda cid, m=m, got=got, want=want, shown=shown, lab=lab: make_check(
            ctx.report, check_id=cid, kind="geo_request_figure", inputs=[("stated", Fraction(ordinal(got)), f"the date of {lab} restated ({m.group(0)}, as YYYYMMDD)")],
            conclusion={"op": "eq", "left": _var("stated"), "right": _real(Fraction(ordinal(want)))},
            label=f"the date of {lab} restated as {m.group(0)} against the request's {shown}",
            description=f"{_excerpt(s.text)} [a date the request gives for a labelled event, restated, is the request's date]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="warning", defect="source_mismatch"))


#: "Storm 2's peak discharge was two and a half times that of Storm 1": a multiple of two labelled figures the request (or the answer)
#: states (attack round 8); the possessive alone too ("three times Storm 1's", c3e left).
_LABEL_FOLD_RE = re.compile(r"\b(?P<l1>(?:Storm|Site|Station|Zone|Area|Sample|Point|Plot|Well|Village|Town)\s\d{1,3})['’]s\s++(?P<noun>(?:[a-z]{2,20}\s++){0,2}[a-z]{2,20})\s++"
                            r"(?:was|is|were|are)\s++(?P<ap>(?:about|around|roughly|nearly|almost|approximately)\s++)?" + _FOLD_K + r"\s++(?:(?:that\s++of|as\s++[a-z]{2,20}\s++as)\s++)?"
                            r"(?:the\s+[a-z]{2,20}\s+of\s+)?(?P<l2>(?:Storm|Site|Station|Zone|Area|Sample|Point|Plot|Well|Village|Town)\s\d{1,3})(?:['’]s)?\b")


def _labelled_fold(ctx: _Ctx, s: _Sentence, facts: dict, answer_facts: dict) -> None:
    for m in _LABEL_FOLD_RE.finditer(s.text):
        k, ktol = _fold_value(m.group("k"))
        if k is None:
            continue
        noun = _fact_noun(m.group("noun").split()[-1])
        def value(lab: str):
            for src in (facts, answer_facts):
                vals = {x[0] for (l2, k2, _u), xs in src.items() if l2 == lab and k2 == noun for x in xs}
                if len(vals) == 1:
                    return vals.pop()
            return None
        a, b = value(m.group("l1")), value(m.group("l2"))
        if a is None or b is None or b == 0 or not ctx.room("geo_pair_comparison"):
            continue
        if m.group("ap"):
            ktol = max(ktol, k / 10)
        ratio = a / b
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_pair_comparison", lambda cid, k=k, ktol=ktol, ratio=ratio, m=m, a=a, b=b: make_check(
            ctx.report, check_id=cid, kind="geo_pair_comparison", inputs=[("stated", k, f"the multiple stated ({m.group('k')})")],
            conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(ratio)}), "right": _real(ktol)},
            label=f"{m.group('l1')}'s {m.group('noun')} ({_fmt(a)}) is {m.group('k')} that of {m.group('l2')} ({_fmt(b)})",
            description=f"{_excerpt(s.text)} [a multiple of two labelled figures stated in the request or the answer equals their ratio]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


_LABEL_WORD = r"(?:Storm|Site|Station|Zone|Area|Sample|Point|Plot|Well|Village|Town|Quadrat|Transect|Event|Borehole|Ward|District|Region)\s\d{1,3}"
_REL_LESS = frozenset(("less", "lower", "fewer", "smaller", "shorter", "shallower", "narrower", "slower", "drier", "cooler", "colder"))
#: "Storm 2 had about 10% less rain than Storm 1", "Site 4's EQS was 25% lower than Site 1's": a relative difference of two labelled
#: figures the request (or the answer) states, with no bracketed pair (c3d, ge-p9c).
_LABEL_REL_RE = re.compile(r"(?:\b(?:the\s++)?(?P<n0>(?:[a-z]{2,20}\s++){0,1}[a-z]{2,20})\s++(?:of|in|at|for)\s++)?"
                           r"\b(?P<l1>" + _LABEL_WORD + r")(?:['’]s\s++(?P<n1>(?:[a-z]{2,20}\s++){0,2}[a-z]{2,20}))?\s++(?:had|has|received|got|saw|recorded|"
                           r"produced|was|were|is|are)\s++(?:(?:about|around|roughly|nearly|almost|approximately|some|over|under|more\s+than|less\s+than|at\s+least)\s++)?"
                           + _num_re("n", scale=False) + r"\s*+(?:(?P<pct>%|per\s*+cent\b|percent\b)|(?P<u>mm|cm|km|m|m³\s?s⁻¹|m3\s?s-1|m³/s|m3/s|cumecs|°C)"
                           r"(?![\w²³⁻/])(?:\s++of\s++(?P<n3>[a-z]{2,20}))?)\s++(?P<cmp>" + _CMP_WORD
                           + r")\b\s*+(?P<n2>(?:[a-z]{2,20}\s++){0,2}?)than\s++(?:(?:that|those)\s++of\s++|in\s++|at\s++|for\s++)?(?P<l2>" + _LABEL_WORD + r")\b",
                           re.IGNORECASE)
_REL_NOUN_SKIP = frozenset(("that", "those", "this", "these", "it", "one"))


def _labelled_relative(ctx: _Ctx, s: _Sentence, facts: dict, answer_facts: dict) -> None:
    """c3d (ge-p9c): a relative difference of two labelled figures the request or the answer states ("Storm 2 had about 10% less rain than
    Storm 1" against 36 mm and 38 mm of rain): |A − B| over either figure × 100, in the direction the comparative word states (a 'less'
    of a larger figure fails); figures of the same noun (after the comparative word or after the possessive) only.
    c3e: the noun may stand before the label ("The rainfall of Storm 2 was ...") or after an amount ("2 mm of rain more"), the noun under
    the one name of its quantity ('rainfall' is the request's 'rain'), and the difference may be an amount in a unit ("2 mm higher than
    that of Storm 1": A − B in the stated direction, against the figures of that unit only)."""
    for m in _LABEL_REL_RE.finditer(s.text):
        words = [w for w in ((m.group("n2") or "").split() or (m.group("n3") or "").split() or (m.group("n1") or "").split()
                             or (m.group("n0") or "").split()) if w.lower() not in _REL_NOUN_SKIP]
        if not words:
            continue
        noun = _fact_noun(words[-1])
        unit = _FACT_UNITS.get(" ".join(m.group("u").lower().split())) if m.group("u") else None
        if m.group("u") and unit is None:
            continue

        def value(lab: str):
            for src in (facts, answer_facts):
                vals = {x[0] for (l2, k2, u2), xs in src.items() if l2 == lab and k2 == noun and (unit is None or u2 == unit) for x in xs}
                if len(vals) == 1:
                    return vals.pop()
            return None
        a, b = value(m.group("l1")), value(m.group("l2"))
        if a is None or b is None or a == 0 or b == 0 or not ctx.room("geo_pair_comparison"):
            continue
        d = (b - a) if m.group("cmp").lower() in _REL_LESS else (a - b)
        stated = _fig(m, "n", s.text)
        if unit is None:
            options = [_stated_band(d / base * 100, stated) for base in dict.fromkeys((b, a))]
            what, shown = "relative difference", f"{stated.shown}%"
        else:
            options = [_stated_band(d, stated)]
            what, shown = "difference", f"{stated.shown} {m.group('u')}"
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_pair_comparison", lambda cid, stated=stated, options=options, m=m, a=a, b=b, noun=noun, what=what, shown=shown: make_check(
            ctx.report, check_id=cid, kind="geo_pair_comparison", inputs=[("stated", stated.value, f"the {what} stated ({shown})")],
            conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
            label=f"{m.group('l1')} ({_fmt(a)}) {shown} {m.group('cmp')} {noun} than {m.group('l2')} ({_fmt(b)})",
            description=(f"{_excerpt(s.text)} [a {what} of two labelled figures of the request or the answer: the difference in the "
                         f"stated direction{' over either figure × 100' if what == 'relative difference' else ''}; {_RULE.format(tau=1)}]"),
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


_CLOCK_RE = re.compile(r"(?<![\d:.,])(?P<h>[01]?\d|2[0-3]):(?P<mi>[0-5]\d)(?![\d:])")
_CLOCK_STOP = frozenset("the with at of a an and on in its their time times peak was were is are before after then from to by for".split())
_DUR_RE = re.compile(r"(?<![\d.,])(?:(?P<h>\d{1,3}(?:\.\d{1,2})?)\s*+(?:hours?|hrs?|h)\b(?:\s*+(?:and\s++)?(?P<hm>\d{1,2})\s*+(?:minutes?|mins?|min)\b)?|"
                     r"(?P<m>\d{1,4})\s*+(?:minutes?|mins?|min)\b|"
                     # c3e: an interval in words ("a lag of ten hours", "four and a half hours")
                     r"\b(?P<hw>" + _WORD_NUMBER + r")(?P<hh>\s++and\s++a\s++half)?(?:-|\s++)hours?\b)", re.IGNORECASE)
_DUR_AFTER_RE = re.compile(r"\s++(?P<dir>after|before|later\s+than|earlier\s+than)\s++(?P<obj>[^.;:,()]{3,80})", re.IGNORECASE)
_LAG_RE = re.compile(r"\blag(?:\s+times?)?\b", re.IGNORECASE)
_FOR_LABEL_RE = re.compile(r"\s++(?:for|in|of)\s++(?P<l>" + _LABEL_WORD + r")\b")
_FLOW_WORDS = ("discharge", "flow", "flood", "river", "runoff")
_RAIN_WORDS = ("rain", "rainfall", "precipitation", "storm")


def _clock_words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'’-]{2,30}", text) if w.lower() not in _CLOCK_STOP}


def _request_clocks(request_text: str) -> dict:
    """The request's clock times by label: ``{label: [(minutes since midnight, shown, words of the clause that names the event)]}``
    ("Storm 2, ...: 36 mm of rain, with the peak rainfall intensity at 09:30; ...; peak discharge 16.2 m³ s⁻¹ at 14:00.")."""
    import bisect
    text = request_text[:20_000]
    labels = _labels_at(text)
    starts = [0] + [m.end() for m in re.finditer(r"[.!?]\s", text)]
    out: dict = {}
    for m in _CLOCK_RE.finditer(text):
        lo = starts[bisect.bisect_right(starts, m.start()) - 1]
        lab = _label_before(labels, m.start(), lo)
        if lab is None:
            continue
        cut = max(text.rfind(";", lo, m.start()), text.rfind(",", lo, m.start()), text.rfind(":", lo, m.start() - 1), text.rfind("(", lo, m.start()), lo - 1) + 1
        words = _clock_words(_FACT_FIG_RE.sub(" ", text[cut:m.start()])) - {w.lower() for w in lab.split()}
        if words and sum(len(v) for v in out.values()) < 64:
            out.setdefault(lab, []).append((int(m.group("h")) * 60 + int(m.group("mi")), m.group(0), frozenset(words)))
    return out


def _duration(m: "re.Match[str]") -> tuple[Fraction, Fraction]:
    """(minutes, half a unit of the duration's last written figure, in minutes)."""
    from .grounded_figures import _half
    if m.group("m"):
        return Fraction(int(m.group("m"))), Fraction(1, 2)
    if m.group("hw"):
        # (a whole number of hours in words is precise to the hour, "and a half" to the half hour: half a unit is 30 or 15 minutes,
        # as for "12 hours" and "12.5 hours"; check round 11 of c3e, where "twelve and a half hours" took the whole hour's band)
        return (_WORD_NUMBERS[m.group("hw").lower()] + (Fraction(1, 2) if m.group("hh") else 0)) * 60, \
            Fraction(15) if m.group("hh") else Fraction(30)
    h = Fraction(m.group("h"))
    if m.group("hm"):
        return h * 60 + int(m.group("hm")), Fraction(1, 2)
    return h * 60, _half(m.group("h")) * 60


def _matches(words: frozenset, mine: set) -> bool:
    return any(w[:4] == x[:4] for w in words if len(w) >= 4 for x in mine if len(x) >= 4)


def _clock_interval(ctx: _Ctx, s: _Sentence, clocks: dict) -> None:
    """c3d (ge-p9c): a time interval between two events whose clock times the request gives for one label ("Storm 2's discharge peaked
    5 hours 30 minutes after its rainfall peak" against the request's 09:30 and 14:00; "the lag time ... 4.5 hours for Storm 2"): the
    events are the request's clauses that share a content word with the words before the interval and after 'after' (a lag: the
    discharge after the rainfall); the interval equals their difference (half a unit of its last figure; 5% after 'about')."""
    if not clocks:
        return
    labels = _labels_at(s.text)
    for d in _DUR_RE.finditer(s.text):
        after = _DUR_AFTER_RE.match(s.text, d.end())
        lag = _LAG_RE.search(s.text, max(0, d.start() - 60), d.start())
        if after is None and lag is None:
            continue
        if not ctx.room("geo_clock_interval"):
            ctx.skip("geo_clock_interval")
            return
        clause_lo = max(s.text.rfind(";", 0, d.start()), s.text.rfind(".", 0, max(0, d.start() - 1)), 0)
        f = _FOR_LABEL_RE.match(s.text, d.end())  # "12 hours for Storm 1 and 4.5 hours for Storm 2": the label right after it first
        lab = f.group("l") if f else _label_before(labels, d.start(), clause_lo)
        if lab is None or lab not in clocks:
            continue
        events = clocks[lab]
        if after is not None:
            subj = _clock_words(s.text[max(clause_lo, d.start() - 200):d.start()]) - {w.lower() for w in lab.split()}  # a bounded window
            obj = _clock_words(after.group("obj"))
            first = [e for e in events if _matches(e[2], subj)]
            second = [e for e in events if _matches(e[2], obj)]
            if not first and len(second) == 1 and len(events) == 2:
                # c3e: the label itself is the subject ("Storm 2 peaked 5.5 h after its rainfall peak"): the label's other event
                first = [e for e in events if e is not second[0]]
            sign = 1 if after.group("dir").lower().startswith(("after", "later")) else -1
        else:
            first = [e for e in events if any(w.startswith(_FLOW_WORDS) for w in e[2])]
            second = [e for e in events if any(w.startswith(_RAIN_WORDS) for w in e[2])]
            sign = 1
        if len(first) != 1 or len(second) != 1 or first[0] is second[0] or not ctx.room("geo_clock_interval"):
            continue
        value = Fraction(sign * (first[0][0] - second[0][0]))
        stated, half = _duration(d)
        approx = bool(_APPROX_RE.search(s.text[max(0, d.start() - 20):d.start()]))
        # (half a unit, the tie excluded: a whole hour never covers a true half hour from both sides, so "four hours" and "five hours"
        # are no reading of a true 4.5 hours; check round 11 of c3e)
        tol = max(half - Fraction(1, 60), value / 20 if approx else Fraction(0))
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_clock_interval", lambda cid, value=value, stated=stated, tol=tol, d=d, lab=lab, a=first[0], b=second[0]: make_check(
            ctx.report, check_id=cid, kind="geo_clock_interval", inputs=[("stated", stated, f"the interval stated ({d.group(0)}, in minutes)")],
            conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(value)}), "right": _real(tol)},
            label=f"{d.group(0)} for {lab} against the request's {a[1]} and {b[1]} ({_fmt(value)} minutes)",
            description=(f"{_excerpt(s.text)} [an interval between two events of a label whose clock times the request gives equals their difference "
                         f"(half a unit of its last figure; 5% after 'about')]"),
            claim_ids=_claims(ctx.report, s.text, d.group(0)), defect="stem_arithmetic_slip"))


#: A peak a labelled event reached at a clock time ("Storm 1 peaked at 22:30", "In Storm 1 the river peaked at 20:30", "Storm 2
#: peaked at 15:00, 4.5 hours after ..."), the time in the peak's own clause.
_PEAK_AT_RE = re.compile(r"\b(?:peak(?:ed|s|ing)?|maximum|highest)\b[^.;:,()]{0,40}?\bat\s++(?P<t>(?:[01]?\d|2[0-3]):[0-5]\d)(?![\d:])",
                         re.IGNORECASE)


def _clock_peak(ctx: _Ctx, s: _Sentence, clocks: dict) -> None:
    """Check round 12 of c3f (ge-p9c): a peak time of a label the request times ("Storm 1 peaked at 22:30" against the request's
    peak discharge at 21:30 and peak rainfall at 09:30): the time stated is one of the request's times of that label's events (the
    discharge's alone when the clause names the river or its flow, the rainfall's alone when it names the rain), half a minute either
    way. A time that is none of them is named; one that is any of them holds. A label the request gives no time for is not read."""
    if not clocks:
        return
    labels = _labels_at(s.text)
    worked = [(w, "t") for w in _CLOCK_WORK_RE.finditer(s.text)] + \
        [(w, "t2") for w in _CLOCK_WORK_RE.finditer(s.text)]
    for m, g in [(x, "t") for x in _PEAK_AT_RE.finditer(s.text)] + worked:
        clause_lo = max(s.text.rfind(";", 0, m.start()), s.text.rfind(".", 0, max(0, m.start() - 1)), 0)
        lab = _label_before(labels, m.start(), clause_lo)
        if lab is None or lab not in clocks or not ctx.room("geo_request_figure"):
            continue
        if m.re is _CLOCK_WORK_RE:
            words = set()  # (a worked difference of two times: each is one of the label's times)
        else:
            words = _clock_words(s.text[clause_lo:m.end()])
        flow = any(w.startswith(_FLOW_WORDS) for w in words)
        rain = any(w.startswith(_RAIN_WORDS) and not w.startswith("storm") for w in words)
        events = clocks[lab]
        if flow != rain:
            want = _FLOW_WORDS if flow else _RAIN_WORDS
            events = [e for e in events if any(w.startswith(want) and not w.startswith("storm") for w in e[2])] or events
        t = m.group(g)
        h, mi = t.split(":")
        stated = Fraction(int(h) * 60 + int(mi))
        if any(e[0] == stated for e in events):
            continue  # (a time the request gives for the label: nothing restated wrongly)
        shown = ", ".join(dict.fromkeys(e[1] for e in events))
        ctx.decided.add(" ".join(s.text.split()))
        options = [{"op": "eq", "left": _var("stated"), "right": _real(Fraction(e[0]))} for e in events]
        ctx.add("geo_request_figure", lambda cid, t=t, stated=stated, options=options, shown=shown, lab=lab: make_check(
            ctx.report, check_id=cid, kind="geo_request_figure", inputs=[("stated", stated, f"the time restated ({t}, in minutes)")],
            conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
            label=f"the time of {lab} restated as {t} against the request's {shown}",
            description=f"{_excerpt(s.text)} [a clock time the request gives for a labelled peak, restated, is one of the request's times of that label]",
            claim_ids=_claims(ctx.report, s.text, t), severity="warning", defect="source_mismatch"))


#: A worked difference of two clock times ("Storm 1: 21:30 − 09:30 = 12 hours").
_CLOCK_WORK_RE = re.compile(r"(?<![\d:.,])(?P<t>(?:[01]?\d|2[0-3]):[0-5]\d)\s*+[−–-]\s*+(?P<t2>(?:[01]?\d|2[0-3]):[0-5]\d)(?![\d:])")


#: A spacing of sampled sites, with the span it covers: "The sites are 150 m apart, from 0 m to 900 m." (c3d, ge-t14).
_SPACING_RE = re.compile(r"\b" + _SITES + r"\s++(?:are|were|lie|lay|sit|sat|stand|stood)\s++(?P<ap>(?:about|around|roughly|approximately)\s++)?(?<![\d.,])(?P<i>"
                         + _NUM + r")\s*+(?P<iu>m|metres|meters|km)\s++apart\b(?:\s*+,?\s*+from\s++(?P<a>" + _NUM + r")\s*+(?P<au>m|metres|meters|km)\s++"
                         r"to\s++(?P<b>" + _NUM + r")\s*+(?P<bu>m|metres|meters|km)\b)?", re.IGNORECASE)


def _table_spacing(ctx: _Ctx, s: _Sentence, tables: list[_AttrTable]) -> None:
    """c3d (ge-t14): the spacing of the sites a supplied table lists by distance ("The sites are 150 m apart, from 0 m to 900 m" against a
    distance column of 0, 100, ..., 900): the spacing is the column's common difference, and a span stated with it runs from the first
    distance to the last (units converted)."""
    for m in _SPACING_RE.finditer(s.text):
        for table in tables:
            if not table.row_noun.startswith(("site", "point", "station", "quadrat", "location")):
                continue
            cols = [k for k, (h, _st) in enumerate(table.columns) if re.search(r"\bdistance\b", h, re.IGNORECASE) and re.search(r"\((?:m|km)\)", h)]
            if len(cols) != 1:
                continue
            col = cols[0]
            unit = _LEN_M["km" if "(km)" in table.columns[col][0] else "m"]
            cells = _column_values(table)[col]
            if any(v is None for v in cells) or len(cells) < 2:
                continue
            vals = [v[0] for v in cells]
            steps = {vals[k + 1] - vals[k] for k in range(len(vals) - 1)}
            if len(steps) != 1 or not ctx.room("geo_table_spacing"):
                continue
            step = steps.pop() * unit
            stated = _num(m.group("i")) * _LEN_M[m.group("iu").lower()]
            tol = stated / 20 if m.group("ap") else Fraction(0)
            args = [{"op": "le", "left": _abs({"op": "sub", "left": _var("spacing"), "right": _real(step)}), "right": _real(tol)}]
            inputs = [("spacing", stated, f"the spacing stated ({m.group('i')} {m.group('iu')})")]
            if m.group("a"):
                inputs += [("first", _num(m.group("a")) * _LEN_M[m.group("au").lower()], f"the first distance stated ({m.group('a')} {m.group('au')})"),
                           ("last", _num(m.group("b")) * _LEN_M[m.group("bu").lower()], f"the last distance stated ({m.group('b')} {m.group('bu')})")]
                args += [{"op": "eq", "left": _var("first"), "right": _real(vals[0] * unit)}, {"op": "eq", "left": _var("last"), "right": _real(vals[-1] * unit)}]
            ctx.decided.add(" ".join(s.text.split()))
            ctx.add("geo_table_spacing", lambda cid, inputs=inputs, args=args, step=step, table=table, vals=vals, unit=unit: make_check(
                ctx.report, check_id=cid, kind="geo_table_spacing", inputs=inputs, conclusion=args[0] if len(args) == 1 else {"op": "and", "args": args},
                label=f"the sites' spacing against {table.document_id}'s distances ({_fmt(step)} m apart, {_fmt(vals[0] * unit)} m to {_fmt(vals[-1] * unit)} m)",
                description=f"{_excerpt(s.text)} [the spacing of the sites a supplied table lists is the common difference of its distance column, the span its first and last]",
                claim_ids=_claims(ctx.report, s.text, m.group(0)), severity="error" if _CREDIT_RE.search(s.text) or "your" in s.text.lower() else "warning",
                defect="source_mismatch"))
            break


@dataclass(frozen=True)
class _Event:
    """A dated event of the answer: the date of a sentence that states exactly one, the words only that sentence holds among the dated
    ones, and its figures by noun (the fact reader's key)."""
    date: tuple
    words: frozenset
    facts: tuple


def _answer_events(sentences: list[_Sentence]) -> list[_Event]:
    dated = []
    for s in sentences[:2000]:
        ds = list(_DATE_RE.finditer(s.text))
        if len(ds) != 1:
            continue
        words = _clock_words(_DATE_RE.sub(" ", s.text))
        facts = []
        for m in _FACT_FIG_RE.finditer(s.text):
            key = _fact_key(s.text, m.start(), m.end())
            if key:
                facts.append((key, _num(m.group("n")), m.group(0)))
        dated.append((_date_value(ds[0]), words, tuple(facts)))
        if len(dated) >= 64:
            break
    out = []
    for k, (date, words, facts) in enumerate(dated):
        others = set().union(*(w for j, (_d, w, _f) in enumerate(dated) if j != k)) if len(dated) > 1 else set()
        out.append(_Event(date, frozenset(words - others), facts))
    return out


def _event_named(events: list[_Event], phrase: str) -> Optional[_Event]:
    """The one dated event whose own words the phrase holds ('the Darfield earthquake' -> the sentence that alone says 'Darfield')."""
    mine = _clock_words(phrase)
    hits = [e for e in events if e.words & mine]
    return hits[0] if len(hits) == 1 else None


_DAY_UNITS = {"day": Fraction(1), "week": Fraction(7), "month": Fraction(1461, 48), "year": Fraction(1461, 4)}
_EVENT_INTERVAL_RE = re.compile(r"(?P<ap>\b(?:about|around|roughly|approximately|nearly|almost|some|just\s+over|just\s+under)\s++)?"
                                # c3e: an interval in words too ("a year and a half after", "five and a half months after", "half a year after")
                                r"(?:(?<![\d.,])(?P<n>\d{1,4}(?:\.\d{1,2})?)|\b(?P<w>" + _WORD_NUMBER + r"|an?)(?P<h1>\s++and\s++a\s++half)?|\b(?P<hf>half)\s++an?)"
                                r"\s++(?P<u>days?|weeks?|months?|years?)(?P<h2>\s++and\s++a\s++half)?\s++(?P<dir>after|before|later\s+than|earlier\s+than)\s++(?P<obj>[^.;:,()]{3,80})", re.IGNORECASE)
_EVENT_FOLD_RE = re.compile(r"(?P<ap>\b(?:about|around|roughly|nearly|almost|approximately)\s++)?\b" + _FOLD_K + r"\s++(?:of\s++)?the\s++(?P<noun>[a-z]{3,20})\s++of\s++"
                            r"(?P<obj>[^.;:,()]{3,80})", re.IGNORECASE)


def _event_relations(ctx: _Ctx, s: _Sentence, events: list[_Event]) -> None:
    """c3d (ge-t16): an interval or a multiple between two events the answer itself dates ("The aftershock struck about 17 months after the
    Darfield earthquake" against 4 September 2010 and 22 February 2011; "The aftershock was about 5 km deep, a third of the depth of the
    Darfield earthquake" against its 'about 10 km deep'). Each event is the one dated sentence that alone holds a word the phrase names:
    the subject before the interval or the fold, the object after 'after' or 'of'."""
    import datetime as _dt
    for m in _EVENT_INTERVAL_RE.finditer(s.text):
        a = _event_named(events, s.text[max(0, m.start() - 120):m.start()])
        b = _event_named(events, m.group("obj"))
        if a is None or b is None or a is b or not ctx.room("geo_event_relation"):
            continue
        try:
            days = Fraction((_dt.date(*a.date) - _dt.date(*b.date)).days)
        except ValueError:
            continue
        unit = m.group("u").lower().rstrip("s")
        value = days / _DAY_UNITS[unit] * (1 if m.group("dir").lower().startswith(("after", "later")) else -1)
        from .grounded_figures import _half
        if m.group("n"):
            stated = Fig(_num(m.group("n")), m.group("n"), max(_half(m.group("n")), Fraction(1, 2)), bool(m.group("ap")))
        else:
            half = bool(m.group("hf") or m.group("h1") or m.group("h2"))
            whole = Fraction(0) if m.group("hf") else Fraction(1 if m.group("w").lower() in ("a", "an") else _WORD_NUMBERS[m.group("w").lower()])
            stated = Fig(whole + (Fraction(1, 2) if half else 0), " ".join(m.group(0)[len(m.group("ap") or ""):m.start("dir") - m.start()].split()),
                         Fraction(1, 4) if half else Fraction(1, 2), bool(m.group("ap")))
        shown = m.group("n") or stated.shown
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_event_relation", lambda cid, value=value, stated=stated, m=m, a=a, b=b, shown=shown: make_check(
            ctx.report, check_id=cid, kind="geo_event_relation", inputs=[("stated", stated.value, f"the interval stated ({shown}{' ' + m.group('u') if m.group('n') else ''})")],
            conclusion=_stated_band(value, stated),
            label=f"{shown}{' ' + m.group('u') if m.group('n') else ''} {m.group('dir')} against the answer's dates {a.date} and {b.date} ({_fmt(value)} {m.group('u')})",
            description=f"{_excerpt(s.text)} [an interval between two events the answer dates equals the time between the dates; half a unit and 1% (5% after 'about')]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="contradiction"))
    for m in _EVENT_FOLD_RE.finditer(s.text):
        k, ktol = _fold_value(m.group("k"))
        b = _event_named(events, m.group("obj"))
        noun = m.group("noun").lower()
        mine = [(v, sh) for key, v, sh in (b.facts if b else ()) if key == noun]
        own = [(_num(f.group("n")), f.group(0)) for f in _FACT_FIG_RE.finditer(s.text, 0, m.start()) if _fact_key(s.text, f.start(), f.end()) == noun]
        if k is None or b is None or len({v for v, _ in mine}) != 1 or len(own) != 1 or mine[0][0] == 0 or not ctx.room("geo_event_relation"):
            continue
        if m.group("ap"):
            ktol = max(ktol, k / 10)
        ratio = own[0][0] / mine[0][0]
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_event_relation", lambda cid, k=k, ktol=ktol, ratio=ratio, m=m, own=own, mine=mine: make_check(
            ctx.report, check_id=cid, kind="geo_event_relation", inputs=[("stated", k, f"the multiple stated ({m.group('k')})")],
            conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(ratio)}), "right": _real(ktol)},
            label=f"{own[0][1]} is {m.group('k')} the {m.group('noun')} of the event the answer gives as {mine[0][1]} (ratio {_fmt(ratio)})",
            description=f"{_excerpt(s.text)} [a multiple of a figure the answer states for a dated event equals the ratio of the two figures]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="contradiction"))


#: c3e left (ge-t16): a magnitude or a clock time the answer states for one event, and a difference of two events' magnitudes.
_AM_PM_RE = re.compile(r"(?<![\d.:])(?P<h>1[0-2]|0?\d)[.:](?P<mi>[0-5]\d)\s*+(?P<ap>a\.?m\.?|p\.?m\.?)(?![\w])", re.IGNORECASE)
_MAG_DIFF_RE = re.compile(r"(?<![\d.,])(?P<n>\d(?:\.\d{1,2})?)\s++(?:magnitude\s+)?(?:units?|points?)\s++(?:of\s+magnitude\s+)?(?P<cmp>weaker|smaller|lower|less|"
                          r"stronger|larger|greater|higher|bigger|more)\b(?:\s+in\s+magnitude)?\s++than\s++(?P<obj>[^.;:,()]{3,80})", re.IGNORECASE)
_MAG_LESS = frozenset(("weaker", "smaller", "lower", "less"))


def _answer_quantities(sentences: list[_Sentence]) -> tuple[list, list]:
    """The answer's own magnitudes (and clock times), one per sentence that states exactly one: ``([(value, words, shown, sentence)], ...)``
    (at most 64 of each)."""
    mags, clocks = [], []
    for k, s in enumerate(sentences[:2000]):
        ms = list(_MAGNITUDE_RE.finditer(s.text))
        if len(ms) == 1 and not _MAG_DIFF_RE.search(s.text) and len(mags) < 64:
            v = ms[0].group("n") or ms[0].group("m")
            mags.append((Fraction(v), frozenset(_clock_words(_MAGNITUDE_RE.sub(" ", s.text))), ms[0].group(0), k))
        cs = list(_AM_PM_RE.finditer(s.text))
        if len(cs) == 1 and len(clocks) < 64:
            c = cs[0]
            h = int(c.group("h")) % 12 + (12 if c.group("ap").lower().startswith("p") else 0)
            clocks.append((h * 60 + int(c.group("mi")), frozenset(_clock_words(_AM_PM_RE.sub(" ", s.text))), c.group(0), k))
    return mags, clocks


def _named_quantity(items: list, phrase: str, here: int) -> Optional[tuple]:
    """The one item of another sentence than ``here`` whose sentence alone (among those others) holds a word the phrase names."""
    pool = [x for x in items if x[3] != here]
    if len(pool) < 2:
        return None  # (one other sentence: no word tells its event from the sentence's own)
    mine = _clock_words(phrase)
    hits = []
    for x in pool:
        others = set().union(*(y[1] for y in pool if y is not x)) if len(pool) > 1 else set()
        if (x[1] - others) & mine:
            hits.append(x)
    return hits[0] if len(hits) == 1 else None


def _answer_quantity_relations(ctx: _Ctx, s: _Sentence, here: int, mags: list, clocks: list) -> None:
    """c3e left (ge-t16): a difference of two events' magnitudes the answer states ("The Haiti earthquake was 0.1 magnitude units weaker
    than Darfield" against its own magnitude 7.0 and 7.1): each event is the one other sentence that alone holds a word the phrase names.
    (A clock time restated for an event is not read: which sentence times which event is not fixed by its words.)"""
    from .grounded_figures import _half
    for m in _MAG_DIFF_RE.finditer(s.text):
        a = _named_quantity(mags, s.text[max(0, m.start() - 120):m.start()], here)
        b = _named_quantity(mags, m.group("obj"), here)
        if a is None or b is None or a is b or not ctx.room("geo_event_relation"):
            continue
        diff = (b[0] - a[0]) if m.group("cmp").lower() in _MAG_LESS else (a[0] - b[0])
        n = Fraction(m.group("n"))
        tol = _half(m.group("n"))
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_event_relation", lambda cid, n=n, diff=diff, tol=tol, m=m, a=a, b=b: make_check(
            ctx.report, check_id=cid, kind="geo_event_relation", inputs=[("stated", n, f"the difference stated ({m.group('n')} {m.group('cmp')})")],
            conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(diff)}), "right": _real(tol)},
            label=f"{m.group('n')} magnitude units {m.group('cmp')} against the answer's {a[2]} and {b[2]} ({_fmt(diff)})",
            description=f"{_excerpt(s.text)} [a difference of two magnitudes the answer states is their difference, in the direction stated]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="contradiction"))


#: A part of a total the answer states: "It killed 185 people, more than 130 of them in the collapse of two buildings."
_PART_OF_TOTAL_RE = re.compile(r"(?<![\d.,])(?P<t>" + _NUM + r")\s++[a-z]{3,20}\b[^.;]{0,40}?,?\s*+(?P<q>more\s+than|over|at\s+least|about|around|nearly|almost|"
                               r"fewer\s+than|less\s+than|under)?\s*+(?<![\d.,])(?P<p>" + _NUM + r")\s++of\s++(?:them|these|those|whom)\s++(?P<where>in|at|inside|within|"
                               r"from|during|by)\b(?P<rest>[^.;]{3,80})", re.IGNORECASE)
#: The rest of that total, stated: "About 75 of the aftershock's 185 deaths happened outside the two collapsed buildings."
_COMPLEMENT_RE = re.compile(r"(?P<ap>\b(?:about|around|roughly|approximately|nearly|almost|some)\s++)?(?<![\d.,])(?P<a>" + _NUM + r")\s++of\s++(?:the\s++)?"
                            r"(?:[\w'’]+\s++){0,3}?(?<![\d.,])(?P<t>" + _NUM + r")\s++[a-z]{3,20}\b[^.;]{0,40}?\b(?:outside|beyond|away\s+from|elsewhere\s+than|"
                            r"other\s+than|not\s+in)\b(?P<rest>[^.;]{3,80})", re.IGNORECASE)


def _answer_parts(sentences: list[_Sentence]) -> list[tuple]:
    out = []
    for s in sentences[:2000]:
        for m in _PART_OF_TOTAL_RE.finditer(s.text):
            out.append((_num(m.group("t")), _num(m.group("p")), (m.group("q") or "").lower(), frozenset(_clock_words(m.group("rest"))), m.group(0)))
            if len(out) >= 64:
                return out
    return out


def _part_complement(ctx: _Ctx, s: _Sentence, parts: list[tuple]) -> None:
    """c3d (ge-t16): the rest of a total whose part the answer states elsewhere ("About 75 of the aftershock's 185 deaths happened outside
    the two collapsed buildings" against "It killed 185 people, more than 130 of them in the collapse of two buildings"): the rest is the
    total less the part, one-sided when the part is a bound (more than 130 in leaves fewer than 55 outside); the part is the one of the
    same total whose place shares a word stem with the place the sentence excludes."""
    for m in _COMPLEMENT_RE.finditer(s.text):
        t, a = _num(m.group("t")), _num(m.group("a"))
        mine = _clock_words(m.group("rest"))
        hits = [p for p in parts if p[0] == t and _matches(p[3], mine)]
        if len(hits) != 1 or not ctx.room("geo_event_relation"):
            continue
        _t, part, q, _w, shown = hits[0]
        rest = t - part
        from .grounded_figures import _half
        slack = _half(m.group("a").replace(",", "")) + (rest / 20 if m.group("ap") else 0)
        if q in ("more than", "over", "at least"):
            concl = {"op": "le", "left": _var("stated"), "right": _real(rest + slack)}
            rule = f"at most {_fmt(rest)}"
        elif q in ("fewer than", "less than", "under"):
            concl = {"op": "ge", "left": _var("stated"), "right": _real(rest - slack)}
            rule = f"at least {_fmt(rest)}"
        else:
            concl = {"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(rest)}), "right": _real(slack + (rest / 20 if q else 0))}
            rule = f"about {_fmt(rest)}"
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_event_relation", lambda cid, a=a, concl=concl, rule=rule, m=m, shown=shown: make_check(
            ctx.report, check_id=cid, kind="geo_event_relation", inputs=[("stated", a, f"the rest stated ({m.group('a')} of {m.group('t')})")],
            conclusion=concl, label=f"{m.group('a')} of {m.group('t')} outside the part the answer states ('{_excerpt(shown, 80)}'): {rule}",
            description=f"{_excerpt(s.text)} [the rest of a total is the total less the part the answer states of it (one-sided when the part is a bound)]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="contradiction"))


def _answer_facts(sentences: list[_Sentence]) -> dict:
    """The answer's own labelled facts, read as the request's are (for a multiple whose figures the request does not give)."""
    out: dict = {}
    for s in sentences:
        labels = _labels_at(s.text)
        for m in _FACT_FIG_RE.finditer(s.text):
            key = _fact_key(s.text, m.start(), m.end())
            unit = _FACT_UNITS.get(" ".join(m.group("u").lower().split()))
            lab = _label_before(labels, m.start(), 0)
            if key and unit and lab and len(out) < 256:
                out.setdefault((lab, key, unit), []).append((Fraction(m.group("n").replace(",", "")), Fraction(0), m.group(0)))
    return out


#: A unit conversion stated outright: "12 hours is 720 minutes", "4.5 km = 4,500 m", "2 ha (20,000 m²)" (attack round 8).
_CONV_UNITS = {"second": ("t", Fraction(1)), "seconds": ("t", Fraction(1)), "s": ("t", Fraction(1)), "minute": ("t", Fraction(60)), "minutes": ("t", Fraction(60)),
               "min": ("t", Fraction(60)), "mins": ("t", Fraction(60)), "hour": ("t", Fraction(3600)), "hours": ("t", Fraction(3600)), "h": ("t", Fraction(3600)),
               "hr": ("t", Fraction(3600)), "hrs": ("t", Fraction(3600)), "day": ("t", Fraction(86400)), "days": ("t", Fraction(86400)),
               "week": ("t", Fraction(604800)), "weeks": ("t", Fraction(604800)), "mm": ("l", Fraction(1, 1000)), "cm": ("l", Fraction(1, 100)),
               "m": ("l", Fraction(1)), "metres": ("l", Fraction(1)), "meters": ("l", Fraction(1)), "km": ("l", Fraction(1000)),
               "kilometres": ("l", Fraction(1000)), "kilometers": ("l", Fraction(1000)), "m²": ("a", Fraction(1)), "ha": ("a", Fraction(10_000)),
               "hectares": ("a", Fraction(10_000)), "km²": ("a", Fraction(1_000_000)), "g": ("m", Fraction(1, 1000)), "kg": ("m", Fraction(1)),
               "tonnes": ("m", Fraction(1000)), "tonne": ("m", Fraction(1000))}
_CONV_UNIT = r"(?P<{g}>seconds?|minutes?|mins?|hours?|hrs?|days?|weeks?|kilomet(?:re|er)s|metres|meters|km²|km|cm|mm|m²|m|hectares|ha|tonnes?|kg|g|h|s)(?![\w²³⁻])"
_CONV_RE = re.compile(r"(?<![\d.,])(?P<a>" + _NUM + r")(?![\d,]\d|\.\d)\s*+" + _CONV_UNIT.format(g="ua") + r"\s*+(?:\(|(?:is|was|are|were|=|equals|"
                      r"is\s+equal\s+to|or|i\.e\.,?|that\s+is,?|which\s+is)\s++)(?P<ap>(?:about|approximately|roughly|around)\s++)?(?<![\d.,])"
                      r"(?P<b>" + _NUM + r")(?![\d,]\d|\.\d)\s*+" + _CONV_UNIT.format(g="ub"), re.IGNORECASE)
_COMPOUND_BEFORE_RE = re.compile(r"\d\s*+(?:hours?|hrs?|h|days?|weeks?|minutes?|km|m)\s*+(?:and\s+)?$", re.IGNORECASE)


def _conversion(ctx: _Ctx, s: _Sentence) -> None:
    from .grounded_figures import _half
    for m in _CONV_RE.finditer(s.text):
        ua, ub = _CONV_UNITS.get(m.group("ua").lower()), _CONV_UNITS.get(m.group("ub").lower())
        if ua is None or ub is None or ua[0] != ub[0] or m.group("ua").lower() == m.group("ub").lower():
            continue
        if _COMPOUND_BEFORE_RE.search(s.text, max(0, m.start() - 20), m.start()):
            continue  # "4 hours 30 minutes = 4.5 hours": a compound figure, read by the worked reader
        if m.group(0).count("(") and ")" not in s.text[m.end():m.end() + 3]:
            continue
        a, b = _num(m.group("a")), _num(m.group("b"))
        value = a * ua[1] / ub[1]
        tol = max(_half(m.group("b").replace(",", "")), value / 20 if m.group("ap") else Fraction(0))
        if not ctx.room("geo_conversion"):
            return
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_conversion", lambda cid, b=b, value=value, tol=tol, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_conversion", inputs=[("stated", b, f"the converted figure stated ({m.group('b')} {m.group('ub')})")],
            conclusion={"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(value)}), "right": _real(tol)},
            label=f"{m.group('a')} {m.group('ua')} in {m.group('ub')} is {_fmt(value)}",
            description=f"{_excerpt(s.text)} [a unit conversion stated outright equals the figure converted exactly (half a unit of the last digit written)]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


#: Spearman's denominator (or another closed formula of n) stated with n given in words or digits: "With six pairs, n³ − n = 216."
_N_GIVEN_RE = re.compile(r"\b(?P<n>" + _WORD_NUMBER + r"|\d{1,3})\s++(?:pairs|sites|rows|values|ranks|points|observations|samples|stations)\b|\bn\s*+=\s*+(?P<m>\d{1,3})\b",
                         re.IGNORECASE)
_N_FORMULA_RE = re.compile(r"(?<![\w])(?P<f>n\s*+(?:³|\^\s*+3)\s*+[−-]\s*+n|n\s*+\(\s*+n\s*+(?:²|\^\s*+2)\s*+[−-]\s*+1\s*+\)|n\s*+(?:²|\^\s*+2)\s*+[−-]\s*+1|"
                           r"n\s*+\(\s*+n\s*+[−-]\s*+1\s*+\)|n\s*+[−-]\s*+1)\s*+=\s*+(?P<v>" + _NUM + r")(?![\d,.]\d|\d)(?!\s*+[⁰¹²³⁴⁵⁶⁷⁸⁹^×÷*/+−(-])")


def _n_formula(ctx: _Ctx, s: _Sentence) -> None:
    fm = list(_N_FORMULA_RE.finditer(s.text))
    if not fm:
        return
    import bisect
    starts = [f.start() for f in fm]

    def inside(at: int) -> bool:  # (one bisection per figure: a scan of every formula per figure was quadratic on one long sentence)
        k = bisect.bisect_right(starts, at) - 1
        return k >= 0 and at < fm[k].end()
    given = [g for g in _N_GIVEN_RE.finditer(s.text) if not inside(g.start())] or list(_N_GIVEN_RE.finditer(s.before))
    ns = {(_WORD_NUMBERS[g.group("n").lower()] if g.group("n") and g.group("n").lower() in _WORD_NUMBERS else int(g.group("n") or g.group("m"))) for g in given}
    if len(ns) != 1:
        return
    n = Fraction(ns.pop())
    for m in fm:
        f = re.sub(r"\s", "", m.group("f")).replace("^3", "³").replace("^2", "²").replace("-", "−")
        value = {"n³−n": n ** 3 - n, "n(n²−1)": n * (n * n - 1), "n²−1": n * n - 1, "n(n−1)": n * (n - 1), "n−1": n - 1}.get(f)
        if value is None or not ctx.room("geo_n_formula"):
            continue
        v = _num(m.group("v"))
        ctx.decided.add(" ".join(s.text.split()))
        ctx.add("geo_n_formula", lambda cid, v=v, value=value, m=m: make_check(
            ctx.report, check_id=cid, kind="geo_n_formula", inputs=[("stated", v, f"the value stated ({m.group('v')})")],
            conclusion={"op": "eq", "left": _var("stated"), "right": _real(value)},
            label=f"{m.group('f')} with n = {_fmt(n)} is {_fmt(value)}",
            description=f"{_excerpt(s.text)} [a formula in n stated with n given in the sentence (pairs, sites, n = ...) equals its value at that n]",
            claim_ids=_claims(ctx.report, s.text, m.group(0)), defect="stem_arithmetic_slip"))


#: A word count the answer states of itself (attack round 8, ge-t16): a line that is only the count ("(Word count: about 950.)", "(About
#: 800 words.)", "Word count: 506") or "this answer / essay / response is about N words (long)".
_GEO_WC_LINE_RE = re.compile(r"^[ \t]*+[(*_]*+[ \t]*+(?:(?:word\s*+count|length)\s*+[:=]\s*+)?(?P<ap>(?:about|approximately|approx\.|around|roughly|some|c\.|~)\s*+)?"
                             r"(?P<n>\d{1,2},\d{3}|\d{1,5})(?:\s++words)?[ \t]*+\.?[ \t]*+[)*_]*+[ \t]*+\.?[ \t]*+$", re.IGNORECASE | re.MULTILINE)
_GEO_WC_SELF_RE = re.compile(r"\b(?:this|my|the)\s+(?:answer|essay|response|report|model\s+answer|analysis)\s+(?:is|runs\s+to|comes\s+to|has)\s+"
                             r"(?P<ap>(?:about|approximately|around|roughly|some|just\s+over|just\s+under)\s+)?(?P<n>\d{1,2},\d{3}|\d{1,5})\s+words\b", re.IGNORECASE)
_GEO_META_LINE_RE = re.compile(r"^[ \t]*+[(*_]*+(?:next\s+step|sources?|references?|note|word\s*+count)\b", re.IGNORECASE)
#: A word figure the answer credits to the request ("the 1,900 words you planned", "your 900-word limit").
#: A word figure the answer credits to the request, the figure after the credit (check round 10 of c3d: "You asked for about 1,500 words
#: for the two sections together.", "The question asks for a model answer of about 800 words.", "Your teacher set a limit of 350
#: words."): group ``p``.
REQ_WORDS_CREDIT = (r"\b(?:you|the\s+(?:[A-Za-z]{1,12}\s+){0,2}?(?:question|task|request|brief|prompt|assignment)|your\s+(?:teacher|task|brief|question|request|assignment))\s+"
                    r"(?:asked|asks|ask|wanted|wants|requested|requests|set|sets|specified|specifies|gave|gives|called|calls|required|requires|"
                    r"allows?|allowed|permits?|permitted|limits?|limited|caps?|capped)\s+"
                    r"(?:for\s+)?(?:[a-z]+\s+){0,5}?(?:of\s+|to\s+)?(?:about|around|approximately|roughly|some|up\s+to|no\s+more\s+than|at\s+most|"
                    r"at\s+least)?\s*(?P<p>\d{1,2},\d{3}|\d{1,5})(?:\s++|-)words?\b")
_REQ_WORDS_CLAIM_RE = re.compile(r"\b(?:the\s+|your\s+|a\s+)?(?P<n>\d{1,2},\d{3}|\d{1,5})(?:\s++|-)words?\s+(?:that\s+)?(?:you|your\s+(?:request|brief|task|teacher))\s+"
                                 r"(?:planned|asked\s+for|requested|wanted|set|specified|mentioned|gave|were\s+given|have)\b|\byour\s+(?:planned\s+|stated\s+)?"
                                 r"(?P<m>\d{1,2},\d{3}|\d{1,5})[-\s]words?\b|" + REQ_WORDS_CREDIT, re.IGNORECASE)
_REQ_WORDS_RE = re.compile(r"(?<![\d.,])(?P<a>\d{1,2},\d{3}|\d{1,5})(?:\s*+(?:–|-|to)\s*+(?P<b>\d{1,2},\d{3}|\d{1,5}))?(?:\s++|-)words?\b", re.IGNORECASE)


def _geo_word_counts(ctx: _Ctx, text: str, request_text: Optional[str]) -> None:
    """A word count the answer states of itself, checked against the count of the answer as written (the shared counter of the channel,
    ``request_parser.count_words``): either the whole answer or the answer without its meta lines (next step, sources, notes, the count
    itself) may be meant, and one reading holding is enough (10% after an approximation word, else 2% or five words). A word figure the
    answer credits to the request is one the request states (a figure or a range)."""
    from ..channel.request_parser import count_words
    statements = [(m, "line") for m in _GEO_WC_LINE_RE.finditer(text[:MAX_TEXT]) if re.search(r"words|count|length", m.group(0), re.IGNORECASE)]
    statements += [(m, "self") for m in _GEO_WC_SELF_RE.finditer(text[:MAX_TEXT])]
    if statements:
        lines = text[:MAX_TEXT].split("\n")
        whole = count_words("\n".join(ln for ln in lines if not _GEO_WC_LINE_RE.fullmatch(ln)))
        body = count_words("\n".join(ln for ln in lines if not _GEO_META_LINE_RE.match(ln) and not _GEO_WC_LINE_RE.fullmatch(ln)))
        for m, _kind in statements[:8]:
            n = int(m.group("n").replace(",", ""))
            approx = bool(m.group("ap"))
            tol = Fraction(n, 10) if approx else max(Fraction(5), Fraction(n, 50))
            if not ctx.room("geo_word_count"):
                return
            options = [{"op": "le", "left": _abs({"op": "sub", "left": _var("stated"), "right": _real(Fraction(c))}), "right": _real(tol)}
                       for c in dict.fromkeys((whole, body))]
            sent = " ".join(m.group(0).split())
            ctx.decided.add(sent)
            ctx.add("geo_word_count", lambda cid, n=n, options=options, sent=sent: make_check(
                ctx.report, check_id=cid, kind="geo_word_count", inputs=[("stated", Fraction(n), f"the word count stated ({sent})")],
                conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
                label=f"the stated count {n} against the answer's {whole} words (or {body} without its meta lines)",
                description=f"{sent} [a word count the answer states of itself against the count of the answer as written; 10% after 'about', else 2% or five words]",
                claim_ids=_claims(ctx.report, sent, sent), severity="warning", defect="source_mismatch"))
    _word_limits(ctx, text)
    if not request_text:
        return
    asked = [(int(r.group("a").replace(",", "")), int((r.group("b") or r.group("a")).replace(",", ""))) for r in _REQ_WORDS_RE.finditer(request_text[:20_000])][:16]
    if not asked:
        return
    for m in _REQ_WORDS_CLAIM_RE.finditer(text[:MAX_TEXT]):
        n = int((m.group("n") or m.group("m") or m.group("p")).replace(",", ""))
        if any(lo - max(5, lo // 50) <= n <= hi + max(5, hi // 50) for lo, hi in asked) or not ctx.room("geo_request_figure"):
            continue
        shown = ", ".join(str(lo) if lo == hi else f"{lo}–{hi}" for lo, hi in asked)
        options = [{"op": "and", "args": [{"op": "ge", "left": _var("stated"), "right": _real(Fraction(lo))}, {"op": "le", "left": _var("stated"), "right": _real(Fraction(hi))}]}
                   for lo, hi in asked]
        ctx.add("geo_request_figure", lambda cid, n=n, m=m, options=options, shown=shown: make_check(
            ctx.report, check_id=cid, kind="geo_request_figure", inputs=[("stated", Fraction(n), f"the word figure credited to the request ({m.group(0).strip()})")],
            conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
            label=f"{n} words credited to the request against the request's {shown} words",
            description=f"{_excerpt(text[max(0, m.start() - 80):m.end() + 40])} [a word figure the answer credits to the request is one the request states]",
            claim_ids=_claims(ctx.report, text[max(0, m.start() - 200):m.end() + 100], m.group(0)), severity="warning", defect="source_mismatch"))


#: A word limit the answer states ("Examiners stop reading at 2,500 words", "the 2,500-word limit", "a limit of 2,500 words").
_WORD_LIMIT_RE = re.compile(r"\b(?:stop(?:s|ped)?\s+reading\s+(?:at|after)|(?:word\s+)?limit\s+(?:of|is|was)|limited\s+to|maximum\s+(?:of|is)|"
                            r"no\s+more\s+than|must\s+not\s+exceed|cap(?:ped)?\s+(?:of|at))\s++(?P<n>\d{1,2},\d{3}|\d{2,5})\s*+words?\b"
                            r"|(?<![\d.,])(?P<m>\d{1,2},\d{3}|\d{2,5})(?:-|\s)words?\s+(?:limit|maximum|cap)\b", re.IGNORECASE)


def _word_limits(ctx: _Ctx, text: str) -> None:
    """c3d (ge-t14): one word limit stated twice with different values ("Examiners stop reading at 2,500 words" and, later, "Examiners
    stop reading at 3,000 words"): the two statements of one quantity must agree (a contradiction, a warning)."""
    seen: list = []
    for m in _WORD_LIMIT_RE.finditer(text[:MAX_TEXT]):
        n = int((m.group("n") or m.group("m")).replace(",", ""))
        if seen and seen[0][0] != n and ctx.room("geo_case_consistency"):
            first, fm = seen[0]
            ctx.add("geo_case_consistency", lambda cid, first=first, fm=fm, n=n, m=m: make_check(
                ctx.report, check_id=cid, kind="geo_case_consistency",
                inputs=[("first", Fraction(first), f"the word limit first stated ({fm.group(0)})"), ("second", Fraction(n), f"the word limit stated again ({m.group(0)})")],
                conclusion={"op": "eq", "left": _var("first"), "right": _var("second")},
                label=f"the word limit: '{fm.group(0)}' and '{m.group(0)}' state one quantity",
                description=f"one word limit stated twice: '{_excerpt(fm.group(0), 120)}' and '{_excerpt(m.group(0), 120)}' [the two statements must agree]",
                claim_ids=tuple(dict.fromkeys(_claims(ctx.report, fm.group(0), fm.group(0)) + _claims(ctx.report, m.group(0), m.group(0)))),
                severity="warning", defect="contradiction"))
            return
        seen.append((n, m))


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


_WORD_DURATION_RE = re.compile(r"\b(?:" + _WORD_NUMBER + r"|an?|half)\s++(?:an?\s++)?(?:and\s++a\s++half\s++)?(?:days?|weeks?|months?|years?|hours?)\b",
                               re.IGNORECASE)


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
    facts, dates = _request_facts(request_text) if request_text else ({}, {})
    if facts:
        ctx.request_text = request_text[:20_000]
    clocks = _request_clocks(request_text) if request_text else {}
    events = _answer_events(sentences) if any(_DATE_RE.search(t.text) for t in sentences[:2000]) else []
    parts = _answer_parts(sentences)
    mags, ams = _answer_quantities(sentences) if any(_MAGNITUDE_RE.search(t.text) for t in sentences[:2000]) else ([], [])
    answer_facts = _answer_facts(sentences) if facts or any("'s" in t.text or "’s" in t.text for t in sentences[:400]) else {}
    for k, s in enumerate(sentences):
        if len(ctx.checks) >= MAX_PER_REPORT:
            ctx.skip("sentence", sum(1 for t in sentences[k:] if re.search(r"\d", t.text)))
            break
        if not re.search(r"\d", s.text) and not _WORD_DURATION_RE.search(s.text):
            continue  # (c3e: an interval written in words, "a year and a half after the Darfield quake", has no digit)
        for reader in (_density, _rate_per_thousand, _natural_increase, _doubling, _per_capita, _growth_rate, _mean, _sampling, _significance,
                       _fold, _change_by, _times_pair, _from_to_percent, _bracket_comparison, _pair_comparison, _years_apart, _conversion, _n_formula,
                       _dimension_area, _depth_volume, _share_part):
            _guarded(ctx, reader.__name__.strip("_"), lambda reader=reader: reader(ctx, s))
        if facts or dates:
            _guarded(ctx, "request_figures", lambda: _request_figures(ctx, s, facts, dates))
        if answer_facts or facts:
            _guarded(ctx, "labelled_fold", lambda: _labelled_fold(ctx, s, facts, answer_facts))
            _guarded(ctx, "labelled_relative", lambda: _labelled_relative(ctx, s, facts, answer_facts))
        if clocks:
            _guarded(ctx, "clock_interval", lambda: _clock_interval(ctx, s, clocks))
            _guarded(ctx, "clock_peak", lambda: _clock_peak(ctx, s, clocks))
        if events:
            _guarded(ctx, "event_relations", lambda: _event_relations(ctx, s, events))
        if parts:
            _guarded(ctx, "part_complement", lambda: _part_complement(ctx, s, parts))
        if mags:
            _guarded(ctx, "answer_quantity_relations", lambda: _answer_quantity_relations(ctx, s, k, mags, ams))
        if year_tables:
            _guarded(ctx, "table_change_by", lambda: _table_change_by(ctx, s, year_tables))
            _guarded(ctx, "year_table_credited", lambda: _year_table_credited(ctx, s, year_tables))
            _guarded(ctx, "year_table_derived", lambda: _year_table_derived(ctx, s, year_tables))
        if tables:
            _guarded(ctx, "table_figures", lambda: _table_figures(ctx, s, tables))
            _guarded(ctx, "table_aggregates", lambda: _table_aggregates(ctx, s, tables))
            _guarded(ctx, "table_superlative", lambda: _table_superlative(ctx, s, tables))
            _guarded(ctx, "table_spacing", lambda: _table_spacing(ctx, s, tables))
            _guarded(ctx, "table_column_change", lambda: _table_column_change(ctx, s, tables))
            _guarded(ctx, "row_pair_comparison", lambda: _row_pair_comparison(ctx, s, tables))
    if tables:
        for s in sentences:
            _guarded(ctx, "table_count", lambda s=s: _table_count(ctx, s, tables))
    _guarded(ctx, "case_consistency", lambda: _case_consistency(ctx, sentences, text))
    _guarded(ctx, "word_counts", lambda: _geo_word_counts(ctx, text, request_text))
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
