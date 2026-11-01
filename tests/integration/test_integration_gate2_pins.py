"""Integration gate 2 (the fresh-session finding, critical): a fresh ``pip install -e ".[dev,service,providers]"`` resolved
z3-solver 5.3.3, which ``pyproject.toml`` (``z3-solver>=4.13``) and ``COMPATIBILITY.json`` (anything below 6) both accepted,
and that solver decided a nonlinear problem differently within the same budget than the 5.1.0 the suite was measured with, so
playbook step 6 could not reproduce the reference environment. The tested solver is pinned for a kit install: the constraints
file names the measured versions, step 6 installs with it and records the solver version, the readiness row prints it, and the
compatibility range accepts only the measured solver series until another is measured on the whole suite.
"""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from epinoic_logic.integration.bootstrap import version_tuple

ROOT = Path(__file__).resolve().parents[2]
CONSTRAINTS = ROOT / "integration" / "constraints.txt"
COMPAT = json.loads((ROOT / "integration" / "COMPATIBILITY.json").read_text(encoding="utf-8"))
PLAYBOOK = (ROOT / "integration" / "PLAYBOOK.md").read_text(encoding="utf-8")


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"([A-Za-z0-9._-]+)==([0-9][0-9A-Za-z.]*)", line)
        assert m, f"every constraint is one exact pin: {line!r}"
        pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    return pins


def _accepted(version: str) -> bool:
    rng = COMPAT["components"]["z3_solver"]
    return version_tuple(rng["min"]) <= version_tuple(version) < version_tuple(rng["below"])


def test_the_constraints_pin_the_measured_solver_inside_the_compatibility_range():
    pins = _pins()
    assert pins["z3-solver"] == "5.1.0.0" and _accepted(pins["z3-solver"])
    # the range is the measured series: the solver of the finding (5.3.3) and the open floor (4.13) are outside it
    assert not _accepted("5.3.3") and not _accepted("4.13") and not _accepted("6.0.0") and _accepted("5.1.0")


def test_the_constraints_pin_every_distribution_the_extras_name():
    pins = _pins()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirements = list(project["dependencies"]) + [r for extra in project["optional-dependencies"].values() for r in extra]
    named = {re.match(r"[A-Za-z0-9_.-]+", r).group(0).lower().replace("_", "-") for r in requirements}
    assert named >= {"z3-solver", "pydantic", "fastapi", "uvicorn", "anthropic", "httpx", "pytest", "pytest-timeout", "hypothesis"}
    assert named <= set(pins), sorted(named - set(pins))


def test_the_constraints_name_no_path_and_no_model():
    text = CONSTRAINTS.read_text(encoding="utf-8")
    assert "/tmp/" not in text and "/root/" not in text and "file:" not in text and "://" not in text
    assert not re.search(r"\b(Opus|Sonnet|Haiku|Fable)\b|claude-(opus|haiku|sonnet)", text)


def test_step_6_installs_with_the_constraints_and_records_the_solver_version():
    step = re.search(r"^## Step 6\..*?(?=^## )", PLAYBOOK, re.M | re.S).group(0)
    flat = re.sub(r"\s+", " ", step)
    assert '<workdir>/venv/bin/pip install -c "<kit>/integration/constraints.txt" -e "<kit>[dev,service,providers]"' in step
    assert '--no-index --find-links <wheelhouse> -c "<kit>/integration/constraints.txt" -e "<kit>[dev,service,providers]"' in flat
    assert '<workdir>/venv/bin/python -c "import z3; print(z3.get_version_string())"' in step
    assert "z3 found 5.1.0" in flat and "components.z3_solver" in flat


def test_the_readiness_row_prints_the_solver_version():
    check = (ROOT / "integration" / "readiness" / "check.py").read_text(encoding="utf-8")
    assert "require_z3(); import z3; \"\n                        \"print('z3 found', z3.get_version_string())" in check
