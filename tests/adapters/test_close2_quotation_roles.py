"""Close round 2 of the argument-diagnosis regression review, the quotation-role reader (SEC-QROLE-QUADRATIC, DIFF-02):

* SEC-QROLE-QUADRATIC (security): the reader of quotation roles (``markdown._span_roles``) read the whole line before every
  quoted span and every earlier span for each span, and its gap patterns read a long run of spaces between two quotations
  again from every position of it, so a hostile answer within the response bound held the hub for minutes. The line
  starts, sentence marks and label heads are now read once per text (``markdown._LineIndex``), an earlier correction on a
  span's line is known from the end of the last correction, the gap patterns consume each run once (possessive
  quantifiers), and one answer's roles are read once however many readers ask for them. The roles are the ones the old
  reader gave.
* DIFF-02: a short span after a contrast ("unlike", "rather than", "instead of") was a mention and never checked, so an
  invented quotation presented as the text's own words passed. What a contrast sets aside is as often the text's own words
  as words the text does not use, so the span after it is a quotation again and is checked, as on the committed base. The
  frames that say the words are absent ("without", "with no", "no") keep their mentions.

Every case is written for this round in wording of its own; nothing from a case is executed."""
from __future__ import annotations

import random
import time

import pytest

from epinoic_logic.adapters import markdown
from epinoic_logic.adapters.markdown import find_quotation_spans, quotation_role, quotation_task

from ..evidence_support import deliver
from .test_repair_round4_quotations import _codes, _poem_case


def _roles(text: str, task: str = "analytical_paragraph") -> list[tuple[str, str]]:
    with quotation_task(task):
        return [(inner, quotation_role(text, s, e)) for s, e, inner in find_quotation_spans(text)]


def _read_roles(text: str, feedback: bool) -> float:
    """CPU seconds of one uncached reading of every role of ``text`` (the role cache is left out on purpose)."""
    spans = tuple(find_quotation_spans(text))
    t0 = time.process_time()
    markdown._roles_of(text, spans, feedback)
    return time.process_time() - t0


def _best(text: str, feedback: bool, runs: int = 3) -> float:
    return min(_read_roles(text, feedback) for _ in range(runs))


# ------------------------------------------------------------------------------------------- SEC-QROLE-QUADRATIC

HOSTILE = {
    # many spans on one line, an analysis task
    "spans": (lambda n: "Intro. " + '"a b" ' * n + " End.", False),
    # many corrections on one line under a label, a feedback task
    "becomes": (lambda n: "Model: " + 'the word "a" becomes ' * n, True),
    # contrasts that correct, one after the other
    "not_but": (lambda n: 'Not "x" but "y". ' * n, True),
    # a list of corrections after one arrow
    "arrow_list": (lambda n: "→ " + '"a", or "b" ' * n, True),
    # a long junk run before a label's colon
    "label_run": (lambda n: "Model" + "(" * (n * 4) + ': "x" ' + '"y" ' * n, True),
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_roles_of_many_spans_on_one_line_are_read_in_linear_time(name):
    make, feedback = HOSTILE[name]
    small, large = make(1500), make(6000)
    t_small, t_large = _best(small, feedback), _best(large, feedback)
    # four times the text: linear work takes about four times as long, the old reader about sixteen times
    assert t_large < 8 * t_small + 0.05, (name, len(large), round(t_small, 3), round(t_large, 3))
    assert t_large < 6.0, (name, len(large), round(t_large, 3))


def test_a_long_run_of_spaces_between_two_quotations_is_read_once():
    # the greedy gap patterns read such a run again from each of its positions (20,000 spaces held the reader over a minute)
    for gap in (" " * 200_000 + ", or ", " " * 200_000 + " but ", "\t" * 100_000):
        text = 'The poet writes "a b"' + gap + '"c d" here.'
        t0 = time.process_time()
        with quotation_task("marking_feedback"):
            markdown.cited_quotation_spans(text)
        assert time.process_time() - t0 < 1.0, repr(gap[-6:])


def test_one_answer_is_read_once_however_many_readers_ask():
    text = "Intro. " + '"a b" ' * 3000 + " End."
    markdown._roles_cached.cache_clear()
    for _ in range(6):
        markdown.cited_quotation_spans(text)
        markdown.uncited_quotation_spans(text)
    info = markdown._roles_cached.cache_info()
    assert info.misses == 1 and info.hits == 11


def test_the_line_index_reads_each_label_as_the_anchored_pattern_does():
    """The label heads read once per line (``_LineIndex.label_governs``) answer what matching the anchored label pattern
    on the line's text before the span answered (``_label_governs``), for labels, junk runs, sentence marks and markup."""
    rng = random.Random(20261024)
    pieces = ["Model", "Model answer", "Corrected version", "Correction", "Better", "Improved", "Rewrite", "Suggestion", "Suggestions",
              ":", ": ", "**", "*", "_", "`", " ", "  ", "\t", ". ", "! ", "? ", "; ", "1.", "(", ")", "#", ">", "-", "word", "the note",
              '"', "“", "x" * 45, "\n"]
    checked = 0
    for _ in range(4000):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 10))) + '"q r"'
        a = text.rfind('"q r"')
        lines = markdown._LineIndex(text)
        prefix = text[text.rfind("\n", 0, a) + 1:a]
        for head, pattern in ((markdown._CORRECTION_LABEL_HEAD_RE, markdown._CORRECTION_LABEL_RE),
                              (markdown._SUGGESTION_LABEL_HEAD_RE, markdown._SUGGESTION_LABEL_RE)):
            assert lines.label_governs(a, head) == markdown._label_governs(prefix, pattern), repr(text)
            checked += 1
    assert checked == 8000


@pytest.mark.parametrize("gap, joined", [(", or ", True), ("  ;  ", True), (" and ", True), (",", True), (" but ", False), (" then ", False),
                                         ("*,*or", False), (" " * 50 + "or", True)])
def test_the_possessive_gap_patterns_match_the_strings_the_greedy_ones_did(gap, joined):
    assert (markdown._LIST_JOIN_RE.match(gap) is not None) is joined


# ------------------------------------------------------------------------------------------- DIFF-02: contrasts

@pytest.mark.parametrize("text, expected", [
    ('Unlike "the bright fields" of the morning, the river is grey.', [("the bright fields", "quotation")]),
    ('Rather than "a quiet harbour", the poem ends at sea.', [("a quiet harbour", "quotation")]),
    ('Instead of "the open sky", the speaker sees only walls.', [("the open sky", "quotation")]),
    ('The poet writes "grey" rather than "silver" here.', [("grey", "quotation"), ("silver", "quotation")]),
])
def test_a_span_after_a_contrast_is_checked_as_a_quotation(text, expected):
    for task in ("analytical_paragraph", "marking_feedback"):
        assert _roles(text, task) == expected, task


@pytest.mark.parametrize("text, expected", [
    ('The stanza runs on without "rhyme" and with no "chorus".', [("rhyme", "mention"), ("chorus", "mention")]),
    ('There is no "refrain" in the poem.', [("refrain", "mention")]),
])
def test_control_a_frame_that_says_the_words_are_absent_keeps_its_mention(text, expected):
    assert _roles(text) == expected


ANSWER = 'The poet presents the willows as wise: they are "patient", and they "read what the slow water writes". '


@pytest.mark.parametrize("sentence", [
    'Unlike "the swift current", the willows wait, so the scene feels calm.',
    'Rather than "the shining river", the poet shows "the slow water".',
    'Instead of "a loud flood", the river keeps "its silver counsel".',
])
def test_an_invented_quotation_after_a_contrast_is_named(sentence):
    _case, rc = deliver(_poem_case(ANSWER + sentence), "text")
    assert {"INT-REQ-003", "ES-SRC-001"} & _codes(rc), sorted(_codes(rc))


@pytest.mark.parametrize("sentence", [
    'Unlike "the dark", which "comes in", the willows wait, so the scene feels calm.',
    'Rather than "the dark", the poet ends on "the slow water".',
])
def test_control_a_real_quotation_after_a_contrast_raises_no_finding(sentence):
    _case, rc = deliver(_poem_case(ANSWER + sentence), "text")
    assert not ({"INT-REQ-003", "ES-SRC-001", "INT-LEDGER-025"} & _codes(rc)), sorted(_codes(rc))
