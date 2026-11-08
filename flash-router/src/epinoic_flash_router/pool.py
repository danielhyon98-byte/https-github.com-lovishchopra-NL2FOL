"""The flash router's pool planner: one overseer-pool batch (``epinoic.integration.pool-routing-request.v1``) in, one
pool routing plan (``epinoic.integration.pool-routing-plan.v1``) out, by the pool rules P1 to P7 of the current rules file.

This is the overseer pool's planning decision, moved out of the overseer into this separate agent: which instances
review which dossiers, and which dossiers are reviewed by independent duplicates. With the released data (rules/2) it is
the decision the overseer's own planner made before the move, plan for plan (the overseer's recorded-plans test holds
it to every recorded transfer). Its thresholds and its batch size are the data's ``pool`` parameters:

* ``escalated_reviewers``: the distinct instances an escalated dossier goes to (DUPLICATE); a dossier is escalated when
  its task carries a repeated fault or a risk signal, or when the overseer's escalation advisor escalated it;
* ``baseline_reviewers``: the instances any other dossier goes to (IN_DEPTH);
* ``record_weight``: the review units a dossier weighs when its task carries risk records only;
* ``batch_size``: the review units one instance takes before the batch is spread over more instances; ``null`` (as
  released) takes the pool's own per-instance quota, an integer is the router's own batch size (an instance over the
  pool's quota is still disclosed, ``over_quota``).

The plan is advice. The overseer validates it as untrusted data and runs it only when it is at or above the overseer's
own minimum-oversight floor; a re-tuned file that plans less (fewer reviewers for an escalated dossier) is refused there
and the floor plan runs. Pure and deterministic: no network, no clock, no randomness, no file read; the same request and
the same data give the same plan.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Optional

from .rules import DEFAULT, DataSet, canonical

__all__ = ["POOL_PLAN_SCHEMA", "POOL_PORT_VERSION", "pool_plan_for"]

POOL_PLAN_SCHEMA = "epinoic.integration.pool-routing-plan.v1"
POOL_PORT_VERSION = "1.1"
PROTOCOL = "epinoic.integration.v1"
#: The pool's hard maximum of instances, whatever its configuration says (the router port's HARD_MAX_INSTANCES).
HARD_MAX_INSTANCES = 64


def _escalated(item: Mapping[str, Any]) -> bool:
    return bool(item["repeated_faults"] or item["risk_signals"] or item.get("advised"))


def pool_plan_for(request: Mapping[str, Any], *, identity: Mapping[str, str], data: Optional[DataSet] = None) -> dict:
    """The pool plan for one batch (a parsed ``pool-routing-request.v1`` object), under this router's ``identity`` and
    ``data`` (the package's own data by default)."""
    data = DEFAULT if data is None else data
    pool = data.pool
    reviewers, baseline, weight = int(pool["escalated_reviewers"]), int(pool["baseline_reviewers"]), int(pool["record_weight"])
    items = list(request["items"])
    limits = request["limits"]
    quota = int(limits["per_instance_quota"])
    batch = quota if pool.get("batch_size") is None else int(pool["batch_size"])
    maximum = min(int(limits["max_instances"]), HARD_MAX_INSTANCES)
    profile = "standard" if "standard" in limits["profiles"] else limits["profiles"][0]

    repeated = [it for it in items if it["repeated_faults"]]
    risky = [it for it in items if it["risk_signals"] and not it["repeated_faults"]]
    advised = [it for it in items if it.get("advised") and not it["repeated_faults"] and not it["risk_signals"]]
    weighted = [it for it in items if it["risk_records"] and not _escalated(it)]

    def units(it: Mapping[str, Any]) -> int:
        return reviewers if _escalated(it) else (weight if it["risk_records"] else 1)

    total = sum(units(it) for it in items)
    reasons: list[dict] = []
    if not items:
        needed = 0
        reasons.append({"code": "pool_empty"})
    else:
        needed = 1
        reasons.append({"code": "pool_baseline"})
        by_batch = -(-total // batch)
        if by_batch > 1:
            needed = by_batch
            reasons.append({"code": "pool_volume", "units": total, "quota": batch, "instances": by_batch})
        if repeated:
            needed = max(needed, reviewers)
            reasons.append({"code": "pool_repeated_faults", "count": len(repeated), "reviewers": reviewers})
        if risky:
            needed = max(needed, reviewers)
            reasons.append({"code": "pool_risk_signals", "count": len(risky), "classes": sorted({c for it in risky for c in it["risk_signals"]}),
                            "reviewers": reviewers})
        if advised:
            needed = max(needed, reviewers)
            reasons.append({"code": "pool_advised", "count": len(advised), "reviewers": reviewers})
        if weighted:
            reasons.append({"code": "pool_risk_records", "count": len(weighted), "classes": sorted({c for it in weighted for c in it["risk_records"]}),
                            "weight": weight})
    count = min(needed, maximum)
    capped = needed > maximum
    if capped:
        reasons.append({"code": "pool_capped", "maximum": maximum, "needed": needed})
    loads = [0] * count
    chosen_for: dict[str, list[int]] = {}
    for it in [*repeated, *risky, *advised, *[x for x in items if not _escalated(x)]]:
        want = reviewers if _escalated(it) else baseline
        chosen = sorted(range(count), key=lambda a: (loads[a], a))[:want]
        for a in chosen:
            loads[a] += 1 if _escalated(it) else units(it)
        chosen_for[it["item_id"]] = sorted(chosen)
    over = any(v > quota for v in loads)
    if over:
        reasons.append({"code": "pool_over_quota", "load": max(loads), "quota": quota})
    assignments = [{"item_id": it["item_id"], "method": "DUPLICATE" if len(chosen_for[it["item_id"]]) >= 2 else "IN_DEPTH",
                    "instances": [a + 1 for a in chosen_for[it["item_id"]]]} for it in items]
    request_sha256 = hashlib.sha256(canonical(request).encode("utf-8")).hexdigest()
    plan_id = "pool-plan-" + hashlib.sha256(canonical({"request_sha256": request_sha256, "router": dict(identity)}).encode("utf-8")).hexdigest()[:32]
    return {"schema": POOL_PLAN_SCHEMA, "protocol": PROTOCOL, "port_version": POOL_PORT_VERSION, "origin": "router", "plan_id": plan_id,
            "request_sha256": request_sha256, "router": dict(identity), "profile": profile, "instances": count, "assignments": assignments,
            "loads": loads, "review_units": total, "needed_instances": needed, "capped": capped, "over_quota": over, "reasons": reasons,
            "estimated_cost": None}
