"""The router port's pool operation (``epinoic.integration.router-port.v1``, pool port version 1.1; ``integration/PROTOCOL.md``
section 7b): how the overseer pool asks the flash router which overseer instances review which dossiers of a batch.

The flash router (the sub-project ``flash-router/``, package ``epinoic_flash_router``) is the oversight planner's
decision maker, a separate and independent agent edited and released apart from the Z3 infrastructure, the STEM support
and the overseer. It is not the translator's ``RouterHub`` (which carries messages between agents) and not the website's
subject routing. Beside the service's ``hello()`` and ``plan(request_json)`` (section 7a, ``router_port``) it exposes two
functions for the overseer pool:

* ``pool_hello() -> str``: one ``pool-router-hello.v1`` document: its identity (name, version, the digests of its rules
  and of its cost data), the capability ``pool-plan``, the pool port version it speaks, the methods and profiles it may
  plan, the cheapest tier and ``deterministic: true``;
* ``pool_plan(request_json) -> str``: one ``pool-routing-plan.v1`` document for one ``pool-routing-request.v1``.

**Attached by capability.** The overseer pool attaches a router module through this port (:func:`attach_pool_router`):
the router runs in its own process (``router_child``, as the service runs it), and it is attached for the pool only when
its module exposes both pool functions and its pool hello declares the ``pool-plan`` capability at a pool port version
the overseer speaks (:data:`POOL_PORT_VERSIONS`); otherwise it is refused with ``KIT-RT-015`` (``KIT-RT-016`` when it
fails) and the overseer's floor plan runs. :func:`attach_pool_router_in_process` attaches two in-process functions for
tests and tools only: a deployment attaches a router by its module name, so its code never runs in the overseer's
process.

**Features only.** A request carries, per dossier, a positional id (``d1``, ``d2``, ... in the overseer's key order: never
a channel uid, a task key or a fault label), its repeated faults, its risk signals and records (the closed classes of
:data:`POOL_RISK_CLASSES`) and whether the overseer's escalation advisor escalated it; and the pool's limits. A plan
carries closed vocabularies, integers, the request's own item ids and digests, and the router's identity: instance
NUMBERS (the overseer names its instances), never text, never a model.

**This module holds no floor.** It is the contract both sides share: the three documents with closed key sets, their
validation (:func:`check_pool_request`, :func:`check_pool_hello`, :func:`check_pool_plan`: shape, binding, identity and
the facts a plan states about its request), and the attachment. The minimum-oversight floor of the pool is the
overseer's (``epinoic_overseer.floor``): a plan in contract runs only when the overseer finds it at or above its floor,
else the overseer refuses it (``KIT-RT-020``) and runs its floor plan. So the router can add oversight, never remove it,
and how the router is edited never decides whether a dossier is reviewed less than its risk signals call for.

Standard library and pydantic only: nothing here imports the engine, Z3 or the overseer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import partial
from typing import Annotated, Any, Callable, Literal, Mapping, Optional, Sequence, Union

from pydantic import Field, StringConstraints, ValidationError, model_validator

from . import router_child as _child
from .canonical import CanonicalError, canonical_json, loads_strict, sha256_json
from .errors import IntegrationError
from .protocol import FLOOR_IDENTITY_PREFIX, PROTOCOL, Frozen, RouterIdentity, Sha256, dump
from .router_port import HARD_MAX_INSTANCES, HELLO_TIMEOUT_S, PLAN_TIMEOUT_S, _hidden, _model_named, _model_value
from .router_port import RouterFailure

__all__ = [
    "POOL_PORT_VERSION", "POOL_PORT_VERSIONS", "POOL_REQUEST_SCHEMA", "POOL_PLAN_SCHEMA", "POOL_HELLO_SCHEMA", "POOL_CAPABILITY",
    "POOL_METHODS", "POOL_RUN_METHODS", "POOL_RISK_CLASSES", "POOL_REASON_CODES", "POOL_REASON_PARAMETERS", "MAX_POOL_ITEMS",
    "PoolItemFeatures", "PoolLimits", "PoolRoutingRequest", "PoolRouterHello", "PoolAssignment", "PoolReason", "PoolRoutingPlan",
    "PoolRouterAttachment", "PoolAnswer", "item_id", "pool_request_digest", "build_pool_request", "check_pool_request",
    "check_pool_hello", "check_pool_plan", "attach_pool_router", "attach_pool_router_in_process", "ask_pool_router",
]

#: The version of the pool documents (a minor addition to router port 1.0: the service's documents are unchanged).
POOL_PORT_VERSION = "1.1"
#: The pool port versions the overseer speaks: a pool hello naming any other is refused (``KIT-RT-015``), the floor runs.
POOL_PORT_VERSIONS: tuple[str, ...] = ("1.1",)
POOL_REQUEST_SCHEMA = "epinoic.integration.pool-routing-request.v1"
POOL_PLAN_SCHEMA = "epinoic.integration.pool-routing-plan.v1"
POOL_HELLO_SCHEMA = "epinoic.integration.pool-router-hello.v1"
#: The capability a pool hello must declare for the overseer pool to attach the router.
POOL_CAPABILITY = "pool-plan"
#: Every method of the router port's method table (section 7a.1).
POOL_METHODS: tuple[str, ...] = ("IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD")
#: The methods a pool dossier is reviewed by in pool port 1.1: one instance reading it whole (``IN_DEPTH``) or independent
#: duplicate reviews (``DUPLICATE``). Dividing one dossier (``SPLIT``) and the combined answer's ``N_FOLD`` are in the
#: method table for a planner later; a 1.1 plan that uses them is refused (``KIT-RT-007``).
POOL_RUN_METHODS: tuple[str, ...] = ("IN_DEPTH", "DUPLICATE")
#: The overseer's risk classes (``epinoic_overseer.emitted.RISK_CLASSES``; the overseer checks at import that they are these).
POOL_RISK_CLASSES: tuple[str, ...] = ("named_defect", "writer_assumption", "unchecked_source", "stem_method", "encoding_conflict", "contradiction",
                                      "withheld_verdict", "rejection", "diagnosis_incomplete", "integrity_error")
#: Why a pool plan has its size: closed codes, each with exactly the integer and class parameters of
#: :data:`POOL_REASON_PARAMETERS` (the overseer renders them in words; a plan carries no free text).
POOL_REASON_CODES: tuple[str, ...] = ("pool_empty", "pool_baseline", "pool_volume", "pool_repeated_faults", "pool_risk_signals",
                                      "pool_advised", "pool_risk_records", "pool_capped", "pool_over_quota")
POOL_REASON_PARAMETERS: Mapping[str, tuple[str, ...]] = {
    "pool_empty": (), "pool_baseline": (), "pool_volume": ("units", "quota", "instances"),
    "pool_repeated_faults": ("count", "reviewers"), "pool_risk_signals": ("count", "classes", "reviewers"),
    "pool_advised": ("count", "reviewers"), "pool_risk_records": ("count", "classes", "weight"),
    "pool_capped": ("maximum", "needed"), "pool_over_quota": ("load", "quota"),
}
#: The most dossiers one batch carries.
MAX_POOL_ITEMS = 4096
_MAX_COUNT = 1_000_000

_ItemId = Annotated[str, StringConstraints(pattern=r"^d[1-9][0-9]{0,5}$")]
_Key = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,128}$")]
_RiskClass = Literal["named_defect", "writer_assumption", "unchecked_source", "stem_method", "encoding_conflict", "contradiction",
                     "withheld_verdict", "rejection", "diagnosis_incomplete", "integrity_error"]
_Method = Literal["IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD"]
_Profile = Literal["standard", "fast"]
_Capability = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,31}$")]
_Count = Annotated[int, Field(ge=0, le=_MAX_COUNT)]
_ReasonCode = Literal["pool_empty", "pool_baseline", "pool_volume", "pool_repeated_faults", "pool_risk_signals", "pool_advised",
                      "pool_risk_records", "pool_capped", "pool_over_quota"]


def item_id(position: int) -> str:
    """The positional id of the dossier at ``position`` (0-based) of a batch in the overseer's key order."""
    return f"d{position + 1}"


def _sorted_unique(xs: Sequence[str]) -> bool:
    return list(xs) == sorted(set(xs))


# --------------------------------------------------------------------------------------------- the request


class PoolItemFeatures(Frozen):
    """One dossier of the batch as features: its position, the repeated faults of its task, the risk signals and the
    risk records its task carries (the overseer's ``emitted.risk_reading``) and whether the escalation advisor escalated
    it. Never its key, its text or a finding."""
    item_id: _ItemId
    repeated_faults: _Count
    risk_signals: list[_RiskClass] = Field(default_factory=list, max_length=len(POOL_RISK_CLASSES))
    risk_records: list[_RiskClass] = Field(default_factory=list, max_length=len(POOL_RISK_CLASSES))
    advised: bool = False

    @model_validator(mode="after")
    def _classes(self) -> "PoolItemFeatures":
        if not _sorted_unique(self.risk_signals) or not _sorted_unique(self.risk_records):
            raise ValueError("risk signals and records are sorted and unique")
        return self


class PoolLimits(Frozen):
    """The pool's configuration as the router may read it: its maximum of instances, its per-instance quota of review
    units and the overseer-agent profiles the overseer offers."""
    max_instances: int = Field(ge=2, le=HARD_MAX_INSTANCES)
    per_instance_quota: int = Field(ge=1, le=100_000)
    profiles: list[_Profile] = Field(min_length=1, max_length=2)


class PoolRoutingRequest(Frozen):
    schema_: Literal["epinoic.integration.pool-routing-request.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.1"]
    items: list[PoolItemFeatures] = Field(default_factory=list, max_length=MAX_POOL_ITEMS)
    limits: PoolLimits

    model_config = Frozen.model_config | {"populate_by_name": True}

    @model_validator(mode="after")
    def _positions(self) -> "PoolRoutingRequest":
        if [it.item_id for it in self.items] != [item_id(i) for i in range(len(self.items))]:
            raise ValueError("the items are d1, d2, ... in order (their positions in the overseer's key order)")
        return self


# --------------------------------------------------------------------------------------------- the hello


class PoolRouterHello(Frozen):
    """What a flash router says about its pool capability when the overseer pool attaches it."""
    schema_: Literal["epinoic.integration.pool-router-hello.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,3}\.[0-9]{1,3}$")]
    router: RouterIdentity
    capabilities: list[_Capability] = Field(min_length=1, max_length=8)
    methods: list[_Method] = Field(min_length=1, max_length=4)
    profiles: list[_Profile] = Field(min_length=1, max_length=2)
    tier: Literal["cheapest"]
    deterministic: Literal[True]

    model_config = Frozen.model_config | {"populate_by_name": True}


# --------------------------------------------------------------------------------------------- the plan


class PoolAssignment(Frozen):
    """How one dossier is reviewed: its method and the instance numbers (1 to the plan's ``instances``) that review it."""
    item_id: _ItemId
    method: _Method
    instances: list[Annotated[int, Field(ge=1, le=HARD_MAX_INSTANCES)]] = Field(min_length=1, max_length=HARD_MAX_INSTANCES)


class PoolReason(Frozen):
    """One reason of a plan: a closed code and exactly its parameters (:data:`POOL_REASON_PARAMETERS`)."""
    code: _ReasonCode
    count: Optional[_Count] = None
    reviewers: Optional[Annotated[int, Field(ge=1, le=HARD_MAX_INSTANCES)]] = None
    classes: Optional[list[_RiskClass]] = Field(default=None, max_length=len(POOL_RISK_CLASSES))
    weight: Optional[Annotated[int, Field(ge=1, le=1000)]] = None
    units: Optional[_Count] = None
    quota: Optional[Annotated[int, Field(ge=1, le=100_000)]] = None
    instances: Optional[_Count] = None
    maximum: Optional[Annotated[int, Field(ge=1, le=HARD_MAX_INSTANCES)]] = None
    needed: Optional[_Count] = None
    load: Optional[_Count] = None

    @model_validator(mode="after")
    def _parameters(self) -> "PoolReason":
        wanted = set(POOL_REASON_PARAMETERS[self.code])
        given = {k for k in ("count", "reviewers", "classes", "weight", "units", "quota", "instances", "maximum", "needed", "load")
                 if getattr(self, k) is not None}
        if given != wanted:
            raise ValueError(f"reason {self.code} takes exactly {sorted(wanted)}")
        if self.classes is not None and (not self.classes or not _sorted_unique(self.classes)):
            raise ValueError("a reason's classes are sorted, unique and not empty")
        return self


class PoolCost(Frozen):
    tokens: int = Field(ge=0, le=1_000_000_000)
    seconds: int = Field(ge=0, le=1_000_000)


class PoolRoutingPlan(Frozen):
    schema_: Literal["epinoic.integration.pool-routing-plan.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.1"]
    origin: Literal["router"]
    plan_id: _Key
    request_sha256: Sha256
    router: RouterIdentity
    profile: _Profile
    instances: Annotated[int, Field(ge=0, le=HARD_MAX_INSTANCES)]
    assignments: list[PoolAssignment] = Field(max_length=MAX_POOL_ITEMS)
    loads: list[_Count] = Field(max_length=HARD_MAX_INSTANCES)
    review_units: _Count
    needed_instances: _Count
    capped: bool
    over_quota: bool
    reasons: list[PoolReason] = Field(min_length=1, max_length=len(POOL_REASON_CODES))
    estimated_cost: Optional[PoolCost] = None

    model_config = Frozen.model_config | {"populate_by_name": True}


# --------------------------------------------------------------------------------------------- building and validation


def pool_request_digest(request: Union[PoolRoutingRequest, dict]) -> str:
    return sha256_json(dump(request) if isinstance(request, PoolRoutingRequest) else request)


def _parsed(raw: Any, code: str) -> Any:
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            return loads_strict(raw)
        except CanonicalError as exc:
            raise IntegrationError(code, f"not protocol JSON: {exc}") from None
    return raw


def build_pool_request(items: Sequence[Mapping[str, Any]], *, max_instances: int, per_instance_quota: int,
                       profiles: Sequence[str] = ("standard",)) -> PoolRoutingRequest:
    """The pool routing request of a batch: ``items`` in the overseer's key order, each a mapping of ``repeated_faults``,
    ``risk_signals``, ``risk_records`` and ``advised`` (its key is never sent; its position is its id). Validated
    (``KIT-RT-014`` on anything out of contract)."""
    raw = {"schema": POOL_REQUEST_SCHEMA, "protocol": PROTOCOL, "port_version": POOL_PORT_VERSION,
           "items": [{"item_id": item_id(i), "repeated_faults": int(it["repeated_faults"]), "risk_signals": list(it.get("risk_signals", ())),
                      "risk_records": list(it.get("risk_records", ())), "advised": bool(it.get("advised", False))} for i, it in enumerate(items)],
           "limits": {"max_instances": int(max_instances), "per_instance_quota": int(per_instance_quota), "profiles": list(profiles)}}
    return check_pool_request(raw)


def check_pool_request(raw: Any) -> PoolRoutingRequest:
    """Validate a pool routing request (the overseer builds it; the router receives it): ``KIT-RT-014`` for anything out
    of contract, ``KIT-RT-011`` when it carries what a blind dossier hides."""
    data = _parsed(raw, "KIT-RT-014")
    if not isinstance(data, dict):
        raise IntegrationError("KIT-RT-014", "a pool routing request is a JSON object")
    hidden = _hidden(data)
    if hidden:
        raise IntegrationError("KIT-RT-011", f"the request carries {hidden}, which a blind dossier hides")
    try:
        return PoolRoutingRequest.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError("KIT-RT-014", f"the pool request does not validate ({exc.error_count()} error(s))") from None


def check_pool_hello(raw: Any) -> PoolRouterHello:
    """Validate a router's pool hello: the version handshake and the capability. ``KIT-RT-015`` when it is out of contract,
    names a model, names the floor's reserved identity, speaks a pool port version the overseer does not speak, or does
    not declare the ``pool-plan`` capability."""
    data = _parsed(raw, "KIT-RT-015")
    if not isinstance(data, dict):
        raise IntegrationError("KIT-RT-015", "a pool router hello is a JSON object")
    if _model_named(data) or _model_value((data.get("router") or {}).get("name") if isinstance(data.get("router"), dict) else None):
        raise IntegrationError("KIT-RT-015", "a router hello names no model: every overseer instance runs on the cheapest tier")
    version = data.get("port_version")
    if isinstance(version, str) and re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}", version) and version not in POOL_PORT_VERSIONS:
        raise IntegrationError("KIT-RT-015", f"the router speaks pool port version {version}; the overseer speaks {', '.join(POOL_PORT_VERSIONS)}")
    try:
        hello = PoolRouterHello.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError("KIT-RT-015", f"the pool hello does not validate ({exc.error_count()} error(s))") from None
    if hello.port_version not in POOL_PORT_VERSIONS:  # pragma: no cover - the pattern and the check above decide it
        raise IntegrationError("KIT-RT-015", f"the router speaks pool port version {hello.port_version}")
    if POOL_CAPABILITY not in hello.capabilities:
        raise IntegrationError("KIT-RT-015", f"the router does not declare the {POOL_CAPABILITY} capability")
    if hello.router.name.startswith(FLOOR_IDENTITY_PREFIX):
        raise IntegrationError("KIT-RT-015", "a router hello names the minimum-oversight floor's reserved identity")
    return hello


_LOCATION_CODES = (("reasons", "KIT-RT-012"), ("estimated_cost", "KIT-RT-013"), ("loads", "KIT-RT-013"), ("review_units", "KIT-RT-013"),
                   ("needed_instances", "KIT-RT-013"), ("method", "KIT-RT-007"), ("assignments", "KIT-RT-007"), ("profile", "KIT-RT-010"),
                   ("instances", "KIT-RT-008"))


def _validation_code(exc: ValidationError) -> str:
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ())]
        if err.get("type") in ("extra_forbidden", "missing"):
            return "KIT-RT-001"
        for name, code in _LOCATION_CODES:
            if name in loc:
                return code
    return "KIT-RT-001"


def check_pool_plan(raw: Any, request: PoolRoutingRequest, *, hello: PoolRouterHello) -> PoolRoutingPlan:
    """Validate a router's pool plan against its request and the attached router's pool hello. Raises
    :class:`IntegrationError` with the ``KIT-RT`` code of the first rule it breaks (PROTOCOL.md section 7b.4). It does NOT
    apply the floor: the overseer does (``KIT-RT-020``)."""
    data = _parsed(raw, "KIT-RT-001")
    if not isinstance(data, dict):
        raise IntegrationError("KIT-RT-001", "a pool routing plan is a JSON object")
    hidden = _hidden(data)
    if hidden:
        raise IntegrationError("KIT-RT-011", f"the plan carries {hidden}, which a blind dossier hides")
    router = data.get("router")
    named = _model_named(data) or _model_value(data.get("plan_id"), router.get("name") if isinstance(router, dict) else None)
    if named:
        raise IntegrationError("KIT-RT-009", f"the plan carries {named}: no plan names a model; every instance runs on the cheapest tier")
    try:
        plan = PoolRoutingPlan.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError(_validation_code(exc), f"the pool plan does not validate ({exc.error_count()} error(s))") from None
    if plan.router.name.startswith(FLOOR_IDENTITY_PREFIX):
        raise IntegrationError("KIT-RT-003", "a router's plan cannot present itself as the overseer's floor plan")
    if plan.request_sha256 != pool_request_digest(request):
        raise IntegrationError("KIT-RT-002", "the plan is not bound to this request (request digest differs)")
    if plan.router != hello.router:
        raise IntegrationError("KIT-RT-003", "the plan's router identity is not the attached router's")
    items = {it.item_id: it for it in request.items}
    keys = [a.item_id for a in plan.assignments]
    if any(k not in items for k in keys):
        raise IntegrationError("KIT-RT-004", "the plan names a dossier the request does not hold")
    if len(set(keys)) != len(keys):
        raise IntegrationError("KIT-RT-006", "the plan names one dossier twice")
    if set(keys) != set(items):
        raise IntegrationError("KIT-RT-005", "the plan leaves a dossier of the request without a review")
    for a in plan.assignments:
        if a.method not in POOL_RUN_METHODS:
            raise IntegrationError("KIT-RT-007", f"pool port {POOL_PORT_VERSION} reviews a dossier IN_DEPTH or DUPLICATE ({a.method} is for a planner later)")
        if a.method not in hello.methods:
            raise IntegrationError("KIT-RT-007", "the plan uses a method its router's pool hello does not declare")
        if len(set(a.instances)) != len(a.instances):
            raise IntegrationError("KIT-RT-007", "a dossier names one instance twice")
        if (a.method == "IN_DEPTH") != (len(a.instances) == 1):
            raise IntegrationError("KIT-RT-007", "IN_DEPTH is one instance reading the dossier whole; DUPLICATE is at least two independent ones")
    if plan.profile not in request.limits.profiles or plan.profile not in hello.profiles:
        raise IntegrationError("KIT-RT-010", "the plan uses an overseer profile that is not available")
    maximum = min(request.limits.max_instances, HARD_MAX_INSTANCES)
    if plan.instances > maximum:
        raise IntegrationError("KIT-RT-008", f"the plan has {plan.instances} instances, over the pool's maximum of {maximum}")
    if any(n > plan.instances for a in plan.assignments for n in a.instances):
        raise IntegrationError("KIT-RT-008", "an assignment names an instance the plan does not have")
    if bool(request.items) != (plan.instances >= 1):
        raise IntegrationError("KIT-RT-008", "a batch with dossiers has at least one instance, an empty batch none")
    codes = [r.code for r in plan.reasons]
    if len(set(codes)) != len(codes):
        raise IntegrationError("KIT-RT-012", "a reason is listed twice")
    problem = _accounting_problem(plan, request) or _reasons_problem(plan, request)
    if problem:
        raise IntegrationError(*problem)
    return plan


def _accounting_problem(plan: PoolRoutingPlan, request: PoolRoutingRequest) -> Optional[tuple[str, str]]:
    """The plan's own numbers must agree with each other (``KIT-RT-013``)."""
    if len(plan.loads) != plan.instances:
        return ("KIT-RT-013", "the plan has one load per instance")
    per_instance = [0] * plan.instances
    for a in plan.assignments:
        for n in a.instances:
            per_instance[n - 1] += 1
    if any(load < count for load, count in zip(plan.loads, per_instance)):
        return ("KIT-RT-013", "an instance's load is less than the dossiers assigned to it")
    if not (sum(per_instance) <= sum(plan.loads) <= plan.review_units):
        return ("KIT-RT-013", "the review units do not account for the loads")
    maximum = min(request.limits.max_instances, HARD_MAX_INSTANCES)
    if plan.instances != min(plan.needed_instances, maximum) or plan.capped != (plan.needed_instances > maximum):
        return ("KIT-RT-013", "the instances are the needed instances within the maximum, and capped says whether the maximum binds")
    if plan.over_quota != any(load > request.limits.per_instance_quota for load in plan.loads):
        return ("KIT-RT-013", "over_quota says whether an instance carries more than the pool's per-instance quota")
    return None


def _reasons_problem(plan: PoolRoutingPlan, request: PoolRoutingRequest) -> Optional[tuple[str, str]]:
    """A reason states only what the plan and the request hold (``KIT-RT-012``): the dossiers it counts and the classes
    it names are the request's, its numbers the plan's."""
    items = request.items
    repeated = [it for it in items if it.repeated_faults]
    risky = [it for it in items if it.risk_signals and not it.repeated_faults]
    advised = [it for it in items if it.advised and not it.repeated_faults and not it.risk_signals]
    escalated = {it.item_id for it in (*repeated, *risky, *advised)}
    weighted = [it for it in items if it.risk_records and it.item_id not in escalated]
    by_code = {r.code: r for r in plan.reasons}
    bad = "KIT-RT-012"
    if ("pool_empty" in by_code) == bool(items) or ("pool_baseline" in by_code) != bool(items):
        return (bad, "an empty batch says so, a batch with dossiers names its baseline")
    if ("pool_capped" in by_code) != plan.capped or ("pool_over_quota" in by_code) != plan.over_quota:
        return (bad, "a plan says when its maximum binds and when an instance is over the quota, and only then")
    expected = {
        "pool_repeated_faults": (len(repeated), None),
        "pool_risk_signals": (len(risky), sorted({c for it in risky for c in it.risk_signals})),
        "pool_advised": (len(advised), None),
        "pool_risk_records": (len(weighted), sorted({c for it in weighted for c in it.risk_records})),
    }
    for code, (count, classes) in expected.items():
        r = by_code.get(code)
        if r is not None and (count == 0 or r.count != count or (classes is not None and r.classes != classes)):
            return (bad, f"reason {code} does not state the request's dossiers and classes")
    r = by_code.get("pool_capped")
    if r is not None and (r.maximum != min(request.limits.max_instances, HARD_MAX_INSTANCES) or r.needed != plan.needed_instances):
        return (bad, "the capped reason states the pool's maximum and the plan's needed instances")
    r = by_code.get("pool_over_quota")
    if r is not None and (r.quota != request.limits.per_instance_quota or r.load != max(plan.loads, default=0)):
        return (bad, "the over-quota reason states the pool's quota and the largest load")
    r = by_code.get("pool_volume")
    if r is not None and (r.units != plan.review_units or r.instances != -(-r.units // r.quota) or r.instances < 2):
        return (bad, "the volume reason states the plan's review units and the instances they need at its quota")
    return None


# --------------------------------------------------------------------------------------------- the attachment


@dataclass(frozen=True)
class PoolRouterAttachment:
    """A flash router attached for the overseer pool: its validated pool hello and its plan function, or why none is
    attached. ``plan_fn(request_json, timeout_s)`` returns the router's answer text or raises :class:`RouterFailure`.
    ``plan_timeout_s`` bounds every plan. ``in_process`` is true only for :func:`attach_pool_router_in_process` (tests
    and tools)."""
    hello: Optional[PoolRouterHello]
    plan_fn: Optional[Callable[[str, float], Any]]
    refusal: Optional[str]
    detail: str
    module: Optional[str] = None
    plan_timeout_s: float = PLAN_TIMEOUT_S
    in_process: bool = False

    @property
    def attached(self) -> bool:
        return self.hello is not None and self.plan_fn is not None

    @property
    def identity(self) -> Optional[RouterIdentity]:
        return self.hello.router if self.hello is not None else None


@dataclass(frozen=True)
class PoolAnswer:
    """One pool router call: the parsed answer (``data``), or the refusal code and why there is none."""
    data: Any
    refusal: Optional[str]
    detail: str


def _run_pool(module: str, op: str, request_json: Optional[str], timeout_s: float) -> str:
    return _child.launch(module, op, request_json, timeout_s)


def attach_pool_router(spec: Optional[str], *, timeout_s: float = HELLO_TIMEOUT_S, plan_timeout_s: float = PLAN_TIMEOUT_S,
                       require_secret_boundary: bool = False) -> PoolRouterAttachment:
    """Attach the flash router named by ``spec`` (a module path) for the overseer pool, by capability: its
    ``pool_hello()`` is called in the router's own process and validated (:func:`check_pool_hello`). ``None``, empty or
    ``"none"``: no router (no refusal). A module that cannot be imported or fails: ``KIT-RT-016``; a module without
    ``pool_hello()`` and ``pool_plan()``, or whose pool hello is out of contract, speaks another pool port version or
    does not declare the ``pool-plan`` capability: ``KIT-RT-015``. The pool runs its floor plan either way."""
    if spec is None or spec.strip() in ("", "none"):
        return PoolRouterAttachment(None, None, None, "no router configured: the floor plan runs")
    name = spec.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", name):
        return PoolRouterAttachment(None, None, "KIT-RT-015", "the router module name is not a Python module path")
    if require_secret_boundary:
        problem = _child.boundary_problem()
        if problem is not None:
            return PoolRouterAttachment(None, None, "KIT-RT-016", f"{problem}: a router is started only where it cannot read the keys, so the floor plan runs")
    try:
        text = _run_pool(name, "pool_hello", None, timeout_s)
    except RouterFailure as exc:
        return PoolRouterAttachment(None, None, exc.code, f"{exc.detail}: the floor plan runs")
    try:
        hello = check_pool_hello(text)
    except IntegrationError as exc:
        code = "KIT-RT-016" if exc.code == "KIT-RT-015" and exc.detail.startswith("not protocol JSON") else exc.code
        return PoolRouterAttachment(None, None, code, exc.detail)
    return PoolRouterAttachment(hello, partial(_run_pool, name, "pool_plan"), None, "", module=name, plan_timeout_s=plan_timeout_s)


def attach_pool_router_in_process(hello_fn: Callable[[], Any], plan_fn: Callable[[str], Any], *,
                                  plan_timeout_s: float = PLAN_TIMEOUT_S) -> PoolRouterAttachment:
    """Attach two in-process functions as the pool's router (tests and tools only: a deployment attaches a router by its
    module name, :func:`attach_pool_router`, so its code never runs in the overseer's process). The hello is validated
    as :func:`attach_pool_router` validates it; whatever the functions raise is a failed router (``KIT-RT-016``)."""
    try:
        text = hello_fn()
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - whatever an in-process router raises, the floor runs
        return PoolRouterAttachment(None, None, "KIT-RT-016", f"the router failed its pool hello ({type(exc).__name__})")
    if not isinstance(text, str):
        return PoolRouterAttachment(None, None, "KIT-RT-016", "the router answered its pool hello with something other than JSON text")
    try:
        hello = check_pool_hello(text)
    except IntegrationError as exc:
        return PoolRouterAttachment(None, None, exc.code, exc.detail)
    return PoolRouterAttachment(hello, lambda request_json, _timeout_s: plan_fn(request_json), None, "", module=None,
                                plan_timeout_s=plan_timeout_s, in_process=True)


def ask_pool_router(request: PoolRoutingRequest, attachment: PoolRouterAttachment, *, timeout_s: Optional[float] = None) -> PoolAnswer:
    """Ask the attached router for the pool plan of ``request``, waiting at most ``timeout_s`` (the attachment's
    ``plan_timeout_s`` by default). Never raises for anything the router does: a router that fails, answers with
    something other than JSON text or does not answer in time gives ``KIT-RT-016``; the JSON it answers is returned for
    :func:`check_pool_plan`."""
    if not attachment.attached:
        return PoolAnswer(None, attachment.refusal, attachment.detail or "no router is attached")
    wait = attachment.plan_timeout_s if timeout_s is None else timeout_s
    if wait <= 0:
        return PoolAnswer(None, "KIT-RT-016", "no time was left for the router: the floor plan runs")
    try:
        raw = attachment.plan_fn(canonical_json(dump(request)), wait)  # type: ignore[misc]
    except RouterFailure as exc:
        return PoolAnswer(None, exc.code, exc.detail)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - an in-process plan function (tests, tools): whatever it raises, the floor runs
        return PoolAnswer(None, "KIT-RT-016", f"the router failed ({type(exc).__name__})")
    if not isinstance(raw, str):
        return PoolAnswer(None, "KIT-RT-016", "the router answered with something other than JSON text")
    try:
        return PoolAnswer(loads_strict(raw), None, "")
    except CanonicalError:
        return PoolAnswer(None, "KIT-RT-016", "the router's answer is not JSON")
