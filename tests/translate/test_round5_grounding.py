"""Quotation grounding found wanting by the round-5 adversarial overseer: a correct quotation of the supplied poem whose em
dashes are typed as spaced hyphens or spaced en dashes, and a quotation that runs across a stanza break of verse dialogue
leaving out the poem's own speech mark at the break, were reported as invented quotations (INT-REQ-003, ES-SRC-001).
Both are now located: the spaced dash as the same words, the stanza span as a form difference (INT-REQ-010)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.grounding import FORM_DIFFERS, NOTE_EDGE_MARKS, locate_quotation, locate_quotation_inexact
from epinoic_logic.translate.contracts import SuppliedText

R5 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r5_material.json").read_text())
EN_P4 = R5["specialists"]["en-p4"]
HARDY = EN_P4["supplied_texts"][0]["text"]
CARROLL = R5["specialists"]["en-t9"]["supplied_texts"][0]["text"]
KEY = b"round5-grounding-test-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
GENUINE_Q01 = "He thought he'd 'list, perhaps, / Off-hand like—just as I— / Was out of work—had sold his traps—"


@pytest.mark.parametrize("excerpt", [
    "He thought he'd 'list, perhaps, / Off-hand like - just as I - / Was out of work - had sold his traps -",   # spaced hyphens
    "He thought he'd 'list, perhaps, / Off-hand like – just as I – / Was out of work – had sold his traps –",   # spaced en dashes
    "Off-hand like — just as I —",                                                                             # spaced em dashes
    "Off-hand like--just as I--",                                                                              # double hyphens
])
def test_a_dash_typed_with_spaces_is_the_same_quotation(excerpt):
    assert locate_quotation(excerpt, HARDY) is not None


@pytest.mark.parametrize("text,excerpt", [
    (HARDY, "That's clear enough; although / He thought he'd 'list, perhaps"),            # stanza 3-4, the opening speech mark left out
    (HARDY, "Right many a nipperkin! / But ranged as infantry"),                            # stanza 1-2 with ' / '
    (HARDY, "Right many a nipperkin! // But ranged as infantry"),                           # with ' // '
    (HARDY, "Right many a nipperkin! But ranged as infantry"),                              # with no break mark
    (CARROLL, "And the mome raths outgrabe. / Beware the Jabberwock, my son!"),             # Jabberwocky stanza 1-2
    (CARROLL, "The frumious Bandersnatch! / He took his vorpal sword in hand"),             # stanza 2-3, the closing mark left out
])
def test_a_stanza_span_without_the_poems_own_speech_mark_is_a_form_difference(text, excerpt):
    assert locate_quotation(excerpt, text) is None
    found = locate_quotation_inexact(excerpt, text)
    assert found is not None and NOTE_EDGE_MARKS in found[1]


def test_a_changed_word_across_a_stanza_break_is_still_not_found():
    assert locate_quotation_inexact("Right many a nipperkin! / But ranged as cavalry", HARDY) is None
    assert locate_quotation("Off-hand like - just as we -", HARDY) is None and locate_quotation_inexact("Off-hand like - just as we -", HARDY) is None


def test_the_span_keeping_the_poems_own_mark_is_found_as_before():
    assert locate_quotation("That's clear enough; although / \"He thought he'd 'list, perhaps", HARDY) is not None


def _deliver(text: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="plan-en-p4", request_id="req-en-p4", task_id="en-p4", subject=EN_P4["subject"], task_type="analytical_paragraph",
                           selected_agent_ids=["english-specialist", "dummy-combinator"], allowed_document_ids=["doc-mhk"]))
    m, _, _ = hub.dispatch("en-p4", "english-specialist", EN_P4["question"], [SuppliedText(**EN_P4["supplied_texts"][0])])
    return hub.receive("en-p4", m.message_id, text, agent_id="english-specialist", report_id="rep-en-p4-v")


@pytest.mark.parametrize("variant", ["dashes-hyphens", "stanza-span", "span-12-slash", "span-12-dslash", "span-12-noslash"])
def test_r5_adversarial_variants_are_never_invented_quotations(variant):
    text = EN_P4["response_text"]
    if variant == "dashes-hyphens":
        text = text.replace(GENUINE_Q01, GENUINE_Q01.replace("—", " - ").replace("  ", " ").replace(" -\"", " -\""))
    else:
        span = {"stanza-span": "That's clear enough; although / He thought he'd 'list, perhaps",
                "span-12-slash": "Right many a nipperkin! / But ranged as infantry",
                "span-12-dslash": "Right many a nipperkin! // But ranged as infantry",
                "span-12-noslash": "Right many a nipperkin! But ranged as infantry"}[variant]
        text = text.replace(" The final stanza sets", f" The stanza break falls mid-thought: \"{span}\". The final stanza sets")
    reply, rc = _deliver(text)
    assert reply is not None
    assert not [f for f in rc.findings if f.code == "INT-REQ-003"], [f.message for f in rc.findings if f.code == "INT-REQ-003"]
    assert not [sf for sf in rc.structural_findings if sf.code.endswith("-SRC-001") and sf.severity == "error"]
    if variant != "dashes-hyphens":
        assert any(f.code == "INT-REQ-010" and f.severity == "warning" for f in rc.findings)
        assert all(FORM_DIFFERS in f.message or "differs only in form" in f.message for f in rc.findings if f.code == "INT-REQ-010")
