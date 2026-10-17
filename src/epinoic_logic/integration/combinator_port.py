"""The combinator port ``epinoic.integration.combinator-port.v1`` (``integration/PROTOCOL.md`` section 7; combined mode only).

**Input** (:class:`CombinatorInput`): the synthesis format built from the delivered claims, the arena's contract
(``scripts/arena/list_claims.py --json``): per source report, the claim ids, roles, materiality, certainty, texts and
their digests, and the closed transformation vocabulary.

**Output** (:class:`CombinatorOutput`): one synthesis in the arena's ``syntheses/*.json`` format (synthesized claims citing
source claims, each with one transformation of the vocabulary, and the dropped ledger). The port refuses an output out of
contract; the hub then validates the synthesis as untrusted data when it is relayed (``INT-REQ-009`` and
``INT-SYNTH-014`` for a bad vocabulary, ``INT-LEDGER-*`` for the ledger), as it does for every synthesis.

**Implementation.** v1 is a provider call from the service on the cheapest tier, with a versioned instruction pack pinned
by digest; a combinator sub-project may implement the same port later. Neither is on this tree: until one is connected
the handshake reports ``ports.combinator.available = false`` and the checks port omits the mode ``combined``.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import Field, StringConstraints, ValidationError

from .canonical import CanonicalError, loads_strict, sha256_text
from .errors import IntegrationError
from .protocol import Frozen, Id, PackRef, Sha256

__all__ = [
    "PORT_VERSION", "VOCABULARY", "CERTAINTIES", "MAX_OUTPUT_TEXT_BYTES", "SourceClaim", "SourceReport",
    "CombinatorInput", "SynthClaim", "EvidenceRef", "Dropped", "CombinatorOutput", "check_input", "check_output",
    "to_synthesis_format",
]

PORT_VERSION = "1.0"
#: The transformations a combinator may give a synthesized claim: every value of ``integrity.contracts.Transformation``
#: except ``new`` (content no source asserts) and ``dropped`` (a ledger entry, never a present claim).
VOCABULARY: tuple[str, ...] = ("carried", "paraphrased", "merged", "narrowed", "generalized")
CERTAINTIES: tuple[str, ...] = ("possible", "probable", "established")
MAX_OUTPUT_TEXT_BYTES = 49152

_Transformation = Literal["carried", "paraphrased", "merged", "narrowed", "generalized"]
_Certainty = Literal["possible", "probable", "established"]
_Text = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class SourceClaim(Frozen):
    claim_id: Id
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
    text: _Text
    source_claim_ids: list[Id] = Field(min_length=1, max_length=64)
    certainty: _Certainty
    transformation: _Transformation
    evidence_refs: Optional[list[EvidenceRef]] = Field(default=None, max_length=64)


class Dropped(Frozen):
    source_claim_ids: list[Id] = Field(min_length=1, max_length=64)
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1000)]


class CombinatorOutput(Frozen):
    schema_: Literal["epinoic.integration.combinator-output.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.0"]
    ids: InputIds
    instruction_pack_sha256: Sha256
    claims: list[SynthClaim] = Field(min_length=1, max_length=512)
    dropped: list[Dropped] = Field(default_factory=list, max_length=512)

    model_config = Frozen.model_config | {"populate_by_name": True}


def _data(raw: Any, code: str) -> dict:
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            raw = loads_strict(raw)
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
    (the hub would refuse it with INT-SYNTH-014), ``KIT-CB-004`` for a citation of a claim the input does not hold,
    ``KIT-CB-005`` for another instruction pack, ``KIT-CB-006`` for an oversized synthesis, ``KIT-CB-002`` otherwise."""
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
    cited = {cid for c in out.claims for cid in c.source_claim_ids} | {cid for d in out.dropped for cid in d.source_claim_ids}
    if not cited <= known:
        raise IntegrationError("KIT-CB-004", "the synthesis cites a claim the input does not hold")
    if sum(len(c.text.encode("utf-8")) for c in out.claims) > MAX_OUTPUT_TEXT_BYTES:
        raise IntegrationError("KIT-CB-006", f"the synthesis text exceeds {MAX_OUTPUT_TEXT_BYTES} UTF-8 bytes")
    return out


def to_synthesis_format(out: CombinatorOutput) -> dict:
    """The arena's ``syntheses/*.json`` body the hub relays (``run_arena.group_synthesis`` reads the same shape)."""
    claims = []
    for c in out.claims:
        item: dict[str, Any] = {"text": c.text, "source_claim_ids": list(c.source_claim_ids), "certainty": c.certainty, "transformation": c.transformation}
        if c.evidence_refs is not None:
            item["evidence_refs"] = [r.model_dump(exclude_none=True) for r in c.evidence_refs]
        claims.append(item)
    return {"claims": claims, "dropped": [{"source_claim_ids": list(d.source_claim_ids), "reason": d.reason} for d in out.dropped]}
