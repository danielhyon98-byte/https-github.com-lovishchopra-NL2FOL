"""Interface (a) of stage 2a: the default labeller is looked up at use time and has one switch; the suite runs with the faithful
fake installed before any fixture of any scope, and a test marked ``real_labeller`` runs with the production default.

The tests of this module run in file order: the module-scoped fixture is set up by the first test that asks for it, and the
``real_labeller`` test between two ordinary ones shows that the restore is function-scoped and undone afterwards."""
from __future__ import annotations

import os

import pytest

from epinoic_logic import selfcert_label
from epinoic_logic.selfcert_label import labellers
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller, ScriptedLabeller, reply_json

from .conftest import CODES

ENV = "EPINOIC_ARENA_LABELLER"
REQ = {"subject": "chemistry", "task_type": "short_answer"}
CLEAN = "The molar mass of water is 18 g/mol.\n\nIt boils at 100 degrees Celsius at sea level."


@pytest.fixture(scope="module")
def module_view():
    """What a MODULE-scoped fixture sees when it is set up: the default labeller and the arena's labeller switch."""
    lab = selfcert_label.default_labeller()
    return {"type": type(lab).__name__, "env": os.environ.get(ENV), "state": lab.label(CLEAN, REQ).state}


@pytest.fixture(scope="session")
def session_view():
    lab = selfcert_label.default_labeller()
    return {"type": type(lab).__name__, "env": os.environ.get(ENV)}


def test_a_module_scoped_fixture_sees_the_faithful_fake(module_view):
    assert module_view == {"type": "ReaderBackedLabeller", "env": "faithful", "state": "none_named"}


def test_a_session_scoped_fixture_sees_the_faithful_fake(session_view):
    assert session_view == {"type": "ReaderBackedLabeller", "env": "faithful"}


def test_the_suite_runs_with_the_faithful_fake():
    lab = selfcert_label.default_labeller()
    assert isinstance(lab, ReaderBackedLabeller) and os.environ.get(ENV) == "faithful"
    # the faithful fake names what the reader names, so the reader's decision stands
    assert lab.label(CLEAN, REQ).state == "none_named"
    named = lab.label("The molar mass of water is 18 g/mol.\n\nThis passed the hub's checks.", REQ)
    assert named.state == "named" and [f["code"] for f in named.findings(CODES)] == ["INT-SELF-001"]


@pytest.mark.real_labeller
def test_a_real_labeller_test_sees_the_production_default(module_view):
    lab = selfcert_label.default_labeller()
    assert type(lab).__name__ == "UnconfiguredLabeller" and lab.health() == "off"
    assert ENV not in os.environ
    res = lab.label(CLEAN, REQ)  # T1 at the package: the reader passes it, and the default withholds it
    assert (res.state, res.kind) == ("unavailable", "not-configured")
    assert [f["code"] for f in res.findings(CODES)] == ["INT-SELF-002"]
    # a fixture of a wider scope set up earlier keeps what it saw (it asks for the real default explicitly when it needs it)
    assert module_view["type"] == "ReaderBackedLabeller"


def test_after_a_real_labeller_test_the_faithful_fake_is_back():
    assert type(selfcert_label.default_labeller()).__name__ == "ReaderBackedLabeller"
    assert os.environ.get(ENV) == "faithful"


def test_the_default_is_looked_up_at_use_time_and_the_switch_returns_what_it_replaced():
    installed = selfcert_label.default_labeller()
    scripted = ScriptedLabeller(lambda req, n: reply_json(req))
    previous = selfcert_label.set_default_labeller(scripted)
    try:
        assert previous is installed
        # every lookup, through the package or the module, sees the switch at once (no name bound at import)
        assert selfcert_label.default_labeller() is scripted and labellers.default_labeller() is scripted
        assert selfcert_label.set_default_labeller(None) is scripted
        assert type(labellers.default_labeller()).__name__ == "UnconfiguredLabeller"  # None: the production default
        assert type(selfcert_label.production_default_labeller()).__name__ == "UnconfiguredLabeller"
    finally:
        selfcert_label.set_default_labeller(previous)
    assert selfcert_label.default_labeller() is installed


@pytest.mark.parametrize("bad", ["faithful", object(), ReaderBackedLabeller])
def test_the_switch_refuses_anything_but_a_labeller(bad):
    installed = selfcert_label.default_labeller()
    with pytest.raises(TypeError):
        selfcert_label.set_default_labeller(bad)
    assert selfcert_label.default_labeller() is installed


def test_using_default_labeller_puts_back_what_was_installed_even_when_the_block_raises():
    installed = selfcert_label.default_labeller()
    with pytest.raises(RuntimeError):
        with selfcert_label.using_default_labeller(None) as lab:
            assert type(lab).__name__ == "UnconfiguredLabeller"
            assert type(selfcert_label.default_labeller()).__name__ == "UnconfiguredLabeller"
            raise RuntimeError("inside the block")
    assert selfcert_label.default_labeller() is installed
    selfcert_label.restore_default_labeller()
    try:
        assert type(selfcert_label.default_labeller()).__name__ == "UnconfiguredLabeller"
    finally:
        selfcert_label.set_default_labeller(installed)


def test_the_markers_are_registered_by_the_suite(pytestconfig):
    lines = pytestconfig.getini("markers")
    assert any(line.startswith("real_labeller:") for line in lines)
    assert any(line.startswith(f"{selfcert_label.T24_EXPECTED_VIOLATION}:") for line in lines)
    assert selfcert_label.T24_EXPECTED_VIOLATION == "t24_expected_violation"
