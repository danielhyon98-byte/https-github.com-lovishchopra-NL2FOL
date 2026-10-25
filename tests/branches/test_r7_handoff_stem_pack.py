"""Round-7 hand-off from the STEM fixer (parser-safety-1, second part, blocker): an emptied STEM document never reads as
a pass.

Any internal failure of the STEM front end returns an empty document whose only finding is ST-INTERNAL-001 (warning;
the front end emits no error, ``tests/stem/test_relations.py``). The receipt then read ACCEPTED_WITH_FINDINGS with no
error and no STEM check, so a wrong calculation in the same answer was no longer reported and nothing on the receipt
said the checks had not run. The STEM pack now adds the hub's PACK-INTERNAL-001 at error severity whenever a report is
left with no STEM check by an internal failure (the front end emptied the document, or the pack raised), as
``SubjectBranch.run_packs`` does for a pack that raises."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.contracts import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import document as stem_document

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"r7-handoff-stem-pack-test-key-0123456789"
REQUEST = "A car travels 120 m in 4.0 s. Calculate its speed."
WRONG = "(a) The speed is v = d / t = 120 m / 4.0 s = 50 m s⁻¹."


def receive(answer: str, rid: str):
    agent = "physics-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=[agent]))
        m, _, _ = hub.dispatch("t", agent, REQUEST, [])
        _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id=rid)
        return rc
    finally:
        hub.close()


def _codes(rc) -> list[tuple[str, str]]:
    return [(f.code, f.severity) for f in rc.findings] + [(f.code, f.severity) for f in rc.structural_findings]


def test_control_the_wrong_step_is_an_engine_error_when_the_front_end_reads_the_answer():
    stem_document.clear_document_cache()
    rc = receive(WRONG, "rep-control")
    assert ("INT-SUBJ-001", "error") in _codes(rc) and ("PACK-INTERNAL-001", "error") not in _codes(rc)


def test_an_emptied_stem_document_carries_an_error_and_is_never_a_clean_receipt(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("injected front-end failure")
    monkeypatch.setattr(stem_document, "_build", boom)
    stem_document.clear_document_cache()
    try:
        rc = receive(WRONG, "rep-emptied")
    finally:
        stem_document.clear_document_cache()
    codes = _codes(rc)
    assert ("ST-INTERNAL-001", "warning") in codes  # the front end's own finding, unchanged
    assert ("PACK-INTERNAL-001", "error") in codes, codes  # the checks are missing: an error, never a pass
    assert rc.status is not TransmissionStatus.ACCEPTED
    assert not rc.formal_checks  # no STEM check was built or run, and the receipt says so with an error
    missing = next(f for f in rc.structural_findings if f.code == "PACK-INTERNAL-001")
    assert "must not treat them as passed" in missing.message
