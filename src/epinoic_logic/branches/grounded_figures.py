"""Figures an answer takes from a supplied table or text, checked against it on every branch but the STEM ones (round 9 second pass).

Round 8 and round 9 (c2 adversarial-live bug 16, breadth finding 15): a figure the answer attributes to a supplied table or text was never
compared with it outside the STEM branches (whose ``stem-giv`` check reads tables), so 'Table 1 gives exports of goods of 46.5 billion
dalers in 2025' (the table: 45.6), 'Coal supply in 2005: 64% × 820 PJ' (the table: 46) and 'the baths recorded 34,000 swims' (the text:
43,000) crossed with no finding. This module reads the supplied texts' pipe tables into cells and names, as engine problems, the figures the
answer takes from them:

* **a figure credited to a table** ('Table 1 gives ...', 'according to Table 1', '(Table 1)', 'the table shows ...'): read against the cell
  of the row (or column) the clause names and the year it states; a figure no such cell holds is an error when the clause names exactly one
  cell, and a warning (an ambiguous cell) when it names none or several and the figure matches no cell it could mean;
* **a table's figure stated with its row and its year** ('Coal supply in 2005: 64% × 820 PJ', 'coal down from 46% to 28%'): a figure in the
  unit of the table (a per cent of a table of shares, an amount in the table's currency or scale), written as an operand (never the result
  after '=' or '≈'), in a clause that names one row of the table and gives the figure one year (the year written right after it, 'in 2005',
  or the only year of the clause): read against that cell, an error when it differs;
* **a figure of a supplied text restated with another value** ('the baths recorded 34,000 swims' where the text says 'the baths recorded
  43,000 swims'): the three words before the figure and the word after it stand around another figure in the text, and the text never states
  the answer's figure: a warning, since the answer may state a figure of its own in the text's words.

A stated figure matches a cell when it lies within half a unit of the last digit written of either (a rounded figure matches its cell). Every
reader is bounded (texts, tables, rows, cells, claims and figures) and linear in its text; nothing is evaluated. A check proves a property of
its encoding only: that the figure as written does or does not equal the cell as written.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from typing import Optional

from ..ir.schema import Problem
from ..translate.contracts import SpecialistReport, SuppliedText
from .base import FormalCheck

__all__ = ["SuppliedCell", "SuppliedTable", "figure_grounding_checks", "supplied_tables"]

_MAX_TEXT = 60_000
_MAX_TABLES = 8
_MAX_ROWS = 60
_MAX_COLUMNS = 8
_MAX_CELL = 80
_MAX_CLAIMS = 400
_MAX_CLAIM_CHARS = 4000
_MAX_FIGURES = 40
_MAX_WINDOW_HITS = 256

_YEAR_RE = re.compile(r"^(?:1[0-9]{3}|20[0-9]{2})$")
_SEPARATOR_RE = re.compile(r"^\s*+\|?\s*+:?-{2,}+:?\s*+(?:\|\s*+:?-{2,}+:?\s*+)*+\|?\s*+$")
#: A cell's number: a sign, a currency sign, digits (thousands groups), decimals, a per cent sign.
_CELL_NUMBER_RE = re.compile(r"^\s*+(?P<sign>[−–-])?\s*+(?P<cur>[$£€¥])?\s*+(?P<n>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*+(?P<pct>%)?\s*+$")
#: The unit a title, a header or a row label states in brackets: '(%)', '(petajoules, PJ)', '($)', '(billion dalers)'.
_BRACKET_UNIT_RE = re.compile(r"\(([^()\n]{1,40})\)\s*+$")
_SCALES = {"thousand": Fraction(10**3), "million": Fraction(10**6), "billion": Fraction(10**9), "trillion": Fraction(10**12),
           "m": Fraction(10**6), "bn": Fraction(10**9), "k": Fraction(10**3)}
#: The function words of English: they never name a table's row or column, alone or as the one word only that row holds (c3e: 'and'
#: of 'Wind and solar power' named that row in 'Energy supply per person was about 38 GJ in 2005 and about 5.5 GJ in 2025').
FUNCTION_WORDS = frozenset("""a an the and or nor but if so as of in on at to by for from with into onto over under via per than then that this these
    those which who whom whose what is are was were be been being has have had do does did not no its it their his her our your my each every all any
    both either neither such same other""".split())
_STOP = frozenset("""the and of in on at for by to from with a an its their this that these those per total share other data source sources year
    years value values number numbers amount figure figures""".split()) | FUNCTION_WORDS
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]{1,30}")
#: A figure of a claim: an optional currency sign and sign, digits, decimals, then a per cent sign, 'percentage points' or a scale word.
_FIGURE_RE = re.compile(
    r"(?<![\w.,])(?P<cur>[$£€¥])?(?P<sign>[−-])?(?P<n>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d,.]?\d)"
    r"(?P<pp>\s*+percentage\s++points?)?(?P<pct>\s*+(?:%|per\s?cent\b|percent\b))?(?P<scale>\s*+(?:thousand|million|billion|trillion|bn|m)\b)?")
#: A clause that credits its figures to a table.
_TABLE_CREDIT_RE = re.compile(
    r"\b(?:table\s*+\d{1,2}|the\s+(?:data\s+)?table|the\s+data)\s+(?:gives?|gave|shows?|showed|shown|states?|stated|records?|recorded|lists?|listed|reports?"
    r"|reported|puts?|has|had|says?|said)\b|\baccording\s+to\s+(?:table\s*+\d{1,2}|the\s+(?:data\s+)?table)\b|\(\s*+(?:see\s+)?table\s*+\d{1,2}\s*+\)"
    r"|\b(?:from|in|using)\s+table\s*+\d{1,2}\b", re.IGNORECASE)
#: What ends a clause for these readers.
_CLAUSE_SPLIT_RE = re.compile(r";|\.\s|\n|,\s*+(?:and|but|while|whereas|so)\b", re.IGNORECASE)
#: A number that names a part of a text rather than states a figure: 'Table 1', 'Figure 2', 'paragraph [3]', 'question 4', 'Option 2'.
_LOCATOR_BEFORE_RE = re.compile(r"\b(?:tables?|figures?|figs?|sources?|paragraphs?|paras?|lines?|pages?|pp?|parts?|sections?|appendix|questions?|items?|rows?"
                                r"|columns?|options?|steps?|stages?|grades?|levels?|bands?|papers?|units?|topics?|criteri(?:on|a)|storm|site|group|phase)\.?\s*+\[?\s*+$",
                                re.IGNORECASE)
_YEAR_AFTER_RE = re.compile(r"\s*+(?:in|for|of|during|at\s+the\s+end\s+of)?\s*+\(?\s*+(1[0-9]{3}|20[0-9]{2})\b")
_RESULT_BEFORE_RE = re.compile(r"[=≈]\s*+$")
#: A from-to pair of figures with no year between them ("coal down from 46% to 28%").
_FROM_TO_FIG_RE = re.compile(r"\bfrom\s++(?P<a>\d[\d,.]*+)\s*+(?:%|per\s?cent)?(?:(?<=\s)(?!to\b)[^\W\d][^\s\d]{0,15}+[ \t]++){0,2}+"
                             # (a scale or unit word after the first figure, "from 21.4 million to 28.0 million"; check round 13 of c3g)
                             r"\s*+to\s++(?P<b>\d[\d,.]*+)", re.IGNORECASE)


@dataclass(frozen=True)
class SuppliedCell:
    """One numeric cell of a supplied table: the row's label, the column's label, the value as written (sign, currency, per cent), and the
    half-unit of its last written digit."""
    entity: str
    year: Optional[int]
    value: Fraction
    shown: str
    half: Fraction
    unit: str           # '%', a currency sign, or the bracketed unit of its row, column or title ('' when none)


@dataclass(frozen=True)
class SuppliedTable:
    """A supplied table: its document, its title line (or the nearest line above it), its cells, and its entities (row or column labels
    that are not years) with their content words."""
    document_id: str
    title: str
    cells: tuple[SuppliedCell, ...]
    entities: tuple[tuple[str, frozenset[str]], ...]


def _half(shown: str) -> Fraction:
    digits = shown.split(".")[1] if "." in shown else ""
    return Fraction(1, 2) / Fraction(10) ** len(digits)


def _content_words(label: str) -> list[str]:
    return [w.lower().strip("'’-") for w in _WORD_RE.findall(_BRACKET_UNIT_RE.sub("", label)) if w.lower().strip("'’-") not in _STOP]


def _unit_of(label: str) -> str:
    m = _BRACKET_UNIT_RE.search(label.strip())
    if m is None:
        return ""
    inner = m.group(1).strip()
    if inner in ("%", "per cent", "percent"):
        return "%"
    if inner in ("$", "£", "€", "¥"):
        return inner
    return inner.lower()


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip()[:_MAX_CELL] for c in s.split("|")]


def _number(cell: str) -> Optional[tuple[Fraction, str, str]]:
    """``(value, shown, unit sign)`` of a cell that is one number, or None."""
    m = _CELL_NUMBER_RE.match(cell)
    if m is None:
        return None
    v = Fraction(m.group("n").replace(",", ""))
    if m.group("sign"):
        v = -v
    return v, m.group("n"), ("%" if m.group("pct") else (m.group("cur") or ""))


@lru_cache(maxsize=64)
def _tables_of(document_id: str, text: str) -> tuple[SuppliedTable, ...]:
    lines = text[:_MAX_TEXT].split("\n")
    out: list[SuppliedTable] = []
    i = 0
    while i < len(lines) and len(out) < _MAX_TABLES:
        if lines[i].count("|") < 1 or _SEPARATOR_RE.match(lines[i]):
            i += 1
            continue
        header = _cells(lines[i])
        width = len(header)
        rows: list[list[str]] = []
        j = i + 1
        while j < len(lines) and len(rows) < _MAX_ROWS:
            if _SEPARATOR_RE.match(lines[j]):
                j += 1
                continue
            if lines[j].count("|") < 1:
                break
            cells = _cells(lines[j])
            if len(cells) != width:
                break
            rows.append(cells)
            j += 1
        if 2 <= width <= _MAX_COLUMNS and len(rows) >= 2:
            title = next((lines[k].strip() for k in range(i - 1, max(-1, i - 4), -1) if lines[k].strip()), "")
            table = _table(document_id, title, header, rows)
            if table is not None:
                out.append(table)
        i = max(j, i + 1)
    return tuple(out)


def _table(document_id: str, title: str, header: list[str], rows: list[list[str]]) -> Optional[SuppliedTable]:
    years_across = all(_YEAR_RE.match(h) for h in header[1:])
    years_down = all(_YEAR_RE.match(r[0]) for r in rows)
    title_unit = _unit_of(title) or _unit_of(header[0])
    cells: list[SuppliedCell] = []
    entities: dict[str, frozenset[str]] = {}
    for r in rows:
        for k in range(1, len(header)):
            num = _number(r[k])
            if num is None:
                continue
            value, shown, sign = num
            if years_across:
                entity, year, unit = r[0], int(header[k]), _unit_of(r[0]) or title_unit
            elif years_down:
                entity, year, unit = header[k], int(r[0]), _unit_of(header[k]) or title_unit
            else:
                entity, year, unit = f"{r[0]} | {header[k]}", None, _unit_of(header[k]) or _unit_of(r[0]) or title_unit
            unit = sign or unit
            cells.append(SuppliedCell(entity, year, value, shown, _half(shown), unit))
            if years_across or years_down:
                words = frozenset(_content_words(entity)[:2])
                if words:
                    entities[entity] = words
    if not cells or not entities:
        return None
    # rows whose first two content words are the same ("Total primary energy supply" and "Share of primary energy supply that is
    # imported") are named by a word only they hold, the longest ("imported"); a row with none keeps its two (attack round 3)
    full = {e: set(_content_words(e)) for e in entities}
    for e, words in list(entities.items()):
        if any(o != e and entities[o] == words for o in entities):
            others = set().union(*(full[o] for o in entities if o != e and entities[o] == words))
            own = sorted(full[e] - others, key=lambda w: (-len(w), w))
            if own:
                entities[e] = frozenset(words | {own[0]})
    return SuppliedTable(document_id, title, tuple(cells), tuple(entities.items()))


def supplied_tables(texts: list[SuppliedText]) -> list[SuppliedTable]:
    """The pipe tables of the supplied texts with years down a column or across a row (their numeric cells by row label and year)."""
    out: list[SuppliedTable] = []
    for t in texts:
        out.extend(_tables_of(t.document_id, t.text or ""))
    return out


# ------------------------------------------------------------------------------------------------------------------ claims
@dataclass(frozen=True)
class _Figure:
    value: Fraction           # as written, in the unit written (no scale applied)
    shown: str
    half: Fraction
    unit: str                 # '%', 'pp', a currency sign, or ''
    scale: Fraction
    start: int
    end: int


def _figures(clause: str) -> list[_Figure]:
    out: list[_Figure] = []
    for m in _FIGURE_RE.finditer(clause):
        if len(out) >= _MAX_FIGURES:
            break
        n = m.group("n")
        if _YEAR_RE.match(n) and not (m.group("cur") or m.group("pct") or m.group("scale")):
            continue  # a year is a date, not a figure of a cell
        if not m.group("cur") and _LOCATOR_BEFORE_RE.search(clause[max(0, m.start() - 24):m.start()]):
            continue  # 'Table 1', 'paragraph [3]': a locator's number, not a figure
        v = Fraction(n.replace(",", ""))
        if m.group("sign"):
            v = -v
        unit = "pp" if m.group("pp") else "%" if m.group("pct") else (m.group("cur") or "")
        scale = _SCALES.get((m.group("scale") or "").strip().lower(), Fraction(1))
        out.append(_Figure(v, m.group(0).strip(), _half(n), unit, scale, m.start(), m.end()))
    return out


def _clauses(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    pos = 0
    depth_at = []  # bracket depth before each offset, one pass ("(hydroelectric, wind and solar, and nuclear power)" is one list)
    d = 0
    for ch in text:
        depth_at.append(d)
        if ch == "(":
            d += 1
        elif ch == ")" and d:
            d -= 1
    from bisect import bisect_right
    from .insertions import insertion_spans
    spans = insertion_spans(text) if "," in text else ()
    starts = [a for a, _b in spans]
    for m in _CLAUSE_SPLIT_RE.finditer(text):
        if m.group(0).startswith(",") and depth_at[m.start()] > 0:
            continue  # a comma inside brackets lists the bracket's items: no clause boundary (attack round 5)
        if m.group(0).startswith(",") and spans:
            k = bisect_right(starts, m.start()) - 1
            if k >= 0 and spans[k][0] <= m.start() < spans[k][1] and text[:spans[k][1]].rstrip()[-1:] == "," \
                    and re.match(r"[^.;\n]*?[^\W\d_]", text[spans[k][1]:]):
                continue  # a contrast inserted between a subject and its verb ('Imports, while coal declined, made up 54%'): an
                # insertion of the clause around it, which reads it blanked (push check of 08c4a36b)
        out.append((pos, text[pos:m.start()]))
        pos = m.end()
    out.append((pos, text[pos:]))
    return [(p, c) for p, c in out if c.strip()]


def _word_positions(clause: str) -> dict[str, list[int]]:
    where: dict[str, list[int]] = {}
    for m in _WORD_RE.finditer(clause):
        w = m.group(0).lower().strip("'’-")
        where.setdefault(w, []).append(m.start())
        if w.endswith(("'s", "’s")):
            where.setdefault(w[:-2], []).append(m.start())  # a possessive names its word ("hydroelectric power's share", attack round 3)
    return where


def _entity_at(table: SuppliedTable, where: dict[str, list[int]], at: int) -> tuple[Optional[str], int]:
    """The entity whose content words all stand in the clause, the one whose words stand nearest before ``at`` (a figure), and how many
    entities the clause names."""
    named: list[tuple[int, str]] = []
    for entity, words in table.entities:
        if all(w in where for w in words):
            before = [p for w in words for p in where[w] if p < at]
            named.append((max(before) if before else -1, entity))
    if not named:
        return None, 0
    best = max(named)
    tied = [e for pos, e in named if pos == best[0]]
    if len(tied) > 1:
        # the row named by more of the clause's words, when one holds every word of the others ("primary energy supply ... imported")
        size = {e: len(dict(table.entities)[e]) for e in tied}
        top = max(size.values())
        widest = [e for e in tied if size[e] == top]
        if len(widest) == 1 and all(dict(table.entities)[e] <= dict(table.entities)[widest[0]] for e in tied):
            return widest[0], len(named)
        return None, len(named)  # two rows named by the same words ('primary energy' of two rows): no one row
    return (best[1] if best[0] >= 0 or len(named) == 1 else None), len(named)


def _unique_entity(table: SuppliedTable, where: dict[str, list[int]]) -> Optional[str]:
    """The one entity of ``table`` whose own words (those no other entity of any of its tables holds) all stand in the clause, at least one
    such word and at least half of its words standing there; None when none or two are."""
    ents = dict(table.entities)
    hits = []
    for entity, words in table.entities:
        own = {w for w in words if not any(w in o for e2, o in table.entities if e2 != entity)}
        if own and all(w in where for w in own) and 2 * sum(1 for w in words if w in where) >= len(words):
            hits.append(entity)
    return hits[0] if len(hits) == 1 and ents.get(hits[0]) else None


_TOGETHER_RE = re.compile(r"\b(?:together|combined|altogether|jointly|between\s+them|in\s+total|in\s+all|sources|both)\b", re.IGNORECASE)


def _group_figure(table: SuppliedTable, where: dict[str, list[int]], clause: str, f: _Figure, figures: list) -> bool:
    """Whether the figure ``f`` is stated for a group of the table's rows: two or more rows named before it with no other figure between
    the first of them and it, and a word of a total ("together", "combined", "in total") or a list of the rows ("oil and natural gas",
    "hydroelectric, wind and solar, and nuclear power")."""
    firsts = []
    for _entity, words in table.entities:
        if all(w in where for w in words):
            before = [p for w in words for p in where[w] if p < f.start]
            if before:
                firsts.append(min(before))
    if len(firsts) < 2:
        return False
    lo = min(firsts)
    if any(lo < g.start < f.start for g in figures if g is not f):
        return False  # a figure of its own between the rows ("coal 28% and oil 27%"): each row has its own
    span = clause[lo:f.start]
    return _TOGETHER_RE.search(clause) is not None or " and " in span or "," in span


def _year_of(clause: str, f: _Figure, alike: int) -> Optional[int]:
    """The year a figure is stated for: the year written right after it ('46% in 2005', '46% (2005)'), else the clause's only year when the
    clause states no other figure in the figure's unit ('Coal supply in 2005: 64% × 820 PJ'); None otherwise ('In 2025 coal fell to 28%,
    down from 46%': two per cents, one year, so which is the year's is not stated)."""
    m = _YEAR_AFTER_RE.match(clause, f.end)
    if m is not None:
        return int(m.group(1))
    if alike > 1:
        return None
    years = {int(y) for y in re.findall(r"(?<![\d,.])(1[0-9]{3}|20[0-9]{2})(?![\d,.]?\d)", clause)}
    return next(iter(years)) if len(years) == 1 else None


def _units_agree(f: _Figure, cell: SuppliedCell) -> bool:
    if f.unit == "pp":
        return False
    if f.unit == "%" or cell.unit == "%":
        return f.unit == "%" and cell.unit == "%"
    if f.unit in ("$", "£", "€", "¥") or cell.unit in ("$", "£", "€", "¥"):
        return f.unit == cell.unit or (f.unit != "" and f.unit in cell.unit)
    if f.scale != 1:
        return any(w in _unit_words(cell.unit) for w, s in _SCALES.items() if s == f.scale)
    return True


#: Units of measure a figure may be written in: a figure in one the cell's unit does not state is another quantity ("about 42 GJ" per
#: person against a total in PJ; check round 11 of c3e).
_MEASURE_UNITS = frozenset("kj mj gj tj pj ej j kwh mwh gwh twh w kw mw gw tw t kt mt gt kg g mg mm cm m km ha l ml".split())
_UNIT_AFTER_RE = re.compile(r"\s*+(?P<u>[A-Za-z]{1,4})\b")


def _other_measure_unit(clause: str, f: "_Figure", cell: "SuppliedCell") -> bool:
    """Whether the figure is written in a unit of measure the cell's unit does not state."""
    m = _UNIT_AFTER_RE.match(clause, f.end)
    if m is None:
        return False
    u = m.group("u").lower()
    return u in _MEASURE_UNITS and u not in _unit_words(cell.unit)


def _unit_words(unit: str) -> set:
    """The words of a unit, singular ("Population (millions)" states "million")."""
    return {w[:-1] if w.endswith("s") and len(w) > 3 else w for w in re.split(r"[\s,;/]+", unit.lower()) if w}


def _value_in_cell_unit(f: _Figure, cell: SuppliedCell) -> Fraction:
    """The figure in the cell's unit: a scale word the cell's unit also states is the cell's own ('45.6 billion' of a table in billion
    dalers); one the cell's unit does not state multiplies the figure."""
    if f.scale == 1 or any(w in _unit_words(cell.unit) for w, s in _SCALES.items() if s == f.scale):
        return f.value
    return f.value * f.scale


@dataclass(frozen=True)
class _Finding:
    claim_id: str
    statement: str
    figure: _Figure
    cells: tuple[SuppliedCell, ...]
    document_id: str
    where: str              # the table's title, or the text's words around the figure
    severity: str
    how: str
    kind: str = "table"     # 'table' (a cell of a supplied table) or 'text' (a figure of a supplied text's prose)


#: After a figure: (a year and) its parts in brackets joined by + or −, "(28 + 27 + 22)", "in 2005 (100 − 38)".
_PARTS_AFTER_RE = re.compile(r"\s*+%?\s*+(?:(?:of\s+[a-z ]{1,30}\s+)?(?:in|for|by)\s++(?:1[0-9]{3}|20[0-9]{2})\s*+)?"
                             r"\(\s*+[\d.,]{1,12}(?:\s*+[+−-]\s*+[\d.,]{1,12}){1,11}\s*+\)", re.IGNORECASE)
# (only a bracket of parts and nothing else: "(13 − 1 = 12)" after a cell is the working of another figure, and the cell is still read)


#: A figure after the change it measures ("fell by about 39%", "an increase of about 47%", "a fall of 18%"): derived from two cells
#: (the from-to and change checks decide it), never a cell of the table (attack round 6).
_DERIVED_FIG_BEFORE_RE = re.compile(r"\b(?:an?\s++)?(?:fall|rise|drop|decrease|increase|decline|change|reduction|gain|loss|difference|"
                                    r"growth)\s++of\s++(?:(?:about|around|roughly|approximately|nearly|almost|some|just\s+over|"
                                    r"just\s+under)\s++)?\(?\s*+$|\b(?:fell|falls|fall|rose|rises|rise|dropped|drops|declined|declines|"
                                    r"decreased|decreases|increased|increases|grew|grows)\s++by\s++(?:(?:about|around|roughly|"
                                    r"approximately|nearly|almost)\s++)?$", re.IGNORECASE)


#: A word that opens an intervening clause or phrase ("After coal declined, imports made up 54%", "Imports made up 54%, after coal
#: declined, in 2025", "with natural gas growing"), a bracket, a pair of dashes or an apposition: a row it names is that insertion's,
#: never a figure's outside it (push check of a9129c78, the sweep of every row lookup; push check of 08c4a36b, the shared reader of
#: :mod:`.insertions`).


def _intervening_spans(clause: str) -> list[tuple[int, int]]:
    """The spans of the clause's insertions (:func:`.insertions.insertion_spans`): an intervening clause or phrase from its opening word
    (anywhere in the clause) to the next delimiter or to where the main clause resumes, a bracket, a pair of dashes or a comma-delimited
    apposition (push check of 08c4a36b: every row lookup reads its figure's own clause only; no cap on their number, so none is left
    unread)."""
    from .insertions import insertion_spans
    return list(insertion_spans(clause, True))


def _outside(where: dict[str, list[int]], spans: list[tuple[int, int]], at: int) -> dict[str, list[int]]:
    """``where`` without the words inside an insertion that does not hold the figure at ``at`` (spans sorted and disjoint: each word is
    placed by bisection)."""
    from bisect import bisect_right
    starts = [a for a, _b in spans]
    k = bisect_right(starts, at) - 1
    own = spans[k] if k >= 0 and spans[k][0] <= at < spans[k][1] else None

    def kept(p: int) -> bool:
        j = bisect_right(starts, p) - 1
        return j < 0 or not (spans[j][0] <= p < spans[j][1]) or spans[j] == own
    out = {w: ks for w, ps in where.items() for ks in [[p for p in ps if kept(p)]] if ks}
    return out if len(out) != len(where) or any(len(out[w]) != len(where[w]) for w in out) else where


def _table_findings(claim_id: str, text: str, tables: list[SuppliedTable]) -> list[_Finding]:
    out: list[_Finding] = []
    for offset, clause in _clauses(text):
        figures = _figures(clause)
        if not figures:
            continue
        credit = _TABLE_CREDIT_RE.search(clause)
        where_all = _word_positions(clause)
        spans = _intervening_spans(clause)
        # "from A to B" with no year written: A is the row's earlier year and B its later one, when the row has exactly two (attack round 3)
        ends: dict[int, str] = {}
        for pm in _FROM_TO_FIG_RE.finditer(clause):
            ends[pm.start("a")] = "first"
            ends[pm.start("b")] = "last"
        for f in figures:
            where = _outside(where_all, spans, f.start) if spans else where_all
            if f.unit == "pp" or _RESULT_BEFORE_RE.search(clause[max(0, f.start - 4):f.start]):
                continue  # a gap in points, or a result after '=': no figure of a cell
            if _DERIVED_FIG_BEFORE_RE.search(clause[max(0, f.start - 48):f.start]):
                continue  # "fell by about 39% (46% to 28%)", "an increase of about 47%": a change derived from two cells, no cell
            if _PARTS_AFTER_RE.match(clause, f.end):
                continue  # "77% in 2025 (28 + 27 + 22)": a total worked from its parts in brackets, no cell (attack round 4)
            credited = credit is not None and credit.start() < f.start
            alike = sum(1 for g in figures if (g.unit, g.scale) == (f.unit, f.scale))
            named_any = any(_entity_at(t, where, f.start)[1] for t in tables)
            for table in tables:
                entity, count = _entity_at(table, where, f.start)
                if not named_any and entity is None:
                    # no row of any table is named whole: the one row named by the words only it holds ("46% of energy was
                    # imported": the share row's "imported"; check round 13 of c3g)
                    entity, count = _unique_entity(table, where), 1
                if count > 1 and _group_figure(table, where, clause, f, figures):
                    continue  # a figure stated for two or more named rows together ("oil and natural gas together supplied 49%",
                    # "Low-carbon sources (hydroelectric, wind and solar, and nuclear power) rose ... to 23%": attack round 5)
                year = _year_of(clause, f, alike)
                if year is None and entity and f.start in ends and not _YEAR_AFTER_RE.match(clause, f.end):
                    years = sorted({c.year for c in table.cells if c.entity == entity and c.year is not None})
                    if len(years) == 2:
                        year = years[0] if ends[f.start] == "first" else years[1]
                same = [c for c in table.cells if c.entity == entity and (year is None or c.year == year)] if entity else []
                if entity and year is not None and len(same) == 1:
                    cell = same[0]
                    if not _units_agree(f, cell) or _other_measure_unit(clause, f, cell):
                        continue
                    if credited or f.unit or f.scale != 1 or cell.unit:
                        out.append(_Finding(claim_id, clause.strip(), f, (cell,), table.document_id, table.title, "error",
                                            f"the clause {'credits it to the table and ' if credited else ''}names the row '{entity}' and the year {year}"))
                    break
                if credited and entity:
                    # a figure credited to the table whose row the clause names, but not one cell of it (no year, or two): it must be one of
                    # the row's cells; one with no row named ('Table 1 shows a deficit of 9.5', a figure derived from the table) is not read
                    candidates = [c for c in same if _units_agree(f, c)]
                    if candidates:
                        out.append(_Finding(claim_id, clause.strip(), f, tuple(candidates[:24]), table.document_id, table.title, "warning",
                                            "the clause credits it to the table but does not name one cell of it (row and year)"))
                        break
    return out


# ------------------------------------------------------------------------------------------------------- a ratio of two columns
#: '<column A words> per <column B word>': a ratio of two columns of a supplied table ('Catch per boat', 'output per worker'). Bounded runs.
_PER_RE = re.compile(r"(?P<a>[A-Za-z][\w'’-]{0,30}(?:\s++[A-Za-z][\w'’-]{0,30}){0,3})\s++per\s++(?P<b>[A-Za-z][\w'’-]{1,30})")
#: After a figure of a ratio: its unit words and its year ('125.0 tonnes in 2019', '152.5 tonnes (2025)').
_RATIO_YEAR_RE = re.compile(r"\s*+(?P<unit>(?:(?:thousand|million|billion)\s++)?[a-z]{1,20})?\s*+(?:in|for|during)?\s*+\(?\s*+(?P<year>1[0-9]{3}|20[0-9]{2})\b")
#: A qualifier of an approximate figure in the words just before it.
_APPROX_BEFORE_RE = re.compile(r"\b(?:about|around|roughly|approximately|approx\.|nearly|almost|some|c\.|ca\.|circa)\s*+$|~\s*+$", re.IGNORECASE)
_SCALE_WORDS = {"thousand": Fraction(10**3), "thousands": Fraction(10**3), "million": Fraction(10**6), "millions": Fraction(10**6),
                "billion": Fraction(10**9), "billions": Fraction(10**9)}
#: The most '<A> per <B>' phrases read in one clause.
_MAX_RATIO_PHRASES = 16
#: An approximate ratio may differ from the columns' ratio by this share of it (and half a unit of its last digit).
RATIO_APPROX = Fraction(1, 20)


@dataclass(frozen=True)
class _Ratio:
    claim_id: str
    statement: str
    figure: _Figure
    numerator: SuppliedCell
    denominator: SuppliedCell
    factor: Fraction        # the columns' ratio times this is the ratio in the figure's unit
    approx: bool
    document_id: str
    where: str


def _unit_parts(unit: str) -> tuple[Fraction, frozenset[str]]:
    """``(scale, other words)`` of a unit ('thousand tonnes' -> (1000, {'tonne'})); plural endings are dropped."""
    scale, words = Fraction(1), set()
    for w in re.findall(r"[a-z$£€¥]+", unit.lower()):
        if w in _SCALE_WORDS:
            scale *= _SCALE_WORDS[w]
        else:
            words.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return scale, frozenset(words)


def _ratio_findings(claim_id: str, text: str, tables: list[SuppliedTable]) -> list[_Ratio]:
    """Clearance c3 (ec-perboat: 'Catch per boat rose from about 125.0 tonnes in 2019 to about 152.5 tonnes in 2025', where Table 1 gives
    48.0 thousand tonnes and 412 boats in 2019, 116.5 tonnes a boat, crossed with no finding): a figure stated as '<A> per <B>' with its
    year, where A names one column (or row) of a supplied table and B (singular or plural) another, is read against the two cells of that
    year. The figure's unit must be A's (a scale word apart: tonnes against thousand tonnes); a column that is already a rate ('P$ per
    tonne') is not read as A or B."""
    out: list[_Ratio] = []
    for _offset, clause in _clauses(text):
        if " per " not in clause:
            continue
        clause_figures: list[list[_Figure]] = []  # the clause's figures, read once on first use
        for n_per, m in enumerate(_PER_RE.finditer(clause)):
            if n_per >= _MAX_RATIO_PHRASES:
                break  # a clause of more ratio phrases than any answer writes: the first ones are read
            if not clause_figures:
                clause_figures.append(_figures(clause))
            a_words = {w.lower().strip("'’-") for w in m.group("a").split()}
            b_word = m.group("b").lower().strip("'’-")
            b_forms = {b_word, b_word + "s", b_word[:-1] if b_word.endswith("s") else b_word}
            for table in tables:
                a = [e for e, words in table.entities if words and words <= a_words and " per " not in e.lower()]
                b = [e for e, words in table.entities if len(words) == 1 and next(iter(words)) in b_forms and " per " not in e.lower()]
                if len(a) != 1 or len(b) != 1 or a[0] == b[0]:
                    continue
                figures = [f for f in clause_figures[0] if f.start >= m.end() and not f.unit]
                for f in figures:
                    after = _RATIO_YEAR_RE.match(clause, f.end)
                    if after is None:
                        continue
                    year = int(after.group("year"))
                    num = [c for c in table.cells if c.entity == a[0] and c.year == year]
                    den = [c for c in table.cells if c.entity == b[0] and c.year == year]
                    if len(num) != 1 or len(den) != 1 or den[0].value <= 0 or num[0].unit in ("%", "$", "£", "€", "¥"):
                        continue
                    a_scale, a_unit = _unit_parts(num[0].unit)
                    b_scale, _b_unit = _unit_parts(den[0].unit)
                    f_scale, f_unit = _unit_parts(after.group("unit") or "")
                    if f_unit and a_unit and not f_unit <= a_unit:
                        continue  # the figure's unit is not the column's: another quantity
                    if not f_unit and a_scale != 1:
                        continue  # no unit written against a column in thousands: which scale is meant is not stated
                    approx = bool(_APPROX_BEFORE_RE.search(clause[max(0, f.start - 16):f.start]))
                    out.append(_Ratio(claim_id, clause.strip(), f, num[0], den[0], a_scale / b_scale / (f_scale * f.scale), approx,
                                      table.document_id, table.title))
                break
    return out


def _ratio_value(r: _Ratio) -> Fraction:
    return r.numerator.value / r.denominator.value * r.factor


def _ratio_check(report: SpecialistReport, prefix: str, n: int, r: _Ratio) -> FormalCheck:
    """The ratio as a linear problem: the denominator cell is a constant, so 'stated = num / den x factor, within a band' is written
    multiplied through by it (``stated x den - num x factor`` within ``band x den``; the denominator is positive)."""
    grounding = {"kind": "supplied_text", "verified": True}
    computed = _ratio_value(r)
    band = r.figure.half + (abs(computed) * RATIO_APPROX if r.approx else 0)
    year = r.numerator.year
    den = r.denominator.value
    symbols = [{"name": "stated", "sort": "Real", "meaning": f"the ratio the answer states ({r.figure.shown})"},
               {"name": "num", "sort": "Real", "meaning": f"the supplied figure of {r.numerator.entity} in {year}"[:200]}]
    premises = [{"id": "STATED", "expr": {"op": "eq", "left": _var("stated"), "right": _real(r.figure.value)}, "label": f"stated ratio {r.figure.shown}"[:1000],
                 "grounding": grounding},
                {"id": "NUM", "expr": {"op": "eq", "left": _var("num"), "right": _real(r.numerator.value)},
                 "label": f"{r.numerator.entity}, {year}: {r.numerator.shown}"[:1000], "grounding": grounding}]
    diff = {"op": "sub", "left": {"op": "mul", "args": [_var("stated"), _real(den)]}, "right": {"op": "mul", "args": [_var("num"), _real(r.factor)]}}
    concl = {"op": "and", "args": [{"op": "le", "left": diff, "right": _real(band * den)}, {"op": "ge", "left": diff, "right": _real(-band * den)}]}
    where = f"{r.document_id} ({r.where[:120]})" if r.where else r.document_id
    label = (f"the ratio {r.figure.shown} equals {r.numerator.entity} over {r.denominator.entity} ({r.denominator.shown}, the supplied figure of "
             f"{year}) in {year} ({r.numerator.shown} / {r.denominator.shown}{'' if r.factor == 1 else f' x {r.factor}'} = {float(computed):.4g}) in {where}, "
             f"within half a unit of its last digit" + (" and 5% for an approximate figure" if r.approx else ""))
    problem = {"problem_id": f"fig-{report.report_id}-{n}"[:128], "request_id": report.request_id, "claim_id": f"{report.report_id}:figure-{n}"[:128],
               "query": "entailment", "symbols": symbols, "premises": premises, "conclusion": {"id": "FIGURE", "expr": concl, "label": label[:1000]}}
    description = (f"a ratio of two columns of a supplied table: {r.figure.shown} in '{r.statement[:200]}' against {where}: {r.numerator.entity} "
                   f"{r.numerator.shown} over {r.denominator.entity} {r.denominator.shown} in {year} is {float(computed):.4g} [rule: a ratio stated as "
                   f"'A per B' with its year equals the table's A over its B for that year, within half a unit of its last digit, and 5% of it when "
                   f"the ratio is approximate]")
    return FormalCheck(check_id=f"{prefix}-figure-{n}", kind="supplied_figure", description=description[:1500], problem=Problem.model_validate(problem),
                       claim_ids=(r.claim_id,), policy="linear", failure_severity="error", defect="source_mismatch")


# ------------------------------------------------------------------------------------------------- figures of a supplied text in prose
_TOKEN_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*|\d{1,3}(?:[ \u00a0\u202f]\d{3})++(?![\d,.]?\d)|\d+(?:[.,]\d+)*")
#: A number written with blanks between its groups of thousands ("1 250", the Spanish, French and SI style): one number.
_GROUP_BLANKS_RE = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d{3})")


@lru_cache(maxsize=64)
def _tokens(text: str) -> tuple[tuple[str, ...], dict[str, tuple[int, ...]]]:
    toks = tuple(_GROUP_BLANKS_RE.sub("", t.lower().replace(",", "").replace("’", "'")) for t in _TOKEN_RE.findall(text[:200_000]))
    where: dict[str, list[int]] = {}
    for i, t in enumerate(toks):
        where.setdefault(t, []).append(i)
    return toks, {k: tuple(v) for k, v in where.items()}


def _is_number(token: str) -> bool:
    return token[:1].isdigit()


def _shown_token(token: str) -> str:
    """A number token as the reader shows it: a whole number of four digits or more with its thousands separators ('43000' -> '43,000')."""
    return f"{int(token):,}" if token.isdigit() and len(token) >= 4 else token


def _prose_findings(claim_id: str, text: str, docs: list[SuppliedText]) -> list[_Finding]:
    out: list[_Finding] = []
    claim_tokens = _tokens(text)[0]
    for i, tok in enumerate(claim_tokens[:2000]):
        if not _is_number(tok) or len(tok.replace(".", "")) < 2 or _YEAR_RE.match(tok) or i < 3 or i + 1 >= len(claim_tokens):
            continue
        before, after = claim_tokens[i - 3:i], claim_tokens[i + 1]
        if any(_is_number(t) for t in (*before, after)):
            continue
        nxt = [t.lower() for t in claim_tokens[i + 1:i + 5]]
        if any(t in ("más", "mas", "menos", "more", "fewer", "less") for t in nxt) and any(t in ("que", "than") for t in nxt):
            continue  # a difference the answer works out ("56 personas más que en 2015", "56 more people than in 2015": attack round 5)
        for doc in docs:
            toks, where = _tokens(doc.text or "")
            if tok in where:
                continue  # the text states the answer's figure: nothing misread
            hits = where.get(before[-1], ())
            if len(hits) > _MAX_WINDOW_HITS:
                continue
            for p in hits:
                q = p + 1
                if q + 1 < len(toks) and _is_number(toks[q]) and toks[q] != tok and toks[q + 1] == after and toks[max(0, p - 2):p + 1] == before:
                    try:
                        stated, holds = Fraction(tok), Fraction(toks[q])
                    except (ValueError, ZeroDivisionError):
                        continue
                    if stated == holds:
                        continue  # the same figure written otherwise ('1.20' for '1.2')
                    f = _Figure(stated, _shown_token(tok), _half(tok), "", Fraction(1), 0, 0)
                    cell = SuppliedCell(" ".join(before + (after,)), None, holds, _shown_token(toks[q]), _half(toks[q]), "")
                    out.append(_Finding(claim_id, text.strip()[:400], f, (cell,), doc.document_id,
                                        f"'{' '.join(before)} {_shown_token(toks[q])} {after}'", "warning",
                                        "the words around the figure stand around another figure in the text, which never states the answer's", "text"))
                    break
            else:
                continue
            break
    return out


#: A clause that credits its figures to a supplied text or case: 'The writer reminds readers that ...', 'the case says ...', 'according to the
#: text', 'paragraph 3 says', "Hartwell's own figures:". A figure after it that the text states otherwise is misread from the text: an error.
_TEXT_CREDIT_RE = re.compile(
    r"\b(?:the|this)\s+(?:writer|author|columnist|journalist|article|column|editorial|op-ed|piece|text|extract|passage|case(?:\s+study)?|source|report|letter"
    r"|speech|advert(?:isement)?|leaflet|blog(?:\s+post)?|essay|transcript|interview)"
    r"\s+(?:says?|said|states?|stated|gives?|gave|reports?|reported|notes?|noted|reminds?|reminded|records?|recorded|tells?|told|claims?|claimed|shows?|showed"
    r"|mentions?|mentioned|writes?|wrote|lists?|listed|puts?)\b"
    r"|\baccording\s+to\s+the\s+(?:writer|author|article|text|extract|passage|case(?:\s+study)?|source)\b"
    r"|\b(?:paragraph|para\.?|line)\s*+\[?\d{1,3}\]?\s+(?:says?|states?|gives?|notes?|reports?|records?)\b"
    r"|['’]s\s+own\s+(?:figures?|data|numbers)\b|\bthe\s+case(?:\s+study)?['’]s\s+(?:figures?|data|numbers)\b", re.IGNORECASE)


def _credited(text: str) -> Optional["re.Match[str]"]:
    return _TEXT_CREDIT_RE.search(text[:_MAX_CLAIM_CHARS])


@lru_cache(maxsize=64)
def _stem_index(text: str) -> dict[str, tuple[int, ...]]:
    """Positions of the tokens of ``text`` by their first five letters (tokens of five letters or more)."""
    toks = _tokens(text)[0]
    where: dict[str, list[int]] = {}
    for i, t in enumerate(toks):
        if len(t) >= 5 and t[:1].isalpha():
            where.setdefault(t[:5], []).append(i)
    return {k: tuple(v) for k, v in where.items()}


def _stem_noun_findings(claim_id: str, text: str, docs: list[SuppliedText]) -> list[_Finding]:
    """Clearance c3 (bm-case: "compare them with Hartwell's own figures: sales of $2,400,000 and 32 employees", where the case says 'it
    employs 28 people', crossed with no finding): after a credit to the supplied text or case, a figure with its noun ('32 employees') where
    the text states one other figure beside a word of the same stem ('employs 28') and never the answer's figure is misread from the text.
    Read only after a credit (a stem is a loose match); bounded by the claim's first 400 tokens and :data:`_MAX_WINDOW_HITS` hits a stem."""
    credit = _credited(text)
    if credit is None:
        return []
    out: list[_Finding] = []
    claim_tokens = _tokens(text[credit.end():_MAX_CLAIM_CHARS])[0]
    for i, tok in enumerate(claim_tokens[:400]):
        if not _is_number(tok) or _YEAR_RE.match(tok) or i + 1 >= len(claim_tokens):
            continue
        noun = claim_tokens[i + 1]
        if _is_number(noun) or len(noun) < 5 or noun in _STOP:
            continue
        for doc in docs:
            toks, where = _tokens(doc.text or "")
            if tok in where:
                break  # the text states the answer's figure: nothing misread
            hits = _stem_index(doc.text or "").get(noun[:5], ())
            if not hits or len(hits) > _MAX_WINDOW_HITS:
                continue
            values = {toks[q] for p in hits for q in (p - 1, p + 1) if 0 <= q < len(toks) and _is_number(toks[q]) and not _YEAR_RE.match(toks[q])}
            if len(values) != 1:
                continue
            held = next(iter(values))
            try:
                stated, holds = Fraction(tok), Fraction(held)
            except (ValueError, ZeroDivisionError):
                break
            if stated != holds:
                f = _Figure(stated, _shown_token(tok), _half(tok), "", Fraction(1), 0, 0)
                cell = SuppliedCell(noun, None, holds, _shown_token(held), _half(held), "")
                out.append(_Finding(claim_id, text.strip()[:400], f, (cell,), doc.document_id, f"'{_shown_token(held)}' beside a word like '{noun}'", "error",
                                    f"the claim credits the figure to the text ('{' '.join(credit.group(0).split())}'), which states another figure with "
                                    f"a word of the same stem and never the answer's", "text"))
            break
    return out


#: Comparative words between a figure and its year: the figure is a difference against the year's figure (attack round 8).
_COMPARATIVE_TOKENS = frozenset("más mas menos more fewer less than que".split())
#: How far (in tokens) a year may stand from a dated figure and its noun, in the answer and in the text.
_DATED_WINDOW = 8


def _dated_noun_findings(claim_id: str, text: str, docs: list[SuppliedText]) -> list[_Finding]:
    """Round-9 clearance c2b (the STEM fixer's handoff 6, c1 adversarial-live 15: sp-t14 with '212 vecinos en 2015' changed to '221 vecinos
    en 2015' crossed with no finding): a figure the answer states with its noun and a year ('221 vecinos en 2015', '1,250 inhabitants in
    1960') where a supplied text states ANOTHER figure with the same noun in a sentence of the same year ('en 2015 solo quedaban 212
    vecinos') and never states the answer's figure: a warning (the answer may state a figure of its own in the text's words). Bounded:
    the text's hits of one noun are read at most :data:`_MAX_WINDOW_HITS` times; linear in the claim."""
    out: list[_Finding] = []
    claim_tokens = _tokens(text)[0]
    for i, tok in enumerate(claim_tokens[:2000]):
        if not _is_number(tok) or len(tok.replace(".", "").replace(",", "")) < 2 or _YEAR_RE.match(tok) or i + 1 >= len(claim_tokens):
            continue
        noun = claim_tokens[i + 1]
        if _is_number(noun) or len(noun) < 4 or noun in _STOP:
            continue
        between = claim_tokens[i + 2:i + 2 + _DATED_WINDOW // 2]
        years = {t for t in between if _YEAR_RE.match(t)}
        if len(years) != 1:
            continue
        year = next(iter(years))
        if any(t in _COMPARATIVE_TOKENS for t in between[:between.index(year)]):
            continue  # "56 vecinos más que en 2015", "56 more residents than in 2015": a difference worked out against the year's figure,
            # never the year's figure itself (attack round 8)
        for doc in docs:
            toks, where = _tokens(doc.text or "")
            # the text states the answer's figure with this noun, or in a sentence of this year: nothing misread. A figure the text states
            # only elsewhere ('268 personas' today) is no figure of this year ('268 vecinos en 2015' against '212 vecinos' in 2015,
            # attack round 8)
            if any(toks[p - 1] == tok for p in where.get(noun, ()) if p > 0) or \
                    any(year in toks[max(0, q - _DATED_WINDOW):q + _DATED_WINDOW] for q in where.get(tok, ())[:_MAX_WINDOW_HITS]):
                break
            hits = where.get(noun, ())
            if len(hits) > _MAX_WINDOW_HITS:
                continue
            found = None
            for p in hits:
                q = p - 1
                if q < 0 or not _is_number(toks[q]) or toks[q] == tok or _YEAR_RE.match(toks[q]):
                    continue
                if year in toks[max(0, q - _DATED_WINDOW):p + _DATED_WINDOW]:
                    found = q
                    break
            if found is None:
                continue
            try:
                stated, holds = Fraction(tok.replace(",", "")), Fraction(toks[found])
            except (ValueError, ZeroDivisionError):
                break
            if stated != holds:
                f = _Figure(stated, _shown_token(tok), _half(tok), "", Fraction(1), 0, 0)
                cell = SuppliedCell(f"{noun} {year}", int(year), holds, _shown_token(toks[found]), _half(toks[found]), "")
                out.append(_Finding(claim_id, text.strip()[:400], f, (cell,), doc.document_id, f"'{_shown_token(toks[found])} {noun}' ({year})", "warning",
                                    "the text states another figure with the same noun in a sentence of the same year, and never the answer's", "text"))
            break
    return out


# ------------------------------------------------------------------------------------------------------------------ problems
def _real(x: Fraction) -> dict:
    return {"op": "real", "value": f"{x.numerator}/{x.denominator}" if x.denominator != 1 else str(x.numerator)}


def _var(name: str) -> dict:
    return {"op": "var", "name": name}


def _check(report: SpecialistReport, prefix: str, n: int, g: _Finding) -> FormalCheck:
    grounding = {"kind": "supplied_text", "verified": True}
    symbols = [{"name": "stated", "sort": "Real", "meaning": f"the figure the answer states ({g.figure.shown})"}]
    premises = [{"id": "STATED", "expr": {"op": "eq", "left": _var("stated"), "right": _real(_value(g))}, "label": f"stated figure {g.figure.shown}"[:1000],
                 "grounding": grounding}]
    options = []
    for k, cell in enumerate(g.cells, start=1):
        symbols.append({"name": f"cell{k}", "sort": "Real", "meaning": f"the supplied figure of {cell.entity}{'' if cell.year is None else ' in ' + str(cell.year)}"[:200]})
        premises.append({"id": f"CELL{k}", "expr": {"op": "eq", "left": _var(f"cell{k}"), "right": _real(cell.value)},
                         "label": f"{cell.entity}{'' if cell.year is None else ', ' + str(cell.year)}: {cell.shown}"[:1000], "grounding": grounding})
        band = max(g.figure.half, cell.half)
        diff = {"op": "sub", "left": _var("stated"), "right": _var(f"cell{k}")}
        options.append({"op": "and", "args": [{"op": "le", "left": diff, "right": _real(band)}, {"op": "ge", "left": diff, "right": _real(-band)}]})
    concl = options[0] if len(options) == 1 else {"op": "or", "args": options}
    where = f"{g.document_id} ({g.where[:120]})" if g.where else g.document_id
    label = (f"the figure {g.figure.shown} equals the supplied figure it is taken from ({', '.join(c.shown for c in g.cells[:6])}"
             f"{' ...' if len(g.cells) > 6 else ''} in {where}), within half a unit of the last digit written of either")
    problem = {"problem_id": f"fig-{report.report_id}-{n}"[:128], "request_id": report.request_id, "claim_id": f"{report.report_id}:figure-{n}"[:128],
               "query": "entailment", "symbols": symbols, "premises": premises, "conclusion": {"id": "FIGURE", "expr": concl, "label": label[:1000]}}
    cells = "; ".join(f"{c.entity}{'' if c.year is None else ', ' + str(c.year)}: {c.shown}" for c in g.cells[:4])
    description = (f"a figure taken from a supplied {g.kind}: "
                   f"{g.figure.shown} in '{g.statement[:200]}' against {where}, cell {cells} ({g.how}) [rule: a figure taken from a supplied table or "
                   f"text equals it within half a unit of the last digit written of either]")
    return FormalCheck(check_id=f"{prefix}-figure-{n}", kind="supplied_figure", description=description[:1500], problem=Problem.model_validate(problem),
                       claim_ids=(g.claim_id,), policy="linear", failure_severity="error" if g.severity == "error" else "warning", defect="source_mismatch")


def _value(g: _Finding) -> Fraction:
    return _value_in_cell_unit(g.figure, g.cells[0]) if g.cells[0].unit or g.figure.scale != 1 else g.figure.value


def figure_grounding_checks(report: SpecialistReport, prefix: str, limit: Optional[int] = None) -> list[FormalCheck]:
    """The engine problems of the figures ``report`` takes from its supplied tables and texts (the module docstring), each naming its
    claim; at most ``limit``."""
    texts = [t for t in report.supplied_texts if not (t.document_id or "").startswith("peer:")]
    if not texts:
        return []
    tables = supplied_tables(texts)
    found: list[_Finding] = []
    ratios: list[_Ratio] = []
    for c in report.claims[:_MAX_CLAIMS]:
        if c.claim_role == "other":
            continue
        text = c.claim_text[:_MAX_CLAIM_CHARS]
        if not re.search(r"\d", text):
            continue
        hits = _table_findings(c.claim_id, text, tables) if tables else []
        if not hits:
            hits = _prose_findings(c.claim_id, text, texts)
        if not hits:
            hits = _dated_noun_findings(c.claim_id, text, texts)
        if not hits:
            hits = _stem_noun_findings(c.claim_id, text, texts)
        if hits and _credited(text) is not None:
            # a figure the claim credits to the text that the text states otherwise is misread from it (clearance c3, ll-t15: 'The writer
            # reminds readers that the baths recorded 34,000 swims', the text 43,000, was a warning): an error, as for a table's cell
            hits = [h if h.severity == "error" or h.kind != "text" else replace(h, severity="error", how=h.how + "; the claim credits it to the text")
                    for h in hits]
        found.extend(hits)
        if tables and " per " in text:
            ratios.extend(_ratio_findings(c.claim_id, text, tables))
    seen: set[tuple[str, str, str]] = set()
    out: list[FormalCheck] = []
    for g in found:
        key = (g.claim_id, g.figure.shown, g.cells[0].shown)
        if key in seen:
            continue
        seen.add(key)
        if limit is not None and len(out) >= limit:
            break
        out.append(_check(report, prefix, len(out) + 1, g))
    for r in ratios:
        key = (r.claim_id, r.figure.shown, f"{r.numerator.shown}/{r.denominator.shown}")
        if key in seen:
            continue
        seen.add(key)
        if limit is not None and len(out) >= limit:
            break
        out.append(_ratio_check(report, prefix, len(out) + 1, r))
    return out
