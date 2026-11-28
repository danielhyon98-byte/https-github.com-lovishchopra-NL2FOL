"""The answer's own scope, segmented and marked by code (meaning-check design 2.5.2).

:func:`own_scope` turns one answer's raw text and the ROUTER's request into the units the label reads:

1. **Invisible characters** (rule N1 of the reader: format characters, controls other than tab and line breaks, variation
   selectors, tag characters, fillers) are removed (a control of the white-space class becomes a space, so words never fuse),
   and THEN every delimiter character of the data blocks (a run of three or more ``<`` or ``>``, ``⟦`` and ``⟧``, including a run
   the removal formed) is replaced by a fixed substitute of the same length. Each rendered character keeps the span of original
   offsets it stands for (the offset map).
2. **Placeholders** are located by code, verbatim, and only inside quotation marks: a quotation whose words occur in a supplied
   text of the request becomes ``⟦source S<n>⟧``, one whose words occur in the router's task text becomes ``⟦task⟧`` (in a
   marking task, the wrong member of a correction pair becomes ``⟦student <n>⟧``). A quotation of certification wording becomes a
   placeholder only inside a relay frame; one the answer asserts as its own ("As I said: '...'") stays visible. Everything else
   stays the answer's own words.
3. **Segments.** Paragraphs (blank lines), their lines, the cells of a table row, then sentences; a sentence over
   :data:`MAX_UNIT` characters is cut at a clause boundary. Each unit is one segment with a place ("paragraph 3, sentence 2").
4. **Chunks** of at most :data:`CHUNK_CHARS` rendered characters or :data:`CHUNK_SENTENCES` sentences, split at paragraph
   boundaries (a paragraph too long for one chunk is split at sentence boundaries), each carrying the previous paragraph as
   context. More than :data:`MAX_CHUNKS` chunks: the answer is ``oversized`` and no call is made.

The context block comes only from the request (writer, subject, task type, marking, whether a true-or-false item is asked, at
most ten known-source titles), through
:func:`epinoic_logic.selfcert.context_for`; the answer never supplies any of it. The reader's segmentation is not public yet
(``selfcert.segments`` and ``selfcert.span_frames`` are API 1.3 work of the reader's owner), so the units are cut here on top of
the reader's public functions; stage 2 moves them to the reader. Every step is one pass, linear in the text's length. Input
that is not a string, or a writer other than ``specialist`` and ``combinator``, raises, and the labeller reads that as
``unavailable`` (``label-failed``), never as an empty answer.
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from .. import selfcert

__all__ = ["Segment", "Paragraph", "Chunk", "OwnScope", "own_scope", "request_field", "SUBSTITUTES",
           "MAX_UNIT", "CHUNK_CHARS", "CHUNK_SENTENCES", "MAX_CHUNKS", "MAX_KNOWN_SOURCES"]

#: A sentence longer than this is cut at a clause boundary (overseer-side design 3.1).
MAX_UNIT = 600
#: A chunk holds at most this many rendered characters (answer text, context and canaries together) ...
CHUNK_CHARS = 8000
#: ... or this many sentences.
CHUNK_SENTENCES = 120
#: Characters of a chunk kept for its canaries and its paragraph of context.
CANARY_RESERVE = 400
CONTEXT_CHARS = 1000
#: More chunks than this: the answer is oversized and withheld, with no call.
MAX_CHUNKS = 6
#: Known-source titles sent in the context block (each cut to 120 characters).
MAX_KNOWN_SOURCES = 10
KNOWN_SOURCE_CHARS = 120
#: Fewest words a quotation needs before it is read against the supplied texts and the task (a shorter one stays own text).
PLACEHOLDER_MIN_WORDS = 2
#: Characters of supplied text and task text scanned in all for placeholders; beyond it every quotation stays own text.
PLACEHOLDER_SCAN_BUDGET = 8_000_000
#: Quotations read for placeholders at most.
MAX_PLACEHOLDER_QUOTES = 256
#: The writers a label is asked for.
WRITERS = ("specialist", "combinator")

#: The fixed substitutes of the delimiter characters (one character for one, so the offset map stays one to one).
SUBSTITUTES = {"<": "‹", ">": "›", "⟦": "〚", "⟧": "〛"}
_SUBSTITUTE_TABLE = str.maketrans(SUBSTITUTES)
_DELIMITER_RUN_RE = re.compile(r"<{3,}|>{3,}|[⟦⟧]")

#: A character that may be invisible: anything but printable ASCII, tab and the line breaks.
_CANDIDATE_RE = re.compile(r"[^\t\n\r\x20-\x7e]")
_INVISIBLE_EXTRA = frozenset([0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F, 0x3164, 0xFFA0])


def _invisible(ch: str) -> bool:
    cp = ord(ch)
    if cp in (9, 10, 13):
        return False
    if 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF or 0xE0000 <= cp <= 0xE007F or cp in _INVISIBLE_EXTRA:
        return True
    return unicodedata.category(ch) in ("Cf", "Cc")


def request_field(obj: Any, name: str) -> Any:
    """``obj[name]`` for a mapping, ``obj.name`` otherwise; None when absent."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


@dataclass(frozen=True)
class Segment:
    """One unit of the answer's own scope. ``text`` is the rendered text; ``origin[i]`` is the span of original offsets the
    rendered character ``i`` stands for; ``forbidden`` the rendered ranges a quote may not touch (placeholders, substitutes)."""
    index: int
    paragraph: int
    sentence: int
    place: str
    start: int
    end: int
    text: str
    origin: tuple[tuple[int, int], ...] = field(repr=False)
    forbidden: tuple[tuple[int, int], ...] = ()

    def original_span(self, a: int, b: int) -> tuple[int, int]:
        """The original offsets of the rendered span ``[a, b)`` of this unit."""
        if not self.origin:
            return (self.start, self.end)
        a = max(0, min(a, len(self.origin) - 1))
        b = max(a + 1, min(b, len(self.origin)))
        return (self.origin[a][0], self.origin[b - 1][1])


@dataclass(frozen=True)
class Paragraph:
    number: int
    segments: tuple[int, ...]  # indices into OwnScope.segments


@dataclass(frozen=True)
class Chunk:
    """``paragraphs``: (paragraph number, segment indices) in order; ``context_only``: the rendered text of the paragraph before
    (cut to :data:`CONTEXT_CHARS`), visible but without ids."""
    index: int
    paragraphs: tuple[tuple[int, tuple[int, ...]], ...]
    context_only: Optional[str] = None


@dataclass(frozen=True)
class OwnScope:
    raw_text: str
    writer: str
    context_block: dict
    ctx: selfcert.Context
    segments: tuple[Segment, ...]
    paragraphs: tuple[Paragraph, ...]
    chunks: tuple[Chunk, ...]
    oversized: bool
    marking: bool
    known_sources: tuple[str, ...]
    command_terms: tuple[str, ...]
    placeholders: int
    invisible_removed: int


# ------------------------------------------------------------------------------------------------- the request's facts
_TASK_FIELDS = ("user_input", "request_text", "text", "prompt", "question", "task")


def _task_text(request: Any) -> str:
    parts: list[str] = []
    for name in _TASK_FIELDS:
        v = request_field(request, name)
        if isinstance(v, str) and v:
            parts.append(v)
    for item in list(request_field(request, "items") or [])[:64]:
        v = request_field(item, "text")
        if isinstance(v, str) and v:
            parts.append(v)
    return "\n".join(parts)


def _supplied_bodies(request: Any) -> list[str]:
    out: list[str] = []
    for st in list(request_field(request, "supplied_texts") or [])[:16]:
        v = request_field(st, "text")
        out.append(v if isinstance(v, str) else "")
    return out


def _command_terms(request: Any) -> tuple[str, ...]:
    out: list[str] = []
    for item in list(request_field(request, "items") or [])[:64]:
        v = request_field(item, "command_term")
        if isinstance(v, str) and v.strip() and len(v) <= 64:
            out.append(" ".join(v.split()).casefold())
    return tuple(dict.fromkeys(out))


def context_block(request: Any, writer: str) -> tuple[dict, selfcert.Context]:
    """The context block (writer, subject, task type, marking, known-source titles) and the reader's context, both from the
    router's request only."""
    if writer not in ("specialist", "combinator"):
        writer = "specialist"
    try:
        ctx = selfcert.context_for(request, writer=writer)
    except Exception:  # noqa: BLE001 - the strict default
        ctx = selfcert.Context(writer=writer)
    subject = request_field(request, "subject")
    task_type = request_field(request, "task_type")
    if task_type is None:
        inner = request_field(request, "request") or request_field(request, "plan")
        task_type = request_field(inner, "task_type")
    titles: list[str] = []
    for t in ctx.known_sources:
        t = " ".join(str(t).split())[:KNOWN_SOURCE_CHARS]
        if t and t not in titles:
            titles.append(t)
        if len(titles) >= MAX_KNOWN_SOURCES:
            break
    block = {
        "writer": writer,
        "subject": _substitute(" ".join(subject.split())[:128]) if isinstance(subject, str) else None,
        "task_type": _substitute(" ".join(task_type.split())[:128]) if isinstance(task_type, str) else None,
        "marking": bool(ctx.marking),
        # whether the router's request asks a true-or-false item (``context_for``): then "Answer: correct" answers it (the
        # reader's X10), so the label reads it as the reader does; it is the router's fact, never the answer's
        "truth_item": bool(ctx.truth_item),
        "known_sources": [_substitute(t) for t in titles],
    }
    return block, ctx


def _substitute(s: str) -> str:
    return _DELIMITER_RUN_RE.sub(lambda m: "".join(SUBSTITUTES[c] for c in m.group(0)), s)


# ------------------------------------------------------------------------------------------------- step 1: clean text
class _Cleaned:
    """The cleaned text and its map back to the raw text, kept as offsets (never one object per character): ``raw_index(i)``
    is the raw offset of the cleaned character ``i``; ``subst`` the sorted (start, end) ranges of substituted delimiter
    characters in the cleaned text; ``removed`` how many invisible characters were removed."""
    __slots__ = ("text", "_e", "subst", "removed")

    def __init__(self, text: str, drops: list[int], subst: list[tuple[int, int]], removed: int):
        self.text = text
        # the raw offset of cleaned character i is i plus the number of removed characters before it: with the removed raw
        # offsets d_0 < d_1 < ..., that number is how many d_j - j are at most i (a non-decreasing list, so one bisection)
        self._e = [d - j for j, d in enumerate(drops)]
        self.subst = subst
        self.removed = removed

    def raw_index(self, i: int) -> int:
        return i + bisect.bisect_right(self._e, i) if self._e else i

    def raw_indices(self, a: int, b: int) -> list[int]:
        """The raw offsets of the cleaned characters ``a`` to ``b - 1``, in one pass."""
        e = self._e
        if not e:
            return list(range(a, b))
        k = bisect.bisect_right(e, a)
        n = len(e)
        out = []
        for i in range(a, b):
            while k < n and e[k] <= i:
                k += 1
            out.append(i + k)
        return out


def _clean(raw: str) -> _Cleaned:
    """The cleaned text: invisible characters removed and white-space controls made spaces, then delimiter runs substituted.

    Invisible characters are removed FIRST, and the delimiter runs are then found on the cleaned text, so a run that the removal
    forms ("<<" + U+200B + "<") is substituted too (attack round 16: it reached the rendered request and failed the marker check).
    A control character of the white-space class (U+000B, U+000C, U+001C to U+001F, U+0085) becomes a space, so it never fuses
    two words ("Every" U+0085 "figure" is read as two words, not one). Each distinct character is classified once and the text
    is rewritten by ``str.translate``; only the removed characters' offsets are listed (the offset map), so the work in Python is
    per distinct character and per removed character, never per character of the text."""
    table: dict[int, Optional[str]] = {}
    dropped: list[str] = []
    for ch in set(raw):
        o = ord(ch)
        if o in (9, 10, 13) or 0x20 <= o <= 0x7E:
            continue  # printable ASCII, tab and the line breaks are never invisible
        if o > 0x7E and _invisible(ch) or o == 0x7F or o < 32:
            if ch.isspace():
                table[o] = " "
            else:
                table[o] = None
                dropped.append(ch)
    drops: list[int] = []
    if dropped:
        drop_re = re.compile("[" + "".join(re.escape(c) for c in sorted(dropped)) + "]")
        drops = [m.start() for m in drop_re.finditer(raw)]
    text = raw.translate(table) if table else raw
    subst: list[tuple[int, int]] = []
    if "<<<" in text or ">>>" in text or "⟦" in text or "⟧" in text:
        subst = [(m.start(), m.end()) for m in _DELIMITER_RUN_RE.finditer(text)]
        text = _DELIMITER_RUN_RE.sub(lambda m: m.group(0).translate(_SUBSTITUTE_TABLE), text)
    return _Cleaned(text, drops, subst, len(drops))


# ------------------------------------------------------------------------------------------------- step 2: placeholders
_WRONG_KEY_BEFORE_RE = re.compile(
    r"(?:^|[\s*_(>\-])(?:wrong|incorrect|error|mistake|mal|incorrecto|incorrecta|err[oó]neo|err[oó]nea|error)[ \t]*[*_]{0,2}[ \t]*:"
    r"[ \t]*[*_]{0,2}[ \t]*\Z", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\W\d_]{1,}")


def _placeholders(text: str, task: str, bodies: list[str], marking: bool,
                  ctx: Optional["selfcert.Context"] = None) -> list[tuple[int, int, str]]:
    """(inner start, inner end, token) of each quotation replaced by a placeholder, in order, never overlapping. A quotation of
    certification wording becomes a placeholder only inside a relay frame (:func:`_relayed`)."""
    if ctx is None:
        ctx = selfcert.Context()
    # a placeholder needs a quotation of at least PLACEHOLDER_MIN_WORDS words found in the task or a supplied text: with neither,
    # or with fewer words than that in the whole answer, no quotation can become one, and the quotation scan is not made (a
    # 200 kB run of quotation marks cost a quarter of a second in it)
    if not task and not any(bodies):
        return []
    words = _WORD_RE.finditer(text)
    if any(next(words, None) is None for _ in range(PLACEHOLDER_MIN_WORDS)):
        return []
    from ..api.adapters import find_quotation_spans
    try:
        spans = find_quotation_spans(text)
    except Exception:  # noqa: BLE001 - no placeholder: every quotation stays own text (the withholding reading)
        return []
    out: list[tuple[int, int, str]] = []
    budget = PLACEHOLDER_SCAN_BUDGET
    last_end = -1
    students = 0
    for start, end, inner in spans[:MAX_PLACEHOLDER_QUOTES]:
        if start < last_end or not isinstance(inner, str):
            continue
        a = text.find(inner, start, end)
        if a < 0 or not inner.strip():
            continue
        b = a + len(inner)
        if len(_WORD_RE.findall(inner)) < PLACEHOLDER_MIN_WORDS:
            continue
        token = None
        for n, body in enumerate(bodies, 1):
            if budget < len(body):
                break
            budget -= len(body)
            if body and inner in body:
                token = f"⟦source S{n}⟧"
                break
        if token is None and task and budget >= len(task):
            budget -= len(task)
            if inner in task:
                if marking and _WRONG_KEY_BEFORE_RE.search(text[max(0, start - 40):start]):
                    students += 1
                    token = f"⟦student {students}⟧"
                else:
                    token = "⟦task⟧"
        if token is not None and not token.startswith("⟦student") and not _relayed(text, start, end, inner, ctx):
            token = None  # the answer asserts certification wording as its own claim: it stays visible to the label
        if token is not None:
            out.append((a, b, token))
            last_end = end
    return out


#: Words that attribute a quotation to the task or to a supplied text (a relay frame).
_ATTRIBUTION_RE = re.compile(
    r"(?<!\w)(?:task|tasks|question|questions|prompt|instruction|instructions|source|sources|text|texts|passage|extract|excerpt|"
    r"author|authors|article|document|title|statement|writer|poem|novel|speech|letter|says|said|states|stated|writes|wrote|asks|"
    r"asked|reads|argues|argued|claims|claimed|puts it|according to|quotes|quoted|tarea|pregunta|enunciado|consigna|fuente|"
    r"fuentes|texto|textos|autor|autora|art[ií]culo|documento|dice|dijo|afirma|afirm[oó]|escribe|escribi[oó]|pregunta|seg[uú]n)"
    r"(?!\w)", re.IGNORECASE)
#: Words by which the answer takes a quotation as its own claim: the first person, or an assertion frame.
_OWN_FRAME_RE = re.compile(
    r"(?<!\w)(?:i|i'm|i've|i'd|me|my|mine|we|we're|we've|us|our|ours|myself|ourselves|as i said|it'?s true|it is true|true that|"
    r"indeed|certainly|definitely|confirm|confirmed|confirms|guarantee|yo|me|mi|mis|nosotros|nosotras|nuestro|nuestra|"
    r"es cierto|es verdad|como dije|confirmo|garantizo)(?!\w)", re.IGNORECASE)
_SENTENCE_STOP_RE = re.compile(r"[.!?\n](?=[^.!?\n]*\Z)")


def _relayed(text: str, start: int, end: int, inner: str, ctx: "selfcert.Context") -> bool:
    """Whether a quotation of task or source wording may become a placeholder: always when its words are no certification
    wording; when they are (the rule reader names a hit or an unread run in them), only inside a relay frame, that is with an
    attribution word around it in its sentence and no first-person or assertion frame ("As I said: '...'", "It's true that
    '...'"). Otherwise the answer asserts the wording as its own claim, and the label must see it (attack round 16: "As I said:
    'every figure was verified by the hub'" was hidden from the label as ⟦task⟧). Any doubt keeps the quotation visible."""
    try:
        reading = selfcert.read(inner, ctx)
    except Exception:  # noqa: BLE001 - doubt: visible
        return False
    if not reading.refuses():
        return True
    before = text[max(0, start - 80):start]
    m = _SENTENCE_STOP_RE.search(before)
    if m:
        before = before[m.end():]
    after = text[end:end + 60]
    stop = min([k for k in (after.find("."), after.find("!"), after.find("?"), after.find("\n")) if k >= 0], default=len(after))
    after = after[:stop]
    window = before + " " + after
    return bool(_ATTRIBUTION_RE.search(window)) and not _OWN_FRAME_RE.search(window)


# ------------------------------------------------------------------------------------------------- step 3: units
_PARA_RE = re.compile(r"\n[ \t\r]*\n")
#: A run of sentence-ending marks with its closing quotation marks and brackets. Both parts are greedy and the match never
#: fails once it starts, so ``finditer`` takes each run whole in one pass; whether the run ends a sentence (white space or the
#: end of the line after it) is tested after the match (attack round 16: the lookahead inside the pattern made a run of 25,000
#: full stops quadratic, 11 s).
_SENT_END_RE = re.compile(r"[.!?…؟。]+[\"'”’»)\]]*")
_CLAUSE_CUT_RE = re.compile(r"[,;:]\s")
_TABLE_SEP_RE = re.compile(r"[\s:|\-+=]*")


def _units_of_line(line: str, base: int) -> list[list[tuple[int, int]]]:
    """The sentences of one line (``base`` is the line's offset in the text), each as its pieces' (start, end) offsets."""
    return list(_iter_units_of_line(line, base))


def _iter_units_of_line(line: str, base: int) -> Iterator[list[tuple[int, int]]]:
    """:func:`_units_of_line` one sentence at a time, in order (so the scope can stop at the oversized cap)."""
    st = line.strip()
    if not st:
        return
    if st.startswith("|") and st.count("|") >= 2:
        if _TABLE_SEP_RE.fullmatch(st):
            a = base + line.find(st[0])
            yield [(a, a + len(st))]
            return
        pos = 0
        for cell in line.split("|"):
            a = base + pos
            pos += len(cell) + 1
            if cell.strip():
                yield from _iter_sentences(cell, a)
        return
    yield from _iter_sentences(line, base)


def _sentences(s: str, base: int) -> list[list[tuple[int, int]]]:
    return list(_iter_sentences(s, base))


def _iter_sentences(s: str, base: int) -> Iterator[list[tuple[int, int]]]:
    pos = 0
    n = len(s)
    for m in _SENT_END_RE.finditer(s):
        if m.end() < n and not s[m.end()].isspace():
            continue
        pieces = _cut(s, pos, m.end(), base)
        if pieces:
            yield pieces
        pos = m.end()
    pieces = _cut(s, pos, len(s), base)
    if pieces:
        yield pieces


def _cut(s: str, a: int, b: int, base: int) -> list[tuple[int, int]]:
    """The sentence ``s[a:b]`` trimmed, cut into pieces of at most MAX_UNIT characters at clause boundaries or white space."""
    while a < b and s[a].isspace():
        a += 1
    while b > a and s[b - 1].isspace():
        b -= 1
    out: list[tuple[int, int]] = []
    while b - a > MAX_UNIT:
        window_end = a + MAX_UNIT
        cut = -1
        for m in _CLAUSE_CUT_RE.finditer(s, a + MAX_UNIT // 2, window_end):
            cut = m.start() + 1
        if cut < 0:
            k = s.rfind(" ", a + MAX_UNIT // 2, window_end)
            cut = k if k > a else window_end
        out.append((base + a, base + cut))
        a = cut
        while a < b and s[a].isspace():
            a += 1
    if b > a:
        out.append((base + a, base + b))
    return out


# ------------------------------------------------------------------------------------------------- the scope
#: The oversized cap in segment characters and in segments: every chunk holds at most CHUNK_CHARS - CANARY_RESERVE characters of
#: segment text and at most CHUNK_SENTENCES segments (:func:`_chunks`), so a scope past either bound needs more than MAX_CHUNKS
#: chunks and is oversized whatever follows; the scope stops being built there (bounded work for an input refused anyway).
CAP_CHARS = MAX_CHUNKS * (CHUNK_CHARS - CANARY_RESERVE)
CAP_SEGMENTS = MAX_CHUNKS * CHUNK_SENTENCES


class _Rendered:
    """The rendered text (the cleaned text with its placeholders) and its maps: each rendered character's original span and
    the rendered ranges a quote may not touch (placeholders and substitutes, adjacent ranges merged)."""

    def __init__(self, cleaned: _Cleaned, marks: list[tuple[int, int, str]]):
        text = cleaned.text
        self.cleaned = cleaned
        parts: list[str] = []
        # pieces: (rendered start, rendered end, cleaned start or None, original span of a placeholder or None)
        pieces: list[tuple[int, int, Optional[int], Optional[tuple[int, int]]]] = []
        r = pos = 0
        for a, b, token in marks:
            if a > pos:
                pieces.append((r, r + a - pos, pos, None))
                parts.append(text[pos:a])
                r += a - pos
            pieces.append((r, r + len(token), None, (cleaned.raw_index(a), cleaned.raw_index(b - 1) + 1)))
            parts.append(token)
            r += len(token)
            pos = b
        if pos < len(text):
            pieces.append((r, r + len(text) - pos, pos, None))
            parts.append(text[pos:])
            r += len(text) - pos
        self.text = "".join(parts) if marks else text
        self.pieces = pieces
        self._starts = [pc[0] for pc in pieces]
        # forbidden rendered ranges: every placeholder, and every substitute outside one, merged where they touch
        forb: list[tuple[int, int]] = []
        subst = cleaned.subst
        k = 0
        for r0, r1, c0, span in pieces:
            if c0 is None:
                forb.append((r0, r1))
                continue
            c1 = c0 + (r1 - r0)
            while k < len(subst) and subst[k][1] <= c0:
                k += 1
            j = k
            while j < len(subst) and subst[j][0] < c1:
                sa, sb = max(subst[j][0], c0), min(subst[j][1], c1)
                if sa < sb:
                    forb.append((r0 + sa - c0, r0 + sb - c0))
                j += 1
        forb.sort()
        merged: list[list[int]] = []
        for fa, fb in forb:
            if merged and fa <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], fb)
            else:
                merged.append([fa, fb])
        self.forbidden = [(fa, fb) for fa, fb in merged]
        self._fstarts = [fa for fa, _fb in self.forbidden]

    def origin(self, ua: int, ub: int) -> tuple[tuple[int, int], ...]:
        """The original span of each rendered character ``ua`` to ``ub - 1``."""
        out: list[tuple[int, int]] = []
        k = max(0, bisect.bisect_right(self._starts, ua) - 1)
        while k < len(self.pieces) and self.pieces[k][0] < ub:
            r0, r1, c0, span = self.pieces[k]
            a, b = max(ua, r0), min(ub, r1)
            if a < b:
                if c0 is None:
                    out.extend([span] * (b - a))
                else:
                    out.extend((o, o + 1) for o in self.cleaned.raw_indices(c0 + a - r0, c0 + b - r0))
            k += 1
        return tuple(out)

    def forbidden_in(self, ua: int, ub: int) -> tuple[tuple[int, int], ...]:
        """The forbidden ranges inside ``[ua, ub)``, relative to ``ua``."""
        out: list[tuple[int, int]] = []
        k = max(0, bisect.bisect_right(self._fstarts, ua) - 1)
        while k < len(self.forbidden) and self.forbidden[k][0] < ub:
            fa, fb = max(self.forbidden[k][0], ua), min(self.forbidden[k][1], ub)
            if fa < fb:
                out.append((fa - ua, fb - ua))
            k += 1
        return tuple(out)


def own_scope(raw_text: str, request: Any = None, *, writer: str = "specialist") -> OwnScope:
    """The own scope of ``raw_text`` read against the router's ``request`` (module docstring). Pure; linear in the text, and
    the segments stop at the oversized cap (:data:`CAP_CHARS`, :data:`CAP_SEGMENTS`): an oversized scope holds the segments up
    to the cap only, since no request is rendered for it."""
    if not isinstance(raw_text, str):
        # unexpected input of any kind is a failure (the labeller's ``label-failed``), never the empty answer read as nothing
        raise TypeError("the answer's raw text must be a string")
    if writer not in WRITERS:
        raise ValueError("the writer must be 'specialist' or 'combinator'")
    block, ctx = context_block(request, writer)
    writer = block["writer"]
    cleaned = _clean(raw_text)
    task = _task_text(request)
    bodies = _supplied_bodies(request)
    marks = _placeholders(cleaned.text, task, bodies, bool(ctx.marking), ctx)
    rendered_map = _Rendered(cleaned, marks)
    rendered = rendered_map.text

    segments: list[Segment] = []
    paragraphs: list[Paragraph] = []
    pnum = 0
    ppos = 0
    seg_chars = 0
    capped = False
    paras = _PARA_RE.finditer(rendered)
    while not capped:
        m = next(paras, None)
        pa, pb = (m.start(), m.end()) if m is not None else (len(rendered), len(rendered))
        para = rendered[ppos:pa]
        para_base = ppos
        ppos = pb
        idx: list[int] = []
        sent = 0
        lpos = 0
        for line in para.split("\n"):
            base = para_base + lpos
            lpos += len(line) + 1
            for pieces in _iter_units_of_line(line, base):
                if not idx:
                    pnum += 1
                sent += 1
                for part, (ua, ub) in enumerate(pieces, 1):
                    place = f"paragraph {pnum}, sentence {sent}" + (f", part {part}" if len(pieces) > 1 else "")
                    uorigin = rendered_map.origin(ua, ub)
                    seg = Segment(index=len(segments), paragraph=pnum, sentence=sent, place=place,
                                  start=uorigin[0][0] if uorigin else 0, end=uorigin[-1][1] if uorigin else 0,
                                  text=rendered[ua:ub], origin=uorigin, forbidden=rendered_map.forbidden_in(ua, ub))
                    idx.append(seg.index)
                    segments.append(seg)
                    seg_chars += ub - ua
                    if seg_chars > CAP_CHARS or len(segments) > CAP_SEGMENTS:
                        capped = True  # oversized whatever follows: the scope stops here, inside a sentence if need be
                        break
                if capped:
                    break
            if capped:
                break
        if idx:
            paragraphs.append(Paragraph(pnum, tuple(idx)))
        if m is None:
            break

    chunks, oversized = _chunks(segments, paragraphs)
    oversized = oversized or capped
    return OwnScope(raw_text=raw_text, writer=writer, context_block=block, ctx=ctx, segments=tuple(segments),
                    paragraphs=tuple(paragraphs), chunks=tuple(chunks), oversized=oversized, marking=bool(ctx.marking),
                    known_sources=tuple(ctx.known_sources), command_terms=_command_terms(request), placeholders=len(marks),
                    invisible_removed=cleaned.removed)


def _chunks(segments: list[Segment], paragraphs: list[Paragraph]) -> tuple[list[Chunk], bool]:
    """Greedy chunks at paragraph boundaries (a paragraph too long for one chunk is split at sentence boundaries)."""
    pieces: list[tuple[int, tuple[int, ...]]] = []  # (paragraph number, segment indices), each fitting one chunk
    for p in paragraphs:
        cur: list[int] = []
        size = 0
        for i in p.segments:
            n = len(segments[i].text)
            if cur and (size + n > CHUNK_CHARS - CANARY_RESERVE - CONTEXT_CHARS or len(cur) >= CHUNK_SENTENCES):
                pieces.append((p.number, tuple(cur)))
                cur, size = [], 0
            cur.append(i)
            size += n
        if cur:
            pieces.append((p.number, tuple(cur)))
    chunks: list[Chunk] = []
    cur_p: list[tuple[int, tuple[int, ...]]] = []
    size = count = 0
    context: Optional[str] = None
    limit = CHUNK_CHARS - CANARY_RESERVE
    for k, (pn, idx) in enumerate(pieces):
        n = sum(len(segments[i].text) for i in idx)
        if cur_p and (size + n > limit or count + len(idx) > CHUNK_SENTENCES):
            chunks.append(Chunk(len(chunks), tuple(cur_p), context))
            if len(chunks) > MAX_CHUNKS:
                return chunks, True
            prev = pieces[k - 1][1]
            context = " ".join(segments[i].text for i in prev)[-CONTEXT_CHARS:]
            cur_p, size, count = [], len(context), 0
        cur_p.append((pn, idx))
        size += n
        count += len(idx)
    if cur_p:
        chunks.append(Chunk(len(chunks), tuple(cur_p), context))
    return chunks, len(chunks) > MAX_CHUNKS
