"""Repair round 3, INV-6: a signature in the earlier build's form never attests a key id.

Earlier builds signed a result's content without its ``signature_key_id``. That form is still read, for a result this build
did not produce, so a historical record stays inspectable; but relabelled to another key id it still verified, so a
receiver that trusts by key id could be misled about who issued it. :func:`signature_form` now tells the two forms apart,
:func:`verify_signature` with a ``key_id`` accepts only the form that covers the id, the release rule names the id as not
attested, and the service answers ``key_id_attested: false`` for such a record. A result of this build (the bound form)
verifies against its key id and against no other."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine.provenance import FORM_BOUND, FORM_LEGACY, signature_form, stale_reasons, verify_signature
from epinoic_logic.engine.release import release_check
from epinoic_logic.engine.results import SolverConfig, VerificationResult
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem

DATA = Path(__file__).parent / "data"
LEGACY_KEY = b"upgrade-test-key-0123456789abcdef"
KEY = b"repair-round3-signature-key-0123456"


def _legacy(case: str = "trusted_kind_chain") -> tuple[VerificationResult, Problem]:
    entry = json.loads((DATA / "release_0_3_0_signed_results.json").read_text())[case]
    return VerificationResult.model_validate(entry["result"]), Problem.model_validate(entry["problem"])


def test_a_legacy_record_is_inspectable_but_attests_no_key_id():
    old, _problem = _legacy()
    assert old.signature_key_id == "upgrade" and stale_reasons(old)
    assert signature_form(old, LEGACY_KEY) == FORM_LEGACY
    assert verify_signature(old, LEGACY_KEY)                                  # inspectable without a key id
    assert not verify_signature(old, LEGACY_KEY, key_id="upgrade")            # never against a key id, even the one it names
    relabelled = old.model_copy(update={"signature_key_id": "other"})
    assert signature_form(relabelled, LEGACY_KEY) == FORM_LEGACY              # the relabel is invisible to the earlier form ...
    assert not verify_signature(relabelled, LEGACY_KEY, key_id="other")       # ... so a receiver trusting 'other' refuses it


@pytest.mark.parametrize("key_id", ["upgrade", "other"])
def test_the_release_rule_names_the_key_id_of_a_legacy_record_as_not_attested(key_id):
    old, problem = _legacy()
    record = old.model_copy(update={"signature_key_id": key_id})
    check = release_check(record, problem, signing_key=LEGACY_KEY, key_id=key_id)
    assert not check.eligible
    assert any(r.startswith("key id not attested") and repr(key_id) in r for r in check.reasons)
    assert any(r.startswith("stale:") for r in check.reasons)
    # without a key id to trust, nothing is said about one
    assert not any(r.startswith("key id not attested") for r in release_check(record, problem, signing_key=LEGACY_KEY).reasons)


def test_control_a_result_of_this_build_verifies_against_its_own_key_id_only():
    problem = Problem.model_validate({
        "problem_id": "p1", "request_id": "r1", "claim_id": "c1", "query": "entailment",
        "symbols": [{"name": "x", "sort": "Int"}],
        "premises": [{"id": "P1", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "2"}},
                      "grounding": {"kind": "task_setting", "verified": True}}],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "1"}}}})
    r = verify(problem, SolverConfig(timeout_ms=4000, memory_max_mb=None), signing_key=KEY, key_id="kid1")
    assert signature_form(r, KEY) == FORM_BOUND
    assert verify_signature(r, KEY) and verify_signature(r, KEY, key_id="kid1")
    assert not verify_signature(r, KEY, key_id="kid2")                                       # another id it does not name
    assert signature_form(r.model_copy(update={"signature_key_id": "kid2"}), KEY) is None    # relabelled: no valid signature
    check = release_check(r, problem, signing_key=KEY, key_id="kid1")
    assert check.eligible and not any(x.startswith("key id not attested") for x in check.reasons)


def test_signature_form_never_raises_and_reads_no_signature_as_none():
    old, _problem = _legacy()
    assert signature_form(old, b"") is None and signature_form(old, "text-key") is None   # type: ignore[arg-type]
    assert signature_form(old.model_copy(update={"signature": "é" * 64}), LEGACY_KEY) is None
    assert signature_form(old.model_copy(update={"signature": None}), LEGACY_KEY) is None
