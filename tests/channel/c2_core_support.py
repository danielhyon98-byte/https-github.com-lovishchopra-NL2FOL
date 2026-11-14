"""Support for the core fixer's round-9 clearance tests (integrated round c2): the recorded material
(``data/c2_core_material.json``, copied verbatim from the round) delivered through a fresh hub, each recorded translation
served to its claim as the arena harness serves it (a fixture keyed by the delivered claim id or its unqualified form, with
the task record of the request passed on, as production passes it), every other claim outside the replay's scope; and a
recorded synthesis relayed as the harness relays it (its claims with the format's defaults, its ``dropped`` entries as
ledger entries, its text the claims joined)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.bus import CLAIM_OUT_OF_SCOPE
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.translate.contracts import SuppliedText, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

KEY = b"c2-core-clearance-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
C2 = json.loads((Path(__file__).parent / "data" / "c2_core_material.json").read_text())
SPEC = C2["specialists"]
COMB = "dummy-combinator"
#: The format's defaults for a synthesized claim (the arena harness's SYNTHESIS_CLAIM_DEFAULTS).
CLAIM_DEFAULTS = {"certainty": "established", "transformation": "paraphrased"}


def codes(findings) -> list[str]:
    return [f.code for f in findings]


def by_code(findings, code: str) -> list:
    return [f for f in findings if f.code == code]


def supplied(task: str, *, with_peer: bool = True) -> list[SuppliedText]:
    item = SPEC[task]
    texts = [SuppliedText(**{k: v for k, v in t.items() if k in ("document_id", "title", "author", "text")}) for t in item.get("supplied_texts", [])]
    peer = C2["peer_documents"].get(task)
    if with_peer and peer is not None:
        texts.append(SuppliedText(document_id=peer["document_id"], text=peer["text"]))
    return texts


def fixture_verifier(translations: dict):
    """A claim verifier serving ``translations`` (claim id -> recorded translator JSON), the task record passed on."""
    def verify(claim, report, task=None):
        key = claim.claim_id if claim.claim_id in translations else next((k for k in translations if k.split("@")[0] == claim.claim_id.split("@")[0]), None)
        if key is None:
            return CLAIM_OUT_OF_SCOPE
        obj = json.loads(json.dumps(translations[key]))
        if isinstance(obj.get("problem"), dict):  # the recorded problem names the round's ids; served to this hub task's claim
            obj["problem"]["claim_id"] = claim.claim_id
            obj["problem"]["request_id"] = claim.request_id
        provider = FixtureTranslationProvider({claim.claim_id: [json.dumps(obj), json.dumps(obj)]})
        return verify_claim(claim, report, Translator(provider), config=CFG, signing_key=KEY, task=task)
    return verify


def open_task(task: str, *, with_peer: bool = True, translations: Optional[dict] = None):
    """``(hub, channel, request message)`` of a hub task of its own for the recorded ``task``."""
    item = SPEC[task]
    texts = supplied(task, with_peer=with_peer)
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id=f"plan-{item['task_id']}", request_id=f"req-{item['task_id']}", task_id=item["task_id"], subject=item["subject"],
                                task_type=item.get("task_type") or "short_answer", selected_agent_ids=[item["agent_id"], COMB],
                                allowed_document_ids=[t.document_id for t in texts]))
    ch.verify_claim_fn = fixture_verifier(translations or {})
    m, _req, _rq = hub.dispatch(item["task_id"], item["agent_id"], item["question"], texts)
    return hub, ch, m


def deliver(task: str, text: Optional[str] = None, *, translations: Optional[dict] = None, with_peer: bool = True):
    """``(hub, channel, reply, receipt)`` of one recorded reply (or ``text`` in its place) delivered on a hub task of its
    own, with ``translations`` served to the claims they name (none: every claim is outside the replay's scope)."""
    item = SPEC[task]
    hub, ch, m = open_task(task, with_peer=with_peer, translations=translations)
    reply, rc = hub.receive(item["task_id"], m.message_id, item["response_text"] if text is None else text, agent_id=item["agent_id"],
                            report_id=f"rep-{item['task_id']}-0")
    return hub, ch, reply, rc


def file_synthesis(ch, reply, task: str, *, mutate: Optional[Callable[[dict], dict]] = None, synthesis_id: Optional[str] = None) -> dict:
    """The recorded synthesis file of ``task`` as the mapping the router receives (the arena harness's shape): its claims
    with the format's defaults and ids ``s<i>``, its ``dropped`` entries as ledger entries, its text the claims joined.
    ``mutate`` edits a copy of the file first."""
    doc = json.loads(json.dumps(C2["syntheses"][task]))
    if mutate is not None:
        doc = mutate(doc)
    by_id = {c["claim_id"]: c for c in reply.payload["claims"]}
    claims = []
    for i, c in enumerate(doc.get("claims", [])):
        claim = dict(c)
        claim.update(claim_id=f"s{i}", **{k: c.get(k, v) for k, v in CLAIM_DEFAULTS.items()})
        if "evidence_refs" not in c:  # as the harness does: the references of cited material sources whose excerpt the text reproduces
            claim["evidence_refs"] = _reproduced_refs(c.get("text", ""), c.get("source_claim_ids", []), by_id)
        claims.append(claim)
    ledger = [{**d, "transformation": "dropped"} for d in doc.get("dropped", [])]
    text = " ".join(c["text"] for c in claims) or "(empty)"
    return {"synthesis_id": synthesis_id or f"syn-{task}", "request_id": ch.plan.request_id, "task_id": ch.plan.task_id, "combinator_agent_id": COMB,
            "source_report_ids": [reply.payload["report_id"]], "claims": claims, "ledger": ledger, "text": text, "text_sha256": sha256_text(text),
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}


def _fold(text: str) -> str:
    return " ".join(re.sub("[\"'“”‘’«»]", '"', text or "").split()).casefold()


def _reproduced_refs(text: str, cited: list, by_id: dict) -> list[dict]:
    """The source references of the cited material source claims whose excerpt ``text`` reproduces word for word (quote marks,
    spacing and trailing sentence punctuation aside), as the arena harness copies them (``run_arena.reproduced_evidence_refs``)."""
    hay = _fold(text)
    out, seen = [], set()
    for cid in cited:
        src = by_id.get(cid) or {}
        if src.get("materiality", "material") != "material":
            continue
        for r in src.get("source_refs") or []:
            ex = _fold((r.get("excerpt") or "").rstrip(" .,;:!?"))
            key = (r.get("document_id"), r.get("locator"), r.get("excerpt"))
            if ex and ex in hay and key not in seen:
                seen.add(key)
                out.append({k: r[k] for k in ("document_id", "locator", "excerpt") if r.get(k) is not None})
    return out


def relay(ch, synthesis: dict):
    """Relay a synthesis mapping from the combinator to the router: ``(message, receipt)``."""
    return ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, synthesis)
