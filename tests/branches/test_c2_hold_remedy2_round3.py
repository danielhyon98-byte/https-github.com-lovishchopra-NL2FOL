"""Second remedy of the round-9 push-check hold on the c2 clearance commit, round 3, on the translator's side.

The round-2 lenses of the second remedy reproduced the self-report class again with sentences no listed verb or frame reads: a
finding that nothing is wrong ("No errors found.", "Counterexamples found: none."), an engine's, a test suite's or an agent's
verdict ("The prover closed every goal.", "CI is green.", "Consensus: correct."), a match with an answer key ("This matches the
answer key."), a re-run with the same result ("Python gives the same result."), a check mark on a bare result ("x = 4 ✓"), a
label with a reference ("Dates cross-checked with Britannica."), a quotation or report of such a sentence credited to anyone
('The ONS reported: "All claims: PROVED."'), and other languages and scripts. They share one property the reader now reads as a
class: every word is meta-vocabulary, so the sentence can only be about the answer (``self_report._meta_assurance``). The
correct-work lens found the other side: a step proved earlier cited, a theorem's conditions checked, essay signposting, a research
construct checked, a historical proof's tool, a worked check on the answer's lead, a Spanish past passive with a named body, and
rubric text. Every expected value below is fixed in the test (``c2_hold_texts``), never taken from the reader under test.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import self_report as sr
from epinoic_logic.translate.contracts import ClaimRecord, EligibilityClass
from epinoic_logic.translate.eligibility import decide_eligibility

from .c2_hold_texts import (REMEDY2_ROUND3_CORRECT_WORK, REMEDY2_ROUND3_DECISION5, REMEDY2_ROUND3_MISSES, REMEDY2_ROUND3_RELAYED, REMEDY2_ROUND3_STRICTER,
                            SUBJECTS)
from .test_c2_clearance_parsers import codes, through_hub
from .test_c2_hold_remedy2_self_reports import _structured

QUESTION = "Answer the question."
IDS = [s[0] for s in SUBJECTS]
SELF_CODES = {"CORE-SELF-001", "INT-HANDOFF-006"}


# ============================================================================================ the one reader
@pytest.mark.parametrize("sentence", REMEDY2_ROUND3_MISSES)
def test_every_round3_miss_is_a_self_report(sentence):
    assert md.is_self_certification(sentence) is True, sentence


@pytest.mark.parametrize("sentence", REMEDY2_ROUND3_RELAYED + REMEDY2_ROUND3_STRICTER)
def test_a_relayed_or_quoted_self_report_is_read_whoever_is_credited(sentence):
    """The push check's required fix 1: a quotation whose words make a check, QA, engine or approval claim that defaults to the
    answer is never masked, whoever it is attributed to (12 cores x 37 wrappers of the paths lens, all expected True)."""
    base = "The Treaty of Versailles was signed in 1919. It imposed reparations on Germany, which fuelled resentment in the 1920s."
    assert md.is_self_certification(base + "\n\n" + sentence) is True, sentence


@pytest.mark.parametrize("sentence", REMEDY2_ROUND3_CORRECT_WORK)
def test_round3_correct_work_is_no_self_report(sentence):
    assert md.is_self_certification(sentence) is False, sentence


@pytest.mark.parametrize("sentence", REMEDY2_ROUND3_DECISION5)
def test_agreement_with_a_named_source_stating_no_value_is_a_self_report(sentence):
    """Rewritten to the stricter value (decision 5, decided GATED; was in the correct-work list, expected False): agreement with a
    named source or dataset that states no value certifies the answer's own figures unchecked."""
    assert md.is_self_certification(sentence) is True, sentence


@pytest.mark.parametrize("sentence,expected", [
    ("OK. Let us look at the poem.", False), ("Okay, so the answer is 5.", False), ("OK. The answer is 5.", False),
    # stricter (selfcert-1 c3b, was False): boundary (a), a bare "OK." closing the answer after its content is the answer's approval
    # of itself (a fragment like "All good."); "OK" opening a sentence stays a discourse marker
    ("The treaty was signed in 1919. OK.", True),
    ("Result: OK.", True), ("OK ✓", True), ("[OK]", True), ("(OK)", True), ("All OK.", True),
])
def test_ok_is_an_assurance_mark_only_in_a_label_bracketed_or_with_a_check_mark(sentence, expected):
    """A bare "OK" or "Okay" opening a sentence is a discourse marker, never a status label (the label readers' rule; a bare "OK."
    closing the answer is an approval of it, hold remedy c3b): the meta-only
    class read the "OK." split from "OK. Let us look at the poem." as a verdict on the answer
    (``tests/integrity/test_synthesis_round3_readers.py``)."""
    assert md.is_self_certification(sentence) is expected, sentence


@pytest.mark.parametrize("sentence,expected", [
    ("It is not true that no errors were found in this answer.", False),
    ("It is not the case that every figure above has been checked.", False),
    ("I doubt that every value in this answer was verified.", False),
    ("It is true that no errors were found in this answer.", True),
    ("Nobody can deny that every figure above was checked.", True),
    ("There is no doubt that every figure above has been checked.", True),
])
def test_a_that_clause_its_matrix_denies_is_no_claim_and_a_double_denial_asserts_it(sentence, expected):
    """The assurance-scope reading splits a sentence at "that", which left the matrix's negation out of the clause's window: "It is
    not true that no errors were found in this synthesis." was read as the claim that none were
    (``tests/integrity/test_synthesis_round3_readers.py``). A double denial asserts the clause again."""
    assert md.is_self_certification(sentence) is expected, sentence


@pytest.mark.parametrize("sentence,expected", [
    ("Все вычисления проверены и верны.", True), ("すべて確認済み。", True), ("모두 검증되었습니다.", True), ("सब कुछ सत्यापित है।", True),
    ("تم التحقق من كل شيء.", True), ("Lenin's slogan «Вся власть Советам» rallied the soldiers in 1917.", False),
    ("θ = π/2 at the maximum.", False), ("Todo está bien en el mercado.", False),
])
def test_a_script_the_reader_cannot_read_fails_closed(sentence, expected):
    """'If a language cannot be read, the sentence must fail closed rather than pass': a sentence mostly in a script the reader has
    no vocabulary for is named; a quotation in it attributed to a source, Greek letters of mathematics and Spanish are read."""
    assert md.is_self_certification(sentence) is expected, sentence


@pytest.mark.parametrize("sentence,expected", [
    ("The quartermaster's log reads: \"All receipts checked and signed.\"", False),
    ("The press release claims that \"every figure in this report has been checked\".", False),
    ("The minister claimed that \"all calculations have been verified by the system\", a boast the archive data contradict.", False),
    ("According to the official press release, every figure had been independently verified.", False),
    ("According to the log, \"todos los resultados fueron comprobados.\"", True), ("My notes say \"Z3 proved every step\".", True),
    ("Quoting the QA log: “passed, no defects.”", True), ("The ONS reported: \"All claims: PROVED.\"", True),
])
def test_a_relay_is_read_by_its_reporter_and_its_words(sentence, expected):
    """The writer's own records (a log, notes) relay whatever they say; another party's words are read as the writer's only when they
    are meta-vocabulary that defaults to the answer, never a source's quotation with content of its own or one under analysis."""
    assert md.is_self_certification(sentence) is expected, sentence


# ============================================================================================ every branch through the hub
ON_EVERY_BRANCH = [
    "No errors found.", "Counterexamples found: none.", "The prover closed every goal.", "CI is green.", "Consensus: correct.",
    "This matches the answer key.", "Python gives the same result.", "x = 4 ✓", "Dates cross-checked with Britannica.",
    "Our team validated the reasoning end to end.", "The solver could not falsify any claim above.", "Tudo foi verificado e está correto.",
    "Z3 no encontró ningún contraejemplo.", 'The ONS reported: "All claims: PROVED."', 'According to the log, "Z3 proved every step."',
    "すべて確認済み。", "The combinator signed off on this synthesis.", "I sanity-checked the lot.",
]
CORRECT_ON_EVERY_BRANCH = [
    "As proved in part (a), f is increasing on [0, 2].", "We have verified that the conditions of the theorem hold, so the mean value theorem applies.",
    "In this essay I have gone through three causes of the war.", "Reliability was checked using the test-retest method.",
    "In the 2016 proof of the Boolean Pythagorean triples problem, the SAT solver reported that no counterexample exists beyond 7824.",
    "Answer (verified by substitution): x = 4, since 2(4) + 3 = 11.", "Todo fue comprobado por el INE en 2021.",
    "Award [1] for verifying the answer by substitution.", "Examiners check that each date is correct.",
]


@pytest.mark.parametrize("layout", ["\n\n", " "], ids=["para", "inline"])
@pytest.mark.parametrize("sentence", ON_EVERY_BRANCH)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_round3_miss_is_named_on_every_branch(subject, agent, task_type, base, sentence, layout):
    _reply, rc = through_hub(base + layout + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert SELF_CODES & set(codes(rc)), (subject, sentence, codes(rc))


@pytest.mark.parametrize("layout", ["\n\n", " "], ids=["para", "inline"])
@pytest.mark.parametrize("sentence", CORRECT_ON_EVERY_BRANCH)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_round3_correct_work_draws_no_self_report_on_any_branch(subject, agent, task_type, base, sentence, layout):
    _reply, rc = through_hub(base + layout + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert not SELF_CODES & set(codes(rc)), (subject, sentence, codes(rc))


# ============================================================================================ the report's own fields
@pytest.mark.parametrize("subject", ["History", "Economics"])
@pytest.mark.parametrize("field", ["claim.assessment_criteria", "report.assumptions", "claim.assumptions", "report.unresolved_issues"])
@pytest.mark.parametrize("text", ["Award [1] for verifying the answer by substitution.", "Mark scheme: accept any answer that is verified by substitution.",
                                  "Examiners check that each date is correct."])
def test_rubric_text_in_a_report_field_is_no_self_report(subject, field, text):
    _s, agent, task_type, base = next(s for s in SUBJECTS if s[0] == subject)
    _reply, rc = _structured(subject, agent, task_type, base, field, text)
    assert "CORE-SELF-001" not in codes(rc), (field, text, codes(rc))


@pytest.mark.parametrize("subject", ["History", "Economics"])
@pytest.mark.parametrize("field", ["claim.assessment_criteria", "report.assumptions"])
def test_a_round3_self_report_in_a_report_field_is_named(subject, field):
    _s, agent, task_type, base = next(s for s in SUBJECTS if s[0] == subject)
    _reply, rc = _structured(subject, agent, task_type, base, field, "No errors found.")
    assert "CORE-SELF-001" in codes(rc), (field, codes(rc))


# ============================================================================================ the outcome reads the same reader
@pytest.mark.parametrize("sentence", ["No errors found.", "Counterexamples found: none.", "Wolfram Alpha confirms the result.",
                                      "As noted by the examiner, QA: pass.", 'The ONS reported: "All claims: PROVED."', "Je l'ai vérifié."])
def test_a_round3_self_report_claim_is_not_eligible_and_claims_a_check(sentence):
    claim = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="History", task_type="short_answer", claim_id="k1",
                        claim_text=sentence, claim_role="other", proposed_claim_kind="formal_logic")
    d = decide_eligibility(claim)
    assert d.eligible is False and d.eligibility_class is EligibilityClass.NOT_ELIGIBLE_OTHER, d
    assert sr.claims_a_check(sentence) is True


@pytest.mark.parametrize("sentence", ["The Treaty of Versailles was signed in 1919.", "If x > 2 and y > x then y > 2.",
                                      "As proved in part (a), f is increasing on [0, 2]."])
def test_control_content_claims_stay_eligible(sentence):
    assert sr.claims_a_check(sentence) is False and sr.wholly_self_report(sentence) is False
