"""Run a development case (``tests/data/argdiag_dev_cases.json``) the way production runs an answer, for the tests of the
argument rules (rules argdiag-1).

* :func:`run_case` opens a ``RouterHub`` task on the case's work plan, dispatches its request through the channel and
  delivers its answer as raw text (the subject branch's own parser makes the claims) or as the case's structured report.
  Every claim the channel hands to its verifier is translated by the real ``Translator`` from the case's recorded proposal
  (a fixture provider serves it as the untrusted JSON text a model would return), verified by the engine, reviewed by a
  fixture reviewer and composed into its outcome. A case's peers are delivered first and, when the case says so, relayed
  to the answering specialist as a supplied text.
* :func:`grounded` returns one claim's translation (the problem after the grounding checks set its ``verified`` flags)
  and the delivered report, without the receipt.

Nothing in a case is executed: proposals are JSON data passed to the translator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, ClaimVerificationOutcome, SpecialistReport, SuppliedText, TranslationResult
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

from . import argdiag_cases as C

__all__ = ["KEY", "CFG", "CaseRun", "run_case", "grounded"]

KEY = b"argdiag-rules-test-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


@dataclass
class CaseRun:
    """One delivery: the receipt, the delivered report and the outcome of every claim the channel verified."""
    receipt: object
    report: Optional[SpecialistReport]
    outcomes: dict[str, ClaimVerificationOutcome] = field(default_factory=dict)

    def claim(self, contains: str) -> ClaimRecord:
        """The delivered claim whose text contains ``contains``."""
        [found] = [c for c in self.report.claims if contains in c.claim_text]
        return found

    def outcome(self, contains: str) -> ClaimVerificationOutcome:
        return self.outcomes[self.claim(contains).claim_id]


def _verifier(case: dict, served: dict):
    fidelity = case.get("fidelity_review", "faithful")

    def verify_fn(claim, report, task=None):
        text = C.proposal_text(case, claim)
        if text is None:
            return None
        translator = Translator(FixtureTranslationProvider({claim.claim_id: text}), config=CFG)
        reviewer = SemanticReviewer(FixtureReviewProvider({claim.claim_id: json.dumps({"verdict": fidelity, "issues": []})}))
        out = verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, key_id="channel", task=task)
        served[claim.claim_id] = out
        return out
    return verify_fn


def run_case(case_id: str, mode: str = "text") -> CaseRun:
    """Deliver the case's answer in ``mode`` (a mode name of the case: its delivery is ``text`` or ``report``)."""
    case = C.load_case(case_id)
    [spec] = [m for m in case["modes"] if m["name"] == mode]
    docs = C.supplied_texts(case)
    plan = WorkPlan(**C.work_plan_fields(case))
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG)
    ch = hub.open_task(plan)
    task = plan.task_id
    extra: list[SuppliedText] = []
    for peer in case.get("peers", []):
        served_peer: dict = {}
        ch.verify_claim_fn = _verifier({**peer, "translations": peer.get("translations", [])}, served_peer)
        pdocs = [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"]) for t in peer.get("supplied_texts", [])]
        m, _req, _rq = hub.dispatch(task, peer["agent_id"], peer["request"], pdocs)
        reply, _prc = hub.receive(task, m.message_id, peer["answer"], agent_id=peer["agent_id"], report_id=peer.get("report_id", f"rep-{peer['agent_id']}"))
        if reply is not None and peer.get("relay_to_main"):
            prep = SpecialistReport.model_validate(reply.payload)
            relayed, _rr = ch.relay("router", AgentRole.ROUTER, case["agent_id"], AgentRole.SPECIALIST, prep, in_reply_to=reply.message_id)
            if relayed is not None:
                extra.append(SuppliedText(document_id=peer["peer_document_id"], title=peer.get("peer_document_title"), author=peer["agent_id"],
                                          text=peer.get("peer_document_text") or prep.original_response))
    served: dict = {}
    ch.verify_claim_fn = _verifier(case, served)
    m, _req, _rq = hub.dispatch(task, case["agent_id"], case["request"], [*docs, *extra])
    if spec["delivery"] == "report":
        reply, rc = hub.receive(task, m.message_id, C.structured_report(case))
    else:
        reply, rc = hub.receive(task, m.message_id, case["answer"], agent_id=case["agent_id"], report_id=case["ids"].get("report_id", f"rep-{case['id']}"))
    report = SpecialistReport.model_validate(reply.payload) if reply is not None else None
    return CaseRun(receipt=rc, report=report, outcomes=served)


def grounded(case_id: str, contains: str, mode: str = "text") -> tuple[TranslationResult, ClaimRecord, SpecialistReport]:
    """The translation of the delivered claim whose text contains ``contains`` (its problem grounded: every ``verified``
    flag set by the checks of this process), with the claim and the delivered report."""
    run = run_case(case_id, mode)
    claim = run.claim(contains)
    return run.outcomes[claim.claim_id].translation, claim, run.report
