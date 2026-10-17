#!/usr/bin/env python3
"""Readiness of the integration (playbook steps 5, 6, 7, 7a and 14). Read-only: it never writes into a repository,
never fetches, never deploys and never calls a provider; services it starts bind 127.0.0.1 and stop before it exits.

    check.py --g1 <kit>                       gate G1: the kit commit carries every required part
    check.py --translator <kit>               generated files fresh, Z3 found, the service's preflight line
    check.py --start-service [--profile integration-sim] [--kit <kit>]
                                              start the service on loopback with ephemeral keys, read the capabilities
    check.py --router <module> [--kit <kit>]  the flash router's hello and its plans over the router-port vectors
    check.py --all --website <checkout> --website-copy <export> --agents <copy> --sim-out <dir> [--kit <kit>]

Every row is PASS, BLOCKER, NOT RUN (with its reason) or REPORTED (the flash router: reported, never required).
Exit status 1 when a row is a BLOCKER. On a pre-build commit (the parts phase 2 connects are absent), a BLOCKER row that
only those parts cause says "(connected in phase 2: ...)"; a BLOCKER row without that mark is a defect of the commit.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
PASS, BLOCKER, NOT_RUN, REPORTED = "PASS", "BLOCKER", "NOT RUN", "REPORTED"


def row(rows: list, name: str, status: str, detail: str) -> None:
    rows.append((name, status, detail))


def _contract_version(kit: Path) -> str | None:
    contract = kit / "docs" / "integration-contract.md"
    m = re.search(r"Contract version:\*\* ([0-9.]+)", contract.read_text(encoding="utf-8")) if contract.exists() else None
    return m.group(1) if m else None


def _named_policies(kit: Path) -> bool:
    pol = (kit / "src" / "epinoic_logic" / "engine" / "policies.py").read_text(encoding="utf-8")
    return "NAMED_POLICIES" in pol and "def named_policy" in pol


def _overseer_package(kit: Path) -> bool:
    return (kit / "src" / "epinoic_logic" / "overseer" / "__init__.py").exists()


def g1(kit: Path, rows: list) -> None:
    version, named, overseer = _contract_version(kit), _named_policies(kit), _overseer_package(kit)
    # the contract line moves to 0.4 when phase 2 merges contract 0.3: before that merge (no named policies yet) a
    # contract older than 0.4 is the expected pre-build state; after it, an older line is a defect
    contract_note = " (connected in phase 2: contract 0.3 merge, then the line says 0.4)" if version != "0.4" and not named else ""
    row(rows, "G1 contract 0.4", PASS if version == "0.4" else BLOCKER, f"contract {version or 'absent'}{contract_note}")
    row(rows, "G1 overseer package", PASS if overseer else BLOCKER,
        "src/epinoic_logic/overseer/" + ("" if overseer else " absent (connected in phase 2: the rebuilt overseer and its port adapter)"))
    reg = (kit / "src" / "epinoic_logic" / "branches" / "registry.py").read_text(encoding="utf-8")
    row(rows, "G1 STEM branches", PASS if all(b in reg for b in ("sciences", "mathematics", "computer_science")) else BLOCKER, "branches/registry.py")
    row(rows, "G1 named policies (contract 0.3)", PASS if named else BLOCKER,
        "engine/policies.py NAMED_POLICIES" + ("" if named else " absent (connected in phase 2: contract 0.3 merge)"))
    compat = json.loads((kit / "integration" / "COMPATIBILITY.json").read_text(encoding="utf-8"))
    row(rows, "G1 protocol", PASS if compat.get("protocol") == "epinoic.integration.v1" else BLOCKER, compat.get("protocol", "?"))
    router = kit / "flash-router"
    version = re.search(r'^version = "([^"]+)"', (router / "pyproject.toml").read_text(encoding="utf-8"), re.M) if (router / "pyproject.toml").exists() else None
    row(rows, "flash router sub-project", REPORTED,
        f"flash-router/ present (epinoic-flash-router {version.group(1) if version else '?'}; attached only when EPINOIC_FLASH_ROUTER names it; never required)"
        if router.exists() else "absent: the floor plan runs (never required)")


def _py(kit: Path) -> dict:
    """The environment of a process run from the kit: no EPINOIC_ variable of the caller, and the kit's src/ on the
    import path, with the flash-router sub-project's src/ after it when the kit has one (so a service started with
    EPINOIC_FLASH_ROUTER=epinoic_flash_router.port can import the router in the router's own process)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("EPINOIC_")}
    paths = [kit / "src"] + ([kit / "flash-router" / "src"] if (kit / "flash-router" / "src").is_dir() else [])
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in paths)
    return env


def translator(kit: Path, rows: list) -> None:
    for tool in ("generate.py", "vectors.py", "build_corpus.py", "manifest.py"):
        p = subprocess.run([sys.executable, str(kit / "integration" / "tools" / tool), "--check"], env=_py(kit), capture_output=True, text=True, timeout=600)
        row(rows, f"generated files fresh ({tool})", PASS if p.returncode == 0 else BLOCKER, (p.stdout.strip().splitlines() or ["fresh"])[-1][:120])
    p = subprocess.run([sys.executable, "-c", "from epinoic_logic.integration.bootstrap import require_z3; require_z3(); print('z3 found')"],
                       env=_py(kit), capture_output=True, text=True, timeout=120)
    row(rows, "Z3 (bootstrap)", PASS if p.returncode == 0 else BLOCKER, (p.stdout + p.stderr).strip().splitlines()[-1][:120])
    env = service_env(kit)
    p = subprocess.run([sys.executable, "-m", "epinoic_logic.integration", "preflight"], env=env, capture_output=True, text=True, timeout=300)
    line = (p.stderr.strip().splitlines() or ["ready"])[-1] if p.returncode else "ready"
    note = ""
    if line.startswith("KIT-HS-006") and not _named_policies(kit):
        note = " (connected in phase 2: the named policies of contract 0.3; then KIT-HS-007 until the overseer port adapter)"
    elif line.startswith("KIT-HS-007") and not _overseer_package(kit):
        note = " (connected in phase 2: the overseer port adapter)"
    row(rows, "service preflight (integration-sim)", PASS if p.returncode == 0 else BLOCKER, line[:160] + note)


def service_env(kit: Path, profile: str = "integration-sim") -> dict:
    env = _py(kit)
    env.update({"EPINOIC_PROFILE": profile, "EPINOIC_SERVICE_ENV": "sim" if profile == "integration-sim" else "development",
                "EPINOIC_SERVICE_TOKEN": secrets.token_hex(24), "EPINOIC_SIGNING_KEY": secrets.token_hex(32),
                "EPINOIC_VERDICT_KEY": secrets.token_hex(32), "EPINOIC_OVERSEER_SECRET": secrets.token_hex(32),
                "EPINOIC_TRANSLATION_PROVIDER": "fixture", "EPINOIC_FIXTURE_DIR": str(kit / "integration" / "sim" / "corpus" / "synthetic"),
                "EPINOIC_FLASH_ROUTER": os.environ.get("EPINOIC_FLASH_ROUTER", "none")})
    return env


def start_service(kit: Path, rows: list, profile: str) -> None:
    env = service_env(kit, profile)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "epinoic_logic.integration", "serve", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 60
        caps = None
        while time.monotonic() < deadline and caps is None:
            if proc.poll() is not None:
                line = (proc.stderr.read() or "").strip().splitlines()[-1:] or ["exited"]
                row(rows, "service start-up", BLOCKER, line[0][:160])
                return
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/capabilities", headers={"Authorization": f"Bearer {env['EPINOIC_SERVICE_TOKEN']}"})
                with urllib.request.urlopen(req, timeout=2) as r:  # noqa: S310 - loopback only
                    caps = json.loads(r.read())
            except OSError:
                time.sleep(0.5)
        if caps is None:
            row(rows, "service start-up", BLOCKER, "no capabilities on loopback within 60 s")
            return
        row(rows, "service start-up", PASS, f"selftest.passed={caps['selftest']['passed']} modes={caps['ports']['checks']['modes']}")
        r = caps["ports"]["router"]
        row(rows, "flash router (handshake)", REPORTED, f"required={r['required']} attached={r['attached']} identity={r.get('identity')} refusal={r.get('refusal')}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def router(kit: Path, rows: list, module: str) -> None:
    """Playbook step 7a (integration/router-port/CONFORMANCE.md items 1, 3 and 6): the router's hello, then, for every
    router-port vector's request, the router's own plan through the service's admission, run as the service runs it (in
    its own process). A plan is good only when it is ADOPTED: origin "router" and no refusal. A refused plan (out of
    contract, below the floor, a failing router) runs the floor in service, but here it is a BLOCKER, named with its
    KIT-RT code. The same request text must give the same plan text."""
    sys.path.insert(0, str(kit / "src"))
    from epinoic_logic.integration import router_port as R
    from epinoic_logic.integration.canonical import canonical_json
    att = R.attach_router(module)
    if not att.attached:
        row(rows, "flash router hello", REPORTED, f"not attached ({att.refusal}): the floor plan runs")
        return
    row(rows, "flash router hello", PASS, json.dumps(R.dump(att.hello.router)))
    refused, unstable = [], []
    paths = sorted((kit / "integration" / "vectors" / "router-port").glob("*.json"))
    for p in paths:
        req = R.check_request(json.loads(p.read_text(encoding="utf-8"))["request"])
        adm = R.route(req, att)
        if adm.origin != "router" or adm.refusal is not None:
            refused.append(f"{p.stem} {adm.refusal or 'not adopted'}")
        text = canonical_json(R.dump(req))
        try:
            first, second = att.plan_fn(text, R.PLAN_TIMEOUT_S), att.plan_fn(text, R.PLAN_TIMEOUT_S)  # type: ignore[misc]
        except R.RouterFailure as exc:
            unstable.append(f"{p.stem} {exc.code}")
            continue
        if first != second:
            unstable.append(f"{p.stem} differs")
    row(rows, "flash router plans at or above the floor", PASS if not refused else BLOCKER,
        "; ".join(refused) or f"every vector request ({len(paths)}) adopted: origin router, no refusal")
    row(rows, "flash router plans deterministic", PASS if not unstable else BLOCKER,
        "; ".join(unstable) or "the same request text gives the same plan text")


def everything(args, rows: list) -> None:
    kit = Path(args.kit)
    g1(kit, rows)
    translator(kit, rows)
    node = shutil.which("node")
    if node and args.website:
        p = subprocess.run([node, str(kit / "integration" / "readiness" / "check-website.mjs"), "--g0", args.website], capture_output=True, text=True, timeout=120)
        row(rows, "website G0 (origin/main)", PASS if "lifted" in p.stdout else BLOCKER, (p.stdout.strip().splitlines() or [p.stderr.strip()])[-1][:160])
    else:
        row(rows, "website G0 (origin/main)", NOT_RUN, "no Node.js or no --website")
    if node and args.agents:
        p = subprocess.run([node, str(kit / "integration" / "readiness" / "check-agents.mjs"), args.agents], capture_output=True, text=True, timeout=120)
        row(rows, "agents contracts", PASS if p.returncode == 0 else BLOCKER, (p.stdout.strip().splitlines() or [p.stderr.strip()])[-1][:160])
    else:
        row(rows, "agents contracts", NOT_RUN, "no Node.js or no --agents")
    if args.sim_out and (Path(args.sim_out) / "results.json").exists():
        res = json.loads((Path(args.sim_out) / "results.json").read_text(encoding="utf-8"))
        statuses = [g["status"] for g in res.get("gates", [])]
        row(rows, "simulation gates", PASS if statuses and all(s == "PASS" for s in statuses) else BLOCKER, ", ".join(f"{g['gate']}={g['status']}" for g in res.get("gates", [])))
    else:
        row(rows, "simulation gates", NOT_RUN, "no simulation output (--sim-out)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="integration readiness (read-only)")
    ap.add_argument("--g1", metavar="KIT")
    ap.add_argument("--translator", metavar="KIT")
    ap.add_argument("--start-service", action="store_true")
    ap.add_argument("--profile", default="integration-sim")
    ap.add_argument("--router", metavar="MODULE")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--kit", default=str(KIT))
    ap.add_argument("--website")
    ap.add_argument("--website-copy")
    ap.add_argument("--agents")
    ap.add_argument("--sim-out")
    ap.add_argument("--keys-dir", help="ignored: keys are ephemeral and stay in the service's environment")
    args = ap.parse_args(argv)
    rows: list = []
    if args.g1:
        g1(Path(args.g1), rows)
    if args.translator:
        translator(Path(args.translator), rows)
    if args.start_service:
        start_service(Path(args.kit), rows, args.profile)
    if args.router:
        router(Path(args.kit), rows, args.router)
    if args.all:
        everything(args, rows)
    width = max([len(r[0]) for r in rows] + [10])
    for name, status, detail in rows:
        print(f"{name:<{width}}  {status:<8}  {detail}")
    if args.all:
        local = not any(s == BLOCKER for _n, s, _d in rows) and not any(s == NOT_RUN for _n, s, _d in rows)
        print(f"Integration ready (local): {'YES' if local else 'NO'}")
        print("Live ready: NO (owner actions: W0, base P, D25 timing, D7 hosting, secrets, D14 caps, D23 models, D15 data terms)")
    return 1 if any(s == BLOCKER for _n, s, _d in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
