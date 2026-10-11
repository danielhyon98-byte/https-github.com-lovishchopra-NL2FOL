import z3

from epinoic_logic.engine.compiler import compile_problem, to_smt2
from epinoic_logic.engine.validator import validate_problem
from epinoic_logic.ir.schema import Problem

from .conftest import I, R, V, cmp, make_problem


def compiled(data):
    p = Problem.model_validate(data)
    assert validate_problem(p).ok, validate_problem(p).diagnostics
    return compile_problem(p)


def check(c):
    s = z3.Solver(ctx=c.ctx)
    s.add(*c.premises.values())
    return s.check()


def test_integer_division_semantics():
    c = compiled(make_problem("consistency", [("x", "Int")], [
        ("P1", cmp("eq", {"op": "idiv", "left": I(7), "right": I(2)}, I(3))),
        ("P2", cmp("eq", {"op": "mod", "left": I(-7), "right": I(2)}, I(1))),
        ("P3", cmp("eq", {"op": "idiv", "left": I(-7), "right": I(2)}, I(-4))),
    ]))
    assert check(c) == z3.sat


def test_exact_real_division():
    c = compiled(make_problem("consistency", [("r", "Real")], [
        ("P1", cmp("eq", V("r"), {"op": "div", "left": R(1), "right": R(3)})),
        ("P2", cmp("eq", {"op": "mul", "args": [V("r"), R(3)]}, R(1))),
    ]))
    s = z3.Solver(ctx=c.ctx)
    s.add(*c.premises.values())
    assert s.check() == z3.sat
    val = s.model().eval(c.symbols["r"])
    assert val.as_fraction().numerator == 1 and val.as_fraction().denominator == 3


def test_decimal_literal_is_exact_rational():
    c = compiled(make_problem("consistency", [("r", "Real")], [
        ("P1", cmp("eq", V("r"), R("0.1"))),
        ("P2", cmp("eq", {"op": "mul", "args": [V("r"), R(10)]}, R(1))),
    ]))
    assert check(c) == z3.sat


def test_every_operator_compiles():
    data = make_problem("consistency", [("a", "Bool"), ("b", "Bool"), ("x", "Int"), ("y", "Int"), ("r", "Real")], [
        ("B1", {"op": "and", "args": [V("a"), {"op": "or", "args": [V("b"), {"op": "not", "arg": V("a")}]}]}),
        ("B2", {"op": "implies", "left": V("a"), "right": V("b")}),
        ("B3", {"op": "iff", "left": V("a"), "right": {"op": "bool", "value": True}}),
        ("A1", cmp("le", {"op": "add", "args": [V("x"), V("y"), I(1)]}, {"op": "sub", "left": V("x"), "right": {"op": "neg", "arg": V("y")}})),
        ("A2", cmp("ne", {"op": "mul", "args": [I(2), V("x")]}, I(3))),
        ("A3", cmp("lt", {"op": "to_real", "arg": V("x")}, {"op": "ite", "cond": V("a"), "then": V("r"), "otherwise": R("1/2")})),
        ("A4", cmp("ge", {"op": "idiv", "left": V("x"), "right": I(2)}, {"op": "mod", "left": V("y"), "right": I(3)})),
        ("A5", cmp("gt", {"op": "div", "left": V("r"), "right": R(2)}, R(0))),
        ("A6", cmp("eq", V("x"), V("y"))),
    ])
    c = compiled(data)
    assert len(c.premises) == 9 and check(c) in (z3.sat, z3.unsat)


def test_to_smt2_contains_declarations_and_negated_conclusion(transitivity):
    c = compiled(transitivity)
    text = to_smt2(c, negate_conclusion=True)
    assert "declare-fun x" in text and "(not" in text and "(check-sat)" in text
    assert "(not" not in to_smt2(c, negate_conclusion=False)


def test_fresh_context_per_compile(transitivity):
    c1 = compiled(transitivity)
    c2 = compiled(transitivity)
    assert c1.ctx is not c2.ctx
