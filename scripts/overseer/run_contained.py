#!/usr/bin/env python3
"""Contained run of the Overseer (``docs/OVERSEER_DESIGN.md`` section 13.5): recorded arena rounds replayed through
``RouterHub`` with the transfer auditor attached, the tampering suite, and overseer agents configured ONLY from a pack
exported by the package's exporter.

    PYTHONPATH=src python scripts/overseer/run_contained.py --out DIR [--rounds ROOT] [--round r2 ...] [--pack EXPORTED_PACK]
                                                          [--probe-scope sample|all] [--no-tamper] [--replies DIR --transfers EXPORT_DIR]

Steps, every output under ``--out`` (never inside a recorded round):

1. **The pack.** Unless ``--pack`` names an exported pack, the INSTALLED pack is exported with the package's exporter
   into ``DIR/pack`` (a directory and a deterministic zip), and that exported copy is loaded with the package's loader
   (every file against the manifest, the pack digest against the digest pinned in the code). A pack the loader refuses
   stops the run before any agent is built (exit status 2). Every overseer agent of the run is an
   ``OverseerAgentRunner`` built from that loaded copy; the harness has no option and no file that carries prompt text,
   and nothing else configures an agent.
2. **Rounds.** Each recorded round (default r2 to r5, each only when present) is COPIED into ``DIR/rounds/<name>`` and
   ``run_arena.run_round`` runs on the copy with ``RouterHub`` replaced by a hub that carries the auditor; a second copy
   runs WITHOUT the auditor, and the two arena results are compared (the auditor must change nothing). Every channel
   (the genuine pass and each fault mutation) gets a signed task audit with the shadow channel. Reported: the genuine
   transfers and the auditor's false alarms on them (``OVS-*`` errors other than DIV, which are true rule findings and
   listed with their classification), the arena's own injected faults (the receipt names each one; the overseer agrees
   when the shadow re-derivation reproduces the receipt and no ``OVS-*`` error names the transfer) and the auditor's
   additions on them (the known channel misses), replay agreement, and the translations checked.
3. **Recorded overseer reports** (``<round>/overseers/*.json``, read-only) are agent self-reports: their functional rate
   is recomputed from the recorded ``results.json`` and the comparison is reported, never trusted.
4. **Tampering suite** (``tamper.py``, unless ``--no-tamper``): every case, its agents built from the same exported pack.
5. **Overseer agents** (scripted probe providers, no network, no model): ``hub.review`` runs probes whose replies
   exercise every validation outcome (a clean verdict, a confirmed accusation, a lie about a signed result, invented
   identifiers, a meaning fault, prose, the "no dossier" object, a verdict naming another pack, a provider failure) on
   every genuine channel and one mutation channel per round (``--probe-scope all``: every channel). Asserted: each
   probe's outcome, and that a review changes no clearance.
6. **Replies** (``--replies DIR --transfers EXPORT_DIR``): verdict texts recorded by whoever ran a live model configured
   from the same exported pack, keyed by dossier digest (``<sha256>.json``), served through runners built from the
   exported pack to the dossiers of an ``export_dossier.py`` export (rebuilt from its transfer records), then scored
   (``score_verdicts.py``). A run without ``--replies`` claims nothing about any model.

Outputs: ``results.json`` and ``summary.md``, the rounds' arena outputs, ``tamper/`` and ``pack/``. Exit status 0 when
every gate passes, 1 when one fails, 2 when the run was stopped (a refused pack, a refused output directory).

Deviations from ``docs/OVERSEER_DESIGN.md`` section 13.5, listed as the stage requires: the arena's results are compared
with a run of the same copy without the auditor (the recorded ``results.json`` of a round may predate later fixes, so
it is reported, not compared); per-task signed audits are summarised in ``results.json`` (each channel's state, codes
and audit id) rather than written one file per task; replies need ``--transfers``, because a dossier digest names the
exact transfers it was issued from and a fresh replay issues new message ids.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ovs_harness as H  # noqa: E402

from epinoic_logic.overseer import KIND_CHECKS, PackError, PackIdentity, verify_audit  # noqa: E402
from epinoic_logic.translate.providers import ProviderError  # noqa: E402

RESULTS_FORMAT = "overseer-contained/1.0"
#: Codes that are true rule findings on genuine transfers, never false alarms (listed apart).
RULE_CODES = ("OVS-DIV-001", "OVS-DIV-002")
#: Codes by which the shadow re-derivation disagrees with a receipt.
SHADOW_DISAGREE = ("OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-008")
OTHER_PACK = PackIdentity(name="overseer-knowledge-docs", version="1.1", sha256="cd" * 32)


class Stopped(RuntimeError):
    """The run was stopped before any agent was built."""


# ============================================================================================ the pack
def configure_pack(out: Path, pack_path: Optional[Path], after_export: Optional[Callable[[Path], None]] = None) -> tuple[Any, dict]:
    """The pack every agent of the run is built from: an export of the installed pack written into ``out/pack`` by the
    package's exporter (or the exported pack ``pack_path``), loaded by the package's loader. ``after_export`` (tests)
    runs between the export and the load. Raises :class:`Stopped` when the loader refuses it: no agent is built."""
    from epinoic_logic.overseer.export import ExportError, export_pack
    info: dict[str, Any] = {}
    try:
        if pack_path is None:
            res = export_pack(out / "pack", zip_archive=True)
            info.update(exported_dir=str(res.directory), exported_zip=str(res.zip_path), zip_sha256=res.zip_sha256)
            target = res.directory
        else:
            target = Path(pack_path)
            info["given"] = str(target)
        if after_export is not None:
            after_export(Path(target))
        pack = H.load_exported_pack(target)
        if pack_path is None:
            zpack = H.load_exported_pack(res.zip_path)
            if zpack.identity != pack.identity:
                raise Stopped("the exported zip and directory load to different identities")
    except PackError as exc:
        raise Stopped(f"the exported pack was refused by the loader ({exc.reason}); no agent was built") from exc
    except ExportError as exc:
        raise Stopped(f"the exporter refused ({exc.reason}); no agent was built") from exc
    info.update(identity=pack.identity.model_dump(), source=pack.source, system_sha256=pack.system_sha256, prompt_version=pack.prompt_version)
    return pack, info


# ============================================================================================ probes (scripted providers: harness code reading data)
def _auditor_target(d: dict) -> Optional[tuple[str, dict]]:
    for f in (d.get("auditor") or {}).get("findings", []):
        if f.get("severity") == "info" or not f.get("message_ids"):
            continue
        kind = next((k for k, codes in KIND_CHECKS.items() if f["code"] in codes), None)
        if kind is not None and H.transfer_of(d, f["message_ids"][0]) is not None:
            return kind, f
    return None


def probe_confirm(d: dict):
    hit = _auditor_target(d)
    if hit is None:
        return H.verdict_dict(d)
    kind, f = hit
    t = H.transfer_of(d, f["message_ids"][0])
    claims = [c for c in f.get("claim_ids", []) if H.index_pointer(d, "claim", c) or H.index_pointer(d, "synthesized_claim", c)][:1]
    return H.verdict_dict(d, [H.accusation("a1", kind, [{"pointer": t["at"]}], message_ids=[t["message_id"]], receipt_ids=[t["receipt_id"]] if t["receipt_id"] else [],
                                           claim_ids=claims, statement="The auditor's finding on this transfer.")])


def _first_result(d: dict) -> Optional[tuple[dict, str]]:
    for t in d["transfers"]:
        for rid in t.get("cited_result_ids") or []:
            if rid in d["results"]:
                return t, rid
    return None


def probe_liar(d: dict):
    hit = _first_result(d)
    if hit is None:
        return H.verdict_dict(d)
    t, rid = hit
    status = d["results"][rid]["status"]
    wrong = "COUNTEREXAMPLE" if status != "COUNTEREXAMPLE" else "ENTAILED"
    acc = H.accusation("a1", "result_unsigned_or_forged", [{"pointer": f"/results/{rid}/signature_present"}], message_ids=[t["message_id"]], result_ids=[rid],
                       statement="The result looks forged.")
    return H.verdict_dict(d, [acc], [{"result_id": rid, "asserted_status": wrong, "pointer": f"/results/{rid}/status"}])


def probe_invent(d: dict):
    t = d["transfers"][0]
    return H.verdict_dict(d, [H.accusation("a1", "claim_not_in_response", [{"pointer": t["at"] + "/payload/claims/999/claim_text"}], message_ids=["message-that-does-not-exist"],
                                           claim_ids=["claim-that-does-not-exist"], statement="An identifier no dossier holds.")])


def probe_unfaithful(d: dict):
    links = d["links"].get("translations") or []
    link = next((x for x in links if x.get("translation_pointer")), None)
    if link is None:
        return H.verdict_dict(d)
    return H.verdict_dict(d, [H.accusation("a1", "translation_unfaithful", [{"pointer": link["claim_pointer"] + "/claim_text"}, {"pointer": link["translation_pointer"]}],
                                           message_ids=[link["message_id"]], claim_ids=[link["claim_id"]], report_ids=[link["report_id"]],
                                           statement="The problem does not say what the claim says.")])


PROBES: tuple[tuple[str, str, Callable[[dict], Any], str], ...] = (
    # agent id, lens, reply, what the infrastructure must make of it
    ("overseer-silent-1", "general", lambda d: H.verdict_dict(d), "valid, no accusation"),
    ("overseer-confirm-1", "custody_results", probe_confirm, "confirmed (AGENT-003) when the audit holds a finding, else no accusation"),
    ("overseer-liar-1", "custody_results", probe_liar, "refuted by the signed result (AGENT-001), accusation and engine statement"),
    ("overseer-invent-1", "content_fidelity", probe_invent, "unverifiable (AGENT-002)"),
    ("overseer-unfaithful-1", "translation_fidelity", probe_unfaithful, "unresolved (AGENT-004), human review"),
    ("overseer-prose-1", "peer_synthesis", lambda d: "I reviewed the transfers and found everything in order.", "AGENT-005 unparseable"),
    ("overseer-nodossier-1", "general", lambda d: {"no_dossier": True}, "AGENT-005 no_dossier (no review)"),
    ("overseer-otherpack-1", "general", lambda d: H.verdict_dict(d, pack=OTHER_PACK.model_dump()), "AGENT-005 pack_unknown"),
    ("overseer-down-1", "general", lambda d: ProviderError("provider unavailable (scripted)"), "provider_error (no review)"),
)


def build_probe_runners(pack: Any) -> list[tuple[Any, Any]]:
    """Every probe agent: the package's runner configured from the loaded exported pack and a scripted provider."""
    out = []
    for agent_id, lens, reply, _expect in PROBES:
        provider = H.ScriptedProvider(reply, name=f"harness-probe-{agent_id}")
        out.append((H.build_runner(pack, provider, agent_id=agent_id, lens=lens), provider))
    return out


def check_probe(agent_id: str, run: Any, assessment: Any) -> tuple[bool, str]:
    """Whether the infrastructure made of a probe's reply what it must."""
    if agent_id == "overseer-silent-1":
        return (run.status == "submitted" and assessment is not None and assessment.valid and not assessment.accusations), "valid, no accusation"
    if agent_id == "overseer-confirm-1":
        if assessment is None or not assessment.valid:
            return False, "not assessed"
        if not assessment.accusations:
            return True, "no auditor finding to confirm"
        return assessment.accusations[0].outcome == "confirmed", assessment.accusations[0].outcome
    if agent_id == "overseer-liar-1":
        if assessment is None or not assessment.valid:
            return False, "not assessed"
        if not assessment.accusations:
            return True, "no cited result"
        a, s = assessment.accusations[0], assessment.engine_statements[0]
        return (a.outcome == "refuted" and a.refuted_by == "signed_result" and s.outcome == "refuted" and s.refuted_by == "signed_result"), f"{a.outcome}/{s.outcome}"
    if agent_id == "overseer-invent-1":
        return (assessment is not None and bool(assessment.accusations) and assessment.accusations[0].outcome == "unverifiable"), \
            assessment.accusations[0].outcome if assessment is not None and assessment.accusations else "none"
    if agent_id == "overseer-unfaithful-1":
        if assessment is None or not assessment.valid:
            return False, "not assessed"
        if not assessment.accusations:
            return True, "no translation link"
        return assessment.accusations[0].outcome == "unresolved", assessment.accusations[0].outcome
    if agent_id == "overseer-prose-1":
        return (run.status == "invalid" and run.reason == "unparseable" and run.finding.code == "OVS-AGENT-005"), str(run.reason)
    if agent_id == "overseer-nodossier-1":
        return (run.status == "invalid" and run.reason == "no_dossier"), str(run.reason)
    if agent_id == "overseer-otherpack-1":
        return (run.status == "invalid" and run.reason == "pack_unknown"), str(run.reason)
    if agent_id == "overseer-down-1":
        return run.status == "provider_error", str(run.reason)
    return False, "unknown probe"


def review_channel(hub: Any, key: str, pack: Any) -> dict:
    """``hub.review`` of one channel with every probe; clearances compared before and after."""
    ch = hub.channel_for(key)
    mids = [rc.message_id for rc in ch.receipts]
    before = {m: (c.state, tuple(c.codes)) for m in mids for c in [hub.clearance(key, m)]}
    runners = build_probe_runners(pack)
    review = hub.review(key, [r for r, _p in runners], mode="informed")
    after = {m: (c.state, tuple(c.codes)) for m in mids for c in [hub.clearance(key, m)]}
    by_agent = {a.agent_id: a for a in review.assessments}
    runs = {r.agent_id: r for r in review.runs}
    probes = {}
    for agent_id, _lens, _reply, expect in PROBES:
        ok, observed = check_probe(agent_id, runs.get(agent_id), by_agent.get(agent_id)) if agent_id in runs else (False, "did not run")
        probes[agent_id] = {"expected": expect, "observed": observed, "ok": ok}
    systems = {p.calls[0][0] for _r, p in runners if p.calls}
    return {"key": key, "probes": probes, "clearances_unchanged": before == after, "verdicts_audit_verifies": verify_audit(review.audit, hub.auditor.keyring),
            "verdicts_audit_state": review.audit.state, "task_audit_state": review.task_audit.state,
            "agent_codes": dict(Counter(f.code for f in review.audit.report.findings)),
            "system_text_is_the_pack": systems == {pack.system_text()}, "provider_calls": sum(len(p.calls) for _r, p in runners)}


# ============================================================================================ rounds
def _arena_signature(results: dict) -> list[tuple]:
    return sorted((r.get("file"), r.get("variant"), r.get("status"), bool(r.get("functional")), tuple(r.get("codes") or ())) for r in results.get("records", []))


def recorded_self_reports(src: Path, recorded_results: Optional[dict]) -> list[dict]:
    """The recorded overseer reports of a round, treated as agent self-reports: their functional rate recomputed."""
    out = []
    odir = src / "overseers"
    if not odir.is_dir():
        return out
    recomputed = None
    if recorded_results and recorded_results.get("transmissions"):
        recomputed = recorded_results["functional"] / recorded_results["transmissions"]
    for p in sorted(odir.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except ValueError:
            out.append({"file": p.name, "error": "not JSON"})
            continue
        claimed = d.get("infrastructure_functional_rate") if isinstance(d, dict) else None
        row = {"file": p.name, "claimed_functional_rate": claimed, "recomputed_from_recorded_results": round(recomputed, 4) if recomputed is not None else None,
               "bugs_listed": len(d.get("bugs", [])) if isinstance(d, dict) else None, "treated_as": "agent self-report (advisory)"}
        if isinstance(claimed, (int, float)) and recomputed is not None:
            row["agrees"] = abs(claimed - recomputed) < 0.0005
            row["difference"] = round(claimed - recomputed, 4)
        out.append(row)
    return out


def run_round_contained(name: str, src: Path, out: Path, pack: Any, *, probe_scope: str) -> dict:
    rdir = out / "rounds"
    plain_copy = H.copy_round(src, rdir / "without-auditor", name=name)
    plain = H.arena().run_round(plain_copy)
    copy = H.copy_round(src, rdir, name=name)
    aud = H.new_auditor(H.keyring_for("arena"))
    try:
        rr = H.replay_round(copy, aud)
        rec: dict[str, Any] = {"round": name, "transmissions": rr.results["transmissions"], "functional": rr.results["functional"],
                               "arena_unchanged_by_the_auditor": _arena_signature(rr.results) == _arena_signature(plain)
                               and (rr.results["functional"], rr.results["transmissions"]) == (plain["functional"], plain["transmissions"])}
        recorded = H.read_json(src / "results.json") if (src / "results.json").exists() else None
        if recorded:
            rec["recorded_results"] = {"functional": recorded.get("functional"), "transmissions": recorded.get("transmissions")}
        records_by_channel = defaultdict(list)
        for r in rr.results["records"]:
            records_by_channel[r.get("channel")].append(r)
        genuine = {"channels": 0, "transfers": 0, "false_alarms": [], "rule_findings": [], "states": Counter()}
        mutations: list[dict] = []
        replay = {"results_replayed": 0, "disagreements": [], "inconclusive": 0}
        translations = {"checked": 0, "trn_codes_on_genuine": Counter()}
        channels = []
        for c in rr.channels:
            audit = aud.audit(c.uid)
            codes = Counter(f.code for f in audit.report.findings)
            channels.append({"key": c.key, "variant": c.variant, "audit_id": audit.audit_id, "state": audit.state, "codes": dict(codes),
                             "verifies": verify_audit(audit, aud.keyring), "transfers": len(audit.message_ids)})
            replay["results_replayed"] += audit.coverage.results_replayed
            replay["disagreements"] += [f"{c.key}: {f.message[:200]}" for f in audit.report.findings if f.code == "OVS-RES-007"]
            replay["inconclusive"] += codes.get("OVS-RES-008", 0)
            translations["checked"] += len(audit.translations)
            if c.variant == "genuine":
                genuine["channels"] += 1
                genuine["transfers"] += len(audit.message_ids)
                genuine["states"][audit.state] += 1
                genuine["false_alarms"] += [{"channel": c.key, "code": f.code, "message": f.message[:300]} for f in audit.report.findings
                                            if f.severity == "error" and f.code not in RULE_CODES]
                for d in audit.divergences:
                    genuine["rule_findings"].append({"channel": c.key, "int_code": d.int_code, "classification": d.classification, "owner": d.owner,
                                                     "severity": d.severity, "claim_ids": list(d.claim_ids)})
                for f in audit.report.findings:
                    if f.code.startswith("OVS-TRN"):
                        translations["trn_codes_on_genuine"][f.code] += 1
            else:
                for r in records_by_channel.get(c.key, []):
                    if r.get("variant") == "peer_relay":
                        continue
                    shadow = [f.code for f in audit.report.findings if f.code in SHADOW_DISAGREE]
                    errors = [f.code for f in audit.report.findings if f.severity == "error" and f.code not in RULE_CODES]
                    additions = sorted({f.code for f in audit.report.findings if f.code not in RULE_CODES and f.code != "OVS-PEER-003"})
                    mutations.append({"channel": c.key, "file": r.get("file"), "kind": r.get("variant"), "receipt_named_it": bool(r.get("functional")),
                                      "named_by": sorted({f.get("code") for f in r.get("named_by", [])}), "status": r.get("status"),
                                      "overseer_agrees_with_receipt": not shadow and not errors, "shadow_disagreements": shadow,
                                      "auditor_additions": additions})
        genuine["states"] = dict(genuine["states"])
        translations["trn_codes_on_genuine"] = dict(translations["trn_codes_on_genuine"])
        rec.update(channels=channels, genuine=genuine, mutations=mutations, replay=replay, translations=translations,
                   recorded_overseer_reports=recorded_self_reports(src, recorded))
        # overseer agents: probes through hub.review
        keys = [c.key for c in rr.channels if c.variant == "genuine"]
        muts = [c.key for c in rr.channels if c.variant not in ("genuine", "closed")]
        keys += muts if probe_scope == "all" else muts[:1]
        reviews = []
        for key in keys:
            hub = rr.hub_for(key)
            try:
                reviews.append(review_channel(hub, key, pack))
            except Exception as exc:
                reviews.append({"key": key, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1200:]})
        rec["reviews"] = reviews
    finally:
        aud.close()
    for p in (copy, plain_copy):  # keep the arena's own outputs as evidence, drop the copied inputs
        for q in list(p.iterdir()):
            if q.name not in ("results.json", "summary.md"):
                shutil.rmtree(q) if q.is_dir() else q.unlink()
    return rec


# ============================================================================================ replies
def run_replies(out: Path, pack: Any, replies_dir: Path, transfers: Path) -> dict:
    """Recorded verdict texts served through runners built from the exported pack to the dossiers of an export."""
    import score_verdicts as SV
    from epinoic_logic.translate.providers import FixtureCompletionProvider
    replies, infos, ignored = SV.read_replies(replies_dir)
    provider = FixtureCompletionProvider({k: v for k, v in replies.items()})
    runs: list[Any] = []

    def respond(agent_id: str, lens: str, dossier: dict, intake: Any):
        if dossier["dossier_sha256"] not in replies:
            return "no_reply", None, None, None, None
        runner = H.build_runner(pack, provider, agent_id=agent_id, lens=lens)
        r = runner.run(dossier, intake)
        runs.append(r)
        info = r.provider_info
        extra = infos.get(dossier["dossier_sha256"])
        if extra:
            info = {**(info or {}), **extra}
        if r.status == "submitted":
            return "submitted", None, r.message_id, info, None
        if r.status == "invalid":
            return "invalid", r.reason, None, info, None
        return r.status, r.reason, None, info, None
    export = SV.load_export(transfers)
    if export.pack != pack.identity:
        raise H.HarnessError(f"the export's dossiers were issued under {export.pack.label}, not under the run's pack {pack.identity.label}")
    assessed = SV.assess_export(export, {pack.identity}, respond)
    scores = SV.score(assessed, export.gold)
    res = {"replies": len(replies), "ignored_files": ignored, "runs": dict(Counter(r.status for r in runs)), "scores": scores,
           "system_text_is_the_pack": all(c.system == pack.system_text() for c in provider.calls)}
    H.write_json(out / "replies" / "scores.json", res)
    return res


# ============================================================================================ the run
def run_contained(out: Path, *, rounds_root: Optional[Path] = None, rounds: Iterable[str] = H.DEFAULT_ROUNDS, pack_path: Optional[Path] = None,
                  tamper: bool = True, probe_scope: str = "sample", replies_dir: Optional[Path] = None, transfers: Optional[Path] = None,
                  after_export: Optional[Callable[[Path], None]] = None) -> dict:
    inputs = [p for _n, p in H.round_dirs(rounds_root, H.ROUND_NAMES)] if rounds_root else []
    out = H.check_output_dir(out, inputs=inputs + ([Path(replies_dir)] if replies_dir else []) + ([Path(transfers)] if transfers else []), must_be_empty=True)
    t0 = time.perf_counter()
    result: dict[str, Any] = {"format": RESULTS_FORMAT, "claims_about_models": "none: every agent here is a scripted probe" if not replies_dir else
                              "only what the recorded replies show; this harness ran no model"}
    try:
        pack, pack_info = configure_pack(out, pack_path, after_export)
    except Stopped as exc:
        result.update(stopped=str(exc), agents_built=0, gates={"pack_loaded": {"ok": False}})
        H.write_json(out / "results.json", result)
        (out / "summary.md").write_text(f"# Contained Overseer run\n\nSTOPPED before any agent was built: {exc}\n", encoding="utf-8")
        return result
    result["pack"] = pack_info
    found = dict(H.round_dirs(rounds_root, rounds)) if rounds_root else {}
    result["rounds_missing"] = [n for n in rounds if n not in found]
    result["rounds"] = {}
    for name in rounds:
        if name in found:
            result["rounds"][name] = run_round_contained(name, found[name], out, pack, probe_scope=probe_scope)
    if tamper:
        import tamper as T
        m = T.run_suite(out / "tamper", rounds_root=rounds_root, pack_dir=Path(pack_info.get("exported_dir") or pack_info.get("given")))
        result["tamper"] = {"counts": m["counts"], "gates": {k: g["ok"] for k, g in m["gates"].items()}, "by_class": m["by_class"],
                            "manifest": str(out / "tamper" / "manifest.json")}
    if replies_dir:
        if not transfers:
            raise H.HarnessError("--replies needs --transfers EXPORT_DIR: a dossier digest names the transfers it was issued from")
        result["replies"] = run_replies(out, pack, Path(replies_dir), Path(transfers))
    result["gates"] = gates(result)
    result["wall_s"] = round(time.perf_counter() - t0, 2)
    H.write_json(out / "results.json", result)
    (out / "summary.md").write_text(summary_md(result), encoding="utf-8")
    return result


def gates(r: dict) -> dict:
    rounds = list(r.get("rounds", {}).values())
    reviews = [rv for rd in rounds for rv in rd.get("reviews", [])]
    g = {
        "agents_only_from_the_exported_pack": {"ok": bool(reviews) and all(rv.get("system_text_is_the_pack") for rv in reviews),
                                               "source": r.get("pack", {}).get("source")},
        "no_false_alarm_on_genuine_transfers": {"ok": all(not rd["genuine"]["false_alarms"] for rd in rounds),
                                                "value": sum(len(rd["genuine"]["false_alarms"]) for rd in rounds)},
        "arena_faults_named_by_receipts_and_confirmed": {"ok": all(m["receipt_named_it"] and m["overseer_agrees_with_receipt"] for rd in rounds for m in rd["mutations"]),
                                                         "value": sum(1 for rd in rounds for m in rd["mutations"] if m["receipt_named_it"] and m["overseer_agrees_with_receipt"]),
                                                         "of": sum(len(rd["mutations"]) for rd in rounds)},
        "replay_agreement_on_definitive_results": {"ok": all(not rd["replay"]["disagreements"] for rd in rounds),
                                                    "replayed": sum(rd["replay"]["results_replayed"] for rd in rounds)},
        "arena_unchanged_by_the_auditor": {"ok": all(rd["arena_unchanged_by_the_auditor"] for rd in rounds)},
        "every_task_audit_verifies": {"ok": all(c["verifies"] for rd in rounds for c in rd["channels"])},
        "probes_as_expected": {"ok": bool(reviews) and all(not rv.get("error") and all(p["ok"] for p in rv["probes"].values()) for rv in reviews),
                               "reviews": len(reviews)},
        "reviews_change_no_clearance": {"ok": bool(reviews) and all(rv.get("clearances_unchanged") for rv in reviews)},
    }
    if not rounds:
        for k in ("no_false_alarm_on_genuine_transfers", "arena_faults_named_by_receipts_and_confirmed", "replay_agreement_on_definitive_results",
                  "arena_unchanged_by_the_auditor", "every_task_audit_verifies", "agents_only_from_the_exported_pack", "probes_as_expected", "reviews_change_no_clearance"):
            g[k] = {"ok": False, "state": "NOT MEASURED (no recorded round present)"}
    if "tamper" in r:
        g["tamper_suite"] = {"ok": all(r["tamper"]["gates"].values()), **r["tamper"]["counts"]}
    return g


def _div_label(d: dict) -> str:
    return "{} ({}, owner {})".format(d["int_code"], d["classification"], d["owner"])


def summary_md(r: dict) -> str:
    L = ["# Contained Overseer run", "", f"Pack: {r['pack']['identity']['name']} {r['pack']['identity']['version']} {r['pack']['identity']['sha256']} "
         f"(loaded from {r['pack']['source']})", f"Models: {r['claims_about_models']}", f"Wall: {r.get('wall_s')} s", "", "## Gates", ""]
    L += [f"- {k}: {'PASS' if v['ok'] else 'FAIL'} " + json.dumps({x: y for x, y in v.items() if x != 'ok'}) for k, v in r["gates"].items()]
    for name, rd in r.get("rounds", {}).items():
        g = rd["genuine"]
        L += ["", f"## Round {name}", "",
              f"- arena: {rd['functional']}/{rd['transmissions']} functional (recorded: {rd.get('recorded_results')}); unchanged by the auditor: {rd['arena_unchanged_by_the_auditor']}",
              f"- genuine: {g['channels']} channels, {g['transfers']} transfers, states {g['states']}, false alarms {len(g['false_alarms'])}",
              f"- rule findings (DIV, true rule findings): {len(g['rule_findings'])}: " + ", ".join(sorted({_div_label(d) for d in g['rule_findings']})),
              f"- arena injected faults: {len(rd['mutations'])}; named by the receipt and confirmed by the overseer: "
              f"{sum(1 for m in rd['mutations'] if m['receipt_named_it'] and m['overseer_agrees_with_receipt'])}",
              f"- auditor additions on mutated transfers: {dict(Counter(c for m in rd['mutations'] for c in m['auditor_additions']))}",
              f"- replay: {rd['replay']['results_replayed']} results replayed, {len(rd['replay']['disagreements'])} disagreements, {rd['replay']['inconclusive']} inconclusive",
              f"- translations checked: {rd['translations']['checked']}; OVS-TRN on genuine: {rd['translations']['trn_codes_on_genuine']}",
              f"- reviews: {len(rd['reviews'])}; probes as expected: {sum(1 for rv in rd['reviews'] if not rv.get('error') and all(p['ok'] for p in rv['probes'].values()))}"]
        for s in rd["recorded_overseer_reports"]:
            L.append(f"- recorded overseer report {s['file']} (agent self-report): claimed functional rate {s.get('claimed_functional_rate')}, "
                     f"recomputed {s.get('recomputed_from_recorded_results')}, agrees {s.get('agrees')}")
    if r.get("rounds_missing"):
        L += ["", "Rounds not present: " + ", ".join(r["rounds_missing"])]
    if "tamper" in r:
        L += ["", "## Tampering suite", "", json.dumps(r["tamper"]["counts"]), json.dumps(r["tamper"]["gates"])]
    if "replies" in r:
        L += ["", "## Recorded replies", "", json.dumps({k: v for k, v in r["replies"].items() if k != "scores"})]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Contained Overseer run: arena rounds through an audited hub, the tampering suite, and overseer agents built only from an exported pack.")
    ap.add_argument("--out", required=True, type=Path, help="output directory (new or empty; never inside a recorded round)")
    ap.add_argument("--rounds", type=Path, default=None, help="directory holding the recorded rounds")
    ap.add_argument("--round", action="append", default=None, help=f"round name (repeatable; default {', '.join(H.DEFAULT_ROUNDS)})")
    ap.add_argument("--pack", type=Path, default=None, help="an exported pack to configure agents from (default: export the installed pack into --out/pack)")
    ap.add_argument("--probe-scope", choices=("sample", "all"), default="sample", help="review every genuine channel and one mutation per round, or every channel")
    ap.add_argument("--no-tamper", action="store_true", help="skip the tampering suite")
    ap.add_argument("--replies", type=Path, default=None, help="recorded verdict texts keyed by dossier digest (<sha256>.json)")
    ap.add_argument("--transfers", type=Path, default=None, help="the export_dossier.py output the replies answer")
    args = ap.parse_args(argv)
    try:
        r = run_contained(args.out, rounds_root=args.rounds, rounds=args.round or H.DEFAULT_ROUNDS, pack_path=args.pack, tamper=not args.no_tamper,
                          probe_scope=args.probe_scope, replies_dir=args.replies, transfers=args.transfers)
    except H.HarnessError as exc:
        print(json.dumps({"refused": str(exc)}))
        return 2
    if "stopped" in r:
        print(json.dumps({"stopped": r["stopped"], "agents_built": 0}))
        return 2
    print(json.dumps({"gates": {k: v["ok"] for k, v in r["gates"].items()}, "wall_s": r["wall_s"], "results": str(Path(args.out) / "results.json")}))
    return 0 if all(v["ok"] for v in r["gates"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
