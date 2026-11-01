"""Integration gate 2 (before arena round 8): the History chronology reader's input stalls.

Critical finding fixed at its cause: the intransitive head ('The crisis followed in July 1922') was read with three adjacent
unbounded blank runs around optional commas (``chronology._INTRANSITIVE_HEAD_RE``): a cue followed by a run of blanks and a word
that is no head ('followed' + 1,200 blanks + 'abroad in July 1922') took 16.9 s, n³ steps. The runs are now possessive, and the
same reading of the coordinated gap (``_COORDINATED_GAP_RE``).

Found by the sweep of the same class in the module, each fixed the same way with its old reading kept here as the specification:

* the span, inclusion, list and 'when' separators (``_SPAN_SEP_RE``, ``_INCLUDE_CUE_RE``, ``_LIST_SEP_RE``, ``_WHEN_RE``) and the
  inner sentence end (``_INNER_END_RE``) were tried again from every blank (or stop) of a run: they are read from the run's first;
* the range word before a date was searched in the whole text before every date (``_range_before`` reads a window that ends at it);
* the paragraph's dated mentions were read again for every look-up (``_paragraph_mentions``, ``_mention_groups``), each sentence's
  words for every dated item (``_word_index``), and each word of a noun phrase or of a noun's modifiers was inserted at the front of
  the phrase (``_np_words``, ``_premodifiers``);
* a statement of thousands of cues or dates was read again for each ('after 1901' * k: 35 s per History receive at 20,000
  characters): a statement over ``_MAX_STATEMENT_CUES`` cues or ``_MAX_STATEMENT_DATES`` dates is one undecided relation that names
  the bound (CORE-CHR-001), never read in part.

The sweep tests feed every public entry point of the History modules the standard hostile inputs and assert a time bound with a wide
margin."""
from __future__ import annotations

import random
import re
import time

import pytest

from epinoic_logic.adapters.base import AdapterError
from epinoic_logic.adapters.history_specialist import chronology as ch
from epinoic_logic.adapters.history_specialist import parser as hp
from epinoic_logic.adapters.history_specialist import sentences as hs
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.adapters.history_specialist.structural import judgement_move_present, structural_checks
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

from ..adapters.hostile_inputs import HOSTILE, all_inputs, bounded
from ..growth import growth
from ..timing import empty_caches

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
KEY = b"integration-gate-2-chronology-key-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
#: A call of a public entry point on a hostile input of about 20,000 characters: a linear reader takes a few hundredths of a second.
CALL_BOUND = 3.0
#: A whole parse of such an answer.
PARSE_BOUND = 10.0

# --------------------------------------------------------------------------- the replaced readings (the specification)

OLD_INTRANSITIVE_HEAD_RE = re.compile(
    r"^\s*,?\s*(?:(?:soon|shortly|quickly|swiftly|rapidly|only|later|immediately|closely|in turn|then)\s+)*,?\s*(?:in|on|by|during|at|within)\s+"
    r"(?:(?:early|late|mid)[\s-]+|the\s+(?:end|start|beginning|middle|spring|summer|autumn|winter|first half|second half)\s+of\s+|(?:about|around|c\.|ca\.|circa)\s+)?$",
    re.IGNORECASE)
OLD_COORDINATED_GAP_RE = re.compile(
    r"^\s*,?\s*(?:and|or|but|yet|as well as)\s+(?:(?:also|only|long|shortly|just|well|soon|immediately|not long|even)\s+)*$", re.IGNORECASE)
OLD_RANGE_BEFORE_DATE_RE = re.compile(
    r"\b(?:up to|until|till|since|from|through|throughout|between|by)\s+(?:(?:early|late|mid)[\s-]+)?(?:the\s+)?$", re.IGNORECASE)
OLD_SPAN_SEP_RE = re.compile(r"\s+(?:to|until|till|through|up\s+to)\s+", re.IGNORECASE)
OLD_INCLUDE_CUE_RE = re.compile(
    r"(?:,\s*|\s+)(?:(?:which|that)\s+(?:had\s+)?(?:included|includes|include|encompassed|encompasses|took\s+in)|including)\b", re.IGNORECASE)
OLD_LIST_SEP_RE = re.compile(r"\s*,\s*(?:and\s+|as\s+well\s+as\s+)?|\s+(?:and|as\s+well\s+as)\s+", re.IGNORECASE)
OLD_WHEN_RE = re.compile(r"(?:,\s*|\s+)when\s+", re.IGNORECASE)
OLD_INNER_END_RE = re.compile(r"[.?!]+[\"”’')\]»]*\s+(?=[\"“‘'(\[«„]?[A-ZÀ-ÖØ-Þ0-9])")
#: Written inline before the gate: the 'when' clause after a cue's second date, and the opening of a leading year's clause.
OLD_WHEN_AT_RE = re.compile(r",?\s*\bwhen\b", re.IGNORECASE)
OLD_LEADING_YEAR_HEAD_RE = re.compile(r"\s*,?\s*(?:(?:and|then|so|but|yet)\s+)?(?:in|by|during)\s+(?:(?:early|late|mid)[\s-]+)?", re.IGNORECASE)


def _old_np_words(text: str, *, trailing: bool) -> list[str]:
    """The noun-phrase reading before the gate: each word inserted at the front of the phrase."""
    words = [w.lower().strip("'’") for w in ch._WORD_RE.findall(text)]
    if trailing:
        while words and (words[-1] in ch._NP_STOP or words[-1] == "that"):
            words.pop()
        out: list[str] = []
        for i in range(len(words) - 1, -1, -1):
            w = words[i]
            if w in ch._NP_STOP or (w == "that" and i > 0):
                break
            out.insert(0, w)
            if w in ch._DEFINITES and (w not in ch._DEMONSTRATIVES or i == 0):
                break
        return out[-6:]
    out = []
    for w in words:
        if w in ch._NP_STOP and not (w in ch._DEFINITES and not out):
            break
        out.append(w)
        if len(out) >= 6:
            break
    return out


def _old_premodifiers(text: str, head: str, near: int) -> list[str]:
    """The modifier reading before the gate: every word of the sentence scanned for the nearest occurrence, each modifier inserted
    at the front."""
    words = list(ch._WORD_RE.finditer(text))
    hits = [i for i, w in enumerate(words) if ch._stem(w.group(0)) == head]
    if not hits:
        return []
    i = min(hits, key=lambda k: abs(words[k].start() - near))
    out: list[str] = []
    j = i - 1
    while j >= 0:
        w = words[j].group(0).lower()
        gap = text[words[j].end(): words[j + 1].start()]
        if gap.strip() or w in ch._DEFINITES or w in ch._NP_STOP or w in ch.MONTHS:
            break
        out.insert(0, ch._stem(w))
        j -= 1
    return out


def _old_dated_mention(head: str, context: str, sentence: str, side_words=None):
    """The paragraph look-up before the gate: every dated item of every other sentence read again for each look-up."""
    found = {}
    target = " ".join(sentence.split())
    for other, normalized, tokens in ch._paragraph_sentences(context):
        if normalized == target or target in normalized:
            continue
        for tok in tokens:
            if tok.year is None:
                continue
            before = other[: tok.start]
            if OLD_RANGE_BEFORE_DATE_RE.search(before):
                continue
            pieces = re.split(r"[,;:()]", before)
            clause_before = pieces[-1]
            after = other[tok.end:]
            noun_before: list[str] = []
            if ch._PARTICIPLE_OPENER_RE.match(clause_before) and ch._PARTICIPIAL_DATE_RE.match(clause_before):
                window_after = " ".join(re.split(r"[;:()]", after)[0].split(",")[:2])
                if len(pieces) >= 2 and before.rstrip()[len(before.rstrip()) - len(clause_before.rstrip()) - 1: len(before.rstrip()) - len(clause_before.rstrip())] == ",":
                    noun_before = [ch._stem(w) for w in ch._WORD_RE.findall(pieces[-2])][-4:]
            else:
                window_after = re.split(r"[,;:()]", after)[0]
            words = noun_before + [ch._stem(w) for w in ch._WORD_RE.findall(clause_before)][-4:] + [ch._stem(w) for w in ch._WORD_RE.findall(window_after)][:3]
            if head not in words and ch._GOVERNING_DATE_HEAD_RE.fullmatch(clause_before):
                governed = [w.lower() for w in ch._WORD_RE.findall(window_after)][:14]
                stems = [ch._stem(w) for w in governed]
                if head in stems and any(w in ch._ENACTMENT_VERBS for w in governed[: stems.index(head)]):
                    words = words + [head]
            if head in words:
                if side_words is not None and not set(_old_premodifiers(other, head, tok.start)) <= side_words:
                    continue
                found.setdefault(tok.ordinal(), (tok, other))
    if not found:
        return None, "no other sentence of the paragraph dates it"
    if len(found) > 1:
        return None, f"the paragraph gives it {len(found)} different dates"
    tok, other = next(iter(found.values()))
    return tok, other.strip()


def _random_texts(alphabet, seed: int, n: int, longest: int = 16):
    rng = random.Random(seed)
    for _ in range(n):
        yield "".join(rng.choice(alphabet) for _ in range(rng.randint(0, longest)))


def _spans(pattern, text: str):
    return [m.span() for m in pattern.finditer(text)]


def _receive(answer: str, request: str = "Describe the sequence of events."):
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"]))
    m, _, _ = hub.dispatch("t", "history-specialist", request)
    t = time.perf_counter()
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="history-specialist", report_id="r1")
    return time.perf_counter() - t, rc


# --------------------------------------------------------------------------- the intransitive head (critical)

HEAD_ALPHABET = [" ", "  ", "\t", "\n", ",", ", ", "soon", "shortly", "then", "in turn", "in", "on", "by", "during", "at", "within", "early",
                 "late", "mid", "-", "the", "end", "spring", "first half", "of", "about", "c.", "circa", "and", "or", "but", "as well as", "also",
                 "not long", "even", "x", "abroad", "1922"]


def test_the_head_and_the_gap_are_those_of_the_old_patterns():
    for text in _random_texts(HEAD_ALPHABET, 21, 60000):
        for new, old in ((ch._INTRANSITIVE_HEAD_RE, OLD_INTRANSITIVE_HEAD_RE), (ch._COORDINATED_GAP_RE, OLD_COORDINATED_GAP_RE)):
            a, b = new.match(text), old.match(text)
            assert (a and a.span()) == (b and b.span()), (new.pattern[:30], repr(text))
            a, b = new.search(text), old.search(text)
            assert (a and a.span()) == (b and b.span()), (new.pattern[:30], repr(text))


@pytest.mark.parametrize("make", [
    lambda n: "The crisis followed" + " " * n + "abroad in July 1922.",          # the finding's input: 16.9 s at 1,200 blanks
    lambda n: "The crisis followed" + " ," * (n // 2) + "abroad in July 1922.",
    lambda n: "The crisis followed" + "\t" * n + "x in July 1922.",
    lambda n: "The strike came after May 1921" + " " * n + ", x and before 1922.",  # the coordinated gap
])
def test_a_long_run_after_an_intransitive_cue_is_read_in_linear_time(make):
    context = "The strike began in May 1921. " + make(1000)
    t = time.perf_counter()
    ch.chronology_relations(make(100_000), context)
    assert time.perf_counter() - t < 5.0
    ratio, small, large = growth(lambda s: ch.chronology_relations(s, None), make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)
    # the reading of a real head is unchanged
    rel = ch.chronology_relations("The crisis followed in July 1922.", "The strike began in May 1921. The crisis followed in July 1922.")
    assert [(r.later_text, r.earlier_text, r.decided, r.violated) for r in rel] == [("July 1922", "May 1921", True, False)]


def test_a_history_answer_with_a_long_run_after_a_cue_crosses_the_hub_in_seconds():
    elapsed, rc = _receive("The strike began in May 1921. The crisis followed" + " " * 100_000 + "abroad in July 1922.")
    assert elapsed < 20.0  # before the gate: the 1,200-blank form took 16.9 s, n³ steps
    assert "CORE-INTERNAL-001" not in {f.code for f in [*rc.findings, *rc.structural_findings]}


# --------------------------------------------------------------------------- the separators, the inner ends, the range word (the sweep)

SEP_ALPHABET = [" ", "  ", "\t", "\n", ",", ", ", ";", ".", "!", "?", "..", '"', "”", "’", ")", "]", "»", "(", "“", "A", "Z", "9", "x", "to",
                "until", "till", "through", "up to", "up", "including", "which included", "that had included", "took in", "when", "and",
                "as well as", "1914", "May 1921", "early", "late", "mid", "-", "the", "since", "from", "between", "by", "throughout"]


def test_the_separators_and_the_inner_ends_are_those_of_the_old_patterns():
    pairs = ((ch._SPAN_SEP_RE, OLD_SPAN_SEP_RE), (ch._INCLUDE_CUE_RE, OLD_INCLUDE_CUE_RE), (ch._LIST_SEP_RE, OLD_LIST_SEP_RE),
             (ch._WHEN_RE, OLD_WHEN_RE), (ch._INNER_END_RE, OLD_INNER_END_RE))
    for text in _random_texts(SEP_ALPHABET, 22, 60000):
        for new, old in pairs:
            assert _spans(new, text) == _spans(old, text), (new.pattern[:30], repr(text))
        # the span separator is also searched from the end of a date: a position after a character that is no blank
        for pos in range(len(text) + 1):
            if pos == 0 or not text[pos - 1].isspace():
                a, b = ch._SPAN_SEP_RE.search(text, pos), OLD_SPAN_SEP_RE.search(text, pos)
                assert (a and a.span()) == (b and b.span()), (pos, repr(text))


def test_the_when_clause_and_the_leading_year_head_are_those_of_the_inline_patterns():
    alphabet = SEP_ALPHABET + ["when", "When", "whenever", "and", "then", "so", "but", "yet", "in", "by", "during", "early", "late", "mid", "-", ","]
    rng = random.Random(27)
    for text in _random_texts(alphabet, 28, 30000, longest=12):
        for end in range(len(text) + 1):
            a, b = ch._WHEN_AT_RE.search(text, 0, end), OLD_WHEN_AT_RE.search(text[:end])
            assert (a and a.span()) == (b and b.span()), (end, repr(text))
        for _ in range(4):
            lo = rng.randint(0, len(text))
            hi = rng.randint(lo, len(text))
            assert bool(ch._LEADING_YEAR_HEAD_RE.fullmatch(text, lo, hi)) == bool(OLD_LEADING_YEAR_HEAD_RE.fullmatch(text[lo:hi])), (lo, hi, repr(text))


@pytest.mark.parametrize("make", [
    lambda n: "The strike came after May 1921" + " " * n + "x and before 1922, when talks resumed.",   # the 'when' clause after a second date
    lambda n: "In" + " " * n + "x 1958 Guinea followed on 2 October.",                               # the opening of a leading year's clause
])
def test_the_when_clause_and_the_leading_year_are_read_in_linear_time(make):
    t = time.perf_counter()
    ch.chronology_relations(make(100_000), "The war ended in 1957. " + make(100))
    assert time.perf_counter() - t < 5.0  # before the gate: 0.87 s and 3.7 s at 8,000 blanks, k² steps
    ratio, small, large = growth(lambda s: ch.chronology_relations(s, None), make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


def test_the_range_word_is_read_from_a_window_as_the_search_of_the_whole_prefix_read_it():
    for text in _random_texts(SEP_ALPHABET, 23, 20000, longest=12):
        for end in range(len(text) + 1):
            assert ch._range_before(text, end) == bool(OLD_RANGE_BEFORE_DATE_RE.search(text[:end])), (end, repr(text))
    long_word = "x" * 40
    for text in ("instability up to 1923", "since 1793", "from early 1920", "until the mid-1930s", "between late 1918",
                 f"{long_word}by 1923", "lasted up to   the 1923", "the Act of 1923"):
        for end in range(len(text) + 1):
            assert ch._range_before(text, end) == bool(OLD_RANGE_BEFORE_DATE_RE.search(text[:end])), (end, text)


@pytest.mark.parametrize("make", [
    lambda n: "The war lasted from 1914" + " " * n + "x to 1918.",                 # the span separator
    lambda n: "In the 1960s" + " " * n + "x including Kenya in 1963.",             # the inclusion cue
    lambda n: "Tanganyika in 1961" + " " * n + "x and Kenya in 1963 during the 1960s.",  # the list separator
    lambda n: "In 1960" + " " * n + "x when Kenya became independent in 1963.",   # the 'when' clause
    lambda n: '"The war ended in 1918' + "." * n + 'x after 1914."',               # the inner sentence end
    lambda n: "in 1901, " * (n // 9) + "after 1902.",                              # the range word before every date
])
def test_a_statement_of_the_separators_class_is_read_in_linear_time(make):
    ratio, small, large = growth(lambda s: ch.chronology_relations(s, None), make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- the noun phrase, its modifiers, the paragraph look-up

NP_ALPHABET = [" ", "  ", ",", "the", "The", "that", "this", "these", "its", "agrarian", "general", "great", "first", "crisis", "crises",
               "election", "war", "was", "began", "in", "and", "May", "1921", "x", "aa", "of", "after", "-"]


def test_the_noun_phrase_and_the_modifiers_are_those_of_the_front_insertion():
    rng = random.Random(24)
    for text in _random_texts(NP_ALPHABET, 25, 30000, longest=20):
        text = " ".join(text.split("  "))
        for trailing in (True, False):
            assert ch._np_words(text, trailing=trailing) == _old_np_words(text, trailing=trailing), (trailing, repr(text))
        for head in ("crisi", "election", "war"):
            near = rng.randint(0, len(text))
            assert ch._premodifiers(text, head, near) == _old_premodifiers(text, head, near), (head, near, repr(text))


SENTENCE_FORMS = (
    "The {m}{n} {v} in {d}.", "Signed on {d}, the {n} {v}.", "The {n}, signed on {d}, {v}.", "On {d} the government signed the {n}.",
    "Instability lasted up to {d}, after the {n}.", "The {n} of {d} came before the {n2}.", "The {m}{n} followed it.",
    "The {n} {v} between {d} and {d2}.", "In {d} the {m}{n} {v}, and the {n2} {v} in {d2}.", "That {n} came after the {n2}.",
)
MODIFIERS = ("", "", "agrarian ", "general ", "first ")
NOUNS = ("crisis", "election", "treaty", "strike", "war", "act")
VERBS = ("began", "ended", "was signed", "broke out", "collapsed")
DATES = ("1919", "May 1921", "13 July 1931", "1923", "early 1920", "June 1919", "1931")


def _paragraph(rng: random.Random) -> list[str]:
    return [rng.choice(SENTENCE_FORMS).format(m=rng.choice(MODIFIERS), n=rng.choice(NOUNS), n2=rng.choice(NOUNS), v=rng.choice(VERBS),
                                              d=rng.choice(DATES), d2=rng.choice(DATES)) for _ in range(rng.randint(1, 8))]


def test_the_paragraph_look_up_is_that_of_the_reading_of_every_item():
    rng = random.Random(26)
    sides = (None, set(), {"agrarian"}, {"the", "general"}, {"first", "agrarian", "the"})
    compared = 0
    for _ in range(1500):
        sentences = _paragraph(rng)
        context = " ".join(sentences)
        for sentence in sentences + ["The strike followed the crisis."]:
            for head in ("crisi", "election", "treaty", "strike", "war", "act"):
                for side in sides:
                    new_tok, new_where = ch._dated_mention(head, context, sentence, side)
                    old_tok, old_where = _old_dated_mention(head, context, sentence, side)
                    assert (new_tok, new_where) == (old_tok, old_where), (head, side, sentence, context)
                    compared += 1
    assert compared > 50_000


@pytest.mark.parametrize("make", [
    lambda n: "The " + "aa " * (n // 3) + "crisis followed the war of 1914.",                        # the noun phrase before a cue
    lambda n: "The " + "aa " * (n // 3) + "crisis began in 1901. The strike followed the crisis.",   # the modifiers of a dated noun
    lambda n: "".join(f"The crisis began in {1800 + i % 200}. " for i in range(n // 28)) + "The strike followed the crisis.",
    lambda n: "".join(f"The war of {1800 + i % 200} ended. " for i in range(n // 24)) + "That war came after the crisis.",
])
def test_a_paragraph_of_many_dated_mentions_is_looked_up_in_linear_time(make):
    def read(paragraph: str):
        for sentence in hs.split_sentences(paragraph)[-2:]:
            ch.chronology_relations(sentence, paragraph)
    t = time.perf_counter()
    read(make(200_000))
    assert time.perf_counter() - t < 10.0
    ratio, small, large = growth(read, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- the statement bounds

def test_a_statement_over_the_cue_bound_is_one_undecided_relation_that_names_it():
    over = "The peace came after 1901 " + "after 1901 " * ch._MAX_STATEMENT_CUES + "and the treaty."
    rels = ch.chronology_relations(over, None)
    assert len(rels) == 1 and not rels[0].decided and not rels[0].violated
    assert f"more than {ch._MAX_STATEMENT_CUES} ordering, duration, containment or 'when' cues" in rels[0].reason
    within = "The peace came after 1901 " + "after 1901 " * (ch._MAX_STATEMENT_CUES - 2) + "and the treaty."
    assert all("more than" not in r.reason for r in ch.chronology_relations(within, None))
    # a real sentence of a few cues reads as before
    rel = ch.chronology_relations("The treaty of June 1919 came after the armistice of November 1918.", None)
    assert [(r.later_text, r.earlier_text, r.decided, r.violated) for r in rel] == [("June 1919", "November 1918", True, False)]


def test_a_statement_over_the_date_bound_is_one_undecided_relation_that_names_it():
    dates = "".join(f", in {1800 + i}" for i in range(ch._MAX_STATEMENT_DATES))
    over = f"The war began in 1914{dates} and ended after 1902."
    rels = ch.chronology_relations(over, None)
    assert len(rels) == 1 and not rels[0].decided
    assert f"more than the {ch._MAX_STATEMENT_DATES} a statement is read for" in rels[0].reason
    within = "The war began in 1914" + "".join(f", in {1800 + i}" for i in range(ch._MAX_STATEMENT_DATES - 2)) + " and ended after 1902."
    assert all("a statement is read for" not in r.reason for r in ch.chronology_relations(within, None))
    # a paragraph holding a sentence over the bound dates nothing by look-up, and says why
    tok, why = ch._dated_mention("crisi", over + " The crisis began in 1929.", "The strike followed the crisis.", None)
    assert tok is None and f"more than {ch._MAX_STATEMENT_DATES} dates" in why


def test_a_statement_of_thousands_of_cues_crosses_the_hub_with_the_bound_named():
    elapsed, rc = _receive("The war began in 1914. The peace came " + "after 1901 " * 2000 + "and the treaty.")
    assert elapsed < 20.0  # before the gate: 35 s at 20,000 characters
    named = [f for f in rc.structural_findings if f.code == "CORE-CHR-001"]
    assert named and any("more than a statement is read for" in f.message for f in named), [(f.code, f.message[:160]) for f in rc.structural_findings]
    assert rc.status.value != "ACCEPTED"  # a statement that was not checked is never shown as a clean acceptance


# --------------------------------------------------------------------------- the History parser's note clauses (the sweep)

OLD_NOTE_CLAUSE_SPLIT_RE = re.compile(r"\s*(?:;|,|\s[-–—]\s|—|–)\s*")


def test_the_note_clause_separator_is_that_of_the_old_pattern():
    alphabet = [" ", "  ", "\t", "\n", ";", ",", "-", "–", "—", "x", "a", " - ", " – ", "—x", "\u00a0"]
    for text in _random_texts(alphabet, 29, 60000, longest=12):
        assert hp._NOTE_CLAUSE_SPLIT_RE.split(text) == OLD_NOTE_CLAUSE_SPLIT_RE.split(text), repr(text)
    t = time.perf_counter()
    hp._NOTE_CLAUSE_SPLIT_RE.split(" \n" + "\n" * 100_000 + ".")
    assert time.perf_counter() - t < 1.0  # 18.9 s at 32,000 line breaks before the gate (its sentences hold at most 400 characters)


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


def test_the_chronology_reads_every_hostile_input_in_linear_time():
    _sweep({
        "chronology_relations": lambda t: ch.chronology_relations(t, None),
        "chronology_relations in a paragraph": lambda t: ch.chronology_relations(t, t),
        "chronology_relations of a sentence in the paragraph": lambda t: ch.chronology_relations("The treaty followed it in 1922.", t),
        "chronology_findings_in": lambda t: ch.chronology_findings_in(t, t),
        # the run between a cue and the date it reads (the finding's shape: the head after 'followed' is read up to the date)
        "between an intransitive cue and its date": lambda t: ch.chronology_relations("The crisis followed" + t + " in July 1922.", "The strike began in May 1921."),
        "between a dated cue and a second cue": lambda t: ch.chronology_relations("The strike came after May 1921" + t + " and before 1922.", None),
        "between a span's dates": lambda t: ch.chronology_relations("The war lasted from 1914" + t + " to 1918.", None),
        "between a period and its inclusion cue": lambda t: ch.chronology_relations("In the 1960s" + t + ", including Kenya in 1963.", None),
        "between the items of a list": lambda t: ch.chronology_relations("Tanganyika in 1961" + t + " and Kenya in 1963 during the 1960s.", None),
        "between a period and a 'when' clause": lambda t: ch.chronology_relations("In 1960" + t + " when Kenya became independent in 1963.", None),
        "statement_pieces": ch.statement_pieces,
        "years_in": lambda t: (ch.years_in(t), ch.years_in(t, dated_only=True)),
        "date_in_aside": lambda t: [ch.date_in_aside(t[: m.start()], m) for m in ch.MONTH_YEAR_RE.finditer(t)] + [ch.date_in_aside(t, ch.DateToken(len(t), len(t), "1922", None, 1922))],
    })


def test_the_history_sentence_reader_reads_every_hostile_input_in_linear_time():
    _sweep({
        "sentence_boundaries": lambda t: (hs.sentence_boundaries(t), hs.sentence_boundaries(t, semicolons=True, capital_next=False)),
        "split_sentences": hs.split_sentences, "split_clauses": hs.split_clauses, "strip_json_spans": hs.strip_json_spans,
        "is_abbreviation_before": hs.is_abbreviation_before, "abbreviation_ends_at": lambda t: [hs.abbreviation_ends_at(t, e) for e in range(0, len(t) + 1, 97)],
    })


def test_the_history_parser_reads_every_hostile_input_in_linear_time():
    _sweep({name: getattr(hp, name) for name in (
        "has_note_lead", "is_source_caveat", "caveat_terms", "is_provenance_note", "split_sentences", "has_dated_item", "is_self_report",
        "is_note_sentence", "is_peer_attribution", "is_note_paragraph", "certainty_of", "opens_with_fact", "states_dated_evidence",
        "is_counter_case_statement", "classify_paragraphs", "quotations_in")})
    _sweep({"classify": lambda t: hp.classify(t, 1, True), "judgement_move_present": lambda t: judgement_move_present(t, ["claim", "evidence"])})

    def parse(text):
        report = HistorySpecialistAdapter().parse_response(text, request_id="q", task_id="t", report_id="r", task_type="essay")
        structural_checks(report)
    _sweep({"parse_response and structural_checks": parse}, bound=PARSE_BOUND, allowed=(AdapterError,))


def test_the_hostile_inputs_are_shared_with_the_parsers_sweep():
    assert {"blanks", "tabs", "line breaks", "stops", "closing marks", "mark labels", "parentheses", "brackets", "fence openers",
            "number words joined by and", "= links", "list markers"} <= set(HOSTILE)
