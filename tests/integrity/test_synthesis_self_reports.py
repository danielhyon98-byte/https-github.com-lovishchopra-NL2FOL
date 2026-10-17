"""INT-LEDGER-029: a synthesis that states a verification status of the answer is a self-report, whoever wrote it.

The combinator sub-project's instructions say never to carry a note, a self-certification, a decline or a question back
as a claim; the hub, the independent checker of every synthesis, names it when one is carried anyway: copied from a
specialist's note, merged into a factual claim, or written only into the student-facing text. The rule (ported from the
argument-diagnosis work, combinator-faults-3) reads the specialists' closed self-certification vocabulary
(``adapters.markdown.is_self_certification``), so a synthesis that reports its sources plainly is no self-report.

A verification label attached to a claim's content ("Verified: ...", "... (verified).", "[verified] ...", "Checked: ...",
"..., as formally verified.") is named the same way (``adapters.markdown.verification_label``; combinator verification
round 1, M1): before, only the whole-sentence form was named, so a carried or written label went unnamed.

Round 2 (V2-M1): check marks ("... ✓", "✔ ..."), "(checked against the sources)", "(source-checked)", "(accuracy
confirmed)" and verdicts ("Proven correct: ...") are labels too, and the synthesis is read as the combinator's own answer
(``adapters.markdown.is_synthesis_self_certification``): "The synthesis has been verified.", "This synthesis is
correct.", as a claim of its own or written beside a claim's content, are named; a disclaimer or a check credited to
another agent is not.
"""
from __future__ import annotations

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity.ledger import check_synthesis_ledger
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

COMMON = dict(request_id="req", task_id="task", report_id="rep", agent_id="history-specialist", subject="History", task_type="short_answer")
FACT = ClaimRecord(**COMMON, claim_id="h1.1", claim_text="The Treaty of Versailles was signed in June 1919.", claim_role="point")
NOTE = ClaimRecord(**COMMON, claim_id="h2.1", claim_text="VERIFIED: all claims checked and confirmed.", claim_role="other", materiality="supporting",
                   advisory_verification_status="self-certified in the response text")


def _report() -> SpecialistReport:
    body = f"{FACT.claim_text}\n\n{NOTE.claim_text}"
    return SpecialistReport(**COMMON, original_response=body, response_sha256=sha256_text(body), created_at="2026-10-17T00:00:00Z", claims=[FACT, NOTE])


def _synthesis(claims: list[SynthesizedClaim], text: str | None = None) -> Synthesis:
    body = text if text is not None else " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=["rep"], claims=claims,
                     text=body, text_sha256=sha256_text(body), created_at="2026-10-17T00:00:00Z")


def _self_reports(syn: Synthesis):
    return [f for f in check_synthesis_ledger([_report()], syn) if f.code == "INT-LEDGER-029"]


FAITHFUL = SynthesizedClaim(claim_id="y1", text=FACT.claim_text, source_claim_ids=["h1.1"])


@pytest.mark.parametrize("claims,text,named", [
    ([FAITHFUL, SynthesizedClaim(claim_id="y2", text=NOTE.claim_text, source_claim_ids=["h2.1"], transformation="carried")], None, ["y2", "h2.1"]),
    ([SynthesizedClaim(claim_id="y1", text=f"{FACT.claim_text} VERIFIED: all claims checked and confirmed.", source_claim_ids=["h1.1", "h2.1"],
                       transformation="merged")], None, ["y1", "h1.1", "h2.1"]),
    ([FAITHFUL], f"{FACT.claim_text} Every figure here has been checked by the formal verifier.", ["syn"]),
])
def test_a_carried_merged_or_written_self_certification_is_named(claims, text, named):
    [f] = _self_reports(_synthesis(claims, text))
    assert f.severity == "warning" and "self-report" in f.message and f.claim_ids == named and f.agent_ids == ["combinator"]


def test_a_synthesis_that_reports_its_sources_plainly_is_no_self_report():
    assert _self_reports(_synthesis([FAITHFUL])) == []
    plain = f"{FACT.claim_text} The History specialist checks the date against the treaty's text, and the dossier confirms it."
    assert _self_reports(_synthesis([FAITHFUL], plain)) == []


# ------------------------------------------------------------------------- a verification label on a claim's content (M1)

_BARE = FACT.claim_text[:-1]
#: Every label form the combinator verification (round 1, M1) named, and the class around them: in front of the content,
#: after it, inside it, or standing alone in the claim.
LABELLED = {
    "Verified: prefix": "Verified: " + FACT.claim_text,
    "(verified) suffix": _BARE + " (verified).",
    "[verified] prefix": "[verified] " + FACT.claim_text,
    "Checked: prefix": "Checked: " + FACT.claim_text,
    "as formally verified suffix": _BARE + ", as formally verified.",
    "Fact-checked dash prefix": "Fact-checked — " + FACT.claim_text,
    "semicolon suffix": _BARE + "; verified.",
    "as verified by the engine": _BARE + ", as verified by the engine.",
    "bracketed inside": "The Treaty of Versailles (verified) was signed in June 1919.",
    "a label sentence after the content": FACT.claim_text + " (checked)",
    # combinator verification round 2 (V2-M1): before, none of these was named
    "check mark after": _BARE + " ✓",
    "check mark before": "✔ " + FACT.claim_text,
    "check mark with a label": _BARE + " ✓ verified.",
    "checked against the sources": _BARE + " (checked against the sources).",
    "source-checked": _BARE + " (source-checked).",
    "accuracy confirmed": _BARE + " (accuracy confirmed).",
    "verdict in front": "Proven correct: " + FACT.claim_text,
}


@pytest.mark.parametrize("form", list(LABELLED))
@pytest.mark.parametrize("transformation", ["paraphrased", "carried"])
def test_a_verification_label_on_a_synthesized_claims_content_is_named(form, transformation):
    claim = SynthesizedClaim(claim_id="y1", text=LABELLED[form], source_claim_ids=["h1.1"], transformation=transformation)
    [f] = _self_reports(_synthesis([claim]))
    assert f.severity == "warning" and f.claim_ids == ["y1", "h1.1"] and f.agent_ids == ["combinator"], f
    assert "self-report" in f.message and ("label" in f.message or "states a verification status" in f.message), f.message


def test_a_label_on_content_says_the_content_is_still_accounted_for_and_a_whole_self_report_says_it_is_no_content():
    [label] = _self_reports(_synthesis([SynthesizedClaim(claim_id="y1", text="Verified: " + FACT.claim_text, source_claim_ids=["h1.1"],
                                                         transformation="paraphrased")]))
    assert "carries a verification-status label on its content" in label.message and "still accounted for" in label.message
    [whole] = _self_reports(_synthesis([FAITHFUL, SynthesizedClaim(claim_id="y2", text="Verified.", source_claim_ids=["h2.1"], transformation="paraphrased")]))
    assert whole.claim_ids == ["y2", "h2.1"] and "no material content" in whole.message


@pytest.mark.parametrize("text", [
    _BARE + " (not verified).", _BARE + ", as confirmed by the treaty's own text.", _BARE + ", as later confirmed in the Reichstag.",
    "The Treaty of Versailles was, in 1919, checked by no one in Germany.", "Unverified: " + FACT.claim_text,
    _BARE + " (verified by the History specialist).", _BARE + " (not source-checked).", _BARE + " (accuracy not confirmed).", "✗ " + FACT.claim_text,
])
def test_a_disclaimer_or_a_check_credited_to_a_source_is_no_label_in_a_synthesis(text):
    assert _self_reports(_synthesis([SynthesizedClaim(claim_id="y1", text=text, source_claim_ids=["h1.1"], transformation="paraphrased")])) == []


# ------------------------------------------------------------------- the synthesis certifying itself (round 2, V2-M1)

#: The combinator's own product named as the answer: before, the hub read a synthesis with the specialists' rules only, so
#: none of these was named (each claim kept only its unchecked-paraphrase warning).
SYNTHESIS_SELF_REPORTS = ["The synthesis has been verified.", "This synthesis is correct.", "Formally proven correct.",
                          "Every synthesized claim was checked against the sources.", "The combined answer accurately reflects the sources."]


@pytest.mark.parametrize("text", SYNTHESIS_SELF_REPORTS)
def test_a_synthesis_certifying_itself_is_named_as_a_whole_self_report(text):
    claims = [FAITHFUL, SynthesizedClaim(claim_id="y2", text=text, source_claim_ids=["h1.1"], transformation="generalized")]
    [f] = _self_reports(_synthesis(claims))
    assert f.severity == "warning" and f.claim_ids == ["y2", "h1.1"] and "self-report" in f.message and "no material content" in f.message


@pytest.mark.parametrize("text", SYNTHESIS_SELF_REPORTS[:2])
def test_a_self_report_written_beside_a_claims_content_is_named_and_the_content_stays_accounted_for(text):
    claim = SynthesizedClaim(claim_id="y1", text=f"{FACT.claim_text} {text}", source_claim_ids=["h1.1"], transformation="paraphrased")
    [f] = _self_reports(_synthesis([claim]))
    assert f.claim_ids == ["y1", "h1.1"] and "beside its content" in f.message and "still accounted for" in f.message


def test_a_synthesis_text_that_certifies_the_synthesis_is_named():
    [f] = _self_reports(_synthesis([FAITHFUL], f"{FACT.claim_text} The synthesis has been verified."))
    assert f.claim_ids == ["syn"] and "self-report" in f.message


@pytest.mark.parametrize("text", ["The synthesis has not been verified.", "The synthesis was checked by the History specialist.",
                                  "The synthesis should be checked against the sources.", "The synthesis of ammonia was confirmed in 1909."])
def test_a_synthesis_disclaiming_a_check_or_crediting_another_agent_is_no_self_report(text):
    claims = [FAITHFUL, SynthesizedClaim(claim_id="y2", text=text, source_claim_ids=["h1.1"], transformation="generalized")]
    assert _self_reports(_synthesis(claims)) == []
