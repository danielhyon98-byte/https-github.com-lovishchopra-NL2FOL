"""Integration gate 3 (before arena round 8): the STEM findings of the independent lenses, each reproduced through the hub and fixed
at its cause, with clean controls (correct working that must hold and wrong working that must still fail). docs/STEM_DESIGN.md,
section 37.

* emphasis markers are layout, never operators (rule emphasis-layout): working wrapped in '**', '*', '__', '_', '***' or '___', or with
  only its result so wrapped, is checked as the line without them, struck text ('~~5.0~~') is read as deleted, and a claim written
  without the markers still offers its words to the coverage heuristic (no INT-REQ-004);
* a middle dot between two digits with no blank ('5·0', '3·5') is read as a decimal point and as a product (rule middle-dot): an error
  only when every reading fails, a warning when the readings disagree, nothing when both hold;
* the fullwidth and small forms of the relation signs and operators are the signs they stand for, and every other mathematical sign the
  grammar does not read keeps its relation undecided (ST-PARSE-001) instead of cutting it into a fragment that is checked or dropped
  (rule sign-forms);
* a value the answer tests, rejects or accepts after 'so' restates no result of the chain before it (rule tested-value).

The last section bounds the CPU time of the new readings on hostile input of about 20,000 characters.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.gate import assess_response
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_overseer import EngineKey, KeyRing, TransferAuditor
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.document import ambiguous_dots, clear_document_cache
from epinoic_logic.stem.hub_hooks import STEM_HOOKS
from epinoic_logic.stem.lexer import is_sign_error, lex, sign_outside_grammar
from epinoic_logic.stem.normalize import SIGN_FORMS, reading_view
from epinoic_logic.stem.spans import find_spans
from epinoic_logic.stem.limits import profile_for

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"integration-gate-3-stem-key-0123456789"
SUBJECTS = {"physics": "Physics", "mathematics_aa": "Mathematics: Analysis and Approaches", "chemistry": "Chemistry",
            "computer_science": "Computer Science"}
PHYS, AA = "physics", "mathematics_aa"
TROLLEY = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."
FIND_X = "Find x = 3 + 4."
SQRT = "Solve √(x + 3) = x − 3."


def receive(profile: str, answer: str, request: str = "Answer the question."):
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[profile], task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def failed(rc) -> set[str]:
    return {c.constraint_id for c in rc.formal_checks if c.satisfied is False}


def held(rc) -> set[str]:
    return {c.constraint_id for c in rc.formal_checks if c.satisfied is True}


def codes(rc) -> list[str]:
    return [f.code for f in rc.findings]


def structural(rc) -> list[str]:
    return [f.code for f in rc.structural_findings]


def message(rc, code: str) -> str:
    return " ".join(f.message for f in rc.findings if f.code == code)


def errors(rc) -> list[str]:
    return [f.code for f in list(rc.findings) + list(rc.structural_findings) if f.severity == "error"]


# ============================================================================================ major 1: rule emphasis-layout
@pytest.mark.parametrize("answer", [
    "u = 0.\n\n**a = (20 - 0)/4.0 = 6.0 m s⁻²**",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = **6.0 m s⁻²**.",
    "The trolley starts from rest, so u = 0. *a = (20 - 0)/4.0 = 6.0 m s⁻²*",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = *6.0 m s⁻²*.",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = __6.0 m s⁻²__.",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = _6.0 m s⁻²_.",
    "The trolley starts from rest, so u = 0. _a = (20 - 0)/4.0 = 6.0 m s⁻²_",
    # the class: bold italic and strikethrough (the struck value goes with its markers)
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = ***6.0 m s⁻²***.",
    "The trolley starts from rest, so u = 0. ***a = (20 - 0)/4.0 = 6.0 m s⁻²***",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = ___6.0 m s⁻²___.",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = ~~5.0~~ 6.0 m s⁻²",
])
def test_working_wrapped_in_emphasis_is_checked_and_its_wrong_step_named(answer):
    rc = receive(PHYS, answer, TROLLEY)
    assert "stem-eq-1" in failed(rc) and "INT-SUBJ-001" in codes(rc), (answer, rc.formal_checks, codes(rc), structural(rc))
    assert "c = 5, r = 6" in message(rc, "INT-SUBJ-001")
    assert "ST-PARSE-001" not in structural(rc)


@pytest.mark.parametrize("answer", [
    "u = 0.\n\n**a = (20 - 0)/4.0 = 5.0 m s⁻²**",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = **5.0 m s⁻²**.",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = _5.0 m s⁻²_.",
    "The trolley starts from rest, so u = 0. *a = (20 - 0)/4.0 = 5.0 m s⁻²*",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = ***5.0 m s⁻²***.",
    "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = ~~6.0~~ 5.0 m s⁻²",
])
def test_correct_working_wrapped_in_emphasis_holds_and_is_covered(answer):
    rc = receive(PHYS, answer, TROLLEY)
    assert "stem-eq-1" in held(rc) and not failed(rc) and not errors(rc), (answer, rc.formal_checks, codes(rc))
    assert "INT-REQ-004" not in codes(rc), codes(rc)  # the claim, written without its markers, still names the acceleration
    assert rc.status.value == "ACCEPTED"


@pytest.mark.parametrize("answer", ["**x = 3 + 4 = 8**", "**Answer: x = 3 + 4 = 8**", "x = 3 + 4 = **8**", "*x = 3 + 4 = 8*"])
def test_bold_mathematics_working_is_named(answer):
    rc = receive(AA, answer, FIND_X)
    assert "stem-eq-1" in failed(rc) and "c = 7, r = 8" in message(rc, "INT-SUBJ-001"), (answer, rc.formal_checks, codes(rc))


@pytest.mark.parametrize("answer", ["**x = 3 + 4 = 7**", "x = 3 + 4 = **7**", "x = 3 + 4 = __7__."])
def test_bold_correct_mathematics_holds(answer):
    rc = receive(AA, answer, FIND_X)
    assert "stem-eq-1" in held(rc) and not failed(rc) and not errors(rc), (answer, rc.formal_checks, codes(rc))


@pytest.mark.parametrize("answer, value", [("x = 2**3 = 8", "8"), ("x = 2 ** 3 = 8", "8"), ("x = 2**3 = 9", "9")])
def test_a_power_written_with_two_stars_is_still_a_power(answer, value):
    rc = receive(AA, answer, "Find x = 2³.")
    assert ("stem-eq-1" in held(rc)) == (value == "8") and ("stem-eq-1" in failed(rc)) == (value == "9"), (answer, rc.formal_checks)


def test_emphasis_is_recorded_apart_and_blanked_one_for_one():
    text = "So **a = 20/4.0 = 5.0 m s⁻²** and _b = 2_; $x_1 = 3$ and `code_with_under_scores_` stay, ***c*** and ~~d = 4~~ too."
    sp = find_spans(text, profile=profile_for(PHYS))
    marked = [text[a:b] for a, b in sp.emphasis]
    assert marked == ["**", "**", "_", "_", "***", "***", "~~d = 4~~"], marked
    assert [text[a:b] for a, b in sp.markup] == ["**", "**", "***", "***"]  # a claim keeps '_' pairs and struck text
    doc = build_document(text, "Find a.", PHYS)
    assert len(doc.reading) == len(text) and "**" not in doc.reading and "_b" not in doc.reading
    assert "x_1" in doc.reading and "code_with_under_scores_" in doc.reading  # LaTeX subscripts and code are no emphasis
    assert len(doc.operand_view) == len(text) and "*" not in doc.operand_view


def test_a_claim_written_without_its_markup_is_located_in_the_answer():
    text = "Intro **bold** text. a = (20 - 0)/4.0 = **6.0 m s⁻²**. End *it* here."
    doc = build_document(text, "Find a.", PHYS)
    at, end = doc.locate("a = (20 - 0)/4.0 = 6.0 m s⁻².")
    assert text[at:end] == "a = (20 - 0)/4.0 = **6.0 m s⁻²**."
    assert doc.locate("End it here.") is not None and doc.locate("nowhere") is None
    terms = STEM_HOOKS.coverage_terms("a = (20 - 0)/4.0 = 6.0 m s⁻².", text, "Find a.", PHYS)
    assert "acceleration" in terms and "calculate" in terms


# ============================================================================================ major 2: rule middle-dot
def test_correct_british_decimal_working_is_never_an_error():
    rc = receive(PHYS, "The trolley starts from rest. a = 20/4.0 = 5·0 m s⁻².", TROLLEY)
    assert not errors(rc) and "INT-SUBJ-001" not in codes(rc), (rc.formal_checks, codes(rc))
    assert "stem-eq-1d" in held(rc)  # some reading holds: no error
    assert "stem-eq-1" in failed(rc) and "INT-SUBJ-004" in codes(rc)  # the readings disagree: a warning


def test_wrong_british_decimal_working_is_not_shown_as_entailed():
    rc = receive(PHYS, "The trolley starts from rest. a = 20/4·0 = 6·0 m s⁻².", TROLLEY)
    assert "stem-eq-1" in failed(rc) and "stem-eq-1" not in held(rc), rc.formal_checks  # 20/4.0 = 6.0 fails as decimals
    assert "INT-SUBJ-004" in codes(rc)
    assert rc.status.value != "ACCEPTED"


def test_working_that_fails_under_every_reading_of_the_dot_is_an_error():
    rc = receive(PHYS, "The trolley starts from rest. a = 20/4.0 = 6·0 m s⁻².", TROLLEY)  # 5 = 6.0 fails, and 5 = 0 too
    assert {"stem-eq-1", "stem-eq-1d"} <= failed(rc) and "INT-SUBJ-001" in codes(rc), (rc.formal_checks, codes(rc))


def test_british_decimal_working_that_holds_both_ways_is_clean():
    rc = receive(PHYS, "The trolley starts from rest. a = 20/4·0 = 5·0 m s⁻².", TROLLEY)  # 20/4.0 = 5.0, and (20/4)·0 = 5·0 = 0
    assert {"stem-eq-1", "stem-eq-1d"} <= held(rc) and not failed(rc), rc.formal_checks


@pytest.mark.parametrize("answer, wrong", [("x = 3·5 + 4 = 7·5", False), ("x = 3·5 + 4 = 8·5", True)])
def test_mathematics_with_the_raised_decimal_point(answer, wrong):
    rc = receive(AA, answer, FIND_X)
    assert not ("INT-SUBJ-001" in codes(rc)) or wrong, (answer, rc.formal_checks, codes(rc))
    assert ("stem-eq-1d" in failed(rc)) == wrong, rc.formal_checks


def test_a_product_written_with_a_raised_dot_between_digits_is_never_an_error():
    rc = receive(AA, "x = 2·3 = 6", "Find x = 2 × 3.")
    assert not errors(rc) and "stem-eq-1d" in held(rc), (rc.formal_checks, codes(rc))


@pytest.mark.parametrize("text, expected", [
    ("5·0", (1,)), ("a = 20/4·0 = 6·0 m s⁻²", (8, 14)), ("3·5 + 4 = 7·5", (1, 11)), ("6·02×10²³", (1,)),
    ("4·10³", ()), ("6·10^23", ()), ("2·10**5", ()), ("1.2·10^{-3}", ()), ("CuSO4·5H2O", ()), ("1·2·3", ()), ("1·2.5", ()),
    ("2 · 3", ()), ("x·2", ()), ("2·x", ()), ("5⋅0", ()), ("5∙0", ()),
])
def test_which_middle_dots_are_ambiguous(text, expected):
    assert ambiguous_dots(text) == expected


def test_the_dual_problems_are_valid_ir_and_name_both_readings():
    doc = build_document("a = 20/4·0 = 6·0 m s⁻²", TROLLEY, PHYS)
    plan = build_checks(doc, report_id="r", request_id="q")
    ids = {c.check_id: c for c in plan.checks}
    assert set(ids) == {"stem-eq-1", "stem-eq-1d"}, ids
    for c in plan.checks:
        Problem.model_validate(c.problem)
        names = {s["name"] for s in c.problem["symbols"]}
        assert any(n.startswith("d_") for n in names) and any(n.startswith("p_") for n in names), names
        assert "rule middle-dot" in c.description and c.problem["notes"].startswith("STEM check")
    assert ids["stem-eq-1"].failure_severity == "warning" and ids["stem-eq-1d"].failure_severity == "error"


def test_a_substitution_through_a_raised_decimal_point_is_a_warning_at_most():
    rc = receive(PHYS, "t = 4·0 s. a = v/t = 20/5·0 = 4·0 m s⁻².", TROLLEY)
    assert "INT-SUBJ-001" not in [f.code for f in rc.findings if "stem-sub" in f.message], [(f.code, f.message[:120]) for f in rc.findings]


def test_a_given_written_with_the_raised_decimal_point():
    ok = receive(PHYS, "Given: u = 0, v = 20 m s⁻¹, t = 4·0 s.\na = (v − u)/t = 20/4·0 = 5·0 m s⁻².", TROLLEY)
    # before, '4·0 s' was a product, no value: the Given t was not set against the request and the substitution was undecided
    assert ok.status.value == "ACCEPTED" and not failed(ok) and "ST-UNDEC-002" not in structural(ok), (ok.formal_checks, codes(ok))
    assert any(c.startswith("stem-giv") for c in held(ok)) and any(c.startswith("stem-sub") for c in held(ok)), ok.formal_checks
    bad = receive(PHYS, "Given: u = 0, v = 20 m s⁻¹, t = 5·0 s.\na = (v − u)/t = 20/4·0 = 5·0 m s⁻².", TROLLEY)
    assert any(c.startswith("stem-giv") for c in failed(bad)) and "INT-SUBJ-004" in codes(bad), (bad.formal_checks, codes(bad))


def test_a_prose_value_written_with_the_raised_decimal_point():
    request = "A trolley accelerates uniformly from rest to 23.2 m s⁻¹ in 4.0 s. Calculate its acceleration."
    ok = receive(PHYS, "The trolley starts from rest. a = 23.2/4.0 = 5.8 m s⁻². The acceleration is therefore 5·8 m s⁻².", request)
    # before, the prose read the integer part alone ('5') and the correct restatement was INT-SUBJ-001 (c = 29/5, r = 5)
    assert not failed(ok) and not errors(ok) and any(c.startswith("stem-res") for c in held(ok)), (ok.formal_checks, codes(ok))
    bad = receive(PHYS, "The trolley starts from rest. a = 23.2/4.0 = 5.8 m s⁻². The acceleration is therefore 6·8 m s⁻².", request)
    assert any(c.startswith("stem-res") for c in failed(bad)) and "INT-SUBJ-004" in codes(bad) and not errors(bad), (bad.formal_checks, codes(bad))


def test_an_explicit_product_keeps_its_reading():
    rc = receive(PHYS, "F = 2.0 · 3.0 = 6.0 N", "A force of 2.0 N acts three times. Calculate F.")
    assert "stem-eq-1" in held(rc) and "stem-eq-1d" not in held(rc) | failed(rc), rc.formal_checks


# ============================================================================================ major 3: rule sign-forms
#: integration gate 4 (rule sign-forms in every category): the equals signs of other categories, U+1F7F0 HEAVY EQUALS SIGN and U+A78A
#: MODIFIER LETTER SHORT EQUALS SIGN, and the double hyphens drawn as '=', U+30A0 and U+2E40, are '=' (they were read as nothing)
GATE4_EQUALS_FORMS = ["\U0001f7f0", "\ua78a", "\u30a0", "\u2e40"]
#: integration gate 4: the other characters drawn as '=' that the lens found read as nothing (U+02ED, U+2550, U+268C, U+3013): named
GATE4_NAMED_LOOKALIKES = ["\u02ed", "\u2550", "\u268c", "\u3013"]


@pytest.mark.parametrize("sign", ["＝", "﹦", "⩵"] + GATE4_EQUALS_FORMS)
def test_a_step_written_with_a_relation_sign_form_is_checked(sign):
    rc = receive(PHYS, f"The trolley starts from rest. a = (20 - 0)/4.0 {sign} 6.0 m s⁻².", TROLLEY)
    assert "stem-eq-1" in failed(rc) and "c = 5, r = 6" in message(rc, "INT-SUBJ-001"), (sign, rc.formal_checks, codes(rc))
    rc = receive(AA, f"x = 3 + 4 {sign} 8", FIND_X)
    assert "stem-eq-1" in failed(rc) and "c = 7, r = 8" in message(rc, "INT-SUBJ-001"), (sign, rc.formal_checks)


@pytest.mark.parametrize("answer", ["x = 3 ＋ 4 = 7", "x = 3 ﹢ 4 = 7", "x = 9 － 2 = 7", "x = 14 ／ 2 = 7", "x = 14 ⁄ 2 = 7", "x = 21 ➗ 3 = 7",
                                    "x = （3 + 4） = 7", "x = 7 ✕ 1 = 7"])
def test_correct_working_with_operator_forms_holds(answer):
    rc = receive(AA, answer, FIND_X)
    assert "stem-eq-1" in held(rc) and not failed(rc) and not errors(rc), (answer, rc.formal_checks, codes(rc))


@pytest.mark.parametrize("answer", ["x = 3 ⨯ 4 = 12", "x = ∜16 = 2", "f ∘ g = 3", "a = 20/4.0 ≒ 6 m s⁻²", "x = 3 ⊗ 4 = 12"]
                         + [f"a = 20/4.0 {sign} 6 m s⁻²" for sign in GATE4_NAMED_LOOKALIKES])
def test_a_sign_outside_the_grammar_keeps_its_relation_undecided(answer):
    rc = receive(AA, answer, "Find x.")
    assert not failed(rc) and not errors(rc), (answer, rc.formal_checks, codes(rc))
    assert "ST-PARSE-001" in structural(rc), (answer, structural(rc))


@pytest.mark.parametrize("answer", ["x ≪ 1", "a ≟ 5", "y ≔ 2", "x ≢ 3"] + [f"x {sign} 6" for sign in GATE4_NAMED_LOOKALIKES])
def test_a_relation_sign_outside_the_grammar_is_named(answer):
    rc = receive(AA, answer, "Find x.")
    assert "ST-PARSE-001" in structural(rc), (answer, structural(rc))


@pytest.mark.parametrize("answer", ["For x ∈ R, x² ≥ 0.", "A ⊆ B and B ⊆ C.", "x = 2 ∵ y = 3"])
def test_signs_of_sets_and_connectives_are_read_as_before(answer):
    rc = receive(AA, answer, "Find x.")
    assert "ST-PARSE-001" not in structural(rc), (answer, structural(rc))


def test_the_sign_forms_map_one_for_one():
    text = "".join(SIGN_FORMS)
    view = reading_view(text)
    assert len(view) == len(text) and all(view[k] == SIGN_FORMS[ch] for k, ch in enumerate(text))
    assert reading_view("∆v = 20") == "Δv = 20"


def test_signs_outside_the_grammar_are_error_tokens():
    assert sign_outside_grammar("⨯") == "operator" and sign_outside_grammar("≪") == "relation"
    assert sign_outside_grammar("∈") == "" and sign_outside_grammar("⊆") == "" and sign_outside_grammar("∵") == "" and sign_outside_grammar("=") == ""
    toks = lex("x = 3 ⨯ 4 = 12").tokens
    assert [t.kind for t in toks if is_sign_error(t)] == ["ERROR"]


def test_the_increment_sign_is_read_as_delta():
    doc = build_document("∆v = 20 m s⁻¹", TROLLEY, PHYS)
    assert "Δv" in doc.bindings and "v" not in doc.bindings, dict(doc.bindings)


# ============================================================================================ major 4: rule tested-value
CHECKING = ("Squaring both sides, x + 3 = x² − 6x + 9, so x² − 7x + 6 = 0.\n(x − 1)(x − 6) = 0, so x = 1 or x = 6.\n"
            "Checking: x = 1 gives √4 = 2 but 1 − 3 = −2, so x = 1 is rejected.\nTherefore x = 6.")


def test_the_checking_sentence_restates_no_result():
    rc = receive(AA, CHECKING, SQRT)
    assert rc.status.value == "ACCEPTED" and not any(c.startswith("stem-res") for c in held(rc) | failed(rc)), (rc.formal_checks, codes(rc))
    assert assess_response([rc], synthesis_required=False).display_status == "VERIFIED"


@pytest.mark.parametrize("tail", ["is rejected", "is not a solution", "does not satisfy the equation", "fails", "is extraneous", "is invalid",
                                  "is not a valid solution", "must be rejected", "doesn't work"])
def test_a_rejected_value_restates_nothing(tail):
    answer = CHECKING.replace("so x = 1 is rejected", f"so x = 1 {tail}")
    rc = receive(AA, answer, SQRT)
    assert not any(c.startswith("stem-res") for c in held(rc) | failed(rc)) and "INT-SUBJ-004" not in codes(rc), (tail, rc.formal_checks, codes(rc))


SQUARED = "Squaring both sides, x + 3 = x² − 6x + 9, so x² − 7x + 6 = 0.\n(x − 1)(x − 6) = 0, so x = 1 or x = 6.\n"


@pytest.mark.parametrize("answer", [
    # each drew a false INT-SUBJ-004 before (the restated 6 set against the check's 3: c = 3, r = 6)
    SQUARED + "Checking: x = 1 gives √4 = 2 but 1 − 3 = −2, so x = 1 is rejected.\nChecking: x = 6 gives √9 = 3 and 6 − 3 = 3, so x = 6.",
    SQUARED + "x = 1 is rejected since 1 − 3 < 0.\nChecking: √(6 + 3) = 3 and 6 − 3 = 3, so x = 6 is valid.",
    SQUARED + "For x = 1: 1 − 3 = −2 < 0, so x = 1 is rejected.\nFor x = 6: √9 = 3 and 6 − 3 = 3, so x = 6 satisfies the equation.",
    # no word after the value and no earlier 'x = 6': the chain itself substitutes the value
    SQUARED + "x = 1 is rejected since 1 − 3 < 0.\nCheck: √(6 + 3) = 3 and 6 − 3 = 3, so x = 6.",
])
def test_so_x_after_a_correct_check_is_clean(answer):
    rc = receive(AA, answer, SQRT)
    assert rc.status.value == "ACCEPTED" and not failed(rc) and "INT-SUBJ-004" not in codes(rc), (answer, rc.formal_checks, codes(rc))


def test_a_value_that_misses_the_root_after_a_check_is_still_named():
    # the stated roots are checked against the equation (stem-sol): rule tested-value moves no root check
    rc = receive(AA, SQUARED.replace("x = 1 or x = 6", "x = 1 or x = 7"), SQRT)
    assert any(c.startswith("stem-sol") for c in failed(rc)) and "INT-SUBJ-001" in codes(rc), (rc.formal_checks, codes(rc))


def test_a_measured_value_restated_for_a_computed_quantity_is_still_named():
    # the chain computes from the measured 820: '(so C(8) = 820)' restates its input, not its result, and is no root under test
    request = ("A sample's measured count rate is 820 counts min⁻¹ at t = 8 h and the background is 20 counts min⁻¹. Find the corrected "
               "count rate C(8).")
    bad = receive(AA, "t = 8 h: 820 − 20 = 800 counts min⁻¹ (so C(8) = 820).", request)
    ok = receive(AA, "t = 8 h: 820 − 20 = 800 counts min⁻¹ (so C(8) = 800).", request)
    assert any(c.startswith("stem-res") for c in failed(bad)) and "INT-SUBJ-004" in codes(bad), (bad.formal_checks, codes(bad))
    assert any(c.startswith("stem-res") for c in held(ok)) and not failed(ok), ok.formal_checks


def test_a_restated_binding_is_still_checked():
    ok = receive(PHYS, "k = 0.693/8.0 = 0.087 h⁻¹, so λ = 0.087 h⁻¹.", "A sample has a half-life of 8.0 h. Find the decay constant.")
    bad = receive(PHYS, "k = 0.693/8.0 = 0.087 h⁻¹, so λ = 0.87 h⁻¹.", "A sample has a half-life of 8.0 h. Find the decay constant.")
    assert any(c.startswith("stem-res") for c in held(ok)) and not failed(ok), ok.formal_checks
    assert any(c.startswith("stem-res") for c in failed(bad)) and "INT-SUBJ-004" in codes(bad), (bad.formal_checks, codes(bad))


# ============================================================================================ the transfer audit of the new readings
SECRET = b"integration-gate-3-stem-secret-0123456789"


@pytest.mark.parametrize("profile, request_, answer", [
    (PHYS, TROLLEY, "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = **6.0 m s⁻²**."),
    (PHYS, TROLLEY, "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = _5.0 m s⁻²_."),
    (PHYS, TROLLEY, "The trolley starts from rest. a = 20/4·0 = 6·0 m s⁻²."),
    (PHYS, TROLLEY, "The trolley starts from rest. a = (20 - 0)/4.0 ＝ 6.0 m s⁻²."),
    (AA, FIND_X, "x = 3 ⨯ 4 = 12"),
    (AA, SQRT, CHECKING),
])
def test_the_transfer_audit_rederives_the_new_readings(profile, request_, answer):
    """The overseer re-runs the branch packs on the journaled report: every new check (the '…d' companion of a joined middle-dot problem
    included) and every new finding is re-derived as delivered, so the audit passes."""
    keyring = KeyRing({k: EngineKey(KEY) for k in ("hub", "channel", "default", "integrity")}, SECRET)
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=TransferAuditor(keyring, replay_mode="inline", eager=True, shadow="always"))
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[profile], task_type="short_answer",
                               selected_agent_ids=["stem-specialist"]))
        m, _req, _rq = hub.dispatch("t", "stem-specialist", request_)
        _reply, rc = hub.receive("t", m.message_id, answer, agent_id="stem-specialist", report_id="r1")
        audit = hub.audit("t")
    finally:
        hub.close()
    state = getattr(audit.state, "value", audit.state)
    assert state == "AUDIT_PASSED", (answer, state, [(f.code, f.message[:160]) for f in audit.report.findings])


# ============================================================================================ the new readings on hostile input
N = 20_000
HOSTILE = {
    "emphasis pairs": "**x** " * (N // 6) + "!", "underscore pairs": "_x_ " * (N // 4) + "!", "stars": "*" * N + "x",
    "underscores": "_" * N + "x", "unclosed emphasis": "**x " * (N // 4) + "!", "middle dots": "1·" * (N // 2) + "x",
    "dot chains": "a = 1·2 + " * (N // 10) + "!", "sign forms": "x ＝ 3 ＋ " * (N // 8) + "!", "signs outside": "x ⨯ " * (N // 4) + "= 1",
    "relation signs outside": "x ≪ 1 " * (N // 6) + "!", "tested values": "x = 1 gives 1 − 3 = −2, so x = 1 is rejected. " * (N // 48),
    "bold results": "a = 20/4.0 = **5.0 m s⁻²**. " * (N // 28), "bold italic": "***x*** " * (N // 8) + "!",
    "struck": "~~x~~ " * (N // 6) + "!", "unclosed strikes": "~~x " * (N // 4) + "!", "mixed markers": "**_~~*" * (N // 6) + "x",
}
#: per call, CPU seconds for a whole document and its checks (measured well under a second); a quadratic rescan of 20,000 characters
#: takes seconds, a regular-expression blow-up far longer
DOCUMENT_BOUND = 8.0


@pytest.mark.parametrize("shape", sorted(HOSTILE))
def test_the_new_readings_stay_linear_on_hostile_input(shape):
    text = HOSTILE[shape]
    clear_document_cache()
    c0 = time.process_time()
    doc = build_document(text, "Find x.", AA)
    build_checks(doc)
    doc.locate(text[: min(200, len(text))].replace("*", ""))
    STEM_HOOKS.coverage_terms(text[:400].replace("*", ""), text, "Find x.", AA)
    spent = time.process_time() - c0
    assert spent < DOCUMENT_BOUND, (shape, round(spent, 2))
