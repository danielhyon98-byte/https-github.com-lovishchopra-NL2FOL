"""Repair round 3 of the argument diagnosis, engine layer: each rule with a positive case and a clean control, built as
problems and decided by ``engine.verify`` (the vacuity case goes through the translator, whose circularity rule it is).

* ADV3-04: options that exhaust their cases ("positive, negative or zero", "acidic, neutral or alkaline", "moving or at
  rest") are no false dilemma; options that do not ("raises taxes or cuts spending") still are (ARG-FD-001).
* ADV3-05: a census that counted the whole population concludes "most" of that population validly; a sample drawn on a
  wider population is still a hasty generalisation (ARG-HG-001); a cause read into one patient's recovery is a causal
  leap, never a hasty generalisation.
* ADV3-06: a control cue warrants a causal link only where it bears on that link: a decoy elsewhere ("the shop was chosen
  randomly by the marketing team") hides nothing.
* ADV3-07: a cause read into a sequence of dated or "after" facts is named (ARG-CL-001), Bool facts included.
* V3-FALSE-CAUSAL-EFFECT-DURATION: "the effect of X was gone after seven days, so the effect is short-lived" reads no
  cause into a sequence.
* tf_z19: a conclusion true under every assignment is a vacuous argument (E108), never refused as circular.
* ADV3-13: a writer's leap the translation labels as a stated rule ("rule" note) with a label that records no rule
  ("so") keeps its missing link (ARG-LINK-001); a rule the label states stays an unchecked rule (ARG-LINK-002)."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from ..contract.helpers import make_report, output, problem_dict
from .test_argument_diagnostics import AND, B, IMP, NOT, OR, P, V, codes, problem, run


def _either(options: list[str], denied: list[int]):
    symbols = {f"o{i}": ("Bool", o) for i, o in enumerate(options)}
    premises = [P("d", OR(*[V(f"o{i}") for i in range(len(options))]), "either " + " or ".join(options))]
    premises += [P(f"n{i}", NOT(V(f"o{i}")), f"it is not the case that {options[i]}") for i in denied]
    rest = [i for i in range(len(options)) if i not in denied]
    return run(problem(premises, V(f"o{rest[0]}"), symbols))


@pytest.mark.parametrize("options", [
    ["the number is positive", "the number is negative", "the number is zero"],
    ["the solution is acidic", "the solution is neutral", "the solution is alkaline"],
    ["the light is reflected", "the light is absorbed", "the light is transmitted"],
    ["the price increased", "the price decreased", "the price stayed the same"],
    ["the trolley was moving", "the trolley was at rest"],
    ["the reaction is exothermic", "the reaction is endothermic"],
])
def test_options_that_exhaust_their_cases_are_no_false_dilemma(options):
    r = _either(options, list(range(len(options) - 1)))
    assert r.status is S.ENTAILED and "ARG-FD-001" not in codes(r)


@pytest.mark.parametrize("options", [["the plan raises taxes", "the plan cuts spending"], ["the team won the cup", "the team lost the final"]])
def test_control_options_that_do_not_exhaust_their_cases_are_a_false_dilemma(options):
    assert codes(_either(options, [0])).get("ARG-FD-001") == "warning"


def _link(fact: str, point: str, decoys: tuple[str, ...] = ()):
    symbols = B(a=fact, c=point)
    premises = [P("e", V("a"), fact, kind="general_knowledge"), P("l", IMP(V("a"), V("c")), f"{fact}, so {point}", note="link: so")]
    for i, text in enumerate(decoys):
        symbols[f"x{i}"] = ("Bool", text)
        premises.append(P(f"x{i}", V(f"x{i}"), text, kind="general_knowledge"))
    return codes(run(problem(premises, V("c"), symbols)))


def test_a_census_of_the_whole_population_concludes_most_validly():
    found = _link("all 1,000 residents were asked and 700 of the 1,000 residents supported the plan", "most residents supported the plan")
    assert "ARG-HG-001" not in found


def test_control_a_sample_drawn_on_a_wider_population_is_hasty():
    found = _link("9 of the 12 students in our class prefer online lessons", "most students in the country prefer online lessons")
    assert found.get("ARG-HG-001") == "warning"


def test_a_cause_read_into_one_patients_recovery_is_a_causal_leap_not_a_hasty_generalisation():
    found = _link("after six sessions of therapy the patient recovered", "the therapy cured the patient")
    assert found.get("ARG-CL-001") == "warning" and "ARG-HG-001" not in found


@pytest.mark.parametrize("decoys", [(), ("the shop was chosen randomly by the marketing team",),
                                    ("our science department uses a control group in its experiments",)])
def test_a_decoy_control_cue_hides_no_causal_leap(decoys):
    found = _link("sales rose after the advert ran in May", "the advert caused sales to rise", decoys)
    assert found.get("ARG-CL-001") == "warning" and "ARG-LINK-001" in found


def test_control_a_control_cue_in_the_links_own_fact_warrants_it():
    found = _link("shops randomly assigned to run the advert sold more than a control group of shops", "the advert caused sales to rise")
    assert "ARG-CL-001" not in found and "ARG-LINK-001" not in found


def test_a_cause_read_into_dated_bool_facts_is_a_causal_leap():
    symbols = B(a="the breakfast club opened in 2019", b="attendance rose in 2020", c="the breakfast club caused attendance to rise")
    r = run(problem([P("e1", V("a"), "the breakfast club opened in 2019", kind="general_knowledge"),
                     P("e2", V("b"), "attendance rose in 2020", kind="general_knowledge"),
                     P("l", IMP(AND(V("a"), V("b")), V("c")), "so the breakfast club caused attendance to rise", note="link: so")], V("c"), symbols))
    assert codes(r).get("ARG-CL-001") == "warning"


def test_control_a_duration_of_an_effect_reads_no_cause_into_a_sequence():
    found = _link("the effect of the drug was gone after seven days", "the effect of the drug is short-lived")
    assert "ARG-CL-001" not in found


def test_a_tautological_conclusion_is_vacuous_not_circular():
    either = {"op": "or", "args": [V("rose"), {"op": "not", "arg": V("rose")}]}
    data = problem_dict([{"id": "p1", "expr": either, "label": "prices either rose or did not rise in 2023", "grounding": {"kind": "specialist_inference"}}],
                        {"id": "C", "expr": either, "label": "the market changed or stayed the same"},
                        [{"name": "rose", "sort": "Bool", "meaning": "prices rose in 2023"}])
    claim, report = make_report("Prices either rose or did not rise in 2023, which proves the market changed or stayed the same.", subject="Economics",
                                role="point")
    result = Translator(FixtureTranslationProvider({claim.claim_id: json.dumps(output(data))})).translate(claim, report)
    assert result.status.value != "INVALID_FORMALIZATION" and not any("E112" in d for d in result.diagnostics)
    from epinoic_logic.engine.runner import verify
    from .test_argument_diagnostics import CFG
    assert any(d.code == "E108" for d in verify(result.problem, CFG).diagnostics)


def _knowledge_link(label: str):
    symbols = B(navy="Britain had the largest navy in 1914", win="Britain was certain to win the war")
    return codes(run(problem([P("f", V("navy"), "Britain had the largest navy in 1914", kind="task_setting", verified=True),
                              P("l", IMP(V("navy"), V("win")), label, kind="general_knowledge", note="rule")], V("win"), symbols)))


@pytest.mark.parametrize("label", ["so", "therefore", "link: so"])
def test_a_rule_note_on_a_label_that_records_no_rule_keeps_the_missing_link(label):
    found = _knowledge_link(label)
    assert "ARG-LINK-001" in found and "ARG-LINK-002" not in found


def test_control_a_rule_the_label_states_is_an_unchecked_rule():
    found = _knowledge_link("a country with the largest navy is certain to win a war")
    assert found.get("ARG-LINK-002") == "info" and "ARG-LINK-001" not in found
