"""Integration gate 2 (before arena round 8): the parsers' input stalls, and the combinator's verdicts read as self-reports.

Critical findings fixed at their cause, each held to the replaced pattern (kept here as the specification) on random texts, to the
finding's worst-case input with a wide time bound, and through the hub:

* the English parser's sentence boundary (``english_specialist.parser._BOUNDARY_RE``) read a run of stops that no blank and capital
  follow again from each of its stops (parser-safety, 'x = 9' + '!' * 20,000: 58 s per receive, hours at the size limit); it is now read
  from the run's first stop with possessive runs, as the shared splitter reads it;
* ``markdown.strip_markup`` paired fences with a lazy pattern read to the end of the text from every opener with no closer ('```a' on
  every line: 3.3 s at 40,000 characters); the fences are now paired in one pass (``markdown.fence_blocks``), and the pasted-JSON blocks,
  the same shape ('{x' on every line: 2.8 s at 20,000), likewise (``markdown._json_block_spans``).

Found by the sweep of the same class in these modules (each fixed the same way, with its old reading kept as the specification):

* the English splitter searched the growing segment before every inline list number ('Fix it: 1. A; 1. A; ...': 80 s at 160,000
  characters) and counted the marks of a label chunk again at every line break inside a quotation;
* ``sources`` read the whole text before every full stop for an abbreviation ('. ' * k: 3.4 s at 10,000), and the credit of a quotation
  read the text again from every mention, for every quotation (1.1 s at 10,000 characters, n³ steps): the stop reads a window, and the
  credit reads its sentence once (``sources._sentence_layout``, ``_sentence_mentions``, ``_clause_marks``) and at most
  ``sources._MAX_CREDIT_MENTIONS`` mentions back;
* the gaps between a name and what it credits (``sources._CREDIT_GAP_RE``, ``_POSSESSIVE_GAP_RE``, ``_BLANK_COMMA_RE``, the agent view
  verb) split a gap of blanks in every way (0.84 s at 1,000 blanks; 83 s for a text of mentions each followed by 200 blanks), and
  ``credited_agents`` copied the text for every quotation;
* the English misattribution check (``ES-SRC-008``) tried every name of a sentence against every quotation, n³ steps (minutes at 80,000
  characters): each sentence's quotations, clause breaks and names are read once (``english_specialist.structural._SentenceMarks``);
* the closing of an accuracy adjective and the synthesis's proof and verdict labels (``markdown._SELF_CLOSING_RE``,
  ``_SYNTH_PROOF_LABEL_RE``, ``_SYNTH_VERDICT_LABEL_RE``) split a run of blanks around an optional comma or stop (0.87 s at 8,000
  blanks); the pasted JSON blocks kept a match object per line (the growth crept above linear);
* a structured report's finding that names hundreds of claims made a message longer than a finding may be, and the checks raised.

Finding 7 (major): the combinator's verdict on what it wrote ("The answer is correct.", "(signed engine result)", "Overseer verdict:
pass.", "Correct: ...", "...; this is fully reliable.") is a self-report on a synthesis (INT-LEDGER-029), while the negated, failed and
credited forms, and every form on a specialist's branch, stay clean.

The sweep tests feed every public entry point of each module the standard hostile inputs (``hostile_inputs``) and assert a time bound
with a wide margin."""
from __future__ import annotations

import itertools
import json
import random
import re
import time

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import sources as src
from epinoic_logic.adapters.base import AdapterError
from epinoic_logic.adapters.english_specialist import parser as en
from epinoic_logic.adapters.english_specialist import structural as en_structural
from epinoic_logic.adapters.generic_structured import (
    GenericStructuredAdapter, generic_cycle_findings, generic_duplicate_findings, generic_link_findings, generic_source_findings,
)
from epinoic_logic.adapters.stem_specialist.parser import StemTextParser, claim_id_for, stem_profile_key
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText

from ..growth import growth
from ..timing import empty_caches
from .hostile_inputs import HOSTILE, all_inputs, bounded

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
KEY = b"integration-gate-2-parsers-key-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
#: A call of a public entry point on a hostile input of about 20,000 characters: a linear reader takes a few hundredths of a second.
CALL_BOUND = 3.0
#: A whole parse of such an answer.
PARSE_BOUND = 10.0


def _random_texts(alphabet, seed: int, n: int, longest: int = 24):
    rng = random.Random(seed)
    for _ in range(n):
        yield "".join(rng.choice(alphabet) for _ in range(rng.randint(0, longest)))


def _receive(subject: str, agent: str, answer: str, request: str = "Answer the question.", docs=()):
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, request, list(docs))
    t = time.perf_counter()
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return time.perf_counter() - t, rc


# --------------------------------------------------------------------------- the English parser's sentence boundary (critical)

OLD_BOUNDARY_RE = re.compile(r"(?:[.!?]+[\"”’')\]»]*|[}\]])(?=\s+(?:[\"“‘(\[«„]?[A-ZÀ-ÖØ-Þ0-9]|[{\[]\s*\"))")


def test_the_english_boundaries_are_those_of_the_old_pattern():
    alphabet = [".", "!", "?", "...", '"', "”", "’", "'", ")", "]", "»", "}", "{", "[", " ", "  ", "\t", "\n", "A", "b", "9", "x", '{"', "e.g.", "(", "«"]
    for text in _random_texts(alphabet, 31, 40000, longest=20):
        assert [m.span() for m in en._BOUNDARY_RE.finditer(text)] == [m.span() for m in OLD_BOUNDARY_RE.finditer(text)], repr(text)


@pytest.mark.parametrize("make", [
    lambda n: "x = 9" + "!" * n,        # the finding's input: a run of stops that no blank and capital follow
    lambda n: "x = 9" + "?!." * (n // 3),
    lambda n: "It rose" + "." * n + " ok",
])
def test_a_long_run_of_stops_is_split_in_linear_time_by_the_english_parser(make):
    t = time.perf_counter()
    en.split_sentences(make(400_000))
    assert time.perf_counter() - t < 3.0  # before the gate: 6.9 s at 20,000 characters, hours at 400,000
    ratio, small, large = growth(en.split_sentences, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)
    assert en.split_sentences("It rose. Then it fell!!! " + "!" * 50) == ["It rose.", "Then it fell!!! " + "!" * 50]


def test_an_english_answer_ending_in_a_run_of_stops_crosses_the_hub_in_seconds():
    elapsed, rc = _receive("English A: Language and Literature", "english-specialist", "x = 9" + "!" * 20_000)
    assert elapsed < 10.0  # before the gate: 58 s per receive at 20,000 (and 29.6 s more in the audit)
    assert rc.status.value.startswith("ACCEPTED")


OLD_INLINE_LIST_NUMBER_RE = re.compile(r"(?:^|[:;—–]\s*)\(?\d{1,2}\)?$")


def test_the_inline_list_number_is_read_from_the_end_of_its_segment_as_the_search_of_the_segment_read_it():
    alphabet = [":", ";", "—", "–", " ", "  ", "1", "12", "(", ")", "(3)", "x", ".", "A", "Fix it", " ", "٣"]
    for text in _random_texts(alphabet, 32, 30000, longest=14):
        for prev in range(0, len(text) + 1, 3):
            for end in range(prev, len(text) + 1, 2):
                found = re.search(r"\S", text[prev:end])
                lead = prev + found.start() if found else end
                assert en._inline_list_number(text, prev, end, lead) == bool(OLD_INLINE_LIST_NUMBER_RE.search(text[prev:end].strip())), (repr(text), prev, end)


def _old_label_chunks(paragraph: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    for m in en._LINE_LABEL_BREAK_RE.finditer(paragraph):
        head = paragraph[start:m.start()]
        if head.count('"') % 2 or head.count("“") != head.count("”") or head.count("«") != head.count("»"):
            continue
        chunks.append(head)
        start = m.end()
    chunks.append(paragraph[start:])
    return [en._LINE_BULLET_RE.sub("", c, count=1) for c in chunks if c.strip()]


def test_the_label_chunks_are_those_of_the_recount_and_a_paragraph_of_inline_numbers_is_split_in_linear_time():
    alphabet = ["\n", "Fix it: ", "Model: ", "- ", "* ", '"', "“", "”", "«", "»", "x ", "A. ", "1. "]
    for text in _random_texts(alphabet, 33, 30000, longest=12):
        assert en._label_chunks(text) == _old_label_chunks(text), repr(text)
    for make in (lambda n: "Fix it: 1. A" + "; 1. A" * (n // 6),                          # the sweep's input: 80 s at 160,000 characters
                 lambda n: '"' + "\nModel: x" * (n // 10),                                  # a quotation left open before every labelled line
                 lambda n: "p. 1 " * (n // 5)):                                            # abbreviations that never cut
        t = time.perf_counter()
        en.split_sentences(make(400_000))
        assert time.perf_counter() - t < 3.0
        ratio, small, large = growth(en.split_sentences, make(20_000), make(80_000), clear=empty_caches)
        assert ratio < LINEAR, (ratio, small, large)
    assert en.split_sentences("Fix it: 1. Choose a quotation. 2. Add the effect.") == ["Fix it: 1. Choose a quotation.", "2. Add the effect."]


# --------------------------------------------------------------------------- fences and pasted JSON blocks in strip_markup (critical)

OLD_FENCE_PARTS_RE = re.compile(r"^[ \t]*(```|~~~)[ \t]*([^\n]*)\n(.*?)^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)


def _old_strip_json_blocks(text: str):
    removed = 0

    def take(m):
        nonlocal removed
        if md.is_json_block(m.group(0)):
            removed += 1
            return ""
        return m.group(0)
    return md.JSON_BLOCK_RE.sub(take, text), removed


def test_the_fences_and_the_json_blocks_are_those_of_the_patterns():
    alphabet = ["`", "```", "~~~", "````", "~", "a", "json", " ", "\t", "\n", "\n\n", "x", "{", "}", "[", "]", '"k": 1', ",", "\r", "  ```", "```  ", "\n```\n"]
    for text in _random_texts(alphabet, 34, 60000, longest=22):
        assert md.fence_blocks(text) == [(m.start(), m.end(), m.group(2), m.group(3)) for m in OLD_FENCE_PARTS_RE.finditer(text)], repr(text)
        assert [(a, b) for a, b, _i, _b in md.fence_blocks(text)] == [m.span() for m in md.FENCE_BLOCK_RE.finditer(text)], repr(text)
        assert md._json_block_spans(text) == [m.span() for m in md.JSON_BLOCK_RE.finditer(text)], repr(text)
        assert md.strip_json_blocks(text) == _old_strip_json_blocks(text), repr(text)
    for length in range(0, 7):
        for chars in itertools.product(["`", "~", "\n", " ", "a", "{", "}"], repeat=length):
            text = "".join(chars).replace("`", "```").replace("~", "~~~")
            assert md.fence_blocks(text) == [(m.start(), m.end(), m.group(2), m.group(3)) for m in OLD_FENCE_PARTS_RE.finditer(text)], repr(text)
            assert md._json_block_spans(text) == [m.span() for m in md.JSON_BLOCK_RE.finditer(text)], repr(text)
    # a fence of prose keeps its body, code is removed, a stray fence line is removed
    prose = "```\n" + "The poem turns on its last line, which reverses the image. " * 3 + "\n```"
    assert "reverses the image" in md.strip_markup(prose) and "```" not in md.strip_markup(prose)
    assert md.strip_markup("Before.\n```python\nx = 1\n```\nAfter.") == "Before.\n\nAfter."


@pytest.mark.parametrize("make", [
    lambda n: "```a\n" * (n // 5),           # the finding's input: openers with a tag and no closer
    lambda n: "~~~a\n" * (n // 5),
    lambda n: "```" + " " * n + "x",          # an opener whose line never ends
    lambda n: "{x\n" * (n // 3),              # lines of unclosed brackets (pasted JSON blocks)
    lambda n: "[\n" * (n // 2),
])
def test_unclosed_fences_and_brackets_are_stripped_in_linear_time(make):
    t = time.perf_counter()
    md.strip_markup(make(400_000))
    assert time.perf_counter() - t < 2.0  # before the gate: 3.3 s at 40,000 characters ('```a'), 2.8 s at 20,000 ('{x')
    ratio, small, large = growth(md.strip_markup, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


@pytest.mark.parametrize("subject,agent", [("History", "history-specialist"), ("English A: Language and Literature", "english-specialist")])
def test_an_answer_of_unclosed_fences_crosses_the_hub_in_seconds(subject, agent):
    elapsed, rc = _receive(subject, agent, "```a\n" * 8_000)
    assert elapsed < 10.0  # before the gate: 21.6 s per History receive at 40,000 characters (13.6 s more in the audit)
    assert rc.status is not None


# --------------------------------------------------------------------------- sources: the stops and the credits (sweep)

OLD_ABBREVIATION_RE = re.compile(r"(?:^|[\s(\[])(?:c|ca|cf|approx|circa|e\.g|i\.e|vs|viz|vol|pp?|nos?|fig|St|Mr|Mrs|Ms|Dr|Jr|Sr|Gen|Col|Capt|Lt|Rev|Prof|Mt|[A-Z])$",
                                 re.IGNORECASE)
POEM = SuppliedText(document_id="d1", title="The Prelude", author="William Wordsworth", text="The river ran. A boy rowed out at night.")
PEER = SuppliedText(document_id="peer:t1", title="History report", author="history-specialist", text="The treaty was signed in 1919 and the war ended.")
DOCS = {"d1": POEM, "peer:t1": PEER}
CREDIT_TOKENS = ["Wordsworth", "Wordsworth's", "the History specialist", "the History specialist's", " says", " argues that", " notes", " gives",
                 " supplies the frame: ", " view that", "'s view is that", "according to", " in the words of", " as reported by", " the", ", ", "; ",
                 ". ", ": ", " - ", ", and ", " c. 1900", " 5.2 million", " Hardy", " I ", " Tomas", " x", '"the river ran"', '"a b"',
                 "'quoted words'", " himself", " The", "  ", "\n", "(", ")"]


def _old_quotation_credit(sentence, quote_start, docs, *, other_sources=()):
    """The credit rule as it read before integration gate 2 (every mention, every quotation, read again): the specification."""
    spans = [(a, b) for a, b, _inner in md.find_quotation_spans(sentence)]

    def quoted(pos):
        return any(a <= pos < b for a, b in spans)
    mentions = []
    for doc_id, doc in docs.items():
        mentions += [(a, b, doc_id, False) for a, b in src._mentions(sentence, doc) if not quoted(a)]
    for name in other_sources:
        if len(name) >= 3:
            mentions += [(m.start(), m.end(), None, False) for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", sentence) if not quoted(m.start())]
    literary = sorted({d for d, t in docs.items() if not src.is_peer_text(t) and not d.startswith("request:")})
    for rx in (src._GENERIC_LITERARY_RE, src._GENERIC_SOURCE_RE):
        for m in rx.finditer(sentence):
            if not quoted(m.start()):
                mentions.append((m.start(), m.end(), literary[0] if len(literary) == 1 else None, True))
    before = sorted((m for m in mentions if m[1] <= quote_start), key=lambda m: (m[1], -m[0]), reverse=True)
    credits = []
    for a, b, doc_id, generic in before:
        gap = sentence[b:quote_start]
        if src._LEADING_CREDIT_RE.search(sentence[:a]) and re.fullmatch(r"\s*,?\s*", gap):
            credits.append((src.Credit(doc_id, sentence[a:b], generic), False))
            continue
        m = src._CREDIT_GAP_RE.match(gap)
        if m is None:
            continue
        rest = gap[m.end():]
        if src._PRESENTING_RE.search(gap[:m.end()]):
            rest = src._PRESENTED_NOUN_RE.sub(" ", rest, count=1)
        if src._CREDIT_CLAUSE_END_RE.search(rest):
            continue
        if m.group("view") and re.search(r"(?<![\w'’])(?!I\b)[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]", rest):
            continue
        credits.append((src.Credit(doc_id, sentence[a:b + m.end()].strip(), generic), bool(re.match(r"\s*that\b", gap[m.end():], re.IGNORECASE))))
    if not credits:
        return None
    reporting = [c for c, opens in credits if opens]
    return reporting[0] if reporting else credits[0][0]


def _old_credited_spans(sentence, doc):
    out = []
    for a, b in src._mentions(sentence, doc):
        rest = sentence[b:]
        leading = src._ACCORDING_TO_RE.search(sentence[:a])
        if not (rest.startswith(("'s", "’s", "'", "’")) or src._REPORTING_VERB_RE.match(rest) or leading):
            continue
        end = src._clause_end(rest)
        if leading and not re.search(r"[^\W_]", rest[:end]):
            out.append((src._clause_start(sentence[:leading.start()]), leading.start()))
            continue
        out.append((b, b + end))
    return out


def test_the_stops_and_the_credits_are_read_as_the_rescans_read_them():
    alphabet = [" ", "(", "[", "c", "ca", "approx", "circa", "e.g", "i.e", "A", "z", "St", "Mr", "x", "1", ".", "pp", "nos", "fig", "\t", "Ab", "Approx"]
    for text in _random_texts(alphabet, 35, 30000, longest=8):
        for end in range(len(text) + 1):
            assert src._abbreviation_before(text, end) == bool(OLD_ABBREVIATION_RE.search(text[:end])), (repr(text), end)
    rng = random.Random(36)
    checked = 0
    for _ in range(20000):
        sentence = "".join(rng.choice(CREDIT_TOKENS) for _ in range(rng.randint(1, 14)))
        for doc in (POEM, PEER):
            assert src.credited_spans(sentence, doc) == _old_credited_spans(sentence, doc), (repr(sentence), doc.document_id)
        for a, _b, _inner in md.find_quotation_spans(sentence):
            for others in ((), ("Hardy",)):
                new, old = src.quotation_credit(sentence, a, DOCS, other_sources=others), _old_quotation_credit(sentence, a, DOCS, other_sources=others)
                assert (new and (new.document_id, new.phrase, new.generic)) == (old and (old.document_id, old.phrase, old.generic)), (repr(sentence), a)
                checked += 1
    assert checked > 5000


@pytest.mark.parametrize("make", [
    lambda n: ". " * (n // 2),                                         # the sweep's input: 3.4 s at 10,000 characters
    lambda n: "\n1. " * (n // 4),
    lambda n: "Wordsworth says " * (n // 16) + "x.",                   # mentions read again from each mention
    lambda n: "x according to Wordsworth; " * (n // 27),
])
def test_the_clause_reader_and_the_credited_spans_are_linear(make):
    def read(text):
        src.clause_boundaries(text)
        src.credited_spans(text, POEM)
    t = time.perf_counter()
    read(make(400_000))
    assert time.perf_counter() - t < 3.0
    ratio, small, large = growth(read, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


def test_a_sentence_of_many_quotations_and_mentions_is_credited_in_linear_time():
    from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter

    def parse(text):
        HistorySpecialistAdapter().parse_response(text, request_id="q", task_id="t", report_id="r", task_type="essay", supplied_texts=[POEM, PEER])
    make = lambda n: 'Wordsworth says "the treaty was signed" ' * (n // 40) + "x."  # noqa: E731 - the sweep's input: 1.1 s at 10,000, n³
    t = time.perf_counter()
    parse(make(100_000))
    assert time.perf_counter() - t < 10.0
    # both sizes above the readers' per-sentence cache limit (16,000 characters): below it a sentence read by several readers is
    # answered once, above it each reader reads it afresh, a constant factor at the limit rather than growth
    ratio, small, large = growth(parse, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- sources: the gaps of a credit (sweep: adjacent blank runs)

OLD_POSSESSIVE_GAP_RE = re.compile(r"^['’]s?\s*[\"'“”‘’«»„]?\s*$")
OLD_CREDIT_GAP_RE = re.compile(
    r"^(?:['’]s?\s*[,:]?\s*$"
    r"|(?:['’]s?(?:\s+own)?(?:\s+" + src._CREDIT_NOUNS + r")?)?\s*,?\s+(?:" + src._CREDIT_ADVERBS + r"\s+)*" + src._CREDIT_VERBS + r"\b"
    r"|(?P<view>['’]s\s+(?:own\s+)?" + src._VIEW_NOUNS + r"\s+(?:is\s+)?(?=that\b)))",
    re.IGNORECASE)
OLD_CREDIT_GAP_AT_RE = re.compile(OLD_CREDIT_GAP_RE.pattern.removeprefix("^"), re.IGNORECASE)
OLD_BLANK_COMMA_RE = re.compile(r"\s*,?\s*")
#: Compiled inside ``credited_agents`` before the gate.
OLD_AGENT_VIEW_VERB_RE = re.compile(r"\s*,?\s+(?:" + src._CREDIT_ADVERBS + r"\s+)*(?:" + src._CREDIT_VERBS + "|" + src._VIEW_VERBS + r")\b", re.IGNORECASE)
GAP_ALPHABET = [" ", "  ", "\t", "\n", ",", ", ", ":", "'", "’", "'s", "’s", "own", "speaker", "poem", "view", "claim", "is", "that", "also", "then",
                "rightly", "says", "notes", "argues", "believes", "regards", "x", '"', "“", "«", "."]


def _span_and_view(m):
    return m and (m.span(), m.span("view") if "view" in m.re.groupindex else None)


def test_the_gaps_of_a_credit_are_those_of_the_old_patterns():
    rng = random.Random(31)
    for text in _random_texts(GAP_ALPHABET, 32, 60000, longest=10):
        for new, old in ((src._POSSESSIVE_GAP_RE, OLD_POSSESSIVE_GAP_RE), (src._CREDIT_GAP_RE, OLD_CREDIT_GAP_RE),
                         (src._AGENT_VIEW_VERB_RE, OLD_AGENT_VIEW_VERB_RE)):
            assert _span_and_view(new.match(text)) == _span_and_view(old.match(text)), (new.pattern[:40], repr(text))
        assert bool(src._BLANK_COMMA_RE.fullmatch(text)) == bool(OLD_BLANK_COMMA_RE.fullmatch(text)), repr(text)
        pos = rng.randint(0, len(text))
        end = rng.randint(pos, len(text))
        assert _span_and_view(src._CREDIT_GAP_AT_RE.match(text, pos, end)) == _span_and_view(OLD_CREDIT_GAP_AT_RE.match(text, pos, end)), (pos, end, repr(text))
        assert bool(src._BLANK_COMMA_RE.fullmatch(text, pos, end)) == bool(OLD_BLANK_COMMA_RE.fullmatch(text, pos, end)), (pos, end, repr(text))


@pytest.mark.parametrize("make", [
    lambda n: "Wordsworth" + " " * n + 'x "the river ran".',                  # 0.84 s at 1,000 blanks before the gate, n² (hours at the limit)
    lambda n: "Wordsworth's" + " " * n + 'x "the river ran".',
    lambda n: "According to Wordsworth" + " " * n + 'x "the river ran".',
    lambda n: "Wordsworth" + " ," * (n // 2) + ' says "the river ran".',
])
def test_a_long_gap_between_a_name_and_its_quotation_is_read_in_linear_time(make):
    def credit(text):
        src.quotation_credit(text, text.index('"'), DOCS)
        src.credited_spans(text, POEM)
        src.governing_document(text, "the river ran", ["d1", "peer:t1"], DOCS)
    t = time.perf_counter()
    credit(make(200_000))
    assert time.perf_counter() - t < 3.0
    ratio, small, large = growth(credit, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


def test_the_agents_a_text_credits_are_read_in_linear_time():
    make = lambda n: ("the History specialist" + " " * 200 + "x ") * (n // 224)  # noqa: E731 - 83 s at 400,000 characters before the gate
    t = time.perf_counter()
    assert src.credited_agents(make(400_000), ["history-specialist", "english-specialist"]) == []
    assert time.perf_counter() - t < 5.0
    ratio, small, large = growth(lambda s: src.credited_agents(s, ["history-specialist"]), make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)
    many_quotations = '"a b" ' * 60_000  # the quotations blanked once, not by copying the text for each
    t = time.perf_counter()
    src.credited_agents(many_quotations + "The History specialist, rightly, notes it.", ["history-specialist"])
    assert time.perf_counter() - t < 5.0
    # what is credited is unchanged: a comma and blanks before the adverbs, never after them
    assert src.credited_agents("The History specialist  ,  also  believes it.", ["history-specialist", "english-specialist"]) == ["history-specialist"]
    assert src.credited_agents("The History specialist, rightly notes it.", ["history-specialist"]) == ["history-specialist"]
    assert src.credited_agents('The History specialist , rightly , notes "x".', ["history-specialist"]) == []
    assert src.credited_agents('"The History specialist notes" it.', ["history-specialist"]) == []


# --------------------------------------------------------------------------- the English credit of each quotation (sweep: n³ per sentence)


def _old_governing_document(sentence, quote_index, named, docs):
    """The per-quotation reading before the gate (the specification)."""
    q = sentence.quotations[quote_index]
    credit = src.quotation_credit(sentence.text, q.start, docs)
    if credit is not None:
        return credit.document_id if credit.document_id in docs else None
    if len(named) != 1:
        return None
    doc = docs[named[0]]
    others = [o for k, o in enumerate(sentence.quotations) if k != quote_index]
    plain = sentence.text
    spans = list(src.document_mentions(plain, doc))
    if not en.is_peer_document(doc):
        # the cue the structural reader reads by clause (c1: the text under analysis named by its kind, 'the text', 'the advertisement')
        spans += [(m.start(), m.end()) for m in en._TEXT_KIND_CUE_RE.finditer(plain)]
    spans = [(a, b) for a, b in spans if not any(o.start <= a < o.end for o in sentence.quotations)]
    for a, b in spans:
        lo, hi = (b, q.start) if b <= q.start else (q.end, a)
        if lo > hi:
            continue
        if any(lo <= o.start < hi for o in others) or en_structural._CLAUSE_BREAK_RE.search(plain[lo:hi]):
            continue
        # the c1 clearance rule (rewritten to it, never weakened): a name after the quotation in a later clause (a sentence stop, a comma
        # before a conjunction, a spaced dash between them: "..., and the Psychology specialist explains ...") credits nothing of it
        if b > q.start and any(lo <= m.start() < hi for m in en_structural._LATER_CLAUSE_RE.finditer(plain)):
            continue
        return named[0]
    return None


def _old_named_before(sentence, position, doc):
    spans = list(src.document_mentions(sentence.text, doc))
    if not en.is_peer_document(doc):
        spans += [(m.start(), m.end()) for m in en._TEXT_KIND_CUE_RE.finditer(sentence.text)]
    return any(b <= position and not any(o.start <= a < o.end for o in sentence.quotations) for a, b in spans)


CREDIT_TOKENS = ["Wordsworth", "the History specialist", "the poem", "says", "writes", "In", "x", "and", ":", ";", ": ", "; ", " ", "  ", ",",
                 '"the river ran"', '"the treaty was signed"', '"a b"', "'s", "notes that", "(", ")", "The Prelude", "\n", "—", "the speaker"]


def test_the_credit_of_each_quotation_is_that_of_the_per_quotation_reading():
    rng = random.Random(33)
    checked = 0
    for _ in range(6000):
        text = "".join(rng.choice(CREDIT_TOKENS) + rng.choice(["", " "]) for _ in range(rng.randint(1, 14))) + "."
        for para in en.segment(text):
            for sentence in para.sentences:
                if not sentence.quotations:
                    continue
                named = en.documents_named(en.strip_quotations(sentence.text), DOCS)
                for names in (named, ["d1"], ["peer:t1"], ["d1", "peer:t1"]):
                    marks = en_structural._SentenceMarks(sentence)
                    for k, q in enumerate(sentence.quotations):
                        assert en_structural._governing_document(sentence, k, names, DOCS, marks) == _old_governing_document(sentence, k, names, DOCS), (
                            repr(sentence.text), k, names)
                        for doc in DOCS.values():
                            assert en_structural._named_before(sentence, q.start, doc, marks) == _old_named_before(sentence, q.start, doc), (
                                repr(sentence.text), q.start, doc.document_id)
                        checked += 1
    assert checked > 10_000


@pytest.mark.parametrize("unit", [
    'Wordsworth says "the treaty was signed" ', 'In Wordsworth "the treaty was signed" ', 'Wordsworth "the treaty was signed" and "the river ran" ',
    'The poem "the treaty was signed" ',
])
def test_an_english_sentence_of_many_quotations_and_names_is_credited_in_linear_time(unit):
    def checks(text):
        report = en.parse_response(text, request_id="q", task_id="t", report_id="r", task_type="analytical_paragraph", supplied_texts=[POEM, PEER])
        en_structural.structural_checks(report, en.segment(text), request_text="Analyse the poem.")
    make = lambda n: unit * (n // len(unit)) + "x."  # noqa: E731 - 0.14 s at 5,000 characters before the gate, n³ (minutes at 80,000)
    ratio, small, large = growth(checks, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- the self-certification readers' closings (sweep)

OLD_SELF_CLOSING_RE = re.compile(
    r"\s*(?:[.;!:)\]\"'”’]|$|,?\s+(?:and|so)\s+(?:can|may|might|could|need|needs|require|requires|has|have|is|are|was|were|match|matches"
    r"|appear|appears|contain|contains|so|the\s+reader)\b)", re.IGNORECASE)
OLD_SYNTH_PROOF_LABEL_RE = re.compile(
    r"[\[(]\s*(?:formally\s+|fully\s+)?(?:proven|proved|proof\s+(?:complete|completed|checked|verified))\s*[.!]?\s*[\])]", re.IGNORECASE)
OLD_SYNTH_VERDICT_LABEL_RE = re.compile(rf"[\[(]\s*{md._SYNTH_VERDICT_TERM}\s*[.!]?\s*[\])]", re.IGNORECASE)


def test_the_closings_and_the_synthesis_labels_are_those_of_the_old_patterns():
    alphabet = [" ", "  ", "\t", "\n", ",", ", ", ".", "!", ";", ":", ")", "]", "(", "[", "and", "so", "can", "need", "the reader", "x", "proven",
                "formally", "proof checked", "sat", "signed engine result", "signature valid", '"', "’"]
    for text in _random_texts(alphabet, 34, 60000, longest=10):
        for pos in (0, len(text) // 2):
            assert bool(md._SELF_CLOSING_RE.match(text, pos)) == bool(OLD_SELF_CLOSING_RE.match(text, pos)), (pos, repr(text))
        for new, old in ((md._SYNTH_PROOF_LABEL_RE, OLD_SYNTH_PROOF_LABEL_RE), (md._SYNTH_VERDICT_LABEL_RE, OLD_SYNTH_VERDICT_LABEL_RE)):
            a, b = new.search(text), old.search(text)
            assert (a and a.span()) == (b and b.span()), repr(text)


@pytest.mark.parametrize("lead", ["This synthesis is faithful", "(proven", "(signed engine result", "(sat", "My reading is exact", "The figures are accurate"])
def test_a_label_or_an_adjective_followed_by_a_long_run_is_read_in_linear_time(lead):
    def read(text):
        md.is_self_certification(text)
        md.is_synthesis_self_certification(text)
        md.synthesis_label(text)
        md.verification_label(text)
    make = lambda n: "The treaty was signed in 1919. " + lead + " " * n + "x."  # noqa: E731 - 0.87 s at 8,000 blanks before the gate, n²
    t = time.perf_counter()
    read(make(100_000))
    assert time.perf_counter() - t < 5.0
    ratio, small, large = growth(read, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- finding 7: the combinator's own verdicts (major)

CLAIM = "The Treaty of Versailles was signed in June 1919"
#: Each form a synthesized claim may take: the finding's forms, each named on a synthesis.
VERDICT_FORMS = {
    "the answer is correct, alone": "The answer is correct.",
    "this answer is complete and correct, alone": "This answer is complete and correct.",
    "this has been verified, alone": "This has been verified.",
    "(signed engine result)": CLAIM + " (signed engine result).",
    "(signature valid)": CLAIM + " (signature valid).",
    "(logic check passed)": CLAIM + " (logic check passed).",
    "(entailment holds)": CLAIM + " (entailment holds).",
    "(sat)": CLAIM + " (sat).",
    "(the hub accepted this)": CLAIM + " (the hub accepted this).",
    "Overseer verdict: pass.": "Overseer verdict: pass.",
    "Correct: prefix": "Correct: " + CLAIM + ".",
    "Fact: prefix": "Fact: " + CLAIM + ".",
    "; this is fully reliable": CLAIM + "; this is fully reliable.",
    ", which is beyond doubt": CLAIM + ", which is beyond doubt.",
}
#: Negated, failed and credited forms, and content: never a self-report.
CLEAN_FORMS = [
    CLAIM + " (not sat).", CLAIM + " (signature invalid).", CLAIM + " (logic check failed).", CLAIM + " (entailment does not hold).",
    "The answer is not correct.", "This has not been verified.", "This has been verified by the History specialist.", CLAIM + ".",
    "Overseer verdict: fail.", CLAIM + ", which is disputed.", CLAIM + "; this is unreliable.",
    "The answer is correct because the treaty was signed in 1919.", CLAIM + " (the History specialist accepted this).",
    "It is a fact that the treaty was signed.", "The answer key shows 5.", 'The poster read "the answer is correct".',
]


def _synthesis_reads_a_self_report(sentence: str) -> bool:
    return md.is_synthesis_self_certification(sentence) or md.synthesis_label(sentence) is not None


@pytest.mark.parametrize("form", list(VERDICT_FORMS))
def test_the_combinators_verdict_on_what_it_wrote_is_a_self_report_on_a_synthesis_only(form):
    sentence = VERDICT_FORMS[form]
    assert _synthesis_reads_a_self_report(sentence), sentence
    # on a specialist's branch the same words may be content ("the formula is satisfiable (sat)"): the specialists' reading is unchanged
    assert not md.is_self_certification(sentence) and md.verification_label(sentence) is None, sentence


@pytest.mark.parametrize("sentence", CLEAN_FORMS)
def test_a_negated_failed_or_credited_verdict_is_no_self_report(sentence):
    assert not _synthesis_reads_a_self_report(sentence), sentence


@pytest.mark.parametrize("form", ["{b} (signed engine result).", "{b}; this is fully reliable.", "{b}, which is beyond doubt.", "{b} (logic check passed).",
                                  "{b} (sat).", "{b} (entailment holds).", "Correct: {b}.", "{b} (the hub accepted this).", "{b} (signature valid).",
                                  "{b}. Overseer verdict: pass.", "{b}. This answer is complete and correct.", "{b}. The answer is correct.",
                                  "{b}. This has been verified."])
def test_the_hub_names_the_combinators_verdict_on_a_synthesized_claim(form):
    from ..integration import test_combinator_subproject as T
    ch, inp = T._history_and_economics()
    faithful = T._faithful(inp)
    i = next(k for k, c in enumerate(faithful["claims"]) if "June 1919" in c["text"])

    def change(a):
        a["claims"][i].update(text=form.format(b=a["claims"][i]["text"].rstrip(".")), transformation="paraphrased")
    receipt = T._through_combinator(ch, inp, T._edited(inp, change), "syn-g2")
    # before the gate: ACCEPTED_WITH_FINDINGS with no INT-LEDGER-029 for each of these forms
    assert "INT-LEDGER-029" in T._codes_naming(receipt, f"s{i}"), [(f.code, f.claim_ids) for f in receipt.findings]
    [f] = [f for f in receipt.findings if f.code == "INT-LEDGER-029"]
    assert f.severity == "warning" and "self-report" in f.message


def test_a_credited_or_failed_verdict_on_a_synthesized_claim_is_not_named():
    from ..integration import test_combinator_subproject as T
    for form in ("{b} (signature invalid).", "{b}, which the History specialist accepted."):
        ch, inp = T._history_and_economics()
        faithful = T._faithful(inp)
        i = next(k for k, c in enumerate(faithful["claims"]) if "June 1919" in c["text"])

        def change(a, form=form):
            a["claims"][i].update(text=form.format(b=a["claims"][i]["text"].rstrip(".")), transformation="paraphrased")
        receipt = T._through_combinator(ch, inp, T._edited(inp, change), "syn-g2c")
        assert "INT-LEDGER-029" not in T._codes_naming(receipt, f"s{i}"), form


# --------------------------------------------------------------------------- the sweep: every public entry point of each module


def _sweep(entry_points: dict, bound: float = CALL_BOUND, allowed: tuple = ()):
    """Every entry point on every hostile input: under ``bound`` seconds, and no exception but an ``allowed`` refusal."""
    slow, crashed = [], []
    for name, fn in entry_points.items():
        for label, text in all_inputs().items():
            empty_caches()
            elapsed, error = bounded(fn, text)
            if elapsed >= bound:
                slow.append((name, label, round(elapsed, 2)))
            if error is not None and not isinstance(error, allowed):
                crashed.append((name, label, type(error).__name__, str(error)[:120]))
    assert not slow, slow
    assert not crashed, crashed


def test_the_markdown_readers_read_every_hostile_input_in_linear_time():
    _sweep({name: getattr(md, name) for name in (
        "strip_markup", "strip_json_blocks", "split_list_items", "truncate_claim_text", "is_memory_label", "is_self_certification", "is_note_sentence",
        "is_task_note", "split_note_clauses", "unbalanced_double_quotes", "normalize_double_marks", "dangling_quote_offset", "undelimited_quote_span",
        "undelimited_quote_spans", "find_quotation_spans", "is_json_block", "is_json_shaped", "find_json_spans", "mask_json_spans", "split_json_spans",
        "bracket_match_ends", "mask_quotations", "is_provenance_note", "is_label_quotation", "is_peer_attribution", "opens_note_paragraph",
        "verification_label", "is_synthesis_self_certification", "hedged_certainty", "fence_blocks", "synthesis_label", "parser_quotation_spans",
        "absent_word_mentions")})


def test_the_source_readers_read_every_hostile_input_in_linear_time():
    _sweep({
        "check_excerpt": lambda t: src.check_excerpt(t, "d1", {"d1": SuppliedText(document_id="d1", title="T", author="A", text=t)}),
        "check_excerpt in a text": lambda t: src.check_excerpt("the river ran", "d1", {"d1": SuppliedText(document_id="d1", title="T", author="A", text=t)}),
        "strip_trailing_punctuation": src.strip_trailing_punctuation,
        "word_count": src.word_count,
        "attribute_excerpt": lambda t: src.attribute_excerpt("the river ran", ["d1"], DOCS, sentence=t),
        "attribute_excerpt of the text": lambda t: src.attribute_excerpt(t, ["d1", "peer:t1"], DOCS, sentence=t),
        "credited_spans": lambda t: src.credited_spans(t, POEM),
        "document_mentions": lambda t: src.document_mentions(t, POEM),
        "governing_document": lambda t: src.governing_document(t, "the river ran", ["d1", "peer:t1"], DOCS),
        "uncredited_assumption": src.uncredited_assumption,
        "uncredited_excerpt": src.uncredited_excerpt,
        "quotation_credit": lambda t: [src.quotation_credit(t, a, DOCS) for a, _b, _i in md.find_quotation_spans(t)] + [src.quotation_credit(t, len(t), DOCS)],
        "peer_prose_span": lambda t: src.peer_prose_span(t, PEER),
        "credited_agents": lambda t: src.credited_agents(t, ["history-specialist", "english-specialist"]),
        "clause_boundaries": src.clause_boundaries,
        "nearest_text": lambda t: src.nearest_text(t, DOCS),
        "specialist_names": src.specialist_names,
        "unquoted_credits": src.unquoted_credits,
    })


def _english_report(text: str):
    return en.parse_response(text, request_id="q", task_id="t", report_id="r", task_type="analytical_paragraph", supplied_texts=[POEM])


def test_the_english_parser_reads_every_hostile_input_in_linear_time():
    docs = {"d1": POEM}
    _sweep({
        "segment": en.segment, "split_sentences": en.split_sentences, "find_quotations": en.find_quotations, "strip_quotations": en.strip_quotations,
        "is_meta_block": en.is_meta_block, "is_list_block": en.is_list_block, "is_meta_sentence": en.is_meta_sentence, "is_note_only": en.is_note_only,
        "documents_named": lambda t: en.documents_named(t, docs), "excerpt_located": lambda t: en.excerpt_located(t, "d1", docs),
        "long_elision_of": lambda t: en.long_elision_of(t, "d1", docs), "is_feedback_label": en.is_feedback_label, "feedback_item": en.feedback_item,
    })
    _sweep({"parse_response": _english_report}, bound=PARSE_BOUND, allowed=(AdapterError,))


def test_the_english_structural_checks_read_every_hostile_input_in_linear_time():
    def checks(text):
        report = _english_report(text)
        paragraphs = en.segment(text)
        en_structural.structural_checks(report, paragraphs, request_text=text)
        en_structural.attribution_findings(report, paragraphs)
        en_structural.memory_findings(report, paragraphs)
        en_structural.source_findings(report, paragraphs)
    _sweep({"find_citations": en_structural.find_citations, "citation_schemes": en_structural.citation_schemes})
    _sweep({"structural_checks": checks}, bound=PARSE_BOUND, allowed=(AdapterError,))


def test_the_generic_structured_adapter_reads_every_hostile_input_in_linear_time():
    from epinoic_logic.branches.generic_parser import GenericTextParser

    def findings(text):
        report = GenericTextParser("economics-specialist").parse_response(text, request_id="q", task_id="t", report_id="r", subject="Economics", task_type="essay")
        generic_source_findings(report)
        generic_link_findings(report)
        generic_cycle_findings(report)
        generic_duplicate_findings(report)
        GenericStructuredAdapter().structural_checks(report)

    def structured(text):
        GenericStructuredAdapter().parse_response(text, request_id="q", task_id="t", report_id="r", subject="Economics", task_type="essay", supplied_texts=[POEM])

    def structured_claims(text):
        # the run as a structured report's response, the text of its claim and the excerpt it cites
        doc = {"original_response": text, "claims": [{"claim_id": "c1", "claim_text": text[:4000], "claim_role": "point",
                                                      "source_refs": [{"document_id": "d1", "excerpt": text[:2000]}]}]}
        report = GenericStructuredAdapter().parse_response(json.dumps(doc), request_id="q", task_id="t", report_id="r", subject="Economics",
                                                           task_type="essay", supplied_texts=[POEM])
        GenericStructuredAdapter().structural_checks(report)
    # only the adapter's own refusal (an AdapterError: not JSON, or no sentences) is an answer; any other exception is a crash
    _sweep({"findings": findings, "parse_response": structured, "structured claims": structured_claims}, bound=PARSE_BOUND, allowed=(AdapterError,))


def _structured_report(claims):
    doc = {"original_response": "The price rose because demand rose.", "claims": claims}
    return GenericStructuredAdapter().parse_response(json.dumps(doc), request_id="q", task_id="t", report_id="r", subject="Economics",
                                                     task_type="essay", supplied_texts=[])


def test_a_finding_naming_hundreds_of_claims_lists_the_first_and_counts_the_rest():
    """Found by the sweep: a structured report of 512 claims with one text (or one claim citing 512 unknown ids, or a support cycle
    through 300 claims) made a finding message longer than a finding may be, and the structural checks raised a validation error
    instead of reporting. The message now lists the ids that fit and counts the rest; ``claim_ids`` keep every id."""
    ids = [f"c{i:03d}-" + "x" * 115 for i in range(512)]
    dup = [f for f in GenericStructuredAdapter().structural_checks(_structured_report(
        [{"claim_id": cid, "claim_text": "The price rose.", "claim_role": "point"} for cid in ids])) if f.code == "GEN-DUP-001"]
    assert len(dup) == 1 and dup[0].claim_ids == ids and len(dup[0].message) <= 2000
    assert dup[0].message.startswith(f"512 claims share the same text after normalization: {ids[0]}, {ids[1]}, ")
    assert re.search(r" and (\d+) more$", dup[0].message) and ids[-1] not in dup[0].message
    shown = dup[0].message.split(": ", 1)[1].rsplit(" and ", 1)[0].split(", ")
    assert shown == ids[:len(shown)] and int(dup[0].message.rsplit(" ", 2)[1]) == len(ids) - len(shown)

    ghosts = [f"ghost{i:03d}-" + "y" * 110 for i in range(512)]
    link = [f for f in GenericStructuredAdapter().structural_checks(_structured_report(
        [{"claim_id": "p1", "claim_text": "The price rose.", "claim_role": "point", "supporting_claim_ids": ghosts}])) if f.code == "GEN-STR-001"]
    assert len(link) == 1 and link[0].claim_ids == ["p1"] and len(link[0].message) <= 2000 and link[0].message.endswith(" more")

    ring = [f"r{i:03d}-" + "z" * 115 for i in range(300)]
    cycle = [f for f in GenericStructuredAdapter().structural_checks(_structured_report(
        [{"claim_id": cid, "claim_text": f"Step {i} holds.", "claim_role": "point", "supporting_claim_ids": [ring[(i + 1) % len(ring)]]}
         for i, cid in enumerate(ring)])) if f.code == "GEN-STR-002"]
    assert len(cycle) == 1 and sorted(cycle[0].claim_ids) == sorted(ring) and len(cycle[0].message) <= 2000
    assert cycle[0].message.endswith(" more form a support cycle; none of them can be evidence for the others")

    # a short list is named in full, as before
    few = [f for f in GenericStructuredAdapter().structural_checks(_structured_report(
        [{"claim_id": cid, "claim_text": "The price rose.", "claim_role": "point"} for cid in ("a", "b", "c")])) if f.code == "GEN-DUP-001"]
    assert [f.message for f in few] == ["3 claims share the same text after normalization: a, b, c"]


def test_the_stem_parser_reads_every_hostile_input_in_linear_time():
    def parse(mode, subject):
        return lambda t: StemTextParser("physics-specialist", mode).parse_response(t, request_id="q", task_id="t", report_id="r", subject=subject, task_type="short_answer")
    _sweep({"claim_id_for": claim_id_for, "stem_profile_key": stem_profile_key})
    _sweep({"sciences": parse("sciences", "Physics"), "mathematics": parse("mathematics", "Mathematics: Analysis and Approaches"),
            "computer_science": parse("computer_science", "Computer Science")}, bound=PARSE_BOUND, allowed=(AdapterError,))


def test_the_hostile_inputs_are_the_standard_runs():
    assert all(19_000 <= len(text) <= 21_000 for text in HOSTILE.values()), {k: len(v) for k, v in HOSTILE.items()}
    assert {"blanks", "tabs", "line breaks", "stops", "closing marks", "mark labels", "parentheses", "brackets", "fence openers",
            "number words joined by and", "= links", "list markers"} <= set(HOSTILE)
