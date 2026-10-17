"""The current-policy release check: may this engine result support releasing a claim as formally checked?

A definitive status is a statement about the encoding. Whether it may authorise anything is a separate decision that
application code makes, and this module states the engine's part of it as one deterministic rule. A result is
**release-eligible** only when every one of these holds:

1. **authentic**: it carries a signature that verifies under the receiver's key (and names the expected key id);
2. **bound**: its binding is internally consistent and, when the problem is given, bound to exactly that problem;
3. **current**: its component versions and its build, schema and policy identity are this engine's, and it was decided
   under the validation limits the receiver requires (:func:`.provenance.stale_reasons`). A result from an earlier
   release stays inspectable (it parses and its signature verifies) but is never eligible until the problem is
   verified again under the current policy;
4. **a positive verdict**: ENTAILED for an entailment query, CONSISTENT for a consistency query, SATISFIABLE for a
   satisfiability query. Everything else is either a negative verdict or no verdict;
5. **a verdict on the claim**: no diagnostic that withholds the verdict (E108 vacuous, E110 unasserted figure, E111
   unencoded reason, E112 circular);
6. **with its evidence**: the premises the proof relied on were computed (an ENTAILED or other positive result over
   premises names them); evidence that was not computed never reads as "no dependencies";
7. **resting on established premises only**: no ungrounded and no unverified dependency. A premise whose kind claims
   task or source authority that no application check validated is an unresolved dependency (:mod:`.authority`), so
   formal entailment from it is not permission to release.

The output option ``SolverConfig.produce_unsat_core`` changes none of these: the engine computes the evidence either way.
The scope statement still applies to an eligible result: it proves a property of the encoding only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..ir.canonical import problem_digest
from ..ir.schema import Limits, Problem
from .errors import NO_VERDICT_CODES
from .provenance import binding_inconsistencies, stale_reasons, verify_signature
from .results import VerificationResult
from .statuses import VerificationStatus

__all__ = ["ReleaseCheck", "POSITIVE_STATUS", "release_check"]

#: The positive verdict of each query.
POSITIVE_STATUS: dict[str, VerificationStatus] = {
    "entailment": VerificationStatus.ENTAILED,
    "consistency": VerificationStatus.CONSISTENT,
    "satisfiability": VerificationStatus.SATISFIABLE,
}


@dataclass(frozen=True)
class ReleaseCheck:
    """The outcome of :func:`release_check`: ``eligible`` and, when it is not, every reason (never only the first)."""
    eligible: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"eligible": self.eligible, "reasons": list(self.reasons)}


def release_check(
    result: VerificationResult,
    problem: Optional[Problem] = None,
    *,
    signing_key: Optional[bytes],
    key_id: Optional[str] = None,
    required_limits: Optional[Limits] = None,
) -> ReleaseCheck:
    """Apply the current-policy release rule (module docstring) to ``result``. Never raises for a parsed result."""
    reasons: list[str] = []
    # 1. authentic
    if not signing_key:
        reasons.append("unauthenticated: no verification key was given, so the signature cannot be verified")
    elif not result.signature:
        reasons.append("unauthenticated: the result is unsigned")
    elif key_id is not None and result.signature_key_id != key_id:
        reasons.append(f"unauthenticated: the result is signed with key id {result.signature_key_id!r}, not {key_id!r}")
    elif not verify_signature(result, signing_key):
        reasons.append("unauthenticated: the signature does not verify (the result was altered or signed with another key)")
    # 2. bound
    inconsistent = binding_inconsistencies(result)
    if inconsistent:
        reasons.append("binding inconsistent: " + "; ".join(inconsistent))
    if problem is not None:
        if result.binding.problem_digest != problem_digest(problem) or result.problem_id != problem.problem_id:
            reasons.append("not bound to this problem: the problem digest or id differs")
        if result.claim_id != problem.claim_id or result.request_id != problem.request_id:
            reasons.append(f"not bound to this claim: the result is for {result.request_id}/{result.claim_id}")
    # 3. current
    reasons.extend(f"stale: {why}; verify the problem again under the current policy" for why in stale_reasons(result, required_limits=required_limits))
    # 4. a positive verdict
    wanted = POSITIVE_STATUS.get(result.query) if result.query is not None else None
    if wanted is None or result.status is not wanted:
        reasons.append(f"no positive verdict: status {result.status.value}" + (f" (the {result.query} query is released only on {wanted.value})" if wanted is not None else ""))
    # 5. a verdict on the claim
    withheld = sorted({d.code for d in result.diagnostics if d.code in NO_VERDICT_CODES})
    if withheld:
        reasons.append(f"no verdict on the claim: {', '.join(withheld)}")
    # 6. with its evidence
    if wanted is VerificationStatus.ENTAILED and result.status is VerificationStatus.ENTAILED and not result.premises_relied_on:
        reasons.append("no dependency evidence: the proof names no premise it relied on")
    # 7. established premises only
    if result.ungrounded_dependencies:
        reasons.append(f"unresolved dependencies (ungrounded): {', '.join(result.ungrounded_dependencies[:16])}")
    if result.unverified_dependencies:
        reasons.append(f"unresolved dependencies (authority not validated by any check): {', '.join(result.unverified_dependencies[:16])}")
    return ReleaseCheck(eligible=not reasons, reasons=tuple(reasons))
