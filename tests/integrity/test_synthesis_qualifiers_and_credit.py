"""INT-LEDGER-026 on what a synthesized claim drops or credits (combinator verification round 2, V2-M2 and V2-M3).

The combinator's instructions (rule 4) say to keep the qualifiers: "may have", "suggests", "probably", "to a limited
extent", "only", "from memory". Before, the hub named a dropped hedge ("probably", "may have", "suggests") but not a
dropped restricting qualifier ("Only a minority" -> "A minority"), a dropped degree limit ("... to a limited extent" with
the limit removed) or a dropped approximation ("about 6 million" -> "6 million"), and it read "Only a minority" -> "A
majority" as no reversal. Rule 5 says to keep the attributions: before, "According to the History specialist, <an
Economics claim>" and "The Treaty of Versailles states that <a History claim>" were named by nothing, because the view
credit read only a possessive or the subject of a crediting verb and INT-LEDGER-025 needs a quotation.

Each form below is named on the synthesized claim; each control (the qualifier kept, the credit the sources give, a text in
scope that holds what it is credited with) is not.
"""
from __future__ import annotations

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity.ledger import check_synthesis_ledger
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

TREATY = SuppliedText(document_id="treaty", title="Treaty of Versailles (1919), Article 231", author=None,
                      text="The Allied and Associated Governments affirm and Germany accepts the responsibility of Germany and her allies for causing "
                           "all the loss and damage to which the Allied and Associated Governments have been subjected as a consequence of the war.")


def _report(agent: str, subject: str, rid: str, claims: list[tuple[str, str]], supplied: tuple[SuppliedText, ...] = ()) -> SpecialistReport:
    common = dict(request_id="req", task_id="task", report_id=rid, agent_id=agent, subject=subject, task_type="short_answer")
    records = [ClaimRecord(**common, claim_id=cid, claim_text=text, claim_role="point") for cid, text in claims]
    body = " ".join(text for _cid, text in claims)
    return SpecialistReport(**common, original_response=body, response_sha256=sha256_text(body), created_at="2026-10-17T00:00:00Z", claims=records,
                            supplied_texts=list(supplied))


HISTORY = _report("history-specialist", "History", "rep-h", [
    ("h1.1", "Only a minority of voters supported the Nazi party in 1928."),
    ("h1.2", "Article 48 allowed the president to rule by decree in emergencies."),
    ("h1.3", "The Treaty of Versailles made Germany accept responsibility for the war."),
    ("h1.4", "Only the army could have stopped the putsch in 1923."),
], supplied=(TREATY,))
ECONOMICS = _report("economics-specialist", "Economics", "rep-e", [
    ("e1.1", "Unemployment reached about 6 million in 1932."),
    ("e1.2", "The Wall Street Crash of October 1929 ended the American loans to a limited extent."),
    ("e1.3", "Some 9,000 banks failed between 1930 and 1933."),
])
TEXTS = {c.claim_id: c.claim_text for r in (HISTORY, ECONOMICS) for c in r.claims}


def _named(text: str, cite: str, transformation: str = "paraphrased") -> list[str]:
    claim = SynthesizedClaim(claim_id="y1", text=text, source_claim_ids=[cite], transformation=transformation)
    syn = Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=["rep-h", "rep-e"],
                    claims=[claim], text=text, text_sha256=sha256_text(text), created_at="2026-10-17T00:00:00Z")
    return [f.message for f in check_synthesis_ledger([HISTORY, ECONOMICS], syn) if f.code == "INT-LEDGER-026" and "y1" in f.claim_ids]


# ------------------------------------------------------------------------------------------- dropped qualifiers (V2-M2)

DROPPED = [
    ("only dropped", "A minority of voters supported the Nazi party in 1928.", "h1.1", "drops the qualifier 'Only'"),
    ("only dropped before a definite", "The army could have stopped the putsch in 1923.", "h1.4", "drops the qualifier 'Only'"),
    ("degree limit dropped", "The Wall Street Crash of October 1929 ended the American loans.", "e1.2", "drops the limit 'to a limited extent'"),
    ("approximation dropped", "Unemployment reached 6 million in 1932.", "e1.1", "where its cited sources give 'about 6 million'"),
    ("approximation dropped, figure in words", "Unemployment reached six million in 1932.", "e1.1", "where its cited sources give 'about 6 million'"),
    ("'some' dropped", "9,000 banks failed between 1930 and 1933.", "e1.3", "where its cited sources give 'some 9000'"),
    ("minority made a majority", "A majority of voters supported the Nazi party in 1928.", "h1.1", "reverses a minority or a majority"),
]


@pytest.mark.parametrize("name,text,cite,said", DROPPED, ids=[d[0] for d in DROPPED])
def test_a_dropped_qualifier_is_named(name, text, cite, said):
    messages = _named(text, cite)
    assert any(said.casefold() in m.casefold() for m in messages), messages


KEPT = [
    ("only kept", "Only a minority of voters supported the Nazi party in 1928.", "h1.1"),
    ("another restricting word", "Merely a minority of voters supported the Nazi party in 1928.", "h1.1"),
    ("the limit kept in other words", "The Wall Street Crash of October 1929 partly ended the American loans.", "e1.2"),
    ("the approximation kept in other words", "Unemployment reached roughly 6 million in 1932.", "e1.1"),
    ("the source carried", TEXTS["e1.3"], "e1.3"),
    ("a minority kept", "A minority of voters, and only a minority, supported the Nazi party in 1928.", "h1.1"),
]


@pytest.mark.parametrize("name,text,cite", KEPT, ids=[k[0] for k in KEPT])
def test_a_kept_qualifier_is_not_named(name, text, cite):
    assert _named(text, cite) == []


def test_not_only_adds_and_in_part_a_names_a_part_of_the_question():
    from epinoic_logic.integrity.ledger import dropped_qualifiers
    assert dropped_qualifiers("Hyperinflation ruined savers and pensioners alike in 1923.", ["Hyperinflation ruined not only savers but also pensioners alike in 1923."]) == []
    assert dropped_qualifiers("Profit stays above the figure of the first part of the question.", ["Profit stays above the figure in part (a) of the question."]) == []
    assert dropped_qualifiers("Prices rose in 3 years after the crash.", ["Prices rose over 3 years after the crash."]) == []
    assert dropped_qualifiers('The narrator calls Bayardo the victim of the town.', ['The narrator calls Bayardo "the only victim" of the town.']) == []
    # a comparison with an exact figure is no approximation (r7 cs-t13), and a qualifier in front of a formula restricts
    # the working, which no lexical reading can scope (r7 maa-p7b)
    assert dropped_qualifiers("Binary search makes at most 20 comparisons, which is still far fewer than the 1,000 of linear search.",
                              ["The binary search makes at most 20 comparisons.", "That is still far fewer than 1,000."]) == []
    assert dropped_qualifiers("Checking t = 0 and t = 8 with the stated counts gives worst-case half-lives of about 8.5 h and 7.6 h.",
                              ["Checking only t = 0 and t = 8 with the stated counts gives worst-case half-lives of about 8.5 h and 7.6 h."]) == []


# ------------------------------------------------------------------------------------------- wrong attribution (V2-M3)

MISCREDITED = [
    ("according to the wrong specialist", "According to the History specialist, unemployment reached about 6 million in 1932.", "e1.1",
     "credits the view to ['history-specialist']"),
    ("in the view of the wrong specialist", "In the view of the History specialist, unemployment reached about 6 million in 1932.", "e1.1",
     "credits the view to ['history-specialist']"),
    ("as noted by the wrong specialist", "Unemployment reached about 6 million in 1932, as noted by the History specialist.", "e1.1",
     "credits the view to ['history-specialist']"),
    ("a possessive view", "In the History specialist's view, unemployment reached about 6 million in 1932.", "e1.1", "credits the view to ['history-specialist']"),
    ("a reporting clause", "As the History specialist notes, unemployment reached about 6 million in 1932.", "e1.1", "credits the view to ['history-specialist']"),
    ("a named text not in scope", "The Weimar constitution states that Article 48 allowed the president to rule by decree in emergencies.", "h1.2",
     "credits the statement"),
    ("a person no source names", "According to Keynes, unemployment reached about 6 million in 1932.", "e1.1", "to 'Keynes'"),
    ("a text in scope that does not hold it", "According to the treaty, Article 48 allowed the president to rule by decree in emergencies.", "h1.2",
     "(treaty), which does not hold it"),
]


@pytest.mark.parametrize("name,text,cite,said", MISCREDITED, ids=[m[0] for m in MISCREDITED])
def test_a_wrong_attribution_is_named(name, text, cite, said):
    messages = _named(text, cite)
    assert any(said in m for m in messages), messages


CREDITED = [
    ("the right specialist", "According to the Economics specialist, unemployment reached about 6 million in 1932.", "e1.1"),
    ("the treaty in scope holds it", "According to the treaty, Germany accepts the responsibility of Germany and her allies for the loss and damage of the war.", "h1.3"),
    ("the source names the treaty", "The Treaty of Versailles states that Germany had to accept responsibility for the war.", "h1.3"),
    ("a pronoun", "It states that unemployment reached about 6 million in 1932.", "e1.1"),
    ("a group", "Historians agree that Article 48 allowed the president to rule by decree in emergencies.", "h1.2"),
    ("a question for a specialist", "This was a question for the History specialist: unemployment reached about 6 million in 1932.", "e1.1"),
]


@pytest.mark.parametrize("name,text,cite", CREDITED, ids=[c[0] for c in CREDITED])
def test_a_credit_the_sources_give_or_a_text_that_holds_it_is_not_named(name, text, cite):
    assert not any("credits" in m for m in _named(text, cite)), _named(text, cite)


def test_the_new_readings_take_linear_time_on_adversarial_text():
    """A long run of qualifiers, spaces, marks or credits never makes the hub's reading quadratic (round 2: a first draft
    took seconds on 4,000 spaces before a trailing credit and on 4,000 qualifiers in one clause)."""
    import time
    from epinoic_logic.adapters.markdown import hedged_certainty, is_synthesis_self_certification
    from epinoic_logic.adapters.sources import credited_agents, unquoted_credits
    from epinoic_logic.integrity.ledger import dropped_qualifiers
    for text in (" " * 4000 + "for the History specialist, x", ". " * 2000 + "x", ", " * 2000 + "x", "only " * 800, "about 6 " * 600,
                 "the synthesis has been " * 200 + "x", "According to Keynes, " * 200, "x, according to Keynes. " * 300):
        start = time.perf_counter()
        unquoted_credits(text)
        credited_agents(text, ["history-specialist", "economics-specialist"])
        dropped_qualifiers(text, [TEXTS["h1.1"], TEXTS["e1.1"]])
        dropped_qualifiers(TEXTS["h1.1"], [text])
        is_synthesis_self_certification(text)
        hedged_certainty(text)
        assert time.perf_counter() - start < 2.0, text[:30]
