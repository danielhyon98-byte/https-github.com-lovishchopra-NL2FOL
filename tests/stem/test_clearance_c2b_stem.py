"""Round-9 clearance, second fix pass (arena round 9, integrated round c2): the STEM findings that still reproduced on the tree the first
pass left (docs/STEM_DESIGN.md, section 41), each fixed at its cause, with clean controls (correct working that must hold, with no error)
and negative controls (wrong working that must still be named):

* a markscheme code after one blank at the end of a line ('… = −6(x − 5) M1', then 'y = −3x + 17 A1') had been read as a factor, so the
  step between the two lines was never read and the mai-t15 slip written in plain text crossed with no check and no finding (rule
  mark-code); with it, the inverse of a defined function ('g⁻¹(x) = (x − 3)/2') is its definition, never a step (rule inverse-notation);
* a law evaluated on the next line with a rounded constant ('T² = 4π²r³/(GM)', then 'T² = (39.48)(…)/(…)') still failed at error
  severity when not every symbol had a stated value (X3a with only r stated, or none);
* a whole number converted limited no figure of the value stated for it, so '2 h = 7000 s' and '3 min = 200 s' held (rule
  converted-value, its stated side);
* an amount stated in words as the consequence of a balanced equation ('so 0.400 mol of N₂ gives 1.20 mol of NH₃') was set against nothing
  (rule mole-consequence);
* a list of results restated at the end of an answer was read by nothing, so a misread value crossed (rule result-list);
* 'Both values lie in 0 ≤ t ≤ 3.' had become a condition checked and named by nothing (the round-7 maa-t13 receipt lost two checks; rule
  values-in-interval);
* 'E = E_k + E_p = GMm/(2r) − GMm/r = −GMm/(2r)' failed at warning severity on correct work (ph-t14 s7.2; rule definition-substitution);
* a value written as a power of another base ('k = 2.0 × 40⁻¹ N m⁻¹') was said to be no stated value, and a request's constant stated
  again that way passed with no word; floor and ceiling brackets were withheld for a cut operand instead of being named;
* (resumed pass) binary digits grouped in threes ('110 101 011₂ = 653₈', correct) failed as an error, the last group read alone (rules
  octal-groups and cut-group).

The last section bounds the CPU time of the new readings on the standard hostile inputs of about 20,000 characters.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.stem import document as stem_document
from epinoic_logic.stem import relations as stem_relations
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.document import clear_document_cache
from epinoic_logic.translate.contracts import SuppliedText

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"round-9-clearance-c2b-stem-key-0123456789"
SUBJECTS = {"physics": "Physics", "mathematics_aa": "Mathematics: Analysis and Approaches", "mathematics_ai": "Mathematics: Applications and Interpretation",
            "chemistry": "Chemistry", "computer_science": "Computer Science", "biology": "Biology", "ess": "Environmental Systems and Societies"}
PHYS, AA, AI, CHEM, CS = "physics", "mathematics_aa", "mathematics_ai", "chemistry", "computer_science"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "stem"
ROUND9 = json.loads((FIXTURES / "round9" / "c2_answers.json").read_text(encoding="utf-8"))["answers"]
ROUND8 = json.loads((FIXTURES / "round8" / "c1_answers.json").read_text(encoding="utf-8"))["answers"]
R7 = json.loads((Path(__file__).parents[1] / "adapters" / "data" / "r7_specialists.json").read_text(encoding="utf-8"))["items"]


def receive(profile: str, answer: str, request: str = "Answer the question.", texts: tuple[str, ...] = ()):
    clear_document_cache()
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[profile], task_type="short_answer", selected_agent_ids=[agent]))
    supplied = [SuppliedText(document_id=f"peer:doc{i}", title="peer", text=t) for i, t in enumerate(texts)]
    m, _, _ = hub.dispatch("t", agent, request, supplied)
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    hub.close()
    return rc


def recorded9(tid: str, text: "str | None" = None):
    a = ROUND9[tid]
    peer = (a["peer_text"],) if a["peer_text"] else ()
    return receive(a["profile"], a["response_text"] if text is None else text, a["question"], peer)


def mutated9(tid: str, old: str, new: str):
    text = ROUND9[tid]["response_text"]
    assert text.count(old) == 1, old
    return recorded9(tid, text.replace(old, new))


def recorded8(tid: str):
    a = ROUND8[tid]
    peer = (ROUND8[a["peer"]]["response_text"],) if a["peer"] else ()
    return receive(a["profile"], a["response_text"], a["question"], peer)


def findings(rc) -> list:
    return list(rc.findings) + list(rc.structural_findings)


def errors(rc) -> list:
    return [(f.code, tuple(f.claim_ids)) for f in findings(rc) if f.severity == "error"]


def named(rc, code: str, claim: "str | None" = None) -> bool:
    return any(f.code == code and (claim is None or claim in f.claim_ids) for f in findings(rc))


def failed(rc) -> list[str]:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is False]


def held(rc) -> list[str]:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is True]


def subj_warnings(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-SUBJ-004"]


def messages(rc) -> list[str]:
    return [f"{f.severity} {f.code} {list(f.claim_ids)} {f.message[:200]}" for f in findings(rc)]


# ============================================================================== markscheme codes after one blank (rule mark-code)

MAI_Q = ROUND9["mai-t15"]["question"]


@pytest.mark.parametrize("answer,ok", [
    ("The line through (5, 2) with gradient −3 is y − 2 = −3(x − 5) M1\n\ny = −3x + 17 A1", True),
    ("The line through (5, 2) with gradient −3 is y − 2 = −6(x − 5) M1\n\ny = −3x + 17 A1", False),   # the mai-t15 slip in plain text
    ("The line through (5, 2) with gradient −3 is y − 2 = −6(x − 5) M1A1\n\ny = −3x + 17 A1", False),  # codes written with no blank
    ("The line through (5, 2) with gradient −3 is y − 2 = −6(x − 5) (M1)\n\ny = −3x + 17 (A1)", False),
])
def test_a_markscheme_code_after_one_blank_is_no_factor(answer, ok):
    """c2 communication-fidelity (isolated for mai-t15): the plain lines with 'M1'/'A1' after one blank carried no check and no finding:
    the codes had been read as factors (−6(x − 5)·M₁, −3x + 17·A₁), so the step between the lines was never read (rule mark-code)."""
    rc = receive(AI, answer, MAI_Q)
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


def test_a_symbol_spelled_like_a_code_stays_a_symbol():
    """Clean controls of rule mark-code: a resistor 'R1' the answer uses elsewhere, or the request names, is a symbol, not a mark; one code
    alone closes no line as a mark either."""
    elsewhere = "R1 = 4.0 Ω and I = 2.0 A.\nV = I R1\nV = 2.0 A × 4.0 Ω = 8.0 V"
    assert stem_document._mark_codes(elsewhere, "Find V.") == []
    asked = "V = I R1\nP = I² R1"
    assert stem_document._mark_codes(asked, "A current I flows through the resistor R1. Find V and P.") == []
    assert stem_document._mark_codes("V = I R1", "Find V.") == []  # a single code at a line's end is no list of marks
    marked = "y − 2 = −3(x − 5) M1\ny = −3x + 17 A1"
    assert [marked[a:b] for a, b in stem_document._mark_codes(marked, "Find the line.")] == ["M1", "A1"]
    after_operator = "y = 2 × M1\nz = 3 + A1"
    assert stem_document._mark_codes(after_operator, "Find y.") == []  # a code right after an operator is its operand
    rc = receive(PHYS, elsewhere, "Find V.")
    assert held(rc) and not failed(rc) and not errors(rc), messages(rc)


_R7_PROFILES = {"Mathematics: Analysis and Approaches": AA, "Physics": PHYS, "Chemistry": CHEM, "Biology": "biology", "Computer Science": CS,
                "Mathematics: Applications and Interpretation": AI, "Environmental Systems and Societies": "ess"}
_RECORDED = ([(k, v["response_text"], v["question"], v["profile"]) for k, v in ROUND9.items()]
             + [(k, v["response_text"], v["question"], v["profile"]) for k, v in ROUND8.items()]
             + [(k, v["response_text"], v["question"], _R7_PROFILES[v["subject"]]) for k, v in R7.items() if v["subject"] in _R7_PROFILES])


@pytest.mark.parametrize("tid,text,question,profile", _RECORDED, ids=[r[0] for r in _RECORDED])
def test_the_markscheme_codes_change_no_statement_of_a_recorded_answer(tid, text, question, profile, monkeypatch):
    """Rule mark-code blanks the codes in the view the maths runs are found in only: the statements, the claims cut from them and their ids
    are what they were (a code blanked in the statements' view had merged 'A1' after '(3 s.f.)' into the sentence before it in mai-t14, and
    a code after two blanks had joined its statement, so recorded translations no longer matched their claims)."""
    clear_document_cache()
    with_rule = [(st.id, build_document(text, question, profile).statement_text(st.id)) for st in build_document(text, question, profile).statements]
    monkeypatch.setattr(stem_document, "_mark_codes", lambda reading, request: [])
    clear_document_cache()
    doc = build_document(text, question, profile)
    assert with_rule == [(st.id, doc.statement_text(st.id)) for st in doc.statements]
    clear_document_cache()


def test_the_inverse_of_a_defined_function_is_its_definition():
    """Rule inverse-notation: once 'M1A1' after 'g⁻¹(x) = (x − 3)/2' was no factor (rule mark-code), the line, read as the product g⁻¹·x, was
    decided as a step from 'x = (y − 3)/2' and failed for a renaming (INT-SUBJ-001 on maa-t15's correct part 2(b)). The inverse of a
    function the text defines states the inverse's definition."""
    for tid in ("maa-t15", "maa-t15-revised"):
        rc = recorded9(tid)
        assert not [e for e in errors(rc) if e[0] == "INT-SUBJ-001"], messages(rc)
    rc = receive(AA, "Let y = 2x + 3. Then x = (y − 3)/2, so\ng⁻¹(x) = (x − 3)/2", "Let g(x) = 2x + 3. Find g⁻¹(x).")
    assert not errors(rc) and not failed(rc), messages(rc)
    wrong = receive(AA, "Let y = 2x + 3. Then x = (y + 3)/2, so\ng⁻¹(x) = (x + 3)/2", "Let g(x) = 2x + 3. Find g⁻¹(x).")
    assert named(wrong, "INT-SUBJ-001"), messages(wrong)  # the rearrangement before it is still a step


# ============================================================================== a law evaluated on the next line (X3a, every binding state)

ORBIT = ("A satellite orbits a planet of mass 6.4 × 10²³ kg at a radius of 5.000 × 10⁶ m. G = 6.67 × 10⁻¹¹ N m² kg⁻². (b) Calculate the period T "
         "of the orbit.")
LAW = "T² = 4π²r³/(GM)\nT² = (39.48)(1.250 × 10²⁰ m³)/(4.2688 × 10¹³ N m² kg⁻¹) = 1.156 × 10⁸ s²\n"


@pytest.mark.parametrize("givens", ["r = 5.000 × 10⁶ m\n\n(b) [3]\n", "(b) [3]\n", "M = 6.4 × 10²³ kg\nr = 5.000 × 10⁶ m\n\n"])
def test_a_law_evaluated_with_a_rounded_constant_is_no_exact_step_whatever_is_bound(givens):
    """c1 communication-fidelity#1 carried: the variants with only r bound, or with nothing bound, still failed as an exact algebra step
    (r = 77109375000/667). The line is the law evaluated at the values it writes: a symbol with no stated value is named undecided
    (ST-UNDEC-002), never left free in an exact step."""
    rc = receive(PHYS, givens + LAW, ORBIT)
    assert not errors(rc) and not [c for c in rc.formal_checks if c.constraint_id.startswith("stem-alg") and c.satisfied is False], messages(rc)
    if "M =" not in givens:
        assert named(rc, "ST-UNDEC-002"), messages(rc)
    wrong = receive(PHYS, givens + LAW.replace("= 1.156 × 10⁸ s²", "= 1.256 × 10⁸ s²"), ORBIT)
    assert named(wrong, "INT-SUBJ-001"), messages(wrong)  # the written arithmetic is still checked


# ============================================================================== a whole number converted (rule converted-value)

@pytest.mark.parametrize("line,ok", [("2 h = 7200 s", True), ("2 h = 7000 s", False), ("3 min = 180 s", True), ("3 min = 200 s", False),
                                     ("1 km = 1000 m", True), ("5 km = 5000 m", True), ("1 day = 86400 s", True),
                                     ("100 km h⁻¹ = 30 m s⁻¹", True), ("2.0 h = 7200 s", True)])
def test_a_whole_number_converted_limits_no_figure_of_the_value_stated_for_it(line, ok):
    """c2 stem-integration (conversion band): '2 h = 7000 s' and '3 min = 200 s' held, the stated value's trailing zeros read as not
    significant (a band of 500 s and 50 s). The whole number converted is exact, so every written digit of the value stated for it
    counts; a converted value written with its own trailing zeros ('100 km h⁻¹') still limits them."""
    rc = receive(PHYS, line)
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


# ============================================================================== an amount stated in words after an equation (rule mole-consequence)

@pytest.mark.parametrize("answer,ok", [
    ("N₂ + 3H₂ → 2NH₃, so 0.400 mol of N₂ gives 0.800 mol of NH₃.", True),
    ("N₂ + 3H₂ → 2NH₃, so 0.400 mol of N₂ gives 1.20 mol of NH₃.", False),  # the lens's prose consequence
    ("N₂ + 3H₂ → 2NH₃. So 0.400 mol of N₂ reacts with 1.20 mol of H₂.", True),
    ("N₂ + 3H₂ → 2NH₃. So 0.400 mol of N₂ reacts with 0.800 mol of H₂.", False),
    ("2H₂ + O₂ → 2H₂O, so 4.0 mol of H₂ forms 4.0 mol of H₂O.", True),
])
def test_an_amount_stated_as_the_consequence_of_an_equation_is_set_against_it(answer, ok):
    """c2 stem-integration (mole ratios): 'so 0.400 mol of N₂ gives 1.20 mol of NH₃' crossed with only the equation's balance held. Which
    equation the amounts follow is a reading, so a wrong amount is a warning (rule mole-consequence)."""
    rc = receive(CHEM, answer)
    assert any(c.constraint_id.startswith("stem-eq") for c in rc.formal_checks), messages(rc)
    if ok:
        assert not failed(rc) and not subj_warnings(rc) and not errors(rc), messages(rc)
    else:
        assert failed(rc) and subj_warnings(rc) and not errors(rc), messages(rc)


# ============================================================================== a list of results (rule result-list)

@pytest.mark.parametrize("old,new,claim", [("Made from 30.00 cm³ of stock: 0.590", "Made from 30.00 cm³ of stock: 0.509", "s14.5"),
                                           ("Stock solution: 0.984", "Stock solution: 0.948", "s14.2"),
                                           ("Made from 10.00 cm³ of stock: 0.197", "Made from 10.00 cm³ of stock: 0.179", "s14.3")])
def test_a_misread_line_of_a_result_list_is_named(old, new, claim):
    """c2 adversarial-live (ch-p9b-summary-misread): 'Made from 30.00 cm³ of stock: 0.509' after the working's 0.590 crossed with no check
    and no finding. A line of the list restates the result its label names (the line of working its figure opens, or the symbol whose
    bracket holds its word); which result that is, is a reading, so a misread value is a warning."""
    rc = mutated9("ch-p9b", old, new)
    assert any(f.code == "INT-SUBJ-004" and claim in f.claim_ids for f in rc.findings), messages(rc)
    assert not [e for e in errors(rc) if e[0] == "INT-SUBJ-001"], messages(rc)


def test_the_result_list_of_the_recorded_answer_holds():
    rc = recorded9("ch-p9b")
    lists = [c for c in rc.formal_checks if c.constraint_id.startswith("stem-res") and c.satisfied]
    assert len(lists) >= 5 and not subj_warnings(rc) and not errors(rc), messages(rc)


def test_a_lone_label_line_restates_nothing():
    """Clean control: 'Answer: 6.0 minutes.' and a single 'label: value' line are no result list."""
    rc = receive(PHYS, "a = (20 − 0)/4.0 = 5.0 m s⁻²\nResult: 5.0")
    assert not subj_warnings(rc) and not errors(rc), messages(rc)


# ============================================================================== values that lie in an interval (rule values-in-interval)

MAA_T13 = R7["maa-t13"]


def test_the_values_a_sentence_places_in_an_interval_are_checked():
    """Overseer handoff (STEM owner): rule part-condition for order relations made 'Both values lie in 0 ≤ t ≤ 3.' a condition checked and
    named by nothing, so maa-t13's receipt had 14 formal checks where the round-7 record has 16. Each order is checked for every root
    the part states (0 and 2)."""
    rc = receive(AA, MAA_T13["response_text"], MAA_T13["question"])
    interval = [c for c in rc.formal_checks if c.constraint_id.startswith("stem-cmp") and "m2.5" in c.claim_ids]
    assert len([c for c in rc.formal_checks if c.formal_result_id]) == 16 and not failed(rc), messages(rc)
    assert len(interval) == 2 and all(c.satisfied for c in interval), [(c.constraint_id, c.claim_ids) for c in rc.formal_checks]
    wrong = receive(AA, MAA_T13["response_text"].replace("Both values lie in 0 ≤ t ≤ 3.", "Both values lie in 0 ≤ t ≤ 1."), MAA_T13["question"])
    assert named(wrong, "INT-SUBJ-001"), messages(wrong)  # 2 is no value of [0, 1]


def test_a_condition_stays_a_condition():
    """Clean control: 'need Δ > 0' (maa-t15) and an inequality no sentence places values in stay conditions."""
    rc = recorded9("maa-t15")
    assert not errors(rc), messages(rc)


# ============================================================================== definitions put in (rule definition-substitution)

def test_expressions_put_in_for_symbols_defined_nowhere_are_no_identity():
    """c1 stem-integration#2 carried: ph-t14 s7.2 'E = E_k + E_p = GMm/(2r) − GMm/r = −GMm/(2r)' failed at warning severity (r = 0: E_k and
    E_p defined nowhere). The first link puts in their definitions; the link after it is an identity and stays checked."""
    rc = recorded8("ph-t14")
    assert not [f for f in subj_warnings(rc) if "s7.2" in f.claim_ids] and not errors(rc), messages(rc)
    request = "A satellite of mass m orbits a planet of mass M at radius r. Find its total energy."
    wrong = receive(PHYS, "For a circular orbit the total energy is E = E_k + E_p = GMm/(2r) − GMm/r = −GMm/r.", request)
    assert named(wrong, "INT-SUBJ-001"), messages(wrong)  # the wrong simplification
    right = receive(PHYS, "For a circular orbit the total energy is E = E_k + E_p = GMm/(2r) − GMm/r = −GMm/(2r).", request)
    assert held(right) and not failed(right) and not errors(right), messages(right)


# ============================================================================== values written as powers of other bases; floor brackets

def test_a_value_written_with_a_power_of_another_base_is_named_truthfully():
    """c1 stem-integration#25 (b) carried: 'k = 2.0 × 40⁻¹ N m⁻¹' then 'F = k × 3.0 m = 5.0 N' was named ST-UNDEC-002 'k has no stated value';
    the finding now names the expression k is stated as. 'G = 6.67 × 40⁻¹¹ N m² kg⁻²' beside the request's G passed with no word: it is
    named as a rebinding is."""
    rc = receive(PHYS, "k = 2.0 × 40⁻¹ N m⁻¹\nF = k × 3.0 m = 5.0 N", "A spring is stretched by 3.0 m. Find F.")
    undecided = [f for f in findings(rc) if f.code == "ST-UNDEC-002"]
    assert undecided and all("no stated value" not in f.message and "written expression" in f.message for f in undecided), messages(rc)
    request = ("The planet has a mass of 6.4 × 10²³ kg and a radius of 3400 km. G = 6.67 × 10⁻¹¹ N m² kg⁻². Calculate the gravitational field "
               "strength at the surface.")
    rc = receive(PHYS, "G = 6.67 × 40⁻¹¹ N m² kg⁻²\ng = GM/r² = 6.67 × 10⁻¹¹ × 6.4 × 10²³ ÷ (3.4 × 10⁶)² = 3.7 N kg⁻¹", request)
    assert named(rc, "ST-SCOPE-001"), messages(rc)


def test_floor_and_ceiling_brackets_are_named_for_the_notation():
    """c2 stem-integration (floor and ceiling): '⌊log₂ 7⌋ + 1 = 6' was withheld as an operand '+ 1' cut from a longer expression; the
    brackets are notation outside the grammar and the relation is named for it."""
    for answer in ("⌊log₂ 7⌋ + 1 = 6", "⌈7 / 2⌉ = 4"):
        rc = receive(CS, answer, "How many bits are needed?")
        notes = [f for f in findings(rc) if f.code == "ST-PARSE-001"]
        assert notes and any("floor and ceiling" in f.message for f in notes) and not errors(rc), messages(rc)


# ============================================================================== bounds on hostile input

_N = 20_000
STANDARD = {
    "blanks": " " * _N + "x", "tabs": "\t" * _N + "x", "line breaks": "\n" * _N + "x", "stops": "." * _N + "x",
    "closing marks": ")" * (_N // 2) + "]" * (_N // 2) + "x", "mark labels": "x = 5" + " (A1)" * (_N // 5) + " z",
    "parentheses": "(" * _N + "x", "brackets": "[" * _N + "x", "fence openers": "```\n" * (_N // 4) + "x",
    "number words": "one and " * (_N // 8) + "x", "= links": "x = " * (_N // 4) + "!", "list markers": "- " * (_N // 2) + "!",
}
NEW_SHAPES = {
    "one-blank codes": "y = 2x + 1 M1\n" * (_N // 14) + "x",
    "glued codes": "y = 2x + 1 " + "M1A1" * (_N // 4) + "x",
    "codes after blanks": "y = 2x M1" + " " * _N + "A1x",
    "mole consequences": "N₂ + 3H₂ → 2NH₃\n" + "so 0.400 mol of N₂ gives 1.20 mol of NH₃ " * (_N // 42) + "!",
    "mole blanks": "N₂ + 3H₂ → 2NH₃\n0.4 mol" + " " * _N + "of N₂ gives!",
    "result lists": "30.00 cm³: 0.98 × (30.00 ÷ 50.00) = 0.59 mol dm⁻³\nResults, in mol dm⁻³:\n" + "Made from 30.00 cm³ of stock: 0.590\n" * (_N // 36),
    "long labels": "Results:\n" + ("a" * 79 + ": 1\n") * (_N // 83),
    "values in intervals": "3t(2 − t) = 0\nt = 0 or t = 2\n" + "Both values lie in 0 ≤ t ≤ 3.\n" * (_N // 31),
    "inverse notation": "Let y = 2x + 3. Then x = (y − 3)/2, so\n" + "g⁻¹(x) = (x − 3)/2\n" * (_N // 20),
    "definitions put in": "E = " + "E_k + E_p = GMm/(2r) − GMm/r = " * (_N // 32) + "x",
    "floor brackets": "⌊" * _N + "x = 2",
    "written expressions": "k = 2.0 × 40⁻¹ N m⁻¹\n" * (_N // 21) + "F = k × 3.0 m = 5.0 N",
}


@pytest.mark.parametrize("name", sorted(STANDARD) + sorted(NEW_SHAPES))
@pytest.mark.parametrize("profile", [PHYS, AA, CHEM, CS])
def test_the_new_readings_are_bounded_on_hostile_input(name, profile):
    text = STANDARD.get(name) or NEW_SHAPES[name]
    clear_document_cache()
    t0 = time.process_time()
    doc = build_document(text, "Let g(x) = 2x + 3. Calculate x. N₂ + 3H₂ → 2NH₃.", profile)
    build_checks(doc, report_id="r", request_id="q")
    assert time.process_time() - t0 < 8.0, name


@pytest.mark.parametrize("name", sorted(STANDARD) + sorted(NEW_SHAPES))
def test_the_new_entry_points_are_linear(name):
    """The new readers' own entry points on each hostile input: the markscheme codes of a text (one read of each line from its end), a
    function glued to a bracket in the request (bounded occurrences) and the patterns of the new rules (bounded or possessive runs)."""
    text = STANDARD.get(name) or NEW_SHAPES[name]
    t0 = time.process_time()
    stem_document._mark_codes(text, text)
    stem_relations._applied_in(text, "g")
    for pattern in (stem_relations._MOLE_CONSEQUENCE_RE, stem_relations._VALUES_LIE_RE, stem_relations._LABEL_FIGURE_RE):
        for _m in pattern.finditer(text):
            pass
    for line in text.split("\n")[:4096]:
        stem_relations._RESULT_LINE_RE.fullmatch(line[:400])
        stem_relations._LEAD_FIGURE_RE.match(line[:400])
    assert time.process_time() - t0 < 2.0, name


# ============================================================================== binary digits grouped in threes (rules octal-groups and cut-group)

@pytest.mark.parametrize("answer,ok", [("110 101 011₂ = 653₈", True), ("1 101 011₂ = 153₈", True), ("11 010₂ = 26", True),
                                       ("110 101 011₂ = 652₈", False)])
def test_binary_digits_grouped_in_threes_with_their_subscript_are_one_numeral(answer, ok):
    """Found while re-checking the thousands-space findings: '110 101 011₂ = 653₈' (correct: 110 101 011₂ is 427, as 653₈ is) failed as an
    error, the last group '011₂' alone set against 653₈ (c = 3). Binary digits in groups of three with the binary subscript are one numeral
    (rule octal-groups), as groups of four already were; a wrong octal value still fails."""
    rc = receive(CS, answer, "Convert the binary numeral to octal.")
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001", "c1.1"), messages(rc)


def test_a_conversion_of_a_cut_digit_group_is_never_checked():
    """Rule cut-group: with no subscript, '110 101 011 = 653 in octal' set the last group, read as eleven, against 653₈ (a false
    INT-SUBJ-001, c = 11). A numeral that a blank and more digits adjoin is never read in part by rule prose-base: no conversion is
    checked, and the relation sign is named (ST-PARSE-001). The prose form with no digit group before it is still checked."""
    rc = receive(CS, "Group the bits in threes: 110 101 011 = 653 in octal", "Convert 110101011 in binary to octal.")
    assert not errors(rc) and not failed(rc) and named(rc, "ST-PARSE-001"), messages(rc)
    whole = receive(CS, "In binary, 110101011 = 653 in octal", "Convert 110101011 in binary to octal.")
    assert held(whole) and not errors(whole), messages(whole)
    wrong = receive(CS, "In binary, 110101011 = 652 in octal", "Convert 110101011 in binary to octal.")
    assert named(wrong, "INT-SUBJ-001"), messages(wrong)


_GROUP_SHAPES = {
    "bits in threes": "110 " * 5000 + "₂ = 1",
    "bit groups then subscript": "1 " + "010 " * 4999 + "₂ = 1",
    "cut groups": "1 0 " * 5000 + "= 653 in octal",
    "groups before a base word": "101 " * 4990 + "= 5 in octal",
}


@pytest.mark.parametrize("name", sorted(_GROUP_SHAPES))
@pytest.mark.parametrize("profile", [PHYS, AA, CHEM, CS])
def test_the_bit_group_readers_are_bounded_on_hostile_input(name, profile):
    """Rule octal-groups is the lexer's bounded pattern (at most eleven groups, read within 160 characters) and rule cut-group looks two
    characters each way: about 20,000 characters of bit groups and digit groups, through the whole document and its checks, stay far
    inside the bound."""
    text = _GROUP_SHAPES[name]
    clear_document_cache()
    t0 = time.process_time()
    doc = build_document(text, "Answer the question.", profile)
    build_checks(doc, report_id="r", request_id="q")
    assert time.process_time() - t0 < 8.0, name


# ============================================================================== a relation whose left side no run reads (rule unread-left-side)

@pytest.mark.parametrize("answer", ["1 000 000 bits ÷ 8 = 125 000 bytes", "2 000 000 bits ÷ 8 = 350 000 bytes", "x: 2 000 000 bits ÷ 8 = 250 000 bytes"])
def test_a_relation_whose_left_side_no_run_reads_is_named(answer):
    """Found while re-checking the CS data-unit findings (c2 stem-integration; c2 communication-fidelity: never drop a recognised relation
    without ST-UNDEC/ST-PARSE): in Computer Science, where binary-looking digit groups are no numeral, '2 000 000 bits ÷ 8 = 350 000 bytes'
    was read from its relation sign on, as a line continuing no chain, and dropped with no check and no finding, so a wrong value crossed.
    The left side is written but not read: ST-PARSE-001 names the relation."""
    rc = receive(CS, answer)
    assert not errors(rc) and any(f.code == "ST-PARSE-001" and "left side is not read" in f.message for f in findings(rc)), messages(rc)


@pytest.mark.parametrize("profile,answer", [
    (CS, "2000000 bits ÷ 8 = 250000 bytes"),                                                          # read whole: checked, as before
    (CHEM, "percentage yield = actual yield ÷ theoretical yield × 100 = 150 cm³ ÷ 1000 cm³ × 100 = 15.0%"),  # its working is checked
    (AI, "(e) Distance to A $= \\sqrt{(5 - 2)^2 + (5 - 1)^2} = \\sqrt{25} = 5$ km"),                    # a labelled line
])
def test_a_line_whose_run_is_read_or_labelled_draws_no_unread_left_side(profile, answer):
    rc = receive(profile, answer)
    assert held(rc) and not failed(rc) and not any("left side is not read" in f.message for f in findings(rc)), messages(rc)


def test_the_unread_left_side_rule_is_bounded_on_hostile_input():
    """The rule reads at most 160 characters before the sign of each such run: lines of digit groups and relation signs of about 20,000
    characters stay far inside the bound through the whole document and its checks."""
    for text in ("1 000 000 bits ÷ 8 = 125 000 bytes\n" * 570, "1 0 = " * 3300 + "1", "1 000 " * 3300 + "= 5"):
        for profile in (CS, PHYS):
            clear_document_cache()
            t0 = time.process_time()
            build_checks(build_document(text, "Answer the question.", profile), report_id="r", request_id="q")
            assert time.process_time() - t0 < 8.0, (profile, text[:20])
