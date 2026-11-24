"""Follow-up c3g, overseer items (expected values fixed here; never relaxed to make the code pass).

* Item 2 (a c3f leftover): the transfer auditor's rules ``own-text``, ``own-correction`` and ``correction-role`` read the quotation
  frames with no task in context, so a feedback-only frame ('Your sentence "x" could become "y"', 'Not "x" but "y"', '"x"; it should
  be "y"') drew OVS-FID-004 and AUDIT_FAILED in a marking_feedback task, where the channel frees the correction. The auditor now reads
  the frames in the PLAN's task type for the agent (``fidelity.plan_task_type``), never the report's own: in a feedback task the
  correction is the writer's own, in an essay or analysis task it is a quotation the channel charges (and, with the channel's source
  checks removed, the auditor names it), and a corrected half that presents a supplied text's wording altered stays a quotation in
  every task (rule ``correction-role``).
* Check round 12 of c3f (pre-existing, no longer reproduced on the tree; pinned here end to end under the NOT CHECKED delivery): the
  unquoted Spanish correction pairs with a cross and a tick, and the gloss with typographic quotes, are correct work, delivered NOT
  CHECKED and never withheld through OVS-FID-009 or OVS-FID-005.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from epinoic_logic.api.channel import TranslatorChannel
from epinoic_logic.api.integrity import WorkPlan
from epinoic_overseer.checks.fidelity import plan_task_type
from epinoic_overseer.delivery_policy import DeliveryConfig

from .conftest import EN_INPUT, english_report, findings, make_auditor, make_plan, new_channel
from .test_c2_hold_round2_gate import _deliver
from .test_c2_hold_self_certification_gate import SUBJECTS
from .test_c3f_correction_role import _notes
from .test_clearance_c3_overseer import C3, _audited_channel, _item

#: The feedback-only frames of the one reader (``own_text``): a correction in a marking or feedback task only.
FEEDBACK_FRAMES = [
    'Your sentence "the adverts are about money" could become "the adverts sell saving as a family duty".',
    'Not "the adverts are about money" but "the adverts sell saving as a family duty".',
    '"the adverts are about money"; it should be "the adverts sell saving as a family duty".',
]
FRAME_IDS = ["could-become", "not-but", "it-should-be"]
_SOURCE_ERRORS = ("INT-REQ-003", "ES-SRC-001", "CORE-SRC-006")


def _ll_t16(extra: str, task_type: str) -> str:
    it = dict(_item("ll-t16"))
    key = f"ll-t16-c3g-{task_type}-{abs(hash(extra))}"
    C3["specialists"][key] = dict(it, task_id=key, task_type=task_type, response_text=it["response_text"] + "\n\n" + extra)
    return key


@pytest.mark.parametrize("sentence", FEEDBACK_FRAMES, ids=FRAME_IDS)
def test_a_feedback_only_frame_draws_no_fid_004_in_a_marking_feedback_task(sentence):
    """End to end on the recorded ll-t16 answer (RouterHub with the transfer auditor): the channel frees the correction in the
    marking task, and the auditor agrees (no OVS-FID-004, AUDIT_PASSED). Before: OVS-FID-004 on p9-point and p9-q01, AUDIT_FAILED."""
    key = _ll_t16(sentence, "marking_feedback")
    a = _audited_channel(key, translations=False)
    try:
        assert sorted({f.code for f in list(a.rc.findings) + list(a.rc.structural_findings) if f.code in _SOURCE_ERRORS}) == []
        assert [f.message for f in a.audit.report.findings if f.code == "OVS-FID-004"] == []
        assert (a.cl.state, sorted(a.cl.codes)) == ("AUDIT_PASSED", [])
    finally:
        a.hub.close()
        C3["specialists"].pop(key, None)


@pytest.mark.parametrize("sentence", FEEDBACK_FRAMES, ids=FRAME_IDS)
def test_in_an_essay_task_the_channel_charges_the_frame_and_the_audit_agrees(sentence):
    """The essay twin: the frame is no correction outside a feedback task, so the channel charges both spans (INT-REQ-003 and
    ES-SRC-001 at error) and the auditor, finding the claims named, adds nothing (AUDIT_PASSED)."""
    key = _ll_t16(sentence, "hl_essay")
    a = _audited_channel(key, translations=False)
    try:
        charged = {(f.code, f.severity) for f in list(a.rc.findings) + list(a.rc.structural_findings) if f.code in _SOURCE_ERRORS}
        assert sorted(charged) == [("ES-SRC-001", "error"), ("INT-REQ-003", "error")]
        assert [f.message for f in a.audit.report.findings if f.code == "OVS-FID-004"] == []
        assert (a.cl.state, sorted(a.cl.codes)) == ("AUDIT_PASSED", [])
    finally:
        a.hub.close()
        C3["specialists"].pop(key, None)


def _without_the_channels_source_checks(monkeypatch) -> None:
    """A channel that names no quotation (as test_c3f_correction_role): the auditor's own reading is what remains."""
    monkeypatch.setattr(TranslatorChannel, "_source_findings", lambda self, report, supplied: (set(), set(), []))
    orig = TranslatorChannel._branch_checks

    def no_src(self, report, req, findings_, *a, **kw):
        structural, formal, ids = orig(self, report, req, findings_, *a, **kw)
        findings_[:] = [f for f in findings_ if not (f.code == "INT-SUBJ-003" and "-SRC-" in f.message)]
        return [s for s in structural if "-SRC-" not in s.code], formal, ids
    monkeypatch.setattr(TranslatorChannel, "_branch_checks", no_src)


def _auditor_alone(sentence: str, plan_task: str, report_task: str | None = None) -> list[str]:
    """The OVS-FID-004 messages the auditor gives ``sentence`` (one claim, ll-t16's notes supplied) under a plan of ``plan_task``,
    the report and its claim declaring ``report_task`` (default: the plan's)."""
    auditor = make_auditor()
    notes = _notes()
    claims = [dict(claim_id="c1", claim_text=sentence, claim_role="point", materiality="material")]
    report = english_report(sentence, claims, docs=(notes,))
    declared = report_task or plan_task
    report = report.model_copy(update={"task_type": declared, "claims": [c.model_copy(update={"task_type": declared}) for c in report.claims]})
    ch = new_channel(auditor, make_plan(task_type=plan_task, allowed_document_ids=[notes.document_id]))
    m, _r, rq = ch.request("router", "english-specialist", EN_INPUT, [notes])
    assert m is not None, rq.findings
    _msg, rc = ch.respond(m.message_id, report)
    assert not [f for f in rc.findings if f.code == "INT-REQ-003"]  # the channel names nothing here
    return [f.message for f in findings(auditor.audit(ch.uid), "OVS-FID-004")]


@pytest.mark.parametrize("task_type, named", [("analytical_paragraph", True), ("hl_essay", True), ("marking_feedback", False)])
@pytest.mark.parametrize("sentence", FEEDBACK_FRAMES, ids=FRAME_IDS)
def test_the_auditor_reads_a_feedback_only_frame_in_the_plans_task(monkeypatch, sentence, task_type, named):
    _without_the_channels_source_checks(monkeypatch)
    got = _auditor_alone(sentence, task_type)
    if named:
        assert len(got) == 1 and "the adverts are about money" in got[0] and "the adverts sell saving as a family duty" in got[0], got
    else:
        assert got == [], got


@pytest.mark.parametrize("sentence", FEEDBACK_FRAMES, ids=FRAME_IDS)
def test_a_report_that_declares_a_feedback_task_never_widens_the_plans_reading(monkeypatch, sentence):
    """The plan is an essay; the report and its claim declare marking_feedback (an agent's own record, advisory): the frames are read
    in the plan's task, so the quotations stay named."""
    _without_the_channels_source_checks(monkeypatch)
    got = _auditor_alone(sentence, "hl_essay", "marking_feedback")
    assert len(got) == 1 and "the adverts are about money" in got[0], got


@pytest.mark.parametrize("task_type", ["analytical_paragraph", "hl_essay", "marking_feedback"])
@pytest.mark.parametrize("sentence", [
    'Your sentence "Made with love." could become "Made with care. Finished with care."',
    'Not "Made with love." but "Made with care. Finished with care."',
], ids=["could-become", "not-but"])
def test_a_corrected_half_that_alters_the_source_stays_named_in_every_task(monkeypatch, sentence, task_type):
    """Rule correction-role in the plan's task: a corrected half presenting the notes' 'Made with love. Finished with love.' altered
    is a quotation, named by OVS-FID-004 in a feedback task too; the replaced half (the notes' exact words) is never named."""
    _without_the_channels_source_checks(monkeypatch)
    got = _auditor_alone(sentence, task_type)
    assert len(got) == 1 and "Made with care. Finished with care." in got[0] and "Made with love" not in got[0], got


@pytest.mark.parametrize("task_type, named", [("hl_essay", True), ("marking_feedback", False)])
def test_the_replaced_half_restoring_the_source_is_read_in_the_plans_task(monkeypatch, task_type, named):
    """'Your sentence "x" could become "y"' where "y" is the notes' exact wording: in a feedback task the replaced half is the writer's
    own example of the misquotation; in an essay the frame is no correction and the replaced half is named."""
    _without_the_channels_source_checks(monkeypatch)
    got = _auditor_alone('Your sentence "Not every kitchen has a home." could become "Not every kitchen has a door."', task_type)
    if named:
        assert len(got) == 1 and "Not every kitchen has a home." in got[0], got
    else:
        assert got == [], got


def _view(plan):
    return SimpleNamespace(view=SimpleNamespace(plan_at=lambda seq: plan))


def test_plan_task_type_is_the_plans_type_for_the_agent_never_the_reports():
    plan = WorkPlan(plan_id="p", request_id="r", task_id="t", subject="English A: Literature", task_type="hl_essay",
                    selected_agent_ids=["english-specialist", "history-specialist"], agent_task_types={"history-specialist": "marking_feedback"})
    rep_en = SimpleNamespace(agent_id="english-specialist", task_type="marking_feedback")
    rep_hi = SimpleNamespace(agent_id="history-specialist", task_type="hl_essay")
    t = SimpleNamespace(seq=1, call={})
    assert plan_task_type(_view(plan), t, rep_en) == "hl_essay"
    assert plan_task_type(_view(plan), t, rep_hi) == "marking_feedback"
    assert plan_task_type(_view(plan), SimpleNamespace(seq=1, call={"agent_id": "history-specialist"}), rep_en) == "marking_feedback"
    assert plan_task_type(_view(None), t, rep_en) is None


def test_plan_task_type_fails_to_no_task():
    def boom(seq):
        raise RuntimeError("unreadable view")
    assert plan_task_type(SimpleNamespace(view=SimpleNamespace(plan_at=boom)), SimpleNamespace(seq=1, call={}), SimpleNamespace(agent_id="a")) is None


# ------------------------------------------------------------------------------------- check round 12 of c3f, end to end
NC = DeliveryConfig(on_overseer_timeout="deliver_canonical_not_checked")
BY = {s[0]: s for s in SUBJECTS}
CORRECT_WORK = [
    "✗ Ella es cansada ✓ Ella está cansada",
    "✗ Nosotros somos en casa ✓ Nosotros estamos en casa",
    "✗ Yo soy cansado ✓ Yo estoy cansado",
    "«comprobado» se dice ‘checked’",
    "En inglés, «comprobado» se dice ‘checked’.",
]


@pytest.mark.parametrize("line", CORRECT_WORK)
@pytest.mark.parametrize("subject", ["Spanish B", "Geography", "Physics", "Economics"])
def test_correct_language_work_is_delivered_not_checked(subject, line):
    s, agent, tt, base = BY[subject]
    _rc, d = _deliver(s, agent, tt, base + "\n\n" + line, config=NC)
    [c] = d.receipt.fallback.candidates
    assert (c.deliverable, list(c.integrity_reasons)) == (True, []), (subject, line, c.integrity_reasons)
    assert (d.delivered, d.mode) == (True, "not_checked"), (subject, line, d.mode)
