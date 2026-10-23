#!/usr/bin/env python3
"""The local end-to-end simulation of the integration kit (PROTOCOL.md section 14.5; playbook step 12).

    python integration/sim/run_sim.py --website <export> --specialist <runtime copy> --agents <harness copy> \
        --translator <kit> --corpus <kit>/integration/sim/corpus --out <dir> [--rounds <dir>]

Two copies (README.md, "The two copies"): ``--specialist`` is the runtime the website path runs (an archive copy of the
retrained repository at ``COMPATIBILITY.json`` ``agents_pins.runtime``); ``--agents`` is the harness the agents path
runs (an archive copy of ``repositories.agents_harness``: its runtime and its router in one tree). Without
``--specialist`` the website path runs the ``--agents`` copy, as before. Each driver replies to its runtime in the shape
that copy's own contract takes (``runtime-reply.mjs``).

Order: copy the corpus (the kit and any supplied rounds are never written to) -> the fault cases, built by the arena's
own functions on the reference copy, indexed to their items' fixtures in a round only the service loads (faults.py)
-> preflight the service in the ``integration-sim`` profile with ephemeral keys -> start it on loopback with the fixture
provider and the evidence tap -> the website driver (users.json and the website-path fault cases through the disposable
export) -> the agents driver (STEM, duplicate, combined, clarify and the STEM fault cases) -> the reference harnesses on
another copy (reference.py) -> the tampering cases at the adapter (tamper_web.py, a sub-check) -> the gates (gates.py).
Writes ``<out>/summary.md`` (one line per gate: PASS, FAIL or NOT RUN with its reason) and ``<out>/results.json``
(denominators, case ids, sub-checks, what was not run and why, and the copy each path was given: ``specialist_copy``,
``specialist_commit``, ``specialist_contract``, ``agents_copy``, ``agents_commit``, ``agents_contract``; the summary's
"Copies" lines say the same, and a path that did not run says so there and in ``not_run``: a copy given to a path that
did not run was not simulated). Exit 0 only when no gate FAILs and all eight gates PASS; every part that is missing makes
its gates NOT RUN with the reason that part gave, never PASS.

``--test-overseer-port MODULE --test-pythonpath DIRS`` (TEST ONLY: tests/integration/sim_double/) starts the service
with a test double of the overseer port so the drivers and the gates can be exercised before the overseer's adapter
exists. A double audits nothing: with it every gate is reported NOT RUN ("the overseer port is a test double"), the
statuses the gates computed are kept only as the sub-check ``gates_with_test_double``, and the exit status is 1.

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
from typing import Any, Optional

SIM = Path(__file__).resolve().parent
#: The simulation service's per-token rate (EPINOIC_RATE_PER_MINUTE; the service's default is 60).
SIM_RATE_PER_MINUTE = "6000"
#: Website-path actions whose answer is the item's own recorded answer (G-EQ-ARENA compares their evidence).
#: Only single-mode calls: a duplicate or combined call delivers two answers on one channel, which the arena never does.
GENUINE_ACTIONS = ("send", "follow_up", "retry", "concurrent", "clock_past_cache", "service_stopped:retry", "stem")


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"kit_sim_{name}", SIM / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def service_env(translator: Path, corpus_copy: Path, evidence: Path, *, test_port: Optional[str] = None, test_path: Optional[str] = None) -> dict:
    """Ephemeral keys (in the service's environment only; the drivers get the service token through <out>/work/token,
    mode 0600, inside the simulation's own output directory), the sim profile, the fixture provider fed from the copy.
    ``test_port``/``test_path`` attach a TEST DOUBLE of the overseer port (module docstring)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("EPINOIC_")}
    paths = [str(translator / "src")] + ([p for p in (test_path or "").split(os.pathsep) if p] if test_port else [])
    env.update({
        "PYTHONPATH": os.pathsep.join(paths), "EPINOIC_PROFILE": "integration-sim", "EPINOIC_SERVICE_ENV": "sim",
        "EPINOIC_SERVICE_TOKEN": secrets.token_hex(24), "EPINOIC_SIGNING_KEY": secrets.token_hex(32), "EPINOIC_VERDICT_KEY": secrets.token_hex(32),
        "EPINOIC_OVERSEER_SECRET": secrets.token_hex(32), "EPINOIC_TRANSLATION_PROVIDER": "fixture", "EPINOIC_FIXTURE_DIR": str(corpus_copy),
        "EPINOIC_SIM_EVIDENCE_DIR": str(evidence), "EPINOIC_FLASH_ROUTER": os.environ.get("EPINOIC_FLASH_ROUTER", "none"),
        # One token replays every simulated user back to back (two requests per turn): the per-token rate is raised for
        # the simulation only, so the replay measures the path and not the default 60 per minute.
        "EPINOIC_RATE_PER_MINUTE": SIM_RATE_PER_MINUTE,
    })
    if test_port:
        env["EPINOIC_OVERSEER_PORT"] = test_port
    return env


def preflight(translator: Path, env: dict) -> tuple[bool, str]:
    proc = subprocess.run([sys.executable, "-m", "epinoic_logic.integration", "preflight"], env=env, capture_output=True, text=True, timeout=300)
    line = (proc.stderr.strip().splitlines() or [""])[-1] if proc.returncode else "ready"
    return proc.returncode == 0, line


def start_service(env: dict, port: int, log: Path):
    """Start the service on loopback; its output goes to ``log`` (a file, never an unread pipe: a full pipe would stall
    the service once its access log fills the pipe's buffer)."""
    log.parent.mkdir(parents=True, exist_ok=True)
    sink = log.open("w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "epinoic_logic.integration", "serve", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            stdout=sink, stderr=subprocess.STDOUT, text=True)
    sink.close()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return None, (log.read_text(encoding="utf-8").strip().splitlines() or ["the service exited"])[-1]
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/capabilities", headers={"Authorization": f"Bearer {env['EPINOIC_SERVICE_TOKEN']}"})
            with urllib.request.urlopen(req, timeout=2) as r:  # noqa: S310 - loopback only
                if r.status == 200:
                    return proc, json.loads(r.read())
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    return None, "the service did not answer on loopback within 60 s"


def _driver(node: str, script: str, argv: list[str], timeout: int = 3600) -> tuple[bool, str]:
    d = subprocess.run([node, str(SIM / script), *argv], capture_output=True, text=True, timeout=timeout)
    if d.returncode == 0:
        return True, (d.stdout.strip().splitlines() or [""])[-1]
    return False, (d.stderr.strip().splitlines() or [f"the {script} driver failed (exit {d.returncode})"])[-1]


def _evidence(evidence_dir: Path, request_id: Optional[str]) -> Optional[dict]:
    if not request_id:
        return None
    p = evidence_dir / f"{request_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _response_receipt(ev: dict, answer_index: int = 0) -> Optional[dict]:
    responses = [r for r in ev.get("receipts") or [] if isinstance(r, dict) and r.get("direction") == "specialist_to_router"]
    return responses[answer_index] if len(responses) > answer_index else None


def _receipt_codes(receipt: Optional[dict]) -> list[str]:
    if not receipt:
        return []
    return sorted({str(f.get("code")) for f in (receipt.get("findings") or []) + (receipt.get("structural_findings") or []) if isinstance(f, dict)})


def collect(website: Optional[dict], agents: Optional[dict], evidence_dir: Path, rounds: list[Path], reference: dict, compare: Any) -> dict:
    """The gates' material from the drivers' records and the evidence tap (pure reading; nothing is decided here)."""
    fixture_ids: dict[str, list[str]] = {}
    for r in rounds:
        for tp in (r / "translations").glob("*.json"):
            fixture_ids[f"{r.name}/{tp.stem}"] = sorted(json.loads(tp.read_text(encoding="utf-8"))["claims"])
    round_name = rounds[0].name if rounds else ""
    projections: dict[str, list] = {}
    calls: list[tuple[str, str, dict]] = []  # (item key, path, record)
    for t in (website or {}).get("turns", []):
        if t.get("action") in GENUINE_ACTIONS and t.get("stored") and t["stored"].get("attempt_id"):
            calls.append((f"{round_name}/{t['item']}", "website", {"request_id": t["stored"]["attempt_id"], **t}))
    for t in (agents or {}).get("turns", []):
        if t.get("action") in GENUINE_ACTIONS and t.get("request_id") and len(t.get("items") or []) >= 1:
            calls.append((f"{round_name}/{t['items'][0]}", "agents", t))
    for key, _path, t in calls:
        ev = _evidence(evidence_dir, t.get("request_id"))
        rc = _response_receipt(ev) if ev else None
        if rc is not None:
            projections.setdefault(key, []).append(compare.receipt_projection(rc, fixture_ids=fixture_ids.get(key)))
    # G-FAULT: each fault case beside the arena's own classification of the same mutation.
    by_case = {f"{m['item']}:{m['kind']}": m for m in reference.get("mutations", [])}
    fault_records = []
    for f in list((website or {}).get("faults", [])) + list((agents or {}).get("faults", [])):
        m = by_case.get(f["case"])
        if m is None:
            continue
        ev = None
        for t in (website or {}).get("turns", []) + (agents or {}).get("turns", []):
            if t.get("fault_case") == f["case"]:
                ev = _evidence(evidence_dir, (t.get("stored") or {}).get("attempt_id") or t.get("request_id"))
        rc = _response_receipt(ev) if ev else None
        codes = _receipt_codes(rc)
        caught = bool(m.get("named_by"))
        fault_records.append({"case": f["case"], "caught_by_arena": caught, "arena_codes": sorted(set(m.get("named_by") or [])),
                              "website_refused": bool(f.get("website_refused")), "website_codes": codes,
                              "website_labelled_checked": bool(f.get("website_labelled_checked")),
                              "same_behaviour": (rc or {}).get("status") == m.get("status") and set(codes) == set(m.get("codes") or [])})
    # G-DEL: the verdicts, and the kit-derived decision on the reference record beside a genuine call of the same item.
    verdicts = list((website or {}).get("verdicts", [])) + list((agents or {}).get("verdicts", []))
    by_request = {v.get("ids", {}).get("request_id"): v for v in verdicts}
    rederived = []
    for key, path, t in calls:
        v = by_request.get(t.get("request_id"))
        ref = reference.get("decisions", {}).get(key)
        if v is None or ref is None or t.get("mode", "single") != "single":
            continue
        rederived.append({"item": key, "path": path, "decision": ref["decision"], "website_decision": v.get("delivery", {}).get("decision"),
                          "overseer_allowed": v.get("overseer", {}).get("delivery_allowed"), "kit_derived": True})
    displays = list((website or {}).get("displays", []))
    invariants = dict((website or {}).get("invariants", {}))
    tamper = dict((website or {}).get("tamper", {}))
    return {"projections": projections, "faults": fault_records, "verdicts": verdicts, "rederived": rederived, "displays": displays,
            "invariants": invariants, "tamper": tamper}


def with_test_double(gate_results: list, module: str, subchecks: dict, gates: Any) -> list:
    """Under a TEST DOUBLE of the overseer port every gate is NOT RUN (a double audits nothing): what each gate computed is
    kept only as the sub-checks ``gates_with_test_double`` and ``gate_cases_with_test_double`` (the cases of a gate that
    computed FAIL), never as a gate status."""
    subchecks["gates_with_test_double"] = [{k: g[k] for k in ("gate", "status", "reason", "denominator")} for g in gate_results]
    subchecks["gate_cases_with_test_double"] = {g["gate"]: g["cases"][:40] for g in gate_results if g["status"] == gates.FAIL}
    return [gates.not_run(g["gate"], f"the overseer port is a test double ({module}): wiring check only, computed {g['status']}") for g in gate_results]


#: The files whose wiring the record names (integration/sim/TESTED.json): a change to any of them needs a new wiring run.
WIRING_FILES = ("integration/sim/run_sim.py", "integration/sim/gates.py", "integration/sim/compare.py", "integration/sim/faults.py",
                "integration/sim/reference.py", "integration/sim/website-driver.mjs", "integration/sim/agents-driver.mjs",
                "integration/sim/runtime-reply.mjs", "integration/sim/users.json", "integration/sim/corpus/MANIFEST.sha256",
                "tests/integration/sim_double/kit_overseer_test_double.py")


def _archive_commit(copy: Optional[str]) -> Optional[str]:
    marker = Path(copy) / ".kit-archive-commit" if copy else None
    return marker.read_text(encoding="utf-8").strip() if marker and marker.exists() else None


def _runtime_contract(copy: Optional[str]) -> Optional[str]:
    import re
    constants = Path(copy) / "specialist-runtime" / "src" / "constants.js" if copy else None
    m = re.search(r'RUNTIME_CONTRACT_VERSION\s*=\s*"([^"]+)"', constants.read_text(encoding="utf-8")) if constants and constants.exists() else None
    return m.group(1) if m else None


def copies(specialist: Optional[str], agents: Optional[str]) -> dict:
    """The archive copy each path is given, for ``results.json`` and ``summary.md`` of every run: the website path's
    runtime (``--specialist``, else ``--agents``) and the agents path's harness (``--agents``), each by its
    ``.kit-archive-commit`` and its ``RUNTIME_CONTRACT_VERSION`` (None when absent). They are recorded before the service
    starts, so they say which copy a path was given, not that it ran (``not_run`` says which path did not). The readiness
    check compares ``specialist_commit`` and ``specialist_contract`` with ``COMPATIBILITY.json`` ``agents_pins.runtime``
    only when the website path ran (check.py, "simulation runtime copy")."""
    website_copy = specialist or agents
    return {"specialist_copy": "--specialist" if specialist else ("--agents" if agents else None),
            "specialist_commit": _archive_commit(website_copy), "specialist_contract": _runtime_contract(website_copy),
            "agents_copy": "--agents" if agents else None,
            "agents_commit": _archive_commit(agents), "agents_contract": _runtime_contract(agents)}


def copy_lines(results: dict) -> list[str]:
    """The summary's lines naming the copy each path was given (``copies``), each followed by its own not-run reason when
    that path did not run (``results["not_run"]``): a copy given to a path that did not run was not simulated."""
    not_run = results.get("not_run") or {}

    def one(flag, commit, contract, path) -> str:
        given = f"{flag} {commit or '(no .kit-archive-commit)'} ({contract or 'no RUNTIME_CONTRACT_VERSION'})" if flag else "no copy"
        return given + (f", not run: {not_run[path]}" if not_run.get(path) else "")
    return ["", "Copies (the archive copy each path was given: its .kit-archive-commit and RUNTIME_CONTRACT_VERSION):",
            f"- website path: {one(results.get('specialist_copy'), results.get('specialist_commit'), results.get('specialist_contract'), 'website_path')}",
            f"- agents path: {one(results.get('agents_copy'), results.get('agents_commit'), results.get('agents_contract'), 'agents_path')}"]


def wiring_record(results: dict, translator: Path, website: Optional[str], agents: Optional[str], specialist: Optional[str] = None) -> dict:
    """The record of one wiring run with the test double (``--record-wiring``): the digests of the files it ran, the
    website export's provenance line, the commits of the two copies (the website path's runtime, ``--specialist`` or
    else ``--agents``, with its contract; the agents path's harness), what every gate computed, and the counts. It is
    evidence about the drivers and the gates' wiring only: no gate is PASS under a double."""
    import hashlib
    marker = Path(website) / "UNREVIEWED-SIMULATION-COPY.txt" if website else None
    runtime_copy = specialist or agents
    return {
        "schema": "epinoic.integration.sim-wiring-record.v1",
        "note": "A wiring run of integration/sim/run_sim.py with the TEST DOUBLE of the overseer port (tests/integration/sim_double/): "
                "every gate is reported NOT RUN; 'computed' is what each gate computed, information only.",
        "files": {f: hashlib.sha256((translator / f).read_bytes()).hexdigest() for f in WIRING_FILES},
        "website_export": marker.read_text(encoding="utf-8").splitlines()[0] if marker and marker.exists() else None,
        "agents_commit": _archive_commit(agents),
        "specialist_commit": _archive_commit(runtime_copy),
        "specialist_contract": _runtime_contract(runtime_copy),
        "computed": results["subchecks"].get("gates_with_test_double"),
        "computed_fail_cases": results["subchecks"].get("gate_cases_with_test_double"),
        "fault_cases": results["subchecks"].get("fault_cases"),
        "drivers": {k: results["subchecks"].get(k) for k in ("website_driver", "agents_driver")},
        "not_run": results["not_run"],
    }


def run(args) -> int:
    gates = _module("gates")
    compare = _module("compare")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    translator = Path(args.translator).resolve()
    corpus_root = Path(args.corpus).resolve()
    rounds = [p for p in sorted((corpus_root / "synthetic").iterdir()) if (p / "specialists").is_dir()]
    if args.rounds:
        rounds += [p for p in sorted(Path(args.rounds).iterdir()) if (p / "specialists").is_dir()]
    test_double = args.test_overseer_port or None
    results: dict = {"rounds": [r.name for r in rounds], "not_run": {}, "subchecks": {}, "test_double": test_double,
                     **copies(args.specialist, args.agents)}
    work = out / "work"
    if work.exists():
        shutil.rmtree(work)
    service_copy, reference_copy = work / "service-corpus", work / "reference-corpus"
    for r in rounds:
        shutil.copytree(r, service_copy / r.name)
        shutil.copytree(r, reference_copy / r.name)

    # 0. The fault cases, by the arena's own functions on the reference copy, indexed for the service only.
    faults = _module("faults")
    cases = []
    for r in rounds:
        cases += [dict(c, round=r.name) for c in faults.fault_cases(translator, reference_copy / r.name)]
    fault_round = faults.write_fault_round(cases, {r.name: reference_copy / r.name for r in rounds}, service_copy)
    (work / "faults.json").write_text(json.dumps([c for c in cases if c["case"] in set(fault_round["written"])], ensure_ascii=False), encoding="utf-8")
    results["subchecks"]["fault_cases"] = {"built": len(cases), "indexed": len(fault_round["written"]), "skipped": fault_round["skipped"]}

    # 1. The service: preflight, then serve on loopback.
    env = service_env(translator, service_copy, work / "evidence", test_port=test_double, test_path=args.test_pythonpath)
    ready, line = preflight(translator, env)
    results["service"] = {"preflight": line}
    proc = None
    port = _free_port()
    if ready:
        proc, caps = start_service(env, port, work / "service.log")
        results["service"]["started"] = proc is not None
        if proc is None:
            results["not_run"]["service"] = f"the service did not start: {caps}"
        else:
            results["service"]["overseer"] = caps.get("ports", {}).get("overseer")
    else:
        results["not_run"]["service"] = f"the service refused to start: {line}"

    website = agents = None
    try:
        # 2. The website path and 3. the agents path.
        node = shutil.which("node")
        token_file = work / "token"
        common = ["--service", f"http://127.0.0.1:{port}", "--token-file", str(token_file), "--users", str(SIM / "users.json"),
                  "--corpus", str(service_copy), "--round", rounds[0].name if rounds else "", "--faults", str(work / "faults.json")]
        if proc is not None and node:
            token_file.write_text(env["EPINOIC_SERVICE_TOKEN"])
            os.chmod(token_file, 0o600)
        if proc is None or not node:
            reason = results["not_run"].get("service") or "no Node.js"
            results["not_run"]["website_path"] = reason
            results["not_run"]["agents_path"] = reason
        else:
            specialist = args.specialist or args.agents  # the website path's runtime copy
            if args.website and specialist:
                ok, msg = _driver(node, "website-driver.mjs", ["--website", args.website, "--agents", specialist, "--out", str(work / "website"),
                                                               "--vectors", str(translator / "integration" / "vectors"), *common])
                if ok:
                    website = json.loads((work / "website" / "website-driver.json").read_text(encoding="utf-8"))
                    results["subchecks"]["website_driver"] = msg
                else:
                    results["not_run"]["website_path"] = msg
            else:
                results["not_run"]["website_path"] = "no website export (--website)" if not args.website else "no runtime copy (--specialist or --agents)"
            if args.agents:
                ok, msg = _driver(node, "agents-driver.mjs", ["--agents", args.agents, "--out", str(work / "agents"), *common])
                if ok:
                    agents = json.loads((work / "agents" / "agents-driver.json").read_text(encoding="utf-8"))
                    results["subchecks"]["agents_driver"] = msg
                else:
                    results["not_run"]["agents_path"] = msg
            else:
                results["not_run"]["agents_path"] = "no agents copy (--agents)"

        # 4. The reference harnesses on another copy of exactly the same items.
        reference_mod = _module("reference")
        ref_by_item, ref_mutations, ref_decisions = {}, [], {}
        for r in rounds:
            rr = reference_mod.run_reference(translator, reference_copy / r.name)
            ref_by_item.update({f"{r.name}/{k}": v for k, v in rr["projections"].items()})
            ref_decisions.update({f"{r.name}/{k}": v for k, v in rr["decisions"].items()})
            ref_mutations += rr["mutations"]
            results["subchecks"][f"arena:{r.name}"] = {"functional": rr["functional"], "qualified": rr["qualified"], "genuine": rr["genuine"]}
        contained = reference_mod.contained_available(translator)
        if contained is None:
            results["not_run"]["contained"] = "scripts/overseer/run_contained.py is not on this tree"

        # 5. The tampering cases at the adapter (a sub-check: evidence about one module, never the gate).
        results["subchecks"]["tamper_adapter"] = _module("tamper_web").adapter_results(translator)

        # 6. The gates, each NOT RUN with the reason its missing part gave.
        material = collect(website, agents, work / "evidence", [service_copy / r.name for r in rounds],
                           {"mutations": ref_mutations, "decisions": ref_decisions}, compare)
        web_reason = results["not_run"].get("website_path")
        agents_reason = results["not_run"].get("agents_path")
        unrun = {}
        for key in ref_by_item:
            item = key.split("/", 1)[1]
            on_agents = item.startswith("ph-")
            if on_agents and agents_reason:
                unrun[key] = f"the agents path was not run: {agents_reason}"
            elif not on_agents and web_reason:
                unrun[key] = f"the website path was not run: {web_reason}"
        any_path = website is not None or agents is not None
        gate_results = [
            gates.g_eq_arena(material["projections"], ref_by_item, compare.differences, unrun) if any_path
            else gates.not_run("G-EQ-ARENA", f"no website-path or agents-path evidence: {web_reason}"),
            gates.g_eq_contained(None) if contained is None else gates.not_run("G-EQ-CONTAINED", "the contained comparison is connected with the rebuilt overseer"),
            gates.g_fault(material["faults"]) if any_path else gates.not_run("G-FAULT", f"no mutation was sent through the website path: {web_reason}"),
            gates.g_inv(material["invariants"]) if website is not None else gates.not_run("G-INV", f"no website-path turn was run: {web_reason}"),
            gates.g_hon(material["displays"]) if website is not None else gates.not_run("G-HON", f"no delivered answer was displayed: {web_reason}"),
            gates.g_del(material["verdicts"], material["rederived"]) if any_path else gates.not_run("G-DEL", f"no checks call returned a verdict: {web_reason}"),
            gates.g_tamper(material["tamper"]) if website is not None else gates.not_run("G-TAMPER", f"the website path was not run: {web_reason}"),
            gates.g_ovs(None),
        ]
        if test_double:
            gate_results = with_test_double(gate_results, test_double, results["subchecks"], gates)
        results["gates"] = gate_results
        results["reference_items"] = sorted(ref_by_item)
        results["reference_mutations"] = len(ref_mutations)
        results["website_records"] = {k: (website or {}).get(k) for k in ("invariants", "tamper", "not_run")} if website else None
        results["agents_records"] = {"turns": [{k: t.get(k) for k in ("user", "action", "items", "mode", "port", "status", "decision", "reasons", "code", "calls")}
                                               for t in agents.get("turns", [])], "not_run": agents.get("not_run")} if agents else None
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    lines = gates.summary_lines(results["gates"])
    lines += copy_lines(results)
    lines += ["", "Not run, and why:"] + [f"- {k}: {v}" for k, v in sorted(results["not_run"].items())]
    lines += ["", "Sub-checks (information, never a gate):"] + [f"- {k}: {json.dumps(v)}" for k, v in sorted(results["subchecks"].items())]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "results.json").write_text(json.dumps(results, indent=1, default=str) + "\n", encoding="utf-8")
    if args.record_wiring:
        if not test_double:
            print("--record-wiring records a wiring run with the test double only (--test-overseer-port)", file=sys.stderr)
            return 2
        Path(args.record_wiring).write_text(json.dumps(wiring_record(results, translator, args.website, args.agents, args.specialist), indent=1,
                                                       sort_keys=True) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return gates.exit_status(results["gates"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the integration kit's local simulation")
    ap.add_argument("--website", default=None)
    ap.add_argument("--agents", default=None, help="the harness copy: the agents path (and the website path without --specialist)")
    ap.add_argument("--specialist", default=None, help="the runtime copy the website path runs (the retrained repository at the runtime pin)")
    ap.add_argument("--translator", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", default=None, help="recorded rounds Daniel supplies and approves (D15); copied first, never written")
    ap.add_argument("--test-overseer-port", default=None, help="TEST ONLY: a test double of the overseer port; every gate is then NOT RUN")
    ap.add_argument("--test-pythonpath", default=None, help="TEST ONLY: where the test double is importable from")
    ap.add_argument("--record-wiring", default=None, help="with the test double: write the wiring record (integration/sim/TESTED.json)")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
