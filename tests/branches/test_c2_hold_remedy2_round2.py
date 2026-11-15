"""Second remedy of the round-9 push-check hold on the c2 clearance commit, round 2, on the translator's side.

The round-1 lenses of the second remedy reproduced both sides of the self-report class on the working tree. Misses (delivered
NOT CHECKED, OVERSEER-SELECTED, by the router, the port and the outcomes): a complete check said through a double negation ("No
figure was left unchecked."), "made sure to" and "took care to" checks, checking verbs outside the listed class ("looked over",
"gone through", "proofed"), engine-result imitations and status leads ("No counterexample exists.", "Checks: 12/12 passed.",
"Engine verdict: consistent."), a question the writer answers itself ("Checked? Yes."), a tool's or the hub's relayed verdict ("The
solver reported that no counterexample exists."), a check label on the answer's lead ("Final answer: 15 km/h, checked twice."),
other languages, and quotations whose frame names no outside party (the writer's own headline, line or caption). False positives
(correct work withheld on every path): an event told with a pronoun subject, a check an outside source made, subject vocabulary
(a chemical solution, data validation, TLS signing, quality control), a proof's conclusion, an essay's evaluation of its subject,
a source's self-report quoted under analysis, a quoted tagline cut into labels by a parser, a method step, a rejected root.

The one reader now reads each as a class (``adapters.self_report``); every expected value below is fixed in the test
(``c2_hold_texts``), never taken from the reader under test.
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import self_report as sr
from epinoic_logic.branches.generic_parser import split_sentences as generic_split
from epinoic_logic.translate.contracts import ClaimRecord, EligibilityClass
from epinoic_logic.translate.eligibility import decide_eligibility

from .c2_hold_texts import REMEDY2_ROUND2_CORRECT_WORK, REMEDY2_ROUND2_MISSES, SUBJECTS
from .test_c2_clearance_parsers import codes, through_hub
from .test_c2_hold_remedy2_self_reports import _structured

QUESTION = "Answer the question."
IDS = [s[0] for s in SUBJECTS]
SELF_CODES = {"CORE-SELF-001", "INT-HANDOFF-006"}


# ============================================================================================ the one reader
@pytest.mark.parametrize("sentence", REMEDY2_ROUND2_MISSES)
def test_every_round2_miss_is_a_self_report(sentence):
    assert md.is_self_certification(sentence) is True, sentence


@pytest.mark.parametrize("sentence", REMEDY2_ROUND2_CORRECT_WORK)
def test_round2_correct_work_is_no_self_report(sentence):
    assert md.is_self_certification(sentence) is False, sentence


@pytest.mark.parametrize("frame,expected", [
    ('Headline: "All figures verified and correct."', False), ('The bottom line: "every value has been verified."', False),
    ('My verdict, in a word: "verified".', False), ('What the extract shows is clear, and "every figure has been verified."', False),
    ('Stalin claimed that "all the figures in this report have been verified and proved", although ...', True),
    ('The narrator\'s line, "the answer was checked and nothing was wrong", is ironic.', True),
    ('The label "QA: pass" printed on the packaging reassures the consumer.', True),
    ('As the examiner wrote, "every figure has been verified."', False), ('"Approved," wrote the overseer.', False),
    ('For the record, "every figure has been verified."', False), ('My summary\'s last line: "every value verified".', False),
    ('The quartermaster\'s log reads: "All receipts checked and signed."', True),
])
def test_a_quotation_is_masked_only_when_an_outside_party_is_its_source(frame, expected):
    """A frame noun alone (a headline, a line, a verdict) names no source: the quotation is the writer's own words."""
    masked = sr.mask_outside_quotations(frame)
    inner = frame.split('"')[1]
    assert (inner not in masked) is expected, masked


@pytest.mark.parametrize("inner,expected", [
    ("every figure here has been verified.", True), ("every figure in it has been verified.", True), ("all of the above has been checked", True),
    ("all the figures in this report have been verified and proved", False), ("All receipts checked and signed.", False), ("QA: pass", False),
    ("the answer was checked and nothing was wrong", False),
])
def test_a_quotation_in_the_answers_scope_refers_to_this_answer(inner, expected):
    """Generic checking words (proved, receipts, QA, "the answer") never by themselves make a source's quotation the writer's."""
    assert sr.quotation_in_scope(inner) is expected


# ============================================================================================ every branch through the hub
ON_EVERY_BRANCH = [
    "No figure was left unchecked.", "I made sure to verify every value.", "Each line was looked over.", "Result: valid; no counterexample.",
    "Checked? Yes.", 'Headline: "All figures verified and correct."', "The solver reported that no counterexample exists.", "Ich habe alle Werte nachgerechnet.",
    "Final answer: 15 km/h, checked twice.", "Confirmed against the mark scheme.", "LGTM.", "Tests: 7 passed, 0 failed.",
]
CORRECT_ON_EVERY_BRANCH = [
    "It was tested at Alamogordo in July 1945.", "These results were confirmed in a later meta-analysis.",
    "Each value is checked against the range 0 to 100 before it is accepted.", "Hence both results are proved.",
    "This essay has assessed the extent to which the treaty caused resentment in Germany.",
    'The narrator\'s line, "the answer was checked and nothing was wrong", is ironic.',
    'The advert\'s tagline, "Tested. Approved. Trusted.", borrows the language of quality assurance.',
    "Both solutions were checked in the original equation, and x = -1 was rejected because ln(-1) is undefined.",
    "In other words, the IMF found that the figures were sound.",
]


@pytest.mark.parametrize("layout", ["\n\n", " "], ids=["para", "inline"])
@pytest.mark.parametrize("sentence", ON_EVERY_BRANCH)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_round2_miss_is_named_on_every_branch(subject, agent, task_type, base, sentence, layout):
    _reply, rc = through_hub(base + layout + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert SELF_CODES & set(codes(rc)), (subject, sentence, codes(rc))


@pytest.mark.parametrize("layout", ["\n\n", " "], ids=["para", "inline"])
@pytest.mark.parametrize("sentence", CORRECT_ON_EVERY_BRANCH)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_round2_correct_work_draws_no_self_report_on_any_branch(subject, agent, task_type, base, sentence, layout):
    _reply, rc = through_hub(base + layout + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert not SELF_CODES & set(codes(rc)), (subject, sentence, codes(rc))


def test_the_generic_parser_never_cuts_a_quotation_into_sentences():
    """The cause of the tagline's branch-dependent result: the generic parser (Economics, Business, Psychology, generic) cut the
    quoted tagline into "Approved." and "Trusted.", which read as bare labels; the English and History parsers keep it whole."""
    para = 'A tariff raises prices. The advert\'s tagline, "Tested. Approved. Trusted.", borrows the language of quality assurance. He said "Yes." Then he left.'
    assert generic_split(para) == ["A tariff raises prices.",
                                   'The advert\'s tagline, "Tested. Approved. Trusted.", borrows the language of quality assurance.',
                                   'He said "Yes."', "Then he left."]


# ============================================================================================ the report's own fields
GDC = "All values were verified on a GDC and are confirmed correct."


@pytest.mark.parametrize("subject", ["History", "Economics"])
@pytest.mark.parametrize("field", ["report.assumptions", "claim.assumptions"])
def test_a_field_copy_of_a_masked_quotation_in_the_response_is_still_read(subject, field):
    """Case A of the paths lens: the response holds the sentence only as an outside party's quotation (masked); the field states it
    bare. The field was dropped as a copy of the response."""
    _s, agent, task_type, base = next(s for s in SUBJECTS if s[0] == subject)
    reply, _rc = through_hub(base + f' The minister claimed that "{GDC}"', QUESTION, subject=subject, agent=agent, task_type=task_type)
    rep = json.loads(json.dumps(reply.payload))
    target = rep if field.startswith("report") else rep["claims"][0]
    target["assumptions"] = list(target.get("assumptions") or []) + [GDC]
    assert sr.report_field_self_reports(rep), field


@pytest.mark.parametrize("lead", ["All checked and confirmed correct", "QA passed", "Verified"])
def test_a_note_lead_that_certifies_is_never_a_platform_record(lead):
    """Case B: "<lead>: <words of the response>" was dropped as the platform's record whatever its lead."""
    response = "The Treaty of Versailles was signed in 1919. It imposed reparations on Germany."
    report = {"original_response": response, "unresolved_issues": [f"{lead}: The Treaty of Versailles was signed in 1919."], "claims": []}
    assert sr.report_field_self_reports(report) == [("an unresolved issue of the report", None)]
    report["unresolved_issues"] = ["inline label recorded, not part of the claim: (A1)"]
    assert sr.report_field_self_reports(report) == []


@pytest.mark.parametrize("filler", [15990, 16010, 40000])
def test_a_long_field_is_read_whole_never_cut_short(filler):
    """Case C: the reader read only the first 16000 characters of a field, so a self-certification after filler was delivered."""
    text = ("This point frames the context of the answer. " * 1000)[:filler] + " " + GDC
    assert sr.report_field_self_reports({"assumptions": [text], "claims": []}) == [("an assumption of the report", None)]
    clean = ("This point frames the context of the answer. " * 1000)[:filler]
    assert sr.report_field_self_reports({"assumptions": [clean], "claims": []}) == []


def test_a_field_too_long_to_read_is_named_fail_closed():
    text = "This point frames the context of the answer. " * 8000
    assert sr.report_field_self_reports({"assumptions": [text], "claims": []}) == [("an assumption of the report", None)]


@pytest.mark.parametrize("subject", ["History", "Economics"])
def test_a_case_b_field_is_named_on_the_receipt(subject):
    _s, agent, task_type, base = next(s for s in SUBJECTS if s[0] == subject)
    _reply, rc = _structured(subject, agent, task_type, base, "report.unresolved_issues", "QA passed: " + base.split(". ")[0] + ".")
    assert "CORE-SELF-001" in codes(rc), codes(rc)


# ============================================================================================ the outcome reads what the packs read
@pytest.mark.parametrize("sentence,wholly", [
    ("Answer (verified): 15 km/h.", True), ("Signed receipt attached: VERIFIED.", True), ("No counterexample exists.", True), ("LGTM.", True),
    ("Final answer: 15 km/h, checked twice.", True), ("Verified: The Weimar constitution was adopted in August 1919.", False),
])
def test_a_label_the_packs_name_never_shows_success_in_the_outcome(sentence, wholly):
    """The outcome's reader (``claims_a_check``) read only the one reader, not the packs' verification labels, so 'Answer
    (verified): 15 km/h.' showed ENTAILED where the hub refused it. A label set on content leaves the content eligible
    (``wholly_self_report`` False) but its outcome never shows a success."""
    assert sr.claims_a_check(sentence) is True
    assert sr.wholly_self_report(sentence) is wholly


@pytest.mark.parametrize("sentence", ["Answer (verified): 15 km/h.", "No counterexample exists.", "Per Z3, all claims hold.", "LGTM."])
def test_a_round2_self_report_claim_is_not_eligible(sentence):
    claim = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="History", task_type="short_answer", claim_id="k1",
                        claim_text=sentence, claim_role="other", proposed_claim_kind="formal_logic")
    d = decide_eligibility(claim)
    assert d.eligible is False and d.eligibility_class is EligibilityClass.NOT_ELIGIBLE_OTHER, d


@pytest.mark.parametrize("sentence", ["The Treaty of Versailles was signed in 1919.", "If x > 2 and y > x then y > 2.", "Mendel's results were later confirmed by Correns."])
def test_control_content_claims_stay_eligible_for_the_outcome(sentence):
    assert sr.claims_a_check(sentence) is False and sr.wholly_self_report(sentence) is False
