"""The overseer pool's minimum-oversight floor (``minimum-oversight-floor/pool-2``), kept in the overseer.

The pool's planning decision (which instances review which dossiers of a batch, and which dossiers are reviewed by
independent duplicates) is made by the flash router, a separate agent in its own sub-project (``flash-router/``),
attached through the router port by capability (``epinoic_logic.integration.router_pool``). Agent self-reports and
routing advice are advisory, and accuracy must not depend on how the router is edited, so the overseer computes this
floor deterministically from the same risk signals the planner read before the decision moved to the router, and the
pool never runs less than it, whatever the router says (:data:`POOL_FLOOR_RULES`):

1. every dossier of the batch is reviewed by at least one instance;
2. a dossier is reviewed by at least two distinct instances (independent duplicate reviews, combined by the verdict
   combination) when its task carries a repeated fault or a risk signal, as ``emitted.risk_reading`` reads the journal at
   the effective severity: an error-level finding, a rejection, a contradiction between results or with a signed result,
   an encoding conflict, a withheld verdict, a named defect at warning or error, an unchecked source or a STEM method
   error at that severity, an argument diagnosis that did not finish; or when the overseer's escalation advisor (off by
   default) escalated it;
3. **a combined answer's floor is N_FOLD** (architecture step 3; ``pool-1`` stated it for later): a dossier whose
   synthesis combines N >= 2 specialists' delivered answers is reviewed in N + 1 parts, each specialist's own transfers
   by at least one instance of their own (two when that source's transfers carry a repeated fault or a risk signal, or
   the advisor escalated the dossier), then the merged review of the combinator's output by at least one instance (two
   under the same rule for the synthesis's own transfers), with the request-scoped temporary context of the source
   reviews' validated outcomes, bounded at the router port's 65,536 bytes (a plan with a smaller bound would cut confirmed
   source faults from the merged review); a plan that reviews a combined answer any other way is below the floor;
4. no plan has more instances than the pool's maximum (at most 64); every instance is built from the pool's one loaded
   pack and runs on the cheapest tier; the profile, the batch sizes and the parallelism are not part of the floor.

What lies above the floor is the router's choice, driven by cost and volume: how many instances a batch is spread over
(its batch sizes), the weight of risk records, extra duplicates, the profile. A router's plan that is out of contract
is refused with its ``KIT-RT`` code, one below the floor with ``KIT-RT-020``; either refusal is recorded in the plan's
:class:`PoolAdmission` and in the signed verdicts audit of every review that runs it, and the floor plan runs. With no
router attached the floor plan runs. Risk signals, and the advisor, only escalate. Every plan records who planned it:
the router's identity (name, version, the digests of its rules and of its cost data) or the floor's name and rules
digest, any refusal, and since pool port 1.2 the decision behind every dossier's review (:class:`PoolDecisionRecord`:
the router's flash decision with the features it read and its reasons, or the floor's own).

The floor plan (no router, or a refused one): one instance for a batch with no escalated or combined dossier, two when
a dossier is escalated, and for a combined answer at least as many as its source reviews need at once (its sources run
in parallel); escalated dossiers first (repeated faults, then risk signals, then the advisor's), each group in key order,
each to the two least-loaded instances, every other dossier to the least-loaded one (ties to the lower instance number);
a combined answer's sources in order, each to the least-loaded instances that review none of its earlier sources, then
its merged review to the least-loaded instances.
"""
from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from epinoic_logic.integration.canonical import sha256_text
from epinoic_logic.integration.protocol import RouterIdentity
from epinoic_logic.integration.router_pool import POOL_RISK_CLASSES

from .emitted import RISK_CLASSES

__all__ = [
    "POOL_FLOOR_NAME", "POOL_FLOOR_RULES", "POOL_FLOOR_RULES_SHA256", "FLOOR_ESCALATED_REVIEWERS", "FLOOR_DECISION_REASONS", "CONTEXT_MAX_BYTES",
    "PoolFloorRef", "PoolDecisionRecord", "PoolAdmission", "escalated", "floor_reviewers", "part_escalated", "floor_part_reviewers", "below_floor",
    "floor_decision", "render_reason", "admission_note", "decision_note",
]

if tuple(RISK_CLASSES) != tuple(POOL_RISK_CLASSES):  # pragma: no cover - a release defect
    raise ImportError("the overseer's risk classes are not the router port's pool vocabulary: the pool cannot speak the port")

POOL_FLOOR_NAME = "minimum-oversight-floor/pool-2"
#: Independent instances an escalated dossier (or an escalated part of a combined answer) reaches at the floor.
FLOOR_ESCALATED_REVIEWERS = 2
#: The temporary context's bound at the floor: the router port's ``CONTEXT_MAX_BYTES``.
CONTEXT_MAX_BYTES = 65536
POOL_FLOOR_RULES = (
    "minimum-oversight-floor/pool-2\n"
    "1. Every dossier of the batch is reviewed by at least one instance: a dossier a plan leaves out has no review, which is"
    " below the floor.\n"
    "2. A dossier is reviewed by at least 2 distinct instances when its task carries a repeated fault or a risk signal"
    " (emitted.risk_reading at the effective severity: an error-level finding, a rejection, a contradiction, an encoding"
    " conflict, a withheld verdict, a named defect at warning or error, an unchecked source or a STEM method error at that"
    " severity, an argument diagnosis that did not finish), or when the escalation advisor escalated it.\n"
    "3. A combined answer (a synthesis combining N >= 2 specialists' delivered answers) is reviewed N_FOLD: each source's own"
    " transfers by at least 1 instance, 2 when they carry a repeated fault or a risk signal or the advisor escalated the"
    " dossier; then the merged review of the combinator's output by at least 1 instance, 2 under the same rule for the"
    " synthesis's own transfers; with a request-scoped temporary context of the source reviews' validated outcomes bounded"
    " at 65536 bytes (a smaller bound would cut confirmed faults), discarded after the request. A plan that reviews a"
    " combined answer any other way is below the floor.\n"
    "4. No plan has more instances than the pool's maximum (at most 64); every instance is built from the pool's one loaded"
    " pack and runs on the cheapest tier; the profile, the batch sizes and the parallelism are not part of the floor.\n"
    "5. The floor plan: one instance, two when a dossier is escalated, and at least the source reviewers a combined answer"
    " needs at once; escalated dossiers first (repeated faults, risk signals, the advisor's), each group in key order, each"
    " to the two least-loaded instances, every other dossier to the least-loaded one, ties to the lower instance number; a"
    " combined answer's sources in order, each to the least-loaded instances that review none of its earlier sources, then"
    " its merged review to the least-loaded instances.\n"
)
POOL_FLOOR_RULES_SHA256 = sha256_text(POOL_FLOOR_RULES)
#: Why the floor reviews a dossier as it does (closed; the floor prices nothing, so its reasons are its rules').
FLOOR_DECISION_REASONS = ("floor_baseline", "floor_agreement", "floor_advised", "floor_n_fold")
_CODE = r"^KIT-RT-[0-9]{3}$"


class PoolFloorRef(BaseModel):
    """The floor a pool plan was held to: its name and the digest of its rules."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: Literal["minimum-oversight-floor/pool-2"] = POOL_FLOOR_NAME
    rules_sha256: str = Field(default=POOL_FLOOR_RULES_SHA256, pattern=r"^[0-9a-f]{64}$")


class PoolDecisionRecord(BaseModel):
    """The decision behind one dossier's review, as the plan's admission records it (rule D7 of the flash router): who
    decided (``router``: the flash decision maker, its record validated against the request; ``floor``: the overseer's
    floor plan), the approach (``in_depth``: one instance examines the whole response; ``duplication``: the work split
    across instances in parallel, duplicates where risk calls for agreement), the method, the reviews (of the merged
    review for an N_FOLD), the reasons (closed codes) and, for the router's decision, what it read, the reading need of
    one instance against the budget, the candidates it priced and its estimated cost (``router``: the record as the
    router port validated it, closed vocabularies and integers only)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str = Field(min_length=1, max_length=256)
    origin: Literal["router", "floor"]
    approach: Literal["in_depth", "duplication"]
    method: Literal["IN_DEPTH", "DUPLICATE", "N_FOLD"]
    reviews: int = Field(ge=1, le=64)
    reasons: tuple[str, ...] = Field(min_length=1, max_length=16)
    router: Optional[dict[str, Any]] = None


class PoolAdmission(BaseModel):
    """Who planned a pool plan and why it runs: ``origin`` ``router`` (the attached flash router's plan, in contract and at
    or above the floor) or ``floor`` (no router attached, or the router refused: ``refusal`` is its ``KIT-RT`` code);
    ``router`` the attached router's identity (also when its plan was refused); ``floor`` the floor it was held to;
    ``detail`` why, in the overseer's words (never the router's text); the profile its instances run; the digests that
    bind the router's plan to its request; the dossiers the escalation advisor escalated; the pool port version the plan
    was asked in (``None``: no router was asked); and the decision behind every dossier's review (``decisions``, in the
    plan's key order: the router's flash decisions when its plan runs, else the floor's)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    origin: Literal["router", "floor"]
    router: Optional[RouterIdentity] = None
    floor: PoolFloorRef = Field(default_factory=PoolFloorRef)
    refusal: Optional[str] = Field(default=None, pattern=_CODE)
    detail: str = Field(max_length=2000)
    profile: Literal["standard", "fast"] = "standard"
    request_sha256: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    router_plan_id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    advised: tuple[str, ...] = ()
    port_version: Optional[Literal["1.1", "1.2"]] = None
    decisions: tuple[PoolDecisionRecord, ...] = ()


def escalated(item: Any, advised: Iterable[str] = ()) -> bool:
    """Floor rule 2: a repeated fault, a risk signal, or the advisor's escalation."""
    return bool(item.repeated_faults or item.risk_signals or item.key in set(advised))


def floor_reviewers(item: Any, advised: Iterable[str] = ()) -> int:
    """The independent instances floor rules 1 and 2 ask for one dossier that is not a combined answer."""
    return FLOOR_ESCALATED_REVIEWERS if escalated(item, advised) else 1


def part_escalated(part: Any, item: Any, advised: Iterable[str] = ()) -> bool:
    """Floor rule 3: a part of a combined answer is escalated by its own transfers' repeated faults or risk signals, or by
    the advisor's escalation of the dossier."""
    return bool(part.repeated_faults or part.risk_signals or item.key in set(advised))


def floor_part_reviewers(part: Any, item: Any, advised: Iterable[str] = ()) -> int:
    """The independent instances floor rule 3 asks for one part (a source, or the merged review) of a combined answer."""
    return FLOOR_ESCALATED_REVIEWERS if part_escalated(part, item, advised) else 1


def below_floor(assignments: Mapping[str, Sequence[str]], items: Sequence[Any], advised: Iterable[str] = (),
                twofold: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    """``None`` when every dossier gets at least the floor's distinct instances (and every combined answer its N_FOLD,
    each part its own floor), else why not (the first dossier, in key order, that does not). ``twofold`` maps a combined
    answer's key to its N_FOLD layout (``sources``: the instances of each source; ``merged``: the merged review's)."""
    adv = set(advised)
    layouts = twofold or {}
    for it in sorted(items, key=lambda x: x.key):
        if getattr(it, "sources", None):
            lay = layouts.get(it.key)
            if lay is None:
                return f"dossier {it.key!r} is a combined answer of {len(it.sources)} sources, which the floor reviews N_FOLD; the plan does not"
            sources = list(_get(lay, "sources"))
            if len(sources) != len(it.sources):
                return f"combined answer {it.key!r} has {len(it.sources)} sources; the plan's N_FOLD reviews {len(sources)}"
            for k, (part, got) in enumerate(zip(it.sources, sources), start=1):
                want = floor_part_reviewers(part, it, adv)
                if len(set(got)) < want:
                    return (f"source {k} of combined answer {it.key!r} gets {len(set(got))} independent review(s); "
                            f"{'its risk signals call' if want > 1 else 'every source calls'} for {want}")
            want = floor_part_reviewers(it.merged, it, adv)
            got = len(set(_get(lay, "merged")))
            if got < want:
                return (f"the merged review of combined answer {it.key!r} gets {got} independent review(s); "
                        f"{'its risk signals call' if want > 1 else 'every merged review calls'} for {want}")
            bound = _get(lay, "context_max_bytes")
            if bound != CONTEXT_MAX_BYTES:  # a smaller bound would cut confirmed source faults from the merged review
                return (f"the temporary context of combined answer {it.key!r} is bounded at {bound} bytes; "
                        f"the floor keeps its bound at {CONTEXT_MAX_BYTES}")
            continue
        got = len(set(assignments.get(it.key, ())))
        want = floor_reviewers(it, adv)
        if got < want:
            return (f"dossier {it.key!r} gets {got} independent review(s); "
                    f"{'its risk signals call' if escalated(it, adv) else 'every dossier calls'} for {want}")
    return None


def _get(layout: Any, name: str) -> Any:
    return layout[name] if isinstance(layout, Mapping) else getattr(layout, name)


def floor_decision(items: Sequence[Any], *, max_instances: int, per_instance_quota: int, base_agent_id: str,
                   advised: Iterable[str] = ()) -> dict:
    """The floor plan's decision for a batch in key order (floor rule 5): instances, assignments, loads, review units,
    needed instances, capped, over quota, reasons, the N_FOLD layout of every combined answer (``twofold``) and the
    floor's decision record of every dossier (``decisions``), as the pool records them."""
    adv = set(advised)
    its = sorted(items, key=lambda x: x.key)
    repeated = [it for it in its if it.repeated_faults]
    risky = [it for it in its if it.risk_signals and not it.repeated_faults]
    advised_only = [it for it in its if it.key in adv and not it.repeated_faults and not it.risk_signals]
    combined = [it for it in its if getattr(it, "sources", None)]
    part_reviews = {it.key: ([floor_part_reviewers(p, it, adv) for p in it.sources], floor_part_reviewers(it.merged, it, adv)) for it in combined}
    reasons: list[str] = []
    if not its:
        needed = 0
        reasons.append("empty batch: no instance")
    else:
        needed = 1
        reasons.append("one instance by default")
        if repeated:
            needed = FLOOR_ESCALATED_REVIEWERS
            reasons.append(f"{len(repeated)} dossier(s) with repeated faults: each goes to {FLOOR_ESCALATED_REVIEWERS} independent instances")
        if risky:
            needed = FLOOR_ESCALATED_REVIEWERS
            classes = sorted({x for it in risky for x in it.risk_signals})
            reasons.append(f"{len(risky)} dossier(s) with risk signals ({', '.join(classes)}): each goes to {FLOOR_ESCALATED_REVIEWERS} independent "
                           "instances (a signal only ever escalates oversight)")
        if advised_only:
            needed = FLOOR_ESCALATED_REVIEWERS
            reasons.append(f"{len(advised_only)} dossier(s) escalated by the escalation advisor: each goes to {FLOOR_ESCALATED_REVIEWERS} independent "
                           "instances (an advisor only ever escalates oversight)")
        if combined:
            for per_source, merged in part_reviews.values():
                needed = max(needed, sum(per_source), merged)
            reasons.append(_n_fold_words(len(combined), sum(len(it.sources) for it in combined)))
    count = min(needed, max_instances)
    instances = [f"{base_agent_id}-{n}" for n in range(1, count + 1)]
    loads = {a: 0 for a in instances}
    assignments: dict[str, list[str]] = {}
    twofold: dict[str, dict] = {}

    def least_loaded(want: int, among: list[str]) -> list[str]:
        return sorted(among, key=lambda a: (loads[a], instances.index(a)))[:want]

    esc = {it.key for it in (*repeated, *risky, *advised_only)}
    for it in [*repeated, *risky, *advised_only, *[x for x in its if x.key not in esc]]:
        if it.key in part_reviews:
            per_source, merged = part_reviews[it.key]
            used: set[str] = set()
            picked: list[list[str]] = []
            for want in per_source:
                free = [a for a in instances if a not in used]
                chosen = least_loaded(want, free if len(free) >= want else list(instances))
                for a in chosen:
                    loads[a] += 1
                used.update(chosen)
                picked.append(sorted(chosen, key=instances.index))
            m = least_loaded(merged, list(instances))
            for a in m:
                loads[a] += 1
            twofold[it.key] = {"sources": picked, "merged": sorted(m, key=instances.index), "context_max_bytes": CONTEXT_MAX_BYTES}
            assignments[it.key] = sorted(set(m) | {a for s in picked for a in s}, key=instances.index)
            continue
        want = FLOOR_ESCALATED_REVIEWERS if it.key in esc else 1
        chosen = least_loaded(want, list(instances))
        for a in chosen:
            loads[a] += 1
        assignments[it.key] = sorted(chosen, key=instances.index)
    over = any(v > per_instance_quota for v in loads.values())
    if over:
        reasons.append(f"an instance carries {max(loads.values())} review units, over the quota of {per_instance_quota}: disclosed (the "
                       "minimum-oversight floor does not spread a batch by volume; batch sizes are the flash router's)")
    decisions = []
    for it in its:
        if it.key in twofold:
            rs = ["floor_n_fold"] + (["floor_advised"] if it.key in adv else [])
            decisions.append(PoolDecisionRecord(key=it.key, origin="floor", approach="duplication", method="N_FOLD", reviews=len(twofold[it.key]["merged"]),
                                                reasons=tuple(rs)))
            continue
        n = len(assignments[it.key])
        rs = ["floor_baseline"] if it.key not in esc else (["floor_agreement"] if (it.repeated_faults or it.risk_signals) else ["floor_advised"])
        decisions.append(PoolDecisionRecord(key=it.key, origin="floor", approach="in_depth" if n == 1 else "duplication",
                                            method="IN_DEPTH" if n == 1 else "DUPLICATE", reviews=n, reasons=tuple(rs)))
    out = {"instances": instances, "assignments": assignments, "loads": loads, "review_units": sum(loads.values()), "needed_instances": needed,
           "capped": needed > max_instances, "over_quota": over, "reasons": reasons}
    return {**out, "twofold": twofold, "decisions": tuple(decisions)}


def _n_fold_words(count: int, sources: int) -> str:
    return (f"{count} combined answer(s): N_FOLD, their {sources} source answer(s) each reviewed on instances of its own in parallel, then one "
            "merged review of each combinator's output with its bounded, request-scoped temporary context of the validated source outcomes")


def render_reason(reason: Any, *, capped: bool) -> str:
    """One reason of a router's plan (a closed code with its numbers and classes, ``router_pool.PoolReason``) in the
    overseer's words: the words the pool's planner wrote before the decision moved to the router."""
    c = reason.code
    if c == "pool_empty":
        return "empty batch: no instance"
    if c == "pool_baseline":
        return "one instance by default"
    if c == "pool_volume":
        return f"{reason.units} review units exceed the per-instance quota of {reason.quota}: {reason.instances} instances needed"
    if c == "pool_repeated_faults":
        return f"{reason.count} dossier(s) with repeated faults: each goes to {reason.reviewers} independent instances"
    if c == "pool_risk_signals":
        return (f"{reason.count} dossier(s) with risk signals ({', '.join(reason.classes)}): each goes to {reason.reviewers} independent instances "
                "(a signal only ever escalates oversight)")
    if c == "pool_advised":
        return (f"{reason.count} dossier(s) escalated by the escalation advisor: each goes to {reason.reviewers} independent instances "
                "(an advisor only ever escalates oversight)")
    if c == "pool_risk_records":
        return (f"{reason.count} dossier(s) with risk records only ({', '.join(reason.classes)}): each weighs {reason.weight} review units toward the "
                "quota (a record only ever escalates oversight)")
    if c == "pool_n_fold":
        return _n_fold_words(reason.count, reason.sources)
    if c == "pool_capped":
        return f"capped at the maximum of {reason.maximum} instances (needed {reason.needed})"
    if c == "pool_over_quota":
        tail = "disclosed, the plan stays at the maximum" if capped else "disclosed (the flash router's batch size)"
        return f"an instance carries {reason.load} review units, over the quota of {reason.quota}: {tail}"
    raise ValueError(f"no words for reason {c!r}")  # pragma: no cover - the router port's vocabulary is closed


def decision_note(record: PoolDecisionRecord) -> str:
    """The sentence the signed verdicts audit records for one dossier's decision: who decided, the approach and the
    method, the reviews, the reasons and, for the flash decision maker, what it read and what it priced."""
    who = "the flash decision maker" if record.origin == "router" else "the minimum-oversight floor"
    text = (f"the decision for this dossier ({who}): approach {record.approach}, method {record.method}, {record.reviews} independent review(s)"
            f"{' of the merged review' if record.method == 'N_FOLD' else ''}; reasons {', '.join(record.reasons)}")
    r = record.router
    if r:
        read = r.get("read") or {}
        f = read.get("features")
        size = (f"{f['chars']} characters in {f['transfers']} transfer(s), stem {str(f['stem']).lower()}, {f['translations']} translation(s)"
                if isinstance(f, Mapping) else "size not measured")
        need = r.get("need_tokens")
        fit = ("not assessed" if r.get("fits") is None else ("fits" if r.get("fits") else "does not fit"))
        cands = "; ".join(f"{c['method']} x{c['reviews']} ({c['calls']} call(s), {c['tokens'] if c['tokens'] is not None else 'unpriced'} tokens): "
                          f"{'keeps' if c['keeps_accuracy'] else 'does not keep'} accuracy, {c['why']}" for c in r.get("candidates", []))
        cost = r.get("estimated_cost") or {}
        text += (f"; it read {read.get('repeated_faults', 0)} repeated fault(s), risk signals [{', '.join(read.get('risk_signals', []))}], risk records "
                 f"[{', '.join(read.get('risk_records', []))}], advised {str(read.get('advised', False)).lower()}, {read.get('sources', 0)} source(s), {size}; "
                 f"one instance reading it whole needs {need if need is not None else 'an unmeasured number of'} tokens of a budget of "
                 f"{r.get('budget_tokens')} ({fit}); candidates: {cands}; estimated cost {cost.get('tokens')} tokens, {cost.get('seconds')} agent-seconds")
    return text


def admission_note(plan: Any) -> str:
    """The sentence the signed verdicts audit records for a pool plan: who planned it, the floor it was held to, any
    refusal (its code and why) and the advisor's escalations."""
    a = plan.admission
    floor = f"{a.floor.name} (rules sha256 {a.floor.rules_sha256})"
    r = a.router
    router = (f"the flash router {r.name} {r.version} (rules sha256 {r.rules_sha256}, cost data sha256 {r.cost_data_sha256})"
              if r is not None else "the flash router")
    if a.origin == "router":
        text = f"pool plan {plan.plan_id} planned by {router} (its plan {a.router_plan_id}), admitted at or above the minimum-oversight floor {floor}"
    elif a.refusal is None:
        text = f"pool plan {plan.plan_id} is the minimum-oversight floor plan {floor}: no flash router is attached"
    else:
        text = f"pool plan {plan.plan_id} is the minimum-oversight floor plan {floor}: {router} was refused ({a.refusal}: {a.detail})"
    if a.advised:
        text += f"; the escalation advisor escalated {len(a.advised)} dossier(s)"
    return text
