"""The arena harness runs a round where the overseer sub-project is not installed (``scripts/arena/run_arena.py``; the
handoff fixer of the architecture review after arena round 8, core handoff H9: "translator never imports overseer",
"standalone split").

The harness is the translator's: the genuine pass, the mutations, the syntheses and every measure (transport, fixture
coverage, translation fidelity, claim counts) are the translator's own and never depend on the overseer. Two passes are
the overseer's: the delivery pass (its delivery policy on an audited hub) and the revision pass (its transfer auditor).
Before the fix the delivery pass imported the overseer unguarded, so every round ended in ``ModuleNotFoundError`` where
it was not installed (``tests/e2e/test_arena_measures.py``, ``tests/integration/test_fixture_parity.py`` and the STEM
round tests all failed there). Now, where the overseer is not installed, the round runs and both passes are recorded as
NOT RUN with the reason (``run_arena.OVERSEER_NOT_INSTALLED``), in results.json, in summary.md and on the command line,
exactly as a pass switched off is: a pass not run is never shown as run, and the transport counts are the same as with
the overseer.

"Not installed" is made here as the translator's suite sees it after the split: every module of ``epinoic_overseer``
unimportable in this process (``sys.modules`` entries of None, restored after each test), or a finder that refuses the
name. No model is called and no network is touched.
"""
from __future__ import annotations

import importlib.abc
import json
import sys

import pytest

from ..overseer_attach import overseer
from .test_arena_measures import HISTORY_ITEM, TASK, _fixture, _round, ra


def _transport(out: dict) -> tuple:
    return (out["transmissions"], out["functional"], json.dumps(out["by_variant"], sort_keys=True), len(out["records"]))


def _not_installed(monkeypatch) -> None:
    """Make the overseer unimportable in this process, as where it is not installed (restored after the test)."""
    for name in [n for n in list(sys.modules) if n.partition(".")[0] == "epinoic_overseer"] + ["epinoic_overseer"]:
        monkeypatch.setitem(sys.modules, name, None)


def _round_dir(d, *, feedback: bool = False):
    (d / "specialists").mkdir(parents=True)
    (d / "specialists" / f"{TASK}.json").write_text(json.dumps(HISTORY_ITEM))
    (d / "translations").mkdir()
    (d / "translations" / f"{TASK}.json").write_text(json.dumps({"report_id": f"rep-{TASK}-0", "claims": {"h1.1": _fixture("h1.1")}}))
    if feedback:  # a round that recorded the feedback its specialists read: the revision pass would run
        (d / ra.FEEDBACK_DIR).mkdir()
    return d


def test_the_harness_locates_the_overseer_without_importing_it(monkeypatch):
    """``overseer_installed`` locates the package (``importlib.util.find_spec``), never imports it; an unimportable name, or
    a finder that refuses it (as the translator's own test of the split installs one), is an overseer not installed."""
    if ra.overseer_installed():  # as in this repository: the sub-project is on the path
        assert overseer().__name__ == "epinoic_overseer"
    _not_installed(monkeypatch)
    assert ra.overseer_installed() is False

    class Refuses(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.partition(".")[0] == "epinoic_overseer":
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None
    monkeypatch.delitem(sys.modules, "epinoic_overseer")
    monkeypatch.setattr(sys, "meta_path", [Refuses(), *sys.meta_path])
    assert ra.overseer_installed() is False


def test_where_the_overseer_is_not_installed_a_round_runs_and_says_both_of_its_passes_were_not_run(tmp_path, monkeypatch, capsys):
    """The round as it runs here (with the overseer when it is installed), then the same round where it is not, through the
    command line: no record fails or errs, the transport counts are the same, and the delivery pass and the revision pass
    are each recorded as not run with the reason, never as a pass that decided nothing."""
    with_it = _round(tmp_path / "with", {"claims": {"h1.1": _fixture("h1.1")}})
    _not_installed(monkeypatch)
    assert ra.overseer_installed() is False
    rd = _round_dir(tmp_path / "without", feedback=True)
    assert ra.main([str(rd)]) == 0  # never a ModuleNotFoundError that ends the round
    printed = capsys.readouterr().out
    out = json.loads((rd / "results.json").read_text())
    assert not out["failures"] and all(r.get("functional") and not r.get("error") for r in out["records"])
    assert _transport(out) == _transport(with_it)  # no transport count depends on the overseer's passes
    assert out["deliveries"] == {"skipped": ra.OVERSEER_NOT_INSTALLED, "tasks": [], "by_mode": {}, "errors": []}
    assert out["revisions"] == {"skipped": ra.OVERSEER_NOT_INSTALLED, "tasks": [], "checks": [], "errors": []}
    summary = (rd / "summary.md").read_text()
    assert f"## Delivery decisions\n\n(not run: {ra.OVERSEER_NOT_INSTALLED})" in summary
    assert f"## Specialist revisions\n\n(not run: {ra.OVERSEER_NOT_INSTALLED})" in summary
    assert f"delivery decisions (a separate measure): not run ({ra.OVERSEER_NOT_INSTALLED})" in printed
    assert "receipts identical to the genuine records': 0 of 0" not in printed  # a pass not run is not printed as one that decided nothing
    assert "the overseer sub-project (package epinoic_overseer) is not installed" in ra.OVERSEER_NOT_INSTALLED


def test_with_the_overseer_installed_the_passes_run_as_before(tmp_path):
    """The control: where the overseer is installed the delivery pass runs (a decision per genuine answer) and a round
    without feedback keeps its own reason for the revision pass."""
    overseer()  # skipped, with the reason, where it is not installed
    out = _round(tmp_path / "r", {"claims": {"h1.1": _fixture("h1.1")}})
    assert "skipped" not in out["deliveries"] and out["deliveries"]["decided"] == 1 and out["deliveries"]["errors"] == []
    assert out["revisions"]["skipped"].startswith("the round has no feedback/ directory")
