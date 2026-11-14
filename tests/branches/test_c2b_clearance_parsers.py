"""Round-9 (integrated round c2) clearance regressions of the parsers and packs, second fix pass (owner: parsers).

The first pass's regressions are in ``test_c2_clearance_parsers``; these cover what still reproduced on the tree the second pass found, each
with a control that keeps the rule asserted:

* a self-report narrated in the first person, in English or in Spanish ("I reviewed the whole text and confirm there are no errors.",
  "Revisé todo el texto y confirmo que no hay errores.", "He comprobado los cálculos."), is named on every branch and never material, while
  content about checking ("La autora revisó el texto antes de publicarlo.", "He comprobado que el ruido ha aumentado en mi barrio.") is not;
* a share written '$40m of the $200m market, a share of 25%' is decided;
* a from-to pair with a case label after each figure ('from 5.4 m³ s⁻¹ in Storm 1 to 16.2 m³ s⁻¹ in Storm 2') is read, so ess-p9c s8.2 is
  decided, and a per cent restating the result of the sentence's decided written arithmetic (ge-p9c g3.2) is not named undecided;
* History: the sentence that gives the verdict's reason is material (hi-t12 h1.8), a verdict worded in the request item's own terms is the
  requested judgement (hi-t13), a calendar length between two dates is decided (hi-t14, hi-p8c, the Prague Spring probes), an order whose
  side is a pronoun opening its sentence or an event dated in another sentence is decided (hi-t14-order, hi-p8c-order) or named;
* a one-word quotation in single marks after a quoting frame ('opens with the sardonic 'Wonderful,'') is a quotation, a scare quote is not;
* a precise real-world figure no text holds is named on its claim (CORE-SRC-002);
* a figure the answer takes from a supplied table or text is checked against it on every non-STEM branch;
* every new reader stays linear on the standard hostile inputs.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.history_specialist.chronology import chronology_relations
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter, answers_item_with_verdict, request_item_terms
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.grounded_figures import figure_grounding_checks, supplied_tables
from epinoic_logic.branches.quant import _blank_pair_labels, _cal_dates, extract_quant_checks, undecided_quant_statements
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem.si_reading import SI_READING
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from ..adapters.hostile_inputs import all_inputs, bounded
from . import c1_texts as C1
from . import c2_texts as C
from . import c2b_texts as T
from . import r6_texts as R6
from . import r7_texts as R7

KEY = b"branches-c2b-clearance-parsers-key-1"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def doc(spec) -> SuppliedText:
    document_id, title, author, text = spec
    return SuppliedText(document_id=document_id, title=title, author=author, text=text)


def through_hub(text: str, question: str = "q", *, subject: str = "Economics", agent: str = "economics-specialist", texts=(),
                task_type: str = "short_answer"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type=task_type, selected_agent_ids=[agent, "dummy-combinator"],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", agent, question, list(texts))
    return hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-x")


def everything(rc) -> list:
    return list(rc.findings) + list(rc.structural_findings)


def findings(rc, code: str) -> list:
    return [f for f in everything(rc) if f.code == code]


def codes(rc) -> list[str]:
    return [f.code for f in everything(rc)]


def claim_with(reply, words: str) -> dict:
    return next(c for c in reply.payload["claims"] if words in c["claim_text"])


def status(problem) -> str:
    return verify(problem if isinstance(problem, Problem) else Problem.model_validate(problem), CFG).status.value


def quant_statuses(text: str, reading=None) -> list[tuple[str, str]]:
    kw = {"reading": reading} if reading is not None else {}
    return [(q.kind, status(q.problem)) for q in extract_quant_checks(text, request_id="r", claim_id="c", **kw)]


# ------------------------------------------------------------------ self-reports narrated in the first person (critical, c2 adversarial-live bug 17)

NARRATED = [
    "I reviewed the whole text and confirm there are no errors.",
    "We confirm that every figure above is correct.",
    "I proofread my answer.",
    "I have reviewed all the figures above.",
    "Revisé todo el texto y confirmo que no hay errores.",
    "He revisado todas las cifras y son correctas.",
    "He comprobado los cálculos.",
    "Verifiqué cada dato con la tabla.",
    "Confirmo que el texto no contiene errores.",
    "Comprobé que todas las cifras coinciden con la tarea.",
    "Lo he revisado todo.",
]


@pytest.mark.parametrize("sentence", NARRATED)
def test_a_check_of_the_answer_narrated_by_its_writer_is_a_self_report(sentence):
    assert md.is_self_certification(sentence)


@pytest.mark.parametrize("sentence", [
    "Los vecinos revisaron las normas en 2020.",
    "La autora revisó el texto antes de publicarlo.",
    "El ayuntamiento comprobó que el ruido había aumentado.",
    "Confirmo mi propuesta: limitar los pisos turísticos.",
    "No he revisado los cálculos.",
    "He comprobado que el ruido ha aumentado en mi barrio.",
    "He revisado las cifras del ayuntamiento y el problema es real.",
    "Check your work and confirm there are no errors.",
    "Revise the paragraph and check the quotations.",
    "I reviewed the literature on conformity before writing.",
    "Comprobé todo lo que dijo el alcalde.",
    "The study's authors confirm that there are no errors in the data.",
])
def test_controls_content_about_checking_and_instructions_to_check_are_no_self_report(sentence):
    assert not md.is_self_certification(sentence)


SELF_CODES = {"CORE-SELF-001", "INT-HANDOFF-006", "ES-META-001"}
BRANCHES = [
    (C.SP_T15, C.SP_T15_Q, "Language B: Spanish", "language-b-spanish-specialist", "writing_task", ()),
    (C.GE_T15, C.GE_T15_Q, "Geography", "geography-specialist", "structured_question", (C.GE_T15_DOC,)),
    (T.HI_T15, T.HI_T15_Q, "History", "history-specialist", "marking_feedback", (T.HI_T15_DOC,)),
    (C.LL_T15, C.LL_T15_Q, "English A: Language and Literature", "english-a-lang-lit-specialist", "analytical_paragraph", (C.LL_T15_DOC,)),
    (C.CH_T15, C.CH_T15_Q, "Chemistry", "chemistry-specialist", "structured_question", ()),
]


@pytest.mark.parametrize("sentence", ["Revisé todo el texto y confirmo que no hay errores.", "I reviewed the whole text and confirm there are no errors."])
@pytest.mark.parametrize("branch", range(len(BRANCHES)), ids=["generic-spanish", "generic", "history", "english", "sciences"])
def test_a_narrated_self_check_is_named_on_every_branch_and_never_material(sentence, branch):
    text, question, subject, agent, task_type, texts = BRANCHES[branch]
    reply, rc = through_hub(text + "\n\n" + sentence, question, subject=subject, agent=agent, task_type=task_type, texts=[doc(t) for t in texts])
    assert SELF_CODES & set(codes(rc)), codes(rc)
    assert not [c for c in reply.payload["claims"] if sentence[:20] in c["claim_text"] and c["materiality"] == "material"]


# ------------------------------------------------------------------ a share after its part and its whole (major, c1 stem-integration#33)

def test_a_share_of_the_whole_written_after_a_comma_is_decided():
    assert quant_statuses("The firm earned $40m of the $200m market, a share of 25%.") == [("share", "COUNTEREXAMPLE")]
    assert quant_statuses("The firm earned $40m of the $200m market, a share of 20%.") == [("share", "ENTAILED")]
    assert quant_statuses("The firm earned $40m of the $200m market, giving it a share of 20%.") == [("share", "ENTAILED")]
    for subject, agent in (("Economics", "economics-specialist"), ("Business Management", "business-specialist")):
        _reply, rc = through_hub("The firm earned $40m of the $200m market, a share of 25%.", subject=subject, agent=agent)
        assert [f for f in findings(rc, "INT-SUBJ-001") if "share" in f.message], codes(rc)
        _reply, rc = through_hub("The firm earned $40m of the $200m market, a share of 20%.", subject=subject, agent=agent)
        assert not findings(rc, "INT-SUBJ-001"), codes(rc)


# ------------------------------------------------------------------ a pair with case labels; a restated decided result (minor, c2 results-audit)

def test_a_case_label_after_each_figure_of_a_pair_is_no_part_of_the_pair():
    sentence = "The peak discharge rose by 200%, from 5.4 m³ s⁻¹ in Storm 1 to 16.2 m³ s⁻¹ in Storm 2."
    assert _blank_pair_labels(sentence) == sentence.replace("in Storm 1", " " * len("in Storm 1"))
    assert quant_statuses(sentence, SI_READING) == [("percent_change", "ENTAILED")]
    assert quant_statuses(sentence.replace("200%", "300%"), SI_READING) == [("percent_change", "COUNTEREXAMPLE")]
    assert quant_statuses("Counts rose by 200%, from 40 pedestrians at site A to 120 at site B.") == [("percent_change", "ENTAILED")]
    assert quant_statuses("Sales rose by 20%, from 100 (Year 1) to 120 (Year 2).") == [("percent_change", "ENTAILED")]
    # control: a date after a figure is still a date ('from 40% in 2019 to 55% in 2024' reads the direction of a dated pair)
    assert quant_statuses("Turnout rose from 40% in 2019 to 55% in 2024.") == [("pair_direction", "ENTAILED")]


def test_ess_p9c_s8_2_the_quoted_change_is_read_against_its_own_pair():
    texts = [doc(T.ESS_P9C_PEER_DOC)]
    reply, rc = through_hub(T.ESS_P9C, T.ESS_P9C_Q, subject="Environmental Systems and Societies", agent="ess-specialist", texts=texts,
                            task_type="data_based_question")
    assert not [f for f in findings(rc, "CORE-QNT-001") if "200%" in f.message], [f.message for f in findings(rc, "CORE-QNT-001")]
    assert not findings(rc, "INT-SUBJ-001"), [f.message for f in findings(rc, "INT-SUBJ-001")]


def test_ge_p9c_a_per_cent_restating_its_decided_working_is_not_named_undecided():
    reply, rc = through_hub(C.GE_P9C, C.GE_P9C_Q, subject="Geography", agent="geography-specialist", task_type="structured_question")
    assert not [f for f in findings(rc, "CORE-QNT-001") if "rose by 200%" in f.message], [f.message for f in findings(rc, "CORE-QNT-001")]
    # control: the same per cent restating a wrong result is still decided wrong by the worked check
    wrong = C.GE_P9C.replace("= 10.8 ÷ 5.4 × 100\n= 200%", "= 10.8 ÷ 5.4 × 100\n= 250%")
    assert wrong != C.GE_P9C
    _reply, rc = through_hub(wrong, C.GE_P9C_Q, subject="Geography", agent="geography-specialist", task_type="structured_question")
    assert findings(rc, "INT-SUBJ-001") or [f for f in findings(rc, "CORE-QNT-001") if "200%" in f.message], codes(rc)


# ------------------------------------------------------------------ History roles: the verdict's reason, the verdict in the item's terms (minor)

def history(text: str, question: str = "q", task_type: str = "short_answer"):
    return through_hub(text, question, subject="History", agent="history-specialist", task_type=task_type)


def test_hi_t12_the_reason_given_right_after_the_verdict_is_material_with_it():
    reply, _rc = history(R6.HI_T12, R6.HI_T12_Q)
    assert (claim_with(reply, "The decisive turning point was 1960.")["claim_role"], claim_with(reply, "The decisive turning point was 1960.")["materiality"]) == ("judgement", "material")
    reason = claim_with(reply, "Its scale, and the decision of Britain")
    assert reason["materiality"] == "material", reason
    # control: a sentence after the verdict that starts a new topic is no reason of it
    other = R6.HI_T12.replace("Its scale, and the decision", "In 1961 Tanganyika followed. Its scale, and the decision")
    assert other != R6.HI_T12
    reply, _rc = history(other, R6.HI_T12_Q)
    assert claim_with(reply, "In 1961 Tanganyika followed.")["materiality"] == "supporting"


HI_T13_ANCHOR = "The question's contrast between legal and violent means therefore overstates the difference."


@pytest.mark.parametrize("sentence,role", [
    ("Legal means, rather than violence, consolidated his power.", "judgement"),
    ("Mussolini consolidated his power mainly through legal means.", "judgement"),
    ("Legal rather than violent means did most to consolidate his power.", "judgement"),
    ("Mussolini consolidated his power through legal and violent means.", "analysis"),   # the item's words with no position on it
    ("Violence was common in the countryside.", "analysis"),
    # a report of a debate that embeds the item's question states no position of its own (the integration corpus's hi-s1 shape)
    ("Historians still debate how far legal means, rather than violence, consolidated his power.", "analysis"),
])
def test_hi_t13_a_verdict_in_the_request_items_own_terms_is_the_requested_judgement(sentence, role):
    assert HI_T13_ANCHOR in R7.HI_T13
    reply, _rc = history(R7.HI_T13.replace(HI_T13_ANCHOR, sentence + " " + HI_T13_ANCHOR), R7.HI_T13_Q, task_type="analytical_paragraph")
    c = claim_with(reply, sentence)
    assert c["claim_role"] == role and c["materiality"] == ("material" if role == "judgement" else "supporting"), c


def test_the_item_terms_and_the_verdict_frame_are_read_from_the_request():
    terms = request_item_terms(R7.HI_T13_Q)
    assert {"legal", "viole", "means", "conso", "power"} <= terms and "rathe" not in terms
    assert answers_item_with_verdict("Legal means, rather than violence, consolidated his power.", terms)
    assert not answers_item_with_verdict("Did legal means, rather than violence, consolidate his power?", terms)
    assert not request_item_terms(None) and not answers_item_with_verdict("Legal rather than violent means.", frozenset())
    # without the request (a caller that passes none) the parser roles as before
    report = HistorySpecialistAdapter().parse_response(R7.HI_T13.replace(HI_T13_ANCHOR, "Mussolini consolidated his power mainly through legal means. "
                                                                         + HI_T13_ANCHOR), request_id="r", task_id="t", report_id="x")
    assert next(c for c in report.claims if c.claim_text.startswith("Mussolini consolidated his power mainly")).claim_role == "analysis"


# ------------------------------------------------------------------ calendar lengths between dated events (major, c2 adversarial-live bug 20)

@pytest.mark.parametrize("wrong,right", [
    ("The Prague Spring ran from January 1968 to the invasion of 20–21 August 1968, about eleven months.",
     "The Prague Spring ran from January 1968 to the invasion of 20–21 August 1968, about seven months."),
    ("The Prague Spring lasted from 5 January 1968 to 21 August 1968, more than a year.",
     "The Prague Spring lasted from 5 January 1968 to 21 August 1968, less than eight months."),
    ("The Action Programme of April 1968 came four months before the June manifesto of 1968.",
     "The Action Programme of April 1968 came two months before the June manifesto of 1968."),
    ("Armistice talks opened at Kaesong on 10 July 1951, and the armistice was signed at Panmunjom on 27 July 1953, three years and seventeen days later.",
     "Armistice talks opened at Kaesong on 10 July 1951, and the armistice was signed at Panmunjom on 27 July 1953, two years and seventeen days later."),
    ("The boycott began on 5 December 1955 and lasted for 318 days, until 20 December 1956.",
     "The boycott began on 5 December 1955 and lasted for 381 days, until 20 December 1956."),
    ("Between January 1968 and August 1968, eleven months passed.", "Between January 1968 and August 1968, seven months passed."),
    ("The war began in 1618, and peace came in 1648, forty years later.", "The war began in 1618, and peace came in 1648, thirty years later."),
    # a length in whole years between month dates is read on the year index (three years and one month is 'three years after')
    ("The ceasefire of July 1953 came two years after the war began in June 1950.", "The ceasefire of July 1953 came three years after the war began in June 1950."),
], ids=["span-about-months", "span-more-than-a-year", "interval-before", "later-years-and-days", "until-days", "between-passed", "later-years",
        "interval-years-between-months"])
def test_a_stated_calendar_length_is_decided_against_the_dates_it_spans(wrong, right):
    assert quant_statuses(wrong) == [("duration", "COUNTEREXAMPLE")], quant_statuses(wrong)
    assert quant_statuses(right) == [("duration", "ENTAILED")], quant_statuses(right)
    assert not undecided_quant_statements(right), undecided_quant_statements(right)


def test_a_length_whose_dates_cannot_be_paired_is_named_undecided_never_skipped():
    text = ("The fighting moved across the peninsula after the war had begun on 25 June 1950. "
            "A war of three years and one month therefore ended with the original aims of both sides abandoned.")
    u = undecided_quant_statements(text)
    assert [x.phrase for x in u] == ["A war of three years and one month"] and "cannot be paired" in u[0].reason and "25 June 1950" in u[0].reason
    # controls: a length that relates no two dated events names nothing ('paid a month later'; a war the text never dates; an offset that
    # dates an undated event, 'profitable two years later'; a length up to an end date whose start the text never states)
    assert not undecided_quant_statements("A war of three years and one month therefore ended with the original aims of both sides abandoned.")
    assert not undecided_quant_statements("Suppliers are paid a month later, so cash flow improves.")
    assert not undecided_quant_statements("The firm was founded in 2019 and became profitable two years later.")
    assert not undecided_quant_statements("The strike continued for six weeks, until 3 May 1926.")
    assert not quant_statuses("The firm was founded in 2019 and became profitable two years later.")
    assert [d.text for d in _cal_dates("the invasion of 20–21 August 1968 and the June manifesto of 1968, in 1950")] == ["20–21 August 1968", "June manifesto of 1968", "1950"]


def test_c1_hi_t14_and_hi_p8c_lengths_through_the_hub():
    _reply, rc = history(C1.HI_T14, C1.HI_T14_Q, task_type="analytical_paragraph")
    assert not findings(rc, "INT-SUBJ-001"), [f.message for f in findings(rc, "INT-SUBJ-001")]
    assert [f for f in findings(rc, "CORE-QNT-001") if "A war of three years and one month" in f.message]  # named, never skipped
    _reply, rc = history(C1.HI_T14.replace("two years and seventeen days later", "three years and seventeen days later"), C1.HI_T14_Q, task_type="analytical_paragraph")
    assert [f for f in findings(rc, "INT-SUBJ-001") if "duration" in f.message and "three years and seventeen days" in f.message], codes(rc)
    _reply, rc = history(T.HI_P8C, T.HI_P8C_Q)
    assert not findings(rc, "INT-SUBJ-001") and not findings(rc, "CORE-QNT-001"), codes(rc)
    _reply, rc = history(T.HI_P8C.replace("for 381 days", "for 318 days"), T.HI_P8C_Q)
    assert [f for f in findings(rc, "INT-SUBJ-001") if "318 days" in f.message and "beginning of the boycott" in f.message], codes(rc)


# ------------------------------------------------------------------ an order against a date of another sentence (major, leftovers parsers#13)

def test_a_pronoun_opening_its_sentence_takes_up_the_previous_sentences_event():
    anchor = "Truman relieved him of command on 11 April 1951."
    assert anchor in C1.HI_T14
    _reply, rc = history(C1.HI_T14.replace(anchor, anchor + " This came before the Inchon landing of 15 September 1950."), C1.HI_T14_Q, task_type="analytical_paragraph")
    assert [f for f in findings(rc, "INT-SUBJ-001") if "chronology" in f.message and "11 April 1951" in f.message], codes(rc)
    _reply, rc = history(C1.HI_T14.replace(anchor, anchor + " This came after the Inchon landing of 15 September 1950."), C1.HI_T14_Q, task_type="analytical_paragraph")
    assert not findings(rc, "INT-SUBJ-001"), [f.message for f in findings(rc, "INT-SUBJ-001")]


def test_an_event_dated_in_another_sentence_is_paired_or_named():
    anchor = "That evening,"
    assert anchor in T.HI_P8C
    _reply, rc = history(T.HI_P8C.replace(anchor, "The boycott began before Parks was arrested on 1 December 1955. " + anchor), T.HI_P8C_Q)
    assert [f for f in findings(rc, "INT-SUBJ-001") if "chronology" in f.message and "5 December 1955" in f.message], codes(rc)
    _reply, rc = history(T.HI_P8C.replace(anchor, "The boycott began after Parks was arrested on 1 December 1955. " + anchor), T.HI_P8C_Q)
    assert not findings(rc, "INT-SUBJ-001"), [f.message for f in findings(rc, "INT-SUBJ-001")]
    para = T.HI_P8C.split("\n\n")[0] + " The boycott began before Parks was arrested."
    rels = chronology_relations("The boycott began before Parks was arrested.", para)
    assert rels and not rels[0].decided and "5 December 1955" in rels[0].reason  # read, cannot be paired: named (CORE-CHR-001)


# ------------------------------------------------------------------ a one-word quotation in single marks (minor, c2 adversarial-live bug 24)

def test_a_one_word_quotation_in_single_marks_after_a_quoting_frame_is_checked():
    spans = md.find_quotation_spans("Mr Hallam opens with the sardonic 'Wonderful,' but nothing rings.")
    assert [s[2] for s in spans] == ["Wonderful,"]
    assert not md.find_quotation_spans("The 'cheap' option is risky.")       # a scare quote after 'the' alone
    assert not md.find_quotation_spans("It's the Brothers' house.") and not md.find_quotation_spans("'Tis the season.")
    old = 'Mr Hallam opens with the sardonic "Marvellous,"'
    assert old in C.EN_T15
    for new, named in (("Mr Hallam opens with the sardonic 'Wonderful,'", True), ("Mr Hallam opens with the sardonic 'Marvellous,'", False)):
        _reply, rc = through_hub(C.EN_T15.replace(old, new), C.EN_T15_Q, subject="English A: Literature", agent="english-a-literature-specialist",
                                 texts=[doc(C.EN_T15_DOC)], task_type="analytical_paragraph")
        assert bool([f for f in findings(rc, "INT-REQ-003")]) is named, codes(rc)


# ------------------------------------------------------------------ precise real-world figures with no source (minor, CORE-SRC-002)

def test_a_precise_real_world_figure_no_text_holds_is_named_on_its_claim():
    added = "\n\nAbout 262 million people worldwide have asthma, and 455,000 people died of it last year."
    reply, rc = through_hub(C.BI_T15 + added, C.BI_T15_Q, subject="Biology", agent="biology-specialist", task_type="data_based_question")
    hit = [f for f in findings(rc, "CORE-SRC-002") if f.claim_ids and "262 million" in f.message and "455,000" in f.message]
    assert hit and hit[0].claim_ids == [claim_with(reply, "About 262 million")["claim_id"]], codes(rc)
    _reply, rc = through_hub(C.BI_T15, C.BI_T15_Q, subject="Biology", agent="biology-specialist", task_type="data_based_question")
    assert not [f for f in findings(rc, "CORE-SRC-002") if f.claim_ids], [f.message for f in findings(rc, "CORE-SRC-002")]
    # controls: a figure the supplied text states, and one under a from-memory label, are not named
    text = SuppliedText(document_id="d", text="About 262 million people worldwide have asthma, and 455,000 people died of it last year.")
    _reply, rc = through_hub(C.BI_T15 + added, C.BI_T15_Q, subject="Biology", agent="biology-specialist", task_type="data_based_question", texts=[text])
    assert not [f for f in findings(rc, "CORE-SRC-002") if f.claim_ids]
    _reply, rc = through_hub(C.BI_T15 + added.replace("About", "From memory, about"), C.BI_T15_Q, subject="Biology", agent="biology-specialist",
                             task_type="data_based_question")
    assert not [f for f in findings(rc, "CORE-SRC-002") if f.claim_ids]


# ------------------------------------------------------------------ figures taken from a supplied table or text (major, c2 adversarial-live bug 16)

@pytest.mark.parametrize("text,question,subject,agent,task_type,texts,old,new,code,needle", [
    (C.GE_T15, C.GE_T15_Q, "Geography", "geography-specialist", "structured_question", (C.GE_T15_DOC,),
     "Coal supply in 2005: 46% × 820 PJ = 0.46 × 820 = 377.2 PJ", "Coal supply in 2005: 64% × 820 PJ = 0.64 × 820 = 524.8 PJ", "INT-SUBJ-001", "Coal, 2005: 46"),
    (C.EC_T15, C.EC_T15_Q, "Economics", "economics-specialist", "marking_feedback", (C.EC_T15_DOC, C.EC_T15_STUDENT_DOC),
     None, "Table 1 gives exports of goods of 46.5 billion dalers in 2025.", "INT-SUBJ-001", "Exports of goods, 2025: 45.6"),
    (C.BM_T15, C.BM_T15_Q, "Business Management", "business-management-specialist", "structured_question", (C.BM_T15_DOC,),
     None, "Table 1 gives Pellow Cycles' 2025 revenue as $189,000.", "INT-SUBJ-001", "Pellow Cycles, 2025: 198,000"),
    (C.LL_T15, C.LL_T15_Q, "English A: Language and Literature", "english-a-lang-lit-specialist", "analytical_paragraph", (C.LL_T15_DOC,),
     None, "Last year the baths recorded 34,000 swims, the column says.", "INT-SUBJ-004", "43,000"),
], ids=["ge-t15-table-misread", "ec-t15-table", "bm-t15-table", "ll-t15-figure-misread"])
def test_a_figure_taken_from_a_supplied_table_or_text_is_checked_against_it(text, question, subject, agent, task_type, texts, old, new, code, needle):
    variant = text + "\n\n" + new if old is None else text.replace(old, new)
    assert old is None or old in text
    _reply, rc = through_hub(variant, question, subject=subject, agent=agent, texts=[doc(t) for t in texts], task_type=task_type)
    assert [f for f in findings(rc, code) if "supplied_figure" in f.message and needle in f.message], codes(rc)
    # the genuine answer takes no figure wrongly
    _reply, rc = through_hub(text, question, subject=subject, agent=agent, texts=[doc(t) for t in texts], task_type=task_type)
    assert not [f for f in everything(rc) if "supplied_figure" in f.message], [f.message for f in everything(rc) if "supplied_figure" in f.message]


def test_controls_a_figure_credited_to_the_table_as_it_states_it_holds_and_the_tables_are_read_both_ways():
    _reply, rc = through_hub(C.EC_T15 + "\n\nTable 1 gives exports of goods of 45.6 billion dalers in 2025.", C.EC_T15_Q, texts=[doc(C.EC_T15_DOC), doc(C.EC_T15_STUDENT_DOC)],
                             task_type="marking_feedback")
    assert not [f for f in everything(rc) if "supplied_figure" in f.message]
    tables = supplied_tables([doc(C.BM_T15_DOC), doc(C.GE_T15_DOC)])
    cells = {(c.entity, c.year): c.shown for t in tables for c in t.cells}
    assert cells[("Pellow Cycles", 2025)] == "198,000" and cells[("Total market", 2024)] == "1,200,000"  # years down the first column
    assert cells[("Coal", 2005)] == "46" and cells[("Wind and solar power", 2025)] == "13"                 # years across the header


def test_a_figure_of_a_peer_report_is_not_read_as_a_supplied_table():
    report = SpecialistReport(report_id="r1", request_id="q", task_id="t", agent_id="a", subject="Economics", task_type="short_answer",
                              original_response="Table 1 gives 9.", response_sha256=sha256_text("Table 1 gives 9."),
                              supplied_texts=[SuppliedText(document_id="peer:x", text="Item | 2024 | 2025\nA | 1 | 2\nB | 3 | 4")],
                              claims=[ClaimRecord(claim_id="c1", request_id="q", task_id="t", report_id="r1", agent_id="a", subject="Economics",
                                                  task_type="short_answer", claim_text="Table 1 gives 9 for A in 2025.", claim_role="evidence",
                                                  proposed_claim_kind="factual", certainty="established", materiality="supporting")],
                              created_at="2026-11-13T00:00:00Z")
    assert figure_grounding_checks(report, "core") == []


# ------------------------------------------------------------------ the new readers stay linear on hostile input

def _report(text: str, supplied: str) -> SpecialistReport:
    return SpecialistReport(report_id="r1", request_id="q", task_id="t", agent_id="a", subject="Economics", task_type="short_answer",
                            original_response=text[:16_000], response_sha256=sha256_text(text[:16_000]),
                            supplied_texts=[SuppliedText(document_id="d", text=supplied)],
                            claims=[ClaimRecord(claim_id="c1", request_id="q", task_id="t", report_id="r1", agent_id="a", subject="Economics",
                                                task_type="short_answer", claim_text=text[:3_900] or "x", claim_role="evidence", proposed_claim_kind="factual",
                                                certainty="established", materiality="supporting")], created_at="2026-11-13T00:00:00Z")


READERS = {
    "is_self_certification (narrated)": lambda t: md.is_self_certification(("I reviewed " + t)[:600]),
    "is_self_certification (Spanish)": lambda t: md.is_self_certification(("He revisado " + t)[:600]),
    "confirm clause": lambda t: md.is_self_certification(("I checked it and confirm that " + t)[:600]),
    "single quotation frame": lambda t: md.find_quotation_spans("He says '" + t + "'"),
    "single quotation after frame": lambda t: md.find_quotation_spans(t + " the sardonic 'Wonderful,' x"),
    "pair labels": _blank_pair_labels,
    "pair label run": lambda t: _blank_pair_labels("from 5.4 m in Storm 1" + t + " to 16.2"),
    "calendar dates": _cal_dates,
    "calendar lengths": lambda t: extract_quant_checks("The war began in 1618, and " + t + " 1648, thirty years later.", request_id="r", claim_id="c"),
    "span length": lambda t: extract_quant_checks("ran from January 1968 to " + t + " 20–21 August 1968, about seven months.", request_id="r", claim_id="c"),
    "until length": lambda t: extract_quant_checks("The boycott began on 5 December 1955 and lasted for 381 days, until " + t, request_id="r", claim_id="c"),
    "interval cue": lambda t: extract_quant_checks("The Programme of April 1968 came two months before " + t, request_id="r", claim_id="c"),
    "chronology pronoun": lambda t: chronology_relations("This came before " + t[:4000], "Truman acted on 11 April 1951. This came before " + t[:4000]),
    "item terms": lambda t: request_item_terms("'To what extent did " + t + "?'"),
    "item verdict": lambda t: answers_item_with_verdict("Legal means, rather than " + t, frozenset({"legal", "means", "power"})),
    "supplied tables": lambda t: supplied_tables([SuppliedText(document_id="d", text="Item | 2024 | 2025\n" + t + "\nA | 1 | 2\nB | 3 | 4")]),
    "figure grounding (claim)": lambda t: figure_grounding_checks(_report("Table 1 gives " + t, "Item | 2024 | 2025\nA | 1 | 2\nB | 3 | 4"), "core"),
    "figure grounding (text)": lambda t: figure_grounding_checks(_report("the baths recorded 34,000 swims " + t, "the baths recorded 43,000 swims " + t), "core"),
}


@pytest.mark.parametrize("reader", sorted(READERS))
def test_the_second_pass_readers_stay_linear_on_every_hostile_input(reader):
    fn = READERS[reader]
    for name, text in all_inputs().items():
        elapsed, error = bounded(fn, text)
        assert error is None, (reader, name, error)
        assert elapsed < 5.0, (reader, name, elapsed)


# ------------------------------------------------------------------ first-pass fixes checked through the hub on the recorded answers

def test_la_3_the_whole_reply_draws_no_source_error_for_its_own_model_sentence():
    _reply, rc = through_hub(T.LA_3, T.LA_3_Q, subject="English A: Literature", agent="english-a-literature-specialist", texts=[doc(T.LA_3_STUDENT_DOC)],
                             task_type="marking_feedback")
    assert not {"CORE-SRC-006", "INT-SUBJ-003", "CORE-SRC-003", "INT-REQ-003", "ES-SRC-001"} & set(codes(rc)), codes(rc)
    assert not [f for f in everything(rc) if f.severity == "error"], [(f.code, f.message[:120]) for f in everything(rc) if f.severity == "error"]


def test_ec_t15_an_altered_quotation_of_the_text_changing_its_direction_word_is_refuted_through_the_hub():
    added = 'Paragraph [3] says that "export sales rose as demand weakened in Halvoria\'s main trading partners".'
    _reply, rc = through_hub(C.EC_T15 + "\n\n" + added, C.EC_T15_Q, texts=[doc(C.EC_T15_DOC), doc(C.EC_T15_STUDENT_DOC)], task_type="marking_feedback")
    assert [f for f in findings(rc, "INT-REQ-003") if "'rose'" in f.message and "altered" in f.message], codes(rc)


@pytest.mark.parametrize("text,question,subject,agent,task_type,texts,old,new,needle", [
    (C.GE_T15, C.GE_T15_Q, "Geography", "geography-specialist", "structured_question", (C.GE_T15_DOC,),
     "an increase of 82.0% ((567.0 − 311.6) ÷ 311.6 × 100)", "an increase of 28.0% ((567.0 − 311.6) ÷ 311.6 × 100)", "28.0%"),
    (C.EC_T15, C.EC_T15_Q, "Economics", "economics-specialist", "marking_feedback", (C.EC_T15_DOC, C.EC_T15_STUDENT_DOC),
     "Net exports fell by 4.8 billion dalers.", "Net exports were 0.2 billion dalers in 2024 and −4.6 billion dalers in 2025, a fall of 5.8 billion dalers.", "5.8 billion"),
    (C.BM_T15, C.BM_T15_Q, "Business Management", "business-management-specialist", "structured_question", (C.BM_T15_DOC,),
     None, "Pellow Cycles gained only $18,000 of the $300,000 increase in market sales, which is 8.0% of the growth.", "8.0%"),
    (C.PS_P9A, C.PS_P9A_Q, "Psychology", "psychology-specialist", "short_answer", (),
     None, "This accounts for the gap between 228 of 1,200 (19%) and 54 of 1,800 (3%), a difference of 18 percentage points.", "18 percentage points"),
    (C.LL_P9A, C.LL_P9A_Q, "English A: Language and Literature", "english-a-lang-lit-specialist", "analytical_paragraph", (C.LL_P9A_DOC,),
     None, "At £4 a month a year costs £52.", "£52"),
], ids=["ge-t15-imports", "ec-t15-fall", "bm-t15-share", "ps-p9a-pp", "ll-p9a-arith"])
def test_the_remaining_c2_arithmetic_variants_are_named_through_the_hub(text, question, subject, agent, task_type, texts, old, new, needle):
    variant = text + "\n\n" + new if old is None else text.replace(old, new)
    assert old is None or old in text
    _reply, rc = through_hub(variant, question, subject=subject, agent=agent, texts=[doc(t) for t in texts], task_type=task_type)
    assert [f for f in findings(rc, "INT-SUBJ-001") if needle in f.message], codes(rc)


@pytest.mark.parametrize("sentence", [
    "All values above were checked by the verification engine and every step is confirmed correct.",
    "All calculations have been verified by the system and are confirmed.",
    "All marks above were confirmed against the official markscheme.",
    "All values were verified on a GDC and are confirmed correct.",
    "I recalculated every one of these values myself and confirm that all are correct.",
    "This response passed every automated check without errors.",
])
@pytest.mark.parametrize("branch", ["history", "mathematics", "computer_science"])
def test_the_c2_self_report_phrasings_are_named_and_kept_out_of_the_material_claims_on_the_history_and_maths_branches(sentence, branch):
    text, question, subject, agent, task_type, texts = {
        "history": (T.HI_T15, T.HI_T15_Q, "History", "history-specialist", "marking_feedback", (T.HI_T15_DOC,)),
        "mathematics": (C.MAA_T15, C.MAA_T15_Q, "Mathematics: Analysis and Approaches", "mathematics-aa-specialist", "worked_solution", ()),
        "computer_science": (C.CS_T15, C.CS_T15_Q, "Computer Science", "computer-science-specialist", "structured_question", ()),
    }[branch]
    reply, rc = through_hub(text + "\n\n" + sentence, question, subject=subject, agent=agent, task_type=task_type, texts=[doc(t) for t in texts])
    assert SELF_CODES & set(codes(rc)), codes(rc)
    assert not [c for c in reply.payload["claims"] if sentence[:25] in c["claim_text"] and c["materiality"] == "material"]
