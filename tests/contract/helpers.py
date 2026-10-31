"""Shared builders of the contract tests of the argument diagnosis (rules argdiag-1).

A stub rule is injected by monkeypatching ``engine.argument.diagnose`` (engine layer) or the rule tuples of
``translate.diag_argument`` / ``translate.diag_evidence`` (claim and report layers); no detection logic lives here.
"""
from __future__ import annotations

from typing import Any, Optional

from epinoic_logic.engine import SolverConfig
from epinoic_logic.ir.schema import Problem
from epinoic_logic.named import named_diagnostic
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer
from epinoic_logic.version import ARG_RULES_VERSION

KEY = b"argdiag-contract-key-0123456789abcdef"
KEY_ID = "contract"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
IDS = dict(request_id="req-ad", task_id="task-ad", report_id="rep-ad", agent_id="physics-specialist", subject="Physics", task_type="calculation")
#: The supplied text of the speed case states both the figure and the relation, so a check establishes every premise.
DOC = "Distance 120 km over 8 hours. Use speed = d / 8."


def V(name: str) -> dict:
    return {"op": "var", "name": name}


def R(value) -> dict:
    return {"op": "real", "value": str(value)}


def eq(left: dict, right: dict) -> dict:
    return {"op": "eq", "left": left, "right": right}


def implies(left: dict, right: dict) -> dict:
    return {"op": "implies", "left": left, "right": right}


def problem_dict(premises: list[dict], conclusion: dict, symbols: list[dict], *, claim_id: str = "c", request_id: str = "req-ad",
                 query: str = "entailment") -> dict:
    return {"ir_version": "1.0", "problem_id": f"p-{claim_id}", "request_id": request_id, "claim_id": claim_id, "query": query,
            "symbols": symbols, "premises": premises, "conclusion": conclusion}


def writer_link_problem(*, link_kind: str = "specialist_inference", fact_verified: bool = True, claim_id: str = "c") -> Problem:
    """e (a task fact a check verified, or one no check verified), the writer's link e -> p, and the point p."""
    fact = {"kind": "task_setting", "verified": True} if fact_verified else {"kind": "task_setting"}
    link = {"kind": link_kind, "note": "link: so"} if link_kind == "specialist_inference" else {"kind": link_kind}
    return Problem.model_validate(problem_dict(
        [{"id": "e", "expr": V("e"), "label": "the evidence holds", "grounding": fact},
         {"id": "l_so", "expr": implies(V("e"), V("p")), "label": "so the point holds", "grounding": link}],
        {"id": "C", "expr": V("p"), "label": "the point holds"},
        [{"name": "e", "sort": "Bool", "meaning": "the evidence holds"}, {"name": "p", "sort": "Bool", "meaning": "the point holds"}],
        claim_id=claim_id))


def established_problem(claim_id: str = "c") -> Problem:
    """Every premise established by a check in this process (verified flags as the application sets them)."""
    return Problem.model_validate(problem_dict(
        [{"id": "e", "expr": V("e"), "grounding": {"kind": "task_setting", "verified": True}},
         {"id": "l", "expr": implies(V("e"), V("p")), "grounding": {"kind": "task_setting", "verified": True}}],
        {"id": "C", "expr": V("p")}, [{"name": "e", "sort": "Bool"}, {"name": "p", "sort": "Bool"}], claim_id=claim_id))


def output(problem: dict, *, flags: Optional[list] = None, ambiguous: bool = False) -> dict:
    return {"problem": problem, "interpretation": {"reading": "read as stated", "glossary": [], "ambiguity_flags": flags or []},
            "ambiguous": ambiguous, "unsupported_reason": None}


def make_report(claim_text: str, *, cid: str = "c", materiality: str = "material", role: str = "quantitative", kind: str = "arithmetic",
                support: tuple = (), texts: tuple = ((("doc", DOC)),), subject: str = "Physics") -> tuple[ClaimRecord, SpecialistReport]:
    ids = {**IDS, "subject": subject}
    supporting = [ClaimRecord(**ids, claim_id=sid, claim_text=stext, claim_role="evidence") for sid, stext in support]
    claim = ClaimRecord(**ids, claim_id=cid, claim_text=claim_text, claim_role=role, proposed_claim_kind=kind, materiality=materiality,
                        supporting_claim_ids=[s.claim_id for s in supporting])
    body = " ".join([claim_text, *(s.claim_text for s in supporting)])
    report = SpecialistReport(**ids, original_response=body, response_sha256=sha256_text(body), claims=[claim, *supporting],
                              supplied_texts=[SuppliedText(document_id=d, text=t) for d, t in texts], created_at="2026-10-17T00:00:00Z")
    return claim, report


def speed_problem(distance=120, speed=15, *, claim_id: str = "c") -> dict:
    """distance = 120 and speed = d / 8 (both stated by DOC, so the grounding checks verify them) |= speed = 15."""
    return problem_dict(
        [{"id": "D", "expr": eq(V("d"), R(distance)), "label": f"Distance is {distance} km", "grounding": {"kind": "arithmetic_fact"}},
         {"id": "SPEED", "expr": eq(V("speed"), {"op": "div", "left": V("d"), "right": R(8)}), "grounding": {"kind": "arithmetic_fact"}}],
        {"id": "C", "expr": eq(V("speed"), R(speed)), "label": f"the speed is {speed} km/h"},
        [{"name": "d", "sort": "Real"}, {"name": "speed", "sort": "Real"}], claim_id=claim_id)


def run_claim(claim, report, response: Any, *, faithful: bool = True, task=None):
    """translate (fixture provider) -> verify (signed) -> review (fixture) -> compose."""
    translator = Translator(FixtureTranslationProvider({claim.claim_id: response}), config=CFG)
    reviewer = SemanticReviewer(FixtureReviewProvider({claim.claim_id: {"verdict": "faithful" if faithful else "uncertain", "issues": []}}))
    return verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, key_id=KEY_ID, task=task)


def stub_engine(*codes_and_severities: tuple, assertion_ids=("l_so",), message: str = "stub rule fired") -> Any:
    """An ``engine.argument.diagnose`` replacement that names the given ``(code, severity)`` pairs (severity None: the
    table's maximum) and reports a complete diagnosis."""
    def diagnose(problem, proc, compiled, config, limits, diagnostics=None):
        return [named_diagnostic(code, severity=sev, assertion_ids=list(assertion_ids), derivation="ir_structure", message=message)
                for code, sev in codes_and_severities], ARG_RULES_VERSION
    return diagnose


def stub_claim_rule(code: str, severity: Optional[str] = None, *, layer: str = "claim", message: str = "stub claim rule fired") -> Any:
    """A claim- or report-layer rule that names ``code`` once."""
    def rule(ctx):
        return [named_diagnostic(code, severity=severity, layer=layer, derivation="source_text", message=message)]
    rule.__name__ = f"stub_{code.lower().replace('-', '_')}"
    return rule
