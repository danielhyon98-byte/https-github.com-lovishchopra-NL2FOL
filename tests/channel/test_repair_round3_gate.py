"""Repair round 3, INV-7: the response gate never reads an undiagnosed claim as passed. A positive display passes only
when the engine's argument diagnosis ran to the end on its result (``argument_rules`` is the rule version), no claim or
report rule of the outcome is incomplete and a release assessment was made and permits release. An outcome built outside
the composer (no release, no diagnosis) is unresolved.

Ported onto the integrated translator without the round's ADV3-02 half (a finding carried from an earlier receipt,
INT-HIST-001): this tree's channel carries no relay history, so those tests are not ported (docs/ARGUMENT_DIAGNOSTICS.md,
section "Port onto the integrated translator")."""
from __future__ import annotations

import pytest

from epinoic_logic.channel.gate import POSITIVE_DISPLAYS, assess_response

from .dev_case_hub import run_case


# ------------------------------------------------------------------ INV-7: a diagnosis not computed is never "none found"

@pytest.fixture()
def verified_run():
    # ported: the feature line used c01_control_econ_table; on this tree its table excerpt for another year is refuted by
    # the integrated grounding (another year's figure), so the clean control whose single outcome is VERIFIED is i00
    run = run_case("i00_control_valid_rule")
    keep = [o for o in run.receipt.outcomes if o.display_status in POSITIVE_DISPLAYS]
    assert len(keep) == 1
    run.receipt = run.receipt.model_copy(update={"outcomes": keep})
    g = assess_response(run.receipts, synthesis_required=False)
    assert g.display_status == "VERIFIED" and g.failed == g.unresolved == 0
    return run


def _claim_check(run, **update):
    o = run.receipt.outcomes[0]
    run.receipt = run.receipt.model_copy(update={"outcomes": [o.model_copy(update=update)]})
    g = assess_response(run.receipts, synthesis_required=False)
    return g, next(c for c in g.checks if c.rule == "claim")


def test_an_outcome_with_no_release_assessment_is_unresolved(verified_run):
    g, c = _claim_check(verified_run, release=None)
    assert c.result == "unresolved" and "no release assessment" in c.detail and g.display_status != "VERIFIED"


def test_an_outcome_whose_engine_diagnosis_was_not_computed_is_unresolved(verified_run):
    v = verified_run.receipt.outcomes[0].verification
    g, c = _claim_check(verified_run, verification=v.model_copy(update={"argument_rules": None}))
    assert c.result == "unresolved" and "not computed" in c.detail and g.display_status != "VERIFIED"
    g, c = _claim_check(verified_run, verification=v.model_copy(update={"argument_rules": "argdiag-2/incomplete:budget_exhausted"}))
    assert c.result == "unresolved" and g.display_status != "VERIFIED"


def test_an_outcome_whose_claim_rules_did_not_finish_is_unresolved(verified_run):
    g, c = _claim_check(verified_run, diagnosis_incomplete=["EVD-SRC-001 raised"])
    assert c.result == "unresolved" and "incomplete" in c.detail and g.display_status != "VERIFIED"

