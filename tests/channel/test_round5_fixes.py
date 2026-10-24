"""Channel behaviour found wanting by the round-5 arena overseers, on the round-5 material: a request echo slightly
longer than the request, 'about N words' read as a maximum only, report-arithmetic findings that named no claim and quoted
a 160-character prefix, a synthesis id reused with other content, payloads that are not models raising out of the hub, an
infrastructure role asserted by any agent id, a colleague's words credited to a poem the agent was never given, a merged
claim delivered with only an info note, and a failing integrity pack taking the transmission down."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from epinoic_logic.adapters.sources import attribute_excerpt
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.base import SubjectBranch
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

KEY = b"round5-channel-test-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
R5 = json.loads((Path(__file__).parent / "data" / "r5_material.json").read_text())
SPEC = R5["specialists"]
EN, HI, COMB = "english-specialist", "history-specialist", "dummy-combinator"


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def texts(item) -> list[SuppliedText]:
    return [SuppliedText(**t) for t in item["supplied_texts"]]


def single_plan(item) -> WorkPlan:
    tid = item["task_id"]
    return WorkPlan(plan_id=f"plan-{tid}", request_id=f"req-{tid}", task_id=tid, subject=item["subject"], task_type=item["task_type"],
                    selected_agent_ids=[item["agent_id"], COMB], allowed_document_ids=[t["document_id"] for t in item["supplied_texts"]])


def deliver(item, text=None, report_id=None, question=None):
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(single_plan(item))
    m, _, _ = hub.dispatch(item["task_id"], item["agent_id"], question or item["question"], texts(item))
    reply, rc = hub.receive(item["task_id"], m.message_id, item["response_text"] if text is None else text, agent_id=item["agent_id"], report_id=report_id or f"rep-{item['task_id']}-0")
    return hub, ch, m, reply, rc


def p4_plan() -> WorkPlan:
    return WorkPlan(plan_id="plan-p4", request_id="req-p4", task_id="p4", subject="History", task_type="short_answer", selected_agent_ids=[EN, HI, COMB],
                    allowed_document_ids=["doc-mhk", "peer:en-p4"], agent_subjects={EN: "English A: Literature"}, agent_task_types={EN: "analytical_paragraph"})


def p4_exchange(hi_text=None):
    """The p4 peer exchange: en-p4 delivered, forwarded by the router to History, hi-p4 delivered quoting the peer."""
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(p4_plan())
    en, hi = SPEC["en-p4"], SPEC["hi-p4"]
    m, _, _ = hub.dispatch("p4", EN, en["question"], texts(en))
    r_en, rc_en = hub.receive("p4", m.message_id, en["response_text"], agent_id=EN, report_id="rep-en-p4-0")
    rep_en = SpecialistReport.model_validate(r_en.payload)
    fwd, frc = ch.relay("router", AgentRole.ROUTER, HI, AgentRole.SPECIALIST, rep_en, in_reply_to=r_en.message_id)
    peer = SuppliedText(document_id="peer:en-p4", title=f"{EN} report rep-en-p4-0 relayed through the hub", author=EN, text=rep_en.original_response)
    m2, _, _ = hub.dispatch("p4", HI, hi["question"], [peer])
    r_hi, rc_hi = hub.receive("p4", m2.message_id, hi["response_text"] if hi_text is None else hi_text, agent_id=HI, report_id="rep-hi-p4-0")
    return hub, ch, r_en, rep_en, fwd, r_hi, rc_hi


def synth(ch, claims, report_ids, sid="syn-x", ledger=(), created_at="2026-10-11T15:00:00Z") -> Synthesis:
    scs = [SynthesizedClaim(claim_id=cid, text=t, certainty=cert, source_claim_ids=src, transformation=tf) for cid, t, cert, src, tf in claims]
    body = " ".join(c.text for c in scs)
    return Synthesis(synthesis_id=sid, request_id=ch.plan.request_id, task_id=ch.plan.task_id, combinator_agent_id=COMB, source_report_ids=report_ids,
                     claims=scs, ledger=list(ledger), text=body, text_sha256=sha256_text(body), created_at=created_at)


def claim_of(reply, needle):
    return next(c for c in reply.payload["claims"] if needle in c["claim_text"])


# ------------------------------------------------------------------ INT-REQ-011: echoes longer than the request


def _echo_of(question: str, ratio: float) -> str:
    """The request followed by its own first words, as long as the whole stays within ``ratio`` times the request's tokens."""
    def n(t):
        return len(re.findall(r"\w+", t))
    words, out = question.split(), question
    for w in words:
        if n(out + " " + w) > ratio * n(question):
            break
        out += " " + w
    assert n(out) / n(question) > ratio - 0.1
    return out


@pytest.mark.parametrize("ratio", [1.3, 1.5])
def test_a_plain_echo_at_1_3x_and_1_5x_the_request_is_int_req_011(ratio):
    item = SPEC["en-t9"]
    echo = _echo_of(item["question"], ratio)
    _hub, _ch, _m, reply, rc = deliver(item, text=echo)
    [f] = [x for x in rc.findings if x.code == "INT-REQ-011"]
    assert reply is not None and f.severity == "error" and "restates the request" in f.message
    assert rc.coverage and not any(c.addressed for c in rc.coverage)


@pytest.mark.parametrize("name", ["en-t9-echo-quoted-long", "en-t7-echo", "en-t5-quotes-request-only"])
def test_the_r3_to_r5_echo_reproductions_are_named_and_address_nothing(name):
    item = dict(R5["adversarial"][name])
    supplied = texts(SPEC["en-t9"]) if name.startswith("en-t9") else [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"]) for t in item["supplied_texts"]]
    hub = RouterHub(signing_key=KEY, config=CFG)
    plan = WorkPlan(plan_id="plan-e", request_id="req-e", task_id="e", subject=item["subject"], task_type=item["task_type"], selected_agent_ids=[EN, COMB])
    hub.open_task(plan)
    m, _, _ = hub.dispatch("e", EN, item["question"], supplied)
    _reply, rc = hub.receive("e", m.message_id, item["response_text"], agent_id=EN, report_id="rep-e")
    assert "INT-REQ-011" in codes(rc.findings)
    assert not any(c.addressed for c in rc.coverage)


def test_the_genuine_r5_answers_are_not_echoes():
    for tid in ("en-t9", "en-t10", "hi-t10"):
        _hub, _ch, _m, _reply, rc = deliver(SPEC[tid])
        assert "INT-REQ-011" not in codes(rc.findings), tid


# ------------------------------------------------------------------ 'about N words' bounds both sides (en-t10)


def test_r5_en_t10_about_250_words_fails_c1_when_cut_to_146_words():
    item = SPEC["en-t10"]
    short = item["response_text"].split(' The phrase "at my back"')[0]
    _hub, _ch, _m, reply, rc = deliver(item, text=short)
    c1 = next(c for c in rc.constraint_results if c.constraint_id == "c1")
    assert c1.satisfied is False and "min_words 225" in c1.detail
    assert any(f.code == "INT-REQ-005" and f.severity == "error" for f in rc.findings)
    _hub, _ch, _m, _reply, ok = deliver(item)  # the genuine answer (242 words) is within 225 to 275
    assert all(c.satisfied for c in ok.constraint_results if c.constraint_id in ("c1", "c2"))


# ------------------------------------------------------------------ INT-SUBJ-001 names the claim and quotes the clause (I11)


def test_i11_false_rise_at_the_end_of_a_long_sentence_is_named_on_its_claim_with_the_clause():
    item = SPEC["hi-t10"]
    long_s = ("The 1840s, which included the Railway Mania of 1845 to 1847 when Parliament authorised hundreds of new companies and speculation drew in investors from every class of society, "
              "saw route mileage climb from about 1,500 in 1840 to about 6,000 in 1850, a rise of about 50 per cent.")
    text = item["response_text"].replace("The 1840s, which included the Railway Mania of 1845 to 1847, added roughly 4,500 miles, more than any other decade of the period, and by 1848 a line ran from London through Carlisle to Glasgow.", long_s)
    _hub, _ch, _m, reply, rc = deliver(item, text=text)
    cid = claim_of(reply, "Railway Mania")["claim_id"]
    failed = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert failed and all(cid in f.claim_ids for f in failed)
    assert any("1,500 in 1840 to about 6,000 in 1850, a rise of about 50 per cent" in f.message for f in failed)
    assert any(fc.satisfied is False and cid in fc.claim_ids for fc in rc.formal_checks)


def test_a_false_statement_after_pasted_braces_is_named_on_its_claim():
    item = SPEC["hi-t10"]
    junk = "{ " * 40 + "}" * 40
    text = item["response_text"] + " " + junk + " Route mileage rose from about 1,500 in 1840 to about 6,000 in 1850, a rise of about 50 per cent."
    _hub, _ch, _m, reply, rc = deliver(item, text=text)
    failed = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    holders = [c["claim_id"] for c in reply.payload["claims"] if "a rise of about 50 per cent" in c["claim_text"]]
    assert failed and holders and all(set(f.claim_ids) & set(holders) for f in failed)
    assert all("{ {" not in f.message.split("does not hold:")[1][:40] for f in failed)  # the clause, not the junk, is quoted first


# ------------------------------------------------------------------ synthesis ids (T1, G4)


def test_t1_g4_a_synthesis_id_reused_with_other_content_is_refused_and_the_first_kept():
    _hub, ch, _m, reply, _rc = deliver(SPEC["hi-t9"])
    full = {c["claim_id"]: c["claim_text"] for c in reply.payload["claims"]}
    keep = [("s1", full["h1.1"], "probable", ["h1.1"], "carried"), ("s8", full["h1.8"], "probable", ["h1.8"], "carried"), ("s9", full["h1.9"], "probable", ["h1.9"], "carried")]
    first = synth(ch, keep, ["rep-hi-t9-0"], sid="syn-t")
    a, ra = ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, first)
    assert a is not None
    t1 = synth(ch, keep[:2], ["rep-hi-t9-0"], sid="syn-t", ledger=[LedgerEntry(source_claim_ids=["h1.9"], transformation="dropped", reason="the link restates the judgement")])
    b, rb = ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, t1)
    [f] = [x for x in rb.findings if x.code == "INT-HANDOFF-015"]
    assert b is None and rb.status is TransmissionStatus.REJECTED and f.severity == "error" and "syn-t" in f.message and "'claims'" in f.message and "'ledger'" in f.message
    g4 = synth(ch, [keep[0], ("s8", full["h1.8"], "established", ["h1.8"], "carried"), keep[2]], ["rep-hi-t9-0"], sid="syn-t")
    c, rc_ = ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, g4)
    assert c is None and "INT-HANDOFF-015" in codes(rc_.findings) and "s8" in next(x for x in rc_.findings if x.code == "INT-HANDOFF-015").message
    assert ch.syntheses["syn-t"] == first
    again = synth(ch, keep, ["rep-hi-t9-0"], sid="syn-t", created_at="2026-10-11T16:00:00Z")  # the same content, re-sent later
    d, rd = ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, again)
    assert d is not None and any(x.code == "INT-ENV-001" and "only the timestamp differs" in x.message for x in rd.findings)


# ------------------------------------------------------------------ payloads that are not models (K3, K4, X1-X3)


def test_k3_k4_x1_x3_payloads_that_are_not_models_never_raise():
    hub, ch, r_en, rep_en, _fwd, _r_hi, _rc = p4_exchange()
    out, rc = ch.relay("router", AgentRole.ROUTER, HI, AgentRole.SPECIALIST, dict(r_en.payload), in_reply_to=r_en.message_id)  # K3 / X3
    assert out is not None and out.contract == "specialist_report_forward/1.0" and out.payload == r_en.payload
    out, rc = ch.relay("router", AgentRole.ROUTER, HI, AgentRole.SPECIALIST, None, in_reply_to=r_en.message_id)  # K4
    assert out is None and rc.status is TransmissionStatus.REJECTED and any(f.code == "INT-REQ-009" and "NoneType" in f.message for f in rc.findings)
    bad = {**r_en.payload, "claims": "not a list"}
    out, rc = ch.relay("router", AgentRole.ROUTER, HI, AgentRole.SPECIALIST, bad, in_reply_to=r_en.message_id)
    assert out is None and any(f.code == "INT-REQ-009" and "specialist_report contract" in f.message for f in rc.findings)
    syn = synth(ch, [("s0", claim_of(r_en, "Hardy's dramatic monologue")["claim_text"], "probable", [claim_of(r_en, "Hardy's dramatic monologue")["claim_id"]], "carried")], ["rep-en-p4-0"], sid="syn-x2")
    out, rc = ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn.model_dump(mode="json"))  # X2
    assert out is not None and out.contract == "synthesis/1.0"
    en = SPEC["en-p4"]
    m, _, _ = hub.dispatch("p4", EN, en["question"], texts(en))
    as_dict = {**r_en.payload, "report_id": "rep-x1", "claims": [{**c, "report_id": "rep-x1"} for c in r_en.payload["claims"]]}
    out, rc = hub.receive("p4", m.message_id, as_dict, agent_id=EN, report_id="rep-x1")  # X1
    assert out is not None and rc.status is not TransmissionStatus.REJECTED
    m, _, _ = hub.dispatch("p4", EN, en["question"], texts(en))
    out, rc = hub.receive("p4", m.message_id, 42, agent_id=EN, report_id="rep-x1b")
    assert out is None and any(f.code == "INT-REQ-009" and "int" in f.message for f in rc.findings)


# ------------------------------------------------------------------ infrastructure roles are held, not asserted (A3, 2a-2b)


def test_a_specialist_or_an_unknown_id_asserting_the_router_role_is_refused():
    _hub, ch, r_en, rep_en, fwd, _r_hi, _rc = p4_exchange()
    assert fwd is not None  # the router's own forward is delivered
    out, rc = ch.relay(EN, AgentRole.ROUTER, HI, AgentRole.SPECIALIST, rep_en, in_reply_to=r_en.message_id)
    assert out is None and rc.status is TransmissionStatus.REJECTED and any(f.code == "INT-ENV-007" and "selects it as a specialist" in f.message for f in rc.findings)
    out, rc = ch.relay("rogue-agent", AgentRole.ROUTER, HI, AgentRole.SPECIALIST, rep_en, in_reply_to=r_en.message_id)
    assert out is None and any(f.code == "INT-ENV-007" and "router of this channel is ['router']" in f.message for f in rc.findings)
    out, rc = ch.relay(EN, AgentRole.SPECIALIST, HI, AgentRole.ROUTER, rep_en)
    assert out is None and any(f.code == "INT-ENV-007" and "does not hold that role" in f.message for f in rc.findings)


# ------------------------------------------------------------------ a colleague's words credited to a text not supplied (C5, C6)


@pytest.mark.parametrize("added,excerpt", [
    (' Hardy\'s speaker himself admits that his casualness "exposes a motive of poverty".', "exposes a motive of poverty"),
    (' The poem says that the killing "only restates the killing".', "only restates the killing"),
])
def test_c5_c6_the_english_specialists_words_credited_to_the_poem_are_named_once_as_an_error(added, excerpt):
    _hub, ch, _r_en, _rep, _fwd, r_hi, rc = p4_exchange(SPEC["hi-p4"]["response_text"] + added)
    cid = claim_of(r_hi, added.strip()[:25])["claim_id"]  # the added sentence (h1.1 quotes the same words, credited to the colleague)
    # the hub's own check (INT-REQ-015) or the branch pack's CORE-SRC-005 (escalated as INT-SUBJ-003), never both, never neither
    found = [f for f in rc.findings if f.code == "INT-REQ-015" or (f.code == "INT-SUBJ-003" and "CORE-SRC-005" in f.message)]
    assert len(found) == 1 and found[0].severity == "error" and excerpt in found[0].message and "peer:en-p4" in found[0].message and cid in found[0].claim_ids
    # the channel's check alone, whatever the packs say: the claim, the credited text and the peer document are named
    report = SpecialistReport.model_validate(r_hi.payload)
    [own] = ch._foreign_credits(report, report.supplied_texts, structural=())
    assert own.code == "INT-REQ-015" and own.severity == "error" and cid in own.claim_ids and "peer:en-p4" in own.document_ids and excerpt in own.message
    if "Hardy" in added:
        assert "doc-mhk" in own.message and "doc-mhk" in own.document_ids


def test_c7_and_the_genuine_hi_p4_credit_the_colleague_correctly():
    for text in (None, SPEC["hi-p4"]["response_text"] + ' The English specialist argues that the justification "becomes circular".'):
        _hub, ch, _r_en, _rep, _fwd, r_hi, rc = p4_exchange(text)
        report = SpecialistReport.model_validate(r_hi.payload)
        assert "INT-REQ-015" not in codes(rc.findings) and ch._foreign_credits(report, report.supplied_texts, structural=()) == []


def test_attribute_excerpt_records_a_credit_to_an_unsupplied_source_when_the_words_are_the_colleagues():
    peer = SuppliedText(document_id="peer:en-p4", title="report", author=EN, text=SPEC["en-p4"]["response_text"])
    docs = {"peer:en-p4": peer}
    doc, notes = attribute_excerpt("exposes a motive of poverty", [], docs, sentence='Hardy\'s speaker himself admits that his casualness "exposes a motive of poverty".')
    assert doc == "peer:en-p4" and notes and "not a supplied text" in notes[0] and "colleague's own prose" in notes[0]
    assert attribute_excerpt("becomes circular", [], docs, sentence='The English specialist argues that the justification "becomes circular".') == ("peer:en-p4", [])
    assert attribute_excerpt("Had he and I but met", [], docs, sentence='Hardy\'s speaker says "Had he and I but met".') == ("peer:en-p4", [])  # the colleague quoted the poem


# ------------------------------------------------------------------ merged material claims carry a warning; a pack failure never raises


def test_a_material_merged_claim_without_a_formal_conclusion_is_a_warning_on_the_synthesis_receipt():
    _hub, ch, _m, reply, _rc = deliver(SPEC["hi-t10"])
    claims = [(f"s{i}", c["text"], c["certainty"], c["source_claim_ids"], c["transformation"]) for i, c in enumerate(R5["syntheses"]["hi-t10"]["claims"])]
    _out, rr = ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, synth(ch, claims, ["rep-hi-t10-0"]))
    warned = {f.claim_ids[0] for f in rr.findings if f.code == "INT-SYNTH-012" and f.severity == "warning" and "NOT formally checked on this channel" in f.message}
    materiality = {c["claim_id"]: c["materiality"] for c in reply.payload["claims"]}
    material_merged = {cid for cid, _t, _c, src, tf in claims if tf == "merged" and any(materiality.get(x) == "material" for x in src)}
    assert material_merged and material_merged <= warned  # s0 and s3 merge the point h1.1


def test_a_failing_integrity_pack_is_reported_and_never_raises(monkeypatch):
    def boom(self, report, request_text=None):
        raise RuntimeError("pack failure")
    monkeypatch.setattr(SubjectBranch, "run_packs", boom)
    _hub, _ch, _m, reply, rc = deliver(SPEC["hi-t10"])
    assert reply is not None and any(f.code == "INT-INTERNAL-001" and "RuntimeError" in f.message for f in rc.findings)
    assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
