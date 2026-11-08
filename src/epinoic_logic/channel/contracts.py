"""Contracts for the inter-agent communication channel.

Every message between agents (router -> specialist, specialist -> router, agent ->
agent) passes through the channel. A request is turned into an explicit
``TaskRequest`` (what is asked, under which constraints, with which texts). A
response is checked against the request it answers before the recipient sees it,
and the recipient receives a ``TransmissionReceipt`` beside the payload saying
exactly what was checked and what was found.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from ..ir.canonical import sha256_hex
from ..integrity.contracts import IntegrityFinding
from ..named import NamedDiagnostic
from ..translate.contracts import ClaimVerificationOutcome, StructuralFinding, SuppliedText

ConstraintKind = Literal["max_words", "min_words", "max_paragraphs", "min_paragraphs", "must_cite_supplied_text", "must_address_all_items", "other"]
#: Longest receipt summary; the channel summarises per-check lists as counts and truncates defensively, never raising.
SUMMARY_MAX_CHARS = 8000


class RequestItem(BaseModel):
    """One thing the request asks the specialist to do (a question or instruction)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    item_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    kind: Literal["question", "instruction"] = "instruction"
    required: bool = True
    command_term: Optional[str] = Field(default=None, description="IB command term detected in the item, e.g. 'to what extent'")
    level: Optional[int] = Field(default=None, ge=1, le=3, description="command-term level: 1 recall, 2 apply/explain, 3 analyse/evaluate (needs a judgement)")


class Constraint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    constraint_id: str = Field(min_length=1, max_length=64)
    kind: ConstraintKind
    value: Optional[str] = Field(default=None, description="numeric value as exact text, when applicable")
    text: str = Field(min_length=1, max_length=1000, description="the constraint as stated in the request")
    excludes: list[Literal["working", "diagram"]] = Field(default_factory=list, max_length=2, description=(
        "what the request sets outside a word bound ('Write no more than 350 words, plus working and your diagram'): the "
        "bound is measured over the prose only, without working lines (equations, calculation lines, tables) and, for "
        "'diagram', without the description of a diagram"))


# ============================================================================================ revision requests
#: The contract of a revision request: the infrastructure's feedback to the specialist that wrote an answer, carried by a
#: re-issued request (``TaskRequest.revision``; envelope contract ``task_request/1.1``). Written only by the overseer's
#: hub operations from the journal, the answer's receipt and signed audits; never by an agent (``channel/feedback.py``).
REVISION_CONTRACT = "revision_request/1.0"
#: The version of the feedback allowlist and its templates (``channel.feedback.FEEDBACK_RULES``).
FEEDBACK_RULES_VERSION = "feedback-rules/1"
#: The envelope contract of a request that carries a revision block (every other request keeps ``task_request/1.0``).
REVISION_REQUEST_CONTRACT = "task_request/1.1"
#: Revision rounds of one answer's chain when the plan sets none (``WorkPlan.budgets['revision_rounds']``), and the most any
#: plan may set; 0 disables feedback.
DEFAULT_REVISION_ROUNDS = 2
HARD_MAX_REVISION_ROUNDS = 3
#: Bounds of one revision block.
MAX_FLAWS = 12
MAX_ADVISORY = 3
MAX_KEEP = 32
MAX_FLAW_CLAIMS = 4
MAX_FLAW_EVIDENCE = 4
MAX_FLAW_PARAMS = 8
#: The key id of the overseer subkey a revision block is signed under (the overseer's ``keys.FEEDBACK_KEY_ID``).
FEEDBACK_KEY_ID = "overseer-feedback"
_CODE_PATTERN = r"^[A-Z]{2,7}-[A-Z]{2,10}-\d{3}$"
_HEX64 = r"^[0-9a-f]{64}$"


class RevisionClaim(BaseModel):
    """A claim of the answer a flaw names: its id and the answer's own claim text, sanitised and cut
    (``channel.feedback.quote_text``)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    claim_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=600)


class RevisionEvidence(BaseModel):
    """What a flaw rests on: a receipt finding (``receipt_id#index``), an engine result (its id), a constraint (its id), an
    audit finding (``audit_id#index``), an excerpt of a text the specialist received (a document id of its request) or a
    validated overseer-agent accusation (``verdicts_audit_id#index``). ``detail`` holds numbers or an excerpt, never a
    finding message."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["receipt_finding", "engine_result", "constraint", "audit_finding", "excerpt", "advisory"]
    ref: str = Field(min_length=1, max_length=160)
    status: Optional[str] = Field(default=None, max_length=64)
    detail: str = Field(default="", max_length=300)


class RevisionFlaw(BaseModel):
    """One flaw fed back: an allowlisted finding (``code``) as a rule of ``FEEDBACK_RULES`` with short parameters. The
    ``instruction`` is the rule's template rendered with the parameters (``feedback.render_instruction``), never a finding
    message; ``signature`` is the flaw's fault signature (``fault-signature/1``)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    flaw_id: str = Field(pattern=r"^f(?:[1-9]|1[0-2])$")
    code: str = Field(pattern=_CODE_PATTERN)
    severity: Literal["error", "warning"]
    flaw_class: Literal["fidelity", "correctness", "coverage"]
    basis: Literal["channel", "engine", "audit", "advisory"]
    rule: str = Field(min_length=1, max_length=64, pattern=r"^[a-z]+\.[a-z_]+$")
    params: dict[str, str] = Field(default_factory=dict, max_length=MAX_FLAW_PARAMS)
    instruction: str = Field(min_length=1, max_length=500)
    removal_ok: bool
    claims: list[RevisionClaim] = Field(default_factory=list, max_length=MAX_FLAW_CLAIMS)
    evidence: list[RevisionEvidence] = Field(default_factory=list, max_length=MAX_FLAW_EVIDENCE)
    signature: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _bounded_params(self) -> "RevisionFlaw":
        for k, v in self.params.items():
            if not re.fullmatch(r"[a-z_]{1,32}", k) or len(v) > 200:
                raise ValueError("a flaw parameter is a short lower-case name with a value of at most 200 characters")
        return self


class RevisionKeep(BaseModel):
    """What the revision must keep unchanged: a request item, a constraint, a figure, date or quotation the answer states
    that also occurs in the question or a supplied text, and one entry for every claim no flaw names."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["request_item", "constraint", "figure", "date", "quotation", "claims"]
    ref: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=300)


class RevisionRequest(BaseModel):
    """``revision_request/1.0``: the signed feedback to the specialist that wrote an answer (``TaskRequest.revision``).
    The channel checks that it binds to the answer and holds only that specialist's own material (INT-REV-001); the
    transfer auditor verifies its signature under the overseer feedback key and that every flaw is a finding the journal
    or its own signed audits hold (OVS-FB-001). Feedback never changes a receipt, a signed result, a status or an audit."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract: Literal["revision_request/1.0"] = REVISION_CONTRACT
    rule_version: Literal["feedback-rules/1"] = FEEDBACK_RULES_VERSION
    revision_id: str = Field(pattern=r"^rev-[0-9a-f]{24}$")
    task_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    plan_id: str = Field(min_length=1, max_length=128)
    to_agent_id: str = Field(min_length=1, max_length=128)
    revises_message_id: str = Field(min_length=1, max_length=128)
    revises_report_id: str = Field(min_length=1, max_length=128)
    revises_receipt_id: str = Field(min_length=1, max_length=128)
    original_request_message_id: str = Field(min_length=1, max_length=128)
    round: int = Field(ge=1, le=HARD_MAX_REVISION_ROUNDS)
    max_rounds: int = Field(ge=1, le=HARD_MAX_REVISION_ROUNDS)
    flaws: list[RevisionFlaw] = Field(min_length=1, max_length=MAX_FLAWS)
    must_not_change: list[RevisionKeep] = Field(default_factory=list, max_length=MAX_KEEP)
    rules: list[str] = Field(default_factory=list, max_length=16)
    task_audit_id: str = Field(min_length=1, max_length=128)
    verdicts_audit_ids: list[str] = Field(default_factory=list, max_length=16)
    rendered_sha256: str = Field(pattern=_HEX64)
    scope_statement: str = Field(min_length=1, max_length=1000)
    signature: Optional[str] = Field(default=None, max_length=128)
    signature_key_id: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _shape(self) -> "RevisionRequest":
        if self.round > self.max_rounds:
            raise ValueError("a revision round past the chain's budget")
        if [f.flaw_id for f in self.flaws] != [f"f{i}" for i in range(1, len(self.flaws) + 1)]:
            raise ValueError("flaw ids are f1, f2, ... in order")
        advisory = [f for f in self.flaws if f.basis == "advisory"]
        if len(advisory) > MAX_ADVISORY or len(advisory) == len(self.flaws):
            raise ValueError(f"at most {MAX_ADVISORY} advisory flaws, and at least one flaw that is not advisory")
        rank = [(1 if f.basis == "advisory" else 0, 0 if f.severity == "error" else 1) for f in self.flaws]
        if rank != sorted(rank):
            raise ValueError("flaws are ordered errors first, advisory items last")
        if not self.must_not_change or self.must_not_change[-1].kind != "claims" or sum(k.kind == "claims" for k in self.must_not_change) != 1:
            raise ValueError("the keep list ends with its one entry for every claim no flaw names")
        return self


class TaskRequest(BaseModel):
    """The router's request to a specialist, made explicit and immutable. ``revision`` (a revision request, contract
    ``revision_request/1.0``) is present only on a request the infrastructure re-issues to an answer's author; every dump
    leaves it out when it is absent (``exclude_none``), so every other request's payload and digest is unchanged."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    plan_id: str = Field(min_length=1, max_length=128)
    from_agent_id: str = Field(min_length=1, max_length=128)
    to_agent_id: str = Field(min_length=1, max_length=128)
    subject: str = Field(min_length=1, max_length=128)
    course_level: Optional[Literal["SL", "HL", "unknown"]] = "unknown"
    task_type: str = Field(min_length=1, max_length=128)
    user_input: str = Field(min_length=1, max_length=400_000)
    user_input_sha256: str = Field(min_length=64, max_length=64)
    items: list[RequestItem] = Field(default_factory=list, max_length=64)
    constraints: list[Constraint] = Field(default_factory=list, max_length=64)
    supplied_texts: list[SuppliedText] = Field(default_factory=list, max_length=16)
    created_at: str
    revision: Optional[RevisionRequest] = None

    @model_validator(mode="after")
    def _hash(self) -> "TaskRequest":
        if sha256_hex(self.user_input) != self.user_input_sha256:
            raise ValueError("user_input_sha256 does not match user_input")
        return self

    @model_serializer(mode="wrap")
    def _omit_absent_revision(self, handler: SerializerFunctionWrapHandler):
        data = handler(self)
        if isinstance(data, dict) and data.get("revision", 0) is None:
            del data["revision"]  # every dump of a request without a revision is the dump it was before the field existed
        return data


class TransmissionStatus(str, Enum):
    ACCEPTED = "ACCEPTED"                            # no findings
    ACCEPTED_WITH_FINDINGS = "ACCEPTED_WITH_FINDINGS"  # delivered; recipient must read the findings
    REJECTED = "REJECTED"                            # not delivered: identity, integrity or scope violation


class CoverageRecord(BaseModel):
    """Which claims address which request item. Heuristic unless an adapter tags claims: ``part_label`` when the item is a
    lettered or numbered part and the answer labels its parts (the claims under the same label address it),
    ``lexical_heuristic`` otherwise (shared content terms with a claim or with a paragraph's claims together)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    item_id: str
    addressed: bool
    addressed_by_claim_ids: list[str] = Field(default_factory=list)
    method: Literal["adapter_tag", "part_label", "lexical_heuristic", "not_checkable"]


class ConstraintResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    constraint_id: str
    satisfied: Optional[bool]
    method: Literal["formal", "deterministic", "not_checkable"]
    detail: str = Field(max_length=2000)
    formal_result_id: Optional[str] = None
    formal_status: Optional[str] = None
    claim_ids: list[str] = Field(default_factory=list, max_length=64, description=(
        "for a check of the report's own statement (receipt.formal_checks): the delivered claims whose text holds the "
        "clause the check was built from, so the router can tell which claim a failed or undecided check concerns"))


class TransmissionReceipt(BaseModel):
    """What the channel did to one message. Travels with the payload to the recipient
    and to the Overseer."""
    model_config = ConfigDict(extra="forbid")
    receipt_id: str
    message_id: str
    request_id: str
    task_id: str
    direction: Literal["router_to_specialist", "specialist_to_router", "agent_to_agent"]
    status: TransmissionStatus
    findings: list[IntegrityFinding] = Field(default_factory=list)
    coverage: list[CoverageRecord] = Field(default_factory=list)
    constraint_results: list[ConstraintResult] = Field(default_factory=list)
    outcomes: list[ClaimVerificationOutcome] = Field(default_factory=list)
    branch: Optional[str] = Field(default=None, description="subject branch that handled the message")
    structural_findings: list[StructuralFinding] = Field(default_factory=list, description="branch integrity-pack findings (deterministic)")
    formal_checks: list[ConstraintResult] = Field(default_factory=list, description="branch formal checks decided by the engine about the report's own statements")
    formal_result_ids: list[str] = Field(default_factory=list)
    summary: str = Field(max_length=SUMMARY_MAX_CHARS)
    created_at: str
    named_diagnostics: list[NamedDiagnostic] = Field(default_factory=list, description=(
        "the argument diagnosis of this transmission (rules argdiag-2): every outcome's named diagnostics, the report-level "
        "ones, and a named diagnostic for each structural or integrity finding that carries a defect label; at most "
        "named.MAX_PER_RECEIPT (an overflow is counted in the summary). Advisory: a warning or error one on a material claim "
        "is also an INT-ARG-001 finding, info ones never change the receipt status. Left out of every dump while empty"))
    named_overflow: int = Field(default=0, ge=0, description=(
        "how many named diagnostics beyond named.MAX_PER_RECEIPT the transmission had and the receipt does not list (counted, "
        "never dropped silently); left out of every dump while 0"))
    diagnosis_incomplete: list[str] = Field(default_factory=list, max_length=64, description=(
        "the report-level argument-diagnosis rules that raised, ran out of budget or overflowed their bound: what they would have "
        "found is not known, never 'none found'. Left out of every dump while empty"))

    @model_serializer(mode="wrap")
    def _omit_empty_named(self, handler: SerializerFunctionWrapHandler):
        data = handler(self)
        if isinstance(data, dict):
            for name, empty in (("named_diagnostics", []), ("named_overflow", 0), ("diagnosis_incomplete", [])):
                if name in data and data[name] == empty:
                    del data[name]
        return data

    @property
    def errors(self) -> list[IntegrityFinding]:
        return [f for f in self.findings if f.severity == "error"]
