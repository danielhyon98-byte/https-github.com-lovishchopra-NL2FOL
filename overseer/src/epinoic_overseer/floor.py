"""The overseer pool's minimum-oversight floor (``minimum-oversight-floor/pool-1``), kept in the overseer.

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
3. a combined answer's floor is N_FOLD once combined answers reach the pool (architecture step 3); until then no pool
   batch carries one;
4. no plan has more instances than the pool's maximum (at most 64); every instance is built from the pool's one loaded
   pack and runs on the cheapest tier; the profile and the batch sizes are not part of the floor.

What lies above the floor is the router's choice, driven by cost and volume: how many instances a batch is spread over
(its batch sizes), the weight of risk records, extra duplicates, the profile. A router's plan that is out of contract
is refused with its ``KIT-RT`` code, one below the floor with ``KIT-RT-020``; either refusal is recorded in the plan's
:class:`PoolAdmission` and in the signed verdicts audit of every review that runs it, and the floor plan runs. With no
router attached the floor plan runs. Risk signals, and the advisor, only escalate. Every plan records who planned it:
the router's identity (name, version, the digests of its rules and of its cost data) or the floor's name and rules
digest, and any refusal.

The floor plan (no router, or a refused one): one instance for a batch with no escalated dossier, two when one is;
escalated dossiers first (repeated faults, then risk signals, then the advisor's), each group in key order, each to the
two least-loaded instances, every other dossier to the least-loaded one (ties to the lower instance number).
"""
from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from epinoic_logic.integration.canonical import sha256_text
from epinoic_logic.integration.protocol import RouterIdentity
from epinoic_logic.integration.router_pool import POOL_RISK_CLASSES

from .emitted import RISK_CLASSES

__all__ = [
    "POOL_FLOOR_NAME", "POOL_FLOOR_RULES", "POOL_FLOOR_RULES_SHA256", "FLOOR_ESCALATED_REVIEWERS", "PoolFloorRef", "PoolAdmission",
    "escalated", "floor_reviewers", "below_floor", "floor_decision", "render_reason", "admission_note",
]

if tuple(RISK_CLASSES) != tuple(POOL_RISK_CLASSES):  # pragma: no cover - a release defect
    raise ImportError("the overseer's risk classes are not the router port's pool vocabulary: the pool cannot speak the port")

POOL_FLOOR_NAME = "minimum-oversight-floor/pool-1"
#: Independent instances an escalated dossier reaches at the floor.
FLOOR_ESCALATED_REVIEWERS = 2
POOL_FLOOR_RULES = (
    "minimum-oversight-floor/pool-1\n"
    "1. Every dossier of the batch is reviewed by at least one instance: a dossier a plan leaves out has no review, which is"
    " below the floor.\n"
    "2. A dossier is reviewed by at least 2 distinct instances when its task carries a repeated fault or a risk signal"
    " (emitted.risk_reading at the effective severity: an error-level finding, a rejection, a contradiction, an encoding"
    " conflict, a withheld verdict, a named defect at warning or error, an unchecked source or a STEM method error at that"
    " severity, an argument diagnosis that did not finish), or when the escalation advisor escalated it.\n"
    "3. A combined answer's floor is N_FOLD once combined answers reach the pool (architecture step 3).\n"
    "4. No plan has more instances than the pool's maximum (at most 64); every instance is built from the pool's one loaded"
    " pack and runs on the cheapest tier; the profile and the batch sizes are not part of the floor.\n"
    "5. The floor plan: one instance, two when a dossier is escalated; escalated dossiers first (repeated faults, risk"
    " signals, the advisor's), each group in key order, each to the two least-loaded instances, every other dossier to the"
    " least-loaded one, ties to the lower instance number.\n"
)
POOL_FLOOR_RULES_SHA256 = sha256_text(POOL_FLOOR_RULES)
_CODE = r"^KIT-RT-[0-9]{3}$"


class PoolFloorRef(BaseModel):
    """The floor a pool plan was held to: its name and the digest of its rules."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: Literal["minimum-oversight-floor/pool-1"] = POOL_FLOOR_NAME
    rules_sha256: str = Field(default=POOL_FLOOR_RULES_SHA256, pattern=r"^[0-9a-f]{64}$")


class PoolAdmission(BaseModel):
    """Who planned a pool plan and why it runs: ``origin`` ``router`` (the attached flash router's plan, in contract and at
    or above the floor) or ``floor`` (no router attached, or the router refused: ``refusal`` is its ``KIT-RT`` code);
    ``router`` the attached router's identity (also when its plan was refused); ``floor`` the floor it was held to;
    ``detail`` why, in the overseer's words (never the router's text); the profile its instances run; the digests that
    bind the router's plan to its request; and the dossiers the escalation advisor escalated."""
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


def escalated(item: Any, advised: Iterable[str] = ()) -> bool:
    """Floor rule 2: a repeated fault, a risk signal, or the advisor's escalation."""
    return bool(item.repeated_faults or item.risk_signals or item.key in set(advised))


def floor_reviewers(item: Any, advised: Iterable[str] = ()) -> int:
    """The independent instances floor rules 1 and 2 ask for one dossier."""
    return FLOOR_ESCALATED_REVIEWERS if escalated(item, advised) else 1


def below_floor(assignments: Mapping[str, Sequence[str]], items: Sequence[Any], advised: Iterable[str] = ()) -> Optional[str]:
    """``None`` when every dossier gets at least the floor's distinct instances, else why not (the first dossier, in key
    order, that does not)."""
    adv = set(advised)
    for it in sorted(items, key=lambda x: x.key):
        got = len(set(assignments.get(it.key, ())))
        want = floor_reviewers(it, adv)
        if got < want:
            return (f"dossier {it.key!r} gets {got} independent review(s); "
                    f"{'its risk signals call' if escalated(it, adv) else 'every dossier calls'} for {want}")
    return None


def floor_decision(items: Sequence[Any], *, max_instances: int, per_instance_quota: int, base_agent_id: str,
                   advised: Iterable[str] = ()) -> dict:
    """The floor plan's decision for a batch in key order (floor rule 5): instances, assignments, loads, review units,
    needed instances, capped, over quota and reasons, as the pool records them."""
    adv = set(advised)
    its = sorted(items, key=lambda x: x.key)
    repeated = [it for it in its if it.repeated_faults]
    risky = [it for it in its if it.risk_signals and not it.repeated_faults]
    advised_only = [it for it in its if it.key in adv and not it.repeated_faults and not it.risk_signals]
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
    count = min(needed, max_instances)
    instances = [f"{base_agent_id}-{n}" for n in range(1, count + 1)]
    loads = {a: 0 for a in instances}
    assignments: dict[str, list[str]] = {}
    esc = {it.key for it in (*repeated, *risky, *advised_only)}
    for it in [*repeated, *risky, *advised_only, *[x for x in its if x.key not in esc]]:
        want = FLOOR_ESCALATED_REVIEWERS if it.key in esc else 1
        chosen = sorted(instances, key=lambda a: (loads[a], instances.index(a)))[:want]
        for a in chosen:
            loads[a] += 1
        assignments[it.key] = sorted(chosen, key=instances.index)
    over = any(v > per_instance_quota for v in loads.values())
    if over:
        reasons.append(f"an instance carries {max(loads.values())} review units, over the quota of {per_instance_quota}: disclosed (the "
                       "minimum-oversight floor does not spread a batch by volume; batch sizes are the flash router's)")
    return {"instances": instances, "assignments": assignments, "loads": loads, "review_units": sum(loads.values()), "needed_instances": needed,
            "capped": needed > max_instances, "over_quota": over, "reasons": reasons}


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
    if c == "pool_capped":
        return f"capped at the maximum of {reason.maximum} instances (needed {reason.needed})"
    if c == "pool_over_quota":
        tail = "disclosed, the plan stays at the maximum" if capped else "disclosed (the flash router's batch size)"
        return f"an instance carries {reason.load} review units, over the quota of {reason.quota}: {tail}"
    raise ValueError(f"no words for reason {c!r}")  # pragma: no cover - the router port's vocabulary is closed


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
