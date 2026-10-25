"""Answers delivered in JSON or wrapped in quotation marks (repair round 1, re-run review rc-7 residual and rc-8):

* an answer delivered as a one-key answer object ('{"answer": "..."}') is read as the text it holds, so a correct answer
  is no "response carries no answer" error and no self-reported status;
* an answer that is one string in double quotes ('"The crash of 1929 ... 1931."') is no envelope: it is also a
  whole-answer quotation, so it stays a quotation and every quotation check still reads it (the arena's altered
  quotation of a supplied text, written as the whole answer, is still caught). A quotation wrapping two or more sentences
  is no bare assertion (``diag_argument.wrapped_passage``), and the History chronology proxy reads its sentences as the
  core pack does, so the wrapped answer gets no warning that the same words unwrapped do not get;
* a whole JSON report followed by more text ('{"report_id": ...}}}') is refused as malformed JSON (INT-REQ-009), never
  delivered as one claim of prose.

Clean controls: the same answer as plain text is delivered the same way; an object with another key, or a second key, is
no envelope and is read as before; one quoted judgement with no reason is a bare assertion as it is unquoted; a whole JSON
report is still read through the report path."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.channel.bus import _answer_in_envelope
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText, sha256_text
from epinoic_logic.translate.diag_argument import wrapped_passage

KEY = b"json-envelope-test-key-0123456789ab"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
TASK, AGENT = "task-r", "history-specialist"
ANSWER = "The 1929 crash followed speculative buying on margin. Banks failed in 1930 and 1931."


def _receive(text: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="plan-r", request_id="req-r", task_id=TASK, subject="History", task_type="short_answer", selected_agent_ids=[AGENT]))
    m, _req, _rc = hub.dispatch(TASK, AGENT, "Explain the causes of the 1929 crash.")
    return hub.receive(TASK, m.message_id, text, agent_id=AGENT, report_id="r1")


def _codes(rc) -> set[str]:
    return {f.code for f in rc.findings}


def test_the_envelope_reader():
    assert _answer_in_envelope(json.dumps({"answer": ANSWER})) == ANSWER
    assert _answer_in_envelope(json.dumps({"Response": "  x y  "})) == "x y"
    for not_one in (ANSWER, json.dumps(ANSWER), json.dumps({"answer": ANSWER, "status": "VERIFIED"}), json.dumps({"verdict": ANSWER}),
                    json.dumps({"answer": 5}), json.dumps({"answer": ""}), '{"answer": "cut', "[1, 2]", '"a" and "b"'):
        assert _answer_in_envelope(not_one) is None, not_one      # a double-quoted answer is a quotation, never an envelope


@pytest.mark.parametrize("text", [json.dumps({"answer": ANSWER}), "  " + json.dumps({"text": ANSWER}) + "\n"])
def test_an_answer_in_a_json_envelope_is_read_as_its_text(text):
    reply, rc = _receive(text)
    plain_reply, plain = _receive(ANSWER)
    assert reply is not None and rc.status is plain.status and _codes(rc) == _codes(plain)
    assert not ({"INT-REQ-012", "INT-HANDOFF-006"} & _codes(rc))
    assert reply.payload["original_response"] == ANSWER and [c["claim_text"] for c in reply.payload["claims"]] == [c["claim_text"] for c in plain_reply.payload["claims"]]


@pytest.mark.parametrize("marks", [('"', '"'), ("“", "”"), ("'", "'")])
def test_an_answer_wrapped_in_quotation_marks_stays_a_quotation_and_gets_no_warning_of_its_own(marks):
    wrapped = marks[0] + ANSWER + marks[1]
    assert wrapped_passage(wrapped)
    reply, rc = _receive(wrapped)
    assert reply is not None and reply.payload["original_response"] == wrapped
    assert reply.payload["claims"][0]["claim_text"].startswith(marks[0])                       # still a quotation
    codes = _codes(rc) | {f.code for f in rc.structural_findings}
    assert "CORE-SRC-003" in codes                      # a quotation no supplied text holds is still named as uncheckable
    assert not ({"INT-ARG-001", "HI-CHR-001", "INT-REQ-012"} & codes), codes                   # no bare assertion, no false chronology
    assert not any(d.code == "ARG-BARE-001" for d in rc.named_diagnostics)


def test_a_misquotation_written_as_the_whole_answer_is_still_caught():
    source = SuppliedText(document_id="doc-h", title="Extract", author="A historian",
                          text="The Depression did not create the Nazi movement, but it made it a mass party.")
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="plan-r", request_id="req-r", task_id=TASK, subject="History", task_type="short_answer", selected_agent_ids=[AGENT],
                           allowed_document_ids=["doc-h"]))
    m, _req, _rc = hub.dispatch(TASK, AGENT, "Explain the view of the extract.", [source])
    altered = '"The Depression did not create the Nazi movemently, but it made it a mass party."'
    _reply, rc = hub.receive(TASK, m.message_id, altered, agent_id=AGENT, report_id="r1")
    [f] = [f for f in rc.findings if f.code == "INT-REQ-003"]                                   # the altered word is not in the source
    assert f.severity == "error" and "movemently" in f.message
    exact = '"The Depression did not create the Nazi movement, but it made it a mass party."'
    hub2 = RouterHub(signing_key=KEY, config=CFG)
    hub2.open_task(WorkPlan(plan_id="plan-r", request_id="req-r", task_id=TASK, subject="History", task_type="short_answer", selected_agent_ids=[AGENT],
                            allowed_document_ids=["doc-h"]))
    m2, _r2, _c2 = hub2.dispatch(TASK, AGENT, "Explain the view of the extract.", [source])
    _reply2, rc2 = hub2.receive(TASK, m2.message_id, exact, agent_id=AGENT, report_id="r1")
    assert "INT-REQ-003" not in {f.code for f in rc2.findings}                                # control: the exact quotation is found


def test_clean_control_one_quoted_judgement_with_no_reason_is_a_bare_assertion_as_unquoted():
    judgement = "The crash of 1929 was a disaster for the world economy."
    for text in (judgement, '"' + judgement + '"'):
        assert not wrapped_passage(text)
        _reply, rc = _receive(text)
        assert any(d.code == "ARG-BARE-001" for d in rc.named_diagnostics), text


def test_clean_control_an_object_that_is_no_envelope_is_read_as_before():
    reply, rc = _receive(json.dumps({"answer": ANSWER, "status": "VERIFIED"}))
    assert "INT-HANDOFF-006" in _codes(rc)     # a status key is still the agent's self-report, never read away


def _report_json(text: str) -> str:
    claim = dict(request_id="req-r", task_id=TASK, report_id="r1", agent_id=AGENT, subject="History", task_type="short_answer", claim_id="h1.1",
                 claim_text=text, claim_role="point")
    return json.dumps(dict(report_id="r1", request_id="req-r", task_id=TASK, agent_id=AGENT, subject="History", task_type="short_answer",
                           original_response=text, response_sha256=sha256_text(text), supplied_texts=[], created_at="2026-10-11T11:00:00Z", claims=[claim]))


@pytest.mark.parametrize("tail", ["}}", " trailing words", "\n{\"report_id\": \"r2\"}"])
def test_a_json_report_followed_by_more_text_is_refused_as_malformed(tail):
    reply, rc = _receive(_report_json(ANSWER) + tail)
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    [f] = [f for f in rc.findings if f.code == "INT-REQ-009"]
    assert f.severity == "error" and "followed by" in f.message and "Extra data" in f.message


def test_clean_control_a_whole_json_report_goes_through_the_report_path():
    reply, rc = _receive(_report_json(ANSWER))
    assert reply is not None and "INT-REQ-009" not in _codes(rc)
    assert [c["claim_id"] for c in reply.payload["claims"]] == ["h1.1"]


def test_the_history_chronology_proxy_reads_a_wrapped_answer_as_its_sentences():
    """The proxy (HI-CHR-001) and the core pack's formal chronology read the same inner sentences: a cue of the first
    sentence ('came after') is never paired with a date of the second. Control: a wrong order inside one sentence is
    still named, wrapped or not."""
    from epinoic_logic.adapters.history_specialist.sentences import inner_sentences
    wrapped = '"The crash of 1929 came after a speculative boom. Banks failed in 1930 and 1931."'
    assert inner_sentences(wrapped) == ["The crash of 1929 came after a speculative boom.", "Banks failed in 1930 and 1931."]
    _reply, rc = _receive(wrapped)
    assert "HI-CHR-001" not in {f.code for f in rc.structural_findings}
    for wrong in ("The 1933 election came after the 1934 plebiscite.", '"The 1933 election came after the 1934 plebiscite. Banks failed in 1931."'):
        _reply, rc = _receive(wrong)
        assert "HI-CHR-001" in {f.code for f in rc.structural_findings}, wrong
