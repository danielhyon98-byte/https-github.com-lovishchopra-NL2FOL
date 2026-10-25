"""Security round 2, SEC-V1: the transcription test of the derived figures (``packs._transcribed``) reads the sentences and the
supplied texts once for all the figures of a report (``packs._transcribed_all``).

A derived figure the supplied text states word for word ('burglaries fell by 30% on the CCTV streets') is a transcription,
not the writer's arithmetic, so CORE-QNT-001 is not raised for it. The test was run once per figure, and each run read the
figure's whole sentence into words and every supplied text into words again: many figures beside a long supplied text cost
the product of the two (2,000 figures beside a text of 400,000 characters held a general branch for minutes). The tests of
all the figures are now read in one pass over the distinct sentences and one over each text, with every phrase and every
window found by one automaton of word sequences, and each figure gets the answer it got.
"""
from __future__ import annotations

import random
from types import SimpleNamespace

from epinoic_logic import lexis
from epinoic_logic.branches import packs, quant
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from ..growth import growth


def _old_transcribed(sentence: str, phrase: str, texts) -> bool:
    """The test before the round, kept as data to pin that every figure gets the answer it got."""
    if not phrase or not texts:
        return False
    sent, ph = list(lexis.tokens(sentence)), list(lexis.tokens(phrase))
    if not ph:
        return False
    k = next((i for i in range(len(sent) - len(ph) + 1) if sent[i:i + len(ph)] == ph), -1)
    if k < 0:
        return False
    bodies = [" " + " ".join(lexis.tokens(t.text[:400_000])) + " " for t in texts if t.text]
    for left in (3, 2, 1, 0):
        for right in (3, 2, 1, 0):
            if left + right < 2 or left > k or k + len(ph) + right > len(sent):
                continue
            window = sent[k - left:k + len(ph) + right]
            if len(window) < 4:
                continue
            probe = " " + " ".join(window) + " "
            if any(probe in b for b in bodies):
                return True
    return False


def _text(body: str):
    return SimpleNamespace(text=body)


def _many(n: int):
    """``n`` derived figures, each in its own sentence, beside a supplied text of ``n`` sentences that states none of them."""
    items = [(f"Exports in region {i} rose by 12% over the period.", "rose by 12%") for i in range(n)]
    texts = [_text(" ".join(f"In district {i} the households saved more while firms cut investment." for i in range(n)))]
    return items, texts


def test_many_figures_beside_a_long_supplied_text_are_read_in_linear_time():
    """Four times the figures beside a text four times as long cost about four times as much (before: about sixteen)."""
    small, large = _many(150), _many(600)
    ratio, t_small, t_large = growth(lambda case: packs._transcribed_all(*case), small, large, clear=lexis._cached_token_spans.cache_clear)
    assert ratio < 8.0, (ratio, t_small, t_large)


def _report(answer: str, supplied: str) -> SpecialistReport:
    claim = dict(claim_id="s1.1", claim_text=answer[:2000], claim_role="quantitative")
    return SpecialistReport(report_id="rep", request_id="req", task_id="task", agent_id="economics-specialist", subject="Economics",
                            task_type="short_answer", original_response=answer, response_sha256=sha256_text(answer),
                            created_at="2026-10-12T00:00:00Z", supplied_texts=[SuppliedText(document_id="doc-a", title="Source A", text=supplied)],
                            claims=[ClaimRecord(request_id="req", task_id="task", report_id="rep", agent_id="economics-specialist", subject="Economics",
                                                task_type="short_answer", **claim)])


def _clear() -> None:
    for cached in (quant._analyse, quant._clause_index, quant._worked_equations_of, quant._content_words_of, lexis._cached_token_spans):
        cached.cache_clear()


def test_the_core_packs_undecided_arithmetic_beside_a_long_supplied_text_grows_linearly():
    """The verification's shape through the core pack: many sentences, each a derived figure, beside a long supplied text."""
    def case(n: int) -> SpecialistReport:
        answer = " ".join(f"Exports in region {i} rose by 12% over the period." for i in range(n))
        supplied = " ".join(["Across many regions the households saved more while firms cut investment in the country."] * n)
        return _report(answer, supplied)
    ratio, small, large = growth(CorePack._undecided_arithmetic, case(60), case(240), clear=_clear)
    assert ratio < 8.0, (ratio, small, large)


SUPPLIED = [
    "Burglaries fell by 30% on the CCTV streets, while they rose by 5% elsewhere.",
    "In 2024 its domestic sales grew by 8%, and exports doubled.",
    "Source A: 'Prices rose by 12 per cent in 1923,' the minister said. Unemployment fell from 3.1 million to 2.4 million.",
    "The council's figures show that the number of visitors “grew by 15%” over five years.",
]


def _random_items(n: int, seed: int):
    rnd = random.Random(seed)
    words = ["burglaries", "fell", "by", "30%", "on", "the", "CCTV", "streets", "while", "they", "rose", "5%", "elsewhere", "in", "2024",
             "its", "domestic", "sales", "grew", "8%", "and", "exports", "doubled", "prices", "12", "per", "cent", "1923", "visitors",
             "“grew", "15%”", "over", "five", "years", "it's", "O'Neill", "3.1", "million", "Source", "A:", "'Prices", "x"]
    out = []
    for _ in range(n):
        sent = [rnd.choice(words) for _ in range(rnd.randrange(3, 16))]
        if rnd.random() < 0.6:   # a sentence that copies a run of a supplied text
            src = lexis.tokens(rnd.choice(SUPPLIED))
            a = rnd.randrange(len(src))
            run = list(src[a:a + rnd.randrange(2, 9)])
            k = rnd.randrange(len(sent) + 1)
            sent[k:k] = [w.upper() if rnd.random() < 0.2 else w for w in run]
        sentence = rnd.choice(["", "\"", "("]) + " ".join(sent) + rnd.choice([".", "!", ".”", ""])
        toks = lexis.tokens(sentence)
        if toks and rnd.random() < 0.9:
            i = rnd.randrange(len(toks))
            phrase = " ".join(toks[i:i + rnd.randrange(1, 4)])
        else:
            phrase = rnd.choice(["", "%", "rose by 12%", "fell by 30%"])
        out.append((sentence, phrase))
    return out


def test_every_figure_gets_the_answer_it_got():
    """``_transcribed_all`` (and ``_transcribed``, one test of it) answers every figure as the test before the round did: on
    sentences that copy runs of the supplied texts (case, punctuation and quotation marks aside), with phrases at any
    place of them, against one text, several, an empty one and none."""
    texts_sets = [[_text(t) for t in SUPPLIED], [_text(SUPPLIED[0])], [_text(""), _text(SUPPLIED[2])], [_text(" ".join(SUPPLIED) * 3)], []]
    items = _random_items(3000, seed=21) + [(SUPPLIED[0], "fell by 30%"), ("In 2024 its domestic sales grew by 8%.", "grew by 8%"),
                                             ("Domestic sales grew by 8% in 2024.", "grew by 8%"), ("x", ""), ("", "fell by 30%")]
    true = 0
    for texts in texts_sets:
        want = [_old_transcribed(s, p, texts) for s, p in items]
        assert packs._transcribed_all(items, texts) == want
        for (s, p), w in list(zip(items, want))[:400]:
            assert packs._transcribed(s, p, texts) == w, (s, p)
        true += sum(want)
    assert true > 300


def test_the_phrase_finder_finds_every_occurrence():
    rnd = random.Random(4)
    alphabet = ["a", "b", "c", "ab", "ba"]
    for _ in range(300):
        phrases = {tuple(rnd.choice(alphabet) for _ in range(rnd.randrange(1, 5))) for _ in range(rnd.randrange(1, 8))}
        words = [rnd.choice(alphabet) for _ in range(rnd.randrange(0, 40))]
        got = sorted(packs._PhraseFinder(phrases).occurrences(words))
        want = sorted((i, ph) for ph in phrases for i in range(len(words) - len(ph) + 1) if tuple(words[i:i + len(ph)]) == ph)
        assert got == want, (phrases, words)


def test_a_transcribed_figure_still_raises_no_undecided_arithmetic():
    """Clean controls through the core pack: a figure the supplied text states word for word is a transcription; the same
    figure in other words is the writer's arithmetic and is named undecided."""
    copied = _report("Burglaries fell by 30% on the CCTV streets, so the cameras worked.", SUPPLIED[0])
    assert [f for f in CorePack._undecided_arithmetic(copied) if f.code == "CORE-QNT-001"] == []
    invented = _report("The cameras cut thefts and burglaries fell by 40% in the end.", SUPPLIED[0])
    assert [f.code for f in CorePack._undecided_arithmetic(invented)] == ["CORE-QNT-001"]
