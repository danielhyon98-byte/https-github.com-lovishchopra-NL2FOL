"""The flash router's port planner: a routing request (``epinoic.integration.routing-request.v1``, features only) in, one
routing plan (``epinoic.integration.routing-plan.v1``) out, by the port rules of the current rules file
(:mod:`epinoic_flash_router.rules`, port rules 1 to 7).

Pure and deterministic: no network, no clock, no randomness, no model call, no file read (the data were read once, when
they were loaded); the same request and the same data give the same plan. It reads the request's features only (the
request never carries an answer, a claim text or an overseer finding) and writes closed vocabularies, the request's own
transfer keys and digests, and the router's identity. Its numbers (split_words, max_parts, max_reviews,
hard_max_instances, context_max_bytes), the agreement signals it reads, the features it records and its cost estimates
all come from the data, so a re-tuned data file changes the plan without any change here.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Optional

from .rules import DEFAULT, DataSet, canonical

__all__ = ["REASON_ORDER", "FEATURE_ORDER", "agreement_signals", "escalations", "plan_for"]

PLAN_SCHEMA = "epinoic.integration.routing-plan.v1"
PROTOCOL = "epinoic.integration.v1"
PORT_VERSION = "1.0"
TIER = "cheapest"

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


def agreement_signals(out: Mapping[str, Any], data: DataSet = DEFAULT) -> list[str]:
    """Port rule 2: the floor's agreement signals that hold for one output, as reason codes (the statuses and codes read
    are the data's ``signals``)."""
    signals = data.signals
    receipt, statuses = out["receipt"], out["engine_statuses"]
    found = []
    if receipt["status"] == "REJECTED":
        found.append("risk_receipt_rejected")
    if receipt["error_codes"]:
        found.append("risk_error_findings")
    if out["repeated_faults"] > 0:
        found.append("risk_repeated_faults")
    if any(statuses.get(s, 0) > 0 for s in signals["negative_statuses"]):
        found.append("risk_negative_results")
    if out["stem"] and (any(statuses.get(s, 0) > 0 for s in signals["undecided_statuses"])
                        or any(c in signals["stem_undecided_codes"] for c in receipt["warning_codes"])):
        found.append("risk_stem_undecided")
    return found


def escalations(out: Mapping[str, Any]) -> list[str]:
    """Port rule 2: what this router adds to the floor's signals (it can only add oversight)."""
    found = []
    if out["diagnostics"]:
        found.append("risk_diagnostics")
    if out["unverified_dependencies"] > 0:
        found.append("risk_unverified_dependencies")
    return found


def _reviews(signals: list[str], extra: list[str], cap: int, params: Mapping[str, int]) -> int:
    """Port rule 3."""
    wanted = 1 + (1 if signals or extra else 0) + (1 if signals and extra else 0)
    return max(min(wanted, params["max_reviews"], cap), 2 if signals else 1)


def _cost(instances: int, chars_each: int, cost: Mapping[str, Any]) -> dict[str, int]:
    """Port rule 7."""
    per_token = cost["chars_per_token"]
    tokens = cost["review_tokens_base"] + -(-chars_each // per_token)
    return {"tokens": instances * tokens, "seconds": instances * cost["seconds_per_instance"]}


def _ordered(names: set[str], order: tuple[str, ...]) -> list[str]:
    return [n for n in order if n in names]


def plan_for(request: Mapping[str, Any], *, identity: Mapping[str, str], data: Optional[DataSet] = None) -> dict:
    """The plan for one routing request (a parsed ``routing-request.v1`` object), under this router's ``identity`` and
    ``data`` (the package's own data by default)."""
    data = DEFAULT if data is None else data
    params, cost = data.parameters, data.cost_data
    read, read_combined = set(data.features["port"]), set(data.features["port_combined"])
    limits, topology = request["limits"], request["topology"]
    cap = min(int(limits["max_instances"]), params["hard_max_instances"])
    profile = "standard" if "standard" in limits["profiles"] else limits["profiles"][0]
    combined = topology["kind"] == "combined"
    synthesis = topology.get("synthesis") if combined else None
    chars = {o["transfer_key"]: int(o["size"]["chars"]) for o in request["outputs"]}
    transfers = []
    for out in request["outputs"]:
        key = out["transfer_key"]
        signals, extra = agreement_signals(out, data), escalations(out)
        reviews = _reviews(signals, extra, cap, params)
        reasons = set(signals) | set(extra) | {"profile_standard" if profile == "standard" else "profile_fast", "cost_cheapest"}
        features = set(read)
        entry: dict[str, Any] = {"transfer_key": key, "profile": profile, "tier": TIER, "sources": [], "context": None}
        if key == synthesis:
            sources = list(topology["sources"])
            reasons.add("topology_combined")
            features |= read_combined
            entry.update(method="N_FOLD", reviews=reviews, parts=1, instances=reviews, sources=sources,
                         context={"scope": "request", "contents": "validated_outcomes", "max_bytes": params["context_max_bytes"],
                                  "discard": "after_request"},
                         estimated_cost=_cost(reviews, chars[key] + sum(chars.get(s, 0) for s in sources), cost))
        else:
            parts = 1
            if reviews == 1 and int(out["size"]["words"]) > params["split_words"]:
                parts = min(-(-int(out["size"]["words"]) // params["split_words"]), params["max_parts"], cap)
            if parts >= 2:
                method = "SPLIT"
                reasons.add("volume_split")
            else:
                parts = 1
                method = "DUPLICATE" if reviews >= 2 else "IN_DEPTH"
            if combined:
                reasons.add("topology_source")
                features |= read_combined
            if not signals and not extra:
                reasons.add("baseline_single_review")
            instances = reviews * parts
            entry.update(method=method, reviews=reviews, parts=parts, instances=instances,
                         estimated_cost=_cost(instances, -(-chars[key] // parts), cost))
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
