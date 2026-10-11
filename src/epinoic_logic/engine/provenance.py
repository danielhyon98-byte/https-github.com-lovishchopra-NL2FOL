"""Provenance: version capture, result binding and result signing.

A result is bound to (problem, solver configuration, component versions) by
digests. Changing any label, note, premise, limit, timeout or version changes the
binding digest, so a stored result can never be presented as covering a modified
representation. Results are signed with HMAC-SHA256 so the Overseer can reject
anything a specialist agent (or anyone else) fabricates.
"""
from __future__ import annotations

import hashlib
import hmac

import z3

from ..ir.canonical import canonical_json, problem_digest, sha256_hex
from ..ir.schema import Problem
from ..version import ENGINE_VERSION, IR_VERSION, POLICY_VERSION
from .results import Binding, SolverConfig, VerificationResult, Versions

SIGNATURE_FIELDS = ("signature", "signature_key_id")


def z3_version() -> str:
    return z3.get_version_string()


def compute_versions() -> Versions:
    return Versions(ir_version=IR_VERSION, engine_version=ENGINE_VERSION, policy_version=POLICY_VERSION, z3_version=z3_version())


def config_digest(config: SolverConfig) -> str:
    return sha256_hex(canonical_json(config))


def versions_digest(versions: Versions) -> str:
    return sha256_hex(canonical_json(versions))


def compute_binding(problem: Problem, config: SolverConfig, versions: Versions, smt2: str | None) -> Binding:
    pd = problem_digest(problem)
    cd = config_digest(config)
    vd = versions_digest(versions)
    return Binding(problem_digest=pd, config_digest=cd, versions_digest=vd, binding_digest=sha256_hex("|".join((pd, cd, vd))), smt2=smt2)


def binding_for_unparsed(raw_digest: str, config: SolverConfig, versions: Versions) -> Binding:
    """Binding for a payload that never became a Problem: the problem digest is the
    digest of the raw bytes, so even a rejection is tied to exactly what was sent."""
    cd = config_digest(config)
    vd = versions_digest(versions)
    return Binding(problem_digest=raw_digest, config_digest=cd, versions_digest=vd, binding_digest=sha256_hex("|".join((raw_digest, cd, vd))), smt2=None)


def signable_text(result: VerificationResult) -> str:
    data = result.model_dump(mode="json", exclude_none=True)
    for f in SIGNATURE_FIELDS:
        data.pop(f, None)
    return canonical_json(data)


def sign_result(result: VerificationResult, key: bytes, key_id: str) -> VerificationResult:
    if not key:
        raise ValueError("signing key must not be empty")
    mac = hmac.new(key, signable_text(result).encode("utf-8"), hashlib.sha256).hexdigest()
    return result.model_copy(update={"signature": mac, "signature_key_id": key_id})


def verify_signature(result: VerificationResult, key: bytes) -> bool:
    if not result.signature or not key:
        return False
    expected = hmac.new(key, signable_text(result).encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, result.signature)
