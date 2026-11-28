"""Stage-1 leftover 7 (owner R2): bounded work at the oversized cap. The own scope stops being built once it is oversized
whatever follows (more than MAX_CHUNKS x (CHUNK_CHARS - CANARY_RESERVE) characters of segment text, or more than
MAX_CHUNKS x CHUNK_SENTENCES segments), so a 2 MB answer is refused as oversized, with no call, within T23's 1.5 s bound
(``tests/timing.py``: median of five runs, caches emptied). The cap changes no reading: an answer at the cap is read as before,
one segment more is oversized, and an oversized scope's segments are the leading segments of the full reading."""
from __future__ import annotations

import pytest

from epinoic_logic.selfcert_label import build_input
from epinoic_logic.selfcert_label.fakes import ScriptedLabeller, reply_json
from epinoic_logic.selfcert_label.scope import (CANARY_RESERVE, CAP_CHARS, CAP_SEGMENTS, CHUNK_CHARS, CHUNK_SENTENCES, MAX_CHUNKS,
                                                own_scope)

from ..timing import measure

#: T23's bound (tests/selfcert_label/test_linear.py): the 32 KiB label input within 1.5 s; a 2 MB oversized answer is held to it.
BOUND = 1.5
REQ = {"subject": "physics", "task_type": "marking_feedback", "user_input": "Mark this.",
       "supplied_texts": [{"title": "Data booklet", "text": "g = 9.8 m/s^2"}]}
_PARA = " ".join(f"Sentence {i} has a value of {i} m." for i in range(20))
TWO_MB = {
    "paragraphs of sentences": ("\n\n".join([_PARA] * 3200))[:2_000_000],
    "short sentences": "Ok. " * 500_000,
    "one long line": "a" * 2_000_000,
    "letter-spaced": "V E R I F I E D " * 125_000,
    "clauses": "word, " * 333_333,
    "table rows": "| a cell | b cell |\n" * 105_263,
}


def test_the_cap_follows_from_the_chunk_bounds():
    assert (CAP_CHARS, CAP_SEGMENTS) == (MAX_CHUNKS * (CHUNK_CHARS - CANARY_RESERVE), MAX_CHUNKS * CHUNK_SENTENCES) == (45_600, 720)


@pytest.mark.parametrize("name", sorted(TWO_MB))
def test_a_2_mb_answer_is_refused_as_oversized_within_the_timing_bound(name, tmp_path):
    text = TWO_MB[name]
    assert len(text) >= 1_999_990
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Fixed system text of the selfcert-label test suite.\n", encoding="utf-8")
    lab = ScriptedLabeller(lambda req, n: reply_json(req), prompt_path=prompt)
    t = measure(lambda: lab.label(text, REQ), BOUND, label=f"2 MB {name}")
    assert t.holds, t
    assert all((r.state, r.kind) == ("unavailable", "oversized") for r in t.results)
    assert lab.requests == []  # no call was made for it
    scope = own_scope(text, REQ)
    assert scope.oversized and len(scope.chunks) > MAX_CHUNKS
    assert sum(len(s.text) for s in scope.segments) <= CAP_CHARS + 600 and len(scope.segments) <= CAP_SEGMENTS + 1


def _answer(segments: int) -> str:
    """``segments`` one-sentence segments in paragraphs of CHUNK_SENTENCES."""
    sents = [f"Value {i} is {i} m." for i in range(segments)]
    return "\n\n".join(" ".join(sents[k:k + CHUNK_SENTENCES]) for k in range(0, segments, CHUNK_SENTENCES))


def test_an_answer_at_the_cap_is_read_whole_and_one_segment_more_is_oversized(tmp_path):
    at = own_scope(_answer(CAP_SEGMENTS), REQ)
    assert (at.oversized, len(at.segments), len(at.chunks)) == (False, 720, 6)
    assert at.segments[-1].text == "Value 719 is 719 m." and at.segments[-1].place == "paragraph 6, sentence 120"
    over = own_scope(_answer(CAP_SEGMENTS + 1), REQ)
    assert (over.oversized, len(over.segments)) == (True, 721)
    assert [s.text for s in over.segments[:720]] == [s.text for s in at.segments]
    assert [(s.start, s.end, s.place) for s in over.segments[:720]] == [(s.start, s.end, s.place) for s in at.segments]
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Fixed system text of the selfcert-label test suite.\n", encoding="utf-8")
    assert len(build_input(_answer(CAP_SEGMENTS), REQ, key=b"k", prompt_path=prompt).requests) == 6
    assert build_input(_answer(CAP_SEGMENTS + 1), REQ, key=b"k", prompt_path=prompt).oversized


def test_an_oversized_scope_holds_the_leading_segments_of_the_full_reading():
    para = " ".join(f"Line {i} of the answer holds {i} kg." for i in range(10))
    text = "\n\n".join([para] * 400)  # well past the cap
    scope = own_scope(text, REQ)
    assert scope.oversized
    n = len(scope.segments)
    assert n == CAP_SEGMENTS + 1  # short sentences: the segment bound is reached first
    # the same leading paragraphs read alone give the same segments
    head = own_scope("\n\n".join([para] * ((n + 9) // 10)), REQ)
    assert [(s.text, s.start, s.end, s.place, s.origin, s.forbidden) for s in head.segments[:n]] == \
           [(s.text, s.start, s.end, s.place, s.origin, s.forbidden) for s in scope.segments]
    assert scope.invisible_removed == 0 and scope.raw_text is text


def test_invisible_characters_and_delimiters_keep_their_offset_map_at_any_size():
    unit = "Every​ fig­ure <<<was>>> ⁣checked\x85twice ⟦here⟧. "
    text = unit * 3000
    scope = own_scope(text, REQ)
    # U+200B, U+00AD and U+2063 are removed; U+0085 is a white-space control and becomes a space
    assert scope.oversized and scope.invisible_removed == 3 * 3000
    seg = scope.segments[1]
    assert seg.text == "Every figure ‹‹‹was››› checked twice 〚here〛."
    assert text[seg.start:seg.end] == unit.strip()
    assert [text[seg.origin[i][0]] for i in (5, 8, 9)] == [" ", "g", "u"]
    assert seg.origin[9][0] - seg.origin[8][0] == 2  # the removed soft hyphen between "g" and "u" keeps its place in the map
    assert seg.forbidden == ((13, 16), (19, 22), (37, 38), (42, 43))
