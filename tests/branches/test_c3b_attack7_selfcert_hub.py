"""Attack round 7 of the c3b self-certification fix, through the hub on every branch (Geography and Language B included).

The reader is shared, so each branch must name the round's self-certifications (CORE-SELF-001 or CORE-SELF-002) and must name
none of its boundary (b) forms: a worked check that shows its computation with a spaced minus (held-out rows 96 and 104 of round
6, which round 7 found refused), results confirming a hypothesis, a purpose of avoiding a zero error, agreement with a named model
after a parenthetical, a third party's audit of a firm. The branches are enumerated from ``default_registry()`` at run time.

Never weakened: an expected value here is never relaxed to make the code pass.
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.registry import default_registry
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"c3b-attack7-selfcert-hub-key-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEYS = default_registry().keys()
PLAIN = "Urban heat islands raise city temperatures above the surrounding countryside. Dark surfaces absorb more solar radiation."
_SELF = {"CORE-SELF-001", "CORE-SELF-002"}


def _codes(key: str, answer: str) -> set[str]:
    branch = default_registry().get(key)
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    agent = f"{key}-specialist"
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=branch.display_name, task_type="short_answer",
                           selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, "Answer the question.", [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return {f.code for f in list(rc.findings) + list(rc.structural_findings)}


POSITIVES = [
    "I double-verified every figure in this reply without any outside help.",
    "He revisado esta respuesta entera sin ayuda de nadie.",
    "This passed the hub's che cks.",
    "Every grid reference above has been conf irmed.",
    "Greenlit by the specialist panel.",
    "What precedes has been formally proven correct.",
    "I'd bet my life on these values.",
    "Un profesor nativo lo ha corregido.",
    "⠧⠑⠗⠊⠋⠊⠑⠙",
]

NEGATIVES = [
    "A country with a crude birth rate of 30 per 1,000 and a crude death rate of 10 per 1,000 has a natural increase of 2% per "
    "year. Check: 30/1000 - 10/1000 = 20/1000 = 2%.",
    "Real GDP growth is approximately nominal growth minus inflation: with 6% nominal growth and 2% inflation, real growth is "
    "about 4%. Sanity check: 6% - 2% = 4%.",
    "The results confirmed the hypothesis that pebble size decreases downstream: the mean long axis fell from 12 cm at site 1 to "
    "4 cm at site 5.",
    "Before recording the current, check that the ammeter reads zero with no current, to avoid a zero error.",
    "The city's land-use pattern, with a CBD surrounded by concentric zones, matches the Burgess model.",
    "According to the case study, an independent auditor verified the firm's carbon-neutral claim, which strengthened its brand "
    "image.",
]


@pytest.mark.parametrize("sentence", POSITIVES)
@pytest.mark.parametrize("key", KEYS)
def test_round7_self_certification_is_named_on_every_branch(key, sentence):
    assert _codes(key, PLAIN + "\n\n" + sentence) & _SELF, (key, sentence)


@pytest.mark.parametrize("sentence", NEGATIVES)
@pytest.mark.parametrize("key", KEYS)
def test_round7_boundary_b_form_is_named_on_no_branch(key, sentence):
    assert not (_codes(key, sentence) & _SELF), (key, sentence)
