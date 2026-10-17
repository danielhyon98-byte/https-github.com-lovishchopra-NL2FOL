"""The start-up self-test (``integration/PROTOCOL.md`` section 3, check 1): three fixed problems decided by the real
engine, each under its named policy, before the service binds a socket.

1. ``linear-entailment``: a linear entailment under ``linear``;
2. ``stem-nonlinear``: a worked STEM step (``v = u + a*t``) under ``nonlinear``, the policy of the STEM checks;
3. ``joint-consistency``: a cross-agent consistency check under ``joint``, the policy of the joint checks.

Each must give its expected status and its pinned build-independent digests (problem, configuration, limits), its
binding must be internally consistent and its signature must verify under the engine key. The binding digest itself
changes with every build (it binds the build identity), so the capabilities response reports it and does not pin it.
A tampered expectation fails the self-test (``KIT-HS-004``).

The policies resolve through the engine's own pack-policy table and joint limits (``engine.policies``): exactly what
the channel's branch checks and the integrity layer's joint checks use, and what the named-policy allowlist of
contract 0.3 maps the names to.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .errors import IntegrationError

__all__ = ["PROBLEMS", "EXPECTED", "SelfTestOutcome", "resolve_policy", "run_selftest"]


def _var(name: str) -> dict:
    return {"op": "var", "name": name}


def _int(value: str) -> dict:
    return {"op": "int", "value": value}


def _real(value: str) -> dict:
    return {"op": "real", "value": value}


#: The three fixed problems (IR 1.0, data only).
PROBLEMS: Mapping[str, tuple[str, dict]] = {
    "linear-entailment": ("linear", {
        "ir_version": "1.0", "problem_id": "selftest-linear", "request_id": "selftest", "claim_id": "selftest-linear",
        "query": "entailment",
        "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}],
        "premises": [
            {"id": "P1", "expr": {"op": "gt", "left": _var("x"), "right": _int("2")}},
            {"id": "P2", "expr": {"op": "eq", "left": _var("y"), "right": {"op": "add", "args": [_var("x"), _int("1")]}}},
        ],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": _var("y"), "right": _int("3")}},
    }),
    "stem-nonlinear": ("nonlinear", {
        "ir_version": "1.0", "problem_id": "selftest-stem", "request_id": "selftest", "claim_id": "selftest-stem",
        "query": "entailment",
        "symbols": [{"name": "u", "sort": "Real"}, {"name": "a", "sort": "Real"}, {"name": "t", "sort": "Real"}, {"name": "v", "sort": "Real"}],
        "premises": [
            {"id": "P1", "expr": {"op": "eq", "left": _var("u"), "right": _real("2")}},
            {"id": "P2", "expr": {"op": "eq", "left": _var("a"), "right": _real("3")}},
            {"id": "P3", "expr": {"op": "eq", "left": _var("t"), "right": _real("4")}},
            {"id": "P4", "expr": {"op": "eq", "left": _var("v"), "right": {"op": "add", "args": [_var("u"), {"op": "mul", "args": [_var("a"), _var("t")]}]}}},
        ],
        "conclusion": {"id": "C", "expr": {"op": "eq", "left": _var("v"), "right": _real("14")}},
    }),
    "joint-consistency": ("joint", {
        "ir_version": "1.0", "problem_id": "selftest-joint", "request_id": "selftest", "claim_id": "selftest-joint",
        "query": "consistency",
        "symbols": [{"name": "y1", "sort": "Int"}, {"name": "y2", "sort": "Int"}],
        "premises": [
            {"id": "P1", "expr": {"op": "eq", "left": _var("y1"), "right": _int("1914")}},
            {"id": "P2", "expr": {"op": "eq", "left": _var("y2"), "right": {"op": "add", "args": [_var("y1"), _int("4")]}}},
            {"id": "P3", "expr": {"op": "eq", "left": _var("y2"), "right": _int("1918")}},
        ],
    }),
}

#: Expected status and build-independent digests of each problem (recomputed by ``tests/integration/test_selftest.py``).
EXPECTED: Mapping[str, Mapping[str, Optional[str]]] = {
    "linear-entailment": {
        "status": "ENTAILED",
        "problem_digest": "e9c27a65e78b85cc5b2dd3f49b1ea2231b1a84e7377a904778910b3e8f9fabef",
        "config_digest": "3fa228d0bdd71f9a138a8527eae9c8ec54368e32e1fc9a888dc9ec0413895b65",
        "limits_digest": None,
    },
    "stem-nonlinear": {
        "status": "ENTAILED",
        "problem_digest": "5ff191ffe1d2a1fe31b15c544f3327961aaeaa5a251bebc51312146e1364dec0",
        "config_digest": "42e46deb2c8effce16d365aa3fc873a9d391462b26a810c87c81fccbf962935d",
        "limits_digest": "3abba818b1d2d3fdbcbc910fe2a1b816cb373baacaf21e29f4e2799f06717a1f",
    },
    "joint-consistency": {
        "status": "CONSISTENT",
        "problem_digest": "5032c23ff200c5e58c04123795ec447472fab73bbc3ec82b52ed29bc6d5b9de5",
        "config_digest": "3fa228d0bdd71f9a138a8527eae9c8ec54368e32e1fc9a888dc9ec0413895b65",
        "limits_digest": "14ade00962c79e27ecd2c4ba749a20e13943b1632281e2853972e3facfdde8e9",
    },
}


@dataclass(frozen=True)
class SelfTestOutcome:
    passed: bool
    binding_digests: tuple[str, ...]
    failures: tuple[str, ...]


def resolve_policy(name: str, config: Any) -> tuple[Any, Any]:
    """``(limits, config)`` for a named policy, from the engine's own tables (see the module docstring)."""
    from ..engine.policies import JOINT_LIMITS, policy_config, policy_limits
    if name == "joint":
        return JOINT_LIMITS, config
    return policy_limits(name), policy_config(name, config)


def run_selftest(signing_key: bytes, key_id: str, *, expected: Optional[Mapping[str, Mapping[str, Optional[str]]]] = None) -> SelfTestOutcome:
    """Decide the three problems. Never raises for a wrong result: the outcome lists every failure by problem name."""
    from ..engine.provenance import binding_inconsistencies, verify_signature
    from ..engine.results import SolverConfig
    from ..engine.runner import verify

    table = EXPECTED if expected is None else expected
    failures: list[str] = []
    digests: list[str] = []
    for name, (policy, problem) in PROBLEMS.items():
        want = table.get(name)
        if want is None:
            failures.append(f"{name}: no expectation")
            continue
        limits, config = resolve_policy(policy, SolverConfig())
        result = verify(problem, config, limits, signing_key, key_id)
        digests.append(result.binding.binding_digest)
        got = {"status": result.status.value, "problem_digest": result.binding.problem_digest,
               "config_digest": result.binding.config_digest, "limits_digest": result.binding.limits_digest}
        for k, v in got.items():
            if want.get(k) != v:
                failures.append(f"{name}: {k} differs from the pinned expectation")
        if binding_inconsistencies(result):
            failures.append(f"{name}: the binding is inconsistent")
        if not verify_signature(result, signing_key):
            failures.append(f"{name}: the signature does not verify")
    return SelfTestOutcome(passed=not failures, binding_digests=tuple(digests), failures=tuple(failures))


def require_selftest(signing_key: bytes, key_id: str) -> SelfTestOutcome:
    outcome = run_selftest(signing_key, key_id)
    if not outcome.passed:
        raise IntegrationError("KIT-HS-004", "; ".join(outcome.failures)[:400])
    return outcome
