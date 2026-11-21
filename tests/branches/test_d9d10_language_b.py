"""D9/D10 (decision D35): the Language B branch's readers and checks. Spanish detection, numeral readings, number words, credits, the model
regions of the recorded answers, the pairing of ¿ and ¡, the address markers; and through the hub the faulty variants of the recorded answers
(design section 11): a wrong word count or range claim, a model said to contain a form it never writes, a false address claim, a wrong listed
count, a wrong Spanish percentage, a misread figure of the supplied text. No Spanish reader acts on a French B answer."""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.branches import spanish_lexicon as es
from epinoic_logic.branches.language_b import LanguageBPack, classify_task, model_regions
from epinoic_logic.channel.request_parser import count_words
from epinoic_logic.engine import verify

from . import d9d10_texts as T
from .d9d10_hub import CFG, SPB, checks, codes, failed, recorded, report, through_hub

# ------------------------------------------------------------------ the lexicon


@pytest.mark.parametrize("text,spanish", [
    (T.SP_T15, True),
    ("La ciudad tiene muchos parques. Los jóvenes prefieren el transporte público y la vida en el centro es muy cara para las familias que viven aquí.", True),
    ("¿Qué opinas? ¡Escríbeme pronto! ¿Vienes el sábado? Es la fiesta del pueblo.", True),
    (T.GE_T15, False),
    ("La ville a beaucoup de parcs. Les jeunes préfèrent les transports publics et la vie au centre est très chère pour les familles.", False),
    ("The town has many parks, and the young prefer public transport.", False),
])
def test_spanish_detection(text, spanish):
    assert es.is_spanish(text) is spanish


@pytest.mark.parametrize("token,language,values", [
    ("1.250", "es", {Fraction(1250)}),
    ("1.250", "en", {Fraction(5, 4)}),
    ("1.250", None, {Fraction(1250), Fraction(5, 4)}),
    ("2,5", "es", {Fraction(5, 2)}),
    ("1,250", "es", {Fraction(5, 4), Fraction(1250)}),
    ("1 250", "es", {Fraction(1250)}),
    ("1 250", "es", {Fraction(1250)}),
    ("12", "es", {Fraction(12)}),
    ("1.2.3.4", "es", set()),
    ("9" * 30, "es", set()),
])
def test_numeral_readings(token, language, values):
    assert set(es.spanish_numeral_readings(token, language)) == values


def test_number_words_and_credits():
    assert [v for _a, _b, v in es.spanish_number_figures("Había doce puestos y catorce alumnos; dos mil trescientos cuarenta y cinco habitantes.")][:3] == ["12", "14", "2345"]
    for credit in ("Según el texto, en 2015 quedaban 212 vecinos.", "El texto dice que había doce puestos.", "Como dice el texto, son catorce.",
                   "Hay doce puestos (línea 4)."):
        assert es.SPANISH_CREDIT_RE.search(credit), credit
    assert not es.SPANISH_CREDIT_RE.search("En el pueblo había doce puestos.")


def test_inverted_marks_pair_in_one_pass():
    t = "¿Cómo estáis? Bien. ¡Qué bien! ¿Sin cierre. ¡Hola!"
    spans = es.inverted_mark_spans(t)
    assert [t[a:b] for a, b in spans] == ["¿Cómo estáis?", "¡Qué bien!", "¡Hola!"]


@pytest.mark.parametrize("text,form,n", [
    ("¿Cómo estáis?", "vosotros", 1), ("vuestra casa", "vosotros", 1), ("os echo de menos", "vosotros", 1),
    ("el país es grande", "vosotros", 0), ("¿Cómo están?", "ustedes", 0), ("su casa", "usted", 0), ("su casa", "ustedes", 0),
    ("¿Cómo está usted?", "usted", 1), ("Te escribo desde tu ciudad", "tú", 2), ("vos sabés", "vos", 1),
])
def test_address_markers_are_unambiguous_only(text, form, n):
    assert len(es.address_markers(text, form)) == n


def test_the_regions_of_the_recorded_model_text():
    r = model_regions(T.SP_T15, task="writing")
    assert r.disclaimer == {0} and r.model == list(range(1, 10)) and r.meta == [10]
    assert r.headline == "Turismo y vecindad: ¿un negocio para todos?" and r.byline == "Por Marta Ruiz Salas, 2.º de Bachillerato"
    assert count_words(r.model_text) == 514 and count_words(r.body_text) == 499
    m = model_regions(T.SP_T16, task="marking", supplied=tuple(_docs(T.SP_T16_DOC)), request_text=T.SP_T16_Q)
    assert count_words(m.student_text) == 296 and m.inline_models and m.inline_models[0].startswith("Al principio")


def _docs(*docs):
    from .d9d10_hub import supplied
    return supplied(docs)


@pytest.mark.parametrize("name,task", [("c2/sp-t15", "writing"), ("c3/sp-t16", "marking"), ("c1/sp-t14", "reading"), ("c3/sp-p10d", "notes")])
def test_task_classification(name, task):
    from .d9d10_hub import RECORDED
    answer, question, subject, agent, task_type, docs = RECORDED[name]
    assert classify_task(report(subject, agent, answer, task_type=task_type, docs=docs), question) == task


# ------------------------------------------------------------------ the recorded answers' faulty variants (design section 11)


def _padding(n: int) -> str:
    return " ".join(["Además, los vecinos piden más zonas verdes y calles tranquilas para los niños del barrio."] * n)


def test_sp_t15_padded_body_is_named_by_the_channel_and_the_pack():
    paragraphs = T.SP_T15.split("\n\n")
    paragraphs[3] = paragraphs[3] + " " + _padding(13)
    rc = recorded("c2/sp-t15", "\n\n".join(paragraphs))
    assert "INT-REQ-005" in codes(rc)
    assert ("language-b-word-count-1", "COUNTEREXAMPLE") in checks(rc) and ("language-b-word-range-claim-1", "COUNTEREXAMPLE") in checks(rc)
    assert len(failed(rc)) >= 2


def test_no_bound_hl_paper_1_model_over_the_course_range_is_a_convention_warning():
    question = T.SP_T15_Q.replace(" Escribe entre 450 y 600 palabras.", "")
    paragraphs = T.SP_T15.split("\n\n")
    paragraphs[3] = paragraphs[3] + " " + _padding(13)
    paragraphs[10] = "Next step: read the model aloud."
    rc = through_hub("\n\n".join(paragraphs), question, *SPB, "writing_task")
    assert ("language-b-course-word-range-1", "COUNTEREXAMPLE") in checks(rc)
    warn = failed(rc, "INT-SUBJ-004")
    assert warn and not failed(rc, "INT-SUBJ-001")
    ok = through_hub(T.SP_T15.replace("inside the 450–600 range", "a fair length"), question, *SPB, "writing_task")
    assert ("language-b-course-word-range-1", "ENTAILED") in checks(ok)


def test_sp_t16_wrong_word_count_and_range():
    rc = recorded("c3/sp-t16", T.SP_T16.replace("Your email is about 300 words", "Your email is about 450 words"))
    assert ("language-b-word-count-1", "COUNTEREXAMPLE") in checks(rc) and failed(rc)
    short = (T.SP_T16_DOC[0], T.SP_T16_DOC[1], T.SP_T16_DOC[2], " ".join(T.SP_T16_DOC[3].split()[:180]))
    from .d9d10_hub import through_hub as th
    rc2 = th(T.SP_T16.replace("Your email is about 300 words, so", "Your email is short, so"), T.SP_T16_Q, *SPB, "marking_feedback", (short,))
    assert ("language-b-word-range-claim-1", "COUNTEREXAMPLE") in checks(rc2) and failed(rc2)


def test_sp_t15_model_said_to_use_a_form_it_never_writes():
    bad = recorded("c2/sp-t15", T.SP_T15.replace("Next step:", "The model uses «por lo tanto» to link its points.\nNext step:"))
    assert ("language-b-quoted-form-1", "COUNTEREXAMPLE") in checks(bad) and failed(bad, "INT-SUBJ-004")
    ok = recorded("c2/sp-t15", T.SP_T15.replace("Next step:", "The model uses «sin embargo» and «además» to link its points.\nNext step:"))
    assert ("language-b-quoted-form-1", "ENTAILED") in checks(ok) and not failed(ok, "INT-SUBJ-004")


def test_sp_t16_false_address_claim():
    rc = recorded("c3/sp-t16", T.SP_T16.replace('you write to the family with vosotros forms ("¿Cómo estáis?"',
                                                 'you write to the family with usted forms ("¿Cómo estáis?"'))
    assert any(c.startswith("language-b-address-form") and s == "COUNTEREXAMPLE" for c, s in checks(rc)) and failed(rc, "INT-SUBJ-004")


def test_sp_t16_wrong_listed_count():
    rc = recorded("c3/sp-t16", T.SP_T16.replace("fix the six points", "fix the eight points"))
    assert ("language-b-listed-count-1", "COUNTEREXAMPLE") in checks(rc) and failed(rc, "INT-SUBJ-004")


@pytest.mark.parametrize("line,status", [
    ("La población pasó de 1.250 a 212 habitantes, una caída del 73 %.", "COUNTEREXAMPLE"),
    ("La población pasó de 1.250 a 212 habitantes, una caída del 83 %.", "ENTAILED"),
])
def test_spanish_percentage_change(line, status):
    rc = recorded("c1/sp-t14", T.SP_T14 + "\n\n" + line)
    assert ("language-b-percent-change-1", status) in checks(rc), checks(rc)
    assert bool(failed(rc)) is (status == "COUNTEREXAMPLE")
    # the 212 the text states as vecinos is not read as a misread habitantes figure
    assert not [c for c, s in checks(rc, "language-b-supplied-figure") if s != "ENTAILED"]


@pytest.mark.parametrize("old,new,code", [
    ("1. 1.250 habitantes en 1960 y 212 vecinos en 2015.", "1. 1.250 habitantes en 1960 y 221 vecinos en 2015.", "INT-SUBJ-001"),
    ("Next step:", "Según el texto, en 2015 quedaban 221 vecinos.\n\nNext step:", "INT-SUBJ-001"),
    ("Next step:", "La escuela volvió a abrir con quince alumnos.\n\nNext step:", "INT-SUBJ-004"),
])
def test_sp_t14_misread_figures_of_the_supplied_text(old, new, code):
    rc = recorded("c1/sp-t14", T.SP_T14.replace(old, new))
    figs = [s for c, s in checks(rc, "language-b-supplied-figure")]
    assert "COUNTEREXAMPLE" in figs, checks(rc)
    assert any(f.code == code and ("supplied" in f.message or "figure" in f.message) for f in rc.findings), [(f.code, f.message[:100]) for f in rc.findings]


def test_a_quoted_student_form_absent_from_the_student_text_is_the_channels_alone():
    rc = recorded("c3/sp-t16", T.SP_T16.replace('"Quiero daros las gracias" covers the thanks', '"Quiero darles las gracias" covers the thanks'))
    assert "INT-REQ-003" in codes(rc) or "INT-REQ-010" in codes(rc)
    assert not [c for c, _s in checks(rc) if c.startswith("language-b-quoted-form")]


def test_no_spanish_reader_acts_on_a_french_b_answer():
    model = ("La ville accueille chaque été des milliers de touristes. Les habitants se plaignent du bruit et des loyers qui augmentent. "
             "Pourtant, le tourisme crée des emplois et fait vivre les commerces du centre. ") * 4
    answer = (f"Titre : Le tourisme, une chance ?\n\n{model}\n\n{model}\n\nWord count: about 160 words, inside the 120–200 range. "
              'You write with vosotros forms ("¿Cómo estáis?"). The model uses «pourtant».')
    rc = through_hub(answer, "Write an article in French for the school magazine. Write 120 to 200 words.", "French B", "language-b-french-specialist", "writing_task")
    assert rc.branch == "language_b"
    ids = [c for c, _s in checks(rc)]
    assert any(c.startswith("language-b-word-count") for c in ids)          # language-neutral
    assert not any(c.startswith(("language-b-address-form", "language-b-percent-change", "language-b-supplied-figure")) for c in ids)


def test_unknown_supporting_claims_are_gen_str_001_on_the_language_b_branch():
    rep = report(*SPB, "Punto.", claims=[dict(claim_id="c1", claim_text="Punto.", claim_role="point", materiality="material", supporting_claim_ids=["zz"])])
    assert [f.code for f in LanguageBPack().checks(rep, "")] == ["GEN-STR-001"]


def test_every_language_b_check_is_linear_and_decided():
    from .d9d10_hub import RECORDED
    for name in ("c2/sp-t15", "c3/sp-t16", "c1/sp-t14"):
        answer, question, subject, agent, task_type, docs = RECORDED[name]
        for fc in LanguageBPack().formal_checks_for(report(subject, agent, answer, task_type=task_type, docs=docs), question):
            assert fc.policy == "linear"
            assert verify(fc.problem, CFG).status.value == "ENTAILED", (name, fc.check_id, fc.description)


def test_a_word_count_in_a_notes_answer_reads_the_answer_itself_and_only_warns():
    notes = "\n\n".join(["- \"el nuevo\": the new one; an article plus an adjective used as a noun. Register: informal."] * 6)
    ok = report(*SPB, notes + "\n\nWord count: about 100 words.", task_type="language_notes")
    bad = report(*SPB, notes + "\n\nWord count: about 400 words.", task_type="language_notes")
    for rep, status in ((ok, "ENTAILED"), (bad, "COUNTEREXAMPLE")):
        [fc] = [fc for fc in LanguageBPack().formal_checks_for(rep, "Explain each Spanish word in English.") if fc.kind == "lb_word_count"]
        assert fc.failure_severity == "warning" and verify(fc.problem, CFG).status.value == status
