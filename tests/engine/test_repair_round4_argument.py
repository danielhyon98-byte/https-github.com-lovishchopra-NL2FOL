"""Repair round 4 of the argument diagnosis, engine layer, the naming gaps of ADV4-08 (each with a positive case and a clean
control, built as problems and decided by ``engine.verify``):

* (a) a cause read into a group comparison with one comparative after a relative clause ("students who eat breakfast have
  higher grades, so eating breakfast causes higher grades") is a causal leap (ARG-CL-001), as two comparatives were; a
  comparative inside a short clause ("students who scored higher") compares no group, and a controlled comparison
  warrants the cause;
* (b) "light" read as radiation where it is what travels ("light travels at 3.0 × 10⁸ m s⁻¹") and as small mass ("a
  feather is light") in one link is an equivocation (ARG-EQ-003); "a light car travels at" selects no radiation sense;
* (c) "did not work" for "ineffective" is a circle by paraphrase (ARG-CIRC-003): "work" is read as "effective" and the
  prefix "in" negates it; a reason with other content, or the opposite polarity, restates nothing."""
from __future__ import annotations

import pytest

from epinoic_logic.engine import argument

from .test_argument_diagnostics import IMP, B, P, V, codes, problem, run


def _link(fact: str, point: str, *, label: str = "", fact_meaning: str = "", extra: tuple[tuple[str, str], ...] = ()):
    symbols = B(a=fact_meaning or fact, c=point)
    premises = [P("e", V("a"), fact, kind="general_knowledge"), P("l", IMP(V("a"), V("c")), label or f"{fact}, so {point}", note="link: so")]
    for i, (meaning, text) in enumerate(extra):
        symbols[f"x{i}"] = ("Bool", meaning)
        premises.append(P(f"x{i}", V(f"x{i}"), text, kind="general_knowledge"))
    return codes(run(problem(premises, V("c"), symbols)))


# ----------------------------------------------------------------------------------------------- (a) one comparative

def test_a_cause_read_into_a_group_comparison_with_one_comparative_is_a_causal_leap():
    found = _link("students who eat breakfast have higher grades", "eating breakfast causes higher grades")
    assert found.get("ARG-CL-001") == "warning"


@pytest.mark.parametrize("text", ["students who eat breakfast have higher grades", "patients who take the drug recover faster"])
def test_one_comparative_after_a_relative_clause_states_a_correlation(text):
    assert argument._correlation(text)


@pytest.mark.parametrize("text", ["students who scored higher passed the exam", "gases with more energy have faster particles",
                                  "the students ate breakfast"])
def test_control_a_comparative_inside_a_short_clause_or_of_a_physical_class_states_no_correlation(text):
    assert argument._correlation(text) is None


def test_control_a_controlled_comparison_warrants_the_cause():
    found = _link("students who were randomly assigned to eat breakfast had higher grades than the control group",
                  "eating breakfast causes higher grades")
    assert "ARG-CL-001" not in found


# ----------------------------------------------------------------------------------------------- (b) light, two senses

def test_light_as_what_travels_and_as_small_mass_in_one_link_is_an_equivocation():
    symbols = B(a="a feather is light (has little mass)", c="a feather travels at 3.0 × 10⁸ m/s")
    premises = [P("e", V("a"), "a feather is light", kind="general_knowledge"),
                P("l", IMP(V("a"), V("c")), "light travels at 3.0 × 10⁸ m/s, so a light thing travels at that speed")]
    assert codes(run(problem(premises, V("c"), symbols))).get("ARG-EQ-003") == "warning"


@pytest.mark.parametrize("fact, point, label", [
    ("light travels at 3.0 × 10⁸ m/s in a vacuum", "light from the Sun reaches Earth in about 8 minutes",
     "light travels at 3.0 × 10⁸ m/s, so sunlight reaches Earth in about 8 minutes"),
    ("the car is lightweight", "the car uses little fuel", "a light car travels at 30 m/s using little fuel, so it uses little fuel"),
])
def test_control_one_sense_of_light_throughout_is_no_equivocation(fact, point, label):
    assert not {"ARG-EQ-002", "ARG-EQ-003"} & set(_link(fact, point, label=label))


# ----------------------------------------------------------------------------------------------- (c) did not work

def test_did_not_work_restating_ineffective_is_a_circle_by_paraphrase():
    assert _link("the sugar tax did not work", "the sugar tax was ineffective").get("ARG-CIRC-003") == "warning"


@pytest.mark.parametrize("fact, point", [("the sugar tax did not work", "the sugar tax should be replaced"),
                                         ("the sugar tax raised revenue", "the sugar tax was effective"),
                                         ("the sugar tax did not work", "the sugar tax was effective")])
def test_control_a_reason_with_other_content_or_polarity_restates_nothing(fact, point):
    assert "ARG-CIRC-003" not in _link(fact, point)
