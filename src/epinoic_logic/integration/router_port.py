"""The flash-router port ``epinoic.integration.router-port.v1`` (``integration/PROTOCOL.md`` section 7a).

The flash router is the oversight planner's decision: per request and per specialist output it decides HOW the
overseer reviews. It runs as a separate, independent agent in its own sub-project (``flash-router/``, package
``epinoic_flash_router``), so it can be edited and released without touching the Z3 infrastructure. It talks to the
service only through this port: a :class:`RoutingRequest` in, a :class:`RoutingPlan` out, both JSON with closed key
sets. It is not the translator's ``RouterHub`` (which carries messages between agents) and not the website router (which
chooses a specialist).

Methods (per transfer):

* ``IN_DEPTH``: one overseer instance examines the whole response;
* ``SPLIT``: the work divided across several parallel instances, each part reviewed once;
* ``DUPLICATE``: independent duplicate reviews of the whole response, combined by the verdict combination;
* ``N_FOLD``: for a combined answer only: one review of each specialist's individual response before combination (the
  source transfers' own entries), then one merged review of the combinator's output (this entry) with a bounded,
  request-scoped temporary context of the per-source validated outcomes, discarded after the request.

**The plan is advisory.** The overseer enforces a deterministic minimum-oversight floor computed from the same risk
signals (:func:`floor_plan`). A plan below the floor is refused with ``KIT-RT-020`` and the floor plan runs; an
out-of-contract plan is refused with its own ``KIT-RT`` code and the floor plan runs; with no router attached the floor
plan runs. So a router can only ever add oversight, never remove it, and risk signals only escalate. A plan carries
only closed-vocabulary values, digests bound to its request and hello, and transfer keys from its request: nothing a
blind dossier hides (no auditor finding, no consolidation result, no OVS code, no gold or fault label), and no model
(no model member, and no plan id or router name naming a model family): every instance runs on the cheapest tier. The
plan never changes a clearance, a delivery decision or a verdict's decision: the review it plans runs after delivery.

**The router runs in its own process** (:func:`run_router`, ``router_child.py``): ``python -I`` with the service's import
path, an environment of :data:`CHILD_ENV_NAMES` only (no ``EPINOIC_`` variable, so no key, secret or token is in its own
environment), its answer read from its standard output, at most :data:`HELLO_TIMEOUT_S` for its hello and at most
``min(PLAN_TIMEOUT_S, what is left of the call's budget)`` for a plan. Its code never runs in the service: it cannot
change the floor or the admission, or raise into the service. A router that raises, exits, hangs, answers with more than
:data:`MAX_ANSWER_BYTES` or with anything but JSON text is refused with ``KIT-RT-016`` and the floor runs; JSON that is
not a plan keeps its own code (``KIT-RT-001`` and the rest of :func:`check_plan`).

That process is a fault boundary, not a sandbox: it runs as the service's user. Before it starts one, the service marks
itself non-dumpable on Linux, so a router without root and without ``CAP_SYS_PTRACE`` cannot read the service's
environment or memory; a service that runs as root or with ``CAP_SYS_PTRACE``, another system, and secrets kept in files
or in other processes of the same user are outside that protection (``router_child.protect_service``,
``router_child.boundary_problem``). The hosted profile therefore attaches a router only where the protection holds
(:func:`attach_router` with ``require_secret_boundary``); a router is installed only as code trusted with the service's
user (decision D28).

Standard library and pydantic only: nothing here imports the engine or Z3, so a router sub-project can validate its own
output against this module, the JSON Schemas in ``integration/schemas/`` and the vectors in
``integration/vectors/router-port/`` without the Z3 infrastructure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import partial
from typing import Annotated, Any, Callable, Literal, Optional, Union

from pydantic import Field, StringConstraints, ValidationError, model_validator

from . import router_child as _child
from .canonical import CanonicalError, canonical_json, loads_strict, sha256_json, sha256_text
from .errors import IntegrationError
from .protocol import (
    FINDING_CODE_PATTERN, FLOOR_IDENTITY_PREFIX, FORMAL_VALUES, PROTOCOL, AgentId, FloorRef, Frozen, Id, RouterIdentity, Sha256, dump,
)

__all__ = [
    "PORT_VERSION", "REQUEST_SCHEMA", "PLAN_SCHEMA", "HELLO_SCHEMA", "METHODS", "PROFILES", "TIER", "HARD_MAX_INSTANCES",
    "MIN_AGREEMENT_REVIEWS", "MAX_REVIEWS", "MAX_PARTS", "CONTEXT_MAX_BYTES", "REASON_CODES", "FEATURE_NAMES",
    "AGREEMENT_SIGNALS", "FLOOR_NAME", "FLOOR_RULES", "FLOOR_RULES_SHA256", "FLOOR_IDENTITY", "FLOOR_REF",
    "MODEL_FAMILIES", "HELLO_TIMEOUT_S", "PLAN_TIMEOUT_S", "MAX_ANSWER_BYTES", "CHILD_ENV_NAMES",
    "RequestItemFeature", "ConstraintFeature", "SuppliedTextFeature", "RequestFeatures", "SizeFeature", "ClaimsFeature",
    "ReceiptFeature", "OutputFeatures", "Topology", "RoutingLimits", "RoutingRequest", "RouterHello", "Cost",
    "TemporaryContext", "TransferPlan", "PlanTotals", "RoutingPlan", "Admission", "RouterAttachment", "RouterFailure",
    "check_request", "check_hello", "check_plan", "risk_signals", "floor_plan", "below_floor", "admit_plan",
    "attach_router", "route", "run_router", "request_digest",
]

PORT_VERSION = "1.0"
REQUEST_SCHEMA = "epinoic.integration.routing-request.v1"
PLAN_SCHEMA = "epinoic.integration.routing-plan.v1"
HELLO_SCHEMA = "epinoic.integration.router-hello.v1"
METHODS: tuple[str, ...] = ("IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD")
PROFILES: tuple[str, ...] = ("standard", "fast")
TIER = "cheapest"
#: The overseer pool's own hard maximum of instances per plan (``overseer.pool.HARD_MAX_INSTANCES``).
HARD_MAX_INSTANCES = 64
#: Independent reviews a transfer gets when a risk signal calls for agreement (``overseer.pool.MIN_REPEAT_REVIEWERS``).
MIN_AGREEMENT_REVIEWS = 2
MAX_REVIEWS = 4
MAX_PARTS = 16
MAX_OUTPUTS = 17
#: Upper bound of an N_FOLD merged review's temporary context (the per-source validated outcomes), in UTF-8 bytes.
CONTEXT_MAX_BYTES = 65536

#: Why a transfer gets its oversight. Closed: a plan carries no free text. ``risk_diagnostics`` and
#: ``risk_unverified_dependencies`` name escalations a router may add on features the floor does not read.
REASON_CODES: tuple[str, ...] = (
    "baseline_single_review", "risk_receipt_rejected", "risk_error_findings", "risk_repeated_faults",
    "risk_negative_results", "risk_stem_undecided", "volume_split", "topology_combined", "topology_source",
    "cost_cheapest", "profile_fast", "profile_standard", "cap_merged", "risk_diagnostics", "risk_unverified_dependencies",
)
#: The request features a plan may say it used. Closed: names only, never values.
FEATURE_NAMES: tuple[str, ...] = (
    "subjects", "stem", "task_type", "course_level", "items", "constraints", "supplied_texts",
    "size", "claims", "engine_statuses", "receipt", "diagnostics", "unverified_dependencies", "peer_relays",
    "repeated_faults", "topology",
)
#: Risk signals that call for agreement (two or more independent reviews), with the request feature each one reads.
AGREEMENT_SIGNALS: tuple[tuple[str, str], ...] = (
    ("risk_receipt_rejected", "receipt"),
    ("risk_error_findings", "receipt"),
    ("risk_repeated_faults", "repeated_faults"),
    ("risk_negative_results", "engine_statuses"),
    ("risk_stem_undecided", "engine_statuses"),
)
_NEGATIVE = ("COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "UNSATISFIABLE")
_UNDECIDED = ("UNKNOWN", "TIMEOUT", "INTERNAL_ERROR", "NOT_ATTEMPTED")
#: The STEM budget's leftover checks (``INT-SUBJ-002``): STEM working the checks could not fully decide.
_STEM_UNDECIDED_CODES = ("INT-SUBJ-002",)

FLOOR_NAME = "minimum-oversight-floor/1"
#: The floor's rules, as data: their digest is reported in the handshake and in every floor plan.
FLOOR_RULES = (
    "minimum-oversight-floor/1\n"
    "1. Every transfer of the request is reviewed: a transfer the plan leaves out has no review, which is below the floor.\n"
    "2. A transfer gets at least 2 independent complete reviews when any agreement signal holds: its receipt is REJECTED;"
    " its receipt carries an error-level finding; it carries a repeated fault; a material or branch check is COUNTEREXAMPLE,"
    " INCONSISTENT_PREMISES or UNSATISFIABLE; it is STEM and a check is UNKNOWN, TIMEOUT, INTERNAL_ERROR or NOT_ATTEMPTED,"
    " or its receipt carries INT-SUBJ-002. Otherwise it gets at least 1 complete review.\n"
    "3. A combined answer with N source answers is reviewed N_FOLD: each source answer by its own entry under rule 2, and"
    " the combinator's output by a merged review of method N_FOLD naming exactly the N sources, with a request-scoped"
    " temporary context of at most 65536 bytes discarded after the request, and at least the reviews rule 2 gives it.\n"
    "4. IN_DEPTH and SPLIT are 1 complete review; DUPLICATE is its number of reviews; the profile is not part of the"
    " floor; every instance runs on the cheapest tier.\n"
    "5. The floor plan runs IN_DEPTH (1 review) or DUPLICATE (2 reviews) for each transfer and N_FOLD for the"
    " combinator's output, on the standard profile.\n"
)
FLOOR_RULES_SHA256 = sha256_text(FLOOR_RULES)
FLOOR_IDENTITY = RouterIdentity(name="minimum-oversight-floor", version="1", rules_sha256=FLOOR_RULES_SHA256, cost_data_sha256=sha256_text(""))
FLOOR_REF = FloorRef(name=FLOOR_NAME, rules_sha256=FLOOR_RULES_SHA256)

#: Keys that would carry what a blind dossier hides, refused anywhere in a plan or a request.
_HIDDEN_KEYS = frozenset({"auditor", "audit", "consolidation", "consolidations", "gold", "fault", "faults_injected", "variant",
                          "verdict", "verdicts", "dossier", "dossiers", "findings", "messages", "text", "answer", "claims_text"})
_OVS_RE = re.compile(r"OVS-[A-Z]{2,12}-[0-9]{3}")
_MODEL_KEYS = frozenset({"model", "model_id", "models", "provider", "model_name"})
#: Model families that a plan's free-form values (its ``plan_id`` and its router's name) and a hello's router name must
#: not name: a plan never names a model (``KIT-RT-009``; a hello ``KIT-RT-015``). Matched as a whole word, any case.
MODEL_FAMILIES: tuple[str, ...] = ("claude", "gpt", "gemini", "llama", "mistral", "mixtral", "opus", "sonnet", "haiku", "qwen", "deepseek")
_MODEL_VALUE_RE = re.compile(r"(?i)(?:^|[^a-z0-9])(?:" + "|".join(MODEL_FAMILIES) + r")(?:[^a-z]|$)")

#: How long the service waits for the router's hello when it attaches it (at start-up, never on a turn).
HELLO_TIMEOUT_S = 10.0
#: The longest the service waits for one plan; a call never waits longer than what is left of its budget either.
PLAN_TIMEOUT_S = 3.0
#: The most the service reads of a router's answer (UTF-8 bytes): a larger answer is a failed router (``KIT-RT-016``).
MAX_ANSWER_BYTES = _child.MAX_ANSWER_BYTES
#: The only environment variables the router's process gets (names, never values; no ``EPINOIC_`` variable is among them).
CHILD_ENV_NAMES: tuple[str, ...] = _child.CHILD_ENV_NAMES

_Key = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,128}$")]
_DocId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:/-]{1,200}$")]
_Code = Annotated[str, StringConstraints(pattern=FINDING_CODE_PATTERN)]
_DiagCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]{0,15}(?:-[A-Z0-9]{1,16}){1,4}$")]
_Subject = Annotated[str, StringConstraints(min_length=1, max_length=128)]
_Branch = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{0,63}$")]
_Method = Literal["IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD"]
_Profile = Literal["standard", "fast"]
_Reason = Literal[
    "baseline_single_review", "risk_receipt_rejected", "risk_error_findings", "risk_repeated_faults",
    "risk_negative_results", "risk_stem_undecided", "volume_split", "topology_combined", "topology_source",
    "cost_cheapest", "profile_fast", "profile_standard", "cap_merged", "risk_diagnostics", "risk_unverified_dependencies",
]
_Feature = Literal[
    "subjects", "stem", "task_type", "course_level", "items", "constraints", "supplied_texts",
    "size", "claims", "engine_statuses", "receipt", "diagnostics", "unverified_dependencies", "peer_relays",
    "repeated_faults", "topology",
]


# --------------------------------------------------------------------------------------------- the routing request


class RequestItemFeature(Frozen):
    item_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,64}$")]
    kind: Literal["question", "instruction"]
    required: bool
    command_term: Optional[Annotated[str, StringConstraints(pattern=r"^[a-z][a-z ]{0,39}$")]] = None
    level: Optional[int] = Field(default=None, ge=1, le=3)


class ConstraintFeature(Frozen):
    constraint_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,64}$")]
    kind: Literal["max_words", "min_words", "max_paragraphs", "min_paragraphs", "must_cite_supplied_text", "must_address_all_items", "other"]
    value: Optional[Annotated[str, StringConstraints(pattern=r"^[0-9]{1,9}$")]] = None


class SuppliedTextFeature(Frozen):
    document_id: _DocId
    sha256: Sha256
    chars: int = Field(ge=0, le=400_000)


class RequestFeatures(Frozen):
    """The user's request as features: subjects, STEM or not, the request items and constraints (ids, kinds, command
    terms; never their text) and the supplied texts by digest."""
    subjects: list[_Subject] = Field(min_length=1, max_length=8)
    stem: bool
    task_type: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    course_level: Literal["SL", "HL", "unknown"]
    items: list[RequestItemFeature] = Field(default_factory=list, max_length=64)
    constraints: list[ConstraintFeature] = Field(default_factory=list, max_length=64)
    supplied_texts: list[SuppliedTextFeature] = Field(default_factory=list, max_length=16)
    user_text_sha256: Sha256


class SizeFeature(Frozen):
    chars: int = Field(ge=0, le=400_000)
    words: int = Field(ge=0, le=200_000)
    paragraphs: int = Field(ge=0, le=10_000)


class ClaimsFeature(Frozen):
    total: int = Field(ge=0, le=512)
    material: int = Field(ge=0, le=512)
    eligible: int = Field(ge=0, le=512)
    translated: int = Field(ge=0, le=512)


class ReceiptFeature(Frozen):
    status: Literal["ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED"]
    error_codes: list[_Code] = Field(default_factory=list, max_length=128)
    warning_codes: list[_Code] = Field(default_factory=list, max_length=128)


class OutputFeatures(Frozen):
    """One specialist output (or the combinator's output) as features: its size, its claims, the engine statuses of its
    claims and branch checks, its receipt's finding codes, its named diagnostics, its unverified dependencies, the peer
    relays and the repeated faults that concern it."""
    transfer_key: _Key
    role: Literal["answer", "synthesis"]
    agent_id: AgentId
    subject: _Subject
    branch: _Branch
    stem: bool
    size: SizeFeature
    claims: ClaimsFeature
    engine_statuses: dict[str, Annotated[int, Field(ge=0, le=4096)]] = Field(default_factory=dict)
    receipt: ReceiptFeature
    diagnostics: list[_DiagCode] = Field(default_factory=list, max_length=64)
    unverified_dependencies: int = Field(ge=0, le=4096)
    peer_relays: int = Field(ge=0, le=64)
    repeated_faults: int = Field(ge=0, le=64)

    @model_validator(mode="after")
    def _statuses(self) -> "OutputFeatures":
        unknown = sorted(set(self.engine_statuses) - set(FORMAL_VALUES))
        if unknown:
            raise ValueError("engine_statuses names a status outside the thirteen statuses and NOT_ATTEMPTED")
        return self


class Topology(Frozen):
    kind: Literal["single", "duplicate", "combined"]
    sources: list[_Key] = Field(default_factory=list, max_length=16)
    synthesis: Optional[_Key] = None


class RoutingLimits(Frozen):
    max_instances: int = Field(ge=MIN_AGREEMENT_REVIEWS, le=HARD_MAX_INSTANCES)
    profiles: list[_Profile] = Field(min_length=1, max_length=2)


class RequestIds(Frozen):
    task_id: Id
    request_id: Id


class RoutingRequest(Frozen):
    schema_: Literal["epinoic.integration.routing-request.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.0"]
    ids: RequestIds
    request: RequestFeatures
    outputs: list[OutputFeatures] = Field(min_length=1, max_length=MAX_OUTPUTS)
    topology: Topology
    limits: RoutingLimits

    model_config = Frozen.model_config | {"populate_by_name": True}

    @model_validator(mode="after")
    def _shape(self) -> "RoutingRequest":
        keys = [o.transfer_key for o in self.outputs]
        if len(set(keys)) != len(keys):
            raise ValueError("two outputs share a transfer key")
        answers = [o.transfer_key for o in self.outputs if o.role == "answer"]
        syntheses = [o.transfer_key for o in self.outputs if o.role == "synthesis"]
        t = self.topology
        if t.kind == "single":
            ok = len(answers) == 1 and not syntheses and not t.sources and t.synthesis is None
        elif t.kind == "duplicate":
            ok = len(answers) == 2 and not syntheses and not t.sources and t.synthesis is None
        else:
            ok = len(answers) >= 2 and t.sources == answers and syntheses == [t.synthesis] if t.synthesis is not None else False
        if not ok:
            raise ValueError("the topology does not match the outputs (single: one answer; duplicate: two answers; "
                             "combined: N >= 2 answers listed as sources in order, and one synthesis)")
        return self


# --------------------------------------------------------------------------------------------- hello and plan


class RouterHello(Frozen):
    """What a flash router says about itself when it is attached. Validated once; every plan must carry its identity."""
    schema_: Literal["epinoic.integration.router-hello.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.0"]
    router: RouterIdentity
    methods: list[_Method] = Field(min_length=1, max_length=4)
    profiles: list[_Profile] = Field(min_length=1, max_length=2)
    tier: Literal["cheapest"]
    deterministic: Literal[True]

    model_config = Frozen.model_config | {"populate_by_name": True}


class Cost(Frozen):
    tokens: int = Field(ge=0, le=1_000_000_000)
    seconds: int = Field(ge=0, le=1_000_000)


class TemporaryContext(Frozen):
    scope: Literal["request"]
    contents: Literal["validated_outcomes"]
    max_bytes: int = Field(ge=1, le=CONTEXT_MAX_BYTES)
    discard: Literal["after_request"]


class TransferPlan(Frozen):
    """How one transfer is reviewed. ``instances`` is the number of distinct overseer instances its review needs at once
    (its reviews times its parts): the overseer pool assigns them within its maximum, and an instance may review several
    transfers in turn under the pool's quota, so a plan's total is a count of review units, not of concurrent instances."""
    transfer_key: _Key
    method: _Method
    reviews: int = Field(ge=1, le=MAX_REVIEWS)
    parts: int = Field(ge=1, le=MAX_PARTS)
    instances: int = Field(ge=1, le=HARD_MAX_INSTANCES)
    profile: _Profile
    tier: Literal["cheapest"]
    sources: list[_Key] = Field(default_factory=list, max_length=16)
    context: Optional[TemporaryContext] = None
    reasons: list[_Reason] = Field(min_length=1, max_length=len(REASON_CODES))
    features_used: list[_Feature] = Field(default_factory=list, max_length=len(FEATURE_NAMES))
    estimated_cost: Optional[Cost] = None


class PlanTotals(Frozen):
    instances: int = Field(ge=1, le=HARD_MAX_INSTANCES * MAX_OUTPUTS)
    estimated_cost: Optional[Cost] = None


class RoutingPlan(Frozen):
    schema_: Literal["epinoic.integration.routing-plan.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.0"]
    origin: Literal["router", "floor"]
    plan_id: _Key
    ids: RequestIds
    request_sha256: Sha256
    router: RouterIdentity
    transfers: list[TransferPlan] = Field(min_length=1, max_length=MAX_OUTPUTS)
    totals: PlanTotals

    model_config = Frozen.model_config | {"populate_by_name": True}


# --------------------------------------------------------------------------------------------- validation


def _parsed(raw: Any, code: str) -> Any:
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            return loads_strict(raw)
        except CanonicalError as exc:
            raise IntegrationError(code, f"not protocol JSON: {exc}") from None
    return raw


def _walk(value: Any):
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                yield ("key", k)
                stack.append(v)
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
        elif isinstance(node, str):
            yield ("str", node)


def _hidden(value: Any) -> Optional[str]:
    for kind, item in _walk(value):
        if kind == "key" and item in _HIDDEN_KEYS:
            return f"a member named {item!r}"
        if kind == "str" and _OVS_RE.search(item):
            return "an overseer finding code"
    return None


def _model_named(value: Any) -> Optional[str]:
    for kind, item in _walk(value):
        if kind == "key" and item in _MODEL_KEYS:
            return f"a member named {item!r}"
    return None


def _model_value(*values: Any) -> Optional[str]:
    """Why one of ``values`` (free-form strings a router chooses) names a model family, or ``None``."""
    for v in values:
        if isinstance(v, str) and _MODEL_VALUE_RE.search(v):
            return "a value that names a model family"
    return None


def _router_name(data: Any) -> Any:
    router = data.get("router") if isinstance(data, dict) else None
    return router.get("name") if isinstance(router, dict) else None


def request_digest(request: Union[RoutingRequest, dict]) -> str:
    data = dump(request) if isinstance(request, RoutingRequest) else request
    return sha256_json(data)


def check_request(raw: Any) -> RoutingRequest:
    """Validate a routing request (the overseer side builds it; the router receives it). ``KIT-RT-014`` for anything out
    of contract, ``KIT-RT-011`` when it carries what a blind dossier hides."""
    data = _parsed(raw, "KIT-RT-014")
    if not isinstance(data, dict):
        raise IntegrationError("KIT-RT-014", "a routing request is a JSON object")
    hidden = _hidden(data)
    if hidden:
        raise IntegrationError("KIT-RT-011", f"the request carries {hidden}, which a blind dossier hides")
    try:
        return RoutingRequest.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError("KIT-RT-014", f"the request does not validate ({exc.error_count()} error(s))") from None


def check_hello(raw: Any) -> RouterHello:
    data = _parsed(raw, "KIT-RT-015")
    if not isinstance(data, dict):
        raise IntegrationError("KIT-RT-015", "a router hello is a JSON object")
    if _model_named(data) or _model_value(_router_name(data)):
        raise IntegrationError("KIT-RT-015", "a router hello names no model: every overseer instance runs on the cheapest tier")
    try:
        hello = RouterHello.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError("KIT-RT-015", f"the hello does not validate ({exc.error_count()} error(s))") from None
    if hello.router.name.startswith(FLOOR_IDENTITY_PREFIX):
        # the floor's identity is reserved (PROTOCOL.md 7a.5): a router named by it is never attached, so no capabilities
        # report or verdict review names a router as the floor
        raise IntegrationError("KIT-RT-015", "a router hello names the minimum-oversight floor's reserved identity")
    return hello


_LOCATION_CODES = (("reasons", "KIT-RT-012"), ("features_used", "KIT-RT-012"), ("estimated_cost", "KIT-RT-013"),
                   ("method", "KIT-RT-007"), ("profile", "KIT-RT-010"), ("tier", "KIT-RT-009"), ("instances", "KIT-RT-008"),
                   ("reviews", "KIT-RT-007"), ("parts", "KIT-RT-007"), ("context", "KIT-RT-007"), ("sources", "KIT-RT-007"))


def _validation_code(exc: ValidationError) -> str:
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ())]
        if err.get("type") in ("extra_forbidden", "missing"):
            return "KIT-RT-001"
        for name, code in _LOCATION_CODES:
            if name in loc:
                return code
    return "KIT-RT-001"


def check_plan(raw: Any, request: RoutingRequest, *, hello: RouterHello) -> RoutingPlan:
    """Validate a router's plan against its request and the attached router's hello, then against the floor. Raises
    :class:`IntegrationError` with the ``KIT-RT`` code of the first rule it breaks, in the order of PROTOCOL.md section
    7a.5; a rule about transfers is applied to every transfer before the next rule."""
    data = _parsed(raw, "KIT-RT-001")
    if not isinstance(data, dict):
        raise IntegrationError("KIT-RT-001", "a routing plan is a JSON object")
    hidden = _hidden(data)
    if hidden:
        raise IntegrationError("KIT-RT-011", f"the plan carries {hidden}, which a blind dossier hides")
    named = _model_named(data) or _model_value(data.get("plan_id"), _router_name(data))
    if named:
        raise IntegrationError("KIT-RT-009", f"the plan carries {named}: no plan names a model; every instance runs on the cheapest tier")
    for t in data.get("transfers", []) if isinstance(data.get("transfers"), list) else []:
        if isinstance(t, dict) and "tier" in t and t["tier"] != TIER:
            raise IntegrationError("KIT-RT-009", "a transfer names a tier other than the cheapest")
    try:
        plan = RoutingPlan.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError(_validation_code(exc), f"the plan does not validate ({exc.error_count()} error(s))") from None
    if plan.origin != "router" or plan.router == FLOOR_IDENTITY:
        raise IntegrationError("KIT-RT-003", "a router's plan cannot present itself as the overseer's floor plan")
    if plan.ids != request.ids or plan.request_sha256 != request_digest(request):
        raise IntegrationError("KIT-RT-002", "the plan is not bound to this request (ids or request digest differ)")
    if plan.router != hello.router:
        raise IntegrationError("KIT-RT-003", "the plan's router identity is not the attached router's")
    outputs = {o.transfer_key: o for o in request.outputs}
    keys = [t.transfer_key for t in plan.transfers]
    if any(k not in outputs for k in keys):
        raise IntegrationError("KIT-RT-004", "the plan names a transfer the request does not hold")
    if len(set(keys)) != len(keys):
        raise IntegrationError("KIT-RT-006", "the plan names one transfer twice")
    if set(keys) != set(outputs):
        raise IntegrationError("KIT-RT-005", "the plan leaves a transfer of the request without a review")
    for code, rule in _transfer_rules(request, hello, outputs):  # PROTOCOL.md 7a.5: each rule over every transfer, in order
        for t in plan.transfers:
            problem = rule(t)
            if problem:
                raise IntegrationError(code, problem)
    maximum = min(request.limits.max_instances, HARD_MAX_INSTANCES)
    for t in plan.transfers:
        if t.instances > maximum:
            raise IntegrationError("KIT-RT-008", f"a transfer needs {t.instances} distinct instances, over the pool's maximum of {maximum}")
    total = sum(t.instances for t in plan.transfers)
    if plan.totals.instances != total:
        raise IntegrationError("KIT-RT-013", "the plan's total instances are not the sum of its transfers")
    cost = plan.totals.estimated_cost
    if cost is None or cost.tokens != sum(t.estimated_cost.tokens for t in plan.transfers) or cost.seconds != sum(t.estimated_cost.seconds for t in plan.transfers):
        raise IntegrationError("KIT-RT-013", "the plan's total cost is not the sum of its transfers")
    below = below_floor(plan, floor_plan(request))
    if below:
        raise IntegrationError("KIT-RT-020", below)
    return plan


def _transfer_rules(request: RoutingRequest, hello: RouterHello, outputs: dict) -> tuple[tuple[str, Callable[[TransferPlan], Optional[str]]], ...]:
    """The per-transfer rules of :func:`check_plan` in the order of PROTOCOL.md section 7a.5, each with its code and a
    function giving why a transfer breaks it (``None`` when it does not). Each rule is applied to every transfer before
    the next rule, so a plan's code does not depend on the order of its transfers."""
    def method(t: TransferPlan) -> Optional[str]:
        problem = _method_problem(t, outputs[t.transfer_key], request)
        if problem:
            return problem
        return None if t.method in hello.methods else "the plan uses a method its router's hello does not declare"

    def profile(t: TransferPlan) -> Optional[str]:
        if t.profile in request.limits.profiles and t.profile in hello.profiles:
            return None
        return "the plan uses an overseer profile that is not available"

    def vocabulary(t: TransferPlan) -> Optional[str]:
        if len(set(t.reasons)) == len(t.reasons) and len(set(t.features_used)) == len(t.features_used):
            return None
        return "a reason or a feature is listed twice"

    def cost(t: TransferPlan) -> Optional[str]:
        return None if t.estimated_cost is not None else "a router's plan estimates the cost of every transfer"

    return (("KIT-RT-007", method), ("KIT-RT-010", profile), ("KIT-RT-012", vocabulary), ("KIT-RT-013", cost))


def _method_problem(t: TransferPlan, out: OutputFeatures, request: RoutingRequest) -> Optional[str]:
    synthesis = request.topology.synthesis
    if t.method == "N_FOLD":
        if request.topology.kind != "combined" or t.transfer_key != synthesis:
            return "N_FOLD reviews only the combinator's output of a combined answer"
        if t.sources != list(request.topology.sources):
            return "an N_FOLD review names exactly the combined answer's sources, in order"
        if t.context is None or t.parts != 1 or t.instances != t.reviews:
            return "an N_FOLD review has a bounded request-scoped context, one part and one instance per review"
        return None
    if t.sources or t.context is not None:
        return "only an N_FOLD review names sources or a temporary context"
    if request.topology.kind == "combined" and t.transfer_key == synthesis:
        return "the combinator's output of a combined answer is reviewed N_FOLD"
    if t.method == "IN_DEPTH" and (t.reviews != 1 or t.parts != 1):
        return "IN_DEPTH is one instance examining the whole response"
    if t.method == "SPLIT" and (t.reviews != 1 or t.parts < 2):
        return "SPLIT divides the work into at least two parts, each reviewed once"
    if t.method == "DUPLICATE" and t.reviews < MIN_AGREEMENT_REVIEWS:
        return "DUPLICATE is at least two independent reviews"
    if t.instances != t.reviews * t.parts:
        return "a transfer's instances are its reviews times its parts"
    return None


# --------------------------------------------------------------------------------------------- the floor


def risk_signals(out: OutputFeatures) -> list[str]:
    """The agreement signals that hold for one output, as reason codes (empty: one complete review is the floor)."""
    found: list[str] = []
    if out.receipt.status == "REJECTED":
        found.append("risk_receipt_rejected")
    if out.receipt.error_codes:
        found.append("risk_error_findings")
    if out.repeated_faults > 0:
        found.append("risk_repeated_faults")
    if any(out.engine_statuses.get(s, 0) > 0 for s in _NEGATIVE):
        found.append("risk_negative_results")
    if out.stem and (any(out.engine_statuses.get(s, 0) > 0 for s in _UNDECIDED)
                     or any(c in _STEM_UNDECIDED_CODES for c in out.receipt.warning_codes)):
        found.append("risk_stem_undecided")
    return found


def _floor_reviews(out: OutputFeatures) -> int:
    return MIN_AGREEMENT_REVIEWS if risk_signals(out) else 1


def floor_plan(request: RoutingRequest) -> RoutingPlan:
    """The deterministic minimum-oversight plan (:data:`FLOOR_RULES`): the plan that runs when no router is attached and
    when a router's plan is refused. It reads the same risk signals the router reads, on the standard profile."""
    transfers: list[TransferPlan] = []
    feature_of = dict(AGREEMENT_SIGNALS)
    for out in request.outputs:
        signals = risk_signals(out)
        reviews = MIN_AGREEMENT_REVIEWS if signals else 1
        features = sorted({feature_of[s] for s in signals}, key=FEATURE_NAMES.index)
        if request.topology.kind == "combined" and out.transfer_key == request.topology.synthesis:
            transfers.append(TransferPlan(
                transfer_key=out.transfer_key, method="N_FOLD", reviews=reviews, parts=1, instances=reviews, profile="standard",
                tier=TIER, sources=list(request.topology.sources),
                context=TemporaryContext(scope="request", contents="validated_outcomes", max_bytes=CONTEXT_MAX_BYTES, discard="after_request"),
                reasons=["topology_combined", *signals, "profile_standard"], features_used=sorted({"topology", *features}, key=FEATURE_NAMES.index)))
            continue
        method = "DUPLICATE" if signals else "IN_DEPTH"
        source = ["topology_source"] if request.topology.kind == "combined" else []
        transfers.append(TransferPlan(
            transfer_key=out.transfer_key, method=method, reviews=reviews, parts=1, instances=reviews, profile="standard", tier=TIER,
            reasons=[*(signals or ["baseline_single_review"]), *source, "profile_standard"],
            features_used=sorted({*features, *(["topology"] if source else [])}, key=FEATURE_NAMES.index)))
    total = sum(t.instances for t in transfers)
    body = {"request_sha256": request_digest(request), "transfers": [dump(t) for t in transfers]}
    return RoutingPlan(schema=PLAN_SCHEMA, protocol=PROTOCOL, port_version=PORT_VERSION, origin="floor",
                       plan_id="floor-" + sha256_json(body)[:32], ids=request.ids, request_sha256=request_digest(request),
                       router=FLOOR_IDENTITY, transfers=transfers, totals=PlanTotals(instances=total))


def _independent_reviews(t: TransferPlan) -> int:
    return t.reviews  # IN_DEPTH and SPLIT are 1 complete review each; DUPLICATE and N_FOLD their review count


def below_floor(plan: RoutingPlan, floor: RoutingPlan) -> Optional[str]:
    """``None`` when ``plan`` gives every transfer at least the floor's oversight, else why it does not. The profile is
    not part of the floor (a profile changes how an instance reads the same pack, not how many reviews there are)."""
    mine = {t.transfer_key: t for t in plan.transfers}
    for f in floor.transfers:
        t = mine.get(f.transfer_key)
        if t is None:
            return "a transfer has no review"
        if f.method == "N_FOLD" and (t.method != "N_FOLD" or t.sources != f.sources):
            return "a combined answer's output is not reviewed N_FOLD over all its sources"
        if _independent_reviews(t) < _independent_reviews(f):
            return f"a transfer gets {_independent_reviews(t)} independent review(s); its risk signals call for {_independent_reviews(f)}"
    return None


# --------------------------------------------------------------------------------------------- admission and the router client


@dataclass(frozen=True)
class Admission:
    """What the overseer runs: the router's plan when it is in contract and at or above the floor, else the floor plan.
    ``refusal`` names why a router's plan was not adopted (``None`` when it was, or when no router is attached)."""
    effective: RoutingPlan
    origin: Literal["router", "floor"]
    refusal: Optional[str]
    detail: str
    router: Optional[RouterIdentity]
    floor: RoutingPlan

    def record(self) -> dict:
        """The admission as recorded with the review: no plan content beyond the closed plan itself."""
        return {"origin": self.origin, "refusal": self.refusal, "router": dump(self.router) if self.router else None,
                "plan_id": self.effective.plan_id, "floor_plan_id": self.floor.plan_id, "instances": self.effective.totals.instances}


def admit_plan(request: RoutingRequest, raw_plan: Any, *, hello: Optional[RouterHello]) -> Admission:
    """Admit a router's plan, or run the floor. Never raises for anything the router returns."""
    floor = floor_plan(request)
    if hello is None:
        return Admission(floor, "floor", None, "no router is attached: the floor plan runs", None, floor)
    if raw_plan is None:
        return Admission(floor, "floor", "KIT-RT-016", "the router returned no plan", hello.router, floor)
    try:
        plan = check_plan(raw_plan, request, hello=hello)
    except IntegrationError as exc:
        return Admission(floor, "floor", exc.code, exc.detail, hello.router, floor)
    return Admission(plan, "router", None, "", hello.router, floor)


#: A router call that produced no answer to validate (``router_child.RouterFailure``): ``code`` is ``KIT-RT-016``
#: (``KIT-RT-015`` for a module without the two functions); ``detail`` never carries anything the router wrote.
RouterFailure = _child.RouterFailure
_child_env = _child.child_env


def run_router(module: str, op: str, request_json: Optional[str], timeout_s: float) -> str:
    """One call of the flash router (``op`` ``hello`` or ``plan``) in its own process, waiting at most ``timeout_s``
    (``router_child.launch``).

    Returns the text the router's function returned. Raises :class:`RouterFailure` for everything else: the service
    could not mark itself non-dumpable (Linux), the process could not start, the module cannot be imported or lacks the
    function, the function raised (``SystemExit`` and ``KeyboardInterrupt`` included) or returned a non-text value, the
    answer is not UTF-8 or larger than :data:`MAX_ANSWER_BYTES`, or no answer came within ``timeout_s`` (the process and
    its children are then killed). The process gets ``python -I`` (no user site, no ``PYTHON*`` variable, no current
    directory on its path), the service's import path, and only the variables of :data:`CHILD_ENV_NAMES`: no
    ``EPINOIC_`` variable is in its environment, and on Linux a router without root or ``CAP_SYS_PTRACE`` cannot read
    the service's environment or memory either."""
    return _child.launch(module, op, request_json, timeout_s)


@dataclass(frozen=True)
class RouterAttachment:
    """The result of attaching a router: its validated hello and its plan function, or why none is attached.

    ``plan_fn(request_json, timeout_s)`` returns the router's answer text or raises :class:`RouterFailure`;
    :func:`attach_router` makes one that runs the router in its own process (:func:`run_router`). ``module`` is the
    module the service attached (``None`` when no router is attached)."""
    hello: Optional[RouterHello]
    plan_fn: Optional[Callable[[str, float], Any]]
    refusal: Optional[str]
    detail: str
    module: Optional[str] = None

    @property
    def attached(self) -> bool:
        return self.hello is not None and self.plan_fn is not None


def attach_router(spec: Optional[str], *, timeout_s: float = HELLO_TIMEOUT_S, require_secret_boundary: bool = False) -> RouterAttachment:
    """Attach the flash router named by ``spec`` (``EPINOIC_FLASH_ROUTER``): unset, empty or ``"none"`` for no router,
    otherwise a module that exposes ``hello() -> str`` and ``plan(request_json: str) -> str``. The router is a separate
    agent: it runs in its own process (:func:`run_router`), gets JSON text and returns JSON text, and everything it
    returns is validated here as untrusted data. Not configured: detached, no refusal. Configured but not importable,
    failing or answering with anything but JSON: detached with ``KIT-RT-016``; a module without the two functions or a
    hello out of contract: detached with ``KIT-RT-015``. The service starts either way: the router is never required.

    ``require_secret_boundary`` (the hosted profile, which holds real keys): the router is started only where its
    process cannot read the service's environment or memory (``router_child.boundary_problem``: Linux, a service that is
    not root and holds no ``CAP_SYS_PTRACE``, marked non-dumpable); elsewhere it is detached with ``KIT-RT-016`` before
    any router process starts."""
    if spec is None or spec.strip() in ("", "none"):
        return RouterAttachment(None, None, None, "no router configured: the floor plan runs")
    name = spec.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", name):
        return RouterAttachment(None, None, "KIT-RT-015", "the router module name is not a Python module path")
    if require_secret_boundary:
        problem = _child.boundary_problem()
        if problem is not None:
            return RouterAttachment(None, None, "KIT-RT-016", f"{problem}: a hosted service starts a router only where it cannot read "
                                    "the service's keys, so the floor plan runs")
    try:
        text = run_router(name, "hello", None, timeout_s)
    except RouterFailure as exc:
        return RouterAttachment(None, None, exc.code, f"{exc.detail}: the floor plan runs")
    try:
        data = loads_strict(text)
    except CanonicalError:
        return RouterAttachment(None, None, "KIT-RT-016", "the router's hello is not JSON: the floor plan runs")
    try:
        hello = check_hello(data)
    except IntegrationError as exc:
        return RouterAttachment(None, None, exc.code, exc.detail)
    return RouterAttachment(hello, partial(run_router, name, "plan"), None, "", module=name)


def route(request: RoutingRequest, attachment: Optional[RouterAttachment], *, timeout_s: float = PLAN_TIMEOUT_S) -> Admission:
    """Ask the attached router for a plan, waiting at most ``timeout_s``, and admit it. Without a router the floor runs
    (no refusal). A router that fails (raises, exits, does not answer in time, answers with a non-text value or with text
    that is not JSON) is refused with ``KIT-RT-016`` and the floor runs; JSON that is not an admissible plan is refused by
    :func:`admit_plan` with its own code. No time left (``timeout_s <= 0``): the router is not asked, ``KIT-RT-016``.
    Never raises for anything the router does."""
    if attachment is None or not attachment.attached:
        return admit_plan(request, None, hello=None)
    floor = floor_plan(request)
    identity = attachment.hello.router  # type: ignore[union-attr]

    def refused(code: str, detail: str) -> Admission:
        return Admission(floor, "floor", code, detail, identity, floor)

    if timeout_s <= 0:
        return refused("KIT-RT-016", "no time was left in the call's budget for the router: the floor plan runs")
    try:
        raw = attachment.plan_fn(canonical_json(dump(request)), timeout_s)  # type: ignore[misc]
    except RouterFailure as exc:
        return refused(exc.code, exc.detail)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - an in-process plan function (tests, tools): whatever it raises, the floor runs
        return refused("KIT-RT-016", f"the router failed ({type(exc).__name__})")
    if not isinstance(raw, str):
        return refused("KIT-RT-016", "the router answered with something other than JSON text")
    try:
        data = loads_strict(raw)
    except CanonicalError:
        return refused("KIT-RT-016", "the router's answer is not JSON")
    return admit_plan(request, data, hello=attachment.hello)
