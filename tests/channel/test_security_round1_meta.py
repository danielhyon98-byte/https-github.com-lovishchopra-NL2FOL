"""Security round 1: an answer's meta-text and its part sections are read in linear time (``channel.request_parser``).

A word bound is measured on the answer without its meta-text (``is_meta_text``) and, for a bound on one part, on that
part's section with its label and mark annotation taken off (``part_section_text``). Three patterns of that reading split a
long run of spaces between two or three quantifiers before failing: a paragraph of 'Limit' and 16,000 spaces held a
word-bound check for 4.7 s, 'Word count' and 16,000 spaces for 27 s, a part line of '(a) [1' and 16,000 spaces for 2.1 s,
each quadratic. Their white space is now read possessively (each quantifier is followed by a token its characters cannot
begin), which matches every text as before.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.channel import request_parser as RP

from ..growth import growth

#: The patterns before this round, kept as data to pin that every text is read as before.
OLD_META = re.compile(RP._META_LABEL_RE.pattern.replace(")\\s*+(?:\\([^)]{0,40}\\))?\\s*+[:", ")\\s*(?:\\([^)]{0,40}\\))?\\s*[:"), RP._META_LABEL_RE.flags)
OLD_WORD_COUNT = re.compile(RP._WORD_COUNT_LINE_RE.pattern.replace("(?:word\\s*+count\\s*+[:\\-–—]?+\\s*+)?",
                                                                   "(?:word\\s*count\\s*[:\\-–—]?\\s*)?"), RP._WORD_COUNT_LINE_RE.flags)
OLD_LEAD_MARKS = re.compile("^\\s*(?:\\[\\s*\\d+(?:\\s*\\+\\s*\\d+)*\\s*(?:marks?)?\\s*\\]|\\(\\s*\\d+\\s*marks?\\s*\\))", re.IGNORECASE)


def test_the_old_patterns_are_rebuilt():
    assert OLD_META.pattern != RP._META_LABEL_RE.pattern and "\\s*+" not in OLD_META.pattern
    assert OLD_WORD_COUNT.pattern != RP._WORD_COUNT_LINE_RE.pattern and "\\s*+" not in OLD_WORD_COUNT.pattern


def test_a_long_run_after_a_footer_label_is_read_in_linear_time():
    for label in ("Limit", "Word count", "Next step", "Limitations (draft)"):
        ratio, small, large = growth(RP.is_meta_text, label + " " * 2000 + "x", label + " " * 8000 + "x")
        assert ratio < 8.0, (label, ratio, small, large)


def test_a_long_run_in_a_part_label_line_is_read_in_linear_time():
    for lead in ("[1", "[1 + 2", "(3", "[2 marks"):
        ratio, small, large = growth(RP._strip_section_lead, "(a) " + lead + " " * 4000 + "x", "(a) " + lead + " " * 16000 + "x")
        assert ratio < 8.0, (lead, ratio, small, large)


def test_a_part_section_with_a_long_label_line_is_found_in_linear_time():
    ratio, small, large = growth(lambda t: RP.part_section_text(t, "a"), "(a) [1" + " " * 4000 + "x\nPrices rose.\n(b) Output fell.",
                                 "(a) [1" + " " * 16000 + "x\nPrices rose.\n(b) Output fell.")
    assert ratio < 8.0, (ratio, small, large)


BLOCKS = ["Limit: this answer uses no sources.", "Limitations - the data stop in 2019.", "Next step: compare the two policies.", "Next steps (optional): read more.",
          "Word count: 249", "(249 words)", "[249 words]", "About 270 words", "approx. 300 words in total", "~ 120 words", "c. 150 words including the title",
          "Word count - 312 words", "Word   count :   250", "word count", "Limit (in brief)  —  none", "Limit   x", "Limits of the model: the curve is linear.",
          "Limitation : the sample is small.", "The limit of f(x) as x tends to 0 is 1.", "  Limit: shifted", "**Word count:** 200", "250", "1,250 words.",
          "Limit (a very long bracket that runs past forty characters): x", "Word count:", "Word count -", ""]
LINES = ["(a) [4 marks] A regressive tax is one that takes more from the poor.", "(e) [4]", "(b) (2 marks) Explain.", "[1 + 2 + 3 marks] text", "[ 3 ]",
         "[3 mark]x", "[3 marks ] x", "[ 1 +2+ 3 ] y", "(4 marks)rest", "( 4 marks )", "[2] [3] two", "[1", "[1 +", "[marks]", "(a)", "", "  [5]  tail",
         "[10 MARKS] upper", "(12 Marks) mixed", "[1 + 2 marks", "(2 mark)"]


def _random_blocks(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["Limit", "Limitations", "Next step", "Word count", "word", "count", "about", "approx.", "~", "c.", "250", "1,250", "words", "in total", "total",
              "(", ")", "[", "]", "(draft)", ":", "-", "–", "—", " ", "  ", "\t", "x", "*", "#"]
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 12))) for _ in range(n)]


def _random_lines(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["[", "]", "(", ")", "1", "23", "+", " ", "  ", "\t", "mark", "marks", "MARKS", "s", "x", "(a)", ".", "a"]
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 14))) for _ in range(n)]


def _norm(m):
    return None if m is None else (m.span(), m.groupdict())


def test_every_footer_label_and_word_count_is_read_as_before():
    for s in BLOCKS + _random_blocks(40_000, seed=29):
        assert _norm(RP._META_LABEL_RE.match(s)) == _norm(OLD_META.match(s)), repr(s)
        assert _norm(RP._WORD_COUNT_LINE_RE.match(s)) == _norm(OLD_WORD_COUNT.match(s)), repr(s)


def test_every_mark_annotation_is_taken_off_as_before():
    for s in LINES + _random_lines(40_000, seed=31):
        assert RP._LEAD_MARKS_RE.sub("", s, count=1) == OLD_LEAD_MARKS.sub("", s, count=1), repr(s)
        assert _norm(RP._LEAD_MARKS_RE.match(s)) == _norm(OLD_LEAD_MARKS.match(s)), repr(s)


def test_meta_text_and_part_sections_are_still_read():
    assert RP.is_meta_text("Word count: 249") and RP.is_meta_text("(249 words)") and RP.is_meta_text("Next step: compare the two.")
    assert RP.is_meta_text("Limit: this answer uses no sources.")
    # clean controls: a mathematics 'Limit:' heading, and content, stay answer
    assert not RP.is_meta_text("Limit: as x tends to 0, sin x / x tends to 1.")
    assert not RP.is_meta_text("Prices rose because demand rose.")
    assert RP._strip_section_lead("(a) [4 marks] A regressive tax is one that takes more from the poor.") == "A regressive tax is one that takes more from the poor."
    assert RP._strip_section_lead("(e) [4]") == ""
    assert RP.part_section_text("(a) [2] Prices rose.\n(b) Output fell.", "a") == "Prices rose."
