"""Repair round 3, grounding: each check reads what a record states, and no fix weakens a refutation the check made before.

* INV-1, INV-3: a figureless task-authority premise citing no excerpt is validated only by a sentence the task states as a
  given, holding the premise's words in their order with their polarity. A sentence that uses the premise's words in
  another order ("The Allies caused the war to end and made Germany pay" for "Germany caused the war"), a question and a
  report of a view the answer is to weigh state nothing as a given: the premise is refuted (``verified=False``), as before
  repair round 2. A compound premise ("if ... then") the task authority claims, which no record states as a rule, is
  refuted too. A paraphrase of a task fact whose words the records hold only in other sentences stays unrefuted.
* INV-2: a rule a question asks about, or a supposition sets up, is no task given.
* INV-5: a quoted conjunction is stated only when each conjunct is stated with its own polarity ("Ash never lost
  population, though birch lost population" states no "ash lost population").
* V3-FALSE-SRCMISMATCH-COMPARED: a figure after "compared with" belongs to the clause's own subject, so an exact quotation
  of it grounds the premise.
* V3-FALSE-SRCMISMATCH-THRESHOLD: a target stated as a bound ("keep ... below 10%") states the figure of a symbol whose
  meaning names the bound (a ceiling, a limit, a target), and of no other symbol.
* rerun-fidelity-1 variant: an excerpt states its figure for its own quantity and entity: imports for imports, never for
  exports; Hightown's residents, never Lowtown's.
* ADV3-08: an exact quotation of a list joined by "and" states each member, so a point drawn from it is no circular
  restatement."""
from __future__ import annotations

from typing import Optional

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText, TaskRecord
from epinoic_logic.translate.grounding import check_problem_grounding


def V(name: str) -> dict:
    return {"op": "var", "name": name}


def _problem(symbols: list[tuple[str, str, str]], premises: list[dict], conclusion: dict) -> Problem:
    return Problem.model_validate({"ir_version": "1.0", "problem_id": "p", "request_id": "req-g", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": n, "sort": s, "meaning": m} for n, s, m in symbols],
                                   "premises": premises, "conclusion": {"id": "C", "expr": conclusion, "label": "the point"}})


def _verified(problem: Problem, docs=(), task: Optional[str] = None, target: str = "P1") -> Optional[bool]:
    g, _checks = check_problem_grounding(problem, list(docs), task=TaskRecord.of("t1", "req-g", task) if task is not None else None)
    return next(p.grounding.verified for p in g.premises if p.id == target)


def _task_fact(meaning: str, label: Optional[str] = None, kind: str = "task_setting") -> Problem:
    return _problem([("a", "Bool", meaning), ("b", "Bool", "the treaty was unjust")],
                    [{"id": "P1", "expr": V("a"), "label": label or meaning, "grounding": {"kind": kind}},
                     {"id": "L", "expr": {"op": "implies", "left": V("a"), "right": V("b")}, "label": "so", "grounding": {"kind": "assumption"}}],
                    V("b"))


# ------------------------------------------------------------------ INV-1, INV-3: task facts

@pytest.mark.parametrize("task, meaning", [
    ("The Allies caused the war to end and made Germany pay reparations. Evaluate the treaty.", "Germany caused the war"),
    ("The treaty forced Germany to pay. Explain.", "Germany forced the treaty"),
    ("Germany did not lose any territory in the east. Discuss the treaty.", "Germany lost territory in the east"),
    ("Many students claim the treaty was harsh. Evaluate this.", "the treaty was harsh"),
    ("It is often said that the treaty was harsh. Evaluate this.", "the treaty was harsh"),
    ("Critics described the treaty as harsh. Evaluate this view.", "the treaty was harsh"),
    ("Was the treaty harsh on Germany? Explain your answer.", "the treaty was harsh on Germany"),
])
def test_a_task_premise_the_task_does_not_state_as_a_given_is_refuted(task, meaning):
    assert _verified(_task_fact(meaning), task=task) is False


def test_control_a_task_fact_the_task_states_is_validated():
    assert _verified(_task_fact("Germany lost the war in 1918"), task="Germany lost the war in 1918. Explain the treaty.") is True


def test_control_a_paraphrase_whose_meaning_the_task_states_is_not_refuted():
    premise = _task_fact("incomes rose and mortgage rates fell", label="incomes up and mortgages cheaper")
    assert _verified(premise, task="Incomes rose by 8% and mortgage rates fell in 2023. Explain the rise in house prices.") is not False


def test_a_rule_the_task_authority_claims_and_no_record_states_is_refuted():
    link = _problem([("navy", "Bool", "Britain had the largest navy in 1914"), ("win", "Bool", "Britain was certain to win the war")],
                    [{"id": "F", "expr": V("navy"), "label": "Britain had the largest navy in 1914", "grounding": {"kind": "task_setting"}},
                     {"id": "P1", "expr": {"op": "implies", "left": V("navy"), "right": V("win")}, "label": "so", "grounding": {"kind": "task_setting"}}],
                    V("win"))
    assert _verified(link, task="Britain had the largest navy in 1914. Was Britain certain to win the war? Explain your answer.") is False


# ------------------------------------------------------------------ INV-2: a rule in a question or a supposition

def _rule() -> Problem:
    return _problem([("mean", "Real", "the mean reaction time (s)"), ("ok", "Bool", "the athlete qualifies")],
                    [{"id": "P1", "expr": {"op": "implies", "left": {"op": "lt", "left": V("mean"), "right": {"op": "real", "value": "0.25"}},
                                           "right": V("ok")}, "label": "rule", "grounding": {"kind": "rubric_rule"}},
                     {"id": "M", "expr": {"op": "eq", "left": V("mean"), "right": {"op": "real", "value": "0.2"}}, "grounding": {"kind": "assumption"}}],
                    V("ok"))


@pytest.mark.parametrize("task", ["Does the athlete qualify if the mean is below 0.25 s?",
                                  "Suppose the athlete qualifies if the mean is below 0.25 s. Is this fair?"])
def test_a_rule_a_question_asks_about_or_a_supposition_sets_is_no_given(task):
    assert _verified(_rule(), task=task) is not True


def test_control_a_rule_the_task_states_is_validated():
    assert _verified(_rule(), task="The athlete qualifies if the mean is below 0.25 s.") is True


# ------------------------------------------------------------------ INV-5: a quoted conjunction, conjunct by conjunct

def _conjunction(excerpt: str) -> Problem:
    both = {"op": "and", "args": [V("a"), V("b")]}
    return _problem([("a", "Bool", "oak lost leaves early"), ("b", "Bool", "beech lost leaves early"), ("z", "Bool", "the wood was stressed")],
                    [{"id": "P1", "expr": both, "label": "oak and beech lost leaves early",
                      "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc", "excerpt": excerpt}]}},
                     {"id": "L", "expr": {"op": "implies", "left": both, "right": V("z")}, "grounding": {"kind": "assumption"}}],
                    V("z"))


@pytest.mark.parametrize("text", ["Oak never lost leaves early, though beech lost leaves early.", "Oak did not lose leaves early; beech lost leaves early."])
def test_a_quotation_that_negates_a_conjunct_does_not_state_the_conjunction(text):
    assert _verified(_conjunction(text.rstrip(".")), [SuppliedText(document_id="doc", text=text)]) is not True


def test_control_a_quotation_that_states_each_conjunct_states_the_conjunction():
    text = "Oak lost leaves early, and beech lost leaves early too."
    assert _verified(_conjunction(text.rstrip(".")), [SuppliedText(document_id="doc", text=text)]) is True


# ------------------------------------------------------------------ COMPARED, THRESHOLD, fidelity-1: whose figure

def _assignment(meaning: str, value: str, excerpt: str, sort: str = "Int", label: Optional[str] = None) -> Problem:
    literal = {"op": "int" if sort == "Int" else "real", "value": value}
    return _problem([("x", sort, meaning), ("y", sort, "the other figure")],
                    [{"id": "P1", "expr": {"op": "eq", "left": V("x"), "right": literal}, "label": label or meaning,
                      "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc", "excerpt": excerpt}]}}],
                    {"op": "gt", "left": V("y"), "right": V("x")})


SQUAD = "Extract: In May the team changed its training plan. It won 7 of its next 12 games, compared with 3 of the 12 games before the change."


def test_a_figure_after_compared_with_belongs_to_its_own_clause():
    p = _assignment("games won in the 12 before the change", "3", "compared with 3 of the 12 games before the change")
    assert _verified(p, [SuppliedText(document_id="doc", text=SQUAD)]) is True


TARGET = "Extract: The council aims to keep household waste below 400 kg per person. In 2023 household waste was 380 kg per person."


def test_control_a_bound_states_no_figure_of_a_quantity_it_bounds():
    p = _assignment("household waste per person (kg)", "400", "below 400 kg per person", sort="Real")
    assert _verified(p, [SuppliedText(document_id="doc", text=TARGET)]) is not True


TRADE = "In 2015 Ostland's imports were 40 million dollars. In 2015 Ostland's exports were 25 million dollars."


# ------------------------------------------------------------------ ADV3-08: an exact quotation of a list

def test_an_exact_quotation_of_a_list_states_each_member():
    members = {"op": "and", "args": [V("it"), V("es"), V("pt")]}
    p = _problem([("it", "Bool", "Italy had a strike in 1920"), ("es", "Bool", "Spain had a strike in 1920"), ("pt", "Bool", "Portugal had a strike in 1920")],
                 [{"id": "P1", "expr": members, "label": "strikes broke out in Italy, in Spain and in Portugal",
                   "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc", "excerpt": "strikes broke out in Italy, in Spain and in Portugal"}]}}],
                 members)
    assert _verified(p, [SuppliedText(document_id="doc", text="Source F: In 1920 strikes broke out in Italy, in Spain and in Portugal.")]) is True


def test_control_a_list_that_leaves_a_member_out_does_not_state_it():
    members = {"op": "and", "args": [V("it"), V("es"), V("pt")]}
    p = _problem([("it", "Bool", "Italy had a strike in 1920"), ("es", "Bool", "Spain had a strike in 1920"), ("pt", "Bool", "Portugal had a strike in 1920")],
                 [{"id": "P1", "expr": members, "label": "strikes broke out in Italy and in Spain",
                   "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc", "excerpt": "strikes broke out in Italy and in Spain"}]}}],
                 members)
    assert _verified(p, [SuppliedText(document_id="doc", text="Source F: In 1920 strikes broke out in Italy and in Spain.")]) is not True
