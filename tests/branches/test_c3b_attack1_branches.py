"""Attack round 1 of c3b on the branches: correct work that a reader failed, a false verdict a reader showed as checked, and two stalls.
Each expected value is fixed here (never relaxed to make the code pass).

* ``log2(1024) = 10``: the base written straight after "log" is the logarithm's base, never "log times 2" (STEM lexer).
* An elasticity stated with the changes named after their figures ("a 10% rise in price causes a 5% fall in quantity demanded"): the
  quantity's change over the price's (Economics pack).
* Spanish thousands written with a point ("50.000 habitantes") in a Spanish text (worked arithmetic and STEM lexer).
* A Spanish question after an answer ("... = 12. ¿Alguien ha revisado este resultado?") is a sentence of its own (segmenters).
* Geography: a compound average annual growth over more than twelve years; the critical value read as the number after "critical value
  of" (a significance level after it is no critical value); a list of row labels ("Sites 1, 2 and 3") names no single row; the case-figure
  anchor and the table-count reader stay linear on a long sentence."""
from __future__ import annotations

import time

import pytest

from . import d9d10_hub as H

ERR = "INT-SUBJ-001"


def _errors(rc) -> list[str]:
    return [f.code for f in rc.findings if f.severity == "error"]


@pytest.mark.parametrize("subject,agent,text", [
    ("Computer Science", "cs-specialist", "Binary search on a sorted list of 1,024 items needs at most 11 comparisons, since log2(1024) = 10."),
    ("Computer Science", "cs-specialist", "log2(1024) = 10."),
    ("Mathematics: Analysis and Approaches", "maths-specialist", "log2(1024) = 10, since 2¹⁰ = 1024."),
    ("Economics", "economics-specialist", "With PED = -0.5, a 10% rise in price causes a 5% fall in quantity demanded."),
    ("Economics", "economics-specialist", "If price elasticity of demand is -0.5, a 10% price rise reduces quantity demanded by 5%."),
    ("Geography", "geography-specialist", "La densidad de población es 50.000 habitantes / 100 km² = 500 habitantes por km²."),
    ("Language B: Spanish", "language-b-spanish-specialist",
     "La ciudad tiene 50.000 habitantes y 100 km², así que la densidad es 50.000 / 100 = 500 habitantes por km²."),
    ("Mathematics: Analysis and Approaches", "maths-specialist",
     "La derivada de f(x) = x³ es f'(x) = 3x², por lo que f'(2) = 12. ¿Alguien ha revisado este resultado?"),
])
def test_correct_work_carries_no_error(subject, agent, text):
    rc = H.through_hub(text, "Answer the question.", subject, agent)
    assert _errors(rc) == [], (text, [(f.code, f.message[:200]) for f in rc.findings if f.severity == "error"])


@pytest.mark.parametrize("subject,agent,text", [
    ("Computer Science", "cs-specialist", "log2(1024) = 11."),
    ("Economics", "economics-specialist", "With PED = -0.5, a 10% rise in price causes a 20% fall in quantity demanded."),
    ("Language B: Spanish", "language-b-spanish-specialist",
     "La ciudad tiene 50.000 habitantes y 100 km², así que la densidad es 50.000 / 100 = 600 habitantes por km²."),
])
def test_the_same_slips_are_still_named(subject, agent, text):
    rc = H.through_hub(text, "Answer the question.", subject, agent)
    assert ERR in _errors(rc), (text, [(f.code, f.message[:200]) for f in rc.findings])


def test_a_spanish_question_after_the_answer_is_its_own_claim():
    from epinoic_logic.adapters.stem_specialist.parser import StemTextParser
    p = StemTextParser(agent_id="maths-specialist", mode="mathematics")
    r = p.parse_response("La derivada de f(x) = x³ es f'(x) = 3x², por lo que f'(2) = 12. ¿Alguien ha revisado este resultado?",
                         request_id="r", task_id="t", report_id="x", subject="Mathematics: Analysis and Approaches", task_type="calculation")
    assert [(c.claim_role, c.materiality) for c in r.claims] == [("point", "material"), ("other", "supporting")]


GEO = [
    # (record, appended sentence, expected new error findings, expected geography check status or None)
    ("c2/ge-t15", "Ostrel's population grew from 21.4 million in 2005 to 24.9 million in 2025, an average annual growth rate of 0.76%.",
     [], ("geography-growth-rate-1", "ENTAILED")),
    ("c3/ge-t16", "The town grew from 1,000 in 2000 to 2,000 in 2035, an average annual growth rate of 2%.", [], ("geography-growth-rate-1", "ENTAILED")),
    ("c2/ge-t15", "Ostrel's population grew from 21.4 million in 2005 to 24.9 million in 2025, an average annual growth rate of 3.5%.",
     [ERR], ("geography-growth-rate-1", "COUNTEREXAMPLE")),
    ("c3/ge-t16", "rs = 0.42 is below the critical value of 0.648 at the 0.05 level, so we accept the null hypothesis.", [],
     ("geography-significance-1", "ENTAILED")),
    ("c3/ge-t16", "rs = 0.42 is below the critical value of 0.648 at the 0.05 significance level, so it is not significant.", [],
     ("geography-significance-1", "ENTAILED")),
    ("c1/ge-t14", "rs = 0.42 is below the critical value of 0.648 at the 0.05 level, so the correlation is significant.", [ERR],
     ("geography-significance-1", "COUNTEREXAMPLE")),
    ("c1/ge-t14", "Your value of rs = 0.30 against the critical value of 0.648 at the 0.05 level means the correlation is statistically significant.",
     [ERR], ("geography-significance-1", "COUNTEREXAMPLE")),
    ("c1/ge-t14", "The mean count at Sites 1, 2 and 3 (214, 186 and 151) is 183.7.", [], None),
]


@pytest.mark.parametrize("rec,sentence,errors,check", GEO)
def test_geography_reads(rec, sentence, errors, check):
    base = H.recorded(rec)
    rc = H.recorded(rec, H.RECORDED[rec][0] + "\n\n" + sentence)
    before = {(f.code, f.message) for f in base.findings}
    new = sorted({f.code for f in rc.findings if f.severity in ("error", "warning") and (f.code, f.message) not in before
                  and f.code in (ERR, "INT-SUBJ-004")})
    assert new == errors, (sentence, [(f.code, f.message[:200]) for f in rc.findings if (f.code, f.message) not in before])
    if check is not None:
        assert check in H.checks(rc, "geography-"), H.checks(rc, "geography-")
    else:
        assert not [c for c in H.checks(rc, "geography-supplied") if c not in H.checks(base, "geography-supplied")]


@pytest.mark.parametrize("unit", ["Haiti 300,000 deaths Kobe 6,000 deaths ", "Abcde Fghij Klmno 12 deaths "])
def test_the_case_anchor_reader_is_linear(unit):
    # (it was O(figures x names): 7 s, 33 s and 120 s at 50, 100 and 200 kB; the work per figure is now a search in the names read once)
    def run(n):
        text = (unit * (n // len(unit) + 1))[:n]
        t0 = time.perf_counter()
        H.through_hub(text, "Compare the earthquakes.", *H.GEO)
        return time.perf_counter() - t0
    small, large = run(25_000), run(100_000)
    assert large / max(small, 0.2) <= 8, (small, large)


def test_the_table_count_reader_is_linear():
    # (each match re-joined the whole sentence before checking for room: 0.56, 2.17 and 9.69 s at 50, 100 and 200 kB for the pack)
    table = "| Site | Distance (m) | Mean pedestrian count | EQS |\n|---|---|---|---|\n" + "".join(
        f"| {k} | {k * 50} | {200 - k} | {k % 20} |\n" for k in range(1, 61))
    docs = (("doc-sites", "Site survey", "Fieldwork team", table),)

    def run(n):
        unit = "the table shows ten sites the table shows "
        text = (unit * (n // len(unit) + 1))[:n]
        t0 = time.perf_counter()
        H.through_hub(text, "Describe the sites.", *H.GEO, docs=docs)
        return time.perf_counter() - t0
    small, large = run(25_000), run(100_000)
    assert large / max(small, 0.2) <= 8, (small, large)
