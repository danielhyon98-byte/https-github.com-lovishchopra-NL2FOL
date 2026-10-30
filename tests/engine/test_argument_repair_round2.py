"""Repair round 2 of the argument diagnosis, engine layer: each rule with a positive case and a clean control, built as
problems and decided by ``engine.verify``.

* circularity by paraphrase where the restatement drops a qualifier or a name (MISS-CIRC-PARAPHRASE);
* complementary options read through word roots ("passed"/"failed", "converges"/"diverges"; ADV2-04);
* equivocation when one symbol's meaning and the labels of the premises that use it read one word in two senses
  (MISS-EQUIV-BIO, MISS-EQUIV-PHYS, ADV2-09);
* a generalisation from a sample to "most" (ADV2-10);
* a causal link warranted by a stated control is no leap, and a rule stated from subject knowledge is named as an
  unchecked rule, not a missing link (NAME-LINK-NONDISCRIMINATING);
* a cause read into a correlation between groups ("countries that eat more chocolate win more Nobel prizes, so eating
  chocolate causes ...") is a causal leap, as one read into a sequence in time is (holdout2 causal class, own probes).
"""
from __future__ import annotations

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S

from .test_argument_diagnostics import B, IMP, NOT, OR, P, V, codes, problem, run


# ----------------------------------------------------------------------------------------------- paraphrase circularity

@pytest.mark.parametrize("fact, point", [
    ("the 1919 Treaty of Versailles imposed harsh terms on Germany", "the treaty imposed harsh terms on Germany"),
    ("Stalin's Five-Year Plans greatly increased Soviet industrial output", "the Five-Year Plans increased industrial output"),
])
def test_a_reason_that_restates_the_point_with_a_qualifier_dropped_is_circular(fact, point):
    meanings = B(a=fact, c=point)
    p = problem([P("e", V("a"), fact), P("l", IMP(V("a"), V("c")), f"{fact}, so {point}", note="link: so")], V("c"), meanings)
    assert codes(run(p)).get("ARG-CIRC-003") == "warning"


def test_a_reason_about_something_else_is_no_paraphrase():
    fact, point = "the Treaty of Versailles imposed reparations on Germany", "the Weimar Republic faced hyperinflation in 1923"
    p = problem([P("e", V("a"), fact), P("l", IMP(V("a"), V("c")), f"{fact}, so {point}", note="link: so")], V("c"), B(a=fact, c=point))
    assert "ARG-CIRC-003" not in codes(run(p))


# ----------------------------------------------------------------------------------------------- complementary options

@pytest.mark.parametrize("a, b", [("the sample passed the purity test", "the sample failed the purity test"),
                                  ("the series converges", "the series diverges")])
def test_complementary_options_read_by_their_roots_are_a_true_dichotomy(a, b):
    meanings = B(p=a, q=b)
    r = run(problem([P("d", OR(V("p"), V("q")), f"either {a} or {b}"), P("n", NOT(V("q")), f"it is not the case that {b}")], V("p"), meanings))
    assert r.status is S.ENTAILED and "ARG-FD-001" not in codes(r)


def test_options_that_are_not_complementary_remain_a_false_dilemma():
    a, b = "the sample passed the purity test", "the sample was contaminated in transport"
    r = run(problem([P("d", OR(V("p"), V("q")), f"either {a} or {b}"), P("n", NOT(V("q")), f"it is not the case that {b}")], V("p"), B(p=a, q=b)))
    assert codes(r).get("ARG-FD-001") == "warning"   # the writer's own either/or of options that do not exclude each other


# ----------------------------------------------------------------------------------------------- equivocation across premises

def test_one_symbol_read_in_an_everyday_and_a_technical_sense_is_equivocation():
    meanings = B(works="work is done on the wall", energy="energy is transferred to the wall")
    p = problem([P("f", V("works"), "pushing against a wall for an hour is hard work", kind="general_knowledge"),
                 P("r", IMP(V("works"), V("energy")), "in physics, whenever work is done on an object energy is transferred to it", kind="general_knowledge",
                   note="rule")], V("energy"), meanings)
    assert codes(run(p)).get("ARG-EQ-003") == "warning"


def test_the_same_word_in_one_technical_sense_throughout_is_no_equivocation():
    meanings = B(works="the crane does work on the load (a force through a distance)", energy="energy is transferred to the load")
    p = problem([P("f", V("works"), "the crane exerts a force through a distance in the direction of the force", kind="general_knowledge"),
                 P("r", IMP(V("works"), V("energy")), "in physics, whenever work is done on an object energy is transferred to it", kind="general_knowledge",
                   note="rule")], V("energy"), meanings)
    assert "ARG-EQ-003" not in codes(run(p))


# ----------------------------------------------------------------------------------------------- generalisation to "most"

def test_a_sample_generalised_to_most_of_a_population_is_hasty():
    meanings = B(sample="9 of the 12 students in our class prefer online lessons", most="most students in the country prefer online lessons")
    p = problem([P("e", V("sample"), "9 of the 12 students in our class prefer online lessons", kind="general_knowledge"),
                 P("l", IMP(V("sample"), V("most")), "so most students in the country prefer online lessons", note="link: so")], V("most"), meanings)
    assert codes(run(p)).get("ARG-HG-001") == "warning"


def test_most_of_the_sample_itself_is_no_generalisation():
    meanings = B(sample="9 of the 12 students in our class prefer online lessons", most="most of the students in our class prefer online lessons")
    p = problem([P("e", V("sample"), "9 of the 12 students in our class prefer online lessons", kind="general_knowledge"),
                 P("l", IMP(V("sample"), V("most")), "so most of the students in our class prefer online lessons", note="link: so")], V("most"), meanings)
    assert "ARG-HG-001" not in codes(run(p))


# ----------------------------------------------------------------------------------------------- warranted links and stated rules

def test_a_causal_link_warranted_by_a_stated_control_is_no_leap():
    meanings = B(trial="patients randomly assigned the drug in a controlled trial recovered faster than the placebo group",
                 cause="the drug caused the faster recovery")
    p = problem([P("e", V("trial"), meanings["trial"][1], kind="general_knowledge"),
                 P("l", IMP(V("trial"), V("cause")), "so the drug caused the faster recovery", note="link: so")], V("cause"), meanings)
    assert "ARG-LINK-001" not in codes(run(p))


def test_the_same_causal_link_with_no_stated_control_is_still_recorded():
    meanings = B(trial="patients who took the drug recovered faster", cause="the drug caused the faster recovery")
    p = problem([P("e", V("trial"), meanings["trial"][1], kind="general_knowledge"),
                 P("l", IMP(V("trial"), V("cause")), "so the drug caused the faster recovery", note="link: so")], V("cause"), meanings)
    assert "ARG-LINK-001" in codes(run(p))


def test_a_rule_stated_from_subject_knowledge_is_an_unchecked_rule_not_a_missing_link():
    meanings = B(metal="the rod is made of copper", conducts="the rod conducts electricity")
    p = problem([P("e", V("metal"), "the rod is made of copper", kind="task_setting", verified=True),
                 P("r", IMP(V("metal"), V("conducts")), "copper conducts electricity", kind="general_knowledge", note="rule")], V("conducts"), meanings)
    found = codes(run(p))
    assert found.get("ARG-LINK-002") == "info" and "ARG-LINK-001" not in found


# ----------------------------------------------------------------------------------------------- a cause read into a correlation

def _causal_link(fact: str, point: str):
    p = problem([P("e", V("a"), fact, kind="general_knowledge"), P("l", IMP(V("a"), V("c")), f"{fact}, so {point}", note="link: so")], V("c"),
                B(a=fact, c=point))
    return run(p)


@pytest.mark.parametrize("fact, point", [
    ("countries that eat more chocolate win more Nobel prizes", "eating chocolate causes people to win Nobel prizes"),
    ("towns with more ice cream sales have more drownings", "ice cream sales cause drownings"),
    ("students who sleep more get higher grades", "more sleep causes higher grades"),
    ("in our survey, screen time was correlated with lower test scores", "screen time causes lower test scores"),
])
def test_a_cause_read_into_a_correlation_is_a_causal_leap(fact, point):
    r = _causal_link(fact, point)
    assert codes(r).get("ARG-CL-001") == "warning"
    assert "correlation" in next(d.message for d in r.named_diagnostics if d.code == "ARG-CL-001")


@pytest.mark.parametrize("fact, point", [
    ("in a randomised controlled trial, students who were made to sleep more got higher grades than the control group", "more sleep causes higher grades"),
    ("countries that eat more chocolate win more Nobel prizes", "chocolate consumption and Nobel prizes are associated"),
    ("gases with more energy have faster moving particles", "heating causes the gas to expand"),
    ("the more energy the particles have, the faster they move", "heating causes the gas to expand"),
])
def test_a_controlled_comparison_a_mere_association_or_a_physical_property_is_no_causal_leap(fact, point):
    assert "ARG-CL-001" not in codes(_causal_link(fact, point))
