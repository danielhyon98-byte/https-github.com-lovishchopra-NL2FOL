"""Math spans of an agent's text, extracted in the order of section 4.2 of docs/STEM_DESIGN.md.

1. **Code**: fenced blocks (```` ``` ```` and ``~~~``, the language tag kept; an unclosed
   fence runs to the end), inline ``code``, and 4-space indented blocks in the Computer
   Science profile. Code is masked from maths and prose, never parsed for meaning and never
   run (ST-CODE-001 names it).
2. **LaTeX display**: ``$$…$$``, ``\\[…\\]`` and the environments ``equation``, ``align``,
   ``gather`` (starred or not). Rows are split at ``\\\\``; ``&`` is dropped by the parser;
   an inner ``aligned``/``split``/``gathered`` wrapper is read through.
3. **LaTeX inline**: ``$…$`` and ``\\(…\\)`` under the TeX rule: the content is non-empty,
   has no leading or trailing space, closes in the same paragraph, is not followed by a
   digit and is at most ``max_span_chars`` long. ``\\$`` and an unclosed ``$5 per kg`` are
   currency.
4. **Chemical equations** (chemistry profiles): an arrow with species on both sides.
5. **Math runs in prose**: a maximal run the lexer can tokenise that contains a relation
   sign. It starts at an identifier, a number, ``(``, ``|`` or a minus after a clean
   boundary (the start of the line, punctuation, a prose word), or at a relation sign right
   after a prose label (``Energy absorbed = 4 × 414 + …``: the label names the left side) or
   at the start of a line (a continuation). It stops before a prose word (three or more
   letters that are not a function name, a unit after a number, a Greek name or a name in
   scope, or a short English word such as ``is``, ``so``, ``or``), before sentence
   punctuation, a comma or semicolon outside brackets, a quotation mark or a bracket it did
   not open. A trailing operator or relation sign is left out. A run that opens with a bracket
   and holds its relation sign only inside it (``(x = 2)``, an aside ``(100.0 cm³ × 1.00 g cm⁻³
   = 100.0 g)``) is read again from inside the bracket, up to three brackets deep. A run with no
   relation sign that is a number with a unit is kept as a ``quantity`` (masked in the prose
   view, read as a prose value by the relations); an article before the number (``A 0.20 kg
   ball``) is a clean boundary. A prose label keeps a bond it names (``H–H bond energy``).
6. **Verbal arithmetic**: ``<number> (plus | minus | times | multiplied by | divided by)
   <number> … (equals | is equal to | gives) <number>``, numbers only, read as the same AST.
7. **Tables and data lines**: Markdown tables (a truth table is recognised from them later)
   and bracketed data, vector and list lines (``[1, 2]``, ``{2, 3}``) become text claims.

Markup is recorded for blanking in the math view: emphasis markers, heading lines, list
markers, block-quote marks and part labels at the start of a line (``(a)``, ``b)``,
``(b)(ii)``, ``Part (c)``, ``Question 2``), which are recorded as structure. So are the
furniture of a marked answer, as the generic branch reads it (``layout.py``): the rest of a
label-only line (``(a) [2]``, ``Part (a) — find — 3 marks``, ``3.``), which opens a part and
proposes no statement, and the mark annotations that close a line or one of its sentences
(``[1]``, ``[1 spare]``, ``M1`` or ``A1`` after two spaces, ``(M1)``), which are never read as
maths and never belong to a statement.

Every scan is linear: lines are visited once, ``$`` signs are paired through a precomputed
table, prose lines are lexed in windows of at most ``max_line_chars`` characters, and the
only regular expressions are anchored, bounded line-start patterns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from .chem import ELEMENTS, find_equations
from .lexer import COMPLETE_UNSUP, Token, lex
from .limits import DEFAULT_LIMITS, StemLimits, StemProfile
from .layout import annotation_ranges, label_only_rest, plain_line
from .normalize import blank_ranges, reading_view
from .parser import STEM_NAMES
from .units import compound_part, english_word_atom, is_unit_atom, prefixed_greek_unit, unit_group

__all__ = ["DISPLAY_ENVIRONMENTS", "Line", "PartLabel", "Span", "SpanSet", "find_spans", "split_lines"]

SpanKind = Literal["code_block", "code_inline", "latex_display", "latex_inline", "chem", "math_run", "verbal", "quantity", "table", "data_line"]
DISPLAY_ENVIRONMENTS = ("equation*", "equation", "align*", "align", "gather*", "gather")
_INNER_WRAPPERS = ("\\begin{aligned}", "\\end{aligned}", "\\begin{split}", "\\end{split}", "\\begin{gathered}", "\\end{gathered}")
_STOPWORDS = frozenset({"is", "so", "of", "to", "be", "in", "by", "or", "if", "an", "it", "on", "we", "do", "no", "up", "us", "my", "he", "me", "am", "go",
                        "the", "and", "for", "then", "than", "that", "this", "with", "from", "into", "when", "only", "also", "here", "there", "each",
                        "both", "some", "such", "what", "which", "will", "were", "have", "has", "had", "not", "but", "are", "was", "its", "one", "two",
                        "per", "all", "any", "can", "may", "our", "out", "own", "too", "via", "who", "why", "how", "yet", "nor", "let", "use", "using",
                        "take", "taking", "given", "where", "since", "thus", "hence", "gives"})
_ARTICLES = frozenset({"the", "a", "an", "of", "all", "some", "this", "that", "each"})
#: bracket depth up to which a relation inside brackets that open a run is read from inside them
_MAX_ASIDE_DEPTH = 3
_VERBAL_OPS = {"plus": "+", "minus": "-", "times": "×", "multiplied": "×", "divided": "/"}
#: the words of a stated quotient's remainder ('17 ÷ 5 = 3 remainder 2', '3 rem 2'; STEM repair 2)
_REMAINDER_WORDS = frozenset({"remainder", "rem"})
_VERBAL_EQ = ("equals", "gives", "makes")
_FENCE_RE = re.compile(r"[ ]{0,3}(`{3,}|~{3,})[ \t]*([^\n`]{0,40})")
_LIST_RE = re.compile(r"[ \t]{0,8}(?:[-*•–—]|\d{1,3}[.)])[ \t]+")
_HEADING_RE = re.compile(r"[ ]{0,3}#{1,6}[ \t]+")
_QUOTE_RE = re.compile(r"[ ]{0,3}>[ \t]?")
_PART_RE = re.compile(
    r"[ \t]*(?:\*\*)?(?:(?:Part|PART|part)[ \t]+\(?[a-hA-H]\)?(?:\([ivx]{1,4}\))?|(?:Question|Q)[ \t]?\d{1,2}(?:\([a-h]\))?|\([a-h]\)(?:\([ivx]{1,4}\))?|"
    r"[a-h]\)(?:\([ivx]{1,4}\))?|\([ivx]{1,4}\))(?:\*\*)?[ \t]*[:.]?(?:\*\*)?(?=[ \t]|$)")


@dataclass(frozen=True)
class Line:
    start: int
    end: int
    index: int


@dataclass(frozen=True)
class PartLabel:
    """A structural label: a heading or a part label at the start of a line."""

    text: str
    start: int
    end: int
    line: int
    heading: bool = False


@dataclass(frozen=True)
class Span:
    """One extracted span. ``start``/``end`` cover the delimiters; ``rows`` are the content
    ranges to read (one per display row, the inner text of an inline span, the run itself).
    ``lead`` marks a run that opens with a relation sign, ``label`` the prose label before it.
    ``error``/``code`` record a bound broken by the span (ST-LIM-001): the span stays text."""

    kind: SpanKind
    start: int
    end: int
    rows: tuple[tuple[int, int], ...] = ()
    mode: Literal["plain", "latex"] = "plain"
    lang: str = ""
    label: str = ""
    lead: bool = False
    error: str = ""
    code: str = ""
    line: int = -1
    tokens: tuple[Token, ...] = ()

    @property
    def is_math(self) -> bool:
        return self.kind in ("latex_display", "latex_inline", "math_run", "verbal")


@dataclass(frozen=True)
class SpanSet:
    spans: tuple[Span, ...]
    lines: tuple[Line, ...]
    part_labels: tuple[PartLabel, ...] = ()
    markup: tuple[tuple[int, int], ...] = ()
    list_markers: tuple[tuple[int, int], ...] = ()
    heading_lines: tuple[int, ...] = ()
    math_view: str = ""

    def of_kind(self, *kinds: str) -> tuple[Span, ...]:
        return tuple(s for s in self.spans if s.kind in kinds)


def split_lines(text: str) -> tuple[Line, ...]:
    out: list[Line] = []
    start = 0
    idx = 0
    n = len(text)
    while True:
        k = text.find("\n", start)
        if k < 0:
            out.append(Line(start, n, idx))
            break
        out.append(Line(start, k, idx))
        start = k + 1
        idx += 1
    return tuple(out)


# ----------------------------------------------------------------------------------------- code


def _code_spans(view: str, lines: tuple[Line, ...], profile: StemProfile) -> tuple[list[Span], "_Cover"]:
    spans: list[Span] = []
    covered = _Cover(len(view))
    i = 0
    nlines = len(lines)
    while i < nlines:
        ln = lines[i]
        m = _FENCE_RE.match(view, ln.start, ln.end)
        if m is not None and m.end() <= ln.end:
            fence = m.group(1)
            lang = (m.group(2) or "").strip().split(" ")[0][:40]
            j = i + 1
            close_line: Optional[Line] = None
            while j < nlines:
                cl = lines[j]
                text = view[cl.start:cl.end].strip()
                if text.startswith(fence[0] * len(fence)) and set(text) <= {fence[0]}:
                    close_line = cl
                    break
                j += 1
            end = close_line.end if close_line is not None else len(view)
            inner_start = ln.end + 1 if ln.end < len(view) else ln.end
            inner_end = close_line.start if close_line is not None else len(view)
            spans.append(Span("code_block", ln.start, end, rows=((min(inner_start, inner_end), inner_end),), lang=lang or "", line=i))
            covered.add(ln.start, end)
            i = (j + 1) if close_line is not None else nlines
            continue
        i += 1
    # indented code blocks (Computer Science only): lines indented by 4 spaces or a tab after a blank line
    if profile.computer_science:
        i = 0
        while i < nlines:
            ln = lines[i]
            text = view[ln.start:ln.end]
            prev_blank = i == 0 or not view[lines[i - 1].start:lines[i - 1].end].strip()
            if prev_blank and (text.startswith("    ") or text.startswith("\t")) and text.strip() and not _inside(ln.start, covered):
                j = i
                while j + 1 < nlines:
                    nt = view[lines[j + 1].start:lines[j + 1].end]
                    if (nt.startswith("    ") or nt.startswith("\t")) or not nt.strip():
                        j += 1
                    else:
                        break
                while j > i and not view[lines[j].start:lines[j].end].strip():
                    j -= 1
                spans.append(Span("code_block", ln.start, lines[j].end, rows=((ln.start, lines[j].end),), lang="indented", line=i))
                covered.add(ln.start, lines[j].end)
                i = j + 1
                continue
            i += 1
    # inline code: backtick runs paired on one line
    for ln in lines:
        k = ln.start
        while k < ln.end:
            k = view.find("`", k, ln.end)
            if k < 0:
                break
            if _inside(k, covered):
                k += 1
                continue
            run = 1
            while k + run < ln.end and view[k + run] == "`":
                run += 1
            close = view.find("`" * run, k + run, ln.end)
            if close < 0:
                k += run
                continue
            spans.append(Span("code_inline", k, close + run, rows=((k + run, close),), line=ln.index))
            covered.add(k, close + run)
            k = close + run
    return spans, covered


class _Cover:
    """Ranges already taken by a span, with a bitmap so a membership test is O(1) however many spans there are."""

    def __init__(self, n: int) -> None:
        self.mask = bytearray(n + 1)
        self.ranges: list[tuple[int, int]] = []

    def add(self, a: int, b: int) -> None:
        if b > a:
            self.mask[a:b] = b"\x01" * (b - a)
            self.ranges.append((a, b))

    def contains(self, pos: int) -> bool:
        return 0 <= pos < len(self.mask) and self.mask[pos] == 1

    def merged(self, other: "_Cover") -> "_Cover":
        out = _Cover(len(self.mask) - 1)
        for a, b in self.ranges + other.ranges:
            out.add(a, b)
        return out


def _inside(pos: int, cover: "_Cover") -> bool:
    return cover.contains(pos)


# ----------------------------------------------------------------------------------------- LaTeX


def _paragraph_breaks(view: str) -> list[int]:
    """Offsets of blank lines (a LaTeX span never crosses one)."""
    out = []
    k = 0
    while True:
        k = view.find("\n", k)
        if k < 0:
            break
        j = k + 1
        while j < len(view) and view[j] in " \t":
            j += 1
        if j < len(view) and view[j] == "\n":
            out.append(k)
        k += 1
    return out


def _crosses_break(a: int, b: int, breaks: list[int]) -> bool:
    """True when a paragraph break lies in [a, b) (binary search over the sorted breaks)."""
    lo, hi = 0, len(breaks)
    while lo < hi:
        mid = (lo + hi) // 2
        if breaks[mid] < a:
            lo = mid + 1
        else:
            hi = mid
    return lo < len(breaks) and breaks[lo] < b


def _rows(view: str, a: int, b: int) -> tuple[tuple[int, int], ...]:
    """Row content ranges of display content ``view[a:b]``: split at ``\\\\`` (an optional ``[2pt]``
    after it dropped), inner aligned/split wrappers removed, each row trimmed."""
    cuts: list[tuple[int, int]] = []
    k = a
    while k < b:
        hit = -1
        for w in _INNER_WRAPPERS:
            if view.startswith(w, k):
                hit = len(w)
                break
        if hit > 0:
            cuts.append((k, k + hit))
            k += hit
            continue
        if view.startswith("\\\\", k):
            e = k + 2
            if e < b and view[e] == "[":
                close = view.find("]", e, min(b, e + 12))
                if close > 0:
                    e = close + 1
            cuts.append((k, e))
            k = e
            continue
        if view[k] == "\\" and k + 1 < b:
            k += 2
            continue
        k += 1
    rows: list[tuple[int, int]] = []
    pos = a
    for c0, c1 in cuts + [(b, b)]:
        s, e = pos, c0
        while s < e and view[s] in " \t\n":
            s += 1
        while e > s and view[e - 1] in " \t\n":
            e -= 1
        if e > s:
            rows.append((s, e))
        pos = c1
    return tuple(rows)


def _latex_spans(view: str, masked: str, limits: StemLimits) -> tuple[list[Span], "_Cover"]:
    spans: list[Span] = []
    covered = _Cover(len(view))
    breaks = _paragraph_breaks(masked)
    n = len(masked)
    # display: \begin{env} ... \end{env}
    for env in DISPLAY_ENVIRONMENTS:
        opener, closer = "\\begin{" + env + "}", "\\end{" + env + "}"
        k = 0
        while True:
            k = masked.find(opener, k)
            if k < 0:
                break
            if _inside(k, covered):
                k += len(opener)
                continue
            close = masked.find(closer, k + len(opener))
            if close < 0:
                k += len(opener)
                continue
            a, b = k + len(opener), close
            spans.append(_display(view, k, close + len(closer), a, b, env, limits))
            covered.add(k, close + len(closer))
            k = close + len(closer)
    # display: $$...$$ and \[...\]
    for opener, closer, lang in (("$$", "$$", "$$"), ("\\[", "\\]", "\\[")):
        k = 0
        while True:
            k = masked.find(opener, k)
            if k < 0:
                break
            if _inside(k, covered) or (opener == "$$" and k > 0 and masked[k - 1] == "\\"):
                k += len(opener)
                continue
            close = masked.find(closer, k + len(opener))
            if close < 0 or _crosses_break(k, close, breaks):
                k += len(opener)
                continue
            spans.append(_display(view, k, close + len(closer), k + len(opener), close, lang, limits))
            covered.add(k, close + len(closer))
            k = close + len(closer)
    # inline: \( ... \)
    k = 0
    while True:
        k = masked.find("\\(", k)
        if k < 0:
            break
        if _inside(k, covered):
            k += 2
            continue
        close = masked.find("\\)", k + 2)
        if close < 0 or _crosses_break(k, close, breaks) or close - (k + 2) > limits.max_span_chars or close == k + 2:
            k += 2
            continue
        spans.append(Span("latex_inline", k, close + 2, rows=((k + 2, close),), mode="latex", lang="\\("))
        covered.add(k, close + 2)
        k = close + 2
    # inline: $ ... $ with the TeX rule; dollars are paired through a table of their positions
    dollars = [i for i in range(n) if masked[i] == "$" and not (i > 0 and masked[i - 1] == "\\") and not _inside(i, covered)]
    dollars = [d for d in dollars if not ((d + 1 < n and masked[d + 1] == "$") or (d > 0 and masked[d - 1] == "$"))]
    idx = 0
    while idx < len(dollars):
        a = dollars[idx]
        if a + 1 >= n or masked[a + 1] in " \t\n":
            idx += 1
            continue
        if idx + 1 >= len(dollars):
            break
        b = dollars[idx + 1]
        content_ok = b > a + 1 and masked[b - 1] not in " \t\n" and not (b + 1 < n and masked[b + 1].isdigit()) and not _crosses_break(a, b, breaks) \
            and b - (a + 1) <= limits.max_span_chars
        if content_ok:
            spans.append(Span("latex_inline", a, b + 1, rows=((a + 1, b),), mode="latex", lang="$"))
            covered.add(a, b + 1)
            idx += 2
        else:
            idx += 1
    return spans, covered


def _display(view: str, start: int, end: int, a: int, b: int, lang: str, limits: StemLimits) -> Span:
    if b - a > limits.max_span_chars:
        return Span("latex_display", start, end, rows=((a, b),), mode="latex", lang=lang,
                    error=f"a display of {b - a} characters exceeds the span bound of {limits.max_span_chars}", code="ST-LIM-001")
    return Span("latex_display", start, end, rows=_rows(view, a, b), mode="latex", lang=lang)


# ----------------------------------------------------------------------------------------- markup


def _markup(view: str, lines: tuple[Line, ...], covered: "_Cover") -> tuple[list[tuple[int, int]], list[PartLabel], list[tuple[int, int]], list[int]]:
    markup: list[tuple[int, int]] = []
    parts: list[PartLabel] = []
    list_markers: list[tuple[int, int]] = []
    headings: list[int] = []
    for ln in lines:
        if ln.end <= ln.start:
            continue
        if _inside(ln.start, covered):
            # a line that opens inside code or maths ('$= 4787.58\\ldots$ (A1)'): only its closing mark annotations are furniture
            markup.extend(_furniture(view, ln, markup, covered, annotations_only=True))
            continue
        pos = ln.start
        m = _HEADING_RE.match(view, pos, ln.end)
        if m is not None:
            text = view[m.end():ln.end].strip()
            parts.append(PartLabel(text=text[:120], start=ln.start, end=ln.end, line=ln.index, heading=True))
            markup.append((ln.start, ln.end))
            headings.append(ln.index)
            continue
        m = _QUOTE_RE.match(view, pos, ln.end)
        if m is not None and m.end() > pos:
            markup.append((pos, m.end()))
            pos = m.end()
        m = _LIST_RE.match(view, pos, ln.end)
        if m is not None and m.end() < ln.end and not _list_is_math(view, m.end(), ln.end, view[m.start():m.end()]):
            markup.append((m.start(), m.end()))
            list_markers.append((m.start(), m.end()))
            pos = m.end()
        m = _PART_RE.match(view, pos, ln.end)
        if m is not None and m.end() > pos:
            label = view[pos:m.end()].strip().strip("*").strip().rstrip(":.").strip()
            parts.append(PartLabel(text=label, start=pos + (len(view[pos:m.end()]) - len(view[pos:m.end()].lstrip())), end=m.end(), line=ln.index))
            markup.append((pos, m.end()))
            pos = m.end()
        # emphasis markers: ** and __ pairs, and single * pairs around words
        for marker in ("**", "__", "*"):
            k = pos
            while k < ln.end:
                k = view.find(marker, k, ln.end)
                if k < 0:
                    break
                if marker == "*" and (view.startswith("**", k) or (k > 0 and view[k - 1] == "*")):
                    k += 1
                    continue
                before_ok = k == ln.start or view[k - 1] in " \t([\"'“‘" or (k - 1, k) in markup
                after = k + len(marker)
                if not before_ok or after >= ln.end or view[after] in " \t":
                    k = after
                    continue
                close = view.find(marker, after, ln.end)
                while close > 0 and marker == "*" and (view.startswith("**", close) or view[close - 1] == "*"):
                    close = view.find(marker, close + 2, ln.end)
                if close < 0 or view[close - 1] in " \t":
                    k = after
                    continue
                tail = close + len(marker)
                if tail < ln.end and (view[tail].isalnum()):
                    k = after
                    continue
                markup.append((k, after))
                markup.append((close, tail))
                k = tail
        markup.extend(_furniture(view, ln, markup, covered))
    return markup, parts, list_markers, headings


def _furniture(view: str, ln: Line, markup: list[tuple[int, int]], covered: "_Cover", annotations_only: bool = False) -> list[tuple[int, int]]:
    """The rest of a label-only line and the mark annotations of one line (``layout.py``), as offsets of ``view``. The
    line is read as the generic branch reads it: with its emphasis markers removed (``**Part (a) — find — 3 marks**``)."""
    line, rel = plain_line(view[ln.start:ln.end])
    if not line.strip():
        return []
    index = [ln.start + k for k in rel]
    out: list[tuple[int, int]] = []
    if not annotations_only and label_only_rest(line) is not None:
        # the whole line is furniture: the label (also recorded as structure when it is one) and its mark allocation
        first = len(line) - len(line.lstrip())
        out.append((index[first], ln.end))
        return out
    for pa, pb in annotation_ranges(line):
        if pb <= pa:
            continue
        a, b = index[pa], index[pb - 1] + 1
        if not _inside(a, covered) and not _inside(b - 1, covered):
            out.append((a, b))
    return out


def _list_is_math(view: str, a: int, b: int, marker: str) -> bool:
    """A leading ``- 2 = x``? A minus followed by a number and a relation is maths, not a list marker."""
    m = marker.strip()
    if m not in ("-", "–", "—"):
        return False
    rest = view[a:b].lstrip()
    return bool(rest) and (rest[0].isdigit()) and ("=" in rest[:40])


# ----------------------------------------------------------------------------------------- math runs


@dataclass
class _Run:
    first: int
    last: int  # exclusive token index
    lead: bool = False
    label: str = ""
    has_rel: bool = False
    quantity: bool = False


def _modulus_at(toks: tuple[Token, ...], k: int) -> bool:
    """``(mod 5)`` at token ``k``: the modulus of a congruence written after it."""
    return (k + 3 < len(toks) and toks[k].kind == "LPAR" and toks[k].text == "(" and toks[k + 1].kind == "IDENT" and toks[k + 1].text.lower() in ("mod", "modulo")
            and toks[k + 2].kind == "NUM" and toks[k + 3].kind == "RPAR" and toks[k + 3].text == ")")


def _is_d_variable(w: str) -> bool:
    return len(w) == 2 and w[0] == "d" and w[1].isalpha()


class _RunFinder:
    def __init__(self, toks: tuple[Token, ...], view: str, names: frozenset[str], profile: StemProfile) -> None:
        self.t = toks
        self.view = view
        self.names = names
        self.profile = profile
        # bracket matching in one pass: a run never scans through a bracket that does not close (linear on any nesting)
        self.match = [-1] * len(toks)
        stack: list[int] = []
        pairs = {"(": ")", "[": "]", "{": "}"}
        for k, t in enumerate(toks):
            if t.kind in ("LPAR", "LGROUP"):
                stack.append(k)
            elif t.kind in ("RPAR", "RGROUP"):
                while stack and pairs.get(toks[stack[-1]].text, "}") != t.text and toks[stack[-1]].kind != "LGROUP":
                    stack.pop()
                if stack:
                    o = stack.pop()
                    self.match[o] = k
                    self.match[k] = o
        self.scanned = 0
        #: the shallowest bracket depth of a relation sign in the last extended run (0: none inside brackets)
        self.inner_rel = 0

    def mathy_start(self, t: Token) -> bool:
        if t.kind != "IDENT":
            return False
        w = t.text
        if t.delta or t.sub or t.primes:
            return True
        if not w.isascii():
            return True
        if len(w) == 1:
            return True
        if w in self.names or w in STEM_NAMES or _is_d_variable(w):
            return True
        if w.isupper() and 2 <= len(w) <= 4:
            return True
        return False

    def mathy_start_at(self, k: int) -> bool:
        """``mathy_start``, and a short run of two or three letters right before a relation sign
        (``pV = nRT``, ``KE = ½mv²``) that is no English word."""
        t = self.t[k]
        prev = self.t[k - 1] if k > 0 else None
        if prev is not None and prev.kind == "IDENT" and prev.text.lower() in _ARTICLES and len(t.text) > 1 and not t.sub and not t.delta:
            return False  # 'the Al', 'of NaOH': a noun after an article
        if self.mathy_start(t):
            return True
        nxt = self.t[k + 1] if k + 1 < len(self.t) else None
        return (t.kind == "IDENT" and 2 <= len(t.text) <= 3 and t.text.isascii() and t.text.isalpha() and t.text.lower() not in _STOPWORDS
                and nxt is not None and nxt.kind == "REL" and nxt.text in ("=", "≈"))

    def is_bond(self, k: int) -> bool:
        """``O=O``, ``C–H``, ``N≡N`` in a chemistry profile: a bond sign glued between two element symbols."""
        if not self.profile.chemistry or k == 0 or k + 1 >= len(self.t):
            return False
        t = self.t[k]
        if t.space or not ((t.kind == "REL" and t.text in ("=", "≡")) or (t.kind == "OTHER" and t.text in "–—") or (t.kind == "OP" and t.text == "-")):
            return False
        a, b = self.t[k - 1], self.t[k + 1]
        return a.kind == "IDENT" and b.kind == "IDENT" and not b.space and a.text in ELEMENTS and b.text in ELEMENTS and not a.sub and not b.sub

    def mathy_operand(self, k: int) -> bool:
        t = self.t[k]
        if self.mathy_start(t):
            return True
        w = t.text
        if w in ("at", "as"):
            return True
        if w.lower() in _STOPWORDS:
            return False
        if len(w) <= 4 and w.isalpha() and w.isascii():
            return True
        nxt = self.t[k + 1] if k + 1 < len(self.t) else None
        if w.islower() and w.isascii() and nxt is not None and ((nxt.kind == "OP" and nxt.text in ("×", "/", "÷", "·", "*", "+", "-")) or nxt.kind == "REL"):
            return True  # a word symbol between operators: '= actual / theoretical × 100'
        prev = self.t[k - 1] if k > 0 else None
        if w.islower() and w.isascii() and nxt is not None and nxt.kind == "RPAR" and prev is not None \
                and prev.kind == "OP" and prev.text in ("×", "/", "÷", "·", "*", "+", "-"):
            return True  # a word symbol closing a bracketed word formula: '(final − initial) ÷ initial × 100'
        return False

    def unit_here(self, k: int) -> bool:
        t = self.t[k]
        if t.kind == "DEGREE" and t.text in ("°C", "°F"):
            return True
        if t.kind != "IDENT" or t.sub or t.delta or t.primes:
            return False
        nxt = self.t[k + 1] if k + 1 < len(self.t) else None
        after = self.t[k + 2] if k + 2 < len(self.t) else None
        if nxt is not None and nxt.kind == "PUNCT" and nxt.text == "." and not nxt.space and after is not None and after.kind == "IDENT" and not after.space:
            return False  # an abbreviation such as 's.f.'
        if t.space and english_word_atom(t.text):
            return False  # '5 at D', 'x = 5 as before': an English word, never an atto-prefixed unit
        if is_unit_atom(t.text, bare_m=self.profile.bare_m, tonne=self.profile.tonne):
            return True
        if t.text in ("μ", "µ") and k + 1 < len(self.t) and self.t[k + 1].kind == "IDENT" and not self.t[k + 1].space:
            return True
        if self.greek_prefixed(k):
            return True  # 'kΩ', 'MΩ', 'mΩ': a Latin prefix glued to a Greek unit symbol
        return False

    def greek_prefixed(self, k: int) -> bool:
        """Tokens ``k`` and ``k + 1`` are a Latin SI prefix and a Greek unit symbol written together (``k`` + ``Ω``)."""
        if k + 1 >= len(self.t):
            return False
        a, b = self.t[k], self.t[k + 1]
        return (a.kind == "IDENT" and b.kind == "IDENT" and not b.space and not (a.sub or a.delta or a.primes or b.sub or b.delta or b.primes)
                and prefixed_greek_unit(a.text, b.text))

    def clean_before(self, k: int, rel_start: bool) -> bool:
        if k == 0:
            return True
        p = self.t[k - 1]
        if p.kind in ("PUNCT", "COMMA", "SEMI", "COLON", "QUOTE", "OTHER", "ERROR", "BANG"):
            return True
        if p.kind == "IDENT":
            if self.t[k].kind == "NUM" and self.t[k].space and p.text.lower() in _ARTICLES:
                return True  # 'A 100.0 cm³ sample': an article before a number
            if rel_start and k >= 2 and self.t[k - 2].kind == "IDENT" and self.t[k - 2].text.lower() in _ARTICLES and len(p.text) > 1 \
                    and not (p.sub or p.delta or p.primes):
                return True  # 'Cl₂ needed for all the Al = 0.20 × 3/2 = 0.30 mol': a noun after an article ends the label (STEM repair 2)
            if not rel_start and self.profile.chemistry and self.t[k].kind == "NUM" and self.t[k].space and p.text in ELEMENTS and not p.sub \
                    and k + 1 < len(self.t) and self.t[k + 1].kind in ("REL", "OP"):
                return True  # an atom tally 'C 3 = 3; H 8 = 4 × 2 = 8': the element names the count (STEM repair 2)
            if not rel_start and self.t[k].kind == "NUM" and self.t[k].space and len(p.text) >= 2 and p.text.isalpha() and not (p.sub or p.delta or p.primes) \
                    and k + 1 < len(self.t) and self.t[k + 1].space and self.unit_here(k + 1):
                return True  # 'a battery of emf 12 V': a quantity named by the word before it, never a product of the name and the quantity
            return not self.mathy_start(p) or p.text.lower() in _STOPWORDS or (rel_start and len(p.text) >= 3)
        if p.kind == "LPAR" and p.text == "(":
            return not rel_start
        if p.kind == "RPAR" and rel_start:
            return True
        if rel_start and p.kind in ("SUP", "SUB") and k >= 2 and self.t[k - 2].kind == "IDENT" and len(self.t[k - 2].text) >= 3 \
                and not self.mathy_start(self.t[k - 2]):
            return True  # a word formula 'BMI = mass/height² = 72/1.80² = …': the prose word ends the label
        if rel_start and p.kind == "PERCENT" and k + 1 < len(self.t) and self.t[k + 1].kind == "NUM":
            return True  # 'useful output/total input × 100% = 600 J / 800 J × 100% = 75%': the word formula is the label
        return False

    def can_start(self, k: int) -> bool:
        t = self.t[k]
        if t.kind == "REL":
            if t.text in ("⇒", "∴") or not self.clean_before(k, True):
                return False
            return True
        if not self.clean_before(k, False):
            return False
        if t.kind in ("NUM", "NUMERR", "FUNC", "UNSUP", "BAR"):
            return True
        if t.kind == "LPAR" and t.text in "([":
            return True
        if t.kind == "OP" and t.text in ("-", "+", "±") and k + 1 < len(self.t) and self.t[k + 1].kind in ("NUM", "IDENT", "LPAR", "FUNC"):
            if not t.space and k > 0 and self.t[k - 1].kind == "IDENT":
                return False  # a hyphen ('helium-4', 'x-axis'), not a minus
            return True
        if t.kind == "IDENT":
            return self.mathy_start_at(k) and t.text.lower() not in _STOPWORDS
        if t.kind == "BOOL" and t.text == "¬":
            return True
        return False

    def extend(self, i: int) -> tuple[int, bool]:
        toks = self.t
        n = len(toks)
        k = i
        stack: list[str] = []
        operand = True  # expecting an operand
        last_good = i
        has_rel_at: list[int] = []
        in_unit = False
        prev_value = False  # the last completed operand ends in a number (a unit may follow)
        inner = 0
        if toks[i].kind == "REL":
            operand = True
            k = i + 1
            has_rel_at.append(i)
        while k < n:
            t = toks[k]
            kind = t.kind
            if kind in ("LPAR", "LGROUP") and self.match[k] < 0:
                break  # a bracket that never closes ends the run
            if not operand and self.is_bond(k):
                k += 2  # the bond sign and the second element: O=O is one symbol
                if not stack:
                    last_good = k
                continue
            if kind in ("QUOTE", "PUNCT") or (kind in ("OTHER",) and t.text not in ("½",)) or (kind == "ERROR" and t.space):
                break
            if kind in ("COMMA", "SEMI") and not stack:
                break
            if kind == "COLON":
                if not t.space and k + 1 < n and toks[k + 1].space:
                    break  # 'Step 1: 1.0 × 2.0 = 2.0': a colon glued to the figure and followed by a space ends a label, not a ratio
                if not operand and prev_value and k + 1 < n and toks[k + 1].kind == "NUM":
                    k += 1
                    operand = True
                    continue
                break
            if operand:
                if k > i and toks[k - 1].kind == "CARET" and not t.space and any(x.kind == "UNSUP" for x in toks[max(i, k - 4):k]):
                    # STEM repair 10: an integral's upper limit written after a caret ('∫_0^1 x dx', '∫_{0}^{1} x dx', '∫_{-2}^{-1}'): part of
                    # the limits, the operand still to come; it had been read as the operand (or a group ended the run), so the relation was
                    # silently left unread
                    j = k
                    braced = kind in ("LGROUP", "LPAR") and t.text == "{"
                    close = self.match[k] if braced else -1
                    if braced and close > k:
                        j = k + 1
                    if j < n and toks[j].kind == "OP" and toks[j].text in ("-", "−") and j + 1 < n and toks[j + 1].kind == "NUM":
                        j += 1
                    if j < n and toks[j].kind == "NUM" and (not braced or j + 1 == close):
                        k = (close if braced else j) + 1
                        continue
                if kind == "IDENT":
                    if not self.mathy_operand(k) and not (k > i and toks[k - 1].kind == "LPAR" and not toks[k - 1].space and k + 1 < n
                                                        and toks[k + 1].kind == "RPAR" and t.text.isalpha()):
                        break
                    operand, prev_value, in_unit = False, False, False
                elif kind in ("NUM", "NUMERR"):
                    operand, prev_value, in_unit = False, True, False
                elif kind == "OP" and t.text in ("-", "+", "±", "∓"):
                    pass
                elif kind == "LPAR" or kind == "LGROUP":
                    stack.append(t.text)
                elif kind == "BAR":
                    stack.append("|")
                elif kind in ("FUNC",):
                    pass
                elif kind == "UNSUP" and t.value in COMPLETE_UNSUP:
                    operand, prev_value, in_unit = False, False, False  # a whole combination or permutation count ('⁵C₂'): an operand
                elif kind == "UNSUP":
                    pass  # ∫, Σ, lim: an operator in front of its operand (the parser names it unsupported)
                elif kind in ("SUB", "SUP", "CARET") and k > i and toks[k - 1].kind in ("UNSUP", "SUB", "SUP", "CARET", "NUM") and not t.space \
                        and any(x.kind == "UNSUP" for x in toks[max(i, k - 4):k]):
                    pass  # the limits of an integral or a sum: ∫₁³, \sum_{i=1}^{n}
                elif kind == "INF":
                    operand, prev_value = False, False
                elif kind == "BOOL" and t.text == "¬":
                    pass
                elif kind == "ERROR":
                    operand = False
                else:
                    break
            else:
                if kind == "REL":
                    operand, in_unit = True, False
                    if not stack:
                        has_rel_at.append(k)
                    else:
                        inner = len(stack) if not inner else min(inner, len(stack))
                elif kind == "OP":
                    if t.text == "/" and in_unit and not t.space and k + 1 < n and toks[k + 1].kind == "LPAR" and not toks[k + 1].space:
                        c = self.match[k + 1]
                        if c > k + 2 and unit_group(toks, k + 2, c, self.profile):
                            k = c + 1  # a parenthesised unit denominator: 'J/(g K)', 'kJ/(m^2 yr)'
                            if not stack:
                                last_good = k
                            continue
                    if t.text == "×" and prev_value and (k + 1 >= n or toks[k + 1].kind in ("PUNCT", "COMMA", "SEMI", "QUOTE")
                                                         or (not t.space and toks[k + 1].space and toks[k + 1].kind == "IDENT")):
                        # a magnification suffix '50×' ('… = 50×.', 'is 50× larger'): written right after its number. A '×' with a space
                        # before it and a symbol after it is a product ('E = 0.5 × k × 0.04', STEM repair 5: it had been read as '0.5×')
                        k += 1
                        if not stack:
                            last_good = k
                        continue
                    operand, in_unit = True, False
                elif kind in ("CARET", "DSTAR"):
                    operand = True
                elif kind in ("SUP", "SUB") and not t.space:
                    pass
                elif kind in ("PERCENT", "DEGREE") or (kind in ("PRIME", "BANG") and not t.space):
                    if kind == "DEGREE" and t.text in ("°C", "°F"):
                        in_unit = True
                elif kind == "NUM" and not t.space and len(t.text) == 1 and "2" <= t.text <= "9" and toks[k - 1].kind == "IDENT" \
                        and len(toks[k - 1].text) >= 2 and not toks[k - 1].sub and self.unit_here(k - 1) \
                        and (in_unit or (k >= 2 and toks[k - 2].kind == "OP" and toks[k - 2].text == "/")):
                    in_unit = True  # an ASCII power glued to a unit atom: '25 cm3', 'mol/dm3' (the parser reads it as the atom's power)
                elif kind in ("RPAR", "RGROUP"):
                    if not stack:
                        break
                    stack.pop()
                    prev_value = True
                elif kind == "BAR":
                    if stack and stack[-1] == "|":
                        stack.pop()
                    else:
                        break
                elif kind == "IDENT":
                    if prev_value and not in_unit and has_rel_at and not stack and t.space and t.text in _REMAINDER_WORDS and k + 1 < n \
                            and toks[k + 1].kind == "NUM" and toks[k + 1].space:
                        k += 2  # '17 ÷ 5 = 3 remainder 2': the stated quotient and its remainder (STEM repair 2)
                        last_good = k
                        continue
                    if (prev_value or in_unit) and t.space and self.unit_here(k):
                        in_unit = True
                    elif in_unit and t.space and t.text.lower() == "per" and k + 1 < n and toks[k + 1].space and self.unit_here(k + 1):
                        pass  # 'mm³ per g per hour', 'counts per minute': the unit goes on after 'per' (STEM repair 3: the run had ended there)
                    elif in_unit and len(t.text) >= 2 and k + 1 < n and not toks[k + 1].space and toks[k + 1].kind in ("SUP", "CARET"):
                        in_unit = True  # an unknown unit atom with an exponent: 'yr⁻¹'
                    elif in_unit and not t.space and toks[k - 1].kind == "IDENT" and toks[k - 1].text in ("μ", "µ"):
                        pass
                    elif not t.space and self.greek_prefixed(k - 1):
                        in_unit = True  # the Ω of 'kΩ' (the prefix opened the unit, or was glued to the number: '2.2kΩ')
                    elif in_unit and self.profile.chemistry and t.text[:1].isupper() and (t.sub or len(t.text) >= 2):
                        break  # a formula after a quantity ('1 mol CaCO₃') names what is counted
                    elif not t.space:
                        if len(t.text) > 4 and t.text.isascii() and t.text not in self.names:
                            break
                        in_unit = False
                    elif t.delta or t.sub or not t.text.isascii() or t.text in self.names or t.text in STEM_NAMES or _is_d_variable(t.text):
                        if t.text.lower() in _STOPWORDS:
                            break
                        in_unit = False
                    elif len(t.text) == 1 and k + 1 < n and not toks[k + 1].space and toks[k + 1].kind in ("CARET", "SUP") and not self.unit_here(k):
                        in_unit = False  # a power after a value: '1600 e^(−8k)', 'C0 e^(−kt)', '3 x²' (a factor, not a unit)
                    else:
                        break
                elif kind == "NUM" and in_unit and t.space and compound_part(toks, k):
                    # stem-precision-5 (round 7): the next part of a compound quantity ('4 min 30 s', '1 kg 250 g'): the run goes on (it had
                    # been cut there, and only the last part was read)
                    prev_value, in_unit = True, False
                elif kind in ("FUNC", "LATEX"):
                    operand = True
                elif kind == "LPAR":
                    if not stack and prev_value and any(toks[r].text == "≡" for r in has_rel_at) and _modulus_at(toks, k):
                        k += 4  # '17 ≡ 2 (mod 5)': the modulus of a congruence (STEM repair 2)
                        last_good = k
                        continue
                    if t.space and in_unit:
                        break  # an aside after a quantity: 'm = 100.0 g (100.0 cm³ × 1.00 g cm⁻³)'
                    stack.append(t.text)
                    operand = True
                elif kind in ("UNSUP", "INF"):
                    pass
                elif kind == "BOOL":
                    operand = True
                else:
                    break
            k += 1
            if not operand and not stack:
                last_good = k
        self.scanned = k
        self.inner_rel = inner
        has_rel = any(r < last_good for r in has_rel_at)
        return last_good, has_rel

    def runs(self) -> list[_Run]:
        out: list[_Run] = []
        n = len(self.t)
        i = 0
        match = self.match
        toks = self.t
        while i < n:
            if match[i] < 0 and toks[i].kind in ("LPAR", "LGROUP"):
                i += 1  # a bracket that never closes: ``extend`` would stop on it at once
                continue
            if not self.can_start(i):
                i += 1
                continue
            end, has_rel = self.extend(i)
            if end <= i:
                # no run starts here; a start inside the scanned stretch meets the same stop (prefix operators, an open bracket)
                i = max(i + 1, min(self.scanned, n))
                continue
            if not has_rel and self.t[i].kind == "LPAR" and 1 <= self.inner_rel <= _MAX_ASIDE_DEPTH:
                i += 1  # a bracketed relation ('(x = 2)', an aside): read again from inside the bracket (bounded depth: linear)
                continue
            if not has_rel and 1 <= self.inner_rel <= _MAX_ASIDE_DEPTH:
                inner = next((x for x in range(i + 1, end) if toks[x].kind == "LPAR" and match[x] > x
                              and any(toks[y].kind == "REL" for y in range(x + 1, match[x]))), None)
                if inner is not None:
                    # a run whose relation sign is only inside a bracket after its start ('greatest at C (2.0 km = 200 m)'): the
                    # bracket is an aside, read from inside it like a run that opens with one (STEM repair 2: it was skipped)
                    i = inner + 1
                    continue
            run = _Run(i, end, lead=self.t[i].kind == "REL", has_rel=has_rel)
            if has_rel:
                if run.lead:
                    run.label = self._label(i)
                out.append(run)
            elif self._is_quantity(i, end):
                run.quantity = True
                out.append(run)
            i = end
        return out

    def _is_quantity(self, i: int, end: int) -> bool:
        toks = self.t[i:end]
        if not toks:
            return False
        j = 0
        if toks[0].kind == "OP" and toks[0].text in ("-", "+"):
            j = 1
        if j >= len(toks) or toks[j].kind != "NUM":
            return False
        rest = toks[j + 1:]
        return bool(rest) and any(x.kind in ("IDENT", "DEGREE", "PERCENT") for x in rest) and all(
            x.kind in ("IDENT", "SUP", "CARET", "OP", "DEGREE", "NUM", "PERCENT") for x in rest) and (rest[0].kind in ("DEGREE", "PERCENT") or self.unit_here(i + j + 1))

    def _label(self, i: int) -> str:
        """The prose label right before a run that opens with a relation sign: up to six words
        (and a bracketed group) back to punctuation, a number or an operator."""
        k = i - 1
        words = 0
        depth = 0
        start_tok = None
        while k >= 0:
            t = self.t[k]
            if t.kind == "RPAR":
                depth += 1
            elif t.kind == "LPAR":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and t.kind == "IDENT":
                words += 1
                if words > 6:
                    break
            elif depth == 0 and self.is_bond(k):
                pass  # 'H–H bond energy = …': the bond belongs to the label
            elif depth == 0:
                break
            start_tok = t
            k -= 1
        if start_tok is None:
            return ""
        return " ".join(self.view[start_tok.start:self.t[i].start].split())[:120]


def _verbal(toks: tuple[Token, ...]) -> list[tuple[int, int, tuple[Token, ...]]]:
    """Verbal arithmetic: numbers joined by plus/minus/times/multiplied by/divided by, then
    equals/is equal to/gives and a number. Returns ``(first, last, synthetic tokens)``."""
    out: list[tuple[int, int, tuple[Token, ...]]] = []
    n = len(toks)
    i = 0
    while i < n:
        if toks[i].kind != "NUM":
            i += 1
            continue
        synth: list[Token] = [toks[i]]
        k = i + 1
        ops = 0
        done = False
        while k < n:
            t = toks[k]
            w = t.text.lower() if t.kind == "IDENT" else ""
            if w in _VERBAL_OPS:
                step = 1
                if w in ("multiplied", "divided"):
                    if k + 1 < n and toks[k + 1].kind == "IDENT" and toks[k + 1].text.lower() == "by":
                        step = 2
                    else:
                        break
                if k + step < n and toks[k + step].kind == "NUM":
                    synth.append(Token("OP", _VERBAL_OPS[w], t.start, toks[k + step - 1].end, True))
                    synth.append(toks[k + step])
                    ops += 1
                    k += step + 1
                    continue
                break
            eq_step = 0
            if w in _VERBAL_EQ:
                eq_step = 1
            elif w == "is" and k + 2 < n and toks[k + 1].text.lower() == "equal" and toks[k + 2].text.lower() == "to":
                eq_step = 3
            elif t.kind == "REL" and t.text == "=":
                eq_step = 1
            if eq_step and ops and k + eq_step < n and toks[k + eq_step].kind == "NUM":
                synth.append(Token("REL", "=", t.start, toks[k + eq_step - 1].end, True))
                synth.append(toks[k + eq_step])
                out.append((i, k + eq_step + 1, tuple(synth)))
                i = k + eq_step + 1
                done = True
            break
        if not done:
            i += 1
    return out


# ----------------------------------------------------------------------------------------- tables and data lines


def _tables_and_data(view: str, lines: tuple[Line, ...], covered: "_Cover") -> list[Span]:
    out: list[Span] = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        text = view[ln.start:ln.end].strip()
        if _inside(ln.start, covered) or not text:
            i += 1
            continue
        if text.startswith("|") and text.count("|") >= 2:
            j = i
            while j + 1 < n and view[lines[j + 1].start:lines[j + 1].end].strip().startswith("|") and not _inside(lines[j + 1].start, covered):
                j += 1
            block = [view[lines[k].start:lines[k].end].strip() for k in range(i, j + 1)]
            if any(t.endswith("|") or t.count("|") >= 3 for t in block):
                out.append(Span("table", lines[i].start, lines[j].end, rows=tuple((lines[k].start, lines[k].end) for k in range(i, j + 1)), line=i))
                i = j + 1
                continue
            # stem-soundness-12 (round 7): a line opening with an absolute value ('|x − 1| < 3, so …') is maths, not a pipe table: no row
            # of it ends with a bar or has three, so the relations on it were read as table cells and named nowhere
        if text[0] in "[{" and text[-1] in "]}" and "," in text and _data_like(text):
            a = ln.start + (len(view[ln.start:ln.end]) - len(view[ln.start:ln.end].lstrip()))
            out.append(Span("data_line", a, a + len(text), rows=((a, a + len(text)),), line=i))
        i += 1
    return out


def _data_like(text: str) -> bool:
    letters = sum(1 for c in text if c.isalpha())
    return letters <= max(2, len(text) // 4)


# ----------------------------------------------------------------------------------------- assembly


def find_spans(text: str, reading: Optional[str] = None, *, profile: StemProfile, limits: StemLimits = DEFAULT_LIMITS,
               names: frozenset[str] = frozenset()) -> SpanSet:
    """Extract every span of ``text`` (see the module docstring). ``reading`` is the reading view
    (computed when omitted); ``names`` are the names in scope from the document's pre-pass."""
    view = reading if reading is not None else reading_view(text)
    lines = split_lines(view)
    spans, code_cov = _code_spans(view, lines, profile)
    masked = blank_ranges(view, code_cov.ranges)
    latex, latex_cov = _latex_spans(view, masked, limits)
    spans.extend(latex)
    covered = code_cov.merged(latex_cov)
    markup, parts, list_markers, headings = _markup(view, lines, covered)
    math_view = blank_ranges(view, code_cov.ranges + markup)
    scan = blank_ranges(math_view, latex_cov.ranges + [(lines[h].start, lines[h].end) for h in headings])
    # chemical equations
    chem_cov: list[tuple[int, int]] = []
    if profile.chemistry:
        for ln in lines:
            seg = scan[ln.start:ln.end]
            if not any(a in seg for a in ("→", "⇌", "->", "⟶", "<=>", "⇄")):
                continue
            for eq in find_equations(seg, ln.start, limits=limits):
                spans.append(Span("chem", eq.start, eq.end, rows=((eq.start, eq.end),), line=ln.index, error=eq.error, code=eq.code))
                chem_cov.append((eq.start, eq.end))
        scan = blank_ranges(scan, chem_cov)
    # tables and data lines
    tables = _tables_and_data(scan, lines, _Cover(len(scan)))
    spans.extend(tables)
    table_cov = [(s.start, s.end) for s in tables]
    scan = blank_ranges(scan, table_cov)
    # math runs, quantities and verbal arithmetic, line by line (long lines in windows)
    for ln in lines:
        if ln.end <= ln.start:
            continue
        for wa, wb in _windows(scan, ln.start, ln.end, limits.max_line_chars):
            seg = scan[wa:wb]
            if not seg.strip():
                continue
            toks = lex(scan, wa, wb, mode="plain", orig=text, cs=profile.computer_science, limits=limits, values=False).tokens
            if not toks:
                continue
            finder = _RunFinder(toks, scan, names, profile)
            taken: list[tuple[int, int]] = []
            verbal = _verbal(toks)
            for run in finder.runs():
                a = toks[run.first].start
                b = toks[run.last - 1].end
                if not run.quantity and any(vf <= run.first and run.last <= vl for vf, vl, _synth in verbal):
                    continue  # '3 times 4 = 12' read as '4 = 12': the verbal reading is the whole relation (STEM repair 2)
                if run.quantity:
                    spans.append(Span("quantity", a, b, rows=((a, b),), line=ln.index))
                    continue
                err, code = "", ""
                if b - a > limits.max_span_chars:
                    err, code = f"a math run of {b - a} characters exceeds the span bound of {limits.max_span_chars}", "ST-LIM-001"
                spans.append(Span("math_run", a, b, rows=((a, b),), lead=run.lead, label=run.label, line=ln.index, error=err, code=code))
                taken.append((run.first, run.last))
            for first, last, synth in verbal:
                if any(f <= first < l for f, l in taken):
                    continue
                a, b = toks[first].start, toks[last - 1].end
                spans.append(Span("verbal", a, b, rows=((a, b),), line=ln.index, tokens=synth))
    spans.sort(key=lambda s: (s.start, -s.end))
    return SpanSet(spans=tuple(spans), lines=lines, part_labels=tuple(sorted(parts, key=lambda p: p.start)), markup=tuple(sorted(markup)),
                   list_markers=tuple(list_markers), heading_lines=tuple(headings), math_view=math_view)


def _windows(view: str, a: int, b: int, size: int) -> list[tuple[int, int]]:
    """Cut ``view[a:b]`` into windows of at most ``size`` characters at spaces (a window never splits a token)."""
    if b - a <= size:
        return [(a, b)]
    out = []
    pos = a
    while pos < b:
        end = min(b, pos + size)
        if end < b:
            cut = view.rfind(" ", pos + size // 2, end)
            if cut > pos:
                end = cut
        out.append((pos, end))
        pos = end
    return out
