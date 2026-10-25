"""Close round 3, DV2-07 (security): one channel decides the same joint problem again on every later transmission (the pool
of every report so far, the claim-by-claim attribution of a contradiction it already named, the rest after a contradiction
is set aside), so an r7 answer group made 190 joint engine runs over 29 distinct problems and the round took more than
three times the committed base's time. A definitive answer of a joint check (``integrity.cross_check.verify``) is now
kept for the identical problem, configuration, limits and signing key, and the same signed result is cited again; an
undecided answer is never kept. The findings are the same; only work repeated for an identical problem is not done twice.
"""
from __future__ import annotations

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity import cross_check as cc
from epinoic_logic.ir.schema import Problem

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"close3-joint-memo-key-0123456789abcdef"


def _claim(cid: str, value: str, meaning: str = "the speed of the car") -> Problem:
    return Problem.model_validate({
        "problem_id": f"p-{cid}", "request_id": "r", "claim_id": cid, "query": "entailment",
        "symbols": [{"name": "x", "sort": "Real", "meaning": meaning}],
        "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": value}},
                      "grounding": {"kind": "supplied_text", "verified": True}}],
        "conclusion": {"id": "C", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": value}}}})


@pytest.fixture
def engine_runs(monkeypatch):
    """Every engine run the joint checks make (the memo's misses), and a fresh memo for the test."""
    runs: list[str] = []
    real = cc._engine_verify

    def counting(problem, *a, **k):
        runs.append(problem.problem_id)
        return real(problem, *a, **k)

    monkeypatch.setattr(cc, "_engine_verify", counting)
    monkeypatch.setattr(cc, "_joint_memo", type(cc._joint_memo)())
    return runs


def _summary(findings) -> list[tuple[str, str, tuple[str, ...]]]:
    return sorted((f.code, f.severity, tuple(f.claim_ids)) for f in findings)


def test_an_identical_joint_check_is_decided_once_and_names_the_same_contradiction(engine_runs):
    pool = [_claim("c1", "1"), _claim("c2", "2"), _claim("c3", "1")]
    first, f1 = cc.check_cross_report_consistency(pool, request_id="r", config=CFG, signing_key=KEY)
    made = len(engine_runs)
    again, f2 = cc.check_cross_report_consistency(pool, request_id="r", config=CFG, signing_key=KEY)
    assert first.status is S.INCONSISTENT_PREMISES and made > 1
    assert len(engine_runs) == made                      # nothing decided twice
    assert _summary(f1) == _summary(f2) and any(f.code == "INT-CONFLICT-001" for f in f2)
    assert again.result_id == first.result_id and again.signature == first.signature  # the same signed result is cited


def test_a_growing_pool_costs_the_new_problems_only(engine_runs):
    # a channel checks the pool after every transmission: the contradiction named on the first check is attributed again on
    # every later one, and each of those attributions is a problem already decided
    pools = [[_claim("c1", "1"), _claim("c2", "2")] + [_claim(f"k{j}", "7", meaning=f"quantity {j}") for j in range(n)] for n in range(6)]
    counts = []
    for pool in pools:
        before = len(engine_runs)
        cc.check_cross_report_consistency(pool, request_id="r", config=CFG, signing_key=KEY)
        counts.append(len(engine_runs) - before)
    # every check after the first decides the new joint problems only: the claim-alone and minimisation runs of the
    # contradiction it names again are kept
    assert all(c <= counts[0] for c in counts[1:]), counts
    assert sum(counts) < 6 * counts[0], counts


def test_control_another_signing_key_or_configuration_is_another_check(engine_runs):
    pool = [_claim("c1", "1"), _claim("c2", "2")]
    cc.check_cross_report_consistency(pool, request_id="r", config=CFG, signing_key=KEY)
    made = len(engine_runs)
    cc.check_cross_report_consistency(pool, request_id="r", config=CFG, signing_key=b"another-key-0123456789abcdef012345")
    assert len(engine_runs) > made
    made = len(engine_runs)
    cc.check_cross_report_consistency(pool, request_id="r", config=CFG.model_copy(update={"timeout_ms": 3000}), signing_key=KEY)
    assert len(engine_runs) > made


def test_control_an_undecided_joint_check_is_decided_again(monkeypatch, engine_runs):
    real = cc._engine_verify

    def undecided(problem, *a, **k):
        res = real(problem, *a, **k)
        return res.model_copy(update={"status": S.UNKNOWN})

    monkeypatch.setattr(cc, "_engine_verify", undecided)
    pool = [_claim("c1", "1"), _claim("c2", "2")]
    assert cc.verify(pool[0], CFG, cc.JOINT_LIMITS, signing_key=KEY, key_id="integrity").status is S.UNKNOWN
    assert len(cc._joint_memo) == 0
