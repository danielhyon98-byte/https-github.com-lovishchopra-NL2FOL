"""Run a development case (``tests/data/argdiag_dev_cases.json``) through the public pipeline, for the channel's tests.

A ``RouterHub`` is opened on the case's plan; the case's peers (if any) are asked, answer as raw text and are forwarded to
the answering specialist on the same channel, their reports supplied as ``peer:<task>`` documents; the request is
dispatched and the answer received as raw text (the subject branch's parser makes the claims) or as the case's structured
report. Every claim the channel hands to its verifier is translated by the real ``Translator`` from the case's recorded
proposal (a fixture provider, so the proposal passes the untrusted-data path: parsing, schema and policy validation,
grounding checks), decided by the engine, reviewed by a fixture reviewer that returns the case's fidelity verdict, and
composed into its outcome. Nothing from a case is executed: proposals are JSON text.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

from ..argdiag_cases import load_case, proposal_text, structured_report, supplied_texts, work_plan_fields

KEY = b"channel-dev-case-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
COMBINATOR = "combinator"


@dataclass
class CaseRun:
    case: dict
    hub: RouterHub
    channel: object
    request_receipt: object
    reply: Optional[object]
    receipt: object
    peer_receipts: list = field(default_factory=list)   # (arrival receipt, forward receipt) per peer

    @property
    def receipts(self) -> list:
        """The answer's receipts: the peers' arrivals and forwards, the request and the answer's arrival."""
        out = []
        for arrival, forward in self.peer_receipts:
            out += [r for r in (arrival, forward) if r is not None]
        return out + [self.request_receipt, self.receipt]


def verifier(case: dict, fidelity: Optional[str] = None):
    """The channel's claim verifier for ``case``: the recorded proposal of each delivered claim, translated and decided."""
    verdict = fidelity or case.get("fidelity_review", "faithful")

    def fn(claim, report, task=None):
        text = proposal_text(case, claim)
        if text is None:
            return None
        translator = Translator(FixtureTranslationProvider({claim.claim_id: text}))
        reviewer = SemanticReviewer(FixtureReviewProvider({claim.claim_id: json.dumps({"verdict": verdict, "issues": []})}))
        return verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, key_id="channel", task=task)
    return fn


def run_case(case_id: str, *, delivery: str = "text", combinator: bool = True, case: Optional[dict] = None) -> CaseRun:
    """Run one development case end to end and return its receipts."""
    case = case if case is not None else load_case(case_id)
    plan = WorkPlan(**work_plan_fields(case, combinator=COMBINATOR if combinator else None))
    hub = RouterHub(signing_key=KEY, key_id="channel", config=CFG)
    ch = hub.open_task(plan)
    task = plan.task_id
    extra: list[SuppliedText] = []
    peers = []
    for peer in case.get("peers", []):
        ch.verify_claim_fn = verifier(peer, peer.get("fidelity_review", case.get("fidelity_review")))
        pm, _req, _rq = hub.dispatch(task, peer["agent_id"], peer["request"], supplied_texts(peer))
        assert pm is not None, f"the peer request of {case['id']} was refused"
        preply, prc = hub.receive(task, pm.message_id, peer["answer"], agent_id=peer["agent_id"], report_id=peer.get("report_id", f"rep-{peer['agent_id']}"))
        forward = None
        if preply is not None and peer.get("relay_to_main"):
            from epinoic_logic.translate.contracts import SpecialistReport
            prep = SpecialistReport.model_validate(preply.payload)
            relayed, forward = ch.relay("router", AgentRole.ROUTER, case["agent_id"], AgentRole.SPECIALIST, prep, in_reply_to=preply.message_id)
            if relayed is not None:
                extra.append(SuppliedText(document_id=peer["peer_document_id"], title=peer.get("peer_document_title"), author=peer["agent_id"],
                                          text=peer.get("peer_document_text") or prep.original_response))
        peers.append((prc, forward))
    ch.verify_claim_fn = verifier(case)
    m, _req, rq = hub.dispatch(task, case["agent_id"], case["request"], [*supplied_texts(case), *extra])
    assert m is not None, f"the request of {case['id']} was refused: {[f.code for f in rq.findings]}"
    if delivery == "report":
        reply, rc = hub.receive(task, m.message_id, structured_report(case))
    else:
        reply, rc = hub.receive(task, m.message_id, case["answer"], agent_id=case["agent_id"], report_id=case.get("ids", {}).get("report_id", f"rep-{case['id']}"))
    return CaseRun(case=case, hub=hub, channel=ch, request_receipt=rq, reply=reply, receipt=rc, peer_receipts=peers)
