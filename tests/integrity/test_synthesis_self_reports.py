"""INT-LEDGER-029: a synthesis that states a verification status of the answer is a self-report, whoever wrote it.

The combinator sub-project's instructions say never to carry a note, a self-certification, a decline or a question back
as a claim; the hub, the independent checker of every synthesis, names it when one is carried anyway: copied from a
specialist's note, merged into a factual claim, or written only into the student-facing text. The rule (ported here
unchanged from the argument-diagnosis work, combinator-faults-3) reads the specialists' closed self-certification
vocabulary (``adapters.markdown.is_self_certification``), so a synthesis that reports its sources plainly is no
self-report.
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
