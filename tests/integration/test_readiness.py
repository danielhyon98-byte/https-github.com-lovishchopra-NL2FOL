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


def test_g1_on_this_tree_names_the_parts_phase_2_connects_and_reports_the_router():
    out = subprocess.run([sys.executable, str(READINESS / "check.py"), "--g1", str(ROOT)], capture_output=True, text=True, timeout=120)
    rows = {line.split("  ")[0].strip(): line for line in out.stdout.splitlines()}
    assert out.returncode == 1
    assert "BLOCKER" in rows["G1 overseer package"]
    if _named_policies_merged():  # contract 0.3 merged: its row passes, and the contract line moved to 0.4 with it
        assert "PASS" in rows["G1 named policies (contract 0.3)"] and "PASS" in rows["G1 contract 0.4"], out.stdout
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
    one, and the preflight row names KIT-HS-007 (the overseer port adapter)."""
    out = subprocess.run([sys.executable, str(READINESS / "check.py"), "--g1", str(ROOT)], capture_output=True, text=True, timeout=120)
    blockers = [line for line in out.stdout.splitlines() if "  BLOCKER  " in line]
    assert blockers and all("(connected in phase 2: " in line for line in blockers), out.stdout
    merged = _named_policies_merged()
    if merged:
        assert [line.split("  ")[0] for line in blockers] == ["G1 overseer package"], out.stdout
    else:
        assert len(blockers) == 3, out.stdout
        assert any(line.startswith("G1 contract 0.4") and "contract 0.2" in line and "contract 0.3 merge" in line for line in blockers)
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


def test_the_service_check_py_starts_can_import_the_flash_router_in_the_routers_own_process():
    """check.py --start-service with EPINOIC_FLASH_ROUTER=epinoic_flash_router.port: the service's import path holds the
    kit's src/ and then the sub-project's src/, so the router's own process (which receives that path) imports it."""
    env = _check_module().service_env(ROOT)
    assert env["PYTHONPATH"].split(os.pathsep) == [str(ROOT / "src"), str(ROOT / "flash-router" / "src")]
    code = ("from epinoic_logic.integration import router_port as R\n"
            "a = R.attach_router('epinoic_flash_router.port')\n"
            "print(a.attached, a.refusal, a.hello.router.name if a.hello else None)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env, cwd=str(ROOT))
    assert out.stdout.split() == ["True", "None", "epinoic-flash-router"], out.stdout + out.stderr
    assert not any(k.startswith("EPINOIC_") and k != "EPINOIC_FLASH_ROUTER" and k not in env for k in os.environ)


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
