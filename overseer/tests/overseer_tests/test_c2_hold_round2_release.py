"""Hold-fix round 2 of the round-9 push-check hold on the c2 clearance commit: every release path applies rule
``self-certification-gate`` with the translator's one self-report reader.

The paths lens reproduced two release paths that never read the gate: the combined answer (the channel's relay of a
synthesis, then ``policy.release_decision`` on the FINAL task audit) released a synthesis that carried "All calculations have
been verified by the system and are confirmed." (INT-LEDGER-029 at warning severity, or no finding at all when the combinator
wrote the claim itself), and the overseer port's consolidated delivery, which the service's turn check (POST /v1/turns/check)
reads, delivered a single answer whose receipt named its CORE-SELF-001 at warning severity. These tests pin:

* the combined answer: a synthesis carrying a self-report, carried from a specialist or written by the combinator, in a claim or
  in the student-facing text alone, is never released, and the clean synthesis still is (the control);
* the consolidated delivery of the port (single mode) is pinned in ``tests/integration/test_c2_hold_round2_turn_check.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import tamper as T  # noqa: E402
from epinoic_logic.api.integrity import SynthesizedClaim  # noqa: E402
from epinoic_overseer.meta_notes import payload_self_reports  # noqa: E402
from epinoic_overseer.policy import release_decision  # noqa: E402

PHRASES = ["All calculations have been verified by the system and are confirmed.", "All calculations confirmed.",
           "The calculations were verified.", "These statistics were checked by the AI verification engine.",
           "Nothing above needs correcting; all of it was checked.", "Self-check: passed.",
           "The calculations above: all verified by the system and confirmed."]


def _release(run, audit):
    a = run.auditor
    return release_decision(run.receipts["syn"], audit, a.keyring, audits=a.audits(run.uid), journal=a.journal(run.uid), message=run.messages.get("syn"))


def _run(**kw):
    a = H.new_auditor(H.keyring_for("synthetic"), shadow="off", inline_final_release=True)
    run = T.run_synthetic(a, **kw)
    return a, run


def test_control_the_clean_synthesis_is_released():
    a, run = _run()
    try:
        d = _release(run, run.audit(final=True))
        assert d.allowed, d.reason
    finally:
        a.close()


@pytest.mark.parametrize("sentence", PHRASES)
def test_a_carried_self_report_is_never_released(sentence):
    claims = list(T.default_synthesis().claims) + [SynthesizedClaim(claim_id="s4", text=sentence, source_claim_ids=["h1.1"], transformation="carried")]
    a, run = _run(synthesis=T.default_synthesis(claims=claims))
    try:
        d = _release(run, run.audit(final=True))
        # never released: by the gate, or earlier by an error-level finding of the ledger (a carried text that is not its source's)
        assert not d.allowed and ("self-certification-gate" in d.reason or "error-level" in d.reason), d.reason
        assert sentence[:18] not in d.reason  # named by code or place, never by its words
    finally:
        a.close()


@pytest.mark.parametrize("sentence", PHRASES)
def test_a_self_report_the_combinator_wrote_is_never_released(sentence):
    claims = list(T.default_synthesis().claims) + [SynthesizedClaim(claim_id="s4", text=sentence, source_claim_ids=["h1.3"], transformation="narrowed")]
    a, run = _run(synthesis=T.default_synthesis(claims=claims))
    try:
        d = _release(run, run.audit(final=True))
        assert not d.allowed and "self-certification-gate" in d.reason, d.reason
    finally:
        a.close()


def test_the_payload_reader_names_a_self_report_in_the_student_facing_text_alone():
    payload = T.default_synthesis().model_dump(mode="json")
    assert payload_self_reports(payload) == []
    payload["text"] += "\n\nAll calculations have been verified by the system and are confirmed."
    assert payload_self_reports(payload) == ["paragraph 2 of the synthesis text"]
    assert payload_self_reports(None) == ["the payload as a whole (it could not be read)"]


@pytest.mark.parametrize("sentence", PHRASES[:3])
def test_a_specialist_self_report_carried_into_a_history_answer_blocks_the_release(sentence):
    """The lens's case: the History answer itself ends with the self-report (h2.1), and the synthesis carries it."""
    hi_text = T.HI_TEXT + "\n\n" + sentence
    claims = list(T.default_synthesis().claims) + [SynthesizedClaim(claim_id="s4", text=sentence, source_claim_ids=["h2.1"], transformation="carried")]
    a, run = _run(hi_text=hi_text, synthesis=T.default_synthesis(claims=claims))
    try:
        d = _release(run, run.audit(final=True))
        assert not d.allowed, d.reason
    finally:
        a.close()
