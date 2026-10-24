"""The STEM front end's layout rules (src/epinoic_logic/stem/layout.py) are the generic parser's round-7 rules: the
patterns are the same, and the furniture they find (part labels, label-only lines, mark annotations, table separator
rows) is blanked from the statements, so the STEM branches cut the claims round 7 verified (docs/STEM_DESIGN.md,
section 4.3)."""
from __future__ import annotations

import re

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.stem_specialist import StemTextParser
from epinoic_logic.branches import generic_parser as gp
from epinoic_logic.stem import build_document, layout


@pytest.mark.parametrize("name,generic", [
    ("PART_LEAD_RE", "_PART_LEAD_RE"), ("LABEL_ONLY_REST_RE", "_LABEL_ONLY_REST_RE"), ("TRAILING_ANNOTATION_RE", "_TRAILING_ANNOTATION_RE"),
    ("ANNOTATION_ONLY_RE", "_ANNOTATION_ONLY_RE"), ("BULLET_RE", "_BULLET_RE"), ("TABLE_SEPARATOR_RE", "_TABLE_SEPARATOR_RE"), ("TABLE_ROW_RE", "_TABLE_ROW_RE"),
    ("SENT_RE", "_SENT_RE"), ("RELATION_RE", "_RELATION_RE"), ("ARITHMETIC_RE", "_ARITHMETIC_RE"), ("TERMINAL_PUNCT_RE", "_TERMINAL_PUNCT_RE"),
    ("CONTINUATION_RE", "_CONTINUATION_RE"), ("CONNECTIVE_END_RE", "_CONNECTIVE_END_RE"), ("SOFT_WRAP_NEXT_RE", "_SOFT_WRAP_NEXT_RE"),
])
def test_the_layout_patterns_are_the_generic_parsers(name, generic):
    mine, theirs = getattr(layout, name), getattr(gp, generic)
    assert (mine.pattern, mine.flags) == (theirs.pattern, theirs.flags), name


def test_the_mark_fragments_and_the_emphasis_rule_are_the_shared_ones():
    assert layout.MARK_ALLOC == gp._MARK_ALLOC and layout.MARK_CODE == gp._MARK_CODE and layout.LABEL_TOKEN == gp._LABEL_TOKEN
    # the shared emphasis rule without inline code (a code span is a span of its own in the STEM reading)
    assert layout.EMPHASIS_RE.pattern == md.EMPHASIS_RE.pattern.replace("|`)", ")")


def test_plain_line_removes_emphasis_and_keeps_offsets():
    line = "**Part (a) — find — 3 marks**"
    plain, index = layout.plain_line(line)
    assert plain == "Part (a) — find — 3 marks" and [line[k] for k in index] == list(plain)
    assert layout.label_only_rest(plain) is not None and layout.label_only_rest("(a) The ball stops.") is None


@pytest.mark.parametrize("line,kept", [
    ("reaching 22 at E [1].", "reaching 22 at E."),
    ("a = 6 − 6t  M1", "a = 6 − 6t"),
    ("$= 4787.58\\ldots$ (A1)", "$= 4787.58\\ldots$"),
    ("Rises to 92 at 35 °C. [1] The rise is steepest between 25 °C and 30 °C. [1]", "Rises to 92 at 35 °C. The rise is steepest between 25 °C and 30 °C."),
    ("The loop runs [1 spare]", "The loop runs"),
])
def test_annotation_ranges_cover_what_the_generic_parser_leaves_out(line, kept):
    out, pos = [], 0
    for a, b in layout.annotation_ranges(line):
        out.append(line[pos:a])
        pos = b
    out.append(line[pos:])
    assert "".join(out).rstrip() == kept


def test_joined_lines_follow_the_generic_parser():
    assert layout.joins_previous("v = u + at", "= 0 + 9.8 × 2.0")             # an equation continued on a line opening with '='
    assert layout.joins_previous("The current falls,", "so the power falls.")    # a comma or a connective ends the line before
    assert layout.joins_previous("The energy is conserved in the", "collision of the two carts.")  # a soft-wrapped prose line
    assert not layout.joins_previous("v = 3.0 m/s", "a = 2.0 m s⁻²")              # every other line break ends a claim
    assert not layout.joins_previous("Given:", "(a) v = 3 m/s") and not layout.joins_previous("| a | b |", "| 1 | 2 |")


def test_furniture_is_blanked_from_the_statements():
    text = "(a) [2]\nv = u + at  M1\n= 0 + 9.8 × 2.0\n= 19.6 m s⁻¹  A1\n\n| t | v |\n|---|---|\n| 0 | 0 |"
    doc = build_document(text, None, "physics")
    assert [doc.statement_text(st.id) for st in doc.statements] == ["v = u + at  M1\n= 0 + 9.8 × 2.0\n= 19.6 m s⁻¹", "| t | v |", "| 0 | 0 |"]
    assert not any(re.fullmatch(r"\(a\)\s*\[2\]", doc.statement_text(st.id)) for st in doc.statements)
    # the claims leave the annotations inside a statement out too, as the generic parser does
    kw = dict(request_id="r", task_id="t", report_id="rep", subject="Physics", task_type="short_answer", supplied_texts=[])
    stem = StemTextParser().parse_response(text, **kw)
    generic = gp.GenericTextParser("physics-specialist").parse_response(text, **kw)
    assert [c.claim_text for c in stem.claims] == [c.claim_text for c in generic.claims] == ["v = u + at\n= 0 + 9.8 × 2.0\n= 19.6 m s⁻¹", "| t | v |", "| 0 | 0 |"]
