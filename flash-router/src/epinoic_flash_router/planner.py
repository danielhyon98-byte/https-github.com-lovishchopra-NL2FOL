"""The flash router's port planner: a routing request (``epinoic.integration.routing-request.v1``, features only) in, one
routing plan (``epinoic.integration.routing-plan.v1``) out, by the port rules of the current rules file
(:mod:`epinoic_flash_router.rules`, port rules 1 to 7).

Since rules/3 (0.3.0) the method of every output is the flash decision maker's (:mod:`epinoic_flash_router.decision`,
rules D1 to D7): one instance examining the whole output (``IN_DEPTH``), or the duplication method (``DUPLICATE`` where
risk calls for agreement, ``SPLIT`` parts of an output that does not fit one instance's budget), the cheapest that keeps
accuracy by the recorded cost data. The rules/2 documents (0.2.0, kept at their digests) are still planned by rules/2's
own rule 4 (an output longer than ``split_words`` words read by one review is divided into parts), so a data directory
holding the released 0.2.0 files plans exactly as 0.2.0 did.

Since rules/4 (0.4.0) a combined answer's synthesis is decided by the decision maker too, as the pool decides one (port
rule 5, D4 and D6): its merged review reads the synthesis and every source whole (port rule 7) and is never divided (an
N_FOLD review is one part, one instance per review), so it is fit-checked like any response its caller cannot divide and,
when one instance cannot read it whole, recorded ``over_budget``, never shortened; its N_FOLD record carries each source's
own decision (the one its entry is planned by) and the merged review's. :func:`transfer_decisions` returns every
transfer's record (D7). The service's plan (router port 1.0) carries each transfer's method, reviews, parts, reasons,
features used and estimated cost in the port's closed vocabulary, which has no code for ``over_budget`` (nor for
``split_to_fit``): until the router port adds one, the record is where a transfer that does not fit is disclosed, and
the plan's numbers are the record's (the merged review's estimated cost is its reviews times one call reading it whole).

Before anything is planned the request is checked (:func:`~epinoic_flash_router.contract.check_routing_request`): one it
does not read is refused with :class:`~epinoic_flash_router.contract.RequestError` naming the member and the rule, and
what planning a request that passes raises is a fault of the router's own code, never of the request.

Pure and deterministic: no network, no clock, no randomness, no model call, no file read (the data were read once, when
they were loaded); the same request and the same data give the same plan. It reads the request's features only (the
request never carries an answer, a claim text or an overseer finding) and writes closed vocabularies, the request's own
transfer keys and digests, and the router's identity. Its numbers, the agreement signals it reads, the features it
records and its cost estimates all come from the data, so a re-tuned data file changes the plan without any change here.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Optional

from .contract import RequestError, check_routing_request
from .decision import decide, n_fold_decision, port_dossier_chars
from .rules import DEFAULT, DataSet, canonical

__all__ = ["REASON_ORDER", "FEATURE_ORDER", "PORT_METHODS", "MERGED_METHODS", "agreement_signals", "escalations", "transfer_decisions",
           "plan_for"]

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
#: The methods the port can run for one output (port rule 4): it may divide an output that does not fit (SPLIT).
PORT_METHODS = ("IN_DEPTH", "DUPLICATE", "SPLIT")
#: The methods of a combined answer's merged review (port rule 5): never divided, since an N_FOLD review is one part with
#: one instance per review, so a merged review one instance cannot read whole is disclosed (over_budget), never shortened.
MERGED_METHODS = ("IN_DEPTH", "DUPLICATE")


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
    """Port rule 7 of rules/2 (0.2.0's cost model)."""
    per_token = cost["chars_per_token"]
    tokens = cost["review_tokens_base"] + -(-chars_each // per_token)
    return {"tokens": instances * tokens, "seconds": instances * cost["seconds_per_instance"]}


def _ordered(names: set[str], order: tuple[str, ...]) -> list[str]:
    return [n for n in order if n in names]


def _agreement(signals: list[str], extra: list[str]) -> list[str]:
    """The decision record's agreement reasons (D3, D7): a floor signal, an escalation this router adds, or both."""
    return (["agreement_risk"] if signals else []) + (["agreement_escalation"] if extra else [])


def _transfer_decision(out: Mapping[str, Any], *, reviews: int, request: Mapping[str, Any], cap: int, data: DataSet,
                       reasons: tuple[str, ...] | list[str] = ()) -> dict:
    """The flash decision maker for one output of the routing request (rules/3 and rules/4, port rule 4): its dossier
    estimated from its size, the request's supplied texts and its translated claims; the composition from STEM and
    translations."""
    cost = data.cost_data
    supplied = sum(int(t["chars"]) for t in request["request"].get("supplied_texts", []))
    translated = int(out["claims"]["translated"])
    chars = port_dossier_chars(int(out["size"]["chars"]), supplied, translated, cost)
    return decide(reviews=reviews, chars=chars, stem=bool(out["stem"]), translations=translated > 0, cost=cost, cap=cap,
                  max_parts=int(data.parameters["max_parts"]), methods=PORT_METHODS, reasons=reasons)


def _part(part: str, index: int, key: str, d: Mapping[str, Any]) -> dict:
    return {"part": part, "index": index, "transfer_key": key, "method": d["method"], "reviews": d["reviews"], "parts": d["parts"],
            "need_tokens": d["need_tokens"], "fits": d["fits"], "reasons": list(d["reasons"])}


def _n_fold_decision(out: Mapping[str, Any], *, reviews: int, reasons: list[str], request: Mapping[str, Any], cap: int, data: DataSet,
                     sources_decided: Mapping[str, Mapping[str, Any]], chars: Mapping[str, int], by_key: Mapping[str, Mapping[str, Any]]) -> dict:
    """The flash decision maker for a combined answer's synthesis (port rules 5 and 7, D4 and D6), as the pool decides one:
    its merged review reads the synthesis and every source whole and is never divided, so it is decided among
    :data:`MERGED_METHODS` with the reviews port rule 3 gives the synthesis, fit-checked (``over_budget`` when one instance
    cannot read it whole); the N_FOLD record (:func:`~epinoic_flash_router.decision.n_fold_decision`) carries each source's
    own decision (``sources_decided``, the decisions their entries are planned by) and the merged review's, the whole
    combined answer's candidates priced and refused (``combined_needs_n_fold``), and ``part_decisions``: each part's
    method, reviews, need, fit and reasons, the sources in the topology's order, then the merged review. ``chars`` and
    ``by_key`` are the request's outputs by transfer key (their sizes, their features)."""
    cost = data.cost_data
    key, sources = out["transfer_key"], list(request["topology"]["sources"])
    supplied = sum(int(t["chars"]) for t in request["request"].get("supplied_texts", []))
    translated = int(out["claims"]["translated"]) + sum(int(by_key[s]["claims"]["translated"]) for s in sources if s in by_key)
    read_chars = port_dossier_chars(chars[key] + sum(chars.get(s, 0) for s in sources), supplied, translated, cost)
    stem = bool(out["stem"]) or any(bool(by_key[s]["stem"]) for s in sources if s in by_key)
    common: dict[str, Any] = dict(reviews=reviews, chars=read_chars, stem=stem, translations=translated > 0, cost=cost, cap=cap,
                                  max_parts=int(data.parameters["max_parts"]), reasons=reasons)
    merged = decide(methods=MERGED_METHODS, **common)
    whole = decide(methods=PORT_METHODS, **common)
    held = [s for s in sources if s in sources_decided]
    record = n_fold_decision(sources=[sources_decided[s] for s in held], merged=merged, whole=whole, cost=cost, reasons=reasons)
    record["part_decisions"] = [_part("source", k, s, sources_decided[s]) for k, s in enumerate(held, start=1)] + [_part("merged", 0, key, merged)]
    return record


def _readings(request: Mapping[str, Any], data: DataSet, cap: int) -> list[tuple[list[str], list[str], int]]:
    """Per output, in the request's order: its agreement signals (port rule 2), this router's escalations and the reviews
    port rule 3 gives it. A request that names one transfer key twice is refused (:class:`RequestError`, a
    ``ValueError``; :func:`~epinoic_flash_router.contract.check_routing_request` refuses it first), as the router port
    refuses it (``check_request``): every transfer gets exactly one entry (port rule 1), and a combined answer's N_FOLD
    decision is made once, for its one synthesis, never once for each repetition of its key."""
    keys = [o["transfer_key"] for o in request["outputs"]]
    if len(set(keys)) != len(keys):
        raise RequestError("the routing request names one transfer key twice: every transfer is one output of the request")
    params = data.parameters
    out = []
    for o in request["outputs"]:
        signals, extra = agreement_signals(o, data), escalations(o)
        out.append((signals, extra, _reviews(signals, extra, cap, params)))
    return out


def _decisions(request: Mapping[str, Any], data: DataSet, cap: int, readings: list[tuple[list[str], list[str], int]]) -> list[dict]:
    """Every output's decision record, in the request's order: the sources and single outputs first (port rule 4), then
    the synthesis of a combined answer from its sources' records (port rule 5)."""
    topology = request["topology"]
    synthesis = topology.get("synthesis") if topology["kind"] == "combined" else None
    outputs = list(request["outputs"])
    records: list[dict] = [{} for _ in outputs]  # every slot is filled below: an output is the synthesis or it is not
    decided: dict[str, dict] = {}
    for i, (o, (signals, extra, reviews)) in enumerate(zip(outputs, readings)):
        if o["transfer_key"] != synthesis:
            records[i] = d = _transfer_decision(o, reviews=reviews, request=request, cap=cap, data=data, reasons=_agreement(signals, extra))
            d["transfer_key"] = o["transfer_key"]
            decided[o["transfer_key"]] = d
    if synthesis is not None:
        chars = {o["transfer_key"]: int(o["size"]["chars"]) for o in outputs}
        by_key = {o["transfer_key"]: o for o in outputs}
        for i, (o, (signals, extra, reviews)) in enumerate(zip(outputs, readings)):
            if o["transfer_key"] == synthesis:
                records[i] = d = _n_fold_decision(o, reviews=reviews, reasons=_agreement(signals, extra), request=request, cap=cap, data=data,
                                                  sources_decided=decided, chars=chars, by_key=by_key)
                d["transfer_key"] = o["transfer_key"]
    return records


def transfer_decisions(request: Mapping[str, Any], *, data: Optional[DataSet] = None) -> list[dict]:
    """The flash decision maker's record (D7) for every transfer of one routing request (a parsed ``routing-request.v1``
    object), in the request's order, each naming its ``transfer_key``: its method, reviews and parts, every candidate it
    priced by the cost data (whether it keeps accuracy, and why it was or was not chosen), its need, fit and reasons and its
    estimated cost, closed codes and integers only (:func:`~epinoic_flash_router.decision.decide`; the features it read are
    the request's, as the plan's ``features_used`` names them); for a combined answer's synthesis the N_FOLD record
    (D6) with each part's decision, the merged review's fit included. The plan (:func:`plan_for`) is built from these
    records; router port 1.0 has no reason code for ``over_budget`` or ``split_to_fit``, so this record is where a
    transfer one instance cannot read whole is disclosed until the port carries it. Pure and deterministic, like the plan.
    ``ValueError`` for a data directory without the decision maker (rules/2 plans by its own rule 4);
    :class:`RequestError` (a ``ValueError``) for a request this router does not read (``contract.check_routing_request``)."""
    data = DEFAULT if data is None else data
    if data.decision is None:
        raise ValueError("the decision records need the flash decision maker's data (rules/3 or later): this data directory holds rules/2")
    check_routing_request(request)
    cap = min(int(request["limits"]["max_instances"]), data.parameters["hard_max_instances"])
    return _decisions(request, data, cap, _readings(request, data, cap))


def plan_for(request: Mapping[str, Any], *, identity: Mapping[str, str], data: Optional[DataSet] = None) -> dict:
    """The plan for one routing request (a parsed ``routing-request.v1`` object), under this router's ``identity`` and
    ``data`` (the package's own data by default). :class:`RequestError` (a ``ValueError``) for a request this router does
    not read (``contract.check_routing_request``), before anything is planned: what planning a request that passes it
    raises is a fault of the router's own code."""
    data = DEFAULT if data is None else data
    request_text = check_routing_request(request)  # the request's canonical text, as UTF-8: what its digest is taken of
    params, cost = data.parameters, data.cost_data
    decided = data.decision is not None  # rules/3 and later: the flash decision maker; rules/2: its own rule 4 (split_words)
    read, read_combined = set(data.features["port"]), set(data.features["port_combined"])
    limits, topology = request["limits"], request["topology"]
    cap = min(int(limits["max_instances"]), params["hard_max_instances"])
    profile = "standard" if "standard" in limits["profiles"] else limits["profiles"][0]
    combined = topology["kind"] == "combined"
    synthesis = topology.get("synthesis") if combined else None
    chars = {o["transfer_key"]: int(o["size"]["chars"]) for o in request["outputs"]}
    readings = _readings(request, data, cap)
    records = _decisions(request, data, cap, readings) if decided else None
    transfers = []
    for i, (out, (signals, extra, reviews)) in enumerate(zip(request["outputs"], readings)):
        key = out["transfer_key"]
        reasons = set(signals) | set(extra) | {"profile_standard" if profile == "standard" else "profile_fast", "cost_cheapest"}
        features = set(read)
        entry: dict[str, Any] = {"transfer_key": key, "profile": profile, "tier": TIER, "sources": [], "context": None}
        if key == synthesis:
            sources = list(topology["sources"])
            reasons.add("topology_combined")
            features |= read_combined
            if records is not None:  # the merged review: each call reads the synthesis and every source whole (port rule 7), fit-checked (D4)
                merged = records[i]["part_decisions"][-1]
                estimated = {"tokens": reviews * int(merged["need_tokens"]), "seconds": reviews * int(cost["seconds_per_call"])}
            else:
                estimated = _cost(reviews, chars[key] + sum(chars.get(s, 0) for s in sources), cost)
            entry.update(method="N_FOLD", reviews=reviews, parts=1, instances=reviews, sources=sources,
                         context={"scope": "request", "contents": "validated_outcomes", "max_bytes": params["context_max_bytes"],
                                  "discard": "after_request"},
                         estimated_cost=estimated)
        else:
            if records is not None:
                d = records[i]
                method, reviews, parts = d["method"], d["reviews"], d["parts"]
                estimated = {"tokens": int(d["estimated_cost"]["tokens"] or 0), "seconds": int(d["estimated_cost"]["seconds"])}
            else:
                parts = 1
                if reviews == 1 and int(out["size"]["words"]) > params["split_words"]:
                    parts = min(-(-int(out["size"]["words"]) // params["split_words"]), params["max_parts"], cap)
                if parts >= 2:
                    method = "SPLIT"
                else:
                    parts = 1
                    method = "DUPLICATE" if reviews >= 2 else "IN_DEPTH"
                estimated = _cost(reviews * parts, -(-chars[key] // parts), cost)
            if parts >= 2:
                reasons.add("volume_split")
            if combined:
                reasons.add("topology_source")
                features |= read_combined
            if not signals and not extra:
                reasons.add("baseline_single_review")
            instances = reviews * parts
            entry.update(method=method, reviews=reviews, parts=parts, instances=instances, estimated_cost=estimated)
        entry["reasons"] = _ordered(reasons, REASON_ORDER)
        entry["features_used"] = _ordered(features, FEATURE_ORDER)
        transfers.append(entry)
    request_sha256 = hashlib.sha256(request_text).hexdigest()
    totals = {"instances": sum(t["instances"] for t in transfers),
              "estimated_cost": {"tokens": sum(t["estimated_cost"]["tokens"] for t in transfers),
                                 "seconds": sum(t["estimated_cost"]["seconds"] for t in transfers)}}
    plan_id = "plan-" + hashlib.sha256(canonical({"request_sha256": request_sha256, "router": dict(identity)}).encode("utf-8")).hexdigest()[:32]
    return {"schema": PLAN_SCHEMA, "protocol": PROTOCOL, "port_version": PORT_VERSION, "origin": "router", "plan_id": plan_id,
            "ids": {"task_id": request["ids"]["task_id"], "request_id": request["ids"]["request_id"]}, "request_sha256": request_sha256,
            "router": dict(identity), "transfers": transfers, "totals": totals}
