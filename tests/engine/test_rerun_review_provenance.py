"""Re-run review findings in result signing (each test is the finding's reproduction, with a clean control).

* security-1: a forged signature holding non-ASCII text (or any text that is not 64 lower-case hex digits) made every
  signature check raise TypeError (``hmac.compare_digest`` on two text values), so ``release_check``, the outcome composer
  and the hand-off check crashed on forged input. Each now answers "not authentic" and never raises.
* security-7: the signature did not cover ``signature_key_id``, so a result relabelled to another key id still verified.
  It now covers it; the form earlier builds signed stays readable only for a result this build did not produce.
* security-5: a genuine result run with ``SolverConfig(memory_max_mb=None)`` read as forged after an ``exclude_none`` dump
  was parsed again. The cause is the parse (an absent key read as the default 512), in ``engine/results.py``, outside this
  change; the strict expected failure below records it until that change lands.

These results prove properties of the encoding and of this code only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from epinoic_logic.engine.provenance import (
    compute_versions,
    legacy_signable_text,
    mac_matches,
    sign_result,
    signable_text,
    stale_reasons,
    verify_signature,
)
from epinoic_logic.engine.release import release_check
from epinoic_logic.engine.results import SolverConfig, VerificationResult
from epinoic_logic.engine.runner import verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity.handoff import check_result_binding
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import EligibilityDecision, TranslationResult, sha256_text
from epinoic_logic.translate.outcome import compose_outcome, display_status_for
from epinoic_logic.version import POLICY_VERSION, TRANSLATOR_VERSION

KEY = b"rerun-review-provenance-key-012345"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
DATA = Path(__file__).parent / "data"


def V(n):
    return {"op": "var", "name": n}


PROBLEM = Problem.model_validate({"problem_id": "p1", "request_id": "r1", "claim_id": "c1", "query": "entailment",
                                  "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}],
                                  "premises": [{"id": "P1", "expr": {"op": "gt", "left": V("x"), "right": V("y")},
                                                "grounding": {"kind": "task_setting", "verified": True}}],
                                  "conclusion": {"id": "C", "expr": {"op": "ge", "left": V("x"), "right": V("y")}}})


def signed() -> VerificationResult:
    r = verify(PROBLEM, CFG, signing_key=KEY, key_id="kid1")
    assert r.status is S.ENTAILED and verify_signature(r, KEY)
    return r


# ============================================================================ security-1


FORGED = {"non-ASCII": "é" * 64, "lone surrogates": "\ud83d" * 64, "upper-case hex": "A" * 64, "63 hex digits": "0" * 63,
          "65 hex digits": "0" * 65, "white space": " " * 64, "empty": "", "a number": 12345, "a list": ["0" * 64]}


@pytest.mark.parametrize("name", sorted(FORGED))
def test_a_malformed_signature_is_not_authentic_and_nothing_raises(name: str):
    forged = signed().model_copy(update={"signature": FORGED[name]})
    assert verify_signature(forged, KEY) is False
    check = release_check(forged, PROBLEM, signing_key=KEY, key_id="kid1")
    assert not check.eligible and any(r.startswith("unauthenticated") for r in check.reasons)
    findings = check_result_binding(forged, PROBLEM, KEY, config=CFG)
    assert "INT-STALE-002" in [f.code for f in findings]
    translation = TranslationResult(translation_id="tr", request_id="r1", report_id="rep", claim_id="c1", status="TRANSLATED", problem=PROBLEM,
                                    claim_text_sha256=sha256_text("x is at least y"), translator_version=TRANSLATOR_VERSION, policy_version=POLICY_VERSION,
                                    eligibility=EligibilityDecision(eligibility_class="QUANTITATIVE_CLAIM", eligible=True, decided_by="deterministic",
                                                                    policy_version=POLICY_VERSION), created_at="2026-10-17T00:00:00Z")
    assert display_status_for(translation, forged, KEY, "kid1") is S.INTERNAL_ERROR


@pytest.mark.parametrize("key", [None, b"", "a text key", 12345])
def test_a_key_that_is_not_bytes_verifies_nothing_and_never_raises(key):
    assert verify_signature(signed(), key) is False


def test_the_genuine_signature_still_verifies_and_a_changed_byte_does_not():
    """Control."""
    r = signed()
    assert verify_signature(r, KEY) and release_check(r, PROBLEM, signing_key=KEY, key_id="kid1").eligible
    flipped = r.signature[:-1] + ("0" if r.signature[-1] != "0" else "1")
    assert not verify_signature(r.model_copy(update={"signature": flipped}), KEY)
    assert not verify_signature(r, b"another-key-another-key-another-k")


def test_mac_matches_compares_hex_digests_as_bytes():
    digest = hashlib.sha256(b"x").hexdigest()
    assert mac_matches(digest, digest) and not mac_matches(digest, digest.upper()) and not mac_matches(digest, "é" * 64)
    assert not mac_matches(digest, None) and not mac_matches(digest, digest + "0")


# ============================================================================ security-7


def test_a_result_relabelled_to_another_key_id_no_longer_verifies():
    """The finding's reproduction: relabelling a result to another key id verified (True); now it does not, so a receiver
    that maps two key ids to one secret, or gives trust by key id, is not misled."""
    r = signed()
    assert r.signature_key_id == "kid1" and '"signature_key_id":"kid1"' in signable_text(r)
    for other in ("other", "external-prod", None):
        assert not verify_signature(r.model_copy(update={"signature_key_id": other}), KEY)


def test_a_result_of_this_build_never_verifies_in_the_form_without_the_key_id():
    """The earlier form is read only for a result this build did not produce: a current result signed without its key id
    (as an earlier build would sign it) is refused, so the relabelling cannot come back through the earlier form."""
    r = signed()
    unbound = hmac.new(KEY, legacy_signable_text(r).encode(), hashlib.sha256).hexdigest()
    assert r.versions == compute_versions() and not verify_signature(r.model_copy(update={"signature": unbound}), KEY)


@pytest.mark.parametrize("case", sorted(json.loads((DATA / "release_0_3_0_signed_results.json").read_text())))
def test_results_signed_by_earlier_releases_stay_inspectable_but_never_current(case: str):
    """Control: genuine results signed by release 0.3.0 (without the key id) still verify, as historical records, and are
    never current-policy evidence."""
    entry = json.loads((DATA / "release_0_3_0_signed_results.json").read_text())[case]
    old = VerificationResult.model_validate(entry["result"])
    assert verify_signature(old, b"upgrade-test-key-0123456789abcdef") and stale_reasons(old)
    baseline = VerificationResult.model_validate(json.loads((DATA / "release_0_2_0_baseline_signed_result.json").read_text()))
    assert verify_signature(baseline, b"probe-signing-key-0123456789012345") and stale_reasons(baseline)


def test_signing_binds_the_key_id_it_names():
    r = verify(PROBLEM, CFG)
    a, b = sign_result(r, KEY, "a"), sign_result(r, KEY, "b")
    assert a.signature != b.signature and verify_signature(a, KEY) and verify_signature(b, KEY)
    assert not verify_signature(a.model_copy(update={"signature_key_id": "b"}), KEY)


# ============================================================================ security-5 (cause outside this change)


def test_a_result_round_trips_through_an_exclude_none_dump_with_its_signature():
    r = verify(PROBLEM, SolverConfig(memory_max_mb=None), signing_key=KEY, key_id="kid1")
    again = VerificationResult.model_validate(r.model_dump(mode="json", exclude_none=True))
    assert again.solver_config.memory_max_mb is None and verify_signature(again, KEY)


def test_a_result_round_trips_through_a_full_dump_with_its_signature():
    """Control: the full dump keeps the explicit null and verifies, before and after the change above."""
    r = verify(PROBLEM, SolverConfig(memory_max_mb=None), signing_key=KEY, key_id="kid1")
    assert verify_signature(VerificationResult.model_validate(r.model_dump(mode="json")), KEY)
    default = verify(PROBLEM, SolverConfig(), signing_key=KEY, key_id="kid1")
    assert verify_signature(VerificationResult.model_validate(default.model_dump(mode="json", exclude_none=True)), KEY)


# Each dump mode alone, and the full dump. Two exclusions at once can drop a ``None`` budget and every other field, which no
# parse can tell from a default configuration's ``exclude_unset`` dump (both are ``{}``), so they are not a round trip.
@pytest.mark.parametrize("dump", [dict(exclude_defaults=True), dict(exclude_unset=True), dict(exclude_none=True), {}])
@pytest.mark.parametrize("config", [SolverConfig(), SolverConfig(memory_max_mb=None), SolverConfig(timeout_ms=5000), SolverConfig(timeout_ms=5000, memory_max_mb=1024)])
def test_a_genuine_result_verifies_after_every_dump_mode(dump, config):
    """Repair round 1, re-run review security-5 variant: a default configuration dumped with ``exclude_defaults`` lost its
    512 MB budget, which the parse read as ``None``, so a genuine result read as forged. An absent budget is ``None`` only
    in a dump that writes every never-``None`` field of the configuration; every dump mode of every configuration verifies."""
    r = verify(PROBLEM, config, signing_key=KEY, key_id="kid1")
    again = VerificationResult.model_validate(r.model_dump(mode="json", **dump))
    assert again.solver_config == r.solver_config and verify_signature(again, KEY)


def test_clean_control_a_changed_budget_still_reads_as_forged():
    r = verify(PROBLEM, SolverConfig(), signing_key=KEY, key_id="kid1")
    data = r.model_dump(mode="json", exclude_defaults=True)
    data["solver_config"] = {**data.get("solver_config", {}), "memory_max_mb": 1024}
    assert not verify_signature(VerificationResult.model_validate(data), KEY)


def test_composing_with_a_forged_signature_names_it_and_never_raises():
    """security-1 through the composer: the outcome shows INTERNAL_ERROR with E501."""
    from epinoic_logic.translate.contracts import ClaimRecord

    claim = ClaimRecord(request_id="r1", task_id="t", report_id="rep", agent_id="a", subject="Mathematics", task_type="algebra", claim_id="c1",
                        claim_text="x is at least y", claim_role="quantitative")
    translation = TranslationResult(translation_id="tr", request_id="r1", report_id="rep", claim_id="c1", status="TRANSLATED", problem=PROBLEM,
                                    claim_text_sha256=sha256_text(claim.claim_text), translator_version=TRANSLATOR_VERSION, policy_version=POLICY_VERSION,
                                    eligibility=EligibilityDecision(eligibility_class="QUANTITATIVE_CLAIM", eligible=True, decided_by="deterministic",
                                                                    policy_version=POLICY_VERSION), created_at="2026-10-17T00:00:00Z")
    forged = signed().model_copy(update={"signature": "é" * 64})
    outcome = compose_outcome(claim, translation, forged, signing_key=KEY, key_id="kid1")
    assert outcome.display_status is S.INTERNAL_ERROR and "E501" in outcome.summary and not outcome.release.permitted
