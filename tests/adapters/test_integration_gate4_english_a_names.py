"""Integration gate 4 (major): the English A specialists are named by their course's own words.

``adapters.sources.specialist_names("english-a-literature-specialist")`` was ``['english a literature specialist',
'english specialist']``, so "the Literature specialist" (and "the English A specialist") read as no credit at all in every
reader that names a specialist (``credited_agents``, the ledger's ``_combinator_credits`` and ``_credits_at_head``, the peer
document names of ``_names_of``). A combinator that re-credited the History specialist's words to "the Literature
specialist" who reported them was not named (INT-LEDGER-026), while the same sentence with "the English specialist" was.
The English A agents now also carry their course's words (``sources._ENGLISH_A_NAMES``); every other agent is named as
before.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.sources import credited_agents, specialist_names
from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity.ledger import check_synthesis_ledger
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

LIT = "english-a-literature-specialist"
LL = "english-a-lang-lit-specialist"
H6 = "The closure therefore dealt with the exit rather than the reasons people left, and the flow fell sharply once the route was sealed."
S7 = 'The History specialist supplies the frame: the closure "dealt with the exit rather than the reasons people left".'


def test_the_literature_specialist_is_named_by_its_course_words():
    names = specialist_names(LIT)
    for n in ("english a literature specialist", "english specialist", "literature specialist", "english literature specialist", "english a specialist"):
        assert n in names
    assert len(names) == len(set(names))


def test_the_lang_lit_specialist_is_named_by_its_course_words():
    names = specialist_names(LL)
    for n in ("english a lang lit specialist", "english specialist", "lang lit specialist", "language and literature specialist", "english a specialist"):
        assert n in names
    assert "literature specialist" not in names, "'the Literature specialist' names the Literature course's agent only"


@pytest.mark.parametrize("instance", ["@a", "@b"])
def test_a_duplicated_instance_is_named_alike(instance):
    assert specialist_names(LIT + instance) == specialist_names(LIT)


@pytest.mark.parametrize("agent,names", [
    ("history-specialist", ["history specialist"]),
    ("mathematics-aa-specialist", ["mathematics aa specialist", "mathematics specialist", "maths specialist", "math specialist"]),
    ("english-specialist", ["english specialist"]),
    ("combinator", []),
])
def test_every_other_agent_is_named_as_before(agent, names):
    assert specialist_names(agent) == names


@pytest.mark.parametrize("credit", ["The Literature specialist", "The English A specialist", "According to the Literature specialist,",
                                    "In the Literature specialist's view,"])
def test_a_credit_in_the_course_words_credits_the_literature_specialist(credit):
    text = f'{credit} the closure "dealt with the exit rather than the reasons people left".'
    if not credit.endswith(","):
        text = text.replace(f"{credit} the closure", f"{credit} supplies the frame: the closure")
    assert credited_agents(text, [LIT, "history-specialist"]) == [LIT]


def _report(rid: str, agent: str, subject: str, claims: list[tuple[str, str, str]]) -> SpecialistReport:
    text = " ".join(t for _c, t, _r in claims)
    base = dict(request_id="req", task_id="task", report_id=rid, agent_id=agent, subject=subject, task_type="short_answer")
    return SpecialistReport(**base, original_response=text, response_sha256=sha256_text(text), created_at="2026-11-01T00:00:00Z",
                            claims=[ClaimRecord(**base, claim_id=c, claim_text=t, claim_role=r, materiality="supporting", certainty="probable")
                                    for c, t, r in claims])


def _credit_findings(text: str) -> list[str]:
    hi = _report("rep-hi", "history-specialist", "History", [("h1.6", H6, "point")])
    lit = _report("rep-lit", LIT, "English A: Literature", [("p1-s07", S7, "interpretation")])
    sc = [SynthesizedClaim(claim_id="s1", text=text, source_claim_ids=["p1-s07"], transformation="paraphrased", certainty="probable")]
    syn = Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=["rep-hi", "rep-lit"],
                    claims=sc, text=text, text_sha256=sha256_hex(text), created_at="2026-11-01T01:00:00Z")
    return [f.message for f in check_synthesis_ledger([hi, lit], syn) if f.code == "INT-LEDGER-026"]


@pytest.mark.parametrize("name", ["Literature specialist", "English A specialist", "English specialist"])
def test_the_history_view_recredited_to_the_literature_specialist_is_named(name):
    """The cited claim opens with its credit to the History specialist: the History specialist holds the view, so the
    synthesis that credits it to the Literature specialist who reported it credits it to another agent."""
    found = _credit_findings(S7.replace("History specialist", name))
    assert len(found) == 1
    assert f"credits the view to ['{LIT}'] but its cited source claims ['p1-s07'] state the view of ['history-specialist']" in found[0]


def test_the_faithful_credit_is_clean():
    assert _credit_findings(S7) == []


def test_a_view_the_literature_report_states_as_its_own_credited_to_it_is_clean():
    own = "The poem's closing image turns the border into a wound rather than a line."
    hi = _report("rep-hi", "history-specialist", "History", [("h1.6", H6, "point")])
    lit = _report("rep-lit", LIT, "English A: Literature", [("p1-s07", own, "interpretation")])
    text = "The Literature specialist reads the poem's closing image as turning the border into a wound rather than a line."
    sc = [SynthesizedClaim(claim_id="s1", text=text, source_claim_ids=["p1-s07"], transformation="paraphrased", certainty="probable")]
    syn = Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=["rep-hi", "rep-lit"],
                    claims=sc, text=text, text_sha256=sha256_hex(text), created_at="2026-11-01T01:00:00Z")
    assert not [f for f in check_synthesis_ledger([hi, lit], syn) if f.code == "INT-LEDGER-026" and "credits the view" in f.message]


# ===================================================================================== the class sweep (integration gate 4)
# adapters/sources.py names a specialist in regular expressions built from specialist_names: the English A agents now carry
# five names each (two shared). Every reader that names a specialist is fed the standard hostile runs with the English A
# agents in scope and must read them in linear time (measured: well under a second per call).
from epinoic_logic.adapters import sources as src
from epinoic_logic.adapters.markdown import find_quotation_spans
from epinoic_logic.integrity import ledger as L
from epinoic_logic.translate.contracts import SuppliedText

from ..core_hostile import SHAPES, one, sweep

_AGENTS = [LIT, LL, "history-specialist"]
_PEERS = {f"peer:{a}": SuppliedText(document_id=f"peer:{a}", title=None, author=a, text=H6) for a in _AGENTS}


def _names_entries(text: str):
    prefixed = "The Literature specialist supplies the frame: " + text
    yield "credited_agents", lambda: src.credited_agents(text, _AGENTS)
    yield "credited_agents (after a credit)", lambda: src.credited_agents(prefixed, _AGENTS)
    yield "document_mentions", lambda: src.document_mentions(prefixed, _PEERS[f"peer:{LIT}"])
    yield "quotation_credit", lambda: [src.quotation_credit(prefixed, a, _PEERS) for a, _b, _i in find_quotation_spans(prefixed)[:64]]
    yield "unquoted_credits", lambda: src.unquoted_credits(prefixed)
    yield "nearest_text", lambda: src.nearest_text(prefixed, _PEERS)
    yield "ledger _credits_at_head", lambda: L._credits_at_head(prefixed, [LIT, LL])
    yield "ledger _combinator_credits", lambda: L._combinator_credits(prefixed, _AGENTS)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_english_a_names(shape):
    """One test per shape; the CPU bound per call is the gate-2 sweep's (4 s)."""
    assert not sweep(_names_entries, texts=one(shape))
