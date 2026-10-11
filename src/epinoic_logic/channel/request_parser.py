"""Deterministic structuring of a student's or router's natural-language request.

The channel must know WHAT was asked in order to check WHETHER it was answered.
This parser extracts request items (questions and imperative instructions) and
explicit constraints (word and paragraph limits, "use the text") with regular
expressions only. It is deliberately conservative: anything it cannot classify is
kept as one instruction item so nothing asked is lost. A model-backed structurer can
be layered on top later through the same ``TaskRequest`` contract; its output would
be data validated here, never trusted.
"""
from __future__ import annotations

import re

from .contracts import Constraint, RequestItem

_WORD_RE = re.compile(r"(?P<q>no more than|at most|maximum of|max(?:imum)?|up to|under|within|at least|minimum of|min(?:imum)?|exactly|about|around|approximately|in)\s+(?P<n>\d{1,5})\s+words", re.IGNORECASE)
_RANGE_RE = re.compile(r"between\s+(?P<a>\d{1,5})\s+and\s+(?P<b>\d{1,5})\s+words", re.IGNORECASE)
_PARA_RE = re.compile(r"(?P<q>no more than|at most|at least|exactly|in|write|produce|give|compose)\s+(?P<n>one|two|three|four|five|six|a single|\d{1,2})\s+(?:\w+\s+){0,2}?paragraphs?\b", re.IGNORECASE)
_CITE_RE = re.compile(r"\b(quote|quotations?|cite|citing|textual evidence|refer(?:ring)? to the (?:text|passage|extract))\b", re.IGNORECASE)
_IMPERATIVES = ("analyse", "analyze", "discuss", "compare", "contrast", "explain", "evaluate", "to what extent", "examine", "assess", "describe", "outline", "calculate", "show that", "prove", "justify", "identify", "write", "comment on", "how does", "how do", "why does", "what is", "what are")
_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"'(])")
_WORD_NUM = {"one": 1, "a single": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}

# IB command terms by level (shared command-terms document, C1-C3). Longest match wins.
COMMAND_TERMS: dict[str, int] = {
    **{t: 1 for t in ("define", "state", "write down", "list", "label", "draw", "measure", "identify", "recall")},
    **{t: 2 for t in ("outline", "describe", "distinguish", "annotate", "calculate", "find", "determine", "estimate", "sketch", "apply", "explain", "suggest", "compare and contrast", "compare", "contrast", "interpret", "solve", "formulate", "classify", "comment", "demonstrate", "analyse how", "analyze how")},
    **{t: 3 for t in ("analyse", "analyze", "deduce", "derive", "show that", "prove", "verify", "predict", "design", "discuss", "examine", "explore", "evaluate", "assess", "justify", "to what extent", "recommend", "synthesise", "synthesize", "investigate")},
}
_TERM_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(t) for t in COMMAND_TERMS), key=len, reverse=True)) + r")\b", re.IGNORECASE)
LEVEL3_VERDICT_TERMS = frozenset({"evaluate", "discuss", "to what extent", "assess", "examine", "justify", "recommend"})


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
_CONTENT_CUES = ("analyse", "analyze", "discuss", "compare", "contrast", "explain", "evaluate", "to what extent", "examine", "assess", "describe", "outline", "calculate", "show that", "prove", "justify", "identify", "comment on", "how ", "why ", "what ")


def is_constraint_only(sentence: str) -> bool:
    """True when a sentence only states a constraint (length, paragraphs, citing) and asks for no content."""
    low = sentence.lower()
    has_constraint = bool(_WORD_RE.search(sentence) or _RANGE_RE.search(sentence) or _PARA_RE.search(sentence) or _CITE_RE.search(sentence))
    return has_constraint and not any(c in low for c in _CONTENT_CUES)
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


def extract_items(text: str) -> list[RequestItem]:
    items: list[RequestItem] = []
    for i, sent in enumerate(s.strip() for s in _SENT_RE.split(text.strip()) if s.strip()):
        if is_constraint_only(sent):
            continue  # captured by extract_constraints; not a content item to cover
        low = sent.lower()
        is_q = sent.endswith("?") or low.startswith(("how ", "why ", "what ", "to what extent", "in what ways"))
        is_imp = any(low.startswith(v) or f" {v} " in f" {low} " for v in _IMPERATIVES)
        if is_q or is_imp:
            term, level = detect_command_term(sent)
            items.append(RequestItem(item_id=f"i{len(items) + 1}", text=sent, kind="question" if is_q else "instruction", command_term=term, level=level))
    if not items:
        items.append(RequestItem(item_id="i1", text=text.strip()[:4000], kind="instruction"))
    return items


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'’-]+\b", text))


def count_paragraphs(text: str) -> int:
    """Paragraphs of the answer proper. A block that is only a note about the text (a
    from-memory label such as 'Dates and figures are from memory; verify them', or a
    self-certification line) is not a paragraph the request asked for and is not counted;
    markdown headings and code fences are not paragraphs either."""
    from ..adapters.markdown import is_note_sentence, strip_markup
    count = 0
    for p in re.split(r"\n\s*\n", strip_markup(text).strip()):
        if not p.strip():
            continue
        sentences = [s for s in _SENT_RE.split(p.strip()) if s.strip()]
        if sentences and all(is_note_sentence(s) for s in sentences):
            continue
        count += 1
    return count
