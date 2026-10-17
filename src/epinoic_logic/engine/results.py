"""Result models. A result is bound to the exact problem, solver configuration, component
versions and build, schema and policy identity that produced it, and to the validation limits it
was decided under (``Binding``). Any change to any of them yields a different binding digest, so
an old result can never be presented as covering a modified representation or a newer policy.

A result decided under non-default ``Limits`` (for example the named ``nonlinear`` pack
policy, see :mod:`.policies`) records them in ``VerificationResult.limits`` and binds their
digest (``Binding.limits_digest``, part of the binding digest). With the default ``Limits`` of
the bound policy both are ``None`` and left out of every dump: the default values are part of
the policy identity in ``Versions.policy_id``. Fields added for the identity and the limits
binding are left out of a dump while ``None``, so a result issued before they existed still
parses, serialises byte-identically and keeps a valid signature: it stays inspectable as a
historical record, but it is not current-policy evidence (``provenance.stale_reasons``).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer


def _drop_none(data: Any, fields: tuple[str, ...]) -> Any:
    """Remove ``fields`` from a dump while their value is ``None`` (fields added after results were first issued)."""
    if isinstance(data, dict):
        for name in fields:
            if name in data and data[name] is None:
                del data[name]
    return data

from ..ir.schema import Limits, QueryKind, Sort
from .statuses import SCOPE_STATEMENT, VerificationStatus


class SolverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    timeout_ms: int = Field(default=2000, ge=1, le=120_000)
    rlimit: Optional[int] = Field(default=None, ge=1, description="Z3 resource limit for deterministic cutoffs")
    random_seed: int = Field(default=0, ge=0)
    memory_max_mb: Optional[int] = Field(
        default=512, ge=128,
        description="Z3 memory budget in MB for ONE verification, never below the engine floor (a lower budget aborts Z3 and corrupts the process). Z3's limit is process-wide, so the engine applies this times the number of verifications running at once and never lowers it while any runs",
    )
    model_completion: bool = True
    produce_unsat_core: bool = Field(
        default=True,
        description=(
            "serialise the raw unsat core record (unsat_core). The engine always computes the core: the dependency "
            "lists, the vacuity check (E108) and the circularity check (E112) rest on it, so this flag never changes them"
        ),
    )
    produce_smt2: bool = True


class ModelAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str
    sort: Sort
    value: str = Field(description="exact textual value: 'true'/'false', integer, or rational a/b")


class Counterexample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    assignments: list[ModelAssignment]
    note: str = (
        "An assignment to the declared symbols under which every premise holds and the "
        "conclusion fails. Values are exact; rationals are written a/b."
    )


class UnsatCore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    premise_ids: list[str]
    includes_negated_conclusion: bool = False


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str
    path: Optional[str] = Field(default=None, description="JSON-pointer-like path into the problem")


class Versions(BaseModel):
    """Component versions and the immutable identity of the build that produced a result (:mod:`.identity`).

    The three identity digests are ``None`` only on results issued before they were bound; such a result is never
    current-policy evidence."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    ir_version: str
    engine_version: str
    policy_version: str
    z3_version: str
    build_id: Optional[str] = Field(default=None, description="sha256 over the decision-relevant source of the engine build")
    schema_id: Optional[str] = Field(default=None, description="sha256 over the JSON Schemas of the problem, limits, configuration and result models")
    policy_id: Optional[str] = Field(default=None, description="sha256 over the engine's decision policy as data (identity.policy_manifest)")

    @model_serializer(mode="wrap")
    def _omit_absent_identity(self, handler: SerializerFunctionWrapHandler) -> Any:
        return _drop_none(handler(self), ("build_id", "schema_id", "policy_id"))


class Binding(BaseModel):
    """Digests tying a result to exactly what produced it."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    problem_digest: str
    config_digest: str
    versions_digest: str
    binding_digest: str = Field(
        description="sha256 over problem_digest|config_digest|versions_digest, with |limits_digest appended when limits_digest is set",
    )
    smt2: Optional[str] = Field(default=None, description="exact SMT-LIB 2 text of the compiled assertions, for audit")
    limits_digest: Optional[str] = Field(
        default=None,
        description=(
            "sha256 over the effective validation Limits when they differ from the default limits of the bound policy "
            "(Versions.policy_id); None when the default limits were used. Part of binding_digest"
        ),
    )

    @model_serializer(mode="wrap")
    def _omit_default_limits_digest(self, handler: SerializerFunctionWrapHandler) -> Any:
        return _drop_none(handler(self), ("limits_digest",))


class StageTiming(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: str
    ms: float


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: str
    request_id: str
    claim_id: str
    problem_id: str
    query: Optional[QueryKind] = Field(default=None, description="None only when the payload could not be parsed into a problem")
    status: VerificationStatus
    scope_statement: str = SCOPE_STATEMENT
    binding: Binding
    versions: Versions
    solver_config: SolverConfig
    counterexample: Optional[Counterexample] = None
    unsat_core: Optional[UnsatCore] = None
    premises_relied_on: list[str] = Field(
        default_factory=list,
        description=(
            "premise ids in the unsat core: for ENTAILED the premises the proof used; for INCONSISTENT_PREMISES and "
            "UNSATISFIABLE the conflicting set. Always computed, whatever solver_config.produce_unsat_core says"
        ),
    )
    ungrounded_dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "relied-on premise ids whose grounding is missing, is 'assumption', 'specialist_inference' or "
            "'general_knowledge', whose grounding.verified is False, or whose quotation grounding was never "
            "positively verified by a deterministic check"
        ),
    )
    unverified_dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "relied-on premise ids (not already ungrounded) whose grounding claims task or source authority that no "
            "deterministic check in this process validated (verified is None), whatever the kind: an unchecked "
            "arithmetic_fact, task_setting or rubric_rule is listed like an unchecked supplied_text"
        ),
    )
    witness_model: Optional[list[ModelAssignment]] = Field(
        default=None,
        description="for CONSISTENT/SATISFIABLE: one assignment under which every premise holds",
    )
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    timings: list[StageTiming] = Field(default_factory=list)
    reason_unknown: Optional[str] = None
    issued_at: str = Field(description="RFC 3339 UTC timestamp")
    signature: Optional[str] = Field(default=None, description="HMAC-SHA256 hex over the canonical result without signature fields; set by the service")
    signature_key_id: Optional[str] = None
    limits: Optional[Limits] = Field(
        default=None,
        description=(
            "the Limits the problem was validated under, recorded only when they differ from the engine "
            "default (for example the 'nonlinear' pack policy); covered by the signature and bound by "
            "binding.limits_digest. Absent from every dump when the default Limits of the bound policy were used"
        ),
    )

    @model_serializer(mode="wrap")
    def _omit_default_limits(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Leave ``limits`` out of every dump while it is ``None``, so a default result serialises
        (and is signed) exactly as before the field existed."""
        data = handler(self)
        if isinstance(data, dict) and "limits" in data and data["limits"] is None:
            del data["limits"]
        return data
