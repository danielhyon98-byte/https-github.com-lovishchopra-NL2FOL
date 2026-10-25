"""Data tables of the texts supplied with a request (STEM repair 1, rule ``table-data``).

A data-based question supplies its data as a table ("Temperature / °C | Mean oxygen uptake / mm3 per g
per hour", one row per measurement). An answer that states a change between two rows ("between 25 °C and
30 °C, an increase of 22 mm³ per g per hour") or a value at a row ("from 18 mm³ per g per hour at 10 °C to
92 mm³ per g per hour at 35 °C") quotes the table, and the relations stage plans a ``giv`` check of the
stated value against the table's cells (warning severity: which rows and which column the prose means is
a reading). This module only reads the tables: pipe-separated rows of the supplied texts, a header row of
column names with their units ("name / unit" or "name (unit)"), the first column the row key. Nothing is
evaluated: cells are read with the one number scanner (:func:`.numbers.scan_number`), units with
:func:`.units.parse_unit`, and every bound is fixed (tables, rows, columns, cell length).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from .numbers import ExactNumber, scan_number
from .units import UnitExpr, parse_unit

__all__ = ["DataColumn", "DataTable", "MAX_TABLES", "parse_data_tables"]

#: bounds: tables read from all the supplied texts, rows and columns per table, characters per cell and per text
MAX_TABLES = 6
_MAX_ROWS = 60
_MAX_COLUMNS = 8
_MAX_CELL = 80
_MAX_TEXT = 60000
_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_UNIT_SLASH_RE = re.compile(r"^(?P<name>.*?\S)\s*/\s*(?P<unit>[^/]{1,40})$")
_UNIT_BRACKET_RE = re.compile(r"^(?P<name>.*?\S)\s*\((?P<unit>[^()]{1,40})\)\s*$")
_WORD_RE = re.compile(r"[a-z]+")
_STOP = frozenset({"the", "and", "per", "for", "from", "with", "each", "mean", "average", "measured", "value", "values", "sample"})


@dataclass(frozen=True)
class DataColumn:
    """One column of a supplied table: its name as written, the content words of the name, its unit as written (empty
    when the header names none) and the unit read (None when the table of units does not read it)."""

    name: str
    words: frozenset[str]
    unit_text: str
    unit: Optional[UnitExpr]
    #: the unit was read only with its ASCII exponents as superscripts ('mm3 per g per hour'; STEM repair 3): before, no unit was
    #: read, so a stated value is not refused for its unit's dimension (a value whose unit the reader cut short keeps its check)
    unit_ascii: bool = False


@dataclass(frozen=True)
class DataTable:
    """A supplied table: its columns and, per row, each cell's text and number (None for a cell that is not one number).
    ``rows[i][0]`` is the row key."""

    columns: tuple[DataColumn, ...]
    rows: tuple[tuple[tuple[str, Optional[ExactNumber]], ...], ...]

    def row_for(self, key: str, value: Optional[Fraction]) -> Optional[int]:
        """The row whose key cell is ``value`` (a number as written) or the label ``key`` (a site 'A'); None unless exactly one."""
        hits = []
        for i, row in enumerate(self.rows):
            text, num = row[0]
            if value is not None and num is not None and num.value == value:
                hits.append(i)
            elif value is None and text.strip().split(" ")[0].upper() == key.upper():
                hits.append(i)
        return hits[0] if len(hits) == 1 else None

    def value_columns(self) -> list[int]:
        """The columns other than the key whose every cell is one number."""
        return [j for j in range(1, len(self.columns)) if all(row[j][1] is not None for row in self.rows)]


def _words(text: str) -> frozenset[str]:
    return frozenset(w for w in _WORD_RE.findall(text.lower()) if len(w) >= 3 and w not in _STOP)


#: an exponent written in ASCII glued to a unit atom of a header ('mm3', 'dm-3', 's-1'): a superscript (STEM repair 3)
_ASCII_EXPONENT_RE = re.compile(r"(?<=[A-Za-zµμΩ])(-?)([1-4])(?![0-9.])")
_SUPERSCRIPT = str.maketrans("-1234", "⁻¹²³⁴")


def ascii_exponents(unit_text: str) -> str:
    """A unit written with ASCII exponents glued to its atoms, in superscripts ('mm3 per g per hour' -> 'mm³ per g per hour',
    'mg dm-3' -> 'mg dm⁻³'): the form the table of units reads. Text only; bounded by the header's length."""
    return _ASCII_EXPONENT_RE.sub(lambda m: (m.group(1) + m.group(2)).translate(_SUPERSCRIPT), unit_text[:_MAX_CELL])


def _column(header: str) -> DataColumn:
    h = " ".join(header.split())[:_MAX_CELL]
    m = _UNIT_SLASH_RE.match(h) or _UNIT_BRACKET_RE.match(h)
    name, unit_text = (m.group("name"), m.group("unit").strip()) if m else (h, "")
    unit = parse_unit(unit_text) if unit_text else None
    ascii_read = False
    if unit_text and (unit is None or not unit.known):
        # STEM repair 3: a header unit written with ASCII exponents ('mm3 per g per hour', 'mg dm-3') was read as no unit, so a value
        # restated in another unit of the column's dimension compared equal to its cell; read with its exponents as superscripts
        again = parse_unit(ascii_exponents(unit_text))
        if again is not None and again.known:
            unit, ascii_read = again, True
    return DataColumn(name=name, words=_words(name), unit_text=unit_text, unit=unit if unit is not None and unit.known else None, unit_ascii=ascii_read)


def _cell(text: str) -> tuple[str, Optional[ExactNumber]]:
    t = " ".join(text.split())[:_MAX_CELL]
    scan = scan_number(t, 0) if t and (t[0].isdigit() or (t[0] in "-−" and len(t) > 1)) else None
    if scan is None or scan.number is None or scan.end != len(t):
        return t, None
    return t, scan.number


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def parse_data_tables(texts: tuple[str, ...]) -> tuple[DataTable, ...]:
    """Every pipe table of ``texts`` with a header row and at least two rows of the same width (separator rows skipped), the
    first column the key and at least one other column of numbers. Bounded; never raises on text."""
    out: list[DataTable] = []
    for text in texts:
        lines = (text or "")[:_MAX_TEXT].split("\n")
        i = 0
        while i < len(lines) and len(out) < MAX_TABLES:
            if lines[i].count("|") < 1 or _SEPARATOR_RE.match(lines[i]):
                i += 1
                continue
            header = _cells(lines[i])
            width = len(header)
            if not 2 <= width <= _MAX_COLUMNS:
                i += 1
                continue
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
            if len(rows) >= 2 and not any(_cell(c)[1] is not None for c in header[1:]):
                table = DataTable(columns=tuple(_column(c) for c in header), rows=tuple(tuple(_cell(c) for c in r) for r in rows))
                if table.value_columns():
                    out.append(table)
            i = max(j, i + 1)
    return tuple(out)
