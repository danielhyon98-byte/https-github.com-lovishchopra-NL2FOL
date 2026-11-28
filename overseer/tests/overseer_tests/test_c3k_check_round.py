"""Check round of meaning-check stage 2a, the overseer's side. Labels are scripted or made by the faithful fake; no provider is
called. Expected values are fixed here:

* a configured labeller with the production default left in place (a deployment: the hub is given its labeller, the process
  default stays ``UnconfiguredLabeller``): a clean answer of every branch is delivered NOT CHECKED and the router's documented
  decision allows it, exactly as under the faithful default. Before: the auditor's shadow replay labelled with the process default,
  raised INT-SELF-002 that the receipt does not carry, and the task audit's OVS-RCPT-004 withheld every answer;
* a combined answer whose ledger reason, conflict description or conflict basis holds a sentence the label names is never released
  (rule ``self-certification-gate``). Before: the label read only the synthesis text and its claims;
* the label gate reads a record only beside its digests: an event whose ``label_sha256`` or ``labelled_text_sha256`` is absent is
  refused as an outage (``missing`` or ``text-mismatch``), never read as ``none_named``.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from epinoic_logic.api.label import ReaderBackedLabeller, ScriptedLabeller, UnconfiguredLabeller, default_labeller, set_default_labeller

from epinoic_overseer.label_gate import LabelUnavailable, label_gate

from . import test_c2_hold_round3_gate  # noqa: F401 - puts the overseer's scripts (ovs_harness, tamper) on the path
from .test_c2_hold_self_certification_gate import SUBJECTS
from .test_c3k_label_gate import HISTORY, close, deliver

from epinoic_overseer.delivery_policy import DeliveryConfig

NC = DeliveryConfig(on_overseer_timeout="deliver_canonical_not_checked")
SCHEMA = "selfcert-label/1"
#: The rule reader passes it (writer combinator); the scripted label below names it.
QUALITY = "This synthesis has no weak points."


@pytest.fixture
def production_default():
    """The production default installed for the test (a deployment's process default), the previous one put back after."""
    prev = set_default_labeller(None)
    try:
        assert isinstance(default_labeller(), UnconfiguredLabeller)
        yield
    finally:
        set_default_labeller(prev)


@pytest.mark.parametrize("subject", SUBJECTS, ids=[s[0] for s in SUBJECTS])
def test_a_configured_hub_labeller_delivers_a_clean_answer_with_the_production_default_in_place(subject, production_default):
    d = deliver(subject[3], labeller=ReaderBackedLabeller(), config=NC, subject=subject)
    try:
        assert [f.code for f in d.rc.findings if f.code.startswith("INT-SELF-")] == []
        assert "OVS-RCPT-004" not in {f.code for f in d.audit.report.findings}
        assert d.candidate.deliverable, d.candidate.integrity_reasons
        assert d.decision.delivered and d.decision.mode == "not_checked", d.decision.mode
        assert d.router.allowed, d.router.reason
    finally:
        close(d)


def _naming_quality(req, _n):
    verdicts = []
    for it in req.items:
        if it.canary is not None and it.canary.positive:
            verdicts.append({"id": it.id, "v": "gated", "spans": [{"quote": it.text, "category": "CHECK"}]})
        elif QUALITY in it.text:
            verdicts.append({"id": it.id, "v": "gated", "spans": [{"quote": QUALITY, "category": "QUALITY"}]})
        else:
            verdicts.append({"id": it.id, "v": "none", "spans": []})
    return json.dumps({"schema": SCHEMA, "verdicts": verdicts}, ensure_ascii=False)


def _release_with(**kw):
    import ovs_harness as H
    import tamper as T
    from epinoic_overseer.policy import release_decision
    a = H.new_auditor(H.keyring_for("synthetic"), shadow="off", inline_final_release=True)
    try:
        run = T.run_synthetic(a, synthesis=T.default_synthesis(**kw))
        return release_decision(run.receipts["syn"], run.audit(final=True), a.keyring, audits=a.audits(run.uid), journal=a.journal(run.uid),
                                message=run.messages.get("syn"))
    finally:
        a.close()


def _ledger(reason: str):
    import tamper as T
    base = list(T.default_synthesis().ledger)
    return [base[0], base[1].model_copy(update={"reason": reason})]


PLACEMENTS = {
    "ledger reason": lambda: {"ledger": _ledger("supporting detail beyond scope. " + QUALITY)},
    "conflict description": lambda: {"conflicts": ({"conflict_id": "k1", "claim_ids": ["s2", "s3"],
                                                    "description": "The two accounts weigh the Act differently. " + QUALITY},)},
    "conflict basis": lambda: {"conflicts": ({"conflict_id": "k1", "claim_ids": ["s2", "s3"], "description": "The two accounts weigh the Act differently.",
                                              "status": "resolved_with_basis", "basis": QUALITY},)},
}


@pytest.mark.parametrize("where", list(PLACEMENTS))
def test_a_combined_answer_whose_payload_field_the_label_names_is_never_released(where):
    prev = set_default_labeller(ScriptedLabeller(_naming_quality))
    try:
        d = _release_with(**PLACEMENTS[where]())
    finally:
        set_default_labeller(prev)
    assert not d.allowed and "self-certification-gate" in d.reason, d.reason
    assert "weak points" not in d.reason


def test_the_control_without_the_sentence_is_released():
    prev = set_default_labeller(ScriptedLabeller(_naming_quality))
    try:
        d = _release_with(ledger=_ledger("supporting detail beyond scope."))
    finally:
        set_default_labeller(prev)
    assert d.allowed, d.reason


@pytest.mark.parametrize("fields,reason", [({"labelled_text_sha256": None}, "text-mismatch"), ({"label_sha256": None}, "missing"),
                                           ({"labelled_text_sha256": None, "label_sha256": None}, "missing")])
def test_the_gate_refuses_a_labelled_event_without_its_digests(fields, reason):
    d = deliver(HISTORY[3])
    try:
        assert label_gate(d.event).state == "none_named"  # the journaled event as it is
        with pytest.raises(LabelUnavailable) as exc:
            label_gate(dataclasses.replace(d.event, **fields))
        assert exc.value.reason == reason
    finally:
        close(d)
