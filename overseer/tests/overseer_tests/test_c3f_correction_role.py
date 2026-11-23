"""Follow-up c3f, overseer item 2: rule ``correction-role`` (the challenger of the push check of a9129c78, ll-t16; expected values fixed
here). The auditor's own-correction exemption covered both halves of an own correction, so a corrected half that presents the source's
wording altered ('Mal: "Made with love." Bien: "Made with care. Finished with care."' for the notes' 'Made with love. Finished with love.')
drew no OVS-FID-004 from the auditor's own reading in any task kind; and once the channel freed the replaced half of a correction that
restores the source's exact wording ('Wrong: "Not every kitchen has a home." Right: "Not every kitchen has a door."'), the auditor still
named it (OVS-FID-004, AUDIT_FAILED on an honest receipt). The auditor now reads the halves by role as the English parser and the channel
do (``correction_reading`` through the public API). Both twins are pinned, end to end and with the channel's source checks removed.
"""
from __future__ import annotations

import pytest

from epinoic_logic.api.adapters import CORRECTION_FREE, CORRECTION_QUOTATION
from epinoic_logic.api.channel import TranslatorChannel
from epinoic_logic.api.translate import SuppliedText
from epinoic_overseer.checks.fidelity import CORRECTION_ROLE_RULE, FIDELITY_RULES, correction_role

from .conftest import EN_INPUT, english_report, findings, make_auditor, make_plan, new_channel
from .test_c3e_own_correction import _claims as _sentences
from .test_clearance_c3_overseer import C3, _audited_channel, _item


#: The faulty twin: its corrected half alters the notes' 'Made with love. Finished with love.' (one word changed, twice).
FAULTY = 'Mal: "Made with love." Bien: "Made with care. Finished with care."'
#: The correct twin: its corrected half is the notes' exact wording; its replaced half is the writer's example of the misquotation.
CORRECT = 'Wrong: "Not every kitchen has a home." Right: "Not every kitchen has a door."'
_ERRORS = ("INT-REQ-003", "ES-SRC-001", "CORE-SRC-006")


def _ll_t16(extra: str, task_type: str):
    it = dict(_item("ll-t16"))
    key = f"ll-t16-c3f-{task_type}-{abs(hash(extra))}"
    C3["specialists"][key] = dict(it, task_id=key, task_type=task_type, response_text=it["response_text"] + "\n\n" + extra)
    return key


def _notes() -> SuppliedText:
    t = _item("ll-t16")["supplied_texts"][0]
    return SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"])


def test_the_rule_is_named():
    assert CORRECTION_ROLE_RULE == "correction-role" and CORRECTION_ROLE_RULE in FIDELITY_RULES


@pytest.mark.parametrize("sentence, quote, role", [
    (FAULTY, "Made with care. Finished with care.", CORRECTION_QUOTATION),
    (FAULTY.replace("Mal:", "Wrong:").replace("Bien:", "Right:"), "Made with care. Finished with care.", CORRECTION_QUOTATION),
    ('"Made with love" -> "Made with care. Finished with care."', "Made with care. Finished with care.", CORRECTION_QUOTATION),
    ('Before: "Every kitchen has a story." After: "Every kitchen has a secret."', "Every kitchen has a secret.", CORRECTION_QUOTATION),
    (CORRECT, "Not every kitchen has a home.", CORRECTION_FREE),
    # the halves no text holds, altered or not, keep the reading of rule own-correction
    ('Your thesis is vague: "the adverts are about money" -> "the adverts sell saving as a family duty".', "the adverts are about money", None),
    ('Your thesis is vague: "the adverts are about money" -> "the adverts sell saving as a family duty".',
     "the adverts sell saving as a family duty", None),
    # a quotation in no correction has no role
    ('The notes quote the slogan "Made with care. Finished with care."', "Made with care. Finished with care.", None),
], ids=["faulty-mal-bien", "faulty-wrong-right", "faulty-arrow", "before-after-altered", "correct-restores", "own-replaced", "own-corrected",
        "no-correction"])
def test_the_auditor_reads_the_halves_by_role(sentence, quote, role):
    rep = _sentences(sentence)
    assert correction_role(rep.claims[0], quote, rep, {"doc-everykitchen-notes": _notes()}) == role


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_the_correct_twin_draws_no_finding_and_the_audit_passes(task_type):
    key = _ll_t16(CORRECT, task_type)
    a = _audited_channel(key, translations=False)
    try:
        assert sorted({f.code for f in list(a.rc.findings) + list(a.rc.structural_findings) if f.code in _ERRORS}) == []
        assert [f.message for f in a.audit.report.findings if f.code == "OVS-FID-004"] == []
        assert (a.cl.state, sorted(a.cl.codes)) == ("AUDIT_PASSED", [])
    finally:
        a.hub.close()
        C3["specialists"].pop(key, None)


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_the_faulty_twin_is_charged_by_the_channel_and_the_audit_agrees(task_type):
    key = _ll_t16(FAULTY, task_type)
    a = _audited_channel(key, translations=False)
    try:
        charged = [f for f in list(a.rc.findings) + list(a.rc.structural_findings) if f.code in ("INT-REQ-003", "ES-SRC-001")]
        assert sorted({(f.code, f.severity) for f in charged}) == [("ES-SRC-001", "error"), ("INT-REQ-003", "error")]
        assert all("care" in f.message for f in charged if f.code == "INT-REQ-003")
        assert [f.message for f in a.audit.report.findings if f.code == "OVS-FID-004"] == []
        assert (a.cl.state, sorted(a.cl.codes)) == ("AUDIT_PASSED", [])
    finally:
        a.hub.close()
        C3["specialists"].pop(key, None)


def _without_the_channels_source_checks(monkeypatch) -> None:
    """A channel that names no quotation (as test_audit_fidelity's T9b): the auditor's own reading is what remains."""
    monkeypatch.setattr(TranslatorChannel, "_source_findings", lambda self, report, supplied: (set(), set(), []))
    orig = TranslatorChannel._branch_checks

    def no_src(self, report, req, findings_, *a, **kw):
        structural, formal, ids = orig(self, report, req, findings_, *a, **kw)
        findings_[:] = [f for f in findings_ if not (f.code == "INT-SUBJ-003" and "-SRC-" in f.message)]
        return [s for s in structural if "-SRC-" not in s.code], formal, ids
    monkeypatch.setattr(TranslatorChannel, "_branch_checks", no_src)


@pytest.mark.parametrize("task_type", ["analytical_paragraph", "hl_essay", "marking_feedback"])
@pytest.mark.parametrize("sentence, named", [
    (FAULTY, ["Made with care. Finished with care."]),
    (FAULTY.replace("Mal:", "Wrong:").replace("Bien:", "Right:"), ["Made with care. Finished with care."]),
    (CORRECT, None),
], ids=["faulty-mal-bien", "faulty-wrong-right", "correct"])
def test_the_auditor_names_a_corrected_half_the_channel_misses_and_never_the_replaced_example(monkeypatch, sentence, named, task_type):
    _without_the_channels_source_checks(monkeypatch)
    auditor = make_auditor()
    notes = _notes()
    claims = [dict(claim_id="c1", claim_text=sentence, claim_role="point", materiality="material")]
    report = english_report(sentence, claims, docs=(notes,))
    report = report.model_copy(update={"task_type": task_type, "claims": [c.model_copy(update={"task_type": task_type}) for c in report.claims]})
    ch = new_channel(auditor, make_plan(task_type=task_type, allowed_document_ids=[notes.document_id]))
    m, _r, rq = ch.request("router", "english-specialist", EN_INPUT, [notes])
    assert m is not None, rq.findings
    _msg, rc = ch.respond(m.message_id, report)
    audit = auditor.audit(ch.uid)
    assert not [f for f in rc.findings if f.code == "INT-REQ-003"]  # the channel names nothing here
    fid = findings(audit, "OVS-FID-004")
    if named is None:
        assert fid == [], [f.message for f in fid]
    else:
        assert len(fid) == 1 and fid[0].claim_ids == ["c1"] and all(q[:40] in fid[0].message for q in named), [f.message for f in fid]
        assert "Made with love" not in fid[0].message  # the replaced half is the notes' exact wording
