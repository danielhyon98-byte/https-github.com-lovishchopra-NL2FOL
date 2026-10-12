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
2. **Rounds.** Each recorded round (default r2 to r5 and r7, each only when present) is COPIED into ``DIR/rounds/<name>`` and
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
   every genuine channel and one mutation channel per round (the first whose audit holds a finding an accusation kind
   maps to, so the confirming probe has a finding to confirm, else the first; ``--probe-scope all``: every channel).
   Asserted: each probe's outcome, and that a review changes no clearance.
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

from epinoic_logic.overseer import KIND_CHECKS, OVS_CODES, PackError, PackIdentity, verify_audit  # noqa: E402
from epinoic_logic.translate.providers import ProviderError  # noqa: E402

RESULTS_FORMAT = "overseer-contained/1.0"
#: Codes that are rule findings, listed apart for mutated transfers. On GENUINE transfers every error-level finding counts
#: as a false alarm, OVS-DIV-001 included (review round 2: an error-level divergence on a genuine, untampered transfer
#: fails it, so the precision gate must see it), unless it is an adjudicated genuine fault (below); the divergences are
#: still listed under ``rule_findings``.
RULE_CODES = ("OVS-DIV-001", "OVS-DIV-002")
GENUINE_EXCLUDED: tuple[str, ...] = ()
#: The versioned, evidenced record of real faults in recorded genuine transfers (see :func:`load_adjudications`).
ADJUDICATIONS_FILE = Path(__file__).resolve().parent / "adjudicated_genuine_faults.json"
ADJUDICATIONS_FORMAT = "overseer-adjudicated-genuine-faults/1.0"
_ENTRY_FIELDS = ("id", "round", "channel", "task_id", "agent_id", "claim_id", "code", "claim_text", "translation", "evidence", "why_genuine")
#: Codes by which the shadow re-derivation disagrees with a receipt.
SHADOW_DISAGREE = ("OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-008")
OTHER_PACK = PackIdentity(name="overseer-knowledge-docs", version="1.3", sha256="cd" * 32)  # a version other than the installed one


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


# ============================================================================================ adjudicated genuine faults
def _evidence_faults(entry: dict) -> list[str]:
    """Why an entry's engine evidence does not reproduce (empty when it does): the embedded IR's digest, its restating
    premises, and the engine's status on it as recorded and without the restating premises (``engine.runner.verify`` on
    the IR as untrusted JSON, default limits and configuration)."""
    from epinoic_logic.engine.results import SolverConfig
    from epinoic_logic.engine.runner import verify
    from epinoic_logic.ir.canonical import canonical_json, problem_digest
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks.translation import circular_premises, without_premises
    out: list[str] = []
    tr, ev = entry.get("translation") or {}, entry.get("evidence") or {}
    prob = tr.get("problem")
    try:
        digest = problem_digest(Problem.model_validate(prob))
    except Exception as exc:
        return [f"the embedded IR is not a valid problem ({type(exc).__name__})"]
    if digest != tr.get("problem_sha256"):
        out.append("the embedded IR's digest is not the recorded problem_sha256")
    if prob.get("claim_id") != entry.get("claim_id"):
        out.append("the embedded IR names another claim")
    restating = circular_premises(prob)
    if entry.get("code") == "OVS-TRN-006" and restating != list(ev.get("restating_premises") or []):
        out.append(f"the restating premises are {restating}, not {ev.get('restating_premises')}")
    recorded = verify(canonical_json(prob), SolverConfig())
    if recorded.status.value != (ev.get("as_recorded") or {}).get("status"):
        out.append(f"the engine gives {recorded.status.value} on the IR as recorded, not {(ev.get('as_recorded') or {}).get('status')}")
    if entry.get("code") == "OVS-TRN-006":
        reduced = verify(canonical_json(without_premises(prob, restating)), SolverConfig())
        want = (ev.get("without_restating_premises") or {}).get("status")
        if reduced.status.value != want:
            out.append(f"the engine gives {reduced.status.value} without the restating premises, not {want}")
        if reduced.status.value == "ENTAILED":
            out.append("the conclusion still follows without the restating premises: a redundant restatement (OVS-TRN-010) is no circular fault")
    return out


def load_adjudications(path: Optional[Path] = None) -> dict:
    """The adjudicated genuine faults (``scripts/overseer/adjudicated_genuine_faults.json``, format
    ``overseer-adjudicated-genuine-faults/1.0``): real faults of recorded genuine transfers, each naming its round, channel,
    agent, claim and finding code, with the engine evidence that decides it (the recorded IR, its restating premises, the
    statuses with and without them) and why it is genuine. The record is refused (``HarnessError``) unless its format, its
    fields and unique ids hold and every entry's evidence reproduces with the engine: the run never relies on an
    adjudication it cannot re-derive. An entry makes the run stricter, never looser (gate
    ``adjudicated_genuine_faults_raised``)."""
    p = Path(path) if path is not None else ADJUDICATIONS_FILE
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise H.HarnessError(f"the adjudication record {p.name} cannot be read ({type(exc).__name__})") from exc
    if not isinstance(doc, dict) or doc.get("format") != ADJUDICATIONS_FORMAT or not isinstance(doc.get("entries"), list):
        raise H.HarnessError(f"the adjudication record {p.name} is not of format {ADJUDICATIONS_FORMAT}")
    seen: set[str] = set()
    for e in doc["entries"]:
        missing = [k for k in _ENTRY_FIELDS if not (isinstance(e, dict) and e.get(k))]
        if missing:
            raise H.HarnessError(f"an adjudicated entry lacks {missing}")
        if e["id"] in seen:
            raise H.HarnessError(f"the adjudicated entry id {e['id']!r} is used twice")
        seen.add(e["id"])
        if e["code"] not in OVS_CODES:
            raise H.HarnessError(f"the adjudicated entry {e['id']!r} names an unknown code")
        faults = _evidence_faults(e)
        if faults:
            raise H.HarnessError(f"the evidence of the adjudicated entry {e['id']!r} does not reproduce: {'; '.join(faults)}")
    return {"format": doc["format"], "version": doc.get("version"), "source": p.name, "entries": list(doc["entries"])}


def _task_of(channel_key: str) -> str:
    """The task (genuine channel key) of an arena channel key (``group`` or ``group::variant``)."""
    return str(channel_key).split("::", 1)[0]


def finding_matches_entry(entry: dict, round_name: str, channel_key: str, f: Any) -> bool:
    """Whether finding ``f`` on channel ``channel_key`` of round ``round_name`` is exactly the adjudicated fault
    ``entry``: the same round, channel (task), code and severity error, the entry's claim and only it, and the entry's
    agent among the finding's agents."""
    get = (lambda k: f.get(k)) if isinstance(f, dict) else (lambda k: getattr(f, k, None))
    return (entry.get("round") == round_name and entry.get("channel") == _task_of(channel_key) and get("code") == entry.get("code")
            and get("severity") == "error" and list(get("claim_ids") or []) == [entry.get("claim_id")]
            and entry.get("agent_id") in set(get("agent_ids") or []))


def adjudicated_entry_for(adjudications: Optional[dict], round_name: str, channel_key: str, f: Any) -> Optional[dict]:
    for e in (adjudications or {}).get("entries", []):
        if finding_matches_entry(e, round_name, channel_key, f):
            return e
    return None


def classify_genuine_errors(round_name: str, channel_key: str, findings: Iterable[Any], adjudications: Optional[dict]) -> tuple[list[dict], list[dict]]:
    """``(false alarms, adjudicated faults raised)`` among the error-level findings of a GENUINE channel: an error is a
    false alarm unless it matches an adjudicated entry exactly (:func:`finding_matches_entry`)."""
    false_alarms, raised = [], []
    for f in findings:
        if f.severity != "error" or f.code in GENUINE_EXCLUDED:
            continue
        e = adjudicated_entry_for(adjudications, round_name, channel_key, f)
        if e is not None:
            raised.append({"entry": e["id"], "channel": channel_key, "code": f.code, "claim_ids": list(f.claim_ids), "message": f.message[:300]})
        else:
            false_alarms.append({"channel": channel_key, "code": f.code, "claim_ids": list(f.claim_ids), "message": f.message[:300]})
    return false_alarms, raised


def classify_mutation_errors(round_name: str, channel_key: str, findings: Iterable[Any], adjudications: Optional[dict]) -> tuple[list[str], list[str]]:
    """``(errors that disagree with the receipt, adjudicated errors)`` on an arena fault variant: an extra error matching an
    adjudicated entry for the same claim of the same task is the genuine fault the variant carries over, not a
    disagreement with the receipt; every other error-level finding (rule codes aside) still is."""
    errors, adjudicated = [], []
    for f in findings:
        if f.severity != "error" or f.code in RULE_CODES:
            continue
        e = adjudicated_entry_for(adjudications, round_name, channel_key, f)
        (adjudicated if e is not None else errors).append(f.code if e is None else e["id"])
    return errors, adjudicated


def adjudication_gate(result: dict) -> dict:
    """Gate ``adjudicated_genuine_faults_raised``: every adjudicated entry of a round this run replayed is raised as an error
    on its genuine transfer; a missing one fails (with what the genuine channel shows for its claim). Entries of rounds
    not run are listed, never counted as raised."""
    entries = (result.get("adjudications") or {}).get("entries", [])
    rounds = result.get("rounds", {})
    measured = [e for e in entries if e["round"] in rounds]
    raised_ids = {r["entry"] for rd in rounds.values() for r in rd["genuine"].get("adjudicated_raised", [])}
    missing = []
    for e in measured:
        if e["id"] in raised_ids:
            continue
        rd = rounds[e["round"]]
        seen = (rd["genuine"].get("claims_findings") or {}).get(f"{e['channel']}|{e['claim_id']}", [])
        missing.append({"entry": e["id"], "recorded_translation": (rd.get("adjudication_evidence") or {}).get(e["id"]),
                        "genuine_channel_shows": seen or "no finding names the claim (not delivered under this id, or not translated)"})
    return {"ok": not missing, "value": len(measured) - len(missing), "of": len(measured), "missing": missing,
            "not_run": [e["id"] for e in entries if e["round"] not in rounds], "record": (result.get("adjudications") or {}).get("source"),
            "record_version": (result.get("adjudications") or {}).get("version")}


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


def recorded_translation_matches(src: Path, entry: dict) -> Optional[str]:
    """None when the round's recorded translation of the entry's claim is the adjudicated IR (by digest); else why not."""
    from epinoic_logic.ir.canonical import problem_digest
    from epinoic_logic.ir.schema import Problem
    path = Path(src) / "translations" / f"{entry['task_id']}.json"
    try:
        prob = json.loads(path.read_text(encoding="utf-8"))["claims"][entry["claim_id"]]["problem"]
        digest = problem_digest(Problem.model_validate(prob))
    except Exception as exc:
        return f"the round holds no recorded translation of {entry['claim_id']} for {entry['task_id']} ({type(exc).__name__})"
    return None if digest == entry["translation"]["problem_sha256"] else "the round's recorded translation is not the adjudicated IR (digest differs)"


def run_round_contained(name: str, src: Path, out: Path, pack: Any, *, probe_scope: str, replay_mode: str = "inline",
                        adjudications: Optional[dict] = None) -> dict:
    rdir = out / "rounds"
    plain_copy = H.copy_round(src, rdir / "without-auditor", name=name)
    plain = H.arena().run_round(plain_copy)
    copy = H.copy_round(src, rdir, name=name)
    aud = H.new_auditor(H.keyring_for("arena"), replay_mode=replay_mode)
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
        genuine = {"channels": 0, "transfers": 0, "false_alarms": [], "adjudicated_raised": [], "claims_findings": {}, "rule_findings": [], "states": Counter()}
        own = [e for e in (adjudications or {}).get("entries", []) if e["round"] == name]
        rec["adjudication_evidence"] = {e["id"]: recorded_translation_matches(src, e) or "the round's recorded translation is the adjudicated IR" for e in own}
        usable = {"entries": [e for e in own if recorded_translation_matches(src, e) is None]}
        mutations: list[dict] = []
        replay = {"results_replayed": 0, "disagreements": [], "inconclusive": 0, "mode": replay_mode}
        translations = {"checked": 0, "trn_codes_on_genuine": Counter()}
        channels = []
        confirmable: set[str] = set()  # channels whose audit holds a finding an accusation kind maps to (the confirm probe's target)
        for c in rr.channels:
            audit = aud.audit(c.uid)
            if any(f.severity != "info" and f.message_ids and any(f.code in kc for kc in KIND_CHECKS.values()) for f in audit.report.findings):
                confirmable.add(c.key)
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
                false_alarms, raised = classify_genuine_errors(name, c.key, audit.report.findings, usable)
                genuine["false_alarms"] += false_alarms
                genuine["adjudicated_raised"] += raised
                for e in own:  # what the genuine channel shows for each adjudicated claim (the gate names it when one is missing); a
                    # claim id is unique only within a report (two STEM agents of one branch share s1.2), so a finding is read
                    # for the entry's agent when it names agents
                    if e["channel"] == c.key:
                        genuine["claims_findings"][f"{e['channel']}|{e['claim_id']}"] = sorted(
                            f"{f.code} ({f.severity})" for f in audit.report.findings
                            if e["claim_id"] in f.claim_ids and (not f.agent_ids or e["agent_id"] in f.agent_ids))
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
                    errors, adjudicated = classify_mutation_errors(name, c.key, audit.report.findings, usable)
                    additions = sorted({f.code for f in audit.report.findings if f.code not in RULE_CODES and f.code != "OVS-PEER-003"})
                    mutations.append({"channel": c.key, "file": r.get("file"), "kind": r.get("variant"), "receipt_named_it": bool(r.get("functional")),
                                      "named_by": sorted({f.get("code") for f in r.get("named_by", [])}), "status": r.get("status"),
                                      "overseer_agrees_with_receipt": not shadow and not errors, "shadow_disagreements": shadow,
                                      "auditor_additions": additions, "adjudicated_errors": adjudicated})
        genuine["states"] = dict(genuine["states"])
        translations["trn_codes_on_genuine"] = dict(translations["trn_codes_on_genuine"])
        rec.update(channels=channels, genuine=genuine, mutations=mutations, replay=replay, translations=translations,
                   recorded_overseer_reports=recorded_self_reports(src, recorded))
        # overseer agents: probes through hub.review
        keys = [c.key for c in rr.channels if c.variant == "genuine"]
        muts = [c.key for c in rr.channels if c.variant not in ("genuine", "closed")]
        if probe_scope != "all" and muts:
            muts = [next((k for k in muts if k in confirmable), muts[0])]
        keys += muts
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
                  after_export: Optional[Callable[[Path], None]] = None, replay_mode: str = "inline", adjudications_path: Optional[Path] = None) -> dict:
    if replay_mode not in ("inline", "process"):
        raise H.HarnessError("--replay-mode is inline or process")
    adjudications = load_adjudications(adjudications_path)  # refused unless every entry's engine evidence reproduces
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
    result["adjudications"] = adjudications
    found = dict(H.round_dirs(rounds_root, rounds)) if rounds_root else {}
    result["rounds_missing"] = [n for n in rounds if n not in found]
    result["rounds"] = {}
    for name in rounds:
        if name in found:
            result["rounds"][name] = run_round_contained(name, found[name], out, pack, probe_scope=probe_scope, replay_mode=replay_mode,
                                                         adjudications=adjudications)
    result["replay_mode"] = replay_mode
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
        # an error on a genuine transfer is a false alarm unless it matches an adjudicated genuine fault exactly (round,
        # channel, claim, code, agent); every adjudicated fault must be raised (the next gate)
        "no_false_alarm_on_genuine_transfers": {"ok": all(not rd["genuine"]["false_alarms"] for rd in rounds),
                                                "value": sum(len(rd["genuine"]["false_alarms"]) for rd in rounds)},
        "adjudicated_genuine_faults_raised": adjudication_gate(r),
        "arena_faults_named_by_receipts_and_confirmed": {"ok": all(m["receipt_named_it"] and m["overseer_agrees_with_receipt"] for rd in rounds for m in rd["mutations"]),
                                                         "value": sum(1 for rd in rounds for m in rd["mutations"] if m["receipt_named_it"] and m["overseer_agrees_with_receipt"]),
                                                         "of": sum(len(rd["mutations"]) for rd in rounds)},
        # decision 20: only a worker-process replay is independent; an inline run says what it measured (contained round c1)
        "replay_agreement_on_definitive_results": {"ok": all(not rd["replay"]["disagreements"] for rd in rounds),
                                                    "replayed": sum(rd["replay"]["results_replayed"] for rd in rounds),
                                                    "replay_mode": r.get("replay_mode", "inline"),
                                                    "scope": "worker process (independent)" if r.get("replay_mode") == "process"
                                                    else "in-process only: replay independence not established"},
        "arena_unchanged_by_the_auditor": {"ok": all(rd["arena_unchanged_by_the_auditor"] for rd in rounds)},
        "every_task_audit_verifies": {"ok": all(c["verifies"] for rd in rounds for c in rd["channels"])},
        "probes_as_expected": {"ok": bool(reviews) and all(not rv.get("error") and all(p["ok"] for p in rv["probes"].values()) for rv in reviews),
                               "reviews": len(reviews)},
        "reviews_change_no_clearance": {"ok": bool(reviews) and all(rv.get("clearances_unchanged") for rv in reviews)},
    }
    if not rounds:
        for k in ("no_false_alarm_on_genuine_transfers", "arena_faults_named_by_receipts_and_confirmed", "replay_agreement_on_definitive_results",
                  "arena_unchanged_by_the_auditor", "every_task_audit_verifies", "agents_only_from_the_exported_pack", "probes_as_expected", "reviews_change_no_clearance",
                  "adjudicated_genuine_faults_raised"):
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
              f"- genuine: {g['channels']} channels, {g['transfers']} transfers, states {g['states']}, false alarms {len(g['false_alarms'])}, "
              f"adjudicated genuine faults raised {len(g.get('adjudicated_raised', []))}"
              + "".join(f"\n  - {x['entry']}: {x['code']} on {x['channel']} claim {', '.join(x['claim_ids'])}" for x in g.get("adjudicated_raised", []))
              + "".join(f"\n  - false alarm: {x['code']} on {x['channel']} claim(s) {', '.join(x.get('claim_ids', []))}: {x['message'][:160]}" for x in g["false_alarms"]),
              f"- rule findings (DIV, true rule findings): {len(g['rule_findings'])}: " + ", ".join(sorted({_div_label(d) for d in g['rule_findings']})),
              f"- arena injected faults: {len(rd['mutations'])}; named by the receipt and confirmed by the overseer: "
              f"{sum(1 for m in rd['mutations'] if m['receipt_named_it'] and m['overseer_agrees_with_receipt'])}",
              f"- auditor additions on mutated transfers: {dict(Counter(c for m in rd['mutations'] for c in m['auditor_additions']))}",
              f"- replay ({rd['replay'].get('mode', 'inline')}{'' if rd['replay'].get('mode') == 'process' else ': in-process only'}): "
              f"{rd['replay']['results_replayed']} results replayed, {len(rd['replay']['disagreements'])} disagreements, {rd['replay']['inconclusive']} inconclusive",
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
    ap.add_argument("--replay-mode", choices=("inline", "process"), default="inline",
                    help="replay the recorded rounds' results inline (default; reported as in-process only) or in a worker process (decision 20)")
    ap.add_argument("--adjudications", type=Path, default=None,
                    help="the adjudicated genuine faults record (default scripts/overseer/adjudicated_genuine_faults.json; its evidence is re-run first)")
    args = ap.parse_args(argv)
    try:
        r = run_contained(args.out, rounds_root=args.rounds, rounds=args.round or H.DEFAULT_ROUNDS, pack_path=args.pack, tamper=not args.no_tamper,
                          probe_scope=args.probe_scope, replies_dir=args.replies, transfers=args.transfers, replay_mode=args.replay_mode,
                          adjudications_path=args.adjudications)
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
