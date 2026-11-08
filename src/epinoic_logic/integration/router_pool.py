"""The router port's pool operation (``epinoic.integration.router-port.v1``, pool port versions 1.1 and 1.2;
``integration/PROTOCOL.md`` section 7b): how the overseer pool asks the flash router which overseer instances review which
dossiers of a batch.

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
the overseer speaks (:data:`POOL_PORT_VERSIONS`: 1.1 and 1.2); otherwise it is refused with ``KIT-RT-015``
(``KIT-RT-016`` when it fails) and the overseer's floor plan runs. The overseer writes every request in the version the
router's pool hello names, and a plan is written in its request's version. :func:`attach_pool_router_in_process` attaches two in-process functions for
tests and tools only: a deployment attaches a router by its module name, so its code never runs in the overseer's
process.

**Features only.** A request carries, per dossier, a positional id (``d1``, ``d2``, ... in the overseer's key order: never
a channel uid, a task key or a fault label), its repeated faults, its risk signals and records (the closed classes of
:data:`POOL_RISK_CLASSES`) and whether the overseer's escalation advisor escalated it; and the pool's limits. A plan
carries closed vocabularies, integers, the request's own item ids and digests, and the router's identity: instance
NUMBERS (the overseer names its instances), never text, never a model.

**Pool port 1.2** (architecture step 3) adds, per dossier, the size features the flash decision maker prices (the
journaled transfers, their characters, whether the content is STEM or carries translations) and, for a **combined
answer** (a synthesis combining N >= 2 specialists' answers), its N **sources** and its **merged** part, each with its
own repeated faults, risk signals, records and size. A 1.2 plan reviews a combined answer ``N_FOLD``: one source
assignment per source (``IN_DEPTH`` or ``DUPLICATE``, the source reviews in parallel: no instance reviews two sources of
one dossier while the plan has instances to spare), the merged review's instances and the bounded request-scoped
temporary context (``scope: request``, ``contents: validated_outcomes``, at most :data:`~.router_port.CONTEXT_MAX_BYTES`
bytes, ``discard: after_request``); and every assignment carries the flash decision maker's **decision record**: the
approach (``in_depth`` or ``duplication``), the method, the features it read (the request item's own, echoed and
checked), the candidates it priced, the parts of an N_FOLD and its reasons, all closed vocabularies and integers
(:data:`DECISION_REASONS`, :data:`CANDIDATE_WHY`). A 1.1 request carries no combined answer, and its plans are exactly
1.1's.

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
from .router_port import CONTEXT_MAX_BYTES, HARD_MAX_INSTANCES, HELLO_TIMEOUT_S, PLAN_TIMEOUT_S, _hidden, _model_named, _model_value
from .router_port import RouterFailure

__all__ = [
    "POOL_PORT_VERSION", "POOL_PORT_VERSIONS", "POOL_REQUEST_SCHEMA", "POOL_PLAN_SCHEMA", "POOL_HELLO_SCHEMA", "POOL_CAPABILITY",
    "POOL_METHODS", "POOL_RUN_METHODS", "POOL_RUN_METHODS_BY_VERSION", "POOL_RISK_CLASSES", "POOL_REASON_CODES", "POOL_REASON_PARAMETERS",
    "POOL_REASON_CODES_12", "POOL_REASON_PARAMETERS_12", "DECISION_APPROACHES", "DECISION_REASONS", "CANDIDATE_WHY", "MAX_SOURCES", "MAX_POOL_ITEMS",
    "PoolItemFeatures", "PoolLimits", "PoolRoutingRequest", "PoolRouterHello", "PoolAssignment", "PoolReason", "PoolRoutingPlan",
    "PoolFeatures", "PoolPartFeatures", "PoolItemFeatures12", "PoolRoutingRequest12", "PoolSourceAssignment", "PoolContext", "PoolDecisionRead",
    "PoolCandidate", "PoolPartDecision", "PoolDecisionCost", "PoolDecision", "PoolAssignment12", "PoolReason12", "PoolRoutingPlan12",
    "PoolRouterAttachment", "PoolAnswer", "item_id", "pool_request_digest", "build_pool_request", "check_pool_request",
    "check_pool_hello", "check_pool_plan", "attach_pool_router", "attach_pool_router_in_process", "ask_pool_router",
]

#: The newest version of the pool documents (minor additions to router port 1.0: the service's documents are unchanged).
POOL_PORT_VERSION = "1.2"
#: The pool port versions the overseer speaks: a pool hello naming any other is refused (``KIT-RT-015``), the floor runs.
#: 1.1 (architecture step 2c) plans IN_DEPTH and DUPLICATE; 1.2 (architecture step 3) adds a combined answer's N_FOLD and
#: every dossier's decision record.
POOL_PORT_VERSIONS: tuple[str, ...] = ("1.1", "1.2")
POOL_REQUEST_SCHEMA = "epinoic.integration.pool-routing-request.v1"
POOL_PLAN_SCHEMA = "epinoic.integration.pool-routing-plan.v1"
POOL_HELLO_SCHEMA = "epinoic.integration.pool-router-hello.v1"
#: The capability a pool hello must declare for the overseer pool to attach the router.
POOL_CAPABILITY = "pool-plan"
#: Every method of the router port's method table (section 7a.1).
POOL_METHODS: tuple[str, ...] = ("IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD")
#: The methods a pool dossier is reviewed by, per pool port version: one instance reading it whole (``IN_DEPTH``) or
#: independent duplicate reviews (``DUPLICATE``); since 1.2 a combined answer's ``N_FOLD``. Dividing one dossier
#: (``SPLIT``) stays in the method table for a planner later; a plan that uses a method its version does not run is
#: refused (``KIT-RT-007``).
POOL_RUN_METHODS_BY_VERSION: Mapping[str, tuple[str, ...]] = {"1.1": ("IN_DEPTH", "DUPLICATE"), "1.2": ("IN_DEPTH", "DUPLICATE", "N_FOLD")}
#: The methods the newest pool port version runs.
POOL_RUN_METHODS: tuple[str, ...] = POOL_RUN_METHODS_BY_VERSION[POOL_PORT_VERSION]
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
#: Pool port 1.2: the reason a plan gives for its combined answers (with exactly ``count`` and ``sources``).
POOL_REASON_CODES_12: tuple[str, ...] = POOL_REASON_CODES + ("pool_n_fold",)
POOL_REASON_PARAMETERS_12: Mapping[str, tuple[str, ...]] = {**POOL_REASON_PARAMETERS, "pool_n_fold": ("count", "sources")}
#: Pool port 1.2: the flash decision maker's two methods, as a decision records them.
DECISION_APPROACHES: tuple[str, ...] = ("in_depth", "duplication")
#: Pool port 1.2: why a decision was made (closed; the flash router's ``decision.DECISION_REASONS``).
DECISION_REASONS: tuple[str, ...] = (
    "in_depth_cheapest", "agreement_risk", "agreement_escalation", "agreement_advised", "combined_n_fold", "split_to_fit", "over_budget",
    "size_not_measured",
)
#: Pool port 1.2: why a priced candidate was or was not chosen (closed; the flash router's ``decision.CANDIDATE_WHY``).
CANDIDATE_WHY: tuple[str, ...] = ("chosen", "costlier", "agreement_needed", "exceeds_budget", "combined_needs_n_fold")
#: The most sources a combined answer carries (the router port's topology bound).
MAX_SOURCES = 16
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


# --------------------------------------------------------------------------------------------- pool port 1.2: the request

_Size = Annotated[int, Field(ge=0, le=1_000_000_000)]
_Small = Annotated[int, Field(ge=0, le=1_000_000)]
_DecisionReason = Literal["in_depth_cheapest", "agreement_risk", "agreement_escalation", "agreement_advised", "combined_n_fold", "split_to_fit",
                          "over_budget", "size_not_measured"]
_Why = Literal["chosen", "costlier", "agreement_needed", "exceeds_budget", "combined_needs_n_fold"]
_ReasonCode12 = Literal["pool_empty", "pool_baseline", "pool_volume", "pool_repeated_faults", "pool_risk_signals", "pool_advised",
                        "pool_risk_records", "pool_capped", "pool_over_quota", "pool_n_fold"]
_Reviews = Annotated[int, Field(ge=1, le=HARD_MAX_INSTANCES)]


class PoolFeatures(Frozen):
    """The size of a dossier (or of one part of a combined answer) as the flash decision maker prices it: its journaled
    transfers, their characters (envelopes, receipts and raw texts as journaled), whether its content is STEM and how many
    translations it carries (which compositions of the overseer's knowledge pack it needs). Counts only."""
    transfers: _Small
    chars: _Size
    stem: bool
    translations: _Small


class PoolPartFeatures(Frozen):
    """One part of a combined answer (one specialist's own transfers, or the combinator's output with what no source
    owns): its repeated faults, risk signals and records, read from its own transfers, and its size."""
    repeated_faults: _Count
    risk_signals: list[_RiskClass] = Field(default_factory=list, max_length=len(POOL_RISK_CLASSES))
    risk_records: list[_RiskClass] = Field(default_factory=list, max_length=len(POOL_RISK_CLASSES))
    features: Optional[PoolFeatures] = None

    @model_validator(mode="after")
    def _classes(self) -> "PoolPartFeatures":
        if not _sorted_unique(self.risk_signals) or not _sorted_unique(self.risk_records):
            raise ValueError("risk signals and records are sorted and unique")
        return self


class PoolItemFeatures12(Frozen):
    """One dossier at pool port 1.2: its 1.1 features, its size (``None``: not measured) and, for a combined answer, its
    N >= 2 sources (in the order their answers were first delivered) and its merged part; never its key or a text."""
    item_id: _ItemId
    repeated_faults: _Count
    risk_signals: list[_RiskClass] = Field(default_factory=list, max_length=len(POOL_RISK_CLASSES))
    risk_records: list[_RiskClass] = Field(default_factory=list, max_length=len(POOL_RISK_CLASSES))
    advised: bool = False
    features: Optional[PoolFeatures] = None
    sources: list[PoolPartFeatures] = Field(default_factory=list, max_length=MAX_SOURCES)
    merged: Optional[PoolPartFeatures] = None

    @model_validator(mode="after")
    def _shape(self) -> "PoolItemFeatures12":
        if not _sorted_unique(self.risk_signals) or not _sorted_unique(self.risk_records):
            raise ValueError("risk signals and records are sorted and unique")
        if len(self.sources) == 1:
            raise ValueError("a combined answer combines at least two sources")
        if bool(self.sources) != (self.merged is not None):
            raise ValueError("a combined answer has its sources and its merged part, any other dossier neither")
        return self

    @property
    def combined(self) -> bool:
        return bool(self.sources)


class PoolRoutingRequest12(Frozen):
    schema_: Literal["epinoic.integration.pool-routing-request.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.2"]
    items: list[PoolItemFeatures12] = Field(default_factory=list, max_length=MAX_POOL_ITEMS)
    limits: PoolLimits

    model_config = Frozen.model_config | {"populate_by_name": True}

    @model_validator(mode="after")
    def _positions(self) -> "PoolRoutingRequest12":
        if [it.item_id for it in self.items] != [item_id(i) for i in range(len(self.items))]:
            raise ValueError("the items are d1, d2, ... in order (their positions in the overseer's key order)")
        return self


# --------------------------------------------------------------------------------------------- pool port 1.2: the plan


class PoolSourceAssignment(Frozen):
    """How one source of a combined answer is reviewed: ``IN_DEPTH`` (one instance) or ``DUPLICATE`` (independent ones)."""
    method: Literal["IN_DEPTH", "DUPLICATE"]
    instances: list[Annotated[int, Field(ge=1, le=HARD_MAX_INSTANCES)]] = Field(min_length=1, max_length=HARD_MAX_INSTANCES)


class PoolContext(Frozen):
    """The merged review's temporary context: the validated outcomes of the source reviews, scoped to the request, at
    most ``max_bytes`` bytes, discarded after the request."""
    scope: Literal["request"]
    contents: Literal["validated_outcomes"]
    max_bytes: int = Field(ge=1, le=CONTEXT_MAX_BYTES)
    discard: Literal["after_request"]


class PoolDecisionRead(Frozen):
    """The features a decision read: the request item's own (the overseer checks the echo), and its number of sources."""
    repeated_faults: _Count
    risk_signals: list[_RiskClass] = Field(max_length=len(POOL_RISK_CLASSES))
    risk_records: list[_RiskClass] = Field(max_length=len(POOL_RISK_CLASSES))
    advised: bool
    features: Optional[PoolFeatures]
    sources: int = Field(ge=0, le=MAX_SOURCES)


class PoolCandidate(Frozen):
    """One method the decision maker priced: its reviews and calls, its estimated tokens (``None`` when the size is not
    measured) and agent-seconds, whether it keeps accuracy and why it was or was not chosen."""
    method: Literal["IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD"]
    reviews: _Reviews
    calls: Annotated[int, Field(ge=0, le=100_000)]
    tokens: Optional[Annotated[int, Field(ge=0, le=1_000_000_000_000)]]
    seconds: Annotated[int, Field(ge=0, le=100_000_000)]
    keeps_accuracy: bool
    why: _Why


class PoolPartDecision(Frozen):
    """The decision for one part of an N_FOLD: a source (``index`` 1 to N) or the merged review (``index`` 0)."""
    part: Literal["source", "merged"]
    index: int = Field(ge=0, le=MAX_SOURCES)
    reviews: _Reviews
    need_tokens: Optional[Annotated[int, Field(ge=0, le=1_000_000_000_000)]]
    fits: Optional[bool]
    reasons: list[_DecisionReason] = Field(min_length=1, max_length=len(DECISION_REASONS))


class PoolDecisionCost(Frozen):
    tokens: Optional[Annotated[int, Field(ge=0, le=1_000_000_000_000)]]
    seconds: Annotated[int, Field(ge=0, le=100_000_000)]


class PoolDecision(Frozen):
    """The flash decision maker's record for one dossier (rule D7): the approach (``in_depth``: one instance examines the
    whole response; ``duplication``: the work split across instances in parallel, with duplicates where risk calls for
    agreement), the method, the reviews and calls, what it read, the reading need of one instance and the instance
    budget, whether one instance fits, its reasons, every candidate it priced, the parts of an N_FOLD and its cost."""
    approach: Literal["in_depth", "duplication"]
    method: Literal["IN_DEPTH", "DUPLICATE", "N_FOLD"]
    reviews: _Reviews
    calls: Annotated[int, Field(ge=0, le=100_000)]
    read: PoolDecisionRead
    need_tokens: Optional[Annotated[int, Field(ge=0, le=1_000_000_000_000)]]
    budget_tokens: Annotated[int, Field(ge=1, le=1_000_000_000_000)]
    fits: Optional[bool]
    reasons: list[_DecisionReason] = Field(min_length=1, max_length=len(DECISION_REASONS))
    candidates: list[PoolCandidate] = Field(min_length=1, max_length=8)
    parts: list[PoolPartDecision] = Field(default_factory=list, max_length=MAX_SOURCES + 1)
    estimated_cost: PoolDecisionCost


class PoolAssignment12(Frozen):
    """How one dossier is reviewed at pool port 1.2: its method and the instances that review it (for ``N_FOLD``, the
    merged review's), its sources' assignments (``N_FOLD`` only) and temporary context (``N_FOLD`` only), and the
    decision that chose them."""
    item_id: _ItemId
    method: _Method
    instances: list[Annotated[int, Field(ge=1, le=HARD_MAX_INSTANCES)]] = Field(min_length=1, max_length=HARD_MAX_INSTANCES)
    sources: list[PoolSourceAssignment] = Field(max_length=MAX_SOURCES)
    context: Optional[PoolContext]
    decision: PoolDecision


class PoolReason12(Frozen):
    """One reason of a 1.2 plan: a closed code and exactly its parameters (:data:`POOL_REASON_PARAMETERS_12`)."""
    code: _ReasonCode12
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
    sources: Optional[_Count] = None

    @model_validator(mode="after")
    def _parameters(self) -> "PoolReason12":
        wanted = set(POOL_REASON_PARAMETERS_12[self.code])
        given = {k for k in ("count", "reviewers", "classes", "weight", "units", "quota", "instances", "maximum", "needed", "load", "sources")
                 if getattr(self, k) is not None}
        if given != wanted:
            raise ValueError(f"reason {self.code} takes exactly {sorted(wanted)}")
        if self.classes is not None and (not self.classes or not _sorted_unique(self.classes)):
            raise ValueError("a reason's classes are sorted, unique and not empty")
        return self


class PoolRoutingPlan12(Frozen):
    schema_: Literal["epinoic.integration.pool-routing-plan.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.2"]
    origin: Literal["router"]
    plan_id: _Key
    request_sha256: Sha256
    router: RouterIdentity
    profile: _Profile
    instances: Annotated[int, Field(ge=0, le=HARD_MAX_INSTANCES)]
    assignments: list[PoolAssignment12] = Field(max_length=MAX_POOL_ITEMS)
    loads: list[_Count] = Field(max_length=HARD_MAX_INSTANCES)
    review_units: _Count
    needed_instances: _Count
    capped: bool
    over_quota: bool
    reasons: list[PoolReason12] = Field(min_length=1, max_length=len(POOL_REASON_CODES_12))
    estimated_cost: Optional[PoolCost] = None

    model_config = Frozen.model_config | {"populate_by_name": True}


AnyPoolRequest = Union[PoolRoutingRequest, PoolRoutingRequest12]
AnyPoolPlan = Union[PoolRoutingPlan, PoolRoutingPlan12]


# --------------------------------------------------------------------------------------------- building and validation


def pool_request_digest(request: Union[PoolRoutingRequest, PoolRoutingRequest12, dict]) -> str:
    return sha256_json(dump(request) if isinstance(request, (PoolRoutingRequest, PoolRoutingRequest12)) else request)


def _parsed(raw: Any, code: str) -> Any:
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            return loads_strict(raw)
        except CanonicalError as exc:
            raise IntegrationError(code, f"not protocol JSON: {exc}") from None
    return raw


def _part(part: Mapping[str, Any]) -> dict:
    return {"repeated_faults": int(part["repeated_faults"]), "risk_signals": list(part.get("risk_signals", ())),
            "risk_records": list(part.get("risk_records", ())), "features": _features_of(part.get("features"))}


def _features_of(f: Any) -> Optional[dict]:
    if f is None:
        return None
    if hasattr(f, "model_dump"):
        f = f.model_dump(mode="json")
    return {"transfers": int(f["transfers"]), "chars": int(f["chars"]), "stem": bool(f["stem"]), "translations": int(f["translations"])}


def build_pool_request(items: Sequence[Mapping[str, Any]], *, max_instances: int, per_instance_quota: int,
                       profiles: Sequence[str] = ("standard",), port_version: str = POOL_PORT_VERSION) -> AnyPoolRequest:
    """The pool routing request of a batch, in pool port ``port_version`` (the version the attached router's pool hello
    names): ``items`` in the overseer's key order, each a mapping of ``repeated_faults``, ``risk_signals``,
    ``risk_records`` and ``advised`` (its key is never sent; its position is its id) and, at 1.2, ``features`` (the
    dossier's size, ``None`` when not measured), ``sources`` and ``merged`` (a combined answer's parts; a 1.1 request
    carries none: ``KIT-RT-014``). Validated (``KIT-RT-014`` on anything out of contract)."""
    if port_version not in POOL_PORT_VERSIONS:
        raise IntegrationError("KIT-RT-014", f"pool port version {port_version!r} is not one the overseer speaks")
    out_items = []
    for i, it in enumerate(items):
        entry = {"item_id": item_id(i), "repeated_faults": int(it["repeated_faults"]), "risk_signals": list(it.get("risk_signals", ())),
                 "risk_records": list(it.get("risk_records", ())), "advised": bool(it.get("advised", False))}
        if port_version == "1.1":
            if it.get("sources") or it.get("merged") is not None:
                raise IntegrationError("KIT-RT-014", "pool port 1.1 carries no combined answer (its N_FOLD needs pool port 1.2)")
        else:
            entry.update(features=_features_of(it.get("features")), sources=[_part(p) for p in it.get("sources") or ()],
                         merged=_part(it["merged"]) if it.get("merged") is not None else None)
        out_items.append(entry)
    raw = {"schema": POOL_REQUEST_SCHEMA, "protocol": PROTOCOL, "port_version": port_version, "items": out_items,
           "limits": {"max_instances": int(max_instances), "per_instance_quota": int(per_instance_quota), "profiles": list(profiles)}}
    return check_pool_request(raw)


def check_pool_request(raw: Any) -> AnyPoolRequest:
    """Validate a pool routing request (the overseer builds it; the router receives it), at the version it names:
    ``KIT-RT-014`` for anything out of contract, ``KIT-RT-011`` when it carries what a blind dossier hides."""
    data = _parsed(raw, "KIT-RT-014")
    if not isinstance(data, dict):
        raise IntegrationError("KIT-RT-014", "a pool routing request is a JSON object")
    hidden = _hidden(data)
    if hidden:
        raise IntegrationError("KIT-RT-011", f"the request carries {hidden}, which a blind dossier hides")
    model = PoolRoutingRequest12 if data.get("port_version") == "1.2" else PoolRoutingRequest
    try:
        return model.model_validate(data)
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


_LOCATION_CODES = (("decision", "KIT-RT-012"), ("reasons", "KIT-RT-012"), ("estimated_cost", "KIT-RT-013"), ("loads", "KIT-RT-013"), ("review_units", "KIT-RT-013"),
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


def check_pool_plan(raw: Any, request: AnyPoolRequest, *, hello: PoolRouterHello) -> AnyPoolPlan:
    """Validate a router's pool plan against its request and the attached router's pool hello. Raises
    :class:`IntegrationError` with the ``KIT-RT`` code of the first rule it breaks (PROTOCOL.md section 7b.4). It does NOT
    apply the floor: the overseer does (``KIT-RT-020``). A plan is written in its request's pool port version (and the
    request in the hello's): a 1.2 request's plan is checked by :func:`_check_pool_plan_12`."""
    if isinstance(request, PoolRoutingRequest12):
        return _check_pool_plan_12(raw, request, hello=hello)
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
        if a.method not in POOL_RUN_METHODS_BY_VERSION["1.1"]:
            raise IntegrationError("KIT-RT-007", f"pool port 1.1 reviews a dossier IN_DEPTH or DUPLICATE ({a.method} is for a planner later)")
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


def _accounting_problem(plan: AnyPoolPlan, request: AnyPoolRequest) -> Optional[tuple[str, str]]:
    """The plan's own numbers must agree with each other (``KIT-RT-013``); a 1.2 plan's source reviews count as reviews
    of their instances."""
    if len(plan.loads) != plan.instances:
        return ("KIT-RT-013", "the plan has one load per instance")
    per_instance = [0] * plan.instances
    for a in plan.assignments:
        for n in [*a.instances, *(k for s in getattr(a, "sources", ()) for k in s.instances)]:
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
    if plan.port_version == "1.2":  # rule P7: a 1.2 plan's estimate is the sum of its decisions', when every dossier's is priced
        costs = [a.decision.estimated_cost for a in plan.assignments]
        priced = bool(costs) and all(c.tokens is not None for c in costs)
        want = {"tokens": sum(c.tokens for c in costs), "seconds": sum(c.seconds for c in costs)} if priced else None
        got = None if plan.estimated_cost is None else {"tokens": plan.estimated_cost.tokens, "seconds": plan.estimated_cost.seconds}
        if got != want:
            return ("KIT-RT-013", "a 1.2 plan's estimated cost is the sum of its decisions' estimates, and absent when one is not priced")
    return None


def _reasons_problem(plan: AnyPoolPlan, request: AnyPoolRequest) -> Optional[tuple[str, str]]:
    """A reason states only what the plan and the request hold (``KIT-RT-012``): the dossiers it counts and the classes
    it names are the request's, its numbers the plan's; at 1.2 a plan with combined answers says how many, and how many
    sources they combine, and only then."""
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
    combined = [it for it in items if getattr(it, "sources", None)]
    r = by_code.get("pool_n_fold")
    if (r is not None) != bool(combined) or (r is not None and (r.count != len(combined) or r.sources != sum(len(it.sources) for it in combined))):
        return (bad, "the n-fold reason states the request's combined answers and their sources, and only when there are some")
    return None


# --------------------------------------------------------------------------------------------- pool port 1.2: the plan's rules


def _read_of(item: PoolItemFeatures12) -> dict:
    """What a decision must have read of one dossier: the request item's own features (rule D7: the echo is checked)."""
    return {"repeated_faults": item.repeated_faults, "risk_signals": list(item.risk_signals), "risk_records": list(item.risk_records),
            "advised": item.advised, "features": dump(item.features) if item.features is not None else None, "sources": len(item.sources)}


def _check_pool_plan_12(raw: Any, request: PoolRoutingRequest12, *, hello: PoolRouterHello) -> PoolRoutingPlan12:
    """The rules of a pool port 1.2 plan, in the order of PROTOCOL.md section 7b.4: those of 1.1, with a combined
    answer's N_FOLD (its sources' assignments, their parallelism and its bounded temporary context) and every dossier's
    decision record (the method it decided, the features it read, exactly one chosen candidate, the parts of an N_FOLD)."""
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
        plan = PoolRoutingPlan12.model_validate(data)
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
        problem = _shape_problem_12(a, items[a.item_id], hello)
        if problem:
            raise IntegrationError("KIT-RT-007", problem)
    if plan.profile not in request.limits.profiles or plan.profile not in hello.profiles:
        raise IntegrationError("KIT-RT-010", "the plan uses an overseer profile that is not available")
    maximum = min(request.limits.max_instances, HARD_MAX_INSTANCES)
    if plan.instances > maximum:
        raise IntegrationError("KIT-RT-008", f"the plan has {plan.instances} instances, over the pool's maximum of {maximum}")
    if any(n > plan.instances for a in plan.assignments for n in [*a.instances, *(k for s in a.sources for k in s.instances)]):
        raise IntegrationError("KIT-RT-008", "an assignment names an instance the plan does not have")
    if bool(request.items) != (plan.instances >= 1):
        raise IntegrationError("KIT-RT-008", "a batch with dossiers has at least one instance, an empty batch none")
    for a in plan.assignments:
        if a.method == "N_FOLD" and sum(len(s.instances) for s in a.sources) <= plan.instances:
            seen: set[int] = set()
            for s in a.sources:
                if seen & set(s.instances):
                    raise IntegrationError("KIT-RT-007", "a combined answer's source reviews run in parallel: no instance reviews two of its sources "
                                                         "while the plan has instances to spare")
                seen |= set(s.instances)
    codes = [r.code for r in plan.reasons]
    if len(set(codes)) != len(codes):
        raise IntegrationError("KIT-RT-012", "a reason is listed twice")
    for a in plan.assignments:
        problem = _decision_problem(a, items[a.item_id])
        if problem:
            raise IntegrationError("KIT-RT-012", problem)
    problem = _accounting_problem(plan, request) or _reasons_problem(plan, request)
    if problem:
        raise IntegrationError(*problem)
    return plan


def _shape_problem_12(a: PoolAssignment12, item: PoolItemFeatures12, hello: PoolRouterHello) -> Optional[str]:
    if a.method not in POOL_RUN_METHODS_BY_VERSION["1.2"]:
        return f"pool port 1.2 reviews a dossier IN_DEPTH, DUPLICATE or N_FOLD ({a.method} is for a planner later)"
    if a.method not in hello.methods:
        return "the plan uses a method its router's pool hello does not declare"
    if (a.method == "N_FOLD") != item.combined:
        return "N_FOLD reviews exactly the combined answers: a combined answer is reviewed N_FOLD, any other dossier never"
    if len(set(a.instances)) != len(a.instances):
        return "a dossier names one instance twice"
    if a.method == "N_FOLD":
        if len(a.sources) != len(item.sources):
            return "an N_FOLD review names one source assignment per source of the combined answer, in order"
        if a.context is None:
            return "an N_FOLD review has its bounded, request-scoped temporary context"
        for s in a.sources:
            if len(set(s.instances)) != len(s.instances):
                return "a source names one instance twice"
            if (s.method == "IN_DEPTH") != (len(s.instances) == 1):
                return "a source is reviewed IN_DEPTH by one instance or DUPLICATE by at least two independent ones"
        return None
    if a.sources or a.context is not None:
        return "only an N_FOLD review names sources or a temporary context"
    if (a.method == "IN_DEPTH") != (len(a.instances) == 1):
        return "IN_DEPTH is one instance reading the dossier whole; DUPLICATE is at least two independent ones"
    return None


def _decision_problem(a: PoolAssignment12, item: PoolItemFeatures12) -> Optional[str]:
    """A decision states only what the plan and the request hold (``KIT-RT-012``)."""
    d = a.decision
    if d.method != a.method or d.approach != ("in_depth" if a.method == "IN_DEPTH" else "duplication"):
        return "a decision records the method its assignment runs, and the approach of that method"
    if d.reviews != len(a.instances):
        return "a decision records the independent complete reviews of its assignment (an N_FOLD's merged review)"
    if dump(d.read) != _read_of(item):
        return "a decision records exactly the features the request holds for its dossier"
    if len(set(d.reasons)) != len(d.reasons):
        return "a decision lists a reason twice"
    chosen = [c for c in d.candidates if c.why == "chosen"]
    if len(chosen) != 1 or chosen[0].method != a.method:
        return "a decision chose exactly one candidate, the method its assignment runs"
    if ("combined_n_fold" in d.reasons) != (a.method == "N_FOLD"):
        return "a decision names combined_n_fold exactly for a combined answer"
    if a.method == "N_FOLD":
        want = [("source", k, len(s.instances)) for k, s in enumerate(a.sources, start=1)] + [("merged", 0, len(a.instances))]
        if [(p.part, p.index, p.reviews) for p in d.parts] != want:
            return "an N_FOLD decision records each source in order and then the merged review, with the reviews each is assigned"
    elif d.parts:
        return "only an N_FOLD decision has parts"
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


def ask_pool_router(request: AnyPoolRequest, attachment: PoolRouterAttachment, *, timeout_s: Optional[float] = None) -> PoolAnswer:
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
