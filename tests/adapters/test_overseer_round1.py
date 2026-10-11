"""Regression tests for the overseer round-1 findings on the adapters (English specialist, shared
source helpers, generic adapter, registry). Each test names the behaviour the overseer probes
exposed; corpus texts come from the English specialist's knowledge documents (fixtures)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.adapters import GenericStructuredAdapter, get_adapter, registered_ids
from epinoic_logic.adapters.base import AdapterError
from epinoic_logic.adapters.english_specialist import fixtures as fx
from epinoic_logic.adapters.english_specialist import parser, structural
from epinoic_logic.adapters.english_specialist.parser import segment, split_sentences
from epinoic_logic.adapters.english_specialist.structural import citation_schemes, find_citations, structural_checks
from epinoic_logic.adapters.sources import JOIN_GAP_CHARS, check_excerpt
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.eligibility import decide_eligibility

from .conftest import DOC_ID, IDS, TEXT, parse, supplied
from .test_structural import CLEAN, codes

ADAPTER = get_adapter("english-specialist")
CORPUS = Path(__file__).resolve().parents[2] / "docs" / "qa_corpus" / "english"
EXTRACT = fx.example1_supplied_text("ex1")


def parse_ex1(text: str, texts=None, task_type: str = "analytical_paragraph", rid: str = "rep-e") -> object:
    return ADAPTER.parse_response(
        text, request_id="req-e", task_id="task-e", report_id=rid, subject="English A: Literature",
        task_type=task_type, supplied_texts=[EXTRACT] if texts is None else texts,
    )


def mutation(name: str) -> str:
    return json.loads((CORPUS / "mutations" / f"{name}.json").read_text(encoding="utf-8"))["text"]


def evidence(report):
    return [(c.claim_id, c.source_refs[0].excerpt) for c in report.claims if c.claim_role == "evidence"]


# --------------------------------------------------- quotations spanning a sentence boundary


GENUINE_TWO_SENTENCES = (
    "Revenge by the Arabs wasn't dismissed, but no one, except the Vicario brothers, had thought of poison. "
    "It was supposed, rather, that they would wait for nightfall"
)
INVENTED_TWO_SENTENCES = "The court washed the blood from the verdict. Nobody noticed the stain."


def test_boundary_inside_a_quotation_does_not_split_the_sentence():
    text = f'The narrator notes "{GENUINE_TWO_SENTENCES}" and moves on. The town waits.'
    assert split_sentences(text) == [f'The narrator notes "{GENUINE_TWO_SENTENCES}" and moves on.', "The town waits."]
    # a quotation that closes at the boundary still ends the sentence
    assert split_sentences('It ends with a quote "like this." Then "another one," she said.') == ['It ends with a quote "like this."', 'Then "another one," she said.']


def test_genuine_multi_sentence_quotation_is_one_grounded_evidence_claim():
    text = (
        f'The narrator records the town\'s mood: "{GENUINE_TWO_SENTENCES}" and then quotes the fear of fire, '
        f'"pour gasoline through the skylight" in the night.'
    )
    report = parse_ex1(text)
    assert evidence(report) == [("p1-q01", GENUINE_TWO_SENTENCES), ("p1-q02", "pour gasoline through the skylight")]
    found = codes(ADAPTER.structural_checks(report))
    assert "ES-SRC-001" not in found and "ES-SRC-005" not in found and "ES-STR-001" not in found


def test_invented_multi_sentence_quotation_is_an_error():
    text = f'The narrator writes: "{INVENTED_TWO_SENTENCES}" The town waits.'
    report = parse_ex1(text)
    assert evidence(report) == [("p1-q01", INVENTED_TWO_SENTENCES.rstrip("."))]  # the final stop belongs to the sentence
    errors = [f for f in ADAPTER.structural_checks(report) if f.code == "ES-SRC-001"]
    assert len(errors) == 1 and errors[0].claim_ids == ["p1-q01"] and "quoted from memory without the required" in errors[0].message


def test_single_quoted_spans_of_two_or_more_words_are_quotations():
    text = "The twins say 'We killed him openly' and then 'the court washed the blood' matters; the lawyer's thesis holds."
    report = parse_ex1(text)
    assert evidence(report) == [("p1-q01", "We killed him openly"), ("p1-q02", "the court washed the blood")]
    errors = [f for f in ADAPTER.structural_checks(report) if f.code == "ES-SRC-001"]
    assert [f.claim_ids for f in errors] == [["p1-q02"]]
    # possessives, contractions and one-word spans are not quotations
    assert parser.find_quotations("the twins' fear wasn't the 'point' of it") == ()


# --------------------------------------------------- paragraph classification


def test_two_body_paragraphs_are_both_bodies():
    paragraphs = segment(fx.EXAMPLE1_BODY_1 + "\n\n" + fx.EXAMPLE1_BODY_2)
    assert [p.kind for p in paragraphs] == ["body", "body"]
    report = parse_ex1(fx.EXAMPLE1_BODY_1 + "\n\n" + fx.EXAMPLE1_BODY_2)
    points = [c.claim_id for c in report.claims if c.claim_role == "point"]
    assert points == ["p1-point", "p2-point"]
    assert {c.claim_role for c in report.claims} == {"point", "evidence", "device", "interpretation", "link"}
    findings = ADAPTER.structural_checks(report)
    assert not [f for f in findings if f.code.startswith("ES-STR")]  # both are checked as bodies and pass P7/P13


@pytest.mark.parametrize("trailer", ["VERIFIED: all claims checked and confirmed.", "Word count: 341", "I have checked every quotation above."])
def test_trailing_meta_block_is_excluded_from_the_argument_and_flagged(trailer):
    text = fx.EXAMPLE1_BODY_1 + "\n\n" + trailer
    assert [p.kind for p in segment(text)] == ["body", "meta"]
    report = parse_ex1(text)
    assert "p1-point" in {c.claim_id for c in report.claims}
    assert not [c for c in report.claims if c.claim_id.startswith("p2-")]
    assert trailer not in {c.claim_text for c in report.claims}
    findings = ADAPTER.structural_checks(report)
    meta = [f for f in findings if f.code == "ES-META-001"]
    assert len(meta) == 1 and meta[0].severity == "warning" and "paragraph 2" in meta[0].message and "plays no part in verification" in meta[0].message
    assert meta[0].rule_source == structural.RULE_SOURCES["ES-META-001"]
    # the analytical paragraph is still checked as a body paragraph and keeps the baseline's findings
    assert sorted(f.code for f in findings if f.code != "ES-META-001") == ["ES-SRC-005"]


def test_corpus_self_certification_mutation():
    text = mutation("self_certification")
    report = parse_ex1(text, rid="rep-sc")
    assert [p.kind for p in segment(text)] == ["body", "meta"]
    assert "p1-point" in {c.claim_id for c in report.claims}
    assert "VERIFIED" not in " ".join(c.claim_text for c in report.claims)
    assert any("meta-text" in u for u in report.unresolved_issues)
    found = codes(ADAPTER.structural_checks(report))
    assert found == ["ES-META-001", "ES-SRC-005"]


def test_leading_title_line_is_a_heading_not_a_thesis():
    text = "Body paragraph 1\n\n" + fx.EXAMPLE1_BODY_1
    assert [p.kind for p in segment(text)] == ["list", "body"]
    report = parse_ex1(text)
    assert [c.claim_id for c in report.claims if c.claim_role == "point"] == ["p2-point"]
    assert not [c for c in report.claims if c.claim_role == "thesis"]


def test_narrated_check_inside_prose_is_flagged_as_meta_text():
    text = CLEAN.replace("Effectively, the room is presented as abandoned rather than merely empty.", "I have checked every claim above against the text.")
    found = [f for f in structural_checks(parse(text)) if f.code == "ES-META-001"]
    assert len(found) == 1 and found[0].claim_ids == ["p1-s16"]


# --------------------------------------------------- outline deliverables


def test_outline_deliverable_is_exempt_from_paragraph_rules_but_quotations_are_still_checked():
    example2 = json.loads((CORPUS / "example_2.json").read_text(encoding="utf-8"))
    outline = example2["supplementary"]["outline_2b_unit_1"]
    kinds = [p.kind for p in segment(outline)]
    assert kinds[0] == "list" and "body" in kinds and kinds.count("list") >= 2
    report = parse_ex1(outline, texts=[], task_type="outline", rid="rep-outline")
    found = codes(ADAPTER.structural_checks(report))
    assert "ES-STR-001" not in found and "ES-STR-002" not in found
    assert found == ["ES-SRC-004"]  # quotations present, no text supplied to check them against
    assert [c for c in report.claims if c.claim_role == "evidence"]
    # the same blocks as an analytical paragraph deliverable are held to P7/P13
    prose = parse_ex1(outline, texts=[], task_type="analytical_paragraph", rid="rep-outline-2")
    assert "ES-STR-001" in codes(ADAPTER.structural_checks(prose))


# --------------------------------------------------- citations (ES-SRC-002)


@pytest.mark.parametrize(
    "citation, schemes",
    [
        ("(García Márquez, p. 48)", {"page"}), ("(ch. 3, p. 49)", {"custom", "page"}), ("Act 1 Scene 2", {"act_scene_line"}),
        ("Chapter 3", {"custom"}), ("page 48", {"page"}), ("(chapter 3)", {"custom"}), ("(Shakespeare, 3.3.165)", {"act_scene_line"}),
        ("(García Márquez 48)", {"page"}), ("(see pp. 12-13)", {"page"}), ("(para. 4)", {"paragraph"}),
    ],
)
def test_citation_shapes_are_found_and_classified(citation, schemes):
    found = find_citations(f"The setting conveys neglect {citation}. Next sentence.")
    assert len(found) == 1 and citation.strip("on ") in found[0]
    assert citation_schemes(found[0]) == schemes


@pytest.mark.parametrize("not_a_citation", ["(Example 1)", "(the twins' declaration)", "(1920)", "(step 2)", "the top 10 lines of thought"])
def test_non_citations_are_left_alone(not_a_citation):
    assert find_citations(f"The setting conveys neglect {not_a_citation}. Next.") == []


@pytest.mark.parametrize("citation", ["(García Márquez, p. 48)", "(ch. 3, p. 49)", "(García Márquez 48)", "Act 1 Scene 2", "Chapter 3", "page 48"])
def test_es_src_002_for_author_prefixed_and_chapter_citations(citation):
    text = CLEAN.replace("The setting conveys neglect.", f"The setting conveys neglect {citation}.")
    findings = [f for f in structural_checks(parse(text)) if f.code == "ES-SRC-002"]
    assert len(findings) == 1 and findings[0].severity == "error" and findings[0].claim_ids == ["p1-point"] and citation in findings[0].message


def test_corpus_fake_citation_mutation_yields_two_errors():
    report = parse_ex1(mutation("fake_citation"), rid="rep-fc")
    found = [f for f in ADAPTER.structural_checks(report) if f.code == "ES-SRC-002"]
    assert len(found) == 2 and all(f.severity == "error" for f in found)
    assert "(García Márquez, p. 48)" in found[0].message and "(ch. 3, p. 49)" in found[1].message


def test_es_src_002_does_not_depend_on_the_locator_scheme_default():
    text = CLEAN.replace("The setting conveys neglect.", "The setting conveys neglect (p. 48).")
    for scheme in (None, "none", "paragraph", "line"):
        doc = SuppliedText(document_id=DOC_ID, text=TEXT) if scheme is None else supplied(TEXT, DOC_ID, scheme)
        found = [f for f in structural_checks(parse(text, texts=[doc])) if f.code == "ES-SRC-002"]
        assert len(found) == 1 and "(page)" in found[0].message, scheme
    page_doc = supplied(TEXT, DOC_ID, "page")
    assert "ES-SRC-002" not in codes(structural_checks(parse(text, texts=[page_doc])))
    assert "ES-SRC-002" in codes(structural_checks(parse(text.replace("(p. 48)", "(l. 12)"), texts=[page_doc])))


def test_supplied_text_locator_scheme_defaults_to_none():
    assert SuppliedText(document_id="d", text="t").locator_scheme == "none"


# --------------------------------------------------- quotation form (ES-SRC-006 / 007)


def test_initial_capital_difference_is_a_form_warning_not_an_invented_quotation():
    docs = {"ex1": EXTRACT}
    case_only = check_excerpt("for the immense majority of people there was only one victim: Bayardo San Roman.", "ex1", docs)
    assert case_only.status == "found_inexact" and "initial capital" in case_only.detail and case_only.located and not case_only.ok
    invented = check_excerpt("the court washed the blood from the verdict", "ex1", docs)
    assert invented.status == "not_found"
    report = parse_ex1(fx.EXAMPLE1_BODY_2, rid="rep-b2")
    findings = ADAPTER.structural_checks(report)
    assert codes(findings) == ["ES-SRC-006"]
    [f] = findings
    assert f.severity == "warning" and f.claim_ids == ["p3-q06" if False else "p1-q06"] and "immense majority" in f.message
    assert f.rule_source == structural.RULE_SOURCES["ES-SRC-006"]


def test_verse_line_break_mark_is_a_form_warning():
    verse = SuppliedText(
        document_id="oth", locator_scheme="none",
        text="O, beware, my lord, of jealousy! / It is the green-eyed monster which doth mock / The meat it feeds on.",
    )
    check = check_excerpt("mock the meat it feeds on", "oth", {"oth": verse})
    assert check.status == "found_inexact" and "line-break" in check.detail
    assert check_excerpt("mock / The meat it feeds on", "oth", {"oth": verse}).status == "found"
    report = ADAPTER.parse_response(
        'Iago calls jealousy the monster that will "mock the meat it feeds on" and feeds it.', request_id="r", task_id="t",
        report_id="rep-v", subject="English A: Literature", task_type="analytical_paragraph", supplied_texts=[verse],
    )
    found = {f.code: f for f in ADAPTER.structural_checks(report)}
    assert "ES-SRC-006" in found and "ES-SRC-001" not in found


def test_elided_quotation_is_reported_as_information_and_far_apart_fragments_are_not_found():
    docs = {"ex1": EXTRACT}
    near = check_excerpt("They burst panting ... Father Amador's desk", "ex1", docs)
    assert near.status == "found_elided" and "span" in near.detail
    far = check_excerpt("The lawyer ... to blame", "ex1", docs)
    # round 3: fragments that all occur in order but span more than the elision window are a long elision, a
    # form difference reported as a warning (INT-REQ-010 / ES-SRC-006), never an exact match and never 'invented'
    assert far.status == "found_long_elision" and not far.ok and "long elision" in far.detail
    report = parse_ex1('The surrender is frantic: "They burst panting ... Father Amador\'s desk" indeed.')
    found = {f.code: f for f in ADAPTER.structural_checks(report)}
    assert "ES-SRC-007" in found and found["ES-SRC-007"].severity == "info" and "ES-SRC-001" not in found


def test_joined_fragments_must_be_close_together():
    docs = {"ex1": EXTRACT}
    stitched = "They burst panting into the parish house, the priest recalled the surrender as an act of great dignity"
    assert check_excerpt(stitched, "ex1", docs).status == "not_found"
    genuine_join = check_excerpt("We killed him openly, but we're innocent.", "ex1", docs)
    assert genuine_join.status == "found_joined" and "omitted span" in genuine_join.detail
    assert JOIN_GAP_CHARS <= 100


# --------------------------------------------------- minors: style and attribution


def test_es_str_002_band_matches_p13():
    assert (structural.BODY_WORDS_MIN, structural.BODY_WORDS_MAX) == (230, 390)
    words = CLEAN.split()
    text_235 = " ".join(words[:235]) if len(words) >= 235 else CLEAN + " " + " ".join(["word"] * (235 - len(words)))
    assert len(text_235.split()) == 235
    assert "ES-STR-002" not in codes(structural_checks(parse(text_235)))


def test_roman_numeral_i_is_not_first_person():
    text = CLEAN.replace("The setting conveys neglect.", "In Act I the Moor is calm, as Part I of the play shows.")
    assert "ES-STY-001" not in codes(structural_checks(parse(text)))
    assert "ES-STY-001" in codes(structural_checks(parse(CLEAN.replace("The setting conveys neglect.", "The play shows us neglect."))))


def test_our_or_spelling_mix_is_flagged():
    text = CLEAN.replace("marks an absence", "marks an absence that honours the colour of labour while the color and behavior differ")
    found = [f for f in structural_checks(parse(text)) if f.code == "ES-STY-002"]
    assert len(found) == 1 and "honours" in found[0].message and "color" in found[0].message
    british_only = CLEAN.replace("marks an absence", "marks an absence that honours the colour of labour")
    assert "ES-STY-002" not in codes(structural_checks(parse(british_only)))


@pytest.mark.parametrize("phrase", ["as I recall", "if memory serves", "quoting from recollection"])
def test_memory_disclosure_phrasings_are_recognised(phrase):
    text = CLEAN.replace("The setting conveys neglect.", f"The setting, {phrase}, conveys neglect.")
    assert "ES-SRC-003" in codes(structural_checks(parse(text)))


def test_findings_attach_to_truncated_claim_text():
    long_sentence = "I think " + ("the hall is very long and the lamp is very dim and " * 90) + "nothing moves."
    report = parse(long_sentence)
    assert len(report.claims[0].claim_text) == 4000
    found = [f for f in structural_checks(report) if f.code == "ES-STY-001"]
    assert found and found[0].claim_ids == ["p1-point"]


# --------------------------------------------------- generic adapter contracts


def _generic(doc: dict, **kw):
    kwargs = dict(IDS, subject="English A: Literature", task_type="analytical_paragraph", supplied_texts=[supplied()])
    kwargs.update(kw)
    return GenericStructuredAdapter().parse_response(json.dumps(doc), **kwargs)


def _doc(**over) -> dict:
    doc = {
        "original_response": 'The yard is "a measured dose of grey" and the speaker stays silent.',
        "claims": [
            {"claim_id": "e1", "claim_text": '"a measured dose of grey"', "claim_role": "evidence",
             "source_refs": [{"document_id": DOC_ID, "excerpt": "a measured dose of grey"}]},
            {"claim_id": "p1", "claim_text": "The setting conveys neglect.", "claim_role": "point", "supporting_claim_ids": ["e1"]},
        ],
    }
    doc.update(over)
    return doc


def test_claims_with_a_foreign_task_or_agent_are_rejected():
    doc = _doc()
    doc["claims"][0]["task_id"] = "someone-elses-task"
    with pytest.raises(AdapterError, match="task_id"):
        _generic(doc)
    doc = _doc(agent_id="english-specialist")
    doc["claims"][0]["agent_id"] = "maths-specialist"
    with pytest.raises(AdapterError, match="agent_id"):
        _generic(doc)


def test_created_at_must_be_rfc3339():
    with pytest.raises(AdapterError, match="created_at"):
        _generic(_doc(created_at="yesterday-ish"))
    assert _generic(_doc(created_at="2026-10-11T09:00:00Z")).created_at == "2026-10-11T09:00:00Z"
    assert _generic(_doc(created_at="2026-10-11T09:00:00+02:00")).created_at.endswith("+02:00")


def test_gen_str_002_self_support_and_cycles():
    doc = _doc()
    doc["claims"][1]["supporting_claim_ids"] = ["p1"]
    doc["claims"].append({"claim_id": "p2", "claim_text": "The verdict is laundered.", "claim_role": "point", "supporting_claim_ids": ["p3"]})
    doc["claims"].append({"claim_id": "p3", "claim_text": "Laundering is what the verdict does.", "claim_role": "link", "supporting_claim_ids": ["p2"]})
    report = _generic(doc)
    findings = [f for f in GenericStructuredAdapter().structural_checks(report) if f.code == "GEN-STR-002"]
    assert len(findings) == 2 and all(f.severity == "error" for f in findings)
    assert findings[0].claim_ids == ["p1"] and "supports itself" in findings[0].message
    assert findings[1].claim_ids == ["p2", "p3"] and "cycle" in findings[1].message
    # a point/evidence pair linked both ways (support + parent) is not a cycle
    doc2 = _doc()
    doc2["claims"][0]["parent_claim_id"] = "p1"
    assert not [f for f in GenericStructuredAdapter().structural_checks(_generic(doc2)) if f.code == "GEN-STR-002"]
    decision = decide_eligibility(next(c for c in report.claims if c.claim_id == "p1"))
    assert not decision.eligible and decision.eligibility_class.value == "NOT_ELIGIBLE_OTHER"
    assert any("self-reference" in r for r in decision.reasons) and any("other than itself" in r for r in decision.reasons)


def test_blank_excerpt_on_an_unknown_document_is_gen_src_001():
    doc = _doc()
    doc["claims"].append({"claim_id": "e9", "claim_text": "cited", "claim_role": "evidence", "source_refs": [{"document_id": "ghost"}]})
    doc["claims"].append({"claim_id": "e10", "claim_text": "located", "claim_role": "evidence", "source_refs": [{"document_id": DOC_ID, "locator": "p. 3"}]})
    findings = {f.claim_ids[0]: f for f in GenericStructuredAdapter().structural_checks(_generic(doc)) if f.code.startswith("GEN-SRC")}
    assert findings["e9"].code == "GEN-SRC-001" and "was not supplied" in findings["e9"].message
    assert findings["e10"].code == "GEN-SRC-005" and findings["e10"].severity == "warning"


def test_generic_near_miss_statuses_have_their_own_codes():
    doc = _doc()
    doc["claims"][0]["source_refs"] = [{"document_id": DOC_ID, "excerpt": "the lamp stays unlit"}]  # text has "The lamp"
    doc["claims"].append({"claim_id": "e2", "claim_text": "elided", "claim_role": "evidence", "source_refs": [{"document_id": DOC_ID, "excerpt": "The lamp ... ticks on"}]})
    findings = {f.claim_ids[0]: (f.code, f.severity) for f in GenericStructuredAdapter().structural_checks(_generic(doc))}
    assert findings == {"e1": ("GEN-SRC-003", "warning"), "e2": ("GEN-SRC-004", "info")}


# --------------------------------------------------- registry


def test_history_specialist_is_registered_on_import():
    assert {"english-specialist", "generic-structured", "history-specialist"} <= set(registered_ids())
    from epinoic_logic.adapters import history_specialist

    assert history_specialist.ADAPTER is get_adapter("history-specialist")
