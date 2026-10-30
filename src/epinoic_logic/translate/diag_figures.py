"""Figure support for the argument diagnosis: whether the figures of an assignment premise are stated, derived by the
answer's own working, or introduced by the answer (``EVD-FIG-001``, ``EVD-LACK-001``; :mod:`.diag_evidence`).

These are the readings the argument diagnosis was built and measured with (rules ``argdiag-2``). They are kept in a
module of their own so that they decide nothing else: the grounding checks of :mod:`.grounding`, and so the authority
of every premise, the engine's dependency lists and release, are this tree's own. A reading here only decides whether
an advisory diagnostic names a figure; it never verifies or refutes a grounding.

Everything is data: closed tables and bounded linear scans of the records (nothing is evaluated).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Any, Literal, Optional, Sequence

from .. import lexis
from ..ir.schema import Symbol
from .quantities import (TRIVIAL_VALUES, DeclaredReading, Exactness, Match, SourceText, StatedFigure, declared_reading, figure_stated_plainly,
                         figures_in, interval_derivation, is_year_like, literal_matches, rounded_intervals, sentence_of, stated_exactness,
                         tolerance_bounds)
from .relations import assignment_parts

__all__ = ["FigureSupport", "assignment_support", "worked_results", "written_precision_intervals"]


def written_precision_intervals(figure: StatedFigure, text: str, declared: Optional[DeclaredReading] = None
                                ) -> list[tuple[tuple[Fraction, Fraction, bool, bool], Match, Exactness]]:
    """The intervals a figure states at its WRITTEN precision: those of :func:`.quantities.rounded_intervals` (a figure
    stated as rounded by a cue or by a calculation it rounds), and, for a figure written as the result of a calculation the
    closed reader does not compute (rounded only by the convention of written calculation, with no computed value), the
    half-unit enclosure of its last written place. A given figure with no cue and no calculation, an exact figure, and a
    figure its own written calculation contradicts state no interval."""
    out = rounded_intervals(figure, text, declared)
    if out:
        return out
    ex = stated_exactness(figure, text)
    if ex.kind == "rounded" and ex.by_convention and ex.computed is None and ex.mode == "nearest" and ex.half_width:
        return _intervals_of(figure, ex, declared if declared is not None else DeclaredReading("none"))
    return []


def _intervals_of(figure: StatedFigure, ex: Exactness, declared: DeclaredReading) -> list[tuple[tuple[Fraction, Fraction, bool, bool], Match, Exactness]]:
    """The intervals the exactness ``ex`` gives ``figure``, one per derivation the declared reading admits."""
    centres = {figure.value, figure.scaled}
    if figure.is_percent_like:
        centres.add(figure.scaled * (figure.unit_factor or Fraction(1, 100)))
    if declared.kind == "unit" and figure.unit_factor is not None and figure.unit_dim == declared.dim and declared.factor:
        centres.add(figure.scaled * figure.unit_factor / declared.factor)
    out: list[tuple[tuple[Fraction, Fraction, bool, bool], Match, Exactness]] = []
    seen: set[tuple[Fraction, Fraction, bool, bool]] = set()
    for centre in sorted(centres | {-c for c in centres}, key=lambda c: (c < 0, abs(c))):
        for m in literal_matches(centre, [figure], declared)[0]:
            bounds = tolerance_bounds(centre, ex, m.factor)
            if bounds is None or bounds in seen:
                continue
            seen.add(bounds)
            out.append((bounds, m, ex))
    return out



@dataclass(frozen=True)
class _Literal:
    """A numeric literal of an expression with the reading its compared symbol declares. ``required`` is the comparison an
    assignment conjunct states about its symbol (``eq``, ``lt``, ``le``, ``gt``, ``ge``, read from the symbol's side), which
    the stated figure must establish (:func:`.assertion.stated_as`); None for a literal of a relation."""
    written: str
    value: Fraction
    declared: DeclaredReading
    symbol: Optional[str]
    required: Optional[str] = None
    year: Optional[int] = None  # the one year that qualifies the symbol's meaning (else the premise's label), if any
    about: str = ""  # the symbol's meaning and the premise's label: what the figure is about (the same-subject rule)
    meaning: str = ""  # the symbol's meaning alone: whether the symbol is a bound itself (a target, a ceiling: stated_as)
    lookup: Optional["_Lookup"] = None  # the indexed lookup whose position this literal is (:func:`_index_lookup`), if any


@dataclass(frozen=True)
class _Lookup:
    """An indexed lookup of an expression (:func:`_index_lookup`): its values in order (``values``: the branch values,
    ``with_default`` the same with the final value), the position ``base`` it counts from (0 or 1) and the slot of one index
    literal (its position is ``base + slot``)."""
    values: tuple[Fraction, ...]
    with_default: tuple[Fraction, ...]
    base: int
    slot: int


_YEAR_TOKEN_RE = re.compile(r"(?<![\w.,$£€¥])(1[0-9]{3}|20[0-9]{2}|21[0-9]{2})(?![\w]|[.,]\d)")


#: Words before a year that make it a time qualifier ("in 2010", "during 1923", "between 1750 and 2023").
_YEAR_LEAD_WORDS = frozenset("in of during by since from to until till before after between year years fy around circa c".split())


_PREV_WORD_RE = re.compile(r"([A-Za-z]+)[\s(]*$")


def qualifier_years(text: Optional[str]) -> frozenset[int]:
    """The years ``text`` uses as time qualifiers: a four-digit year (1000 to 2199) after a temporal word ("in 2010",
    "during 1923", "between 1750 and 2023"), in parentheses ("(1974)"), as a table label ("2019: 5.0%") or in a span of
    years ("2019-20"). A four-digit count ("2000 people", "1,800 cakes") is no qualifier. Bounded and linear."""
    if not text:
        return frozenset()
    out: list[int] = []
    for m in _YEAR_TOKEN_RE.finditer(text[:4000]):
        before = text[max(0, m.start() - 24):m.start()]
        after = text[m.end():m.end() + 2]
        word = _PREV_WORD_RE.search(before)
        lead = word.group(1).lower() if word is not None else ""
        if (lead in _YEAR_LEAD_WORDS or (lead in ("and", "or") and out)
                or after[:1] in (":", ")", "-", "–", "/") or before.rstrip().endswith(("(", "-", "–", "/"))):
            out.append(int(m.group(1)))
    return frozenset(out)


def _symbol_year(meaning: Optional[str], label: Optional[str]) -> Optional[int]:
    """The one year that qualifies a symbol (its meaning's, else the premise label's): None when there is none or several
    (a period, not a point in time)."""
    years = qualifier_years(meaning) or qualifier_years(label)
    return next(iter(years)) if len(years) == 1 else None


#: Where a figure's clause ends for its year qualifier: a sentence stop or a semicolon followed by space (never a decimal
#: point), or a line break.
_QUALIFIER_CLAUSE_END_RE = re.compile(r"[.!?;](?=\s)|\n")


def _figure_clause(text: str, start: int, end: int) -> tuple[int, int]:
    """The clause of ``text`` that holds the figure at ``start``-``end`` for its year qualifier: within its sentence, from the
    previous clause end to the next ("2019: 5.0%. 2020: 8.0%." is two clauses)."""
    a, b = sentence_of(text, start, end)
    lo = a
    for m in _QUALIFIER_CLAUSE_END_RE.finditer(text, a, start):
        lo = m.end()
    m = _QUALIFIER_CLAUSE_END_RE.search(text, end, b)
    return lo, (m.start() if m is not None else b)


#: Separators that end the words a figure is stated for, within its clause ("Northtown had 300 and Southtown had 450").
_SUBJECT_BREAK_WORDS = frozenset({"and", "but", "while", "whereas", "whilst", "although", "though", "or"})


#: Words a figure's subject may hold that say nothing about what is counted: trend verbs, comparison words, units.
_FIGURE_FRAME_WORDS = frozenset("""
rose rise rises risen rising fell fall falls fallen falling grew grow grows grown growing increased increase increases increasing
decreased decrease decreases decreasing dropped drop drops declined decline declines doubled halved reached reach reaches was were is
are had has have stood stands total totalled totaled about around nearly almost roughly approximately exactly more less than at least
most over under per cent percent percentage points point by of to from in on for a an the its their there some
number numbers amount amounts value values quantity quantities level levels size count part parts question questions mark marks
answer item items step steps unit units figure figures
compared compare compares comparing comparison versus vs against contrast contrasted relative
""".split())


#: Capitalised words that are no name of what a figure is about (document references, months, days, the pronoun "I").
_NOT_NAMES = frozenset("""
text source figure table extract document passage graph chart appendix fig page section part i a the in on at by for from of to and
january february march april may june july august september october november december monday tuesday wednesday thursday friday
saturday sunday
""".split())


#: Units and scale words: they say how a figure is measured, never what is counted ("55 million tonnes" of imports and
#: "40 million tonnes" of exports share them; repair round 2, fidelity-1 variant). Compared by :func:`.lexis.root`.
_FIGURE_UNIT_WORDS = frozenset("""
tonne tonnes ton tons kilogram kilograms kg gram grams mg pound pounds lb lbs ounce ounces dollar dollars euro euros yen pence penny
cent cents metre metres meter meters kilometre kilometres kilometer kilometers km centimetre centimetres cm millimetre millimetres mm
mile miles foot feet inch inches yard yards litre litres liter liters ml gallon gallons barrel barrels acre acres hectare hectares
second seconds minute minutes hour hours mph kph watt watts kilowatt kilowatts joule joules kilojoule kilojoules calorie calories
volt volts amp amps ohm ohms newton newtons pascal pascals mole moles hertz degree degrees celsius kelvin
hundred hundreds thousand thousands million millions billion billions trillion trillions dozen bn mn
""".split())


_FIGURE_UNIT_ROOTS = frozenset(lexis.root(w) for w in _FIGURE_UNIT_WORDS)


#: A hyphenated name is one word of what is counted ("p-value", "t-test", "half-life", "chi-squared"): its parts alone are
#: a letter and a frame word ("p", "value"), which would leave the figure with no name of its quantity (repair round 2).
_HYPHEN_JOINERS = frozenset("-‐‑")


def _subject_tokens(text: str, a: int, b: int) -> list[tuple[int, int, str]]:
    """The tokens of ``text[a:b]`` (:func:`.lexis.token_spans`) with hyphenated words joined into one token ("p-value"),
    and a possessive read as its noun ("region's" is "region")."""
    out: list[tuple[int, int, str]] = []
    for s, e, tok in lexis.token_spans(text[a:b]):
        if out and s - out[-1][1] == 1 and text[a + s - 1] in _HYPHEN_JOINERS and tok.isalpha() and out[-1][2].replace("-", "").isalpha():
            ps, _pe, ptok = out.pop()
            out.append((ps, e, f"{ptok}-{tok}"))
            continue
        if tok.endswith("'s") and tok[:-2].isalpha():
            tok = tok[:-2]
        out.append((s, e, tok))
    return out


def _subject_root(tok: str) -> str:
    return "-".join(lexis.root(part) for part in tok.split("-")) if "-" in tok else lexis.root(tok)


def _subject_words(text: str, a: int, b: int) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """``(names, quantity words, openers)`` of ``text[a:b]``, each as ``{root: the word as written}``: the capitalised words
    that are no sentence opening and no :data:`_NOT_NAMES`; the other words that say what is counted (no number, no word of
    fewer than three letters, no :data:`_FIGURE_FRAME_WORDS`, which also holds the generic words "number", "amount", "part",
    "mark" and the comparison words "compared", "versus", "against", no unit or scale word (:data:`_FIGURE_UNIT_WORDS`) and no
    function word); and the capitalised words that open a sentence, which may be a name ("Hightown had 300 residents") or a
    common word ("Exports were 25 million dollars"): :func:`_subject_conflict` reads them against the other side (repair
    round 3, fidelity-1 variant). A hyphenated word is one word ("p-value": :func:`_subject_tokens`)."""
    names: dict[str, str] = {}
    roots: dict[str, str] = {}
    openers: dict[str, str] = {}
    for s, e, tok in _subject_tokens(text, a, b):
        raw = text[a + s:a + e]
        compound = "-" in tok
        if not compound and (tok in _NOT_NAMES or tok in _FIGURE_FRAME_WORDS or tok in lexis.FUNCTION_WORDS or not tok.isalpha() or len(tok) < 3):
            continue
        r = _subject_root(tok)
        if not compound and r in _FIGURE_UNIT_ROOTS:
            continue
        before = text[max(0, a + s - 3):a + s]
        opening = a + s == 0 or any(ch in ".!?\n" for ch in before)
        if raw[:1].isupper() and opening:
            openers.setdefault(r, raw)
        else:
            (names if raw[:1].isupper() else roots).setdefault(r, raw)
    return names, roots, openers


def _figure_subject(text: str, figure, figures: Sequence[Any]) -> tuple[int, int]:
    """The characters a figure is stated for: its clause (:func:`_figure_clause`), cut at the nearest separator word, clause
    mark or other figure on each side ("In 2020 Northtown had 300 residents and Southtown had 450": "Southtown had" for
    450)."""
    a, b = _figure_clause(text, figure.start, figure.end)
    lo, hi = a, b
    for f in figures:
        if f.end <= figure.start and f.end > lo and f.start >= a:
            lo = f.end
        if f.start >= figure.end and f.start < hi and f.end <= b:
            hi = f.start
    left = text[lo:figure.start]
    cut = max((m.end() for m in re.finditer(r"[,;:]|\b(?:" + "|".join(sorted(_SUBJECT_BREAK_WORDS)) + r")\b", left, re.IGNORECASE)), default=0)
    right = text[figure.end:hi]
    m = re.search(r"[,;:]|\b(?:" + "|".join(sorted(_SUBJECT_BREAK_WORDS)) + r")\b", right, re.IGNORECASE)
    return lo + cut, figure.end + (m.start() if m else len(right))


class _Bounds:
    """A figure's position only (what :func:`_figure_subject` reads)."""
    __slots__ = ("start", "end")

    def __init__(self, start: int, end: int) -> None:
        self.start, self.end = start, end


#: How far up a table row looks for its header line, and the longest line read as a table row.
_TABLE_REACH_LINES = 200


_TABLE_LINE_CHARS = 2000


def _cells(line: str) -> list[tuple[int, int]]:
    """The ``(start, end)`` of each cell of a pipe-table line, relative to the line; a leading or trailing bar opens or
    closes the row and makes no empty cell."""
    bars = [i for i, ch in enumerate(line) if ch == "|"]
    edges = [-1, *bars, len(line)]
    cells = [(edges[k] + 1, edges[k + 1]) for k in range(len(edges) - 1)]
    if cells and not line[cells[0][0]:cells[0][1]].strip():
        cells = cells[1:]
    if cells and not line[cells[-1][0]:cells[-1][1]].strip():
        cells = cells[:-1]
    return cells


def _table_cell(text: str, start: int, end: int) -> Optional[tuple[int, int, str]]:
    """``(cell start, cell end, label)`` when the figure at ``start``-``end`` stands in a cell of a pipe table: the label is
    its row's first cell and its column's header (the table's first line that is no rule), joined by a unit separator, the
    words a table states the figure for ("2020 | 40 | 55" under "Year | Exports | Imports": 40 is "2020 Exports"; repair round 5, rerun-fidelity-1
    variant: a figure in a table row was read with no subject, so it verified a premise about another column). None
    when the line is no table row or no header is found."""
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    le = len(text) if le < 0 else le
    line = text[ls:le]
    if "|" not in line or le - ls > _TABLE_LINE_CHARS:
        return None
    cells = _cells(line)
    idx = next((k for k, (a, b) in enumerate(cells) if ls + a <= start and end <= ls + b), None)
    if idx is None:
        return None
    header: Optional[str] = None
    pos = ls - 1
    for _ in range(_TABLE_REACH_LINES):
        if pos <= 0:
            break
        ps = text.rfind("\n", 0, pos) + 1
        prev = text[ps:pos]
        if "|" not in prev or pos - ps > _TABLE_LINE_CHARS:
            break
        if not re.fullmatch(r"[\s|:+-]*", prev):
            header = prev
        pos = ps - 1
    if header is None:
        return None
    head_cells = _cells(header)
    if idx >= len(head_cells) or len(head_cells) != len(cells):
        return None
    column = header[head_cells[idx][0]:head_cells[idx][1]].strip()
    row = line[cells[0][0]:cells[0][1]].strip() if idx > 0 else ""
    return (ls + cells[idx][0], ls + cells[idx][1], f"{row}\x1f{column}") if column else None


def _figure_subject_words(text: str, figure, figures: Sequence[Any]) -> tuple[int, int, dict[str, str], dict[str, str], dict[str, str], str]:
    """``(subject start, subject end, names, quantity words, openers, subject text)`` of one figure: the words of its clause
    (:func:`_figure_subject`), or for a figure in a pipe table its row label and column header (:func:`_table_cell`)."""
    cell = _table_cell(text, figure.start, figure.end) if "|" in text else None
    if cell is not None:
        a, b, label = cell
        row, _sep, column = label.rpartition("\x1f")
        # the column header names what is counted (title case by convention): its words are quantity words; the row label
        # is read as prose (a place's name stays a name)
        names, roots, openers = _subject_words(row, 0, len(row)) if row else ({}, {}, {})
        _cn, column_roots, _co = _subject_words(column.casefold(), 0, len(column))
        shown = f"{row} {column}".strip()
        return a, b, names, {**roots, **column_roots}, openers, shown
    a, b = _figure_subject(text, figure, figures)
    names, roots, openers = _subject_words(text, a, b)
    return a, b, names, roots, openers, text[a:b]


@lru_cache(maxsize=64)
def _subject_table(text: str, bounds: tuple[tuple[int, int], ...]) -> dict[tuple[int, int], tuple[int, int, dict[str, str], dict[str, str], dict[str, str], str]]:
    """``(start, end) -> (subject start, subject end, names, quantity words, openers, subject text)`` for every figure of a
    record, read once per record (repair round 2, ADV2-03: each figure match read every figure's subject again)."""
    figs = [_Bounds(a, b) for a, b in bounds]
    return {(f.start, f.end): _figure_subject_words(text, f, figs) for f in figs}


def _effective_words(names: dict[str, str], roots: dict[str, str], openers: dict[str, str], other_words: set[str]) -> tuple[dict[str, str], dict[str, str]]:
    """``(names, quantity words)`` of one side of the same-subject rule, a sentence opener read against the other side: a
    capitalised opener that the other side uses as an ordinary word ("Exports were 25" against "Ruritania's exports") is a
    quantity word, any other is a name ("Hightown had 300 residents" against "Lowtown residents")."""
    names = dict(names)
    roots = dict(roots)
    for r, raw in openers.items():
        if r in other_words or r in roots:
            roots.setdefault(r, raw)
        else:
            names.setdefault(r, raw)
    return names, roots


def _year_figure(figure) -> bool:
    """A figure that is a bare year ("2023"): it dates other figures and states no quantity of its own here."""
    written = (getattr(figure, "written", "") or "").strip()
    return len(written) == 4 and written.isdecimal() and 1000 <= int(written) <= 2199


#: Function words an abbreviation's letters skip ("price elasticity OF demand" is PED).
_INITIALS_SKIP = frozenset({"of", "and", "the", "in", "for", "to", "on", "at", "a", "an", "&"})


def _initials_of(word: str, text: str) -> bool:
    """Whether ``word`` is an abbreviation (two to six capital letters, an optional plural ``s``) whose letters are the
    initials of a run of consecutive words of ``text`` (bounded by the caller), function words skipped: "PED" in "the
    price elasticity of demand", "GDP" in "gross domestic product"."""
    letters = word[:-1] if len(word) > 2 and word.endswith("s") and word[:-1].isupper() else word
    if not (2 <= len(letters) <= 6 and letters.isalpha() and letters.isupper()):
        return False
    words = [t for t in lexis.tokens(text[:2000]) if t.isalpha()]
    want = letters.lower()
    for i in range(len(words)):
        k, j = 0, i
        while j < len(words) and k < len(want):
            w = words[j]
            if w[0] == want[k]:
                k += 1
            elif w not in _INITIALS_SKIP or k == 0:
                break
            j += 1
        if k == len(want):
            return True
    return False


#: Qualifiers that name opposite parts of what is counted (a period before or after an event, one sex or the other, the
#: least or the most): a figure stated for one is not stated for the other ("3 of the 12 games before the change" for the
#: games won after it: repair round 3, fidelity-1 class, the time dimension beyond the year).
OPPOSED_QUALIFIERS: tuple[tuple[str, str], ...] = (
    ("before", "after"), ("earlier", "later"), ("previous", "next"), ("prior", "after"), ("pre", "post"), ("start", "end"),
    ("beginning", "end"), ("men", "women"), ("male", "female"), ("boys", "girls"), ("minimum", "maximum"), ("lowest", "highest"),
    ("morning", "evening"), ("first", "last"),
)


def _opposed_qualifier(subject: str, about: str) -> Optional[tuple[str, str]]:
    """``(the subject's qualifier, the premise's)`` when the words a figure is stated for hold one member of a pair of
    :data:`OPPOSED_QUALIFIERS` and the premise's meaning holds the other (and neither holds both), else None."""
    st, at = set(lexis.tokens(subject or "")), set(lexis.tokens(about or ""))
    for x, y in OPPOSED_QUALIFIERS:
        for mine, theirs in ((x, y), (y, x)):
            if mine in st and theirs not in st and theirs in at and mine not in at:
                return mine, theirs
    return None


def _subject_conflict(lit: _Literal, text: Optional[str], figure, figures: Sequence[Any]) -> Optional[str]:
    """Why the figure is not stated for ``lit``'s quantity (re-run review, fidelity-1 variant), or None: the words it is
    stated for (:func:`_figure_subject`) name something the premise does not and the premise names something they do not
    ("Southtown had 450 residents" for Northtown's count), or they say what is counted in words the premise shares none
    of, while the record states the premise's quantity for another figure ("prices rose by 12 per cent" for the rise in
    wages, when the record gives wages their own figure). A synonym the record uses for nothing else ("inhabitants" for
    "population") is no conflict. Another figure counts only when its words are its own: when the two figures stand in one
    clause with no separator between them ("A test at the 5% significance level gives a p-value of 0.0312"), the words
    before both are the subject of both, and the premise's word "test" is no reason to give 0.0312 to the 5% figure
    (repair round 2). A figure of the same value and unit is no other figure: the record then states the premise's quantity
    with this very figure (close round 1, arena run1 ec-e1: a table cell repeating "$1.60" refuted the excerpt that states it)."""
    if text is None or not lit.about:
        return None
    table = _subject_table(text, tuple((f.start, f.end) for f in figures))
    own = table.get((figure.start, figure.end))
    a, b, names, roots, openers, subject = own if own is not None else _figure_subject_words(text, figure, figures)
    # the words before the figure in its subject: a list's head ("Freedonia exported 30 tonnes of wheat, 45 tonnes of
    # barley"), which every item of the list shares
    in_prose = subject == text[a:b]  # a table cell's subject is its row label and column header, not text around it
    head_roots = set(_subject_words(text, a, figure.start)[1]) if in_prose and a < figure.start else set()
    mine_names, mine_roots, mine_openers = _subject_words(lit.about, 0, len(lit.about))
    # a sentence opener is a name or a word by what the other side says (repair round 3, fidelity-1 variant: "Hightown had 300
    # residents" was read with no name, so it grounded Lowtown's count; "Ruritania" opening the premise's meaning was read as a
    # quantity word, so the record's "Ruritania's imports" shared a word with "Ruritania exports")
    names, roots = _effective_words(names, roots, openers, set(mine_roots) | set(mine_names) | set(mine_openers))
    mine_names, mine_roots = _effective_words(mine_names, mine_roots, mine_openers, set(roots) | set(names))
    mine_roots = {k: v for k, v in mine_roots.items() if k not in mine_names and k not in names}
    roots = {k: v for k, v in roots.items() if k not in names and k not in mine_names}
    # the words after the figure up to its clause's end qualify it too ("3 of the 12 games before the change"); a clause that
    # names both qualifiers ("4 before the change and 6 after it") names neither alone. The words before it in its clause,
    # back to the previous figure, qualify it as well, whatever comma stands between ("Before the reform, 120 pupils
    # attended": repair round 5, rerun-fidelity-1 variant)
    tail = re.split(r"[,;:.!?()]", text[figure.end:figure.end + 160], maxsplit=1)[0]
    ca, _cb = _figure_clause(text, figure.start, figure.end)
    lead_from = max([ca] + [f.end for f in figures if f.end <= figure.start and f.end > ca])
    lead = text[lead_from:figure.start][-200:] if in_prose and lead_from < a else ""
    opposed = _opposed_qualifier(lead + " " + subject + " " + tail, lit.about)
    if opposed is not None:
        return (f"{figure.where()} is stated for what is '{opposed[0]}' ({subject.strip()[:120]!r}), not for what is '{opposed[1]}', which the "
                f"premise is about, so it does not state {lit.symbol}")
    # an abbreviation is the name of the quantity, not of another thing: "PED" for "the price elasticity of demand", "GDP"
    # for "gross domestic product" (repair round 2, holdout2 class: a premise about the PED was refused the record's figure)
    mine_names = {k: v for k, v in mine_names.items() if k not in roots and not _initials_of(v, subject)}
    names = {k: v for k, v in names.items() if not _initials_of(v, lit.about)}
    if names and mine_names and not (names.keys() & mine_names.keys()) and not (mine_names.keys() & roots.keys()):
        return (f"{figure.where()} is stated for {', '.join(sorted(names.values()))} ({subject.strip()[:120]!r}), not for "
                f"{', '.join(sorted(mine_names.values()))}, which the premise is about, so it does not state {lit.symbol}")
    # what tells the premise's quantity from the figure's: the words only one side has ("inflation" against "unemployment" when
    # both say "rate"; repair round 4, fidelity-1 same-sentence variant)
    common = set(mine_roots) & set(roots)
    mine_only = set(mine_roots) - set(roots)
    distinct = bool(mine_only) and bool(set(roots) - set(mine_roots))
    if roots and mine_roots and (not common or distinct):
        wanted = set(mine_roots) if not common else mine_only
        for f in figures:
            if (f.start, f.end) == (figure.start, figure.end) or _year_figure(f):
                continue
            if f.scaled == figure.scaled and f.unit_factor == figure.unit_factor and f.currency == figure.currency:
                # the record states the premise's quantity with this same figure elsewhere ("Average price per litre | $1.60"
                # beside "a litre ... sold for $1.60 on average"): it gives the quantity no other figure (close round 1)
                continue
            fa, fb, _n, other, other_openers, other_subject = table[(f.start, f.end)]
            if fa < b and a < fb:
                continue  # the two subjects overlap: no separator divides the clause between the figures
            if _opposed_qualifier(other_subject, lit.about) is not None:
                continue  # stated for the opposite part ("After the tax" for a premise about the price before it): not its quantity
            other = {**other, **{k: v for k, v in other_openers.items() if k in mine_roots}}
            shared = sorted(mine_roots[k] for k in other.keys() & wanted)
            # an item of a list shares the list's head ("exported" in "Freedonia exported 30 tonnes of wheat, 45 tonnes of
            # barley"): the head's words count for every item (repair round 5, rerun-fidelity-1 variant)
            common_own = common - head_roots if fa > b else common
            # with words in common, the other figure must carry every word that tells the premise's quantity apart, and the
            # words of the quantity the premise shares with this figure too: it states the same kind of quantity for another
            # thing ("its unemployment rate was 7" against "Freedonia's inflation rate was 4"). An owner the premise names that
            # another figure's clause also holds is no such quantity ("the firm's revenue target" against "The firm sold 120
            # units ... and had set a revenue target of $900": 120 counts units, not a target; repair round 4)
            if shared and (wanted == set(mine_roots) or (wanted <= other.keys() and common_own <= other.keys())):
                return (f"{figure.where()} is stated for {', '.join(sorted(roots.values()))} ({subject.strip()[:120]!r}); the record states "
                        f"{', '.join(shared)}, which the premise is about, with another figure ({f.where()}), so it does not state {lit.symbol}")
    return None


def _literals(expr, symbols: dict[str, Symbol], label: Optional[str] = None) -> list[_Literal]:
    """The non-trivial numeric literals of ``expr`` (integers, decimals and fractions alike: one value, one figure), each
    with the reading the symbol it is directly compared with declares (``tax_rate = 0.2`` with ``tax_rate`` declared
    dimensionless). Zero, one and the powers of ten a percentage or conversion brings in are no figures of a relation. For an
    assignment (:func:`.relations.assignment_parts`) every literal is the figure itself (``k = 10`` for "10 km"), and
    carries the comparison its conjunct states about its symbol."""
    parts = assignment_parts(expr)
    if parts is not None:
        out_a: list[_Literal] = []
        for name, required, node in parts:
            lit = node.arg if getattr(node, "op", None) == "neg" else node  # type: ignore[attr-defined]
            try:
                value = Fraction(lit.value)  # type: ignore[attr-defined]
            except (ValueError, ZeroDivisionError):
                continue
            if getattr(node, "op", None) == "neg":
                value = -value
            # a literal an assignment compares directly with its symbol is the figure itself, trivial or not ("10 km": k = 10)
            sym = symbols.get(name)
            written = lit.value if getattr(node, "op", None) != "neg" else f"-{lit.value}"  # type: ignore[attr-defined]
            out_a.append(_Literal(written, value, declared_reading(sym.meaning if sym is not None else None), name, required,
                                  _symbol_year(sym.meaning if sym is not None else None, label),
                                  " ".join(x for x in ((sym.meaning if sym is not None else None), label) if x)[:2000],
                                  ((sym.meaning if sym is not None else None) or "")[:1000]))
        return out_a
    out: list[_Literal] = []
    stack: list[tuple[object, Optional[str]]] = [(expr, None)]
    lookups: dict[int, _Lookup] = {}  # id of an index literal -> the lookup whose position it is
    in_chain: set[int] = set()  # ids of the conditionals of a lookup read whole (a tail of the chain is no lookup of its own)
    while stack:
        node, compared = stack.pop()
        op = getattr(node, "op", None)
        if op in ("int", "real"):
            try:
                value = Fraction(node.value)  # type: ignore[attr-defined]
            except (ValueError, ZeroDivisionError):
                continue
            if abs(value) in TRIVIAL_VALUES:
                continue
            sym = symbols.get(compared) if compared else None
            out.append(_Literal(node.value, value, declared_reading(sym.meaning if sym is not None else None), compared,  # type: ignore[attr-defined]
                                lookup=lookups.get(id(node))))
            continue
        if op == "ite" and id(node) not in in_chain:
            pairs, chain = _index_lookup(node)
            in_chain.update(id(c) for c in chain)
            for index_node, lookup in pairs:
                lookups[id(index_node)] = lookup
        if op in ("eq", "ne", "lt", "le", "gt", "ge"):
            left, right = node.left, node.right  # type: ignore[attr-defined]
            lname = left.name if getattr(left, "op", None) == "var" else None
            rname = right.name if getattr(right, "op", None) == "var" else None
            stack.append((left, rname))
            stack.append((right, lname))
            continue
        if op == "div" and _counts_addends(node):
            stack.append((node.left, None))  # type: ignore[attr-defined]
            continue  # the divisor of a mean counts the terms it divides ("(1200 + 1180 + 1150) / 3"): no figure of a record
        for key in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(node, key, None)
            if child is not None:
                stack.append((child, None))
        stack.extend((a, None) for a in (getattr(node, "args", None) or ()))
    return out


#: The fewest values an indexed lookup reads as positions of a list (:func:`_index_lookup`), as a list holds (:data:`_MIN_LIST_ITEMS`).
_MIN_LOOKUP_VALUES = 3


#: The longest lookup chain read (branches).
_MAX_LOOKUP_VALUES = 400


def _literal_value(node) -> Optional[Fraction]:
    op = getattr(node, "op", None)
    if op == "neg":
        inner = _literal_value(getattr(node, "arg", None))
        return -inner if inner is not None else None
    if op not in ("int", "real"):
        return None
    try:
        return Fraction(node.value)  # type: ignore[attr-defined]
    except (ValueError, ZeroDivisionError):
        return None


def _index_lookup(node) -> tuple[list[tuple[Any, _Lookup]], list[Any]]:
    """The index literals of an indexed lookup, each with its :class:`_Lookup`: a chain ``ite(v = b, x_b, ite(v = b + 1,
    x_{b+1}, ..., x_last))`` that compares one variable with consecutive whole positions from ``b`` (0 or 1) and whose
    values are literals (the item a trace reads at a position: "items[mid]" over "scores = [3, 8, 12, ...]"). The positions
    are not figures a record must state when the values are, in order, a list a record states (:func:`_position_source`;
    repair round 4, E2E-CS). Also the chain's conditionals, which are read with it. Empty for any other shape."""
    var: Optional[str] = None
    indices: list[Any] = []
    values: list[Fraction] = []
    chain: list[Any] = []
    cur = node
    while getattr(cur, "op", None) == "ite" and len(indices) < _MAX_LOOKUP_VALUES:
        cond = getattr(cur, "cond", None)
        if getattr(cond, "op", None) != "eq":
            return [], []
        left, right = cond.left, cond.right  # type: ignore[union-attr]
        if getattr(left, "op", None) == "var" and getattr(right, "op", None) == "int":
            name, index = left.name, right
        elif getattr(right, "op", None) == "var" and getattr(left, "op", None) == "int":
            name, index = right.name, left
        else:
            return [], []
        if var is not None and name != var:
            return [], []
        var = name
        value = _literal_value(getattr(cur, "then", None))
        if value is None:
            return [], []
        indices.append(index)
        values.append(value)
        chain.append(cur)
        cur = getattr(cur, "otherwise", None)
    default = _literal_value(cur)
    if getattr(cur, "op", None) == "ite" or len(values) + (default is not None) < _MIN_LOOKUP_VALUES:
        return [], []
    try:
        base = Fraction(indices[0].value)
        if base not in (0, 1) or any(Fraction(ix.value) != base + k for k, ix in enumerate(indices)):
            return [], []
    except (ValueError, ZeroDivisionError):
        return [], []
    with_default = (*values, default) if default is not None else tuple(values)
    return [(ix, _Lookup(tuple(values), with_default, int(base), k)) for k, ix in enumerate(indices)], chain


def _counts_addends(node) -> bool:
    """A division of a sum by a literal equal to the number of its terms: the mean of the terms (re-run review
    A-FA-POOLED: the "3" of "(1200 + 1180 + 1150) / 3" is the count of the months, not a figure a record must state)."""
    left, right = getattr(node, "left", None), getattr(node, "right", None)
    if getattr(left, "op", None) != "add" or getattr(right, "op", None) not in ("int", "real"):
        return False
    try:
        return Fraction(right.value) == len(left.args)  # type: ignore[union-attr]
    except (ValueError, ZeroDivisionError):
        return False


#: At most this many answer texts, and characters of each, are read for written calculations.
_MAX_ANSWER_TEXTS = 64


_MAX_ANSWER_CHARS = 20_000


#: Constants of unit conversion a written calculation may use beside the records' figures (seconds in a minute, minutes in an
#: hour, hours in a day, days in a week and a year, months and weeks in a year): "4 min 30 s = (4 × 60 + 30) s = 270 s".
CONVERSION_CONSTANTS = frozenset({Fraction(60), Fraction(3600), Fraction(24), Fraction(7), Fraction(12), Fraction(52), Fraction(365)})


def _operand_reading(g) -> DeclaredReading:
    """The reading an operand's own unit declares ("2200 W" is read in watts), so it matches a record's figure in another
    unit of that dimension ("2.2 kW")."""
    if g.unit_factor and g.unit_dim and not g.is_percent_like:
        return DeclaredReading("unit", factor=g.unit_factor, dim=g.unit_dim, text=g.written)
    return DeclaredReading("none")


#: The signs a written result follows; the words that state one after a comma ("…, which is 2.050511…").
_RESULT_SIGNS = "=≈≃≅"


_RESULT_WORDS_RE = re.compile(r"(?:,\s*|\s+)(?:which|that)\s+is(?:\s+(?:about|approximately|roughly))?\s*$", re.IGNORECASE)


#: A trailing ellipsis: the figure is a truncated value of a computation ("2.050511…", "0.693147...", LaTeX "\ldots"); no
#: datum is written so.
_ELLIPSIS_AFTER_RE = re.compile(r"\s?(?:…|\.\.\.(?!\.)|\\l?dots\b)")


#: What makes a member of a chain a calculation once its figures are masked: an operator between operands, a power of a
#: number or a bracket, a root, a function, the constant e raised to a power. A unit's power ("m s⁻²") is none.
_CALC_MARK_RE = re.compile(
    r"[0)…]\s*[-+−–×*·⋅÷/]\s*[0(√]|\^|[0)][⁰¹²³⁴⁵⁶⁷⁸⁹]|[√∛∜]"
    r"|\b(?:ln|log|lg|exp|sin|cos|tan|sqrt)\b|(?<![A-Za-z])e(?=\^|[ᵏⁿˣᵗ⁽⁰¹²³⁴⁵⁶⁷⁸⁹])")


#: After a figure the expression goes on: an operator before an operand, or a letter, bracket or power glued to the figure
#: (implicit multiplication: "250e^(6k)", "5(2 × 3)").
_GOES_ON_RE = re.compile(r"\s*[-+−–×*·⋅÷/^]\s*[\d(.A-Za-z√π]|[A-Za-z(√π^⁰¹²³⁴⁵⁶⁷⁸⁹]")


#: Where a member of a chain begins, read back from its sign: another sign, a clause mark (also ", "), a sentence end.
_MEMBER_STOPS = frozenset("=≈≃≅:;\n")


_MEMBER_MAX_CHARS = 240


#: A symbol's meaning that names a date: a year literal compared with it identifies a time, it states no quantity.
_DATE_MEANING_RE = re.compile(r"\b(?:year|years|date|dated|dates)\b", re.IGNORECASE)


def _result_member(text: str, figure) -> Optional[str]:
    """The member of written working whose result ``figure`` is stated as, or None. The figure follows a result sign
    (``= ≈ ≃ ≅``) or ", which is"; it ends the expression (no operator, bracket or letter carries it on: "= 2.084429… +
    18.420681…" states no result at 2.084429); and the member, read back from the sign to the previous sign, a clause mark
    or a sentence end (a line that opens with the sign continues the line before: "= $0.60 × 45 million litres\\n= $27
    million"), is a calculation once its figures are masked (:data:`_CALC_MARK_RE`): "k = 2.05" and "P(6) = 250" state no
    result."""
    j = figure.start - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j >= 0 and text[j] in _RESULT_SIGNS:
        sign = j
    else:
        lo = max(0, figure.start - 40)
        m = _RESULT_WORDS_RE.search(text, lo, figure.start)
        if m is None or m.end() != figure.start:
            return None
        sign = m.start()
    after = figure.end
    e = _ELLIPSIS_AFTER_RE.match(text, after)
    if e is not None:
        after = e.end()
    if _GOES_ON_RE.match(text, after) is not None:
        return None
    k = sign - 1
    while k >= 0 and text[k] in " \t":
        k -= 1
    if k >= 0 and text[k] == "\n":  # the sign opens its line: the member is the end of the line before
        k -= 1
        while k >= 0 and text[k] in " \t\r":
            k -= 1
    end = k + 1
    start = end - 1
    floor = max(0, end - _MEMBER_MAX_CHARS)
    while start >= floor:
        ch = text[start]
        if ch in _MEMBER_STOPS or (ch == "," and start + 1 < len(text) and text[start + 1] == " "):
            break
        if ch in ".?!" and start + 1 < len(text) and text[start + 1] in " \n" and not (ch == "." and start > 0 and text[start - 1].isdigit()):
            break
        start -= 1
    if start < floor and floor > 0:
        return None  # a member longer than the reader reads
    member = text[start + 1:end]
    masked = list(member)
    has_figure = False
    for g in figures_in(SourceText("claim", "member", member)):
        has_figure = True
        fill = "0/0" if "/" in g.numeral else "0"
        masked[g.start:g.end] = [fill] + [""] * (g.end - g.start - 1)
    if not has_figure or _CALC_MARK_RE.search("".join(masked)) is None:
        return None
    return member


def _anchored_operands(member: str, record_figures: Sequence[Any], results: Sequence[Any]) -> bool:
    """Whether every figure of ``member`` is anchored: stated by a record (in its own unit), trivial (0, 1, 10, 100, 1000), a
    constant of unit conversion, a result of earlier working, a date, or written with a trailing ellipsis (a truncated value
    the working computed; no datum is written so). A fraction ("3465/250") is read as its two parts."""
    for g in figures_in(SourceText("claim", "member", member)):
        if g.word or is_year_like(g) or _ELLIPSIS_AFTER_RE.match(member, g.end) is not None:
            continue
        if "/" in g.numeral:
            try:
                parts = [abs(Fraction(p.replace(",", "").replace(" ", ""))) for p in g.numeral.split("/", 1)]
            except (ValueError, ZeroDivisionError):
                return False
            reading = DeclaredReading("none")
        else:
            parts, reading = [abs(g.value)], _operand_reading(g)
        for v in parts:
            if v in TRIVIAL_VALUES or v in CONVERSION_CONSTANTS:
                continue
            if literal_matches(v, record_figures, reading)[0] or literal_matches(v, results, reading)[0]:
                continue
            return False
    return True


@lru_cache(maxsize=64)
def _worked_results(texts: tuple[str, ...], records: tuple[tuple[str, str, str], ...]) -> tuple[tuple[Any, str, str], ...]:
    record_figures = [f for kind, ident, text in records for f in figures_in(SourceText(kind, ident, text))]  # type: ignore[arg-type]
    out: list[tuple[Any, str, str]] = []
    results: list[Any] = []
    for k, text in enumerate(texts[:_MAX_ANSWER_TEXTS]):
        body = (text or "")[:_MAX_ANSWER_CHARS]
        lowered = body.lower()
        if not any(s in body for s in _RESULT_SIGNS) and "which is" not in lowered and "that is" not in lowered:
            continue
        for f in figures_in(SourceText("claim", f"work-{k}", body)):
            if f.word or is_year_like(f):
                continue
            member = _result_member(body, f)
            if member is None or not _anchored_operands(member, record_figures, results):
                continue
            out.append((f, body, member.strip()))
            results.append(f)
    return tuple(out)


def worked_results(texts: Sequence[str], records: Sequence[SourceText]) -> tuple[tuple[Any, str, str], ...]:
    """``(figure, the text it stands in, its member)`` for every figure a text of the answer's working states as a WORKED
    RESULT (:func:`_result_member`) whose operands are anchored (:func:`_anchored_operands`), read in text order so a chain
    of steps anchors each result in the one before. The reading is wider than :func:`answer_derived_figures` (a function, a
    power, an ellipsis, a chain over lines, ", which is"), because it decides no grounding: it says only that the answer
    works a figure out rather than introducing it (the evidence rules EVD-FIG-001 and EVD-LACK-001). Whether the working is
    right is the arithmetic checks' business. Nothing is evaluated."""
    return _worked_results(tuple(texts), tuple((r.kind, r.ident, r.text) for r in records))


@dataclass(frozen=True)
class FigureSupport:
    """How the figure(s) an assignment gives one symbol are supported (:func:`assignment_support`). ``status``:
    ``date`` (a year the symbol's meaning names as a date: it identifies a time and states no quantity), ``stated`` (a
    record states it: its value, or an end of the interval a record's figure states at its written precision),
    ``answer_stated`` (the answer's figure that the assignment encodes is stated by a record), ``worked`` (that figure is
    a worked result of the answer's working), ``not_in_answer`` (no record states it and no figure of the answer encodes
    it: the translation's own figure, not the answer's), ``introduced`` (the answer writes it, and no record states it and
    no working derives it). ``same_subject`` is False when the only record that states it states it for another subject
    (the same-subject rule of the figure checks)."""
    written: tuple[str, ...]
    status: Literal["date", "stated", "answer_stated", "worked", "not_in_answer", "introduced"]
    answer_figure: Optional[str] = None
    same_subject: bool = True


@lru_cache(maxsize=4096)
def _enclosures(f, text: str, declared: DeclaredReading, truncated: bool) -> tuple[tuple[Fraction, Fraction], ...]:
    """The intervals figure ``f`` states at its written precision in ``text``: those of its wording
    (:func:`.quantities.written_precision_intervals`), the half-unit enclosure of its last written place, and, for a figure
    written with a trailing ellipsis, the truncation interval [value, value + one unit); each in the reading's units. A
    pure function of immutable inputs, cached (repair round 5, ADV5-13: every bound premise asks it of every answer
    figure)."""
    return tuple(_enclosure_list(f, text, declared, truncated))


def _enclosure_list(f, text: str, declared: DeclaredReading, truncated: bool) -> list[tuple[Fraction, Fraction]]:
    out = [(lo, hi) for (lo, hi, _li, _hi), _m, _ex in written_precision_intervals(f, text, declared)]
    centres = {abs(f.value), abs(f.scaled)}
    if f.is_percent_like:
        centres.add(abs(f.scaled) * (f.unit_factor or Fraction(1, 100)))
    if declared.kind == "unit" and f.unit_factor is not None and f.unit_dim == declared.dim and declared.factor:
        centres.add(abs(f.scaled) * f.unit_factor / declared.factor)
    for c in centres:
        factor = c / abs(f.value) if f.value else Fraction(1)
        h = f.half_width * factor
        if not h:
            continue
        out.append((c - h, c + h))
        if truncated:
            out.append((c, c + 2 * h))
    return out


def _group_encodes(group: list[_Literal], f, text: str, truncated: bool) -> bool:
    """Whether one symbol's literals encode figure ``f``: an equality its value (in the symbol's declared reading), a bound
    its value or an end of an interval it states, two bounds an interval inside one it states."""
    declared = group[0].declared
    if len(group) == 1 and literal_matches(group[0].value, [f], declared)[0]:
        return True
    if not all(lit.required in _LOWER_BOUNDS + _UPPER_BOUNDS for lit in group):
        return False
    lows = [abs(lit.value) for lit in group if lit.required in _LOWER_BOUNDS]
    highs = [abs(lit.value) for lit in group if lit.required in _UPPER_BOUNDS]
    for lo, hi in _enclosures(f, text, declared, truncated):
        if len(group) == 1:
            if abs(group[0].value) in (lo, hi):
                return True
        elif lows and highs and lo <= min(lows) and max(highs) <= hi and min(lows) <= max(highs):
            return True
    return False


def assignment_support(expr, symbols: dict[str, Symbol], label: Optional[str], records: Sequence[SourceText],
                       answer_texts: Sequence[str]) -> Optional[list[FigureSupport]]:
    """How each figure an assignment premise gives a symbol is supported (:class:`FigureSupport`), or None for a premise that
    is no assignment. ``records`` are the supplied texts and the task record; ``answer_texts`` the answer's own texts (the
    claim, its supporting claims, the whole response). Trivial values (0, 1, 10, 100, 1000) are left out. Read as data,
    bounded by the readers' limits; nothing is evaluated."""
    if assignment_parts(expr) is None:
        return None
    literals = [lit for lit in _literals(expr, symbols, label) if lit.symbol is not None and abs(lit.value) not in TRIVIAL_VALUES]
    groups: dict[str, list[_Literal]] = {}
    for lit in literals:
        groups.setdefault(lit.symbol, []).append(lit)  # type: ignore[arg-type]
    record_figures = [f for r in records for f in figures_in(r)]
    texts = {(r.kind, r.ident): r.text for r in records}
    answer = [t for t in dict.fromkeys(answer_texts) if t][:_MAX_ANSWER_TEXTS]
    answer_figures: Optional[list[tuple[Any, str, bool]]] = None
    worked: Optional[tuple[tuple[Any, str, str], ...]] = None
    out: list[FigureSupport] = []
    for name, group in groups.items():
        written = tuple(lit.written for lit in group)
        if all(lit.value.denominator == 1 and 1000 <= abs(lit.value) <= 2199 for lit in group) and _DATE_MEANING_RE.search(group[0].meaning or ""):
            out.append(FigureSupport(written, "date"))
            continue
        stating = [f for lit in group for m in literal_matches(lit.value, record_figures, lit.declared)[0] for f in (m.figure,)] if len(group) == 1 else []
        if not stating and all(lit.required in _LOWER_BOUNDS + _UPPER_BOUNDS for lit in group):
            ends = _tolerance_ends(group, record_figures, texts)
            if len(ends) == len(group):
                out.append(FigureSupport(written, "stated"))
                continue
        if stating:
            same = any(_subject_conflict(group[0], texts.get((f.source_kind, f.source_id)), f, figures_in(SourceText(f.source_kind, f.source_id, texts.get((f.source_kind, f.source_id), "")))) is None
                       for f in stating[:8])
            out.append(FigureSupport(written, "stated", same_subject=same))
            continue
        if answer_figures is None:
            answer_figures = []
            for k, text in enumerate(answer):
                body = text[:_MAX_ANSWER_CHARS]
                for f in figures_in(SourceText("claim", "answer", body)):
                    if not f.word:
                        answer_figures.append((f, body, _ELLIPSIS_AFTER_RE.match(body, f.end) is not None))
        mine = [(f, body) for f, body, truncated in answer_figures if _group_encodes(group, f, body, truncated)]
        if not mine:
            out.append(FigureSupport(written, "not_in_answer"))
            continue
        status, shown, same = "introduced", mine[0][0].written, True
        for f, _body in mine:
            reading = _operand_reading(f)
            matches = literal_matches(abs(f.scaled), record_figures, reading)[0] or literal_matches(abs(f.value), record_figures, reading)[0]
            if matches:
                g = matches[0].figure
                same = _subject_conflict(group[0], texts.get((g.source_kind, g.source_id)), g,
                                         figures_in(SourceText(g.source_kind, g.source_id, texts.get((g.source_kind, g.source_id), "")))) is None
                status, shown = "answer_stated", f.written
                break
            if worked is None:
                worked = worked_results(answer, records)
            if any(literal_matches(abs(w.value), [f], DeclaredReading("none"))[0] for w, _t, _m in worked):
                status, shown = "worked", f.written
                break
        out.append(FigureSupport(written, status, shown, same))  # type: ignore[arg-type]
    return out


_LOWER_BOUNDS = ("ge", "gt")


_UPPER_BOUNDS = ("le", "lt")


def _end_establishes(bounds: tuple[Fraction, Fraction, bool, bool], lit: _Literal) -> bool:
    """Whether the interval ``bounds`` that a figure states at its written precision establishes the assignment conjunct
    ``lit`` at one of its ends: ``symbol >= lower`` always and ``symbol > lower`` only when the lower end is excluded;
    ``symbol <= upper`` always and ``symbol < upper`` only when the upper end is excluded. So the closure the stated
    enclosure implies grounds ("1.259" states [1.2585, 1.2595), which establishes both ``x < 1.2595`` and ``x <=
    1.2595``), and a closure that narrows it by an end point does not (``x > 1.2585`` is not stated); whether such a
    closure changes a verdict is the precision decision's, not this check's. A bound at any other value is not what it
    states."""
    lo, hi, lo_incl, hi_incl = bounds
    if lit.required in _LOWER_BOUNDS:
        return lit.value == lo and (lit.required == "ge" or not lo_incl)
    if lit.required in _UPPER_BOUNDS:
        return lit.value == hi and (lit.required == "le" or not hi_incl)
    return False


def _tolerance_ends(literals: list[_Literal], figures: Sequence[Any], texts: dict[tuple[str, str], str]) -> dict[int, str]:
    """``{index of a literal: derivation}`` for the bounds of an assignment that are the ends of the interval a figure states
    at its WRITTEN precision (:func:`.quantities.written_precision_intervals`: "x is 0.33 to 2 decimal places" states
    ``x >= 0.325 and x < 0.335``; "≈ 1.55" states [1.545, 1.555); the result of a written calculation, "… = 1.259",
    states [1.2585, 1.2595)), read where the figure stands in its record, at the closures that interval implies
    (:func:`_end_establishes`). A symbol bounded on both sides takes both ends from ONE stated interval, never one end from
    each of two figures; a symbol with one bound takes the end of any. An exact or given figure states no interval, so an
    interval in its place stays unestablished (a weakening)."""
    by_symbol: dict[str, list[int]] = {}
    for k, lit in enumerate(literals):
        if lit.symbol is not None and lit.required in _LOWER_BOUNDS + _UPPER_BOUNDS:
            by_symbol.setdefault(lit.symbol, []).append(k)
    # what each symbol needs: both ends of one interval (a lower and an upper bound), or the end of any (one bound); a
    # symbol with more bounds than that takes none from a tolerance
    pending: dict[str, tuple[int, ...]] = {}
    for name, indices in by_symbol.items():
        lowers = [k for k in indices if literals[k].required in _LOWER_BOUNDS]
        uppers = [k for k in indices if literals[k].required in _UPPER_BOUNDS]
        if len(lowers) == 1 and len(uppers) == 1:
            pending[name] = (lowers[0], uppers[0])
        elif len(indices) == 1:
            pending[name] = (indices[0],)
    out: dict[int, str] = {}
    plain: dict[int, bool] = {}  # how a figure's own words state it, read once (only for a figure whose interval ends at a wanted bound)
    for declared in dict.fromkeys(literals[ks[0]].declared for ks in pending.values()):
        mine = {name: ks for name, ks in pending.items() if literals[ks[0]].declared == declared}
        wanted = {literals[k].value for ks in mine.values() for k in ks}
        for f in figures:  # in order: the first interval that establishes what a symbol needs decides, and the scan stops when none is left
            if not mine:
                break
            text = texts.get((f.source_kind, f.source_id))
            if text is None:
                continue
            for bounds, m, ex in written_precision_intervals(f, text, declared):
                if bounds[0] not in wanted and bounds[1] not in wanted:
                    continue
                if id(f) not in plain:
                    plain[id(f)] = figure_stated_plainly(f, text)
                if not plain[id(f)]:
                    break
                for name, ks in list(mine.items()):
                    if all(_end_establishes(bounds, literals[k]) for k in ks):
                        derivation = interval_derivation(bounds, m, ex)
                        for k in ks:
                            out[k] = derivation
                        del mine[name]
    return out
