"""The harness's round-c3 rules in the default suite (round-10 clearance, handoff pass; the harness fixer's handoff H3).

The round's overseers found that the harness read ``specialists/`` only: the four peer-dependent tasks ``tasks.json`` planned
(mai-p10a, ec-p10b, ge-p10c, en-p10d) were never relayed or answered and appeared nowhere in results.json or summary.md, and a
specialist file written as a one-element list stopped the whole round with a bare TypeError. ``scripts/arena/run_arena.py``
now names both (``load_items``, ``SpecialistFileError``, ``planned_tasks``). The fuller tests are in
``scripts/arena/test_arena_rules.py`` (run by path); this one keeps the two rules in the default suite, as
``test_r7_relay_file.py`` keeps the relayed-file rule. The recorded items are that file's own.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import run_arena as ra  # noqa: E402
from test_arena_rules import ENGLISH_PEER_ITEM, HISTORY_ITEM, HISTORY_SYNTHESIS  # noqa: E402


def _write(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_a_specialist_file_that_is_a_list_is_refused_by_name(tmp_path):
    specialists = tmp_path / "specialists"
    _write(specialists / "hi-x1.json", {**HISTORY_ITEM, "task_id": "hi-x1"})
    _write(specialists / "bi-x2.json", [{**HISTORY_ITEM, "task_id": "bi-x2"}])
    with pytest.raises(ra.SpecialistFileError) as err:
        ra.load_items(specialists)
    assert "specialists/bi-x2.json" in str(err.value) and "a list of 1 element(s)" in str(err.value) and "list indices" not in str(err.value)
    refused: list = []
    assert [it["task_id"] for it in ra.load_items(specialists, refused=refused)] == ["hi-x1"]
    assert [(b["file"], b["task_id"]) for b in refused] == [("bi-x2.json", "bi-x2")]


def test_a_planned_task_never_answered_is_named_and_fails_its_groups_synthesis(tmp_path):
    rd = tmp_path / "r"
    hi = {**HISTORY_ITEM, "task_id": "hi-y1", "group": "y1"}
    _write(rd / "specialists" / "hi-y1.json", hi)
    _write(rd / "syntheses" / "hi-y1.json", {**HISTORY_SYNTHESIS, "dropped": [{"source_claim_ids": ["h1.3"], "reason": "the sonnet is the English specialist's"}]})
    _write(rd / "tasks.json", [{k: v for k, v in t.items() if k != "response_text"} for t in (hi, ENGLISH_PEER_ITEM)])
    out = ra.run_round(rd)
    recs = {(r["file"], r["variant"]): r for r in out["records"]}
    reply, relay, syn = recs[("en-y1.json", "genuine")], recs[("en-y1.json", "peer_relay")], recs[("en-y1.json", "synthesis")]
    assert reply["functional"] is False and reply["not_answered"] is True and "group y1, peer of hi-y1" in reply["error"]
    assert relay["functional"] is False and relay["relay_not_run"] is True
    assert syn["functional"] is False and syn["members_not_answered"] == ["en-y1"]
    assert out["planned_tasks"]["not_answered"] == [{"task_id": "en-y1", "group": "y1", "peer_of": "hi-y1", "agent_id": "english-specialist",
                                                     "subject": "English A: Literature"}]
    assert all(r["functional"] for r in out["records"] if r["file"] == "hi-y1.json")
    assert "- NOT ANSWERED: en-y1 (English A: Literature, english-specialist; group y1, peer of hi-y1)" in (rd / "summary.md").read_text()
    # control: the answer recorded, nothing is named
    _write(rd / "specialists" / "en-y1.json", ENGLISH_PEER_ITEM)
    again = ra.run_round(rd)
    assert again["planned_tasks"]["not_answered"] == [] and again["metrics"]["transport"]["genuine_traffic"]["not_answered"] == []
