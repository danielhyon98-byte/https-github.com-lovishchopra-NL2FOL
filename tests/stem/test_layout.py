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
    ("ANNOTATION_ONLY_RE", "_ANNOTATION_ONLY_RE"), ("ANNOTATION_ONLY_LINEAR_RE", "_ANNOTATION_ONLY_LINEAR_RE"), ("BULLET_RE", "_BULLET_RE"), ("TABLE_SEPARATOR_RE", "_TABLE_SEPARATOR_RE"), ("TABLE_ROW_RE", "_TABLE_ROW_RE"),
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


# ------------------------------------------------------------------ rule locator-number (round-9 clearance, second pass)

def test_the_locator_patterns_are_the_generic_parsers():
    """The bracketed number a locator word owns ('paragraph [3]') is read by the same patterns on both branches, so the STEM and the
    generic parsers keep the same number in their claims."""
    for mine, theirs in ((layout.LOCATOR_BEFORE_RE, gp._LOCATOR_BEFORE_RE), (layout.LEADING_BRACKET_NUMBER_RE, gp._LEADING_BRACKET_NUMBER_RE)):
        assert (mine.pattern, mine.flags) == (theirs.pattern, theirs.flags)


@pytest.mark.parametrize("line,kept", [
    ("The force is shown on the graph and linked to paragraph [3].", "The force is shown on the graph and linked to paragraph [3]."),
    ("The data are in Table [2].", "The data are in Table [2]."),
    ("see paragraphs [3]  M1", "see paragraphs [3]"),       # the locator's number stays, the mark after it goes
    ("using the source [2].", "using the source."),          # a locator after a determiner names no number: the bracket is a mark
    ("reaching 22 at E [1].", "reaching 22 at E."),          # no locator: a mark, as before
    ("The loop runs [1 spare]", "The loop runs"),
])
def test_a_bracketed_number_a_locator_owns_is_no_mark(line, kept):
    """c2 stem-integration (citation): 'linked to paragraph [3].' and 'Table [2].' were cut to 'linked to paragraph.' and 'Table.' in the
    STEM claims, as the generic parser cut them before its own fix (ec-t15 g4.2). The number a locator word owns stays in the claim."""
    out, pos = [], 0
    for a, b in layout.annotation_ranges(line):
        out.append(line[pos:a])
        pos = b
    out.append(line[pos:])
    assert "".join(out).rstrip() == kept


def test_the_stem_and_generic_parsers_keep_a_locators_number_in_the_same_claims():
    kw = dict(request_id="r", task_id="t", report_id="rep", subject="Physics", task_type="short_answer", supplied_texts=[])
    text = "The force is shown on the graph and linked to paragraph [3]. The speed is 4.0 m s⁻¹ [1].\n\nThe data are in Table [2]."
    stem = [c.claim_text for c in StemTextParser().parse_response(text, **kw).claims]
    generic = [c.claim_text for c in gp.GenericTextParser("physics-specialist").parse_response(text, **kw).claims]
    assert stem == generic == ["The force is shown on the graph and linked to paragraph [3].", "The speed is 4.0 m s⁻¹.", "The data are in Table [2]."]


@pytest.mark.parametrize("line", [
    "paragraph [3] " * 1300 + "x", "paragraph [3]. " * 1260, "paragraph" + " " * 19_000 + "[3].", "Table [2]" + " [1]" * 4700 + ".",
    "Table [2]" + "  M1" * 4700, "see line " + "[" * 19_000 + "1]", "the " * 4700 + "source [2].", "\t" * 19_000 + "Table [2]x",
])
def test_the_locator_rule_is_bounded_on_hostile_input(line):
    """Rule locator-number reads at most 40 characters before a run of annotations, with possessive blank runs: a line of about 19,000
    characters (the line bound is 20,000) is read in well under the bound, and so is the rule asked at every offset of it."""
    import time
    t0 = time.process_time()
    layout.annotation_ranges(line)
    for k in range(len(line)):
        layout.locator_number_end(line, k)
    assert time.process_time() - t0 < 4.0
