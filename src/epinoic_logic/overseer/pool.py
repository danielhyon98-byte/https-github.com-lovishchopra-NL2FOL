"""The overseer pool: how many overseer-agent instances review a batch of dossiers, decided deterministically, and the
instances themselves, every one configured from the same loaded knowledge pack.

Design ``docs/OVERSEER_DESIGN.md`` section 19. A batch is a list of :class:`PoolItem` (one dossier key each, with the
number of repeated faults in its task, :mod:`~epinoic_logic.overseer.repeats`). :func:`plan_pool` returns a
:class:`PoolPlan`:

* **review units**: one per dossier, two per dossier whose task has a repeated fault (it goes to two independent
  instances, :data:`MIN_REPEAT_REVIEWERS`), two per dossier whose task carries a risk signal and two per dossier whose task
  carries only risk records (integration step: :func:`~epinoic_logic.overseer.emitted.risk_reading` reads both from the
  journal; a signal is what blocks release or names a fault: a named defect at effective warning or error, an unchecked
  source or a STEM method error at that severity, an encoding conflict, a contradiction, a withheld verdict, a rejection,
  an argument diagnosis that did not finish, an error-level finding; a record is an info diagnostic of the three named
  families: a load-bearing writer's assumption, an unchecked source, a STEM method record). Both only ever escalate
  oversight: a dossier with a signal goes to two independent instances like a repeated fault, one with records only weighs
  two review units toward the quota, and a plan never has fewer instances, nor gives any dossier fewer reviewers, than the
  same batch without them (always within the maximum);
* **instances**: ONE by default; more when the review units exceed the per-instance quota
  (``ceil(units / per_instance_quota)``) or when any dossier has a repeated fault (at least two); never more than
  ``max_instances`` (default :data:`DEFAULT_MAX_INSTANCES`, at most :data:`HARD_MAX_INSTANCES`, never below two so a
  repeated-fault dossier can always reach two instances). When the cap binds, the plan says so (``capped``) and an
  instance may carry more than its quota (``over_quota``): the plan never grows past the maximum. An empty batch plans no
  instance;
* **assignment**, deterministic and independent of the input order: repeated-fault dossiers first, then the dossiers with
  risk signals, then the others, each in key order, every review unit to the least-loaded instance (ties to the lower
  instance number); a repeated-fault dossier, and one with risk signals, goes to the two least-loaded DISTINCT instances. Instance agent ids are ``<base_agent_id>-<n>``;
* ``plan_id``: a digest of the configuration, the pack identity, the items and the assignment; ``reasons`` say in words
  why the plan has its size.

:class:`OverseerPool` holds one loaded :class:`~epinoic_logic.overseer.pack.KnowledgePack` and a provider factory. Every
instance is an :class:`~epinoic_logic.overseer.runner.OverseerAgentRunner` built from THAT pack (so every instance's
configuration is byte-identical: the same exported pack, the same system text), with its own provider from the factory and
the pool's lens, and only for an agent id a recorded plan names (so the pool never holds more instances than its capped
plans; a pool instance is marked ``pool_member`` and the hub runs it only under a pool plan). The deployment tier is
recorded as :data:`MODEL_TIER` (``cheapest``): which model serves it is the
provider's business, and correctness never rests on it. Every plan the pool makes is recorded (``plans``, append-only)
and the hub records it in the signed verdicts audit of every review it runs (``RouterHub.review_pool``).

Instances are overseer agents like any other: they read a dossier and return a verdict that the intake, validation and
combination treat as data. They never certify anything, never change a status or a clearance, and stay advisory: the
verdicts of the instances that reviewed one dossier are combined by the existing rule (``combine_verdicts``: no voting on
facts; agreement between instances is never evidence).
"""
from __future__ import annotations

import math
import re
import threading
from typing import Any, Callable, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..ir.canonical import canonical_json, sha256_hex
from .pack import KnowledgePack
from .runner import OverseerAgentRunner
from .verdicts import HEADER_ID_PATTERN, Lens, Mode, PackIdentity

__all__ = [
    "DEFAULT_MAX_INSTANCES", "DEFAULT_PER_INSTANCE_QUOTA", "MIN_REPEAT_REVIEWERS", "HARD_MAX_INSTANCES", "MODEL_TIER", "PoolConfig", "PoolItem",
    "PoolPlan", "plan_pool", "OverseerPool",
]

DEFAULT_MAX_INSTANCES = 4
DEFAULT_PER_INSTANCE_QUOTA = 8
#: Independent instances every repeated-fault dossier goes to.
MIN_REPEAT_REVIEWERS = 2
#: No configuration may plan more instances than this.
HARD_MAX_INSTANCES = 64
#: The tier deployed overseer agents run on. Correctness rests on the deterministic code and the signed engine results.
MODEL_TIER = "cheapest"
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


class PoolItem(BaseModel):
    """One dossier of a batch: its key (the hub uses the channel uid), the repeated faults in its task and the risk signals
    its task carries (the classes of :data:`~epinoic_logic.overseer.emitted.RISK_CLASSES`, sorted and unique)."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    key: str = Field(pattern=_KEY_PATTERN)
    repeated_faults: int = Field(default=0, ge=0)
    risk_signals: tuple[str, ...] = Field(default=(), strict=False)  # a JSON list re-validates (a plan read back from its dump)
    risk_records: tuple[str, ...] = Field(default=(), strict=False)

    @model_validator(mode="after")
    def _signals(self) -> "PoolItem":
        from .emitted import RISK_CLASSES
        for xs in (self.risk_signals, self.risk_records):
            if any(x not in RISK_CLASSES for x in xs) or list(xs) != sorted(set(xs)):
                raise ValueError("risk signals and records are classes of emitted.RISK_CLASSES, sorted and unique")
        return self

    @property
    def units(self) -> int:
        """The review units the dossier weighs: one, two when it is escalated or carries risk records."""
        return MIN_REPEAT_REVIEWERS if (self.escalated or self.risk_records) else 1

    @property
    def escalated(self) -> bool:
        """Whether the dossier goes to two independent instances: a repeated fault or a risk signal."""
        return bool(self.repeated_faults or self.risk_signals)


class PoolPlan(BaseModel):
    """How many instances review a batch and which instance reviews which dossier. Never more instances than
    ``config.max_instances``; every repeated-fault dossier goes to at least two distinct instances."""
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
        if set(self.assignments) != {it.key for it in self.items}:
            raise ValueError("every dossier, and only those, is assigned")
        return self

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


def plan_pool(items: Sequence[PoolItem], config: PoolConfig, pack: PackIdentity) -> PoolPlan:
    """The deterministic plan for a batch (module docstring). ``ValueError`` on a duplicated key or a configuration outside
    the pool's bounds (re-validated here, so a config copied around validation is refused)."""
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
    repeated = [it for it in its if it.repeated_faults]
    risky = [it for it in its if it.risk_signals and not it.repeated_faults]
    escalated = repeated + risky
    weighted = [it for it in its if it.risk_records and not it.escalated]
    units = sum(it.units for it in its)
    reasons: list[str] = []
    if not its:
        needed = 0
        reasons.append("empty batch: no instance")
    else:
        needed = 1
        reasons.append("one instance by default")
        by_quota = math.ceil(units / config.per_instance_quota)
        if by_quota > 1:
            needed = by_quota
            reasons.append(f"{units} review units exceed the per-instance quota of {config.per_instance_quota}: {by_quota} instances needed")
        if repeated:
            needed = max(needed, MIN_REPEAT_REVIEWERS)
            reasons.append(f"{len(repeated)} dossier(s) with repeated faults: each goes to {MIN_REPEAT_REVIEWERS} independent instances")
        if risky:
            needed = max(needed, MIN_REPEAT_REVIEWERS)
            classes = sorted({x for it in risky for x in it.risk_signals})
            reasons.append(f"{len(risky)} dossier(s) with risk signals ({', '.join(classes)}): each goes to {MIN_REPEAT_REVIEWERS} independent instances "
                           "(a signal only ever escalates oversight)")
        if weighted:
            records = sorted({x for it in weighted for x in it.risk_records})
            reasons.append(f"{len(weighted)} dossier(s) with risk records only ({', '.join(records)}): each weighs {MIN_REPEAT_REVIEWERS} review units "
                           "toward the quota (a record only ever escalates oversight)")
    count = min(needed, config.max_instances)
    capped = needed > config.max_instances
    if capped:
        reasons.append(f"capped at the maximum of {config.max_instances} instances (needed {needed})")
    instances = [f"{config.base_agent_id}-{n}" for n in range(1, count + 1)]
    for a in instances:
        if not re.match(HEADER_ID_PATTERN, a):
            raise ValueError(f"instance id {a!r} is not a valid agent id")
    loads = {a: 0 for a in instances}
    assignments: dict[str, list[str]] = {}
    for it in [*repeated, *risky, *[x for x in its if not x.escalated]]:
        want = MIN_REPEAT_REVIEWERS if it.escalated else 1
        chosen = sorted(instances, key=lambda a: (loads[a], instances.index(a)))[:want]
        for a in chosen:
            loads[a] += 1 if it.escalated else it.units
        assignments[it.key] = sorted(chosen, key=instances.index)
    over = any(v > config.per_instance_quota for v in loads.values())
    if over:
        reasons.append(f"an instance carries {max(loads.values())} review units, over the quota of {config.per_instance_quota}: disclosed, the plan stays at the maximum")
    body = {"config": config.model_dump(mode="json"), "pack": pack.model_dump(mode="json"), "items": [it.model_dump(mode="json") for it in its],
            "instances": instances, "assignments": assignments}
    return PoolPlan(plan_id="pool-" + _plan_digest(body), config=config, pack=pack, items=its, instances=instances, assignments=assignments, loads=loads,
                    review_units=units, needed_instances=needed, capped=capped, over_quota=over, reasons=reasons)


class OverseerPool:
    """Overseer-agent instances built from ONE loaded knowledge pack, sized per batch by :func:`plan_pool`.

    ``provider_factory(agent_id)`` returns the completion provider of one instance (called once per instance id). The
    pool holds no key and builds nothing but :class:`OverseerAgentRunner` instances from its pack."""

    def __init__(self, pack: KnowledgePack, provider_factory: Callable[[str], Any], *, config: Optional[PoolConfig] = None) -> None:
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
        self._plans: list[PoolPlan] = []
        self._runners: dict[str, OverseerAgentRunner] = {}
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"OverseerPool(pack={self._pack.identity.label!r}, max_instances={self.config.max_instances}, quota={self.config.per_instance_quota})"

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
        """Plan a batch and record the plan."""
        p = plan_pool(items, self.config, self._pack.identity)
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
