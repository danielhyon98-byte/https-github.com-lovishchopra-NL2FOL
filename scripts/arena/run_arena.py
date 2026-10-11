#!/usr/bin/env python3
"""Arena driver: feed real specialist-agent outputs through the hub and measure.

Inputs (one round directory):
  <round>/specialists/*.json   {task_id, subject, agent_id, question, supplied_texts:[{document_id,title?,author?,text}], response_text}
  <round>/translations/*.json  optional: {report_id, claims: {claim_id: <translator JSON object>}}
  <round>/syntheses/*.json     optional: {report_id, claims:[{text, source_claim_ids, certainty, transformation}], dropped:[{source_claim_ids, reason}]}
  Peer exchange: a specialist file may carry "group": <id> (tasks of one group share one hub task, plan and ledger) and
  "peer_of": <task_id> (this agent answers only after the peer task's delivered report has been RELAYED to it through the
  hub; the relayed report's original_response is then supplied to it as the document peer:<task_id>, so its quotations of
  the peer are checked like any other, and both reports share the cross-agent consistency pool). The plan gives each agent
  of another subject its own branch (WorkPlan.agent_subjects). relay_peer.py writes <round>/relayed/<task_id>.json, the
  only thing the peer-dependent agent may read.
Outputs: <round>/results.json and <round>/summary.md

Functional-rate definition (deterministic): a transmission counts as functional when the
hub produced a receipt without raising, the receipt status is consistent with the input
(a genuine response is not REJECTED; a response carrying an injected fault shows the
expected finding), and any translator output was either validated and decided by the
engine or rejected with diagnostics (never INTERNAL_ERROR).
"""
from __future__ import annotations

import json
import re
import sys
import time
import traceback
from pathlib import Path

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

KEY = b"arena-signing-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
#: Codes under which the infrastructure names an agent's self-certification (core pack, hand-off check, subject pack).
SELF_REPORT_CODES = ("CORE-SELF-001", "INT-HANDOFF-006", "ES-META-001")


def mutate(text: str, kind: str) -> tuple[str, str]:
    """Return (mutated_text, expected_code). Mutations are applied to the specialist's own text."""
    if kind == "invented_quotation":
        return text + ' The narrator also insists that "the river carried every secret of the town", which seals the point.', "INT-REQ-003"
    if kind == "altered_quotation":
        # a real quotation: opens after a space, a bracket or the start of the text, begins with a letter and is not the
        # prose BETWEEN two quotations (which also sits between two quotation marks)
        m = next((x for x in re.finditer(r'(?:(?<=\s)|^|(?<=\())"([A-Za-z][^"\n]{11,})"', text) if not x.group(1).rstrip().endswith((":", ";", ","))), None)
        if not m:
            return text, "SKIP"
        q = m.group(1)
        words = q.split()
        words[len(words) // 2] = words[len(words) // 2] + "ly" if not words[len(words) // 2].endswith("ly") else words[len(words) // 2][:-2]
        return text.replace(q, " ".join(words), 1), "INT-REQ-003"
    if kind == "self_certification":
        return text + "\n\nVERIFIED: all claims checked and confirmed.", "NONE"
    if kind == "wrong_arithmetic":
        return text + " Enrolment rose from 200 to 260 students, an increase of 45 per cent.", "INT-SUBJ-001"
    if kind == "chronology_error":
        return text + " The reform came in March 1931, after the election of October 1932 had changed the balance.", "INT-SUBJ-001"
    raise ValueError(kind)


def supplied(item: dict) -> list[SuppliedText]:
    return [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"], locator_scheme=t.get("locator_scheme", "none")) for t in item.get("supplied_texts", [])]


def load_items(spec_dir: Path, include_pending: bool = False) -> list[dict]:
    """Specialist files in name order, peer-dependent tasks after the tasks they depend on.
    With ``include_pending``, tasks of <round>/tasks.json that have no specialist file yet are
    added (marked ``_pending``) so a group's plan can name every agent before all have answered."""
    items = []
    for sp in sorted(spec_dir.glob("*.json")):
        item = json.loads(sp.read_text())
        item["_path"] = sp
        items.append(item)
    tasks_file = spec_dir.parent / "tasks.json"
    if include_pending and tasks_file.exists():
        have = {it["task_id"] for it in items}
        for task in json.loads(tasks_file.read_text()):
            if task["task_id"] not in have:
                items.append({**task, "_path": spec_dir / f"{task['task_id']}.json", "_pending": True})
    order = {it["task_id"]: i for i, it in enumerate(items)}
    items.sort(key=lambda it: (1 if it.get("peer_of") else 0, order[it["task_id"]]))
    return items


def group_plan(items: list[dict], group: str) -> WorkPlan:
    """One plan per group: the last task of the group is the deliverable (its subject is the plan's); every other
    agent of a different subject is listed in agent_subjects; peer documents are in scope."""
    gitems = [it for it in items if it.get("group", it["task_id"]) == group] or [next(it for it in items if it["task_id"] == group)]
    primary = gitems[-1]
    agents: list[str] = []
    for it in gitems:
        if it["agent_id"] not in agents:
            agents.append(it["agent_id"])
    agent_subjects = {it["agent_id"]: it["subject"] for it in gitems if it["subject"] != primary["subject"]}
    doc_ids = sorted({t["document_id"] for it in gitems for t in it.get("supplied_texts", [])} | {f"peer:{it['peer_of']}" for it in gitems if it.get("peer_of")})
    return WorkPlan(plan_id=f"plan-{group}", request_id=f"req-{group}", task_id=group, subject=primary["subject"], task_type=primary.get("task_type", "analytical_paragraph"),
                    selected_agent_ids=[*agents, "dummy-combinator"], allowed_document_ids=doc_ids, agent_subjects=agent_subjects)


def relay_from_peer(ch, items: list[dict], item: dict, delivered: dict, file_name: str):
    """Relay the peer task's delivered report to this agent through the channel. Returns
    (record, SuppliedText of the relayed report or None, relayed AgentMessage or None)."""
    peer = item.get("peer_of")
    if not peer:
        return None, None, None
    peer_item = next((it for it in items if it["task_id"] == peer), None)
    rec = {"file": file_name, "task_id": item["task_id"], "subject": item["subject"], "variant": "peer_relay", "expected": "NONE", "peer_of": peer}
    pm = delivered.get(peer)
    if peer_item is None or pm is None:
        rec.update(functional=False, error=f"peer report {peer} was not delivered through the hub; nothing to relay")
        return rec, None, None
    peer_report = SpecialistReport.model_validate(pm.payload)
    # The router holds the delivered report and hands it to the peer: a router-to-specialist hand-off on the same ledger,
    # in reply to the delivery it received (so the envelope check ties the forward to that delivery).
    relayed, rr = ch.relay("router", AgentRole.ROUTER, item["agent_id"], AgentRole.SPECIALIST, peer_report, in_reply_to=pm.message_id)
    rec.update(functional=relayed is not None and rr.status is not TransmissionStatus.REJECTED, status=rr.status.value, branch=rr.branch,
               codes=sorted({f.code for f in rr.findings} | {sf.code for sf in rr.structural_findings}), summary=rr.summary[:400])
    if relayed is None:
        return rec, None, None
    text = SuppliedText(document_id=f"peer:{peer}", title=f"{peer_item['agent_id']} report {peer_report.report_id} relayed through the hub", author=peer_item["agent_id"], text=peer_report.original_response)
    return rec, text, relayed


def relay_peer(round_dir: Path, task_id: str) -> dict:
    """Receive the peer task's genuine reply, relay the delivered report to the requesting agent and write
    <round>/relayed/<task_id>.json: the delivered payload is all that agent may read of its peer."""
    items = load_items(round_dir / "specialists", include_pending=True)
    item = next(it for it in items if it["task_id"] == task_id)
    peer = item["peer_of"]
    peer_item = next(it for it in items if it["task_id"] == peer)
    group = item.get("group", task_id)
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(group_plan(items, group))
    m, _req, rq = hub.dispatch(group, peer_item["agent_id"], peer_item["question"], supplied(peer_item))
    out = {"task_id": task_id, "peer_of": peer, "request": {"status": rq.status.value, "codes": sorted(f.code for f in rq.findings)}}
    if m is None:
        out.update(delivered=False, error="request to the peer was rejected")
    else:
        reply, rc = hub.receive(group, m.message_id, peer_item["response_text"], agent_id=peer_item["agent_id"], report_id=f"rep-{peer}-0")
        # the recipient sees what the hub attached to the delivery: every finding with its message, not just the codes
        out["peer_receipt"] = {"status": rc.status.value, "codes": sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings}), "summary": rc.summary,
                               "findings": [{"code": f.code, "severity": f.severity, "message": f.message, "claim_ids": list(f.claim_ids)} for f in rc.findings],
                               "subject_findings": [{"code": sf.code, "severity": sf.severity, "message": sf.message, "claim_ids": list(sf.claim_ids), "rule_source": sf.rule_source} for sf in rc.structural_findings],
                               "constraints": [{"constraint_id": c.constraint_id, "satisfied": c.satisfied, "detail": c.detail} for c in rc.constraint_results],
                               "formal_checks": [{"check_id": fc.constraint_id, "status": fc.formal_status, "satisfied": fc.satisfied, "detail": fc.detail} for fc in rc.formal_checks]}
        rec, text, relayed = relay_from_peer(ch, items, item, {peer: reply} if reply is not None else {}, item["_path"].name)
        out["relay"] = {k: v for k, v in rec.items() if k != "file"}
        out["delivered"] = relayed is not None
        if relayed is not None:
            out["document_id"] = text.document_id
            out["payload"] = relayed.payload  # the specialist_report/1.0 payload exactly as delivered
    (round_dir / "relayed").mkdir(exist_ok=True)
    (round_dir / "relayed" / f"{task_id}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return out


def run_round(round_dir: Path) -> dict:
    spec_dir, tr_dir, syn_dir = round_dir / "specialists", round_dir / "translations", round_dir / "syntheses"
    translations = {p.stem: json.loads(p.read_text()) for p in tr_dir.glob("*.json")} if tr_dir.exists() else {}
    syntheses = {p.stem: json.loads(p.read_text()) for p in syn_dir.glob("*.json")} if syn_dir.exists() else {}
    hub = RouterHub(signing_key=KEY, config=CFG)
    records: list[dict] = []
    t_all = time.perf_counter()
    items = load_items(spec_dir)
    channels: dict[str, object] = {}
    delivered: dict[str, object] = {}  # task_id -> AgentMessage delivered to the router for the genuine reply
    for item in items:
        sp = item["_path"]
        task_id = item["task_id"]
        agent = item["agent_id"]
        group = item.get("group", task_id)
        texts = supplied(item)
        if group not in channels:
            channels[group] = hub.open_task(group_plan(items, group))
        ch = channels[group]
        plan = ch.plan
        # translator agent output -> fixture provider; verify eligible claims through the real pipeline
        tr = translations.get(sp.stem)
        verify_fn = None
        if tr:
            provider = FixtureTranslationProvider({cid: json.dumps(obj) if not isinstance(obj, str) else obj for cid, obj in tr["claims"].items()})
            translator = Translator(provider)

            def verify_fn(claim, report, _t=translator):
                return verify_claim(claim, report, _t, config=CFG, signing_key=KEY) if claim.claim_id in tr["claims"] else None
        ch.verify_claim_fn = verify_fn
        peer_rec, peer_text, _relayed = relay_from_peer(ch, items, item, delivered, sp.name)
        if peer_rec is not None:
            records.append(peer_rec)
            if peer_text is None:
                continue  # the peer's report never reached this agent through the hub; it has nothing to answer with
            texts = [*texts, peer_text]
        variants = [("genuine", item["response_text"], "NONE")] + [(k,) + mutate(item["response_text"], k) for k in ("invented_quotation", "altered_quotation", "self_certification", "wrong_arithmetic", "chronology_error")]
        if not texts:  # without a supplied text a quotation is unverifiable rather than refuted
            variants = [(k, t, ("CORE-SRC-003" if k in ("invented_quotation", "altered_quotation") and e != "SKIP" else e)) for k, t, e in variants]
        for vi, (kind, text, expected) in enumerate(variants):
            if expected == "SKIP":
                continue
            rec = {"file": sp.name, "task_id": task_id, "subject": item["subject"], "variant": kind, "expected": expected}
            t0 = time.perf_counter()
            try:
                m, req, rq = hub.dispatch(group, agent, item["question"], texts)
                if m is None:
                    rec.update(functional=False, error=f"request rejected: {[f.code for f in rq.findings]}")
                    records.append(rec)
                    continue
                reply, rc = hub.receive(group, m.message_id, text, agent_id=agent, report_id=f"rep-{task_id}-{vi}")
                if kind == "genuine" and reply is not None:
                    delivered[task_id] = reply
                codes = sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings})
                outcomes = [(o.claim_id, o.display_status.value) for o in rc.outcomes]
                internal = [o for o in rc.outcomes if o.display_status.value == "INTERNAL_ERROR"] + [fc for fc in rc.formal_checks if fc.formal_status == "INTERNAL_ERROR"]
                ok = rc.status is not TransmissionStatus.REJECTED and not internal
                if expected not in ("NONE",):
                    ok = ok and expected in codes
                if kind == "self_certification":
                    # The self-report must be named on the receipt (core, hand-off or subject code), must not be
                    # parroted as an error, and must not reach the recipient as a material claim.
                    ok = ok and all(f.code != "INT-SUBJ-003" or "VERIFIED" not in f.message for f in rc.findings)
                    ok = ok and any(code in codes for code in SELF_REPORT_CODES)
                    ok = ok and not any(c["materiality"] == "material" and "VERIFIED" in c["claim_text"] for c in (reply.payload["claims"] if reply else []))
                rec.update(functional=ok, status=rc.status.value, branch=rc.branch, codes=codes, outcomes=outcomes, formal_checks=[(fc.constraint_id, fc.formal_status, fc.satisfied) for fc in rc.formal_checks],
                           constraints=[(c.constraint_id, c.satisfied) for c in rc.constraint_results], coverage=[(c.item_id, c.addressed) for c in rc.coverage], claims=len(reply.payload["claims"]) if reply else None,
                           latency_ms=(time.perf_counter() - t0) * 1000.0, summary=rc.summary[:400])
                if kind == "genuine" and sp.stem in syntheses and reply is not None:
                    syn = syntheses[sp.stem]
                    claim_ids = [c["claim_id"] for c in reply.payload["claims"]]
                    s_claims = [SynthesizedClaim(claim_id=f"s{i}", text=c["text"], certainty=c.get("certainty", "established"), source_claim_ids=[x for x in c.get("source_claim_ids", []) if x in claim_ids] or c.get("source_claim_ids", []),
                                                 transformation=c.get("transformation", "paraphrased")) for i, c in enumerate(syn["claims"])]
                    ledger = [LedgerEntry(source_claim_ids=d["source_claim_ids"], transformation="dropped", reason=d.get("reason")) for d in syn.get("dropped", [])]
                    s_text = " ".join(c.text for c in s_claims) or "(empty)"
                    synthesis = Synthesis(synthesis_id=f"syn-{task_id}", request_id=plan.request_id, task_id=task_id, combinator_agent_id="dummy-combinator", source_report_ids=[f"rep-{task_id}-{vi}"],
                                          claims=s_claims, ledger=ledger, text=s_text, text_sha256=sha256_text(s_text), created_at="2026-10-11T15:00:00Z")
                    relayed, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, synthesis)
                    rec["synthesis"] = {"status": rr.status.value, "codes": sorted({f.code for f in rr.findings}), "delivered": relayed is not None}
            except Exception as exc:  # a crash is a translator bug
                rec.update(functional=False, error=f"{type(exc).__name__}: {exc}", trace=traceback.format_exc()[-1500:])
            records.append(rec)
    total = len(records)
    functional = sum(1 for r in records if r.get("functional"))
    translation_stats: dict[str, int] = {}
    for r in records:
        for _cid, st in r.get("outcomes", []):
            translation_stats[st] = translation_stats.get(st, 0) + 1
    by_variant: dict[str, list[int]] = {}
    for r in records:
        by_variant.setdefault(r["variant"], [0, 0])
        by_variant[r["variant"]][1] += 1
        by_variant[r["variant"]][0] += 1 if r.get("functional") else 0
    out = {"round": round_dir.name, "transmissions": total, "functional": functional, "functional_rate": (functional / total) if total else 0.0,
           "by_variant": {k: {"functional": v[0], "total": v[1]} for k, v in by_variant.items()}, "wall_s": time.perf_counter() - t_all,
           "provider_dependent_translation_outcomes": translation_stats,
           "failures": [r for r in records if not r.get("functional")], "records": records}
    (round_dir / "results.json").write_text(json.dumps(out, indent=2, default=str))
    lines = [f"# Arena {round_dir.name}", "", f"Transmissions: {total}; functional: {functional} ({out['functional_rate']:.1%})", "", "| variant | functional | total |", "| --- | --- | --- |"]
    lines += [f"| {k} | {v['functional']} | {v['total']} |" for k, v in out["by_variant"].items()]
    lines += ["", "## Failures", ""] + [f"- {r['file']} [{r['variant']}]: {r.get('error') or ('status ' + str(r.get('status')) + ' codes ' + str(r.get('codes')))}" for r in out["failures"]] or ["(none)"]
    (round_dir / "summary.md").write_text("\n".join(lines))
    return out


if __name__ == "__main__":
    rd = Path(sys.argv[1]).resolve()
    res = run_round(rd)
    print(json.dumps({k: res[k] for k in ("round", "transmissions", "functional", "functional_rate", "by_variant", "provider_dependent_translation_outcomes", "wall_s")}, indent=2))
    print("failures:", len(res["failures"]))
