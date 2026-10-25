"""E2E B13: the response gate (``channel.gate.assess_response``) decides what the student is shown from the receipts.

The end-to-end judge found the answers of ll-e1, sp-e1, lit-e1, ec-e1 and ps-e1 correct, yet the run's gate withheld
them: false findings (the word bounds of B4 and B19, sp's corrected forms read as quotations, ec's pair-direction check,
ps's counterexamples from dropped links) and a synthesis no request could deliver. Once the false findings are gone each
is delivered labelled "not verified", and on the fast path (a plan with no combinator) no synthesis is required.

ll and lit are clean on this tree. The other three still carry false findings that other parts of the repair remove
(sp's B5 quotations, ec's pair-direction check, ps's B8 counterexamples): the tests take exactly those out of the receipts
before the gate, so on a tree where they are already gone the removal changes nothing, and they check that the gate fails
nothing else on the receipts as they stand."""
from __future__ import annotations

import math

import pytest

from epinoic_logic import named as N
from epinoic_logic.channel.contracts import TransmissionStatus
from epinoic_logic.channel.gate import DEFAULT_THRESHOLD, POSITIVE_DISPLAYS, assess_response
from epinoic_logic.engine.statuses import VerificationStatus as S

from ..argdiag_cases import case_ids
from .dev_case_hub import run_case


def gate(run, **kw):
    kw.setdefault("synthesis_required", False)
    return assess_response(run.receipts, **kw)


def _failed(g):
    return [c for c in g.checks if c.result == "failed"]


# ------------------------------------------------------------------ the E2E decisions

def _without(receipt, *, codes=(), claims=(), displays=()):
    """``receipt`` without the findings of ``codes`` on ``claims`` and with the outcomes of ``claims`` displayed as
    ``displays[0]`` instead of a negative verdict: exactly the false findings another part of the repair removes."""
    keep = [f for f in receipt.findings if not (f.code in codes and set(f.claim_ids) & set(claims))]
    named = [d for d in receipt.named_diagnostics if not (d.code in codes and set(d.claim_ids) & set(claims))]
    outcomes = [o.model_copy(update={"display_status": displays[0]}) if displays and o.claim_id in claims and o.display_status in (S.COUNTEREXAMPLE,) else o
                for o in receipt.outcomes]
    checks = [fc.model_copy(update={"satisfied": True}) if "INT-SUBJ-001" in codes and fc.satisfied is False and set(fc.claim_ids) & set(claims) else fc
              for fc in receipt.formal_checks]
    return receipt.model_copy(update={"findings": keep, "named_diagnostics": named, "outcomes": outcomes, "formal_checks": checks})


SP_CORRECTIONS = [f"g7.{k}@language-b-spanish-specialist" for k in range(2, 7)] + ["g8.1@language-b-spanish-specialist"]
EC_PAIR = ["g5.2@economics-specialist", "g7.1@economics-specialist"]
PS_DROPPED_LINKS = [f"{c}@psychology-specialist" for c in ("g2.1", "g3.1", "g6.5", "g6.7", "g7.1", "g8.1")]


def test_the_fast_path_needs_no_synthesis():
    run = run_case("e2e-B13-lit")
    fast = gate(run)
    synth = next(c for c in fast.checks if c.rule == "synthesis")
    assert synth.result == "not_required" and fast.display_status == "DELIVERED_UNVERIFIED"
    routed = gate(run, synthesis_required=True)                        # a plan that routes to a combinator, no synthesis
    assert [c.check for c in _failed(routed)] == ["combinator synthesis"] and routed.display_status == "WITHHELD"


def test_a_synthesis_receipt_is_read_only_when_one_is_required():
    run = run_case("e2e-B13-lit")
    rejected = run.receipt.model_copy(update={"status": TransmissionStatus.REJECTED, "receipt_id": "synthesis-receipt"})
    assert gate(run, synthesis_receipt=rejected).display_status == "DELIVERED_UNVERIFIED"         # fast path: not read
    routed = gate(run, synthesis_required=True, synthesis_receipt=rejected)
    assert routed.display_status == "WITHHELD" and any(c.receipt_id == "synthesis-receipt" and c.result == "failed" for c in routed.checks)


# ------------------------------------------------------------------ controls

def test_a_counterexample_answer_is_withheld():
    g = gate(run_case("f01_non_sequitur"))
    assert g.display_status == "WITHHELD" and not g.delivered
    assert [c.display_status for c in _failed(g)] == ["COUNTEREXAMPLE"]


@pytest.fixture()
def verified_run():
    """A control's receipt with only its engine-verified claim: every required check passes (the VERIFIED baseline).

    Ported onto the integrated translator: the baseline is i00 (a valid stated rule), not c01, whose year-led table
    entries this tree's year-of-figure grounding rule refutes (docs/ARGUMENT_DIAGNOSTICS.md, section 20, defect P-1)."""
    run = run_case("i00_control_valid_rule")
    keep = [o for o in run.receipt.outcomes if o.display_status in POSITIVE_DISPLAYS]
    assert len(keep) == 1
    run.receipt = run.receipt.model_copy(update={"outcomes": keep})
    g = gate(run)
    assert g.display_status == "VERIFIED" and g.label == "verified" and g.failed == g.unresolved == 0
    return run


def _with_outcome(run, **update):
    o = run.receipt.outcomes[0]
    run.receipt = run.receipt.model_copy(update={"outcomes": [o.model_copy(update=update)]})
    return gate(run)


def test_an_entailed_claim_resting_on_an_unestablished_premise_is_never_verified(verified_run):
    o = verified_run.receipt.outcomes[0]
    for field in ("ungrounded_dependencies", "unverified_dependencies"):
        g = _with_outcome(verified_run, verification=o.verification.model_copy(update={field: ["P_any"]}))
        claim = next(c for c in g.checks if c.rule == "claim")
        assert claim.result == "unresolved" and "not established" in claim.detail
        assert g.display_status == "DELIVERED_UNVERIFIED"
        verified_run.receipt = verified_run.receipt.model_copy(update={"outcomes": [o]})


def _diagnostic(claim_id: str, severity: str = "warning"):
    return N.named_diagnostic("EVD-SRC-001", severity=severity, layer="claim", claim_ids=[claim_id], derivation="source_text",
                              message="the claim's source is the writer's own say-so")


def test_a_capped_warning_still_counts_unresolved(verified_run):
    o = verified_run.receipt.outcomes[0]
    capped = N.cap([_diagnostic(o.claim_id)], "info", "not_source_bound")[0]
    assert capped.severity == "info" and capped.capped_from == "warning"
    g = _with_outcome(verified_run, named_diagnostics=[capped])
    assert next(c for c in g.checks if c.rule == "claim").result == "unresolved" and g.display_status == "DELIVERED_UNVERIFIED"


def test_an_info_diagnostic_that_was_never_capped_leaves_the_claim_passed(verified_run):
    o = verified_run.receipt.outcomes[0]
    g = _with_outcome(verified_run, named_diagnostics=[N.named_diagnostic("EVD-SRC-004", severity="info", layer="claim", claim_ids=[o.claim_id],
                                                                          derivation="source_text", message="noted")])
    assert g.display_status == "VERIFIED"


def test_a_refused_release_leaves_the_claim_unresolved(verified_run):
    o = verified_run.receipt.outcomes[0]
    g = _with_outcome(verified_run, release=o.release.model_copy(update={"permitted": False, "unresolved": ["no semantic-fidelity review"]}))
    assert next(c for c in g.checks if c.rule == "claim").result == "unresolved" and g.display_status == "DELIVERED_UNVERIFIED"


def test_a_negative_display_fails_the_answer(verified_run):
    g = _with_outcome(verified_run, display_status=S.COUNTEREXAMPLE)
    assert next(c for c in g.checks if c.rule == "claim").result == "failed" and g.display_status == "WITHHELD"


def test_an_answer_with_no_formal_check_is_never_verified(verified_run):
    verified_run.receipt = verified_run.receipt.model_copy(update={"outcomes": [], "formal_checks": []})
    g = gate(verified_run)
    assert g.failed == g.unresolved == 0 and g.display_status == "DELIVERED_UNVERIFIED"
    assert "no claim or statement of the answer was verified by the engine" in g.reasons


@pytest.mark.parametrize("code, severity, result", [
    ("ES-STR-001", "error", "unresolved"), ("CORE-QNT-001", "warning", "unresolved"),
    ("INT-XENC-001", "warning", "unresolved"), ("INT-ARG-001", "error", "unresolved"), ("INT-INTERNAL-001", "error", "unresolved"),
    ("INT-REQ-003", "error", "failed"), ("CORE-SRC-005", "error", "failed"), ("INT-REQ-017", "warning", "unresolved"),
])
def test_findings_are_classified_by_what_they_establish(verified_run, code, severity, result):
    from epinoic_logic.integrity.contracts import IntegrityFinding
    f = IntegrityFinding(code=code, severity=severity, message="m", claim_ids=["x"])
    verified_run.receipt = verified_run.receipt.model_copy(update={"findings": list(verified_run.receipt.findings) + [f]})
    g = gate(verified_run)
    assert next(c for c in g.checks if c.code == code).result == result
    assert g.display_status != "VERIFIED"


def test_a_coverage_or_constraint_finding_restates_its_record_and_is_not_counted_twice():
    run = run_case("e2e-B4-en")                                        # c3 "ONE paragraph": a constraint record and its INT-REQ-005
    g = gate(run)
    assert [f for f in run.receipt.findings if f.code == "INT-REQ-005"]
    assert not [c for c in g.checks if c.code in ("INT-REQ-004", "INT-REQ-005")]
    assert [c for c in g.checks if c.rule == "constraint" and c.result == "failed"]


#: The heuristic notes e2e-B16-hi's peer arrival leaves unresolved (a correct Mathematics answer), with their counts: pinned exactly.
B16_ARRIVAL_NOTES = sorted(["CORE-QNT-001"] + ["ST-PARSE-001"] * 2 + ["ST-UNDEC-001"] * 5)


# ------------------------------------------------------------------ never raises, fails closed, invariants

@pytest.mark.parametrize("receipts, kw", [
    (None, {}), ([], {}), ([1, 2], {}), ("receipts", {}), (object(), {}),
    ("ok", {"threshold": 2.0}), ("ok", {"threshold": -0.1}), ("ok", {"threshold": math.nan}), ("ok", {"threshold": "high"}), ("ok", {"threshold": True}),
    ("ok", {"synthesis_required": "yes"}), ("ok", {"synthesis_receipt": "not a receipt", "synthesis_required": True}),
])
def test_the_gate_never_raises_and_fails_closed(receipts, kw):
    if receipts == "ok":
        receipts = run_case("e2e-B13-ll").receipts
    kw.setdefault("synthesis_required", False)
    g = assess_response(receipts, **kw)
    assert g.display_status == "WITHHELD" and not g.delivered and g.reasons and g.label.startswith("withheld: ")
    assert all(g.invariants().values())


def test_a_rejected_answer_is_withheld():
    run = run_case("e2e-B13-ll")
    rejected = run.receipt.model_copy(update={"status": TransmissionStatus.REJECTED, "outcomes": [], "coverage": [], "constraint_results": []})
    g = assess_response([rejected], synthesis_required=False)
    assert g.display_status == "WITHHELD" and not g.answer_available and [c.rule for c in _failed(g)] == ["delivery"]


@pytest.mark.parametrize("case_id", case_ids())
def test_the_invariants_hold_on_every_development_case(case_id):
    run = run_case(case_id)
    for kw in ({"synthesis_required": False}, {"synthesis_required": True}, {"synthesis_required": False, "threshold": 0.0},
               {"synthesis_required": False, "threshold": 1.0}):
        g = assess_response(run.receipts, **kw)
        inv = g.invariants()
        assert all(inv.values()), (kw, [k for k, ok in inv.items() if not ok])
        assert g.threshold == kw.get("threshold", DEFAULT_THRESHOLD)
        if g.display_status == "VERIFIED":
            assert g.failed == g.unresolved == 0
        if g.display_status == "DELIVERED_UNVERIFIED":
            assert g.label == "not verified" and "checked" not in g.label and g.accuracy > g.threshold
        for c in g.checks:
            if c.rule == "claim" and c.result == "passed":
                assert c.display_status in {s.value for s in POSITIVE_DISPLAYS}
