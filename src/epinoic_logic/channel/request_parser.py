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

_WORD_RE = re.compile(r"(?P<q>no more than|at most|maximum of|max(?:imum)?|up to|under|within|at least|minimum of|min(?:imum)?|exactly|about|around|approximately|in)\s+(?P<n>\d{2,5})\s+words", re.IGNORECASE)
_RANGE_RE = re.compile(r"between\s+(?P<a>\d{2,5})\s+and\s+(?P<b>\d{2,5})\s+words", re.IGNORECASE)
_PARA_RE = re.compile(r"(?P<q>no more than|at most|at least|exactly|in)\s+(?P<n>one|two|three|four|five|six|\d{1,2})\s+(?:body\s+)?paragraphs?", re.IGNORECASE)
_CITE_RE = re.compile(r"\b(quote|quotations?|cite|citing|textual evidence|refer(?:ring)? to the (?:text|passage|extract))\b", re.IGNORECASE)
_IMPERATIVES = ("analyse", "analyze", "discuss", "compare", "contrast", "explain", "evaluate", "to what extent", "examine", "assess", "describe", "outline", "calculate", "show that", "prove", "justify", "identify", "write", "comment on", "how does", "how do", "why does", "what is", "what are")
_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"'(])")
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
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
            items.append(RequestItem(item_id=f"i{len(items) + 1}", text=sent, kind="question" if is_q else "instruction"))
    if not items:
        items.append(RequestItem(item_id="i1", text=text.strip()[:4000], kind="instruction"))
    return items


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'’-]+\b", text))


def count_paragraphs(text: str) -> int:
    return len([p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()])
