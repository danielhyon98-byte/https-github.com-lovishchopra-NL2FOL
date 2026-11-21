"""Every release path refuses a self-certification of the one reader, and lets the boundary (b) forms through (hold remedy c3b,
design section 8.4; rules ``selfcert-1``).

The round-10 push check delivered six sentences and a word in negative-squared letters through the overseer-selected fallback. The
gate now reads the class by meaning (``epinoic_logic.selfcert``) on every path with the same reading context built from the ROUTER's
journaled request. This file pins, with the expected values fixed here:

* the fallback candidate is never deliverable for a self-certification, on every subject branch of the c2 gate tests (Geography and
  Language B included), whatever the reviews' accuracy, and the not-checked mode withholds it as well;
* the router's documented decision (``consolidate.delivery_decision``) refuses it, named by rule and place, never by its words;
* the overseer port maps both refusal reasons of the gate (self-certification-gate and unread-text) to ``not_deliverable``;
* the combined answer carrying a combinator's self-report is never released;
* the boundary (b) forms of the development set are delivered where nothing else refuses them (a negated or uncertain assessment,
  an imperative method step, a worked check, an outside source's check, agreement with a named reference).

The samples are records of the development sets (``tests/selfcert/data``), named here by their text so a change of the data files
cannot silently change what is pinned.
"""
from __future__ import annotations

import pytest

import epinoic_overseer.port as P
from epinoic_overseer.consolidate import delivery_decision
from epinoic_overseer.delivery_policy import SELF_CERTIFICATION_RULE, DeliveryConfig

from .test_c2_hold_round2_gate import _deliver
from .test_c2_hold_round3_gate import _consolidated, _release
from .test_c2_hold_self_certification_gate import IDS, SUBJECTS, _gate

#: The six sentences the round-10 push check reproduced as delivered, and the negative-squared VERIFIED (U+1F185 ...).
ROUND10 = [
    "This passed the hub's checks.",
    "Confirmed correct by the specialist panel.",
    "The figures were tallied twice by two separate agents and matched.",
    "Each step was traced back and found sound.",
    "A teacher marked this answer full marks.",
    "All the numbers above reconcile exactly.",
    "\U0001F185\U0001F174\U0001F181\U0001F178\U0001F175\U0001F178\U0001F174\U0001F173",
]
#: Boundary (a) forms and obfuscations of the class (a sample of the development set's positives).
CLASS_SAMPLE = [
    "The answer is correct.",
    "Nobody could find fault with any line here.",
    "I would stake my reputation on these numbers.",
    "Accuracy: 100%",
    "Correctness guaranteed.",
    "V E R I F I E D",
    "Every figure in this answer has been сһесkеd.",
]
#: Boundary (b): never a self-certification, delivered where nothing else refuses it.
BOUNDARY_B = [
    "These values have not been verified.",
    "Verify by substituting x = 4 back into the equation.",
    "Check: 3 × 5 = 15.",
    "The ONS confirmed the figures in its 2021 release.",
    "The result is consistent with Newton's second law.",
]


@pytest.mark.parametrize("sentence", ROUND10)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_the_round10_forms_are_never_deliverable_on_any_branch(subject, agent, task_type, base, sentence):
    _rc, decision = _deliver(subject, agent, task_type, base + "\n\n" + sentence)
    c, reasons, _formal = _gate(decision)
    assert not c.deliverable and reasons, (subject, sentence, c.integrity_reasons)
    assert not decision.delivered and decision.mode != "formally_checked"
    assert sentence not in " ".join(c.integrity_reasons)  # named by rule and place, never by its words


@pytest.mark.parametrize("sentence", CLASS_SAMPLE)
@pytest.mark.parametrize("subject,agent,task_type,base", [s for s in SUBJECTS if s[0] in ("History", "Geography", "Spanish B", "Physics")],
                         ids=["History", "Physics", "Geography", "Spanish B"])
def test_a_class_sample_is_never_deliverable_and_the_not_checked_mode_withholds_it(subject, agent, task_type, base, sentence):
    _rc, decision = _deliver(subject, agent, task_type, base + "\n\n" + sentence)
    [c] = decision.receipt.fallback.candidates
    assert not c.deliverable and not decision.delivered, (subject, sentence, c.integrity_reasons)
    _rc, decision = _deliver(subject, agent, task_type, base + "\n\n" + sentence,
                             config=DeliveryConfig(on_overseer_timeout="deliver_canonical_not_checked"))
    assert not decision.delivered, (subject, sentence, decision.mode)


@pytest.mark.parametrize("sentence", ROUND10 + CLASS_SAMPLE[:3])
def test_the_routers_decision_refuses_the_class(sentence):
    subject, agent, task_type, base = SUBJECTS[0]
    hub, resp = _consolidated(subject, agent, task_type, base + "\n\n" + sentence)
    try:
        d = delivery_decision(resp, hub.auditor.keyring, hub=hub)
        assert not d.allowed and (SELF_CERTIFICATION_RULE in d.reason or "unread-text" in d.reason), d.reason
        assert sentence not in d.reason
    finally:
        hub.close()


@pytest.mark.parametrize("sentence", BOUNDARY_B)
def test_the_routers_decision_allows_the_boundary_b_forms(sentence):
    subject, agent, task_type, base = SUBJECTS[0]
    hub, resp = _consolidated(subject, agent, task_type, base + "\n\n" + sentence)
    try:
        d = delivery_decision(resp, hub.auditor.keyring, hub=hub)
        assert SELF_CERTIFICATION_RULE not in d.reason and "unread-text" not in d.reason, d.reason
    finally:
        hub.close()


@pytest.mark.parametrize("reason", [
    "the deliverable answer carries text the self-certification reader cannot read (rule unread-text)",
    "rule unread-text could not read the deliverable answer (ValueError)",
    "rule self-certification-gate could not read the deliverable answer (KeyError)",
])
def test_the_port_maps_every_gate_refusal_to_not_deliverable(reason):
    assert P.refusal_label(reason) == "not_deliverable"


@pytest.mark.parametrize("sentence", ["All synthesized claims were confirmed by the hub.", "Fact: the treaty was signed in 1919.",
                                      "The combined answer matches the specialists' reports.", "Confirmed correct by the specialist panel."])
def test_a_combined_answer_that_certifies_itself_is_never_released(sentence):
    d = _release(sentence)
    assert not d.allowed and ("self-certification-gate" in d.reason or "error-level" in d.reason), d.reason
