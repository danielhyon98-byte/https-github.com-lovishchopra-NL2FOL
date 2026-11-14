"""STEM fault injection for the arena harness (run_arena.py): contained multi-agent runs on STEM subjects.

Three mutations, applied only to answers of STEM subjects (the subjects the registry routes to the ``sciences``,
``mathematics`` or ``computer_science`` branch), each with the code that must name it on the receipt:

``stem_arithmetic_slip``   one stated result of a worked chain changed (``(20 − 0)/4.0 = 5.0`` → ``= 8.0``):
                           INT-SUBJ-001 (an engine check of the report's own arithmetic does not hold).
``stem_wrong_unit``        the unit of a stated result replaced by a unit of another dimension (``= 15 m s⁻¹`` →
                           ``= 15 m s⁻²``) in a link whose operands carry units: ST-DIM-001 (or ST-DIM-002), a warning.
``stem_substitution``      a value the request gives, substituted into a calculation, written as another value
                           (``…/4.0`` → ``…/7.0`` with 4.0 s in the request): INT-SUBJ-001.

The sites are found with bounded regular expressions over the answer's own text, independently of the STEM front end
under test, and every change moves the leading significant digit of a number by 3 (d + 3 for d ≤ 6, else d − 3): a
change of at least three units in the leading place, which no rounding of the written figures can absorb. That holds for
every figure, the exponent of a power of ten included (``10^(−8.2)`` → ``10^(−5.2)``): the checks must name such a change
whatever unit the result is stated in, so the injection never steers around a reading. A mutation with no site in an
answer is skipped (``None``), as ``altered_quotation`` is for an answer with no quotation. The marker (the mutated
stretch a finding's claim must carry) stays inside one statement: it stops at the end of its sentence and leaves a part
label ("(b) ") and a closing mark annotation ("  M1", "(A1)", "[2]") out, as every claim does. Nothing here evaluates
text, and nothing here decides whether an injection counts: run_arena.py counts every injection no finding names as a
miss.

Sites (round-8 clearance c1, STEM-integration finding 25; the STEM fixer's handoff item 4). A figure inside code (a fenced
block or an inline code span: the specialist's program, which the design never checks as working, ST-CODE-001), inside a
mark annotation ("M1", "(A1)", "[2]") or on a line that states a mark ("Provisional mark: 1–5 / 4") is never a site: the
mutation takes the next one. Two sites keep their mutation, and the code the design names the fault with there is accepted
beside the mutation's own (``StemInjection.site_codes``; ``expected`` itself never changes): a site inside a quotation of
another text, where the change is an altered quotation the hub refutes (INT-REQ-003; rule quoted-relation: a relation in
quotation marks is quoted text, no root and no step), and a term of a sum in brackets right after the value it forms
('7 on the left (1 + 6)'), which the STEM pack checks at warning severity (INT-SUBJ-004; rule parenthetical-sum, a reading).
"""
from __future__ import annotations

import bisect
import re
from typing import NamedTuple, Optional

STEM_MUTATIONS = ("stem_arithmetic_slip", "stem_wrong_unit", "stem_substitution")
#: codes that name each STEM mutation on a receipt
STEM_EXPECTED = {
    "stem_arithmetic_slip": ("INT-SUBJ-001",),
    "stem_wrong_unit": ("ST-DIM-001", "ST-DIM-002"),
    "stem_substitution": ("INT-SUBJ-001",),
}
STEM_BRANCHES = frozenset({"sciences", "mathematics", "computer_science"})

_MAX_SCAN = 200_000
#: the longest operand stretch before a relation sign that is examined (a bound on the work per sign)
_WINDOW = 200
_OPERATOR_CHARS = frozenset("×*/÷+−-·")
_OPERATOR_WORDS = ("\\times", "\\cdot")
#: unit swaps: a result unit and one of another dimension (unicode, ASCII and LaTeX spellings), longest first
_UNIT_SWAPS = sorted([
    ("m s⁻²", "m s⁻¹"), ("m s⁻¹", "m s⁻²"), ("m/s^2", "m/s"), ("m/s²", "m/s"), ("m/s", "m/s^2"), ("km h⁻¹", "km h⁻²"),
    ("kg m s⁻¹", "kg m s⁻²"), ("mol dm⁻³", "mol dm⁻²"), ("g mol⁻¹", "g mol"), ("N", "J"), ("J", "N"), ("kJ", "kN"), ("W", "J"), ("Pa", "N"),
    ("kPa", "kN"), ("V", "A"), ("A", "V"), ("Ω", "V"), ("Hz", "s"), ("kg", "mol"), ("mol", "kg"), ("g", "mol"), ("K", "J"), ("s", "m"), ("m", "s"),
    ("m³", "m²"), ("m²", "m³"), ("cm³", "cm²"), ("dm³", "dm²"),
], key=lambda p: -len(p[0]))
_UNIT_TAIL = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789⁰¹²³⁴⁵⁶⁷⁸⁹⁻^/_")
#: mark annotations closing a stretch ("  M1", "(A1)", "[2]", "[1 spare]"): marking furniture, which no claim carries
_ANNOTATION_TAIL_RE = re.compile(r"(?:(?:[ \t]{2,}|\t)\(?[MARN]\d{1,2}\)?|[ \t]*\([MARN]\d{1,2}\)|[ \t]*\[[ \t]*\d{1,2}(?:[ \t]*(?:marks?|spare))?[ \t]*\])+[ \t]*$")
#: the end of a sentence inside a line: a full stop, question or exclamation mark, then a space and a capital or a figure
_SENTENCE_END_RE = re.compile(r"[.?!](?=[ \t]+[A-Z0-9(\[])")
#: a list marker opening a line ("- ", "* ", "• ", "– ", "3) "), the shape the STEM front end reads as one (``stem.spans``): structure
#: too, which no claim carries
_LIST_MARKER_RE = re.compile(r"[ \t]{0,8}(?:[-*•–—]|\d{1,3}[.)])[ \t]+")
#: a part label opening a line ("(b) ", "(a)(ii) ", "2. ", "b) ", "Part (c): "): structure, which no claim carries
_PART_LABEL_RE = re.compile(r"[ \t]*(?:(?:part|question|q)[ \t]*)?(?:\([ \t]*(?:[a-h]|[ivx]{1,4}|\d{1,2})[ \t]*\)|(?:[a-h]|[ivx]{1,4})\)|\d{1,2}[.)])"
                            r"(?:[ \t]*\([ \t]*(?:[a-h]|[ivx]{1,4})[ \t]*\))?[ \t]*[:.]?[ \t]+", re.IGNORECASE)


def _number_at(text: str, i: int, end: int) -> int:
    """The end of a decimal number starting at ``i`` (digits, optionally a point and digits), or ``i`` when none starts there."""
    k = i
    while k < end and text[k].isdigit() and text[k].isascii():
        k += 1
    if k == i:
        return i
    if k + 1 < end and text[k] == "." and text[k + 1].isdigit() and text[k + 1].isascii():
        k += 1
        while k < end and text[k].isdigit() and text[k].isascii():
            k += 1
    return k


def _has_operator_between_figures(seg: str) -> bool:
    """A figure, then an arithmetic operator, then a figure (units may stand between): one pass over ``seg``."""
    seen_digit = seen_op = False
    i, n = 0, len(seg)
    while i < n:
        ch = seg[i]
        if ch.isdigit():
            if seen_op:
                return True
            seen_digit = True
        elif seen_digit and (ch in _OPERATOR_CHARS or seg.startswith(_OPERATOR_WORDS, i)):
            seen_op = True
        i += 1
    return False


def _unit_at(text: str, i: int, end: int) -> str:
    """The table unit written at ``i`` and ending there (not followed by more unit characters), or ''."""
    for unit, _other in _UNIT_SWAPS:
        j = i + len(unit)
        if j <= end and text.startswith(unit, i) and (j == end or text[j] not in _UNIT_TAIL):
            return unit
    return ""


def _has_quantity(seg: str) -> bool:
    """A figure followed (after at most one space) by a table unit: bounded by ``len(seg)`` times the table size."""
    for i, ch in enumerate(seg):
        if ch.isdigit() and i + 1 < len(seg) and not seg[i + 1].isdigit():
            k = i + 1 + (1 if seg[i + 1] == " " else 0)
            if _unit_at(seg, k, len(seg)):
                return True
    return False


def _relations(text: str):
    """``(operand start, sign index, value start, value end)`` for every '=' followed by a number, line by line: the operand
    is the stretch since the previous sign (at most ``_WINDOW`` characters). Linear in the text."""
    n = min(len(text), _MAX_SCAN)
    line_start = 0
    prev = -1
    i = 0
    while i < n:
        ch = text[i]
        if ch == "\n":
            line_start, prev = i + 1, -1
        elif ch == "=":
            lo = max(line_start, prev + 1, i - _WINDOW)
            j = i + 1
            while j < n and text[j] == " ":
                j += 1
            sign = j < n and text[j] in "−-"
            k = _number_at(text, j + (1 if sign else 0), n)
            if k > j + (1 if sign else 0):
                yield lo, i, j + (1 if sign else 0), k
            prev = i
        i += 1


class StemInjection(NamedTuple):
    """A mutated answer, the codes that must name the fault, and the mutated text a finding's claim must carry.
    ``site_codes``: the codes that name the fault at this site by design (module docstring, "Sites"), accepted by the arena
    beside ``expected``; empty for a site the mutation's own check reads."""
    text: str
    expected: tuple[str, ...]
    marker: str
    site_codes: tuple[str, ...] = ()


#: The longest body a quotation site is read in (one line; a mark with no closer on its line opens no quotation).
_QUOTE_BODY_MAX = 2000
#: Opening double marks and the marks that close each.
_QUOTE_CLOSERS = {'"': '"', "“": "”", "«": "»", "„": "“”"}
#: A mark annotation ("M1", "A1", "(A1)", "[2]", "[1 mark]"): marking furniture, never working.
_MARK_ANNOTATION_RE = re.compile(r"(?<![\w.])\(?[MARN]\d{1,2}\)?(?![\w.])|\[[ \t]*\d{1,2}(?:[ \t]*(?:marks?|spare))?[ \t]*\]")
#: A line that states a mark ("Provisional mark: 1–5 / 4", "Mark for (b): 2/4", "Marks: 3"): the marking, never working.
_MARK_LINE_RE = re.compile(r"^[ \t>*_-]*(?:provisional[ \t]+)?(?:marks?|score)(?:[ \t]+for[ \t]+[^:\n]{1,20})?[ \t]*:[^\n]*", re.IGNORECASE | re.MULTILINE)
#: A bracket holding a sum of figures right after the value it forms, at most four words before it ('7 on the left (1 + 6)').
_PAREN_SUM_RE = re.compile(r"\d(?:[ \t]+[^\W\d][\w'’-]*){0,4}[ \t]*\((?P<body>[ \t]*\d+(?:\.\d+)?(?:[ \t]*[+−-][ \t]*\d+(?:\.\d+)?){1,5}[ \t]*)\)")


def _code_spans(text: str) -> list[tuple[int, int]]:
    """Fenced code blocks (a line opening with three backticks or tildes to the next such line, or the end) and inline code
    spans (a backtick run to the next run of the same length on its line). One pass over the text."""
    n = min(len(text), _MAX_SCAN)
    out: list[tuple[int, int]] = []
    pos = 0
    fence_start = -1
    while pos < n:
        end = text.find("\n", pos, n)
        end = n if end < 0 else end
        line = text[pos:end]
        stripped = line.lstrip(" \t")
        if stripped.startswith(("```", "~~~")):
            if fence_start < 0:
                fence_start = pos
            else:
                out.append((fence_start, end))
                fence_start = -1
        elif fence_start < 0 and "`" in line:
            i = 0
            while True:
                i = line.find("`", i)
                if i < 0:
                    break
                k = i
                while k < len(line) and line[k] == "`":
                    k += 1
                close = line.find(line[i:k], k)
                if close < 0:
                    break
                out.append((pos + i, pos + close + (k - i)))
                i = close + (k - i)
        pos = end + 1
    if fence_start >= 0:
        out.append((fence_start, n))
    return out


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    """The bodies of double quotations, each on one line (at most ``_QUOTE_BODY_MAX`` characters): one pass per line, each
    opening mark looking for its closer once."""
    n = min(len(text), _MAX_SCAN)
    out: list[tuple[int, int]] = []
    pos = 0
    while pos < n:
        end = text.find("\n", pos, n)
        end = n if end < 0 else end
        i = pos
        while i < end:
            ch = text[i]
            closers = _QUOTE_CLOSERS.get(ch)
            if closers is None:
                i += 1
                continue
            k = i + 1
            stop = min(end, i + 1 + _QUOTE_BODY_MAX)
            while k < stop and text[k] not in closers:
                k += 1
            if k < stop:
                out.append((i + 1, k))
                i = k + 1
            else:
                i += 1
        pos = end + 1
    return out


def _disjoint(spans: list[tuple[int, int]]) -> tuple[list[int], list[int]]:
    """``spans`` merged into disjoint intervals, as their starts and ends in order."""
    starts: list[int] = []
    ends: list[int] = []
    for s0, e0 in sorted(spans):
        if starts and s0 <= ends[-1]:
            ends[-1] = max(ends[-1], e0)
        else:
            starts.append(s0)
            ends.append(e0)
    return starts, ends


class _Sites:
    """Where a site may not be (code, mark annotations, mark lines) and where its fault is named by design with another code
    (a quotation, a bracketed sum after its value): the spans, found once per answer and merged into disjoint intervals, each
    looked up by binary search."""

    def __init__(self, text: str):
        n = min(len(text), _MAX_SCAN)
        self.excluded = _disjoint(_code_spans(text) + [m.span() for m in _MARK_ANNOTATION_RE.finditer(text, 0, n)]
                                  + [m.span() for m in _MARK_LINE_RE.finditer(text, 0, n)])
        self.quoted = _disjoint(_quoted_spans(text))
        self.sums = _disjoint([m.span("body") for m in _PAREN_SUM_RE.finditer(text, 0, n)])

    @staticmethod
    def _last_before(spans: tuple[list[int], list[int]], b: int) -> Optional[tuple[int, int]]:
        """The interval with the greatest start below ``b`` (in disjoint intervals the only one that can reach past any point before b)."""
        starts, ends = spans
        k = bisect.bisect_left(starts, b) - 1
        return (starts[k], ends[k]) if k >= 0 else None

    def excluded_at(self, a: int, b: int) -> bool:
        """True when the changed stretch ``[a, b)`` overlaps code, a mark annotation or a mark line."""
        hit = self._last_before(self.excluded, b)
        return hit is not None and a < hit[1]

    @classmethod
    def _inside(cls, spans: tuple[list[int], list[int]], a: int, b: int) -> bool:
        hit = cls._last_before(spans, b)
        return hit is not None and hit[0] <= a and b <= hit[1]

    def codes_at(self, a: int, b: int, kind: str) -> tuple[str, ...]:
        """The codes that name the fault at ``[a, b)`` by design (module docstring)."""
        if self._inside(self.quoted, a, b):
            return ("INT-REQ-003",)
        if kind == "stem_substitution" and self._inside(self.sums, a, b):
            return ("INT-SUBJ-004",)
        return ()


def leading_digit_slip(number: str) -> str:
    """``number`` with its leading significant digit moved by 3 (d + 3 for d ≤ 6, else d − 3)."""
    for i, ch in enumerate(number):
        if ch in "123456789":
            d = int(ch)
            return number[:i] + str(d + 3 if d <= 6 else d - 3) + number[i + 1:]
    raise ValueError(f"no significant digit in {number!r}")


def is_stem_subject(subject: str) -> bool:
    """True when the registry routes ``subject`` to a STEM branch (the routing the hub itself applies)."""
    from epinoic_logic.branches.registry import default_registry
    return default_registry().for_subject(subject)[0].key in STEM_BRANCHES


def _line_bounds(text: str, a: int) -> tuple[int, int]:
    """The line around ``a``, at most ``_WINDOW`` characters each way."""
    s = text.rfind("\n", max(0, a - _WINDOW), a) + 1 or max(0, a - _WINDOW)
    s = max(s, a - _WINDOW)
    e = text.find("\n", a, a + _WINDOW)
    return s, min(len(text), a + _WINDOW) if e < 0 else e


def _link_marker(text: str, a: int, b: int, *, through_next_relation: bool = False) -> str:
    """The mutated link as a marker: from the relation sign before the operand that holds ``[a, b)`` (``through_next``:
    the operand alone, up to the next relation sign) — a stretch inside one statement, so the claim that carries it is
    found by its text. Bounded by the line, and by the sentence that holds the operand ("low = mid + 4 is safe. In an
    unsorted list ..." gives "mid + 4 is safe"); a part label or a list marker opening the line ("(b) ", "- ") and a mark
    annotation closing the stretch ("6 − 9t  M1") are left out, as every claim leaves them out."""
    s, e = _line_bounds(text, a)
    at_line_start = s == 0 or text[s - 1] == "\n"
    label = _PART_LABEL_RE.match(text, s) if at_line_start else None
    if label is not None and label.end() <= a:
        s = label.end()  # a part label opening the line is structure: no claim carries it
    bullet = _LIST_MARKER_RE.match(text, s) if at_line_start else None
    if bullet is not None and bullet.end() <= a:
        s = bullet.end()  # so is a list marker ("- 181 − 128 = 53" is carried as "181 − 128 = 53")
    if through_next_relation:
        left = text.rfind("=", s, a)
        right = text.find("=", b, e)
        lo = (left + 1) if left >= 0 else s
        hi = right if right >= 0 else e
        end = _SENTENCE_END_RE.search(text, b, hi)
        if end is not None:
            hi = end.start()
        tail = _ANNOTATION_TAIL_RE.search(text, b, hi)
        if tail is not None:
            hi = tail.start()
    else:
        eq = text.rfind("=", s, a)
        left = text.rfind("=", s, eq) if eq >= 0 else -1
        lo = (left + 1) if left >= 0 else s
        hi = b
    for stop in (". ", "; ", ", "):
        k = text.rfind(stop, lo, a)
        if k >= 0:
            lo = k + len(stop)
    return text[lo:hi].strip(" $\t")


def arithmetic_slip(text: str) -> Optional[StemInjection]:
    """The first stated result of a worked chain (an operator between figures before ``=``) with its leading digit moved."""
    sites = _Sites(text)
    for lo, _sign, a, b in _relations(text):
        if not _has_operator_between_figures(text[lo:_sign]):
            continue
        num = text[a:b]
        if not any(c in "123456789" for c in num) or sites.excluded_at(a, b):
            continue
        mutated = text[:a] + leading_digit_slip(num) + text[b:]
        return StemInjection(mutated, STEM_EXPECTED["stem_arithmetic_slip"], _link_marker(mutated, a, b), sites.codes_at(a, b, "stem_arithmetic_slip"))
    return None


def wrong_unit(text: str) -> Optional[StemInjection]:
    """The unit of the first stated result whose left side carries quantities with units and an operator, replaced by a
    unit of another dimension (the left side's units fix the dimension, so the mismatch is visible to a dimension check)."""
    swaps = dict(_UNIT_SWAPS)
    n = min(len(text), _MAX_SCAN)
    sites = _Sites(text)
    for lo, sign, _a, b in _relations(text):
        k = b + (1 if b < n and text[b] == " " else 0)
        unit = _unit_at(text, k, n)
        lhs = text[lo:sign]
        if not unit or not _has_quantity(lhs) or not any(c in _OPERATOR_CHARS for c in lhs) or sites.excluded_at(k, k + len(unit)):
            continue
        mutated = text[:k] + swaps[unit] + text[k + len(unit):]
        return StemInjection(mutated, STEM_EXPECTED["stem_wrong_unit"], _link_marker(mutated, k, k + len(swaps[unit])),
                             sites.codes_at(k, k + len(unit), "stem_wrong_unit"))
    return None


def _numbers(text: str):
    """``(start, end)`` of every decimal number not glued to another figure or point, in one pass."""
    n = min(len(text), _MAX_SCAN)
    i = 0
    while i < n:
        if text[i].isdigit() and text[i].isascii() and (i == 0 or not (text[i - 1].isdigit() or text[i - 1] == ".")):
            k = _number_at(text, i, n)
            if not (k < n and (text[k].isdigit() or text[k] == ".")):
                yield i, k
            i = max(k, i + 1)
        else:
            i += 1


def _given_values(question: str) -> set[str]:
    return {question[a:b] for a, b in _numbers(question) if any(c in "123456789" for c in question[a:b])}


def substitution(text: str, question: str) -> Optional[StemInjection]:
    """A value the request gives, written in the answer as an operand of an arithmetic operator (a substitution in a
    calculation, not a ``Given`` line or a stated value), with its leading digit moved. Only that occurrence changes, so
    the substituted value no longer matches the request and the chain's arithmetic no longer holds."""
    givens = _given_values(question)
    if not givens:
        return None
    sites = _Sites(text)
    for a, b in _numbers(text):
        num = text[a:b]
        if num not in givens or sites.excluded_at(a, b):
            continue
        before = text[max(0, a - 40):a]
        before = before[before.rfind("\n") + 1:].rstrip(" (")
        after = text[b:b + 40]
        after = after[:after.find("\n")] if "\n" in after else after
        after = after.lstrip(" )")
        beside_op = (before[-1:] in _OPERATOR_CHARS or before.endswith(_OPERATOR_WORDS)) or (after[:1] in _OPERATOR_CHARS or after.startswith(_OPERATOR_WORDS))
        if not beside_op or before.lstrip().lower().startswith(("given", "data")):
            continue
        stripped = before.rstrip()
        if stripped.endswith("=") and stripped[:-1].rstrip()[-1:].isalpha():
            continue  # 'x = 8.0 …': a value stated for a symbol, not a substitution
        line_end = text.find("\n", b, b + _WINDOW)
        if "=" not in text[a:(line_end if line_end >= 0 else b + _WINDOW)] and "=" not in before:
            continue
        mutated = text[:a] + leading_digit_slip(num) + text[b:]
        return StemInjection(mutated, STEM_EXPECTED["stem_substitution"], _link_marker(mutated, a, b, through_next_relation=True),
                             sites.codes_at(a, b, "stem_substitution"))
    return None


def mutate_stem(text: str, question: str, kind: str) -> Optional[StemInjection]:
    """The STEM mutation ``kind`` of ``text`` (an answer to ``question``), or None when the answer has no site for it."""
    if kind == "stem_arithmetic_slip":
        return arithmetic_slip(text)
    if kind == "stem_wrong_unit":
        return wrong_unit(text)
    if kind == "stem_substitution":
        return substitution(text, question)
    raise ValueError(kind)
