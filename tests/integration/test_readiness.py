"""The readiness scripts (playbook steps 1, 4, 5, 7a, 8 and 14), on fixture repositories made in a temporary directory:
G0 read from origin/main only (in force, lifted, inconsistent), the website base, gate G1 on this tree (the parts
phase 2 connects are BLOCKERs, the flash router is REPORTED, never required), the flash router's plans over the
router-port vectors, the agents contracts, and the locator's TOP/SKIP rule."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.helpers import write_router_module

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "integration" / "readiness"
NODE = shutil.which("node")
GIT = shutil.which("git")


def _git(repo: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "kit-test", "GIT_AUTHOR_EMAIL": "kit-test@example.invalid", "GIT_COMMITTER_NAME": "kit-test",
           "GIT_COMMITTER_EMAIL": "kit-test@example.invalid"}
    subprocess.run([GIT, "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _website(tmp_path: Path, files: dict) -> Path:
    repo = tmp_path / "website"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for name, text in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


IN_FORCE = {
    "docs/current-state.md": "Status. Z3 remains deferred.\n",
    "docs/architecture.md": "The Z3 logic translator is **deferred**.\n",
    "docs/handoff/05-integration-planning-brief.md": "Website Z3 integration stays deferred.\n",
    "docs/handoff/04-logic-translator.md": "> Deferred by Bruno on 12 October.\n\nbody\n",
}
LIFTED = {
    "docs/current-state.md": "Status. Integration follows epinoic.integration.v1.\n",
    "docs/architecture.md": "The verified backend.\n",
    "docs/handoff/05-integration-planning-brief.md": "Every released answer requires the checks port.\n",
    "docs/handoff/04-logic-translator.md": "> Superseded by protocol epinoic.integration.v1.\n",
}


@pytest.mark.skipif(NODE is None or GIT is None, reason="needs Node.js and git to build the fixture repository")
@pytest.mark.parametrize("files,state", [(IN_FORCE, "in force"), (LIFTED, "lifted"),
                                         ({k: v for k, v in IN_FORCE.items() if "architecture" not in k}, "inconsistent")])
def test_g0_is_read_from_origin_main_only(tmp_path, files, state):
    repo = _website(tmp_path, files)
    # the working tree says something else: G0 must not read it
    (repo / "docs" / "current-state.md").write_text("Integration follows epinoic.integration.v1.\n", encoding="utf-8")
    out = subprocess.run([NODE, str(READINESS / "check-website.mjs"), "--g0", str(repo)], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip().splitlines()[-1] == f"G0 on origin/main: {state}", out.stdout + out.stderr


@pytest.mark.skipif(NODE is None or GIT is None, reason="needs Node.js and git to build the fixture repository")
def test_the_website_base_is_m_without_the_pilot_and_p_with_it(tmp_path):
    repo = _website(tmp_path, dict(IN_FORCE))
    run = lambda: subprocess.run([NODE, str(READINESS / "check-website.mjs"), "--base", str(repo)], capture_output=True, text=True, timeout=60).stdout.strip()  # noqa: E731
    assert run() == "M"
    (repo / "src" / "chat").mkdir(parents=True)
    (repo / "src" / "chat" / "pilot.js").write_text("export {};\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "pilot")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert run() == "P"


def _named_policies_merged() -> bool:
    """Contract 0.3's named policies are on this tree. The pre-build branch merged them with the end-to-end fixes on
    17 October 2026; a pre-build commit before that merge has none (and its contract line is older than 0.4)."""
    from epinoic_logic.engine import policies
    return getattr(policies, "NAMED_POLICIES", None) is not None and callable(getattr(policies, "named_policy", None))


def _overseer_merged() -> bool:
    """The overseer package is on this tree (the second translator merge joined the overseer build, OVERSEER_DESIGN
    section 44); its embedded port adapter (``epinoic_overseer.port``) is still connected in phase 2."""
    return (ROOT / "src" / "epinoic_logic" / "overseer" / "__init__.py").exists()


def test_g1_on_this_tree_names_the_parts_phase_2_connects_and_reports_the_router():
    out = subprocess.run([sys.executable, str(READINESS / "check.py"), "--g1", str(ROOT)], capture_output=True, text=True, timeout=120)
    rows = {line.split("  ")[0].strip(): line for line in out.stdout.splitlines()}
    if _overseer_merged():  # the overseer merged (with contract 0.3 before it): every G1 row passes, so G1 does too
        assert out.returncode == 0 and "PASS" in rows["G1 overseer package"] and not [x for x in rows.values() if "  BLOCKER  " in x], out.stdout
    else:
        assert out.returncode == 1
        assert "BLOCKER" in rows["G1 overseer package"]
    if _named_policies_merged():  # contract 0.3 merged: its row passes, and the contract line moved on with it (0.5 since the argument diagnosis)
        assert "PASS" in rows["G1 named policies (contract 0.3)"] and "PASS" in rows["G1 contract 0.5"], out.stdout
    else:
        assert "BLOCKER" in rows["G1 named policies (contract 0.3)"]
    assert "PASS" in rows["G1 STEM branches"] and "PASS" in rows["G1 protocol"]
    assert "REPORTED" in rows["flash router sub-project"] and "never required" in rows["flash router sub-project"]
    assert "REPORTED" in rows["combinator sub-project"] and "epinoic-combinator" in rows["combinator sub-project"] and "combined" in rows["combinator sub-project"]


def test_on_this_tree_every_blocker_of_g1_and_of_the_translator_section_names_its_phase_2_connection():
    """A fresh session tells an expected pre-build stop from a defect by the row itself: on this pre-build tree every
    BLOCKER row of G1 (the contract line included) and the preflight row of the translator section say "(connected in
    phase 2: ...)". Before the contract 0.3 merge there are three (contract line, overseer package, named policies) and
    the preflight row names KIT-HS-006; after it (this branch since 17 October 2026) the overseer package is the only
    one, and the preflight row names KIT-HS-007 (the overseer port adapter). After the second translator merge (the
    overseer package on this tree) G1 has no BLOCKER, and the preflight row still names KIT-HS-007 with its mark: only
    the overseer port adapter, which phase 2 connects, causes it."""
    out = subprocess.run([sys.executable, str(READINESS / "check.py"), "--g1", str(ROOT)], capture_output=True, text=True, timeout=120)
    blockers = [line for line in out.stdout.splitlines() if "  BLOCKER  " in line]
    assert all("(connected in phase 2: " in line for line in blockers), out.stdout
    merged = _named_policies_merged()
    if merged and _overseer_merged():
        # the second translator merge: G1 has no BLOCKER left; the service still refuses with KIT-HS-007, which only the
        # overseer port adapter phase 2 connects causes, and the preflight row below says so
        assert blockers == [], out.stdout
    elif merged:
        assert [line.split("  ")[0] for line in blockers] == ["G1 overseer package"], out.stdout
    else:
        assert len(blockers) == 3, out.stdout
        assert any(line.startswith("G1 contract 0.5") and "contract 0.2" in line and "contract 0.3 merge" in line for line in blockers)
    env = {k: v for k, v in os.environ.items() if not k.startswith("EPINOIC_")}
    out = subprocess.run([sys.executable, str(READINESS / "check.py"), "--translator", str(ROOT)], capture_output=True, text=True, timeout=600, env=env)
    [preflight] = [line for line in out.stdout.splitlines() if line.startswith("service preflight")]
    stop = "KIT-HS-007 overseer_unavailable" if merged else "KIT-HS-006"
    assert "BLOCKER" in preflight and stop in preflight and "(connected in phase 2: " in preflight, out.stdout
    assert not [line for line in out.stdout.splitlines() if "  BLOCKER  " in line and "connected in phase 2" not in line], out.stdout


def _check_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("kit_readiness_check", READINESS / "check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_service_check_py_starts_can_import_the_flash_router_in_the_routers_own_process(monkeypatch):
    """check.py --start-service with EPINOIC_FLASH_ROUTER=epinoic_flash_router.port: the service's import path holds the
    kit's src/ and then the sub-project's src/, so the router's own process (which receives that path) imports it.
    No EPINOIC_ variable of the caller reaches the service (check.py _py drops them): a stray one is planted to show it."""
    monkeypatch.setenv("EPINOIC_STRAY_CALLER_VARIABLE", "must-not-reach-the-service")
    env = _check_module().service_env(ROOT)
    assert env["PYTHONPATH"].split(os.pathsep) == [str(ROOT / "src"), str(ROOT / "flash-router" / "src")]
    code = ("from epinoic_logic.integration import router_port as R\n"
            "a = R.attach_router('epinoic_flash_router.port')\n"
            "print(a.attached, a.refusal, a.hello.router.name if a.hello else None)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env, cwd=str(ROOT))
    assert out.stdout.split() == ["True", "None", "epinoic-flash-router"], out.stdout + out.stderr
    # The service sees exactly the kit's own EPINOIC_ variables: nothing of the caller's leaks in (whatever the caller has
    # set, e.g. EPINOIC_ARENA_ROUNDS in a simulation run), and none of the kit's is missing.
    assert "EPINOIC_STRAY_CALLER_VARIABLE" not in env
    assert {k for k in env if k.startswith("EPINOIC_")} == {
        "EPINOIC_PROFILE", "EPINOIC_SERVICE_ENV", "EPINOIC_SERVICE_TOKEN", "EPINOIC_SIGNING_KEY", "EPINOIC_VERDICT_KEY",
        "EPINOIC_OVERSEER_SECRET", "EPINOIC_TRANSLATION_PROVIDER", "EPINOIC_FIXTURE_DIR", "EPINOIC_FLASH_ROUTER"}


def test_the_router_check_runs_a_router_over_the_vectors_through_the_admission(tmp_path, monkeypatch):
    name = write_router_module(tmp_path, monkeypatch, "readiness_router")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT / "src"), os.environ.get("PYTHONPATH", "")])}
    out = subprocess.run([sys.executable, str(READINESS / "check.py"), "--router", name], capture_output=True, text=True, timeout=300, env=env)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "flash router hello" in out.stdout and "PASS" in out.stdout
    absent = subprocess.run([sys.executable, str(READINESS / "check.py"), "--router", "no_such_router_module"], capture_output=True, text=True, timeout=300, env=env)
    assert absent.returncode == 0 and "REPORTED" in absent.stdout and "floor plan runs" in absent.stdout


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_agents_check_reads_the_contracts_from_a_copy(tmp_path):
    copy = tmp_path / "agents"
    (copy / "specialist-runtime" / "src").mkdir(parents=True)
    (copy / "specialist-routing" / "src").mkdir(parents=True)
    (copy / "specialist-runtime" / "src" / "constants.js").write_text('export const RUNTIME_CONTRACT_VERSION = "epinoic.specialist-runtime.v0.1.0";\n')
    (copy / "specialist-runtime" / "src" / "provenance.js").write_text("export const P = { claims: null };\n")
    (copy / "specialist-routing" / "src" / "version.js").write_text('export const ROUTING_CONTRACT_VERSION = "epinoic.specialist-routing.v0.1.0";\n')
    run = lambda: subprocess.run([NODE, str(READINESS / "check-agents.mjs"), str(copy)], capture_output=True, text=True, timeout=60)  # noqa: E731
    assert run().returncode == 0
    (copy / "specialist-runtime" / "src" / "provenance.js").write_text("export const P = { claims: [] };\n")
    out = run()
    assert out.returncode == 1 and "BLOCKER  claims: null" in out.stdout


@pytest.mark.skipif(GIT is None, reason="needs git")
def test_the_locator_uses_top_checkouts_only(tmp_path):
    top = tmp_path / "a" / "translator"
    top.mkdir(parents=True)
    (top / "pyproject.toml").write_text('[project]\nname = "epinoic-logic"\n')
    _git(top, "init", "-q")
    _git(top, "add", "-A")
    _git(top, "commit", "-q", "-m", "x")
    _git(top, "worktree", "add", "-q", "--detach", str(tmp_path / "b" / "linked"))
    export = tmp_path / "c" / "export"
    export.mkdir(parents=True)
    (export / "pyproject.toml").write_text('[project]\nname = "epinoic-logic"\n')
    out = subprocess.run(["sh", str(READINESS / "locate.sh"), str(tmp_path)], capture_output=True, text=True, timeout=120).stdout
    lines = [line.split() for line in out.splitlines()]
    by_dir = {parts[3]: parts[1] for parts in lines}
    assert by_dir[str(top.resolve())] == "TOP" or by_dir.get(str(top)) == "TOP"
    assert by_dir.get(str(tmp_path / "b" / "linked")) == "SKIP" and by_dir.get(str(export)) == "SKIP"


def test_the_simulation_row_passes_only_on_eight_passing_gates_and_never_on_a_test_double(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("kit_readiness_check_sim", READINESS / "check.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    gates = ["G-EQ-ARENA", "G-EQ-CONTAINED", "G-FAULT", "G-INV", "G-HON", "G-DEL", "G-TAMPER", "G-OVS"]

    def row_for(results) -> tuple:
        out = tmp_path / f"out{len(list(tmp_path.iterdir()))}"
        out.mkdir()
        (out / "results.json").write_text(json.dumps(results), encoding="utf-8")
        rows: list = []
        check.simulation(ROOT, rows, str(out))
        [r] = rows
        return r
    passing = {"gates": [{"gate": g, "status": "PASS"} for g in gates], "service": {"preflight": "ready"}}
    assert row_for(passing)[1] == check.PASS
    double = dict(passing, test_double="kit_overseer_test_double")
    name, status, detail = row_for(double)
    assert status == check.BLOCKER and "test double of the overseer port" in detail and "not evidence" in detail
    refused = {"gates": [{"gate": g, "status": "NOT RUN"} for g in gates], "service": {"preflight": "KIT-HS-007 overseer_unavailable: x"}}
    assert row_for(refused)[1] == check.BLOCKER
    rows: list = []
    check.simulation(ROOT, rows, None)
    assert rows[0][1] == check.NOT_RUN


# ----------------------------------------------------------------------------------------------- the agents repositories by role

COMPAT = json.loads((ROOT / "integration" / "COMPATIBILITY.json").read_text(encoding="utf-8"))
PINS = COMPAT["agents_pins"]
V1, V2 = "epinoic.specialist-runtime.v0.1.0", "epinoic.specialist-runtime.v0.2.0"


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def _runtime_files(contract: str, *, claims: str = "null", kb_commit: str | None = None, bundle_sha: str | None = None) -> dict:
    kb = PINS["knowledge_bases"]
    entry = {"slug": "history", "source": {"repo": "Epinoic-AI/Epinoic-Agent-Training", "commit": kb_commit or kb["commit"],
                                           "bundlePath": kb["history_bundle"]["path"]},
             "bundleSha256": bundle_sha or kb["history_bundle"]["sha256"]}
    return {
        "specialist-runtime/src/constants.js": f'export const RUNTIME_CONTRACT_VERSION = "{contract}";\n',
        "specialist-runtime/src/provenance.js": f"export const P = {{ claims: {claims} }};\n",
        "specialist-runtime/src/index.js": f"export const RUNTIME_MANIFEST = Object.freeze({{ entries: [{json.dumps(entry)}] }});\n",
    }


def _routing_files(accepts: list, contract: str = "epinoic.specialist-routing.v0.1.0") -> dict:
    return {"specialist-routing/src/version.js": (f'export const ROUTING_CONTRACT_VERSION = "{contract}";\n'
                                                  f"export const ACCEPTED_RUNTIME_CONTRACT_VERSIONS = Object.freeze({json.dumps(accepts)});\n")}


def _copies(tmp_path: Path, *, runtime: dict | None = None, routing: dict | None = None, harness: dict | None = None,
            commits: dict | None = None) -> dict[str, Path]:
    """Synthetic archive copies by role: the retrained repository at the runtime pin and at the routing pin, and the
    harness (runtime v0.1.0 and its routing in one tree), each with its .kit-archive-commit."""
    commits = {"runtime": PINS["runtime"]["commit"], "routing": PINS["routing"]["commit"], "harness": PINS["harness"]["commit"], **(commits or {})}
    out = {}
    for role, files in (("runtime", runtime if runtime is not None else _runtime_files(PINS["runtime"]["contract"])),
                        ("routing", routing if routing is not None else _routing_files([V1, V2])),
                        ("harness", harness if harness is not None else {**_runtime_files(V1), **_routing_files([V1])})):
        out[role] = _write(tmp_path / role, {**files, ".kit-archive-commit": commits[role] + "\n"})
    return out


def _by_role(copies: dict[str, Path], *roles: str) -> subprocess.CompletedProcess:
    argv = [NODE, str(READINESS / "check-agents.mjs")]
    for role in roles:
        argv += [f"--{role}", str(copies[role])]
    return subprocess.run(argv, capture_output=True, text=True, timeout=60)


def _rows(out: subprocess.CompletedProcess) -> dict[str, str]:
    """{row name: status} of a role-mode output (status padded to eight characters, two spaces, name, colon)."""
    rows = {}
    for line in out.stdout.splitlines()[:-1]:
        status, rest = line[:8].strip(), line[10:]
        name = rest.split(": ", 1)[0]
        if name.endswith("claims") and rest[len(name):].startswith(": null:"):  # the row named "... claims: null"
            name += ": null"
        rows[name] = status
    return rows


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_agents_check_by_role_on_synthetic_copies(tmp_path):
    good = _copies(tmp_path / "good")
    out = _by_role(good, "runtime", "routing", "harness")
    assert out.returncode == 0 and out.stdout.strip().splitlines()[-1] == "agents contracts: accepted", out.stdout + out.stderr
    rows = _rows(out)
    assert set(rows.values()) == {"PASS"}, out.stdout
    assert {"runtime archive commit", "runtime contract", "runtime claims: null", "runtime knowledge base", "routing archive commit",
            "routing contract", "routing accepts runtime", "harness archive commit", "harness runtime contract", "harness routing contract",
            "harness claims: null", "harness routing accepts runtime"} == set(rows), out.stdout
    # each of these is a BLOCKER, and exit status 1
    blockers = {
        "runtime archive commit": dict(commits={"runtime": "0" * 40}),
        "runtime contract": dict(runtime=_runtime_files(V1)),  # accepted by a pair, but not the runtime pin's contract
        "runtime claims: null": dict(runtime=_runtime_files(PINS["runtime"]["contract"], claims="[]")),
        "runtime knowledge base": dict(runtime=_runtime_files(PINS["runtime"]["contract"], kb_commit="1" * 40)),
        "routing archive commit": dict(commits={"routing": "2" * 40}),
        "routing contract": dict(routing=_routing_files([V1, V2], contract="epinoic.specialist-routing.v0.2.0")),
        "harness routing accepts runtime": dict(harness={**_runtime_files(V2), **_routing_files([V1])}),
    }
    for i, (row, case) in enumerate(blockers.items()):
        out = _by_role(_copies(tmp_path / f"blocker{i}", **case), "runtime", "routing", "harness")
        assert out.returncode == 1 and _rows(out)[row] == "BLOCKER", (row, out.stdout)
        assert out.stdout.strip().splitlines()[-1].endswith("blocker(s)"), out.stdout
    other_bundle = _by_role(_copies(tmp_path / "bundle", runtime=_runtime_files(PINS["runtime"]["contract"], bundle_sha="3" * 64)), "runtime")
    assert other_bundle.returncode == 1 and _rows(other_bundle)["runtime knowledge base"] == "BLOCKER", other_bundle.stdout
    # REPORTED, never a stop: a routing that accepts runtime v0.1.0 only (the retrained pair is unrouted on the website),
    # and a harness copy past its pin
    v1_only = _by_role(_copies(tmp_path / "v1only", routing=_routing_files([V1])), "routing")
    assert v1_only.returncode == 0 and _rows(v1_only)["routing accepts runtime"] == "REPORTED", v1_only.stdout
    assert "D9/D10" in v1_only.stdout and v1_only.stdout.strip().splitlines()[-1] == "agents contracts: accepted"
    moved = _by_role(_copies(tmp_path / "moved", commits={"harness": "4" * 40}), "harness")
    assert moved.returncode == 0 and _rows(moved)["harness archive commit"] == "REPORTED" and "re-anchor" in moved.stdout, moved.stdout
    # usage: an unknown flag, or --kit-tree without --vendored
    assert _by_role(good, "runtime").returncode == 0
    bad = subprocess.run([NODE, str(READINESS / "check-agents.mjs"), "--runtme", str(good["runtime"])], capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2 and "usage" in bad.stderr
    bad = subprocess.run([NODE, str(READINESS / "check-agents.mjs"), "--kit-tree", "0" * 40], capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2


def _vendored_export(root: Path, *, src_tree: str | None = None, contract: str | None = None, kb_commit: str | None = None,
                     repo: str = "Epinoic-AI/Epinoic-Agent-Training", kit_tree: str | None = None) -> Path:
    """A disposable website export shaped like the History branches: vendor/specialist-runtime/SOURCE.json and, when
    `kit_tree` is given, vendor/logic-translator-kit/SOURCE.json (field names as the website's vendoring tools write)."""
    kb = PINS["knowledge_bases"]
    runtime = {"schema": "epinoic.website.vendored-source.v1",
               "package": {"name": "@epinoic/specialist-runtime", "version": "0.2.0", "contractVersion": contract or PINS["runtime"]["contract"]},
               "source": {"repo": repo, "branch": "feature/history-specialist-integration", "commit": "5" * 40,
                          "srcTree": src_tree or PINS["runtime"]["src_tree"]},
               "knowledgeBase": {"repo": repo, "commit": kb_commit or kb["commit"], "bundlePath": kb["history_bundle"]["path"],
                                 "sha256": kb["history_bundle"]["sha256"], "bytes": kb["history_bundle"]["bytes"]}}
    files = {"UNREVIEWED-SIMULATION-COPY.txt": "unmerged: test 0000000\n", "vendor/specialist-runtime/SOURCE.json": json.dumps(runtime)}
    if kit_tree is not None:
        files["vendor/logic-translator-kit/SOURCE.json"] = json.dumps({"source": {"repo": "Epinoic-AI/Epinoic-Logic-Translator", "branch": "b",
                                                                                   "commit": "6" * 40, "integrationTree": kit_tree}})
    return _write(root, files)


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_vendored_check_compares_the_websites_copies_with_the_pins(tmp_path):
    def run(export: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([NODE, str(READINESS / "check-agents.mjs"), "--vendored", str(export), *extra], capture_output=True, text=True, timeout=60)
    kit_tree = "7" * 40
    # shaped like the History staging prototype: the runtime pin's src tree, copied from another commit; no vendored kit
    out = run(_vendored_export(tmp_path / "prototype"), "--kit-tree", kit_tree)
    rows = _rows(out)
    assert out.returncode == 0, out.stdout + out.stderr
    assert [rows[r] for r in ("vendored runtime source", "vendored runtime src tree", "vendored runtime contract", "vendored knowledge base")] == ["PASS"] * 4
    assert rows["vendored kit"] == "REPORTED" and "no vendored kit" in out.stdout
    # the lower-case repository name compares (GitHub names compare without case)
    assert run(_vendored_export(tmp_path / "lower", repo="epinoic-ai/epinoic-agent-training")).returncode == 0
    # shaped like a pilot head that vendors runtime 0.3.0 (same contract, another src tree) and another kit tree
    out = run(_vendored_export(tmp_path / "pilot", src_tree="8" * 40, kit_tree="9" * 40), "--kit-tree", kit_tree)
    rows = _rows(out)
    assert out.returncode == 1 and rows["vendored runtime src tree"] == "BLOCKER" and rows["vendored kit tree"] == "BLOCKER", out.stdout
    assert rows["vendored runtime contract"] == "PASS" and rows["vendored kit source"] == "REPORTED"
    # the kit tree this kit has: PASS; without --kit-tree the vendored kit is only reported
    out = run(_vendored_export(tmp_path / "same-kit", kit_tree=kit_tree), "--kit-tree", kit_tree)
    assert out.returncode == 0 and _rows(out)["vendored kit tree"] == "PASS", out.stdout
    assert "vendored kit tree" not in _rows(run(_vendored_export(tmp_path / "no-flag", kit_tree="9" * 40)))
    # another source repository, another contract, another knowledge base: each a BLOCKER
    for name, case in (("repo", dict(repo="someone/fork")), ("contract", dict(contract=V1)), ("kb", dict(kb_commit="a" * 40))):
        out = run(_vendored_export(tmp_path / name, **case))
        assert out.returncode == 1 and "BLOCKER" in out.stdout, (name, out.stdout)
    # no vendored runtime at all (the website's main, base M): reported, not a blocker
    plain = _write(tmp_path / "main", {"UNREVIEWED-SIMULATION-COPY.txt": "x\n", "src/index.js": "export {};\n"})
    out = run(plain)
    assert out.returncode == 0 and "REPORTED  vendored runtime: no vendored runtime (base M)" in out.stdout, out.stdout


@pytest.mark.skipif(NODE is None or GIT is None, reason="needs Node.js and git")
def test_roles_names_each_checkout_by_its_remotes(tmp_path):
    def checkout(name: str, **remotes: str) -> Path:
        repo = tmp_path / name
        repo.mkdir()
        _git(repo, "init", "-q")
        for remote, url in remotes.items():
            _git(repo, "remote", "add", remote, url)
        return repo
    cases = {
        checkout("lower", origin="https://github.com/epinoic-ai/epinoic-agent-training"): ["agents"],
        checkout("ssh", origin="git@github.com:Epinoic-AI/Epinoic-Agent-Training.git"): ["agents"],
        checkout("proxy", origin="http://proxy@127.0.0.1:9/git/Epinoic-AI/Epinoic-Agent-Training"): ["agents"],
        checkout("former", epinoic="https://github.com/Bruno-ios/Epinoic-Logic-Translator.git"): ["translator"],
        checkout("harness", origin="https://github.com/danielhyon98-byte/epinoic-agent-training-api-connector/"): ["agents_harness"],
        checkout("two", origin="https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL",
                 epinoic="https://github.com/Epinoic-AI/Epinoic-Logic-Translator.git"): ["translator", "translator_development"],
    }
    for repo, roles in cases.items():
        out = subprocess.run([NODE, str(READINESS / "roles.mjs"), str(repo)], capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, (repo.name, out.stdout + out.stderr)
        assert sorted(line.split("  ")[0] for line in out.stdout.splitlines()) == roles, (repo.name, out.stdout)
        assert all(line.split("  ")[1] == str(repo) for line in out.stdout.splitlines())
    unknown = checkout("unknown", origin="https://github.com/someone/something-else.git")
    out = subprocess.run([NODE, str(READINESS / "roles.mjs"), str(unknown), str(tmp_path / "ssh")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 1 and f"none  {unknown}" in out.stdout.splitlines() and any(line.startswith("agents  ") for line in out.stdout.splitlines())


@pytest.mark.skipif(GIT is None, reason="needs git")
def test_the_locator_finds_the_retrained_repository_and_keeps_vendored_runtimes_as_reference(tmp_path):
    retrained = tmp_path / "a" / "b" / "c" / "retrained"  # its marker at depth 7 below the search root
    _write(retrained, {"README.md": "x\n", "knowledge-bases/_build/check_kb_set.py": "# marker\n"})
    _git(retrained, "init", "-q")
    _git(retrained, "add", "-A")
    _git(retrained, "commit", "-q", "-m", "x")
    site = tmp_path / "site"
    _write(site, {"package.json": '{\n  "name": "epinoic-ai-website"\n}\n',
                  "vendor/specialist-runtime/package.json": '{\n  "name": "@epinoic/specialist-runtime"\n}\n'})
    _git(site, "init", "-q")
    _git(site, "add", "-A")
    _git(site, "commit", "-q", "-m", "x")
    stray = tmp_path / "stray"  # a check_kb_set.py outside knowledge-bases/_build is no marker
    _write(stray, {"tools/check_kb_set.py": "# not a marker\n"})
    out = subprocess.run(["sh", str(READINESS / "locate.sh"), str(tmp_path)], capture_output=True, text=True, timeout=120).stdout
    rows = [line.split() for line in out.splitlines()]
    by_dir = {r[3]: (r[0], r[1]) for r in rows}
    assert by_dir[str(retrained.resolve())] == ("agents", "TOP") or by_dir.get(str(retrained)) == ("agents", "TOP"), out
    vendored = [r for r in rows if r[3] in (str(site / "vendor"), str((site / "vendor").resolve()))]
    assert vendored and all((r[0], r[1]) == ("agents-vendored", "REFERENCE") for r in vendored), out
    assert not any(r[0] == "agents" and "vendor" in r[3] for r in rows), out
    assert not any(str(stray) in r[3] for r in rows), out


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_readiness_row_runs_the_agents_check_by_role(tmp_path):
    check = _check_module()
    good = _copies(tmp_path / "good", routing=_routing_files([V1]))  # the routing accepts v0.1.0 only: one REPORTED row
    rows: list = []
    check.agents(ROOT, rows, NODE, runtime=str(good["runtime"]), routing=str(good["routing"]), harness=str(good["harness"]))
    assert [(r[0], r[1]) for r in rows] == [("agents contracts", check.PASS)], rows
    assert "agents contracts: accepted" in rows[0][2] and "1 REPORTED: routing accepts runtime" in rows[0][2], rows
    bad = _copies(tmp_path / "bad", runtime=_runtime_files(PINS["runtime"]["contract"], claims="[]"))
    rows = []
    check.agents(ROOT, rows, NODE, runtime=str(bad["runtime"]), routing=str(bad["routing"]), harness=str(bad["harness"]))
    assert rows[0][:2] == ("agents contracts", check.BLOCKER) and "blocker(s)" in rows[0][2], rows
    rows = []
    check.agents(ROOT, rows, NODE, runtime=str(good["runtime"]), routing=str(good["routing"]))
    assert [(r[0], r[1]) for r in rows] == [("agents contracts", check.PASS), ("agents harness", check.NOT_RUN)], rows
    assert "A3 and A5 are not checked" in rows[1][2]
    # Repair 1: check-agents checks only the roles it is given, so every role without a copy is a NOT RUN row of its own
    # (a harness copy alone, or the runtime and the harness without the routing, gave one PASS row before), and a NOT RUN
    # row keeps "Integration ready (local)" at NO.
    for given, unchecked in (({"harness"}, ["agents runtime", "agents routing"]), ({"runtime", "harness"}, ["agents routing"]),
                             ({"routing", "harness"}, ["agents runtime"]), ({"runtime"}, ["agents routing", "agents harness"]),
                             ({"routing"}, ["agents runtime", "agents harness"])):
        rows = []
        check.agents(ROOT, rows, NODE, **{role: str(good[role]) for role in given})
        assert rows[0][:2] == ("agents contracts", check.PASS), (given, rows)
        assert [(r[0], r[1]) for r in rows[1:]] == [(name, check.NOT_RUN) for name in unchecked], (given, rows)
        assert all(r[2].startswith(f"no --agents-{name.split()[1]}: ") and r[2].endswith("not checked") for name, r in zip(unchecked, rows[1:])), rows
        assert not check.local_ready(rows), given
    assert "the runtime pin, its contract, `claims: null` and the knowledge-base pin" in dict((r[0], r[2]) for r in rows)["agents runtime"]
    rows = []
    check.agents(ROOT, rows, NODE, runtime=str(good["runtime"]), routing=str(good["routing"]), harness=str(good["harness"]))
    assert check.local_ready(rows), "all three roles checked and accepted: the agents rows hold nothing back"
    # the earlier one-copy form checks the contracts of one copy and none of the pins: alone, every role's row is NOT RUN
    one = _write(tmp_path / "one-copy", {**_runtime_files(V1), **_routing_files([V1])})
    rows = []
    check.agents_rows(ROOT, rows, NODE, one_copy=str(one))
    assert [(r[0], r[1]) for r in rows] == [("agents contracts", check.PASS), ("agents runtime", check.NOT_RUN),
                                            ("agents routing", check.NOT_RUN), ("agents harness", check.NOT_RUN)], rows
    assert not check.local_ready(rows)
    rows = []
    check.agents_rows(ROOT, rows, NODE, runtime=str(good["runtime"]), routing=str(good["routing"]), harness=str(good["harness"]), one_copy=str(one))
    assert [(r[0], r[1]) for r in rows] == [("agents contracts", check.PASS), ("agents contracts (one copy)", check.PASS)], rows
    for node, copies, reason in ((NODE, {}, "no agents copy"), (None, {"runtime": str(good["runtime"])}, "no Node.js")):
        rows = []
        check.agents_rows(ROOT, rows, node, **copies)
        assert [(r[0], r[1]) for r in rows] == [("agents contracts", check.NOT_RUN)] and rows[0][2].startswith(reason), rows


def test_the_simulation_runtime_copy_row_needs_the_runtime_pin(tmp_path):
    """Repair 1: the simulation is evidence for the runtime pin only when its website path ran that pin. The row reads the
    copy the simulation's own output names (results.json specialist_commit and specialist_contract): PASS for the pin,
    NOT RUN for any other copy (the harness, run without --specialist; another commit or contract; no archive commit)
    and for an output that does not name it; no row without an output (the gates row is NOT RUN then).
    Repair 2: the copy fields name the copy run_sim.py GAVE the website path, written before the service starts, so the
    row is PASS only when that path also ran: no not_run.website_path, and the website driver's own line in
    subchecks.website_driver. A website path that did not run (the service refused with KIT-HS-007 on a pre-build commit,
    or the driver stopped on a contract it does not take) is NOT RUN with that reason, whatever copy it was given."""
    check = _check_module()
    pin = PINS["runtime"]

    def rows_for(results: dict) -> list:
        out = tmp_path / f"out{len(list(tmp_path.iterdir()))}"
        out.mkdir()
        (out / "results.json").write_text(json.dumps(results), encoding="utf-8")
        rows: list = []
        check.simulation_copies(ROOT, rows, str(out))
        return rows
    driver_line = "website driver: 63 turn(s), 8 tampering case(s), 24 fault case(s), 0 not run; refused hosts: 0"
    ran_pin = {"gates": [], "not_run": {}, "subchecks": {"website_driver": driver_line},
               "specialist_copy": "--specialist", "specialist_commit": pin["commit"], "specialist_contract": pin["contract"],
               "agents_copy": "--agents", "agents_commit": PINS["harness"]["commit"], "agents_contract": V1}
    [r] = rows_for(ran_pin)
    assert r[:2] == ("simulation runtime copy", check.PASS) and pin["commit"] in r[2] and PINS["harness"]["commit"] in r[2], r
    assert driver_line in r[2] and check.local_ready([r]), r
    # repair 2: the pin given, but the website path did not run: NOT RUN with the output's own reason, never PASS
    refused = "the service refused to start: KIT-HS-007 overseer_unavailable: the overseer port is not attached"
    did_not_run = {
        "service refused": dict(ran_pin, not_run={"service": refused, "website_path": refused, "agents_path": refused}, subchecks={}),
        "driver stopped": dict(ran_pin, not_run={"website_path": "not runnable: unsupported runtime contract"}, subchecks={}),
        "no driver line": dict(ran_pin, subchecks={}),
        "no sub-checks": {k: v for k, v in ran_pin.items() if k != "subchecks"},
        "not run, a stale driver line": dict(ran_pin, not_run={"website_path": "no website export (--website)"}),
    }
    for case, results in did_not_run.items():
        [r] = rows_for(results)
        assert r[1] == check.NOT_RUN and "the website path did not run" in r[2] and "not simulated" in r[2], (case, r)
        assert not check.local_ready([r]) and pin["commit"] in r[2], (case, r)
        reason = (results.get("not_run") or {}).get("website_path")
        assert (reason in r[2]) if reason else ("subchecks.website_driver" in r[2]), (case, r)
    [r] = rows_for(did_not_run["service refused"])
    assert "KIT-HS-007" in r[2] and "agents path: " in r[2] and "not run: " + refused in r[2], r
    # the agents path not running is named, and does not decide this row: the website path ran the pin
    [r] = rows_for(dict(ran_pin, not_run={"agents_path": "no agents copy (--agents)"}, agents_copy=None, agents_commit=None, agents_contract=None))
    assert r[1] == check.PASS and "agents path: no harness copy" in r[2] and "not run: no agents copy (--agents)" in r[2], r
    [r] = rows_for(dict(ran_pin, specialist_copy="--agents", specialist_commit=PINS["harness"]["commit"], specialist_contract=V1))
    assert r[1] == check.NOT_RUN and "--agents" in r[2] and "not the runtime pin" in r[2] and "not simulated" in r[2], r
    for case in (dict(ran_pin, specialist_commit="0" * 40), dict(ran_pin, specialist_contract=V1), dict(ran_pin, specialist_commit=None),
                 dict(ran_pin, specialist_copy=None, specialist_commit=None, specialist_contract=None)):
        [r] = rows_for(case)
        assert r[1] == check.NOT_RUN and not check.local_ready([r]), (case, r)
    [r] = rows_for({"gates": []})
    assert r[1] == check.NOT_RUN and "does not name the runtime copy" in r[2], r
    for sim_out in (None, str(tmp_path / "no-such-output")):
        rows: list = []
        check.simulation_copies(ROOT, rows, sim_out)
        assert rows == []


def _result_sha256(files: dict) -> str:
    """RESULT.sha256's own form: the SHA-256 of each file, two spaces, the path (apply.mjs --write-result)."""
    import hashlib
    return "".join(f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}  {rel}\n" for rel, text in files.items())


def test_the_website_patch_set_row_passes_only_on_the_tested_patch_set(tmp_path):
    """Repair 2: the row "website patch set (export)" (playbook step 14, read from step 10's export) is PASS only when
    every file RESULT.sha256 lists is in the export with its recorded digest. Drift (a listed file changed or missing,
    with the patch set applied) is a BLOCKER that names the drifted files, as step 10 stops on it: the patch set on the
    export is not the tested one, so it never counts toward "Integration ready (local)" (before, drift was REPORTED and
    readiness could read YES). A patch set not applied, an export that is not disposable, and a base without a tested
    patch set are BLOCKERs too; without an export the row is NOT RUN."""
    check = _check_module()
    patched = {"src/verify/with-verification.js": "export const withVerification = 1;\n", "src/chat/handler.js": "// patched handler\n",
               "wrangler.jsonc": "{ \"name\": \"site\" }\n"}
    kit = _write(tmp_path / "kit", {"integration/website/patches/M/RESULT.sha256": _result_sha256(patched)})
    marker = {"UNREVIEWED-SIMULATION-COPY.txt": "UNREVIEWED SIMULATION COPY of origin/main 0000000.\n"}

    def row_for(export: Path | None) -> tuple:
        rows: list = []
        check.website_copy(kit, rows, str(export) if export else None)
        [r] = rows
        assert r[0] == "website patch set (export)", r
        return r
    r = row_for(_write(tmp_path / "exact", {**marker, **patched}))
    assert r[1] == check.PASS and "exact" in r[2] and check.local_ready([r]), r
    drifted = row_for(_write(tmp_path / "drift", {**marker, **patched, "wrangler.jsonc": "{ \"name\": \"site\", \"moved\": true }\n"}))
    assert drifted[1] == check.BLOCKER and "drift in 1 file(s): wrangler.jsonc" in drifted[2] and "not the tested patch set" in drifted[2], drifted
    assert not check.local_ready([drifted]) and not check.local_ready([r, drifted])
    gone = row_for(_write(tmp_path / "missing", {**marker, **{k: v for k, v in patched.items() if k != "src/chat/handler.js"}}))
    assert gone[1] == check.BLOCKER and "drift in 1 file(s): src/chat/handler.js" in gone[2], gone
    r = row_for(_write(tmp_path / "unpatched", {**marker, "wrangler.jsonc": patched["wrangler.jsonc"]}))
    assert r[1] == check.BLOCKER and "not applied" in r[2], r
    r = row_for(_write(tmp_path / "checkout", dict(patched)))
    assert r[1] == check.BLOCKER and "not a disposable export" in r[2], r
    r = row_for(_write(tmp_path / "pilot", {**marker, **patched, "src/chat/pilot.js": "export {};\n"}))
    assert r[1] == check.BLOCKER and "base P has no tested patch set" in r[2], r
    r = row_for(None)
    assert r[1] == check.NOT_RUN and not check.local_ready([r]), r
    # on this kit's own patch set M: an applied export that holds none of the other recorded files drifts in all of them
    rows: list = []
    check.website_copy(ROOT, rows, str(_write(tmp_path / "kit-m", {**marker, "src/verify/with-verification.js": "x\n"})))
    [many] = rows
    recorded = (ROOT / "integration" / "website" / "patches" / "M" / "RESULT.sha256").read_text(encoding="utf-8").splitlines()
    assert many[1] == check.BLOCKER and f"base M: drift in {len(recorded)} file(s): " in many[2] and " ..." in many[2], many
    source = (READINESS / "check.py").read_text(encoding="utf-8")
    assert 'row(rows, "website patch set (export)", REPORTED' not in source, "drift is never REPORTED"


@pytest.mark.skipif(NODE is None or GIT is None, reason="needs Node.js and git")
def test_roles_names_only_github_urls_and_a_loopback_git_proxy(tmp_path):
    """Repair 1: the last two path segments name a role only in a GitHub URL (https, ssh, git@github.com:), a git proxy
    on loopback serving /git/<owner>/<repo>, or a bare <owner>/<repo> (the vendored SOURCE.json form). Another host, a
    local path or a file URL ending in a kit repository's name names none (exit 1; the remote named on standard error),
    and a user name or password a URL carries is never printed."""
    def checkout(name: str, **remotes: str) -> Path:
        repo = tmp_path / name
        repo.mkdir()
        _git(repo, "init", "-q")
        for remote, url in remotes.items():
            _git(repo, "remote", "add", remote, url)
        return repo

    def roles(*repos: Path) -> subprocess.CompletedProcess:
        return subprocess.run([NODE, str(READINESS / "roles.mjs"), *map(str, repos)], capture_output=True, text=True, timeout=60)
    for name, url in (("other-host", "https://git.example.com/Epinoic-AI/Epinoic-Agent-Training.git"),
                      ("local-path", str(tmp_path / "mirror" / "Epinoic-AI" / "Epinoic-Agent-Training")),
                      ("file-url", "file:///srv/mirror/Epinoic-AI/Epinoic-Agent-Training"),
                      ("proxy-not-loopback", "http://proxy@10.0.0.5:9/git/Epinoic-AI/Epinoic-Agent-Training"),
                      ("loopback-not-git", "http://127.0.0.1:9/Epinoic-AI/Epinoic-Agent-Training"),
                      ("ssh-other-host", "git@git.example.com:Epinoic-AI/Epinoic-Agent-Training.git"),
                      ("github-deeper-path", "https://github.com/Epinoic-AI/Epinoic-Agent-Training/tree/main")):
        repo = checkout(name, origin=url)
        out = roles(repo)
        assert out.returncode == 1 and out.stdout.splitlines() == [f"none  {repo}"], (name, out.stdout)
        assert f"{repo} origin " in out.stderr and "no role" in out.stderr, (name, out.stderr)
    for name, url in (("proxy-localhost", "http://local_proxy@localhost:4/git/Epinoic-AI/Epinoic-Agent-Training"),
                      ("proxy-ipv6", "http://[::1]:4/git/epinoic-ai/epinoic-agent-training"),
                      ("ssh-url", "ssh://git@github.com/Epinoic-AI/Epinoic-Agent-Training.git")):
        out = roles(checkout(name, origin=url))
        assert out.returncode == 0 and out.stdout.split("  ")[0] == "agents", (name, out.stdout + out.stderr)
    secret = "kit-test-not-a-real-token"
    out = roles(checkout("credential", origin=f"https://kit-user:{secret}@github.com/Epinoic-AI/Epinoic-Agent-Training.git"))
    assert out.returncode == 0 and out.stdout.split("  ")[0] == "agents", out.stdout
    assert out.stdout.rstrip().endswith("  https://github.com/Epinoic-AI/Epinoic-Agent-Training.git") and secret not in out.stdout + out.stderr
    out = roles(checkout("credential-other-host", origin=f"https://{secret}@git.example.com/Epinoic-AI/Epinoic-Agent-Training.git"))
    assert out.returncode == 1 and secret not in out.stdout + out.stderr, out.stdout + out.stderr
    # the vendored check reads SOURCE.json's repository the same way: another host is not the agents repository
    for repo, status in (("https://git.example.com/Epinoic-AI/Epinoic-Agent-Training", "BLOCKER"),
                         ("https://github.com/Epinoic-AI/Epinoic-Agent-Training", "PASS"), ("Epinoic-AI/Epinoic-Agent-Training", "PASS")):
        out = subprocess.run([NODE, str(READINESS / "check-agents.mjs"), "--vendored", str(_vendored_export(tmp_path / f"v{len(list(tmp_path.iterdir()))}", repo=repo))],
                             capture_output=True, text=True, timeout=60)
        assert _rows(out)["vendored runtime source"] == status and out.returncode == (1 if status == "BLOCKER" else 0), (repo, out.stdout)
