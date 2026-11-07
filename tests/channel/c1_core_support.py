"""Support for the core fixer's round-8 clearance tests (integrated round c1): the recorded material
(``data/c1_core_material.json``, copied verbatim from the round and from breadth round b1) delivered through a fresh hub,
each recorded translation served to its claim as the arena harness serves it (a fixture keyed by the delivered claim id
or its unqualified form), every other claim outside the replay's scope."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.bus import CLAIM_OUT_OF_SCOPE
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.translate.contracts import SuppliedText, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

KEY = b"c1-core-clearance-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
C1 = json.loads((Path(__file__).parent / "data" / "c1_core_material.json").read_text())
SPEC = C1["specialists"]
COMB = "dummy-combinator"


def codes(findings) -> list[str]:
    return [f.code for f in findings]


def by_code(findings, code: str) -> list:
    return [f for f in findings if f.code == code]


def supplied(task: str, *, with_peer: bool = True) -> list[SuppliedText]:
    item = SPEC[task]
    texts = [SuppliedText(**{k: v for k, v in t.items() if k in ("document_id", "title", "author", "text")}) for t in item.get("supplied_texts", [])]
    peer = C1["peer_documents"].get(task)
    if with_peer and peer is not None:
        texts.append(SuppliedText(document_id=peer["document_id"], text=peer["text"]))
    return texts


def _fixture_verifier(translations: dict):
    def verify(claim, report, task=None):
        key = claim.claim_id if claim.claim_id in translations else next((k for k in translations if k.split("@")[0] == claim.claim_id.split("@")[0]), None)
        if key is None:
            return CLAIM_OUT_OF_SCOPE
        obj = json.loads(json.dumps(translations[key]))
        if isinstance(obj.get("problem"), dict):  # the recorded problem names the round's ids; served to this hub task's claim
            obj["problem"]["claim_id"] = claim.claim_id
            obj["problem"]["request_id"] = claim.request_id
        provider = FixtureTranslationProvider({claim.claim_id: [json.dumps(obj), json.dumps(obj)]})
        # served as the arena harness serves a recorded translation: without the task record (its replay verifier takes none)
        return verify_claim(claim, report, Translator(provider), config=CFG, signing_key=KEY)
    return verify


def deliver(task: str, text: Optional[str] = None, *, translations: Optional[dict] = None, with_peer: bool = True):
    """``(hub, channel, reply, receipt)`` of one recorded reply (or ``text`` in its place) delivered on a hub task of its
    own, with ``translations`` (claim id -> recorded translator JSON) served to the claims they name."""
    item = SPEC[task]
    texts = supplied(task, with_peer=with_peer)
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id=f"plan-{item['task_id']}", request_id=f"req-{item['task_id']}", task_id=item["task_id"], subject=item["subject"],
                                task_type=item.get("task_type") or "short_answer", selected_agent_ids=[item["agent_id"], COMB],
                                allowed_document_ids=[t.document_id for t in texts]))
    if translations is not None:
        ch.verify_claim_fn = _fixture_verifier(translations)
    m, _req, _rq = hub.dispatch(item["task_id"], item["agent_id"], item["question"], texts)
    reply, rc = hub.receive(item["task_id"], m.message_id, item["response_text"] if text is None else text, agent_id=item["agent_id"],
                            report_id=f"rep-{item['task_id']}-0")
    return hub, ch, reply, rc


def relay_synthesis(ch, report_id: str, claims: list[tuple[str, list[str], str]], *, synthesis_id: str = "syn-0", conflicts=()):
    """Relay a synthesis of ``claims`` ``(text, source claim ids, transformation)`` whose text is the claims joined."""
    sc = [SynthesizedClaim(claim_id=f"s{i}", text=t, certainty="probable", source_claim_ids=list(ids), transformation=tr) for i, (t, ids, tr) in enumerate(claims)]
    text = " ".join(t for t, _ids, _tr in claims)
    s = Synthesis(synthesis_id=synthesis_id, request_id=ch.plan.request_id, task_id=ch.plan.task_id, combinator_agent_id=COMB, source_report_ids=[report_id],
                  claims=sc, ledger=[], text=text, text_sha256=sha256_text(text), created_at="2026-11-02T09:00:00Z", conflicts=list(conflicts))
    return ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, s)
