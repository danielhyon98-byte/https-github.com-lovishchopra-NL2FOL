"""Integration gate 1, handoff fixer: the STEM front end's readers whose cost grew with the square of the input.

Critical rule (input that stalls the service is a security finding, not optimisation work): each reader is fixed at its
cause, held equal to what it computed before on random and hostile inputs, and timed on the worst-case input its finding
names, with a wide margin and a growth ratio (a 4x input costs about 4x for a linear reader, about 16x for a quadratic one).

* parser-safety-5: ``stem.layout.plain_line`` searched ``EMPHASIS_RE``, whose lazy body read to the end of the line from
  every unclosed opener ('**a ' * k: 3.68 s at 20,000 characters; a Physics hub 11.5 s at 20,000). It reads the matches in
  one pass (``layout.emphasis_spans``).
* parser-safety-10: the verbal arithmetic reader (``stem.spans._verbal``) restarted an unterminated 'plus' chain at every
  operand ('5 plus ' * k: 3.45 s at 20,000 characters). It resumes at the chain's end.
* parser-safety-11: ``stem.segment.segment_statements`` looked every list marker up for every list line ('- x = 1\\n' * k:
  7.25 s at 100,000 characters). The markers are indexed by line once.
* overseer handoff item 2: ``stem.layout.annotation_ranges`` and the generic parser's trailing-annotation strip searched
  ``TRAILING_ANNOTATION_RE`` as written, re-reading a run of mark annotations from each of them ('[1] ' * k: 3.88 s at
  16,000 characters, in both parsers and in the overseer's re-parse). Each maximal run is found once
  (``layout.trailing_annotation_span``); the two patterns stay the same strings (tests/stem/test_layout.py).
"""
from __future__ import annotations

import random
import time

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches import generic_parser as gp
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_overseer import EngineKey, KeyRing, TransferAuditor
from epinoic_logic.stem import build_document, clear_document_cache, layout
from epinoic_logic.stem import spans as stem_spans
from epinoic_logic.stem.lexer import Token, lex

from ..growth import growth
from ..timing import empty_caches

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
KEY = b"integration-gate-1-handoff-stem-readers-key-01"
SECRET = b"integration-gate-1-handoff-stem-readers-secret-0123"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)


def _random_texts(alphabet, seed: int, n: int, longest: int = 24):
    rng = random.Random(seed)
    for _ in range(n):
        yield "".join(rng.choice(alphabet) for _ in range(rng.randint(0, longest)))


def _audited_physics_hub():
    keyring = KeyRing({k: EngineKey(KEY) for k in ("hub", "channel", "default", "integrity")}, SECRET)
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=TransferAuditor(keyring, replay_mode="inline", eager=True, shadow="always"))
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer",
                           selected_agent_ids=["physics-specialist"]))
    m, _req, _rq = hub.dispatch("t", "physics-specialist", "Answer the question.")
    return hub, m


def _cross(text: str) -> tuple[float, float, object, object]:
    """Receive ``text`` on an audited Physics hub and audit the task: (receive s, audit s, receipt, audit)."""
    hub, m = _audited_physics_hub()
    try:
        t0 = time.perf_counter()
        _reply, rc = hub.receive("t", m.message_id, text, agent_id="physics-specialist", report_id="r1")
        t1 = time.perf_counter()
        audit = hub.audit("t")
        t2 = time.perf_counter()
    finally:
        hub.close()
    return t1 - t0, t2 - t1, rc, audit


# --------------------------------------------------------------------------- emphasis markers (parser-safety-5)


def _old_plain_line(line: str) -> tuple[str, list[int]]:
    """``plain_line`` as it was built from the pattern's own matches before the gate."""
    out: list[str] = []
    index: list[int] = []
    pos = 0
    for m in layout.EMPHASIS_RE.finditer(line):
        out.append(line[pos:m.start()])
        index.extend(range(pos, m.start()))
        out.append(m.group(2))
        index.extend(range(m.start(2), m.end(2)))
        pos = m.end()
    out.append(line[pos:])
    index.extend(range(pos, len(line)))
    return "".join(out), index


def test_the_emphasis_spans_are_the_patterns_matches_and_plain_line_is_unchanged():
    alphabet = ["*", "**", "_", "__", "`", "a", "b", " ", "\n", "1", "é", ".", "-", "\t", "x_y", "*a*", "**b**", "_c_", "`d`", "ü", "٣", " ", "(", ")",
                "***", "a*", "*a", "_1_", " "]
    for text in _random_texts(alphabet, 11, 40000, longest=18):
        assert layout.emphasis_spans(text) == [(m.start(), m.start(2), m.end(2), m.end()) for m in layout.EMPHASIS_RE.finditer(text)], repr(text)
        assert layout.plain_line(text) == _old_plain_line(text), repr(text)
    for text in ("**Given:** $v = 20$ m s⁻¹ and *t* = 4.0 s", "**a " * 50, "*" * 40, "_" * 40, "a_b_c *x* __y__ **z**", "** a**", "**a **"):
        assert layout.plain_line(text) == _old_plain_line(text), repr(text)
    assert layout.plain_line("**Answer:** a = *5.0* m s⁻²")[0] == "Answer: a = 5.0 m s⁻²"


def test_plain_line_reads_unclosed_emphasis_in_linear_time():
    # the finding's input; before the gate 0.89 s at 10,000 characters and 3.68 s at 20,000
    t = time.perf_counter()
    layout.plain_line("**a " * (400000 // 4))
    assert time.perf_counter() - t < 2.0
    ratio, small, large = growth(layout.plain_line, "**a " * 2000, "**a " * 8000)
    assert ratio < LINEAR, (ratio, small, large)


def test_a_physics_answer_of_unclosed_emphasis_crosses_the_audited_hub_in_seconds():
    # before the gate: a Physics hub took 11.5 s at 20,000 characters; the audit re-runs plain_line on the response
    receive_s, audit_s, rc, audit = _cross("**a " * 5000)
    assert receive_s < 10.0 and audit_s < 10.0, (receive_s, audit_s)
    assert rc.status.value.startswith("ACCEPTED") and getattr(audit.state, "value", audit.state) != "AUDIT_FAILED"


# --------------------------------------------------------------------------- verbal arithmetic (parser-safety-10)


def _old_verbal(toks):
    """``stem.spans._verbal`` as it was before the gate: an unterminated chain restarted at its next token."""
    out = []
    n = len(toks)
    i = 0
    while i < n:
        if toks[i].kind != "NUM":
            i += 1
            continue
        synth = [toks[i]]
        k = i + 1
        ops = 0
        done = False
        while k < n:
            t = toks[k]
            w = t.text.lower() if t.kind == "IDENT" else ""
            if w in stem_spans._VERBAL_OPS:
                step = 1
                if w in ("multiplied", "divided"):
                    if k + 1 < n and toks[k + 1].kind == "IDENT" and toks[k + 1].text.lower() == "by":
                        step = 2
                    else:
                        break
                if k + step < n and toks[k + step].kind == "NUM":
                    synth.append(Token("OP", stem_spans._VERBAL_OPS[w], t.start, toks[k + step - 1].end, True))
                    synth.append(toks[k + step])
                    ops += 1
                    k += step + 1
                    continue
                break
            eq_step = 0
            if w in stem_spans._VERBAL_EQ:
                eq_step = 1
            elif w == "is" and k + 2 < n and toks[k + 1].text.lower() == "equal" and toks[k + 2].text.lower() == "to":
                eq_step = 3
            elif t.kind == "REL" and t.text == "=":
                eq_step = 1
            if eq_step and ops and k + eq_step < n and toks[k + eq_step].kind == "NUM":
                synth.append(Token("REL", "=", t.start, toks[k + eq_step - 1].end, True))
                synth.append(toks[k + eq_step])
                out.append((i, k + eq_step + 1, tuple(synth)))
                i = k + eq_step + 1
                done = True
            break
        if not done:
            i += 1
    return out


def test_the_verbal_reader_finds_what_it_found_before():
    words = ["5", "plus", "minus", "times", "multiplied", "by", "divided", "equals", "gives", "makes", "is", "equal", "to", "=", "x", "making",
             "3.5", "10", "and", "m", "Plus", "2", "−"]
    rng = random.Random(12)
    for _ in range(20000):
        text = " ".join(rng.choice(words) for _ in range(rng.randint(1, 16)))
        toks = lex(text, 0, len(text), mode="plain", values=False).tokens
        assert stem_spans._verbal(toks) == _old_verbal(toks), repr(text)
    toks = lex("3 plus 4 equals 7 and 5 times 6 is equal to 30", values=False).tokens
    assert [(a, b) for a, b, _s in stem_spans._verbal(toks)] == [(0, 5), (6, 13)]


def test_an_unterminated_verbal_chain_is_read_in_linear_time():
    # the finding's input; before the gate 0.81 s at 10,000 characters, 3.45 s at 20,000, 6.30 s at 40,000
    make = lambda n: "5 plus " * (n // 7) + "5 making 10"  # noqa: E731
    clear_document_cache()
    t = time.perf_counter()
    build_document(make(40000), None, "physics")
    assert time.perf_counter() - t < 4.0
    toks_small = lex(make(4000), values=False).tokens
    toks_large = lex(make(16000), values=False).tokens
    ratio, small, large = growth(stem_spans._verbal, toks_small, toks_large)
    assert ratio < LINEAR, (ratio, small, large)


def test_a_physics_answer_of_an_unterminated_verbal_chain_crosses_the_audited_hub_in_seconds():
    # before the gate: a Physics hub took 12.43 s at 20,000 characters
    receive_s, audit_s, rc, _audit = _cross("5 plus " * (20000 // 7) + "5 making 10")
    assert receive_s < 15.0 and audit_s < 15.0, (receive_s, audit_s)
    assert rc.status.value.startswith("ACCEPTED")


# --------------------------------------------------------------------------- list markers (parser-safety-11)


def test_list_items_are_segmented_as_before():
    doc = build_document("- x = 1\n* y = 2\n1. a = 3\n  - nested = 6\n- (b) c = 7\ntext line.", None, "physics")
    assert [doc.text[s.start:s.end] for s in doc.statements][:5] == ["x = 1", "y = 2", "a = 3", "nested = 6", "c = 7"]
    parts = [s.part for s in doc.statements]
    assert parts[4] == "(b)", parts


def test_a_long_list_is_segmented_in_linear_time():
    # the finding's input; before the gate 0.88 s at 25,000 characters, 2.03 s at 50,000, 7.25 s at 100,000
    make = lambda n: "- x = 1\n" * (n // 8)  # noqa: E731
    clear_document_cache()
    t = time.perf_counter()
    build_document(make(100000), None, "physics")
    assert time.perf_counter() - t < 6.0

    def run(text):
        clear_document_cache()
        build_document(text, None, "physics")
    ratio, small, large = growth(run, make(12500), make(50000), floor_s=0.1)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- trailing mark annotations (overseer handoff 2)


def test_the_trailing_annotation_span_is_the_searchs_span():
    alphabet = ["[1]", "[2 marks]", "[ 3 spare ]", "(3 marks)", "M1", "A1", "(M1)", "(A2)", "AG", "R1", "N2", " ", "  ", "\t", "\n", ".", ";", ",",
                "x", "y.", "(", ")", "[", "]", "12", "123", "= 5", "M", "A", " [1]", "  M1", "\t(A1)", " ", "(M12)", "[12]", "A123"]
    for text in _random_texts(alphabet, 13, 40000, longest=16):
        m = layout.TRAILING_ANNOTATION_RE.search(text)
        assert layout.trailing_annotation_span(text) == (m.span() if m else None), repr(text)
        old = layout.TRAILING_ANNOTATION_RE.sub("", text).rstrip()
        assert layout.strip_trailing_annotations(text) == old, repr(text)
        assert gp._strip_annotations(text) == gp._TRAILING_ANNOTATION_RE.sub("", text).rstrip(), repr(text)
    assert layout.strip_trailing_annotations("v = 30 m/s  A1") == "v = 30 m/s"
    assert layout.strip_trailing_annotations("only 9 [1].") == "only 9."
    assert gp._TRAILING_ANNOTATION_RE.pattern == layout.TRAILING_ANNOTATION_RE.pattern


@pytest.mark.parametrize("unit", ["[1] ", "  M1", " (M1)", "\t(A1)", "[2 marks] "])
def test_a_line_of_mark_annotations_is_read_in_linear_time(unit):
    # the finding's inputs; before the gate '[1] ' * k took 3.88 s at 16,000 characters, '  M1' * k 3.75 s
    make = lambda n: unit * (n // len(unit)) + " y"  # noqa: E731
    t = time.perf_counter()
    layout.annotation_ranges(make(19990))
    gp._strip_annotations(make(400000))
    assert time.perf_counter() - t < 2.0
    ratio, small, large = growth(layout.annotation_ranges, make(4000), make(16000))
    assert ratio < LINEAR, (ratio, small, large)
    ratio, small, large = growth(gp._strip_annotations, make(4000), make(16000))
    assert ratio < LINEAR, (ratio, small, large)


def test_a_physics_answer_of_mark_annotations_crosses_the_audited_hub_in_seconds():
    # before the gate: 20 such lines of 19,999 characters cost about 2 minutes in each parser and in the overseer's re-parse
    empty_caches()
    receive_s, audit_s, rc, _audit = _cross(("[1] " * 4999 + "x\n") * 5)
    assert receive_s < 15.0 and audit_s < 15.0, (receive_s, audit_s)
    assert rc.status.value.startswith("ACCEPTED")
