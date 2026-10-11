"""Integrity checks added after the round-3 arena: a synthesis that swaps two dates or two
figures between events (same tokens, different facts) is a fidelity error (INT-LEDGER-023),
decided on the pairing of each figure with its event words, its dated statement and its from/to
partner; and note claims roled 'other' are not content a synthesis must account for
(INT-LEDGER-022)."""
from __future__ import annotations

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim, check_synthesis_ledger
from epinoic_logic.integrity.ledger import figure_pairing_differences, light_stem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

REQ, TASK = "req-l3", "task-l3"


def report(agent, subject, claims, report_id=None):
    rid = report_id or f"rep-{agent}"
    text = " ".join(c["claim_text"] for c in claims)
    return SpecialistReport(report_id=rid, request_id=REQ, task_id=TASK, agent_id=agent, subject=subject, task_type="short_answer", original_response=text,
                            response_sha256=sha256_text(text), created_at="2026-10-11T10:00:00Z",
                            claims=[ClaimRecord(request_id=REQ, task_id=TASK, report_id=rid, agent_id=agent, subject=subject, task_type="short_answer", **c) for c in claims])


def history():
    return report("history-specialist", "History", [
        dict(claim_id="h1.1", claim_text="The quarantine was announced on 22 October 1962.", claim_role="evidence"),
        dict(claim_id="h1.2", claim_text="The quarantine came into force from 24 October 1962.", claim_role="evidence"),
        dict(claim_id="h1.3", claim_text="Khrushchev's first letter of 26 October offered to remove the missiles.", claim_role="evidence"),
        dict(claim_id="h1.4", claim_text="His second letter of 27 October demanded a Turkish trade.", claim_role="evidence"),
        dict(claim_id="h1.5", claim_text="Registered unemployment rose from about 1.4 million in 1928 to 6 million by early 1932.", claim_role="evidence"),
        dict(claim_id="h1.6", claim_text="Dates and figures are from memory; verify them against your notes.", claim_role="other", materiality="supporting"),
        dict(claim_id="h1.7", claim_text="The correlation is not itself the explanation.", claim_role="analysis", materiality="supporting"),
    ])


def synthesis(claims, reports=("rep-history-specialist",)):
    text = " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn-3", request_id=REQ, task_id=TASK, combinator_agent_id="combinator", source_report_ids=list(reports),
                     claims=list(claims), text=text, text_sha256=sha256_text(text), created_at="2026-10-11T10:05:00Z")


def fidelity(syn):
    return [f for f in check_synthesis_ledger([history()], syn) if f.code == "INT-LEDGER-023"]


# ------------------------------------------------------------ swapped dates and figures


@pytest.mark.parametrize("transformation", ["merged", "paraphrased", "generalized"])
def test_dates_swapped_between_two_events_are_a_fidelity_error(transformation):
    swapped = SynthesizedClaim(claim_id="s-1", text="The quarantine was announced on 24 October and came into force from 22 October.", certainty="probable", source_claim_ids=["h1.1", "h1.2"], transformation=transformation)
    f = fidelity(synthesis([swapped]))
    assert len(f) == 1 and f[0].severity == "error" and f[0].claim_ids == ["s-1", "h1.1", "h1.2"] and f[0].agent_ids == ["combinator"]
    assert "re-pairs figures or dates between events" in f[0].message and "'24'" in f[0].message and "'22'" in f[0].message and "(exchanged)" in f[0].message
    assert "occur in none of its cited sources" not in f[0].message  # every token occurs: this is the swap case, not the introduced case
    faithful = SynthesizedClaim(claim_id="s-1", text="The quarantine was announced on 22 October and came into force from 24 October.", certainty="probable", source_claim_ids=["h1.1", "h1.2"], transformation=transformation)
    assert fidelity(synthesis([faithful])) == []


def test_the_two_letters_dates_swapped_are_named_and_the_faithful_merge_is_not():
    swapped = SynthesizedClaim(claim_id="s-2", text="Khrushchev's first letter of 27 October offered a deal; his second letter of 26 October demanded a trade.", certainty="probable", source_claim_ids=["h1.3", "h1.4"], transformation="merged")
    f = fidelity(synthesis([swapped]))
    assert len(f) == 1 and "'26'" in f[0].message and "'27'" in f[0].message and "first" in f[0].message
    faithful = SynthesizedClaim(claim_id="s-2", text="Khrushchev's first letter of 26 October offered a deal; his second letter of 27 October demanded a trade.", certainty="probable", source_claim_ids=["h1.3", "h1.4"], transformation="merged")
    assert fidelity(synthesis([faithful])) == []


def test_from_to_figures_reversed_are_a_fidelity_error_and_the_faithful_paraphrase_is_not():
    reversed_ = SynthesizedClaim(claim_id="s-3", text="Unemployment grew from 6 million in 1928 to 1.4 million in 1932.", certainty="probable", source_claim_ids=["h1.5"], transformation="paraphrased")
    f = fidelity(synthesis([reversed_]))
    assert len(f) == 1 and "'from 6 to 1.4' reverses the cited sources' 'from 1.4 to 6'" in f[0].message
    faithful = SynthesizedClaim(claim_id="s-3", text="Unemployment grew from 1.4 million in 1928 to 6 million in 1932.", certainty="probable", source_claim_ids=["h1.5"], transformation="paraphrased")
    assert fidelity(synthesis([faithful])) == []


def test_an_introduced_figure_and_a_swap_in_one_claim_yield_one_finding_naming_both():
    both = SynthesizedClaim(claim_id="s-4", text="The quarantine was announced on 24 October 1963 and came into force from 22 October.", certainty="probable", source_claim_ids=["h1.1", "h1.2"], transformation="merged")
    f = fidelity(synthesis([both]))
    assert len(f) == 1 and "states figures or dates ['1963', 'october 1963'] that occur in none of its cited sources" in f[0].message and "re-pairs figures or dates" in f[0].message and "(exchanged)" in f[0].message


def test_pairing_analysis_shapes():
    nazi = ["Registered unemployment rose from about 1.4 million in 1928 to more than six million by early 1932, and the Nazi vote rose with it: from 2.6 per cent and twelve seats in May 1928, "
            "to 18.3 per cent and 107 seats in September 1930, to 37.3 per cent and 230 seats in July 1932, when the party became the largest in the Reichstag.",
            "The Nazi vote fell to 33.1 per cent in November 1932 as the economy showed its first signs of recovery."]
    # faithful merges and re-orderings: silent
    assert figure_pairing_differences("The Nazi vote rose from 2.6 per cent in May 1928 to 37.3 per cent in July 1932, with 230 seats, before falling to 33.1 per cent in November 1932.", nazi) == []
    assert figure_pairing_differences("Unemployment of 1.4 million in 1928 and 230 seats in July 1932 framed the breakthrough; the vote fell to 33.1 per cent in November 1932.", nazi) == []
    assert figure_pairing_differences("The vote fell to 33.1 per cent in 1932.", nazi) == []  # a month omitted is not a changed date
    assert figure_pairing_differences("Printed in January 1818, when wheat cost 80 shillings a quarter in 1815 and 9,000 banks would fail.",
                                      ["The sonnet was printed in January 1818 in The Examiner.", "Wheat had cost 80 shillings a quarter in 1815, and some 9,000 banks failed later."]) == []
    assert figure_pairing_differences("Unemployment reached 6 million in 1932.", ["Unemployment reached 6 million.", "The crisis peaked in 1932."]) == []  # a new pairing, not a swap
    assert figure_pairing_differences("The party won 230 seats in July 1932 but only 196 in November 1932.", ["In July 1932 the party won 230 seats; in November 1932 it won 196."]) == []
    # swaps: named
    months = figure_pairing_differences("The Nazi vote rose from 2.6 per cent in May 1928 to 33.1 per cent in July 1932, before falling to 37.3 per cent in November 1932.", nazi)
    assert months and "'33.1' is dated july 1932, where the cited sources date it ['november 1932']" in months[0]
    years = figure_pairing_differences("Unemployment of 1.4 million in 1932 and 230 seats in July 1928 framed the breakthrough.", nazi)
    assert years and "(exchanged)" in years[0]
    seats = figure_pairing_differences("The party won 196 seats in July 1932 but only 230 in November 1932.", ["In July 1932 the party won 230 seats; in November 1932 it won 196."])
    assert seats and "'196'" in seats[0] and "'230'" in seats[0] and "(exchanged)" in seats[0]
    quantities = figure_pairing_differences("The vote rose from 18.3 per cent in 1928 to 2.6 per cent in 1930.", ["The party won 2.6 per cent in 1928 and 18.3 per cent in 1930."])
    assert any("'18.3' is dated 1928, where the cited sources date it ['1930']" in d for d in quantities)
    # a figure in no source is not this check's business (the plain INT-LEDGER-023 case names it)
    assert figure_pairing_differences("The sonnet was printed in March 1819.", ["The sonnet was printed in January 1818."]) == []


def test_light_stem_unifies_inflections_only():
    assert {light_stem(w) for w in ("quote", "quotes", "quoting", "quoted")} == {"quot"}
    assert {light_stem(w) for w in ("present", "presents", "presented", "presenting")} == {"present"}
    assert light_stem("analyses") == light_stem("analyse") and light_stem("class") == "class" and light_stem("was") == "was"
    assert light_stem("poem") != light_stem("power")


# ------------------------------------------------------------ notes are not unaccounted content


def test_note_claims_are_not_counted_among_unaccounted_supporting_claims():
    rep = history()
    carried = [SynthesizedClaim(claim_id=f"s{i}", text=c.claim_text, certainty="probable", source_claim_ids=[c.claim_id], transformation="carried") for i, c in enumerate(rep.claims) if c.materiality == "material"]
    f = check_synthesis_ledger([rep], synthesis(carried))
    notes = [x for x in f if x.code == "INT-LEDGER-022"]
    assert len(notes) == 1 and notes[0].claim_ids == ["h1.7"] and "h1.6" not in notes[0].claim_ids and "1 supporting source claim(s)" in notes[0].message
    assert not [x for x in f if x.code == "INT-LEDGER-002"]
