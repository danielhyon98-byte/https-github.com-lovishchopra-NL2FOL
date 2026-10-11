"""Grounding and attribution found wanting by the round-4 arena overseers: an elision written in the academic form
("[...]", "[…]", "(...)") reported as an invented quotation, an altered quotation of a colleague credited to no text
when its sentence also named the poet, and agent text with a lone surrogate that the hashing helpers could not hash."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.sources import attribute_excerpt, check_excerpt, credited_spans, governing_document
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.translate.contracts import ClaimRecord, SuppliedText, sha256_text
from epinoic_logic.translate.grounding import check_claim_sources, locate_long_elision, locate_quotation, text_sha256, unbracket_elisions

POEM = SuppliedText(document_id="doc-wb", title="Composed upon Westminster Bridge, September 3, 1802 (sonnet, supplied text)", author="William Wordsworth",
                    text="Earth has not anything to show more fair:\nDull would he be of soul who could pass by\nA sight so touching in its majesty:\n"
                         "This City now doth, like a garment, wear\nThe beauty of the morning; silent, bare,")
PEER = SuppliedText(document_id="peer:hi-p3c", title="history-specialist report rep-hi-p3c-0 relayed through the hub", author="history-specialist",
                    text="The Peace of Amiens, signed on 25 March 1802, ended a war. It was a lull rather than a settlement, and war resumed in May 1803.")
DOCS = {POEM.document_id: POEM, PEER.document_id: PEER}


# ------------------------------------------------------------ bracketed and parenthesised elisions


@pytest.mark.parametrize("mark", ["[...]", "[…]", "[ . . . ]", "(...)", "(…)"])
def test_a_bracketed_or_parenthesised_elision_is_an_elided_quotation_never_invented(mark):
    excerpt = f"Earth has not anything {mark} more fair"
    match = locate_quotation(excerpt, POEM.text)
    assert match is not None and match.elided and match.matched.startswith("Earth has not anything")
    assert check_excerpt(excerpt, "doc-wb", DOCS).status == "found_elided"
    claim = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="english-specialist", subject="English A: Literature", task_type="analytical_paragraph",
                        claim_id="c1", claim_text=f'The boast "{excerpt}" sets the scale.', claim_role="evidence", source_refs=[SourceRef(document_id="doc-wb", excerpt=excerpt)])
    [g] = check_claim_sources(claim, [POEM])
    assert g.verified is not False, g.detail


def test_a_changed_word_beside_a_bracketed_elision_is_still_not_found():
    assert locate_quotation("Earth has not anything [...] more foul", POEM.text) is None
    assert check_excerpt("Earth has not anything [...] more foul", "doc-wb", DOCS).status == "not_found"
    assert unbracket_elisions("a (sic) word [1802]") == "a (sic) word [1802]"  # only an ellipsis in brackets is an elision mark


def test_a_long_bracketed_elision_is_a_form_difference():
    far = locate_long_elision("Earth has not anything [...] the morning", POEM.text + "\n" + "x " * 400 + "\nthe morning")
    assert far is not None and "long elision" in far[1]


# ------------------------------------------------------------ attribution in a sentence that names several texts


def test_the_possessive_governing_an_altered_peer_quotation_credits_the_peer():
    sentence = "Wordsworth's clear morning and the History specialist's \"lull rather than a peace\" belong together."
    doc, notes = attribute_excerpt("lull rather than a peace", ["doc-wb", "peer:hi-p3c"], DOCS, sentence=sentence)
    assert doc == "peer:hi-p3c" and "possessive governs the quotation" in notes[0] and "doc-wb, peer:hi-p3c" in notes[0]


def test_the_reporting_clause_credits_its_speaker():
    outer = "The History specialist argues that Wordsworth presents \"a calm so very deep\" in the poem."
    assert governing_document(outer, "a calm so very deep", ["doc-wb", "peer:hi-p3c"], DOCS)[0] == "peer:hi-p3c"
    inner = "The History specialist dates the peace, but Wordsworth writes \"a calm so very deep\"."
    assert governing_document(inner, "a calm so very deep", ["doc-wb", "peer:hi-p3c"], DOCS)[0] == "doc-wb"


def test_with_the_sentence_a_quotation_is_never_credited_to_none_when_texts_are_named():
    doc, notes = attribute_excerpt("an invented line", ["doc-wb", "peer:hi-p3c"], DOCS, sentence="Both the poem and the colleague's report say \"an invented line\".")
    assert doc in ("doc-wb", "peer:hi-p3c") and not notes[0].startswith("quotation with no supplied text")
    # without the sentence the shared rule is unchanged (a caller that cannot give it keeps the old answer)
    doc, notes = attribute_excerpt("an invented line", ["doc-wb", "peer:hi-p3c"], DOCS)
    assert doc is None and "names several supplied texts" in notes[0]
    # a located quotation is credited as before, whatever the sentence
    assert attribute_excerpt("a lull rather than a settlement", ["doc-wb", "peer:hi-p3c"], DOCS, sentence="x")[0] == "peer:hi-p3c"


def test_credited_spans_cover_the_clause_the_peer_speaks_in():
    s = "The scale matters, because the History specialist gives close to two million inhabitants and calls London large; the poem is from 1802."
    [(a, b)] = credited_spans(s, PEER)
    assert "two million" in s[a:b] and "1802" not in s[a:b]
    assert credited_spans("The poem, unlike the History specialist, is calm.", PEER) == []


# ------------------------------------------------------------ hashing agent text never raises


def test_hashing_text_with_a_lone_surrogate_never_raises_and_valid_text_is_unchanged():
    import hashlib
    assert sha256_text("emoji \U0001F600 ok") == hashlib.sha256("emoji \U0001F600 ok".encode("utf-8")).hexdigest()
    assert len(sha256_text("half \ud83d")) == 64 and len(text_sha256("half \ude00")) == 64
    assert sha256_text("half \ud83d") != sha256_text("half \ude00")


def test_r3_hi_p2d_altered_quotation_of_the_english_specialist_is_credited_to_the_peer():
    london = SuppliedText(document_id="doc-london", title="London", author="William Blake", text="I wander thro' each charter'd street,\nNear where the charter'd Thames does flow.")
    peer = SuppliedText(document_id="peer:en-p2d", title="english-specialist report relayed through the hub", author="english-specialist",
                        text="Blake presents the city's institutions as human constructions that bind the people beneath them.")
    docs = {london.document_id: london, peer.document_id: peer}
    sentence = "The English specialist argues that Blake presents the city's institutions as \"human constructions that bind thely people beneath them\"."
    doc, notes = attribute_excerpt("human constructions that bind thely people beneath them", ["doc-london", "peer:en-p2d"], docs, sentence=sentence)
    assert doc == "peer:en-p2d" and "reporting clause" in notes[0]
