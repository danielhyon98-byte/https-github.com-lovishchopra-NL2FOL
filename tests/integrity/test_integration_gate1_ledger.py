"""Integration gate, round 1: the synthesis ledger's findings (combinator faults and parser safety).

* A figure of thousands of digits made ``figure_pairing_differences`` raise (``int()`` over Python's 4,300-digit limit), so
  every INT-LEDGER finding of that synthesis was lost.
* ``dropped_hedges`` returned nothing as soon as any hedge occurred anywhere in the synthesis: a hedge kept in one sentence
  masked one dropped in another.
* A figure grouped with a space, a thin or no-break space or LaTeX's thin space ("3 000", "1 512 000", "21\\,131.40") was
  read as separate figures, so a correct synthesis was charged an introduced figure.
* Figure pairing read partners across the join of merged sources: a verbatim merge of two table rows was an "exchange".
* ``substituted_names`` took a determiner as the act slot, so a synthesis crediting its own specialist ("The History
  specialist argues ...") was charged a substituted actor.
* A specialist's own unquoted view credited to the supplied table ("The table shows that ...") was not named.
* A merged claim aligned against each cited source on its own read the words of one source as an edit of another.
"""
from __future__ import annotations

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity import ledger as L
from epinoic_logic.integrity.ledger import check_synthesis_ledger
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from ..timing import measure


# ============================================================================================ huge figures (parser-safety-14)
HUGE = {
    "huge_int": "In 1990 the total was " + "9" * 4301 + " people.",
    "huge_exp": "The value was 1e" + "9" * 5000 + " units.",
    "huge_exp_neg": "The value was 1e-" + "9" * 5000 + " units.",
    "unit_power": "The area was " + "9" * 5000 + " m² in 1990.",
    "based_bin": "The register held 0b" + "1" * 5000 + " in 1990.",
    "words_after": "It cost " + "9" * 4400 + " thousand marks in 1923.",
}
CONTROL = "In 1990 the total was 5 people."


@pytest.mark.parametrize("name", list(HUGE))
@pytest.mark.parametrize("position", ["synthesis", "source"])
def test_an_overlong_figure_never_makes_the_pairing_reader_raise(name, position):
    syn, src = (HUGE[name], CONTROL) if position == "synthesis" else (CONTROL, HUGE[name])
    timing = measure(lambda: L.figure_pairing_differences(syn, [src]), bound=1.0, repeat=3, label=f"pairing, {name} in the {position}")
    assert timing.holds, timing
    assert all(isinstance(r, list) for r in timing.results)


def test_the_other_ledger_checks_still_run_beside_an_overlong_figure():
    assert L.figure_pairing_differences(CONTROL, [CONTROL]) == []
    introduced, _dropped, _rescaled = L._figure_differences(HUGE["huge_int"], [CONTROL])
    assert introduced and introduced[0].startswith("9999")  # the overlong figure is still an introduced figure


# ============================================================================================ dropped hedges
@pytest.mark.parametrize("synthesis,sources,dropped", [
    ("Heat loss to the surroundings will be greater while the water boils. The efficiency during boiling is therefore likely to be below 0.870.",
     ["Heat loss to the surroundings is likely to be greater while the water boils.", "The efficiency during boiling is therefore likely to be below 0.870."],
     "Heat loss to the surroundings is likely"),
    ("The 1923 collapse left voters with a lasting fear of inflation. The Nazis probably used it.",
     ["The 1923 collapse may have left voters with a lasting fear of inflation.", "The Nazis probably used it."], "may have left voters"),
])
def test_a_hedge_dropped_beside_a_hedge_kept_elsewhere_is_named(synthesis, sources, dropped):
    out = L.dropped_hedges(synthesis, sources)
    assert len(out) == 1 and dropped in out[0] and "drops the hedge" in out[0]


@pytest.mark.parametrize("synthesis,sources", [
    ("Heat loss to the surroundings is likely to be greater while the water boils. The efficiency during boiling is therefore likely to be below 0.870.",
     ["Heat loss to the surroundings is likely to be greater while the water boils.", "The efficiency during boiling is therefore likely to be below 0.870."]),
    ("The 1923 collapse probably left voters with a lasting fear of inflation. The Nazis used it.",
     ["The 1923 collapse may have left voters with a lasting fear of inflation.", "The Nazis used it."]),
])
def test_every_hedge_kept_is_clean(synthesis, sources):
    assert L.dropped_hedges(synthesis, sources) == []


def test_a_hedge_dropped_from_a_synthesis_with_no_hedge_is_named_as_before():
    assert L.dropped_hedges("The policy worked.", ["The policy may have worked."])


# ============================================================================================ space-grouped figures
@pytest.mark.parametrize("sep", [" ", " ", " ", " ", "\\,"], ids=["space", "thin", "narrow-nbsp", "nbsp", "latex"])
def test_a_figure_grouped_with_a_space_is_one_figure_both_ways(sep):
    assert L._figure_differences(f"Break-even is 3{sep}000 cakes per month.", ["Break-even is 3,000 cakes per month."]) == ([], [], [])
    assert L._figure_differences("The price was 1,512,000 marks.", [f"The price was 1{sep}512{sep}000 marks."]) == ([], [], [])
    assert L._figure_differences(f"The total was 21{sep}131.40 dollars.", ["The total was 21131.40 dollars."]) == ([], [], [])
    assert L.figure_pairing_differences(f"Break-even is 3{sep}000 cakes per month.", ["Break-even is 3,000 cakes per month."]) == []


def test_numbers_that_are_not_digit_groups_stay_apart():
    # a lead of four digits, a group of other than three digits: separate figures, as before
    assert L._figure_differences("In 1990 100 people came.", ["In 1990 100 people came."]) == ([], [], [])
    introduced, _d, _r = L._figure_differences("In 1990 120 people came.", ["In 1990 100 people came."])
    assert introduced == ["120"]
    introduced, _d, _r = L._figure_differences("Break-even is 3 500 cakes per month.", ["Break-even is 3,000 cakes per month."])
    assert introduced == ["3500"]  # a different number is still introduced


def test_space_grouping_is_read_in_linear_time():
    text = "It cost " + " ".join(["123"] * 100_000) + " marks and then " + "1 " * 100_000 + "x."
    timing = measure(lambda: L._ungroup(text), bound=1.0, repeat=3, label="digit groups over 600 KB")
    assert timing.holds, timing


# ============================================================================================ list markers over blank lines
# (handed over by the overseer fixer: ``_LIST_MARKER_RE.sub`` rescanned a run of blank lines from every line start in it)
BLANK_RUNS = {"blank_lines": "a." + "\n" * 40_000 + "b", "blank_lines_then_marker": "In 1990 it was 5." + "\n" * 40_000 + "1. In 1991 it was 6.",
              "spaced_blank_lines": "x" + " \n" * 40_000 + "y 1990"}


@pytest.mark.parametrize("name", list(BLANK_RUNS))
def test_list_markers_are_stripped_in_linear_time_through_every_reader(name):
    text = BLANK_RUNS[name]
    for label, call in (("strip", lambda: L._strip_list_markers(text)), ("figure_spellings", lambda: L.figure_spellings(text)),
                        ("pairing", lambda: L.figure_pairing_differences(text, ["In 1990 it was 5."]))):
        timing = measure(call, bound=1.0, repeat=3, label=f"{label} over {name} (40,000 line breaks)")
        assert timing.holds, timing


def test_the_linear_list_marker_reader_gives_exactly_the_reference_substitution():
    import random
    rng = random.Random(20261031)
    pieces = ["\n", "\n", " ", "\t", "\r", "\u00a0", "\u2028", "\x0b", "1", "12", "123", ".", ")", "(", "a", "(1)", "1.", "2)", " 3. ",
              "\n1. ", "\n\n(2) ", "\u0663.", "\u3000"]
    texts = ["".join(rng.choice(pieces) for _ in range(rng.randint(0, 30))) for _ in range(20_000)]
    texts += ["a." + "\n" * 3000 + "b", "\n" * 3000 + "1. x", "1.\n2.\n3. x", "(1) a\n (2) b", " \n \n 12) z", "1. ", "", "\n",
              "\n1. \n2. \n", "a\n\n\n1. x", "99. x", "100. x", "\n\t(7)\tz"]
    assert [L._strip_list_markers(t) for t in texts] == [L._LIST_MARKER_RE.sub(" ", t) for t in texts]


# ============================================================================================ the pairing reader on long texts
# (found while sweeping the ledger this round: comma-joined dates re-read the whole carried clause per segment, every
# figure of a long clause was compared with every other, and each event-word lookup scanned every pair: quadratic, about
# 9 s per call at a synthesis's 49,152 characters and 35-40 s at 100,000; now linear, about 1 s at 60,000)
LONG_PAIRING = {
    "dates_after_commas": lambda n: " ".join(f"{i} in {1900 + i % 100}," for i in range(n // 12)) + ".",
    "one_clause_of_numbers": lambda n: "The values " + " ".join(str(i) for i in range(n // 6)) + " rose.",
    "from_to_changes": lambda n: " ".join(f"rose from {i} to {i + 1}," for i in range(n // 22)) + ".",
    "years_and_acts": lambda n: " ".join(f"In {1500 + i % 500} the Act {['passed', 'failed', 'began', 'ended'][i % 4]} {i}." for i in range(n // 30)),
}


@pytest.mark.parametrize("name", list(LONG_PAIRING))
@pytest.mark.parametrize("position", ["source", "synthesis"])
def test_the_pairing_reader_is_linear_on_long_texts(name, position):
    long_text = LONG_PAIRING[name](60_000)
    short = "In 1990 the total was 5 people."
    args = (short, [long_text]) if position == "source" else (long_text, [short])
    timing = measure(lambda: L.figure_pairing_differences(*args), bound=6.0, repeat=3, label=f"pairing, {name} (60,000 characters) as the {position}")
    assert timing.holds, timing


# ============================================================================================ pairing across a merge's join
ROW_A = "| start | 0 | 8 |  | 0 |  |  |  |"
ROW_B = "| 1 | 5 | 8 | 4 | 1 | 21 | 1 | 5 |"


def test_a_verbatim_merge_of_two_table_rows_pairs_nothing_across_the_join():
    assert L.figure_pairing_differences(f"{ROW_A} {ROW_B}", [ROW_A, ROW_B]) == []
    assert L.figure_pairing_differences(f"{ROW_A}\n{ROW_B}", [ROW_A, ROW_B]) == []


def test_an_exchange_inside_one_copied_statement_is_still_named():
    src = ["The 1923 hyperinflation peaked in November, while unemployment peaked at 6 million in 1932."]
    syn = "The 1932 hyperinflation peaked in November, while unemployment peaked at 6 million in 1923."
    assert any("exchanged" in d or "1923" in d for d in L.figure_pairing_differences(syn, src))


# ============================================================================================ actors and credits
NAZI_SOURCE = ["The 1923 collapse may have left voters with a lasting fear of inflation that the Nazis later used."]


@pytest.mark.parametrize("synthesis", [
    "The History specialist argues that the 1923 collapse may have left voters with a lasting fear of inflation that the Nazis later used.",
    "According to the History specialist, the 1923 collapse may have left voters with a lasting fear of inflation that the Nazis later used.",
    "In the Weimar years the 1923 collapse may have left voters with a lasting fear of inflation that the Nazis later used.",
])
def test_a_credit_to_the_specialist_or_a_name_after_a_determiner_is_no_substituted_actor(synthesis):
    assert L.substituted_names(synthesis, NAZI_SOURCE, "merged") == []


@pytest.mark.parametrize("synthesis,source,actor", [
    ("The Treaty of Versailles was signed by the Allies in 1919.", "The Treaty of Versailles was signed by the Germans in 1919.", "Allies"),
    ("Robert Peel championed the Ten Hours Act.", "Lord Ashley championed the Ten Hours Act.", "Robert Peel"),
    ("On 27 October Khrushchev chose to answer.", "On 27 October he chose to answer.", "Khrushchev"),
])
def test_a_real_substitution_is_still_named(synthesis, source, actor):
    out = L.substituted_names(synthesis, [source], "merged")
    assert len(out) == 1 and f"'{actor}'" in out[0] and "substituted actor" in out[0]


BREAD = SuppliedText(document_id="doc-bread", title="Bread price table", author=None, text="Month | Price in marks\nJanuary 1923 | 250\nJuly 1923 | 3465\nNovember 1923 | 80000000000")


def _history(claims, supplied=(BREAD,), refs=None):
    common = dict(request_id="req", task_id="task", report_id="rep-h", agent_id="history-specialist", subject="History", task_type="short_answer")
    records = [ClaimRecord(**common, claim_id=cid, claim_text=text, claim_role="point", source_refs=list((refs or {}).get(cid, [])))
               for cid, text in claims]
    body = " ".join(text for _c, text in claims)
    return SpecialistReport(**common, original_response=body, response_sha256=sha256_text(body), created_at="2026-10-17T00:00:00Z", claims=records,
                            supplied_texts=list(supplied))


H_CLAIMS = [("h1.9", "The 1923 collapse may have left voters with a lasting fear of inflation that the Nazis later used, but the table cannot test that."),
            ("h1.10", "Prices rose from 250 marks in January to 3465 marks in July 1923.")]


def _credit_findings(text, report):
    claim = SynthesizedClaim(claim_id="y1", text=text, source_claim_ids=["h1.9"], transformation="paraphrased")
    syn = Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=["rep-h"],
                    claims=[claim], text=text, text_sha256=sha256_text(text), created_at="2026-10-17T00:00:00Z")
    return [f.message for f in check_synthesis_ledger([report], syn) if f.code in ("INT-LEDGER-025", "INT-LEDGER-026") and "y1" in f.claim_ids]


@pytest.mark.parametrize("lead", ["The table shows that ", "The bread price table shows that "])
def test_a_specialists_view_credited_to_the_supplied_table_is_named(lead):
    text = lead + "the 1923 collapse may have left voters with a lasting fear of inflation that the Nazis later used."
    out = _credit_findings(text, _history(H_CLAIMS))
    assert any("credits the statement" in m and f"to '{lead.split(' shows')[0]}'" in m for m in out), out


def test_a_credit_to_the_table_its_cited_claim_takes_from_it_is_not_charged_as_unsourced():
    text = "The table shows that prices rose from 250 marks in January to 3465 marks in July 1923."
    report = _history(H_CLAIMS, refs={"h1.10": [SourceRef(document_id="doc-bread", excerpt="July 1923 | 3465")]})
    claim = SynthesizedClaim(claim_id="y1", text=text, source_claim_ids=["h1.10"], transformation="paraphrased")
    syn = Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=["rep-h"],
                    claims=[claim], text=text, text_sha256=sha256_text(text), created_at="2026-10-17T00:00:00Z")
    out = [f.message for f in check_synthesis_ledger([report], syn) if f.code == "INT-LEDGER-026" and "y1" in f.claim_ids]
    assert not any("cite no excerpt of that document" in m for m in out), out


# ============================================================================================ merged claims aligned per source
SIGMA = "The GDC normal inputs take the standard deviation, σ = 12, not the variance."
P_LINE = "Normal probability, lower bound 190, upper bound a very large number, μ = 170, σ = 12: P(X > 190) = 0.04779"


def test_a_merge_of_its_sources_own_words_adds_no_negation():
    merged = f"{SIGMA} {P_LINE}"
    assert L.aligned_changes(merged, " ".join([SIGMA, P_LINE])) == ([], [])
    assert L.aligned_differences(merged, [SIGMA, P_LINE]) == ([], [])


def test_a_negation_added_to_a_merge_is_still_named():
    merged = f"{SIGMA} Normal probability, lower bound 190, upper bound a very large number, μ = 170, σ = 12: P(X > 190) is not 0.04779"
    _figs, meaning = L.aligned_differences(merged, [SIGMA, P_LINE])
    assert any("negation" in m for m in meaning), meaning
