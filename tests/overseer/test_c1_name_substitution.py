"""Regression tests for the contained round c1 judges' ledger finding: a synthesized claim that swaps the person its
source names passed the channel ledger and the audit, and the synthesis was released (rule ``name-substitution``,
INT-LEDGER-029). Each test fails on the code before the fix.

* the recorded genuine synthesis of round r3 (hi-t5, s2 'paraphrased' from h1.8): the source says "On 27 October he
  chose to answer the first letter", where "he" is Kennedy, and the synthesized claim says "On 27 October Khrushchev
  chose to answer the first letter";
* the judges' synthetic reproduction: "Lord Ashley championed the Ten Hours Act in Parliament" restated as "Robert Peel
  championed ...", through the channel, the FINAL audit and ``release_decision``;
* B2 and the shadow re-derive the finding when a patched channel drops it from the receipt;
* precision controls: the source's own names, an added title, a pronoun kept, a merge that names fewer people, and
  every recorded genuine synthesis of rounds r1 to r7 (scanned when writing the rule) stay clean.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.channel import bus as channel_bus  # noqa: E402
from epinoic_logic.integrity import SynthesizedClaim  # noqa: E402
from epinoic_logic.integrity.ledger import substituted_names  # noqa: E402
from epinoic_logic.overseer.checks.receipts import FIXED_SEVERITY  # noqa: E402
from epinoic_logic.overseer.policy import release_decision  # noqa: E402

#: The recorded round r3, task hi-t5: the History specialist's sentence h1.8 and the combinator's s2 (verbatim).
R3_H18 = ("On 27 October he chose to answer the first letter and set aside the second, while Robert Kennedy told Anatoly Dobrynin that the "
          "Jupiters would be withdrawn within months, a commitment kept out of the public record.")
R3_S2 = ("On 27 October Khrushchev chose to answer the first letter and set aside the second, while Robert Kennedy told Anatoly Dobrynin that "
         "the Jupiters would be withdrawn within months, a commitment kept out of the public record.")
#: Other sentences of the same recorded report (the cited report's other claims, which name Khrushchev and Kennedy).
R3_CONTEXT = ("Khrushchev's decision of 28 October 1962 to dismantle the missiles and return them to the Soviet Union ended the crisis, so the "
              "resolution was to a large extent his; but the terms that made the decision acceptable at home, above all a secret American "
              "assurance, were Kennedy's.",
              "After the U-2 photographs of 14 October showed missile sites under construction in Cuba, Khrushchev offered on 26 October to remove "
              "them in exchange for a pledge that the United States would not invade Cuba.")
ASHLEY = "Lord Ashley championed the Ten Hours Act in Parliament."


def _auditor(**kw):
    return H.new_auditor(H.keyring_for("synthetic"), **kw)


def _release(run, audit):
    a = run.auditor
    return release_decision(run.receipts["syn"], audit, a.keyring, audits=a.audits(run.uid), journal=a.journal(run.uid), message=run.messages.get("syn"))


# ============================================================================================ the rule itself
def test_the_recorded_r3_paraphrase_that_names_khrushchev_for_he_is_a_substituted_actor():
    out = substituted_names(R3_S2, [R3_H18], "paraphrased", context_texts=R3_CONTEXT)
    assert len(out) == 1 and "'Khrushchev'" in out[0] and "'he'" in out[0] and "substituted actor" in out[0]
    # the name is in the cited report's OTHER claims: still a name the cited source does not state
    assert substituted_names(R3_S2, [R3_H18], "merged", context_texts=R3_CONTEXT)
    # the faithful paraphrase is clean, and so is the claim carried verbatim
    assert substituted_names(R3_H18, [R3_H18], "carried", context_texts=R3_CONTEXT) == []
    assert substituted_names(R3_H18.replace("set aside", "put aside"), [R3_H18], "paraphrased", context_texts=R3_CONTEXT) == []


@pytest.mark.parametrize("label,text,tr,substituted", [
    ("the source's own name", "Lord Ashley championed the Ten Hours Act in Parliament.", "paraphrased", False),
    ("a title dropped", "Ashley championed the Ten Hours Act in Parliament.", "paraphrased", False),
    ("a title added", "Lord Ashley, the reformer, championed the Ten Hours Act in Parliament.", "paraphrased", False),
    ("the person exchanged, same act", "Robert Peel championed the Ten Hours Act in Parliament.", "paraphrased", True),
    ("the person exchanged, act reworded", "Robert Peel promoted the Ten Hours Act in Parliament.", "paraphrased", True),
    ("the person exchanged in a merge, same act", "Robert Peel championed the Ten Hours Act in Parliament.", "merged", True),
    ("a generalization is not held to names", "Robert Peel championed the Ten Hours Act in Parliament.", "generalized", False),
])
def test_a_person_exchanged_for_the_one_the_source_names_is_reported(label, text, tr, substituted):
    assert bool(substituted_names(text, [ASHLEY], tr)) is substituted, label


def test_names_inside_quotations_titles_months_and_prose_openers_never_count_as_substitutions():
    src = ['The town says "only one victim: Bayardo San Roman", and García Márquez lets the verdict stand.']
    # a name the source states inside a quotation is stated
    assert substituted_names("The majority gives the word 'victim' to Bayardo San Roman.", src, "paraphrased") == []
    # a sentence-initial prose word is not a name; months and offices identify no one
    assert substituted_names("Overall, in October García Márquez lets the verdict stand.", src, "paraphrased") == []
    assert substituted_names("President Kennedy chose to answer.", ["Kennedy chose to answer."], "paraphrased") == []
    # a merge may leave a name of its sources out and resolve a possessive pronoun no actor rule covers
    assert substituted_names("Much of London's air came from coal, as Evelyn complained.", ["Much of its air came from coal.",
                                                                                            "John Evelyn complained of the smoke."], "merged") == []


def test_the_code_is_an_error_of_the_fixed_severity_table():
    assert FIXED_SEVERITY["INT-LEDGER-029"] == "error"


# ============================================================================================ through the channel, the audit and release
def _ashley_run(auditor, synthesis_text, *, transformation="paraphrased"):
    hi_text = T.HI_TEXT + " " + ASHLEY
    probe_aud = _auditor(shadow="off")
    try:
        probe = T.run_synthetic(probe_aud, hi_text=hi_text, synthesis=False)
        hi = [t for t in probe.transfers("response_text") if t.report is not None][0]
        src = next(c for c in hi.report.claims if "Ashley" in c.claim_text)
    finally:
        probe_aud.close()
    claims = [SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried"),
              SynthesizedClaim(claim_id="s2", text="The Factory Act of 1833 banned the employment of children under nine in textile mills.",
                               source_claim_ids=["h1.1"], transformation="carried"),
              SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"],
                               transformation="carried"),
              SynthesizedClaim(claim_id="s4", text=synthesis_text, source_claim_ids=[src.claim_id], transformation=transformation)]
    return T.run_synthetic(auditor, hi_text=hi_text, synthesis=T.default_synthesis(claims=claims))


def test_the_ashley_to_peel_paraphrase_is_an_error_on_the_receipt_and_is_never_released():
    a = _auditor(shadow="off")
    try:
        run = _ashley_run(a, ASHLEY.replace("Lord Ashley", "Robert Peel"))
        rc = run.receipts["syn"]
        f = [x for x in rc.findings if x.code == "INT-LEDGER-029"]
        assert f and f[0].severity == "error" and "s4" in f[0].claim_ids and "Robert Peel" in f[0].message
        audit = run.audit(final=True)
        d = _release(run, audit)
        assert not d.allowed and "INT-LEDGER-029" in d.reason
    finally:
        a.close()


def test_the_faithful_ashley_paraphrase_is_clean_and_released():
    a = _auditor(shadow="off")
    try:
        run = _ashley_run(a, "In Parliament, Lord Ashley championed the Ten Hours Act.")
        assert not [x for x in run.receipts["syn"].findings if x.code == "INT-LEDGER-029"]
        audit = run.audit(final=True)
        assert not [f for f in audit.report.findings if "INT-LEDGER-029" in f.message]
    finally:
        a.close()


def test_b2_and_the_shadow_re_derive_the_substitution_a_patched_channel_dropped(monkeypatch):
    real = channel_bus.check_synthesis_ledger

    def dropping(*args, **kw):
        return [f for f in real(*args, **kw) if f.code != "INT-LEDGER-029"]

    a = _auditor(shadow="always")
    try:
        monkeypatch.setattr(channel_bus, "check_synthesis_ledger", dropping)
        run = _ashley_run(a, ASHLEY.replace("Lord Ashley", "Robert Peel"))
        monkeypatch.setattr(channel_bus, "check_synthesis_ledger", real)  # the patch is gone when the batch re-derives
        assert not [x for x in run.receipts["syn"].findings if x.code == "INT-LEDGER-029"]
        audit = run.audit(final=True)
        sid = run.mids["syn"]
        b2 = [f for f in audit.report.findings if f.code == "OVS-SYN-002" and "INT-LEDGER-029" in f.message]
        assert b2 and b2[0].severity == "error" and "s4" in b2[0].claim_ids
        shadow = [f for f in audit.report.findings if f.code == "OVS-RCPT-004" and sid in f.message_ids]
        assert shadow, sorted({f.code for f in audit.report.findings})
        assert audit.transfer_states.get(sid) == "AUDIT_FAILED"
        assert not _release(run, audit).allowed
    finally:
        a.close()
