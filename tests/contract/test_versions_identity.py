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
    assert (IR_VERSION, ENGINE_VERSION, POLICY_VERSION, TRANSLATOR_VERSION) == ("1.0", "0.4.0", "2026.10-v4", "0.4.0")
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
