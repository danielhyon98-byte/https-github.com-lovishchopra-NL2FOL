"""Diagnostic codes. Stable strings; add, never rename.

``E`` codes are findings; on a definitive status, the codes in :data:`NO_VERDICT_CODES` mean the status is no verdict
on the claim. ``W`` codes are advisory coverage warnings: the status stands as the verdict on the encoding and the
warning says what the encoding leaves open (:data:`ADVISORY_CODES`).
"""
from __future__ import annotations

from enum import Enum


class DiagnosticCode(str, Enum):
    # INVALID_FORMALIZATION
    SCHEMA_VIOLATION = "E100"
    UNDECLARED_SYMBOL = "E101"
    SORT_MISMATCH = "E102"
    DUPLICATE_IDENTIFIER = "E103"
    BAD_LITERAL = "E104"
    MISSING_CONCLUSION = "E105"
    UNEXPECTED_CONCLUSION = "E106"
    NON_BOOLEAN_ASSERTION = "E107"
    VACUOUS_RESULT = "E108"         # a definitive status that used no premise (tautology / empty problem)
    CLOSED_CONCLUSION = "E109"      # conclusion mentions no declared symbol
    UNASSERTED_FIGURE = "E110"      # a COUNTEREXAMPLE that only reassigns a figure a verified source states and the problem never asserts
    UNENCODED_REASON = "E111"       # a COUNTEREXAMPLE that only reassigns conclusion symbols a verified source states and no premise mentions
    CIRCULAR_PREMISES = "E112"      # an ENTAILED proof whose premises restate the conclusion (it, or each of its conjuncts)
    # Advisory coverage warnings (the definitive status stands as the verdict on the encoding)
    UNASSERTED_FIGURE_ADVISORY = "W110"  # as E110, with no source-linked evidence that a source asserts the figure
    UNENCODED_REASON_ADVISORY = "W111"   # as E111, with no source-linked evidence that a source states the free symbols
    # UNSUPPORTED (policy)
    UNKNOWN_OPERATOR = "E200"
    NONLINEAR_TERM = "E201"
    NONCONSTANT_DIVISOR = "E202"
    ZERO_DIVISOR = "E203"
    QUANTIFIER_UNSUPPORTED = "E204"
    THEORY_UNSUPPORTED = "E205"
    UNSUPPORTED_IR_VERSION = "E206"
    # Limits
    TOO_MANY_SYMBOLS = "E300"
    TOO_MANY_PREMISES = "E301"
    TOO_MANY_NODES = "E302"
    TOO_DEEP = "E303"
    TOO_MANY_ARGS = "E304"
    LITERAL_TOO_LONG = "E305"
    PAYLOAD_TOO_LARGE = "E306"
    # Solver
    SOLVER_TIMEOUT = "E400"
    SOLVER_UNKNOWN = "E401"
    SOLVER_MEMOUT = "E402"
    SOLVER_INTERRUPTED = "E403"
    # Service / binding
    BINDING_MISMATCH = "E500"
    SIGNATURE_INVALID = "E501"
    UNAUTHENTICATED = "E502"
    RATE_LIMITED = "E503"
    CONCURRENCY_LIMITED = "E504"
    SELF_CERTIFICATION_REJECTED = "E505"
    INTERNAL = "E900"


#: On a definitive status these make the status no verdict on the claim: vacuous (E108), an unasserted figure a verified
#: source states (E110), an unencoded reason a verified source states (E111), a circular encoding (E112).
NO_VERDICT_CODES: frozenset[str] = frozenset({
    DiagnosticCode.VACUOUS_RESULT.value, DiagnosticCode.UNASSERTED_FIGURE.value,
    DiagnosticCode.UNENCODED_REASON.value, DiagnosticCode.CIRCULAR_PREMISES.value,
})
#: Advisory coverage warnings: the status stands; they never withhold a verdict.
ADVISORY_CODES: frozenset[str] = frozenset({
    DiagnosticCode.UNASSERTED_FIGURE_ADVISORY.value, DiagnosticCode.UNENCODED_REASON_ADVISORY.value,
})
