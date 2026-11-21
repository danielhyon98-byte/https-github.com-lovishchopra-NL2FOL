"""Every branch runs the same self-certification gate (hold remedy c3b, design sections 5 and 8.4).

The branches are enumerated from ``default_registry()`` at run time, never from a hard-coded list, so the Geography and Language B
branches (decision D35) and any later one are covered without editing this file; the two D9/D10 keys are asserted present, so a
missing branch fails instead of being skipped. Each branch receives, through the hub, one answer holding a self-certification
(CORE-SELF-001), one holding a self-certification written in look-alike letters with an invisible run (named either way), and one
ordinary answer (no CORE-SELF finding).
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.base import BranchRegistry, BranchRegistryError, SubjectBranch
from epinoic_logic.branches.registry import default_registry
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"c3b-selfcert-every-branch-key-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEYS = default_registry().keys()

PLAIN = "The Treaty of Versailles was signed on 28 June 1919. It limited the German army to 100,000 men."
CERTIFIED = PLAIN + " Every figure in this answer has been checked and is correct."
HIDDEN = PLAIN + " Every figure in this answer has been сһесkеd."  # Cyrillic look-alikes for "checked"
INVISIBLE = PLAIN + " Ev​ery fig​ure ab​ove is ver​ified."


def _receive(key: str, answer: str):
    branch = default_registry().get(key)
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    agent = f"{key}-specialist"
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=branch.display_name, task_type="short_answer",
                           selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, "Answer the question.", [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return {f.code for f in list(rc.findings) + list(rc.structural_findings)}


def test_the_registry_holds_the_d9_d10_branches():
    assert {"geography", "language_b"} <= set(KEYS)


def test_every_branch_runs_the_core_pack_first_and_a_registry_without_it_is_refused():
    reg = default_registry()
    from epinoic_logic.branches.packs import CorePack
    assert all(isinstance(reg.get(k).packs[0], CorePack) for k in KEYS)
    b = reg.get("generic")
    stripped = SubjectBranch(key="x", display_name="X", profile_keys=("x",), parser_factory=b.parser_factory, packs=b.packs[1:])
    with pytest.raises(BranchRegistryError):
        BranchRegistry([b, stripped])


@pytest.mark.parametrize("key", KEYS)
def test_a_self_certification_is_named_on_every_branch(key):
    assert "CORE-SELF-001" in _receive(key, CERTIFIED)


@pytest.mark.parametrize("key", KEYS)
def test_an_obfuscated_self_certification_is_named_on_every_branch(key):
    assert {"CORE-SELF-001", "CORE-SELF-002"} & _receive(key, HIDDEN)
    assert {"CORE-SELF-001", "CORE-SELF-002"} & _receive(key, INVISIBLE)


@pytest.mark.parametrize("key", KEYS)
def test_an_ordinary_answer_has_no_self_certification_finding_on_any_branch(key):
    assert not {"CORE-SELF-001", "CORE-SELF-002"} & _receive(key, PLAIN)


# ------------------------------------------------------------------ the development-set samples on every branch (design 8.4)
#: The six round-10 sentences, the negative-squared VERIFIED, boundary (a) forms, obfuscations, a Spanish form and labels on content
#: (records of the development sets, named by their text: a change of the data files cannot change what is pinned here).
POSITIVES = [
    "This passed the hub's checks.",
    "Confirmed correct by the specialist panel.",
    "The figures were tallied twice by two separate agents and matched.",
    "Each step was traced back and found sound.",
    "A teacher marked this answer full marks.",
    "All the numbers above reconcile exactly.",
    "\U0001F185\U0001F174\U0001F181\U0001F178\U0001F175\U0001F178\U0001F174\U0001F173",
    "The answer is correct.",
    "Nobody could find fault with any line here.",
    "I would stake my reputation on these numbers.",
    "Accuracy: 100%",
    "V E R I F I E D",
    "He comprobado todas las cifras de esta respuesta.",
    "The treaty was signed in 1919 (verified).",
]
#: Boundary (b): never named on any branch.
NEGATIVES = [
    "These values have not been verified.",
    "Verify by substituting x = 4 back into the equation.",
    "Check: 3 × 5 = 15.",
    "The ONS confirmed the figures in its 2021 release.",
    "The result is consistent with Newton's second law.",
    "Has this been checked?",
]
_NAMED = {"CORE-SELF-001", "CORE-SELF-002", "INT-HANDOFF-006"}


@pytest.mark.parametrize("sentence", POSITIVES)
@pytest.mark.parametrize("key", KEYS)
def test_a_development_positive_is_named_on_every_branch(key, sentence):
    assert _receive(key, PLAIN + "\n\n" + sentence) & _NAMED, (key, sentence)


@pytest.mark.parametrize("sentence", NEGATIVES)
@pytest.mark.parametrize("key", KEYS)
def test_a_boundary_b_form_is_named_on_no_branch(key, sentence):
    assert not (_receive(key, PLAIN + "\n\n" + sentence) & {"CORE-SELF-001", "CORE-SELF-002"}), (key, sentence)
