"""L5 claim fidelity: the delivered claims are what the specialist actually said. Normalisation and every named rule
have their own tests; every FID code has a positive case and a control."""
from __future__ import annotations

import pytest

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.overseer.checks import normalise
from epinoic_logic.overseer.checks.fidelity import FIDELITY_RULES, claim_occurs, strip_enclosing_quotes, strip_trailing_punctuation
from epinoic_logic.overseer.checks.selfcert import flags_self_certification
from epinoic_logic.translate.contracts import SuppliedText

from .conftest import DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, english_report, findings, new_channel, ovs_errors


def _send(auditor, report, *, texts=(DOC,), request=EN_INPUT):
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", request, list(texts))
    _msg, rc = ch.respond(m.message_id, report)
    return ch, rc, auditor.audit(ch.uid)


def _claims(*extra, replace=None):
    out = [dict(c) for c in EN_CLAIMS]
    if replace:
        out = [replace.get(c["claim_id"], c) for c in out]
    return out + list(extra)


# ------------------------------------------------------------------------------------------- normalisation and rules
def test_normalisation_is_fixed_and_case_sensitive():
    assert normalise("“We” work — until the  bell’s **end** `now`") == '"We" work - until the bell\'s end now'
    assert normalise("## Heading\n- item one\n2. item two") == "Heading item one item two"
    assert normalise("ﬁne") == "fine"  # NFKC
    assert normalise("The Bell") != normalise("the bell")  # no case folding


def test_named_rules_are_listed():
    # review round 1 added joined-list-markers (its own tests: tests/overseer/test_review1_content_checks.py)
    # review round 2 added three named rules (context-free, carried-list-number, invisible); the earlier five stay, in order
    # the translator merge added three (mark-annotation, same-form-figures, no-quotation-to-verify; their own tests:
    # tests/overseer/test_rebuild_merged_translator.py); the earlier eight stay, in order
    assert FIDELITY_RULES == ("enclosing-quotes", "folded-tail", "trailing-punctuation", "contract-cut", "joined-list-markers", "context-free",
                              "carried-list-number", "invisible", "mark-annotation", "same-form-figures", "no-quotation-to-verify")


def test_rule_contract_cut():
    from epinoic_logic.adapters.markdown import truncate_claim_text
    long_sentence = "The mill " + "turned and " * 600 + "stopped."
    cut = truncate_claim_text(long_sentence)
    assert cut.endswith("...") and len(cut) <= 4000
    assert claim_occurs(cut, normalise(long_sentence))
    assert not claim_occurs("The mill rested...", normalise(long_sentence))  # a short claim ending in an ellipsis is not a cut


def test_rule_enclosing_quotes():
    resp = normalise('The killing is recast as "homicide in legitimate defense of honor, a phrase that juxtaposes. The key')
    claim = '"homicide in legitimate defense of honor, a phrase that juxtaposes."'
    assert claim_occurs(claim, resp)
    assert strip_enclosing_quotes('"abc".') == "abc" and strip_enclosing_quotes("abc") == "abc"
    assert not claim_occurs('"homicide in self-defence."', resp)


def test_rule_folded_tail():
    resp = normalise("First sentence here. Second sentence is long. Third one ends it.")
    assert claim_occurs("Second sentence is long. Third one...", resp, tail=True)
    assert not claim_occurs("Second sentence is long. Third one...", resp, tail=False)
    assert not claim_occurs("Second sentence is short. Third one...", resp, tail=True)


def test_rule_trailing_punctuation():
    assert strip_trailing_punctuation("from the barbarous work of death.") == "from the barbarous work of death"
    assert strip_trailing_punctuation("what?!") == "what"


# ------------------------------------------------------------------------------------------- controls
def test_control_faithful_report_has_no_fidelity_finding(auditor):
    _ch, _rc, audit = _send(auditor, english_report())
    assert not [f for f in audit.report.findings if f.code.startswith("OVS-FID")]


# ------------------------------------------------------------------------------------------- FID-001..003, T9
def test_fid_001_a_claim_the_response_does_not_carry(auditor):
    rep = english_report(claims=_claims(dict(claim_id="en-x", claim_text="The writer celebrates the joy of labour", claim_role="interpretation", materiality="supporting")))
    _ch, rc, audit = _send(auditor, rep)
    f = findings(audit, "OVS-FID-001")
    assert f and f[0].claim_ids == ["en-x"] and f[0].message_ids == [rc.message_id] and f[0].severity == "error"
    assert audit.transfer_states[rc.message_id] == "AUDIT_FAILED"


def test_t9_a_quotation_inserted_after_parsing_is_fid_002(auditor):
    """The inserted words are in the supplied text, so the channel's source check passes; they are not in the response."""
    ev = dict(claim_id="en-ev2", claim_text="the town grew rich on their silence", claim_role="evidence", materiality="supporting",
              source_refs=[SourceRef(document_id="doc-mill", excerpt="the town grew rich on their silence")])
    _ch, rc, audit = _send(auditor, english_report(claims=_claims(replace={"en-ev2": ev})))
    assert not [f for f in rc.findings if f.code == "INT-REQ-003"]
    f2 = findings(audit, "OVS-FID-002")
    assert f2 and f2[0].claim_ids == ["en-ev2"] and f2[0].document_ids == ["doc-mill"]
    assert [f.claim_ids for f in findings(audit, "OVS-FID-001")] == [["en-ev2"]]


def test_fid_003_a_figure_the_response_states_under_no_spelling(auditor):
    text = EN_TEXT + " The shifts lasted 12 hours."
    claim = dict(claim_id="en-fig", claim_text="The shifts lasted 14 hours.", claim_role="evidence", materiality="supporting")
    _ch, _rc, audit = _send(auditor, english_report(text, _claims(claim)))
    f = findings(audit, "OVS-FID-003")
    assert f and f[0].claim_ids == ["en-fig"] and "14" in f[0].message


def test_fid_003_control_a_figure_in_words_matches_its_digits(auditor):
    text = EN_TEXT + " The shifts lasted twelve hours."
    claim = dict(claim_id="en-fig", claim_text="The shifts lasted twelve hours.", claim_role="evidence", materiality="supporting")
    _ch, _rc, audit = _send(auditor, english_report(text, _claims(claim)))
    assert not findings(audit, "OVS-FID-003")


# ------------------------------------------------------------------------------------------- FID-004, T9b
_INVENTED_TEXT = EN_TEXT + ' The foreman insists "the bell is our only god".'
_INVENTED = dict(claim_id="en-ev3", claim_text="the bell is our only god", claim_role="evidence", materiality="supporting",
                 source_refs=[SourceRef(document_id="doc-mill", excerpt="the bell is our only god")])


def test_fid_004_control_the_channel_names_the_invented_quotation(auditor):
    _ch, rc, audit = _send(auditor, english_report(_INVENTED_TEXT, _claims(_INVENTED)))
    assert any(f.code == "INT-REQ-003" and "en-ev3" in f.claim_ids for f in rc.findings)
    assert not findings(audit, "OVS-FID-004")


def test_t9b_source_location_patched_out_is_fid_004(auditor, monkeypatch):
    monkeypatch.setattr(TranslatorChannel, "_source_findings", lambda self, report, supplied: (set(), set(), []))
    orig = TranslatorChannel._branch_checks

    def no_src(self, report, req, findings_, *a, **kw):
        structural, formal, ids = orig(self, report, req, findings_, *a, **kw)
        findings_[:] = [f for f in findings_ if not (f.code == "INT-SUBJ-003" and "-SRC-" in f.message)]
        return [s for s in structural if "-SRC-" not in s.code], formal, ids
    monkeypatch.setattr(TranslatorChannel, "_branch_checks", no_src)
    _ch, rc, audit = _send(auditor, english_report(_INVENTED_TEXT, _claims(_INVENTED)))
    f = findings(audit, "OVS-FID-004")
    assert f and f[0].claim_ids == ["en-ev3"] and f[0].message_ids == [rc.message_id] and "doc-mill" in f[0].document_ids


# ------------------------------------------------------------------------------------------- FID-005, FID-009, T8
def test_t8b_a_self_report_delivered_as_analysis_is_fid_005(auditor):
    text = EN_TEXT + " All quotations verified."
    claim = dict(claim_id="en-self", claim_text="All quotations verified.", claim_role="analysis", materiality="supporting", advisory_verification_status="verified")
    _ch, rc, audit = _send(auditor, english_report(text, _claims(claim)))
    f = findings(audit, "OVS-FID-005")
    assert f and f[0].claim_ids == ["en-self"] and f[0].severity == "error"


#: Recorded round-5 phrasings the adapters' detector missed before the translator merge; the merged translator's
#: detector (round-5 fixes of the development branch) now flags each of them.
R5_PHRASINGS = [
    "Every mileage figure above has been checked against the Board of Trade railway returns.",
    "These quotations are accurate and need no further checking.",
    "Each of the mileage figures given above has been verified.",
    "Every quoted line above has been checked against the poem's text.",
    "All of the quotations above are exact.",
]
#: Phrasings the merged detector still misses and the auditor's own structural rule flags: what FID-009 is for.
MISSED_PHRASINGS = [
    "Our statistics are precise to the decimal.",
    "Each of these statistics is faithful to the census tables.",
    "I compared every figure with the census tables.",
    "These excerpts are verbatim from the poem.",
    "Every detail here is precise.",
]


@pytest.mark.parametrize("sentence", MISSED_PHRASINGS)
def test_t8_phrasings_the_adapters_miss_are_fid_009(auditor, sentence):
    # Rewritten for the translator merge (every assertion kept): the recorded round-5 phrasings this test used are now
    # caught by the merged adapters' detector (next test), so FID-009, the auditor's heuristic for what the detector
    # misses, is asserted on phrasings the merged detector misses.
    from epinoic_logic.adapters.markdown import is_self_certification
    assert not is_self_certification(sentence)  # the adapters' detector misses it
    claim = dict(claim_id="en-cert", claim_text=sentence, claim_role="interpretation", materiality="supporting")
    _ch, rc, audit = _send(auditor, english_report(EN_TEXT + " " + sentence, _claims(claim)))
    f = findings(audit, "OVS-FID-009")
    assert f and f[0].severity == "warning" and f[0].claim_ids == ["en-cert"]
    assert not findings(audit, "OVS-FID-005")
    assert audit.transfer_states[rc.message_id] == "AUDIT_PASSED_WITH_FINDINGS"  # a heuristic never fails a transfer


@pytest.mark.parametrize("sentence", R5_PHRASINGS)
def test_t8_r5_phrasings_the_merged_detector_catches_are_fid_005(auditor, sentence):
    """The round-5 phrasings, delivered as content: the merged detector flags each, so the channel names the claim
    (ES-META-001 on the structured path) and the auditor reports the self-report delivered as content as FID-005, the
    error, exactly as for any phrasing the detector knows (test_t8b); FID-009 is not raised beside it."""
    from epinoic_logic.adapters.markdown import is_self_certification
    assert is_self_certification(sentence)
    claim = dict(claim_id="en-cert", claim_text=sentence, claim_role="interpretation", materiality="supporting")
    _ch, rc, audit = _send(auditor, english_report(EN_TEXT + " " + sentence, _claims(claim)))
    assert any(sf.code == "ES-META-001" and "en-cert" in sf.claim_ids for sf in rc.structural_findings)
    f = findings(audit, "OVS-FID-005")
    assert f and f[0].severity == "error" and f[0].claim_ids == ["en-cert"]
    assert not findings(audit, "OVS-FID-009")
    assert audit.transfer_states[rc.message_id] == "AUDIT_FAILED"


def test_t8c_controls_roled_other_are_not_flagged(auditor):
    sentence = "These quotations are accurate and need no further checking."
    claim = dict(claim_id="en-cert", claim_text=sentence, claim_role="other", materiality="supporting", advisory_verification_status="self-certified in the response text")
    _ch, _rc, audit = _send(auditor, english_report(EN_TEXT + " " + sentence, _claims(claim)))
    assert not findings(audit, "OVS-FID-009") and not findings(audit, "OVS-FID-005")


@pytest.mark.parametrize("sentence", [
    "The census figures were checked by the registrar in 1851.",
    "These figures were checked by the registrar.",
    "Dates and figures are from memory; verify them against your notes before use.",
    "The dates and figures in this paragraph are from memory and should be checked before they are cited.",
    "The dates in this paragraph have not been checked.",
    "Every figure in the painting is exact.",
    "I think the poet confirms the reading.",
    "These dates mark the turning point of the war.",
    "Every quotation must be verified against the source.",
])
def test_structural_detector_negatives(sentence):
    assert not flags_self_certification(sentence)


@pytest.mark.parametrize("sentence", [
    "I have confirmed each of these dates against the timeline.",
    "All the dates in this answer are correct.",
    "The figures above are accurate.",
    "Each quotation was compared with the supplied poem and matches it exactly.",
    "We verified every figure.",
])
def test_structural_detector_positives(sentence):
    assert flags_self_certification(sentence)


# ------------------------------------------------------------------------------------------- FID-006..008
def test_fid_006_response_content_no_claim_carries(auditor):
    text = EN_TEXT + ' The foreman ends the day: "and then we sleep".'
    _ch, rc, audit = _send(auditor, english_report(text))
    f = findings(audit, "OVS-FID-006")
    assert f and f[0].severity == "warning" and "and then we sleep" in f[0].message and f[0].message_ids == [rc.message_id]


def test_fid_007_quotations_checked_only_against_the_specialists_own_text(auditor):
    _ch, rc, audit = _send(auditor, english_report(), texts=(), request="Analyse how the writer presents work. Write no more than 80 words.")
    f = findings(audit, "OVS-FID-007")
    assert f and f[0].severity == "warning" and f[0].document_ids == ["doc-mill"]


def test_fid_008_a_supplied_text_altered_in_the_report(auditor):
    altered = SuppliedText(document_id="doc-mill", title="Mill extract", author="Anonymous",
                           text=DOC.text.replace("grew rich on their silence", "grew poor") + " We work until the bell.")
    _ch, rc, audit = _send(auditor, english_report(docs=(altered,)))
    f = findings(audit, "OVS-FID-008")
    assert f and f[0].document_ids == ["doc-mill"] and f[0].severity == "error" and f[0].message_ids == [rc.message_id]
