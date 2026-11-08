"""Integration gate 2, handoff fixer: the STEM front end's input stalls (critical rule: input that stalls the service is a
security finding, fixed at its cause, never deferred as optimisation work).

Handed over (parsers handoff, section 3, and the parsers fixer's PERF-G2-07):

* ``stem.layout.annotation_ranges`` matched every sentence of a line whole with ``ANNOTATION_ONLY_RE``, whose blank run after the
  last mark and blank run after the optional stop were adjacent: a line of a mark, blanks and text ('(A1)' + k blanks + 'x')
  tried every split of the run, k² steps (1.46 s for one 20,000-character line; 29 s for an answer of 20 such lines in the
  front end; 30 s to receive and 14 s to audit five of them on a Physics hub). The line is read with the same pattern with
  possessive runs (``layout.ANNOTATION_ONLY_LINEAR_RE``; the written pattern, which the generic parser shares, is unchanged).

Found by the sweep of the same class in these modules (each fixed at its cause, its old reading kept below as the specification):

* ``layout._mask_quoted`` read up to 2,000 characters from every opening quotation mark with no closing mark (``_QUOTED_RE``):
  1.25 s for ``joins_previous`` on one 20,000-character line of '„', 9 s for five soft-wrapped such lines in the front end.
  The spans are found in one pass (``layout.quoted_spans``).
* ``segment._joins`` joined the logical line read so far and asked each join rule of the whole of it for every physical line it
  absorbed, n² steps on soft-wrapped lines ('ab cd' on each of 8,000 lines: 39 s in the front end, 22 s to receive 4,000 of
  them on a Physics hub). The logical line is kept as lines are added (``layout.JoinedLine``, ``layout.WorkingReader``).
* ``relations._Planner._chain`` read a chain continued line after line ('x = 1' then '= 1' on each line) whole again for every
  line, n² steps up to the statement limit (6.7 s at 800 lines; 25 s to receive and audit on a Physics hub). The link limit
  of one chain (``max_chain_links``, ST-LIM-001) now holds for a continued chain too: the lines past it are named undecided.

And the regression the stem handoff asked for beside the blank-run one: a run of accuracy marks that does not end the line
('x = 5' + ' (A1)' * 8,000 + ' z', fixed by ``generic_parser._accuracy_marked``) through the audited Physics hub.
"""
from __future__ import annotations

import importlib
import random
import re
import time

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches import generic_parser as gp
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_overseer import EngineKey, KeyRing, TransferAuditor
from epinoic_logic.stem import layout
from epinoic_logic.stem.document import build_document, clear_document_cache

from ..growth import growth
from ..timing import empty_caches

segment_module = importlib.import_module("epinoic_logic.stem.segment")

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
KEY = b"integration-gate-2-handoff-stem-key-0123456789"
SECRET = b"integration-gate-2-handoff-stem-secret-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)

#: ``layout.ANNOTATION_ONLY_RE`` as written (the specification of :data:`layout.ANNOTATION_ONLY_LINEAR_RE`)
WRITTEN_ANNOTATION_ONLY_RE = re.compile(rf"\s*(?:(?:{layout.MARK_ALLOC}|\(?{layout.MARK_CODE}\)?)\s*)+[.;,]?\s*")


def _random_texts(alphabet, seed: int, n: int, longest: int = 12):
    rng = random.Random(seed)
    for _ in range(n):
        yield "".join(rng.choice(alphabet) for _ in range(rng.randint(0, longest)))


def _cross(text: str) -> tuple[float, float, object, object]:
    """Receive ``text`` on an audited Physics hub and audit the task: (receive CPU s, audit CPU s, receipt, audit)."""
    keyring = KeyRing({k: EngineKey(KEY) for k in ("hub", "channel", "default", "integrity")}, SECRET)
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=TransferAuditor(keyring, replay_mode="inline", eager=True, shadow="always"))
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist"]))
    m, _req, _rq = hub.dispatch("t", "physics-specialist", "Answer the question.")
    empty_caches()
    try:
        c0 = time.process_time()
        _reply, rc = hub.receive("t", m.message_id, text, agent_id="physics-specialist", report_id="r1")
        c1 = time.process_time()
        audit = hub.audit("t")
        c2 = time.process_time()
    finally:
        hub.close()
    return c1 - c0, c2 - c1, rc, audit


def _document(text: str) -> float:
    clear_document_cache()
    c0 = time.process_time()
    build_document(text, "Answer the question.", "physics")
    return time.process_time() - c0


# --------------------------------------------------------------------------- a line of marks, blanks and text (handed over)


def test_the_linear_annotation_line_pattern_matches_what_the_written_one_matched():
    assert layout.ANNOTATION_ONLY_RE.pattern == WRITTEN_ANNOTATION_ONLY_RE.pattern  # the shared pattern is unchanged
    alphabet = [" ", "  ", "\t", "\n", "(A1)", "A1", "(M1)", "M2", "AG", "R1", "N2", "[2]", "[1 spare]", "[3 marks]", "(2 marks)", "(", ")", "[", "]",
                ".", ";", ",", "x", "1", "marks", " "]
    for text in _random_texts(alphabet, 52, 80000):
        old, new = WRITTEN_ANNOTATION_ONLY_RE.fullmatch(text), layout.ANNOTATION_ONLY_LINEAR_RE.fullmatch(text)
        assert (old is None) == (new is None), repr(text)


def test_the_annotation_ranges_are_those_the_written_pattern_gave(monkeypatch):
    alphabet = [" ", "  ", "\t", "(A1)", "A1", "  M1", "(M1)", "AG", "[2]", "[1 spare]", "(2 marks)", ".", ";", ",", "x = 5", "The rise is steep",
                ". ", "It", "5", "(", ")"]
    texts = list(_random_texts(alphabet, 53, 20000, longest=10))
    new = [layout.annotation_ranges(t) for t in texts]
    monkeypatch.setattr(layout, "ANNOTATION_ONLY_LINEAR_RE", WRITTEN_ANNOTATION_ONLY_RE)
    assert [layout.annotation_ranges(t) for t in texts] == new


@pytest.mark.parametrize("make", [
    lambda n: "(A1)" + " " * n + "x",
    lambda n: "[2]" + "\t" * n + "x",
    lambda n: "(A1) (M1)." + " " * n + "x",
])
def test_a_line_of_marks_then_blanks_and_text_is_read_in_linear_time(make):
    # before the fix: 1.46 s for one 20,000-character line ('(A1)' + 19,990 blanks + 'x'). A line longer than the layout's
    # bound (layout._MAX_LINE, 20,000 characters) is not read for annotations at all, so the worst case is a line just under it.
    c0 = time.process_time()
    layout.annotation_ranges(make(19_990))
    assert time.process_time() - c0 < 0.5
    ratio, small, large = growth(layout.annotation_ranges, make(4000), make(16000))
    assert ratio < LINEAR, (ratio, small, large)


def test_an_answer_of_lines_of_marks_blanks_and_text_is_read_by_the_front_end_in_seconds():
    # the parsers handoff's case at the contract's 400,000 characters: 20 lines; before the fix 29 s, after about 0.2 s
    answer = "\n".join(["(A1)" + " " * 19_990 + "x"] * 20)
    assert _document(answer) < 8.0
    # and the handoff's own line of 100,000 blanks, which the layout's line bound keeps out of the pattern: under a second
    assert _document("Output fell.\n(A1)" + " " * 100_000 + "x") < 1.0


def test_a_physics_answer_of_lines_of_marks_blanks_and_text_crosses_the_audited_hub_in_seconds():
    # before the fix: 30 s to receive and 14 s to audit five such lines (100,000 characters); after, about 2 s and 1 s
    receive_s, audit_s, rc, audit = _cross("\n".join(["(A1)" + " " * 19_990 + "x"] * 5))
    assert receive_s < 20.0 and audit_s < 15.0, (receive_s, audit_s)
    assert rc.status.value.startswith("ACCEPTED") and getattr(audit.state, "value", audit.state) != "AUDIT_FAILED"


# --------------------------------------------------------------------------- quoted spans of a line (sweep)


def test_the_quoted_spans_are_the_patterns_matches_and_the_mask_is_unchanged():
    alphabet = ['"', "“", "”", "«", "»", "„", "a", " ", "\n", "x = 5", "b" * 1999, "c" * 2000, "d" * 2001, "=", '""', "“”", "„“", "«»"]
    for text in _random_texts(alphabet, 54, 60000, longest=10):
        assert layout.quoted_spans(text) == [m.span() for m in layout._QUOTED_RE.finditer(text)], repr(text)[:200]
        assert layout._mask_quoted(text) == layout._QUOTED_RE.sub(lambda m: " " * len(m.group(0)), text), repr(text)[:200]


@pytest.mark.parametrize("opener", ["„", "“", "«", '"'])
def test_a_line_of_unclosed_quotation_marks_is_read_in_linear_time(opener):
    make = lambda n: "ab " + opener * n + "x"  # noqa: E731
    c0 = time.process_time()
    layout.joins_previous(make(19_990), make(19_990))  # before the fix: 1.25 s for '„'
    assert time.process_time() - c0 < 0.5
    ratio, small, large = growth(layout.is_working, make(4000), make(16000))
    assert ratio < LINEAR, (ratio, small, large)


def test_soft_wrapped_lines_of_unclosed_quotation_marks_are_read_by_the_front_end_in_seconds():
    # before the fix: 9.0 s for five such lines (100,000 characters)
    assert _document("\n".join(["ab " + "„" * 19_990 + "x"] * 5)) < 4.0


# --------------------------------------------------------------------------- the logical line of the segmenter (sweep)


def _whole_text_joins(view: str, logical: list, a: int, b: int) -> bool:
    """``segment._joins`` as it was before the fix: every rule asked of the whole joined logical line (the specification)."""
    line = view[a:b]
    prev = "\n".join(view[x:y].rstrip() for x, y, *_rest in logical)
    if layout.TABLE_ROW_RE.match(line):
        return False
    if layout.CONTINUATION_RE.match(line):
        return True
    if layout.CONNECTIVE_END_RE.search(prev.rstrip()) and not layout.TABLE_ROW_RE.match(prev):
        return True
    return bool(layout.SOFT_WRAP_NEXT_RE.match(line) and not layout.TERMINAL_PUNCT_RE.search(prev.rstrip().rstrip(":;")) and not prev.rstrip().endswith((":", ";"))
                and not layout.is_working(prev) and not layout.is_working(line))


def test_the_kept_logical_line_joins_exactly_as_the_whole_text_did():
    pieces = [" ", "  ", "\t", "ab", "cd", "so", "and", "therefore", ",", ":", ";", ".", ".)", "!", "?", "…", ")", "]", "”", '"', "“", "«", "»", "„",
              "=", "≈", "<", ">", "<=", "!=", "==", "5", "3", "×", "*", "^", "+", "-", "−", "/", "(", "$", "|", "x", "also", "x = 5", '"x = 5"', "5 *",
              '"a b"', "| a |"]
    rng = random.Random(55)
    checked = 0
    for _ in range(25000):
        lines = []
        for _ in range(rng.randint(2, 7)):
            ln = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 6)))
            lines.append(ln if ln.strip() else ln + "x")
        view = "\n".join(lines)
        spans, pos = [], 0
        for ln in lines:
            spans.append((pos, pos + len(ln)))
            pos += len(ln) + 1
        logical: list = []
        joined = segment_module._JoinedLogical()
        for i, (a, b) in enumerate(spans):
            if logical:
                expected = _whole_text_joins(view, logical, a, b)
                assert segment_module._joins(view, logical, a, b, joined) == expected, lines[: i + 1]
                checked += 1
                if not expected and rng.random() < 0.5:
                    logical.clear()
            logical.append((a, b, i, "prose", False, False))
    assert checked > 50000  # about 88,000 join decisions compared


@pytest.mark.parametrize("make", [
    lambda k: "ab cd\n" * k,                                   # soft-wrapped prose lines (before: 39 s at 8,000 lines)
    lambda k: "ab,\n" * k,                                     # lines ending on a comma
    lambda k: 'a "x = 5" b\n' + "ab cd\n" * k,                # a quoted equation, then soft-wrapped lines
    lambda k: "5 *\n" + '"a b"\n' * k + "3",                  # masked lines between the parts of a working line
    lambda k: "x = 1\n" + "= 1\n" * k,                         # a chain continued line after line (before: 6.7 s at 800 lines)
])
def test_an_answer_of_joined_lines_is_read_by_the_front_end_in_linear_time(make):
    assert _document(make(8000)) < 8.0
    ratio, small, large = growth(lambda t: build_document(t, "Answer the question.", "physics"), make(1000), make(4000), clear=clear_document_cache)
    assert ratio < LINEAR, (ratio, small, large)


def test_a_physics_answer_of_soft_wrapped_lines_crosses_the_audited_hub_in_seconds():
    # before the fix: 22 s to receive 4,000 such lines (24,000 characters)
    receive_s, audit_s, rc, _audit = _cross("ab cd\n" * 16_000)
    assert receive_s < 20.0 and audit_s < 20.0, (receive_s, audit_s)
    assert rc.status.value.startswith("ACCEPTED")


# --------------------------------------------------------------------------- a chain continued past the link limit (sweep)


def test_a_chain_continued_past_the_link_limit_is_named_and_its_later_lines_are_undecided():
    limit = 12
    doc = build_document("x = 1\n" + "= 1\n" * (limit + 3), "Answer the question.", "physics")
    lim = [f for f in doc.findings if f.code == "ST-LIM-001"]
    assert len(lim) == 1 and f"more than {limit} links" in lim[0].message
    # the first line holds one link and each continuing line one more: lines 2 to 12 continue the chain to 12 links, and the
    # 4 lines after them are each named undecided, never read in part and never dropped silently
    undecided = [r for r in doc.relations if r.outcome == "undecided" and r.code == "ST-LIM-001"]
    assert len(undecided) == 4, [(r.kind, r.outcome, r.code) for r in doc.relations]
    assert len([r for r in doc.relations if r.kind == "eq" and r.outcome == "check"]) == limit - 1


def test_control_a_chain_continued_within_the_link_limit_is_read_as_before():
    doc = build_document("x = 2 + 3\n= 5\n= 10 / 2\n= 5.0", "Answer the question.", "physics")
    assert not [f for f in doc.findings if f.code == "ST-LIM-001"]
    assert not [r for r in doc.relations if r.outcome == "undecided" and r.code == "ST-LIM-001"]
    wrong = build_document("x = 2 + 3\n= 5\n= 10 / 2\n= 6.0", "Answer the question.", "physics")
    assert [r for r in wrong.relations if r.kind != "span"] and not [f for f in wrong.findings if f.code == "ST-LIM-001"]


# --------------------------------------------------------------------------- a run of accuracy marks (stem handoff item 1)


def test_a_run_of_accuracy_marks_is_read_in_linear_time_through_the_generic_and_the_stem_readers():
    line = "x = 5" + " (A1)" * 8000 + " z"
    c0 = time.process_time()
    assert gp._accuracy_marked(line) is False and gp._accuracy_marked("x = 5 (A1)") is True
    assert time.process_time() - c0 < 0.5  # the unanchored search took about 8 s on this line (0.54 s at 2,000 marks, 2.07 s at 4,000)
    ratio, small, large = growth(gp._accuracy_marked, "x = 5" + " (A1)" * 2000 + " z", "x = 5" + " (A1)" * 8000 + " z")
    assert ratio < LINEAR, (ratio, small, large)


def test_a_physics_answer_with_a_run_of_accuracy_marks_crosses_the_audited_hub_in_seconds():
    receive_s, audit_s, rc, audit = _cross("x = 5" + " (A1)" * 8000 + " z")
    assert receive_s < 10.0 and audit_s < 10.0, (receive_s, audit_s)
    assert rc.status.value.startswith("ACCEPTED") and getattr(audit.state, "value", audit.state) != "AUDIT_FAILED"


# --------------------------------------------------------------------------- the sweep: the modules this fix touched

#: the standard hostile runs of the gate (about 20,000 characters, each followed by a character that defeats the match) and the
#: compound shapes this sweep found: a mark then a blank run, soft-wrapped lines, unclosed quotation marks, a continued chain
SHAPES = {
    "blanks": " " * 20_000 + "x", "tabs": "\t" * 20_000 + "x", "line breaks": "\n" * 20_000 + "x", "stops": "." * 20_000 + "x",
    "closing marks": ")\"”’]»" * 3333 + "x", "mark labels": "x = 5" + " (A1)" * 4000 + " z", "parentheses": "(" * 20_000 + "x",
    "brackets": "[" * 20_000 + "x", "fence openers": "```a\n" * 4000 + "x", "number words": "one and " * 2500 + "x", "= links": "x = " * 5000 + "!",
    "list markers": "\n1. " * 5000 + "x", "mark then blanks": "(A1)" + " " * 19_990 + "x", "allocation then tabs": "[2]" + "\t" * 19_990 + "x",
    "soft-wrapped lines": "ab cd\n" * 3333, "comma lines": "ab,\n" * 5000, "connective lines": "it rose so\n" * 1818,
    "unclosed low marks": "ab " + "„" * 19_990 + "x", "unclosed curly marks": "“" * 20_000 + "x", "continued chain": "x = 1\n" + "= 1\n" * 4999,
    "quoted equation then wraps": 'a "x = 5" b\n' + "ab cd\n" * 3330,
}


def _sweep(entries, bound: float) -> None:
    slow = []
    for shape, text in SHAPES.items():
        for name, call in entries(text):
            empty_caches()
            c0 = time.process_time()
            try:
                call()
            except (ValueError, OverflowError):
                pass  # a refusal of hostile input fails loudly, which is allowed; a stall is not
            spent = time.process_time() - c0
            if spent > bound:
                slow.append((name, shape, round(spent, 2)))
    assert not slow, slow


def test_sweep_layout_with_the_compound_shapes():
    _sweep(lambda t: [("annotation_ranges", lambda: layout.annotation_ranges(t)), ("quoted_spans", lambda: layout.quoted_spans(t)),
                      ("is_working", lambda: layout.is_working(t)), ("joins_previous", lambda: layout.joins_previous(t, t)),
                      ("JoinedLine", lambda: [layout.JoinedLine(t).add(t)]), ("strip_trailing_annotations", lambda: layout.strip_trailing_annotations(t)),
                      ("plain_line", lambda: layout.plain_line(t)), ("label_only_rest", lambda: layout.label_only_rest(t))], bound=1.0)


def test_sweep_segment_and_document_with_the_compound_shapes():
    _sweep(lambda t: [("build_document/physics", lambda: build_document(t, "Answer the question.", "physics")),
                      ("build_document/mathematics_aa", lambda: build_document(t, "Solve for x.", "mathematics_aa")),
                      ("build_document/computer_science", lambda: build_document(t, "Convert the value.", "computer_science"))], bound=8.0)
