"""The c3h bump (POLICY_VERSION 2026.11-v7 to 2026.11-v8, rules ``selfcert-3`` to ``selfcert-4``, contract 0.8 to 0.9).

Eligibility rule 0's readings changed again in the c3h follow-up (it reverts exemptions that freed own-scope text and closes bounds
that failed open; ``epinoic_logic.version`` lists them), so a result signed under policy 2026.11-v7 is not current-policy evidence
of this build. A current result rewritten to policy_version 2026.11-v7, rebound and re-signed with the test key exactly as a
2026.11-v7 build would have issued it, is stale: ``stale_reasons`` names the policy version, ``release_check`` refuses it with that
staleness as its only reason, and the composer never displays it as a verdict (INTERNAL_ERROR). The same result, fresh, is
eligible and displayed as the engine decided it. The current versions are pinned exactly beside it."""
from __future__ import annotations

import json
from pathlib import Path

from epinoic_logic import selfcert
from epinoic_logic.engine.provenance import compute_binding, sign_result, stale_reasons, verify_signature
from epinoic_logic.engine.release import release_check
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.runner import verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integration.protocol import INTEGRATION_CONTRACT_VERSION
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, EligibilityDecision, TranslationResult
from epinoic_logic.translate.outcome import compose_outcome, display_status_for
from epinoic_logic.version import POLICY_VERSION, TRANSLATOR_VERSION

ROOT = Path(__file__).resolve().parents[2]
KEY = b"c3h-policy-bump-test-key-0123456789abcd"
KEY_ID = "c3h"
PREVIOUS = "2026.11-v7"


def _fixture() -> tuple[Problem, SolverConfig]:
    data = ROOT / "tests" / "engine" / "data" / "release_0_4_0_signed_results.json"
    entry = json.loads(data.read_text(encoding="utf-8"))["established_modus_ponens"]
    return Problem.model_validate(entry["problem"]), SolverConfig.model_validate(entry["config"])


def _translated(problem: Problem) -> TranslationResult:
    return TranslationResult(translation_id="tr", request_id=problem.request_id, report_id="rep", claim_id=problem.claim_id,
                             status="TRANSLATED",
                             eligibility=EligibilityDecision(eligibility_class="PROPOSITIONAL_ARGUMENT", eligible=True,
                                                             decided_by="deterministic", policy_version=POLICY_VERSION),
                             problem=problem, translator_version=TRANSLATOR_VERSION, policy_version=POLICY_VERSION,
                             created_at="2026-11-24T00:00:00Z")


def _claim(problem: Problem) -> ClaimRecord:
    return ClaimRecord(request_id=problem.request_id, task_id="t", report_id="rep", agent_id="a", subject="Philosophy",
                       task_type="short_answer", claim_id=problem.claim_id, claim_text="If p then q; p; so q.",
                       claim_role="thesis")


def _as_previous_policy(fresh, problem: Problem, config: SolverConfig):
    """``fresh`` as a 2026.11-v7 build would have issued it: only ``versions.policy_version`` differs, the binding is computed over
    those versions, and the whole is signed again with the test key (so neither the signature nor the binding gives it away)."""
    versions = fresh.versions.model_copy(update={"policy_version": PREVIOUS})
    binding = compute_binding(problem, config, versions, fresh.binding.smt2, fresh.limits)
    old = fresh.model_copy(update={"versions": versions, "binding": binding})
    return sign_result(old, KEY, KEY_ID)


def test_the_versions_of_the_c3h_bump():
    # pins moved with the c3k bump (2026.11-v8 to 2026.11-v9, selfcert-4 to selfcert-5, contract 0.9 to 0.10), exact; a result
    # signed under 2026.11-v7 stays stale below, and tests/contract/test_policy_v9_stale.py holds the same for 2026.11-v8
    assert POLICY_VERSION == "2026.11-v9" and INTEGRATION_CONTRACT_VERSION == "0.10" and selfcert.SELFCERT_RULES == "selfcert-5"
    compat = json.loads((ROOT / "integration" / "COMPATIBILITY.json").read_text(encoding="utf-8"))
    # decision D8: only the new versions are accepted, never the previous ones beside them
    assert compat["components"]["policy"] == ["2026.11-v9"] and compat["components"]["contract"] == ["0.10"]
    assert PREVIOUS not in compat["components"]["policy"] and "0.8" not in compat["components"]["contract"]
    assert "2026.11-v8" not in compat["components"]["policy"] and "0.9" not in compat["components"]["contract"]


def test_a_fresh_result_is_current_eligible_and_displayed_as_decided():
    problem, config = _fixture()
    fresh = verify(problem, config, signing_key=KEY, key_id=KEY_ID)
    assert fresh.status is S.ENTAILED and fresh.versions.policy_version == POLICY_VERSION
    assert stale_reasons(fresh) == []
    check = release_check(fresh, problem, signing_key=KEY, key_id=KEY_ID)
    assert check.eligible is True and check.reasons == ()
    assert display_status_for(_translated(problem), fresh, KEY, KEY_ID) is S.ENTAILED
    outcome = compose_outcome(_claim(problem), _translated(problem), fresh, signing_key=KEY, key_id=KEY_ID)
    assert outcome.display_status is S.ENTAILED


def test_a_result_signed_under_policy_2026_11_v7_is_stale_refused_and_never_displayed_as_a_verdict():
    problem, config = _fixture()
    fresh = verify(problem, config, signing_key=KEY, key_id=KEY_ID)
    old = _as_previous_policy(fresh, problem, config)
    assert verify_signature(old, KEY) and old.status is S.ENTAILED
    reasons = stale_reasons(old)
    assert reasons and any(f"policy_version '{PREVIOUS}' (current '{POLICY_VERSION}')" in r for r in reasons), reasons
    check = release_check(old, problem, signing_key=KEY, key_id=KEY_ID)
    assert check.eligible is False
    # the staleness is the only reason: the result is authentic, bound and a positive verdict in every other respect
    assert check.reasons and all(r.startswith("stale: ") for r in check.reasons), check.reasons
    assert any(PREVIOUS in r for r in check.reasons), check.reasons
    assert display_status_for(_translated(problem), old, KEY, KEY_ID) is S.INTERNAL_ERROR
    outcome = compose_outcome(_claim(problem), _translated(problem), old, signing_key=KEY, key_id=KEY_ID)
    assert outcome.display_status is S.INTERNAL_ERROR
    assert outcome.display_status not in (S.ENTAILED, S.CONSISTENT, S.COUNTEREXAMPLE)
