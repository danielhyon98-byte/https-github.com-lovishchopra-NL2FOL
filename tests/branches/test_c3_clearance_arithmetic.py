"""Clearance c3 (arena round 10): arithmetic stated in prose, calendar lengths and figures taken from supplied texts (owner: parsers).

The adversarial lens of round 10 found twelve arithmetic faults in the c3 answers of Economics, Business Management, Psychology,
Geography and English A: Language and Literature that crossed the hub with no finding, or only with CORE-QNT-001 ('could not be
checked'), and two History lengths of time that passed. Each is decided now, beside the genuine sentence it changed:

* prose arithmetic (``worked.prose_problems``): a share with its per cent in brackets, a change with its per cent, a per cent with its
  working, a difference ('differ by'), a distance from a bound, and a difference of two costs the paragraph states ('Option 2 is $110,000
  cheaper');
* worked lines on the Psychology branch ('4.5 − 0.6 = 4.9 points', '(3.7 ÷ 2.9 ≈ 1.8)') and a currency prefix such as 'P$';
* calendar lengths (``quant``): a bound or an approach ('almost four years') between two month dates read on the calendar, a span in
  brackets right after a length ('lasted about five years (1918–1921)'), and a length ordered against an event named by a proper name and
  dated in another sentence ('About seven months after Darfield, on 22 February 2011, ...');
* figures taken from supplied texts (``grounded_figures``): a ratio of two table columns ('Catch per boat ... 125.0 tonnes in 2019'), a
  figure the claim credits to a case that the case states otherwise ("the firm's own figures: ... 32 employees"), and a misread figure the
  claim credits to the text is an error;
* every new reader stays linear on the standard hostile inputs.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist.chronology import chronology_relations
from epinoic_logic.branches.grounded_figures import _ratio_findings, _stem_noun_findings, figure_grounding_checks, supplied_tables
from epinoic_logic.branches.quant import extract_quant_checks, undecided_quant_statements
from epinoic_logic.branches.worked import _p_cost_differences, prose_problems
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from ..adapters.hostile_inputs import all_inputs, bounded, word_runs
from . import c3_arith_texts as A
from .test_c2b_clearance_parsers import codes, doc, findings, status, through_hub

QUESTION = "Answer the question."


def prose_statuses(text: str) -> list[tuple[str, str]]:
    return [(wp.phrase, status(wp.problem)) for wp in prose_problems(text, report_id="r", request_id="q", prefix="core-prose")]


def quant_statuses(text: str) -> list[tuple[str, str]]:
    return [(q.kind, status(q.problem)) for q in extract_quant_checks(text, request_id="r", claim_id="c")]


def report_with(claim: str, supplied) -> SpecialistReport:
    texts = [doc(supplied)]
    return SpecialistReport(report_id="r1", request_id="q", task_id="t", agent_id="a", subject="Economics", task_type="short_answer",
                            original_response=claim, response_sha256=sha256_text(claim), supplied_texts=texts,
                            claims=[ClaimRecord(claim_id="c1", request_id="q", task_id="t", report_id="r1", agent_id="a", subject="Economics",
                                                task_type="short_answer", claim_text=claim, claim_role="evidence", proposed_claim_kind="factual",
                                                certainty="established", materiality="supporting")], created_at="2026-11-15T00:00:00Z")


# ============================================================================================ prose arithmetic
@pytest.mark.parametrize("vid,wrong,right", A.PROSE_ARITHMETIC, ids=[v[0] for v in A.PROSE_ARITHMETIC])
def test_prose_arithmetic_is_decided_beside_the_genuine_sentence(vid, wrong, right):
    assert [s for _p, s in prose_statuses(wrong)] == ["COUNTEREXAMPLE"], (vid, prose_statuses(wrong))
    assert [s for _p, s in prose_statuses(right)] == ["ENTAILED"], (vid, prose_statuses(right))


@pytest.mark.parametrize("sentence,expected", A.COST_DIFFERENCES)
def test_a_difference_of_two_stated_costs_is_decided(sentence, expected):
    """bm-cheaper: 'Option 2 is $110,000 cheaper' after costs of $380,000 and $290,000 crossed with no finding."""
    got = [s for p, s in prose_statuses(A.OPTION_COSTS + sentence) if "cheaper" in p or "expensive" in p or "than" in p]
    assert got == [expected], (sentence, prose_statuses(A.OPTION_COSTS + sentence))


def test_a_cost_difference_with_no_stated_costs_or_an_ambiguous_party_is_not_read():
    assert not _p_cost_differences("Option 2 is $90,000 cheaper.")
    three = A.OPTION_COSTS + "Option 3 costs $250,000. Option 2 is $90,000 cheaper."
    assert not _p_cost_differences(three)  # cheaper than which of two others is not stated
    assert [r.phrase for _p, _s, r in _p_cost_differences(three.replace("cheaper.", "cheaper than Option 1."))]


def test_the_prose_reading_runs_on_every_prose_branch():
    for subject, agent in (("Business Management", "business-specialist"), ("Geography", "geography-specialist"),
                           ("English A: Language and Literature", "english-a-lang-lit-specialist"), ("Psychology", "psychology-specialist")):
        _reply, rc = through_hub("The answer weighs the options.\n\n" + A.OPTION_COSTS + "Option 2 is $110,000 cheaper.", QUESTION, subject=subject, agent=agent)
        assert [f for f in findings(rc, "INT-SUBJ-001") if "110,000" in f.message], (subject, codes(rc))
        _reply, rc = through_hub("The answer weighs the options.\n\n" + A.OPTION_COSTS + "Option 2 is $90,000 cheaper.", QUESTION, subject=subject, agent=agent)
        assert not [f for f in findings(rc, "INT-SUBJ-001") if "90,000" in f.message], (subject, codes(rc))


@pytest.mark.parametrize("subject,agent,wrong,right", A.WORKED_LINES, ids=["ps-diff", "ps-sd", "ec-value"])
def test_worked_lines_are_decided_on_the_psychology_and_economics_branches(subject, agent, wrong, right):
    """ps-diff and ps-sd were CORE-QNT-001 only ('which this branch's prose arithmetic reader does not decide'); ec-value's 'P$' was no
    currency the worked reader read."""
    _reply, rc = through_hub("The study compares two groups.\n\n" + wrong, QUESTION, subject=subject, agent=agent)
    assert findings(rc, "INT-SUBJ-001"), (wrong, codes(rc))
    _reply, rc = through_hub("The study compares two groups.\n\n" + right, QUESTION, subject=subject, agent=agent)
    assert not findings(rc, "INT-SUBJ-001"), (right, [f.message for f in findings(rc, "INT-SUBJ-001")])


# ============================================================================================ calendar lengths
@pytest.mark.parametrize("sentence,expected", A.CALENDAR_LENGTHS)
def test_a_stated_length_is_decided_against_its_span(sentence, expected):
    """hi-duration ('from July 1936 to April 1939, almost four years') passed on the year index; hib-duration ('lasted about five years
    (1918–1921)') was only named undecided."""
    assert quant_statuses(sentence) == [("duration", expected)], (sentence, quant_statuses(sentence))
    assert not undecided_quant_statements(sentence), undecided_quant_statements(sentence)


def test_a_bracket_before_the_length_is_a_life_not_the_span():
    sentence = "Stalin (1878–1953) ruled for nearly thirty years."
    assert not quant_statuses(sentence)
    assert undecided_quant_statements(sentence)  # named undecided, as before: its dates cannot be paired into a span


@pytest.mark.parametrize("text,expected", A.NAMED_LENGTHS)
def test_a_length_after_a_named_event_is_decided_against_the_date_the_text_gives_it(text, expected):
    """ge-months: 'About seven months after Darfield, on 22 February 2011' (Darfield: 4 September 2010, five and a half months before) gave
    CORE-CHR-001 only, which read 'About' as the event."""
    assert quant_statuses(text) == [("duration", expected)], quant_statuses(text)


def test_a_named_event_the_text_dates_twice_or_never_is_not_guessed():
    twice = ("Darfield struck on 4 September 2010. Darfield was also dated on 4 October 2010 by one source.\n\n"
             "About seven months after Darfield, on 22 February 2011, an aftershock struck.")
    assert not quant_statuses(twice)
    assert [u for u in undecided_quant_statements(twice) if "more than one date" in u.reason]
    never = "About seven months after Darfield, on 22 February 2011, an aftershock struck."
    assert not quant_statuses(never) and not undecided_quant_statements(never)


def test_a_qualifier_opening_a_sentence_is_no_event_name():
    rels = chronology_relations("About seven months after Darfield, on 22 February 2011, an aftershock struck.")
    assert not [r for r in rels if "About" in (r.later_text, r.earlier_text) or "'About'" in (r.reason or "")], rels


@pytest.mark.parametrize("subject,agent,text", [
    ("History", "history-specialist", "The Nationalists won the civil war.\n\nThe war lasted from July 1936 to April 1939, almost four years."),
    ("History", "history-specialist", "Lenin's state seized grain.\n\nWar Communism lasted about five years (1918–1921)."),
    ("Geography", "geography-specialist", A.QUAKE_DATED + "About seven months after Darfield, on 22 February 2011, an aftershock struck."),
])
def test_a_wrong_length_is_named_through_the_hub(subject, agent, text):
    _reply, rc = through_hub(text, QUESTION, subject=subject, agent=agent)
    assert findings(rc, "INT-SUBJ-001"), codes(rc)
    right = text.replace("almost four", "nearly three").replace("about five years", "about three years").replace("seven months", "six months")
    _reply, rc = through_hub(right, QUESTION, subject=subject, agent=agent)
    assert not findings(rc, "INT-SUBJ-001"), [f.message for f in findings(rc, "INT-SUBJ-001")]


# ============================================================================================ figures taken from supplied texts
def test_a_ratio_of_two_table_columns_is_read_against_their_cells():
    """ec-perboat: 'Catch per boat rose from about 125.0 tonnes in 2019' (48.0 thousand tonnes over 412 boats is 116.5) crossed."""
    tables = supplied_tables([doc(A.FISHERY_DOC)])
    found = _ratio_findings("c", A.PER_BOAT_WRONG, tables)
    assert [(r.figure.shown, r.numerator.shown, r.denominator.shown, r.factor) for r in found] == [("125.0", "48.0", "412", 1000), ("152.5", "36.0", "236", 1000)]
    checks = figure_grounding_checks(report_with(A.PER_BOAT_WRONG, A.FISHERY_DOC), "core")
    assert [status(c.problem) for c in checks] == ["COUNTEREXAMPLE", "ENTAILED"], [c.description for c in checks]
    checks = figure_grounding_checks(report_with(A.PER_BOAT_RIGHT, A.FISHERY_DOC), "core")
    assert [status(c.problem) for c in checks] == ["ENTAILED", "ENTAILED"]
    # a figure with no unit against a column in thousands, or a column that is already a rate, is not read
    assert not _ratio_findings("c", "Catch per boat rose from 117 in 2019 to 153 in 2025.", tables)
    assert not _ratio_findings("c", "The price per tonne rose to 2,880 in 2025.", tables)


def test_a_figure_credited_to_the_case_that_the_case_states_otherwise_is_an_error():
    """bm-case: "compare them with Hartwell's own figures: sales of $2,400,000 and 32 employees" (the case: 'it employs 28 people')."""
    found = _stem_noun_findings("c", A.CASE_FIGURES_WRONG, [doc(A.TOY_CASE_DOC)])
    assert [(g.figure.shown, g.cells[0].shown, g.severity) for g in found] == [("32", "28", "error")]
    assert not _stem_noun_findings("c", A.CASE_FIGURES_RIGHT, [doc(A.TOY_CASE_DOC)])
    assert not _stem_noun_findings("c", "The firm has 32 employees.", [doc(A.TOY_CASE_DOC)])  # no credit to the case: a stem is too loose alone
    _reply, rc = through_hub("The firm should expand.\n\n" + A.CASE_FIGURES_WRONG, QUESTION, subject="Business Management", agent="business-specialist",
                             texts=[doc(A.TOY_CASE_DOC)])
    assert [f for f in findings(rc, "INT-SUBJ-001") if "supplied_figure" in f.message and "28" in f.message], codes(rc)
    _reply, rc = through_hub("The firm should expand.\n\n" + A.CASE_FIGURES_RIGHT, QUESTION, subject="Business Management", agent="business-specialist",
                             texts=[doc(A.TOY_CASE_DOC)])
    assert not [f for f in findings(rc, "INT-SUBJ-001") + findings(rc, "INT-SUBJ-004") if "supplied_figure" in f.message], codes(rc)


def test_a_misread_figure_is_an_error_when_credited_and_a_warning_when_not():
    from . import c2_texts as C
    for sentence, code in (("The writer reminds readers that the baths recorded 34,000 swims last year.", "INT-SUBJ-001"),
                           ("Last year the baths recorded 34,000 swims.", "INT-SUBJ-004")):
        _reply, rc = through_hub(C.LL_T15 + "\n\n" + sentence, C.LL_T15_Q, subject="English A: Language and Literature",
                                 agent="english-a-lang-lit-specialist", texts=[doc(C.LL_T15_DOC)], task_type="analytical_paragraph")
        assert [f for f in findings(rc, code) if "supplied_figure" in f.message and "43,000" in f.message], (sentence, codes(rc))


# ============================================================================================ the new readers stay linear
READERS = {
    "prose arithmetic": lambda t: prose_problems(t, report_id="r", request_id="q", prefix="p"),
    "cost differences": lambda t: _p_cost_differences(A.OPTION_COSTS + "Option 2 is " + t),
    "cost differences (party run)": lambda t: _p_cost_differences("Option 1 costs $5. " + t + " Option 2 costs $4. Option 2 is $1 cheaper."),
    "bracketed span": lambda t: extract_quant_checks("War Communism lasted about five years (" + t, request_id="r", claim_id="c"),
    "named event": lambda t: extract_quant_checks(A.QUAKE_DATED + "About seven months after Darfield" + t + ", on 22 February 2011, x.",
                                                  request_id="r", claim_id="c"),
    "named event (lookup)": lambda t: extract_quant_checks("Darfield " + t + " on 4 September 2010.\n\nAbout seven months after Darfield, on 22 "
                                                           "February 2011, x.", request_id="r", claim_id="c"),
    "chronology": lambda t: chronology_relations("About seven months after " + t),
    "ratio": lambda t: _ratio_findings("c", "Catch per boat " + t, supplied_tables([doc(A.FISHERY_DOC)])),
    "credited stem": lambda t: _stem_noun_findings("c", "the firm's own figures: " + t, [doc(A.TOY_CASE_DOC)]),
    "credited stem (text)": lambda t: _stem_noun_findings("c", "the case says 32 employees", [SuppliedText(document_id="d", text="employs " + t)]),
}


@pytest.mark.parametrize("reader", sorted(READERS))
def test_the_c3_arithmetic_readers_stay_linear_on_every_hostile_input(reader):
    fn = READERS[reader]
    for name, text in {**all_inputs(), **word_runs()}.items():  # the joined word runs since round 10 (stricter)
        elapsed, error = bounded(fn, text)
        assert error is None, (reader, name, error)
        assert elapsed < 5.0, (reader, name, elapsed)


#: Words that bring the party readers into the state that reads a joined word run after them ('X alone received', a share's party).
PARTY_PREFIXES = {"after an alone": ("Kenya alone received 5% and ", " alone had 3%."),
                  "as a share's party": ("The ", " alone received about two-thirds of the total.")}


def test_the_quantitative_entry_points_read_joined_word_runs_in_linear_time():
    """The round-10 sweep of joined word runs (input stall, quadratic): the party name of 'X alone received' and of a share's party was
    read again from each letter of a joined token ('A-A-A...', "A'A'A..."): 9 to 12 s per call at 20,000 characters for
    extract_quant_checks, undecided_quant_statements and the generic parser with its packs. Each name word is now read once and is at most
    41 characters long; the names themselves read as before."""
    from epinoic_logic.adapters.base import AdapterError
    from epinoic_logic.branches import packs, quant as q, worked as w
    from epinoic_logic.branches.generic_parser import GenericTextParser
    from ..adapters.hostile_inputs import WORD_RUNS
    from ..timing import empty_caches

    def parse_and_check(text):
        report = GenericTextParser("economics-specialist").parse_response(text, request_id="q", task_id="t", report_id="r", subject="Economics",
                                                                          task_type="essay")
        for pack in (packs.CorePack(), packs.EconomicsPack(), packs.BusinessPack(), packs.PsychologyPack(), packs.GenericPack()):
            pack.checks(report, request_text=text[:2000])
            pack.formal_checks(report)
    entries = {"extract_quant_checks": lambda t: extract_quant_checks(t, request_id="r", claim_id="c"),
               "undecided_quant_statements": undecided_quant_statements,
               "worked_problems": lambda t: w.worked_problems(t, report_id="r", request_id="q", prefix="c")}
    inputs = dict(word_runs())
    inputs.update({f"{run} {where}": before + text + after for where, (before, after) in PARTY_PREFIXES.items() for run, text in WORD_RUNS.items()})
    for label, text in inputs.items():
        for name, fn in entries.items():
            empty_caches()
            elapsed, error = bounded(fn, text)
            assert error is None and elapsed < 3.0, (name, label, error, elapsed)
        empty_caches()
        elapsed, error = bounded(parse_and_check, text)
        assert (error is None or isinstance(error, AdapterError)) and elapsed < 10.0, ("parse and pack checks", label, error, elapsed)
    assert q._ALONE_RE.search("In 1882 the United Kingdom of Great Britain alone received $3.2 billion.").group("who") == "United Kingdom of Great Britain"
    assert q._SHARE_PARTY_RE.search("so the United Kingdom alone received").group("who") == "the United Kingdom"
    assert [m.group(1) for m in packs._UNSUPPLIED_WORK_RE.finditer("Thomas Hardy's speaker admits it, and O'Brien's poem and Anglo-Irish's "
                                                                    "text too.")] == ["Thomas Hardy", "O'Brien", "Anglo-Irish"]


def test_ec_t16_a_bracketed_pair_with_a_currency_prefix_is_read_and_named_by_its_pair():
    """Minor (c2 bug 20 in a new shape): ec-t16 g11.8 '... the price rose 33.95% in nominal terms (P$2,150 to P$2,880) ...' drew CORE-QNT-001
    'its sentence states no pair of figures it can be read against (only $2,150, $2,880, 0.47%)'. The pair in brackets is read, with the
    currency prefix 'P$', by the quant reader and by the prose reader, and decides the stated per cent either way."""
    right = ("Weigh it: the table holds no cost data, so profit cannot be judged; the price rose 33.95% in nominal terms (P$2,150 to P$2,880), "
             "with no inflation figure to deflate it.")
    assert not undecided_quant_statements(right)
    assert quant_statuses(right) == [("percent_change", "ENTAILED")]
    assert [s for _p, s in prose_statuses(right)] == ["ENTAILED"]
    wrong = right.replace("33.95%", "43.95%")
    assert quant_statuses(wrong) == [("percent_change", "COUNTEREXAMPLE")]
    assert [s for _p, s in prose_statuses(wrong)] == ["COUNTEREXAMPLE"]


def test_repeated_named_lengths_and_ratio_phrases_stay_linear():
    """A text of many lengths after one named event looks the name up once per text, not once per sentence, and a clause of many 'A per
    B' phrases reads its figures once (both were k² readings of a hostile text before they were bounded)."""
    import time
    text = "Darfield struck on 4 September 2010.\n\n" + " ".join("Two months after Darfield, on 1 May 2011, an aftershock struck." for _ in range(2000))
    t = time.perf_counter()
    checks = extract_quant_checks(text, request_id="r", claim_id="c")
    assert time.perf_counter() - t < 10.0 and len(checks) == 2000
    tables = supplied_tables([doc(A.FISHERY_DOC)])
    t = time.perf_counter()
    found = _ratio_findings("c", "Catch per boat " * 2000 + "rose to 125.0 tonnes in 2019.", tables)
    assert time.perf_counter() - t < 2.0 and found and {r.figure.shown for r in found} == {"125.0"}
