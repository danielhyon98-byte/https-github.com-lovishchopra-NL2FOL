"""The class of re-run review finding security-5 in the plan and the request: ``course_level`` is optional with the
default ``"unknown"``, so a plan or a request stating ``None`` lost the key in its canonical dump and read back as
``"unknown"``, a different record. A stated ``None`` is read as ``"unknown"``, so each reads back as it was written."""
from __future__ import annotations

import pytest

from epinoic_logic.channel.contracts import TaskRequest
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.canonical import sha256_hex


def plan(**over) -> WorkPlan:
    return WorkPlan(**{**dict(plan_id="pl", request_id="rq", task_id="t", subject="History", task_type="short_answer",
                              selected_agent_ids=["history-specialist"]), **over})


def request(**over) -> TaskRequest:
    text = "Explain the 1929 crash."
    return TaskRequest(**{**dict(request_id="rq", task_id="t", plan_id="pl", from_agent_id="router", to_agent_id="history-specialist",
                                 subject="History", task_type="short_answer", user_input=text, user_input_sha256=sha256_hex(text),
                                 created_at="2026-10-17T00:00:00Z"), **over})


@pytest.mark.parametrize("make", [plan, request], ids=["plan", "request"])
def test_a_record_stating_no_course_level_reads_back_as_it_was_written(make):
    record = make(course_level=None)
    again = type(record).model_validate(record.model_dump(mode="json", exclude_none=True))
    assert again == record and record.course_level == "unknown"


@pytest.mark.parametrize("make", [plan, request], ids=["plan", "request"])
@pytest.mark.parametrize("level", ["SL", "HL", "unknown"])
def test_a_stated_course_level_is_kept_as_stated(make, level: str):
    """Control."""
    assert make(course_level=level).course_level == level and make().course_level == "unknown"
