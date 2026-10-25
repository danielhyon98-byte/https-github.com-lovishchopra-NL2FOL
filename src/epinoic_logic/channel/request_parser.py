"""Deterministic structuring of a student's or router's natural-language request.

The channel must know WHAT was asked in order to check WHETHER it was answered.
This parser extracts request items (questions and imperative instructions) and
explicit constraints (word and paragraph limits, "use the text") with regular
expressions only. It is deliberately conservative: anything it cannot classify is
kept as one instruction item so nothing asked is lost. A model-backed structurer can
be layered on top later through the same ``TaskRequest`` contract; its output would
be data validated here, never trusted.

A branch may widen two readings (``branches.base.BranchHooks``; the STEM branches only):
``extract_items(text, extra_imperatives=...)`` takes more imperative verbs (at the start of a
sentence or after a part label such as ``(a)``), and splits a request at a line that opens with
a part label, so a multi-part question becomes one item per part; ``count_answer_words(text,
view=...)`` and ``measure_answer_words(text, excludes=..., view=...)`` measure the words of the
branch's view of the answer (STEM: a maths span or a code block is one word). The defaults
reproduce the general reading exactly.
"""
from __future__ import annotations

import math
import re
from bisect import bisect_left, bisect_right

from .contracts import Constraint, ConstraintScope, RequestItem
from .cues import FORMAT_PHRASES, FORMAT_SUBORDINATORS, FORMAT_VERBS, FORMAT_WORDS, FUNCTION_WORDS, META_LABELS, PLAN_HEADINGS, READER_ADDRESS_CUES, SIDE_REPLY_OPENERS, phrase_regex
from .cues import VERDICT_CUES  # noqa: F401  re-exported: the verdict cue list the channel and the subject parsers share

#: Most request items and constraints a TaskRequest holds (the contract's bounds); what a request states beyond them is
#: counted and reported by the channel, never dropped silently.
MAX_ITEMS = 64
MAX_CONSTRAINTS = 64

_WORD_RE = re.compile(r"(?P<q>no more than|at most|maximum of|max(?:imum)?|up to|under|within|at least|minimum of|min(?:imum)?|exactly|about|around|approximately|in)\s+(?P<n>\d{1,5})\s+words", re.IGNORECASE)
#: A bound written after its number ("300 words max", "250 words or fewer", "a 300-word limit", "150 words minimum").
_WORD_AFTER_RE = re.compile(r"(?P<n>\d{1,5})(?:\s+|-)words?\s+(?P<q>max(?:imum)?|or\s+(?:less|fewer)|at\s+most|tops|min(?:imum)?|or\s+more|at\s+least)\b"
                            r"|(?P<n2>\d{1,5})(?:\s+|-)word\s+(?P<q2>limit|maximum|max|cap)\b", re.IGNORECASE)
_AFTER_MAX = ("max", "maximum", "or less", "or fewer", "at most", "tops", "limit", "cap")
_RANGE_RE = re.compile(r"between\s+(?P<a>\d{1,5})\s+and\s+(?P<b>\d{1,5})\s+words", re.IGNORECASE)
_PARA_RE = re.compile(r"(?P<q>no more than|at most|at least|exactly|in|write|produce|give|compose)\s+(?P<n>one|two|three|four|five|six|a single|\d{1,2})\s+(?:\w+\s+){0,2}?paragraphs?\b", re.IGNORECASE)
_CITE_RE = re.compile(r"\b(quote|quotations?|cite|citing|textual evidence|refer(?:ring)? to the (?:text|passage|extract))\b", re.IGNORECASE)
_IMPERATIVES = ("analyse", "analyze", "discuss", "compare", "contrast", "explain", "evaluate", "to what extent", "examine", "assess", "describe", "outline", "calculate", "show that", "prove", "justify", "identify", "write", "comment on", "how does", "how do", "why does", "what is", "what are",
                "give", "judge", "recommend", "decide", "conclude", "label", "suggest", "interpret", "distinguish", "define", "summarise", "summarize", "argue", "consider")
_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"'(])")
_WORD_NUM = {"one": 1, "a single": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}

# IB command terms by level (shared command-terms document, C1-C3). Longest match wins.
COMMAND_TERMS: dict[str, int] = {
    **{t: 1 for t in ("define", "state", "write down", "list", "label", "draw", "measure", "identify", "recall")},
    **{t: 2 for t in ("outline", "describe", "distinguish", "annotate", "calculate", "find", "determine", "estimate", "sketch", "apply", "explain", "suggest", "compare and contrast", "compare", "contrast", "interpret", "solve", "formulate", "classify", "comment", "demonstrate", "analyse how", "analyze how")},
    **{t: 3 for t in ("analyse", "analyze", "deduce", "derive", "show that", "prove", "verify", "predict", "design", "discuss", "examine", "explore", "evaluate", "assess", "justify", "to what extent", "recommend", "synthesise", "synthesize", "investigate",
                      "give a judgement", "give a judgment", "reach a judgement", "reach a judgment", "judge")},
}
_TERM_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(t) for t in COMMAND_TERMS), key=len, reverse=True)) + r")\b", re.IGNORECASE)
LEVEL3_VERDICT_TERMS = frozenset({"evaluate", "discuss", "to what extent", "assess", "examine", "justify", "recommend", "give a judgement", "give a judgment", "reach a judgement", "reach a judgment", "judge"})


def detect_command_term(sentence: str) -> tuple[str | None, int | None]:
    """First IB command term in the sentence (longest match preferred) and its level."""
    m = _TERM_RE.search(sentence)
    if not m:
        return None, None
    term = m.group(1).lower()
    if term in ("analyse how", "analyze how"):
        term = term.split()[0]
        return term, 3
    return term, COMMAND_TERMS[term]
#: Words that ask for content. A sentence that states a constraint AND carries one of these ("Write no more than 200 words
#: and give a judgement on which effect mattered most") is a request item as well as a constraint.
_CONTENT_CUE_RE = re.compile(
    r"\b(?:analy[sz]e|discuss|compare|contrast|explain|evaluate|to what extent|examine|assess|describe|outline|calculate|show that|prove|justify|identify|comment on|how|why|what|"
    r"give|judge|judge?ment|recommend|decide|conclude|label|suggest|interpret|distinguish|define|summari[sz]e|argue|consider)\b", re.IGNORECASE)
#: Words a constraint clause leaves behind when its span is removed ("Write", "and", "of"), stripped from the front of the
#: residual so the item reads as the content instruction it is.
_RESIDUAL_LEAD_RE = re.compile(r"^(?:[\s,;:.\-]+|(?:write|produce|compose|keep|use|answer|respond|and|then|also|of|in|on|about|regarding|with|to|within)\b)+", re.IGNORECASE)
_RESIDUAL_JOIN_RE = re.compile(r"\s+([.,;:!?])")
#: A preposition or conjunction left dangling at the end once a constraint span is removed ("Give the speed of.", "Please
#: show working, and keep."): stripped, up to three times.
_RESIDUAL_TAIL_RE = re.compile(r"\s*\b(?:of|in|on|with|to|and|within|for|keep)\s*([.,;:!?]*)$", re.IGNORECASE)
#: "Write one paragraph ON <topic>": the words after the paragraph instruction are the topic asked for.
_TOPIC_AFTER_RE = re.compile(r"^\s*(?:on|about|regarding)\s+\S")


def _word_bound_matches(text: str) -> list[re.Match]:
    """Every word-bound span of ``text``: "between A and B words", then "no more than N words" (the qualifier first), then
    "N words max" (the qualifier after; never one that overlaps an earlier span), each pattern's spans in text order, so
    constraint ids follow the order of earlier versions."""
    out: list[re.Match] = list(_RANGE_RE.finditer(text)) + list(_WORD_RE.finditer(text))
    # the earlier spans, sorted, for an overlap test in logarithmic time (a request may state thousands of bounds)
    spans = sorted(m.span() for m in out)
    starts = [a for a, _b in spans]
    reach: list[int] = []  # reach[k]: the furthest end among spans[0..k]
    for _a, b in spans:
        reach.append(max(b, reach[-1]) if reach else b)
    for m in _WORD_AFTER_RE.finditer(text):
        k = bisect_left(starts, m.end()) - 1  # the last earlier span that starts before m ends
        if k < 0 or reach[k] <= m.start():
            out.append(m)
    return out


def _constraint_spans(sentence: str, *, keep_citing: bool = False) -> list[tuple[int, int]]:
    """The constraint spans of ``sentence``: word bounds (with the part labels and the "each" bound to them, so "keep (e)
    under 150 words" is one span), paragraph bounds and, unless ``keep_citing``, citing clauses. A citing clause is also an
    instruction ("Please quote my exact words ..."), so the item text keeps it (``keep_citing``); the constraint is still
    extracted (:func:`extract_constraints`)."""
    spans = []
    for m in _word_bound_matches(sentence):
        start, end = m.span()
        labels = _labels_before(sentence, start)
        if labels:
            start = labels[0][1]
            each = _EACH_RE.match(sentence, end)
            if each is not None:
                end = each.end()
        spans.append((start, end))
    spans += [m.span() for m in _PARA_RE.finditer(sentence)]
    if not keep_citing:
        spans += [m.span() for m in _CITE_RE.finditer(sentence)]
    return sorted(spans)


def _residual(sentence: str) -> tuple[str, bool]:
    """``(residual, topic_follows)``: the sentence without its constraint spans (a citing clause kept: it is the
    instruction itself), and whether a paragraph instruction was followed by "on/about <topic>" (the topic is content
    asked for)."""
    spans = _constraint_spans(sentence, keep_citing=True)
    if not spans:
        return sentence.strip(), False
    topic = any(_TOPIC_AFTER_RE.match(sentence[m.end():]) is not None for m in _PARA_RE.finditer(sentence))
    out: list[str] = []
    cursor = 0
    for start, end in spans:
        if start >= cursor:
            out.append(sentence[cursor:start])
            cursor = end
    out.append(sentence[cursor:])
    residual = _RESIDUAL_JOIN_RE.sub(r"\1", re.sub(r"\s{2,}", " ", "".join(out))).strip()
    residual = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", residual)  # "for me, about 600 words, so" -> "for me, so"
    residual = _RESIDUAL_LEAD_RE.sub("", residual).strip()
    for _ in range(3):
        residual = _RESIDUAL_TAIL_RE.sub(r"\1", residual).strip()
    residual = re.sub(r"\s*[,;:]+\s*([.!?]?)$", r"\1", residual).strip()  # "Please show working, ." -> "Please show working."
    if not re.search(r"[^\W\d_]", residual):
        return "", topic
    return residual[0].upper() + residual[1:], topic


def strip_constraint_spans(sentence: str) -> str:
    """The sentence without its constraint spans (word and paragraph bounds with the part labels bound to them), tidied so
    the content instruction that shared the sentence can be read on its own; empty when nothing but the constraint
    remains. A citing clause stays: "Please quote my exact words when you point out a mistake" is an instruction, and its
    constraint ``must_cite_supplied_text`` is still extracted."""
    return _residual(sentence)[0]


def _asks_for_content(residual: str, topic_follows: bool) -> bool:
    if not residual:
        return False
    if residual.endswith("?") or _CONTENT_CUE_RE.search(residual):
        return True
    return topic_follows and len(re.findall(r"[^\W\d_]+", residual)) >= 2


def is_constraint_only(sentence: str) -> bool:
    """True when a sentence only states a constraint (length, paragraphs, citing) and asks for no content: what is left
    once the constraint spans are removed carries no content cue, is no question and names no topic."""
    if not _constraint_spans(sentence):
        return False
    return not _asks_for_content(*_residual(sentence))
_MAX_Q = ("no more than", "at most", "maximum of", "max", "maximum", "up to", "under", "within")
#: "about / around / approximately N words": a length on both sides, within 10 per cent of N (the first constraint the
#: minimum, the second the maximum, as for "between A and B words").
_ABOUT_Q = ("about", "around", "approximately")
_MIN_Q = ("at least", "minimum of", "min", "minimum")


#: What a request sets outside a word bound, right after it ("no more than 350 words, plus working and your diagram",
#: "(excluding working)", "not counting calculations", "plus your diagram"): the bound is measured over the prose only.
_EXEMPT_RE = re.compile(
    r"^[\s,;(\u2013\u2014-]*(?:plus|excluding|not\s+(?:counting|including)|exclusive\s+of|in\s+addition\s+to|besides)\s+"
    r"(?P<what>(?:(?:your|the|any|all|its)\s+)?(?:working|workings|calculations?|diagrams?|graphs?|sketch(?:es)?|tables?)"
    r"(?:\s*(?:,|and|&|or)\s*(?:(?:your|the|any|all|its)\s+)?(?:working|workings|calculations?|diagrams?|graphs?|sketch(?:es)?|tables?))*)", re.IGNORECASE)


def _exemptions(text: str, end: int) -> list[str]:
    """``["working"]``, ``["diagram"]`` or both when the words right after a word bound set them outside it."""
    rest = text[end:end + 160]
    lead = re.match(r"\s*(?:in\s+total|overall|altogether|in\s+all|for\s+the\s+whole\s+answer)\b", rest, re.IGNORECASE)
    m = _EXEMPT_RE.match(rest[lead.end():] if lead else rest)
    if m is None:
        return []
    what = m.group("what").casefold()
    out = []
    if re.search(r"working|calculation|table", what):
        out.append("working")
    if re.search(r"diagram|graph|sketch", what):
        out.append("diagram")
    return out


#: A part label as a request writes it beside a bound: "(e)", "( ii )", "part (b)", "part b", "parts (e)".
_BOUND_LABEL_RE = re.compile(r"\(\s*(?P<a>[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x|\d{1,2})\s*\)|\bparts?\s+\(?(?P<b>[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x|\d{1,2})\)?(?![\w(])", re.IGNORECASE)
#: What may stand between two labels of one list ("(e) and (f)", "(e), (f) & (g)", "(e)/(f)") and between the last label and
#: the bound's qualifier ("(e) under", "(e) should be under", "(e) [4] (150 words max)"): connectors, a mark annotation, an
#: opening bracket and a few words that bind the label to the bound.
_LABEL_JOIN_RE = re.compile(r"^\s*(?:,|and|&|or|/|plus)?\s*$", re.IGNORECASE)
_LABEL_GAP_RE = re.compile(r"^\s*(?:\[\s*\d+(?:\s*\+\s*\d+)*\s*(?:marks?)?\s*\])?\s*[(\[]?\s*(?:(?:should|must|needs?|has|to|be|is|are|in|within|keep|kept|answered|written|stay|stays|at|answer|it|them)\s+){0,3}[(\[]?\s*$", re.IGNORECASE)
_EACH_RE = re.compile(r"\s*(?:,\s*)?each\b", re.IGNORECASE)
#: A bound the request sets on the whole answer whatever part it stands in ("... 500 words in total", "overall").
_WHOLE_AFTER_RE = re.compile(r"\s*(?:words?\s+)?(?:in\s+total|overall|altogether|in\s+all|for\s+the\s+(?:whole|entire)\b|for\s+everything|for\s+the\s+lot)", re.IGNORECASE)
#: "max 500 words FOR THE ANSWER", "(for the main answer)": the answer proper, without a plan or side answers.
_ANSWER_AFTER_RE = re.compile(r"\s*[,)]?\s*(?:for|of|in|on)\s+the\s+(?:full\s+|main\s+|actual\s+|final\s+|real\s+)?(?:answer|response|essay)\b(?!\s+(?:plan|outline))", re.IGNORECASE)
_ANSWER_BEFORE_RE = re.compile(r"\bthe\s+(?:full\s+|main\s+|actual\s+|final\s+|real\s+)?(?:answer|response|essay)\s+(?:itself\s+)?(?:should|must|needs?\s+to|has\s+to|is\s+to|can)\s+be\s*$", re.IGNORECASE)
#: A paragraph instruction near a bound ("Write ONE body paragraph (max 300 words)", "... ONE paragraph ...? max 250
#: words."): the bound is set on the paragraph the request asks for, not on side answers.
_PARA_ASK_RE = re.compile(r"\b(?:one|two|three|four|five|six|a\s+single|\d{1,2})\s+(?:[^\W\d_]+\s+){0,2}?paragraphs?\b|\bthe\s+paragraph\b", re.IGNORECASE)
#: Sentence cuts for a bound's scope: any sentence mark followed by a space, whatever the case of the next word ("...
#: from the poem? max 250 words. also quick question: ..."), and line breaks.
_SCOPE_SENT_RE = re.compile(r"(?<=[.?!])\s+|\n+")


def _labels_before(text: str, start: int) -> list[tuple[str, int]]:
    """``[(label, offset)]`` of the part labels written immediately before a bound at ``start`` ("keep (e) under 150 words",
    "(e) and (f) under 120 words each"), in order; empty when the words before the bound are not a label list."""
    window_start = max(0, start - 120)
    found = [m for m in _BOUND_LABEL_RE.finditer(text, window_start, start)]
    run: list[re.Match] = []
    tail_end = start
    for m in reversed(found):
        gap = collapse_whitespace(text[m.end():tail_end])
        ok = _LABEL_GAP_RE.match(gap) is not None if not run else _LABEL_JOIN_RE.match(gap) is not None
        if not ok:
            break
        run.insert(0, m)
        tail_end = m.start()
    return [((m.group("a") or m.group("b")).casefold(), m.start()) for m in run]


def _part_spans(text: str) -> list[tuple[str, int, int]]:
    """``[(label, start, end)]`` of the labelled parts of a request (:func:`request_parts`' cut, with offsets)."""
    t = text
    marks = list(_PART_LABEL_RE.finditer(t))
    out: list[tuple[str, int, int]] = []
    for k, m in enumerate(marks):
        end = marks[k + 1].start("label") if k + 1 < len(marks) else len(t)
        if k + 1 == len(marks):
            stop = _PART_END_RE.search(t, m.start("label"), end)
            if stop is not None:
                end = stop.end()
        lab = part_label(t[m.start("label"):end])
        if lab is not None:
            out.append((lab, m.start("label"), end))
    return out


#: Whitespace runs, read as one gap by every scope pattern.
_WHITESPACE_RUN_RE = re.compile(r"\s+")
#: How many characters of the (collapsed) request after a bound and before it its scope words are read in.
_SCOPE_AFTER_WINDOW = 200
_SCOPE_BEFORE_WINDOW = 240


def collapse_whitespace(text: str) -> str:
    """``text`` with every run of whitespace written as one space. The scope patterns read a run of any length as one gap,
    so their result is unchanged; on the collapsed text no run of whitespace can make them backtrack (a request may hold
    400,000 characters)."""
    return _WHITESPACE_RUN_RE.sub(" ", text)


class _ScopeIndex:
    """What every bound's scope reads from one request, computed once (linear in its length): the sentence cuts, the
    labelled parts, and the request with its whitespace runs collapsed, with the offset map into it. Each bound then costs
    a bounded window and a binary search, so a request that states thousands of bounds is read in linear time."""

    def __init__(self, text: str) -> None:
        self.cuts = [0] + [m.end() for m in _SCOPE_SENT_RE.finditer(text)] + [len(text)]
        self.parts = _part_spans(text)
        self.part_starts = [a for _lab, a, _b in self.parts]
        pieces: list[str] = []
        #: (original offset, collapsed offset, is a run of whitespace) at the start of each piece, then the end
        self.marks: list[tuple[int, int, bool]] = []
        pos = col = 0
        for m in _WHITESPACE_RUN_RE.finditer(text):
            if m.start() > pos:
                self.marks.append((pos, col, False))
                pieces.append(text[pos:m.start()])
                col += m.start() - pos
            self.marks.append((m.start(), col, True))
            pieces.append(" ")
            col += 1
            pos = m.end()
        if pos < len(text):
            self.marks.append((pos, col, False))
            pieces.append(text[pos:])
            col += len(text) - pos
        self.marks.append((len(text), col, False))
        self.mark_starts = [a for a, _c, _w in self.marks]
        self.collapsed = "".join(pieces)
        self._paragraph: dict[tuple[int, int], bool] = {}

    def at(self, offset: int) -> int:
        """The collapsed offset of an original offset (inside a run of whitespace: at its one space, or after it)."""
        k = bisect_right(self.mark_starts, offset) - 1
        if k < 0:
            return 0
        a, c, ws = self.marks[k]
        if ws:
            return c if offset == a else c + 1
        return c + (offset - a)

    def sentence(self, pos: int) -> tuple[int, int, int]:
        """``(start of the previous sentence, start, end)`` of the sentence holding offset ``pos``."""
        k = bisect_right(self.cuts, pos) - 1
        if 0 <= k < len(self.cuts) - 1:
            return (self.cuts[k - 1] if k > 0 else self.cuts[k]), self.cuts[k], self.cuts[k + 1]
        return 0, 0, self.cuts[-1]

    def part_at(self, pos: int) -> list[str]:
        """The label of the labelled part of the request that holds offset ``pos`` (empty when none does)."""
        k = bisect_right(self.part_starts, pos) - 1
        if k >= 0:
            lab, a, b = self.parts[k]
            if a <= pos < b:
                return [lab]
        return []

    def paragraph_asked(self, lo: int, hi: int) -> bool:
        """A paragraph instruction between original offsets ``lo`` and ``hi`` (cached: bounds of one sentence share it)."""
        key = (lo, hi)
        if key not in self._paragraph:
            self._paragraph[key] = _PARA_ASK_RE.search(self.collapsed, self.at(lo), self.at(hi)) is not None
        return self._paragraph[key]


def _sentence_bounds(text: str, pos: int) -> tuple[int, int, int]:
    """``(start of the previous sentence, start, end)`` of the sentence of ``text`` holding offset ``pos``."""
    return _ScopeIndex(text).sentence(pos)


def bound_scope(text: str, start: int, end: int, *, _index: _ScopeIndex | None = None) -> ConstraintScope | None:
    """The scope of the word bound at ``text[start:end]`` (None: the whole answer). In order: a bound the request sets "in
    total" or "overall" is the whole answer; the part labels written right before it ("keep (e) under 150 words") or the
    labelled part of the request it stands in ("(e) Explain ... (150 words max)") give ``part``, with "each" after the bound
    and two labels or more ``each_part``; "for the answer" or "the answer should be" gives ``answer_proper``; a paragraph
    instruction in its sentence or the sentence before ("Write ONE body paragraph (max 300 words)") gives ``paragraph``.
    The words after and before the bound are read in a bounded window of the request with its whitespace collapsed
    (:class:`_ScopeIndex`), so the reading is linear in the request's length."""
    idx = _index if _index is not None else _ScopeIndex(text)
    c_end = idx.at(end)
    after = idx.collapsed[c_end:c_end + _SCOPE_AFTER_WINDOW]
    if _WHOLE_AFTER_RE.match(after):
        return None
    labels = [lab for lab, _pos in _labels_before(text, start)]
    each = _EACH_RE.match(after) is not None
    if not labels:
        labels = idx.part_at(start)
    if labels:
        labels = list(dict.fromkeys(labels))
        return ConstraintScope(kind="each_part" if each and len(labels) > 1 else "part", parts=labels[:16])
    prev_start, sent_start, sent_end = idx.sentence(start)
    c_start, c_sent = idx.at(start), idx.at(sent_start)
    if _ANSWER_AFTER_RE.match(after) or _ANSWER_BEFORE_RE.search(idx.collapsed, max(c_sent, c_start - _SCOPE_BEFORE_WINDOW), c_start):
        return ConstraintScope(kind="answer_proper")
    if idx.paragraph_asked(prev_start, sent_end):
        return ConstraintScope(kind="paragraph")
    return None


def extract_constraints(text: str) -> list[Constraint]:
    """Word, paragraph and citing constraints of the request, in order; each word bound carries its scope
    (:func:`bound_scope`). Identical constraints (same kind, value, words, exclusions and scope: a request that repeats
    "about 500 words") are stated once. Use :func:`extract_constraints_counted` for the count beyond the contract bound."""
    return extract_constraints_counted(text)[0]


def extract_constraints_counted(text: str, limit: int = MAX_CONSTRAINTS) -> tuple[list[Constraint], int]:
    """``(constraints, how many more the request states beyond limit)``: :func:`extract_constraints` capped at the
    contract's bound, the overflow counted so the channel can report it (never dropped silently)."""
    out: list[Constraint] = []
    seen: set[tuple] = set()
    overflow = 0

    def add(kind: str, value: str | None, span: str, excludes: list[str] = (), scope: ConstraintScope | None = None) -> None:
        nonlocal overflow
        key = (kind, value, span.strip().casefold(), tuple(excludes), scope.model_dump_json() if scope is not None else None)
        if key in seen:
            return
        seen.add(key)
        if len(out) >= limit:
            overflow += 1
            return
        out.append(Constraint(constraint_id=f"c{len(out) + 1}", kind=kind, value=value, text=span.strip()[:1000], excludes=list(excludes), scope=scope))

    index = _ScopeIndex(text)
    for m in _word_bound_matches(text):
        ex = _exemptions(text, m.end())
        scope = bound_scope(text, m.start(), m.end(), _index=index)
        if m.re is _RANGE_RE:
            add("min_words", m.group("a"), m.group(0), ex, scope)
            add("max_words", m.group("b"), m.group(0), ex, scope)
            continue
        if m.re is _WORD_AFTER_RE:
            n_text = m.group("n") or m.group("n2")
            q = " ".join((m.group("q") or m.group("q2")).lower().split())
            add("max_words" if q in _AFTER_MAX else "min_words", n_text, m.group(0), ex, scope)
            continue
        q = m.group("q").lower()
        if q in _MAX_Q:
            add("max_words", m.group("n"), m.group(0), ex, scope)
        elif q in _MIN_Q:
            add("min_words", m.group("n"), m.group(0), ex, scope)
        elif q == "exactly":
            add("min_words", m.group("n"), m.group(0), ex, scope)
            add("max_words", m.group("n"), m.group(0), ex, scope)
        elif q in _ABOUT_Q:  # "about 250 words": bounded on both sides, 10% either way (225 to 275)
            add("min_words", str(math.ceil(int(m.group("n")) * 0.9)), m.group(0), ex, scope)
            add("max_words", str(int(int(m.group("n")) * 1.1)), m.group(0), ex, scope)
        else:  # "in 350 words": a soft maximum with 10% tolerance
            add("max_words", str(int(int(m.group("n")) * 1.1)), m.group(0), ex, scope)
    for m in _PARA_RE.finditer(text):
        raw = m.group("n").lower()
        val = str(_WORD_NUM.get(raw, raw))
        q = m.group("q").lower()
        if q in ("no more than", "at most"):
            add("max_paragraphs", val, m.group(0))
        elif q == "at least":
            add("min_paragraphs", val, m.group(0))
        else:
            add("min_paragraphs", val, m.group(0))
            add("max_paragraphs", val, m.group(0))
    if _CITE_RE.search(text):
        add("must_cite_supplied_text", None, _CITE_RE.search(text).group(0))
    return out, overflow


#: A line that opens with a part label ('(a)', 'b)', '(ii)', 'Part (c)'): a new item when a branch adds imperatives.
_PART_LINE_RE = re.compile(r"\n[ \t]*(?=\(?(?:[a-h]|i{1,3}|iv|vi{0,3}|ix|x)\)\s|part\s+\(?[a-z0-9]{1,3}\)?\b)", re.IGNORECASE)
#: A part label at the start of a sentence.
_PART_LEAD_RE = re.compile(r"^(?:\(?(?:[a-h]|i{1,3}|iv|vi{0,3}|ix|x)\)\s*|part\s+\(?[a-z0-9]{1,3}\)?[:.]?\s*)+", re.IGNORECASE)


#: The rubric's instruction on how to set out an answer ("Show your working with units.", "Show full working.", "Show all
#: steps clearly."): a way of answering the parts, never a part of its own, whatever imperatives a branch adds.
_SHOW_WORKING_RE = re.compile(
    r"^show\s+(?:(?:all|your|full|the|clear|complete|any|of)\s+)*(?:working|workings|work|steps|method|calculations?)"
    r"(?:\s+(?:clearly|in\s+full|with\s+(?:the\s+)?units))?\s*[.!]?\s*$")


def _leads_with(low: str, words: tuple[str, ...]) -> bool:
    """True when ``low`` (a lower-cased sentence) opens with one of ``words``, after any part label. A sentence that only
    asks for working to be shown (:data:`_SHOW_WORKING_RE`) is no item: the default reading never takes it for one, and
    the imperatives a branch adds do not either."""
    lead = _PART_LEAD_RE.sub("", low, count=1)
    if _SHOW_WORKING_RE.match(lead):
        return False
    return any(lead.startswith(w) and (len(lead) == len(w) or not lead[len(w)].isalpha()) for w in words)


#: A part label of a multi-part question: "(a)", "a)", "(ii)", "ii)", "1.", "2)" standing at the start of the request, of a
#: line, or after the end of a sentence, a mark annotation or a closing quotation mark ("... [3] (b) Find ...", "... exam.
#: 1. Según ...", "... en 2020? 3. Indica ..."), never inside prose ("part (a)", "Paper 2", "1.5").
#: (security round 1) The white space after a sentence's end is read possessively: the label after it cannot begin with white
#: space, and the spaces and tabs read after the run ('[ \t]*') are part of it, so its whole run is the only reading the label can
#: follow and the same labels are found. Split between the two quantifiers, a run of spaces after a full stop with no label after
#: it took 86 s on a request of 32,000 spaces, the base's pattern alike (quadratic); the request's parts were read by it once
#: more in this tree (``_part_spans``) (tests/channel/test_security_round1_parts.py).
_PART_LABEL_RE = re.compile(r"(?:^|(?<=\n)|(?<=[.?!:;\]»\"'”’)])\s++|(?<=[.?!:;\]»\"'”’])(?=\())[ \t]*(?P<label>\((?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|\d{1,2}[.)])(?=\s)")
#: The end of a part: its mark annotation, with any closing quotation mark of the question it belongs to ("... [3]' My
#: answer is pasted below."); what follows is the request's own text again.
#: (security round 1) Its quantifiers possessive, as the mark annotations' (``_MARKS_RE``): the same ends are found.
_PART_END_RE = re.compile(r"\[\s*+\d++\s*+(?:marks?+)?+\s*+\][\'’\"”»]?(?=\s+[A-Z¿¡«\"“])")
#: Sentences for items: like the parsers' cut, but a sentence may also open with an inverted question or exclamation mark,
#: a guillemet or a figure ("¿Quién tuvo ...?").
_ITEM_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"'(¿¡«“‘\d])")
#: A request for content that names no command term: "Please write ...", "Please mark it ... and tell me ...".
_PLEASE_RE = re.compile(r"^(?:please|could you|can you|would you)\b", re.IGNORECASE)


def part_label(text: str) -> str | None:
    """The part label an item or an answer section opens with ("(a) Find ..." -> "a", "3. Indica ..." -> "3", "**Part
    (b) — find" -> "b", "ii) ..." -> "ii"), lower-cased without brackets; None when it opens with none. A nested label
    opens with its outer label: "(a)(i) ..." -> "a", "1(a) ..." -> "1" (the inner one is read after it)."""
    m = re.match(r"^\W{0,4}(?:part\s+)?(\(?(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|\d{1,2}[.)]|\((?:\d{1,2})\)|\d{1,2}(?=\((?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)))"
                 r"(?=[\s*:—–(-]|$)", text.strip(), re.IGNORECASE)
    if m is None:
        return None
    return m.group(1).strip("().").casefold()


def request_parts(text: str) -> list[tuple[str | None, str]]:
    """``(label, text)`` pieces of a request in order: the text before the first part label (label None), each lettered or
    numbered part with its own text (to the next label, or to its mark annotation when the request's own text follows),
    and any text after the last part (label None). A request with no part labels is one piece."""
    t = text.strip()
    marks = list(_PART_LABEL_RE.finditer(t))
    if not marks:
        return [(None, t)] if t else []
    out: list[tuple[str | None, str]] = []
    head = t[:marks[0].start("label")].strip()
    if head:
        out.append((None, head))
    for k, m in enumerate(marks):
        end = marks[k + 1].start("label") if k + 1 < len(marks) else len(t)
        chunk = t[m.start("label"):end]
        tail = ""
        if k + 1 == len(marks):
            stop = _PART_END_RE.search(chunk)
            if stop is not None:
                chunk, tail = chunk[:stop.end()], chunk[stop.end():]
        out.append((part_label(chunk), chunk.strip()))
        if tail.strip():
            out.append((None, tail.strip()))
    return out


def _sentence_items(chunk: str, extra_imperatives: tuple[str, ...] = ()) -> list[tuple[str, str, bool]]:
    """``(item text, kind, is_item)`` per sentence of an unlabelled piece: questions, imperatives and requests ("Please
    ..."), a constraint span removed; a sentence that is only a constraint is not an item. ``extra_imperatives`` (a
    branch's hook) are further imperative verbs, read at the start of a sentence or after a part label."""
    out: list[tuple[str, str, bool]] = []
    for sent in (s.strip() for s in _ITEM_SENT_RE.split(chunk.strip()) if s.strip()):
        if is_constraint_only(sent) and not _PLEASE_RE.match(sent):
            continue  # captured by extract_constraints; not a content item to cover
        item_text, topic_follows = _residual(sent)
        if not item_text:
            continue
        low = item_text.lower()
        is_q = item_text.endswith("?") or "?" in item_text or low.startswith(("how ", "why ", "what ", "to what extent", "in what ways", "¿"))
        is_imp = any(low.startswith(v) or f" {v} " in f" {low} " for v in _IMPERATIVES) or _asks_for_content(item_text, topic_follows) or bool(_PLEASE_RE.match(item_text)) \
            or (bool(extra_imperatives) and _leads_with(low, extra_imperatives))
        out.append((item_text, "question" if is_q else "instruction", is_q or is_imp))
    return out


#: A mark annotation of an exam part ("[2]", "[2 + 2]", "[3 marks]", "(4 marks)"): the part earns marks, so it is an item.
#: (security round 1) Every quantifier of the bracket forms possessive: each is followed by a token its own characters cannot
#: begin (digits by a space, a plus, 'marks' or the closing bracket; a space by a digit, a plus, 'marks' or the bracket), so its
#: longest reading is the only one the rest can follow and the same annotations are read. The spaces after '[1' were split
#: between two or three quantifiers before failing (quadratic in the run) (tests/channel/test_security_round1_marks.py).
_MARKS_RE = re.compile(r"\[\s*+\d++(?:\s*+\+\s*+\d++)*+\s*+(?:marks?+)?+\s*+\]|\(\s*+\d++\s*+marks?+\s*+\)", re.IGNORECASE)
_FORMAT_PHRASE_RE = re.compile(r"\b(?:" + phrase_regex(FORMAT_PHRASES) + r")\b", re.IGNORECASE)
_FORMAT_SUBORDINATOR_RE = re.compile(r"\b(?:" + phrase_regex(FORMAT_SUBORDINATORS) + r")\b", re.IGNORECASE)
_FORMAT_TOKEN_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?")
_FORMAT_WORDS = frozenset(FORMAT_WORDS)
_FORMAT_PLAIN = frozenset(FUNCTION_WORDS) | frozenset(FORMAT_VERBS) | frozenset(w for t in COMMAND_TERMS for w in t.split())


def is_format_instruction(text: str) -> bool:
    """True when an unlabelled request item asks only for the FORM of the answer (its language, its quotations, its parts
    or its manner: "Explain in English pls", "Please quote my exact words when you point out a mistake", "Can you write my
    thesis statement properly and then ONE body paragraph proving it with exact quotes?") and names nothing it is about.
    Read on the item's main clause (a subordinate "when ..." or "if ..." clause after it says when the form applies): once
    the form phrases (:data:`~.cues.FORMAT_PHRASES`), form words (:data:`~.cues.FORMAT_WORDS`), function words, form verbs
    and command terms are set aside nothing may remain, and at least one form phrase or word must have been present. Any
    other word, a number or a single letter is content, so "Prove the statement.", "Use causality and measurement." and
    "Explain." are not format instructions. Bounded and linear: two passes of closed patterns over at most 4,000
    characters."""
    t = (text or "")[:4000]
    sub = next((m for m in _FORMAT_SUBORDINATOR_RE.finditer(t) if t[:m.start()].strip()), None)
    main = t[:sub.start()] if sub is not None else t
    main = _PART_LEAD_RE.sub("", main.strip().lower(), count=1)
    found = bool(_FORMAT_PHRASE_RE.search(main))
    main = _FORMAT_PHRASE_RE.sub(" ", main)
    for tok in _FORMAT_TOKEN_RE.findall(main):
        tok = tok.replace("’", "'")
        if tok in _FORMAT_WORDS:
            found = True
        elif tok not in _FORMAT_PLAIN:
            return False
    return found


def _is_stem(body: str, extra_imperatives: tuple[str, ...] = ()) -> bool:
    """True for a labelled part that asks nothing: no question mark, no mark annotation, no command term, no imperative and
    no "Please ..." ("1. Priya buys a car and borrows €18 000 ...", "2. The Python code from the practice sheet is pasted
    below."): the stem of the parts that follow it, not an item of its own."""
    if "?" in body or "¿" in body or _MARKS_RE.search(body):
        return False
    lead = _PART_LEAD_RE.sub("", body.strip(), count=1)
    low = lead.lower()
    if detect_command_term(lead)[0] is not None or _PLEASE_RE.match(lead) or _asks_for_content(lead, False):
        return False
    if any(low.startswith(v) or f" {v} " in f" {low} " for v in _IMPERATIVES):
        return False
    return not (extra_imperatives and _leads_with(low, extra_imperatives))


_ROMAN_LABELS = frozenset({"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"})


def _label_depth(label: str) -> int:
    """How deep a part label nests: a number (0) holds letters (1), a letter holds roman numerals (2)."""
    return 0 if label.isdigit() else 2 if label in _ROMAN_LABELS else 1


def extract_items(text: str, *, extra_imperatives: tuple[str, ...] = ()) -> list[RequestItem]:
    """Questions and instructions of the request, one item each. A lettered or numbered part ("(a)", "a)", "(ii)", "1.")
    is one item with its own text, whatever language it is in, so a reply that leaves a part out is seen as leaving it out
    (:func:`request_parts`); a bare label with no words of its own ("(a)" before "(i) ...") and a stem that asks nothing
    ("1. Priya buys a car ...", "2. The Python code ... is pasted below.": no question, command term, imperative or mark
    annotation) are no items. The request's own text around the parts yields an item per question, imperative or request
    ("Please mark it ... and tell me where I lost marks"); one that asks only for the form of the answer ("Explain in
    English pls", :func:`is_format_instruction`) is listed as an item that is not required, so the coverage heuristic never
    demands that the answer repeat its words. A sentence that is only a constraint is left to ``extract_constraints``; a
    sentence that mixes a constraint with a content instruction ("Write no more than 200 words and give a judgement on
    which effect mattered most") yields the content instruction as an item, with the constraint span removed (a citing
    clause is kept: it is the instruction), so an answer that omits it is seen as not covering it. Conservative: a sentence
    that carries a question mark is never dropped. ``extra_imperatives`` (a branch's hook; the STEM branches) are further
    imperative verbs, read at the start of a sentence or after a part label; with them, a line that opens with a part label
    (``(a)``, ``b)``, ``Part (c)``) also starts a new piece. With none (every other branch) the reading is the general one
    exactly. At most :data:`MAX_ITEMS` items (:func:`extract_items_counted` counts the rest)."""
    return extract_items_counted(text, extra_imperatives=extra_imperatives)[0]


def extract_items_counted(text: str, *, extra_imperatives: tuple[str, ...] = (), limit: int = MAX_ITEMS) -> tuple[list[RequestItem], int]:
    """``(items, how many more the request asks beyond limit)``: :func:`extract_items`, the overflow counted so the
    channel can report it."""
    items: list[RequestItem] = []
    overflow = 0

    def add(item_text: str, kind: str, required: bool = True) -> None:
        nonlocal overflow
        if len(items) >= limit:
            overflow += 1
            return
        term, level = detect_command_term(item_text)
        items.append(RequestItem(item_id=f"i{len(items) + 1}", text=item_text[:4000], kind=kind, required=required, command_term=term, level=level))

    text = text if isinstance(text, str) else ""
    pieces = [pc for pc in _PART_LINE_RE.split(text.strip()) if pc.strip()] if extra_imperatives else [text]
    parts = [part for piece in pieces for part in request_parts(piece)]
    for k, (label, chunk) in enumerate(parts):
        if label is None:
            for item_text, kind, is_item in _sentence_items(chunk, extra_imperatives):
                if is_item:
                    add(item_text, kind, not is_format_instruction(item_text))
            continue
        kept = [it for it, _k, _i in _sentence_items(chunk, extra_imperatives)]
        body = " ".join(kept).strip()
        own = _MARKS_RE.sub(" ", _PART_LEAD_RE.sub("", body, count=1))
        if not body or not re.search(r"[^\W\d_]", own):  # a bare label: "(a)" whose words are its sub-parts'
            continue
        # a stem asks nothing of its own; it is set aside only when its own sub-parts follow it (the next labelled part is
        # of a deeper kind: "1." then "(a)", "(a)" then "(i)") and that sub-part asks something, so the asks are theirs
        nxt = next(((lab, c) for lab, c in parts[k + 1:] if lab is not None), None)
        if nxt is not None and _label_depth(nxt[0]) > _label_depth(label) and _is_stem(body, extra_imperatives) \
                and not _is_stem(nxt[1], extra_imperatives):
            continue
        add(body, "question" if "?" in body else "instruction")
    if not items and text.strip():
        items.append(RequestItem(item_id="i1", text=text.strip()[:4000], kind="instruction"))
    return items, overflow


#: A word for a word bound. A figure written with internal separators ("1.9", "100,000", "63.2%", "1.9m") is ONE word,
#: as in any word count; every other word is a run of letters, digits, apostrophes and hyphens.
_WORD_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)+[\w%'’-]*|\b[\w'’-]+\b")


def count_words(text: str) -> int:
    """Every word of ``text``, notes included (the raw count); a decimal or thousands-separated figure is one word."""
    return len(_WORD_TOKEN_RE.findall(text))


def _note_core(sentence: str) -> str:
    """The substance of a sentence once its note clauses are set aside (``split_note_clauses``):
    empty when the sentence is nothing but a note (a from-memory label, a self-certification, a
    task note). A dated sentence that carries the label inline ("... in July 1791 (from memory)")
    keeps its core and is part of the answer, as the parsers role it."""
    from ..adapters.markdown import split_note_clauses
    return split_note_clauses(sentence)[0].strip()


def _segments(paragraph: str) -> list[tuple[str, bool]]:
    """``(sentence, is_json)`` pieces of one paragraph, cut as the parsers cut it: every pasted JSON span (a receipt or a
    payload glued to the prose, ``markdown.split_json_spans``) is one piece of its own, and the prose between spans is
    split into sentences. A JSON span therefore never takes the prose around it out of the answer: only its own words
    are meta-text, and the sentences around it are read (and counted) as the claims the parser delivers."""
    from ..adapters.markdown import split_json_spans
    out: list[tuple[str, bool]] = []
    for piece, is_json in split_json_spans(paragraph):
        if is_json:
            out.append((piece, True))
            continue
        out += [(s, False) for s in _SENT_RE.split(piece.strip()) if s.strip()]
    return out


#: A block the writer labels as a note ("Note: ...", "NB:", "Notes -", "Note on sources:"): meta-text when its sentences are
#: about the answer's sources, the task or the method (:data:`_META_CUE_RE`), not part of the answer.
_NOTE_LABEL_RE = re.compile(r"^\W{0,3}(?:notes?|n\.?\s?b\.?|source\s+notes?|notes?\s+on\s+(?:sources?|method|the\s+task|figures?))\s*(?:\([^)]{0,40}\))?\s*[:\-\u2013\u2014]", re.IGNORECASE)
#: What a note says: where the answer's material came from (or did not: a library unavailable, a figure unconfirmed), a
#: correction of the task's own statement (marks, timings, level), or what the writer did or used.
_META_CUE_RE = re.compile(
    r"\b(?:sources?|textbooks?|librar(?:y|ies)|mylib|knowledge\s+(?:base|documents?)|unavailable|not\s+available|(?:un)?confirm\w*|verif\w*|check\w*|"
    r"memory|this\s+session|marked\s+out\s+of|marks?|mark\s+scheme|syllabus|the\s+question|your\s+question|the\s+task|IB|level|assum\w*|"
    r"I\s+(?:use|used|have|had|did|do|give|gave|follow|followed|rely|relied|draw|drew|quote|quoted)|my\s+\w+|its\s+own\s+note|note\s+says)\b", re.IGNORECASE)


def is_note_block(block: str) -> bool:
    """A blank-line block that opens with a note label ("Note:", "NB:", "Note on sources:") and whose every sentence is
    about the answer rather than part of it (its sources or their availability, a correction of the task's figures,
    what the writer used: :data:`_META_CUE_RE`). Such a block is meta-text: no paragraph, no words of a bound. A block
    labelled a note that states content without any such cue stays answer."""
    body = block.strip()
    m = _NOTE_LABEL_RE.match(body)
    if m is None:
        return False
    rest = body[m.end():].strip()
    sentences = [s for s in _SENT_RE.split(rest) if s.strip()] if rest else []
    return bool(sentences) and all(_META_CUE_RE.search(s) for s in sentences)


#: A footer label of meta-text ("Limit:", "Limitations -", "Next step:", "Word count:"; :data:`~.cues.META_LABELS`).
#: (security round 1) The white space after the label is read possessively: the bracket after it, the separator and the space
#: before the separator cannot begin with white space, so its whole run is the only reading the rest can follow, and the
#: label is matched as before. Shared between two quantifiers, a long run after a label with no separator was split between them
#: in every way before failing (quadratic: 1.4 s on 16,000 spaces, 6 s on 32,000) (tests/channel/test_security_round1_meta.py).
_META_LABEL_RE = re.compile(r"^\W{0,3}(?P<label>" + phrase_regex(META_LABELS) + r")\s*+(?:\([^)]{0,40}\))?\s*+[:\-–—]", re.IGNORECASE)
#: A word count written as a line of its own: "(249 words)", "[249 words]", "Word count: 249", "About 270 words".
#: (security round 1) The space around the separator after 'word count' is read possessively, as the label's above: the same
#: lines are word counts (a run of 16,000 spaces after 'Word count' took 8 s, quadratic).
_WORD_COUNT_LINE_RE = re.compile(r"^\W{0,3}(?:word\s*+count\s*+[:\-–—]?+\s*+)?(?:about\s+|approx(?:imately|\.)?\s+|~\s*|c\.\s*)?\d[\d,]*(?:\s+words?)?(?:\s+(?:in\s+total|total|including\s+the\s+title))?\s*[)\]]?\W{0,3}$"
                                 r"|^\W{0,3}word\s*count\b", re.IGNORECASE)
_READER_ADDRESS_RE = re.compile(r"\b(?:" + phrase_regex(READER_ADDRESS_CUES) + r")\b", re.IGNORECASE)
#: Longest closing note read as meta-text by its reader-address cue alone (a longer block is answer).
_TRAILING_NOTE_MAX_WORDS = 60


def is_meta_text(block: str, *, last: bool = False) -> bool:
    """The one meta-text classifier of word and paragraph counts (E2E B19), shared by :func:`count_paragraphs` and
    :func:`measure_answer_words`. A blank-line block is meta-text, not answer, when it is a note block (:func:`is_note_block`),
    a word count on its own ("(249 words)", "Word count: 249"), a "Next step:" or "Word count:" footer, a "Limit:" footer
    that speaks about the answer's sources, checks or availability (:data:`_META_CUE_RE`; a mathematics "Limit:" heading
    stays content) or, with ``last`` (the answer's closing block when it has more than one), a one-line note of at most 60
    words that addresses the reader about the answer itself ("... paste your own paragraph and I will give provisional
    marks": :data:`~.cues.READER_ADDRESS_CUES`). A block that states content under such a label without such a cue stays
    answer."""
    body = (block or "").strip()
    if not body:
        return False
    if is_note_block(body):
        return True
    if "\n" not in body and _WORD_COUNT_LINE_RE.match(body) and re.search(r"\bwords?\b", body, re.IGNORECASE):
        return True
    m = _META_LABEL_RE.match(body)
    if m is not None:
        label = " ".join(m.group("label").casefold().split())
        if label.startswith(("next", "word")):
            return True
        rest = body[m.end():]
        return bool(_META_CUE_RE.search(rest) or _READER_ADDRESS_RE.search(rest))
    return last and "\n" not in body and count_words(body) <= _TRAILING_NOTE_MAX_WORDS and bool(_READER_ADDRESS_RE.search(body))


def answer_blocks(text: str) -> list[str]:
    """The answer's blank-line blocks, markup removed (headings, fences), empty blocks left out."""
    from ..adapters.markdown import strip_markup
    return [p for p in re.split(r"\n\s*\n", strip_markup(text).strip()) if p.strip()]


def _meta_flags(blocks: list[str]) -> list[bool]:
    """Per block, whether it is meta-text (:func:`is_meta_text`; the closing block of a several-block answer read with
    ``last``)."""
    return [is_meta_text(p, last=(k == len(blocks) - 1 and len(blocks) > 1)) for k, p in enumerate(blocks)]


#: A line of working: an equation or a calculation ("PED = −12.50 ÷ 18.75 = −0.67", "t = 0 h: 1620 − 20 = 1600"), an
#: arrow chain of figures, or a table row.
_EQUATION_RE = re.compile(r"[=≈≅]|\d\s*(?:→|->)\s*[-−]?\$?\d")
_TABLE_ROW_RE = re.compile(r"^\s*\|")
#: A label line with nothing to count but a part label and its marks ("(i) [2 marks]", "(b) [2]", "2025", "2024 (no tax)").
#: (Possessive whitespace quantifiers: each is followed by a token that cannot begin with whitespace, so the lines it matches are
#: unchanged, and a line holding a long run of spaces cannot make it backtrack.)
_LABEL_LINE_RE = re.compile(r"^\s*+(?:\(?[a-z]{1,4}\)|\d{1,2}[.)]|part\s++\(?[a-z0-9]{1,4}\)?)?\s*+(?:\[\s*+\d+(?:\s++(?:marks?|spare))?\s*+\])?\s*+$|^\s*+\d{4}(?:\s*+\([^)]{0,30}\))?\s*+$", re.IGNORECASE)
#: A block of working the writer labels as such ("Working for (b):", "Calculation:", "Workings").
_WORKING_BLOCK_RE = re.compile(r"^\W{0,3}(?:working|workings|calculations?|method)\b[^\n]{0,40}:?\s*$", re.IGNORECASE | re.MULTILINE)
#: A diagram described in words: a block opening "Diagram 1: ...", "Figure 2 -", "Graph:", "Sketch:", or a block of
#: "Axes:", "Curves:", "Labels:" lines.
_DIAGRAM_HEAD_RE = re.compile(r"^\W{0,3}(?:diagram|figure|graph|sketch|chart)\b[^\n]{0,120}?[:.\-\u2013\u2014]", re.IGNORECASE)
_DIAGRAM_LINE_RE = re.compile(r"^\s*(?:axes|axis|x-axis|y-axis|curves?|lines?|labels?|change|shift|equilibri(?:a|um)|areas?|shading|arrows?|key|title)\s*:", re.IGNORECASE)


def _is_working_sentence(sentence: str) -> bool:
    """A sentence of working: an equation or a calculation outside its quotations (a quoted equation in a prose
    sentence, 'the Economics specialist calculates "PED = −0.67"', stays prose)."""
    from ..adapters.markdown import find_quotation_spans
    bare = sentence
    for start, end, _inner in reversed(find_quotation_spans(sentence)):
        bare = bare[:start] + " " * (end - start) + bare[end:]
    return bool(_EQUATION_RE.search(bare))


def measure_answer_words(text: str, *, excludes: tuple[str, ...] | list[str] = (), view=None) -> tuple[int, int, int]:
    """``(answer words, note words, exempt words)`` for a word bound. Notes are left out as :func:`count_answer_words`
    leaves them out (note blocks, note clauses, JSON spans). With ``"working"`` in ``excludes`` (the request said "plus
    working"), lines and sentences of working (equations and calculations outside quotations, arrow chains of figures,
    table rows, part-and-mark label lines, a block the writer heads "Working ...") are exempt; with ``"diagram"``, a
    diagram described in words (a block opening "Diagram 1:", or one of "Axes:", "Curves:", "Labels:" lines) is exempt.
    A line that holds an equation outside its quotations is working as a whole ("Result: PED = −0.67. Demand is price
    inelastic ..." states the result of the working on its line); a prose line that quotes an equation stays prose.
    ``view`` (a branch's hook; the STEM branches) maps the answer to the text its words are counted on (STEM: a maths span
    or a code block is one word) before anything else is read."""
    if view is not None:
        text = view(text)
    answer = notes = exempt = 0
    working, diagram = "working" in excludes, "diagram" in excludes
    blocks = answer_blocks(text)
    for p, meta in zip(blocks, _meta_flags(blocks)):
        if meta:  # the shared meta-text classifier (is_meta_text): no words of a bound, as no paragraph
            notes += count_words(p)
            continue
        lines = [ln for ln in p.strip().split("\n") if ln.strip()]
        if diagram and lines and (_DIAGRAM_HEAD_RE.match(lines[0]) or sum(1 for ln in lines if _DIAGRAM_LINE_RE.match(ln)) >= max(2, len(lines) // 2)):
            exempt += count_words(p)
            continue
        if working and lines and _WORKING_BLOCK_RE.match(lines[0]):
            exempt += count_words(p)
            continue
        pieces = ["\n".join(lines)]
        if working:  # a line of working is set aside whole: a table row, a part-and-mark label, a line holding an equation
            pieces = []
            worked = [bool(_TABLE_ROW_RE.match(ln) or _LABEL_LINE_RE.match(ln) or _is_working_sentence(ln)) for ln in lines]
            # In a block of working (at least half its lines), a line that quotes an equation sources a step of it
            # ('the Economics specialist gives "Pp = $1.90 − $0.40 = $1.50 per litre"') and is working too.
            in_working_block = len(lines) >= 2 and sum(worked) * 2 >= len(lines)
            for ln, w in zip(lines, worked):
                if w or (in_working_block and _EQUATION_RE.search(ln)):
                    exempt += count_words(ln)
                    continue
                pieces.append(ln)
            pieces = [" ".join(pieces)] if pieces else []
        for piece in pieces:
            for s, is_json in _segments(piece.strip()):
                n = count_words(s)
                if is_json:
                    notes += n
                    continue
                if working and _is_working_sentence(s):
                    exempt += n
                    continue
                core = _note_core(s)
                if not core:
                    notes += n
                    continue
                kept = min(n, count_words(core))
                answer += kept
                notes += n - kept
    return answer, notes, exempt


def count_answer_words(text: str, *, view=None) -> tuple[int, int]:
    """``(answer words, note words)``: the words of the answer proper and the words of the
    note blocks and note clauses :func:`count_paragraphs` leaves out (from-memory labels,
    self-certification lines, task notes, pasted JSON spans, a block labelled "Note:" that is
    about the answer's sources or the task, :func:`is_note_block`), so a word bound is measured
    over the same text as a paragraph bound and the receipt can say how many words were meta-text.
    A sentence whose only note is an inline label counts its substance as answer and the label
    as notes. Sentences are cut as the parsers cut them (:func:`_segments`): a JSON fragment
    glued into a paragraph is meta-text on its own and the sentences around it stay answer, so
    adding ``{"n": 1}`` to a paragraph never takes its prose out of a word bound. ``view`` (a branch's hook) maps the
    answer to the text its words are counted on."""
    answer, notes, _exempt = measure_answer_words(text, view=view)
    return answer, notes


def count_paragraphs(text: str) -> int:
    """Paragraphs of the answer proper. A block that is only a note about the text (a
    from-memory label such as 'Dates and figures are from memory; verify them', a block labelled
    "Note:" about the answer's sources or the task, :func:`is_note_block`, or a
    self-certification line, or a pasted JSON span) is not a paragraph the request asked for
    and is not counted; markdown headings and code fences are not paragraphs either. Meta-text is
    read by the classifier :func:`measure_answer_words` shares (:func:`is_meta_text`: a "Limit:" or
    "Next step:" footer, a word count, a closing one-line note to the reader). A block whose
    sentences keep a substance once their inline labels are set aside is a paragraph."""
    count = 0
    blocks = answer_blocks(text)
    for p, meta in zip(blocks, _meta_flags(blocks)):
        if meta:
            continue
        segments = _segments(p.strip())
        if segments and all(is_json or not _note_core(s) for s, is_json in segments):
            continue
        count += 1
    return count


# ------------------------------------------------------------------------------------------- the span a bound is set on (B4)

#: The heading of a plan or outline ("Plan", "Essay plan:", "Outline -"), as a short line of its own or as a label.
_PLAN_HEAD_RE = re.compile(r"^\W{0,3}(?:" + phrase_regex(PLAN_HEADINGS) + r")\b\s*(?P<colon>[:\-–—])?", re.IGNORECASE)
#: The heading of the answer proper after a plan ("Answer", "Full answer:", "Essay").
_ANSWER_HEAD_RE = re.compile(r"^\W{0,3}(?:the\s+)?(?:full\s+|main\s+|final\s+)?(?:answer|essay|response)\s*[:\-–—]?\W{0,3}$", re.IGNORECASE)
#: A bullet or numbered line of a plan, and a labelled plan line ("Judgement: The study supports ...").
_BULLET_RE = re.compile(r"^\s*(?:[-•*·▪◦–]|\d{1,2}[.)])\s+\S")
_LABELLED_LINE_RE = re.compile(r"^\W{0,3}[^\W\d_][\w'’() -]{0,40}?:\s+\S")
_SIDE_OPENER_RE = re.compile(r"^\W{0,3}(?:" + phrase_regex(SIDE_REPLY_OPENERS) + r")\b", re.IGNORECASE)
#: An either-or question of the request ("is 'each one a closed fist' a simile or a metaphor?"): its options.
_ALTERNATIVE_RE = re.compile(r"\b(?:an?\s+)?([^\W\d_]{3,40})\s+or\s+(?:an?\s+)?([^\W\d_]{3,40})\s*\?", re.IGNORECASE)
#: The label (and mark annotation) a section's first line opens with, nested labels included ("(a)(i)", "1(a) [2]").
_SECTION_LEAD_RE = re.compile(r"^\W{0,4}(?:part\s+)?(?:\(?(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x|\d{1,2})[.)]|\d{1,2}(?=\())\)?\s*", re.IGNORECASE)


def _is_heading(block: str) -> bool:
    """A one-line block of at most five words with no sentence mark at its end ("Plan", "Answer", "Paragraph 1")."""
    body = block.strip()
    return "\n" not in body and count_words(body) <= 5 and not re.search(r"[.?!;]\W{0,3}$", body)


def _plan_like(block: str) -> bool:
    """Every line of the block is a bullet or numbered line or a labelled line ("Judgement: ..."): plan content."""
    lines = [ln for ln in block.strip().split("\n") if ln.strip()]
    return bool(lines) and all(_BULLET_RE.match(ln) or _LABELLED_LINE_RE.match(ln) for ln in lines)


def _side_answer(block: str, options: set[str]) -> bool:
    """A reply to the student's own question or work rather than the deliverable: the block's first line opens with a
    second-person reply (:data:`~.cues.SIDE_REPLY_OPENERS`: "Your thesis does not survive ...", "On your 30% figure: ...")
    or states one option of an either-or question of the request ("It is a metaphor: ..." to "a simile or a metaphor?")."""
    first = block.strip().split("\n", 1)[0]
    if _SIDE_OPENER_RE.match(first):
        return True
    low = first.strip().lower()
    for opt in options:
        if re.match(rf"^\W{{0,3}}(?:it\s+is|it['’]s|this\s+is|that\s+is|the\s+answer\s+is)\s+(?:an?\s+)?{re.escape(opt)}\b", low) or re.match(rf"^\W{{0,3}}(?:an?\s+)?{re.escape(opt)}\s*[:.;,]", low):
            return True
    return False


def deliverable_blocks(text: str, request_text: str = "") -> list[str]:
    """The blocks of the answer a bound on "the paragraph" or "the answer" is set on (scope ``paragraph`` or
    ``answer_proper``): the answer's blocks without meta-text (:func:`is_meta_text`), without a plan or outline (its heading
    and the bullet or labelled lines after it, up to the first prose block or an "Answer" heading), without heading lines,
    and without the side answers at its start or its end (:func:`_side_answer`), which answer the student's other
    questions. A side answer is set aside only while a block of the deliverable remains: when every block reads as one,
    every block is measured."""
    blocks = answer_blocks(text)
    kept = [p for p, meta in zip(blocks, _meta_flags(blocks)) if not meta]
    out: list[str] = []
    in_plan = False
    for p in kept:
        first = p.strip().split("\n", 1)[0]
        head = _PLAN_HEAD_RE.match(first)
        if head is not None and (count_words(first) <= 4 or head.group("colon")):
            in_plan = True
            continue
        if in_plan:
            if _ANSWER_HEAD_RE.match(first):
                in_plan = False
                continue
            if _plan_like(p):
                continue
            in_plan = False
        if _is_heading(p):
            continue
        out.append(p)
    options = {o.lower() for m in _ALTERNATIVE_RE.finditer(request_text or "") for o in m.groups()}
    side = [_side_answer(p, options) for p in out]
    if out and not all(side):
        lo, hi = 0, len(out)
        while lo < hi and side[lo]:
            lo += 1
        while hi > lo and side[hi - 1]:
            hi -= 1
        out = out[lo:hi]
    return out


def part_section_text(text: str, label: str) -> str | None:
    """The answer's own text for part ``label`` (scope ``part``): every section whose opening line carries the label
    (nested labels too: "(a)(i)" carries a and i, "1(a)" carries 1 and a), from that line to the next labelled line, with
    the section's label and mark annotation taken off its first line. None when no section carries the label: the bound
    then cannot be measured on its scope, and the channel says so. Labels are read as the coverage heuristic reads them
    (markup characters set aside), so a section the coverage test finds is the section a bound is measured on."""
    want = label.casefold()
    chunks: list[list[str]] = []
    current: list[str] | None = None
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        labs = _line_labels(line)
        if labs:
            current = None
            if want in labs:
                current = [_strip_section_lead(line)]
                chunks.append(current)
            continue
        if current is not None:
            current.append(line)
    if not chunks:
        return None
    return "\n\n".join(body for body in ("\n".join(c).strip() for c in chunks) if body)


_MARKUP_CHARS_RE = re.compile(r"[*_`$#]")
#: (security round 1) Every quantifier possessive: each is followed by a token its own characters cannot begin (a digit by a
#: space, a plus, 'marks' or a bracket; a space by a digit, a plus, 'marks' or a bracket), so its longest reading is the only
#: one the rest can follow and the same leads are taken off. The spaces after '[1' were split between three quantifiers before
#: failing (quadratic: 6 s on a line of 64,000 spaces) (tests/channel/test_security_round1_meta.py).
_LEAD_MARKS_RE = re.compile(r"^\s*+(?:\[\s*+\d++(?:\s*+\+\s*+\d++)*+\s*+(?:marks?+)?+\s*+\]|\(\s*+\d++\s*+marks?+\s*+\))", re.IGNORECASE)


def _strip_section_lead(line: str) -> str:
    """A section's first line without its part labels and mark annotation ("(e) [4]" -> "", "(a) A regressive tax is ..."
    -> "A regressive tax is ..."): a label is no word of the answer."""
    s = _MARKUP_CHARS_RE.sub("", line).strip()
    for _ in range(4):
        new = _LEAD_MARKS_RE.sub("", _SECTION_LEAD_RE.sub("", s, count=1), count=1).strip()
        if new == s:
            break
        s = new
    return s


def _line_labels(line: str) -> frozenset[str]:
    """The part labels a line of the answer opens with: its label and a nested one ("(a)(i)", "1(a)", "3. a)")."""
    plain = _MARKUP_CHARS_RE.sub("", line)
    lab = part_label(plain)
    if lab is None:
        return frozenset()
    labels = {lab}
    rest = _SECTION_LEAD_RE.sub("", plain.strip(), count=1)
    inner = part_label(rest) if rest else None
    if inner is not None:
        labels.add(inner)
    return frozenset(labels)
