"""The overseer as a separate sub-project (``overseer/``, package ``epinoic_overseer``; architecture step 2 of 3).

- it is a project of its own: its own ``pyproject.toml`` and version, README, LICENSE, docs, tests and harness, and its
  knowledge pack as its own package data;
- the package reaches the translator ONLY through the translator's documented public API (``epinoic_logic.api``) and
  the integration protocol's modules (the overseer port contract, the protocol, its errors, its canonical JSON and the
  router port's pool operation; never the service's implementation modules such as its turn, routes or self-test): no
  module of the package imports another translator module, and every public name it imports resolves (architecture
  review after arena round 8: the rule admitted the whole ``epinoic_logic.integration`` package before; it is the stricter
  explicit set now);
- the tests and the harness scripts use the same two doors except for the imports one explicit, documented allowlist
  names (``internal_imports.py``: monkeypatch targets, drift comparisons, names the public API does not offer yet, the
  translator's test fixtures), file by file, under a ceiling that may only be lowered; and no path in them climbs above
  the sub-project (a standalone copy has no translator above it: they reach the translator's files through
  ``translator_checkout``);
- the package checks, when it is imported, that the installed translator offers every name it imports
  (``compat.py``), and refuses an incompatible translator with one error naming them all;
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
from pathlib import Path, PurePosixPath

import pytest

import epinoic_logic
import epinoic_overseer
from epinoic_overseer.pack import PACK_DIGESTS, PACK_NAME, installed_pack, installed_pack_dir, load_pack

from .internal_imports import ALLOWED, CATEGORIES, CEILING, COPIED_FILES, PROTOCOL_MODULES
from .translator_checkout import SUBPROJECT, translator_root

PACKAGE = Path(epinoic_overseer.__file__).resolve().parent
TRANSLATOR_PACKAGE = Path(epinoic_logic.__file__).resolve().parent
#: The two doors: the public API's modules and the integration protocol's modules (``internal_imports.PROTOCOL_MODULES``),
#: never the service's implementation modules of ``epinoic_logic.integration`` (turn, routes, settings, runtime, selftest).
ALLOWED_TRANSLATOR_MODULES = re.compile(r"^epinoic_logic\.api(\.[a-z_]+)?$|^epinoic_logic\.integration\.(" + "|".join(PROTOCOL_MODULES) + r")$")

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
#: combined answer; a MAJOR version, the kind synthesis_carries_fault added); 2.1, integration step 2 (specialist feedback:
#: the review of a revision request; a MINOR version), the installed pack since.
POSTMOVE_PACK_DIGESTS = {"2.0": "c2be21abf85f01cf672666650cdf5bb2ee26926c6095eb1569db3e193123f673",
                         "2.1": "a60727fce80a4190f59a8a0e21bf0c69cb759bab4a04876d81c88095ea21ebb5"}


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
    assert installed_pack().identity.version == "2.1" and Path(knowledge_dir := str(PACKAGE / "knowledge")).is_dir(), knowledge_dir


# ----------------------------------------------------------------------------------------------- isolation
def test_the_package_reaches_the_translator_only_through_its_public_api_and_the_integration_protocol():
    # rewritten to a stricter rule after arena round 8's architecture review: the integration protocol is its explicit
    # modules (PROTOCOL_MODULES), no longer every module of epinoic_logic.integration (the service's self-test set passed
    # the old rule), and a dynamic import of a translator module counts too
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
        for name in _dynamic_imports(p):
            # a dynamic import names a door too; only the compatibility check builds a module name, of the public API's
            # areas and of the protocol modules its lists name (test_the_compatibility_lists_are_what_the_package_imports)
            ok = ALLOWED_TRANSLATOR_MODULES.match(name) or (p.name == "compat.py" and name in ("epinoic_logic.api.{}", "epinoic_logic.integration.{}"))
            assert ok or not name.startswith("epinoic_logic"), f"{p.relative_to(PACKAGE)} imports a translator module dynamically: {name}"
    assert {m for m in seen if m.startswith("epinoic_logic.api")} and {m for m in seen if m.startswith("epinoic_logic.integration")}
    assert {m.rsplit(".", 1)[1] for m in seen if m.startswith("epinoic_logic.integration.")} == set(PROTOCOL_MODULES)
    for rejected in ("epinoic_logic.integration.selftest", "epinoic_logic.integration.turn", "epinoic_logic.integration.routes",
                     "epinoic_logic.integration", "epinoic_logic.channel.bus", "epinoic_logic.apix"):
        assert not ALLOWED_TRANSLATOR_MODULES.match(rejected), rejected


def _dynamic_imports(p: Path) -> list[str]:
    """The module name of every ``import_module(...)`` and ``__import__(...)`` call of ``p``: a string literal as written, an
    f-string with each placeholder written ``{}``, anything else ``"<computed>"``."""
    out = []
    for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and node.args and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module") or (isinstance(node.func, ast.Name) and node.func.id in ("import_module", "__import__"))):
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.append(arg.value)
            elif isinstance(arg, ast.JoinedStr):
                out.append("".join(v.value if isinstance(v, ast.Constant) else "{}" for v in arg.values))
            else:
                out.append("<computed>")
    return out


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
    # architecture step 3 made pack 2.0 the installed pack, and integration step 2 (specialist feedback) 2.1: every pack
    # pinned before the move is still pinned to its premove digest and still loads with it, and those pinned since are 2.0
    # (still loading with its digest) and 2.1, the installed pack (the same exact pins, two more)
    assert {v: d for (n, v), d in PACK_DIGESTS.items() if n == PACK_NAME} == {**PREMOVE_PACK_DIGESTS, **POSTMOVE_PACK_DIGESTS}
    assert installed_pack().identity.sha256 == POSTMOVE_PACK_DIGESTS["2.1"]
    for version, digest in {**PREMOVE_PACK_DIGESTS, "2.0": POSTMOVE_PACK_DIGESTS["2.0"]}.items():
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


# ----------------------------------------------------------------------------------------------- the tests and the scripts
#: Where the tests and the harness scripts live (``scripts/`` is never installed with the package).
SCANNED = ("tests", "scripts")


def _scanned_files() -> list[Path]:
    out = []
    for sub in SCANNED:
        for p in sorted((SUBPROJECT / sub).rglob("*.py")):
            if "__pycache__" not in p.parts:
                out.append(p)
    return out


def _internal_imports(p: Path) -> set[tuple[str, str]]:
    """``(internal module, name)`` of every import of a translator module ``p`` makes that is not the public API or an
    integration-protocol module (``name`` is "" for the module itself)."""
    out: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and not node.level and (node.module or "").split(".")[0] == "epinoic_logic":
            for a in node.names:
                full = f"{node.module}.{a.name}" if node.module == "epinoic_logic.integration" else node.module
                if not ALLOWED_TRANSLATOR_MODULES.match(full):
                    out.add((node.module, a.name))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] == "epinoic_logic" and not ALLOWED_TRANSLATOR_MODULES.match(a.name):
                    out.add((a.name, ""))
    return out


def test_the_tests_and_scripts_import_translator_internals_only_where_the_allowlist_names_them():
    """Architecture review after arena round 8: the tests and the harness scripts reach the translator through its public
    API and the integration protocol, except for the imports ``internal_imports.ALLOWED`` names file by file (monkeypatch
    targets, drift comparisons, names the public API does not offer yet, the translator's test fixtures, the service's own
    modules a test compares with). A new direct import fails; an entry no file still makes fails (remove it); the
    entries never exceed the ceiling, which may only be lowered: the count only goes down."""
    copies = {f"tests/overseer_tests/{c}" for c in COPIES if c.endswith(".py")}
    assert set(COPIED_FILES) == copies, "the unscanned copies are exactly the byte-equal copies of the translator's test material"
    allowed = {(m, n, f) for m, (_cat, _why, names) in ALLOWED.items() for n, files in names.items() for f in files}
    found = set()
    for p in _scanned_files():
        rel = p.relative_to(SUBPROJECT).as_posix()
        if rel in COPIED_FILES or rel == "tests/overseer_tests/internal_imports.py":
            continue
        found |= {(m, n, rel) for m, n in _internal_imports(p)}
    new = sorted(found - allowed)
    assert not new, ("imports of translator internals the allowlist does not name (use epinoic_logic.api.*, or the translator's public API is "
                     f"to add the name; a tampering case's patch target is listed in internal_imports.py): {new[:12]}")
    stale = sorted(allowed - found)
    assert not stale, f"allowlist entries no file makes any more (remove them: the count only goes down): {stale[:12]}"
    assert len(allowed) <= CEILING, f"{len(allowed)} direct imports exceed the ceiling of {CEILING} (it may only be lowered)"
    for m, (cat, why, names) in ALLOWED.items():
        assert cat in CATEGORIES and why.strip() and names, m
        assert not ALLOWED_TRANSLATOR_MODULES.match(m), f"{m} is a door, not an internal module"
    # the debt measured at the review was 91 test files and 6 scripts; the move onto the public API leaves fewer
    files = {f for _m, _n, f in allowed}
    assert len({f for f in files if f.startswith("tests/")}) < 91 and len({f for f in files if f.startswith("scripts/")}) < 6


def test_the_ratchet_names_a_new_direct_import_and_a_stale_entry(tmp_path):
    """A control of the ratchet's reader: a direct import of an internal module or name is found, the public API and
    the protocol modules are not, a module imported whole is the empty name."""
    probe = tmp_path / "probe.py"
    probe.write_text("from epinoic_logic.channel.bus import _now\nimport epinoic_logic.channel.bus as bus\n"
                     "from epinoic_logic.api.channel import TranslatorChannel\nfrom epinoic_logic.integration.protocol import PROTOCOL\n"
                     "from epinoic_logic.integration import router_pool, turn\nfrom epinoic_logic.integration.selftest import PROBLEMS\n", encoding="utf-8")
    assert _internal_imports(probe) == {("epinoic_logic.channel.bus", "_now"), ("epinoic_logic.channel.bus", ""),
                                        ("epinoic_logic.integration", "turn"), ("epinoic_logic.integration.selftest", "PROBLEMS")}


#: The translator-checkout resolvers: the only functions that may look at the directory enclosing the sub-project, and
#: only after checking that it is a translator checkout (``translator_checkout.translator_root``, the harness's
#: ``ovs_harness._translator_root``).
CHECKOUT_RESOLVERS = ("translator_root", "_translator_root")


def _climbs(rel: str, source: str) -> list[str]:
    """Every expression of the file ``rel`` (its path inside the sub-project) holding ``source`` that reaches a directory
    above the sub-project: ``Path(__file__)`` (or its ``resolve()`` / ``absolute()``) followed by ``.parent`` or
    ``.parents[k]`` steps past the sub-project root, or a computed ``parents[...]`` index on it; a ``.parent`` or
    ``.parents[...]`` of a name for the sub-project root (``SUBPROJECT``, ``SUBPROJECT_ROOT``); a ``..`` segment in a
    string given to ``Path`` or joined with ``/``. The checkout resolvers (:data:`CHECKOUT_RESOLVERS`) are exempt."""
    depth = len(PurePosixPath(rel).parts) - 1  # directories between the sub-project root and the file
    tree = ast.parse(source)
    exempt: set[int] = set()
    path_parts: set[int] = set()  # string constants used as path segments
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in CHECKOUT_RESOLVERS:
            exempt.update(id(n) for n in ast.walk(node))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            path_parts.update(id(n) for n in (node.left, node.right))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("Path", "PurePath", "PurePosixPath"):
            path_parts.update(id(n) for n in node.args)

    def unwrap(node: ast.AST) -> ast.AST:
        while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("resolve", "absolute"):
            node = node.func.value
        return node

    def is_file_path(node: ast.AST) -> bool:
        node = unwrap(node)
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path" and len(node.args) == 1
                and isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__")

    def climb(node: ast.AST) -> tuple[int, ast.AST]:
        """(levels climbed, base) of a chain of ``.parent`` and ``.parents[k]`` steps (k a literal)."""
        n = 0
        while True:
            if isinstance(node, ast.Attribute) and node.attr == "parent":
                n, node = n + 1, node.value
            elif (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents"
                  and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int)):
                n, node = n + node.slice.value + 1, node.value.value
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("resolve", "absolute"):
                node = node.func.value
            else:
                return n, node

    out: list[str] = []
    for node in ast.walk(tree):
        if id(node) in exempt:
            continue
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            n, base = climb(node)
            if n and is_file_path(base) and n > depth + 1:
                out.append(f"line {node.lineno}: {n} levels up from {rel}, above the sub-project")
            elif n and isinstance(unwrap(base), ast.Name) and unwrap(base).id in ("SUBPROJECT", "SUBPROJECT_ROOT"):
                out.append(f"line {node.lineno}: above the sub-project root ({unwrap(base).id})")
            if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents"
                    and not isinstance(node.slice, ast.Constant) and is_file_path(node.value.value)):
                out.append(f"line {node.lineno}: a computed parents[...] index")
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) in path_parts
                and ".." in node.value.replace("\\", "/").split("/")):
            out.append(f"line {node.lineno}: a '..' path segment")
    return sorted(set(out))


def test_no_path_in_the_tests_or_scripts_climbs_above_the_sub_project():
    """Architecture review after arena round 8: a test reached the translator's arena tools with
    ``Path(__file__).resolve().parents[3]``, a directory above the sub-project, so a standalone copy (``git subtree split``)
    failed it whenever the recorded rounds were supplied. The tests and the scripts reach the translator's files only
    through ``translator_checkout`` (``EPINOIC_TRANSLATOR_ROOT`` in a standalone copy) or the harness's ``REPO_ROOT``."""
    faults = {}
    for p in _scanned_files():
        rel = p.relative_to(SUBPROJECT).as_posix()
        found = _climbs(rel, p.read_text(encoding="utf-8"))
        if found:
            faults[rel] = found
    assert not faults, faults


@pytest.mark.parametrize("rel, source, climbs", [
    # the defect the review found, and the same climb written other ways
    ("tests/overseer_tests/t.py", "X = Path(__file__).resolve().parents[3] / 'scripts' / 'arena'\n", True),
    ("tests/overseer_tests/t.py", "X = Path(__file__).parent.parent.parent.parent\n", True),
    ("tests/overseer_tests/t.py", "X = Path(__file__).resolve().parent / '..' / '..' / '..' / 'scripts'\n", True),
    ("tests/overseer_tests/t.py", "X = Path('../../../scripts/arena')\n", True),
    ("scripts/s.py", "X = Path(__file__).resolve().parents[2]\n", True),
    ("tests/overseer_tests/t.py", "SUBPROJECT = Path(__file__).resolve().parents[2]\nX = SUBPROJECT.parent / 'scripts'\n", True),
    ("tests/overseer_tests/t.py", "k = 3\nX = Path(__file__).resolve().parents[k]\n", True),
    # controls: the sub-project root and below, a refusal case's text, the one resolver
    ("tests/overseer_tests/t.py", "X = Path(__file__).resolve().parents[2] / 'scripts'\n", False),
    ("scripts/s.py", "X = Path(__file__).resolve().parents[1]\n", False),
    ("tests/overseer_tests/t.py", "BAD = ['../01-role-and-trust.md', '..']\n", False),
    ("tests/overseer_tests/t.py", "SUBPROJECT = Path(__file__).resolve().parents[2]\ndef translator_root():\n    return SUBPROJECT.parent\n", False),
])
def test_the_climbing_rule_has_controls(rel, source, climbs):
    assert bool(_climbs(rel, source)) is climbs, _climbs(rel, source)


# ----------------------------------------------------------------------------------------------- the translator it needs
def _package_translator_names() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    api: dict[str, set[str]] = {}
    proto: dict[str, set[str]] = {}
    for p in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and not node.level and (node.module or "").startswith("epinoic_logic."):
                parts = node.module.split(".")
                target = api if parts[1] == "api" else proto
                target.setdefault(parts[2], set()).update(a.name for a in node.names)
    return api, proto


def test_the_compatibility_lists_are_what_the_package_imports():
    """``compat.REQUIRED_API`` and ``REQUIRED_PROTOCOL`` are exactly the translator names the package's modules import,
    so the import-time check holds the translator to what this release really uses."""
    from epinoic_overseer import compat
    api, proto = _package_translator_names()
    assert {a: set(n) for a, n in compat.REQUIRED_API.items()} == api
    assert {m: set(n) for m, n in compat.REQUIRED_PROTOCOL.items()} == proto
    assert all(isinstance(v, tuple) and all(isinstance(x, str) for x in v) for v in [*compat.REQUIRED_API.values(), *compat.REQUIRED_PROTOCOL.values()])
    assert compat.missing_translator_names() == []


def test_a_translator_without_a_name_this_release_imports_is_refused_at_import_with_one_clear_error():
    """Architecture review after arena round 8: an overseer release paired with a translator that lacks a public name it
    imports (``FEEDBACK_KEY_ID`` here, as for the release before it) installs, since both distributions carry the versions
    they always carried, and failed only with a bare ImportError from deep inside the package. It is refused by the check
    that runs first, naming every missing name; a public API stating another MAJOR version is refused too.

    Each case runs in a fresh interpreter (``python -I``: it reads no ``PYTHONPATH`` and inherits nothing of this session's
    path), given first on its path the directory this session imported the package from, as the session's ``pythonpath``
    gives it: the repository's test command also runs where only the translator is installed, and before, every case there
    failed with ModuleNotFoundError instead of reaching the check. The fresh interpreter is held to resolve the package
    under test itself, never another installed copy (an assertion added with that fix: a stricter rule)."""
    import subprocess
    import sys
    root = str(PACKAGE.parent)
    where = subprocess.run([sys.executable, "-I", "-c", "import importlib.util, sys\nsys.path.insert(0, sys.argv[1])\n"
                            "print(importlib.util.find_spec('epinoic_overseer').origin)\n", root], capture_output=True, text=True, timeout=300)
    assert Path(where.stdout.strip()).resolve() == PACKAGE / "__init__.py", (where.stdout, where.stderr[-2000:])
    code = ("import sys\nsys.path.insert(0, sys.argv[1])\n"
            "import epinoic_logic.api as api, epinoic_logic.api.channel as ch\n"
            "del ch.EXPORTS['FEEDBACK_KEY_ID']\n{extra}"
            "try:\n    import epinoic_overseer\nexcept ImportError as exc:\n    print(type(exc).__name__ + ': ' + str(exc))\nelse:\n    print('IMPORTED')\n")
    out = subprocess.run([sys.executable, "-I", "-c", code.format(extra=""), root], capture_output=True, text=True, timeout=300)
    assert out.stdout.startswith("TranslatorIncompatible: epinoic-overseer ") and "api.channel.FEEDBACK_KEY_ID" in out.stdout, (out.stdout, out.stderr[-2000:])
    assert "Install the translator release this overseer release was built against" in out.stdout
    major = subprocess.run([sys.executable, "-I", "-c", code.replace("del ch.EXPORTS['FEEDBACK_KEY_ID']\n", "").format(extra="api.API_VERSION = '2.0'\n"), root],
                           capture_output=True, text=True, timeout=300)
    assert major.stdout.startswith("TranslatorIncompatible: ") and "version 2.0; this release speaks version 1.x" in major.stdout, (major.stdout, major.stderr[-2000:])
    same = subprocess.run([sys.executable, "-I", "-c", code.replace("del ch.EXPORTS['FEEDBACK_KEY_ID']\n", "").format(extra="api.API_VERSION = '1.7'\n"), root],
                          capture_output=True, text=True, timeout=300)
    assert same.stdout.strip() == "IMPORTED", (same.stdout, same.stderr[-2000:])
