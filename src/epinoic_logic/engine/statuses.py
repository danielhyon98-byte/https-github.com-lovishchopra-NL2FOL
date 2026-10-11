"""Closed verification status taxonomy.

Only DEFINITIVE statuses carry a solver verdict about the encoded problem. None of
them means the natural-language claim is true. Everything else is a non-result and
must never be displayed as "verified".
"""
from __future__ import annotations

from enum import Enum


class VerificationStatus(str, Enum):
    # Definitive solver verdicts about the ENCODED problem
    ENTAILED = "ENTAILED"                            # premises consistent; premises AND NOT conclusion unsat
    COUNTEREXAMPLE = "COUNTEREXAMPLE"                # premises consistent; premises AND NOT conclusion sat (model given)
    INCONSISTENT_PREMISES = "INCONSISTENT_PREMISES"  # premises alone unsat (core given)
    CONSISTENT = "CONSISTENT"                        # consistency query: premises sat
    SATISFIABLE = "SATISFIABLE"                      # satisfiability query: sat (model given)
    UNSATISFIABLE = "UNSATISFIABLE"                  # satisfiability query: unsat
    # Non-results from the solver
    UNKNOWN = "UNKNOWN"                              # solver gave up (incomplete theory, memout, ...)
    TIMEOUT = "TIMEOUT"                              # solver hit the time or resource limit
    # Non-results from validation / policy
    UNSUPPORTED = "UNSUPPORTED"                      # construct outside the allowlist or policy
    INVALID_FORMALIZATION = "INVALID_FORMALIZATION"  # schema, sort, identifier or limit violation
    # Non-results from the translation layer (never produced by the engine itself)
    AMBIGUOUS_TRANSLATION = "AMBIGUOUS_TRANSLATION"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    # Failure
    INTERNAL_ERROR = "INTERNAL_ERROR"


DEFINITIVE: frozenset[VerificationStatus] = frozenset({
    VerificationStatus.ENTAILED,
    VerificationStatus.COUNTEREXAMPLE,
    VerificationStatus.INCONSISTENT_PREMISES,
    VerificationStatus.CONSISTENT,
    VerificationStatus.SATISFIABLE,
    VerificationStatus.UNSATISFIABLE,
})

ENGINE_PRODUCIBLE: frozenset[VerificationStatus] = DEFINITIVE | frozenset({
    VerificationStatus.UNKNOWN,
    VerificationStatus.TIMEOUT,
    VerificationStatus.UNSUPPORTED,
    VerificationStatus.INVALID_FORMALIZATION,
    VerificationStatus.INTERNAL_ERROR,
})


def is_definitive(status: VerificationStatus) -> bool:
    return status in DEFINITIVE


SCOPE_STATEMENT = (
    "This result concerns only the formal encoding it is bound to, under the encoded "
    "premises and the stated solver configuration. It does not establish that the "
    "premises are factually true, that the natural-language claim was translated "
    "faithfully, or that any interpretive judgement is correct. Grounding and "
    "semantic-fidelity information is reported separately and is advisory."
)
