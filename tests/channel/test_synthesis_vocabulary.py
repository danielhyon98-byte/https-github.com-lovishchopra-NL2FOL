"""The combinator's synthesis at the channel boundary: a value outside the synthesis contract's closed vocabularies.

End-to-end simulation of 16 October 2026 (bug 7): the combinator described its edits in ``transformation`` instead of
naming one of the documented values ("Verdict (s1.1) and reason (s1.2) joined with the formula, the sum and the rounding
(s3.1 to s3.3); figures verbatim."), in all 62 synthesized claims of the 14 syntheses. The arena built the contract
models itself and raised a pydantic ValidationError before the hub saw anything; over the hub, the same synthesis as JSON
was refused with a bare INT-REQ-009 ("claims.0.transformation: literal_error"), and a Synthesis object built around
validation (``model_copy``) with such a value was DELIVERED, its value-specific ledger rules silently skipped.

Pinned here:

* a synthesis mapping with a value outside a closed vocabulary (transformation, certainty, materiality, a ledger
  entry's transformation, a conflict's status) is REJECTED with INT-REQ-009 and INT-SYNTH-014, which names every such
  item and the rule it broke, quotes a one-word value and describes free text only by its length; nothing is stored and
  nothing raises;
* a Synthesis object built around validation is re-validated and refused the same way (no longer delivered);
* every documented transformation still validates and is delivered; a valid synthesis gets the same receipt codes as a
  mapping and as an object (negative controls);
* the documented vocabulary (``TRANSFORMATION_MEANINGS``) is exactly the contract's ``Transformation`` and the values a
  combinator is told to use exclude 'new' and 'dropped'.
"""
from __future__ import annotations

from typing import Any, get_args

import pytest

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.integrity.contracts import SYNTHESIZED_CLAIM_TRANSFORMATIONS, TRANSFORMATION_MEANINGS, Transformation
from epinoic_logic.translate.contracts import sha256_text

KEY = b"synthesis-vocabulary-key-0123456789"
COMBINATOR = "dummy-combinator"
TEXT = ("London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801. "
        "Coal smoke from homes and workshops hung over the city for much of the year.")
#: Four transformations the e2e combinator wrote (run1/syntheses/bi-e1.json and others), verbatim.
E2E_FREE_TEXT = [
    "Verdict (s1.1) and reason (s1.2) joined with the formula, the sum and the rounding (s3.1 to s3.3); figures verbatim.",
    "Ratio (s2.1) joined to its expected counts (s2.2); no figure changed.",
    "Part (c) working in source order; 7.815 and p = 0.05 verbatim.",
    "Parts (d) and (e) joined; s6.2 and s6.3 are non-eligible interpretive claims carried as written, not checked.",
]


def channel() -> tuple[TranslatorChannel, list]:
    plan = WorkPlan(plan_id="plan-v", request_id="req-v", task_id="task-v", subject="History", task_type="short_answer",
                    selected_agent_ids=["history-specialist", COMBINATOR])
    ch = TranslatorChannel(plan, signing_key=KEY)
    request_msg, _req, rr = ch.request("router", "history-specialist", "Outline the context of London in 1802 in one paragraph.")
    assert rr.status is TransmissionStatus.ACCEPTED
    msg, rc = ch.respond_text(request_msg.message_id, TEXT, agent_id="history-specialist", report_id="rep-v")
    assert msg is not None, rc.summary
    return ch, list(ch.transmitted_reports["rep-v"].claims)


def mapping(claims: list[dict[str, Any]], *, synthesis_id: str = "syn-v", ledger: list | None = None, conflicts: list | None = None) -> dict[str, Any]:
    text = " ".join(c["text"] for c in claims if isinstance(c.get("text"), str)) or "(empty)"
    return {"synthesis_id": synthesis_id, "request_id": "req-v", "task_id": "task-v", "combinator_agent_id": COMBINATOR,
            "source_report_ids": ["rep-v"], "claims": claims, "ledger": ledger or [], "conflicts": conflicts or [],
            "text": text, "text_sha256": sha256_text(text), "created_at": "2026-10-11T15:00:00Z"}


def carried(claim, sid: str = "s0", **extra) -> dict[str, Any]:
    return {"claim_id": sid, "text": claim.claim_text, "source_claim_ids": [claim.claim_id], "transformation": "carried", **extra}


def relay(ch: TranslatorChannel, payload):
    return ch.relay(COMBINATOR, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)


def codes(receipt) -> list[str]:
    return sorted({f.code for f in receipt.findings})


# =========================================================================== the e2e shape


def test_the_e2e_free_text_transformations_are_a_named_rejection_not_an_exception():
    ch, claims = channel()
    syn = mapping([carried(claims[i % len(claims)], f"s{i}", transformation=t) for i, t in enumerate(E2E_FREE_TEXT)])
    relayed, rc = relay(ch, syn)
    assert relayed is None and rc.status is TransmissionStatus.REJECTED
    assert codes(rc) == ["INT-REQ-009", "INT-SYNTH-014"]
    named = next(f for f in rc.findings if f.code == "INT-SYNTH-014")
    assert named.severity == "error" and named.claim_ids == ["s0", "s1", "s2", "s3"] and named.agent_ids == [COMBINATOR]
    for i, t in enumerate(E2E_FREE_TEXT):
        assert f"synthesized claim s{i}: transformation free text of {len(t)} characters" in named.message
        assert t not in named.message and t[:30] not in named.message, "the agent's free text is never echoed into the receipt"
    for value in SYNTHESIZED_CLAIM_TRANSFORMATIONS:
        assert value in named.message
    assert "never a description of the edit" in named.message and "not delivered (INT-REQ-009)" in named.message
    assert named.message_ids and named.message_ids == next(f for f in rc.findings if f.code == "INT-REQ-009").message_ids
    assert "syn-v" not in ch.syntheses, "a refused synthesis is never held"
    assert "Findings: INT-REQ-009, INT-SYNTH-014." in rc.summary


@pytest.mark.parametrize("value", ["joined", "Merged", "verbatim", "carried ", "paraphrase", "NEW"])
def test_an_alias_or_another_spelling_is_refused_and_quoted(value):
    ch, claims = channel()
    _relayed, rc = relay(ch, mapping([carried(claims[0], transformation=value)]))
    assert rc.status is TransmissionStatus.REJECTED and "INT-SYNTH-014" in codes(rc)
    named = next(f for f in rc.findings if f.code == "INT-SYNTH-014")
    shown = repr(value) if value.strip() == value else f"free text of {len(value)} characters"
    assert f"synthesized claim s0: transformation {shown}" in named.message


def test_every_closed_vocabulary_of_the_synthesis_contract_is_named_with_its_rule():
    ch, claims = channel()
    syn = mapping([carried(claims[0], certainty="high"), carried(claims[1], "s1", materiality="core"), carried(claims[0], "s2", transformation=3)],
                  ledger=[{"source_claim_ids": [claims[1].claim_id], "transformation": "left out on purpose"}],
                  conflicts=[{"conflict_id": "k1", "claim_ids": [claims[0].claim_id, claims[1].claim_id], "description": "x", "status": "settled"}])
    _relayed, rc = relay(ch, syn)
    assert rc.status is TransmissionStatus.REJECTED and codes(rc) == ["INT-REQ-009", "INT-SYNTH-014"]
    named = next(f for f in rc.findings if f.code == "INT-SYNTH-014")
    msg = named.message
    assert "synthesized claim s0: certainty 'high'" in msg and "certainty is one of established, probable, possible" in msg
    assert "synthesized claim s1: materiality 'core'" in msg and "materiality is one of material, supporting" in msg
    assert "synthesized claim s2: transformation a value of type int" in msg
    assert f"ledger[0] (source claims {claims[1].claim_id}): transformation free text of 19 characters" in msg
    assert "a ledger entry's transformation is one of carried, paraphrased, merged, narrowed, generalized, new, dropped" in msg
    assert "conflict k1: status 'settled'" in msg and "a conflict record's status is one of unresolved, resolved_with_basis" in msg
    assert named.claim_ids == ["s0", "s1", "s2", claims[1].claim_id]


def test_a_contract_failure_outside_the_vocabularies_stays_a_plain_int_req_009():
    """Negative control: INT-SYNTH-014 names only closed-vocabulary values; a missing text is the generic contract error."""
    ch, claims = channel()
    claim = carried(claims[0])
    del claim["text"]
    _relayed, rc = relay(ch, mapping([claim]))
    assert rc.status is TransmissionStatus.REJECTED and codes(rc) == ["INT-REQ-009"]
    assert "claims.0.text: missing" in rc.findings[-1].message


@pytest.mark.parametrize("payload", ["Verdict joined; figures verbatim.", ["s0"], 42, None])
def test_a_combinator_output_that_is_no_mapping_is_refused_with_a_receipt(payload):
    ch, _claims = channel()
    relayed, rc = relay(ch, payload)
    assert relayed is None and rc.status is TransmissionStatus.REJECTED and codes(rc) == ["INT-REQ-009"]


# =========================================================================== objects built around validation


def valid_synthesis(claims, transformation: str = "carried") -> Synthesis:
    c = claims[0]
    return Synthesis(synthesis_id="syn-o", request_id="req-v", task_id="task-v", combinator_agent_id=COMBINATOR, source_report_ids=["rep-v"],
                     claims=[SynthesizedClaim(claim_id="s0", text=c.claim_text, source_claim_ids=[c.claim_id], transformation=transformation)],
                     text=c.claim_text, text_sha256=sha256_text(c.claim_text), created_at="2026-10-11T15:00:00Z")


def test_a_synthesis_object_built_around_validation_is_refused_not_delivered():
    """Before the fix this synthesis was ACCEPTED_WITH_FINDINGS and delivered: model_copy does not validate, so the free
    text reached the ledger, whose rules for 'carried' (one source, identical text) never ran."""
    ch, claims = channel()
    syn = valid_synthesis(claims)
    bad = syn.model_copy(update={"claims": [syn.claims[0].model_copy(update={"transformation": E2E_FREE_TEXT[0]})]})
    relayed, rc = relay(ch, bad)
    assert relayed is None and rc.status is TransmissionStatus.REJECTED
    assert codes(rc) == ["INT-REQ-009", "INT-SYNTH-014"]
    plain = next(f for f in rc.findings if f.code == "INT-REQ-009")
    assert "does not re-validate against the synthesis contract" in plain.message and plain.claim_ids == ["syn-o"]
    assert "syn-o" not in ch.syntheses


def test_a_synthesis_object_whose_text_no_longer_matches_its_digest_is_refused():
    ch, claims = channel()
    syn = valid_synthesis(claims)
    relayed, rc = relay(ch, syn.model_copy(update={"text": syn.text + " Added after sealing."}))
    assert relayed is None and rc.status is TransmissionStatus.REJECTED and codes(rc) == ["INT-REQ-009"]
    assert "does not re-validate against the synthesis contract" in rc.findings[-1].message


def test_a_synthesis_object_that_cannot_be_enveloped_is_refused_never_raised():
    ch, claims = channel()
    broken = Synthesis.model_construct(**{**valid_synthesis(claims).__dict__, "request_id": "", "synthesis_id": "syn-c"})
    relayed, rc = relay(ch, broken)
    assert relayed is None and rc.status is TransmissionStatus.REJECTED and codes(rc) == ["INT-REQ-009"]
    assert "cannot be put in an envelope" in rc.findings[-1].message


# =========================================================================== negative controls: the documented values


@pytest.mark.parametrize("transformation", SYNTHESIZED_CLAIM_TRANSFORMATIONS)
def test_every_documented_transformation_validates_and_is_delivered(transformation):
    ch, claims = channel()
    relayed, rc = relay(ch, mapping([carried(claims[0], transformation=transformation)]))
    assert relayed is not None and rc.status is not TransmissionStatus.REJECTED, rc.summary
    assert not {"INT-REQ-009", "INT-SYNTH-014"} & set(codes(rc))
    assert "syn-v" in ch.syntheses


def test_a_valid_synthesis_gets_the_same_receipt_as_a_mapping_and_as_an_object():
    ch_a, claims_a = channel()
    ch_b, claims_b = channel()
    _ra, as_object = relay(ch_a, valid_synthesis(claims_a))
    _rb, as_mapping = relay(ch_b, valid_synthesis(claims_b).model_dump(mode="json", exclude_none=True))
    assert as_object.status is as_mapping.status is not TransmissionStatus.REJECTED
    assert codes(as_object) == codes(as_mapping) and "INT-REQ-009" not in codes(as_object)


def test_the_documented_vocabulary_is_the_contract_vocabulary():
    assert tuple(TRANSFORMATION_MEANINGS) == get_args(Transformation)
    assert set(SYNTHESIZED_CLAIM_TRANSFORMATIONS) == set(get_args(Transformation)) - {"new", "dropped"}
    assert all(meaning.strip() for meaning in TRANSFORMATION_MEANINGS.values())
    with pytest.raises(TypeError):
        TRANSFORMATION_MEANINGS["joined"] = "an alias"  # type: ignore[index]
