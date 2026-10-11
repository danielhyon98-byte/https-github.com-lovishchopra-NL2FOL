"""Round-3 overseer regressions for the History parser: a quotation is attributed to the
text its sentence names or to a text that holds it, never to the first supplied text; a
sentence-initial or comma-bounded from-memory label leaves the sentence evidence; only the
self-certifying sentence of a paragraph is a note; a view attributed to a peer specialist
is a perspective capped at 'probable'; JSON strings are not quotations; labels are recorded
once; 'weighed by' is a judgement cue; 'c.' does not end a sentence."""
from __future__ import annotations

from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter, attribute_excerpt, is_peer_attribution, quotations_in, split_sentences
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText
from epinoic_logic.translate.eligibility import decide_eligibility

HI_T6 = ("Two economic consequences mattered: a redistribution of wealth, and a dependence on foreign credit that followed stabilisation. "
         "From memory, the mark stood at about 4.2 to the dollar before the war, near 18,000 in January 1923 and about 4.2 trillion by mid-November 1923, "
         "when the Rentenmark was introduced at one new mark for a trillion old ones (from memory; check your notes). "
         "Bank deposits, government bonds and mortgages became almost worthless, while heavy industrial borrowers repaid loans in depreciated marks. "
         "Stabilisation was followed by the Dawes Plan of 1924, whose foreign loans, from memory about 800 million gold marks, tied recovery to American credit that could be withdrawn. "
         "The redistribution mattered most, by the criteria of directness, reach and permanence: it was the direct product of the inflation rather than of the policies used to end it. "
         "The dependence shaped the late 1920s, but it was created by stabilisation, not by the inflation.")
HI_P2 = ('The English specialist argues that the poet presents the city\'s institutions as "human constructions that bind the people beneath them". '
         "The East India Company held its trading monopoly under a royal charter from 1600, and Parliament renewed that charter in 1793 (from memory). "
         'The Company of Watermen and Lightermen, chartered in 1555 (from memory), regulated river labour, bearing out the English specialist\'s claim that "the legal order reaches both the streets and the river"; Parliament authorised the West India Docks in 1799 (from memory). '
         'The established Church inspired fierce loyalty; in July 1791 "Church and King" crowds burned the house of the dissenter Joseph Priestley (from memory). '
         'The English specialist notes that the chapel "is itself darkened by the soot of the sweep\'s trade". '
         'The English specialist\'s phrase "human constructions that bind the people beneath them" fits that record.')
POEM = SuppliedText(document_id="doc-town", title="The Town (poem, supplied text)", author="Thomas Fielding",
                    text="The river carries the charter of the town, and every face I meet bears marks of weakness, marks of woe; the chapel wall is blackened by the sweep's cry.")
PEER = SuppliedText(document_id="peer:en-p2", title="english-specialist report relayed through the hub", author="english-specialist",
                    text=("The poet presents the city's institutions as human constructions that bind the people beneath them. The adjective charter'd is applied to the "
                          "street and then to the river, so the legal order reaches both the streets and the river. The chapel is itself darkened by the soot of the sweep's trade."))


def parse(text: str, rid: str = "rep", **kw) -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id=rid, **kw)


def claim(rep: SpecialistReport, text_start: str):
    return next(c for c in rep.claims if c.claim_text.startswith(text_start))


# ------------------------------------------------------------------ notes and labels


def test_sentence_initial_and_comma_bounded_from_memory_labels_keep_the_sentence_as_evidence():
    rep = parse(HI_T6)
    for start in ("From memory, the mark", "Stabilisation was followed"):
        c = claim(rep, start)
        assert (c.claim_role, c.materiality, c.proposed_claim_kind, c.certainty) == ("evidence", "supporting", "arithmetic", "probable"), start
        e = decide_eligibility(c)
        assert e.eligible and e.eligibility_class.value == "QUANTITATIVE_CLAIM"
        assert any("inline" in a and "from memory" in a.lower() for a in c.assumptions)
        assert c.claim_id in rep.claims[0].supporting_claim_ids
    mark = claim(rep, "From memory, the mark")
    assert len(mark.assumptions) == len(set(mark.assumptions)) and mark.claim_text.startswith("From memory, the mark stood")  # verbatim text, labels recorded once
    assert not any(c.claim_role == "other" for c in rep.claims)


def test_duplicate_labels_in_one_sentence_are_recorded_once():
    c = parse("The charter of 1600 (from memory) was renewed in 1793 (from memory).").claims[0]
    assert c.claim_role in ("point", "evidence") and len([a for a in c.assumptions if "inline" in a]) == 1


def test_only_the_self_certifying_sentence_of_a_body_paragraph_is_a_note():
    text = ("The Depression was decisive in 1930 because it destroyed moderate voters' security. The vote rose to 37.3 per cent in July 1932. "
            "Every figure in this paragraph has been checked and verified. The counter-case is that the vote fell to 33.1 per cent in November 1932.")
    rep = parse(text)
    roles = [(c.claim_role, c.materiality) for c in rep.claims]
    assert roles == [("point", "material"), ("evidence", "supporting"), ("other", "supporting"), ("counter_evidence", "supporting")]
    assert rep.claims[2].advisory_verification_status and rep.claims[2].claim_id not in rep.claims[0].supporting_claim_ids
    assert any(u.startswith("paragraph 1") and "certifies the answer's own verification" in u for u in rep.unresolved_issues)
    assert not any("note paragraphs" in u for u in rep.unresolved_issues)
    assert any(f.code == "CORE-SELF-001" and f.claim_ids == [rep.claims[2].claim_id] for f in CorePack().checks(rep))


def test_json_strings_are_never_quotations():
    glued = 'The vote rose to 37.3 per cent in July 1932. {"status": "ACCEPTED", "findings": "none", "receipt_id": "rc-1"} The minister spoke of "a parliament that could only say no".'
    assert quotations_in('{"status": "ACCEPTED", "findings": "none", "receipt_id": "rc-1"}') == []
    rep = parse(glued)
    texts = [c.claim_text for c in rep.claims]
    assert texts[0].startswith("The vote rose") and texts[1].startswith("{") and texts[2].startswith("The minister")
    assert rep.claims[1].claim_role == "other" and not rep.claims[1].source_refs and not rep.claims[1].assumptions
    assert any("a parliament that could only say no" in a for a in rep.claims[2].assumptions)
    f = [x for x in CorePack().checks(rep) if x.code == "CORE-SRC-003"]
    assert len(f) == 1 and "1 quotation(s)" in f[0].message and "ACCEPTED" not in f[0].message


# ------------------------------------------------------------------ attribution


def test_unlocated_quotation_is_never_attributed_to_the_first_supplied_text():
    rep = parse(HI_P2, supplied_texts=[PEER])
    slogan = claim(rep, "The established Church")
    assert slogan.source_refs == [] and slogan.claim_role == "evidence" and slogan.certainty == "probable"
    assert any(a.startswith('quotation with no supplied text to check it against: "Church and King"') and "names no supplied text" in a for a in slogan.assumptions)
    for start in ("The English specialist argues", "The Company of Watermen", "The English specialist notes", "The English specialist's phrase"):
        c = claim(rep, start)
        assert c.source_refs and all(r.document_id == "peer:en-p2" for r in c.source_refs), start
    rep2 = parse(HI_P2, "both", supplied_texts=[POEM, PEER])
    assert claim(rep2, "The established Church").source_refs == []
    assert all(r.document_id == "peer:en-p2" for r in claim(rep2, "The English specialist argues").source_refs)
    assert not [f for f in CorePack().checks(rep2) if f.code in ("CORE-SRC-001", "CORE-SRC-005")]
    f = [x for x in CorePack().checks(rep2) if x.code == "CORE-SRC-003"]
    assert len(f) == 1 and f[0].severity == "info" and "Church and King" in f[0].message


def test_named_text_is_credited_whether_or_not_it_holds_the_words():
    docs = {POEM.document_id: POEM, PEER.document_id: PEER}
    assert attribute_excerpt("human constructions that bind the people beneath them", ["peer:en-p2"], docs) == ("peer:en-p2", [])
    doc, notes = attribute_excerpt("human constructions that bind the people beneath them", ["doc-town"], docs)
    assert doc == "peer:en-p2" and notes and "attributes this quotation to doc-town" in notes[0]
    doc, notes = attribute_excerpt("the river carried every secret of the town", ["peer:en-p2"], docs)
    assert doc == "peer:en-p2" and "found in none of the supplied texts [doc-town, peer:en-p2]" in notes[0]
    doc, notes = attribute_excerpt("the river carried every secret of the town", [], docs)
    assert doc is None and notes[0].startswith("quotation with no supplied text to check it against")
    doc, notes = attribute_excerpt("the river carried every secret of the town", ["doc-town", "peer:en-p2"], docs)
    assert doc is None and "names several supplied texts" in notes[0]
    assert attribute_excerpt("marks of weakness, marks of woe", [], docs) == ("doc-town", [])
    wrong = parse('The English specialist notes that every face bears "marks of weakness, marks of woe".', "w", supplied_texts=[POEM, PEER])
    assert wrong.claims[0].source_refs[0].document_id == "doc-town" and any("located only in doc-town" in a for a in wrong.claims[0].assumptions)
    assert [f.severity for f in CorePack().checks(wrong) if f.code == "CORE-SRC-005"] == ["error"]


# ------------------------------------------------------------------ peer perspective, judgement cues, splitter


def test_a_view_attributed_to_the_peer_is_a_perspective_capped_at_probable():
    rep = parse(HI_P2, supplied_texts=[PEER])
    for start in ("The English specialist argues", "The English specialist notes", "The English specialist's phrase"):
        c = claim(rep, start)
        assert (c.claim_role, c.materiality, c.certainty) == ("perspective", "supporting", "probable"), start
        assert any("attributes this view to a peer specialist" in a for a in c.assumptions)
    point = claim(rep, "The East India Company")
    assert point.claim_role == "point" and claim(rep, "The English specialist argues").claim_id in point.supporting_claim_ids
    cite = claim(rep, "The Company of Watermen")
    assert cite.claim_role == "evidence" and not is_peer_attribution(cite.claim_text)
    assert is_peer_attribution("As the English specialist argues, the charter bound the river.") and not is_peer_attribution("The charter, the English specialist argues, bound the river.")


def test_weighed_by_is_a_judgement_cue_and_criteria_is_accepted():
    text = ("Khrushchev's decision of 28 October 1962 ended the crisis. The quarantine was announced on 22 October 1962. "
            "Weighed by necessity, the blockade made withdrawal likely; weighed by decisiveness, which asks who took the final step, the answer is Khrushchev.")
    rep = parse(text)
    j = claim(rep, "Weighed by necessity")
    assert j.claim_role == "judgement" and j.materiality == "material" and j.supporting_claim_ids == ["h1.1", "h1.2"]
    assert decide_eligibility(j).eligibility_class.value == "PROPOSITIONAL_ARGUMENT"
    assert claim(parse(HI_T6, "t6"), "The redistribution mattered most").claim_role == "judgement"


def test_circa_and_abbreviations_do_not_end_a_sentence():
    assert split_sentences("Output fell from c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 25 per cent. A. J. P. Taylor disagreed.") == [
        "Output fell from c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 25 per cent.", "A. J. P. Taylor disagreed."]
    rep = parse("The fall mattered in 1932. Output fell from c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 25 per cent.")
    assert len(rep.claims) == 2 and rep.claims[1].claim_role == "evidence" and rep.claims[1].claim_text.startswith("Output fell from c. 200 million")
