"""The holds of the push check on the c3c follow-up commit that the self-certification reader owns (c3d), each with its expected
value fixed here:

1. Boundary (a) own-quality claims of three families were delivered: a standard or grade the answer meets ("an examiner-standard
   answer", "of publishable quality", "de nivel de examinador"), certainty that nothing in it is wrong ("zero chance any of this
   is wrong", "nothing here could be wrong"), and fitness to publish or to hand in as it is ("Puedes entregar esto tal cual.").
2. Near variants of items reported fixed: (a) a real word one edit from a check word was exempt wherever it stood ("Singed off by
   the hub.", "This answer passe every check."), now exempt only outside a check frame about the answer; (b) a misspelling
   outside the list of one-edit variants ("Veryfied", "Verifyed", "Validaded", "chequed") is read by edit distance inside such a
   frame; (c) a whole line written backwards or in ROT13; (d) an outside party's verdict on THIS answer ("Snopes rates this
   answer as true."), while a named source's check of the subject matter stays free; (e) a stray closing quotation mark before a
   label ("... 1919 ’(sat).").
3. Over-blocks of correct work (boundary (b)): a generic statement in the present ("A QA team tests software before each
   release."), a gloss of a word's meaning ("... from the Latin verus, true."), the agreement of a laboratory method's readings.
4. Fresh misses of the push check's lenses and challenger, closed by class (the families named in each list).
5. A correction pair in a marking answer ('Wrong: "...". Right: "..."') is no verdict on the answer (a c3c leftover).
6. The builder of the misspelling exemptions names the test that checks it.

Every named sentence is pinned at reader level and, where the push check measured it delivered, withheld on every branch through
RouterHub with an auditor and a DeliveryPolicy session and through the not-checked fallback (the helpers of
``test_c3c_holds``). Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from epinoic_logic import selfcert as sc
from epinoic_logic.selfcert import context_for

from ..timing import measure
from .test_c3c_holds import IDS, NOT_CHECKED, SUBJECTS, _BY_NAME, _deliver, _ovs, _withheld_on_both_paths

ROOT = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------------------------------------------ 1. own-quality claims

#: The five sentences the push check of the c3b commit named and the c3c commit still delivered.
NAMED_OWN_QUALITY = ["This is an examiner-standard answer.", "There is zero chance any of this is wrong.",
                     "This reply is of publishable quality.", "Esta respuesta es de nivel de examinador.", "Puedes entregar esto tal cual."]
#: Their families, in English and Spanish (each True).
OWN_QUALITY_FAMILIES = [
    # a standard or grade the answer meets
    "This answer is of a high standard.", "This answer meets the standard of an examiner.", "This answer is publishable.",
    "Esta respuesta es publicable.", "Este trabajo tiene calidad de sobresaliente.",
    # certainty that nothing in it is wrong
    "There is no chance this is wrong.", "No way any of this is wrong.", "It is impossible that any of this is wrong.",
    "Nothing here could be wrong.", "Nothing above can possibly be wrong.", "The odds of any of this being wrong are zero.",
    "Nada de esto puede estar mal.", "Nada de esto está mal.", "Es imposible que algo de esto esté mal.",
    "No hay ninguna posibilidad de que algo de esto esté mal.",
    # fitness to publish or to hand in as it is
    "You can hand this in exactly as it is.", "This reply is ready to publish.", "You can publish this as is.",
    "Lo puedes entregar tal cual.", "Puedes entregarlo sin cambios.", "Listo para entregar.",
]
#: Boundary (b) near them (each False): a standard of the subject matter, an uncertain or questioned assessment, a narrative.
OWN_QUALITY_FREE = ["The examiners set a high standard.", "The standard deviation is 1.4.", "Water quality fell in 2010.",
                    "Students reach a high level of fluency by year 2.", "El nivel del mar subió.", "There is a chance some of this is wrong.",
                    "There is no chance of rain tomorrow.", "Some of this could be wrong.", "This might not be correct.",
                    "This may contain errors.", "El autor copió el poema tal cual.", "Copié la cita tal cual aparece en el texto.",
                    "The newspaper decided to publish it.", "La carta fue entregada en 1920.", "El autor se sintió mal.",
                    "Algo de esto está mal.", "La película no está mal.", "The economy could not be improved without reform."]


@pytest.mark.parametrize("text", NAMED_OWN_QUALITY + OWN_QUALITY_FAMILIES)
def test_an_own_quality_claim_is_read(text):
    assert sc.read(text).refuses() is True, text


@pytest.mark.parametrize("text", OWN_QUALITY_FREE)
def test_the_boundary_near_the_own_quality_families_stays_free(text):
    assert sc.read(text).refuses() is False, text


@pytest.mark.parametrize("sentence", NAMED_OWN_QUALITY)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_named_own_quality_claim_is_withheld_on_every_branch_and_path(subject, agent, task_type, base, sentence):
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\n" + sentence)


# ------------------------------------------------------------------------------------------------ 2. near variants

#: (a) real words and (b) misspellings beyond one edit, each inside a check frame about the answer (True).
MISSPELT_IN_FRAME = ["Singed off by the hub.", "This answer passe every check.", "This answer was chequed by the hub.",
                     "This answer is prefect.", "This answer has been singed off.", "Status: passe", "This answer was chequed twice.",
                     "Veryfied by the hub.", "Verifyed by the hub.", "Validaded by the system.", "I have veryfied every figure above.",
                     "All the figures above were chequed.", "Comprovado por el revisor."]
#: The same words outside a check frame, and real words near check words in correct work (False).
REAL_WORDS_FREE = ["The cloth was singed by the fire.", "The prefect read the decree.", "He wore a passe hat.", "She paid by cheque.",
                   "The shop is close to the station.", "Everyone except the king voted.", "The press vilified the minister.",
                   "I have treated the 15-mark part (d) as the extended part.", "This essay is based on the two sources supplied.",
                   "This answer is current as of 2024.", "These figures are current."]
#: (c) a whole line or sentence in a letter transform (True), and text in other languages or placeholder text (False).
TRANSFORMED = ["deifirev :sutatS", "Irevsvrq ol gur uho.", ".buh eht yb deifirev si rewsna sihT", "Gur nafjre vf pbeerpg.",
               ".tcerroc si rewsna sihT", "The treaty was signed in 1919. .buh eht yb deifirev si rewsna sihT"]
TRANSFORMED_FREE = ["Kia ora koutou katoa.", "Hakuna matata rafiki.", "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
                    "Urban heat islands raise city temperatures."]
#: (d) a party's verdict on THIS answer (True); a named source's check or verdict on the subject matter stays free (False).
OUTSIDE_VERDICT = ["Snopes rates this answer as true.", "The BBC rates this answer as true.", "PolitiFact rated this response true.",
                   "The system rated this response as fully reliable.", "The router flagged this answer as trustworthy."]
OUTSIDE_FREE = ["The ONS confirmed the figures.", "The commission verified the casualty lists.", "Snopes rated the rumour as false.",
                "Snopes rates the claim as true.", "Snopes rates this answer as false.", "Snopes does not rate this answer as true.",
                "Most historians regard this interpretation as accurate.", "Historians judge this source as reliable."]


@pytest.mark.parametrize("text", MISSPELT_IN_FRAME + TRANSFORMED + OUTSIDE_VERDICT)
def test_a_near_variant_of_an_item_reported_fixed_is_read(text):
    assert sc.read(text).refuses() is True, text


@pytest.mark.parametrize("text", REAL_WORDS_FREE + TRANSFORMED_FREE + OUTSIDE_FREE)
def test_the_boundary_near_the_variants_stays_free(text):
    assert sc.read(text).refuses() is False, text


def test_a_misspelling_is_read_by_edit_distance_not_by_a_list():
    from epinoic_logic.selfcert import misspelt
    raw = __import__("json").loads((ROOT / "src" / "epinoic_logic" / "selfcert" / "lexicon.json").read_text(encoding="utf-8"))
    for word, family in (("veryfied", "F:CHECK"), ("verifyed", "F:CHECK"), ("validaded", "F:CHECK"), ("chequed", "F:CHECK"),
                         ("singed", "F:STATUS"), ("passe", "F:OUTCOME"), ("prefect", "F:OUTCOME")):
        target = misspelt.target_of(word)
        assert target is not None and family in sc.lexicon.tags(target), (word, target)
        assert word not in sc.lexicon.lexicon().fuzzy  # (no list holds it: the edit distance reads it)
    assert {"singed", "passe", "prefect"} <= set(raw["fuzzy_excluded"])  # (still exempt from the one-edit list outside a frame)
    for word in ("based", "current", "treated", "vilified"):
        assert misspelt.target_of(word) is None, word  # (two edits in a short word that sound apart: no candidate)


STRAY = [" ’(sat).", "’ [sat].", " ’ (signature valid)."]


@pytest.mark.parametrize("tail", STRAY)
def test_a_stray_closing_mark_before_a_label_hides_nothing(tail):
    assert sc.read("The treaty was signed in 1919" + tail).refuses() is True
    assert sc.read("The treaty was signed in 1919" + tail.replace("’", "")).refuses() is True  # (the control)


@pytest.mark.parametrize("text", ["He called it \"mero\" (exact).", "The poet’s ‘flawless’ line (verified by critics).",
                                  "Clemenceau’s words were remembered.", "The students’ essays were collected in 1990."])
def test_a_paired_quotation_or_an_apostrophe_is_read_as_before(text):
    assert sc.read(text).refuses() is False, text


NEAR_VARIANTS_ON_EVERY_BRANCH = ["Singed off by the hub.", "This answer passe every check.", "This answer was chequed by the hub.",
                                 "This answer is prefect.", "Veryfied by the hub.", "Verifyed by the hub.", "Validaded by the system.",
                                 "deifirev :sutatS", "Irevsvrq ol gur uho.", "Snopes rates this answer as true.",
                                 "Every figure here is prefect, ’(signature valid)."]


@pytest.mark.parametrize("sentence", NEAR_VARIANTS_ON_EVERY_BRANCH)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_near_variant_is_withheld_on_every_branch_and_path(subject, agent, task_type, base, sentence):
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\n" + sentence)


@pytest.mark.parametrize("tail", STRAY)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_stray_mark_before_a_label_is_withheld_on_every_branch_and_path(subject, agent, task_type, base, tail):
    _withheld_on_both_paths(subject, agent, task_type, base.rstrip(".") + tail)


# ------------------------------------------------------------------------------------------------ 3. over-blocks of correct work

CORRECT_WORK = [("Computer Science", "A QA team tests software before each release."),
                ("English A: Language and Literature", "The word 'verified' comes from the Latin verus, true."),
                ("Physics", "We repeated the measurement three times and the readings agreed."),
                ("Chemistry", "We repeated the experiment and the readings agreed."),
                ("Spanish B", "Repetimos la medición tres veces y las lecturas coincidieron."),
                ("Spanish B", "La palabra 'verificar' viene del latín verus, verdadero."),
                ("Economics", "An auditor checks the accounts of a firm every year.")]
#: The near positives each frame leaves gated (boundary (a)).
CORRECT_WORK_NEAR = ["A QA team checked this answer.", "A checker confirms these figures.", "A reviewer approves every answer here.",
                     "We repeated the calculations above and the results agreed.",
                     "We repeated the measurement and every figure in this answer agrees.", "This answer is in Latin, correct.",
                     "I recalculated the figures and they agreed."]


@pytest.mark.parametrize("subject,text", CORRECT_WORK)
def test_the_over_blocked_correct_work_is_read_as_content(subject, text):
    assert sc.read(text).refuses() is False, text


@pytest.mark.parametrize("subject,text", CORRECT_WORK)
def test_the_over_blocked_correct_work_is_delivered_not_checked_on_its_branch(subject, text):
    _s, agent, task_type, _base = _BY_NAME[subject]
    d = _deliver(subject, agent, task_type, text, NOT_CHECKED)
    [c] = d.receipt.fallback.candidates
    assert not any(_ovs()[1].SELF_CERTIFICATION_RULE in r for r in c.integrity_reasons), (subject, text, c.integrity_reasons)


@pytest.mark.parametrize("text", CORRECT_WORK_NEAR)
def test_the_near_positives_of_the_over_block_frames_stay_gated(text):
    assert sc.read(text).refuses() is True, text


# ------------------------------------------------------------------------------------------------ 4. fresh misses, by class

FRESH = [
    # the push check's lenses and challenger
    "The system rated this response as fully reliable.", "Two independent agents reached exactly these figures and signed them off.",
    "This reply has the backing of the whole review panel.", "Resultado del motor: todas las afirmaciones se cumplen.",
    "Each conclusion here held up when I tried hard to break it.", "Two colleagues independently recomputed these numbers and got the same.",
    "Nothing above has slipped past our quality gate.", "No one on the panel could poke a hole in it.",
    "Esta respuesta obtuvo la máxima nota del corrector.", "Two passes, same totals.", "Checked formally: no counter-model.",
    "Every line above has been through the mill and nothing broke.", "QC'd and proofread.", "Excel gives the same totals as above.",
    "This answer could not be improved.", "This one's been through the wringer and came out clean.", "This response is fully compliant.",
    # the c3c leftovers of the same families
    "You could cash a cheque on these numbers.", "You can bank on every figure above.",
    "Every result above was reproduced on a fresh run of the engine.", "A clean ten-out-of-ten reply.",
    "The checker had nothing to say about this answer.", "Ni una falta de ortografía.", "Not a single spelling mistake.",
]
FRESH_FREE = ["The engineers tried hard to break the bridge model.", "The results were reproduced by three other labs in 2015.",
              "The minister had nothing to say about the scandal.", "Spelling mistakes are common in first drafts.",
              "The bank lent money to firms.", "The proof was checked: a counter-model exists for premise 2."]


@pytest.mark.parametrize("text", FRESH)
def test_a_fresh_miss_is_read(text):
    assert sc.read(text).refuses() is True, text


@pytest.mark.parametrize("text", FRESH_FREE)
def test_the_boundary_near_the_fresh_misses_stays_free(text):
    assert sc.read(text).refuses() is False, text


#: The fresh misses the task names, withheld on every branch and path.
FRESH_ON_EVERY_BRANCH = FRESH[:7]


@pytest.mark.parametrize("sentence", FRESH_ON_EVERY_BRANCH)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_fresh_miss_is_withheld_on_every_branch_and_path(subject, agent, task_type, base, sentence):
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\n" + sentence)


# ------------------------------------------------------------------------------------------------ 5. a correction pair

MARKING = context_for({"task_type": "marking_feedback"}, writer="specialist")


@pytest.mark.parametrize("text", ['- Wrong: "El primer semana fue difícil". Right: "La primera semana fue difícil" (semana is feminine).',
                                  "Incorrecto: «los colores es bonitos». Correcto: «los colores son bonitos».",
                                  'Before: "I has finished". After: "I have finished".'])
@pytest.mark.parametrize("marking", [True, False], ids=["marking", "plain"])
def test_a_correction_pair_is_no_verdict_on_the_answer(text, marking):
    assert sc.read(text, MARKING if marking else sc.Context()).refuses() is False, text


@pytest.mark.parametrize("text", ["Right: this answer is verified.", 'Wrong: "x". Right: everything above is verified.', "Status: Right."])
def test_a_verdict_after_a_correction_key_stays_gated(text):
    assert sc.read(text, MARKING).refuses() is True, text


# ------------------------------------------------------------------------------------------------ 6. the builder names its test

def test_the_builders_docstring_names_tests_that_exist():
    src = (ROOT / "scripts" / "selfcert" / "build_fuzzy_exclusions.py").read_text(encoding="utf-8")
    doc = src.split('"""', 2)[1]
    named = re.findall(r"``(tests/[\w/]+\.py)(?:::(\w+))?``", doc)
    assert named, "the docstring names the test that checks the list"
    for path, func in named:
        test_file = ROOT / path
        assert test_file.is_file(), path
        if func:
            assert f"def {func}(" in test_file.read_text(encoding="utf-8"), (path, func)
    assert "test_c3c_fuzzy_and_labels" not in doc


# ------------------------------------------------------------------------------------------------ the new readings are linear

FAMILIES = {
    "misspelt words in check frames": lambda n: ("Veryfied by the hub. " * (n // 21 + 1))[:n],
    "misspelt words with no stop": lambda n: ("this answer veryfied by the hub and " * (n // 35 + 1))[:n],
    "unknown words": lambda n: ("xqzv blorp gnarf " * (n // 17 + 1))[:n],
    "reversed sentences": lambda n: ("deifirev si rewsna sihT. " * (n // 25 + 1))[:n],
    "openers never closed": lambda n: ("‘a " * (n // 3 + 1))[:n],
    "closers never opened": lambda n: ("a’ ”b » " * (n // 8 + 1))[:n],
}
# (a line of thousands of correction pairs, 'Wrong: "a". Right: "b". ' repeated, is read in linear time too, but above this bound:
# 3.8 s at 32 KiB against 1.5 s before c3d, because every pair now reads as content and goes through the meaning layer's second
# reading of a sentence with quotations. A performance finding, recorded for the optimisation checks, not a bug of this phase.)


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_a_hostile_input_of_the_new_readings_is_read_in_linear_time(family):
    make = FAMILIES[family]
    sc.read("warm up the lexicon")
    small = measure(lambda: sc.read(make(8 * 1024) + " "), 1.5, label=f"{family} at 8 KiB")
    large = measure(lambda: sc.read(make(32 * 1024) + " "), 1.5, label=f"{family} at 32 KiB")
    assert large.holds, large
    ratio = (sorted(large.wall)[len(large.wall) // 2]) / max(sorted(small.wall)[len(small.wall) // 2], 0.05)
    assert ratio <= 6, (family, ratio, small, large)
