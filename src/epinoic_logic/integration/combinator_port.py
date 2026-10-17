"""The combinator port ``epinoic.integration.combinator-port.v1`` (``integration/PROTOCOL.md`` section 7; combined mode only).

**Input** (:class:`CombinatorInput`): the synthesis format built from the delivered claims (``build_input`` from the
delivered reports' payloads): per source report, the claim ids, roles, materiality, certainty, texts and their digests,
the closed transformation vocabulary and the instruction pack the service pins.

**Output** (:class:`CombinatorOutput`): one synthesis (synthesized claims citing source claims, each with one
transformation of the vocabulary; the dropped ledger; the contradictions it discloses), or a named refusal
(:class:`CombinatorRefusal`, a closed ``reason`` with its ``KIT-CB`` code). The port refuses an output out of contract;
the hub then validates the synthesis as untrusted data when it is relayed (``synthesis_payload`` builds the
``synthesis/1.0`` mapping: ``INT-REQ-009`` and ``INT-SYNTH-014`` for a bad vocabulary, ``INT-LEDGER-*`` for the ledger,
``INT-CONFLICT-002`` for an undisclosed contradiction), as it does for every synthesis. A port check is a contract check,
never a faithfulness check: the hub stays the independent checker of every synthesis.

**The published contract.** The JSON Schemas of the four messages (``integration/schemas/combinator-*.v1.schema.json``),
the synthesis contract's closed vocabularies (``synthesis-vocabulary.v1.json``, built from ``integrity.contracts`` by
:func:`vocabulary_document`) and the port's own rules (``combinator-port.v1.json``, :func:`port_rules_document`) are the
contract a combinator is built against; the kit's
generator copies them into the combinator sub-project (``combinator/src/epinoic_combinator/contract/``, drift-tested),
whose runner validates every output against them before it leaves the sub-agent. :func:`contract_digest` is their
digest, which the combinator's hello reports.

**Implementation.** v1 is the combinator sub-project (``combinator/``, package ``epinoic_combinator``: a separate agent
run on the cheapest tier through a provider interface, with a versioned instruction pack pinned by digest). The
translator never imports it; it is attached through this port in phase 2. Until then the handshake reports
``ports.combinator.available = false`` and the checks port omits the mode ``combined``. Nothing here imports the engine:
``integrity.contracts`` is read only inside :func:`vocabulary_document`.
"""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Annotated, Any, Literal, Mapping, Optional, Sequence

from pydantic import Field, StringConstraints, ValidationError, model_validator

from .canonical import CanonicalError, check_value, loads_strict, sha256_json, sha256_text
from .errors import IntegrationError
from .protocol import Frozen, Id, PackRef, Sha256

__all__ = [
    "PORT_VERSION", "VOCABULARY", "CERTAINTIES", "MAX_OUTPUT_TEXT_BYTES", "MAX_REFUSAL_DETAIL_CHARS", "REFUSAL_REASONS", "CLAIM_ID_PATTERN", "TEXT_PATTERN",
    "CONTRACT_FILES", "SourceClaim", "SourceReport", "InputIds", "CombinatorInput", "SynthClaim", "EvidenceRef", "Dropped",
    "Conflict", "CombinatorOutput", "CombinatorIdentity", "CombinatorHello", "CombinatorRefusal", "check_input",
    "check_output", "check_hello", "check_refusal", "to_synthesis_format", "synthesis_payload", "source_report",
    "build_input", "vocabulary_document", "port_rules_document", "contract_documents", "contract_digest",
]

PORT_VERSION = "1.0"
#: The transformations a combinator may give a synthesized claim: ``integrity.contracts.SYNTHESIZED_CLAIM_TRANSFORMATIONS``
#: restated (every documented value except ``new``, content no source asserts, and ``dropped``, a ledger entry), pinned
#: to it by ``tests/integration/test_combinator_port.py`` so the port and the hub's contract cannot drift apart.
VOCABULARY: tuple[str, ...] = ("carried", "paraphrased", "merged", "narrowed", "generalized")
CERTAINTIES: tuple[str, ...] = ("possible", "probable", "established")
MAX_OUTPUT_TEXT_BYTES = 49152
MAX_REFUSAL_DETAIL_CHARS = 300
#: Why a combinator produced no output in contract, each with the one ``KIT-CB`` code it carries. ``KIT-CB-002`` covers
#: every case where no output in contract exists: malformed, not JSON, or none at all (no provider, a provider that
#: failed or gave no text, an internal error of the combinator).
REFUSAL_REASONS: Mapping[str, str] = MappingProxyType({
    "input_not_json": "KIT-CB-001",
    "input_invalid": "KIT-CB-001",
    "pack_mismatch": "KIT-CB-005",
    "provider_unavailable": "KIT-CB-002",
    "provider_failed": "KIT-CB-002",
    "provider_no_text": "KIT-CB-002",
    "output_not_json": "KIT-CB-002",
    "output_not_object": "KIT-CB-002",
    "output_invalid": "KIT-CB-002",
    "transformation_unknown": "KIT-CB-003",
    "source_claim_unknown": "KIT-CB-004",
    "output_too_large": "KIT-CB-006",
    "internal_error": "KIT-CB-002",
})
#: The refusal reasons that come before the input was read: their refusal names no request (``ids`` null). An internal
#: error may come before or after it (``ids`` null or the request's); every other refusal names the request it refuses.
_UNREAD_INPUT_REASONS = frozenset({"input_not_json", "input_invalid"})
_IDS_OPTIONAL_REASONS = frozenset({"internal_error"})
#: The published contract a combinator is built against, by file name (``integration/schemas/``), in this order: the
#: JSON Schemas of the four messages, the synthesis contract's closed vocabularies and the port's own rules.
CONTRACT_FILES: tuple[str, ...] = (
    "combinator-input.v1.schema.json", "combinator-output.v1.schema.json", "combinator-hello.v1.schema.json",
    "combinator-refusal.v1.schema.json", "synthesis-vocabulary.v1.json", "combinator-port.v1.json",
)

_Transformation = Literal["carried", "paraphrased", "merged", "narrowed", "generalized"]
_Certainty = Literal["possible", "probable", "established"]
#: What a combinator's own text may hold (a synthesized claim's text, a dropped entry's reason, a conflict's description):
#: at least one visible character, and no control character other than a tab or a line break and no bidirectional embedding,
#: override or isolate (which would let the text a reader sees differ from the text the hub checks). The classes are written
#: out, never ``\s``, so the translator's models (pydantic, Rust regular expressions) and the combinator's validator (Python)
#: read the pattern alike.
_SPACE_CLASS = r"\t\n\r \u00a0\u1680\u2000-\u200d\u2028\u2029\u202f\u205f\u2060\u3000\ufeff"
_FORBIDDEN_CLASS = r"\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069"
TEXT_PATTERN = rf"^[{_SPACE_CLASS}]*[^{_FORBIDDEN_CLASS}{_SPACE_CLASS}][^{_FORBIDDEN_CLASS}]*$"
_Text = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
#: A synthesized claim's text: the combinator's own words, held to :data:`TEXT_PATTERN` (a source claim's text is the delivered
#: report's, held to nothing more than its length: the hub already delivered it).
_OwnText = Annotated[str, StringConstraints(min_length=1, max_length=4000, pattern=TEXT_PATTERN)]
_Reason = Literal["input_not_json", "input_invalid", "pack_mismatch", "provider_unavailable", "provider_failed", "provider_no_text",
                  "output_not_json", "output_not_object", "output_invalid", "transformation_unknown", "source_claim_unknown",
                  "output_too_large", "internal_error"]
_CbCode = Literal["KIT-CB-001", "KIT-CB-002", "KIT-CB-003", "KIT-CB-004", "KIT-CB-005", "KIT-CB-006"]
_NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
#: A claim id as the hub's branch parsers write it: the protocol's id alphabet and ``@`` (the generic parser's
#: ``g4.2@economics-specialist``), so every delivered claim can be carried, cited, dropped or named in a conflict.
CLAIM_ID_PATTERN = r"^[A-Za-z0-9._:@-]{1,128}$"
ClaimId = Annotated[str, StringConstraints(pattern=CLAIM_ID_PATTERN)]
_VERSION_PATTERN = r"^[0-9]{1,4}(?:\.[0-9]{1,4}){0,3}$"


class SourceClaim(Frozen):
    claim_id: ClaimId
    role: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{0,63}$")]
    materiality: Literal["material", "supporting"]
    certainty: _Certainty
    claim_text_sha256: Sha256
    text: _Text


class SourceReport(Frozen):
    report_id: Id
    agent_id: Id
    subject: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    branch: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{0,63}$")]
    claims: list[SourceClaim] = Field(min_length=1, max_length=512)


class InputIds(Frozen):
    task_id: Id
    request_id: Id


class CombinatorInput(Frozen):
    schema_: Literal["epinoic.integration.combinator-input.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.0"]
    ids: InputIds
    sources: list[SourceReport] = Field(min_length=2, max_length=16)
    vocabulary: list[_Transformation] = Field(min_length=5, max_length=5)
    instruction_pack: PackRef

    model_config = Frozen.model_config | {"populate_by_name": True}


class EvidenceRef(Frozen):
    document_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    locator: Optional[Annotated[str, StringConstraints(max_length=200)]] = None
    excerpt: Optional[Annotated[str, StringConstraints(max_length=2000)]] = None


class SynthClaim(Frozen):
    """A synthesized claim: its text, the source claims it was made from (each cited once: a claim citing one source twice
    would pass for a 'merged' claim with one source), its certainty and its one transformation word."""
    text: _OwnText
    source_claim_ids: list[ClaimId] = Field(min_length=1, max_length=64)
    certainty: _Certainty
    transformation: _Transformation
    evidence_refs: Optional[list[EvidenceRef]] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _distinct(self) -> "SynthClaim":
        if len(set(self.source_claim_ids)) != len(self.source_claim_ids):
            raise ValueError("a synthesized claim cites each source claim once")
        return self


class Dropped(Frozen):
    source_claim_ids: list[ClaimId] = Field(min_length=1, max_length=64)
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1000, pattern=TEXT_PATTERN)]


class Conflict(Frozen):
    """A contradiction between source claims the combinator discloses instead of reconciling it: the hub requires every
    formal contradiction among the claims in scope to be disclosed (``INT-CONFLICT-002``). The service relays it as an
    ``unresolved`` conflict record: a combinator never resolves a contradiction."""
    claim_ids: list[ClaimId] = Field(min_length=2, max_length=64)
    description: Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=TEXT_PATTERN)]

    @model_validator(mode="after")
    def _distinct(self) -> "Conflict":
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("a conflict names each source claim once (two distinct claims at least)")
        return self


class CombinatorOutput(Frozen):
    schema_: Literal["epinoic.integration.combinator-output.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.0"]
    ids: InputIds
    instruction_pack_sha256: Sha256
    claims: list[SynthClaim] = Field(min_length=1, max_length=512)
    dropped: list[Dropped] = Field(default_factory=list, max_length=512)
    conflicts: list[Conflict] = Field(default_factory=list, max_length=64)

    model_config = Frozen.model_config | {"populate_by_name": True}


class CombinatorIdentity(Frozen):
    name: Annotated[str, StringConstraints(pattern=_NAME_PATTERN)]
    version: Annotated[str, StringConstraints(pattern=_VERSION_PATTERN)]


class CombinatorHello(Frozen):
    """What a combinator says about itself when it is attached: its release, the instruction pack it runs (pinned by
    digest), the digest of the published contract it validates its output against, its tier and its vocabulary."""
    schema_: Literal["epinoic.integration.combinator-hello.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.0"]
    combinator: CombinatorIdentity
    instruction_pack: PackRef
    contract_sha256: Sha256
    tier: Literal["cheapest"]
    vocabulary: list[_Transformation] = Field(min_length=5, max_length=5)

    model_config = Frozen.model_config | {"populate_by_name": True}


class CombinatorRefusal(Frozen):
    """A combinator's named refusal: no output in contract left the sub-agent. ``detail`` names positions, rules and
    lengths, never the agent's prose."""
    schema_: Literal["epinoic.integration.combinator-refusal.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.0"]
    ids: Optional[InputIds] = None
    instruction_pack_sha256: Sha256
    code: _CbCode
    reason: _Reason
    detail: Annotated[str, StringConstraints(min_length=1, max_length=MAX_REFUSAL_DETAIL_CHARS)]

    model_config = Frozen.model_config | {"populate_by_name": True}

    @model_validator(mode="after")
    def _code_of_reason(self) -> "CombinatorRefusal":
        if REFUSAL_REASONS[self.reason] != self.code:
            raise ValueError("the refusal's code is not the code of its reason")
        if self.reason not in _IDS_OPTIONAL_REASONS and (self.ids is None) != (self.reason in _UNREAD_INPUT_REASONS):
            raise ValueError("a refusal names the request it refuses unless the input could not be read")
        return self


def _data(raw: Any, code: str) -> dict:
    """The message as a protocol JSON object (``code`` otherwise). An object passed already parsed is held to the same rules
    as text (``canonical.check_value``: no lone surrogate, no float, no non-string key), before any other rule reads it,
    the order the combinator's own contract check follows."""
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            raw = loads_strict(raw)
        except CanonicalError as exc:
            raise IntegrationError(code, f"not protocol JSON: {exc}") from None
    else:
        try:
            check_value(raw)
        except CanonicalError as exc:
            raise IntegrationError(code, f"not protocol JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise IntegrationError(code, "a combinator-port message is a JSON object")
    return raw


def check_input(raw: Any) -> CombinatorInput:
    data = _data(raw, "KIT-CB-001")
    try:
        inp = CombinatorInput.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError("KIT-CB-001", f"the input does not validate ({exc.error_count()} error(s))") from None
    if tuple(inp.vocabulary) != VOCABULARY:
        raise IntegrationError("KIT-CB-001", "the input's vocabulary is not the closed transformation vocabulary")
    ids = [c.claim_id for s in inp.sources for c in s.claims]
    if len(set(ids)) != len(ids):
        raise IntegrationError("KIT-CB-001", "two source claims share a claim id")
    for s in inp.sources:
        for c in s.claims:
            if sha256_text(c.text) != c.claim_text_sha256:
                raise IntegrationError("KIT-CB-001", "a source claim's digest is not the digest of its text")
    return inp


def check_output(raw: Any, inp: CombinatorInput) -> CombinatorOutput:
    """Validate the combinator's output against its input. ``KIT-CB-003`` for a transformation outside the vocabulary
    (the hub would refuse it with INT-SYNTH-014), ``KIT-CB-004`` for a citation (a synthesized claim's, a dropped entry's
    or a disclosed conflict's) of a claim the input does not hold, ``KIT-CB-005`` for another instruction pack,
    ``KIT-CB-006`` for an oversized synthesis, ``KIT-CB-002`` otherwise."""
    data = _data(raw, "KIT-CB-002")
    claims = data.get("claims")
    if isinstance(claims, list):
        for c in claims:
            if isinstance(c, dict) and "transformation" in c and c["transformation"] not in VOCABULARY:
                raise IntegrationError("KIT-CB-003", "a synthesized claim's transformation is outside the closed vocabulary")
    try:
        out = CombinatorOutput.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError("KIT-CB-002", f"the output does not validate ({exc.error_count()} error(s))") from None
    if out.ids != inp.ids:
        raise IntegrationError("KIT-CB-002", "the output answers another request")
    if out.instruction_pack_sha256 != inp.instruction_pack.sha256:
        raise IntegrationError("KIT-CB-005", "the output was written under another instruction pack")
    known = {c.claim_id for s in inp.sources for c in s.claims}
    cited = ({cid for c in out.claims for cid in c.source_claim_ids} | {cid for d in out.dropped for cid in d.source_claim_ids}
             | {cid for k in out.conflicts for cid in k.claim_ids})
    if not cited <= known:
        raise IntegrationError("KIT-CB-004", "the synthesis cites a claim the input does not hold")
    if sum(len(c.text.encode("utf-8")) for c in out.claims) > MAX_OUTPUT_TEXT_BYTES:
        raise IntegrationError("KIT-CB-006", f"the synthesis text exceeds {MAX_OUTPUT_TEXT_BYTES} UTF-8 bytes")
    return out


def _names_a_model(value: str) -> bool:
    from .router_port import MODEL_FAMILIES
    return re.search(r"(?i)(?:^|[^a-z0-9])(?:" + "|".join(MODEL_FAMILIES) + r")(?:[^a-z]|$)", value) is not None


def check_hello(raw: Any, *, contract_sha256: Optional[str] = None) -> CombinatorHello:
    """Validate a combinator's hello (``KIT-CB-002`` when it is out of contract: a combinator message the service cannot
    read). With ``contract_sha256`` (the service's :func:`contract_digest`), a combinator that validates against another
    contract is refused the same way: its outputs would be checked against rules this service does not publish."""
    data = _data(raw, "KIT-CB-002")
    try:
        hello = CombinatorHello.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError("KIT-CB-002", f"the combinator's hello does not validate ({exc.error_count()} error(s))") from None
    if tuple(hello.vocabulary) != VOCABULARY:
        raise IntegrationError("KIT-CB-002", "the combinator's vocabulary is not the closed transformation vocabulary")
    if _names_a_model(hello.combinator.name) or _names_a_model(hello.instruction_pack.name):
        raise IntegrationError("KIT-CB-002", "a combinator's hello never names a model (decision D23)")
    if contract_sha256 is not None and hello.contract_sha256 != contract_sha256:
        raise IntegrationError("KIT-CB-002", "the combinator validates against another version of the published contract")
    return hello


def check_refusal(raw: Any, inp: Optional[CombinatorInput] = None) -> CombinatorRefusal:
    """Validate a combinator's refusal (``KIT-CB-002`` when it is out of contract). With the input it refuses, the refusal
    must name that request (or none, for an input it could not read)."""
    data = _data(raw, "KIT-CB-002")
    try:
        ref = CombinatorRefusal.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError("KIT-CB-002", f"the combinator's refusal does not validate ({exc.error_count()} error(s))") from None
    if inp is not None and ref.ids is not None and ref.ids != inp.ids:
        raise IntegrationError("KIT-CB-002", "the refusal answers another request")
    return ref


def to_synthesis_format(out: CombinatorOutput) -> dict:
    """The arena's ``syntheses/*.json`` body the hub relays (``run_arena.group_synthesis`` reads the same shape)."""
    claims = []
    for c in out.claims:
        item: dict[str, Any] = {"text": c.text, "source_claim_ids": list(c.source_claim_ids), "certainty": c.certainty, "transformation": c.transformation}
        if c.evidence_refs is not None:
            item["evidence_refs"] = [r.model_dump(exclude_none=True) for r in c.evidence_refs]
        claims.append(item)
    body: dict[str, Any] = {"claims": claims, "dropped": [{"source_claim_ids": list(d.source_claim_ids), "reason": d.reason} for d in out.dropped]}
    if out.conflicts:
        body["conflicts"] = [{"claim_ids": list(k.claim_ids), "description": k.description} for k in out.conflicts]
    return body


def synthesis_payload(out: CombinatorOutput, inp: CombinatorInput, *, synthesis_id: str, combinator_agent_id: str, created_at: str,
                      evidence_refs: Optional[Mapping[int, Sequence[Mapping[str, Any]]]] = None) -> dict:
    """The ``synthesis/1.0`` mapping the service relays through the hub for a checked output (``check_output``): the
    hub's contract validation and every ledger, conflict and entailment check then decide it as untrusted data.

    Synthesized claims are numbered ``s0``, ``s1``, ... (with a longer prefix should the input hold such a claim id, so a
    synthesized claim never reuses a source claim's id, INT-LEDGER-015); every material synthesized claim keeps the
    default materiality ``material``; a dropped entry is a ledger entry ``dropped``; a disclosed conflict is an
    ``unresolved`` conflict record; the student-facing text is the claims' texts joined by a space. ``evidence_refs``
    (synthesized claim index -> references) are the references the service attaches (phase 2: the arena's rule, the
    references of cited material sources whose excerpts the claim reproduces word for word); without them a claim keeps
    the references the combinator gave, if any."""
    known = {c.claim_id for s in inp.sources for c in s.claims}
    prefix = "s"
    while any(f"{prefix}{i}" in known for i in range(len(out.claims))):
        prefix += "s"
    claims: list[dict[str, Any]] = []
    for i, c in enumerate(out.claims):
        item: dict[str, Any] = {"claim_id": f"{prefix}{i}", "text": c.text, "source_claim_ids": list(c.source_claim_ids),
                                "certainty": c.certainty, "transformation": c.transformation}
        refs = (evidence_refs or {}).get(i)
        if refs is not None:
            item["evidence_refs"] = [dict(r) for r in refs]
        elif c.evidence_refs is not None:
            item["evidence_refs"] = [r.model_dump(exclude_none=True) for r in c.evidence_refs]
        claims.append(item)
    text = " ".join(c.text for c in out.claims)
    return {
        "synthesis_id": synthesis_id, "request_id": inp.ids.request_id, "task_id": inp.ids.task_id,
        "combinator_agent_id": combinator_agent_id, "source_report_ids": [s.report_id for s in inp.sources], "claims": claims,
        "ledger": [{"source_claim_ids": list(d.source_claim_ids), "transformation": "dropped", "reason": d.reason} for d in out.dropped],
        "conflicts": [{"conflict_id": f"k{i}", "claim_ids": list(k.claim_ids), "description": k.description, "status": "unresolved"}
                      for i, k in enumerate(out.conflicts)],
        "text": text, "text_sha256": sha256_text(text), "created_at": created_at,
    }


def source_report(payload: Mapping[str, Any], branch: str) -> dict:
    """One source of a combinator input from a delivered report's payload (``specialist_report/1.0`` as JSON): its report
    id, agent, subject and every claim with its role, materiality, certainty, text and the digest of that text."""
    return {"report_id": payload["report_id"], "agent_id": payload["agent_id"], "subject": payload["subject"], "branch": branch,
            "claims": [{"claim_id": c["claim_id"], "role": c["claim_role"], "materiality": c["materiality"], "certainty": c["certainty"],
                        "claim_text_sha256": sha256_text(c["claim_text"]), "text": c["claim_text"]} for c in payload["claims"]]}


def build_input(ids: Mapping[str, str], sources: Sequence[Mapping[str, Any]], instruction_pack: Mapping[str, str]) -> CombinatorInput:
    """A checked combinator input (``KIT-CB-001`` when it is out of contract)."""
    return check_input({"schema": "epinoic.integration.combinator-input.v1", "protocol": "epinoic.integration.v1", "port_version": PORT_VERSION,
                        "ids": dict(ids), "sources": [dict(s) for s in sources], "vocabulary": list(VOCABULARY), "instruction_pack": dict(instruction_pack)})


def vocabulary_document() -> dict:
    """The synthesis contract's closed vocabularies as data (``integration/schemas/synthesis-vocabulary.v1.json``), built
    from ``integrity.contracts`` (imported here only: it reaches the engine): every transformation with what it records,
    the ones a combinator gives a synthesized claim, the certainty order (strongest first) and rank, the materiality and
    a conflict record's status."""
    from typing import get_args

    from ..integrity.contracts import CERTAINTY_RANK, SYNTHESIZED_CLAIM_TRANSFORMATIONS, TRANSFORMATION_MEANINGS, ConflictRecord, SynthesizedClaim
    return {
        "schema": "epinoic.integration.synthesis-vocabulary.v1", "protocol": "epinoic.integration.v1", "synthesis_contract": "synthesis/1.0",
        "source": "src/epinoic_logic/integrity/contracts.py",
        "transformations": dict(TRANSFORMATION_MEANINGS),
        "synthesized_claim_transformations": list(SYNTHESIZED_CLAIM_TRANSFORMATIONS),
        "certainty": sorted(CERTAINTY_RANK, key=CERTAINTY_RANK.get, reverse=True),
        "certainty_rank": dict(CERTAINTY_RANK),
        "materiality": list(get_args(SynthesizedClaim.model_fields["materiality"].annotation)),
        "conflict_status": list(get_args(ConflictRecord.model_fields["status"].annotation)),
    }


def port_rules_document() -> dict:
    """The rules of this port that its schemas cannot state, as data (``integration/schemas/combinator-port.v1.json``): the
    refusal reasons with their codes, the reasons that come before the input was read (their refusal names no request),
    the largest synthesis text and refusal detail, and the order in which ``check_output`` decides."""
    return {
        "schema": "epinoic.integration.combinator-port-rules.v1", "protocol": "epinoic.integration.v1", "port_version": PORT_VERSION,
        "refusal_reasons": dict(REFUSAL_REASONS), "unread_input_reasons": sorted(_UNREAD_INPUT_REASONS),
        "ids_optional_reasons": sorted(_IDS_OPTIONAL_REASONS),
        "max_output_text_bytes": MAX_OUTPUT_TEXT_BYTES, "max_refusal_detail_chars": MAX_REFUSAL_DETAIL_CHARS,
        "output_check_order": ["not protocol JSON (text that does not parse strictly, or an object passed already parsed that holds a lone surrogate, "
                               "a float, a non-string key or a value that is not JSON) or not a JSON object: KIT-CB-002",
                               "a synthesized claim's transformation outside the vocabulary: KIT-CB-003",
                               "the schema (a synthesized claim's text, a dropped entry's reason or a conflict's description without a visible "
                               "character, or holding a control character other than a tab or a line break or a bidirectional embedding, override "
                               "or isolate, included), a synthesized claim citing a source claim twice and a conflict naming a claim twice: KIT-CB-002",
                               "another request: KIT-CB-002",
                               "another instruction pack: KIT-CB-005", "a citation the input does not hold: KIT-CB-004",
                               f"a synthesis text over {MAX_OUTPUT_TEXT_BYTES} UTF-8 bytes: KIT-CB-006"],
    }


def contract_documents() -> dict[str, dict]:
    """The published contract by file name (:data:`CONTRACT_FILES`): the JSON Schemas of the four messages, the
    vocabulary document and the port's rules, as the kit's generator writes them."""
    models = {"combinator-input.v1.schema.json": CombinatorInput, "combinator-output.v1.schema.json": CombinatorOutput,
              "combinator-hello.v1.schema.json": CombinatorHello, "combinator-refusal.v1.schema.json": CombinatorRefusal}
    docs: dict[str, dict] = {name: model.model_json_schema(by_alias=True) for name, model in models.items()}
    docs["synthesis-vocabulary.v1.json"] = vocabulary_document()
    docs["combinator-port.v1.json"] = port_rules_document()
    return {name: docs[name] for name in CONTRACT_FILES}


def contract_digest(documents: Optional[Mapping[str, Any]] = None) -> str:
    """SHA-256 of the canonical JSON of the published contract (file name -> document): the ``contract_sha256`` a
    combinator's hello reports for the copy it validates against."""
    return sha256_json(dict(documents if documents is not None else contract_documents()))
