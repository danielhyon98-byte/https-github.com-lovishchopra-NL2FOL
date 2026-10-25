"""Repair round 2, the worked-equation checker of the core pack (B25): every link of a worked line is checked, the links
after a bare figure and the equations nested in brackets included (I1), and an equation quoted from another text is no
arithmetic of the writer's own (I3). Each with its clean control."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

from .. import argdiag_cases as C
from ..stem.argdiag_hub import deliver, findings, structural

GE_LINE = "1990: (4.3 + 0.3) ÷ 5.0 × 100 = 92.0 dependants"
BM_LINE = "total costs $8,100 + ($1.80 × 3,500 = $6,300) = $14,400"


def _errors(rc) -> list:
    return [f for f in findings(rc, "INT-SUBJ-001") if f.severity == "error"]


@pytest.mark.parametrize("line, fragment", [
    ("1990: (4.3 + 0.3) ÷ 5.0 × 100 = 92.0 = 95.0 dependants", "92.0 = 95.0"),
    ("1990: (4.3 + 0.3) ÷ 5.0 × 100 = 92.0 = 0.95 × 100 dependants", "92.0 = 0.95 × 100"),
])
def test_a_wrong_link_after_a_bare_figure_is_checked(line, fragment):
    case = C.load_case("e2e-B21-ge")
    rc = deliver(case, answer=case["answer"].replace(GE_LINE, line, 1))
    assert any(fragment in f.message for f in _errors(rc)), [f.message[:160] for f in _errors(rc)]


def test_a_correct_link_after_a_bare_figure_is_clean():
    case = C.load_case("e2e-B21-ge")
    rc = deliver(case, answer=case["answer"].replace(GE_LINE, "1990: (4.3 + 0.3) ÷ 5.0 × 100 = 92.0 = 92 dependants", 1))
    assert _errors(rc) == []


def test_a_link_the_checker_cannot_read_is_named_undecided_never_passed():
    case = C.load_case("e2e-B21-ge")
    rc = deliver(case, answer=case["answer"].replace(GE_LINE, "1990: (4.3 + 0.3) ÷ 5.0 × 100 = 92.0 = 2^k = 95.0 dependants", 1))
    assert any("worked arithmetic" in f.message for f in structural(rc, "CORE-QNT-001"))


@pytest.mark.parametrize("line, fragment", [
    ("total costs $8,100 + ($1.80 × 3,500 = $6,900) = $14,400", "1.80 × 3,500 = 6,900"),     # the nested equation
    ("total costs $8,100 + ($1.80 × 3,500 = $6,300) = $15,400", "= 15,400"),                 # the outer one
])
def test_an_equation_nested_in_brackets_and_its_outer_equation_are_each_checked(line, fragment):
    case = C.load_case("e2e-B23-bm")
    rc = deliver(case, answer=case["answer"].replace(BM_LINE, line, 1))
    assert any(fragment in f.message for f in _errors(rc)), [f.message[:160] for f in _errors(rc)]


def test_the_correct_nested_line_is_decided_in_both_views():
    rc = deliver("e2e-B23-bm")
    ids = {c.constraint_id: c.satisfied for c in rc.formal_checks if c.constraint_id.startswith("core-")}
    assert any(k.startswith("core-nested-") for k in ids) and all(v is True for k, v in ids.items() if "stem" in k)
    assert _errors(rc) == []


PED = "The price of a drink rose from $1.60 to $1.90 and the quantity sold fell from 120 to 105. Calculate the PED and explain whether demand is elastic."


def _business(answer: str):
    hub = RouterHub(signing_key=b"repair-round-2-packs-key-0123456789ab", config=SolverConfig(timeout_ms=4000, memory_max_mb=None))
    agent = "business-management-specialist"
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Business Management", task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, PED, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def test_an_equation_quoted_from_another_text_is_no_arithmetic_of_the_writer():
    rc = _business('The Economics report states "PED = −12.50 ÷ 18.75 = −0.80", but the correct value is −12.50 ÷ 18.75 = −0.67, '
                   'so demand is price inelastic.')
    assert [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"] == []


def test_the_writers_own_wrong_equation_is_still_an_error():
    rc = _business("The PED is −12.50 ÷ 18.75 = −0.80, so demand is price inelastic.")
    assert [f.code for f in rc.findings if f.severity == "error"] == ["INT-SUBJ-001"]
