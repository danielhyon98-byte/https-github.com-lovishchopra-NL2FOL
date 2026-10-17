"""The start-up self-test: three fixed problems decided by the real engine under linear, nonlinear and joint."""
from __future__ import annotations

import pytest

from epinoic_logic.engine.policies import JOINT_LIMITS, policy_config, policy_limits
from epinoic_logic.engine.provenance import config_digest, limits_digest
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.selftest import EXPECTED, PROBLEMS, require_selftest, resolve_policy, run_selftest
from epinoic_logic.ir.canonical import canonical_json, sha256_hex
from epinoic_logic.ir.schema import Problem

KEY = bytes.fromhex("44" * 32)


def test_the_three_problems_give_their_pinned_statuses_and_build_independent_digests():
    outcome = run_selftest(KEY, "selftest")
    assert outcome.passed, outcome.failures
    assert len(outcome.binding_digests) == 3 and len(set(outcome.binding_digests)) == 3


def test_the_pins_are_recomputed_from_the_problems_and_the_policies():
    for name, (policy, problem) in PROBLEMS.items():
        limits, config = resolve_policy(policy, SolverConfig())
        assert EXPECTED[name]["problem_digest"] == sha256_hex(canonical_json(Problem.model_validate(problem)))
        assert EXPECTED[name]["config_digest"] == config_digest(config)
        assert EXPECTED[name]["limits_digest"] == limits_digest(limits)
    assert resolve_policy("nonlinear", SolverConfig()) == (policy_limits("nonlinear"), policy_config("nonlinear", SolverConfig()))
    assert resolve_policy("joint", SolverConfig())[0] == JOINT_LIMITS


@pytest.mark.parametrize("field", ["status", "problem_digest", "config_digest", "limits_digest"])
def test_a_tampered_expectation_fails_the_selftest(field):
    tampered = {k: dict(v) for k, v in EXPECTED.items()}
    tampered["stem-nonlinear"][field] = "COUNTEREXAMPLE" if field == "status" else "0" * 64
    outcome = run_selftest(KEY, "selftest", expected=tampered)
    assert not outcome.passed
    assert any(f.startswith("stem-nonlinear") for f in outcome.failures)


def test_require_selftest_refuses_with_kit_hs_004(monkeypatch):
    import epinoic_logic.integration.selftest as st
    tampered = {k: dict(v) for k, v in EXPECTED.items()}
    tampered["linear-entailment"]["status"] = "COUNTEREXAMPLE"
    monkeypatch.setattr(st, "EXPECTED", tampered)
    with pytest.raises(IntegrationError) as exc:
        require_selftest(KEY, "selftest")
    assert exc.value.code == "KIT-HS-004"
