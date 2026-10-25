"""Round-7 material for the regression tests: the recorded specialist replies, the combinator's syntheses and the
translator fixtures of the claims the round-7 overseers named, delivered through the hub as the arena delivers them (one
hub task per group; a peer-dependent agent answers after the peer's delivered report was forwarded to it through the
hub, with that report supplied as ``peer:<task>``)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

DATA = Path(__file__).parent / "data"
R7 = json.loads((DATA / "r7_material.json").read_text())
TRANSLATIONS = json.loads((DATA / "r7_translations.json").read_text())
SPEC: dict[str, dict] = R7["specialists"]
SYN: dict[str, dict] = R7["syntheses"]
KEY = b"round7-channel-test-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
COMB = "dummy-combinator"


def group_of(task_id: str) -> str:
    return SPEC[task_id].get("group") or task_id


def members(group: str) -> list[dict]:
    """The tasks of a group in delivery order: an agent that answers a peer comes after the peer."""
    items = [it for tid, it in SPEC.items() if group_of(tid) == group]
    return sorted(items, key=lambda it: (1 if it.get("peer_of") else 0, R7["order"].index(it["task_id"]) if it["task_id"] in R7["order"] else 99))


def supplied(item: dict) -> list[SuppliedText]:
    return [SuppliedText(**t) for t in item.get("supplied_texts", [])]


def plan_for(group: str) -> WorkPlan:
    """The arena's plan for a group: the last task is the deliverable, other subjects and task types are per agent."""
    items = members(group)
    primary = items[-1]
    ttype = primary.get("task_type", "analytical_paragraph")
    agents = list(dict.fromkeys(it["agent_id"] for it in items))
    return WorkPlan(plan_id=f"plan-{group}", request_id=f"req-{group}", task_id=group, subject=primary["subject"], task_type=ttype,
                    selected_agent_ids=[*agents, COMB],
                    allowed_document_ids=sorted({t["document_id"] for it in items for t in it.get("supplied_texts", [])} | {f"peer:{it['peer_of']}" for it in items if it.get("peer_of")}),
                    agent_subjects={it["agent_id"]: it["subject"] for it in items if it["subject"] != primary["subject"]},
                    agent_task_types={it["agent_id"]: it["task_type"] for it in items if it.get("task_type") and it["task_type"] != ttype})


def base_id(claim_id: str) -> str:
    """A claim id as the r7 recording wrote it: a parser that makes ids unique per agent ("g1.1@physics-specialist")
    keeps the recorded id before the "@"."""
    return claim_id.split("@", 1)[0]


#: the branches whose parser numbers claims with its own letter (s, m, c) instead of the generic branch's agent-qualified ids
STEM_BRANCHES = frozenset({"sciences", "mathematics", "computer_science"})
_RECORDED: dict[tuple[str, str], dict[str, str]] = {}


def recorded_ids(report: SpecialistReport) -> dict[str, str]:
    """Delivered claim id -> the id the r7 recording gives the same claim. A generic-branch id keeps the recorded id before
    the "@"; a STEM-branch report (Physics, Chemistry, Biology, ESS, Mathematics, Computer Science) delivers the generic
    parser's round-7 claims, claim by claim, under the branch's own letter (tests/stem/test_merge_round7.py), so its
    claim's recorded id is the generic parser's id of the claim at the same place (the texts are asserted equal)."""
    key = (report.report_id, report.response_sha256)
    if key in _RECORDED:
        return _RECORDED[key]
    ids = [c.claim_id for c in report.claims]
    branch, _ = default_registry().for_subject(report.subject)
    if branch.key not in STEM_BRANCHES:
        out = {i: base_id(i) for i in ids}
    else:
        generic = GenericTextParser(report.agent_id).parse_response(report.original_response, request_id=report.request_id, task_id=report.task_id,
                                                                    report_id=report.report_id, subject=report.subject, task_type=report.task_type,
                                                                    supplied_texts=list(report.supplied_texts), agent_id=report.agent_id)
        texts = [" ".join(c.claim_text.split()) for c in report.claims]
        assert texts == [" ".join(c.claim_text.split()) for c in generic.claims], (report.report_id, "the STEM parser's claims are not the generic parser's")
        out = {i: base_id(g.claim_id) for i, g in zip(ids, generic.claims)}
    _RECORDED[key] = out
    return out


def verify_fn(task_id: str):
    """The translator agent's recorded output for ``task_id`` (only the claims kept in r7_translations.json), served by
    the fixture provider and decided through the real pipeline and engine. The fixture is bound to the delivered claim
    (its problem's claim and request ids are the delivered claim's)."""
    tr = TRANSLATIONS.get(task_id)
    if not tr:
        return None

    def fn(claim, report):
        obj = tr["claims"].get(recorded_ids(report).get(claim.claim_id, base_id(claim.claim_id)))
        if obj is None:
            return None
        obj = json.loads(json.dumps(obj))
        obj["problem"]["claim_id"] = claim.claim_id
        obj["problem"]["request_id"] = claim.request_id
        translator = Translator(FixtureTranslationProvider({claim.claim_id: json.dumps(obj)}))
        return verify_claim(claim, report, translator, config=CFG, signing_key=KEY)
    return fn


def verify_fn_pooled(task_id: str, fixture_ids: list[str]):
    """The recorded translator fixtures ``fixture_ids`` of ``task_id``, the k-th bound to the k-th claim the channel asks to
    translate (read as a quantitative claim): what the channel pools then does not depend on how a parser numbers, splits
    or roles the claims. The outcome binds to the delivered claim (its id and request), as the channel requires."""
    fixtures = [TRANSLATIONS[task_id]["claims"][cid] for cid in fixture_ids]
    bound: dict[str, dict] = {}

    def fn(claim, report, task=None):
        # The channel passes the task record of the request (as it does to every task-aware verifier): since policy
        # 2026.10-v5 a restated task setting is a transcription only when a check validated it against that record.
        as_quantity = claim.model_copy(update={"claim_role": "quantitative", "proposed_claim_kind": "arithmetic"})
        if claim.claim_id not in bound and len(bound) < len(fixtures) and decide_eligibility(as_quantity).eligible:
            bound[claim.claim_id] = fixtures[len(bound)]
        obj = bound.get(claim.claim_id)
        if obj is None:
            return None
        obj = json.loads(json.dumps(obj))
        obj["problem"]["claim_id"] = claim.claim_id
        obj["problem"]["request_id"] = claim.request_id
        outcome = verify_claim(as_quantity, report, Translator(FixtureTranslationProvider({claim.claim_id: json.dumps(obj)})), config=CFG, signing_key=KEY,
                               task=task)
        return outcome
    return fn


class Run:
    """One group delivered through a fresh hub: ``receipts[task_id]`` and ``delivered[task_id]`` for every member."""

    def __init__(self, group: str, *, texts: Optional[dict[str, str]] = None, translations: bool = False, pooled: Optional[dict[str, list[str]]] = None) -> None:
        self.group = group
        self.hub = RouterHub(signing_key=KEY, config=CFG)
        self.ch = self.hub.open_task(plan_for(group))
        self.receipts: dict[str, object] = {}
        self.delivered: dict[str, object] = {}
        self.forward_receipts: dict[str, object] = {}
        for it in members(group):
            tid = it["task_id"]
            docs = supplied(it)
            peer = it.get("peer_of")
            if peer:
                pm = self.delivered[peer]
                fwd, frc = self.ch.relay("router", AgentRole.ROUTER, it["agent_id"], AgentRole.SPECIALIST, SpecialistReport.model_validate(pm.payload), in_reply_to=pm.message_id)
                self.forward_receipts[tid] = frc
                docs = [*docs, SuppliedText(document_id=f"peer:{peer}", title=f"{SPEC[peer]['agent_id']} report relayed through the hub", author=SPEC[peer]["agent_id"],
                                            text=fwd.payload["original_response"])]
            self.ch.verify_claim_fn = verify_fn_pooled(tid, pooled[tid]) if pooled and tid in pooled else (verify_fn(tid) if translations else None)
            m, _req, _rq = self.hub.dispatch(group, it["agent_id"], it["question"], docs)
            text = (texts or {}).get(tid, it["response_text"])
            reply, rc = self.hub.receive(group, m.message_id, text, agent_id=it["agent_id"], report_id=f"rep-{tid}-0")
            self.receipts[tid] = rc
            if reply is not None:
                self.delivered[tid] = reply

    def report(self, task_id: str) -> SpecialistReport:
        return SpecialistReport.model_validate(self.delivered[task_id].payload)

    def claim_id(self, task_id: str, recorded: str) -> str:
        """The delivered id of the claim the r7 recording calls ``recorded``."""
        return next((d for d, r in recorded_ids(self.report(task_id)).items() if r == recorded), recorded)

    def recorded_id(self, task_id: str, delivered: str) -> str:
        """The id the r7 recording gives the delivered claim ``delivered``."""
        return recorded_ids(self.report(task_id)).get(delivered, base_id(delivered))

    def claim(self, task_id: str, recorded: str):
        cid = self.claim_id(task_id, recorded)
        return next(c for c in self.report(task_id).claims if c.claim_id == cid)

    def synthesis(self, claims: Optional[dict[str, list[dict]]] = None) -> Synthesis:
        """The dummy combinator's recorded synthesis of the group (``claims`` replaces a member's synthesized claims)."""
        s_claims, ledger, sources = [], [], []
        items = [it for it in members(self.group) if it["task_id"] in self.delivered and it["task_id"] in SYN]
        for it in items:
            tid = it["task_id"]
            syn = SYN[tid]
            ids = {r: d for d, r in recorded_ids(self.report(tid)).items()}
            prefix = "" if len(items) == 1 else f"{tid}-"
            for i, c in enumerate((claims or {}).get(tid, syn["claims"])):
                s_claims.append(SynthesizedClaim(claim_id=f"{prefix}s{i}", text=c["text"], certainty=c.get("certainty", "established"),
                                                 source_claim_ids=[ids[x] for x in c.get("source_claim_ids", []) if x in ids] or c.get("source_claim_ids", []),
                                                 transformation=c.get("transformation", "paraphrased")))
            ledger += [LedgerEntry(source_claim_ids=[ids.get(x, x) for x in d["source_claim_ids"]], transformation="dropped", reason=d.get("reason")) for d in syn.get("dropped", [])]
            sources.append(self.delivered[tid].payload["report_id"])
        text = " ".join(c.text for c in s_claims) or "(empty)"
        return Synthesis(synthesis_id=f"syn-{self.group}", request_id=self.ch.plan.request_id, task_id=self.ch.plan.task_id, combinator_agent_id=COMB,
                         source_report_ids=sources, claims=s_claims, ledger=ledger, text=text, text_sha256=sha256_text(text), created_at="2026-10-11T15:00:00Z")

    def relay_synthesis(self, synthesis: Optional[Synthesis] = None):
        return self.ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, synthesis or self.synthesis())


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def by_code(findings, code: str) -> list:
    return [f for f in findings if f.code == code]
