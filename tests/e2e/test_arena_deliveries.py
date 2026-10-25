"""The arena harness reports the delivery policy's decision for every genuine answer (``scripts/arena/run_arena.py``,
``docs/DELIVERY.md``): per task the delivery mode, the time to decision (with the translation and overseer times), the
candidates with their accuracy and the one chosen, in ``results.json`` and in ``summary.md``.

The delivery pass runs on a hub of its own, after the round's records are complete: it adds no record and moves no
transport count. On the command line no overseer agent is configured (the harness calls no model), so an answer whose
formal path does not complete is withheld; a test configures scripted overseer agents (no model, no network) to show the
fallback's candidates and choice."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

from epinoic_logic.overseer import load_pack
from epinoic_logic.overseer.export import export_pack

from ..overseer.delivery_support import ScriptedOverseer, silent
from .test_arena_measures import _GK, TASK, _fixture, _round, ra


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover - only hit if a test leaks a connection
        raise AssertionError("network access attempted in a unit test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    return load_pack(export_pack(tmp_path_factory.mktemp("export"), zip_archive=True).zip_path)


def _untranslatable(claim_id: str) -> dict:
    """The History fixture with the census premise added: the premises then restate the conclusion with no grounding of
    their own, so the validator refuses it (E112, INVALID_FORMALIZATION). A failed translation, not a fault of the answer."""
    fx = _fixture(claim_id)
    fx["problem"]["premises"].append({"id": "pr_million", "expr": {"op": "var", "name": "near_million"},
                                      "label": "London had close to a million inhabitants in 1801", "grounding": _GK, "materiality": "material"})
    return fx


def _with_overseer(tmp_path, translations, pack):
    (tmp_path / "specialists").mkdir(parents=True)
    from .test_arena_measures import HISTORY_ITEM
    (tmp_path / "specialists" / f"{TASK}.json").write_text(json.dumps(HISTORY_ITEM))
    (tmp_path / "translations").mkdir()
    (tmp_path / "translations" / f"{TASK}.json").write_text(json.dumps({"report_id": f"rep-{TASK}-0", **translations}))
    return ra.run_round(tmp_path, delivery_overseer={"pack": pack, "provider_factory": lambda agent_id: ScriptedOverseer(silent)})


def _transport(out: dict) -> tuple:
    return (out["transmissions"], out["functional"], json.dumps(out["by_variant"], sort_keys=True), len(out["records"]))


def test_every_genuine_answer_gets_a_delivery_decision_in_results_and_summary(tmp_path):
    out = _round(tmp_path / "r", {"claims": {"h1.1": _untranslatable("h1.1")}})
    d = out["deliveries"]
    assert d["policy"] == "delivery-v1" and d["translation_budget_s"] == 240.0 and d["min_selected_accuracy"] == 0.9
    assert d["overseer"].startswith("not configured") and d["errors"] == [] and d["decided"] == 1
    [t] = d["tasks"]
    assert t["file"] == f"{TASK}.json" and t["task_id"] == TASK and t["agent_id"] == "history-specialist"
    # a replay calls no fidelity reviewer, so the formal path never completes; with no overseer agent nothing is established
    assert t["mode"] == "withheld" and t["delivered"] is False and t["chosen"] is None
    assert t["formal"]["complete"] is False and any("h1.1" in r for r in t["formal"]["reasons"])
    assert t["time_to_decision_s"] >= t["translation_s"] >= 0 and t["overseer_s"] is None
    assert [c["agent_id"] for c in t["candidates"]] == ["history-specialist"] and t["candidates"][0]["chosen"] is False
    assert t["receipt_verifies"] is True and t["receipt_matches_genuine_record"] is True and d["receipts_matching_genuine_records"] == 1
    assert "not formally checked, not verified" in t["label"]
    # results.json on disk carries the same, and summary.md has the per-task table
    on_disk = json.loads((tmp_path / "r" / "results.json").read_text())
    assert on_disk["deliveries"]["tasks"][0]["mode"] == "withheld"
    summary = (tmp_path / "r" / "summary.md").read_text()
    assert "## Delivery decisions (delivery policy delivery-v1: 240 s translation budget" in summary
    assert "| task | mode | time to decision (s) | translation (s) | overseer (s) | candidates (accuracy) | chosen | why |" in summary
    row = next(line for line in summary.splitlines() if line.startswith(f"| {TASK}.json | withheld |"))
    assert "history-specialist 0/2" in row
    assert summary.index("## Delivery decisions") < summary.index("## Failures")


def test_with_overseer_agents_the_round_reports_the_candidates_and_the_chosen_one(tmp_path, pack):
    out = _with_overseer(tmp_path / "o", {"claims": {"h1.1": _untranslatable("h1.1")}}, pack)
    [t] = out["deliveries"]["tasks"]
    assert t["mode"] == "overseer_selected" and t["delivered"] and t["chosen"]["agent_id"] == "history-specialist"
    [c] = t["candidates"]
    assert c["chosen"] is True and c["accuracy_fraction"] == "2/2" and c["above_threshold"] and c["claims"]["accurate"] == 2
    assert t["overseer"]["ran"] and t["overseer"]["instances"] == ["overseer-pool-1"] and t["overseer_s"] is not None
    assert t["label"].startswith("OVERSEER-SELECTED (not formally checked, not verified)")
    row = next(line for line in (tmp_path / "o" / "summary.md").read_text().splitlines() if line.startswith(f"| {TASK}.json |"))
    assert "| overseer_selected |" in row and "history-specialist 2/2" in row and row.split("|")[7].strip() == "history-specialist"


def test_a_refuted_answer_is_withheld_with_its_score(tmp_path, pack):
    out = _with_overseer(tmp_path / "x", {"claims": {"h1.1": _fixture("h1.1")}}, pack)  # COUNTEREXAMPLE: the census is not a premise
    [t] = out["deliveries"]["tasks"]
    [c] = t["candidates"]
    assert t["mode"] == "withheld" and c["refuted"] and c["accuracy_fraction"] == "1/2" and c["above_threshold"] is False
    assert any("refuted" in r for r in t["formal"]["reasons"])


def test_the_delivery_pass_moves_no_transport_count(tmp_path, pack):
    plain = _round(tmp_path / "p", {"claims": {"h1.1": _untranslatable("h1.1")}})
    selected = _with_overseer(tmp_path / "s", {"claims": {"h1.1": _untranslatable("h1.1")}}, pack)
    assert _transport(plain) == _transport(selected)
    assert plain["functional"] == plain["transmissions"]
    assert {r["variant"] for r in plain["records"]} == {r["variant"] for r in selected["records"]}


def test_the_pass_never_goes_through_a_replaced_verifier(tmp_path, monkeypatch):
    """A harness that replaces the module's ``verify_claim`` (the contained harness's tampering hooks) changes the round's
    own pass only: the delivery pass verifies with the verifier bound at import, like its hub."""
    calls: list[str] = []

    def replaced(claim, report, translator, **kw):
        calls.append(claim.claim_id)
        return None  # the round's own pass gets no outcome at all
    monkeypatch.setattr(ra, "verify_claim", replaced)
    out = _round(tmp_path / "hook", {"claims": {"h1.1": _fixture("h1.1")}})
    [genuine] = [r for r in out["records"] if r["variant"] == "genuine"]
    assert "h1.1" in calls and genuine["outcomes"] == []
    [t] = out["deliveries"]["tasks"]
    [c] = [c for c in t["formal"]["claims"] if c["claim_id"] == "h1.1"]
    assert (c["translation_status"], c["display_status"], c["outcome"]) == ("TRANSLATED", "COUNTEREXAMPLE", "refuted")


def test_a_switched_off_pass_says_so_and_moves_nothing(tmp_path, monkeypatch):
    on = _round(tmp_path / "on", {"claims": {"h1.1": _untranslatable("h1.1")}})
    monkeypatch.setattr(ra, "DELIVERY_PASS", False)
    off = _round(tmp_path / "off", {"claims": {"h1.1": _untranslatable("h1.1")}})
    assert off["deliveries"]["skipped"].startswith("the delivery pass is switched off") and off["deliveries"]["tasks"] == []
    summary = (tmp_path / "off" / "summary.md").read_text()
    assert "## Delivery decisions" in summary and "(not run: the delivery pass is switched off" in summary
    assert _transport(on) == _transport(off)


def test_the_contained_harness_switches_the_pass_off_and_restores_it():
    scripts = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import ovs_harness as H

    aud = H.new_auditor(H.keyring_for("arena"))
    try:
        assert H.arena() is ra and ra.DELIVERY_PASS is True
        with H.audited_arena(aud):
            assert ra.DELIVERY_PASS is False
        assert ra.DELIVERY_PASS is True
    finally:
        aud.close()
