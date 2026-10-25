"""Regression tests for the content-check defects found by adversarial review round 2 of the Overseer (each fails on the
code before the fix; the scenarios are the reviewers' own):

* a supplied text that presents a forwarded report is held to byte identity whatever its document id (PEER-002), and
  one document id carries one text in a task;
* the synthesis ledger: a one-sided move of a figure onto another figure's event that keeps only a shared noun
  ("Factory", "Act"), or a year standing in another year's place, is INT-LEDGER-023; a figure or date in the
  student-facing text that no synthesized claim states is INT-LEDGER-023; a single-source paraphrase that turns a
  comparison the other way or negates its source's own content is INT-LEDGER-030 (INT-LEDGER-027 before the translator merge,
  which gave that number to a dropped from-memory label); each is an error the release gate
  refuses;
* precision on genuine transfers: a claim that occurs verbatim in a response laid out with markdown structure (bold
  numbering, items without full stops, a bullet after a quotation, inline numbering) is never FID-001; a list number
  carried in a claim is never FID-003; a U+FEFF inside a response is invisible; the contract's advisory fields on a
  structured report are FID-009 (warning), not FID-005; a hand-off that differs only in ``created_at`` is not PEER-001;
  faithful STEM syntheses (notation, ranges) are not INT-LEDGER-023; a synthesis whose receipt states its unperformed
  entailment check is released, and the contained harness counts DIV-001 as a false alarm on genuine transfers.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from epinoic_logic.adapters.fixtures_multi_subject import by_name
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.integrity.ledger import check_synthesis_ledger, figure_pairing_differences, meaning_inversions
from epinoic_logic.ir.schema import Assertion
from epinoic_logic.overseer import may_act, may_release
from epinoic_logic.overseer.checks import normalise, plain_form
from epinoic_logic.overseer.checks.fidelity import claim_occurs, response_list_numbers
from epinoic_logic.overseer.policy import release_decision
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from .conftest import (
    EN_CLAIMS, EN_TEXT, EXTRACT, EN_INPUT, HI_INPUT, HI_TEXT, default_synthesis, english_report, findings, int_problem, make_auditor, make_plan,
    run_task,
)
from .test_audit_joint_divergence import _merged_synthesis
from .test_hook_hub import audited_hub
from .test_review1_content_checks import _hi_report


def _errors(audit) -> set[str]:
    return {f.code for f in audit.report.findings if f.severity == "error"}


def _release(auditor, task, audit):
    return release_decision(task.receipts["syn"], audit, auditor.keyring, audits=auditor.audits(task.uid), journal=auditor.journal(task.uid),
                            message=task.messages["syn"])


# ============================================================================================ peer documents under any id
ALTERED = EN_TEXT.replace("every hour", "every minute")


def _forward_then_supply(auditor, document_id: str, text: str, *, author: str = "english-specialist", allowed=()):
    """The router forwards the English report faithfully, then supplies the History specialist a text under ``document_id``."""
    task = run_task(auditor, synthesis=False, peer=False, plan=make_plan(allowed_document_ids=list(allowed)))
    reply = task.messages["rep_en"]
    task.ch.relay("router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(reply.payload),
                  in_reply_to=reply.message_id)
    doc = SuppliedText(document_id=document_id, title="English specialist report", author=author, text=text)
    m, _r, rq = task.ch.request("router", "history-specialist", HI_INPUT + " Again.", [doc])
    return task, m, rq


@pytest.mark.parametrize("document_id,author,allowed", [
    ("en-answer", "english-specialist", ()),
    ("english-specialist", "english-specialist", ()),
    ("doc-mill", "english-specialist", ("doc-mill", "peer:en")),  # an allowed id, in the extract's place
    ("notes", "Anonymous", ()),  # neither id nor author: a near copy of the forwarded answer
])
def test_a_forwarded_answer_altered_under_any_document_id_is_peer_002(auditor, document_id, author, allowed):
    assert "every hour" in EN_TEXT
    task, m, rq = _forward_then_supply(auditor, document_id, ALTERED, author=author, allowed=allowed)
    assert rq.status.value == "ACCEPTED"  # the channel has no rule for it
    clr = auditor.clearance(task.uid, m.message_id, receipt=rq)
    assert clr.state == "AUDIT_FAILED" and "OVS-PEER-002" in clr.codes and not may_act(rq, clr), (document_id, clr.codes)
    assert [f for f in findings(task.audit(), "OVS-PEER-002") if m.message_id in f.message_ids]


def test_control_the_forwarded_answer_unchanged_under_another_id_is_not_peer_002(auditor):
    task, m, rq = _forward_then_supply(auditor, "en-answer", EN_TEXT)
    clr = auditor.clearance(task.uid, m.message_id, receipt=rq)
    assert "OVS-PEER-002" not in clr.codes and clr.state != "AUDIT_FAILED"


def test_one_document_id_carries_one_text_in_a_task(auditor):
    task = run_task(auditor, synthesis=False)
    same = SuppliedText(document_id="doc-mill", title="Mill extract", author="Anonymous", text=EXTRACT)
    m0, _r0, rq0 = task.ch.request("router", "english-specialist", EN_INPUT + " Once more.", [same])
    assert "OVS-PEER-002" not in auditor.clearance(task.uid, m0.message_id, receipt=rq0).codes
    other = SuppliedText(document_id="doc-mill", title="Mill extract", author="Anonymous", text=EXTRACT.replace("all night", "all day"))
    m, _r, rq = task.ch.request("router", "english-specialist", EN_INPUT + " Again.", [other])
    assert rq.status.value == "ACCEPTED"
    clr = auditor.clearance(task.uid, m.message_id, receipt=rq)
    assert clr.state == "AUDIT_FAILED" and "OVS-PEER-002" in clr.codes
    f = [x for x in findings(task.audit(), "OVS-PEER-002") if m.message_id in x.message_ids]
    assert f and "doc-mill" in f[0].document_ids and task.mids["req_en"] in f[0].message_ids


# ============================================================================================ the synthesis ledger
def _syn(rep: SpecialistReport, claims: list[SynthesizedClaim], text: str | None = None) -> Synthesis:
    text = text if text is not None else " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn-1", request_id=rep.request_id, task_id=rep.task_id, combinator_agent_id="combinator", source_report_ids=[rep.report_id],
                     claims=claims, ledger=[], text=text, text_sha256=sha256_text(text), created_at="2026-10-11T12:00:00Z")


def _ledger(rep, claims, text=None) -> set[tuple[str, str]]:
    return {(f.code, f.severity) for f in check_synthesis_ledger([rep], _syn(rep, claims, text))}


def _ledger_messages(rep, claims, code: str, text=None) -> list[str]:
    return [f.message for f in check_synthesis_ledger([rep], _syn(rep, claims, text)) if f.code == code]


@pytest.mark.parametrize("text", [
    "The Factory Act of 1847 banned the employment of children under nine in textile mills.",  # keeps 'Factory', 'Act'
    "The ban on the employment of children under nine in textile mills, which the Factory Act introduced, came in 1847.",
    "The ban on employing children under nine, which the Factory Act introduced, came in 1847.",  # reworded events
])
def test_the_1833_ban_moved_onto_1847_in_a_merged_claim_is_int_ledger_023(text):
    rep = _hi_report(HI_TEXT)
    claims = [SynthesizedClaim(claim_id="s2", text=text, source_claim_ids=["h1.1", "h1.2"], transformation="merged")]
    assert ("INT-LEDGER-023", "error") in _ledger(rep, claims)


@pytest.mark.parametrize("text", [
    "The Factory Act of 1833 banned the employment of children under nine in textile mills, and the Ten Hours Act of 1847 followed it.",
    "Children under nine were banned from textile mills by the Factory Act of 1833, which the Ten Hours Act of 1847 followed.",
])
def test_control_a_faithful_merge_of_the_two_acts_is_not_re_paired(text):
    rep = _hi_report(HI_TEXT)
    claims = [SynthesizedClaim(claim_id="s2", text=text, source_claim_ids=["h1.1", "h1.2"], transformation="merged")]
    assert ("INT-LEDGER-023", "error") not in _ledger(rep, claims)


def test_the_1833_ban_moved_onto_1847_in_the_student_text_only_is_never_released(auditor):
    rep = _hi_report(HI_TEXT)
    carried = [SynthesizedClaim(claim_id="s2", text=rep.claims[0].claim_text, source_claim_ids=["h1.1"], transformation="carried"),
               SynthesizedClaim(claim_id="s2b", text=rep.claims[1].claim_text, source_claim_ids=["h1.2"], transformation="carried")]
    moved = "The Factory Act of 1847 banned the employment of children under nine in textile mills. The Ten Hours Act of 1847 followed it."
    assert ("INT-LEDGER-023", "error") in _ledger(rep, carried, moved)
    s1 = SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried")
    s3 = SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"], transformation="carried")
    text = "The writer presents work as endless. " + moved + " On balance, the Act mattered most because it established inspection."
    task = run_task(auditor, synthesis_obj=default_synthesis(claims=[s1, *carried, s3], text=text))
    assert any(f.code == "INT-LEDGER-023" and f.severity == "error" for f in task.receipts["syn"].findings)
    assert not _release(auditor, task, task.audit(final=True)).allowed


@pytest.mark.parametrize("old,new", [("1833", "1834"), ("under nine", "under ten"), ("under nine", "under 12")])
def test_a_figure_or_date_in_the_student_text_that_no_claim_states_is_int_ledger_023_and_never_released(auditor, old, new):
    syn = default_synthesis()
    assert old in syn.text
    text = syn.text.replace(old, new, 1)
    task = run_task(auditor, synthesis_obj=syn.model_copy(update={"text": text, "text_sha256": sha256_text(text)}))
    rs = task.receipts["syn"]
    f = [x for x in rs.findings if x.code == "INT-LEDGER-023" and x.severity == "error"]
    assert f and "student-facing text" in f[0].message
    dec = _release(auditor, task, task.audit(final=True))
    assert not dec.allowed and "INT-LEDGER-023" in dec.reason


def test_control_the_unchanged_student_text_states_only_the_claims_figures(auditor):
    task = run_task(auditor)
    assert not [x for x in task.receipts["syn"].findings if x.code == "INT-LEDGER-023"]
    assert _release(auditor, task, task.audit(final=True)).allowed


H11 = "The Factory Act of 1833 banned the employment of children under nine in textile mills."
CONCL = Assertion.model_validate(int_problem("h1.1", "min_age", 9, op="ge", bound=9).conclusion.model_dump(mode="json"))


def _paraphrase(text: str) -> Synthesis:
    return default_synthesis(claims=[
        SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried"),
        SynthesizedClaim(claim_id="s2", text=text, source_claim_ids=["h1.1"], transformation="paraphrased", formal_conclusion=CONCL),
        SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"], transformation="carried")])


@pytest.mark.parametrize("text", [
    "The Factory Act of 1833 banned the employment of children over nine in textile mills.",  # the comparison turned the other way
    "The Factory Act of 1833 did not ban the employment of children under nine in textile mills.",  # the source negated
])
def test_a_paraphrase_that_states_the_opposite_of_its_source_is_int_ledger_030_whatever_its_formal_conclusion(auditor, text):
    task = run_task(auditor, synthesis_obj=_paraphrase(text))
    rs = task.receipts["syn"]
    assert rs.formal_result_ids  # the entailment check on the source's own conclusion ran and succeeded
    f = [x for x in rs.findings if x.code == "INT-LEDGER-030"]
    assert f and f[0].severity == "error" and "s2" in f[0].claim_ids
    assert not _release(auditor, task, task.audit(final=True)).allowed


def test_control_a_faithful_paraphrase_is_released(auditor):
    task = run_task(auditor, synthesis_obj=_paraphrase("In 1833 the Factory Act banned the employment of children under nine in textile mills."))
    assert not [x for x in task.receipts["syn"].findings if x.code in ("INT-LEDGER-030", "INT-LEDGER-026", "INT-LEDGER-027")]
    assert _release(auditor, task, task.audit(final=True)).allowed


def test_an_added_negation_is_an_error_only_when_it_negates_the_sources_own_content():
    assert meaning_inversions("The Factory Act of 1833 did not ban the employment of children under nine.", [H11], "paraphrased")
    # a polarity-preserving rewording of a prohibition ("banned employing" -> "could not be employed")
    assert not meaning_inversions("Under the Factory Act of 1833, children under nine could not be employed in textile mills.", [H11], "paraphrased")
    # a negation over words the source does not state: another statement (the INT-LEDGER-026 warning), not its opposite
    src = 'The verb "assembled", with the reflexive "itself", gives the town the action, so the place she left seems to build itself out of the mist.'
    other = "The bruise comparison has no 'like' or 'as', so it is a metaphor."
    assert not meaning_inversions(other, [src], "paraphrased")
    rep = _hi_report("The verb assembled gives the town the action. It builds itself out of the mist.")
    found = _ledger(rep, [SynthesizedClaim(claim_id="s1", text=other, source_claim_ids=["h1.1"], transformation="paraphrased")])
    # The original assertion on the original input, kept (the error renumbered INT-LEDGER-030 by the translator merge): the
    # unaligned negation is the INT-LEDGER-026 warning, never the error. The merged ledger keeps this branch's polarity
    # reading (rule unaligned-polarity) beside the development branch's aligned comparison, which reads a negation only in a
    # statement copied from a cited source; the third repair restored it after the staged rewrite had pinned its loss.
    assert ("INT-LEDGER-030", "error") not in found and ("INT-LEDGER-026", "warning") in found
    assert found == {("INT-LEDGER-002", "error"), ("INT-LEDGER-026", "warning")}  # exactly: and the uncited h1.2 unaccounted for
    msgs = _ledger_messages(rep, [SynthesizedClaim(claim_id="s1", text=other, source_claim_ids=["h1.1"], transformation="paraphrased")], "INT-LEDGER-026")
    assert len(msgs) == 1 and "it adds a negation its cited sources do not state" in msgs[0]
    # the warning-not-error property on a statement the merged rule aligns: a negation over a word the source does not
    # state ("no fog" for "the mist") is the INT-LEDGER-026 warning and never the INT-LEDGER-030 error
    copied = _hi_report("The place she left seems to build itself out of the mist.")
    found = _ledger(copied, [SynthesizedClaim(claim_id="s1", text="The place she left seems to build itself out of no fog.", source_claim_ids=["h1.1"],
                                               transformation="paraphrased")])
    assert ("INT-LEDGER-030", "error") not in found and ("INT-LEDGER-026", "warning") in found
    assert meaning_inversions("The place she left does not build itself out of the mist.", [src], "paraphrased")


# ============================================================================================ faithful STEM syntheses (rule math-notation, range-ends)
MAA_T13 = ("The distance travelled in 0 ≤ t ≤ 3 is 8 m: v = 3t(2 − t) is positive for 0 < t < 2 and negative for 2 < t ≤ 3, so distance = ∫₀² v dt − ∫₂³ v dt = "
           "4 − (−4) = 8.",
           ["(c) Distance travelled is ∫₀³ |v| dt, so the sign of v must be found.", "From (b), v = 3t(2 − t).",
            "For 0 < t < 2, both 3t and 2 − t are positive, so v > 0.", "For 2 < t ≤ 3, 2 − t is negative, so v < 0.",
            "The velocity changes sign at t = 2, so\n    distance = ∫₀² v dt − ∫₂³ v dt  M1\n    An antiderivative of v is 3t² − t³, since ∫6t dt = 3t² and "
            "∫3t² dt = t³.\n    ∫₀² v dt = [3t² − t³]₀² = (12 − 8) − 0 = 4  A1\n    ∫₂³ v dt = [3t² − t³]₂³ = (27 − 27) − (12 − 8) = −4  A1\n    distance = 4 − (−4) = 8\n"
            "    Distance travelled = 8 m  A1"])
PH_T13 = ("With the 6.0 Ω resistor removed, the external resistance rises to 4.0 Ω and the total to 4.5 Ω, so the current from the cell falls from 4.1 A to 2.7 A; "
          "the potential difference lost across the internal resistance therefore falls, and the terminal potential difference rises from 9.9 V to 10.7 V.",
          ["With the 6.0 Ω resistor removed, only the 4.0 Ω resistor remains.",
           "The external resistance rises from 2.4 Ω to 4.0 Ω, so the total resistance rises from 2.9 Ω to 4.5 Ω.",
           "From ε = I(R + r), the current from the cell falls, from 4.1 A to 2.7 A.",
           "The potential difference lost across the internal resistance, Ir, therefore falls, and from V = ε − Ir the terminal potential difference rises, "
           "from 9.9 V to 10.7 V."])
MAA_P7B = ("The Physics report's values agree with this answer (its λ = 0.693/8.0 h = 0.087 h⁻¹ matches k = (ln 2)/8 h⁻¹, and its T½ = 8.0 h matches part (b)), "
           "but its stated half-life range of about 7.8 h to 8.2 h is narrower than its own ±2% values allow, since checking t = 0 and t = 8 with the stated ±32 "
           "and ±16 counts min⁻¹ gives worst-case half-lives of about 8.5 h and 7.6 h.",
           ["Cross-checks with the Physics specialist: its “λ = 0.693/8.0 h = 0.087 h⁻¹” agrees with k = (ln 2)/8 h⁻¹, and its “T½ = 8.0 h” agrees with (b).",
            "Its statement “The corrected rate halves each time: 1600 to 800 counts min⁻¹ between 0 and 8 h, 800 to 400 between 8 and 16 h, and 400 to 200 "
            "between 16 and 24 h.” matches an 8-hour half-life.",
            "Note on the Physics specialist’s uncertainty: it writes “T½ = 8.0 h, with an uncertainty of about ±0.2 h (between about 7.8 h and 8.2 h, from the "
            "±2% values).” Checking only t = 0 and t = 8 with the stated ±32 and ±16 gives worst-case half-lives of about 8 ln 2 ÷ ln(1568/816) ≈ 8.5 h and "
            "8 ln 2 ÷ ln(1632/784) ≈ 7.6 h.",
            "So the stated range is narrower than its own ±2% values allow at the extremes."])


def _stem_report(sources: list[str]) -> SpecialistReport:
    text = "\n".join(sources)
    claims = [ClaimRecord(request_id="req-t", task_id="t", report_id="rep-t", agent_id="maths-specialist", subject="Mathematics: Analysis and Approaches",
                          task_type="worked_solution", claim_id=f"g{i + 1}", claim_text=s, claim_role="point", materiality="material") for i, s in enumerate(sources)]
    return SpecialistReport(report_id="rep-t", request_id="req-t", task_id="t", agent_id="maths-specialist", subject="Mathematics: Analysis and Approaches",
                            task_type="worked_solution", original_response=text, response_sha256=sha256_text(text), supplied_texts=[], claims=claims,
                            created_at="2026-10-11T11:00:00Z")


@pytest.mark.parametrize("name,case", [("maa-t13", MAA_T13), ("ph-t13", PH_T13), ("maa-p7b", MAA_P7B)])
def test_recorded_faithful_stem_syntheses_are_not_re_paired(name, case):
    text, sources = case
    assert figure_pairing_differences(text, sources) == [], name
    rep = _stem_report(sources)
    claims = [SynthesizedClaim(claim_id="s1", text=text, source_claim_ids=[c.claim_id for c in rep.claims], transformation="merged")]
    assert ("INT-LEDGER-023", "error") not in _ledger(rep, claims), name


def test_control_a_reversed_range_is_still_caught():
    _text, sources = PH_T13
    out = figure_pairing_differences("The external resistance falls from 4.0 Ω to 2.4 Ω.", sources)
    assert out and "reverses" in out[0]


# ============================================================================================ FID precision on genuine layouts
POEM = SuppliedText(document_id="doc-p", title="poem", author="A. Poet", text="Who goes there? It is only the wind.")
LAYOUTS = [
    ("items without full stops", "English A: Literature", "english-specialist", "analytical_paragraph", [],
     "The main causes of hyperinflation in 1923 were:\n1. Reparations owed under the Treaty of Versailles\n2. The occupation of the Ruhr\n"
     "3. Printing money to pay striking workers\n\nTogether these destroyed the value of the mark."),
    ("paragraphs numbered in bold", "English A: Literature", "english-specialist", "analytical_paragraph", [POEM],
     "**1.** The poem opens with a question, \"Who goes there?\", which creates suspense.\n\n**2.** The answer, \"It is only the wind\", releases that suspense."),
    ("a bullet after a line ending in a quotation", "English A: Literature", "english-specialist", "analytical_paragraph", [POEM],
     "The poem withholds its answer.\n- \"Who goes there?\"\n- The question is answered only by \"It is only the wind\"."),
    ("items numbered inline (generic adapter)", "Economics", "economics-specialist", "data_response", [],
     "Answers: 1. Demand is price elastic. 2. Total revenue falls when the price rises. 3. The tax burden falls mainly on producers."),
    ("a list number on its own line (History)", "History", "history-specialist", "short_answer", [],
     "1.\nThe treaty was signed in 1919.\n\n2.\nIt imposed reparations on Germany."),
    ("a U+FEFF inside a word (Economics)", "Economics", "economics-specialist", "data_response", [],
     "Demand for petrol is price inelastic.\n\nTotal revenue rises when the price rises.\n\nThe burden falls mainly on con﻿sumers in 2023."),
    ("a U+FEFF inside a word (History)", "History", "history-specialist", "short_answer", [],
     "Demand for petrol is price inelastic.\n\nTotal revenue rises when the price rises.\n\nThe burden falls mainly on con﻿sumers in 2023."),
    ("a U+FEFF inside a word (English)", "English A: Literature", "english-specialist", "analytical_paragraph", [],
     "Demand for petrol is price inelastic.\n\nTotal revenue rises when the price rises.\n\nThe burden falls mainly on con﻿sumers in 2023."),
]


def _deliver_raw(subject: str, agent: str, task_type: str, docs: list, text: str):
    hub = audited_hub(auditor=make_auditor(shadow="off"))
    try:
        hub.open_task(WorkPlan(plan_id="plan-t", request_id="req-t", task_id="t", subject=subject, task_type=task_type,
                               selected_agent_ids=[agent, "combinator"], allowed_document_ids=[d.document_id for d in docs]))
        m, _req, _rq = hub.dispatch("t", agent, "Answer the question; quote exactly.", docs)
        reply, rc = hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-t")
        return reply, rc, hub.audit("t"), hub.clearance("t", rc.message_id, receipt=rc)
    finally:
        hub.close()


@pytest.mark.parametrize("label,subject,agent,task_type,docs,text", LAYOUTS, ids=[x[0] for x in LAYOUTS])
def test_a_genuine_answer_laid_out_with_markdown_structure_is_never_fid_001_or_fid_003(label, subject, agent, task_type, docs, text):
    reply, rc, audit, clr = _deliver_raw(subject, agent, task_type, docs, text)
    assert reply is not None and rc.status.value != "REJECTED"
    bad = [(f.code, f.claim_ids) for f in audit.report.findings if f.code in ("OVS-FID-001", "OVS-FID-003")]
    assert not bad, (label, bad)
    assert audit.state != "AUDIT_FAILED" and clr.state != "AUDIT_FAILED", (label, _errors(audit))


def test_rule_context_free_accepts_every_claim_that_occurs_verbatim():
    response = "**1.** The poem opens with a question.\n\n**2.** The answer, \"It is only the wind\", releases that suspense."
    claim = "**2.** The answer, \"It is only the wind\", releases that suspense."
    assert normalise(claim) not in normalise(response)  # the in-context list-marker rule alone rejected it
    assert claim_occurs(claim, normalise(response), plain_response=plain_form(response))
    assert not claim_occurs("**2.** The answer releases nothing.", normalise(response), plain_response=plain_form(response))
    assert "﻿" not in normalise("con﻿sumers") and plain_form("con﻿sumers") == "consumers"


def test_rule_carried_list_number():
    assert response_list_numbers("Answers: 1. X. 2. Y.") == {"1", "2"}
    assert response_list_numbers("were:\n1. A\n**2.** B") == {"1", "2"}
    assert response_list_numbers("The treaty was signed in 1919.") == set()


def test_control_a_figure_absent_from_the_response_is_still_fid_003():
    text = "Answers: 1. Demand is price elastic. 2. Total revenue falls when the price rises."
    hub = audited_hub(auditor=make_auditor(shadow="off"))
    try:
        hub.open_task(WorkPlan(plan_id="plan-t", request_id="req-t", task_id="t", subject="Economics", task_type="data_response",
                               selected_agent_ids=["economics-specialist", "combinator"]))
        m, _req, _rq = hub.dispatch("t", "economics-specialist", "Answer.", [])
        claims = [ClaimRecord(request_id="req-t", task_id="t", report_id="rep-t", agent_id="economics-specialist", subject="Economics", task_type="data_response",
                              claim_id="g1", claim_text="Demand is price elastic in 2023.", claim_role="point", materiality="material")]
        rep = SpecialistReport(report_id="rep-t", request_id="req-t", task_id="t", agent_id="economics-specialist", subject="Economics", task_type="data_response",
                               original_response=text, response_sha256=sha256_text(text), supplied_texts=[], claims=claims, created_at="2026-10-11T11:00:00Z")
        _reply, _rc = hub.receive("t", m.message_id, rep)
        assert {"OVS-FID-001", "OVS-FID-003"} <= _errors(hub.audit("t"))
    finally:
        hub.close()


# ============================================================================================ advisory fields on a structured report
def test_the_contracts_advisory_fields_on_a_structured_report_are_fid_009_not_fid_005():
    rep = by_name("english_interpretation").report
    assert rep.claims[0].advisory_verification_status is not None
    hub = audited_hub(auditor=make_auditor(shadow="off"))
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id=rep.request_id, task_id=rep.task_id, subject=rep.subject, task_type=rep.task_type,
                               selected_agent_ids=[rep.agent_id, "combinator"]))
        m, _req, _rq = hub.dispatch(rep.task_id, rep.agent_id, "How does the writer distance the reader from the violence?")
        _reply, rc = hub.receive(rep.task_id, m.message_id, rep)
        assert any(f.code == "INT-HANDOFF-006" for f in rc.findings)
        audit = hub.audit(rep.task_id)
        assert not findings(audit, "OVS-FID-005") and findings(audit, "OVS-FID-009")
        assert audit.state != "AUDIT_FAILED" and hub.clearance(rep.task_id, rc.message_id, receipt=rc).state != "AUDIT_FAILED"
    finally:
        hub.close()


def test_control_a_self_certification_delivered_as_content_is_still_fid_005(auditor):
    cert = "I have verified every quotation in this answer."
    claims = [dict(c) for c in EN_CLAIMS] + [dict(claim_id="en-cert", claim_text=cert, claim_role="point", materiality="material")]
    task = run_task(auditor, en_report=english_report(EN_TEXT + " " + cert, claims), synthesis=False)
    f = findings(task.audit(), "OVS-FID-005")
    assert f and "en-cert" in f[0].claim_ids


# ============================================================================================ a hand-off re-timestamped
def test_a_hand_off_of_the_delivered_report_with_only_a_new_created_at_is_not_peer_001(auditor):
    task = run_task(auditor, synthesis=False, peer=False)
    held = SpecialistReport.model_validate(task.messages["rep_en"].payload)
    again = SpecialistReport.model_validate({**held.model_dump(mode="json", exclude_none=True), "created_at": "2026-10-11T11:30:00Z"})
    _m, rc = task.ch.relay("english-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, again)
    assert rc.status.value == "ACCEPTED"
    clr = auditor.clearance(task.uid, rc.message_id, receipt=rc)
    assert "OVS-PEER-001" not in clr.codes and clr.state != "AUDIT_FAILED"
    assert not [f for f in findings(task.audit(), "OVS-PEER-001") if rc.message_id in f.message_ids]


def test_control_a_hand_off_with_another_claim_text_is_peer_001(auditor):
    task = run_task(auditor, synthesis=False, peer=False)
    payload = SpecialistReport.model_validate(task.messages["rep_en"].payload).model_dump(mode="json", exclude_none=True)
    payload["claims"][3]["claim_text"] = "time itself is paid in coal"
    _m, rc = task.ch.relay("english-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, SpecialistReport.model_validate(payload))
    if rc.status.value != "REJECTED":
        clr = auditor.clearance(task.uid, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-PEER-001" in clr.codes


# ============================================================================================ a stated, unperformed synthesis check
def test_a_merged_synthesis_whose_receipt_states_the_unperformed_check_is_released(auditor):
    task = run_task(auditor, synthesis_obj=_merged_synthesis())
    rs = task.receipts["syn"]
    assert any(f.code in ("INT-LEDGER-011", "INT-SYNTH-012") and "NOT performed" in f.message for f in rs.findings)
    audit = task.audit(final=True)
    assert not findings(audit, "OVS-DIV-001") and audit.transfer_states[task.mids["syn"]] != "AUDIT_FAILED"
    assert _release(auditor, task, audit).allowed


def test_the_contained_harness_counts_every_error_on_a_genuine_transfer_as_a_false_alarm():
    scripts = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import run_contained as RC
    assert RC.GENUINE_EXCLUDED == () and "OVS-DIV-001" not in RC.GENUINE_EXCLUDED
