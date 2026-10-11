import json

import pytest

from epinoic_logic.engine.statuses import VerificationStatus
from epinoic_logic.engine.validator import parse_and_validate, validate_problem
from epinoic_logic.ir.schema import DEFAULT_LIMITS, Limits, Problem

from .conftest import I, R, V, cmp, make_problem


def codes(outcome):
    return sorted({d.code for d in outcome.diagnostics})


def test_valid_problem_ok(transitivity):
    p, out = parse_and_validate(json.dumps(transitivity))
    assert p is not None and out.ok and out.status is None and out.diagnostics == []
    assert out.sorts == {"P1": "Bool", "P2": "Bool", "C": "Bool"}


def test_undeclared_symbol():
    data = make_problem("consistency", [("x", "Int")], [("P", cmp("gt", V("x"), V("y")))])
    _, out = parse_and_validate(data)
    assert not out.ok and out.status is VerificationStatus.INVALID_FORMALIZATION and "E101" in codes(out)


def test_int_real_mixing_rejected():
    data = make_problem("consistency", [("x", "Int"), ("r", "Real")], [("P", cmp("gt", V("x"), V("r")))])
    _, out = parse_and_validate(data)
    assert "E102" in codes(out) and out.status is VerificationStatus.INVALID_FORMALIZATION


def test_to_real_makes_mixing_legal():
    data = make_problem("consistency", [("x", "Int"), ("r", "Real")], [("P", cmp("gt", {"op": "to_real", "arg": V("x")}, V("r")))])
    _, out = parse_and_validate(data)
    assert out.ok


def test_bool_in_compare_rejected():
    data = make_problem("consistency", [("a", "Bool"), ("b", "Bool")], [("P", cmp("eq", V("a"), V("b")))])
    _, out = parse_and_validate(data)
    assert "E102" in codes(out)


def test_non_boolean_assertion_rejected():
    data = make_problem("consistency", [("x", "Int")], [("P", {"op": "add", "args": [V("x"), I(1)]})])
    _, out = parse_and_validate(data)
    assert "E107" in codes(out)


def test_unknown_operator_is_schema_violation():
    data = make_problem("consistency", [], [("P", {"op": "exec", "code": "import os"})])
    p, out = parse_and_validate(data)
    assert p is None and "E100" in codes(out) and out.status is VerificationStatus.INVALID_FORMALIZATION


def test_unapproved_field_rejected():
    data = make_problem("consistency", [("a", "Bool")], [("P", V("a"))])
    data["premises"][0]["extra"] = 1
    p, out = parse_and_validate(data)
    assert p is None and "E100" in codes(out)


def test_nonlinear_rejected_by_default_and_allowed_by_policy():
    data = make_problem("consistency", [("x", "Int"), ("y", "Int")], [("P", cmp("gt", {"op": "mul", "args": [V("x"), V("y")]}, I(0)))])
    _, out = parse_and_validate(data)
    assert "E201" in codes(out) and out.status is VerificationStatus.UNSUPPORTED
    _, out2 = parse_and_validate(data, Limits(allow_nonlinear=True))
    assert out2.ok


def test_division_policy():
    bad_var = make_problem("consistency", [("a", "Real"), ("b", "Real")], [("P", cmp("gt", {"op": "div", "left": V("a"), "right": V("b")}, R(0)))])
    _, out = parse_and_validate(bad_var)
    assert "E202" in codes(out) and out.status is VerificationStatus.UNSUPPORTED
    zero = make_problem("consistency", [("a", "Real")], [("P", cmp("gt", {"op": "div", "left": V("a"), "right": R(0)}, R(0)))])
    _, out = parse_and_validate(zero)
    assert "E203" in codes(out)
    ok = make_problem("consistency", [("a", "Real")], [("P", cmp("gt", {"op": "div", "left": V("a"), "right": R("3/2")}, R(0)))])
    _, out = parse_and_validate(ok)
    assert out.ok
    int_mod_real = make_problem("consistency", [("a", "Real")], [("P", cmp("gt", {"op": "mod", "left": V("a"), "right": I(2)}, R(0)))])
    _, out = parse_and_validate(int_mod_real)
    assert not out.ok


def test_limits_depth_nodes_symbols_premises():
    deep = V("a")
    for _ in range(DEFAULT_LIMITS.max_depth + 2):
        deep = {"op": "not", "arg": deep}
    data = make_problem("consistency", [("a", "Bool")], [("P", deep)])
    _, out = parse_and_validate(data)
    assert "E303" in codes(out)
    wide = {"op": "and", "args": [V("a")] * (DEFAULT_LIMITS.max_nary_args + 1)}
    _, out = parse_and_validate(make_problem("consistency", [("a", "Bool")], [("P", wide)]))
    assert "E304" in codes(out)
    many_syms = make_problem("consistency", [(f"s{i}", "Bool") for i in range(DEFAULT_LIMITS.max_symbols + 1)], [("P", V("s0"))])
    _, out = parse_and_validate(many_syms)
    assert "E300" in codes(out)
    many_prem = make_problem("consistency", [("a", "Bool")], [(f"P{i}", V("a")) for i in range(DEFAULT_LIMITS.max_premises + 1)])
    _, out = parse_and_validate(many_prem)
    assert "E301" in codes(out)
    small = Limits(max_nodes=3)
    _, out = parse_and_validate(make_problem("consistency", [("a", "Bool")], [("P", {"op": "and", "args": [V("a"), V("a"), V("a")]})]), small)
    assert "E302" in codes(out)


def test_payload_size_and_shape():
    _, out = parse_and_validate(b"[1,2,3]")
    assert not out.ok and out.status is VerificationStatus.INVALID_FORMALIZATION
    _, out = parse_and_validate("x" * 2000, max_bytes=1000)
    assert "E306" in codes(out)
    _, out = parse_and_validate("{not json")
    assert not out.ok


def test_deep_json_bomb_does_not_crash():
    bomb = '{"op":"not","arg":' * 10000 + '{"op":"var","name":"a"}' + "}" * 10000
    data = '{"problem_id":"p","request_id":"r","claim_id":"c","query":"consistency","symbols":[{"name":"a","sort":"Bool"}],"premises":[{"id":"P","expr":' + bomb + "}]}"
    p, out = parse_and_validate(data)
    assert not out.ok and out.status is VerificationStatus.INVALID_FORMALIZATION


def test_huge_literal_rejected():
    data = make_problem("consistency", [("x", "Int")], [("P", cmp("gt", V("x"), I("9" * 60)))])
    p, out = parse_and_validate(data)
    assert not out.ok


def test_duplicate_ids_and_conclusion_shape():
    with pytest.raises(Exception):
        Problem.model_validate(make_problem("consistency", [("a", "Bool")], [("P", V("a")), ("P", V("a"))]))
    with pytest.raises(Exception):
        Problem.model_validate(make_problem("consistency", [("a", "Bool")], [("P", V("a"))], ("C", V("a"))))
    with pytest.raises(Exception):
        Problem.model_validate(make_problem("entailment", [("a", "Bool")], [("P", V("a"))]))


def test_ir_version_unsupported():
    data = make_problem("consistency", [("a", "Bool")], [("P", V("a"))])
    data["ir_version"] = "2.0"
    p, out = parse_and_validate(data)
    assert not out.ok
