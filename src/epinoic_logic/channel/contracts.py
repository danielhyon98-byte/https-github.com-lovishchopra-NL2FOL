"""Contracts for the inter-agent communication channel.

Every message between agents (router -> specialist, specialist -> router, agent ->
agent) passes through the channel. A request is turned into an explicit
``TaskRequest`` (what is asked, under which constraints, with which texts). A
response is checked against the request it answers before the recipient sees it,
and the recipient receives a ``TransmissionReceipt`` beside the payload saying
exactly what was checked and what was found.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, field_validator, model_serializer, model_validator

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


ScopeKind = Literal["whole", "part", "each_part", "answer_proper", "paragraph"]


class ConstraintScope(BaseModel):
    """The span of the answer a bound is set on (E2E B4). ``whole``: the whole answer (notes and meta-text left out, as
    always). ``part``: the answer's sections labelled with ``parts`` together ("keep (e) under 150 words"); ``each_part``:
    every listed part on its own ("(e) and (f) under 120 words each"). ``answer_proper``: the answer the request asks for,
    without a plan or outline and without side answers to the student's other questions ("max 500 words for the answer").
    ``paragraph``: the paragraph the request asks for ("ONE paragraph ... max 250 words"), without side answers. A scope
    the answer does not carry (no section labelled with the part) is reported, never measured on another span."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: ScopeKind = "whole"
    parts: list[str] = Field(default_factory=list, max_length=16, description="the part labels, lower-cased without brackets ('e', 'ii', '3')")


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
    scope: Optional[ConstraintScope] = Field(default=None, description=(
        "the span a word bound is set on (ConstraintScope); None is the whole answer, so a constraint of an earlier "
        "version dumps exactly as before"))


class TaskRequest(BaseModel):
    """The router's request to a specialist, made explicit and immutable."""
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

    @field_validator("course_level", mode="before")
    @classmethod
    def _no_level_is_unknown(cls, value):
        """A stated ``None`` is ``"unknown"`` (both mean no level is known), so the canonical dump, which leaves ``None`` out,
        reads back as the same record instead of as the default."""
        return "unknown" if value is None else value

    @model_validator(mode="after")
    def _hash(self) -> "TaskRequest":
        if sha256_hex(self.user_input) != self.user_input_sha256:
            raise ValueError("user_input_sha256 does not match user_input")
        return self


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


class ReceiptReference(BaseModel):
    """An earlier receipt on this channel that a transmission builds on, with what it left unresolved: its error and
    warning findings (the receipt's own, never findings it carried itself), its subject findings of warning or error
    severity, its branch formal checks that failed or stayed undecided and its request constraints that failed. A relayed
    or forwarded report carries the receipts of its earlier transmissions (its arrival from the specialist first), and
    a synthesis the receipts of the reports it cites, so a later transmission that re-checks less (a relay has no
    request; a forward re-checks nothing) never reads as a clean history."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    receipt_id: str
    message_id: str
    direction: Literal["router_to_specialist", "specialist_to_router", "agent_to_agent"]
    status: TransmissionStatus
    payload_kind: Literal["report", "synthesis"]
    payload_id: str
    unresolved_findings: list[IntegrityFinding] = Field(default_factory=list)
    unresolved_subject_findings: list[StructuralFinding] = Field(default_factory=list)
    unresolved_checks: list[ConstraintResult] = Field(default_factory=list)

    @property
    def unresolved(self) -> bool:
        return bool(self.unresolved_findings or self.unresolved_subject_findings or self.unresolved_checks)


#: How many claim ids the message of a carried finding names; the rest are counted.
CARRIED_NAMED_MAX = 8
#: The code of a finding carried from an earlier receipt (relay history).
HISTORY_CODE = "INT-HIST-001"


def _carried_claims(ids: list[str]) -> str:
    if not ids:
        return ""
    shown = ", ".join(ids[:CARRIED_NAMED_MAX])
    return " on claim(s) " + shown + (f" and {len(ids) - CARRIED_NAMED_MAX} more" if len(ids) > CARRIED_NAMED_MAX else "")


def carried_where(ref: ReceiptReference) -> str:
    """Where a carried finding comes from, as its message names it."""
    return f"receipt {ref.receipt_id} ({ref.direction}, {ref.status.value}, message {ref.message_id}) of {ref.payload_kind} {ref.payload_id!r}"


def carried_subject_severity(sf: StructuralFinding) -> str:
    """The severity a carried subject finding takes: an error stays an error, anything else unresolved is a warning."""
    return "error" if sf.severity == "error" else "warning"


def carried_finding(ref: ReceiptReference, f: IntegrityFinding) -> IntegrityFinding:
    """INT-HIST-001 for an unresolved finding ``f`` of the earlier receipt ``ref``: its own severity, claims, reports,
    agents, documents and signed result, and a message naming where it comes from and its code. The channel makes every
    carried finding with this function and the response gate recognises one only by making it again from the receipt's
    structured history (``channel.gate``), so no part of the message is ever parsed."""
    return IntegrityFinding(code=HISTORY_CODE, severity=f.severity,
                            message=f"carried from {carried_where(ref)}: {f.code} ({f.severity}){_carried_claims(list(f.claim_ids))}, "
                                    f"unresolved by any later transmission: {f.message}",
                            claim_ids=list(f.claim_ids), message_ids=list(dict.fromkeys([ref.message_id, *f.message_ids])),
                            report_ids=list(f.report_ids) or ([ref.payload_id] if ref.payload_kind == "report" else []), agent_ids=list(f.agent_ids),
                            document_ids=list(f.document_ids), formal_result_id=f.formal_result_id, related_result_ids=list(f.related_result_ids),
                            deterministic=f.deterministic)


def carried_subject_finding(ref: ReceiptReference, sf: StructuralFinding) -> IntegrityFinding:
    """INT-HIST-001 for an unresolved subject finding ``sf`` of the earlier receipt ``ref`` (:func:`carried_finding`)."""
    return IntegrityFinding(code=HISTORY_CODE, severity=carried_subject_severity(sf),
                            message=f"carried from {carried_where(ref)}: subject finding {sf.code} ({sf.severity}){_carried_claims(list(sf.claim_ids))}, "
                                    f"unresolved by any later transmission: {sf.message}",
                            claim_ids=list(sf.claim_ids), message_ids=[ref.message_id], report_ids=[ref.payload_id] if ref.payload_kind == "report" else [])


class TransmissionReceipt(BaseModel):
    """What the channel did to one message. Travels with the payload to the recipient
    and to the Overseer. ``history`` references the earlier receipts the transmission builds on (a relay or forward of
    a report: that report's earlier transmissions; a synthesis: the transmissions of the reports it cites), each with
    what it left unresolved; the unresolved findings are also carried into ``findings`` as INT-HIST-001 with their own
    severity, so the receipt's status and errors never read cleaner than the history it carries."""
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
    history: list[ReceiptReference] = Field(default_factory=list, description=(
        "earlier receipts on this channel that this transmission builds on, with what each left unresolved (relay history)"))
    summary: str = Field(max_length=SUMMARY_MAX_CHARS)
    created_at: str
    named_diagnostics: list[NamedDiagnostic] = Field(default_factory=list, description=(
        "the argument diagnosis of this transmission (rules argdiag-2): every outcome's named diagnostics, the report-level "
        "ones, and a named diagnostic for each structural or integrity finding that carries a defect label; at most "
        "named.MAX_PER_RECEIPT (an overflow is counted in the summary). Advisory: a warning or error one on a material claim "
        "is also an INT-ARG-001 finding, info ones never change the receipt status. Left out of every dump while empty"))

    @model_serializer(mode="wrap")
    def _omit_empty_named(self, handler: SerializerFunctionWrapHandler):
        data = handler(self)
        if isinstance(data, dict) and data.get("named_diagnostics", None) == []:
            del data["named_diagnostics"]
        return data

    @property
    def errors(self) -> list[IntegrityFinding]:
        return [f for f in self.findings if f.severity == "error"]
