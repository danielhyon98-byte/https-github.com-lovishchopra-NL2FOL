"""Repair round 4, grounding: what a record states, read for the classes the review found refused or unchecked on correct
answers, with every earlier refutation kept.

* FA-TASK-EITHER-OR-REFUTED: an "or" the task states is a rule it states. A disjunction of literals is validated by an
  asserted task sentence holding "or" between each option's words; an exclusive one needs a word of exclusion too, and
  without one it is left unvalidated, never refuted. An "or" no task sentence states, or one the task negates, is refuted
  as before.
* ADV4-06: a task sentence restated with its pronoun resolved, in the passive, or with its agent after "by" states the
  premise; a restatement that gives the act to another agent stays refuted, and one with another verb is not validated.
* E2E-BI, E2E-CS: the count, the total and the mean of a list a record states give a figure, in every list form (with
  semicolons, with commas, and with "and" before the last item); a count read off a quoted list grounds the length of the
  list. A figure no list gives stays refuted.
* E2E-MAA: a unit conversion the task gives inside an instruction ("(take 1 month = 30 days)") validates the premise that
  applies it; another factor does not.
* E2E-HI-MENTION: a task-authority premise whose excerpt stands only in a relayed specialist's report is unvalidated (the
  report confers no authority), not refuted.
* rerun-fidelity-1, same sentence: one sentence, or one table line, that states two quantities gives each its own figure:
  a premise giving one the other's figure is refused; each quantity's own figure grounds."""
from __future__ import annotations

from typing import Optional

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText, TaskRecord
from epinoic_logic.translate.grounding import check_problem_grounding


def V(name: str) -> dict:
    return {"op": "var", "name": name}


def N(value, sort: str = "Int") -> dict:
    return {"op": "int" if sort == "Int" else "real", "value": str(value)}


def _problem(symbols, premises, conclusion) -> Problem:
    return Problem.model_validate({"ir_version": "1.0", "problem_id": "p", "request_id": "req-g", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": n, "sort": s, "meaning": m} for n, s, m in symbols],
                                   "premises": premises, "conclusion": {"id": "C", "expr": conclusion, "label": "the point"}})


def _verified(problem: Problem, docs=(), task: Optional[str] = None, target: str = "P1") -> Optional[bool]:
    g, _checks = check_problem_grounding(problem, list(docs), task=TaskRecord.of("t1", "req-g", task) if task is not None else None)
    return next(p.grounding.verified for p in g.premises if p.id == target)


def _with_link(symbols, premise: dict, antecedent: dict, point: str = "pt") -> Problem:
    return _problem([*symbols, (point, "Bool", "the point the answer draws")],
                    [premise, {"id": "L", "expr": {"op": "implies", "left": antecedent, "right": V(point)}, "label": "so", "grounding": {"kind": "assumption"}}],
                    V(point))


# ------------------------------------------------------------------ FA-TASK-EITHER-OR-REFUTED

GROUPS = [("caff", "Bool", "participant 7 was in the caffeine group"), ("plac", "Bool", "participant 7 was in the placebo group")]
EITHER = {"op": "or", "args": [V("caff"), V("plac")]}
ONE_OF = {"op": "and", "args": [EITHER, {"op": "not", "arg": {"op": "and", "args": [V("caff"), V("plac")]}}]}


def _either(expr: dict) -> Problem:
    return _with_link(GROUPS, {"id": "P1", "expr": expr, "label": "participant 7 was in the caffeine group or the placebo group",
                               "grounding": {"kind": "task_setting"}}, V("plac"))


@pytest.mark.parametrize("task", [
    "Each participant was placed in one of two groups, the caffeine group or the placebo group. Evaluate the design.",
    "Participant 7 was in either the caffeine group or the placebo group. Evaluate the design.",
])
def test_an_either_or_the_task_states_validates_the_premise(task):
    assert _verified(_either(EITHER), task=task) is True


def test_an_exclusive_either_or_needs_a_word_of_exclusion_and_without_one_is_left_unvalidated():
    assert _verified(_either(ONE_OF), task="Participant 7 was in either the caffeine group or the placebo group, but not both. Evaluate.") is True
    assert _verified(_either(ONE_OF), task="Participant 7 was in either the caffeine group or the placebo group. Evaluate the design.") is None


@pytest.mark.parametrize("task", [
    "The study had a caffeine group. Evaluate the design.",
    "Participant 7 was in neither the caffeine group nor the placebo group. Evaluate the design.",
])
def test_control_an_either_or_the_task_does_not_state_or_negates_is_still_refuted(task):
    assert _verified(_either(EITHER), task=task) is False


# ------------------------------------------------------------------ ADV4-06: a task fact in other words

RATES = "Ruritania is in recession and its central bank has lowered interest rates to 1.5%. Explain one effect on consumer spending."


def _fact(meaning: str) -> Problem:
    return _with_link([("a", "Bool", meaning)], {"id": "P1", "expr": V("a"), "label": meaning, "grounding": {"kind": "task_setting"}}, V("a"))


@pytest.mark.parametrize("meaning", [
    "the central bank of Ruritania has lowered interest rates to 1.5%",
    "interest rates in Ruritania were lowered to 1.5%",
    "interest rates were lowered to 1.5% by the central bank of Ruritania",
])
def test_a_task_fact_with_its_pronoun_resolved_or_in_the_passive_is_validated(meaning):
    assert _verified(_fact(meaning), task=RATES) is True


def test_control_the_act_given_to_another_agent_is_refuted_and_another_verb_is_not_validated():
    assert _verified(_fact("Ruritania has lowered the central bank's interest rates to 1.5%"), task=RATES) is False
    assert _verified(_fact("the central bank of Ruritania has raised interest rates to 1.5%"), task=RATES) is not True


# ------------------------------------------------------------------ E2E-BI, E2E-CS: figures a stated list gives

def _figure(meaning: str, value, kind: str, docs_ref: Optional[dict] = None) -> Problem:
    grounding = {"kind": kind, **({"source_refs": [docs_ref]} if docs_ref else {})}
    return _with_link([("k", "Int", meaning)], {"id": "P1", "expr": {"op": "eq", "left": V("k"), "right": N(value)}, "label": f"{meaning} is {value}",
                                               "grounding": grounding}, {"op": "gt", "left": V("k"), "right": N(0)})


CROSS = ["The seeds were: round yellow 315; round green 108; wrinkled yellow 101; wrinkled green 32. Carry out a chi-squared test.",
         "The seeds were 315 round yellow, 108 round green, 101 wrinkled yellow and 32 wrinkled green. Carry out a chi-squared test.",
         "The seeds were 315 round yellow, 108 round green, 101 wrinkled yellow, and 32 wrinkled green. Carry out a chi-squared test."]


@pytest.mark.parametrize("task", CROSS, ids=["semicolons", "and before the last", "serial comma"])
@pytest.mark.parametrize("meaning, value", [("the number of seed phenotypes", 5), ("the total number of seeds", 600)])
def test_control_a_figure_no_list_gives_is_still_refuted(task, meaning, value):
    assert _verified(_figure(meaning, value, "task_setting"), task=task) is False


LISTING = SuppliedText(document_id="code", title="Listing 2", text="marks = [4, 9, 15, 16, 23, 42, 50]\nprint(search(marks, 23))")
LIST_REF = {"document_id": "code", "excerpt": "marks = [4, 9, 15, 16, 23, 42, 50]"}


def test_control_a_length_the_quoted_list_does_not_have_is_refused():
    assert _verified(_figure("the number of items in the list marks", 8, "supplied_text", LIST_REF), docs=[LISTING], task="Trace search(marks, 23).") is False


# ------------------------------------------------------------------ E2E-MAA: a conversion given in an instruction

def _conversion(factor: int) -> Problem:
    symbols = [("days", "Real", "the half-life in days"), ("w", "Real", "the half-life in weeks")]
    premise = {"id": "P1", "expr": {"op": "eq", "left": V("days"), "right": {"op": "mul", "args": [N(factor, "Real"), V("w")]}},
               "label": f"1 week = {factor} days, so days = {factor} x weeks", "grounding": {"kind": "task_setting"}}
    return _with_link(symbols, premise, {"op": "gt", "left": V("days"), "right": N(0, "Real")})


TASK_WEEKS = "(b) Find the half-life of the drug in days (take 1 week = 7 days)."


def test_control_another_factor_is_refused():
    assert _verified(_conversion(5), task=TASK_WEEKS) is False


# ------------------------------------------------------------------ E2E-HI-MENTION: words located only in a peer's report

PEER = SuppliedText(document_id="peer:physics", title="Physics report", author="physics-specialist",
                    text="The half-life is 6 hours, from the decay curve.")


def _peer_premise(document_id: str) -> Problem:
    return _with_link([("h", "Bool", "the half-life is 6 hours")],
                      {"id": "P1", "expr": V("h"), "label": "the half-life is 6 hours",
                       "grounding": {"kind": "task_setting", "source_refs": [{"document_id": document_id, "excerpt": "The half-life is 6 hours"}]}}, V("h"))


def test_control_a_peer_report_never_validates_a_task_premise():
    assert _verified(_peer_premise("peer:physics"), docs=[PEER], task="Explain what the half-life means for the dose.") is not True


# ------------------------------------------------------------------ rerun-fidelity-1: two quantities in one sentence

MACRO = SuppliedText(document_id="macro", title="Macro data", text="In 2023 Ruritania's interest rate was 5 per cent and its inflation rate was 9 per cent.")
RAIN = SuppliedText(document_id="rain", title="Rainfall", text="Rainfall (mm): March 70; April 48.")


def _quoted_figure(meaning: str, value: int, doc: SuppliedText, excerpt: str) -> Problem:
    return _with_link([("x", "Int", meaning)], {"id": "P1", "expr": {"op": "eq", "left": V("x"), "right": N(value)}, "label": f"{meaning} was {value}",
                                               "grounding": {"kind": "quotation", "source_refs": [{"document_id": doc.document_id, "excerpt": excerpt}]}},
                      {"op": "gt", "left": V("x"), "right": N(0)})


SENTENCE = "In 2023 Ruritania's interest rate was 5 per cent and its inflation rate was 9 per cent"


@pytest.mark.parametrize("meaning, value, doc, excerpt", [
    ("Ruritania's interest rate in 2023 (per cent)", 5, MACRO, SENTENCE),
    ("Ruritania's inflation rate in 2023 (per cent)", 9, MACRO, SENTENCE),
    ("rainfall in April (mm)", 48, RAIN, "Rainfall (mm): March 70; April 48"),
    ("rainfall in March (mm)", 70, RAIN, "Rainfall (mm): March 70; April 48"),
])
def test_control_each_quantitys_own_figure_grounds(meaning, value, doc, excerpt):
    assert _verified(_quoted_figure(meaning, value, doc, excerpt), docs=[doc]) is True


# ------------------------------------------------------------------ ADV4-09: the answer's working is read once per text

