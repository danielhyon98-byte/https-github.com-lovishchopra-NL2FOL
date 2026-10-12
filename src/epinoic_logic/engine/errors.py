"""Diagnostic codes. Stable strings; add, never rename."""
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
    UNASSERTED_FIGURE = "E110"      # a COUNTEREXAMPLE that only reassigns a figure the problem defines but never asserts
    UNENCODED_REASON = "E111"       # a COUNTEREXAMPLE that only reassigns conclusion symbols no premise mentions
    CIRCULAR_PREMISES = "E112"      # an ENTAILED proof whose premises restate the conclusion (it, or each of its conjuncts)
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
