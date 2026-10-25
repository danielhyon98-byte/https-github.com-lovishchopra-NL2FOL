"""Repair round 2, channel residuals, each with a clean control:

* a mapping report whose original response is one JSON object wrapping the answer has an answer (no INT-REQ-012), while a
  response that is only a JSON receipt still has none (robustness-and-contracts-7);
* a request made only of zero-width, format or control characters asks nothing and is REJECTED (empty-request residual);
* a contract error of one field names the validator's own message, never the field's value (combinator-faults-11);
* a relayed agent's report is a peer document whatever label it carries: its id, author or provenance (security-2);
* a judgement whose own sentence quotes a supplied text, punctuation inside the closing mark included, is neither a bare
  assertion nor an invented quotation in History, as in English (history-bare-assertion false alarm);
* a request to recommend, or to answer "with reasons" or "with justification", asks for reasons, so a recommendation with no
  reason given is a bare assertion, while the same answer to a request that asks only for a statement is not.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.bus import _shape_reason
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.integrity.contracts import Synthesis
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText, sha256_text
from epinoic_logic.translate.grounding import check_problem_grounding, is_peer_document

KEY = b"repair-round-2-channel-tests-0123456789"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
TASK = "task-r2"
HISTORY = "history-specialist"


def _hub(request: str = "Explain the causes of the 1929 crash.", docs=(), subject: str = "History", agent: str = HISTORY):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="plan-r2", request_id="req-r2", task_id=TASK, subject=subject, task_type="short_answer", selected_agent_ids=[agent],
                           allowed_document_ids=[d.document_id for d in docs]))
    m, _req, rc = hub.dispatch(TASK, agent, request, list(docs))
    return hub, m, rc


def _mapping(text: str, claim_text: str) -> dict:
    ids = dict(request_id="req-r2", task_id=TASK, agent_id=HISTORY, subject="History", task_type="short_answer")
    return dict(report_id="r1", original_response=text, response_sha256=sha256_text(text), supplied_texts=[], created_at="2026-10-17T11:00:00Z",
                claims=[dict(report_id="r1", claim_id="c1", claim_text=claim_text, claim_role="point", **ids)], **ids)


ANSWER = "The 1929 crash followed speculative buying on margin. Banks failed in 1930 and 1931."


@pytest.mark.parametrize("wrapped", ['{"answer": "%s"}' % ANSWER, '{"response": "%s", "notes": "none"}' % ANSWER])
def test_an_answer_wrapped_in_one_json_object_is_an_answer(wrapped):
    hub, m, _ = _hub()
    _reply, rc = hub.receive(TASK, m.message_id, _mapping(wrapped, ANSWER))
    assert "INT-REQ-012" not in {f.code for f in rc.findings}


def test_a_response_that_is_only_a_json_receipt_still_has_no_answer():
    hub, m, _ = _hub()
    _reply, rc = hub.receive(TASK, m.message_id, _mapping('{"status": "ok"}', '{"status": "ok"}'))
    assert "INT-REQ-012" in {f.code for f in rc.findings if f.severity == "error"}


@pytest.mark.parametrize("request_text", ["​‌‍", "\x00\x01\x02", "﻿ \t\n", "⁠​"])
def test_a_request_with_no_visible_character_asks_nothing(request_text):
    _hub_, _m, rc = _hub(request_text)
    assert rc.status.value == "REJECTED" and "INT-REQ-009" in {f.code for f in rc.findings}


@pytest.mark.parametrize("request_text", ["Explain​ the causes of the crash.", "​Why did banks fail in 1930?"])
def test_a_request_with_words_and_an_invisible_character_is_sent(request_text):
    _hub_, m, rc = _hub(request_text)
    assert m is not None and rc.status.value != "REJECTED"


def test_a_field_error_names_the_validators_message_and_never_the_value():
    base = dict(synthesis_id="s", request_id="r", task_id="t", combinator_agent_id="c", source_report_ids=["r1"], claims=[], ledger=[], text="x",
                text_sha256=sha256_text("x"), created_at="2026-10-17T11:00:00Z")
    with pytest.raises(ValidationError) as dup:
        Synthesis(**{**base, "conflicts": [{"conflict_id": "c1", "claim_ids": ["a", "a"], "description": "d"}]})
    shown = _shape_reason(dup.value, "synthesis")
    assert "conflicts.0" in shown and "two distinct parties" in shown and "value_error" not in shown
    with pytest.raises(ValidationError) as stamp:
        Synthesis(**{**base, "conflicts": [], "created_at": "yesterday at noon"})
    shown = _shape_reason(stamp.value, "synthesis")
    assert "created_at" in shown and "RFC 3339" in shown and "yesterday" not in shown


# ------------------------------------------------------------------------------------------------------- peer documents

@pytest.mark.parametrize("fields", [
    dict(document_id="peer:econ-1", author=None, provenance=None),
    dict(document_id="peer-econ", author="Economics agent", provenance="relayed"),
    dict(document_id="doc-notes", author=None, provenance="relayed from the Economics specialist"),
    dict(document_id="notes", author="economics-specialist", provenance=None),
])
def test_a_relayed_agents_report_is_a_peer_document_whatever_its_label(fields):
    assert is_peer_document(SuppliedText(title=None, text="x", **fields))


@pytest.mark.parametrize("fields", [
    dict(document_id="src-a", author="A. Historian", provenance="supplied by student"),
    dict(document_id="table-2", author="Office for National Statistics", provenance="downloaded by the teacher"),
    dict(document_id="extract-1", author=None, provenance=None),
])
def test_a_primary_text_is_no_peer_document(fields):
    assert not is_peer_document(SuppliedText(title=None, text="x", **fields))


def test_a_premise_cited_to_a_relayed_report_labelled_otherwise_is_not_verified():
    relayed = SuppliedText(document_id="peer-econ", title="Notes", author="Economics agent", provenance="relayed",
                           text="Inflation in 2022 was 9.1 per cent.")
    problem = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                      "symbols": [{"name": "inf", "sort": "Real", "meaning": "inflation in 2022 (per cent)"}],
                                      "premises": [{"id": "P1", "expr": {"op": "eq", "left": {"op": "var", "name": "inf"}, "right": {"op": "real", "value": "9.1"}},
                                                    "label": "inflation was 9.1 per cent", "grounding": {"kind": "quotation", "certainty": "established",
                                                    "source_refs": [{"document_id": "peer-econ", "excerpt": "Inflation in 2022 was 9.1 per cent"}]}}],
                                      "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "inf"}, "right": {"op": "real", "value": "5"}}}})
    grounded, _checks = check_problem_grounding(problem, [relayed])
    assert grounded.premises[0].grounding.verified is not True


# ------------------------------------------------------------------------------------------------------- a quotation in the judgement's sentence

SOURCE = SuppliedText(document_id="source-a", title="Source A", author=None,
                      text="Source A: a pamphlet of 1641. 'The king has ignored the people for too long, and his ministers rule in his name.'")
PRESENTS = "Explain how Source A presents the king. [3 marks]"


def _history(answer: str):
    hub, m, _ = _hub(PRESENTS, docs=[SOURCE])
    _reply, rc = hub.receive(TASK, m.message_id, answer, agent_id=HISTORY, report_id="rep-h")
    return rc


def test_a_judgement_that_quotes_the_source_in_its_sentence_is_neither_bare_nor_invented():
    rc = _history('Source A presents the king as negligent: "The king has ignored the people for too long."')
    assert [f.code for f in rc.findings] == []


def test_an_invented_quotation_is_still_named_and_supports_nothing():
    rc = _history('Source A presents the king as negligent: "The king has neglected his people for many years."')
    codes = {f.code for f in rc.findings}
    assert "INT-REQ-003" in codes and "INT-ARG-001" in codes


def test_the_judgement_with_no_quotation_is_still_a_bare_assertion():
    rc = _history("Source A presents the king as negligent.")
    assert "INT-ARG-001" in {f.code for f in rc.findings}


# ------------------------------------------------------------------------------------------------------- a recommendation asks for reasons

BM = "business-management-specialist"
BARE_RECOMMENDATION = "The firm should use penetration pricing for its new energy drink."


def _business(request: str, answer: str):
    hub, m, _ = _hub(request, subject="Business Management", agent=BM)
    _reply, rc = hub.receive(TASK, m.message_id, answer, agent_id=BM, report_id="rep-bm")
    return rc


@pytest.mark.parametrize("request_text", [
    "Recommend, with reasons, a pricing strategy for the firm's new energy drink. [4 marks]",
    "Recommend a pricing strategy for the firm's new energy drink, giving reasons. [4 marks]",
    "State, with justification, which pricing strategy the firm should use for its new energy drink. [3 marks]",
])
def test_a_recommendation_with_no_reason_is_a_bare_assertion(request_text):
    found = [f for f in _business(request_text, BARE_RECOMMENDATION).findings if f.code == "INT-ARG-001"]
    assert found and "ARG-BARE-001" in found[0].message and found[0].severity == "warning"


@pytest.mark.parametrize("answer", [
    "The firm should use penetration pricing for its new energy drink because the market is crowded and a low price builds market share quickly.",
    "The firm should use penetration pricing for its new energy drink. Penetration pricing will build market share quickly in a crowded market.",
])
def test_a_recommendation_with_its_reason_is_no_bare_assertion(answer):
    rc = _business("Recommend, with reasons, a pricing strategy for the firm's new energy drink. [4 marks]", answer)
    assert "INT-ARG-001" not in {f.code for f in rc.findings}


@pytest.mark.parametrize("request_text", ["State the pricing strategy the firm should use for its new energy drink. [1 mark]",
                                          "Identify a pricing strategy for the firm's new energy drink. [1 mark]"])
def test_a_request_for_a_statement_alone_asks_for_no_reasons(request_text):
    assert "INT-ARG-001" not in {f.code for f in _business(request_text, BARE_RECOMMENDATION).findings}
