#!/usr/bin/env python3
"""Mutation gate of the auditor (``docs/OVERSEER_DESIGN.md`` section 13.7): for each check module, a mutant that
disables it must make its tamper cases fail. A check whose disabling leaves every one of its cases passing is reported
as UNTESTED: the suite would not notice it was gone.

    PYTHONPATH=src python scripts/overseer/mutate_auditor.py --out DIR [--modules custody,receipts,...] [--rounds ROOT] [--targets synthetic]

A mutant replaces the module's check functions, in this process only and for the duration of one run of its cases, by
stubs that find nothing (the harness's own ``patched``; no source file is edited). The cases of a module are the
tampering cases ``tamper.py`` tags with it (``Case.module``). For each mutant the script runs those cases and counts a
case KILLED when at least one of its faults that passed without the mutant is no longer detected under it. The gate:
every mutant kills at least one case.

Outputs under ``--out``: ``mutation.json`` and ``mutation.md``. Exit status 0 when the gate holds, 1 otherwise.
Keys are test constants; there is no network and no model call.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ovs_harness as H  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.overseer import audit as audit_mod  # noqa: E402
from epinoic_logic.overseer.checks import custody, fidelity, formal, joint, peer, receipts, results, synthesis, translation  # noqa: E402

MUTATION_FORMAT = "overseer-mutation/1.0"


def _none(*_a: Any, **_k: Any) -> None:
    return None


def _empty(*_a: Any, **_k: Any) -> list:
    return []


def _false(*_a: Any, **_k: Any) -> bool:
    return False


#: module -> the (object, attribute, stub) patches that disable it.
MUTANTS: dict[str, list[tuple[Any, str, Callable[..., Any]]]] = {
    "custody": [(custody, n, _none) for n in ("check_issue_consistency", "check_custody", "check_raw_text", "check_chain", "sweep_log")],
    "receipts": [(receipts, n, _none) for n in ("check_receipt_custody", "check_presented_receipt", "check_status", "check_delivery", "check_identifiers", "check_summary")],
    "results": [(results, "check_results", _none)],
    "formal": [(formal, n, _none) for n in ("check_formal_status", "check_branch_satisfied", "rederive")],
    "fidelity": [(fidelity, "check_fidelity", _none)],
    "selfcert": [(fidelity, "flags_self_certification", _false)],
    "translation": [(translation, "check_translations", _empty)],
    "peer": [(peer, n, _none) for n in ("check_forward", "check_peer_documents")],
    "synthesis": [(synthesis, n, _none) for n in ("check_synthesis_citations", "recheck_ledger", "recheck_disclosure")],
    "joint": [(joint, n, _none) for n in ("check_pool", "check_live_pool", "independent_joint")],
    "divergence": [(audit_mod, "check_divergence", _empty)],
    "shadow": [(audit_mod, "run_shadow", _none)],
    "replay": [(audit_mod, "replay_findings", _none)],
}


def cases_of(module: str) -> list[str]:
    return [c.name for c in T.CASES if module in c.module]


def _detected(manifest: dict) -> dict[str, tuple[str, bool]]:
    """fault id -> (the case that produced it, detected)."""
    return {e["fault_id"]: (e["group"], bool(e["detected"])) for e in manifest["faults"] if not e["skipped"] and not e["error"]}


def run_mutation(out: Path, *, modules: Optional[Iterable[str]] = None, rounds_root: Optional[Path] = None, targets: Iterable[str] = ("synthetic",)) -> dict:
    out = H.check_output_dir(out, inputs=[p for _n, p in H.round_dirs(rounds_root, H.ROUND_NAMES)] if rounds_root else [])
    modules = list(modules or MUTANTS)
    unknown = [m for m in modules if m not in MUTANTS]
    if unknown:
        raise H.HarnessError(f"unknown module(s) {unknown}; known: {sorted(MUTANTS)}")
    targets = tuple(targets)
    t0 = time.perf_counter()
    pack_dir = None
    report: dict[str, Any] = {"format": MUTATION_FORMAT, "targets": list(targets), "modules": {}}
    baseline_cases = sorted({c for m in modules for c in cases_of(m)})
    base = T.run_suite(out / "baseline", rounds_root=rounds_root, cases=baseline_cases, targets=targets, write_records=False, controls=False)
    pack_dir = base.get("pack_dir")
    base_detected = _detected(base)
    for m in modules:
        names = cases_of(m)
        if not names:
            report["modules"][m] = {"cases": [], "killed": [], "survived": [], "state": "UNTESTED (no case is tagged with this module)"}
            continue
        with H.patched(*MUTANTS[m]):
            mm = T.run_suite(out / f"mutant-{m}", rounds_root=rounds_root, cases=names, targets=targets, write_records=False, controls=False,
                             pack_dir=Path(pack_dir) if pack_dir else None)
        det = _detected(mm)
        killed, survived = [], []
        for case_name in names:
            was = [f for f, (group, ok) in base_detected.items() if group == case_name and ok]
            now_missed = [f for f in was if f not in det or not det[f][1]]
            (killed if now_missed else survived).append({"case": case_name, "faults_detected_without_mutant": was, "missed_under_mutant": now_missed})
        report["modules"][m] = {"patched": [f"{getattr(o, '__name__', type(o).__name__)}.{a}" for o, a, _s in MUTANTS[m]], "cases": names,
                                "killed": killed, "survived": survived, "state": "TESTED" if killed else "UNTESTED"}
    report["gate"] = {"ok": all(v["state"] == "TESTED" for v in report["modules"].values()),
                      "untested": [k for k, v in report["modules"].items() if v["state"] != "TESTED"]}
    report["wall_s"] = round(time.perf_counter() - t0, 2)
    H.write_json(out / "mutation.json", report)
    (out / "mutation.md").write_text(mutation_md(report), encoding="utf-8")
    return report


def mutation_md(r: dict) -> str:
    lines = ["# Mutation of the auditor", "", f"Gate: {'PASS' if r['gate']['ok'] else 'FAIL'}; untested: {r['gate']['untested'] or 'none'}; wall {r['wall_s']} s", "",
             "| module | cases | killed | survived | state |", "| --- | --- | --- | --- | --- |"]
    for m, v in r["modules"].items():
        lines.append(f"| {m} | {len(v['cases'])} | {', '.join(k['case'] for k in v['killed']) or '-'} | {', '.join(k['case'] for k in v['survived']) or '-'} | {v['state']} |")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Mutation gate: disabling each auditor check module must make its tamper cases fail.")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--modules", default="", help=f"comma-separated modules (default: all of {', '.join(MUTANTS)})")
    ap.add_argument("--rounds", type=Path, default=None)
    ap.add_argument("--targets", default="synthetic")
    args = ap.parse_args(argv)
    try:
        r = run_mutation(args.out, modules=[m for m in args.modules.split(",") if m] or None, rounds_root=args.rounds, targets=[t for t in args.targets.split(",") if t])
    except H.HarnessError as exc:
        print(json.dumps({"refused": str(exc)}))
        return 2
    print(json.dumps({"gate": r["gate"], "wall_s": r["wall_s"]}))
    return 0 if r["gate"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
