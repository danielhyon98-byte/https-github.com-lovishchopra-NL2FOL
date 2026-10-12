"""Statements of a STEM answer (section 4.3 of docs/STEM_DESIGN.md).

A statement is one of:

* ``sentence``: a sentence of the prose view, split by the SHARED splitter
  (``adapters/history_specialist/sentences.sentence_boundaries``, untouched) plus three
  STEM-only boundary rules applied here:
  - a sentence ends after a masked math span or a number with its unit followed by ``.``,
    a space and a capital (``The ball falls 5.0 m. It then stops.``), also when a unit follows
    the masked span (``… $E = 3.5$ J. Next …``: a bounded look-back of 16 characters);
  - it ends after a single lower-case letter that is a symbol in scope followed by ``.``, a
    space and a capital (``the speed is v. Then …``);
  - neither rule applies to ``c.`` or ``p.`` followed by a digit (circa, page), and the shared
    splitter's own abbreviation rules stay in force;
* ``derivation``: a line of which at least 60 % of the non-space characters lie in one math
  span (a math run with its prose label, or an inline LaTeX span), or that opens with a
  relation sign (``continuation``: it continues the previous line's chain);
* ``display_row``: one row of a LaTeX display;
* ``list_item``: an item of a list (a line that opens with a list marker), split into
  sentences when it holds several;
* ``code``: a code block (never parsed for meaning);
* ``table`` and ``data_line``: a Markdown table, a bracketed data or vector line.

Part labels (``(a)``, ``b)``, ``(b)(ii)``, ``Part (c)``, ``Question 2``, Markdown headings)
are structure, not statements: each statement records the part in force. A Markdown heading,
or a part label alone on its line (``**Part (a)**``), starts a paragraph and sets the part. Ids are
``s<paragraph>.<statement>``, both counted from 1, stable and deterministic. Statements
beyond ``max_statements`` are merged into one ``s.tail`` statement (the report contract's
claim limit), which the parser turns into an unresolved issue.

The prose view is a same-length masked copy of the text, so a sentence boundary never falls
inside a math span: ``\\frac{1}{2} M v^2`` is never cut, and the decimal points, primes,
inch marks and quotation marks inside spans are invisible to the splitter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..adapters.history_specialist.sentences import sentence_boundaries
from .limits import DEFAULT_LIMITS, StemLimits
from .normalize import prose_view
from .spans import Span, SpanSet
from .units import parse_unit

__all__ = ["Segmentation", "Statement", "TAIL_ID", "segment_statements"]

TAIL_ID = "s.tail"
_DERIVATION_SHARE = 0.6
_UNIT_LOOKBACK = 16
_UNIT_CHARS = frozenset(" ⁻¹²³⁴⁵⁶⁷⁸⁹⁰·/°%")
_MASKED_KINDS = ("code_block", "code_inline", "latex_display", "latex_inline", "chem", "math_run", "verbal", "quantity")


@dataclass(frozen=True)
class Statement:
    """One statement: ``start``/``end`` are offsets of the original text (``text[start:end]`` is
    the claim text, trimmed). ``spans`` lists ``(span index, row index)`` of the math and chemistry
    read in this statement, in order. ``continuation`` marks a derivation line or display row that
    opens with a relation sign. ``part`` is the part label in force (empty when none)."""

    id: str
    kind: str
    start: int
    end: int
    paragraph: int
    index: int
    line: int
    part: str = ""
    continuation: bool = False
    list_item: bool = False
    spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class Segmentation:
    statements: tuple[Statement, ...]
    paragraphs: tuple[tuple[int, int], ...]
    prose: str
    overflow: int = 0

    def by_id(self, sid: str) -> Optional[Statement]:
        for st in self.statements:
            if st.id == sid:
                return st
        return None

    def covering(self, start: int, end: int) -> tuple[Statement, ...]:
        """Statements whose ranges overlap ``[start, end)``."""
        return tuple(st for st in self.statements if st.start < end and start < st.end)


def _trim(text: str, a: int, b: int) -> tuple[int, int]:
    while a < b and text[a] in " \t\r\n":
        a += 1
    while b > a and text[b - 1] in " \t\r\n":
        b -= 1
    return a, b


@dataclass
class _Builder:
    text: str
    prose: str
    spans: SpanSet
    names: frozenset[str]
    mask_ranges: list[tuple[int, int]]
    limits: StemLimits
    out: list[Statement]
    paragraph: int = 0
    index: int = 0
    part: str = ""
    #: end offsets of the masked spans (a set: the boundary rule looks one up per full stop)
    mask_ends: frozenset[int] = frozenset()

    def add(self, kind: str, a: int, b: int, line: int, *, continuation: bool = False, list_item: bool = False) -> None:
        a, b = _trim(self.text, a, b)
        if b <= a:
            return
        self.index += 1
        self.out.append(Statement(id=f"s{self.paragraph}.{self.index}", kind=kind, start=a, end=b, paragraph=self.paragraph, index=self.index, line=line,
                                  part=self.part, continuation=continuation, list_item=list_item))

    def prose_group(self, a: int, b: int, line: int, list_item: bool) -> None:
        a, b = _trim(self.text, a, b)
        if b <= a:
            return
        pv = self.prose[a:b]
        cuts = set(sentence_boundaries(pv))
        cuts.update(self._stem_boundaries(pv, a))
        pos = 0
        first = True
        for c in sorted(cuts) + [len(pv)]:
            if c <= pos:
                continue
            kind = "list_item" if (list_item and first) else "sentence"
            self.add(kind, a + pos, a + c, line, list_item=list_item)
            first = False
            pos = c

    def _stem_boundaries(self, pv: str, base: int) -> list[int]:
        """The STEM-only boundary rules (see the module docstring)."""
        out: list[int] = []
        n = len(pv)
        k = pv.find(".")
        while 0 <= k < n:
            nxt = k + 1
            while nxt < n and pv[nxt] in " \t\n":
                nxt += 1
            if nxt > k + 1 and nxt < n and pv[nxt].isupper():
                absolute = base + k
                after_mask = absolute in self.mask_ends or self._unit_after_mask(pv, k, base)
                letter = k >= 1 and pv[k - 1].isalpha() and pv[k - 1].islower() and (k == 1 or not pv[k - 2].isalnum()) and pv[k - 1] in self.names \
                    and pv[k - 1] not in ("c", "p")
                if after_mask or letter:
                    out.append(nxt)
            k = pv.find(".", k + 1)
        return out

    def _unit_after_mask(self, pv: str, k: int, base: int) -> bool:
        """A unit between a masked span and the full stop at ``k`` (``$…$ J. Next``): a bounded look-back."""
        j = k
        lo = max(0, k - _UNIT_LOOKBACK)
        while j > lo and (pv[j - 1].isalpha() or pv[j - 1] in _UNIT_CHARS):
            j -= 1
            if base + j in self.mask_ends:
                unit = pv[j:k].strip()
                return bool(unit) and pv[j:j + 1] in (" ", "\u00a0") and parse_unit(unit) is not None
        return False


def segment_statements(text: str, spans: SpanSet, *, names: frozenset[str] = frozenset(), limits: StemLimits = DEFAULT_LIMITS,
                       reading: Optional[str] = None) -> Segmentation:
    """Split ``text`` into statements using its spans (``spans.find_spans``). ``names`` are the
    symbols in scope (for the ``is v. Then`` rule); ``reading`` is the reading view (part labels
    are located in it; the math view has them blanked)."""
    view = spans.math_view or text
    rview = reading if reading is not None else text
    masked_ranges = [(s.start, s.end) for s in spans.spans if s.kind in _MASKED_KINDS]
    prose = prose_view(view, masked_ranges, blank=spans.markup)
    lines = spans.lines
    out: list[Statement] = []
    b = _Builder(text=text, prose=prose, spans=spans, names=names, mask_ranges=sorted(masked_ranges), limits=limits, out=out,
                 mask_ends=frozenset(e for a, e in masked_ranges if e > a))
    # atomic blocks that may span lines
    blocks: list[Span] = [s for s in spans.spans if s.kind in ("code_block", "latex_display", "table")]
    block_at: dict[int, Span] = {}
    for blk in blocks:
        block_at.setdefault(blk.start, blk)
    blocks_sorted = sorted(blocks, key=lambda s: s.start)
    part_at = {p.start: p for p in spans.part_labels}
    part_by_line = {p.line: p for p in spans.part_labels}
    list_lines = {_line_of(lines, a) for a, _b in spans.list_markers}
    heading_lines = set(spans.heading_lines)
    line_spans = _line_math_spans(spans)
    math_ends = frozenset(sp.end for sp in spans.spans if sp.is_math)
    paragraphs: list[tuple[int, int]] = []
    para_start: Optional[int] = None
    group: Optional[tuple[int, int, int, bool]] = None  # (start, end, line, list_item)

    def flush() -> None:
        nonlocal group
        if group is not None:
            b.prose_group(group[0], group[1], group[2], group[3])
            group = None

    def new_paragraph(at: int) -> None:
        nonlocal para_start
        flush()
        if para_start is not None:
            paragraphs.append((para_start, at))
        para_start = None

    def open_paragraph(at: int) -> None:
        nonlocal para_start
        if para_start is None:
            para_start = at
            b.paragraph += 1
            b.index = 0

    li = 0
    nlines = len(lines)
    bi = 0
    pos = 0  # everything before pos is consumed
    while li < nlines:
        ln = lines[li]
        if ln.end < pos:
            li += 1
            continue
        seg_start = max(ln.start, pos)
        raw = view[seg_start:ln.end]
        # a block that starts on this line (at or after seg_start)
        while bi < len(blocks_sorted) and blocks_sorted[bi].end <= seg_start:
            bi += 1
        blk = blocks_sorted[bi] if bi < len(blocks_sorted) and blocks_sorted[bi].start < ln.end + 1 and blocks_sorted[bi].start >= seg_start else None
        if ln.index in heading_lines and seg_start == ln.start and blk is None:
            # a Markdown heading (blanked in the math view): a paragraph break that sets the part in force
            new_paragraph(ln.start)
            p = part_by_line.get(ln.index)
            b.part = p.text if p is not None else b.part
            pos = ln.end + 1
            li += 1
            continue
        if blk is None and not raw.strip():
            new_paragraph(ln.start)
            lone = part_by_line.get(ln.index)
            if lone is not None and seg_start == ln.start:
                b.part = lone.text  # a part label alone on its line ('**Part (a)**', '(b)'): it holds for what follows
            pos = ln.end + 1
            li += 1
            continue
        open_paragraph(seg_start)
        if blk is not None:
            # prose before the block on this line
            if blk.start > seg_start and view[seg_start:blk.start].strip():
                if group is None:
                    group = (seg_start, blk.start, ln.index, False)
                else:
                    group = (group[0], blk.start, group[2], group[3])
            flush()
            if blk.kind == "code_block":
                b.add("code", blk.start, blk.end, ln.index)
            elif blk.kind == "table":
                b.add("table", blk.start, blk.end, ln.index)
            else:
                rows = blk.rows if not blk.error else ((blk.start, blk.end),)
                for ri, (ra, rb) in enumerate(rows):
                    cont = _starts_with_relation(view, ra, rb)
                    b.add("display_row", ra, rb, _line_of(lines, ra), continuation=cont)
            pos = blk.end
            # continue on the line holding the block's end
            li = _line_of(lines, max(blk.end - 1, blk.start))
            if blk.end >= lines[li].end:
                li += 1
                pos = lines[li - 1].end + 1 if li - 1 < nlines else blk.end
            continue
        # a part label at the start of the line
        content_start = seg_start
        p = part_at.get(_first_nonspace(rview, seg_start, ln.end))
        if p is not None and p.line == ln.index:
            flush()
            b.part = p.text
            content_start = p.end
        is_list = ln.index in list_lines and seg_start == ln.start
        if is_list:
            flush()
            for a0, b0 in spans.list_markers:
                if ln.start <= a0 < ln.end:
                    content_start = max(content_start, b0)
            p2 = part_at.get(_first_nonspace(rview, content_start, ln.end))
            if p2 is not None and p2.line == ln.index:
                b.part = p2.text
                content_start = p2.end
        if not view[content_start:ln.end].strip():
            pos = ln.end + 1
            li += 1
            continue
        kind = _line_kind(view, content_start, ln.end, line_spans.get(ln.index, []), spans)
        if kind in ("derivation", "data_line"):
            flush()
            cont = _starts_with_relation(view, content_start, ln.end)
            split = _derivation_split(view, content_start, ln.end, line_spans.get(ln.index, [])) if kind == "derivation" else None
            if split is None:
                b.add(kind, content_start, ln.end, ln.index, continuation=cont, list_item=is_list)
            else:
                # a derivation followed on its line by a sentence of prose ('… = 30 m. The displacement is therefore 30 m.'):
                # the prose is a statement of its own, as it would be after a line break
                b.add(kind, content_start, split[0], ln.index, continuation=cont, list_item=is_list)
                group = (split[1], ln.end, ln.index, False)
        elif is_list:
            group = (content_start, ln.end, ln.index, True)
        else:
            if group is not None and _ends_in_math(view, group[1], math_ends) and _opens_statement(view, content_start, ln.end):
                flush()  # a line that ends in maths, then a line that opens with a capital or maths: two statements
            if group is None:
                group = (content_start, ln.end, ln.index, False)
            else:
                group = (group[0], ln.end, group[2], group[3])
        pos = ln.end + 1
        li += 1
    flush()
    if para_start is not None:
        paragraphs.append((para_start, len(text)))
    # attach spans to statements
    statements = _attach(out, spans, text)
    overflow = 0
    if len(statements) > limits.max_statements:
        head = statements[: limits.max_statements - 1]
        rest = statements[limits.max_statements - 1:]
        overflow = len(rest)
        tail = Statement(id=TAIL_ID, kind="tail", start=rest[0].start, end=rest[-1].end, paragraph=rest[0].paragraph, index=0, line=rest[0].line,
                         part=rest[0].part, spans=tuple(x for st in rest for x in st.spans))
        statements = head + [tail]
    return Segmentation(statements=tuple(statements), paragraphs=tuple(paragraphs), prose=prose, overflow=overflow)


def _ends_in_math(view: str, end: int, math_ends: frozenset[int]) -> bool:
    """The text before ``end`` ends with a math span (trailing spaces aside), with no sentence punctuation after it.
    ``math_ends`` holds the end offsets of the math spans (computed once: one look-up per line)."""
    e = end
    while e > 0 and view[e - 1] in " \t":
        e -= 1
    return e in math_ends


def _opens_statement(view: str, a: int, b: int) -> bool:
    k = _first_nonspace(view, a, b)
    return k < b and (view[k].isupper() or view[k].isdigit() or view[k] in "(-−√")


def _first_nonspace(view: str, a: int, b: int) -> int:
    while a < b and view[a] in " \t":
        a += 1
    return a


def _line_of(lines: tuple, offset: int) -> int:
    lo, hi = 0, len(lines) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if lines[mid].start <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _starts_with_relation(view: str, a: int, b: int) -> bool:
    s = view[a:b].lstrip(" \t&")
    for sign in ("=", "≈", "≃", "≠", "<", ">", "≤", "≥", "⇒", "\\approx", "\\neq", "\\leq", "\\geq", "\\Rightarrow", "\\implies", "→", "\\to "):
        if s.startswith(sign):
            return True
    return False


def _line_math_spans(spans: SpanSet) -> dict[int, list[Span]]:
    out: dict[int, list[Span]] = {}
    for sp in spans.spans:
        if sp.kind in ("math_run", "latex_inline", "verbal", "data_line", "chem"):
            line = sp.line if sp.line >= 0 else _line_of(spans.lines, sp.start)
            out.setdefault(line, []).append(sp)
    return out


def _derivation_split(view: str, a: int, b: int, line_spans: list[Span]) -> Optional[tuple[int, int]]:
    """``(end of the derivation, start of the prose)`` when a math span of the line ``[a, b)`` is followed by sentence
    punctuation, a space and a capital outside every span, with prose after it; None otherwise (one pass over the spans)."""
    inside = [(sp.start, sp.end) for sp in line_spans if a <= sp.start and sp.end <= b]
    for sp in sorted(line_spans, key=lambda s: s.end):
        if sp.kind not in ("math_run", "latex_inline", "verbal", "chem") or sp.start < a or sp.end > b:
            continue
        k = sp.end
        while k < b and view[k] in " \t$":
            k += 1
        if k >= b or view[k] not in ".;!?":
            continue
        j = k + 1
        if j >= b or view[j] not in " \t":
            continue
        while j < b and view[j] in " \t":
            j += 1
        if j < b and view[j].isupper() and not any(x <= j < y for x, y in inside) and len(view[j:b].split()) >= 2:
            return k + 1, j
    return None


def _line_kind(view: str, a: int, b: int, line_spans: list[Span], spans: SpanSet) -> str:
    """``derivation`` when one math span (with its prose label) covers at least 60 % of the
    line's non-space characters, or the line opens with a relation sign; ``data_line`` for a
    bracketed data line; ``prose`` otherwise."""
    text = view[a:b]
    # a short header ending in a colon ('Carriers:', 'Heat released:') is not counted against the maths
    colon = text.find(":")
    if 0 < colon <= 48 and len(text[:colon].split()) <= 6 and all(w.isalpha() for w in text[:colon].split()):
        a = a + colon + 1
        text = view[a:b]
    total = len("".join(text.split()))   # the non-space characters (str.split and str.isspace share one notion of space)
    if total == 0:
        return "prose"
    if _starts_with_relation(view, a, b) and any(sp.kind == "math_run" and sp.start >= a for sp in line_spans):
        return "derivation"
    for sp in line_spans:
        if sp.start < a or sp.end > b:
            continue
        if sp.kind == "data_line" and sp.start <= a + 2:
            return "data_line"
        if sp.kind not in ("math_run", "latex_inline", "verbal", "chem"):
            continue
        lo = sp.start
        if sp.kind == "math_run" and sp.label:
            k = view.rfind(sp.label.split(" ")[0], a, sp.start)
            if k >= a:
                lo = k
        covered = len("".join(view[lo:sp.end].split()))
        if covered >= _DERIVATION_SHARE * total:
            return "derivation"
    return "prose"


def _attach(statements: list[Statement], spans: SpanSet, text: str) -> list[Statement]:
    """Record on each statement the spans (and display rows) it holds."""
    out: list[Statement] = []
    # index spans by start for a linear sweep
    entries: list[tuple[int, int, int]] = []  # (offset, span index, row index)
    view = text
    for si, sp in enumerate(spans.spans):
        if sp.kind == "latex_display" and not sp.error:
            for ri, (ra, _rb) in enumerate(sp.rows):
                entries.append((ra, si, ri))
        else:
            # a block may open with indentation the statement trims away: use its first non-space character
            a = sp.start
            while view and a < sp.end and a < len(view) and view[a] in " \t\n":
                a += 1
            entries.append((a, si, 0))
    entries.sort()
    j = 0
    ordered = sorted(range(len(statements)), key=lambda k: statements[k].start)
    found: dict[int, list[tuple[int, int]]] = {k: [] for k in ordered}
    for k in ordered:
        st = statements[k]
        while j < len(entries) and entries[j][0] < st.start:
            j += 1
        m = j
        while m < len(entries) and entries[m][0] < st.end:
            found[k].append((entries[m][1], entries[m][2]))
            m += 1
    for k, st in enumerate(statements):
        out.append(Statement(id=st.id, kind=st.kind, start=st.start, end=st.end, paragraph=st.paragraph, index=st.index, line=st.line, part=st.part,
                             continuation=st.continuation, list_item=st.list_item, spans=tuple(found[k])))
    return out
