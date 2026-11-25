"""Follow-up 7 (c3i), its check round: Geography table readings that the check lenses found on the working tree of follow-up 7. The rule
is the same as in tests/branches/test_c3i_branches.py: a figure is checked against the row its own clause names; a figure inside an
insertion belongs to the noun the insertion attaches to; a noun inside a nested comparison never names the row; a label before a colon
names the row; the total row named by its own phrase is the total row; where the row is not determined, no check.

1. A comparison opened by a comparative with 'than' ('more than', 'bigger than', 'less than'), by Spanish 'en comparación con', 'más
   que' or 'mayor que', or by a substitution or ranking ('instead of', 'in place of', 'beside', 'against', 'behind', 'exceeding',
   'outweighing', 'differently from') had not been read as an insertion of its own: the compared row's figure was ENTAILED and the
   correct twin charged, in a comma pair, after a participle ('Oil, providing, more than hydroelectric power, roughly 2.5 GJ ...'),
   inside a relative clause and on c1/ge-t14 ('Site 3, which, more than site 4, drew a pedestrian count of 97, ...'); and a
   comparison in mid-clause with no commas ('Coal unlike natural gas supplied about 9.3 GJ ...') had been ENTAILED.
2. A dash typed as two ASCII hyphens ('Coal -- unlike natural gas, roughly 9.3 GJ ... -- declined.') was no dash.
3. A participle or an apposition's head with its relative word between the noun and its modifier ('Coal, providing, unlike nuclear
   power, roughly 42 GJ ...', 'Energy supply, a source that, unlike oil, provided roughly 38 GJ ...') had left the noun unread (no
   check where 84aff95c charged); an apposition opened by 'one' ('Coal, one source which gave 42 GJ ...') was read against the total.
4. An 'at' phrase right after the noun of a comparison or an example that opens the insertion is that noun's figure ('Site 3 (compared
   with site 4 at 15)', 'Fossil fuels (such as natural gas, at 11.8 GJ ...)', 'Fossil fuels (including coal, at 9.3 GJ ...)'), as
   84aff95c read them; follow-up 7 had given them no check.
5. Labels: a comparison in the label or after its colon never names the row ('Coal compared with natural gas: about 9.3 GJ', 'Coal:
   more than natural gas, about 9.3 GJ', 'Site 2 compared with site 5: a pedestrian count of 88'); 'Total:' names the total row; an
   amount of a whole after the colon is no label figure ('Coal: about 294 PJ of the 1,050 PJ total in 2025.'); the one year a label
   writes is the figure's year ('Coal in 2025: about 42 GJ per person.' had no check). On c1/ge-t14 a 'whose' clause with a nested
   comparison ('Site 4, whose EQS, unlike site 6, was 16, ...') reads its column past the comparison (it had no check).
6. The total's own phrase with a row named after the figure inside its modifier ('Energy supply (about 1,050 PJ from coal in 2025)',
   'Ostrel (about 42 GJ per person imported in 2025)'): the figure may be that row's, so no check, never ENTAILED against the total
   and never a charge on the correct component figure.
7. A bracket in a label that holds only a row's name names the row ('Pedestrian count (site 4): 88.' had no check; 'Energy supply per
   person (coal): about 42 GJ in 2025.' was read against the total row, ENTAILED, with the correct 11.8 charged, on the head of the
   branch too); a bracket holding a comparison or other words stays an insertion that never names the row, and a label naming two
   rows ('Coal (natural gas):', 'Site 2 (site 4):') leaves the row not determined: no check.

c2/ge-t15 (worked from the task's own table): 2025 total 1,050 PJ / 24.9 M = 42.2 GJ per person; coal 28% = 11.8, oil 27% = 11.4,
natural gas 22% = 9.3, nuclear 4% = 1.7, hydroelectric 6% = 2.5, wind and solar 13% = 5.5; imports 54% = 22.8 (567 PJ); 2005 total 820
/ 21.4 = 38.3. c1/ge-t14: site (pedestrian count, EQS) 1 (214, 24), 2 (186, 22), 3 (151, 23), 4 (97, 18), 5 (88, 15), 6 (61, 16), 7
(42, 12), 8 (45, 13), 9 (23, 9), 10 (19, 11). Every expected value is fixed here; each fault is pinned with its correct twin.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import geography
from epinoic_logic.branches.insertions import insertion_spans, nested_parts

from . import d9d10_hub as H

_NEUTRAL = {"c2/ge-t15": "The answer uses the supplied table.", "c1/ge-t14": "The answer uses the supplied fieldwork data."}
_BASE: dict = {}
_CEX = (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])
_OK = (["ENTAILED"], [])
_NONE = ([], [])
_BOTH = (["COUNTEREXAMPLE", "ENTAILED"], ["INT-SUBJ-004"])


def _one(record: str, sentence: str):
    """(statuses, subject-matter codes) of ``sentence`` delivered alone as the recorded answer's agent, codes net of a neutral one-line
    answer's (the request reader's INT-REQ-012 and the argument reader's INT-ARG-001, which some of these forms also get on the head of
    the branch, are not this reader's)."""
    _a, question, subject, agent, task_type, docs = H.RECORDED[record]
    rc = H.through_hub(sentence, question, subject, agent, task_type, docs)
    if record not in _BASE:
        _BASE[record] = set(H.codes(H.through_hub(_NEUTRAL[record], question, subject, agent, task_type, docs)))
    return sorted({st for _c, st in H.checks(rc)}), [c for c in sorted(set(H.codes(rc)) - _BASE[record]) if c.startswith("INT-SUBJ")]


# ------------------------------------------------------------------------------------------------- 1. comparisons, ge-t15 rows
_ROWS15 = [("Coal", "coal", "11.8"), ("Oil", "oil", "11.4"), ("Natural gas", "natural gas", "9.3"), ("Nuclear power", "nuclear power", "1.7"),
           ("Hydroelectric power", "hydroelectric power", "2.5"), ("Wind and solar power", "wind and solar power", "5.5")]
_FORMS15 = {
    "comma pair": "{R}, {C}, roughly {v} GJ per person in 2025, fell back.",
    "-ing participle": "{R}, providing, {C}, roughly {v} GJ per person in 2025, fell back.",
    "-ed participle": "{R}, estimated, {C}, at roughly {v} GJ per person in 2025, fell back.",
    "apposition with 'that'": "{R}, a source that, {C}, provided roughly {v} GJ per person in 2025, fell back.",
}
_CMP15 = ("more than {o}", "bigger than {o}", "en comparación con {o}", "más que {o}", "unlike {o}", "rather than {o}")
GRID_CMP15 = [(f.format(R=R, C=c.format(o=_ROWS15[(k + 2) % 6][1]), v=v), right)
              for f in _FORMS15.values() for k, (R, _r, own) in enumerate(_ROWS15) for c in _CMP15
              for v, right in ((_ROWS15[(k + 2) % 6][2], False), (own, True))]


def test_grid_cmp15_size():
    assert len(GRID_CMP15) == 4 * 6 * 6 * 2 == len(set(GRID_CMP15))


@pytest.mark.parametrize("sentence,right", GRID_CMP15)
def test_comparison_before_the_figure_never_names_the_row(sentence, right):
    """The compared row's figure a COUNTEREXAMPLE with INT-SUBJ-004, the head noun's own figure ENTAILED with no finding."""
    assert _one("c2/ge-t15", sentence) == (_OK if right else _CEX)


# the total row's own phrase as the head (the compared row's figure and the 2005 total wrong, the 2025 total right)
_TOTAL_HEADS = ("Energy supply per person", "The total energy supply per person", "Total energy supply per head", "Energy supply per capita")
_TOTAL_FORMS = {
    "comma pair": "{h}, {C}, roughly {v} GJ in 2025, fell back.",
    "-ing participle": "{h}, providing, {C}, roughly {v} GJ in 2025, fell back.",
    "-ed participle": "{h}, estimated, {C}, at roughly {v} GJ in 2025, fell back.",
    "apposition with 'that'": "{h}, a source that, {C}, provided roughly {v} GJ in 2025, fell back.",
}
_TOTAL_CMP = (("more than oil", "11.4"), ("bigger than hydroelectric power", "2.5"), ("unlike coal", "11.8"),
              ("as opposed to natural gas", "9.3"), ("en comparación con coal", "11.8"), ("más que oil", "11.4"))
GRID_TOTAL = [(f.format(h=h, C=c, v=v), right) for f in _TOTAL_FORMS.values() for h in _TOTAL_HEADS for c, cv in _TOTAL_CMP
              for v, right in ((cv, False), ("38", False), ("42", True))]


def test_grid_total_size():
    assert len(GRID_TOTAL) == 4 * 4 * 6 * 3 == len(set(GRID_TOTAL))


@pytest.mark.parametrize("sentence,right", GRID_TOTAL)
def test_total_head_with_a_comparison(sentence, right):
    assert _one("c2/ge-t15", sentence) == (_OK if right else _CEX)


@pytest.mark.parametrize("sentence,expected", [
    # comparisons inside a relative clause or a bracket whose opener had not been read as one (the compared figure had been ENTAILED)
    ("Coal (outweighing natural gas, 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (outweighing natural gas, 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal (which, exceeding natural gas, supplied 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, exceeding natural gas, supplied 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal [which, instead of natural gas, supplied 9.3 GJ per person in 2025] declined.", _CEX),
    ("Coal [which, instead of natural gas, supplied 11.8 GJ per person in 2025] declined.", _OK),
    ("Coal (mayor que natural gas, 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (mayor que natural gas, 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal (which, in place of natural gas, supplied about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, beside natural gas, supplied about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, next to natural gas, supplied about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, against natural gas, supplied about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, differently from natural gas, supplied about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, differently from natural gas, supplied about 11.8 GJ per person in 2025) declined.", _OK),
    # a comparison in mid-clause with no commas (follow-up 7's leftover: the compared figure had been ENTAILED)
    ("Coal unlike natural gas supplied about 9.3 GJ per person in 2025.", _CEX),
    ("Coal unlike natural gas supplied about 11.8 GJ per person in 2025.", _OK),
    ("Coal compared with natural gas supplied about 9.3 GJ per person in 2025.", _CEX),
    ("Coal compared with natural gas supplied about 11.8 GJ per person in 2025.", _OK),
    ("Coal rather than natural gas supplied about 9.3 GJ per person in 2025.", _CEX),
    ("Coal rather than natural gas supplied about 11.8 GJ per person in 2025.", _OK),
    ("Coal supplied about 9.3 GJ per person in 2025 compared with 11.8 GJ for natural gas.", _CEX),
    ("Coal supplied about 11.8 GJ per person in 2025 compared with 9.3 GJ for natural gas.", _OK),
    # an ASCII double hyphen is a dash
    ("Coal -- unlike natural gas, roughly 9.3 GJ per person in 2025 -- declined.", _CEX),
    ("Coal -- unlike natural gas, roughly 11.8 GJ per person in 2025 -- declined.", _OK),
    ("Coal--unlike natural gas, roughly 9.3 GJ per person in 2025--declined.", _CEX),
    ("Coal--unlike natural gas, roughly 11.8 GJ per person in 2025--declined.", _OK),
    # an apposition opened by 'one', or an apposition's head with its relative word, belongs to the noun before it
    ("Coal, one source which gave 42 GJ per person in 2025, declined.", _CEX),
    ("Coal, one source which gave 11.8 GJ per person in 2025, declined.", _OK),
    ("Coal, one source which, compared with natural gas, gave 11.8 GJ per person in 2025, declined.", _OK),
    ("Oil, a source that, more than hydroelectric power, provided roughly 42 GJ per person in 2025, fell back.", _CEX),
    ("Oil, a source that, more than hydroelectric power, provided roughly 11.4 GJ per person in 2025, fell back.", _OK),
    # the regressions of follow-up 7 on 84aff95c: the wrong total figure after a participle and a nested comparison is charged again
    ("Coal, providing, unlike nuclear power, roughly 42 GJ per person in 2025, fell back.", _CEX),
    ("Coal, providing, unlike nuclear power, roughly 11.8 GJ per person in 2025, fell back.", _OK),
    ("Natural gas, estimated, rather than wind and solar power, at roughly 42 GJ per person in 2025, fell back.", _CEX),
    ("Natural gas, estimated, rather than wind and solar power, at roughly 9.3 GJ per person in 2025, fell back.", _OK),
    ("Coal, a source that, compared with natural gas, provided roughly 42 GJ per person in 2025, fell back.", _CEX),
    ("Coal, a source that, compared with natural gas, provided roughly 11.8 GJ per person in 2025, fell back.", _OK),
    # an 'at' phrase right after the noun of an example or a comparison that opens the insertion: that noun's figure
    ("Fossil fuels (such as natural gas, at 11.8 GJ per person in 2025) mattered.", _CEX),
    ("Fossil fuels (such as natural gas, at 9.3 GJ per person in 2025) mattered.", _OK),
    ("Fossil fuels (including coal, at 9.3 GJ per person in 2025) declined.", _CEX),
    ("Fossil fuels (including coal, at 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal, unlike natural gas at 11.8 GJ per person in 2025, declined.", _CEX),
    ("Coal, unlike natural gas at 9.3 GJ per person in 2025, declined.", _OK),
    ("Coal, unlike nuclear power at 11.8 GJ per person in 2025, declined.", _CEX),
    ("Coal, unlike nuclear power at 1.7 GJ per person in 2025, declined.", _OK),
    # after a comparative with 'than' the 'at' phrase may be the compared noun's or the head's: not determined (never ENTAILED, never
    # a charge)
    ("Coal (higher than natural gas at roughly 9.3 GJ per person in 2025) declined.", _NONE),
    ("Coal (higher than natural gas at roughly 11.8 GJ per person in 2025) declined.", _NONE),
    ("Coal (more than nuclear power at 11.8 GJ per person in 2025) declined.", _NONE),
    # Spanish 'que' after an English comparative is a comparison too
    ("Coal (which supplied more que natural gas, roughly 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which supplied more que natural gas, roughly 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal (which supplied more GJ que natural gas, 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which supplied more GJ que natural gas, 11.8 GJ per person in 2025) declined.", _OK),
    # after a comparison's comma the 'at' phrase is the head noun's own
    ("Total energy supply per head, estimated, as opposed to natural gas, at roughly 9.3 GJ in 2025, fell back.", _CEX),
    ("Total energy supply per head, estimated, as opposed to natural gas, at roughly 42 GJ in 2025, fell back.", _OK),
    # unchanged: the follow-up 7 pins
    ("Coal (which, unlike natural gas, supplied about 9.3 GJ per person in 2025) declined.", _CEX),
    ("Coal (which, unlike natural gas, supplied about 11.8 GJ per person in 2025) declined.", _OK),
    ("Coal (which supplied more than natural gas at about 9.3 GJ per person in 2025) declined.", _NONE),
    ("Coal (which supplied more than natural gas at about 11.8 GJ per person in 2025) declined.", _NONE),
])
def test_comparison_lines(sentence, expected):
    assert _one("c2/ge-t15", sentence) == expected


# ------------------------------------------------------------------------------------------------- 5. labels, 6. the total's phrase
@pytest.mark.parametrize("sentence,expected", [
    # a comparison in the label never names the row: coal's figure
    ("Coal compared with natural gas: about 9.3 GJ per person in 2025.", _CEX),
    ("Coal compared with natural gas: about 11.8 GJ per person in 2025.", _OK),
    ("Coal rather than natural gas: about 9.3 GJ per person in 2025.", _CEX),
    ("Coal unlike natural gas: about 9.3 GJ per person in 2025.", _CEX),
    ("Coal vs natural gas: about 9.3 GJ per person in 2025.", _CEX),
    ("Coal more than natural gas: about 9.3 GJ per person in 2025.", _CEX),
    ("Coal in contrast to natural gas: about 9.3 GJ per person in 2025.", _CEX),
    ("Coal in contrast to natural gas: about 11.8 GJ per person in 2025.", _OK),
    ("Wind and solar power compared with nuclear power: about 1.7 GJ per person in 2025.", _CEX),
    ("Wind and solar power compared with nuclear power: about 5.5 GJ per person in 2025.", _OK),
    ("Energy supply compared with coal: about 11.8 GJ per person in 2025.", _CEX),
    ("Energy supply compared with coal: about 42 GJ per person in 2025.", _OK),
    ("Coal, compared with natural gas: about 11.8 GJ per person in 2025.", _OK),
    ("Coal (as opposed to natural gas): about 9.3 GJ per person in 2025.", _CEX),
    # a comparison after the colon never names the row: the label's
    ("Coal: more than natural gas, about 9.3 GJ per person in 2025.", _CEX),
    ("Coal: more than natural gas, about 11.8 GJ per person in 2025.", _OK),
    ("Coal: unlike natural gas, about 9.3 GJ per person in 2025.", _CEX),
    ("Coal: unlike natural gas, about 11.8 GJ per person in 2025.", _OK),
    ("Coal: compared with natural gas, about 9.3 GJ per person in 2025.", _CEX),
    ("Coal: compared with natural gas, about 11.8 GJ per person in 2025.", _OK),
    ("Coal: like natural gas, about 9.3 GJ per person in 2025.", _CEX),
    ("Coal: like natural gas, about 11.8 GJ per person in 2025.", _OK),
    # 'Total' names the table's one total row
    ("Total: about 38 GJ per person in 2025.", _CEX),
    ("Total: about 42 GJ per person in 2025.", _OK),
    ("Total supply: about 38 GJ per person in 2025.", _CEX),
    # the whole a stated amount is part of is no label figure: the correct sentence is never charged (no check, as on 84aff95c)
    ("Coal: about 294 PJ of the 1,050 PJ total in 2025.", _NONE),
    # a row named after the figure in the total's modifier: not determined, never ENTAILED against the total, never a charge
    ("Energy supply (about 1,050 PJ from coal in 2025) changed.", _NONE),
    ("Energy supply (about 294 PJ from coal in 2025) changed.", _NONE),
    ("Ostrel (about 1,050 PJ imported in 2025) changed.", _NONE),
    ("Ostrel (about 567 PJ imported in 2025) changed.", _NONE),
    ("Ostrel (about 42 GJ per person from coal in 2025) changed.", _NONE),
    ("Ostrel (about 11.8 GJ per person from coal in 2025) changed.", _NONE),
    ("Ostrel (about 42 GJ per person from oil in 2025) changed.", _NONE),
    ("Ostrel (about 11.4 GJ per person from oil in 2025) changed.", _NONE),
    ("Energy supply, about 42 GJ per person from coal in 2025, changed.", _NONE),
    ("Energy supply, about 11.8 GJ per person from coal in 2025, changed.", _NONE),
    ("Energy supply (42 GJ per person coal in 2025) changed.", _NONE),
    ("Energy supply (11.8 GJ per person coal in 2025) changed.", _NONE),
    ("Ostrel (about 42 GJ per person imported in 2025) changed.", _NONE),
    ("Ostrel (about 23 GJ per person imported in 2025) changed.", _NONE),
    # the figure's own words after it name its row; a total label keeps its figure when the rows come in a later clause
    ("Coal and natural gas compared: about 9.3 GJ per person in 2025 for gas.", _OK),
    ("Coal and natural gas compared: about 11.8 GJ per person in 2025 for gas.", _CEX),
    ("Energy supply per person: about 38 GJ in 2025, of which coal gave 11.8 GJ.", _BOTH),
    ("Energy supply per person: about 42 GJ in 2025, of which coal gave 11.8 GJ.", _OK),
    # the one year a label writes before its colon is the figure's year (these had no check)
    ("Energy supply per person in 2025: about 38 GJ.", _CEX),
    ("Energy supply per person in 2025: about 42 GJ.", _OK),
    ("Coal in 2025: about 42 GJ per person.", _CEX),
    ("Coal in 2025: about 11.8 GJ per person.", _OK),
    ("Coal (2025): about 42 GJ per person.", _CEX),
    ("Coal (2025): about 11.8 GJ per person.", _OK),
    ("Energy supply per person, 2005: about 42 GJ.", _CEX),
    ("Energy supply per person, 2005: about 38 GJ.", _OK),
    ("2025, natural gas: about 11.8 GJ per person.", _CEX),
    ("2025, natural gas: about 9.3 GJ per person.", _OK),
    ("In 2005 and 2025: about 42 GJ per person.", _NONE),
    # a comparison after the figure in the total's modifier never names the row: the total's (the check lens's grid, where a first
    # form of the row-after-the-figure reading had lost these charges)
    ("Ostrel, which provided roughly 38 GJ per person in 2025, unlike nuclear power, fell back.", _CEX),
    ("Ostrel, which provided roughly 42 GJ per person in 2025, unlike nuclear power, fell back.", _OK),
    ("Energy supply per capita (roughly 38 GJ in 2025, as opposed to hydroelectric power) fell back.", _CEX),
    ("Energy supply per person, roughly 38 GJ in 2025, unlike coal, fell back.", _CEX),
    ("Energy supply per person, roughly 42 GJ in 2025, unlike coal, fell back.", _OK),
    ("Ostrel, roughly 1.7 GJ per person in 2025 unlike nuclear power, fell back.", _CEX),
    ("Ostrel, roughly 42 GJ per person in 2025 unlike nuclear power, fell back.", _OK),
    ("Energy supply per head, roughly 11.8 GJ in 2025 más que coal, fell back.", _CEX),
    ("Energy supply per head, roughly 42 GJ in 2025 más que coal, fell back.", _OK),
    ("Energy supply: about 38 GJ per person in 2025, unlike coal.", _CEX),
    ("Energy supply: about 42 GJ per person in 2025, unlike coal.", _OK),
    # unchanged: the total's own phrase with no row after the figure, and the follow-up 7 label pins
    ("Ostrel (about 42 GJ per person in 2025) imported more.", _OK),
    ("Ostrel (about 38 GJ per person in 2025) imported more.", _CEX),
    ("Coal: about 42 GJ per person in 2025.", _CEX),
    ("Coal: about 11.8 GJ per person in 2025.", _OK),
    ("Answer: about 42 GJ per person in 2025.", _NONE),
    ("Result: coal supplied about 42 GJ per person in 2025.", _CEX),
])
def test_label_and_total_lines(sentence, expected):
    assert _one("c2/ge-t15", sentence) == expected


# ------------------------------------------------------------------------------------------------- c1/ge-t14: sites
_SITES = {1: (214, 24), 2: (186, 22), 3: (151, 23), 4: (97, 18), 5: (88, 15), 6: (61, 16), 7: (42, 12), 8: (45, 13), 9: (23, 9), 10: (19, 11)}
_FORMS14 = {
    "relative clause": "Site {s}, which, {C}, drew a {col} of {v}, stood out.",
    "comma pair": "Site {s}, {C}, a {col} of {v}, stood out.",
    "bracket": "Site {s} ({C}, a {col} of {v}) stood out.",
    "dash pair": "Site {s} -- {C}, a {col} of {v} -- stood out.",
}
_CMP14 = ("more than site {o}", "bigger than site {o}", "en comparación con site {o}", "más que site {o}", "instead of site {o}", "behind site {o}")
GRID_SITE = [(f.format(s=s, C=c.format(o=(s + 3) % 10 + 1), col=col, v=v), right)
             for f in _FORMS14.values() for s in (2, 3, 6, 9) for col, k in (("pedestrian count", 0), ("EQS", 1)) for c in _CMP14
             for v, right in ((_SITES[(s + 3) % 10 + 1][k], False), (_SITES[s][k], True))]


def test_grid_site_size():
    assert len(GRID_SITE) == 4 * 4 * 2 * 6 * 2 == len(set(GRID_SITE))


@pytest.mark.parametrize("sentence,right", GRID_SITE)
def test_site_comparison_never_names_the_row(sentence, right):
    assert _one("c1/ge-t14", sentence) == (_OK if right else _CEX)


@pytest.mark.parametrize("sentence,expected", [
    ("Site 3, which, more than site 4, drew a pedestrian count of 97, was busy.", _CEX),
    ("Site 3, which, more than site 4, drew a pedestrian count of 151, was busy.", _OK),
    ("Site 9, which, less than site 8, drew a pedestrian count of 45, was quiet.", _CEX),
    ("Site 9, which, less than site 8, drew a pedestrian count of 23, was quiet.", _OK),
    ("Site 6, which, more than site 5, scored an EQS of 15, improved.", _CEX),
    ("Site 6, which, more than site 5, scored an EQS of 16, improved.", _OK),
    ("Site 2 -- unlike site 5, a pedestrian count of 88 -- was busy.", _CEX),
    ("Site 2 -- unlike site 5, a pedestrian count of 186 -- was busy.", _OK),
    ("Site 3 (behind site 1, a pedestrian count of 214) was busy.", _CEX),
    ("Site 3 (behind site 1, a pedestrian count of 151) was busy.", _OK),
    ("Site 2 (which, instead of site 5, had a pedestrian count of 88) was busier.", _CEX),
    ("Site 2 (which, instead of site 5, had a pedestrian count of 186) was busier.", _OK),
    ("Site 2 (which, beside site 5, had a pedestrian count of 88) was busier.", _CEX),
    ("Site 2 (which, against site 5, had a pedestrian count of 88) was busier.", _CEX),
    # an 'at' phrase right after the compared site: that site's figure (the main clause's 23 is site 3's EQS)
    ("Site 3 (compared with site 4 at 15) had a higher EQS of 23.", _BOTH),
    ("Site 3 (compared with site 4 at 18) had a higher EQS of 23.", _OK),
    ("Site 5 (compared with site 6 at 18) had a lower EQS of 15.", _BOTH),
    ("Site 5 (compared with site 6 at 16) had a lower EQS of 15.", _OK),
    # a 'whose' clause with a nested comparison: the column word before the comparison is the figure's (these had no check)
    ("Site 4, whose EQS, unlike site 6, was 16, stood out.", _CEX),
    ("Site 4, whose EQS, unlike site 6, was 18, stood out.", _OK),
    ("Site 4 (whose EQS, unlike site 6, was 16) stood out.", _CEX),
    ("Site 4 (whose EQS, unlike site 6, was 18) stood out.", _OK),
    ("Site 4, whose pedestrian count, more than site 5, was 88, stood out.", _CEX),
    ("Site 4, whose pedestrian count, more than site 5, was 97, stood out.", _OK),
    # a comparison in a label never names the row
    ("Site 2 compared with site 5: a pedestrian count of 88.", _CEX),
    ("Site 2 compared with site 5: a pedestrian count of 186.", _OK),
    ("Site 2 rather than site 5: a pedestrian count of 88.", _CEX),
    ("Site 2 unlike site 5: a pedestrian count of 88.", _CEX),
    ("Site 2 vs site 5: a pedestrian count of 88.", _CEX),
    ("Site 2 vs site 5: a pedestrian count of 186.", _OK),
    ("Site 2: more than site 5, a pedestrian count of 88.", _CEX),
    ("Site 2: more than site 5, a pedestrian count of 186.", _OK),
    # unchanged: the follow-up 7 pins
    ("Site 2 (unlike site 5, which had a pedestrian count of 88) was busy.", _NONE),
    ("Site 2, which had more pedestrians than the 97 counted at site 4, was busy.", _NONE),
    ("Site 4 (EQS 24) stood out.", _CEX),
    ("Site 4 (EQS 18) stood out.", _OK),
])
def test_site_lines(sentence, expected):
    assert _one("c1/ge-t14", sentence) == expected


# ------------------------------------------------------------------------------------------------- 7. a row's name in a label's bracket
@pytest.mark.parametrize("record,sentence,expected", [
    ("c1/ge-t14", "Pedestrian count (site 4): 88.", _CEX),
    ("c1/ge-t14", "Pedestrian count (site 4): 97.", _OK),
    ("c1/ge-t14", "Pedestrian count [site 4]: 88.", _CEX),
    ("c1/ge-t14", "Pedestrian count [site 4]: 97.", _OK),
    ("c1/ge-t14", "EQS (site 4): 16.", _CEX),
    ("c1/ge-t14", "EQS (site 4): 18.", _OK),
    ("c1/ge-t14", "Site 2 (site 4): 186.", _NONE),
    ("c1/ge-t14", "Site 2 (site 4): 97.", _NONE),
    ("c1/ge-t14", "Pedestrian count (site 4 and site 5): 97.", _NONE),
    ("c1/ge-t14", "Pedestrian count (site 4, unlike site 2): 186.", _NONE),
    ("c1/ge-t14", "Pedestrian count (unlike site 2): 186.", _NONE),
    ("c2/ge-t15", "Energy supply per person (coal): about 42 GJ in 2025.", _CEX),
    ("c2/ge-t15", "Energy supply per person (coal): about 11.8 GJ in 2025.", _OK),
    ("c2/ge-t15", "Supply per person (coal): about 42 GJ in 2025.", _CEX),
    ("c2/ge-t15", "Supply per person (coal): about 11.8 GJ in 2025.", _OK),
    ("c2/ge-t15", "Supply per person (natural gas): about 11.8 GJ in 2025.", _CEX),
    ("c2/ge-t15", "Supply per person (natural gas): about 9.3 GJ in 2025.", _OK),
    ("c2/ge-t15", "Coal (natural gas): about 11.8 GJ per person in 2025.", _NONE),
    ("c2/ge-t15", "Coal (natural gas): about 9.3 GJ per person in 2025.", _NONE),
    ("c2/ge-t15", "Energy supply per person (coal and oil): about 11.8 GJ in 2025.", _NONE),
    # unchanged: a bracket holding a comparison or other words never names the row
    ("c2/ge-t15", "Coal (unlike natural gas): about 9.3 GJ per person in 2025.", _CEX),
    ("c2/ge-t15", "Coal (unlike natural gas): about 11.8 GJ per person in 2025.", _OK),
    ("c2/ge-t15", "Energy supply per person (mostly coal): about 11.8 GJ in 2025.", _CEX),
    ("c2/ge-t15", "Energy supply per person (mostly coal): about 42 GJ in 2025.", _OK),
])
def test_a_row_name_in_a_label_bracket(record, sentence, expected):
    assert _one(record, sentence) == expected


# ------------------------------------------------------------------------------------------------- the helpers and linear time
def test_compare_openers_only_where_asked():
    """The comparison openers are read only by the Geography readers: the shared reading of the other packs is unchanged."""
    text = "Oil, more than hydroelectric power, roughly 11.4 GJ per person in 2025, fell back."
    assert [text[a:b] for a, b in insertion_spans(text, compare=True)] == [", more than hydroelectric power,"]
    assert insertion_spans(text) == ()
    text = "Coal unlike natural gas supplied about 11.8 GJ per person in 2025."
    assert [text[a:b] for a, b in insertion_spans(text, compare=True)] == ["unlike natural gas "]
    assert insertion_spans(text) == ()
    text = "Coal (which, exceeding natural gas, supplied 9.3 GJ) declined."
    lo, hi = text.index("which"), text.index(") declined")
    assert [(text[a:b], k) for a, b, k in nested_parts(text, lo, hi)] == [("exceeding natural gas", "c")]
    assert geography._dash_fold("Coal -- unlike gas --- x--y") == "Coal —  unlike gas —   x— y"


@pytest.mark.parametrize("unit", [
    "Oil, providing, more than hydroelectric power, roughly 11.4 GJ per person in 2025, ",
    "Coal -- unlike natural gas, roughly 11.8 GJ -- ",
    "Coal compared with natural gas: about 11.8 GJ per person; ",
    "Coal: more than natural gas, about 11.8 GJ, 9.3 GJ, 1.7 GJ, ",
    "Fossil fuels (such as natural gas, at 9.3 GJ per person) ",
    "Energy supply (about 1,050 PJ from coal in 2025) ",
    "Supply per person (coal): about 11.8 GJ in 2025; ",
    "Energy supply per person (coal) (oil) [gas]: about 11.8 GJ, 9.3 GJ; ",
])
def test_check_reading_is_linear(unit):
    """Hostile input: each figure's reading is a few bisections over what is read once per sentence, label or insertion."""
    from epinoic_logic.branches.grounded_figures import supplied_tables
    _a, _q, _s, _g, _t, docs = H.RECORDED["c2/ge-t15"]
    table = geography._yt_documents(supplied_tables(H.supplied(docs)))[0]
    total = geography._yt_total_of(table) + (frozenset({"ostrel"}),)

    def run(k: int) -> float:
        text = unit * k + "declined in 2025."
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
    ("Coal compared with natural gas: about 11.8 GJ per person in 2025; ", "c2/ge-t15"),
    ("Coal -- unlike natural gas, roughly 11.8 GJ per person in 2025 -- declined, ", "c2/ge-t15"),
    ("Site 2 compared with site 5: a pedestrian count of 186; ", "c1/ge-t14"),
    ("Site 3, which, more than site 4, drew a pedestrian count of 151, was busy, ", "c1/ge-t14"),
    ("Pedestrian count (site 4): 97; ", "c1/ge-t14"),
    ("Energy supply per person (coal): about 11.8 GJ in 2025; ", "c2/ge-t15"),
])
def test_check_reading_through_the_reader_is_linear(unit, record):
    """Hostile input through the readers themselves (a sentence of 200 kB never stalls)."""
    text = unit * (200_000 // len(unit) + 1) + "and so on."
    assert len(text) > 200_000
    t0 = time.perf_counter()
    _one(record, text)
    assert time.perf_counter() - t0 < 60
