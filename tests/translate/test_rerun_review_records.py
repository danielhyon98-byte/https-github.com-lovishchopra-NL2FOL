"""Re-run review findings in the translation records and their outcome.

* correctness-5: a translation record from before contract 0.2 (translator 0.3.0, no claim_text_sha256, coverage,
  grounding support, figure readings, repairs or task digest) was trusted: re-verified and bound to a faithful review it
  displayed ENTAILED and permitted release, although contract section 9 says such a record must be translated and
  verified again. A record this translator did not make is now INTERNAL_ERROR whatever its status, and never released.
* robustness-and-contracts-12: the items of a report's note lists (assumptions, unresolved issues, a claim's assumptions
  and assessment criteria) had no length bound, so a 10 MB assumption or a 64 MB report was delivered ACCEPTED. Each item
  and the notes together are now bounded by the contract, and an oversized report is REJECTED with INT-REQ-009.
* security-5, the same class in the report contract: ``course_level`` is optional with the default ``"unknown"``, so a
  report or claim stating ``None`` lost the key in its canonical dump and read back as ``"unknown"``: the delivered report
  re-read from its own payload differed from the report delivered, and its faithful forward was REJECTED as altered in
  transit (INT-HANDOFF-013). A stated ``None`` is now read as ``"unknown"``, so a record reads back as it was written.

These results prove properties of the encoding and of this code only.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.integrity.contracts import AgentRole
from epinoic_logic.translate.contracts import (
    NOTE_MAX_CHARS,
    REPORT_NOTES_MAX_CHARS,
    ClaimRecord,
    SpecialistReport,
    SuppliedText,
    TranslationStatus as T,
    sha256_text,
)
from epinoic_logic.translate.outcome import compose_outcome, display_status_for, translation_staleness, verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer
from epinoic_logic.version import TRANSLATOR_VERSION

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"rerun-review-records-key-01234567"
TEXT = "x is 0.33 to 2 decimal places."
IDS = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Mathematics", task_type="algebra")


def V(n):
    return {"op": "var", "name": n}


def R(v):
    return {"op": "real", "value": str(v)}


def _case():
    """The finding's case: a current translation that is released ENTAILED (the control)."""
    support = ClaimRecord(**IDS, claim_id="s0", claim_text=TEXT, claim_role="evidence")
    claim = ClaimRecord(**IDS, claim_id="c", claim_text="Given the stated value of x, x is less than 1/2.", claim_role="quantitative",
                        proposed_claim_kind="arithmetic", supporting_claim_ids=["s0"])
    body = claim.claim_text + " " + TEXT
    report = SpecialistReport(**IDS, original_response=body, response_sha256=sha256_text(body), claims=[claim, support],
                              supplied_texts=[SuppliedText(document_id="task", text=TEXT)], created_at="2026-10-16T00:00:00Z")
    problem = {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": [{"name": "x", "sort": "Real"}],
               "premises": [{"id": "P", "expr": {"op": "eq", "left": V("x"), "right": R("0.33")}, "label": TEXT,
                             "grounding": {"kind": "task_setting", "source_refs": [{"document_id": "task", "excerpt": TEXT}]}}],
               "conclusion": {"id": "C", "expr": {"op": "lt", "left": V("x"), "right": R("1/2")}, "label": "x is less than one half"}}
    output = {"problem": problem, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}
    reviewer = SemanticReviewer(FixtureReviewProvider({"c": {"verdict": "faithful", "issues": []}}))
    current = verify_claim(claim, report, Translator(FixtureTranslationProvider({"c": [output]}), config=CFG), reviewer, config=CFG,
                           signing_key=KEY, key_id="k")
    return claim, report, reviewer, current


def _recompose(claim, report, reviewer, translation):
    result = verify(translation.problem, CFG, signing_key=KEY, key_id="k")
    review = reviewer.review(claim, translation, report=report)
    return compose_outcome(claim, translation, result, review, signing_key=KEY, key_id="k", report=report)


def test_a_current_record_is_displayed_and_released():
    """Control: the record this translator made, re-verified and reviewed, is ENTAILED and released."""
    claim, report, reviewer, current = _case()
    assert current.translation.translator_version == TRANSLATOR_VERSION and current.translation.claim_text_sha256 is not None
    assert translation_staleness(current.translation) is None
    assert current.display_status is S.ENTAILED and current.release.permitted
    again = _recompose(claim, report, reviewer, current.translation)
    assert again.display_status is S.ENTAILED and again.release.permitted


def test_a_record_from_before_contract_0_2_must_be_translated_again():
    """The finding's reproduction: the same record with translator 0.3.0 and the 0.2 fields cleared."""
    claim, report, reviewer, current = _case()
    old = current.translation.model_copy(update={"translator_version": "0.3.0", "claim_text_sha256": None, "grounding_support": [], "figure_readings": [],
                                                 "coverage": [], "repairs": [], "task_sha256": None})
    outcome = _recompose(claim, report, reviewer, old)
    assert outcome.display_status is S.INTERNAL_ERROR and not outcome.release.permitted
    assert any(u.startswith("translation record not current") for u in outcome.release.unresolved)
    assert "Translation record not current" in outcome.summary and "0.3.0" in outcome.summary
    assert outcome.named_diagnostics == [] or all(d.layer != "engine" for d in outcome.named_diagnostics)  # the engine result is not trusted


@pytest.mark.parametrize("update", [{"translator_version": "0.4.0"}, {"claim_text_sha256": None}, {"translator_version": "t"}],
                         ids=["an earlier translator", "no claim-text digest", "an unknown translator label"])
def test_any_record_this_translator_did_not_make_is_internal_error(update: dict):
    claim, report, reviewer, current = _case()
    record = current.translation.model_copy(update=update)
    assert translation_staleness(record) is not None
    assert display_status_for(record, current.verification, KEY, "k") is S.INTERNAL_ERROR
    outcome = _recompose(claim, report, reviewer, record)
    assert outcome.display_status is S.INTERNAL_ERROR and not outcome.release.permitted


@pytest.mark.parametrize("status", [T.NOT_ELIGIBLE, T.AMBIGUOUS_TRANSLATION, T.INVALID_FORMALIZATION, T.UNSUPPORTED])
def test_an_old_record_of_any_status_is_internal_error_and_a_current_one_keeps_its_status(status: T):
    claim, report, reviewer, current = _case()
    record = current.translation.model_copy(update={"status": status})
    assert display_status_for(record, None) is not S.INTERNAL_ERROR  # control: the current record keeps its own display
    old = record.model_copy(update={"translator_version": "0.3.0", "claim_text_sha256": None})
    assert display_status_for(old, None) is S.INTERNAL_ERROR


# ============================================================================ robustness-and-contracts-12

CLAIM_TEXT = "The crash of 1929 followed speculative excess."


def _report_dict(**over) -> dict:
    claim = dict(request_id="rq", task_id="t", report_id="rep1", agent_id="history-specialist", subject="History", task_type="short_answer",
                 claim_id="c1", claim_text=CLAIM_TEXT, claim_role="point")
    claim.update(over.pop("claim", {}))
    data = dict(report_id="rep1", request_id="rq", task_id="t", agent_id="history-specialist", subject="History", task_type="short_answer",
                original_response=CLAIM_TEXT, response_sha256=sha256_text(CLAIM_TEXT), supplied_texts=[], created_at="2026-10-11T11:00:00Z",
                claims=[claim])
    data.update(over)
    return data


@pytest.mark.parametrize("over", [
    {"assumptions": ["x" * (NOTE_MAX_CHARS + 1)]},
    {"unresolved_issues": ["y" * (NOTE_MAX_CHARS + 1)]},
    {"claim": {"assumptions": ["z" * (NOTE_MAX_CHARS + 1)]}},
    {"claim": {"assessment_criteria": ["w" * (NOTE_MAX_CHARS + 1)]}},
], ids=["report assumption", "unresolved issue", "claim assumption", "assessment criterion"])
def test_an_overlong_note_is_refused_by_the_contract(over: dict):
    with pytest.raises(ValidationError):
        SpecialistReport.model_validate(_report_dict(**over))


def test_notes_beyond_the_reports_total_are_refused():
    """64 assumptions within the item bound would still allow far more than the response bound: the total is bounded."""
    per_claim = ["n" * NOTE_MAX_CHARS] * 32
    claims = [dict(request_id="rq", task_id="t", report_id="rep1", agent_id="history-specialist", subject="History", task_type="short_answer",
                   claim_id=f"c{i}", claim_text=CLAIM_TEXT, claim_role="point", assumptions=per_claim) for i in range(4)]
    assert 4 * 32 * NOTE_MAX_CHARS > REPORT_NOTES_MAX_CHARS
    with pytest.raises(ValidationError):
        SpecialistReport.model_validate(_report_dict(claims=claims))


def test_notes_at_the_bounds_are_accepted():
    """Control: an item at the bound, and notes up to the total, are a valid report."""
    report = SpecialistReport.model_validate(_report_dict(assumptions=["x" * NOTE_MAX_CHARS], unresolved_issues=["y" * NOTE_MAX_CHARS],
                                                           claim={"assumptions": ["z" * NOTE_MAX_CHARS], "assessment_criteria": ["w" * NOTE_MAX_CHARS]}))
    assert len(report.assumptions[0]) == NOTE_MAX_CHARS


def _hub():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="pl", request_id="rq", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"]))
    return hub


@pytest.mark.parametrize("over", [{"assumptions": ["x" * 10_000_000]}, {"assumptions": ["y" * 1_000_000] * 64},
                                  {"claim": {"assumptions": ["z" * 10_000_000], "assessment_criteria": ["w" * 5_000_000]}}],
                         ids=["10 MB assumption", "64 MB of assumptions", "15 MB in a claim"])
def test_an_oversized_report_is_rejected_by_the_hub_not_delivered(over: dict):
    """The finding's reproduction through RouterHub.receive: each was ACCEPTED and held in transmitted_reports."""
    hub = _hub()
    message, _req, _rc = hub.dispatch("t", "history-specialist", "Explain the 1929 crash.")
    reply, receipt = hub.receive("t", message.message_id, _report_dict(**over))
    assert reply is None and receipt.status is TransmissionStatus.REJECTED and [f.code for f in receipt.findings] == ["INT-REQ-009"]
    assert hub.channels["t"].transmitted_reports == {}


def test_a_normal_report_and_a_parsed_answer_with_notes_are_still_delivered():
    """Controls: the same report without the oversized notes, and a raw answer whose parser writes notes, are delivered."""
    hub = _hub()
    message, _req, _rc = hub.dispatch("t", "history-specialist", "Explain the 1929 crash.")
    reply, receipt = hub.receive("t", message.message_id, _report_dict(assumptions=["the dates are from memory"]))
    assert reply is not None and receipt.status is not TransmissionStatus.REJECTED
    message2, _req2, _rc2 = hub.dispatch("t", "history-specialist", "Explain the 1929 crash.")
    raw = ("The crash of 1929 followed speculative excess (from memory: c. 1929). Margin buying had \"inflated prices\" for years; "
           "banks failed in waves. Note: dates are from memory.")
    reply2, receipt2 = hub.receive("t", message2.message_id, raw, agent_id="history-specialist", report_id="rep2")
    assert reply2 is not None and receipt2.status is not TransmissionStatus.REJECTED


# ============================================================================ security-5, the same class in the report contract


@pytest.mark.parametrize("model", ["report", "claim"])
def test_a_record_stating_no_course_level_reads_back_as_it_was_written(model: str):
    report = SpecialistReport.model_validate(_report_dict(course_level=None, claim={"course_level": None}))
    record = report if model == "report" else report.claims[0]
    again = type(record).model_validate(record.model_dump(mode="json", exclude_none=True))
    assert again == record and again.course_level == record.course_level == "unknown"


@pytest.mark.parametrize("level", ["SL", "HL", "unknown"])
def test_a_stated_course_level_is_kept_as_stated(level: str):
    """Control: only ``None`` is read as ``"unknown"``; a stated level is the level, and an absent one is the default."""
    report = SpecialistReport.model_validate(_report_dict(course_level=level, claim={"course_level": level}))
    assert report.course_level == report.claims[0].course_level == level
    assert SpecialistReport.model_validate(_report_dict()).course_level == "unknown"


def _relay_hub():
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="pl", request_id="rq", task_id="t", subject="History", task_type="short_answer",
                                selected_agent_ids=["history-specialist", "dummy-combinator"]))
    return hub, ch


def test_a_faithful_forward_of_a_report_stating_no_course_level_is_carried():
    """The reproduction: the report is delivered, then the copy read back from the delivered payload (what a router or a
    combinator holds) is forwarded unchanged. Before, that copy read "unknown" where the delivered report held None, and the
    forward was REJECTED as altered in transit (INT-HANDOFF-013)."""
    hub, ch = _relay_hub()
    message, _req, _rc = hub.dispatch("t", "history-specialist", "Explain the 1929 crash.")
    report = SpecialistReport.model_validate(_report_dict(course_level=None, claim={"course_level": None}))
    reply, receipt = hub.receive("t", message.message_id, report)
    assert reply is not None and receipt.status is not TransmissionStatus.REJECTED
    held = SpecialistReport.model_validate(reply.payload)
    forwarded, relay = ch.relay("router", AgentRole.ROUTER, "dummy-combinator", AgentRole.COMBINATOR, held, in_reply_to=reply.message_id)
    assert forwarded is not None and "INT-HANDOFF-013" not in [f.code for f in relay.findings], [f.model_dump() for f in relay.findings]


def test_a_forward_that_alters_the_course_level_is_still_refused():
    """Control: the transit check is unchanged; a copy whose level differs from the delivered report is altered in transit."""
    hub, ch = _relay_hub()
    message, _req, _rc = hub.dispatch("t", "history-specialist", "Explain the 1929 crash.")
    reply, _receipt = hub.receive("t", message.message_id, SpecialistReport.model_validate(_report_dict(course_level=None)))
    altered = SpecialistReport.model_validate(reply.payload).model_copy(update={"course_level": "HL"})
    forwarded, relay = ch.relay("router", AgentRole.ROUTER, "dummy-combinator", AgentRole.COMBINATOR, altered, in_reply_to=reply.message_id)
    assert forwarded is None and "INT-HANDOFF-013" in [f.code for f in relay.findings]
