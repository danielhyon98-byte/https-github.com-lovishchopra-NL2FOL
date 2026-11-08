"""The overseer as a separate sub-project (``overseer/``, package ``epinoic_overseer``; architecture step 2 of 3).

- it is a project of its own: its own ``pyproject.toml`` and version, README, LICENSE, docs, tests and harness, and its
  knowledge pack as its own package data;
- the package reaches the translator ONLY through the translator's documented public API (``epinoic_logic.api``) and
  the integration protocol (``epinoic_logic.integration``): no module of the package imports a translator module
  directly, and every public name it imports resolves;
- the translator never imports it (it is attached through ``RouterHub(auditor=...)`` and the overseer port);
- the move kept the pack: every pinned pack digest is the one recorded before the move, and the exported pack's zip is
  byte for byte the one exported before it;
- the test helpers and recorded material copied from the translator's tests when the suite moved stay equal to the
  translator's while both live in one repository.
"""
from __future__ import annotations

import ast
import hashlib
import re
import tomllib
from pathlib import Path

import pytest

import epinoic_logic
import epinoic_overseer
from epinoic_overseer.pack import PACK_DIGESTS, PACK_NAME, installed_pack, installed_pack_dir, load_pack

from .translator_checkout import SUBPROJECT, translator_root

PACKAGE = Path(epinoic_overseer.__file__).resolve().parent
TRANSLATOR_PACKAGE = Path(epinoic_logic.__file__).resolve().parent
ALLOWED_TRANSLATOR_MODULES = re.compile(r"^epinoic_logic\.(api|integration)(\.|$)")

#: The pack digests recorded before the move (premove baseline): the move changes no pack.
PREMOVE_PACK_DIGESTS = {
    "1.0": "df73e1e60913fc6ce35d8fadb74612e6be75dff6ae292aef4496a06c3201a448",
    "1.1": "f0999e7096ef461cf66ba1c74e5a95c8d28b95595d0c2f04e938f18529691c09",
    "1.2": "bb2ab43e20d0d08956041775201192cbe528038f0a154258b4966a448a02f13a",
    "1.3": "b44776a1d76a0ee1ac8b02cd9e3596c832ee3dbfe51fff76d8c09ec4970c6f67",
    "1.4": "a80fb042158efa8b81991c378f17f98c22985104fb822c72c9706ab427dcf8bc",
    "1.5": "cac995dccdb03feeb0b68c8b7d0eb94d1dd4be6839de6b6e48c401085ec787ab",
}
#: The deterministic zip of the installed pack (1.5), exported by the package's exporter before the move.
PREMOVE_ZIP_SHA256 = "fb7308eb3afa7746e965bb4884969147bb3edbd965f518a7af489a8d107da4c5"
#: The packs pinned after the move, each with the step that made it: 2.0, architecture step 3 (the twofold review of a
#: combined answer; a MAJOR version, the kind synthesis_carries_fault added), the installed pack since.
POSTMOVE_PACK_DIGESTS = {"2.0": "c2be21abf85f01cf672666650cdf5bb2ee26926c6095eb1569db3e193123f673"}


def _imports(path: Path) -> list[tuple[int, str]]:
    """(level, absolute-or-relative module) of every import of a file."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            out.append((node.level, node.module or ""))
        elif isinstance(node, ast.Import):
            out.extend((0, a.name) for a in node.names)
    return out


# ----------------------------------------------------------------------------------------------- a project of its own
def test_it_is_a_project_of_its_own_with_its_version():
    meta = tomllib.loads((SUBPROJECT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert meta["name"] == "epinoic-overseer" and meta["version"] == epinoic_overseer.__version__
    assert meta["dependencies"] == ["epinoic-logic>=0.1.0"], "the translator is the one dependency (its public API)"
    for part in ("README.md", "LICENSE", ".gitignore", "pyproject.toml", "docs/OVERSEER_DESIGN.md", "docs/OVERSEER_RESULTS.md",
                 "docs/OVERSEER_AGENT_BRIEF.md", "docs/DELIVERY.md", "scripts/run_contained.py", "scripts/ovs_harness.py", "scripts/tamper.py",
                 "src/epinoic_overseer/port.py", "src/epinoic_overseer/hub_ops.py"):
        assert (SUBPROJECT / part).is_file(), part
    readme = (SUBPROJECT / "README.md").read_text(encoding="utf-8")
    assert "git subtree split --prefix overseer" in readme and "epinoic_logic.api" in readme and "python -m pytest" in readme


def test_the_package_ships_its_knowledge_pack_as_its_own_package_data():
    conf = tomllib.loads((SUBPROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    assert conf["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert set(conf["tool"]["setuptools"]["package-data"]["epinoic_overseer"]) == {"knowledge/*/*.txt", "knowledge/*/*.md", "knowledge/*/*.json"}
    assert installed_pack().identity.version == "2.0" and Path(knowledge_dir := str(PACKAGE / "knowledge")).is_dir(), knowledge_dir


# ----------------------------------------------------------------------------------------------- isolation
def test_the_package_reaches_the_translator_only_through_its_public_api_and_the_integration_protocol():
    seen = set()
    for p in sorted(PACKAGE.rglob("*.py")):
        for level, mod in _imports(p):
            if level:
                depth = len(p.relative_to(PACKAGE).parts) - 1  # how many packages the file sits below epinoic_overseer
                assert level <= depth + 1, f"{p.name}: a relative import leaves the package ({'.' * level}{mod})"
                continue
            if mod.split(".")[0] == "epinoic_logic":
                assert ALLOWED_TRANSLATOR_MODULES.match(mod), f"{p.relative_to(PACKAGE)} imports translator internals: {mod}"
                seen.add(mod)
    assert {m for m in seen if m.startswith("epinoic_logic.api")} and {m for m in seen if m.startswith("epinoic_logic.integration")}


def test_every_public_name_the_package_imports_resolves():
    import importlib
    names = set()
    for p in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and not node.level and (node.module or "").startswith("epinoic_logic.api"):
                names.update((node.module, a.name) for a in node.names)
    assert len(names) > 150
    for module, name in sorted(names):
        assert hasattr(importlib.import_module(module), name), (module, name)


def test_the_translator_never_imports_the_overseer():
    for p in sorted(TRANSLATOR_PACKAGE.rglob("*.py")):
        for _level, mod in _imports(p):
            assert not mod.startswith("epinoic_overseer"), f"the translator imports the overseer: {p}"
        assert "epinoic_logic.overseer" not in p.read_text(encoding="utf-8"), p
    import importlib.util
    assert importlib.util.find_spec("epinoic_logic.overseer") is None, "no shim at the old path"


# ----------------------------------------------------------------------------------------------- the pack kept
def test_every_pinned_pack_digest_is_the_one_recorded_before_the_move():
    # architecture step 3 made pack 2.0 the installed pack: every pack pinned before the move is still pinned to its premove
    # digest and still loads with it, and the one pinned since is 2.0, the installed pack (the same exact pins, one more)
    assert {v: d for (n, v), d in PACK_DIGESTS.items() if n == PACK_NAME} == {**PREMOVE_PACK_DIGESTS, **POSTMOVE_PACK_DIGESTS}
    assert installed_pack().identity.sha256 == POSTMOVE_PACK_DIGESTS["2.0"]
    for version, digest in PREMOVE_PACK_DIGESTS.items():
        assert load_pack(installed_pack_dir(version)).identity.sha256 == digest, version


def test_the_exported_pack_is_byte_for_byte_the_one_exported_before_the_move(tmp_path):
    # since architecture step 3 the installed pack is 2.0: the pack exported before the move, 1.5, is exported by name and is
    # still byte for byte the premove zip
    from epinoic_overseer.export import export_pack
    res = export_pack(tmp_path / "out", zip_archive=True, pack=load_pack(installed_pack_dir("1.5")))
    assert res.zip_sha256 == PREMOVE_ZIP_SHA256 and res.identity.sha256 == PREMOVE_PACK_DIGESTS["1.5"]


# ----------------------------------------------------------------------------------------------- copies kept equal
COPIES = {  # this suite's copy -> the translator's original (relative to the translator's repository)
    "core_hostile.py": "tests/core_hostile.py", "timing.py": "tests/timing.py", "growth.py": "tests/growth.py",
    "c1_texts.py": "tests/branches/c1_texts.py", "r7_support.py": "tests/channel/r7_support.py",
    "data/r7_material.json": "tests/channel/data/r7_material.json", "data/r7_translations.json": "tests/channel/data/r7_translations.json",
    "data/c1_core_material.json": "tests/channel/data/c1_core_material.json",
}


@pytest.mark.parametrize("copy,original", sorted(COPIES.items()))
def test_the_copied_test_material_is_the_translators(copy, original):
    root = translator_root()
    if root is None:
        pytest.skip("a standalone copy of the sub-project: no translator checkout to compare with (set EPINOIC_TRANSLATOR_ROOT)")
    here = Path(__file__).resolve().parent / copy
    assert hashlib.sha256(here.read_bytes()).hexdigest() == hashlib.sha256((root / original).read_bytes()).hexdigest(), copy


def test_the_copied_stem_helpers_are_the_translators():
    root = translator_root()
    if root is None:
        pytest.skip("a standalone copy of the sub-project: no translator checkout to compare with (set EPINOIC_TRANSLATOR_ROOT)")
    original = ast.parse((root / "tests" / "stem" / "test_stem_repair5.py").read_text(encoding="utf-8"))
    copy = ast.parse((Path(__file__).resolve().parent / "stem_decide.py").read_text(encoding="utf-8"))

    def defs(tree):
        return {n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("decide", "holds", "failing")}
    assert defs(copy) == defs(original) and len(defs(copy)) == 3
