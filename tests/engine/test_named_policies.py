"""Named engine policies a caller outside the packs may request (engine/policies.py: NAMED_POLICIES, named_policy,
named_policy_of), added for bug 8 of the end-to-end simulation of 16 October 2026: the service and the CLI take a
policy NAME and decide a problem exactly as the in-process caller of that policy does.

Pinned here:

* the table is exactly the pack policies plus ``joint`` (the integrity layer's joint bounds), read-only, and the pack
  policies are unchanged (a pack still cannot choose ``joint``);
* ``named_policy`` gives the channel's limits and configuration for a pack policy (the nonlinear rlimit cap included)
  and ``(JOINT_LIMITS, config)`` for ``joint``, so a problem decided through it binds what the in-process run binds;
* every name the pack policies refuse is refused here too, and so are case variants of ``joint``;
* ``named_policy_of`` names the policy a result's limits record stands for, compared on every limit value;
* the policy identity covers the table.
"""
from __future__ import annotations

from typing import Any

import pytest

from epinoic_logic.engine import identity as identity_mod
from epinoic_logic.engine.policies import (
    JOINT,
    JOINT_LIMITS,
    LINEAR,
    NAMED_POLICIES,
    NONLINEAR,
    NONLINEAR_LIMITS,
    NONLINEAR_RLIMIT,
    PACK_POLICIES,
    UnknownPolicyError,
    named_policy,
    named_policy_of,
    policy_config,
    policy_limits,
)
from epinoic_logic.engine.provenance import limits_digest
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import DEFAULT_LIMITS, Limits, Problem

from .test_pack_policies import UNKNOWN_NAMES

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def square() -> Problem:
    v = {"op": "var", "name": "x"}
    return Problem.model_validate({"problem_id": "sq", "request_id": "r", "claim_id": "c", "query": "satisfiability", "symbols": [{"name": "x", "sort": "Int"}],
                                   "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "mul", "args": [v, v]}, "right": {"op": "int", "value": "9"}}}]})


def test_the_named_policies_are_the_pack_policies_and_the_joint_bounds():
    assert dict(NAMED_POLICIES) == {LINEAR: DEFAULT_LIMITS, NONLINEAR: NONLINEAR_LIMITS, JOINT: JOINT_LIMITS}
    assert set(PACK_POLICIES) == {LINEAR, NONLINEAR}, "the pack policies are unchanged"
    with pytest.raises(UnknownPolicyError):
        policy_limits(JOINT)  # a pack still cannot choose the joint bounds
    with pytest.raises(TypeError):
        NAMED_POLICIES["unbounded"] = Limits(max_nodes=10 ** 9)  # type: ignore[index]
    for method in ("update", "clear", "pop", "popitem", "setdefault"):
        assert not hasattr(NAMED_POLICIES, method)
    assert len({limits_digest(v) for v in NAMED_POLICIES.values()}) == 3, "every policy has its own limits identity"


@pytest.mark.parametrize("name", [LINEAR, NONLINEAR])
def test_a_pack_policy_is_named_exactly_as_the_channel_runs_it(name):
    for config in (CFG, SolverConfig(), SolverConfig(rlimit=5), SolverConfig(rlimit=NONLINEAR_RLIMIT * 100)):
        limits, cfg = named_policy(name, config)
        assert limits is policy_limits(name) and cfg == policy_config(name, config)
    assert named_policy(LINEAR, CFG)[1] is CFG
    assert named_policy(NONLINEAR, SolverConfig())[1].rlimit == NONLINEAR_RLIMIT


def test_joint_is_named_exactly_as_the_joint_checks_run():
    for config in (CFG, SolverConfig(rlimit=7)):
        limits, cfg = named_policy(JOINT, config)
        assert limits is JOINT_LIMITS and cfg is config


REFUSED = UNKNOWN_NAMES + ["Joint", "JOINT", " joint", "joint\n", "jo\u0131nt", "joints"]


@pytest.mark.parametrize("name", REFUSED, ids=[f"name{i}" for i in range(len(REFUSED))])
def test_an_unknown_name_is_refused_never_run_under_another_policy(name: Any):
    with pytest.raises(UnknownPolicyError) as error:
        named_policy(name, CFG)
    message = str(error.value)
    assert message.startswith("unknown engine policy") and "known policies: joint, linear, nonlinear" in message and len(message) < 400
    message.encode("utf-8")


@pytest.mark.parametrize("name", sorted(NAMED_POLICIES))
def test_a_result_names_its_policy_by_its_limits(name):
    limits, cfg = named_policy(name, CFG)
    result = verify(square(), cfg, limits)
    assert named_policy_of(result.limits) == name
    assert result.binding.limits_digest == limits_digest(limits)


def test_limits_that_no_named_policy_has_name_no_policy():
    assert named_policy_of(None) == LINEAR
    assert named_policy_of(Limits()) == LINEAR and named_policy_of(Limits(allow_nonlinear=True)) == NONLINEAR
    assert named_policy_of(JOINT_LIMITS.model_copy()) == JOINT
    assert named_policy_of(Limits(max_nodes=3000)) is None
    assert named_policy_of(Limits(**{**JOINT_LIMITS.model_dump(), "allow_nonlinear": True})) is None
    assert named_policy_of({"allow_nonlinear": True}) is None  # type: ignore[arg-type]


def test_the_same_problem_decides_by_policy_and_binds_each_differently():
    by_name = {}
    for name in sorted(NAMED_POLICIES):
        limits, cfg = named_policy(name, CFG)
        by_name[name] = verify(square(), cfg, limits)
    assert by_name[NONLINEAR].status.value == "SATISFIABLE"
    assert by_name[LINEAR].status.value == by_name[JOINT].status.value == "UNSUPPORTED"
    assert len({r.binding.binding_digest for r in by_name.values()}) == 3


def test_the_policy_identity_covers_the_named_policies():
    manifest = identity_mod.policy_manifest()
    assert manifest["named_policies"] == {name: NAMED_POLICIES[name].model_dump(mode="json") for name in sorted(NAMED_POLICIES)}
