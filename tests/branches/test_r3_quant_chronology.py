"""Round-3 overseer regressions for the core pack and the shared extractors: the
arithmetic check reads noun phrases after a unit, trillion scales, thousands separators
and word folds, year ranges, figures in words and signed changes, never a bare number
against a scaled one, and one abbreviation-aware sentence splitter; chronology carries
the day, decides year-only and day-month tokens from the sentence or paragraph year, and
reports an equal month or year as undecided; a reporting clause credits the outer speaker
and two named sources make a wrong credit a warning naming both; an uncredited quotation
that no supplied text holds is CORE-SRC-003, not an invented-quotation error; the History
structural source check uses the channel's own tiers so it never contradicts INT-REQ-010."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist.chronology import chronology_relations
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter, chronology_findings_in
from epinoic_logic.adapters.history_specialist.sentences import split_clauses, split_sentences, strip_json_spans
from epinoic_logic.adapters.history_specialist.structural import structural_checks
from epinoic_logic.branches import RouterHub, extract_quant_checks
from epinoic_logic.branches.packs import CorePack, HistoryPack
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

KEY = b"packs-r3-regression-key-0123456789ab"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
BODY = ("The Depression was responsible for the Nazi electoral rise because it destroyed the economic security of groups that had voted "
        "for moderate parties in 1928. The strongest counter-case is that the vote fell to 33.1 per cent in November 1932. "
        "By the criterion of what made the breakthrough possible, the Depression carries the greater weight.")
LABEL = "\n\nDates and figures are from memory; verify them against your notes before use."
CUBA = ("Khrushchev's decision of 28 October 1962 to dismantle the missiles ended the crisis, so the resolution was to a large extent his. "
        "After the U-2 photographs of 14 October showed missile sites under construction in Cuba, Khrushchev offered on 26 October to remove them in exchange for a pledge. "
        "The counter-case is that American pressure alone forced the retreat. Weighed by decisiveness, the answer is Khrushchev.")
POEM_TEXT = "The river carries the charter of the town, and every face I meet bears marks of weakness, marks of woe; the chapel wall is blackened by the sweep's cry."
PEER_TEXT = ("The poet presents the city's institutions as human constructions that bind the people beneath them. The adjective charter'd is applied to the "
             "street and then to the river, so the legal order reaches both the streets and the river. The chapel is itself darkened by the soot of the sweep's trade.")
POEM = SuppliedText(document_id="doc-town", title="The Town (poem, supplied text)", author="Thomas Fielding", text=POEM_TEXT)
PEER = SuppliedText(document_id="peer:en-p2", title="english-specialist report relayed through the hub", author="english-specialist", text=PEER_TEXT)


def status(problem) -> str:
    return verify(problem, CFG).status.value


def statuses(sentence: str) -> list[tuple[str, str]]:
    return [(c.kind, status(c.problem)) for c in extract_quant_checks(sentence, request_id="r", claim_id="c")]


def history_report(text: str, rid: str = "rep", texts=()) -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id=rid, supplied_texts=list(texts))


def through_hub(text: str, question: str = "To what extent was the Depression responsible? Write one body paragraph only, in no more than 350 words.", texts=()):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["history-specialist"],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", "history-specialist", question, list(texts))
    return hub.receive("t", m.message_id, text, agent_id="history-specialist", report_id="rep-x")


# ------------------------------------------------------------------ quant: noun phrases, scales, folds, ranges, words, signs


@pytest.mark.parametrize("sentence,kind,expected", [
    ("Lending rose from 800 million gold marks in 1924 to 1.2 billion gold marks in 1928, a rise of 25 per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("Lending rose from 800 million gold marks in 1924 to 1.2 billion gold marks in 1928, a rise of 50 per cent.", "percent_change", "ENTAILED"),
    ("Enrolment rose from 200 students in 1920 to 260 students in 1925, an increase of 45 per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("Enrolment rose from 200 students in 1920 to 260 students in 1925, an increase of 30 per cent.", "percent_change", "ENTAILED"),
    ("Membership fell from 6 per cent of members in September 1923 to 3 per cent in 1924, a fall of 3 percentage points.", "points_change", "ENTAILED"),
    ("Membership fell from 6 per cent of members in September 1923 to 3 per cent in 1924, a fall of 5 percentage points.", "points_change", "COUNTEREXAMPLE"),
    ("The mark fell from 4 billion to 4 trillion marks, a thousandfold rise.", "fold_change", "ENTAILED"),
    ("The mark fell from 4 billion to 4 trillion marks, a hundredfold rise.", "fold_change", "COUNTEREXAMPLE"),
    ("The debt rose from 2 tn to 4 trn marks, doubling.", "fold_change", "ENTAILED"),
    ("Prices rose from 1 to 1,000 marks, a 1,000-fold rise.", "fold_change", "ENTAILED"),
    ("Prices rose from 1 to 1,000 marks, a 100-fold rise.", "fold_change", "COUNTEREXAMPLE"),
    ("Output rose from 100 million tonnes in 1923-24 to 120 million in 1925-26, a rise of 20 per cent.", "percent_change", "ENTAILED"),
    ("Output rose from 100 million tonnes in 1923-24 to 120 million in 1925-26, a rise of 50 per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("Output fell from c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 25 per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("Output fell from c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 50 per cent.", "percent_change", "ENTAILED"),
    ("Enrolment rose from two hundred to two hundred and sixty students, an increase of forty-five per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("Enrolment rose from two hundred to two hundred and sixty students, an increase of thirty per cent.", "percent_change", "ENTAILED"),
    ("Unemployment rose from about 1.4 million in 1928 to more than six million by early 1932, a rise of 329 per cent.", "percent_change", "ENTAILED"),
    ("Revenue rose from 100 to 90, a rise of -10 per cent.", "percent_change", "ENTAILED"),
    ("Revenue rose from 100 to 90, a rise of -20 per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("The share fell from 37.3 per cent in July 1932 to 33.1 in November 1932, a fall of 4.2 percentage points.", "points_change", "ENTAILED"),
])
def test_noun_phrases_scales_folds_ranges_words_and_signs_are_checked(sentence, kind, expected):
    assert statuses(sentence) == [(kind, expected)], sentence


def test_a_pair_whose_units_cannot_be_compared_is_skipped_never_read_as_a_bare_number():
    assert extract_quant_checks("Reserves rose from 4 billion to 4 lakh marks, a rise of 50 per cent.", request_id="r", claim_id="c") == []
    assert extract_quant_checks("Output rose from 1.4 million to 25 per cent, a rise of 50 per cent.", request_id="r", claim_id="c") == []
    assert extract_quant_checks("Unemployment saw a rise of 30 per cent from 1928 to 1930 among industrial workers.", request_id="r", claim_id="c") == []
    _, rc = through_hub(BODY + LABEL + " Reserves rose from 4 billion to 4 lakh marks, a rise of 50 per cent.")
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001"] and not [fc for fc in rc.formal_checks if fc.constraint_id.startswith("core-quant")]


def test_wrong_arithmetic_behind_a_noun_unit_and_a_circa_figure_reaches_the_router_as_an_error():
    _, rc = through_hub(BODY + LABEL + " Lending rose from 800 million gold marks in 1924 to 1.2 billion gold marks in 1928, a rise of 25 per cent.")
    assert any(f.code == "INT-SUBJ-001" and "25 per cent" in f.message for f in rc.errors)
    _, rc2 = through_hub(BODY + LABEL + " Output fell from c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 25 per cent. The fall mattered.")
    assert any(f.code == "INT-SUBJ-001" and "c. 200 million" in f.message for f in rc2.errors)
    rep = history_report(BODY + LABEL + " Output fell from c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 25 per cent. The fall mattered.")
    assert any(c.claim_text.startswith("Output fell from c. 200 million tonnes in 1928 to c. 100 million") for c in rep.claims)
    assert not any(c.claim_text == "Output fell from c." for c in rep.claims)


# ------------------------------------------------------------------ the shared sentence splitter


def test_shared_splitter_keeps_abbreviations_initials_and_quotations_together():
    text = "Output fell from c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 25 per cent. A. J. P. Taylor saw vol. 2, p. 14 and approx. 200 cases. It ends with a quote \"like this.\" Then she left."
    assert split_sentences(text) == ["Output fell from c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 25 per cent.",
                                     "A. J. P. Taylor saw vol. 2, p. 14 and approx. 200 cases.", 'It ends with a quote "like this."', "Then she left."]
    assert split_clauses("Prices rose in March 1930; the budget fell after the vote of July 1930. The end came in 1933.") == ["Prices rose in March 1930;", "the budget fell after the vote of July 1930.", "The end came in 1933."]
    glued = 'The vote fell. {"status": "ACCEPTED", "codes": []} The narrator insists that "the river carried every secret".'
    assert split_sentences(glued) == ["The vote fell.", '{"status": "ACCEPTED", "codes": []}', 'The narrator insists that "the river carried every secret".']
    assert strip_json_spans(glued)[0].split() == "The vote fell. The narrator insists that \"the river carried every secret\".".split()
    assert strip_json_spans("The Act [1788] stands. {not json} x") == ("The Act [1788] stands. {not json} x", 0)


# ------------------------------------------------------------------ chronology: days, year-only, day-month, undecided ties


@pytest.mark.parametrize("sentence,expected", [
    ("The broadcast of 28 October 1962 came after his first letter of 26 October 1962.", "ENTAILED"),
    ("His first letter of 26 October 1962 came after the broadcast of 28 October 1962.", "COUNTEREXAMPLE"),
    ("After the U-2 photographs of 14 October 1962 showed missile sites under construction in Cuba, Khrushchev offered on 26 October 1962 to remove them.", "ENTAILED"),
    ("After the U-2 photographs of 26 October 1962 showed missile sites under construction in Cuba, Khrushchev offered on 14 October 1962 to remove them.", "COUNTEREXAMPLE"),
    ("The letter of c. 16 October 1962 came after the U-2 flight of 14 October 1962.", "ENTAILED"),
    ("The Chimney Sweepers Act of 1788 came after Pott's finding of 1775.", "ENTAILED"),
    ("Pott's finding of 1775 came after the Act of 1788.", "COUNTEREXAMPLE"),
    ("The decree of October 14, 1962 followed the flight of October 12, 1962.", "ENTAILED"),
])
def test_same_month_day_level_year_only_and_circa_dates_are_decided(sentence, expected):
    rep = history_report("The point stands in 1962. " + sentence)
    formal = [c for c in CorePack().formal_checks(rep) if c.kind == "chronology"]
    assert [status(c.problem) for c in formal] == [expected]
    assert (chronology_findings_in(sentence) is not None) == (expected == "COUNTEREXAMPLE")
    assert not [x for x in CorePack().checks(rep) if x.code == "CORE-CHR-001"]


@pytest.mark.parametrize("sentence,reason_part", [
    ("The broadcast of October 1962 came after his first letter of October 1962.", "day of"),
    ("The Act of 1788 came after the finding of March 1788.", "states only a year"),
    ("The vote of 1932 came after the reform of 1932.", "states only a year"),
    ("The second letter of 27 October 1962 came after the first letter of 27 October 1962.", "within the day"),
])
def test_an_equal_month_or_year_is_undecided_not_violated(sentence, reason_part):
    rels = chronology_relations(sentence)
    assert len(rels) == 1 and not rels[0].decided and not rels[0].violated and reason_part in rels[0].reason
    rep = history_report("The point stands. " + sentence)
    assert not [c for c in CorePack().formal_checks(rep) if c.kind == "chronology"]
    f = [x for x in CorePack().checks(rep) if x.code == "CORE-CHR-001"]
    assert len(f) == 1 and f[0].severity == "warning" and "could not be decided" in f[0].message and f[0].claim_ids == ["h1.2"]
    _, rc = through_hub(BODY + LABEL + " " + sentence)
    assert not [x for x in rc.findings if x.code == "INT-SUBJ-001"] and not [sf for sf in rc.structural_findings if sf.code == "HI-CHR-001"]
    assert any(sf.code == "CORE-CHR-001" for sf in rc.structural_findings)


def test_day_month_dates_take_the_year_from_the_sentence_or_paragraph_when_unambiguous():
    with_year = "After the U-2 photographs of 14 October showed missile sites in Cuba, Khrushchev offered on 26 October 1962 to remove them."
    rels = chronology_relations(with_year)
    assert len(rels) == 1 and rels[0].decided and not rels[0].violated and "1962" in rels[0].reason
    rep = history_report(CUBA)
    formal = [c for c in CorePack().formal_checks(rep) if c.kind == "chronology"]
    assert len(formal) == 1 and status(formal[0].problem) == "ENTAILED" and "paragraph" in formal[0].problem.conclusion.label
    assert not [x for x in CorePack().checks(rep) if x.code == "CORE-CHR-001"]
    reversed_cuba = CUBA.replace("photographs of 14 October", "photographs of 26 October").replace("offered on 26 October", "offered on 14 October")
    rep2 = history_report(reversed_cuba, "rev")
    formal2 = [c for c in CorePack().formal_checks(rep2) if c.kind == "chronology"]
    assert len(formal2) == 1 and status(formal2[0].problem) == "COUNTEREXAMPLE"
    assert any(f.code == "HI-CHR-001" and "14 October 1962" in f.message for f in structural_checks(rep2))
    _, rc = through_hub(reversed_cuba, "To what extent was the crisis resolved by Khrushchev? Write one body paragraph only.")
    assert any(f.code == "INT-SUBJ-001" for f in rc.errors) and any(sf.code == "HI-CHR-001" for sf in rc.structural_findings)
    _, ok = through_hub(CUBA, "To what extent was the crisis resolved by Khrushchev? Write one body paragraph only.")
    assert not ok.errors and not [sf for sf in ok.structural_findings if sf.code == "HI-CHR-001"]
    # no year anywhere, or two different years in the sentence: undecided with the reason
    alone = "After the U-2 photographs of 14 October showed missile sites, Khrushchev offered on 26 October to remove them."
    assert [(r.decided, "carries a year" in r.reason) for r in chronology_relations(alone)] == [(False, True)]
    two_years = "The treaty of 1919 framed it: after the vote of 14 October, the Act passed on 26 October, as the 1920 report said."
    rels = chronology_relations(two_years)
    assert len(rels) == 1 and not rels[0].decided and "2 different years" in rels[0].reason


HI_T5 = ("Khrushchev's decision of 28 October 1962 to dismantle the missiles ended the crisis, so the resolution was to a large extent his; but the terms that made the "
         "decision acceptable at home, above all a secret American assurance, were Kennedy's. After the U-2 photographs of 14 October showed missile sites under construction "
         "in Cuba, Khrushchev offered on 26 October to remove them in exchange for a pledge that the United States would not invade Cuba. The counter-case is that American "
         "pressure alone forced the retreat; Robert Kennedy's memoir Thirteen Days (1969), written by a participant, gives that assurance a central place. "
         "Weighed by decisiveness, the answer is Khrushchev. Dates and figures are from memory; verify them against your notes before use.")


def test_a_possessive_before_the_full_stop_ends_the_sentence_and_the_paragraphs_dated_year_is_used():
    sentences = split_sentences(HI_T5)
    assert sentences[1].startswith("After the U-2 photographs of 14 October") and sentences[0].endswith("were Kennedy's.")
    rep = history_report(HI_T5)
    assert any(c.claim_text.startswith("After the U-2 photographs") for c in rep.claims)
    formal = [c for c in CorePack().formal_checks(rep) if c.kind == "chronology"]
    assert len(formal) == 1 and status(formal[0].problem) == "ENTAILED" and "dated events" in formal[0].problem.conclusion.label  # 1962, not the memoir's 1969
    assert not [x for x in CorePack().checks(rep) if x.code == "CORE-CHR-001"]
    rels = chronology_relations(sentences[1], HI_T5)
    assert len(rels) == 1 and rels[0].decided and "26 October 1962" in rels[0].later_text and "14 October 1962" in rels[0].earlier_text
    reversed_t5 = HI_T5.replace("photographs of 14 October", "photographs of 26 October").replace("offered on 26 October", "offered on 14 October")
    assert any(f.code == "HI-CHR-001" for f in structural_checks(history_report(reversed_t5, "rev")))
    _, rc = through_hub(reversed_t5, "To what extent was the crisis resolved by Khrushchev? Write one body paragraph only.")
    assert any(f.code == "INT-SUBJ-001" for f in rc.errors)


def test_called_is_a_summons_not_the_subjects_occurrence():
    sentence = "The plenum, which had been called in June 1959, met after the harvest of October 1959."
    rels = chronology_relations(sentence)
    assert len(rels) == 1 and not rels[0].decided and "aside about the subject" in rels[0].reason
    assert chronology_findings_in(sentence) is None
    _, rc = through_hub(BODY + LABEL + " " + sentence)
    assert not [x for x in rc.findings if x.code == "INT-SUBJ-001"] and any(sf.code == "CORE-CHR-001" for sf in rc.structural_findings)
    met = "The plenum, which met in July 1959, came after the harvest of October 1959."
    assert chronology_findings_in(met) is not None  # an occurrence verb still makes the aside's date the subject's date


# ------------------------------------------------------------------ CORE-SRC-005: outer speaker and two named sources


def english_report(text: str, texts=(POEM, PEER)) -> SpecialistReport:
    claim = ClaimRecord(request_id="r", task_id="t", report_id="rep-e", agent_id="english-specialist", subject="English A: Literature", task_type="analytical_paragraph", claim_id="e1", claim_text=text[:4000], claim_role="point")
    return SpecialistReport(report_id="rep-e", request_id="r", task_id="t", agent_id="english-specialist", subject="English A: Literature", task_type="analytical_paragraph",
                            original_response=text, response_sha256=sha256_text(text), supplied_texts=list(texts), claims=[claim], created_at="2026-10-11T14:00:00Z")


def src005(text: str, texts=(POEM, PEER)):
    return [f for f in CorePack().checks(english_report(text, texts)) if f.code == "CORE-SRC-005"]


def test_a_reporting_clause_credits_the_outer_speaker_not_the_inner_subject():
    assert src005('The English specialist argues that Fielding presents the city\'s institutions as "human constructions that bind the people beneath them".') == []
    assert src005('The English specialist notes that the poem makes "the legal order reaches both the streets and the river" a legal fact.') == []
    # a genuine wrong credit with one named source stays an error naming both documents
    f = src005('Fielding writes of "human constructions that bind the people beneath them".')
    assert len(f) == 1 and f[0].severity == "error" and "Thomas Fielding (doc-town)" in f[0].message and "occurs only in peer:en-p2" in f[0].message
    f = src005('The English specialist writes of "marks of weakness, marks of woe" in every face.')
    assert len(f) == 1 and f[0].severity == "error" and "occurs only in doc-town" in f[0].message


def test_two_sources_named_before_a_quotation_make_a_wrong_credit_a_warning_naming_both():
    # the last-named source carries the saying verb and so the credit, but the other source named before the quotation holds the words
    ambiguous = 'The English specialist, unlike Fielding, describes "human constructions that bind the people beneath them".'
    f = src005(ambiguous)
    assert len(f) == 1 and f[0].severity == "warning" and "ambiguous" in f[0].message
    assert "Thomas Fielding (doc-town)" in f[0].message and "the english specialist (peer:en-p2)" in f[0].message
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="English A: Literature", task_type="analytical_paragraph", selected_agent_ids=["english-specialist"], allowed_document_ids=["doc-town", "peer:en-p2"]))
    m, _, _ = hub.dispatch("t", "english-specialist", "Analyse the poem against the History specialist's context. Quote exactly.", [POEM, PEER])
    _, rc = hub.receive("t", m.message_id, english_report(ambiguous))
    assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS and not any(f.code == "INT-SUBJ-003" and "CORE-SRC-005" in f.message for f in rc.errors)
    assert any(sf.code == "CORE-SRC-005" and sf.severity == "warning" for sf in rc.structural_findings)


# ------------------------------------------------------------------ CORE-SRC-003 with texts supplied; HI-SRC-001 tiers


SLOGAN = 'The established Church inspired fierce loyalty; in July 1791 "Church and King" crowds burned the house of the dissenter Joseph Priestley (from memory).'
OUTLINE = "In one paragraph of no more than 220 words, outline for a literature student the historical context of the institutions the English specialist identifies, with dated evidence labelled from memory. Where you draw on the English specialist's paragraph, quote it exactly and attribute it to the English specialist."


ANSWER = ('The English specialist argues that the poet presents the city\'s institutions as "human constructions that bind the people beneath them". '
          "The East India Company held its trading monopoly under a royal charter from 1600, and Parliament renewed that charter in 1793 (from memory). "
          + SLOGAN + " The Crown fought France from 1793 and the established Church stood with it.")


def test_uncredited_quotation_held_by_no_text_is_core_src_003_not_an_invented_quotation_error():
    rep = history_report(ANSWER, texts=(PEER,))
    slogan = next(c for c in rep.claims if "Church and King" in c.claim_text)
    assert slogan.source_refs == [] and any(a.startswith('quotation with no supplied text to check it against: "Church and King"') for a in slogan.assumptions)
    f = [x for x in CorePack().checks(rep) if x.code == "CORE-SRC-003"]
    assert len(f) == 1 and f[0].severity == "info" and "Church and King" in f[0].message and f[0].claim_ids == [slogan.claim_id] and "peer:en-p2" in f[0].message
    reply, rc = through_hub(ANSWER, OUTLINE, texts=(PEER,))
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    assert not [f for f in rc.errors if f.code in ("INT-REQ-003", "INT-SUBJ-003")], [f.model_dump() for f in rc.errors]
    assert any(sf.code == "CORE-SRC-003" and sf.severity == "info" for sf in rc.structural_findings)
    assert not any(sf.code == "HI-SRC-001" for sf in rc.structural_findings) and not any(sf.code == "CORE-SRC-005" for sf in rc.structural_findings)
    delivered = next(c for c in reply.payload["claims"] if "Church and King" in c["claim_text"])
    assert delivered["source_refs"] == []  # no invented reference to the peer leaves the hub
    # without the from-memory label the same quotation is a warning
    plain = history_report('The East India Company held its charter from 1600. In July 1791 "Church and King" crowds burned the house of Joseph Priestley.', "p", texts=(PEER,))
    f = [x for x in CorePack().checks(plain) if x.code == "CORE-SRC-003"]
    assert len(f) == 1 and f[0].severity == "warning"


def test_named_but_missing_credit_stays_an_error_and_a_form_difference_is_a_warning_on_both_sides():
    # credited to the peer by name, found nowhere: INT-REQ-003 from the channel, HI-SRC-001 error naming the excerpt and the texts searched
    missing = 'The English specialist writes that "the river carried every secret of the town". The charter dates from 1600 (from memory).'
    rep = history_report(missing, texts=(PEER,))
    assert rep.claims[0].source_refs[0].document_id == "peer:en-p2" and any("found in none of the supplied texts [peer:en-p2]" in a for a in rep.claims[0].assumptions)
    hi = [f for f in structural_checks(rep) if f.code == "HI-SRC-001"]
    assert len(hi) == 1 and hi[0].severity == "error" and "the river carried every secret of the town" in hi[0].message and "searched: peer:en-p2" in hi[0].message
    _, rc = through_hub(missing, OUTLINE, texts=(PEER,))
    assert any(f.code == "INT-REQ-003" and "h1.1" in f.claim_ids for f in rc.errors)
    # the words occur but the quotation differs only in its initial capital: INT-REQ-010 warning and HI-SRC-001 warning, no error at all
    form = 'The English specialist writes that "The legal order reaches both the streets and the river". The charter dates from 1600 (from memory).'
    rep2 = history_report(form, "f", texts=(PEER,))
    hi2 = [f for f in structural_checks(rep2) if f.code == "HI-SRC-001"]
    assert len(hi2) == 1 and hi2[0].severity == "warning" and "different form" in hi2[0].message and "initial capital" in hi2[0].message
    _, rc2 = through_hub(form, OUTLINE, texts=(PEER,))
    assert any(f.code == "INT-REQ-010" for f in rc2.findings) and not rc2.errors
    assert not [sf for sf in rc2.structural_findings if sf.severity == "error"]


# ------------------------------------------------------------------ HI-STR-001 from the parsed roles


HI_T6 = ("Two economic consequences mattered: a redistribution of wealth, and a dependence on foreign credit that followed stabilisation. "
         "From memory, the mark stood at about 4.2 to the dollar before the war, near 18,000 in January 1923 and about 4.2 trillion by mid-November 1923, "
         "when the Rentenmark was introduced at one new mark for a trillion old ones (from memory; check your notes). "
         "Stabilisation was followed by the Dawes Plan of 1924, whose foreign loans, from memory about 800 million gold marks, tied recovery to American credit that could be withdrawn. "
         "The redistribution mattered most, by the criteria of directness, reach and permanence: it was the direct product of the inflation rather than of the policies used to end it. "
         "The dependence shaped the late 1920s, but it was created by stabilisation, not by the inflation.")


def test_hi_str_001_is_decided_from_the_parsed_roles_and_accepts_criteria():
    for text in (HI_T6, HI_T6.replace("by the criteria of", "by the criterion of"), HI_T6.replace("by the criteria of", "measured by")):
        rep = history_report(text)
        assert any(c.claim_role == "judgement" and c.claim_text.startswith("The redistribution mattered most") for c in rep.claims)
        assert not [f for f in structural_checks(rep) if f.code == "HI-STR-001"], text[:40]
    verdict = "Outline the economic consequences. Write no more than 200 words and give a judgement on which consequence mattered most."
    assert not [f for f in HistoryPack().checks(history_report(HI_T6), verdict) if f.code == "HI-STR-001"]
    # a weighed counter-case without a criterion phrase also counts; a bare verdict with neither does not
    assert not [f for f in structural_checks(history_report(CUBA)) if f.code == "HI-STR-001"]
    bare = "The Depression was decisive in 1930. The vote rose to 37.3 per cent in July 1932. Economic collapse was therefore responsible to a degree no other factor matched."
    assert [f.code for f in structural_checks(history_report(bare)) if f.code == "HI-STR-001"] == ["HI-STR-001"]
