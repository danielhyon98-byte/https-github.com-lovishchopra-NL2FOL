"""Repair round 5, the channel's text intake (the re-run review's variants of two robustness classes):

* robustness-and-contracts-7: an answer delivered in envelopes nested in envelopes ('{"response": {"text": "..."}}', up to
  four levels, each one answer key) or between one pair of envelope tags ('<answer>...</answer>') is the answer it carries,
  read exactly as the plain answer is; a JSON object with any other key, or a tag inside the text, is no envelope.
* robustness-and-contracts-8: a structured reply cut off in transit (a Python-notation envelope left unclosed, an envelope
  tag with no closing tag) or a JSON report embedded after prose is refused (INT-REQ-009, REJECTED); a dictionary or a JSON
  example that an answer writes as content is read as prose."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.channel.bus import _answer_in_envelope, _cut_structured_reply

from .test_repair_round2_channel import TASK, _hub

ANSWER = "Inflation rose in 1922 because the government printed money. Prices then doubled every few days in 1923."
REQUEST = "Explain why prices rose in Germany in 1922-23. [4 marks]"


def _codes(text: str):
    hub, m, _ = _hub(request=REQUEST)
    _reply, rc = hub.receive(TASK, m.message_id, text, agent_id="history-specialist", report_id="r1")
    return rc.status.value, sorted({(f.code, f.severity) for f in rc.findings if f.severity in ("error", "warning")})


@pytest.mark.parametrize("wrapped", [json.dumps({"response": {"text": ANSWER}}), json.dumps({"output": {"content": {"answer": ANSWER}}}),
                                     f"<answer>{ANSWER}</answer>", f"<reply>\n{ANSWER}\n</reply>"],
                         ids=["two levels", "three levels", "answer tag", "reply tag on lines of its own"])
def test_an_answer_in_nested_envelopes_or_tags_is_read_as_the_plain_answer(wrapped):
    assert _answer_in_envelope(wrapped) == ANSWER
    assert _codes(wrapped) == _codes(ANSWER)


@pytest.mark.parametrize("text", [json.dumps({"response": {"text": ANSWER, "notes": "none"}}), json.dumps({"status": {"text": ANSWER}}),
                                  f"<answer>{ANSWER}</answer> <answer>more</answer>", f"Intro. <answer>{ANSWER}</answer>"])
def test_control_an_object_with_another_key_or_a_tag_inside_the_text_is_no_envelope(text):
    assert _answer_in_envelope(text) is None


@pytest.mark.parametrize("cut", ["{'answer': 'Inflation rose in 1922 because the government", "<answer>Inflation rose in 1922 because the gov",
                                 'Here is my report.\n{"report_id": "r1", "claims": [{"claim_id": "c1"'],
                         ids=["python notation unclosed", "tag unclosed", "json report after prose"])
def test_a_structured_reply_cut_off_in_transit_is_refused(cut):
    assert _cut_structured_reply(cut) is not None
    status, codes = _codes(cut)
    assert status == "REJECTED" and ("INT-REQ-009", "error") in codes


@pytest.mark.parametrize("text", ["In Python a record is written {'name': 'Ada', 'age': 36}, which maps keys to values.",
                                  'A JSON example: {"answer": 42} is an object with one key.', ANSWER])
def test_control_a_dictionary_or_a_json_example_in_an_answer_is_prose(text):
    assert _cut_structured_reply(text) is None
    assert ("INT-REQ-009", "error") not in _codes(text)[1]
