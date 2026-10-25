"""Re-run review finding parser-safety-4: the shared sentence splitter (History and STEM segmentation, the core pack, the
arithmetic extractor) found sentence ends with ``[.?!]+[closers]*(?=\\s+\\S)`` through ``finditer``. A long run of '!', '.'
or '?' with no white space after it was retried from every position of the run, which is quadratic: 6.5 s for a run of
20,000, minutes at the 400,000-character bound of an answer, against the documented "every scan is linear". The end marks
are now read in one pass that gives exactly the matches the pattern gave."""
from __future__ import annotations

import random
import re

import pytest

from epinoic_logic.adapters.history_specialist import sentences as S
from epinoic_logic.adapters.history_specialist.sentences import sentence_boundaries, split_clauses, split_sentences

from ..timing import measure

BOUND = 400_000


def reference_boundaries(text: str, *, semicolons: bool = False, capital_next: bool = True) -> list[int]:
    """The splitter as it read the end marks before (the pattern through ``finditer``), kept as the reference answer the
    one-pass scan reproduces; quadratic on a long run of marks, so it is run here on short texts only."""
    original = text
    text, json_spans = S._json_cuts(text)
    spans = sorted(S._quotation_spans(text))
    starts, furthest_end = S._span_index(spans)
    out: list[int] = []
    for a, b in json_spans:
        if original[:a].strip():
            out.append(a)
        nxt = S._WS_RE.match(original, b)
        after = nxt.end() if nxt else b
        if after < len(original):
            out.append(after)
    marks = "[.?!;]+" if semicolons else "[.?!]+"
    for m in re.finditer(rf"{marks}[{S._CLOSERS}]*(?=\s+\S)", text):
        if spans and S._inside_any(starts, furthest_end, m.start(), m.end()):
            continue
        if m.group(0)[0] != ";" and S.abbreviation_ends_at(text, m.end()):
            continue
        nxt = S._WS_RE.match(text, m.end())
        start = nxt.end() if nxt else m.end()
        if start >= len(text):
            continue
        if capital_next and m.group(0)[0] != ";" and not S._STARTS_SENTENCE_RE.match(text, start):
            continue
        out.append(start)
    for m in S._JSON_END_RE.finditer(text):
        if spans and S._inside_any(starts, furthest_end, m.start(), m.end()):
            continue
        nxt = S._WS_RE.match(text, m.end())
        start = nxt.end() if nxt else m.end()
        if start < len(text):
            out.append(start)
    return sorted(set(out))


@pytest.mark.parametrize("mark", ["!", ".", "?", ";"])
def test_a_run_of_end_marks_at_the_answer_bound_is_read_in_linear_time(mark: str):
    text = "x = 9" + mark * (BOUND - 5)
    for fn in (sentence_boundaries, split_sentences, split_clauses):
        timing = measure(lambda: fn(text), 1.0, repeat=3, label=f"{fn.__name__} on a run of {mark!r} x {BOUND - 5}")
        assert timing.holds, str(timing)
    assert sentence_boundaries(text) == [] and split_clauses(text) == [text]


def test_the_history_hub_reads_a_long_run_of_marks_in_linear_time():
    """The finding's hub reproduction (12 s at 10,000 marks, 35 s at 20,000)."""
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.engine import SolverConfig
    from epinoic_logic.integrity import WorkPlan

    def cross():
        hub = RouterHub(signing_key=b"rerun-review-sentences-key-012345", config=SolverConfig(timeout_ms=2000, memory_max_mb=None))
        hub.open_task(WorkPlan(plan_id="pl", request_id="rq", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"]))
        message, _request, _receipt = hub.dispatch("t", "history-specialist", "Explain the main point.")
        return hub.receive("t", message.message_id, "The answer is clear" + "!" * 20_000, agent_id="history-specialist", report_id="r1")

    timing = measure(cross, 2.0, repeat=3, label="History hub crossing with a run of 20,000 '!'")
    assert timing.holds, str(timing)
    assert all(reply is not None for reply, _receipt in timing.results)


@pytest.mark.parametrize("mark", ["!", "."])
def test_the_stem_front_end_stays_within_its_documented_bound(mark: str):
    """The finding's STEM reproduction at the response bound (over 600 s before); stem/README: each stress case under 2 s."""
    from epinoic_logic.stem import build_document

    text = "x = 9" + mark * (BOUND - 5)
    timing = measure(lambda: build_document(text, None, "physics"), 2.0, repeat=3, label=f"STEM front end on a run of {mark!r} at {BOUND}")
    assert timing.holds, str(timing)


def _random_texts(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    alphabet = list(".?!;\"”’')]»\\ \t\n  xyAZ09:,-{}[]“‘«„") + [" Then", " The", "c. ", "e.g. ", " A. J. ", "\"Quote.\" ", "Mr. ", "{\"a\": \"b.\"} "]
    return ["".join(rng.choice(alphabet) for _ in range(rng.randint(1, 60))) for _ in range(n)]


REAL = [
    "The crash of 1929 followed speculative excess. Margin buying had \"inflated prices\" for years; banks failed in waves.",
    "From c. 200 million tonnes in 1928 to c. 100 million in 1932, a fall of 25 per cent. Then output recovered!",
    "A. J. P. Taylor argued otherwise (see p. 12). \"Was it planned?\" he asked. 'No.' The record says so.",
    "Prices rose 4.2 per cent; wages fell. Why? Because demand collapsed... Recovery came later!! «Indeed.» 1933 was worse.",
    "He wrote [1788] a letter.] Then he left. {\"status\": \"ACCEPTED. Delivered.\"} The narrator continues.",
    "x = 9!!! y = 4?? z.) Next line.\n\nNew paragraph; with a clause. And more.",
]


@pytest.mark.parametrize("kw", [{}, {"semicolons": True, "capital_next": False}, {"semicolons": True}, {"capital_next": False}],
                         ids=["sentences", "clauses", "semicolons with capitals", "no capital needed"])
def test_the_one_pass_scan_gives_exactly_the_patterns_boundaries(kw: dict):
    """Control: the reading is unchanged, on real paragraphs and on random texts built from the characters that matter
    (marks, closing marks, kinds of white space, quotation marks, brackets, abbreviations and initials)."""
    for text in REAL + _random_texts(4000, seed=11):
        assert sentence_boundaries(text, **kw) == reference_boundaries(text, **kw), repr(text)


def test_split_sentences_still_reads_the_paragraphs_it_read():
    """Control on the readings the parsers rely on."""
    assert split_sentences(REAL[0]) == ["The crash of 1929 followed speculative excess.", "Margin buying had \"inflated prices\" for years; banks failed in waves."]
    assert split_clauses(REAL[0])[-1] == "banks failed in waves."
    assert split_sentences(REAL[1])[0].startswith("From c. 200 million") and len(split_sentences(REAL[1])) == 2
