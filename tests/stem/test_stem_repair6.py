"""STEM repair 6: the sixth independent test of the STEM completion found four classes the front end did not decide as the pack
says. Each is fixed at its cause in the STEM front end, for its whole class, and every new reading has a clean control (correct
working is never flagged):

* rule ``prose-given``: a Given written in prose had neither a check nor an ST code ('Data: emf 15 V, internal resistance 0.50 Ω.',
  'Given: the mass of seeds is 12 g.', 'Given: mass of seeds: 12 g.', 'Given: 15.0 cm³ of acid.', 'We know the mass of seeds was
  12 g.'), while D31, I98 and the master prompt said every Given value has its check or ST-UNDEC-003; an agent's true
  ``finding_missing`` was refuted. Every value of a statement whose head ("Given", "Data", "Known", "We know") ends with a colon within
  three more words, of the list a line "Given:" opens, and of the first clause of a statement that begins "Given", "Known" or "We know"
  with no such colon is a Given value, named by its item's words and checked as the same Given written with "=" (rule named-given when
  the request names the quantity by those words); a value right after "at", "when", "whenever" or "if" is a condition, never a Given;
* rule ``part-given``: a symbol reused in a part with a value the request states passed with any such value ('P = (9.93 V)² / 4.0 Ω'
  and '/ 0.50 Ω' in the part that asks for the power in the 6.0 ohm resistor: ENTAILED, R dropped from the check); when the part's
  question states other values of that dimension and neither it nor the part's working before the line states this one, the symbol is
  checked at warning severity in a check of its own;
* rule ``fraction-unit``: a unit written after a fraction whose slash has no space ('(ln 2)/8 h⁻¹', '1/40 s⁻¹') was read as the
  divisor's only, so the recorded answer's own notation 'k = (ln 2)/8 h⁻¹ = 0.0866 h⁻¹' got a false ST-DIM-001 (rule bare-factor) and
  its SI form a false INT-SUBJ-001; the unit is read as the fraction's own when that gives the relation one dimension and the
  divisor's reading does not;
* rule ``boolean-gates``: NAND, NOR and XNOR (and ↑ ⊼ ↓ ⊽ in computer science) were outside the grammar: a correct gate and a wrong
  one got the same ST-PARSE-001 (a truth table, ST-UNDEC-001); they are read as the negations of AND, OR and XOR, and a gate written
  beside another operator, or NAND or NOR twice, with no brackets has two readings: ST-PARSE-002, never one reading chosen.
"""
from __future__ import annotations

import pytest

from epinoic_logic.stem.boolean import gate_order
from epinoic_logic.stem.lexer import lex

from .test_stem_repair5 import SPEC, after, before, decide, failing, holds, new, replaced, task, warnings

#: anchors in the recorded r7 answers
PH_A = "(a) [2]\nFor resistors"
PH_D = "= 16.4 W, so 16 W"
PH_PART_D = "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"
BI = "which makes ATP. [1 spare]"
CH = "so I cannot give one yet."
CS = "Next step: trace"
MI = "Next step: rework (a)"
MB_K = "k = (ln 2)/8 h⁻¹  A1"


def _place(tid: str, line: str) -> str:
    """``line`` written into the recorded answer of ``tid`` where the independent test wrote its plants."""
    if tid == "ph-t13":
        return before(tid, PH_A, line)
    if tid == "mai-t13":
        return before(tid, MI, line)
    if tid == "cs-t13":
        return before(tid, CS, line)
    return after(tid, {"bi-t13": BI, "ch-t13": CH}[tid], line, "\n\n")


def _rule(check, rule: str) -> bool:
    return f"rule {rule}" in check[3]


def _shown(check) -> str:
    """The value a Given check names ('the Given value against the request: '15 V'')."""
    return check[3].split(" [claims")[0].split(": ", 1)[-1]


# ============================================================================================ rule prose-given
PROSE_GIVENS = [
    # (task, the plant, its control, the value the plant's failing check names)
    ("ph-t13", "Data: emf 15 V, internal resistance 0.50 Ω.", "Data: emf 12 V, internal resistance 0.50 Ω.", "'15 V'"),
    ("ph-t13", "Known values: emf 15 V.", "Known values: emf 12 V.", "'15 V'"),
    ("ph-t13", "We know: emf 15 V, internal resistance 0.50 Ω.", "We know: emf 12 V, internal resistance 0.50 Ω.", "'15 V'"),
    ("ph-t13", "Given (from the question): emf 15 V.", "Given (from the question): emf 12 V.", "'15 V'"),
    ("ph-t13", "Data: emf 12 V and internal resistance 0.40 Ω.", "Data: emf 12 V and internal resistance 0.50 Ω.", "'0.40 Ω'"),
    ("ph-t13", "Data: emf 12 V; internal resistance 0.40 Ω.", "Data: emf 12 V; internal resistance 0.50 Ω.", "'0.40 Ω'"),
    ("ph-t13", "Data: emf 12 V internal resistance 0.40 Ω.", "Data: emf 12 V internal resistance 0.50 Ω.", "'0.40 Ω'"),
    ("bi-t13", "Given: the mass of seeds is 12 g.", "Given: the mass of seeds is 10 g.", "'12 g'"),
    ("bi-t13", "Given: mass of seeds: 12 g.", "Given: mass of seeds: 10 g.", "'12 g'"),
    ("bi-t13", "We know the mass of seeds was 12 g.", "We know the mass of seeds was 10 g.", "'12 g'"),
    ("bi-t13", "Given:\n- mass of seeds 12 g\n- five repeats at each temperature", "Given:\n- mass of seeds 10 g\n- five repeats at each temperature", "'12 g'"),
    ("ch-t13", "Given: 15.0 cm³ of acid.", "Given: 5.0 cm³ of acid.", "'15.0 cm³'"),
    ("ch-t13", "Known: the acid is 0.20 mol dm⁻³.", "Known: the acid is 2.0 mol dm⁻³.", "'0.20 mol dm⁻³'"),
    ("ch-t13", "Given: thermometer uncertainty ±0.2 °C.", "Given: thermometer uncertainty ±0.5 °C.", "'±0.2 °C'"),
    ("ch-t13", "Given: thermometer uncertainty +/-0.2 °C.", "Given: thermometer uncertainty +/-0.5 °C.", "'+/-0.2 °C'"),
    ("mai-t13", "Data: interest rate 4.6% per year, principal 4000 euros.", "Data: interest rate 3.6% per year, principal 4000 euros.", "'4.6%'"),
]


@pytest.mark.parametrize("tid,plant,control,shown", PROSE_GIVENS)
def test_a_given_written_in_prose_is_checked_like_one_written_with_equals(tid, plant, control, shown):
    """Before, every one of these plants had neither a check nor an ST code. The plant's contradicting value fails its Given check at
    warning severity (INT-SUBJ-004 in the receipt), the check's statement naming rule prose-given, and nothing else is new; the
    control's Given values are checked too, and hold."""
    c, f = new(tid, _place(tid, plant))
    bad = failing(c)
    assert len(bad) == 1 and bad[0][0] == "giv" and bad[0][1] == "COUNTEREXAMPLE" and bad[0][2] == "warning", (bad, c)
    assert _shown(bad[0]) == shown and _rule(bad[0], "prose-given"), bad[0][3][:300]
    assert not warnings(f), f
    c, f = new(tid, _place(tid, control))
    assert not failing(c) and not warnings(f), (failing(c), warnings(f))
    held = [x for x in c if x[0] == "giv" and _rule(x, "prose-given")]
    assert held and all(holds(x) for x in held), c


def test_a_prose_given_whose_words_the_request_names_is_set_against_that_quantity():
    """Rule named-given in prose: 'internal resistance 6.0 Ω' is set against the request's internal resistance (0.50 ohm), though the
    request states a 6.0 ohm resistor; the emf beside it holds."""
    c, f = new("ph-t13", _place("ph-t13", "Data: emf 12 V, internal resistance 6.0 Ω."))
    bad = failing(c)
    assert [(_shown(x), x[2]) for x in bad] == [("'6.0 Ω'", "warning")] and _rule(bad[0], "named-given") and _rule(bad[0], "prose-given"), bad
    assert [_shown(x) for x in c if holds(x)] == ["'12 V'"] and not warnings(f)


@pytest.mark.parametrize("line,status", [("Given that the emf is 12 V, the current is 4.1 A.", "ENTAILED"),
                                         ("Given that the emf is 15 V, the current is 4.1 A.", "COUNTEREXAMPLE")])
def test_only_the_first_clause_of_a_given_clause_with_no_colon_is_given(line, status):
    """The current after the first comma is the statement's own result: it is never set against the request (no check, no ST code);
    the emf of the first clause is the Given, checked."""
    c, f = new("ph-t13", _place("ph-t13", line))
    assert [(x[0], x[1], _shown(x)) for x in c] == [("giv", status, "'12 V'" if status == "ENTAILED" else "'15 V'")], c
    assert not warnings(f), f


def test_a_clause_known_or_we_know_opens_is_given_up_to_its_first_comma_or_semicolon():
    c, _f = new("ph-t13", _place("ph-t13", "Known that the internal resistance is 0.40 Ω; the current is 4.1 A."))
    assert [(x[1], _shown(x)) for x in c] == [("COUNTEREXAMPLE", "'0.40 Ω'")], c
    c, f = new("ph-t13", _place("ph-t13", "We know the internal resistance is 0.50 Ω, so the lost volts are 2.1 V."))
    assert [(x[1], _shown(x)) for x in c] == [("ENTAILED", "'0.50 Ω'")] and not warnings(f), (c, f)


@pytest.mark.parametrize("line", ["Data analysis shows an emf of 15 V.", "The emf is 15 V here."])
def test_data_with_no_colon_and_prose_outside_a_given_statement_are_no_given(line):
    """No Given is read (rule prose-given), and no finding is new. STEM repair 9: the request names its emf by the words after the
    preposition ('a battery of emf 12 V' -> emf; it had been 'battery, emf'), so the value the prose states for the emf is the one check,
    rule named-given's: set against the request's 12 V, it fails at warning severity."""
    checks, findings = new("ph-t13", _place("ph-t13", line))
    assert [(x[0], x[1], x[2], _shown(x)) for x in checks] == [("giv", "COUNTEREXAMPLE", "warning", "'15 V'")] and findings == [], checks
    assert _rule(checks[0], "named-given") and not _rule(checks[0], "prose-given") and "the Given value of" not in checks[0][3]


def test_a_value_right_after_at_is_the_condition_never_a_given():
    """'Given: the oxygen uptake at 30 °C is 85 mm³ per g per hour.': 30 °C is the condition; the uptake is set against the supplied
    table's row 30 (80), and no check names 30 °C as a Given."""
    c, _f = new("bi-t13", _place("bi-t13", "Given: the oxygen uptake at 30 °C is 85 mm³ per g per hour."))
    assert [(x[0], x[1], _shown(x)) for x in c] == [("giv", "COUNTEREXAMPLE", "'85 mm³ per g per hour'")], c
    assert "the supplied table's row 30 against Mean oxygen uptake there (80)" in c[0][3]
    c, f = new("bi-t13", _place("bi-t13", "Given: at 30 °C the uptake is 80 mm³ per g per hour."))
    assert not failing(c) and not warnings(f) and [(x[0], _shown(x)) for x in c] == [("giv", "'80 mm³ per g per hour'")], (c, f)


def test_a_prose_given_of_a_kind_the_request_states_no_value_of_is_named_unchecked():
    """Every Given value has its check or its ST-UNDEC-003 (D31, I98): a volume the request states nowhere is named."""
    c, f = new("bi-t13", _place("bi-t13", "Given: the volume of water is 25.0 cm³."))
    assert c == [] and [(x[0], x[1]) for x in f] == [("ST-UNDEC-003", "warning")] and "volume of water = 25.0 cm³" in f[0][2], (c, f)


def test_an_amount_after_a_currency_sign_or_a_numeral_with_a_thousands_space_is_never_read_in_part():
    """As for a Given written with "=" (tests/stem/test_stem_repair2.py): '€4000' is an amount, never read; '4 000' may be a numeral
    written with a thousands space, named ST-PARSE-001 and never set against the request in part ('000' or '4')."""
    c, f = new("mai-t13", _place("mai-t13", "Data: interest rate 3.6% per year, principal €4000."))
    assert [(x[0], x[1], _shown(x)) for x in c] == [("giv", "ENTAILED", "'3.6%'")] and f == [], (c, f)
    c, f = new("mai-t13", _place("mai-t13", "Data: interest rate 3.6% per year, principal 4 000 euros."))
    assert [(x[0], x[1], _shown(x)) for x in c] == [("giv", "ENTAILED", "'3.6%'")], c
    assert [(x[0], x[2]) for x in f] == [("ST-PARSE-001", "the Given value of principal ('4 000') in s15.1 may be a numeral written with a thousands "
                                                          "space; it is not read, and it is not checked against the request")], f


def test_no_recorded_answer_reads_a_prose_given_a_part_given_or_a_fraction_unit():
    """The recorded r7 answers state no Given in prose, reuse no symbol with a value its part names nowhere, and write no unit after a
    compact fraction in a relation: none of the three rules reads anything in them (their checks and findings are unchanged)."""
    for tid in ("ph-t13", "ph-p7b", "maa-t13", "maa-p7b", "mai-t13", "bi-t13", "ess-t13", "ch-t13", "cs-t13"):
        checks, _f = task(tid, SPEC[tid]["response_text"])
        assert not [x for x in checks if _rule(x, "prose-given") or _rule(x, "part-given") or _rule(x, "fraction-unit")], tid


# ============================================================================================ rule part-given
@pytest.mark.parametrize("value,result", [("4.0 Ω", "24.7 W, so 25 W"), ("0.50 Ω", "197 W, so 200 W")])
def test_a_symbol_reused_with_a_request_value_its_part_names_nowhere_is_checked_at_warning(value, result):
    """The independent test's ph-t13 (d) plants: R reused in the part that asks for the power in the 6.0 ohm resistor, with the other
    resistor's or the internal resistance's value (before: ENTAILED, R dropped from the check). The substitution of R is a check of its
    own, at warning severity, naming rule part-given; V, checked against its bindings in the same line, keeps its own check at error
    severity, and holds."""
    c, f = new("ph-t13", replaced("ph-t13", "P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", f"P = (9.93 V)² / {value} = {result}"))
    bad = failing(c)
    assert [(x[0], x[1], x[2]) for x in bad] == [("sub", "COUNTEREXAMPLE", "warning")] and _rule(bad[0], "part-given"), bad
    assert "rule part-given: R reused here for a value the request gives; its part's question states 6.0 ohm, which it matches too" in bad[0][3]
    assert "failure severity warning: the request's value a reused symbol stands for in this part is a reading (rule part-given)" in bad[0][3]
    v_check = [x for x in c if x[0] == "sub" and not _rule(x, "part-given")]
    assert [(x[1], x[2]) for x in v_check] == [("ENTAILED", "error")] and "substituted symbols: V" in v_check[0][3], v_check
    assert not warnings(f), f


def test_a_current_computed_with_the_other_resistor_in_that_part_fails_its_part_given_check():
    c, _f = new("ph-t13", replaced("ph-t13", PH_PART_D, "I = V/R = 9.93 V / 4.0 Ω = 2.48 A\n" + PH_PART_D))
    bad = failing(c)
    assert [(x[0], x[1], x[2]) for x in bad] == [("sub", "COUNTEREXAMPLE", "warning")] and _rule(bad[0], "part-given"), bad


@pytest.mark.parametrize("text", [
    replaced("ph-t13", PH_PART_D, "I = V/R = 9.93 V / 6.0 Ω = 1.655 A\n" + PH_PART_D),
    after("ph-t13", PH_D, "For comparison, the 4.0 Ω resistor dissipates P = (9.93 V)² / 4.0 Ω = 24.7 W."),
])
def test_the_value_the_part_s_question_or_its_working_before_the_line_names_is_read_with_no_check(text):
    """The part's own 6.0 Ω, and the 4.0 Ω its working names before the line ('the 4.0 Ω resistor dissipates …'), are read for R in the
    part, with no part-given check: nothing new fails and nothing is named."""
    c, f = new("ph-t13", text)
    assert not failing(c) and not warnings(f) and not [x for x in c if _rule(x, "part-given")], (failing(c), f)


def test_a_value_the_request_does_not_state_is_still_checked_against_the_bindings_at_error():
    c, _f = new("ph-t13", replaced("ph-t13", "P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "P = (9.93 V)² / 5.0 Ω = 19.7 W, so 20 W"))
    bad = failing(c)
    assert [(x[0], x[1], x[2]) for x in bad] == [("sub", "COUNTEREXAMPLE", "error")] and not _rule(bad[0], "part-given"), bad


# ============================================================================================ rule fraction-unit
@pytest.mark.parametrize("tid,old,new_text,status", [
    ("maa-p7b", MB_K, "k = (ln 2)/8 h⁻¹ = 0.0866 h⁻¹  A1", "SATISFIABLE"),
    ("ch-t13", CH, CH + "\n\nThe rate is 1/40 s⁻¹ = 0.025 s⁻¹.", "ENTAILED"),
])
def test_a_unit_after_a_compact_fraction_is_read_as_the_fraction_s_own_when_that_gives_one_dimension(tid, old, new_text, status):
    """Before, rule bare-factor raised ST-DIM-001 on this correct working (the recorded answer's own notation): the relation is now
    checked with the fraction's unit, its statement naming rule fraction-unit, and it holds with no finding."""
    c, f = new(tid, replaced(tid, old, new_text))
    eq = [x for x in c if x[0] == "eq"]
    assert [x[1] for x in eq] == [status] and _rule(eq[0], "fraction-unit") and "is read as the fraction's own" in eq[0][3], eq
    assert not failing(c) and f == [], (failing(c), f)


@pytest.mark.parametrize("tid,old,new_text", [
    ("maa-p7b", MB_K, "k = (ln 2)/8 h⁻¹ = 0.0966 h⁻¹  A1"),
    ("ch-t13", CH, CH + "\n\nThe rate is 1/40 s⁻¹ = 0.25 s⁻¹."),
])
def test_a_slip_after_a_compact_fraction_still_fails_its_arithmetic(tid, old, new_text):
    c, _f = new(tid, replaced(tid, old, new_text))
    eq = [x for x in failing(c) if x[0] == "eq"]
    assert eq and eq[0][2] == "error" and _rule(eq[0], "fraction-unit"), failing(c)


def test_st_dim_001_is_raised_only_when_neither_reading_agrees():
    c, f = new("ch-t13", replaced("ch-t13", CH, CH + "\n\nThe rate is 1/40 s⁻¹ = 0.025 m."))
    assert [x[0] for x in f] == ["ST-DIM-001"] and "(rule bare-factor)" in f[0][2] and not [x for x in c if _rule(x, "fraction-unit")], (c, f)


@pytest.mark.parametrize("text,dim_finding", [
    ("1 / 0.087 h⁻¹ = 11.5 h⁻¹", True), ("1 / 0.087 h⁻¹ = 11.5 h", False), ("1 / 40 s⁻¹ = 0.025 s⁻¹", True), ("1 ÷ 40 s⁻¹ = 0.025 s⁻¹", True),
    ("t = 0.693/0.087 h⁻¹ = 8.0 h", False), ("0.693/8.0 h = 0.087 h⁻¹", False),
])
def test_a_spaced_slash_a_division_sign_or_an_agreeing_divisor_keeps_the_divisor_s_unit(text, dim_finding):
    """Only a compact fraction whose divisor's reading disagrees is re-read: with a space around the slash or with ÷ the unit is the
    divisor's (ST-DIM-001 where that disagrees), and a divisor's unit that agrees is kept."""
    checks, findings = decide(text, None, "physics")
    assert ([c for c, _s, _m in findings] == ["ST-DIM-001"]) == dim_finding, findings
    assert all(holds(x) for x in checks) and not [x for x in checks if _rule(x, "fraction-unit")], checks


@pytest.mark.parametrize("text,ok", [("λ = (ln 2)/8.0 h⁻¹ = 2.4 × 10⁻⁵ s⁻¹", True), ("λ = (ln 2)/8.0 h⁻¹ = 2.4 × 10⁻⁴ s⁻¹", False)])
def test_the_si_form_of_a_fraction_with_its_unit_is_checked(text, ok):
    """Before, '(ln 2)/8.0 h⁻¹ = 2.4 × 10⁻⁵ s⁻¹' failed its arithmetic in SI (the divisor's reading) and got two ST-DIM-001."""
    checks, findings = decide(text, None, "physics")
    assert [(k, holds((k, st))) for k, st, _sev, _d in checks] == [("eq", ok)] and findings == [], (checks, findings)


# ============================================================================================ rule boolean-gates
GATES = [
    ("With A = 0 and B = 1, A NAND B = 1.", True), ("With A = 0 and B = 1, A NAND B = 0.", False),
    ("With A = 0 and B = 0, A NOR B = 1.", True), ("With A = 0 and B = 0, A NOR B = 0.", False),
    ("With A = 1 and B = 0, A XNOR B = 0.", True), ("With A = 1 and B = 0, A XNOR B = 1.", False),
    ("By definition, A NOR B = NOT (A OR B).", True), ("By definition, A NOR B = NOT A OR NOT B.", False),
    ("By definition, A NAND B = NOT A OR NOT B.", True), ("By definition, A NAND B = NOT A AND NOT B.", False),
    ("By definition, A XNOR B = (A AND B) OR (NOT A AND NOT B).", True), ("By definition, A XNOR B = (A AND NOT B) OR (NOT A AND B).", False),
    ("With the Sheffer stroke, A ↑ B = NOT A OR NOT B.", True), ("With the Sheffer stroke, A ↑ B = NOT A AND NOT B.", False),
    ("With the Sheffer stroke, A ⊼ B = NOT (A AND B).", True),
    ("With the Peirce arrow, A ↓ B = NOT A AND NOT B.", True), ("With the Peirce arrow, A ↓ B = NOT A OR NOT B.", False),
    ("With the Peirce arrow, A ⊽ B = NOT (A OR B).", True),
    ("So (A NAND B) NAND C = NOT ((NOT (A AND B)) AND C).", True), ("So (A NAND B) NAND C = NOT (A AND B AND C).", False),
    ("So A XNOR B XNOR C = A XOR B XOR C.", True),
    ("So NOT A NAND B = A OR NOT B.", True), ("So NOT A NAND B = NOT A OR B.", False),
]


@pytest.mark.parametrize("line,right", GATES)
def test_nand_nor_and_xnor_are_read_as_the_negations_of_and_or_and_xor(line, right):
    """Before, a correct gate and a wrong one got the same ST-PARSE-001 (the arrow ended the run: 'A ↑ B = …' was read from B). Each is
    one Boolean check now: it holds when right and fails when wrong (a witness makes the two sides differ), with no finding."""
    c, f = new("cs-t13", _place("cs-t13", line))
    assert [(x[0], holds(x), x[2]) for x in c] == [("bool", right, "error")] and f == [], (c, f)


_TABLE = "| A | B | A {g} B |\n|---|---|---|\n| 0 | 0 | {r[0]} |\n| 0 | 1 | {r[1]} |\n| 1 | 0 | {r[2]} |\n| 1 | 1 | {r[3]} |"


@pytest.mark.parametrize("gate,right,wrong", [("NAND", "1110", "1111"), ("NOR", "1000", "1100"), ("XNOR", "1001", "1101")])
def test_a_truth_table_of_a_gate_is_checked(gate, right, wrong):
    """Before, ST-UNDEC-001 on both tables."""
    for rows, ok in ((right, True), (wrong, False)):
        c, f = new("cs-t13", _place("cs-t13", _TABLE.format(g=gate, r=rows)))
        assert [(x[0], holds(x)) for x in c] == [("tt", ok)] and f == [], (gate, rows, c, f)


@pytest.mark.parametrize("line", ["So A NAND B NAND C = 1.", "So A NAND B AND C = 0.", "So A OR B NOR C = 0.", "So A NOR B NOR C = 1.",
                                  "So A NAND B XNOR C = 1."])
def test_a_gate_beside_another_operator_or_twice_with_no_brackets_has_two_readings(line):
    """Never one reading chosen: ST-PARSE-002 names it, and nothing is checked."""
    c, f = new("cs-t13", _place("cs-t13", line))
    assert c == [] and [(x[0], x[1]) for x in f] == [("ST-PARSE-002", "warning")] and "a Boolean expression with two readings" in f[0][2], (c, f)


def test_a_truth_table_column_whose_gates_have_two_readings_is_named_st_parse_002():
    rows = "".join(f"| {a} | {b} | {c} | 1 |\n" for a in (0, 1) for b in (0, 1) for c in (0, 1))
    c, f = new("cs-t13", _place("cs-t13", "| A | B | C | A NAND B NAND C |\n|---|---|---|---|\n" + rows.rstrip("\n")))
    assert c == [] and [(x[0], x[1]) for x in f] == [("ST-PARSE-002", "warning")] and "the output column 'A NAND B NAND C' has two readings" in f[0][2], (c, f)


def test_gate_order_reads_each_bracket_level():
    def toks(s: str):
        return lex(s, 0, len(s), mode="plain", cs=True).tokens
    for s in ("A NAND B NAND C", "A NAND B AND C", "A OR B NOR C", "A NAND B C", "A NAND B XNOR C", "(A NAND B NAND C) OR D", "A ↑ B ↑ C", "A + B ↓ C"):
        assert gate_order(toks(s)), s
    for s in ("A NAND B", "(A NAND B) NAND C", "A NAND (B AND C)", "A XNOR B XNOR C", "NOT A NAND B", "A AND B OR C", "(A ↑ B) ↓ C", "A NAND NOT B"):
        assert gate_order(toks(s)) is None, s


def test_the_gate_symbols_and_words_are_read_only_in_computer_science():
    """An arrow in chemistry prose ('T ↑') and a lower-case "nor" are no gates; with ``cs`` the arrows and the upper-case words are."""
    assert [(t.kind, t.text) for t in lex("A ↑ B ⊽ C", 0, 9, mode="plain", cs=True).tokens if t.kind == "BOOL"] == [("BOOL", "NAND"), ("BOOL", "NOR")]
    assert not [t for t in lex("A ↑ B ⊽ C", 0, 9, mode="plain", cs=False).tokens if t.kind == "BOOL"]
    checks, findings = decide("The temperature T ↑ so the rate ↑ by 2 × 3 = 6.", None, "chemistry")
    assert [(k, st) for k, st, _sev, _d in checks] == [("eq", "ENTAILED")] and findings == []
    checks, findings = decide("Neither the rate nor the yield changes: 2 + 2 = 4.", None, "chemistry")
    assert [(k, st) for k, st, _sev, _d in checks] == [("eq", "ENTAILED")] and findings == []
