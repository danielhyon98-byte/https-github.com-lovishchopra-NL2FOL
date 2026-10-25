"""STEM repair 3: the third independent test of the STEM completion found a false error on correct work, an arithmetic slip
passed inside a stated uncertainty, and five fault forms the STEM front end did not read. Each is fixed at its cause in the
STEM front end, for its whole class, and every new reading has a clean control (correct working is never flagged):

* rule ``value-at``: '<quantity> at <condition> = <value>' ('Given: oxygen uptake at 30 °C = 80 mm³ per g per hour', 'the count
  rate at t = 8 h = 820 counts min⁻¹', 'time at 30.0 °C = 33.1 s') states the quantity's value under the condition; it was read
  as a unit conversion between the condition and the value and failed (INT-SUBJ-001 and ST-DIM-001 on correct work), and such
  a Given had neither its check nor its ST-UNDEC-003. Now a Given so stated is set against the supplied table's cell at the row
  the condition names (or named unchecked), a statement so written outside a Given likewise when the row and the column are
  read, and the condition binds nothing; 'at 25 °C = 298 K' stays a conversion;
* rule ``central-value``: a stated value with its uncertainty ('586 − 20 = 556 ± 12') is checked at its central value; the band
  had widened h, so a slip within the uncertainty passed;
* rule ``processed-data``: a line that takes a supplied table's raw cell where the answer processed it ('C = 1620 counts min⁻¹ ×
  (1/2)⁴' after '1620 − 20 = 1600 ± 32', in a part asking for the corrected rate) is set against the processed value;
* rule ``supplied-values`` with rule ``given-digits``: the values a supplied text states in prose are the request's too, for a
  Given whose name shares a word with their sentence ('Given: volume of thiosulfate = 40.0 cm³' against '50.0 cm3 of … sodium
  thiosulfate'), and a Given restates its data with every digit of a whole number counted (30 against 20 had held);
* units given only in the task or its table: a header unit written with ASCII exponents ('mm3 per g per hour') is read, a value
  with a unit 'per …' is read whole, a table value restated in another unit is compared in SI ('18 cm³ per g per hour'), and rule
  ``restated-unit`` sets a value with the task's number and another unit of that dimension against the task's quantity ('the
  background of 20 counts s⁻¹' for 20 counts per minute);
* rules ``percentage-change`` and ``half-lives``, and a stated rounding of a stated value ('R = 2.4 Ω (…), or 3 Ω to one
  significant figure'): a percentage change divided by the wrong value, a power of ½ that is not the number of half-lives the
  prose states, a time that is not that number of half-lives, and a wrong rounding to significant figures are named;
* a percentage is never read as the restatement of a quantity of a dimension ('… = 6.0 m. So the uncertainty is 2%');
* rule ``given-uncertainty``: a Given named or written as an uncertainty ('Given: thermometer uncertainty = 0.5 °C', 'Δθ = ±0.5 °C')
  is set against the uncertainties the request and its supplied texts state ('+/-0.5 °C', '+/-2%'), never against a value of its
  quantity (it had failed against the request's 20 °C and 60 °C, a false warning on a correct Given; a Given written with '±' had
  neither its check nor its ST code), or named unchecked; a Given written with its uncertainty ('T = 20.0 ± 0.5 °C') is set
  against the request at its central value (rule central-value).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.datatables import ascii_exponents, parse_data_tables

R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))
SPEC: dict[str, dict] = R7["specialists"]
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)


def _data(tid: str) -> tuple[str, ...]:
    return tuple(t["text"] for t in SPEC[tid].get("supplied_texts") or [])


def decided(text: str, profile: str = "physics", request: str = None, data: tuple = ()):
    """(checks as (kind, status, severity, form, description), findings as (code, message)) for ``text``, every check decided."""
    clear_document_cache()
    doc = build_document(text, request, profile, **({"data": data} if data else {}))
    plan = build_checks(doc, report_id="r", request_id="q")
    checks = [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy)).status.value,
               pc.failure_severity, pc.form, pc.description) for pc in plan.checks]
    return checks, [(f.code, f.message) for f in list(doc.findings) + list(plan.findings)]


def task(tid: str, text: str, profile: str):
    return decided(text, profile, request=SPEC[tid]["question"], data=_data(tid))


def with_line(tid: str, anchor: str, line: str) -> str:
    text = SPEC[tid]["response_text"]
    assert text.count(anchor) == 1, anchor
    return text.replace(anchor, line + "\n\n" + anchor)


def replaced(tid: str, old: str, new: str) -> str:
    text = SPEC[tid]["response_text"]
    assert text.count(old) == 1, old
    return text.replace(old, new)


def new_checks(tid: str, text: str, profile: str) -> tuple[list, list]:
    """The checks and findings ``text`` has beyond the recorded answer's (compared by kind, status, severity and statement head)."""
    def key(c):
        return (c[0], c[1], c[2], c[4].split(" [claims")[0])
    base_c, base_f = task(tid, SPEC[tid]["response_text"], profile)
    got_c, got_f = task(tid, text, profile)
    bc = [key(c) for c in base_c]
    out_c = []
    for c in got_c:
        if key(c) in bc:
            bc.remove(key(c))
        else:
            out_c.append(c)
    bf = [(c, m.split(" in s")[0]) for c, m in base_f]
    out_f = []
    for c, m in got_f:
        k = (c, m.split(" in s")[0])
        if k in bf:
            bf.remove(k)
        else:
            out_f.append((c, m))
    return out_c, out_f


# ============================================================================================ rule value-at
BI_GIVEN = "Given: oxygen uptake at 30 °C = {v} mm³ per g per hour."


@pytest.mark.parametrize("value, status", [("80", "ENTAILED"), ("85", "COUNTEREXAMPLE")])
def test_a_given_stated_under_a_condition_is_set_against_the_supplied_table_s_cell(value, status):
    """The independent test's false error: 'Given: oxygen uptake at 30 °C = 80 mm³ per g per hour.' was the unit conversion
    '30 °C = 80 mm³' (COUNTEREXAMPLE, INT-SUBJ-001) with ST-DIM-001, and had no stem_given check. It is the uptake's value at
    the row 30 °C of the supplied table: one stem_given check against that cell, at warning severity, which the table's 80 holds
    and 85 fails; no ST-DIM-001, no conversion."""
    checks, findings = new_checks("bi-t13", with_line("bi-t13", "Level not stated:", BI_GIVEN.format(v=value)), "biology")
    assert [(k, st, sev) for k, st, sev, _f, _d in checks] == [("giv", status, "warning")] and findings == [], (checks, findings)
    assert "Mean oxygen uptake at the supplied table's row 30 (80)" in checks[0][4] and "(rule table-data, rule value-at)" in checks[0][4]


@pytest.mark.parametrize("tid, line, profile, status", [
    ("ph-p7b", "Given: the count rate at t = 8 h = 820 counts min⁻¹.", "physics", "ENTAILED"),
    ("ph-p7b", "Given: the count rate at t = 8 h = 830 counts min⁻¹.", "physics", "COUNTEREXAMPLE"),
    ("ch-t13", "Given: time at 30.0 °C = 33.1 s.", "chemistry", "ENTAILED"),
    ("ch-t13", "Given: time at 30.0 °C = 36.1 s.", "chemistry", "COUNTEREXAMPLE"),
    ("ph-p7b", "Given: at t = 8 h, C = 820 counts min⁻¹.", "physics", "ENTAILED"),
    ("ph-p7b", "Given: at t = 8 h, C = 850 counts min⁻¹.", "physics", "COUNTEREXAMPLE"),
])
def test_every_phrasing_of_a_value_under_a_condition_is_read_so(tid, line, profile, status):
    """'the count rate at t = 8 h = 820 counts min⁻¹' had been '8 h = 820 counts min⁻¹' (INT-SUBJ-001), had bound t to the count
    rate and made '2%' a false restatement of it; 'time at 30.0 °C = 33.1 s' had been '30.0 °C = 33.1 s'; 'Given: at t = 8 h, C = …'
    had set the condition t = 8 h against the request's t = 32 h. Each is now the value under its condition: one stem_given check
    against the supplied table's row, and nothing else. A name that fits no single column (the three timed trials) takes the row's
    cells of every column of the value's dimension."""
    anchor = "(a) [2]" if tid == "ph-p7b" else "Two reminders."
    checks, findings = new_checks(tid, with_line(tid, anchor, line), profile)
    if line.startswith("Given: at t"):
        # the Given binds C, which (d) gives another value: the scope's info note says so (no warning, no check)
        assert [c for c, _m in findings] == ["ST-SCOPE-001"] and findings[0][1].startswith("'C' takes the value 100 counts min⁻¹ in s5.1"), findings
        findings = []
    assert [(k, st, sev) for k, st, sev, _f, _d in checks] == [("giv", status, "warning")] and findings == [], (checks, findings)
    if tid == "ch-t13":
        assert "one of its cells Time, trial 1 33.1, Time, trial 2 34.0, Time, trial 3 32.5" in checks[0][4]


@pytest.mark.parametrize("second, status", [("80", "ENTAILED"), ("88", "COUNTEREXAMPLE")])
def test_values_under_conditions_outside_a_given_are_set_against_their_rows(second, status):
    """'The uptake at 20 °C = 40 mm³ …, and at 30 °C = 80 mm³ …' had been two false conversions (two INT-SUBJ-001); each value is
    now set against its row (the second clause takes the first's name), at warning severity."""
    line = f"The uptake at 20 °C = 40 mm³ per g per hour, and at 30 °C = {second} mm³ per g per hour."
    checks, findings = new_checks("bi-t13", with_line("bi-t13", "Level not stated:", line), "biology")
    assert [(k, st) for k, st, *_ in checks] == [("giv", "ENTAILED"), ("giv", status)] and findings == []


def test_a_condition_value_of_the_same_kind_stays_a_conversion():
    """'at 25 °C = 298 K' converts the condition: the conversion is checked as before (and a wrong one fails)."""
    assert [(k, st) for k, st, *_ in decided("The rate at 25 °C = 298 K is measured.")[0]] == [("cnv", "ENTAILED")]
    assert [(k, st) for k, st, *_ in decided("The rate at 25 °C = 350 K is measured.")[0]] == [("cnv", "COUNTEREXAMPLE")]


def test_a_given_under_a_condition_with_no_table_is_named_unchecked():
    """Pack D31 and I98: a Given always has its check or its ST-UNDEC-003. With no supplied table the Given stated under its
    condition is named (before: no check and no ST code)."""
    checks, findings = decided(BI_GIVEN.format(v="80"), "biology", request=SPEC["bi-t13"]["question"])
    assert checks == [] and [c for c, _m in findings] == ["ST-UNDEC-003"] and "oxygen uptake = 80 mm³ per g per hour" in findings[0][1]


def test_the_condition_binds_nothing():
    """The condition t = 8 h of the Given binds no t, so the request's t = 32 h and the answer's own times keep their values."""
    clear_document_cache()
    doc = build_document("Given: the count rate at t = 8 h = 820 counts min⁻¹.", SPEC["ph-p7b"]["question"], "physics", data=_data("ph-p7b"))
    assert [b.source for b in doc.bindings.get("t", ())] == ["request"]
    [rel] = [r for r in doc.relations if r.kind == "label"]
    assert rel.outcome == "binding" and rel.condition_symbol == "t" and "(rule value-at)" in rel.reason


# ============================================================================================ rule central-value
@pytest.mark.parametrize("value, status", [("566", "ENTAILED"), ("556", "COUNTEREXAMPLE"), ("564", "COUNTEREXAMPLE"), ("546", "COUNTEREXAMPLE")])
def test_a_stated_uncertainty_never_widens_the_check_of_its_central_value(value, status):
    """'586 − 20 = 556 ± 12' held: the band ± 12 was added to h. The central value is checked under the tolerance rule; the
    uncertainty itself is not checked by it, and the statement says so. STEM repair 4 (rule operand-precision): 586 and 20 are
    exact as written, so their rounding cannot move 566 and τ is 0: 564, a slip of 2 that τ = 1/100 (5.66) had let pass, fails too."""
    checks, findings = decided(f"t = 12 h: 586 − 20 = {value} ± 12 counts min⁻¹", request="Q")
    [eq] = [c for c in checks if c[0] == "eq"]
    assert eq[1] == status and findings == []
    assert "the computed value is set against its central value" in eq[4] and "the uncertainty itself is not checked (rule central-value)" in eq[4]
    assert "τ = 0: twice the largest relative change the rounding of the written operands can make" in eq[4] and "(rule operand-precision)" in eq[4]


def test_the_recorded_corrected_rates_hold_at_their_central_values():
    checks, _findings = task("ph-p7b", SPEC["ph-p7b"]["response_text"], "physics")
    central = [c for c in checks if "(rule central-value)" in c[4]]
    assert len(central) == 7 and all(st == "ENTAILED" for _k, st, *_ in central)


# ============================================================================================ rule processed-data
P7B_D = "C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹"


def test_the_raw_cell_taken_where_the_answer_processed_it_is_named():
    """(d) asks for the corrected rate; '1620 counts min⁻¹ × (1/2)⁴' takes the measured cell that (a) corrected to 1600: a
    stem_given check of 1620 against 1600, at warning severity, naming both statements. The arithmetic itself still holds."""
    checks, findings = new_checks("ph-p7b", replaced("ph-p7b", P7B_D, "C = 1620 counts min⁻¹ × (1/2)⁴ = 101 counts min⁻¹"), "physics")
    giv = [c for c in checks if c[0] == "giv"]
    assert [(k, st, sev) for k, st, sev, _f, _d in giv] == [("giv", "COUNTEREXAMPLE", "warning")] and findings == []
    assert "processed into 1600 [counts min⁻¹] in s1.3; the part asks for the corrected value (rule processed-data)" in giv[0][4]
    assert "[claims s4.1, s1.3]" in giv[0][4]


def test_the_processed_value_and_a_part_that_names_no_processing_are_not_read():
    """Controls: the recorded (d) takes the corrected 1600 (nothing planned); the raw cell in the processing part itself (an
    uncertainty of the measured value) and in a part whose question names no processed quantity are other computations."""
    assert new_checks("ph-p7b", SPEC["ph-p7b"]["response_text"], "physics") == ([], [])
    same_part = replaced("ph-p7b", "t = 4 h: 1151 − 20 = 1131 ± 23 counts min⁻¹", "t = 4 h: 1151 − 20 = 1131 ± 23 counts min⁻¹\n2% of 1620 = 0.02 × 1620 = 32.4")
    assert [c for c in new_checks("ph-p7b", same_part, "physics")[0] if c[0] == "giv"] == []
    other = replaced("ph-p7b", "(e) [2]\n", "(e) [2]\nThe background is 20/1620 × 100 = 1.2% of the first reading.\n")
    assert [c for c in new_checks("ph-p7b", other, "physics")[0] if c[0] == "giv"] == []


@pytest.mark.parametrize("line", ["C₀ = 1620 − 20 = 1600 counts min⁻¹.", "The corrected initial rate is 1620 − 20 = 1600 counts min⁻¹.",
                                  "The background is 20/1620 × 100 = 1.2% of the first reading."])
def test_in_the_part_that_asks_for_the_processed_value_a_reprocessing_or_a_ratio_of_the_raw_cell_is_not_read(line):
    """Controls in (d) itself, whose question names the corrected rate: a line that corrects the raw cell again into the processed
    value substitutes nothing (its own arithmetic is checked, and holds), and a percentage of the raw cell is no value of the
    column's quantity. Both had been set against the processed 1600 and failed (a false warning on correct work)."""
    text = replaced("ph-p7b", "32 h is 4 half-lives, so", line + " 32 h is 4 half-lives, so")
    checks, findings = new_checks("ph-p7b", text, "physics")
    assert [(k, st) for k, st, *_ in checks] == [("eq", "ENTAILED")] and findings == [], (checks, findings)


# ============================================================================================ rules supplied-values and given-digits
@pytest.mark.parametrize("tid, line, profile, status", [
    ("ph-p7b", "Given: background count rate = 30 counts min⁻¹.", "physics", "COUNTEREXAMPLE"),
    ("ph-p7b", "Given: background count rate = 20 counts min⁻¹.", "physics", "ENTAILED"),
    ("ch-t13", "Given: volume of thiosulfate = 40.0 cm³.", "chemistry", "COUNTEREXAMPLE"),
    ("ch-t13", "Given: volume of thiosulfate = 50.0 cm³.", "chemistry", "ENTAILED"),
    ("ch-t13", "Given: volume of acid = 5.0 cm³.", "chemistry", "ENTAILED"),
])
def test_a_given_is_set_against_the_values_its_supplied_text_states(tid, line, profile, status):
    """A Given contradicting a value the supplied text states in prose got only ST-UNDEC-003, exactly as the correct Given did.
    The supplied text's values are the request's too (rule supplied-values), and a Given restates its data with every digit of a
    whole number counted (rule given-digits: 30 against 20 had held, each with h = 5)."""
    anchor = "(a) [2]" if tid == "ph-p7b" else "Two reminders."
    checks, findings = new_checks(tid, with_line(tid, anchor, line), profile)
    assert [(k, st, sev) for k, st, sev, _f, _d in checks] == [("giv", status, "warning")] and findings == [], (checks, findings)
    assert "(with those its supplied texts state: rule supplied-values)" in checks[0][4]
    assert "rule given-digits" in checks[0][4] or tid == "ch-t13"


def test_a_given_whose_name_the_supplied_text_does_not_write_is_not_set_against_it():
    """C0 = 1600 counts min⁻¹ is a corrected rate, no restatement of the supplied background: it is named unchecked, with why."""
    checks, findings = task("ph-p7b", "Given: C0 = 1600 counts min⁻¹.", "physics")
    assert checks == [] and [c for c, _m in findings] == ["ST-UNDEC-003"]
    assert "a supplied text states one, but in no sentence that holds a word of the Given's name" in findings[0][1]


def test_an_uncertainty_a_supplied_text_states_is_no_value():
    """'+/-0.5 °C', '+/-0.01 s' and '+/-2%' are uncertainties: no Given is set against them."""
    clear_document_cache()
    doc = build_document("x", SPEC["ch-t13"]["question"], "chemistry", data=_data("ch-t13"))
    shown = sorted(f"{n.number.text} {n.unit.text}" for n, _a, _b, _w in doc.request.supplied_quantities)
    assert shown == ["0.10 mol dm⁻³", "2.0 mol dm⁻³", "5.0 cm³", "50.0 cm³"]
    clear_document_cache()
    doc = build_document("x", SPEC["ph-p7b"]["question"], "physics", data=_data("ph-p7b"))
    assert [f"{n.number.text} {n.unit.text}" for n, _a, _b, _w in doc.request.supplied_quantities] == ["20 counts per minute"]
    assert doc.request.supplied_values == ()


# ============================================================================================ units given only in the task or its table
def test_table_header_units_with_ascii_exponents_are_read():
    assert ascii_exponents("mm3 per g per hour") == "mm³ per g per hour" and ascii_exponents("mg dm-3") == "mg dm⁻³"
    [table] = parse_data_tables(_data("bi-t13"))
    col = table.columns[1]
    assert col.unit is not None and col.unit.text == "mm³ per g per hour" and col.unit_ascii
    [ess] = parse_data_tables(_data("ess-t13"))
    assert [c.unit.text if c.unit else None for c in ess.columns] == [None, "km", "mg dm⁻³", "mg dm⁻³", None]


def test_a_unit_per_another_is_read_whole():
    clear_document_cache()
    doc = build_document("Uptake rises from 18 mm³ per g per hour. The rate is 20 counts per minute. It is 5 per cent.", None, "biology")
    assert [pv.node.unit.text for pv in doc.prose_values if getattr(pv.node, "unit", None) is not None] == ["mm³ per g per hour", "counts per minute"]


@pytest.mark.parametrize("unit, status", [("mm³", "ENTAILED"), ("cm³", "COUNTEREXAMPLE")])
def test_a_table_value_restated_in_another_unit_is_compared_in_si(unit, status):
    """'from 18 cm³ per g per hour at 10 °C' for the table's 18 mm3 per g per hour was silent (compared as written, 18 = 18)."""
    line = f"from 18 {unit} per g per hour at 10 °C"
    checks, findings = new_checks("bi-t13", replaced("bi-t13", "from 18 mm³ per g per hour at 10 °C", line), "biology")
    if status == "ENTAILED":
        assert checks == [] and findings == []
    else:
        assert [(k, st, sev) for k, st, sev, _f, _d in checks] == [("giv", status, "warning")] and findings == []


@pytest.mark.parametrize("line, status", [("Assumption: the background of 20 counts s⁻¹ is constant", "COUNTEREXAMPLE"),
                                          ("Assumption: the background of 20 counts min⁻¹ is constant", None)])
def test_a_value_with_the_task_s_number_and_another_unit_is_set_against_the_task_s_quantity(line, status):
    """Rule restated-unit: the task states 20 counts per minute; '20 counts s⁻¹' restates its number with another unit of the same
    dimension: a stem_given check in SI, at warning severity, which fails. Written with the task's unit, nothing is planned."""
    checks, findings = new_checks("ph-p7b", replaced("ph-p7b", "Assumption: the background of 20 counts min⁻¹ is constant", line), "physics")
    if status is None:
        assert checks == [] and findings == []
    else:
        assert [(k, st, sev) for k, st, sev, _f, _d in checks] == [("giv", status, "warning")] and findings == []
        assert checks[0][4].startswith("the stated value against the task's quantity of the same number") and "(rule restated-unit)" in checks[0][4]


@pytest.mark.parametrize("text", ["The water was heated by 20 K.", "A rise of 20 K is a rise of 20 °C.", "It took 3.0 min = 180 s."])
def test_temperatures_and_conversions_are_no_restated_unit(text):
    assert [c for c in decided(text, request="Heat the water from 20 °C for 3.0 minutes.")[0] if "(rule restated-unit)" in c[4]] == []


# ============================================================================================ rules percentage-change and half-lives
@pytest.mark.parametrize("tid, profile, old, new, status", [
    ("ess-t13", "ess", "(9.6 − 3.8) ÷ 9.6 × 100\n= 60.4% decrease", "(9.6 − 3.8) ÷ 3.8 × 100\n= 152.6% decrease", "COUNTEREXAMPLE"),
    ("bi-t13", "biology", "(80 − 40) ÷ 40 × 100 = 100%", "(80 − 40) ÷ 80 × 100 = 50%", "COUNTEREXAMPLE"),
])
def test_a_percentage_change_over_the_wrong_value_is_named(tid, profile, old, new, status):
    """'(9.6 − 3.8) ÷ 3.8 × 100 = 152.6% decrease' divides by the final value with the arithmetic right: the line over the
    starting value (the larger of a decrease, the smaller of an increase) is set against the stated value and fails, at warning
    severity (the direction is read from the words)."""
    checks, findings = new_checks(tid, replaced(tid, old, new), profile)
    pct = [c for c in checks if "(rule percentage-change)" in c[4]]
    assert [(k, st, sev) for k, st, sev, _f, _d in pct] == [("eq", status, "warning")] and findings == []
    assert pct[0][4].startswith("the percentage change as defined (the written change over the starting value, × 100)")


def test_a_percentage_change_over_the_starting_value_plans_nothing_more():
    """The recorded lines divide by the starting value: their arithmetic checks decide them, and nothing is added; a percentage
    error or uncertainty names no direction and is not read."""
    for tid, profile in (("ess-t13", "ess"), ("bi-t13", "biology")):
        assert not [c for c in task(tid, SPEC[tid]["response_text"], profile)[0] if "(rule percentage-change)" in c[4]]
    assert not [c for c in decided("Percentage error = (9.9 − 9.81) ÷ 9.81 × 100 = 0.92%")[0] if "(rule percentage-change)" in c[4]]


@pytest.mark.parametrize("old, new, rule_status", [("32 h is 4 half-lives", "32 h is 5 half-lives", ["COUNTEREXAMPLE", "COUNTEREXAMPLE"]),
                                                   (P7B_D, "C = 1600 counts min⁻¹ × (1/2)³ = 200 counts min⁻¹", ["ENTAILED", "COUNTEREXAMPLE"]),
                                                   (P7B_D, P7B_D, ["ENTAILED", "ENTAILED"])])
def test_the_number_of_half_lives_the_prose_states_is_checked(old, new, rule_status):
    """Rule half-lives: '32 h is 4 half-lives' is 4 × T½ (8.0 h, stated in (b)) against 32 h, and the power of ½ written after the
    phrase must be 4. '32 h is 5 half-lives' fails both; '(1/2)³ = 200' after '4 half-lives' fails the power (its arithmetic holds)."""
    checks, _findings = task("ph-p7b", replaced("ph-p7b", old, new), "physics")
    half = [c for c in checks if "(rule half-lives)" in c[4]]
    assert [st for _k, st, *_ in half] == rule_status and all(sev == "warning" for _k, _st, sev, *_ in half)
    assert half[0][4].startswith("the number of half-lives the prose states, times the half-life")
    assert half[1][4].startswith("the power of ½ in the decay against the number of half-lives the prose states: '(1/2)")


def test_half_lives_written_as_a_count_and_their_power_hold():
    text = "Number of half-lives: n = t/T½ = 24/8.0 = 3\nActivity after 3 half-lives: A = 640 × (½)³ = 640/8 = 80 Bq"
    checks, findings = decided(text, request="A radioactive sample has a half-life of 8.0 days and an initial activity of 640 Bq.")
    assert [st for _k, st, *_ in checks if "(rule half-lives)" in _[-1]] == ["ENTAILED"] and findings == []


# ============================================================================================ stated rounding of a stated value
@pytest.mark.parametrize("value, status", [("3", "COUNTEREXAMPLE"), ("2", "ENTAILED")])
def test_a_stated_value_restated_with_a_stated_rounding_is_checked(value, status):
    """'R = 2.4 Ω (the external resistance), or 3 Ω to one significant figure' was silent: a bracket label stood between the value
    and 'or', and the value was stated, not computed."""
    line = f"R = 2.4 Ω (the external resistance), or {value} Ω to one significant figure"
    checks, findings = new_checks("ph-t13", replaced("ph-t13", "R = 2.4 Ω (the external resistance)", line), "physics")
    # STEM repair 9 (rule rounded-digits): beside the restatement, the place the stated rounding names (the units, for one significant
    # figure of 3 or 2) is set against the place the restated value is written to (the units): that check holds for both values
    assert [(k, st) for k, st, *_ in checks] == [("res", status), ("eq", "ENTAILED")] and findings == []
    assert "the restated value is rounded as the prose states (to one significant figure): h = 1/2" in checks[0][4]
    assert "(rule rounded-digits)" in checks[1][4] and f"the value {value} is written to the place of 1;" in checks[1][4]


# ============================================================================================ a percentage and a quantity
@pytest.mark.parametrize("text, kinds", [("L = 2.0 m × 3.0 = 6.0 m. So the percentage uncertainty is 2%.", [("eq", "ENTAILED")]),
                                         ("x = 0.25 × 2 = 0.50, so 50%.", [("eq", "ENTAILED"), ("res", "ENTAILED")])])
def test_a_percentage_never_restates_a_quantity_of_a_dimension(text, kinds):
    """The false '2%' restatement of '820 counts min⁻¹' (the independent test's p7b Given): a percentage is no value of a length or a
    count rate; a bare value restated as a percentage still is."""
    assert [(k, st) for k, st, *_ in decided(text)[0]] == kinds


# ============================================================================================ rule given-uncertainty
@pytest.mark.parametrize("tid, line, profile, status", [
    ("ch-t13", "Given: thermometer uncertainty = 0.5 °C.", "chemistry", "ENTAILED"),
    ("ch-t13", "Given: thermometer uncertainty = 0.1 °C.", "chemistry", "COUNTEREXAMPLE"),
    ("ch-t13", "Given: uncertainty in temperature = ±0.5 °C.", "chemistry", "ENTAILED"),
    ("ch-t13", "Given: uncertainty in temperature = ±2 °C.", "chemistry", "COUNTEREXAMPLE"),
    ("ch-t13", "Given: Δθ = ±0.5 °C.", "chemistry", "ENTAILED"),
    ("ch-t13", "Given: Δθ = ±0.2 °C.", "chemistry", "COUNTEREXAMPLE"),
    ("ch-t13", "Given: uncertainty in the stopwatch reading = 0.01 s.", "chemistry", "ENTAILED"),
    ("ch-t13", "Given: uncertainty in the stopwatch reading = 0.05 s.", "chemistry", "COUNTEREXAMPLE"),
    ("ph-p7b", "Given: percentage uncertainty in each count rate = 2%.", "physics", "ENTAILED"),
    ("ph-p7b", "Given: percentage uncertainty in each count rate = 3%.", "physics", "COUNTEREXAMPLE"),
])
def test_a_given_uncertainty_is_set_against_the_uncertainties_stated(tid, line, profile, status):
    """A Given named as an uncertainty was set against the request's values of its quantity (0.5 °C failed against 20 °C and 60 °C:
    a false warning on a correct Given), one written '±0.5 °C' had neither its check nor its ST code, and a percentage uncertainty
    was named unchecked though the supplied text states it. Each is now set against the uncertainties stated (rule given-uncertainty),
    with the reading named."""
    checks, findings = task(tid, line, profile)
    assert [(k, st, sev) for k, st, sev, _f, _d in checks] == [("giv", status, "warning")] and findings == [], (checks, findings)
    d = checks[0][4]
    assert "an uncertainty, against the uncertainties the request and its supplied texts state (rule given-uncertainty)" in d
    assert "which of the uncertainties the request and its supplied texts state the Given restates is a reading (rule given-uncertainty)" in d
    assert ("'±" in d) is ("±" in line)  # the check quotes the value as written


def test_a_given_uncertainty_with_no_uncertainty_stated_is_named_unchecked():
    """ph-t13's request states no uncertainty: the Given uncertainty is ST-UNDEC-003 with why, never failed against 12 V or 0.50 Ω,
    and the statement's other Given is still checked."""
    checks, findings = task("ph-t13", "Given: thermometer uncertainty = ±0.5 °C, r = 0.50 Ω.", "physics")
    assert [(k, st) for k, st, *_ in checks] == [("giv", "ENTAILED")] and "'0.50 Ω'" in checks[0][4]
    assert findings == [("ST-UNDEC-003", "the Given value thermometer uncertainty = ±0.5 °C (an uncertainty: the request and its supplied texts state no "
                                         "uncertainty in °C) in s1.1 could not be set against the request: it is not checked against the request")]


@pytest.mark.parametrize("tid, line, profile, statuses", [
    # STEM repair 4: the uncertainty written with the Given is set against the supplied text's +/-0.5 °C (the second check, rule
    # given-uncertainty); with no uncertainty of its kind stated (ph-p7b's +/-2% is a percentage, ph-t13 states none) it is not read
    ("ch-t13", "Given: T = 20.0 ± 0.5 °C.", "chemistry", ["ENTAILED", "ENTAILED"]),
    ("ch-t13", "Given: T = 25.0 ± 0.5 °C.", "chemistry", ["COUNTEREXAMPLE", "ENTAILED"]),
    ("ch-t13", "Given: T = 20.0 ± 0.1 °C.", "chemistry", ["ENTAILED", "COUNTEREXAMPLE"]),
    ("ph-p7b", "Given: background = 20 ± 2 counts min⁻¹.", "physics", ["ENTAILED"]),
    ("ph-p7b", "Given: background = 30 ± 2 counts min⁻¹.", "physics", ["COUNTEREXAMPLE"]),
    ("ph-t13", "Given: ε = 12 ± 0.1 V, r = 0.50 Ω.", "physics", ["ENTAILED", "ENTAILED"]),
])
def test_a_given_written_with_its_uncertainty_is_set_against_the_request_at_its_central_value(tid, line, profile, statuses):
    """'Given: T = 20.0 ± 0.5 °C' had neither its check nor its ST code (no value node, so no Given): its central value is the
    Given value now (rule central-value), quoted whole."""
    checks, findings = task(tid, line, profile)
    assert [(k, st, sev) for k, st, sev, _f, _d in checks] == [("giv", s, "warning") for s in statuses] and findings == [], (checks, findings)
    first = checks[0][4]
    assert "(its central value, the Given being written with its uncertainty: rule central-value)" in first
    assert "± " in first.split("[claims")[0]
    if tid == "ch-t13":
        assert "the uncertainty of the Given value of T, written with it, against the uncertainties" in checks[1][4] and "(rule given-uncertainty)" in checks[1][4]


def test_the_uncertainties_the_request_and_its_supplied_texts_state_are_read_with_their_units():
    clear_document_cache()
    doc = build_document("x", SPEC["ch-t13"]["question"], "chemistry", data=_data("ch-t13"))
    got = [(n.number.text, u.text if u is not None else None, w) for n, _a, _b, u, w, _ws in doc.request.supplied_uncertainties]
    assert got == [("0.5", "°C", ""), ("0.01", "s", ""), ("0.5", "s", "")] and doc.request.request_uncertainties == ()
    clear_document_cache()
    doc = build_document("x", SPEC["ph-p7b"]["question"], "physics", data=_data("ph-p7b"))
    assert [(u, w) for _n, _a, _b, u, w, _ws in doc.request.supplied_uncertainties] == [(None, "%")]
    request = "The temperature was measured as 25.0 ± 0.5 °C and the mass as 2.00 +/- 0.01 g."
    clear_document_cache()
    doc = build_document("x", request, "chemistry")
    assert [(n.number.text, u.text) for n, _a, _b, u, _w, _ws in doc.request.request_uncertainties] == [("0.5", "°C"), ("0.01", "g")]
    for value, status in (("0.5", "ENTAILED"), ("0.2", "COUNTEREXAMPLE")):
        checks, findings = decided(f"Given: uncertainty in the temperature = {value} °C.", "chemistry", request=request)
        assert [(k, st) for k, st, *_ in checks] == [("giv", status)] and findings == [], (value, checks, findings)


def test_a_change_or_a_quantity_named_by_other_words_is_no_uncertainty():
    """Only a Given named or written as an uncertainty is one: a temperature with no such word is set against the request's
    temperatures exactly as before, and a Δ symbol written with a plain value is too."""
    for line, status in (("Given: T = 20 °C.", "ENTAILED"), ("Given: T = 25 °C.", "COUNTEREXAMPLE")):
        checks, findings = task("ch-t13", line, "chemistry")
        assert [(k, st) for k, st, *_ in checks] == [("giv", status)] and "rule given-uncertainty" not in checks[0][4], line


# ============================================================================================ the recorded answers
_RULES = ("(rule value-at)", "(rule central-value)", "(rule processed-data)", "rule supplied-values", "(rule restated-unit)", "(rule percentage-change)",
          "(rule half-lives)", "rule given-digits", "(rule given-uncertainty)")


@pytest.mark.parametrize("tid, profile", [("ph-t13", "physics"), ("ph-p7b", "physics"), ("maa-t13", "mathematics_aa"), ("maa-p7b", "mathematics_aa"),
                                          ("mai-t13", "mathematics_ai"), ("bi-t13", "biology"), ("ess-t13", "ess"), ("ch-t13", "chemistry"),
                                          ("cs-t13", "computer_science")])
def test_on_the_recorded_answers_every_new_reading_holds_and_names_nothing(tid, profile):
    """The clean control on genuine work: on every recorded STEM answer of round 7 each check a repair-3 rule plans holds, every
    check holds, and no error-free answer gains a finding."""
    it = SPEC[tid]
    checks, findings = task(tid, it["response_text"], profile)
    new = [(k, st) for k, st, _sev, _f, d in checks if any(r in d for r in _RULES)]
    assert all(st in ("ENTAILED", "SATISFIABLE") for _k, st in new), new
    assert not {"ST-UNDEC-003", "ST-PARSE-001", "ST-DIM-001"} & {c for c, _m in findings}, findings
