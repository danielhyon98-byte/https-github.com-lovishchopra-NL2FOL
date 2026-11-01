"""Integration gate 2: the claim ledger's findings (integrity/ledger.py).

* critical, input stall (rule ``name-partner``): ``_name_partners`` scanned forward to the end of the sentence for a ')' at
  every '(' token, so a run of unclosed '(' in a synthesis's student-facing text was quadratic (20.5 s at 32,000; about
  55 minutes at the 400,000-character limit). The first ')' and the first ',' after every token now come from one backward
  pass. ``unit_differences`` read a unit run over a whole token from every figure inside it ('1–2–1–2–...', 11.4 s at
  32,000): a token is now at most ``_UNIT_TOKEN_MAX`` characters, longer tokens are no unit. Both readers give the results
  they gave on every recorded text.
* major, a dropped hedge in a merged claim was masked: a synthesized sentence that restated another hedged source sentence
  better counted as a restatement of this one, so the hedge it kept masked the hedge dropped here.
* major, a wrong attribution to a consensus, a discipline or a party that is no source ("Historians agree that",
  "It is widely accepted that", "The evidence shows that", "[History] ..." on an Economics claim) was not named.
* major, a changed unit after a LaTeX math span ("$6.0$ kN" for "$6.0$ N") or after a figure in scientific notation
  ("2.3 × 10⁶ J kg⁻¹" for "2.3 × 10⁶ J g⁻¹") was not named.

The sweep test at the end feeds every public text reader of the module and ``check_synthesis_ledger`` the standard hostile
inputs (``tests/core_hostile.py``) and asserts a CPU-time bound per call.
"""
from __future__ import annotations

import random
import time

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity import ledger as L
from epinoic_logic.integrity.ledger import check_synthesis_ledger, dropped_hedges, unit_differences
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

from ..core_hostile import SHAPES, one, sweep


def codes(findings) -> list[str]:
    return [f.code for f in findings]


def _report(rid: str, agent: str, subject: str, claims: list[tuple[str, str]]) -> SpecialistReport:
    text = " ".join(t for _c, t in claims)
    base = dict(request_id="req", task_id="task", report_id=rid, agent_id=agent, subject=subject, task_type="short_answer")
    return SpecialistReport(**base, original_response=text, response_sha256=sha256_text(text), created_at="2026-10-12T00:00:00Z",
                            claims=[ClaimRecord(**base, claim_id=c, claim_text=t, claim_role="evidence", materiality="material") for c, t in claims])


def _synthesis(reports: list[SpecialistReport], claims: list[tuple[str, str, list[str], str]], text: str | None = None,
               certainty: str = "established") -> Synthesis:
    sc = [SynthesizedClaim(claim_id=c, text=t, source_claim_ids=s, transformation=tr, certainty=certainty) for c, t, s, tr in claims]
    text = text if text is not None else " ".join(c.text for c in sc)
    return Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator",
                     source_report_ids=[r.report_id for r in reports], claims=sc, text=text, text_sha256=sha256_hex(text),
                     created_at="2026-10-12T01:00:00Z")


# ============================================================================================ critical: linear readers
_SOURCE = "In 1990 the total was 5 people."


def _paren_case(n: int):
    rep = _report("rep-h", "history-specialist", "History", [("h1.1", _SOURCE)])
    return rep, _synthesis([rep], [("syn-1", _SOURCE, ["h1.1"], "carried")], text=_SOURCE + " Also " + "(" * n + " 1990.")


def test_a_run_of_unclosed_brackets_in_the_synthesis_text_is_read_in_linear_time():
    """The finding's input: a valid one-claim synthesis whose student-facing text carries 32,000 unclosed '(' took 20.47 s
    (cProfile: 4.91 of 5.14 s at 16,000 in the forward scan). It now takes well under a second, with the same result."""
    rep, syn = _paren_case(32_000)
    c0 = time.process_time()
    found = check_synthesis_ledger([rep], syn)
    spent = time.process_time() - c0
    assert codes(found) == ["INT-LEDGER-031"], codes(found)
    assert spent < 6.0, spent  # measured 0.72 s; 20.47 s before the fix


def test_the_largest_synthesis_text_with_unclosed_brackets_is_read_in_seconds():
    rep, syn = _paren_case(399_000)  # the contract's limit is 400,000 characters (about 55 minutes before the fix)
    c0 = time.process_time()
    found = check_synthesis_ledger([rep], syn)
    assert time.process_time() - c0 < 30.0  # measured 2.8 s
    assert codes(found) == ["INT-LEDGER-031"]


@pytest.mark.parametrize("text", ["(" * 32_000, ", which x" * 4_000 + " 1990", "(" * 16_000 + ")" + "(" * 16_000],
                         ids=["unclosed brackets", "relative clauses", "brackets around one closer"])
def test_the_figure_pairing_reader_is_linear_on_unclosed_brackets_and_relative_clauses(text):
    c0 = time.process_time()
    assert L.figure_pairing_differences(text, [_SOURCE]) == []
    assert time.process_time() - c0 < 6.0  # 20.71 s at 32,000 before the fix


def test_a_run_of_dashed_digits_is_read_for_units_in_linear_time():
    c0 = time.process_time()
    assert unit_differences("1–2–" * 8_000, [_SOURCE]) == []
    assert time.process_time() - c0 < 6.0  # 11.43 s at 32,000 before the fix


def test_the_jump_tables_find_what_the_forward_scans_found():
    """``_next_token_index`` against the forward scans it replaced (kept here as the specification), on random sentences."""
    rng = random.Random(29)
    for _ in range(3000):
        toks = [rng.choice(["(", ")", ",", "which", "the", "Act", "1833", "of"]) for _ in range(rng.randint(0, 14))]
        nxt_close, nxt_comma = L._next_token_index(toks, ")"), L._next_token_index(toks, ",")
        for k in range(len(toks)):
            assert nxt_close[k + 1] == next((x for x in range(k + 1, len(toks)) if toks[x] == ")"), None)
            if k + 2 <= len(toks):
                assert nxt_comma[k + 2] == next((x for x in range(k + 2, len(toks)) if toks[x] == ","), None)


@pytest.mark.parametrize("synthesized,source,named", [
    ("The Ten Hours Act of 1833 banned night work.", "The Factory Act of 1833 banned night work. The Ten Hours Act of 1847 limited hours.", True),
    ("The Factory Act (1833) banned night work.", "The Factory Act of 1833 banned night work.", False),
])
def test_the_name_partner_rule_still_names_a_re_paired_name(synthesized, source, named):
    assert bool(L.figure_pairing_differences(synthesized, [source])) == named


@pytest.mark.parametrize("unit_text", ["9.6 A", "15 m/s", "2 kg", "225 kJ", "30 per cent", "45 square units", "-10-fold"])
def test_a_unit_in_an_ordinary_token_is_still_read(unit_text):
    figures = L._unit_figures(f"The value is {unit_text}.")
    assert figures and figures[0][1] is not None, figures


def test_a_token_longer_than_the_unit_limit_is_no_unit():
    long_token = "m/" * 40
    assert L._unit_after(" " + long_token, 0) is None
    assert L._unit_after(" m/s " + long_token, 0) is not None  # the run ends before the long token


# ============================================================================================ major: dropped hedges in a merged claim
_HEDGED = ["Inflation probably hurt German savers in 1923.", "German savers probably blamed the republic for the inflation."]
_KETTLE = ["Heat loss to the surroundings is likely to be greater while the water boils, because the water and the kettle are then at about "
           "100 °C, a larger temperature difference from the surroundings than during heating.",
           "The efficiency during boiling is therefore likely to be below 0.870, less energy reaches the water as latent heat, and the "
           "estimate of 2.3 × 10⁶ J kg⁻¹ comes out higher than the accepted value of 2.26 × 10⁶ J kg⁻¹."]


@pytest.mark.parametrize("synthesized,dropped", [
    ("Inflation hurt German savers in 1923. German savers probably blamed the republic for the inflation.", ["Inflation probably hurt"]),
    ("Inflation probably hurt German savers in 1923. German savers blamed the republic for the inflation.", ["German savers probably blamed"]),
    ("Inflation hurt German savers in 1923. German savers blamed the republic for the inflation.", ["Inflation probably hurt", "German savers probably blamed"]),
    ("Inflation probably hurt German savers in 1923. German savers probably blamed the republic for the inflation.", []),
], ids=["drop_first", "drop_second", "drop_both", "keep_both"])
def test_a_hedge_kept_in_one_merged_sentence_never_masks_the_hedge_dropped_in_another(synthesized, dropped):
    found = dropped_hedges(synthesized, _HEDGED)
    assert len(found) == len(dropped), found
    for words in dropped:
        assert any(words in f for f in found), (words, found)


@pytest.mark.parametrize("old,new,dropped", [
    ("is likely to be greater", "is greater", "Heat loss"),
    ("is likely to be greater", "will be greater", "Heat loss"),
    ("is therefore likely to be below", "is therefore below", "The efficiency"),
    (None, None, None),
], ids=["drop_likely_first_only", "likely_to_will", "drop_likely_second_only", "keep_both"])
def test_the_recorded_kettle_merge_names_the_hedge_it_drops(old, new, dropped):
    merged = " ".join(_KETTLE)
    found = dropped_hedges(merged.replace(old, new) if old else merged, _KETTLE)
    if dropped is None:
        assert found == []
    else:
        assert len(found) == 1 and dropped in found[0] and "'likely'" in found[0], found


@pytest.mark.parametrize("distinct", [False, True], ids=["repeated sentences", "distinct sentences"])
def test_the_hedge_comparison_on_the_largest_claim_and_cited_sources_is_bounded(distinct):
    """A synthesized claim at the contract's 4,000 characters against 64 cited claims of 4,000 characters, every source
    sentence hedged: every synthesized sentence is compared with every hedged source statement, once per distinct pair
    (measured 0.41 s for distinct sentences and 0.11 s for repeated ones, where the reading before the gate took 0.43 s
    and 0.6 to 0.8 s)."""
    import itertools
    import string
    names = ("".join(p) for p in itertools.product(string.ascii_lowercase, repeat=4))

    def sentence(hedge: bool) -> str:
        tail = f"{next(names)} {next(names)}" if distinct else "fast"
        return f"Prices {'probably ' if hedge else ''}rose {tail}. "

    synthesized, sources = "", []
    while len(synthesized) < 3_850:
        synthesized += sentence(False)
    for _ in range(64):
        text = ""
        while len(text) < 3_950:
            text += sentence(True)
        sources.append(text)
    c0 = time.process_time()
    found = dropped_hedges(synthesized, sources)
    assert time.process_time() - c0 < 5.0
    # repeated: the synthesis restates the hedged statement flatly, so its hedge is dropped; distinct: every sentence names
    # other things, so no synthesized sentence restates a source statement and nothing is named
    assert bool(found) == (not distinct), found[:2]


def test_a_merged_claim_that_drops_one_hedge_is_named_through_the_ledger():
    rep = _report("rep-e", "economics-specialist", "Economics", [("e1", _HEDGED[0]), ("e2", _HEDGED[1])])
    wrong = _synthesis([rep], [("s0", "Inflation hurt German savers in 1923. German savers probably blamed the republic for the inflation.", ["e1", "e2"], "merged")],
                       certainty="possible")
    found = [f for f in check_synthesis_ledger([rep], wrong) if f.code == "INT-LEDGER-026"]
    assert found and "drops the hedge" in found[0].message and "Inflation probably hurt" in found[0].message
    right = _synthesis([rep], [("s0", " ".join(_HEDGED), ["e1", "e2"], "merged")], certainty="possible")
    assert not [f for f in check_synthesis_ledger([rep], right) if f.code == "INT-LEDGER-026" and "drops the hedge" in f.message]


# ============================================================================================ major: credits to a party that is no source
_VIEW = "The reparations bill of 1921 may have weakened the republic's finances."
_CREDITS = {
    "historians_agree": "Historians agree that the reparations bill of 1921 may have weakened the republic's finances.",
    "it_is_widely_accepted": "It is widely accepted that the reparations bill of 1921 may have weakened the republic's finances.",
    "scholars_argue": "Scholars argue that the reparations bill of 1921 may have weakened the republic's finances.",
    "experts_say": "Experts say the reparations bill of 1921 may have weakened the republic's finances.",
    "economists_agree": "Economists agree that the reparations bill of 1921 may have weakened the republic's finances.",
    "the_evidence_shows": "The evidence shows that the reparations bill of 1921 may have weakened the republic's finances.",
    "the_economic_analysis_shows": "The economic analysis shows that the reparations bill of 1921 may have weakened the republic's finances.",
    "the_question_states": "The question states that the reparations bill of 1921 may have weakened the republic's finances.",
    "the_router_notes": "The router notes that the reparations bill of 1921 may have weakened the republic's finances.",
    "the_economists_view": "The economist's view is that the reparations bill of 1921 may have weakened the republic's finances.",
}


def _two_specialists():
    hist = _report("rep-h", "history-specialist", "History", [("h1.1", _VIEW)])
    econ = _report("rep-e", "economics-specialist", "Economics", [("g1.1", "Hyperinflation peaked in November 1923.")])
    return hist, econ


@pytest.mark.parametrize("name", sorted(_CREDITS))
def test_a_view_credited_to_a_consensus_a_discipline_or_another_party_is_named(name):
    hist, econ = _two_specialists()
    syn = _synthesis([hist, econ], [("s0", _CREDITS[name], ["h1.1"], "paraphrased")], certainty="possible")
    found = [f for f in check_synthesis_ledger([hist, econ], syn) if f.code == "INT-LEDGER-026"]
    assert found and "it credits the statement to" in found[0].message, [(f.code, f.message[:200]) for f in check_synthesis_ledger([hist, econ], syn)]


@pytest.mark.parametrize("text", [
    "In the History specialist's view, the reparations bill of 1921 may have weakened the republic's finances.",
    "The History specialist notes that the reparations bill of 1921 may have weakened the republic's finances.",
    _VIEW,
])
def test_a_credit_to_the_cited_specialist_or_no_credit_is_clean(text):
    hist, econ = _two_specialists()
    syn = _synthesis([hist, econ], [("s0", text, ["h1.1"], "paraphrased")], certainty="possible")
    assert not [f for f in check_synthesis_ledger([hist, econ], syn) if f.code == "INT-LEDGER-026" and "credit" in f.message]


def test_a_credit_the_cited_source_gives_itself_is_carried_not_named():
    hist = _report("rep-h", "history-specialist", "History", [("h1.1", _CREDITS["historians_agree"])])
    econ = _report("rep-e", "economics-specialist", "Economics", [("g1.1", "Hyperinflation peaked in November 1923.")])
    syn = _synthesis([hist, econ], [("s0", _CREDITS["historians_agree"], ["h1.1"], "carried")], certainty="possible")
    assert not [f for f in check_synthesis_ledger([hist, econ], syn) if f.code == "INT-LEDGER-026" and "credit" in f.message]


def test_a_credit_to_the_question_or_the_router_is_named_even_over_a_flat_statement():
    hist = _report("rep-h", "history-specialist", "History", [("h1.1", "Article 48 allowed the president to rule by decree in emergencies.")])
    econ = _report("rep-e", "economics-specialist", "Economics", [("g1.1", "Hyperinflation peaked in November 1923.")])
    for lead in ("The question states that", "The router notes that"):
        syn = _synthesis([hist, econ], [("s0", f"{lead} Article 48 allowed the president to rule by decree in emergencies.", ["h1.1"], "paraphrased")])
        assert [f for f in check_synthesis_ledger([hist, econ], syn) if f.code == "INT-LEDGER-026" and "it credits the statement to" in f.message], lead
    # a group credit over a statement the source states flatly presents nothing as more established (the earlier control,
    # tests/integrity/test_synthesis_qualifiers_and_credit.py 'a group')
    syn = _synthesis([hist, econ], [("s0", "Historians agree that Article 48 allowed the president to rule by decree in emergencies.", ["h1.1"], "paraphrased")])
    assert not [f for f in check_synthesis_ledger([hist, econ], syn) if f.code == "INT-LEDGER-026" and "credit" in f.message]


def test_a_bracketed_subject_tag_credits_that_subject_s_specialist():
    hist, econ = _two_specialists()
    wrong = _synthesis([hist, econ], [("s0", "[History] Hyperinflation peaked in November 1923.", ["g1.1"], "paraphrased")])
    found = [f for f in check_synthesis_ledger([hist, econ], wrong) if f.code == "INT-LEDGER-026"]
    assert found and "history-specialist" in found[0].message
    right = _synthesis([hist, econ], [("s0", "[Economics] Hyperinflation peaked in November 1923.", ["g1.1"], "paraphrased")])
    assert not [f for f in check_synthesis_ledger([hist, econ], right) if f.code == "INT-LEDGER-026" and "credit" in f.message]


# ============================================================================================ major: units after LaTeX and in scientific notation
UNIT_CHANGES_STEM = [
    ("The force is $6.0$ N.", "The force is $6.0$ kN.", True),
    ("The mass is $9.0$ g.", "The mass is $9.0$ kg.", True),
    ("So $m = nM = 0.50 \\times 18 = 9.0$ g.", "So $m = nM = 0.50 \\times 18 = 9.0$ kg.", True),
    ("The current is \\(9.6\\) A.", "The current is \\(9.6\\) mA.", True),
    ("The energy is 2.3 × 10⁶ J g⁻¹.", "The energy is 2.3 × 10⁶ J kg⁻¹.", True),
    ("The energy is $2.3 \\times 10^{6}$ J kg$^{-1}$.", "The energy is $2.3 \\times 10^{6}$ J g$^{-1}$.", True),
    # the same unit in LaTeX and in plain text, and prices, are no change
    ("The force is 6.0 N.", "The force is $6.0$ N.", False),
    ("The force is $6.0$ N.", "The force is 6.0 N.", False),
    ("The force is $6.0\\,\\text{N}$.", "The force is 6.0 N.", False),
    ("The energy is 2.3 × 10⁶ J kg⁻¹.", "The energy is 2.3 \\times 10^{6} J kg^{-1}.", False),
    ("The constant is 6.63 × 10⁻³⁴ J s.", "The photon has 4.0 × 10⁻¹⁹ J.", False),
    ("Prices rose from $5 to $6.", "Prices rose from $5 to $6.", False),
]


@pytest.mark.parametrize("source,synthesized,named", UNIT_CHANGES_STEM, ids=[s[:48] for _src, s, _n in UNIT_CHANGES_STEM])
def test_a_changed_unit_in_latex_or_scientific_notation_is_named(source, synthesized, named):
    found = unit_differences(synthesized, [source])
    assert bool(found) == named, found


def test_a_changed_unit_after_a_math_span_is_an_error_through_the_ledger():
    rep = _report("rep-c", "chemistry-specialist", "Chemistry", [("s1.1", "So $m = nM = 0.50 \\times 18 = 9.0$ g.")])
    syn = _synthesis([rep], [("s0", "So $m = nM = 0.50 \\times 18 = 9.0$ kg.", ["s1.1"], "paraphrased")])
    found = [f for f in check_synthesis_ledger([rep], syn) if f.code == "INT-LEDGER-023"]
    assert found and found[0].severity == "error" and "in another unit or era" in found[0].message


# ============================================================================================ the sweep: every text reader of the module
_PAIR_READERS = ("figure_pairing_differences", "unit_differences", "dropped_hedges", "dropped_qualifiers", "reversed_voices", "reversed_comparisons",
                 "aligned_differences", "day_month_differences", "credited_date_repairings")
_TRANSFORMED = ("meaning_differences", "meaning_inversions", "substituted_names")
_ONE_TEXT = ("figure_spellings", "figure_tokens", "incidental_figures", "foreign_number_values", "meaningful", "fold_exponent_marks", "light_stem",
             "text_outside_claims")


def _ledger_entries(text: str):
    for name in _PAIR_READERS:
        fn = getattr(L, name)
        yield f"{name}(synthesis)", lambda fn=fn: fn(text, [_SOURCE]) if fn is not L.credited_date_repairings else fn(text, _SOURCE)
        yield f"{name}(source)", lambda fn=fn: fn(_SOURCE, [text]) if fn is not L.credited_date_repairings else fn(_SOURCE, text)
    for name in _TRANSFORMED:
        fn = getattr(L, name)
        yield f"{name}(synthesis)", lambda fn=fn: fn(text, [_SOURCE], "paraphrased")
        yield f"{name}(source)", lambda fn=fn: fn(_SOURCE, [text], "merged")
    for name in _ONE_TEXT:
        fn = getattr(L, name)
        yield name, (lambda fn=fn: fn(text, [_SOURCE])) if name == "text_outside_claims" else (lambda fn=fn: fn(text))
    yield "aligned_changes", lambda: L.aligned_changes(text, _SOURCE)
    yield "unlocated_quotations", lambda: L.unlocated_quotations(text, [_SOURCE])
    yield "quotation_form_differences", lambda: L.quotation_form_differences(text, [_SOURCE])
    # integration gate 3: the readers the gate's majors added (an introduced name, a count or relative date in words)
    yield "introduced_names(synthesis)", lambda: L.introduced_names(text[:4_000], [_SOURCE], "paraphrased", stated_elsewhere=set())
    yield "introduced_names(source)", lambda: L.introduced_names(_SOURCE, [text], "merged", stated_elsewhere=set())
    yield "figure differences with counts in words", lambda: L._figure_differences(text, [_SOURCE])


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_ledger_readers(shape):
    """One test per hostile shape (integration gate 3: the whole sweep in one test overran the suite's 120 s wall-clock
    timeout on a loaded machine; the per-call CPU-time bound decides, unchanged)."""
    assert not sweep(_ledger_entries, texts=one(shape))


def _ledger_check_entries(text: str):
    claim = text[:3_900] if text[:3_900].strip() else "x"
    rep_hostile = _report("rep-h", "history-specialist", "History", [("h1.1", claim)])
    rep = _report("rep-h", "history-specialist", "History", [("h1.1", _SOURCE)])
    yield "check_synthesis_ledger(text)", lambda: check_synthesis_ledger([rep], _synthesis([rep], [("s0", _SOURCE, ["h1.1"], "carried")], text=_SOURCE + " " + text))
    yield "check_synthesis_ledger(claim)", lambda: check_synthesis_ledger([rep], _synthesis([rep], [("s0", claim, ["h1.1"], "paraphrased")]))
    yield "check_synthesis_ledger(source)", lambda: check_synthesis_ledger([rep_hostile], _synthesis([rep_hostile], [("s0", _SOURCE, ["h1.1"], "paraphrased")]))
    # integration gate 3: one hostile source claim cited by eight synthesized claims (its figures were read again for every
    # figure and for every citing claim)
    yield "check_synthesis_ledger(source cited 8 times)", lambda: check_synthesis_ledger(
        [rep_hostile], _synthesis([rep_hostile], [(f"s{i}", _SOURCE, ["h1.1"], "paraphrased") for i in range(8)]))


_CHECK_SHAPES = tuple(k for k in SHAPES if not k.startswith(("braces", "fence")))


@pytest.mark.parametrize("shape", _CHECK_SHAPES)
def test_sweep_check_synthesis_ledger(shape):
    """The ledger check on a synthesis whose text, synthesized claim or cited source claim is a hostile input (a claim is at
    most 4,000 characters, so the first 3,900 are used there: the formula constants of integration gate 3 at the claim
    cap). The contract refuses some of these texts (a blank claim text): a refusal is a ValueError, which is allowed. One
    test per shape (integration gate 3)."""
    assert not sweep(_ledger_check_entries, bound=12.0, texts=one(shape))
