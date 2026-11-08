#!/usr/bin/env python3
"""Specialist feedback and revision in the contained run (design section 53 of ``docs/OVERSEER_DESIGN.md``;
``epinoic_overseer.feedback``).

Two parts, every transfer through a hub carrying the contained harness's auditor (``ovs_harness.new_auditor``: inline
replay, the shadow channel on every task); no model, no network:

1. **The recorded rounds.** A copy of each requested round is replayed by the arena's feedback replay
   (``run_arena._feedback_replay``: each group's genuine traffic, peer relays included, then the infrastructure's revision
   request for every genuine answer, never a synthesis). For every request issued, the answer's own text is delivered
   again as its revision under a new report id (an identity revision, whose outcome is known in advance); then the task
   audit runs with the shadow, each revision's outcome is decided, and the original request and the revision request are
   consolidated. Checked per answer: the channel refused no request the infrastructure built (no INT-REV-001); the audit
   raises no OVS-FB-001; the shadow agrees on the revision request and the revision (no OVS-RCPT-004, 005 or 008 naming
   them); the original's receipt is unchanged; every issued request carries an allowlisted flaw that is not advisory and
   no other code; the delivered revision supersedes the original in the consolidation; and a fed-back error that
   persists leaves the revision undeliverable and the chain escalated.
2. **Controls** (the checks are not vacuous), on a synthetic Physics answer with a wrong arithmetic step: a corrected
   revision is fixed and the chain done; a block stripped of its signature is refused by the channel (INT-REV-001,
   nothing sent); a block re-signed with a fabricated audit flaw passes the channel but not the audit (OVS-FB-001, the
   request and the answer replying to it AUDIT_FAILED).

Gates: ``revision_requests_bind`` (no INT-REV-001 and no OVS-FB-001 on an infrastructure-built request, every issued
request with an allowlisted flaw that is not advisory, every delivered revision superseding its original, every
persisting error withheld and escalated, and the controls as expected) and ``shadow_agrees_on_revision_transfers``.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ovs_harness as H  # noqa: E402

SHADOW_CODES = ("OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-008")
#: The per-answer checks of the gate ``revision_requests_bind`` (the shadow's has a gate of its own).
BIND_CHECKS = ("flaws_allowlisted", "no_ovs_fb_001", "original_receipt_unchanged", "supersedes_the_original", "persisting_error_withheld_and_escalated")
PH_QUESTION = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."
PH_WRONG = ("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². "
            "The acceleration is therefore 6.0 m s⁻².")
PH_RIGHT = ("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻². "
            "The acceleration is therefore 5.0 m s⁻².")


def _codes_naming(audit: Any, codes: tuple[str, ...], mids: set[str]) -> list[str]:
    return sorted(f.code for f in audit.report.findings if f.code in codes and mids & set(f.message_ids))


def _answer_checks(hub: Any, key: str, entry: dict, audit: Any) -> dict:
    """The checks of one identity revision (module docstring, part 1)."""
    from epinoic_logic.api.channel import CODE_RULES
    issue, rc2 = entry["issue"], entry["revision_receipt"]
    mids = {issue.message.message_id, rc2.message_id}
    held = next((r for r in hub.channels[key].receipts if r.message_id == entry["receipt"].message_id), None)
    outcome = hub.revision_outcome(key, rc2.message_id)
    resp = hub.consolidate(key, request_message_ids=[entry["request"].message_id, issue.message.message_id])
    orig = next((e for e in resp.excluded if e.message_id == entry["receipt"].message_id), None)
    flaws = list(issue.revision.flaws)
    persisting = [f for f in outcome.flaws if f.bucket == "persisted" and f.severity == "error"]
    delivered = entry.get("revised") is not None
    checks = {
        "flaws_allowlisted": all(f.code in CODE_RULES and f.rule in CODE_RULES[f.code][1] for f in flaws) and any(f.basis != "advisory" for f in flaws),
        "no_ovs_fb_001": not _codes_naming(audit, ("OVS-FB-001",), mids),
        "shadow_agrees": not _codes_naming(audit, SHADOW_CODES, mids),
        "original_receipt_unchanged": held is not None and held.model_dump(mode="json") == entry["receipt_dump"],
        "supersedes_the_original": (not delivered) or (orig is not None and any("superseded by its revision" in r for r in orig.reasons)),
        "persisting_error_withheld_and_escalated": (not persisting) or (rc2.message_id in resp.excluded_message_ids() and outcome.next == "escalated"),
    }
    return {"task_id": entry["item"]["task_id"], "agent_id": entry["item"]["agent_id"], "ok": all(checks.values()), "checks": checks,
            "flaws": [f"{f.code} {f.basis}" for f in flaws], "revision_status": rc2.status.value, "buckets": [f"{f.code} {f.bucket}" for f in outcome.flaws],
            "next": outcome.next, "shadow_codes": _codes_naming(audit, SHADOW_CODES, mids), "fb_codes": _codes_naming(audit, ("OVS-FB-001",), mids)}


def run_recorded_round(name: str, src: Path, out: Path) -> dict:
    """Part 1 on a copy of one recorded round."""
    RA = H.arena()
    copy = H.copy_round(src, out / "rounds", name=name)
    aud = H.new_auditor(H.keyring_for("arena"))
    res: dict = {"round": name, "answers": 0, "issued": 0, "no_actionable_flaw": 0, "refused_by_channel": [], "not_replayed": [], "tasks": [], "errors": []}
    hub = None
    try:
        items = RA.load_items(copy / "specialists")
        hub, entries = RA._feedback_replay(items, RA.load_recorded_relays(copy, items), auditor=aud)
        groups: dict[str, list[dict]] = {}
        for task_id, entry in entries.items():
            issue = entry.get("issue")
            if entry.get("error") or issue is None:
                res["not_replayed"].append(f"{task_id}: {entry.get('error')}")
                continue
            res["answers"] += 1
            if issue.reason == "refused_by_channel":
                res["refused_by_channel"].append(task_id)
            if not issue.allowed:
                res["no_actionable_flaw"] += issue.reason == "no_actionable_flaw"
                continue
            res["issued"] += 1
            r2, rc2 = hub.receive(entry["key"], issue.message.message_id, entry["item"]["response_text"], agent_id=entry["item"]["agent_id"],
                                  report_id=f"rep-{task_id}-rev1")
            entry.update(revised=r2, revision_receipt=rc2)
            groups.setdefault(entry["key"], []).append(entry)
        for key, group in groups.items():
            audit = hub.audit(key, shadow=True)
            for entry in group:
                try:
                    res["tasks"].append(_answer_checks(hub, key, entry, audit))
                except Exception as exc:  # recorded as a failed check, never raised
                    res["tasks"].append({"task_id": entry["item"]["task_id"], "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    except Exception as exc:
        res["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if hub is not None:
            hub.close()
        aud.close()
        shutil.rmtree(copy, ignore_errors=True)
    res["ok"] = not res["errors"] and not res["refused_by_channel"] and all(t.get("ok") for t in res["tasks"])
    return res


def _physics_hub():
    from epinoic_logic.branches.hub import RouterHub
    from epinoic_logic.integrity import WorkPlan
    RA = H.arena()
    aud = H.new_auditor(H.keyring_for("arena"))
    hub = RouterHub(signing_key=RA.KEY, key_id="hub", config=RA.CFG, auditor=aud)
    plan = WorkPlan(plan_id="plan-ph-ctl", request_id="req-ph-ctl", task_id="ph-ctl", subject="Physics", task_type="short_answer",
                    selected_agent_ids=["physics-specialist"])
    hub.open_task(plan)
    m, _r, _q = hub.dispatch("ph-ctl", "physics-specialist", PH_QUESTION, [])
    a, rc = hub.receive("ph-ctl", m.message_id, PH_WRONG, agent_id="physics-specialist", report_id="rep-ph-ctl-0")
    return hub, aud, m, a


def run_controls() -> dict:
    """Part 2: the corrected revision, the unsigned block and the fabricated audit flaw."""
    from epinoic_logic.api.channel import RevisionEvidence, RevisionFlaw, keep_list, named_claim_ids, render_instruction, rendered_digest, revision_id_of
    from epinoic_overseer import feedback as F
    out: dict = {}
    hub, aud, m, a = _physics_hub()
    try:
        issue = hub.request_revision("ph-ctl", a.message_id)
        a2, _rc2 = hub.receive("ph-ctl", issue.message.message_id, PH_RIGHT, agent_id="physics-specialist", report_id="rep-ph-ctl-1")
        oc = hub.revision_outcome("ph-ctl", a2.message_id)
        out["corrected_revision_fixed"] = {"ok": issue.allowed and [(f.code, f.bucket) for f in oc.flaws] == [("INT-SUBJ-001", "fixed")] and oc.next == "done",
                                           "observed": [f"{f.code} {f.bucket}" for f in oc.flaws] + [oc.next]}
    finally:
        hub.close()
        aud.close()
    for case in ("unsigned", "fabricated_audit_flaw"):
        hub, aud, m, a = _physics_hub()
        try:
            uid = hub.channels["ph-ctl"].channel_uid
            base = F.build_revision_request(aud.view(uid), a.message_id, task_audit=hub.audit("ph-ctl", shadow=True), keyring=aud.keyring).block
            if case == "unsigned":
                block = base.model_copy(update={"signature": None, "signature_key_id": None})
            else:
                claim = base.flaws[0].claims[0]
                fake = RevisionFlaw(flaw_id=f"f{len(base.flaws) + 1}", code="OVS-FID-005", severity="error", flaw_class="fidelity", basis="audit",
                                    rule="self.certification", params={}, instruction=render_instruction("self.certification", {}), removal_ok=True,
                                    claims=[claim], evidence=[RevisionEvidence(kind="audit_finding", ref=f"{base.task_audit_id}#000000000000")], signature="c" * 64)
                flaws = [*base.flaws, fake]
                view = aud.view(uid)
                b = base.model_copy(update={"flaws": flaws, "must_not_change": keep_list(view.by_message[m.message_id].request, view.by_message[a.message_id].report,
                                                                                        *named_claim_ids(flaws))})
                b = b.model_copy(update={"rendered_sha256": rendered_digest(b)})
                block = F.sign_revision(b.model_copy(update={"revision_id": revision_id_of(b)}), aud.keyring)
            ch = hub.channels["ph-ctl"]
            orig = ch.requests[m.message_id]
            m2, _req, rq = ch.request("router", "physics-specialist", orig.user_input, list(orig.supplied_texts), items=list(orig.items),
                                      constraints=list(orig.constraints), revision=block)
            audit = hub.audit("ph-ctl", shadow=True)
            fb = [f for f in audit.report.findings if f.code == "OVS-FB-001" and rq.message_id in f.message_ids]
            if case == "unsigned":
                ok = m2 is None and "INT-REV-001" in {f.code for f in rq.findings}
            else:
                a3, _rc3 = hub.receive("ph-ctl", m2.message_id, PH_RIGHT, agent_id="physics-specialist", report_id="rep-ph-ctl-2") if m2 is not None else (None, None)
                audit = hub.audit("ph-ctl", shadow=True)
                fb = [f for f in audit.report.findings if f.code == "OVS-FB-001" and rq.message_id in f.message_ids]
                ok = (m2 is not None and bool(fb) and audit.transfer_states.get(rq.message_id) == "AUDIT_FAILED"
                      and a3 is not None and audit.transfer_states.get(a3.message_id) == "AUDIT_FAILED")
            out[case] = {"ok": ok, "observed": {"sent": m2 is not None, "request_codes": sorted({f.code for f in rq.findings}), "ovs_fb_001": len(fb)}}
        except Exception as exc:  # recorded as a failed control, never raised
            out[case] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            hub.close()
            aud.close()
    return out


def run(out: Path, rounds: Optional[list[tuple[str, Path]]] = None) -> dict:
    t0 = time.perf_counter()
    controls = run_controls()
    recorded = [run_recorded_round(name, src, out) for name, src in (rounds or [])]
    tasks = [t for r in recorded for t in r["tasks"]]
    bind = {"ok": all(c["ok"] for c in controls.values()) and all(not r["errors"] and not r["refused_by_channel"] for r in recorded)
            and all("error" not in t and all(t["checks"][k] for k in BIND_CHECKS) for t in tasks),
            "controls": {k: v["ok"] for k, v in controls.items()}, "answers": sum(r["answers"] for r in recorded), "requests_issued": sum(r["issued"] for r in recorded),
            "negative_controls": sum(r["no_actionable_flaw"] for r in recorded), "channel_refusals": sum(len(r["refused_by_channel"]) for r in recorded),
            "ovs_fb_001": sum(len(t.get("fb_codes", [])) for t in tasks)}
    shadow = {"ok": all("error" not in t and (t.get("checks") or {}).get("shadow_agrees") for t in tasks),
              "revision_transfers": 2 * len(tasks), "shadow_findings": sum(len(t.get("shadow_codes", [])) for t in tasks)}
    return {"format": "overseer-revision-probes/1.0", "gates": {"revision_requests_bind": bind, "shadow_agrees_on_revision_transfers": shadow},
            "controls": controls, "recorded": recorded, "wall_s": round(time.perf_counter() - t0, 2)}


def summary_md(doc: dict) -> str:
    L = ["# Specialist feedback and revision", ""]
    for name, g in doc["gates"].items():
        L.append(f"- gate {name}: {'PASS' if g['ok'] else 'FAIL'} {json.dumps({k: v for k, v in g.items() if k != 'ok'})}")
    L += ["", "## Controls", ""] + [f"- {k}: {'PASS' if v['ok'] else 'FAIL'} {json.dumps(v.get('observed') or v.get('error'))}" for k, v in doc["controls"].items()]
    L += ["", "## Recorded rounds (identity revisions)", ""]
    for r in doc["recorded"]:
        L.append(f"- {r['round']}: {'PASS' if r['ok'] else 'FAIL'}; answers {r['answers']}, requests issued {r['issued']}, no actionable flaw {r['no_actionable_flaw']}, "
                 f"refused by the channel {r['refused_by_channel'] or 'none'}" + (f"; errors {r['errors']}" if r["errors"] else ""))
        for t in r["tasks"]:
            failed = sorted(k for k, ok in (t.get("checks") or {}).items() if not ok)
            L.append(f"  - {t['task_id']}: {'PASS' if t.get('ok') else 'FAIL'}; flaws {t.get('flaws')}, revision {t.get('revision_status')}, outcome {t.get('buckets')} "
                     f"{t.get('next')}" + (f"; failed {failed}" if failed else "") + (f"; error {t['error']}" if t.get("error") else ""))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Specialist feedback and revision probes (contained run stage)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--rounds", type=Path, help="the directory holding the recorded rounds (copied, never written)")
    ap.add_argument("--round", action="append", default=[])
    args = ap.parse_args()
    found = H.round_dirs(args.rounds, args.round) if args.rounds else []
    doc = run(H.check_output_dir(args.out, inputs=[args.rounds] if args.rounds else []), found)
    H.write_json(args.out / "revisions.json", doc)
    (args.out / "revisions.md").write_text(summary_md(doc), encoding="utf-8")
    print(json.dumps(doc["gates"], indent=1))
