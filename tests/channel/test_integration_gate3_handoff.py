"""Integration gate 3, handoff fixer: the channel's class sweep and the counterexample note of a joined STEM problem.

The critical input stalls of the round (the ledger's incidental figures, the figure-ahead pattern) were fixed at their cause by
the parallel fixers; the handoff fixer swept the modules it changed for the same classes (a lazy or greedy scan before an
optional blank run, a scan repeated for every token or marker) and fixed each instance found at its cause, the old reading
kept as the specification:

* ``bus._FOLDED_TAIL_RE`` (and the ledger's copy): searched from every digit of a long run of digits, the count re-read the
  rest of the run each time. A structured report may carry an unresolved issue of any length (the contract bounds their
  number, not their length), so one issue of 16,000 digits cost 2.4 s to receive and 2.5 s to audit, quadratic. The count is
  read from the first digit of its run now, and taken whole.
* ``bus._framed_check_result``: the gap "blanks, 'by', blanks" between an outcome and a later framed name was a fullmatch
  from the outcome's end to each name's start, so a long blank run after an outcome was read again for every name after it
  ('The History report holds' + tabs + 'Z3 ' repeated: 0.34 s at 40,000 characters, 1.47 s at 80,000). It is read once per
  outcome now.
* ``bus._PREMISE_VALUE_RE`` (deferred by the core fixer as bounded: a premise label holds at most 1,000 characters): the lazy
  value re-read the optional suffix's blank run at every character it grew by, quadratic in a blank run inside the label.
  ``premise_value`` reads the same value in linear time.

The stem fixer's handoff (optional item 2): a STEM check that joins the two readings of a middle dot between digits names its
symbols ``d_c``, ``d_r`` and ``p_c``, ``p_r``, so its INT-SUBJ-001 / INT-SUBJ-004 message carried no values; it now gives the
engine's values per reading, and the overseer's receipt check (which binds the channel's own note) agrees.
"""
from __future__ import annotations

import random
import re
import time

import pytest

from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import bus as B
from epinoic_logic.channel.bus import check_result_statement, premise_value
from epinoic_logic.integrity import ledger as L
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

from ..core_hostile import INPUTS, SHAPES, one, sweep
from ..growth import growth
from ..timing import empty_caches
# the overseer only through its public package API; a test that attaches it is skipped where it is not installed
from ..overseer_attach import CFG, KEY, make_auditor

#: The ledger's folded-tail pattern as it was written before integration gate 3 (the reference its linear form is held to).
_LEDGER_FOLDED_TAIL_BEFORE = re.compile(r"\d+ (?:claims|sentences) beyond the report's claim limit \(\d+\) were merged into claim (?P<tail>\S+)")
FOLD = "{n} sentences beyond the report's claim limit (512) were merged into claim {tail} and were not individually roled or checked"


# --------------------------------------------------------------------------- the folded-tail count (critical: quadratic in an issue)


def _random_issue(rng: random.Random) -> str:
    pieces = ["1", "12", "512", "0", "x", " ", "  ", "\t", "(", ")", "claims", "sentences", " claims beyond", "h.tail", "g.tail@economics-specialist",
              FOLD.format(n=89, tail="h.tail"), FOLD.format(n=7, tail="p-tail@english-a-lang-lit-specialist").replace("sentences", "claims"),
              " beyond the report's claim limit (", "512) were merged into claim ", "٣", "a1", "9" * 30]
    return "".join(rng.choice(pieces) for _ in range(rng.randint(0, 8)))


def test_the_folded_tail_patterns_read_what_their_old_forms_read():
    rng = random.Random(3)
    for _ in range(20000):
        issue = _random_issue(rng)
        old, new = B._FOLDED_TAIL_REFERENCE_RE.search(issue), B._FOLDED_TAIL_RE.search(issue)
        assert ((old.span(), old.groupdict()) if old else None) == ((new.span(), new.groupdict()) if new else None), issue
        old, new = _LEDGER_FOLDED_TAIL_BEFORE.search(issue), L._FOLDED_TAIL_RE.search(issue)
        assert (old.span(), old.group("tail")) == (new.span(), new.group("tail")) if old else new is None, issue


@pytest.mark.parametrize("pattern", [B._FOLDED_TAIL_RE, L._FOLDED_TAIL_RE], ids=["channel", "ledger"])
def test_the_folded_tail_count_is_read_in_linear_time(pattern):
    ratio, small, large = growth(pattern.search, "1" * 20000 + "x", "1" * 80000 + "x")
    assert large < 0.05 and ratio < 8, (ratio, small, large)  # 1.45 s at 16,000 digits before the gate (quadratic)


def _structured(issue: str) -> dict:
    text = "The Factory Act of 1833 banned the employment of children under nine in textile mills."
    ids = dict(request_id="q", task_id="t", report_id="r1", agent_id="history-specialist", subject="History", task_type="short_answer")
    report = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), created_at="2026-11-01T00:00:00Z",
                              claims=[ClaimRecord(**ids, claim_id="h1.1", claim_text=text, claim_role="point")], unresolved_issues=[issue])
    return report.model_dump(mode="json")


def test_a_structured_report_with_a_long_unresolved_issue_crosses_the_hub_and_its_audit_in_linear_time():
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"]))
        m = hub.dispatch("t", "history-specialist", "Explain the significance of the Factory Act of 1833.")[0]
        empty_caches()
        c0 = time.process_time()
        reply, rc = hub.receive("t", m.message_id, _structured("1" * 64000 + " x"), agent_id="history-specialist", report_id="r1")
        audit = hub.audit("t")
        spent = time.process_time() - c0
    finally:
        hub.close()
    assert reply is not None and rc.status.value.startswith("ACCEPTED"), rc.summary
    assert "INT-REQ-013" not in {f.code for f in rc.findings}  # a run of digits is no fold message
    assert getattr(audit.state, "value", audit.state) in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")
    assert spent < 4.0, spent  # quadratic before the gate: about 40 s each for the receive and the audit at 64,000 digits


def test_a_structured_report_with_a_long_unresolved_issue_crosses_the_hub_in_linear_time_with_no_overseer_attached():
    """The channel's half of the test above, which needs no overseer: it runs where the overseer is not installed."""
    hub = RouterHub(signing_key=KEY, config=CFG)
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"]))
        m = hub.dispatch("t", "history-specialist", "Explain the significance of the Factory Act of 1833.")[0]
        empty_caches()
        c0 = time.process_time()
        reply, rc = hub.receive("t", m.message_id, _structured("1" * 64000 + " x"), agent_id="history-specialist", report_id="r1")
        spent = time.process_time() - c0
    finally:
        hub.close()
    assert reply is not None and rc.status.value.startswith("ACCEPTED"), rc.summary
    assert "INT-REQ-013" not in {f.code for f in rc.findings}  # a run of digits is no fold message
    assert spent < 4.0, spent  # quadratic before the gate: about 40 s for the receive at 64,000 digits


def test_the_ledger_reads_a_report_with_a_long_unresolved_issue_in_linear_time():
    from ..integrity.test_integration_gate2_ledger import _SOURCE, _report, _synthesis
    rep = _report("rep-h", "history-specialist", "History", [("h1.1", _SOURCE)])
    rep = rep.model_copy(update={"unresolved_issues": ["1" * 64000 + " x", FOLD.format(n=3, tail="h1.1")]})
    syn = _synthesis([rep], [("s0", _SOURCE, ["h1.1"], "carried")])
    empty_caches()
    c0 = time.process_time()
    found = L.check_synthesis_ledger([rep], syn)
    assert time.process_time() - c0 < 2.0  # the count was searched from every digit: about 40 s at 64,000 digits before the gate
    assert not [f for f in found if f.severity == "error"], [(f.code, f.message[:120]) for f in found]


def test_control_a_fold_message_is_still_read():
    for pattern in (B._FOLDED_TAIL_RE, L._FOLDED_TAIL_RE):
        m = pattern.search("note; " + FOLD.format(n=89, tail="h.tail@history-specialist-b-cc7267dc"))
        assert m is not None and m.group("tail") == "h.tail@history-specialist-b-cc7267dc"
    m = B._FOLDED_TAIL_RE.search("x" + FOLD.format(n=1234, tail="s.tail"))
    assert (m.group("n"), m.group("limit"), m.group("tail")) == ("1234", "512", "s.tail")
    hub = RouterHub(signing_key=KEY, config=CFG)
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"]))
        msg = hub.dispatch("t", "history-specialist", "Explain the significance of the Factory Act of 1833.")[0]
        reply, rc = hub.receive("t", msg.message_id, _structured(FOLD.format(n=89, tail="h1.1")), agent_id="history-specialist", report_id="r1")
    finally:
        hub.close()
    assert reply is not None and "INT-REQ-013" in {f.code for f in rc.findings}, [(f.code, f.message[:120]) for f in rc.findings]


# --------------------------------------------------------------------------- the 'by' gap of a framed check (critical: per name)


def _gap_sentences(rng: random.Random) -> str:
    pieces = ["The History report", " this answer", " my essay", " holds", " was confirmed", " was checked", " by", " By", " the overseer", " Z3",
              " formally verified", " the translator's", "  ", "\t", "\n", ",", ".", " and", " the engine", " according to", " that"]
    return "".join(rng.choice(pieces) for _ in range(rng.randint(1, 14)))


def test_the_by_gap_read_once_per_outcome_is_the_fullmatch_it_replaces():
    rng = random.Random(11)
    for _ in range(6000):
        s = _gap_sentences(rng)
        outcomes = [m.span() for m in B._CHECK_OUTCOME_RE.finditer(s)]
        for f in B._FRAMED_CHECK_RE.finditer(s):
            assert not s[f.start()].isspace()  # a name starts with a letter: the premise of the rewrite
            for _a, o_end in outcomes:
                if o_end > f.start():
                    continue
                gap = B._BY_GAP_RE.match(s, o_end)
                assert (B._BY_GAP_RE.fullmatch(s, o_end, f.start()) is not None) == (gap is not None and gap.end() == f.start()), (s, o_end, f.span())


def test_a_long_blank_run_after_an_outcome_is_read_once_whatever_names_follow():
    make = lambda n: "The History report holds " + "\t" * (n // 2) + "Z3 " * (n // 6) + "."  # noqa: E731
    ratio, small, large = growth(check_result_statement, make(20000), make(80000), clear=empty_caches)
    assert large < 0.5 and ratio < 8, (ratio, small, large)  # 0.34 s at 40,000 and 1.47 s at 80,000 characters before the gate


@pytest.mark.parametrize("sentence,name", [("This answer was confirmed by the overseer.", "the overseer"), ("This answer was confirmed by Z3.", "Z3"),
                                           ("This answer was confirmed" + " " * 300 + "by" + "\t" * 50 + "the overseer.", "the overseer"),
                                           ("The History report holds by Z3", "Z3"), ("This answer was confirmed by the overseer, and Z3 Z3 Z3.", "the overseer")])
def test_control_a_report_checked_by_a_name_is_still_a_check_result(sentence, name):
    assert check_result_statement(sentence) == name


@pytest.mark.parametrize("sentence", ["This answer was confirmed. By the overseer's standards it is long.", "The overseer of the mill confirmed the shift."])
def test_control_a_name_that_checks_no_report_by_the_gap_is_no_check_result(sentence):
    assert check_result_statement(sentence) is None


# --------------------------------------------------------------------------- the premise value (bounded quadratic, deferred: fixed)


def _random_label(rng: random.Random) -> str:
    pieces = ["x", "before", "after_1", "1,500", " in 1840", "=", " = ", "  ", "\t", "\n", " ", " ", "(stated in sentence 3 of the paragraph)",
              " (stated in sentence 12 of the paragraph)", "(stated in sentence", " of the paragraph)", "(", ")", "é", "January 1923", "5", "Δv", "_",
              "-", "\r", "x" * 41, "a b c"]
    return "".join(rng.choice(pieces) for _ in range(rng.randint(0, 7))).strip()


def test_the_premise_value_is_the_reference_reading():
    rng = random.Random(5)
    for _ in range(50000):
        label = _random_label(rng)
        m = B._PREMISE_VALUE_RE.match(label)
        assert premise_value(label) == (m.group("v") if m else None), label
    for shape in SHAPES:  # the hostile inputs at the IR's bound on a label
        label = INPUTS[shape][:1000].strip()
        m = B._PREMISE_VALUE_RE.match(label)
        assert premise_value(label) == (m.group("v") if m else None), shape


def test_the_premise_value_is_read_in_linear_time():
    ratio, small, large = growth(premise_value, "a" + " " * 20000 + "b", "a" + " " * 80000 + "b")
    assert large < 0.05 and ratio < 8, (ratio, small, large)  # the reference: 1.4 ms at 1,000, 385 ms at 16,000 characters


# --------------------------------------------------------------------------- the module sweep (standard hostile inputs)


def _bus_entries(text: str):
    yield "premise_value", lambda: premise_value(text.strip())
    yield "premise_value(named)", lambda: premise_value(("v = " + text).strip())
    yield "_FOLDED_TAIL_RE", lambda: B._FOLDED_TAIL_RE.search(text)
    yield "ledger _FOLDED_TAIL_RE", lambda: L._FOLDED_TAIL_RE.search(text)
    yield "check_result_statement(after an outcome)", lambda: check_result_statement("The History report holds " + text + " Z3 Z3 Z3.")
    yield "check_result_statement(names after an outcome)", lambda: check_result_statement("The History report holds " + text + " Z3" * 2000)
    yield "needs_qualified_ids", lambda: B.needs_qualified_ids(HistorySpecialistAdapter(), SpecialistReport.model_validate(_structured(text)), {"h1.1"})


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_channel_readers_the_handoff_changed(shape):
    assert not sweep(_bus_entries, texts=one(shape))


# --------------------------------------------------------------------------- the counterexample note of a joined STEM problem


def _physics_hub(answer: str, auditor=None):
    """The answer through a hub with ``auditor`` attached (none: no overseer); the receipt and the task's audit (None
    without an auditor)."""
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=auditor)
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist"]))
        m = hub.dispatch("t", "physics-specialist", "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.")[0]
        _reply, rc = hub.receive("t", m.message_id, answer, agent_id="physics-specialist", report_id="r1")
        return rc, (hub.audit("t") if auditor is not None else None)
    finally:
        hub.close()


def _physics(answer: str):
    """The answer through a hub the overseer audits (skipped where the overseer is not installed)."""
    return _physics_hub(answer, make_auditor())


def test_a_failed_middle_dot_check_gives_the_engines_values_per_reading():
    rc, audit = _physics("a = 20/4 = 6·0 m s⁻².")
    err = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert len(err) == 1, [(f.code, f.message[:120]) for f in rc.findings]
    assert "(engine counterexample: decimal-point reading: c = 5, r = 6; product reading: c = 5, r = 0; under each reading of the middle dot" in err[0].message
    warn = [f for f in rc.findings if f.code == "INT-SUBJ-004"]
    assert warn and "decimal-point reading: c = 5, r = 6" in warn[0].message
    assert getattr(audit.state, "value", audit.state) in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")
    assert "OVS-RCPT-007" not in {f.code for f in audit.report.findings}  # the overseer binds the channel's own note


def test_control_a_check_of_one_reading_keeps_its_note():
    rc, audit = _physics("a = (20 - 0)/4.0 = 6.0 m s⁻².")
    err = next(f for f in rc.findings if f.code == "INT-SUBJ-001")
    assert "(engine counterexample: c = 5, r = 6; c is the value computed from the written expression, r the stated value)" in err.message
    assert getattr(audit.state, "value", audit.state) in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")


def test_a_failed_middle_dot_check_gives_the_engines_values_per_reading_with_no_overseer_attached():
    """The receipt's half of the two tests above, which needs no overseer: it runs where the overseer is not installed."""
    rc, audit = _physics_hub("a = 20/4 = 6·0 m s⁻².")
    assert audit is None
    err = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert len(err) == 1, [(f.code, f.message[:120]) for f in rc.findings]
    assert "(engine counterexample: decimal-point reading: c = 5, r = 6; product reading: c = 5, r = 0; under each reading of the middle dot" in err[0].message
    warn = [f for f in rc.findings if f.code == "INT-SUBJ-004"]
    assert warn and "decimal-point reading: c = 5, r = 6" in warn[0].message
    rc, _audit = _physics_hub("a = (20 - 0)/4.0 = 6.0 m s⁻².")
    err = next(f for f in rc.findings if f.code == "INT-SUBJ-001")
    assert "(engine counterexample: c = 5, r = 6; c is the value computed from the written expression, r the stated value)" in err.message
