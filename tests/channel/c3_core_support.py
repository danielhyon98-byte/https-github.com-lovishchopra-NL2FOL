"""Support for the core fixer's round-10 clearance tests (integrated round c3): the recorded material
(``data/c3_core_material.json``, copied verbatim from the round and from the communication-fidelity lens's own exchanges)
delivered through a fresh hub as ``c2_core_support`` delivers the c2 material: each recorded translation served to its claim
as the arena harness serves it (the task record passed on), every other claim outside the replay's scope, and a recorded
synthesis relayed as the harness relays it."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from epinoic_logic.branches import RouterHub
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText, sha256_text

from .c2_core_support import CFG, CLAIM_DEFAULTS, COMB, KEY, _reproduced_refs, fixture_verifier, relay

C3 = json.loads((Path(__file__).parent / "data" / "c3_core_material.json").read_text())

__all__ = ["C3", "KEY", "CFG", "COMB", "translations", "deliver_c3", "deliver_exchange", "synthesis_of", "relay"]


def translations(task: str) -> dict:
    """The recorded translations of ``task`` the material holds (claim id -> translator JSON)."""
    return dict(C3["c3"]["translations"].get(task, {}))


def _deliver(item: dict, served: Optional[dict], text: Optional[str]):
    texts = [SuppliedText(**{k: v for k, v in t.items() if k in ("document_id", "title", "author", "text")}) for t in item.get("supplied_texts", [])]
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id=f"plan-{item['task_id']}", request_id=f"req-{item['task_id']}", task_id=item["task_id"], subject=item["subject"],
                                task_type=item.get("task_type") or "short_answer", selected_agent_ids=[item["agent_id"], COMB],
                                allowed_document_ids=[t.document_id for t in texts]))
    ch.verify_claim_fn = fixture_verifier(served or {})
    m, _req, _rq = hub.dispatch(item["task_id"], item["agent_id"], item["question"], texts)
    reply, rc = hub.receive(item["task_id"], m.message_id, item["response_text"] if text is None else text, agent_id=item["agent_id"],
                            report_id=f"rep-{item['task_id']}-0")
    return hub, ch, reply, rc


def deliver_c3(task: str, served: Optional[dict] = None, *, text: Optional[str] = None):
    """``(hub, channel, reply, receipt)`` of the recorded c3 reply of ``task`` (or ``text`` in its place) on a hub task of its own,
    with ``served`` translations (claim id -> recorded translator JSON) served to the claims they name."""
    return _deliver(C3["c3"]["specialists"][task], served, text)


def deliver_exchange(name: str, *, text: Optional[str] = None):
    """``(hub, channel, reply, receipt)`` of one of the communication-fidelity lens's exchanges, no translation served."""
    return _deliver(C3["exchanges"]["specialists"][name], None, text)


def synthesis_of(ch, reply, doc: dict, *, synthesis_id: Optional[str] = None) -> dict:
    """A recorded synthesis file ``doc`` as the mapping the router receives (the arena harness's shape, as
    ``c2_core_support.file_synthesis`` builds it): claims with the format's defaults and ids ``s<i>``, the ``dropped`` entries as
    ledger entries, the text the claims joined."""
    doc = json.loads(json.dumps(doc))
    by_id = {c["claim_id"]: c for c in reply.payload["claims"]}
    claims = []
    for i, c in enumerate(doc.get("claims", [])):
        claim = dict(c)
        claim.update(claim_id=f"s{i}", **{k: c.get(k, v) for k, v in CLAIM_DEFAULTS.items()})
        if "evidence_refs" not in c:
            claim["evidence_refs"] = _reproduced_refs(c.get("text", ""), c.get("source_claim_ids", []), by_id)
        claims.append(claim)
    ledger = [{**d, "transformation": "dropped"} for d in doc.get("dropped", [])]
    text = " ".join(c["text"] for c in claims) or "(empty)"
    return {"synthesis_id": synthesis_id or f"syn-{ch.plan.task_id}", "request_id": ch.plan.request_id, "task_id": ch.plan.task_id,
            "combinator_agent_id": COMB, "source_report_ids": [reply.payload["report_id"]], "claims": claims, "ledger": ledger, "text": text,
            "text_sha256": sha256_text(text), "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}
