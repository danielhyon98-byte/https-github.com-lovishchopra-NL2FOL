"""Deterministic compiler from validated IR v1 problems to Z3 expressions.

The IR is data. This module never evaluates or executes anything from it: every
node is matched against the closed set of IR node classes and mapped to exactly
one Z3 API call. Anything else raises :class:`CompileError`.

Precondition: the problem has passed :func:`epinoic_logic.engine.validator.validate_problem`.
The compiler nevertheless re-checks the allowlist, declared symbols, operand sorts
and the constant-divisor policy (defense in depth), because a wrong Z3 call would
silently change semantics. Two examples the checks guard against:

* ``/`` on Int-sorted Z3 terms is INTEGER division (``div``) and on Real-sorted
  terms is REAL division; the compiler therefore asserts the operand sorts before
  emitting either ``div`` or ``idiv``.
* Numerals are built from their exact textual form (``z3.IntVal(str)``,
  ``z3.RealVal(str)``) so ``"0.1"`` is the rational 1/10, never a binary float.

Every compilation uses the caller-supplied ``z3.Context`` or a fresh one; nothing
touches Z3's global context or global parameters.
"""
from __future__ import annotations

import functools
import operator
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import z3

from ..ir.schema import (
    ALLOWED_OPS,
    Add,
    And,
    Assertion,
    BoolConst,
    Compare,
    Div,
    Iff,
    Implies,
    IntConst,
    IntDiv,
    Ite,
    Mod,
    Mul,
    Neg,
    Not,
    Or,
    Problem,
    RealConst,
    Sub,
    ToReal,
    Var,
)
from .errors import DiagnosticCode
from .results import Diagnostic
from .validator import _valid_int_literal, _valid_real_literal, walk_postorder

__all__ = ["Compiled", "CompileError", "compile_problem", "compile_expr", "to_smt2"]

_MAX_MESSAGE_CHARS = 500


class CompileError(Exception):
    """Raised when a node cannot be compiled; carries a :class:`Diagnostic`."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        location = f" at {diagnostic.path}" if diagnostic.path else ""
        super().__init__(f"{diagnostic.code}: {diagnostic.message}{location}")


@dataclass
class Compiled:
    """Z3 objects for one problem, all living in ``ctx``.

    ``premises`` preserves the order of ``problem.premises``; ``conclusion`` is
    ``None`` unless the problem carries one.
    """

    ctx: z3.Context
    symbols: dict[str, z3.ExprRef]
    premises: dict[str, z3.BoolRef] = field(default_factory=dict)
    conclusion: Optional[z3.BoolRef] = None
    problem: Optional[Problem] = None


def _fail(code: DiagnosticCode, message: str, path: Optional[str]) -> CompileError:
    return CompileError(Diagnostic(code=code.value, message=message[:_MAX_MESSAGE_CHARS], path=path))


# --------------------------------------------------------------------------- #
# Z3 sort predicates
# --------------------------------------------------------------------------- #


def _is_bool(e: z3.ExprRef) -> bool:
    return z3.is_bool(e)


def _is_int(e: z3.ExprRef) -> bool:
    return z3.is_arith(e) and e.is_int()


def _is_real(e: z3.ExprRef) -> bool:
    return z3.is_arith(e) and e.is_real()


def _sort_name(e: z3.ExprRef) -> str:
    if _is_bool(e):
        return "Bool"
    if _is_int(e):
        return "Int"
    if _is_real(e):
        return "Real"
    return str(e.sort())


def _require_bool(op: str, e: z3.ExprRef, path: str) -> z3.BoolRef:
    if not _is_bool(e):
        raise _fail(DiagnosticCode.SORT_MISMATCH, f"{op!r} expects Bool operands, got {_sort_name(e)}", path)
    return e


def _require_numeric(op: str, e: z3.ExprRef, path: str) -> z3.ArithRef:
    if not (_is_int(e) or _is_real(e)):
        raise _fail(DiagnosticCode.SORT_MISMATCH, f"{op!r} expects Int or Real operands, got {_sort_name(e)}", path)
    return e


def _require_same_numeric(op: str, args: list[z3.ExprRef], paths: list[str], node_path: str) -> list[z3.ArithRef]:
    checked = [_require_numeric(op, a, p) for a, p in zip(args, paths)]
    sorts = {_sort_name(a) for a in checked}
    if len(sorts) > 1:
        raise _fail(DiagnosticCode.SORT_MISMATCH, f"{op!r} mixes Int and Real operands; use 'to_real'", node_path)
    return checked


def _require_sort(op: str, e: z3.ExprRef, sort: str, path: str) -> z3.ArithRef:
    if _sort_name(e) != sort:
        raise _fail(DiagnosticCode.SORT_MISMATCH, f"{op!r} expects {sort} operands, got {_sort_name(e)}", path)
    return e


def _require_nonzero_literal(op: str, divisor: z3.ExprRef, sort: str, path: str) -> None:
    """Policy v1: divisors are non-zero numerals of the operand sort."""
    is_literal = z3.is_int_value(divisor) if sort == "Int" else z3.is_rational_value(divisor)
    if not is_literal:
        raise _fail(DiagnosticCode.NONCONSTANT_DIVISOR, f"{op!r} requires a non-zero {sort} literal as divisor", path)
    zero = divisor.as_long() == 0 if sort == "Int" else divisor.numerator_as_long() == 0
    if zero:
        raise _fail(DiagnosticCode.ZERO_DIVISOR, f"{op!r} divisor is zero", path)


# --------------------------------------------------------------------------- #
# Node compilation
# --------------------------------------------------------------------------- #

_COMPARE_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
}


def _compile_leaf(node: Any, path: str, symbols: dict[str, z3.ExprRef], ctx: z3.Context) -> z3.ExprRef:
    if isinstance(node, Var):
        value = symbols.get(node.name)
        if value is None:
            raise _fail(DiagnosticCode.UNDECLARED_SYMBOL, f"symbol {node.name!r} is not declared", path)
        return value
    if isinstance(node, BoolConst):
        if not isinstance(node.value, bool):
            raise _fail(DiagnosticCode.BAD_LITERAL, "bool literal must be true or false", path)
        return z3.BoolVal(node.value, ctx)
    if isinstance(node, IntConst):
        if not _valid_int_literal(node.value):
            raise _fail(DiagnosticCode.BAD_LITERAL, "int literal must be exact decimal integer text", path)
        return z3.IntVal(node.value, ctx)
    if isinstance(node, RealConst):
        if not _valid_real_literal(node.value):
            raise _fail(DiagnosticCode.BAD_LITERAL, "real literal must be integer, fraction a/b or decimal text", path)
        return z3.RealVal(node.value, ctx)
    raise _fail(DiagnosticCode.UNKNOWN_OPERATOR, f"operator {getattr(node, 'op', type(node).__name__)!r} is not in the allowlist", path)


def _compile_boolean(node: Any, path: str, kids: list[z3.ExprRef], kid_paths: list[str], ctx: z3.Context) -> z3.BoolRef:
    bools = [_require_bool(node.op, k, p) for k, p in zip(kids, kid_paths)]
    if isinstance(node, Not):
        return z3.Not(bools[0], ctx)
    if isinstance(node, And):
        return z3.And(*bools, ctx)
    if isinstance(node, Or):
        return z3.Or(*bools, ctx)
    if isinstance(node, Implies):
        return z3.Implies(bools[0], bools[1], ctx)
    # Iff: Z3 equality on Bool terms is Boolean equivalence.
    return bools[0] == bools[1]


def _compile_ite(node: Ite, path: str, kids: list[z3.ExprRef], kid_paths: list[str], ctx: z3.Context) -> z3.ExprRef:
    cond = _require_bool("ite", kids[0], kid_paths[0])
    then, otherwise = kids[1], kids[2]
    if _sort_name(then) != _sort_name(otherwise):
        raise _fail(DiagnosticCode.SORT_MISMATCH, f"'ite' branches have different sorts ({_sort_name(then)} vs {_sort_name(otherwise)})", path)
    return z3.If(cond, then, otherwise, ctx)


def _compile_arith(node: Any, path: str, kids: list[z3.ExprRef], kid_paths: list[str]) -> z3.ArithRef:
    args = _require_same_numeric(node.op, kids, kid_paths, path)
    if isinstance(node, Add):
        return functools.reduce(operator.add, args)
    if isinstance(node, Mul):
        return functools.reduce(operator.mul, args)
    if isinstance(node, Sub):
        return args[0] - args[1]
    # Neg
    return -args[0]


def _compile_division(node: Any, path: str, kids: list[z3.ExprRef], kid_paths: list[str]) -> z3.ArithRef:
    sort = "Real" if isinstance(node, Div) else "Int"
    left = _require_sort(node.op, kids[0], sort, kid_paths[0])
    right = _require_sort(node.op, kids[1], sort, kid_paths[1])
    _require_nonzero_literal(node.op, right, sort, kid_paths[1])
    if isinstance(node, Mod):
        return left % right
    # z3py: '/' on Int terms builds (div a b); on Real terms builds (/ a b).
    return left / right


def _compile_to_real(node: ToReal, kids: list[z3.ExprRef], kid_paths: list[str]) -> z3.ArithRef:
    arg = _require_sort("to_real", kids[0], "Int", kid_paths[0])
    return z3.ToReal(arg)


def _compile_compare(node: Compare, path: str, kids: list[z3.ExprRef], kid_paths: list[str]) -> z3.BoolRef:
    for kid, kid_path in zip(kids, kid_paths):
        if _is_bool(kid):
            raise _fail(DiagnosticCode.SORT_MISMATCH, f"{node.op!r} compares numbers; use 'iff' for Boolean equivalence", kid_path)
    left, right = _require_same_numeric(node.op, kids, kid_paths, path)
    fn = _COMPARE_OPS.get(node.op)
    if fn is None:
        raise _fail(DiagnosticCode.UNKNOWN_OPERATOR, f"comparison {node.op!r} is not in the allowlist", path)
    return fn(left, right)


def _compile_node(
    node: Any,
    path: str,
    kids: list[z3.ExprRef],
    kid_paths: list[str],
    symbols: dict[str, z3.ExprRef],
    ctx: z3.Context,
) -> z3.ExprRef:
    """Map one IR node (whose children are already compiled) to one Z3 term."""
    if getattr(node, "op", None) not in ALLOWED_OPS:
        raise _fail(DiagnosticCode.UNKNOWN_OPERATOR, f"operator {getattr(node, 'op', type(node).__name__)!r} is not in the allowlist", path)
    if isinstance(node, (Var, BoolConst, IntConst, RealConst)):
        return _compile_leaf(node, path, symbols, ctx)
    if isinstance(node, (Not, And, Or, Implies, Iff)):
        return _compile_boolean(node, path, kids, kid_paths, ctx)
    if isinstance(node, Ite):
        return _compile_ite(node, path, kids, kid_paths, ctx)
    if isinstance(node, (Add, Mul, Sub, Neg)):
        return _compile_arith(node, path, kids, kid_paths)
    if isinstance(node, (Div, IntDiv, Mod)):
        return _compile_division(node, path, kids, kid_paths)
    if isinstance(node, ToReal):
        return _compile_to_real(node, kids, kid_paths)
    if isinstance(node, Compare):
        return _compile_compare(node, path, kids, kid_paths)
    raise _fail(DiagnosticCode.UNKNOWN_OPERATOR, f"node type {type(node).__name__!r} is not compilable", path)


def compile_expr(expr: Any, symbols: dict[str, z3.ExprRef], ctx: z3.Context, path: str = "expr") -> z3.ExprRef:
    """Compile one IR expression to a Z3 term in ``ctx`` (iteratively, post-order).

    Raises :class:`CompileError` for unknown nodes, undeclared symbols, sort
    mismatches, bad literals and policy violations.
    """
    built: dict[str, z3.ExprRef] = {}
    for node, node_path, _depth, kid_paths in walk_postorder(expr, path):
        kids = [built.pop(kid_path) for kid_path in kid_paths]
        built[node_path] = _compile_node(node, node_path, kids, kid_paths, symbols, ctx)
    return built[path]


# --------------------------------------------------------------------------- #
# Problem compilation
# --------------------------------------------------------------------------- #

_SORT_CONSTRUCTORS: dict[str, Callable[[str, z3.Context], z3.ExprRef]] = {
    "Bool": lambda name, ctx: z3.Bool(name, ctx),
    "Int": lambda name, ctx: z3.Int(name, ctx),
    "Real": lambda name, ctx: z3.Real(name, ctx),
}


def _declare_symbols(problem: Problem, ctx: z3.Context) -> dict[str, z3.ExprRef]:
    symbols: dict[str, z3.ExprRef] = {}
    for index, symbol in enumerate(problem.symbols):
        constructor = _SORT_CONSTRUCTORS.get(symbol.sort)
        if constructor is None:
            raise _fail(DiagnosticCode.SCHEMA_VIOLATION, f"unknown sort {symbol.sort!r}", f"symbols[{index}].sort")
        if symbol.name in symbols:
            raise _fail(DiagnosticCode.DUPLICATE_IDENTIFIER, f"symbol {symbol.name!r} declared more than once", f"symbols[{index}].name")
        symbols[symbol.name] = constructor(symbol.name, ctx)
    return symbols


def _compile_assertion(assertion: Assertion, base: str, symbols: dict[str, z3.ExprRef], ctx: z3.Context) -> z3.BoolRef:
    expr_path = f"{base}.expr"
    term = compile_expr(assertion.expr, symbols, ctx, expr_path)
    if not _is_bool(term):
        raise _fail(DiagnosticCode.NON_BOOLEAN_ASSERTION, f"assertion must be Bool, got {_sort_name(term)}", expr_path)
    return term


def compile_problem(problem: Problem, ctx: Optional[z3.Context] = None) -> Compiled:
    """Compile a VALIDATED problem into Z3 terms in a fresh (or supplied) context.

    Raises :class:`CompileError` on anything unexpected; unexpected exceptions
    from Z3 or elsewhere are wrapped as ``E900`` so callers never see raw errors.
    """
    context = ctx if ctx is not None else z3.Context()
    try:
        symbols = _declare_symbols(problem, context)
        premises: dict[str, z3.BoolRef] = {}
        for index, assertion in enumerate(problem.premises):
            base = f"premises[{index}]"
            if assertion.id in premises:
                raise _fail(DiagnosticCode.DUPLICATE_IDENTIFIER, f"assertion id {assertion.id!r} used more than once", f"{base}.id")
            premises[assertion.id] = _compile_assertion(assertion, base, symbols, context)
        conclusion: Optional[z3.BoolRef] = None
        if problem.conclusion is not None:
            if problem.conclusion.id in premises:
                raise _fail(DiagnosticCode.DUPLICATE_IDENTIFIER, f"assertion id {problem.conclusion.id!r} used more than once", "conclusion.id")
            conclusion = _compile_assertion(problem.conclusion, "conclusion", symbols, context)
    except CompileError:
        raise
    except Exception as exc:  # defense in depth: never leak raw solver errors
        raise _fail(DiagnosticCode.INTERNAL, f"compilation failed: {type(exc).__name__}", None) from exc
    return Compiled(ctx=context, symbols=symbols, premises=premises, conclusion=conclusion, problem=problem)


def to_smt2(compiled: Compiled, negate_conclusion: bool = False) -> str:
    """Exact SMT-LIB 2 text of the premises (and optionally the negated conclusion).

    Uses a throwaway solver in the compiled context; nothing is checked. Raises
    ``ValueError`` when ``negate_conclusion`` is requested without a conclusion.
    """
    if negate_conclusion and compiled.conclusion is None:
        raise ValueError("problem has no conclusion to negate")
    solver = z3.Solver(ctx=compiled.ctx)
    for premise in compiled.premises.values():
        solver.add(premise)
    if negate_conclusion:
        solver.add(z3.Not(compiled.conclusion, compiled.ctx))
    return solver.to_smt2()
