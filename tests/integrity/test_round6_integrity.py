"""Ledger behaviour found wanting by the round-6 arena overseers, on the round-6 material: INT-LEDGER-026 read only a
one-word exchange between copied words, so a synthesis that rewrote a degree verdict as a phrase ("to a significant but
limited extent" -> "to a large extent"), reversed the two sides of a comparison, inverted an order with an added object
("Guinea preceded Ghana"), changed a quantity qualifier ("only one" -> "at least one"), exchanged a length ("short lines"
-> "long lines") or made an approximate figure in words exact reached the router with only the generic INT-SYNTH-012,
the receipt of a faithful paraphrase. A day-month date changed at the end of its sentence ("6 March" -> "6 May"), a year
moved onto another event of the same sentence ("wrote the sonnet in 1886", the dedication year) and the request's own
words quoted as the poem's or its author's were not named either."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.integrity.ledger import aligned_changes, credited_date_repairings, day_month_differences, meaning_differences, reversed_comparisons
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

KEY = b"round6-integrity-test-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
R6 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r6_material.json").read_text())
SPEC, SYN = R6["specialists"], R6["syntheses"]
COMB = "dummy-combinator"


def deliver(task_id):
    item = SPEC[task_id]
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id=f"plan-{task_id}", request_id=f"req-{task_id}", task_id=task_id, subject=item["subject"], task_type=item["task_type"],
                                selected_agent_ids=[item["agent_id"], COMB], allowed_document_ids=[t["document_id"] for t in item["supplied_texts"]]))
    m, _, _ = hub.dispatch(task_id, item["agent_id"], item["question"], [SuppliedText(**t) for t in item["supplied_texts"]])
    reply, _rc = hub.receive(task_id, m.message_id, item["response_text"], agent_id=item["agent_id"], report_id=f"rep-{task_id}-0")
    return ch, SpecialistReport.model_validate(reply.payload)


def claim_id(report: SpecialistReport, words: str) -> str:
    return next(c.claim_id for c in report.claims if words in c.claim_text)


def relay(task_id, text, source_words, transformation="paraphrased"):
    """Relay a one-claim synthesis of ``task_id`` whose claim ``s1`` cites the claim holding ``source_words``; every other
    material source is recorded as dropped with a reason, so only the claim under test can carry a content finding."""
    ch, rep = deliver(task_id)
    src = claim_id(rep, source_words)
    others = [c.claim_id for c in rep.claims if c.claim_id != src and c.materiality == "material"]
    sc = SynthesizedClaim(claim_id="s1", text=text, certainty="probable", source_claim_ids=[src], transformation=transformation)
    ledger = [LedgerEntry(source_claim_ids=others, transformation="dropped", reason="outside this one-claim synthesis")] if others else []
    syn = Synthesis(synthesis_id=f"syn-{task_id}", request_id=f"req-{task_id}", task_id=task_id, combinator_agent_id=COMB, source_report_ids=[rep.report_id],
                    claims=[sc], ledger=ledger, text=text, text_sha256=sha256_text(text), created_at="2026-10-12T12:00:00Z")
    reply, rc = ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    assert reply is not None
    return [f for f in rc.findings if "s1" in f.claim_ids]


def named(findings, code, *words):
    return [f for f in findings if f.code == code and all(w in f.message for w in words)]


T11 = SYN["hi-t11"]["claims"][0]["text"]
T12_H2 = "In 1957 only one African territory became independent: the Gold Coast, as Ghana, on 6 March."
T12_H3 = "In 1958 Guinea followed on 2 October, having voted No in de Gaulle's referendum of 28 September and faced the immediate withdrawal of French aid and personnel."
T12_H5 = "From 1961 the flow slowed to roughly fifteen states by 1968, including Tanganyika in 1961, Kenya in 1963 and Botswana in 1966."
P5_H5 = SYN["hi-p5"]["claims"][3]["text"]
P5_H4 = ("Emma Lazarus, a New York writer already active in aid for Jewish refugees from Russia, wrote the sonnet in 1883 for an auction to raise money for the "
         "statue's pedestal, and the statue, a gift from France, was dedicated on 28 October 1886.")
EN_P3 = "The short lines carry the decisive turns."


# --------------------------------------------------------------------------- degree verdicts, comparisons, polarity (major)
@pytest.mark.parametrize("old,new,what", [
    ("to a significant but limited extent", "to a large extent", "a degree verdict"),
    ("to a significant but limited extent", "to a decisive extent", "a degree verdict"),
    ("significant but limited extent", "significant but unlimited extent", "negating prefix"),
    ("but limited extent", "but large extent", "a degree verdict"),
    ("more for the timing of recovery than for its occurrence", "more for its occurrence than for the timing of recovery", "the two sides of a comparison"),
])
def test_a_rewritten_hi_t11_verdict_is_int_ledger_026(old, new, what):
    found = relay("hi-t11", T11.replace(old, new), "to a significant but limited extent")
    assert named(found, "INT-LEDGER-026", what), [f.message for f in found]


@pytest.mark.parametrize("old,new,what", [
    ("while excluding some by origin", "while welcoming all by origin", "inclusion or exclusion"),
    ("while excluding some by origin", "while welcoming some by origin", "inclusion or exclusion"),
    ("while excluding some by origin", "while excluding none by origin", "negation"),
    ("in unprecedented numbers", "in declining numbers", "replaces 'unprecedented' with 'declining'"),
])
def test_a_reversed_hi_p5_link_is_int_ledger_026(old, new, what):
    found = relay("hi-p5", P5_H5.replace(old, new), "while excluding some by origin")
    assert named(found, "INT-LEDGER-026", what), [f.message for f in found]


@pytest.mark.parametrize("new,what", [
    (T12_H3.replace("Guinea followed", "Guinea preceded Ghana"), "an order in time"),
    (T12_H2.replace("only one", "at least one"), "a quantity qualifier"),
])
def test_an_inverted_order_or_qualifier_in_hi_t12_is_int_ledger_026(new, what):
    words = "Guinea followed" if "Guinea" in new else "only one African"
    found = relay("hi-t12", new, words)
    assert named(found, "INT-LEDGER-026", what), [f.message for f in found]


@pytest.mark.parametrize("transformation", ["carried", "paraphrased", "merged"])
@pytest.mark.parametrize("new,what", [(EN_P3.replace("short", "long"), "a length"), (EN_P3.replace("decisive", "minor"), "a degree verdict")])
def test_one_word_exchanged_for_its_opposite_in_a_short_sentence_is_named_under_every_label(new, what, transformation):
    found = relay("en-t12", new, "The short lines carry the decisive turns", transformation)
    assert named(found, "INT-LEDGER-026", what), [f.message for f in found]


@pytest.mark.parametrize("new,written,source", [
    (T12_H5.replace("roughly fifteen", "exactly fifteen"), "exactly fifteen", "roughly fifteen"),
    (T12_H5.replace("roughly fifteen", "exactly 15"), "exactly 15", "roughly fifteen"),
])
def test_an_approximate_figure_in_words_made_exact_is_int_ledger_026(new, written, source):
    found = relay("hi-t12", new, "roughly fifteen states")
    assert named(found, "INT-LEDGER-026", f"'{written}'", f"'{source}'"), [f.message for f in found]


def test_meaning_rules_on_the_bare_texts():
    assert reversed_comparisons("It explains more for its occurrence than for the timing of recovery.", [T11])
    assert not reversed_comparisons(T11, [T11])
    figures, meaning = aligned_changes("They arrived from the north and west rather than from southern and eastern Europe.",
                                       "They arrived from southern and eastern Europe rather than from the north and west.")
    assert not figures
    assert meaning_differences("They arrived from the north and west rather than from southern and eastern Europe.",
                               ["They arrived from southern and eastern Europe rather than from the north and west."], "paraphrased")


# --------------------------------------------------------------------------- dates and request words (major)
def test_a_changed_month_at_the_end_of_its_sentence_is_int_ledger_023():
    found = relay("hi-t12", T12_H2.replace("6 March", "6 May"), "only one African", "carried")
    assert named(found, "INT-LEDGER-023", "'6 May'", "'6 March'", "a month changed"), [f.message for f in found]
    assert day_month_differences(T12_H2.replace("6 March", "6 May"), [T12_H2])
    assert not day_month_differences(T12_H2, [T12_H2]) and not day_month_differences("Ghana became independent on 6 March 1957.", [T12_H2])


def test_a_year_moved_onto_another_event_of_the_copied_sentence_is_int_ledger_023():
    """p5: 'wrote the sonnet in 1886' where the source dates the sonnet 1883 and the dedication 1886 got only the
    INT-LEDGER-024 'figures dropped' warning."""
    found = relay("hi-p5", P5_H4.replace("wrote the sonnet in 1883", "wrote the sonnet in 1886"), "wrote the sonnet in 1883")
    assert named(found, "INT-LEDGER-023", "'1886'", "'1883'"), [f.message for f in found]


@pytest.mark.parametrize("added", [' Herbert calls this "the alternation of long and short lines".', ' The poem names "the speaker\'s reluctance and Love\'s insistence".',
                                   ' Herbert uses "the alternation of long and short lines" to stage the exchange.'])
def test_the_requests_words_credited_to_the_poem_or_its_author_are_int_ledger_025(added):
    found = relay("en-t12", EN_P3 + added, "The short lines carry the decisive turns")
    assert named(found, "INT-LEDGER-025", "the router's request"), [f.message for f in found]


def test_control_quoting_the_poem_and_naming_its_title_raise_no_misattribution():
    found = relay("en-t12", EN_P3 + ' The refusal "I cannot look on thee." is compressed into one short line.', "The short lines carry the decisive turns")
    assert not named(found, "INT-LEDGER-025"), [f.message for f in found]


def test_credited_date_repairings_on_the_bare_texts():
    peer = SPEC["hi-p5"]["response_text"]
    assert credited_date_repairings("dates the sonnet to 1886", peer)
    assert credited_date_repairings("dates the Chinese Exclusion Act to 1883", peer)
    assert not credited_date_repairings("dates the Chinese Exclusion Act to 1882", peer)
    assert not credited_date_repairings("dates the statue's dedication to 1886", peer)


# --------------------------------------------------------------------------- the faithful baselines stay quiet
@pytest.mark.parametrize("task_id", ["hi-t11", "hi-t12", "hi-p5", "en-t12", "en-t11"])
def test_the_recorded_faithful_syntheses_carry_no_new_content_finding(task_id):
    ch, rep = deliver(task_id)
    scs = []
    for i, c in enumerate(SYN[task_id]["claims"]):
        scs.append(SynthesizedClaim(claim_id=f"s{i}", text=c["text"], certainty=c["certainty"], source_claim_ids=c["source_claim_ids"], transformation=c["transformation"]))
    body = " ".join(s.text for s in scs)
    syn = Synthesis(synthesis_id=f"syn-{task_id}", request_id=f"req-{task_id}", task_id=task_id, combinator_agent_id=COMB, source_report_ids=[rep.report_id],
                    claims=scs, text=body, text_sha256=sha256_text(body), created_at="2026-10-12T12:00:00Z")
    _reply, rc = ch.relay(COMB, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    assert not [f.message for f in rc.findings if f.code in ("INT-LEDGER-023", "INT-LEDGER-025", "INT-LEDGER-026")]


@pytest.mark.parametrize("syn,src", [
    ("The Plan was responsible to a great extent.", "The Plan was responsible to a large extent."),
    ("Output rose sharply in the territories after 1960.", "Output rose sharply in the territory after 1960."),
    ("The speaker refuses whereas Love insists, and the poem ends at the table.", "The speaker refuses while Love insists, and the poem ends at the table."),
])
def test_synonyms_word_forms_and_function_words_are_not_replacements(syn, src):
    figures, meaning = aligned_changes(syn, src)
    assert not figures and not meaning, (figures, meaning)
