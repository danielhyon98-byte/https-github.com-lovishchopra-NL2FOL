"""English adapter: a sentence that is nothing but a quotation is one evidence claim (not
also an interpretation), a note about the text (from-memory label on dates, a task-setting
note, a self-certification) is roled 'other' and never a material point, and ES-SRC-003
concerns quotations from memory only."""
from __future__ import annotations

from epinoic_logic.adapters.english_specialist.parser import parse_response, segment
from epinoic_logic.adapters.english_specialist.structural import structural_checks
from epinoic_logic.translate.contracts import SuppliedText

DOC = SuppliedText(document_id="d", title="Extract", text='"The lawyer stood by the thesis of homicide in legitimate defense of honor, which was upheld by the court in good faith."')


def parse(text: str):
    return parse_response(text, request_id="r", task_id="t", report_id="rep", subject="English A: Literature", task_type="analytical_paragraph", supplied_texts=[DOC], course_level="unknown")


def test_quotation_only_sentence_is_one_evidence_claim():
    rep = parse('The writer presents justice as hollow. "The lawyer stood by the thesis of homicide in legitimate defense of honor, which was upheld by the court in good faith." This shows complicity.')
    texts = [c.claim_text for c in rep.claims]
    assert sum(1 for t in texts if t.startswith('"The lawyer stood')) == 1
    assert [c.claim_role for c in rep.claims if c.claim_text.startswith('"The lawyer stood')] == ["evidence"]


def test_from_memory_label_on_dates_is_a_note_not_an_interpretation_and_not_es_src_003():
    rep = parse('Justice is shown as hollow because the court "stood by the thesis of homicide". Dates and figures are from memory; verify them.')
    note = [c for c in rep.claims if c.claim_text.startswith("Dates and figures")]
    assert note and note[0].claim_role == "other" and note[0].materiality == "supporting"
    point = next(c for c in rep.claims if c.claim_role == "point")
    assert note[0].claim_id not in point.supporting_claim_ids
    assert "ES-SRC-003" not in {f.code for f in structural_checks(rep)}


def test_quoting_from_memory_is_still_es_src_003():
    rep = parse('Justice is shown as hollow because the court, quoting from memory, "stood by the thesis of homicide". The reader sees the gap.')
    assert "ES-SRC-003" in {f.code for f in structural_checks(rep)}
    rep2 = parse('The setting, as I recall, conveys neglect through the court that "stood by the thesis of homicide". The reader sees the gap.')
    assert "ES-SRC-003" in {f.code for f in structural_checks(rep2)}


def test_task_setting_note_and_self_certification_are_other_and_a_note_block_is_meta():
    text = ('Justice is shown as hollow because the court "stood by the thesis of homicide". Syllabus version and level were not stated. '
            'VERIFIED: all claims checked and confirmed.\n\nDates and figures are from memory; verify them.')
    rep = parse(text)
    roles = {c.claim_text[:20]: c.claim_role for c in rep.claims}
    assert roles["Syllabus version and"] == "other" and roles["VERIFIED: all claims"] == "other"
    cert = next(c for c in rep.claims if c.claim_text.startswith("VERIFIED"))
    assert cert.advisory_verification_status and cert.materiality == "supporting"
    assert [p.kind for p in segment(text)] == ["body", "meta"]
    assert not [c for c in rep.claims if c.claim_role == "point" and c.claim_text.startswith("Dates")]
