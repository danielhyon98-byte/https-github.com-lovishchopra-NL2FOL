"""Round-7 arena handoffs to the parsers' owner, after the STEM and overseer builds merged: arithmetic and chronology readers.

* parser-safety-13: the general reading read '2.5e3', '2.5 × 10³' and '1e9' by their mantissa, so a correct rise from 500 tonnes to 2,500
  tonnes was an INT-SUBJ-001 error on the Economics and History branches. A pair figure in scientific notation is now read whole (the
  STEM number reader gives its exact value), and no reader takes the mantissa alone or starts a figure at the exponent.
* robustness-and-contracts-7: a correct answer wrapped in quotation marks paired a chronology cue with a year of its next sentence. A
  dated relation is now read piece by piece at the sentence ends a quotation or a JSON string holds.
* r7 history handoff A1: worked equations on the Economics, Business Management and generic branches were only named undecided
  (CORE-QNT-001). They are now engine problems (``branches.worked``): a wrong result is a COUNTEREXAMPLE and INT-SUBJ-001, a right one
  ENTAILED, and the undecided report and the verdict never both name a line.
* r7 history handoff A2: a from/to pair with SI unit symbols ('rises from 4.0 Ω to 2.4 Ω') had no direction check on the STEM branches.
  The direction word is now checked in the SI reading (figures in SI units), except a verb of motion over lengths.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist.chronology import chronology_relations, statement_pieces
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.packs import BusinessPack, EconomicsPack, GenericPack, pack_decided_equations
from epinoic_logic.branches.quant import extract_quant_checks, undecided_quant_statements
from epinoic_logic.branches.worked import decided_worked_chains, worked_problems
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem.si_reading import SI_READING
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

KEY = b"branches-r7-handoff-parsers-key-01"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def through_hub(text: str, question: str = "Describe the change.", *, subject: str, agent: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, question)
    return hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-x")


def statuses(text: str, reading=None) -> list[tuple[str, str]]:
    kw = {"reading": reading} if reading is not None else {}
    return [(c.kind, verify(c.problem, CFG).status.value) for c in extract_quant_checks(text, request_id="r", claim_id="c", **kw)]


def report(subject: str, agent: str, text: str) -> SpecialistReport:
    return SpecialistReport(report_id="rep-u", request_id="r", task_id="t", agent_id=agent, subject=subject, task_type="short_answer", original_response=text,
                            response_sha256=sha256_text(text), supplied_texts=[],
                            claims=[ClaimRecord(request_id="r", task_id="t", report_id="rep-u", agent_id=agent, subject=subject, task_type="short_answer",
                                                claim_id="c1", claim_text=text, claim_role="point", materiality="material")],
                            created_at="2026-10-12T00:00:00Z")


# ------------------------------------------------------------------ parser-safety-13: scientific notation in the general reading

SCI_RISES = [
    "Output rose from 500 tonnes to 2.5e3 tonnes between 1990 and 2000.",
    "Output rose from 500 tonnes to 2.5 × 10³ tonnes between 1990 and 2000.",
    "It rose from 5 to 1e9 between 1990 and 2000.",
]


@pytest.mark.parametrize("subject,agent", [("Economics", "economics-specialist"), ("History", "history-specialist")])
@pytest.mark.parametrize("text", SCI_RISES)
def test_ps13_a_correct_rise_in_scientific_notation_is_no_error(subject, agent, text):
    _reply, rc = through_hub(text, subject=subject, agent=agent)
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001"], [f.message for f in rc.findings if f.code == "INT-SUBJ-001"]


@pytest.mark.parametrize("text,expected", [
    ("Output rose from 500 tonnes to 2.5e3 tonnes between 1990 and 2000.", "ENTAILED"),       # read whole: 2,500 > 500
    ("Output fell from 500 tonnes to 2.5e3 tonnes between 1990 and 2000.", "COUNTEREXAMPLE"),  # negative control: the direction is still checked
    ("Output rose from 2 × 10³ tonnes to 3 × 10³ tonnes, a rise of 50 per cent.", "ENTAILED"),
    ("Output rose from 2 × 10³ tonnes to 3 × 10³ tonnes, a rise of 20 per cent.", "COUNTEREXAMPLE"),
    ("Output rose from 500 tonnes in 1990 to 3,000 tonnes in 2000, an increase of 2.5e3 tonnes.", "ENTAILED"),
    ("Output rose from 500 tonnes in 1990 to 3,000 tonnes in 2000, an increase of 3.5e3 tonnes.", "COUNTEREXAMPLE"),
])
def test_ps13_scientific_notation_is_read_whole(text, expected):
    got = statuses(text)
    assert got and got[0][1] == expected, got


@pytest.mark.parametrize("text", [
    "Output rose from 500 to 1e100 between 1990 and 2000.",       # an exponent beyond the reader's two digits: never read as 1
    "Output rose from 500 to 2.5e−3 between 1990 and 2000.",      # a Unicode minus in an e-form: never read as 2.5 or as 3
    "The army lost 2.2 × 10⁴ men.",                               # never 2.2, never the 10 of the power
])
def test_ps13_a_mantissa_is_never_read_alone(text):
    assert all(status != "COUNTEREXAMPLE" for _k, status in statuses(text)), statuses(text)


def test_ps13_figures_in_words_and_plain_digits_are_unchanged():
    assert statuses("Output rose from six to sixty tonnes, a tenfold increase.") == [("fold_change", "ENTAILED")]
    assert statuses("Output rose from 1.4 million to 6 million, a threefold increase.") == [("fold_change", "COUNTEREXAMPLE")]


# ------------------------------------------------------------------ robustness-and-contracts-7: a quoted answer's chronology

QUOTED = [
    '"The crash of 1929 came after a speculative boom. Banks failed in 1930 and 1931."',
    "“The crash of 1929 came after a speculative boom. Banks failed in 1930 and 1931.”",
]


@pytest.mark.parametrize("text", QUOTED)
def test_rc7_a_quoted_answer_gets_no_false_chronology_failure(text):
    _reply, rc = through_hub(text, "Explain the causes of the 1929 crash.", subject="History", agent="history-specialist")
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    unquoted = text.strip('"“”')
    _reply, rc2 = through_hub(unquoted, "Explain the causes of the 1929 crash.", subject="History", agent="history-specialist")
    assert not [f for f in rc2.findings if f.code == "INT-SUBJ-001"]


def test_rc7_a_cue_is_never_paired_across_a_sentence_end_inside_a_quotation_or_a_json_string():
    for text in QUOTED + ['{"answer": "The crash of 1929 came after a speculative boom. Banks failed in 1930 and 1931."}']:
        assert len(statement_pieces(text)) == 2, statement_pieces(text)
        assert chronology_relations(text) == []
    # negative control: a wrong order inside one quoted sentence is still read and still violated
    [rel] = chronology_relations('"The crash of 1929 came after the boom of 1931. Banks failed in 1930."')
    assert rel.decided and rel.violated
    _reply, rc = through_hub('"The crash of 1929 came after the boom of 1931. Banks failed in 1930."', "Explain.", subject="History", agent="history-specialist")
    assert any(f.code == "INT-SUBJ-001" for f in rc.findings)


@pytest.mark.parametrize("text", [
    'He wrote that "the war of c. 1914 came after the crisis of 1912".',               # an abbreviation is no sentence end
    '"A. J. P. Taylor argued the war of 1939 came after the pact of 1940."',          # nor is an initial
    "The crash of 1929 came after the boom of 1928.",                                 # no quotation mark: one piece
])
def test_rc7_abbreviations_and_initials_do_not_cut_a_piece(text):
    assert statement_pieces(text) == [text]


# ------------------------------------------------------------------ A1: worked equations on the prose branches are engine problems

A1 = [
    ("Business Management", "business-management-specialist", "Break-even quantity = $6,000 ÷ $2.00 = 2,000 loaves per month.",
     "Break-even quantity = $6,000 ÷ $2.00 = 3,000 loaves per month."),
    ("Business Management", "business-management-specialist", "Fixed costs = $2,500 + $2,800 + $700 = $7,000.", "Fixed costs = $2,500 + $2,800 + $700 = $6,000."),
    ("Economics", "economics-specialist", "PED: (1.90 − 1.60) ÷ 1.60 × 100 = 28.75%.", "PED: (1.90 − 1.60) ÷ 1.60 × 100 = 18.75%."),
    ("Economics", "economics-specialist", "Tax revenue = $0.40 × 105 million litres = $52 million.", "Tax revenue = $0.40 × 105 million litres = $42 million."),
    ("Geography", "geography-specialist", "Dependency ratio = 31 ÷ 69 × 100 = 54.9.", "Dependency ratio = 31 ÷ 69 × 100 = 44.9."),
    ("Geography", "geography-specialist", "Growth rate = (31 − 11) ÷ 10 = 3.0%.", "Growth rate = (31 − 11) ÷ 10 = 2.0%."),
]


@pytest.mark.parametrize("subject,agent,wrong,right", A1)
def test_a1_a_wrong_worked_result_is_an_engine_counterexample_and_a_right_one_is_entailed(subject, agent, wrong, right):
    _reply, rc = through_hub(wrong, "q", subject=subject, agent=agent)
    worked = [fc for fc in rc.formal_checks if "-worked-" in fc.constraint_id]
    assert [fc.formal_status for fc in worked] == ["COUNTEREXAMPLE"]
    failures = [f for f in rc.findings if f.code == "INT-SUBJ-001" and "worked_arithmetic" in f.message]
    assert failures and failures[0].claim_ids and failures[0].formal_result_id
    # the undecided report and the verdict never both name a line
    assert not [f for f in rc.structural_findings if f.code == "CORE-QNT-001" and "worked arithmetic" in f.message]
    _reply, ok = through_hub(right, "q", subject=subject, agent=agent)
    assert [fc.formal_status for fc in ok.formal_checks if "-worked-" in fc.constraint_id] == ["ENTAILED"]
    assert not [f for f in ok.findings if f.code == "INT-SUBJ-001"]


@pytest.mark.parametrize("line,expected", [
    ("Tax = 5% × $200 = $10.", "ENTAILED"),                       # a per cent of an amount is a fraction
    ("Tax = 5% × $200 = $1,000.", "COUNTEREXAMPLE"),              # no 'as written' reading for money
    ("Share = 12.50% ÷ 18.75% = 0.67.", "ENTAILED"),
    ("Gap = 12.5% − 10.0% = 2.5 percentage points.", "ENTAILED"),  # per-cent arithmetic stated in points
    ("Q = 6,000 ÷ (5.00 − 3.00) = 3,000 units.", "ENTAILED"),     # a divisor that is an expression: an auxiliary the engine defines
    ("Q = 6,000 ÷ (5.00 − 3.00) = 2,000 units.", "COUNTEREXAMPLE"),
    ("Value = 4,000 × (1 + 0.036)^5 = 4,773.9", "ENTAILED"),
    ("Value = 4,000 × (1 + 0.036)^5 = 4,973.9", "COUNTEREXAMPLE"),
    ("Interest = 7 ÷ 3 = 2.", "COUNTEREXAMPLE"),                  # exact mode: every figure exact, a one-digit result has no slack
    ("Interest = 1,000 ÷ 3 = 333.", "ENTAILED"),
    ("Loss = $5,000 − $7,000 = −$2,000.", "ENTAILED"),
    ("Loss = $5,000 − $7,000 = $2,000.", "COUNTEREXAMPLE"),
    ("Revenue = 2.5 × 10³ × $4 = $10,000.", "ENTAILED"),
])
def test_a1_the_reading_of_worked_arithmetic(line, expected):
    [wp] = worked_problems(line, report_id="r", request_id="q", prefix="generic-worked")
    assert verify(Problem.model_validate(wp.problem), CFG).status.value == expected
    assert "proves a property of its encoding only" in wp.problem["notes"]


@pytest.mark.parametrize("line", [
    "Speed = 120 km ÷ 90 minutes = 80 km per hour.",           # two units of measurement: an unwritten conversion
    "Annual = $500 per month × 12 = $6,000 per year.",         # month and year
    "Half of $6,000 ÷ 2 = $1,500.",                            # label words that take part in the arithmetic
    "Cost = £500 + $200 = $700.",                              # two currencies
])
def test_a1_a_line_outside_the_reading_stays_named_undecided(line):
    assert worked_problems(line, report_id="r", request_id="q", prefix="generic-worked") == []
    rep = report("Geography", "geography-specialist", line)
    assert GenericPack().formal_checks(rep) == []
    assert not pack_decided_equations(rep)
    _reply, rc = through_hub(line, "q", subject="Geography", agent="geography-specialist")
    assert any(f.code == "CORE-QNT-001" and "worked arithmetic" in f.message for f in rc.structural_findings)


def test_a1_an_elasticity_or_a_margin_is_decided_once_by_its_own_pack():
    ped = report("Economics", "economics-specialist", "PED = −12.50 ÷ 18.75 = −0.67")
    kinds = [fc.kind for fc in EconomicsPack().formal_checks(ped)]
    assert kinds == ["elasticity"]
    margin = report("Business Management", "business-management-specialist", "Gross profit margin = ($100,800 ÷ $201,600) × 100 = 50.00%")
    assert [fc.kind for fc in BusinessPack().formal_checks(margin)] == ["margin"]
    assert pack_decided_equations(ped) and pack_decided_equations(margin)


def test_a1_other_branches_keep_their_readers():
    # the History branch names a worked equation undecided as before; the STEM branches read the maths with the STEM pack
    rep = report("History", "history-specialist", "Losses = 1,200 + 800 = 2,500 men.")
    assert not pack_decided_equations(rep)
    assert decided_worked_chains("Losses = 1,200 + 800 = 2,500 men.")  # the reader would read it; the History branch does not run it


# ------------------------------------------------------------------ A2: a pair's direction word in the SI reading

PHYSICS = SI_READING.for_profile("physics")


@pytest.mark.parametrize("text,expected", [
    ("The external resistance rises from 4.0 Ω to 2.4 Ω.", "COUNTEREXAMPLE"),
    ("The current from the cell falls from 2.7 A to 4.1 A.", "COUNTEREXAMPLE"),
    ("The wavelength increases from 400 nm to 300 nm.", "COUNTEREXAMPLE"),
    ("The pd falls from 12 V to 9.0 V.", "ENTAILED"),
    ("It decreases from 5.0 kΩ to 500 Ω.", "ENTAILED"),            # compared in SI units
    ("The temperature rises from 20 °C to 80 °C.", "ENTAILED"),     # an offset scale in one unit: the order is defined
    ("The velocity falls from 4.0 m/s to -2.0 m/s.", "ENTAILED"),
])
def test_a2_the_direction_of_an_si_pair_is_checked(text, expected):
    assert statuses(text, PHYSICS) == [("pair_direction", expected)]


@pytest.mark.parametrize("text", [
    "The ball falls from 0 m to 20 m below the top.",     # a verb of motion over positions
    "The lift rises from 2.0 m to 1.0 m below the roof.",
])
def test_a2_a_verb_of_motion_over_lengths_is_not_read_as_a_change(text):
    assert statuses(text, PHYSICS) == []


@pytest.mark.parametrize("text", ["The external resistance rises from 4.0 Ω to 2.4 Ω.", "The current from the cell falls from 2.7 A to 4.1 A."])
def test_a2_through_the_sciences_branch(text):
    _reply, rc = through_hub(text, "q", subject="Physics", agent="physics-specialist")
    assert any(f.code == "INT-SUBJ-001" and "pair_direction" in f.message for f in rc.findings)
    fixed = text.replace("rises", "falls") if "rises" in text else text.replace("falls", "rises")
    _reply, ok = through_hub(fixed, "q", subject="Physics", agent="physics-specialist")
    assert not [f for f in ok.findings if f.code == "INT-SUBJ-001"]
    assert not undecided_quant_statements(fixed, reading=PHYSICS)
