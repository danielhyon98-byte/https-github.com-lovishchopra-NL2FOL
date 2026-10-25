"""The syntheses format carries a disclosed conflict record to the hub (repair round 1, re-run review cf-2): a
``conflicts`` entry of a syntheses file is relayed as written, so the record reaches the hub's synthesis, which reads it
(INT-CONFLICT-*), instead of the whole synthesis being refused as an unknown field. A field a conflict record does not
hold is still refused, never dropped. Control: a file with no conflicts relays no conflicts field."""
from __future__ import annotations

import json
import sys

import pytest

from .test_lens_round_d import ARENA, HI


@pytest.fixture()
def arena():
    sys.path.insert(0, str(ARENA))
    try:
        import run_arena  # noqa: PLC0415
        yield run_arena
    finally:
        sys.path.remove(str(ARENA))


def _round(tmp_path, syn: dict):
    (tmp_path / "specialists").mkdir()
    (tmp_path / "syntheses").mkdir()
    (tmp_path / "specialists" / "hi-d1.json").write_text(json.dumps(HI))
    (tmp_path / "syntheses" / "hi-d1.json").write_text(json.dumps(syn))


SYN = {"report_id": "rep-hi-d1-0", "dropped": [],
       "claims": [{"text": "Banks failed in 1930 and 1931.", "source_claim_ids": ["h1.2"], "transformation": "carried"}]}
CONFLICT = {"conflict_id": "c1", "claim_ids": ["h1.1", "h1.2"], "description": "the two sentences date the spread differently", "status": "unresolved"}


def test_a_disclosed_conflict_record_reaches_the_hub(arena, tmp_path):
    _round(tmp_path, {**SYN, "conflicts": [CONFLICT]})
    assert arena.synthesis_format_problems("hi-d1", {**SYN, "conflicts": [CONFLICT]}) == {}
    rec = next(r for r in arena.run_round(tmp_path)["records"] if r["variant"] == "synthesis")
    assert rec["delivered"] is True and "unknown_synthesis_fields" not in rec


def test_a_conflict_record_field_the_contract_does_not_hold_is_refused(arena, tmp_path):
    bad = {**CONFLICT, "verified": True}
    _round(tmp_path, {**SYN, "conflicts": [bad]})
    assert arena.synthesis_format_problems("hi-d1", {**SYN, "conflicts": [bad]}) == {"syntheses/hi-d1.json conflicts[0]": ["verified"]}
    rec = next(r for r in arena.run_round(tmp_path)["records"] if r["variant"] == "synthesis")
    assert rec["functional"] is False and rec.get("delivered") is False and any("conflicts[0]" in k for k in rec["unknown_synthesis_fields"])


def test_clean_control_a_file_without_conflicts_relays_none(arena, tmp_path):
    _round(tmp_path, SYN)
    items = arena.load_items(tmp_path / "specialists")

    class _Reply:  # the delivered report as group_synthesis reads it: its report id and claim ids
        payload = {"report_id": "rep-hi-d1-0", "claims": [{"claim_id": "h1.1"}, {"claim_id": "h1.2"}]}

    plan = arena.group_plan(items, "hi-d1")
    mapping = arena.group_synthesis(items, "hi-d1", {"hi-d1": SYN}, {"hi-d1": _Reply()}, plan)
    assert "conflicts" not in mapping
    with_conflict = arena.group_synthesis(items, "hi-d1", {"hi-d1": {**SYN, "conflicts": [CONFLICT]}}, {"hi-d1": _Reply()}, plan)
    assert with_conflict["conflicts"] == [CONFLICT]
