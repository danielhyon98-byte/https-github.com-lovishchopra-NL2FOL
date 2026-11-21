"""Check round 9 of the c3c follow-up on the Geography and Language B branches and the shared readers, each expected value fixed
here: correct work the branches lens found named (an own correction written with "Wrong:"/"Right:" labels or another connector,
an article's body paragraphs, a per cent of another site's count worked out in brackets, agreement with a named relation, the
parts of a total restated in a rate), and the faulty twins that must stay named.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from . import d9d10_hub as H
from . import d9d10_texts as T

ESP_ARROW = '- "Espero que nos vemos pronto" → "Espero que nos veamos pronto"'
SEMANA = '- "El primer semana fue difícil" → "La primera semana fue difícil" (semana'

_BASE: dict = {}


def _new(name: str, text: str):
    """The error and warning findings and the non-entailed checks of ``text`` that the recorded answer ``name`` does not have."""
    if name not in _BASE:
        _BASE[name] = H.recorded(name)
    b = _BASE[name]
    rc = H.recorded(name, text)
    old = {(f.code, f.severity, f.message[:140]) for f in b.findings}
    new = [f.code for f in rc.findings if f.severity in ("error", "warning") and (f.code, f.severity, f.message[:140]) not in old]
    old_checks = [c for c in H.checks(b) if c[1] != "ENTAILED"]
    checks = [c for c in H.checks(rc) if c[1] != "ENTAILED" and c not in old_checks]
    return new, checks


CORRECTIONS = [
    (SEMANA, '- Wrong: "El primer semana fue difícil". Right: "La primera semana fue difícil" (semana'),
    (ESP_ARROW, '- Wrong: "Espero que nos vemos pronto". Right: "Espero que nos veamos pronto"'),
    (ESP_ARROW, '- "Espero que nos vemos pronto" ⇒ "Espero que nos veamos pronto"'),
    (ESP_ARROW, '- "Espero que nos vemos pronto". Correct form: "Espero que nos veamos pronto"'),
    (ESP_ARROW, '- "Espero que nos vemos pronto" --> "Espero que nos veamos pronto"'),
    (ESP_ARROW, '- "Espero que nos vemos pronto" > "Espero que nos veamos pronto"'),
    (ESP_ARROW, '- "Espero que nos vemos pronto" becomes "Espero que nos veamos pronto"'),
    (ESP_ARROW, '- "Espero que nos vemos pronto" should be "Espero que nos veamos pronto"'),
    (ESP_ARROW, '- Write "Espero que nos veamos pronto", not "Espero que nos vemos pronto"'),
]


@pytest.mark.parametrize("old,new", CORRECTIONS)
def test_an_own_correction_with_another_connector_is_still_a_correction(old, new):
    assert old in T.SP_T16
    found, checks = _new("c3/sp-t16", T.SP_T16.replace(old, new, 1))
    assert found == [] and checks == [], (new, found, checks)


@pytest.mark.parametrize("name,sentence", [
    ("c2/sp-t15", "The body of the article has seven paragraphs."),
    ("c1/ge-t14", "Site 10's count is about 9% of Site 1's (19 ÷ 214)."),
    ("c2/ge-p9c", "The discharge calculation is consistent with the continuity equation Q = A × v."),
])
def test_correct_statements_are_not_named(name, sentence):
    found, checks = _new(name, H.RECORDED[name][0] + "\n\n" + sentence)
    assert found == [] and checks == [], (sentence, found, checks)


@pytest.mark.parametrize("name,sentence,code,check", [
    ("c2/sp-t15", "The body of the article has nine paragraphs.", "INT-SUBJ-004", ("language-b-structure-count-1", "COUNTEREXAMPLE")),
    ("c1/ge-t14", "Site 10's count is about 19% of Site 1's (19 ÷ 214).", "INT-SUBJ-001", ("geography-pair-comparison-1", "COUNTEREXAMPLE")),
])
def test_the_faulty_twins_are_named(name, sentence, code, check):
    found, checks = _new(name, H.RECORDED[name][0] + "\n\n" + sentence)
    assert code in found and check in checks, (sentence, found, checks)


@pytest.mark.parametrize("subject,agent,text", [
    ("Psychology", "psychology-specialist", "Of the 40 participants, 26 passed the memory test, so the pass rate was 26 / 40 = 65%."),
    ("Psychology", "psychology-specialist", "Of the 40 participants, 26 conformed at least once, so the conformity rate was 26 / 40 = 65%."),
    ("Geography", "geography-specialist", "Of the 40 households surveyed, 26 used public transport, so the share was 26 / 40 = 65%."),
    ("Economics", "economics-specialist", "Of the 40 participants, 26 passed the memory test, so the pass rate was 26 / 40 = 65%."),
])
def test_a_part_restated_in_a_worked_rate_is_no_second_part(subject, agent, text):
    rc = H.through_hub(text, "Answer the question.", subject, agent)
    assert "INT-SUBJ-001" not in H.codes(rc), [f.message[:200] for f in rc.findings if f.code == "INT-SUBJ-001"]


def test_parts_over_their_total_are_still_named():
    rc = H.through_hub("Of the 40 households surveyed, 46 used public transport.", "Answer the question.", "Geography", "geography-specialist")
    assert "INT-SUBJ-001" in H.codes(rc)


@pytest.mark.parametrize("name,sentence", [
    ("c1/sp-t14", "Entre 1960 y 2015 la población cayó un treinta y ocho por ciento."),
    ("c1/sp-t14", "Si un alquiler sube de 500 € a 650 €, sube un 20 %."),
    ("c1/sp-t14", "Si un alquiler sube de quinientos a seiscientos cincuenta euros, sube un veinte por ciento."),
    ("c1/sp-t14", "En 2015 la escuela llevaba nueve años cerrada (desde 2009)."),
    ("c3/sp-t16", "There are seven corrections above."),
    ("c2/ge-p9c", "The two storms were 16 years apart (2006 and 2024)."),
])
def test_the_branch_misses_of_the_check_round_are_named(name, sentence):
    found, checks = _new(name, H.RECORDED[name][0] + "\n\n" + sentence)
    assert any(c in found for c in ("INT-SUBJ-001", "INT-SUBJ-004")) and checks, (sentence, found, checks)


@pytest.mark.parametrize("name,sentence", [
    ("c1/sp-t14", "Si un alquiler sube de 500 € a 650 €, sube un 30 %."),
    ("c1/sp-t14", "En 2015 la escuela llevaba seis años cerrada (desde 2009)."),
    ("c3/sp-t16", "There are six corrections above."),
    ("c2/ge-p9c", "The two storms were 18 years apart (2006 and 2024)."),
])
def test_their_correct_twins_are_not_named(name, sentence):
    found, checks = _new(name, H.RECORDED[name][0] + "\n\n" + sentence)
    assert found == [] and checks == [], (sentence, found, checks)
