"""Round-5 overseer regressions for the arithmetic extractor and the core pack: 'nearly'/'almost'
approach a stated fold, fraction or per cent from below and 'just over' from above; absolute
changes, average rates, multiples, comparisons with a stated benchmark, the direction of a from/to
pair and a decade superlative are decided or reported undecided (CORE-QNT-001); the report's own
formal checks name the delivered claim; a colleague's own words credited to the poet are CORE-SRC-005
whether or not the poem was supplied; a structured claim whose quotation disagrees with its source
reference is CORE-SRC-006; bracket-heavy answers cross the English branch quickly."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.branches.quant import extract_quant_checks, undecided_quant_statements
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

KEY = b"branches-r5-quant-key-0123456789ab"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)

HI_T9 = ("The Five-Year Plans transformed Soviet heavy industry to a large extent in scale and geography, but far less in efficiency and in the quality of its "
         "output. Between 1928 and 1932 official figures show pig iron rising from about 3.3 million tonnes to about 6.2 million, steel from about 4.3 million "
         "to 5.9 million and coal from about 35 million tonnes to about 64 million. These totals fell short of the First Plan's original target of about 10 "
         "million tonnes of pig iron, and later Western reassessments reduced the growth that the official series claimed, yet the expansion was real and it "
         "was directed by state investment rather than by market demand. The geography changed as well. Magnitogorsk, built on an iron-ore mountain in the "
         "southern Urals, lit its first blast furnace in 1932, and the Second Five-Year Plan of 1933 to 1937 pushed coal output to about 128 million tonnes by "
         "1937. Judged by the criterion of military and industrial capacity by 1941, the plans achieved a great deal; judged by efficiency, they achieved much "
         "less. Dates and figures are from memory; verify them against your notes before use.")
HI_T10 = ("Railway growth in Britain between 1830 and 1870 came in phases, and the 1840s gave the network its shape. The Liverpool and Manchester Railway "
          "opened in September 1830 over 31 miles, the first inter-city line worked by steam locomotives on a timetable. The network then grew from almost "
          "nothing: the London and Birmingham Railway opened in 1838, and the Great Western reached Bristol in 1841. Route mileage was about 1,500 by 1840 and "
          "about 6,000 by 1850 (from memory; check your notes). The 1840s, which included the Railway Mania of 1845 to 1847, added roughly 4,500 miles, more "
          "than any other decade of the period, and by 1848 a line ran from London through Carlisle to Glasgow. The 1850s and 1860s took the network to about "
          "13,000 miles by 1870, but largely through branches and extensions to an existing framework. The 1840s were the most decisive decade.")
EN_P4 = ('Hardy\'s dramatic monologue lets the speaker justify the killing in casual terms, and the casualness exposes a motive of poverty and a view of the '
         'enemy that his justification cannot sustain. The motive is presented through a colloquial parallel: "He thought he\'d \'list, perhaps, / Off-hand '
         'like—just as I— / Was out of work—had sold his traps—". The key word "traps", which conventionally denotes snares but in colloquial use means a '
         'man\'s gear and belongings, suggests a man who has sold his belongings for want of work, so poverty becomes the motive. Foe should supply a reason '
         'for killing, but it only restates the killing, so the justification becomes circular. The opening conditional, "Had he and I but met", imagines the '
         'man as a drinking companion.')
POEM_TEXT = ('"Had he and I but met\nBy some old ancient inn,\nWe should have sat us down to wet\nRight many a nipperkin!\n\n"He thought he\'d \'list, perhaps,\n'
             'Off-hand like—just as I—\nWas out of work—had sold his traps—\nNo other reason why.\n\n"Yes; quaint and curious war is!\nYou shoot a fellow down"')
POEM = SuppliedText(document_id="doc-mhk", title="The Man He Killed (poem, supplied text)", author="Thomas Hardy", text=POEM_TEXT)
PEER = SuppliedText(document_id="peer:en-p4", title="english-specialist report rep-en-p4-0 relayed through the hub", author="english-specialist", text=EN_P4)


def statuses(text: str) -> list[tuple[str, str]]:
    return [(c.kind, verify(c.problem, CFG).status.value) for c in extract_quant_checks(text, request_id="r", claim_id="c")]


def history(text: str, texts=()) -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="rep", task_type="short_answer", supplied_texts=list(texts))


def through_hub(text: str, question: str, *, subject: str = "History", agent: str = "history-specialist", texts=(), task_type: str = "short_answer"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type=task_type, selected_agent_ids=[agent, "dummy-combinator"],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", agent, question, list(texts))
    return hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-x")


# ------------------------------------------------------------------ 'nearly' / 'almost' / 'just over' bands


@pytest.mark.parametrize("sentence,expected", [
    ("The garrison rose from about 10,000 men in 1898 to about 31,000 men in 1899, nearly a tripling.", "COUNTEREXAMPLE"),          # x3.1 overshoots
    ("Cattle numbers fell from about 100 million head in 1928 to about 48 million head in 1933, a fall of nearly a half.", "COUNTEREXAMPLE"),  # 52 per cent
    ("Coal output rose from about 35 million tonnes in 1928 to about 64 million tonnes in 1932, nearly a doubling.", "ENTAILED"),   # x1.83
    ("Pig iron output rose from about 3.3 million tonnes in 1928 to about 6.2 million tonnes in 1932, almost a doubling.", "ENTAILED"),  # x1.88
    ("Cattle numbers fell from about 60 million head in 1928 to about 33 million head in 1933, a fall of nearly a half.", "ENTAILED"),  # 45 per cent
    ("The garrison rose from c. 10,000 men in c. 1898 to c. 27,000 men in c. 1899, nearly a tripling.", "ENTAILED"),                  # x2.7
    ("Pig iron output nearly doubled from about 3.3 million tonnes in 1928 to about 6.2 million in 1932.", "ENTAILED"),
    ("Pig iron output almost doubled from about 3.3 million tonnes in 1928 to about 4.3 million in 1932.", "COUNTEREXAMPLE"),        # x1.3
    ("Pig iron output nearly doubled from about 3.3 million tonnes in 1928 to about 6.9 million in 1932.", "COUNTEREXAMPLE"),        # x2.1
    ("Output rose from 100 in 1928 to 151 in 1932, a rise of just over 50 per cent.", "ENTAILED"),
    ("Output rose from 100 in 1928 to 140 in 1932, a rise of just over 50 per cent.", "COUNTEREXAMPLE"),
    ("Output rose from 100 in 1928 to 149 in 1932, a rise of nearly 50 per cent.", "ENTAILED"),
    ("Output rose from 100 in 1928 to 153 in 1932, a rise of nearly 50 per cent.", "COUNTEREXAMPLE"),
])
def test_approach_qualifiers_bound_the_stated_figure_from_one_side(sentence, expected):
    [(_kind, status)] = statuses(sentence)
    assert status == expected, sentence
    [check] = extract_quant_checks(sentence, request_id="r", claim_id="c")
    assert "approached from" in check.rule


# ------------------------------------------------------------------ absolute changes, rates, multiples


def test_the_genuine_hi_t10_absolute_change_is_decided_and_its_superlative_is_reported_undecided():
    assert ("abs_change", "ENTAILED") in statuses(HI_T10)
    [u] = [u for u in undecided_quant_statements(HI_T10) if "any other decade" in u.phrase]
    assert "1850s" in u.reason and "1860s" in u.reason
    found = [f for f in CorePack().checks(history(HI_T10)) if f.code == "CORE-QNT-001"]
    assert found and found[0].claim_ids == ["h1.5"]


@pytest.mark.parametrize("old,new,kind", [
    ("added roughly 4,500 miles", "added roughly 6,500 miles", "abs_change"),
    ("Route mileage was about 1,500 by 1840 and about 6,000 by 1850", "Route mileage rose from about 1,500 miles in 1840 to about 6,000 miles in 1850, an increase of about 6,500 miles", "abs_change"),
    ("Route mileage was about 1,500 by 1840 and about 6,000 by 1850", "Route mileage grew from about 1,500 miles in 1840 to about 6,000 miles in 1850, adding roughly 2,000 miles", "abs_change"),
    ("Route mileage was about 1,500 by 1840 and about 6,000 by 1850", "Route mileage rose from about 1,500 miles in 1840 to about 6,000 miles in 1850, an average of 900 miles a year", "rate_change"),
    ("Route mileage was about 1,500 by 1840 and about 6,000 by 1850", "Route mileage rose from about 1,500 miles in 1840 to about 6,000 miles in 1850, six times its earlier length", "fold_change"),
])
def test_false_absolute_changes_rates_and_multiples_are_counterexamples(old, new, kind):
    text = HI_T10.replace(old, new)
    assert text != HI_T10
    assert (kind, "COUNTEREXAMPLE") in statuses(text)


def test_correct_rates_and_multiples_hold():
    text = HI_T10.replace("Route mileage was about 1,500 by 1840 and about 6,000 by 1850",
                          "Route mileage rose from about 1,500 miles in 1840 to about 6,000 miles in 1850, an average of 450 miles a year, four times its earlier length")
    got = statuses(text)
    assert ("rate_change", "ENTAILED") in got and ("fold_change", "ENTAILED") in got and not [s for _k, s in got if s != "ENTAILED"]


def test_a_decade_superlative_is_refuted_when_another_decade_added_more():
    for text in (HI_T10.replace("The 1850s and 1860s took the network to about 13,000 miles by 1870",
                                "The 1850s took the network to about 11,000 miles by 1860 and the 1860s to about 13,000 miles by 1870"),
                 HI_T10.replace("The 1850s and 1860s took the network to about 13,000 miles by 1870, but largely through branches and extensions to an existing framework.",
                                "Route mileage reached about 13,000 in 1860 and about 15,500 in 1870, so the 1850s added about 7,000 miles (from memory).")):
        got = statuses(text)
        assert ("series_extreme", "COUNTEREXAMPLE") in got, got
        assert not [u for u in undecided_quant_statements(text) if "any other decade" in u.phrase]
    # 'fewer than any other decade' with the genuine figures is undecided, not silent
    fewer = HI_T10.replace("more than any other decade", "fewer than any other decade")
    assert [u for u in undecided_quant_statements(fewer) if "fewer than any other decade" in u.phrase]
    # the 1850s are read through the decade, not the 1860-1870 pair stated beside them
    rerouted = HI_T10.replace("The 1850s and 1860s took the network to about 13,000 miles by 1870, but largely through branches and extensions to an existing framework.",
                              "Route mileage reached about 13,000 in 1860 and about 15,500 in 1870, so the 1850s added about 7,000 miles (from memory).")
    abs_checks = [c for c in extract_quant_checks(rerouted, request_id="r", claim_id="c") if c.kind == "abs_change" and "7,000" in c.phrase]
    assert abs_checks and verify(abs_checks[0].problem, CFG).status.value == "ENTAILED" and "1850 to 1860" in abs_checks[0].basis


# ------------------------------------------------------------------ comparisons with a stated benchmark and the direction of a pair


def test_the_genuine_hi_t9_comparison_and_directions_hold():
    got = statuses(HI_T9)
    assert got.count(("pair_direction", "ENTAILED")) == 3 and ("comparison", "ENTAILED") in got
    assert not [s for _k, s in got if s != "ENTAILED"]
    [cmp] = [c for c in extract_quant_checks(HI_T9, request_id="r", claim_id="c") if c.kind == "comparison"]
    assert "6.2 million" in cmp.problem.premises[0].label and "pig iron" in cmp.problem.conclusion.label


@pytest.mark.parametrize("old,new,kind", [
    ("about 10 million tonnes of pig iron", "about 5 million tonnes of pig iron", "comparison"),
    ("fell short of the First Plan's original target of about 10 million tonnes of pig iron", "exceeded the First Plan's original target of about 5 million tonnes of pig iron by half", "comparison"),
    ("about 10 million tonnes of pig iron", "about 10 million tonnes of pig iron by about 10 per cent", "comparison"),
    ("pig iron rising from about 3.3 million tonnes to about 6.2 million", "pig iron rising from about 6.2 million tonnes to about 3.3 million", "pair_direction"),
])
def test_false_comparisons_and_directions_are_counterexamples(old, new, kind):
    text = HI_T9.replace(old, new)
    assert text != HI_T9
    assert (kind, "COUNTEREXAMPLE") in statuses(text)


def test_a_comparison_whose_compared_figure_cannot_be_read_is_undecided():
    text = "The plans were ambitious. Output fell short of the First Plan's target of about 10 million tonnes of pig iron."
    [u] = undecided_quant_statements(text)
    assert "fell short of" in u.phrase and "not stated" in u.reason
    assert not undecided_quant_statements("British deaths exceeded 22,000 in the war.")  # a plain stated quantity is not a comparison of two figures


# ------------------------------------------------------------------ the report's own checks name the delivered claim


def test_formal_checks_and_their_findings_name_the_claim():
    text = HI_T10.replace("added roughly 4,500 miles", "added roughly 6,500 miles")
    rep = history(text)
    checks = CorePack().formal_checks(rep)
    abs_check = next(fc for fc in checks if fc.kind == "abs_change")
    assert abs_check.claim_ids == ("h1.5",)
    rc = through_hub(text, "Outline the growth of the railway network in Britain between 1830 and 1870.")[1]
    errors = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert errors and errors[0].claim_ids == ["h1.5"] and "6,500" in errors[0].message


def test_a_long_unpunctuated_block_names_the_claim_holding_the_false_phrase():
    bullets = "\n".join(f"- point {i} about the economy of the period and its many difficulties" for i in range(40))
    text = bullets + "\n- output rose from 100 in 1929 to 120 in 1930, a rise of 50 per cent"
    rep = history(text)
    [fc] = [fc for fc in CorePack().formal_checks(rep) if fc.kind == "percent_change"]
    holder = [c.claim_id for c in rep.claims if "a rise of 50 per cent" in c.claim_text]
    assert fc.claim_ids and set(fc.claim_ids) <= set(holder)
    assert "a rise of 50 per cent" in fc.description


# ------------------------------------------------------------------ a colleague's words credited to the poet


@pytest.mark.parametrize("sentence,excerpt", [
    ('Hardy\'s speaker himself admits that his justification "becomes circular".', "becomes circular"),
    ('Hardy\'s poem identifies the speaker\'s motive as poverty: the casualness "exposes a motive of poverty", and the key word "traps" suggests a man who '
     '"sold his belongings for want of work".', "exposes a motive of poverty"),
])
@pytest.mark.parametrize("texts", [[PEER], [POEM, PEER]], ids=["peer-only", "poem-and-peer"])
def test_a_colleagues_words_credited_to_the_poet_are_core_src_005(sentence, excerpt, texts):
    rep = history("The Second Boer War ran from 11 October 1899 to 31 May 1902 (from memory). " + sentence, texts)
    found = [f for f in CorePack().checks(rep) if f.code == "CORE-SRC-005" and excerpt in f.message]
    assert found and found[0].severity == "error" and "peer:en-p4" in found[0].message, [(f.code, f.message[:160]) for f in CorePack().checks(rep)]
    assert found[0].claim_ids == ["h1.2"]


def test_the_poets_words_quoted_by_the_colleague_and_the_colleagues_credited_words_are_no_finding():
    for sentence in ('Hardy\'s speaker says he "had sold his traps".',                      # the poem's words, quoted by the colleague
                     'The English specialist argues that the justification "becomes circular".',  # the colleague's words, credited to the colleague
                     'The English specialist notes that Hardy\'s speaker "becomes circular" in his reasoning.'):  # the outer speaker is credited
        for texts in ([PEER], [POEM, PEER]):
            rep = history("The war ran from 11 October 1899 to 31 May 1902. " + sentence, texts)
            assert not [f for f in CorePack().checks(rep) if f.code == "CORE-SRC-005"], (sentence, [f.message for f in CorePack().checks(rep) if f.code == "CORE-SRC-005"])


# ------------------------------------------------------------------ a structured claim whose quotation disagrees with its reference


def _structured(alter: bool) -> SpecialistReport:
    from epinoic_logic.adapters.english_specialist.parser import parse_response
    good = parse_response(EN_P4, request_id="r", task_id="t", report_id="rep-en", subject="English A: Literature", task_type="analytical_paragraph",
                          supplied_texts=[POEM], agent_id="english-specialist")
    data = good.model_dump(mode="json", exclude_none=True)
    if alter:
        text = EN_P4.replace('"Had he and I but met"', '"Had we two but met"')
        data["original_response"], data["response_sha256"] = text, sha256_text(text)
        data["claims"] = [{**c, "claim_text": c["claim_text"].replace('"Had he and I but met"', '"Had we two but met"')} for c in data["claims"]]
    return SpecialistReport.model_validate(data)


def test_a_structured_claim_quoting_words_its_reference_does_not_carry_is_core_src_006():
    assert not [f for f in CorePack().checks(_structured(False)) if f.code in ("CORE-SRC-006", "CORE-SRC-003")]
    altered = _structured(True)
    [found] = [f for f in CorePack().checks(altered) if f.code == "CORE-SRC-006"]
    holders = [c.claim_id for c in altered.claims if "Had we two but met" in c.claim_text]
    assert found.severity == "error" and set(found.claim_ids) == set(holders) and "Had he and I but met" in found.message
    assert not [f for f in CorePack().checks(altered) if f.code == "CORE-SRC-003"]  # never 'credited to none of the supplied texts'
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="English A: Literature", task_type="analytical_paragraph",
                           selected_agent_ids=["english-specialist", "dummy-combinator"], allowed_document_ids=["doc-mhk"]))
    m, _, _ = hub.dispatch("t", "english-specialist", "Write one analytical paragraph on the speaker's motive. Quote exactly from the poem.", [POEM])
    _reply, rc = hub.receive("t", m.message_id, altered)
    errors = [f for f in rc.findings if f.code == "INT-SUBJ-003" and "CORE-SRC-006" in f.message]
    assert errors and set(errors[0].claim_ids) == set(holders)


# ------------------------------------------------------------------ bracket-heavy answers on the English branch


@pytest.mark.parametrize("text", [
    "{" * 5000 + ' The son "Beware the Jabberwock, my son!" ' + "}" * 5000,
    "The son quests heroically. " + "[" * 20000 + "]" * 20000,
    " ".join('{"a": 1, "b": [' for _ in range(2000)) + " The turning point was 1930.",
], ids=["5000-nested-braces", "20000-deep-array", "2000-unclosed-fragments"])
def test_bracket_heavy_answers_cross_the_english_branch_quickly(text):
    # round 5 measured 13.3 s, 172.7 s and 23.7 s for these on the English branch; each now takes well under a second
    t0 = time.perf_counter()
    _reply, rc = through_hub(text, "Write one analytical paragraph on the son's quest. Quote exactly from the poem.", subject="English A: Literature",
                             agent="english-specialist", texts=[POEM], task_type="analytical_paragraph")
    assert time.perf_counter() - t0 < 2.0 and rc.status is not None
