"""The flash router's planner: a routing request (``epinoic.integration.routing-request.v1``, features only) in, one
routing plan (``epinoic.integration.routing-plan.v1``) out, by the rules of :mod:`epinoic_flash_router.rules`.

Pure and deterministic: no network, no clock, no randomness, no model call, no file read; the same request gives the
same plan. It reads the request's features only (the request never carries an answer, a claim text or an overseer
finding) and writes closed vocabularies, the request's own transfer keys and digests, and the router's identity.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .rules import COST_MODEL, PARAMETERS, canonical

__all__ = ["REASON_ORDER", "FEATURE_ORDER", "agreement_signals", "escalations", "plan_for"]

PLAN_SCHEMA = "epinoic.integration.routing-plan.v1"
PROTOCOL = "epinoic.integration.v1"
PORT_VERSION = "1.0"
TIER = "cheapest"

_NEGATIVE = ("COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "UNSATISFIABLE")
_UNDECIDED = ("UNKNOWN", "TIMEOUT", "INTERNAL_ERROR", "NOT_ATTEMPTED")
_STEM_UNDECIDED_CODES = ("INT-SUBJ-002",)

#: The order reasons are written in (a subset of the port's closed REASON_CODES).
REASON_ORDER = (
    "topology_combined", "baseline_single_review", "risk_receipt_rejected", "risk_error_findings", "risk_repeated_faults",
    "risk_negative_results", "risk_stem_undecided", "risk_diagnostics", "risk_unverified_dependencies", "volume_split",
    "topology_source", "profile_standard", "profile_fast", "cost_cheapest",
)
#: The port's closed FEATURE_NAMES, in the port's order.
FEATURE_ORDER = (
    "subjects", "stem", "task_type", "course_level", "items", "constraints", "supplied_texts", "size", "claims",
    "engine_statuses", "receipt", "diagnostics", "unverified_dependencies", "peer_relays", "repeated_faults", "topology",
)
#: The features every entry's decision reads (rules 2 to 4), and the one a combined answer's entries read (rule 5).
_READ = ("stem", "size", "engine_statuses", "receipt", "diagnostics", "unverified_dependencies", "repeated_faults")


def agreement_signals(out: Mapping[str, Any]) -> list[str]:
    """Rule 2: the floor's agreement signals that hold for one output, as reason codes."""
    receipt, statuses = out["receipt"], out["engine_statuses"]
    found = []
    if receipt["status"] == "REJECTED":
        found.append("risk_receipt_rejected")
    if receipt["error_codes"]:
        found.append("risk_error_findings")
    if out["repeated_faults"] > 0:
        found.append("risk_repeated_faults")
    if any(statuses.get(s, 0) > 0 for s in _NEGATIVE):
        found.append("risk_negative_results")
    if out["stem"] and (any(statuses.get(s, 0) > 0 for s in _UNDECIDED) or any(c in _STEM_UNDECIDED_CODES for c in receipt["warning_codes"])):
        found.append("risk_stem_undecided")
    return found


def escalations(out: Mapping[str, Any]) -> list[str]:
    """Rule 2: what this router adds to the floor's signals (it can only add oversight)."""
    found = []
    if out["diagnostics"]:
        found.append("risk_diagnostics")
    if out["unverified_dependencies"] > 0:
        found.append("risk_unverified_dependencies")
    return found


def _reviews(signals: list[str], extra: list[str], cap: int) -> int:
    """Rule 3."""
    wanted = 1 + (1 if signals or extra else 0) + (1 if signals and extra else 0)
    return max(min(wanted, PARAMETERS["max_reviews"], cap), 2 if signals else 1)


def _cost(instances: int, chars_each: int) -> dict[str, int]:
    """Rule 7."""
    per_token = COST_MODEL["chars_per_token"]
    tokens = COST_MODEL["review_tokens_base"] + -(-chars_each // per_token)
    return {"tokens": instances * tokens, "seconds": instances * COST_MODEL["seconds_per_instance"]}


def _ordered(names: set[str], order: tuple[str, ...]) -> list[str]:
    return [n for n in order if n in names]


def plan_for(request: Mapping[str, Any], *, identity: Mapping[str, str]) -> dict:
    """The plan for one routing request (a parsed ``routing-request.v1`` object), under this router's ``identity``."""
    limits, topology = request["limits"], request["topology"]
    cap = min(int(limits["max_instances"]), PARAMETERS["hard_max_instances"])
    profile = "standard" if "standard" in limits["profiles"] else limits["profiles"][0]
    combined = topology["kind"] == "combined"
    synthesis = topology.get("synthesis") if combined else None
    chars = {o["transfer_key"]: int(o["size"]["chars"]) for o in request["outputs"]}
    transfers = []
    for out in request["outputs"]:
        key = out["transfer_key"]
        signals, extra = agreement_signals(out), escalations(out)
        reviews = _reviews(signals, extra, cap)
        reasons = set(signals) | set(extra) | {"profile_standard" if profile == "standard" else "profile_fast", "cost_cheapest"}
        features = set(_READ)
        entry: dict[str, Any] = {"transfer_key": key, "profile": profile, "tier": TIER, "sources": [], "context": None}
        if key == synthesis:
            sources = list(topology["sources"])
            reasons.add("topology_combined")
            features.add("topology")
            entry.update(method="N_FOLD", reviews=reviews, parts=1, instances=reviews, sources=sources,
                         context={"scope": "request", "contents": "validated_outcomes", "max_bytes": PARAMETERS["context_max_bytes"],
                                  "discard": "after_request"},
                         estimated_cost=_cost(reviews, chars[key] + sum(chars.get(s, 0) for s in sources)))
        else:
            parts = 1
            if reviews == 1 and int(out["size"]["words"]) > PARAMETERS["split_words"]:
                parts = min(-(-int(out["size"]["words"]) // PARAMETERS["split_words"]), PARAMETERS["max_parts"], cap)
            if parts >= 2:
                method = "SPLIT"
                reasons.add("volume_split")
            else:
                parts = 1
                method = "DUPLICATE" if reviews >= 2 else "IN_DEPTH"
            if combined:
                reasons.add("topology_source")
                features.add("topology")
            if not signals and not extra:
                reasons.add("baseline_single_review")
            instances = reviews * parts
            entry.update(method=method, reviews=reviews, parts=parts, instances=instances,
                         estimated_cost=_cost(instances, -(-chars[key] // parts)))
        entry["reasons"] = _ordered(reasons, REASON_ORDER)
        entry["features_used"] = _ordered(features, FEATURE_ORDER)
        transfers.append(entry)
    request_sha256 = hashlib.sha256(canonical(request).encode("utf-8")).hexdigest()
    totals = {"instances": sum(t["instances"] for t in transfers),
              "estimated_cost": {"tokens": sum(t["estimated_cost"]["tokens"] for t in transfers),
                                 "seconds": sum(t["estimated_cost"]["seconds"] for t in transfers)}}
    plan_id = "plan-" + hashlib.sha256(canonical({"request_sha256": request_sha256, "router": dict(identity)}).encode("utf-8")).hexdigest()[:32]
    return {"schema": PLAN_SCHEMA, "protocol": PROTOCOL, "port_version": PORT_VERSION, "origin": "router", "plan_id": plan_id,
            "ids": {"task_id": request["ids"]["task_id"], "request_id": request["ids"]["request_id"]}, "request_sha256": request_sha256,
            "router": dict(identity), "transfers": transfers, "totals": totals}
