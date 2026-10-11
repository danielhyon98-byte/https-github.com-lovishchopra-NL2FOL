"""Named pack policies (engine/policies.py) and the signed record of non-default Limits
(engine/results.py, engine/runner.py).

What is pinned here:

* the two named policies map to exact Limits, the table is read-only, and no policy can
  raise any bound other than opening the nonlinear-term gate;
* an unknown policy name (case, whitespace, confusables, str subclasses, non-strings) is
  refused, never run under some other policy;
* a default-policy result has no ``limits`` field in any dump, and its signable text, JSON
  and signature are byte-identical to the result model before the record existed (golden
  digests computed with the committed code);
* a nonlinear result records its Limits under the signature, so tampering with or stripping
  the record fails ``verify_signature``; the hand-off binding check is unaffected;
* every runner path records non-default Limits, and a non-Limits argument is an
  INTERNAL_ERROR, never a run under guessed bounds;
* under the nonlinear policy, an assertion above the degree bound is UNSUPPORTED before it
  reaches Z3 (degree 1024 held the solver for about 20 s under a 2 s timeout);
* NONLINEAR_RLIMIT turns hard polynomial systems into TIMEOUT, deterministically and well
  before a long wall-clock timeout, and TIMEOUT/UNKNOWN are never success;
* adversarial IR (10,000-digit literals, nesting depth 500, oversize arity, symbol and node
  counts, confusable identifiers, malformed JSON) is rejected within bounds under every
  policy, without raising.
"""
from __future__ import annotations

import hashlib
import json
import time
from types import SimpleNamespace
from typing import Any, Callable

import pytest
import z3
from pydantic import BaseModel

from epinoic_logic.engine import runner as runner_mod
from epinoic_logic.engine.compiler import CompileError
from epinoic_logic.engine.policies import (
    LINEAR,
    LINEAR_LIMITS,
    NONLINEAR,
    NONLINEAR_LIMITS,
    NONLINEAR_MAX_DEGREE,
    NONLINEAR_RLIMIT,
    PACK_POLICIES,
    UnknownPolicyError,
    max_degree,
    policy_config,
    policy_limits,
    polynomial_degree,
    required_policy,
)
from epinoic_logic.engine.procedures import ProcedureOutcome
from epinoic_logic.engine.provenance import config_digest, sign_result, signable_text, verify_signature
from epinoic_logic.engine.results import (
    Binding,
    Counterexample,
    Diagnostic,
    ModelAssignment,
    SolverConfig,
    StageTiming,
    UnsatCore,
    VerificationResult,
    Versions,
)
from epinoic_logic.engine.runner import verify
from epinoic_logic.engine.statuses import VerificationStatus as S, is_definitive
from epinoic_logic.integrity.handoff import check_result_binding
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.ir.schema import DEFAULT_LIMITS, Limits, Neg, Problem, Var

from .conftest import I, R, V, cmp, make_problem

KEY = b"policy-test-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)
#: VerificationResult fields before the limits record existed.
OLD_FIELDS = frozenset({
    "result_id", "request_id", "claim_id", "problem_id", "query", "status", "scope_statement", "binding", "versions",
    "solver_config", "counterexample", "unsat_core", "premises_relied_on", "ungrounded_dependencies",
    "unverified_dependencies", "witness_model", "diagnostics", "timings", "reason_unknown", "issued_at", "signature",
    "signature_key_id",
})


def mul(*args: dict) -> dict:
    return {"op": "mul", "args": list(args)}


def add(*args: dict) -> dict:
    return {"op": "add", "args": list(args)}


def P(data: dict) -> Problem:
    return Problem.model_validate(data)


def linear_problem() -> Problem:
    """x > y, y > z |= x > z over Int."""
    return P(make_problem("entailment", [("x", "Int"), ("y", "Int"), ("z", "Int")],
                          [("P1", cmp("gt", V("x"), V("y"))), ("P2", cmp("gt", V("y"), V("z")))], ("C", cmp("gt", V("x"), V("z")))))


def nonlinear_problem() -> Problem:
    """x*y = 6, x = 2 |= y = 3 over Real: a product of two unknowns (E201 under the linear policy)."""
    return P(make_problem("entailment", [("x", "Real"), ("y", "Real")],
                          [("P1", cmp("eq", mul(V("x"), V("y")), R(6))), ("P2", cmp("eq", V("x"), R(2)))], ("C", cmp("eq", V("y"), R(3)))))


def power_problem(n: int, value: str = "2") -> Problem:
    """x^n = value as nested products of at most 32 factors (the shape of a degree bomb)."""
    def pw(k: int) -> dict:
        if k <= 32:
            return mul(*([V("x")] * k)) if k > 1 else V("x")
        f = 32
        while k % f:
            f -= 1
        return mul(*([pw(k // f)] * f))
    return P(make_problem("satisfiability", [("x", "Real")], [("P", cmp("eq", pw(n), R(value)))]))


def fermat_cubic(query: str = "satisfiability") -> Problem:
    """a^3 + b^3 = c^3 over Int with a, b, c > 1: no solution exists and Z3 cannot show it."""
    cube = lambda n: mul(V(n), V(n), V(n))  # noqa: E731
    bounds = [("P1", cmp("gt", V("a"), I(1))), ("P2", cmp("gt", V("b"), I(1))), ("P3", cmp("gt", V("c"), I(1)))]
    symbols = [("a", "Int"), ("b", "Int"), ("c", "Int")]
    if query == "satisfiability":
        return P(make_problem(query, symbols, bounds + [("P4", cmp("eq", add(cube("a"), cube("b")), cube("c"))), ("P5", cmp("lt", V("c"), I(10 ** 12)))]))
    return P(make_problem(query, symbols, bounds, ("C", cmp("ne", add(cube("a"), cube("b")), cube("c")))))


def run_policy(problem: Any, name: str, config: SolverConfig = CFG, **kw: Any):
    return verify(problem, policy_config(name, config), policy_limits(name), **kw)


# =========================================================================== the policy table


def test_named_policies_map_to_exact_limits():
    assert set(PACK_POLICIES) == {LINEAR, NONLINEAR} == {"linear", "nonlinear"}
    assert policy_limits("linear") is DEFAULT_LIMITS is LINEAR_LIMITS
    assert policy_limits("linear") == Limits()
    assert policy_limits("nonlinear") is NONLINEAR_LIMITS
    assert policy_limits("nonlinear") == Limits(allow_nonlinear=True)
    assert policy_limits("nonlinear").model_dump() == {**DEFAULT_LIMITS.model_dump(), "allow_nonlinear": True}


def test_no_policy_can_raise_any_other_limit():
    default = DEFAULT_LIMITS.model_dump()
    assert set(default) == {"max_symbols", "max_premises", "max_nodes", "max_depth", "max_nary_args", "max_const_digits",
                            "allow_nonlinear", "allow_real_division", "allow_int_division"}  # a new Limits field must be reviewed here
    for name, limits in PACK_POLICIES.items():
        values = limits.model_dump()
        changed = {k for k in default if values[k] != default[k]}
        assert changed <= {"allow_nonlinear"}, (name, changed)


def test_the_policy_table_cannot_be_changed_at_run_time():
    with pytest.raises(TypeError):
        PACK_POLICIES["unbounded"] = Limits(max_nodes=10 ** 9)  # type: ignore[index]
    with pytest.raises(TypeError):
        PACK_POLICIES["linear"] = Limits(allow_nonlinear=True)  # type: ignore[index]
    with pytest.raises(TypeError):
        del PACK_POLICIES["linear"]  # type: ignore[attr-defined]
    for method in ("update", "clear", "pop", "popitem", "setdefault"):
        assert not hasattr(PACK_POLICIES, method)
    with pytest.raises(Exception):
        policy_limits("nonlinear").max_nodes = 10 ** 9  # frozen model
    with pytest.raises(Exception):
        policy_limits("linear").allow_nonlinear = True
    assert policy_limits("nonlinear") == Limits(allow_nonlinear=True) and DEFAULT_LIMITS == Limits()


class _Sneaky(str):
    """A str subclass that claims to equal every name."""

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return hash("nonlinear")


class _Loud:
    def __repr__(self) -> str:
        raise AssertionError("the refusal must not call a foreign __repr__")

    __str__ = __repr__


class _PlainSubclass(str):
    pass


UNKNOWN_NAMES = [
    "", "Linear", "LINEAR", "Nonlinear", "NONLINEAR", " linear", "linear ", "linear\n", "\tnonlinear", "non-linear", "non_linear",
    "nonlinear\u200b", "\u200blinear", "nonIinear", "l\u0456near", "\uff4c\uff49\uff4e\uff45\uff41\uff52", "linear\u0301",
    "linear;nonlinear", "linear,nonlinear", "default", "unbounded", "__class__", "keys", "\ud800linear",
    None, 0, 1, 1.0, True, b"linear", bytearray(b"nonlinear"), ["linear"], ("nonlinear",), {"name": "linear"}, {"linear"},
    Limits(), DEFAULT_LIMITS, NONLINEAR_LIMITS, _Sneaky("anything"), _Sneaky("nonlinear"), _PlainSubclass("nonlinear"), _Loud(),
]


@pytest.mark.parametrize("name", UNKNOWN_NAMES, ids=[f"name{i}" for i in range(len(UNKNOWN_NAMES))])
def test_unknown_policy_names_are_refused(name: Any):
    with pytest.raises(UnknownPolicyError) as limits_error:
        policy_limits(name)
    with pytest.raises(UnknownPolicyError):
        policy_config(name, CFG)
    assert isinstance(limits_error.value, ValueError)
    message = str(limits_error.value)
    assert "known policies: linear, nonlinear" in message and len(message) < 400
    message.encode("utf-8")  # never an unencodable message, even for a lone surrogate


def test_refusing_a_huge_name_is_fast_and_bounded():
    giant = "nonlinear" + "x" * 1_000_000
    t0 = time.perf_counter()
    with pytest.raises(UnknownPolicyError) as error:
        policy_limits(giant)
    assert time.perf_counter() - t0 < 0.5
    assert len(str(error.value)) < 400 and "(+999945 characters)" in str(error.value)


def test_a_foreign_object_is_named_by_its_type_only():
    with pytest.raises(UnknownPolicyError) as error:
        policy_limits(_Loud())
    assert "_Loud" in str(error.value)


def test_policy_config_linear_returns_the_callers_config_unchanged():
    for config in (SolverConfig(), CFG, SolverConfig(rlimit=5), SolverConfig(rlimit=NONLINEAR_RLIMIT * 100, timeout_ms=7)):
        assert policy_config("linear", config) is config


def test_policy_config_nonlinear_caps_the_rlimit_and_changes_nothing_else():
    base = SolverConfig(timeout_ms=1234, random_seed=7, memory_max_mb=256)
    capped = policy_config("nonlinear", base)
    assert capped.model_dump() == {**base.model_dump(), "rlimit": NONLINEAR_RLIMIT}
    assert base.rlimit is None  # the caller's config is never modified
    larger = base.model_copy(update={"rlimit": NONLINEAR_RLIMIT * 10})
    assert policy_config("nonlinear", larger).rlimit == NONLINEAR_RLIMIT
    smaller = base.model_copy(update={"rlimit": 1000})
    assert policy_config("nonlinear", smaller) is smaller  # a stricter caller bound is kept
    exact = base.model_copy(update={"rlimit": NONLINEAR_RLIMIT})
    assert policy_config("nonlinear", exact) is exact
    # The rlimit is part of the bound configuration, so linear and nonlinear results never share a config digest.
    assert config_digest(capped) != config_digest(base)


def test_nonlinear_bounds_are_valid_settings():
    assert type(NONLINEAR_RLIMIT) is int and 1 <= NONLINEAR_RLIMIT < 2 ** 32  # Z3 takes an unsigned 32-bit rlimit
    assert SolverConfig(rlimit=NONLINEAR_RLIMIT).rlimit == NONLINEAR_RLIMIT
    # STEM needs degree 13 (integer powers up to 12 plus one auxiliary factor); from degree 384 Z3 overran its timeout.
    assert type(NONLINEAR_MAX_DEGREE) is int and 13 <= NONLINEAR_MAX_DEGREE < 128


# =========================================================================== required_policy and degree


def test_required_policy_is_nonlinear_exactly_when_the_linear_policy_refuses_a_product():
    assert required_policy(linear_problem()) == "linear"
    assert required_policy(nonlinear_problem()) == "nonlinear"
    scaled = P(make_problem("consistency", [("x", "Real")], [("P", cmp("gt", mul(R(2), V("x"), add(R(1), R(2))), R(0)))]))
    assert required_policy(scaled) == "linear"  # constant factors keep a product linear
    other_errors = P(make_problem("consistency", [("x", "Real")], [("P", cmp("gt", V("x"), I(0)))]))
    assert required_policy(other_errors) == "linear"  # a sort error is not a reason to open the gate
    both = P(make_problem("consistency", [("x", "Real"), ("y", "Real")], [("P", cmp("gt", mul(V("x"), V("y")), I(0)))]))
    assert required_policy(both) == "nonlinear"


def _premise_expr(expr: dict, symbols: list[tuple[str, str]] = (("x", "Real"), ("y", "Real"), ("n", "Int"), ("b", "Bool"))) -> Any:
    return P(make_problem("consistency", list(symbols), [("P", expr)])).premises[0].expr


@pytest.mark.parametrize("expr, degree", [
    (cmp("gt", R(3), V("x")), 1),
    (cmp("eq", mul(V("x"), V("x"), V("x")), R(1)), 3),
    (cmp("eq", add(mul(V("x"), V("x")), V("x")), R(1)), 2),
    (cmp("eq", {"op": "sub", "left": V("x"), "right": mul(V("y"), V("y"))}, R(1)), 2),
    (cmp("eq", {"op": "neg", "arg": mul(V("x"), V("y"))}, R(1)), 2),
    (cmp("eq", {"op": "div", "left": mul(V("x"), V("x")), "right": R(2)}, R(1)), 2),
    (cmp("eq", mul(add(V("x"), V("y")), add(V("x"), V("y"))), R(1)), 2),
    (cmp("eq", mul(mul(V("x"), V("x")), mul(V("x"), V("x"))), R(1)), 4),
    (cmp("eq", {"op": "ite", "cond": cmp("gt", mul(V("x"), V("x"), V("x")), R(0)), "then": V("x"), "otherwise": R(0)}, R(1)), 3),
    (cmp("eq", {"op": "to_real", "arg": mul(V("n"), V("n"))}, R(4)), 2),
    (cmp("eq", mul(R(2), R(3), V("x")), R(6)), 1),
    ({"op": "and", "args": [cmp("gt", mul(V("x"), V("y")), R(0)), V("b")]}, 2),
])
def test_polynomial_degree_counts_products_through_every_node(expr: dict, degree: int):
    assert polynomial_degree(_premise_expr(expr)) == degree


def test_polynomial_degree_is_iterative_on_deep_and_wide_input():
    deep: Any = Var(op="var", name="x")
    for _ in range(5_000):  # far beyond Python's recursion limit
        deep = Neg(op="neg", arg=deep)
    t0 = time.perf_counter()
    assert polynomial_degree(deep) == 1
    assert polynomial_degree(power_problem(1024).premises[0].expr) == 1024
    assert time.perf_counter() - t0 < 2.0


def test_max_degree_names_the_first_assertion_at_the_maximum():
    p = P(make_problem("entailment", [("x", "Real"), ("y", "Real")], [
        ("A", cmp("gt", V("x"), R(0))),
        ("B", cmp("eq", mul(V("x"), V("x"), V("y")), R(1))),
        ("C", cmp("eq", mul(V("y"), V("y"), V("y")), R(1))),
    ], ("D", cmp("eq", mul(V("x"), V("y")), R(1)))))
    assert max_degree(p) == (3, "premises[1].expr")
    empty = P(make_problem("consistency", [("x", "Real")], []))
    assert max_degree(empty) == (0, None)


# =========================================================================== the record: default results unchanged


class _Box(BaseModel):
    result: VerificationResult
    results: list[VerificationResult] = []


def test_the_result_model_gained_exactly_one_field():
    assert set(VerificationResult.model_fields) == OLD_FIELDS | {"limits"}
    assert VerificationResult.model_fields["limits"].default is None


@pytest.mark.parametrize("limits", [DEFAULT_LIMITS, Limits(), Limits(allow_nonlinear=False), DEFAULT_LIMITS.model_copy(), LINEAR_LIMITS])
def test_default_results_carry_no_limits_record_in_any_dump(limits: Limits):
    r = verify(linear_problem(), CFG, limits, KEY, "k1")
    assert r.status is S.ENTAILED and r.limits is None
    dumps = [r.model_dump(), r.model_dump(mode="json"), r.model_dump(exclude_none=True), r.model_dump(round_trip=True),
             json.loads(r.model_dump_json()), _Box(result=r, results=[r]).model_dump(mode="json")["result"],
             json.loads(_Box(result=r, results=[r]).model_dump_json())["results"][0]]
    for dump in dumps:
        assert "limits" not in dump
    assert '"limits"' not in signable_text(r)
    assert verify_signature(r, KEY)


def _golden_results() -> dict[str, VerificationResult]:
    common: dict[str, Any] = dict(
        request_id="req1", claim_id="r1:s1.2", problem_id="stem-eq-r1-1",
        binding=Binding(problem_digest="a" * 64, config_digest="b" * 64, versions_digest="c" * 64, binding_digest="d" * 64, smt2="(assert true)\n"),
        versions=Versions(ir_version="1.0", engine_version="0.2.0", policy_version="2026.10-v2", z3_version="5.1.0"),
        solver_config=SolverConfig(), issued_at="2026-10-11T00:00:00Z",
        timings=[StageTiming(stage="validate", ms=0.25), StageTiming(stage="entailment", ms=3.5)],
    )
    return {
        "entailed": VerificationResult(result_id="0" * 32, query="entailment", status=S.ENTAILED,
                                       unsat_core=UnsatCore(premise_ids=["C_DEF", "R"], includes_negated_conclusion=True),
                                       premises_relied_on=["C_DEF", "R"], **common),
        "counter": VerificationResult(result_id="1" * 32, query="entailment", status=S.COUNTEREXAMPLE,
                                      counterexample=Counterexample(assignments=[ModelAssignment(symbol="c", sort="Real", value="5"),
                                                                                 ModelAssignment(symbol="r", sort="Real", value="6")]),
                                      diagnostics=[Diagnostic(code="E505", message="discarded \u00e9", path="premises[0].grounding")], **common),
        "unparsed": VerificationResult(result_id="2" * 32, request_id="unknown", claim_id="unknown", problem_id="unknown", query=None,
                                       status=S.INVALID_FORMALIZATION, binding=common["binding"], versions=common["versions"],
                                       solver_config=SolverConfig(timeout_ms=10, rlimit=5, memory_max_mb=None), issued_at=common["issued_at"]),
    }


#: sha256(signable_text), sha256(model_dump_json of the signed result), signature: computed with the
#: committed result model, before the limits record was added (key b"golden-key-0123456789abcdef01234").
GOLDEN = {
    "entailed": ("7e64d89714e4525e7a17fb00b75aa659e9eec5b838f886c812c9b5bd0aaa6fb4",
                 "3d750a3c701c4e6f7dbb2aeb15be70a6605d7b5b735d0ebde1dea5dc10cec72d",
                 "5d1107153511e82534bf2bf3bce2f6264595746006d141a4f2d6d16cd37e6aa4"),
    "counter": ("6c73e794fbd8574a404cfdf6bb83329cd0aaae1a3180ba4cd54341fbc2a83897",
                "bba354b45ff7ffa97e50de106ba8d2aff89d0c4dbe1444e5576209b510fe2503",
                "f1449b1e88f4d801ee529669049a6097cb8ae5e1b9d47f385898b98ac3d8d2d3"),
    "unparsed": ("7e055a5621f8566480ac53bc5aef1efbd3a43d2e88dc802d2c4543703e9ca700",
                 "af3be4c8a02f512bc1620dcf207f8f6c2917f525e3eb2f4994805a3e3ea6fea0",
                 "1d12159b08985051c970e38712cb78e44d1f744aa35f81d3aee69973856f3f35"),
}


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_default_results_are_byte_identical_to_the_pre_record_model(name: str):
    result = _golden_results()[name]
    signed = sign_result(result, b"golden-key-0123456789abcdef01234", "k1")
    text_digest, dump_digest, signature = GOLDEN[name]
    assert hashlib.sha256(signable_text(result).encode()).hexdigest() == text_digest
    assert hashlib.sha256(signed.model_dump_json().encode()).hexdigest() == dump_digest
    assert signed.signature == signature


# =========================================================================== the record: non-default results


def test_nonlinear_result_records_its_limits_under_the_signature():
    r = run_policy(nonlinear_problem(), NONLINEAR, signing_key=KEY, key_id="k1")
    assert r.status is S.ENTAILED
    assert r.limits == NONLINEAR_LIMITS and type(r.limits) is Limits
    assert r.solver_config.rlimit == NONLINEAR_RLIMIT
    dumped = r.model_dump(mode="json")
    assert dumped["limits"] == {**DEFAULT_LIMITS.model_dump(), "allow_nonlinear": True}
    assert '"limits":{' in signable_text(r) and '"allow_nonlinear":true' in signable_text(r)
    assert verify_signature(r, KEY)
    assert run_policy(nonlinear_problem(), LINEAR).status is S.UNSUPPORTED


def test_other_non_default_limits_are_recorded_too():
    tight = Limits(max_nodes=500, max_depth=12)
    r = verify(linear_problem(), CFG, tight, KEY, "k1")
    assert r.status is S.ENTAILED and r.limits == tight and verify_signature(r, KEY)


@pytest.mark.parametrize("forged", [None, DEFAULT_LIMITS, Limits(allow_nonlinear=False), Limits(allow_nonlinear=True, max_nodes=10 ** 6),
                                    Limits(allow_nonlinear=True, max_const_digits=400), Limits(allow_nonlinear=True, allow_int_division=False)])
def test_changing_or_stripping_a_limits_record_breaks_the_signature(forged: Any):
    r = run_policy(nonlinear_problem(), NONLINEAR, signing_key=KEY, key_id="k1")
    assert verify_signature(r, KEY)
    assert not verify_signature(r.model_copy(update={"limits": forged}), KEY)


def test_adding_a_limits_record_to_a_default_result_breaks_the_signature():
    r = verify(linear_problem(), CFG, signing_key=KEY, key_id="k1")
    assert not verify_signature(r.model_copy(update={"limits": NONLINEAR_LIMITS}), KEY)


@pytest.mark.parametrize("edit", [
    lambda d: d["limits"].__setitem__("max_depth", 400),
    lambda d: d["limits"].__setitem__("allow_nonlinear", False),
    lambda d: d.pop("limits"),
    lambda d: d.__setitem__("limits", None),
])
def test_tampering_with_the_record_in_transit_is_detected(edit: Callable[[dict], Any]):
    r = run_policy(nonlinear_problem(), NONLINEAR, signing_key=KEY, key_id="k1")
    payload = r.model_dump(mode="json")
    edit(payload)
    assert not verify_signature(VerificationResult.model_validate(payload), KEY)


def test_results_round_trip_through_json_with_their_signatures():
    default = verify(linear_problem(), CFG, signing_key=KEY, key_id="k1")
    nonlinear = run_policy(nonlinear_problem(), NONLINEAR, signing_key=KEY, key_id="k1")
    for r in (default, nonlinear):
        again = VerificationResult.model_validate(r.model_dump(mode="json"))
        assert verify_signature(again, KEY) and signable_text(again) == signable_text(r) and again.limits == r.limits
        assert verify_signature(VerificationResult.model_validate_json(r.model_dump_json()), KEY)
    # An explicit null (as a client might send it back) is the default record.
    with_null = VerificationResult.model_validate({**default.model_dump(mode="json"), "limits": None})
    assert verify_signature(with_null, KEY) and "limits" not in with_null.model_dump(mode="json")


def test_the_binding_formula_is_unchanged_by_the_record():
    p = linear_problem()
    a = verify(p, CFG, DEFAULT_LIMITS)
    b = verify(p, CFG, NONLINEAR_LIMITS)
    assert a.limits is None and b.limits == NONLINEAR_LIMITS
    for field in ("problem_digest", "config_digest", "versions_digest", "binding_digest", "smt2"):
        assert getattr(a.binding, field) == getattr(b.binding, field)
    pd, cd, vd = b.binding.problem_digest, b.binding.config_digest, b.binding.versions_digest
    assert b.binding.binding_digest == sha256_hex("|".join((pd, cd, vd)))


@pytest.mark.parametrize("name", [LINEAR, NONLINEAR])
def test_the_hand_off_binding_check_accepts_policy_results(name: str):
    p = nonlinear_problem() if name == NONLINEAR else linear_problem()
    config = policy_config(name, CFG)
    r = verify(p, config, policy_limits(name), KEY, "k1")
    assert r.status is S.ENTAILED
    assert check_result_binding(r, p, KEY, config=config) == []


def test_the_hand_off_check_sees_the_policy_rlimit_and_a_forged_record():
    p = nonlinear_problem()
    r = run_policy(p, NONLINEAR, signing_key=KEY, key_id="k1")
    stale = {f.code for f in check_result_binding(r, p, KEY, config=CFG)}
    assert "INT-STALE-005" in stale  # the nonlinear rlimit is part of the bound configuration
    forged = {f.code for f in check_result_binding(r.model_copy(update={"limits": None}), p, KEY, config=policy_config(NONLINEAR, CFG))}
    assert forged == {"INT-STALE-002"}


# =========================================================================== every runner path records the Limits


def _raise(exc: BaseException) -> Callable[..., Any]:
    def fn(*_a: Any, **_k: Any) -> Any:
        raise exc
    return fn


def _outcome(**kw: Any) -> Callable[..., ProcedureOutcome]:
    return lambda _compiled, _config: ProcedureOutcome(**kw)


def _literal_problem(digits: int) -> dict:
    return make_problem("consistency", [("x", "Real")], [("P", cmp("eq", V("x"), R("1" * digits)))])


PATHS: dict[str, tuple[Callable[[pytest.MonkeyPatch], Any], S, str]] = {
    # name: (setup returning the problem or raw payload, expected status, expected diagnostic code or "")
    "unparsed-bytes": (lambda mp: b"{not json", S.INVALID_FORMALIZATION, "E100"),
    "schema-violation": (lambda mp: {"problem_id": "p"}, S.INVALID_FORMALIZATION, "E100"),
    "limit-violation": (lambda mp: _literal_problem(41), S.INVALID_FORMALIZATION, "E305"),
    "policy-violation": (lambda mp: make_problem("consistency", [("x", "Real")], [("P", cmp("eq", {"op": "div", "left": V("x"), "right": R(0)}, R(1)))]),
                         S.UNSUPPORTED, "E203"),
    "degree-gate": (lambda mp: power_problem(NONLINEAR_MAX_DEGREE + 1), S.UNSUPPORTED, "E201"),
    "compile-error": (lambda mp: (mp.setattr(runner_mod, "compile_problem", _raise(CompileError(Diagnostic(code="E200", message="injected")))),
                                  linear_problem())[1], S.UNSUPPORTED, "E200"),
    "solver-abort": (lambda mp: (mp.setattr(runner_mod, "reset_global_memory_limit", lambda: None),
                                 mp.setitem(runner_mod._PROCEDURES, "entailment", _raise(z3.Z3Exception("injected"))), linear_problem())[2],
                     S.UNKNOWN, "E402"),
    "internal-error": (lambda mp: (mp.setitem(runner_mod._PROCEDURES, "entailment", _raise(RuntimeError("injected"))), linear_problem())[1],
                       S.INTERNAL_ERROR, "E900"),
    "solver-unknown": (lambda mp: (mp.setitem(runner_mod._PROCEDURES, "entailment", _outcome(status=S.UNKNOWN, reason_unknown="incomplete",
                                                                                         model={"x": "1"})), linear_problem())[1],
                       S.UNKNOWN, "E401"),
    "solver-memout": (lambda mp: (mp.setitem(runner_mod._PROCEDURES, "entailment", _outcome(status=S.UNKNOWN, reason_unknown="memout", memout=True)),
                                  linear_problem())[1], S.UNKNOWN, "E402"),
    "solver-timeout": (lambda mp: (mp.setitem(runner_mod._PROCEDURES, "entailment", _outcome(status=S.TIMEOUT, reason_unknown="canceled")),
                                   linear_problem())[1], S.TIMEOUT, "E400"),
    "decided": (lambda mp: linear_problem(), S.ENTAILED, ""),
}


@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("limits", [NONLINEAR_LIMITS, DEFAULT_LIMITS], ids=["nonlinear", "default"])
def test_every_result_path_records_non_default_limits(path: str, limits: Limits, monkeypatch: pytest.MonkeyPatch):
    setup, expected, code = PATHS[path]
    payload = setup(monkeypatch)
    if isinstance(payload, dict) and "query" in payload:
        payload = P(payload)
    r = verify(payload, CFG, limits, KEY, "k1")
    assert r.status is expected, (r.status, r.diagnostics)
    if code:
        assert code in {d.code for d in r.diagnostics}
        assert not is_definitive(r.status)
        assert r.counterexample is None and r.witness_model is None and r.unsat_core is None
    assert verify_signature(r, KEY)
    if limits is DEFAULT_LIMITS:
        assert r.limits is None and "limits" not in r.model_dump(mode="json")
    else:
        assert r.limits == NONLINEAR_LIMITS and '"limits":{' in signable_text(r)


@pytest.mark.parametrize("bad", [None, {}, {"allow_nonlinear": True}, "nonlinear", 1, object(),
                                 SimpleNamespace(**NONLINEAR_LIMITS.model_dump())], ids=lambda b: type(b).__name__)
def test_a_non_limits_argument_is_an_internal_error_never_a_guess(bad: Any):
    r = verify(nonlinear_problem(), CFG, bad, KEY, "k1")  # type: ignore[arg-type]
    assert r.status is S.INTERNAL_ERROR and not is_definitive(r.status)
    assert [d.code for d in r.diagnostics] == ["E900"]
    assert r.limits is None and verify_signature(r, KEY)


# =========================================================================== the degree gate


def test_degree_at_the_bound_is_decided_and_above_it_refused_before_compilation():
    at = P(make_problem("satisfiability", [("x", "Real")], [("A", cmp("eq", V("x"), R(1))),
                                                            ("B", cmp("eq", mul(*([V("x")] * NONLINEAR_MAX_DEGREE)), R(1)))]))
    assert run_policy(at, NONLINEAR).status is S.SATISFIABLE
    above = power_problem(NONLINEAR_MAX_DEGREE + 1)
    r = run_policy(above, NONLINEAR)
    assert r.status is S.UNSUPPORTED and [d.code for d in r.diagnostics] == ["E201"]
    assert r.diagnostics[0].path == "premises[0].expr"
    assert f"polynomial degree {NONLINEAR_MAX_DEGREE + 1} exceeds the nonlinear policy bound {NONLINEAR_MAX_DEGREE}" in r.diagnostics[0].message
    assert [t.stage for t in r.timings] == ["validate"] and r.binding.smt2 is None  # never compiled
    assert r.limits == NONLINEAR_LIMITS
    # Under the linear policy the same problem is refused by the nonlinear-term gate itself.
    linear = run_policy(above, LINEAR)
    assert linear.status is S.UNSUPPORTED and "non-constant factors" in linear.diagnostics[0].message


def test_the_measured_degree_1024_hang_is_refused_at_once():
    """Before the gate: x^1024 = 2 under allow_nonlinear held Z3 for about 20 s with a 2000 ms timeout."""
    t0 = time.perf_counter()
    r = run_policy(power_problem(1024), NONLINEAR, SolverConfig(memory_max_mb=None))
    assert r.status is S.UNSUPPORTED and r.diagnostics[0].code == "E201"
    assert time.perf_counter() - t0 < 1.0


def test_the_degree_gate_covers_the_conclusion_and_ite_conditions():
    in_conclusion = P(make_problem("entailment", [("x", "Real")], [("A", cmp("gt", V("x"), R(1)))],
                                   ("C", cmp("gt", mul(*([V("x")] * 25)), R(1)))))
    r = run_policy(in_conclusion, NONLINEAR)
    assert r.status is S.UNSUPPORTED and r.diagnostics[0].path == "conclusion.expr"
    hidden = {"op": "ite", "cond": cmp("gt", mul(*([V("x")] * 25)), R(0)), "then": R(1), "otherwise": R(0)}
    in_condition = P(make_problem("consistency", [("x", "Real")], [("A", cmp("eq", hidden, R(1)))]))
    assert run_policy(in_condition, NONLINEAR).status is S.UNSUPPORTED


def test_chained_auxiliaries_escape_the_degree_gate_but_stay_bounded_by_the_timeout():
    """Each y_k = y_{k-1}^2 has degree 2, so the gate admits the chain (x^32 in effect). Z3 counts
    resource slowly there, so the wall-clock timeout, not the rlimit, stops it; never a success."""
    n = 5
    symbols = [("x", "Real")] + [(f"y{k}", "Real") for k in range(1, n + 1)]
    premises = [("D1", cmp("eq", V("y1"), mul(V("x"), V("x"))))]
    premises += [(f"D{k + 1}", cmp("eq", V(f"y{k + 1}"), mul(V(f"y{k}"), V(f"y{k}")))) for k in range(1, n)]
    premises += [("T", cmp("eq", V(f"y{n}"), R(3)))]
    chain = P(make_problem("satisfiability", symbols, premises))
    assert max_degree(chain)[0] == 2
    t0 = time.perf_counter()
    r = run_policy(chain, NONLINEAR, SolverConfig(timeout_ms=200, memory_max_mb=None))
    assert r.status in (S.TIMEOUT, S.UNKNOWN) and not is_definitive(r.status)
    assert r.witness_model is None
    assert time.perf_counter() - t0 < 3.0


# =========================================================================== rlimit cutoffs


def test_nonlinear_rlimit_cuts_a_hard_polynomial_system_deterministically_and_never_as_success():
    long_clock = SolverConfig(timeout_ms=60_000, memory_max_mb=None)
    outcomes = []
    for _ in range(2):
        t0 = time.perf_counter()
        r = run_policy(fermat_cubic(), NONLINEAR, long_clock, signing_key=KEY, key_id="k1")
        elapsed = time.perf_counter() - t0
        assert r.status is S.TIMEOUT and not is_definitive(r.status)
        assert [d.code for d in r.diagnostics] == ["E400"]
        assert r.witness_model is None and r.counterexample is None and r.unsat_core is None and r.premises_relied_on == []
        assert r.solver_config.rlimit == NONLINEAR_RLIMIT and r.limits == NONLINEAR_LIMITS and verify_signature(r, KEY)
        assert elapsed < 15.0  # the rlimit, not the 60 s clock, stopped it (measured: about 0.5 s)
        outcomes.append((r.status, r.reason_unknown, r.binding.binding_digest))
    assert outcomes[0] == outcomes[1]


def test_nonlinear_rlimit_bounds_both_solver_calls_of_an_entailment():
    t0 = time.perf_counter()
    r = run_policy(fermat_cubic("entailment"), NONLINEAR, SolverConfig(timeout_ms=60_000, memory_max_mb=None))
    assert r.status is S.TIMEOUT and r.counterexample is None and r.unsat_core is None
    assert time.perf_counter() - t0 < 15.0


def test_a_short_timeout_still_bounds_a_nonlinear_check():
    t0 = time.perf_counter()
    r = run_policy(fermat_cubic(), NONLINEAR, SolverConfig(timeout_ms=50, memory_max_mb=None))
    assert r.status in (S.TIMEOUT, S.UNKNOWN) and not is_definitive(r.status)
    assert time.perf_counter() - t0 < 3.0


def test_an_unknown_outcome_never_shows_a_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(runner_mod._PROCEDURES, "satisfiability", _outcome(status=S.UNKNOWN, reason_unknown="incomplete", model={"x": "1"}))
    p = P(make_problem("satisfiability", [("x", "Real"), ("y", "Real")], [("P", cmp("eq", mul(V("x"), V("y")), R(1)))]))
    r = run_policy(p, NONLINEAR)
    assert r.status is S.UNKNOWN and r.witness_model is None and r.counterexample is None
    assert [d.code for d in r.diagnostics] == ["E401"] and r.reason_unknown == "incomplete"


# =========================================================================== adversarial IR under every policy


def _deep(levels: int) -> dict:
    expr: dict = V("x")
    for _ in range(levels):
        expr = {"op": "neg", "arg": expr}
    return expr


def _many_nodes(premises: int) -> dict:
    """``premises`` assertions of 33 nodes each (an ``add`` of 30 symbols under a comparison)."""
    return make_problem("consistency", [("x", "Real")], [(f"Q{i}", cmp("gt", add(*([V("x")] * 30)), R(0))) for i in range(premises)])


BOUNDS: dict[str, tuple[Callable[[], Any], str]] = {
    "10000-digit literal": (lambda: _literal_problem(10_000), "E305"),
    "10000-digit literal in a product": (lambda: make_problem("consistency", [("x", "Real"), ("y", "Real")],
                                                              [("P", cmp("eq", mul(V("x"), V("y")), R("9" * 10_000)))]), "E305"),
    "nesting depth 500 (json text)": (lambda: json.dumps(make_problem("consistency", [("x", "Real")], [("P", cmp("gt", _deep(500), R(0)))])), "E303"),
    "nesting depth 41": (lambda: make_problem("consistency", [("x", "Real")], [("P", cmp("gt", _deep(40), R(0)))]), "E303"),
    "arity 33": (lambda: make_problem("consistency", [("x", "Real")], [("P", cmp("gt", add(*([V("x")] * 33)), R(0)))]), "E304"),
    "65 symbols": (lambda: make_problem("consistency", [(f"x{i}", "Real") for i in range(65)], [("P", cmp("gt", V("x0"), R(0)))]), "E300"),
    "129 premises": (lambda: make_problem("consistency", [("x", "Real")], [(f"P{i}", cmp("gt", V("x"), R(i))) for i in range(129)]), "E301"),
    "2001+ nodes": (lambda: _many_nodes(61), "E302"),  # 61 x 33 = 2013 nodes
}


@pytest.mark.parametrize("case", sorted(BOUNDS))
def test_no_policy_lifts_a_structural_bound(case: str):
    build, code = BOUNDS[case]
    seen = []
    for name in (LINEAR, NONLINEAR):
        payload = build()
        t0 = time.perf_counter()
        r = run_policy(payload, name)
        assert time.perf_counter() - t0 < 2.0
        assert r.status is S.INVALID_FORMALIZATION and code in {d.code for d in r.diagnostics}, (name, r.diagnostics)
        seen.append(sorted({d.code for d in r.diagnostics} - {"E201"}))  # the linear gate may add E201 for a product
    assert seen[0] == seen[1]


BAD_LITERALS = ["1e10", "10^10^10", "1_000", "\u0661\u0662\u0663", "\uff10", "Infinity", "NaN", "0x10", "\u00bd", "1/0", "--1", "+1",
                "1.", ".5", " 1", "1 ", "1.2.3", "2**3", "sqrt(2)", "__import__('os')", "", "\u22121", "1\u20442"]
BAD_IDENTIFIERS = ["\u0445", "\uff58", "x\u200b", "X", "_x", "x-y", "x\u0307", "x\u0301", "1x", "", "x" * 65, "\u0430_0"]
MALFORMED = ['{"problem_id": "p", ', "[[[[", '{"a": [}', "}", "\\frac{1}{", '{"query": "entailment"}' + "}" * 50, "\x00", b"\xff\xfe{", b'{"problem_id": "\xed\xa0\x80"}']


@pytest.mark.parametrize("literal", BAD_LITERALS, ids=[f"lit{i}" for i in range(len(BAD_LITERALS))])
def test_untrusted_literals_are_rejected_without_raising(literal: str):
    raw = make_problem("consistency", [("x", "Real")], [("P", cmp("eq", mul(V("x"), V("x")), {"op": "real", "value": literal}))])
    r = run_policy(raw, NONLINEAR)
    assert r.status is S.INVALID_FORMALIZATION and r.problem_id == "unknown" and not is_definitive(r.status)


@pytest.mark.parametrize("name", BAD_IDENTIFIERS, ids=[f"id{i}" for i in range(len(BAD_IDENTIFIERS))])
def test_confusable_identifiers_are_rejected_without_raising(name: str):
    raw = make_problem("consistency", [(name, "Real")], [("P", cmp("gt", mul(V(name), V(name)), R(0)))])
    r = run_policy(raw, NONLINEAR)
    assert r.status is S.INVALID_FORMALIZATION and "E100" in {d.code for d in r.diagnostics}


@pytest.mark.parametrize("text", MALFORMED, ids=[f"raw{i}" for i in range(len(MALFORMED))])
def test_malformed_payloads_are_rejected_without_raising(text: Any):
    for name in (LINEAR, NONLINEAR):
        r = run_policy(text, name, signing_key=KEY, key_id="k1")
        assert r.status is S.INVALID_FORMALIZATION and verify_signature(r, KEY)
        assert (r.limits is None) == (name == LINEAR)


@pytest.mark.xfail(strict=True, reason=(
    "pre-existing IR schema defect, outside this stage (no IR schema change): IDENT_RE, ASSERTION_ID_RE and the numeric "
    "literal patterns end in '$', which also matches before a trailing newline, so 'x\\n' is accepted as a symbol distinct "
    "from 'x' and '1\\n' as a literal. Fix: anchor with \\Z or use fullmatch; then remove this marker."))
@pytest.mark.parametrize("field", ["identifier", "assertion id", "literal"])
def test_trailing_newline_is_not_part_of_an_identifier_or_literal(field: str):
    name, pid, literal = ("x\n", "P", "1") if field == "identifier" else (("x", "P\n", "1") if field == "assertion id" else ("x", "P", "1\n"))
    raw = make_problem("entailment", [(name, "Real")], [(pid, cmp("eq", V(name), R(literal)))], ("C", cmp("eq", V(name), R(1))))
    r = verify(raw, CFG)
    assert r.status is S.INVALID_FORMALIZATION


def test_a_lone_surrogate_in_a_text_payload_is_never_a_success():
    """Holds today: the payload ends as a non-success result and nothing raises out of verify."""
    for name in (LINEAR, NONLINEAR):
        r = run_policy("\ud800", name, signing_key=KEY, key_id="k1")
        assert not is_definitive(r.status) and r.status in (S.INVALID_FORMALIZATION, S.INTERNAL_ERROR) and verify_signature(r, KEY)


@pytest.mark.xfail(strict=True, reason=(
    "pre-existing validator defect, outside this stage (no validator change): _decode_text encodes a str payload with "
    "UTF-8 and lets UnicodeEncodeError escape parse_and_validate, so a lone surrogate is INTERNAL_ERROR (E900) instead of "
    "INVALID_FORMALIZATION (E100). Fix: catch UnicodeEncodeError there; then remove this marker."))
def test_a_lone_surrogate_in_a_text_payload_is_an_invalid_formalization():
    assert run_policy("\ud800", LINEAR).status is S.INVALID_FORMALIZATION
