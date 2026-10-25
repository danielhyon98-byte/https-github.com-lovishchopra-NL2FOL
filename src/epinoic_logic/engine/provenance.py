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

The signature covers the key id it names (:func:`signable_text` leaves out only ``signature``), so
a result relabelled to another key id no longer verifies, even for a receiver whose key ring maps
several ids to one secret or gives trust by key id. Earlier builds signed without the key id
(:func:`legacy_signable_text`); that form is still accepted, but only for a result this build did
not produce (another build, schema or policy identity, or none), which is never current-policy
evidence: a historical record stays inspectable, and a result of this build can only verify in the
form that binds its key id. That earlier form attests who holds the key, never the key id the result
names (:func:`signature_form` reports it as ``legacy``): a receiver that trusts by key id passes the id
to :func:`verify_signature`, which refuses the earlier form, and the release rule and the service name
the id as not attested (repair round 3, INV-6).

:func:`verify_signature` never raises: a signature that is not 64 lower-case hex digits (the only
form :func:`sign_result` issues), a key that is not bytes, or a result that cannot be serialised is
simply not a valid signature, and the digests are compared as bytes in constant time.
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

#: Fields the signature does not cover: the signature itself. ``signature_key_id`` is covered.
SIGNATURE_FIELDS = ("signature",)
#: Fields the signature of an earlier build did not cover (:func:`legacy_signable_text`).
LEGACY_SIGNATURE_FIELDS = ("signature", "signature_key_id")
#: The only form a signature takes: HMAC-SHA256 as 64 lower-case hex digits.
_SIGNATURE_RE = re.compile(r"[0-9a-f]{64}")
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


def _text_without(result: VerificationResult, fields: tuple[str, ...]) -> str:
    data = result.model_dump(mode="json", exclude_none=True)
    for f in fields:
        data.pop(f, None)
    return canonical_json(data)


def signable_text(result: VerificationResult) -> str:
    """The canonical text the signature covers: the result without its ``signature``, its key id included."""
    return _text_without(result, SIGNATURE_FIELDS)


def legacy_signable_text(result: VerificationResult) -> str:
    """The text an earlier build signed: the result without its signature and without its key id. Read only to keep a
    result this build did not produce inspectable (:func:`verify_signature`)."""
    return _text_without(result, LEGACY_SIGNATURE_FIELDS)


def _mac(key: bytes, text: str) -> str:
    # A lone surrogate (only a result built around validation can hold one) is encoded, never raised on.
    return hmac.new(key, text.encode("utf-8", errors="surrogatepass"), hashlib.sha256).hexdigest()


def mac_matches(expected: str, presented: object) -> bool:
    """Constant-time comparison of a computed HMAC-SHA256 hex digest with a presented one, as bytes. Anything that is not
    64 lower-case hex digits (a non-ASCII or overlong text, a value of another type) is no signature: ``False``, never an
    exception (``hmac.compare_digest`` raises on two text values holding non-ASCII characters)."""
    if not isinstance(presented, str) or _SIGNATURE_RE.fullmatch(presented) is None:
        return False
    return hmac.compare_digest(expected.encode("ascii"), presented.encode("ascii"))


def sign_result(result: VerificationResult, key: bytes, key_id: str) -> VerificationResult:
    """``result`` signed with ``key`` under ``key_id``: the HMAC covers every field but the signature, the key id included."""
    if not key:
        raise ValueError("signing key must not be empty")
    labelled = result.model_copy(update={"signature": None, "signature_key_id": key_id})
    return labelled.model_copy(update={"signature": _mac(key, signable_text(labelled))})


#: :func:`signature_form`: the signature covers the content and the key id it names.
FORM_BOUND = "bound"
#: :func:`signature_form`: the signature an earlier build issued over the content without the key id; the key id is not attested.
FORM_LEGACY = "legacy"


def signature_form(result: VerificationResult, key: bytes) -> Optional[str]:
    """The form in which ``key`` signed ``result``: :data:`FORM_BOUND` (over exactly its content and the key id it names),
    :data:`FORM_LEGACY` (over its content without the key id, as an earlier build signed; accepted only for a result this
    build did not produce, :func:`_issued_elsewhere`) or None (no valid signature). Never raises.

    A legacy-form signature attests who holds the key, never the key id the result names: relabelled to another id, the
    result still verifies in that form (repair round 3, INV-6). A receiver that trusts by key id therefore asks with the id
    (:func:`verify_signature` ``key_id``), and the release rule reports the id as not attested."""
    try:
        if not isinstance(key, (bytes, bytearray)) or not key:
            return None
        presented = result.signature
        if not isinstance(presented, str) or _SIGNATURE_RE.fullmatch(presented) is None:
            return None
        if mac_matches(_mac(bytes(key), signable_text(result)), presented):
            return FORM_BOUND
        if _issued_elsewhere(result) and mac_matches(_mac(bytes(key), legacy_signable_text(result)), presented):
            return FORM_LEGACY
        return None
    except Exception:  # noqa: BLE001 - a result that cannot be serialised or read carries no valid signature
        return None


def verify_signature(result: VerificationResult, key: bytes, key_id: Optional[str] = None) -> bool:
    """Whether ``result`` carries a signature that ``key`` issued over exactly its content and key id. Never raises.

    A result this build did not produce (:func:`_issued_elsewhere`) may also carry the signature an earlier build issued over
    the content without the key id (:func:`legacy_signable_text`); such a result is never current-policy evidence
    (:func:`stale_reasons`), so accepting that form keeps it inspectable and grants nothing. With ``key_id`` (a receiver
    that trusts by key id) the result must name that id and its signature must cover it: the earlier form attests no key
    id, so a result signed in it never verifies against one (repair round 3, INV-6)."""
    form = signature_form(result, key)
    if form is None:
        return False
    if key_id is None:
        return True
    return form == FORM_BOUND and result.signature_key_id == key_id


def _issued_elsewhere(result: VerificationResult) -> bool:
    """True when ``result`` names other component versions or another build, schema or policy identity than this build's
    (or none): a result of another build, which this build can only read as a historical record."""
    return result.versions != compute_versions()
