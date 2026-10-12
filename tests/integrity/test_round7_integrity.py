"""Integrity behaviour found wanting by the round-7 arena overseers, on the round-7 material.

* A superscript or subscript digit ("min⁻¹", "10³", "(1/2)⁴", "CO₂") made the ledger's figure readers raise ValueError
  (``str.isdigit`` is true for it, ``int`` refuses it); numerals are now read in decimal digits only and the marks are
  folded away as exponents or indices.
* One symbol name for two quantities (the targets 67 and 20, the marks of part (a) and part (c)) made correct claims look
  contradictory: the consistency check now reads such symbols apart, and a contradiction that exists only when they are
  pooled is INT-CONFLICT-004 (warning), never INT-CONFLICT-001. A part label is content of a gloss.
* The figure-pairing reader paired the operands of an equation, the members of an arrow chain and a figure with the next
  line's year; it now reads calculations as calculations, while real swaps stay named.
* Number words in another language, quotation marks, inflections and "rather than" were read as changes; reversals at the
  start of a copied sentence, a passive comparison, a true/false flip, a dropped hedge and a swapped series were missed.

The synthesized claims and the texts of their cited sources are the r7 recording (tests/integrity/data/r7_syntheses.json:
each synthesis of the round with its sources as the round's parser delivered them)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity.cross_check import check_cross_report_consistency, gloss_content, split_by_gloss
from epinoic_logic.integrity.ledger import (
    _figure_differences, _figure_kind, aligned_differences, check_synthesis_ledger, credited_date_repairings, figure_pairing_differences,
    fold_exponent_marks, foreign_number_values, incidental_figures, meaning_differences, quotation_form_differences, unlocated_quotations,
)
from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

DATA = Path(__file__).parent / "data"
SYN = json.loads((DATA / "r7_syntheses.json").read_text())
TRANSLATIONS = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_translations.json").read_text())
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def synthesized(group: str, claim_id: str) -> tuple[str, list[str], str]:
    sc = next(s for s in SYN[group] if s["claim_id"] == claim_id)
    return sc["text"], [t for t in sc["sources"].values() if t], sc["transformation"]


def problems(task: str, *claim_ids: str) -> list[Problem]:
    return [Problem.model_validate(TRANSLATIONS[task]["claims"][c]["problem"]) for c in claim_ids]


def codes(findings) -> list[str]:
    return [f.code for f in findings]


# ------------------------------------------------------------------ blocker: superscripts never raise


SUPERSCRIPT_TEXTS = [
    "The rate is 1.5 × 10³ per hour.", "The value is 2⁵ = 32.", "Nitrate was 8.4 mg dm⁻³ at site B in 2021.",
    "C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹ in 1990.", "CO₂ rose to 420 ppm by 2023.", "① The first point, in 1949.",
    "The Physics specialist's corrected rate at t = 0 h is 1600 counts per minute; its data give 1620 − 20 = 1600 counts min⁻¹.",
]


@pytest.mark.parametrize("text", SUPERSCRIPT_TEXTS)
def test_superscript_and_subscript_digits_never_raise_in_any_figure_reader(text):
    other = "In 1990 the rate was 1600 counts min⁻¹, 8.4 mg dm⁻³ and 10³ units; CO₂ stood at 400 ppm; ② 2⁵ = 32."
    figure_pairing_differences(text, [other])
    figure_pairing_differences(other, [text])
    credited_date_repairings(text, other)
    aligned_differences(text, [other])
    meaning_differences(text, [other], "merged")
    _figure_differences(text, [other])
    assert "¹" not in fold_exponent_marks("min⁻¹") and fold_exponent_marks("10³") == "10"


def test_a_superscript_is_no_figure_and_never_a_day_of_a_month():
    assert _figure_kind(["counts", "min", "¹", "May"], 2) == "quantity"
    assert figure_pairing_differences("The rate fell to 1600 counts min⁻¹ in 1990.", ["The rate fell to 1600 counts min⁻¹ in 1990."]) == []


def test_a_synthesis_with_superscripts_gets_a_ledger_and_no_exception():
    report = _report("rep-1", "physics-specialist", [("g1", "The count rate fell to 1600 counts min⁻¹, and nitrate was 8.4 mg dm⁻³ (10³ litres).")])
    synthesis = _synthesis(["rep-1"], [("s0", "The count rate fell to 1600 counts min⁻¹ with nitrate at 8.4 mg dm⁻³ (10³ litres); 2⁵ = 32 and (1/2)⁴ = 1/16.", ["g1"], "paraphrased")])
    findings = check_synthesis_ledger([report], synthesis)
    assert "INT-INTERNAL-001" not in codes(findings)


# ------------------------------------------------------------------ one symbol, two quantities (INT-CONFLICT-001 -> 004)


def test_part_labels_are_content_of_a_gloss():
    assert gloss_content("marks allocated to part (a) of the question") != gloss_content("marks allocated to part (c) of the question")
    assert gloss_content("marks for part (b)") == gloss_content("marks for part b")
    assert gloss_content("route mileage in 1870 (about 13,000)") == gloss_content("route mileage by 1870 (about 13,000)")  # r5 rule kept


@pytest.mark.parametrize("task,claims,symbol", [
    ("ph-t13", ("g1.1", "g3.1"), "marks"),
    ("ph-p7b", ("g1.1", "g4.1"), "marks"),
    ("cs-t13", ("g3.1", "g4.1", "g7.1", "g7.2", "g9.1", "g9.5", "g11.1", "g11.2"), "tgt"),
])
def test_the_r7_glossary_conflations_are_no_contradiction_charged_to_the_specialist(task, claims, symbol):
    res, f = check_cross_report_consistency(problems(task, *claims), request_id="req-x", config=CFG)
    assert res is not None
    assert "INT-CONFLICT-001" not in codes(f), [x.message for x in f if x.code == "INT-CONFLICT-001"]
    [unattributable] = [x for x in f if x.code == "INT-CONFLICT-004"]
    assert unattributable.severity == "warning" and f"'{symbol}'" in unattributable.message and "no contradiction is charged" in unattributable.message
    assert any(x.code == "INT-GLOSSARY-005" and "reads them as different quantities" in x.message for x in f)


def _prob(cid: str, symbol: str, meaning: str, value: str, *, extra: list = ()) -> Problem:
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "consistency",
                                   "symbols": [{"name": symbol, "sort": "Int", "meaning": meaning}, *extra],
                                   "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": symbol}, "right": {"op": "int", "value": value}}}]})


def test_a_contradiction_over_one_quantity_glossed_alike_stays_int_conflict_001():
    res, f = check_cross_report_consistency([_prob("h1", "closed_day", "day of August 1961 the sector border was closed", "13"),
                                             _prob("e1", "closed_day", "day of August 1961 the sector border closed", "12")], request_id="req-x", config=CFG)
    assert [x.code for x in f if x.code.startswith("INT-CONFLICT")] == ["INT-CONFLICT-001"]
    split, splits = split_by_gloss([_prob("a", "marks", "marks for part (a)", "2"), _prob("c", "marks", "marks for part (c)", "1"), _prob("a2", "marks", "marks for part (a)", "2")])
    assert [p.symbols[0].name for p in split] == ["marks", "marks_g2", "marks"] and [ids for _n, ids, _g in splits["marks"]] == [["a", "a2"], ["c"]]


def test_quantities_computed_with_a_differently_glossed_symbol_are_read_apart_too():
    # 'low on pass 1' is glossed alike in both traces, but each trace computes it from its own target
    def trace(cid, target, low):
        return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "consistency",
                                       "symbols": [{"name": "tgt", "sort": "Int", "meaning": f"the target is {target}"}, {"name": "lo1", "sort": "Int", "meaning": "low on pass 1"}],
                                       "premises": [{"id": "T", "expr": {"op": "eq", "left": {"op": "var", "name": "tgt"}, "right": {"op": "int", "value": target}}},
                                                    {"id": "L", "expr": {"op": "eq", "left": {"op": "var", "name": "lo1"}, "right": {"op": "add", "args": [{"op": "var", "name": "tgt"}, {"op": "int", "value": "0"}]}}},
                                                    {"id": "V", "expr": {"op": "eq", "left": {"op": "var", "name": "lo1"}, "right": {"op": "int", "value": low}}}]})
    res, f = check_cross_report_consistency([trace("g3.1", "67", "67"), trace("g7.1", "20", "20")], request_id="req-x", config=CFG)
    assert "INT-CONFLICT-001" not in codes(f) and "INT-CONFLICT-004" in codes(f)


# ------------------------------------------------------------------ figure pairing on worked answers (INT-LEDGER-023)


@pytest.mark.parametrize("group,claim_id", [("bm-t13", "s0"), ("ec-t13", "s0"), ("mai-t13", "s0"), ("cs-t13", "s1"), ("p7a", "bm-p7a-s0"),
                                            ("maa-t13", "s1"), ("ph-t13", "s2"), ("p7b", "maa-p7b-s3")])
def test_faithful_syntheses_of_worked_answers_re_pair_nothing(group, claim_id):
    text, sources, _t = synthesized(group, claim_id)
    assert figure_pairing_differences(text, sources) == []


def test_every_r7_synthesis_is_read_without_a_false_re_pairing_or_meaning_change():
    flagged = []
    for group, scs in SYN.items():
        for sc in scs:
            sources = [t for t in sc["sources"].values() if t]
            if figure_pairing_differences(sc["text"], sources) or meaning_differences(sc["text"], sources, sc["transformation"]) or aligned_differences(sc["text"], sources)[0]:
                flagged.append((group, sc["claim_id"]))
    assert flagged == []


BM_SOURCES = ["Break-even quantity = fixed costs ÷ contribution per loaf\n= $6,000 ÷ $2.00 = 3,000 loaves per month",
              "Margin of safety = current output − break-even quantity\n= 4,200 − 3,000 = 1,200 loaves per month\nAs a percentage of current output: 1,200 ÷ 4,200 × 100 = 28.57%"]


def test_real_swaps_stay_named():
    swapped = figure_pairing_differences("Break-even is 1,200 loaves per month, so current output of 4,200 loaves gives a margin of safety of 3,000 loaves.", BM_SOURCES)
    assert len(swapped) == 1 and "break-even" in swapped[0] and "margin" in swapped[0] and "(exchanged)" in swapped[0]
    acerbo = ["The Acerbo Law of November 1923 gave two-thirds of the seats to the list with the most votes.", "In the election of 6 April 1924, held under that law, the Fascist list won."]
    assert figure_pairing_differences("The Acerbo Law of 1924 gave two-thirds of the seats to the list with the most votes, and in the election of 1923 the Fascist list won.", acerbo)


def test_a_figure_on_one_line_is_not_dated_by_the_next_line():
    text, sources, _t = synthesized("ec-t13", "s0")
    assert "Value in 2022 = 1 ÷ 8.40 = US$0.1190 per krona\nValue in 2025" in sources[-1]
    assert figure_pairing_differences(text, sources) == []
    assert figure_pairing_differences("One krona was worth US$0.1190 in 2025 and US$0.1429 in 2022.", sources)  # the dates exchanged are named


def test_two_series_exchanged_and_a_moved_data_interval_are_named():
    rates = ["The crude death rate in Country X fell from 11 to 7 per 1,000 between 1990 and 2020.",
             "This helped to lower the crude birth rate, which fell from 31 to 16 per 1,000 over the same period."]
    swapped = figure_pairing_differences("The crude death rate fell from 31 to 16 per 1,000 and the crude birth rate fell from 11 to 7 per 1,000 between 1990 and 2020.", rates)
    assert swapped and all("(exchanged)" in d for d in swapped) and any("'death'" in d and "'birth'" in d for d in swapped)
    assert figure_pairing_differences("The crude death rate fell from 11 to 7 per 1,000 and the crude birth rate fell from 31 to 16 per 1,000 between 1990 and 2020.", rates) == []
    uptake = ["The rise is steepest between 25 °C and 30 °C, an increase of 22 mm³ per g per hour, and slows between 30 °C and 35 °C, an increase of 12 mm³ per g per hour."]
    moved = figure_pairing_differences("The rise is steepest between 30 °C and 35 °C, by 12 mm³ per g per hour.", uptake)
    assert len(moved) == 1 and "'between 30 and 35'" in moved[0] and "steepest" in moved[0] and "re-paired" in moved[0]
    assert figure_pairing_differences("The rise is steepest between 25 °C and 30 °C and slows between 30 °C and 35 °C.", uptake) == []


def test_a_number_word_of_the_source_language_is_no_introduced_figure():
    text, sources, _t = synthesized("sp-t13", "s1")
    assert "twelve" in text and any("doce" in s for s in sources)
    introduced, _dropped, _rescaled = _figure_differences(text, sources)
    assert introduced == []
    assert _figure_differences(text.replace("twelve", "thirteen"), sources)[0] == ["thirteen"]
    assert foreign_number_values("En 2020 reunió a doce vecinos; douze; zwölf; dodici") == {"12"}


def test_formula_constants_part_numbers_and_mark_annotations_are_no_dropped_content():
    assert incidental_figures("As a percentage of current output: 1,200 ÷ 4,200 × 100 = 28.57%") == {"100"}
    assert incidental_figures("Paragraph 1 reports a rise; paragraph 2 explains it [1]") == {"1", "2"}
    assert incidental_figures("100 firms reported; the share is x × 100") == set()  # stated as content elsewhere


# ------------------------------------------------------------------ quotations (INT-LEDGER-025 / 010 / 028)


LL = 'The answer rests on a precise figure, "removes 99.9% of bacteria", but the casual comparison "in the time it takes to say \'cheers\'" makes that measurement feel effortless.'


def test_a_quotation_differing_only_in_its_inner_marks_is_located():
    assert unlocated_quotations('The comparison "in the time it takes to say cheers" makes it effortless.', [LL]) == []
    assert unlocated_quotations('The comparison "in the time it takes to say hello" makes it effortless.', [LL]) == ["in the time it takes to say hello"]


def test_a_carried_claim_that_only_changes_its_mark_style_is_no_change():
    src = 'The closing claim that "the best memories shouldn\'t come with a warning label" is ironic.'
    report = _report("rep-1", "english-specialist", [("p1-s10", src)])
    synthesis = _synthesis(["rep-1"], [("s3", src.replace('"', "'"), ["p1-s10"], "carried")])
    assert "INT-LEDGER-010" not in codes(check_synthesis_ledger([report], synthesis))
    synthesis2 = _synthesis(["rep-1"], [("s3", src.replace("ironic", "sincere"), ["p1-s10"], "carried")])
    assert "INT-LEDGER-010" in codes(check_synthesis_ledger([report], synthesis2))


def test_a_quotation_with_other_diacritics_is_int_ledger_028():
    corpus = ["Muchas personas mayores que, en muchos casos, vivían solas, ahora cultivan juntas."]
    assert quotation_form_differences('The article says they «vivian solas».', corpus) and quotation_form_differences('They «vivían solas».', corpus) == []


# ------------------------------------------------------------------ what a paraphrase says (INT-LEDGER-026)


HI = ("Benito Mussolini consolidated his power between 1922 and 1929 largely through legal and constitutional means, but those means worked "
      "because they rested on the violence that had brought him to power. Legal means did most of the consolidating after 1925, but violence "
      "had already shaped the terms on which they worked.")


def test_reversals_in_a_merged_claim_are_named_at_the_start_of_a_copied_sentence_and_for_a_span_of_three_words():
    found = meaning_differences(HI.replace("Legal means did most", "Violent means did most"), [HI], "merged")
    assert any("'Violent means did' where its cited sources state 'Legal means did'" in d for d in found)
    found = meaning_differences(HI.replace("legal and constitutional means", "violent means"), [HI], "merged")
    assert any("lawful or violent means" in d and "legal and constitutional means" in d for d in found)
    assert meaning_differences(HI, [HI], "merged") == []


@pytest.mark.parametrize("group,claim_id", [("sp-t13", "s3"), ("p7c", "hi-p7c-s0"), ("lit-t13", "s0")])
def test_rather_than_and_inflections_are_no_change(group, claim_id):
    text, sources, transformation = synthesized(group, claim_id)
    assert meaning_differences(text, sources, transformation) == []


def test_rather_than_keeps_the_polarity_of_not_and_a_dropped_not_is_still_named():
    assert meaning_differences("the wall answered pressure built over that time rather than a sudden act", ["the wall answered pressure built over that time, not a sudden act"], "merged") == []
    assert meaning_differences("the wall answered pressure built over that time and a sudden act", ["the wall answered pressure built over that time, not a sudden act"], "merged")


def test_a_passive_comparison_a_true_false_flip_a_length_at_a_sentence_start_and_a_dropped_hedge_are_named():
    assert any("passive" in d for d in meaning_differences("The ratio is 44.9, so working-age people are outnumbered by dependants.", ["The ratio is below 100, so working-age people outnumber dependants."], "merged"))
    assert any("true/false" in d for d in meaning_differences("Item b is false (F): the older people lived alone.", ["Item b is true (V): the older people lived alone."], "merged"))
    en = "The poet presents the reluctance as a division. Short sentences carry the practical work of clearing, while enjambment keeps the compulsion open past the point."
    assert any("a length" in d for d in meaning_differences("Long sentences carry the practical work of clearing, while enjambment keeps the compulsion open.", [en], "merged"))
    ge = ("Couples therefore chose smaller families and used contraception more widely, so births fell. The table does not measure education, "
          "urbanisation or contraception use, so this reason is a suggested process rather than one the data show.")
    hedged = meaning_differences("Couples chose smaller families and used contraception more widely, so births fell; the data show this process of education and urbanisation.", [ge], "merged")
    assert any("drops the hedge" in d and "suggested" in d for d in hedged)
    assert not any("hedge" in d for d in meaning_differences("Couples chose smaller families, so births fell; this reason is a suggested process of education and urbanisation, not one the data show.", [ge], "merged"))
    hp = "The closure therefore dealt with the exit rather than the reasons people left, and the flow fell sharply once the route was sealed."
    assert meaning_differences(hp.replace("fell sharply", "rose sharply"), [hp], "carried")


def test_a_comparison_of_a_change_and_one_of_a_level_agree():
    src = ["Decomposition continues as the water flows, so the fall in dissolved oxygen is greatest at C (2.0 km), where it reaches 3.8 mg dm⁻³."]
    assert meaning_differences("Dissolved oxygen is lowest at C (2.0 km), where it reaches 3.8 mg dm⁻³.", src, "merged") == []


# ------------------------------------------------------------------ helpers


def _report(rid: str, agent: str, claims: list[tuple[str, str]]) -> SpecialistReport:
    text = " ".join(t for _c, t in claims)
    base = dict(request_id="req-x", task_id="t-x", report_id=rid, agent_id=agent, subject="History", task_type="short_answer")
    return SpecialistReport(**base, original_response=text, response_sha256=sha256_text(text), created_at="2026-10-11T10:00:00Z",
                            claims=[ClaimRecord(**base, claim_id=c, claim_text=t, claim_role="point", materiality="material") for c, t in claims])


def _synthesis(sources: list[str], claims: list[tuple[str, str, list[str], str]]) -> Synthesis:
    sc = [SynthesizedClaim(claim_id=c, text=t, certainty="established", source_claim_ids=s, transformation=tr) for c, t, s, tr in claims]
    text = " ".join(c.text for c in sc)
    return Synthesis(synthesis_id="syn-x", request_id="req-x", task_id="t-x", combinator_agent_id="comb", source_report_ids=sources, claims=sc, ledger=[],
                     text=text, text_sha256=sha256_text(text), created_at="2026-10-11T11:00:00Z")
