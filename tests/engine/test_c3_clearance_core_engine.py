"""Argument diagnosis fixed by the core fixer of the round-10 clearance (integrated round c3; c2 bug 24 in new shapes): warning-level
hasty-generalisation and causal-leap defects were raised on valid links, one of them on a receipt (INT-ARG-001):

* ARG-HG-001 on a negated universal one instance establishes (hi-t16 h1.7, "did not settle every battle" from one defeat), on a
  link from a definition (ec-t16 g2.3, "a common pool resource is rivalrous ...", so "each user's catch reduces what is left for
  everyone else") and on a defining consequent (bm-t16 g1.2, "profit before interest and tax is taken as gross profit less
  expenses");
* ARG-CL-001 on a link that concludes a cause cannot be established (ec-t16 g11.5, "so natural variation cannot be excluded").

The encodings below are the round's recorded translations (symbols, meanings, premises and labels as recorded); the controls keep
a real hasty generalisation and a real causal leap named."""
from __future__ import annotations

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem

from ..core_hostile import SHAPES, one, sweep

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
GK, SI, ST = {"kind": "general_knowledge"}, {"kind": "specialist_inference"}, {"kind": "supplied_text"}


def V(n: str) -> dict:
    return {"op": "var", "name": n}


def AND(*a) -> dict:
    return {"op": "and", "args": list(a)}


def IMP(a, b) -> dict:
    return {"op": "implies", "left": a, "right": b}


def problem(symbols, premises, conclusion) -> Problem:
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": n, "sort": "Bool", "meaning": m, "grounding": g} for n, m, g in symbols],
                                   "premises": [{"id": i, "expr": e, "label": lab, "grounding": g} for i, e, lab, g in premises],
                                   "conclusion": {"id": "C", "expr": conclusion[0], "label": conclusion[1]}})


def named(p: Problem) -> set[str]:
    r = verify(p, CFG)
    return {d.code for d in (r.named_diagnostics or [])}


H1_7 = problem([("guad", "Italian formations were defeated at Guadalajara in March 1937", GK), ("soviet", "the Republic received Soviet aid from October 1936", GK),
                ("matched", "intervention was matched on the other side", SI), ("unsettled", "intervention did not settle every battle", SI)],
               [("p_a", AND(V("guad"), V("soviet")), "Guadalajara defeat and Soviet aid (the 'so' premise)", GK),
                ("l_so", IMP(AND(V("guad"), V("soviet")), AND(V("matched"), V("unsettled"))), "so intervention was matched and did not settle every battle", SI)],
               (AND(V("matched"), V("unsettled")), "intervention was matched on the other side and did not settle every battle"))
G2_3 = problem([("rivalrous", "a common pool resource is rivalrous and non-excludable, so one user's unit cannot be another's", GK),
                ("reduces", "each user's catch reduces what is left for everyone else", SI)],
               [("gk_rival", V("rivalrous"), "a common pool resource is rivalrous, so one unit taken cannot be taken by another", GK),
                ("link", IMP(V("rivalrous"), V("reduces")), "therefore each user's catch reduces what is left for others", SI)],
               (V("reduces"), "each user's catch therefore reduces what is left for everyone else"))
G1_2 = problem([("nointfig", "the case gives no interest figure", ST), ("expnoint", "the $1,104,000 of expenses contains no interest", SI),
                ("pbitdef", "profit before interest and tax is taken as gross profit less expenses", SI)],
               [("p_nointfig", V("nointfig"), "the case gives no interest figure", ST),
                ("link_a", IMP(V("nointfig"), V("expnoint")), "no interest figure in the case, so expenses contain no interest", SI),
                ("link_b", IMP(V("expnoint"), V("pbitdef")), "expenses with no interest, so profit before interest and tax is gross profit less expenses", SI)],
               (AND(V("expnoint"), V("pbitdef")), "the $1,104,000 of expenses contains no interest, so profit before interest and tax is taken as gross profit less expenses"))
G11_5 = problem([("few_points", "the table holds only three data points", ST), ("pre_quota", "one of the data points (2019) is before the quotas", ST),
                 ("cannot_exclude", "natural variation cannot be excluded as the cause of the change", SI)],
                [("few", V("few_points"), "there are only three data points", ST), ("pre", V("pre_quota"), "one data point is before the 2021 quotas", ST),
                 ("link", IMP(AND(V("few_points"), V("pre_quota")), V("cannot_exclude")), "so natural variation cannot be excluded", SI)],
                (V("cannot_exclude"), "there are only three data points, one of them before the quotas, so natural variation cannot be excluded"))


@pytest.mark.parametrize("name,p,code", [("hi-t16 h1.7", H1_7, "ARG-HG-001"), ("ec-t16 g2.3", G2_3, "ARG-HG-001"), ("bm-t16 g1.2", G1_2, "ARG-HG-001"),
                                         ("ec-t16 g11.5", G11_5, "ARG-CL-001")])
def test_the_c3_valid_links_draw_no_hasty_generalisation_or_causal_leap(name, p, code):
    assert code not in named(p), name


def test_controls_a_real_hasty_generalisation_and_a_real_causal_leap_are_still_named():
    hasty = problem([("one_failed", "the one student we asked in 2023 failed the test", ST), ("all_fail", "every student fails the test", SI)],
                    [("f", V("one_failed"), "the one student we asked in 2023 failed the test", ST),
                     ("l", IMP(V("one_failed"), V("all_fail")), "so every student fails the test", SI)],
                    (V("all_fail"), "every student fails the test"))
    assert "ARG-HG-001" in named(hasty)
    leap = problem([("advert_may", "the advert ran in May 2024", ST), ("sales_june", "sales rose in June 2024", ST),
                    ("caused", "the advert caused the rise in sales", SI)],
                   [("a", V("advert_may"), "the advert ran in May 2024", ST), ("s", V("sales_june"), "sales rose in June 2024", ST),
                    ("l", IMP(AND(V("advert_may"), V("sales_june")), V("caused")), "so the advert caused the rise in sales", SI)],
                   (V("caused"), "the advert caused the rise in sales"))
    assert "ARG-CL-001" in named(leap)


# ------------------------------------------------------------------ the readers of this pass are linear

def _entries(text: str):
    from epinoic_logic.engine import argument as A
    yield "_NEGATED_UNIVERSAL_RE", lambda: A._NEGATED_UNIVERSAL_RE.search(text)
    yield "_DEFINING_RE", lambda: A._DEFINING_RE.search(text)
    yield "_GENERIC_KIND_RE", lambda: A._GENERIC_KIND_RE.match(text)
    yield "_CAUSE_WITHHELD_RE", lambda: A._CAUSE_WITHHELD_RE.search(text)
    meaning = ("x " + text)[:1000]
    p = problem([("a", meaning, ST), ("b", meaning, SI)], [("f", V("a"), meaning, ST), ("l", IMP(V("a"), V("b")), meaning, SI)], (V("b"), meaning))
    yield "verify (argument diagnosis)", lambda: verify(p, CFG)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c3_argument_readers(shape):
    """The patterns this pass added to the argument diagnosis, and the diagnosis on meanings of the standard hostile inputs."""
    assert not sweep(_entries, texts=one(shape))
