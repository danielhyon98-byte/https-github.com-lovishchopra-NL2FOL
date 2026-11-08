"""The arena harness's specialist revisions (``scripts/arena/run_arena.py``, ``scripts/arena/revision_feedback.py``; design
section 53 of ``overseer/docs/OVERSEER_DESIGN.md``).

``revision_feedback.py`` writes, for every genuine answer of a round, the infrastructure's feedback as the router keeps it
(``feedback/<task>.json``): whether a revision request was issued and, if not, why; the signed block; the exact message
the specialist reads and its digest; the flaws. When the round also holds the specialists' revisions
(``revisions/<task>.json``), the harness re-issues every request, compares it with what was recorded, delivers each
revision in reply to it and reports the outcome in a section of its own, apart from the transport, fidelity and coverage
measures: the headline rate never moves. No model is called and no network is touched."""
from __future__ import annotations

import hashlib
import json
import shutil
import socket

import pytest

from .test_arena_measures import HISTORY_ITEM, ra

PH_TASK = "ph-x1"
PHYSICS_ITEM = {
    "task_id": PH_TASK, "subject": "Physics", "agent_id": "physics-specialist", "task_type": "short_answer",
    "question": "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.", "supplied_texts": [],
    "response_text": "The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². The acceleration is therefore 6.0 m s⁻².",
}
PH_CORRECTED = ("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻². "
                "The acceleration is therefore 5.0 m s⁻².")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover - only hit if a test leaks a connection
        raise AssertionError("network access attempted in a unit test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _round(d):
    (d / "specialists").mkdir(parents=True)
    for item in (PHYSICS_ITEM, HISTORY_ITEM):
        (d / "specialists" / f"{item['task_id']}.json").write_text(json.dumps(item))
    return d


def _revise(d, task_id: str, text: str, *, read: str | None = None):
    fb = json.loads((d / ra.FEEDBACK_DIR / f"{task_id}.json").read_text())
    (d / ra.REVISIONS_DIR).mkdir(exist_ok=True)
    (d / ra.REVISIONS_DIR / f"{task_id}.json").write_text(json.dumps({
        "task_id": task_id, "agent_id": fb["agent_id"], "feedback_sha256": read or fb["rendered_sha256"], "response_text": text, "elapsed_s": 2.5,
        "input_tokens": 900, "output_tokens": 120}))


def _transport(out: dict) -> tuple:
    return (out["transmissions"], out["functional"], json.dumps(out["by_variant"], sort_keys=True), len(out["records"]))


def test_feedback_files_hold_what_the_specialist_reads_and_why_an_answer_got_none(tmp_path):
    rd = _round(tmp_path / "r")
    out = ra.revision_feedback(rd)
    assert out["issued"] == 1 and out["by_reason"] == {"issued": 1, "no_actionable_flaw": 1}
    ph = json.loads((rd / ra.FEEDBACK_DIR / f"{PH_TASK}.json").read_text())
    hi = json.loads((rd / ra.FEEDBACK_DIR / f"{HISTORY_ITEM['task_id']}.json").read_text())
    assert set(ph) == set(hi) == set(ra.FEEDBACK_FILE_KEYS)
    assert ph["issued"] and ph["reason"] == "issued" and (ph["round"], ph["max_rounds"]) == (1, 2)
    assert [(f["code"], f["rule"], f["basis"], f["flaw_class"]) for f in ph["flaws"]] == [("INT-SUBJ-001", "calc.does_not_hold", "engine", "correctness")]
    assert hashlib.sha256(ph["rendered"].encode("utf-8")).hexdigest() == ph["rendered_sha256"] == ph["block"]["rendered_sha256"]
    assert ph["block"]["signature_key_id"] == "overseer-feedback" and ph["advisory"] == 0
    assert ph["rendered"].startswith("Revision request 1 of 2 from the tutoring system") and "INT-" not in ph["rendered"]  # no finding code reaches it
    assert not hi["issued"] and hi["reason"] == "no_actionable_flaw" and hi["flaws"] == [] and hi["rendered"] is None and hi["block"] is None


def test_a_round_with_revisions_reports_them_apart_and_the_headline_rate_does_not_move(tmp_path):
    rd = _round(tmp_path / "r")
    plain = ra.run_round(shutil.copytree(rd, tmp_path / "plain"))
    assert plain["revisions"]["skipped"].startswith("the round has no feedback/ directory")
    ra.revision_feedback(rd)
    _revise(rd, PH_TASK, PH_CORRECTED)
    out = ra.run_round(rd)
    assert _transport(out) == _transport(plain)  # the revision pass adds no record and moves no transport count
    rv = out["revisions"]
    assert (rv["answers_checked"], rv["feedback_issued"], rv["negative_controls"], rv["answers_revised"]) == (2, 1, 1, 1)
    [t] = rv["tasks"]
    assert t["delivered"] and t["feedback_read"] and [(b["code"], b["bucket"]) for b in t["buckets"]] == [("INT-SUBJ-001", "fixed")] and t["next"] == "done"
    assert rv["buckets"]["fixed"] == 1 and rv["fix_rate"] == 1.0 and rv["specialist_time_s"] == {"median": 2.5, "p90": 2.5}
    assert t["consolidation_after"]["deliverable_message_id"] and t["original_receipt_unchanged"] and t["shadow_codes"] == [] and t["feedback_audit_codes"] == []
    assert all(rv["gates"].values()) and all(c["identical"] for c in rv["checks"])
    summary = (rd / "summary.md").read_text()
    assert "## Specialist revisions" in summary and "fix rate 100.0%" in summary
    assert json.loads((rd / "results.json").read_text())["revisions"]["answers_revised"] == 1


def test_a_fault_kept_verbatim_persists_and_is_withheld_and_escalated(tmp_path):
    rd = _round(tmp_path / "r")
    ra.revision_feedback(rd)
    _revise(rd, PH_TASK, PHYSICS_ITEM["response_text"])  # the very answer again
    rv = ra.revision_pass(rd, ra.load_items(rd / "specialists"), {})
    [t] = rv["tasks"]
    assert [(b["code"], b["bucket"]) for b in t["buckets"]] == [("INT-SUBJ-001", "persisted")] and t["next"] == "escalated"
    assert t["persisting_error_withheld"] and t["consolidation_after"]["deliverable_message_id"] is None and rv["gates"]["persisting_errors_withheld_and_escalated"]


def test_feedback_that_differs_from_what_the_specialist_read_is_flagged(tmp_path):
    rd = _round(tmp_path / "r")
    ra.revision_feedback(rd)
    _revise(rd, PH_TASK, PH_CORRECTED, read="0" * 64)  # the pipeline recorded another digest than the message it sent
    rv = ra.revision_pass(rd, ra.load_items(rd / "specialists"), {})
    assert rv["tasks"][0]["flag"] == "feedback differs from what the specialist read" and not rv["gates"]["feedback_as_read"]
    fb = rd / ra.FEEDBACK_DIR / f"{PH_TASK}.json"
    doc = json.loads(fb.read_text())
    doc["flaws"][0]["claim_ids"] = ["s9.9"]  # a recorded flaw this code does not issue
    fb.write_text(json.dumps(doc))
    rv = ra.revision_pass(rd, ra.load_items(rd / "specialists"), {})
    assert [c["differences"] for c in rv["checks"] if c["task_id"] == PH_TASK] == [["flaws"]] and not rv["gates"]["feedback_as_read"]
    assert "feedback differs from what the specialist read: ph-x1 (flaws)" in "\n".join(ra.revision_lines(rv))


def test_a_revision_of_an_answer_that_got_no_feedback_is_never_delivered(tmp_path):
    rd = _round(tmp_path / "r")
    ra.revision_feedback(rd)
    hid = HISTORY_ITEM["task_id"]
    (rd / ra.REVISIONS_DIR).mkdir()
    (rd / ra.REVISIONS_DIR / f"{hid}.json").write_text(json.dumps({"task_id": hid, "agent_id": HISTORY_ITEM["agent_id"], "feedback_sha256": "a" * 64,
                                                                   "response_text": HISTORY_ITEM["response_text"]}))
    rv = ra.revision_pass(rd, ra.load_items(rd / "specialists"), {})
    [t] = rv["tasks"]
    assert not t["delivered"] and "no revision request was issued" in t["error"] and not rv["gates"]["no_feedback_without_request"]


def test_a_rounds_revision_budget_comes_from_its_tasks_and_a_round_without_one_keeps_its_plan(tmp_path):
    rd = _round(tmp_path / "r")
    before = ra.group_plan(ra.load_items(rd / "specialists"), PH_TASK)
    assert before.budgets == {}
    (rd / "tasks.json").write_text(json.dumps([{"task_id": PH_TASK, "revision_rounds": 1}]))
    plan = ra.group_plan(ra.load_items(rd / "specialists"), PH_TASK)
    assert plan.budgets == {"revision_rounds": 1} and plan.model_copy(update={"budgets": {}}) == before
    ra.revision_feedback(rd)
    assert json.loads((rd / ra.FEEDBACK_DIR / f"{PH_TASK}.json").read_text())["max_rounds"] == 1
