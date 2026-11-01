"""Integration gate 3: the translator's findings (translate/quantities.py and the class sweep in translate/).

* major, critical (input stall): ``quantities._FIGURE_AHEAD_RE`` had adjacent unbounded blank runs separated only by
  optional items, and ``_approximation_cues`` matched it after a postposed "approximately" with the whole rest of the text
  after it. A figure followed by "approximately" and a long blank run in a supplied text was quadratic through
  ``precision.read_sites`` on every source of a claim, so ``verify_claim`` stalled (137.9 s at 32,000 blanks, about six
  hours at the 400,000-character limit). Its runs are possessive now; it matches exactly what it matched.
* the class sweep (same kinds of pattern, translate): ``quantities._RATIO_RE`` ("per" and an optional hyphen between two
  blank runs after a figure) and ``grounding._BRACKETED_ELISION_RE`` (a leading blank run read again from every position of
  a long run) were quadratic; both read exactly what they read before.
"""
from __future__ import annotations

import random
import re
import time

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.translate import grounding as G
from epinoic_logic.translate import precision as PR
from epinoic_logic.translate import quantities as Q
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from ..timing import empty_caches

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def _cpu(call) -> float:
    empty_caches()
    c0 = time.process_time()
    call()
    return time.process_time() - c0


# ============================================================================================ critical: the finding's input
def _verify(blanks: int):
    """The finding's end-to-end input: a fixture translation x = 0.33 grounded in a supplied text 'x is 0.33
    approximately' followed by a blank run (the arena's translator path)."""
    text = "x is 0.33 approximately" + " " * blanks + "in this survey."
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Mathematics", task_type="algebra")
    claim = ClaimRecord(**ids, claim_id="c", claim_text="Given the stated value of x, x is less than 1/2.", claim_role="quantitative", proposed_claim_kind="arithmetic")
    report = SpecialistReport(**ids, original_response=claim.claim_text, response_sha256=sha256_text(claim.claim_text), claims=[claim],
                              supplied_texts=[SuppliedText(document_id="doc", text=text)], created_at="2026-11-01T00:00:00Z")
    problem = {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": [{"name": "x", "sort": "Real"}],
               "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "0.33"}}, "label": "x is 0.33",
                             "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "doc", "excerpt": "x is 0.33"}]}}],
               "conclusion": {"id": "C", "expr": {"op": "lt", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "1/2"}}, "label": "x is less than one half"}}
    out = {"problem": problem, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}
    return verify_claim(claim, report, Translator(FixtureTranslationProvider({"c": [out]}), config=CFG), None, config=CFG, signing_key=b"k" * 32, key_id="k")


def test_a_postposed_approximation_before_a_long_blank_run_is_verified_in_bounded_time_with_the_same_verdict():
    small = _verify(10)
    c0 = time.process_time()
    big = _verify(32_000)
    assert time.process_time() - c0 < 20.0  # 137.9 s before the fix
    assert big.translation.status.value == small.translation.status.value == "TRANSLATED"
    assert getattr(big.display_status, "value", big.display_status) == getattr(small.display_status, "value", small.display_status) == "ENTAILED"


@pytest.mark.parametrize("call", [
    lambda: Q._FIGURE_AHEAD_RE.match("30 approximately" + " " * 400_000 + "x", 16),
    lambda: [Q.stated_exactness(f, t) for t in ["The population was 30 approximately" + " " * 400_000 + "and it grew."]
             for f in Q.figures_in(Q.SourceText(kind="supplied_text", ident="s", text=t))],
    lambda: Q.figures_in(Q.SourceText(kind="supplied_text", ident="s", text="It rose by 5 per" + " " * 400_000 + "x.")),
    lambda: G.unbracket_elisions("a" + " " * 400_000 + "(x"),
], ids=["figure ahead", "figures and their exactness", "ratio unit", "bracketed elision"])
def test_the_quantity_and_quotation_readers_are_linear_on_long_blank_runs(call):
    assert _cpu(call) < 4.0  # quadratic before: 5.7 s at 8,000 blanks for the figure-ahead pattern, 0.22 s for the ratio unit


def test_read_sites_on_a_postposed_approximation_is_linear():
    from epinoic_logic.ir.schema import Problem
    problem = Problem.model_validate({
        "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "n", "sort": "Real", "meaning": "the number of states"}, {"name": "b", "sort": "Bool", "meaning": "the union grew"}],
        "premises": [{"id": "P1", "expr": {"op": "eq", "left": {"op": "var", "name": "n"}, "right": {"op": "real", "value": "17.5"}}},
                     {"id": "P2", "expr": {"op": "iff", "left": {"op": "var", "name": "b"},
                                           "right": {"op": "gt", "left": {"op": "var", "name": "n"}, "right": {"op": "real", "value": "13"}}}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}}})
    src = Q.SourceText(kind="supplied_text", ident="src", text="In 1850 there were 17.5 approximately" + " " * 200_000 + "x states.")
    assert _cpu(lambda: PR.read_sites(problem, [src])) < 6.0  # 6.1 s at 8,000 blanks before the fix


# ============================================================================================ the old patterns, as the specification
_OLD_FIGURE_AHEAD_RE = re.compile(r"\s*(?:(?:equal|equals|close)\s+to\s+|to\s+)?\(?\s*(?:US\$|A\$|C\$|NZ\$|HK\$|[$£€¥₹₩])?\s?[-−–+]?(?:\d|\.\d)")
_OLD_RATIO_RE = re.compile(
    r"\s*(?:(?P<pct>%|per\s*-?\s*cent\b|percent\b|pc\b(?=\s|$|[.,;)]))(?:\s*(?P<pp>points?\b))?|(?P<ppt>percentage\s+points?\b|pp\b|p\.p\.)"
    r"|(?P<pm>‰|per\s+mill?e?\b)|(?P<bp>basis\s+points?\b|bps?\b))", re.IGNORECASE)
_OLD_BRACKETED_ELISION_RE = re.compile(r"\s*[\[(]\s*(?:(?:\.\s*){3}|…)\s*[\])]\s*")


def test_the_rewritten_patterns_match_exactly_what_the_old_ones_matched():
    rng = random.Random(61)
    pieces = [" ", "  ", "\t", "\n", "to", "equal", "equals", "close", "(", ")", "$", "US$", "£", "-", "−", "+", "5", ".5", "x", "approximately", "per", "cent",
              "-cent", "percent", "pc", "points", "point", "percentage", "pp", "p.p.", "‰", "mille", "mil", "basis", "bps", "%", "[", "]", "...", ". . .", "…", ".", ","]
    for _ in range(40_000):
        t = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 9)))
        for i in range(len(t) + 1):
            for old, new in ((_OLD_FIGURE_AHEAD_RE, Q._FIGURE_AHEAD_RE), (_OLD_RATIO_RE, Q._RATIO_RE)):
                a, b = old.match(t, i), new.match(t, i)
                assert (a is None) == (b is None) and (a is None or (a.span(), a.groupdict()) == (b.span(), b.groupdict())), (repr(t), i)
        assert _OLD_BRACKETED_ELISION_RE.sub(" ... ", t) == G._BRACKETED_ELISION_RE.sub(" ... ", t), repr(t)
