"""Repair round 2, evidence family: EVD-CHERRY-001 reads a trend over the months of a year as it reads one over years, and
reads the words of a recovery ("recovered", "rebounded") as a rising direction (NAME-CHERRY-GENERIC). Each positive has a
clean control: the same table and wording with the period's own end values agreeing, or with both ends used."""
from __future__ import annotations

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.diag_evidence import _month_periods, _month_values, _periods

from ..evidence_support import assert_message_hygiene, blocking, deliver, diagnostics, outcome

MODES = ("report", "text")


def _v(name):
    return {"op": "var", "name": name}


def _quoted(pid, name, value, label, doc):
    return {"id": pid, "expr": {"op": "eq", "left": _v(name), "right": {"op": "real", "value": value}}, "label": label,
            "grounding": {"kind": "quotation", "source_refs": [{"document_id": doc, "excerpt": value}], "certainty": "established"}}


def _trend_case(*, table: str, period: str, evidence: str, points: list[tuple[str, str, str]], verb: str, rising: bool = True) -> dict:
    """A constructed data response: ``evidence`` cites two figures of the table (``points``: symbol, value, time label), and
    the point reads the change between them as the trend over ``period`` ("sales recovered between January and June")."""
    (a, va, ta), (b, vb, tb) = points
    point = f"Table 3 therefore shows that sales {verb} {period}."
    meaning = {a: f"sales in {ta} (units)", b: f"sales in {tb} (units)"}
    symbols = [{"name": n, "sort": "Real", "meaning": m} for n, m in meaning.items()]
    facts = [_quoted("Pa", a, va, f"sales were {va} units in {ta}", "table-3"), _quoted("Pb", b, vb, f"sales were {vb} units in {tb}", "table-3")]
    change = {"op": "gt" if rising else "lt", "left": _v(b), "right": _v(a)}
    first = {"problem": {"ir_version": "1.0", "problem_id": "p-k1", "request_id": "x", "claim_id": "x", "query": "entailment", "symbols": symbols,
                         "premises": facts, "conclusion": {"id": "C", "expr": change, "label": f"sales changed from {va} to {vb}"}},
             "interpretation": {"reading": "two quoted figures", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}
    trend = {"name": "trend", "sort": "Bool", "meaning": f"sales {verb} {period}",
             "grounding": {"kind": "specialist_inference", "source_refs": [], "certainty": "established"}}
    link = {"id": "L1", "expr": {"op": "implies", "left": change, "right": _v("trend")},
            "label": f"the change from {ta} to {tb} shows the trend {period}",
            "grounding": {"kind": "specialist_inference", "source_refs": [], "certainty": "established"}}
    second = {"problem": {"ir_version": "1.0", "problem_id": "p-k2", "request_id": "x", "claim_id": "x", "query": "entailment",
                          "symbols": symbols + [trend], "premises": facts + [link],
                          "conclusion": {"id": "C", "expr": _v("trend"), "label": f"sales {verb} {period}"}},
              "interpretation": {"reading": "the cited change, read as the period's trend", "glossary": [], "ambiguity_flags": []},
              "ambiguous": False, "unsupported_reason": None}
    return {
        "case_format": "argdiag-corpus/1", "id": "monthly-trend", "family": "evidence", "expected_label": "cherry_picked_data",
        "acceptable_labels": [], "title": "monthly trend", "subject": "Business", "task_type": "data_response", "agent_id": "business-specialist",
        "request": f"Using Table 3, describe the change in the firm's monthly sales {period}. [2 marks]",
        "answer": f"{evidence} {point}",
        "supplied_texts": [{"document_id": "table-3", "title": "Table 3", "text": table}],
        "ids": {"task_id": "task-monthly", "request_id": "req-monthly", "report_id": "rep-monthly", "plan_id": "plan-monthly"},
        "modes": [{"name": "report", "delivery": "report", "synthesis": "carried"}, {"name": "text", "delivery": "text", "synthesis": "carried"}],
        "report_claims": [
            {"claim_id": "k1", "text": evidence, "role": "evidence", "materiality": "supporting",
             "source_refs": [{"document_id": "table-3", "excerpt": va}, {"document_id": "table-3", "excerpt": vb}]},
            {"claim_id": "k2", "text": point, "role": "point", "supporting": ["k1"]}],
        "translations": [{"contains": evidence.rstrip("."), "proposal": first}, {"contains": point.rstrip("."), "proposal": second}],
        "fidelity_review": "faithful"}


MONTHS = "Table 3: the firm's monthly sales (units). January: 120. February: 90. March: 100. April: 95. May: 105. June: 110."
MONTHS_UP = "Table 3: the firm's monthly sales (units). January: 80. February: 90. March: 100. April: 95. May: 105. June: 110."
YEARS = "Table 3: the firm's annual sales (units). 2012: 100. 2013: 104. 2014: 99. 2016: 97. 2018: 98. 2020: 96."
SUB_PERIOD = "Sales recovered from 90 in February to 100 in March."


@pytest.mark.parametrize("delivery", MODES)
@pytest.mark.parametrize("period", ["between January and June", "from January to June", "in the first half of the year", "in the first six months"])
def test_a_months_trend_drawn_from_inner_months_is_cherry_picked_data(period, delivery):
    case = _trend_case(table=MONTHS, period=period, evidence=SUB_PERIOD, verb="recovered",
                       points=[("s_feb", "90", "February"), ("s_mar", "100", "March")])
    _case, rc = deliver(case, delivery)
    [d] = diagnostics(rc, "EVD-CHERRY-001")
    assert d.defect == "cherry_picked_data" and d.severity == "warning"
    assert "120 for January" in d.message and "110 for June" in d.message and "fell" in d.message   # the omitted end values are named
    assert_message_hygiene([d])
    assert outcome(rc, d.claim_ids[0]).display_status is S.ENTAILED   # the diagnosis never changes the display


@pytest.mark.parametrize("delivery", MODES)
def test_a_recovery_over_years_read_from_its_first_two_years_is_cherry_picked_data(delivery):
    case = _trend_case(table=YEARS, period="between 2012 and 2020", evidence="Sales recovered from 100 in 2012 to 104 in 2013.", verb="recovered",
                       points=[("s12", "100", "2012"), ("s13", "104", "2013")])
    _case, rc = deliver(case, delivery)
    [d] = diagnostics(rc, "EVD-CHERRY-001")
    assert "100 for 2012" in d.message and "96 for 2020" in d.message and "fell" in d.message


@pytest.mark.parametrize("verb", ["rebounded", "surged", "recovered"])
def test_the_words_of_a_recovery_state_a_rising_direction(verb):
    case = _trend_case(table=MONTHS, period="between January and June", evidence=SUB_PERIOD, verb=verb,
                       points=[("s_feb", "90", "February"), ("s_mar", "100", "March")])
    _case, rc = deliver(case, "report")
    assert [d.code for d in diagnostics(rc, "EVD-CHERRY-001")] == ["EVD-CHERRY-001"]


# ------------------------------------------------------------------------------------------------------- controls

@pytest.mark.parametrize("delivery", MODES)
def test_a_months_trend_the_end_values_bear_out_is_clean(delivery):
    case = _trend_case(table=MONTHS_UP, period="between January and June", evidence=SUB_PERIOD, verb="recovered",
                       points=[("s_feb", "90", "February"), ("s_mar", "100", "March")])
    _case, rc = deliver(case, delivery)
    assert diagnostics(rc, "EVD-CHERRY-001") == []
    assert blocking(diagnostics(rc, prefix="EVD-")) == [], [(d.code, d.message[:120]) for d in diagnostics(rc, prefix="EVD-")]


@pytest.mark.parametrize("delivery", MODES)
def test_a_months_trend_read_from_both_end_months_is_clean(delivery):
    case = _trend_case(table=MONTHS_UP, period="between January and June", evidence="Sales rose from 80 in January to 110 in June.", verb="rose",
                       points=[("s_jan", "80", "January"), ("s_jun", "110", "June")])
    _case, rc = deliver(case, delivery)
    assert diagnostics(rc, "EVD-CHERRY-001") == []


def test_a_months_fall_drawn_from_both_ends_is_clean_even_when_inner_months_rise():
    case = _trend_case(table=MONTHS, period="between January and June", evidence="Sales fell from 120 in January to 110 in June.", verb="fell",
                       points=[("s_jan", "120", "January"), ("s_jun", "110", "June")], rising=False)
    _case, rc = deliver(case, "report")
    assert diagnostics(rc, "EVD-CHERRY-001") == []


# ------------------------------------------------------------------------------------------------------- the readings

@pytest.mark.parametrize("text, period", [
    ("Sales recovered between January and June.", (10001, 10006)), ("from January to June", (10001, 10006)), ("Jan–Jun", (10001, 10006)),
    ("in the first half of the year", (10001, 10006)), ("in the second half of 2021", (10007, 10012)), ("the first quarter of the year", (10001, 10003)),
    ("the first six months", (10001, 10006))])
def test_month_periods_are_read(text, period):
    assert [(a, b) for a, b, _s, _e in _month_periods(text)] == [period]
    assert _periods(text) == []   # months are never years


@pytest.mark.parametrize("text", ["Sales may rise from march to june.", "The troops march on.", "We may see a rise.", "between 2012 and 2020"])
def test_lower_case_words_that_spell_a_month_are_no_period(text):
    assert _month_periods(text) == []


def test_month_values_are_read_like_year_values():
    assert {k - 10000: sorted(v) for k, v in _month_values(MONTHS).items()} == {1: [120], 2: [90], 3: [100], 4: [95], 5: [105], 6: [110]}
    assert {k - 10000: sorted(v) for k, v in _month_values("In January sales were 120 units; 110 in June.").items()} == {1: [120], 6: [110]}
    # two values for one month (two years of data) are never read as the month's one value
    assert sorted(_month_values("January 2020: 100. January 2021: 120.")[10001]) == [100, 120]


# ------------------------------------------------------------------------------------------------------- a source cited for the opposite stance
# EVD-SRC-006 (NAME-E04A): a paraphrase that credits a document with one stance where the document states only the other.

from epinoic_logic.translate.diag_evidence import _stances  # noqa: E402

from .. import argdiag_cases as C  # noqa: E402


@pytest.mark.parametrize("delivery", MODES)
def test_e04a_a_source_cited_for_the_opposite_stance_is_a_source_mismatch(delivery):
    _case, rc = deliver("e04a_source_mismatch_paraphrase", delivery)
    found = diagnostics(rc, "EVD-SRC-006")
    assert found and all(d.defect == "source_mismatch" and d.severity == "warning" for d in found)
    assert any("accepted" in d.message and "protest" in d.message for d in found)
    assert_message_hygiene(found)


def _stance_case(claim: str, source: str) -> dict:
    case = C.load_case("e04a_source_mismatch_paraphrase")
    case = {**case, "id": "stance", "answer": claim, "report_claims": [], "translations": [], "modes": [{"name": "text", "delivery": "text", "synthesis": "none"}],
            "supplied_texts": [{"document_id": "source-a", "title": "Source A", "text": source}]}
    return case


SPEECH = ("Source A: from a speech by a German delegate at Versailles, June 1919. 'This treaty is a humiliation imposed on the German "
          "people, and we sign it only under protest.'")


@pytest.mark.parametrize("claim, source", [
    ("Source A shows that the German delegate signed the treaty only under protest.", SPEECH),               # the same stance
    ("Source A shows that the German delegate did not accept the treaty as fair.", SPEECH),                  # the stance negated: the same
    ("Source A shows that the treaty was welcomed by the delegate.",
     "Source A: the treaty was welcomed by some delegates and condemned by others."),                        # the document states both
    ("Source A shows that the delegate spoke at Versailles in June 1919.", SPEECH),                           # no stance claimed
])
def test_a_paraphrase_with_the_documents_own_stance_or_none_is_no_mismatch(claim, source):
    _case, rc = deliver(_stance_case(claim, source), "text")
    assert diagnostics(rc, "EVD-SRC-006") == []


def test_the_stance_reader_reads_negation_within_the_clause():
    assert _stances("they did not accept the terms") == (set(), {"accept"})
    assert _stances("the settlement was not unfair") == ({"unfair"}, set())
    assert _stances("we sign it only under protest, and it is a humiliation") == (set(), {"protest", "humiliation"})


# ------------------------------------------------------------------------------------------------------- the task's notation in words
# EVD-SRC-005 (ADV2-11): a task-authority label that writes the task's notation in words states what the task states.

def _notation_case(label: str) -> dict:
    gk = {"kind": "general_knowledge", "source_refs": [], "certainty": "established"}
    task = {"kind": "task_setting", "source_refs": [], "certainty": "established"}
    problem = {"ir_version": "1.0", "problem_id": "p-n", "request_id": "x", "claim_id": "x", "query": "entailment",
               "symbols": [{"name": "one", "sort": "Bool", "meaning": "y is 1"}, {"name": "sq", "sort": "Bool", "meaning": label, "grounding": task}],
               "premises": [{"id": "f1", "expr": _v("sq"), "label": label, "materiality": "material", "grounding": task},
                            {"id": "r1", "expr": {"op": "implies", "left": _v("one"), "right": {"op": "not", "arg": _v("sq")}},
                             "label": "if y is 1 then y squared is 1, which is not greater than 4", "materiality": "material", "grounding": gk}],
               "conclusion": {"id": "C", "expr": {"op": "not", "arg": _v("one")}, "label": "y is not 1."}}
    return {"case_format": "argdiag-corpus/1", "id": "notation", "family": "evidence", "expected_label": "none", "acceptable_labels": [],
            "title": "notation", "subject": "Mathematics: analysis and approaches", "task_type": "short_answer", "agent_id": "mathematics-specialist",
            "request": "The real number y satisfies y² > 4. Explain whether y can be 1.",
            "answer": "y is not 1. Since y² > 4 and 1² = 1 is not greater than 4, y cannot be 1.", "supplied_texts": [],
            "ids": {"task_id": "task-n", "request_id": "req-n", "report_id": "rep-n", "plan_id": "plan-n"},
            "modes": [{"name": "text", "delivery": "text", "synthesis": "none"}], "report_claims": [],
            "translations": [{"contains": "y is not 1.", "proposal": {"problem": problem, "interpretation": {"reading": "as written", "glossary": [], "ambiguity_flags": []},
                                                                      "ambiguous": False, "unsupported_reason": None}}],
            "fidelity_review": "faithful"}


@pytest.mark.parametrize("label", ["y squared is greater than 4", "the task states that y squared is more than 4"])
def test_a_task_label_that_writes_the_tasks_notation_in_words_is_not_unchecked(label):
    _case, rc = deliver(_notation_case(label), "text")
    assert diagnostics(rc, "EVD-SRC-005") == []


@pytest.mark.parametrize("label", ["y is greater than 4", "y squared is less than 4", "y cubed is greater than 4"])
def test_a_task_label_the_notation_does_not_spell_is_still_unchecked(label):
    _case, rc = deliver(_notation_case(label), "text")
    [d] = diagnostics(rc, "EVD-SRC-005")
    assert d.severity == "warning" and d.assertion_ids == ["f1"]
