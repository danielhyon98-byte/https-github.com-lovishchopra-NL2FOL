"""Test set-up of the combinator sub-project.

The combinator imports only the standard library and its own package. Most of its tests need nothing else. Its
conformance tests (``test_conformance.py``) compare it with the translator's own combinator port
(``epinoic_logic.integration.combinator_port``, which the hub's contract is published from): inside the translator
repository they use that repository's ``src/`` and must run; a copy of the sub-project outside it runs them against the
translator package installed in its environment, and skips them (saying so) when none is installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
TRANSLATOR_SRC = PROJECT.parent / "src"
#: True when this sub-project sits in the translator repository (its port module beside it).
INSIDE_TRANSLATOR = (TRANSLATOR_SRC / "epinoic_logic" / "integration" / "combinator_port.py").is_file()

sys.path.insert(0, str(PROJECT / "src"))
if INSIDE_TRANSLATOR:
    sys.path.insert(1, str(TRANSLATOR_SRC))


def _translator_importable() -> bool:
    try:
        import epinoic_logic.integration.combinator_port  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.fixture(scope="session")
def kit():
    """The translator's combinator port. Inside the translator repository its absence is a failure, never a skip."""
    if not _translator_importable():
        if INSIDE_TRANSLATOR:
            pytest.fail("inside the translator repository the conformance tests must run, but its src/ is not importable")
        pytest.skip("the translator package (epinoic_logic) is not installed: the conformance tests against its combinator port need it")
    from epinoic_logic.integration import combinator_port
    return combinator_port


# ============================================================================================ the meaning label (stage 2a)
# Interface (a) of the meaning check, stage 2a: where the translator is importable (inside its repository, or installed), the
# suite's tests that cross the translator's hub run with the faithful fake as the default labeller (``ReaderBackedLabeller``: it
# names exactly what the translator's rule reader names, so every delivery decision is the reader's, as before the label was wired;
# never a label measurement), installed through the one switch before any fixture runs, with ``EPINOIC_ARENA_LABELLER=faithful``; a
# test marked ``real_labeller`` runs with the production default (every answer the reader passes is withheld, not-configured). T24
# (``check_t24``) is applied to every transmission receipt and channel event those tests produce. All of it through the
# translator's public API (``epinoic_logic.api.label``, ``epinoic_logic.api.channel``). Where the translator is not importable
# nothing here runs: the sub-project's isolated mode is unchanged (its package never imports the translator).
import collections as _collections
import os as _os

ARENA_LABELLER_ENV = "EPINOIC_ARENA_LABELLER"
REAL_LABELLER = "real_labeller"
T24_EXPECTED_VIOLATION = "t24_expected_violation"
_LABEL_SESSION: dict = {}


def _label_api():
    """The translator's public label API, or None when the translator (or a translator with API 1.5) is not importable."""
    try:
        from epinoic_logic.api import label
        label.default_labeller  # noqa: B018 - resolves the name (a translator before API 1.5 has none)
        return label
    except (ImportError, AttributeError):
        return None


def pytest_configure(config):
    config.addinivalue_line("markers", f"{REAL_LABELLER}: run with the translator's production default labeller (UnconfiguredLabeller)")
    config.addinivalue_line("markers", f"{T24_EXPECTED_VIOLATION}: the test builds a record that violates T24 on purpose and asserts that "
                                       "check_t24 detects it")
    api = _label_api()
    if api is None or "installed" in _LABEL_SESSION:
        return
    if isinstance(api.default_labeller(), api.ReaderBackedLabeller):
        _LABEL_SESSION["installed"] = False
    else:
        _LABEL_SESSION["previous"] = api.set_default_labeller(api.ReaderBackedLabeller())
        _LABEL_SESSION["installed"] = True
    _LABEL_SESSION["env"] = _os.environ.get(ARENA_LABELLER_ENV)
    _os.environ[ARENA_LABELLER_ENV] = "faithful"
    _T24.install(api)


def pytest_unconfigure(config):
    api = _label_api()
    if api is None or "installed" not in _LABEL_SESSION:
        return
    _T24.uninstall()
    if _LABEL_SESSION.pop("installed"):
        api.set_default_labeller(_LABEL_SESSION.pop("previous", None))
    env = _LABEL_SESSION.pop("env", None)
    if env is None:
        _os.environ.pop(ARENA_LABELLER_ENV, None)
    else:
        _os.environ[ARENA_LABELLER_ENV] = env


@pytest.fixture(autouse=True)
def _selfcert_label_per_test(request):
    """For a ``real_labeller`` test (translator importable): the production default labeller, put back afterwards."""
    api = _label_api() if request.node.get_closest_marker(REAL_LABELLER) is not None else None
    if api is None:
        yield
        return
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv(ARENA_LABELLER_ENV, raising=False)
        previous = api.set_default_labeller(None)
        try:
            yield
        finally:
            api.set_default_labeller(previous)


class _T24Hook:
    """Records the translator's receipts and channel events made while a phase of a test runs, and checks each with ``check_t24``."""

    def __init__(self):
        self.active = False
        self.produced: list = []
        self._patched: list = []
        self._check = None
        self.checked: "_collections.Counter[str]" = _collections.Counter()

    def install(self, api) -> None:
        from epinoic_logic.api.channel import ChannelEvent as _Event, TransmissionReceipt as _Receipt
        self._check = api.check_t24
        for cls, pydantic in ((_Receipt, True), (_Event, False)):
            original_init = cls.__dict__.get("__init__")
            base_init = cls.__init__

            def init(obj, *a, _base=base_init, **k):
                _base(obj, *a, **k)
                if self.active:
                    self.produced.append(obj)
            cls.__init__ = init
            self._patched.append((cls, "__init__", original_init))
            if pydantic:
                original_copy = cls.__dict__.get("model_copy")
                base_copy = cls.model_copy

                def model_copy(obj, *a, _base=base_copy, **k):
                    out = _base(obj, *a, **k)
                    if self.active:
                        self.produced.append(out)
                    return out
                cls.model_copy = model_copy
                self._patched.append((cls, "model_copy", original_copy))

    def uninstall(self) -> None:
        for cls, name, original in reversed(self._patched):
            if original is None:
                delattr(cls, name)
            else:
                setattr(cls, name, original)
        self._patched.clear()

    def phase(self, item, when: str):
        self.produced, self.active = [], self._check is not None
        try:
            result = yield
        finally:
            self.active = False
            produced, self.produced = self.produced, []
        found: list[str] = []
        for obj in produced:
            self.checked[type(obj).__name__] += 1
            found += [f"{type(obj).__name__}: {v}" for v in self._check(obj)]
        found = list(dict.fromkeys(found))
        if found and item.get_closest_marker(T24_EXPECTED_VIOLATION) is None:
            raise AssertionError(f"T24 ({when}): {len(found)} violation(s) in what this test produced:\n  " + "\n  ".join(found[:20]))
        return result


_T24 = _T24Hook()


def pytest_terminal_summary(terminalreporter):
    if _T24.checked:
        counts = ", ".join(f"{n} {k}" for k, n in sorted(_T24.checked.items()))
        terminalreporter.write_line(f"T24 (combinator suite, check_t24): checked {counts}")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    return (yield from _T24.phase(item, "set-up"))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    return (yield from _T24.phase(item, "call"))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    return (yield from _T24.phase(item, "tear-down"))
