"""Integrity behaviour found wanting by the round-4 arena overseers: a contradiction inside one claim attributed to an
innocent claim that merely repeated its premises (and a disclosure then demanded of a faithful synthesis), figures
written in words and scale words invisible to the figure check, a verdict reversed by re-pairing a figure the sources
state elsewhere, a comma that cut a date from its event, a merged claim silently dropping a dated statement, and a
synthesis that alters or invents quotations, reverses a direction, drops a negation or turns 'roughly' into 'exactly'."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity import Synthesis, SynthesizedClaim, WorkPlan, run_integrity_checks
from epinoic_logic.integrity.cross_check import check_cross_report_consistency, joint_problem
from epinoic_logic.integrity.ledger import check_synthesis_ledger, figure_pairing_differences, figure_tokens
from epinoic_logic.engine import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

KEY = b"round4-integrity-test-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
DATA = json.loads((Path(__file__).parent / "data" / "r4_hi_t8.json").read_text())
PROBLEMS = {cid: Problem.model_validate(p) for cid, p in DATA["problems"].items()}
TEXTS = {c["claim_id"]: c["claim_text"] for c in DATA["claims"]}
REQ, TASK = "req-hi-t8", "hi-t8"


def codes(fs):
    return [f.code for f in fs]


def V(n):
    return {"op": "var", "name": n}


def I(v):
    return {"op": "int", "value": str(v)}


def eq(a, b):
    return {"op": "eq", "left": a, "right": b}


def prob(cid, premises, conclusion=None, request_id=REQ):
    data = {"problem_id": f"p-{cid}", "request_id": request_id, "claim_id": cid, "query": "entailment" if conclusion else "consistency",
            "symbols": [{"name": n, "sort": "Int"} for n in ("x", "y", "z")],
            "premises": [{"id": f"P{i}", "expr": e, "grounding": {"kind": "general_knowledge", "certainty": "probable"}} for i, e in enumerate(premises)]}
    if conclusion:
        data["conclusion"] = {"id": "C", "expr": conclusion}
    return Problem.model_validate(data)


# ------------------------------------------------------------ claim-minimal conflict attribution (hi-t8, r4)


@pytest.mark.parametrize("order", [["h1.5"], ["h1.1", "h1.5"], ["h1.5", "h1.1"], ["h1.2", "h1.5"], ["h1.1", "h1.2", "h1.3", "h1.4", "h1.5", "h1.6"],
                                   ["h1.6", "h1.5", "h1.4", "h1.3", "h1.2", "h1.1"]])
def test_hi_t8_self_refuting_h1_5_is_named_alone_whatever_the_pooling_order(order):
    # h1.5's own premises u1929 = 1.9 and u1930 = 3.1 refute its pooled conclusion (u1930 - u1929)/1.9 = 0.6; h1.1 restates the
    # same figures under the shared glossary, so the unsat core could use h1.1's copies: the claim-minimal attribution names h1.5 only
    res, f = check_cross_report_consistency([PROBLEMS[c] for c in order], request_id=REQ, config=CFG, signing_key=KEY)
    assert res is not None and res.status is S.INCONSISTENT_PREMISES
    assert [(x.code, x.severity, x.claim_ids) for x in f] == [("INT-CONFLICT-005", "error", ["h1.5"])]
    assert "concl (conclusion)" in f[0].message and "h1.1" not in f[0].message
    assert f[0].formal_result_id and res.result_id in [f[0].formal_result_id, *f[0].related_result_ids]


def test_h1_1_alone_is_consistent_and_never_named():
    res, f = check_cross_report_consistency([PROBLEMS["h1.1"]], request_id=REQ, config=CFG)
    assert res.status is S.CONSISTENT and f == []


def test_an_assumed_reading_is_a_warning_not_an_error_charged_to_the_specialist():
    res, f = check_cross_report_consistency(list(PROBLEMS.values()), request_id=REQ, config=CFG, assumed_readings={"h1.5"})
    assert [(x.code, x.severity, x.claim_ids) for x in f] == [("INT-CONFLICT-005", "warning", ["h1.5"])]
    assert "assumed reading" in f[0].message and "AMBIGUOUS_TRANSLATION" in f[0].message


def test_after_setting_a_self_refuting_conclusion_aside_a_real_conflict_is_still_found():
    a = prob("a", [eq(V("x"), I(1))], eq(V("x"), I(2)))      # refutes itself
    b = prob("b", [eq(V("y"), I(5))])
    c = prob("c", [eq(V("y"), I(6))])                         # contradicts b
    for order in ([a, b, c], [c, b, a], [b, a, c]):
        _, f = check_cross_report_consistency(order, request_id=REQ, config=CFG)
        assert sorted((x.code, tuple(x.claim_ids)) for x in f) == [("INT-CONFLICT-001", ("b", "c")), ("INT-CONFLICT-005", ("a",))]


@pytest.mark.parametrize("first", ["innocent", "guilty"])
def test_duplicate_premises_across_claims_never_implicate_the_innocent_claim(first):
    innocent = prob("innocent", [eq(V("x"), I(1)), eq(V("y"), I(2))], eq(V("z"), I(7)))
    guilty = prob("guilty", [eq(V("x"), I(1)), eq(V("y"), I(2))], eq({"op": "add", "args": [V("x"), V("y")]}, I(4)))
    order = [innocent, guilty] if first == "innocent" else [guilty, innocent]
    _, f = check_cross_report_consistency(order, request_id=REQ, config=CFG)
    assert [(x.code, x.claim_ids) for x in f] == [("INT-CONFLICT-005", ["guilty"])]


def test_a_conflict_names_only_claims_it_needs():
    # x = 1, y = 2 and x + y = 4 contradict only together; w is an unrelated bystander that shares x's premise
    a = prob("a", [eq(V("x"), I(1))])
    b = prob("b", [eq(V("y"), I(2))])
    c = prob("c", [eq({"op": "add", "args": [V("x"), V("y")]}, I(4))])
    w = prob("w", [eq(V("z"), I(9))])
    for order in ([a, b, c, w], [w, c, b, a]):
        _, f = check_cross_report_consistency(order, request_id=REQ, config=CFG)
        [c1] = [x for x in f if x.code == "INT-CONFLICT-001"]
        named = set(c1.claim_ids)
        assert named == {"a", "b", "c"} and "claim-minimal" in c1.message
        for drop in named:  # every claim named is needed: without it the rest is consistent
            rest = [p for p in (a, b, c) if p.claim_id != drop]
            joint, _, _ = joint_problem(rest, request_id=REQ)
            assert verify(joint, CFG).status is S.CONSISTENT


def _report(claims, rid="rep-hi-t8-0", agent="history-specialist"):
    text = " ".join(c[1] for c in claims)
    return SpecialistReport(report_id=rid, request_id=REQ, task_id=TASK, agent_id=agent, subject="History", task_type="short_answer", original_response=text,
                            response_sha256=sha256_text(text), created_at="2026-10-11T11:00:00Z",
                            claims=[ClaimRecord(request_id=REQ, task_id=TASK, report_id=rid, agent_id=agent, subject="History", task_type="short_answer", claim_id=cid, claim_text=t,
                                                claim_role=role, materiality="material" if role == "point" else "supporting") for cid, t, role in claims])


def _hi_t8_report():
    roles = {c["claim_id"]: c["claim_role"] for c in DATA["claims"]}
    return _report([(cid, TEXTS[cid], roles[cid]) for cid in TEXTS])


def _synthesis(claims, rid="rep-hi-t8-0", conflicts=()):
    text = " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn-r4", request_id=REQ, task_id=TASK, combinator_agent_id="combinator", source_report_ids=[rid], claims=list(claims), conflicts=list(conflicts),
                     text=text, text_sha256=sha256_text(text), created_at="2026-10-11T12:00:00Z")


def test_a_faithful_hi_t8_synthesis_is_not_asked_to_disclose_a_self_refutation():
    plan = WorkPlan(plan_id="plan-hi-t8", request_id=REQ, task_id=TASK, subject="History", task_type="short_answer", selected_agent_ids=["history-specialist", "combinator"])
    syn = _synthesis([SynthesizedClaim(claim_id=f"s{i}", text=c["text"], certainty=c["certainty"], source_claim_ids=c["source_claim_ids"], transformation=c["transformation"])
                      for i, c in enumerate(DATA["synthesis"])])
    rep = run_integrity_checks(plan, [_hi_t8_report()], syn, dict(PROBLEMS), signing_key=KEY, config=CFG)
    assert [(f.code, f.claim_ids) for f in rep.findings if f.code.startswith("INT-CONFLICT")] == [("INT-CONFLICT-005", ["h1.5"])]
    c5 = next(f for f in rep.findings if f.code == "INT-CONFLICT-005")
    assert c5.formal_result_id in rep.formal_result_ids and set(c5.related_result_ids) <= set(rep.formal_result_ids)


# ------------------------------------------------------------ figures in words and scale words (INT-LEDGER-023)


def _ledger(source_claims, syn_text, sources, transformation="paraphrased", supplied=()):
    rep = _report(source_claims)
    if supplied:
        rep = rep.model_copy(update={"supplied_texts": list(supplied)})
    return check_synthesis_ledger([rep], _synthesis([SynthesizedClaim(claim_id="s9", text=syn_text, certainty="probable", source_claim_ids=sources, transformation=transformation)]))


P3_S05 = "The scale of that heart matters, because the History specialist gives \"close to a million inhabitants\" and calls London \"the largest city in Europe\"."
P3_H12 = "London in 1802 was the largest city in Europe, with close to a million inhabitants at the first national census of 1801."
T7_H13 = ("Signed on 28 June 1919, the treaty took about 13 per cent of Germany's pre-war European territory and roughly a tenth of its population, limited the army "
          "to 100,000 men under Article 160, and under Article 231 placed responsibility for the war on Germany and its allies.")


def test_F1a_a_figure_in_words_changed_in_a_paraphrase_is_named():
    syn = "The scale of that heart matters, because the History specialist gives close to two million inhabitants and calls London the largest city in Europe."
    f = [x for x in _ledger([("p1-s05", P3_S05, "interpretation")], syn, ["p1-s05"]) if x.code == "INT-LEDGER-023"]
    assert len(f) == 1 and f[0].severity == "error" and "'two million'" in f[0].message
    faithful = "The scale of that heart matters, because the History specialist gives close to a million inhabitants and calls London the largest city in Europe."
    assert not [x for x in _ledger([("p1-s05", P3_S05, "interpretation")], faithful, ["p1-s05"]) if x.code in ("INT-LEDGER-023", "INT-LEDGER-024")]


def test_F1b_the_same_change_under_carried_is_an_error_not_only_a_text_difference():
    syn = P3_H12.replace("close to a million inhabitants", "close to two million inhabitants")
    f = _ledger([("h1.2", P3_H12, "point")], syn, ["h1.2"], transformation="carried")
    assert {"INT-LEDGER-010", "INT-LEDGER-023"} <= set(codes(f))
    assert [x.severity for x in f if x.code == "INT-LEDGER-023"] == ["error"]


def test_F1c_a_figure_in_digits_exchanged_with_a_figure_in_words_is_named():
    syn = T7_H13.replace("about 13 per cent of Germany's pre-war European territory and roughly a tenth of its population",
                         "roughly a tenth of Germany's pre-war European territory and about 13 per cent of its population")
    f = [x for x in _ledger([("h1.3", T7_H13, "evidence")], syn, ["h1.3"]) if x.code == "INT-LEDGER-023"]
    assert len(f) == 1 and "(exchanged)" in f[0].message and "'a tenth' (0.1)" in f[0].message and "'13'" in f[0].message
    assert not [x for x in _ledger([("h1.3", T7_H13, "evidence")], T7_H13, ["h1.3"]) if x.code == "INT-LEDGER-023"]


@pytest.mark.parametrize("changed,shown", [("6.1 billion", "6.1 billion"), ("6.1 thousand", "6.1 thousand")])
def test_a_changed_scale_word_is_a_changed_figure(changed, shown):
    src = "Unemployment peaked at about 6.1 million in February 1932."
    f = [x for x in _ledger([("h1.2", src, "evidence")], src.replace("6.1 million", changed), ["h1.2"]) if x.code == "INT-LEDGER-023"]
    assert len(f) == 1 and f"'{shown}' where the cited sources state 6.1 million" in f[0].message and "changed scale word" in f[0].message


def test_an_elided_scale_is_not_held_to_one_and_equal_values_meet():
    src = "Unemployment rose from 1.9 to 6.1 million between 1929 and 1932."
    assert not [x for x in _ledger([("h1.2", src, "evidence")], "Unemployment rose from 1.9 million to 6.1 million between 1929 and 1932.", ["h1.2"]) if x.code == "INT-LEDGER-023"]
    assert not [x for x in _ledger([("h1.2", "The city had close to a million inhabitants.", "evidence")], "The city had close to 1,000,000 inhabitants.", ["h1.2"]) if x.code == "INT-LEDGER-023"]


def test_figure_tokens_read_figures_written_in_words_only_where_they_are_quantities():
    assert figure_tokens("close to a million inhabitants, two-thirds of the seats, thirteen per cent, two hundred and sixty students") == {"1", "0.6667", "13", "260"}
    assert figure_tokens("one of the two poems; a third attempt; Thirteen Days") == set()


# ------------------------------------------------------------ re-pairing (INT-LEDGER-023)


def test_a_verdict_reversed_by_re_pairing_a_figure_stated_elsewhere_is_named():
    srcs = [TEXTS["h1.4"], TEXTS["h1.5"], TEXTS["h1.6"]]
    reversed_ = "The turning point was 1932: the annual average grew by roughly 60 per cent that year, the greatest proportional rise of the period."
    d = figure_pairing_differences(reversed_, srcs)
    assert len(d) == 1 and "'1932' is stated with 'point', 'turning'" in d[0] and "only with '1930'" in d[0] and "counter-case" in d[0] and "(re-paired)" in d[0]
    assert figure_pairing_differences(reversed_.replace("1932:", "1930:"), srcs) == []
    f = [x for x in _ledger([(c, TEXTS[c], "evidence") for c in ("h1.4", "h1.5", "h1.6")], reversed_, ["h1.4", "h1.5", "h1.6"], transformation="merged") if x.code == "INT-LEDGER-023"]
    assert len(f) == 1 and "(re-paired)" in f[0].message


def test_a_new_pairing_of_a_figure_the_sources_state_without_an_event_is_not_a_re_pairing():
    srcs = ["Annual averages climbed from about 1.9 million in 1929 to 3.1 million in 1930, 4.5 million in 1931 and 5.6 million in 1932."]
    assert figure_pairing_differences("Unemployment rose to 4.5 million in 1931.", srcs) == []


R3_T5 = ["After U-2 photographs of 14 October showed missile sites under construction in Cuba, Khrushchev offered on 26 October to remove them in exchange for a pledge that the United States would not invade Cuba.",
         "The quarantine, announced on 22 October and in force from 24 October, stopped further shipments and forced Moscow to choose between withdrawal and confrontation.",
         "On 27 October, the day an American U-2 was shot down over the island, a second message added a demand for the removal of the Jupiter missiles in Turkey."]


def test_r3_hi_t5_announced_and_in_force_dates_swapped_are_named():
    d = figure_pairing_differences("The quarantine, announced on 24 October and in force from 22 October, stopped further shipments.", R3_T5)
    assert len(d) == 1 and "(exchanged)" in d[0] and "'announced'" in d[0] and "'force'" in d[0]
    assert figure_pairing_differences("The quarantine, announced on 22 October and in force from 24 October, stopped further shipments.", R3_T5) == []


def test_r3_hi_t5_letters_swapped_are_named_though_a_comma_follows_the_source_date():
    swapped = "Khrushchev offered on 27 October to remove them in exchange for a pledge; on 26 October a second message added a demand for the removal of the Jupiter missiles."
    d = figure_pairing_differences(swapped, R3_T5)
    assert d and "'27'" in d[0] and "'offered'" in d[0] and "'26'" in d[0]
    faithful = "Khrushchev offered on 26 October to remove them in exchange for a pledge; on 27 October a second message added a demand for the removal of the Jupiter missiles."
    assert figure_pairing_differences(faithful, R3_T5) == []


# ------------------------------------------------------------ dropped content under 'merged' (INT-LEDGER-024)


P3_H14 = "Much of its air came from coal."
P3_H15 = ("Sea-coal was carried to the Thames by colliers from Newcastle, roughly a million tons a year by about 1800, and it was burned in domestic grates and in breweries, "
          "glassworks, soap and lime works, so that a dense smoke hung over the city on most days; John Evelyn had complained of the same problem in 1661 in his Fumifugium.")
P3_MERGED = ("Much of London's air came from coal: sea-coal carried to the Thames by colliers from Newcastle, roughly a million tons a year by about 1800, was burned in domestic "
             "grates and in breweries, glassworks, soap and lime works, so that a dense smoke hung over the city on most days.")


def test_a_merged_claim_that_leaves_out_a_dated_statement_is_a_warning():
    f = [x for x in _ledger([("h1.4", P3_H14, "analysis"), ("h1.5", P3_H15, "evidence")], P3_MERGED, ["h1.4", "h1.5"], transformation="merged") if x.code == "INT-LEDGER-024"]
    assert len(f) == 1 and f[0].severity == "warning" and "['1661']" in f[0].message and "merged" in f[0].message
    whole = P3_MERGED[:-1] + "; John Evelyn had complained of the same problem in 1661."
    assert not [x for x in _ledger([("h1.4", P3_H14, "analysis"), ("h1.5", P3_H15, "evidence")], whole, ["h1.4", "h1.5"], transformation="merged") if x.code == "INT-LEDGER-024"]


# ------------------------------------------------------------ quotations and meaning of a synthesized claim (INT-LEDGER-025/026)


POEM = SuppliedText(document_id="doc-wb", title="Composed upon Westminster Bridge", author="William Wordsworth",
                    text="This City now doth, like a garment, wear\nThe beauty of the morning; silent, bare,\nDear God! the very houses seem asleep;")
EN_T7 = "The city is first animated when it \"doth, like a garment, wear\" the morning's beauty, and \"the very houses seem asleep\"."


@pytest.mark.parametrize("syn,bad", [
    ("The city is animated when it \"doth, like a cloak, wear\" the morning's beauty.", "doth, like a cloak, wear"),
    ("The city is animated, \"a sleeping giant\" that \"doth, like a garment, wear\" the morning.", "a sleeping giant"),
])
def test_an_altered_or_invented_quotation_in_a_synthesized_claim_is_an_error(syn, bad):
    f = [x for x in _ledger([("p1-s01", EN_T7, "interpretation")], syn, ["p1-s01"], supplied=[POEM]) if x.code == "INT-LEDGER-025"]
    assert len(f) == 1 and f[0].severity == "error" and bad in f[0].message and f[0].claim_ids == ["s9", "p1-s01"]


def test_faithful_quotations_in_a_synthesized_claim_are_not_named():
    syn = "The city \"doth, like a garment, wear\" the beauty of the morning, and \"the very houses seem asleep\"."
    assert not [x for x in _ledger([("p1-s01", EN_T7, "interpretation")], syn, ["p1-s01"], supplied=[POEM]) if x.code == "INT-LEDGER-025"]


@pytest.mark.parametrize("src,syn,transformation,expect", [
    ("Annual averages climbed from 1.9 million in 1929 to 3.1 million in 1930.", "Annual averages fell from 1.9 million in 1929 to 3.1 million in 1930.", "paraphrased", "states a fall"),
    ("The poem never mentions the war, so this reading rests on the History specialist's context.", "The poem mentions the war, so this reading rests on the History specialist's context.", "paraphrased", "drops the negation"),
    ("The annual average grew by roughly 60 per cent that year.", "The annual average grew by exactly 60 per cent that year.", "merged", "'exactly 60'"),
])
def test_a_reversed_direction_a_dropped_negation_or_an_exact_figure_is_a_warning(src, syn, transformation, expect):
    f = [x for x in _ledger([("h1.5", src, "evidence")], syn, ["h1.5"], transformation=transformation) if x.code == "INT-LEDGER-026"]
    assert len(f) == 1 and f[0].severity == "warning" and expect in f[0].message
    assert not [x for x in _ledger([("h1.5", src, "evidence")], src, ["h1.5"], transformation=transformation) if x.code == "INT-LEDGER-026"]
