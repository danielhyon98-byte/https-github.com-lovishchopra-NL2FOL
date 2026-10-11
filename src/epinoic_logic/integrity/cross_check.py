"""Formal cross-agent checks with Z3.

Two questions that only a solver can answer soundly across agents:

1. Do the formalized claims of different specialists (and the synthesis) contradict
   each other? -> joint consistency, with the conflicting claims named from the core.
2. Does a synthesized claim actually follow from the source claims it cites? ->
   entailment of the synthesized conclusion from the union of the sources' premises.

Both rely on a SHARED GLOSSARY: symbols with the same name across problems denote
the same proposition or quantity. The translator is instructed to reuse the request's
glossary; a symbol declared with different sorts in two problems is reported as a
glossary conflict and the joint check is not run.
"""
from __future__ import annotations

from typing import Optional

from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import verify
from ..engine.statuses import VerificationStatus as S
from ..ir.schema import Assertion, Problem, Symbol
from .contracts import IntegrityFinding

SEP = "::"


def _merge_symbols(problems: list[Problem]) -> tuple[list[Symbol], list[IntegrityFinding]]:
    seen: dict[str, Symbol] = {}
    findings: list[IntegrityFinding] = []
    for p in problems:
        for s in p.symbols:
            prior = seen.get(s.name)
            if prior is None:
                seen[s.name] = s
            elif prior.sort != s.sort:
                findings.append(IntegrityFinding(code="INT-GLOSSARY-001", severity="error", message=f"symbol {s.name!r} declared as {prior.sort} and {s.sort} in different claims; shared glossary violated", claim_ids=[p.claim_id]))
    return list(seen.values()), findings


def _prefixed_premises(problems: list[Problem]) -> list[Assertion]:
    out: list[Assertion] = []
    for p in problems:
        for a in p.premises:
            out.append(a.model_copy(update={"id": f"{p.claim_id}{SEP}{a.id}"}))
        if p.conclusion is not None and p.query == "entailment":
            # A specialist's asserted point is itself a claim others may contradict.
            out.append(p.conclusion.model_copy(update={"id": f"{p.claim_id}{SEP}{p.conclusion.id}", "grounding": p.conclusion.grounding}))
    return out


def claim_ids_from_core(core: list[str]) -> list[str]:
    return sorted({pid.split(SEP, 1)[0] for pid in core if SEP in pid})


def joint_problem(problems: list[Problem], *, request_id: str, joint_id: str = "joint", query: str = "consistency", conclusion: Optional[Assertion] = None) -> tuple[Optional[Problem], list[IntegrityFinding]]:
    if not problems:
        return None, [IntegrityFinding(code="INT-GLOSSARY-002", severity="info", message="no formalized claims to cross-check")]
    symbols, findings = _merge_symbols(problems)
    if findings:
        return None, findings
    if conclusion is not None:
        for s in _needed_symbols(conclusion):
            if s not in {x.name for x in symbols}:
                findings.append(IntegrityFinding(code="INT-GLOSSARY-003", severity="error", message=f"synthesized conclusion uses symbol {s!r} that no source claim defines", claim_ids=[joint_id]))
        if findings:
            return None, findings
    data = {"problem_id": f"{joint_id}-problem", "request_id": request_id, "claim_id": joint_id, "query": query,
            "symbols": [s.model_dump(mode="json", exclude_none=True) for s in symbols],
            "premises": [a.model_dump(mode="json", exclude_none=True) for a in _prefixed_premises(problems)]}
    if conclusion is not None:
        data["conclusion"] = conclusion.model_dump(mode="json", exclude_none=True)
    try:
        return Problem.model_validate(data), []
    except Exception as exc:  # oversized or malformed merge
        return None, [IntegrityFinding(code="INT-GLOSSARY-004", severity="error", message=f"joint problem could not be built: {type(exc).__name__}")]


def _needed_symbols(a: Assertion) -> set[str]:
    out: set[str] = set()
    stack = [a.expr]
    while stack:
        n = stack.pop()
        op = getattr(n, "op", None)
        if op == "var":
            out.add(n.name)
        for field in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(n, field, None)
            if child is not None:
                stack.append(child)
        for child in getattr(n, "args", []) or []:
            stack.append(child)
    return out


def check_cross_report_consistency(problems: list[Problem], *, request_id: str, config: SolverConfig = SolverConfig(), signing_key: Optional[bytes] = None) -> tuple[Optional[VerificationResult], list[IntegrityFinding]]:
    """Are all specialists' formalized claims jointly consistent? Names the conflict."""
    joint, findings = joint_problem(problems, request_id=request_id, joint_id="cross-report")
    if joint is None:
        return None, findings
    result = verify(joint, config, signing_key=signing_key, key_id="integrity")
    if result.status is S.INCONSISTENT_PREMISES:
        claims = claim_ids_from_core(result.premises_relied_on)
        findings.append(IntegrityFinding(code="INT-CONFLICT-001", severity="error", message=f"specialist claims contradict each other under the shared glossary; conflicting claims: {claims}", claim_ids=claims, formal_result_id=result.result_id, deterministic=False))
    elif result.status is not S.CONSISTENT:
        findings.append(IntegrityFinding(code="INT-CONFLICT-004", severity="warning", message=f"cross-report consistency could not be decided: {result.status.value}", formal_result_id=result.result_id, deterministic=False))
    return result, findings


def check_synthesis_entailment(source_problems: list[Problem], synthesized_conclusion: Assertion, *, request_id: str, synthesized_claim_id: str, config: SolverConfig = SolverConfig(), signing_key: Optional[bytes] = None) -> tuple[Optional[VerificationResult], list[IntegrityFinding]]:
    """Does the synthesized claim follow from what the specialists actually asserted?"""
    joint, findings = joint_problem(source_problems, request_id=request_id, joint_id=synthesized_claim_id, query="entailment", conclusion=synthesized_conclusion)
    if joint is None:
        return None, findings
    result = verify(joint, config, signing_key=signing_key, key_id="integrity")
    if result.status is S.COUNTEREXAMPLE:
        findings.append(IntegrityFinding(code="INT-SYNTH-001", severity="error", message="synthesized claim is NOT entailed by the cited source claims (counterexample found): the combinator strengthened or invented content", claim_ids=[synthesized_claim_id], formal_result_id=result.result_id, deterministic=False))
    elif result.status is S.INCONSISTENT_PREMISES:
        claims = claim_ids_from_core(result.premises_relied_on)
        findings.append(IntegrityFinding(code="INT-CONFLICT-001", severity="error", message=f"source claims behind this synthesis contradict each other: {claims}", claim_ids=[synthesized_claim_id] + claims, formal_result_id=result.result_id, deterministic=False))
    elif result.status is S.ENTAILED:
        if result.ungrounded_dependencies:
            claims = claim_ids_from_core(result.ungrounded_dependencies)
            findings.append(IntegrityFinding(code="INT-SYNTH-002", severity="info", message=f"synthesized claim follows only via unverified inferences or assumptions in source claims {claims}", claim_ids=[synthesized_claim_id] + claims, formal_result_id=result.result_id, deterministic=False))
    else:
        findings.append(IntegrityFinding(code="INT-SYNTH-003", severity="warning", message=f"synthesis entailment could not be decided: {result.status.value}", claim_ids=[synthesized_claim_id], formal_result_id=result.result_id, deterministic=False))
    return result, findings
