"""Round-7 overseer regressions for the History parser's notes (communication-fidelity): a closing note ('Note: my sources do not confirm
the exact emigration total, so the figure is given as 'millions'; ...') is role ``other``, never material, never a body paragraph, whatever
its length, dates or figures; a paragraph opened by a bare note lead ('Note:', 'Limit:', 'Next step:', 'Confidence:') is a note paragraph as a
whole; a caveat about the answer's own sources or library is a note without a lead too, unless it goes on to state a dated item; the caveat
is recorded as an assumption, with certainty capped at 'probable', on the claims that carry the figure it names (hi-p7c h1.2 'millions'); and a
faithful synthesis that leaves the note out carries no INT-LEDGER-019."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter, has_note_lead, is_note_paragraph, is_note_sentence, is_source_caveat
from epinoic_logic.adapters.history_specialist.structural import structural_checks
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import sha256_text

from ..branches.r7_texts import HI_P7C, HI_P7C_Q, HI_T13, HI_T13_Q

KEY = b"history-r7-notes-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def parse(text: str, task_type: str = "short_answer"):
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="rep", task_type=task_type)


def hub_reply(text: str, question: str, task_type: str = "short_answer"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type=task_type, selected_agent_ids=["history-specialist", "dummy-combinator"]))
    m, _, _ = hub.dispatch("t", "history-specialist", question)
    reply, rc = hub.receive("t", m.message_id, text, agent_id="history-specialist", report_id="rep-h")
    return ch, reply, rc


def relay_material(ch, reply):
    claims = [c for c in reply.payload["claims"] if c["materiality"] == "material"]
    carried = [SynthesizedClaim(claim_id=f"s{i}", text=c["claim_text"], certainty="probable", source_claim_ids=[c["claim_id"]], transformation="carried") for i, c in enumerate(claims)]
    body = " ".join(c.text for c in carried)
    syn = Synthesis(synthesis_id="syn-1", request_id="r", task_id="t", combinator_agent_id="dummy-combinator", source_report_ids=["rep-h"], claims=carried,
                    text=body, text_sha256=sha256_text(body), created_at="2026-10-12T08:00:00Z")
    _relayed, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    return rr


@pytest.mark.parametrize("text,question", [(HI_P7C, HI_P7C_Q), (HI_T13, HI_T13_Q)])
def test_the_closing_note_is_other_and_a_synthesis_that_drops_it_is_not_faulted(text, question):
    rep = parse(text)
    [note] = [c for c in rep.claims if c.claim_text.startswith("Note:")]
    assert (note.claim_role, note.materiality) == ("other", "supporting")
    findings = structural_checks(rep)
    assert not [f for f in findings if f.code.startswith("HI-STR") and note.claim_id in f.claim_ids]  # never judged as a body paragraph
    ch, reply, rc = hub_reply(text, question)
    assert reply is not None
    assert not [f for f in rc.findings if f.code == "INT-REQ-005" and f.severity == "error"]  # the note's words are not the answer's (hi-t13: 303 + 57)
    rr = relay_material(ch, reply)
    assert not [f for f in rr.findings if f.code in ("INT-LEDGER-019", "INT-LEDGER-002") and note.claim_id in f.claim_ids], [(f.code, f.claim_ids) for f in rr.findings]


def test_the_caveat_is_recorded_on_the_claim_that_carries_the_figure_it_names():
    rep = parse(HI_P7C)
    [h12] = [c for c in rep.claims if "millions of East Germans" in c.claim_text]
    assert h12.certainty == "probable" and any("do not confirm the figure 'millions'" in a for a in h12.assumptions)
    others = [c for c in rep.claims if c.claim_role != "other" and c is not h12]
    assert not [c for c in others if any("do not confirm" in a for a in c.assumptions)]
    # hi-t13: the note's second clause ('my sources do not confirm the 1924 vote share, so the quantified evidence is the dates ...') names
    # a figure the answer does not state, so no claim is capped (the answer said 'a clear majority of the vote' instead)
    t13 = parse(HI_T13)
    assert not [c for c in t13.claims if any("do not confirm" in a for a in c.assumptions)]
    # a caveat in a note's later clause naming the figure it gives ('given as 'about 65 per cent'') reaches the claim that states it
    varied = parse(HI_T13.replace("won a clear majority of the vote", "won about 65 per cent of the vote").replace(
        "my sources do not confirm the 1924 vote share, so", "my sources do not confirm the 1924 vote share, so it is given as 'about 65 per cent' and"))
    [vote] = [c for c in varied.claims if "of the vote" in c.claim_text and c.claim_role != "other"]
    assert vote.certainty == "probable" and any("'about 65 per cent'" in a for a in vote.assumptions)
    # HI-SRC-004 says what the note says rather than that the answer is silent about its figures
    [src4] = [f for f in structural_checks(rep) if f.code == "HI-SRC-004"]
    assert "the answer's own note says its sources do not confirm" in src4.message and "h2.1" not in src4.claim_ids


@pytest.mark.parametrize("para", [
    "Note: the totals for 1953 and 1961 come from a textbook table I could not check. Departures rose from about 144,000 in 1959 to about 199,000 "
    "in 1960, and the table gives about 2.7 million for the whole period; check them before use.",
    "Limit: no textbook library was available in this session. The figures for 1953 and 1961 come from the supplied table, and they show a rise of 40 per cent.",
    "Next step: compare the 1953 and 1961 figures with your notes. Then add the 1958 ultimatum.",
    "Confidence: lowered. The 1953 figure is the least certain.",
])
def test_a_paragraph_opened_by_a_bare_note_lead_is_a_note_whatever_its_dates(para):
    assert is_note_paragraph(para)
    rep = parse(HI_P7C.split("\n\nNote:")[0] + "\n\n" + para)
    tail = [c for c in rep.claims if c.claim_id.startswith("h2.")]
    assert tail and all((c.claim_role, c.materiality) == ("other", "supporting") for c in tail)
    assert not [f for f in structural_checks(rep) if f.code.startswith("HI-STR") and any(cid.startswith("h2.") for cid in f.claim_ids)]


@pytest.mark.parametrize("sentence,caveat", [
    ("My sources do not confirm the exact emigration total, so the figure is given as 'millions'; check the total in your textbook before quoting it.", True),
    ("The textbook library and MyLib were unavailable in this session, so these points rest on the supplied data and course-standard knowledge.", True),
    ("No approved source here confirms the 1924 vote share.", True),
    ("My sources do not confirm the exact total, but about 3 million left between 1949 and 1961.", False),  # it goes on to state a dated figure
    ("The sources show that the Fascist vote rose in 1924.", False),
    ("Sources from the period describe the exodus as a haemorrhage.", False),
])
def test_a_caveat_about_the_answers_own_sources_is_a_note(sentence, caveat):
    assert is_source_caveat(sentence) is caveat
    assert is_note_sentence(sentence) is caveat


@pytest.mark.parametrize("sentence,lead", [
    ("Note: Paper 2 essays are marked out of 15.", True),
    ("Limit: no library was available.", True),
    ("Confidence: lowered.", True),
    ("N.B. the figures are rounded.", True),
    ("Note that the vote share rose in 1924.", False),   # an argument's own signpost
    ("Notably, the vote share rose in 1924.", False),
])
def test_bare_note_leads(sentence, lead):
    assert has_note_lead(sentence) is lead


def test_a_note_on_a_named_subject_is_not_a_note_paragraph_by_its_lead_alone():
    para = "Note on the 1953 rising: workers in East Berlin struck on 16 June 1953. Soviet tanks ended the rising on 17 June 1953."
    rep = parse(HI_P7C.split("\n\nNote:")[0] + "\n\n" + para)
    assert any(c.claim_id.startswith("h2.") and c.claim_role != "other" for c in rep.claims)


@pytest.mark.parametrize("sentence,peer", [
    ("The English specialist supplies the frame: the closure dealt with the exit rather than the reasons people left.", True),
    ("The English specialist provides the reading that the wall answered a drain.", True),
    ("The war supplied the frame for the closure.", False),
])
def test_a_peer_specialist_supplying_a_view_is_a_reported_view(sentence, peer):
    from epinoic_logic.adapters.history_specialist.parser import is_peer_attribution
    assert is_peer_attribution(sentence) is peer
