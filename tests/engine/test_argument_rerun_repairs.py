"""Repair round 1 of the argument diagnosis, engine layer: the informal-fallacy findings of the re-run review.

Each rule below has a positive case and a clean control, built as problems and decided by ``engine.verify`` (the
diagnostics are the engine's own, signed with its result). Every rule reads the bound problem only: expressions, grounding
kinds and notes, meanings and labels through the shared tokenizer and the closed tables of ``engine/argument_cues.py``.

* hasty generalisation from a counted sample (A-INF-HG) and from a step hidden in a conjunction (ADV-11 c);
* equivocation on a word of the closed table of equivocal terms (A-INF-EQ);
* circular reasoning by paraphrase through the closed paraphrase tables (A-INF-CIRC, ADV-11 e);
* an arithmetic restatement of the point (fidelity-4 variant): E112 in the engine's normal form, ARG-CIRC-002 beyond it;
* affirming the consequent over a chain of stated rules (ADV-11 d) and with a link labelled as subject knowledge (ADV-11 a);
* a false dilemma labelled as subject knowledge (ADV-11 b) and complementary options read from their meanings (ADV-13);
* a causal leap whose control cue is negated or is a comparison with another time (ADV-06).
"""
from __future__ import annotations

import pytest

from epinoic_logic.engine import argument as A
from epinoic_logic.engine.runner import circular_premises
from epinoic_logic.engine.statuses import VerificationStatus as S

from .test_argument_diagnostics import AND, B, CMP, IMP, NOT, OR, P, R, V, codes, problem, run, warnings


def I(value) -> dict:
    return {"op": "int", "value": str(value)}


def ADD(*args: dict) -> dict:
    return {"op": "add", "args": list(args)}


def MUL(*args: dict) -> dict:
    return {"op": "mul", "args": list(args)}


def SUB(a: dict, b: dict) -> dict:
    return {"op": "sub", "left": a, "right": b}


def diag(result, code: str):
    return next(d for d in result.named_diagnostics if d.code == code)


# ----------------------------------------------------------------------------------------------- hasty generalisation

def _hasty(antecedent: str, consequent: str, label: str):
    meanings = B(sample=antecedent, all_=consequent)
    return problem([P("e", V("sample"), antecedent, kind="general_knowledge"),
                    P("l", IMP(V("sample"), V("all_")), label, note="link: so")], V("all_"), meanings)


@pytest.mark.parametrize("antecedent", [
    "two cyclists raised their VO2 max after altitude training",
    "12 participants remembered more words after sleeping",
    "some students who revised with flashcards improved",
    "three of the schools that banned phones improved their results",
])
def test_a_universal_drawn_from_a_counted_sample_is_a_hasty_generalisation(antecedent):
    r = run(_hasty(antecedent, "altitude training benefits all endurance athletes", "so it benefits all endurance athletes"))
    assert r.status is S.ENTAILED and codes(r)["ARG-HG-001"] == "warning"
    d = diag(r, "ARG-HG-001")
    assert d.defect == "hasty_generalisation" and d.assertion_ids == ["l"] and d.missing_link is not None


@pytest.mark.parametrize("antecedent", [
    "all thirty students in the class passed the test",            # a closed enumeration of the whole class
    "the average speed of the cars was 30 metres per second",      # a measurement, not a count of cases
    "the speed of light is 300 million metres per second",         # a law with a figure, not a sample
])
def test_a_count_that_is_an_enumeration_or_a_measurement_is_no_sample(antecedent):
    r = run(_hasty(antecedent, "every car exceeded the limit", "so every car exceeded the limit"))
    assert r.status is S.ENTAILED and "ARG-HG-001" not in codes(r)


def test_a_generalising_step_hidden_in_a_conjunction_is_read_as_a_link():
    """ADV-11 c: "Nairobi grew, and two cities growing means every African city grew" is one premise holding a fact and
    the writer's step; R0 reads it as a link, and the pattern rule reads the step inside it."""
    meanings = B(lagos="the population of Lagos grew rapidly between 2000 and 2020",
                 nairobi="the population of Nairobi grew rapidly between 2000 and 2020",
                 every="every African city grew rapidly between 2000 and 2020")
    p = problem([P("e1", V("lagos"), "Lagos grew", kind="quotation", verified=True),
                 P("l", AND(V("nairobi"), IMP(AND(V("lagos"), V("nairobi")), V("every"))), "Nairobi grew, and two cities growing means every city grew")],
                V("every"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and codes(r)["ARG-HG-001"] == "warning"
    link = diag(r, "ARG-LINK-001")
    assert link.assertion_ids == ["l"] and "inside a conjunction" in link.message and link.missing_link.text.startswith("if ")
    assert "ARG-FACT-001" not in codes(r)


# ----------------------------------------------------------------------------------------------- equivocation

def test_one_word_in_its_biological_and_its_everyday_sense_is_an_equivocation():
    meanings = B(fit="only the fittest organisms, those best adapted to their environment, survive",
                 strong="only the strongest animals survive")
    p = problem([P("e", V("fit"), "natural selection is the survival of the fittest", kind="general_knowledge"),
                 P("l", IMP(V("fit"), V("strong")), "the fittest are the strongest, so the strongest survive", note="link: so")], V("strong"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and codes(r)["ARG-EQ-003"] == "warning"
    d = diag(r, "ARG-EQ-003")
    assert d.defect == "equivocation" and "biological" in d.message and "everyday" in d.message and d.missing_link is not None


def test_one_word_in_both_senses_within_the_writers_own_step_is_an_equivocation():
    meanings = B(push="the student pushed against the wall all day", work="work is done on the wall in the physics sense")
    p = problem([P("e", V("push"), "the student pushed against the wall all day", kind="general_knowledge"),
                 P("l", IMP(V("push"), V("work")), "pushing a wall all day is hard work, so work is done on the wall", note="link: so")],
                V("work"), meanings)
    r = run(p)
    assert codes(r)["ARG-EQ-003"] == "warning" and "physics" in diag(r, "ARG-EQ-003").message


@pytest.mark.parametrize("label, consequent", [
    ("a 10 N force moved the box 2 m, so work was done on it", "work is done on the box in the physics sense"),     # one sense
    ("holding the box still takes effort, so no work is done on it", "no work is done on the box in the physics sense"),  # contrast
])
def test_one_sense_or_two_senses_contrasted_is_no_equivocation(label, consequent):
    meanings = B(e="the force moved the box", work=consequent)
    p = problem([P("f", V("e"), "the force moved the box", kind="general_knowledge"),
                 P("l", IMP(V("e"), V("work")), label, note="link: so")], V("work"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and "ARG-EQ-003" not in codes(r)


def test_a_negated_everyday_cue_selects_no_sense():
    meanings = B(fit="the fittest organisms are the best adapted to their environment, not necessarily the strongest",
                 more="the best adapted organisms leave more offspring")
    p = problem([P("e", V("fit"), "fitness means being best adapted", kind="general_knowledge"),
                 P("l", IMP(V("fit"), V("more")), "the fittest are best adapted, so they leave more offspring", note="link: so")], V("more"), meanings)
    assert "ARG-EQ-003" not in codes(run(p))


# ----------------------------------------------------------------------------------------------- circular by paraphrase

@pytest.mark.parametrize("fact, point", [
    ("his ambition is what drives Macbeth", "Macbeth is driven by ambition"),                         # voice
    ("Weimar Germany lacked political stability", "Weimar Germany was politically unstable"),         # part of speech, negation
    ("the Five-Year Plans achieved what they set out to achieve", "the Five-Year Plans were successful"),  # closed definition
])
def test_a_reason_that_restates_the_point_in_other_words_is_circular(fact, point):
    meanings = B(a=fact, c=point)
    p = problem([P("e", V("a"), fact), P("l", IMP(V("a"), V("c")), f"{fact}, so {point}", note="link: so")], V("c"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and codes(r)["ARG-CIRC-003"] == "warning"


@pytest.mark.parametrize("fact, point", [
    ("the Five-Year Plans increased industrial output", "the Five-Year Plans were successful"),
    ("the Wall Street Crash caused mass unemployment", "the Treaty of Versailles was the main reason for Nazi success"),
    ("Weimar Germany lacked political stability", "Weimar Germany was politically stable"),           # opposite polarity
])
def test_a_reason_with_other_content_or_the_opposite_polarity_is_no_paraphrase(fact, point):
    meanings = B(a=fact, c=point)
    p = problem([P("e", V("a"), fact), P("l", IMP(V("a"), V("c")), f"{fact}, so {point}", note="link: so")], V("c"), meanings)
    assert "ARG-CIRC-003" not in codes(run(p))


def test_the_paraphrase_reader_roots_forms_of_one_word_together():
    assert {A._root(w) for w in ("drives", "driven", "drove")} == {"driv"}
    assert A._root("stability") == A._root("stable") and A._root("political") == A._root("politics") == A._root("politically")
    assert A._root("successful") == A._root("succeeded") == A._root("success")
    assert A._concept("he lacked stability", "he was unstable")[1] is True and A._concept("he was unstable", "he lacked stability")[1] is True


# ----------------------------------------------------------------------------------------------- arithmetic restatement

DT = {"dt": ("Int", "the doubling time in years")}
POINT = CMP("eq", V("dt"), I(41))


@pytest.mark.parametrize("premise", [
    CMP("eq", ADD(V("dt"), I(0)), I(41)),        # an identity element
    CMP("eq", ADD(I(40), I(1)), V("dt")),        # 41 spelt as a closed term
    CMP("eq", SUB(V("dt"), I(41)), I(0)),        # a difference of zero
], ids=["plus zero", "forty plus one", "difference zero"])
def test_a_restatement_in_arithmetic_form_is_e112(premise):
    p = problem([P("w", premise, "the point written as arithmetic")], POINT, DT)
    assert circular_premises(p) == ["w"]
    r = run(p)
    assert r.status is S.ENTAILED and "E112" in {d.code for d in r.diagnostics} and codes(r)["ARG-CIRC-001"] == "warning"


def test_an_equation_equivalent_to_the_point_is_circular_beyond_the_normal_form():
    """``2 x dt = 82`` is no rewrite of the normal form (solving is not spelling), but the writer's own unsourced
    equation equivalent to the point assumes it. Rewritten to the stricter rule of repair round 2 (fidelity-4 variant):
    the engine's E112 reads the equivalence too (:func:`equivalent_premises`), so the ENTAILED is no verdict and the
    circle is named ARG-CIRC-001 from E112 (before, it was ENTAILED with only the argument rule ARG-CIRC-002)."""
    p = problem([P("w", CMP("eq", MUL(I(2), V("dt")), I(82)), "twice the doubling time is 82")], POINT, DT)
    assert circular_premises(p) == []
    r = run(p)
    assert r.status is S.ENTAILED and "E112" in {d.code for d in r.diagnostics} and codes(r)["ARG-CIRC-001"] == "warning"


def test_working_and_sourced_equations_are_no_circle():
    rate = {"rate": ("Real", "the charge in pounds")}
    working = problem([P("w", CMP("eq", V("rate"), ADD(R("2.0"), MUL(R("0.40"), R("60")))), "2.00 + 0.40 x 60")], CMP("eq", V("rate"), R("26")), rate)
    r = run(working)
    assert r.status is S.ENTAILED and "E112" not in {d.code for d in r.diagnostics} and "ARG-CIRC-002" not in codes(r)
    sourced = problem([{"id": "w", "expr": CMP("eq", MUL(I(2), V("dt")), I(82)), "label": "the task gives 2 x dt = 82",
                        "grounding": {"kind": "arithmetic_fact", "source_refs": [{"document_id": "task", "excerpt": "2dt = 82"}]}}], POINT, DT)
    assert "ARG-CIRC-002" not in codes(run(sourced))


# ----------------------------------------------------------------------------------------------- affirming the consequent

def _chain(link_expr: dict, conclusion: dict):
    meanings = B(dem="demand for steel rose in 2024", pr="steel prices rose in 2024", out="the mills expanded output in 2024")
    return problem([P("r1", IMP(V("dem"), V("pr")), "If demand for steel rises, steel prices rise", kind="quotation", verified=True),
                    P("r2", IMP(V("pr"), V("out")), "If steel prices rise, mills expand output", kind="quotation", verified=True),
                    P("e", V("out"), "In 2024 the mills expanded output", kind="quotation", verified=True),
                    P("l", link_expr, "mills expanded output, so demand must have risen", note="link: so")], conclusion, meanings)


def test_the_converse_of_a_chain_of_stated_rules_is_affirming_the_consequent():
    r = run(_chain(IMP(V("out"), V("dem")), V("dem")))
    assert r.status is S.ENTAILED and codes(r)["ARG-AC-001"] == "warning"
    d = diag(r, "ARG-AC-001")
    assert d.assertion_ids[0] == "l" and {"r1", "r2"} <= set(d.assertion_ids) and len(d.derived_problem_digests) >= 2


def test_the_inverse_of_a_chain_of_stated_rules_is_denying_the_antecedent():
    meanings = B(dem="demand for steel rose in 2024", pr="steel prices rose in 2024", out="the mills expanded output in 2024")
    p = problem([P("r1", IMP(V("dem"), V("pr")), "If demand rises, prices rise", kind="quotation", verified=True),
                 P("r2", IMP(V("pr"), V("out")), "If prices rise, mills expand output", kind="quotation", verified=True),
                 P("e", NOT(V("dem")), "demand did not rise", kind="quotation", verified=True),
                 P("l", IMP(NOT(V("dem")), NOT(V("out"))), "demand did not rise, so output did not expand", note="link: so")], NOT(V("out")), meanings)
    assert codes(run(p))["ARG-DA-001"] == "warning"


def test_a_link_the_chain_gives_is_no_fallacy():
    # the writer's own link dem -> out is what the rules give together: a shortcut, not a converse
    meanings = B(dem="demand for steel rose in 2024", pr="steel prices rose in 2024", out="the mills expanded output in 2024")
    p = problem([P("r1", IMP(V("dem"), V("pr")), "If demand rises, prices rise", kind="quotation", verified=True),
                 P("r2", IMP(V("pr"), V("out")), "If prices rise, mills expand output", kind="quotation", verified=True),
                 P("e", V("dem"), "demand rose", kind="quotation", verified=True),
                 P("l", IMP(V("dem"), V("out")), "demand rose, so output expanded", note="link: so")], V("out"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and "ARG-AC-001" not in codes(r) and "ARG-DA-001" not in codes(r)


def test_a_converse_labelled_as_unmarked_subject_knowledge_is_recorded_at_info():
    """ADV-11 a: the step the proof needs is the converse of the stated rule, labelled general_knowledge with no "rule"
    note; the shape is named at info (the label claims knowledge), and a converse marked as a stated rule is not read
    (``test_a_biconditional_stated_both_ways_is_no_affirming_the_consequent``)."""
    meanings = B(mg="plant 7 was short of magnesium", yellow="the leaves of plant 7 turned yellow between their veins")
    p = problem([P("r", IMP(V("mg"), V("yellow")), "a lack of magnesium makes leaves turn yellow between the veins", kind="general_knowledge"),
                 P("e", V("yellow"), "the leaves of plant 7 turned yellow", kind="quotation", verified=True),
                 P("l", IMP(V("yellow"), V("mg")), "yellow leaves between the veins mean a magnesium shortage", kind="general_knowledge")], V("mg"), meanings)
    r = run(p)
    assert codes(r)["ARG-AC-001"] == "info" and warnings(r.named_diagnostics) == []


# ----------------------------------------------------------------------------------------------- false dilemma

def test_an_unmarked_either_or_labelled_as_knowledge_is_recorded_at_info():
    meanings = B(gen="memory span is entirely genetic", learned="memory span is entirely learned")
    p = problem([P("d", OR(V("gen"), V("learned")), "a trait is either entirely genetic or entirely learned", kind="general_knowledge"),
                 P("e", NOT(V("gen")), "memory span is not entirely genetic", kind="quotation", verified=True)], V("learned"), meanings)
    r = run(p)
    assert codes(r)["ARG-FD-001"] == "info" and warnings(r.named_diagnostics) == []


@pytest.mark.parametrize("a_text, b_text", [
    ("n is even", "n is odd"), ("the bit b is 0", "the bit b is 1"), ("the switch is on", "the switch is off"), ("n is even", "n is not even"),
])
def test_options_complementary_by_meaning_are_no_false_dilemma(a_text, b_text):
    meanings = B(a=a_text, b=b_text)
    p = problem([P("d", OR(V("a"), V("b")), f"either {a_text} or {b_text}", note="link: either"),
                 P("e", NOT(V("a")), f"it is not the case that {a_text}", kind="task_setting", verified=True)], V("b"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and "ARG-FD-001" not in codes(r)


def test_options_that_differ_by_more_than_a_complementary_pair_are_still_a_false_dilemma():
    meanings = B(a="the policy was a complete success", b="the policy was a complete failure")
    p = problem([P("d", OR(V("a"), V("b")), "the policy was either a complete success or a complete failure", note="link: either"),
                 P("e", NOT(V("a")), "the policy was not a complete success", kind="task_setting", verified=True)], V("b"), meanings)
    assert codes(run(p))["ARG-FD-001"] == "warning"
    assert not A._complementary_meanings("the bit b is 0", "the count b is 1")    # a context pair needs its context word


# ----------------------------------------------------------------------------------------------- causal leap

def _causal(extra_label: str):
    meanings = {"s_before": ("Real", "sales in the months before April"), "s_after": ("Real", "sales in the months after April"),
                **B(caused="the advertising campaign caused the rise in sales")}
    return problem([P("e1", CMP("eq", V("s_before"), R(100)), "sales were 100 before April", kind="quotation", verified=True),
                    P("e2", CMP("eq", V("s_after"), R(140)), "sales were 140 after April", kind="quotation", verified=True),
                    P("l", IMP(CMP("gt", V("s_after"), V("s_before")), V("caused")), f"sales rose after the campaign, so it caused the rise{extra_label}",
                      note="link: so")], V("caused"), meanings)


@pytest.mark.parametrize("extra", ["; there was no control group", "; compared with the months before April sales rose"])
def test_a_negated_control_cue_or_a_before_and_after_comparison_does_not_rule_a_causal_leap_out(extra):
    assert codes(run(_causal(extra)))["ARG-CL-001"] == "warning"


@pytest.mark.parametrize("extra", ["; compared with a control group of shops, sales rose more", "; shops were randomly assigned to the campaign"])
def test_a_stated_control_still_rules_a_causal_leap_out(extra):
    r = run(_causal(extra))
    assert r.status is S.ENTAILED and "ARG-CL-001" not in codes(r)
    assert A._control("the party took control of the press") is None
