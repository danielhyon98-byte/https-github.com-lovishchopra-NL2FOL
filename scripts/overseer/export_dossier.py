#!/usr/bin/env python3
"""Dossier export of the contained Overseer harness (``docs/OVERSEER_DESIGN.md`` sections 9.2, 13.8 and 14, stage
``harness``): one JSON dossier per task variant and agent, issued under the identity of an EXPORTED knowledge pack.

    PYTHONPATH=src python scripts/overseer/export_dossier.py --pack EXPORTED_PACK --out DIR [--rounds ROOT] [--round r2 ...]
                                                          [--tamper TAMPER_OUT] [--modes blind[,informed]] [--lenses LENS,...]

``--pack`` is a pack written by the package's exporter (``python -m epinoic_logic.overseer.export --out ...``), a
directory or a zip. It is loaded with the package's loader (every file against its manifest, the pack digest against the
digest pinned in the code); a refused pack stops the export before anything is issued (exit status 2).

Inputs are read-only: each recorded round is COPIED into ``DIR/rounds/<name>`` and replayed there through a hub that
carries the auditor (every variant the arena runs: the genuine pass and its six fault mutations, each on its own
channel); ``--tamper`` takes the output directory of ``tamper.py`` and issues dossiers for every transfer record in it.

**The re-keyed pass** (the fifth repair of the translator merge; rule ``recorded-ids``, design decision 50). A round
recorded before the translator merge keys its recorded translation fixtures by the claim ids of its time, so on its
genuine pass the merged parsers' claims (the STEM ids ``s``, ``m`` and ``c``, agent-qualified generic ids) get none of
them, and no dossier of that pass carries a STEM translation. When the arena reports fixtures matching no delivered claim,
a further copy (``DIR/rounds/rekeyed/<name>``) has its fixtures re-keyed to the claims the merged parse delivers
(``ovs_harness.rekey_translations``; rule ``recorded-ids/2`` withholds a fixture the round's records show was written for
another claim) and its genuine pass is replayed with the auditor attached, as the contained run's re-keyed pass is: one
dossier per channel, agent and mode, variant ``<round>-rekeyed--<channel>``, its gold a genuine control's (the auditor's
own findings, the adjudicated faults of that pass among them). ``export.json`` counts the STEM translations the dossiers
carry (``stem_translations``), so the pack's STEM guidance is put in front of an agent on recorded STEM data.

For every task variant (one channel) the export writes, under ``DIR``:

* ``transfers/<variant>/``: the transfer record (the journal's events as issued, the signed task audit, identifiers);
* ``dossiers/<agent_id>/<variant>.<mode>.json``: the dossier issued to that agent (one agent per lens), built from a
  REBUILD of the transfer record (a fresh auditor fed the recorded events: the dossier comes from the record, never from
  live objects), in ``blind`` mode (no auditor finding: the measurement mode) and, with ``--modes``, ``informed`` mode
  (the recorded signed audit's findings). A dossier holds the request, the delivered payloads, the receipts, the cited
  signed results (redacted: no signature, no key) and, informed, the audit report. It holds NO gold label;
* ``issues.jsonl``: the issue record of every dossier (the intake's ``IssueRecord`` plus the variant, the paths and the
  keyring profile), so ``score_verdicts.py`` re-issues exactly the same dossier (same digest) from the same record;
* ``index.json``: dossier digest to dossier path. A deployed agent's reply to a dossier is stored as
  ``<dossier_sha256>.json`` (or ``.txt``) in a replies directory, for ``score_verdicts.py`` and ``run_contained.py``;
* ``gold/gold.json``: the ground truth, kept apart from the dossiers (never handed to an agent): per variant the faults
  injected (from the tampering manifest, or the arena's injected specialist faults that the receipts name), the
  auditor's own findings, whether it is a clean control, and the transfers it holds;
* ``export.json``: the pack identity, the rounds, the counts.

Keys are test constants (``ovs_harness.keyring_for``); there is no network and no model call. Every output goes under
``--out``, never into a recorded round.

Deviations from ``docs/OVERSEER_DESIGN.md``, listed as the stage requires: the default mode is ``blind`` only (decision
18: blind is the measurement mode, and a blind dossier is reproducible from the transfer record); ``informed`` dossiers
are issued from the recorded signed audit, so a rebuild re-issues them identically too.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ovs_harness as H  # noqa: E402

from epinoic_logic.overseer import KIND_CHECKS, LENSES, MODES, PackError, VerdictIntake  # noqa: E402
from epinoic_logic.overseer.dossier import dossier_json  # noqa: E402

EXPORT_FORMAT = "overseer-dossier-export/1.0"
GOLD_FORMAT = "overseer-gold/1.0"
#: Auditor codes that are never a fault of a transfer (coverage notes and info-level links).
NOT_FAULTS = ("OVS-PEER-003", "OVS-AUDIT-002", "OVS-AUDIT-003")


def kind_for(code: str, message: str = "") -> Optional[str]:
    """The accusation kind whose checks decide ``code`` (``figure_changed`` for an SYN-002 naming INT-LEDGER-023), or
    None when no kind maps it."""
    if code == "OVS-SYN-002" and "INT-LEDGER-023" in message:
        return "figure_changed"
    for kind, codes in KIND_CHECKS.items():
        if code in codes:
            return kind
    return None


def finding_record(f: Any) -> dict:
    d = f.model_dump(mode="json", exclude_none=True) if hasattr(f, "model_dump") else dict(f)
    out = {k: d.get(k) for k in ("code", "severity", "message_ids", "claim_ids", "report_ids", "document_ids", "formal_result_id", "related_result_ids") if d.get(k)}
    out["kind"] = kind_for(d.get("code", ""), d.get("message", ""))
    out["message"] = (d.get("message") or "")[:400]
    return out


def auditor_faults(audit: Any) -> list[dict]:
    """The deterministic auditor's own findings that a fault kind covers (errors and warnings): true findings an agent
    may name. DIV-001 is a true rule finding (the router must not act on what the Overseer's rules reject)."""
    out = []
    for i, f in enumerate(audit.report.findings):
        if f.code in NOT_FAULTS or f.severity == "info":
            continue
        kind = kind_for(f.code, f.message)
        idents = {k: sorted(v) for k, v in H.finding_ids(f).items() if v}
        out.append({"fault_id": f"auditor-{i}-{f.code}", "origin": "auditor", "class": kind or "infrastructure", "expected_codes": [f.code],
                    "identifiers": idents, "severity": f.severity, "agent_scorable": kind is not None, "visibility": "journal", "agent_only": False})
    return out


def _overlap(a: dict, b: dict) -> bool:
    """Whether two identifier sets share an identifier, a claim only within its report (rule ``report-scoped-claims``,
    ``ovs_harness.ids_overlap``): an auditor finding on another report's claim of the same id is not the injected fault."""
    return H.ids_overlap(a, b)


# ============================================================================================ issuing
class Exporter:
    def __init__(self, out: Path, pack: Any, *, modes: Iterable[str] = ("blind",), agents: Iterable[tuple[str, str]] = H.LENS_AGENTS) -> None:
        self.out = Path(out)
        self.pack = pack
        self.modes = tuple(modes)
        self.agents = tuple(agents)
        self.issues: list[dict] = []
        self.index: dict[str, str] = {}
        self.gold: dict[str, dict] = {}
        self.variants: list[str] = []
        #: STEM translations the issued dossiers carry: (variant, claim id) pairs and the dossiers that carry one
        self.stem_claims: set[tuple[str, str]] = set()
        self.stem_dossiers = 0

    def issue_variant(self, variant_id: str, record_dir: Path, gold: dict) -> int:
        """Rebuild the record, issue one dossier per agent and mode, write them, and keep the gold apart."""
        rec = H.load_record(record_dir)
        aud, uid = H.rebuild(rec.events, rec.keyring)
        n = 0
        try:
            view = aud.view(uid)
            intake = VerdictIntake(rec.keyring, accepted_packs={self.pack.identity})
            for agent_id, lens in self.agents:
                for mode in self.modes:
                    d = intake.issue(view, agent_id=agent_id, lens=lens, mode=mode, pack=self.pack.identity, audit=rec.audit if mode == "informed" else None)
                    issue = intake.issue_record(agent_id, d["task"]["task_id"])
                    rel = Path("dossiers") / agent_id / f"{variant_id}.{mode}.json"
                    (self.out / rel).parent.mkdir(parents=True, exist_ok=True)
                    (self.out / rel).write_text(dossier_json(d) + "\n", encoding="utf-8")  # canonical JSON, exactly as issued
                    self.index[d["dossier_sha256"]] = str(rel)
                    stem = stem_translations(d)
                    if stem:
                        self.stem_dossiers += 1
                        self.stem_claims.update((variant_id, c) for c in stem)
                    self.issues.append({"variant_id": variant_id, "dossier": str(rel), "transfers": str(Path(record_dir).relative_to(self.out)),
                                        "keyring_profile": rec.record["keyring_profile"], "issue": issue.model_dump(mode="json")})
                    n += 1
            gold = dict(gold)
            gold.update(variant_id=variant_id, task_id=view.task_id, channel_uid=uid, message_ids=[t.message_id for t in view.transfers if t.message_id],
                        transfers=sum(1 for t in view.transfers if t.message_id), audit_state=rec.audit.state,
                        auditor_findings=[finding_record(f) for f in rec.audit.report.findings])
            gold["faults"] = list(gold.get("faults", []))
            for af in auditor_faults(rec.audit):  # the auditor's own findings, unless one is the injected fault itself
                if not any(af["expected_codes"][0] in (tf.get("expected_codes") or []) and _overlap(af["identifiers"], tf.get("identifiers") or {})
                           for tf in gold["faults"]):
                    gold["faults"].append(af)
            gold["clean"] = not gold["faults"]
            self.gold[variant_id] = gold
            self.variants.append(variant_id)
        finally:
            aud.close()
        return n

    def finish(self, meta: dict) -> dict:
        with (self.out / "issues.jsonl").open("w", encoding="utf-8") as fh:
            for i in self.issues:
                fh.write(json.dumps(i, sort_keys=True) + "\n")
        H.write_json(self.out / "index.json", self.index)
        H.write_json(self.out / "gold" / "gold.json", {"format": GOLD_FORMAT, "pack": self.pack.identity.model_dump(), "variants": self.gold})
        summary = {"format": EXPORT_FORMAT, "pack": self.pack.identity.model_dump(), "pack_source": self.pack.source, "modes": list(self.modes),
                   "agents": [{"agent_id": a, "lens": lens} for a, lens in self.agents], "variants": len(self.variants), "dossiers": len(self.issues),
                   "clean_variants": sum(1 for g in self.gold.values() if g["clean"]),
                   "variants_with_faults": sum(1 for g in self.gold.values() if not g["clean"]),
                   "stem_translations": {"dossiers": self.stem_dossiers, "claims": len(self.stem_claims),
                                         "by_letter": dict(sorted(Counter(c[:1] for _v, c in self.stem_claims).items()))}, **meta}
        H.write_json(self.out / "export.json", summary)
        return summary


#: The claim-id letters of the STEM parsers (``adapters.stem_specialist.parser.ID_PREFIXES``).
STEM_ID_LETTERS = ("s", "m", "c")


def stem_translations(d: dict) -> list[str]:
    """The STEM claims (an id of a STEM parser, never agent-qualified) whose translation, carrying a problem, a dossier
    links to its claim."""
    from epinoic_logic.overseer import resolve_pointer
    out = []
    for link in d.get("links", {}).get("translations") or []:
        cid = str(link.get("claim_id") or "")
        if cid[:1] not in STEM_ID_LETTERS or not cid[1:2].isdigit() or "@" in cid or not link.get("translation_pointer"):
            continue
        try:
            translation = resolve_pointer(d, link["translation_pointer"])
        except Exception:
            continue
        if isinstance(translation, dict) and translation.get("problem") and cid not in out:
            out.append(cid)
    return out


def arena_gold(results: dict, key: str, variant: str) -> dict:
    """The gold of an arena channel: a genuine channel is a control; a mutation channel carries a specialist fault the
    receipt must name (the arena's own injected fault). Neither is a transfer fault: a fault the receipt names is no
    miscommunication (Inspection I3)."""
    gold: dict[str, Any] = {"origin": "arena_genuine" if variant == "genuine" else "arena_mutation", "channel_key": key, "faults": [], "injection": False}
    if variant != "genuine":
        recs = [r for r in results.get("records", []) if r.get("channel") == key]
        if recs:
            r = recs[0]
            gold["arena_injection"] = {"kind": r.get("variant"), "expected_receipt_codes": r.get("expected"), "functional": bool(r.get("functional")),
                                       "named_by": [f.get("code") for f in r.get("named_by", [])], "injected_claim_ids": r.get("injected_claim_ids", [])}
    return gold


def export_round(exporter: Exporter, name: str, src: Path) -> dict:
    """Replay a COPY of the round with the auditor, write a transfer record per channel, issue its dossiers."""
    work = exporter.out / "rounds"
    copy = H.copy_round(src, work)
    aud = H.new_auditor(H.keyring_for("arena"))
    try:
        rr = H.replay_round(copy, aud)
        counts = {"channels": 0, "dossiers": 0}
        for c in rr.channels:
            audit = aud.audit(c.uid)
            vid = f"{name}--{H.safe_name(c.key)}"
            rdir = exporter.out / "transfers" / vid
            H.write_record(rdir, auditor=aud, uid=c.uid, audit=audit, profile="arena", meta={"round": name, "channel_key": c.key, "variant": c.variant})
            g = arena_gold(rr.results, c.key, c.variant)
            g["round"] = name
            counts["dossiers"] += exporter.issue_variant(vid, rdir, g)
            counts["channels"] += 1
    finally:
        aud.close()
    # keep only the arena's own outputs of the copy (results.json, summary.md) as evidence
    for p in list(copy.iterdir()):
        if p.name not in ("results.json", "summary.md"):
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    counts["functional"] = f"{rr.results['functional']}/{rr.results['transmissions']}"
    if (rr.results.get("translation_fixtures_matching_no_delivered_claim") or {}).get("count", 0):
        # a round recorded before the translator merge: its recorded translations reach the merged claims only re-keyed
        counts["rekeyed"] = export_rekeyed_round(exporter, name, src)
    return counts


def export_rekeyed_round(exporter: Exporter, name: str, src: Path) -> dict:
    """The re-keyed pass of a round (module docstring): a COPY with its fixtures re-keyed to the merged claims, its genuine
    pass replayed with the auditor attached, a transfer record per channel and its dossiers issued."""
    copy = H.copy_round(src, exporter.out / "rounds" / "rekeyed", name=name)
    mapping = H.rekey_translations(copy)
    before = (exporter.stem_dossiers, len(exporter.stem_claims))
    aud = H.new_auditor(H.keyring_for("arena"))
    counts: dict[str, Any] = {"rule": H.REKEY_RULE, "correspondence_rule": H.CORRESPONDENCE_RULE, "channels": 0, "dossiers": 0,
                              "fixtures": sum(m["fixtures"] for m in mapping.values()), "fixtures_rekeyed": sum(m["rekeyed"] for m in mapping.values()),
                              "fixtures_withheld": sum(len(m.get("withheld") or {}) for m in mapping.values())}
    try:
        rr = H.replay_round(copy, aud, genuine_only=True)
        for c in rr.channels:
            audit = aud.audit(c.uid)
            vid = f"{name}-rekeyed--{H.safe_name(c.key)}"
            rdir = exporter.out / "transfers" / vid
            H.write_record(rdir, auditor=aud, uid=c.uid, audit=audit, profile="arena",
                           meta={"round": name, "pass": "rekeyed", "rule": H.REKEY_RULE, "channel_key": c.key, "variant": c.variant})
            g = arena_gold(rr.results, c.key, c.variant)
            g.update(round=name, origin="arena_genuine_rekeyed", rekey_rule=H.REKEY_RULE)
            counts["dossiers"] += exporter.issue_variant(vid, rdir, g)
            counts["channels"] += 1
        counts["functional"] = f"{rr.results['functional']}/{rr.results['transmissions']}"
    finally:
        aud.close()
    for p in list(copy.iterdir()):
        if p.name not in ("results.json", "summary.md"):
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    counts["stem_translations"] = {"dossiers": exporter.stem_dossiers - before[0], "claims": len(exporter.stem_claims) - before[1]}
    return counts


def tamper_gold(entry: dict) -> dict:
    """The gold of a tampering record: its fault (unless a control, or a fault of the agent side), from the manifest."""
    cls = entry["class"]
    faults = []
    if cls not in ("control", "agent", "pack", "runner", "lifecycle"):
        scorable = cls in KIND_CHECKS
        faults.append({"fault_id": entry["fault_id"], "origin": "tamper", "class": cls, "expected_codes": entry["expected_codes"], "identifiers": entry["injected"],
                       "agent_scorable": scorable, "visibility": entry["visibility"], "agent_only": entry["agent_only"], "severity": None})
    return {"origin": "tamper_control" if not faults else "tamper", "fault_id": entry["fault_id"], "case": entry["case"], "target": entry["target"],
            "faults": faults, "injection": bool(entry.get("injection"))}


def export_tamper(exporter: Exporter, tamper_dir: Path) -> dict:
    manifest = H.read_json(Path(tamper_dir) / "manifest.json")
    counts = {"records": 0, "dossiers": 0}
    for e in manifest["faults"]:
        if not e.get("record"):
            continue
        vid = f"tamper--{H.safe_name(e['fault_id'])}"
        rdir = exporter.out / "transfers" / vid
        if rdir.exists():
            shutil.rmtree(rdir)
        shutil.copytree(Path(tamper_dir) / e["record"], rdir)
        g = tamper_gold(e)
        counts["dossiers"] += exporter.issue_variant(vid, rdir, g)
        counts["records"] += 1
    return counts


def run_export(out: Path, pack_path: Path, *, rounds_root: Optional[Path] = None, rounds: Iterable[str] = H.DEFAULT_ROUNDS, tamper_dir: Optional[Path] = None,
               modes: Iterable[str] = ("blind",), lenses: Optional[Iterable[str]] = None) -> dict:
    inputs = [p for _n, p in H.round_dirs(rounds_root, H.ROUND_NAMES)] if rounds_root else []
    if tamper_dir:
        inputs.append(Path(tamper_dir))
    out = H.check_output_dir(out, inputs=inputs + [Path(pack_path)], must_be_empty=True)
    pack = H.load_exported_pack(pack_path)  # PackError: nothing is issued
    modes = tuple(modes)
    if not modes or any(m not in MODES for m in modes):
        raise H.HarnessError(f"modes must be among {MODES}")
    agents = H.LENS_AGENTS if not lenses else tuple((a, l) for a, l in H.LENS_AGENTS if l in set(lenses))
    if lenses and any(l not in LENSES for l in lenses):
        raise H.HarnessError(f"lenses must be among {LENSES}")
    exporter = Exporter(out, pack, modes=modes, agents=agents)
    t0 = time.perf_counter()
    meta: dict[str, Any] = {"rounds": {}, "rounds_missing": [], "tamper": None}
    if rounds_root:
        found = dict(H.round_dirs(rounds_root, rounds))
        for name in rounds:
            if name not in found:
                meta["rounds_missing"].append(name)
                continue
            meta["rounds"][name] = export_round(exporter, name, found[name])
    if tamper_dir:
        meta["tamper"] = export_tamper(exporter, tamper_dir)
    meta["wall_s"] = round(time.perf_counter() - t0, 2)
    return exporter.finish(meta)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Issue overseer dossiers for every task variant under an exported pack; gold kept apart.")
    ap.add_argument("--pack", required=True, type=Path, help="an exported knowledge pack (directory or zip) written by the package's exporter")
    ap.add_argument("--out", required=True, type=Path, help="output directory (new or empty; never inside a recorded round)")
    ap.add_argument("--rounds", type=Path, default=None, help="directory holding the recorded rounds")
    ap.add_argument("--round", action="append", default=None, help=f"round name (repeatable; default {', '.join(H.DEFAULT_ROUNDS)})")
    ap.add_argument("--tamper", type=Path, default=None, help="output directory of tamper.py: issue dossiers for its transfer records too")
    ap.add_argument("--modes", default="blind", help="comma-separated dossier modes: blind, informed")
    ap.add_argument("--lenses", default="", help="comma-separated lenses (default: one agent per lens)")
    args = ap.parse_args(argv)
    if not args.rounds and not args.tamper:
        ap.error("give --rounds and/or --tamper")
    try:
        summary = run_export(args.out, args.pack, rounds_root=args.rounds, rounds=args.round or H.DEFAULT_ROUNDS, tamper_dir=args.tamper,
                             modes=[m for m in args.modes.split(",") if m], lenses=[x for x in args.lenses.split(",") if x] or None)
    except PackError as exc:
        print(json.dumps({"refused": "pack", "reason": exc.reason, "detail": str(exc)}))
        return 2
    except H.HarnessError as exc:
        print(json.dumps({"refused": "harness", "detail": str(exc)}))
        return 2
    print(json.dumps({k: summary[k] for k in ("pack", "variants", "dossiers", "clean_variants", "variants_with_faults", "rounds", "rounds_missing", "tamper", "wall_s")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
