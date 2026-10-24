"""Channel behaviour found wanting by the round-6 arena overseers, on the round-6 material: a JSON fragment that took the
prose around it out of a word bound, a credited clause cut at the point of a decimal (a false INT-REQ-014 naming '5'), a
credit by "according to" not read, a colleague's date re-paired to another event in an unquoted paraphrase, a report
received as a mapping refused with a bare value error instead of INT-HANDOFF-012, an outline item reported unaddressed
because 'Africa' never met 'African', INT-SUBJ-001 quoting a clause cut inside a decimal or after 'c.', and a claim id
already delivered by another agent's report crossing the hub silently."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.adapters.sources import clause_boundaries, credited_spans
from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.channel.bus import _terms
from epinoic_logic.channel.request_parser import count_answer_words, count_paragraphs
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText

KEY = b"round6-channel-test-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
R6 = json.loads((Path(__file__).parent / "data" / "r6_material.json").read_text())
SPEC = R6["specialists"]
EN, HI, COMB = "english-specialist", "history-specialist", "dummy-combinator"
E5 = SPEC["en-p5"]["response_text"]
STAT = 'the History specialist\'s statistic, "About 5.2 million people entered the United States in the 1880s", comes from context'


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def texts(item) -> list[SuppliedText]:
    return [SuppliedText(**t) for t in item["supplied_texts"]]


def deliver(item, text=None, report_id=None):
    tid = item["task_id"]
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id=f"plan-{tid}", request_id=f"req-{tid}", task_id=tid, subject=item["subject"], task_type=item["task_type"],
                                selected_agent_ids=[item["agent_id"], COMB], allowed_document_ids=[t["document_id"] for t in item["supplied_texts"]]))
    m, _, _ = hub.dispatch(tid, item["agent_id"], item["question"], texts(item))
    reply, rc = hub.receive(tid, m.message_id, item["response_text"] if text is None else text, agent_id=item["agent_id"], report_id=report_id or f"rep-{tid}-0")
    return hub, ch, m, reply, rc


def p5_plan() -> WorkPlan:
    return WorkPlan(plan_id="plan-p5", request_id="req-p5", task_id="p5", subject=SPEC["en-p5"]["subject"], task_type=SPEC["en-p5"]["task_type"],
                    selected_agent_ids=[EN, HI, COMB], allowed_document_ids=["doc-nc", "peer:hi-p5"], agent_subjects={HI: "History"}, agent_task_types={HI: "short_answer"})


def p5_exchange(en_text=None):
    """The p5 peer exchange: hi-p5 delivered, forwarded by the router to English, en-p5 delivered with peer:hi-p5 supplied."""
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(p5_plan())
    hi, en = SPEC["hi-p5"], SPEC["en-p5"]
    m, _, _ = hub.dispatch("p5", HI, hi["question"], [])
    hreply, hrc = hub.receive("p5", m.message_id, hi["response_text"], agent_id=HI, report_id="rep-hi-p5-0")
    held = SpecialistReport.model_validate(hreply.payload)
    fwd, _ = ch.relay("router", AgentRole.ROUTER, EN, AgentRole.SPECIALIST, held, in_reply_to=hreply.message_id)
    peer = SuppliedText(document_id="peer:hi-p5", title="history-specialist report relayed through the hub", author=HI, text=fwd.payload["original_response"])
    m2, _, _ = hub.dispatch("p5", EN, en["question"], [*texts(en), peer])
    ereply, erc = hub.receive("p5", m2.message_id, en_text or E5, agent_id=EN, report_id="rep-en-p5-0")
    return hub, ch, hreply, ereply, erc


def req14(rc) -> list[str]:
    return [f.message for f in rc.findings if f.code == "INT-REQ-014"]


# --------------------------------------------------------------------------- a JSON fragment and the word bound (major)
EXTRA = ("The final stanza turns the exchange around. Love answers each objection with a question that the speaker cannot refuse, and the "
         "short replies shrink as the long lines of invitation grow, until the speaker sits and eats. The meal resolves the argument "
         "in an action rather than in words, so the reluctance the poem began with is answered by hospitality rather than by debate.")


def _bound(rc, kind):
    return next(c for c in rc.constraint_results if c.detail and f"bound {kind}" in c.detail)


def test_a_json_fragment_inside_a_paragraph_never_takes_its_prose_out_of_a_maximum_word_bound():
    """en-t12 (at most 300 words) plus a 64-word paragraph fails the bound; the same paragraph with '{"n": 1}' glued after its
    first sentence still fails it, measured on the same answer words: only the JSON span's two words are meta-text."""
    item = SPEC["en-t12"]
    plain = item["response_text"] + "\n\n" + EXTRA
    glued = item["response_text"] + "\n\n" + EXTRA.replace("turns the exchange around.", 'turns the exchange around.{"n": 1}')
    (a_plain, n_plain), (a_glued, n_glued) = count_answer_words(plain), count_answer_words(glued)
    assert a_glued == a_plain > 300 and n_glued == n_plain + 2
    for text in (plain, glued):
        _hub, _ch, _m, reply, rc = deliver(item, text)
        c = _bound(rc, "max_words")
        assert c.satisfied is False and f"measured {a_plain} words" in c.detail and c.formal_status == "COUNTEREXAMPLE", c.detail
        assert any(f.code == "INT-REQ-005" and f.severity == "error" and "max_words" in f.message for f in rc.findings)


def test_a_json_fragment_in_a_history_answer_never_hides_an_overrun():
    item = SPEC["hi-t12"]
    sent = ("The Organisation of African Unity was founded in Addis Ababa in May 1963 by thirty-two states, and it took up decolonisation of "
            "the remaining territories as a central aim of its charter.")
    plain = item["response_text"].replace("The decisive turning point was 1960.", sent + " The decisive turning point was 1960.")
    glued = item["response_text"].replace("The decisive turning point was 1960.", sent + '{"n": 1} The decisive turning point was 1960.')
    assert count_answer_words(glued)[0] == count_answer_words(plain)[0] > 200
    _hub, _ch, _m, _reply, rc = deliver(item, glued)
    c = _bound(rc, "max_words")
    assert c.satisfied is False and c.formal_status == "COUNTEREXAMPLE"


def test_a_json_object_glued_between_two_thesis_sentences_is_the_only_meta_text():
    """r6a en-t11-json-glued: a receipt object glued between the two thesis sentences took 55 words out of the count and
    raised a false 'min_words 225' error, while the parser delivered both sentences as material claims."""
    item = R6["variants"]["en-t11-json-glued"]
    answer, notes = count_answer_words(item["response_text"])
    assert notes == 7  # {"verified": true, "quotations": "all found in doc-je"}
    assert 225 <= answer <= 275
    _hub, _ch, _m, reply, rc = deliver(item)
    assert reply is not None
    assert _bound(rc, "min_words").satisfied is True and _bound(rc, "max_words").satisfied is True
    assert not any(f.code == "INT-REQ-005" and f.severity == "error" for f in rc.findings), [f.message for f in rc.findings]
    material = [c["claim_text"] for c in reply.payload["claims"] if c["claim_role"] != "other"]
    assert any(t.startswith("Brontë presents Jane's exclusion") for t in material) and any(t.startswith("The passage moves") for t in material)


def test_a_block_that_is_only_a_json_span_is_no_paragraph():
    assert count_paragraphs('The answer is one paragraph of prose. It has two sentences.\n\n{"verified": true, "words": 12}') == 1
    assert count_paragraphs('The answer is one paragraph.{"verified": true} It keeps its prose.') == 1


# --------------------------------------------------------------------------- INT-REQ-014: decimals and credits (majors)
def test_the_credited_clause_never_ends_at_the_point_of_a_decimal():
    peer = SuppliedText(document_id="peer:hi-p5", title="peer", author=HI, text=SPEC["hi-p5"]["response_text"])
    s = "and the History specialist's figure of about 5.2 million arrivals in the 1880s comes from context, not the poem."
    (a, b), = credited_spans(s, peer)
    assert "5.2 million arrivals in the 1880s comes from context" in s[a:b]
    s2 = "According to the History specialist, about 7.2 million people arrived in the 1880s."
    assert any("7.2 million people arrived" in s2[a:b] for a, b in credited_spans(s2, peer))
    s3 = "About 7.2 million people arrived in the 1880s, according to the History specialist."
    assert any("7.2 million people arrived" in s3[a:b] for a, b in credited_spans(s3, peer))
    assert clause_boundaries("Kenya in c. 1963 had 3.3 million people. Then") == [len("Kenya in c. 1963 had 3.3 million people")]


def test_a_correct_unquoted_paraphrase_of_the_peers_decimal_figure_raises_nothing():
    """C7 (communication-fidelity control): the correct paraphrase was named as a misreported '5'."""
    _hub, _ch, _h, reply, rc = p5_exchange(E5.replace(STAT, "the History specialist's figure of about 5.2 million arrivals in the 1880s comes from context"))
    assert reply is not None and not req14(rc), req14(rc)
    _hub, _ch, _h, reply, rc = p5_exchange(E5 + " The History specialist gives about 5.2 million arrivals in the 1880s.")
    assert not req14(rc), req14(rc)


@pytest.mark.parametrize("sentence,figure", [
    (" The History specialist gives about 2.5 million arrivals in the 1880s.", "2.5 million"),
    (" According to the History specialist, about 7.2 million people arrived in the 1880s.", "7.2 million"),
    (" About 7.2 million people arrived in the 1880s, according to the History specialist.", "7.2 million"),
    (" In the History specialist's account, about 7.2 million people arrived in the 1880s.", "7.2 million"),
    (" As the History specialist notes, about 7.2 million people arrived in the 1880s.", "7.2 million"),
])
def test_a_misreported_decimal_credited_to_the_peer_is_named_with_the_whole_figure(sentence, figure):
    _hub, _ch, _h, _reply, rc = p5_exchange(E5 + sentence)
    found = req14(rc)
    assert len(found) == 1 and f"['{figure}']" in found[0], found


def test_a_misreported_figure_in_the_possessive_paraphrase_is_named_in_full():
    """C5 with a decimal: '5.8 million' is named as '5.8 million', not as '5'."""
    _hub, _ch, _h, _reply, rc = p5_exchange(E5.replace(STAT, "the History specialist's figure of about 5.8 million arrivals in the 1880s comes from context"))
    found = req14(rc)
    assert len(found) == 1 and "['5.8 million']" in found[0], found


@pytest.mark.parametrize("sentence,stated,peer_date", [
    (" The History specialist dates the sonnet to 1886.", "1886", "1883"),
    (" The History specialist dates the Chinese Exclusion Act to 1883.", "1883", "1882"),
])
def test_a_peers_date_re_paired_to_another_event_is_named(sentence, stated, peer_date):
    """r6a en-p5f / en-p5o: a date the peer gives for another event (the dedication 1886, the sonnet 1883), credited to the
    peer for the sonnet or the Act, crossed the hub with no finding."""
    _hub, _ch, _h, reply, rc = p5_exchange(E5 + sentence)
    assert reply is not None
    found = req14(rc)
    assert len(found) == 1 and f"'{stated}'" in found[0] and f"'{peer_date}'" in found[0] and "another event" in found[0], found


@pytest.mark.parametrize("sentence", [" The History specialist dates the Chinese Exclusion Act to 1882.", " The History specialist dates the sonnet to 1883.",
                                      " The History specialist dates the statue's dedication to 1886."])
def test_a_peers_date_reported_with_its_own_event_raises_nothing(sentence):
    _hub, _ch, _h, _reply, rc = p5_exchange(E5 + sentence)
    assert not req14(rc), req14(rc)


def test_the_genuine_peer_exchange_carries_no_int_req_014():
    _hub, _ch, _h, reply, rc = p5_exchange()
    assert reply is not None and not req14(rc)


# --------------------------------------------------------------------------- INT-HANDOFF-012 on a mapping (minor)
def _hi_mapping(mutate):
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(p5_plan())
    hi = SPEC["hi-p5"]
    m, _, _ = hub.dispatch("p5", HI, hi["question"], [])
    branch = ch._branch_for(HI)[0]
    rep = branch.parser().parse_response(hi["response_text"], request_id="req-p5", task_id="p5", report_id="rep-hi-p5-h", subject="History", task_type="short_answer",
                                         supplied_texts=[], agent_id=HI)
    data = rep.model_dump(mode="json", exclude_none=True)
    data["claims"] = [mutate(c) for c in data["claims"]]
    return hub, ch, m, data


@pytest.mark.parametrize("cid,field,value", [("h1.3", "report_id", "rep-en-p5-0"), ("h1.2", "request_id", "req-hi-t12")])
def test_a_mapping_whose_claim_carries_another_reports_provenance_is_int_handoff_012_not_a_value_error(cid, field, value):
    """H1 / H3: a report received as JSON with a claim of another report or request was refused with a bare
    'INT-REQ-009 ... report: value_error' naming no claim and no field."""
    hub, ch, m, data = _hi_mapping(lambda c: {**c, field: value} if c["claim_id"] == cid else c)
    reply, rc = hub.receive("p5", m.message_id, data, agent_id=HI, report_id=data["report_id"])
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    assert "INT-REQ-009" not in codes(rc.findings)
    f = next(f for f in rc.findings if f.code == "INT-HANDOFF-012")
    assert f.severity == "error" and f.claim_ids == [cid] and f"['{field}']" in f.message and value in f.message
    assert "rep-hi-p5-h" not in ch.transmitted_reports


def test_a_relayed_mapping_with_a_foreign_claim_is_named_the_same_way():
    hub, ch, m, data = _hi_mapping(lambda c: {**c, "report_id": "rep-other"} if c["claim_id"] == "h1.4" else c)
    reply, rc = ch.relay(HI, AgentRole.SPECIALIST, COMB, AgentRole.COMBINATOR, data)
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    assert [f.claim_ids for f in rc.findings if f.code == "INT-HANDOFF-012"] == [["h1.4"]] and "INT-REQ-009" not in codes(rc.findings)


def test_control_a_valid_mapping_is_still_delivered():
    hub, ch, m, data = _hi_mapping(lambda c: c)
    reply, rc = hub.receive("p5", m.message_id, data, agent_id=HI, report_id=data["report_id"])
    assert reply is not None and "INT-HANDOFF-012" not in codes(rc.findings)


# --------------------------------------------------------------------------- coverage of an outline item (minors)
def test_an_adjective_of_place_meets_its_place_in_the_coverage_terms():
    assert "africa" in _terms("the pace of decolonisation in Africa") and "africa" in _terms("seventeen African states")
    assert _terms("European recovery") & _terms("the recovery of Europe") == {"europ", "recovery"} or "europ" in _terms("European")


def test_the_genuine_hi_t12_outline_item_is_addressed():
    """r6 hi-t12: 'request item i1 appears unaddressed: Outline, with dated and quantified evidence, the pace of
    decolonisation in Africa between 1957 and 1968' although the answer is that outline."""
    _hub, _ch, _m, reply, rc = deliver(SPEC["hi-t12"])
    cov = {c.item_id: c.addressed for c in rc.coverage}
    assert cov == {"i1": True, "i2": True}, cov
    assert "INT-REQ-004" not in codes(rc.findings)


def test_control_an_item_the_answer_does_not_touch_is_still_unaddressed():
    item = dict(SPEC["hi-t12"], question=SPEC["hi-t12"]["question"] + " Explain the role of the Soviet Union in the Cuban missile crisis.")
    _hub, _ch, _m, _reply, rc = deliver(item)
    assert any(f.code == "INT-REQ-004" and "Cuban" in f.message for f in rc.findings)


# --------------------------------------------------------------------------- INT-SUBJ-001 quoting (minor)
def test_int_subj_001_quotes_the_whole_clause_with_its_decimals_and_abbreviations():
    item = SPEC["hi-t11"]
    text = item["response_text"].replace("Output had already begun to revive:", "Pig iron output more than doubled from about 3.3 million tonnes in 1947 to about 6.2 million in 1951. "
                                         "Kenya became independent in c. 1963, before Tanganyika in c. 1961. Output had already begun to revive:")
    _hub, _ch, _m, _reply, rc = deliver(item, text)
    msgs = [f.message for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert any("'Kenya became independent in c. 1963, before Tanganyika in c. 1961'" in m for m in msgs), msgs
    assert any("'Pig iron output more than doubled from about 3.3 million tonnes in 1947 to about 6.2 million in 1951'" in m for m in msgs), msgs


def test_int_subj_001_quotes_an_absolute_change_up_to_the_derived_figure_it_refutes():
    item = dict(SPEC["hi-t11"], question="Outline the growth of British railways between 1840 and 1850, with dated and quantified evidence.")
    text = ("Railways grew fast in the 1840s. Route mileage rose from about 1,500 miles in 1840 to about 6,000 miles in 1850, an increase of 6,500 miles "
            "(from memory). The trunk lines laid then shaped the later network.")
    _hub, _ch, _m, _reply, rc = deliver(item, text)
    msgs = [f.message for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert any("'Route mileage rose from about 1,500 miles in 1840 to about 6,000 miles in 1850, an increase of 6,500 miles'" in m for m in msgs), msgs


def test_a_containment_check_quotes_its_sentence_from_a_word_boundary():
    item = SPEC["hi-t12"]
    text = item["response_text"].replace("Nigeria on 1 October and the Belgian Congo on 30 June among them", "Nigeria on 1 October 1960 and Kenya on 12 December 1963 among them")
    _hub, _ch, _m, _reply, rc = deliver(item, text)
    msg = next(f.message for f in rc.findings if f.code == "INT-SUBJ-001")
    assert "'The pace changed in 1960, when seventeen African states became independent, Nigeria on 1 October 1960 and Kenya on 12 December 1963 among them'" in msg, msg


# --------------------------------------------------------------------------- a claim id another agent already holds (minor)
def test_a_claim_id_already_delivered_by_another_agent_is_named_at_delivery():
    """probe_roles_ids 1a: a History claim reusing the English report's claim id crossed the hub with no finding; the
    collision surfaced only when a synthesis cited it (INT-LEDGER-014)."""
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(p5_plan())
    en, hi = SPEC["en-p5"], SPEC["hi-p5"]
    m, _, _ = hub.dispatch("p5", EN, en["question"], texts(en))
    ereply, _ = hub.receive("p5", m.message_id, E5, agent_id=EN, report_id="rep-en-p5-0")
    branch = ch._branch_for(HI)[0]
    rep = branch.parser().parse_response(hi["response_text"], request_id="req-p5", task_id="p5", report_id="rep-hi-p5-0", subject="History", task_type="short_answer",
                                         supplied_texts=[], agent_id=HI)
    claims = list(rep.claims)
    claims[1] = claims[1].model_copy(update={"claim_id": "p1-point"})
    m2, _, _ = hub.dispatch("p5", HI, hi["question"], [])
    reply, rc = hub.receive("p5", m2.message_id, rep.model_copy(update={"claims": claims}))
    assert reply is not None
    f = next(f for f in rc.findings if f.code == "INT-REQ-016")
    assert f.severity == "warning" and f.claim_ids == ["p1-point"] and set(f.report_ids) == {"rep-hi-p5-0", "rep-en-p5-0"} and "INT-LEDGER-014" in f.message


def test_control_distinct_claim_ids_and_a_same_agent_revision_raise_no_collision():
    _hub, _ch, _h, reply, rc = p5_exchange()
    assert "INT-REQ-016" not in codes(rc.findings)
    item = SPEC["hi-t12"]
    hub, ch, m, reply, _rc = deliver(item)
    m2, _, _ = hub.dispatch(item["task_id"], item["agent_id"], item["question"], [])
    _r2, rc2 = hub.receive(item["task_id"], m2.message_id, item["response_text"].replace("seventeen", "eighteen"), agent_id=item["agent_id"], report_id="rep-hi-t12-1")
    assert "INT-REQ-016" not in codes(rc2.findings) and "INT-HANDOFF-009" in codes(rc2.findings)
