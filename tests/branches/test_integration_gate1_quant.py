"""Integration gate 1 (before arena round 8): the prose arithmetic reader (``branches/quant.py``) on hostile input, and the
direction of a pair whose later figure opens written arithmetic.

Linear time (critical findings parser-safety-2, -7, -8 and -12, which stalled the hub in every subject):

* a figure in words reads at most five number words (``quant.MAX_NUMBER_WORDS``), so no pattern tries every length of a long
  run from each of its words; a sentence holding a longer run ('one hundred and ' * k, 'twenty-three ' * k) is reported
  undecided (CORE-QNT-001, ``LONG_NUMBER_RUN_REASON``), never read as a figure of its first words. Below that length every
  pattern matches what the unbounded pattern matched (an equality test against the old patterns);
* the totals' keyword is tested by its first letter before the alternation, and a sentence holding no keyword of a total is
  not searched (the same matches);
* a figure in scientific notation in the SI reading starts where no digit precedes ('0b111...1');
* a chain of '=' links is read once (the first link with an operator is kept as the links are read);
* the pair reader looks up a continuation's earlier pair and the pairs already read by bisection.

Each fix is held to the worst-case input of its finding with a wide time bound and to a growth ratio (CPU time, a 4x input),
and every receipt of the recorded rounds is unchanged by the linear readers.

The pair direction (major, ec-e1, end-to-end B2 residual): 'the price they keep falls from $1.60 to $2.00 − $0.60 = $1.40' ends
at the arithmetic's stated result, $1.40; a pair whose arithmetic states no result is reported undecided; a check that rests
on that reading fails as a warning (INT-SUBJ-004), never an error; a plain pair keeps its reading."""
from __future__ import annotations

import random
import re
import time

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches import quant as q
from epinoic_logic.branches.quant import (
    ARITH_ENDPOINT_REASON, LONG_NUMBER_RUN_REASON, MAX_NUMBER_WORDS, extract_quant_checks, undecided_quant_statements, worked_equations,
)
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan

from ..growth import growth

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
KEY = b"integration-gate-1-parsers-quant-key-0123"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)

#: The number-word pattern before the gate: every length of a run of number words.
OLD_WNUM = rf"(?:{q._WNUM_TOKEN})(?:(?:[\s-]+and)?[\s-]+(?:{q._WNUM_TOKEN}|hundred))*(?![a-z])"


def _old(pattern: "re.Pattern[str]") -> "re.Pattern[str]":
    """``pattern`` as it was before the gate: unbounded number words, no first-letter test of a total's keyword, no digit guard
    before a figure in scientific notation."""
    src = pattern.pattern.replace(q._WNUM, OLD_WNUM).replace(q._TOTAL_KEYWORD_START, "").replace(rf"(?<!\d)(?:{q.si_digits_pattern()})", q.si_digits_pattern())
    return re.compile(src, pattern.flags)


def _all_reading_checks(text: str) -> None:
    q._analyse.cache_clear()
    q._extract_cached.cache_clear()
    for reading in (q.GENERAL, q.SI_READING):
        extract_quant_checks(text, request_id="r", claim_id="c", reading=reading)
        undecided_quant_statements(text, reading=reading)


def _timed(fn, *args) -> float:
    t = time.perf_counter()
    fn(*args)
    return time.perf_counter() - t


# --------------------------------------------------------------------------- number words joined by 'and' (parser-safety-2)


def test_the_total_pattern_reads_a_run_of_number_words_in_linear_time():
    # the finding's input: 'one hundred and ' * k; before the gate 0.98 s at 400 characters, 32.71 s at 1,200 (cubic)
    assert _timed(q._TOTAL_RE.search, "one hundred and " * (1200 // 16)) < 1.0
    assert _timed(q._si_patterns().total.search, "one hundred and " * (1200 // 16)) < 1.0
    ratio, small, large = growth(q._TOTAL_RE.search, "one hundred and " * 60, "one hundred and " * 240)
    assert ratio < LINEAR, (ratio, small, large)
    ratio, small, large = growth(q._si_patterns().total.search, "one hundred and " * 60 + "making ten", "one hundred and " * 240 + "making ten")
    assert ratio < LINEAR, (ratio, small, large)


def test_a_2500_character_answer_of_number_words_is_read_well_under_a_second_and_reported_undecided():
    text = "one hundred and " * (2500 // 16)
    assert _timed(_all_reading_checks, text) < 1.0
    [u] = undecided_quant_statements(text)
    assert u.reason == LONG_NUMBER_RUN_REASON and u.phrase.startswith("one hundred and one hundred")
    assert extract_quant_checks(text, request_id="r", claim_id="c") == []


@pytest.mark.parametrize("subject,agent", [("History", "history-specialist"), ("Physics", "physics-specialist")])
@pytest.mark.parametrize("unit", ["one hundred and ", "twenty-three "])
def test_the_hub_crosses_20000_characters_of_number_words_in_seconds(subject, agent, unit):
    # before the gate both crossings ran past a 45 s timeout
    text = unit * (20000 // len(unit))
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, "Answer the question.")
    t = time.perf_counter()
    _reply, rc = hub.receive("t", m.message_id, text, agent_id=agent, report_id="r1")
    assert time.perf_counter() - t < 15.0
    assert rc.status.value.startswith("ACCEPTED")


def test_a_sentence_with_a_long_run_of_number_words_is_named_and_the_others_are_read():
    text = ("Output rose from 20 to 30 million tonnes in 1932, a rise of 50 per cent. "
            "The plan listed one two three four five six seven targets.")  # six words or more: no figure in words
    assert [c.kind for c in extract_quant_checks(text, request_id="r", claim_id="c")] == ["percent_change"]
    [u] = [u for u in undecided_quant_statements(text) if u.reason == LONG_NUMBER_RUN_REASON]
    assert u.sentence == 2 and "one two three four five" in u.phrase


@pytest.mark.parametrize("text,kinds", [
    ("Exports rose from two hundred and sixty to three hundred, a rise of about 15 per cent.", ["percent_change"]),
    ("The party won twenty seats and thirty seats, making fifty seats in total.", ["total"]),
    ("Membership grew from nine hundred and ninety-nine to 1,998, a rise of about 100 per cent.", ["percent_change"]),
    ("The army grew from nineteen to twenty-three divisions, a rise of about 21 per cent.", ["percent_change"]),
    ("The crowd grew from twenty-one hundred and twenty-two to 4,244, a rise of 100 per cent.", ["percent_change"]),  # five words
])
def test_figures_of_up_to_five_number_words_keep_their_readings(text, kinds):
    checks = extract_quant_checks(text, request_id="r", claim_id="c")
    assert [c.kind for c in checks] == kinds
    for c in checks:
        assert verify(c.problem).status.value == "ENTAILED", c.sentence
    assert not [u for u in undecided_quant_statements(text) if u.reason == LONG_NUMBER_RUN_REASON]
    assert MAX_NUMBER_WORDS == 5


_WORDS = ["one", "two", "three", "nine", "ten", "twenty", "thirty", "forty-five", "sixty", "hundred", "and", "plus", "5", "1,200", "2.5",
          "$3", "million", "per cent", "%", "seats", "tonnes", "people", "making", "in total", "a total of", "together", "totals", "giving",
          "from", "to", "in 1990", "in 1991", "rose", "fell", "times", "twice", "as", "about", ",", ".", ";", "-"]


def _texts(seed: int, n: int):
    rng = random.Random(seed)
    for _ in range(n):
        text = " ".join(rng.choice(_WORDS) for _ in range(rng.randint(2, 26)))
        if q._LONG_NUMBER_RUN_RE.search(text) is None:  # below the bound the patterns must read exactly what they read before
            yield text


@pytest.mark.parametrize("name", ["_TOTAL_RE", "_FROM_TO_RE", "_AND_DATED_RE", "_LIST_ITEM_RE", "_CONT_RE", "_SHARE_RE", "_TIMES_RE", "_LONE_FIG_RE",
                                  "_DUR_PHRASE_RE", "_COMPARE_RE"])
def test_below_the_bound_every_number_word_pattern_matches_what_it_matched(name):
    new = getattr(q, name)
    old = _old(new)
    assert old.pattern != new.pattern or name not in ("_TOTAL_RE", "_FROM_TO_RE")
    for text in _texts(hash(name) % 1000, 1500):
        assert [m.span() + (m.groupdict(),) for m in new.finditer(text)] == [m.span() + (m.groupdict(),) for m in old.finditer(text)], text


def test_below_the_bound_the_si_patterns_match_what_they_matched():
    for field in q._Patterns._fields:
        new = getattr(q._si_patterns(), field)
        old = _old(new)
        for text in list(_texts(7, 800)) + ["0b" + "1" * 30, "2e12345 and 3 making 4", "3,14e5 plus 2 making 5", "x 12.5e3 and 2.5 × 10³ making 3e3"]:
            assert [m.span() + m.groups() for m in new.finditer(text)] == [m.span() + m.groups() for m in old.finditer(text)], (field, text)


def test_the_total_keyword_prefilter_changes_no_match():
    for text in _texts(3, 3000):
        assert q._search_total(q._TOTAL_RE, text) is None or q._search_total(q._TOTAL_RE, text).span() == _old(q._TOTAL_RE).search(text).span()
        if q._TOTAL_HINT_RE.search(text) is None:
            assert _old(q._TOTAL_RE).search(text) is None


# --------------------------------------------------------------------------- runs of number words in pairs (parser-safety-7)


def test_the_pair_reader_is_linear_on_runs_of_number_words():
    # before the gate: 0.32 / 1.22 / 5.58 s at 2,500 / 5,000 / 10,000 characters (SI: 0.45 / 1.87 / 7.80 s)
    assert _timed(q._pairs, "twenty-three " * (10000 // 13)) < 1.0
    assert _timed(q._pairs, "twenty-three " * (10000 // 13), q._si_patterns()) < 1.0
    ratio, small, large = growth(q._pairs, "twenty-three " * 150, "twenty-three " * 600)
    assert ratio < LINEAR, (ratio, small, large)
    [u] = undecided_quant_statements("twenty-three " * 200)
    assert u.reason == LONG_NUMBER_RUN_REASON


def _ref_pairs(clause, pat=q._GENERAL_PATTERNS):
    """The pair reader before the gate: every earlier pair read again for each continuation and each dated pair."""
    pairs, covered = [], []
    if not q._FIGURE_HINT_RE.search(clause):
        return pairs

    def overlaps(s, e):
        return any(s < b and a < e for a, b in covered)
    for m in pat.from_to.finditer(clause):
        p = q._Pair(m.start(), m.end(), q._fig_of(m, 1), q._fig_of(m, 2))
        pos = m.end()
        while True:
            li = pat.list_item.match(clause, pos)
            if not li or len(p.tail) >= q._MAX_SERIES:
                break
            p.tail.append(q._fig_of(li, 3))
            pos = li.end()
        p.end = pos
        if not p.tail:
            p = q._arith_endpoint(clause, p, pat)
        pairs.append(p)
        covered.append((p.start, p.end))
    for m in pat.cont.finditer(clause):
        if overlaps(m.start(), m.end()):
            continue
        prior = [p for p in pairs if p.end <= m.start()]
        if not prior:
            continue
        p = q._Pair(m.start(), m.end(), max(prior, key=lambda x: x.end).last, q._fig_of(m, 3 if m.group("n3") else 4))
        pos = m.end()
        while True:
            li = pat.list_item.match(clause, pos)
            if not li or len(p.tail) >= q._MAX_SERIES:
                break
            p.tail.append(q._fig_of(li, 3))
            pos = li.end()
        p.end = pos
        if not p.tail:
            p = q._arith_endpoint(clause, p, pat)
        pairs.append(p)
        covered.append((p.start, p.end))
    for m in pat.and_dated.finditer(clause):
        if overlaps(m.start(), m.end()):
            continue
        p = q._Pair(m.start(), m.end(), q._fig_of(m, 1), q._fig_of(m, 2))
        pairs.append(p)
        covered.append((p.start, p.end))
    pairs.sort(key=lambda p: p.start)
    return pairs


_PIECES = ["from 5 to 10", "from 5 in 1990 to 10 in 1991", "rose from 2.5 million to 3 million", ", 4 million in 1992", " and 6 in 1993",
           " before rising to 12", " then to 14 per cent", " and later reaching 20", "7 in 1980 and 8 in 1981", "8 in 1982, and 9 in 1983",
           ", ", " ", "; ", " and ", "from 1.60 to 2.00 − 0.60 = 1.40", " of 3 to 4", "fell from 40 per cent to 35 per cent", " before falling to 30"]


def test_the_pair_reader_reads_the_pairs_the_scan_of_every_pair_read():
    rng = random.Random(11)
    for _ in range(4000):
        text = "".join(rng.choice(_PIECES) for _ in range(rng.randint(1, 9)))
        for pat in (q._GENERAL_PATTERNS, q._si_patterns()):
            got = [(p.start, p.end, p.before, p.after, tuple(p.tail), p.via, p.arith) for p in q._pairs(text, pat)]
            assert got == [(p.start, p.end, p.before, p.after, tuple(p.tail), p.via, p.arith) for p in _ref_pairs(text, pat)], text


@pytest.mark.parametrize("make", [
    lambda k: "from 5 to 10 before rising to 12 " * (k // 33),               # thousands of continuations in one sentence
    lambda k: "from 5 to 10, " * (k // 28) + "5 in 1990 and 6 in 1991, " * (k // 50),  # and dated pairs after them
])
def test_the_pair_reader_is_linear_in_its_pairs(make):
    # before the gate the continuations took 4.3 s at 160,000 characters (quadratic)
    assert _timed(q._pairs, make(160000)) < 3.0
    ratio, small, large = growth(q._pairs, make(10000), make(40000))
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- a long based numeral in the SI reading (parser-safety-8)


@pytest.mark.parametrize("field", ["total", "share"])
def test_the_si_patterns_read_a_long_based_numeral_in_linear_time(field):
    # before the gate: 0.14 / 0.62 / 2.67 s at 2,000 / 4,000 / 8,000 characters
    pattern = getattr(q._si_patterns(), field)
    assert _timed(pattern.search, "0b" + "1" * 20000) < 1.0
    ratio, small, large = growth(pattern.search, "0b" + "1" * 2000, "0b" + "1" * 8000)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- a chain of '=' links (parser-safety-12)


def _ref_worked(text):
    """worked_equations before the gate: the earlier links searched again for every link."""
    out = []
    if "=" not in text and "≈" not in text:
        return out
    lines, pos = [], 0
    for raw in text.split("\n"):
        start, end = pos, pos + len(raw)
        pos = end + 1
        if lines and q._CONTINUATION_LINE_RE.match(raw):
            lines[-1] = (lines[-1][0], end)
        else:
            lines.append((start, end))
    for start, end in lines:
        line = text[start:end]
        if "=" not in line and "≈" not in line:
            continue
        cuts = [0] + [m.end() for m in q._WORKING_SEGMENT_RE.finditer(line)] + [len(line)]
        for a, b in zip(cuts, cuts[1:]):
            segment = " ".join(line[a:b].split())
            bounds = [-1] + [m.start() for m in re.finditer(r"[=≈]", segment)] + [len(segment)]
            links = [segment[x + 1: y] for x, y in zip(bounds, bounds[1:])]
            if len(links) < 2:
                continue
            for k in range(1, len(links)):
                if not (q._RESULT_START_RE.match(links[k]) and not q._OPERATOR_BETWEEN_RE.search(links[k])):
                    continue
                first = next((f for f in range(k) if q._OPERATOR_BETWEEN_RE.search(links[f])), None)
                if first is None:
                    continue
                lead = q._LINK_LEAD_END_RE.match(links[first])
                p_start = bounds[first] + 1 + (lead.end() if lead else 0)
                stop = q._RESULT_END_RE.search(links[k])
                p_end = bounds[k] + 1 + (stop.start() if stop else len(links[k]))
                out.append((start, end, segment, segment[p_start:p_end].strip().rstrip(" .,;:")))
                break
    return out


def test_worked_equations_read_a_chain_of_links_in_linear_time():
    # before the gate: 0.29 / 0.94 / 4.10 s at 1,000 / 2,000 / 4,000 links
    assert _timed(worked_equations, "= 1 " * 4000) < 1.0
    ratio, small, large = growth(worked_equations, "= 1 " * 1000, "= 1 " * 4000)
    assert ratio < LINEAR, (ratio, small, large)
    rng = random.Random(5)
    links = ["= 4", "= 2 + 2", "x", "= 3 × 5", "$6,000 ÷ $2.00", "= 3,000 loaves", ";", ". Then", "\n= 7", "≈ 8.1", "6 − 6t", "= (12 − 8) − 0"]
    for _ in range(3000):
        text = " ".join(rng.choice(links) for _ in range(rng.randint(1, 12)))
        assert [(w.start, w.end, w.statement, w.phrase) for w in worked_equations(text)] == _ref_worked(text), text


# --------------------------------------------------------------------------- the pair direction through written arithmetic (major)


def _checks(text: str):
    return [(c.kind, verify(c.problem).status.value, c.failure_severity) for c in extract_quant_checks(text, request_id="r", claim_id="c")]


def test_ec_e1_the_price_producers_keep_falls_to_the_arithmetics_stated_result():
    sentence = "Producers' share = $1.60 − $1.40 = $0.20 per litre (the price they keep falls from $1.60 to $2.00 − $0.60 = $1.40)."
    assert _checks(sentence) == [("pair_direction", "ENTAILED", "warning")]
    [check] = extract_quant_checks(sentence, request_id="r", claim_id="c")
    assert "'$2.00 − $0.60 = $1.40'" in check.basis


@pytest.mark.parametrize("sentence,expected", [
    ("The price producers keep falls from $1.60 to $1.40 ($2.00 − $0.60).", [("pair_direction", "ENTAILED", "error")]),  # control: a plain pair
    ("The price they keep falls from $1.60 to $2.00 - $0.60 = $1.40.", [("pair_direction", "ENTAILED", "warning")]),       # ASCII minus, spaced
    ("The price they keep falls from $1.60 to $2.00 − 0.60 = $1.40 per litre, a fall of 12.5 per cent.", [("percent_change", "ENTAILED", "warning")]),
    ("The price producers keep falls from $1.60 to $2.00 − $0.60 = $1.80.", [("pair_direction", "COUNTEREXAMPLE", "warning")]),  # named, a warning
    ("The price producers keep rises from $1.60 to $2.00 − $0.60 = $1.40.", [("pair_direction", "COUNTEREXAMPLE", "warning")]),
    ("The price consumers pay falls from $1.60 to $2.00, so the burden is shared.", [("pair_direction", "COUNTEREXAMPLE", "error")]),  # a plain pair
])
def test_a_pair_ends_at_its_figure_or_at_the_stated_result_of_its_arithmetic(sentence, expected):
    assert _checks(sentence) == expected


def test_arithmetic_that_states_no_result_leaves_the_pair_undecided_and_named():
    sentence = "The price producers keep falls from $1.60 to $2.00 − $0.60."
    assert _checks(sentence) == []
    [u] = undecided_quant_statements(sentence)
    assert u.reason == ARITH_ENDPOINT_REASON and u.phrase == "$2.00 − $0.60"


def _hub_codes(subject: str, agent: str, request: str, answer: str):
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, request)
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return [(f.code, f.severity) for f in rc.findings] + [(f.code, f.severity) for f in rc.structural_findings]


EC_REQUEST = "A tax of $0.60 per litre raises the price from $1.60 to $2.00. Calculate the producers' share of the tax."


def test_the_ec_e1_answer_crosses_the_economics_hub_with_no_error():
    answer = "Producers' share = $1.60 − $1.40 = $0.20 per litre (the price they keep falls from $1.60 to $2.00 − $0.60 = $1.40)."
    codes = _hub_codes("Economics", "economics-specialist", EC_REQUEST, answer)
    assert not [c for c in codes if c[1] == "error"], codes
    assert not [c for c in codes if c[0].startswith("INT-SUBJ")], codes
    fault = "The price producers keep falls from $1.60 to $2.00 − $0.60 = $1.80."
    assert ("INT-SUBJ-004", "warning") in _hub_codes("Economics", "economics-specialist", EC_REQUEST, fault)
    plain = "The price consumers pay falls from $1.60 to $2.00, so the burden is shared."
    assert ("INT-SUBJ-001", "error") in _hub_codes("Economics", "economics-specialist", EC_REQUEST, plain)


def test_the_end_to_end_ec_case_has_no_pair_direction_finding():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests import argdiag_cases as C, case_scoring as S
    run = S.run_case(C.load_cases(["e2e-B13-ec"])[0])
    flags = [f for m in run["modes"] for f in m["flags"]]
    assert not [f for f in flags if f["code"].startswith("INT-SUBJ") or "pair_direction" in f["message"]], flags
