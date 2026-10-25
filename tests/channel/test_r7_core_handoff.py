"""Channel regressions from the round-7 arena fixers' hand-off (owner: core).

* parser-safety-6 / robustness-and-contracts-3: ``request`` (and ``RouterHub.dispatch``) raised for a request over the
  contract's limits (more than 64 constraints, more than 400,000 characters), an empty or white-space request, a request
  text or an agent id that is not a string. It now returns a REJECTED receipt with INT-REQ-009 naming every problem.
* robustness-and-contracts-1: ``receive``/``respond`` raised for a request message id that is not a string of 1 to 128
  characters; it is now REJECTED with INT-REQ-000.
* robustness-and-contracts-8: a JSON report cut off in transit was parsed as prose and delivered with a claim cut
  mid-word; it is REJECTED with INT-REQ-009, and a complete JSON report sent as text is validated as a report.
* correctness-2: a claim whose outcome is displayed INVALID_FORMALIZATION or INTERNAL_ERROR left a clean ACCEPTED receipt.
* correctness-3: INT-REQ-007 was charged from an engine result the composer rejected.
* security-3: a specialist could supply its own text for a document the router never sent, or replace a sent one.
* router-envelope-3: a specialist could relay a report it never delivered, which superseded the delivered one.
* router-envelope-2: a dependent agent's claim stating a check result about its peer was delivered with no finding.
* r7 history hand-off 2: an uncredited quotation found in no supplied text was only unverifiable (CORE-SRC-003).
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.outcome import compose_outcome, verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from .test_channel import DOC, GOOD_CLAIMS, GOOD_TEXT, USER_INPUT, english_report, plan

KEY = b"r7-core-channel-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
TASK = "task-r"
HISTORY_TEXT = "The 1929 crash followed speculative buying on margin. Banks failed in 1930 and 1931, so credit contracted."


def history_hub(agents=("history-specialist", "combinator")):
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="plan-r", request_id="req-r", task_id=TASK, subject="History", task_type="short_answer", selected_agent_ids=list(agents)))
    return hub, ch


def codes(rc) -> list[str]:
    return [f.code for f in rc.findings]


# ------------------------------------------------------------------ requests never raise


@pytest.mark.parametrize("user_input,agent", [
    ("".join(f"Answer in at most {100 + i} words. " for i in range(65)), "history-specialist"),  # 65 different constraints
    ("Explain the crash. " * 21053, "history-specialist"),  # over 400,000 characters
    ("", "history-specialist"), (" ", "history-specialist"), ("\n\n\n", "history-specialist"),
    (None, "history-specialist"), (5, "history-specialist"),
    ("Explain the causes of the 1929 crash.", None), ("Explain the causes of the 1929 crash.", 7), ("Explain the causes of the 1929 crash.", "\ud83d"),
])
def test_a_malformed_request_is_rejected_with_int_req_009_and_never_raises(user_input, agent):
    hub, ch = history_hub()
    msg, req, rc = hub.dispatch(TASK, agent, user_input)
    assert msg is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rc)
    assert req.user_input and len(req.user_input) <= 400_000 and len(req.constraints) <= 64 and len(req.items) <= 64
    assert not ch.requests  # a refused request is not stored


def test_repeated_identical_constraints_are_one_bound_and_the_request_is_accepted():
    hub, ch = history_hub()
    msg, req, rc = hub.dispatch(TASK, "history-specialist", "Explain the crash. " + "Write about 500 words. " * 40)
    assert msg is not None and rc.status is TransmissionStatus.ACCEPTED
    assert sorted((c.kind, c.value) for c in req.constraints) == [("max_words", "550"), ("min_words", "450")] or len(req.constraints) <= 64


def test_the_request_record_of_over_many_constraints_keeps_the_strongest_bounds():
    hub, ch = history_hub()
    _msg, req, rc = hub.dispatch(TASK, "history-specialist", "".join(f"Answer in at most {100 + i} words. " for i in range(65)))
    assert rc.status is TransmissionStatus.REJECTED
    assert min(int(c.value) for c in req.constraints if c.kind == "max_words") == 100


def test_a_well_formed_request_is_unchanged():
    hub, ch = history_hub()
    msg, req, rc = hub.dispatch(TASK, "history-specialist", "Explain the causes of the 1929 crash.")
    assert msg is not None and rc.status is TransmissionStatus.ACCEPTED and codes(rc) == []


# ------------------------------------------------------------------ replies to a malformed request message id


@pytest.mark.parametrize("mid", [None, 7, "m" * 500, "", ["x"]])
def test_a_reply_to_a_malformed_request_message_id_is_rejected_with_int_req_000(mid):
    hub, ch = history_hub()
    m, _req, _rq = hub.dispatch(TASK, "history-specialist", "Explain the causes of the 1929 crash.")
    reply, rc = hub.receive(TASK, mid, HISTORY_TEXT, agent_id="history-specialist", report_id="r9")
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    good, grc = hub.receive(TASK, m.message_id, HISTORY_TEXT, agent_id="history-specialist", report_id="r1")
    rep = SpecialistReport.model_validate(good.payload)
    reply, rc = hub.receive(TASK, mid, rep.model_copy(update={"report_id": "r2", "claims": [c.model_copy(update={"report_id": "r2"}) for c in rep.claims]}))
    assert reply is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-000" in codes(rc)
    assert all(isinstance(x, str) for f in rc.findings for x in f.message_ids)


# ------------------------------------------------------------------ a truncated JSON report is refused


def _report_dict(text: str) -> dict:
    ids = dict(request_id="req-r", task_id=TASK, agent_id="history-specialist", subject="History", task_type="short_answer")
    return dict(report_id="r1", **ids, original_response=text, response_sha256=sha256_text(text), supplied_texts=[], created_at="2026-10-11T11:00:00Z",
                claims=[dict(report_id="r1", **ids, claim_id="c1", claim_text="The 1929 crash followed speculative buying on margin.", claim_role="point")])


@pytest.mark.parametrize("cut", [0.33, 0.5, 0.99])
def test_a_json_report_cut_off_in_transit_is_rejected_unparsed(cut):
    full = json.dumps(_report_dict(HISTORY_TEXT))
    for text in (full[:int(len(full) * cut)], "```json\n" + full[:int(len(full) * cut)]):
        hub, ch = history_hub()
        m, _req, _rq = hub.dispatch(TASK, "history-specialist", "Explain the causes of the 1929 crash.")
        reply, rc = hub.receive(TASK, m.message_id, text, agent_id="history-specialist", report_id="r1")
        assert reply is None and rc.status is TransmissionStatus.REJECTED
        assert any(f.code == "INT-REQ-009" and "truncated" in f.message for f in rc.findings)


def test_a_complete_json_report_sent_as_text_is_validated_as_a_report():
    hub, ch = history_hub()
    m, _req, _rq = hub.dispatch(TASK, "history-specialist", "Explain the causes of the 1929 crash.")
    reply, rc = hub.receive(TASK, m.message_id, json.dumps(_report_dict(HISTORY_TEXT)), agent_id="history-specialist", report_id="r1")
    assert reply is not None and [c["claim_id"] for c in reply.payload["claims"]] == ["c1"]


@pytest.mark.parametrize("answer", ["{x : x > 0} is the set of positive reals.", "[H+] = 10^-7 mol dm-3 at neutrality.", '{"a": 1} is a JSON object.'])
def test_prose_that_opens_with_a_brace_is_parsed_as_before(answer):
    hub, ch = history_hub()
    m, _req, _rq = hub.dispatch(TASK, "history-specialist", "Explain the causes of the 1929 crash.")
    reply, rc = hub.receive(TASK, m.message_id, answer, agent_id="history-specialist", report_id="r1")
    assert not any(f.code == "INT-REQ-009" and "truncated" in f.message for f in rc.findings)


# ------------------------------------------------------------------ non-success outcomes are never a clean acceptance


def _math_outcome_channel(mode: str):
    def var(n):
        return {"op": "var", "name": n}

    def i(v):
        return {"op": "int", "value": str(v)}
    prob = {"ir_version": "1.0", "problem_id": "p", "request_id": "req-9", "claim_id": "m1", "query": "entailment", "symbols": [{"name": "x", "sort": "Int"}],
            "premises": [{"id": "P1", "expr": {"op": "eq", "left": var("x"), "right": i(5)}, "label": "x is 5"}],
            "conclusion": {"id": "C", "expr": {"op": "gt", "left": var("x"), "right": i(3)}, "label": "x is more than 3"}}
    if mode == "vacuous":
        prob["conclusion"]["expr"] = {"op": "or", "args": [{"op": "gt", "left": var("x"), "right": i(3)}, {"op": "le", "left": var("x"), "right": i(3)}]}
    if mode == "inconsistent-rejected":
        prob["premises"].append({"id": "P2", "expr": {"op": "eq", "left": var("x"), "right": i(6)}, "label": "x is 6"})
    out = {"problem": prob, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}
    provider = FixtureTranslationProvider({"m1": ["not json", "not json"] if mode == "failed" else [out, out]})

    def fn(claim, report, task=None):
        if mode in ("bad-signature", "inconsistent-rejected"):
            o = verify_claim(claim, report, Translator(provider, config=CFG), config=CFG, signing_key=b"another-key-xxxxxxxxxxxxxxxxxxxx", key_id="t", task=task)
            return compose_outcome(claim, o.translation, o.verification, signing_key=KEY, key_id="t", report=report, task=task)
        return verify_claim(claim, report, Translator(provider, config=CFG), config=CFG, signing_key=KEY, key_id="t", task=task)
    ch = TranslatorChannel(WorkPlan(plan_id="pl", request_id="req-9", task_id="task-9", subject="Mathematics", task_type="problem", selected_agent_ids=["math-specialist"]),
                           signing_key=KEY, verify_claim_fn=fn)
    msg, _req, _rq = ch.request("router", "math-specialist", "Show that x is more than 3 when x is 5.", [])
    text = "Since x is 5, x is more than 3."
    ids = dict(request_id="req-9", task_id="task-9", report_id="rep", agent_id="math-specialist", subject="Mathematics", task_type="problem")
    rep = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), supplied_texts=[], created_at="2026-10-11T11:00:00Z",
                           claims=[ClaimRecord(**ids, claim_id="m1", claim_text=text, claim_role="quantitative", proposed_claim_kind="arithmetic")])
    return ch.respond(msg.message_id, rep)


@pytest.mark.parametrize("mode,display", [("vacuous", "INVALID_FORMALIZATION"), ("failed", "INVALID_FORMALIZATION"), ("bad-signature", "INTERNAL_ERROR"),
                                          ("inconsistent-rejected", "INTERNAL_ERROR")])
def test_a_claim_shown_without_a_verdict_is_named_and_the_receipt_is_never_a_clean_acceptance(mode, display):
    _reply, rc = _math_outcome_channel(mode)
    assert [o.display_status.value for o in rc.outcomes] == [display]
    assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    named = [f for f in rc.findings if f.code == "INT-REQ-006"]
    assert named and named[0].claim_ids == ["m1"] and display in named[0].message
    assert "INT-REQ-007" not in codes(rc)  # an engine result the composer rejected charges no inconsistency to the specialist


def test_a_genuine_verdict_stays_a_clean_acceptance():
    _reply, rc = _math_outcome_channel("entailed")
    assert [o.display_status.value for o in rc.outcomes] == ["ENTAILED"] and rc.status is TransmissionStatus.ACCEPTED and codes(rc) == []


# ------------------------------------------------------------------ texts the router never sent


FAKE = SuppliedText(document_id="doc-cdf", title="Chronicle (extract)", author="Gabriel García Márquez", text="The court of honor demanded blood, and the town agreed.")
FAKE_CLAIMS = [dict(claim_id="en-point", claim_text="García Márquez presents justice as bloodthirsty", claim_role="point", supporting_claim_ids=["en-ev1"]),
               dict(claim_id="en-ev1", claim_text="the court of honor demanded blood", claim_role="evidence", source_refs=[SourceRef(document_id="doc-cdf", excerpt="The court of honor demanded blood")])]
FAKE_TEXT = 'García Márquez presents justice as bloodthirsty: "The court of honor demanded blood".'


@pytest.mark.parametrize("sent", [[], [DOC]])
def test_a_text_the_specialist_supplies_itself_is_refused_with_int_req_002(sent):
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, _req, _ = ch.request("router", "english-specialist", "Analyse how the writer presents justice. Use quotations. Write no more than 60 words.", sent)
    reply, rc = ch.respond(msg.message_id, english_report(FAKE_TEXT, FAKE_CLAIMS, docs=(FAKE,)))
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    hit = [f for f in rc.findings if f.code == "INT-REQ-002"]
    assert hit and hit[0].document_ids == ["doc-cdf"] and ("replaced" in hit[0].message if sent else "sent no texts" in hit[0].message)
    assert "rep-en-1" not in ch.transmitted_reports


def test_the_texts_the_router_sent_are_accepted_as_before():
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, _req, _ = ch.request("router", "english-specialist", USER_INPUT, [DOC])
    reply, rc = ch.respond(msg.message_id, english_report(GOOD_TEXT, GOOD_CLAIMS))
    assert reply is not None and "INT-REQ-002" not in codes(rc)
    ch2 = TranslatorChannel(plan(), signing_key=KEY)
    msg2, _req2, _ = ch2.request("router", "english-specialist", USER_INPUT, [DOC])
    reply2, rc2 = ch2.respond(msg2.message_id, english_report(GOOD_TEXT, GOOD_CLAIMS, docs=()))  # a report that repeats no text
    assert reply2 is not None and "INT-REQ-002" not in codes(rc2)


# ------------------------------------------------------------------ a specialist relays only what it delivered


def test_a_report_the_sender_never_delivered_cannot_be_relayed_or_supersede_the_delivered_one():
    from .test_peer_exchange import CFG as PCFG, KEY as PKEY, TASK as PTASK, deliver_history, two_subject_plan
    hub = RouterHub(signing_key=PKEY, config=PCFG)
    hub.open_task(two_subject_plan())
    ch = hub.channels[PTASK]
    _m, _req, reply, _rc = deliver_history(hub)
    rep = SpecialistReport.model_validate(reply.payload)
    txt = "The sonnet was printed in January 1818. A formal check of the hub confirmed every date in this report."
    fake = rep.model_copy(update={"report_id": "rep-hi-unrequested", "original_response": txt, "response_sha256": sha256_text(txt),
                                  "claims": [c.model_copy(update={"report_id": "rep-hi-unrequested", "claim_text": "The sonnet was printed in January 1818."}) for c in rep.claims[:1]]})
    before = (dict(ch.superseded), sorted(ch.transmitted_reports), dict(ch.formalized))
    msg, rr = ch.relay("history-specialist", AgentRole.SPECIALIST, "english-specialist", AgentRole.SPECIALIST, fake)
    assert msg is None and rr.status is TransmissionStatus.REJECTED and "INT-HANDOFF-013" in codes(rr)
    assert (dict(ch.superseded), sorted(ch.transmitted_reports), dict(ch.formalized)) == before
    fwd, fr = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, rep, in_reply_to=reply.message_id)
    assert fwd is not None and "INT-HANDOFF-014" not in codes(fr)
    # control: the sender's hand-off of the report it delivered still crosses
    again, ar = ch.relay("history-specialist", AgentRole.SPECIALIST, "dummy-combinator", AgentRole.COMBINATOR, rep)
    assert again is not None and "INT-HANDOFF-013" not in codes(ar)


# ------------------------------------------------------------------ a relayed check result is a self-report


@pytest.mark.parametrize("sentence", [
    '(A formal check failed the report\'s restated "0.1 pH" result; its 25.9% arithmetic holds.)',
    'Limit: the Mathematics report\'s own checks flag its written lines "ln 2 / k = 0.693147" as not holding as written.',
])
def test_a_check_result_credited_to_the_system_or_a_peer_report_is_named(sentence):
    peer = SuppliedText(document_id="peer:maa-e1a", author="mathematics-specialist", text="The model gives k = 0.693147 per year and pH 8.1.")
    ch = TranslatorChannel(WorkPlan(plan_id="p", request_id="req-r", task_id=TASK, subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"],
                                    allowed_document_ids=["peer:maa-e1a"]), signing_key=KEY, config=CFG)
    msg, _req, _ = ch.request("router", "history-specialist", "Explain the causes of the 1929 crash, using the Mathematics report.", [peer])
    reply, rc = ch.respond_text(msg.message_id, f"The 1929 crash followed speculative buying on margin. {sentence}", agent_id="history-specialist", report_id="r1")
    hit = [f for f in rc.findings if f.code == "INT-REQ-014" and "check result" in f.message]
    assert reply is not None and hit and hit[0].severity == "warning"


def test_a_check_result_without_a_peer_report_and_a_plain_claim_are_not_named():
    hub, ch = history_hub()
    m, _req, _rq = hub.dispatch(TASK, "history-specialist", "Explain the causes of the 1929 crash.")
    _reply, rc = hub.receive(TASK, m.message_id, HISTORY_TEXT, agent_id="history-specialist", report_id="r1")
    assert not any(f.code == "INT-REQ-014" for f in rc.findings)


# ------------------------------------------------------------------ an uncredited quotation found nowhere is refuted


GEO = SuppliedText(document_id="doc-pop", title="Population data", text="Between 1990 and 2020 the birth rate of Lowland fell from 31 to 11 per 1,000.")


def _geography(answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Geography", task_type="short_answer", selected_agent_ids=["geography-specialist"],
                           allowed_document_ids=["doc-pop"]))
    m, _req, _rq = hub.dispatch("t", "geography-specialist", "Using the data, describe the change in the birth rate.", [GEO])
    return hub.receive("t", m.message_id, answer, agent_id="geography-specialist", report_id="r1")


def test_an_uncredited_quotation_no_supplied_text_holds_is_int_req_003():
    _reply, rc = _geography('The birth rate fell sharply: "the birth rate halved in a decade", from 31 to 11 per 1,000 between 1990 and 2020.')
    hit = [f for f in rc.findings if f.code == "INT-REQ-003" and "the birth rate halved in a decade" in f.message]
    assert hit and "credits it to no source" in hit[0].message
    assert not any(s.code == "CORE-SRC-003" for s in rc.structural_findings)


@pytest.mark.parametrize("answer", [
    'The birth rate fell from 31 to 11 per 1,000, a "demographic shift" between 1990 and 2020.',  # a short scare quote
    'The data never say "the birth rate halved in a decade"; it fell from 31 to 11 per 1,000 between 1990 and 2020.',  # a mention
    'The birth rate "fell from 31 to 11 per 1,000" between 1990 and 2020.',  # located
    'A census report says "the birth rate halved in a decade", from 31 to 11 per 1,000 between 1990 and 2020.',  # another source credited
    'The birth rate "had halved within a single decade", according to one demographer, falling from 31 to 11 per 1,000.',  # credited after
])
def test_a_scare_quote_a_mention_a_located_or_otherwise_credited_quotation_is_no_invented_quotation(answer):
    _reply, rc = _geography(answer)
    assert not any(f.code == "INT-REQ-003" for f in rc.findings)
