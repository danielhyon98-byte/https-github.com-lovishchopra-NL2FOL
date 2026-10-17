"""Playbook step 7a, ``check.py --router <module>`` (integration/router-port/CONFORMANCE.md items 1, 3 and 6): a plan is
good only when the service's admission ADOPTS it (origin ``router``, no refusal). A router whose plans are refused (not
JSON, out of contract, below the floor) is a BLOCKER named with each refusal code, although in service the floor would
run; so is a router whose plan text changes from one call to the next."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.helpers import write_router_module
from tests.integration.test_router_isolation import CHEAP

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "integration" / "readiness" / "check.py"


def _check(tmp_path, module: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT / "src")])}
    return subprocess.run([sys.executable, str(CHECK), "--router", module], capture_output=True, text=True, timeout=600, env=env)


def _row(out: str, name: str) -> str:
    return next(line for line in out.splitlines() if line.startswith(name))


@pytest.mark.parametrize("body,codes", [
    ("    return 'not json at all'\n", {"KIT-RT-016"}),
    ("    return '{}'\n", {"KIT-RT-001"}),
    ("    raise RuntimeError('router bug')\n", {"KIT-RT-016"}),
    (CHEAP, {"KIT-RT-020", "KIT-RT-007"}),  # below the floor on the risky vectors, not N_FOLD on the combined ones
])
def test_a_router_whose_plans_are_refused_is_a_blocker_named_with_its_codes(tmp_path, monkeypatch, body, codes):
    name = write_router_module(tmp_path, monkeypatch, f"refused_router_{abs(hash(body)) % 10**8}", plan_body=body)
    out = _check(tmp_path, name)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "PASS" in _row(out.stdout, "flash router hello")
    row = _row(out.stdout, "flash router plans at or above the floor")
    assert "BLOCKER" in row and all(code in row for code in codes), row


def test_a_router_that_plans_the_same_request_differently_is_a_blocker(tmp_path, monkeypatch):
    epilogue = "def _plan_id(digest):\n    return 'plan-' + str(time.time_ns())\n"
    name = write_router_module(tmp_path, monkeypatch, "unstable_router_for_readiness", epilogue=epilogue)
    out = _check(tmp_path, name)
    assert out.returncode == 1
    assert "PASS" in _row(out.stdout, "flash router plans at or above the floor")
    assert "BLOCKER" in _row(out.stdout, "flash router plans deterministic")


def test_a_conforming_router_passes_every_row(tmp_path, monkeypatch):
    name = write_router_module(tmp_path, monkeypatch, "conforming_router_for_readiness")
    out = _check(tmp_path, name)
    assert out.returncode == 0, out.stdout + out.stderr
    for row in ("flash router hello", "flash router plans at or above the floor", "flash router plans deterministic"):
        assert "PASS" in _row(out.stdout, row), out.stdout
    assert "adopted: origin router, no refusal" in _row(out.stdout, "flash router plans at or above the floor")
