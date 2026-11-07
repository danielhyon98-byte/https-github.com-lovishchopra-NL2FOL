"""Integrity behaviour found wanting by the round-8 clearance overseers (integrated round c1), fixed by the core fixer:

* critical: a faithful synthesis whose claims open with list markers ("(2) Re-add each total column.") was charged
  INT-LEDGER-031 (error), the markers read as figures the claims do not state (bm-t14);
* critical (regression of the round-7 glossary fix): a real contradiction between two specialists was no longer charged
  when one gloss of the shared symbol added a qualifier ("Montgomery", "of the oscillation", "as the Physics specialist
  gives it"): INT-CONFLICT-004 instead of INT-CONFLICT-001, and paraphrases of one quantity filled the receipts with
  INT-GLOSSARY-005. Two glosses now name different quantities only when their difference names one (rule same-gloss);
* critical: a candidate root a claim tests and rejects ("x = −5 is rejected because it does not satisfy x > 4", maa-t14
  m7.7) was pooled as an assertion about the unknown (rule candidate);
* major: "rather than" read as dropping or adding a negation (INT-LEDGER-030 on a faithful paraphrase), a reversed contrast,
  an exchanged term beside its article and a flipped true/false verdict were named only by INT-LEDGER-010.

The recorded material is in ``tests/channel/data/c1_core_material.json`` (copied verbatim from the round)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity import ledger as L
from epinoic_logic.integrity.cross_check import (
    candidate_tests, check_cross_report_consistency, gloss_content, gloss_difference, gloss_reading, rename_candidates_apart, split_by_gloss,
)
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import sha256_text

from ..core_hostile import SHAPES, one, sweep

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
C1 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "c1_core_material.json").read_text())


def codes(findings) -> list[str]:
    return [f.code for f in findings]


def conflicts(findings) -> list[tuple[str, str, list[str]]]:
    return [(f.code, f.severity, sorted(f.claim_ids)) for f in findings if f.code.startswith("INT-CONFLICT")]


# -------------------------------------------------------------------------- critical: list markers in the joined text


def test_list_markers_are_read_alike_in_the_claims_and_in_the_joined_text():
    assert L.text_outside_claims("Fix it: (1) Do A. (2) Do B. (3) Do C.", ["Fix it: (1) Do A.", "(2) Do B.", "(3) Do C."]) == []
    assert L.text_outside_claims("Fix it: Do A. Do B. Do C.", ["Fix it: Do A.", "Do B.", "Do C."]) == []  # the control the finding gave
    assert L.text_outside_claims("Steps: 1. Do A. 2. Do B.", ["Steps: 1. Do A.", "2. Do B."]) == []
    assert L.text_outside_claims("Steps: (1) Do A. (2) Do B.", ["Steps:", "Do A.", "Do B."]) == []  # a marker the text adds before a claim
    # controls: content outside the claims is still named, and a number that opens no claim is content
    assert L.text_outside_claims("Fix it: (1) Do A. Not (2) Do B.", ["Fix it: (1) Do A.", "(2) Do B."]) == ["not"]
    assert L.text_outside_claims("The score was 7 (2) Do B.", ["The score was 7", "Do B."]) == ["2"]
    assert L.text_outside_claims("The score was 7. (2) Do B. Never do C.", ["The score was 7.", "Do B."]) == ["never do c"]


def _synthesis(claims: list[str]) -> Synthesis:
    text = " ".join(claims)
    return Synthesis(synthesis_id="syn-bm-t14", request_id="req-bm-t14", task_id="bm-t14", combinator_agent_id="dummy-combinator", source_report_ids=["rep-bm-t14-0"],
                     claims=[SynthesizedClaim(claim_id=f"s{i}", text=t, certainty="probable", source_claim_ids=[f"g{i}"], transformation="carried") for i, t in enumerate(claims)],
                     ledger=[], text=text, text_sha256=sha256_text(text), created_at="2026-11-02T09:00:00Z")


def test_the_bm_t14_synthesis_text_is_its_claims_joined_and_draws_no_int_ledger_031():
    claims = [c["text"] for c in C1["syntheses"]["bm-t14"]["claims"]]
    assert any(c.startswith("(2) ") for c in claims) and any(c.startswith("(3) ") for c in claims)
    assert L.text_outside_claims(" ".join(claims), claims) == []
    assert "INT-LEDGER-031" not in codes(L._text_coverage(_synthesis(claims)))
    # control: one added sentence in the student-facing text is still INT-LEDGER-031
    s = _synthesis(claims)
    text = s.text + " The forecast is therefore wrong in every month."
    added = s.model_copy(update={"text": text, "text_sha256": sha256_text(text)})
    [f] = [x for x in L._text_coverage(added) if x.code == "INT-LEDGER-031"]
    assert "the forecast is therefore wrong in every month" in f.message


# ------------------------------------------------------------- critical: one quantity glossed in other words (same-gloss)


@pytest.mark.parametrize("a,b", [
    ("the bus boycott began on 5 December 1955", "the Montgomery bus boycott began on 5 December 1955"),
    ("East German forces closed the sector route on 13 August 1961", "East German forces closed the route in the early hours of 13 August 1961"),
    ("East German forces closed the sector route on 13 August 1961", "the route was closed on 13 August 1961"),
    ("amplitude of the oscillation, in metres", "amplitude in metres"),
    ("amplitude in metres", "amplitude, as the Physics specialist gives it, in metres"),
    ("amplitude of the trolley, in metres", "amplitude in metres"),
    ("maximum speed of the trolley, in m/s", "maximum speed in m/s"),
    ("period of the oscillation, in seconds", "period of the original oscillation, in seconds"),
    ("domestic producers' revenue before the tariff ($ million per year)", "domestic producers' revenue before the tariff ($ million)"),
    ("AD shifts left from AD₁ to AD₂", "AD shifts left from AD₁ to AD₂ in Diagram 1"),
    ("each visit earns a reward", "each visit earns him a reward"),
    ("price in Calvessa after the tariff ($ per tonne)", "steel price per tonne after the tariff ($), Economics specialist"),
    ("tariff per tonne ($)", "tariff per tonne of steel ($), as the Economics specialist states it"),
    ("area a: producer surplus gain ($ million per year)", "area a ($ million per year)"),
    ("the nominal annual rate is 3.6 per cent", "nominal annual rate (percent)"),
])
def test_glosses_that_name_one_quantity_are_one_meaning(a, b):
    assert gloss_difference(a, b) is None and gloss_difference(b, a) is None


@pytest.mark.parametrize("a,b,why", [
    ("marks allocated to part (a) of the question", "marks allocated to part (c) of the question", "part labels"),
    ("the target is 67", "the target is 20 (task setting for part (b))", "figures"),
    ("route mileage in 1870 (about 13,000)", "route mileage in 1860 (about 13,000)", "figures"),
    ("speed in m/s", "speed in km/h", "units"),
    ("period of the oscillation, in seconds", "period of the oscillation, in minutes", "units"),
    ("cost in $ million", "cost in $ billion", "scales"),
    ("GDP of France in 2019", "GDP of Germany in 2019", "proper names"),
    ("domestic producers' revenue before the tariff", "domestic producers' revenue after the tariff", "after"),
    ("number of red balls in the bag", "number of blue balls in the bag", "role words"),
    ("low on pass 1", "low after pass 1", "a shift"),
    ("the period", "the new period", "a shift"),
    ("the boycott began on 5 December 1955", "the boycott did not begin on 5 December 1955", "negates"),
    ("area a", "area b", "part labels"),
    ("speed of the cart", "speed of the ball", "content"),
    ("the Price of Steel in 2019", "the price of copper in 2019", "content"),
])
def test_glosses_that_name_different_quantities_stay_apart(a, b, why):
    found = gloss_difference(a, b)
    assert found is not None and why in found, found


def _bool_claim(cid: str, meaning: str, positive: bool) -> Problem:
    e = {"op": "var", "name": "boycott_began_5dec"}
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "consistency",
                                   "symbols": [{"name": "boycott_began_5dec", "sort": "Bool", "meaning": meaning}],
                                   "premises": [{"id": "pr", "expr": e if positive else {"op": "not", "arg": e}}]})


@pytest.mark.parametrize("gloss", ["the bus boycott began on 5 December 1955", "the Montgomery bus boycott began on 5 December 1955"])
def test_x17_a_denial_of_the_dated_fact_is_int_conflict_001_whichever_gloss(gloss):
    res, f = check_cross_report_consistency([_bool_claim("h1.2", "the bus boycott began on 5 December 1955", True), _bool_claim("p4-s04", gloss, False)],
                                            request_id="req-x", config=CFG)
    assert conflicts(f) == [("INT-CONFLICT-001", "error", ["h1.2", "p4-s04"])] and "INT-GLOSSARY-005" not in codes(f)


def test_r7_f1_a_denial_of_the_closure_is_int_conflict_001_again():
    """The round-7 controls F1/F2: the Literature specialist denies the 13 August 1961 closure the History specialist
    states, each translation glossing the closure in its own words."""
    def closure(cid, meaning, positive):
        e = {"op": "var", "name": "closed_1961"}
        return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "consistency",
                                       "symbols": [{"name": "closed_1961", "sort": "Bool", "meaning": meaning}],
                                       "premises": [{"id": "pr", "expr": e if positive else {"op": "not", "arg": e}}]})
    res, f = check_cross_report_consistency([closure("h1.1", "East German forces closed the sector route on 13 August 1961", True),
                                             closure("h1.6", "the route was closed on 13 August 1961", True),
                                             closure("p1-s11", "East German forces closed the route in the early hours of 13 August 1961", False)],
                                            request_id="req-x", config=CFG)
    assert [c for c in conflicts(f) if c[0] == "INT-CONFLICT-001"] and "INT-GLOSSARY-005" not in codes(f)
    assert all("p1-s11" in c[2] for c in conflicts(f) if c[0] == "INT-CONFLICT-001")


def _amp(cid: str, meaning: str, value: str) -> Problem:
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "consistency",
                                   "symbols": [{"name": "amp_m", "sort": "Real", "meaning": meaning}],
                                   "premises": [{"id": "pr", "expr": {"op": "eq", "left": {"op": "var", "name": "amp_m"}, "right": {"op": "real", "value": value}}}]})


@pytest.mark.parametrize("gloss", ["amplitude in metres", "amplitude of the oscillation, in metres", "amplitude, as the Physics specialist gives it, in metres",
                                   "amplitude of the trolley, in metres"])
def test_the_amplitude_probe_is_int_conflict_001_whatever_qualifier_one_gloss_adds(gloss):
    res, f = check_cross_report_consistency([_amp("s1.1", "amplitude in metres", "0.040"), _amp("m4.1", gloss, "0.400")], request_id="req-x", config=CFG)
    assert conflicts(f) == [("INT-CONFLICT-001", "error", ["m4.1", "s1.1"])]


def test_glosses_of_different_parts_still_read_apart():
    split, splits = split_by_gloss([_amp("a", "marks for part (a)", "2"), _amp("c", "marks for part (c)", "1")])
    assert [p.symbols[0].name for p in split] == ["amp_m", "amp_m_g2"] and set(splits) == {"amp_m"}
    res, f = check_cross_report_consistency([_amp("a", "marks for part (a)", "2"), _amp("c", "marks for part (c)", "1")], request_id="req-x", config=CFG)
    assert [c[0] for c in conflicts(f)] == ["INT-CONFLICT-004"]


def test_paraphrased_glosses_of_one_quantity_draw_no_glossary_warning():
    res, f = check_cross_report_consistency([_amp("s4.1", "period of the oscillation, in seconds", "0.63"), _amp("s8.2", "period of the original oscillation, in seconds", "0.63")],
                                            request_id="req-x", config=CFG)
    assert "INT-GLOSSARY-005" not in codes(f) and not conflicts(f)
    res, f = check_cross_report_consistency([_amp("s1", "speed in m/s", "3"), _amp("s2", "speed in km/h", "3")], request_id="req-x", config=CFG)
    [g] = [x for x in f if x.code == "INT-GLOSSARY-005"]
    assert "they name different quantities by units" in g.message


def _sym(cid: str, name: str, meaning: str, value: str) -> Problem:
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "consistency",
                                   "symbols": [{"name": name, "sort": "Real", "meaning": meaning}],
                                   "premises": [{"id": "pr", "expr": {"op": "eq", "left": {"op": "var", "name": name}, "right": {"op": "real", "value": value}}}]})


def test_a_symbol_read_apart_keeps_its_warning_beside_a_rounding_only_contradiction():
    """ph-p8b in the c1 replay: once the two glosses of 'period_s' were read as one period (rule same-gloss), the pool read
    apart held a contradiction that exists only at a precision neither claim states (0.63 against 0.628), so the
    glossary-only check of 'x0_cm' (glossed as two displacements) was skipped and its INT-CONFLICT-004 lost. The check now
    runs with the rounding-only claims read at their stated precision."""
    x0 = [_sym("s2.4", "x0_cm", "release displacement in centimetres, as the task gives it", "5.0"),
          _sym("s7.2", "x0_cm", "displacement of 2.0 cm, as the task gives it", "2.0")]
    period = [_sym("s4.1", "period_s", "period of the oscillation, in seconds", "0.63"),
              _sym("s8.2", "period_s", "period of the original oscillation, in seconds", "0.628")]
    res, f = check_cross_report_consistency(x0 + period, request_id="req-x", config=CFG)
    assert conflicts(f) == [("INT-CONFLICT-004", "warning", ["s2.4", "s7.2"])]
    [u] = [x for x in f if x.code == "INT-CONFLICT-004"]
    assert "'x0_cm'" in u.message and "precision" in u.message
    # the same without the rounding-only pair: the warning as before, with no precision note
    res, f = check_cross_report_consistency(x0, request_id="req-x", config=CFG)
    [u] = [x for x in f if x.code == "INT-CONFLICT-004"]
    assert conflicts(f) == [("INT-CONFLICT-004", "warning", ["s2.4", "s7.2"])] and "precision" not in u.message
    # controls: the rounding-only pair alone, or beside a symbol read apart that contradicts nothing, names no conflict
    assert not conflicts(check_cross_report_consistency(period, request_id="req-x", config=CFG)[1])
    same = [_sym("s2.4", "x0_cm", "release displacement in centimetres, as the task gives it", "2.0"), x0[1]]
    assert not conflicts(check_cross_report_consistency(same + period, request_id="req-x", config=CFG)[1])
    # a real contradiction of the period is still charged, whatever the symbol read apart does
    wrong = [period[0], _sym("s8.2", "period_s", "period of the original oscillation, in seconds", "0.70")]
    assert ("INT-CONFLICT-001", "error", ["s4.1", "s8.2"]) in conflicts(check_cross_report_consistency(x0 + wrong, request_id="req-x", config=CFG)[1])


# ----------------------------------------------------------------- critical: a rejected candidate value (rule candidate)


def _recorded(task: str, cid: str) -> Problem:
    return Problem.model_validate(C1["translations"][task][cid]["problem"])


def test_maa_t14_m6_1_and_m7_7_are_no_contradiction_charged_to_the_specialist():
    m61, m77 = _recorded("maa-t14", "m6.1"), _recorded("maa-t14", "m7.7")
    assert candidate_tests(m77) == {"x": "candidate"} and candidate_tests(m61) == {}
    res, f = check_cross_report_consistency([m61, m77], request_id="req-maa-t14", config=CFG)
    assert [c[:2] for c in conflicts(f)] == [("INT-CONFLICT-004", "warning")]
    [u] = [x for x in f if x.code == "INT-CONFLICT-004"]
    assert sorted(u.claim_ids) == ["m6.1", "m7.7"] and "rule candidate" in u.message and "'candidate'" in u.message
    renamed, info = rename_candidates_apart([m61, m77])
    assert renamed[0] is m61 and {s.name for s in renamed[1].symbols} == {"x_h1", "dom_h1"} and info == {"m7.7": [("x", "x_h1", "candidate")]}


def _rejected(value: str, *, label: str = "x = {v} is rejected because it does not satisfy x > 4", pid: str = "candidate",
              prem_label: str = "x = {v} is one of the candidate solutions", raw: bool = False) -> Problem:
    x = {"op": "var", "name": "x"}
    if not raw:
        label, prem_label = label.format(v=value), prem_label.format(v=value)
    return Problem.model_validate({
        "problem_id": "p-m7.7", "request_id": "req-x", "claim_id": "m7.7", "query": "entailment",
        "symbols": [{"name": "x", "sort": "Real", "meaning": "the unknown in the logarithmic equation"}, {"name": "dom", "sort": "Bool", "meaning": "x lies in the domain"}],
        "premises": [{"id": "domain-def", "expr": {"op": "iff", "left": {"op": "var", "name": "dom"}, "right": {"op": "gt", "left": x, "right": {"op": "real", "value": "4"}}}},
                     {"id": pid, "expr": {"op": "eq", "left": x, "right": {"op": "real", "value": value}}, "label": prem_label}],
        "conclusion": {"id": "claim", "expr": {"op": "and", "args": [{"op": "eq", "left": x, "right": {"op": "real", "value": value}}, {"op": "not", "arg": {"op": "var", "name": "dom"}}]},
                       "label": label}})


def _solution(cid: str, value: str, *, not_value: str | None = None) -> Problem:
    x = {"op": "var", "name": "x"}
    concl = {"op": "eq", "left": x, "right": {"op": "real", "value": value}}
    if not_value is not None:
        concl = {"op": "and", "args": [concl, {"op": "ne", "left": x, "right": {"op": "real", "value": not_value}}]}
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "entailment",
                                   "symbols": [{"name": "x", "sort": "Real", "meaning": "the unknown in the logarithmic equation"}],
                                   "premises": [{"id": "s", "expr": {"op": "eq", "left": x, "right": {"op": "real", "value": value}}, "label": f"the solution is x = {value}"}],
                                   "conclusion": {"id": "c", "expr": concl, "label": f"x = {value}" + (f", not {not_value} (the other root is rejected)" if not_value else "")}})


def test_the_candidate_rule_keeps_every_real_contradiction():
    m61 = _recorded("maa-t14", "m6.1")
    # a candidate the claim says fails the domain while it satisfies it refutes itself: still the specialist's error
    res, f = check_cross_report_consistency([m61, _rejected("5")], request_id="req-x", config=CFG)
    assert conflicts(f) == [("INT-CONFLICT-005", "error", ["m7.7"])]
    # the same encoding with no word of a tested or rejected value is an assertion about the unknown: INT-CONFLICT-001
    plain = _rejected("-5", label="x = {v} and x is outside", pid="value", prem_label="x is {v}")
    assert candidate_tests(plain) == {}
    res, f = check_cross_report_consistency([m61, plain], request_id="req-x", config=CFG)
    assert conflicts(f) == [("INT-CONFLICT-001", "error", ["m6.1", "m7.7"])]
    # "x = 7, not 5" corrects a value: it tests no candidate, and contradicts "x = 5"
    res, f = check_cross_report_consistency([_solution("m8.1", "5"), _solution("e8.1", "7", not_value="5")], request_id="req-x", config=CFG)
    assert conflicts(f) == [("INT-CONFLICT-001", "error", ["e8.1", "m8.1"])]
    # a solution that violates the domain stays a contradiction beside the rejected candidate
    res, f = check_cross_report_consistency([m61, _rejected("-5"), _solution("m8.1", "3")], request_id="req-x", config=CFG)
    assert ("INT-CONFLICT-001", "error", ["m6.1", "m8.1"]) in conflicts(f)


# ----------------------------------------------- major: "rather than", a reversed contrast, an exchanged term, a verdict


HI = "The war stayed limited because both sides are restrained rather than aimed at the total defeat of the enemy state."
LIT = 'The simile "as if she were setting a table" turns her farewell into a domestic ritual of control rather than defeat.'
PS = "Before the filling, the smell of the waiting room was a neutral stimulus that caused no fear."


@pytest.mark.parametrize("source,paraphrase", [
    (HI, HI.replace("are restrained rather than aimed at", "are restrained and not aimed at")),
    (LIT, LIT.replace("control rather than defeat", "control, not defeat")),
    (LIT, LIT.replace("control rather than defeat", "control instead of defeat")),
])
@pytest.mark.parametrize("transformation", ["carried", "paraphrased"])
def test_rather_than_and_not_state_one_polarity(source, paraphrase, transformation):
    assert L.meaning_inversions(paraphrase, [source], transformation) == []
    assert not [d for d in L.meaning_differences(paraphrase, [source], transformation) if "negation" in d]


def test_an_added_negation_of_the_source_is_still_int_ledger_030():
    assert L.meaning_inversions(PS.replace("caused no fear", "caused fear"), [PS.replace("caused no fear", "caused fear").replace("was a neutral", "was not a neutral")],
                                "carried") == []  # dropped: the warning's, never the error's
    [d] = L.meaning_inversions("The council did not ban the market.", ["The council banned the market."], "carried")
    assert "adds a negation" in d


def test_a_reversed_contrast_and_an_exchanged_term_are_named():
    [d] = L.meaning_differences(LIT.replace("control rather than defeat", "defeat rather than control"), [LIT], "paraphrased")
    assert "reverses the two sides of a comparison" in d
    [d] = L.meaning_differences(PS.replace("was a neutral stimulus", "was an unconditioned stimulus"), [PS], "paraphrased")
    assert "replaces 'neutral' with 'unconditioned'" in d
    # controls: a copied contrast and a copied statement draw nothing
    assert L.meaning_differences(LIT, [LIT], "carried") == [] and L.meaning_differences(PS, [PS], "carried") == []


@pytest.mark.parametrize("syn,src", [("V.", "F."), ("F.", "V."), ("Verdadero.", "Falso."), ("False: the text says fourteen.", "True: the text says fourteen."),
                                     ("F. El texto dice catorce.", "V. El texto dice catorce.")])
def test_a_flipped_true_false_verdict_is_an_error(syn, src):
    [d] = L.meaning_inversions(syn, [src], "carried")
    assert "reverses the true/false verdict" in d


@pytest.mark.parametrize("text", ["Vitamin F.", "f.", "True to form, the poem ends.", "Falsetto voices", "T. S. Eliot wrote it.", "V-shaped recovery."])
def test_a_letter_or_word_that_is_no_verdict_is_not_read_as_one(text):
    assert L.true_false_verdict(text) is None or text.startswith(("T.",))  # "T. S. Eliot": an initial, never compared below
    assert L.meaning_inversions(text, [text], "carried") == []


# ----------------------------------------------------------------------------- sweep: the readers this clearance added


def _entries(text: str):
    amp = _amp("s1", "amplitude in metres", "1")
    labelled = _rejected("-5", label=text[:1000], prem_label=text[:1000], raw=True)
    return [("gloss_reading", lambda: gloss_reading(text)), ("gloss_content", lambda: gloss_content(text)),
            ("gloss_difference", lambda: gloss_difference(text, "amplitude of the oscillation, in metres")),
            ("gloss_difference(both)", lambda: gloss_difference(text, text + " x")),
            ("candidate_tests", lambda: candidate_tests(labelled)), ("rename_candidates_apart", lambda: rename_candidates_apart([amp, labelled])),
            ("true_false_verdict", lambda: L.true_false_verdict(text)), ("soft negations", lambda: L._soft_negations(text)),
            ("text_outside_claims", lambda: L.text_outside_claims(text, [text[: len(text) // 2], "(2) Do B."]))]


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c1_integrity_readers(shape):
    assert not sweep(_entries, texts=one(shape))


def test_rather_than_in_the_synthesis_keeps_a_not_of_the_source():
    """B15c: "a loss rather than a reward" restates "a loss, not a reward"; dropping the contrast altogether is still named."""
    src = "For Morag the end of her work is a loss, not a reward, and she will not pretend otherwise."
    assert L.meaning_differences(src.replace("a loss, not a reward", "a loss rather than a reward"), [src], "paraphrased") == []
    [d] = L.meaning_differences(src.replace("a loss, not a reward", "a loss and a reward"), [src], "paraphrased")
    assert "drops the negation" in d
