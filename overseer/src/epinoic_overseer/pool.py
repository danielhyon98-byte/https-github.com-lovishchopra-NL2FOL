"""The overseer pool: the overseer-agent instances that review a batch of dossiers, every one configured from the same
loaded knowledge pack, and the plan that says which instances review which dossiers.

Design ``docs/OVERSEER_DESIGN.md`` sections 19, 51 and 52. A batch is a list of :class:`PoolItem` (one dossier key each,
with the number of repeated faults in its task, :mod:`~epinoic_overseer.repeats`, the risk signals and records its task
carries, :func:`~epinoic_overseer.emitted.risk_reading`, its size, and for a combined answer its sources and its merged
part, :mod:`~epinoic_overseer.twofold`). :func:`plan_pool` returns a :class:`PoolPlan`.

**A combined answer (architecture step 3, the twofold mode).** A dossier whose synthesis combines N >= 2 specialists'
delivered answers carries its N sources and its merged part (:class:`PoolPart`: each part's own repeated faults, risk
signals and records, and size). The floor reviews it N_FOLD (:mod:`~epinoic_overseer.floor`, rule 3), and so does the
flash router at pool port 1.2: the plan records, in ``twofold``, which instances review each source (in parallel: no
instance reviews two sources of one dossier while the plan has instances to spare) and which instances run the merged
review, with the temporary context's bound; ``assignments`` holds every instance the dossier's review uses. The hub then
runs it (``hub_ops``): the source reviews, their validated outcomes as the bounded temporary context, the merged
review. A router that speaks only pool port 1.1 plans no combined answer: a batch holding one runs the floor plan, the
refusal recorded (``KIT-RT-015``).

**Who decides (architecture step 2c).** The planning decision (how many instances, which instance reviews which dossier,
which dossiers go to independent duplicates) is the flash router's: a separate agent in its own sub-project
(``flash-router/``, package ``epinoic_flash_router``), edited, re-tuned and released apart from the overseer, attached
through the router port by capability (``router=`` a module name, run in its own process, or an attachment of
``epinoic_logic.integration.router_pool``; this package never imports it). The overseer keeps the floor
(:mod:`~epinoic_overseer.floor`): it computes the minimum oversight from the same risk signals, validates the router's
plan as untrusted data, and runs it only when it is in contract and at or above the floor; otherwise the floor plan runs
and the refusal is recorded (``PoolPlan.admission`` and the signed verdicts audit of every review that runs the plan).
With no router attached the floor plan runs. With the router's released rules, the router's plan is the plan this module
made before the move, for every recorded transfer:

* **review units**: one per dossier, two per dossier whose task has a repeated fault or a risk signal (it goes to two
  independent instances, :data:`MIN_REPEAT_REVIEWERS`), two per dossier whose task carries only risk records (a record
  weighs two units toward the quota);
* **instances**: ONE by default; more when the review units exceed the per-instance quota (``ceil(units /
  per_instance_quota)``) or when a dossier is escalated (at least two); never more than ``max_instances`` (default
  :data:`DEFAULT_MAX_INSTANCES`, at most :data:`HARD_MAX_INSTANCES`, never below two so an escalated dossier can always
  reach two instances). When the cap binds, the plan says so (``capped``) and an instance may carry more than its quota
  (``over_quota``): the plan never grows past the maximum. An empty batch plans no instance;
* **assignment**, deterministic and independent of the input order: repeated-fault dossiers first, then the dossiers with
  risk signals, then the others, each in key order, every review unit to the least-loaded instance (ties to the lower
  instance number); an escalated dossier goes to the two least-loaded DISTINCT instances. Instance agent ids are
  ``<base_agent_id>-<n>``: the router names instance numbers, the overseer names the instances.

The floor plan keeps the escalations and drops what is the router's to choose (the spreading by volume and the weight of
risk records): one instance, two when a dossier is escalated. ``plan_id`` is a digest of the configuration, the pack
identity, the items and the assignment, whoever planned it; ``reasons`` say in words why the plan has its size (the
overseer's words, rendered from the router's closed reason codes), and ``admission`` says who planned it.

:class:`OverseerPool` holds one loaded :class:`~epinoic_overseer.pack.KnowledgePack`, a provider factory and, optionally,
the attached router and an escalation advisor. Every instance is an :class:`~epinoic_overseer.runner.OverseerAgentRunner`
built from THAT pack (so every instance's configuration is byte-identical: the same exported pack, the same system
text), with its own provider from the factory and the pool's lens, and only for an agent id a recorded plan names (so the
pool never holds more instances than its capped plans; a pool instance is marked ``pool_member`` and the hub runs it only
under a pool plan). The deployment tier is recorded as :data:`MODEL_TIER` (``cheapest``): which model serves it is the
provider's business, and correctness never rests on it. Every plan the pool makes is recorded (``plans``, append-only)
and the hub records it, with its admission, in the signed verdicts audit of every review it runs
(``RouterHub.review_pool``).

**The escalation advisor** (``advisor=``, off by default) lets a cheapest-tier model propose extra escalations: a
callable given the batch's items that returns dossier keys. Its keys only ever escalate (each named dossier is then held
to two independent instances by the floor and asked of the router as escalated); whatever else it returns, or raises,
is ignored and noted. It can never lower a plan.

Instances are overseer agents like any other: they read a dossier and return a verdict that the intake, validation and
combination treat as data. They never certify anything, never change a status or a clearance, and stay advisory: the
verdicts of the instances that reviewed one dossier are combined by the existing rule (``combine_verdicts``: no voting on
facts; agreement between instances is never evidence).
"""
from __future__ import annotations

import re
import threading
from typing import Any, Callable, Iterable, Literal, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_serializer, model_validator

from epinoic_logic.api.ir import canonical_json, sha256_hex
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.router_pool import (
    PoolRouterAttachment, ask_pool_router, attach_pool_router, build_pool_request, check_pool_plan, item_id, pool_request_digest,
)
from .floor import CONTEXT_MAX_BYTES, FLOOR_ESCALATED_REVIEWERS, PoolAdmission, PoolDecisionRecord, below_floor, floor_decision, render_reason
from .pack import KnowledgePack
from .runner import OverseerAgentRunner
from .verdicts import HEADER_ID_PATTERN, Lens, Mode, PackIdentity

__all__ = [
    "DEFAULT_MAX_INSTANCES", "DEFAULT_PER_INSTANCE_QUOTA", "MIN_REPEAT_REVIEWERS", "HARD_MAX_INSTANCES", "MODEL_TIER", "PROFILES", "PoolConfig",
    "PoolFeatures", "PoolPart", "PoolItem", "PoolTwofold", "PoolPlan", "PoolAdmission", "PoolDecisionRecord", "plan_pool", "OverseerPool",
]

DEFAULT_MAX_INSTANCES = 4
DEFAULT_PER_INSTANCE_QUOTA = 8
#: Independent instances every escalated dossier (a repeated fault or a risk signal) goes to: the floor's.
MIN_REPEAT_REVIEWERS = FLOOR_ESCALATED_REVIEWERS
#: No configuration may plan more instances than this.
HARD_MAX_INSTANCES = 64
#: The tier deployed overseer agents run on. Correctness rests on the deterministic code and the signed engine results.
MODEL_TIER = "cheapest"
#: The overseer-agent profiles the pool offers a router (``standard`` only: the fast profile is not built).
PROFILES: tuple[str, ...] = ("standard",)
_KEY_PATTERN = r"^[^\x00-\x1f\x7f]{1,256}$"
_BASE_ID_PATTERN = r"^[A-Za-z0-9._-]{1,100}$"


class PoolConfig(BaseModel):
    """The pool's fixed configuration."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    max_instances: int = Field(default=DEFAULT_MAX_INSTANCES, ge=MIN_REPEAT_REVIEWERS, le=HARD_MAX_INSTANCES)
    per_instance_quota: int = Field(default=DEFAULT_PER_INSTANCE_QUOTA, ge=1, le=100_000)
    lens: Lens = "general"
    mode: Mode = "informed"
    base_agent_id: str = Field(default="overseer-pool", pattern=_BASE_ID_PATTERN)
    model_tier: Literal["cheapest"] = MODEL_TIER


class PoolFeatures(BaseModel):
    """The size of a dossier, or of one part of a combined answer, as the flash decision maker prices it: its journaled
    transfers, their characters (envelopes, receipts and raw texts as journaled), whether its content is STEM and how many
    translations it carries. Counts only (``twofold.features_of``)."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    transfers: int = Field(ge=0, le=1_000_000)
    chars: int = Field(ge=0, le=1_000_000_000)
    stem: bool
    translations: int = Field(ge=0, le=1_000_000)


class PoolPart(BaseModel):
    """One part of a combined answer: one specialist's own transfers (a source), or the combinator's output with every
    transfer no source owns (the merged part); its repeated faults, the risk signals and records its own transfers carry,
    and its size."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    repeated_faults: int = Field(default=0, ge=0)
    risk_signals: tuple[str, ...] = Field(default=(), strict=False)
    risk_records: tuple[str, ...] = Field(default=(), strict=False)
    features: Optional[PoolFeatures] = None

    @model_validator(mode="after")
    def _signals(self) -> "PoolPart":
        from .emitted import RISK_CLASSES
        for xs in (self.risk_signals, self.risk_records):
            if any(x not in RISK_CLASSES for x in xs) or list(xs) != sorted(set(xs)):
                raise ValueError("risk signals and records are classes of emitted.RISK_CLASSES, sorted and unique")
        return self

    @property
    def escalated(self) -> bool:
        return bool(self.repeated_faults or self.risk_signals)


class PoolItem(BaseModel):
    """One dossier of a batch: its key (the hub uses the channel uid), the repeated faults in its task and the risk signals
    its task carries (the classes of :data:`~epinoic_overseer.emitted.RISK_CLASSES`, sorted and unique); its size
    (``features``, ``None`` when not measured); and for a combined answer its N >= 2 ``sources`` (in the order their
    answers were first delivered) and its ``merged`` part. A dossier that is not a combined answer dumps exactly as it did
    before architecture step 3 when its size is not measured (the recorded plans keep their digests)."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    key: str = Field(pattern=_KEY_PATTERN)
    repeated_faults: int = Field(default=0, ge=0)
    risk_signals: tuple[str, ...] = Field(default=(), strict=False)  # a JSON list re-validates (a plan read back from its dump)
    risk_records: tuple[str, ...] = Field(default=(), strict=False)
    features: Optional[PoolFeatures] = None
    sources: tuple[PoolPart, ...] = Field(default=(), strict=False, max_length=16)
    merged: Optional[PoolPart] = None

    @model_validator(mode="after")
    def _signals(self) -> "PoolItem":
        from .emitted import RISK_CLASSES
        for xs in (self.risk_signals, self.risk_records):
            if any(x not in RISK_CLASSES for x in xs) or list(xs) != sorted(set(xs)):
                raise ValueError("risk signals and records are classes of emitted.RISK_CLASSES, sorted and unique")
        if len(self.sources) == 1:
            raise ValueError("a combined answer combines at least two sources")
        if bool(self.sources) != (self.merged is not None):
            raise ValueError("a combined answer has its sources and its merged part, any other dossier neither")
        return self

    @model_serializer(mode="wrap")
    def _dump(self, handler):
        data = handler(self)
        for name in ("features", "merged"):
            if data.get(name) is None:
                data.pop(name, None)
        if not data.get("sources"):
            data.pop("sources", None)
        return data

    @property
    def units(self) -> int:
        """The review units the dossier weighs: one, two when it is escalated or carries risk records."""
        return MIN_REPEAT_REVIEWERS if (self.escalated or self.risk_records) else 1

    @property
    def escalated(self) -> bool:
        """Whether the dossier goes to two independent instances: a repeated fault or a risk signal."""
        return bool(self.repeated_faults or self.risk_signals)

    @property
    def combined(self) -> bool:
        """Whether the dossier is a combined answer (reviewed N_FOLD)."""
        return bool(self.sources)


class PoolTwofold(BaseModel):
    """A combined answer's N_FOLD in a plan: the instances that review each source (in the order of the dossier's
    sources), the instances that run the merged review, and the temporary context's bound."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    sources: tuple[tuple[str, ...], ...] = Field(min_length=2, max_length=16)
    merged: tuple[str, ...] = Field(min_length=1, max_length=HARD_MAX_INSTANCES)
    context_max_bytes: int = Field(default=CONTEXT_MAX_BYTES, ge=1, le=CONTEXT_MAX_BYTES)


class PoolPlan(BaseModel):
    """How many instances review a batch and which instance reviews which dossier. Never more instances than
    ``config.max_instances``; every repeated-fault dossier goes to at least two distinct instances; every combined answer
    is reviewed N_FOLD at its parts' floor (``twofold``, absent from the dump when the batch holds none)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_id: str
    config: PoolConfig
    pack: PackIdentity
    items: list[PoolItem]
    instances: list[str]
    assignments: dict[str, list[str]]
    loads: dict[str, int]
    review_units: int
    needed_instances: int
    capped: bool
    over_quota: bool
    reasons: list[str]
    #: Who planned it (the flash router, or the minimum-oversight floor), the floor it was held to and any refusal.
    admission: PoolAdmission
    #: Each combined answer's N_FOLD: the instances of each source review and of the merged review (architecture step 3).
    twofold: dict[str, PoolTwofold] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _bounded(self) -> "PoolPlan":
        if len(self.instances) > self.config.max_instances or len(self.instances) > HARD_MAX_INSTANCES:
            raise ValueError("a pool plan never grows past its maximum (nor past HARD_MAX_INSTANCES, whatever its config says)")
        if not (MIN_REPEAT_REVIEWERS <= self.config.max_instances <= HARD_MAX_INSTANCES) or self.config.per_instance_quota < 1:
            raise ValueError("the plan's configuration is outside the pool's bounds")
        if len(set(self.instances)) != len(self.instances):
            raise ValueError("instance ids are unique")
        known = set(self.instances)
        for it in self.items:
            chosen = self.assignments.get(it.key, [])
            if not chosen or len(set(chosen)) != len(chosen) or not set(chosen) <= known:
                raise ValueError(f"dossier {it.key!r} has no valid assignment")
            if it.escalated and len(chosen) < MIN_REPEAT_REVIEWERS:
                raise ValueError(f"escalated dossier {it.key!r} (a repeated fault or a risk signal) goes to fewer than {MIN_REPEAT_REVIEWERS} instances")
            lay = self.twofold.get(it.key)
            if it.combined != (lay is not None):
                raise ValueError(f"dossier {it.key!r}: a combined answer is reviewed N_FOLD, any other dossier never")
            if lay is not None:
                parts = [*lay.sources, lay.merged]
                if any(not p or len(set(p)) != len(p) or not set(p) <= known for p in parts):
                    raise ValueError(f"combined answer {it.key!r} has an N_FOLD part with no valid instances")
                if sorted(set(a for p in parts for a in p), key=self.instances.index) != list(chosen):
                    raise ValueError(f"combined answer {it.key!r}: its assignment is every instance its N_FOLD uses")
        if set(self.assignments) != {it.key for it in self.items}:
            raise ValueError("every dossier, and only those, is assigned")
        if set(self.twofold) - {it.key for it in self.items}:
            raise ValueError("an N_FOLD layout names a dossier of no item")
        below = below_floor(self.assignments, [it for it in self.items if it.combined], self.admission.advised, self.twofold)
        if below is not None:
            raise ValueError(f"the plan is below the minimum-oversight floor: {below}")
        return self

    @model_serializer(mode="wrap")
    def _dump(self, handler):
        data = handler(self)
        if not data.get("twofold"):
            data.pop("twofold", None)
        return data

    def instances_for(self, key: str) -> list[str]:
        return list(self.assignments[key])


def _plan_digest(data: dict) -> str:
    return sha256_hex(canonical_json(data))[:32]


def _revalidated(config: PoolConfig) -> PoolConfig:
    """The configuration re-validated against :class:`PoolConfig`: a config built around validation (``model_copy(update=...)``
    is not validated by pydantic) can never plan past :data:`HARD_MAX_INSTANCES` or with a quota below one."""
    try:
        return PoolConfig.model_validate(config.model_dump())
    except ValidationError as exc:
        raise ValueError(f"the pool configuration is outside its bounds ({exc.error_count()} error(s): max_instances {MIN_REPEAT_REVIEWERS} to "
                         f"{HARD_MAX_INSTANCES}, per_instance_quota at least 1)") from None


RouterSpec = Union[None, str, PoolRouterAttachment]
Advisor = Callable[[list], Iterable[str]]


def _attachment(router: RouterSpec) -> Optional[PoolRouterAttachment]:
    """``None`` (no router), a module name (attached through the router port, in its own process) or an attachment."""
    if router is None or isinstance(router, PoolRouterAttachment):
        return router
    if isinstance(router, str):
        return attach_pool_router(router)
    raise TypeError("router is a module name or a router_pool.PoolRouterAttachment (or None: the floor plan runs)")


def _advised(advisor: Optional[Advisor], its: list[PoolItem]) -> tuple[tuple[str, ...], str]:
    """The keys the escalation advisor escalates (only keys of this batch; escalation only), and a note when it failed or
    named anything else (ignored: an advisor never lowers a plan)."""
    if advisor is None:
        return (), ""
    keys = {it.key for it in its}
    try:
        proposed = list(advisor([it.model_copy() for it in its]))
    except Exception as exc:  # noqa: BLE001 - an advisor that fails escalates nothing; the plan stands without it
        return (), f"; the escalation advisor failed ({type(exc).__name__}): no extra escalation"
    chosen = sorted({k for k in proposed if isinstance(k, str) and k in keys})
    ignored = sum(1 for k in proposed if not (isinstance(k, str) and k in keys))
    return tuple(chosen), (f"; {ignored} proposal(s) of the escalation advisor named no dossier of this batch and were ignored" if ignored else "")


def _plan(its: list[PoolItem], config: PoolConfig, pack: PackIdentity, decision: dict, admission: PoolAdmission) -> PoolPlan:
    for a in decision["instances"]:
        if not re.match(HEADER_ID_PATTERN, a):
            raise ValueError(f"instance id {a!r} is not a valid agent id")
    twofold = decision.get("twofold") or {}
    body = {"config": config.model_dump(mode="json"), "pack": pack.model_dump(mode="json"), "items": [it.model_dump(mode="json") for it in its],
            "instances": decision["instances"], "assignments": decision["assignments"]}
    if twofold:
        body["twofold"] = {k: {"sources": [list(x) for x in v["sources"]], "merged": list(v["merged"]), "context_max_bytes": v["context_max_bytes"]}
                           for k, v in twofold.items()}
    fields = {k: v for k, v in decision.items() if k not in ("twofold", "decisions")}
    return PoolPlan(plan_id="pool-" + _plan_digest(body), config=config, pack=pack, items=its, admission=admission,
                    twofold={k: PoolTwofold(sources=tuple(tuple(x) for x in v["sources"]), merged=tuple(v["merged"]),
                                            context_max_bytes=v["context_max_bytes"]) for k, v in twofold.items()}, **fields)


def _request_item(it: PoolItem, advised: Iterable[str]) -> dict:
    def part(p: PoolPart) -> dict:
        return {"repeated_faults": p.repeated_faults, "risk_signals": list(p.risk_signals), "risk_records": list(p.risk_records),
                "features": p.features.model_dump(mode="json") if p.features is not None else None}
    out: dict[str, Any] = {"repeated_faults": it.repeated_faults, "risk_signals": list(it.risk_signals), "risk_records": list(it.risk_records),
                           "advised": it.key in set(advised)}
    out.update(features=it.features.model_dump(mode="json") if it.features is not None else None, sources=[part(p) for p in it.sources],
               merged=part(it.merged) if it.merged is not None else None)
    return out


def plan_pool(items: Sequence[PoolItem], config: PoolConfig, pack: PackIdentity, *, router: RouterSpec = None,
              advisor: Optional[Advisor] = None) -> PoolPlan:
    """The plan for a batch (module docstring): the attached flash router's, when it is in contract and at or above the
    minimum-oversight floor, else the floor plan, with the refusal recorded in ``admission``. ``router`` is ``None`` (the
    floor plan runs), a router module name (attached through the router port, in its own process, for this call) or a
    :class:`~epinoic_logic.integration.router_pool.PoolRouterAttachment`; :class:`OverseerPool` attaches once. The request
    is written in the pool port version the router's pool hello names (1.2: every dossier's size and a combined answer's
    parts, and the router's decision for every dossier recorded in ``admission.decisions``); a router at 1.1 is not asked
    about a batch that holds a combined answer (its floor plan runs, ``KIT-RT-015``). Never raises for anything the router
    does. ``ValueError`` on a duplicated key or a configuration outside the pool's bounds (re-validated here, so a config
    copied around validation is refused)."""
    if not isinstance(config, PoolConfig):
        raise TypeError("config must be a PoolConfig")
    config = _revalidated(config)
    if not isinstance(pack, PackIdentity):
        raise TypeError("pack must be a PackIdentity")
    its = [it if isinstance(it, PoolItem) else PoolItem.model_validate(it) for it in items]
    keys = [it.key for it in its]
    if len(set(keys)) != len(keys):
        raise ValueError("a dossier key is given twice in one batch")
    its.sort(key=lambda it: it.key)
    advised, advisor_note = _advised(advisor, its)
    att = _attachment(router)
    identity = att.identity if att is not None else None
    version = att.hello.port_version if att is not None and att.attached and att.hello is not None else None

    def floor(refusal: Optional[str], detail: str, *, request_sha256: Optional[str] = None) -> PoolPlan:
        decision = floor_decision(its, max_instances=config.max_instances, per_instance_quota=config.per_instance_quota,
                                  base_agent_id=config.base_agent_id, advised=advised)
        return _plan(its, config, pack, decision, PoolAdmission(origin="floor", router=identity, refusal=refusal, detail=(detail + advisor_note)[:2000],
                                                                 request_sha256=request_sha256, advised=advised,
                                                                 port_version=version if request_sha256 is not None else None,
                                                                 decisions=decision["decisions"]))

    if att is None:
        return floor(None, "no flash router is attached: the minimum-oversight floor plan runs")
    if not att.attached:
        return floor(att.refusal, f"the flash router is not attached ({att.detail})")
    if version == "1.1" and any(it.combined for it in its):
        return floor("KIT-RT-015", "the attached router speaks pool port 1.1, which plans no combined answer (its N_FOLD needs pool port 1.2): "
                                   "the floor plans this batch")
    try:
        if version == "1.1":
            raw_items = [{"repeated_faults": it.repeated_faults, "risk_signals": list(it.risk_signals), "risk_records": list(it.risk_records),
                          "advised": it.key in advised} for it in its]
        else:
            raw_items = [_request_item(it, advised) for it in its]
        request = build_pool_request(raw_items, max_instances=config.max_instances, per_instance_quota=config.per_instance_quota, profiles=PROFILES,
                                     port_version=version or "1.1")
    except IntegrationError as exc:
        return floor(exc.code, f"the pool request could not be built ({exc.detail})")
    digest = pool_request_digest(request)
    answer = ask_pool_router(request, att)
    if answer.refusal is not None:
        return floor(answer.refusal, answer.detail, request_sha256=digest)
    try:
        routed = check_pool_plan(answer.data, request, hello=att.hello)  # type: ignore[arg-type]
    except IntegrationError as exc:
        return floor(exc.code, exc.detail, request_sha256=digest)
    names = [f"{config.base_agent_id}-{n}" for n in range(1, routed.instances + 1)]
    by_item = {a.item_id: a for a in routed.assignments}

    def named(numbers: Iterable[int]) -> list[str]:
        return [names[n - 1] for n in sorted(set(numbers))]

    assignments: dict[str, list[str]] = {}
    twofold: dict[str, dict] = {}
    for i, it in enumerate(its):
        a = by_item[item_id(i)]
        if a.method == "N_FOLD":
            sources = [named(s.instances) for s in a.sources]
            merged = named(a.instances)
            twofold[it.key] = {"sources": sources, "merged": merged, "context_max_bytes": a.context.max_bytes}
            assignments[it.key] = named([*a.instances, *(n for s in a.sources for n in s.instances)])
        else:
            assignments[it.key] = named(a.instances)
    below = below_floor(assignments, its, advised, twofold)
    if below is not None:
        return floor("KIT-RT-020", f"the router's plan is below the minimum-oversight floor: {below}", request_sha256=digest)
    # the router's assignment in the order it assigned (escalated dossiers first), as the pool recorded it before the move
    order = sorted(range(len(its)), key=lambda i: (0 if its[i].repeated_faults else 1 if its[i].risk_signals else 2 if its[i].key in advised else 3, i))
    decision = {"instances": names, "assignments": {its[i].key: assignments[its[i].key] for i in order},
                "loads": {names[i]: routed.loads[i] for i in range(routed.instances)}, "review_units": routed.review_units,
                "needed_instances": routed.needed_instances, "capped": routed.capped, "over_quota": routed.over_quota,
                "reasons": [render_reason(r, capped=routed.capped) for r in routed.reasons], "twofold": twofold}
    decisions = ()
    if version == "1.2":
        decisions = tuple(PoolDecisionRecord(key=it.key, origin="router", approach=by_item[item_id(i)].decision.approach,
                                             method=by_item[item_id(i)].decision.method, reviews=by_item[item_id(i)].decision.reviews,
                                             reasons=tuple(by_item[item_id(i)].decision.reasons),
                                             router=by_item[item_id(i)].decision.model_dump(mode="json"))
                          for i, it in enumerate(its))
    admission = PoolAdmission(origin="router", router=identity, refusal=None,
                              detail=("the flash router's plan is in contract and at or above the minimum-oversight floor" + advisor_note)[:2000],
                              profile=routed.profile, request_sha256=digest, router_plan_id=routed.plan_id, advised=advised, port_version=version,
                              decisions=decisions)
    try:
        return _plan(its, config, pack, decision, admission)
    except (ValidationError, ValueError) as exc:  # the overseer's own plan contract: never past the maximum, the floor kept
        return floor("KIT-RT-001", f"the router's plan does not make a valid pool plan ({type(exc).__name__})", request_sha256=digest)


class OverseerPool:
    """Overseer-agent instances built from ONE loaded knowledge pack, sized per batch by :func:`plan_pool`.

    ``provider_factory(agent_id)`` returns the completion provider of one instance (called once per instance id). The
    pool holds no key and builds nothing but :class:`OverseerAgentRunner` instances from its pack. ``router`` attaches
    the flash router once, by capability (a module name, run in its own process, or an attachment of
    ``epinoic_logic.integration.router_pool``); without it every plan is the minimum-oversight floor plan. ``advisor``
    (off by default) may only escalate (module docstring)."""

    def __init__(self, pack: KnowledgePack, provider_factory: Callable[[str], Any], *, config: Optional[PoolConfig] = None,
                 router: RouterSpec = None, advisor: Optional[Advisor] = None) -> None:
        if not isinstance(pack, KnowledgePack):
            raise TypeError("an overseer pool is configured only from a KnowledgePack loaded by load_pack")
        pack.verify()
        if not callable(provider_factory):
            raise TypeError("provider_factory must be callable: agent_id -> completion provider")
        self._pack = pack
        self._factory = provider_factory
        self.config = config if config is not None else PoolConfig()
        if not isinstance(self.config, PoolConfig):
            raise TypeError("config must be a PoolConfig")
        self.config = _revalidated(self.config)
        if advisor is not None and not callable(advisor):
            raise TypeError("advisor must be callable: the batch's items -> dossier keys to escalate")
        self._router: Optional[PoolRouterAttachment] = _attachment(router)
        self._advisor = advisor
        self._plans: list[PoolPlan] = []
        self._runners: dict[str, OverseerAgentRunner] = {}
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        r = self._router.identity if self._router is not None else None
        router = f"{r.name} {r.version}" if r is not None else ("refused " + str(self._router.refusal) if self._router is not None else "none")
        return (f"OverseerPool(pack={self._pack.identity.label!r}, max_instances={self.config.max_instances}, quota={self.config.per_instance_quota}, "
                f"router={router!r})")

    @property
    def router(self) -> Optional[PoolRouterAttachment]:
        """The flash router attached for this pool (``None`` when none was named; an attachment that is not ``attached``
        carries the refusal every plan records)."""
        return self._router

    @property
    def pack(self) -> KnowledgePack:
        return self._pack

    @property
    def identity(self) -> PackIdentity:
        return self._pack.identity

    @property
    def plans(self) -> tuple[PoolPlan, ...]:
        """Every plan this pool made, in order (append-only)."""
        with self._lock:
            return tuple(self._plans)

    def plan(self, items: Sequence[PoolItem]) -> PoolPlan:
        """Plan a batch (the router's plan when it is admitted, else the floor plan) and record the plan."""
        p = plan_pool(items, self.config, self._pack.identity, router=self._router, advisor=self._advisor)
        with self._lock:
            self._plans.append(p)
        return p

    def is_recorded(self, plan: Any) -> bool:
        with self._lock:
            return any(p is plan or (isinstance(plan, PoolPlan) and p == plan) for p in self._plans)

    def instance(self, agent_id: str) -> OverseerAgentRunner:
        """The instance ``agent_id``, built once from the pool's pack with its own provider. Only an instance a recorded
        plan names is ever built (the pool never holds more instances than its plans, each capped at ``max_instances``);
        any other agent id is refused (ValueError). Every pool instance carries ``pool_member = True``, and the hub
        runs one only under a pool plan (``RouterHub.review(..., pool_plan=...)``)."""
        with self._lock:
            r = self._runners.get(agent_id)
            if r is None:
                if not any(agent_id in p.instances for p in self._plans):
                    raise ValueError(f"{agent_id!r} is not an instance of any plan this pool made: instances are built only as a recorded plan assigns them")
                r = OverseerAgentRunner(self._pack, self._factory(agent_id), agent_id=agent_id, lens=self.config.lens)
                r.pool_member = True
                self._runners[agent_id] = r
            return r

    def runners_for(self, plan: PoolPlan, key: str) -> list[OverseerAgentRunner]:
        """The instances a recorded plan assigns to dossier ``key``. A plan this pool did not make is refused."""
        if not self.is_recorded(plan):
            raise ValueError("this pool did not make that plan")
        if plan.pack != self._pack.identity:
            raise ValueError("the plan was made under another pack")
        return [self.instance(a) for a in plan.instances_for(key)]
