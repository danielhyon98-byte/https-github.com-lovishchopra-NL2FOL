"""The fifth repair of the translator merge (design decision 57): rule statement-context.

Finding (b) of the independent re-test of the fourth repair: rule same-quantity read a figure as the request's statement
of the premise's quantity "as the premise states it" without reading how the request states it. So a numeric p-proves-p
translation whose figure the request states only under a negation ("Explain why the extract does not mention 3
workers."), in a yes/no question ("Does the extract mention 3 workers?") or as a requirement on the answer ("Your answer
should be 80 words long.", the claim "the answer is 80 words long") was undecided, graded OVS-TRN-011 (a warning), the
transfer cleared and the router was shown ENTAILED.

Rule statement-context (``checks.translation.figure_context``) reads the context of every place a source states a
figure: only a statement states it as the source's own. A yes/no or embedded question (or a yes/no clause of a
wh-question), a negation before the figure in its clause (a negative word, or a verb or frame that denies: "fails to
mention", "It is false that"; or, after the figure, one negating what the premise says), one of alternatives joined by
"or", a claim the answer must examine (named as one, or put up by a prompt after it: "Discuss.", "To what extent do you
agree?"), a requirement on the answer and the value of a limit or target do not; a requirement or a limit is read only
for a premise whose statement names one. Data in an instruction, a supposition, a wh-question's presupposition, a negated
bound and a figure restated after ", or" in another unit stay statements. The same reading applies to a located excerpt
(it states the figure in its document's sentence).

No model is called; translations come from the translator's own pipeline with the fixture provider.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.overseer.checks import translation as T
from epinoic_logic.translate.contracts import SuppliedText

from .conftest import DOC, EN_TEXT, english_report
from .test_protocol_validate import review
from .test_repair3_same_quantity import _run_on
from .test_translation_agents import outcome_of, tr_acc
from .test_translation_oversight import POINT, V, trn

TS = {"kind": "task_setting"}


def _count(value: str, label: str, meaning: str, *, op: str = "eq", grounding: dict = TS) -> dict:
    """The point's own figure ``n <op> value`` assumed as its only premise (the review's probe): the premise, the symbol and
    the conclusion grounded the same way, no excerpt."""
    c = {"op": op, "left": V("n"), "right": {"op": "int", "value": value}}
    return {"problem_id": "p-ctx", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment",
            "symbols": [{"name": "n", "sort": "Int", "meaning": meaning, "grounding": dict(grounding)}],
            "premises": [{"id": "a_x", "expr": c, "label": label, "grounding": dict(grounding)}],
            "conclusion": {"id": "C", "expr": c, "label": label, "grounding": dict(grounding)}}


WORKERS = ("3", "the extract mentions 3 workers", "the number of workers in the extract")
WORDS = ("80", "the answer is 80 words long", "the number of words of the answer")


# ============================================================================================ the review's probe, end to end
@pytest.mark.parametrize("case, user_input, figure, context", [
    ("negation", "Analyse the extract. Explain why the extract does not mention 3 workers.", WORKERS, "under a negation"),
    ("yes/no question", "Analyse the extract. Does the extract mention 3 workers? Write no more than 80 words.", WORKERS, "in a yes/no question"),
    ("requirement on the answer", "Analyse how the writer presents work in the extract. Your answer should be 80 words long.", WORDS,
     "as a requirement on the answer"),
    # the same class in other forms
    ("negation after the figure, of what the premise states", "Analyse the extract. Explain why 3 workers are not mentioned in the extract.", WORKERS,
     "under a negation"),
    ("embedded yes/no question", "Analyse the extract. Discuss whether the extract mentions 3 workers.", WORKERS, "in a yes/no question"),
    ("claim the answer must examine", "Analyse the extract. Evaluate the claim that the extract mentions 3 workers.", WORKERS,
     "inside a claim the answer must examine"),
    ("instruction counting what the answer must contain", "Analyse how the writer presents work in the extract. Write 80 words.", WORDS,
     "as a requirement on the answer"),
    ("limit set on the answer", "Analyse how the writer presents work in the extract. The word limit is 80 words.", WORDS,
     "as the value of a limit or target set on a quantity"),
    # the bound form: the request parser records "no more than 80 words" as a constraint on the answer, whose text, read
    # alone, would look like a statement of a bound (the tampering case T22ad found it)
    ("requirement on the answer, a bound", "Analyse how the writer presents work in the extract. Write no more than 80 words.",
     ("80", "the paragraph has no more than 80 words", "the number of words of the paragraph", "le"), "as a requirement on the answer"),
    # further forms of the same class, found probing the reader: a negation by a verb or a frame, a figure offered as one
    # of alternatives, a yes/no clause of a wh-question, and a claim a prompt after it puts up for examination
    ("negation by a verb", "Analyse the extract. Explain why the extract fails to mention 3 workers.", WORKERS, "under a negation"),
    ("negation by a frame", "Analyse the extract. It is false that the extract mentions 3 workers.", WORKERS, "under a negation"),
    ("one of alternatives", "Analyse the extract. Which is right, 3 workers or 4 workers?", WORKERS, "as one of alternatives"),
    ("one of alternatives, stated", "Analyse the extract. The extract mentions 3 workers or 4 workers.", WORKERS, "as one of alternatives"),
    ("yes/no clause of a wh-question", "Analyse the extract. How many workers does the extract mention, or is it 3 workers?", WORKERS,
     "in a yes/no question"),
    ("claim a prompt puts up for examination", "Analyse the extract. The extract mentions 3 workers. To what extent do you agree?", WORKERS,
     "inside a claim the answer must examine"),
    ("quotation a prompt puts up for examination", 'Analyse the extract. "The extract mentions 3 workers." Discuss.', WORKERS,
     "inside a claim the answer must examine"),
])
def test_a_figure_the_request_does_not_state_as_a_statement_never_reads_p_proves_p_as_data(case, user_input, figure, context):
    """The review's probe and its class. The merged translator delivers the encoding (its rule reads the task_setting label
    as a transcription) and the engine gives ENTAILED: the router is shown ENTAILED. The request states the figure only
    where it asks, denies, puts up for examination, requires or limits it, so no check reads the premise as data: it is
    shown not to be data (uncheckable), the result rests on it, and the grade is OVS-TRN-006, the transfer AUDIT_FAILED,
    an agent's translation_circular accusation CONFIRMED. The fourth repair's code gave OVS-TRN-011 and
    AUDIT_PASSED_WITH_FINDINGS for each."""
    value, label, meaning, *op = figure
    aud, ch, rc = _run_on(user_input, _count(value, label, meaning, op=op[0] if op else "eq"))
    try:
        o = next(x for x in rc.outcomes if x.claim_id == POINT)
        assert o.translation.status.value == "TRANSLATED" and o.verification.status.value == "ENTAILED" and not o.verification.diagnostics
        assert o.display_status.value == "ENTAILED"  # what the router is shown
        a = aud.audit(ch.uid)
        (f,) = trn(a, "OVS-TRN-006")
        assert f.severity == "error" and f.claim_ids == [POINT] and "a_x" in f.message and f.related_result_ids, f.message
        assert "engine-shown" in f.message and "data-standing" in f.message
        assert trn(a, "OVS-TRN-011") == [] and a.transfer_states[rc.message_id] == "AUDIT_FAILED"
        # the reason, in the audit note, names the rule and the context
        view = aud.view(ch.uid)
        t = next(x for x in view.transfers if x.message_id == rc.message_id)
        reason = dict(T.restatement(o.translation.problem, t.report, T._request_texts(view, t), request_documents=T._request_documents(view, t),
                                    request_constraints=T._request_constraints(view, t)).why_own)["a_x"]
        assert T.CONTEXT_RULE in reason and context in reason and "the kind label is then the only evidence" in reason, reason
        r = review(aud, ch.uid)
        acc = outcome_of(r.run([tr_acc(r.dossier, "translation_circular")]))
        assert acc.outcome == "confirmed" and [c.code for c in acc.confirming] == ["OVS-TRN-006"]
    finally:
        aud.close()


@pytest.mark.parametrize("case, user_input, figure, grade", [
    # the request STATES the figure for the premise's quantity: undecided, a data conjunct needs its data premise (warning)
    ("a statement beside a word limit", "Analyse the extract. The extract mentions 3 workers. Write no more than 80 words.", WORKERS, "OVS-TRN-011"),
    ("what a wh-question presupposes", "Analyse the extract. Why does the extract mention 3 workers?", WORKERS, "OVS-TRN-011"),
    ("a statement before a question", "Analyse the extract. The extract mentions 3 workers; which of them speaks?", WORKERS, "OVS-TRN-011"),
    ("a requirement the premise states as one", "Analyse how the writer presents work in the extract. Your answer should be 80 words long.",
     ("80", "the required length is 80 words", "the number of words the answer should have"), "OVS-TRN-011"),
    ("a limit the premise names", "Analyse how the writer presents work in the extract. The word limit is 80 words.",
     ("80", "the word limit is 80 words", "the word limit of the task"), "OVS-TRN-011"),
    ("a statement a topic instruction follows", "Analyse the extract. The extract mentions 3 workers. Discuss the role of the workers.", WORKERS,
     "OVS-TRN-011"),
    ("a verb whose object is a count of its own", "Analyse the extract. The extract omits 3 workers.",
     ("3", "the extract omits 3 workers", "the number of workers the extract omits"), "OVS-TRN-011"),
    ("figures joined by 'and'", "Analyse the extract. The extract mentions 3 workers and 4 managers.", WORKERS, "OVS-TRN-011"),
    # controls kept from the review: a show-that target and a figure stated only bare stay OVS-TRN-006
    ("a show-that target", "Analyse the extract. Show that the extract mentions 3 workers.", WORKERS, "OVS-TRN-006"),
    ("an N-word compound (bare)", "Analyse how the writer presents work in the extract. Write an 80-word answer.",
     ("80", "the answer has 80 words", "the number of words of the answer"), "OVS-TRN-006"),
])
def test_control_a_statement_of_the_figure_stays_undecided_and_the_reviews_controls_stay_circular(case, user_input, figure, grade):
    value, label, meaning = figure
    aud, ch, rc = _run_on(user_input, _count(value, label, meaning))
    try:
        a = aud.audit(ch.uid)
        codes = sorted({f.code for f in trn(a) if f.code in ("OVS-TRN-006", "OVS-TRN-010", "OVS-TRN-011")})
        assert codes == [grade], (case, codes)
        assert a.transfer_states[rc.message_id] == ("AUDIT_FAILED" if grade == "OVS-TRN-006" else "AUDIT_PASSED_WITH_FINDINGS")
    finally:
        aud.close()


# ============================================================================================ rule statement-context
@pytest.mark.parametrize("text, figure, context", [
    # questions: a yes/no question asks, never states; an embedded one too
    ("Does the extract mention 3 workers?", "3", "question"),
    ("¿El extracto menciona 3 trabajadores?", "3", "question"),
    ("Is the speed 8 m/s?", "8", "question"),
    ("Discuss whether 3 workers are enough.", "3", "question"),
    ("Determine if the speed is 8 m/s.", "8", "question"),
    ("The extract mentions 3 workers; does it name 4 children?", "4", "question"),
    # negations: before the figure in its clause
    ("Explain why the extract does not mention 3 workers.", "3", "negation"),
    ("The extract doesn't mention 3 workers.", "3", "negation"),
    ("The extract never names 3 workers.", "3", "negation"),
    ("The extract mentions not 3 but 4 workers.", "3", "negation"),
    # a claim the answer must examine
    ("Evaluate the claim that the Act banned children under 9.", "9", "examined"),
    ("To what extent do you agree that the extract mentions 3 workers?", "3", "examined"),
    # requirements on the answer
    ("Your answer should be 80 words long.", "80", "requirement"),
    ("Your answer must not exceed 80 words.", "80", "requirement"),
    ("You must use 3 quotations.", "3", "requirement"),
    ("You may use up to 3 sources.", "3", "requirement"),
    ("Write 80 words.", "80", "requirement"),
    ("Write no more than 80 words.", "80", "requirement"),
    ("Write an 80-word answer.", "80", "requirement"),
    ("Give 3 reasons.", "3", "requirement"),
    ("Identify 2 techniques the writer uses.", "2", "requirement"),
    ("Give your answer to 3 significant figures.", "3", "requirement"),
    ("Limit your answer to 80 words.", "80", "requirement"),
    ("Write one body paragraph only, following your method, in no more than 350 words.", "350", "requirement"),
    ("In one paragraph of no more than 200 words, outline for that student the historical context.", "200", "requirement"),
    ("[3] Answer each part in no more than 300 words in total.", "300", "requirement"),
    ("Please write a model answer in no more than 200 words.", "200", "requirement"),
    # the value of a limit or target set on a quantity
    ("The word limit is 80 words.", "80", "limit"),
    ("Kestria's central bank aims to bring inflation back towards its target of 2 per cent.", "2", "limit"),
    ("Maximum 80 words.", "80", "limit"),
    # statements: data in an instruction, a supposition, a wh-question's presupposition, a negated bound
    ("The extract mentions 3 workers.", "3", "statement"),
    ("Find the value of Kai's investment after 5 years.", "5", "statement"),
    ("Find the number of complete years until the value of the investment first exceeds 6000 euros.", "6000", "statement"),
    ("Use g = 9.8 m s-2.", "9.8", "statement"),
    ("You must use g = 9.8 m s-2.", "9.8", "statement"),
    ("Calculate 5% of 300.", "300", "statement"),
    ("Solve 3x + 2 = 8.", "3", "statement"),
    ("Convert 5 metres to centimetres.", "5", "statement"),
    ("If the car travels 8 m in 2 s, find its speed.", "8", "statement"),
    ("Assume 3 workers are present.", "3", "statement"),
    ("Why does the extract mention 3 workers?", "3", "statement"),
    ("To what extent was the Great Leap Forward responsible for the famine in China between 1959 and 1961?", "1959", "statement"),
    ("My research question is: 'How does the temperature, from 20 °C to 60 °C, affect the time taken?", "20", "statement"),
    ("The extract mentions 3 workers; which of them speaks?", "3", "statement"),
    ("The ball does not exceed 5 m.", "5", "statement"),
    ("The extract mentions no more than 3 workers.", "3", "statement"),
    ("Write about the hours: 12 hours a day.", "12", "statement"),
    ("I'm an SL History student sitting my exams in May 2027.", "2027", "statement"),
    ("Compare the maximum number of passes this algorithm needs for a sorted list of 1,000 items with a linear search.", "1,000", "statement"),
    ("Paper 1 (no calculator): a particle moves 8 m in 2 s.", "8", "statement"),
    # further forms (the probe of the reader): questions
    ("How many workers does the extract mention, or is it 3?", "3", "question"),
    ("How many workers does the extract mention — is it 3?", "3", "question"),
    ("How many workers does the extract mention, is it 3?", "3", "question"),
    ("How many workers does the extract mention, and does it name 3 of them?", "3", "question"),
    ("Was the Act passed in 1833 or 1834?", "1833", "question"),
    # negations by a verb or a frame
    ("The extract fails to mention 3 workers.", "3", "negation"),
    ("The writer neglects to name 3 workers.", "3", "negation"),
    ("It is false that the extract mentions 3 workers.", "3", "negation"),
    ("The extract denies that 3 workers were present.", "3", "negation"),
    # alternatives
    ("The extract mentions 3 workers or 4 workers.", "3", "alternative"),
    ("The extract mentions 3 workers or 4 workers.", "4", "alternative"),
    ("Which is right, 3 workers or 4 workers?", "4", "alternative"),
    ("The Act was passed in 1833 or 1834.", "1834", "alternative"),
    ("Either 3 or 4 workers are named.", "3", "alternative"),
    ("The mill employed 3 workers, or perhaps 4.", "3", "alternative"),
    # claims a prompt after them puts up for examination
    ("The extract mentions 3 workers. To what extent do you agree?", "3", "examined"),
    ("The extract mentions 3 workers. How far is this view valid?", "3", "examined"),
    ("Some readers claim the extract mentions 3 workers. Do you agree?", "3", "examined"),
    ('"The extract mentions 3 workers." Discuss.', "3", "examined"),
    ("\u201cThe mill employed 3 workers. It was the largest in the valley.\u201d Discuss with reference to the extract.", "3", "examined"),
    ("Discuss: the extract mentions 3 workers.", "3", "examined"),
    ("The extract mentions 3 workers.\nEvaluate this claim.", "3", "examined"),
    # ... and the controls: statements
    ("The extract omits 3 workers.", "3", "statement"),
    ("The extract mentions 3 workers and 4 managers.", "3", "statement"),
    ("The extract mentions 3 or more workers.", "3", "statement"),
    # ", or" alone restates the same quantity another way (a recorded r7 supplied text): both are stated
    ("Result: consumers bear $0.30 per litre, or $31.50 million per year (75% of the tax).", "0.30", "statement"),
    ("Result: consumers bear $0.30 per litre, or $31.50 million per year (75% of the tax).", "31.50", "statement"),
    ("Either 3 workers, or 4, are named.", "4", "alternative"),
    ("The extract mentions 3 workers. Discuss the role of the workers.", "3", "statement"),
    ("A particle moves 8 m. Discuss whether it stops.", "8", "statement"),
    ("The car travels 8 m in 2 s. Evaluate its speed.", "8", "statement"),
    ("Consider the following data: the car travels 8 m in 2 s.", "8", "statement"),
    ("The extract mentions 3 workers.\n\nTo what extent do you agree?", "3", "statement"),
    ("Why does the extract mention 3 workers, and what does it say of them?", "3", "statement"),
])
def test_rule_statement_context_reads_how_the_source_states_each_figure(text, figure, context):
    i = text.index(figure)
    got, phrase = T.figure_context(text, i, i + len(figure))
    assert got == context, (text, got)
    assert (phrase == "") == (context == "statement")


@pytest.mark.parametrize("text, figure, negates", [
    ("3 workers are not mentioned in the extract.", "3", ("mention",)),
    ("Assumption: the background of 20 counts min⁻¹ is constant and has no uncertainty.", "20", ("uncertainty",)),
    ("The extract mentions 3 workers, but not their names.", "3", ()),
    ("The ball does not exceed 5 m.", "5", ()),
])
def test_rule_statement_context_reads_what_a_negation_after_the_figure_negates(text, figure, negates):
    i = text.index(figure)
    assert T.figure_negates(text, i, i + len(figure)) == negates


def test_a_negation_after_the_figure_reaches_only_a_premise_saying_what_it_negates():
    """'3 workers are not mentioned' negates what 'the extract mentions 3 workers' says, so that premise is not read; the
    background of 20 counts min⁻¹ 'has no uncertainty' negates nothing a premise about the background count states."""
    neg = T.figure_reading(Fraction(3), ["3 workers are not mentioned in the extract."], "the extract mentions 3 workers ; the number of workers", {"eq"})
    assert neg.kind == T.FIGURE_UNREAD and neg.context == T.CONTEXT_NEGATION and "which negates what the premise states (mention)" in neg.reason
    bg = T.figure_reading(Fraction(20), ["Assumption: the background of 20 counts min⁻¹ is constant and has no uncertainty."],
                          "the background count rate is 20 counts min⁻¹", {"eq"})
    assert bg.kind == T.FIGURE_READ and bg.context is None, bg.reason


LIMIT_REQUESTS = ("Write no more than 80 words.", "Your answer should be no more than 80 words.", "The word limit is 80 words.")


@pytest.mark.parametrize("request_text, statement, relations, kind", [
    # a requirement or a limit is read only for a premise whose statement names one (their value) ...
    *[(r, "the word limit is 80 words", {"eq"}, "read") for r in LIMIT_REQUESTS],
    *[(r, "the answer must have at most 80 words", {"le"}, "read") for r in LIMIT_REQUESTS],
    ("Your answer should be 80 words long.", "the required length is 80 words", {"eq"}, "read"),
    # ... never for the quantity it is set on (rule statement-context keeps it unread) ...
    *[(r, "the paragraph has at most 80 words ; the number of words of the paragraph", {"le"}, "requirement or limit") for r in LIMIT_REQUESTS],
    ("Your answer should be 80 words long.", "the answer is 80 words long", {"eq"}, "requirement or limit"),
    ("The word limit is 80 words.", "the answer is 80 words long", {"eq"}, "requirement or limit"),
    # ... and a value read from a bound is refuted by rule same-quantity, as before (a maximum is not a required length)
    ("Write no more than 80 words.", "the required length is 80 words", {"eq"}, "refuted"),
    ("Write no more than 80 words.", "the answer is 80 words long", {"eq"}, "refuted"),
])
def test_rule_statement_context_reads_a_requirement_only_for_a_premise_that_states_one(request_text, statement, relations, kind):
    r = T.figure_reading(Fraction(80), [request_text], statement, relations)
    if kind == "read":
        assert r.kind == T.FIGURE_READ and r.context is None, (request_text, statement, r.reason)
    elif kind == "refuted":
        assert r.kind == T.FIGURE_REFUTED and "only as a bound" in r.reason, (request_text, statement, r.reason)
    else:
        assert r.kind == T.FIGURE_UNREAD and r.context in (T.CONTEXT_REQUIREMENT, T.CONTEXT_LIMIT), (request_text, statement, r.reason)
        assert T.CONTEXT_RULE in r.reason and "names no requirement or limit" in r.reason, r.reason


def test_a_constraint_text_states_its_figures_as_requirements_on_the_answer():
    """The request parser records each constraint with the request's own words ("no more than 80 words"); the audit holds
    those texts beside the input. Read alone such a fragment looks like a statement of a bound, so rule statement-context
    reads every figure of a constraint text as a requirement on the answer (``request_constraints``), as its own sentence
    in the request states it. Without the marking the fragment would read the paragraph's own count as data."""
    p = Problem.model_validate(_count("80", "the paragraph has no more than 80 words", "the number of words of the paragraph", op="le"))
    texts = ["Analyse how the writer presents work in the extract.", "no more than 80 words"]
    marked = T.restatement(p, english_report(), texts, request_constraints=["no more than 80 words"])
    assert marked.standings == (("a_x", "uncheckable"),) and "a constraint on the answer" in dict(marked.why_own)["a_x"]
    unmarked = T.restatement(p, english_report(), texts)
    assert unmarked.standings == (("a_x", "undecided"),)  # what the marking is for
    # a premise naming the limit reads the constraint's figure as the limit's value
    q = Problem.model_validate(_count("80", "the word limit is 80 words", "the word limit of the task"))
    assert T.restatement(q, english_report(), texts, request_constraints=["no more than 80 words"]).standings == (("a_x", "undecided"),)


def test_the_bound_form_of_the_review_s_requirement_case_is_shown_not_to_be_data():
    """The review's requirement case in its bound form (the fourth repair's control pinned it undecided): the paragraph's
    own count assumed as 'at most 80' beside 'Write no more than 80 words'. The request requires it, never states it, so
    the premise is uncheckable and a result resting on it is OVS-TRN-006."""
    p = Problem.model_validate(_count("80", "the paragraph has no more than 80 words", "the number of words of the paragraph", op="le"))
    rs = T.restatement(p, english_report(), ["Write no more than 80 words."])
    assert rs.standings == (("a_x", "uncheckable"),) and rs.shown == ("a_x",) and rs.undecided == ()
    reason = dict(rs.why_own)["a_x"]
    assert "as a requirement on the answer" in reason and T.CONTEXT_RULE in reason


# ============================================================================================ a located excerpt
def _quoted_count(excerpt: str, label: str = "the extract mentions 3 workers", meaning: str = "the number of workers the extract mentions") -> Problem:
    c = {"op": "eq", "left": V("n"), "right": {"op": "int", "value": "3"}}
    return Problem.model_validate({"problem_id": "p-q", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment",
                                   "symbols": [{"name": "n", "sort": "Int", "meaning": meaning}],
                                   "premises": [{"id": "P", "expr": c, "label": label,
                                                 "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc-q", "excerpt": excerpt}]}}],
                                   "conclusion": {"id": "C", "expr": c, "label": label}})


@pytest.mark.parametrize("doc_text, excerpt, standing, why", [
    ("The foreman does not mention 3 workers by name.", "mention 3 workers", "refuted", "under a negation"),
    ("Does the foreman mention 3 workers? He does not say.", "the foreman mention 3 workers", "refuted", "in a yes/no question"),
    ("Evaluate the claim that the foreman names 3 workers.", "the foreman names 3 workers", "refuted", "inside a claim the answer must examine"),
    # controls: the figure stated as data is a transcription, as before (a located excerpt is the evidence, decision 49)
    ("The foreman names 3 workers by the gate.", "names 3 workers", "transcription", ""),
    ("The foreman does not mention 3 workers by name. The foreman names 3 workers by the gate.", "names 3 workers", "transcription", ""),
])
def test_rule_statement_context_reads_a_located_excerpt_in_its_document(doc_text, excerpt, standing, why):
    """A quotation whose excerpt the grounding check locates is no transcription when the document states the figure there
    only under a negation, in a yes/no question or inside a claim the answer must examine (read in the document: the
    excerpt may cut its sentence). The control locates the same excerpt in a statement."""
    doc = SuppliedText(document_id="doc-q", title="Notes", author="Board", text=doc_text)
    rs = T.restatement(_quoted_count(excerpt), english_report(EN_TEXT + " The foreman names 3 workers.", docs=(DOC, doc)), [])
    assert rs.standings == (("P", standing),), (doc_text, rs.why_own)
    if standing == "refuted":
        reason = dict(rs.why_own)["P"]
        assert rs.holds and rs.shown == ("P",) and why in reason and T.CONTEXT_RULE in reason, reason
    else:
        assert not rs.holds and rs.grounded == ("P",)


def test_control_a_located_excerpt_naming_its_quantity_before_the_figure_stays_a_transcription():
    """Rule statement-context reads no quantity in an excerpt: the recorded r7 excerpts name it before the figure ("PED =
    −12.50 ÷ 18.75 = −0.67", "Pc = $1.90 per litre"), which rule same-quantity (the word after a figure) does not read,
    so their verified excerpts stay the transcription evidence (decision 49).

    The document's author is a source that is not a specialist ("Board"): since the round-7 core fix (security-2) a text
    a specialist wrote (``translate.grounding.is_peer_document``: a relayed peer report) gives a premise no source
    authority, so the same excerpt in the Economics specialist's report is no transcription; that case is pinned below as
    well. (Rewritten to the stricter rule: the statement-context control keeps its standing, and the peer case's standing
    is asserted in addition.)"""
    c = {"op": "eq", "left": V("ped"), "right": {"op": "real", "value": "-0.67"}}
    p = Problem.model_validate({"problem_id": "p-ped", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment",
                                "symbols": [{"name": "ped", "sort": "Real", "meaning": "price elasticity of demand as given by the Economics specialist"}],
                                "premises": [{"id": "a_ped", "expr": c, "label": "price elasticity of demand as given by the Economics specialist",
                                              "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc-q", "excerpt": "PED = −12.50 ÷ 18.75 = −0.67"}]}}],
                                "conclusion": {"id": "C", "expr": c, "label": "PED is -0.67"}})
    text = "PED = −12.50 ÷ 18.75 = −0.67\nResult: demand is price inelastic."
    doc = SuppliedText(document_id="doc-q", title="Notes", author="Board", text=text)
    rs = T.restatement(p, english_report(EN_TEXT + " PED = −0.67.", docs=(DOC, doc)), [])
    assert rs.standings == (("a_ped", "transcription"),) and not rs.holds
    peer = SuppliedText(document_id="doc-q", title="Peer", author="Economics specialist", text=text)
    rs = T.restatement(p, english_report(EN_TEXT + " PED = −0.67.", docs=(DOC, peer)), [])
    assert rs.standings == (("a_ped", "own_kind"),) and rs.holds, rs.why_own
