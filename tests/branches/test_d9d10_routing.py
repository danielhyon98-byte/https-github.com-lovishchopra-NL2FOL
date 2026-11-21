"""D9/D10 (decision D35): Geography and every Language B and ab initio course route to their own branches; the subjects no other branch
serves still go to the generic branch. Each branch runs the shared core pack first (the one self-certification gate) and its own pack, with
the generic parser and no hub hooks; no pack other than the core pack holds a self-certification reader; the three new modules evaluate
nothing (an AST scan, as the STEM suites do)."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.branches.geography import GeographyPack
from epinoic_logic.branches.language_b import LanguageBPack
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.branches.registry import default_registry

from .d9d10_hub import KEY

PACKAGE = Path(inspect.getfile(GeographyPack)).parent


@pytest.mark.parametrize("label,key", [
    ("Geography", "geography"), ("Geography HL", "geography"), ("IB Geography: Paper 1", "geography"),
    ("Language B: Spanish", "language_b"), ("Spanish B HL", "language_b"), ("language-b-spanish", "language_b"), ("French B", "language_b"),
    ("Spanish ab initio", "language_b"), ("Mandarin B", "language_b"),
    ("Philosophy", "generic"), ("Visual Arts", "generic"), ("TOK", "generic"), ("Underwater Basket Weaving", "generic"), (None, "generic"),
])
def test_labels_route_to_their_branch(label, key):
    assert default_registry().for_subject(label)[0].key == key


def test_the_two_branches_are_composed_as_designed():
    r = default_registry()
    geo, lb = r.get("geography"), r.get("language_b")
    assert [type(p) for p in geo.packs] == [CorePack, GeographyPack] and [type(p) for p in lb.packs] == [CorePack, LanguageBPack]
    assert geo.hub_hooks is None and lb.hub_hooks is None
    assert geo.profile_keys == ("geography",) and lb.profile_keys == ("language_b",)
    for b, agent in ((geo, "geography-specialist"), (lb, "language-b-spanish-specialist")):
        parser = b.parser()
        assert type(parser) is GenericTextParser and parser.agent_id == agent
    assert "geography" not in r.get("generic").profile_keys and "language_b" not in r.get("generic").profile_keys


def test_the_hub_reports_the_new_branches():
    hub = RouterHub(signing_key=KEY)
    assert hub.branch_for("Geography") == "geography" and hub.branch_for("Language B: Spanish") == "language_b"
    assert hub.branch_for("Philosophy") == "generic"


def test_every_branch_runs_the_shared_core_pack_first():
    r = default_registry()
    for key in r.keys():
        assert isinstance(r.get(key).packs[0], CorePack), key
    for key in r.keys():
        for pack in r.get(key).packs[1:]:
            names = [n for n, _v in inspect.getmembers(type(pack)) if "self_cert" in n]
            assert not names, (key, type(pack).__name__, names)


_FORBIDDEN_NAMES = frozenset({"eval", "exec", "compile", "__import__", "globals", "locals", "vars", "open", "input", "breakpoint", "setattr", "delattr"})
_FORBIDDEN_ATTRS = frozenset({"eval", "exec", "sympify", "parse_expr", "literal_eval", "loads", "load", "system", "popen", "import_module", "__subclasses__",
                              "__globals__", "__builtins__", "__code__", "run_path", "run_module"})


@pytest.mark.parametrize("module", ["geography", "language_b", "spanish_lexicon"])
def test_the_new_modules_evaluate_nothing(module):
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in _FORBIDDEN_NAMES, (module, node.lineno, node.id)
        elif isinstance(node, ast.Attribute):
            assert node.attr not in _FORBIDDEN_ATTRS, (module, node.lineno, node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(n.split(".")[0] in ("importlib", "sympy", "numexpr", "pickle", "marshal", "subprocess", "os") for n in names), (module, names)
