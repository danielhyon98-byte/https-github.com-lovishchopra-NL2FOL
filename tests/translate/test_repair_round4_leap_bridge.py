"""Repair round 4, ADV4-07: an unbridged leap between two named things (ARG-NS-003) stays one when another sentence of the
answer only names the two things. A sentence with no connective states the connection of the link's sides only when it
holds words of both and not only their names: "The Kaiser was Germany's emperor" or "Britain was worried about the Kaiser"
says who or where, not how a cousinship makes Britain declare war, so the leap "King George V was a cousin of the Kaiser,
so Britain declared war on Germany" is named. A word opening a sentence is a name when the answer or the sides write it as
one elsewhere ("Britain"), and a plain word otherwise ("Unemployment made ..."). Controls: a sentence that states the
connection with a word of either side's content ("The cousin relationship made war with Germany unavoidable", the pinned
"The Treaty of Versailles shaped how the Crash and mass unemployment hit Germany"), sides that share a word, and a side
that names nothing."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate import diag_argument

from ..argdiag_hub import CFG, KEY, _verifier

ANTE = "King George V was a cousin of the Kaiser"
CONS = "Britain declared war on Germany in August 1914"
LEAP = "King George V was a cousin of the Kaiser, so Britain declared war on Germany."


@pytest.mark.parametrize("names_only", [
    "The Kaiser was Germany's emperor.",
    "The King visited Germany in 1913.",
    "Britain was worried about the Kaiser.",
    "King George V and the Kaiser met in Berlin in 1913.",
])
def test_a_sentence_that_only_names_the_two_things_states_no_connection(names_only):
    assert diag_argument.unbridged_leap_reading([f"{names_only} {LEAP}"], ANTE, CONS) == LEAP
    assert diag_argument.unbridged_leap_reading([f"{LEAP} {names_only}"], ANTE, CONS) == LEAP


@pytest.mark.parametrize("bridge", [
    "The cousin relationship made war with Germany unavoidable.",
    "Family ties between the King and the Kaiser pushed Britain into war with Germany.",
])
def test_control_a_sentence_that_states_the_connection_with_a_word_of_a_side_is_a_bridge(bridge):
    assert diag_argument.unbridged_leap_reading([f"{bridge} {LEAP}"], ANTE, CONS) is None


def test_control_a_word_that_opens_a_sentence_and_is_never_written_as_a_name_is_a_plain_word():
    ante, cons = "unemployment rose sharply after the Wall Street Crash", "the Nazis came to power in Weimar Germany"
    leap = "Unemployment rose sharply after the Wall Street Crash, so the Nazis came to power."
    assert diag_argument.unbridged_leap_reading([leap], ante, cons) == leap
    bridged = f"Unemployment made desperate voters turn to the Nazis. {leap}"   # "Unemployment" opens both sentences: a plain word
    assert diag_argument.unbridged_leap_reading([bridged], ante, cons) is None


@pytest.mark.parametrize("text, ante, cons", [
    ("The Treaty of Versailles shaped how the Crash and mass unemployment hit Germany. The Wall Street Crash of 1929 caused mass "
     "unemployment in Germany, so the Treaty of Versailles was the main reason the Nazis rose to power.",
     "the Wall Street Crash of 1929 caused mass unemployment in Germany", "the Treaty of Versailles was the main reason the Nazis rose to power"),
    ("The Kaiser ruled Germany. Germany lost the war, so Germany signed the Treaty of Versailles.", "Germany lost the war",
     "Germany signed the Treaty of Versailles"),
    ("The Kaiser ruled Germany. Prices rose, so demand fell.", "prices rose", "demand fell"),
])
def test_control_the_pinned_shapes_stay_unread(text, ante, cons):
    assert diag_argument.unbridged_leap_reading([text], ante, cons) is None


# ------------------------------------------------------------------ end to end: the delivered answer, the receipt

def _proposal() -> dict:
    g = {"source_refs": [], "certainty": "established"}
    return {"problem": {"ir_version": "1.0", "problem_id": "p", "request_id": "x", "claim_id": "x", "query": "entailment",
                        "symbols": [{"name": "cousin", "sort": "Bool", "meaning": ANTE, "grounding": {"kind": "general_knowledge", **g}},
                                    {"name": "war", "sort": "Bool", "meaning": CONS, "grounding": {"kind": "specialist_inference", **g}}],
                        "premises": [{"id": "e1", "expr": {"op": "var", "name": "cousin"}, "label": ANTE, "materiality": "material",
                                      "grounding": {"kind": "general_knowledge", **g}},
                                     {"id": "l1", "expr": {"op": "implies", "left": {"op": "var", "name": "cousin"}, "right": {"op": "var", "name": "war"}},
                                      "label": "the King was the Kaiser's cousin, so Britain declared war", "materiality": "material",
                                      "grounding": {"kind": "specialist_inference", **g}}],
                        "conclusion": {"id": "C", "expr": {"op": "var", "name": "war"}, "label": "Britain declared war on Germany",
                                       "materiality": "material", "grounding": {"kind": "specialist_inference", **g}}},
            "interpretation": {"reading": "as written", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}


def _ns3(answer: str) -> list:
    case = {"id": "leap", "fidelity_review": "faithful", "translations": [{"contains": "so Britain declared war on Germany", "proposal": _proposal()}]}
    plan = WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"])
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG)
    ch = hub.open_task(plan)
    served: dict = {}
    ch.verify_claim_fn = _verifier(json.loads(json.dumps(case)), served)
    m, _req, _rq = hub.dispatch("t", "history-specialist", "Explain why Britain entered the First World War in August 1914. [4 marks]", [])
    hub.receive("t", m.message_id, answer, agent_id="history-specialist", report_id="r1")
    return [d for o in served.values() for d in (o.named_diagnostics or []) if d.code == "ARG-NS-003"]


def test_the_leap_is_named_on_the_receipt_when_another_sentence_only_names_the_things():
    [d] = _ns3(f"The Kaiser was Germany's emperor. {LEAP}")
    assert d.severity == "warning" and d.defect == "leap_in_logic"


def test_control_the_leap_is_not_named_when_the_answer_states_the_connection():
    assert _ns3(f"The cousin relationship made war with Germany unavoidable. {LEAP}") == []
