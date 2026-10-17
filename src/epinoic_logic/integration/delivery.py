"""The decision table, the summary, verdict signing and the binding checks (``integration/PROTOCOL.md`` sections 8 and 9).

Everything here is a pure function of a verdict's own fields, so the Worker re-derives exactly the same decision from
the verdict it receives (``integration/website/src/verify/decision-table.js``, same golden vectors in
``integration/vectors/decision-table/``). Nothing here imports the engine.

**Decision table** (rows in order, first match wins; only material claims count where a row says so):

1. (Worker only) the binding checks fail -> ``refuse_integrity`` (KIT-DL-030);
2. the receipt is REJECTED, the FINAL audit failed, or delivery was refused for a clearance, signature, custody or
   staleness reason -> ``refuse_integrity`` (KIT-DL-001, -003, -005, -006);
3. the clearance is still pending after the bounded wait -> ``refuse_incomplete`` (KIT-DL-004);
4. error-level receipt findings, a CONFLICTING or NO_DELIVERABLE_OUTPUT consolidation, or a material claim that is
   COUNTEREXAMPLE, INCONSISTENT_PREMISES or UNSATISFIABLE -> ``revise`` when the policy allows one revision that has not
   happened yet, else ``refuse_unresolved`` (KIT-DL-002, -007, -008, -010; KIT-DL-020 after a revision);
5. a material eligible claim is UNKNOWN, TIMEOUT, INTERNAL_ERROR or NOT_ATTEMPTED -> ``refuse_incomplete`` (KIT-DL-011,
   and KIT-DL-013 when the budget was spent: the count ``budget_skipped`` of material eligible claims the budget or the
   STEM budget left NOT_ATTEMPTED) under every policy but ``verified-v1-qualify``, which continues (so ``verified-v1``,
   the default, and any policy this table does not know refuse: the row fails closed);
6. a material claim is AMBIGUOUS_TRANSLATION -> continue with its label (no v1 policy blocks it; decision D4);
7. otherwise ``deliver``.

NOT_ELIGIBLE, UNSUPPORTED and INVALID_FORMALIZATION neither block nor make the checks incomplete: they are labelled as
not formally checked. **An answer whose required checks did not complete is never labelled as checked, whatever the
policy**: a non-definitive status never yields the summary ``formally_checked`` (property-tested).

Every row reads the verdict's own fields and its ``counts``, never the list of claims: the list is capped at 32 and
leaves out a claim without a verbatim excerpt, so a decision read from it could differ from the one the service made
over every claim. The service and the Worker therefore decide from the same counts.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

from pydantic import ValidationError

from .canonical import CanonicalError, canonical_bytes, sha256_text
from .protocol import (
    AUDIT_SCOPE_STATEMENT, DEFINITIVE, INCOMPLETE_STATUSES, NEGATIVE, POSITIVE, SCOPE_STATEMENT, TurnVerdict, dump,
)

__all__ = [
    "REVISION_POLICIES", "QUALIFY_POLICY", "BUDGET_ATTEMPTS", "INTEGRITY_REFUSALS", "ClaimFields", "DecisionInput", "decide", "summarize",
    "count_claims", "decision_input_of", "signable_bytes", "sign_verdict", "verify_verdict_signature", "BindingContext",
    "counts_problem", "binding_problem",
]

#: Policies that allow one bounded revision (decision D5: none by default, so ``revise`` is never produced in v1).
REVISION_POLICIES: frozenset[str] = frozenset()
#: The one policy under which a material eligible claim without a definitive result does not refuse (row 5, decision D2).
QUALIFY_POLICY = "verified-v1-qualify"
BUDGET_ATTEMPTS: frozenset[str] = frozenset({"skipped_budget", "stem_budget"})
#: Overseer refusal labels that are integrity failures (row 2), with their delivery reason.
INTEGRITY_REFUSALS: Mapping[str, str] = {
    "clearance_failed": "KIT-DL-003",
    "final_audit_not_passed": "KIT-DL-005",
    "signature_invalid": "KIT-DL-006",
    "custody_failed": "KIT-DL-006",
    "stale": "KIT-DL-006",
    "not_deliverable": "KIT-DL-006",
}
#: Overseer refusal labels that are unresolved content (row 4), with their delivery reason.
UNRESOLVED_REFUSALS: Mapping[str, str] = {
    "receipt_error_findings": "KIT-DL-002",
    "consolidation_conflicting": "KIT-DL-007",
    "no_deliverable_output": "KIT-DL-008",
}


@dataclass(frozen=True)
class ClaimFields:
    materiality: str
    formal: str
    attempt: str
    release_permitted: bool = False


@dataclass(frozen=True)
class DecisionInput:
    """The verdict fields the decision table reads (and nothing else): the counts, never the capped list of claims."""
    policy: str
    revision_of: Optional[str]
    receipt_status: str
    receipt_error_codes: tuple[str, ...]
    overseer_state: str
    delivery_allowed: bool
    overseer_refusal: Optional[str]
    consolidation_status: Optional[str]
    blocking: int
    unavailable: int
    #: Material eligible claims the budget or the STEM budget left NOT_ATTEMPTED (``counts.budget_skipped``; KIT-DL-013).
    budget_skipped: int = 0


def _material(c: ClaimFields) -> bool:
    return c.materiality == "material"


def _eligible(c: ClaimFields) -> bool:
    return c.attempt != "not_eligible"


def count_claims(claims: Iterable[ClaimFields]) -> dict[str, int]:
    """The verdict's ``counts`` (PROTOCOL.md section 5.4): every count but ``claims_total`` concerns material claims;
    ``eligible`` excludes NOT_ELIGIBLE; ``permitted`` is the positive results whose release assessment permits release;
    ``budget_skipped`` the incomplete ones the budget or the STEM budget left NOT_ATTEMPTED (row 5's KIT-DL-013)."""
    cs = list(claims)
    material = [c for c in cs if _material(c)]
    eligible = [c for c in material if _eligible(c)]
    return {
        "claims_total": len(cs),
        "material": len(material),
        "eligible": len(eligible),
        "attempted": sum(1 for c in eligible if c.attempt == "attempted"),
        "definitive": sum(1 for c in eligible if c.formal in DEFINITIVE),
        "positive": sum(1 for c in eligible if c.formal in POSITIVE),
        "permitted": sum(1 for c in eligible if c.formal in POSITIVE and c.release_permitted),
        "blocking": sum(1 for c in material if c.formal in NEGATIVE),
        "unavailable": sum(1 for c in eligible if c.formal in INCOMPLETE_STATUSES),
        "budget_skipped": sum(1 for c in eligible if c.formal in INCOMPLETE_STATUSES and c.attempt in BUDGET_ATTEMPTS),
        "not_eligible": sum(1 for c in material if not _eligible(c)),
    }


def decide(inp: DecisionInput) -> tuple[str, list[str]]:
    """Rows 2 to 7 of the decision table: ``(decision, reasons)``. Row 1 is the Worker's binding check. A verdict the
    service issued after an unexpected exception (refusal ``internal_error``) is ``refuse_incomplete`` with KIT-DL-900,
    before every row: it never delivers."""
    if inp.overseer_refusal == "internal_error":
        return "refuse_incomplete", ["KIT-DL-900"]
    # Row 2: integrity.
    reasons: list[str] = []
    if inp.receipt_status == "REJECTED":
        reasons.append("KIT-DL-001")
    if inp.overseer_state == "AUDIT_FAILED":
        reasons.append("KIT-DL-005")
    if inp.overseer_refusal in INTEGRITY_REFUSALS:
        reasons.append(INTEGRITY_REFUSALS[inp.overseer_refusal])
    if (not inp.delivery_allowed and inp.overseer_refusal is None and inp.overseer_state != "AUDIT_PENDING"):
        reasons.append("KIT-DL-006")  # a refusal without a label is a refusal (fail closed)
    if reasons:
        return "refuse_integrity", sorted(set(reasons))
    # Row 3: the clearance is still pending.
    if inp.overseer_state == "AUDIT_PENDING" or inp.overseer_refusal == "clearance_pending":
        return "refuse_incomplete", ["KIT-DL-004"]
    # Row 4: unresolved content.
    if inp.receipt_error_codes:
        reasons.append("KIT-DL-002")
    if inp.overseer_refusal in UNRESOLVED_REFUSALS:
        reasons.append(UNRESOLVED_REFUSALS[inp.overseer_refusal])
    if inp.consolidation_status == "CONFLICTING":
        reasons.append("KIT-DL-007")
    if inp.consolidation_status == "NO_DELIVERABLE_OUTPUT":
        reasons.append("KIT-DL-008")
    if inp.blocking > 0:
        reasons.append("KIT-DL-010")
    if reasons:
        if inp.policy in REVISION_POLICIES and inp.revision_of is None:
            return "revise", sorted(set(reasons))
        if inp.revision_of is not None:
            reasons.append("KIT-DL-020")
        return "refuse_unresolved", sorted(set(reasons))
    if not inp.delivery_allowed:  # pragma: no cover - every refusal label is handled above
        return "refuse_integrity", ["KIT-DL-006"]
    # Row 5: checks incomplete for a material eligible claim. Only the qualify policy continues; verified-v1 and any
    # policy this table does not know refuse (fail closed).
    if inp.unavailable > 0 and inp.policy != QUALIFY_POLICY:
        reasons = ["KIT-DL-011"]
        if inp.budget_skipped > 0:
            reasons.append("KIT-DL-013")
        return "refuse_incomplete", reasons
    # Row 6 (ambiguous material claim: continue with its label) and row 7.
    return "deliver", []


def summarize(counts: Mapping[str, int]) -> str:
    """The ``summary`` of a delivered answer (PROTOCOL.md section 8), from its counts."""
    if counts["unavailable"] > 0:
        return "incomplete"
    if counts["positive"] == 0:
        return "not_formally_checkable"
    if counts["permitted"] == counts["eligible"]:
        return "formally_checked"
    if counts["permitted"] > 0:
        return "partly_checked"
    return "formal_only"


def decision_input_of(verdict: Mapping[str, Any], *, revision_of: Optional[str] = None) -> DecisionInput:
    """The decision-table input read from a verdict JSON object (the Worker's re-derivation reads the same fields): its
    counts, never its capped list of claims."""
    consolidation = verdict["delivery"].get("consolidation")
    counts = verdict["counts"]
    return DecisionInput(
        policy=verdict["bound"]["policy"], revision_of=revision_of, receipt_status=verdict["receipt"]["status"],
        receipt_error_codes=tuple(verdict["receipt"]["error_codes"]), overseer_state=verdict["overseer"]["state"],
        delivery_allowed=bool(verdict["overseer"]["delivery_allowed"]), overseer_refusal=verdict["overseer"].get("refusal"),
        consolidation_status=consolidation["status"] if consolidation else None,
        blocking=int(counts["blocking"]), unavailable=int(counts["unavailable"]), budget_skipped=int(counts["budget_skipped"]),
    )


# --------------------------------------------------------------------------------------------- signing


def signable_bytes(verdict: Mapping[str, Any]) -> bytes:
    """The canonical JSON of a verdict without its ``signature`` member: what the HMAC covers."""
    body = {k: v for k, v in verdict.items() if k != "signature"}
    return canonical_bytes(body)


def sign_verdict(verdict: Mapping[str, Any], key: bytes, key_id: str) -> dict:
    """``verdict`` with its HMAC-SHA256 signature under the verdict key (never the engine key)."""
    if not key or len(key) < 32:
        raise ValueError("the verdict key must be at least 32 bytes")
    mac = hmac.new(key, signable_bytes(verdict), hashlib.sha256).hexdigest()
    return {**{k: v for k, v in verdict.items() if k != "signature"}, "signature": {"alg": "hmac-sha256", "key_id": key_id, "value": mac}}


def verify_verdict_signature(verdict: Mapping[str, Any], key: bytes) -> bool:
    sig = verdict.get("signature")
    if not isinstance(sig, Mapping) or sig.get("alg") != "hmac-sha256" or not isinstance(sig.get("value"), str) or not key:
        return False
    try:
        expected = hmac.new(key, signable_bytes(verdict), hashlib.sha256).hexdigest()
    except CanonicalError:
        return False
    return hmac.compare_digest(expected, sig["value"])


# --------------------------------------------------------------------------------------------- binding (row 1)


@dataclass(frozen=True)
class BindingContext:
    """What the Worker knows independently of the verdict: its own ids, the student's text, the answers it sent (agent
    id, answer text, result digest) and, for ``deliver``, the text it is about to release."""
    task_id: str
    request_id: str
    user_text: str
    policy: str
    mode: str
    answers: Sequence[tuple[str, str, str]]
    release_text: Optional[str] = None
    revision_of: Optional[str] = None


def counts_problem(counts: Mapping[str, int], listed: Mapping[str, int], n_listed: int) -> Optional[str]:
    """Why ``counts`` (a verdict's counts over EVERY claim of its deliverable) cannot go with the claims it lists, whose
    own counts are ``listed`` (``n_listed`` entries), or ``None``.

    The list is a part of every claim (claims without an excerpt are counted but not listed, and at most 32 are
    listed), so each listed count is a lower bound of the verdict's count whatever the list's length, and equal to it
    when every claim is listed; when every material claim is listed, every count but ``claims_total`` (the only one
    that counts supporting claims) is exact. The counts must also be the counts of SOME list of claims: a material
    claim is eligible or not; attempted, definitive and unavailable claims are eligible ones; positive results are
    definitive; permitted ones are positive; a definitive result that is not positive is a blocking one; a claim the
    budget skipped is an incomplete one. So a listed material claim that is TIMEOUT or COUNTEREXAMPLE can never be hidden
    from the decision re-derived from the counts."""
    if n_listed > counts["claims_total"]:
        return "more claims are listed than counted"
    if any(listed[k] > counts[k] for k in listed):
        return "a listed claim is missing from the counts"
    if n_listed == counts["claims_total"] and any(listed[k] != counts[k] for k in listed):
        return "the counts disagree with the listed claims"
    if listed["material"] == counts["material"] and any(listed[k] != counts[k] for k in listed if k != "claims_total"):
        return "the counts disagree with the listed material claims"  # all material claims listed: all but the total exact
    c = counts
    coherent = (c["material"] <= c["claims_total"] and c["eligible"] + c["not_eligible"] == c["material"]
                and c["attempted"] <= c["eligible"] and c["positive"] <= c["definitive"] and c["permitted"] <= c["positive"]
                and c["definitive"] + c["unavailable"] <= c["eligible"] and c["definitive"] - c["positive"] <= c["blocking"] <= c["material"]
                and c["budget_skipped"] <= c["unavailable"])
    return None if coherent else "the counts are not the counts of any list of claims"


def binding_problem(verdict: Any, ctx: BindingContext) -> Optional[tuple[str, str]]:
    """``None`` when ``verdict`` is well formed, bound to this attempt and internally consistent; otherwise
    ``(raw code, detail)`` with the raw code ``verifier_malformed`` (not a verdict) or ``kit_dl_030`` (a verdict for
    something else, or one whose decision does not follow from its own fields). The Worker cannot verify the HMAC (it
    holds no key, invariant 22); it checks that a signature of the right algorithm is present."""
    if not isinstance(verdict, Mapping):
        return "verifier_malformed", "not a JSON object"
    try:
        v = TurnVerdict.model_validate(dict(verdict))
    except ValidationError as exc:
        return "verifier_malformed", f"not a turn verdict ({exc.error_count()} error(s))"
    data = dump(v)
    if v.ids.task_id != ctx.task_id or v.ids.request_id != ctx.request_id:
        return "kit_dl_030", "ids differ from this turn and attempt"
    try:
        if v.bound.user_text_sha256 != sha256_text(ctx.user_text):
            return "kit_dl_030", "bound to another user text"
    except CanonicalError:
        return "kit_dl_030", "the user text has no digest"
    if v.bound.policy != ctx.policy or v.bound.mode != ctx.mode:
        return "kit_dl_030", "bound to another policy or mode"
    sent = [(a, sha256_text(t), r) for a, t, r in ctx.answers]
    got = [(a.agent_id, a.answer_sha256, a.result_sha256) for a in v.bound.answers]
    if sorted(sent) != sorted(got):
        return "kit_dl_030", "bound to other answers"
    if v.scope_statement != SCOPE_STATEMENT or v.audit_scope_statement != AUDIT_SCOPE_STATEMENT:  # pragma: no cover - Literal-checked
        return "kit_dl_030", "the scope statement differs from the pinned constant"
    counts = {k: data["counts"][k] for k in data["counts"]}
    listed = count_claims(ClaimFields(c.materiality, c.formal, c.attempt, c.release_permitted) for c in v.claims)
    problem = counts_problem(counts, listed, len(v.claims))
    if problem:
        return "kit_dl_030", problem
    decision, reasons = decide(decision_input_of(data, revision_of=ctx.revision_of))
    if decision != v.delivery.decision or sorted(reasons) != sorted(v.delivery.reasons):
        return "kit_dl_030", "the decision does not follow from the verdict's own fields"
    if decision == "deliver":
        if v.delivery.deliverable is None or ctx.release_text is None:
            return "kit_dl_030", "a delivered verdict names its deliverable"
        if v.delivery.deliverable.answer_sha256 != sha256_text(ctx.release_text):
            return "kit_dl_030", "the text to release is not the checked deliverable"
        if v.summary != summarize(counts):
            return "kit_dl_030", "the summary does not follow from the counts"
        for c in v.claims:
            if c.excerpt not in ctx.release_text:
                return "kit_dl_030", "a claim excerpt is not a verbatim part of the deliverable"
    elif v.summary is not None:
        return "kit_dl_030", "only a delivered verdict carries a summary"
    return None
