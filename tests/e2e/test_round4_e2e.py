"""End to end through the hub, round 4: a correct quotation written with an academic elision mark ("[...]", "[…]",
"(...)") crosses the English branch as an elided quotation, never as an invented one, and a truncated emoji in the
same answer is refused with INT-REQ-009 instead of raising out of the hub."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText

KEY = b"round4-e2e-test-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
EN_T7 = json.loads((Path(__file__).parent / "r4_en_t7_elision.json").read_text())


def _hub():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="plan-en-t7", request_id="req-en-t7", task_id="en-t7", subject="English A: Literature", task_type="analytical_paragraph",
                           selected_agent_ids=["english-specialist"], allowed_document_ids=["doc-wb"]))
    msg, _req, _rq = hub.dispatch("en-t7", "english-specialist", EN_T7["question"], [SuppliedText(**t) for t in EN_T7["supplied_texts"]])
    return hub, msg


@pytest.mark.parametrize("mark", ["[...]", "[…]", "(...)"])
def test_an_academic_elision_mark_is_never_an_invented_quotation(mark):
    hub, msg = _hub()
    text = EN_T7["response_text"].replace("[...]", mark)
    reply, rc = hub.receive("en-t7", msg.message_id, text, agent_id="english-specialist", report_id="rep-en-t7")
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    assert "INT-REQ-003" not in {f.code for f in rc.findings}, [f.message for f in rc.findings if f.code == "INT-REQ-003"]
    assert not [sf for sf in rc.structural_findings if sf.code.endswith("-SRC-001") and sf.severity == "error"]


def test_a_truncated_emoji_in_the_same_answer_is_refused_not_raised():
    hub, msg = _hub()
    reply, rc = hub.receive("en-t7", msg.message_id, EN_T7["response_text"] + " The city glows \ud83d", agent_id="english-specialist", report_id="rep-en-t7")
    assert reply is None and rc.status is TransmissionStatus.REJECTED and [f.code for f in rc.findings] == ["INT-REQ-009"]
