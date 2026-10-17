"""The combinator is a project of its own, independent of the Z3 infrastructure.

* it runs with nothing but its own ``src/`` on the import path, in an isolated interpreter, and imports neither the
  translator, the engine, Z3 nor pydantic;
* its package never imports the translator; its ``pyproject.toml`` has its own name and version, no run-time
  dependency, and ships its instructions and its contract copy as package data;
* it is ready to be split into a repository of its own (``git subtree split --prefix combinator``): nothing in it
  reaches outside its directory except the tests' optional use of the translator's ``src/``.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

from epinoic_combinator import __version__

PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
PACKAGE = SRC / "epinoic_combinator"


def test_it_runs_isolated_with_only_its_own_src_and_imports_no_translator():
    code = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from epinoic_combinator import port\n"
        "from epinoic_combinator.providers import FaithfulFakeProvider\n"
        "from epinoic_combinator.pack import load_pack\n"
        "hello = json.loads(port.hello())\n"
        "doc = {'schema': 'epinoic.integration.combinator-input.v1', 'protocol': 'epinoic.integration.v1', 'port_version': '1.0',\n"
        "       'ids': {'task_id': 't-1', 'request_id': 'a-1'}, 'vocabulary': hello['vocabulary'], 'instruction_pack': load_pack().identity(),\n"
        "       'sources': []}\n"
        "from epinoic_combinator.jsonio import sha256_text\n"
        "for rid, cid, t in (('rep-a', 'a1', 'The treaty was signed in 1919.'), ('rep-b', 'b1', 'Hyperinflation peaked in 1923.')):\n"
        "    doc['sources'].append({'report_id': rid, 'agent_id': rid[4:], 'subject': 'History', 'branch': 'history', 'claims': [\n"
        "        {'claim_id': cid, 'role': 'point', 'materiality': 'material', 'certainty': 'established', 'claim_text_sha256': sha256_text(t), 'text': t}]})\n"
        "out = json.loads(port.combine(json.dumps(doc), FaithfulFakeProvider()))\n"
        "assert out['schema'] == 'epinoic.integration.combinator-output.v1', out\n"
        "forbidden = [m for m in sys.modules if m.split('.')[0] in ('epinoic_logic', 'z3', 'pydantic', 'pydantic_core')]\n"
        "print('imports', forbidden)\n"
    )
    out = subprocess.run([sys.executable, "-I", "-c", code, str(SRC)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "imports []"


def test_the_package_never_imports_the_translator():
    for p in PACKAGE.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+(epinoic_logic|z3|pydantic)\b", text, re.M), p


def test_it_is_a_project_of_its_own():
    meta = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    project = meta["project"]
    assert project["name"] == "epinoic-combinator" and project["version"] == __version__ and project["dependencies"] == []
    data = meta["tool"]["setuptools"]["package-data"]["epinoic_combinator"]
    assert {"pack/*.md", "pack/*.json", "contract/*.json"} <= set(data)
    shipped = sorted(p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*") if p.is_file() and p.suffix in (".md", ".json"))
    assert shipped == sorted(["pack/INSTRUCTIONS.md", "pack/output-format.json", *(f"contract/{n}" for n in (
        "combinator-hello.v1.schema.json", "combinator-input.v1.schema.json", "combinator-output.v1.schema.json", "combinator-port.v1.json",
        "combinator-refusal.v1.schema.json", "synthesis-vocabulary.v1.json"))])
    for name in ("README.md", "LICENSE", "docs/DESIGN.md"):
        assert (PROJECT / name).is_file(), name


def test_the_package_reads_its_files_as_package_data_never_by_a_path_outside_it():
    for p in PACKAGE.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "__file__" not in text and "parents[" not in text and "os.path" not in text, p
    assert "importlib import resources" in (PACKAGE / "pack.py").read_text(encoding="utf-8")
    assert "importlib import resources" in (PACKAGE / "contract.py").read_text(encoding="utf-8")
