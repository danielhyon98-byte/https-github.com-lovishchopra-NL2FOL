"""The versions and identities of the argument-diagnosis release: bumped once, and the rules bound into the identity."""
from __future__ import annotations

import pytest

from epinoic_logic import ARG_RULES_VERSION as EXPORTED
from epinoic_logic import named
from epinoic_logic.engine import identity as identity_mod
from epinoic_logic.engine.provenance import compute_versions
from epinoic_logic.engine.results import VerificationResult
from epinoic_logic.translate.contracts import ReleaseAssessment
from epinoic_logic.translate.outcome import RELEASE_POLICY
from epinoic_logic.version import ARG_RULES_VERSION, ENGINE_VERSION, IR_VERSION, POLICY_VERSION, TRANSLATOR_VERSION


def test_the_versions_of_this_release():
    # ported onto the integrated translator: the four component versions stay as this tree and its integration kit pin them
    # (docs/ARGUMENT_DIAGNOSTICS.md, section 20); the argument rules and the release policy are the feature's own. The pins stay exact
    assert (IR_VERSION, ENGINE_VERSION, POLICY_VERSION, TRANSLATOR_VERSION) == ("1.0", "0.4.0", "2026.11-v5", "0.4.0")  # pin moved: POLICY_VERSION 2026.11-v5 (eligibility rule 0, round-10 hold remedy c3b)
    assert ARG_RULES_VERSION == EXPORTED == "argdiag-2" and RELEASE_POLICY == "release-v1"   # ported: the label stays with the versions
    assert ReleaseAssessment.model_fields["policy"].default == "release-v1"
    v = compute_versions()
    assert (v.engine_version, v.policy_version) == (ENGINE_VERSION, POLICY_VERSION)


def test_the_build_identity_covers_the_shared_modules():
    assert identity_mod.BUILD_SOURCES == ("version.py", "named.py", "lexis.py", "ir", "engine")


def test_the_policy_manifest_binds_the_rules_and_the_code_table(monkeypatch: pytest.MonkeyPatch):
    manifest = identity_mod.policy_manifest()
    assert manifest["argument_rules"] == "argdiag-2" and manifest["named_codes"] == named.named_codes_digest()
    current = identity_mod.policy_id.__wrapped__()
    monkeypatch.setattr(named, "named_codes_digest", lambda: "0" * 64)            # another code table is another policy
    assert identity_mod.policy_id.__wrapped__() != current


def test_the_schema_identity_covers_the_two_result_fields():
    props = VerificationResult.model_json_schema()["properties"]
    assert {"named_diagnostics", "argument_rules"} <= set(props)
    assert identity_mod.schema_id() == compute_versions().schema_id


def test_the_policy_manifest_binds_the_self_certification_rules(monkeypatch: pytest.MonkeyPatch):
    """POLICY_VERSION 2026.11-v5 (hold remedy c3b, decision D6): eligibility rule 0 reads the one self-certification reader, so its
    rules version and the digest of its lexicon and fold table are part of the policy identity; a change to them without a version
    bump still makes every result of another build stale."""
    from epinoic_logic import selfcert
    manifest = identity_mod.policy_manifest()
    assert manifest["eligibility_self_certification"] == {"rules": "selfcert-1", "digest": selfcert.rules_digest()}
    current = identity_mod.policy_id.__wrapped__()
    monkeypatch.setattr(selfcert, "rules_digest", lambda: "0" * 64)               # another lexicon is another policy
    assert identity_mod.policy_id.__wrapped__() != current


def test_a_result_signed_under_the_previous_policy_version_is_stale_and_never_current():
    """A current result whose only change is ``versions.policy_version`` set back to 2026.10-v4 (re-signed with the test key) is
    stale: the policy version is named, and the result is never displayed as a verdict of this build."""
    from epinoic_logic.engine import SolverConfig, verify, verify_signature
    from epinoic_logic.engine.provenance import stale_reasons
    from epinoic_logic.engine.provenance import sign_result
    from epinoic_logic.ir import Problem
    import json
    from pathlib import Path
    key = b"c3b-policy-bump-test-key-0123456789abcd"
    data = Path(__file__).resolve().parents[1] / "engine" / "data" / "release_0_4_0_signed_results.json"
    entry = next(iter(json.loads(data.read_text(encoding="utf-8")).values()))
    problem = Problem.model_validate(entry["problem"])
    fresh = verify(problem, SolverConfig.model_validate(entry["config"]), signing_key=key, key_id="k")
    assert stale_reasons(fresh) == []
    old = fresh.model_copy(update={"versions": fresh.versions.model_copy(update={"policy_version": "2026.10-v4"})})
    old = sign_result(old, key, "k")
    assert verify_signature(old, key)
    reasons = stale_reasons(old)
    assert reasons and any("2026.10-v4" in r for r in reasons), reasons
