"""STEM review S3: a generic calculation verb is no evidence that a claim addresses an item that names what it wants
(docs/STEM_DESIGN.md, section 11.2). "Calculate the acceleration" is addressed only by a claim about the acceleration (its
name, its unit, its symbol, the item's own figures), never by unrelated arithmetic; three requested quantities answered by
one irrelevant sum leave all three unaddressed. The positive controls (a genuine calculation, a claim about two
quantities, notation the request uses) must still address their items."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.channel.bus import _COMMAND_STEMS, _terms
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem.hub_hooks import STEM_HOOKS

KEY = b"stem-review-coverage-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
MATHS = "Mathematics: Analysis and Approaches"


def send(ask: str, answer: str, subject: str = "Physics"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=["spec"]))
    m, req, rq = hub.dispatch("t", "spec", ask)
    assert m is not None and rq.status is TransmissionStatus.ACCEPTED
    reply, rc = hub.receive("t", m.message_id, answer, agent_id="spec", report_id="r")
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    return req, rc


def coverage(rc) -> dict[str, tuple[bool, list[str]]]:
    return {c.item_id: (c.addressed, list(c.addressed_by_claim_ids)) for c in rc.coverage}


# ----------------------------------------------------------------------------------------- the reviewer's probes


@pytest.mark.parametrize("ask", ["Calculate the acceleration.", "Find the distance.", "Calculate the efficiency.", "Determine the wavelength."])
def test_unrelated_arithmetic_addresses_no_item_that_names_a_quantity(ask):
    _req, rc = send(ask, "2 + 2 = 4.")
    assert coverage(rc) == {"i1": (False, [])}
    assert [f.code for f in rc.findings] == ["INT-REQ-004"] and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    assert [(c.constraint_id, c.satisfied) for c in rc.formal_checks] == [("stem-eq-1", True)]  # the sum itself is still checked and holds


def test_three_requested_quantities_answered_by_one_irrelevant_sum_are_all_unaddressed():
    req, rc = send("Calculate the acceleration. Calculate the force. Calculate the wavelength.", "2 + 2 = 4.")
    assert len(req.items) == 3
    assert coverage(rc) == {"i1": (False, []), "i2": (False, []), "i3": (False, [])}
    assert [f.code for f in rc.findings].count("INT-REQ-004") == 3


def test_a_genuine_acceleration_calculation_still_addresses_the_item():
    _req, rc = send("Calculate the acceleration.", "a = (20 - 0)/4.0 = 5.0 m s⁻²")
    assert coverage(rc) == {"i1": (True, ["s1.1"])} and rc.status is TransmissionStatus.ACCEPTED and rc.findings == []


# ----------------------------------------------------------------------------------- one claim, several items


def test_a_claim_addresses_each_item_it_is_about_and_no_other():
    _req, both = send("Calculate the acceleration. Calculate the force.", "a = 20/4.0 = 5.0 m s⁻² and F = ma = 2.0 × 5.0 = 10 N")
    assert coverage(both) == {"i1": (True, ["s1.1"]), "i2": (True, ["s1.1"])}
    _req, one = send("Calculate the acceleration. Calculate the force.", "a = 20/4.0 = 5.0 m s⁻².")
    assert coverage(one) == {"i1": (True, ["s1.1"]), "i2": (False, [])}


def test_a_claim_computing_another_quantity_from_the_same_data_does_not_address_the_item():
    ask = "Calculate the acceleration of a car that speeds up from 0 to 20 m/s in 4.0 s. Calculate the distance it travels."
    _req, distance_only = send(ask, "s = ½ × 20 × 4.0 = 40 m")
    assert coverage(distance_only) == {"i1": (False, []), "i2": (True, ["s1.1"])}
    _req, both = send(ask, "a = (20 - 0)/4.0 = 5.0 m s⁻²\ns = ½ × 20 × 4.0 = 40 m")
    assert coverage(both) == {"i1": (True, ["s1.1"]), "i2": (True, ["s1.2"])}


def test_an_intermediate_step_is_not_counted_as_answering_an_item_it_is_not_about():
    answer = "Δv = 20 - 0 = 20\na = Δv/Δt = 20/4.0 = 5.0 m s⁻²"
    _req, rc = send("Calculate the acceleration.", answer)
    addressed, claims = coverage(rc)["i1"]
    assert addressed and claims == ["s1.2"]  # before the review both lines counted, the first only through 'calculate'


# --------------------------------------------- evidence the STEM hooks lend: units, symbols, figures, relation kinds


@pytest.mark.parametrize("subject,ask,answer", [
    ("Physics", "Convert 1500 mm into metres.", "1500 mm = 1.5 m"),
    ("Physics", "Convert 1.5 h into minutes.", "1.5 h = 90 min"),
    ("Physics", "Convert 25 °C into kelvin.", "25 °C = 298 K"),
    (MATHS, "Find S₁₀.", "$S_{10} = \\frac{10}{2}(2 \\times 3 + 9 \\times 4) = 210$"),
    (MATHS, "Find the gradient of the line through (1, 3) and (5, 7).", "m = (7 - 3)/(5 - 1) = 4/4 = 1"),
    (MATHS, "Show that its gradient is m = 1.", "m = (7 − 3)/(5 − 1) = 1"),
    (MATHS, "Solve the inequality.", "2x − 3 < 7 ⇒ 2x < 10 ⇒ x < 5"),
    (MATHS, "For f(x) = x³ − 2x, find the gradient of the curve at x = 2.", "For f(x) = x³ − 2x, f′(x) = 3x² − 2, so f′(2) = 3 × 2² − 2 = 10."),
    ("Mathematics: Applications and Interpretation", "A population fell from 65 to 52. Calculate the percentage change.", "$\\frac{52 - 65}{65} \\times 100 = -20\\%$"),
    ("Computer Science", "Simplify or verify the Boolean expression.", "By De Morgan's law, ¬(A ∧ B) = ¬A ∨ ¬B."),
    ("Computer Science", "Convert 1011 in binary to denary and FF in hexadecimal to denary.", "1011₂ = 8 + 0 + 2 + 1 = 11 and FF₁₆ = 15 × 16 + 15 = 255"),
    ("Physics", "Calculate the efficiency.", "Efficiency = 300/500 × 100 = 60%"),
])
def test_genuine_answers_in_the_requests_notation_address_their_item(subject, ask, answer):
    _req, rc = send(ask, answer, subject)
    assert all(addressed for addressed, _claims in coverage(rc).values()), coverage(rc)
    assert not [f for f in rc.findings if f.code == "INT-REQ-004"]


@pytest.mark.parametrize("subject,ask", [
    ("Physics", "Convert 1500 mm into metres."),
    (MATHS, "Find S₁₀."),
    (MATHS, "Find the gradient of the line through (1, 3) and (5, 7)."),
    ("Computer Science", "Simplify or verify the Boolean expression."),
    ("Physics", "Calculate the acceleration of a car that speeds up from 0 to 20 m/s in 4.0 s."),
])
def test_the_same_items_are_not_addressed_by_unrelated_arithmetic(subject, ask):
    _req, rc = send(ask, "2 + 2 = 4.", subject)
    assert coverage(rc) == {"i1": (False, [])}


def test_an_item_that_names_nothing_beyond_its_imperative_is_addressed_by_a_computing_claim():
    _req, rc = send("Solve 3x + 5 = 20.", "3x = 15, so x = 5.", MATHS)
    assert coverage(rc) == {"i1": (True, ["m1.1"])}


def test_the_topic_evidence_hook_needs_a_computation_and_the_items_own_figures_or_symbols():
    claim = "m = (7 - 3)/(5 - 1) = 4/4 = 1"
    assert STEM_HOOKS.topic_evidence("Find the gradient of the line through (1, 3) and (5, 7).", claim, claim, None, "mathematics_aa")
    assert not STEM_HOOKS.topic_evidence("Calculate the acceleration.", "2 + 2 = 4.", "2 + 2 = 4.", None, "physics")
    # one shared single-digit figure is no evidence: '2 + 2 = 4' is not about 'the acceleration at t = 2 s'
    assert not STEM_HOOKS.topic_evidence("Calculate the acceleration at t = 2 s.", "2 + 2 = 4.", "2 + 2 = 4.", None, "physics")
    # a line that computes nothing is no evidence, whatever figures it shares
    given = "Given: d = 120 m and t = 8 s."
    assert not STEM_HOOKS.topic_evidence("Calculate the speed if d = 120 m and t = 8 s.", given, given, None, "physics")
    assert STEM_HOOKS.topic_evidence("x", "", "", None, "physics") is False  # total: never raises


def test_a_symbol_the_item_gives_a_value_for_is_an_input_and_no_evidence():
    speed = "Calculate the speed if d = 120 m and t = 8 s."
    assert coverage(send(speed, "t = 2 + 2 = 4.")[1]) == {"i1": (False, [])}  # recomputing a given symbol answers nothing
    assert coverage(send(speed, "v = d/t = 120/8 = 15 m/s")[1]) == {"i1": (True, ["s1.1"])}
    shown = "Given that d = 120 m and t = 8 s, show that v = 15 m/s."
    assert coverage(send(shown, "t = 2 + 2 = 4.")[1]) == {"i1": (False, [])}  # the target is v, stated after 'show that'
    assert coverage(send(shown, "v = 120/8 = 15 m/s")[1]) == {"i1": (True, ["s1.1"])}
    series = "Given u₁ = 3 and d = 4, find S₁₀."
    assert coverage(send(series, "u₁ = 1 + 2 = 3", MATHS)[1]) == {"i1": (False, [])}
    assert coverage(send(series, "$S_{10} = \\frac{10}{2}(2 \\times 3 + 9 \\times 4) = 210$", MATHS)[1]) == {"i1": (True, ["m1.1"])}
    # the hook itself: the input is no evidence, the asked symbol and the show-that target are
    assert not STEM_HOOKS.topic_evidence(speed, "t = 2 + 2 = 4", "t = 2 + 2 = 4", None, "physics")
    assert not STEM_HOOKS.topic_evidence(shown, "t = 2 + 2 = 4", "t = 2 + 2 = 4", None, "physics")
    assert STEM_HOOKS.topic_evidence(shown, "v = 120/8 = 15 m/s", "v = 120/8 = 15 m/s", None, "physics")
    target = "m = (7 − 3)/(5 − 1) = 1"
    assert STEM_HOOKS.topic_evidence("Show that its gradient is m = 1.", target, target, None, "mathematics_aa")


# ------------------------------------------------- items that name what they ask for in notation, not in words


NOTATION_ITEMS = [
    (MATHS, "Solve 3x + 5 = 20.", "3x = 20 − 5 = 15, so x = 15/3 = 5."),
    (MATHS, "Solve x² + 4 = 0.", "The discriminant is b² − 4ac = 0² − 4 × 1 × 4 = −16 < 0, so the roots are complex: x = ±2i."),
    (MATHS, "Simplify √50.", "√50 = √25 × √2 = 5√2"),
    (MATHS, "Simplify 2³ × 2⁴ and evaluate it.", "2³ × 2⁴ = 2⁷ = 128"),
    (MATHS, "Find u₆ and S₅.", "u₆ = 3 × 2⁵ = 96 and S₅ = 3(2⁵ − 1)/(2 − 1) = 93"),
    (MATHS, "Given f(x) = x² − 3x, find f(5).", "f(5) = 5² − 3 × 5 = 25 − 15 = 10"),
    (MATHS, "Find the value of k.", "k = 6/2 = 3"),
    (MATHS, "Evaluate 16^(3/4) without a calculator.", "$16^{3/4} = (\\sqrt[4]{16})^3 = 2^3 = 8$"),
    ("Physics", "Convert 72 km h⁻¹ into m s⁻¹.", "72 km h⁻¹ = 72 × 1000/3600 = 20 m s⁻¹"),
    ("Physics", "Calculate v if d = 120 m and t = 8 s.", "v = d/t = 120/8 = 15 m/s"),
]


@pytest.mark.parametrize("subject,ask,_genuine", NOTATION_ITEMS)
def test_unrelated_arithmetic_addresses_no_item_that_names_what_it_asks_for_in_notation(subject, ask, _genuine):
    # before: every one of these was addressed by '2 + 2 = 4' through the computing command words alone
    _req, rc = send(ask, "2 + 2 = 4.", subject)
    assert coverage(rc) == {"i1": (False, [])}
    assert "INT-REQ-004" in [f.code for f in rc.findings]


@pytest.mark.parametrize("subject,ask,genuine", NOTATION_ITEMS)
def test_a_genuine_answer_to_an_item_in_notation_addresses_it(subject, ask, genuine):
    _req, rc = send(ask, genuine, subject)
    assert coverage(rc)["i1"][0] is True, coverage(rc)
    assert not [f for f in rc.findings if f.code == "INT-REQ-004"]


def test_an_item_that_names_neither_a_topic_nor_notation_keeps_the_plain_reading():
    assert not STEM_HOOKS.names_notation("Find the final value.", "mathematics_ai")
    assert not STEM_HOOKS.names_notation("(b) Give your answer to 3 significant figures. [2 marks]", "mathematics_ai")  # a label and form only
    assert STEM_HOOKS.names_notation("Solve 3x + 5 = 20.", "mathematics_aa")
    _req, rc = send("Find the final value.", "A = 1000 × 1.05³ = 1157.63", "Mathematics: Applications and Interpretation")
    assert coverage(rc) == {"i1": (True, ["m1.1"])}


def test_shared_single_digit_figures_are_no_evidence_by_coincidence():
    # before: '2 + 2 = 4' shared the figures 2 and 4 with these items and addressed them
    trolley = "Calculate the acceleration of a trolley that reaches 4 m/s in 2 s."
    assert coverage(send(trolley, "2 + 2 = 4.")[1]) == {"i1": (False, [])}
    assert coverage(send(trolley.replace("4 m/s in 2 s", "4.0 m/s in 2.0 s"), "2 + 2 = 4.")[1]) == {"i1": (False, [])}
    force = "Calculate the force on a 2 kg mass accelerating at 4 m/s²."
    assert coverage(send(force, "4 − 2 = 2")[1]) == {"i1": (False, [])}
    # positive controls: the genuine answers, and figures that cannot coincide so easily
    assert coverage(send(trolley, "a = 4/2 = 2 m s⁻²")[1]) == {"i1": (True, ["s1.1"])}
    assert coverage(send(force, "F = ma = 2 × 4 = 8 N")[1]) == {"i1": (True, ["s1.1"])}
    gradient = "Find the gradient of the line through (1, 3) and (5, 7)."
    assert STEM_HOOKS.topic_evidence(gradient, "m = (7 - 3)/(5 - 1) = 1", "m = (7 - 3)/(5 - 1) = 1", None, "mathematics_aa")
    assert not STEM_HOOKS.topic_evidence(gradient, "7 - 3 = 4", "7 - 3 = 4", None, "mathematics_aa")  # two single digits weigh two


def test_the_unknowns_of_an_equation_to_solve_are_asked_and_the_symbols_of_a_formula_are_not():
    claim = "x = (3 + 7)/2 = 5"
    assert STEM_HOOKS.topic_evidence("Solve log x + log(x − 3) = 1.", claim, claim, None, "mathematics_aa")
    assert not STEM_HOOKS.topic_evidence("Simplify log 20 + log 5.", claim, claim, None, "mathematics_aa")  # no equation to solve
    formula = "Calculate the acceleration using v = u + at."
    assert not STEM_HOOKS.topic_evidence(formula, "t = 2 + 2 = 4", "t = 2 + 2 = 4", None, "physics")
    kc = "$K_c = \\frac{(0.020)^2}{(0.50)(0.10)^3} = 0.80$"
    assert STEM_HOOKS.topic_evidence("Calculate Kc for N₂(g) + 3H₂(g) ⇌ 2NH₃(g).", kc, kc, None, "chemistry")


# ------------------------------------------------------------------------------------------- the general rule


def test_a_shared_imperative_alone_addresses_no_item_on_any_branch():
    _req, rc = send("Calculate the profit margin.", "We calculate 2 + 2 = 4.", "Business Management")
    assert coverage(rc)["i1"] == (False, [])
    _req, ok = send("Calculate the profit margin.", "The profit margin is 25%.", "Business Management")
    assert coverage(ok)["i1"][0] is True
    _req, en = send("Analyse how the poet presents nature.", "The poet presents nature as indifferent to human ambition.", "English A: Literature")
    assert coverage(en)["i1"][0] is True


def test_the_command_vocabulary_holds_command_and_form_words_and_no_quantity():
    for word in ("calculate", "determine", "find", "solve", "evaluate", "value", "answer", "significant", "figures", "exact", "given"):
        assert _terms(word) <= _COMMAND_STEMS, word
    for word in ("acceleration", "force", "wavelength", "distance", "efficiency", "gradient", "concentration", "percentage", "boolean", "inequality"):
        assert not (_terms(word) & _COMMAND_STEMS), word
