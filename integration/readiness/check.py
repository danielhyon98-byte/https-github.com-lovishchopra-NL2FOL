#!/usr/bin/env python3
"""Readiness of the integration (playbook steps 5, 6, 7, 7a and 14). Read-only: it never writes into a repository,
never fetches, never deploys and never calls a provider; services it starts bind 127.0.0.1 and stop before it exits.

    check.py --g1 <kit>                       gate G1: the kit commit carries every required part
    check.py --translator <kit>               generated files fresh, Z3 found, the service's preflight line
    check.py --start-service [--profile integration-sim] [--kit <kit>]
                                              start the service on loopback with ephemeral keys, read the capabilities
    check.py --router <module> [--kit <kit>]  the flash router's hello and its plans over the router-port vectors
    check.py --all --website <checkout> --website-copy <export> --agents-runtime <copy> --agents-routing <copy> \
                   --agents-harness <copy> --sim-out <dir> [--kit <kit>]
                                              (the earlier one-copy form --agents <copy> still runs, unchanged)

Every row is PASS, BLOCKER, NOT RUN (with its reason) or REPORTED (the flash router: reported, never required).
The agents copies are archive copies by role (``COMPATIBILITY.json`` ``agents_pins``; playbook step 8): the retrained
repository at the runtime pin and at the routing pin, and the harness. They make one row, "agents contracts", from
``check-agents.mjs --runtime --routing --harness`` (BLOCKER when it exits 1; its REPORTED rows are named in the
detail), and one NOT RUN row for each role whose copy is missing: "agents runtime" (the runtime pin, its contract,
``claims: null`` and the knowledge-base pin are not checked), "agents routing" (the routing pin and the routing contract
are not checked), "agents harness" (the agents path, A3 and A5 are not checked). The earlier one-copy form checks the
contracts of one copy, never the pins, so with it alone the three rows are NOT RUN too. A role that was not checked is
never part of a PASS: every NOT RUN row keeps "Integration ready (local)" at NO. The simulation adds the row
"simulation runtime copy": PASS only when the simulation's website path ran, and ran the runtime pin (``results.json``:
no ``not_run.website_path``, the website driver's own line ``subchecks.website_driver``, and ``specialist_commit`` and
``specialist_contract`` equal to the pin), else NOT RUN (the pinned runtime was not simulated).
Exit status 1 when a row is a BLOCKER. Four kinds of BLOCKER rows, each named as such:

* **kit rows** (G1, the translator section, the service start-up): on a commit where a part phase 2 connects is absent,
  a BLOCKER row that only that part causes says "(connected in phase 2: ...)"; a kit BLOCKER row without that mark is a
  defect of the commit;
* **owner gates** (the website's G0): a decision only its owner records; the row says "(owner gate: ...)". It blocks
  website work, never the rehearsal, and is never a defect of the kit;
* **website rows** (``--website-copy``, playbook steps 9 and 10): the export is not a disposable one, its base has no
  tested patch set in this kit, the patch set is not applied, or it drifted (a file the patch set writes is not as
  ``RESULT.sha256`` records: the website changed since the patch set was tested). Each is a stop of those steps, and the
  website tests of step 11 decide nothing on a patch set that is not the tested one. A rehearsal records it and goes on
  with steps 13 and 14; re-recording the patch set for a newer website is a kit change, never the session's;
* **simulation gates**: the gates of ``run_sim.py``; when every gate is NOT RUN because the service refused for a part
  phase 2 connects, the row carries that part's "(connected in phase 2: ...)" mark too.

``--website-copy`` checks the patched disposable export against the tested patch set (``RESULT.sha256``, read-only:
``exact`` is PASS, drift is a BLOCKER that names the drifted files); ``--sim-out`` reads the simulation's own output as
written there (``results.json``, which ``run_sim.py`` writes into the session's scratch directory; it is evidence of
that run, not re-derived here).
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
import tempfile
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
    combinator = kit / "combinator"
    cversion = re.search(r'^version = "([^"]+)"', (combinator / "pyproject.toml").read_text(encoding="utf-8"), re.M) if (combinator / "pyproject.toml").exists() else None
    row(rows, "combinator sub-project", REPORTED,
        f"combinator/ present (epinoic-combinator {cversion.group(1) if cversion else '?'}; connected to the service in phase 2: "
        "until then the mode combined is not offered)" if combinator.exists() else "absent: the mode combined is not offered")


def _py(kit: Path) -> dict:
    """The environment of a process run from the kit: no EPINOIC_ variable of the caller, and the kit's src/ on the
    import path, with the flash-router sub-project's src/ after it when the kit has one (so a service started with
    EPINOIC_FLASH_ROUTER=epinoic_flash_router.port can import the router in the router's own process)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("EPINOIC_")}
    paths = [kit / "src"] + ([kit / "flash-router" / "src"] if (kit / "flash-router" / "src").is_dir() else [])
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in paths)
    return env


def _phase2_note(kit: Path, line: str) -> str:
    """The "(connected in phase 2: ...)" mark of a service refusal that only an absent phase-2 part causes, else ''."""
    if line.startswith("KIT-HS-006") and not _named_policies(kit):
        return " (connected in phase 2: the named policies of contract 0.3; then KIT-HS-007 until the overseer port adapter)"
    if line.startswith("KIT-HS-007") and not _overseer_package(kit):
        return " (connected in phase 2: the overseer port adapter)"
    return ""


def _last_line(p: subprocess.CompletedProcess) -> str:
    """A generator's last line: what it printed (standard output, else standard error); "fresh" only when it succeeded
    and printed nothing."""
    lines = (p.stdout.strip() + "\n" + p.stderr.strip()).strip().splitlines()
    if lines:
        return lines[-1]
    return "fresh" if p.returncode == 0 else f"failed (exit {p.returncode}) with no output"


def translator(kit: Path, rows: list) -> None:
    for tool in ("generate.py", "vectors.py", "build_corpus.py", "manifest.py"):
        p = subprocess.run([sys.executable, str(kit / "integration" / "tools" / tool), "--check"], env=_py(kit), capture_output=True, text=True, timeout=600)
        detail = "fresh" if p.returncode == 0 and not (p.stdout.strip() or p.stderr.strip()) else _last_line(p)
        row(rows, f"generated files fresh ({tool})", PASS if p.returncode == 0 else BLOCKER, detail[:120])
    p = subprocess.run([sys.executable, "-c", "from epinoic_logic.integration.bootstrap import require_z3; require_z3(); print('z3 found')"],
                       env=_py(kit), capture_output=True, text=True, timeout=120)
    row(rows, "Z3 (bootstrap)", PASS if p.returncode == 0 else BLOCKER, (p.stdout + p.stderr).strip().splitlines()[-1][:120])
    env = service_env(kit)
    p = subprocess.run([sys.executable, "-m", "epinoic_logic.integration", "preflight"], env=env, capture_output=True, text=True, timeout=300)
    line = (p.stderr.strip().splitlines() or ["ready"])[-1] if p.returncode else "ready"
    row(rows, "service preflight (integration-sim)", PASS if p.returncode == 0 else BLOCKER, line[:160] + _phase2_note(kit, line))


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
    # The service's output goes to an unnamed temporary file, never an unread pipe (a full pipe stalls the service).
    sink = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "epinoic_logic.integration", "serve", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            stdout=sink, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 60
        caps = None
        while time.monotonic() < deadline and caps is None:
            if proc.poll() is not None:
                sink.seek(0)
                line = ((sink.read() or "").strip().splitlines()[-1:] or ["exited"])[0]
                row(rows, "service start-up", BLOCKER, line[:160] + _phase2_note(kit, line))
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
        sink.close()


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


def website_copy(kit: Path, rows: list, export: str | None) -> None:
    """The patched disposable export against the tested patch set (read-only): every file ``RESULT.sha256`` lists, as it
    is in the export. ``exact`` is the only PASS. The patch set not applied at all, and ``drift`` (a listed file missing
    or with another digest, each named), are BLOCKERs, as playbook step 10 stops on both: the patch set on the export is
    not the tested one, so the website tests of step 11 decide nothing on their own, and the row never counts toward
    "Integration ready (local)". Without an export the row is NOT RUN."""
    import hashlib
    if not export:
        row(rows, "website patch set (export)", NOT_RUN, "no --website-copy")
        return
    root = Path(export)
    if not (root / "UNREVIEWED-SIMULATION-COPY.txt").exists():
        row(rows, "website patch set (export)", BLOCKER, "not a disposable export (no UNREVIEWED-SIMULATION-COPY.txt)")
        return
    base = "P" if (root / "src" / "chat" / "pilot.js").exists() else "M"
    result = kit / "integration" / "website" / "patches" / base / "RESULT.sha256"
    if not result.exists():
        row(rows, "website patch set (export)", BLOCKER, f"website base {base} has no tested patch set in this kit")
        return
    drifted, missing = [], []
    for line in result.read_text(encoding="utf-8").splitlines():
        digest, rel = line[:64], line[66:]
        path = root / rel
        if not path.exists():
            missing.append(rel)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            drifted.append(rel)
    if missing and not (root / "src" / "verify" / "with-verification.js").exists():
        row(rows, "website patch set (export)", BLOCKER, f"base {base}: the patch set is not applied (no src/verify/)")
    elif missing or drifted:
        changed = missing + drifted
        row(rows, "website patch set (export)", BLOCKER, f"base {base}: drift in {len(changed)} file(s): " + ", ".join(changed[:6])
            + (" ..." if len(changed) > 6 else "") + " (not the tested patch set: playbook step 10 stops; re-recording the patch set "
            "for this website is a kit change)")
    else:
        row(rows, "website patch set (export)", PASS, f"base {base}: exact (every file RESULT.sha256 lists)")


def everything(args, rows: list) -> None:
    kit = Path(args.kit)
    g1(kit, rows)
    translator(kit, rows)
    node = shutil.which("node")
    if node and args.website:
        p = subprocess.run([node, str(kit / "integration" / "readiness" / "check-website.mjs"), "--g0", args.website], capture_output=True, text=True, timeout=120)
        lifted = "G0 on origin/main: lifted" in p.stdout
        detail = (p.stdout.strip().splitlines() or [p.stderr.strip()])[-1][:120]
        row(rows, "website G0 (owner gate, origin/main)", PASS if lifted else BLOCKER,
            detail + ("" if lifted else " (owner gate: only Bruno records the decision, W0; it blocks website work, not the rehearsal)"))
    else:
        row(rows, "website G0 (owner gate, origin/main)", NOT_RUN, "no Node.js or no --website")
    website_copy(kit, rows, args.website_copy)
    agents_rows(kit, rows, node, runtime=args.agents_runtime, routing=args.agents_routing, harness=args.agents_harness, one_copy=args.agents)
    simulation(kit, rows, args.sim_out)
    simulation_copies(kit, rows, args.sim_out)


#: The agents roles checked by archive copy (playbook step 8): the row each missing copy leaves NOT RUN, and what it
#: leaves unchecked.
AGENTS_ROLES = (
    ("runtime", "agents runtime", "the runtime pin, its contract, `claims: null` and the knowledge-base pin are not checked"),
    ("routing", "agents routing", "the routing pin and the routing contract are not checked"),
    ("harness", "agents harness", "the agents path, A3 and A5 are not checked"),
)


def _unchecked_roles(rows: list, copies: dict) -> None:
    """One NOT RUN row per role without a copy: a role that was not checked never counts toward a PASS."""
    for role, name, unchecked in AGENTS_ROLES:
        if not copies.get(role):
            row(rows, name, NOT_RUN, f"no --agents-{role}: {unchecked}")


def agents_rows(kit: Path, rows: list, node: str | None, *, runtime: str | None = None, routing: str | None = None,
                harness: str | None = None, one_copy: str | None = None) -> None:
    """Playbook step 14's agents rows: by role (``agents``), and the earlier one-copy form (``--agents``), which checks
    the contracts of one copy and none of the pins, so on its own it leaves every role's row NOT RUN."""
    copies = {"runtime": runtime, "routing": routing, "harness": harness}
    by_role = any(copies.values())
    if not node or not (by_role or one_copy):
        row(rows, "agents contracts", NOT_RUN, "no Node.js" if not node else "no agents copy (--agents-runtime, --agents-routing, --agents-harness, or --agents)")
        return
    if by_role:
        agents(kit, rows, node, **copies)
    if one_copy:
        p = subprocess.run([node, str(kit / "integration" / "readiness" / "check-agents.mjs"), one_copy], capture_output=True, text=True, timeout=120)
        row(rows, "agents contracts (one copy)" if by_role else "agents contracts", PASS if p.returncode == 0 else BLOCKER,
            (p.stdout.strip().splitlines() or [p.stderr.strip()])[-1][:160])
        if not by_role:
            _unchecked_roles(rows, copies)


def agents(kit: Path, rows: list, node: str, *, runtime: str | None = None, routing: str | None = None, harness: str | None = None) -> None:
    """Playbook steps 8 and 14: the agents contracts by role, as one row "agents contracts" from ``check-agents.mjs``
    (BLOCKER when it exits 1, else PASS; the rows it REPORTED are named in the detail, never hidden), and one NOT RUN row
    for each role whose copy is not given ("agents runtime", "agents routing", "agents harness"): check-agents checks only
    the roles it is given, so its PASS says nothing of the others, and a NOT RUN row keeps readiness at NO."""
    argv = [node, str(kit / "integration" / "readiness" / "check-agents.mjs")]
    for flag, copy in (("--runtime", runtime), ("--routing", routing), ("--harness", harness)):
        if copy:
            argv += [flag, copy]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    lines = p.stdout.strip().splitlines()
    reported = [line[len("REPORTED"):].strip().split(":", 1)[0] for line in lines if line.startswith("REPORTED")]
    detail = (lines or [p.stderr.strip()])[-1][:160] + (f" ({len(reported)} REPORTED: {', '.join(reported)})" if reported else "")
    row(rows, "agents contracts", PASS if p.returncode == 0 else BLOCKER, detail)
    _unchecked_roles(rows, {"runtime": runtime, "routing": routing, "harness": harness})


def simulation(kit: Path, rows: list, sim_out: str | None) -> None:
    """Playbook step 14's simulation row, read from the simulation's own output (``<sim-out>/results.json``): PASS only
    when all eight gates PASS; a run with a test double of the overseer port is never evidence."""
    if sim_out and (Path(sim_out) / "results.json").exists():
        res = json.loads((Path(sim_out) / "results.json").read_text(encoding="utf-8"))
        statuses = [g["status"] for g in res.get("gates", [])]
        detail = ", ".join(f"{g['gate']}={g['status']}" for g in res.get("gates", []))
        refused = str((res.get("service") or {}).get("preflight") or "")
        if res.get("test_double"):
            # a wiring run with a test double of the overseer port is never the simulation's result (sim/README.md)
            row(rows, "simulation gates", BLOCKER, f"the simulation ran with a test double of the overseer port ({res['test_double']}): "
                "a wiring check, not evidence; run it without --test-overseer-port")
        else:
            if statuses and all(s == NOT_RUN for s in statuses):
                detail += _phase2_note(kit, refused)
            row(rows, "simulation gates", PASS if statuses and all(s == "PASS" for s in statuses) else BLOCKER, detail)
    else:
        row(rows, "simulation gates", NOT_RUN, "no simulation output (--sim-out)")


def simulation_copies(kit: Path, rows: list, sim_out: str | None) -> None:
    """Playbook step 14: the runtime copy the simulation's website path ran, read from its own output (``results.json``).
    ``specialist_commit`` and ``specialist_contract`` name the copy ``run_sim.py`` gave the website path (its
    ``.kit-archive-commit`` and ``RUNTIME_CONTRACT_VERSION``), whether or not that path then ran. The path ran only when the
    output records no ``not_run.website_path`` and holds the website driver's own line (``subchecks.website_driver``,
    written only when the driver finished). The simulation is evidence for the runtime pin (``COMPATIBILITY.json``
    ``agents_pins.runtime``) only when its website path ran that pin: PASS then. NOT RUN when the website path did not run
    (the service refused to start, or the driver stopped: the reason the output gives), when it ran another copy (the
    harness, without ``--specialist``, or another commit or contract) or when the output does not name the copy (a run of
    an earlier ``run_sim.py``), so readiness stays NO. The agents path's copy (the harness) is named in the detail, with
    its own not-run reason. No row without a simulation output: the gates row is NOT RUN then."""
    results = Path(sim_out) / "results.json" if sim_out else None
    if results is None or not results.exists():
        return
    res = json.loads(results.read_text(encoding="utf-8"))
    pin = json.loads((kit / "integration" / "COMPATIBILITY.json").read_text(encoding="utf-8"))["agents_pins"]["runtime"]
    name = "simulation runtime copy"
    if "specialist_commit" not in res:
        row(rows, name, NOT_RUN, "the simulation output does not name the runtime copy its website path ran (an earlier run_sim.py): "
            "the runtime pin was not simulated")
        return
    commit, contract = res.get("specialist_commit"), res.get("specialist_contract")
    not_run = res.get("not_run") or {}
    driver = (res.get("subchecks") or {}).get("website_driver")
    given = f"{res.get('specialist_copy') or 'no runtime copy'} {commit or '(no .kit-archive-commit)'} ({contract})"
    agents = f"; agents path: {res.get('agents_commit') or 'no harness copy'} ({res.get('agents_contract')})" + (
        f", not run: {not_run['agents_path']}" if not_run.get("agents_path") else "")
    if not_run.get("website_path") or not driver:
        reason = not_run.get("website_path") or "the output holds no website driver line (subchecks.website_driver)"
        row(rows, name, NOT_RUN, f"the website path did not run ({reason}): the runtime pin was not simulated (the copy given: {given}){agents}")
    elif commit == pin["commit"] and contract == pin["contract"]:
        row(rows, name, PASS, f"website path ran the runtime pin {commit} ({contract}, {res.get('specialist_copy')}; {driver}){agents}")
    else:
        row(rows, name, NOT_RUN, f"the website path ran {given}, not the runtime pin {pin['commit']} ({pin['contract']}): "
            f"the pinned runtime was not simulated{agents}")


def local_ready(rows: list) -> bool:
    """"Integration ready (local)": no BLOCKER and no NOT RUN row (REPORTED rows are recorded, never a stop)."""
    return not any(s in (BLOCKER, NOT_RUN) for _n, s, _d in rows)


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
    ap.add_argument("--agents", help="one agents copy (the earlier form; check-agents.mjs <copy>)")
    ap.add_argument("--agents-runtime", help="an archive copy of the retrained repository at the runtime pin")
    ap.add_argument("--agents-routing", help="an archive copy of the retrained repository at the routing pin")
    ap.add_argument("--agents-harness", help="an archive copy of the harness (the agents path, A3 and A5)")
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
        print(f"Integration ready (local): {'YES' if local_ready(rows) else 'NO'}")
        print("Live ready: NO (owner actions: W0, base P, D25 timing, D7 hosting, secrets, D14 caps, D23 models, D15 data terms)")
    return 1 if any(s == BLOCKER for _n, s, _d in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
