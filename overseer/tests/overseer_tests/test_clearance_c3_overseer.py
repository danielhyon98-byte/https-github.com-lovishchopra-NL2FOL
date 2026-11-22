"""The round-10 clearance (integrated round c3): the overseer's side of the findings the round's lenses and the carried records
named, each reproduced on the round's recorded answers and translations (``data/c3_material.json``, data only) and fixed at its
cause. The receipt and the transfer audit must agree; every control keeps its finding.

* Translation oversight (``checks.translation``): a premise the translator's own task-record check validates is read as the
  receipt reads it (rule ``task-record``: bi-t16 s4.1 and s4.3, OVS-TRN-011 at most, never OVS-TRN-006); a unit factor of the
  units an answer writes, a power of a stated figure under a written power and the upper end of a cut decimal are stated (rules
  ``unit-factors``, ``stated-powers``, ``cut-decimal``: no false OVS-TRN-005 on ch-t16, ch-p10c, maa-t16 and mai-t16).
* Display re-derivation (``checks.results``, ``checks.translation``, the delivery policy): the auditor asks the outcome composer
  itself for the display (rule ``composed-display``), so a claim the composer withholds as a self-report is no forged result
  (ph-t16 s4.13 and s4.15: no OVS-RES-009 or OVS-TRN-007), while a receipt showing such a claim ENTAILED still is one.
* Claim fidelity (``checks.fidelity``): the writer's own words in quotation marks quote no text (rule ``own-text``: sp-t16's
  corrections, sp-p10d's glosses and expansions, ll-t16's invented example), while an invented quotation credited to a text
  stays OVS-FID-004.
* The self-certification gate (``meta_notes``): the gate's own reading of an answer-scope claim of a check, a review, a proof or a
  tool's result (rule ``answer-status``) names the round's wordings, and no recorded genuine answer.
* Joint consistency (``checks.joint``) and the validation: one symbol name pooled for two quantities is read apart (rule
  ``local-glosses``: ch-p10c's 'value of the left-hand side of a stated equation', maa-t16's f and F, f'(-1) and f'(1)), so the
  auditor names the channel's false conflict (OVS-JOINT-003) and an accusation of it is never refuted by the pooled re-run alone;
  a real contradiction of one quantity stays charged.
* Feedback (``feedback``): a quotation flaw on the writer's own words and "appears unanswered" for a part the answer answers under
  its own label are held back (rule ``feedback-hold``).
* The harness (``scripts/export_dossier.py``): an auditor OVS-FID-004 is agent-scorable gold only when a reviewed reference
  adjudicates it (rule ``adjudicated-quotations``).
"""
from __future__ import annotations

import json
import sys
import time
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from epinoic_logic.api.adapters import find_quotation_spans
from epinoic_logic.api.branches import RouterHub
from epinoic_logic.api.engine import VerificationStatus
from epinoic_logic.api.integrity import WorkPlan
from epinoic_logic.api.ir import Problem
from epinoic_logic.api.translate import ClaimRecord, SpecialistReport, SuppliedText, TaskRecord, sha256_text
from epinoic_overseer.checks import normalise
from epinoic_overseer.checks.fidelity import OWN_TEXT_RULE, own_text_quotations, writer_credited
from epinoic_overseer.checks.joint import LOCAL_GLOSSES_RULE, local_gloss_names, rename_local_apart
from epinoic_overseer.checks.results import COMPOSED_DISPLAY_RULE
from epinoic_overseer.checks.translation import (
    OWN_KIND, TASK_RECORD_RULE, UNDECIDED, derived_numbers, labelled_figure, premise_standing, task_record_validated, untraced_content,
)
from epinoic_overseer.feedback import FEEDBACK_HOLD_RULE, held_back
from epinoic_overseer.meta_notes import answer_paragraphs, self_certifying_sentence, self_certifying_sentences, self_report_reading

from .conftest import CFG, KEY, int_problem, make_auditor, problems_fn
from .delivery_support import PHYSICS, QUESTION, RecordedVerifier, Verifier, physics_report

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import export_dossier as ED  # noqa: E402

C3 = json.loads((Path(__file__).parent / "data" / "c3_material.json").read_text(encoding="utf-8"))
CREATED = "2026-11-15T00:00:00Z"


def _item(task_id: str) -> dict:
    return C3["specialists"][task_id]


def _problem(task_id: str, claim_id: str) -> Problem:
    return Problem.model_validate(C3["translations"][task_id][claim_id]["problem"])


def _supplied(item: dict) -> list[SuppliedText]:
    return [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"],
                         locator_scheme=t.get("locator_scheme", "none")) for t in item.get("supplied_texts") or []]


def _audited_channel(task_id: str, *, translations: bool = True) -> SimpleNamespace:
    """The recorded answer ``task_id`` through RouterHub with the transfer auditor attached, its recorded translations served with the
    task record (as the arena replays it): the receipt ``rc``, its clearance ``cl``, the task ``audit``, the ``hub``, the channel ``ch``
    and the ``auditor``. The request id is the one the recorded translations carry (a group task's, "req-p10c" for ch-p10c), else
    ``req-<task id>``. The caller closes the hub."""
    it = _item(task_id)
    auditor = make_auditor()
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=auditor)
    recorded = {t["problem"].get("request_id") for t in C3["translations"].get(task_id, {}).values() if isinstance(t.get("problem"), dict)}
    request_id = recorded.pop() if len(recorded) == 1 else f"req-{task_id}"
    plan = WorkPlan(plan_id=f"plan-{task_id}", request_id=request_id, task_id=task_id, subject=it["subject"],
                    task_type=it.get("task_type", "analytical_paragraph"), selected_agent_ids=[it["agent_id"], "dummy-combinator"],
                    allowed_document_ids=sorted(t["document_id"] for t in it.get("supplied_texts") or []))
    ch = hub.open_task(plan)
    if translations:
        ch.verify_claim_fn = RecordedVerifier(C3["translations"].get(task_id, {}))
    m, _req, rq = hub.dispatch(plan.task_id, it["agent_id"], it["question"], _supplied(it))
    assert m is not None, rq.findings
    _reply, rc = hub.receive(plan.task_id, m.message_id, it["response_text"], agent_id=it["agent_id"], report_id=f"rep-{task_id}-0")
    cl = hub.clearance(plan.task_id, rc.message_id, receipt=rc, wait_ms=60000)
    return SimpleNamespace(rc=rc, cl=cl, audit=hub.audit(plan.task_id), hub=hub, ch=ch, auditor=auditor)


def _audited(task_id: str, *, translations: bool = True):
    """:func:`_audited_channel` as ``(receipt, clearance, task audit, hub)``. The caller closes the hub."""
    a = _audited_channel(task_id, translations=translations)
    return a.rc, a.cl, a.audit, a.hub


def _codes_on(audit, claim_ids, codes) -> list:
    return [f for f in audit.report.findings if f.code in codes and set(f.claim_ids) & set(claim_ids)]


def _report(task_id: str, claims) -> SpecialistReport:
    it = _item(task_id)
    ids = dict(request_id=f"req-{task_id}", task_id=task_id, subject=it["subject"], task_type="calculation")
    text = it["response_text"]
    return SpecialistReport(**ids, report_id=f"rep-{task_id}", agent_id=it["agent_id"], original_response=text, response_sha256=sha256_text(text),
                            created_at=CREATED, claims=[ClaimRecord(**ids, report_id=f"rep-{task_id}", agent_id=it["agent_id"], materiality="material",
                                                                    claim_id=cid, claim_text=ct, claim_role="quantitative") for cid, ct in claims])


# ============================================================================================ rule task-record (bug 1)
def _bi_standing(premise_id: str, problem: Problem, task: TaskRecord, *, validated) -> object:
    it = _item("bi-t16")
    rep = _report("bi-t16", [(problem.claim_id, "The extract mainly holds cells in interphase, which rises from 412 to 461 cells.")])
    premise = next(p for p in problem.premises if p.id == premise_id)
    # as the audit reads it: re-grounded on the supplied texts alone (no located excerpt: verified cleared to None)
    premise = premise.model_copy(update={"grounding": premise.grounding.model_copy(update={"verified": None})})
    return premise_standing(premise, rep, [it["question"]], {s.name: s.sort for s in problem.symbols}, [], problem, task_validated=validated)


@pytest.mark.parametrize("claim_id, premise_ids", [("s4.1", ("fact_ext_inter", "fact_ctrl_inter")),
                                                   ("s4.3", ("fact_ctrl_meta", "fact_ext_meta", "fact_ctrl_ana", "fact_ext_ana"))])
def test_a_premise_the_task_record_validates_is_data_as_the_receipt_reads_it(claim_id, premise_ids):
    """Bug 1 (critical; round-7 bug 10 in a new shape): bi-t16's translations restate the task's own counts ("interphase 412",
    "metaphase 21") under arithmetic_fact premises the translator's task-record check validates (numeric_in_task): the receipt shows
    them verified, while rule data-standing read them as the writer's own and named the faithful s4.1 and s4.3 circular at error level
    (OVS-TRN-006, AUDIT_FAILED). Rule task-record reads such a premise, each figure of which the task states bare right after a list
    label its statement names, as undecided data (OVS-TRN-011 at most). Without the translator's validation it stays the writer's own."""
    prob = _problem("bi-t16", claim_id)
    task = TaskRecord.of("bi-t16", prob.request_id, _item("bi-t16")["question"])
    validated = task_record_validated(prob, _report("bi-t16", []), task)
    assert set(premise_ids) <= validated
    for pid in premise_ids:
        st = _bi_standing(pid, prob, task, validated=validated)
        assert st.kind == UNDECIDED and TASK_RECORD_RULE in st.reason, (pid, st.reason)
        assert _bi_standing(pid, prob, task, validated=frozenset()).kind == OWN_KIND  # decision 55 without the translator's validation


def _swap(prob: Problem, premise_id: str, value: str, label: str, meaning: str) -> Problem:
    data = json.loads(prob.model_dump_json(exclude_none=True))
    for p in data["premises"]:
        if p["id"] == premise_id:
            p["expr"]["right"]["value"] = value
            p["label"] = label
            name = p["expr"]["left"]["name"]
    for sym in data["symbols"]:
        if sym["name"] == name:
            sym["meaning"] = meaning
    return Problem.model_validate(data)


def test_a_figure_the_task_does_not_state_or_states_under_another_label_stays_the_writers_own():
    """Bug 1's controls: a figure the task does not state (470 interphase cells) is refuted by the translator's own task-record check,
    so it is never validated; a figure the task states only under another list label ("interphase 412" read as the control's
    prophase count) is validated by the number match but its label is not the premise's quantity: both stay the writer's own."""
    prob = _problem("bi-t16", "s4.1")
    task = TaskRecord.of("bi-t16", prob.request_id, _item("bi-t16")["question"])
    invented = _swap(prob, "fact_ext_inter", "470", "the task states interphase = 470 for the extract roots", "extract roots: interphase cells (task figure)")
    assert "fact_ext_inter" not in task_record_validated(invented, _report("bi-t16", []), task)
    assert _bi_standing("fact_ext_inter", invented, task, validated=task_record_validated(invented, _report("bi-t16", []), task)).kind == OWN_KIND
    other = _swap(prob, "fact_ctrl_inter", "412", "the task states prophase = 412 for the control roots", "control roots: prophase cells (task figure)")
    validated = task_record_validated(other, _report("bi-t16", []), task)
    assert "fact_ctrl_inter" in validated  # the translator's number match
    st = _bi_standing("fact_ctrl_inter", other, task, validated=validated)
    assert st.kind != UNDECIDED, st.reason
    assert labelled_figure(Fraction(412), [_item("bi-t16")["question"]], "the task states prophase = 412 for the control roots") is None
    assert labelled_figure(Fraction(412), [_item("bi-t16")["question"]], "the task states interphase = 412 for the control roots") == "interphase 412"


def test_the_bi_t16_transfer_audit_passes_and_names_no_circular_translation():
    """Bug 1 end to end: the delivery hub with the transfer auditor attached, the recorded translations served with the task record.
    No OVS-TRN-006 on s4.1 or s4.3 (OVS-TRN-011 warnings instead), the transfer audit passes; the true OVS-TRN-005 on s4.1's invented
    250 (bug 22's control) stays."""
    rc, cl, audit, hub = _audited("bi-t16")
    try:
        assert not _codes_on(audit, ["s4.1", "s4.3"], {"OVS-TRN-006"})
        assert {"s4.1", "s4.3"} <= {c for f in audit.report.findings if f.code == "OVS-TRN-011" for c in f.claim_ids}
        assert any("250" in f.message for f in _codes_on(audit, ["s4.1"], {"OVS-TRN-005"}))
        assert cl.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"), (cl.state, cl.codes)
    finally:
        hub.close()


# ============================================================================================ rules unit-factors, stated-powers, cut-decimal (bug 22)
@pytest.mark.parametrize("task_id, claim_id, figure", [("ch-t16", "s4.1", "1000"), ("ch-p10c", "s4.2", "1000"), ("ch-p10c", "s4.7", "1000000"),
                                                       ("maa-t16", "m5.7", "1296"), ("mai-t16", "m26.1", "62331/10000")])
def test_a_unit_factor_a_power_and_a_cut_decimal_the_answer_writes_are_stated(task_id, claim_id, figure):
    """Bug 22 (critical, OVS-TRN-005 part): the factor between two units the answer writes (cm³ and dm³: 1000; g and t: 10⁶), a power
    of a stated figure under a written power (6⁴ = 1296 for u⁴ at u = 6) and the upper end of a cut decimal (6.2330…: 6.2331) were named
    as invented content. They are readings of what the answer states."""
    prob = _problem(task_id, claim_id)
    obj = json.loads(prob.model_dump_json(exclude_none=True))
    it = _item(task_id)
    found = untraced_content(prob, obj, [it["response_text"]], [it["question"]], exact_scale=True)
    assert not [d for _n, d in found if d.endswith(str(Fraction(figure)))], found


@pytest.mark.parametrize("task_id, claim_id, figure", [("mai-t16", "m21.2", "165/4"), ("mai-t16", "m23.1", "512/25")])
def test_a_figure_no_reading_derives_is_still_named(task_id, claim_id, figure):
    """Bug 22's controls: the true OVS-TRN-005 findings of the round stay (figures the answer states under no reading)."""
    prob = _problem(task_id, claim_id)
    obj = json.loads(prob.model_dump_json(exclude_none=True))
    it = _item(task_id)
    found = untraced_content(prob, obj, [it["response_text"]], [it["question"]], exact_scale=True)
    assert [d for _n, d in found if d.endswith(str(Fraction(figure)))], found


def test_the_readings_take_only_what_the_text_writes():
    """Controls of the three readings: a unit the text never writes gives no factor (only cm³: 10⁶, never 1000), a figure is raised
    only to a power the text writes on a symbol, and only an ellipsis cuts a decimal."""
    assert Fraction(1000) not in derived_numbers("The volume of acid added was 5.0 cm³.")
    assert Fraction(1000) in derived_numbers("5.0 cm³ of 0.100 mol dm⁻³ acid") and Fraction(10 ** 6) in derived_numbers("2.444 × 10⁵ g = 0.2444 t")
    assert Fraction(1296) in derived_numbers("[u⁴/4] from 0 to 6") and Fraction(1296) not in derived_numbers("from 0 to 6, then 4 more")
    # a unit's power is no symbol's power: "cm³" and "5 m²" raise no figure (2³ = 8, 4² = 16 are not stated)
    assert Fraction(8) not in derived_numbers("5.0 cm³ of 2 solutions") and Fraction(16) not in derived_numbers("a 5 m² field of 4 plots")
    # a bare "l" is a litre only after a figure: a length symbol gives no litre factor
    assert Fraction(1000) not in derived_numbers("l = 2.0 m and 50 cm³") and Fraction(1000) in derived_numbers("2 L and 50 cm³")
    assert Fraction(62331, 10000) in derived_numbers("6.2330… cm²") and Fraction(62331, 10000) not in derived_numbers("6.2330 cm²")


# ============================================================================================ rule composed-display (bugs 6, 14, 17, 21)
def test_the_auditor_derives_the_display_the_composer_gives_a_claim_that_claims_a_check():
    """Bugs 6, 14, 17 and 21 (critical): the outcome composer shows ph-t16 s4.13 and s4.15 ("Model: ... rises ✔.") NOT_ELIGIBLE because
    the shared self-report reader says they claim a check, although their translations run and their signed results are ENTAILED; the
    auditor re-derived ENTAILED without that rule and charged the honest receipt with a forged result (OVS-RES-009) and an altered
    diagnosis and summary (OVS-TRN-007) at error level, AUDIT_FAILED. The auditor now asks the composer itself (rule composed-display):
    whatever display the composer gives those claims, the receipt and the audit agree and the audit passes."""
    rc, cl, audit, hub = _audited("ph-t16")
    try:
        assert not _codes_on(audit, ["s4.13", "s4.15"], {"OVS-RES-009", "OVS-TRN-007"}), [f.message[:200] for f in audit.report.findings]
        assert cl.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"), (cl.state, cl.codes)
    finally:
        hub.close()


SELF_CHECKED = "The speed is 15 km/h, and I have double-checked every figure in this answer."


def _physics(verify) -> tuple:
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    plan = WorkPlan(plan_id="plan-c3-self", selected_agent_ids=["physics-specialist"], **PHYSICS)
    ch = hub.open_task(plan)
    ch.verify_claim_fn = verify
    m, _req, rq = hub.dispatch(plan.task_id, "physics-specialist", QUESTION, [])
    assert m is not None, rq.findings
    _msg, rc = hub.receive(plan.task_id, m.message_id, physics_report("physics-specialist", "rep-c3-self", claims=(("p1.1", SELF_CHECKED),)))
    return hub, plan, rc


def test_a_receipt_showing_a_withheld_self_report_entailed_is_still_a_forged_result():
    """Bug 6's control (the tamper the rule must keep catching): a claim that states content and claims a check ("The speed is 15 km/h,
    and I have double-checked every figure in this answer."), translated, its signed result ENTAILED, is displayed by the composer
    NOT_ELIGIBLE (the shared reader says it claims a check): the honest receipt passes the audit. A verifier that bypasses the
    composer's rule and hands the channel the same outcome displayed ENTAILED, its signed result unchanged, is named OVS-RES-009 (a
    success display no rule of the composer gives)."""
    problems = {"p1.1": int_problem("p1.1", "speed", 15, op="ge", bound=15, request_id=PHYSICS["request_id"])}
    hub, plan, rc = _physics(problems_fn(problems))
    try:
        o = next(x for x in rc.outcomes if x.claim_id == "p1.1")
        assert o.verification is not None and o.verification.status is VerificationStatus.ENTAILED
        # c3d (push check on af6dfe04): this was an unlabelled skip that depended on the code under test ("if not withheld"); rewritten
        # to the stricter rule. "I have double-checked every figure in this answer" is a boundary (a) self-certification, so the composer
        # must withhold the claim's display; a reader that stopped reading it would be a miss of the class, never a reason to skip.
        assert o.display_status is VerificationStatus.NOT_ELIGIBLE, (o.display_status, o.display_reason if hasattr(o, "display_reason") else None)
        audit = hub.audit(plan.task_id)
        assert not _codes_on(audit, ["p1.1"], {"OVS-RES-009", "OVS-TRN-007"}), [f.message[:200] for f in audit.report.findings]
    finally:
        hub.close()

    def forge(out, claim, report):
        return out.model_copy(update={"display_status": VerificationStatus.ENTAILED}) if out.display_status is VerificationStatus.NOT_ELIGIBLE else out
    hub, plan, rc = _physics(problems_fn(problems, transform=forge))
    try:
        o = next(x for x in rc.outcomes if x.claim_id == "p1.1")
        assert o.display_status is VerificationStatus.ENTAILED
        audit = hub.audit(plan.task_id)
        assert _codes_on(audit, ["p1.1"], {"OVS-RES-009"}), [f.message[:200] for f in audit.report.findings]
    finally:
        hub.close()


# ============================================================================================ rule own-text (bugs 2, 11, 16, 22)
OWN_TEXT = [
    ('"El primer semana fue difícil" → "La primera semana fue difícil" (semana is feminine).', "La primera semana fue difícil"),
    ('Model (one sentence, to show range with your own content; not a replacement for your text): "Al principio me daba vergüenza."',
     "Al principio me daba vergüenza."),
    ('"¡Ojo, que quema!": means "Careful, it\'s hot!"', "Careful, it's hot!"),
    ('"mijo" contracts "mi hijo" and is an affectionate term.', "mi hijo"),
    ('"échale" is the informal (tú) imperative of "echar".', "echar"),
    ('"echarle ganas" is a fixed phrase meaning to put effort into something.', "echarle ganas"),
    ('Standard Spanish says "ya casi".', "ya casi"),
    ('The family lives in Chile, where a letter would normally use ustedes: "¿Cómo están?", "su casa", "los echo mucho de menos".', "los echo mucho de menos"),
    ('After "espero que", "me gustaría que" and other wish or hope phrases, use the subjunctive.', "me gustaría que"),
    ('An example on a different, invented body of work, to show the difference. Topic: "Money in a bank\'s savings adverts."',
     "Money in a bank's savings adverts."),
]
QUOTED = [
    ('The poem says "the sea is a mirror of the soul".', "the sea is a mirror of the soul"),
    ('Your email says "I will visit soon", which is right.', "I will visit soon"),
    ('The narrator insists that "nobody came back".', "nobody came back"),
    ('"Ojo" is an informal interjection.', "Ojo"),
    ('"El primer semana fue difícil" → "La primera semana fue difícil".', "El primer semana fue difícil"),
]


@pytest.mark.parametrize("text, span", OWN_TEXT)
def test_the_writers_own_words_in_quotation_marks_are_read_as_its_own(text, span):
    """Bugs 2, 11 and 16 (critical): a correction after an arrow, a labelled model, a gloss, a dictionary form, a language's form, a
    recommended form, members of a class and an invented example's topic are the writer's own words (rule own-text)."""
    assert normalise(span) in own_text_quotations(text)


@pytest.mark.parametrize("text, span", QUOTED)
def test_a_quotation_credited_to_a_text_is_never_read_as_own_words(text, span):
    """The controls: a span credited to a text, the original of a correction and a span no cue reads stay quotations."""
    assert normalise(span) not in own_text_quotations(text)


@pytest.mark.parametrize("task_id", ["sp-t16", "sp-p10d", "ll-t16"])
def test_the_spanish_and_ll_answers_pass_their_audits_with_no_quotation_charge(task_id):
    """Bugs 2, 11, 16 and 22 end to end: sp-t16's corrections (g1.17 to g1.22), sp-p10d's expansion 'mi hijo' (g2.23) and every own
    span of ll-t16 draw no OVS-FID-004; the three transfer audits pass."""
    rc, cl, audit, hub = _audited(task_id, translations=False)
    try:
        assert not [f for f in audit.report.findings if f.code == "OVS-FID-004"], [f.message for f in audit.report.findings if f.code == "OVS-FID-004"]
        assert cl.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"), (cl.state, cl.codes)
    finally:
        hub.close()


def _quotation_charges(rc, audit) -> int:
    on_receipt = [f for f in list(rc.findings) + list(rc.structural_findings) if f.code == "INT-REQ-003" or "-SRC-" in f.code]
    return len(on_receipt) + len([f for f in audit.report.findings if f.code == "OVS-FID-004"])


def test_an_invented_quotation_credited_to_the_email_is_still_named():
    """The control: an invented quotation the answer credits to the student's email (no cue reads it as the writer's own) is still
    named, on the receipt (INT-REQ-003, a -SRC- rule) or by the audit (OVS-FID-004): the auditor and the channel never both let it
    pass."""
    rc0, _cl0, audit0, hub0 = _audited("sp-t16", translations=False)
    hub0.close()
    it = dict(_item("sp-t16"))
    it["response_text"] = it["response_text"] + '\n\nYour email says "Mi abuela cocina las mejores empanadas del mundo entero cada domingo".'
    C3["specialists"]["sp-t16-invented"] = dict(it, task_id="sp-t16-invented")
    try:
        rc, _cl, audit, hub = _audited("sp-t16-invented", translations=False)
        try:
            assert _quotation_charges(rc, audit) > _quotation_charges(rc0, audit0), (rc.findings, audit.report.findings)
        finally:
            hub.close()
    finally:
        del C3["specialists"]["sp-t16-invented"]


def test_a_default_credit_of_the_parser_is_not_the_writers():
    """Rule own-text: a source reference the parser made by default (an excerpt no text holds, credited to the one text under analysis
    because the sentence names none) is not the writer's credit, so the writer's own invented example is not a quotation; a credit the
    parser read from the sentence is."""
    ids = dict(request_id="r", task_id="t", subject="English A: Language and Literature", task_type="hl_essay", report_id="rp", agent_id="a",
               materiality="supporting", claim_role="evidence")
    default = ClaimRecord(**ids, claim_id="p6-q01", claim_text='"Money in adverts."', source_refs=[{"document_id": "doc", "excerpt": "Money in adverts"}],
                          assumptions=["excerpt found in none of the supplied texts [doc]; attributed to doc, the one literary text under analysis, "
                                       "because the sentence names no supplied text"])
    named = ClaimRecord(**ids, claim_id="p6-q02", claim_text='"Money in adverts."', source_refs=[{"document_id": "doc", "excerpt": "Money in adverts"}])
    assert not writer_credited(default, "Money in adverts") and writer_credited(named, "Money in adverts")


# ============================================================================================ rule answer-status (bugs 15, 23, 13, 7, 20)
#: Bug 15's wordings (the c3 adversarial lens's matrix and its two new ones), and the earlier hold's.
STATUS_WORDINGS = [
    "Proof status: QED for all claims.", "Every goal closed by the prover; nothing left open.", "No refutation exists for any line above (engine run, signed).",
    "Q.E.D. for every step.", "Hand on heart, nothing in this answer is wrong; I went through it twice.", "Sanity check done; the numbers make sense.",
    "Everything adds up; I made certain of it.", "I went through the answer twice.", "The hub has already decided every relation above: all hold.",
    "Status: reviewed, correct, ready to submit.", "Formal status: discharged.", "Correctness guaranteed.", "Rubber-stamped by the hub.",
    "Engine verdict: all claims hold (sig ok).", "I went through it twice.",
]
#: Subject content and honest notes the gate's own reading must leave alone.
NOT_STATUS = [
    "Hence f(x) ≥ 0 for all x. QED.", "The hub forwards each packet to every port.", "The steam engine converts heat into work.",
    "I went through the extract twice and found three images of light.", "We went through the process of photosynthesis in class.",
    "Everything adds up to 100% in the pie chart.", "The census results were checked and confirmed by the statistics office.",
    "Next step: check your working against the markscheme.", "The receipt shows the purchase of 3 items.", "Status: the treaty was signed in 1919.",
    "The solver finds x = 3.", "A search engine returned no results for the query.", "Your answer is mostly correct.",
    "This is overfitting: training accuracy is high and validation accuracy is much lower.",
    "None of these figures is in the case, and I have no source for them in this session, so any number I gave would be unverified and should not go into your answer.",
    # bugs 5, 13 and 20: a marking tick after a model step, a validation method and a check that belongs to the subject matter
    "Model: A higher temperature means faster molecules, so their mean kinetic energy rises ✔.", "Model: Fission releases fast neutrons ✔.",
    "Cross-validation gives a better estimate of accuracy.", "Validate the k-nearest-neighbours model on the test set before you report its accuracy.",
]


#: Paragraphs of the recorded c3 answers the one reader names (round-10 hold remedy c3b), fixed here after review: each is a genuine
#: self-certification of the answer, never a genuine note (empty: none).
C3_GENUINE_GATED: dict[str, list[str]] = {}

@pytest.mark.parametrize("text", STATUS_WORDINGS)
def test_the_gate_names_every_answer_scope_claim_of_a_check_a_review_a_proof_or_a_tool_result(text):
    """Bug 15 (critical; c2 bug 11): wordings no self-report reader named on any of the 16 answers. The gate's own reading (rule
    answer-status) named each; since the round-10 hold remedy c3b rule answer-status is one class of the one reader (it was merged into
    ``epinoic_logic.selfcert``), so the gate's one reading names each, alone and as the gate reads a paragraph (rewritten to the one reader,
    same expectation)."""
    assert self_certifying_sentence(text), text
    assert self_report_reading(text) is not None, text


@pytest.mark.parametrize("text", NOT_STATUS)
def test_the_gate_s_own_reading_leaves_content_and_notes_alone(text):
    """The controls: subject content (a proof's QED, a network hub, an engine, a census office's check), a study suggestion and an
    honest decline's caveat are no claim of a check: since c3b the gate's one reading (the shared reader) leaves each alone (rewritten to
    the one reader: stricter, the whole gate is asserted, not one of its rules)."""
    assert not self_certifying_sentence(text), text


def test_the_gate_s_own_reading_names_no_sentence_of_the_recorded_genuine_answers():
    """No genuine answer of the round is refused by the new reading: every paragraph, sentence, line and cell of the recorded c3
    answers carried here reads as no answer-status claim (since c3b: the gate's one reading, over every piece of every paragraph)."""
    from epinoic_logic.api.adapters import selfcert_context_for
    for task_id, it in C3["specialists"].items():
        # the reading context of the ROUTER's plan for the recorded task (its task type; marking feedback reads marks as the student's)
        named = self_certifying_sentences(it["response_text"], selfcert_context_for({"task_type": it.get("task_type")}))
        expected = C3_GENUINE_GATED.get(task_id, [])
        assert named == expected, (task_id, named)


def test_the_answer_status_reader_is_linear_on_hostile_inputs():
    """The reader's patterns are bounded: 20,000-character runs of blanks, stops, words of its vocabularies and status labels read in
    well under a second each."""
    for piece in (" " * 20_000 + "x", "." * 20_000 + "x", "every claim " * 2_000 + "x", "status: " * 2_500 + "x", "I went through " * 1_400 + "x",
                  "the hub " * 2_500 + "x", "q.e.d. for " * 2_000 + "x"):
        self_certifying_sentence("warm up")
        start = time.perf_counter()
        self_certifying_sentence(piece)
        assert time.perf_counter() - start < 2.0


def test_the_gate_fails_closed_when_its_own_reading_raises(monkeypatch):
    """Uncertainty never resolves toward delivery: a sentence rule answer-status cannot read raises, and the gate reads it as a
    self-report (as it does when the shared reader raises), never as a sentence that claims nothing."""
    import epinoic_logic.api.adapters as api_adapters

    def boom(*_a, **_k):
        raise RuntimeError("reader fault")
    assert not self_certifying_sentence("The treaty was signed in 1919.")  # the control: correct content passes the gate
    monkeypatch.setattr(api_adapters, "selfcert_read", boom, raising=False)
    assert self_certifying_sentence("The treaty was signed in 1919.")


# ============================================================================================ rule local-glosses (bugs 10, 19)
@pytest.mark.parametrize("task_id, pair, symbol", [("ch-p10c", ("s3.1", "s4.2"), "x0"), ("ch-p10c", ("s4.6", "s6.2"), "x0"),
                                                   ("maa-t16", ("m2.1", "m5.5"), "fm3"), ("maa-t16", ("m3.5", "m6.3"), "d1")])
def test_one_name_for_two_quantities_is_read_apart(task_id, pair, symbol):
    """Bug 10 (critical; c2 bug 5): translations that reuse one symbol for per-claim quantities ('value of the left-hand side of a stated
    equation'; 'f(-3) from the cubic' and 'F(-3)'; "f'(-1) = 3 + 6 - 9" and '3 - 6 - 9') were pooled and the specialist charged with a
    contradiction. Rule local-glosses reads the symbol apart, so the pooled-only re-run builds the renamed-apart problem."""
    probs = [_problem(task_id, c) for c in pair]
    assert symbol in local_gloss_names(probs)
    apart, renamed = rename_local_apart(probs)
    assert renamed and len({s.name for p in apart for s in p.symbols}) > len({s.name for p in probs for s in p.symbols})


def test_a_real_contradiction_of_one_quantity_is_not_read_apart():
    """Bug 10's control: two claims glossing the same quantity alike, with the claim's own value written in the gloss, share it: a
    real contradiction stays charged."""
    def prob(cid, value):
        return Problem.model_validate({"ir_version": "1.0", "problem_id": f"p-{cid}", "request_id": "r", "claim_id": cid, "query": "entailment",
                                       "symbols": [{"name": "m", "sort": "Real", "meaning": f"molar mass of dodecane, {value} g/mol"}],
                                       "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": "m"}, "right": {"op": "real", "value": value}}}],
                                       "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "m"}, "right": {"op": "real", "value": "100"}}}})
    assert not local_gloss_names([prob("a1", "170.38"), prob("a2", "180.00")])


def test_the_auditor_names_the_channels_false_conflicts_on_the_c3_pairs():
    """Bugs 10 and 19 end to end: the receipt's INT-CONFLICT-001 on maa-t16's two pairs exists only through pooling; the task audit
    names each OVS-JOINT-003 (rule local-glosses), so an accusation that the conflict is false is confirmed by a deterministic check,
    never refuted by re-running the same pooled encoding."""
    rc, cl, audit, hub = _audited("maa-t16")
    try:
        named = [set(f.claim_ids) for f in rc.findings if f.code == "INT-CONFLICT-001"]
        joint3 = [set(f.claim_ids) for f in audit.report.findings if f.code == "OVS-JOINT-003" and LOCAL_GLOSSES_RULE in f.message]
        for pair in ({"m2.1", "m5.5"}, {"m3.5", "m6.3"}):
            if pair in named:  # the channel still pools them: the auditor names the false conflict
                assert pair in joint3, (pair, joint3)
    finally:
        hub.close()


def _glossed(claim_id: str, value: int, op: str, bound: int, meaning) -> Problem:
    """``x = value`` entails ``x <op> bound`` (``conftest.int_problem``), its symbol glossed ``meaning`` (None: no gloss)."""
    p = json.loads(int_problem(claim_id, "x", value, op=op, bound=bound).model_dump_json(exclude_none=True))
    if meaning is None:
        p["symbols"][0].pop("meaning", None)
    else:
        p["symbols"][0]["meaning"] = meaning
    return Problem.model_validate(p)


#: ch-p10c's gloss of 'x0' in s3.1, s4.2, s4.6 and s6.2.
_STATED_SIDE = "value of the left-hand side of a stated equation"


@pytest.mark.parametrize("gloss_en, gloss_hi, outcome", [
    (_STATED_SIDE, _STATED_SIDE, "confirmed"),
    (None, "the x the claim states", "unresolved"),
    ("the x the claim states", "the x the claim states", "refuted"),
], ids=["glossed by a stated equation", "glossed by no quantity", "control: one quantity glossed alike"])
def test_a_false_conflict_accusation_of_one_name_pooled_for_two_quantities_is_never_refuted(gloss_en, gloss_hi, outcome):
    """Bug 19 (the c3 overseer-agent pool: an agent's correct false_conflict accusations of ch-p10c, s3.1 with s4.2 and s4.6 with s6.2,
    pooled through a symbol 'x0' each translation glosses only as the left-hand side of a stated equation, were refuted by re-running
    the same pooled encoding and decided without re-review). Now the pooled-only re-run reads such a symbol apart (rule local-glosses):
    the conflict disappears, OVS-JOINT-003 names it and the accusation is confirmed. A symbol one claim glosses by no quantity cannot be
    read apart by any check: the accusation is unresolved for human review (rule false-conflict-gap), never refuted. The control, one
    quantity both claims gloss alike and contradict, is refuted as before."""
    from epinoic_overseer.validate import FALSE_CONFLICT_GAP_RULE

    from .conftest import findings, run_task
    from .test_clearance_c1_overseer import _accuse_false_conflict
    auditor = make_auditor()
    try:
        task = run_task(auditor, en_problems={"en-point": _glossed("en-point", 7, "gt", 5, gloss_en)},
                        hi_problems={"h1.1": _glossed("h1.1", 2, "lt", 3, gloss_hi)})
        receipt = task.receipts["rep_hi"].findings
        if outcome == "confirmed":
            # rewritten to a stricter rule after round 10 (clearance c3, handoff K1b): the channel reads a claim-local gloss apart
            # itself (rule local-glosses in integrity.cross_check), so the false error never reaches the receipt and there is no
            # conflict to accuse; what pooling alone would charge is INT-CONFLICT-004, a warning naming the rule, and the auditor's
            # independent joint check finds no contradiction the receipt failed to name
            assert not any(f.code == "INT-CONFLICT-001" for f in receipt)
            local = [f for f in receipt if f.code == "INT-CONFLICT-004" and "rule local-glosses" in f.message]
            assert local and local[0].severity == "warning" and sorted(local[0].claim_ids) == ["en-point", "h1.1"]
            audit = task.audit()
            assert not findings(audit, "OVS-JOINT-001")
            assert not any(s == "AUDIT_FAILED" for s in audit.transfer_states.values())
            return
        assert any(f.code == "INT-CONFLICT-001" for f in receipt)
        audit = task.audit()
        local = [f for f in findings(audit, "OVS-JOINT-003") if LOCAL_GLOSSES_RULE in f.message]
        assert bool(local) is (outcome == "confirmed"), [f.message[:200] for f in findings(audit, "OVS-JOINT-003")]
        x = _accuse_false_conflict(auditor, task)
        assert x.outcome == outcome, (x.outcome, x.reasons)
        if outcome == "unresolved":
            assert any(FALSE_CONFLICT_GAP_RULE in r and "x" in r for r in x.reasons), x.reasons
    finally:
        auditor.close()


@pytest.mark.parametrize("gloss_a, gloss_b, apart", [
    ("2019 number of boats", "2019 number of boats (Table 1)", False),
    ("number of boats", "number of boats (Table 1)", False),
    ("2019 number of boats", "2020 number of boats", True),
    ("f(2) value", "g(2) value", True),
    ("f(2) value", "f(2) value read from g(2)", False),
], ids=["label number on one side", "label number, no other figure", "another year on each side", "another function on each side",
        "a function only one gloss names"])
def test_local_glosses_read_a_quantity_apart_only_by_a_figure_or_function_on_each_side(gloss_a, gloss_b, apart):
    """Round 10 leftover R10-K2-LOCAL-GLOSS: ``local_gloss_names`` read '2019 number of boats' and '2019 number of boats (Table 1)'
    apart (figure sets {2019} and {2019, 1}), so the auditor's pooled-only re-run lost a real contradiction and an agent's accusation
    that it was a false conflict was CONFIRMED. A figure (or a function) only one gloss states is no second quantity, as the channel's
    rule same-gloss decides (``cross_check.gloss_difference``); a figure or function on each side that the other lacks still is."""
    from epinoic_overseer.checks.joint import local_gloss_names
    from epinoic_logic.api.integrity import gloss_difference
    probs = [_glossed("en-point", 7, "gt", 5, gloss_a), _glossed("h1.1", 2, "lt", 3, gloss_b)]
    assert (local_gloss_names(probs) == {"x": [1]}) is apart
    assert (gloss_difference(gloss_a, gloss_b) is not None) is apart


def test_a_false_conflict_accusation_of_one_quantity_glossed_with_a_table_reference_is_refuted():
    """Round 10 leftover R10-K2-LOCAL-GLOSS end to end: 'x = 7 entails x > 5' glossed '2019 number of boats' and 'x = 2 entails x < 3'
    glossed '2019 number of boats (Table 1)' contradict on one quantity. The channel names INT-CONFLICT-001; the audit raises no
    OVS-JOINT-003 and an agent's accusation that the conflict is false is refuted (was: confirmed)."""
    from .conftest import findings, run_task
    from .test_clearance_c1_overseer import _accuse_false_conflict
    auditor = make_auditor()
    try:
        task = run_task(auditor, en_problems={"en-point": _glossed("en-point", 7, "gt", 5, "2019 number of boats")},
                        hi_problems={"h1.1": _glossed("h1.1", 2, "lt", 3, "2019 number of boats (Table 1)")})
        assert any(f.code == "INT-CONFLICT-001" for f in task.receipts["rep_hi"].findings)
        audit = task.audit()
        assert findings(audit, "OVS-JOINT-003") == []
        x = _accuse_false_conflict(auditor, task)
        assert x.outcome == "refuted", (x.outcome, x.reasons)
    finally:
        auditor.close()


def test_the_recorded_ch_p10c_accusations_of_its_pooled_conflicts_are_confirmed():
    """Bug 19 on the recorded answer (the pool's case, rebuilt from the round's data): an agent accuses each INT-CONFLICT-001 the
    channel names on ch-p10c's pairs through 'x0' of being false; the validation confirms each (OVS-JOINT-003, rule local-glosses) and
    refutes none. When the channel no longer pools the pair (the handoff), there is nothing to accuse."""
    from .test_protocol_validate import acc, review
    a = _audited_channel("ch-p10c")
    try:
        d = review(a.auditor, a.ch.channel_uid, agent="overseer-general-1").dossier
        i = next(k for k, t in enumerate(d["transfers"]) if t["message_id"] == a.rc.message_id)
        pairs = ({"s3.1", "s4.2"}, {"s4.6", "s6.2"})
        accusations = [acc(f"a{j}", "false_conflict", [{"pointer": f"/transfers/{i}/receipt/findings/{j}"}], message_ids=[a.rc.message_id],
                           claim_ids=sorted(f["claim_ids"]))
                       for j, f in enumerate(d["transfers"][i]["receipt"]["findings"])
                       if f["code"] == "INT-CONFLICT-001" and set(f["claim_ids"]) in pairs]
        named = [set(f.claim_ids) for f in a.rc.findings if f.code == "INT-CONFLICT-001" and set(f.claim_ids) in pairs]
        assert len(accusations) == len(named)
        if not accusations:
            return
        r = review(a.auditor, a.ch.channel_uid, agent="overseer-general-1")
        out = r.run(accusations)
        assert [x.outcome for x in out.accusations] == ["confirmed"] * len(accusations), [(x.outcome, x.reasons) for x in out.accusations]
    finally:
        a.hub.close()


# ============================================================================================ rule feedback-hold (bugs 9, 18)
def _candidate(code, rule, claim_ids, message, params=()):
    return SimpleNamespace(code=code, rule=rule, basis="channel", claim_ids=tuple(claim_ids), params=tuple(params),
                           finding=SimpleNamespace(code=code, message=message, claim_ids=list(claim_ids)))


def _answer(task_id: str, claims) -> SimpleNamespace:
    it = _item(task_id)
    ids = dict(request_id="r", task_id=task_id, subject=it["subject"], task_type="essay", report_id="rp", agent_id=it["agent_id"], materiality="supporting")
    rep = SimpleNamespace(original_response=it["response_text"], claims=[ClaimRecord(**ids, claim_id=cid, claim_text=ct, claim_role="evidence",
                                                                                        source_refs=refs) for cid, ct, refs in claims])
    return SimpleNamespace(report=rep, receipt=SimpleNamespace(findings=[], coverage=[]))


def test_feedback_holds_a_quotation_flaw_on_the_writers_own_words_and_keeps_a_real_one():
    """Bugs 9 and 18 (critical): the feedback told sp-t16 to remove its labelled model sentence and its suggested ustedes forms, and
    sp-p10d its glosses ("... remove the quotation and what is credited to it"). A quotation flaw every quotation of which the auditor's
    reader reads as the writer's own words is held back (rule feedback-hold); an invented quotation credited to the email is sent."""
    model = ('Model (one sentence, to show range with your own content; not a replacement for your text): "Al principio me daba vergüenza hablar '
             'con la gente del mercado, pero al final ya hablaba con el vendedor de pescado sin ayuda."')
    answer = _answer("sp-t16", [("g1.28", model, []), ("g1.99", 'Your email says "Mi abuela cocina cada domingo".', [])])
    own = _candidate("INT-REQ-003", "src.quote_not_found", ["g1.28"],
                     "quotation 'Al principio me daba vergüenza hablar con la gente del mercado, pero al final ya hablaba con el vendedor de pescado sin ' of "
                     "claim g1.28, which the report credits to no text, was not found in the supplied texts ['doc-rojas-student']")
    real = _candidate("INT-REQ-003", "src.quote_not_found", ["g1.99"],
                      "quotation 'Mi abuela cocina cada domingo' of claim g1.99, which the report credits to no text, was not found in the supplied texts")
    kept, held = held_back(answer, [(own, "s1"), (real, "s2")])
    assert [c for c, _s in kept] == [real]
    assert held and FEEDBACK_HOLD_RULE in held[0] and "own words" in held[0]


def test_feedback_holds_an_unanswered_part_the_answer_answers_under_its_own_label():
    """Bug 9 (maa-t16): "This part of the task appears unanswered: (c) Write down the x-intercepts ... Answer it" although the answer's
    "(c)" section answers it. Held back; a part whose label opens no section of the answer is still sent."""
    answer = _answer("maa-t16", [])
    c = _candidate("INT-REQ-004", "cov.item_unaddressed", [], "request item i3 appears unaddressed", params=(("item", "(c) Write down the x-intercepts of the graph. [1]"),))
    f = _candidate("INT-REQ-004", "cov.item_unaddressed", [], "request item i6 appears unaddressed", params=(("item", "(f) Sketch the graph. [2]"),))
    kept, held = held_back(answer, [(c, "s1"), (f, "s2")])
    assert [x for x, _s in kept] == [f] and "label" in held[0]
    # a section that only restates the question answers nothing: the flaw is still sent
    echoed = SimpleNamespace(report=SimpleNamespace(original_response="(c) Write down the x-intercepts of the graph. [1]\n\n(d) The area is 108.",
                                                    claims=[]), receipt=SimpleNamespace(findings=[], coverage=[]))
    kept, _held = held_back(echoed, [(c, "s1")])
    assert [x for x, _s in kept] == [c]


# ============================================================================================ rule adjudicated-quotations (bug 12)
def test_an_auditor_quotation_accusation_is_scored_only_when_a_reference_adjudicates_it():
    """Bug 12 (major): the c3 gold took the auditor's OVS-FID-004 accusations of sp-t16's corrections as agent-scorable faults. Such a
    disagreement of the auditor and the receipt is scored only when a reviewed reference lists it as a true finding."""
    fault = {"fault_id": "auditor-1-OVS-FID-004", "origin": "auditor", "class": "quotation_absent", "expected_codes": ["OVS-FID-004"],
             "identifiers": {"claim_ids": ["g1.17"]}, "agent_scorable": True}
    other = {"fault_id": "auditor-2-OVS-TRN-004", "origin": "auditor", "class": "grounding_overstated", "expected_codes": ["OVS-TRN-004"],
             "identifiers": {"claim_ids": ["s1.1"]}, "agent_scorable": True}
    gold = ED.adjudicate_disagreements({"channel_key": "sp-t16", "faults": [dict(fault), dict(other)]}, None)
    assert gold["faults"][0]["agent_scorable"] is False and gold["faults"][0]["adjudication"] == "unadjudicated"
    assert gold["faults"][1]["agent_scorable"] is True
    ref = {"true_findings": [{"channel": "sp-t16", "claim_id": "g1.17", "code": "OVS-FID-004"}]}
    gold = ED.adjudicate_disagreements({"channel_key": "sp-t16", "faults": [dict(fault)]}, ref)
    assert gold["faults"][0]["agent_scorable"] is True and gold["faults"][0]["adjudication"].startswith("true")


# ============================================================================================ hostile inputs of the new readers
@pytest.mark.parametrize("piece", ['"a" → ' * 4_000 + "x", "Model (" + "a" * 20_000 + "): x", '"x" means ' * 3_000 + "y", '"a", ' * 5_000 + "b",
                                   " " * 20_000 + '"a"', "\n" * 20_000 + '"a"', "(A1) " * 4_000 + '"a"', "invented example " * 1_500 + '"a"'],
                         ids=["arrows", "label parenthesis", "glosses", "list", "blanks", "line breaks", "mark labels", "invented"])
def test_the_own_text_reader_is_linear_on_hostile_inputs(piece):
    """The own-text reader reads a bounded window around each span: hostile runs of 20,000 characters read in well under the bound."""
    start = time.perf_counter()
    own_text_quotations(piece)
    assert time.perf_counter() - start < 5.0


# ============================================================================================ the class sweep (rule linear-context)
#: The standard hostile inputs of the round's stall rule: about 20,000 characters of blanks, tabs, line breaks, stops, closing marks,
#: mark labels, parentheses, brackets, fence openers, number words joined by "and", "=" links and list markers, each followed by a
#: character that defeats the match, and the figure-dense shapes that stalled the occurrence reader (a figure per short span).
HOSTILE_N = 20_000
HOSTILE = {
    "blanks": " " * HOSTILE_N + "x", "tabs": "\t" * HOSTILE_N + "x", "line breaks": "\n" * HOSTILE_N + "x", "stops": "." * HOSTILE_N + "x",
    "closing marks": ")" * HOSTILE_N + "x", "closing quotes": "”" * HOSTILE_N + "x", "mark labels": "(A1) " * (HOSTILE_N // 5) + "x",
    "parentheses": "(" * HOSTILE_N + "x", "brackets": "[" * HOSTILE_N + "x", "fences": "```\n" * (HOSTILE_N // 4) + "x",
    "number words": "one and " * (HOSTILE_N // 8) + "x", "links": "= " * (HOSTILE_N // 2) + "x", "list markers": "- " * (HOSTILE_N // 2) + "x",
    "numbered": "1. " * (HOSTILE_N // 3) + "x", "figures": "3 " * (HOSTILE_N // 2) + "x", "cut decimals": "1.2… " * (HOSTILE_N // 5) + "x",
    "powers": "x⁴ 2 " * (HOSTILE_N // 5) + "x", "quotations": '"a" ' * (HOSTILE_N // 4) + "x", "arrows": '"a" → ' * (HOSTILE_N // 6) + "x",
    "questions": "Is it 3? " * (HOSTILE_N // 9) + "x", "digits": "9" * HOSTILE_N,
}


def _timed(fn, text: str, bound: float = 5.0) -> None:
    start = time.perf_counter()
    fn(text)
    assert time.perf_counter() - start < bound


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_translation_readers_are_linear_on_hostile_inputs(name):
    """Rule linear-context (the class sweep of the round's stall rule): the same-quantity occurrence reader re-read each figure's
    sentence and paragraph from their starts and rebuilt the sentence list for each figure, so 20,000 characters of figures took 28 to
    85 seconds and a 20,000-digit numeral raised; each public reader of ``checks.translation`` now reads such a text in well under the
    bound (the recorded rounds' 434 texts give the same occurrences as before)."""
    from epinoic_overseer.checks.translation import _read_occurrences, figure_context, figure_reading, target_spans, text_numbers
    text = HOSTILE[name]
    _read_occurrences.cache_clear()
    for fn in (text_numbers, derived_numbers, target_spans, lambda t: figure_reading(Fraction(3), [t], "the count is 3 cm", {"eq"}),
               lambda t: figure_context(t, len(t) // 2, len(t) // 2 + 1), lambda t: labelled_figure(Fraction(3), [t], "the count is 3")):
        _timed(fn, text)


def test_a_figure_in_an_oversize_or_crowded_sentence_is_read_as_no_statement():
    """Rule linear-context fails closed: a figure whose sentence is longer than the bound, or holds more figures than the bound, is
    never read as its source's statement of a quantity (unread), so no premise is ever read as data on an unread sentence."""
    from epinoic_overseer.checks.translation import CONTEXT_UNREAD, FIGURE_READ, figure_reading
    plain = "The count is 3 workers."
    assert figure_reading(Fraction(3), [plain], "the count of workers is 3", {"eq"}).kind == FIGURE_READ
    long = "The count is 3 workers " + "and so on " * 400 + "."
    crowded = "The count is 3 workers, " + ", ".join(str(n) for n in range(10, 60)) + "."
    for text in (long, crowded):
        r = figure_reading(Fraction(3), [text], "the count of workers is 3", {"eq"})
        assert r.kind != FIGURE_READ and r.context == CONTEXT_UNREAD, (r.kind, r.reason[:200])


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_fidelity_joint_feedback_and_gate_readers_are_linear_on_hostile_inputs(name):
    """The class sweep over the other modules this clearance changed: ``checks.fidelity`` (own-text, own-model, mark annotations, the
    figure text, list numbers), ``checks.joint`` (evaluation points, glosses), ``feedback`` (an answered label, the quotations a flaw
    rests on and whether they are the writer's own words, a flaw on a note-led block) and ``meta_notes`` (rule answer-status) each read
    a hostile text in well under the bound."""
    from epinoic_overseer.checks.fidelity import figure_text, own_model_quotations, response_list_numbers, strip_mark_annotations
    from epinoic_overseer.checks.joint import _gloss_identity, evaluation_points
    from epinoic_overseer.feedback import _answered_label, _in_lead_blocks, _own_words

    def flaw(t: str, code: str, message: str) -> tuple:
        c = SimpleNamespace(code=code, rule="r", basis="channel", claim_ids=("g1",), params=(),
                            finding=SimpleNamespace(code=code, message=message, claim_ids=["g1"]))
        return c, SimpleNamespace(original_response=t, claims=[SimpleNamespace(claim_id="g1", claim_text=t, source_refs=[])])

    def own_words(t: str) -> None:
        for code, message in (("OVS-FID-004", "claim g1 quotes [" + ", ".join(["'" + t[:200] + "'"] * 6) + "], which occur in no supplied text"),
                              ("INT-REQ-003", "quotation '" + t[:200] + "' of claim g1 is credited to no supplied text"), ("INT-REQ-003", t)):
            c, rep = flaw(t, code, message)
            _own_words(c, rep, own_text_quotations(t))

    text = HOSTILE[name]
    for fn in (own_text_quotations, own_model_quotations, strip_mark_annotations, figure_text, response_list_numbers, evaluation_points,
               lambda t: _gloss_identity(t, set()), self_certifying_sentence,
               lambda t: _answered_label(SimpleNamespace(params=(("item", "(c) " + t[:300]),)), "(c)\n" + t),
               own_words, lambda t: _in_lead_blocks(*flaw(t, "ES-STR-001", "structure"))):
        _timed(fn, text)
