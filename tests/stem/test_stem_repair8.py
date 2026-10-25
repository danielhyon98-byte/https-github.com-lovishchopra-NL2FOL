"""STEM repair 8: the eighth independent test of the STEM completion found four classes the front end did not decide as the pack says.
Each is fixed at its cause in the STEM front end, for its whole class, and every new reading has a clean control (correct working is
never flagged):

* rule ``value-at`` for a computing chain, rules ``name-list`` and ``item-label``: a value the run computes under a condition ('Mean time
  at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s', 'Rate at 20.0 °C = 1/61.7 s = 0.0162 s⁻¹', 'I at t = 5 s = 12 V / 4.5 Ω = 2.7 A',
  'The corrected rate at t = 40 h = …', 'Uptake at 30 °C = 2 × 40 = 80', 'Speed after 2.0 s = …'), after a list or a range the prose
  names it by ('Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3', 'The rise from 20.0 °C to 30.0 °C = 30.0 − 20.0 = 10.0 K') or for a
  numbered item ('Rate for trial 2 = …', 'Year 2 = …') read the condition's, the list's last or the item's number as the left side of a
  relation and failed (INT-SUBJ-001 on correct working, most with ST-DIM-001). The run is the named quantity's value now; rule
  ``condition-value`` sets the value of the condition's dimension the computation takes against the condition, and rule name-list's
  check a term of a sum of listed values against the list, both at warning severity;
* rule ``table-terms``: a number the working takes beside a supplied table's values that is no cell ('t = 12 h: 568 − 20 = 548 ± 11', the
  12 h row states 586; a background of 25 where the supplied text states 20) was neither checked nor named; the one unaccounted term
  of a line naming one row is set against that row's cell, a term added to or taken from the table's quantity against the value the
  request and its supplied texts state outside the table, at warning severity, every digit counting;
* rule ``law-values``: a law stated right before a line that evaluates it in another shape ('V = ε + Ir' then 'V = 12 V − (4.14 A ×
  0.50 Ω) = 9.9 V') was named by nothing; the law at the values the line puts in (paired with its symbols by their dimensions) is set
  against the line's value at warning severity, and a failed substitution names the law it evaluates ('P = V/R');
* rule ``inline-restatement`` with up to three describing words between the chain's value and ', so' ('= 60.4% decrease, so 61% to 2
  s.f.') was not read; it is a restatement of the chain's value now.
"""
from __future__ import annotations

import re

import pytest

from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.relations import _list_values, _name_head, _orders

from .test_stem_repair5 import CFG, PROFILE, SPEC, _data, clean, decide, failing, holds, new, replaced, task, warnings

#: anchors in the recorded r7 answers
CH_R = "Two reminders."
PH_E = "from 9.9 V to 10.7 V."
PH_D = "= 16.4 W, so 16 W"
PB_D = "32 h is 4 half-lives, so C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹."
BI_END = "which makes ATP. [1 spare]"
MI_END = "Next step: rework (a)"
PH_VC = "(c) [1]\nV = ε − Ir"
PH_PC = PH_VC + "\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
ES_A = "= 60.4% decrease [1]"
MI_R = "$= 4788$ euros, to the nearest euro (A1)"
PB_LINE = {k: f"t = {k} h: {c} − 20 = {c - 20} ± {u} counts min⁻¹" for k, c, u in ((4, 1151, 23), (12, 586, 12), (20, 303, 6), (24, 220, 4))}


def _quoting(checks, text: str) -> list:
    """The checks whose statement quotes ``text``."""
    return [c for c in checks if f"'{text}" in c[3].split(" [claims")[0]]


def _rule(checks, rule: str) -> list:
    return [c for c in checks if f"(rule {rule})" in c[3]]


def _ins(tid: str, anchor: str, line: str, *, before: bool = False) -> str:
    return replaced(tid, anchor, line + "\n\n" + anchor if before else anchor + "\n" + line)


def _planned(tid: str, text: str) -> list[tuple[str, str, str, str, tuple[str, ...]]]:
    """(kind, status, severity, statement, related statement ids) of every check the front end plans for ``text`` in task ``tid``."""
    clear_document_cache()
    data = _data(tid)
    doc = build_document(text, SPEC[tid]["question"], PROFILE[tid], **({"data": data} if data else {}))
    plan = build_checks(doc, report_id="r", request_id="q")
    return [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy)).status.value,
             pc.failure_severity, pc.description, tuple(pc.related_ids)) for pc in plan.checks]


# ============================================================================================ rule value-at for a computing chain
#: (the tester's line or a shape of its class, profile, the condition or value the run had been read to start with, the computation)
VALUE_AT_CONTROLS = [
    ("Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s.", "chemistry", "30.0 °C =", "(33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s"),
    ("Rate at 20.0 °C = 1/61.7 s = 0.0162 s⁻¹.", "chemistry", "20.0 °C =", "1/61.7 s = 0.0162 s⁻¹"),
    ("The current at t = 5 s = 12 V / 4.0 Ω = 3.0 A.", "physics", "5 s =", "12 V / 4.0 Ω = 3.0 A"),
    ("I at t = 5 s = 12 V / 4.5 Ω = 2.7 A", "physics", "5 s =", "12 V / 4.5 Ω = 2.7 A"),
    ("Speed after 2.0 s = 9.8 m s⁻² × 2.0 s = 19.6 m s⁻¹", "physics", "2.0 s =", "9.8 m s⁻² × 2.0 s = 19.6 m s⁻¹"),
    ("Uptake at 30 °C = 2 × 40 = 80", "biology", "30 °C =", "2 × 40 = 80"),
    ("The corrected rate at t = 40 h = 1600 counts min⁻¹ × (1/2)⁵ = 50 counts min⁻¹.", "physics", "40 h =", "1600 counts min⁻¹ × (1/2)⁵ = 50 counts min⁻¹"),
    ("The corrected rate when t = 16 h = 1600 counts min⁻¹ × (1/2)² = 400 counts min⁻¹.", "physics", "16 h =", "1600 counts min⁻¹ × (1/2)² = 400 counts min⁻¹"),
    ("The energy dissipated in 10 s = 16.4 W × 10 s = 164 J.", "physics", "10 s =", "16.4 W × 10 s = 164 J"),
    ("The charge that flows after 2.0 s = 4.1 A × 2.0 s = 8.2 C.", "physics", "2.0 s =", "4.1 A × 2.0 s = 8.2 C"),
    ("The mean time at 20.0 °C = (62.4 + 60.8 + 61.9) ÷ 3 = 61.7 s.", "chemistry", "20.0 °C =", "(62.4 + 60.8 + 61.9) ÷ 3 = 61.7 s"),
    # rules name-list and item-label
    ("Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3", "biology", "40 =", "(18 + 27 + 40) ÷ 3 = 28.3"),
    ("Difference between 40 and 80 = 80 − 40 = 40", "biology", "80 =", "80 − 40 = 40"),
    ("The rise from 20.0 °C to 30.0 °C = 30.0 − 20.0 = 10.0 K.", "chemistry", "30.0 °C =", "30.0 − 20.0 = 10.0 K"),
    ("Rate for trial 2 = 1/60.8 s = 0.0164 s⁻¹.", "chemistry", "2 =", "1/60.8 s = 0.0164 s⁻¹"),
    ("Year 2 = 4000 × 1.036² = 4293.18 euros", "mathematics_ai", "2 =", "4000 × 1.036² = 4293.18"),
]


@pytest.mark.parametrize("text,profile,side,computation", VALUE_AT_CONTROLS)
def test_a_value_computed_under_a_condition_or_named_by_a_list_is_no_relation(text, profile, side, computation):
    """Before, each line had a failing check '<condition> = <computation>' (INT-SUBJ-001 on correct working; with ST-DIM-001 where the
    condition has a unit of another dimension). Now nothing fails or warns, no check takes the condition (or the list's last value, or the
    item's number) as a side, and the computation's own arithmetic is checked and holds."""
    checks, findings = decide(text, None, profile)
    assert not failing(checks) and not warnings(findings), (failing(checks), warnings(findings))
    assert not _quoting(checks, side), checks
    arithmetic = [c for c in _quoting(checks, computation) if c[0] == "eq"]
    assert len(arithmetic) == 1 and holds(arithmetic[0]), checks


def test_the_tester_s_colon_form_reads_as_before():
    checks, findings = decide("Mean of 18, 27 and 40: (18 + 27 + 40) ÷ 3 = 28.3", None, "biology")
    assert [(c[0], c[1]) for c in checks] == [("eq", "ENTAILED")] and not warnings(findings)


#: (task, anchor, plant, its control, the computation the slip is in): in the recorded answers, each slip named on its computation
VALUE_AT_SLIPS = [
    ("ch-t13", CH_R, "Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 32.2 s.", "Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s.",
     "(33.1 s + 34.0 s + 32.5 s) ÷ 3 = 32.2 s"),
    ("ch-t13", CH_R, "Rate at 20.0 °C = 1/61.7 s = 0.162 s⁻¹.", "Rate at 20.0 °C = 1/61.7 s = 0.0162 s⁻¹.", "1/61.7 s = 0.162 s⁻¹"),
    ("ch-t13", CH_R, "Rate for trial 2 = 1/60.8 s = 0.164 s⁻¹.", "Rate for trial 2 = 1/60.8 s = 0.0164 s⁻¹.", "1/60.8 s = 0.164 s⁻¹"),
    ("bi-t13", BI_END, "Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 29.3", "Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3", "(18 + 27 + 40) ÷ 3 = 29.3"),
    ("bi-t13", BI_END, "Uptake at 30 °C = 2 × 40 = 90", "Uptake at 30 °C = 2 × 40 = 80", "2 × 40 = 90"),
    ("ph-t13", PH_E, "The current at t = 5 s is unchanged: I at t = 5 s = 12 V / 4.5 Ω = 3.7 A.",
     "The current at t = 5 s is unchanged: I at t = 5 s = 12 V / 4.5 Ω = 2.7 A.", "12 V / 4.5 Ω = 3.7 A"),
    ("ph-p7b", PB_D, "The corrected rate at t = 40 h = 1600 counts min⁻¹ × (1/2)⁵ = 60 counts min⁻¹.",
     "The corrected rate at t = 40 h = 1600 counts min⁻¹ × (1/2)⁵ = 50 counts min⁻¹.", "1600 counts min⁻¹ × (1/2)⁵ = 60 counts min⁻¹"),
    ("mai-t13", MI_END, "Year 2 = 4000 × 1.036² = 4393.18 euros", "Year 2 = 4000 × 1.036² = 4293.18 euros", "4000 × 1.036² = 4393.18"),
]


@pytest.mark.parametrize("tid,anchor,plant,control,computation", VALUE_AT_SLIPS)
def test_a_slip_in_the_computation_is_still_named_on_the_computation(tid, anchor, plant, control, computation):
    before = anchor in (CH_R, MI_END)
    checks, _f = new(tid, _ins(tid, anchor, plant, before=before))
    bad = failing(checks)
    assert len(bad) == 1 and bad[0][0] == "eq" and bad[0][2] == "error" and _quoting(bad, computation), checks
    clean(tid, _ins(tid, anchor, control, before=before))


def test_a_value_stated_for_a_numbered_item_is_no_relation():
    """'Time for trial 2 = 60.8 s.' had failed as '2 = 60.8 s'; the trial's number names the item: nothing is checked or flagged."""
    checks, findings = decide("Time for trial 2 = 60.8 s.", None, "chemistry")
    assert checks == [] and not warnings(findings), (checks, findings)
    clean("ch-t13", _ins("ch-t13", CH_R, "Time for trial 2 = 60.8 s.", before=True))


def test_a_conversion_of_the_condition_reads_as_before():
    """A run that converts the condition itself ('at 25 °C = 298 K') stays a conversion: the condition and the value are of one kind."""
    checks, _f = decide("The rate constant at 25 °C = 298 K is 0.040 s⁻¹.", None, "chemistry")
    assert [c[0] for c in checks] == ["cnv"] and all(holds(c) for c in checks) and "'25 °C = 298 K'" in checks[0][3], checks


# ============================================================================================ rule condition-value
#: (task, anchor, the line with another value of the condition's dimension put in, its control, the value set against the condition)
CONDITION_VALUE = [
    ("ph-t13", PH_E, "The charge that flows after 2.0 s = 4.1 A × 3.0 s = 12.3 C.", "The charge that flows after 2.0 s = 4.1 A × 2.0 s = 8.2 C.", "3.0 s"),
    ("ph-t13", PH_D, "The energy dissipated in 10 s = 16.4 W × 20 s = 328 J.", "The energy dissipated in 10 s = 16.4 W × 10 s = 164 J.", "20 s"),
    ("ph-t13", PH_E, "Speed after 2.0 s = 9.8 m s⁻² × 2.5 s = 24.5 m s⁻¹", "Speed after 2.0 s = 9.8 m s⁻² × 2.0 s = 19.6 m s⁻¹", "2.5 s"),
]


@pytest.mark.parametrize("tid,anchor,plant,control,value", CONDITION_VALUE)
def test_the_value_of_the_condition_s_dimension_is_set_against_the_condition(tid, anchor, plant, control, value):
    """The value the computation takes of the condition's dimension stands for the condition: another value fails at warning severity
    (every digit counts: 20 s against 10 s); the right one holds; the arithmetic is checked as before."""
    checks, _f = new(tid, _ins(tid, anchor, plant))
    bad = failing(checks)
    assert len(bad) == 1 and bad[0][0] == "giv" and bad[0][2] == "warning" and _rule(bad, "condition-value") and _quoting(bad, value), checks
    ok, f = new(tid, _ins(tid, anchor, control))
    assert len(_rule(ok, "condition-value")) == 1 and not failing(ok) and not warnings(f), (ok, f)


@pytest.mark.parametrize("text,profile", [
    ("Uptake at 30 °C = 2 × 40 = 80", "biology"),                                  # a condition with no exact SI reading (affine °C)
    ("Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s.", "chemistry"),
    ("The speed after 3.0 s = 9.8 m s⁻² × (4.0 s − 1.0 s) = 29.4 m s⁻¹", "physics"),  # two values of the condition's dimension
    ("The corrected rate at t = 40 h = 1600 counts min⁻¹ × (1/2)⁵ = 50 counts min⁻¹.", "physics"),  # none
])
def test_no_condition_value_check_when_no_one_value_stands_for_the_condition(text, profile):
    checks, findings = decide(text, None, profile)
    assert not _rule(checks, "condition-value") and not failing(checks) and not warnings(findings), (checks, findings)


# ============================================================================================ rule name-list's check
@pytest.mark.parametrize("tid,anchor,plant,control,term", [
    ("bi-t13", BI_END, "Mean of 18, 27 and 40 = (18 + 27 + 41) ÷ 3 = 28.7", "Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3", "41"),
    ("ch-t13", CH_R, "The rise from 20.0 °C to 30.0 °C = 30.0 − 25.0 = 5.0 K.", "The rise from 20.0 °C to 30.0 °C = 30.0 − 20.0 = 10.0 K.", "25.0"),
    ("bi-t13", BI_END, "Difference between 40 and 80 = 80 − 45 = 35", "Difference between 40 and 80 = 80 − 40 = 40", "45"),
])
def test_a_term_that_is_no_listed_value_is_set_against_the_list(tid, anchor, plant, control, term):
    """The arithmetic is consistent, so before the plant was named by nothing (once its false INT-SUBJ-001 was gone); the term is set
    against the listed values at warning severity. A term that is a listed value has nothing to decide: the control plans no such check."""
    before = anchor == CH_R
    checks, _f = new(tid, _ins(tid, anchor, plant, before=before))
    bad = failing(checks)
    assert len(bad) == 1 and bad[0][0] == "giv" and bad[0][2] == "warning" and _rule(bad, "name-list") and _quoting(bad, term), checks
    ok, f = new(tid, _ins(tid, anchor, control, before=before))
    assert not _rule(ok, "name-list") and not failing(ok) and not warnings(f), (ok, f)


def test_the_list_s_values_and_the_name_s_words():
    assert [n.text for n in _list_values("Mean of 18, 27 and ")] == ["18", "27"]
    assert [n.text for n in _list_values("Mean of 18 mm³, 27 mm³ and ")] == ["18", "27"]
    assert [n.text for n in _list_values("The rise from 20.0 °C to ")] == ["20.0"]
    assert _list_values("Mean time at ") == () and _list_values("from −5 to ") == ()
    assert _name_head("Mean of 18, 27 and ") == ["mean"] and _name_head("Difference between 40 and ") == ["difference"]
    assert _name_head("Time for trial ") == ["time", "trial"] and _name_head("The rise from 20.0 °C to ") == ["rise"]
    assert len(_orders([1, 2, 3])) == 6 and _orders([]) == [[]] and len({tuple(o) for o in _orders([1, 2, 3, 4, 5])}) == 120


def test_a_list_with_no_computation_after_it_reads_as_before():
    """'… 18, 27 and 40 = 28.3' (a value, no written expression) stays what it was: no rule of this repair reads it."""
    for text in ("Mean of 18, 27 and 40 = 28.3", "Mean of 18, 27 and 40 = 28.3 mm³"):
        new_checks, _ = decide(text, None, "biology")
        old = [c for c in new_checks if "rule name-list" in c[3] or "rule item-label" in c[3]]
        assert not old, new_checks


# ============================================================================================ rule table-terms
#: (the line of the recorded p7b answer, the plant, the term set against the table)
TABLE_TERMS = [
    (PB_LINE[12], "t = 12 h: 568 − 20 = 548 ± 11 counts min⁻¹", "568"),
    (PB_LINE[4], "t = 4 h: 1115 − 20 = 1095 ± 22 counts min⁻¹", "1115"),
    (PB_LINE[20], "t = 20 h: 330 − 20 = 310 ± 7 counts min⁻¹", "330"),
    (PB_LINE[24], "t = 24 h: 220 − 25 = 195 ± 4 counts min⁻¹", "25"),
    (PB_LINE[12], "t = 12 h: 586 counts min⁻¹ − 25 counts min⁻¹ = 561 counts min⁻¹", "25 counts"),
    (PB_LINE[12], "The corrected rate at t = 12 h = 568 − 20 = 548 counts min⁻¹", "568"),
]


@pytest.mark.parametrize("old,plant,term", TABLE_TERMS)
def test_a_value_copied_wrongly_from_the_table_or_a_wrong_background_is_named(old, plant, term):
    """The tester's four plants (568 for 586, 1115 for 1151, 330 for 303, a background of 25 for the 20 the supplied text and the answer
    state) and their shapes: before, each line's arithmetic held and nothing named the wrong value; now the term is set against the row's
    cell or the stated background, at warning severity, and fails."""
    checks, _f = new("ph-p7b", replaced("ph-p7b", old, plant))
    bad = [c for c in failing(checks) if c[0] == "giv"]
    assert len(bad) == 1 and bad[0][2] == "warning" and _rule(bad, "table-terms") and _quoting(bad, term), checks
    assert not [c for c in failing(checks) if c[2] == "error"], failing(checks)


@pytest.mark.parametrize("old,control", [
    (PB_LINE[24], "t = 24 h: 220 − 20.0 = 200 ± 4 counts min⁻¹"),
    (PB_LINE[12], "t = 12 h: 586 counts min⁻¹ − 20 counts min⁻¹ = 566 counts min⁻¹"),
    (PB_LINE[12], "The corrected rate at t = 12 h = 586 − 20 = 566 counts min⁻¹"),
    (PB_LINE[12], PB_LINE[12] + " (upper bound 586 + 11.72 = 597.72 counts min⁻¹)"),
    (PB_LINE[12], "t = 12 h: 566 + 20 = 586 counts min⁻¹"),
])
def test_the_right_values_of_the_table_are_never_flagged(old, control):
    clean("ph-p7b", replaced("ph-p7b", old, control))


def test_the_rows_are_set_against_their_own_cells_in_the_other_tasks():
    """ESS's site C (3.9 for 3.8) and biology's 20 °C row (41 for 40), each with consistent arithmetic, are named the same way."""
    checks, _f = new("ess-t13", replaced("ess-t13", "(a) Percentage decrease = (9.6 − 3.8) ÷ 9.6 × 100\n= 60.4% decrease [1]",
                                         "(a) Percentage decrease = (9.6 − 3.9) ÷ 9.6 × 100\n= 59.4% decrease [1]"))
    assert [c[2] for c in failing(checks)] == ["warning"] and _rule(failing(checks), "table-terms"), checks
    checks, _f = new("bi-t13", replaced("bi-t13", "(80 − 40) ÷ 40 × 100 = 100%, an increase of 100%", "(80 − 41) ÷ 41 × 100 = 95%, an increase of 95%"))
    assert _rule([c for c in failing(checks) if c[2] == "warning"], "table-terms"), checks


def test_a_background_stated_wrongly_in_prose_is_named_every_digit_counting():
    """'the background count rate of 25 counts min⁻¹' against the supplied 20: before, it held by the half-width of 20's trailing zero."""
    old = "the background of 20 counts min⁻¹ is constant"
    checks, f = new("ph-p7b", replaced("ph-p7b", old, "the background count rate of 25 counts min⁻¹ is constant"))
    assert [c[2] for c in failing(checks)] == ["warning"] and _quoting(failing(checks), "25 counts"), (checks, f)
    clean("ph-p7b", replaced("ph-p7b", old, "the background count rate of 20 counts min⁻¹ is constant"))


# ============================================================================================ rule law-values
#: (the recorded working, the plant, the evaluation the law is set against, whether the plant changes the line's value)
LAW_PLANTS = [
    (PH_VC, "(c) [1]\nV = ε + Ir", "12 V − (4.14 A × 0.50 Ω) = 9.9 V", False),
    (PH_PC, "(c) [1]\nV = ε − Ir\nV = 12 V + (4.14 A × 0.50 Ω) = 14.1 V", "12 V + (4.14 A × 0.50 Ω) = 14.1 V", True),
    (PH_PC, "(c) [1]\nV = ε + Ir = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "12 V − (4.14 A × 0.50 Ω) = 9.9 V", False),
    (PH_PC, "(c) [1]\nV = ε + Ir, so V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "12 V − (4.14 A × 0.50 Ω) = 9.9 V", False),
    (PH_PC, "(c) [1]\nUsing V = ε + Ir:\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "12 V − (4.14 A × 0.50 Ω) = 9.9 V", False),
]


@pytest.mark.parametrize("old,plant,evaluation,changes_value", LAW_PLANTS)
def test_a_law_its_evaluation_does_not_follow_is_named(old, plant, evaluation, changes_value):
    """The tester's 'V = ε + Ir' then '… = 9.9 V' was named by nothing (the line's arithmetic holds, ε has no stated value so no
    substitution is checked); the law at the line's values (ε = 12 V, I = 4.14 A, r = 0.50 Ω, paired by dimension) is set against the
    line's value and fails at warning severity, its statement naming the law's statement and the line's. A plant that changes the line's
    value (14.1 V) also fails what part (d) and the prose take from it, as before."""
    planned = _planned("ph-t13", replaced("ph-t13", old, plant))
    law = [c for c in planned if "(rule law-values)" in c[3]]
    assert len(law) == 1 and not holds(law[0]) and law[0][2] == "warning", planned
    m = re.match(r"the law stated in (s[\d.]+) at the values the line puts in: '([^']*)'", law[0][3])
    assert m is not None and m.group(2).endswith(evaluation), law[0][3]
    assert "the law V = " in law[0][3] and "(ε = 12 [V], I = 4.14 [A], r = 0.50 [Ω])" in law[0][3], law[0][3]
    assert [c[1] for c in _quoting(planned, evaluation) if c[0] == "eq" and "rule law-values" not in c[3]] == ["ENTAILED"], planned
    if not changes_value:
        assert [c for c in planned if not holds(c)] == law, [c for c in planned if not holds(c)]


@pytest.mark.parametrize("old,control", [
    (PH_VC, "(c) [1]\nV = ε − rI"),
    (PH_PC, "(c) [1]\nV = ε − Ir = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"),
    (PH_PC, "(c) [1]\nV = ε − Ir, so V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"),
    (PH_PC, "(c) [1]\nUsing V = ε − Ir:\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"),
])
def test_the_law_the_line_evaluates_holds(old, control):
    """The right law, in each form: the line is its substitution (checked against the stated bindings, holding), or, with the product
    written the other way round, a substitution introducing its values, as before; no law-values check fails and nothing new is flagged."""
    planned = _planned("ph-t13", replaced("ph-t13", old, control))
    assert not [c for c in planned if "(rule law-values)" in c[3] and not holds(c)], planned
    if "rI" not in control:
        assert [c[1] for c in planned if c[0] == "sub" and "12 V − (4.14 A × 0.50 Ω)'" in c[3].split(" [claims")[0]] == ["ENTAILED"], planned
    clean("ph-t13", replaced("ph-t13", old, control))


@pytest.mark.parametrize("old,control", [
    (PH_PC, "(c) [1]\nV = ε − Ir\nV = 12 V − 2.07 V = 9.93 V"),                   # the lost volts computed first: two values, three symbols
    ("P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W", "P = V²/R\nP = 9.93 V × 1.655 A = 16.4 W"),  # another law (P = VI) evaluated
])
def test_a_line_that_does_not_put_one_value_in_for_each_symbol_is_not_paired(old, control):
    """No pairing is read when the line's values do not stand one for each symbol, and a line that takes a value of a dimension no symbol of
    the formula has evaluates another relation (before, 'P = 9.93 V × 1.655 A' was set against V²/R under the stated values and failed)."""
    planned = _planned("ph-t13", replaced("ph-t13", old, control))
    assert not [c for c in planned if "(rule law-values)" in c[3]] and all(holds(c) for c in planned), planned
    clean("ph-t13", replaced("ph-t13", old, control))


def test_a_failed_substitution_names_the_law_it_evaluates():
    """'P = V/R' then 'P = (9.93 V)² / 6.0 Ω = 16.4 W': the substitution fails as before, and its related statements now name the law's
    statement first (before: only part (c)'s V), so the failure finding names the claim that states the wrong law. 'P = V²/(2R)' was
    named before (the formula under the stated values, its claims the law's statement and the line's) and still is."""
    planned = _planned("ph-t13", replaced("ph-t13", "P = V²/R\nP = (9.93 V)²", "P = V/R\nP = (9.93 V)²"))
    bad = [c for c in planned if not holds(c)]
    assert len(bad) == 1 and bad[0][0] == "sub" and bad[0][2] == "error", bad
    m = re.search(r"the formula of 'P' stated in (s[\d.]+)", bad[0][3])
    assert m is not None and bad[0][4][0] == m.group(1), bad[0]
    planned = _planned("ph-t13", replaced("ph-t13", "P = V²/R\nP = (9.93 V)²", "P = V²/(2R)\nP = (9.93 V)²"))
    bad = [c for c in planned if not holds(c)]
    assert len(bad) == 1 and bad[0][0] == "sub" and bad[0][2] == "error" and bad[0][3].split(" [claims ")[1].startswith(m.group(1) + ","), bad


# ============================================================================================ rule inline-restatement with words
@pytest.mark.parametrize("tid,old,plant,control,value", [
    ("ess-t13", ES_A, "= 60.4% decrease, so 61% to 2 s.f. [1]", "= 60.4% decrease, so 60% to 2 s.f. [1]", "61%"),
    ("ess-t13", ES_A, "= 60.4% decrease, which is 61% to 2 s.f. [1]", "= 60.4% decrease, which is 60% to 2 s.f. [1]", "61%"),
    ("mai-t13", MI_R, "$= 4787.58$ euros, so 4787 euros to the nearest euro (A1)", "$= 4787.58$ euros, so 4788 euros to the nearest euro (A1)",
     "4787"),
    ("ph-t13", "(4.14 A × 0.50 Ω) = 9.9 V", "(4.14 A × 0.50 Ω) = 9.93 V across the resistors, so 9.8 V to 2 s.f.",
     "(4.14 A × 0.50 Ω) = 9.93 V across the resistors, so 9.9 V to 2 s.f.", "9.8 V"),
])
def test_a_restatement_after_describing_words_and_so_is_read(tid, old, plant, control, value):
    """Before, a word between the chain's value and ', so' left the restatement unread (the wrong rounding named by nothing); it is set
    against the chain's value now and fails (INT-SUBJ-001); the right rounding holds."""
    checks, _f = new(tid, replaced(tid, old, plant))
    bad = failing(checks)
    assert bad and all(c[0] == "res" for c in bad) and _quoting(bad, value) and any(c[2] == "error" for c in bad), checks
    ok, f = new(tid, replaced(tid, old, control))
    assert [c for c in ok if c[0] == "res"] and not failing(ok) and not warnings(f), (ok, f)


@pytest.mark.parametrize("text", [
    "The voltage is 9.93 V, so the bulb lights.",                 # no number after ', so'
    "V = 9.93 V and so on, so 3 cells are needed.",               # more than three words between
])
def test_what_is_no_restatement_reads_as_before(text):
    checks, _f = decide(text, None, "physics")
    assert not [c for c in checks if c[0] == "res"], checks


# ============================================================================================ the recorded answers
def test_no_recorded_round_7_answer_gets_a_reading_of_this_repair():
    """The recorded STEM answers compute no value under a condition, after a list or for a numbered item; take no value beside a table's
    that no cell gives; state no law evaluated in another shape: none of their checks names a rule of this repair (the front end's dump of
    them, and of the STEM corpus, is byte for byte as before)."""
    for tid, spec in SPEC.items():
        if tid not in PROFILE:
            continue
        checks, _findings = task(tid, spec["response_text"])
        assert not [c for c in checks if any(f"(rule {r})" in c[3] for r in ("condition-value", "name-list", "item-label", "table-terms", "law-values"))], tid
