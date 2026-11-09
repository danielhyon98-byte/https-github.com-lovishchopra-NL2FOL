"""Integration gate 3, handoff fixer: agent-qualified claim ids for the English and History branches.

Correctness lens, major ("needs_qualified_ids ... English and History parsers never do"): the hub qualified the claim ids of
a report whose ids a report of ANOTHER agent already delivered on the task holds only for parsers that offer it
(``accepts_qualify_ids``: the STEM parsers; the generic parser always qualifies). Two agents of the english or history
branch on one task (English A: Literature with English A: Language and Literature; duplicated instances
``history-specialist@a`` / ``@b``) therefore delivered the same claim ids: the second receipt got only INT-REQ-016, and a
faithful synthesis citing each report's claim got INT-LEDGER-014 and INT-LEDGER-002 errors, so the response gate WITHHELD the
answer. The History and English parsers now offer the option (``qualify_ids``: every claim id, and every reference to one
inside the report, carries ``"@" + generic_parser.agent_claim_tag(agent)``, as the STEM parsers' do), and the one rule of
``channel.bus.needs_qualified_ids`` (the channel, the overseer's re-parse CUST-006, list_claims.py and the arena harness)
applies to them. A report that collides with nothing keeps every id it always had.
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.adapters.english_specialist.parser import parse_response as english_parse
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.branches.generic_parser import agent_claim_tag
from epinoic_logic.channel.bus import needs_qualified_ids
from epinoic_logic.channel.gate import assess_response
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, Synthesis, WorkPlan
from epinoic_logic.translate.contracts import SuppliedText, sha256_text

from ..core_hostile import HOSTILE, sweep
# the hub signs with the key the overseer's test auditor holds (overseer_attach's KEY is byte for byte the overseer suite's);
# make_auditor reaches the overseer through its public package API only and skips the test where it is not installed
from ..overseer_attach import KEY, make_auditor

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)

HISTORY = {
    "subject": "History", "subjects": {},
    "question": "Explain German hyperinflation in 1923.",
    "agents": (("history-specialist@a", "Hyperinflation peaked in November 1923, when a dollar bought 4.2 trillion marks."),
               ("history-specialist@b", "The French occupation of the Ruhr began in January 1923 and halted production.")),
}
ENGLISH = {
    "subject": "English A: Literature",
    "subjects": {"english-a-literature-specialist": "English A: Literature", "english-a-lang-lit-specialist": "English A: Language and Literature"},
    "question": "How does Kafka present the family in The Metamorphosis?",
    "agents": (("english-a-literature-specialist", "Gregor's transformation in the first sentence makes the family's disgust the centre of the story."),
               ("english-a-lang-lit-specialist", "Grete's growing independence shows how the family recovers once Gregor is gone.")),
}
GROUPS = {"history": HISTORY, "english": ENGLISH}

HI_TEXT = ("The Treaty of Versailles was a major but partial cause of instability in the Weimar Republic. It imposed reparations of 132 "
           "billion gold marks in 1921. Hyperinflation peaked in November 1923. Against this background, the treaty weakened the republic.\n\n"
           "Note: my sources do not confirm the exact reparations total, so the figure is given as '132 billion gold marks'.")
EXTRACT = "The mill wheel turned all night. 'We work until the bell,' the foreman said, 'and then we sleep.' The children counted every hour in coal."
EN_TEXT = ('The writer presents work as endless. The foreman\'s words "We work until the bell" make labour the measure of time. '
           'The children "counted every hour in coal", so time itself is paid in fuel. Therefore the extract shows work consuming childhood.')
EN_DOCS = [SuppliedText(document_id="doc-mill", title="Mill extract", author="Anonymous", text=EXTRACT)]


def _history(text: str, agent: str, **kw):
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="rep", agent_id=agent, **kw)


def _english(text: str, agent: str, **kw):
    return english_parse(text, request_id="r", task_id="t", report_id="rep", task_type="analytical_paragraph", supplied_texts=EN_DOCS, agent_id=agent, **kw)


def _without(report, suffix: str) -> dict:
    """The report as JSON with the agent suffix taken out of every string (creation time aside)."""
    data = json.loads(json.dumps(report.model_dump(mode="json")).replace(suffix, ""))
    data.pop("created_at")
    return data


# --------------------------------------------------------------------------- the parsers' option


@pytest.mark.parametrize("parse,text,agent", [(_history, HI_TEXT, "history-specialist@b"), (_history, HI_TEXT, "history-specialist"),
                                              (_english, EN_TEXT, "english-a-lang-lit-specialist"), (_english, EN_TEXT, "english-specialist@b")])
def test_the_parser_qualifies_every_id_and_every_reference_on_request_and_nothing_else(parse, text, agent):
    plain, qual = parse(text, agent), parse(text, agent, qualify_ids=True)
    suffix = "@" + agent_claim_tag(agent)
    assert all("@" not in c.claim_id for c in plain.claims), [c.claim_id for c in plain.claims]  # unchanged without the option
    ids = [c.claim_id for c in qual.claims]
    assert len(ids) >= 4 and all(i.endswith(suffix) and i.count("@") == 1 for i in ids), ids
    refs = [s for c in qual.claims for s in c.supporting_claim_ids] + [c.parent_claim_id for c in qual.claims if c.parent_claim_id]
    assert refs and all(r in ids for r in refs), refs  # every reference names a claim of the qualified report
    # the qualified report is the plain one with the suffix on every id and reference, nothing else changed
    expected = plain.model_dump(mode="json")
    expected.pop("created_at")
    assert _without(qual, suffix) == expected


def test_a_note_that_names_a_claim_names_the_qualified_id():
    agent = "history-specialist@b"
    qual = _history(HI_TEXT, agent, qualify_ids=True)
    note = next(c for c in qual.claims if c.claim_role == "other")
    named = [a for c in qual.claims for a in c.assumptions if "the answer's own note" in a]
    assert named and all(f"({note.claim_id})" in a for a in named), named


@pytest.mark.parametrize("which", ["history", "english"])
def test_the_tail_of_an_oversized_answer_and_its_issue_are_qualified_too(which):
    if which == "history":
        text = " ".join(f"The mill employed {k} children in 18{k % 90 + 10}." for k in range(600))
        agent, tail = "history-specialist@b", "h.tail"
        rep = _history(text, agent, qualify_ids=True)
    else:
        text = "The writer presents work as endless. " + " ".join(f"Line {k} shows the bell ringing again." for k in range(600))
        agent, tail = "english-a-lang-lit-specialist", "p-tail"
        rep = _english(text, agent, qualify_ids=True)
    qualified_tail = tail + "@" + agent_claim_tag(agent)
    assert len(rep.claims) == 512 and rep.claims[-1].claim_id == qualified_tail
    assert any(f"merged into claim {qualified_tail} " in u for u in rep.unresolved_issues), rep.unresolved_issues
    ids = {c.claim_id for c in rep.claims}
    assert all(s in ids for c in rep.claims for s in c.supporting_claim_ids)


def test_the_branches_offer_the_option_through_the_registry_and_the_hub_rule_reads_it():
    registry = default_registry()
    for subject in ("History", "English A: Literature", "English A: Language and Literature"):
        parser = registry.for_subject(subject)[0].parser()
        assert getattr(parser, "accepts_qualify_ids", False) is True, subject
    english = registry.for_subject("English A: Language and Literature")[0].parser()
    rep = english.parse_response(EN_TEXT, request_id="r", task_id="t", report_id="rep", subject="English A: Language and Literature",
                                 task_type="analytical_paragraph", supplied_texts=EN_DOCS, agent_id="english-a-lang-lit-specialist", qualify_ids=True)
    assert all(c.claim_id.endswith("@english-a-lang-lit-specialist") for c in rep.claims)
    plain = _history(HI_TEXT, "history-specialist@a")
    held = {c.claim_id for c in plain.claims}
    assert needs_qualified_ids(HistorySpecialistAdapter(), _history(HI_TEXT, "history-specialist@b"), held)
    assert not needs_qualified_ids(HistorySpecialistAdapter(), _history(HI_TEXT, "history-specialist@b"), {"p1-point"})  # nothing collides


# --------------------------------------------------------------------------- through the hub, with and without the overseer


def _group(which: str, *, auditor=None):
    g = GROUPS[which]
    hub = RouterHub(signing_key=KEY, config=CFG, **({"auditor": auditor} if auditor is not None else {}))
    agents = [a for a, _t in g["agents"]]
    channel = hub.open_task(WorkPlan(plan_id="p", request_id="req", task_id="t", subject=g["subject"], agent_subjects=g["subjects"], task_type="short_answer",
                                     selected_agent_ids=[*agents, "combinator"]))
    receipts, reports = [], []
    for k, (agent, text) in enumerate(g["agents"]):
        m, _req, _rq = hub.dispatch("t", agent, g["question"])
        reply, rc = hub.receive("t", m.message_id, text, agent_id=agent, report_id=f"rep-{k}")
        assert reply is not None, rc.summary
        receipts.append(rc)
        reports.append(channel.transmitted_reports[f"rep-{k}"])
    return hub, channel, receipts, reports


def _faithful_synthesis(reports) -> Synthesis:
    """Each report's claim carried word for word, at the source's own certainty and materiality, citing that claim."""
    claims = [{"claim_id": f"s{k}", "text": c.claim_text, "source_claim_ids": [c.claim_id], "transformation": "carried", "certainty": c.certainty,
               "materiality": c.materiality} for k, r in enumerate(reports) for c in r.claims]
    text = " ".join(c["text"] for c in claims)
    return Synthesis.model_validate({"synthesis_id": "syn", "request_id": "req", "task_id": "t", "combinator_agent_id": "combinator",
                                     "source_report_ids": [r.report_id for r in reports], "claims": claims, "text": text,
                                     "text_sha256": sha256_text(text), "created_at": "2026-11-01T00:00:00Z"})


@pytest.mark.parametrize("which", ["history", "english"])
def test_two_agents_of_one_branch_on_one_task_deliver_disjoint_ids_and_a_faithful_synthesis_is_accounted_for(which):
    hub, channel, receipts, reports = _group(which)
    try:
        first, second = reports
        (agent_a, _), (agent_b, _) = GROUPS[which]["agents"]
        assert all("@" not in c.claim_id for c in first.claims)  # the first report keeps its ids
        tag = agent_claim_tag(agent_b)
        assert second.claims and all(c.claim_id.endswith("@" + tag) for c in second.claims), [c.claim_id for c in second.claims]
        assert {c.claim_id.split("@", 1)[0] for c in second.claims} & {c.claim_id for c in first.claims}  # the ids it would have shared
        assert not {c.claim_id for c in first.claims} & {c.claim_id for c in second.claims}
        assert "INT-REQ-016" not in {f.code for r in receipts for f in r.findings}  # no shared id left to name
        _msg, src = channel.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _faithful_synthesis(reports))
        codes = {f.code for f in src.findings}
        assert not codes & {"INT-LEDGER-014", "INT-LEDGER-002", "INT-LEDGER-023"}, [(f.code, f.message[:160]) for f in src.findings]
        assert not any(f.severity == "error" and f.code.startswith("INT-LEDGER") for f in src.findings), [(f.code, f.message[:160]) for f in src.findings]
        gate = assess_response(receipts, src, synthesis_required=True)
        assert gate.display_status != "WITHHELD", [(c.check, c.result, c.detail) for c in gate.checks if c.result == "failed"]
        assert not [c for c in gate.checks if c.result == "failed" and "INT-LEDGER" in f"{c.check} {c.detail}"]
    finally:
        hub.close()


@pytest.mark.parametrize("which", ["history", "english"])
def test_the_overseer_reparse_reproduces_the_qualified_report(which):
    hub, _channel, _receipts, reports = _group(which, auditor=make_auditor())
    try:
        assert all("@" in c.claim_id for c in reports[1].claims)
        audit = hub.audit("t")
        found = [(f.code, f.message[:200]) for f in audit.report.findings if f.code == "OVS-CUST-006"]
        assert not found, found
    finally:
        hub.close()


def test_control_a_single_agent_and_two_branches_keep_their_ids():
    hub = RouterHub(signing_key=KEY, config=CFG)
    try:
        channel = hub.open_task(WorkPlan(plan_id="p", request_id="req", task_id="t", subject="History", task_type="short_answer",
                                         agent_subjects={"english-a-literature-specialist": "English A: Literature"},
                                         selected_agent_ids=["history-specialist", "english-a-literature-specialist"]))
        ids = []
        for k, (agent, text) in enumerate((("history-specialist", HISTORY["agents"][0][1]), ("english-a-literature-specialist", ENGLISH["agents"][0][1]))):
            m, _req, _rq = hub.dispatch("t", agent, "Answer the question.")
            reply, rc = hub.receive("t", m.message_id, text, agent_id=agent, report_id=f"rep-{k}")
            assert reply is not None, rc.summary
            ids.append([c.claim_id for c in channel.transmitted_reports[f"rep-{k}"].claims])
        assert ids == [["h1.1"], ["p1-point"]]  # different schemes: nothing collides, nothing is qualified
    finally:
        hub.close()


# --------------------------------------------------------------------------- the class sweep: the parsers' option on hostile input


#: CPU seconds one parse of one 20,000-character hostile input (with the branch's structural checks) may take: the gate-2 sweeps'
#: parse bound; the parsers take a few tenths of a second to about two seconds (the History parser on dashed digits).
PARSE_BOUND = 10.0


def _parser_entries(text: str):
    from epinoic_logic.adapters.english_specialist import structural as en_structural
    from epinoic_logic.adapters.history_specialist.parser import agent_id_suffix
    from epinoic_logic.adapters.history_specialist.structural import structural_checks as history_checks

    def history():
        history_checks(_history(text, "history-specialist@b", qualify_ids=True))

    def english():
        en_structural.structural_checks(_english(text, "english-a-lang-lit-specialist", qualify_ids=True), en_structural_segment(text), request_text=text)

    def registry_wrapper():
        default_registry().for_subject("English A: Language and Literature")[0].parser().parse_response(
            text, request_id="r", task_id="t", report_id="rep", subject="English A: Language and Literature", task_type="analytical_paragraph",
            supplied_texts=EN_DOCS, agent_id="english-a-lang-lit-specialist", qualify_ids=True)

    yield "History parse_response(qualify_ids) and structural_checks", history
    yield "English parse_response(qualify_ids) and structural_checks", english
    yield "registry English parser (qualify_ids)", registry_wrapper
    yield "agent_id_suffix of a hostile agent id", lambda: agent_id_suffix(text)


def en_structural_segment(text: str):
    from epinoic_logic.adapters.english_specialist.parser import segment
    return segment(text)


@pytest.mark.parametrize("shape", tuple(HOSTILE))
def test_sweep_the_parsers_qualified_ids_on_hostile_input(shape):
    from epinoic_logic.adapters.base import AdapterError
    assert not sweep(_parser_entries, bound=PARSE_BOUND, refusals=(AdapterError, ValueError), texts={shape: HOSTILE[shape]})
