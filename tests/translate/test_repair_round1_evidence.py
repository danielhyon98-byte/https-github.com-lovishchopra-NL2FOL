"""The evidence, release and quantity-reading repairs of repair round 1 (each with its positive test and its clean control):

* source-bound requests in other words ("Using Text C", "Compare Sources C and D", "Based on the extract": ADV-12);
* a named historian's or expert's verdict as an authority cue, and the historian verbs of the history pack (A-EVD-AUTH);
* the periods and dated values the cherry-picking rule reads ("from 2012 to 2013", "since 2012", "in 2012 were 40":
  A-EVD-CHERRY, ADV-03);
* the history parser keeps a sole judgement line as the answer, so a bare assertion is named rather than read as "no
  answer" (A-INF-BARE), while a sign-off line stays a note;
* release reads a diagnosis that did not finish as unresolved, and an overflow keeps the blocking diagnostics (INV-5);
* the quantity reader checks a derived figure from a dated series, a figure computed in the sentence before, and a
  change "over the twenty years" (A-FA-QNT): a correct one holds and a wrong one fails.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist.parser import classify_paragraphs
from epinoic_logic.adapters.history_specialist.structural import _HISTORIAN_RE
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine import verify as engine_verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.named import named_diagnostic
from epinoic_logic.translate import TranslationStatus as T
from epinoic_logic.translate.diag_core import _bound
from epinoic_logic.translate.diag_evidence import _authority_cue, _periods, _year_values, source_bound
from epinoic_logic.translate.outcome import assess_release, display_status_for

from .conftest import chain_problem
from .test_outcome import make_translation

KEY = b"repair-round1-evidence-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


# ------------------------------------------------------------------------------------------- source-bound requests

@pytest.mark.parametrize("request_text", ["Using Text C, evaluate the claim that the charge worked.", "Compare Sources C and D on the causes of the strike.",
                                          "Based on the extract, explain why prices rose.", "According to the text, why did prices rise?",
                                          "Using Document A, explain the decision."])
def test_a_request_bound_to_its_source_in_other_words_is_source_bound(request_text):
    assert source_bound(request_text)


@pytest.mark.parametrize("request_text", ["Explain why the reforms failed.", "Evaluate the claim that the charge worked.", "Compare the two policies."])
def test_clean_control_a_request_that_names_no_source_is_not_source_bound(request_text):
    assert not source_bound(request_text)


# ------------------------------------------------------------------------------------------- authorities

@pytest.mark.parametrize("text", ["The historian Margaret Hale has shown that the reforms failed.", "Historians agree that the reforms failed."])
def test_a_named_or_collective_authority_is_an_authority_cue(text):
    assert _authority_cue(text, supplied=False) is not None


def test_clean_control_a_dated_record_is_no_authority_cue():
    assert _authority_cue("The reforms failed, as the 1931 census shows.", supplied=False) is None


@pytest.mark.parametrize("text", ["Margaret Hale has shown that", "E. H. Carr has argued that", "Margaret Hale showed that"])
def test_the_history_pack_reads_a_historians_verdict_with_has_or_have(text):
    assert _HISTORIAN_RE.search(text)


@pytest.mark.parametrize("text", ["Hale's book shows that", "the census has shown that", "Stalin has shown that"])
def test_clean_control_a_possessive_a_record_or_one_name_is_no_historians_verdict(text):
    assert not _HISTORIAN_RE.search(text)


# ------------------------------------------------------------------------------------------- periods and dated values

def test_the_periods_and_dated_values_of_a_trend_are_read():
    assert _periods("Emissions fell from 2012 to 2013.", 2020) == [(2012, 2013, 15, 32)]
    assert _periods("Since 2012 emissions have fallen.", 2020) == [(2012, 2020, 0, 10)]
    values = _year_values("Emissions in 2012 were 40 and in 2020 were 30.")
    assert {y: sorted(v) for y, v in values.items()} == {2012: [40], 2020: [30]}


def test_clean_control_a_sentence_with_no_period_or_date_gives_none():
    assert _periods("Emissions fell sharply.", 2020) == [] and _year_values("Emissions fell sharply.") == {}


# ------------------------------------------------------------------------------------------- a sole judgement line

def test_a_sole_judgement_line_is_the_answer_and_a_sign_off_is_a_note():
    assert classify_paragraphs("Stalin's Five-Year Plans were a complete success.") == [("body", "Stalin's Five-Year Plans were a complete success.")]
    assert classify_paragraphs("Hope this helps.") == [("note", "Hope this helps.")]


# ------------------------------------------------------------------------------------------- release and overflow

def _assessed(incomplete):
    problem = Problem.model_validate(chain_problem())
    translation = make_translation(T.TRANSLATED, problem)
    verification = engine_verify(problem, CFG)
    display = display_status_for(translation, verification)
    return assess_release(translation, verification, None, [], display, diagnosis_incomplete=incomplete)


def test_release_reads_an_unfinished_diagnosis_as_unresolved():
    release = _assessed(["claim rule evd_src_001 raised ValueError"])
    assert not release.permitted and any(u.startswith("argument diagnosis incomplete") for u in release.unresolved)


def test_clean_control_a_finished_diagnosis_adds_no_such_reason():
    release = _assessed([])
    assert not any(u.startswith("argument diagnosis incomplete") for u in release.unresolved)


def test_an_overflow_keeps_the_blocking_diagnostics_before_records_of_higher_precedence():
    infos = [named_diagnostic("ARG-LINK-001", severity="info", assertion_ids=[f"L{i}"], derivation="ir_structure", message=f"link {i}") for i in range(6)]
    warning = named_diagnostic("EVD-SRC-001", assertion_ids=["P"], derivation="grounding_record", message="label only")
    incomplete: list[str] = []
    kept = _bound([*infos, warning], 3, incomplete, "claim")
    assert warning in kept and len(kept) == 3 and incomplete and incomplete[0].startswith("overflow: 4 diagnostic(s)")
    clean: list[str] = []
    assert len(_bound(infos[:2] + [warning], 3, clean, "claim")) == 3 and clean == []      # control: within the bound nothing is cut


# ------------------------------------------------------------------------------------------- derived figures

def _send(subject: str, agent: str, request: str, answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _req, _rc = hub.dispatch("t", agent, request)
    return hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")[1]


GEO = ("Geography", "geography-specialist")
ECON = ("Economics", "economics-specialist")


@pytest.mark.parametrize("who, request_text, answer, failed", [
    (GEO, "Describe how the town's population changed.", "The town's population was 2019: 610, 2020: 640, 2021: 670, 2022: 700, 2023: 720. It rose every year.", []),
    (GEO, "Describe how the town's population changed.", "The town's population was 2019: 610, 2020: 640, 2021: 670, 2022: 700, 2023: 720. It fell every year.", ["core-quant-1"]),
    (ECON, "By what percentage did output change?", "Output rose from 800 to 900 units. That is (900 − 800)/800 × 100 = 12.5%, so output rose by 12.5%.", []),
    (ECON, "By what percentage did output change?", "Output rose from 800 to 900 units. That is (900 − 800)/800 × 100 = 12.5%, so output rose by 15%.", ["core-quant-2"]),
    (GEO, "Describe the change in population.", "In 2000 the population was 60 million and in 2020 it was 65 million. The population grew by about 5 million over the twenty years.", []),
    (GEO, "Describe the change in population.", "In 2000 the population was 60 million and in 2020 it was 65 million. The population grew by about 9 million over the twenty years.", ["core-quant-1"]),
])
def test_a_derived_figure_is_checked_where_its_figures_are_stated(who, request_text, answer, failed):
    rc = _send(*who, request_text, answer)
    checks = {c.constraint_id: c.satisfied for c in rc.formal_checks}
    assert checks and sorted(k for k, v in checks.items() if v is False) == failed, checks
    assert ("INT-SUBJ-001" in {f.code for f in rc.findings}) is bool(failed)
    assert "CORE-QNT-001" not in {f.code for f in rc.structural_findings}      # never "could not be checked" on these
