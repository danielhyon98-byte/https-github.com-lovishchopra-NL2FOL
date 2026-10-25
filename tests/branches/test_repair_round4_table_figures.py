"""Repair round 4, ADV4-12: a figure the answer reads from a supplied data table for a year, which the table states
otherwise, is named whether or not the claim is translated (CORE-SRC-007, warning): ``invented_figure`` when the table
states the figure for no year, ``source_mismatch`` when it states it for another year. A chained trend ("then rose sharply
to 11.4% in 2020 before falling to 8.1% in 2021") is read link by link, so a continuation is never paired with a figure
before an unread one (a false INT-SUBJ-001 labelled an arithmetic slip). Controls: the table's own figures, rounded or in
another scale, a figure of another quantity in its own clause, a change rather than a level, a year the table does not
hold, and a table nothing names."""
from __future__ import annotations

import pytest

from epinoic_logic import named
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText

KEY = b"stem-channel-test-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
TABLE = SuppliedText(document_id="table-1", title="Table 1",
                     text="Table 1: Unemployment rate in Country P (%)\n2015: 7.2\n2016: 6.8\n2017: 6.1\n2018: 5.9\n2019: 6.4\n2020: 8.9\n2021: 8.1")
FIGURE = SuppliedText(document_id="fig-2", title="Figure 2", text="Figure 2: City population (millions)\n1990: 1.1\n2000: 1.6\n2010: 1.9\n2020: 2.3")


def _receipt(subject: str, request: str, answer: str, texts):
    agent = {"Economics": "economics-specialist", "Geography": "geography-specialist"}[subject]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _, _rq = hub.dispatch("t", agent, request, list(texts))
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return rc


def _named(rc, code):
    return [d for d in (rc.named_diagnostics or []) if d.code == code]


@pytest.mark.parametrize("subject, request_text, answer, texts, defect", [
    ("Economics", "Using Table 1, describe the change in unemployment in Country P between 2015 and 2021. [4 marks]",
     "Unemployment fell from 7.2% in 2015 to 5.9% in 2018, then rose sharply to 11.4% in 2020 before falling to 8.1% in 2021.", [TABLE], "invented_figure"),
    ("Economics", "Describe unemployment in Country P in 2020. [2 marks]",
     "According to Table 1, unemployment in Country P reached 11.4% in 2020, its highest level in the period.", [TABLE], "invented_figure"),
    ("Geography", "Using Figure 2, describe the population of the city in 2010. [2 marks]",
     "Figure 2 shows the city's population was 2.4 million in 2010.", [FIGURE], "invented_figure"),
    ("Economics", "Using Table 1, describe unemployment in Country P in 2019. [2 marks]",
     "Unemployment in Country P was 8.9% in 2019.", [TABLE], "source_mismatch"),
])
def test_a_figure_the_named_table_states_otherwise_is_named(subject, request_text, answer, texts, defect):
    rc = _receipt(subject, request_text, answer, texts)
    [d] = _named(rc, "CORE-SRC-007")
    assert d.defect == defect and d.severity == "warning"
    assert "INT-SUBJ-001" not in {f.code for f in rc.findings}       # the trend is read link by link: no arithmetic slip


@pytest.mark.parametrize("subject, request_text, answer, texts", [
    ("Economics", "Using Table 1, describe the change in unemployment in Country P between 2015 and 2021. [4 marks]",
     "Unemployment fell from 7.2% in 2015 to 5.9% in 2018, then rose sharply to 8.9% in 2020 before falling to 8.1% in 2021.", [TABLE]),
    ("Economics", "Using Table 1, describe unemployment in Country P in 2020. [2 marks]", "Unemployment in Country P was about 9% in 2020.", [TABLE]),
    ("Geography", "Using Figure 2, describe the population of the city in 2010. [2 marks]", "The city's population was 1,900,000 in 2010.", [FIGURE]),
    ("Economics", "Using Table 1, describe unemployment in Country P in 2020. [2 marks]",
     "Unemployment rose to 8.9% in 2020, while inflation fell to 1.2% in 2020.", [TABLE]),
    ("Economics", "Using Table 1, describe unemployment in Country P in 2020. [2 marks]", "Unemployment rose by 2.5 points in 2020.", [TABLE]),
    ("Economics", "Using Table 1, describe unemployment in Country P. [2 marks]", "Unemployment in Country P was 4.1% in 2012.", [TABLE]),
    ("Economics", "Describe unemployment in Country P in 2020. [2 marks]", "Unemployment in Country P was 11.4% in 2020.", [TABLE]),
])
def test_control_the_tables_figures_another_quantity_a_change_or_an_unnamed_table_are_not_named(subject, request_text, answer, texts):
    assert _named(_receipt(subject, request_text, answer, texts), "CORE-SRC-007") == []


def test_the_code_is_labelled_by_its_message():
    assert named.defect_of("CORE-SRC-007", "claim g1 states 11.4 for 2020 ... and states 11.4 for no year") == "invented_figure"
    assert named.defect_of("CORE-SRC-007", "claim g1 states 8.9 for 2019 ... and states 8.9 for 2020: another year's figure") == "source_mismatch"


# ------------------------------------------------------------------ a chained trend read link by link (the pair reader)

@pytest.mark.parametrize("sentence, pairs", [
    # a level the reader leaves unread stands between: the continuation is not chained to the figure before it
    ("Unemployment fell from 7.2% in 2015 to 5.9% in 2018, peaking at 11.4% in 2020, before falling to 8.1% in 2021.", [("7.2", "5.9")]),
    ("Unemployment fell from 7.2% in 2015 to 5.9% in 2018 and, after 11.4% in 2020, fell to 8.1% in 2021.", [("7.2", "5.9")]),
    # a link read with its adverb ("rose sharply to") chains the next one from it
    ("Unemployment fell from 7.2% in 2015 to 5.9% in 2018, then rose sharply to 11.4% in 2020 before falling to 8.1% in 2021.",
     [("7.2", "5.9"), ("5.9", "11.4"), ("11.4", "8.1")]),
])
def test_a_continuation_is_never_chained_across_an_unread_level(sentence, pairs):
    from epinoic_logic.branches import quant
    assert [(p.before.num, p.last.num) for p in quant._pairs(sentence)] == pairs


@pytest.mark.parametrize("sentence, pairs", [
    # the stated change of the link before and the years are read, not unread levels: the chain goes on
    ("Unemployment rose from 1.9 million in 1929 to 3.1 million in 1930, a rise of 63 per cent, before climbing to 5.6 million in 1932.",
     [("1.9", "3.1"), ("3.1", "5.6")]),
    ("Unemployment fell from 7.2% in 2015 to 5.9% in 2018, a fall of 18 per cent, before falling to 5.1% in 2021.", [("7.2", "5.9"), ("5.9", "5.1")]),
])
def test_control_a_stated_change_or_a_year_between_links_keeps_the_chain(sentence, pairs):
    from epinoic_logic.branches import quant
    assert [(p.before.num, p.last.num) for p in quant._pairs(sentence)] == pairs


def test_the_si_reading_reads_a_link_with_its_adverb_as_the_general_one_does():
    from epinoic_logic.branches import quant
    sentence = "The extension fell from 7.2 cm in 2015 to 5.9 cm in 2018, then rose sharply to 11.4 cm in 2020 before falling to 8.1 cm in 2021."
    general = [(p.before.num, p.last.num) for p in quant._pairs(sentence)]
    si = [(p.before.num, p.last.num) for p in quant._pairs(sentence, quant._si_patterns())]
    assert general == si == [("7.2", "5.9"), ("5.9", "11.4"), ("11.4", "8.1")]
