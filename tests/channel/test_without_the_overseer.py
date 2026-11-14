"""The translator's tests run where the overseer sub-project is not installed (architecture lenses after arena round 8,
"translator never imports overseer" and "standalone split").

The overseer (``overseer/``, package ``epinoic_overseer``) depends on the translator and never the reverse; after the
documented split the translator is a project of its own whose suite runs with at most the overseer installed as a
package. The channel's tests reached into the overseer's in-repository layout: ``test_integration_gate3_handoff.py``
imported the overseer's TEST package (``overseer_tests.conftest``, put on the path by ``tests/overseer_support.py``) when
it was collected, so with the overseer absent, or installed as a package without its tests, ``tests/channel`` did not
collect; ``test_integration_gate1_channel.py`` and ``test_integration_gate3_channel.py`` imported ``overseer_tests``
inside a test (a failure at run time), and ``test_revision_feedback_rules.py`` imported the overseer's modules unguarded.
They now reach the overseer only through ``tests/overseer_attach.py`` (its public package API, with
``pytest.importorskip``), and the channel's own facts those tests asserted beside the overseer's are also asserted with no
overseer attached.

The other packages' tests had the same dependency, handed off by the core fixer and applied by the handoff fixer of the
same review (H1 to H10): eight modules did not collect (a module-level import of the overseer, of its test package or of
a private name), and 73 tests failed and 6 errored at run time over ``tests/e2e``, ``tests/integration``,
``tests/contract``, ``tests/branches/test_hub_revisions.py`` and the STEM round tests (an unguarded import inside a
test, the integration helpers' real port adapter, and the arena harness's delivery pass, which imported the overseer and
ended every round). :data:`PENDING` is now empty, so every rule below holds for the whole suite.

Held here:

* the translator's tests (``tests/``) collect with the overseer off the path (``epinoic_overseer`` and ``overseer_tests``
  unimportable, ``overseer/`` off ``sys.path`` and off the test path): no module fails to collect, and each module of the
  core packages' tests (channel, integrity, translate, engine, service) collects exactly the tests it collects with the
  overseer present;
* every core test that attaches the overseer is SKIPPED there with ``overseer_attach.REASON`` (none passes, fails or
  errs), and passes with the overseer installed as a package but its tests absent (the split's other state);
* every test that failed or errored there before the handoff fixer's pass (:data:`FAILED_WITHOUT_THE_OVERSEER`) now
  passes or is skipped with ``overseer_attach.REASON``, and the translator's own (:data:`RUN_WITHOUT_THE_OVERSEER`: the
  arena harness's rounds, whose overseer passes are then recorded as not run) pass; the tests that imported the
  overseer's test package pass with the overseer installed without its tests;
* no translator test imports the overseer's test package, ``tests/overseer_support.py`` (deleted) or a private name of
  the overseer; every import of the overseer in the translator's tests is ``pytest.importorskip`` with a reason (never a
  plain import, at module level or inside a test); the core tests import the overseer only through ``overseer_attach``,
  which imports only its public modules, with ``pytest.importorskip``, and they read no path inside ``overseer/``. That
  last rule stays the core packages': the integration kit's tests examine the overseer sub-project itself (its port
  adapter, its pinned pack, its layout) through public modules ``overseer_attach`` does not name, each guarded.

The subprocesses make the overseer unimportable with a finder placed ahead of every other, so neither an installed copy,
an editable install nor a source tree on the path is reached: the check holds on this repository without removing
anything from it.
"""
from __future__ import annotations

import ast
import functools
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from epinoic_logic.integrity import WorkPlan

from ..overseer_attach import PUBLIC_MODULES, REASON, make_auditor, make_keyring, observed_channel, overseer, overseer_module

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
HELPER = TESTS / "overseer_attach.py"  # shared by the whole translator suite (it sat in tests/channel/ before)
#: The core packages' tests (owner: core), which reach the overseer only through ``overseer_attach``.
CORE = ("tests/channel/", "tests/integrity/", "tests/translate/", "tests/engine/", "tests/service/")
#: The overseer sub-project's importable names: its package and its test package.
OVERSEER_NAMES = ("epinoic_overseer", "overseer_tests")
#: The other owners' modules that still reach the overseer when collected, or through its test package, a private name
#: or a path into ``overseer/``. The list only shrinks: a module is removed from it once it is fixed, and the rule then
#: holds for it too. Empty since the handoff fixer's pass (it held tests/overseer_support.py, deleted, and eight modules
#: of tests/adapters, tests/branches, tests/e2e and tests/stem, each fixed): every rule here holds for the whole suite.
PENDING: frozenset = frozenset()
#: The core tests that attach the overseer (at least these: ``_attached_tests`` finds every one).
ATTACHED = (
    "tests/channel/test_integration_gate1_channel.py::test_a_material_eligible_claim_with_no_outcome_is_named_not_attempted_and_never_verified",
    "tests/channel/test_integration_gate1_channel.py::test_the_deadline_finding_case_agrees_with_the_delivery_policy",
    "tests/channel/test_integration_gate1_channel.py::test_every_claim_with_an_outcome_keeps_the_receipt_clean",
    "tests/channel/test_integration_gate1_channel.py::test_a_supporting_or_ineligible_claim_with_no_outcome_is_not_named",
    "tests/channel/test_integration_gate3_channel.py::test_the_overseer_fidelity_check_reads_the_same_sentences_as_content",
    "tests/channel/test_integration_gate3_handoff.py::test_a_structured_report_with_a_long_unresolved_issue_crosses_the_hub_and_its_audit_in_linear_time",
    "tests/channel/test_integration_gate3_handoff.py::test_a_failed_middle_dot_check_gives_the_engines_values_per_reading",
    "tests/channel/test_integration_gate3_handoff.py::test_control_a_check_of_one_reading_keeps_its_note",
    "tests/channel/test_revision_feedback_rules.py::test_only_allowlisted_codes_ever_yield_a_flaw",
)
#: The translator tests that FAILED or ERRED at run time with the overseer off the path (:data:`ABSENT`) before the
#: handoff fixer's pass (measured on 8 November: 73 failed and 6 errors over these, beside the eight modules that did not
#: collect), by module or test; a module or a test function selects every parameter. Each now passes, or is skipped with
#: ``overseer_attach.REASON`` where what it tests is the overseer's own.
FAILED_WITHOUT_THE_OVERSEER = (
    "tests/e2e/test_arena_measures.py",  # 9: the arena harness's delivery pass imported the overseer and ended the round (H9)
    "tests/e2e/test_arena_revisions.py",  # 6: the revision feedback is built through the overseer's auditor: skipped
    "tests/integration/test_fixture_parity.py",  # 5 errors: its module fixture runs an arena round (H9)
    "tests/integration/test_turn_checker.py",  # 20 [real] parameters: the overseer's port adapter (helpers.real_port, H7)
    "tests/integration/test_turn_fixes.py",  # 12 [real] parameters
    "tests/integration/test_turn_review.py",  # 15 [real] parameters
    "tests/integration/test_overseer_subproject.py",  # 2: unguarded imports of the overseer (H7)
    "tests/integration/test_preflight_handshake.py::test_the_default_overseer_port_adapter_is_the_overseer_sub_projects_and_connects",
    "tests/integration/test_protocol_constants.py::test_the_audit_scope_sentence_is_the_overseers_own_constant_verbatim",
    "tests/branches/test_hub_revisions.py",  # 2: an unguarded import inside a helper (H3)
    "tests/stem/test_arena_stem_mutations.py::test_a_contained_round_names_every_stem_injection_and_leaves_history_unchanged",
    "tests/stem/test_e2e_run1_detection.py::test_the_verifiers_probe_misses_are_counted_as_misses",
    "tests/stem/test_e2e_run1_detection.py::test_a_contained_round_names_all_six_faults",
    "tests/stem/test_e2e_run1_detection.py::test_no_unnamed_stem_injection_is_ever_excused",
    "tests/e2e/test_arena_deliveries.py",  # did not collect: the overseer's test package (H5)
)
#: Of :data:`FAILED_WITHOUT_THE_OVERSEER`, the tests of the translator's own behaviour, which must PASS with the overseer
#: off the path (never be skipped): the arena harness's rounds (their delivery and revision passes are recorded as not
#: run), the hub's refusal without an auditor and the turn checker on the test double of the overseer port.
RUN_WITHOUT_THE_OVERSEER = (
    "tests/e2e/test_arena_measures.py::",
    "tests/integration/test_fixture_parity.py::",
    "tests/stem/test_arena_stem_mutations.py::test_a_contained_round_names_every_stem_injection_and_leaves_history_unchanged",
    "tests/stem/test_e2e_run1_detection.py::test_a_contained_round_names_all_six_faults",
    "tests/branches/test_hub_revisions.py::test_every_feedback_entry_point_refuses_without_an_auditor",
    "tests/integration/test_turn_checker.py::test_single_clean_answer_is_delivered_with_the_formal_results_of_its_encoding_only[double]",
    "tests/integration/test_overseer_subproject.py::test_the_translator_never_imports_the_overseer",
)
#: The translator tests that imported the overseer's TEST package (``overseer_tests``) before the handoff fixer's pass
#: (H4, H5): with the overseer installed but its tests absent they must pass.
TEST_PACKAGE_IMPORTERS = (
    "tests/branches/test_integration_gate3_qualified_ids.py::test_the_overseer_reparse_reproduces_the_qualified_report",
    "tests/e2e/test_arena_deliveries.py",
)

# ============================================================================================ pytest in a subprocess
#: The overseer neither installed nor on the path: both names unimportable, ``overseer/`` off ``sys.path`` and off the
#: test path (the ini's ``pythonpath`` without ``overseer/src``).
ABSENT = {"blocked": list(OVERSEER_NAMES), "strip": ["overseer"], "pythonpath": "flash-router/src"}
#: The overseer installed as a package, its tests absent (``overseer_tests`` unimportable).
INSTALLED_WITHOUT_TESTS = {"blocked": ["overseer_tests"], "strip": [os.path.join("overseer", "tests")], "pythonpath": None}
#: The repository as it is.
PRESENT = {"blocked": [], "strip": [], "pythonpath": None}

_BOOT = """
import importlib.abc, json, os, sys
state = json.loads(sys.argv[1])
blocked = tuple(state["blocked"])
strip = tuple(os.path.join(os.getcwd(), d) + os.sep for d in state["strip"])
sys.path[:] = [p for p in sys.path if not (os.path.abspath(p or os.curdir) + os.sep).startswith(strip)] if strip else sys.path
class NotInstalled(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.partition(".")[0] in blocked:
            raise ModuleNotFoundError("No module named %r" % name, name=name)
        return None
sys.meta_path.insert(0, NotInstalled())
import pytest
sys.exit(pytest.main(sys.argv[2:]))
"""


def _pytest(state: dict, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
    env["COLUMNS"] = "1000"  # no skip reason cut short
    opts = ["-p", "no:cacheprovider", "-p", "no:warnings"]
    if state["pythonpath"] is not None:
        opts += ["-o", f"pythonpath={state['pythonpath']}"]
    return subprocess.run([sys.executable, "-c", _BOOT, json.dumps(state), *opts, *args], cwd=ROOT, capture_output=True, text=True,
                          timeout=600, env=env)


def _summary_line(out: str) -> str:
    """The run's final summary line (``15172/15217 tests collected ... in 10.3s``, ``9 skipped in 2.1s``). Only this
    short line is matched with patterns: the node ids above it hold runs of 20,000 digits and blanks (the hostile
    parameters), on which an unanchored number pattern would be quadratic."""
    lines = [line for line in out.splitlines() if line.strip()]
    assert lines, out
    last = lines[-1].strip("= ")
    assert len(last) < 300, last[:300]
    return last


def _collected(out: str) -> tuple[Counter, set[str]]:
    """Tests collected per module, and the modules that failed to collect, from ``--co -q`` output."""
    lines = out.splitlines()
    per_module = Counter(line.split("::", 1)[0] for line in lines if line.startswith("tests/") and "::" in line)
    errors = {line.split(maxsplit=2)[1] for line in lines if line.startswith("ERROR ") and len(line.split(maxsplit=2)) > 1}
    assert re.match(r"\d+(?:/\d+)? tests? collected", _summary_line(out)), out[-3000:]
    return per_module, errors


def _outcomes(out: str) -> dict[str, int]:
    """The final summary line's counts (``9 skipped in 2.1s`` -> ``{"skipped": 9}``)."""
    return {word.rstrip("s") if word.startswith("error") else word: int(n)
            for n, word in re.findall(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)", _summary_line(out))}


# ============================================================================================ reading the tests as data
def _py_files(prefixes=("tests/",)) -> list[Path]:
    return [p for p in sorted(TESTS.rglob("*.py")) if "__pycache__" not in p.parts and p.relative_to(ROOT).as_posix().startswith(prefixes)]


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _call_name(node: ast.Call) -> str:
    return node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""


def _first_text(node: ast.Call):
    return node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) else None


def _overseer_name(name: str) -> bool:
    return name.partition(".")[0] in OVERSEER_NAMES


def _imports_overseer_attach(node: ast.ImportFrom) -> bool:
    return (node.module or "").rpartition(".")[2] == "overseer_attach"


@functools.lru_cache(maxsize=None)
def _overseer_functions() -> frozenset[str]:
    """The functions of ``overseer_attach`` that reach the overseer (each skips where it is not installed)."""
    defs = {n.name: n for n in ast.parse(HELPER.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)}
    reach: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, fn in defs.items():
            calls = {_call_name(c) for c in ast.walk(fn) if isinstance(c, ast.Call)}
            if name not in reach and ("importorskip" in calls or calls & reach):
                reach.add(name)
                changed = True
    return frozenset(reach)


@functools.lru_cache(maxsize=None)
def _attached_tests() -> tuple[str, ...]:
    """The node ids of the core tests that attach the overseer: every test that reaches a function of
    ``overseer_attach`` that reaches the overseer, directly or through the functions and classes of its own module (this
    module, which runs the others, apart)."""
    reach = _overseer_functions()
    ids: list[str] = []
    for path in _py_files(CORE):
        if not path.name.startswith("test_") or path == Path(__file__).resolve():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def helper_names(nodes) -> set[str]:
            out: set[str] = set()
            for n in nodes:
                if isinstance(n, ast.ImportFrom):
                    if _imports_overseer_attach(n):
                        out |= {a.asname or a.name for a in n.names if a.name in reach}
                    out |= {a.asname or a.name for a in n.names if a.name == "overseer_attach"}  # the module itself
            return out

        module_level = helper_names(tree.body)
        top = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        attached: set[str] = set()
        changed = True
        while changed:
            changed = False
            for name, node in top.items():
                if name in attached:
                    continue
                used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):  # a fixture by its parameter's name
                    used |= {a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs}
                if used & (module_level | helper_names(ast.walk(node)) | attached):
                    attached.add(name)
                    changed = True
        ids += [f"{_rel(path)}::{name}" for name in sorted(attached) if name.startswith(("test", "Test"))]
    return tuple(ids)


def _test_package_or_private(path: Path) -> list[str]:
    """Where the module at ``path`` imports the overseer's test package or ``tests/overseer_support.py``, builds a path
    to the overseer's tests, or reads a private name of the overseer."""
    return _test_package_or_private_in(path.read_text(encoding="utf-8"))


_IMPORTERS = ("importorskip", "import_module", "__import__")


def _test_package_or_private_in(source: str) -> list[str]:
    """:func:`_test_package_or_private` on a module's source text."""
    tree = ast.parse(source)
    out: list[str] = []
    bound: set[str] = set()  # names bound to an overseer module
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.partition(".")[0] == "overseer_tests" or "overseer_support" in a.name.split("."):
                    out.append(f"{node.lineno}: import {a.name}")
                elif _overseer_name(a.name):
                    bound.add(a.asname or a.name.partition(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = [a.name for a in node.names]
            if mod.partition(".")[0] == "overseer_tests" or "overseer_support" in mod.split(".") + names:
                out.append(f"{node.lineno}: from {mod or '.'} import {', '.join(names)}")
            elif _overseer_name(mod):
                out += [f"{node.lineno}: from {mod} import {n} (a private name)" for n in names if n.startswith("_")]
                bound |= {a.asname or a.name for a in node.names}
        elif isinstance(node, ast.Call) and _call_name(node) in _IMPORTERS and (_first_text(node) or "").partition(".")[0] == "overseer_tests":
            out.append(f"{node.lineno}: {_call_name(node)}({_first_text(node)!r})")
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and (
                _call_name(node.value) in ("overseer", "overseer_module")
                or (_call_name(node.value) in _IMPORTERS and _overseer_name(_first_text(node.value) or ""))):
            bound |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant) and node.right.value == "tests" \
                and isinstance(node.left, ast.BinOp) and isinstance(node.left.right, ast.Constant) and node.left.right.value == "overseer":
            out.append(f"{node.lineno}: a path to overseer/tests")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
            value = node.value
            while isinstance(value, ast.Attribute):  # epinoic_overseer.delivery_policy._name: the chain's root
                value = value.value
            on_module = (isinstance(value, ast.Name) and value.id in bound) or (
                isinstance(value, ast.Call) and (_call_name(value) in ("overseer", "overseer_module")
                                                 or (_call_name(value) in _IMPORTERS and _overseer_name(_first_text(value) or ""))))
            if on_module:
                out.append(f"{node.lineno}: reads the private name {node.attr}")
    return out


# ============================================================================================ the translator's tests collect
def test_the_translator_tests_collect_with_the_overseer_off_the_path():
    absent = _pytest(ABSENT, "--co", "-q", "--continue-on-collection-errors", "tests")
    counts, errors = _collected(absent.stdout)
    assert not [m for m in errors if m.startswith(CORE)], (sorted(errors), absent.stdout[-4000:])
    assert errors <= PENDING, (sorted(errors - PENDING), absent.stdout[-4000:])
    assert counts["tests/channel/test_integration_gate3_handoff.py"] > 20  # the module that did not collect before


def test_no_core_test_module_collects_fewer_tests_without_the_overseer():
    absent_counts, absent_errors = _collected(_pytest(ABSENT, "--co", "-q", *CORE).stdout)
    present_counts, present_errors = _collected(_pytest(PRESENT, "--co", "-q", *CORE).stdout)
    assert not absent_errors and not present_errors, (absent_errors, present_errors)
    lost = {m: (present_counts.get(m), absent_counts.get(m)) for m in present_counts.keys() | absent_counts.keys()
            if present_counts.get(m) != absent_counts.get(m)}
    assert not lost, lost  # none is skipped whole, none loses a parameter: the translator-only tests all still run
    assert len(present_counts) > 100 and all(m.startswith(CORE) for m in present_counts)


# ============================================================================================ the tests that attach it
def test_the_core_tests_that_attach_the_overseer_are_found():
    ids = _attached_tests()
    assert set(ATTACHED) <= set(ids), sorted(set(ATTACHED) - set(ids))
    # the channel's own facts those tests assert beside the overseer's are asserted again with no overseer attached
    for added in ("test_integration_gate1_channel.py::test_a_material_eligible_claim_with_no_outcome_is_named_not_attempted_with_no_overseer_attached",
                  "test_integration_gate3_handoff.py::test_a_failed_middle_dot_check_gives_the_engines_values_per_reading_with_no_overseer_attached",
                  "test_revision_feedback_rules.py::test_only_allowlisted_codes_of_the_translators_own_source_ever_yield_a_flaw"):
        assert f"tests/channel/{added}" not in ids, added


def test_every_core_test_that_attaches_the_overseer_is_skipped_where_it_is_not_installed():
    ids = _attached_tests()
    assert set(ATTACHED) <= set(ids)  # never an empty selection (pytest would then run the whole default suite)
    proc = _pytest(ABSENT, "-q", "-rs", *ids)
    counts = _outcomes(proc.stdout)
    assert proc.returncode == 0 and set(counts) == {"skipped"} and counts["skipped"] >= len(ids), (counts, proc.stdout[-4000:], proc.stderr[-2000:])
    reasons = [line for line in proc.stdout.splitlines() if line.startswith("SKIPPED")]
    assert reasons and all(REASON in line for line in reasons), reasons
    assert sum(int(re.match(r"SKIPPED \[(\d+)\]", line).group(1)) for line in reasons) == counts["skipped"]


def test_with_the_overseer_installed_without_its_tests_the_core_tests_that_attach_it_pass():
    overseer()  # where the overseer is not installed there is nothing to run them with (the test above holds instead)
    ids = _attached_tests()
    assert set(ATTACHED) <= set(ids)  # never an empty selection (pytest would then run the whole default suite)
    proc = _pytest(INSTALLED_WITHOUT_TESTS, "-q", *ids)
    counts = _outcomes(proc.stdout)
    assert proc.returncode == 0 and set(counts) == {"passed"} and counts["passed"] >= len(ids), (counts, proc.stdout[-4000:], proc.stderr[-2000:])


def _block_overseer(monkeypatch) -> None:
    """Make the overseer unimportable in this process (as where it is not installed), restored after the test."""
    for name in [n for n in list(sys.modules) if _overseer_name(n)] + list(OVERSEER_NAMES):
        monkeypatch.setitem(sys.modules, name, None)


@pytest.mark.parametrize("call", [
    overseer, lambda: overseer_module("epinoic_overseer"), lambda: overseer_module("epinoic_overseer.emitted"), make_keyring, make_auditor,
    lambda: observed_channel(None, WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="short_answer",
                                            selected_agent_ids=["history-specialist"])),
], ids=["overseer", "package", "emitted", "make_keyring", "make_auditor", "observed_channel"])
def test_each_function_that_attaches_the_overseer_skips_where_it_is_not_installed(monkeypatch, call):
    _block_overseer(monkeypatch)
    with pytest.raises(pytest.skip.Exception) as skipped:
        call()
    assert REASON in str(skipped.value)


def test_no_module_of_the_overseer_but_its_public_ones_is_ever_imported():
    for name in ("epinoic_overseer.delivery_policy", "epinoic_overseer.codes", "overseer_tests.conftest", "epinoic_overseer._private"):
        with pytest.raises(ValueError):
            overseer_module(name)


# ============================================================================================ what the tests import
def test_no_translator_test_imports_the_overseers_test_package_or_a_private_name():
    found = {_rel(p): v for p in _py_files() if (v := _test_package_or_private(p))}
    assert not [m for m in found if m.startswith(CORE)], {m: v for m, v in found.items() if m.startswith(CORE)}
    assert set(found) <= PENDING, {m: v for m, v in found.items() if m not in PENDING}


def test_the_rule_reads_the_imports_it_forbids():
    """Controls: the reader of the rule above names each form it forbids, and none of the public forms."""
    for src in ("from overseer_tests.conftest import make_auditor\n", "import overseer_tests.delivery_support\n", "from .. import overseer_support\n",
                "from epinoic_overseer.delivery_policy import SELF_REPORT_CODES, _receipt_findings_of\n",
                "import epinoic_overseer.delivery_policy as D\nD._receipt_findings_of(1, 2)\n", "x = overseer()._journal\n",
                "import epinoic_overseer.delivery_policy\nepinoic_overseer.delivery_policy._receipt_findings_of(1, 2)\n",
                "m = overseer_module('epinoic_overseer.emitted')\nm._receipt_table()\n", "from pathlib import Path\nP = Path('.') / 'overseer' / 'tests'\n",
                "import pytest\nc = pytest.importorskip('overseer_tests.conftest')\n"):
        assert _test_package_or_private_in(src), src
    for src in ("from epinoic_overseer import TransferAuditor\n", "x = overseer().DeliveryPolicy\n", "m = overseer_module('epinoic_overseer.emitted')\nm.RECEIPT_CODES\n",
                "x = obj._private\n", "AgentRole.OVERSEER, 'overseer'\n", "NAMES = ('epinoic_overseer', 'overseer_tests')\n"):
        assert not _test_package_or_private_in(src), src


def test_the_core_tests_reach_the_overseer_only_through_overseer_attach():
    bad = []
    for path in _py_files(CORE):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        helper = path == HELPER
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(_overseer_name(a.name) for a in node.names):
                bad.append(f"{_rel(path)}:{node.lineno}: imports the overseer directly")
            elif isinstance(node, ast.ImportFrom) and _overseer_name(node.module or ""):
                bad.append(f"{_rel(path)}:{node.lineno}: imports the overseer directly")
            elif isinstance(node, ast.Call):
                name, first = _call_name(node), _first_text(node)
                if name in ("importorskip", "import_module", "__import__", "find_spec") and first is not None and _overseer_name(first) \
                        and not (helper and first in PUBLIC_MODULES):
                    bad.append(f"{_rel(path)}:{node.lineno}: {name}({first!r})")
                if name == "overseer_module" and first is not None and first not in PUBLIC_MODULES:  # any other name raises (tested)
                    bad.append(f"{_rel(path)}:{node.lineno}: overseer_module({first!r})")
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant) and node.right.value == "overseer":
                bad.append(f"{_rel(path)}:{node.lineno}: a path into overseer/")
    assert not bad, bad
    # the helper imports the overseer with pytest.importorskip only, and only its public modules
    calls = [(c.lineno, _call_name(c), _first_text(c)) for c in ast.walk(ast.parse(HELPER.read_text(encoding="utf-8"))) if isinstance(c, ast.Call)
             and _call_name(c) == "importorskip"]
    assert calls and all(first in PUBLIC_MODULES or first == "name" or first is None for _l, _n, first in calls), calls
    assert all(not part.startswith("_") for m in PUBLIC_MODULES for part in m.split("."))


# ============================================================================================ the whole suite (H1 to H10)
_IMPORTED_BY_NAME = ("import_module", "__import__")


def _unguarded_overseer_imports_in(source: str) -> list[str]:
    """Where a module's source imports the overseer unguarded: a plain ``import``/``from`` of ``epinoic_overseer`` or of its
    test package (at module level, which fails the module's collection where the overseer is not installed, or inside a
    test, which fails it at run time), ``importlib.import_module``/``__import__`` of it, or ``pytest.importorskip`` of it
    without a reason or without ``exc_type=ModuleNotFoundError``. The guarded form is ``pytest.importorskip(<module>,
    reason=..., exc_type=ModuleNotFoundError)`` (``overseer_attach``'s functions use it): under pytest 8.x the default
    ``exc_type`` is ``ImportError``, so an overseer that is installed but fails to import would be skipped as "not installed"
    instead of failing (round-9 clearance c2b, the router fixer's handoff; rewritten to this stricter rule)."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(_overseer_name(a.name) for a in node.names):
            out.append(f"{node.lineno}: import {', '.join(a.name for a in node.names)}")
        elif isinstance(node, ast.ImportFrom) and not node.level and _overseer_name(node.module or ""):
            out.append(f"{node.lineno}: from {node.module} import {', '.join(a.name for a in node.names)}")
        elif isinstance(node, ast.Call):
            name, first = _call_name(node), _first_text(node)
            if first is None or not _overseer_name(first):
                continue
            if name in _IMPORTED_BY_NAME:
                out.append(f"{node.lineno}: {name}({first!r})")
            elif name == "importorskip" and not any(k.arg == "reason" for k in node.keywords):
                out.append(f"{node.lineno}: importorskip({first!r}) without a reason")
            elif name == "importorskip" and not any(k.arg == "exc_type" and isinstance(k.value, ast.Name) and k.value.id == "ModuleNotFoundError"
                                                    for k in node.keywords):
                out.append(f"{node.lineno}: importorskip({first!r}) without exc_type=ModuleNotFoundError")
    return out


def test_every_import_of_the_overseer_in_the_translator_tests_is_guarded():
    """The whole suite (not only the core packages'): no module of ``tests/`` imports the overseer unguarded, so where it
    is not installed a test that needs it is skipped with the reason and the module beside it still collects and runs."""
    found = {_rel(p): v for p in _py_files() if (v := _unguarded_overseer_imports_in(p.read_text(encoding="utf-8")))}
    assert not found, found


def test_the_guard_rule_reads_every_unguarded_form():
    """Controls: the reader of the rule above names each unguarded form, and none of the guarded ones."""
    for src in ("from epinoic_overseer import TransferAuditor\n", "import epinoic_overseer\n", "import epinoic_overseer.port as P\n",
                "def f():\n    from epinoic_overseer.port import connect\n", "def f():\n    import epinoic_overseer\n",
                "import importlib\nm = importlib.import_module('epinoic_overseer.pack')\n", "m = __import__('epinoic_overseer')\n",
                "import pytest\nm = pytest.importorskip('epinoic_overseer.contracts')\n", "from overseer_tests.conftest import KEY\n",
                "import pytest\nm = pytest.importorskip('epinoic_overseer.contracts', reason='x')\n",
                "import pytest\nm = pytest.importorskip('epinoic_overseer.contracts', reason='x', exc_type=ImportError)\n"):
        assert _unguarded_overseer_imports_in(src), src
    for src in ("import pytest\nm = pytest.importorskip('epinoic_overseer.contracts', reason='x', exc_type=ModuleNotFoundError)\n",
                "from ..overseer_attach import overseer\n",
                "x = overseer().TransferAuditor\n", "from epinoic_logic.integration import overseer_port\n",
                "import importlib.util\nimportlib.util.find_spec('epinoic_overseer')\n", "NAMES = ('epinoic_overseer', 'overseer_tests')\n"):
        assert not _unguarded_overseer_imports_in(src), src


def _junit_outcomes(xml_path: Path) -> dict[str, tuple[str, str]]:
    """``{node id: (outcome, skip message)}`` from a pytest JUnit XML report (outcome: passed, skipped, xfailed, failed,
    error). The classname is the module's dotted path, then any test classes (``tests.e2e.test_x.TestY``)."""
    import xml.etree.ElementTree as ET

    out: dict[str, tuple[str, str]] = {}
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        parts = case.get("classname", "").split(".")
        at = next((i for i, part in reversed(list(enumerate(parts))) if part.startswith("test_")), len(parts) - 1)
        node = "::".join(["/".join(parts[:at + 1]) + ".py", *parts[at + 1:], case.get("name") or ""])
        outcome, message = "passed", ""
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[child.tag]
                if outcome == "skipped" and child.get("type") == "pytest.xfail":
                    outcome = "xfailed"
                message = child.get("message") or ""
                if outcome in ("failed", "error"):
                    break
        out[node] = (outcome, message)
    return out


@pytest.mark.timeout(1200)
def test_the_tests_that_failed_without_the_overseer_now_pass_or_are_skipped_with_the_reason(tmp_path):
    """With the overseer off the path (:data:`ABSENT`), every test of :data:`FAILED_WITHOUT_THE_OVERSEER` passes or is
    skipped with ``overseer_attach.REASON``; none fails or errs, and the translator's own (:data:`RUN_WITHOUT_THE_OVERSEER`)
    pass: the arena harness's rounds run, recording the overseer's passes as not run, and a turn on the test double of the
    overseer port runs while its ``[real]`` twin is skipped."""
    report = tmp_path / "absent.xml"
    proc = _pytest(ABSENT, "-q", "-rfE", f"--junitxml={report}", *FAILED_WITHOUT_THE_OVERSEER)
    outcomes = _junit_outcomes(report)
    bad = {n: o for n, o in outcomes.items() if o[0] in ("failed", "error")}
    assert proc.returncode == 0 and not bad, (bad, proc.stdout[-4000:], proc.stderr[-2000:])
    assert len(outcomes) > 79, len(outcomes)  # at least the 73 failed and 6 erred before, and the tests beside them
    skipped = {n: m for n, (o, m) in outcomes.items() if o == "skipped"}
    assert skipped and all(REASON in m for m in skipped.values()), {n: m for n, m in skipped.items() if REASON not in m}
    for wanted in RUN_WITHOUT_THE_OVERSEER:
        mine = {n: o for n, (o, _m) in outcomes.items() if n == wanted or (wanted.endswith("::") and n.startswith(wanted))}
        assert mine and all(o == "passed" for o in mine.values()), (wanted, mine)
    # the [real] parameters of the turn tests attach the overseer's port adapter: each skipped, never failed
    real = [n for n in outcomes if n.startswith("tests/integration/test_turn_") and "[real" in n]
    assert len(real) >= 47 and all(outcomes[n][0] == "skipped" for n in real), [n for n in real if outcomes[n][0] != "skipped"]


@pytest.mark.timeout(1200)
def test_the_tests_that_imported_the_overseers_test_package_pass_with_it_installed_without_its_tests(tmp_path):
    """With the overseer installed as a package but its tests absent (:data:`INSTALLED_WITHOUT_TESTS`, the split's other
    state), the tests that imported ``overseer_tests`` before (:data:`TEST_PACKAGE_IMPORTERS`) pass: they reach only the
    overseer's public package API now."""
    overseer()  # where the overseer is not installed there is nothing to run them with (the test above holds instead)
    report = tmp_path / "installed.xml"
    proc = _pytest(INSTALLED_WITHOUT_TESTS, "-q", "-rfEs", f"--junitxml={report}", *TEST_PACKAGE_IMPORTERS)
    outcomes = _junit_outcomes(report)
    assert proc.returncode == 0 and outcomes and all(o == "passed" for o, _m in outcomes.values()), (outcomes, proc.stdout[-4000:], proc.stderr[-2000:])
    for wanted in TEST_PACKAGE_IMPORTERS:
        assert any(n == wanted or n.startswith(wanted.split("::")[0]) for n in outcomes), wanted


def test_an_overseer_that_is_installed_but_fails_to_import_fails_the_test_never_skips_it(tmp_path):
    """The router fixer's handoff (round-9 clearance c2b): an overseer that IS installed but fails to import (a module of it raising
    ImportError, a broken install) must fail the tests that attach it, never be skipped as "not installed" (pytest older than 9
    catches every ImportError in ``importorskip`` unless ``exc_type=ModuleNotFoundError`` is passed). A scratch package named
    ``epinoic_overseer`` whose ``__init__`` raises ImportError, first on the path: ``overseer_attach.overseer()`` raises; with no
    such package (and the real one blocked) the same call skips with the reason."""
    broken = tmp_path / "broken" / "epinoic_overseer"
    broken.mkdir(parents=True)
    (broken / "__init__.py").write_text("raise ImportError('a module of the overseer failed to import')\n")
    code = ("import sys, pytest; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]);\n"
            "from tests import overseer_attach as oa\n"
            "try:\n    oa.overseer()\nexcept pytest.skip.Exception as e:\n    print('SKIPPED', e)\nexcept ImportError as e:\n    print('FAILED', e)\n")
    out = subprocess.run([sys.executable, "-c", code, str(tmp_path / "broken"), str(ROOT)], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert out.stdout.strip().startswith("FAILED") and "failed to import" in out.stdout, (out.stdout[-400:], out.stderr[-400:])
    absent = ("import sys, importlib.abc, pytest; sys.path.insert(0, sys.argv[1])\n"
              "class R(importlib.abc.MetaPathFinder):\n    def find_spec(self, n, p=None, t=None):\n"
              "        if n.partition('.')[0] == 'epinoic_overseer':\n            raise ModuleNotFoundError(n, name=n)\n        return None\n"
              "sys.meta_path.insert(0, R())\nfrom tests import overseer_attach as oa\n"
              "try:\n    oa.overseer()\nexcept pytest.skip.Exception as e:\n    print('SKIPPED', e)\n")
    out2 = subprocess.run([sys.executable, "-c", absent, str(ROOT)], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert out2.stdout.strip().startswith("SKIPPED"), (out2.stdout[-400:], out2.stderr[-400:])
