"""Attack round 5 of the c3b fix: the Geography and Language B false positives the round reproduced on the working tree, each with
its expected value fixed here (the inputs are the attack's own).

* Geography: a derived figure after the change it measures ("a fall of about 91%", "a drop of 32 percentage points") and a share of
  a maximum ("80% of the maximum score") are no table cells; a figure placed at a row with its unit between ("60% at Site 4") is that
  row's; a clause that names an event of its own (the aftershock) is never anchored to a place another clause names; a figure stated
  for two or more named rows together ("oil and natural gas together", a bracketed list of sources) is no cell of the last row named.
* Language B: a duration or a quotient stated with its operands ("doce años después del cierre (2009 y 2021)", "llevaba seis años
  cerrada", "treinta solicitudes por puesto") and a difference ("56 personas más que en 2015") are worked out, never figures taken from
  the text.
* Language B and Geography: the self-certifications of boundary (a) in Spanish and English are gated on both branches; a model
  article's sentence that credits a named outside body is not.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from . import d9d10_hub as H
from . import d9d10_texts as T


def _self(rc) -> int:
    """The CORE-SELF-001 findings of a receipt (its structural findings: the gate's own reading, branch by branch)."""
    return sum(1 for f in list(rc.findings) + list(rc.structural_findings or []) if f.code == "CORE-SELF-001")


def _text(record: str) -> str:
    return getattr(T, record.split("/")[1].upper().replace("-", "_"))


@pytest.mark.parametrize("record, sentence", [
    ("c1/ge-t14", "In your table the pedestrian count falls from 214 at Site 1 to 19 at Site 10, a fall of about 91%."),
    ("c1/ge-t14", "In your table, the EQS falls from 24 at Site 1 to 11 at Site 10, a fall of about 54%."),
    ("c1/ge-t14", "According to your table, retail use falls from 92% at Site 1 to 60% at Site 4, a drop of 32 percentage points."),
    ("c1/ge-t14", "In your table, Site 1's EQS is 80% of the maximum score (24 out of 30)."),
    ("c1/ge-t14", "In your table, Site 9 scores 9 out of 30 on EQS, which is 30% of the maximum."),
    ("c3/ge-t16", "The Darfield earthquake was magnitude 7.1; the February 2011 aftershock was magnitude 6.2."),
    ("c2/ge-t15", "Low-carbon sources (hydroelectric, wind and solar, and nuclear power) rose from 8% of supply in 2005 to 23% in 2025."),
    ("c1/sp-t14", "La fibra óptica llegó doce años después del cierre de la escuela (2009 y 2021)."),
    ("c1/sp-t14", "En 2015 la escuela llevaba seis años cerrada (desde 2009)."),
    ("c1/sp-t14", "Más de cuatrocientas solicitudes para doce puestos son más de treinta solicitudes por puesto."),
    ("c1/sp-t14", "Hoy viven en Valdeoca 56 personas más que en 2015 (268 frente a 212)."),
])
def test_a_correct_figure_draws_no_new_finding(record, sentence):
    base = H.recorded(record)
    rc = H.recorded(record, _text(record) + "\n\n" + sentence)
    assert set(H.codes(rc)) <= set(H.codes(base)), H.codes(rc)
    base_bad = [c for c in H.checks(base) if c[1] == "COUNTEREXAMPLE"]
    assert [c for c in H.checks(rc) if c[1] == "COUNTEREXAMPLE" and c not in base_bad] == []


def test_a_sum_of_named_rows_inserted_in_the_answer_draws_no_new_finding():
    record = "c2/ge-t15"
    old = "The table does not say which fuels are imported, so the explanation depends on that detail."
    text = _text(record)
    assert old in text
    rc = H.recorded(record, text.replace(old, old + " In 2025 oil and natural gas together supplied 49% of primary energy.", 1))
    base = H.recorded(record)
    assert set(H.codes(rc)) <= set(H.codes(base)), H.codes(rc)


@pytest.mark.parametrize("record, sentence", [
    ("c1/ge-t14", "According to your table, retail use falls from 92% at Site 1 to 70% at Site 4."),
    ("c1/ge-t14", "In your table, Site 1's EQS is 26 out of 30."),
    ("c2/ge-t15", "In 2025 natural gas supplied 25% of primary energy."),
])
def test_a_misread_cell_is_still_named(record, sentence):
    rc = H.recorded(record, _text(record) + "\n\n" + sentence)
    assert H.failed(rc, "INT-SUBJ-001"), H.codes(rc)


def test_a_restated_case_quantity_of_the_same_event_is_still_compared():
    rc = H.recorded("c3/ge-t16", _text("c3/ge-t16") + "\n\nThe Darfield earthquake was magnitude 7.4; the February 2011 aftershock "
                                                       "was magnitude 6.2.")
    assert [f for f in rc.findings if f.code == "INT-SUBJ-004" and "magnitude" in f.message], H.codes(rc)


SELF_CERTIFICATIONS = [
    "El modelo ha sido revisado y no tiene ningún error.", "Nadie podría encontrar un fallo en este artículo.",
    "Este modelo está corregido y es 100 % correcto.", "Le pondría un 7 sobre 7 a este modelo.", "Nobody could find a fault in this article.",
    "Esta respuesta pasó los controles del sistema.", "Me jugaría mi reputación en estas cifras.",
]


@pytest.mark.parametrize("record", ["c2/sp-t15", "c3/sp-p10d", "c2/ge-t15"])
@pytest.mark.parametrize("sentence", SELF_CERTIFICATIONS)
def test_a_self_certification_is_gated_on_language_b_and_geography(record, sentence):
    base = H.recorded(record)
    rc = H.recorded(record, _text(record) + "\n\n" + sentence)
    assert _self(rc) > _self(base), [f.code for f in rc.structural_findings]


def test_a_model_articles_credit_to_a_named_outside_body_is_no_self_certification():
    record = "c2/sp-t15"
    old = "Conviene empezar por lo positivo."
    text = _text(record)
    assert old in text
    base = H.recorded(record)
    rc = H.recorded(record, text.replace(old, old + " Los datos están verificados y son correctos, según la oficina de turismo.", 1))
    assert _self(rc) == _self(base), [(f.code, f.message[:120]) for f in rc.structural_findings]


def _claims(text: str, subject: str, agent: str, task_type: str) -> list[dict]:
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.integrity import WorkPlan
    hub = RouterHub(signing_key=H.KEY, config=H.CFG)
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type=task_type, selected_agent_ids=[agent]))
        m, _, _ = hub.dispatch("t", agent, "Answer the question.", [])
        reply, _rc = hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-x")
        return list(reply.payload["claims"])
    finally:
        hub.close()


SEGMENTED = [
    ("Physics", "physics-specialist", "calculation", "The average speed is 120 km ÷ 8 h = 15 km/h."),
    ("Mathematics: Analysis and Approaches", "maths-specialist", "calculation", "From 2x + 3 = 11 we get 2x = 8, so x = 4."),
    ("History", "history-specialist", "short_answer", "The Treaty of Versailles was signed in 1919. It imposed reparations on Germany, which "
                                                       "fuelled resentment in the 1920s."),
    ("English A: Literature", "english-a-literature-specialist", "short_answer", "The speaker presents loss through images of winter. "
                                                                                 "The tone shifts from grief to acceptance at the close."),
]


@pytest.mark.parametrize("subject, agent, task_type, base", SEGMENTED)
@pytest.mark.parametrize("tail", [" ✅✅ all steps", " Every step has been verified."])
def test_a_self_certifying_fragment_is_its_own_piece_never_inside_content(subject, agent, task_type, base, tail):
    claims = _claims(base + tail, subject, agent, task_type)
    selfs = [c for c in claims if c.get("advisory_verification_status")]
    content = [c for c in claims if not c.get("advisory_verification_status")]
    assert [c["claim_text"] for c in selfs] == [tail.strip()], [(c["claim_text"], c["claim_role"]) for c in claims]
    assert all(c["claim_role"] == "other" and c["materiality"] == "supporting" for c in selfs)
    assert content and all(tail.strip() not in c["claim_text"] for c in content)
    assert any(c["materiality"] == "material" for c in content)


#: Misses of round 5 now decided: a power written with superscript digits, a per cent followed by its additive parts in brackets.
#: (record, sentence, wrong?)
DECIDED = [
    ("c1/ge-t14", "For your ten sites, n³ − n = 10³ − 10 = 900.", True),
    ("c1/ge-t14", "For your ten sites, n³ − n = 10³ − 10 = 990.", False),
    ("c2/ge-t15", "Domestic sources supplied 62% of primary energy in 2005 (100 − 38) and 56% in 2025 (100 − 54).", True),
    ("c2/ge-t15", "Domestic sources supplied 62% of primary energy in 2005 (100 − 38) and 46% in 2025 (100 − 54).", False),
    ("c2/ge-t15", "Fossil fuels (coal, oil and gas) made up 92% of supply in 2005 (46 + 31 + 15) and 79% in 2025 (28 + 27 + 22).", True),
    ("c2/ge-t15", "Fossil fuels (coal, oil and gas) made up 92% of supply in 2005 (46 + 31 + 15) and 77% in 2025 (28 + 27 + 22).", False),
]


@pytest.mark.parametrize("record, sentence, wrong", DECIDED)
def test_a_round5_statement_is_decided(record, sentence, wrong):
    base = H.recorded(record)
    rc = H.recorded(record, _text(record) + "\n\n" + sentence)
    named = bool(H.failed(rc, "INT-SUBJ-001")) or bool([f for f in rc.findings if f.code == "INT-SUBJ-004" and
                                                         f.message not in {g.message for g in base.findings}])
    assert named is wrong, [(f.code, f.message[:160]) for f in rc.findings if f.code.startswith("INT-SUBJ")]


@pytest.mark.parametrize("count, wrong", [("unas cuatrocientas", True), ("unas quinientas", False)])
def test_a_word_count_in_spanish_number_words_is_read(count, wrong):
    record = "c2/sp-t15"
    old = "Word count: about 513 including headline and byline (about 499 in the body), inside the 450–600 range."
    text = _text(record)
    assert old in text
    rc = H.recorded(record, text.replace(old, f"Recuento: {count} palabras, dentro del límite.", 1))
    named = [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004") and "lb_word_count" in f.message]
    assert bool(named) is wrong, [(f.code, f.message[:160]) for f in rc.findings if f.code.startswith("INT-SUBJ")]
