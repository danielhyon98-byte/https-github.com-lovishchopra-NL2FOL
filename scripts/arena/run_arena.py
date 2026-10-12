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

STEM mutations (stem_mutations.py), applied in addition and only to answers of STEM subjects (the subjects routed to the
sciences, mathematics or computer_science branch): stem_arithmetic_slip (one stated result of a worked chain changed;
INT-SUBJ-001), stem_wrong_unit (a stated result's unit replaced by one of another dimension; ST-DIM-001 or ST-DIM-002),
stem_substitution (a value the request gives, substituted into a calculation, written as another value; INT-SUBJ-001).
Each is skipped when the answer has no site for it. The injection is named when a finding of its code names a claim
that carries the mutated text. Every other subject's round is unchanged.

Functional-rate definition (deterministic): a transmission counts as functional when the
hub produced a receipt without raising, the receipt status is consistent with the input
(a genuine response is not REJECTED; a response carrying an injected fault shows the
expected finding), and any translator output was either validated and decided by the
engine or rejected with diagnostics (never INTERNAL_ERROR; a fixture refused as stale is
neither). The expected finding must name the injection: a finding of the expected code (for
self_certification, one of SELF_REPORT_CODES) that names an injected claim (a delivered claim
whose text or quotation excerpt carries the injected words, INJECTION_MARKERS; for
altered_quotation the altered quotation) or quotes the injected words in its message, and that
the genuine record of the same task does not already carry. A code that is present only for what
the specialist's own text explains (hi-p3's CORE-SRC-003 for its own 'smokeless air') does not
count. A failing record says why under ``failure_reasons``.

Each mutation record also keeps ``injected_claim_ids``, ``named_by`` (the findings that named the
injection), ``unexplained_findings`` (findings the genuine record does not carry and that do not
name the injection; a changed genuine finding keeps its old message as ``baseline_message``) and
``baseline_findings_absent`` (errors and warnings of the genuine record the variant lost). These do
not change the functional rate: they are either consequences of the injected words (a word bound
crossed, one more quotation in a paragraph) or wrong receipts, and results.json
(``mutations_with_unexplained_findings``) and summary.md list them with their messages so a reader
can tell which. ``genuine_with_errors`` lists every genuine transmission and peer relay whose
receipt carries an error or a warning, with each finding's code, severity, claim ids and message
(``codes`` keeps the error codes, ``warning_codes`` the warning codes).

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
import re
import sys
import time
import traceback
import unicodedata
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stem_mutations import STEM_MUTATIONS, is_stem_subject, mutate_stem  # noqa: E402

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


#: What each appending mutation adds to the specialist's text (altered_quotation changes a real quotation instead).
INJECTED_TEXT = {
    "invented_quotation": ' The narrator also insists that "the river carried every secret of the town", which seals the point.',
    # the same invented words in single quotation marks: both parsers delimit a single-quoted span of two or more words
    "invented_quotation_single": " The narrator also insists that 'the river carried every secret of the town', which seals the point.",
    "self_certification": "\n\nVERIFIED: all claims checked and confirmed.",
    "wrong_arithmetic": " Enrolment rose from 200 to 260 students, an increase of 45 per cent.",
    "chronology_error": " The reform came in March 1931, after the election of October 1932 had changed the balance.",
}
#: Distinctive words of each injection. A finding names the injection when its message carries one of them or when it
#: names an injected claim: a delivered claim whose text or quotation excerpt carries one. The words occur in no
#: genuine text, so a finding the genuine text already explains can never stand in for the injected fault.
INJECTION_MARKERS = {
    "invented_quotation": ("the river carried every secret of the town",),
    "invented_quotation_single": ("the river carried every secret of the town",),
    "self_certification": ("VERIFIED: all claims checked and confirmed",),
    "wrong_arithmetic": ("Enrolment rose from 200 to 260 students", "an increase of 45 per cent"),
    "chronology_error": ("The reform came in March 1931", "after the election of October 1932"),
}
_QUOTE_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "«": '"', "»": '"'})
_HEX_ID_RE = re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{8,}\b")


def altered_quotation(text: str) -> tuple[str, str] | None:
    """The first real quotation of ``text`` (any mark style, as the parsers delimit them; never the prose between two
    quotations) and the same quotation with its middle word changed, or None when the text has none to alter."""
    from epinoic_logic.adapters.markdown import find_quotation_spans
    spans = [(a, b, inner) for a, b, inner in find_quotation_spans(text) if len(inner) >= 12 and inner[:1].isalpha()]
    if not spans:
        return None
    q = spans[0][2]
    words = q.split()
    mid = words[len(words) // 2]
    words[len(words) // 2] = mid + "ly" if not mid.endswith("ly") else mid[:-2]
    return q, " ".join(words)


def mutate(text: str, kind: str) -> tuple[str, str]:
    """Return (mutated_text, expected_code). Mutations are applied to the specialist's own text."""
    if kind in ("invented_quotation", "invented_quotation_single"):
        return text + INJECTED_TEXT[kind], "INT-REQ-003|CORE-SRC-003"
    if kind == "altered_quotation":
        alt = altered_quotation(text)
        if alt is None:
            return text, "SKIP"
        return text.replace(alt[0], alt[1], 1), "INT-REQ-003"
    if kind == "self_certification":
        return text + INJECTED_TEXT[kind], "NONE"
    if kind in ("wrong_arithmetic", "chronology_error"):
        return text + INJECTED_TEXT[kind], "INT-SUBJ-001"
    raise ValueError(kind)


class Injection(NamedTuple):
    """What identifies an injected fault on a receipt: its words (``markers``) and, for an appended paragraph, regular
    expressions for the place a finding may name it by instead (``locations``: 'paragraph 5, sentence 1')."""
    markers: tuple[str, ...]
    locations: tuple[str, ...] = ()
    words_added: int = 0


def paragraph_count(text: str) -> int:
    """Blank-line blocks with content, as the receipts number paragraphs."""
    return len([b for b in re.split(r"\n[ \t\r]*\n", text.replace("\r\n", "\n")) if b.strip()])


def stem_variant(text: str, question: str, kind: str) -> tuple[str, str]:
    """``(mutated_text, expected codes joined by '|')`` of a STEM mutation, or ``(text, 'SKIP')`` when the answer has no site."""
    inj = mutate_stem(text, question, kind)
    return (text, "SKIP") if inj is None else (inj.text, "|".join(inj.expected))


def injection(text: str, kind: str, question: str = "") -> Injection:
    """How ``mutate(text, kind)``'s injection is recognised on a receipt. For altered_quotation the marker is the altered
    quotation; for self_certification (appended as a paragraph of its own) a finding may also name its place; for a STEM
    mutation the marker is the mutated stretch of the answer."""
    if kind in STEM_MUTATIONS:
        inj = mutate_stem(text, question, kind)
        return Injection((inj.marker,) if inj is not None else (), (), 0)
    mutated = mutate(text, kind)[0]
    added = len(mutated.split()) - len(text.split())
    if kind == "altered_quotation":
        alt = altered_quotation(text)
        return Injection((alt[1],) if alt is not None else (), (), added)
    locations = (rf"\bparagraph {paragraph_count(mutated)}, sentence 1\b",) if kind == "self_certification" else ()
    return Injection(INJECTION_MARKERS.get(kind, ()), locations, added)


def norm_text(s: str) -> str:
    """Case-folded, quote-folded, whitespace-collapsed text for marker matching."""
    return " ".join(unicodedata.normalize("NFKC", s).translate(_QUOTE_FOLD).casefold().split())


def finding_dict(f) -> dict:
    """A receipt finding (IntegrityFinding or StructuralFinding) as the harness compares it: full message, never cut."""
    return {"code": f.code, "severity": f.severity, "claim_ids": list(f.claim_ids), "message": f.message}


def brief(f: dict, n: int = 300) -> dict:
    """A finding as a record keeps it (message and any genuine-record message cut to ``n`` characters)."""
    return {k: (v[:n] if k in ("message", "baseline_message") and isinstance(v, str) else v) for k, v in f.items()}


def finding_key(f: dict, task_id: str) -> tuple:
    """Identity of a finding across the genuine record and a variant of the same task: code, severity, claim ids and
    message, with the per-variant report id and generated hex ids (message, receipt, problem ids) folded."""
    msg = re.sub(rf"rep-{re.escape(task_id)}-\d+", f"rep-{task_id}-*", f["message"])
    return f["code"], f["severity"], tuple(sorted(f["claim_ids"])), norm_text(_HEX_ID_RE.sub("<id>", msg))


def injected_claim_ids(claims: list[dict], markers: tuple[str, ...]) -> list[str]:
    """Delivered claims that carry the injection: the claim text or a source excerpt contains one of the markers."""
    ms = [norm_text(m) for m in markers if m]
    out = []
    for c in claims:
        hay = [c.get("claim_text") or ""] + [r.get("excerpt") or "" for r in c.get("source_refs", [])]
        if any(m in norm_text(h) for h in hay for m in ms):
            out.append(c["claim_id"])
    return out


def names_injection(f: dict, inj: Injection, injected_ids) -> bool:
    """True when the finding names an injected claim, quotes the injected words or names the injected paragraph."""
    if set(f["claim_ids"]) & set(injected_ids):
        return True
    msg = norm_text(f["message"])
    return any(norm_text(m) in msg for m in inj.markers if m) or any(re.search(p, f["message"]) for p in inj.locations)


def findings_naming_injection(findings: list[dict], codes, inj: Injection, injected_ids, baseline: list[dict], task_id: str) -> list[dict]:
    """Findings of one of ``codes`` that name the injection and are not already on the genuine record (a finding the
    genuine text explains, such as a CORE-SRC-003 for a quotation the specialist itself wrote, never counts)."""
    base = {finding_key(b, task_id) for b in baseline}
    return [f for f in findings if f["code"] in codes and finding_key(f, task_id) not in base and names_injection(f, inj, injected_ids)]


def diff_against_baseline(findings: list[dict], baseline: list[dict], inj: Injection, injected_ids, task_id: str,
                          baseline_constraints: dict[str, str] | None = None) -> tuple[list[dict], list[dict]]:
    """(unexplained, absent). ``unexplained``: findings of a variant that the genuine record does not carry and that do
    not name the injection; when a genuine finding of the same code on the same claims changed, its message is kept as
    ``baseline_message``. ``absent``: error or warning findings of the genuine record that the variant lost without a
    changed counterpart. Either is a consequence of the injected words (a word bound crossed, a quotation count
    changed) or a wrong receipt; the record lists them so a reader can tell which. An unexplained INT-REQ-005 carries
    the genuine record's measurement of the same constraint (``genuine_constraint``, from ``baseline_constraints``) and
    the number of words the mutation added (``words_added``), so a crossed word bound can be checked by subtraction."""
    vkeys = {finding_key(f, task_id) for f in findings}
    bkeys = {finding_key(b, task_id) for b in baseline}
    gone = [b for b in baseline if finding_key(b, task_id) not in vkeys]
    paired: set[int] = set()
    unexplained = []
    for f in findings:
        if finding_key(f, task_id) in bkeys:
            continue
        match = next((i for i, b in enumerate(gone) if i not in paired and b["code"] == f["code"] and b["severity"] == f["severity"] and set(b["claim_ids"]) <= set(f["claim_ids"])), None)
        if match is not None:
            paired.add(match)
        if names_injection(f, inj, injected_ids):
            continue
        entry = dict(f)
        if match is not None:
            entry["baseline_message"] = gone[match]["message"]
        cm = re.match(r"constraint (\S+) not satisfied", f["message"]) if f["code"] == "INT-REQ-005" else None
        if cm:
            entry["genuine_constraint"] = (baseline_constraints or {}).get(cm.group(1))
            entry["words_added"] = inj.words_added
        unexplained.append(entry)
    absent = [b for i, b in enumerate(gone) if i not in paired and b["severity"] in ("error", "warning")]
    return unexplained, absent


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
               codes=sorted({f.code for f in rr.findings} | {sf.code for sf in rr.structural_findings}), summary=rr.summary[:400],
               findings=[brief(finding_dict(f)) for f in rr.findings], subject_findings=[brief(finding_dict(sf)) for sf in rr.structural_findings])
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


def _record_findings(r: dict) -> list[dict]:
    return r.get("findings", []) + r.get("subject_findings", [])


def genuine_findings_summary(records: list[dict]) -> list[dict]:
    """Every genuine transmission (and peer relay) whose receipt carries an error or a warning, with each such finding's
    code, severity, claim ids and message: a correct finding against a specialist fault, or a false one."""
    out = []
    for r in records:
        if r["variant"] not in ("genuine", "peer_relay"):
            continue
        shown = [f for f in _record_findings(r) if f["severity"] in ("error", "warning")]
        if shown:
            out.append({"file": r["file"], "variant": r["variant"], "status": r.get("status"),
                        "codes": sorted({f["code"] for f in shown if f["severity"] == "error"}),
                        "warning_codes": sorted({f["code"] for f in shown if f["severity"] == "warning"}), "findings": shown})
    return out


def unexplained_summary(records: list[dict]) -> list[dict]:
    """Mutation records carrying findings beyond the genuine record that do not name the injection, or that lost an
    error or warning of the genuine record (info-level additions are counted by code)."""
    out = []
    for r in records:
        un = r.get("unexplained_findings") or []
        shown = [f for f in un if f["severity"] in ("error", "warning")]
        info = sorted(f["code"] for f in un if f["severity"] == "info")
        absent = r.get("baseline_findings_absent") or []
        if shown or absent or info:
            out.append({"file": r["file"], "variant": r["variant"], "status": r.get("status"), "functional": bool(r.get("functional")),
                        "injected_claim_ids": r.get("injected_claim_ids", []), "unexplained": shown, "absent": absent, "unexplained_info": info})
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
    delivered: dict[str, object] = {}  # file stem -> AgentMessage delivered to the router for the genuine reply
    baseline: dict[str, list[dict]] = {}  # file stem -> every finding of the genuine receipt (full messages)
    baseline_constraints: dict[str, dict[str, str]] = {}  # file stem -> {constraint_id: detail} of the genuine receipt
    peer_docs: dict[str, SuppliedText] = {}
    last_in_group: dict[str, str] = {}
    # file stem -> {claim_id: sha256 of the claim text each fixture was produced for}: carried by the translations file
    # or captured from the genuine transmission, and handed to the fixture provider for every later variant
    fixture_digests: dict[str, dict[str, str]] = {stem: dict(tr.get("claim_text_sha256") or {}) for stem, tr in translations.items()}
    for it in items:
        last_in_group[group_of(it)] = it["task_id"]

    def make_verify_fn(stem: str, capture: bool):
        """Translator agent output -> fixture provider; verify eligible claims of the task ``stem`` through the real
        pipeline. With ``capture`` (the genuine pass) each fixture is bound to the claim text it is first served for."""
        tr = translations.get(stem)
        if not tr:
            return None
        digests = fixture_digests.setdefault(stem, {})
        provider = FixtureTranslationProvider({cid: json.dumps(obj) if not isinstance(obj, str) else obj for cid, obj in tr["claims"].items()}, claim_text_sha256=digests)

        def verify_fn(claim, report, _t=Translator(provider), _ids=frozenset(tr["claims"]), _capture=digests if capture else None):
            if claim.claim_id not in _ids:
                return None
            if _capture is not None and claim.claim_id not in _capture:
                # the fixture was produced for the genuine text: bind it to that claim text (computed here, at verify
                # time, from the parsed report) so a re-stated claim under the same id is refused later
                _capture[claim.claim_id] = sha256_text(claim.claim_text)
            return verify_claim(claim, report, _t, config=CFG, signing_key=KEY)
        return verify_fn

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
        tr = translations.get(sp.stem)
        verify_fn = make_verify_fn(sp.stem, pass_kind == "genuine")
        ch.verify_claim_fn = verify_fn
        # A delivered report recorded by relay_peer.py (the payload the peer-dependent agent actually read) is what the
        # genuine pass delivers for that task, so the forward measured here is byte-identical to the recorded one.
        recorded_payload = None
        for other in items:
            if other.get("peer_of") == task_id:
                rel_path = round_dir / "relayed" / f"{other['task_id']}.json"
                if rel_path.exists():
                    rel = json.loads(rel_path.read_text())
                    if rel.get("delivered") and rel.get("payload"):
                        recorded_payload = rel["payload"]
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
        if is_stem_subject(item["subject"]):  # STEM faults, only on STEM subjects (after the shared ones: their indices are unchanged)
            variants += [(k,) + stem_variant(item["response_text"], item["question"], k) for k in STEM_MUTATIONS]
        for vi, (kind, text, expected) in enumerate(variants):
            if expected == "SKIP" or (kind == "genuine") != (pass_kind == "genuine"):
                continue
            rec = {"file": sp.name, "task_id": task_id, "subject": item["subject"], "variant": kind, "expected": expected, "task_type": plan.agent_task_types.get(agent, plan.task_type)}
            t0 = time.perf_counter()
            hub_key = group
            if kind != "genuine":
                # every mutation gets its own hub task (same plan), so its receipt is that of a single delivery and never
                # carries the supersession or stale-forward findings a re-statement on the genuine reply's channel would
                hub_key = f"{group}::{kind}"
                vch = hub.open_task(plan)  # the hub registers it under plan.task_id: put the group's channel back and key this one
                hub.channels[plan.task_id] = channels[group]
                hub.channels[hub_key] = vch
                vch.verify_claim_fn = verify_fn
                channels[hub_key] = vch
                if item.get("peer_of"):  # the peer's genuine report is delivered and forwarded on this channel too
                    peer_item = next(it for it in items if it["task_id"] == item["peer_of"])
                    pm_, _, _ = hub.dispatch(hub_key, peer_item["agent_id"], peer_item["question"], supplied(peer_item))
                    peer_payload = delivered.get(peer_item["_path"].stem)
                    # verified with the peer's own translations, as in the genuine pass, so the cross-agent pool the
                    # mutated reply is checked against holds the peer's formalizations too (not an empty peer share)
                    vch.verify_claim_fn = make_verify_fn(peer_item["_path"].stem, False)
                    preply, _ = hub.receive(hub_key, pm_.message_id, SpecialistReport.model_validate(peer_payload.payload) if peer_payload is not None else peer_item["response_text"],
                                            agent_id=peer_item["agent_id"], report_id=f"rep-{peer_item['task_id']}-0")
                    vch.verify_claim_fn = verify_fn
                    _r, ptext, _m = relay_from_peer(vch, items, item, {peer_item["_path"].stem: preply} if preply is not None else {}, sp.name)
                    texts = [*supplied(item), *([ptext] if ptext is not None else [])]
            rec["channel"] = hub_key
            try:
                m, req, rq = hub.dispatch(hub_key, agent, item["question"], texts)
                if m is None:
                    rec.update(functional=False, error=f"request rejected: {[f.code for f in rq.findings]}")
                    records.append(rec)
                    continue
                payload_in = SpecialistReport.model_validate(recorded_payload) if (kind == "genuine" and recorded_payload is not None) else text
                reply, rc = hub.receive(hub_key, m.message_id, payload_in, agent_id=agent, report_id=f"rep-{task_id}-{vi}")
                if kind == "genuine" and reply is not None:
                    delivered[sp.stem] = reply
                codes = sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings})
                found = [finding_dict(f) for f in rc.findings] + [finding_dict(sf) for sf in rc.structural_findings]
                rec["findings"] = [brief(finding_dict(f)) for f in rc.findings]
                rec["subject_findings"] = [brief(finding_dict(sf)) for sf in rc.structural_findings]
                outcomes = [outcome_record(o) for o in rc.outcomes]
                stale = [o["claim_id"] for o in outcomes if o["stale_fixture_refused"]]
                internal = [o for o in rc.outcomes if o.display_status.value == "INTERNAL_ERROR" and not stale_fixture(o)] + [fc for fc in rc.formal_checks if fc.formal_status == "INTERNAL_ERROR"]
                reasons = []
                if rc.status is TransmissionStatus.REJECTED:
                    reasons.append("receipt REJECTED")
                if internal:
                    reasons.append(f"{len(internal)} INTERNAL_ERROR outcome(s) or formal check(s)")
                if kind == "genuine":
                    baseline[sp.stem] = found
                    baseline_constraints[sp.stem] = {c.constraint_id: c.detail for c in rc.constraint_results}
                else:
                    # A fault counts as named only by a finding of the expected code that names an injected claim or
                    # quotes the injected words, and that the genuine record does not already carry.
                    inj = injection(item["response_text"], kind, item.get("question", ""))
                    injected = injected_claim_ids(reply.payload["claims"] if reply else [], inj.markers)
                    expected_codes = SELF_REPORT_CODES if kind == "self_certification" else tuple(c for c in expected.split("|") if c != "NONE")
                    named = findings_naming_injection(found, expected_codes, inj, injected, baseline.get(sp.stem, []), task_id)
                    unexplained, absent = diff_against_baseline(found, baseline.get(sp.stem, []), inj, injected, task_id, baseline_constraints.get(sp.stem))
                    rec.update(injected_claim_ids=injected, named_by=[brief(f) for f in named], unexplained_findings=[brief(f) for f in unexplained],
                               baseline_findings_absent=[brief(f) for f in absent])
                    if expected_codes and not named:
                        present = sorted(set(codes) & set(expected_codes))
                        reasons.append(f"no {'/'.join(expected_codes)} finding names the injected claims {injected} or the injected words"
                                       + (f" ({present} present, but only for what the genuine text already carries or for other claims)" if present else ""))
                if kind == "self_certification":
                    # The self-report must be named on the receipt (core, hand-off or subject code; checked above), must
                    # not be parroted as an error, and must not reach the recipient as a material claim.
                    if not all(f.code != "INT-SUBJ-003" or "VERIFIED" not in f.message for f in rc.findings):
                        reasons.append("the self-certification is parroted as an INT-SUBJ-003 error")
                    if any(c["materiality"] == "material" and "VERIFIED" in c["claim_text"] for c in (reply.payload["claims"] if reply else [])):
                        reasons.append("the self-certification reaches the recipient as a material claim")
                ok = not reasons
                if reasons:
                    rec["failure_reasons"] = reasons
                rec.update(functional=ok, status=rc.status.value, branch=rc.branch, codes=codes, outcomes=outcomes, stale_fixtures_refused=stale,
                           formal_checks=[(fc.constraint_id, fc.formal_status, fc.satisfied) for fc in rc.formal_checks],
                           constraints=[(c.constraint_id, c.satisfied) for c in rc.constraint_results], constraint_details={c.constraint_id: c.detail[:300] for c in rc.constraint_results}, coverage=[(c.item_id, c.addressed) for c in rc.coverage], claims=len(reply.payload["claims"]) if reply else None,
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
           "genuine_with_errors": genuine_findings_summary(records),
           "mutations_with_unexplained_findings": unexplained_summary(records),
           "failures": [r for r in records if not r.get("functional")], "records": records}
    (round_dir / "results.json").write_text(json.dumps(out, indent=2, default=str))
    lines = [f"# Arena {round_dir.name}", "", f"Transmissions: {total}; functional: {functional} ({out['functional_rate']:.1%})", "", "| variant | functional | total |", "| --- | --- | --- |"]
    lines += [f"| {k} | {v['functional']} | {v['total']} |" for k, v in out["by_variant"].items()]
    lines += ["", "## Translation outcomes (provider-dependent; genuine pass, one outcome per eligible claim with a fixture)", ""]
    lines += [f"- {k}: {n} ({out['provider_dependent_translation_outcomes']['distinct_claims'].get(k, 0)} distinct claims)" for k, n in sorted(genuine_counts.items())] or ["(none)"]
    lines += [f"- ENTAILED verdicts resting only on ungrounded premises: {ungrounded_entailed['resting_only_on_ungrounded_premises']} of {ungrounded_entailed['entailed']}",
              f"- all variants together (the same claims repeated): {all_variants}"]
    lines += ["", "## Genuine transmissions carrying error- or warning-level findings (correct against a specialist fault, or a false finding: read the message)", ""]
    for g in out["genuine_with_errors"]:
        lines.append(f"- {g['file']} [{g['variant']}] {g['status']}: errors {g['codes']}, warnings {g['warning_codes']}")
        lines += [f"  - {f['severity']} {f['code']} {f['claim_ids']}: {f['message']}" for f in g["findings"]]
    if not out["genuine_with_errors"]:
        lines.append("(none)")
    lines += ["", "## Mutations: findings beyond the genuine record that do not name the injection (a consequence of the injected words, such as a word bound crossed, or a wrong receipt: read the message)", ""]
    for u in out["mutations_with_unexplained_findings"]:
        lines.append(f"- {u['file']} [{u['variant']}] {u['status']}: injected claims {u['injected_claim_ids']}")
        lines += [f"  - {f['severity']} {f['code']} {f['claim_ids']}: {f['message']}" + (f" (genuine record: {f['baseline_message']})" if f.get("baseline_message") else "")
                  + (f" (genuine record: {f.get('genuine_constraint')}; the mutation added {f['words_added']} words)" if "words_added" in f else "") for f in u["unexplained"]]
        lines += [f"  - lost from the genuine record: {f['severity']} {f['code']} {f['claim_ids']}: {f['message']}" for f in u["absent"]]
        if u["unexplained_info"]:
            lines.append(f"  - info-level: {u['unexplained_info']}")
    if not out["mutations_with_unexplained_findings"]:
        lines.append("(none)")
    lines += ["", "## Failures", ""] + ([f"- {r['file']} [{r['variant']}]: {r.get('error') or '; '.join(r.get('failure_reasons') or []) or ('status ' + str(r.get('status')) + ' codes ' + str(r.get('codes')))}" for r in out["failures"]] or ["(none)"])
    (round_dir / "summary.md").write_text("\n".join(lines))
    return out


if __name__ == "__main__":
    rd = Path(sys.argv[1]).resolve()
    res = run_round(rd)
    print(json.dumps({k: res[k] for k in ("round", "transmissions", "functional", "functional_rate", "by_variant", "provider_dependent_translation_outcomes", "translation_outcomes_all_variants", "wall_s")}, indent=2))
    print("failures:", len(res["failures"]))
    print("genuine transmissions with errors or warnings:", len(res["genuine_with_errors"]), "| mutation records with unexplained findings:", len(res["mutations_with_unexplained_findings"]))
    print("results written to", rd / "results.json", "and", rd / "summary.md")
