"""The c3k bump (POLICY_VERSION 2026.11-v8 to 2026.11-v9, rules ``selfcert-4`` to ``selfcert-5``, contract 0.9 to 0.10; stage 2a of
the meaning check).

The policy identity now binds the block-only meaning label of the self-certification class (``policy_manifest()`` gains
``selfcert_meaning_label``: ``selfcert-label-2``, its ``label_digest()`` and ``required: true``), and eligibility rule 0 reads
``selfcert-5`` (decision 5, decision L4's companion test and the stage-1 misses; ``epinoic_logic.version`` lists them), so a result
signed under policy 2026.11-v8 is not current-policy evidence of this build. A current result rewritten to policy_version
2026.11-v8, rebound and re-signed with the test key exactly as a 2026.11-v8 build would have issued it, is stale: ``stale_reasons``
names the policy version, ``release_check`` refuses it with that staleness as its only reason, and the composer never displays it
as a verdict (INTERNAL_ERROR). The same result, fresh, is eligible and displayed as the engine decided it. A result whose policy
identity is that of a build without the label entry (or with another label digest) is stale too. The current versions are
pinned exactly beside it."""
from __future__ import annotations

import json
from pathlib import Path

import epinoic_logic.selfcert_label as L
from epinoic_logic import selfcert
from epinoic_logic.engine import identity as identity_mod
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
KEY = b"c3k-policy-bump-test-key-0123456789abcd"
KEY_ID = "c3k"
PREVIOUS = "2026.11-v8"


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
                             created_at="2026-11-27T00:00:00Z")


def _claim(problem: Problem) -> ClaimRecord:
    return ClaimRecord(request_id=problem.request_id, task_id="t", report_id="rep", agent_id="a", subject="Philosophy",
                       task_type="short_answer", claim_id=problem.claim_id, claim_text="If p then q; p; so q.",
                       claim_role="thesis")


def _as_previous_policy(fresh, problem: Problem, config: SolverConfig):
    """``fresh`` as a 2026.11-v8 build would have issued it: only ``versions.policy_version`` differs, the binding is computed over
    those versions, and the whole is signed again with the test key (so neither the signature nor the binding gives it away)."""
    versions = fresh.versions.model_copy(update={"policy_version": PREVIOUS})
    binding = compute_binding(problem, config, versions, fresh.binding.smt2, fresh.limits)
    old = fresh.model_copy(update={"versions": versions, "binding": binding})
    return sign_result(old, KEY, KEY_ID)


def test_the_versions_of_the_c3k_bump():
    assert POLICY_VERSION == "2026.11-v9" and INTEGRATION_CONTRACT_VERSION == "0.10" and selfcert.SELFCERT_RULES == "selfcert-5"
    assert L.LABEL_VERSION == "selfcert-label-2"
    compat = json.loads((ROOT / "integration" / "COMPATIBILITY.json").read_text(encoding="utf-8"))
    # decision D8: only the new versions are accepted, never the previous ones beside them
    assert compat["components"]["policy"] == ["2026.11-v9"] and compat["components"]["contract"] == ["0.10"]
    assert PREVIOUS not in compat["components"]["policy"] and "0.9" not in compat["components"]["contract"]
    manifest = identity_mod.policy_manifest()
    assert manifest["selfcert_meaning_label"] == {"version": "selfcert-label-2", "digest": L.label_digest(), "required": True}


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


def test_a_result_signed_under_policy_2026_11_v8_is_stale_refused_and_never_displayed_as_a_verdict():
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


def test_a_result_of_a_build_without_the_label_entry_is_stale_and_never_displayed_as_a_verdict(monkeypatch):
    """The policy identity of a build whose manifest lacks ``selfcert_meaning_label`` (or binds another label digest) is another
    policy: a result bound to it, re-signed with the test key, is stale by its policy identity alone and never displayed as a
    verdict, even under the current POLICY_VERSION (a missed version bump cannot make it current)."""
    from epinoic_logic.ir.canonical import canonical_json, sha256_hex
    problem, config = _fixture()
    fresh = verify(problem, config, signing_key=KEY, key_id=KEY_ID)
    without = {k: v for k, v in identity_mod.policy_manifest().items() if k != "selfcert_meaning_label"}
    other = dict(identity_mod.policy_manifest(), selfcert_meaning_label={"version": "selfcert-label-2", "digest": "0" * 64,
                                                                          "required": True})
    for manifest in (without, other):
        pid = sha256_hex(canonical_json(manifest))
        assert pid != fresh.versions.policy_id
        versions = fresh.versions.model_copy(update={"policy_id": pid})
        binding = compute_binding(problem, config, versions, fresh.binding.smt2, fresh.limits)
        old = sign_result(fresh.model_copy(update={"versions": versions, "binding": binding}), KEY, KEY_ID)
        assert verify_signature(old, KEY) and old.versions.policy_version == POLICY_VERSION
        reasons = stale_reasons(old)
        assert reasons and any("policy_id" in r for r in reasons), reasons
        assert release_check(old, problem, signing_key=KEY, key_id=KEY_ID).eligible is False
        assert display_status_for(_translated(problem), old, KEY, KEY_ID) is S.INTERNAL_ERROR
