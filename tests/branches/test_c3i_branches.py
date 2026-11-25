"""Follow-up 7 (c3i) of the branch packs: the push check of 84aff95c, Geography table readings only. The rule: a figure is checked
against the row its own clause names; a figure inside an insertion belongs to the noun the insertion attaches to; a noun inside a
nested comparison never names the row; a label before a colon names the row; the table's total row named by its own phrase (or by the
country the table belongs to) is the total row. Where the row is not determined that way, the figure gets no check: never ENTAILED and
never a charge on a correct figure.

1. A nested comparison inside a bracket, square bracket, dash pair or comma pair ('Coal (which, unlike natural gas, supplied about 9.3
   GJ per person in 2025) declined.') had read the figure against the compared row on 84aff95c: the gas figure ENTAILED for coal, the
   correct 11.8 GJ twin charged. The compared noun never names the row.
2. A figure inside an insertion after the total row's own phrase ('Energy supply per person, at about 11.8 GJ in 2025, was high.',
   'Energy supply, at about 38 GJ per person in 2025, rose.', 'Ostrel (about 38 GJ per person in 2025) imported more.') had lost its
   check on 84aff95c (no check for the wrong figure and for its correct 42 GJ twin). It is checked against the total row again.
3. A label before a colon ('Coal: about 42 GJ per person in 2025.') had been read against the total row (pre-existing): ENTAILED for
   the total's figure, the correct coal figure charged. The label names the row; a label that names no row gives no check.
4. c1/ge-t14: 'Site 2, which, unlike site 5, had a pedestrian count of 88, ...' had been ENTAILED against site 5 (pre-existing); site 2
   counted 186. The same rule for the sites and columns of the fieldwork table.

c2/ge-t15 (worked from the task's own table): 2025 total 1,050 PJ / 24.9 M = 42.2 GJ per person; coal 28% = 11.8, oil 27% = 11.4,
natural gas 22% = 9.3, nuclear 4% = 1.7, hydroelectric 6% = 2.5, wind and solar 13% = 5.5; imports 54% = 22.8; 2005 total 820 / 21.4 =
38.3. c1/ge-t14: site (pedestrian count, EQS) 1 (214, 24), 2 (186, 22), 3 (151, 23), 4 (97, 18), 5 (88, 15), 6 (61, 16), 7 (42, 12),
8 (45, 13), 9 (23, 9), 10 (19, 11). Every expected value is fixed here; each fault is pinned with its correct twin.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import geography
from epinoic_logic.branches.insertions import nested_parts

from . import d9d10_hub as H

_NEUTRAL = {"c2/ge-t15": "The answer uses the supplied table.", "c1/ge-t14": "The answer uses the supplied fieldwork data."}
_BASE: dict = {}
_CEX = (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])
_OK = (["ENTAILED"], [])
_NONE = ([], [])


def _one(record: str, sentence: str):
    """(statuses, codes) of ``sentence`` delivered alone as the recorded answer's agent; codes net of a neutral one-line answer's."""
    _a, question, subject, agent, task_type, docs = H.RECORDED[record]
    rc = H.through_hub(sentence, question, subject, agent, task_type, docs)
    if record not in _BASE:
        _BASE[record] = set(H.codes(H.through_hub(_NEUTRAL[record], question, subject, agent, task_type, docs)))
    return sorted({st for _c, st in H.checks(rc)}), sorted(set(H.codes(rc)) - _BASE[record])


# ------------------------------------------------------------------------------------------------- 1. nested comparisons (ge-t15)
_ROWS15 = [("Coal", "coal", "11.8"), ("Oil", "oil", "11.4"), ("Natural gas", "natural gas", "9.3"), ("Nuclear power", "nuclear power", "1.7"),
           ("Hydroelectric power", "hydroelectric power", "2.5"), ("Wind and solar power", "wind and solar power", "5.5")]
#: Each insertion form with the comparison before ('b') and after ('a') the figure: round and square brackets, an em-dash pair, a
#: spaced-hyphen pair, a comma pair, and a comparison with no commas of its own inside a comma pair.
_NEST15 = {
    "bracket, before": "{R} (which, {c} {o}, supplied about {v} GJ per person in 2025) declined.",
    "bracket, after": "{R} (which supplied about {v} GJ per person in 2025, {c} {o}) declined.",
    "bracket, opening": "{R} ({c} {o}, about {v} GJ per person in 2025) declined.",
    "square, before": "{R} [which, {c} {o}, supplied about {v} GJ per person in 2025] declined.",
    "square, after": "{R} [which supplied about {v} GJ per person in 2025, {c} {o}] declined.",
    "em dash, before": "{R} — which, {c} {o}, supplied about {v} GJ per person in 2025 — declined.",
    "em dash, after": "{R} — which supplied about {v} GJ per person in 2025, {c} {o} — declined.",
    "hyphen pair, before": "{R} - which, {c} {o}, supplied about {v} GJ per person in 2025 - declined.",
    "comma pair, before": "{R}, which, {c} {o}, supplied about {v} GJ per person in 2025, declined.",
    "comma pair, after": "{R}, which supplied about {v} GJ per person in 2025, {c} {o}, declined.",
    "comma pair, no commas": "{R}, which {c} {o} supplied about {v} GJ per person in 2025, declined.",
    "participle, before": "{R} (supplying, {c} {o}, about {v} GJ per person in 2025) declined.",
}
_CMP15 = ("unlike", "like", "compared with")
GRID_NEST15 = [(f.format(R=R, c=c, o=_ROWS15[(k + 2) % 6][1], v=v), right)
               for f in _NEST15.values() for k, (R, _r, own) in enumerate(_ROWS15) for c in _CMP15
               for v, right in ((_ROWS15[(k + 2) % 6][2], False), (own, True))]


def test_grid_nest15_size():
    assert len(GRID_NEST15) == 12 * 6 * 3 * 2 == len(set(GRID_NEST15))


@pytest.mark.parametrize("sentence,right", GRID_NEST15)
def test_nested_comparison_never_names_the_row(sentence, right):
    """Each cell exactly: the wrong figure (the compared row's) a COUNTEREXAMPLE with INT-SUBJ-004, the correct figure ENTAILED with no
    subject finding. (The codes are the subject-matter ones: '(compared with natural gas, ...)' opening a bracket also gets the
    request reader's INT-REQ-012, as on the head of the branch, which is not this reader's.)"""
    statuses, codes = _one("c2/ge-t15", sentence)
    assert (statuses, [c for c in codes if c.startswith("INT-SUBJ")]) == (_OK if right else _CEX)


@pytest.mark.parametrize("sentence,expected", [
    # the push check's lines (critical_open 1) and the challenger's fresh forms, each with its correct twin
    ("Coal (which, unlike natural gas, supplied about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, unlike natural gas, supplied about 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal — which, unlike natural gas, supplied about 9.3 GJ per person in 2025 — declined.", _CEX),
    ("Coal — which, unlike natural gas, supplied about 11.8 GJ per person in 2025 — declined.", _OK),
    ("Coal [which, unlike natural gas, supplied about 9.3 GJ per person in 2025] declined.", _CEX),
    ("Coal [which, unlike natural gas, supplied about 11.8 GJ per person in 2025] declined.", _OK),
    ("Coal (which, unlike imports, supplied about 22.8 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, unlike imports, supplied about 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal (supplying, as natural gas did, about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (supplying, as natural gas did, about 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal (unlike natural gas, about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (unlike natural gas, about 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal (in contrast to natural gas, about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (in contrast to natural gas, about 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal - which, unlike natural gas, supplied about 9.3 GJ per person in 2025 - declined.", _CEX),
    ("Coal - which, unlike natural gas, supplied about 11.8 GJ per person in 2025 - declined.", _OK),
    ("In 2025 coal (which, unlike natural gas, gave about 9.3 GJ per person) declined.", _CEX),
    ("In 2025 coal (which, unlike natural gas, gave about 11.8 GJ per person) declined.", _OK),
    ("Coal (which, unlike natural gas, gave each person about 9.3 GJ in 2025) declined.", _CEX),
    ("Coal (which, unlike natural gas, gave each person about 11.8 GJ in 2025) declined.", _OK),
    ("Coal (which, as natural gas did, supplied about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, as natural gas did, supplied about 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal (whereas natural gas grew, about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (whereas natural gas grew, about 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal, which unlike natural gas supplied about 9.3 GJ per person in 2025, declined.", _CEX),
    ("Coal, which unlike natural gas supplied about 11.8 GJ per person in 2025, declined.", _OK),
    # the challenger's over-block on 84aff95c: a correct figure after 'more than <row>' is no longer charged
    ("Oil (which, more than nuclear power, supplied about 11.4 GJ per person in 2025) changed least.", _OK),
    ("Oil (which, more than nuclear power, supplied about 1.7 GJ per person in 2025) changed least.", _CEX),
    # not determined: a joining phrase (the figure may be the items' together), a figure inside the comparison, a relative clause
    # after the compared noun: no check, never ENTAILED, never a charge
    ("Coal (which, alongside natural gas, supplied about 9.3 GJ per person in 2025) declined.", _NONE),
    ("Coal (which, alongside natural gas, supplied about 11.8 GJ per person in 2025) declined.", _NONE),
    ("Coal (which, together with oil, supplied about 23.2 GJ per person in 2025) declined.", _NONE),
    ("Coal (which, together with oil, supplied about 11.8 GJ per person in 2025) declined.", _NONE),
    ("Coal (which supplied more than natural gas at about 9.3 GJ per person in 2025) declined.", _NONE),
    ("Coal (which supplied more than natural gas at about 11.8 GJ per person in 2025) declined.", _NONE),
    ("Coal (unlike natural gas, which supplied about 9.3 GJ per person in 2025) declined.", _NONE),
    ("Coal (unlike natural gas, which supplied about 11.8 GJ per person in 2025) declined.", _NONE),
    # unchanged: the comma forms 08c4a36b read right, a listed pair, a joining phrase that opens the modifier and holds the figure
    ("Coal, which, unlike natural gas, supplied about 9.3 GJ per person in 2025, declined.", _CEX),
    ("Coal, which, unlike natural gas, supplied about 11.8 GJ per person in 2025, declined.", _OK),
    ("Coal, unlike natural gas, supplied about 9.3 GJ per person in 2025.", _CEX),
    ("Coal supplied about 9.3 GJ per person in 2025, unlike natural gas.", _CEX),
    ("Coal and oil (which together supplied about 23.2 GJ per person in 2025) declined.", _OK),
    ("Natural gas, with coal at about 11.8 GJ per person in 2025, grew.", _OK),
])
def test_nested_comparison_lines(sentence, expected):
    assert _one("c2/ge-t15", sentence) == expected


# ------------------------------------------------------------------------------------------------- 2. the total row's own phrase
_HEADS = ["Energy supply per person", "Energy supply", "Total energy supply per head", "Average energy supply per person",
          "Primary energy supply per person", "Ostrel", "Ostrel's energy supply"]
_TOTAL_FORMS = {
    "at phrase": "{h}, at about {v} GJ{pp} in 2025, rose.",
    "bracket": "{h} (about {v} GJ{pp} in 2025) rose.",
    "square bracket": "{h} [about {v} GJ{pp} in 2025] rose.",
    "dash pair": "{h} — about {v} GJ{pp} in 2025 — rose.",
    "relative clause": "{h}, which reached about {v} GJ{pp} in 2025, rose.",
    "participle": "{h}, reaching about {v} GJ{pp} in 2025, rose.",
    "bare comma pair": "{h}, about {v} GJ{pp} in 2025, rose.",
}
GRID_TOTAL = [(f.format(h=h, v=v, pp="" if ("per person" in h or "per head" in h) else " per person"), right)
              for f in _TOTAL_FORMS.values() for h in _HEADS for v, right in (("38", False), ("11.8", False), ("42", True))]


def test_grid_total_size():
    assert len(GRID_TOTAL) == 7 * 7 * 3 == len(set(GRID_TOTAL))


@pytest.mark.parametrize("sentence,right", GRID_TOTAL)
def test_total_row_phrase_is_the_total(sentence, right):
    """The total's own phrase (and the country's name: the table is Ostrel's) names the total row: 42 GJ ENTAILED, the 2005 figure
    (38) and coal's figure (11.8) each a COUNTEREXAMPLE."""
    assert _one("c2/ge-t15", sentence) == (_OK if right else _CEX)


@pytest.mark.parametrize("sentence,expected", [
    # the push check's lines (critical_open 2), each with its correct twin
    ("Energy supply per person, at about 11.8 GJ in 2025, was high.", _CEX),
    ("Energy supply per person, at about 42 GJ in 2025, was high.", _OK),
    ("Energy supply, at about 38 GJ per person in 2025, rose.", _CEX),
    ("Energy supply, at about 42 GJ per person in 2025, rose.", _OK),
    ("Ostrel (about 38 GJ per person in 2025) imported more.", _CEX),
    ("Ostrel (about 42 GJ per person in 2025) imported more.", _OK),
    ("Energy supply per person (11.8 GJ in 2025) was higher than in 2005.", _CEX),
    ("Energy supply per person (42 GJ in 2025) was higher than in 2005.", _OK),
    # a noun that is neither a row nor the total's own phrase: no check
    ("Petroleum, at about 42 GJ per person in 2025, mattered.", _NONE),
    ("Energy demand growth, at about 42 GJ per person in 2025, mattered.", _NONE),
    # the fixes of 08c4a36b and 67bc64ec stay fixed
    ("Energy supply per person, while coal declined, was about 11.8 GJ in 2025.", _CEX),
    ("Energy supply per person, while coal declined, was about 42 GJ in 2025.", _OK),
    ("One source, natural gas, supplied about 9.3 GJ per person in 2025.", _OK),
    ("One source, natural gas, supplied about 42 GJ per person in 2025.", _CEX),
    ("Coal, which supplied about 42 GJ per person in 2025, declined.", _CEX),
    ("Coal, which supplied about 11.8 GJ per person in 2025, declined.", _OK),
    ("Oil (about 42 GJ per person in 2025) changed least.", _CEX),
    ("Oil (about 11.4 GJ per person in 2025) changed least.", _OK),
])
def test_total_row_lines(sentence, expected):
    assert _one("c2/ge-t15", sentence) == expected


# ------------------------------------------------------------------------------------------------- 3. a label before a colon
_LABEL_FORMS = ["{L}: about {v} GJ per person in 2025.", "{L}: roughly {v} GJ per head in 2025.", "{L}: {v} GJ per person in 2025, up from 2005.",
                "{L}: it supplied about {v} GJ per person in 2025."]
GRID_LABEL = [(f.format(L=R, v=v), right) for f in _LABEL_FORMS for R, _r, own in _ROWS15 for v, right in (("42", False), (own, True))] + \
             [(f.format(L=L, v=v), right) for f in _LABEL_FORMS for L in ("Energy supply per person", "Ostrel") for v, right in (("11.8", False), ("42", True))]


def test_grid_label_size():
    assert len(GRID_LABEL) == 4 * 6 * 2 + 4 * 2 * 2 == len(set(GRID_LABEL))


@pytest.mark.parametrize("sentence,right", GRID_LABEL)
def test_label_names_the_row(sentence, right):
    assert _one("c2/ge-t15", sentence) == (_OK if right else _CEX)


@pytest.mark.parametrize("sentence,expected", [
    # the push check's lines (critical_open 5), each with its correct twin
    ("Coal: about 42 GJ per person in 2025.", _CEX),
    ("Coal: about 11.8 GJ per person in 2025.", _OK),
    ("Oil: roughly 42 GJ per head in 2025.", _CEX),
    ("Oil: roughly 11.4 GJ per head in 2025.", _OK),
    ("Natural gas: 42 GJ per person in 2025, up from 2005.", _CEX),
    ("Natural gas: 9.3 GJ per person in 2025, up from 2005.", _OK),
    ("Coal and oil: about 23.2 GJ per person in 2025.", _OK),
    ("Coal and oil: about 42 GJ per person in 2025.", _CEX),
    # a label that names no row: no check (never ENTAILED, never a charge)
    ("Answer: about 42 GJ per person in 2025.", _NONE),
    ("Answer: about 11.8 GJ per person in 2025.", _NONE),
    # the words after the colon a clause with its own subject: its own reading, unchanged
    ("Result: energy supply per person rose from about 38 GJ in 2005 to about 42 GJ in 2025.", _OK),
    ("Result: coal supplied about 11.8 GJ per person in 2025.", _OK),
    ("Result: coal supplied about 42 GJ per person in 2025.", _CEX),
])
def test_label_lines(sentence, expected):
    assert _one("c2/ge-t15", sentence) == expected


# ------------------------------------------------------------------------------------------------- 4. c1/ge-t14: sites and columns
_SITES = {1: (214, 24), 2: (186, 22), 3: (151, 23), 4: (97, 18), 5: (88, 15), 6: (61, 16), 7: (42, 12), 8: (45, 13), 9: (23, 9), 10: (19, 11)}
_COLS14 = (("pedestrian count", 0), ("EQS", 1))
_NEST14 = {
    "comma pair, before": "Site {s}, which, {c} site {o}, had a {col} of {v}, stood out.",
    "comma pair, no commas": "Site {s}, which {c} site {o} had a {col} of {v}, stood out.",
    "bracket, before": "Site {s} (which, {c} site {o}, had a {col} of {v}) stood out.",
    "bracket, after": "Site {s} (which had a {col} of {v}, {c} site {o}) stood out.",
    "square, before": "Site {s} [which, {c} site {o}, had a {col} of {v}] stood out.",
    "dash pair, before": "Site {s} — which, {c} site {o}, had a {col} of {v} — stood out.",
}
GRID_NEST14 = [(f.format(s=s, c=c, o=(s + 3) % 10 + 1, col=col, v=v), right)
               for f in _NEST14.values() for s in _SITES for col, k in _COLS14 for c in ("unlike",)
               for v, right in ((_SITES[(s + 3) % 10 + 1][k], False), (_SITES[s][k], True))]


def test_grid_nest14_size():
    assert len(GRID_NEST14) == 6 * 10 * 2 * 2 == len(set(GRID_NEST14))


@pytest.mark.parametrize("sentence,right", GRID_NEST14)
def test_site_nested_comparison_never_names_the_row(sentence, right):
    assert _one("c1/ge-t14", sentence) == (_OK if right else _CEX)


@pytest.mark.parametrize("sentence,expected", [
    # the push check's line (reason 5) and its bracket form, each with its correct twin (site 2 counted 186, site 5 88)
    ("Site 2, which, unlike site 5, had a pedestrian count of 88, was busy.", _CEX),
    ("Site 2, which, unlike site 5, had a pedestrian count of 186, was busy.", _OK),
    ("Site 2 (which, unlike site 5, had a pedestrian count of 88) was busy.", _CEX),
    ("Site 2 (which, unlike site 5, had a pedestrian count of 186) was busy.", _OK),
    ("Site 2 (unlike site 5, a pedestrian count of 88) was busy.", _CEX),
    ("Site 2 (unlike site 5, a pedestrian count of 186) was busy.", _OK),
    # not determined: a relative clause after the compared site; a figure its own words place at another site (67bc64ec's fix)
    ("Site 2 (unlike site 5, which had a pedestrian count of 88) was busy.", _NONE),
    ("Site 2, which had more pedestrians than the 97 counted at site 4, was busy.", _NONE),
    # unchanged
    ("Site 2, which had a pedestrian count of 186, was busy.", _OK),
    ("Site 4 (EQS 24) stood out.", _CEX),
    ("Site 4 (EQS 18) stood out.", _OK),
])
def test_site_lines(sentence, expected):
    assert _one("c1/ge-t14", sentence) == expected


# ------------------------------------------------------------------------------------------------- the helpers
def test_nested_parts():
    text = "Coal (which, unlike natural gas, supplied about 9.3 GJ, together with oil [a fuel] in 2025) declined."
    lo, hi = text.index("which"), text.index(") declined")
    parts = nested_parts(text, lo, hi)
    assert [(text[a:b], k) for a, b, k in parts] == [("unlike natural gas", "c"), ("together with oil ", "j"), ("[a fuel]", "b")]
    assert nested_parts(text, 5, 5) == ()
    text = "Coal, which unlike natural gas supplied 9.3 GJ, fell."
    assert [(text[a:b], k) for a, b, k in nested_parts(text, text.index("which"), text.index(", fell"))] == [("unlike natural gas ", "c")]


def test_total_and_owner():
    from epinoic_logic.branches.grounded_figures import supplied_tables
    _a, _q, _s, _g, _t, docs = H.RECORDED["c2/ge-t15"]
    table = geography._yt_documents(supplied_tables(H.supplied(docs)))[0]
    entity, label, head = geography._yt_total_of(table)
    assert (entity, label, head) == ("Total primary energy supply (petajoules, PJ)", frozenset({"energy", "supply"}), "supply")
    assert geography._yt_owner(docs[0][3]) == frozenset({"ostrel"})
    total = (entity, label, head, frozenset({"ostrel"}))
    for phrase, named in [("Energy supply per person", True), ("Ostrel", True), ("Ostrel's energy supply", True), ("Energy", False),
                          ("Energy demand", False), ("Coal", False), ("The supply of coal", False)]:
        assert geography._yt_total_named(phrase, 0, len(phrase), total) is named, phrase


# ------------------------------------------------------------------------------------------------- linear time
@pytest.mark.parametrize("unit", [
    "Coal (which, unlike natural gas, supplied about 11.8 GJ per person in 2025, unlike oil, alongside coal, ",
    "Coal [unlike natural gas, about 11.8 GJ per person in 2025 — unlike oil — (like coal) ",
    "Coal — which, unlike natural gas, supplied about 11.8 GJ, ",
    "Coal: about 11.8 GJ per person in 2025; ",
    "Energy supply per person, at about 42 GJ in 2025, ",
])
def test_nested_reading_is_linear(unit):
    """Hostile input: the nested parts of an insertion are read once per insertion, each figure's reading a few bisections."""
    from epinoic_logic.branches.grounded_figures import supplied_tables
    _a, _q, _s, _g, _t, docs = H.RECORDED["c2/ge-t15"]
    table = geography._yt_documents(supplied_tables(H.supplied(docs)))[0]
    total = geography._yt_total_of(table) + (frozenset({"ostrel"}),)

    def run(k: int) -> float:
        text = unit * k + ") declined in 2025."
        t0 = time.perf_counter()
        idx = geography._YtIndex(text)
        for m in geography._YT_NUMBER_RE.finditer(text):
            idx.attached(table, m.start(), total)
            idx.row(table, m.start(), total)
        return time.perf_counter() - t0
    run(50)
    small, large = min(run(250) for _ in range(3)), min(run(2000) for _ in range(3))
    assert large < small * 8 * 3 + 0.05  # 8 times the input: well under quadratic growth


@pytest.mark.parametrize("unit,record", [
    ("Coal (which, unlike natural gas, supplied about 11.8 GJ per person in 2025) declined, ", "c2/ge-t15"),
    ("Coal: about 11.8 GJ per person in 2025; ", "c2/ge-t15"),
    ("Site 2 (which, unlike site 5, had a pedestrian count of 186) was busy, ", "c1/ge-t14"),
])
def test_nested_reading_through_the_reader_is_linear(unit, record):
    """Hostile input through the readers themselves (a sentence of 200 kB never stalls)."""
    text = unit * (200_000 // len(unit) + 1) + "and so on."
    assert len(text) > 200_000
    t0 = time.perf_counter()
    _one(record, text)
    assert time.perf_counter() - t0 < 60
