"""The flash router's rules and cost model, as data. Their digests are part of the router's identity (its hello and
every plan), so a change of either is visible to the service and to every recorded review.

The rules restate the service's minimum-oversight floor (``minimum-oversight-floor/1``) and only ever add to it: the
same agreement signals give at least the floor's two reviews, a combined answer's synthesis is reviewed N_FOLD over
all its sources, and every transfer is reviewed. What the router adds: escalations the floor does not read (a named
diagnostic, an unverified dependency), a third review when an agreement signal and an escalation hold together, and
SPLIT for long outputs. It never optimises cost below the floor (the service would refuse such a plan with
``KIT-RT-020``) and always chooses the standard profile when the overseer offers it.

The cost model holds planning estimates, NOT measurements: it names no model (decision D23) and is replaced by recorded
overseer-agent costs when such records exist (a new version of this sub-project, so a new ``cost_data_sha256``).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["RULES", "PARAMETERS", "COST_MODEL", "canonical", "rules_sha256", "cost_data_sha256", "RULES_SHA256", "COST_DATA_SHA256"]

RULES = (
    "epinoic-flash-router rules/1\n"
    "1. Every transfer of the request gets exactly one entry, in the request's order; the plan carries only closed"
    " vocabularies, the request's own transfer keys and digests, and this router's identity: no text and no model.\n"
    "2. Agreement signals, read exactly as the service's floor reads them: the receipt is REJECTED; it carries an"
    " error-level finding; it carries a repeated fault; a check is COUNTEREXAMPLE, INCONSISTENT_PREMISES or"
    " UNSATISFIABLE; it is STEM and a check is UNKNOWN, TIMEOUT, INTERNAL_ERROR or NOT_ATTEMPTED, or its receipt"
    " carries INT-SUBJ-002. Escalations this router adds: a named diagnostic; an unverified dependency.\n"
    "3. Independent complete reviews: 1 without a signal or an escalation; 2 with either; 3 with an agreement signal and"
    " an escalation together; never more than 4, never more than the request's max_instances, never fewer than 2 when"
    " an agreement signal holds.\n"
    "4. An output read by one review that has more than split_words words is divided into parts of at most split_words"
    " words, at most max_parts and at most max_instances parts (SPLIT); with 2 or more reviews each review reads the"
    " whole output (DUPLICATE); otherwise one instance reads it whole (IN_DEPTH).\n"
    "5. A combined answer's synthesis is reviewed N_FOLD over all its sources in the topology's order, with a"
    " request-scoped temporary context of the validated outcomes of at most context_max_bytes bytes, discarded after"
    " the request; its reviews follow rule 3. Its sources are reviewed by their own entries under rules 2 to 4.\n"
    "6. Every instance runs on the cheapest tier, on the standard profile when the request offers it (else the first"
    " profile it offers).\n"
    "7. The estimated cost of an entry follows the cost model: per instance, review_tokens_base tokens plus the"
    " characters the instance reads divided by chars_per_token (rounded up), and seconds_per_instance seconds; an"
    " N_FOLD instance reads the synthesis and every source. Integers only.\n"
)

PARAMETERS: dict[str, int] = {
    "split_words": 900,
    "max_parts": 16,
    "max_reviews": 4,
    "hard_max_instances": 64,
    "context_max_bytes": 65536,
}

COST_MODEL: dict[str, Any] = {
    "name": "epinoic-flash-router/cost-model-1",
    "basis": "planning estimates, not measurements; no model is named (decision D23)",
    "review_tokens_base": 6000,
    "chars_per_token": 4,
    "seconds_per_instance": 30,
}


def canonical(value: Any) -> str:
    """Canonical JSON (keys sorted by code point, no whitespace, non-ASCII raw): the form the service digests."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def rules_sha256(rules: str = RULES, parameters: dict[str, int] = PARAMETERS) -> str:
    return hashlib.sha256(canonical({"rules": rules, "parameters": parameters}).encode("utf-8")).hexdigest()


def cost_data_sha256(cost_model: dict[str, Any] = COST_MODEL) -> str:
    return hashlib.sha256(canonical(cost_model).encode("utf-8")).hexdigest()


RULES_SHA256 = rules_sha256()
COST_DATA_SHA256 = cost_data_sha256()
