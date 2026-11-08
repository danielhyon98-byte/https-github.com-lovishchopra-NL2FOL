"""The flash router as a sub-project of its own, split-ready (architecture step 2c):

- its own pyproject and version, README, LICENSE, docs and tests; standard library only at run time;
- the docs say plainly that it is not the translator's ``RouterHub``, and give the split steps
  (``git subtree split --prefix flash-router``);
- every path the sub-project uses is inside ``flash-router/``, but for the translator's router port its tests validate
  against (found installed, or beside it in the translator's repository).
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

from epinoic_flash_router import __version__

PROJECT = Path(__file__).resolve().parents[2]


def test_it_is_a_project_of_its_own():
    meta = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    assert meta["project"]["name"] == "epinoic-flash-router" and meta["project"]["version"] == __version__
    assert meta["project"]["dependencies"] == [], "standard library only at run time"
    assert meta["tool"]["setuptools"]["package-data"]["epinoic_flash_router"] == ["data/*.json"]
    assert meta["project"]["scripts"]["epinoic-flash-router"] == "epinoic_flash_router_cli.__main__:main"
    for part in ("README.md", "LICENSE", ".gitignore", "docs/DESIGN.md", "src/epinoic_flash_router/data/MANIFEST.json",
                 "tests/flash_router_tests/conftest.py", "tests/vectors/router-port"):
        assert (PROJECT / part).exists(), part


def test_the_docs_say_plainly_what_it_is_and_how_to_split_it():
    readme = (PROJECT / "README.md").read_text(encoding="utf-8")
    design = (PROJECT / "docs" / "DESIGN.md").read_text(encoding="utf-8")
    for text in (readme, design):
        assert re.search(r"not the translator's `RouterHub`", text), "it is not the translator's RouterHub"
        assert "minimum-oversight floor" in text and "advisory" in text.lower()
    assert "git subtree split --prefix flash-router" in readme and "python -m pytest" in readme
    assert "python -m epinoic_flash_router_cli" in readme and "data/MANIFEST.json" in readme


def test_nothing_in_the_sub_project_reaches_outside_it_but_the_router_port():
    for p in sorted((PROJECT / "src").rglob("*.py")) + sorted((PROJECT / "tests").rglob("*.py")):
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"^\s*(?:from|import)\s+(epinoic_[a-z_]+)", text, re.M):
            assert m.group(1) in ("epinoic_flash_router", "epinoic_flash_router_cli", "epinoic_logic"), (p, m.group(1))
        if "epinoic_logic" in text:
            assert p.parts[-3:-1] == ("tests", "flash_router_tests"), f"only the tests read the translator's router port: {p}"
            assert not re.search(r"epinoic_logic\.(?!integration\b)", text), f"the tests use the router port contract only: {p}"
        scratch = ("/" + "tmp/", "/" + "root/")
        assert not any(s in text for s in scratch), f"no scratch path in the sub-project: {p}"
