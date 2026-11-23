"""The c3e follow-up (the c3c and c3d runs' overseer handoff; expected values fixed here): the transfer auditor's OVS-FID-004 named the
wording one of the answer's own corrections replaces ('Your thesis is vague: "the adverts are about money" -> "..."' on the arena c3
record ll-t16) after the channel stopped charging it, so the receipt and the audit disagreed (AUDIT_FAILED on an honest receipt).
Rule ``own-correction``: the auditor asks the decision the channel's parser and the merged core pack ask (``own_model_words`` through
the public API, which reads the span through the one reader of the writer's own words, ``adapters/own_text.py``), with the supplied
texts in view. Both directions are pinned:

* an own correction in each form the one reader reads (an arrow, a Unicode arrow, a double arrow, 'should be', 'becomes', 'rather
  than', 'instead of', a 'Wrong:'/'Right:' pair in one paragraph or as two list lines, 'Incorrect:'/'Correct:', 'Weak:'/'Better:',
  'Before:'/'After:', one word) draws no OVS-FID-004 on either span, and the audit passes, in an essay task and a feedback task;
* the replaced wording that a supplied text holds altered, a correction credited to a text and a bare invented quotation stay
  quotations for the auditor (:func:`own_correction_words` is False), so a channel that missed them is still named.
"""
from __future__ import annotations

import pytest

from epinoic_logic.api.translate import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from epinoic_overseer.checks.fidelity import FIDELITY_RULES, OWN_CORRECTION_RULE, own_correction_words

from .test_clearance_c3_overseer import C3, _audited_channel, _item

BETTER = "the adverts sell saving as a family duty"
VAGUE = "the adverts are about money"
OWN_CORRECTIONS = {
    "ascii-arrow": f'Your thesis is vague: "{VAGUE}" -> "{BETTER}".',
    "arrow": f'Your thesis is vague: "{VAGUE}" → "{BETTER}".',
    "double-arrow": f'Your thesis is vague: "{VAGUE}" => "{BETTER}".',
    "unicode-double-arrow": f'Your thesis is vague: "{VAGUE}" ⇒ "{BETTER}".',
    "should-be": f'"{VAGUE}" should be "{BETTER}".',
    "becomes": f'A vague thesis such as "{VAGUE}" becomes "{BETTER}".',
    "rather-than": f'Better: "{BETTER}" rather than "{VAGUE}".',
    "instead-of": f'Write "{BETTER}" instead of "{VAGUE}".',
    "wrong-right": f'Wrong: "{VAGUE}". Right: "{BETTER}".',
    "wrong-right-list": f'- Wrong: "{VAGUE}"\n- Right: "{BETTER}"',
    "incorrect-correct": f'Incorrect: "{VAGUE}". Correct: "{BETTER}".',
    "weak-better": f'Weak: "{VAGUE}". Better: "{BETTER}".',
    "before-after": f'Before: "{VAGUE}". After: "{BETTER}".',
    "one-word": 'Your thesis: "greed" -> "thrift".',
}


#: The audit outcomes that are not a clean pass, fixed here. In a feedback task the English parser keeps only the evidence claim of the
#: two labelled list lines ('- Wrong: "x"' over '- Right: "y"') and drops the lines themselves, so the auditor names that parse loss
#: (OVS-FID-006, a warning; the parser's handoff); OVS-FID-004 no longer names the replaced wording.
EXPECTED_AUDIT = {("wrong-right-list", "marking_feedback"): ("AUDIT_PASSED_WITH_FINDINGS", ["OVS-FID-006"])}


def test_the_rule_is_named():
    assert OWN_CORRECTION_RULE == "own-correction" and OWN_CORRECTION_RULE in FIDELITY_RULES


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("form", sorted(OWN_CORRECTIONS))
def test_an_own_correction_draws_no_fid_004_and_the_audit_passes(form, task_type):
    it = dict(_item("ll-t16"))
    key = f"ll-t16-c3e-{form}-{task_type}"
    C3["specialists"][key] = dict(it, task_id=key, task_type=task_type, response_text=it["response_text"] + "\n\n" + OWN_CORRECTIONS[form])
    a = _audited_channel(key, translations=False)
    try:
        fid = [f.message for f in a.audit.report.findings if f.code == "OVS-FID-004"]
        assert fid == [], fid
        assert (a.cl.state, sorted(a.cl.codes)) == EXPECTED_AUDIT.get((form, task_type), ("AUDIT_PASSED", [])), (a.cl.state, a.cl.codes)
    finally:
        a.hub.close()
        C3["specialists"].pop(key, None)


@pytest.mark.parametrize("extra", [
    # the notes hold it with one word changed: an altered quotation of the supplied text, whatever the arrow (INV-Q1)
    f'"A grandmother cooks for a tiny family" -> "{BETTER}".',
    f'The notes say "A grandmother cooks for a tiny family" -> "{BETTER}".',
], ids=["altered-notes", "credited-altered-notes"])
def test_an_altered_quotation_under_a_correction_stays_charged(extra):
    it = dict(_item("ll-t16"))
    key = f"ll-t16-c3e-control-{len(extra)}"
    C3["specialists"][key] = dict(it, task_id=key, response_text=it["response_text"] + "\n\n" + extra)
    a = _audited_channel(key, translations=False)
    try:
        charged = sorted({(f.code, f.severity) for f in list(a.rc.findings) + list(a.rc.structural_findings) if f.code == "INT-REQ-003"})
        assert charged == [("INT-REQ-003", "error")], charged
        assert [f.message for f in a.audit.report.findings if f.code == "OVS-FID-004"] == []
        assert a.cl.state == "AUDIT_PASSED", (a.cl.state, a.cl.codes)
    finally:
        a.hub.close()
        C3["specialists"].pop(key, None)


NOTES = SuppliedText(document_id="notes", title="Notes", author="student", text="A grandmother cooks for a huge family every Sunday.")


def _claims(*sentences: str, response: str | None = None) -> SpecialistReport:
    ids = dict(request_id="r", task_id="t", subject="English A: Language and Literature", task_type="hl_essay")
    text = " ".join(sentences) if response is None else response
    return SpecialistReport(**ids, report_id="rep", agent_id="english-a-language-literature-specialist", original_response=text,
                            response_sha256=sha256_text(text), created_at="2026-11-21T00:00:00Z",
                            claims=[ClaimRecord(**ids, report_id="rep", agent_id="english-a-language-literature-specialist", claim_id=f"c{k}",
                                                claim_text=s, claim_role="point") for k, s in enumerate(sentences, start=1)])


@pytest.mark.parametrize("sentence, quote, own", [
    (f'Your thesis is vague: "{VAGUE}" -> "{BETTER}".', VAGUE, True),
    (f'Your thesis is vague: "{VAGUE}" -> "{BETTER}".', BETTER, True),
    (f'Your thesis is vague: "{VAGUE}" ⇒ "{BETTER}".', VAGUE, True),
    (f'"{VAGUE}" should be "{BETTER}".', VAGUE, True),
    (f'A vague thesis such as "{VAGUE}" becomes "{BETTER}".', VAGUE, True),
    (f'Better: "{BETTER}" rather than "{VAGUE}".', VAGUE, True),
    (f'Write "{BETTER}" instead of "{VAGUE}".', VAGUE, True),
    (f'Wrong: "{VAGUE}". Right: "{BETTER}".', VAGUE, True),
    (f'Incorrect: "{VAGUE}".', VAGUE, True),
    ('Your thesis: "greed" -> "thrift".', "greed", True),
    # the notes hold it with one word changed: an altered quotation of the supplied text, whatever the arrow (INV-Q1)
    (f'"A grandmother cooks for a tiny family" -> "{BETTER}".', "A grandmother cooks for a tiny family", False),
    # credited to a text: a quotation of it, never an own correction
    ('Your email says "I has went to the beach" → "I have gone to the beach".', "I has went to the beach", False),
    # no correction, no frame: an invented quotation stays one
    ('The notes insist that "nobody ever came back to the village".', "nobody ever came back to the village", False),
], ids=["replaced", "correction", "unicode-double-arrow", "should-be", "becomes", "rather-than", "instead-of", "wrong-label",
        "incorrect-label", "one-word", "altered-notes", "credited", "bare"])
def test_the_auditor_reads_the_one_readers_decision(sentence, quote, own):
    rep = _claims(sentence)
    assert own_correction_words(rep.claims[0], quote, rep, {"notes": NOTES}) is own


def test_an_evidence_claim_holding_only_the_quotation_is_read_in_the_sentence_that_quotes_it():
    sentence = f'Your thesis is vague: "{VAGUE}" -> "{BETTER}".'
    rep = _claims(sentence, f'"{VAGUE}"')
    assert own_correction_words(rep.claims[1], VAGUE, rep, {"notes": NOTES}) is True
    rep = _claims(f'"{VAGUE}"')
    assert own_correction_words(rep.claims[0], VAGUE, rep, {"notes": NOTES}) is False


def test_an_evidence_claim_is_read_in_the_paragraph_of_the_response_when_no_claim_holds_the_line():
    # a parser may keep only the evidence claim of a labelled list line: the response's paragraph is read
    response = f'Your thesis needs a direction.\n\n- Wrong: "{VAGUE}"\n- Right: "{BETTER}"'
    rep = _claims(f'"{VAGUE}"', response=response)
    assert own_correction_words(rep.claims[0], VAGUE, rep, {"notes": NOTES}) is True
    # the same evidence claim with a paragraph that only quotes the words stays a quotation
    rep = _claims(f'"{VAGUE}"', response=f'Your notes put it as "{VAGUE}".')
    assert own_correction_words(rep.claims[0], VAGUE, rep, {"notes": NOTES}) is False
