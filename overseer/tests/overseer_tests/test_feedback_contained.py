"""The contained run's stage of specialist feedback and revision (``scripts/revision_probes.py``; design section 53): its
three controls catch what they must (a corrected revision fixed, an unsigned block refused by the channel, a fabricated
audit flaw caught by the audit), the run's gates read the stage, and a recorded round, when present, passes both gates
with every infrastructure-built request bound and the shadow agreeing on every revision transfer."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None


def test_the_controls_catch_an_unsigned_block_and_a_fabricated_flaw_and_a_correction_is_fixed():
    import revision_probes as RP
    c = RP.run_controls()
    assert {k: v["ok"] for k, v in c.items()} == {"corrected_revision_fixed": True, "unsigned": True, "fabricated_audit_flaw": True}, c
    assert c["corrected_revision_fixed"]["observed"] == ["INT-SUBJ-001 fixed", "done"]
    assert not c["unsigned"]["observed"]["sent"] and c["unsigned"]["observed"]["request_codes"] == ["INT-REV-001"]
    assert c["fabricated_audit_flaw"]["observed"]["sent"] and c["fabricated_audit_flaw"]["observed"]["ovs_fb_001"] >= 1


def test_the_run_reads_both_gates_of_the_stage_and_a_run_without_it_has_neither():
    import run_contained as RC
    ok = {"gates": {"revision_requests_bind": {"ok": True, "requests_issued": 6}, "shadow_agrees_on_revision_transfers": {"ok": True, "shadow_findings": 0}}}
    g = RC.gates({"revisions": ok})
    assert g["revision_requests_bind"] == {"ok": True, "requests_issued": 6} and g["shadow_agrees_on_revision_transfers"]["ok"]
    bad = {"gates": {"revision_requests_bind": {"ok": True}, "shadow_agrees_on_revision_transfers": {"ok": False, "shadow_findings": 1}}}
    assert not RC.gates({"revisions": bad})["shadow_agrees_on_revision_transfers"]["ok"]
    assert "revision_requests_bind" not in RC.gates({}) and "shadow_agrees_on_revision_transfers" not in RC.gates({})


def test_a_recorded_round_passes_both_gates(tmp_path):
    if ROUNDS is None or not (ROUNDS / "r7" / "specialists").is_dir():
        pytest.skip("the recorded round r7 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
    import revision_probes as RP
    doc = RP.run(tmp_path / "out", [("r7", ROUNDS / "r7")])
    bind, shadow = doc["gates"]["revision_requests_bind"], doc["gates"]["shadow_agrees_on_revision_transfers"]
    assert bind["ok"] and shadow["ok"], doc["gates"]
    assert bind["requests_issued"] >= 1 and bind["channel_refusals"] == 0 and bind["ovs_fb_001"] == 0 and shadow["shadow_findings"] == 0
    assert (ROUNDS / "r7" / "specialists").is_dir() and not (ROUNDS / "r7" / "feedback").exists()  # the recorded round is never written
