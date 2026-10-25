"""Repeated faults (design section 19): every error-level fault of an answer gets a deterministic signature (code,
normalised offending claim or quoted phrase, figures); the same signature again in the same task is a repeated fault
(OVS-REP-001, error), never delivered or consolidated, and counted per agent.

Covered: the normalisation (what a trivial rewording is, and what it is not); a faulty answer repeated by two agents;
a rejected answer (channel REJECTED, and excluded for an error finding) resubmitted with a trivial rewording; a
non-trivial rewording that is a new fault, not a repeat; an auditor fault (OVS-FID-001) repeated; a repeat across a
reopened task; counts per agent and occurrence numbers; that a repeat changes no clearance and no receipt; and the
refusals (several tasks, a degraded view, a channel twice, an audit that does not verify)."""
from __future__ import annotations

import pytest

from epinoic_logic.overseer import OVS_CODES, OverseerView, detect_repeats, may_deliver
from epinoic_logic.overseer.repeats import (
    SIGNATURE_RULE, content_form, fault_occurrences, fault_signature, figures_of, quotations_of,
)
from epinoic_logic.translate.contracts import ClaimRecord, SuppliedText

from .conftest import DOC, EN_CLAIMS, EN_TEXT, english_report
from .test_consolidation_consolidate import BAD_CLAIM, DUP, INVENTED, Dup
from .test_hook_hub import audited_hub

OTHER_DOC = SuppliedText(document_id="doc-other", title="Other", author="Anonymous", text="Another text entirely.")
X_CLAIM = dict(claim_id="en-x", claim_text="The writer celebrates the joy of labour", claim_role="interpretation", materiality="supporting")


@pytest.fixture
def hub():
    h = audited_hub()
    yield h
    h.close()


def bad_answer(quote: str = "the river carried every secret", *, lead: str = "The extract says", claim_text=None):
    text = f'{EN_TEXT} {lead} "{quote}".'
    claim = dict(BAD_CLAIM, claim_text=claim_text or quote, source_refs=[dict(document_id="doc-mill", excerpt=quote)])
    return text, [*[dict(c) for c in EN_CLAIMS], claim]


# ============================================================================================ normalisation and signatures
def test_content_form_folds_only_case_punctuation_markdown_whitespace_and_articles():
    assert content_form("The *Treaty*  of Versailles, signed in 1,919!") == content_form("treaty of versailles signed in 1919")
    assert content_form("A mill ran") == content_form("the mill ran") == "mill ran"
    assert content_form("The mill never ran") != content_form("The mill ran")
    assert content_form("ran 1.5 hours") != content_form("ran 15 hours") and content_form("1,000 men") == content_form("1000 men")
    assert content_form("Mill ran") != content_form("Ran mill")
    assert content_form(None) == "" and content_form("— … !!") == ""


def test_figures_keep_scale_words_and_dates():
    assert figures_of("from 1.9 to 6.1 million in March 1917") == ("1.9", "1917", "march 1917", "6.1 million")  # by length, then text
    assert figures_of("6.1 billion") != figures_of("6.1 million") and figures_of("two million") == ("2 million",)
    assert figures_of("no figure here") == ()


def test_quoted_phrases_are_read_from_the_claim_text_and_its_source_excerpts():
    c = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="English A: Literature", task_type="analytical_paragraph",
                    claim_id="c", claim_text='The foreman says "We work until the bell"', source_refs=[dict(document_id="d", excerpt="counted every hour in coal")])
    assert quotations_of(c) == ("counted every hour in coal", "we work until bell")


def test_the_signature_names_its_rule_and_changes_with_any_part():
    base = fault_signature("INT-REQ-003", "quotation", "river carried every secret", ())
    assert base == fault_signature("INT-REQ-003", "quotation", "river carried every secret", [])
    for other in (fault_signature("INT-REQ-002", "quotation", "river carried every secret", ()),
                  fault_signature("INT-REQ-003", "claim", "river carried every secret", ()),
                  fault_signature("INT-REQ-003", "quotation", "river carried every song", ()),
                  fault_signature("INT-REQ-003", "quotation", "river carried every secret", ("12",))):
        assert other != base
    assert SIGNATURE_RULE == "fault-signature/1" and OVS_CODES["OVS-REP-001"][0] == "error"


# ============================================================================================ a faulty answer repeated by two agents
def test_a_faulty_answer_repeated_by_two_agents_is_a_repeated_fault_never_delivered_or_consolidated(hub):
    d = Dup(hub)
    text, claims = bad_answer()
    d.answer("english-1", text=text, claims=claims, name="first")
    d.answer("english-2", text=text, claims=claims, name="again")
    d.answer("english-3", name="clean")
    rep = hub.repeats(d.key)
    assert rep.answers == 3 and len(rep.repeats) == 1 and rep.counts == {"english-2": 1}
    rr = rep.repeats[0]
    assert rr.code == "INT-REQ-003" and rr.anchor_kind == "quotation" and rr.anchor == "river carried every secret"
    assert rr.message_id == d.mids["again"] and rr.first_message_id == d.mids["first"] and rr.agent_id == "english-2" and rr.first_agent_id == "english-1"
    assert rr.occurrence == 2 and not rr.same_agent
    f = rep.findings[0]
    assert f.code == "OVS-REP-001" and f.severity == "error" and f.message_ids == [d.mids["again"], d.mids["first"]]
    assert f.agent_ids == ["english-2", "english-1"] and "never delivered or consolidated" in f.message
    r = d.consolidate()
    ex = {e.message_id: e for e in r.excluded}
    assert set(ex) == {d.mids["first"], d.mids["again"]} and ex[d.mids["again"]].repeated and not ex[d.mids["first"]].repeated
    assert "OVS-REP-001" in ex[d.mids["again"]].codes and ex[d.mids["again"]].repeat_signatures == [rr.signature]
    assert r.repeats == [rr] and r.repeat_counts == {"english-2": 1} and "OVS-REP-001" in {f.code for f in r.findings}
    assert r.status == "CONSOLIDATED_WITH_FINDINGS" and r.deliverable_message_id == d.mids["clean"]
    assert not may_deliver(r, hub.auditor.keyring, message_id=d.mids["again"])


def test_three_occurrences_are_numbered_and_counted_per_agent(hub):
    d = Dup(hub)
    text, claims = bad_answer()
    for a in DUP:
        d.answer(a, text=text, claims=claims, name=a)
    d.answer("english-2", text=text, claims=claims, name="english-2-again")
    rep = hub.repeats(d.key)
    assert [r.occurrence for r in rep.repeats] == [2, 3, 4] and rep.counts == {"english-2": 2, "english-3": 1}
    assert [r.same_agent for r in rep.repeats] == [False, False, False]  # the original is english-1's
    assert all(r.first_message_id == d.mids["english-1"] for r in rep.repeats)


# ============================================================================================ resubmission after rejection
def test_a_channel_rejected_answer_resubmitted_with_a_trivial_rewording_is_a_repeat_of_the_same_agent(hub):
    d = Dup(hub)
    # the report cites a document the request did not carry: INT-REQ-002, blocking -> REJECTED
    req = d.ask("english-1")
    r1 = english_report(report_id="rep-a", agent="english-1", task_id=d.key, docs=(DOC, OTHER_DOC))
    _m, rc1 = hub.receive(d.key, req, r1)
    assert rc1.status.value == "REJECTED" and "INT-REQ-002" in [f.code for f in rc1.findings]
    # the router asks again; the agent resubmits the same fault, its prose changed only in case and punctuation
    req2 = d.ask("english-1")
    reworded = EN_TEXT.replace("The writer presents", "the writer presents").replace(", so", "; so")
    claims = [dict(c) for c in EN_CLAIMS]
    claims[0] = dict(claims[0], claim_text="the writer presents work as endless")
    r2 = english_report(text=reworded, claims=claims, report_id="rep-b", agent="english-1", task_id=d.key, docs=(DOC, OTHER_DOC))
    _m, rc2 = hub.receive(d.key, req2, r2)
    assert rc2.status.value == "REJECTED"
    rep = hub.repeats(d.key)
    # two faults, each repeated: the text cited outside the request (INT-REQ-002) and outside the plan's scope (INT-HANDOFF-004)
    assert sorted(r.code for r in rep.repeats) == ["INT-HANDOFF-004", "INT-REQ-002"] and rep.counts == {"english-1": 2}
    for r in rep.repeats:
        assert r.same_agent and r.message_id == rc2.message_id and r.first_message_id == rc1.message_id
    req002 = next(r for r in rep.repeats if r.code == "INT-REQ-002")
    # a finding that names no claim is signed by its message, the answer's own ids stripped and the document kept
    assert req002.anchor_kind == "finding" and "doc other" in req002.anchor and "rep" not in req002.anchor.split()


def test_an_excluded_answer_resubmitted_with_a_trivial_rewording_is_a_repeat(hub):
    d = Dup(hub)
    text, claims = bad_answer()
    d.answer("english-1", text=text, claims=claims, name="first")
    # trivial rewording: another lead-in, the quotation capitalised and closed with an exclamation mark
    text2, claims2 = bad_answer("The river carried every secret!", lead="In the extract we read")
    d.answer("english-1", text=text2, claims=claims2, name="resubmitted")
    rep = hub.repeats(d.key)
    assert len(rep.repeats) == 1 and rep.repeats[0].same_agent and rep.repeats[0].message_id == d.mids["resubmitted"]
    r = d.consolidate()
    assert r.status == "NO_DELIVERABLE_OUTPUT" and {e.message_id for e in r.excluded if e.repeated} == {d.mids["resubmitted"]}


def test_a_non_trivial_rewording_is_a_new_fault_not_a_repeat(hub):
    d = Dup(hub)
    text, claims = bad_answer()
    d.answer("english-1", text=text, claims=claims, name="first")
    text2, claims2 = bad_answer("the river carried every song")
    d.answer("english-2", text=text2, claims=claims2, name="other")
    rep = hub.repeats(d.key)
    assert rep.repeats == [] and rep.counts == {} and len({o.signature for o in rep.occurrences}) == 2
    r = d.consolidate()
    assert not any(e.repeated for e in r.excluded) and r.repeats == []


def test_an_auditor_fault_about_what_the_agent_said_is_signed_and_repeated(hub):
    d = Dup(hub)
    claims = [*[dict(c) for c in EN_CLAIMS], X_CLAIM]  # a claim its response does not carry: OVS-FID-001 (the receipt is clean)
    rc1 = d.answer("english-1", claims=claims, name="a")
    rc2 = d.answer("english-2", claims=claims, name="b")
    # the receipts carry no finding of the fault (the merged channel adds only the duplication's INT-REQ-016 to the second)
    assert rc1.status.value == "ACCEPTED" and rc1.findings == []
    assert rc2.status.value == "ACCEPTED_WITH_FINDINGS" and [(f.code, f.severity) for f in rc2.findings] == [("INT-REQ-016", "warning")]
    rep = hub.repeats(d.key)
    fid = [o for o in rep.occurrences if o.code == "OVS-FID-001"]
    assert len(fid) == 2 and all(o.source == "audit" and o.anchor_kind == "claim" and o.anchor == "writer celebrates joy of labour" for o in fid)
    assert [r.code for r in rep.repeats] == ["OVS-FID-001"] and rep.repeats[0].message_id == d.mids["b"]
    r = d.consolidate()
    assert {e.message_id for e in r.excluded} == {d.mids["a"], d.mids["b"]} and r.status == "NO_DELIVERABLE_OUTPUT"
    assert all(e.clearance == "AUDIT_FAILED" and "OVS-FID-001" in e.codes for e in r.excluded)


def test_a_repeat_across_a_reopened_task_counts_against_the_later_answer(hub):
    d = Dup(hub)
    text, claims = bad_answer()
    d.answer("english-1", text=text, claims=claims, name="old")
    old_uid = d.ch.channel_uid
    hub.audit(d.key)
    e = Dup(hub)  # the same task id opened again: the old channel is kept in closed_channels
    assert old_uid in hub.closed_channels and e.ch.channel_uid != old_uid
    e.answer("english-2", text=text, claims=claims, name="new")
    rep = hub.repeats(e.key)
    assert rep.channel_uids == [old_uid, e.ch.channel_uid] and len(rep.repeats) == 1
    rr = rep.repeats[0]
    assert rr.first_channel_uid == old_uid and rr.channel_uid == e.ch.channel_uid and rr.first_message_id == d.mids["old"]
    r = e.consolidate()
    assert r.excluded[0].repeated and r.repeats == [rr]


# ============================================================================================ non-interference and refusals
def test_a_repeated_fault_changes_no_clearance_and_no_receipt(hub):
    d = Dup(hub)
    text, claims = bad_answer()
    d.answer("english-1", text=text, claims=claims, name="first")
    d.answer("english-2", text=text, claims=claims, name="again")
    before = {m: hub.clearance(d.key, m).state for m in d.mids.values()}
    receipts = [r.model_dump(mode="json") for r in d.ch.receipts]
    assert hub.repeats(d.key).repeats and d.consolidate().repeats
    assert {m: hub.clearance(d.key, m).state for m in d.mids.values()} == before
    assert [r.model_dump(mode="json") for r in d.ch.receipts] == receipts
    task = hub.audit(d.key)
    assert not any(f.code.startswith(("OVS-REP", "OVS-CONS")) for f in task.report.findings)  # never in a task audit


def test_only_answers_are_signed_and_each_signature_counts_once_per_answer(hub):
    d = Dup(hub)
    text, claims = bad_answer()
    claims.append(dict(claims[-1], claim_id="en-bad-2"))  # the same invented quotation twice in one answer
    d.answer("english-1", text=text, claims=claims, name="a")
    view = hub.view(d.key)
    occ = fault_occurrences(view, view.by_message[d.mids["a"]])
    assert len([o for o in occ if o.code == "INT-REQ-003"]) == 1
    req = next(t for t in view.transfers if t.kind == "request")
    assert fault_occurrences(view, req) == []
    assert hub.repeats(d.key).repeats == []


def test_detect_repeats_refuses_views_it_cannot_trust(hub):
    d = Dup(hub)
    text, claims = bad_answer()
    d.answer("english-1", text=text, claims=claims, name="a")
    a = hub.auditor
    view = a.view(d.ch.channel_uid)
    with pytest.raises(ValueError, match="no view"):
        detect_repeats([])
    with pytest.raises(ValueError, match="twice"):
        detect_repeats([view, view])
    with pytest.raises(ValueError, match="journaled views"):
        detect_repeats([OverseerView.from_channel(d.ch)])
    other = Dup(hub, task_id="task-other")
    other.answer("english-1", name="x")
    with pytest.raises(ValueError, match="one task"):
        detect_repeats([view, a.view(other.ch.channel_uid)])
    audit = a.audit(d.ch.channel_uid)
    with pytest.raises(ValueError, match="does not verify"):
        detect_repeats([view], {view.channel_uid: audit.model_copy(update={"message_ids": []})}, keyring=a.keyring)
    with pytest.raises(ValueError, match="not that channel's task audit"):
        detect_repeats([view], {"another-uid": audit})
    assert detect_repeats([view], {view.channel_uid: audit}, keyring=a.keyring).answers == 1
