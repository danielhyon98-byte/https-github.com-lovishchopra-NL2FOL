"""STEM front end of the Epinoic logic translator (docs/STEM_DESIGN.md, stage ``core``).

A deterministic reading of what STEM specialists write: equations and prose mixed, in
LaTeX, Unicode, ASCII and words. No text is ever evaluated (no ``eval``/``exec`` or any
library that evaluates strings): a hand-written single-pass lexer and a bounded Pratt
parser over a closed grammar build frozen ASTs, and later stages translate only those
nodes into allowlisted IR 1.0 nodes that the engine decides.

The API later stages use:

* :func:`build_document` -> :class:`StemDocument` (memoised per text, request and profile):
  ``statements`` (claim ids ``s<paragraph>.<n>``), ``items`` (parsed chains with readings),
  ``bindings`` and ``formulas`` (scope), ``relations`` with their outcomes, ``checks``
  (planned checks with stable ids and claim ids), ``findings`` (ST-* codes), ``request``.
* :class:`StemLimits` / :data:`DEFAULT_LIMITS` (every bound), :func:`profile_for` (per-profile
  reading switches).
* Building blocks: :func:`reading_view`, :func:`find_spans`, :func:`segment_statements`,
  :func:`lex`, :func:`parse_math`, :func:`scan_number` / :class:`ExactNumber`,
  :func:`parse_unit` / :class:`Dimension`, :func:`parse_species` / :func:`parse_equation`,
  :func:`parse_boolean` / :func:`parse_truth_table`, :mod:`nodes` helpers.
"""
from __future__ import annotations

from .boolean import BoolRelation, TruthTable, parse_boolean, parse_truth_table
from .chem import ChemEquation, Species, find_equations, parse_equation, parse_species
from .document import StemDocument, build_document, clear_document_cache, document_cache_info
from .lexer import Token, lex
from .limits import DEFAULT_LIMITS, PROFILES, StemLimits, StemProfile, profile_for
from .normalize import masked_view, prose_view, reading_view
from .numbers import ExactNumber, scan_based, scan_number
from .parser import ParseContext, ParsedMath, ParseIssue, parse_math, segment
from .relations import CHECK_KINDS, ST_SEVERITY, FrontEndFinding, MathItem, ProseValue, Relation, RequestReading, dimension_of
from .scope import Binding, Formula, Scope, prescan_names
from .segment import Statement, segment_statements
from .spans import Span, SpanSet, find_spans
from .units import Dimension, UnitExpr, parse_unit

__all__ = [
    "Binding", "BoolRelation", "CHECK_KINDS", "ChemEquation", "DEFAULT_LIMITS", "Dimension", "ExactNumber", "Formula", "FrontEndFinding", "MathItem",
    "PROFILES", "ParseContext", "ParseIssue", "ParsedMath", "ProseValue", "Relation", "RequestReading", "ST_SEVERITY", "Scope", "Span", "SpanSet",
    "Species", "Statement", "StemDocument", "StemLimits", "StemProfile", "Token", "TruthTable", "UnitExpr", "build_document", "clear_document_cache",
    "dimension_of", "document_cache_info", "find_equations", "find_spans", "lex", "masked_view", "parse_boolean", "parse_equation", "parse_math",
    "parse_species", "parse_truth_table", "parse_unit", "prescan_names", "profile_for", "prose_view", "reading_view", "scan_based", "scan_number",
    "segment", "segment_statements",
]
