"""Result models. A result is bound to the exact problem, solver configuration and
component versions that produced it (``Binding``). Any change to any of them yields
a different binding digest, so an old result can never be presented as covering a
modified representation.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ..ir.schema import QueryKind, Sort
from .statuses import SCOPE_STATEMENT, VerificationStatus


class SolverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    timeout_ms: int = Field(default=2000, ge=1, le=120_000)
    rlimit: Optional[int] = Field(default=None, ge=1, description="Z3 resource limit for deterministic cutoffs")
    random_seed: int = Field(default=0, ge=0)
    memory_max_mb: Optional[int] = Field(default=512, ge=16)
    model_completion: bool = True
    produce_unsat_core: bool = True
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
    model_config = ConfigDict(extra="forbid", frozen=True)
    ir_version: str
    engine_version: str
    policy_version: str
    z3_version: str


class Binding(BaseModel):
    """Digests tying a result to exactly what produced it."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    problem_digest: str
    config_digest: str
    versions_digest: str
    binding_digest: str = Field(description="sha256 over problem_digest|config_digest|versions_digest")
    smt2: Optional[str] = Field(default=None, description="exact SMT-LIB 2 text of the compiled assertions, for audit")


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
    query: QueryKind
    status: VerificationStatus
    scope_statement: str = SCOPE_STATEMENT
    binding: Binding
    versions: Versions
    solver_config: SolverConfig
    counterexample: Optional[Counterexample] = None
    unsat_core: Optional[UnsatCore] = None
    premises_relied_on: list[str] = Field(
        default_factory=list,
        description="premise ids in the unsat core: for ENTAILED the premises the proof used; for INCONSISTENT_PREMISES the conflicting set",
    )
    ungrounded_dependencies: list[str] = Field(
        default_factory=list,
        description="relied-on premise ids whose grounding is 'assumption' or 'specialist_inference', or whose grounding.verified is False",
    )
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    timings: list[StageTiming] = Field(default_factory=list)
    reason_unknown: Optional[str] = None
    issued_at: str = Field(description="RFC 3339 UTC timestamp")
    signature: Optional[str] = Field(default=None, description="HMAC-SHA256 hex over the canonical result without signature fields; set by the service")
    signature_key_id: Optional[str] = None
