"""Accuracy round 1: every reading the round adds or changes is linear in its input (two sizes, a ratio of CPU times, never a
wall-clock bound; ``tests/growth.py``). A linear reader costs about four times as much on an input four times as long, a
quadratic one about sixteen times; each bound below leaves room for noise and none for a quadratic reader.

* ``diag_argument.offers_cause`` (DIFF3-01, the cause phrases of a one-sentence explanation): prefix counts of content
  words and the next clause end, one pass;
* ``grounding.direction_verbs`` (DIFF3-03, the phrasal verbs of a change): a particle read at most four tokens after its
  verb;
* ``stated_rules._generic_statement`` and the rule qualifier's conjunct, relative-clause, parallel-complement and
  affirming-frame readings (DIFF3-07, DV2-03), through :func:`stated_rules.stated_rule` on one long sentence;
* ``diag_evidence._stance_clauses`` (DIFF3-05): the clause start read back at most as far as the stance window;
* ``diag_evidence._task_restatements`` and ``_restatement_roots`` (DIFF3-04), and the cue of a request that invites own
  knowledge (DIFF3-06);

Accuracy round 2 reverted the two readings of round 1 that still misfired (DIFF3-05's clause reading, DIFF3-04's
restatement reading; docs/ARGUMENT_DIAGNOSTICS.md, section 18): ``_stance_clauses``, ``_task_restatements`` and
``_restatement_roots`` no longer exist. Their two tests below are rewritten to measure, on the same inputs, the readers that
replace them (``diag_evidence._stance_index`` and ``_stances``; ``diag_evidence._task_statements``,
``grounding._held_change_roots`` and ``grounding._unread_particles``), each with an input of distinct words added (a stance
document of distinct words was quadratic in round 1, V1-STANCE-QUADRATIC), so each is stricter than before;
* ``diag_argument.unbridged_leap_reading`` with its quotation and reason-clause bridges (DIFF3-02).

Nothing from an input is executed."""
from __future__ import annotations

from epinoic_logic import lexis
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import diag_argument as DA
from epinoic_logic.translate import diag_evidence as DE
from epinoic_logic.translate import grounding as G
from epinoic_logic.translate.quantities import SourceText
from epinoic_logic.translate.stated_rules import _generic_statement, stated_rule

from ..growth import growth

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
#: the token cache of short texts is emptied before every timed call, so neither size is served from it
CLEAR = lexis._cached_token_spans.cache_clear


def test_the_cause_phrase_reading_is_linear():
    for unit in ("by ", "because of the ", "due to a ", "as a result of "):
        ratio, small, large = growth(DA.offers_cause, "Prices rose " + unit * 300 + "drought.", "Prices rose " + unit * 1200 + "drought.", clear=CLEAR)
        assert ratio < LINEAR, (unit, ratio, small, large)
    assert DA.offers_cause("The price of cocoa rose in 2024 because of a fungal disease that destroyed much of the crop.")
    assert not DA.offers_cause("The price of cocoa rose in 2024 and this was bad for consumers.")


def test_the_phrasal_verb_reading_is_linear():
    def tokens(n: int) -> list[str]:
        return (["the", "bank", "brought", "its", "rates", "down", "and", "then"] * n)[: 8 * n]
    ratio, small, large = growth(G.direction_verbs, tokens(400), tokens(1600))
    assert ratio < LINEAR, (ratio, small, large)
    assert G.direction_verbs(["the", "bank", "brought", "interest", "rates", "down"]) == (set(), {"brought down"})


def test_the_generic_statement_reading_is_linear():
    ratio, small, large = growth(_generic_statement, ["demand", "rises", "and", "the", "price", "is", "raised"] * 300,
                                 ["demand", "rises", "and", "the", "price", "is", "raised"] * 1200)
    assert ratio < LINEAR, (ratio, small, large)
    assert _generic_statement(["when", "demand", "rises", "the", "price", "rises"])
    assert not _generic_statement(["when", "the", "war", "ended", "unemployment", "rose"])


def _rule_problem() -> tuple:
    problem = Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "a", "sort": "Bool", "meaning": "fuel duty rises"}, {"name": "b", "sort": "Bool", "meaning": "car journeys fall"}],
        "premises": [{"id": "q1", "expr": {"op": "implies", "left": {"op": "var", "name": "a"}, "right": {"op": "var", "name": "b"}}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}}})
    return problem.premises[0].expr, {s.name: s for s in problem.symbols}


def test_the_rule_qualifier_readings_are_linear():
    expr, syms = _rule_problem()

    def read(text: str):
        src = SourceText("supplied_text", "ext", text)
        return stated_rule(expr, syms, src, (0, len(text) - 1))

    for tail in (" or to the towns", " and drivers may switch to buses", " which can vary", ", and nobody doubts that it holds"):
        small = "When fuel duty rises, car journeys fall" + tail * 60 + "."
        large = "When fuel duty rises, car journeys fall" + tail * 240 + "."
        ratio, t_small, t_large = growth(read, small, large, clear=CLEAR)
        assert ratio < LINEAR, (tail, ratio, t_small, t_large)
    rule = read("When fuel duty rises, car journeys fall and bus companies can add more services.")
    assert rule is not None and rule.qualifier is None


def test_the_stance_clause_reading_is_linear():
    """Rewritten in accuracy round 2: the clause reading it measured (``_stance_clauses``) was reverted (V1I-01); the same
    units now measure the index that replaces it and the stance words, with a document of distinct words added."""
    def distinct(n: int) -> str:
        return " ".join(f"condemned q{k}x" for k in range(n))
    for make in ((lambda n: "welcomed " * n), (lambda n: "the treaty was welcomed, " * n), (lambda n: "not condemned and " * n), distinct):
        for reader in (DE._stance_index, DE._stances):
            ratio, small, large = growth(reader, make(400), make(1600), clear=CLEAR)
            assert ratio < LINEAR, (reader.__name__, make(2)[:30], ratio, small, large)
    index = DE._stance_index("The mayor welcomed the end of the consultation, but residents condemned the bypass.")
    assert index["mayor"] == (False, True) and index["bypass"] == (True, False)  # each clause carries its own stance


def test_the_restatement_readings_are_linear():
    """Rewritten in accuracy round 2: the restatement reading it measured (``_task_restatements``, ``_restatement_roots``) was
    reverted (V1I-02, V1-RESTATE-SUSPENDED); the same inputs now measure the readers that replace it."""
    task = "In Country S the government raised the minimum wage. "
    def statements(text: str):
        DE._task_statements.cache_clear()
        return DE._task_statements(text)
    ratio, small, large = growth(statements, task * 100, task * 400, clear=CLEAR)
    assert ratio < LINEAR, (ratio, small, large)
    for unit in ("the following week ", "washed away ", "brought the rates down "):
        clauses = G.change_clauses("Prices went up while costs fell, and the firm drove its costs down.")
        for reader in (lambda t: G._held_change_roots(t, clauses, {"firm", "cost", "price"}), lambda t: G._unread_particles(lexis.tokens(t))):
            ratio, small, large = growth(reader, unit * 400, unit * 1600, clear=CLEAR)
            assert ratio < LINEAR, (unit, ratio, small, large)
    ratio, small, large = growth(DE.asks_own_knowledge, "Using the source and " * 300 + "your own knowledge, explain.",
                                 "Using the source and " * 1200 + "your own knowledge, explain.", clear=CLEAR)
    assert ratio < LINEAR, (ratio, small, large)


def test_the_bridge_readings_are_linear():
    a, b = "Parliament repealed the Corn Laws in 1846", "bread became cheaper in Britain"
    for unit in ("Historian M writes that \"the repeal of the Corn Laws mattered\". ", "The repeal of the Corn Laws lowered rents, so landlords lost. "):
        def read(text: str, a=a, b=b):
            DA._quotations.cache_clear()
            return DA.unbridged_leap_reading([text], a, b)
        ratio, small, large = growth(read, unit * 40 + "Parliament repealed the Corn Laws in 1846, so bread became cheaper in Britain.",
                                     unit * 160 + "Parliament repealed the Corn Laws in 1846, so bread became cheaper in Britain.", clear=CLEAR)
        assert ratio < LINEAR, (unit[:20], ratio, small, large)
    assert DA.unbridged_leap_reading(["Parliament repealed the Corn Laws in 1846. The repeal of the Corn Laws lowered the price of bread in Britain, "
                                      "so bread became cheaper in Britain."], a, b) is None
    assert DA.unbridged_leap_reading(["Parliament repealed the Corn Laws in 1846, so bread became cheaper in Britain."], a, b) is not None
