"""Shared helpers of the evidence-family tests: deliver a development case (``tests/data/argdiag_dev_cases.json``) through the
hub as production runs it, the claims translated by the real translator from the case's recorded proposals (served by the
fixture provider, so every proposal passes the untrusted-data path: parsing, schema and policy validation, grounding
checks), decided by the engine and composed with their diagnosis, and read the receipt's named diagnostics. Nothing from a
case is executed."""
from __future__ import annotations

import json
import re
from typing import Iterable, Optional

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.named import SUCCESS_WORDS, NamedDiagnostic, effective_severity
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

from . import argdiag_cases as C

KEY = b"evidence-family-tests-engine-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def verify_fn(case: dict):
    """The channel's claim verifier for ``case``: its recorded proposal for the claim, a fixture reviewer returning the case's
    fidelity verdict, the task record the channel passes."""
    def fn(claim, report, task=None):
        text = C.proposal_text(case, claim)
        if text is None:
            return None
        translator = Translator(FixtureTranslationProvider({claim.claim_id: text}))
        verdict = json.dumps({"verdict": case.get("fidelity_review", "faithful"), "issues": []})
        reviewer = SemanticReviewer(FixtureReviewProvider({claim.claim_id: verdict}))
        return verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, key_id="channel", task=task)
    return fn


def deliver(case_or_id, delivery: str = "report"):
    """``(case, receipt)``: the case's answer delivered as its structured report (``report``) or as raw text (``text``)."""
    case = C.load_case(case_or_id) if isinstance(case_or_id, str) else case_or_id
    plan = WorkPlan(**C.work_plan_fields(case))
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG)
    ch = hub.open_task(plan)
    ch.verify_claim_fn = verify_fn(case)
    message, _request, request_receipt = hub.dispatch(plan.task_id, case["agent_id"], case["request"], C.supplied_texts(case))
    assert message is not None, [f.code for f in request_receipt.findings]
    if delivery == "report":
        _reply, receipt = hub.receive(plan.task_id, message.message_id, C.structured_report(case))
    else:
        report_id = (case.get("ids") or {}).get("report_id", f"rep-{case['id']}")
        _reply, receipt = hub.receive(plan.task_id, message.message_id, case["answer"], agent_id=case["agent_id"], report_id=report_id)
    return case, receipt


def diagnostics(receipt, code: Optional[str] = None, prefix: Optional[str] = None) -> list[NamedDiagnostic]:
    """Every named diagnostic of ``receipt``: its own list and each outcome's (deduplicated by code, claims and assertions)."""
    seen: dict[tuple, NamedDiagnostic] = {}
    for d in [*receipt.named_diagnostics, *(d for o in receipt.outcomes for d in o.named_diagnostics)]:
        seen.setdefault((d.code, tuple(d.claim_ids), tuple(d.assertion_ids)), d)
    out = list(seen.values())
    if code is not None:
        out = [d for d in out if d.code == code]
    if prefix is not None:
        out = [d for d in out if d.code.startswith(prefix)]
    return out


def blocking(diags: Iterable[NamedDiagnostic]) -> list[NamedDiagnostic]:
    """The diagnostics shown at warning or error (by their displayed severity)."""
    return [d for d in diags if d.severity in ("warning", "error")]


def outcome(receipt, claim_id: str):
    return next(o for o in receipt.outcomes if o.claim_id == claim_id)


def failed_groundings(receipt) -> list:
    """Every grounding check a check in this process refuted, over all the receipt's outcomes."""
    return [c for o in receipt.outcomes for c in o.translation.grounding_checks if c.verified is False]


def assert_message_hygiene(diags: Iterable[NamedDiagnostic]) -> None:
    """No success word in a message, and "verified" only in "a check verified" / "no check verified" (the contract's rule
    for every diagnosis text)."""
    for d in diags:
        words = set(re.findall(r"[a-z]+", d.message.casefold()))
        assert not (words & set(SUCCESS_WORDS)), d.message
        rest = d.message.casefold().replace("a check verified", "").replace("no check verified", "")
        assert "verified" not in rest, d.message


__all__ = ["KEY", "CFG", "verify_fn", "deliver", "diagnostics", "blocking", "outcome", "failed_groundings", "assert_message_hygiene",
           "effective_severity"]
