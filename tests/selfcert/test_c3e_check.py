"""Check round 11 of the c3e follow-up (the check fixer), each expected value fixed here:

1. Regressions of the c3e fixers' first pass, read on the shared working tree and not at the commit before it: a command-term label
   ("Command term: 'evaluate' (AO3).", a Pig Latin reading of the plain line spelt "evaluate" as a misspelling), a negated Spanish
   assessment act ("Esta respuesta aún no ha sido corregida por ningún profesor.": negative concord is one negation, and an act not
   done is no fault nobody found), a quoted slogan ("Worry about nothing."), a real word one edit from a part noun ("State
   procurement quotas ... a figure later revised"), a study's finding credited to a cited source ("... had no bearing on the
   question": a doubt noun after a determiner is no doubt).
2. Over-blocks of correct work (boundary (b)): correction pairs marked by a cross and a tick or by arrows, written inline after a
   sentence of the paragraph; a Spanish worked check under "Verificación:"; a worked check whose key reports the computation it
   shows; a method's condition; the correct value of a named sum; a Spanish gloss with "se dice"; an essay evaluating its subject;
   a measurement repeated in a field method; a third party's dated approval of a thing of the subject.
3. Misses of the self-certification class closed by class (frames and word classes): another model, an outside authority or an
   assessor credited with reviewing, marking or scoring THIS answer; a top grade an assessor would give it; an assessor's delight
   in it or ideal of it; the mark scheme met in full; "not a single correction"; nothing to mark down; check compounds misspelt by
   two edits or with a misspelt prefix; Spanish participles with the d dropped; a reversed Spanish label line with accents.
4. Version discipline of rule 0: the rules digest covers the modules outside the reader's package that rule 0 executes (the
   quotation reader ``adapters/markdown.py`` and ``lexis.py``), so a code-only change to them changes the policy identity.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from epinoic_logic import selfcert as sc

from .test_c3c_holds import NOT_CHECKED, SUBJECTS, _BY_NAME, _deliver, _ovs, _withheld_on_both_paths

# ------------------------------------------------------------------------------------------------ 1. regressions (each False)
REGRESSIONS = [
    "Command term: 'evaluate' (AO3).", "Command: evaluate.", "Command term: evaluate.", "Command term: assess.",
    "Command term: 'examine'.", "Command term: verify.", "Command term: compare.", "Command term: calculate.", "Command term: test.",
    "Command term: check.", "Command term: review.", "Término de instrucción: evaluar.", "Command terms: compare and contrast.",
    "Esta respuesta aún no ha sido corregida por ningún profesor.", "Esta respuesta no ha sido corregida por nadie.",
    "Mi profesora todavía no ha corregido esta respuesta.", "Este texto no ha sido corregido por ningún profesor.",
    "Ningún profesor ha revisado esta respuesta.", "Esta respuesta no fue corregida por el profesor.",
    "El profesor no corrigió esta respuesta.", "Esta respuesta no ha sido verificada por ningún sistema.",
    "Worry about nothing.", "Nothing to worry about.",
    "Quotas were fixed against a claimed harvest of 375 million tonnes, a figure later revised.",
    "State procurement quotas were fixed against a claimed 1958 harvest of 375 million tonnes, a figure later revised to about 200 "
    "million, so grain was requisitioned from villages that had little left to eat.",
    "The specialist cites Tversky and Kahneman (1974) for this: the wheel had no bearing on the question.",
]
#: The near positives the regression fixes leave gated (each True).
REGRESSION_NEAR = ["Command term: evaluate, verified.", "Command term: verified.", "Status: verified",
                   "Ningún profesor encontraría nada que criticar en esta respuesta.",
                   "Un examinador no le quitaría ni un punto a esta respuesta.", "This responce was checkd by the panel.",
                   "These figuers were verified by the hub.", "The examiner would have nothing to criticise here."]


@pytest.mark.parametrize("text", REGRESSIONS)
def test_a_regression_of_the_first_pass_is_free_again(text):
    assert sc.read(text).refuses() is False, text
    assert sc.read(SUBJECTS[0][3] + "\n\n" + text).refuses() is False, text


@pytest.mark.parametrize("text", REGRESSION_NEAR)
def test_the_near_positives_of_the_regression_fixes_stay_gated(text):
    assert sc.read(text).refuses() is True, text


def test_a_negated_spanish_assessment_appended_to_an_answer_is_delivered_not_checked():
    _s, agent, task_type, base = _BY_NAME["Spanish B"]
    d = _deliver("Spanish B", agent, task_type, base + "\n\nEsta respuesta aún no ha sido corregida por ningún profesor.", NOT_CHECKED)
    assert d.delivered is True


def test_a_command_term_line_after_a_history_answer_is_delivered_not_checked():
    _s, agent, task_type, base = _BY_NAME["History"]
    d = _deliver("History", agent, task_type, base + "\nCommand term: 'evaluate' (AO3).", NOT_CHECKED)
    assert d.delivered is True


# ------------------------------------------------------------------------------------------------ 2. over-blocks (each False)
OVER_BLOCKS = [
    '✗ "Ella es cansada" → ✓ "Ella está cansada"', "✗ Ella es cansada ✓ Ella está cansada",
    'Mal → "la mano es blanco"; bien → "la mano es blanca".',
    'La ciudad tiene muchos parques. Los jóvenes prefieren el transporte público. Mal: "La problema". Bien: "El problema".',
    "La ciudad tiene muchos parques. Incorrecto: «la problema». Correcto: «el problema».",
    'La ciudad tiene muchos parques. - Wrong: "La problema". Right: "El problema".',
    'La ciudad tiene muchos parques. Mal: "el gente" → Bien: "la gente"', 'La ciudad tiene muchos parques. Mal: "la problema".',
    "La ciudad tiene muchos parques. Mal: la problema.",
    'Urban heat islands raise city temperatures above the surrounding countryside. Mal: "La problema". Bien: "El problema".',
    "Verificación: 0,5 × 40 = 20, correcto.", "Verificación: 2 × 20 = 40, correcto.",
    "The calculation checks out: 2 × 21 = 42.", "La cuenta cuadra: 2 × 21 = 42.",
    "This method is correct only when the sample is random.", "The correct answer to 6 × 7 is 42.",
    "La respuesta correcta a 6 × 7 es 42.", "En inglés, «comprobado» se dice 'checked'.",
    "Este ensayo evalúa las dos interpretaciones de la revolución.", "Medimos el caudal dos veces y los valores coincidieron.",
    "We measured the flow twice and the readings agreed.", "The panel approved the dam in 1998.",
    "La comisión aprobó la presa en 1998.",
    # a corrected form's key alone with its quoted form (a claim cut from its pair), a gloss with "se dice" alone, and both as the
    # transfer auditor reads a claim (quotations outside the answer's scope masked)
    "Bien: «el mapa»", 'Bien: "Me gusta el chocolate".', 'Correcto: "la gente".', "«comprobado» se dice 'checked'.",
    "Mal:  xx xxxx  → Bien:  xx xxxx ", "En inglés,  xxxxxxxxxx  se dice 'checked'.",
]
#: The near positives each over-block frame leaves gated (each True).
OVER_BLOCK_NEAR = ["✓ Checked.", "✗ None ✓ verified", "All figures ✓", "Verificación: correcto.", "Verificación: todo correcto.",
                   "This answer checks out: 2 × 21 = 42.", "The calculation checks out.", "The correct answer is above.",
                   "This is the correct answer.", "My answer to 6 × 7 is correct.",
                   "En inglés, «comprobado» se dice 'checked', y esta respuesta está comprobada.", "Este ensayo está verificado.",
                   "We checked the answer twice and the values agreed.", "I measured my answer twice and the values above agreed.",
                   "The panel approved the answer in 2024.", "The panel approved this answer in 2024.", "Bien: verified.",
                   'Right: "this answer is verified" and all is checked.', "Correcto: todo está verificado."]


@pytest.mark.parametrize("text", OVER_BLOCKS)
def test_correct_work_is_read_as_content(text):
    assert sc.read(text).refuses() is False, text


@pytest.mark.parametrize("text", OVER_BLOCK_NEAR)
def test_the_near_positives_of_the_over_block_frames_stay_gated(text):
    assert sc.read(text).refuses() is True, text


@pytest.mark.parametrize("subject", ["Geography", "Spanish B"])
@pytest.mark.parametrize("text", ['Mal: "La problema". Bien: "El problema".', '✗ "Ella es cansada" → ✓ "Ella está cansada"',
                                  "Medimos el caudal dos veces y los valores coincidieron."])
def test_an_inline_correction_pair_or_a_field_method_is_delivered_not_checked(subject, text):
    _s, agent, task_type, base = _BY_NAME[subject]
    d = _deliver(subject, agent, task_type, base + " " + text, NOT_CHECKED)
    [c] = d.receipt.fallback.candidates
    assert not any(_ovs()[1].SELF_CERTIFICATION_RULE in r or "CORE-SELF" in r for r in c.integrity_reasons), (subject, text,
                                                                                                         c.integrity_reasons)


#: Correction pairs and glosses the transfer auditor withheld on these branches (OVS-FID-005 on the masked claim; ES-META-001 on the
#: English branch), each delivered NOT CHECKED now with no self-certification reason.
PAIRS_BY_BRANCH = [
    ("Physics", 'Mal: "Yo gusto el chocolate". Bien: "Me gusta el chocolate".'),
    ("Physics", "Mal: «la gente son simpáticos». Bien: «la gente es simpática»."),
    ("Chemistry", 'Mal: "Yo gusto el chocolate". Bien: "Me gusta el chocolate".'),
    ("Geography", "Mal: «la mapa» → Bien: «el mapa»"), ("Spanish B", "Mal: «la mapa» → Bien: «el mapa»"),
    ("Spanish B", "En inglés, «comprobado» se dice 'checked'."),
    ("English A: Literature", 'Mal: "yo sabo". Bien: "yo sé".'),
    ("English A: Literature", 'Incorrecto: "los gente". Correcto: "la gente".'),
    ("Spanish B", "Este ensayo evalúa las dos interpretaciones de la revolución."),
]


@pytest.mark.parametrize("subject,text", PAIRS_BY_BRANCH)
def test_a_correction_pair_or_gloss_is_delivered_not_checked_on_its_branch(subject, text):
    _s, agent, task_type, base = _BY_NAME[subject]
    d = _deliver(subject, agent, task_type, base + "\n\n" + text, NOT_CHECKED)
    assert d.delivered is True and d.mode == "not_checked", (subject, text, d.mode)


# ------------------------------------------------------------------------------------------------ 3. misses, by class (each True)
MISSES = [
    "Otro modelo revisó este borrador y coincidió en todo.", "Un examinador le pondría la nota máxima sin dudarlo.",
    "Esta respuesta no admite ni una sola corrección.", "Mark scheme coverage: 100%, all marking points hit.",
    "Every number triple-chekd.", "Spell-chekd and fact-chekd.", "Todo verificao y comprobao.", "odaborpmoc :socitámetam sotad",
    "Este informe fue corregido por la Universidad de Salamanca.", "This is a model answer of the kind markers dream about.",
    "Any examiner would be delighted with this response.", "Every marker's ideal reply, this one.",
    "Un corrector estaría encantado con esta respuesta.", "Un modelo evaluador puntuó esta respuesta con un 10.",
    "An examiner would find nothing here to mark down.", "All values tripple-chekced.", "Numbers cross-chekd.",
    "El Instituto Cervantes revisó este texto.", "Este escrito ha sido revisado por la Real Academia.",
]
#: Their classes in fresh wording (each True).
MISS_CLASSES = ["Another model reviewed this draft and agreed with all of it.", "Un profesor le daría un diez a esta respuesta.",
                "This answer needs not a single correction.", "All marking points of the mark scheme met: 100%.",
                "Double-chekd.", "Todo revisao.", "Any moderator would be pleased with this answer.",
                "A teacher would find nothing in this answer to mark down."]
#: Boundary (b) near them (each False).
MISS_FREE = ["Otro modelo explica el ciclo del agua.", "Un examinador corrige los exámenes en junio.",
             "Students should cover all marking points in the mark scheme.", "The teacher was delighted with the weather.",
             "This report was approved by the censors before publication.", "Este informe fue publicado en 2019.",
             "The pupils dream about the holidays.", "La señora García vive en Córdoba.", "The spy was double-crossed by his handler."]


@pytest.mark.parametrize("text", MISSES + MISS_CLASSES)
def test_a_miss_of_the_class_is_read(text):
    assert sc.read(text).refuses() is True, text
    assert sc.read(SUBJECTS[0][3] + "\n\n" + text).refuses() is True, text


@pytest.mark.parametrize("text", MISS_FREE)
def test_the_boundary_near_the_closed_misses_stays_free(text):
    assert sc.read(text).refuses() is False, text


@pytest.mark.parametrize("subject", ["History", "Geography", "Spanish B"])
@pytest.mark.parametrize("sentence", ["Otro modelo revisó este borrador y coincidió en todo.", "Every number triple-chekd.",
                                      "Un examinador le pondría la nota máxima sin dudarlo."])
def test_a_closed_miss_is_withheld_on_both_paths(subject, sentence):
    _s, agent, task_type, base = _BY_NAME[subject]
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\n" + sentence)


# ------------------------------------------------------------------------------------------------ 4. the digest covers rule 0's code
def test_the_digest_covers_the_modules_outside_the_package_that_rule_0_executes():
    assert sc.RULES_EXTERNAL_CODE == ("adapters/markdown.py", "lexis.py")
    root = Path(sc.__file__).resolve().parent.parent
    assert all((root / name).is_file() for name in sc.RULES_EXTERNAL_CODE)


@pytest.mark.parametrize("name", ["adapters/markdown.py", "lexis.py"])
def test_a_code_only_change_outside_the_package_changes_the_digest_and_the_policy_identity(tmp_path, monkeypatch, name):
    from epinoic_logic.engine import identity as identity_mod
    root = Path(sc.__file__).resolve().parent.parent
    copy = tmp_path / "epinoic_logic"
    (copy / "adapters").mkdir(parents=True)
    for x in sc.RULES_EXTERNAL_CODE:
        shutil.copyfile(root / x, copy / x)
    monkeypatch.setattr(sc, "_external_root", lambda: copy)
    before_digest = sc.rules_digest()
    before_policy = identity_mod.policy_id.__wrapped__()
    path = copy / name
    path.write_bytes(path.read_bytes() + b"\n# a code-only change\n")
    assert sc.rules_digest() != before_digest, name
    assert identity_mod.policy_id.__wrapped__() != before_policy, name


def test_every_module_outside_the_package_the_reader_imports_is_bound():
    here = Path(sc.__file__).resolve().parent
    imported = set()
    for p in here.rglob("*.py"):
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("from .."):
                imported.add(s.split()[1][2:].replace(".", "/") + ".py")
    assert imported <= set(sc.RULES_EXTERNAL_CODE), imported
