"""T18 for the translator's claim display (meaning-check design 2.4 O4, 2.5.7; stage 2a, interface (d)).

A claim the meaning label names (INT-SELF-001 on its receipt) whose engine result would be shown as a success is shown
NOT_ELIGIBLE with the self-report withheld, on ``claim_display_status``, on ``compose_outcome`` and on ``withhold_labelled`` (the
channel's recomposition of a receipt outcome); a non-success status (COUNTEREXAMPLE, UNKNOWN, a translation non-result) is
returned as it is, never changed or raised. Expected values are fixed here.
"""
from __future__ import annotations

import pytest

from epinoic_logic.engine import SolverConfig, VerificationStatus as S, verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import (ClaimRecord, EligibilityClass, EligibilityDecision, TranslationResult, TranslationStatus)
from epinoic_logic.translate.outcome import (STATUS_MEANING, WITHHELD_SELF_REPORT_MEANING, claim_display_status, compose_outcome,
                                             withhold_labelled)

CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
KEY = b"labelled-display-key-0123456789abc"


def _claim(cid="c-1", text="The speed is 15 m/s."):
    return ClaimRecord(request_id="req-t18", task_id="task-t18", report_id="rep-t18", agent_id="physics-specialist", subject="Physics",
                       task_type="short_answer", claim_id=cid, claim_text=text, claim_role="quantitative", proposed_claim_kind="arithmetic")


def _problem(cid: str, given: int, concluded: int) -> Problem:
    V = {"op": "var", "name": "speed"}
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-t18", "claim_id": cid, "query": "entailment",
                                   "symbols": [{"name": "speed", "sort": "Real"}],
                                   "premises": [{"id": "GIVEN", "expr": {"op": "eq", "left": V, "right": {"op": "real", "value": str(given)}},
                                                 "grounding": {"kind": "arithmetic_fact", "verified": True}}],
                                   "conclusion": {"id": "C", "expr": {"op": "eq", "left": V, "right": {"op": "real", "value": str(concluded)}}}})


def _translation(claim, problem=None, status=TranslationStatus.TRANSLATED):
    return TranslationResult(translation_id=f"tr-{claim.claim_id}", claim_id=claim.claim_id, request_id=claim.request_id, report_id=claim.report_id,
                             status=status, eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True,
                                                                            decided_by="deterministic", policy_version="t"),
                             problem=problem, translator_version="t", policy_version="t", created_at="2026-11-26T10:00:00Z")


def _case(given: int, concluded: int):
    claim = _claim()
    problem = _problem(claim.claim_id, given, concluded)
    return claim, _translation(claim, problem), verify(problem, CFG, signing_key=KEY, key_id="t")


def test_a_labelled_success_is_not_eligible_and_withheld():
    claim, tr, res = _case(15, 15)
    assert res.status is S.ENTAILED
    assert claim_display_status(claim, tr, res, KEY, "t") == (S.ENTAILED, False)
    assert claim_display_status(claim, tr, res, KEY, "t", labelled_self_report=True) == (S.NOT_ELIGIBLE, True)


@pytest.mark.parametrize("status", [S.COUNTEREXAMPLE, S.UNKNOWN])
def test_a_labelled_non_success_is_never_changed(status):
    claim, tr, res = _case(15, 16) if status is S.COUNTEREXAMPLE else _case(15, 15)
    if status is S.UNKNOWN:
        res = res.model_copy(update={"status": S.UNKNOWN})
        assert claim_display_status(claim, tr, res, labelled_self_report=True) == (S.UNKNOWN, False)
        return
    assert res.status is S.COUNTEREXAMPLE
    assert claim_display_status(claim, tr, res, KEY, "t", labelled_self_report=True) == (S.COUNTEREXAMPLE, False)


def test_a_labelled_translation_non_result_is_never_changed():
    claim = _claim()
    tr = _translation(claim, None, TranslationStatus.UNSUPPORTED)
    assert claim_display_status(claim, tr, None, labelled_self_report=True) == (S.UNSUPPORTED, False)


def test_compose_outcome_withholds_a_labelled_success():
    claim, tr, res = _case(15, 15)
    plain = compose_outcome(claim, tr, res, signing_key=KEY, key_id="t")
    labelled = compose_outcome(claim, tr, res, signing_key=KEY, key_id="t", labelled_self_report=True)
    assert plain.display_status is S.ENTAILED and STATUS_MEANING[S.ENTAILED] in plain.summary
    assert labelled.display_status is S.NOT_ELIGIBLE and WITHHELD_SELF_REPORT_MEANING in labelled.summary
    assert labelled.verification == plain.verification  # the signed engine result is kept as it is, never shown as a verdict


def test_withhold_labelled_keeps_the_outcome_id_and_never_raises_a_status():
    claim, tr, res = _case(15, 15)
    out = compose_outcome(claim, tr, res, signing_key=KEY, key_id="t")
    held = withhold_labelled(out, claim, signing_key=KEY, key_id="t")
    assert (held.display_status, held.outcome_id, held.created_at) == (S.NOT_ELIGIBLE, out.outcome_id, out.created_at)
    assert WITHHELD_SELF_REPORT_MEANING in held.summary
    claim2, tr2, res2 = _case(15, 16)
    refuted = compose_outcome(claim2, tr2, res2, signing_key=KEY, key_id="t")
    assert refuted.display_status is S.COUNTEREXAMPLE and withhold_labelled(refuted, claim2) is refuted
    with pytest.raises(ValueError):
        withhold_labelled(out, _claim("c-2"), signing_key=KEY, key_id="t")
