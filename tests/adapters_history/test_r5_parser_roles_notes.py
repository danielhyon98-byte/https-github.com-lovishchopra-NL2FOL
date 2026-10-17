"""Round-5 overseer regressions for the History parser, its structural checks and its chronology
extractor: the verdict a request asks for is a material judgement however it is worded ('The 1840s
were the most decisive decade.'), and so is the criterion that opens a sentence ('Measured by ...');
'Against that toll, ...' is a material link; a note on how the answer was composed ('The historical
setting is my own addition, not part of that paragraph.') is a note, never the point; an inline
from-memory label caps certainty whether or not the sentence is dated; an altered quotation in a
sentence naming the poet and the colleague is credited to the reporting clause's speaker (INT-REQ-003
naming the claim); HI-STR-003 reads a year range as a claim's scope; HI-STR-004 counts '1.9' as one
word; durations, containment and same-year relations are decided; the JSON stripper is linear."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist.chronology import chronology_relations
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter, classify, is_note_sentence, is_provenance_note, opens_with_fact, split_sentences
from epinoic_logic.adapters.history_specialist.sentences import _balanced_end, strip_json_spans
from epinoic_logic.adapters.history_specialist.structural import structural_checks
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

from ..timing import measure

KEY = b"history-r5-roles-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)

HI_T10 = ("Railway growth in Britain between 1830 and 1870 came in phases, and the 1840s gave the network its shape. The Liverpool and Manchester Railway "
          "opened in September 1830 over 31 miles, the first inter-city line worked by steam locomotives on a timetable. The network then grew from almost "
          "nothing: the London and Birmingham Railway opened in 1838, and the Great Western reached Bristol in 1841. Route mileage was about 1,500 by 1840 and "
          "about 6,000 by 1850 (from memory; check your notes). The 1840s, which included the Railway Mania of 1845 to 1847, added roughly 4,500 miles, more "
          "than any other decade of the period, and by 1848 a line ran from London through Carlisle to Glasgow. The 1850s and 1860s took the network to about "
          "13,000 miles by 1870, but largely through branches and extensions to an existing framework. The 1840s were the most decisive decade. Measured by "
          "what the network could do, carrying traffic between the main cities, they created the trunk routes that later growth filled in, whereas the 1830s, "
          "though faster in relative terms, built only the first links.")
HI_T10_Q = ("Outline, with dated and quantified evidence, the growth of the railway network in Britain between 1830 and 1870. Write no more than 200 words "
            "and give a judgement on which decade saw the most decisive expansion.")
HI_P4 = ('The English specialist\'s paragraph identifies the speaker\'s motive as poverty: the casualness "exposes a motive of poverty", and the key word '
         '"traps" suggests a man who "sold his belongings for want of work". The historical setting is my own addition, not part of that paragraph. The '
         "Second Boer War ran from 11 October 1899 to the Peace of Vereeniging on 31 May 1902 (from memory; check your notes), so the poem's 1902 date falls "
         "at the war's close. Reverses in December 1899, including the Highland Brigade's defeat at Magersfontein on 11 December (from memory), helped drive "
         "the call for volunteers, and the Imperial Yeomanry's first contingents sailed in early 1900 (from memory). A regular private's pay of about a "
         "shilling a day (from memory) was a real draw for men without work, though historians dispute how far unemployment, rather than patriotism or "
         "adventure, drove enlistment. The losses were heavy: roughly 22,000 British and imperial deaths, the large majority from disease, chiefly enteric "
         'fever (from memory; approximate, and sources differ). Against that toll, Hardy\'s speaker calls the conflict a "quaint and curious war", a line '
         "that reads as a sardonic frame for a war that killed far more men through disease than in battle.")
EN_P4 = ('Hardy\'s dramatic monologue lets the speaker justify the killing in casual terms, and the casualness exposes a motive of poverty and a view of the '
         'enemy that his justification cannot sustain. The motive is presented through a colloquial parallel: "He thought he\'d \'list, perhaps, / Off-hand '
         'like—just as I— / Was out of work—had sold his traps—". The clipped "\'list" makes enlisting sound impulsive, while "just as I" implies that the '
         'speaker\'s own reason matches the enemy\'s. The key word "traps", which conventionally denotes snares but in colloquial use means a man\'s gear and '
         'belongings, suggests a man who has sold his belongings for want of work, so poverty becomes the motive, as the closing "No other reason why" '
         'confirms. The view of the enemy is built through the repetition of "foe": "I shot him dead because— / Because he was my foe, / Just so: my foe of '
         'course he was". Foe should supply a reason for killing, but it only restates the killing, so the justification becomes circular, and the unfinished '
         '"although" that ends the stanza shows a speaker who does not complete his argument. The opening conditional, "Had he and I but met", imagines the man '
         'as a drinking companion, which suggests the speaker sees the enemy as a man like himself. The final stanza sets the killing beside a social courtesy, '
         '"You shoot a fellow down / You\'d treat if met where any bar is", so the colloquial voice comfortably holds a contradiction.')
POEM = SuppliedText(document_id="doc-mhk", title="The Man He Killed (poem, supplied text)", author="Thomas Hardy",
                    text=('"Had he and I but met\nBy some old ancient inn,\nWe should have sat us down to wet\nRight many a nipperkin!\n\n"But ranged as infantry,\n'
                          'And staring face to face,\nI shot at him as he at me,\nAnd killed him in his place.\n\n"I shot him dead because—\nBecause he was my foe,\n'
                          'Just so: my foe of course he was;\nThat\'s clear enough; although\n\n"He thought he\'d \'list, perhaps,\nOff-hand like—just as I—\n'
                          'Was out of work—had sold his traps—\nNo other reason why.\n\n"Yes; quaint and curious war is!\nYou shoot a fellow down\n'
                          'You\'d treat if met where any bar is,\nOr help to half-a-crown."'))
PEER = SuppliedText(document_id="peer:en-p4", title="english-specialist report rep-en-p4-0 relayed through the hub", author="english-specialist", text=EN_P4)
P4_Q = ("You have received the English specialist's analytical paragraph on Hardy's 'The Man He Killed' (1902) through the hub; it is supplied to you as "
        "the document peer:en-p4. In one paragraph of no more than 220 words, outline for a literature student the historical context of what the English "
        "specialist identifies, with dated evidence labelled from memory as your method requires.")


def parse(text: str, rid: str = "rep", task_type: str = "short_answer", **kw) -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id=rid, task_type=task_type, **kw)


def claim(rep: SpecialistReport, text_start: str):
    return next(c for c in rep.claims if c.claim_text.startswith(text_start))


def hub_reply(text: str, question: str, texts=(), task_type: str = "short_answer"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type=task_type,
                                selected_agent_ids=["history-specialist", "dummy-combinator"], allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", "history-specialist", question, list(texts))
    reply, rc = hub.receive("t", m.message_id, text, agent_id="history-specialist", report_id="rep-h")
    return ch, reply, rc


def relay_synthesis(ch, claims: list[SynthesizedClaim], ledger=()):
    body = " ".join(c.text for c in claims)
    syn = Synthesis(synthesis_id=f"syn-{len(claims)}", request_id="r", task_id="t", combinator_agent_id="dummy-combinator", source_report_ids=["rep-h"],
                    claims=claims, ledger=list(ledger), text=body, text_sha256=sha256_text(body), created_at="2026-10-11T18:00:00Z")
    _relayed, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    return rr


# ------------------------------------------------------------------ the requested verdict and its criterion are material judgements


def test_hi_t10_verdict_and_its_criterion_are_material_judgements():
    rep = parse(HI_T10)
    verdict = claim(rep, "The 1840s were the most decisive decade.")
    criterion = claim(rep, "Measured by what the network could do")
    for c in (verdict, criterion):
        assert (c.claim_role, c.materiality) == ("judgement", "material"), c.claim_text
        assert c.supporting_claim_ids and c.supporting_claim_ids[0] == rep.claims[0].claim_id  # an argument from the point
    for sentence in ("The 1840s were the decisive decade.", "The most decisive decade was the 1840s.", "The 1840s saw the most decisive expansion.",
                     "The 1840s mattered most.", "The 1840s are the pivotal decade of the period.", "The most significant phase of the period was the 1840s."):
        varied = parse(HI_T10.replace("The 1840s were the most decisive decade.", sentence))
        c = claim(varied, sentence[:20])
        assert (c.claim_role, c.materiality) == ("judgement", "material"), sentence
    # a description with a degree word is not a verdict, and a dated sentence stays evidence
    assert classify("The significant growth was concentrated in the north.", 2, True) == "analysis"
    assert classify("Route mileage was about 1,500 by 1840 and about 6,000 by 1850.", 2, True) == "evidence"


def test_dropping_the_hi_t10_verdict_from_a_synthesis_is_a_ledger_error():
    ch, reply, rc = hub_reply(HI_T10, HI_T10_Q)
    claims = reply.payload["claims"]
    verdict = next(c for c in claims if c["claim_text"] == "The 1840s were the most decisive decade.")
    assert not [f for f in rc.findings if f.code == "INT-REQ-008"]  # the hub and the parser agree that the answer carries its verdict
    kept = [c for c in claims if c["materiality"] == "material" and c["claim_id"] != verdict["claim_id"]]
    carried = [SynthesizedClaim(claim_id=f"s{i}", text=c["claim_text"], certainty="probable", source_claim_ids=[c["claim_id"]], transformation="carried") for i, c in enumerate(kept)]
    rr = relay_synthesis(ch, carried)
    assert any(f.code == "INT-LEDGER-002" and f.severity == "error" and verdict["claim_id"] in f.claim_ids for f in rr.findings), [(f.code, f.claim_ids) for f in rr.findings]


def test_against_that_toll_is_a_material_link_whatever_it_quotes():
    rep = parse(HI_P4, supplied_texts=[PEER])
    link = claim(rep, "Against that toll")
    assert (link.claim_role, link.materiality) == ("link", "material")
    assert classify("Against this, the growth was extensive rather than intensive.", 3, True) == "counter_evidence"  # a bare 'Against this,' stays a counter-case


# ------------------------------------------------------------------ notes on how the answer was composed


@pytest.mark.parametrize("sentence", [
    "The historical setting is my own addition, not part of that paragraph.",
    "The judgement on which decade saw the most decisive expansion is from memory as well; verify it before use.",
    "The judgement on the extent of the transformation is my own; check it before use.",
    "The English specialist's paragraph is from the hub; I have not checked its quotations.",
])
def test_provenance_notes_are_notes(sentence):
    assert is_provenance_note(sentence) and is_note_sentence(sentence)


@pytest.mark.parametrize("sentence", [
    "The historical setting explains why men enlisted in 1899.",
    "The judgement is my own, and it shows that the 1840s were decisive.",
    "The war was not part of British memory until 1902.",
    "The Second Boer War ran from 11 October 1899 to 31 May 1902.",
])
def test_substantive_sentences_are_not_provenance_notes(sentence):
    assert not is_provenance_note(sentence)


def test_hi_p4_provenance_note_is_other_and_the_point_is_the_first_historical_sentence():
    rep = parse(HI_P4, supplied_texts=[PEER])
    note = claim(rep, "The historical setting is my own addition")
    assert (note.claim_role, note.materiality) == ("other", "supporting")
    point = next(c for c in rep.claims if c.claim_role == "point")
    assert point.claim_text.startswith("The Second Boer War ran from") and point.materiality == "material"
    assert note.claim_id not in point.supporting_claim_ids
    # an inline label caps certainty whether or not the sentence is dated
    pay = claim(rep, "A regular private's pay")
    assert pay.certainty == "probable" and any("from memory" in a for a in pay.assumptions)


def test_a_synthesis_that_leaves_out_the_provenance_note_is_not_faulted():
    ch, reply, _rc = hub_reply(HI_P4, P4_Q, [PEER])
    claims = reply.payload["claims"]
    note = next(c for c in claims if c["claim_text"].startswith("The historical setting"))
    material = [c for c in claims if c["materiality"] == "material"]
    assert note not in material
    carried = [SynthesizedClaim(claim_id=f"s{i}", text=c["claim_text"], certainty="probable", source_claim_ids=[c["claim_id"]], transformation="carried") for i, c in enumerate(material)]
    rr = relay_synthesis(ch, carried)
    assert not [f for f in rr.findings if f.code in ("INT-LEDGER-002", "INT-LEDGER-019") and note["claim_id"] in f.claim_ids]
    dropped = relay_synthesis(ch, carried[:-1] + [carried[-1]], ledger=[LedgerEntry(source_claim_ids=[note["claim_id"]], transformation="dropped", reason="a note on how the report was built")])
    assert not [f for f in dropped.findings if f.code == "INT-LEDGER-019"]


@pytest.mark.parametrize("text", [
    "Route mileage figures between 1830 and 1870 are from memory; check them against your notes. The judgement on which decade saw the most decisive "
    "expansion is from memory as well; verify it before use. Syllabus version and level were not stated.",
    "Dates and figures for the Five-Year Plans are from memory; verify them against your notes before use. The judgement on the extent of the "
    "transformation is my own; check it before use. Syllabus version and level were not stated.",
    "The English specialist's paragraph is from the hub; I have not checked its quotations. Dates and figures below are from memory; check them before "
    "use. Syllabus level was not stated.",
])
def test_an_answer_of_notes_only_has_no_answer(text):
    rep = parse(text, supplied_texts=[PEER])
    assert all(c.claim_role == "other" and c.materiality == "supporting" for c in rep.claims)
    _ch, _reply, rc = hub_reply(text, HI_T10_Q, [PEER])
    assert any(f.code == "INT-REQ-012" and f.severity == "error" for f in rc.findings)
    assert all(not cov.addressed for cov in rc.coverage)


# ------------------------------------------------------------------ attribution with the poet and the colleague both named


def test_an_altered_quotation_of_the_colleague_in_a_sentence_naming_the_poet_is_refuted_against_the_colleague():
    text = HI_P4.replace("The historical setting is my own addition, not part of that paragraph.",
                         "The historical setting is my own addition, not part of that paragraph. The English specialist argues that Hardy presents the enemy as \"a man much like himself\".")
    rep = parse(text, supplied_texts=[POEM, PEER])
    altered = claim(rep, "The English specialist argues that Hardy")
    assert [r.document_id for r in altered.source_refs] == ["peer:en-p4"]
    assert any("attributed to peer:en-p4" in a for a in altered.assumptions)
    assert not [f for f in CorePack().checks(rep) if f.code == "CORE-SRC-003" and "a man much like himself" in f.message]
    _ch, _reply, rc = hub_reply(text, P4_Q, [POEM, PEER])
    errors = [f for f in rc.findings if f.code == "INT-REQ-003"]
    assert errors and errors[0].severity == "error" and altered.claim_id in errors[0].claim_ids


# ------------------------------------------------------------------ HI-STR-003 and HI-STR-004


def test_hi_str_003_reads_a_year_range_as_the_scope_of_a_claim():
    assert not opens_with_fact(split_sentences(HI_T10)[0])
    assert not [f for f in structural_checks(parse(HI_T10)) if f.code == "HI-STR-003"]
    assert opens_with_fact("The Liverpool and Manchester Railway opened in 1830.")  # a single dated occurrence is still a bare fact


def test_hi_str_004_counts_a_decimal_as_one_word():
    body = ("Between 1928 and 1932 output rose from 3.3 million tonnes to 6.2 million, from 4.3 million to 5.9 million and from 35.5 million to 64.4 million, "
            "and the plans were pursued with urgency across the whole economy in every region and sector. ")
    words_per_paragraph = len(body.split())
    paragraph = (body * 5).strip()
    essay = "\n\n".join([paragraph] * 4)
    true_words = words_per_paragraph * 20
    assert 800 <= true_words <= 1100
    assert not [f for f in structural_checks(parse(essay, task_type="essay")) if f.code == "HI-STR-004"]


# ------------------------------------------------------------------ chronology: durations, containment, same year, a named event


def _relations(text: str):
    return [r for s in split_sentences(text) for r in chronology_relations(s, text)]


def test_the_genuine_hi_p4_and_hi_t10_relations_are_decided_and_hold():
    rels = _relations(HI_P4) + _relations(HI_T10)
    kinds = sorted(r.kind for r in rels)
    assert kinds == ["order", "same_year", "within", "within"], [(r.kind, r.statement) for r in rels]
    assert all(r.decided and not r.violated for r in rels)


@pytest.mark.parametrize("base,old,new,kind", [
    (HI_P4, "ran from 11 October 1899 to the Peace of Vereeniging on 31 May 1902", "ran from 31 May 1902 to the Peace of Vereeniging on 11 October 1899", "order"),
    (HI_P4, "Magersfontein on 11 December", "Magersfontein on 11 November", "within"),
    (HI_T10, "Railway Mania of 1845 to 1847", "Railway Mania of 1855 to 1857", "within"),
    (HI_P4, "so the poem's 1902 date falls", "so the poem's 1899 date falls", "same_year"),
    (HI_T10, "the Great Western reached Bristol in 1841.", "the Great Western reached Bristol in 1841, three years before the London and Birmingham opened.", "order"),
], ids=["reversed-span", "containment-of-a-day", "containment-of-a-range-in-a-decade", "same-year-as-the-close", "an-event-dated-earlier-in-the-sentence"])
def test_false_relations_are_violations_named_by_hi_chr_001_and_refuted_by_the_engine(base, old, new, kind):
    text = base.replace(old, new)
    assert text != base
    violated = [r for r in _relations(text) if r.violated]
    assert violated and violated[0].kind == kind and violated[0].decided
    rep = parse(text, supplied_texts=[PEER] if base is HI_P4 else [])
    proxy = [f for f in structural_checks(rep) if f.code == "HI-CHR-001"]
    assert proxy and proxy[0].claim_ids
    _ch, _reply, rc = hub_reply(text, P4_Q if base is HI_P4 else HI_T10_Q, [PEER] if base is HI_P4 else [])
    errors = [f for f in rc.findings if f.code == "INT-SUBJ-001" and "chronology" in f.message]
    assert errors and errors[0].claim_ids, [(f.code, f.message[:120]) for f in rc.findings]


def test_an_interval_against_an_event_the_sentence_never_dates_is_undecided():
    text = "The network grew quickly, and the Great Western reached Bristol in 1841, three years before the London and Birmingham opened."
    [rel] = _relations(text)
    assert not rel.decided and "does not date" in rel.reason
    assert [f.code for f in CorePack().checks(parse("The railways spread fast in 1841. " + text)) if f.code == "CORE-CHR-001"] == ["CORE-CHR-001"]
    # a reference with a number ('Article 48') is not an event dated elsewhere
    assert not _relations("Article 48 was promulgated in 1919. Brüning governed by emergency decree under Article 48 after the Reichstag rejected his budget in July 1930.")


# ------------------------------------------------------------------ the JSON stripper is linear (round-4 quadratic scan)


@pytest.mark.parametrize("text", [
    "{" * 5000 + ' The son "Beware the Jabberwock, my son!" ' + "}" * 5000,
    "[" * 20000 + "]" * 20000,
    " ".join('{"a": 1, "b": [' for _ in range(2000)) + " The turning point was 1930.",
    "[" * 8000 + '{"status": "ACCEPTED"}' + "]" * 8000,
], ids=["5000-nested-braces", "20000-deep-array", "2000-unclosed-fragments", "deep-array-around-a-receipt"])
def test_strip_json_spans_is_linear_and_agrees_with_a_stack_scan(text):
    # the 1 s bound, measured as in tests/timing.py (warm-up, median of five first runs, earlier heap frozen)
    timing = measure(lambda: strip_json_spans(text), bound=1.0, label="strip_json_spans")
    assert timing.holds, timing
    small = text[:200] + text[-200:]
    reference = []
    i = 0
    while i < len(small):  # the old per-opener stack scan, on a slice small enough to stay fast
        end = _balanced_end(small, i) if small[i] in "{[" else None
        if end is not None and '"' in small[i:end] and ":" in small[i:end] and strip_json_spans(small[i:end])[1]:
            i = end
            continue
        reference.append(small[i])
        i += 1
    assert strip_json_spans(small)[0] == "".join(reference)


@pytest.mark.parametrize("text", [
    "{" * 5000 + ' The son "Beware the Jabberwock, my son!" ' + "}" * 5000,
    "Railway growth came in phases. " + "[" * 20000 + "]" * 20000,
    " ".join('{"a": 1, "b": [' for _ in range(2000)) + " The turning point was 1930.",
], ids=["5000-nested-braces", "20000-deep-array", "2000-unclosed-fragments"])
def test_bracket_heavy_answers_cross_the_history_branch_quickly(text):
    # round 5 measured 11.5 s, 166 s and 23.5 s for these on the History branch; each now takes well under a second.
    # The 2 s bound is unchanged and measured as in tests/timing.py: a warm-up run, then the median of five runs, each a
    # first crossing (caches emptied) with the earlier heap frozen.
    timing = measure(lambda: hub_reply(text, HI_T10_Q), bound=2.0, label="History branch")
    assert timing.holds, timing
    assert all(rc.status is not None for _ch, _reply, rc in timing.results)
