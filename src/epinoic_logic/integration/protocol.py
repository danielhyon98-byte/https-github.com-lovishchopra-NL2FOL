"""Messages of the integration protocol ``epinoic.integration.v1`` (``integration/PROTOCOL.md``).

Every message is a JSON object with a closed key set, identified by ``schema`` and by ``protocol``. The models here are
pydantic models with ``extra="forbid"`` and ``frozen=True`` in strict mode (no coercion: an integer is an integer, a
boolean a boolean). Nothing here imports the engine or Z3: the constants the protocol carries verbatim (the engine scope
statement, the audit scope sentence, the thirteen statuses) are restated in this module and a test pins each one to
its source.

Ports defined here: the specialist port (:class:`SpecialistAnswer`), the checks port (:class:`TurnCheckRequest`,
:class:`TurnVerdict`) and the capabilities handshake (:class:`Capabilities`). The overseer, combinator and flash-router
ports have modules of their own (``overseer_port``, ``combinator_port``, ``router_port``).
"""
from __future__ import annotations

import re
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

__all__ = [
    "PROTOCOL", "PROTOCOL_HEADER", "INTEGRATION_CONTRACT_VERSION", "SCOPE_STATEMENT", "AUDIT_SCOPE_STATEMENT",
    "GATE_DISCLAIMER", "STATUSES", "DEFINITIVE", "POSITIVE", "NEGATIVE", "INCOMPLETE_STATUSES", "NOT_ATTEMPTED",
    "FORMAL_VALUES", "ID_PATTERN", "SHA256_PATTERN", "SLUG_PATTERN", "FINDING_CODE_PATTERN", "OVS_CODE_PATTERN", "AGENT_ID_PATTERN", "AgentId",
    "Id", "Sha256", "Timestamp", "Slug", "FindingCode", "OvsCode",
    "Frozen", "SpecialistPair", "SpecialistPortCaps", "StemCaps", "ChecksPortCaps", "OverseerPortCaps",
    "TranslationCaps", "PackRef", "CombinatorPortCaps", "RouterIdentity", "FloorRef", "RouterPortCaps", "Ports",
    "ComponentVersions", "BuildIdentity", "SelfTestReport", "SubjectMapRef", "ServiceLimits", "Signing",
    "Capabilities", "RuntimeRef", "SpecialistAnswer", "Ids", "SuppliedTextIn", "TaskIn", "TurnCheckRequest",
    "VerdictIds", "BoundAnswer", "Bound", "ServiceRef", "Deliverable", "ConsolidationRef", "SynthesisRef", "Delivery",
    "ReviewRef", "OverseerSection", "ReceiptSection", "ClaimEntry", "Counts", "Timings", "Signature", "TurnVerdict",
    "MODES", "POLICIES", "DECISIONS", "SUMMARIES", "ATTEMPTS", "FIDELITY", "CLAIM_SOURCES", "OVERSEER_REFUSALS",
    "SERVICE_ENVS", "WEBSITE_ROUTES", "SELF_CERTIFICATION_KEYS", "ROUTER_ATTACH_REFUSALS", "FLOOR_IDENTITY_PREFIX",
]

PROTOCOL = "epinoic.integration.v1"
#: Value of the ``Epinoic-Protocol`` header on every protocol request.
PROTOCOL_HEADER = "integration.v1"
#: The translator's integration contract version this protocol belongs to (``docs/integration-contract.md``).
INTEGRATION_CONTRACT_VERSION = "0.5"

#: The engine scope statement (``engine.statuses.SCOPE_STATEMENT``), carried verbatim by every verdict.
SCOPE_STATEMENT = (
    "This result concerns only the formal encoding it is bound to, under the encoded "
    "premises and the stated solver configuration. It does not establish that the "
    "premises are factually true, that the natural-language claim was translated "
    "faithfully, or that any interpretive judgement is correct. Grounding and "
    "semantic-fidelity information is reported separately and is advisory."
)
#: The overseer's audit scope sentence (trust rule TR6), carried verbatim by every verdict.
AUDIT_SCOPE_STATEMENT = (
    "This audit covers only the transfers journaled since the auditor was attached to the channel. It shows whether the "
    "recorded transfers, receipts and signed results agree with each other and with this repository's rules. It does "
    "not show that any claim is true or any reading correct."
)
#: The specialist runtime's gate disclaimer: a gate pass is a format precondition, never evidence of verification.
GATE_DISCLAIMER = "Deterministic format and policy heuristics. Not factual, academic or formal verification."

#: The thirteen statuses of the engine and the translation layer (``engine.statuses.VerificationStatus``).
STATUSES: tuple[str, ...] = (
    "ENTAILED", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE",
    "UNKNOWN", "TIMEOUT", "UNSUPPORTED", "INVALID_FORMALIZATION", "AMBIGUOUS_TRANSLATION", "NOT_ELIGIBLE", "INTERNAL_ERROR",
)
DEFINITIVE: frozenset[str] = frozenset(STATUSES[:6])
POSITIVE: frozenset[str] = frozenset({"ENTAILED", "CONSISTENT", "SATISFIABLE"})
NEGATIVE: frozenset[str] = frozenset({"COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "UNSATISFIABLE"})
#: The kit's marker for an eligible claim that was skipped (cap, budget, provider unavailable): a non-result.
NOT_ATTEMPTED = "NOT_ATTEMPTED"
#: Statuses that leave a material eligible claim's checks incomplete (decision-table row 5).
INCOMPLETE_STATUSES: frozenset[str] = frozenset({"UNKNOWN", "TIMEOUT", "INTERNAL_ERROR", NOT_ATTEMPTED})
FORMAL_VALUES: tuple[str, ...] = STATUSES + (NOT_ATTEMPTED,)

MODES: tuple[str, ...] = ("single", "duplicate", "combined")
POLICIES: tuple[str, ...] = ("verified-v1", "verified-v1-qualify")
DECISIONS: tuple[str, ...] = ("deliver", "revise", "refuse_unresolved", "refuse_incomplete", "refuse_integrity")
SUMMARIES: tuple[str, ...] = ("formally_checked", "partly_checked", "formal_only", "not_formally_checkable", "incomplete")
ATTEMPTS: tuple[str, ...] = ("attempted", "not_eligible", "skipped_cap", "skipped_budget", "provider_unavailable", "stem_budget")
FIDELITY: tuple[str, ...] = ("faithful", "unfaithful", "uncertain", "missing", "stale", "unbound", "without_evidence")
CLAIM_SOURCES: tuple[str, ...] = ("translation", "branch_check", "stem")
SERVICE_ENVS: tuple[str, ...] = ("development", "staging", "production", "sim")
WEBSITE_ROUTES: tuple[str, ...] = ("history", "english")
#: Closed labels for why the overseer did not allow delivery (``OverseerSection.refusal``). Phase 2 maps every reason the
#: overseer's ``delivery_decision`` and ``release_decision`` give onto exactly one of these.
OVERSEER_REFUSALS: tuple[str, ...] = (
    "clearance_failed", "clearance_pending", "final_audit_not_passed", "signature_invalid", "custody_failed", "stale",
    "consolidation_conflicting", "no_deliverable_output", "receipt_error_findings", "not_deliverable", "internal_error",
)
#: The refusals a router's attachment can give, as the handshake reports them (``ports.router.refusal``): a hello out of
#: contract or a module without ``hello()`` and ``plan()`` (``KIT-RT-015``), a router that failed (``KIT-RT-016``).
ROUTER_ATTACH_REFUSALS: tuple[str, ...] = ("KIT-RT-015", "KIT-RT-016")
#: The name the minimum-oversight floor's own identity carries (``router_port.FLOOR_IDENTITY``): reserved, so no router
#: may report it (its hello is refused, ``KIT-RT-015``) and no capabilities report may name an attached router by it.
FLOOR_IDENTITY_PREFIX = "minimum-oversight-floor"
#: Keys a caller might use to certify its own payload. Refused at the top level of every request and of every specialist
#: envelope (``KIT-REQ-005``), as the service's E505 does for ``/v1/verify``.
SELF_CERTIFICATION_KEYS: frozenset[str] = frozenset({"advisory_verification_status", "verified", "self_certified", "status"})

ID_PATTERN = r"^[A-Za-z0-9._:-]{1,128}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
#: A finding code of a receipt (INT-REQ-009, CORE-SRC-001, ST-DIM-001, INT-SUBJ-003/HI-SRC-001).
FINDING_CODE_PATTERN = r"^[A-Z][A-Z0-9]{0,15}(?:-[A-Z0-9]{1,16}){1,4}(?:/[A-Z][A-Z0-9]{0,15}(?:-[A-Z0-9]{1,16}){1,4})?$"
#: A deterministic overseer finding code (OVS-FID-003); OVS-AGENT-* codes never affect a clearance.
OVS_CODE_PATTERN = r"^OVS-[A-Z]{2,12}-[0-9]{3}$"
_KIT_DL_PATTERN = r"^KIT-DL-[0-9]{3}$"
_KIT_RT_PATTERN = r"^KIT-RT-[0-9]{3}$"
_ROUTER_NAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,63}$"
_ROUTER_VERSION_PATTERN = r"^[0-9]{1,4}(?:\.[0-9]{1,4}){0,3}$"

Id = Annotated[str, StringConstraints(pattern=ID_PATTERN)]
#: An agent id: the agents slug, ``<slug>@a`` or ``<slug>@b`` in duplicate mode, or ``synthesis`` for a combined answer.
AGENT_ID_PATTERN = r"^(?:[a-z0-9]+(?:-[a-z0-9]+)*(?:@[ab])?|synthesis)$"
AgentId = Annotated[str, StringConstraints(pattern=AGENT_ID_PATTERN, max_length=72)]
Sha256 = Annotated[str, StringConstraints(pattern=SHA256_PATTERN)]
Timestamp = Annotated[str, StringConstraints(pattern=TIMESTAMP_PATTERN)]
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN, max_length=64)]
FindingCode = Annotated[str, StringConstraints(pattern=FINDING_CODE_PATTERN)]
OvsCode = Annotated[str, StringConstraints(pattern=OVS_CODE_PATTERN)]
DlCode = Annotated[str, StringConstraints(pattern=_KIT_DL_PATTERN)]
RtCode = Annotated[str, StringConstraints(pattern=_KIT_RT_PATTERN)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Version = Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z.+-]{1,40}$")]
Schema = Annotated[str, StringConstraints(pattern=r"^epinoic\.[a-z0-9.-]{1,120}$")]


class Frozen(BaseModel):
    """Closed, immutable, strict: an unknown key is refused and no value is coerced."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


# --------------------------------------------------------------------------------------------- capabilities (handshake)


class SpecialistPair(Frozen):
    result: Schema
    runtime: Schema
    log: Schema


class SpecialistPortCaps(Frozen):
    version: Literal["1.0"]
    accepted: list[SpecialistPair] = Field(min_length=1, max_length=8)


class StemCaps(Frozen):
    branches: list[ShortText] = Field(min_length=1, max_length=8)
    report_budget_max_s: int = Field(ge=1, le=60)


class ChecksPortCaps(Frozen):
    version: Literal["1.0"]
    modes: list[Literal["single", "duplicate", "combined"]] = Field(min_length=1, max_length=3)
    named_policies: list[ShortText] = Field(min_length=1, max_length=8)
    stem: StemCaps


class OverseerPortCaps(Frozen):
    version: Literal["1.0"]
    mode: Literal["embedded", "sidecar"]
    auditor_version: Version
    pack_digests: list[Sha256] = Field(min_length=1, max_length=16)
    replay_mode: Literal["process"]
    inline_final_release: Literal[False]
    agents: Literal["off", "async"]
    profiles: list[Literal["standard", "fast"]] = Field(min_length=1, max_length=2)


class TranslationCaps(Frozen):
    provider: Literal["fixture", "anthropic", "openai_compatible"]
    tier: Literal["cheapest"]
    live: bool
    reviewer: Literal["none"]


class PackRef(Frozen):
    name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    version: Version
    sha256: Sha256


class CombinatorPortCaps(Frozen):
    version: Literal["1.0"]
    available: bool
    instruction_pack: Optional[PackRef] = None


class RouterIdentity(Frozen):
    """The flash router's identity as it reports it in its hello: name, version and the digests of its rules and of its
    recorded cost data. A plan must carry exactly this identity (``KIT-RT-003``)."""
    name: Annotated[str, StringConstraints(pattern=_ROUTER_NAME_PATTERN)]
    version: Annotated[str, StringConstraints(pattern=_ROUTER_VERSION_PATTERN)]
    rules_sha256: Sha256
    cost_data_sha256: Sha256


class FloorRef(Frozen):
    name: Literal["minimum-oversight-floor/1"]
    rules_sha256: Sha256


class RouterPortCaps(Frozen):
    """What the handshake reports about the flash router. The router is never required: without one the overseer runs
    the floor plan, and a router whose hello is out of contract is reported absent with its refusal code.

    The report is coherent: a router is ``attached`` exactly when its ``identity`` is reported, an attached router has
    no ``refusal``, a refusal is one an attachment can give (:data:`ROUTER_ATTACH_REFUSALS`), and no router is named by
    the floor's reserved identity (:data:`FLOOR_IDENTITY_PREFIX`). Anything else is out of contract (the Worker's
    handshake refuses it with ``KIT-HS-001``, as ``handshake.evaluate`` does)."""
    version: Literal["1.0"]
    required: Literal[False]
    attached: bool
    identity: Optional[RouterIdentity] = None
    refusal: Optional[RtCode] = None
    floor: FloorRef

    @model_validator(mode="after")
    def _coherent(self) -> "RouterPortCaps":
        if self.attached != (self.identity is not None) or (self.attached and self.refusal is not None):
            raise ValueError("a router is attached exactly when its identity is reported, and an attached router has no refusal")
        if self.refusal is not None and self.refusal not in ROUTER_ATTACH_REFUSALS:
            raise ValueError("a router's refusal is one its attachment can give (KIT-RT-015 or KIT-RT-016)")
        if self.identity is not None and self.identity.name.startswith(FLOOR_IDENTITY_PREFIX):
            raise ValueError("the floor's identity is reserved: no attached router is named by it")
        return self


class Ports(Frozen):
    specialist: SpecialistPortCaps
    checks: ChecksPortCaps
    overseer: OverseerPortCaps
    translation: TranslationCaps
    combinator: CombinatorPortCaps
    router: RouterPortCaps


class ComponentVersions(Frozen):
    ir: Version
    engine: Version
    policy: Version
    translator: Version
    z3: Version
    contract: Version


class BuildIdentity(Frozen):
    build_id: Sha256
    schema_id: Sha256
    policy_id: Sha256


class SelfTestReport(Frozen):
    passed: bool
    digests: list[Sha256] = Field(min_length=3, max_length=3)


class SubjectMapRef(Frozen):
    version: Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]{1,3}$")]
    sha256: Sha256


class ServiceLimits(Frozen):
    max_body_bytes: int = Field(ge=1024)
    max_answer_bytes: int = Field(ge=1)
    max_answers: int = Field(ge=1, le=2)
    max_translated_claims: int = Field(ge=0, le=64)
    checks_min_ms: int = Field(ge=1)
    checks_max_ms: int = Field(ge=1)
    turn_slots: int = Field(ge=1)


class Signing(Frozen):
    verdict_alg: Literal["hmac-sha256"]
    verdict_key_id: Id
    engine_key_id: Id


class Capabilities(Frozen):
    """``GET /v1/capabilities`` (PROTOCOL.md section 3, check 2)."""
    schema_: Literal["epinoic.integration.capabilities.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    service_env: Literal["development", "staging", "production", "sim"]
    versions: ComponentVersions
    build: BuildIdentity
    selftest: SelfTestReport
    ports: Ports
    subject_map: SubjectMapRef
    policies: list[Literal["verified-v1", "verified-v1-qualify"]] = Field(min_length=1, max_length=2)
    limits: ServiceLimits
    signing: Signing
    issued_at: Timestamp

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)


# --------------------------------------------------------------------------------------------- specialist port


class RuntimeRef(Frozen):
    schema_: Schema = Field(alias="schema")
    contract_version: Schema

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)


class SpecialistAnswer(Frozen):
    """``epinoic.integration.specialist-answer.v1``: the runtime's output wrapped, never changed (PROTOCOL.md section 4).

    ``log`` is the runtime's own ``redactForLog(result)`` without its ``turn`` and ``usage`` members; its shape is checked
    per result schema by :func:`epinoic_logic.integration.specialist_port.check_answer`. ``result_sha256`` is the digest
    of the whole frozen result, computed in the Worker; the service echoes it and never recomputes it."""
    schema_: Literal["epinoic.integration.specialist-answer.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    agent_id: AgentId
    runtime: RuntimeRef
    log: dict
    answer: Annotated[str, StringConstraints(min_length=1, max_length=49152)]
    answer_sha256: Sha256
    result_sha256: Sha256

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)


# --------------------------------------------------------------------------------------------- checks port: request


class Ids(Frozen):
    task_id: Id
    request_id: Id


class SuppliedTextIn(Frozen):
    document_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    title: Optional[Annotated[str, StringConstraints(max_length=500)]] = None
    text: Annotated[str, StringConstraints(min_length=1, max_length=49152)]


class TaskIn(Frozen):
    route: Optional[Literal["history", "english"]] = None
    slug: Slug
    subject: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    course_level: Literal["SL", "HL", "unknown"] = "unknown"
    task_type: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    user_text: Annotated[str, StringConstraints(min_length=1, max_length=49152)]
    user_text_sha256: Sha256
    supplied_texts: list[SuppliedTextIn] = Field(default_factory=list, max_length=16)


class TurnCheckRequest(Frozen):
    """``POST /v1/turns/check`` (``epinoic.integration.turn-check.v1``, PROTOCOL.md section 5.1)."""
    schema_: Literal["epinoic.integration.turn-check.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    mode: Literal["single", "duplicate", "combined"]
    ids: Ids
    task: TaskIn
    answers: list[SpecialistAnswer] = Field(min_length=1, max_length=2)
    policy: Literal["verified-v1", "verified-v1-qualify"]
    budget_ms: int = Field(ge=1)
    revision_of: Optional[Id] = None

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)


# --------------------------------------------------------------------------------------------- checks port: verdict


class VerdictIds(Frozen):
    task_id: Id
    request_id: Id
    plan_id: Id
    channel_uid: Id


class BoundAnswer(Frozen):
    agent_id: AgentId
    answer_sha256: Sha256
    result_sha256: Sha256
    report_id: Id
    message_id: Id


class Bound(Frozen):
    user_text_sha256: Sha256
    policy: Literal["verified-v1", "verified-v1-qualify"]
    mode: Literal["single", "duplicate", "combined"]
    answers: list[BoundAnswer] = Field(min_length=1, max_length=2)


class ServiceRef(Frozen):
    service_env: Literal["development", "staging", "production", "sim"]
    versions: ComponentVersions
    build: BuildIdentity
    subject_map_sha256: Sha256


class Deliverable(Frozen):
    agent_id: AgentId
    answer_sha256: Sha256
    message_id: Id


class ConsolidationRef(Frozen):
    id: Id
    status: Literal["CONSOLIDATED", "CONSOLIDATED_WITH_FINDINGS", "CONFLICTING", "NO_DELIVERABLE_OUTPUT"]
    basis: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]


class SynthesisRef(Frozen):
    id: Id
    receipt_status: Literal["ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED"]


class Delivery(Frozen):
    decision: Literal["deliver", "revise", "refuse_unresolved", "refuse_incomplete", "refuse_integrity"]
    deliverable: Optional[Deliverable] = None
    reasons: list[DlCode] = Field(default_factory=list, max_length=16)
    consolidation: Optional[ConsolidationRef] = None
    synthesis: Optional[SynthesisRef] = None


class ReviewRef(Frozen):
    """The asynchronous overseer-agent review of this turn: never on the critical path, never a release condition."""
    queued: bool
    plan_origin: Optional[Literal["router", "floor"]] = None
    plan_refusal: Optional[RtCode] = None
    router: Optional[RouterIdentity] = None


class OverseerSection(Frozen):
    mode: Literal["embedded", "sidecar"]
    final_audit_id: Id
    state: Literal["AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS", "AUDIT_PENDING", "AUDIT_FAILED"]
    error_codes: list[OvsCode] = Field(default_factory=list, max_length=64)
    delivery_allowed: bool
    refusal: Optional[Literal[
        "clearance_failed", "clearance_pending", "final_audit_not_passed", "signature_invalid", "custody_failed", "stale",
        "consolidation_conflicting", "no_deliverable_output", "receipt_error_findings", "not_deliverable", "internal_error",
    ]] = None
    review: ReviewRef


class ReceiptSection(Frozen):
    status: Literal["ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED"]
    error_codes: list[FindingCode] = Field(default_factory=list, max_length=128)
    warning_count: int = Field(ge=0)
    branch: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{0,63}$")]


class ClaimEntry(Frozen):
    claim_id: Id
    materiality: Literal["material", "supporting"]
    role: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{0,63}$")]
    excerpt: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    source: Literal["translation", "branch_check", "stem"]
    formal: Literal[
        "ENTAILED", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE",
        "UNKNOWN", "TIMEOUT", "UNSUPPORTED", "INVALID_FORMALIZATION", "AMBIGUOUS_TRANSLATION", "NOT_ELIGIBLE",
        "INTERNAL_ERROR", "NOT_ATTEMPTED",
    ]
    attempt: Literal["attempted", "not_eligible", "skipped_cap", "skipped_budget", "provider_unavailable", "stem_budget"]
    fidelity: Literal["faithful", "unfaithful", "uncertain", "missing", "stale", "unbound", "without_evidence"]
    evidence_resolved: bool
    release_permitted: bool
    result_id: Optional[Id] = None
    binding_digest: Optional[Sha256] = None


class Counts(Frozen):
    """Counts over ALL claims of the deliverable (the list ``claims`` is capped at 32, material first, and leaves out a
    claim without a verbatim excerpt), so the Worker re-derives the decision and the summary exactly from them, never
    from the list. Every count but ``claims_total`` concerns material claims; ``eligible`` excludes NOT_ELIGIBLE;
    ``permitted`` counts the positive results whose release assessment permits release; ``budget_skipped`` the
    incomplete ones the budget or the STEM budget left NOT_ATTEMPTED (decision-table row 5's KIT-DL-013)."""
    claims_total: int = Field(ge=0)
    material: int = Field(ge=0)
    eligible: int = Field(ge=0)
    attempted: int = Field(ge=0)
    definitive: int = Field(ge=0)
    positive: int = Field(ge=0)
    permitted: int = Field(ge=0)
    blocking: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    budget_skipped: int = Field(ge=0)
    not_eligible: int = Field(ge=0)


class Timings(Frozen):
    total_ms: int = Field(ge=0)
    translation_ms: int = Field(ge=0)
    solver_ms: int = Field(ge=0)
    overseer_ms: int = Field(ge=0)


class Signature(Frozen):
    alg: Literal["hmac-sha256"]
    key_id: Id
    value: Sha256


class TurnVerdict(Frozen):
    """``epinoic.integration.turn-verdict.v1`` (PROTOCOL.md section 5.4). ``receipt`` and ``claims`` describe the
    deliverable. No verdict carries the evidence bundle. ``summary`` is set only when the decision is ``deliver``."""
    schema_: Literal["epinoic.integration.turn-verdict.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    verdict_id: Id
    issued_at: Timestamp
    ids: VerdictIds
    bound: Bound
    service: ServiceRef
    delivery: Delivery
    overseer: OverseerSection
    receipt: ReceiptSection
    claims: list[ClaimEntry] = Field(default_factory=list, max_length=32)
    counts: Counts
    summary: Optional[Literal["formally_checked", "partly_checked", "formal_only", "not_formally_checkable", "incomplete"]] = None
    scope_statement: Literal[SCOPE_STATEMENT]  # type: ignore[valid-type]
    audit_scope_statement: Literal[AUDIT_SCOPE_STATEMENT]  # type: ignore[valid-type]
    timings: Timings
    signature: Signature

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)


def dump(model: BaseModel) -> dict:
    """A message as its JSON object (aliases applied, so ``schema`` is written as ``schema``)."""
    return model.model_dump(mode="json", by_alias=True)


_SCHEMA_RE = re.compile(r"^epinoic\.integration\.[a-z0-9-]+\.v1$")
