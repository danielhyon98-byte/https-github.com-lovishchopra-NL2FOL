"""Support for the core fixer's second-pass round-9 clearance tests: the recorded material the c2 core material lacks
(``data/c2b_core_material.json``, copied verbatim from the rounds), delivered as ``c2_core_support`` delivers the c2
material: a fresh hub, each recorded translation served to its claim as the arena harness serves it (the task record
passed on), every other claim outside the replay's scope."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from epinoic_logic.branches import RouterHub
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText

from .c2_core_support import CFG, COMB, KEY, fixture_verifier

C2B = json.loads((Path(__file__).parent / "data" / "c2b_core_material.json").read_text())


def translation(round_: str, task: str, cid: str) -> dict:
    """The recorded translation of ``cid`` (or of its qualified form) in ``round_`` (``c1`` or ``c2``)."""
    claims = C2B[round_]["translations"][task]
    key = cid if cid in claims else next(k for k in claims if k.split("@")[0] == cid.split("@")[0])
    return claims[key]


def deliver_recorded(round_: str, task: str, translations: Optional[dict] = None, *, text: Optional[str] = None):
    """``(hub, channel, reply, receipt)`` of the recorded reply of ``task`` in ``round_`` (a specialist file of this material)
    delivered on a hub task of its own with ``translations`` served."""
    item = C2B[round_]["specialists"][task]
    texts = [SuppliedText(**{k: v for k, v in t.items() if k in ("document_id", "title", "author", "text")}) for t in item.get("supplied_texts", [])]
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id=f"plan-{item['task_id']}", request_id=f"req-{item['task_id']}", task_id=item["task_id"], subject=item["subject"],
                                task_type=item.get("task_type") or "short_answer", selected_agent_ids=[item["agent_id"], COMB],
                                allowed_document_ids=[t.document_id for t in texts]))
    ch.verify_claim_fn = fixture_verifier(translations or {})
    m, _req, _rq = hub.dispatch(item["task_id"], item["agent_id"], item["question"], texts)
    reply, rc = hub.receive(item["task_id"], m.message_id, item["response_text"] if text is None else text, agent_id=item["agent_id"],
                            report_id=f"rep-{item['task_id']}-0")
    return hub, ch, reply, rc


def supplied(round_: str, task: str) -> list[SuppliedText]:
    item = C2B[round_]["specialists"][task]
    return [SuppliedText(**{k: v for k, v in t.items() if k in ("document_id", "title", "author", "text")}) for t in item.get("supplied_texts", [])]
