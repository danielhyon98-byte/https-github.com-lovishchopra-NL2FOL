"""Consolidation pass on the shared quotation locator.

Performance: a supplied text's normalised forms and offset maps are built once per
``(document_id, sha256 of the text)`` and kept in a bounded LRU cache, and every locating
answer is memoised per excerpt and document, so one parse or check never locates the same
excerpt in the same document twice. The cached answer is the uncached answer.

Diacritics: a quotation that differs from the supplied text only in its accents ('Bayardo
San Román' quoted from a text printing 'Bayardo San Roman') is located (both sides folded
with NFKD, combining marks dropped, the offset map kept) and reported as a form difference
that names the words, never as an invented quotation; an excerpt that differs only in how
its accented letters are encoded is the same quotation."""
from __future__ import annotations

import threading
import unicodedata

import pytest

from epinoic_logic.adapters.english_specialist.example1_texts import EXAMPLE1_SOURCE_EXTRACT
from epinoic_logic.adapters.sources import check_excerpt, clear_excerpt_cache
from epinoic_logic.translate import grounding as g
from epinoic_logic.translate.contracts import ClaimRecord, SuppliedText
from epinoic_logic.ir.schema import SourceRef

CDF = SuppliedText(document_id="doc-cdf", title="Chronicle of a Death Foretold (extract)", author="Gabriel García Márquez", text=EXAMPLE1_SOURCE_EXTRACT)
VERSE = "London\n\nI wander thro' each charter'd street,\nNear where the charter'd Thames does flow.\n\nIn every cry of every Man,\nIn every Infants cry of fear."


@pytest.fixture(autouse=True)
def _fresh_caches():
    g.clear_grounding_caches()
    clear_excerpt_cache()
    yield
    g.clear_grounding_caches()
    clear_excerpt_cache()


# ------------------------------------------------------------------ performance: cached forms, memoised answers


CASES = [
    ("Bayardo San Roman", EXAMPLE1_SOURCE_EXTRACT),                          # verbatim
    ("We killed him openly, but we're innocent", EXAMPLE1_SOURCE_EXTRACT),   # absent as written
    ("for the immense majority of people", EXAMPLE1_SOURCE_EXTRACT),         # initial capital
    ("poor Bayardo ... remembered over the years", EXAMPLE1_SOURCE_EXTRACT),  # elided
    ("Bayardo San Román", EXAMPLE1_SOURCE_EXTRACT),                          # diacritics
    ("charter'd street, / Near where", VERSE),                               # verse line break as a slash
    ("charter'd Thames does flow. // In every cry", VERSE),                  # stanza break
    ("I wander thro' each charter'd street ... In every Infants cry of fear", VERSE),  # long elision? (short text: elided)
    ("the river carried every secret of the town", VERSE),                   # invented
]


@pytest.mark.parametrize("excerpt,text", CASES)
def test_cached_answers_are_the_uncached_answers(excerpt, text):
    fresh = g.TextForms(text)  # not taken from the cache
    expected = (g._locate_quotation(excerpt, fresh), g._locate_quotation_inexact(excerpt, g.TextForms(text)), g._locate_long_elision(excerpt, g.TextForms(text)))
    for _ in range(3):  # first call computes, later calls are served from the memo
        got = (g.locate_quotation(excerpt, text, document_id="d"), g.locate_quotation_inexact(excerpt, text, document_id="d"), g.locate_long_elision(excerpt, text, document_id="d"))
        assert got == expected
    # without a document id the answer is the same
    assert g.locate_quotation(excerpt, text) == expected[0] and g.find_quotation(excerpt, text) == (None if expected[0] is None else (expected[0].start, expected[0].end, expected[0].matched))


def test_forms_are_keyed_by_document_id_and_text_digest_and_never_stale():
    a = g.text_forms("The lamp stays unlit.", "doc-1")
    assert g.text_forms("The lamp stays unlit.", "doc-1") is a  # one build per (id, sha256)
    b = g.text_forms("The lamp is lit.", "doc-1")  # the same id with another text: other forms, never the stale ones
    assert b is not a and b.norm()[0] == "The lamp is lit."
    assert g.locate_quotation("stays unlit", "The lamp is lit.", document_id="doc-1") is None
    assert g.locate_quotation("stays unlit", "The lamp stays unlit.", document_id="doc-1") is not None
    assert g.text_forms("The lamp stays unlit.", "doc-2") is not a  # another document id is another entry
    assert g.text_sha256("x") == "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"


def test_the_caches_are_bounded_least_recently_used():
    lru = g.BoundedLRU(3, max_weight=10)
    for k in "abc":
        lru.put(k, k.upper(), weight=2)
    assert lru.get("a") == "A"  # a is now the most recently used
    lru.put("d", "D", weight=2)  # four entries: the least recently used (b) goes
    assert lru.get("b") is None and [lru.get(k) for k in "acd"] == ["A", "C", "D"] and len(lru) == 3
    lru.put("e", "E", weight=7)  # weight 13 > 10: evict from the oldest until it fits, the newest entry always kept
    assert lru.get("e") == "E" and lru.weight <= 10
    lru.put("huge", "H", weight=100)
    assert len(lru) == 1 and lru.get("huge") == "H"
    for i in range(g.TEXT_FORMS_MAX_ENTRIES + 20):
        g.text_forms(f"text number {i}", f"doc-{i}")
    assert len(g._TEXT_FORMS) == g.TEXT_FORMS_MAX_ENTRIES
    with pytest.raises(ValueError):
        g.BoundedLRU(0)


def test_a_large_text_is_hashed_once_and_its_forms_are_compact():
    text = ("Every face I meet bears marks of weakness, marks of woe. " * 4000)
    forms = g.text_forms(text, "big")
    chars, idx = forms.norm()
    assert len(idx) == len(chars) and idx.itemsize == 4  # an array of 4-byte offsets, not a list of int objects
    assert g.text_sha256(text) is g.text_sha256(text)  # memoised digest


def test_locating_is_thread_safe():
    expected = [g._locate_quotation(ex, g.TextForms(t)) for ex, t in CASES]
    errors: list[str] = []

    def worker():
        for _ in range(20):
            for (ex, t), want in zip(CASES, expected):
                if g.locate_quotation(ex, t, document_id="d") != want:
                    errors.append(ex)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


# ------------------------------------------------------------------ diacritics


def test_a_quotation_differing_only_in_diacritics_is_located_as_a_form_difference():
    assert g.locate_quotation("Bayardo San Román", EXAMPLE1_SOURCE_EXTRACT) is None  # not the same letters
    match, difference = g.locate_quotation_inexact("Bayardo San Román", EXAMPLE1_SOURCE_EXTRACT)
    assert EXAMPLE1_SOURCE_EXTRACT[match.start:match.end] == match.matched == "Bayardo San Roman"  # offsets into the original text
    assert difference == "differs in diacritics ('Román' where the document has 'Roman')"
    check = check_excerpt("Bayardo San Román", "doc-cdf", {"doc-cdf": CDF})
    assert check.status == "found_inexact" and check.located and not check.ok
    assert "differs in diacritics" in check.detail and f"characters {match.start}-{match.end}" in check.detail
    claim = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="English A: Literature", task_type="analytical_paragraph",
                        claim_id="p4-q02", claim_text='"Bayardo San Román"', claim_role="evidence", source_refs=[SourceRef(document_id="doc-cdf", excerpt="Bayardo San Román")])
    [gc] = g.check_claim_sources(claim, [CDF])
    assert gc.verified is False and "differs in form" in gc.detail and "differs in diacritics" in gc.detail  # the channel's INT-REQ-010 test


def test_diacritics_fold_both_ways_and_with_an_elision_but_a_changed_word_is_still_not_found():
    text = "Gabriel Garcia Marquez wrote the chronicle. For the immense majority of people there was only one victim: Bayardo San Román."
    _m, diff = g.locate_quotation_inexact("García Márquez wrote", text)
    assert diff.startswith("differs in diacritics") and "'García' where the document has 'Garcia'" in diff and "'Márquez' where the document has 'Marquez'" in diff
    elided = check_excerpt("The only one who had lost everything was Bayardo San Román ... as he was remembered", "doc-cdf", {"doc-cdf": CDF})
    assert elided.status == "found_inexact" and "differs in diacritics" in elided.detail and "elided" in elided.detail
    for changed in ("Bayardo San Ramón", "Bayardo Santo Román"):
        assert check_excerpt(changed, "doc-cdf", {"doc-cdf": CDF}).status == "not_found"


def test_accents_encoded_differently_are_the_same_quotation():
    decomposed = unicodedata.normalize("NFD", "the only victim was Bayardo San Román, and the town said café")
    precomposed = unicodedata.normalize("NFC", "Bayardo San Román")
    assert decomposed != unicodedata.normalize("NFC", decomposed)
    m = g.locate_quotation(precomposed, decomposed)
    assert m is not None and m.note == g.NOTE_COMPOSITION and unicodedata.normalize("NFC", m.matched) == precomposed
    end = g.locate_quotation("café", decomposed)  # the accent at the very end belongs to the match
    assert end is not None and decomposed[end.start:end.end] == unicodedata.normalize("NFD", "café")
    docs = {"d": SuppliedText(document_id="d", text=decomposed)}
    assert check_excerpt(precomposed, "d", docs).status == "found"


# ------------------------------------------------------------------ one parse and check: each excerpt located once per document


POEM = SuppliedText(document_id="doc-town", title="The Town", author="Thomas Fielding",
                    text="I wander through each charter'd street,\nNear where the charter'd river flows,\nAnd mark in every face I meet\nMarks of weakness, marks of woe.")
PEER = SuppliedText(document_id="peer:hi-p9", title="history-specialist report relayed through the hub", author="history-specialist",
                    text="The charter of 1600 gave the Company its monopoly. Parliament renewed it in 1793 (from memory).")
ANSWER = ('The town is presented as a legal cage. The speaker marks "Marks of weakness, marks of woe" in every face, and the History specialist '
          'notes that "Parliament renewed it in 1793", so the charter binds the people. The "charter\'d river flows" past them, the '
          '"marks of weakness" return, and "the city sleeps beneath its laws" closes the strand. Thus "Marks of weakness, marks of woe" '
          'is the cost of the charter, and "Marks of Weakness, marks of woe" is its echo.')


def test_one_parse_and_check_never_locates_the_same_excerpt_in_the_same_document_twice(monkeypatch):
    from collections import Counter

    from epinoic_logic.adapters import sources
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.engine import SolverConfig
    from epinoic_logic.integrity import WorkPlan

    calls: Counter = Counter()

    def counting(name, fn):
        def wrapped(excerpt, forms):
            calls[(name, excerpt, g.text_sha256(forms.text))] += 1
            return fn(excerpt, forms)
        return wrapped

    for name in ("_locate_quotation", "_locate_quotation_inexact", "_locate_long_elision"):
        monkeypatch.setattr(g, name, counting(name, getattr(g, name)))
    real_check = sources._check_in_document

    def counting_check(excerpt, cleaned, document_id, doc_text):
        calls[("check_excerpt", excerpt, document_id, g.text_sha256(doc_text))] += 1
        return real_check(excerpt, cleaned, document_id, doc_text)

    monkeypatch.setattr(sources, "_check_in_document", counting_check)
    hub = RouterHub(signing_key=b"grounding-cache-test-key-0123456789", config=SolverConfig(timeout_ms=3000, memory_max_mb=None))
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="English A: Literature", task_type="analytical_paragraph",
                           selected_agent_ids=["english-specialist"], allowed_document_ids=["doc-town", "peer:hi-p9"]))
    m, _, _ = hub.dispatch("t", "english-specialist", "Write one analytical paragraph on the poem. Quote from the poem.", [POEM, PEER])
    reply, rc = hub.receive("t", m.message_id, ANSWER, agent_id="english-specialist", report_id="rep-x")
    assert reply is not None
    # the parser, the core and English packs and the channel all asked about these excerpts; each was located once per text
    assert {k[0] for k in calls} >= {"_locate_quotation", "_locate_quotation_inexact", "check_excerpt"}
    assert max(calls.values()) == 1, sorted(k for k, n in calls.items() if n > 1)
    # and the receipt is the one the checks give: the invented quotation is refuted against the poem under analysis,
    # the changed capital is a form difference
    assert any(f.code == "INT-REQ-003" for f in rc.findings) and any(f.code == "INT-REQ-010" for f in rc.findings)
