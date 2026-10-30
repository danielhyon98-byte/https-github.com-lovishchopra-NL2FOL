"""The grounding repairs of repair round 1 (each with its positive test and its clean control):

* a conditional rule quoted from the supplied text grounds the premise that states it (A-FA-QUOTERULE), never its converse
  or another threshold;
* a conjunction of facts one located excerpt states is verified as content of that excerpt (ADV-09), and one with a fact
  the excerpt does not state is not;
* a quotation premise whose excerpt does not state it is refused (``content_in_excerpt`` False: ADV-01, the point dressed
  as a quotation), while an excerpt that states it verifies it;
* an excerpt about another entity or another quantity does not ground a premise (fidelity-1 variant);
* a task-setting proposition the task does not state is refuted again (weakened-task-setting-refutation), and one it
  states is not;
* a dated change ("fell from 42% in 2014 to 18% in 2024") states each figure, while a range ("between 15% and 18%")
  states no single value (A-FA-RANGE);
* the divisor of a mean is no figure the excerpts must state, while an addend they do not state is (A-FA-POOLED), and a
  figure the answer's own written calculation derived grounds, while one nothing derived does not.

Ported onto the integrated translator without the tests that pin the feature line's own versions of grounding behaviours
the integrated translator decides otherwise (the ADV-01 restated-point refusal: a verified quotation identical to the
point is a transcription there) or makes its own way (figure subjects, dated changes, means, answer-derived figures, the
converse of a quoted rule); docs/ARGUMENT_DIAGNOSTICS.md, section 20, lists each."""
from __future__ import annotations

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText, TaskRecord
from epinoic_logic.translate.grounding import check_problem_grounding


def V(name: str) -> dict:
    return {"op": "var", "name": name}


def R(value: str) -> dict:
    return {"op": "real", "value": value}


def _quote(doc: str, excerpt: str) -> dict:
    return {"kind": "quotation", "source_refs": [{"document_id": doc, "excerpt": excerpt}], "certainty": "established"}


def _arith(refs: list[dict]) -> dict:
    return {"kind": "arithmetic_fact", "source_refs": refs, "certainty": "established"}


def _ground(premises: list[dict], symbols: list[dict], conclusion: dict, docs, *, task=None, answer_texts=()):
    problem = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": symbols,
                                      "premises": premises, "conclusion": {"id": "C", "expr": conclusion}})
    # ported: this tree's grounding checks take no answer texts (the answer's own working is read by the diagnosis only)
    extra = {"answer_texts": list(answer_texts)} if answer_texts else {}
    grounded, checks = check_problem_grounding(problem, list(docs), task=task, **extra)
    return {p.id: p.grounding.verified for p in grounded.premises}, checks


def _methods(checks, target: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for c in checks:
        if c.target_id == target:
            out.setdefault(c.method, []).append(c.verified)
    return out


# ------------------------------------------------------------------------------------------- a quoted conditional rule

MEMO = SuppliedText(document_id="memo", title="Board memo", author=None,
                    text="The board met in March. If our domestic sales grow by more than 5% in 2024, we will expand into Spain. In 2024 its domestic sales grew by 8%.")
RULE_EXCERPT = "If our domestic sales grow by more than 5% in 2024, we will expand into Spain"
RULE_SYMBOLS = [{"name": "g24", "sort": "Real", "meaning": "growth of the firm's domestic sales in 2024 (%)"},
                {"name": "spain", "sort": "Bool", "meaning": "the firm expands into Spain"}]


def _rule(expr: dict):
    return _ground([{"id": "P_rule", "expr": expr, "label": "the board's rule", "grounding": _quote("memo", RULE_EXCERPT)}], RULE_SYMBOLS, V("spain"), [MEMO])


def test_a_quoted_conditional_rule_grounds_the_premise_that_states_it():
    verified, checks = _rule({"op": "implies", "left": {"op": "gt", "left": V("g24"), "right": R("5")}, "right": V("spain")})
    assert verified == {"P_rule": True} and _methods(checks, "P_rule")["relation_in_source"] == [True]


# ------------------------------------------------------------------------------------------- a quoted conjunction

TOWNS = SuppliedText(document_id="memo", title="Census", author=None, text="Ash, Birch and Cedar each lost population between 2010 and 2020.")
TOWN_SYMBOLS = [{"name": n, "sort": "Bool", "meaning": f"{town} lost population"} for n, town in (("a", "Ash"), ("b", "Birch"), ("c", "Cedar"), ("d", "Dale"))]


def test_a_conjunction_of_facts_one_excerpt_states_is_verified_as_its_content():
    verified, checks = _ground([{"id": "E", "expr": {"op": "and", "args": [V("a"), V("b"), V("c")]}, "label": "Ash, Birch and Cedar each lost population",
                                 "grounding": _quote("memo", "Ash, Birch and Cedar each lost population between 2010 and 2020")}], TOWN_SYMBOLS, V("a"), [TOWNS])
    assert verified == {"E": True} and _methods(checks, "E")["content_in_excerpt"] == [True]


def test_clean_control_a_conjunct_the_excerpt_does_not_state_leaves_it_unverified():
    verified, _ = _ground([{"id": "E", "expr": {"op": "and", "args": [V("a"), V("b"), V("d")]}, "label": "Ash, Birch and Dale each lost population",
                            "grounding": _quote("memo", "Ash, Birch and Cedar each lost population between 2010 and 2020")}], TOWN_SYMBOLS, V("a"), [TOWNS])
    assert verified == {"E": None}


# ------------------------------------------------------------------------------------------- the point dressed as a quotation

TEXT_C = SuppliedText(document_id="memo", title="Text C", author=None, text="In 2003 the city introduced a congestion charge. Traffic in the zone fell by 15%.")


def test_clean_control_an_excerpt_that_states_the_premise_verifies_it():
    verified, checks = _ground([{"id": "Q", "expr": V("fell"), "label": "traffic in the zone fell by 15%", "grounding": _quote("memo", "Traffic in the zone fell by 15%")}],
                               [{"name": "fell", "sort": "Bool", "meaning": "traffic in the zone fell by 15%"}], V("fell"), [TEXT_C])
    assert verified == {"Q": True} and "content_in_excerpt" not in _methods(checks, "Q")


# ------------------------------------------------------------------------------------------- another entity or quantity

CENSUS = SuppliedText(document_id="d1", title="Census", author=None,
                      text="In 2020 Northtown had 300 residents. In 2020 Southtown had 450 residents. In 2020 wages rose by 3%. In 2020 prices rose by 5%.")


def _figure(label: str, excerpt: str, value: str):
    return _ground([{"id": "P1", "expr": {"op": "eq", "left": V("x"), "right": {"op": "int", "value": value}}, "label": label,
                     "grounding": {"kind": "quotation", "source_refs": [{"document_id": "d1", "excerpt": excerpt}], "certainty": "established"}}],
                   [{"name": "x", "sort": "Int", "meaning": label}], {"op": "gt", "left": V("x"), "right": {"op": "int", "value": "1"}}, [CENSUS])[0]


def test_clean_control_the_excerpt_about_the_same_entity_and_quantity_grounds_it():
    assert _figure("In 2020 Southtown had 450 residents", "In 2020 Southtown had 450 residents", "450") == {"P1": True}
    assert _figure("In 2020 prices rose by 5%", "In 2020 prices rose by 5%", "5") == {"P1": True}


# ------------------------------------------------------------------------------------------- a task-setting proposition

TASK = TaskRecord.of("t", "r", "Discuss whether the policy worked. Assume inflation is falling.")


def _task_premise(text: str, name: str):
    return _ground([{"id": "P1", "expr": V(name), "label": text, "grounding": {"kind": "task_setting", "source_refs": []}},
                    {"id": "P2", "expr": {"op": "implies", "left": V(name), "right": V("w")}, "label": "so the policy worked",
                     "grounding": {"kind": "specialist_inference", "source_refs": []}}],
                   [{"name": name, "sort": "Bool", "meaning": text}, {"name": "w", "sort": "Bool", "meaning": "the policy worked"}], V("w"), [], task=TASK)


def test_a_task_setting_proposition_the_task_does_not_state_is_refuted():
    verified, checks = _task_premise("the economy is in recession", "rcs")
    assert verified["P1"] is False and _methods(checks, "P1")["numeric_in_task"] == [False]


def test_clean_control_a_task_setting_proposition_the_task_states_is_not_refuted():
    verified, _ = _task_premise("inflation is falling", "f")
    assert verified["P1"] is not False


# ------------------------------------------------------------------------------------------- a dated change is no range

SYM_C24 = [{"name": "c24", "sort": "Real", "meaning": "share of shoppers using single-use bags in 2024 (%)"}]


def test_clean_control_a_range_states_no_single_value():
    survey = SuppliedText(document_id="survey-1", title="Survey", author=None, text="In 2024 between 15% and 18% of shoppers used single-use bags.")
    verified, _ = _ground([{"id": "P", "expr": {"op": "eq", "left": V("c24"), "right": R("18")}, "label": "in 2024 18% used single-use bags",
                            "grounding": _quote("survey-1", "between 15% and 18% of shoppers used single-use bags")}], SYM_C24, {"op": "lt", "left": V("c24"), "right": R("20")}, [survey])
    assert verified == {"P": False}


# ------------------------------------------------------------------------------------------- pooled and derived figures

SALES = SuppliedText(document_id="sales", title="Sales table", author=None, text="Monthly sales: January 1200 units, February 1180 units, March 1150 units.")
SALES_REFS = [{"document_id": "sales", "excerpt": e} for e in ("January 1200 units", "February 1180 units", "March 1150 units")]
SYM_MEAN = [{"name": "m1", "sort": "Real", "meaning": "mean monthly sales January to March (units)"}]


def _mean(addends: tuple[str, str, str]):
    expr = {"op": "eq", "left": V("m1"), "right": {"op": "div", "left": {"op": "add", "args": [R(a) for a in addends]}, "right": R("3")}}
    return _ground([{"id": "P_m1", "expr": expr, "label": "the mean of the three months", "grounding": _arith(SALES_REFS)}], SYM_MEAN,
                   {"op": "gt", "left": V("m1"), "right": R("1000")}, [SALES])


def test_clean_control_an_addend_the_excerpts_do_not_state_is_refused():
    verified, _ = _mean(("1200", "1180", "1250"))
    assert verified == {"P_m1": False}


COSTS = SuppliedText(document_id="costs", title="Costs", author=None, text="Fixed costs are $40000. The selling price is $5.00 and the variable cost is $3.00 per unit.")


def _break_even(answer: str):
    expr = {"op": "eq", "left": V("be"), "right": {"op": "div", "left": R("40000"), "right": R("2.00")}}
    return _ground([{"id": "P_be", "expr": expr, "label": "break-even = 40000 / 2.00", "grounding": _arith([{"document_id": "costs", "excerpt": "Fixed costs are $40000"}])}],
                   [{"name": "be", "sort": "Real", "meaning": "break-even output (units)"}], {"op": "eq", "left": V("be"), "right": R("20000")}, [COSTS],
                   answer_texts=[answer])


