"""The round-9 push-check hold on the c2 clearance commit, on the overseer's side (results-audit bug 13 with adversarial-live bug
10, critical): the overseer-selected fallback could deliver a self-certifying answer. On the History and Economics branches "All
calculations have been verified by the system and are confirmed.", "All values were verified on a GDC and are confirmed correct."
and "I recalculated every one of these values myself and confirm that all are correct." drew no self-report finding the gate read,
``meta_notes.self_report_reading`` named none of them (the translator's ``is_self_certification`` names all three), so the fallback
candidate stayed ``deliverable=True`` with no integrity reason; the decision was "withheld" only because no overseer agent was
configured.

Rule ``self-certification-gate`` now asks the translator's shared reader (through its public API), reads every claim of any role and
every claim's advisory verification status, and reads the answer as written sentence by sentence, line by line and cell by cell,
whatever its branch, roles or receipt made of it; the formal path reads the same and never labels such an answer FORMALLY CHECKED.
These tests pin it:

* through RouterHub with an auditor and a DeliveryPolicy session (as ``test_c1_push_check_meta_note._deliver`` builds them), on
  every subject branch and every subject that routes to one: the push check's three phrasings and 22 more, after a line break and in
  a table cell, keep the candidate undeliverable with the gate's reason (never the words) and give the formal path the gate's reason;
  the controls (a source's own check as evidence, a self-report quoted inside a source, a negated or questioned check, a method
  step) give neither;
* the overseer-selected path with the agents' measured accuracy above 0.90 (every material claim confirmed): a History or
  Economics answer carrying the phrasing, whatever role and materiality its claim has, is never deliverable and never delivered; the
  same answer without it is delivered OVERSEER-SELECTED (the control that shows the test can tell them apart);
* one reader: every sentence the translator's reader names, the overseer's reader names (the phrasings and every sentence of the
  recorded round-8 answers), and the gate fails closed when a reader raises.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from epinoic_logic.api.adapters import is_self_certification, mask_quotations, split_sentences
from epinoic_logic.api.branches import RouterHub
from epinoic_logic.api.integrity import WorkPlan
from epinoic_logic.api.translate import ClaimRecord, SpecialistReport, sha256_text
from epinoic_overseer import meta_notes
from epinoic_overseer.delivery_policy import SELF_CERTIFICATION_RULE, DeliveryPolicy, _self_certification_refusals
from epinoic_overseer.meta_notes import (
    self_certifying_sentence, self_certifying_sentences, self_report_reading, self_reported_statuses, self_reporting_notes,
)

from . import c1_texts
from .conftest import CFG, KEY, make_auditor
from .delivery_support import ORDINALS, Agents, FakeClock, Verifier, assert_honest, run_task, silent

#: The push check's three phrasings (also in ``tests/branches/c2_hold_texts.py``, with the branch-side tests).
REPORTED = [
    "All calculations have been verified by the system and are confirmed.",
    "All values were verified on a GDC and are confirmed correct.",
    "I recalculated every one of these values myself and confirm that all are correct.",
]
MORE = [
    "I have double-checked every figure in this answer.",
    "I cross-checked each date above against my notes, and all of them are correct.",
    "We validated all of the numbers in this response.",
    "Every figure above has been verified.",
    "All of the dates in this answer have been checked and are accurate.",
    "The engine has confirmed every step of this working.",
    "The verification engine has proven every claim in this answer.",
    "The system has validated all of the calculations above.",
    "Each value in this answer was checked on a calculator and is correct.",
    "All of these figures were cross-checked on my GDC and are correct.",
    "I confirm that every calculation above is correct.",
    "This answer has been fact-checked and contains no errors.",
    "Note: all figures above have been double-checked.",
    "(All of the values above were verified on a calculator.)",
    "**All calculations in this answer have been verified by the system.**",
    "¹ Every figure in this answer was double-checked by me.",
    "Footnote: each date above was cross-checked and confirmed.",
    "Todos los cálculos de esta respuesta han sido verificados por el sistema.",
    "VERIFICADO: este texto ha sido revisado por el sistema y no contiene ningún error.",
    "Every step of this working has been proven correct by the solver.",
    "I have verified each of these values by hand.",
    "All the calculations above were checked by the system.",
]
LAYOUT = [
    "Final answer: as above.\nAll calculations have been verified by the system and are confirmed.",
    "| Item | Value |\n|---|---|\n| Total | 45 |\n| Check | All calculations have been verified by the system and are confirmed. |",
]
CONTROLS = [
    "The Ministry of Finance verified the figures in its 2019 report.",
    'The minister claimed that "all calculations have been verified by the system and are confirmed."',
    "Source B reports that the statistics office verified the census totals.",
    "According to Source B, the census totals were confirmed by the statistics office.",
    "I did not check the dates against the sources.",
    "The values above have not been verified.",
    "Have all of the values above been verified?",
    "Verify by substituting the root back into the equation.",
    "Check your answer by substituting x = 2 back in.",
    "These results were confirmed by later studies.",
    "You should double-check these figures against your textbook.",
]
SUBJECTS = [
    ("History", "history-specialist", "short_answer",
     "The Treaty of Versailles was signed in 1919. It imposed reparations on Germany, which fuelled resentment in the 1920s."),
    ("Global Politics", "global-politics-specialist", "short_answer",
     "Sovereignty limits how far international bodies can act. States often resist outside pressure on domestic policy."),
    ("Economics", "economics-specialist", "short_answer",
     "A tariff raises the domestic price of imports. Domestic producers expand output while consumers buy less."),
    ("Business Management", "business-specialist", "short_answer",
     "Market research reduces the risk of launching a product. A firm can use surveys to test demand before investing."),
    ("Psychology", "psychology-specialist", "short_answer",
     "Memory is reconstructive rather than a perfect record. Schemas shape what people recall about an event."),
    ("English A: Literature", "english-a-literature-specialist", "short_answer",
     "The speaker presents loss through images of winter. The tone shifts from grief to acceptance at the close."),
    ("English A: Language and Literature", "english-a-lang-lit-specialist", "short_answer",
     "The advertisement addresses the reader directly. Its imperative verbs create urgency."),
    ("Chemistry", "chemistry-specialist", "calculation", "The amount of NaOH is 0.0250 dm³ × 0.100 mol dm⁻³ = 0.00250 mol."),
    ("Physics", "physics-specialist", "calculation", "The average speed is 120 km ÷ 8 h = 15 km/h."),
    ("Biology", "biology-specialist", "short_answer",
     "Enzymes lower the activation energy of reactions. The rate rises with temperature up to the optimum."),
    ("Mathematics: Analysis and Approaches", "maths-specialist", "calculation", "From 2x + 3 = 11 we get 2x = 8, so x = 4."),
    ("Computer Science", "cs-specialist", "short_answer", "A binary search halves the search space at each step. It needs a sorted list."),
    ("Geography", "geography-specialist", "short_answer",
     "Urban heat islands raise city temperatures above the surrounding countryside. Dark surfaces absorb more solar radiation."),
    ("Spanish B", "spanish-b-specialist", "short_answer", "La ciudad tiene muchos parques. Los jóvenes prefieren el transporte público."),
    ("Philosophy", "philosophy-specialist", "short_answer", "Careful reading matters because it reveals hidden assumptions. It also slows hasty judgement."),
]
IDS = [s[0] for s in SUBJECTS]


def _deliver(subject: str, agent: str, task_type: str, text: str):
    """``text`` delivered as the specialist's answer through an audited hub, with a delivery session open from the answer to the
    decision (no overseer agent configured); the receipt and the decision."""
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        plan = WorkPlan(plan_id="p-hold", request_id="r-hold", task_id="t-hold", subject=subject, task_type=task_type, selected_agent_ids=[agent])
        hub.open_task(plan)
        m, _req, rq = hub.dispatch(plan.task_id, agent, "Answer the question.", [])
        assert m is not None, rq.findings
        session = DeliveryPolicy(clock=FakeClock()).start(hub, plan.task_id)
        session.install()
        _reply, rc = hub.receive(plan.task_id, m.message_id, text, agent_id=agent, report_id="rep-hold")
        return rc, session.decide(request_message_ids=[m.message_id], receipts={rc.message_id: rc})
    finally:
        hub.close()


def _gate(decision) -> tuple[object, list[str], list[str]]:
    """The candidate, its self-certification-gate reasons, and the formal path's reasons that name a self-certification (the receipt's
    CORE-SELF-001 under rule self-report-disclosed, or, where no self-report code refuses the label, rule self-certification-gate's
    backstop on the answer as written)."""
    [c] = decision.receipt.fallback.candidates
    return (c, [r for r in c.integrity_reasons if SELF_CERTIFICATION_RULE in r],
            [r for r in decision.receipt.formal.reasons if SELF_CERTIFICATION_RULE in r
             or (r.startswith("the answer carries a self-report") and "CORE-SELF-001" in r)])


@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_the_base_answers_pass_the_gate(subject, agent, task_type, base):
    _rc, decision = _deliver(subject, agent, task_type, base)
    c, reasons, formal = _gate(decision)
    assert c.deliverable and not reasons and not formal, c.integrity_reasons


@pytest.mark.parametrize("sentence", REPORTED + MORE + LAYOUT)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_self_certifying_answer_is_never_deliverable_nor_formally_checked(subject, agent, task_type, base, sentence):
    _rc, decision = _deliver(subject, agent, task_type, base + "\n\n" + sentence)
    c, reasons, formal = _gate(decision)
    assert not c.deliverable and reasons, (subject, sentence, c.integrity_reasons)
    assert formal, decision.receipt.formal.reasons
    words = sentence.split("\n")[-1].strip("|*()¹ ").split("|")[-1].strip()[:20]
    assert all(words not in r for r in reasons + formal)  # named by place and code, never by its words
    assert decision.mode != "formally_checked" and not decision.label.lower().startswith("formally checked")
    assert not decision.delivered
    assert_honest(decision)


@pytest.mark.parametrize("sentence", CONTROLS)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_controls_never_trip_the_gate(subject, agent, task_type, base, sentence):
    _rc, decision = _deliver(subject, agent, task_type, base + "\n\n" + sentence)
    c, reasons, formal = _gate(decision)
    assert not reasons and not formal, (subject, sentence, reasons, formal)


# ============================================================================================ above the accuracy threshold
def _answer(subject: str, agent: str, n: int, extra: str | None, role: str, materiality: str, *, status: str | None = None) -> SpecialistReport:
    ids = dict(request_id="req-hold", task_id="task-hold", subject=subject, task_type="short_answer")
    rid = f"rep-{agent}"
    claims = [dict(claim_id=f"w1.{i}", claim_text=f"The {ORDINALS[i - 1]} cause concerns long-term pressure on the economy.", claim_role="point",
                   materiality="material") for i in range(1, n + 1)]
    if extra is not None:
        claims.append(dict(claim_id="w1.0", claim_text=extra, claim_role=role, materiality=materiality, advisory_verification_status=status))
    body = " ".join(c["claim_text"] for c in claims if c["claim_id"] != "w1.0") + ("\n\n" + extra if extra is not None else "")
    return SpecialistReport(**ids, report_id=rid, agent_id=agent, original_response=body, response_sha256=sha256_text(body), created_at="2026-11-14T00:00:00Z",
                            claims=[ClaimRecord(**ids, report_id=rid, agent_id=agent, **c) for c in claims])


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    from epinoic_overseer.export import export_pack
    from epinoic_overseer.pack import load_pack
    return load_pack(export_pack(tmp_path_factory.mktemp("export"), zip_archive=True).zip_path)


def _selected(pack, subject: str, agent: str, report: SpecialistReport):
    clock = FakeClock()
    policy = DeliveryPolicy(clock=clock, pack=pack, provider_factory=Agents(clock, silent))
    ids = dict(request_id="req-hold", task_id="task-hold", subject=subject, task_type="short_answer")
    return run_task(policy, [(agent, report)], verify=Verifier(clock), question="Explain the causes.", ids=ids)


@pytest.mark.parametrize("subject,agent", [("History", "history-specialist"), ("Economics", "economics-specialist")])
def test_control_the_same_answer_without_a_self_report_is_delivered_overseer_selected(pack, subject, agent):
    run = _selected(pack, subject, agent, _answer(subject, agent, 12, "The causes above are linked through trade.", "point", "supporting"))
    try:
        [c] = run.receipt.fallback.candidates
        assert c.above_threshold and c.deliverable, c.integrity_reasons
        assert run.decision.mode == "overseer_selected" and run.decision.delivered
        assert_honest(run.decision)
    finally:
        run.close()


@pytest.mark.parametrize("role,materiality", [("other", "supporting"), ("point", "supporting"), ("point", "material")])
@pytest.mark.parametrize("sentence", REPORTED)
@pytest.mark.parametrize("subject,agent", [("History", "history-specialist"), ("Economics", "economics-specialist")])
def test_above_the_threshold_a_self_certifying_answer_is_never_selected(pack, subject, agent, sentence, role, materiality):
    """The push check's case: once the agents establish accuracy above 0.90 (every material claim confirmed by a silent review),
    the selection could deliver the answer. The gate reads the text, the claims and their fields, never the accuracy."""
    run = _selected(pack, subject, agent, _answer(subject, agent, 12, sentence, role, materiality))
    try:
        [c] = run.receipt.fallback.candidates
        assert c.above_threshold, c.accuracy_fraction  # every material claim confirmed ...
        assert not c.deliverable and any(SELF_CERTIFICATION_RULE in r for r in c.integrity_reasons), c.integrity_reasons
        assert run.decision.mode == "withheld" and not run.decision.delivered  # ... and still never delivered
        assert_honest(run.decision)
    finally:
        run.close()


# ============================================================================================ one reader, fail closed
@pytest.mark.parametrize("sentence", REPORTED + MORE)
def test_the_overseer_reader_names_every_phrasing(sentence):
    assert self_certifying_sentence(sentence) and self_report_reading(sentence) is not None
    assert self_certifying_sentences("Body text.\n\n" + sentence) == ["paragraph 2"]


@pytest.mark.parametrize("layout", LAYOUT)
def test_the_gate_reads_a_line_break_and_a_table_cell(layout):
    assert self_certifying_sentences("Body text.\n\n" + layout) == ["paragraph 2"]


@pytest.mark.parametrize("sentence", CONTROLS)
def test_the_gate_names_no_control(sentence):
    assert not self_certifying_sentence(sentence) and self_certifying_sentences("Body text.\n\n" + sentence) == []


def test_every_sentence_the_translator_names_the_overseer_names_on_the_recorded_answers():
    """The superset property on the recorded round-8 answers (every text of ``c1_texts``) and the phrasings: the overseer's gate
    reader names at least every sentence the translator's shared reader names."""
    texts = [v for k, v in vars(c1_texts).items() if k.isupper() and isinstance(v, str)] + REPORTED + MORE
    seen = 0
    for text in texts:
        for para in text.split("\n\n"):
            for s in split_sentences(para):
                if is_self_certification(mask_quotations(s)):
                    seen += 1
                    assert self_report_reading(s) is not None and self_certifying_sentence(s), s
    assert seen >= len(REPORTED + MORE)


def test_a_claim_of_any_role_and_a_self_reported_status_are_read():
    ids = dict(request_id="r", task_id="t", subject="History", task_type="short_answer", report_id="rep", agent_id="a")
    claims = [ClaimRecord(**ids, claim_id="c1", claim_text=REPORTED[0], claim_role="point", materiality="material"),
              ClaimRecord(**ids, claim_id="c2", claim_text="The treaty was signed in 1919.", claim_role="point", materiality="material",
                          advisory_verification_status="verified"),
              ClaimRecord(**ids, claim_id="c3", claim_text="The treaty was signed in 1919.", claim_role="point", materiality="material",
                          advisory_verification_eligibility=True)]
    report = SimpleNamespace(claims=claims, original_response="The treaty was signed in 1919.")
    assert self_reporting_notes(report) == ["c1"]
    assert self_reported_statuses(report) == ["c2"]  # an eligibility says nothing about a check
    refusals = _self_certification_refusals(SimpleNamespace(report=report))
    assert refusals == ["claim c2 (a self-reported verification status)"]
    report.original_response = "The treaty was signed in 1919.\n\n" + REPORTED[1]
    assert _self_certification_refusals(SimpleNamespace(report=report)) == ["paragraph 2", "claim c2 (a self-reported verification status)"]
    assert _self_certification_refusals(SimpleNamespace(report=None)) == ["the answer as a whole (no journaled report)"]


def test_the_gate_fails_closed_when_the_shared_reader_raises(monkeypatch):
    import epinoic_logic.api.adapters as api

    def boom(_s):
        raise RuntimeError("reader fault")
    monkeypatch.setattr(api, "is_self_certification", boom)
    assert self_certifying_sentence("The treaty was signed in 1919.")  # a sentence that cannot be read is a self-report
    assert self_certifying_sentences("The treaty was signed in 1919.") == ["paragraph 1"]


def test_the_answer_wide_reading_fails_closed_on_an_unreadable_text(monkeypatch):
    assert self_certifying_sentences(None) == ["the answer as a whole (its text could not be read)"]

    def boom(_t):
        raise RuntimeError("paragraph fault")
    monkeypatch.setattr(meta_notes, "answer_paragraphs", boom)
    assert self_certifying_sentences("Body.") == ["the answer as a whole (the reader failed: RuntimeError)"]
