"""Integration gate 4: the synthesis receipt the router receives (channel.bus.TranslatorChannel.relay, synthesis branch).

The ledger readers fixed at this gate (``tests/integrity/test_integration_gate4_ledger.py``) reach the router through the
channel: two History reports on one channel, a combinator's synthesis relayed to the router.

* a faithful paraphrase that fronts the first event as a participial phrase is delivered without INT-LEDGER-023, and the
  same sentence with the dates exchanged is still named;
* a quantifier widened ("Some historians argue" -> "Most historians argue") and an attributed view stated as fact (under
  'narrowed') are INT-LEDGER-026;
* a dropped entry's reason, a conflict's description or a conflict's basis that reports an engine or Overseer verdict is
  INT-LEDGER-029, naming the record, and the hub's INT-LEDGER-019 says that the reason it quotes is such a self-report.
"""
from __future__ import annotations

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.integrity import AgentRole, Synthesis, WorkPlan
from epinoic_logic.translate.contracts import sha256_text

KEY = b"gate4-synthesis-key-0123456789abcdef"
COMBINATOR = "dummy-combinator"
A, B = "history-a", "history-b"


def _channel(text_a: str, text_b: str, request: str) -> tuple[TranslatorChannel, dict[str, tuple[str, str]]]:
    plan = WorkPlan(plan_id="p4", request_id="r4", task_id="t4", subject="History", task_type="short_answer", selected_agent_ids=[A, B, COMBINATOR])
    ch = TranslatorChannel(plan, signing_key=KEY)
    for agent, text, rid in ((A, text_a, "rep-a"), (B, text_b, "rep-b")):
        msg, _req, rr = ch.request("router", agent, request)
        assert rr.status is not TransmissionStatus.REJECTED, rr.summary
        delivered, rc = ch.respond_text(msg.message_id, text, agent_id=agent, report_id=rid)
        assert delivered is not None, rc.summary
    claims = {c.claim_id: (c.claim_text, c.certainty) for rid in ("rep-a", "rep-b") for c in ch.transmitted_reports[rid].claims}
    return ch, claims


def _claim(cid: str, text: str, sources: list[str], certainty: str, transformation: str = "carried") -> dict:
    return {"claim_id": cid, "text": text, "source_claim_ids": sources, "certainty": certainty, "transformation": transformation}


def _relay(ch: TranslatorChannel, claims: list[dict], *, ledger: tuple = (), conflicts: tuple = ()):
    text = " ".join(c["text"] for c in claims)
    syn = Synthesis.model_validate({"synthesis_id": "syn4", "request_id": "r4", "task_id": "t4", "combinator_agent_id": COMBINATOR,
                                    "source_report_ids": ["rep-a", "rep-b"], "claims": claims, "ledger": list(ledger), "conflicts": list(conflicts),
                                    "text": text, "text_sha256": sha256_text(text), "created_at": "2026-11-01T08:00:00Z"})
    _msg, rc = ch.relay(COMBINATOR, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    assert rc.status is not TransmissionStatus.REJECTED, rc.summary
    return rc


def _carried(claims: dict[str, tuple[str, str]], skip: str) -> list[dict]:
    return [_claim(f"c{k}", text, [cid], certainty) for k, (cid, (text, certainty)) in enumerate(claims.items()) if cid != skip]


AMIENS_A = "At the census of 1801, London had close to a million inhabitants. The Peace of Amiens was signed in March 1802 and broke down in May 1803."
AMIENS_B = "Paris had about 550,000 inhabitants in 1802. Napoleon became First Consul in 1799."


def test_a_faithful_participial_paraphrase_is_delivered_without_a_re_pairing():
    ch, claims = _channel(AMIENS_A, AMIENS_B, "Compare London and Paris in 1802 in one paragraph.")
    cid = next(c for c, (t, _x) in claims.items() if "Amiens" in t)
    certainty = claims[cid][1]
    faithful = _relay(ch, _carried(claims, cid) + [_claim("p1", "Signed in March 1802, the Peace of Amiens broke down in May 1803.", [cid], certainty, "paraphrased")])
    assert not [f for f in faithful.findings if f.code == "INT-LEDGER-023"], [f.message for f in faithful.findings]
    ch, claims = _channel(AMIENS_A, AMIENS_B, "Compare London and Paris in 1802 in one paragraph.")
    swapped = _relay(ch, _carried(claims, cid) + [_claim("p1", "Signed in May 1803, the Peace of Amiens broke down in March 1802.", [cid], certainty, "paraphrased")])
    [f] = [f for f in swapped.findings if f.code == "INT-LEDGER-023"]
    assert f.severity == "error" and "p1" in f.claim_ids and "(exchanged)" in f.message


VIEW_A = "Some historians argue that the Peace of Amiens was only a truce. Coal smoke hung over London for much of the year."
VIEW_B = "Paris had about 550,000 inhabitants in 1802. Napoleon became First Consul in 1799."


def test_a_widened_quantifier_and_an_attribution_dropped_under_narrowed_are_named():
    for text, transformation, said in (("Most historians argue that the Peace of Amiens was only a truce.", "paraphrased", "widens the quantifier 'Some'"),
                                       ("The Peace of Amiens was only a truce.", "narrowed", "drops the attribution 'Some historians argue that'")):
        ch, claims = _channel(VIEW_A, VIEW_B, "Was the Peace of Amiens a lasting settlement? Answer in one paragraph.")
        cid = next(c for c, (t, _x) in claims.items() if "historians" in t)
        rc = _relay(ch, _carried(claims, cid) + [_claim("v1", text, [cid], claims[cid][1], transformation)])
        named = [f for f in rc.findings if f.code == "INT-LEDGER-026" and "v1" in f.claim_ids]
        assert named and said in named[0].message, [f.message for f in rc.findings]


DATE_A = "The Peace of Amiens was signed in March 1802. Coal smoke hung over London for much of the year."
DATE_B = "The Peace of Amiens was signed in October 1801. Paris had about 550,000 inhabitants in 1802."


def _dates():
    ch, claims = _channel(DATE_A, DATE_B, "When was the Peace of Amiens signed? Answer in one paragraph.")
    a1 = next(c for c, (t, _x) in claims.items() if "March 1802" in t)
    b1 = next(c for c, (t, _x) in claims.items() if "October 1801" in t)
    return ch, claims, a1, b1


def test_a_dropped_reason_reporting_an_overseer_verdict_is_a_self_report_and_int_ledger_019_says_so():
    ch, claims, _a1, b1 = _dates()
    reason = "The overseer confirmed the March 1802 date, so the October date was removed."
    rc = _relay(ch, _carried(claims, b1), ledger=({"source_claim_ids": [b1], "transformation": "dropped", "reason": reason},))
    [own] = [f for f in rc.findings if f.code == "INT-LEDGER-029"]
    assert own.severity == "warning" and own.claim_ids == [b1] and own.agent_ids == [COMBINATOR] and reason in own.message
    [dropped] = [f for f in rc.findings if f.code == "INT-LEDGER-019"]
    assert reason in dropped.message and "a self-report" in dropped.message


def test_a_conflict_basis_or_description_reporting_an_engine_verdict_is_a_self_report():
    ch, claims, a1, b1 = _dates()
    conflict = {"conflict_id": "k1", "claim_ids": [a1, b1], "description": "Checked by the logic engine: both are verified and agree.",
                "status": "resolved_with_basis", "basis": "The Z3 engine proved that March 1802 is correct."}
    rc = _relay(ch, _carried(claims, b1), ledger=({"source_claim_ids": [b1], "transformation": "dropped", "reason": "The other report is wrong on the date."},),
                conflicts=(conflict,))
    named = [f for f in rc.findings if f.code == "INT-LEDGER-029"]
    assert len(named) == 2 and all(f.claim_ids[0] == "k1" for f in named)
    assert {("description" if "its description" in f.message else "basis") for f in named} == {"description", "basis"}
    ch, claims, a1, b1 = _dates()
    plain = {"conflict_id": "k1", "claim_ids": [a1, b1], "description": "The reports give different dates.", "status": "resolved_with_basis",
             "basis": "The October date is the preliminary peace; the treaty itself was signed in March 1802."}
    rc = _relay(ch, _carried(claims, b1), ledger=({"source_claim_ids": [b1], "transformation": "dropped", "reason": "The other report is wrong on the date."},),
                conflicts=(plain,))
    assert not [f for f in rc.findings if f.code == "INT-LEDGER-029"]
