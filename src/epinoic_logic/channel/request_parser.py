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

from .contracts import Constraint, RequestItem
from .cues import VERDICT_CUES  # noqa: F401  re-exported: the verdict cue list the channel and the subject parsers share

_WORD_RE = re.compile(r"(?P<q>no more than|at most|maximum of|max(?:imum)?|up to|under|within|at least|minimum of|min(?:imum)?|exactly|about|around|approximately|in)\s+(?P<n>\d{1,5})\s+words", re.IGNORECASE)
_RANGE_RE = re.compile(r"between\s+(?P<a>\d{1,5})\s+and\s+(?P<b>\d{1,5})\s+words", re.IGNORECASE)
#: Word bounds written in the languages of the Language B courses (round-9 clearance c2, sp-t15: "Escribe entre 450 y 600 palabras."
#: set no bound, so a reply of any length passed): Spanish and French, each phrase read as its English counterpart. Every run is
#: bounded, so a scan is linear.
_RANGE_LB_RE = re.compile(r"\bentre[ \t]{1,3}(?P<a>\d{1,5})[ \t]{1,3}(?:y[ \t]{1,3}(?P<b>\d{1,5})[ \t]{1,3}palabras|et[ \t]{1,3}(?P<c>\d{1,5})[ \t]{1,3}mots)\b",
                          re.IGNORECASE)
_WORD_LB_RE = re.compile(
    r"\b(?P<q>no[ \t]{1,3}m[aá]s[ \t]{1,3}de|como[ \t]{1,3}m[aá]ximo|(?:un[ \t]{1,3})?m[aá]ximo[ \t]{1,3}de|hasta|como[ \t]{1,3}m[ií]nimo"
    r"|(?:un[ \t]{1,3})?m[ií]nimo[ \t]{1,3}de|al[ \t]{1,3}menos|unas|alrededor[ \t]{1,3}de|aproximadamente|cerca[ \t]{1,3}de|exactamente"
    r"|pas[ \t]{1,3}plus[ \t]{1,3}de|au[ \t]{1,3}maximum|au[ \t]{1,3}plus|au[ \t]{1,3}moins|au[ \t]{1,3}minimum|environ|exactement)"
    r"[ \t]{1,3}(?P<n>\d{1,5})[ \t]{1,3}(?P<unit>palabras|mots)\b", re.IGNORECASE)
#: The kind of each phrase of :data:`_WORD_LB_RE`, keyed by its words with the accents dropped and blanks collapsed.
_LB_KIND = {"no mas de": "max", "como maximo": "max", "un maximo de": "max", "maximo de": "max", "hasta": "max", "pas plus de": "max",
            "au maximum": "max", "au plus": "max", "como minimo": "min", "un minimo de": "min", "minimo de": "min", "al menos": "min",
            "au moins": "min", "au minimum": "min", "unas": "about", "alrededor de": "about", "aproximadamente": "about", "cerca de": "about",
            "environ": "about", "exactamente": "exact", "exactement": "exact"}


def _lb_kind(phrase: str) -> str:
    """The kind of a Language B bound phrase (:data:`_LB_KIND`): max, min, about or exact."""
    plain = " ".join(phrase.casefold().translate(str.maketrans("áí", "ai")).split())
    return _LB_KIND[plain]
_PARA_RE = re.compile(r"(?P<q>no more than|at most|at least|exactly|in|write|produce|give|compose)\s+(?P<n>one|two|three|four|five|six|a single|\d{1,2})\s+(?:\w+\s+){0,2}?paragraphs?\b", re.IGNORECASE)
#: A request to cite the supplied texts: "quote", "quoting exactly from the extract" (round-8 clearance c1: lit-t14 and ll-t14
#: asked for quotations with "quoting", which set no constraint), "quotations", "cite", "textual evidence".
_CITE_RE = re.compile(r"\b(quote|quoting|quotations?|cite|citing|textual evidence|refer(?:ring)? to the (?:text|passage|extract))\b", re.IGNORECASE)
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
    spans = [m.span() for rx in (_RANGE_RE, _WORD_RE, _RANGE_LB_RE, _WORD_LB_RE, _PARA_RE, _CITE_RE) for m in rx.finditer(sentence)]
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
    residual = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", residual)  # "for me, about 600 words, so" -> "for me, so"
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


#: A word bound set on each part of the request rather than on the whole reply (round-8 clearance c1, ps-t14: "Write no
#: more than 250 words for each answer" was measured over the whole reply, 441 words, while its two answers measured 216
#: and 211): the scope written right after the bound ("for each answer", "in each part", "for every question", "per
#: answer", "250 words each") or, in the same sentence, before it ("For each answer, write ...", "Each answer should be no
#: more than 250 words"). Every run is bounded and the look-back is a fixed window, so each bound is read in constant time.
_PER_PART_NOUN = r"(?:answer|part|question|response|section|item|sub-?question)s?\b"
_PER_PART_AFTER_RE = re.compile(
    r"[ \t]{0,3}(?:(?:for|in|on)[ \t]{1,3}(?:each|every)[ \t]{1,3}(?:of[ \t]{1,3}(?:the|your)[ \t]{1,3})?|per[ \t]{1,3})" + _PER_PART_NOUN
    + r"|[ \t]{0,3}each(?=[ \t]{0,3}(?:[.,;:)!?\n]|$))", re.IGNORECASE)
#: Read on a fixed window before the bound that starts with a line break when it starts the text, so the scope must open
#: a sentence or a line (a window cut in mid-sentence never opens one).
_PER_PART_BEFORE_RE = re.compile(
    r"(?:[.?!;:][ \t]{1,3}|\n)[ \t]{0,3}(?P<scope>(?:(?:for|in)[ \t]{1,3})?(?:each|every)[ \t]{1,3}" + _PER_PART_NOUN + r"[^.?!\n]{0,80})$", re.IGNORECASE)
#: The same scope read from a bound's own text (:func:`per_part_bound`): the channel and the transfer auditor read the
#: journaled constraint, so both measure the same bound the same way.
_PER_PART_TEXT_RE = re.compile(
    r"\b(?:(?:for|in|on)\s{1,3}(?:each|every)\s{1,3}(?:of\s{1,3}(?:the|your)\s{1,3})?|per\s{1,3})" + _PER_PART_NOUN
    + r"|\bwords\s{1,3}each\b|^\s{0,3}(?:(?:for|in)\s{1,3})?(?:each|every)\s{1,3}" + _PER_PART_NOUN, re.IGNORECASE)
_WHOLE_ANSWER_RE = re.compile(r"\s*(?:in\s+total|overall|altogether|in\s+all|for\s+the\s+whole\s+answer)\b", re.IGNORECASE)


def _per_part_span(text: str, m: "re.Match[str]") -> tuple[str, int] | None:
    """``(span, end)`` of a word bound written with its per-part scope (:data:`_PER_PART_AFTER_RE`,
    :data:`_PER_PART_BEFORE_RE`; ``end`` is where the request's text after the bound and its scope resumes), or None for a
    bound on the whole reply (one followed by "in total", "overall", ...)."""
    if _WHOLE_ANSWER_RE.match(text, m.end()):
        return None
    after = _PER_PART_AFTER_RE.match(text, m.end())
    if after is not None:
        return text[m.start():after.end()], after.end()
    lo = max(0, m.start() - 120)
    before = _PER_PART_BEFORE_RE.search(("\n" if lo == 0 else "") + text[lo:m.start()])
    if before is not None:
        return (before.group("scope") + text[m.start():m.end()]).strip(), m.end()
    return None


def _bound_span(text: str, m: "re.Match[str]") -> tuple[str, list[str]]:
    """The text a word bound is recorded with (its per-part scope included) and what the request sets outside it, read
    right after the bound or after its scope ("no more than 250 words for each answer, plus working")."""
    scoped = _per_part_span(text, m)
    ex = _exemptions(text, m.end())
    if scoped is None:
        return m.group(0), ex
    return scoped[0], ex or _exemptions(text, scoped[1])


def per_part_bound(c: Constraint) -> bool:
    """True for a word bound the request sets on each of its parts ("no more than 250 words for each answer"): its own
    text carries the scope (:func:`extract_constraints` writes it into the span), so a journaled request says it."""
    return c.kind in ("max_words", "min_words") and bool(_PER_PART_TEXT_RE.search(c.text or ""))


#: "about / around / approximately N words": the band the request states (N less and plus a tenth) is a target, not an edge
#: (round-8 clearance c1: en-t14's 276 words against "about 250" was an error by one word), so a measure outside the band
#: but within a quarter of N is reported at warning; a gross miss (146 words for "about 250", round 5) stays an error, as
#: does every hard bound ("no more than", "at least", "exactly").
_ABOUT_TEXT_RE = re.compile(r"\b(?:about|around|approximately)\s{1,3}(?P<n>\d{1,5})\s{1,3}words\b"
                            r"|\b(?:unas|alrededor\s{1,3}de|aproximadamente|cerca\s{1,3}de)\s{1,3}(?P<es>\d{1,5})\s{1,3}palabras\b"
                            r"|\benviron\s{1,3}(?P<fr>\d{1,5})\s{1,3}mots\b", re.IGNORECASE)


def about_target(c: Constraint) -> int | None:
    """N of a word bound read from "about / around / approximately N words", else None."""
    if c.kind not in ("max_words", "min_words"):
        return None
    m = _ABOUT_TEXT_RE.search(c.text or "")
    return int(m.group("n") or m.group("es") or m.group("fr")) if m else None


def about_band(c: Constraint) -> bool:
    """True for a word bound read from "about / around / approximately N words" (:func:`about_target`)."""
    return about_target(c) is not None


def word_bound_severity(c: Constraint | None, measured: int | None = None) -> str:
    """The severity of INT-REQ-005 for a bound not met: a paragraph bound is a warning (a paragraph set out in blocks counts
    as several), and so is an "about N words" band missed by at most a quarter of N; every other word bound, and a band whose
    measure is not given, an error. The channel decides with its measure; the transfer auditor with its own recount."""
    if c is None:
        return "error"
    if c.kind.endswith("paragraphs"):
        return "warning"
    target = about_target(c)
    if target is not None and measured is not None and abs(measured - target) * 4 <= target:
        return "warning"
    return "error"


_MEASURED_RE = re.compile(r"^measured (\d{1,9}) (?:words|paragraphs)\b")


def measured_of(detail: str | None) -> int | None:
    """The count a constraint result's detail opens with ("measured 216 words ..."), as the channel writes it."""
    m = _MEASURED_RE.match(detail or "")
    return int(m.group(1)) if m else None


def extract_constraints(text: str) -> list[Constraint]:
    out: list[Constraint] = []
    n = 0

    def add(kind: str, value: str | None, span: str, excludes: list[str] = ()) -> None:
        nonlocal n
        n += 1
        out.append(Constraint(constraint_id=f"c{n}", kind=kind, value=value, text=span.strip(), excludes=list(excludes)))

    for m in _RANGE_RE.finditer(text):
        span, ex = _bound_span(text, m)
        add("min_words", m.group("a"), span, ex)
        add("max_words", m.group("b"), span, ex)
    for m in _WORD_RE.finditer(text):
        q = m.group("q").lower()
        span, ex = _bound_span(text, m)
        if q in _MAX_Q:
            add("max_words", m.group("n"), span, ex)
        elif q in _MIN_Q:
            add("min_words", m.group("n"), span, ex)
        elif q == "exactly":
            add("min_words", m.group("n"), span, ex)
            add("max_words", m.group("n"), span, ex)
        elif q in _ABOUT_Q:  # "about 250 words": bounded on both sides, 10% either way (225 to 275)
            add("min_words", str(math.ceil(int(m.group("n")) * 0.9)), span, ex)
            add("max_words", str(int(int(m.group("n")) * 1.1)), span, ex)
        else:  # "in 350 words": a soft maximum with 10% tolerance
            add("max_words", str(int(int(m.group("n")) * 1.1)), span, ex)
    # Language B bounds (Spanish, French), each read as its English counterpart above
    for m in _RANGE_LB_RE.finditer(text):
        span, ex = _bound_span(text, m)
        add("min_words", m.group("a"), span, ex)
        add("max_words", m.group("b") or m.group("c"), span, ex)
    for m in _WORD_LB_RE.finditer(text):
        kind = _lb_kind(m.group("q"))
        span, ex = _bound_span(text, m)
        words = int(m.group("n"))
        if kind == "max":
            add("max_words", str(words), span, ex)
        elif kind == "min":
            add("min_words", str(words), span, ex)
        elif kind == "exact":
            add("min_words", str(words), span, ex)
            add("max_words", str(words), span, ex)
        else:  # "unas 300 palabras", "environ 300 mots": the band of "about 300 words"
            add("min_words", str(math.ceil(words * 0.9)), span, ex)
            add("max_words", str(int(words * 1.1)), span, ex)
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
#: The blank run after a sentence end is possessive (integration gate 2): the label never starts with a blank, so the run
#: ends where the label must start, and a long run with no label after it fails in linear time (it was quadratic).
_PART_LABEL_RE = re.compile(r"(?:^|(?<=\n)|(?<=[.?!:;\]»\"'”’)])\s++|(?<=[.?!:;\]»\"'”’])(?=\())[ \t]*(?P<label>\((?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|\d{1,2}[.)])(?=\s)")
#: The end of a part: its mark annotation, with any closing quotation mark of the question it belongs to ("... [3]' My
#: answer is pasted below."); what follows is the request's own text again.
#: Every run is possessive (integration gate 3): the blank runs before and after the optional "marks" met only through it,
#: so a last part ending "[1" before a long blank run backtracked through every split of the run (quadratic in a request);
#: no item after a run starts with a blank or a digit, so every match is the one the backtracking form found.
_PART_END_RE = re.compile(r"\[\s*+\d++\s*+(?:marks?)?\s*+\][\'’\"”»]?(?=\s++[A-Z¿¡«\"“])")
#: Sentences for items: like the parsers' cut, but a sentence may also open with an inverted question or exclamation mark,
#: a guillemet or a figure ("¿Quién tuvo ...?").
_ITEM_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"'(¿¡«“‘\d])")
#: A request for content that names no command term: "Please write ...", "Please mark it ... and tell me ...".
_PLEASE_RE = re.compile(r"^(?:please|could you|can you|would you)\b", re.IGNORECASE)
#: A question heading of a multi-question request ("Question 2 [5 marks]:", "Question 3:", "QUESTION 1.", or a heading on a line
#: of its own, "Question 2 [5 marks]"), at the start of the request, of a line, or after the end of a sentence or a mark annotation (round-8 clearance c1, maa-t14: "Question 2
#: [5 marks]: Solve ..." and "Question 3 [5 marks]: Solve ... Show full working." followed the last lettered part of
#: Question 1 and were in no item). Every run is bounded, so a scan is linear.
_QUESTION_HEAD_RE = re.compile(
    r"(?:^|(?<=\n)|(?<=[.?!:;\]»\"'”’)]))[ \t]{0,6}(?P<head>question[ \t]{1,3}\d{1,2}(?!\d)(?!\.\d)[ \t]{0,3}"
    r"(?:[\[(][ \t]{0,3}\d{1,3}[ \t]{0,3}(?:marks?)?[ \t]{0,3}[\])])?[ \t]{0,3}(?:[:.)\u2013\u2014-]|(?=\r?\n)))", re.IGNORECASE)
#: A sentence that tells the specialist about the request rather than asking it for content (round-8 clearance c1): what a
#: third party will later do with the answer ("A Psychology student will use your answer to evaluate a study ...", bi-p8d),
#: a permission ("Since we're allowed to use our GDC in Paper 1, you can use calculator values ...", maa-t14), or the
#: student's own description of a paper or a task ("... and it only asks me to discuss the study through one concept",
#: breadth ps-3). Its command term is not the specialist's, so it makes no item (and no INT-REQ-008).
_CONTEXT_SENTENCE_RE = re.compile(
    r"\bwill[ \t]{1,3}use[ \t]{1,3}(?:your|the|this|my)[ \t]{1,3}(?:answer|response|work|explanation|results?|summary)[ \t]{1,3}to\b"
    r"|^(?:since|as|because)\b[^.?!]{0,80}?\b(?:allowed|permitted)[ \t]{1,3}to\b"
    r"|\b(?:it|the[ \t]{1,3}(?:paper|section|question|exam|task|rubric))[ \t]{1,3}(?:only[ \t]{1,3})?(?:asks|requires|wants|expects)[ \t]{1,3}"
    r"(?:me|us|you|students|candidates)[ \t]{1,3}to\b", re.IGNORECASE)
#: An instruction about the form of the answer, with no content of its own (round-8 clearance c1, breadth ec-1 and sp-1:
#: "Skip the plan and give the full answer now.", "Write a model answer to this practice task in Spanish."): it makes no
#: coverage item. One that names a topic ("Write an essay on the causes of the war.") is still an item.
_FORM_ONLY_RE = re.compile(
    r"^(?:please[ \t]{1,3})?(?:skip|omit|leave[ \t]{1,3}out|don'?t[ \t]{1,3}(?:give|write|include)|do[ \t]{1,3}not[ \t]{1,3}(?:give|write|include))[ \t]{1,3}"
    r"(?:(?:the|a|your)[ \t]{1,3})?(?:plan|planning|outline|introduction|preamble)\b[^.?!]{0,80}$"
    r"|^(?:please[ \t]{1,3})?(?:write|give|produce|provide)[ \t]{1,3}(?:me[ \t]{1,3})?(?:a|an|the|your)[ \t]{1,3}(?:(?:full|complete|model|sample|final|whole)[ \t]{1,3}){0,3}"
    r"(?:answer|response|text|essay|version)(?:[ \t]{1,3}(?:to|for)[ \t]{1,3}(?:this|the|my)[ \t]{1,3}(?:(?:practice|exam|sample)[ \t]{1,3})?(?:task|question|prompt|exercise))?"
    r"(?:[ \t]{1,3}(?:in|using)[ \t]{1,3}[^\W\d_]{2,20})?(?:[ \t]{1,3}now)?$", re.IGNORECASE)


#: A short label before a colon that opens a request's sentence ("Paper 1 writing practice:", "Exam practice:", "Task:"; round-9
#: clearance c2, sp-t15): the form instruction after it is read as if it opened the sentence. At most 48 characters, no sentence
#: mark, opening with a letter.
_LABEL_LEAD_RE = re.compile(r"^[^\W\d_][^:.?!\n]{0,47}:[ \t]{1,3}")


def is_context_sentence(sentence: str) -> bool:
    """True for a sentence of the request that is context or form, not content asked for (:data:`_CONTEXT_SENTENCE_RE`,
    :data:`_FORM_ONLY_RE`, read after a short label lead such as "Paper 1 writing practice:", :data:`_LABEL_LEAD_RE`); a
    sentence that asks a question is never context."""
    s = sentence.strip()
    if not s or "?" in s or "¿" in s:
        return False
    if _CONTEXT_SENTENCE_RE.search(s[:2000]) or _FORM_ONLY_RE.match(s.rstrip(".! \t")[:400]):
        return True
    lead = _LABEL_LEAD_RE.match(s)
    return bool(lead is not None and _FORM_ONLY_RE.match(s[lead.end():].rstrip(".! \t")[:400]))


#: Task verbs of the Language B courses (round-9 clearance c2, sp-t15: "Escribe un artículo ... en el que expongas las ventajas ... y
#: propongas dos medidas ..." made no item, so a reply that left a task out crossed unnamed): an imperative that opens a sentence
#: (Spanish and French; a choice of text type, "Elige", is form and is not read) and the subjunctive of a task verb in a clause
#: that names what the text must do ("... en el que expongas ...", "... que propongas ..."). Closed lists; matched at word
#: boundaries, case folded.
_LB_IMPERATIVE_RE = re.compile(
    r"^(?:escribe|redacta|explica|describe|compara|analiza|prop[oó]n|justifica|comenta|resume|argumenta|eval[uú]a|discute|exp[oó]n|presenta|"
    r"indica|menciona|defiende|[eé]cris|r[eé]dige|explique|d[eé]cris|justifie|commente|résume|argumente|[eé]value|pr[eé]sente)\b",
    re.IGNORECASE)
#: Only verb forms no English word shares ("compares", "justifies", "proposes" and "exposes" are left out), read only in a sentence
#: whose clause marker "que" stands before the first of them (:func:`language_b_items`).
_LB_SUBJUNCTIVE_RE = re.compile(
    r"\b(?:expongas|propongas|expliques|describas|analices|justifiques|comentes|argumentes|eval[uú]es|discutas|resumas|presentes|"
    r"defiendas|menciones|indiques|d[eé]crives)\b", re.IGNORECASE)
_LB_QUE_RE = re.compile(r"\bque\b", re.IGNORECASE)
#: A conjunction left at the end of a clause cut before the next task verb ("... para tu ciudad y").
_LB_TAIL_RE = re.compile(r"[ \t,;]{1,6}(?:y|e|et)?[ \t]{0,3}$", re.IGNORECASE)


def language_b_items(sentence: str) -> list[str] | None:
    """The items a sentence of a Language B request asks for (:data:`_LB_IMPERATIVE_RE`, :data:`_LB_SUBJUNCTIVE_RE`): one per
    task verb in the subjunctive, each from its verb to the next one ("expongas las ventajas y los inconvenientes del turismo
    para tu ciudad", "propongas dos medidas para mejorar la convivencia entre vecinos y visitantes."), the clause that only
    names the text to write ("Escribe un artículo de opinión ... en el que") being its form; else the whole sentence when it
    opens with a task imperative ("Explica las causas de la crisis."); None for a sentence that asks for no task in these
    languages. Linear: one scan for the verbs."""
    verbs = list(_LB_SUBJUNCTIVE_RE.finditer(sentence))
    que = _LB_QUE_RE.search(sentence)
    if verbs and que is not None and que.start() < verbs[0].start():
        out = []
        for k, m in enumerate(verbs):
            end = verbs[k + 1].start() if k + 1 < len(verbs) else len(sentence)
            piece = sentence[m.start():end]
            piece = _LB_TAIL_RE.sub("", piece) if k + 1 < len(verbs) else piece.strip()
            if piece.strip():
                out.append(piece.strip())
        return out or None
    if _LB_IMPERATIVE_RE.match(sentence.strip()):
        return [sentence.strip()]
    return None


def question_pieces(text: str) -> list[tuple[bool, str]]:
    """``(is_question, piece)``: the request cut at its question headings (:data:`_QUESTION_HEAD_RE`), each question with its
    own text, heading included; the text before the first heading is a piece of its own (False). A request with fewer than
    two headings is one piece."""
    heads = list(_QUESTION_HEAD_RE.finditer(text))
    if len(heads) < 2:
        return [(False, text)]
    out: list[tuple[bool, str]] = []
    first = heads[0].start("head")
    if text[:first].strip():
        out.append((False, text[:first]))
    for k, m in enumerate(heads):
        end = heads[k + 1].start("head") if k + 1 < len(heads) else len(text)
        out.append((True, text[m.start("head"):end]))
    return out


def part_label(text: str) -> str | None:
    """The part label an item or an answer section opens with ("(a) Find ..." -> "a", "3. Indica ..." -> "3", "**Part
    (b) — find" -> "b", "ii) ..." -> "ii"), lower-cased without brackets; None when it opens with none."""
    m = re.match(r"^\W{0,4}(?:part\s+)?(\(?(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|\d{1,2}[.)]|\((?:\d{1,2})\))(?=[\s*:—–-]|$)", text.strip(), re.IGNORECASE)
    if m is None:
        return None
    return m.group(1).strip("().").casefold()


#: A compound part label: a lettered part with its roman sub-part ("(a)(i)", "(a) (i)", "a(i)", "a)(i)"; round-9 clearance c2,
#: ge-t15: the answer's "(a)(i) [1]" and "(a)(ii) [2]" were read as no label, so the request's items (a), (i) and (ii) were reported
#: unaddressed). Bounded, anchored at the start.
_COMPOUND_LABEL_RE = re.compile(r"^\W{0,4}(?:part[ \t]{1,3})?\(?(?P<a>[a-h])\)?[ \t]{0,2}\((?P<b>i{1,3}|iv|vi{0,3}|ix|x)\)(?=[\s*:—–-]|$)", re.IGNORECASE)
#: A lettered part label and a roman sub-part label, as :func:`part_label` returns them.
_LETTER_LABEL_RE = re.compile(r"[a-h]")
_ROMAN_LABEL_RE = re.compile(r"i{1,3}|iv|vi{0,3}|ix|x")


def compound_label(text: str) -> str | None:
    """The compound label an item or an answer section opens with ("(a)(i) Calculate ..." -> "a.i", "a(ii)" -> "a.ii"),
    lower-cased, the part and its sub-part joined by a full stop; None when it opens with none (:data:`_COMPOUND_LABEL_RE`)."""
    m = _COMPOUND_LABEL_RE.match(text.strip()[:40])
    if m is None:
        return None
    return f"{m.group('a').casefold()}.{m.group('b').casefold()}"


def item_label(text: str) -> str | None:
    """The label coverage reads an item by: its compound label ("a.i"), else its part label, else its question label."""
    return compound_label(text) or part_label(text) or question_label(text)


_QUESTION_LABEL_RE = re.compile(r"^\W{0,4}question[ \t]{1,3}(\d{1,2})(?!\d)(?!\.\d)", re.IGNORECASE)


def question_label(text: str) -> str | None:
    """The label of a question heading an item or an answer section opens with ("Question 2 [5 marks]: Solve ..." ->
    "q2", "**Question 3**" -> "q3"); None when it opens with none (round-8 clearance c1: a request's questions are items,
    and the claims under the answer's own "Question 2" heading address the item of Question 2)."""
    m = _QUESTION_LABEL_RE.match(text.strip()[:80])
    return f"q{int(m.group(1))}" if m else None


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


def _sentence_items(chunk: str, extra_imperatives: tuple[str, ...] = (), *, split_language_b: bool = False) -> list[tuple[str, str, bool]]:
    """``(item text, kind, is_item)`` per sentence of an unlabelled piece: questions, imperatives and requests ("Please
    ..."), a constraint span removed; a sentence that is only a constraint is not an item. ``extra_imperatives`` (a
    branch's hook) are further imperative verbs, read at the start of a sentence or after a part label. A task sentence of a
    Language B request is an item too (:func:`language_b_items`), and with ``split_language_b`` (an unlabelled piece, whose items
    are kept apart) each of its subjunctive task clauses is an item of its own."""
    out: list[tuple[str, str, bool]] = []
    for sent in (s.strip() for s in _ITEM_SENT_RE.split(chunk.strip()) if s.strip()):
        if is_constraint_only(sent) and not _PLEASE_RE.match(sent):
            continue  # captured by extract_constraints; not a content item to cover
        item_text, topic_follows = _residual(sent)
        if not item_text:
            continue
        if is_context_sentence(item_text):
            out.append((item_text, "instruction", False))  # context or form: never an item of an unlabelled piece
            continue
        if "?" not in item_text and "¿" not in item_text:
            lb = language_b_items(item_text)
            if lb is not None:
                out += [(t, "instruction", True) for t in (lb if split_language_b else [item_text])]
                continue
        low = item_text.lower()
        is_q = item_text.endswith("?") or "?" in item_text or low.startswith(("how ", "why ", "what ", "to what extent", "in what ways", "¿"))
        is_imp = any(low.startswith(v) or f" {v} " in f" {low} " for v in _IMPERATIVES) or _asks_for_content(item_text, topic_follows) or bool(_PLEASE_RE.match(item_text)) \
            or (bool(extra_imperatives) and _leads_with(low, extra_imperatives))
        out.append((item_text, "question" if is_q else "instruction", is_q or is_imp))
    return out


def extract_items(text: str, *, extra_imperatives: tuple[str, ...] = ()) -> list[RequestItem]:
    """Questions and instructions of the request, one item each. A lettered or numbered part ("(a)", "a)", "(ii)", "1.")
    is one item with its own text, whatever language it is in, so a reply that leaves a part out is seen as leaving it out
    (:func:`request_parts`); the request's own text around the parts yields an item per question, imperative or request
    ("Please mark it ... and tell me where I lost marks"). A sentence that is only a constraint is left to
    ``extract_constraints``; a sentence that mixes a constraint with a content instruction ("Write no more than 200 words
    and give a judgement on which effect mattered most") yields the content instruction as an item, with the constraint
    span removed, so an answer that omits it is seen as not covering it. Conservative: a sentence that carries a question
    mark is never dropped. ``extra_imperatives`` (a branch's hook; the STEM branches) are further imperative verbs, read at
    the start of a sentence or after a part label; with them, a line that opens with a part label (``(a)``, ``b)``,
    ``Part (c)``) also starts a new piece. With none (every other branch) the reading is the general one exactly."""
    items: list[RequestItem] = []

    def add(item_text: str, kind: str) -> None:
        if len(items) >= 64:
            return
        term, level = detect_command_term(item_text)
        items.append(RequestItem(item_id=f"i{len(items) + 1}", text=item_text[:4000], kind=kind, command_term=term, level=level))

    # the request's questions first ("Question 2 [5 marks]: ...", on one line or on lines of their own), then, with a branch's
    # imperatives, the lines that open with a part label within each question
    for is_question, qpiece in question_pieces(text):
        pieces = [pc for pc in _PART_LINE_RE.split(qpiece.strip()) if pc.strip()] if extra_imperatives else [qpiece]
        parts = [part for piece in pieces for part in request_parts(piece)]
        if is_question and not any(label is not None for label, _chunk in parts):
            # a question heading with no lettered parts: the question is one item with its own text
            kept = [it for it, _k, _i in _sentence_items(qpiece, extra_imperatives)]
            body = " ".join(kept).strip()
            if body and re.search(r"[^\W\d_]", body):
                add(body, "question" if "?" in body else "instruction")
            continue
        parent: str | None = None
        for k, (label, chunk) in enumerate(parts):
            if label is None:
                head = _QUESTION_HEAD_RE.match(chunk.lstrip()) if is_question else None
                if head is not None:  # a question's stem before its lettered parts: its parts are the items
                    chunk = chunk.lstrip()[head.end():]
                for item_text, kind, is_item in _sentence_items(chunk, extra_imperatives, split_language_b=True):
                    if is_item:
                        add(item_text, kind)
                continue
            kept = [it for it, _k, _i in _sentence_items(chunk, extra_imperatives)]
            body = " ".join(kept).strip()
            if not body or not re.search(r"[^\W\d_]", body):
                continue
            # rule nested-parts (round-9 clearance c2, ge-t15): a lettered part opens the context of the roman sub-parts after it
            # ("(a) (i) Calculate ... (ii) Calculate ..."); each sub-part is an item named with its part ("(a)(i) Calculate ..."),
            # and a lettered label with no words of its own before its sub-parts is their parent, not an item
            if _LETTER_LABEL_RE.fullmatch(label):
                parent = label
                nxt = parts[k + 1][0] if k + 1 < len(parts) else None
                bare = not re.search(r"[^\W\d_]", re.sub(r"\[[^\]]{0,20}\]", "", re.sub(r"^\W{0,4}\(?[a-hA-H]\)", "", body)))
                if bare and nxt is not None and _ROMAN_LABEL_RE.fullmatch(nxt):
                    continue
            elif parent is not None and _ROMAN_LABEL_RE.fullmatch(label):
                rest = re.sub(r"^\W{0,4}\(?(?:i{1,3}|iv|vi{0,3}|ix|x)\)[ \t]*", "", body, count=1, flags=re.IGNORECASE)
                body = f"({parent})({label}) {rest}".strip()
            else:
                parent = None
            add(body, "question" if "?" in body else "instruction")
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
#: The blank runs around the optional bracket are possessive (integration gate 3): "Note" before a long blank run in an
#: answer backtracked through every split of the run (quadratic); neither the bracket nor the label's mark starts with a
#: blank, so every match is the one the backtracking form found.
_NOTE_LABEL_RE = re.compile(r"^\W{0,3}(?:notes?|n\.?\s?b\.?|source\s+notes?|notes?\s+on\s+(?:sources?|method|the\s+task|figures?))\s*+(?:\([^)]{0,40}\))?\s*+[:\-\u2013\u2014]", re.IGNORECASE)
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


#: A line of working: an equation or a calculation ("PED = −12.50 ÷ 18.75 = −0.67", "t = 0 h: 1620 − 20 = 1600"), an
#: arrow chain of figures, or a table row.
_EQUATION_RE = re.compile(r"[=≈≅]|\d\s*(?:→|->)\s*[-−]?\$?\d")
_TABLE_ROW_RE = re.compile(r"^\s*\|")
#: A label line with nothing to count but a part label and its marks ("(i) [2 marks]", "(b) [2]", "2025", "2024 (no tax)").
#: Every blank run is possessive (integration gate 2): a run is always followed by a label, a '[', a digit, 'marks'/'spare',
#: a ']' or the end of the line, never by a blank, so no shorter run can lead to a match, and a line of blanks followed by
#: another character fails in linear time (three adjacent backtracking runs made it cubic: 9 s at 2,000 blanks).
_LABEL_LINE_RE = re.compile(r"^\s*+(?:\(?[a-z]{1,4}\)|\d{1,2}[.)]|part\s++\(?[a-z0-9]{1,4}\)?)?\s*+(?:\[\s*+\d++(?:\s++(?:marks?|spare))?\s*+\])?\s*+$|^\s*+\d{4}(?:\s*+\([^)]{0,30}\))?\s*+$", re.IGNORECASE)
#: A block of working the writer labels as such ("Working for (b):", "Calculation:", "Workings").
_WORKING_BLOCK_RE = re.compile(r"^\W{0,3}(?:working|workings|calculations?|method)\b[^\n]{0,40}:?\s*$", re.IGNORECASE | re.MULTILINE)
#: A diagram described in words: a block opening "Diagram 1: ...", "Figure 2 -", "Graph:", "Sketch:", or a block of
#: "Axes:", "Curves:", "Labels:" lines.
_DIAGRAM_HEAD_RE = re.compile(r"^\W{0,3}(?:diagram|figure|graph|sketch|chart)\b[^\n]{0,120}?[:.\-\u2013\u2014]", re.IGNORECASE)
_DIAGRAM_LINE_RE = re.compile(r"^\s*(?:axes|axis|x-axis|y-axis|curves?|lines?|labels?|change|shift|equilibri(?:a|um)|areas?|shading|arrows?|key|title)\s*:", re.IGNORECASE)


def blank_quotations(text: str) -> str:
    """``text`` with every quotation span (``adapters.markdown.find_quotation_spans``, marks included) blanked, the length
    kept, in one pass: what blanking each span in turn gave (integration gate 3: the text was rebuilt once per quotation)."""
    from ..adapters.markdown import find_quotation_spans
    spans = find_quotation_spans(text)
    if not spans:
        return text
    parts: list[str] = []
    at = 0
    for start, end, _inner in sorted(spans):
        start = max(start, at)
        if end <= start:
            continue
        parts.append(text[at:start])
        parts.append(" " * (end - start))
        at = end
    parts.append(text[at:])
    return "".join(parts)


def _is_working_sentence(sentence: str) -> bool:
    """A sentence of working: an equation or a calculation outside its quotations (a quoted equation in a prose
    sentence, 'the Economics specialist calculates "PED = −0.67"', stays prose)."""
    return bool(_EQUATION_RE.search(blank_quotations(sentence)))


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
    from ..adapters.markdown import opens_note_paragraph, strip_markup
    if view is not None:
        text = view(text)
    answer = notes = exempt = 0
    working, diagram = "working" in excludes, "diagram" in excludes
    for p in re.split(r"\n\s*\n", strip_markup(text).strip()):
        if not p.strip():
            continue
        # a note block, or a paragraph opened by a bare note lead ("Note:", "N.B.", "Next step:", "Limit:", "Caveat:";
        # ``markdown.opens_note_paragraph``): the parsers role every sentence of it non-material, so none counts
        if is_note_block(p) or opens_note_paragraph(p):
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


def answer_parts(response: str, request_text: str) -> list[tuple[str | None, str]]:
    """``(label, text)`` of each part of the answer, cut at the paragraphs that open with the request's own part labels
    (:func:`request_parts`, :func:`part_label`: "(a) [6]", "**Part (b)**", "2."; a paragraph opens the answer or follows a
    blank line), the text before the first label a piece of its own (label None). The cut is made only when each of the
    request's labels opens exactly one paragraph and they stand in the request's order; otherwise (a part left out, a
    label that also numbers a list set out in paragraphs, labels out of order, a request of fewer than two parts) it is
    empty and the whole answer is measured: the parts are never guessed, so the reading is never laxer. One pass."""
    order: list[str] = []
    for label, _chunk in request_parts(request_text or ""):
        if label is not None and label not in order:
            order.append(label)
    if len(order) < 2 or not response:
        return []
    wanted = set(order)
    opens: list[tuple[str, int]] = []  # (label, offset) of every paragraph that opens with one of the request's labels
    pos = 0
    after_blank = True
    for line in response.splitlines(keepends=True):
        blank = not line.strip()
        if not blank and after_blank:
            lab = part_label(line[:200])
            if lab in wanted:
                opens.append((lab, pos))
                if len(opens) > len(order):
                    return []
        after_blank = blank
        pos += len(line)
    if [lab for lab, _at in opens] != order:
        return []
    cuts = [at for _lab, at in opens]
    out: list[tuple[str | None, str]] = [(None, response[:cuts[0]])]
    for k, (lab, at) in enumerate(opens):
        out.append((lab, response[at:cuts[k + 1] if k + 1 < len(cuts) else len(response)]))
    return [(lab, t) for lab, t in out if t.strip()]


def bound_word_measure(response: str, c: Constraint, *, request_text: str | None, view=None, measure=None) -> tuple[int, int, int, str]:
    """``(measured words, note words, exempt words, scope note)`` for the word bound ``c``: over the whole answer
    (:func:`measure_answer_words` under the bound's ``excludes``), or, for a bound the request sets on each part
    (:func:`per_part_bound`), over each part of the answer (:func:`answer_parts`): the longest part for a maximum (the text
    before the first part counted as a part), the shortest labelled part for a minimum. When the answer's parts cannot be
    told apart, the whole answer is measured and the note says so (never a laxer reading). The channel and the transfer
    auditor both measure a bound with this function; ``measure`` replaces the word measure (the channel passes its own
    binding of :func:`measure_answer_words`)."""
    measure = measure or measure_answer_words
    excludes = tuple(sorted(c.excludes))
    if not per_part_bound(c):
        words, notes, exempt = measure(response, excludes=excludes, view=view)
        return words, notes, exempt, ""
    parts = answer_parts(response, request_text or "")
    if not parts:
        words, notes, exempt = measure(response, excludes=excludes, view=view)
        return words, notes, exempt, "a bound on each answer: the answer's parts cannot be told apart by the request's part labels, so the whole answer is measured"
    counted = [(lab, measure(t, excludes=excludes, view=view)) for lab, t in parts]
    pool = counted if c.kind == "max_words" else ([x for x in counted if x[0] is not None] or counted)
    lab, (words, notes, exempt) = (max if c.kind == "max_words" else min)(pool, key=lambda x: x[1][0])
    each = ", ".join((f"({x}) {m[0]}" if x is not None else f"before the first part {m[0]}") for x, m in counted)
    which = "longest" if c.kind == "max_words" else "shortest"
    return words, notes, exempt, f"a bound on each answer: the {which} answer is measured ({each} words)"


def count_paragraphs(text: str) -> int:
    """Paragraphs of the answer proper. A block that is only a note about the text (a
    from-memory label such as 'Dates and figures are from memory; verify them', a block labelled
    "Note:" about the answer's sources or the task, :func:`is_note_block`, a paragraph opened by a
    bare note lead such as "Note:", "N.B.", "Limit:" or "Caveat:", which the parsers role as a note
    as a whole, or a self-certification line, or a pasted JSON span) is not a paragraph the request asked for
    and is not counted; markdown headings and code fences are not paragraphs either. A block
    whose sentences keep a substance once their inline labels are set aside is a paragraph."""
    from ..adapters.markdown import opens_note_paragraph, strip_markup
    count = 0
    for p in re.split(r"\n\s*\n", strip_markup(text).strip()):
        if not p.strip() or is_note_block(p) or opens_note_paragraph(p):
            continue
        segments = _segments(p.strip())
        if segments and all(is_json or not _note_core(s) for s, is_json in segments):
            continue
        count += 1
    return count
