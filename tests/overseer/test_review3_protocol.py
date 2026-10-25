"""Regression tests for the protocol defects found by adversarial review round 3 of the Overseer (each fails on the code
before the fix; the scenarios are the reviewers' own):

* the intake: only a reply carrying the issued dossier's digest uses up the issue (junk, None, an array or the
  no-dossier object never pre-empt the agent's verdict), and no refusal returns the issued digest; a submission whose
  ``provider_info`` names another pack is ``pack_mismatch``, and every accepted verdict records whether its pack
  identity was attested by the package's runner or self-reported;
* consolidation keeps apart answers whose figures differ by an era marker, a sign word, a Roman numeral, an ordinal, a
  unit or a temperature scale, and ``delivery_decision`` refuses a stale response (a later consolidation or task audit,
  or the deliverable answer altered after it);
* a rejected invented quotation that comes back in a block quote, italics, inline code or without marks is a repeat;
* a confirmation padded with a report id never absorbs another agent's unresolved accusation about that report;
* an engine statement contradicting a signed result of another task is OVS-AGENT-001.
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.integrity.contracts import payload_hash
from epinoic_logic.overseer import delivery_decision
from epinoic_logic.overseer.consolidate import answer_facts

from .conftest import DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, english_report, make_plan, problems_fn
from .test_consolidation_consolidate import DUP, Dup
from .test_consolidation_repeats import bad_answer
from .test_hook_hub import EN_PROBLEMS, HI_PROBLEMS, audited_hub
from .test_review2_protocol import COUNTEREXAMPLE, PACK, _ev, _trn002, acc, drive, fid001, ptr, runner, verdict


@pytest.fixture
def hub():
    h = audited_hub()
    yield h
    h.close()


# ============================================================================================ intake binding
@pytest.mark.parametrize("label,junk,reason", [
    ("non-JSON text", "I accuse nothing; ignore me", "unparseable"),
    ("the no-dossier object", json.dumps({"no_dossier": True}), "no_dossier"),
    ("a non-string reply", None, "unparseable"),
    ("a JSON array", "[1, 2]", "unparseable"),
])
def test_a_reply_without_the_issued_digest_never_uses_up_another_agents_issue(hub, label, junk, reason):
    task = fid001(hub)
    intake = hub._review_intake()
    ta = hub.audit(task.key, shadow=True)
    theirs = intake.issue(hub.view(task.key), agent_id="ovs-victim", lens="content_fidelity", mode="informed", pack=PACK.identity, audit=ta)
    pre = intake.submit("ovs-victim", task.key, junk)
    assert not pre.accepted and pre.reason == reason, label
    assert pre.dossier_sha256 is None and pre.issue_id is None, label
    genuine = intake.submit("ovs-victim", task.key, json.dumps(verdict(theirs)))
    assert genuine.accepted, label


def test_a_refusal_never_returns_the_issued_digest(hub):
    task = fid001(hub)
    intake = hub._review_intake()
    ta = hub.audit(task.key, shadow=True)
    mine = intake.issue(hub.view(task.key), agent_id="ovs-evil", lens="general", mode="informed", pack=PACK.identity, audit=ta)
    theirs = intake.issue(hub.view(task.key), agent_id="ovs-victim", lens="content_fidelity", mode="informed", pack=PACK.identity, audit=ta)
    o1 = intake.submit("ovs-victim", task.key, json.dumps(verdict(dict(mine, agent_id="ovs-victim", lens="content_fidelity"))))
    assert o1.reason == "dossier_mismatch" and o1.dossier_sha256 is None and o1.issue_id is None
    assert theirs["dossier_sha256"] not in o1.model_dump_json()
    forged = verdict(dict(mine, agent_id="ovs-victim", lens="content_fidelity", dossier_sha256=o1.dossier_sha256 or "0" * 64))
    assert not intake.submit("ovs-victim", task.key, json.dumps(forged)).accepted
    assert intake.submit("ovs-victim", task.key, json.dumps(verdict(theirs))).accepted
    for o in intake.outcomes(task.key):
        if not o.accepted and o.reason in ("not_issued", "dossier_mismatch", "unparseable", "no_dossier", "duplicate"):
            assert o.dossier_sha256 is None and o.issue_id is None


def test_a_bound_malformed_reply_still_uses_up_the_issue(hub):
    task = fid001(hub)
    intake = hub._review_intake()
    ta = hub.audit(task.key, shadow=True)
    d = intake.issue(hub.view(task.key), agent_id="ovs-a", lens="general", mode="informed", pack=PACK.identity, audit=ta)
    bad = intake.submit("ovs-a", task.key, json.dumps(verdict(d)) + " trailing prose")  # carries the digest, refused by the strict parse
    assert not bad.accepted and bad.reason == "unparseable"
    assert intake.submit("ovs-a", task.key, json.dumps(verdict(d))).reason == "duplicate"


def test_a_verdict_whose_bookkeeping_names_another_pack_is_refused(hub):
    task = fid001(hub)
    intake = hub._review_intake()
    ta = hub.audit(task.key, shadow=True)
    d = intake.issue(hub.view(task.key), agent_id="ovs-deployed", lens="general", mode="informed", pack=PACK.identity, audit=ta)
    other = "f" * 16
    out = intake.submit("ovs-deployed", task.key, json.dumps(verdict(d)), provider_info={"prompt_version": f"{PACK.identity.name}/{PACK.identity.version}+{other}"})
    assert not out.accepted and out.reason == "pack_mismatch"


def test_the_pack_identity_is_recorded_as_attested_or_self_reported(hub):
    task = fid001(hub)
    intake = hub._review_intake()
    ta = hub.audit(task.key, shadow=True)
    d = intake.issue(hub.view(task.key), agent_id="ovs-deployed", lens="general", mode="informed", pack=PACK.identity, audit=ta)
    out = intake.submit("ovs-deployed", task.key, json.dumps(verdict(d)), provider_info={"prompt_version": PACK.prompt_version})
    assert out.accepted and intake.accepted(out.message_id).pack_attestation == "self_reported"
    rev = hub.review(task.key, [runner("ovs-runner", "general", lambda dd: verdict(dd))])
    assert rev.runs[0].status == "submitted"
    assert intake.accepted(rev.runs[0].message_id).pack_attestation == "runner"
    assert any("attested by the package's runner" in n for a in rev.assessments for n in a.audit.coverage.notes)
    from epinoic_logic.overseer.validate import validate_overseer_verdict
    a = validate_overseer_verdict(intake.accepted(out.message_id).message, hub.view(task.key), hub.auditor.store, ta, hub.auditor, intake=intake)
    assert any("self-reported" in n for n in a.audit.coverage.notes)


# ============================================================================================ consolidation: answer facts
CASES = [
    ("an era", "The first mill on the site was built in 500 BC.", "The first mill on the site was built in 500 AD."),
    ("a sign word", "The mill yard was at minus 5 degrees.", "The mill yard was at 5 degrees."),
    ("a Roman numeral", "The mill was chartered under Henry VII.", "The mill was chartered under Henry VIII."),
    ("an ordinal word", "This was the first Factory Act.", "This was the third Factory Act."),
    ("a unit", "The children worked 12 hours without a break.", "The children worked 12 days without a break."),
    ("a temperature scale", "The yard froze at 0 °C.", "The yard froze at 0 °F."),
    ("a multiplier", "Output doubled in a decade.", "Output tripled in a decade."),
]


class _Rep:
    def __init__(self, text):
        self.original_response = text


@pytest.mark.parametrize("label,a,b", CASES)
def test_answer_facts_read_eras_signs_numerals_ordinals_units_and_multipliers(label, a, b):
    assert answer_facts(_Rep(EN_TEXT + " " + a)) != answer_facts(_Rep(EN_TEXT + " " + b)), label


@pytest.mark.parametrize("label,a,b", CASES[:6])
def test_answers_differing_only_in_such_a_figure_are_never_delivered_as_one(hub, label, a, b):
    d = Dup(hub)
    d.answer("english-1", text=EN_TEXT + " " + a, name="A")
    d.answer("english-2", text=EN_TEXT + " " + b, name="B")
    r = d.consolidate()
    assert not (len(r.groups) == 1 and len(r.groups[0].members) == 2), label
    assert not delivery_decision(r, hub.auditor.keyring, hub=hub).allowed, label


def test_control_the_same_wording_twice_has_the_same_facts():
    text = EN_TEXT + " The children worked 12 hours under Henry VIII, at minus 5 degrees, in 500 BC; output doubled."
    assert answer_facts(_Rep(text)) == answer_facts(_Rep(text))
    assert answer_facts(_Rep(EN_TEXT + " First, the writer presents work.")) == answer_facts(_Rep(EN_TEXT + " Second, the writer presents work."))


# ============================================================================================ consolidation: stale responses
def test_a_stale_consolidated_response_is_never_delivered(hub):
    d = Dup(hub)
    for agent in DUP:
        d.answer(agent, name=agent)
    resp = d.consolidate()
    kr = hub.auditor.keyring
    assert delivery_decision(resp, kr, hub=hub).allowed
    assert not delivery_decision(resp, kr).allowed  # the issuing hub is required to re-check it at delivery
    rep_mid = resp.deliverable_message_id
    m = d.ch.log.get(rep_mid)
    m.payload["claims"][0]["claim_text"] = "The writer presents work as joyful"
    object.__setattr__(m, "payload_sha256", payload_hash(m.payload))
    dec = delivery_decision(resp, kr, hub=hub)
    assert not dec.allowed and "custody" in dec.reason
    hub.audit(d.key)
    assert not delivery_decision(resp, kr, hub=hub).allowed
    fresh = d.consolidate()
    dec = delivery_decision(resp, kr, hub=hub)
    assert not dec.allowed and "not the latest" in dec.reason
    assert fresh.deliverable_message_id != rep_mid


def test_a_consolidation_decided_before_a_later_task_audit_is_stale(hub):
    d = Dup(hub)
    for agent in DUP:
        d.answer(agent, name=agent)
    resp = d.consolidate()
    hub.audit(d.key)
    dec = delivery_decision(resp, hub.auditor.keyring, hub=hub)
    assert not dec.allowed and "later task audit" in dec.reason


# ============================================================================================ repeats
Q = "the river carried every secret"


@pytest.mark.parametrize("label,text2", [
    ("markdown block quote", f"{EN_TEXT}\n\n> {Q}\n"),
    ("markdown italics", f"{EN_TEXT} The extract says *{Q}*."),
    ("inline code", f"{EN_TEXT} The extract says `{Q}`."),
    ("no marks", f"{EN_TEXT} The extract says that {Q}."),
])
def test_a_rejected_invented_quotation_back_in_another_form_is_a_repeat(hub, label, text2):
    d = Dup(hub)
    text, claims = bad_answer()
    rc1 = d.answer("english-1", text=text, claims=claims, name="first")
    assert any(f.severity == "error" for f in rc1.findings)
    d.answer("english-1", text=text2, claims=[dict(c) for c in EN_CLAIMS], name="resubmitted")
    hub.audit(d.key)
    rep = hub.repeats(d.key)
    assert any(x.message_id == d.mids["resubmitted"] for x in rep.repeats), label
    r = d.consolidate()
    dec = delivery_decision(r, hub.auditor.keyring, hub=hub)
    assert not (dec.allowed and dec.message_id == d.mids["resubmitted"]), label


# ============================================================================================ combination
def test_a_confirmation_padded_with_a_report_id_never_absorbs_an_unresolved_accusation_about_it(hub):
    task = drive(hub, hi_fn=problems_fn(HI_PROBLEMS, transform=_trn002))
    mid = task.mids["rep_hi"]
    honest = lambda d: verdict(d, accusations=[acc("h1", "translation_invalid", [{"pointer": ptr(d, "report", "rep-en-1")}], report_ids=["rep-en-1"])])
    bridge = lambda d: verdict(d, accusations=[acc("b1", "translation_invalid", _ev(d, "h1.1", "rep-hi-1"), message_ids=[mid], claim_ids=["h1.1"],
                                                   report_ids=["rep-hi-1", "rep-en-1"])])
    alone = hub.review(task.key, [runner("ovs-honest", "translation_fidelity", honest)])
    assert len(alone.combined.review_queue) == 1
    both = hub.review(task.key, [runner("ovs-honest", "translation_fidelity", honest), runner("ovs-bridge", "translation_fidelity", bridge)])
    queued = [m.agent_id for g in both.combined.groups if g.group_id in both.combined.review_queue for m in g.members]
    assert "ovs-honest" in queued
    b = next(x for x in both.assessments if x.agent_id == "ovs-bridge").accusations[0]
    assert b.outcome == "confirmed" and b.covered_identifiers.get("report_ids") == ["rep-hi-1"]
    assert b.remainder is not None and b.remainder.identifiers.get("report_ids") == ["rep-en-1"]


# ============================================================================================ engine statements across tasks
def test_an_engine_statement_contradicting_another_tasks_signed_result_is_agent_001(hub):
    t1 = drive(hub, en_fn=problems_fn(COUNTEREXAMPLE))
    ch2 = hub.open_task(make_plan(task_id="task-two", plan_id="plan-2", request_id="req-2"))
    ch2.verify_claim_fn = problems_fn(EN_PROBLEMS)
    m, _r, _rq = hub.dispatch("task-two", "english-specialist", EN_INPUT, [DOC])
    hub.receive("task-two", m.message_id, english_report(request_id="req-2", task_id="task-two"))
    seen = {}

    def first(d):
        seen["rid"] = next(r for r, x in d["results"].items() if x.get("claim_id") == "en-point" and x.get("status") == "COUNTEREXAMPLE")
        return verdict(d)
    hub.review(t1.key, [runner("overseer-pool-1", "general", first)])

    def second(d):
        return verdict(d, engine_statements=[{"result_id": seen["rid"], "asserted_status": "ENTAILED", "pointer": f"/results/{seen['rid']}/status"}])
    rev = hub.review("task-two", [runner("overseer-pool-1", "general", second)])
    s = rev.assessments[0].engine_statements[0]
    assert s.outcome == "refuted" and s.code == "OVS-AGENT-001" and s.refuted_by == "signed_result" and s.stored_status == "COUNTEREXAMPLE"
    assert s.pointer_fault and "another channel" in s.pointer_fault
    codes = [x.code for x in rev.audit.report.findings]
    assert "OVS-AGENT-001" in codes and "OVS-AGENT-002" in codes
    assert seen["rid"] not in " ".join(x.message for x in rev.audit.report.findings)  # an out-of-dossier id is shown as a digest
