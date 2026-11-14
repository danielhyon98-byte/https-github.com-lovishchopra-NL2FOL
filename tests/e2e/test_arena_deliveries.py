"""The arena harness reports the delivery policy's decision for every genuine answer (``scripts/arena/run_arena.py``,
``docs/DELIVERY.md``): per task the delivery mode, the time to decision (with the translation and overseer times), the
candidates with their accuracy and the one chosen, in ``results.json`` and in ``summary.md``.

The delivery pass runs on a hub of its own, after the round's records are complete: it adds no record and moves no
transport count. On the command line no overseer agent is configured (the harness calls no model), so an answer whose
formal path does not complete is withheld; a test configures scripted overseer agents (no model, no network) to show the
fallback's candidates and choice.

Every test here drives the delivery pass, which is the overseer's delivery policy: each needs the overseer installed and
is skipped with ``overseer_attach.REASON`` where it is not (architecture review after arena round 8: the translator's
suite runs without the overseer; where it is not installed the harness records the pass as not run, which
``test_arena_without_the_overseer.py`` holds). The overseer is reached through its public package API only, never its
test package: the scripted overseer agents are written here on the translator's provider types."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from epinoic_logic.translate.contracts import ProviderInfo
from epinoic_logic.translate.providers.base import ProviderResponse

from ..overseer_attach import overseer
from .test_arena_measures import _GK, TASK, _fixture, _round, ra

#: The overseer's harness scripts in this repository (the contained harness, ``ovs_harness.py``); absent where the overseer
#: is installed as a package of its own after the split.
OVERSEER_SCRIPTS = Path(__file__).resolve().parents[2] / "overseer" / "scripts"


@pytest.fixture(autouse=True)
def needs_the_overseer():
    """Every test here drives the overseer's delivery policy: skipped, with the reason, where it is not installed."""
    overseer()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover - only hit if a test leaks a connection
        raise AssertionError("network access attempted in a unit test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    ov = overseer()
    return ov.load_pack(ov.export_pack(tmp_path_factory.mktemp("export"), zip_archive=True).zip_path)


class ScriptedOverseer:
    """An overseer completion provider whose reply is computed from the dossier it receives (test code reading data,
    never a model): the overseer suite's scripted agent (``delivery_support.ScriptedOverseer`` without its fake clock),
    written here so that this module needs the overseer's public package only, never its test package."""

    name = "scripted"

    def __init__(self, reply: Callable[[dict], Any]) -> None:
        self.reply = reply
        self.calls: list[str] = []

    def complete(self, system: str, user: str, *, prompt_version: str) -> ProviderResponse:
        lines = user.split("\n")
        assert lines[0] == "<<<DATA dossier>>>" and lines[-1] == "<<<END dossier>>>"
        d = json.loads("\n".join(lines[1:-1]))
        self.calls.append(d["agent_id"])
        out = self.reply(d)
        if isinstance(out, Exception):
            raise out
        text = out if isinstance(out, str) else json.dumps(out)
        return ProviderResponse(raw_text=text, info=ProviderInfo(provider_name=self.name, prompt_version=prompt_version, temperature=0.0))


def silent(d: dict) -> dict:
    """A well-formed verdict on the dossier ``d`` that reviews every transfer and accuses nothing (the overseer suite's
    ``delivery_support.silent``)."""
    return {"contract": d["verdict_contract"], "pack": dict(d["pack"]), "verdict_id": f"v-{d['agent_id']}", "agent_id": d["agent_id"],
            "task_id": d["task"]["task_id"], "dossier_sha256": d["dossier_sha256"], "lens": d["lens"],
            "transfers_reviewed": [t["message_id"] for t in d["transfers"] if t["message_id"]], "accusations": [], "engine_statements": [],
            "notes": ""}


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
    # integration step: the History answer's receipt carries CORE-SRC-003 at warning (unchecked_source), a risk signal that
    # sends the dossier to two independent instances (rewritten from one instance to the stricter planning rule)
    assert t["overseer"]["ran"] and t["overseer"]["instances"] == ["overseer-pool-1", "overseer-pool-2"] and t["overseer_s"] is not None
    assert t["label"].startswith("OVERSEER-SELECTED (not formally checked, not verified)")
    row = next(line for line in (tmp_path / "o" / "summary.md").read_text().splitlines() if line.startswith(f"| {TASK}.json |"))
    assert "| overseer_selected |" in row and "history-specialist 2/2" in row and row.split("|")[7].strip() == "history-specialist"


def _refuted(claim_id: str) -> dict:
    """A GENUINE refutation of the History claim (round-9 clearance c2b, the overseer's handoff 3): the fixture's encoding with a
    premise that denies the census figure ("London had nowhere near a million inhabitants"), so the COUNTEREXAMPLE constrains every
    conclusion symbol and carries no coverage warning (W110/W111); the plain fixture leaves ``near_million`` constrained by no premise
    (W111), a counterexample the delivery policy reads as a gap of the translation (rule coverage-gap), never as a refutation."""
    fx = _fixture(claim_id)
    fx["problem"]["premises"].append({"id": "pr_not_million", "expr": {"op": "not", "arg": {"op": "var", "name": "near_million"}},
                                      "label": "London had nowhere near a million inhabitants", "grounding": _GK, "materiality": "material"})
    return fx


def test_a_refuted_answer_is_withheld_with_its_score(tmp_path, pack):
    out = _with_overseer(tmp_path / "x", {"claims": {"h1.1": _refuted("h1.1")}}, pack)  # COUNTEREXAMPLE: the encoding denies the census figure
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
    out = _round(tmp_path / "hook", {"claims": {"h1.1": _refuted("h1.1")}})
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
    if not OVERSEER_SCRIPTS.is_dir():  # an overseer installed as a package of its own (after the split) ships no harness here
        pytest.skip("the overseer's harness scripts (overseer/scripts/) are not in this checkout: the overseer sub-project was split off")
    scripts = OVERSEER_SCRIPTS
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
