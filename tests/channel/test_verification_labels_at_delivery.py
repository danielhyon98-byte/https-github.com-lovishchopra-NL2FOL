"""A verification label on a specialist's sentence is named at delivery on every branch (CORE-SELF-001), and never
demotes the content it is attached to (combinator verification finding M1, round 1).

Before, "Verified: The Weimar constitution was adopted in August 1919." was delivered with no finding at all (the core
pack read only the whole-sentence vocabulary, "VERIFIED: all claims checked and confirmed."), and a sentence that was
nothing but "[verified]" could even become a paragraph's point. Now the core pack names the label on the claim that
holds it, on the History, English, generic (Economics) and STEM (Physics, Mathematics) branches; the labelled content
keeps the role and the materiality it has without the label, so a label can never take content out of the checks; and
a sentence that is nothing but a label is a note (roled ``other``, its self-report recorded for audit).
"""
from __future__ import annotations

import pytest

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"verification-label-test-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)

#: subject -> (agent, the sentence a label is attached to, the rest of the answer). The English answer is long enough
#: (more than 25 words) that its paragraph is prose, not a short meta block.
ANSWERS = {
    "History": ("history-specialist", "The Weimar constitution was adopted in August 1919.",
                "Article 48 may have weakened the Reichstag's authority because it allowed rule by decree."),
    "Economics": ("economics-specialist", "Unemployment in Germany reached 6 million in 1932.", "The slump deepened because exports collapsed."),
    "English A: Literature": ("english-specialist", "The speaker presents the city as calm and bright in the early morning light.",
                              "The calm suggests a moment of suspended time, and the stillness of the river carries the poem's quiet wonder at a city "
                              "seen before its working day begins."),
    "Physics": ("physics-specialist", "The trolley's speed is 15 m/s.", "Its kinetic energy is therefore larger than at rest."),
    "Mathematics": ("mathematics-specialist", "The solution of 2x + 3 = 7 is x = 2.", "Substituting x = 2 gives 7 = 7."),
}
#: Every label form the verifiers named, attached to the sentence.
FORMS = {
    "Verified: prefix": lambda s: "Verified: " + s,
    "(verified) suffix": lambda s: s[:-1] + " (verified).",
    "[verified] prefix": lambda s: "[verified] " + s,
    "Checked: prefix": lambda s: "Checked: " + s,
    "as formally verified suffix": lambda s: s[:-1] + ", as formally verified.",
}


def _deliver(subject: str, text: str):
    agent = ANSWERS[subject][0]
    plan = WorkPlan(plan_id="plan-l", request_id="req-l", task_id="task-l", subject=subject, task_type="short_answer", selected_agent_ids=[agent])
    ch = TranslatorChannel(plan, signing_key=KEY, config=CFG)
    m, _req, _rr = ch.request("router", agent, "Answer the question in a short paragraph.")
    reply, rc = ch.respond_text(m.message_id, text, agent_id=agent, report_id="rep-l")
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED, rc.summary
    [report] = ch.transmitted_reports.values()
    return report, rc


def _self_reports(rc) -> list:
    return [f for f in rc.structural_findings if f.code == "CORE-SELF-001"]


def _holding(report, needle: str):
    return [c for c in report.claims if needle in c.claim_text]


@pytest.mark.parametrize("form", list(FORMS))
@pytest.mark.parametrize("subject", list(ANSWERS))
def test_a_label_on_a_content_sentence_is_named_on_its_claim_and_leaves_the_content_a_claim(subject, form):
    _agent, sentence, rest = ANSWERS[subject]
    plain_report, plain_rc = _deliver(subject, f"{sentence} {rest}")
    assert not _self_reports(plain_rc), "the answer without the label carries no self-report"
    labelled = FORMS[form](sentence)
    report, rc = _deliver(subject, f"{labelled} {rest}")
    findings = _self_reports(rc)
    assert len(findings) == 1 and findings[0].severity == "warning", [(f.code, f.message) for f in rc.structural_findings]
    label_claims = [c for c in report.claims if "erified" in c.claim_text or "hecked" in c.claim_text]
    assert label_claims and set(findings[0].claim_ids) == {c.claim_id for c in label_claims}, (findings[0].claim_ids, report.claims)
    assert "verification" in findings[0].message and "verified" not in findings[0].message.replace("verification", ""), "the message never repeats the label"
    # the content keeps the role and the materiality it has without the label: a label never takes content out of the checks
    content = sentence[:20]
    [before] = _holding(plain_report, content)
    [after] = _holding(report, content)
    assert (after.claim_role, after.materiality) == (before.claim_role, before.materiality), (after, before)


@pytest.mark.parametrize("subject", list(ANSWERS))
def test_a_sentence_that_is_nothing_but_a_label_is_a_note_named_at_delivery(subject):
    _agent, sentence, rest = ANSWERS[subject]
    report, rc = _deliver(subject, f"{sentence} Verified. {rest}")
    [note] = [c for c in report.claims if c.claim_text.strip() == "Verified."]
    assert note.claim_role == "other" and note.materiality == "supporting" and note.advisory_verification_status
    [finding] = _self_reports(rc)
    assert finding.claim_ids == [note.claim_id] and "nothing but a verification-status label" in finding.message
    assert any(f.code == "INT-HANDOFF-006" and f.claim_ids == [note.claim_id] for f in rc.findings)


@pytest.mark.parametrize("subject", list(ANSWERS))
def test_a_historical_check_or_a_disclaimer_is_no_label_at_delivery(subject):
    _agent, sentence, rest = ANSWERS[subject]
    for text in (f"{sentence[:-1]} (not verified). {rest}", f"{sentence[:-1]}, as confirmed by the census of 1925. {rest}",
                 f"{sentence} The figures were, in 1925, verified by the statistical office. {rest}"):
        _report, rc = _deliver(subject, text)
        assert not _self_reports(rc), (subject, text, [f.message for f in _self_reports(rc)])
