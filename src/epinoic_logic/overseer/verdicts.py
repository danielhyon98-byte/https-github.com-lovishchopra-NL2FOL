"""The verdict contract ``overseer_verdict/1.0``: what an overseer agent returns, and the pack it was produced under.

An overseer agent reads one dossier (:mod:`~epinoic_logic.overseer.dossier`) and returns one verdict: a list of
accusations, each pinned to identifiers and JSON Pointers of that dossier, and engine statements that copy the status
of results it relied on. A verdict is an AGENT OUTPUT. The infrastructure parses it strictly as data
(:mod:`~epinoic_logic.overseer.intake`), validates every accusation against the journal and the signed engine results
(:mod:`~epinoic_logic.overseer.validate`) and never obeys it: an accusation counts only when a deterministic check
reproduces it (trust rule TR3), and the router then acts on that check's ``OVS-*`` finding, never on the agent's
words. Nothing in this module confers authority on a verdict.

* :data:`VERDICT_CONTRACT` and :data:`DOSSIER_VERSION` are the contract versions the dossier names and the verdict
  copies; a verdict written to another contract is invalid (AGENT-005).
* :class:`PackIdentity` names the knowledge pack (name, version, digest) a dossier was issued under and a verdict was
  produced under. It lives here, not in the loader, so the protocol does not depend on reading pack files.
* :class:`AgentVerdict`, :class:`Accusation`, :class:`EvidenceItem`, :class:`EngineStatement`: every model forbids
  extra fields, validates strictly (no coercion: an identifier written as a number is a schema fault) and bounds every
  length, so a verdict cannot carry unbounded or unexpected content.
* :data:`KIND_CHECKS` maps each :data:`AccusationKind` to the ``OVS-*`` codes that decide it, in the order of the
  pack's Kinds and codes table (a drift test of the knowledge stage keeps the two identical). ``translation_unfaithful``
  and ``other`` map to no code (:data:`UNCHECKED_KINDS`): they are always unresolved and go to human review.
* Translator oversight: the translator is an agent like any other, so its translations have kinds of their own.
  ``translation_invalid`` (OVS-TRN-001, 002), ``translation_ungrounded`` (OVS-TRN-003, 004, 005) and
  ``translation_circular`` (OVS-TRN-006) name faults a deterministic check decides; ``translation_unfaithful`` names a
  meaning fault no check compares (a dropped condition, a flipped comparison or direction, an invented premise, an
  ambiguity resolved in words, a claim forced into IR that should have been left unsupported): it stays advisory and
  goes to human review. OVS-TRN-007 (an outcome summary that states more than its translation and signed result)
  confirms ``receipt_altered``. The lens ``translation_fidelity`` focuses an agent on the translations.
* :data:`NO_DOSSIER_MARKER` is the one object an agent outputs when it received no dossier (When unsure U1); the intake
  records it as AGENT-005 with the reason ``no_dossier``, so scoring counts it as no review, not as a malformed verdict.

Deviations from ``docs/OVERSEER_DESIGN.md`` sections 9.3 and 17.10, listed as each stage requires:

* ``transfers_reviewed`` is bounded by the journal's entry cap (4096 identifiers), not by the 64 of an accusation's
  identifier lists, so an agent can list every transfer of a long task;
* ``engine_statements`` is bounded at 256 (the design gives no bound);
* ``asserted_status`` must be one of the 13 status spellings of Verdict format V19 (a schema fault otherwise), and a
  ``quote`` must be non-empty; ``statement`` must be non-empty (Verdict format V20 item 4);
* accusation ids must be unique within a verdict (Verdict format V8), checked by the schema;
* :data:`KIND_CODE_QUALIFIERS` records the one qualified mapping of the table: ``figure_changed`` is confirmed by
  OVS-SYN-002 only when that finding names INT-LEDGER-023.
* translator oversight (founder's requirement, design section 18): the four translation kinds, OVS-TRN-007 under
  ``receipt_altered`` and the lens ``translation_fidelity`` are part of ``overseer_verdict/1.0`` and dossier 1.0. Neither
  contract had been released (no verdict exists outside this branch), so they were extended in place rather than
  versioned (design decision 33).
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ..engine.statuses import VerificationStatus

__all__ = [
    "VERDICT_CONTRACT", "VERDICT_CONTRACT_NAME", "DOSSIER_VERSION", "NO_DOSSIER_MARKER", "is_no_dossier", "PackIdentity", "AccusationKind",
    "ACCUSATION_KINDS", "KIND_CHECKS", "KIND_CODE_QUALIFIERS", "UNCHECKED_KINDS", "TRANSLATION_KINDS", "Lens", "LENSES", "Mode", "MODES", "EvidenceItem", "Accusation", "EngineStatement",
    "AgentVerdict", "ID_FIELDS", "accusation_identifiers", "MAX_ACCUSATIONS", "MAX_EVIDENCE", "MAX_IDS", "MAX_QUOTE_CHARS", "MAX_TEXT_CHARS",
    "MAX_TRANSFERS_REVIEWED", "MAX_ENGINE_STATEMENTS", "STATUS_SPELLINGS", "IdentifierStr", "PACK_NAME_PATTERN", "PACK_VERSION_PATTERN", "SHA256_PATTERN",
]

#: The verdict contract a dossier names and a verdict copies (Verdict format V2).
VERDICT_CONTRACT = "overseer_verdict/1.0"
VERDICT_CONTRACT_NAME = "overseer_verdict"
#: The dossier contract version (section 9.2).
DOSSIER_VERSION = "1.0"
#: The whole output of an agent that received no dossier (When unsure U1).
NO_DOSSIER_MARKER: Mapping[str, Any] = {"no_dossier": True}

PACK_NAME_PATTERN = r"^[a-z0-9-]{1,64}$"
PACK_VERSION_PATTERN = r"^[0-9]+\.[0-9]+$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
VERDICT_ID_PATTERN = r"^[A-Za-z0-9._-]{1,128}$"
ACCUSATION_ID_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
#: An identifier copied from a dossier: 1 to 256 characters, no control characters (no line breaks).
IDENTIFIER_PATTERN = r"^[^\x00-\x1f\x7f]{1,256}$"
#: A JSON Pointer (RFC 6901) into a dossier: at least one reference token; ``~`` only as ``~0`` or ``~1``.
POINTER_PATTERN = r"^(/([^~/]|~[01])*)+$"
#: A header string copied from a dossier (agent id, task id): 1 to 128 characters, no control characters.
HEADER_ID_PATTERN = r"^[^\x00-\x1f\x7f]{1,128}$"

MAX_ACCUSATIONS = 256
MAX_EVIDENCE = 32
MAX_IDS = 64
MAX_QUOTE_CHARS = 1000
MAX_TEXT_CHARS = 2000
MAX_POINTER_CHARS = 2048
MAX_TRANSFERS_REVIEWED = 4096
MAX_ENGINE_STATEMENTS = 256

#: Every status an engine statement may assert, spelled exactly as in ``results`` (Verdict format V19).
STATUS_SPELLINGS: tuple[str, ...] = tuple(s.value for s in VerificationStatus)
StatusSpelling = Literal[
    "ENTAILED", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE", "UNKNOWN", "TIMEOUT", "UNSUPPORTED",
    "INVALID_FORMALIZATION", "AMBIGUOUS_TRANSLATION", "NOT_ELIGIBLE", "INTERNAL_ERROR",
]

AccusationKind = Literal[
    "payload_altered", "receipt_altered", "receipt_status_wrong", "finding_missing", "result_unsigned_or_forged", "result_from_other_problem",
    "result_out_of_task", "replay_differs", "formal_status_wrong", "claim_not_in_response", "quotation_absent", "figure_changed",
    "self_certification_as_content", "forward_altered", "peer_document_altered", "synthesis_ledger_fault", "contradiction_unnamed", "false_conflict",
    "translation_invalid", "translation_ungrounded", "translation_circular", "translation_unfaithful", "other",
]

#: Each kind and the deterministic checks that confirm it, in the order of the pack's Kinds and codes table (design
#: section 9.3 with decision 31's additions: CUST-006 for ``payload_altered``, RCPT-006 and RCPT-007 for
#: ``receipt_altered``, RCPT-006 for ``result_out_of_task``; and section 18's translation kinds, with TRN-007 for
#: ``receipt_altered``). ``translation_unfaithful`` and ``other`` are decided by no check.
KIND_CHECKS: dict[str, tuple[str, ...]] = {
    "payload_altered": ("OVS-CUST-001", "OVS-CUST-002", "OVS-CUST-004", "OVS-CUST-006"),
    "receipt_altered": ("OVS-RCPT-001", "OVS-RCPT-006", "OVS-RCPT-007", "OVS-TRN-007"),
    "receipt_status_wrong": ("OVS-RCPT-002", "OVS-RCPT-003", "OVS-RCPT-008"),
    "finding_missing": ("OVS-RCPT-004", "OVS-SYN-002", "OVS-DIV-001"),
    "result_unsigned_or_forged": ("OVS-RES-003", "OVS-RES-009"),
    "result_from_other_problem": ("OVS-RES-004", "OVS-RES-010"),
    "result_out_of_task": ("OVS-RES-001", "OVS-RES-005", "OVS-RES-006", "OVS-RCPT-006"),
    "replay_differs": ("OVS-RES-007",),
    "formal_status_wrong": ("OVS-FORM-001", "OVS-FORM-002", "OVS-FORM-003", "OVS-FORM-004", "OVS-FORM-005"),
    "claim_not_in_response": ("OVS-FID-001",),
    "quotation_absent": ("OVS-FID-002", "OVS-FID-004"),
    "figure_changed": ("OVS-FID-003", "OVS-SYN-002"),
    "self_certification_as_content": ("OVS-FID-005", "OVS-FID-009"),
    "forward_altered": ("OVS-PEER-001",),
    "peer_document_altered": ("OVS-PEER-002", "OVS-FID-008"),
    "synthesis_ledger_fault": ("OVS-SYN-001", "OVS-SYN-002"),
    "contradiction_unnamed": ("OVS-JOINT-001", "OVS-SYN-003"),
    "false_conflict": ("OVS-JOINT-003",),
    "translation_invalid": ("OVS-TRN-001", "OVS-TRN-002"),
    "translation_ungrounded": ("OVS-TRN-003", "OVS-TRN-004", "OVS-TRN-005"),
    "translation_circular": ("OVS-TRN-006",),
    "translation_unfaithful": (),
    "other": (),
}
ACCUSATION_KINDS: tuple[str, ...] = tuple(KIND_CHECKS)
#: Kinds no deterministic check decides: always unresolved (OVS-AGENT-004), sent to human review.
UNCHECKED_KINDS: frozenset[str] = frozenset(k for k, codes in KIND_CHECKS.items() if not codes)
#: The translator-oversight kinds a deterministic check decides (OVS-TRN-001..006).
TRANSLATION_KINDS: frozenset[str] = frozenset({"translation_invalid", "translation_ungrounded", "translation_circular"})
#: ``(kind, code) -> INT codes``: the code confirms the kind only when its finding names one of these INT codes.
KIND_CODE_QUALIFIERS: dict[tuple[str, str], tuple[str, ...]] = {("figure_changed", "OVS-SYN-002"): ("INT-LEDGER-023",)}

Lens = Literal["custody_results", "content_fidelity", "translation_fidelity", "peer_synthesis", "general"]
LENSES: tuple[str, ...] = ("custody_results", "content_fidelity", "translation_fidelity", "peer_synthesis", "general")
Mode = Literal["blind", "informed"]
MODES: tuple[str, ...] = ("blind", "informed")

#: The six identifier lists of an accusation, in the order the pack writes them.
ID_FIELDS: tuple[str, ...] = ("message_ids", "receipt_ids", "claim_ids", "report_ids", "result_ids", "document_ids")


def is_no_dossier(obj: Any) -> bool:
    """True only for the exact "no dossier" object of When unsure U1: one key, the boolean ``true``."""
    return isinstance(obj, dict) and len(obj) == 1 and obj.get("no_dossier") is True


_STRICT = ConfigDict(extra="forbid", strict=True)
_STRICT_FROZEN = ConfigDict(extra="forbid", strict=True, frozen=True)

#: One identifier copied from a dossier.
IdentifierStr = Annotated[str, StringConstraints(pattern=IDENTIFIER_PATTERN)]


class PackIdentity(BaseModel):
    """The knowledge pack a dossier was issued under and a verdict was produced under: name, version and the pack
    digest (``pack_sha256`` of its manifest). Frozen and hashable, so a set of accepted packs is a set of these."""
    model_config = _STRICT_FROZEN
    name: str = Field(pattern=PACK_NAME_PATTERN, description="pack name, e.g. overseer-knowledge-docs")
    version: str = Field(pattern=PACK_VERSION_PATTERN, description="pack version MAJOR.MINOR")
    sha256: str = Field(pattern=SHA256_PATTERN, description="the pack digest (manifest pack_sha256), 64 lowercase hex")

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}"

    def key(self) -> tuple[str, str, str]:
        return (self.name, self.version, self.sha256)


class EvidenceItem(BaseModel):
    """One evidence item: a JSON Pointer into the dossier and, optionally, an exact quote of part of that field."""
    model_config = _STRICT
    pointer: str = Field(min_length=2, max_length=MAX_POINTER_CHARS, pattern=POINTER_PATTERN)
    quote: Optional[str] = Field(default=None, min_length=1, max_length=MAX_QUOTE_CHARS)


class Accusation(BaseModel):
    """One accusation: a kind from the closed list, the identifiers involved, at least one evidence item, and an
    advisory statement (free text: never parsed for instructions, never copied into a finding)."""
    model_config = _STRICT
    accusation_id: str = Field(pattern=ACCUSATION_ID_PATTERN)
    kind: AccusationKind
    claimed_severity: Literal["error", "warning"]
    message_ids: list[IdentifierStr] = Field(default_factory=list, max_length=MAX_IDS)
    receipt_ids: list[IdentifierStr] = Field(default_factory=list, max_length=MAX_IDS)
    claim_ids: list[IdentifierStr] = Field(default_factory=list, max_length=MAX_IDS)
    report_ids: list[IdentifierStr] = Field(default_factory=list, max_length=MAX_IDS)
    result_ids: list[IdentifierStr] = Field(default_factory=list, max_length=MAX_IDS)
    document_ids: list[IdentifierStr] = Field(default_factory=list, max_length=MAX_IDS)
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=MAX_EVIDENCE)
    statement: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class EngineStatement(BaseModel):
    """A status the agent read from ``results``: it names the result, copies the status exactly and points at the
    field it read it from. It is compared with the stored, signature-verified result; a different status, or an unknown
    result asserted as existing, is OVS-AGENT-001."""
    model_config = _STRICT
    result_id: str = Field(pattern=IDENTIFIER_PATTERN)
    asserted_status: StatusSpelling
    pointer: str = Field(min_length=2, max_length=MAX_POINTER_CHARS, pattern=POINTER_PATTERN)


class AgentVerdict(BaseModel):
    """``overseer_verdict/1.0``. The header (``contract``, ``pack``, ``agent_id``, ``task_id``, ``dossier_sha256``,
    ``lens``) is copied from the dossier; the intake checks it against the issue record. The body is advisory data."""
    model_config = _STRICT
    contract: Literal["overseer_verdict/1.0"]
    pack: PackIdentity
    verdict_id: str = Field(pattern=VERDICT_ID_PATTERN)
    agent_id: str = Field(pattern=HEADER_ID_PATTERN)
    task_id: str = Field(pattern=HEADER_ID_PATTERN)
    dossier_sha256: str = Field(pattern=SHA256_PATTERN)
    lens: Lens
    transfers_reviewed: list[IdentifierStr] = Field(max_length=MAX_TRANSFERS_REVIEWED)
    accusations: list[Accusation] = Field(max_length=MAX_ACCUSATIONS)
    engine_statements: list[EngineStatement] = Field(max_length=MAX_ENGINE_STATEMENTS)
    notes: str = Field(default="", max_length=MAX_TEXT_CHARS)

    @model_validator(mode="after")
    def _unique_accusation_ids(self) -> "AgentVerdict":
        ids = [a.accusation_id for a in self.accusations]
        if len(ids) != len(set(ids)):
            raise ValueError("accusation ids must be unique within a verdict")
        return self


def accusation_identifiers(acc: Accusation) -> dict[str, list[str]]:
    """The six identifier lists of an accusation, deduplicated in first-seen order."""
    return {name: list(dict.fromkeys(getattr(acc, name))) for name in ID_FIELDS}
