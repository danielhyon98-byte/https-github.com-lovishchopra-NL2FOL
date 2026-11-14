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
from dataclasses import dataclass
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
_STOP = frozenset("""the and of in on at for by to from with a an its their this that these those per total share other data source sources year
    years value values number numbers amount figure figures""".split())
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
    for m in _CLAUSE_SPLIT_RE.finditer(text):
        out.append((pos, text[pos:m.start()]))
        pos = m.end()
    out.append((pos, text[pos:]))
    return [(p, c) for p, c in out if c.strip()]


def _word_positions(clause: str) -> dict[str, list[int]]:
    where: dict[str, list[int]] = {}
    for m in _WORD_RE.finditer(clause):
        where.setdefault(m.group(0).lower().strip("'’-"), []).append(m.start())
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
    if sum(1 for pos, _e in named if pos == best[0]) > 1:
        return None, len(named)  # two rows named by the same words ('primary energy' of two rows): no one row
    return (best[1] if best[0] >= 0 or len(named) == 1 else None), len(named)


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
        return any(w in cell.unit.split() for w, s in _SCALES.items() if s == f.scale)
    return True


def _value_in_cell_unit(f: _Figure, cell: SuppliedCell) -> Fraction:
    """The figure in the cell's unit: a scale word the cell's unit also states is the cell's own ('45.6 billion' of a table in billion
    dalers); one the cell's unit does not state multiplies the figure."""
    if f.scale == 1 or any(w in cell.unit.split() for w, s in _SCALES.items() if s == f.scale):
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


def _table_findings(claim_id: str, text: str, tables: list[SuppliedTable]) -> list[_Finding]:
    out: list[_Finding] = []
    for offset, clause in _clauses(text):
        figures = _figures(clause)
        if not figures:
            continue
        credit = _TABLE_CREDIT_RE.search(clause)
        where = _word_positions(clause)
        for f in figures:
            if f.unit == "pp" or _RESULT_BEFORE_RE.search(clause[max(0, f.start - 4):f.start]):
                continue  # a gap in points, or a result after '=': no figure of a cell
            credited = credit is not None and credit.start() < f.start
            alike = sum(1 for g in figures if (g.unit, g.scale) == (f.unit, f.scale))
            for table in tables:
                entity, count = _entity_at(table, where, f.start)
                year = _year_of(clause, f, alike)
                same = [c for c in table.cells if c.entity == entity and (year is None or c.year == year)] if entity else []
                if entity and year is not None and len(same) == 1:
                    cell = same[0]
                    if not _units_agree(f, cell):
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


# ------------------------------------------------------------------------------------------------- figures of a supplied text in prose
_TOKEN_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*|\d+(?:[.,]\d+)*")


@lru_cache(maxsize=64)
def _tokens(text: str) -> tuple[tuple[str, ...], dict[str, tuple[int, ...]]]:
    toks = tuple(t.lower().replace(",", "").replace("’", "'") for t in _TOKEN_RE.findall(text[:200_000]))
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
        years = {t for t in claim_tokens[i + 2:i + 2 + _DATED_WINDOW // 2] if _YEAR_RE.match(t)}
        if len(years) != 1:
            continue
        year = next(iter(years))
        for doc in docs:
            toks, where = _tokens(doc.text or "")
            if tok in where:
                break  # the text states the answer's figure: nothing misread
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
        found.extend(hits)
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
    return out
