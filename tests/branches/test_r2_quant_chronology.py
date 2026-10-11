"""Round-2 overseer regressions for the core and subject packs: dated from/to pairs,
shared-unit elision, rates, word fractions and fold words are checked by the engine with a
tolerance band symmetric around the computed value; every after/before relation of a
sentence is decided (or reported undecided) by one extractor shared with HI-CHR-001;
quotations in single marks, guillemets and mixed marks are seen; a quotation credited to
the wrong supplied text is named; HI-STR-001 and ES-STR-002 yield to the request."""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.adapters.history_specialist.chronology import chronology_relations
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter, chronology_findings_in
from epinoic_logic.adapters.history_specialist.structural import structural_checks
from epinoic_logic.branches import RouterHub, extract_quant_checks
from epinoic_logic.branches.packs import CorePack, EnglishPack, HistoryPack, request_demands_judgement
from epinoic_logic.branches.quant import TOLERANCE_RULE
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

KEY = b"packs-r2-regression-key-0123456789ab"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
BODY = ("The Depression was responsible for the Nazi electoral rise because it destroyed the economic security of groups that had voted "
        "for moderate parties in 1928. Registered unemployment rose from about 1.4 million in 1928 to more than six million by early 1932, "
        "and the Nazi vote rose to 37.3 per cent in July 1932. The strongest counter-case is that the vote fell to 33.1 per cent in November 1932. "
        "By the criterion of what made the breakthrough possible, the Depression carries the greater weight.")
LABEL = "\n\nDates and figures are from memory; verify them against your notes before use."
DOW_WRONG = "The Dow Jones Industrial Average fell from about 381 in September 1929 to about 41 in July 1932, a fall of about 50 per cent."
DOW_RIGHT = "The Dow Jones Industrial Average fell from about 381 in September 1929 to about 41 in July 1932, a fall of about 89 per cent."


def status(problem) -> str:
    return verify(problem, CFG).status.value


def one_check(sentence: str):
    checks = extract_quant_checks(sentence, request_id="r", claim_id="c")
    assert len(checks) == 1, (sentence, checks)
    return checks[0]


def history_report(text: str, rid: str = "rep") -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id=rid)


def through_hub(text: str, question: str = "To what extent was the Depression responsible? Write one body paragraph only, in no more than 350 words."):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["history-specialist"]))
    m, _, _ = hub.dispatch("t", "history-specialist", question)
    return hub.receive("t", m.message_id, text, agent_id="history-specialist", report_id="rep-x")


# ------------------------------------------------------------------ quant: dated figures


@pytest.mark.parametrize("sentence,kind,expected", [
    (DOW_WRONG, "percent_change", "COUNTEREXAMPLE"),
    (DOW_RIGHT, "percent_change", "ENTAILED"),
    ("The index fell from 381 on 3 September 1929 to 41 on 8 July 1932, a fall of 89 per cent.", "percent_change", "ENTAILED"),
    ("The index fell from 381 in September 3, 1929 to 41 in July 8, 1932, a fall of 50 per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("Unemployment rose from 1.4 million in early 1928 to 6 million by late 1932, a rise of 329 per cent.", "percent_change", "ENTAILED"),
    ("Unemployment rose from 1.4 million in early 1928 to 6 million by late 1932, a rise of 200 per cent.", "percent_change", "COUNTEREXAMPLE"),
])
def test_month_year_and_day_month_year_dates_between_the_figures_are_skipped_not_fatal(sentence, kind, expected):
    c = one_check(sentence)
    assert c.kind == kind and status(c.problem) == expected


def test_dow_sentence_with_a_wrong_fall_is_an_int_subj_001_error_through_the_hub():
    _, rc = through_hub(BODY + LABEL + " " + DOW_WRONG)
    failed = [fc for fc in rc.formal_checks if fc.satisfied is False]
    assert failed and failed[0].formal_status == "COUNTEREXAMPLE" and "381" in failed[0].detail
    assert any(f.code == "INT-SUBJ-001" and "50 per cent" in f.message for f in rc.errors)
    _, ok = through_hub(BODY + LABEL + " " + DOW_RIGHT)
    assert not [f for f in ok.findings if f.code == "INT-SUBJ-001"] and any(fc.satisfied for fc in ok.formal_checks if fc.constraint_id.startswith("core-quant"))


# ------------------------------------------------------------ quant: shared-unit elision


@pytest.mark.parametrize("sentence,kind,expected", [
    ("Estimates range from 15 to 45 million, a threefold spread.", "fold_change", "ENTAILED"),
    ("Estimates range from 15 to 45 million, a fivefold spread.", "fold_change", "COUNTEREXAMPLE"),
    ("Output fell from 200 to 144 million tonnes, a fall of 28 per cent.", "percent_change", "ENTAILED"),
    ("Output fell from 200 to 144 million tonnes, a fall of 48 per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("The share rose from 3.2 to 24.9 per cent, a rise of 21.7 percentage points.", "points_change", "ENTAILED"),
    ("The share rose from 3.2 to 24.9 per cent, a rise of 25 percentage points.", "points_change", "COUNTEREXAMPLE"),
])
def test_shared_unit_elision_applies_the_second_unit_to_the_first_figure(sentence, kind, expected):
    c = one_check(sentence)
    assert c.kind == kind and status(c.problem) == expected
    before = next(p for p in c.problem.premises if p.id == "BEFORE")
    assert before.label.split("=")[1].strip().split()[-1] in ("million", "cent"), before.label  # the elided unit is recorded on the first figure


# --------------------------------------------- quant: rates, word fractions, fold words


@pytest.mark.parametrize("sentence,kind,expected", [
    ("The death rate rose from about 12 per thousand in 1958 to about 25 per thousand in 1960, a rise of roughly 50 per cent.", "percent_change", "COUNTEREXAMPLE"),
    ("The death rate rose from about 12 per thousand in 1958 to about 25 per thousand in 1960, a rise of roughly 108 per cent.", "percent_change", "ENTAILED"),
    ("Infant deaths fell from 90 per 1,000 to 45 per 1,000, halving.", "fold_change", "ENTAILED"),
    ("Prices fell from 100 to 67, a fall of about a half.", "fraction_change", "COUNTEREXAMPLE"),
    ("Prices fell from 100 to 67, a fall of about a third.", "fraction_change", "ENTAILED"),
    ("Exports fell by two-thirds from 300 to 100 million.", "fraction_change", "ENTAILED"),
    ("Exports fell by three-quarters from 300 to 100 million.", "fraction_change", "COUNTEREXAMPLE"),
    ("Output rose from 1.5 to 3 million, doubling in two years.", "fold_change", "ENTAILED"),
    ("Output rose from 1.5 to 3 million, tripling in two years.", "fold_change", "COUNTEREXAMPLE"),
    ("Output fell from 3 to 1 million, halving in two years.", "fold_change", "COUNTEREXAMPLE"),
    ("Membership grew from 10 to 30 thousand, tripling.", "fold_change", "ENTAILED"),
    ("Membership more than doubled from 1,200 to 3,000.", "fold_change", "ENTAILED"),
    ("Membership more than doubled from 1,200 to 2,000.", "fold_change", "COUNTEREXAMPLE"),
])
def test_rates_word_fractions_and_fold_words_are_checked(sentence, kind, expected):
    c = one_check(sentence)
    assert c.kind == kind and status(c.problem) == expected


# ------------------------------------------------------- quant: symmetric tolerance band


def test_tolerance_band_is_symmetric_around_the_computed_change_and_documented():
    # from 100 to 200 is a rise of exactly 100 per cent: 5 per cent either side passes, 6 per cent either side fails
    assert status(one_check("Revenue rose from 100 to 200, an increase of 105 per cent.").problem) == "ENTAILED"
    assert status(one_check("Revenue rose from 100 to 200, an increase of 95 per cent.").problem) == "ENTAILED"
    assert status(one_check("Revenue rose from 100 to 200, an increase of 106 per cent.").problem) == "COUNTEREXAMPLE"
    assert status(one_check("Revenue rose from 100 to 200, an increase of 94 per cent.").problem) == "COUNTEREXAMPLE"
    # the overseer's pair: an understated fall and an overstated rise are judged by the same rule
    assert status(one_check("The index fell from 381 to 41, a fall of 85 per cent.").problem) == "ENTAILED"       # true 89.2; 4.2 points off, within 5 per cent of 89.2
    assert status(one_check("The index rose from 100 to 169.9, a rise of 74 per cent.").problem) == "COUNTEREXAMPLE"  # true 69.9; 4.1 points off, outside 5 per cent of 69.9
    assert status(one_check("The index rose from 100 to 169.9, a rise of 73 per cent.").problem) == "ENTAILED"     # 3.1 points off, within
    # the rule is stated on the check and reaches the receipt's check description
    c = one_check("Revenue rose from 100 to 200, an increase of 105 per cent.")
    assert "symmetric around the computed value" in c.rule and "0.5 percentage points" in c.rule
    assert c.rule == TOLERANCE_RULE.format(tol="5", floor=", or within 0.5 percentage points of it", side="")
    fc = [x for x in CorePack().formal_checks(history_report(BODY + LABEL + " Revenue rose from 100 to 200, an increase of 105 per cent.")) if x.kind == "percent_change"]
    assert fc and "symmetric around the computed value" in fc[0].description
    # a figure rounded to the nearest whole per cent always passes (the half-point floor): 513/500 is a rise of 2.6 per cent
    assert status(one_check("Turnout rose from 500 to 513, a rise of 3 per cent.").problem) == "ENTAILED"
    assert status(one_check("Turnout rose from 500 to 513, a rise of 2 per cent.").problem) == "COUNTEREXAMPLE"
    # one-sided qualifiers
    assert status(one_check("Revenue rose from 100 to 260, an increase of more than 50 per cent.").problem) == "ENTAILED"
    assert status(one_check("Revenue rose from 100 to 140, an increase of more than 50 per cent.").problem) == "COUNTEREXAMPLE"
    assert extract_quant_checks("Unemployment saw a rise of 30 per cent from 1928 to 1930 among industrial workers.", request_id="r", claim_id="c") == []


# ------------------------------------------------------------------- chronology shapes


def formal_statuses(text: str) -> list[str]:
    return [status(c.problem) for c in CorePack().formal_checks(history_report(text)) if c.kind == "chronology"]


def test_every_after_relation_of_a_sentence_is_decided_not_only_the_first():
    leading = "Britain after Waterloo was repressive: Parliament suspended habeas corpus in January 1817, after a crowd broke a window of the carriage in March 1817."
    assert formal_statuses(leading) == ["COUNTEREXAMPLE"]
    assert chronology_findings_in(leading) == (1817 * 12 + 1, 1817 * 12 + 3)
    lushan = "These practices persisted after the Lushan plenum of August 1959, which came after the withdrawal of Soviet experts in July 1960."
    assert formal_statuses(lushan) == ["COUNTEREXAMPLE"]
    assert chronology_findings_in(lushan) == (1959 * 12 + 8, 1960 * 12 + 7)
    _, rc = through_hub(BODY + LABEL + " " + lushan)
    assert any(f.code == "INT-SUBJ-001" for f in rc.errors) and any(sf.code == "HI-CHR-001" for sf in rc.structural_findings)


def test_leading_after_with_a_bare_month_carries_the_sentence_year():
    hi_p1 = ("Britain after Waterloo, fought on 18 June 1815, was a country of postwar distress and repression: the Corn Law of 1815 kept foreign wheat out "
             "until domestic prices reached 80 shillings a quarter, demobilisation swelled unemployment, and after a crowd broke a window of the Prince Regent's "
             "carriage in January 1817, Parliament suspended habeas corpus in March.")
    rels = chronology_relations(hi_p1)
    assert len(rels) == 1 and rels[0].decided and not rels[0].violated and "March 1817" in rels[0].later_text and "1817 of the dated side was carried" in rels[0].reason
    assert formal_statuses(hi_p1) == ["ENTAILED"]
    # the bare month read in the same year contradicts the order: undecided, never a counterexample
    undecided = "After the riot of November 1817, the Act passed in January."
    rels = chronology_relations(undecided)
    assert len(rels) == 1 and not rels[0].decided and "not stated" in rels[0].reason
    assert formal_statuses(undecided) == []
    f = [x for x in CorePack().checks(history_report("The riot mattered in 1817. " + undecided)) if x.code == "CORE-CHR-001"]
    assert f and f[0].severity == "warning" and "could not be decided" in f[0].message and "January" in f[0].message


def test_aside_with_an_event_verb_is_the_ordered_event_otherwise_undecided():
    plenum = "The Lushan plenum, which met in July 1959, came after the shortfall of October 1959."
    assert formal_statuses(plenum) == ["COUNTEREXAMPLE"] and chronology_findings_in(plenum) == (1959 * 12 + 7, 1959 * 12 + 10)
    treaty = "The treaty, signed in June 1919, came after the armistice of November 1918."
    assert formal_statuses(treaty) == ["ENTAILED"]
    party = "The party, which had been founded in January 1919, was banned after the putsch of November 1923."
    assert formal_statuses(party) == [] and chronology_findings_in(party) is None
    rep = history_report("The ban mattered in 1923. " + party)
    f = [x for x in CorePack().checks(rep) if x.code == "CORE-CHR-001"]
    assert len(f) == 1 and "aside about the subject" in f[0].message and f[0].claim_ids == ["h1.2"]
    _, rc = through_hub(BODY + LABEL + " " + party)
    assert not [x for x in rc.findings if x.code == "INT-SUBJ-001"] and any(sf.code == "CORE-CHR-001" for sf in rc.structural_findings)


@pytest.mark.parametrize("sentence,expected", [
    ("The election of October 1932 followed the reform of March 1931.", "ENTAILED"),
    ("The reform of March 1931 followed the election of October 1932.", "COUNTEREXAMPLE"),
    ("The reform of March 1931 was followed by the election of October 1932.", "ENTAILED"),
    ("The election of October 1932 was followed by the reform of March 1931.", "COUNTEREXAMPLE"),
    ("The reform of March 1931 preceded the election of October 1932.", "ENTAILED"),
    ("The election of October 1932 preceded the reform of March 1931.", "COUNTEREXAMPLE"),
    ("The election of October 1932 was preceded by the reform of March 1931.", "ENTAILED"),
    ("The reform of March 1931 was preceded by the election of October 1932.", "COUNTEREXAMPLE"),
    ("The party had 230 seats in July 1932, before the vote fell in November 1932.", "ENTAILED"),
    ("The party had 230 seats in July 1932, before the vote fell in November 1931.", "COUNTEREXAMPLE"),
    ("Before the Crash of October 1929, output had peaked in August 1929.", "ENTAILED"),
    ("Before the Crash of October 1929, output had peaked in August 1930.", "COUNTEREXAMPLE"),
])
def test_before_followed_and_preceded_are_ordering_cues(sentence, expected):
    assert formal_statuses(sentence) == [expected]
    assert (chronology_findings_in(sentence) is not None) == (expected == "COUNTEREXAMPLE")


@pytest.mark.parametrize("sentence", [
    "The law of March 1931, named after the minister who had proposed it in October 1930, failed.",
    "Prices rose in March 1930; the budget fell after the vote of July 1930.",
    "The fall came only after the Depression had already made the party the largest in Germany; by the criterion of what made the breakthrough possible, it was decisive.",
    "These practices persisted after the Lushan plenum of July and August 1959, which condemned Peng Dehuai for criticising the Leap.",
    "Two developments of the years before framed it; the Rosetta Stone entered the British Museum in 1802.",
])
def test_no_dated_order_means_no_relation_and_no_undecided_finding(sentence):
    assert chronology_relations(sentence) == []
    assert not [x for x in CorePack().checks(history_report("The point stands in 1930. " + sentence)) if x.code == "CORE-CHR-001"]


def test_hi_chr_001_and_the_formal_check_share_one_extractor():
    for sentence in ("The reform came in March 1931, after the election of October 1932 had changed the balance.",
                     "The vote fell in November 1931, which came only after the breakthrough of July 1932.",
                     "The election of October 1932 came after the reform of March 1931.",
                     "The reform of March 1931 was preceded by the election of October 1932."):
        rep = history_report("The point is stated for 1930. " + sentence)
        violated = [r for r in chronology_relations(sentence) if r.violated]
        proxy = [f for f in structural_checks(rep) if f.code == "HI-CHR-001"]
        formal = [c for c in CorePack().formal_checks(rep) if c.kind == "chronology"]
        assert len(proxy) == len(violated) and len(formal) == len(chronology_relations(sentence))
        assert [status(c.problem) == "COUNTEREXAMPLE" for c in formal] == [r.violated for r in chronology_relations(sentence)]


# ------------------------------------------------------ quotation marks of every kind


def test_single_quotes_guillemets_and_mixed_marks_are_unverifiable_quotations_like_double_ones():
    text = BODY + LABEL + (" The leadership blamed 'three years of natural disasters' for the famine of 1960. Another minister spoke of «a parliament that could only say no» "
                           "in July 1930, and a third of “a house of talkers\" in March 1931.")
    rep = history_report(text)
    f = [x for x in CorePack().checks(rep) if x.code == "CORE-SRC-003"]
    assert len(f) == 1 and f[0].severity == "warning" and "3 quotation(s)" in f[0].message
    for span in ("three years of natural disasters", "a parliament that could only say no", "a house of talkers"):
        assert span in f[0].message
        assert any(span in a for c in rep.claims for a in c.assumptions)
    assert "'" not in "".join(x.message for x in CorePack().checks(history_report(BODY + LABEL + " The workers' demands and the employers' response met in 1930.")) if x.code == "CORE-SRC-003")


def test_unbalanced_guillemet_is_reported_and_mixed_balanced_marks_are_not():
    f = [x for x in CorePack().checks(history_report(BODY + LABEL + " The minister called it «a parliament that could only say no in July 1930, and the house rose.")) if x.code == "CORE-SRC-004"]
    assert f and "a parliament that could only say no" in f[0].message
    assert not [x for x in CorePack().checks(history_report(BODY + LABEL + ' The minister called it “a parliament that could only say no" in July 1930.')) if x.code == "CORE-SRC-004"]


# -------------------------------------------------------------------- CORE-SRC-005


POEM = "I met a traveller from an antique land who said: Two vast and trunkless legs of stone stand in the desert, and a sneer of cold command tells the tale."
PEER = ("Britain after Waterloo was a country of distress and repression, and after a crowd broke a window of the carriage in January 1817, "
        "Parliament suspended habeas corpus in March. Dates other than the poem's own are from memory, so check your notes.")
DOC = SuppliedText(document_id="doc-poem", title="Ozymandias (sonnet, supplied text)", author="Percy Bysshe Shelley", text=POEM)
PEER_DOC = SuppliedText(document_id="peer:hi-p1", title="history-specialist report relayed through the hub", author="history-specialist", text=PEER)


def english_report(text: str, texts=(DOC, PEER_DOC)) -> SpecialistReport:
    claim = ClaimRecord(request_id="r", task_id="t", report_id="rep-e", agent_id="english-specialist", subject="English A: Literature", task_type="analytical_paragraph", claim_id="e1", claim_text=text[:4000], claim_role="point")
    return SpecialistReport(report_id="rep-e", request_id="r", task_id="t", agent_id="english-specialist", subject="English A: Literature", task_type="analytical_paragraph",
                            original_response=text, response_sha256=sha256_text(text), supplied_texts=list(texts), claims=[claim], created_at="2026-10-11T14:00:00Z")


def src005(text: str, texts=(DOC, PEER_DOC)):
    return [f for f in CorePack().checks(english_report(text, texts)) if f.code == "CORE-SRC-005"]


def test_quotation_credited_to_the_peer_but_located_only_in_the_poem_is_an_error_naming_both_documents():
    f = src005('The History specialist writes that the face shows a "sneer of cold command".')
    assert len(f) == 1 and f[0].severity == "error" and f[0].claim_ids == ["e1"]
    assert "the history specialist (peer:hi-p1)" in f[0].message and "occurs only in doc-poem" in f[0].message and "sneer of cold command" in f[0].message
    f = src005('Shelley writes that "Parliament suspended habeas corpus in March", a detail the poem turns into ruin.')
    assert len(f) == 1 and "Percy Bysshe Shelley (doc-poem)" in f[0].message and "occurs only in peer:hi-p1" in f[0].message
    assert src005('"Two vast and trunkless legs of stone", the History specialist writes.')
    assert src005('According to the History specialist, "Two vast and trunkless legs of stone" remain.')
    assert src005('My colleague notes that a "sneer of cold command" survives in stone.')


def test_correct_attributions_topics_and_unlocated_quotations_yield_no_core_src_005():
    assert src005('The History specialist notes that "Parliament suspended habeas corpus in March", and the poem speaks of a "sneer of cold command".') == []
    assert src005('The poem shows a "sneer of cold command" and the History specialist describes "a country of distress and repression".') == []
    assert src005('Shelley\'s "Ozymandias" presents royal power as a claim its own material cannot sustain.') == []
    assert src005('The History specialist writes that "the river carried every secret of the town".') == []  # found nowhere: INT-REQ-003 territory
    assert src005('The History specialist warns that "dates other than the poem\'s own are from memory, so check your notes."') == []
    assert src005('The poem speaks of a "sneer of cold command".', (DOC,)) == []


def test_core_src_005_reaches_the_receipt_as_a_branch_error():
    plan = WorkPlan(plan_id="p", request_id="r", task_id="t", subject="English A: Literature", task_type="analytical_paragraph", selected_agent_ids=["english-specialist"], allowed_document_ids=["doc-poem", "peer:hi-p1"])
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(plan)
    m, _, _ = ch.request("router", "english-specialist", "Analyse how the poem treats power against the History specialist's context. Quote exactly and attribute the History specialist's words to the History specialist.", [DOC, PEER_DOC])
    reply, rc = ch.respond(m.message_id, english_report('The History specialist writes that the face shows a "sneer of cold command", which the ruin answers.'))
    assert reply is not None and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    assert any(sf.code == "CORE-SRC-005" for sf in rc.structural_findings) and any(f.code == "INT-SUBJ-003" and "CORE-SRC-005" in f.message for f in rc.errors)


# ------------------------------------------------------- request-aware subject findings


def test_hi_str_001_does_not_fire_for_an_outline_request_but_does_for_a_verdict_term():
    no_judgement = ("Shelley's sonnet was written in 1817 and printed in January 1818. Egyptian antiquities had reached Britain in quantity: the Rosetta Stone entered the "
                    "British Museum in 1802, and in 1816 Belzoni removed a colossal head from Thebes. A poem about a king in ruins therefore appeared in a country that had seen its rulers restrained by law.")
    rep = history_report(no_judgement)
    assert any(f.code == "HI-STR-001" for f in structural_checks(rep))
    assert any(f.code == "HI-STR-001" for f in HistoryPack().checks(rep, None))
    outline = "In one paragraph of no more than 200 words, outline for that student the historical context of its composition, with dated evidence. Label dates from memory as your method requires."
    assert not request_demands_judgement(outline) and not any(f.code == "HI-STR-001" for f in HistoryPack().checks(rep, outline))
    assert not any(f.code == "HI-STR-001" for f in HistoryPack().checks(rep, "Describe the arrival of Egyptian antiquities in Britain between 1802 and 1818."))
    assert not any(f.code == "HI-STR-001" for f in HistoryPack().checks(rep, "Analyse the arrival of Egyptian antiquities in Britain."))  # level 3, no verdict term
    for verdict in ("To what extent was the Depression responsible? Write one paragraph.", "Evaluate the claim that the Depression caused the collapse.",
                    "Outline the effects. Write no more than 200 words and give a judgement on which effect mattered most."):
        assert request_demands_judgement(verdict) and any(f.code == "HI-STR-001" for f in HistoryPack().checks(rep, verdict))
    _, rc = through_hub(no_judgement, outline)
    assert not any(sf.code == "HI-STR-001" for sf in rc.structural_findings)


def test_es_str_002_is_suppressed_when_the_request_sets_a_word_bound():
    text = 'Justice is compromised: the court upheld the thesis "in good faith", so the code decides what the law recognises.'
    extract = SuppliedText(document_id="doc-cdf", text="The lawyer stood by the thesis of homicide in legitimate defense of honor, which was upheld by the court in good faith.", locator_scheme="none")
    hub = RouterHub(signing_key=KEY, config=CFG)
    plan = WorkPlan(plan_id="p", request_id="r", task_id="t", subject="English A: Literature", task_type="analytical_paragraph", selected_agent_ids=["english-specialist"], allowed_document_ids=["doc-cdf"])
    hub.open_task(plan)
    m1, _, _ = hub.dispatch("t", "english-specialist", "Analyse how justice is presented in the extract. Use quotations.", [extract])
    _, r1 = hub.receive("t", m1.message_id, text, agent_id="english-specialist", report_id="rep-1")
    assert any(sf.code == "ES-STR-002" for sf in r1.structural_findings)
    m2, _, _ = hub.dispatch("t", "english-specialist", "Analyse how justice is presented in the extract. Use quotations. Write no more than 300 words.", [extract])
    _, r2 = hub.receive("t", m2.message_id, text, agent_id="english-specialist", report_id="rep-2")
    assert not any(sf.code == "ES-STR-002" for sf in r2.structural_findings)
    rep = hub.channels["t"].transmitted_reports["rep-2"]
    assert any(sf.code == "ES-STR-002" for sf in EnglishPack().checks(rep, None))
    assert not any(sf.code == "ES-STR-002" for sf in EnglishPack().checks(rep, "Keep to about 250 words."))
