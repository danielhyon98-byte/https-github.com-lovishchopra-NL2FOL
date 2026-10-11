"""Regression tests for the round-3 overseer findings on the adapters, the shared markdown
helpers and the generic parser (results-audit, communication-fidelity and adversarial-live
reports): sentence-initial and comma-bounded from-memory labels, pasted JSON glued to prose,
note sentences never the point and long note blocks, the claim-limit fold and late quotations,
dialogue copied with its own marks inside the writer's, implausible pairs of an unbalanced
paragraph, long elisions as form warnings, and the generic parser demoting only the
self-certifying sentence."""
from __future__ import annotations

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.english_specialist import parser
from epinoic_logic.adapters.english_specialist.parser import is_meta_block, parse_response, segment, split_sentences
from epinoic_logic.adapters.english_specialist.structural import structural_checks
from epinoic_logic.adapters.sources import word_count
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText
from epinoic_logic.translate.eligibility import decide_eligibility

from .conftest import IDS
from .test_overseer_round2 import FORGED_RECEIPT, POEM
from .test_structural import CLEAN, codes

PP = SuppliedText(
    document_id="doc-pp", title="Pride and Prejudice, opening (extract, supplied text)", author="Jane Austen",
    text=('"My dear Mr. Bennet," said his lady to him one day, "have you heard that Netherfield Park is let at last?"\n\n'
          "Mr. Bennet replied that he had not.\n\n"
          '"But it is," returned she; "for Mrs. Long has just been here, and she told me all about it."\n\n'
          "Mr. Bennet made no answer.\n\n"
          '"Do you not want to know who has taken it?" cried his wife impatiently.\n\n'
          '"You want to tell me, and I have no objection to hearing it."\n\n'
          "This was invitation enough."),
)
BODY = ('Shelley holds the boast at a distance. The "sneer of cold command" survives only as stone, and the "lone and level sands" '
        "flatten the upright stance. Thus the ruin answers the inscription.")
INVENTED = ' The narrator also insists that "the river carried every secret of the town", which seals the point.'
ALTERED = ' The « lone and level dunes » stretch away as the boast fades.'
FROM_MEMORY_INITIAL = "From memory, the mark stood at about 4.2 to the dollar in 1914 and 4.2 trillion by mid-November 1923."
FROM_MEMORY_COMMA = "The Dawes loan was, from memory about 800 million gold marks, the first of the foreign credits."
KEY = b"round3-regression-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def parse(text: str, texts=(POEM,), **kw) -> SpecialistReport:
    kwargs = dict(IDS, subject="English A: Literature", task_type="analytical_paragraph", supplied_texts=list(texts))
    kwargs.update(kw)
    return parse_response(text, **kwargs)


def generic(text: str, agent: str = "history-specialist", subject: str = "History", texts=()) -> SpecialistReport:
    return GenericTextParser(agent).parse_response(text, request_id="r", task_id="t", report_id="rep", subject=subject, task_type="short_answer", supplied_texts=list(texts))


def through_hub(text: str, task_id: str, texts=(POEM,)):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id=task_id, subject="English A: Literature", task_type="analytical_paragraph",
                           selected_agent_ids=["english-specialist"], allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch(task_id, "english-specialist", "Write one analytical paragraph on power in the poem. Quote from the poem.", list(texts))
    return hub.receive(task_id, m.message_id, text, agent_id="english-specialist", report_id=f"rep-{task_id}")


# ------------------------------------------------------------ communication-fidelity #2 (round-2 #1 still open): inline from-memory labels


def test_sentence_initial_and_comma_bounded_from_memory_labels_are_split_from_the_substance():
    core, notes = md.split_note_clauses(FROM_MEMORY_INITIAL)
    assert core == "the mark stood at about 4.2 to the dollar in 1914 and 4.2 trillion by mid-November 1923." and notes == ["From memory"]
    core2, notes2 = md.split_note_clauses(FROM_MEMORY_COMMA)
    assert "800 million gold marks" in core2 and "from memory" not in core2.lower() and notes2 == ["from memory"]
    assert not md.is_note_sentence(core) and not md.is_note_sentence(core2)
    # a sentence that is nothing but a label is still a note; a label stated twice is recorded once
    assert md.split_note_clauses("Dates and figures are from memory; verify them against your notes before use.")[0] == ""
    assert md.split_note_clauses("From memory, verify these dates before use.")[0] == ""
    assert md.split_note_clauses("Parliament renewed that charter in 1793 (from memory) and again in 1813 (from memory).") == (
        "Parliament renewed that charter in 1793 and again in 1813.", ["from memory"])


def test_generic_parser_keeps_the_hi_t6_from_memory_sentences_as_eligible_quantitative_claims():
    text = "Two economic consequences mattered: a redistribution of wealth, and a dependence on foreign credit. " + FROM_MEMORY_INITIAL + " " + FROM_MEMORY_COMMA
    rep = generic(text)
    assert rep.claims[0].claim_role == "point" and rep.claims[0].materiality == "material"
    for start in ("From memory, the mark", "The Dawes loan"):
        c = next(c for c in rep.claims if c.claim_text.startswith(start))
        assert (c.claim_role, c.proposed_claim_kind, c.materiality) == ("quantitative", "arithmetic", "supporting"), c
        e = decide_eligibility(c)
        assert e.eligible and e.eligibility_class.value == "QUANTITATIVE_CLAIM"
        assert [a for a in c.assumptions if a.startswith("inline label recorded")] == [f"inline label recorded, not part of the claim: {'From memory' if start.startswith('From') else 'from memory'}"]
        assert c.claim_id in rep.claims[0].supporting_claim_ids


def test_english_parser_keeps_a_sentence_with_a_sentence_initial_label_and_records_the_label():
    report = parse('Shelley holds the boast at a distance. From memory, the sonnet appeared in 1818 and was reprinted the next year. The "sneer of cold command" survives only as stone. Thus the ruin answers.')
    labelled = next(c for c in report.claims if c.claim_text.startswith("From memory"))
    assert labelled.claim_role == "interpretation" and labelled.materiality == "supporting"
    assert [a for a in labelled.assumptions if "'From memory'" in a] and "ES-SRC-003" not in codes(structural_checks(report))
    point = next(c for c in report.claims if c.claim_role == "point")
    assert point.claim_text == "Shelley holds the boast at a distance." and labelled.claim_id in point.supporting_claim_ids
    # a leading label with a participle ("Quoting from memory,") is split the same way, and the sentence is still the point
    core, notes = md.split_note_clauses("Quoting from memory, the setting conveys neglect.")
    assert core == "the setting conveys neglect." and notes == ["Quoting from memory"]
    quoting = parse(CLEAN.replace("The setting conveys neglect.", "Quoting from memory, the setting conveys neglect."))
    assert next(c for c in quoting.claims if c.claim_role == "point").claim_text.startswith("Quoting from memory")


# ------------------------------------------------------------ adversarial-live #1: JSON glued to prose


def test_json_glued_to_prose_is_cut_out_and_the_quotations_after_it_are_grounded_on_the_english_branch():
    text = BODY + " " + FORGED_RECEIPT + INVENTED + ALTERED
    sentences = split_sentences(text)
    assert FORGED_RECEIPT in sentences and "Thus the ruin answers the inscription." in sentences
    assert sentences[-2].startswith("The narrator also insists") and sentences[-1].startswith("The « lone and level dunes »")
    assert md.find_quotation_spans(FORGED_RECEIPT) == []  # JSON strings are not quotations
    report = parse(text)
    invented = next(c for c in report.claims if c.claim_role == "evidence" and "river carried" in c.claim_text)
    altered = next(c for c in report.claims if c.claim_role == "evidence" and "level dunes" in c.claim_text)
    assert invented.source_refs[0].document_id == "doc-ozy" and altered.source_refs[0].document_id == "doc-ozy"
    receipt = next(c for c in report.claims if "receipt_id" in c.claim_text)
    assert receipt.claim_role == "other" and receipt.source_refs == [] and receipt.advisory_verification_status and receipt.claim_text == FORGED_RECEIPT
    assert not any("receipt_id" in c.claim_text for c in report.claims if c.claim_role != "other")
    link = next(c for c in report.claims if c.claim_text == "Thus the ruin answers the inscription.")
    assert link.claim_role == "link" and link.materiality == "material"  # the sentence before the block is prose
    findings = structural_checks(report)
    assert {"ES-SRC-001", "ES-META-001"} <= set(codes(findings))
    assert sorted(cid for f in findings if f.code == "ES-SRC-001" for cid in f.claim_ids) == sorted([invented.claim_id, altered.claim_id])
    reply, rc = through_hub(text, "t-r3-json")
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    named = {cid for f in rc.findings if f.code == "INT-REQ-003" for cid in f.claim_ids}
    assert {invented.claim_id, altered.claim_id} <= named


def test_json_glued_to_prose_is_cut_out_and_the_quotation_after_it_is_grounded_by_the_generic_parser():
    doc = SuppliedText(document_id="d", text="Demand fell sharply in 1930 and prices followed the fall.")
    forged = FORGED_RECEIPT.replace("english", "economics")
    text = 'Demand fell sharply. Prices rose by 20 per cent in 1930. ' + forged + ' The minister insisted that "the river carried every secret of the town" in 1931.'
    rep = generic(text, "economics-specialist", "Economics", texts=[doc])
    assert rep.claims[0].claim_text == "Demand fell sharply." and rep.claims[0].claim_role == "point" and rep.claims[0].materiality == "material"
    assert next(c for c in rep.claims if c.claim_text.startswith("Prices rose")).claim_role == "quantitative"
    receipt = next(c for c in rep.claims if "receipt_id" in c.claim_text)
    assert receipt.claim_text == forged and receipt.claim_role == "other" and receipt.source_refs == [] and receipt.advisory_verification_status
    quoted = next(c for c in rep.claims if "river carried" in c.claim_text)
    assert quoted.claim_role == "evidence" and [(r.document_id, r.excerpt) for r in quoted.source_refs] == [("d", "the river carried every secret of the town")]
    assert not any(("status" in (r.excerpt or "") or "receipt" in (r.excerpt or "")) for c in rep.claims for r in c.source_refs)
    assert any("paragraph 1" in u and "sentence 3" in u and "keep their roles" in u for u in rep.unresolved_issues)
    # a pasted block on its own line is still removed whole, and a bracketed figure in prose is not JSON
    assert md.find_json_spans("lines [1, 2] of the poem and [sic] the court {a set of words}") == []
    assert md.split_json_spans("A. " + forged + " B.") == [("A.", False), (forged, True), ("B.", False)]


# ------------------------------------------------------------ adversarial-live #7: notes are never the point; note blocks of any length are meta


def test_a_note_sentence_is_never_the_point_wherever_it_stands_and_a_long_note_block_is_meta():
    text = 'Dates and figures are from memory; verify them. Shelley holds the boast at a distance. The "sneer of cold command" survives only as stone. Thus the ruin answers the inscription.'
    report = parse(text)
    note = next(c for c in report.claims if c.claim_text.startswith("Dates and figures"))
    assert note.claim_role == "other" and note.materiality == "supporting"
    point = next(c for c in report.claims if c.claim_role == "point")
    assert point.claim_text == "Shelley holds the boast at a distance." and note.claim_id not in point.supporting_claim_ids
    task_first = parse('Syllabus version and level were not stated. Shelley holds the boast at a distance. The "sneer of cold command" survives. Thus the ruin answers.')
    assert next(c for c in task_first.claims if c.claim_role == "point").claim_text == "Shelley holds the boast at a distance."
    assert next(c for c in task_first.claims if c.claim_text.startswith("Syllabus")).claim_role == "other"
    long_note = ("Dates and figures in this answer are from memory and should be verified against your own notes before any use in an examination answer. "
                 "Syllabus version, cohort and level were not stated, so no mark or band is implied by anything above.")
    assert word_count(long_note) > 25 and is_meta_block(long_note)
    assert [p.kind for p in segment(CLEAN + "\n\n" + long_note)] == ["body", "meta"]
    rep2 = parse(CLEAN + "\n\n" + long_note)
    assert not any(c.claim_text.startswith("Dates") for c in rep2.claims) and "ES-META-001" in codes(structural_checks(rep2))
    assert not is_meta_block('The lamp "stays unlit" in the hall; dates are from memory.')  # a quoting sentence is checked, not meta


# ------------------------------------------------------------ adversarial-live #2: the claim-limit fold and late quotations


def test_oversized_answer_folds_interpretation_before_evidence_so_a_late_invented_quotation_is_still_checked():
    text = " ".join(f'The lamp "stays unlit" in sentence {i}, and the metaphor of darkness marks an absence.' for i in range(600)) + INVENTED
    doc = SuppliedText(document_id="d", text="The lamp stays unlit in the hall.")
    report = parse(text, texts=[doc])
    assert len(report.claims) == 512 and report.claims[-1].claim_id == parser.TAIL_CLAIM_ID and report.claims[-1].claim_role == "other"
    [invented] = [c for c in report.claims if c.claim_role == "evidence" and any(r.excerpt == "the river carried every secret of the town" for r in c.source_refs)]
    assert invented.claim_id != parser.TAIL_CLAIM_ID and any(c.claim_role == "point" for c in report.claims)
    [issue] = [u for u in report.unresolved_issues if "merged into claim p-tail" in u]
    assert "0 of them were evidence claims" in issue and "no quotation was merged" in issue
    assert [f.claim_ids for f in structural_checks(report) if f.code == "ES-SRC-001"] == [[invented.claim_id]]
    SpecialistReport.model_validate(report.model_dump(mode="json"))
    reply, rc = through_hub(text, "t-r3-tail", texts=[doc])
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    assert any(f.code == "INT-REQ-003" and invented.claim_id in f.claim_ids for f in rc.findings)


def test_folded_evidence_claims_carry_their_source_references_on_the_tail_claim_and_the_issue_counts_them():
    text = " ".join(f'The lamp "stays unlit number {i}" in the hall.' for i in range(600))
    doc = SuppliedText(document_id="d", text="The lamp stays unlit in the hall.")
    report = parse(text, texts=[doc])
    tail = report.claims[-1]
    assert tail.claim_id == parser.TAIL_CLAIM_ID and len(tail.source_refs) == 32 and all(r.document_id == "d" for r in tail.source_refs)
    [issue] = [u for u in report.unresolved_issues if "merged into claim p-tail" in u]
    assert "90 of them were evidence claims with 90 quotation(s)" in issue and "32 quotation(s) are carried on the tail claim" in issue and "58 quotation(s) were merged unchecked" in issue
    assert any("could not be carried" in a for a in tail.assumptions)
    assert sum(1 for c in report.claims if c.claim_role == "evidence") == 510  # evidence kept over interpretation
    errors = [f for f in structural_checks(report) if f.code == "ES-SRC-001" and parser.TAIL_CLAIM_ID in f.claim_ids]
    assert len(errors) == 32  # the carried quotations are checked like any other
    SpecialistReport.model_validate(report.model_dump(mode="json"))


# ------------------------------------------------------------ adversarial-live #9: dialogue copied with its own marks inside the writer's


def test_dialogue_copied_with_double_marks_inside_double_marks_is_read_as_nested_marks():
    para = ("The Bennets' dialogue tests this logic within a marriage. The narrator reports \"\"My dear Mr. Bennet,\" said his lady to him one day, "
            "\"have you heard that Netherfield Park is let at last?\"\" and then that Mr. Bennet \"made no answer\". "
            'The closing sentence "This was invitation enough." deflates the scene.')
    assert md.dangling_quote_offset(para) is None and not md.unbalanced_double_quotes(para)
    assert [inner for _s, _e, inner in md.find_quotation_spans(para)] == [
        "My dear Mr. Bennet,", "have you heard that Netherfield Park is let at last?", "made no answer", "This was invitation enough."]
    report = parse(para, texts=[PP])
    ev = [c for c in report.claims if c.claim_role == "evidence"]
    assert {c.source_refs[0].excerpt for c in ev if c.source_refs} == {
        "My dear Mr. Bennet", "have you heard that Netherfield Park is let at last", "made no answer", "This was invitation enough"}
    assert all(c.source_refs for c in ev) and not report.unresolved_issues
    assert not any(c.startswith("ES-SRC") for c in codes(structural_checks(report)))
    curly = para.replace('""My', "““My").replace('?""', "?””")
    assert [inner for _s, _e, inner in md.find_quotation_spans(curly)][:2] == ["My dear Mr. Bennet,", "have you heard that Netherfield Park is let at last?"]
    reply, rc = through_hub(para, "t-r3-nested", texts=[PP])
    assert reply is not None and not any(f.code == "INT-REQ-003" for f in rc.findings)


def test_implausible_pairs_of_an_unbalanced_paragraph_are_undelimited_not_quotations():
    para = 'He writes "Two vast "legs of stone" stand" in the desert and "near them" a visage lies.'
    assert md.dangling_quote_offset(para) == para.index('"')
    assert [inner for _s, _e, inner in md.find_quotation_spans(para)] == ["legs of stone"]
    loose = [inner.strip() for _s, _e, inner in md.undelimited_quote_spans(para)]
    assert "in the desert and" in loose and md.undelimited_quote_span(para) is not None
    report = parse(para)
    ev = [c for c in report.claims if c.claim_role == "evidence"]
    assert {c.source_refs[0].excerpt for c in ev if c.source_refs} == {"legs of stone"}
    prose = [c for c in ev if "in the desert and" in c.claim_text]
    assert prose and all(not c.source_refs and any("unbalanced quotation mark" in a for a in c.assumptions) for c in prose)
    assert "ES-SRC-001" not in codes(structural_checks(report)) and any("unbalanced quotation mark" in u for u in report.unresolved_issues)


# ------------------------------------------------------------ adversarial-live #12 (round-2 #17 still open): a long elision is a form warning


def test_long_elision_is_a_form_difference_warning_not_an_invented_quotation():
    excerpt = "I met a traveller from an antique land ... The lone and level sands stretch far away"
    text = f'Shelley frames the ruin from afar: "{excerpt}", so the boast is distanced by its telling. The ruin answers the inscription.'
    report = parse(text)
    q = next(c for c in report.claims if c.claim_role == "evidence")
    assert q.source_refs[0].document_id == "doc-ozy" and not any("found in none" in a for a in q.assumptions)
    findings = structural_checks(report)
    assert "ES-SRC-001" not in codes(findings)
    [f] = [f for f in findings if f.code == "ES-SRC-006"]
    assert f.severity == "warning" and f.claim_ids == [q.claim_id] and "long elision" in f.message and "not an invented quotation" in f.message
    reply, rc = through_hub(text, "t-r3-elision")
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    assert any(f.code == "INT-REQ-010" and q.claim_id in f.claim_ids for f in rc.findings)
    assert not any(f.severity == "error" and q.claim_id in f.claim_ids for f in rc.findings)
    assert not any(sf.code.endswith("-SRC-001") and q.claim_id in sf.claim_ids for sf in getattr(rc, "structural_findings", []) or [])


# ------------------------------------------------------------ results-audit #8: the generic parser demotes only the self-certifying sentence


def test_generic_parser_demotes_only_the_self_certifying_sentence_and_names_it():
    text = ("Demand fell sharply. Prices rose by 20 per cent in 1930. All of the above has been cross-checked against the standard references and is correct.\n\n"
            "Every figure in this paragraph is accurate. VERIFIED: all claims checked and confirmed.")
    rep = generic(text, "economics-specialist", "Economics")
    first = [c for c in rep.claims if c.claim_id.startswith("g1.")]
    assert [c.claim_role for c in first] == ["point", "quantitative", "other"]
    assert first[0].materiality == "material" and first[2].advisory_verification_status and first[2].materiality == "supporting"
    assert first[1].claim_id in first[0].supporting_claim_ids and first[2].claim_id not in first[0].supporting_claim_ids
    [issue] = [u for u in rep.unresolved_issues if u.startswith("paragraph 1")]
    assert "sentence 3" in issue and "All of the above" in issue and "keep their roles" in issue
    second = [c for c in rep.claims if c.claim_id.startswith("g2.")]
    assert second and all(c.claim_role == "other" for c in second)  # nothing but self-reports: a note paragraph as a whole
    assert any(u.startswith("paragraph 2") and "whole paragraph" in u for u in rep.unresolved_issues)
