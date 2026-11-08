#!/usr/bin/env python3
"""The twofold (N_FOLD) review of combined answers in the contained run (architecture step 3; ``docs/OVERSEER_DESIGN.md``
section 52; ``epinoic_overseer.twofold``).

Two parts, every overseer agent an ``OverseerAgentRunner`` the pool builds from the exported, loaded pack, with a scripted
provider (harness code reading the dossier as data, never a model):

1. **The synthetic combined answer** (the tampering suite's two-subject task, ``tamper.run_synthetic``: the English and
   the History specialists' answers joined by the combinator), through an audited hub, in four cases: a fault in the
   English source that the synthesis keeps (its source review's ``quotation_absent`` confirmed, the merged review's
   ``synthesis_carries_fault`` confirmed through that fault's own finding), one it drops (the same source fault; the
   accusation of it as carried refuted), one it adds (a figure no source states: the synthesis receipt names it, the
   merged review is escalated, and an accusation of it as carried is unresolved), and a faithful control (nothing).
2. **The recorded rounds' combined answers**: every genuine channel of a replayed round whose journal holds a combined
   answer, reviewed N_FOLD through ``hub.review_pool`` by silent instances: the plan reviews it N_FOLD, every part is
   reviewed, the temporary context is complete, scoped to the request, within its bound, recorded in the signed audit and
   discarded, the audit verifies, no clearance changes, every part dossier is issued to its part, and every call's
   system text is the pack's composition for its dossier.

The gate ``twofold_combined_answers`` passes when every synthetic case is as expected and every recorded combined
answer passes every check. No network, no model, no key of any provider.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ovs_harness as H  # noqa: E402

CASES = ("keeps", "drops", "adds", "faithful")
#: What each synthetic case must give: the source reviews' outcomes, the merged review's, whether a carried fault is
#: confirmed, and whether the merged review is escalated (two instances).
EXPECTED = {
    "keeps": {"source_1": [("quotation_absent", "confirmed")], "merged": [("synthesis_carries_fault", "confirmed")], "carried": True, "context_faults": 1},
    "drops": {"source_1": [("quotation_absent", "confirmed")], "merged": [("synthesis_carries_fault", "refuted")], "carried": False, "context_faults": 1},
    "adds": {"source_1": [], "merged": [("synthesis_carries_fault", "unresolved")], "carried": False, "context_faults": 0, "merged_escalated": True},
    "faithful": {"source_1": [], "merged": [], "carried": False, "context_faults": 0},
}


def _synthetic_inputs(case: str):
    import tamper as T
    from epinoic_logic.integrity import LedgerEntry, SynthesizedClaim
    from epinoic_logic.ir.schema import SourceRef
    inserted = dict(claim_id="en-ev2", claim_text="the town grew rich on their silence", claim_role="evidence", materiality="supporting",
                    source_refs=[SourceRef(document_id="doc-mill", excerpt="the town grew rich on their silence")])
    claims = T.claims_with(replace={"en-ev2": inserted}) if case in ("keeps", "drops") else None
    report = T.english_report(claims=claims) if claims is not None else None
    base = [SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried"),
            SynthesizedClaim(claim_id="s2", text="The Factory Act of 1833 banned the employment of children under nine in textile mills.",
                             source_claim_ids=["h1.1"], transformation="carried"),
            SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"],
                             transformation="carried")]
    if case == "keeps":
        syn = T.default_synthesis(claims=[*base, SynthesizedClaim(claim_id="s4", text="the town grew rich on their silence", source_claim_ids=["en-ev2"],
                                                                  transformation="carried")],
                                  ledger=[LedgerEntry(source_claim_ids=["en-ev1", "en-an"], transformation="dropped", reason="supporting evidence summarised by the carried point"),
                                          LedgerEntry(source_claim_ids=["h1.2"], transformation="dropped", reason="supporting detail beyond the synthesis's scope")])
    elif case == "adds":
        syn = T.default_synthesis(claims=[base[0], SynthesizedClaim(claim_id="s2", text="The Factory Act of 1833 banned the employment of children under ten "
                                                                    "in textile mills.", source_claim_ids=["h1.1"], transformation="carried"), base[2]])
    else:
        syn = T.default_synthesis()
    return report, syn


def _probe(case: str) -> Callable[[dict], dict]:
    """The scripted reply of every instance of a synthetic case."""
    def reply(d: dict) -> dict:
        r = d.get("review") or {}
        if r.get("role") == "source" and r.get("source") == 1 and case in ("keeps", "drops"):
            t = next(t for t in d["transfers"] if t["kind"] == "response")
            p = H.index_pointer(d, "claim", "en-ev2", report_id="rep-en-1")
            return H.verdict_dict(d, [H.accusation("a1", "quotation_absent", [{"pointer": p + "/claim_text", "quote": "the town grew rich on their silence"},
                                                                              {"pointer": t["at"] + "/payload/original_response"}],
                                                   message_ids=[t["message_id"]], claim_ids=["en-ev2"], report_ids=["rep-en-1"], document_ids=["doc-mill"])])
        if r.get("role") == "merged":
            target = {"keeps": ("s4", "en-ev2", "rep-en-1"), "drops": ("s1", "en-ev2", "rep-en-1"), "adds": ("s2", "h1.1", "rep-hi-1")}.get(case)
            if target:
                syn = next(t for t in d["transfers"] if t["kind"] == "relay_synthesis")
                p = H.index_pointer(d, "synthesized_claim", target[0])
                return H.verdict_dict(d, [H.accusation("m1", "synthesis_carries_fault", [{"pointer": p + "/source_claim_ids"},
                                                                                          {"pointer": "/temporary_context/sources"}],
                                                       message_ids=[syn["message_id"]], receipt_ids=[syn["receipt_id"]], claim_ids=list(target[:2]),
                                                       report_ids=[target[2]])])
        return H.verdict_dict(d)
    return reply


def _silent(d: dict) -> dict:
    return H.verdict_dict(d)


def _outcomes(part: Any) -> list[tuple[str, str]]:
    return sorted((x.kind, x.outcome) for a in part.assessments for x in a.accusations)


def _review_checks(hub: Any, key: str, review: Any, plan: Any, providers: list, pack: Any, before: dict, after: dict) -> dict:
    """What every N_FOLD review must hold, whatever its verdicts."""
    from epinoic_overseer import verify_audit
    tw = review.twofold
    uid = hub.channel_for(key).channel_uid
    rec = tw.context_record if tw is not None else {}
    calls = [c for p in providers for c in p.calls]
    dossiers = [H.dossier_of_user_text(c[1]) for c in calls]
    lay = plan.twofold.get(uid)
    notes = "\n".join(review.audit.coverage.notes)
    checks = {
        "planned_n_fold": lay is not None,
        "every_part_reviewed": tw is not None and all(p.assessments for p in tw.sources) and bool(tw.merged.assessments),
        "context_complete_and_bounded": bool(rec) and rec["complete"] and rec["bytes"] <= rec["max_bytes"] == 65536,
        "context_scoped_to_the_request": bool(rec) and (rec["scope"]["task_id"], rec["scope"]["request_id"]) == (review.task_audit.task_id, review.task_audit.request_id),
        "context_recorded_and_discarded": tw is not None and tw.context_discarded and f"temporary context sha256 {tw.context_sha256}" in notes
        and "discarded after the request" in notes,
        "audit_verifies": verify_audit(review.audit, hub.auditor.keyring),
        "clearances_unchanged": before == after,
        "part_dossiers_issued_to_their_parts": bool(dossiers) and all((d.get("review") or {}).get("method") == "N_FOLD" for d in dossiers)
        and all(("temporary_context" in d) == ((d.get("review") or {}).get("role") == "merged") for d in dossiers),
        "system_text_is_the_pack": bool(calls) and all(c[0] == pack.system_text_for(d) and hashlib.sha256(c[0].encode("utf-8")).hexdigest()
                                                       == pack.composition_sha256(pack.modules_for(d)) for c, d in zip(calls, dossiers)),
    }
    return {"checks": checks, "ok": all(checks.values()), "sources": tw.layout.n if tw is not None else 0,
            "agents": {"sources": [list(s) for s in lay.sources] if lay else [], "merged": list(lay.merged) if lay else []},
            "context": {"sha256": tw.context_sha256 if tw is not None else None, "bytes": rec.get("bytes"),
                        "faults": sum(len(s["confirmed"]) for s in rec.get("sources", []))},
            "calls": len(calls), "admission": {"origin": plan.admission.origin, "refusal": plan.admission.refusal}}


def run_synthetic_cases(pack: Any) -> dict:
    """The four synthetic cases, each through its own audited hub."""
    import tamper as T
    from epinoic_overseer import OverseerPool
    out: dict[str, Any] = {}
    for case in CASES:
        aud = H.new_auditor(H.keyring_for("synthetic"))
        try:
            report, syn = _synthetic_inputs(case)
            run = T.run_synthetic(aud, en_report=report, synthesis=syn)
            providers: list = []

            def factory(agent_id: str, _case: str = case) -> Any:
                p = H.ScriptedProvider(_probe(_case), name=f"harness-twofold-{agent_id}")
                providers.append(p)
                return p
            ch = run.channel
            before = {rc.message_id: run.hub.clearance(run.key, rc.message_id).state for rc in ch.receipts}
            pool = OverseerPool(pack, factory)
            pr = run.hub.review_pool([run.key], pool)
            after = {rc.message_id: run.hub.clearance(run.key, rc.message_id).state for rc in ch.receipts}
            review = pr.reviews[ch.channel_uid]
            res = _review_checks(run.hub, run.key, review, pr.plan, providers, pack, before, after)
            tw = review.twofold
            exp = EXPECTED[case]
            observed = {"source_1": _outcomes(tw.sources[0]), "source_2": _outcomes(tw.sources[1]), "merged": sorted(set(_outcomes(tw.merged))),
                        "carried": bool(tw.carried), "context_faults": res["context"]["faults"],
                        "merged_instances": len(pr.plan.twofold[ch.channel_uid].merged),
                        "synthesis_receipt_codes": sorted({f.code for f in ch.receipts[-1].findings})}
            expected_ok = set(observed["source_1"]) == set(exp["source_1"]) and bool(observed["source_1"]) == bool(exp["source_1"]) \
                and observed["source_2"] == [] and observed["merged"] == sorted(set(exp["merged"])) and observed["carried"] == exp["carried"] \
                and observed["context_faults"] == exp["context_faults"] \
                and (not exp.get("merged_escalated") or (observed["merged_instances"] == 2 and "INT-LEDGER-023" in observed["synthesis_receipt_codes"]))
            res.update(case=case, expected={k: v for k, v in exp.items()}, observed=observed, as_expected=expected_ok, ok=res["ok"] and expected_ok)
            out[case] = res
        finally:
            aud.close()
    return out


def run_recorded_round(name: str, src: Path, out: Path, pack: Any) -> dict:
    """Every combined answer of a recorded round's genuine pass (a copy of the round, replayed through an audited hub),
    reviewed N_FOLD by silent instances."""
    from epinoic_overseer import OverseerPool
    from epinoic_overseer.twofold import combined_layout
    copy = H.copy_round(src, out / "rounds", name=name)
    aud = H.new_auditor(H.keyring_for("arena"))
    found: list[dict] = []
    try:
        rr = H.replay_round(copy, aud, genuine_only=True)
        for c in rr.channels:
            if c.variant != "genuine" or combined_layout(aud.view(c.uid)) is None:
                continue
            hub = rr.hub_for(c.key)
            providers: list = []

            def factory(agent_id: str) -> Any:
                p = H.ScriptedProvider(_silent, name=f"harness-twofold-{agent_id}")
                providers.append(p)
                return p
            ch = hub.channel_for(c.key)
            before = {rc.message_id: hub.clearance(c.key, rc.message_id).state for rc in ch.receipts}
            try:
                pr = hub.review_pool([c.key], OverseerPool(pack, factory))
                after = {rc.message_id: hub.clearance(c.key, rc.message_id).state for rc in ch.receipts}
                res = _review_checks(hub, c.key, pr.reviews[ch.channel_uid], pr.plan, providers, pack, before, after)
            except Exception as exc:  # recorded as a failed check, never raised
                res = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            res.update(round=name, channel=c.key)
            found.append(res)
    finally:
        aud.close()
    for q in list(copy.iterdir()):  # the copy's inputs are dropped; the arena's outputs are not needed here
        if q.is_dir():
            import shutil
            shutil.rmtree(q)
        else:
            q.unlink()
    return {"round": name, "combined_answers": found}


def run(out: Path, pack: Any, rounds: Optional[list[tuple[str, Path]]] = None) -> dict:
    t0 = time.perf_counter()
    synthetic = run_synthetic_cases(pack)
    recorded = [run_recorded_round(name, src, out, pack) for name, src in (rounds or [])]
    combined = [x for r in recorded for x in r["combined_answers"]]
    gate = {"ok": all(v["ok"] for v in synthetic.values()) and all(x["ok"] for x in combined) and bool(synthetic),
            "synthetic_cases": {k: v["ok"] for k, v in synthetic.items()},
            "recorded_combined_answers": len(combined), "recorded_ok": sum(1 for x in combined if x["ok"]),
            "recorded": sorted(f"{x['round']}/{x['channel']} ({x.get('sources', 0)} sources)" for x in combined)}
    return {"format": "overseer-twofold-probes/1.0", "gate": gate, "synthetic": synthetic, "recorded": recorded,
            "wall_s": round(time.perf_counter() - t0, 2)}


def summary_md(doc: dict) -> str:
    g = doc["gate"]
    L = ["# Twofold (N_FOLD) review of combined answers", "", f"Gate: {'PASS' if g['ok'] else 'FAIL'}", "", "## Synthetic combined answer", ""]
    for case, v in doc["synthetic"].items():
        L.append(f"- {case}: {'PASS' if v['ok'] else 'FAIL'}; observed {json.dumps(v['observed'])}; checks "
                 f"{sorted(k for k, ok in v['checks'].items() if not ok) or 'all hold'}")
    L += ["", "## Recorded combined answers", ""]
    for r in doc["recorded"]:
        for x in r["combined_answers"]:
            L.append(f"- {x['round']}/{x['channel']}: {'PASS' if x['ok'] else 'FAIL'}; {x.get('sources')} sources, instances {json.dumps(x.get('agents'))}, "
                     f"context {json.dumps(x.get('context'))}, failed checks {sorted(k for k, ok in (x.get('checks') or {}).items() if not ok) or 'none'}"
                     + (f"; error {x['error']}" if x.get("error") else ""))
    return "\n".join(L) + "\n"
