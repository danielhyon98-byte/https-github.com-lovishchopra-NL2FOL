"""Integration gate 1, harness handoff 1: the hub holds the combinator port's text and citation rules on every path.

A synthesis the combinator's runner and the port refuse (KIT-CB-002: a control character, a bidirectional override, a blank
text, a claim citing one source twice) was delivered by the hub, whose synthesis contract checked lengths only: relayed
through ``TranslatorChannel.relay`` a dropped reason holding ``"\\x1b[2J\\x07\\u202e"`` was ACCEPTED with no finding, and a
bidirectional override could make the text a reader sees differ from the text the hub checked. The contract now holds the
port's rule (``integrity.contracts.SYNTHESIS_TEXT_PATTERN``, which ``integration.combinator_port.TEXT_PATTERN`` is) on a
synthesized claim's text, a ledger entry's reason, a conflict's description and basis and the student-facing text, and a
synthesized claim cites each source claim once. Such a synthesis is REJECTED with INT-REQ-009 stating the rule broken, never
the text, whether it is relayed as JSON or as an object built around validation. Controls: a tab, a line break, accented and
non-Latin text are delivered unchanged.
"""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.integration import combinator_port
from epinoic_logic.integrity import AgentRole, Synthesis, WorkPlan
from epinoic_logic.integrity.contracts import (SYNTHESIS_CITATION_RULE, SYNTHESIS_TEXT_PATTERN, ConflictRecord, LedgerEntry, SynthesizedClaim)
from epinoic_logic.translate.contracts import sha256_text

KEY = b"integration-gate-1-synthesis-text-key-01"
COMBINATOR = "dummy-combinator"
TEXT = ("London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801. "
        "Coal smoke from homes and workshops hung over the city for much of the year.")


def channel() -> tuple[TranslatorChannel, list]:
    plan = WorkPlan(plan_id="plan-t", request_id="req-t", task_id="task-t", subject="History", task_type="short_answer",
                    selected_agent_ids=["history-specialist", COMBINATOR])
    ch = TranslatorChannel(plan, signing_key=KEY)
    request_msg, _req, rr = ch.request("router", "history-specialist", "Outline the context of London in 1802 in one paragraph.")
    assert rr.status is TransmissionStatus.ACCEPTED
    msg, rc = ch.respond_text(request_msg.message_id, TEXT, agent_id="history-specialist", report_id="rep-t")
    assert msg is not None, rc.summary
    return ch, list(ch.transmitted_reports["rep-t"].claims)


def mapping(claims: list[dict[str, Any]], *, ledger: list | None = None, conflicts: list | None = None, text: str | None = None) -> dict[str, Any]:
    text = text if text is not None else " ".join(c["text"] for c in claims)
    return {"synthesis_id": "syn-t", "request_id": "req-t", "task_id": "task-t", "combinator_agent_id": COMBINATOR,
            "source_report_ids": ["rep-t"], "claims": claims, "ledger": ledger or [], "conflicts": conflicts or [],
            "text": text, "text_sha256": sha256_text(text), "created_at": "2026-10-31T15:00:00Z"}


def relay(ch: TranslatorChannel, payload):
    return ch.relay(COMBINATOR, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)


def around_validation(data: dict[str, Any]) -> Synthesis:
    """The same synthesis as an object built around validation (``model_construct``): no validator ran on it."""
    claims = [SynthesizedClaim.model_construct(**c) for c in data["claims"]]
    ledger = [LedgerEntry.model_construct(**e) for e in data["ledger"]]
    conflicts = [ConflictRecord.model_construct(**c) for c in data["conflicts"]]
    return Synthesis.model_construct(**{**data, "claims": claims, "ledger": ledger, "conflicts": conflicts})


def _cases(claims) -> dict[str, dict[str, Any]]:
    a, b = claims[0], claims[1]
    good_b = {"claim_id": "s1", "text": b.claim_text, "source_claim_ids": [b.claim_id], "transformation": "carried"}

    def with_text(t: str) -> dict[str, Any]:
        return mapping([{"claim_id": "s0", "text": t, "source_claim_ids": [a.claim_id], "transformation": "paraphrased"}, good_b],
                       text=a.claim_text + " " + b.claim_text)

    def with_reason(r: str) -> dict[str, Any]:
        return mapping([good_b], ledger=[{"source_claim_ids": [a.claim_id], "transformation": "dropped", "reason": r}])

    def with_conflict(desc: str, basis: str | None = None) -> dict[str, Any]:
        c = {"conflict_id": "k1", "claim_ids": [a.claim_id, b.claim_id], "description": desc}
        if basis is not None:
            c.update(status="resolved_with_basis", basis=basis)
        return mapping([{"claim_id": "s0", "text": a.claim_text, "source_claim_ids": [a.claim_id], "transformation": "carried"}, good_b], conflicts=[c])

    return {
        "text ending in NUL and RLO": with_text(a.claim_text + "\x00‮"),
        "text holding bell and escape": with_text("London \x07\x1b[2J was large."),
        "text starting with RLO": with_text("‮" + a.claim_text),
        "text holding LRI": with_text("London ⁦was large."),
        "blank text": with_text("   "),
        "dropped reason with controls": with_reason("context \x1b[2J\x07‮"),
        "blank dropped reason": with_reason("   "),
        "blank conflict description": with_conflict("   "),
        "overridden conflict description": with_conflict("‮the figures disagree"),
        "overridden conflict basis": with_conflict("the figures disagree", basis="‮the census rules"),
        "merged claim citing one source twice": mapping([{"claim_id": "s0", "text": a.claim_text, "source_claim_ids": [a.claim_id, a.claim_id],
                                                          "transformation": "merged"}, good_b]),
        "student text holding a bell": mapping([good_b], text=b.claim_text + "\x07"),
    }


#: The forms the port refuses (KIT-CB-002) that the hub delivered before this fix, by name (built per channel by ``_cases``).
NAMES = ["text ending in NUL and RLO", "text holding bell and escape", "text starting with RLO", "text holding LRI", "blank text",
         "dropped reason with controls", "blank dropped reason", "blank conflict description", "overridden conflict description",
         "overridden conflict basis", "merged claim citing one source twice", "student text holding a bell"]


@pytest.mark.parametrize("form", ["mapping", "object built around validation"])
@pytest.mark.parametrize("name", NAMES)
def test_a_synthesis_outside_the_text_or_citation_rule_is_rejected_on_every_path(name, form):
    ch, claims = channel()
    data = _cases(claims)[name]
    with pytest.raises(ValidationError):
        Synthesis.model_validate(data)  # the contract itself refuses it
    payload = data if form == "mapping" else around_validation(data)
    msg, rc = relay(ch, payload)
    assert msg is None and rc.status is TransmissionStatus.REJECTED, (name, form, rc.status, rc.summary)
    req009 = [f for f in rc.findings if f.code == "INT-REQ-009"]
    assert req009 and req009[0].severity == "error", rc.findings
    rule = SYNTHESIS_CITATION_RULE if "twice" in name else "the synthesis text rule"
    assert rule in req009[0].message, req009[0].message
    for bad in ("\x00", "\x07", "\x1b", "‮", "⁦"):
        assert bad not in req009[0].message and bad not in rc.summary  # the rule is stated, never the text
    assert "syn-t" not in ch.syntheses


@pytest.mark.parametrize("form", ["mapping", "object"])
@pytest.mark.parametrize("text", ["London in 1802\twas the largest city in Europe.\nIt had close to a million inhabitants.",
                                  "Londres était la plus grande ville d'Europe en 1802.", "1802 年的伦敦是欧洲最大的城市。"])
def test_control_tabs_line_breaks_accents_and_non_latin_text_are_delivered_unchanged(text, form):
    ch, claims = channel()
    a = claims[0]
    data = mapping([{"claim_id": "s0", "text": text, "source_claim_ids": [a.claim_id], "transformation": "paraphrased"}])
    payload = data if form == "mapping" else Synthesis.model_validate(data)
    msg, rc = relay(ch, payload)
    assert msg is not None and rc.status is not TransmissionStatus.REJECTED, rc.summary
    assert not [f for f in rc.findings if f.code == "INT-REQ-009"]
    assert ch.syntheses["syn-t"].claims[0].text == text


def test_the_port_and_the_hub_hold_one_text_rule():
    assert combinator_port.TEXT_PATTERN == SYNTHESIS_TEXT_PATTERN
    for field, model in (("text", SynthesizedClaim), ("reason", LedgerEntry), ("description", ConflictRecord), ("basis", ConflictRecord), ("text", Synthesis)):
        meta = model.model_fields[field].metadata
        assert any(getattr(m, "pattern", None) == SYNTHESIS_TEXT_PATTERN for m in meta), (model.__name__, field, meta)
    assert LedgerEntry(source_claim_ids=["a"], transformation="dropped").reason is None  # a missing reason stays INT-LEDGER-006's
