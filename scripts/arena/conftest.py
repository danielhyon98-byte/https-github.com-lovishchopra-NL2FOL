"""Session set-up of the arena's own tests (``scripts/arena/test_arena_rules.py``, run by path) for the meaning label
(meaning-check stage 2a, interface (a)): the same set-up ``tests/conftest.py`` gives the translator's suite.

1. ``pytest_configure`` installs the faithful fake (``selfcert_label.fakes.ReaderBackedLabeller``) through the one switch,
   ``selfcert_label.set_default_labeller``, before any fixture of any scope runs, and sets ``EPINOIC_ARENA_LABELLER`` to
   ``faithful``, so every hub the harness builds (in this process, and in a command-line run it starts as a subprocess) labels
   as the rule reader reads: every delivery decision is the reader's, as before the label was wired. It is never a label
   measurement. When the suite's own set-up already did this (``tests/`` collected in the same session), nothing is changed.
   ``pytest_unconfigure`` puts back only what this file changed.
2. A test marked ``real_labeller`` runs with the production default (the unconfigured labeller) and without
   ``EPINOIC_ARENA_LABELLER``; the label package's shared calls are emptied before each test.

Nothing here calls a provider or opens a connection.
"""
from __future__ import annotations

import os

import pytest

from epinoic_logic.selfcert_label import labellers as _labellers
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller

ARENA_LABELLER_ENV = "EPINOIC_ARENA_LABELLER"
REAL_LABELLER = "real_labeller"
_SESSION: dict = {}


def pytest_configure(config):
    config.addinivalue_line("markers", f"{REAL_LABELLER}: run with the production default labeller (UnconfiguredLabeller) and no "
                                       f"{ARENA_LABELLER_ENV}, in place of the faithful fake")
    if "installed" in _SESSION:
        return
    already = isinstance(_labellers.default_labeller(), ReaderBackedLabeller) and os.environ.get(ARENA_LABELLER_ENV) == "faithful"
    _SESSION["installed"] = not already
    if already:
        return
    _SESSION["labeller"] = _labellers.set_default_labeller(ReaderBackedLabeller())
    _SESSION["env"] = os.environ.get(ARENA_LABELLER_ENV)
    os.environ[ARENA_LABELLER_ENV] = "faithful"


def pytest_unconfigure(config):
    if not _SESSION.pop("installed", False):
        return
    _labellers.set_default_labeller(_SESSION.pop("labeller"))
    env = _SESSION.pop("env")
    if env is None:
        os.environ.pop(ARENA_LABELLER_ENV, None)
    else:
        os.environ[ARENA_LABELLER_ENV] = env


@pytest.fixture(autouse=True)
def _arena_label_per_test(request):
    """Empties the label package's shared calls; for a ``real_labeller`` test, the production default and no arena labeller."""
    _labellers.clear_shared_calls()
    if request.node.get_closest_marker(REAL_LABELLER) is None:
        yield
        return
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv(ARENA_LABELLER_ENV, raising=False)
        with _labellers.using_default_labeller(None):
            yield
