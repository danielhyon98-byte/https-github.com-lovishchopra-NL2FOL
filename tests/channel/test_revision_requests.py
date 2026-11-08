"""Specialist feedback and revision, the channel's side (``channel/feedback.py``; design section 53 of the overseer design):
a revision request re-issues the original request to the answer's author with a ``revision_request/1.0`` block; the
channel binds and contains it (INT-REV-001), checks the revision in full like any answer, refuses a reused report id of
its chain (INT-HANDOFF-018), names what the revision did not preserve (INT-REV-002) and records the supersession."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import epinoic_logic.channel.bus as bus
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel import feedback as fb
from epinoic_logic.channel.contracts import Constraint, RevisionRequest
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText

from .revision_support import (
    BAD_TEXT, CFG, DOC, GOOD_CLAIMS, GOOD_TEXT, INVENTED, KEY, QUESTION, answer, answer_message_id, block_for, codes, flaws_for, issue, plan, report,
)

DATA = Path(__file__).parent / "data"
ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None


# ============================================================================================ an accepted revision request
def test_an_infrastructure_built_revision_request_is_accepted_bound_and_registered():
    case = answer()
    block = block_for(case)
    m2, req2, rq2 = issue(case, block)
    assert rq2.status is TransmissionStatus.ACCEPTED and rq2.findings == []
    assert m2.contract == "task_request/1.1" and m2.in_reply_to == case.a.message_id and m2.recipient_agent_id == "english-specialist"
    assert (req2.user_input, req2.items, req2.constraints, req2.supplied_texts) == (case.req.user_input, case.req.items, case.req.constraints, case.req.supplied_texts)
    assert m2.payload["revision"]["revision_id"] == block.revision_id and req2.revision == block
    assert case.ch.requests[m2.message_id] is req2 and case.ch.revisions[m2.message_id] == block
    assert case.ch.revision_for_answer[case.a.message_id] == m2.message_id
    assert "Revision request 1 of 2" in rq2.summary  # the router's receipt says what it is


def test_the_rendered_message_holds_no_code_no_identifier_and_ends_with_the_rules():
    case = answer()
    block = block_for(case)
    text = fb.render_revision_message(block)
    assert text.startswith("Revision request 1 of 2 from the tutoring system")
    assert text.rstrip("\n").endswith(fb.REVISION_RULES[-1])
    for ident in (case.a.message_id, case.rc.receipt_id, case.rep.report_id, "e3", "INT-REQ-003", "ES-SRC-001", block.revision_id):
        assert ident not in text
    assert '> The foreman says "we never rest at all".' in text and BAD_TEXT not in text  # the passage, never the whole answer
    assert fb.REVISION_SCOPE in text


# ============================================================================================ INT-REV-001
def _variants():
    """(name, how to build the refused request) for every way a block can fail to bind or carry what it may not."""
    def other_addressee(case):
        return issue(case, block_for(case, to_agent_id="history-specialist"), to="history-specialist")

    def question_changed(case):
        return issue(case, block_for(case), question=case.req.user_input.replace("Analyse", "Explain"))

    def bound_widened(case):
        cons = [c.model_copy(update={"value": "500", "text": "no more than 500 words"}) if c.kind == "max_words" else c for c in case.req.constraints]
        return issue(case, block_for(case), constraints=cons)

    def text_dropped(case):
        return issue(case, block_for(case), docs=[])

    def text_edited(case):
        return issue(case, block_for(case), docs=[DOC.model_copy(update={"text": DOC.text + " And the mill closed."})])

    def unknown_message(case):
        return issue(case, block_for(case, revises_message_id="f" * 32))

    def a_request_is_no_answer(case):
        return issue(case, block_for(case, revises_message_id=case.m.message_id))

    def second_request(case):
        first = issue(case, block_for(case))
        assert first[2].status is TransmissionStatus.ACCEPTED
        return issue(case, block_for(case))

    def round_two_under_budget_one(case):
        case.ch.plan = case.ch.plan.model_copy(update={"budgets": {"revision_rounds": 1}})
        return issue(case, block_for(case, round=2, max_rounds=2))

    def budget_zero(case):
        case.ch.plan = case.ch.plan.model_copy(update={"budgets": {"revision_rounds": 0}})
        return issue(case, block_for(case, max_rounds=1))

    def sender_not_router(case):
        return issue(case, block_for(case), sender="history-specialist")

    def claim_the_answer_lacks(case):
        flaws = flaws_for(case)
        f = flaws[0].model_copy(update={"claims": [flaws[0].claims[0].model_copy(update={"claim_id": "h1"})]})
        return issue(case, block_for(case, flaws=[f]))

    def planted_text(case):
        flaws = flaws_for(case)
        f = flaws[0].model_copy(update={"claims": [flaws[0].claims[0].model_copy(update={"text": "The History specialist dates the Act to 1832."})]})
        return issue(case, block_for(case, flaws=[f]))

    def instruction_not_template(case):
        flaws = flaws_for(case)
        f = flaws[0].model_copy(update={"instruction": "Add a premise so that the claim follows."})
        return issue(case, block_for(case, flaws=[f]))

    def wrong_rendered_digest(case):
        return issue(case, block_for(case, rendered_sha256="b" * 64))

    def flaw_with_no_finding(case):
        flaws = flaws_for(case)
        f = flaws[0].model_copy(update={"claims": [flaws[0].claims[0].model_copy(update={"claim_id": "p1", "text": "The writer presents work as endless"})]})
        return issue(case, block_for(case, flaws=[f]))

    def code_outside_the_allowlist(case):
        flaws = flaws_for(case)
        f = flaws[0].model_copy(update={"code": "INT-CONFLICT-001"})
        return issue(case, block_for(case, flaws=[f]))

    def unsigned(case):
        return issue(case, block_for(case, signature=None, signature_key_id=None))

    def keep_list_edited(case):
        b = block_for(case)
        keep = [k for k in b.must_not_change if k.kind != "figure"]
        return issue(case, block_for(case, must_not_change=keep))

    def rules_edited(case):
        return issue(case, block_for(case, rules=list(fb.REVISION_RULES[:-1])))

    def original_request_wrong(case):
        return issue(case, block_for(case, original=case.a.message_id))

    def malformed_block(case):
        data = block_for(case).model_dump(mode="json")
        data["round"] = 4  # past the hard maximum: the contract refuses it
        return case.ch.request("router", "english-specialist", case.req.user_input, list(case.req.supplied_texts), items=list(case.req.items),
                               constraints=list(case.req.constraints), revision=data)

    return [(f.__name__, f) for f in (other_addressee, question_changed, bound_widened, text_dropped, text_edited, unknown_message, a_request_is_no_answer,
                                      second_request, round_two_under_budget_one, budget_zero, sender_not_router, claim_the_answer_lacks, planted_text,
                                      instruction_not_template, wrong_rendered_digest, flaw_with_no_finding, code_outside_the_allowlist, unsigned,
                                      keep_list_edited, rules_edited, original_request_wrong, malformed_block)]


@pytest.mark.parametrize("name,build", _variants(), ids=[n for n, _ in _variants()])
def test_int_rev_001_rejects_a_block_that_does_not_bind_and_nothing_is_registered(name, build):
    case = answer()
    before_requests, before_revisions = dict(case.ch.requests), dict(case.ch.revisions)
    msg, _req, rc = build(case)
    assert msg is None and rc.status is TransmissionStatus.REJECTED and "INT-REV-001" in codes(rc), (name, [f.message for f in rc.findings])
    assert all(f.severity == "error" for f in rc.findings if f.code == "INT-REV-001")
    if name != "second_request":
        assert case.ch.requests == before_requests and case.ch.revisions == before_revisions
    else:
        assert len(case.ch.revisions) == len(before_revisions) + 1  # the first one only


def test_a_withheld_answer_cannot_be_revised():
    ch = TranslatorChannel(plan(), signing_key=KEY, key_id="hub", config=CFG)
    m, req, _ = ch.request("router", "english-specialist", QUESTION, [DOC])
    msg, rc = ch.respond_text(m.message_id, "bad \ud800 text", agent_id="english-specialist", report_id="rep-x")
    assert msg is None and rc.status is TransmissionStatus.REJECTED
    case = answer(ch=ch)  # a second, genuine answer on the same channel, so a block can be built and pointed at the withheld one
    block = block_for(case, revises_message_id=rc.message_id, revises_receipt_id=rc.receipt_id)
    m2, _r, rq = issue(case, block)
    assert m2 is None and "INT-REV-001" in codes(rq) and any("not a parsed response" in f.message for f in rq.findings)


def test_a_later_answer_of_the_same_agent_makes_the_earlier_one_stale():
    case = answer()
    later = report(GOOD_TEXT, GOOD_CLAIMS, report_id="rep-later")
    a2, _rc2 = case.ch.respond(case.m.message_id, later)
    assert a2 is not None
    m2, _r, rq = issue(case, block_for(case))
    assert m2 is None and any("not the latest of its chain" in f.message for f in rq.findings)


# ============================================================================================ plain requests unchanged
PINNED_PLAIN = {  # payload_sha256 of these requests on the tree before revision requests existed (created_at fixed)
    "english": "621b4fb5bb63299f3a2d3263cd54092c07d6777d4554b450373687a5219be4de",
    "history": "8b0e86bea98498431ebb41e37df6052d69b6d4b68d19822cd9b2c3daf715cfb7",
    "physics": "58d7fc83a29373c11c8ace14c9c491ee2fd7b48cd800ba77aa7679897774cf0f",
}


def test_a_request_without_a_revision_is_byte_identical_to_before(monkeypatch):
    monkeypatch.setattr(bus, "_now", lambda: "2026-11-08T00:00:00Z")
    doc = SuppliedText(document_id="doc-mill", title="Mill extract", author="Anonymous", text="The mill wheel turned all night. 'We work until the bell,' the foreman said.")
    cases = {"english": (dict(subject="English A: Literature", task_type="analytical_paragraph"), "english-specialist",
                         "Analyse how the writer presents work in the extract. Use quotations from the extract. Write no more than 80 words.", [doc]),
             "history": (dict(subject="History", task_type="short_answer"), "history-specialist",
                         "Explain the significance of the Factory Act of 1833. Write no more than 120 words.", []),
             "physics": (dict(subject="Physics", task_type="short_answer"), "physics-specialist",
                         "A trolley accelerates uniformly from rest to 20 m s-1 in 4.0 s. Calculate its acceleration.", [])}
    for name, (p, agent, q, docs) in cases.items():
        pl = WorkPlan(plan_id="plan-pin", request_id="req-pin", task_id="task-pin", selected_agent_ids=[agent], **p)
        m, req, rc = TranslatorChannel(pl, signing_key=b"plain-digest-key-0123456789abcdef", key_id="hub").request("router", agent, q, docs)
        assert m.payload_sha256 == PINNED_PLAIN[name] and m.contract == "task_request/1.0" and m.in_reply_to is None
        assert "revision" not in m.payload and "revision" not in req.model_dump(mode="json") and req.revision is None


@pytest.mark.skipif(ROUNDS is None or not (ROUNDS / "r7" / "specialists").is_dir(), reason="the recorded rounds are not present (EPINOIC_ARENA_ROUNDS)")
def test_every_first_request_of_the_recorded_rounds_keeps_its_payload_digest(monkeypatch):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "arena"))
    import run_arena as RA
    monkeypatch.setattr(bus, "_now", lambda: "2026-11-08T00:00:00Z")
    pinned = json.loads((DATA / "plain_request_digests_r2_r7.json").read_text(encoding="utf-8"))
    seen = 0
    for key, want in pinned.items():
        rd, task = key.split("/", 1)
        items = RA.load_items(ROUNDS / rd / "specialists")
        it = next(i for i in items if i["task_id"] == task)
        ch = TranslatorChannel(RA.group_plan(items, RA.group_of(it)), signing_key=b"plain-digest-key-0123456789abcdef", key_id="hub")
        m, _req, rc = ch.request("router", it["agent_id"], it["question"], RA.supplied(it))
        assert (rc.status.value, m.payload_sha256, m.contract, sorted(m.payload)) == (want["status"], want["payload_sha256"], want["contract"], want["keys"]), key
        seen += 1
    assert seen == len(pinned) == 44


# ============================================================================================ the revision is checked in full
def _tuples(rc, skip=("INT-REV-002", "INT-HANDOFF-009", "INT-HANDOFF-018")):
    return sorted((f.code, f.severity, tuple(sorted(f.claim_ids))) for f in rc.findings if f.code not in skip)


def test_a_revision_is_checked_exactly_as_a_first_answer():
    """Parity: the same text delivered as a revision and as a first answer on a fresh channel gives the same findings,
    coverage, constraint results and status, once the revision's own records are set aside."""
    case = answer()
    m2, _r, rq = issue(case, block_for(case))
    text = GOOD_TEXT + ' The foreman says "we sleep only when the bell allows".'
    claims = GOOD_CLAIMS + [dict(INVENTED, claim_text='The foreman says "we sleep only when the bell allows".',
                                 source_refs=[dict(document_id="doc-mill", excerpt="we sleep only when the bell allows")])]
    _a, rev_rc = case.ch.respond(m2.message_id, report(text, claims, report_id="rep-2"))
    fresh = answer(text, claims, report_id="rep-2")
    assert _tuples(rev_rc) == _tuples(fresh.rc) and "INT-REQ-003" in codes(rev_rc)
    assert [c.model_dump() for c in rev_rc.coverage] == [c.model_dump() for c in fresh.rc.coverage]
    assert [(c.constraint_id, c.satisfied) for c in rev_rc.constraint_results] == [(c.constraint_id, c.satisfied) for c in fresh.rc.constraint_results]
    assert rev_rc.status is fresh.rc.status


def test_int_handoff_018_refuses_a_revision_that_reuses_its_chains_report_id():
    case = answer()
    m2, _r, _rq = issue(case, block_for(case))
    a2, rc2 = case.ch.respond(m2.message_id, report(GOOD_TEXT, GOOD_CLAIMS, report_id="rep-1"))
    assert a2 is None and rc2.status is TransmissionStatus.REJECTED and "INT-HANDOFF-018" in codes(rc2)
    assert next(f for f in rc2.findings if f.code == "INT-HANDOFF-018").severity == "error"


def test_int_handoff_018_holds_when_the_revised_answer_was_rejected_and_never_stored():
    # an answer that carries a text the request never sent is REJECTED (INT-REQ-002) and never stored; it can be revised
    other = SuppliedText(document_id="doc-other", title="Other", text="A text the router never sent.")
    case = answer(report_docs=(DOC, other))
    assert case.a is None and "INT-REQ-002" in codes(case.rc) and "rep-1" not in case.ch.transmitted_reports
    m2, _r, rq = issue(case, block_for(case))
    assert rq.status is TransmissionStatus.ACCEPTED
    a2, rc2 = case.ch.respond(m2.message_id, report(GOOD_TEXT, GOOD_CLAIMS, report_id="rep-1"))
    assert a2 is None and "INT-HANDOFF-018" in codes(rc2) and "INT-HANDOFF-015" not in codes(rc2)
    ok, rc3 = case.ch.respond(m2.message_id, report(GOOD_TEXT, GOOD_CLAIMS, report_id="rep-3"))
    assert ok is not None and "INT-HANDOFF-018" not in codes(rc3)


def test_a_reply_to_a_revision_request_from_another_agent_is_still_refused():
    case = answer()
    m2, _r, _rq = issue(case, block_for(case))
    a2, rc2 = case.ch.respond(m2.message_id, report(GOOD_TEXT, GOOD_CLAIMS, report_id="rep-h", agent="history-specialist", subject="History", task_type="short_answer"))
    assert a2 is None and "INT-REQ-001" in codes(rc2)


# ============================================================================================ explicit supersession
def test_a_delivered_revision_supersedes_the_answer_and_its_formalizations_leave_the_pool():
    case = answer()
    case.ch.formalized["p1"] = object()  # a formalization pooled from the revised report, whatever its claims share
    case.ch.formalized_by["p1"] = ("english-specialist", "rep-1")
    m2, _r, _rq = issue(case, block_for(case))
    rewritten = [dict(claim_id="x1", claim_text="Labour becomes the clock of the mill in this passage", claim_role="point")]
    a2, rc2 = case.ch.respond(m2.message_id, report("Labour becomes the clock of the mill in this passage.", rewritten, report_id="rep-2"))
    assert a2 is not None
    sup = [f for f in rc2.findings if f.code == "INT-HANDOFF-009"]
    assert len(sup) == 1 and m2.message_id in sup[0].message_ids and sup[0].report_ids == ["rep-2", "rep-1"]
    assert case.ch.superseded["rep-1"] == "rep-2" and "p1" not in case.ch.formalized and "p1" not in case.ch.formalized_by


def test_a_rejected_revision_leaves_the_answer_as_it_was():
    case = answer()
    m2, _r, _rq = issue(case, block_for(case))
    a2, rc2 = case.ch.respond(m2.message_id, report(GOOD_TEXT, GOOD_CLAIMS, report_id="rep-1"))
    assert a2 is None and case.ch.superseded == {} and "rep-1" in case.ch.transmitted_reports


# ============================================================================================ INT-REV-002
def _revise(case, text: str, claims: list[dict], report_id: str = "rep-2"):
    m2, _r, rq = issue(case, block_for(case))
    assert rq.status is TransmissionStatus.ACCEPTED
    return case.ch.respond(m2.message_id, report(text, claims, report_id=report_id))


def _clean():
    return GOOD_TEXT, [dict(c) for c in GOOD_CLAIMS]


def _with(claims: list[dict], cid: str, **upd) -> list[dict]:
    return [dict(c, **upd) if c["claim_id"] == cid else c for c in claims]


PRESERVATION = {
    "a claim no flaw named dropped": (lambda t, c: (t, [x for x in c if x["claim_id"] != "p1"]), "are gone"),
    "an exact figure made approximate": (lambda t, c: (t.replace("42%", "about 40%"), _with(c, "f1", claim_text="In 1833 the mill employed about 40% of the town.")),
                                         "made approximate"),
    "an exact figure turned into a range": (lambda t, c: (t.replace("42%", "40-45%"), _with(c, "f1", claim_text="In 1833 the mill employed 40-45% of the town.")),
                                            "turned into a range"),
    "a figure no source states": (lambda t, c: (t + " About 300 children worked there.", c + [dict(claim_id="f2", claim_text="About 300 children worked there.",
                                                                                                    claim_role="evidence")]), "no source states"),
    "the request's own text echoed": (lambda t, c: (t + " Quote the words exactly as the text gives them.",
                                                     c + [dict(claim_id="n1", claim_text="Quote the words exactly as the text gives them.", claim_role="point")]),
                                      "own text or the system's check codes"),
    "a check code echoed": (lambda t, c: (t + " This answer passed INT-REQ-003.", c + [dict(claim_id="n2", claim_text="This answer passed INT-REQ-003.",
                                                                                              claim_role="point")]), "check codes"),
}


@pytest.mark.parametrize("case_name", sorted(PRESERVATION))
def test_int_rev_002_names_each_preservation_case_once(case_name):
    build, phrase = PRESERVATION[case_name]
    case = answer()
    text, claims = build(*_clean())
    _a, rc = _revise(case, text, claims)
    named = [f for f in rc.findings if f.code == "INT-REV-002" and phrase in f.message]
    assert len(named) == 1 and named[0].severity == "warning", (case_name, [f.message for f in rc.findings if f.code == "INT-REV-002"])


def test_int_rev_002_names_raised_certainty_an_asserted_definition_and_a_note_turned_into_content():
    hedged = [dict(c) for c in GOOD_CLAIMS] + [dict(claim_id="d1", claim_text="Let the bell stand for the owners' power.", claim_role="analysis", certainty="possible"),
                                               dict(claim_id="n1", claim_text="Note: the extract is anonymous.", claim_role="other", materiality="supporting")]
    text = GOOD_TEXT + " Let the bell stand for the owners' power. Note: the extract is anonymous."
    case = answer(text, hedged + [INVENTED])
    revised = [dict(c) for c in GOOD_CLAIMS] + [dict(claim_id="d1", claim_text="The bell stands for the owners' power.", claim_role="analysis"),
                                                dict(claim_id="n1", claim_text="Note: the extract is anonymous.", claim_role="point")]
    _a, rc = _revise(case, GOOD_TEXT + " The bell stands for the owners' power. Note: the extract is anonymous.", revised)
    msgs = [f.message for f in rc.findings if f.code == "INT-REV-002"]
    assert sum("certainty of claims" in m for m in msgs) == 1 and sum("turned into an assertion" in m for m in msgs) == 1
    assert sum("note of claims" in m for m in msgs) == 1


def test_a_clean_minimal_revision_has_no_preservation_finding():
    case = answer()
    _a, rc = _revise(case, *_clean())
    assert "INT-REV-002" not in codes(rc) and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS  # INT-HANDOFF-009 only
    assert codes(rc) == ["INT-HANDOFF-009"]


# ============================================================================================ nothing is rewritten
def test_feedback_rewrites_nothing_of_the_answer_it_revises():
    case = answer()
    receipt_before = case.rc.model_dump(mode="json")
    msg_before = case.ch.log.get(case.a.message_id).model_dump(mode="json")
    held_before = case.ch.transmitted_reports["rep-1"].model_dump(mode="json")
    m2, _r, _rq = issue(case, block_for(case))
    case.ch.respond(m2.message_id, report(*_clean(), report_id="rep-2"))
    assert case.rc.model_dump(mode="json") == receipt_before
    assert next(r for r in case.ch.receipts if r.message_id == case.a.message_id).model_dump(mode="json") == receipt_before
    assert case.ch.log.get(case.a.message_id).model_dump(mode="json") == msg_before
    assert case.ch.transmitted_reports["rep-1"].model_dump(mode="json") == held_before
