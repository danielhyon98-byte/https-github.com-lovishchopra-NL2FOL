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
view=...)`` measures the words of the branch's view of the answer (STEM: a maths span or a code
block is one word). The defaults reproduce the general reading exactly.
"""
from __future__ import annotations

import re

from .contracts import Constraint, RequestItem
from .cues import VERDICT_CUES  # noqa: F401  re-exported: the verdict cue list the channel and the subject parsers share

_WORD_RE = re.compile(r"(?P<q>no more than|at most|maximum of|max(?:imum)?|up to|under|within|at least|minimum of|min(?:imum)?|exactly|about|around|approximately|in)\s+(?P<n>\d{1,5})\s+words", re.IGNORECASE)
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
#: A preposition or conjunction left dangling at the end once a constraint span is removed ("Give the speed of.").
_RESIDUAL_TAIL_RE = re.compile(r"\s*\b(?:of|in|on|with|to|and|within|for)\s*([.,;:!?]*)$", re.IGNORECASE)
#: "Write one paragraph ON <topic>": the words after the paragraph instruction are the topic asked for.
_TOPIC_AFTER_RE = re.compile(r"^\s*(?:on|about|regarding)\s+\S")


def _constraint_spans(sentence: str) -> list[tuple[int, int]]:
    spans = [m.span() for rx in (_RANGE_RE, _WORD_RE, _PARA_RE, _CITE_RE) for m in rx.finditer(sentence)]
    return sorted(spans)


def _residual(sentence: str) -> tuple[str, bool]:
    """``(residual, topic_follows)``: the sentence without its constraint spans, and whether a
    paragraph instruction was followed by "on/about <topic>" (the topic is content asked for)."""
    spans = _constraint_spans(sentence)
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
    residual = _RESIDUAL_LEAD_RE.sub("", residual).strip()
    residual = _RESIDUAL_TAIL_RE.sub(r"\1", residual).strip()
    if not re.search(r"[^\W\d_]", residual):
        return "", topic
    return residual[0].upper() + residual[1:], topic


def strip_constraint_spans(sentence: str) -> str:
    """The sentence without its constraint spans (word and paragraph bounds, citing clauses), tidied so the content
    instruction that shared the sentence can be read on its own; empty when nothing but the constraint remains."""
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
_MIN_Q = ("at least", "minimum of", "min", "minimum")


def extract_constraints(text: str) -> list[Constraint]:
    out: list[Constraint] = []
    n = 0

    def add(kind: str, value: str | None, span: str) -> None:
        nonlocal n
        n += 1
        out.append(Constraint(constraint_id=f"c{n}", kind=kind, value=value, text=span.strip()))

    for m in _RANGE_RE.finditer(text):
        add("min_words", m.group("a"), m.group(0))
        add("max_words", m.group("b"), m.group(0))
    for m in _WORD_RE.finditer(text):
        q = m.group("q").lower()
        if q in _MAX_Q:
            add("max_words", m.group("n"), m.group(0))
        elif q in _MIN_Q:
            add("min_words", m.group("n"), m.group(0))
        elif q == "exactly":
            add("min_words", m.group("n"), m.group(0))
            add("max_words", m.group("n"), m.group(0))
        else:  # "in 350 words", "about 350 words": treated as a soft maximum with 10% tolerance
            add("max_words", str(int(int(m.group("n")) * 1.1)), m.group(0))
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
    return out


#: A line that opens with a part label ('(a)', 'b)', '(ii)', 'Part (c)'): a new item when a branch adds imperatives.
_PART_LINE_RE = re.compile(r"\n[ \t]*(?=\(?(?:[a-h]|i{1,3}|iv|vi{0,3}|ix|x)\)\s|part\s+\(?[a-z0-9]{1,3}\)?\b)", re.IGNORECASE)
#: A part label at the start of a sentence.
_PART_LEAD_RE = re.compile(r"^(?:\(?(?:[a-h]|i{1,3}|iv|vi{0,3}|ix|x)\)\s*|part\s+\(?[a-z0-9]{1,3}\)?[:.]?\s*)+", re.IGNORECASE)


def _leads_with(low: str, words: tuple[str, ...]) -> bool:
    """True when ``low`` (a lower-cased sentence) opens with one of ``words``, after any part label."""
    lead = _PART_LEAD_RE.sub("", low, count=1)
    return any(lead.startswith(w) and (len(lead) == len(w) or not lead[len(w)].isalpha()) for w in words)


def extract_items(text: str, *, extra_imperatives: tuple[str, ...] = ()) -> list[RequestItem]:
    """Questions and instructions of the request, one item each. A sentence that is only a
    constraint is left to ``extract_constraints``; a sentence that mixes a constraint with a
    content instruction ("Write no more than 200 words and give a judgement on which effect
    mattered most") yields the content instruction as an item, with the constraint span
    removed, so an answer that omits it is seen as not covering it. ``extra_imperatives``
    (a branch's hook) are further imperative verbs, read at the start of a sentence or after
    a part label; with them, a line that opens with a part label also starts a new sentence."""
    items: list[RequestItem] = []
    pieces = _PART_LINE_RE.split(text.strip()) if extra_imperatives else [text.strip()]
    sentences = [s.strip() for piece in pieces for s in _SENT_RE.split(piece.strip()) if s.strip()]
    for sent in sentences:
        if is_constraint_only(sent):
            continue  # captured by extract_constraints; not a content item to cover
        item_text, topic_follows = _residual(sent)
        if not item_text:
            continue
        low = item_text.lower()
        is_q = item_text.endswith("?") or low.startswith(("how ", "why ", "what ", "to what extent", "in what ways"))
        is_imp = any(low.startswith(v) or f" {v} " in f" {low} " for v in _IMPERATIVES) or _asks_for_content(item_text, topic_follows) \
            or (bool(extra_imperatives) and _leads_with(low, extra_imperatives))
        if is_q or is_imp:
            term, level = detect_command_term(item_text)
            items.append(RequestItem(item_id=f"i{len(items) + 1}", text=item_text[:4000], kind="question" if is_q else "instruction", command_term=term, level=level))
    if not items:
        items.append(RequestItem(item_id="i1", text=text.strip()[:4000], kind="instruction"))
    return items


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


def count_answer_words(text: str, *, view=None) -> tuple[int, int]:
    """``(answer words, note words)``: the words of the answer proper and the words of the
    note blocks and note clauses :func:`count_paragraphs` leaves out (from-memory labels,
    self-certification lines, task notes), so a word bound is measured over the same text as
    a paragraph bound and the receipt can say how many words were meta-text. A sentence whose
    only note is an inline label counts its substance as answer and the label as notes.
    ``view`` (a branch's hook) maps the answer to the text its words are counted on."""
    from ..adapters.markdown import strip_markup
    if view is not None:
        text = view(text)
    answer = notes = 0
    for p in re.split(r"\n\s*\n", strip_markup(text).strip()):
        if not p.strip():
            continue
        for s in (x for x in _SENT_RE.split(p.strip()) if x.strip()):
            n = count_words(s)
            core = _note_core(s)
            if not core:
                notes += n
                continue
            kept = min(n, count_words(core))
            answer += kept
            notes += n - kept
    return answer, notes


def count_paragraphs(text: str) -> int:
    """Paragraphs of the answer proper. A block that is only a note about the text (a
    from-memory label such as 'Dates and figures are from memory; verify them', or a
    self-certification line) is not a paragraph the request asked for and is not counted;
    markdown headings and code fences are not paragraphs either. A block whose sentences keep
    a substance once their inline labels are set aside is a paragraph."""
    from ..adapters.markdown import strip_markup
    count = 0
    for p in re.split(r"\n\s*\n", strip_markup(text).strip()):
        if not p.strip():
            continue
        sentences = [s for s in _SENT_RE.split(p.strip()) if s.strip()]
        if sentences and all(not _note_core(s) for s in sentences):
            continue
        count += 1
    return count
