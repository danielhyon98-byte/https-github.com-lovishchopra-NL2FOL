#!/usr/bin/env python3
"""Arena driver: feed real specialist-agent outputs through the hub and measure.

Inputs (one round directory):
  <round>/specialists/*.json   {task_id, subject, agent_id, question, supplied_texts:[{document_id,title?,author?,text}], response_text}
  <round>/translations/*.json  optional: {report_id, claims: {claim_id: <translator JSON object>}}
  <round>/syntheses/*.json     optional: {report_id, claims:[{text, source_claim_ids, certainty, transformation}], dropped:[{source_claim_ids, reason}]}
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
from epinoic_logic.translate.contracts import SuppliedText, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

KEY = b"arena-signing-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def mutate(text: str, kind: str) -> tuple[str, str]:
    """Return (mutated_text, expected_code). Mutations are applied to the specialist's own text."""
    if kind == "invented_quotation":
        return text + ' The narrator also insists that "the river carried every secret of the town", which seals the point.', "INT-REQ-003"
    if kind == "altered_quotation":
        m = re.search(r'"([^"]{12,})"', text)
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


def run_round(round_dir: Path) -> dict:
    spec_dir, tr_dir, syn_dir = round_dir / "specialists", round_dir / "translations", round_dir / "syntheses"
    translations = {p.stem: json.loads(p.read_text()) for p in tr_dir.glob("*.json")} if tr_dir.exists() else {}
    syntheses = {p.stem: json.loads(p.read_text()) for p in syn_dir.glob("*.json")} if syn_dir.exists() else {}
    hub = RouterHub(signing_key=KEY, config=CFG)
    records: list[dict] = []
    t_all = time.perf_counter()
    for sp in sorted(spec_dir.glob("*.json")):
        item = json.loads(sp.read_text())
        task_id = item["task_id"]
        agent = item["agent_id"]
        texts = [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"], locator_scheme=t.get("locator_scheme", "none")) for t in item.get("supplied_texts", [])]
        plan = WorkPlan(plan_id=f"plan-{task_id}", request_id=f"req-{task_id}", task_id=task_id, subject=item["subject"], task_type=item.get("task_type", "analytical_paragraph"),
                        selected_agent_ids=[agent, "dummy-combinator"], allowed_document_ids=[t.document_id for t in texts])
        # translator agent output -> fixture provider; verify eligible claims through the real pipeline
        tr = translations.get(sp.stem)
        verify_fn = None
        if tr:
            provider = FixtureTranslationProvider({cid: json.dumps(obj) if not isinstance(obj, str) else obj for cid, obj in tr["claims"].items()})
            translator = Translator(provider)

            def verify_fn(claim, report, _t=translator):
                return verify_claim(claim, report, _t, config=CFG, signing_key=KEY) if claim.claim_id in tr["claims"] else None
        hub.verify_claim_fn = verify_fn
        ch = hub.open_task(plan)
        variants = [("genuine", item["response_text"], "NONE")] + [(k,) + mutate(item["response_text"], k) for k in ("invented_quotation", "altered_quotation", "self_certification", "wrong_arithmetic", "chronology_error")]
        if not texts:  # without a supplied text a quotation is unverifiable rather than refuted
            variants = [(k, t, ("CORE-SRC-003" if k in ("invented_quotation", "altered_quotation") else e)) for k, t, e in variants]
        for vi, (kind, text, expected) in enumerate(variants):
            if expected == "SKIP":
                continue
            rec = {"file": sp.name, "task_id": task_id, "subject": item["subject"], "variant": kind, "expected": expected}
            t0 = time.perf_counter()
            try:
                m, req, rq = hub.dispatch(task_id, agent, item["question"], texts)
                if m is None:
                    rec.update(functional=False, error=f"request rejected: {[f.code for f in rq.findings]}")
                    records.append(rec)
                    continue
                reply, rc = hub.receive(task_id, m.message_id, text, agent_id=agent, report_id=f"rep-{task_id}-{vi}")
                codes = sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings})
                outcomes = [(o.claim_id, o.display_status.value) for o in rc.outcomes]
                internal = [o for o in rc.outcomes if o.display_status.value == "INTERNAL_ERROR"] + [fc for fc in rc.formal_checks if fc.formal_status == "INTERNAL_ERROR"]
                ok = rc.status is not TransmissionStatus.REJECTED and not internal
                if expected not in ("NONE",):
                    ok = ok and expected in codes
                if kind == "self_certification":
                    ok = ok and all(f.code != "INT-SUBJ-003" or "VERIFIED" not in f.message for f in rc.findings)
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
