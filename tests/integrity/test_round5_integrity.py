"""Ledger and glossary behaviour found wanting by the round-5 arena overseers, on the round-5 material: a decade moved or
a verdict re-dated, a degree or comparative verdict reversed, a negation added under 'merged', a cause or a count written
in words changed, a view or a quotation credited to someone who does not hold it, figures reported dropped although
another synthesized claim carries them, a from-memory label dropped, and glosses that differ only in word order reported
as different meanings."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity.cross_check import check_cross_report_consistency, gloss_content
from epinoic_logic.integrity.ledger import aligned_changes, check_synthesis_ledger, figure_pairing_differences, figure_tokens
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
R5 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r5_material.json").read_text())
SPEC = R5["specialists"]
POEM = SuppliedText(**SPEC["en-p4"]["supplied_texts"][0])
EN_P4 = SPEC["en-p4"]["response_text"]

# hi-t10 as the History branch delivers it (claim ids by sentence; h1.4 carries the method's inline label)
HI_T10 = [
    ("h1.1", "Railway growth in Britain between 1830 and 1870 came in phases, and the 1840s gave the network its shape.", "point", "material", []),
    ("h1.2", "The Liverpool and Manchester Railway opened in September 1830 over 31 miles, the first inter-city line worked by steam locomotives on a timetable.", "evidence", "supporting", []),
    ("h1.3", "The network then grew from almost nothing: the London and Birmingham Railway opened in 1838, and the Great Western reached Bristol in 1841.", "evidence", "supporting", []),
    ("h1.4", "Route mileage was about 1,500 by 1840 and about 6,000 by 1850 (from memory; check your notes).", "evidence", "supporting",
     ["the sentence carries the method's own label inline ('from memory; check your notes'); the label is kept out of the claim's role and its dated items are from memory"]),
    ("h1.5", "The 1840s, which included the Railway Mania of 1845 to 1847, added roughly 4,500 miles, more than any other decade of the period, and by 1848 a line ran from London through Carlisle to Glasgow.", "evidence", "supporting", []),
    ("h1.6", "The 1850s and 1860s took the network to about 13,000 miles by 1870, but largely through branches and extensions to an existing framework.", "evidence", "supporting", []),
    ("h1.7", "The 1840s were the most decisive decade.", "judgement", "material", []),
    ("h1.8", "Measured by what the network could do, carrying traffic between the main cities, they created the trunk routes that later growth filled in, whereas the 1830s, though faster in relative terms, built only the first links.", "analysis", "supporting", []),
]
HI_T9_H1_1 = "The Five-Year Plans transformed Soviet heavy industry to a large extent in scale and geography, but far less in efficiency and in the quality of its output."
HI_T9_H1_2 = "Between 1928 and 1932 official figures show pig iron rising from about 3.3 million tonnes to about 6.2 million, steel from about 4.3 million to 5.9 million and coal from about 35 million tonnes to about 64 million."
HI_T9_H1_3 = ("These totals fell short of the First Plan's original target of about 10 million tonnes of pig iron, and later Western reassessments reduced the growth that the "
              "official series claimed, yet the expansion was real and it was directed by state investment rather than by market demand.")
# hi-p4 as delivered: h1.1 is the English specialist's view, roled perspective
HI_P4 = [
    ("h1.1", "The English specialist's paragraph identifies the speaker's motive as poverty: the casualness \"exposes a motive of poverty\", and the key word \"traps\" suggests a man who \"sold his belongings for want of work\".", "perspective", "supporting", []),
    ("h1.3", "The Second Boer War ran from 11 October 1899 to the Peace of Vereeniging on 31 May 1902 (from memory; check your notes), so the poem's 1902 date falls at the war's close.", "evidence", "supporting", ["the sentence carries the method's own label inline ('from memory; check your notes')"]),
    ("h1.4", "Reverses in December 1899, including the Highland Brigade's defeat at Magersfontein on 11 December (from memory), helped drive the call for volunteers, and the Imperial Yeomanry's first contingents sailed in early 1900 (from memory).", "evidence", "supporting", []),
    ("h1.5", "A regular private's pay of about a shilling a day (from memory) was a real draw for men without work, though historians dispute how far unemployment, rather than patriotism or adventure, drove enlistment.", "evidence", "supporting", []),
    ("h1.6", "The losses were heavy: roughly 22,000 British and imperial deaths, the large majority from disease, chiefly enteric fever (from memory; approximate, and sources differ).", "evidence", "supporting", []),
    ("h1.7", "Against that toll, Hardy's speaker calls the conflict a \"quaint and curious war\", a line that reads as a sardonic frame for a war that killed far more men through disease than in battle.", "link", "material", []),
]
EN_P4_CLAIMS = [
    ("p1-point", "Hardy's dramatic monologue lets the speaker justify the killing in casual terms, and the casualness exposes a motive of poverty and a view of the enemy that his justification cannot sustain.", "point", "material", []),
    ("p1-s03", "The key word \"traps\", which conventionally denotes snares but in colloquial use means a man's gear and belongings, suggests a man who has sold his belongings for want of work, so poverty becomes the motive, as the closing \"No other reason why\" confirms.", "interpretation", "supporting", []),
]


def report(agent: str, rid: str, claims, *, text: Optional[str] = None, supplied=(), subject="History", task_type="short_answer", req="req-x", task="x") -> SpecialistReport:
    body = text if text is not None else " ".join(c[1] for c in claims)
    return SpecialistReport(report_id=rid, request_id=req, task_id=task, agent_id=agent, subject=subject, task_type=task_type, original_response=body,
                            response_sha256=sha256_text(body), supplied_texts=list(supplied), created_at="2026-10-11T12:00:00Z",
                            claims=[ClaimRecord(request_id=req, task_id=task, report_id=rid, agent_id=agent, subject=subject, task_type=task_type, claim_id=cid, claim_text=t,
                                                claim_role=role, materiality=mat, certainty="probable", assumptions=list(assumptions)) for cid, t, role, mat, assumptions in claims])


def synthesis(claims, report_ids, req="req-x", task="x") -> Synthesis:
    scs = [SynthesizedClaim(claim_id=cid, text=t, certainty="probable", source_claim_ids=src, transformation=tf) for cid, t, src, tf in claims]
    body = " ".join(c.text for c in scs)
    return Synthesis(synthesis_id="syn-r5", request_id=req, task_id=task, combinator_agent_id="dummy-combinator", source_report_ids=report_ids, claims=scs, text=body,
                     text_sha256=sha256_text(body), created_at="2026-10-11T15:00:00Z")


def by_code(findings, code):
    return [f for f in findings if f.code == code]


def t10_report():
    return report("history-specialist", "rep-hi-t10", HI_T10)


def t10_genuine():
    return [(f"s{i}", c["text"], c["source_claim_ids"], c["transformation"]) for i, c in enumerate(R5["syntheses"]["hi-t10"]["claims"])]


def p4_reports():
    peer = SuppliedText(document_id="peer:en-p4", title="english-specialist report rep-en-p4-0 relayed through the hub", author="english-specialist", text=EN_P4)
    en = report("english-specialist", "rep-en-p4", EN_P4_CLAIMS, text=EN_P4, supplied=[POEM], subject="English A: Literature", task_type="analytical_paragraph")
    hi = report("history-specialist", "rep-hi-p4", HI_P4, text=SPEC["hi-p4"]["response_text"], supplied=[peer])
    return [en, hi]


# ------------------------------------------------------------------ (a) decades are dates


def test_a_decade_is_one_date_token():
    assert figure_tokens("the 1840s, which included the Railway Mania of 1845 to 1847") == {"1840s", "1845", "1847"}
    assert figure_tokens("the 1840's and the 1850’s") == {"1840s", "1850s"}


def test_r5_hi_t10_synthesis_moving_the_railway_mania_to_the_1850s_is_int_ledger_023():
    claims = t10_genuine()
    claims[1] = (claims[1][0], claims[1][1].replace("and the 1840s, which included", "and the 1850s, which included"), claims[1][2], claims[1][3])
    [f] = by_code(check_synthesis_ledger([t10_report()], synthesis(claims, ["rep-hi-t10"])), "INT-LEDGER-023")
    assert f.severity == "error" and "'1850s'" in f.message and f.claim_ids[0] == "s1"
    assert not by_code(check_synthesis_ledger([t10_report()], synthesis(t10_genuine(), ["rep-hi-t10"])), "INT-LEDGER-023")


def test_r5_hi_t10_verdict_moved_to_the_1850s_is_int_ledger_023():
    claims = t10_genuine()
    claims[3] = (claims[3][0], claims[3][1].replace("the 1840s gave the network its shape and were the most decisive decade", "the 1850s gave the network its shape and were the most decisive decade"), claims[3][2], claims[3][3])
    [f] = by_code(check_synthesis_ledger([t10_report()], synthesis(claims, ["rep-hi-t10"])), "INT-LEDGER-023")
    assert "'1850s'" in f.message and f.claim_ids[:4] == ["s3", "h1.1", "h1.7", "h1.8"]


def test_a_thousands_separated_quantity_re_dated_to_another_stated_year_is_named():
    syn = "Route mileage was about 1,500 by 1845 and about 6,000 by 1850, and the 1840s, which included the Railway Mania of 1845 to 1847, added roughly 4,500 miles, more than any other decade of the period."
    srcs = [HI_T10[3][1], HI_T10[4][1]]
    assert figure_pairing_differences(syn, srcs) == ["'1,500' is dated 1845, where the cited sources date it ['1840']"]
    assert figure_pairing_differences(syn.replace("1,500 by 1845", "1,500 by 1840"), srcs) == []


# ------------------------------------------------------------------ (b) degree, comparative, negation, direction, cause


@pytest.mark.parametrize("transformation", ["merged", "paraphrased", "generalized"])
def test_r5_hi_t9_degree_verdict_reversed_is_int_ledger_026(transformation):
    src = report("history-specialist", "rep-hi-t9", [("h1.1", HI_T9_H1_1, "point", "material", [])])
    syn = "The Five-Year Plans transformed Soviet heavy industry to a limited extent in scale and geography but far more in efficiency and in the quality of its output."
    [f] = by_code(check_synthesis_ledger([src], synthesis([("s0", syn, ["h1.1"], transformation)], ["rep-hi-t9"])), "INT-LEDGER-026")
    assert f.severity == "warning" and "reverses a degree verdict" in f.message and "'to a large extent in'" in f.message
    assert "reverses a comparative or superlative" in f.message and "far less in efficiency" in f.message
    assert not by_code(check_synthesis_ledger([src], synthesis([("s0", HI_T9_H1_1, ["h1.1"], transformation)], ["rep-hi-t9"])), "INT-LEDGER-026")


@pytest.mark.parametrize("old,new,expect", [
    ("were the most decisive decade", "were not the most decisive decade", "adds a negation"),
    ("more than any other decade", "less than any other decade", "reverses a comparative"),
])
def test_r5_hi_t10_merged_verdict_negated_or_comparative_reversed_is_named(old, new, expect):
    claims = t10_genuine()
    idx = 3 if "decisive" in old else 1
    claims[idx] = (claims[idx][0], claims[idx][1].replace(old, new), claims[idx][2], claims[idx][3])
    [f] = by_code(check_synthesis_ledger([t10_report()], synthesis(claims, ["rep-hi-t10"])), "INT-LEDGER-026")
    assert expect in f.message and f.claim_ids[0] == f"s{idx}"


def test_r5_hi_t9_direction_and_target_reversed_although_sources_state_both_directions():
    src = report("history-specialist", "rep-hi-t9", [("h1.2", HI_T9_H1_2, "evidence", "supporting", []), ("h1.3", HI_T9_H1_3, "evidence", "supporting", [])])
    genuine = R5["syntheses"]["hi-t9"]["claims"][1]["text"]
    for old, new, expect in (("pig iron rising", "pig iron falling", "reverses the direction of a change"), ("fell short of", "exceeded", "reverses a comparison with a target")):
        [f] = by_code(check_synthesis_ledger([src], synthesis([("s1", genuine.replace(old, new), ["h1.2", "h1.3"], "merged")], ["rep-hi-t9"])), "INT-LEDGER-026")
        assert expect in f.message
    assert not by_code(check_synthesis_ledger([src], synthesis([("s1", genuine, ["h1.2", "h1.3"], "merged")], ["rep-hi-t9"])), "INT-LEDGER-026")


def test_r5_p4_cause_changed_in_a_copied_statement_is_named():
    genuine = R5["syntheses"]["hi-p4"]["claims"][3]["text"]
    reps = p4_reports()
    [f] = by_code(check_synthesis_ledger(reps, synthesis([("s3", genuine.replace("the large majority from disease", "the large majority from battle"), ["h1.6", "h1.7"], "merged")], ["rep-hi-p4"])), "INT-LEDGER-026")
    assert "replaces 'disease' with 'battle'" in f.message
    assert not by_code(check_synthesis_ledger(reps, synthesis([("s3", genuine, ["h1.6", "h1.7"], "merged")], ["rep-hi-p4"])), "INT-LEDGER-026")


# ------------------------------------------------------------------ small counts written in words (Y4, W1, E7)


@pytest.mark.parametrize("transformation", ["merged", "carried", "paraphrased"])
def test_r5_p4_private_pay_doubled_in_words_is_int_ledger_023(transformation):
    syn = HI_P4[3][1].replace("about a shilling a day (from memory)", "about two shillings a day")
    found = by_code(check_synthesis_ledger(p4_reports(), synthesis([("h5", syn, ["h1.5"] if transformation != "merged" else ["h1.4", "h1.5"], transformation)], ["rep-hi-p4"])), "INT-LEDGER-023")
    assert len(found) == 1 and found[0].severity == "error" and "'two shillings' (2)" in found[0].message and "'a shilling' (1)" in found[0].message


@pytest.mark.parametrize("src,syn,shown", [
    ("The Imperial Yeomanry sent two contingents in 1900.", "The Imperial Yeomanry sent three contingents in 1900.", "'three contingents' (3)"),
    ("The war lasted three years.", "The war lasted four years.", "'four years' (4)"),
    ("I would love you ten years before the flood.", "I would love you twenty years before the flood.", "'twenty years' (20)"),
])
def test_small_counts_written_in_words_are_compared(src, syn, shown):
    figures, _meaning = aligned_changes(syn, src)
    assert figures and shown in figures[0]
    assert aligned_changes(src, src) == ([], [])


def test_a_faithful_count_in_words_is_not_named():
    src = report("history-specialist", "rep-hi-t10", HI_T10)
    syn = "The Liverpool and Manchester Railway opened in September 1830 over thirty-one miles, the first inter-city line worked by steam locomotives on a timetable."
    assert not by_code(check_synthesis_ledger([src], synthesis([("s2", syn, ["h1.2"], "paraphrased")], ["rep-hi-t10"])), "INT-LEDGER-023")


# ------------------------------------------------------------------ (c) who holds a view, who wrote a quotation


def test_r5_p4_view_credited_to_the_wrong_specialist_is_int_ledger_026():
    reps = p4_reports()
    wrong = "The History specialist reads the casualness as exposing a motive of poverty, with the key word 'traps' suggesting a man who 'sold his belongings for want of work'."
    [f] = by_code(check_synthesis_ledger(reps, synthesis([("s2", wrong, ["h1.1"], "paraphrased")], ["rep-en-p4", "rep-hi-p4"])), "INT-LEDGER-026")
    assert "credits the view to ['history-specialist']" in f.message and "['english-specialist']" in f.message
    genuine = R5["syntheses"]["hi-p4"]["claims"][2]["text"]  # "The English specialist reads the casualness ..." citing h1.1: right
    assert not by_code(check_synthesis_ledger(reps, synthesis([("s2", genuine, ["h1.1"], "paraphrased")], ["rep-en-p4", "rep-hi-p4"])), "INT-LEDGER-026")


def test_e12_history_dates_credited_to_the_english_specialist_is_int_ledger_026():
    reps = p4_reports()
    s = "The English specialist dates the war from 11 October 1899 to 31 May 1902 and counts roughly 22,000 deaths."
    [f] = by_code(check_synthesis_ledger(reps, synthesis([("s10", s, ["h1.3", "h1.6"], "merged")], ["rep-en-p4", "rep-hi-p4"])), "INT-LEDGER-026")
    assert "credits the view to ['english-specialist']" in f.message and "history-specialist" in f.message


@pytest.mark.parametrize("transformation,sources", [("merged", ["p1-point", "p1-s03"]), ("generalized", ["p1-point", "p1-s03"]), ("carried", ["p1-point"]), ("paraphrased", ["p1-point"])])
def test_v_the_english_specialists_words_presented_as_hardys_speakers_are_int_ledger_025(transformation, sources):
    s = "Hardy's speaker admits that his casualness \"exposes a motive of poverty\" and that he had \"sold his belongings for want of work\"."
    found = by_code(check_synthesis_ledger(p4_reports(), synthesis([("s9", s, sources, transformation)], ["rep-en-p4", "rep-hi-p4"])), "INT-LEDGER-025")
    assert len(found) == 1 and found[0].severity == "error" and "misattributed" in found[0].message
    assert "exposes a motive of poverty" in found[0].message and "doc-mhk" in found[0].message and "sold his belongings for want of work" in found[0].message


def test_e11_single_marked_quotation_credited_to_hardys_speaker_is_named_and_the_genuine_credit_is_not():
    reps = p4_reports()
    e11 = "Hardy's speaker admits that his own casualness 'exposes a motive of poverty'."
    [f] = by_code(check_synthesis_ledger(reps, synthesis([("s9", e11, ["p1-point"], "paraphrased")], ["rep-en-p4", "rep-hi-p4"])), "INT-LEDGER-025")
    assert "credited to" in f.message and "english-specialist" in f.message
    genuine = R5["syntheses"]["hi-p4"]["claims"][3]["text"]  # "... Hardy's speaker calls the conflict a 'quaint and curious war' ...": the poem holds it
    assert not by_code(check_synthesis_ledger(reps, synthesis([("s3", genuine, ["h1.6", "h1.7"], "merged")], ["rep-en-p4", "rep-hi-p4"])), "INT-LEDGER-025")
    reporting = "The English specialist argues that the casualness 'exposes a motive of poverty'."  # the outer speaker of a reporting clause holds it
    assert not by_code(check_synthesis_ledger(reps, synthesis([("s9", reporting, ["p1-point"], "paraphrased")], ["rep-en-p4", "rep-hi-p4"])), "INT-LEDGER-025")


# ------------------------------------------------------------------ INT-LEDGER-024 per source, INT-LEDGER-027 labels


def test_r5_hi_t10_genuine_synthesis_does_not_lose_figures_another_claim_carries():
    found = by_code(check_synthesis_ledger([t10_report()], synthesis(t10_genuine(), ["rep-hi-t10"])), "INT-LEDGER-024")
    assert [f.claim_ids[0] for f in found] == ["s1"] and "'1848'" in found[0].message  # the correct warning stays
    assert not any("'1830'" in f.message or "'1870'" in f.message for f in found)  # s0 carries 'between 1830 and 1870' of h1.1


def test_r5_hi_t10_and_p4_dropped_from_memory_labels_are_named():
    found = by_code(check_synthesis_ledger([t10_report()], synthesis(t10_genuine(), ["rep-hi-t10"])), "INT-LEDGER-027")
    assert [f.claim_ids[:2] for f in found] == [["s1", "h1.4"]] and found[0].severity == "warning" and "from memory; check your notes" in found[0].message
    labelled = [(cid, t.replace("by 1850,", "by 1850 (from memory),") if cid == "s1" else t, src, tf) for cid, t, src, tf in t10_genuine()]
    assert not by_code(check_synthesis_ledger([t10_report()], synthesis(labelled, ["rep-hi-t10"])), "INT-LEDGER-027")
    p4 = [(f"s{i}", c["text"], c["source_claim_ids"], c["transformation"]) for i, c in enumerate(R5["syntheses"]["hi-p4"]["claims"])]
    named = {f.claim_ids[0] for f in by_code(check_synthesis_ledger(p4_reports(), synthesis(p4, ["rep-hi-p4"])), "INT-LEDGER-027")}
    assert {"s0", "s1"} <= named  # h1.3 carried and h1.4 + h1.5 merged without their labels


def test_a_report_level_from_memory_note_labels_every_dated_item():
    claims = [("h1.1", "Coal output reached about 128 million tonnes by 1937.", "evidence", "supporting", []),
              ("h1.2", "Dates and figures are from memory; verify them against your notes before use.", "other", "supporting", [])]
    src = report("history-specialist", "rep-n", claims)
    [f] = by_code(check_synthesis_ledger([src], synthesis([("s0", claims[0][1], ["h1.1"], "carried")], ["rep-n"])), "INT-LEDGER-027")
    assert "a note of its report" in f.message


# ------------------------------------------------------------------ INT-GLOSSARY-005 compares meanings


def _gloss_problem(cid: str, name: str, meaning: str) -> Problem:
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-g", "claim_id": cid, "query": "consistency",
                                   "symbols": [{"name": name, "sort": "Real", "meaning": meaning}],
                                   "premises": [{"id": "P0", "expr": {"op": "gt", "left": {"op": "var", "name": name}, "right": {"op": "int", "value": "0"}}}]})


@pytest.mark.parametrize("a,b", [
    ("pig iron output in 1928 (million tonnes, about 3.3)", "pig iron output in 1928 (about 3.3 million tonnes)"),
    ("coal output in 1937 (million tonnes, about 128)", "coal output by 1937 (about 128 million tonnes)"),
    ("route mileage in 1870 (about 13,000)", "route mileage by 1870 (about 13,000)"),
])
def test_r5_glosses_in_another_word_order_are_one_meaning(a, b):
    assert gloss_content(a) == gloss_content(b)
    _res, f = check_cross_report_consistency([_gloss_problem("h1.1", "x", a), _gloss_problem("h1.2", "x", b)], request_id="req-g", config=CFG)
    assert not by_code(f, "INT-GLOSSARY-005")


def test_a_gloss_with_another_year_or_quantity_is_still_warned_and_names_the_difference():
    _res, f = check_cross_report_consistency([_gloss_problem("h1.1", "x", "route mileage in 1870 (about 13,000)"), _gloss_problem("h1.2", "x", "route mileage in 1860 (about 13,000)")],
                                             request_id="req-g", config=CFG)
    [g] = by_code(f, "INT-GLOSSARY-005")
    assert "different meanings" in g.message and "'1870'" in g.message and "'1860'" in g.message and "route mileage in 1870 (about 13,000)" in g.message
