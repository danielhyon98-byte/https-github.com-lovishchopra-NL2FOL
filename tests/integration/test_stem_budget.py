"""The STEM check budget as a per-channel parameter (integration/README.md, T4): bounded by ``STEM_CHECK_BUDGET_S``, never larger, never
below zero; ``None`` (every existing caller) is the module budget, so the channel behaves exactly as before. A check the
budget leaves out is undecided (INT-SUBJ-002), never success."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import bus
from epinoic_logic.channel.bus import STEM_CHECK_BUDGET_S, TranslatorChannel, stem_budget_s
from epinoic_logic.integrity import WorkPlan

CORPUS = Path(__file__).resolve().parents[2] / "integration" / "sim" / "corpus" / "synthetic" / "s1"
KEY = b"stem-budget-key-0123456789abcdef0123"


@pytest.mark.parametrize("requested,expected", [
    (None, STEM_CHECK_BUDGET_S), (0, 0.0), (0.5, 0.5), (STEM_CHECK_BUDGET_S, STEM_CHECK_BUDGET_S),
    (STEM_CHECK_BUDGET_S * 10, STEM_CHECK_BUDGET_S), (-3, 0.0), (math.inf, STEM_CHECK_BUDGET_S), (math.nan, 0.0), ("x", STEM_CHECK_BUDGET_S),
])
def test_the_budget_is_bounded_by_the_module_budget(requested, expected):
    assert stem_budget_s(requested) == expected


def test_the_module_budget_is_read_at_call_time(monkeypatch):
    monkeypatch.setattr(bus, "STEM_CHECK_BUDGET_S", 1.5)
    assert bus.stem_budget_s(None) == 1.5 and bus.stem_budget_s(9.0) == 1.5


def test_a_channel_nobody_configured_uses_the_module_budget():
    assert TranslatorChannel.stem_budget_s is None


def _receive(name: str, budget):
    item = json.loads((CORPUS / "specialists" / f"{name}.json").read_text(encoding="utf-8"))
    hub = RouterHub(signing_key=KEY)
    ch = hub.open_task(WorkPlan(plan_id=f"plan-{name}", request_id=f"req-{name}", task_id=name, subject=item["subject"],
                                task_type=item["task_type"], selected_agent_ids=[item["agent_id"]]))
    if budget is not None:
        ch.stem_budget_s = budget
    msg, _req, _rc = hub.dispatch(name, item["agent_id"], item["question"], [])
    _reply, rc = hub.receive(name, msg.message_id, item["response_text"], agent_id=item["agent_id"], report_id=f"rep-{name}")
    return rc


def test_a_spent_budget_leaves_the_stem_checks_undecided_never_success():
    decided = _receive("ph-s1", None)
    cut = _receive("ph-s1", 0.0)
    assert [fc.formal_status for fc in decided.formal_checks] == ["ENTAILED"]
    assert [(fc.formal_status, fc.satisfied) for fc in cut.formal_checks] == [(None, None)]
    assert any(f.code == "INT-SUBJ-002" and "0 s" in f.message for f in cut.findings)
    assert not any(f.code == "INT-SUBJ-002" for f in decided.findings)
    assert cut.status.value == "ACCEPTED_WITH_FINDINGS"


def test_a_spent_budget_never_hides_a_refutation_as_success():
    cut = _receive("ph-s2", 0.0)
    assert all(fc.formal_status != "ENTAILED" for fc in cut.formal_checks)
