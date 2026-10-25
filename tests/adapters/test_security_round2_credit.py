"""Security round 2 (the sweep): the credit of a quotation (``sources.quotation_credit``) reads the names before it in time
linear in the sentence.

For every text named before a quotation the reader copied the sentence up to the name three times and searched the copies
('according to', 'in', a sentence start), copied the gap from the name to the quotation, and searched the rest of the gap
for a clause end: the names times the sentence ('Ashdown writes ' 8,000 times before a quotation took 30 s, quadratic). Two
gap patterns also split a run of white space between two quantifiers (after 'according to' a name, and after "'s words").
The text before a name is now read from its end, the gap with the patterns' own bounds, the clause ends up to the quotation
once, and each run of white space of the two gap patterns once (possessive); every credit is the one the reader gave.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.adapters import sources
from epinoic_logic.adapters.markdown import find_quotation_spans
from epinoic_logic.translate.contracts import SuppliedText

from ..growth import growth

#: The gap pattern after "'s words" before this round (kept as data).
OLD_IN_WORDS_GAP_RE = re.compile(r"['’]s?\s+(?:own\s+)?words\s*[,:]?\s*", re.IGNORECASE)


def _old_quotation_credit(sentence, quote_start, docs, *, other_sources=()):
    """``quotation_credit`` before this round, kept as data to pin that every credit is the one it gave."""
    s = sources
    spans = [(a, b) for a, b, _inner in find_quotation_spans(sentence)]

    def quoted(pos):
        return any(a <= pos < b for a, b in spans)

    mentions = []
    for doc_id, doc in docs.items():
        mentions += [(a, b, doc_id, False) for a, b in s._mentions(sentence, doc) if not quoted(a)]
    for name in other_sources:
        if len(name) >= 3:
            mentions += [(m.start(), m.end(), None, False) for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", sentence) if not quoted(m.start())]
    literary = sorted({d for d, t in docs.items() if not s.is_peer_text(t) and not d.startswith("request:")})
    for m in s._GENERIC_LITERARY_RE.finditer(sentence):
        if not quoted(m.start()):
            kind = " ".join(m.group("kind").casefold().split())
            of_kind = [d for d in literary if kind in s._title_parts(docs[d])[1] or kind in s._author_kinds(docs[d])]
            if kind in s._MATCH_ONLY_KINDS:
                if len(of_kind) == 1:
                    mentions.append((m.start(), m.end(), of_kind[0], True))
                continue
            doc_id = of_kind[0] if len(of_kind) == 1 else literary[0] if len(literary) == 1 else None
            mentions.append((m.start(), m.end(), doc_id, True))
    before = sorted((m for m in mentions if m[1] <= quote_start), key=lambda m: (m[1], m[0]), reverse=True)
    credits = []
    for a, b, doc_id, generic in before:
        gap = sentence[b:quote_start]
        if s._LEADING_CREDIT_RE.search(sentence[:a]) and re.fullmatch(r"\s*,?\s*", gap):
            credits.append((s.Credit(doc_id, sentence[a:b], generic), False))
            continue
        if (s._IN_WORDS_BEFORE_RE.search(sentence[:a]) and OLD_IN_WORDS_GAP_RE.fullmatch(gap)) or (
                s._opens_sentence(sentence[:a]) and s._LABEL_COLON_GAP_RE.fullmatch(gap)):
            credits.append((s.Credit(doc_id, sentence[a:b + len(gap.rstrip())].strip(), generic), False))
            continue
        m = s._CREDIT_GAP_RE.match(gap)
        if m is None:
            continue
        rest = gap[m.end():]
        if s._PRESENTING_RE.search(gap[:m.end()]):
            rest = s._PRESENTED_NOUN_RE.sub(" ", rest, count=1)
        if s._CREDIT_CLAUSE_END_RE.search(rest) and not s._VERB_COLON_REST_RE.fullmatch(rest):
            continue
        credits.append((s.Credit(doc_id, sentence[a:b + m.end()].strip(), generic), bool(re.match(r"\s+that\b", gap[m.end():], re.IGNORECASE))))
    if not credits:
        return s._credit_after(sentence, quote_start, spans, mentions, docs, literary)
    reporting = [c for c, opens_report in credits if opens_report]
    return reporting[0] if reporting else credits[0][0]


POEM = {"doc-1": SuppliedText(document_id="doc-1", title="Allotment, November (poem)", author="Ruth Ashdown (a fictional poet)",
                              text="The frost has taken the last of the beans.")}
DOCS = [
    POEM,
    {"doc-a": SuppliedText(document_id="doc-a", title="Source A", author="A. Historian", text="In 1923 prices rose."),
     "peer:history": SuppliedText(document_id="peer:history", title="History specialist report", author="history-specialist",
                                  text="The History specialist says prices rose.")},
    {"doc-l": SuppliedText(document_id="doc-l", title="Love it? Don't bin it. (council leaflet)", author="Kestrelford Borough Council",
                           text="Recycling saves money.")},
]

#: Many names before one quotation, and long runs of white space where the gap patterns read them.
SHAPES = {
    "names and a verb": lambda n: "Ashdown writes " * (n // 15) + "\"the last of the beans\".",
    "names": lambda n: "Ashdown, " * (n // 9) + "writes \"the last of the beans\".",
    "presenting verbs": lambda n: "Ashdown supplies the frame: " * (n // 28) + "\"the last of the beans\".",
    "according to": lambda n: "According to Ashdown" + " " * n + "x \"the last of the beans\".",
    "in her words": lambda n: "In Ashdown's words" + " " * n + "x \"the last of the beans\".",
}


def _credit(text: str):
    return sources.quotation_credit(text, text.index("\""), POEM)


def test_the_names_before_a_quotation_are_read_in_linear_time():
    """Four times the sentence costs about four times as much (before the round: about sixteen times)."""
    for shape, make in SHAPES.items():
        ratio, small, large = growth(_credit, make(4000), make(16000))
        assert ratio < 8.0, (shape, ratio, small, large)


def _random_sentences(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    words = ["Ashdown", "Ruth Ashdown", "Ashdown's", "the poem", "the poet", "the speaker", "the leaflet", "the council", "Kestrelford Borough Council",
             "Source A", "the History specialist", "Historian", "Hardy", "writes", "says", "argues that", "puts it", "supplies", "offers", "gives",
             "the frame:", "the closure:", "a line:", "himself", "also", "according to", "in the words of", "In", "in", "'s words", "own words",
             ",", ":", ";", ".", "!", "?", " - ", " — ", ", and", ", but", "and", "that", "it", "it:", "words", "x", "the", "We read", "Then",
             "notes", "as", "As", "speaker", "'s speaker", "(", ")", "\n"]
    quotes = ['"the last of the beans"', '"prices rose"', "“Recycling saves money”", "'the frost'", '"x"']
    spaces = [" ", " ", " ", "  ", "", "\n", "\t", "   "]
    out = []
    for _ in range(n):
        toks = []
        for _ in range(rnd.randrange(1, 18)):
            toks.append(rnd.choice(words if rnd.random() < 0.85 else quotes))
            toks.append(rnd.choice(spaces))
        toks.append(rnd.choice(quotes))
        if rnd.random() < 0.4:
            toks.append(rnd.choice(spaces) + rnd.choice(words))
        out.append("".join(toks))
    return out


def _key(c):
    return None if c is None else (c.document_id, c.phrase, c.generic)


def test_every_quotation_is_credited_as_before():
    """Every quotation of sentences built from names, kinds, crediting and presenting verbs, 'according to', "in her
    words", colons, clause ends, dashes and white space is credited as the reader before the round credited it."""
    rnd = random.Random(12)
    calls = credited = 0
    for text in _random_sentences(2500, seed=6) + [make(300) for make in SHAPES.values()]:
        docs = rnd.choice(DOCS)
        others = rnd.choice([(), ("Hardy",), ("Hardy", "Engels")])
        for a, _b, _inner in find_quotation_spans(text):
            got = sources.quotation_credit(text, a, docs, other_sources=others)
            assert _key(got) == _key(_old_quotation_credit(text, a, docs, other_sources=others)), (text, a)
            calls += 1
            credited += got is not None
    assert calls > 4000 and credited > 150


def test_quotations_are_still_credited():
    """Clean controls of the credits the reader gives."""
    assert _key(_credit("Ashdown writes \"the last of the beans\".")) == ("doc-1", "Ashdown writes", False)
    assert _key(_credit("According to Ashdown, \"the last of the beans\" are gone.")) == ("doc-1", "Ashdown", False)
    assert _key(_credit("In Ashdown's words, \"the last of the beans\" are gone.")) == ("doc-1", "Ashdown's words,", False)
    assert _key(_credit("Ashdown writes that the frost came; then \"the last of the beans\" went.")) is None
    assert _key(_credit("Ashdown supplies the frame: \"the last of the beans\".")) == ("doc-1", "Ashdown supplies", False)
