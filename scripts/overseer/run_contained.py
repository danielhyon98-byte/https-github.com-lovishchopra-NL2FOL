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
2b. **The re-keyed pass** (the repair of the translator merge, design decision 50). A round recorded before the
   translator merge keys its translation fixtures by the claim ids of the parsers of that time, so the arena, by its own
   rule, serves none of them to the merged parsers' claims (r7: 200 fixtures, the STEM answers' among them). For such a
   round (the arena reports fixtures matching no delivered claim) a further copy has its fixtures re-keyed to the claims
   the merged parse delivers (rule ``recorded-ids``, ``ovs_harness.rekey_translations``; rule ``recorded-ids/2``, the
   second repair of the translator merge: a fixture the round's own records show was written for another claim than the
   one it would reach, its recorded relay or claims file naming another text or its conclusion label a mark line, is
   withheld and listed, never served) and its genuine pass replayed with
   the auditor (and once without it): every recorded translation that reaches a delivered claim goes through the merged
   translator's real pipeline and the overseer's checks, and the pass is gated like the genuine one (false alarms, the
   adjudicated faults it names, replay agreement, non-interference, audits verifying), each retired adjudication is
   confirmed on it, and the gate ``recorded_translations_served_under_merged_ids`` fails a run that skipped it.
3. **Recorded overseer reports** (``<round>/overseers/*.json``, read-only) are agent self-reports: their functional rate
   is recomputed from the recorded ``results.json`` and the comparison is reported, never trusted.
2c. **STEM fault classes** (``stem_probes.py``, when r7 is among the rounds; decision 60): for each STEM fault class one
   planted fault (and, where a check could misread it, its correct control) on a copy of a recorded STEM transfer of r7,
   through an audited hub: whether the receipt names it and the overseer agrees, what a blind dossier shows of it, and
   for a STEM translation the overseer's checks and a scripted agent built from the same exported pack; gate
   ``stem_fault_classes_named`` (a probe whose fault the STEM translator's reading does not decide is reported with the
   reason and not counted against the overseer).
4. **Tampering suite** (``tamper.py``, unless ``--no-tamper``): every case, its agents built from the same exported pack, on
   the synthetic task and the recorded r5 and r7 targets (the STEM receipt cases T23a to T23z, T23aa to T23az and T23ba to T23bt on r7's STEM tasks).
5. **Overseer agents** (scripted probe providers, no network, no model): ``hub.review`` runs probes whose replies
   exercise every validation outcome (a clean verdict, a confirmed accusation, a lie about a signed result, invented
   identifiers, a meaning fault, prose, the "no dossier" object, a verdict naming another pack, a provider failure) on
   every genuine channel and one mutation channel per round (the first whose audit holds a finding an accusation kind
   maps to, so the confirming probe has a finding to confirm, else the first; ``--probe-scope all``: every channel),
   and on every genuine channel of a re-keyed pass (the fifth repair: the only pass that serves a round's recorded
   translations to the merged STEM claims, so the agents are shown them; a STEM probe accuses one, which stays unresolved
   for human review, and the gate ``recorded_stem_translations_reviewed_by_agents`` fails a run whose re-keyed pass
   served STEM translations no probe was shown). Asserted: each probe's outcome, and that a review changes no clearance.
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
import hashlib
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
#: A retired entry keeps every field and adds why it was retired, in which version, and the evidence of its retirement.
_RETIRED_FIELDS = _ENTRY_FIELDS + ("retired_in_version", "why_retired", "retirement_evidence")
#: What a RESTORED entry carries beside the fields of an entry (record version 6): the version that restores it, why, the
#: retirement it supersedes (its ``retired_in_version``, ``why_retired`` and ``retirement_evidence``, kept as recorded) and
#: the evidence it carried when it was retired (``superseded_evidence``: its ``version``, ``evidence`` and ``why_genuine``).
_RESTORED_FIELDS = ("restored_in_version", "why_restored", "superseded_retirement", "superseded_evidence")
#: The pass of a round in which an entry's fault is raised: the round's genuine pass, or its RE-KEYED pass (rule
#: ``recorded-ids``, ``ovs_harness.rekey_translations``: a round recorded before the translator merge, its translation
#: fixtures served to the claims the merged parse delivers; the arena by its own rule serves none of them).
PASSES = ("genuine", "rekeyed")
#: What an entry measured in the re-keyed pass adds: the id the recording gives the claim, and in its evidence the
#: recorded answer, the plan it was delivered under and the recorded proposal, from which the harness re-derives the
#: merged parse, the pipeline's run and the overseer's rule before it accepts the record.
_REKEYED_FIELDS = ("recorded_claim_id",)
_SOURCE_FIELDS = ("recorded_answer", "recorded_plan", "recorded_proposal")
#: Codes by which the shadow re-derivation disagrees with a receipt.
SHADOW_DISAGREE = ("OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-008")
OTHER_PACK = PackIdentity(name="overseer-knowledge-docs", version="1.5", sha256="cd" * 32)  # a version other than the installed one (1.4)


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


#: The claim-id letters of the STEM parsers (``adapters.stem_specialist.parser.ID_PREFIXES``: science, mathematics,
#: computer science); a generic claim id is agent-qualified (``g4.1@economics-specialist``).
STEM_ID_LETTERS = ("s", "m", "c")


def stem_translation_link(d: dict) -> Optional[dict]:
    """The first translation link of a dossier to a STEM claim (an id of a STEM parser, never agent-qualified) whose
    translation carries a problem; None when the dossier holds none."""
    from epinoic_logic.overseer import resolve_pointer
    for link in d.get("links", {}).get("translations") or []:
        cid = str(link.get("claim_id") or "")
        if cid[:1] not in STEM_ID_LETTERS or not cid[1:2].isdigit() or "@" in cid or not link.get("translation_pointer"):
            continue
        try:
            translation = resolve_pointer(d, link["translation_pointer"])
        except Exception:
            continue
        if isinstance(translation, dict) and translation.get("problem"):
            return link
    return None


def probe_stem(d: dict):
    """A STEM translation (on a recorded round, served by the re-keyed pass: rule recorded-ids) accused as unfaithful: no
    check decides whether an encoding says what its claim says, so the accusation is unresolved (AGENT-004), human review.
    A dossier with no STEM translation gets no accusation."""
    link = stem_translation_link(d)
    if link is None:
        return H.verdict_dict(d)
    return H.verdict_dict(d, [H.accusation("a1", "translation_unfaithful", [{"pointer": link["claim_pointer"] + "/claim_text"}, {"pointer": link["translation_pointer"]}],
                                           message_ids=[link["message_id"]], claim_ids=[link["claim_id"]], report_ids=[link["report_id"]],
                                           statement="The STEM translation does not say what the claim says (a substitution, a unit or a precision).")])


PROBES: tuple[tuple[str, str, Callable[[dict], Any], str], ...] = (
    # agent id, lens, reply, what the infrastructure must make of it
    ("overseer-silent-1", "general", lambda d: H.verdict_dict(d), "valid, no accusation"),
    ("overseer-confirm-1", "custody_results", probe_confirm, "confirmed (AGENT-003) when the audit holds a finding, else no accusation"),
    ("overseer-liar-1", "custody_results", probe_liar, "refuted by the signed result (AGENT-001), accusation and engine statement"),
    ("overseer-invent-1", "content_fidelity", probe_invent, "unverifiable (AGENT-002)"),
    ("overseer-unfaithful-1", "translation_fidelity", probe_unfaithful, "unresolved (AGENT-004), human review"),
    ("overseer-stem-1", "translation_fidelity", probe_stem, "unresolved (AGENT-004) on a STEM translation, else no accusation"),
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
    if agent_id == "overseer-stem-1":
        if assessment is None or not assessment.valid:
            return False, "not assessed"
        if not assessment.accusations:
            return True, "no STEM translation"
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
    # which STEM translation the STEM probe was shown and accused (rule recorded-ids: on a recorded round, the re-keyed pass)
    stem_provider = next((p for (r, p), probe in zip(runners, PROBES) if probe[0] == "overseer-stem-1"), None)
    stem_links = [stem_translation_link(H.dossier_of_user_text(c[1])) for c in (stem_provider.calls if stem_provider is not None else [])]
    stem_reviewed = next((x["claim_id"] for x in stem_links if x), None)
    return {"key": key, "probes": probes, "clearances_unchanged": before == after, "verdicts_audit_verifies": verify_audit(review.audit, hub.auditor.keyring),
            "stem_translation_reviewed": stem_reviewed,
            "verdicts_audit_state": review.audit.state, "task_audit_state": review.task_audit.state,
            "agent_codes": dict(Counter(f.code for f in review.audit.report.findings)),
            # STEM repair 11: each call's system text is the pack's composition for the dossier that call carries (the core and the modules
            # its content needs), and that composition recomputes to the manifest's digest
            "system_text_is_the_pack": bool(systems) and all(c[0] == pack.system_text_for(H.dossier_of_user_text(c[1])) and hashlib.sha256(c[0].encode("utf-8")).hexdigest()
                                                             == pack.composition_sha256(pack.modules_for(H.dossier_of_user_text(c[1])))
                                                             for _r, p in runners for c in p.calls),
            "system_modules": sorted({"+".join(("core",) + pack.modules_for(H.dossier_of_user_text(c[1]))) for _r, p in runners for c in p.calls}),
            "provider_calls": sum(len(p.calls) for _r, p in runners)}


# ============================================================================================ adjudicated genuine faults
#: The kinds of retirement (``retirement_evidence.kind``): the translator no longer delivers the encoding (record version 2:
#: its gate withholds it, E112), or the overseer's rules, corrected, no longer read the delivered encoding as a circular
#: fault (record version 4: the engine shows that the result does not rest on a writer's-own premise; record version 5,
#: rule engine-shown: the engine shows nothing beyond a data conjunct needing its data premise). Record version 6 (rule
#: data-standing corrected, decision 56) restored the three entries version 5 retired that way: their restating premises
#: were "undecided" on labels alone, and the corrected rule shows them not to be data (:func:`_restoration_faults`).
RETIREMENT_KINDS = ("translator_withholds", "overseer_rules")
#: The ``OVS-TRN`` codes a retirement's replay is read for (rule engine-shown grades a restatement with these three).
RESTATEMENT_CODES = ("OVS-TRN-006", "OVS-TRN-010", "OVS-TRN-011")


def _plain_follows(problem: Any) -> Callable[[list[str]], bool]:
    """``follows(premise_ids)`` for rule engine-shown re-derived by the harness: a plain engine run
    (``engine.runner.verify`` on the IR as untrusted JSON, default limits and configuration) on ``problem`` (JSON) without
    those premises gives ENTAILED with no diagnostic that withholds the verdict (the audit asks the same of its own signed
    run, rule restatement-necessity)."""
    from epinoic_logic.engine.results import SolverConfig
    from epinoic_logic.engine.runner import verify
    from epinoic_logic.ir.canonical import canonical_json
    from epinoic_logic.overseer.checks.translation import NECESSITY_BENIGN_DIAGNOSTICS, without_premises
    memo: dict[tuple[str, ...], bool] = {}

    def follows(pids: list[str]) -> bool:
        key = tuple(sorted(pids))
        if key not in memo:
            res = verify(canonical_json(without_premises(problem, list(pids))), SolverConfig())
            memo[key] = res.status.value == "ENTAILED" and all(d.code in NECESSITY_BENIGN_DIAGNOSTICS for d in res.diagnostics)
        return memo[key]
    return follows


def _engine_run(problem: Any, pids: list[str]) -> dict:
    """The plain engine run on ``problem`` (JSON) without ``pids``, as a record states it."""
    from epinoic_logic.engine.results import SolverConfig
    from epinoic_logic.engine.runner import verify
    from epinoic_logic.ir.canonical import canonical_json
    from epinoic_logic.overseer.checks.translation import without_premises
    res = verify(canonical_json(without_premises(problem, list(pids))), SolverConfig())
    return {"without": list(pids), "status": res.status.value, "premises_relied_on": list(res.premises_relied_on),
            "diagnostics": sorted({d.code for d in res.diagnostics})}


def _grade_record(rs: Any, problem: Any, partial: bool = False) -> list[list[Any]]:
    """Rule engine-shown's grade of the restatement ``rs`` on ``problem`` (JSON), re-derived with plain engine runs, as a
    record states it: ``[decision, premises named, premises removed]`` per decision."""
    from epinoic_logic.overseer.checks.translation import engine_shown_grade
    return [[d, list(named), list(removed)] for d, named, removed in engine_shown_grade(rs, partial, _plain_follows(problem))]


def _standing_record(rs: Any) -> dict:
    """The overseer's reading of a restatement (rules data-standing and grounded-transcription) as a record states it."""
    return {"own": list(rs.own), "transcriptions": list(rs.grounded), "shown": list(rs.shown), "undecided": list(rs.undecided),
            "undecided_disclosed": list(rs.undecided_disclosed), "standings": {pid: kind for pid, kind in rs.standings},
            "why_own": {pid: why for pid, why in rs.why_own}}


def _has_sources(ev: dict) -> bool:
    return all(ev.get(k) for k in _SOURCE_FIELDS)


def _core_faults(entry: dict, recorded: Any) -> list[str]:
    """Rule ``engine-shown``, part one (the second repair of the translator merge): an OVS-TRN-006 entry adjudicates a
    fault the ENGINE shows, not one a label suggests. The proof the engine gives on the IR as recorded must rest on the
    restatement: its core (``premises_relied_on``) holds only premises that restate the conclusion (the writer's-own ones
    the record names, and the restating premises a deterministic check verified, ``transcriptions``), and at least one of
    the writer's own; and the record states that core exactly. Part two (record version 5, :func:`_shown_faults`): the
    engine must show more than that a data conjunct needs its data premise."""
    ev = entry.get("evidence") or {}
    core = list(recorded.premises_relied_on)
    out: list[str] = []
    stated = (ev.get("as_recorded") or {}).get("premises_relied_on")
    if stated is None:
        out.append("the record does not state the core of the proof as recorded (as_recorded.premises_relied_on)")
    elif list(stated) != core:
        out.append(f"the engine's proof as recorded relies on {core}, not on {list(stated)}")
    own = set(ev.get("restating_premises") or [])
    restating = own | set(ev.get("transcriptions") or [])
    if not core or not set(core) <= restating:
        out.append(f"the proof as recorded relies on {sorted(set(core) - restating) or core}, which restate no part of the conclusion: the engine does not "
                   "show that the result rests on the claim assumed")
    elif not set(core) & own:
        out.append(f"the proof as recorded relies only on {core}, restating premises a deterministic check verified: the result does not rest on a "
                   "writer's-own premise (a transcription check, not a circular fault)")
    return out


def _shown_faults(entry: dict, rs: Any, problem: Any) -> list[str]:
    """Rule ``engine-shown``, part two (record version 5, the third repair of the translator merge, decision 55): an
    OVS-TRN-006 entry adjudicates only a fault the engine shows BEYOND "a data conjunct needs its data premise". The
    overseer's rules on the delivered encoding (rule data-standing) name exactly the record's ``shown_premises`` (the
    restating premises a deterministic check shows are not data: the writer's own by kind, refuted by their source, naming
    no source the overseer holds, or, decision 56, presented as data on a kind label alone: content no check reads in its
    source) and ``undecided_premises`` (whose whole content rule same-quantity reads as their source's data, which no check
    verifies or refutes);
    at least one is shown; and the grade re-derived with plain engine runs on the embedded IR is exactly OVS-TRN-006: the
    run without the shown premises, keeping the undecided ones, does not give ENTAILED (``without_shown_premises`` states
    its status). An entry whose result rests only on undecided premises shows nothing more than a transcription would: it
    is refused, and is to be retired."""
    ev = entry.get("evidence") or {}
    out: list[str] = []
    shown, undecided = [p for p in rs.own if p in rs.shown], [p for p in rs.own if p in rs.undecided]
    if "shown_premises" not in ev or "undecided_premises" not in ev:
        out.append("the record does not state which restating premises a check shows are not data (shown_premises, undecided_premises: rule "
                   "data-standing, record version 5)")
    elif list(ev["shown_premises"]) != shown or list(ev["undecided_premises"]) != undecided:
        out.append(f"the overseer's rules show {shown} not to be data and leave {undecided} undecided, not {ev.get('shown_premises')} and "
                   f"{ev.get('undecided_premises')}")
    if not shown:
        out.append(f"no restating premise is shown not to be data: the result rests only on {undecided}, presented as data that no check verifies or "
                   "refutes, which shows only that a data conjunct needs its data premise (rule engine-shown): retire the entry")
        return out
    grade = _grade_record(rs, problem)
    codes = sorted({d for d, _n, _r in grade if d.startswith("OVS-")})
    if codes != ["OVS-TRN-006"]:
        out.append(f"rule engine-shown grades the restatement {codes}, not OVS-TRN-006: the run without the shown premises {shown} (keeping {undecided}) "
                   "gives ENTAILED, so the result does not rest on a premise shown not to be data")
    run = _engine_run(problem, shown)
    want = ev.get("without_shown_premises") or {}
    if {k: run[k] for k in ("status",)} != {k: want.get(k) for k in ("status",)}:
        out.append(f"the engine gives {run['status']} without the shown premises {shown}, not {want.get('status')}")
    return out


def _unsourced_shown(prob: dict) -> tuple[list[str], list[str], list[str]]:
    """``(restating, shown, needs_sources)`` for an entry that embeds no sources (record version 1): its verbatim
    restating premises, those whose grounding alone shows they are not data (no grounding, a writer's-own kind, a source
    no check reads, an arithmetic fact or quotation no check verified: rule data-standing needs no request for these), and
    those whose standing needs the request (a task_setting or supplied_text with no excerpt)."""
    from epinoic_logic.engine.runner import assumed_grounding
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks.translation import HELD_SOURCE_KINDS, UNREAD_SOURCE_KINDS, WRITER_OWN_KINDS, circular_premises
    problem = Problem.model_validate(prob)
    by_id = {pr.id: pr for pr in problem.premises}
    restating = circular_premises(prob)
    shown, needs = [], []
    for pid in restating:
        g = by_id[pid].grounding if pid in by_id else None
        if g is None or g.kind in WRITER_OWN_KINDS or g.kind in UNREAD_SOURCE_KINDS or assumed_grounding(g) or g.verified is False:
            shown.append(pid)
        elif g.kind in HELD_SOURCE_KINDS and not any(r.excerpt for r in g.source_refs):
            needs.append(pid)
    return restating, shown, needs


def _evidence_faults(entry: dict, *, rules_superseded: bool = False) -> list[str]:
    """Why an entry's engine evidence does not reproduce (empty when it does): the embedded IR's digest, its restating
    premises, and the engine's status on it as recorded and without the restating premises (``engine.runner.verify`` on
    the IR as untrusted JSON, default limits and configuration); for an OVS-TRN-006 entry, rule ``engine-shown``
    (:func:`_core_faults`). An entry that embeds its sources (the recorded answer, its plan and the recorded proposal: every
    re-keyed entry, and any genuine-pass entry of record version 4) has the merged parse, the pipeline's run and the
    overseer's rules re-derived from them (:func:`_sourced_evidence_faults`). ``rules_superseded``: a retirement of kind
    ``overseer_rules`` supersedes the record's reading of the overseer's rules (the corrected rules no longer give it); every
    other part of the original evidence must still reproduce, and the retirement's own evidence is re-derived instead."""
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
    if _has_sources(ev):
        # the overseer's rules name the restating premises on the delivered problem and report, re-derived from the
        # embedded sources (_sourced_evidence_faults); the engine evidence below is run on the embedded IR without them
        restating = [pid for pid in (ev.get("restating_premises") or []) if any(pr.get("id") == pid for pr in prob.get("premises") or [])]
        if restating != list(ev.get("restating_premises") or []):
            out.append(f"the restating premises {ev.get('restating_premises')} are not all premises of the embedded IR")
        out += _sourced_evidence_faults(entry, rules_superseded=rules_superseded)
    elif entry.get("pass", "genuine") == "rekeyed":
        return out + ["a re-keyed entry embeds no recorded answer, plan and proposal to re-derive its evidence from"]
    else:
        restating = circular_premises(prob)
        if entry.get("code") == "OVS-TRN-006" and restating != list(ev.get("restating_premises") or []):
            out.append(f"the restating premises are {restating}, not {ev.get('restating_premises')}")
        if entry.get("code") == "OVS-TRN-006" and not rules_superseded:
            # rule engine-shown, part two, on an entry with no sources: only a grounding that alone shows the premise is not
            # data can carry the fault (a premise whose standing needs the request needs the embedded sources)
            _r, shown, needs = _unsourced_shown(prob)
            if needs:
                out.append(f"the restating premise(s) {needs} name the request as their source, so the entry must embed its sources to re-derive their "
                           "standing (rule data-standing)")
            elif not shown:
                out.append("no restating premise is shown not to be data by its grounding (rule engine-shown): retire the entry")
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
        if recorded.status.value == "ENTAILED" and not rules_superseded:
            out += _core_faults(entry, recorded)
        elif recorded.status.value == "ENTAILED" and "premises_relied_on" in (ev.get("as_recorded") or {}):
            # an engine fact, whatever rules read it: the core of the proof as recorded is re-derived on a retirement too
            stated = list((ev.get("as_recorded") or {}).get("premises_relied_on") or [])
            if stated != list(recorded.premises_relied_on):
                out.append(f"the engine's proof as recorded relies on {list(recorded.premises_relied_on)}, not on {stated}")
    return out


def _same_sources_faults(entry: dict) -> list[str]:
    """Why a retirement does not embed the very sources its entry's evidence embeds (empty when it does, or when the entry
    embeds none: record version 1). A retirement re-derived from other sources than the entry's says nothing of the entry."""
    ev, rev = entry.get("evidence") or {}, entry.get("retirement_evidence") or {}
    if not _has_sources(ev) or not _has_sources(rev):
        return []
    return [f"the retirement embeds another {f.replace('_', ' ')} than the entry's evidence (SHA-256 {str(rev.get(f + '_sha256'))[:12]}, not "
            f"{str(ev.get(f + '_sha256'))[:12]})" for f in _SOURCE_FIELDS if canonical_json_of(rev.get(f)) != canonical_json_of(ev.get(f))
            or rev.get(f + "_sha256") != ev.get(f + "_sha256")]


def _source_faults(src: dict) -> list[str]:
    """Why an entry's embedded sources (``recorded_answer``, ``recorded_plan``, ``recorded_proposal`` with their SHA-256)
    are not what the record says they are (empty when they are)."""
    from epinoic_logic.ir.canonical import sha256_hex
    out = []
    for f in _SOURCE_FIELDS:
        if not isinstance(src.get(f), (dict, str)) or not src.get(f):
            out.append(f"the evidence lacks the {f.replace('_', ' ')}")
        elif src.get(f + "_sha256") != sha256_hex(canonical_json_of(src[f])):
            out.append(f"the {f.replace('_', ' ')} is not the one whose SHA-256 the record names")
    return out


def canonical_json_of(value: Any) -> str:
    """Canonical JSON of an embedded source (a fixture recorded as JSON text is read as the object it holds)."""
    from epinoic_logic.ir.canonical import canonical_json
    return canonical_json(json.loads(value) if isinstance(value, str) else value)


def _delivery(src: dict, recorded_claim_id: str) -> Any:
    """The recorded answer of ``src`` delivered under its recorded plan, the recorded proposal served to the claim the
    merged parse delivers for ``recorded_claim_id`` (``ovs_harness.recorded_delivery``)."""
    return H.recorded_delivery(src["recorded_answer"], src["recorded_plan"], {recorded_claim_id: src["recorded_proposal"]})


def _request_of(src: dict) -> tuple[list[str], list[Any]]:
    """``(request texts, request documents)`` of an embedded recorded answer as the arena dispatches it: the question
    (the request's input; its constraints are read from it) and the texts supplied with it. The overseer's rule
    same-quantity reads a premise against these (it can refute it, never verify it), as the audit does against the
    journaled request."""
    answer = src.get("recorded_answer") or {}
    return [answer.get("question") or ""], H.arena().supplied(answer)


def _pipeline_record(o: Any) -> dict:
    """What the pipeline delivered for one outcome, as the record states it."""
    tr = o.translation
    rec = {"claim_id": o.claim_id, "translation_status": tr.status.value, "problem_delivered": tr.problem is not None, "engine_run": o.verification is not None,
           "display_status": o.display_status.value}
    if o.verification is not None:
        rec.update(result_status=o.verification.status.value, result_diagnostics=sorted({d.code for d in o.verification.diagnostics}))
    if any("E112" in d for d in tr.diagnostics):
        rec["translation_diagnostic"] = "E112"
    return rec


def _sourced_evidence_faults(entry: dict, *, rules_superseded: bool = False) -> list[str]:
    """Why the evidence of an entry that embeds its sources does not reproduce (empty when it does). From the recorded
    answer, its plan and the recorded proposal the harness re-derives everything the record states: the merged parse
    delivers the recorded claim (``recorded_claim_id``, else the entry's claim id) under the entry's claim id with the
    entry's text; the translator's real pipeline, served the recorded proposal under that id, delivers what
    ``pipeline_on_the_recorded_proposal`` states (for an OVS-TRN-006 entry: a translation with a problem and an engine
    result displayed as a success); the served problem is the embedded IR; and, unless ``rules_superseded``, the
    overseer's rules on the delivered problem, report and request (``checks.translation.restatement``, with the request's
    texts and supplied documents) name exactly the restating premises the record names as the writer's own, with the
    record's reasons, and exactly its ``transcriptions``, and the translator's own rule decides as ``translator_rule``
    states."""
    from epinoic_logic.ir.canonical import problem_digest
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks.translation import restatement
    ev = entry.get("evidence") or {}
    out = _source_faults(ev)
    if out:
        return out
    recorded_id = entry.get("recorded_claim_id") or entry["claim_id"]
    try:
        d = _delivery(ev, recorded_id)
    except Exception as exc:
        return [f"the recorded answer cannot be delivered ({type(exc).__name__}: {str(exc)[:160]})"]
    did = d.delivered_id(recorded_id)
    if did != entry.get("claim_id"):
        return [f"the merged parse delivers the recorded claim {recorded_id} as {did}, not {entry.get('claim_id')}"]
    claim = next(c for c in d.report.claims if c.claim_id == did)
    if " ".join(claim.claim_text.split()) != " ".join(str(entry.get("claim_text", "")).split()):
        out.append(f"the delivered claim {did} does not say the record's claim text")
    o = d.outcomes.get(did)
    if o is None:
        return out + [f"no outcome of claim {did} was delivered"]
    got = _pipeline_record(o)
    want = ev.get("pipeline_on_the_recorded_proposal") or {}
    if got != want:
        out.append(f"the pipeline on the recorded proposal gives {got}, not {want}")
    served = H.rekeyed_fixture(ev["recorded_proposal"], did, d.report.request_id).get("problem")
    try:
        if problem_digest(Problem.model_validate(served)) != (entry.get("translation") or {}).get("problem_sha256"):
            out.append("the recorded proposal served under the merged id is not the embedded IR")
    except Exception as exc:
        out.append(f"the recorded proposal holds no valid problem ({type(exc).__name__})")
    if entry.get("pass") == "rekeyed":
        # rule recorded-ids/2: the re-keyed pass serves a recorded proposal only to the claim it was written for
        why = H.fixture_mismatch(ev["recorded_proposal"], recorded_id, did, d.report)
        if why is not None:
            out.append(f"the re-keyed pass withholds the recorded proposal (rule {H.CORRESPONDENCE_RULE}): {why}")
    if entry.get("code") == "OVS-TRN-006" and rules_superseded and o.translation.problem is not None:
        # a retirement by the overseer's rules supersedes only their reading of the standings (which restating premises
        # are the writer's own, and why): which premises restate the conclusion (rules circularity-agreement and
        # semantic-restatement) and what the translator's own rule decides are re-derived as the entry recorded them
        texts, docs = _request_of(ev)
        rs = restatement(o.translation.problem, d.report, texts, request_documents=docs)
        rule = ev.get("translator_rule") or {}
        recorded_set = sorted(set(ev.get("restating_premises") or []) | set(ev.get("transcriptions") or []))
        if sorted(set(rs.own) | set(rs.grounded)) != recorded_set:
            out.append(f"the premises restating the conclusion are {sorted(set(rs.own) | set(rs.grounded))}, not the {recorded_set} the entry's evidence "
                       "names (its restating premises and transcriptions)")
        if rule and (list(rs.named) != list(rule.get("circular_premises") or []) or rs.translator_holds != bool(rule.get("every_named_premise_is_the_writers_own"))):
            out.append(f"the translator's rule names {list(rs.named)} and holds {rs.translator_holds}, not {rule}")
    if entry.get("code") == "OVS-TRN-006" and not rules_superseded:
        if o.translation.problem is None:
            return out + ["the pipeline delivered no problem, so no circular encoding reached the receipt"]
        texts, docs = _request_of(ev)
        rs = restatement(o.translation.problem, d.report, texts, request_documents=docs)
        rule = ev.get("translator_rule") or {}
        if not rs.holds or list(rs.own) != list(ev.get("restating_premises") or []):
            out.append(f"the overseer's rules name {list(rs.own)} (holding: {rs.holds}), not {ev.get('restating_premises')}")
        if "transcriptions" in ev and list(rs.grounded) != list(ev.get("transcriptions") or []):
            out.append(f"the overseer's rules uphold {list(rs.grounded)} as transcriptions, not {ev.get('transcriptions')}")
        if list(rs.named) != list(rule.get("circular_premises") or []) or rs.translator_holds != bool(rule.get("every_named_premise_is_the_writers_own")):
            out.append(f"the translator's rule names {list(rs.named)} and holds {rs.translator_holds}, not {rule}")
        why = {pid: reason for pid, reason in rs.why_own}
        if {pid: why.get(pid) for pid in rs.own} != (ev.get("why_own") or {}):
            out.append("the reasons the overseer's rule gives are not the record's")
        try:
            delivered = json.loads(o.translation.problem.model_dump_json(exclude_none=True))
        except Exception as exc:
            return out + [f"the delivered problem cannot be read ({type(exc).__name__})"]
        out += _shown_faults(entry, rs, delivered)
    return out


#: Kept for callers of the earlier name (a re-keyed entry's evidence is re-derived from its sources).
_rekeyed_evidence_faults = _sourced_evidence_faults


def _retirement_faults(entry: dict) -> list[str]:
    """Why a retired entry's retirement does not reproduce (empty when it does), by its kind (``RETIREMENT_KINDS``):
    :func:`_withheld_retirement_faults` (``translator_withholds``, the default) or :func:`_rules_retirement_faults`
    (``overseer_rules``). A retirement the code no longer supports refuses the record: the entry must be restored."""
    kind = (entry.get("retirement_evidence") or {}).get("kind", "translator_withholds")
    if kind not in RETIREMENT_KINDS:
        return [f"a retirement of kind {kind!r} has no rule to re-derive it"]
    if entry.get("code") != "OVS-TRN-006":
        return [f"a retirement of a {entry.get('code')} entry has no rule to re-derive it"]
    return _withheld_retirement_faults(entry) if kind == "translator_withholds" else _rules_retirement_faults(entry)


def _withheld_retirement_faults(entry: dict) -> list[str]:
    """Retirement kind ``translator_withholds`` (record version 2): the translator no longer delivers the encoding. On the
    recorded IR the translator's own circularity rule holds (``engine.runner.circular_premises`` names the restating
    premises and every one is the writer's own, ``assumed_grounding``), the pipeline's gate
    (``translate.pipeline.Translator._circularity``) rejects it with E112, and the engine withholds the ENTAILED proof (E112
    on the result). A translator that would deliver the encoding again makes the retirement fail."""
    from epinoic_logic.engine.results import SolverConfig
    from epinoic_logic.engine.runner import assumed_grounding, circular_premises, verify
    from epinoic_logic.ir.canonical import canonical_json
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.translate.pipeline import Translator, _Rejected
    out: list[str] = []
    ev = entry.get("retirement_evidence") or {}
    try:
        prob = Problem.model_validate((entry.get("translation") or {}).get("problem"))
    except Exception as exc:
        return [f"the embedded IR is not a valid problem ({type(exc).__name__})"]
    named = circular_premises(prob)
    by_id = {pr.id: pr for pr in prob.premises}
    rule = ev.get("translator_rule") or {}
    if not named or not all(assumed_grounding(by_id[pid].grounding) for pid in named if pid in by_id):
        out.append("the translator's own circularity rule no longer holds on the recorded IR")
    elif named != list(rule.get("circular_premises") or []):
        out.append(f"the translator's rule names {named}, not {rule.get('circular_premises')}")
    try:
        Translator._circularity(prob, "retirement")
        out.append("the translator's circularity gate would deliver the recorded IR")
    except _Rejected as exc:
        if exc.status.value != "INVALID_FORMALIZATION" or not any("E112" in d for d in exc.diagnostics):
            out.append(f"the translator's gate rejects the recorded IR as {exc.status.value}, not as circular (E112)")
    res = verify(canonical_json(entry["translation"]["problem"]), SolverConfig())
    if res.status.value != "ENTAILED" or not any(d.code == "E112" for d in res.diagnostics):
        out.append(f"the engine gives {res.status.value} with {[d.code for d in res.diagnostics]} on the recorded IR, not an ENTAILED proof it withholds (E112)")
    out += _merged_retirement_faults(entry)
    return out


def _merged_parse_of(entry: dict, d: Any, recorded_id: str) -> tuple[Optional[str], dict]:
    did = d.delivered_id(recorded_id)
    if did is None:
        return None, {}
    claim = next(c for c in d.report.claims if c.claim_id == did)
    o = d.outcomes.get(did)
    elig = o.translation.eligibility if o is not None else None
    return did, {"claim_id": did, "claim_text": claim.claim_text, "role": claim.claim_role,
                 "eligibility_class": elig.eligibility_class.value if elig is not None else None, "eligible": elig.eligible if elig is not None else None,
                 "earlier_claim_id_issued": recorded_id in {c.claim_id for c in d.report.claims}}


def _merged_retirement_faults(entry: dict, *, delivered: bool = False) -> list[str]:
    """Why the merged parse and the pipeline run a retirement states do not reproduce (empty when they do), re-derived
    from the recorded answer, its plan and the recorded proposal the retirement evidence embeds: the merged parse delivers
    the recorded claim (``recorded_claim_id``, else the entry's claim id) under ``merged_parse.claim_id``, with that text,
    role and eligibility; the translator's real pipeline, served the recorded proposal under the merged id, delivers
    exactly ``pipeline_on_the_recorded_proposal``. With ``delivered`` false (kind ``translator_withholds``) that run
    delivers no problem, so no engine run and no verdict; with ``delivered`` true (kind ``overseer_rules``) it delivers
    the problem the entry embeds, displayed as its engine result."""
    ev = entry.get("retirement_evidence") or {}
    out = _source_faults(ev)
    if out:
        return [f"{x}, so the merged parse and the pipeline run cannot be re-derived" for x in out]
    mp = ev.get("merged_parse") or {}
    recorded_id = entry.get("recorded_claim_id") or entry["claim_id"]
    try:
        d = _delivery(ev, recorded_id)
    except Exception as exc:
        return [f"the recorded answer cannot be delivered ({type(exc).__name__}: {str(exc)[:160]})"]
    did, got_parse = _merged_parse_of(entry, d, recorded_id)
    if did != mp.get("claim_id"):
        return [f"the merged parse delivers the recorded claim {recorded_id} as {did}, not {mp.get('claim_id')}"]
    if got_parse != mp:
        out.append(f"the merged parse gives {got_parse}, not {mp}")
    o = d.outcomes.get(did)
    if o is None:
        return out + [f"no outcome of claim {did} was delivered"]
    got = _pipeline_record(o)
    want = ev.get("pipeline_on_the_recorded_proposal") or {}
    if got != want:
        out.append(f"the pipeline on the recorded proposal gives {got}, not {want}")
    why = H.fixture_mismatch(ev["recorded_proposal"], recorded_id, did, d.report)
    if why is not None and ev.get("pass", "rekeyed") == "rekeyed":
        # the re-keyed replay that confirms a retirement serves only a proposal written for the claim (rule recorded-ids/2);
        # a retirement confirmed on the round's GENUINE pass is served by its recorded id, the arena's own rule
        out.append(f"the re-keyed pass withholds the recorded proposal (rule {H.CORRESPONDENCE_RULE}): {why}")
    if not delivered and (o.translation.problem is not None or o.verification is not None):
        out.append("the pipeline delivered a problem for the retired claim: the translator would deliver the encoding again")
    if delivered and (o.translation.problem is None or o.verification is None):
        out.append("the pipeline delivered no problem for the retired claim, so the retirement's reading of it cannot be re-derived")
    return out


def _rules_retirement_faults(entry: dict) -> list[str]:
    """Retirement kind ``overseer_rules`` (record versions 4 and 5): the translator still delivers the encoding, but the
    overseer's rules, corrected, no longer read it as a circular fault, and the ENGINE shows why. Re-derived from the
    sources the retirement embeds: the merged parse and the pipeline's run (:func:`_merged_retirement_faults`, the
    problem delivered and run); the served problem is the embedded IR; the overseer's rules on the delivered problem,
    report and request (``checks.translation.restatement`` with the request's texts and supplied documents) give exactly
    the reading ``overseer_rules`` states (the writer's-own restating premises, the transcriptions, which of them a check
    shows are not data and which are undecided: rule data-standing); rule engine-shown, re-derived with plain engine runs
    on the embedded IR, gives exactly ``grade`` and the runs it rests on (``engine_runs``); and its codes, exactly
    ``expected_findings_on_replay``, never include OVS-TRN-006 (version 4: OVS-TRN-010, the restatement redundant;
    version 5: OVS-TRN-011, the result rests only on data premises no check verifies or refutes, which shows nothing
    beyond a data conjunct needing its data premise). Record version 6: the reasons the rules give for each restating
    premise are the retirement's ``overseer_rules.why_own``, exactly (as an entry's evidence states them). A rule that
    would read the encoding as circular again refuses the record: the entry must be restored (record version 6 restored
    three entries so, :func:`_restoration_faults`)."""
    from epinoic_logic.ir.canonical import problem_digest
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks.translation import restatement
    ev = entry.get("retirement_evidence") or {}
    out = _merged_retirement_faults(entry, delivered=True)
    if out:
        return out
    recorded_id = entry.get("recorded_claim_id") or entry["claim_id"]
    d = _delivery(ev, recorded_id)
    did = d.delivered_id(recorded_id)
    o = d.outcomes[did]
    served = H.rekeyed_fixture(ev["recorded_proposal"], did, d.report.request_id).get("problem")
    if problem_digest(Problem.model_validate(served)) != (entry.get("translation") or {}).get("problem_sha256"):
        out.append("the recorded proposal served under the merged id is not the embedded IR")
    texts, docs = _request_of(ev)
    rs = restatement(o.translation.problem, d.report, texts, request_documents=docs)
    rules = ev.get("overseer_rules") or {}
    got = _standing_record(rs)
    if not rs.holds or any(got.get(k) != rules.get(k) for k in ("own", "transcriptions", "shown", "undecided", "undecided_disclosed", "standings")):
        out.append(f"the overseer's rules give {({k: got[k] for k in ('own', 'transcriptions', 'shown', 'undecided', 'undecided_disclosed')})} (holding: "
                   f"{rs.holds}), not {({k: rules.get(k) for k in ('own', 'transcriptions', 'shown', 'undecided', 'undecided_disclosed')})}")
    elif got["why_own"] != rules.get("why_own"):
        # record version 6: the reasons the record states are the rules' own, exactly (as for an entry's evidence)
        out.append("the reasons the overseer's rules give for the restating premises are not the retirement's (overseer_rules.why_own)")
    delivered = json.loads(o.translation.problem.model_dump_json(exclude_none=True))
    grade = _grade_record(rs, delivered)
    if grade != ev.get("grade"):
        out.append(f"rule engine-shown grades the restatement {grade}, not {ev.get('grade')}")
    codes = sorted({g[0] for g in grade if str(g[0]).startswith("OVS-")})
    if "OVS-TRN-006" in codes:
        out.append("rule engine-shown grades the restatement OVS-TRN-006: the result rests on a premise shown not to be data, the entry must be restored")
    runs = [_engine_run(delivered, list(r.get("without") or [])) for r in (ev.get("engine_runs") or [])]
    if runs != list(ev.get("engine_runs") or []) or not runs:
        out.append(f"the engine runs the grade rests on give {runs}, not {ev.get('engine_runs')}")
    if list(ev.get("expected_findings_on_replay") or []) != codes:
        out.append(f"a retirement by the overseer's rules expects exactly the codes rule engine-shown gives ({codes}) on the replay, not "
                   f"{ev.get('expected_findings_on_replay')}")
    return out


def _superseded_as_retired(entry: dict) -> dict:
    """A restored entry as the record held it while it was retired: its fields, the evidence it carried then
    (``superseded_evidence``) and the retirement it supersedes (``superseded_retirement``)."""
    sup, old = entry.get("superseded_retirement") or {}, entry.get("superseded_evidence") or {}
    base = {k: v for k, v in entry.items() if k not in _RESTORED_FIELDS}
    return {**base, "evidence": old.get("evidence"), "why_genuine": old.get("why_genuine"), "retired_in_version": sup.get("retired_in_version"),
            "why_retired": sup.get("why_retired"), "retirement_evidence": sup.get("retirement_evidence")}


def _restoration_faults(entry: dict, version: Any) -> list[str]:
    """Why a RESTORED entry (record version 6) is not restored with evidence (empty when it is): it names the version that
    restores it (no later than the record's) and why; it keeps the retirement it supersedes and the evidence it carried
    then, both as recorded; and that retirement, re-derived as the harness re-derives every retirement
    (:func:`_retirement_faults`), NO LONGER holds for the reason a restoration needs: the overseer's corrected rules grade
    the restatement OVS-TRN-006 (rule engine-shown) on the sources the retirement embeds, which must be the entry's own. A
    retirement that would still reproduce keeps the entry retired: the restoration is refused."""
    out = [f"the restored entry lacks {k}" for k in _RESTORED_FIELDS if not entry.get(k)]
    if out:
        return out
    if not isinstance(entry["restored_in_version"], int) or not isinstance(version, int) or entry["restored_in_version"] > version:
        return ["the restored entry names a version this record is not"]
    sup = entry["superseded_retirement"]
    if not isinstance(sup.get("retired_in_version"), int) or sup["retired_in_version"] >= entry["restored_in_version"]:
        return ["the superseded retirement names no version before the restoration"]
    if not sup.get("why_retired") or not isinstance(sup.get("retirement_evidence"), dict):
        return ["the superseded retirement lacks why_retired or retirement_evidence"]
    if not isinstance((entry["superseded_evidence"] or {}).get("evidence"), dict):
        return ["the superseded evidence lacks the evidence the entry carried when it was retired"]
    old = _superseded_as_retired(entry)
    out += _same_sources_faults(old)
    if _has_sources(entry.get("evidence") or {}) and _has_sources(sup["retirement_evidence"]):
        out += [f"the superseded retirement embeds another {f.replace('_', ' ')} than the restored entry's evidence" for f in _SOURCE_FIELDS
                if sup["retirement_evidence"].get(f + "_sha256") != (entry.get("evidence") or {}).get(f + "_sha256")]
    why = _retirement_faults(old)
    if not any("grades the restatement OVS-TRN-006" in w for w in why):
        out.append("the superseded retirement does not fail because the corrected rules grade the restatement OVS-TRN-006: "
                   + ("it still reproduces, so the entry stays retired" if not why else f"it fails otherwise ({'; '.join(why)[:300]})"))
    return out


def load_adjudications(path: Optional[Path] = None) -> dict:
    """The adjudicated genuine faults (``scripts/overseer/adjudicated_genuine_faults.json``, format
    ``overseer-adjudicated-genuine-faults/1.0``): real faults of recorded genuine transfers, each naming its round, channel,
    agent, claim and finding code, with the engine evidence that decides it (the recorded IR, its restating premises, the
    statuses with and without them) and why it is genuine. The record is refused (``HarnessError``) unless its format, its
    fields and unique ids hold and every entry's evidence reproduces with the engine: the run never relies on an
    adjudication it cannot re-derive. An entry makes the run stricter, never looser (gate
    ``adjudicated_genuine_faults_raised``). A RETIRED entry (``retired``: an entry a later version took out, with why and
    the evidence) keeps its fields and its original evidence, which must still reproduce (a retirement by the overseer's
    rules supersedes only the record's reading of those rules), and its retirement must reproduce too
    (:func:`_retirement_faults`): an entry is never retired silently, and a retirement the code no longer supports refuses
    the record. A RESTORED entry (record version 6) keeps the retirement it supersedes and the evidence it carried then,
    and that retirement must no longer hold because the corrected rules grade the restatement OVS-TRN-006
    (:func:`_restoration_faults`): an entry is never restored without evidence either."""
    p = Path(path) if path is not None else ADJUDICATIONS_FILE
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise H.HarnessError(f"the adjudication record {p.name} cannot be read ({type(exc).__name__})") from exc
    if not isinstance(doc, dict) or doc.get("format") != ADJUDICATIONS_FORMAT or not isinstance(doc.get("entries"), list):
        raise H.HarnessError(f"the adjudication record {p.name} is not of format {ADJUDICATIONS_FORMAT}")
    retired = doc.get("retired") or []
    if not isinstance(retired, list):
        raise H.HarnessError(f"the adjudication record {p.name} is not of format {ADJUDICATIONS_FORMAT} (retired is not a list)")
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
        if e.get("pass", "genuine") not in PASSES:
            raise H.HarnessError(f"the adjudicated entry {e['id']!r} names a pass that is not one of {PASSES}")
        if e.get("pass") == "rekeyed":
            missing = [k for k in _REKEYED_FIELDS if not e.get(k)] + [k for k in _SOURCE_FIELDS if not (e.get("evidence") or {}).get(k)]
            if missing:
                raise H.HarnessError(f"the re-keyed entry {e['id']!r} lacks {missing}")
        faults = _evidence_faults(e)
        if faults:
            raise H.HarnessError(f"the evidence of the adjudicated entry {e['id']!r} does not reproduce: {'; '.join(faults)}")
        if any(e.get(k) for k in _RESTORED_FIELDS):
            # record version 6: an entry restored from a retirement keeps that retirement, which must no longer hold
            faults = _restoration_faults(e, doc.get("version"))
            if faults:
                raise H.HarnessError(f"the restoration of the adjudicated entry {e['id']!r} does not reproduce: {'; '.join(faults)}")
    for e in retired:
        missing = [k for k in _RETIRED_FIELDS if not (isinstance(e, dict) and e.get(k))]
        if missing:
            raise H.HarnessError(f"a retired entry lacks {missing}")
        if e["id"] in seen:
            raise H.HarnessError(f"the adjudicated entry id {e['id']!r} is used twice")
        seen.add(e["id"])
        if e["code"] not in OVS_CODES:
            raise H.HarnessError(f"the retired entry {e['id']!r} names an unknown code")
        if not isinstance(e["retired_in_version"], int) or not isinstance(doc.get("version"), int) or e["retired_in_version"] > doc["version"]:
            raise H.HarnessError(f"the retired entry {e['id']!r} names a version this record is not")
        kind = e["retirement_evidence"].get("kind", "translator_withholds")
        if e["retirement_evidence"].get("pass", "rekeyed") not in PASSES:
            raise H.HarnessError(f"the retirement of the entry {e['id']!r} names a pass that is not one of {PASSES}")
        # the entry a retirement keeps is still an entry: its own pass, and the fields a re-keyed entry needs (record version 5)
        if e.get("pass", "genuine") not in PASSES:
            raise H.HarnessError(f"the retired entry {e['id']!r} names a pass that is not one of {PASSES}")
        if e.get("pass") == "rekeyed":
            missing = [k for k in _REKEYED_FIELDS if not e.get(k)] + [k for k in _SOURCE_FIELDS if not (e.get("evidence") or {}).get(k)]
            if missing:
                raise H.HarnessError(f"the re-keyed retired entry {e['id']!r} lacks {missing}")
        if kind not in RETIREMENT_KINDS:
            raise H.HarnessError(f"the retirement of the entry {e['id']!r} names the kind {kind!r}, which is not one of {RETIREMENT_KINDS}; restore the entry")
        # both the entry's own evidence and its retirement are re-derived, and every reason either fails is named
        faults = _evidence_faults(e, rules_superseded=kind == "overseer_rules") + _same_sources_faults(e)
        rfaults = _retirement_faults(e)
        if faults or rfaults:
            raise H.HarnessError(" | ".join(x for x in (
                f"the evidence of the retired entry {e['id']!r} does not reproduce: {'; '.join(faults)}" if faults else "",
                f"the retirement of the entry {e['id']!r} does not reproduce: {'; '.join(rfaults)}; restore the entry" if rfaults else "") if x))
    return {"format": doc["format"], "version": doc.get("version"), "source": p.name, "entries": list(doc["entries"]),
            "retired": [{"id": e["id"], "retired_in_version": e["retired_in_version"], "why_retired": e["why_retired"], "round": e["round"],
                         "channel": e["channel"], "task_id": e["task_id"], "agent_id": e["agent_id"], "claim_id": e["claim_id"],
                         "recorded_claim_id": e.get("recorded_claim_id") or e["claim_id"],
                         "kind": e["retirement_evidence"].get("kind", "translator_withholds"),
                         "pass": e["retirement_evidence"].get("pass", "rekeyed"),
                         "merged_claim_id": (e["retirement_evidence"].get("merged_parse") or {}).get("claim_id"),
                         "pipeline_on_the_recorded_proposal": e["retirement_evidence"].get("pipeline_on_the_recorded_proposal"),
                         "expected_findings_on_replay": list(e["retirement_evidence"].get("expected_findings_on_replay") or []),
                         "sources": {k: e["retirement_evidence"].get(k) for k in ("recorded_answer", "recorded_answer_sha256", "recorded_proposal_sha256")}}
                        for e in retired]}


def entries_of_pass(adjudications: Optional[dict], pass_name: str) -> list[dict]:
    """The adjudicated entries measured in ``pass_name`` (an entry names no pass when it is measured in the genuine pass)."""
    return [e for e in (adjudications or {}).get("entries", []) if e.get("pass", "genuine") == pass_name]


def _task_of(channel_key: str) -> str:
    """The task (genuine channel key) of an arena channel key (``group`` or ``group::variant``)."""
    return str(channel_key).split("::", 1)[0]


def finding_matches_entry(entry: dict, round_name: str, channel_key: str, f: Any, pass_name: str = "genuine") -> bool:
    """Whether finding ``f`` on channel ``channel_key`` of round ``round_name``, in the pass ``pass_name``, is exactly the
    adjudicated fault ``entry``: the same pass (an entry that names none is measured in the genuine pass), round, channel
    (task), code and severity error, the entry's claim and only it, and the entry's agent among the finding's agents. STEM
    repair 4: the pass is matched too (before, an entry of the genuine pass matched the same error on the re-keyed pass)."""
    if pass_name not in PASSES:
        raise ValueError(f"unknown pass {pass_name!r}; expected one of {PASSES}")
    get = (lambda k: f.get(k)) if isinstance(f, dict) else (lambda k: getattr(f, k, None))
    return (entry.get("pass", "genuine") == pass_name and entry.get("round") == round_name and entry.get("channel") == _task_of(channel_key)
            and get("code") == entry.get("code") and get("severity") == "error" and list(get("claim_ids") or []) == [entry.get("claim_id")]
            and entry.get("agent_id") in set(get("agent_ids") or []))


def adjudicated_entry_for(adjudications: Optional[dict], round_name: str, channel_key: str, f: Any, pass_name: str = "genuine") -> Optional[dict]:
    for e in (adjudications or {}).get("entries", []):
        if finding_matches_entry(e, round_name, channel_key, f, pass_name):
            return e
    return None


def classify_genuine_errors(round_name: str, channel_key: str, findings: Iterable[Any], adjudications: Optional[dict],
                            pass_name: str = "genuine") -> tuple[list[dict], list[dict]]:
    """``(false alarms, adjudicated faults raised)`` among the error-level findings of a GENUINE channel of the pass
    ``pass_name``: an error is a false alarm unless it matches an adjudicated entry of that pass exactly
    (:func:`finding_matches_entry`)."""
    false_alarms, raised = [], []
    for f in findings:
        if f.severity != "error" or f.code in GENUINE_EXCLUDED:
            continue
        e = adjudicated_entry_for(adjudications, round_name, channel_key, f, pass_name)
        if e is not None:
            raised.append({"entry": e["id"], "pass": pass_name, "channel": channel_key, "code": f.code, "claim_ids": list(f.claim_ids),
                           "message": f.message[:300]})
        else:
            false_alarms.append({"channel": channel_key, "code": f.code, "claim_ids": list(f.claim_ids), "message": f.message[:300]})
    return false_alarms, raised


def classify_mutation_errors(round_name: str, channel_key: str, findings: Iterable[Any], adjudications: Optional[dict]) -> tuple[list[str], list[str]]:
    """``(errors that disagree with the receipt, adjudicated errors)`` on an arena fault variant (the arena's variants run in
    the genuine pass): an extra error matching an adjudicated entry of the genuine pass for the same claim of the same task is
    the genuine fault the variant carries over, not a disagreement with the receipt; every other error-level finding (rule
    codes aside) still is."""
    errors, adjudicated = [], []
    for f in findings:
        if f.severity != "error" or f.code in RULE_CODES:
            continue
        e = adjudicated_entry_for(adjudications, round_name, channel_key, f, "genuine")
        (adjudicated if e is not None else errors).append(f.code if e is None else e["id"])
    return errors, adjudicated


def adjudication_gate(result: dict) -> dict:
    """Gate ``adjudicated_genuine_faults_raised``. (1) Every adjudicated entry of a round this run replayed is raised as an
    error on its genuine transfer in the pass the entry names (the round's genuine pass, or its re-keyed pass); a missing
    one fails, with what that pass shows for its claim. (2) Every retired entry of a replayed round is confirmed on the
    pass its retirement names (the round's re-keyed pass, the default: its claim delivered under the merged id with the
    recorded proposal served to it; or its genuine pass, where the arena serves the proposal by its recorded id): the
    claim gets exactly the pipeline outcome the retirement states and exactly the OVS-TRN-006 / -010 / -011 findings it
    expects on replay (``expected_findings_on_replay``: none when the translator withholds the encoding; OVS-TRN-010 or
    OVS-TRN-011, never OVS-TRN-006, for a retirement by the overseer's corrected rules, record versions 4 to 6), from the
    recorded sources the entry embeds; a translator that delivers the encoding again, or a rule that reads it as circular
    again, fails the gate even when the record was not updated. Entries and retirements of rounds not run, and
    retirements of a pass the round did not run, are listed, never counted."""
    adj = result.get("adjudications") or {}
    entries = adj.get("entries", [])
    rounds = result.get("rounds", {})
    measured = [e for e in entries if e["round"] in rounds]
    missing = []
    for e in measured:
        rd = rounds[e["round"]]
        pass_name = e.get("pass", "genuine")
        part = rd["genuine"] if pass_name == "genuine" else (rd.get("rekeyed") or {}).get("genuine")
        # STEM repair 4: an entry is raised only by an error in the pass it names, of its own round (before, the ids raised in either
        # pass of any round were pooled, so an entry of the genuine pass raised only on the re-keyed pass passed the gate)
        if part is not None and any(r.get("entry") == e["id"] and r.get("pass", pass_name) == pass_name for r in part.get("adjudicated_raised", [])):
            continue
        if part is None:
            missing.append({"entry": e["id"], "pass": pass_name, "genuine_channel_shows": f"the round ran no {pass_name} pass"})
            continue
        evidence = (rd.get("adjudication_evidence") if pass_name == "genuine" else (rd.get("rekeyed") or {}).get("adjudication_evidence")) or {}
        seen = (part.get("claims_findings") or {}).get(f"{e['channel']}|{e['claim_id']}", [])
        missing.append({"entry": e["id"], "pass": pass_name, "recorded_translation": evidence.get(e["id"]),
                        "genuine_channel_shows": seen or "no finding names the claim (not delivered under this id, or not translated)"})
    confirmed, unconfirmed, retired_not_measured = [], [], []
    for x in adj.get("retired", []):
        if x.get("round") not in rounds:
            continue
        rd = rounds[x["round"]]
        part = rd if x.get("pass", "rekeyed") == "genuine" else rd.get("rekeyed")
        if part is None or not x.get("merged_claim_id"):
            retired_not_measured.append(x["id"])
            continue
        obs = (part.get("retired_on_replay") or {}).get(x["id"])
        if (obs is not None and obs.get("pipeline") == x.get("pipeline_on_the_recorded_proposal") and list(obs.get("trn_findings") or [])
                == list(x.get("expected_findings_on_replay") or []) and obs.get("sources_match")):
            confirmed.append(x["id"])
        else:
            unconfirmed.append({"entry": x["id"], "pass": x.get("pass", "rekeyed"), "expected": x.get("pipeline_on_the_recorded_proposal"),
                                "expected_findings": x.get("expected_findings_on_replay") or [],
                                "replay_shows": obs or f"the merged claim was not delivered on the {x.get('pass', 'rekeyed')} pass"})
    return {"ok": not missing and not unconfirmed, "value": len(measured) - len(missing), "of": len(measured), "missing": missing,
            "retired_confirmed_on_replay": len(confirmed), "retired_of": len(confirmed) + len(unconfirmed), "retired_unconfirmed": unconfirmed,
            "retired_not_measured": retired_not_measured, "not_run": [e["id"] for e in entries if e["round"] not in rounds], "record": adj.get("source"),
            "record_version": adj.get("version"), "retired": [e["id"] for e in adj.get("retired", [])]}


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


def recorded_sources_match(src: Path, task_id: str, recorded_claim_id: str, evidence: dict) -> Optional[str]:
    """None when the round's recorded answer of ``task_id`` and its recorded fixture of ``recorded_claim_id`` are the ones
    an entry's evidence embeds (by SHA-256); else why not."""
    from epinoic_logic.ir.canonical import sha256_hex
    try:
        item = json.loads((Path(src) / "specialists" / f"{task_id}.json").read_text(encoding="utf-8"))
        fixture = json.loads((Path(src) / "translations" / f"{task_id}.json").read_text(encoding="utf-8"))["claims"][recorded_claim_id]
    except Exception as exc:
        return f"the round holds no recorded answer or fixture {recorded_claim_id} of {task_id} ({type(exc).__name__})"
    answer = {k: item.get(k) for k in (evidence.get("recorded_answer") or {})}
    if sha256_hex(canonical_json_of(answer)) != evidence.get("recorded_answer_sha256"):
        return "the round's recorded answer is not the embedded one (digest differs)"
    if sha256_hex(canonical_json_of(fixture)) != evidence.get("recorded_proposal_sha256"):
        return "the round's recorded fixture is not the embedded proposal (digest differs)"
    return None


def observe_retired(retired: list[dict], src: Path, channel_key: str, report: Any, outcome: Any, findings: Iterable[Any]) -> dict[str, dict]:
    """What a pass shows for each retired entry whose claim ``outcome`` is (the channel, the report's agent and the claim
    id the retirement names): the pipeline's outcome, the restatement codes (``RESTATEMENT_CODES``) the audit raises on the
    claim, and whether the round's recorded sources are the ones the retirement embeds."""
    out: dict[str, dict] = {}
    for x in retired:
        if x["channel"] != channel_key or report.agent_id != x["agent_id"] or outcome.claim_id != x["merged_claim_id"]:
            continue
        named = sorted({f.code for f in findings if f.code in RESTATEMENT_CODES and outcome.claim_id in f.claim_ids
                        and (not f.agent_ids or x["agent_id"] in f.agent_ids)})
        why = recorded_sources_match(src, x["task_id"], x.get("recorded_claim_id") or x["claim_id"], x.get("sources") or {})
        out[x["id"]] = {"claim_id": outcome.claim_id, "pipeline": _pipeline_record(outcome), "trn_findings": named, "sources_match": why is None,
                        "sources": why or "the round's recorded answer and fixture are the ones the retirement embeds"}
    return out


def run_round_contained(name: str, src: Path, out: Path, pack: Any, *, probe_scope: str, replay_mode: str = "inline",
                        adjudications: Optional[dict] = None) -> dict:
    rdir = out / "rounds"
    plain_copy = H.copy_round(src, rdir / "without-auditor", name=name)
    ra = H.arena()
    delivery_pass = getattr(ra, "DELIVERY_PASS", None)
    if delivery_pass is not None:  # the arena's delivery pass measures delivery, not the auditor: off in contained runs
        ra.DELIVERY_PASS = False
    try:
        plain = ra.run_round(plain_copy)
    finally:
        if delivery_pass is not None:
            ra.DELIVERY_PASS = delivery_pass
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
        own = [e for e in entries_of_pass(adjudications, "genuine") if e["round"] == name]
        rec["adjudication_evidence"] = {e["id"]: recorded_translation_matches(src, e) or "the round's recorded translation is the adjudicated IR" for e in own}
        rec["fixtures_matching_no_delivered_claim"] = (rr.results.get("translation_fixtures_matching_no_delivered_claim") or {}).get("count", 0)
        usable = {"entries": [e for e in own if recorded_translation_matches(src, e) is None]}
        retired_here = [x for x in (adjudications or {}).get("retired", []) if x["round"] == name and x.get("merged_claim_id")
                        and x.get("pass", "rekeyed") == "genuine"]
        retired_on_replay: dict[str, dict] = {}
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
                false_alarms, raised = classify_genuine_errors(name, c.key, audit.report.findings, usable, "genuine")
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
                if retired_here:  # a retirement confirmed on the genuine pass (record version 5: served by its recorded id)
                    for t in aud.view(c.uid).transfers:
                        if t.receipt is None or t.report is None:
                            continue
                        for oc in t.receipt.outcomes:
                            retired_on_replay.update(observe_retired(retired_here, src, c.key, t.report, oc, audit.report.findings))
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
                   recorded_overseer_reports=recorded_self_reports(src, recorded), retired_on_replay=retired_on_replay)
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


def run_rekeyed_contained(name: str, src: Path, out: Path, *, replay_mode: str = "inline", adjudications: Optional[dict] = None,
                          pack: Any = None) -> dict:
    """The RE-KEYED pass of a round recorded before the translator merge (rule ``recorded-ids``): the arena serves a
    translation fixture only to the claim id it was recorded under, so on such a round the merged parsers' claims (STEM
    ids ``s``/``m``/``c``, agent-qualified generic ids) get none of the recorded model-proposed translations. A copy of the
    round has its fixtures re-keyed to the claims the merged parse delivers (``ovs_harness.rekey_translations``) and its
    genuine pass replayed with the auditor attached, every recorded translation that reaches a delivered claim going
    through the merged translator's real pipeline and the overseer's checks; a second re-keyed copy runs without the
    auditor (non-interference). Reported and gated like the genuine pass: false alarms (an error matching no entry of
    this pass), the entries of this pass raised, every retired entry's claim as the replay delivers it, replay
    agreement, every audit verifying, and the translations served (STEM ones by letter). With ``pack``, every genuine
    channel of the pass is reviewed by the probe agents too (``review_channel``), so the agents are shown the recorded
    translations of the merged claims, STEM ones among them (the STEM probe accuses one: unresolved, human review)."""
    rdir = out / "rounds" / "rekeyed"
    plain_copy = H.copy_round(src, rdir / "without-auditor", name=name)
    H.rekey_translations(plain_copy)
    plain = H.run_round_without_auditor(plain_copy, genuine_only=True)
    copy = H.copy_round(src, rdir, name=name)
    mapping = H.rekey_translations(copy)
    own = [e for e in entries_of_pass(adjudications, "rekeyed") if e["round"] == name]
    retired = [x for x in (adjudications or {}).get("retired", []) if x["round"] == name and x.get("merged_claim_id")
               and x.get("pass", "rekeyed") == "rekeyed"]
    aud = H.new_auditor(H.keyring_for("arena"), replay_mode=replay_mode)
    try:
        rr = H.replay_round(copy, aud, genuine_only=True)
        rec: dict[str, Any] = {"rule": H.REKEY_RULE, "transmissions": rr.results["transmissions"], "functional": rr.results["functional"],
                               "arena_unchanged_by_the_auditor": _arena_signature(rr.results) == _arena_signature(plain)
                               and (rr.results["functional"], rr.results["transmissions"]) == (plain["functional"], plain["transmissions"]),
                               "fixtures": sum(m["fixtures"] for m in mapping.values()), "fixtures_rekeyed": sum(m["rekeyed"] for m in mapping.values()),
                               # rule recorded-ids/2: a fixture the round's records show was written for another claim is withheld
                               "correspondence_rule": H.CORRESPONDENCE_RULE,
                               "fixtures_withheld": sum(len(m.get("withheld") or {}) for m in mapping.values()),
                               "withheld": {stem: m["withheld"] for stem, m in mapping.items() if m.get("withheld")},
                               "rekeyed_by_branch": dict(sum((Counter({m["branch"]: m["rekeyed"]}) for m in mapping.values()), Counter())),
                               "fixtures_matching_no_delivered_claim": (rr.results.get("translation_fixtures_matching_no_delivered_claim") or {}).get("count", 0)}
        evidence = {}
        for e in own:
            why = recorded_sources_match(src, e["task_id"], e["recorded_claim_id"], e.get("evidence") or {})
            evidence[e["id"]] = why or "the round's recorded answer and fixture are the ones the entry embeds"
        rec["adjudication_evidence"] = evidence
        usable = {"entries": [e for e in own if evidence[e["id"]].startswith("the round's recorded answer and fixture are")]}
        genuine = {"channels": 0, "transfers": 0, "false_alarms": [], "adjudicated_raised": [], "claims_findings": {}, "states": Counter()}
        replay = {"results_replayed": 0, "disagreements": [], "inconclusive": 0, "mode": replay_mode}
        translations = {"checked": 0, "served_stem": Counter(), "trn_codes_on_genuine": Counter(), "withheld_by_the_translator_e112": 0}
        channels, retired_on_replay = [], {}
        for c in rr.channels:
            audit = aud.audit(c.uid)
            view = aud.view(c.uid)
            codes = Counter(f.code for f in audit.report.findings)
            channels.append({"key": c.key, "variant": c.variant, "audit_id": audit.audit_id, "state": audit.state, "codes": dict(codes),
                             "verifies": verify_audit(audit, aud.keyring), "transfers": len(audit.message_ids)})
            replay["results_replayed"] += audit.coverage.results_replayed
            replay["disagreements"] += [f"{c.key}: {f.message[:200]}" for f in audit.report.findings if f.code == "OVS-RES-007"]
            replay["inconclusive"] += codes.get("OVS-RES-008", 0)
            translations["checked"] += len(audit.translations)
            if c.variant != "genuine":
                continue
            genuine["channels"] += 1
            genuine["transfers"] += len(audit.message_ids)
            genuine["states"][audit.state] += 1
            false_alarms, raised = classify_genuine_errors(name, c.key, audit.report.findings, usable, "rekeyed")
            genuine["false_alarms"] += false_alarms
            genuine["adjudicated_raised"] += raised
            for e in own:
                if e["channel"] == c.key:
                    genuine["claims_findings"][f"{e['channel']}|{e['claim_id']}"] = sorted(
                        f"{f.code} ({f.severity})" for f in audit.report.findings if e["claim_id"] in f.claim_ids and (not f.agent_ids or e["agent_id"] in f.agent_ids))
            for f in audit.report.findings:
                if f.code.startswith("OVS-TRN"):
                    translations["trn_codes_on_genuine"][f"{f.code} ({f.severity})"] += 1
            for t in view.transfers:
                if t.receipt is None or t.report is None:
                    continue
                for o in t.receipt.outcomes:
                    if o.translation.provider is not None and o.claim_id[:1] in ("s", "m", "c") and "@" not in o.claim_id:
                        translations["served_stem"][o.claim_id[:1]] += 1
                    if o.translation.problem is None and any("E112" in d for d in o.translation.diagnostics):
                        translations["withheld_by_the_translator_e112"] += 1
                    retired_on_replay.update(observe_retired(retired, src, c.key, t.report, o, audit.report.findings))
        genuine["states"] = dict(genuine["states"])
        translations["served_stem"] = dict(translations["served_stem"])
        translations["trn_codes_on_genuine"] = dict(translations["trn_codes_on_genuine"])
        rec.update(channels=channels, genuine=genuine, replay=replay, translations=translations, retired_on_replay=retired_on_replay)
        reviews = []
        if pack is not None:
            for c in rr.channels:
                if c.variant != "genuine":
                    continue
                try:
                    reviews.append(review_channel(rr.hub_for(c.key), c.key, pack))
                except Exception as exc:
                    reviews.append({"key": c.key, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1200:]})
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
           # STEM repair 11: each call's system text is the pack's composition for the dossier it carries
           "system_text_is_the_pack": all(c.system == pack.system_text_for(H.dossier_of_user_text(c.user)) for c in provider.calls)}
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
            if result["rounds"][name].get("fixtures_matching_no_delivered_claim"):
                # a round recorded before the translator merge: its recorded translations reach the merged claims only re-keyed
                result["rounds"][name]["rekeyed"] = run_rekeyed_contained(name, found[name], out, replay_mode=replay_mode, adjudications=adjudications,
                                                                         pack=pack)
    result["replay_mode"] = replay_mode
    if "r7" in list(rounds):
        # the STEM fault classes (decision 60): one planted fault per class on copies of r7's recorded STEM transfers, through
        # an audited hub, each probe's dossier evidence and, for a translation, a scripted agent built from the same pack
        result["stem_probes"] = run_stem_probes(out, Path(rounds_root), pack) if "r7" in found else {"measured": False, "why": "the recorded round r7 is not present"}
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


def run_stem_probes(out: Path, rounds_root: Path, pack: Any) -> dict:
    """The STEM fault-class probes (``stem_probes.py``) on copies of r7's recorded STEM transfers, written under
    ``out/stem``; returns their gate and their class table."""
    import stem_probes as SP
    doc = SP.run_probes(out / "stem", rounds_root, pack=pack)
    H.write_json(out / "stem" / "stem_probes.json", doc)
    (out / "stem" / "stem_probes.md").write_text(SP.summary_md(doc), encoding="utf-8")
    return {"measured": bool(doc.get("measured")), "why": doc.get("why"), "gate": doc.get("gate"), "file": str(out / "stem" / "stem_probes.json"),
            "classes": {k: v["probes"] for k, v in (doc.get("classes") or {}).items()}, "wall_s": doc.get("wall_s")}


def stem_review_gate(rekeyed: list[dict]) -> dict:
    """The fifth repair (finding (d) of the re-test of the fourth): the agents must be shown the recorded STEM translations.
    Every re-keyed pass that served one has a review whose STEM probe was shown one and accused it (the probe gate checks
    that the accusation stays unresolved)."""
    serving = [x for x in rekeyed if x.get("translations", {}).get("served_stem")]
    return {"ok": all(bool(x.get("reviews")) and any(rv.get("stem_translation_reviewed") for rv in x["reviews"]) for x in serving),
            "reviewed": sorted({f"{rv['key']}|{rv['stem_translation_reviewed']}" for x in rekeyed for rv in x.get("reviews", []) if rv.get("stem_translation_reviewed")}),
            "passes_serving_stem": len(serving)}


def gates(r: dict) -> dict:
    rounds = list(r.get("rounds", {}).values())
    rekeyed = [rd["rekeyed"] for rd in rounds if rd.get("rekeyed")]
    passes = rounds + rekeyed  # every replay with the auditor attached: each round's genuine and mutation channels, and its re-keyed pass
    reviews = [rv for rd in rounds for rv in rd.get("reviews", [])] + [rv for x in rekeyed for rv in x.get("reviews", [])]
    g = {
        "agents_only_from_the_exported_pack": {"ok": bool(reviews) and all(rv.get("system_text_is_the_pack") for rv in reviews),
                                               "source": r.get("pack", {}).get("source")},
        # an error on a genuine transfer is a false alarm unless it matches an adjudicated genuine fault of its pass exactly
        # (round, channel, claim, code, agent); every adjudicated fault must be raised (the next gate)
        "no_false_alarm_on_genuine_transfers": {"ok": all(not x["genuine"]["false_alarms"] for x in passes),
                                                "value": sum(len(x["genuine"]["false_alarms"]) for x in passes),
                                                "rekeyed": sum(len(x["genuine"]["false_alarms"]) for x in rekeyed)},
        "adjudicated_genuine_faults_raised": adjudication_gate(r),
        "arena_faults_named_by_receipts_and_confirmed": {"ok": all(m["receipt_named_it"] and m["overseer_agrees_with_receipt"] for rd in rounds for m in rd["mutations"]),
                                                         "value": sum(1 for rd in rounds for m in rd["mutations"] if m["receipt_named_it"] and m["overseer_agrees_with_receipt"]),
                                                         "of": sum(len(rd["mutations"]) for rd in rounds)},
        # decision 20: only a worker-process replay is independent; an inline run says what it measured (contained round c1)
        "replay_agreement_on_definitive_results": {"ok": all(not x["replay"]["disagreements"] for x in passes),
                                                    "replayed": sum(x["replay"]["results_replayed"] for x in passes),
                                                    "replay_mode": r.get("replay_mode", "inline"),
                                                    "scope": "worker process (independent)" if r.get("replay_mode") == "process"
                                                    else "in-process only: replay independence not established"},
        "arena_unchanged_by_the_auditor": {"ok": all(x["arena_unchanged_by_the_auditor"] for x in passes)},
        "every_task_audit_verifies": {"ok": all(c["verifies"] for x in passes for c in x["channels"])},
        "probes_as_expected": {"ok": bool(reviews) and all(not rv.get("error") and all(p["ok"] for p in rv["probes"].values()) for rv in reviews),
                               "reviews": len(reviews)},
        "reviews_change_no_clearance": {"ok": bool(reviews) and all(rv.get("clearances_unchanged") for rv in reviews)},
        "recorded_stem_translations_reviewed_by_agents": stem_review_gate(rekeyed),
        # a round recorded before the translator merge serves its recorded translations to the merged claims only re-keyed:
        # the run must have replayed that pass, so those translations are checked (never silently left out)
        "recorded_translations_served_under_merged_ids": {
            "ok": all(bool(rd.get("rekeyed")) == bool(rd.get("fixtures_matching_no_delivered_claim")) and
                      (not rd.get("rekeyed") or (rd["rekeyed"]["fixtures_rekeyed"] > 0 and rd["rekeyed"]["translations"]["checked"] > 0))
                      for rd in rounds),
            "rounds": {name: {"fixtures_matching_no_delivered_claim": rd.get("fixtures_matching_no_delivered_claim", 0),
                              **({"fixtures_rekeyed": rd["rekeyed"]["fixtures_rekeyed"], "translations_checked": rd["rekeyed"]["translations"]["checked"],
                                  "stem_translations_served": rd["rekeyed"]["translations"]["served_stem"]} if rd.get("rekeyed") else {})}
                       for name, rd in r.get("rounds", {}).items()}},
    }
    if not rounds:
        for k in ("no_false_alarm_on_genuine_transfers", "arena_faults_named_by_receipts_and_confirmed", "replay_agreement_on_definitive_results",
                  "arena_unchanged_by_the_auditor", "every_task_audit_verifies", "agents_only_from_the_exported_pack", "probes_as_expected", "reviews_change_no_clearance",
                  "adjudicated_genuine_faults_raised", "recorded_translations_served_under_merged_ids", "recorded_stem_translations_reviewed_by_agents"):
            g[k] = {"ok": False, "state": "NOT MEASURED (no recorded round present)"}
    if "tamper" in r:
        g["tamper_suite"] = {"ok": all(r["tamper"]["gates"].values()), **r["tamper"]["counts"]}
    if "stem_probes" in r:
        sp = r["stem_probes"]
        gate = sp.get("gate") or {}
        g["stem_fault_classes_named"] = ({"ok": bool(gate.get("ok")), **{k: v for k, v in gate.items() if k not in ("ok", "classes_with_a_named_probe")}}
                                         if sp.get("measured") else {"ok": False, "state": f"NOT MEASURED ({sp.get('why')})"})
    return g


def _div_label(d: dict) -> str:
    return "{} ({}, owner {})".format(d["int_code"], d["classification"], d["owner"])


def summary_md(r: dict) -> str:
    L = ["# Contained Overseer run", "", f"Pack: {r['pack']['identity']['name']} {r['pack']['identity']['version']} {r['pack']['identity']['sha256']} "
         f"(loaded from {r['pack']['source']})", f"Models: {r['claims_about_models']}", f"Wall: {r.get('wall_s')} s", "", "## Gates", ""]
    L += [f"- {k}: {'PASS' if v['ok'] else 'FAIL'} " + json.dumps({x: y for x, y in v.items() if x != 'ok'}) for k, v in r["gates"].items()]
    adj = r.get("adjudications") or {}
    if adj:
        L += ["", f"Adjudicated genuine faults record: {adj.get('source')} version {adj.get('version')}, {len(adj.get('entries', []))} entries, "
              f"{len(adj.get('retired', []))} retired (each retirement re-derived before the run):"]
        L += [f"- retired in version {x['retired_in_version']}: {x['id']}: {x['why_retired'][:400]}" for x in adj.get("retired", [])]
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
        rk = rd.get("rekeyed")
        if rk:
            gk = rk["genuine"]
            L += [f"- re-keyed pass (rule {rk['rule']}: the round's {rk['fixtures']} recorded fixtures served, {rk['fixtures_rekeyed']} of them re-keyed to the claims "
                  f"the merged parse delivers; rule {rk.get('correspondence_rule', H.CORRESPONDENCE_RULE)}: {rk.get('fixtures_withheld', 0)} withheld, the round's "
                  f"records showing each was written for another claim): {rk['functional']}/{rk['transmissions']} functional, unchanged by the auditor: "
                  f"{rk['arena_unchanged_by_the_auditor']}; "
                  f"{gk['channels']} genuine channels, {gk['transfers']} transfers, states {gk['states']}, false alarms {len(gk['false_alarms'])}, "
                  f"adjudicated genuine faults raised {len(gk['adjudicated_raised'])}"
                  + "".join(f"\n  - {x['entry']}: {x['code']} on {x['channel']} claim {', '.join(x['claim_ids'])}" for x in gk["adjudicated_raised"])
                  + "".join(f"\n  - false alarm: {x['code']} on {x['channel']} claim(s) {', '.join(x.get('claim_ids', []))}: {x['message'][:160]}" for x in gk["false_alarms"]),
                  f"  - translations checked {rk['translations']['checked']}, STEM translations served {rk['translations']['served_stem']}, withheld by the "
                  f"translator as circular (E112) {rk['translations']['withheld_by_the_translator_e112']}; OVS-TRN on genuine: {rk['translations']['trn_codes_on_genuine']}",
                  f"  - replay: {rk['replay']['results_replayed']} results replayed, {len(rk['replay']['disagreements'])} disagreements, {rk['replay']['inconclusive']} inconclusive",
                  f"  - reviews: {len(rk.get('reviews', []))}; probes as expected: "
                  f"{sum(1 for rv in rk.get('reviews', []) if not rv.get('error') and all(p['ok'] for p in rv['probes'].values()))}; STEM translations the "
                  f"STEM probe was shown and accused: {sorted({rv['stem_translation_reviewed'] for rv in rk.get('reviews', []) if rv.get('stem_translation_reviewed')})}",
                  "  - retired entries on the replay: " + ("; ".join(f"{k}: {v['claim_id']} {v['pipeline'].get('translation_status')}, display "
                                                                   f"{v['pipeline'].get('display_status')}, OVS-TRN {v['trn_findings'] or 'none'}"
                                                                   for k, v in rk.get("retired_on_replay", {}).items()) or "none")]
        for s in rd["recorded_overseer_reports"]:
            L.append(f"- recorded overseer report {s['file']} (agent self-report): claimed functional rate {s.get('claimed_functional_rate')}, "
                     f"recomputed {s.get('recomputed_from_recorded_results')}, agrees {s.get('agrees')}")
    if r.get("rounds_missing"):
        L += ["", "Rounds not present: " + ", ".join(r["rounds_missing"])]
    if "stem_probes" in r:
        sp = r["stem_probes"]
        L += ["", "## STEM fault-class probes", "", json.dumps({k: v for k, v in (sp.get("gate") or {}).items() if k != "classes_with_a_named_probe"}) if sp.get("measured")
              else f"NOT MEASURED: {sp.get('why')}"]
        L += [f"- {c}: " + ", ".join(f"{pid} {o}" for pid, o in probes.items()) for c, probes in (sp.get("classes") or {}).items()]
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
