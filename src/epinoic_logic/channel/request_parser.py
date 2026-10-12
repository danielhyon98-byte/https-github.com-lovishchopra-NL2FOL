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

import math
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


def extract_constraints(text: str) -> list[Constraint]:
    out: list[Constraint] = []
    n = 0

    def add(kind: str, value: str | None, span: str, excludes: list[str] = ()) -> None:
        nonlocal n
        n += 1
        out.append(Constraint(constraint_id=f"c{n}", kind=kind, value=value, text=span.strip(), excludes=list(excludes)))

    for m in _RANGE_RE.finditer(text):
        ex = _exemptions(text, m.end())
        add("min_words", m.group("a"), m.group(0), ex)
        add("max_words", m.group("b"), m.group(0), ex)
    for m in _WORD_RE.finditer(text):
        q = m.group("q").lower()
        ex = _exemptions(text, m.end())
        if q in _MAX_Q:
            add("max_words", m.group("n"), m.group(0), ex)
        elif q in _MIN_Q:
            add("min_words", m.group("n"), m.group(0), ex)
        elif q == "exactly":
            add("min_words", m.group("n"), m.group(0), ex)
            add("max_words", m.group("n"), m.group(0), ex)
        elif q in _ABOUT_Q:  # "about 250 words": bounded on both sides, 10% either way (225 to 275)
            add("min_words", str(math.ceil(int(m.group("n")) * 0.9)), m.group(0), ex)
            add("max_words", str(int(int(m.group("n")) * 1.1)), m.group(0), ex)
        else:  # "in 350 words": a soft maximum with 10% tolerance
            add("max_words", str(int(int(m.group("n")) * 1.1)), m.group(0), ex)
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


#: A part label of a multi-part question: "(a)", "a)", "(ii)", "ii)", "1.", "2)" standing at the start of the request, of a
#: line, or after the end of a sentence, a mark annotation or a closing quotation mark ("... [3] (b) Find ...", "... exam.
#: 1. Según ...", "... en 2020? 3. Indica ..."), never inside prose ("part (a)", "Paper 2", "1.5").
_PART_LABEL_RE = re.compile(r"(?:^|(?<=\n)|(?<=[.?!:;\]»\"'”’)])\s+|(?<=[.?!:;\]»\"'”’])(?=\())[ \t]*(?P<label>\((?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|\d{1,2}[.)])(?=\s)")
#: The end of a part: its mark annotation, with any closing quotation mark of the question it belongs to ("... [3]' My
#: answer is pasted below."); what follows is the request's own text again.
_PART_END_RE = re.compile(r"\[\s*\d+\s*(?:marks?)?\s*\][\'’\"”»]?(?=\s+[A-Z¿¡«\"“])")
#: Sentences for items: like the parsers' cut, but a sentence may also open with an inverted question or exclamation mark,
#: a guillemet or a figure ("¿Quién tuvo ...?").
_ITEM_SENT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"'(¿¡«“‘\d])")
#: A request for content that names no command term: "Please write ...", "Please mark it ... and tell me ...".
_PLEASE_RE = re.compile(r"^(?:please|could you|can you|would you)\b", re.IGNORECASE)


def part_label(text: str) -> str | None:
    """The part label an item or an answer section opens with ("(a) Find ..." -> "a", "3. Indica ..." -> "3", "**Part
    (b) — find" -> "b", "ii) ..." -> "ii"), lower-cased without brackets; None when it opens with none."""
    m = re.match(r"^\W{0,4}(?:part\s+)?(\(?(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|\d{1,2}[.)]|\((?:\d{1,2})\))(?=[\s*:—–-]|$)", text.strip(), re.IGNORECASE)
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


def _sentence_items(chunk: str) -> list[tuple[str, str, bool]]:
    """``(item text, kind, is_item)`` per sentence of an unlabelled piece: questions, imperatives and requests ("Please
    ..."), a constraint span removed; a sentence that is only a constraint is not an item."""
    out: list[tuple[str, str, bool]] = []
    for sent in (s.strip() for s in _ITEM_SENT_RE.split(chunk.strip()) if s.strip()):
        if is_constraint_only(sent) and not _PLEASE_RE.match(sent):
            continue  # captured by extract_constraints; not a content item to cover
        item_text, topic_follows = _residual(sent)
        if not item_text:
            continue
        low = item_text.lower()
        is_q = item_text.endswith("?") or "?" in item_text or low.startswith(("how ", "why ", "what ", "to what extent", "in what ways", "¿"))
        is_imp = any(low.startswith(v) or f" {v} " in f" {low} " for v in _IMPERATIVES) or _asks_for_content(item_text, topic_follows) or bool(_PLEASE_RE.match(item_text))
        out.append((item_text, "question" if is_q else "instruction", is_q or is_imp))
    return out


def extract_items(text: str) -> list[RequestItem]:
    """Questions and instructions of the request, one item each. A lettered or numbered part ("(a)", "a)", "(ii)", "1.")
    is one item with its own text, whatever language it is in, so a reply that leaves a part out is seen as leaving it out
    (:func:`request_parts`); the request's own text around the parts yields an item per question, imperative or request
    ("Please mark it ... and tell me where I lost marks"). A sentence that is only a constraint is left to
    ``extract_constraints``; a sentence that mixes a constraint with a content instruction ("Write no more than 200 words
    and give a judgement on which effect mattered most") yields the content instruction as an item, with the constraint
    span removed, so an answer that omits it is seen as not covering it. Conservative: a sentence that carries a question
    mark is never dropped."""
    items: list[RequestItem] = []

    def add(item_text: str, kind: str) -> None:
        if len(items) >= 64:
            return
        term, level = detect_command_term(item_text)
        items.append(RequestItem(item_id=f"i{len(items) + 1}", text=item_text[:4000], kind=kind, command_term=term, level=level))

    for label, chunk in request_parts(text):
        if label is None:
            for item_text, kind, is_item in _sentence_items(chunk):
                if is_item:
                    add(item_text, kind)
            continue
        kept = [it for it, _k, _i in _sentence_items(chunk)]
        body = " ".join(kept).strip()
        if not body or not re.search(r"[^\W\d_]", body):
            continue
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


#: A line of working: an equation or a calculation ("PED = −12.50 ÷ 18.75 = −0.67", "t = 0 h: 1620 − 20 = 1600"), an
#: arrow chain of figures, or a table row.
_EQUATION_RE = re.compile(r"[=≈≅]|\d\s*(?:→|->)\s*[-−]?\$?\d")
_TABLE_ROW_RE = re.compile(r"^\s*\|")
#: A label line with nothing to count but a part label and its marks ("(i) [2 marks]", "(b) [2]", "2025", "2024 (no tax)").
_LABEL_LINE_RE = re.compile(r"^\s*(?:\(?[a-z]{1,4}\)|\d{1,2}[.)]|part\s+\(?[a-z0-9]{1,4}\)?)?\s*(?:\[\s*\d+(?:\s+(?:marks?|spare))?\s*\])?\s*$|^\s*\d{4}(?:\s*\([^)]{0,30}\))?\s*$", re.IGNORECASE)
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


def measure_answer_words(text: str, *, excludes: tuple[str, ...] | list[str] = ()) -> tuple[int, int, int]:
    """``(answer words, note words, exempt words)`` for a word bound. Notes are left out as :func:`count_answer_words`
    leaves them out (note blocks, note clauses, JSON spans). With ``"working"`` in ``excludes`` (the request said "plus
    working"), lines and sentences of working (equations and calculations outside quotations, arrow chains of figures,
    table rows, part-and-mark label lines, a block the writer heads "Working ...") are exempt; with ``"diagram"``, a
    diagram described in words (a block opening "Diagram 1:", or one of "Axes:", "Curves:", "Labels:" lines) is exempt.
    A line that holds an equation outside its quotations is working as a whole ("Result: PED = −0.67. Demand is price
    inelastic ..." states the result of the working on its line); a prose line that quotes an equation stays prose."""
    from ..adapters.markdown import strip_markup
    answer = notes = exempt = 0
    working, diagram = "working" in excludes, "diagram" in excludes
    for p in re.split(r"\n\s*\n", strip_markup(text).strip()):
        if not p.strip():
            continue
        if is_note_block(p):
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


def count_answer_words(text: str) -> tuple[int, int]:
    """``(answer words, note words)``: the words of the answer proper and the words of the
    note blocks and note clauses :func:`count_paragraphs` leaves out (from-memory labels,
    self-certification lines, task notes, pasted JSON spans, a block labelled "Note:" that is
    about the answer's sources or the task, :func:`is_note_block`), so a word bound is measured
    over the same text as a paragraph bound and the receipt can say how many words were meta-text.
    A sentence whose only note is an inline label counts its substance as answer and the label
    as notes. Sentences are cut as the parsers cut them (:func:`_segments`): a JSON fragment
    glued into a paragraph is meta-text on its own and the sentences around it stay answer, so
    adding ``{"n": 1}`` to a paragraph never takes its prose out of a word bound."""
    answer, notes, _exempt = measure_answer_words(text)
    return answer, notes


def count_paragraphs(text: str) -> int:
    """Paragraphs of the answer proper. A block that is only a note about the text (a
    from-memory label such as 'Dates and figures are from memory; verify them', a block labelled
    "Note:" about the answer's sources or the task, :func:`is_note_block`, or a
    self-certification line, or a pasted JSON span) is not a paragraph the request asked for
    and is not counted; markdown headings and code fences are not paragraphs either. A block
    whose sentences keep a substance once their inline labels are set aside is a paragraph."""
    from ..adapters.markdown import strip_markup
    count = 0
    for p in re.split(r"\n\s*\n", strip_markup(text).strip()):
        if not p.strip() or is_note_block(p):
            continue
        segments = _segments(p.strip())
        if segments and all(is_json or not _note_core(s) for s, is_json in segments):
            continue
        count += 1
    return count
