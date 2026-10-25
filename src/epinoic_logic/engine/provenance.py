"""Provenance: version and identity capture, result binding, result signing, and the
current-policy staleness rule.

A result is bound to (problem, solver configuration, component versions with the build,
schema and policy identity, effective validation limits) by digests. Changing any label,
note, premise, limit, timeout, version or engine source changes the binding digest, so a
stored result can never be presented as covering a modified representation or as decided
under the current policy when it was not. Results are signed with HMAC-SHA256 so the Overseer
can reject anything a specialist agent (or anyone else) fabricates.

Signing proves who issued a result, not that it is current: a result from an earlier release
keeps a valid signature (it stays inspectable as a historical record), and
:func:`stale_reasons` says why it cannot stand as current-policy evidence until the problem is
verified again.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Optional

import z3

from ..ir.canonical import canonical_json, problem_digest, sha256_hex
from ..ir.schema import DEFAULT_LIMITS, Limits, Problem
from ..version import ENGINE_VERSION, IR_VERSION, POLICY_VERSION
from .identity import build_id, policy_id, schema_id
from .results import Binding, SolverConfig, VerificationResult, Versions

SIGNATURE_FIELDS = ("signature", "signature_key_id")
#: Identity fields of :class:`Versions`; a result without them predates identity binding.
IDENTITY_FIELDS = ("build_id", "schema_id", "policy_id")


def z3_version() -> str:
    return z3.get_version_string()


def compute_versions() -> Versions:
    return Versions(ir_version=IR_VERSION, engine_version=ENGINE_VERSION, policy_version=POLICY_VERSION, z3_version=z3_version(),
                    build_id=build_id(), schema_id=schema_id(), policy_id=policy_id())


def config_digest(config: SolverConfig) -> str:
    return sha256_hex(canonical_json(config))


def versions_digest(versions: Versions) -> str:
    return sha256_hex(canonical_json(versions))


def limits_digest(limits: Optional[Limits]) -> Optional[str]:
    """The digest a binding carries for ``limits``: ``None`` for the default limits of this policy (and for ``None``),
    else SHA-256 over the canonical JSON of every limit value."""
    if limits is None:
        return None
    values = {name: getattr(limits, name) for name in Limits.model_fields}
    if values == DEFAULT_LIMITS.model_dump():
        return None
    return sha256_hex(canonical_json(values))


def binding_digest_of(problem_d: str, config_d: str, versions_d: str, limits_d: Optional[str] = None) -> str:
    """``sha256(problem|config|versions)``, with ``|limits`` appended when the limits are not the default ones."""
    parts = (problem_d, config_d, versions_d) if limits_d is None else (problem_d, config_d, versions_d, limits_d)
    return sha256_hex("|".join(parts))


def compute_binding(problem: Problem, config: SolverConfig, versions: Versions, smt2: str | None, limits: Optional[Limits] = None) -> Binding:
    pd = problem_digest(problem)
    cd = config_digest(config)
    vd = versions_digest(versions)
    ld = limits_digest(limits)
    return Binding(problem_digest=pd, config_digest=cd, versions_digest=vd, binding_digest=binding_digest_of(pd, cd, vd, ld), smt2=smt2, limits_digest=ld)


def binding_for_unparsed(raw_digest: str, config: SolverConfig, versions: Versions, limits: Optional[Limits] = None) -> Binding:
    """Binding for a payload that never became a Problem: the problem digest is the
    digest of the raw bytes, so even a rejection is tied to exactly what was sent."""
    cd = config_digest(config)
    vd = versions_digest(versions)
    ld = limits_digest(limits)
    return Binding(problem_digest=raw_digest, config_digest=cd, versions_digest=vd, binding_digest=binding_digest_of(raw_digest, cd, vd, ld), smt2=None, limits_digest=ld)


def predates_identity(result: VerificationResult) -> bool:
    """True for a result issued before results bound a build, schema and policy identity (and their limits)."""
    return all(getattr(result.versions, k) is None for k in IDENTITY_FIELDS)


def bound_limits_digest(result: VerificationResult) -> Optional[str]:
    """The limits digest a result stands for: its binding's, or, for a result issued before limits were bound, the
    digest of its limits record (``None``: the default limits of the policy it was issued under)."""
    if result.binding.limits_digest is not None or not predates_identity(result):
        return result.binding.limits_digest
    return limits_digest(result.limits)


def binding_inconsistencies(result: VerificationResult) -> list[str]:
    """Where a result's binding disagrees with the fields it binds (empty when it is internally consistent).

    A result issued before limits were bound carries a limits record with no limits digest; that is its release's
    shape, not an inconsistency (:func:`stale_reasons` names it instead)."""
    b = result.binding
    out: list[str] = []
    if b.binding_digest != binding_digest_of(b.problem_digest, b.config_digest, b.versions_digest, b.limits_digest):
        out.append("binding_digest != sha256(problem_digest|config_digest|versions_digest" + ("|limits_digest)" if b.limits_digest is not None else ")"))
    if config_digest(result.solver_config) != b.config_digest:
        out.append("config_digest != digest(solver_config)")
    if versions_digest(result.versions) != b.versions_digest:
        out.append("versions_digest != digest(versions)")
    if b.limits_digest != limits_digest(result.limits) and not (b.limits_digest is None and predates_identity(result)):
        out.append("limits_digest != digest(limits)")
    return out


def describe_limits(limits: Optional[Limits]) -> str:
    """Short text for a set of limits: ``default`` or the values that differ from the default."""
    if limits is None or limits_digest(limits) is None:
        return "the default limits"
    diff = {k: v for k, v in limits.model_dump().items() if DEFAULT_LIMITS.model_dump().get(k) != v}
    return "limits " + ", ".join(f"{k}={v}" for k, v in sorted(diff.items()))


def stale_reasons(result: VerificationResult, *, required_limits: Optional[Limits] = None, current: Optional[Versions] = None) -> list[str]:
    """Why ``result`` is not current-policy evidence for this build; empty when it is.

    A result is current only when its component versions and its build, schema and policy identity equal the running
    engine's (``current``, default :func:`compute_versions`) and it was decided under the validation limits the
    receiver requires (``required_limits``, default the engine's default limits). Anything else is a historical record:
    its signature may still verify, but the problem must be verified again before the result can support a decision.
    """
    now = current if current is not None else compute_versions()
    out: list[str] = []
    if result.versions != now:
        missing = [k for k in IDENTITY_FIELDS if getattr(result.versions, k) is None]
        differ = [k for k in Versions.model_fields if k not in missing and getattr(result.versions, k) != getattr(now, k)]
        if missing:
            out.append("the result binds no build, schema or policy identity (issued by a release before identities were bound)")
        if differ:
            shown = ", ".join(f"{k} {getattr(result.versions, k)!r} (current {getattr(now, k)!r})" if k not in IDENTITY_FIELDS else k for k in differ)
            out.append(f"the result was produced under other component versions or another build, schema or policy: {shown}")
    required = required_limits if required_limits is not None else DEFAULT_LIMITS
    if bound_limits_digest(result) != limits_digest(required):
        out.append(f"the result was decided under {describe_limits(result.limits)} but the required policy is {describe_limits(required)}")
    return out


def signable_text(result: VerificationResult) -> str:
    data = result.model_dump(mode="json", exclude_none=True)
    for f in SIGNATURE_FIELDS:
        data.pop(f, None)
    return canonical_json(data)


#: An HMAC-SHA256 signature as the engine writes it: 64 lowercase hexadecimal characters.
_SIGNATURE_RE = re.compile(r"[0-9a-f]{64}")


def signature_matches(expected: str, given) -> bool:
    """Constant-time comparison of a computed signature with a given one, total on untrusted input: a value that is not
    64 lowercase hex characters (any other type, another length, a non-ASCII or surrogate character) never matches and
    never raises (``hmac.compare_digest`` refuses non-ASCII text, so both sides are compared as ASCII bytes)."""
    if not isinstance(given, str) or not _SIGNATURE_RE.fullmatch(given) or not isinstance(expected, str) or not expected.isascii():
        return False
    return hmac.compare_digest(expected.encode("ascii"), given.encode("ascii"))


def sign_result(result: VerificationResult, key: bytes, key_id: str) -> VerificationResult:
    if not key:
        raise ValueError("signing key must not be empty")
    mac = hmac.new(key, signable_text(result).encode("utf-8"), hashlib.sha256).hexdigest()
    return result.model_copy(update={"signature": mac, "signature_key_id": key_id})


def verify_signature(result: VerificationResult, key: bytes) -> bool:
    """True exactly when ``result`` carries the signature ``key`` gives its canonical text. Never raises: a forged
    signature of any form is False, and so is a result whose text is not valid Unicode (no result the engine signs holds
    a lone surrogate, so none can carry a genuine signature)."""
    if not result.signature or not key:
        return False
    try:
        text = signable_text(result).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError):
        return False
    expected = hmac.new(key, text, hashlib.sha256).hexdigest()
    return signature_matches(expected, result.signature)
