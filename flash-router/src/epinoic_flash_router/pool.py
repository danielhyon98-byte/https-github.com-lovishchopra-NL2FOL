"""The flash router's pool planner: one overseer-pool batch (``epinoic.integration.pool-routing-request.v1``) in, one
pool routing plan (``epinoic.integration.pool-routing-plan.v1``) out, by the pool rules P1 to P8 of the current rules file.

This is the overseer pool's planning decision, moved out of the overseer into this separate agent (architecture step
2c): which instances review which dossiers, and which dossiers are reviewed by independent duplicates. With the released
data it is the decision the overseer's own planner made before the move, plan for plan, for every batch without a
combined answer (the overseer's recorded-plans test holds it to every recorded transfer). Its thresholds and its batch
size are the data's ``pool`` parameters:

* ``escalated_reviewers``: the distinct instances an escalated dossier goes to (DUPLICATE); a dossier is escalated when
  its task carries a repeated fault or a risk signal, or when the overseer's escalation advisor escalated it;
* ``baseline_reviewers``: the instances any other dossier goes to (IN_DEPTH);
* ``record_weight``: the review units a dossier weighs when its task carries risk records only;
* ``batch_size``: the review units one instance takes before the batch is spread over more instances; ``null`` (as
  released) takes the pool's own per-instance quota, an integer is the router's own batch size (an instance over the
  pool's quota is still disclosed, ``over_quota``);
* ``source_reviewers`` and ``merged_reviewers`` (rules/3, pool port 1.2): the instances each source of a combined answer
  and its merged review go to when their own transfers carry no repeated fault and no risk signal (else
  ``escalated_reviewers``).

**Pool port 1.2** (architecture step 3) adds two things, both planned by the flash decision maker
(:mod:`epinoic_flash_router.decision`): every dossier's entry carries its **decision** (the method, the features it read,
the candidates it priced from the cost data and its reasons, rule D7), and a **combined answer** (a dossier whose
synthesis combines N >= 2 specialists' answers; the request names its N sources and its merged part) is planned
**N_FOLD** (rule P8, D6): each source by its own instances in parallel (no instance reviews two of its sources while the
plan has instances to spare), then one merged review of the combinator's output with a request-scoped temporary context
of the validated source outcomes. A pool port 1.1 request carries no combined dossier and gets exactly the plan of rules
P1 to P7, with no decision record.

The plan is advice. The overseer validates it as untrusted data and runs it only when it is at or above the overseer's
own minimum-oversight floor; a re-tuned file that plans less (fewer reviewers for an escalated dossier, a combined answer
not N_FOLD) is refused there and the floor plan runs. Before anything is planned the request is checked
(:func:`~epinoic_flash_router.contract.check_pool_request`): one this router does not read is refused with
:class:`~epinoic_flash_router.contract.RequestError` naming the member and the rule, and what planning a request that
passes raises is a fault of the router's own code. Pure and deterministic: no network, no clock, no randomness, no
file read; the same request and the same data give the same plan.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Optional

from .contract import RequestError, check_pool_request
from .decision import decide, n_fold_decision
from .rules import DEFAULT, DataSet, canonical

__all__ = ["POOL_PLAN_SCHEMA", "POOL_PORT_VERSION", "POOL_PORT_VERSIONS", "pool_plan_for"]

POOL_PLAN_SCHEMA = "epinoic.integration.pool-routing-plan.v1"
#: The newest pool port version this router speaks (its pool hello names it when its data carry the decision maker).
POOL_PORT_VERSION = "1.2"
#: Every pool port version this router answers: a request names its own and gets a plan of that version.
POOL_PORT_VERSIONS = ("1.1", "1.2")
PROTOCOL = "epinoic.integration.v1"
#: The pool's hard maximum of instances, whatever its configuration says (the router port's HARD_MAX_INSTANCES).
HARD_MAX_INSTANCES = 64
_CONTEXT = {"scope": "request", "contents": "validated_outcomes", "discard": "after_request"}


def _escalated(item: Mapping[str, Any]) -> bool:
    return bool(item["repeated_faults"] or item["risk_signals"] or item.get("advised"))


def _part_escalated(part: Mapping[str, Any], item: Mapping[str, Any]) -> bool:
    """A part of a combined answer is escalated by its own transfers' repeated faults or risk signals, or by the advisor's
    escalation of the dossier (an escalation of the dossier escalates every part)."""
    return bool(part["repeated_faults"] or part["risk_signals"] or _escalated({"repeated_faults": 0, "risk_signals": [], "advised": item.get("advised")}))


def _agreement(escalated: bool, part: Mapping[str, Any], item: Mapping[str, Any]) -> list[str]:
    if not escalated:
        return []
    out = []
    if part["repeated_faults"] or part["risk_signals"]:
        out.append("agreement_risk")
    if item.get("advised"):
        out.append("agreement_advised")
    return out


def _features(f: Optional[Mapping[str, Any]]) -> tuple[Optional[int], bool, bool]:
    if f is None:
        return None, False, False
    return int(f["chars"]), bool(f["stem"]), int(f["translations"]) > 0


def _read(item: Mapping[str, Any]) -> dict:
    """What the decision read of one dossier: the request item's own features, echoed (the overseer checks the echo)."""
    return {"repeated_faults": item["repeated_faults"], "risk_signals": list(item["risk_signals"]), "risk_records": list(item["risk_records"]),
            "advised": bool(item.get("advised")), "features": item.get("features"), "sources": len(item.get("sources") or [])}


def pool_plan_for(request: Mapping[str, Any], *, identity: Mapping[str, str], data: Optional[DataSet] = None) -> dict:
    """The pool plan for one batch (a parsed ``pool-routing-request.v1`` object), under this router's ``identity`` and
    ``data`` (the package's own data by default). A pool port 1.1 request gets a 1.1 plan (rules P1 to P7); a 1.2 request
    a 1.2 plan with every dossier's decision and N_FOLD for every combined answer, which needs the decision maker's data.
    :class:`RequestError` (a ``ValueError``) for a request this router does not read (``contract.check_pool_request``: a
    version it does not answer, 1.2 without the decision maker's data, a member the planner reads out of its type or
    range), before anything is planned: what planning a request that passes it raises is a fault of the router's own
    code."""
    data = DEFAULT if data is None else data
    # the request's canonical text, as UTF-8 (what its digest is taken of), once it is a request this router reads
    request_text = check_pool_request(request, versions=POOL_PORT_VERSIONS, decision=data.decision is not None)
    version = request["port_version"]
    if version not in POOL_PORT_VERSIONS:
        raise RequestError(f"port_version: this router reads pool port versions {', '.join(POOL_PORT_VERSIONS)}")
    v12 = version == "1.2"
    if v12 and data.decision is None:
        raise RequestError("pool port 1.2 needs the flash decision maker's data (rules/3): this data directory plans pool port 1.1 only")
    pool = data.pool
    reviewers, baseline, weight = int(pool["escalated_reviewers"]), int(pool["baseline_reviewers"]), int(pool["record_weight"])
    items = list(request["items"])
    limits = request["limits"]
    quota = int(limits["per_instance_quota"])
    batch = quota if pool.get("batch_size") is None else int(pool["batch_size"])
    maximum = min(int(limits["max_instances"]), HARD_MAX_INSTANCES)
    profile = "standard" if "standard" in limits["profiles"] else limits["profiles"][0]
    combined = [it for it in items if v12 and it.get("sources")]
    source_reviewers = int(pool.get("source_reviewers", baseline))
    merged_reviewers = int(pool.get("merged_reviewers", baseline))

    def part_reviews(part: Mapping[str, Any], item: Mapping[str, Any], base: int) -> int:
        return reviewers if _part_escalated(part, item) else base

    layout: dict[str, tuple[list[int], int]] = {}  # combined item id -> (reviews per source, merged reviews)
    for it in combined:
        layout[it["item_id"]] = ([part_reviews(s, it, source_reviewers) for s in it["sources"]], part_reviews(it["merged"], it, merged_reviewers))

    repeated = [it for it in items if it["repeated_faults"]]
    risky = [it for it in items if it["risk_signals"] and not it["repeated_faults"]]
    advised = [it for it in items if it.get("advised") and not it["repeated_faults"] and not it["risk_signals"]]
    weighted = [it for it in items if it["risk_records"] and not _escalated(it)]

    def units(it: Mapping[str, Any]) -> int:
        if it["item_id"] in layout:
            per_source, merged = layout[it["item_id"]]
            return sum(per_source) + merged
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
        if combined:
            # P8: a combined answer's source reviews run in parallel, each on instances of its own, then its merged review
            for per_source, merged in layout.values():
                needed = max(needed, sum(per_source), merged)
            reasons.append({"code": "pool_n_fold", "count": len(combined), "sources": sum(len(it["sources"]) for it in combined)})
    count = min(needed, maximum)
    capped = needed > maximum
    if capped:
        reasons.append({"code": "pool_capped", "maximum": maximum, "needed": needed})
    loads = [0] * count
    chosen_for: dict[str, list[int]] = {}
    sources_for: dict[str, list[list[int]]] = {}
    merged_for: dict[str, list[int]] = {}

    def least_loaded(want: int, among: list[int]) -> list[int]:
        return sorted(among, key=lambda a: (loads[a], a))[:want]

    for it in [*repeated, *risky, *advised, *[x for x in items if not _escalated(x)]]:
        iid = it["item_id"]
        if iid in layout:
            per_source, merged = layout[iid]
            used: set[int] = set()
            picked: list[list[int]] = []
            for want in per_source:
                free = [a for a in range(count) if a not in used]
                chosen = least_loaded(want, free if len(free) >= want else list(range(count)))
                for a in chosen:
                    loads[a] += 1
                used.update(chosen)
                picked.append(sorted(chosen))
            m = least_loaded(merged, list(range(count)))
            for a in m:
                loads[a] += 1
            sources_for[iid], merged_for[iid] = picked, sorted(m)
            chosen_for[iid] = sorted(set(m) | {a for s in picked for a in s})
            continue
        want = reviewers if _escalated(it) else baseline
        chosen = least_loaded(want, list(range(count)))
        for a in chosen:
            loads[a] += 1 if _escalated(it) else units(it)
        chosen_for[iid] = sorted(chosen)
    over = any(v > quota for v in loads)
    if over:
        reasons.append({"code": "pool_over_quota", "load": max(loads), "quota": quota})
    assignments = []
    for it in items:
        iid = it["item_id"]
        if iid in layout:
            entry: dict[str, Any] = {"item_id": iid, "method": "N_FOLD", "instances": [a + 1 for a in merged_for[iid]],
                                     "sources": [{"method": "DUPLICATE" if len(s) >= 2 else "IN_DEPTH", "instances": [a + 1 for a in s]} for s in sources_for[iid]],
                                     "context": {**_CONTEXT, "max_bytes": int(data.parameters["context_max_bytes"])}}
        else:
            entry = {"item_id": iid, "method": "DUPLICATE" if len(chosen_for[iid]) >= 2 else "IN_DEPTH", "instances": [a + 1 for a in chosen_for[iid]]}
            if v12:
                entry.update(sources=[], context=None)
        if v12:
            entry["decision"] = _decision(it, entry, layout.get(iid), data=data, maximum=maximum)
        assignments.append(entry)
    request_sha256 = hashlib.sha256(request_text).hexdigest()
    plan_id = "pool-plan-" + hashlib.sha256(canonical({"request_sha256": request_sha256, "router": dict(identity)}).encode("utf-8")).hexdigest()[:32]
    estimated: Optional[dict] = None
    if v12 and assignments:
        costs = [a["decision"]["estimated_cost"] for a in assignments]
        if all(c["tokens"] is not None for c in costs):
            estimated = {"tokens": sum(c["tokens"] for c in costs), "seconds": sum(c["seconds"] for c in costs)}
    return {"schema": POOL_PLAN_SCHEMA, "protocol": PROTOCOL, "port_version": version, "origin": "router", "plan_id": plan_id,
            "request_sha256": request_sha256, "router": dict(identity), "profile": profile, "instances": count, "assignments": assignments,
            "loads": loads, "review_units": total, "needed_instances": needed, "capped": capped, "over_quota": over, "reasons": reasons,
            "estimated_cost": estimated}


def _decision(item: Mapping[str, Any], entry: Mapping[str, Any], layout: Optional[tuple[list[int], int]], *, data: DataSet, maximum: int) -> dict:
    """The flash decision maker's record for one dossier (rules D1 to D7): the dossier examined whole by the reviews its
    risk calls for, or, for a combined answer, N_FOLD with the decision of each source and of the merged review. The pool
    does not divide one dossier (no SPLIT): a dossier no instance can read whole is disclosed (over_budget)."""
    cost, max_parts = data.cost_data, int(data.parameters["max_parts"])
    methods = ("IN_DEPTH", "DUPLICATE")
    reviewers, baseline = int(data.pool["escalated_reviewers"]), int(data.pool["baseline_reviewers"])
    chars, stem, translations = _features(item.get("features"))
    escalated = _escalated(item)
    whole = decide(reviews=reviewers if escalated else baseline, chars=chars, stem=stem, translations=translations, cost=cost, cap=maximum,
                   max_parts=max_parts, methods=methods, reasons=_agreement(escalated, item, item))
    parts: list[dict] = []
    if layout is None:
        record = whole
    else:
        per_source, merged_reviews = layout
        decided = []
        for k, (src, want) in enumerate(zip(item["sources"], per_source), start=1):
            c, s, t = _features(src.get("features"))
            d = decide(reviews=want, chars=c, stem=s, translations=t, cost=cost, cap=maximum, max_parts=max_parts, methods=methods,
                       reasons=_agreement(want >= 2, src, item))
            decided.append(d)
            parts.append({"part": "source", "index": k, "reviews": d["reviews"], "need_tokens": d["need_tokens"], "fits": d["fits"], "reasons": d["reasons"]})
        m = item["merged"]
        c, s, t = _features(m.get("features"))
        md = decide(reviews=merged_reviews, chars=c, stem=s, translations=t, cost=cost, cap=maximum, max_parts=max_parts, methods=methods,
                    reasons=_agreement(merged_reviews >= 2, m, item))
        parts.append({"part": "merged", "index": 0, "reviews": md["reviews"], "need_tokens": md["need_tokens"], "fits": md["fits"], "reasons": md["reasons"]})
        record = n_fold_decision(sources=decided, merged=md, whole=whole, cost=cost, reasons=_agreement(escalated, item, item))
    approach = "in_depth" if entry["method"] == "IN_DEPTH" else "duplication"
    return {"approach": approach, "method": entry["method"], "reviews": len(entry["instances"]), "calls": int(record["calls"]),
            "read": _read(item), "need_tokens": record["need_tokens"], "budget_tokens": record["budget_tokens"], "fits": record["fits"],
            "reasons": record["reasons"], "candidates": [{k: c[k] for k in ("method", "reviews", "calls", "tokens", "seconds", "keeps_accuracy", "why")}
                                                         for c in record["candidates"]],
            "parts": parts, "estimated_cost": record["estimated_cost"]}
