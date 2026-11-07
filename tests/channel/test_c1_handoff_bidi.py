"""Round-8 clearance (integrated round c1), handoff fixer: a bidirectional control in a specialist's response (the STEM fixer's
handoff item 2; STEM-integration finding 17, major).

A bidirectional embedding, override or isolate (U+202A to U+202E, U+2066 to U+2069) makes the text a reader is shown differ from the
text every check of the hub reads: 'a = (20 − 0)/4.0 = U+202E 5.0 U+202C' is displayed as 0.5 while the check read 5.0 and held. The
STEM pack declines to decide such a relation (rule bidi-control), but a humanities answer's claims, which it never reads, were still
translated, located and checked in the order the hub reads them, and the receipt certified a date or a quotation the student does not
see. The channel now refuses a specialist's response whose own text holds one (rule bidi-text, INT-REQ-009, REJECTED, never delivered),
as the combinator port's text rule already refuses one in a synthesis: raw text before it is parsed, a structured report on the text of
the report it delivers. The marks U+200E, U+200F and U+061C reorder no run of text and are not refused; a supplied text is the router's
and is not read for it."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.bus import BIDI_CONTROL_CLASS, bidi_control_message, report_bidi_findings
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.integrity.contracts import SYNTHESIS_FORBIDDEN_CLASS
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

from ..core_hostile import SHAPES, one, sweep
from ..timing import measure

KEY = b"c1-handoff-bidi-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
CONTROLS = ("\u202a", "\u202b", "\u202c", "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069")


def _hub(subject: str, agent: str, texts=()):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent, "combinator"],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _req, _rq = hub.dispatch("t", agent, "Explain the events and the figures.", list(texts))
    return hub, m


def deliver(subject: str, agent: str, payload, texts=()):
    hub, m = _hub(subject, agent, texts)
    try:
        _reply, rc = hub.receive("t", m.message_id, payload, agent_id=agent, report_id="rep-t-0")
    finally:
        hub.close()
    return rc


def refusals(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-REQ-009" and "bidirectional embedding, override or isolate" in f.message]


def refused(rc) -> bool:
    """REJECTED for the rule alone: one INT-REQ-009 naming it, nothing checked, nothing translated, nothing delivered."""
    return (rc.status.value == "REJECTED" and len(refusals(rc)) == 1 and not rc.formal_checks and not rc.outcomes and not rc.structural_findings
            and not rc.constraint_results)


def errors(rc) -> list:
    return [(f.code, f.message[:160]) for f in rc.findings if f.severity == "error"]


# ---------------------------------------------------------------------------------------------- every subject, every control

ANSWERS = {
    "History": ("history-specialist", "The Montgomery bus boycott began on 5 December {c}1955{e} and lasted 381 days."),
    "English A: Literature": ("english-specialist", "The narrator calls the river {c}\"a patient thief\"{e}, which shows how slowly the town decays."),
    "Economics": ("economics-specialist", "Revenue rose from $40m to {c}$50m{e}, an increase of 25%."),
    "Psychology": ("psychology-specialist", "Bandura (1961) found that {c}children copied aggression{e} they had observed."),
    "Physics": ("physics-specialist", "a = (20 − 0)/4.0 = {c}5.0{e} m s⁻²"),
}


@pytest.mark.parametrize("subject", sorted(ANSWERS))
@pytest.mark.parametrize("control", ["\u202e", "\u202b", "\u2067", "\u2066"])
def test_a_response_holding_a_bidirectional_control_is_refused_for_every_subject(subject, control):
    agent, template = ANSWERS[subject]
    closer = "\u2069" if control in "\u2066\u2067\u2068" else "\u202c"
    text = template.format(c=control, e=closer)
    rc = deliver(subject, agent, text)
    assert refused(rc), [(f.code, f.message[:200]) for f in rc.findings]
    [f] = refusals(rc)
    # names the code points and their offsets, never the text it governs
    assert f"U+{ord(control):04X} at character offset {text.index(control)}" in f.message and f"U+{ord(closer):04X}" in f.message
    assert "1955" not in f.message and "patient thief" not in f.message and "rep-t-0" in f.report_ids and agent in f.agent_ids
    # control: the same answer without the controls is delivered and checked as before
    clean = deliver(subject, agent, template.format(c="", e=""))
    assert clean.status.value != "REJECTED" and not refusals(clean), errors(clean)


@pytest.mark.parametrize("mark", ["‎", "‏", "؜"])
def test_control_the_marks_that_reorder_no_run_are_not_refused(mark):
    """A left-to-right or right-to-left mark (or the Arabic letter mark) carries a direction but reorders no run of digits or words."""
    rc = deliver("History", "history-specialist", f"The Montgomery bus boycott began on 5 December 1955{mark} and lasted 381 days.")
    assert rc.status.value != "REJECTED" and not refusals(rc), errors(rc)


def test_the_rules_class_is_the_bidirectional_class_of_the_synthesis_text_rule():
    """The response rule and the combinator port's text rule refuse the same bidirectional characters."""
    import re
    bidi = {chr(cp) for cp in range(0x2000, 0x2100) if re.fullmatch(f"[{BIDI_CONTROL_CLASS}]", chr(cp))}
    synthesis = {chr(cp) for cp in range(0x2000, 0x2100) if re.fullmatch(f"[{SYNTHESIS_FORBIDDEN_CLASS}]", chr(cp))}
    assert bidi == synthesis == set(CONTROLS)


# --------------------------------------------------------------------------------------------- a structured report

def _report(claim_text: str, *, response: str | None = None, excerpt: str | None = None, texts=()) -> dict:
    agent, subject = "history-specialist", "History"
    response = response if response is not None else claim_text
    ids = dict(request_id="r", task_id="t", report_id="rep-t-0", agent_id=agent, subject=subject, task_type="short_answer")
    claim = dict(ids, claim_id="h1.1", claim_text=claim_text, claim_role="point", materiality="material")
    if excerpt is not None:
        claim["source_refs"] = [{"document_id": texts[0].document_id, "excerpt": excerpt}]
    return dict(ids, original_response=response, response_sha256=sha256_text(response), claims=[claim],
                supplied_texts=[t.model_dump(mode="json", exclude_none=True) for t in texts], created_at="2026-11-06T10:00:00Z")


def test_a_structured_report_holding_a_bidirectional_control_in_a_claim_is_refused():
    """A report received as JSON: the response text is clean, the claim's own text is not (and the escaped form '\\u202e' in JSON text
    reaches the claim as the control itself)."""
    payload = _report("The boycott began on 5 December \u202e1955\u202c.", response="The boycott began on 5 December 1955.")
    rc = deliver("History", "history-specialist", payload)
    assert refused(rc) and refusals(rc)[0].claim_ids == ["h1.1"] and "of the text of claim h1.1" in refusals(rc)[0].message, errors(rc)
    rc = deliver("History", "history-specialist", json.dumps(payload))  # JSON text: '\u202e' escaped, so the raw text holds no control
    assert refused(rc) and refusals(rc)[0].claim_ids == ["h1.1"], errors(rc)
    clean = deliver("History", "history-specialist", _report("The boycott began on 5 December 1955.", response="The boycott began on 5 December 1955."))
    assert not refusals(clean) and clean.status.value != "REJECTED", errors(clean)


def test_a_supplied_text_holding_a_control_is_the_routers_and_is_not_read_for_it():
    """The rule reads the specialist's own text: a supplied text the router sent with an isolate in it (a name pasted from a web page)
    is not the specialist's, and a report that echoes it with clean text of its own is not refused for it; a quotation that carries the
    control into the specialist's own text is."""
    doc = SuppliedText(document_id="doc1", title="Source A", text="The organiser \u2067Rosa Parks\u2069 was arrested on 1 December 1955.")
    payload = _report("Source A says Parks was arrested on 1 December 1955.", texts=(doc,))
    rc = deliver("History", "history-specialist", payload, texts=(doc,))
    assert not refusals(rc), errors(rc)
    quoting = _report("Source A says \"The organiser \u2067Rosa Parks\u2069 was arrested\".", texts=(doc,), excerpt="The organiser \u2067Rosa Parks\u2069 was arrested")
    rc = deliver("History", "history-specialist", quoting, texts=(doc,))
    assert refused(rc), errors(rc)


def test_a_report_handed_over_as_an_object_is_refused_too():
    report = SpecialistReport.model_validate(_report("The boycott began on 5 December \u20661955\u2069."))
    rc = deliver("History", "history-specialist", report)
    assert refused(rc), errors(rc)


# ------------------------------------------------------------------------------------------------- the readers are linear


def _entries(text: str):
    yield "bidi_control_message", lambda: bidi_control_message("response text", text)
    yield "bidi_control_message (controls)", lambda: bidi_control_message("response text", text + "\u202e" * 200)
    rep = SpecialistReport.model_validate(_report(text[:4000] or "x", response=text or "x"))
    yield "report_bidi_findings", lambda: report_bidi_findings(rep)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_bidi_readers(shape):
    """The rule's readers, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_entries, texts=one(shape))


@pytest.mark.parametrize("name,text", [
    ("every character a control", "\u202e" * 399_999 + "x"),
    ("alternating controls and digits", "\u20661\u2069" * 133_000),
])
def test_the_rule_is_linear_on_the_longest_response_the_contract_allows(name, text):
    timing = measure(lambda: bidi_control_message("response text", text), bound=2.0, repeat=3, label=f"bidi-text, {name}")
    assert timing.holds and all(r and r.count("U+") == 8 for r in timing.results), timing
    rep = SpecialistReport.model_validate(_report(text[:4000], response=text))
    timing = measure(lambda: report_bidi_findings(rep), bound=2.0, repeat=3, label=f"bidi-text report, {name}")
    assert timing.holds and all(len(r) == 1 for r in timing.results), timing
