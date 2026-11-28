"""Check round of meaning-check stage 2a, the channel's side. Every label here is scripted (``ScriptedLabeller``); no provider is
called. Expected values are fixed in the tests:

* the label of a synthesis reads every free text of the synthesis that travels in the delivered payload and that the rule reader
  reads there: each ledger entry's reason, each conflict's description and basis and each evidence locator. A label that names a
  sentence in one of them gives INT-SELF-001 and withholds the synthesis, as it does for a sentence of the text or of a claim
  (before: the label read only the text and the claims, so such a sentence was delivered unlabelled, DELIVERED_UNVERIFIED);
* a claim whose source sentence the label names is listed in that INT-SELF-001's ``claim_ids`` and shown NOT_ELIGIBLE with
  the withheld-self-report meaning, also when the parser normalised the claim's text (a tick mark removed): claims are located in the
  labelled text by their letters and digits, not by exact containment (before: ``claim_ids`` [] and the claim shown ENTAILED).
"""
from __future__ import annotations

import pytest

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.channel.bus import synthesis_label_text
from epinoic_logic.channel.gate import assess_response
from epinoic_logic.integrity import AgentRole, ConflictRecord, LedgerEntry, Synthesis, SynthesizedClaim
from epinoic_logic.selfcert_label.fakes import ScriptedLabeller, reply_json
from epinoic_logic.translate.contracts import sha256_text
from epinoic_logic.translate.outcome import WITHHELD_SELF_REPORT_MEANING

from .test_channel import CFG, KEY, _speed_problem, _stub_outcome
from .test_selfcert_label_channel import QUESTION, _plan, _report

#: A sentence the rule reader passes, which the scripted label names wherever an answer unit holds it.
NAMED = "The second table settles the matter for every value."


def _naming(fragment: str, category: str = "OUTCOME"):
    def script(req, n):
        return reply_json(req, {it.id: [(fragment, category)] for it in req.items if it.canary is None and fragment in it.text})
    return script


def _synthesis(*, reason=None, description=None, basis=None, locator=None):
    text = "The speed is 15 m/s. The time is 8 s."
    refs = [{"document_id": "doc-1", "locator": locator}] if locator is not None else []
    claims = [SynthesizedClaim(claim_id="s-1", text="The speed is 15 m/s.", source_claim_ids=["a-1"], transformation="carried",
                               evidence_refs=refs),
              SynthesizedClaim(claim_id="s-2", text="The time is 8 s.", source_claim_ids=["a-3"], transformation="carried")]
    ledger = [LedgerEntry(source_claim_ids=["a-2"], transformation="dropped", reason=reason)] if reason is not None else []
    conflicts = ([ConflictRecord(conflict_id="k-1", claim_ids=["a-1", "a-3"], description=description or "The two figures differ.",
                                 status="resolved_with_basis" if basis else "unresolved", basis=basis)]
                 if description is not None or basis is not None else [])
    return Synthesis(synthesis_id="syn-1", request_id="req-9", task_id="task-9", combinator_agent_id="combinator", source_report_ids=["rep-a"],
                     claims=claims, ledger=ledger, conflicts=conflicts, text=text, text_sha256=sha256_text(text),
                     created_at="2026-11-27T10:05:00Z")


PLACEMENTS = {"ledger reason": {"reason": NAMED}, "conflict description": {"description": NAMED},
              "conflict basis": {"basis": NAMED}, "evidence locator": {"locator": "h1.1 " + NAMED}}


@pytest.mark.parametrize("where", list(PLACEMENTS))
def test_the_synthesis_label_reads_every_free_text_of_the_payload(where):
    syn = _synthesis(**PLACEMENTS[where])
    labelled = synthesis_label_text(syn)
    assert labelled.startswith(syn.text + "\n\n") and NAMED in labelled


@pytest.mark.parametrize("where", list(PLACEMENTS))
def test_a_named_sentence_in_a_synthesis_field_is_int_self_001_and_withheld(where):
    lab = ScriptedLabeller(_naming(NAMED))
    ch = TranslatorChannel(_plan(), signing_key=KEY, key_id="t", config=CFG, selfcert_labeller=lab)
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    ch.respond(m.message_id, _report())
    relayed, rc = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis(**PLACEMENTS[where]))
    assert relayed is not None
    assert [f.code for f in rc.findings if f.code.startswith("INT-SELF-")] == ["INT-SELF-001"]
    # the label's finding names the place and the family, never a word (the ledger's own findings quote the combinator's reason
    # as they did before the label: INT-LEDGER-019 and -029 report its words as the combinator's own, advisory)
    assert all("second table" not in f.message for f in rc.findings if f.code.startswith("INT-SELF-"))
    assert assess_response([rc], synthesis_required=False).display_status == "WITHHELD"
    # the sentence the label read is the one in the payload's field (it is in the labelled text, not in the synthesis text)
    _rec, labelled, _req_json = ch.label_records[relayed.message_id]
    assert NAMED in labelled and NAMED not in relayed.payload["text"]


def test_a_synthesis_whose_fields_hold_no_named_sentence_reads_none_named():
    lab = ScriptedLabeller(_naming(NAMED))
    ch = TranslatorChannel(_plan(), signing_key=KEY, key_id="t", config=CFG, selfcert_labeller=lab)
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    ch.respond(m.message_id, _report())
    _relayed, rc = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER,
                            _synthesis(reason="Outside the scope of the question.", description="The two figures differ."))
    assert [f.code for f in rc.findings if f.code.startswith("INT-SELF-")] == []


# ============================================================================================ claims located by sentence
def _entailed(claim, report):
    return _stub_outcome(claim, report, _speed_problem(claim.claim_id, 15), "ENTAILED")


def test_a_claim_whose_text_the_parser_normalised_is_named_and_withheld():
    lab = ScriptedLabeller(_naming("✔", "MARK"))
    ch = TranslatorChannel(_plan(), signing_key=KEY, key_id="t", config=CFG, selfcert_labeller=lab, verify_claim_fn=_entailed)
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    _msg, rc = ch.respond_text(m.message_id, "Model: v = d / t = 120 / 8 = 15 m/s ✔.\n\nThe time is 8 s.", agent_id="physics-specialist",
                               report_id="rep-tick")
    named = [f for f in rc.findings if f.code == "INT-SELF-001"]
    assert len(named) == 1 and named[0].message.startswith("paragraph 1, sentence 1 of the answer:")
    claims = {o.claim_id: o for o in rc.outcomes}
    # every claim of the named sentence is listed and withheld; the claim of the other paragraph keeps its own display
    assert named[0].claim_ids, named[0]
    for cid in named[0].claim_ids:
        assert claims[cid].display_status.value == "NOT_ELIGIBLE" and WITHHELD_SELF_REPORT_MEANING in claims[cid].summary
    others = [o for cid, o in claims.items() if cid not in named[0].claim_ids]
    assert others and all(o.display_status.value == "ENTAILED" for o in others)


def test_a_short_claim_elsewhere_in_the_answer_is_not_named_by_another_sentence():
    lab = ScriptedLabeller(_naming("✔", "MARK"))
    ch = TranslatorChannel(_plan(), signing_key=KEY, key_id="t", config=CFG, selfcert_labeller=lab, verify_claim_fn=_entailed)
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    _msg, rc = ch.respond_text(m.message_id, "The time is 8 s.\n\nModel: v = d / t = 120 / 8 = 15 m/s ✔.", agent_id="physics-specialist",
                               report_id="rep-tick2")
    [named] = [f for f in rc.findings if f.code == "INT-SELF-001"]
    assert named.message.startswith("paragraph 2, sentence 1 of the answer:")
    shown = {o.claim_id: o.display_status.value for o in rc.outcomes}
    assert set(named.claim_ids) and all(shown[c] == "NOT_ELIGIBLE" for c in named.claim_ids)
    assert any(v == "ENTAILED" for c, v in shown.items() if c not in named.claim_ids)
