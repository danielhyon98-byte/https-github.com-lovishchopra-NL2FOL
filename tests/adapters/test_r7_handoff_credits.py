"""Round-7 arena handoffs to the parsers' owner: who a quotation is credited to.

* combinator-faults-5: a synthesis crediting a specialist's own prose to a supplied text named by its author with a closing parenthesis
  ('Kestrelford Borough Council (a fictional council)') or by a non-literary kind ('the leaflet', 'the textbook', 'the bread price
  table') was not named. An author's closing parenthesis is a description, not a name (the name and its last word now name the text),
  and a supplied text named by such a kind is credited as 'the poem' is (INT-LEDGER-025).
* r7 english handoff 5 (bm-p7ac): a possessive view with its complement clause ('The Economics specialist's view that the company could
  "carry on as before"') was no credit, so a supplied text's words credited to a colleague got no CORE-SRC-005. It is now a credit, in
  the shared rule (``sources.quotation_credit``) and in the core pack, unless the clause names its own speaker; a colleague credited by
  name whose report was not supplied is a credit too.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.sources import document_mentions, quotation_credit
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.integrity.ledger import misattributed_quotations
from epinoic_logic.translate.contracts import SuppliedText

KEY = b"adapters-r7-handoff-credits-key-01"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)

LEAFLET = SuppliedText(document_id="doc-leaflet", title="Love it? Don't bin it. (council leaflet, supplied text)", author="Kestrelford Borough Council (a fictional council)",
                       text="Every week a household throws away food worth a family meal. Love it? Don't bin it.")
ENGLISH = SuppliedText(document_id="report:rep-en", title=None, author="english-specialist",
                       text="The leaflet turns a statistic into a picture: an abstract weight becomes a meal the reader can see.")
BREAD = SuppliedText(document_id="doc-bread", title="Price of a loaf of bread in Berlin, 1918–1923 (table from the student's History textbook, supplied text)",
                     author="Table typed in by the student", text="1918: 0.53 marks. 1922: 163 marks. 1923: 201,000,000,000 marks.")
MATHS = SuppliedText(document_id="report:rep-ma", title=None, author="mathematics-aa-specialist", text="An exponential fit holds to 1922, but the model is not a good fit for 1923.")
POET = SuppliedText(document_id="doc-poem", title="Allotment, November (poem from a class handout, supplied text)", author="Ruth Ashdown (a fictional poet)",
                    text="The beans hang black on the frost-bitten frame.")

WORDS = "an abstract weight becomes a meal the reader can see"
MODEL = "the model is not a good fit for 1923"


@pytest.mark.parametrize("sentence", [
    f'Kestrelford Borough Council writes that "{WORDS}".',
    f'The council says "{WORDS}".',
    f'The leaflet itself admits that "{WORDS}".',
    f'The council leaflet states that "{WORDS}".',
])
def test_cf5_the_leaflets_author_and_kind_credit_the_leaflet(sentence):
    docs = {d.document_id: d for d in (LEAFLET, ENGLISH)}
    credit = quotation_credit(sentence, sentence.index('"'), docs)
    assert credit is not None and credit.document_id == "doc-leaflet"
    [message] = misattributed_quotations(sentence, docs)
    assert "doc-leaflet" in message and "english-specialist report rep-en" in message


@pytest.mark.parametrize("sentence", [
    f"The textbook states that '{MODEL}'.",
    f"According to the textbook, '{MODEL}'.",
    f"The bread price table says that '{MODEL}'.",
    f"As the table typed in by the student says, '{MODEL}'.",
])
def test_cf5_a_supplied_table_named_by_kind_is_credited(sentence):
    docs = {d.document_id: d for d in (BREAD, MATHS)}
    [message] = misattributed_quotations(sentence, docs)
    assert "doc-bread" in message and "mathematics-aa-specialist report rep-ma" in message


def test_cf5_controls_a_right_credit_and_a_colleagues_own_table_are_no_misattribution():
    docs = {d.document_id: d for d in (BREAD, MATHS)}
    assert misattributed_quotations(f"The Mathematics specialist states that '{MODEL}'.", docs) == []
    # a kind after a capitalised name or a possessive is that source's, not the supplied table
    assert quotation_credit(f"The Mathematics specialist's table shows '{MODEL}'.", 37, docs) is None or \
        quotation_credit(f"The Mathematics specialist's table shows '{MODEL}'.", 37, docs).document_id != "doc-bread"
    leaf = {d.document_id: d for d in (LEAFLET, ENGLISH)}
    assert misattributed_quotations('The leaflet asks "Love it? Don\'t bin it."', leaf) == []  # the leaflet's own words


def test_cf5_an_authors_closing_parenthesis_is_a_description_not_a_name():
    assert document_mentions("Ashdown writes about frost.", POET) == [(0, 7)]
    assert document_mentions("Ruth Ashdown writes about frost.", POET)
    assert document_mentions("Kestrelford Borough Council printed it.", LEAFLET)


# ------------------------------------------------------------------ r7 english handoff 5: a possessive view credits its clause

FIZZ = SuppliedText(document_id="doc-fizz", title="Fizzbrook Ltd (case study, supplied text)", author="Task data",
                    text="The managing director, Tomas Reyes, says: \"Our customers are loyal. We should be able to put the whole tax on the shelf price and carry on as before.\"")
FIZZ_REYES = SuppliedText(document_id="doc-fizz", title="Fizzbrook case study", author="Tomas Reyes",
                          text="Tomas Reyes, the owner, said the company could carry on as before if sales held up.")
PEER = SuppliedText(document_id="peer:ec-p7a", title="Economics answer", author="economics-specialist",
                    text="The tax raises the price paid by consumers from $1.60 to $2.00. Demand is price inelastic, because its absolute value, 0.67, is less than 1.")
QUESTION = "Using the case study and the Economics specialist's analysis, evaluate the plan."


def bm_receipt(answer: str, texts):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Business Management", task_type="short_answer",
                           selected_agent_ids=["business-management-specialist"], allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", "business-management-specialist", QUESTION, list(texts))
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="business-management-specialist", report_id="r1")
    return [s for s in rc.structural_findings if s.code == "CORE-SRC-005"]


BM_P7AC = "The Economics specialist's view that the company could \"carry on as before\" ignores the falling cash flow, so the plan is risky."


def test_bm_p7ac_a_case_studys_words_credited_to_the_supplied_colleague_are_core_src_005():
    [f] = bm_receipt(BM_P7AC, [FIZZ, PEER])
    assert f.severity == "error" and "carry on as before" in f.message and "doc-fizz" in f.message and f.claim_ids


def test_bm_p7ac_a_case_studys_words_credited_to_a_colleague_not_supplied_are_core_src_005():
    [f] = bm_receipt(BM_P7AC, [FIZZ_REYES])
    assert f.severity == "error" and "carry on as before" in f.message and "doc-fizz" in f.message and "not supplied" in f.message


@pytest.mark.parametrize("answer", [
    "Tomas Reyes's view that the company could \"carry on as before\" ignores the falling cash flow, so the plan is risky.",   # bm-p7ad: the right credit
    "The Economics specialist's view that \"Demand is price inelastic\" supports passing on part of the tax.",                 # the colleague's own words
    "The Economics specialist's point is that Tomas Reyes wants to \"carry on as before\", which ignores the tax.",           # the clause names its speaker
    "The case study's claim that the firm can \"carry on as before\" is weak.",
])
def test_bm_p7ad_controls_get_no_core_src_005(answer):
    assert bm_receipt(answer, [FIZZ, PEER]) == []


@pytest.mark.parametrize("answer", [
    "As the Business Management specialist, my view is that the firm cannot \"carry on as before\".",    # the agent's own name
    "Tomas Reyes's view that the company could \"carry on as before\" ignores the falling cash flow.",
])
def test_bm_p7ad_controls_without_the_colleagues_report(answer):
    assert bm_receipt(answer, [FIZZ_REYES]) == []


def test_the_shared_rule_reads_the_view_credit_and_its_inner_speaker():
    docs = {d.document_id: d for d in (FIZZ, PEER)}
    credit = quotation_credit(BM_P7AC, BM_P7AC.index('"'), docs)
    assert credit is not None and credit.document_id == "peer:ec-p7a"
    inner = "The Economics specialist's point is that Tomas Reyes wants to \"carry on as before\"."
    assert quotation_credit(inner, inner.index('"'), docs) is None
    [message] = misattributed_quotations(BM_P7AC, docs)
    assert "doc-fizz" in message
