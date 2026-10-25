"""INT-LEDGER-029 on the other phrasings of a self-report (repair round 1, re-run review cf-3 variant):

* the short status of the checks themselves ("All checks passed.", "No checks failed.", after a colon "Verified: every
  check passes"), in a synthesis and in a specialist's report alike (``adapters.markdown.SELF_CERT_RE``);
* a check result stated in either polarity, with the checks of the process or of a report as its subject ("the
  Mathematics report's own checks flag its written lines ... as not holding", "the engine found that the second line
  does not hold"): a combinator cannot vouch for a check result, only the receipts carry them
  (``integrity.ledger._CHECK_STATUS_RE``).

Clean controls: a program's checks inside a clause ("if all checks pass, the record is saved"), checks that are subject
matter ("border checks", "the safety checks"), and a source or person that finds something ("the court found ...")."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import SELF_CERT_RE, is_self_certification
from epinoic_logic.integrity import SynthesizedClaim
from epinoic_logic.integrity.ledger import check_synthesis_ledger

from .test_ledger_round8 import FACT, NOTE, TWO, _codes, _report, _synthesis

NOTE_CHECKS = 'Limit: the Mathematics report\'s own checks flag its written lines "ln 8.04 + 8 ln 10 = 2.084429" and "ln 2 / k = 0.693147" as not holding as written.'


@pytest.mark.parametrize("sentence", ["All checks passed.", "No checks failed.", "Verified: every check passes.", "All formal checks have passed.",
                                      "All of the checks passed."])
def test_the_status_of_the_checks_is_verification_status_language(sentence):
    assert SELF_CERT_RE.search(sentence) and is_self_certification(sentence)


@pytest.mark.parametrize("sentence", ["If all checks pass, the record is saved.", "The function returns True when every check passes.",
                                      "Its two checks passed.", "All the safety checks passed before launch.", "Border checks passed without incident."])
def test_clean_control_checks_inside_a_clause_or_of_subject_matter_are_no_status(sentence):
    assert not SELF_CERT_RE.search(sentence) and not is_self_certification(sentence)


@pytest.mark.parametrize("added", [" All checks passed.", f" {NOTE_CHECKS}", " The engine found that the second line does not hold.",
                                   " The hub's checks show every figure holds."])
def test_a_merged_status_or_check_result_is_a_self_report(added):
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=FACT.claim_text + added, source_claim_ids=["s1.1"], transformation="merged", evidence_refs=TWO)])
    [f] = _codes(check_synthesis_ledger([_report([FACT, NOTE])], syn))["INT-LEDGER-029"]
    assert f.severity == "warning" and "self-report" in f.message and f.claim_ids[0] == "y1"


def test_a_carried_check_status_note_is_a_self_report():
    note = FACT.model_copy(update={"claim_id": "s1.3", "claim_text": NOTE_CHECKS, "claim_role": "other", "materiality": "supporting", "source_refs": []})
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=FACT.claim_text, source_claim_ids=["s1.1"], evidence_refs=TWO),
                      SynthesizedClaim(claim_id="y2", text=NOTE_CHECKS, source_claim_ids=["s1.3"], transformation="carried")])
    [f] = _codes(check_synthesis_ledger([_report([FACT, note])], syn))["INT-LEDGER-029"]
    assert f.claim_ids[:2] == ["y2", "s1.3"]


@pytest.mark.parametrize("added", [" Border checks showed that the travellers were refugees.", " The safety checks found a fault in the O-ring, which failed.",
                                   " The court found that the law does not hold.", " The historian found that the claim is false.",
                                   " If all checks pass, the record is saved."])
def test_clean_control_checks_of_the_subject_matter_are_no_self_report(added):
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=FACT.claim_text + added, source_claim_ids=["s1.1"], transformation="merged", evidence_refs=TWO)])
    assert "INT-LEDGER-029" not in _codes(check_synthesis_ledger([_report([FACT, NOTE])], syn))
