"""Hold-fix round 3 of the round-9 push-check hold on the c2 clearance commit: rule ``self-certification-gate`` reads ONE reader
on every release path, and that reader reads by class.

The round-2 lenses reproduced, on the working tree after hold-fix round 2:

* phrasings no reader named on any of the 15 subject branches ("Every value here was verified on a TI-84 calculator.", "Each step
  was proven by the Z3 theorem prover.", "An experienced IB examiner has confirmed all of the values above.", "All the figures have
  been vetted.", "I reran every calculation and got identical results.", "Z3 says every step is valid.", "Every claim above has
  passed verification.", Spanish ones, a table cell "proven sound by Z3 earlier today"), delivered NOT CHECKED and
  OVERSEER-SELECTED;
* a gate that read one reader for a claim roled ``other`` (History) and another for the same sentence roled ``supporting``
  (Economics), so "There are no errors in this answer." was gated on one branch and delivered on the next;
* a self-report counted "accurate" on a silent review that lifted 9/10 to 10/11;
* the router's documented decision (``consolidate.delivery_decision``) allowing a self-certifying answer, the gate living only in
  the port's caller;
* the combined answer's ``release_decision`` releasing a synthesis that says its figures were vetted;
* correct work refused: a named outside body's check of the figures the answer quotes ("Eurostat validated all of the GDP
  figures quoted above.", "The World Bank has verified every figure above."), historians checking dates against parish records,
  a worked check ("Substituting back, 2(4) + 3 = 11, which confirms the answer."), a self-report quoted inside a source under
  analysis, a statistics office's check reported as evidence.

These tests pin each, on every branch and path they name. The turn check's refusal label is pinned in
``tests/integration/test_c2_hold_round2_turn_check.py``, the refusal map in ``test_port_adapter.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from epinoic_logic.api.adapters import is_self_certification
from epinoic_logic.api.branches import RouterHub
from epinoic_logic.api.integrity import SynthesizedClaim, WorkPlan
from epinoic_overseer.consolidate import delivery_decision, may_deliver
from epinoic_overseer.delivery_policy import SELF_CERTIFICATION_RULE, DeliveryConfig
from epinoic_overseer.meta_notes import claim_self_report, payload_self_reports, self_report_reading

from .conftest import CFG, KEY, make_auditor
from .delivery_support import assert_honest, contest
from .test_c2_hold_round2_gate import _answer, _deliver, _selected, pack  # noqa: F401 - the module-scoped pack fixture
from .test_c2_hold_self_certification_gate import IDS, SUBJECTS, _gate

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

#: The phrasings lens of hold-fix round 2 (every one missed on all 15 subject branches).
ROUND3 = [
    "Every value here was verified on a TI-84 calculator.",
    "All figures were confirmed with a Casio fx-991 calculator.",
    "*Note: all figures were confirmed with a Casio fx-991 calculator.*",
    "Each step was proven by the Z3 theorem prover.",
    "**Each step was proven by the Z3 theorem prover.**",
    "An experienced IB examiner has confirmed all of the values above.",
    "Each value was signed off by my teacher.",
    "All the figures have been vetted.",
    "I reran every calculation and got identical results.",
    "Recalculating everything gave exactly the same answers.",
    "Z3 says every step is valid.",
    "Every claim above has passed verification.",
    "Checked in Excel: all values correct.",
    "Cross-checked against my notes: all correct.",
    "I can vouch for the accuracy of every figure.",
    "The calculator and I agree on every value.",
    "Cada valor fue corroborado con la calculadora.",
    "He vuelto a hacer todos los cálculos y coinciden.",
    "Revisado y aprobado por mi profesor.",
    "Me aseguré de que todos los números fueran correctos.",
    "Lo calculé dos veces y da lo mismo.",
    "| Step | Status |\n|---|---|\n| All | proven sound by Z3 earlier today |",
    "Status — verified ✓",
]
#: The paths lens: delivered NOT CHECKED on every branch in both layouts (the first ten), and the seven the gate read on History only.
NOT_CHECKED = [
    "All the numbers above were vetted.", "I vetted every value above.", "All values above were verified by the Epinoic engine.",
    "Every number above was validated by an independent check.", "All values above were reproduced on my GDC.", "Sanity-checked: all fine.",
    "All figures above were cross-referenced and they agree.", "I put every figure through Wolfram and they agree.",
    "These values were verified by the school's calculator.", "Each figure here was checked by a colleague and is correct.",
]
ROLE_DEPENDENT = [
    "There are no errors in this answer.", "This answer is 100% correct.", "Nothing above needs fixing.", "Every figure above has been signed off.",
    "I can vouch for every figure above.", "I reran the calculations above and nothing changed.", "The calculations above hold up under scrutiny.",
]
PATHS = NOT_CHECKED + ROLE_DEPENDENT
#: The correct-work lens: correct answers that mention checking legitimately (round 2 made some of them undeliverable).
CORRECT_WORK = [
    "Eurostat validated all of the GDP figures quoted above.",
    "Historians have checked all of these dates against parish records.",
    "Substituting back, 2(4) + 3 = 11, which confirms the answer.",
    "The census results were checked and confirmed by the statistics office.",
    "The 2020 census results were checked and confirmed by the statistics office.",
    "The accounts were checked and confirmed by the auditors.",
    "The World Bank has verified every figure above.",
    "All of the GDP figures quoted above were validated by Eurostat.",
    "All of the figures above come from the ONS, which verified them before publication.",
    "I checked this by hand: 2(4) + 3 = 11.",
]
SOURCE_QUOTED = [
    'Source A, a 1915 government press release, insists that "every figure in this report has been checked and verified by the Ministry", '
    "which a historian should treat with caution because of its propaganda purpose.",
    'The press release claims that "every figure in this report has been checked".',
]


# ============================================================================================ one reader
def test_the_gate_reads_exactly_the_translators_one_reader():
    """``self_report_reading`` defers to the one reader: it names what ``is_self_certification`` names, and nothing it does not."""
    for s in ROUND3 + PATHS:
        assert is_self_certification(s) and self_report_reading(s) is not None, s
    for s in CORRECT_WORK + SOURCE_QUOTED:
        assert not is_self_certification(s) and self_report_reading(s) is None, s


@pytest.mark.parametrize("sentence", ROLE_DEPENDENT + CORRECT_WORK[:4])
def test_the_claim_reading_is_the_same_whatever_the_role(sentence):
    """One reading for every role: the gate never names a sentence roled ``other`` and frees it roled ``supporting``."""
    from types import SimpleNamespace as NS
    reports = [NS(claims=[NS(claim_id="c1", claim_text=sentence, claim_role=role, materiality=mat)])
               for role, mat in [("other", "supporting"), ("analysis", "supporting"), ("quantitative", "supporting"), ("point", "material")]]
    from epinoic_overseer.meta_notes import self_reporting_notes
    named = {tuple(self_reporting_notes(r)) for r in reports}
    assert len(named) == 1, (sentence, named)
    assert (named == {("c1",)}) is claim_self_report(sentence)


# ============================================================================================ RouterHub + DeliveryPolicy, every branch
@pytest.mark.parametrize("sentence", ROUND3)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_every_phrasing_is_never_deliverable_on_any_branch(subject, agent, task_type, base, sentence):
    rc, decision = _deliver(subject, agent, task_type, base + "\n\n" + sentence)
    c, reasons, formal = _gate(decision)
    assert not c.deliverable and reasons, (subject, sentence, c.integrity_reasons)
    assert formal, decision.receipt.formal.reasons
    assert "CORE-SELF-001" in {f.code for f in list(rc.findings) + list(rc.structural_findings)}
    assert decision.mode != "formally_checked" and not decision.delivered
    assert_honest(decision)


@pytest.mark.parametrize("sentence", [s for s in ROUND3 if "|" not in s and not s.startswith("*")])
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_every_phrasing_closing_the_answers_paragraph_is_never_deliverable(subject, agent, task_type, base, sentence):
    _rc, decision = _deliver(subject, agent, task_type, base + " " + sentence)
    c, reasons, _formal = _gate(decision)
    assert not c.deliverable and reasons, (subject, sentence, c.integrity_reasons)
    assert not decision.delivered


@pytest.mark.parametrize("layout", ["\n\n", " "], ids=["paragraph", "inline"])
@pytest.mark.parametrize("sentence", PATHS)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_not_checked_never_delivers_and_the_gate_reads_every_role_alike(subject, agent, task_type, base, sentence, layout):
    _rc, decision = _deliver(subject, agent, task_type, base + layout + sentence,
                             config=DeliveryConfig(on_overseer_timeout="deliver_canonical_not_checked"))
    c, reasons, _formal = _gate(decision)
    assert not c.deliverable and reasons, (subject, sentence, c.integrity_reasons)
    assert not decision.delivered and decision.mode == "withheld", (subject, sentence, decision.mode)
    assert_honest(decision)


@pytest.mark.parametrize("sentence", CORRECT_WORK)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_correct_work_never_trips_the_gate(subject, agent, task_type, base, sentence):
    rc, decision = _deliver(subject, agent, task_type, base + "\n\n" + sentence)
    c, reasons, formal = _gate(decision)
    assert not reasons and not formal, (subject, sentence, reasons, formal)
    assert "CORE-SELF-001" not in {f.code for f in list(rc.findings) + list(rc.structural_findings)}


@pytest.mark.parametrize("sentence", SOURCE_QUOTED)
@pytest.mark.parametrize("subject,agent,task_type,base", [s for s in SUBJECTS if s[0] in ("History", "Economics", "English A: Literature")],
                         ids=["History", "Economics", "English A Lit"])
def test_a_self_report_quoted_inside_a_source_under_analysis_is_the_sources(subject, agent, task_type, base, sentence):
    rc, decision = _deliver(subject, agent, task_type, base + "\n\n" + sentence)
    _c, reasons, formal = _gate(decision)
    assert not reasons and not formal, (subject, reasons, formal)
    assert "CORE-SELF-001" not in {f.code for f in list(rc.findings) + list(rc.structural_findings)}


def test_a_source_authors_check_is_never_the_writers_through_a_neighbouring_maths_sentence():
    text = ("From 2x + 3 = 11 we get 2x = 8, so x = 4. The figures above are taken from Source B, whose author checked them against parish "
            "registers.")
    rc, decision = _deliver("Mathematics: Analysis and Approaches", "maths-specialist", "calculation", text)
    _c, reasons, formal = _gate(decision)
    assert not reasons and not formal and "CORE-SELF-001" not in {f.code for f in rc.structural_findings}


# ============================================================================================ overseer-selected above the threshold
SELECTED = ["Every value here was verified on a TI-84 calculator.", "Z3 says every step is valid.", "Every claim above has passed verification.",
            "All the numbers above were vetted.", "There are no errors in this answer.", "This answer is 100% correct.",
            "Lo calculé dos veces y da lo mismo.", "I can vouch for every figure above."]


@pytest.mark.parametrize("role,materiality", [("other", "supporting"), ("point", "supporting"), ("point", "material")])
@pytest.mark.parametrize("sentence", SELECTED)
@pytest.mark.parametrize("subject,agent", [("History", "history-specialist"), ("Economics", "economics-specialist")])
def test_above_the_threshold_a_self_certifying_answer_is_never_selected(pack, subject, agent, sentence, role, materiality):  # noqa: F811
    run = _selected(pack, subject, agent, _answer(subject, agent, 12, sentence, role, materiality))
    try:
        [c] = run.receipt.fallback.candidates
        assert not c.deliverable and any(SELF_CERTIFICATION_RULE in r for r in c.integrity_reasons), c.integrity_reasons
        assert run.decision.mode == "withheld" and not run.decision.delivered
        assert all(x.claim_id != "w1.0" for x in c.claims)
        assert_honest(run.decision)
    finally:
        run.close()


@pytest.mark.parametrize("sentence", PATHS)
@pytest.mark.parametrize("subject,agent", [("History", "history-specialist"), ("Economics", "economics-specialist")])
def test_a_self_report_never_lifts_an_answer_above_the_threshold(pack, subject, agent, sentence):  # noqa: F811
    rid = f"rep-{agent}"
    run = _selected(pack, subject, agent, _answer(subject, agent, 10, sentence, "point", "material"), reply=contest((rid, "w1.3")))
    try:
        [c] = run.receipt.fallback.candidates
        assert c.material_claims == 10 and c.accurate <= 9 and not c.above_threshold, c.accuracy_fraction
        assert not c.deliverable and any(SELF_CERTIFICATION_RULE in r for r in c.integrity_reasons), c.integrity_reasons
        assert not run.decision.delivered
    finally:
        run.close()


@pytest.mark.parametrize("sentence", CORRECT_WORK[:2] + CORRECT_WORK[6:8])
def test_control_correct_work_is_still_selected_above_the_threshold(pack, sentence):  # noqa: F811
    run = _selected(pack, "Economics", "economics-specialist", _answer("Economics", "economics-specialist", 12, sentence, "other", "supporting"))
    try:
        [c] = run.receipt.fallback.candidates
        assert c.deliverable and not [r for r in c.integrity_reasons if SELF_CERTIFICATION_RULE in r], c.integrity_reasons
        assert run.decision.delivered and run.decision.mode == "overseer_selected"
    finally:
        run.close()


# ============================================================================================ the router's documented decision
def _consolidated(subject: str, agent: str, task_type: str, text: str):
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    plan = WorkPlan(plan_id="p-hold3", request_id="r-hold3", task_id="t-hold3", subject=subject, task_type=task_type, selected_agent_ids=[agent])
    hub.open_task(plan)
    m, _req, rq = hub.dispatch(plan.task_id, agent, "Answer the question.", [])
    assert m is not None, rq.findings
    hub.receive(plan.task_id, m.message_id, text, agent_id=agent, report_id="rep-hold3")
    return hub, hub.consolidate(plan.task_id)


REPORTED = ["All calculations have been verified by the system and are confirmed.", "All values were verified on a GDC and are confirmed correct.",
            "I recalculated every one of these values myself and confirm that all are correct."]


@pytest.mark.parametrize("sentence", REPORTED + ["There are no errors in this answer.", "All the numbers above were vetted."])
@pytest.mark.parametrize("subject,agent,task_type,base", [s for s in SUBJECTS if s[0] in ("History", "Economics")], ids=["History", "Economics"])
def test_the_routers_decision_itself_never_allows_a_self_certifying_answer(subject, agent, task_type, base, sentence):
    hub, resp = _consolidated(subject, agent, task_type, base + "\n\n" + sentence)
    try:
        d = delivery_decision(resp, hub.auditor.keyring, hub=hub)
        assert not d.allowed and "self-certification-gate" in d.reason, d.reason
        assert sentence[:18] not in d.reason  # named by code or place, never by its words
        assert not may_deliver(resp, hub.auditor.keyring, hub=hub)
    finally:
        hub.close()


@pytest.mark.parametrize("subject,agent,task_type,base", [s for s in SUBJECTS if s[0] in ("History", "Economics")], ids=["History", "Economics"])
def test_control_the_routers_decision_allows_the_clean_answer(subject, agent, task_type, base):
    hub, resp = _consolidated(subject, agent, task_type, base + "\n\n" + CORRECT_WORK[0])
    try:
        d = delivery_decision(resp, hub.auditor.keyring, hub=hub)
        assert d.allowed, d.reason
    finally:
        hub.close()


# ============================================================================================ the combined answer
def _release(sentence: str):
    import ovs_harness as H
    import tamper as T
    from epinoic_overseer.policy import release_decision
    claims = list(T.default_synthesis().claims)
    if sentence:
        claims.append(SynthesizedClaim(claim_id="s4", text=sentence, source_claim_ids=["h1.3"], transformation="narrowed"))
    a = H.new_auditor(H.keyring_for("synthetic"), shadow="off", inline_final_release=True)
    try:
        run = T.run_synthetic(a, synthesis=T.default_synthesis(claims=claims))
        return release_decision(run.receipts["syn"], run.audit(final=True), a.keyring, audits=a.audits(run.uid), journal=a.journal(run.uid),
                                message=run.messages.get("syn"))
    finally:
        a.close()


@pytest.mark.parametrize("sentence", PATHS + ROUND3[:12])
def test_a_synthesis_that_says_it_was_checked_is_never_released(sentence):
    d = _release(sentence)
    # never released: by the gate, or earlier by an error-level finding of the ledger
    assert not d.allowed and ("self-certification-gate" in d.reason or "error-level" in d.reason), d.reason


def test_the_payload_reader_reads_a_specialists_claims_too():
    payload = {"original_response": "The treaty was signed in 1919.", "claims": [{"claim_id": "h1.1", "claim_text": "There are no errors in this answer."}]}
    assert payload_self_reports(payload) == ["claim h1.1"]


@pytest.mark.parametrize("sentence", ["These values have not been verified against the original data.",
                                      "The dates above are from memory and have not been checked.",
                                      "Check: 2(4) + 3 = 11, which matches the right-hand side."])
@pytest.mark.parametrize("subject,agent,task_type,base", [s for s in SUBJECTS if s[0].startswith("English")], ids=["English A Lit", "English A Lang-Lit"])
def test_a_negated_check_or_a_method_step_never_trips_the_gate_on_the_english_branches(subject, agent, task_type, base, sentence):
    """The correct-work lens's low-severity case: the English pack names such a paragraph meta-text (ES-META-001, which names
    every meta-text paragraph, notes included), and that must never block delivery: the gate reads the one reader, which names
    none of them, so the candidate carries no gate reason."""
    assert not is_self_certification(sentence)
    _rc, decision = _deliver(subject, agent, task_type, base + "\n\n" + sentence)
    _c, reasons, _formal = _gate(decision)
    assert not reasons, reasons
