"""Per-claim entries of a verdict (``integration/PROTOCOL.md`` section 5.2, step 9).

The entries come from the deliverable's receipt (its outcomes and formal checks), the delivered report (the claims as
transmitted: the payload the channel delivered, never channel internals; phase 2 reads them from the overseer's
authoritative journal view instead) and the verifier's log (why an eligible claim has no outcome). Material claims come
first. ``excerpt`` is a verbatim part of the answer of at most 200 characters; a claim whose text does not occur in the
answer is counted but not listed (its status still counts in ``counts``). Every status is the deterministic display
status; nothing here decides a verdict.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from .delivery import ClaimFields
from .protocol import FORMAL_VALUES, NOT_ATTEMPTED
from .verifier import VerifierLog, claim_is_eligible

__all__ = ["MAX_ENTRIES", "MAX_EXCERPT", "excerpt_of", "claim_entries"]

MAX_ENTRIES = 32
MAX_EXCERPT = 200
_WS = re.compile(r"\s+")
_ROLE_RE = re.compile(r"^[a-z][a-z_]{0,63}$")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_STEM_BRANCHES = frozenset({"sciences", "mathematics", "computer_science"})


def excerpt_of(text: str, answer: str) -> Optional[str]:
    """A verbatim part of ``answer`` for ``text`` (at most 200 characters), or ``None``. An exact occurrence first; then
    an occurrence that differs only in whitespace, mapped back to the answer's own characters."""
    if not text or not answer:
        return None
    if text in answer:
        return text[:MAX_EXCERPT].rstrip() or None
    words = _WS.split(text.strip())
    if not words or not words[0]:
        return None
    pattern = r"\s+".join(re.escape(w) for w in words[:40])
    m = re.search(pattern, answer)
    if not m:
        return None
    found = answer[m.start():m.end()]
    return found[:MAX_EXCERPT].rstrip() or None


def _fidelity(outcome: Any) -> tuple[str, bool, bool]:
    rel = getattr(outcome, "release", None)
    if rel is None:
        return "missing", False, False
    return rel.fidelity, bool(rel.evidence_resolved), bool(rel.permitted)


def claim_entries(receipt: Any, claims: Iterable[Any], answer: str, log: Optional[VerifierLog] = None) -> tuple[list[dict], list[ClaimFields]]:
    """``(listed entries, every claim's decision fields)``: one entry per delivered claim, then one per branch formal check
    of the report's own statements (``source`` ``branch_check``, or ``stem`` on a STEM branch)."""
    outcomes = {o.claim_id: o for o in getattr(receipt, "outcomes", []) or []}
    claims = list(claims)
    materiality = {c.claim_id: c.materiality for c in claims}
    texts = {c.claim_id: c.claim_text for c in claims}
    entries: list[tuple[int, dict]] = []
    fields: list[ClaimFields] = []
    for order, c in enumerate(claims):
        o = outcomes.get(c.claim_id)
        if o is not None:
            formal = o.display_status.value
            attempt = "not_eligible" if formal == "NOT_ELIGIBLE" else "attempted"
            fidelity, resolved, permitted = _fidelity(o)
            result_id = o.verification.result_id if o.verification is not None else None
            binding = o.verification.binding.binding_digest if o.verification is not None else None
        elif not claim_is_eligible(c):
            formal, attempt, fidelity, resolved, permitted, result_id, binding = "NOT_ELIGIBLE", "not_eligible", "missing", False, False, None, None
        else:
            reason = (log.reason(c.claim_id) if log is not None else None) or "provider_unavailable"
            formal, attempt, fidelity, resolved, permitted, result_id, binding = NOT_ATTEMPTED, reason, "missing", False, False, None, None
        fields.append(ClaimFields(c.materiality, formal, attempt, permitted))
        ex = excerpt_of(c.claim_text, answer)
        if ex is None or not _ID_RE.match(c.claim_id):
            continue
        entries.append((order, {
            "claim_id": c.claim_id, "materiality": c.materiality, "role": c.claim_role if _ROLE_RE.match(str(c.claim_role)) else "other",
            "excerpt": ex, "source": "translation", "formal": formal, "attempt": attempt, "fidelity": fidelity,
            "evidence_resolved": resolved, "release_permitted": permitted, "result_id": result_id if result_id and _ID_RE.match(result_id) else None,
            "binding_digest": binding,
        }))
    stem = getattr(receipt, "branch", None) in _STEM_BRANCHES
    for k, fc in enumerate(getattr(receipt, "formal_checks", []) or []):
        named = list(getattr(fc, "claim_ids", []) or [])
        mat = "material" if any(materiality.get(cid) == "material" for cid in named) else "supporting"
        not_run = fc.satisfied is None and fc.formal_status is None
        formal = fc.formal_status if fc.formal_status in FORMAL_VALUES else NOT_ATTEMPTED
        if not_run:
            formal = NOT_ATTEMPTED
        attempt = ("stem_budget" if stem else "skipped_budget") if not_run else "attempted"
        fields.append(ClaimFields(mat, formal, attempt, False))
        text = next((texts[cid] for cid in named if cid in texts), "")
        ex = excerpt_of(text, answer)
        cid = fc.constraint_id if _ID_RE.match(str(fc.constraint_id)) else f"check-{k}"
        if ex is None:
            continue
        entries.append((len(claims) + k, {
            "claim_id": cid, "materiality": mat, "role": "quantitative", "excerpt": ex, "source": "stem" if stem else "branch_check",
            "formal": formal, "attempt": attempt, "fidelity": "missing", "evidence_resolved": False, "release_permitted": False,
            "result_id": fc.formal_result_id if fc.formal_result_id and _ID_RE.match(fc.formal_result_id) else None, "binding_digest": None,
        }))
    entries.sort(key=lambda e: (e[1]["materiality"] != "material", e[0]))
    return [e for _, e in entries[:MAX_ENTRIES]], fields
