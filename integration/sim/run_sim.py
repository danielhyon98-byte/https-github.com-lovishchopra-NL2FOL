#!/usr/bin/env python3
"""The local end-to-end simulation of the integration kit (PROTOCOL.md section 14.5; playbook step 12).

    python integration/sim/run_sim.py --website <export> --agents <agents copy> --translator <kit> \
        --corpus <kit>/integration/sim/corpus --out <dir> [--rounds <dir>]

Order: copy the corpus (the kit and any supplied rounds are never written to) -> preflight the service in the
``integration-sim`` profile with ephemeral keys -> start it on loopback with the fixture provider and the evidence tap
-> the website driver (users.json through the disposable export) -> the agents driver -> the reference harnesses on
another copy (reference.py) -> the fault cases (faults.py) -> the tampering cases (tamper_web.py) -> the gates
(gates.py). Writes ``<out>/summary.md`` (one line per gate: PASS, FAIL or NOT RUN with its reason) and
``<out>/results.json`` (denominators, case ids, sub-checks, what was not run and why). Exit 0 only when no gate FAILs
and all eight gates PASS; every part that is missing makes its gates NOT RUN, never PASS.

Network: the service binds 127.0.0.1 only and the drivers' fetch refuses every other host. No provider is called.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SIM = Path(__file__).resolve().parent


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"kit_sim_{name}", SIM / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def service_env(translator: Path, corpus_copy: Path, evidence: Path) -> dict:
    """Ephemeral keys (in the service's environment only; the drivers get the service token through <out>/work/token,
    mode 0600, inside the simulation's own output directory), the sim profile, the fixture provider fed from the copy."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("EPINOIC_")}
    env.update({
        "PYTHONPATH": str(translator / "src"), "EPINOIC_PROFILE": "integration-sim", "EPINOIC_SERVICE_ENV": "sim",
        "EPINOIC_SERVICE_TOKEN": secrets.token_hex(24), "EPINOIC_SIGNING_KEY": secrets.token_hex(32), "EPINOIC_VERDICT_KEY": secrets.token_hex(32),
        "EPINOIC_OVERSEER_SECRET": secrets.token_hex(32), "EPINOIC_TRANSLATION_PROVIDER": "fixture", "EPINOIC_FIXTURE_DIR": str(corpus_copy),
        "EPINOIC_SIM_EVIDENCE_DIR": str(evidence), "EPINOIC_FLASH_ROUTER": os.environ.get("EPINOIC_FLASH_ROUTER", "none"),
    })
    return env


def preflight(translator: Path, env: dict) -> tuple[bool, str]:
    proc = subprocess.run([sys.executable, "-m", "epinoic_logic.integration", "preflight"], env=env, capture_output=True, text=True, timeout=300)
    line = (proc.stderr.strip().splitlines() or [""])[-1] if proc.returncode else "ready"
    return proc.returncode == 0, line


def start_service(env: dict, port: int):
    proc = subprocess.Popen([sys.executable, "-m", "epinoic_logic.integration", "serve", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return None, (proc.stderr.read() or "").strip().splitlines()[-1:] or ["the service exited"]
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/capabilities", headers={"Authorization": f"Bearer {env['EPINOIC_SERVICE_TOKEN']}"})
            with urllib.request.urlopen(req, timeout=2) as r:  # noqa: S310 - loopback only
                if r.status == 200:
                    return proc, json.loads(r.read())
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    return None, ["the service did not answer on loopback within 60 s"]


def run(args) -> int:
    gates = _module("gates")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    translator = Path(args.translator).resolve()
    corpus_root = Path(args.corpus).resolve()
    rounds = [p for p in sorted((corpus_root / "synthetic").iterdir()) if (p / "specialists").is_dir()]
    if args.rounds:
        rounds += [p for p in sorted(Path(args.rounds).iterdir()) if (p / "specialists").is_dir()]
    results: dict = {"rounds": [r.name for r in rounds], "not_run": {}, "subchecks": {}}
    work = out / "work"
    if work.exists():
        shutil.rmtree(work)
    service_copy, reference_copy = work / "service-corpus", work / "reference-corpus"
    for r in rounds:
        shutil.copytree(r, service_copy / r.name)
        shutil.copytree(r, reference_copy / r.name)

    # 1. The service: preflight, then serve on loopback.
    env = service_env(translator, service_copy, work / "evidence")
    ready, line = preflight(translator, env)
    results["service"] = {"preflight": line}
    proc = None
    port = _free_port()
    if ready:
        proc, caps = start_service(env, port)
        results["service"]["started"] = proc is not None
        if proc is None:
            results["not_run"]["service"] = caps
    else:
        results["not_run"]["service"] = f"the service refused to start: {line}"

    try:
        # 2. The website path and the agents driver.
        website_ok = False
        node = shutil.which("node")
        if proc is not None and node and args.website:
            token_file = work / "token"
            token_file.write_text(env["EPINOIC_SERVICE_TOKEN"])
            os.chmod(token_file, 0o600)
            d = subprocess.run([node, str(SIM / "website-driver.mjs"), "--website", args.website, "--service", f"http://127.0.0.1:{port}", "--token-file", str(token_file),
                                "--users", str(SIM / "users.json"), "--corpus", str(service_copy), "--out", str(work / "website")],
                               capture_output=True, text=True, timeout=1800)
            website_ok = d.returncode == 0
            if not website_ok:
                results["not_run"]["website_path"] = (d.stderr.strip().splitlines() or ["the website driver failed"])[-1]
        else:
            results["not_run"]["website_path"] = ("no checks service" if proc is None else "no Node.js" if not node else "no website export (--website)")
        results["not_run"].setdefault("agents_path", results["not_run"].get("service", "the agents turns are connected in phase 2"))

        # 3. The reference harnesses on another copy of exactly the same items.
        reference = _module("reference")
        ref_by_item, ref_mutations = {}, []
        for r in rounds:
            rr = reference.run_reference(translator, reference_copy / r.name)
            ref_by_item.update({f"{r.name}/{k}": v for k, v in rr["projections"].items()})
            ref_mutations += rr["mutations"]
            results["subchecks"][f"arena:{r.name}"] = {"functional": rr["functional"], "qualified": rr["qualified"], "genuine": rr["genuine"]}
        contained = reference.contained_available(translator)
        if contained is None:
            results["not_run"]["contained"] = "scripts/overseer/run_contained.py is not on this tree"

        # 4. Fault cases and 5. tampering cases (sub-check at the adapter: never the gate).
        faults = _module("faults")
        cases = []
        for r in rounds:
            cases += faults.fault_cases(translator, reference_copy / r.name)
        results["subchecks"]["fault_cases"] = len(cases)
        tamper = _module("tamper_web").adapter_results(translator)
        results["subchecks"]["tamper_adapter"] = tamper

        # 6. The gates.
        compare = _module("compare")
        website_projections = None  # filled from the evidence tap by the website path (phase 2)
        gate_results = [
            gates.g_eq_arena(website_projections, ref_by_item, compare.differences) if website_ok else gates.not_run("G-EQ-ARENA", results["not_run"]["website_path"]),
            gates.g_eq_contained(None) if contained is None else gates.not_run("G-EQ-CONTAINED", "the contained comparison is connected in phase 2"),
            gates.g_fault(None) if not website_ok else gates.not_run("G-FAULT", "the fault replay is connected in phase 2"),
            gates.g_inv(None),
            gates.g_hon(None),
            gates.g_del(None, None),
            gates.g_tamper(None),
            gates.g_ovs(None),
        ]
        results["gates"] = gate_results
        results["reference_items"] = sorted(ref_by_item)
        results["reference_mutations"] = len(ref_mutations)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    lines = gates.summary_lines(results["gates"])
    lines += ["", "Not run, and why:"] + [f"- {k}: {v}" for k, v in sorted(results["not_run"].items())]
    lines += ["", "Sub-checks (information, never a gate):"] + [f"- {k}: {json.dumps(v)}" for k, v in sorted(results["subchecks"].items())]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "results.json").write_text(json.dumps(results, indent=1, default=str) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return gates.exit_status(results["gates"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the integration kit's local simulation")
    ap.add_argument("--website", default=None)
    ap.add_argument("--agents", default=None)
    ap.add_argument("--translator", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", default=None, help="recorded rounds Daniel supplies and approves (D15); copied first, never written")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
