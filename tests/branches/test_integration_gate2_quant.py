"""Integration gate 2 (before arena round 8): the prose arithmetic reader (``branches/quant.py``) and the generic parser on hostile input.

Critical finding fixed at its cause: the next item of a list after a pair (``quant._LIST_ITEM_RE``) opened with ``\\s*`` before the
``\\s+`` of ' and ', so a long run of blanks after a dated pair ('... to 4.5 million in 1931' + blanks + 'xx') was split in every way
before failing, n² steps (19.7 s per History receive at 40,000 characters). The run is one possessive run; the items are the same.

Found by the sweep of the same class in these modules, each fixed the same way with its old reading kept here as the specification:

* the join of two dated figures (``_AND_DATED_RE``), the share of a total and its part (``_SHARE_RE``), the share of a stated total
  (``_SHARE_OF_TOTAL_RE``: 72 s for a clause of 16,000 blanks), the separator between two pairs (``_SEG_SEP_RE``), the name of a party
  ('Kenya alone received', ``_ALONE_RE`` and ``_SHARE_PARTY_RE``: an unbounded name was read again from each of its words, 4 s at 24,000
  characters; a name is read up to twelve words);
* the parts of a clause ('of which', '<party> alone', ...) each read the clause before them again: a clause of more than
  ``_MAX_CLAUSE_PART_MARKERS`` of them is reported undecided (CORE-QNT-001), never read in part (256 s for a clause of 'of which' at
  32,000 characters); a clause of more than ``_MAX_CLAUSE_FIGURES`` derived figures or pairs likewise;
* each rate or absolute change was tested against every phrase read before it (the phrases are marked once), the rest of the text
  was copied for every figure, and the years a 'that year' anaphor may refer to were looked up again for each;
* an average rate stated 'annually' crashed the reader (its tail was an ungrouped alternation: ``CORE-INTERNAL-001``);
* the generic parser's accuracy mark at the end of a line and its consequence lead read a run again from each of its characters, and
  a line of marks followed by text was matched whole with two adjacent blank runs.

The sweep tests feed every public entry point of the modules the standard hostile inputs, and the quantitative reader the same runs after
the words that bring it into each reading, and assert a time bound with a wide margin."""
from __future__ import annotations

import random
import re
import time

import pytest

from epinoic_logic.adapters.base import AdapterError
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches import generic_parser as g
from epinoic_logic.branches import packs
from epinoic_logic.branches import quant as q
from epinoic_logic.branches import worked as w
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.branches.quant import extract_quant_checks, undecided_quant_statements, worked_equations
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

from ..adapters.hostile_inputs import PREFIXED_RUNS, HOSTILE, all_inputs, bounded
from ..growth import growth
from ..timing import empty_caches

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
KEY = b"integration-gate-2-quant-key-0123456789ab"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
CALL_BOUND = 3.0
PARSE_BOUND = 10.0

# --------------------------------------------------------------------------- the replaced readings (the specification)

OLD_AND_DATED_RE = re.compile(rf"(?<![\w.,]){q._fig(1, dated=True)}\s*,?\s+and\s+(?:(?:had\s+|then\s+)?{q._TO_VERB}\s+)?{q._fig(2, dated=True)}", re.IGNORECASE)
OLD_LIST_ITEM_RE = re.compile(rf"\s*(?:,\s*(?:and\s+)?|\s+and\s+)(?:then\s+)?(?:to\s+)?{q._fig(3, dated=True)}", re.IGNORECASE)
OLD_SHARE_RE = re.compile(
    rf"\b{q._NUM}\s*{q._PCT_UNIT}\s+of\s+(?:the\s+)?(?:about|around|roughly)?\s*{q._NUM}{q._UNIT}(?:\s+[a-z]+){{0,2}}?(?:\s*,\s*(?:or|i\.e\.|that is)?|"
    rf"\s+(?:or|was|is|=|that is|i\.e\.)|\s*\()\s*(?:about|around|roughly|some)?\s*{q._NUM}{q._UNIT}", re.IGNORECASE)
OLD_SHARE_OF_TOTAL_RE = re.compile(
    rf"(?:,\s*|\s+)(?:(?P<q>{q._QUAL})\s+)?(?:(?P<frac>{q._FRAC})|(?P<pn>\d+(?:\.\d+)?)\s*{q._PCT_UNIT})\s+of\s+(?:the|this|that|its|their)\s+"
    r"(?:(?P<period>decade|year|period|programme|plan|war|era|century|month)(?:'s|’s)\s+)?(?P<noun>total|sum|whole|aggregate|arrivals|figure|amount|number)\b",
    re.IGNORECASE)
OLD_SEG_SEP_RE = re.compile(r",\s*(?:and|while|whereas|but|yet)\b|;|\s+and\s+", re.IGNORECASE)
OLD_ALONE_RE = re.compile(q._ALONE_RE.pattern.replace("){0,11})\\s+alone", ")*)\\s+alone"), q._ALONE_RE.flags)
OLD_SHARE_PARTY_RE = re.compile(q._SHARE_PARTY_RE.pattern.replace("){0,11})\\s+(?:alone", ")*)\\s+(?:alone"), q._SHARE_PARTY_RE.flags)
OLD_ANNOTATION_ONLY_RE = re.compile(rf"\s*(?:(?:{g._MARK_ALLOC}|\(?{g._MARK_CODE}\)?)\s*)+[.;,]?\s*")

QUANT_ALPHABET = [" ", "  ", "\t", "\n", ",", ", ", ";", ".", "(", ")", "=", "%", "per cent", "of", "the", "about", "around", "some", "or", "is", "was",
                  "i.e.", "that is", "and", "then", "to", "rose to", "had", "from", "in", "1930", "1931", "3", "4.5", "20", "1,200", "million", "seats",
                  "votes", "x", "a quarter", "half", "of the total", "of its total", "decade's", "about a quarter", "60", "while", "but", "Kenya",
                  "Uganda", "of", "alone", "received", "got", "brought", "itself", "The", "United", "Kingdom"]


def _random_texts(alphabet, seed: int, n: int, longest: int = 14):
    rng = random.Random(seed)
    for _ in range(n):
        yield "".join(rng.choice(alphabet) for _ in range(rng.randint(0, longest)))


def _matches(m):
    return m and (m.span(), tuple(m.span(i) for i in range(1, (m.re.groups or 0) + 1)))


def _all(pattern, text):
    return [_matches(m) for m in pattern.finditer(text)]


def _read(text: str) -> None:
    """Every reading of the quantitative reader: the general and the SI reading, the checks, the undecided statements and the worked
    equations."""
    for reading in (q.GENERAL, q.SI_READING):
        extract_quant_checks(text, request_id="r", claim_id="c", reading=reading)
        undecided_quant_statements(text, reading=reading)
    worked_equations(text)


def _receive(answer: str, subject: str = "History", agent: str = "history-specialist", request: str = "Describe the change."):
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, request)
    t = time.perf_counter()
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return time.perf_counter() - t, rc


# --------------------------------------------------------------------------- the list item after a pair (critical) and the joins

def test_the_joins_and_the_shares_are_those_of_the_old_patterns():
    for text in _random_texts(QUANT_ALPHABET, 41, 40000):
        assert _all(q._AND_DATED_RE, text) == _all(OLD_AND_DATED_RE, text), repr(text)
        assert _all(q._SHARE_RE, text) == _all(OLD_SHARE_RE, text), repr(text)
        assert _all(q._SHARE_OF_TOTAL_RE, text) == _all(OLD_SHARE_OF_TOTAL_RE, text), repr(text)
        assert _matches(q._SHARE_OF_TOTAL_RE.search(text)) == _matches(OLD_SHARE_OF_TOTAL_RE.search(text)), repr(text)
        assert _all(q._SEG_SEP_RE, text) == _all(OLD_SEG_SEP_RE, text), repr(text)
        # names of at most twelve words, as every random text here
        assert _all(q._ALONE_RE, text) == _all(OLD_ALONE_RE, text), repr(text)
        assert _matches(q._SHARE_PARTY_RE.search(text)) == _matches(OLD_SHARE_PARTY_RE.search(text)), repr(text)
        for pos in range(len(text) + 1):  # the list item is read at the end of a pair
            assert _matches(q._LIST_ITEM_RE.match(text, pos)) == _matches(OLD_LIST_ITEM_RE.match(text, pos)), (pos, repr(text))


@pytest.mark.parametrize("make", [
    lambda n: "Unemployment rose from 3 million in 1930 to 4.5 million in 1931" + " " * n + "xx.",   # the finding's input
    lambda n: "Unemployment rose from 3 million in 1930 to 4.5 million in 1931" + "\t" * n + "x.",
    lambda n: "It was 3 million in 1930" + " " * n + ", x.",                                         # the dated join
    lambda n: "About 20 per cent of" + " " * n + "x.",                                               # the share
    lambda n: "The total was 5" + " " * n + "x total.",                                              # the share of a total
    lambda n: "Of the 100 seats, Kenya" + " " * n + "x total.",
    lambda n: "Kenya alone received 5" + " " * n + "x of the total.",
    lambda n: "It rose from 3 million in 1930 to 4 million in 1931" + " " * n + "x and 5 million in 1932 to 6 million in 1933.",  # between pairs
])
def test_a_long_run_in_a_quantitative_clause_is_read_in_linear_time(make):
    t = time.perf_counter()
    _read(make(100_000))  # both readings: about 2 s
    assert time.perf_counter() - t < 15.0  # before the gate: 19.7 s per receive at 40,000; 72 s for the share of a total at 16,000 blanks
    ratio, small, large = growth(_read, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


def test_a_history_answer_with_a_long_run_after_a_pair_crosses_the_hub_in_seconds():
    elapsed, rc = _receive("Unemployment rose from 3 million in 1930 to 4.5 million in 1931" + " " * 40_000 + "xx.")
    assert elapsed < 20.0  # before the gate: 19.7 s
    assert "CORE-INTERNAL-001" not in {f.code for f in [*rc.findings, *rc.structural_findings]}


# --------------------------------------------------------------------------- markers repeated in one clause (the sweep)

MARKERS = {
    "of which": "100 voters, of which 5 and ",                    # 256 s at 32,000 characters before the gate
    "alone": "Kenya alone received 5 and ",                       # 50 s
    "an average rate": "an average of 5 per year and ",
    "averaging": "averaging 5 a year, ",                          # n² overlap test of the rates
    "a total": "a total of 5 seats and ",
    "that year": "in that year 5 rose and ",
    "a share": "20 per cent of 100 voters and ",
    "a change": "rose by 5 per cent in 1930 and ",
    "a pair": "from 3 million in 1930 to 4 million in 1931 and ",
    "a lone figure": "5 x ",
    "a worked step": "5 + 5 = 10 and ",
    "a name": "Kenya ",                                            # the party's name read again from each of its words
}


@pytest.mark.parametrize("unit", list(MARKERS.values()), ids=list(MARKERS))
def test_a_clause_repeating_a_marker_is_read_in_linear_time(unit):
    make = lambda n: "The figure was 3 in 1929 and " + unit * (n // len(unit)) + "x total."  # noqa: E731
    t = time.perf_counter()
    _read(make(200_000))
    assert time.perf_counter() - t < 20.0
    ratio, small, large = growth(_read, make(16_000), make(64_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


def test_a_clause_over_the_part_marker_bound_is_undecided_and_says_why():
    over = "The figure was 1,000 seats" + ", of which Kenya got 5" * (q._MAX_CLAUSE_PART_MARKERS + 1) + "."
    reasons = [u.reason for u in undecided_quant_statements(over)]
    assert q._TOO_MANY_PARTS_REASON in reasons
    assert f"more than {q._MAX_CLAUSE_PART_MARKERS} parts" in q._TOO_MANY_PARTS_REASON
    within = "The figure was 1,000 seats, of which Kenya got 500 and Uganda got 600."
    assert q._TOO_MANY_PARTS_REASON not in [u.reason for u in undecided_quant_statements(within)]
    assert extract_quant_checks(within, request_id="r", claim_id="c")  # the parts are read and checked as before


def test_a_clause_over_the_figure_bound_is_undecided_and_says_why():
    over = "Output " + ", ".join(f"rose by {i + 1} per cent" for i in range(q._MAX_CLAUSE_FIGURES + 1)) + "."
    assert q._TOO_MANY_REASON in [u.reason for u in undecided_quant_statements(over)]
    within = "Output rose by 5 per cent, from 100 in 1930 to 105 in 1931."
    assert q._TOO_MANY_REASON not in [u.reason for u in undecided_quant_statements(within)]


def test_a_party_name_is_read_up_to_twelve_words():
    for n in (1, 5, 12):
        name = " ".join(["Kenya"] * n)
        m = q._ALONE_RE.search(f"The total was 100 seats. {name} alone received 5 seats.")
        assert m is not None and m.group("who") == name
    m = q._ALONE_RE.search("The total was 100 seats. " + "Kenya " * 20 + "alone received 5 seats.")
    assert m is not None and m.group("who") == " ".join(["Kenya"] * 12)


def test_an_average_stated_annually_no_longer_crashes_the_reader():
    for text in ("The average rainfall rose annually.", "Output grew by an average of 5 per cent annually.", "Prices averaged 3 per cent yearly."):
        _read(text)  # before the gate: a TypeError, reported as CORE-INTERNAL-001 on every branch
    _elapsed, rc = _receive("The average rainfall rose annually, and output grew by an average of 5 tonnes annually from 1930 to 1935.",
                            subject="Economics", agent="economics-specialist")
    assert "CORE-INTERNAL-001" not in {f.code for f in [*rc.findings, *rc.structural_findings]}
    # an average rate with a stated period reads as before
    assert extract_quant_checks("Output rose from 100 tonnes in 1930 to 150 tonnes in 1935, an average of 10 tonnes a year.", request_id="r", claim_id="c")


# --------------------------------------------------------------------------- the packs' worked divisions (the sweep)

OLD_DIVISION_LINK_RE = re.compile(rf"^\s*\(?\s*(?P<a>{packs._WORKED_NUM})\s*%?\s*\)?\s*[÷/]\s*\(?\s*(?P<b>{packs._WORKED_NUM})\s*%?\s*\)?\s*$")
OLD_MARGIN_LINK_RE = re.compile(rf"^\s*\(?\s*(?P<a>{packs._WORKED_NUM})\s*[÷/]\s*(?P<b>{packs._WORKED_NUM})\s*\)?\s*[×x*]\s*100\s*$")


def test_the_links_of_a_worked_division_are_those_of_the_old_patterns():
    alphabet = [" ", "  ", "\t", "\n", "(", ")", "%", "÷", "/", "×", "x", "*", "100", "5", "12.50", "-", "−", "+", "$", "£", "US", "1,000", "0.5", "a"]
    for text in _random_texts(alphabet, 44, 60000, longest=11):
        assert _matches(packs._DIVISION_LINK_RE.match(text)) == _matches(OLD_DIVISION_LINK_RE.match(text)), repr(text)
        assert _matches(packs._MARGIN_LINK_RE.match(text)) == _matches(OLD_MARGIN_LINK_RE.match(text)), repr(text)


@pytest.mark.parametrize("make", [
    lambda n: "PED = " + " " * n + "x ÷ 2 = 5.",              # a link of blanks: 3.7 s at 4,000 blanks before the gate
    lambda n: "PED = (" + " " * n + "x) ÷ 2 = 5.",
    lambda n: "Gross profit margin = (" + "\t" * n + "x ÷ 2) × 100 = 50%.",
])
def test_a_worked_division_with_a_long_link_is_read_in_linear_time(make):
    def read(text):
        packs.elasticity_equations(text)
        packs.margin_equations(text)
    for link in (" " * 20_000 + "x", "(" + " " * 20_000 + "x", "5" + " " * 20_000 + "x"):
        t = time.perf_counter()
        packs._DIVISION_LINK_RE.match(link)
        packs._MARGIN_LINK_RE.match(link)
        assert time.perf_counter() - t < 0.5
    t = time.perf_counter()
    read(make(100_000))
    assert time.perf_counter() - t < 10.0
    ratio, small, large = growth(read, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- the generic parser's marks and leads

def test_the_accuracy_mark_the_consequence_lead_and_the_annotation_line_are_those_of_the_old_readings():
    alphabet = [" ", "  ", "\t", "(A1)", "A1", "(M1)", "M2", "AG", "(", ")", ".", ";", ",", "x", "A", "1", "therefore", "Thus", "so", "hence",
                "far", "'", "’", "-", "it", "follows", "as a result", "[2]", "(2 marks)"]
    for text in _random_texts(alphabet, 43, 60000, longest=10):
        assert g._accuracy_marked(text) == bool(g._ACCURACY_MARK_RE.search(text)), repr(text)
        assert g._is_consequence(text) == bool(g._CONSEQUENCE_RE.match(text)), repr(text)
        assert bool(g._ANNOTATION_ONLY_LINEAR_RE.fullmatch(text)) == bool(OLD_ANNOTATION_ONLY_RE.fullmatch(text)), repr(text)
    # the shared pattern itself (the STEM layout's) is unchanged
    assert g._ANNOTATION_ONLY_RE.pattern == OLD_ANNOTATION_ONLY_RE.pattern


@pytest.mark.parametrize("make", [
    lambda n: "The price rose" + " (A1)" * (n // 5) + " x",        # a run of marks that text follows
    lambda n: "(A1)" + " " * n + "x",                               # a line of marks, then blanks and text
    lambda n: "’ " * (n // 2) + "x therefore y.",                  # a run before a consequence lead
])
def test_the_generic_parser_reads_a_long_line_of_marks_in_linear_time(make):
    def parse(text):
        GenericTextParser("economics-specialist").parse_response(text, request_id="q", task_id="t", report_id="r", subject="Economics", task_type="essay")
    t = time.perf_counter()
    parse(make(200_000))
    assert time.perf_counter() - t < 10.0
    ratio, small, large = growth(parse, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- the sweep: every public entry point of each module

#: Words that bring the quantitative reader into each of its readings, before each standard run.
QUANT_PREFIXES = {
    "after a pair": "Unemployment rose from 3 million in 1930 to 4.5 million in 1931",
    "after a total": "The total was 5",
    "after a lead total": "Of the 100 seats, Kenya",
    "after a part": "Kenya alone received 5",
    "after 'of which'": "100 voters, of which",
    "after a difference": "about 5 more than France",
    "after a rate": "an average of 5 per year",
    "after a worked step": "5 + 5 =",
    "after a worked elasticity": "PED =",
    "after a worked margin": "Gross profit margin = (",
}


def _quant_inputs() -> dict[str, str]:
    out = dict(all_inputs())
    out.update({f"{run} {where}": words + HOSTILE[run] for where, words in QUANT_PREFIXES.items() for run in PREFIXED_RUNS})
    return out


def _sweep(entry_points: dict, inputs: dict, bound: float = CALL_BOUND, allowed: tuple = ()):
    slow, crashed = [], []
    for name, fn in entry_points.items():
        for label, text in inputs.items():
            empty_caches()
            elapsed, error = bounded(fn, text)
            if elapsed >= bound:
                slow.append((name, label, round(elapsed, 2)))
            if error is not None and not isinstance(error, allowed):
                crashed.append((name, label, type(error).__name__, str(error)[:120]))
    assert not slow, slow
    assert not crashed, crashed


def test_the_quantitative_reader_reads_every_hostile_input_in_linear_time():
    _sweep({
        "extract_quant_checks": lambda t: extract_quant_checks(t, request_id="r", claim_id="c"),
        "extract_quant_checks, SI reading": lambda t: extract_quant_checks(t, request_id="r", claim_id="c", reading=q.SI_READING),
        "undecided_quant_statements": undecided_quant_statements,
        "undecided_quant_statements, SI reading": lambda t: undecided_quant_statements(t, reading=q.SI_READING),
        "worked_equations": worked_equations,
        "worked_problems": lambda t: w.worked_problems(t, report_id="r", request_id="q", prefix="c"),
        "decided_worked_chains": w.decided_worked_chains,
    }, _quant_inputs())


def test_the_generic_parser_and_the_packs_read_every_hostile_input_in_linear_time():
    from epinoic_logic.branches.packs import BusinessPack, CorePack, EconomicsPack, GenericPack, PsychologyPack

    def parse_and_check(text):
        report = GenericTextParser("economics-specialist").parse_response(text, request_id="q", task_id="t", report_id="r", subject="Economics", task_type="essay")
        for pack in (CorePack(), EconomicsPack(), BusinessPack(), PsychologyPack(), GenericPack()):
            pack.checks(report, request_text=text[:2000])
            pack.formal_checks(report)
    _sweep({"parse and pack checks": parse_and_check}, _quant_inputs(), bound=PARSE_BOUND, allowed=(AdapterError,))


def test_the_hostile_inputs_include_the_quantitative_prefixes():
    inputs = _quant_inputs()
    assert all(f"blanks {where}" in inputs for where in QUANT_PREFIXES)
    assert all(19_000 <= len(text) <= 21_200 for label, text in inputs.items() if label.startswith(("blanks ", "tabs ")))
