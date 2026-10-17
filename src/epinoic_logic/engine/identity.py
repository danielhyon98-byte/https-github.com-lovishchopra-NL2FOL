"""Immutable identity of the engine build, of its schemas and of its decision policy.

Every result binds three digests beside the component versions (``Versions.build_id``, ``schema_id`` and
``policy_id``), so a result is current-policy evidence only for the build that produced it:

* ``build_id``: SHA-256 over the source of everything that decides an engine result (``version.py``, the ``ir``
  package and the ``engine`` package), file by file in path order;
* ``schema_id``: SHA-256 over the JSON Schemas of ``Problem``, ``Limits``, ``SolverConfig`` and
  ``VerificationResult`` as this build renders them;
* ``policy_id``: SHA-256 over :func:`policy_manifest`, the decision policy as data (allowlist, default and named
  limits, the nonlinear bounds, the premise-authority rules, which diagnostics withhold a verdict and which are
  advisory, and what evidence is always computed).

They are computed, never maintained by hand: a component version left unchanged by mistake cannot make an older result
look current, and two policies used within one build (default and permissive limits) are told apart by the limits
binding (:func:`.provenance.limits_digest`), not by these identities. When the sources cannot be read the build id is
``unavailable:`` plus a random token, so such a build never treats another process's results as current.
"""
from __future__ import annotations

import hashlib
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..ir.canonical import canonical_json, sha256_hex

__all__ = ["BUILD_SOURCES", "build_id", "schema_id", "policy_id", "policy_manifest", "identity"]

_PACKAGE = Path(__file__).resolve().parent.parent
#: The sources that decide an engine result, relative to the package directory.
BUILD_SOURCES: tuple[str, ...] = ("version.py", "ir", "engine")


def _unavailable() -> str:
    return "unavailable:" + uuid.uuid4().hex


@lru_cache(maxsize=1)
def build_id() -> str:
    """SHA-256 over the decision-relevant source files of this build (see :data:`BUILD_SOURCES`)."""
    try:
        files: list[Path] = []
        for entry in BUILD_SOURCES:
            path = _PACKAGE / entry
            files.extend(sorted(path.glob("*.py")) if path.is_dir() else [path])
        h = hashlib.sha256()
        for f in sorted(set(files), key=lambda p: p.relative_to(_PACKAGE).as_posix()):
            data = f.read_bytes()
            h.update(f"{f.relative_to(_PACKAGE).as_posix()}\0{len(data)}\0".encode("utf-8"))
            h.update(data)
        return h.hexdigest()
    except Exception:  # noqa: BLE001 - never raise from identity; fail closed instead
        return _unavailable()


@lru_cache(maxsize=1)
def schema_id() -> str:
    """SHA-256 over the JSON Schemas of the problem, limits, configuration and result models of this build."""
    try:
        from ..ir.schema import Limits, Problem
        from .results import SolverConfig, VerificationResult
        return sha256_hex(canonical_json({m.__name__: m.model_json_schema() for m in (Problem, Limits, SolverConfig, VerificationResult)}))
    except Exception:  # noqa: BLE001
        return _unavailable()


def policy_manifest() -> dict[str, Any]:
    """The engine's decision policy as data. Its digest is :func:`policy_id`."""
    from ..ir.schema import ALLOWED_OPS, DEFAULT_LIMITS
    from ..version import POLICY_VERSION
    from .authority import dependency_policy
    from .errors import ADVISORY_CODES, NO_VERDICT_CODES
    from .policies import JOINT_LIMITS, NAMED_POLICIES, NONLINEAR_MAX_DEGREE, NONLINEAR_RLIMIT, PACK_POLICIES
    return {
        "policy_version": POLICY_VERSION,
        "allowlist": sorted(ALLOWED_OPS),
        "default_limits": DEFAULT_LIMITS.model_dump(mode="json"),
        "pack_policies": {name: PACK_POLICIES[name].model_dump(mode="json") for name in sorted(PACK_POLICIES)},
        "joint_limits": JOINT_LIMITS.model_dump(mode="json"),
        "named_policies": {name: NAMED_POLICIES[name].model_dump(mode="json") for name in sorted(NAMED_POLICIES)},
        "nonlinear_rlimit": NONLINEAR_RLIMIT,
        "nonlinear_max_degree": NONLINEAR_MAX_DEGREE,
        "dependencies": dependency_policy(),
        "no_verdict_diagnostics": sorted(NO_VERDICT_CODES),
        "advisory_diagnostics": sorted(ADVISORY_CODES),
        "evidence": {
            "unsat_core": "always computed; produce_unsat_core only decides whether the unsat_core record is serialised",
            "limits": "non-default effective limits are recorded and bound by binding.limits_digest; default limits are those of this policy",
            "coverage": ("E110/E111 only when a symbol the counterexample turns on carries a grounding verified in this process (any kind: "
                         "a source states it); otherwise the advisory W110/W111 and the COUNTEREXAMPLE stands"),
        },
    }


@lru_cache(maxsize=1)
def policy_id() -> str:
    """SHA-256 over :func:`policy_manifest`."""
    try:
        return sha256_hex(canonical_json(policy_manifest()))
    except Exception:  # noqa: BLE001
        return _unavailable()


def identity() -> dict[str, str]:
    """``{build_id, schema_id, policy_id}`` of this build."""
    return {"build_id": build_id(), "schema_id": schema_id(), "policy_id": policy_id()}
