"""Close round 1, V6-DA-05: the rule text of the unbridged-leap reading (repair round 5, DA-1) quoted examples taken from the
hold-out, so the hold-out no longer measured how the rule generalises. Its examples are now written for the rule, and this
test pins that each one behaves as its docstring says: the ranked cause and the advised action are leaps, and a sentence
that says more about the advised target bridges the second. (The hold-out itself is never read by the tests.)"""
from __future__ import annotations

from epinoic_logic.translate import diag_argument
from epinoic_logic.translate.diag_argument import unbridged_leap_reading

RANKED = "The Dunmore valley has steep slopes, so overgrazing is the main cause of soil loss in the Dunmore valley."
ADVISED = "Since Marlpit Ltd's profits rose, Marlpit Ltd should open an office in Norway."
BRIDGE = "Norway has the lowest energy costs in Europe."


def test_the_docstring_examples_are_the_rules_own():
    doc = diag_argument.unbridged_leap_reading.__doc__ or ""
    assert "the Dunmore valley has steep slopes, so overgrazing is the main" in doc
    assert "Since Marlpit Ltd's profits rose, Marlpit Ltd should open an office in Norway" in doc
    assert "Norway has the lowest energy costs in Europe" in doc


def test_the_ranked_cause_example_is_a_leap():
    assert unbridged_leap_reading([RANKED], "the Dunmore valley has steep slopes",
                                  "overgrazing is the main cause of soil loss in the Dunmore valley") == RANKED


def test_the_advised_action_example_is_a_leap():
    assert unbridged_leap_reading([ADVISED], "Marlpit Ltd's profits rose", "Marlpit Ltd should open an office in Norway") == ADVISED


def test_control_a_sentence_about_the_advised_target_bridges_it():
    assert unbridged_leap_reading([ADVISED + " " + BRIDGE], "Marlpit Ltd's profits rose", "Marlpit Ltd should open an office in Norway") is None
