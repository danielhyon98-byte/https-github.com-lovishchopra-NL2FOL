"""Integrity packs: the subject-specific checks each branch carries, plus the core pack
every branch runs. Deterministic findings cite the pack's working rules; formal checks
are problems the engine decides about the report's own statements."""
from __future__ import annotations

import re
from typing import Optional

from ..translate.contracts import SpecialistReport, StructuralFinding
from ..translate.grounding import check_claim_sources
from .base import FormalCheck
from .quant import extract_quant_checks

_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), start=1)}
_MONTH_YEAR_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(1[0-9]{3}|20[0-9]{2})\b")
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_SENT_RE = re.compile(r"(?<=[.?!])\s+")
_STUDY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s(?:and|&)\s[A-Z][a-z]+)?(?:\set\sal\.?)?)\s*\((\d{4})\)")
_PCT_RE = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s*(?:per cent|percent|%)")
_MEMORY_LABEL_RE = re.compile(r"from memory|illustrative|verify (?:them|these|this)", re.IGNORECASE)


def _chronology_formal(report: SpecialistReport, prefix: str) -> list[FormalCheck]:
    """'X ... came/was ... after ... Y' with two month-year dates -> X must be later than Y."""
    from ..ir.schema import Problem
    out: list[FormalCheck] = []
    n = 0
    for sent in _SENT_RE.split(report.original_response):
        if " after " not in sent.lower():
            continue
        dates = _MONTH_YEAR_RE.findall(sent)
        if len(dates) < 2:
            continue
        n += 1
        a = int(dates[0][1]) * 12 + _MONTHS[dates[0][0].lower()]
        b = int(dates[1][1]) * 12 + _MONTHS[dates[1][0].lower()]
        problem = {
            "problem_id": f"chron-{report.report_id}-{n}", "request_id": report.request_id, "claim_id": f"{report.report_id}:chronology-{n}", "query": "entailment",
            "symbols": [{"name": "later_event", "sort": "Int", "meaning": f"{dates[0][0]} {dates[0][1]} as year*12+month"}, {"name": "earlier_event", "sort": "Int", "meaning": f"{dates[1][0]} {dates[1][1]}"}],
            "premises": [{"id": "D1", "expr": {"op": "eq", "left": {"op": "var", "name": "later_event"}, "right": {"op": "int", "value": str(a)}}, "grounding": {"kind": "supplied_text", "verified": True}},
                         {"id": "D2", "expr": {"op": "eq", "left": {"op": "var", "name": "earlier_event"}, "right": {"op": "int", "value": str(b)}}, "grounding": {"kind": "supplied_text", "verified": True}}],
            "conclusion": {"id": "ORDER", "expr": {"op": "gt", "left": {"op": "var", "name": "later_event"}, "right": {"op": "var", "name": "earlier_event"}}, "label": "the first-named event came after the second"},
        }
        out.append(FormalCheck(check_id=f"{prefix}-chronology-{n}", kind="chronology", description=f"stated order of dated events: {sent.strip()[:160]}", problem=Problem.model_validate(problem)))
    return out


_QUOTE_SPAN_RE = re.compile(r"\"([^\"]{12,})\"|“([^”]{12,})”")


def _quant_formal(report: SpecialistReport, prefix: str) -> list[FormalCheck]:
    out: list[FormalCheck] = []
    for qc in extract_quant_checks(report.original_response, request_id=report.request_id, claim_id=f"{report.report_id}:{prefix}"):
        out.append(FormalCheck(check_id=f"{prefix}-{qc.check_id}", kind=qc.kind, description=f"report's own arithmetic: {qc.sentence[:160]}", problem=qc.problem))
    return out


class CorePack:
    """Runs for every subject: quotation grounding against supplied texts, numeric
    self-consistency of the report's own figures, and labelling of figures from memory."""
    name = "core"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        for c in report.claims:
            for g in check_claim_sources(c, report.supplied_texts):
                if g.verified is False:
                    f.append(StructuralFinding(code="CORE-SRC-001", severity="error", message="cited excerpt not found in the supplied text", claim_ids=[c.claim_id], rule_source="source integrity (every pack's non-negotiable 2)"))
        if _PCT_RE.search(report.original_response) and not report.supplied_texts and not _MEMORY_LABEL_RE.search(report.original_response) and not any(c.source_refs for c in report.claims):
            f.append(StructuralFinding(code="CORE-SRC-002", severity="info", message="figures stated without supplied sources, library references or a from-memory label", rule_source="sources.md L5 (working rule)"))
        if not report.supplied_texts and not _MEMORY_LABEL_RE.search(report.original_response):
            quoted = [m.group(1) or m.group(2) for m in _QUOTE_SPAN_RE.finditer(report.original_response)]
            if quoted:
                f.append(StructuralFinding(code="CORE-SRC-003", severity="warning", message=f"{len(quoted)} quotation(s) cannot be verified: no text was supplied and no from-memory label is present", claim_ids=[c.claim_id for c in report.claims if any(q in c.claim_text for q in quoted)][:8], rule_source="source integrity (quote from memory only with permission, and say so)"))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return _quant_formal(report, "core") + _chronology_formal(report, "core")


class HistoryPack:
    name = "history"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        try:
            from ..adapters.history_specialist.structural import structural_checks
        except Exception:
            return []
        return structural_checks(report)

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return []  # chronology and numeric self-consistency run in CorePack for every subject


class EnglishPack:
    name = "english"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        try:
            from ..adapters.english_specialist.structural import structural_checks
        except Exception:
            return []
        try:
            return list(structural_checks(report))
        except Exception:
            return []

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return []


class PsychologyPack:
    """Studies must be grounded (name + year is an attribution, not evidence); figures must be self-consistent."""
    name = "psychology"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        for c in report.claims:
            for m in _STUDY_RE.finditer(c.claim_text):
                if not c.source_refs:
                    f.append(StructuralFinding(code="PS-SRC-001", severity="warning", message=f"study attribution {m.group(0)!r} has no knowledge-document or library grounding", claim_ids=[c.claim_id], rule_source="blueprint core operation (Psychology: Claim -> Study -> Link -> Evaluation); sources.md L5 (working rule)"))
            if re.search(r"\b(significant(?:ly)?|statistically)\b", c.claim_text, re.IGNORECASE) and not _PCT_RE.search(c.claim_text) and not re.search(r"\bp\s*[<=>]\s*0?\.\d+", c.claim_text):
                f.append(StructuralFinding(code="PS-STR-001", severity="info", message="'significant' used without a figure or p-value", claim_ids=[c.claim_id], rule_source="command terms C7 (quantities checked in parts; working rule)"))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return []  # numeric self-consistency comes from CorePack


class EconomicsPack:
    name = "economics"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        text = report.original_response.lower()
        if "diagram" in text and not re.search(r"\b(shift|curve|axis|equilibrium|intersect)", text):
            f.append(StructuralFinding(code="EC-STR-001", severity="info", message="a diagram is mentioned but no curve, shift or equilibrium is described", rule_source="blueprint core operation (Economics: Define -> Model/Diagram -> Mechanism -> Apply -> Evaluate); working rule"))
        for c in report.claims:
            if re.search(r"\belasticity\b", c.claim_text, re.IGNORECASE) and not re.search(r"\d", c.claim_text):
                f.append(StructuralFinding(code="EC-STR-002", severity="info", message="elasticity asserted without a value or the percentage changes it is computed from", claim_ids=[c.claim_id], rule_source="command terms C7 (working rule)"))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        """Elasticity = %change in quantity / %change in price when all three are stated."""
        out: list[FormalCheck] = []
        n = 0
        for sent in _SENT_RE.split(report.original_response):
            m = re.search(r"elasticity[^.]{0,80}?(?:is|was|of|=|equals)\s*(-?\d+(?:\.\d+)?)", sent, re.IGNORECASE)
            pcts = _PCT_RE.findall(sent)
            if m and len(pcts) >= 2:
                n += 1
                from fractions import Fraction
                from ..ir.schema import Problem
                stated = Fraction(m.group(1)).__abs__()
                q, p = Fraction(pcts[0]), Fraction(pcts[1])
                if "price" in sent.lower()[: sent.lower().find(pcts[0])] if pcts[0] in sent else False:
                    q, p = p, q  # price change named first
                lo, hi = stated * Fraction(19, 20), stated * Fraction(21, 20)
                R = lambda x: {"op": "real", "value": f"{x.numerator}/{x.denominator}" if x.denominator != 1 else str(x.numerator)}
                V = lambda s: {"op": "var", "name": s}
                ratio = {"op": "div", "left": V("dq"), "right": R(p)}
                prob = {"problem_id": f"ped-{report.report_id}-{n}", "request_id": report.request_id, "claim_id": f"{report.report_id}:elasticity-{n}", "query": "entailment",
                        "symbols": [{"name": "dq", "sort": "Real", "meaning": "percentage change in quantity"}, {"name": "dp", "sort": "Real", "meaning": "percentage change in price"}],
                        "premises": [{"id": "DQ", "expr": {"op": "eq", "left": V("dq"), "right": R(q)}, "grounding": {"kind": "supplied_text", "verified": True}},
                                     {"id": "DP", "expr": {"op": "eq", "left": V("dp"), "right": R(p)}, "grounding": {"kind": "supplied_text", "verified": True}}],
                        "conclusion": {"id": "PED", "expr": {"op": "and", "args": [{"op": "ge", "left": ratio, "right": R(lo)}, {"op": "le", "left": ratio, "right": R(hi)}]}, "label": f"stated elasticity {stated}"}}
                out.append(FormalCheck(check_id=f"economics-elasticity-{n}", kind="elasticity", description=sent.strip()[:160], problem=Problem.model_validate(prob)))
        return out


class BusinessPack:
    name = "business_management"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        for c in report.claims:
            if re.search(r"\b(recommend|should)\b", c.claim_text, re.IGNORECASE) and c.claim_role in ("judgement", "point", "link") and not c.supporting_claim_ids:
                f.append(StructuralFinding(code="BM-STR-001", severity="info", message="a recommendation with no supporting claims recorded", claim_ids=[c.claim_id], rule_source="blueprint core operation (Business: Define -> Apply -> Analyse with the tool -> Evaluate); working rule"))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        """Margins stated with the figures they are computed from: margin = profit / revenue."""
        out: list[FormalCheck] = []
        n = 0
        for sent in _SENT_RE.split(report.original_response):
            m = re.search(r"(?:profit|gross|net)\s+margin[^.]{0,60}?(\d{1,3}(?:\.\d+)?)\s*(?:per cent|percent|%)", sent, re.IGNORECASE)
            nums = re.findall(r"(?:profit|revenue|sales)\s+of\s+(?:\$|£|€)?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(million|m|thousand|k)?", sent, re.IGNORECASE)
            if m and len(nums) >= 2:
                n += 1
                from fractions import Fraction
                from ..ir.schema import Problem
                scale = {"million": 10**6, "m": 10**6, "thousand": 10**3, "k": 10**3}
                vals = [Fraction(v.replace(",", "")) * scale.get((u or "").lower(), 1) for v, u in nums[:2]]
                low = sent.lower()
                profit, revenue = (vals[0], vals[1]) if low.find("profit") < low.find("revenue" if "revenue" in low else "sales") else (vals[1], vals[0])
                stated = Fraction(m.group(1))
                lo, hi = stated * Fraction(19, 20), stated * Fraction(21, 20)
                R = lambda x: {"op": "real", "value": f"{x.numerator}/{x.denominator}" if x.denominator != 1 else str(x.numerator)}
                V = lambda s: {"op": "var", "name": s}
                margin = {"op": "mul", "args": [R(Fraction(100)), {"op": "div", "left": V("profit"), "right": R(revenue)}]}
                prob = {"problem_id": f"margin-{report.report_id}-{n}", "request_id": report.request_id, "claim_id": f"{report.report_id}:margin-{n}", "query": "entailment",
                        "symbols": [{"name": "profit", "sort": "Real"}, {"name": "revenue", "sort": "Real"}],
                        "premises": [{"id": "PROFIT", "expr": {"op": "eq", "left": V("profit"), "right": R(profit)}, "grounding": {"kind": "supplied_text", "verified": True}},
                                     {"id": "REVENUE", "expr": {"op": "eq", "left": V("revenue"), "right": R(revenue)}, "grounding": {"kind": "supplied_text", "verified": True}}],
                        "conclusion": {"id": "MARGIN", "expr": {"op": "and", "args": [{"op": "ge", "left": margin, "right": R(lo)}, {"op": "le", "left": margin, "right": R(hi)}]}, "label": f"stated margin {stated} per cent"}}
                out.append(FormalCheck(check_id=f"business-margin-{n}", kind="margin", description=sent.strip()[:160], problem=Problem.model_validate(prob)))
        return out


class GenericPack:
    name = "generic"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        ids = {c.claim_id for c in report.claims}
        for c in report.claims:
            missing = [s for s in c.supporting_claim_ids if s not in ids]
            if missing:
                f.append(StructuralFinding(code="GEN-STR-001", severity="error", message=f"claim cites unknown supporting claims {missing}", claim_ids=[c.claim_id]))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return []
