"""A claim the translation read as ambiguous, or one the encoding cannot express, has no verdict a clean receipt could stand
on (repair round 1, re-run review correctness-2 variant): the receipt is ACCEPTED_WITH_FINDINGS and its summary names the
claim, as for an engine non-result, an invalid or vacuous encoding or a refused result. The engine status of the chosen
reading of an ambiguous claim is never the claim's verdict. Control: a trusted verdict still leaves a clean receipt."""
from __future__ import annotations

import pytest

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

KEY = b"receipt-no-verdict-key-0123456789ab"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
ACC, AWF = TransmissionStatus.ACCEPTED, TransmissionStatus.ACCEPTED_WITH_FINDINGS


def _V(n: str) -> dict:
    return {"op": "var", "name": n}


def _I(v: int) -> dict:
    return {"op": "int", "value": str(v)}


def _receipt(mode: str):
    symbols = [{"name": "x", "sort": "Int"}]
    premises = [{"id": "P1", "expr": {"op": "eq", "left": _V("x"), "right": _I(5)}, "label": "x is 5"}]
    if mode == "unsupported":  # a product of two unknowns: outside the linear fragment the encoding supports
        symbols.append({"name": "y", "sort": "Int"})
        premises.append({"id": "P2", "expr": {"op": "eq", "left": {"op": "mul", "args": [_V("x"), _V("y")]}, "right": _I(10)}, "label": "xy is 10"})
    problem = {"ir_version": "1.0", "problem_id": "p", "request_id": "req-9", "claim_id": "m1", "query": "entailment", "symbols": symbols,
               "premises": premises, "conclusion": {"id": "C", "expr": {"op": "gt", "left": _V("x"), "right": _I(3)}, "label": "x is more than 3"}}
    answer = {"problem": problem, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []},
              "ambiguous": mode == "ambiguous", "unsupported_reason": None}
    provider = FixtureTranslationProvider({"m1": [answer, answer]})

    def fn(claim, report, task=None):
        return verify_claim(claim, report, Translator(provider, config=CFG), config=CFG, signing_key=KEY, key_id="t", task=task)

    plan = WorkPlan(plan_id="pl", request_id="req-9", task_id="task-9", subject="Mathematics", task_type="problem", selected_agent_ids=["math-specialist"])
    ch = TranslatorChannel(plan, signing_key=KEY, verify_claim_fn=fn)
    msg, _req, _ = ch.request("router", "math-specialist", "Show that x is more than 3 when x is 5.", [])
    text = "Since x is 5, x is more than 3."
    rep = SpecialistReport(report_id="rep", request_id="req-9", task_id="task-9", agent_id="math-specialist", subject="Mathematics", task_type="problem",
                           original_response=text, response_sha256=sha256_text(text), supplied_texts=[], created_at="2026-10-11T11:00:00Z",
                           claims=[ClaimRecord(request_id="req-9", task_id="task-9", report_id="rep", agent_id="math-specialist", subject="Mathematics",
                                               task_type="problem", claim_id="m1", claim_text=text, claim_role="quantitative", proposed_claim_kind="arithmetic")])
    return ch.respond(msg.message_id, rep)[1]


@pytest.mark.parametrize("mode, display", [("ambiguous", "AMBIGUOUS_TRANSLATION"), ("unsupported", "UNSUPPORTED")])
def test_an_ambiguous_or_unsupported_claim_never_leaves_a_clean_receipt(mode, display):
    rc = _receipt(mode)
    assert [o.display_status.value for o in rc.outcomes] == [display]
    assert rc.status is AWF and "No verdict a clean receipt could stand on for claim(s) m1" in rc.summary
    if mode == "ambiguous":  # the chosen reading was run and entailed: that is still no verdict on the claim
        assert [o.verification.status.value for o in rc.outcomes if o.verification is not None] == ["ENTAILED"]


def test_clean_control_a_trusted_verdict_leaves_a_clean_receipt():
    rc = _receipt("entailed")
    assert [o.display_status.value for o in rc.outcomes] == ["ENTAILED"] and rc.status is ACC and not rc.findings
    assert "No verdict" not in rc.summary
