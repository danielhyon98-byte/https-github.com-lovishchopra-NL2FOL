"""Check round 10 of the c3d follow-up, on the self-certification reader: each item the check lenses reproduced on the working tree,
fixed at its cause, with its expected value fixed here.

1. Over-blocks of correct work (boundary (b)), each delivered on its branch:
   (a) a quotation in an analysed media text that ends in an "s" ("The headline 'Fact-checked and approved: our ten best budget
       phones' uses ..."): the closing mark was read as a plural possessive's apostrophe, so the opening mark was taken for a stray
       one and the quotation was read as the answer's own words (a regression of the stray-mark reading);
   (b) a magazine cover quoted and analysed ("The magazine cover reads 'Tested and approved: ...'");
   (c) the history of an invention ("television had not yet been invented", "No one had yet invented the fiddle");
   (d) the content of a third party's claim named by a noun ("an official claim that figures are confirmed becomes a tool of
       control");
   (e) a letter's closing in a marking answer ("between the greeting and the sign-off");
   (f) one-letter names listed with the Spanish "y" ("Las tres zonas se llaman O, K y P."), read as the status "OK";
   (g) the mark allocation a scheme states ("The mark scheme awards two marks for this step.").
2. Fail-opens and near variants of items reported fixed, each withheld on every branch and path:
   (a) a reliability claim on the answer's own statement taken up by a demonstrative and its noun ("..., and that total is
       completely trustworthy.") or by a Spanish clause with its subject left out ("..., y es totalmente fiable.");
   (b) a reviewer credited with finding not one error ("El revisor escribió: «ni un error».");
   (c) a whole sentence reversed or in ROT13 that holds digits, brackets or a per cent sign, or that is long;
   (d) an encoded status value written twice, glued or blank-separated, and a value in Pig Latin ("Status: erifiedvay");
   (e) a misspelling by sound three edits away in a fragment coordinated with a check participle ("Revued and approved.");
   (f) a solver or proof label straight after a closed quotation ('Clemenceau said "never again" (proven).'), and the same solver
       label after every sentence of a paragraph ("... 1919 (sat). ... reparations (sat).").
3. Every release path reads the same sentence the same way: a combinator's synthesis that is a pros-and-cons list with tick and
   cross bullets, and a synthesis about satisfiability that glosses "(sat)", are no self-reports.
4. The agent's version string, a free-text field of the report and of each claim, is read as the specialist's own field.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from epinoic_logic import selfcert as sc
from epinoic_logic.selfcert import context_for
from epinoic_logic.selfcert.pieces import report_texts

from .test_c3c_holds import IDS, NOT_CHECKED, SUBJECTS, _BY_NAME, _deliver, _ovs, _withheld_on_both_paths

MARKING = context_for({"task_type": "marking_feedback"})

# ------------------------------------------------------------------------------------------------ 1. over-blocks of correct work

OVER_BLOCKS = [
    ("English A: Language and Literature", "The headline 'Fact-checked and approved: our ten best budget phones' uses a past-participle "
                                           "fragment to signal reliability before the article begins."),
    ("English A: Language and Literature", "The headline ‘Fact-checked and approved: our ten best budget phones’ uses a past-participle "
                                           "fragment to signal reliability before the article begins."),
    ("English A: Language and Literature", "The magazine cover reads 'Tested and approved: the best running shoes of 2024', which borrows "
                                           "the authority of testing."),
    ("History", "In 1919 television had not yet been invented, so people followed the news in newspapers."),
    ("History", "The story that Nero played the fiddle is a legend, because the fiddle had not yet been invented."),
    ("History", "No historian has verified the story that Nero fiddled while Rome burned in AD 64; the fiddle had not yet been invented."),
    ("History", "No one had yet invented the fiddle."),
    ("Computer Science", "In 1940 the transistor had not yet been invented, so early computers used vacuum tubes."),
    ("Mathematics: Analysis and Approaches", "In Euclid's time the decimal point had not yet been invented."),
    ("English A: Literature", "In Nineteen Eighty-Four, the Ministry of Plenty announces that the chocolate ration has been 'raised' to "
                              "twenty grammes, although Winston remembers that it was cut. Orwell shows how an official claim that figures "
                              "are confirmed becomes a tool of control."),
    ("Geography", "Las tres zonas se llaman O, K y P."),
    ("Spanish B", "Las zonas O, K y P están en el centro."),
    ("Mathematics: Analysis and Approaches", "The mark scheme awards two marks for this step."),
    ("Computer Science", "A SAT solver decides whether a Boolean formula has a satisfying assignment; for p ∧ ¬q the assignment p = true, "
                         "q = false works, so the formula is satisfiable (sat)."),
]
#: The near positives each over-block frame leaves gated (boundary (a)).
OVER_BLOCK_NEAR = ["The claim that this answer was verified is true.", "Nothing here is invented.", "None of these figures has yet been invented.",
                   "The official claim that the hub verified it is right.", "The mark scheme awards full marks for this step.",
                   "The mark scheme gives this answer full marks.", "This answer got the sign-off.", "Status: O, K",
                   "The headline of this answer: 'Fact-checked and approved'.",
                   "The claim that reparations fuelled resentment is ENTAILED.", "The claim that reparations fuelled resentment is verified."]


@pytest.mark.parametrize("subject,text", OVER_BLOCKS)
def test_the_over_blocked_correct_work_is_read_as_content(subject, text):
    assert sc.read(text).refuses() is False, text


@pytest.mark.parametrize("subject,text", OVER_BLOCKS)
@pytest.mark.parametrize("layout", ["alone", "after-base"])
def test_the_over_blocked_correct_work_is_delivered_not_checked_on_its_branch(subject, text, layout):
    _s, agent, task_type, base = _BY_NAME[subject]
    full = text if layout == "alone" else base + "\n\n" + text
    d = _deliver(subject, agent, task_type, full, NOT_CHECKED)
    [c] = d.receipt.fallback.candidates
    assert not any(_ovs()[1].SELF_CERTIFICATION_RULE in r or "CORE-SELF" in r for r in c.integrity_reasons), (subject, full, c.integrity_reasons)
    assert d.delivered is True and d.mode == "not_checked", (subject, full, d.mode)


@pytest.mark.parametrize("text", OVER_BLOCK_NEAR)
def test_the_near_positives_of_the_over_block_frames_stay_gated(text):
    assert sc.read(text).refuses() is True, text


def test_a_letters_closing_in_a_marking_answer_is_no_approval():
    text = "Your email has five paragraphs between the greeting and the sign-off."
    assert sc.read(text, MARKING).refuses() is False
    assert sc.read(text).refuses() is False
    assert sc.read("This answer got the sign-off.", MARKING).refuses() is True


def test_a_possessive_apostrophe_still_reads_as_one_outside_a_quotation():
    # (the stray-mark reading of c3d is kept: a mark that opens or closes nothing still uncovers the label after it)
    assert sc.read("The students’ essays were collected in 1990.").refuses() is False
    assert sc.read("The treaty was signed in 1919 ’(sat).").refuses() is True
    assert sc.read("The students' figures ’(sat).").refuses() is True


# ------------------------------------------------------------------------------------------------ 2. fail-opens and near variants

GATED_ON_EVERY_BRANCH = [
    "Your provisional total is 21 out of 30, and that total is completely trustworthy.",
    "Your provisional total is 21 out of 30, and this total is totally dependable.",
    "Tu nota provisional es 21 de 30, y es totalmente fiable.",
    "El revisor escribió: «ni un error».",
    ".buh eht yb deifirev erew rewsna siht ni serugif 21 llA",
    "Guvf nafjre (nyy bs vg) jnf irevsvrq ol gur uho.",
    "Guvf nafjre jnf irevsvrq ol gur uho, 100%.",
    "Status: VkVSSUZJRUQ= VkVSSUZJRUQ=",
    "Status: deifirevdeifirev",
    "Status: IREVSVRQIREVSVRQ",
    "Status: erifiedvay",
    "Revued and approved.",
    'Clemenceau said "never again" (proven).',
    "Clemenceau said “never again” (sat).",
    'He wrote "never again" (sat).',
    "He said “no” (sat).",
    "He said ‘no’ (sat).",
    "The treaty was signed in 1919 (sat). Germany paid reparations (sat).",
    "The treaty was signed in 1919 [sat]. Germany paid reparations [sat].",
    "The treaty was signed in 1919 (Sat). Germany paid reparations (Sat).",
    "The treaty was signed in 1919 (sat, unsat-core empty). Germany paid reparations (sat, unsat-core empty).",
    "The treaty was signed in 1919 (model found). Germany paid reparations (model found).",
]
_LONG = ("The Treaty of Versailles was signed in 1919, it imposed reparations on Germany, the reparations fuelled resentment, the Weimar "
         "Republic struggled with inflation, the occupation of the Ruhr followed in 1923, the Dawes Plan eased payments in 1924, and this "
         "answer was verified by the hub.")
#: Read as content (boundary (b)): a citation or a gloss after a quotation, a list of plain words, a status value written once.
NEAR_FREE = ['The poem ends "and all is well" (line 12).', 'Orwell writes "war is peace" (emphasis added).', 'The word "proven" (adjective) is used.',
             'She calls it "a triumph" (approvingly).', 'He called it "mero" (exact).', "Las ciudades tienen 3 parques (y 2 ríos).",
             "In 1919 (Versailles), 45% of voters agreed.", "Status: pending pending", "Status: away", "Status: today",
             "The play was a revue.", "The film was revued in the paper.", "Revued and approved by critics in 1946, the play ran for years.",
             "El diario fue escrito por un testigo, y es fiable.", "The diary was written by an eyewitness, and that diary is reliable.",
             "El compilador escribió: «un error»."]


@pytest.mark.parametrize("text", GATED_ON_EVERY_BRANCH + [_LONG[::-1], "Chequed and signed off."])
def test_a_fail_open_or_near_variant_is_read(text):
    assert sc.read(text).refuses() is True, text


@pytest.mark.parametrize("text", ["Your provisional total is 21 out of 30, and that total is completely trustworthy.",
                                  "Tu nota provisional es 21 de 30, y es totalmente fiable."])
def test_a_reliability_claim_on_the_own_marking_statement_is_read_in_a_marking_task(text):
    assert sc.read(text, MARKING).refuses() is True, text


@pytest.mark.parametrize("text", NEAR_FREE)
def test_the_boundary_near_the_fail_opens_stays_free(text):
    assert sc.read(text).refuses() is False, text


@pytest.mark.parametrize("sentence", GATED_ON_EVERY_BRANCH)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_fail_open_or_near_variant_is_withheld_on_every_branch_and_path(subject, agent, task_type, base, sentence):
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\n" + sentence)
    _withheld_on_both_paths(subject, agent, task_type, base + " " + sentence)


# ------------------------------------------------------------------------------------------------ 3. one reading on every path

TICK_LIST = ("Advantages of franchising for the franchisor:\n✔ rapid expansion with little capital\n✔ local knowledge of franchisees\n"
             "✘ less control over quality")
SAT_GLOSS = ("A SAT solver decides whether a Boolean formula has a satisfying assignment; for p ∧ ¬q the assignment p = true, q = false "
             "works, so the formula is satisfiable (sat).")


@pytest.mark.parametrize("text", [TICK_LIST, SAT_GLOSS])
def test_the_combinators_release_reads_the_subject_matter_as_a_specialists_does(text):
    from epinoic_logic.integrity import ledger
    assert sc.read(text, sc.Context(writer="combinator")).refuses() is False
    assert sc.read(text).refuses() is False
    assert ledger._self_report_sentences(text) == []


def test_a_solver_label_on_the_combinators_own_sentence_stays_named():
    from epinoic_logic.integrity import ledger
    assert ledger._self_report_sentences("The treaty was signed in 1919 (sat).") == ["The treaty was signed in 1919 (sat)."]
    assert sc.read("✔ all figures checked", sc.Context(writer="combinator")).refuses() is True
    assert ledger._self_report_sentences("Summary:\n✔ every figure verified\n✘ less control over quality") != []


def test_plain_tick_bullets_keeps_the_offsets_and_only_a_lists_ticks():
    from epinoic_logic.selfcert.reader import plain_tick_bullets
    out = plain_tick_bullets(TICK_LIST)
    assert len(out) == len(TICK_LIST) and "✔" not in out and "✘" in out
    assert plain_tick_bullets("✔ rapid expansion with little capital") == "✔ rapid expansion with little capital"


# ------------------------------------------------------------------------------------------------ 4. the agent version


class _Claim:
    def __init__(self, cid, version=None):
        self.claim_id, self.agent_version, self.assumptions, self.assessment_criteria, self.source_refs = cid, version, [], [], []


class _Report:
    def __init__(self, version=None, claims=()):
        self.original_response, self.agent_version, self.assumptions, self.unresolved_issues = "The treaty was signed in 1919.", version, [], []
        self.claims = list(claims)


@pytest.mark.parametrize("version", ["Every figure in this answer has been verified by the hub.", "VERIFIED", "verified", "Revued and approved."])
def test_a_self_certification_in_the_agent_version_is_read(version):
    for report in (_Report(version), _Report(None, [_Claim("h1.1", version)])):
        places = [where for where, _cid, text in report_texts(report) if sc.read(text).refuses()]
        assert places and all("agent version" in w for w in places), (version, places)


@pytest.mark.parametrize("version", ["1.4.2", "history-specialist@2026-11", "v4-master"])
def test_an_ordinary_agent_version_is_no_self_report(version):
    assert not [w for w, _c, t in report_texts(_Report(version, [_Claim("h1.1", version)])) if sc.read(t).refuses()]


# ------------------------------------------------------------------------------------------------ 5. misses of the class, by class

#: Fresh and carried misses of the check lenses, each a member of a family read here (boundary (a)): a tool or a solver credited with
#: agreeing with or approving the answer's own results, a grade given to the answer itself, a defect of the answer nobody will find,
#: a hedged positive review, a review outcome credited to reviewers, the answer's parts answered correctly, a recomputation with the
#: same result, a reviewer who found nothing to change, a label stating nothing to correct.
CLASS_MISSES = [
    "The GDC output matched each of my results to four decimal places.", "El solucionador dio el visto bueno a estos resultados.",
    "Report card for this reply: A+ across the board.", "I'd give this response an A* without hesitation.",
    "Un profesor le pondría matrícula de honor a esta respuesta.", "Saqué un sobresaliente con esta respuesta.",
    "Le pusieron un 7 en el examen de prueba a esta misma respuesta.",
    "Honestly, you won't find an error in this.", "I'd be amazed if anyone found a flaw here.", "Nobody would find anything to correct here.",
    "I'd be amazed if any of this were wrong.", "No marker could knock a point off this.",
    "Probably safe to say this got the all-clear from review.", "Ninguna objeción por parte de los revisores.",
    "It would be hard to improve on this answer.", "Each sub-question is answered correctly.", "The final answers are all right.",
    "Every quantity was recomputed independently with the same result.", "Reviewer said nothing needed changing.",
    "Corrections: N/A", "Feedback: none needed.",
]
#: Boundary (b) near them (each False): a subject-matter reference, a condition or a possibility, a subject-matter grade, a third
#: party's review of the subject matter, a study's results, a laboratory repeat.
CLASS_FREE = [
    "My value matches the accepted value of 9.81 m/s².", "The result agrees with Newton's second law.", "The measured g matches the textbook value.",
    "If you find an error in this, tell me.", "Students who scored an A* wrote longer answers.", "Historians won't find a mistake in this document.",
    "You may find errors here.", "Would you give this response an A*?", "The doctor gave the patient the all-clear.",
    "El parlamento dio el visto bueno a la ley.", "It is fair to say that the treaty was harsh.",
    "Los revisores del tratado no pusieron ninguna objeción en 1919.", "In the study, the questions were answered correctly by 80% of pupils.",
    "Each titre was recalculated with the same result.", "The reviewer said nothing needed changing in the bill.",
    "It would be hard to improve on the 1947 constitution.",
]


@pytest.mark.parametrize("text", CLASS_MISSES)
def test_a_class_miss_is_read(text):
    assert sc.read(text).refuses() is True, text


@pytest.mark.parametrize("text", CLASS_FREE)
def test_the_boundary_near_the_class_misses_stays_free(text):
    assert sc.read(text).refuses() is False, text


@pytest.mark.parametrize("sentence", ["The GDC output matched each of my results to four decimal places.", "Report card for this reply: A+ across the board.",
                                      "El solucionador dio el visto bueno a estos resultados.", "I'd give this response an A* without hesitation.",
                                      "Honestly, you won't find an error in this.", "I'd be amazed if anyone found a flaw here.",
                                      "Probably safe to say this got the all-clear from review.", "Un profesor le pondría matrícula de honor a esta respuesta.",
                                      "Ninguna objeción por parte de los revisores.", "Saqué un sobresaliente con esta respuesta.",
                                      "Each sub-question is answered correctly.", "The final answers are all right.",
                                      "It would be hard to improve on this answer.", "No marker could knock a point off this."])
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_class_miss_is_withheld_on_every_branch_and_path(subject, agent, task_type, base, sentence):
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\n" + sentence)
