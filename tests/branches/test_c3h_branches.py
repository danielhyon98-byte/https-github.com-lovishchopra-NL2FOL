"""Follow-up 6 (c3h) of the branch packs: the push check of 67bc64ec.

1. A figure inside a modifier of a noun belongs to that noun and is read against that noun's row: a relative clause ('Coal, which
   supplied about 11.8 GJ per person in 2025, declined.'), a bracket, a pair of dashes, an 'at' phrase, a participle phrase, a 'whose'
   clause, an apposition opened by an article and a bare figure in a comma pair. 67bc64ec read the relative-clause form against the
   total row (ENTAILED for the wrong 42 GJ, its correct 11.8 GJ twin charged); the bracket, dash, 'at', participle and 'whose' forms were
   read that way before it as well (c2/ge-t15: total 1,050 PJ / 24.9 M = 42.2 GJ per person; coal 28% = 11.8, oil 27% = 11.4, natural
   gas 22% = 9.3, nuclear 4% = 1.7, hydroelectric 6% = 2.5, wind and solar 13% = 5.5). Where the noun names no one row, the figure gets
   no check: never ENTAILED, and never a charge. The push-check lenses' grids are rebuilt here on c2/ge-t15 and c1/ge-t14: every wrong
   cell a COUNTEREXAMPLE with INT-SUBJ-004, every correct cell ENTAILED with no finding.
2. Language B (c1/sp-t14): a correction written with labels ('Incorrecto: x. Correcto: y') keeps the year and count checks of its
   corrected half (67bc64ec skipped every such line). The labels decide only which half is the writer's correction; the replaced half
   is never read as a claim. The text: the school had been closed since 2009 and reopened with catorce alumnos.

Every expected value is fixed here; each fault is pinned with its correct twin.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import geography, language_b

from . import d9d10_hub as H

_NEUTRAL = {"c2/ge-t15": "The answer uses the supplied table.", "c1/ge-t14": "The answer uses the supplied fieldwork data.",
            "c1/sp-t14": "6. La escuela está en Valdeoca.", "c3/sp-t16": "Your email answers the task."}
_BASE: dict = {}


def _one(record: str, sentence: str):
    """(statuses, codes) of ``sentence`` delivered alone as the recorded answer's agent; codes net of a neutral one-line answer's."""
    _a, question, subject, agent, task_type, docs = H.RECORDED[record]
    rc = H.through_hub(sentence, question, subject, agent, task_type, docs)
    if record not in _BASE:
        _BASE[record] = set(H.codes(H.through_hub(_NEUTRAL[record], question, subject, agent, task_type, docs)))
    return sorted({st for _c, st in H.checks(rc)}), sorted(set(H.codes(rc)) - _BASE[record])


# ------------------------------------------------------------------------------------------------- 1. c2/ge-t15: the figure's noun
_ROWS15 = [("Coal", "11.8"), ("Oil", "11.4"), ("Natural gas", "9.3"), ("Nuclear power", "1.7"), ("Hydroelectric power", "2.5"),
           ("Wind and solar power", "5.5")]
_FORMS15 = {
    "relative clause": "{r}, which supplied about {v} GJ per person in 2025, {m}.",
    "bracket": "{r} (about {v} GJ per person in 2025) {m}.",
    "dash pair": "{r} — about {v} GJ per person in 2025 — {m}.",
    "at phrase": "{r}, at about {v} GJ per person in 2025, {m}.",
    "participle phrase": "{r}, supplying about {v} GJ per person in 2025, {m}.",
    "whose clause": "{r}, whose supply reached about {v} GJ per person in 2025, {m}.",
    "article apposition": "{r}, a source that supplied about {v} GJ per person in 2025, {m}.",
    "bare comma pair": "{r}, about {v} GJ per person in 2025, {m}.",
    "past participle": "{r}, supplied at about {v} GJ per person in 2025, {m}.",
}
_MAIN15 = ("declined", "mattered")  # (a main verb the subject reader knows, and one it does not)
GRID15 = [(f.format(r=r, v=v, m=m), right) for f in _FORMS15.values() for r, w in _ROWS15 for m in _MAIN15 for v, right in (("42", False), (w, True))]


def test_grid15_has_216_cells():
    assert len(GRID15) == 216 and len(set(GRID15)) == 216


@pytest.mark.parametrize("sentence,right", GRID15)
def test_figure_in_a_modifier_is_its_nouns(sentence, right):
    statuses, codes = _one("c2/ge-t15", sentence)
    if right:
        assert (statuses, codes) == (["ENTAILED"], [])
    else:
        assert (statuses, codes) == (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])


@pytest.mark.parametrize("sentence,expected", [
    # the push check's own lines (the 67bc64ec regression and the pre-existing forms of the class), each with its correct twin
    ("Coal, which supplied about 42 GJ per person in 2025, declined.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Coal, which supplied about 11.8 GJ per person in 2025, declined.", (["ENTAILED"], [])),
    ("Oil (about 42 GJ per person in 2025) changed least.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Oil (about 11.4 GJ per person in 2025) changed least.", (["ENTAILED"], [])),
    ("Coal — about 42 GJ per person in 2025 — mattered.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Natural gas, at about 42 GJ per person in 2025, mattered.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Nuclear power, supplying about 42 GJ per person in 2025, mattered.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Hydroelectric power, whose supply reached about 42 GJ per person in 2025, mattered.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Coal, a fuel that supplied about 42 GJ per person in 2025, declined.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Coal, a fuel that supplied about 11.8 GJ per person in 2025, declined.", (["ENTAILED"], [])),
    ("Natural gas, which provided roughly 42 GJ per person in 2025, grew.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Natural gas, which provided roughly 9.3 GJ per person in 2025, grew.", (["ENTAILED"], [])),
    # another year, an amount and a listed pair of rows are the noun's too
    ("Coal, which supplied about 38 GJ per person in 2005, declined.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),  # (coal 46% = 17.6)
    ("Coal, which supplied about 17.6 GJ per person in 2005, declined.", (["ENTAILED"], [])),
    ("Coal, which supplied 1,050 PJ in 2025, declined.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),  # (coal 28% of 1,050 = 294)
    ("Coal, which supplied 294 PJ in 2025, declined.", (["ENTAILED"], [])),
    ("Coal (1,050 PJ in 2025) declined.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Coal (294 PJ in 2025) declined.", (["ENTAILED"], [])),
    ("Coal and oil, which together supplied about 42 GJ per person in 2025, declined.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Coal and oil, which together supplied about 23.2 GJ per person in 2025, declined.", (["ENTAILED"], [])),  # (55% = 23.2)
    # the noun names no row of the table: no check, never ENTAILED and never the total row by default (an over-block of the total's
    # own form fails closed)
    ("Petroleum, at about 42 GJ per person in 2025, mattered.", ([], [])),
    ("Ostrel, at about 42 GJ per person in 2025, imported more.", ([], [])),
    ("Energy supply per person, at about 42 GJ in 2025, rose.", ([], [])),
    ("Energy supply per person (about 42 GJ in 2025) rose.", ([], [])),
    # the fixes of 08c4a36b stay fixed: a main-clause figure with a subordinate clause in between, an apposition naming the subject
    ("Energy supply per person, while coal declined, was about 11.8 GJ in 2025.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Energy supply per person, while coal declined, was about 42 GJ in 2025.", (["ENTAILED"], [])),
    ("One source, natural gas, supplied about 9.3 GJ per person in 2025.", (["ENTAILED"], [])),
    ("One source, natural gas, supplied about 42 GJ per person in 2025.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    # a participle after a whole clause is that clause's subject's (unchanged)
    ("Energy supply per person rose from about 38 GJ in 2005, reaching about 11.8 GJ in 2025.", (["COUNTEREXAMPLE", "ENTAILED"], ["INT-SUBJ-004"])),
    ("Energy supply per person rose from about 38 GJ in 2005, reaching about 42 GJ in 2025.", (["ENTAILED"], [])),
])
def test_figure_in_a_modifier_lines(sentence, expected):
    assert _one("c2/ge-t15", sentence) == expected


# ------------------------------------------------------------------------------------------------- 1. c1/ge-t14: the same forms
_ROWS14 = [("4", {"pedestrian count": ("97", "60"), "EQS": ("18", "24"), "retail share": ("60", "97")}),
           ("2", {"pedestrian count": ("186", "214"), "EQS": ("22", "85"), "retail share": ("85", "22")})]
_FORMS14 = ["Site {s}, which had a {c} of {v}, {m}.", "Site {s} ({c} {v}) {m}.", "Site {s} — {c} {v} — {m}.", "Site {s}, at a {c} of {v}, {m}.",
            "Site {s}, recording a {c} of {v}, {m}.", "Site {s}, whose {c} was {v}, {m}."]
GRID14 = [(f.format(s=s, c=c, v=v, m=m), right) for f in _FORMS14 for s, cols in _ROWS14 for c, (good, bad) in cols.items()
          for m in ("lies on the main road", "stood out") for v, right in ((bad, False), (good, True))]


def test_grid14_has_144_cells():
    assert len(GRID14) == 144 and len(set(GRID14)) == 144


@pytest.mark.parametrize("sentence,right", GRID14)
def test_site_figure_in_a_modifier_is_its_sites(sentence, right):
    statuses, codes = _one("c1/ge-t14", sentence)
    if right:
        assert (statuses, codes) == (["ENTAILED"], [])
    else:
        assert (statuses, codes) == (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])


@pytest.mark.parametrize("unit", ["Coal, which supplied about 11.8 GJ per person in 2025, ", "Oil (about 11.4 GJ per person in 2025) ",
                                  "Coal — about 11.8 GJ — ", "Natural gas, at about 9.3 GJ, ", "Coal, supplying about 11.8 GJ, ",
                                  "Coal, whose supply reached about 11.8 GJ, ", "Coal, about 11.8 GJ per person, "])
def test_modifier_reading_is_linear(unit):
    """Hostile input: the modifier reading is a few bisections per figure over the sentence read once."""
    from epinoic_logic.branches.grounded_figures import supplied_tables
    _a, _q, _s, _g, _t, docs = H.RECORDED["c2/ge-t15"]
    table = geography._yt_documents(supplied_tables(H.supplied(docs)))[0]

    def run(k: int) -> float:
        text = unit * k + "declined in 2025."
        t0 = time.perf_counter()
        idx = geography._YtIndex(text)
        for m in geography._YT_NUMBER_RE.finditer(text):
            idx.attached(table, m.start())
            idx.row(table, m.start())
        return time.perf_counter() - t0
    run(50)
    small, large = min(run(500) for _ in range(3)), min(run(4000) for _ in range(3))
    assert large < small * 8 * 3 + 0.05  # 8 times the input: well under quadratic growth


def test_modifier_reading_through_the_reader_is_linear():
    """Hostile input through the table reader itself (a sentence of 200 kB never stalls)."""
    text = "Coal, which supplied about 11.8 GJ per person in 2025, " * 3700 + "declined."
    assert len(text) > 200_000
    t0 = time.perf_counter()
    _one("c2/ge-t15", text)
    assert time.perf_counter() - t0 < 60


# ------------------------------------------------------------------------------------------------- 2. Language B: label pairs
@pytest.mark.parametrize("sentence,expected", [
    # the push check's line: its corrected half's year is checked again (the school closed in 2009)
    ("Incorrecto: la escuela cerró en 1990. Correcto: la escuela cerró en 1975.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Incorrecto: la escuela cerró en 1990. Correcto: la escuela cerró en 2009.", (["ENTAILED"], [])),
    ("Incorrecto: la escuela cerró en 2009. Correcto: la escuela cerró en 1990.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Mal: la escuela cerró en 1990. Bien: la escuela cerró en 2009.", (["ENTAILED"], [])),
    ("Mal: la escuela cerró en 2009. Bien: la escuela cerró en 1990.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Wrong: the school closed in 1990. Right: the school closed in 2009.", (["ENTAILED"], [])),
    ("Wrong: the school closed in 2009. Right: the school closed in 1990.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    # the unlabelled and right-labelled controls
    ("La escuela cerró en 1990.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Correcto: la escuela cerró en 1990.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
])
def test_label_pair_keeps_the_year_check_of_its_corrected_half(sentence, expected):
    assert _one("c1/sp-t14", sentence) == expected


@pytest.mark.parametrize("sentence,expected", [
    # the count check of a corrected half (the task: an exchange of tres semanas)
    ("Incorrecto: el intercambio duró tres semanas. Correcto: el intercambio duró dos semanas.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Incorrecto: el intercambio duró dos semanas. Correcto: el intercambio duró tres semanas.", ([], [])),
    ("Mal: el intercambio duró tres semanas. Bien: el intercambio duró dos semanas.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
    ("Mal: el intercambio duró dos semanas. Bien: el intercambio duró tres semanas.", ([], [])),
    ("El intercambio duró dos semanas.", (["COUNTEREXAMPLE"], ["INT-SUBJ-004"])),
])
def test_label_pair_keeps_the_count_check_of_its_corrected_half(sentence, expected):
    assert _one("c3/sp-t16", sentence) == expected


def test_label_pair_half():
    line = "Incorrecto: la escuela cerró en 1990. Correcto: la escuela cerró en 1975."
    assert language_b._label_pair_half(line) == line.index("la escuela cerró en 1975") == 48
    assert language_b._label_pair_half("- Mal: x. Bien: y") == 16
    assert language_b._label_pair_half("La escuela cerró en 1990.") is None
    assert language_b._label_pair_half("Correcto: la escuela cerró en 1990.") is None


# the correction-count fix of 67bc64ec stays fixed: a label correction line is counted among the answer's corrections
_SP16_LINE = '- "El primer semana fue difícil" → "La primera semana fue difícil" (semana is feminine; primer is shortened only before a masculine singular noun).'
_EXPL = " (semana is feminine; primer is shortened only before a masculine singular noun)."


@pytest.mark.parametrize("form", [
    "- Incorrecto: El primer semana fue difícil. Correcto: La primera semana fue difícil" + _EXPL,
    "- Mal: El primer semana fue difícil. Bien: La primera semana fue difícil" + _EXPL,
    "- ✗ El primer semana fue difícil ✓ La primera semana fue difícil" + _EXPL,
])
def test_label_correction_lines_are_still_counted(form):
    base = H.RECORDED["c3/sp-t16"][0]
    assert _SP16_LINE in base

    def listed(answer):
        return [c for c in H.checks(H.recorded("c3/sp-t16", answer)) if c[0].startswith("language-b-listed-count")]
    assert {st for _c, st in listed(base.replace(_SP16_LINE, form))} == {"ENTAILED"}
    wrong = base.replace(_SP16_LINE, form).replace("fix the six points", "fix the seven points")
    assert ("language-b-listed-count-1", "COUNTEREXAMPLE") in listed(wrong)


def test_label_pair_reading_is_linear():
    """Hostile input: a 200 kB answer of label-pair lines is read line by line (the label match reads each line's head only)."""
    line = "Incorrecto: la escuela cerró en 1990. Correcto: la escuela cerró en 2009.\n"
    text = line * (200_000 // len(line) + 1)
    assert len(text) > 200_000
    t0 = time.perf_counter()
    _one("c1/sp-t14", text)
    assert time.perf_counter() - t0 < 120
