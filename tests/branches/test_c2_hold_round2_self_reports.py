"""Hold-fix round 2 of the round-9 push-check hold on the c2 clearance commit, on the translator's side: one self-report reader,
by vocabulary class, on text normalised as the student sees it (``adapters.self_report``; ``markdown.is_self_certification`` is it).

The round-1 lenses reproduced, on every subject branch, dozens of self-certifying phrasings no reader named ("I've gone back over
all the numbers and they're right.", "All calculations confirmed.", "Comprobado con Z3: todo es correcto.", the push check's
sentence in quotation marks, with a soft hyphen or a Cyrillic 'е'), and correct work refused as a self-report (a census office's
check reported as evidence, the Hollerith tabulating system checking the 1890 census, a narrator's claim under analysis, "Check:
2(4) + 3 = 11 ✓"). These tests pin, on every subject branch and every subject that routes to one:

* every phrasing of the class (its own paragraph, a heading, a table cell, parentheses, bold, quotation marks with no attribution,
  scare quotes, invisible format characters, fullwidth and look-alike letters) is named CORE-SELF-001 on the receipt, the claims
  holding it carry the advisory status (INT-HANDOFF-006) and none is material; written as the last sentence of the answer's own
  paragraph, it is named CORE-SELF-001;
* the correct work draws no CORE-SELF-001 and no advisory status, and the reader names none of it;
* the reader itself: its normalisation, its attribution of quotations, and the vetoes.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import self_report as sr
from epinoic_logic.translate.contracts import SuppliedText

from .c2_hold_texts import CORRECT_WORK, DISGUISED, INLINE, QUOTED, ROUND2, ROUND2_SELF_CERTIFYING, SUBJECTS
from .test_c2_clearance_parsers import codes, through_hub

QUESTION = "Answer the question."
IDS = [s[0] for s in SUBJECTS]


def _key(sentence: str) -> str:
    """A run of the sentence that a claim holding it keeps, read in its reading form (table, heading and emphasis marks removed)."""
    last = sentence.split("\n")[-1]
    cells = [c for c in last.split("|") if c.strip()]
    return " ".join(sr.reading_form(cells[-1] if cells else last).split())[:20]


def _holding(reply, sentence: str) -> list[dict]:
    key = _key(sentence)
    return [c for c in reply.payload["claims"] if key and key in " ".join(sr.reading_form(c["claim_text"]).split())]


@pytest.mark.parametrize("sentence", ROUND2_SELF_CERTIFYING + INLINE)
def test_the_one_reader_names_every_phrasing(sentence):
    assert md.is_self_certification(sentence) and sr.is_self_report(sentence), sentence


@pytest.mark.parametrize("sentence", CORRECT_WORK)
def test_the_one_reader_names_no_correct_work(sentence):
    assert not md.is_self_certification(sentence), (sentence, sr.reading_form(sentence))


@pytest.mark.parametrize("sentence", ROUND2_SELF_CERTIFYING)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_self_certification_of_the_class_is_named_on_every_branch_and_never_material(subject, agent, task_type, base, sentence):
    reply, rc = through_hub(base + "\n\n" + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert "CORE-SELF-001" in codes(rc), (subject, sentence, codes(rc))
    holding = _holding(reply, sentence)
    assert not [c for c in holding if c["materiality"] == "material"], holding
    for c in holding:
        assert c.get("advisory_verification_status") is not None, c
        assert [f for f in rc.findings if f.code == "INT-HANDOFF-006" and c["claim_id"] in f.claim_ids], codes(rc)


@pytest.mark.parametrize("sentence", INLINE)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_self_certification_closing_the_answers_own_paragraph_is_named(subject, agent, task_type, base, sentence):
    _reply, rc = through_hub(base + " " + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    found = [f for f in rc.structural_findings if f.code == "CORE-SELF-001"]
    assert found, (subject, sentence, codes(rc))
    assert all(sentence[:18] not in f.message for f in found)  # named by place, never by its words


@pytest.mark.parametrize("sentence", CORRECT_WORK)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_correct_work_draws_no_self_report(subject, agent, task_type, base, sentence):
    reply, rc = through_hub(base + "\n\n" + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert "CORE-SELF-001" not in codes(rc), (subject, sentence, [f.message for f in rc.structural_findings if f.code == "CORE-SELF-001"])
    assert not [c for c in _holding(reply, sentence) if c.get("advisory_verification_status") is not None]


#: Full correct answers of the correct-work lens: (subject, agent, task type, answer, supplied texts).
MEMOIR = SuppliedText(document_id="doc-memoir", title="Memoir of General Hale, 1919",
                      text="Memoir of General Hale, 1919. Every figure in my dispatches was checked by me and is correct. Our losses at the river were "
                           "light, fewer than two hundred men.")
NARRATIVE = SuppliedText(document_id="doc-narr", title="Extract",
                         text="I checked every lock twice and all of them were secure, he told himself, though the door stood open behind him.")
FULL_ANSWERS = [
    ("History", "history-specialist", "short_answer",
     "The 1890 United States census was the first counted by machine. The Hollerith tabulating system checked these census figures in months "
     "rather than years, which made punched-card machines central to later government statistics.", ()),
    ("Biology", "biology-specialist", "short_answer",
     "The data-logging software checked all the readings in the table below for outliers. The rate of oxygen production rose with temperature "
     "up to 35 °C.", ()),
    ("Computer Science", "cs-specialist", "short_answer",
     "A static type checker verified these values before the program ran, so the type error was reported at compile time rather than at run "
     "time.", ()),
    ("Economics", "economics-specialist", "short_answer",
     "All the figures below were verified by the National Audit Office. The subsidy cost 2.3 billion pounds, about 0.1% of GDP, so its fiscal "
     "burden was small.", ()),
    ("English A: Literature", "english-a-literature-specialist", "short_answer",
     "The narrator claims that he has checked every figure in the ledger himself, which the reader is invited to doubt. His certainty contrasts "
     "with the chaos of the room.", ()),
    ("History", "history-specialist", "short_answer",
     "General Hale's memoir claims that \"Every figure in my dispatches was checked by me and is correct.\" The regimental returns record far "
     "heavier losses at the river, so the memoir is unreliable as evidence of casualties.", (MEMOIR,)),
    ("Mathematics: Analysis and Approaches", "maths-specialist", "calculation",
     "From 2x + 3 = 11 we get 2x = 8, so x = 4.\nCheck: 2(4) + 3 = 11 ✓", ()),
    ("English A: Literature", "english-a-literature-specialist", "short_answer",
     "The narrator reassures himself: \"I checked every lock twice and all of them were secure.\" The open door behind him exposes how "
     "unreliable his reassurance is.", (NARRATIVE,)),
]


@pytest.mark.parametrize("subject,agent,task_type,answer,texts", FULL_ANSWERS, ids=[f"{a[0]}-{i}" for i, a in enumerate(FULL_ANSWERS)])
def test_full_correct_answers_carry_no_self_report(subject, agent, task_type, answer, texts):
    reply, rc = through_hub(answer, QUESTION, subject=subject, agent=agent, task_type=task_type, texts=texts)
    assert "CORE-SELF-001" not in codes(rc), [f.message for f in rc.structural_findings if f.code == "CORE-SELF-001"]
    assert not [c for c in reply.payload["claims"] if c.get("advisory_verification_status") is not None]


# ============================================================================================ the reader itself
@pytest.mark.parametrize("sentence", DISGUISED)
def test_the_reading_form_is_the_text_the_student_sees(sentence):
    assert sr.reading_form(sentence) == "All calculations have been verified by the system and are confirmed."


def test_a_quotation_is_masked_only_where_attributed_or_analysed():
    quoted = '"All calculations have been verified by the system and are confirmed."'
    assert md.is_self_certification(quoted)  # no attribution: the writer's own words
    assert not md.is_self_certification("The minister claimed that " + quoted)
    assert not md.is_self_certification("The phrase " + quoted + " suggests a bureaucrat's confidence.")
    assert md.is_self_certification('I can confirm: "All values above were verified."')  # the writer reporting itself
    for q in QUOTED:
        assert md.is_self_certification(q), q


@pytest.mark.parametrize("sentence,expected", [
    ("The census figures were checked by clerks in 1891.", False),          # an outside party, a date: history
    ("These figures were checked by me.", True),                            # the writer
    ("The values in this answer were verified by the National Audit Office.", True),  # an explicit reference to the answer
    ("We tested the effect of temperature on enzyme activity.", False),     # an experiment, not a check of the answer
    ("The system verifies the password against the stored hash.", False),  # the subject matter (Computer Science)
    ("Prices were checked by the tariff.", False),
    ("Inflation was checked by higher interest rates.", False),
    ("The rumours spread quickly and they were soon confirmed.", False),
    ("Hence the identity is proved by induction.", False),
    ("This was confirmed by the 1921 census.", False),
    ("Have all of the values above been verified?", False),
    ("None of the figures above were verified.", False),
    ("You should double-check these figures against your textbook.", False),
    ("Self-check: passed.", True),
    ("Accuracy: 100%", True),
])
def test_the_class_reading_and_its_vetoes(sentence, expected):
    assert md.is_self_certification(sentence) is expected, (sentence, sr.reading_form(sentence))


def test_the_answer_wide_reading_names_a_heading_a_line_and_a_cell():
    assert sr.self_report_places("Body text here.\n\n## All figures verified\n\nMore text.") == [2]
    assert sr.self_report_places("Final answer: as above.\nAll calculations confirmed.") == [1]
    assert sr.self_report_places("| Item | Note |\n|---|---|\n| Figures | Checked by Z3 and correct |") == [1]
    assert sr.self_report_places("The treaty was signed in 1919.\n\nCheck: 2(4) + 3 = 11 ✓") == []


def test_a_quotation_drawn_out_of_its_sentence_is_read_in_that_sentence():
    assert sr.quotation_only('"I checked every lock twice and all of them were secure."')
    assert not sr.claim_is_self_report('"All calculations have been verified by the system and are confirmed."')
    assert sr.claim_is_self_report("Note: all calculations have been verified by the system and are confirmed.")


def test_the_reader_is_bounded_on_a_long_text():
    import time
    text = ("The figures were all audited by the census office in 1891 and the totals rose. " * 400)[:30_000]
    t0 = time.perf_counter()
    sr.is_self_report(text)
    assert time.perf_counter() - t0 < 5.0
