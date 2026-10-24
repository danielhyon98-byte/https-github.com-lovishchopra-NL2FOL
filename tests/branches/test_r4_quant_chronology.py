"""Round-4 overseer regressions for the core pack's arithmetic and chronology checks: a bound
qualifier before an article and a fold word; no shared-unit elision onto a first figure with its
own noun; 'near', rate phrases and a circa before the year; every pair of a clause bound to its
own derived figure (', and', chained continuations, 'stood at ... and reached', 'X in D1 and Y
in D2', exchange rates, decimal commas, 'a change of'); relations stated across sentences read
against the paragraph's dated series or reported undecided (CORE-QNT-001); intransitive
'followed in <date>'; a second cue coordinated with a first orders the clause's subject; the cues
'earlier than', 'prior to', 'predated' and kin; an event named without a date looked up in the
paragraph; CORE-SRC-005 names only the misattributed quotation's claim and the sentence claim."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist.chronology import chronology_relations
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.adapters.history_specialist.structural import structural_checks
from epinoic_logic.branches import RouterHub, extract_quant_checks
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.branches.quant import undecided_quant_statements
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

KEY = b"packs-r4-regression-key-0123456789ab"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)

#: The round-4 History answers as the isolated specialist wrote them.
HI_T8 = ("The Wall Street Crash of October 1929 led American lenders to recall the short-term credit on which the Weimar economy depended, and registered "
         "unemployment then rose in each year that followed. Annual averages climbed from about 1.9 million in 1929 to 3.1 million in 1930, 4.5 million in 1931 "
         "and 5.6 million in 1932, peaking at about 6.1 million in February 1932 (figures from memory; check them against your notes). Brüning's deflationary "
         "decrees of December 1930 and June 1931 cut wages and benefits and deepened the fall in demand, while the collapse of the Danatbank on 13 July 1931 "
         "turned the slump into a banking crisis. The turning point was 1930. The annual average grew by roughly 60 per cent that year, the greatest proportional "
         "rise of the period, and the increase became a sustained mass crisis rather than a cyclical dip, which fed the political break of the September 1930 "
         "election. The strongest counter-case is 1932, the peak year, but a peak within a rising trend marks the height of the crisis rather than the point at "
         "which its direction changed, so by the criterion of when the trajectory altered it weighs less.")
HI_T8_Q = ("Outline, with dated and quantified evidence, the impact of the 1929 crash on unemployment in Germany between 1929 and 1932. Write no more than "
           "200 words and give a judgement on which year marked the turning point.")
HI_T7 = ("The Treaty of Versailles was a major but partial cause of the Weimar Republic's instability up to 1923. It supplied the grievance and fiscal burden "
         "that the republic's enemies and the 1923 crisis exploited, but the violence that began before the treaty was signed came mainly from domestic sources. "
         "Signed on 28 June 1919, the treaty took about 13 per cent of Germany's pre-war European territory and roughly a tenth of its population, limited the "
         "army to 100,000 men under Article 160, and under Article 231 placed responsibility for the war on Germany and its allies. The nationalist right used "
         "these terms to present the republic as the government that had accepted a diktat, so every concession became a humiliation. The reparations bill, "
         "fixed on 5 May 1921 at 132 billion gold marks, tied the state's finances to foreign transfers. The crisis came when deliveries fell into default: "
         "French and Belgian troops occupied the Ruhr on 11 January 1923, the government financed passive resistance by printing money, and by November 1923 "
         "one US dollar bought about 4.2 trillion marks. The occupation followed from the reparations regime, so the treaty did produce the crisis, but "
         "financing resistance by currency creation was a German decision. The strongest counter-case is that instability began before the treaty. The "
         "Spartacist rising of January 1919 and the Kapp Putsch of March 1920 came from the left and the right, and the murders of Matthias Erzberger in August "
         "1921 and Walther Rathenau in June 1922 were carried out by the far right, with courts lenient towards such killers. By the criterion of timing, the "
         "domestic sources come first and explain the early violence; by the criterion of scale, reparations were the largest recurring drain on public "
         "finances that the 1923 crisis exposed. The treaty was therefore a considerable cause of the republic's economic and fiscal weakness and a smaller "
         "cause of its early violence, so its responsibility for instability up to 1923 is real but partial.\n\n"
         "Dates and figures are from memory; verify them against your notes before use.")
HI_T7_Q = ("To what extent was the Treaty of Versailles responsible for the instability of the Weimar Republic up to 1923? Write one body paragraph only, "
           "following your method, in no more than 350 words, with dated and quantified evidence.")


def status(problem) -> str:
    return verify(problem, CFG).status.value


def statuses(text: str) -> list[tuple[str, str]]:
    return [(c.kind, status(c.problem)) for c in extract_quant_checks(text, request_id="r", claim_id="c")]


def history_report(text: str, rid: str = "rep") -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id=rid)


def through_hub(text: str, question: str = HI_T7_Q, task_type: str = "essay"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type=task_type, selected_agent_ids=["history-specialist"]))
    m, _, _ = hub.dispatch("t", "history-specialist", question)
    return hub.receive("t", m.message_id, text, agent_id="history-specialist", report_id="rep-x")


def chronology_statuses(text: str) -> list[str]:
    return [status(c.problem) for c in CorePack().formal_checks(history_report(text)) if c.kind == "chronology"]


# ------------------------------------------------------------------ quant: a qualifier, an article, a fold word


@pytest.mark.parametrize("sentence,expected", [
    ("Registered unemployment rose from 1.9 million registered unemployed in 1929 to 6.1 million registered unemployed in February 1932, more than a tripling.", "ENTAILED"),
    ("Registered unemployment rose from 1.9 million registered unemployed in 1929 to 5.1 million registered unemployed in February 1932, more than a tripling.", "COUNTEREXAMPLE"),
    ("Coal imports rose from 300,000 tons in 1700 to 1,000,000 tons in 1800, more than a threefold rise.", "ENTAILED"),
    ("Coal imports rose from 300,000 tons in 1700 to 800,000 tons in 1800, more than a threefold rise.", "COUNTEREXAMPLE"),
    ("Unemployment climbed from about 1.9 million in 1929 to 3.7 million in 1931, nearly a doubling.", "ENTAILED"),
    ("Unemployment climbed from about 1.9 million in 1929 to 5.6 million in 1932, nearly a doubling.", "COUNTEREXAMPLE"),
    ("Unemployment climbed from about 1.9 million in 1929 to 6.1 million in 1932, over a threefold rise.", "ENTAILED"),
])
def test_a_bound_qualifier_before_an_article_and_a_fold_word_keeps_its_side(sentence, expected):
    assert statuses(sentence) == [("fold_change", expected)], sentence
    side = extract_quant_checks(sentence, request_id="r", claim_id="c")[0].rule
    if sentence.endswith(("more than a tripling.", "more than a threefold rise.", "over a threefold rise.")):
        assert "lower bound" in side  # 'more than' makes the stated factor a lower bound, as for 'more than threefold'


# ------------------------------------------------------------------ quant: no elision onto a first figure with its own noun


def test_a_first_figure_with_its_own_noun_is_read_unscaled():
    trillion = "The dollar rose from about 4.2 marks in 1914 to about 4.2 trillion marks in November 1923, a trillionfold rise."
    assert statuses(trillion) == [("fold_change", "ENTAILED")]
    million = "The dollar rose from about 18,000 marks in January 1923 to about 4.2 trillion marks in November 1923, a more than millionfold rise."
    assert statuses(million) == [("fold_change", "ENTAILED")]
    wrong = "The dollar rose from about 18,000 marks in January 1923 to about 4.2 trillion marks in November 1923, a rise of roughly 200 per cent."
    [c] = extract_quant_checks(wrong, request_id="r", claim_id="c")
    assert status(c.problem) == "COUNTEREXAMPLE"
    before = next(p for p in c.problem.premises if p.id == "BEFORE")
    assert before.label == "before = 18,000 marks in January 1923" and before.expr.right.value == "18000"  # not 18,000 trillion
    # a bare first figure still takes the second figure's scale
    assert statuses("Estimates range from 15 to 45 million, a threefold spread.") == [("fold_change", "ENTAILED")]


# ------------------------------------------------------------------ quant: near, rate phrases, circa before the year


@pytest.mark.parametrize("sentence,kind,expected", [
    ("Unemployment rose from near 1.9 million in 1929 to near 6.1 million in 1932, a rise of 50 per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("Unemployment rose from near 1.9 million in 1929 to near 6.1 million in 1932, a rise of 221 per cent.", "percent_change", "ENTAILED"),
    ("Unemployment rose from close to 1.9 million in 1929 to just 2 million in 1930, a rise of 5 per cent.", "percent_change", "ENTAILED"),
    ("Coal shipments rose from roughly 500,000 tons a year in 1700 to roughly 1,000,000 tons a year in 1800, a tripling.", "fold_change", "COUNTEREXAMPLE"),
    ("Coal shipments rose from roughly 500,000 tons a year in 1700 to roughly 1,000,000 tons a year in 1800, a doubling.", "fold_change", "ENTAILED"),
    ("Coal shipments rose from roughly 500,000 tons by about 1700 to roughly 1,000,000 tons by about 1800, a tripling.", "fold_change", "COUNTEREXAMPLE"),
    ("Coal shipments rose from c. 500,000 tons in c. 1700 to c. 1,000,000 tons in c. 1800, a tripling.", "fold_change", "COUNTEREXAMPLE"),
    ("Coal shipments rose from c. 500,000 tons in c. 1700 to c. 1,000,000 tons in c. 1800, a doubling.", "fold_change", "ENTAILED"),
    ("Wages rose from 20 shillings per annum in 1790 to 30 shillings per annum in 1800, a rise of 50 per cent.", "percent_change", "ENTAILED"),
])
def test_near_rate_phrases_and_a_circa_before_the_year_are_read(sentence, kind, expected):
    assert statuses(sentence) == [(kind, expected)], sentence


# ------------------------------------------------------------------ quant: every pair of a clause, bound to its own derived figure


def test_every_from_to_pair_of_a_clause_is_checked_against_its_own_derived_figure():
    two = "Output rose from 100 in 1929 to 120 in 1930, a rise of 20 per cent, and exports rose from 50 in 1929 to 60 in 1930, a rise of 50 per cent."
    checks = extract_quant_checks(two, request_id="r", claim_id="c")
    assert [(c.kind, status(c.problem)) for c in checks] == [("percent_change", "ENTAILED"), ("percent_change", "COUNTEREXAMPLE")]
    assert checks[1].sentence.startswith("exports rose from 50") or "exports rose from 50" in checks[1].sentence  # the failing check names its own part
    folds = ("Unemployment roughly tripled from 1.9 million in 1929 to 5.6 million in 1932, and the number of welfare recipients quadrupled from 1.5 million "
             "in 1929 to 3 million in 1932.")
    assert statuses(folds) == [("fold_change", "ENTAILED"), ("fold_change", "COUNTEREXAMPLE")]
    fractions = ("Industrial production fell by a third from 100 in 1929 to 58 in 1932, and imports fell by about three-quarters from 13.4 billion marks in 1929 "
                 "to 4.7 billion in 1932.")
    assert statuses(fractions) == [("fraction_change", "COUNTEREXAMPLE"), ("fraction_change", "COUNTEREXAMPLE")]
    right = fractions.replace("by a third", "by about two-fifths").replace("three-quarters", "two-thirds")
    assert statuses(right) == [("fraction_change", "ENTAILED"), ("fraction_change", "ENTAILED")]


@pytest.mark.parametrize("sentence,expected", [
    ("Unemployment rose from 1.9 million in 1929 to 3.1 million in 1930, a rise of 63 per cent, before climbing to 5.6 million in 1932, a rise of 30 per cent.",
     [("percent_change", "ENTAILED"), ("percent_change", "COUNTEREXAMPLE")]),
    ("Unemployment rose from 1.9 million in 1929 to 3.1 million in 1930, a rise of 63 per cent, before climbing to 5.6 million in 1932, a rise of 81 per cent.",
     [("percent_change", "ENTAILED"), ("percent_change", "ENTAILED")]),
    ("Unemployment stood at 1.9 million in 1929 and reached 5.6 million in 1932, a rise of 95 per cent.", [("percent_change", "COUNTEREXAMPLE")]),
    ("Unemployment stood at 1.9 million in 1929 and reached 5.6 million in 1932, a rise of 195 per cent.", [("percent_change", "ENTAILED")]),
    ("One US dollar bought 4.2 marks in July 1914 and about 4.2 trillion marks in November 1923, a millionfold rise.", [("fold_change", "COUNTEREXAMPLE")]),
    ("One US dollar bought 4.2 marks in July 1914 and about 4.2 trillion marks in November 1923, a trillionfold rise.", [("fold_change", "ENTAILED")]),
    ("The mark fell from 4.2 to the dollar in July 1914 to 7,000 to the dollar in December 1922, a rise in the dollar's price of about 1,670-fold.", [("fold_change", "ENTAILED")]),
    ("The mark fell from 4.2 to the dollar in July 1914 to 7,000 to the dollar in December 1922, a rise in the dollar's price of about 100-fold.", [("fold_change", "COUNTEREXAMPLE")]),
    ("Unemployment rose from 1,9 million in 1929 to 3 million in 1930, a rise of 58 per cent.", [("percent_change", "ENTAILED")]),
    ("Unemployment rose from 1,9 million in 1929 to 3 million in 1930, a rise of 90 per cent.", [("percent_change", "COUNTEREXAMPLE")]),
    ("Wages stood from 100 in 1929 to 100 in 1930, a change of 0 per cent.", [("percent_change", "ENTAILED")]),
    ("Wages rose from 100 in 1929 to 120 in 1930, a change of 0 per cent.", [("percent_change", "COUNTEREXAMPLE")]),
    ("Wages fell from 100 in 1929 to 80 in 1930, a change of 20 per cent.", [("percent_change", "ENTAILED")]),
])
def test_chained_stood_reached_dated_and_rate_shapes_decimal_commas_and_a_change_of(sentence, expected):
    assert statuses(sentence) == expected, sentence


def test_a_derived_figure_that_cannot_be_bound_is_reported_undecided_not_skipped():
    for text, phrase in (("Reserves rose from 4 billion to 4 lakh marks, a rise of 50 per cent.", "a rise of 50 per cent"),
                         ("Prices fell by about a quarter.", "a quarter"),
                         ("Membership doubled in the decade.", "doubled")):
        assert extract_quant_checks(text, request_id="r", claim_id="c") == []
        undecided = undecided_quant_statements(text)
        assert len(undecided) == 1 and phrase in undecided[0].phrase, (text, undecided)
        rep = history_report("The point stands in 1930. " + text)
        found = [f for f in CorePack().checks(rep) if f.code == "CORE-QNT-001"]
        assert len(found) == 1 and found[0].severity == "warning" and "was not checked" in found[0].message and found[0].claim_ids == ["h1.2"]
    _, rc = through_hub(HI_T7 + " Reserves rose from 4 billion to 4 lakh marks, a rise of 50 per cent.")
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001"] and any(sf.code == "CORE-QNT-001" for sf in rc.structural_findings)


# ------------------------------------------------------------------ quant: relations stated across sentences (hi-t8)


def test_hi_t8_relations_across_sentences_are_read_against_the_paragraphs_dated_series():
    genuine = extract_quant_checks(HI_T8, request_id="r", claim_id="c")
    # round 5: the pair 'climbed from about 1.9 million in 1929 to ... 5.6 million in 1932' is also checked for its stated direction
    # (the overseers asked that a from/to pair under 'rose'/'fell' be decided); the three round-4 checks keep their order and verdicts
    assert [(c.kind, status(c.problem)) for c in genuine] == [("pair_direction", "ENTAILED"), ("series_monotonic", "ENTAILED"), ("percent_change", "ENTAILED"), ("series_extreme", "ENTAILED")]
    pct = genuine[2]
    assert "'that year' read as 1930" in pct.basis and "sentence 2" in pct.basis and "1.9 million in 1929" in pct.basis
    assert not undecided_quant_statements(HI_T8)
    cases = {
        "grew by roughly 90 per cent that year": (["percent_change"], HI_T8.replace("grew by roughly 60 per cent that year", "grew by roughly 90 per cent that year")),
        "1932 below 1931": (["series_monotonic"], HI_T8.replace("and 5.6 million in 1932", "and 4.2 million in 1932")),
        "1931 the larger rise": (["series_extreme"], HI_T8.replace("4.5 million in 1931", "5.5 million in 1931")),
        "1931 at 6.0 million (the overseer's probe)": (["series_monotonic", "series_extreme"], HI_T8.replace("4.5 million in 1931", "6.0 million in 1931")),
    }
    for name, (kinds, text) in cases.items():
        failed = [c.kind for c in extract_quant_checks(text, request_id="r", claim_id="c") if status(c.problem) == "COUNTEREXAMPLE"]
        assert failed == kinds, (name, failed)


def test_hi_t8_through_the_hub_cross_sentence_arithmetic_is_decided_and_a_wrong_figure_is_an_error():
    _, ok = through_hub(HI_T8, HI_T8_Q, "short_answer")
    quant = [fc for fc in ok.formal_checks if fc.constraint_id.startswith("core-quant")]
    # round 5: four checks, the pair's stated direction among them, all holding (round 4 pinned the three cross-sentence checks)
    assert len(quant) == 4 and all(fc.satisfied for fc in quant) and not [f for f in ok.findings if f.code == "INT-SUBJ-001"]
    assert sorted(fc.detail.split(" ")[0].split(":")[0] for fc in quant) == ["pair_direction", "percent_change", "series_extreme", "series_monotonic"]
    _, bad = through_hub(HI_T8.replace("grew by roughly 60 per cent that year", "grew by roughly 90 per cent that year"), HI_T8_Q, "short_answer")
    errors = [f for f in bad.findings if f.code == "INT-SUBJ-001"]
    assert errors and "90 per cent" in errors[0].message and "stated across sentences" in errors[0].message


def test_an_anaphor_with_two_candidate_years_or_no_series_is_undecided():
    ambiguous = HI_T8.replace("The turning point was 1930. ", "The turning point came between 1930 and 1931. ")
    assert "percent_change" not in [c.kind for c in extract_quant_checks(ambiguous, request_id="r", claim_id="c")]
    reasons = [u.reason for u in undecided_quant_statements(ambiguous)]
    assert any("could refer to 2 years" in r for r in reasons), reasons
    alone = "The vote fell in 1930. The annual average grew by roughly 60 per cent that year."
    [u] = undecided_quant_statements(alone)
    assert "no dated series" in u.reason or "state no year before" in u.reason


# ------------------------------------------------------------------ chronology: intransitive 'followed in <date>'


@pytest.mark.parametrize("sentence,expected", [
    ("After the murder of Rathenau in June 1922, the Law for the Protection of the Republic followed in July 1922.", "ENTAILED"),
    ("After the murder of Rathenau in July 1922, the Law for the Protection of the Republic followed in June 1922.", "COUNTEREXAMPLE"),
    ("After hyperinflation peaked in November 1923, stabilisation followed in 1924.", "ENTAILED"),
    ("After hyperinflation peaked in November 1924, stabilisation followed in 1923.", "COUNTEREXAMPLE"),
    ("After the Ruhr was occupied on 11 January 1923, passive resistance followed on 13 January 1923.", "ENTAILED"),
    ("After the Ruhr was occupied on 13 January 1923, passive resistance followed on 11 January 1923.", "COUNTEREXAMPLE"),
    ("The Ruhr was occupied in January 1923 and passive resistance followed in February 1923.", "ENTAILED"),
    ("The Ruhr was occupied in February 1923 and passive resistance followed in January 1923.", "COUNTEREXAMPLE"),
])
def test_followed_in_a_date_dates_its_own_subject(sentence, expected):
    assert chronology_statuses("The point stands. " + sentence) == [expected]
    rels = chronology_relations(sentence)
    assert len(rels) == 1 and rels[0].cue == "followed" and rels[0].violated == (expected == "COUNTEREXAMPLE")
    hi = [f for f in structural_checks(history_report("The point stands. " + sentence)) if f.code == "HI-CHR-001"]
    assert bool(hi) == (expected == "COUNTEREXAMPLE")


def test_followed_with_no_object_orders_its_subject_after_the_previous_sentences_one_date():
    text = "The Ruhr was occupied in January 1923. Passive resistance followed in February 1923."
    assert chronology_statuses(text) == ["ENTAILED"]
    assert chronology_statuses(text.replace("February 1923", "December 1922")) == ["COUNTEREXAMPLE"]
    # the previous sentence dates two events: which one is followed is not stated, so the order is undecided, never guessed
    two = "Hyperinflation peaked in November 1923 after the occupation of January 1923. Stabilisation followed in 1924."
    rels = chronology_relations("Stabilisation followed in 1924.", two)
    assert len(rels) == 1 and not rels[0].decided and "states 2 dates" in rels[0].reason
    assert any(f.code == "CORE-CHR-001" and f.claim_ids == ["h1.2"] for f in CorePack().checks(history_report(two)))
    # transitive uses keep their direction, and 'followed from' is a consequence, not an order
    assert chronology_statuses("The election of October 1932 followed the reform of March 1931.") == ["ENTAILED"]
    assert chronology_relations("The occupation followed from the reparations regime of May 1921.") == []


# ------------------------------------------------------------------ chronology: a second cue coordinated with the first


def test_a_cue_coordinated_with_a_first_orders_the_clause_subject_not_the_first_object():
    wrong = "The Ruhr was occupied in January 1923, after the London ultimatum of May 1921 and before the Dawes Plan of 1922."
    rels = chronology_relations(wrong)
    assert [(r.cue, r.later_text, r.earlier_text, r.violated) for r in rels] == [("after", "January 1923", "May 1921", False), ("before", "1922", "January 1923", True)]
    assert chronology_statuses("The point stands. " + wrong) == ["ENTAILED", "COUNTEREXAMPLE"]
    right = wrong.replace("Dawes Plan of 1922", "Dawes Plan of 1924")
    assert chronology_statuses("The point stands. " + right) == ["ENTAILED", "ENTAILED"]
    days = "The Danatbank closed on 13 July 1931, after the bank holiday of 12 July 1931 and before the Hoover Moratorium of 20 June 1931."
    assert [(r.later_text, r.earlier_text, r.violated) for r in chronology_relations(days)] == [("13 July 1931", "12 July 1931", False), ("20 June 1931", "13 July 1931", True)]
    _, rc = through_hub(HI_T7.replace("The occupation followed", "The Ruhr was occupied in January 1923, after the London ultimatum of May 1921 and before the Dawes Plan of 1922. The occupation followed"))
    assert any(f.code == "INT-SUBJ-001" and "Dawes" in f.message for f in rc.findings)
    # a subject with no date of its own: the coordinated cue is undecided, never paired with the first cue's object
    undated = chronology_relations("The Ruhr was occupied after the London ultimatum of May 1921 and before the Dawes Plan of 1922.")
    assert all(not r.decided or "1922" not in (r.later_text, r.earlier_text) for r in undated)


# ------------------------------------------------------------------ chronology: 'earlier than', 'prior to', 'predated' ...


@pytest.mark.parametrize("sentence,expected", [
    ("The occupation of the Ruhr in January 1923 came earlier than the Treaty of Rapallo of April 1922.", "COUNTEREXAMPLE"),
    ("The Treaty of Rapallo of April 1922 came earlier than the occupation of the Ruhr in January 1923.", "ENTAILED"),
    ("The occupation of the Ruhr in January 1923 came later than the Treaty of Rapallo of April 1922.", "ENTAILED"),
    ("Prior to the Treaty of Rapallo of April 1922, the Ruhr was occupied in January 1923.", "COUNTEREXAMPLE"),
    ("Prior to the Treaty of Rapallo of April 1922, the Genoa conference opened in March 1922.", "ENTAILED"),
    ("The Kapp Putsch of March 1920 came prior to the Treaty of Rapallo of April 1922.", "ENTAILED"),
    ("The Dawes Plan of 1924 predated the Young Plan of 1929.", "ENTAILED"),
    ("The Young Plan of 1929 predated the Dawes Plan of 1924.", "COUNTEREXAMPLE"),
    ("The Young Plan of 1929 postdated the Dawes Plan of 1924.", "ENTAILED"),
    ("The Locarno treaties of October 1925 came subsequent to the Dawes Plan of August 1924.", "ENTAILED"),
])
def test_earlier_than_prior_to_and_predated_are_ordering_cues(sentence, expected):
    assert chronology_statuses("The point stands. " + sentence) == [expected]


def test_no_later_than_is_a_bound_and_the_following_year_is_not_a_cue():
    assert chronology_relations("The Ruhr occupation of January 1923 came no later than the default of December 1922.") == []
    assert chronology_relations("In the following year, unemployment rose to 3.1 million in 1930.") == []


# ------------------------------------------------------------------ chronology: an event named without a date


def test_an_event_named_without_a_date_is_looked_up_in_the_paragraph():
    wrong = HI_T8.replace("which fed the political break of the September 1930 election.",
                          "which fed the political break of the September 1930 election. That election came after the Danatbank collapse of July 1931.")
    rels = [r for r in chronology_relations("That election came after the Danatbank collapse of July 1931.", wrong)]
    assert len(rels) == 1 and rels[0].decided and rels[0].violated and rels[0].later_text == "September 1930" and "another sentence" in rels[0].reason
    _, rc = through_hub(wrong, HI_T8_Q, "short_answer")
    assert any(f.code == "INT-SUBJ-001" and "September 1930" in f.message for f in rc.findings)
    right = wrong.replace("That election came after the Danatbank collapse of July 1931.", "That election came after the Young Plan referendum of December 1929.")
    _, ok = through_hub(right, HI_T8_Q, "short_answer")
    assert not [f for f in ok.findings if f.code == "INT-SUBJ-001"]


def test_hi_t7_counter_case_stated_across_sentences_is_reported_undecided():
    first = HI_T7.split("\n\n")[0]
    rels = chronology_relations("The strongest counter-case is that instability began before the treaty.", first)
    assert len(rels) == 1 and not rels[0].decided and "stated across sentences" in rels[0].reason and "28 June 1919" in rels[0].reason
    for text in (HI_T7, HI_T7.replace("The Spartacist rising of January 1919", "The Spartacist rising of January 1920")):
        rep = history_report(text)
        undecided = [f for f in CorePack().checks(rep) if f.code == "CORE-CHR-001"]
        assert any(f.claim_ids == ["h1.8"] for f in undecided), [f.message for f in undecided]
        assert not [c for c in CorePack().formal_checks(rep) if c.kind == "chronology"]
    # a modified noun elsewhere may be another event: 'the crisis' is not 'the agrarian crisis that began in 1928'
    para = ("The agrarian crisis that began in 1928 ruined farming communities. The Depression carries the greater weight, because the fall came only after "
            "the crisis had already made the Nazis the largest party.")
    assert chronology_relations(para.split(". ")[1], para) == []
    # an undated event beside a dated one in the same sentence still states no checkable order
    assert chronology_relations("Prices rose in March 1930; the budget fell after the vote of July 1930.") == []


# ------------------------------------------------------------------ CORE-SRC-005 names the misattributed quotation's claim only


def test_core_src_005_names_the_misattributed_quotation_and_the_sentence_claim_only():
    poem = SuppliedText(document_id="doc-wb", title="Composed upon Westminster Bridge", author="William Wordsworth",
                        text="Earth has not anything to show more fair. All bright and glittering in the smokeless air.")
    peer = SuppliedText(document_id="peer:hi-p3", title="history-specialist report relayed through the hub", author="history-specialist",
                        text="The Peace of Amiens, signed on 25 March 1802, was a lull rather than a settlement.")
    sentence = ('The History specialist writes that London lay "All bright and glittering in the smokeless air", that the peace of "25 March 1802" was '
                '"a lull rather than a settlement".')
    base = dict(request_id="r", task_id="t", report_id="rep-e", agent_id="english-specialist", subject="English A: Literature", task_type="analytical_paragraph")
    claims = [ClaimRecord(**base, claim_id="p1-q02", claim_text='"All bright and glittering in the smokeless air"', claim_role="evidence",
                          source_refs=[SourceRef(document_id="doc-wb", excerpt="All bright and glittering in the smokeless air")]),
              ClaimRecord(**base, claim_id="p1-q12", claim_text='"25 March 1802"', claim_role="evidence", source_refs=[SourceRef(document_id="peer:hi-p3", excerpt="25 March 1802")]),
              ClaimRecord(**base, claim_id="p1-q13", claim_text='"a lull rather than a settlement"', claim_role="evidence",
                          source_refs=[SourceRef(document_id="peer:hi-p3", excerpt="a lull rather than a settlement")]),
              ClaimRecord(**base, claim_id="p1-s07", claim_text=sentence, claim_role="analysis")]
    rep = SpecialistReport(report_id="rep-e", request_id="r", task_id="t", agent_id="english-specialist", subject="English A: Literature", task_type="analytical_paragraph",
                           original_response=sentence, response_sha256=sha256_text(sentence), supplied_texts=[poem, peer], claims=claims, created_at="2026-10-11T18:00:00Z")
    found = [f for f in CorePack().checks(rep) if f.code == "CORE-SRC-005"]
    assert len(found) == 1 and found[0].severity == "error" and found[0].claim_ids == ["p1-q02", "p1-s07"]
