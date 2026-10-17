"""The flash router as a separate, independent agent in its own sub-project (``flash-router/``, package
``epinoic_flash_router``; PROTOCOL.md section 7a; decision D28): it is edited, tested and released apart from the Z3
infrastructure, and the service reaches it only through the router port, in its own process.

- its own suite (CONFORMANCE.md items 1 to 6) passes in the sub-project;
- the service attaches it by name and ADOPTS its plan for every router-port vector (origin ``router``, no refusal);
- the readiness check of playbook step 7a passes it;
- it is attached only when ``EPINOIC_FLASH_ROUTER`` names it: unset or ``none`` detaches it even when it is installed,
  so the rollback "set none, or remove the variable" holds (ROLLBACK.md, D28);
- it depends on nothing at run time, and the translator's package never imports it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from epinoic_logic.integration import router_port as R
from epinoic_logic.integration.runtime import build_runtime
from epinoic_logic.integration.settings import IntegrationSettings
from tests.integration.helpers import FixtureProbes, RecordingPort, env, hello, settings

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "flash-router"
SRC = PROJECT / "src"
VECTORS = sorted((ROOT / "integration" / "vectors" / "router-port").glob("*.json"))


@pytest.fixture
def installed(monkeypatch):
    """The sub-project importable, as it is once installed next to the service."""
    monkeypatch.syspath_prepend(str(SRC))
    return "epinoic_flash_router.port"


def test_the_sub_projects_own_suite_passes():
    environ = {**os.environ, "PYTHONPATH": os.pathsep.join([str(SRC), str(ROOT / "src")])}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=PROJECT, capture_output=True, text=True,
                          timeout=900, env=environ)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert re.search(r"\b\d+ passed\b", proc.stdout) and " failed" not in proc.stdout


def test_the_service_attaches_it_in_its_own_process_and_adopts_its_plans(installed):
    att = R.attach_router(installed)
    assert att.attached and att.refusal is None and att.module == installed
    from epinoic_flash_router import __version__
    from epinoic_flash_router.rules import COST_DATA_SHA256, RULES_SHA256
    assert R.dump(att.hello.router) == {"name": "epinoic-flash-router", "version": __version__, "rules_sha256": RULES_SHA256,
                                        "cost_data_sha256": COST_DATA_SHA256}
    for p in VECTORS:
        req = R.check_request(json.loads(p.read_text(encoding="utf-8"))["request"])
        adm = R.route(req, att)
        assert (adm.origin, adm.refusal) == ("router", None), (p.stem, adm.detail)
        assert R.below_floor(adm.effective, adm.floor) is None


def test_the_readiness_check_of_step_7a_passes_it():
    environ = {**os.environ, "PYTHONPATH": os.pathsep.join([str(SRC), str(ROOT / "src")])}
    out = subprocess.run([sys.executable, str(ROOT / "integration" / "readiness" / "check.py"), "--router", "epinoic_flash_router.port"],
                         capture_output=True, text=True, timeout=600, env=environ)
    assert out.returncode == 0, out.stdout + out.stderr
    rows = [line for line in out.stdout.splitlines() if line.startswith("flash router")]
    assert len(rows) == 3 and all("PASS" in r for r in rows), out.stdout


def test_it_is_attached_only_when_named_so_removing_the_variable_detaches_it(installed):
    assert IntegrationSettings.from_env({}).flash_router == "none"
    assert IntegrationSettings.from_env({"EPINOIC_FLASH_ROUTER": "  "}).flash_router == "none"
    assert not R.attach_router(IntegrationSettings.from_env({}).flash_router).attached
    unset = build_runtime(settings(FLASH_ROUTER=None), probes=FixtureProbes(RecordingPort(hello_message=hello(agents="async"))))
    caps = unset.capabilities()["ports"]["router"]
    assert (caps["attached"], caps["identity"], caps["refusal"], caps["required"]) == (False, None, None, False)
    assert "EPINOIC_FLASH_ROUTER" not in env(FLASH_ROUTER=None)
    named = build_runtime(settings(FLASH_ROUTER=installed), probes=FixtureProbes(RecordingPort(hello_message=hello(agents="async"))))
    caps = named.capabilities()["ports"]["router"]
    assert caps["attached"] is True and caps["identity"]["name"] == "epinoic-flash-router" and caps["refusal"] is None


def test_it_is_a_project_of_its_own_that_the_translator_never_imports(installed):
    meta = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    assert meta["project"]["name"] == "epinoic-flash-router" and meta["project"]["dependencies"] == []
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert root["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"], "the translator's package never ships the router"
    for p in (ROOT / "src" / "epinoic_logic").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+epinoic_flash_router", text, re.M), p
    from epinoic_flash_router import __version__
    assert __version__ == meta["project"]["version"], "the identity's version is the project's version"
