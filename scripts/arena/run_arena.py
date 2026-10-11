#!/usr/bin/env python3
"""Arena driver: feed real specialist-agent outputs through the hub and measure.

Inputs (one round directory):
  <round>/specialists/*.json   {task_id, subject, agent_id, task_type?, question, supplied_texts:[{document_id,title?,author?,text}], response_text}
  <round>/translations/*.json  optional: {report_id, claims: {claim_id: <translator JSON object>}, claim_text_sha256?: {claim_id: sha256}}
                               The optional claim_text_sha256 map (list_claims.py --json prints the digest of every claim) binds each
                               fixture to the claim text it was produced for; without it the harness captures the digest of each
                               fixture's claim from the genuine transmission. Either way the fixture provider refuses to serve a
                               fixture for a claim whose text changed (a mutation that alters the sentence, ids that shift when a
                               sentence is prepended), and the channel independently rejects an outcome bound to another text
                               (INT-STALE-011). Such a refusal is recorded per claim as STALE_FIXTURE_REFUSED: no verdict, and not an
                               infrastructure error.
  <round>/syntheses/*.json     optional: {report_id, claims:[{text, source_claim_ids, certainty, transformation}], dropped:[{source_claim_ids, reason}]}
  Peer exchange: a specialist file may carry "group": <id> (tasks of one group share one hub task, plan and ledger) and
  "peer_of": <task_id> (this agent answers only after the peer task's delivered report has been RELAYED to it through the
  hub; the relayed report's original_response is then supplied to it as the document peer:<task_id>, so its quotations of
  the peer are checked like any other, and both reports share the cross-agent consistency pool). The plan gives each agent
  of another subject its own branch (WorkPlan.agent_subjects) and each agent set a different task type its own task type
  (WorkPlan.agent_task_types), so a History peer asked for a short_answer on an analytical_paragraph task carries
  short_answer on its request, report and forward (INT-HANDOFF-010 compares against it). relay_peer.py builds the same plan
  through group_plan() and writes <round>/relayed/<task_id>.json, the only thing the peer-dependent agent may read.
Outputs: <round>/results.json and <round>/summary.md

Fault mutations applied to every specialist text: invented_quotation (double marks), invented_quotation_single (the same
invented words in single marks), altered_quotation (a real quotation changed by one word; skipped when the text has none),
self_certification, wrong_arithmetic, chronology_error. With a supplied text an invented or altered quotation is expected
as INT-REQ-003; without one it is unverifiable rather than refuted and is expected as CORE-SRC-003.

Functional-rate definition (deterministic): a transmission counts as functional when the
hub produced a receipt without raising, the receipt status is consistent with the input
(a genuine response is not REJECTED; a response carrying an injected fault shows the
expected finding), and any translator output was either validated and decided by the
engine or rejected with diagnostics (never INTERNAL_ERROR; a fixture refused as stale is
neither).

Per claim outcome the record keeps the display status, the translation status, the interpretation's ambiguity flags
(why a claim is AMBIGUOUS_TRANSLATION), the translation diagnostics, and for a verified problem the engine status with
the number of premises relied on, how many of those are ungrounded (assumptions, specialist inferences, unverified
quotations) and how many are unverified, so an ENTAILED verdict is read together with what it rests on.
Translation outcomes are provider-dependent: ``provider_dependent_translation_outcomes`` counts the genuine pass only
(every eligible claim with a fixture exactly once; the distinct-claim counts are reported beside it) and
``translation_outcomes_by_variant`` keeps the totals of every variant, which repeat the same claims.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import ClaimVerificationOutcome, SpecialistReport, SuppliedText, TranslationStatus, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

KEY = b"arena-signing-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
#: Codes under which the infrastructure names an agent's self-certification (core pack, hand-off check, subject pack).
SELF_REPORT_CODES = ("CORE-SELF-001", "INT-HANDOFF-006", "ES-META-001")
#: Mutations in the order they are applied; the variant index is part of the report id.
MUTATIONS = ("invented_quotation", "invented_quotation_single", "altered_quotation", "self_certification", "wrong_arithmetic", "chronology_error")
#: Mutations that invent or alter a quotation: INT-REQ-003 against a supplied text, CORE-SRC-003 (unverifiable) without one.
QUOTATION_MUTATIONS = ("invented_quotation", "invented_quotation_single", "altered_quotation")
#: The fixture provider's own refusal of a fixture produced for another claim text.
STALE_FIXTURE_MARK = "stale fixture"
STALE_BUCKET = "STALE_FIXTURE_REFUSED"


def mutate(text: str, kind: str) -> tuple[str, str]:
    """Return (mutated_text, expected_code). Mutations are applied to the specialist's own text."""
    if kind == "invented_quotation":
        return text + ' The narrator also insists that "the river carried every secret of the town", which seals the point.', "INT-REQ-003"
    if kind == "invented_quotation_single":
        # the same invented words in single quotation marks: both parsers delimit a single-quoted span of two or more words
        return text + " The narrator also insists that 'the river carried every secret of the town', which seals the point.", "INT-REQ-003"
    if kind == "altered_quotation":
        # alter a real quotation (any mark style, as the parsers delimit them), never the prose between two quotations
        from epinoic_logic.adapters.markdown import find_quotation_spans
        spans = [(a, b, inner) for a, b, inner in find_quotation_spans(text) if len(inner) >= 12 and inner[:1].isalpha()]
        if not spans:
            return text, "SKIP"
        q = spans[0][2]
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


def group_of(item: dict) -> str:
    """The hub task an input belongs to: its declared group, else its own file (variants of one task that share a
    task_id are separate hub tasks, each with its own channel and report ids)."""
    return item.get("group") or item["_path"].stem


def group_plan(items: list[dict], group: str) -> WorkPlan:
    """One plan per group: the last task of the group is the deliverable (its subject and task type are the plan's);
    every other agent of a different subject is listed in agent_subjects and every agent set a different task type in
    agent_task_types (the History peer of an English deliverable answers a short_answer, not an analytical_paragraph);
    peer documents are in scope. relay_peer() and run_round() both build their plans here, so they agree."""
    gitems = [it for it in items if group_of(it) == group] or [next(it for it in items if it["task_id"] == group)]
    primary = gitems[-1]
    primary_task_type = primary.get("task_type", "analytical_paragraph")
    agents: list[str] = []
    for it in gitems:
        if it["agent_id"] not in agents:
            agents.append(it["agent_id"])
    agent_subjects = {it["agent_id"]: it["subject"] for it in gitems if it["subject"] != primary["subject"]}
    agent_task_types = {it["agent_id"]: it["task_type"] for it in gitems if it.get("task_type") and it["task_type"] != primary_task_type}
    doc_ids = sorted({t["document_id"] for it in gitems for t in it.get("supplied_texts", [])} | {f"peer:{it['peer_of']}" for it in gitems if it.get("peer_of")})
    return WorkPlan(plan_id=f"plan-{group}", request_id=f"req-{group}", task_id=group, subject=primary["subject"], task_type=primary_task_type,
                    selected_agent_ids=[*agents, "dummy-combinator"], allowed_document_ids=doc_ids, agent_subjects=agent_subjects, agent_task_types=agent_task_types)


def relay_from_peer(ch, items: list[dict], item: dict, delivered: dict, file_name: str):
    """Relay the peer task's delivered report to this agent through the channel. Returns
    (record, SuppliedText of the relayed report or None, relayed AgentMessage or None)."""
    peer = item.get("peer_of")
    if not peer:
        return None, None, None
    peer_item = next((it for it in items if it["task_id"] == peer), None)
    rec = {"file": file_name, "task_id": item["task_id"], "subject": item["subject"], "variant": "peer_relay", "expected": "NONE", "peer_of": peer}
    pm = delivered.get(peer_item["_path"].stem) if peer_item is not None else None
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
    group = group_of(item)
    hub = RouterHub(signing_key=KEY, config=CFG)
    plan = group_plan(items, group)
    ch = hub.open_task(plan)
    m, _req, rq = hub.dispatch(group, peer_item["agent_id"], peer_item["question"], supplied(peer_item))
    out = {"task_id": task_id, "peer_of": peer, "plan": {"task_type": plan.task_type, "agent_task_types": dict(plan.agent_task_types), "agent_subjects": dict(plan.agent_subjects)},
           "request": {"status": rq.status.value, "codes": sorted(f.code for f in rq.findings)}}
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
        rec, text, relayed = relay_from_peer(ch, items, item, {peer_item["_path"].stem: reply} if reply is not None else {}, item["_path"].name)
        out["relay"] = {k: v for k, v in rec.items() if k != "file"}
        out["delivered"] = relayed is not None
        if relayed is not None:
            out["document_id"] = text.document_id
            out["payload"] = relayed.payload  # the specialist_report/1.0 payload exactly as delivered
    (round_dir / "relayed").mkdir(exist_ok=True)
    (round_dir / "relayed" / f"{task_id}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return out


def group_synthesis(items: list[dict], group: str, syntheses: dict, delivered: dict, plan: WorkPlan):
    """The dummy combinator's synthesis for a hub task: the per-report syntheses of every delivered member of the
    group, merged, citing each delivered report (a peer exchange is one task with two reports)."""
    members = [it for it in items if group_of(it) == group and it["_path"].stem in delivered and it["_path"].stem in syntheses]
    if not members:
        return None
    s_claims, ledger, source_ids = [], [], []
    for it in members:
        tid, syn, reply = it["task_id"], syntheses[it["_path"].stem], delivered[it["_path"].stem]
        claim_ids = [c["claim_id"] for c in reply.payload["claims"]]
        prefix = "" if len(members) == 1 else f"{tid}-"
        for i, c in enumerate(syn["claims"]):
            s_claims.append(SynthesizedClaim(claim_id=f"{prefix}s{i}", text=c["text"], certainty=c.get("certainty", "established"),
                                             source_claim_ids=[x for x in c.get("source_claim_ids", []) if x in claim_ids] or c.get("source_claim_ids", []), transformation=c.get("transformation", "paraphrased")))
        ledger += [LedgerEntry(source_claim_ids=d["source_claim_ids"], transformation="dropped", reason=d.get("reason")) for d in syn.get("dropped", [])]
        source_ids.append(reply.payload["report_id"])
    s_text = " ".join(c.text for c in s_claims) or "(empty)"
    return Synthesis(synthesis_id=f"syn-{group}", request_id=plan.request_id, task_id=plan.task_id, combinator_agent_id="dummy-combinator", source_report_ids=source_ids,
                     claims=s_claims, ledger=ledger, text=s_text, text_sha256=sha256_text(s_text), created_at="2026-10-11T15:00:00Z")


def stale_fixture(o: ClaimVerificationOutcome) -> bool:
    """True when the fixture provider refused its fixture because the claim text differs from the one the fixture was
    produced for: the translation failed by design of the harness, not of the infrastructure."""
    return o.translation.status is TranslationStatus.TRANSLATION_FAILED and any(STALE_FIXTURE_MARK in d for d in o.translation.diagnostics)


def outcome_record(o: ClaimVerificationOutcome) -> dict:
    """What a record keeps per claim outcome: enough to see why a claim is AMBIGUOUS and what a verdict rests on."""
    t, v = o.translation, o.verification
    flags = t.interpretation.ambiguity_flags if t.interpretation is not None else []
    rec = {"claim_id": o.claim_id, "display_status": o.display_status.value, "translation_status": t.status.value,
           "ambiguity_flags": [{"code": f.code, "message": f.message[:300], "alternatives": [a[:200] for a in f.alternatives]} for f in flags],
           "translation_diagnostics": [d[:300] for d in t.diagnostics][:8], "stale_fixture_refused": stale_fixture(o)}
    if v is not None:
        rec.update(engine_status=v.status.value, premises_relied_on=len(v.premises_relied_on), ungrounded_dependencies=len(v.ungrounded_dependencies),
                   unverified_dependencies=len(v.unverified_dependencies), ungrounded_dependency_ids=list(v.ungrounded_dependencies)[:16],
                   engine_diagnostics=[d.message[:200] for d in v.diagnostics][:3])
    return rec


def outcome_bucket(o: dict) -> str:
    return STALE_BUCKET if o.get("stale_fixture_refused") else o["display_status"]


def run_round(round_dir: Path) -> dict:
    spec_dir, tr_dir, syn_dir = round_dir / "specialists", round_dir / "translations", round_dir / "syntheses"
    translations = {p.stem: json.loads(p.read_text()) for p in tr_dir.glob("*.json")} if tr_dir.exists() else {}
    syntheses = {p.stem: json.loads(p.read_text()) for p in syn_dir.glob("*.json")} if syn_dir.exists() else {}
    hub = RouterHub(signing_key=KEY, config=CFG)
    records: list[dict] = []
    t_all = time.perf_counter()
    items = load_items(spec_dir)
    channels: dict[str, object] = {}
    delivered: dict[str, object] = {}  # file stem -> AgentMessage delivered to the router for the genuine reply
    peer_docs: dict[str, SuppliedText] = {}
    last_in_group: dict[str, str] = {}
    # file stem -> {claim_id: sha256 of the claim text each fixture was produced for}: carried by the translations file
    # or captured from the genuine transmission, and handed to the fixture provider for every later variant
    fixture_digests: dict[str, dict[str, str]] = {stem: dict(tr.get("claim_text_sha256") or {}) for stem, tr in translations.items()}
    for it in items:
        last_in_group[group_of(it)] = it["task_id"]
    # Two passes: every genuine reply (with peer relays and the combinator's synthesis) first, then the fault
    # mutations, so a synthesis is judged against the reports actually delivered for the task, not against the
    # mutated re-statements that follow.
    for pass_kind, item in [(pk, it) for pk in ("genuine", "mutations") for it in items]:
        sp = item["_path"]
        task_id = item["task_id"]
        agent = item["agent_id"]
        group = group_of(item)
        texts = supplied(item)
        if group not in channels:
            channels[group] = hub.open_task(group_plan(items, group))
        ch = channels[group]
        plan = ch.plan
        # translator agent output -> fixture provider; verify eligible claims through the real pipeline
        tr = translations.get(sp.stem)
        verify_fn = None
        if tr:
            digests = fixture_digests.setdefault(sp.stem, {})
            provider = FixtureTranslationProvider({cid: json.dumps(obj) if not isinstance(obj, str) else obj for cid, obj in tr["claims"].items()}, claim_text_sha256=digests)
            translator = Translator(provider)
            fixture_ids = set(tr["claims"])
            capture = digests if pass_kind == "genuine" else None

            def verify_fn(claim, report, _t=translator, _ids=fixture_ids, _capture=capture):
                if claim.claim_id not in _ids:
                    return None
                if _capture is not None and claim.claim_id not in _capture:
                    # the fixture was produced for the genuine text: bind it to that claim text (computed here, at verify
                    # time, from the parsed report) so a re-stated claim under the same id is refused later
                    _capture[claim.claim_id] = sha256_text(claim.claim_text)
                return verify_claim(claim, report, _t, config=CFG, signing_key=KEY)
        ch.verify_claim_fn = verify_fn
        if pass_kind == "genuine":
            peer_rec, peer_text, _relayed = relay_from_peer(ch, items, item, delivered, sp.name)
            if peer_rec is not None:
                records.append(peer_rec)
                if peer_text is None:
                    continue  # the peer's report never reached this agent through the hub; it has nothing to answer with
                peer_docs[task_id] = peer_text
                texts = [*texts, peer_text]
        elif task_id in peer_docs:
            texts = [*texts, peer_docs[task_id]]
        elif item.get("peer_of"):
            continue
        variants = [("genuine", item["response_text"], "NONE")] + [(k,) + mutate(item["response_text"], k) for k in MUTATIONS]
        if not texts:  # without a supplied text a quotation is unverifiable rather than refuted
            variants = [(k, t, ("CORE-SRC-003" if k in QUOTATION_MUTATIONS and e != "SKIP" else e)) for k, t, e in variants]
        for vi, (kind, text, expected) in enumerate(variants):
            if expected == "SKIP" or (kind == "genuine") != (pass_kind == "genuine"):
                continue
            rec = {"file": sp.name, "task_id": task_id, "subject": item["subject"], "variant": kind, "expected": expected, "task_type": plan.agent_task_types.get(agent, plan.task_type)}
            t0 = time.perf_counter()
            try:
                m, req, rq = hub.dispatch(group, agent, item["question"], texts)
                if m is None:
                    rec.update(functional=False, error=f"request rejected: {[f.code for f in rq.findings]}")
                    records.append(rec)
                    continue
                reply, rc = hub.receive(group, m.message_id, text, agent_id=agent, report_id=f"rep-{task_id}-{vi}")
                if kind == "genuine" and reply is not None:
                    delivered[sp.stem] = reply
                codes = sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings})
                rec["findings"] = [{"code": f.code, "severity": f.severity, "message": f.message[:300], "claim_ids": list(f.claim_ids)} for f in rc.findings]
                rec["subject_findings"] = [{"code": sf.code, "severity": sf.severity, "message": sf.message[:300], "claim_ids": list(sf.claim_ids)} for sf in rc.structural_findings]
                outcomes = [outcome_record(o) for o in rc.outcomes]
                stale = [o["claim_id"] for o in outcomes if o["stale_fixture_refused"]]
                internal = [o for o in rc.outcomes if o.display_status.value == "INTERNAL_ERROR" and not stale_fixture(o)] + [fc for fc in rc.formal_checks if fc.formal_status == "INTERNAL_ERROR"]
                ok = rc.status is not TransmissionStatus.REJECTED and not internal
                if expected not in ("NONE",):
                    ok = ok and expected in codes
                if kind == "self_certification":
                    # The self-report must be named on the receipt (core, hand-off or subject code), must not be
                    # parroted as an error, and must not reach the recipient as a material claim.
                    ok = ok and all(f.code != "INT-SUBJ-003" or "VERIFIED" not in f.message for f in rc.findings)
                    ok = ok and any(code in codes for code in SELF_REPORT_CODES)
                    ok = ok and not any(c["materiality"] == "material" and "VERIFIED" in c["claim_text"] for c in (reply.payload["claims"] if reply else []))
                rec.update(functional=ok, status=rc.status.value, branch=rc.branch, codes=codes, outcomes=outcomes, stale_fixtures_refused=stale,
                           formal_checks=[(fc.constraint_id, fc.formal_status, fc.satisfied) for fc in rc.formal_checks],
                           constraints=[(c.constraint_id, c.satisfied) for c in rc.constraint_results], coverage=[(c.item_id, c.addressed) for c in rc.coverage], claims=len(reply.payload["claims"]) if reply else None,
                           latency_ms=(time.perf_counter() - t0) * 1000.0, summary=rc.summary[:400])
                if kind == "genuine" and tr:
                    rec["fixture_claim_text_sha256"] = dict(fixture_digests.get(sp.stem, {}))
                if kind == "genuine" and reply is not None and task_id == last_in_group[group] and syntheses:
                    synthesis = group_synthesis(items, group, syntheses, delivered, plan)
                    if synthesis is None:
                        raise RuntimeError("no synthesis for a delivered group")
                    relayed, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, synthesis)
                    rec["synthesis"] = {"status": rr.status.value, "codes": sorted({f.code for f in rr.findings}), "delivered": relayed is not None, "findings": [{"code": f.code, "severity": f.severity, "message": f.message[:300]} for f in rr.findings]}
            except Exception as exc:  # a crash is a translator bug
                rec.update(functional=False, error=f"{type(exc).__name__}: {exc}", trace=traceback.format_exc()[-1500:])
            records.append(rec)
    total = len(records)
    functional = sum(1 for r in records if r.get("functional"))
    # Translation outcomes: the genuine pass verifies every eligible claim with a fixture exactly once, so its counts are
    # the distinct-claim counts (checked below over (file, claim_id)); the mutation variants repeat the same claims and
    # are totalled separately.
    genuine_counts: dict[str, int] = {}
    distinct: dict[str, set] = {}
    by_variant_outcomes: dict[str, dict[str, int]] = {}
    ungrounded_entailed = {"entailed": 0, "resting_only_on_ungrounded_premises": 0, "with_some_ungrounded_premise": 0}
    for r in records:
        for o in r.get("outcomes", []):
            bucket = outcome_bucket(o)
            bv = by_variant_outcomes.setdefault(r["variant"], {})
            bv[bucket] = bv.get(bucket, 0) + 1
            if r["variant"] == "genuine":
                genuine_counts[bucket] = genuine_counts.get(bucket, 0) + 1
                distinct.setdefault(bucket, set()).add((r["file"], o["claim_id"]))
                if o["display_status"] == "ENTAILED":
                    ungrounded_entailed["entailed"] += 1
                    if o.get("ungrounded_dependencies"):
                        ungrounded_entailed["with_some_ungrounded_premise"] += 1
                        if o["ungrounded_dependencies"] >= o.get("premises_relied_on", 0):
                            ungrounded_entailed["resting_only_on_ungrounded_premises"] += 1
    all_variants: dict[str, int] = {}
    for bv in by_variant_outcomes.values():
        for k, n in bv.items():
            all_variants[k] = all_variants.get(k, 0) + n
    by_variant: dict[str, list[int]] = {}
    for r in records:
        by_variant.setdefault(r["variant"], [0, 0])
        by_variant[r["variant"]][1] += 1
        by_variant[r["variant"]][0] += 1 if r.get("functional") else 0
    out = {"round": round_dir.name, "transmissions": total, "functional": functional, "functional_rate": (functional / total) if total else 0.0,
           "by_variant": {k: {"functional": v[0], "total": v[1]} for k, v in by_variant.items()}, "wall_s": time.perf_counter() - t_all,
           "provider_dependent_translation_outcomes": {"scope": "genuine pass only: each eligible claim with a fixture once", "by_status": genuine_counts,
                                                       "distinct_claims": {k: len(v) for k, v in distinct.items()}, "distinct_claims_total": len(set().union(*distinct.values())) if distinct else 0,
                                                       "entailed_dependencies": ungrounded_entailed},
           "translation_outcomes_by_variant": by_variant_outcomes, "translation_outcomes_all_variants": all_variants,
           "failures": [r for r in records if not r.get("functional")], "records": records}
    (round_dir / "results.json").write_text(json.dumps(out, indent=2, default=str))
    lines = [f"# Arena {round_dir.name}", "", f"Transmissions: {total}; functional: {functional} ({out['functional_rate']:.1%})", "", "| variant | functional | total |", "| --- | --- | --- |"]
    lines += [f"| {k} | {v['functional']} | {v['total']} |" for k, v in out["by_variant"].items()]
    lines += ["", "## Translation outcomes (provider-dependent; genuine pass, one outcome per eligible claim with a fixture)", ""]
    lines += [f"- {k}: {n} ({out['provider_dependent_translation_outcomes']['distinct_claims'].get(k, 0)} distinct claims)" for k, n in sorted(genuine_counts.items())] or ["(none)"]
    lines += [f"- ENTAILED verdicts resting only on ungrounded premises: {ungrounded_entailed['resting_only_on_ungrounded_premises']} of {ungrounded_entailed['entailed']}",
              f"- all variants together (the same claims repeated): {all_variants}"]
    lines += ["", "## Failures", ""] + ([f"- {r['file']} [{r['variant']}]: {r.get('error') or ('status ' + str(r.get('status')) + ' codes ' + str(r.get('codes')))}" for r in out["failures"]] or ["(none)"])
    (round_dir / "summary.md").write_text("\n".join(lines))
    return out


if __name__ == "__main__":
    rd = Path(sys.argv[1]).resolve()
    res = run_round(rd)
    print(json.dumps({k: res[k] for k in ("round", "transmissions", "functional", "functional_rate", "by_variant", "provider_dependent_translation_outcomes", "translation_outcomes_all_variants", "wall_s")}, indent=2))
    print("failures:", len(res["failures"]))
    print("results written to", rd / "results.json", "and", rd / "summary.md")
