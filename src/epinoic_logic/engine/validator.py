"""Deterministic validator for IR v1 problems.

The validator runs BEFORE compilation and decides whether a ``Problem`` may be
handed to the compiler at all. It is pure data processing: nothing in the IR is
ever executed, and every expression node is inspected one by one against the
closed operator allowlist in :mod:`epinoic_logic.ir.schema`.

Responsibilities
----------------
* Parse untrusted JSON into a ``Problem`` (``parse_and_validate``), rejecting
  oversized payloads, non-object documents, duplicate keys, non-finite numbers,
  unknown operators and unapproved fields (surfaced as ``E100`` with the pydantic
  location path), and nesting the parser cannot handle (``E303``).
* Check identifiers, sorts, policy and limits (``validate_problem``), collecting
  ALL diagnostics rather than stopping at the first.
* Infer the sort of an expression (``infer_sort``) with strict rules: no implicit
  coercion between Int and Real (``to_real`` is the only conversion), Boolean
  connectives take Bool, comparisons take two operands of the same numeric sort.

Status mapping: any ``E1xx`` or ``E3xx`` diagnostic yields
``INVALID_FORMALIZATION``; only ``E2xx`` diagnostics yield ``UNSUPPORTED``; when
both kinds appear ``INVALID_FORMALIZATION`` wins.

All traversals are iterative so that adversarially deep expressions can never
exhaust the Python stack. Diagnostic paths look like ``premises[2].expr.args[0]``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Iterator, Optional, Sequence, Union

from pydantic import ValidationError

from ..ir.schema import (
    ALLOWED_OPS,
    ASSERTION_ID_RE,
    DECIMAL_RE,
    DEFAULT_LIMITS,
    IDENT_RE,
    INT_RE,
    RATIONAL_RE,
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
    Limits,
    Mod,
    Mul,
    Neg,
    Not,
    Or,
    Problem,
    RealConst,
    Sort,
    Sub,
    ToReal,
    Var,
)
from ..ir.canonical import strict_object_pairs
from ..version import IR_VERSION
from .errors import DiagnosticCode
from .results import Diagnostic
from .statuses import VerificationStatus

__all__ = [
    "ValidationOutcome",
    "SortError",
    "validate_problem",
    "parse_and_validate",
    "infer_sort",
    "walk_postorder",
    "children_of",
    "NUMERIC_SORTS",
    "DEFAULT_MAX_BYTES",
]

NUMERIC_SORTS: frozenset[str] = frozenset({"Int", "Real"})
DEFAULT_MAX_BYTES = 1_000_000
_MAX_MESSAGE_CHARS = 500

# Node classes that carry child expressions in single fields, in positional order.
_SINGLE_CHILD_FIELDS: dict[type, tuple[str, ...]] = {
    Not: ("arg",),
    Neg: ("arg",),
    ToReal: ("arg",),
    Implies: ("left", "right"),
    Iff: ("left", "right"),
    Sub: ("left", "right"),
    Div: ("left", "right"),
    IntDiv: ("left", "right"),
    Mod: ("left", "right"),
    Compare: ("left", "right"),
    Ite: ("cond", "then", "otherwise"),
}
_NARY_TYPES: tuple[type, ...] = (And, Or, Add, Mul)
_LEAF_TYPES: tuple[type, ...] = (Var, BoolConst, IntConst, RealConst)
_NODE_TYPES: tuple[type, ...] = _LEAF_TYPES + _NARY_TYPES + tuple(_SINGLE_CHILD_FIELDS)
# Fields whose value is an expression; used to recognise union tags in pydantic locs.
_EXPR_FIELDS: frozenset[str] = frozenset({"expr", "arg", "left", "right", "cond", "then", "otherwise"})


class SortError(Exception):
    """Raised by :func:`infer_sort` on the first sort, identifier or policy problem.

    The offending :class:`Diagnostic` is available as ``.diagnostic``.
    """

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        location = f" at {diagnostic.path}" if diagnostic.path else ""
        super().__init__(f"{diagnostic.code}: {diagnostic.message}{location}")


@dataclass
class ValidationOutcome:
    """Result of validating a problem.

    ``ok`` is True only when there are no diagnostics at all. ``status`` is
    ``None`` when ok, otherwise ``INVALID_FORMALIZATION`` or ``UNSUPPORTED``.
    ``sorts`` maps each assertion id whose sort could be inferred to that sort;
    all of them must be ``Bool`` for the problem to be ok.
    """

    ok: bool
    status: Optional[VerificationStatus]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    node_count: int = 0
    max_depth: int = 0
    sorts: dict[str, Sort] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Expression traversal (shared with the compiler)
# --------------------------------------------------------------------------- #


def children_of(node: Any, path: str) -> list[tuple[str, Any]]:
    """Return ``(child_path, child_node)`` pairs of ``node`` in positional order.

    Unknown node types have no children; the caller reports them as ``E200``.
    """
    if isinstance(node, _NARY_TYPES):
        return [(f"{path}.args[{i}]", child) for i, child in enumerate(node.args)]
    fields = _SINGLE_CHILD_FIELDS.get(type(node))
    if fields is None:
        return []
    return [(f"{path}.{name}", getattr(node, name)) for name in fields]


def walk_postorder(expr: Any, path: str) -> Iterator[tuple[Any, str, int, list[str]]]:
    """Iteratively yield ``(node, path, depth, child_paths)`` in post-order.

    The root has depth 1. Children are always yielded before their parent, so a
    consumer can keep per-path results in a dictionary and combine them when the
    parent arrives. No recursion is used, so arbitrarily deep input is safe.
    """
    stack: list[tuple[Any, str, int, bool]] = [(expr, path, 1, False)]
    while stack:
        node, node_path, depth, expanded = stack.pop()
        kids = children_of(node, node_path)
        if expanded:
            yield node, node_path, depth, [child_path for child_path, _ in kids]
            continue
        stack.append((node, node_path, depth, True))
        for child_path, child in reversed(kids):
            stack.append((child, child_path, depth + 1, False))


def _is_closed_term(expr: Any) -> bool:
    """True when the expression contains no ``var`` node (a constant term)."""
    for node, _path, _depth, _kids in walk_postorder(expr, "t"):
        if isinstance(node, Var):
            return False
    return True


# --------------------------------------------------------------------------- #
# Literal helpers
# --------------------------------------------------------------------------- #


def _digit_count(text: str) -> int:
    return sum(1 for ch in text if ch.isdigit())


def _literal_is_zero(text: str) -> Optional[bool]:
    """Exact zero test for a numeric literal; ``None`` when the text is not a literal."""
    try:
        return Fraction(text) == 0
    except (ValueError, ZeroDivisionError):
        return None


def _valid_int_literal(text: Any) -> bool:
    return isinstance(text, str) and INT_RE.fullmatch(text) is not None


def _valid_real_literal(text: Any) -> bool:
    return isinstance(text, str) and (
        INT_RE.fullmatch(text) is not None
        or RATIONAL_RE.fullmatch(text) is not None
        or DECIMAL_RE.fullmatch(text) is not None
    )


# --------------------------------------------------------------------------- #
# Sort inference with diagnostic collection
# --------------------------------------------------------------------------- #


class _Checker:
    """Infers sorts and records every diagnostic found along the way.

    A ``None`` sort means "an error was already reported below this node"; checks
    involving an unknown operand sort are skipped so one mistake does not cascade
    into many diagnostics.
    """

    def __init__(self, symbols: dict[str, Sort], limits: Limits, diagnostics: list[Diagnostic]) -> None:
        self.symbols = symbols
        self.limits = limits
        self.diagnostics = diagnostics

    # -- bookkeeping -------------------------------------------------------- #

    def _report(self, code: DiagnosticCode, message: str, path: str) -> None:
        self.diagnostics.append(Diagnostic(code=code.value, message=message[:_MAX_MESSAGE_CHARS], path=path))

    def infer(self, expr: Any, path: str) -> tuple[Optional[Sort], int, int]:
        """Return ``(sort_or_None, node_count, max_depth)`` for ``expr``."""
        sorts: dict[str, Optional[Sort]] = {}
        count = 0
        max_depth = 0
        for node, node_path, depth, child_paths in walk_postorder(expr, path):
            count += 1
            max_depth = max(max_depth, depth)
            child_sorts = [sorts.pop(child_path) for child_path in child_paths]
            sorts[node_path] = self._node_sort(node, node_path, child_paths, child_sorts)
        return sorts[path], count, max_depth

    # -- dispatch ----------------------------------------------------------- #

    def _node_sort(
        self, node: Any, path: str, child_paths: list[str], child_sorts: list[Optional[Sort]]
    ) -> Optional[Sort]:
        if not isinstance(node, _NODE_TYPES) or getattr(node, "op", None) not in ALLOWED_OPS:
            op = getattr(node, "op", type(node).__name__)
            self._report(DiagnosticCode.UNKNOWN_OPERATOR, f"operator {op!r} is not in the IR v1 allowlist", path)
            return None
        if isinstance(node, Var):
            return self._var(node, path)
        if isinstance(node, BoolConst):
            return "Bool"
        if isinstance(node, IntConst):
            return self._int_const(node, path)
        if isinstance(node, RealConst):
            return self._real_const(node, path)
        if isinstance(node, Not):
            self._expect_bool(node.op, child_paths[0], child_sorts[0])
            return "Bool"
        if isinstance(node, (And, Or)):
            self._check_arity(node, path)
            for child_path, child_sort in zip(child_paths, child_sorts):
                self._expect_bool(node.op, child_path, child_sort)
            return "Bool"
        if isinstance(node, (Implies, Iff)):
            for child_path, child_sort in zip(child_paths, child_sorts):
                self._expect_bool(node.op, child_path, child_sort)
            return "Bool"
        if isinstance(node, Ite):
            return self._ite(node, path, child_paths, child_sorts)
        if isinstance(node, (Add, Mul)):
            return self._nary_arith(node, path, child_paths, child_sorts)
        if isinstance(node, Sub):
            return self._same_numeric(node.op, path, child_paths, child_sorts)
        if isinstance(node, Neg):
            return self._numeric_operand(node.op, child_paths[0], child_sorts[0])
        if isinstance(node, Div):
            return self._real_division(node, path, child_paths, child_sorts)
        if isinstance(node, (IntDiv, Mod)):
            return self._int_division(node, path, child_paths, child_sorts)
        if isinstance(node, ToReal):
            return self._to_real(child_paths[0], child_sorts[0])
        if isinstance(node, Compare):
            self._compare(node, path, child_paths, child_sorts)
            return "Bool"
        self._report(DiagnosticCode.UNKNOWN_OPERATOR, f"operator {node.op!r} has no sort rule", path)  # pragma: no cover
        return None

    # -- leaves ------------------------------------------------------------- #

    def _var(self, node: Var, path: str) -> Optional[Sort]:
        sort = self.symbols.get(node.name)
        if sort is None:
            self._report(DiagnosticCode.UNDECLARED_SYMBOL, f"symbol {node.name!r} is not declared", path)
            return None
        return sort

    def _int_const(self, node: IntConst, path: str) -> Optional[Sort]:
        if not _valid_int_literal(node.value):
            self._report(DiagnosticCode.BAD_LITERAL, "int literal must be exact decimal integer text", path)
            return None
        self._check_digits(node.value, path)
        return "Int"

    def _real_const(self, node: RealConst, path: str) -> Optional[Sort]:
        if not _valid_real_literal(node.value):
            self._report(DiagnosticCode.BAD_LITERAL, "real literal must be integer, fraction a/b or decimal text", path)
            return None
        self._check_digits(node.value, path)
        return "Real"

    def _check_digits(self, text: str, path: str) -> None:
        digits = _digit_count(text)
        if digits > self.limits.max_const_digits:
            self._report(
                DiagnosticCode.LITERAL_TOO_LONG,
                f"numeric literal has {digits} digits; limit is {self.limits.max_const_digits}",
                path,
            )

    # -- shared operand checks --------------------------------------------- #

    def _expect_bool(self, op: str, child_path: str, child_sort: Optional[Sort]) -> None:
        if child_sort is not None and child_sort != "Bool":
            self._report(DiagnosticCode.SORT_MISMATCH, f"{op!r} expects Bool operands, got {child_sort}", child_path)

    def _numeric_operand(self, op: str, child_path: str, child_sort: Optional[Sort]) -> Optional[Sort]:
        if child_sort is None:
            return None
        if child_sort not in NUMERIC_SORTS:
            self._report(DiagnosticCode.SORT_MISMATCH, f"{op!r} expects Int or Real operands, got {child_sort}", child_path)
            return None
        return child_sort

    def _same_numeric(
        self, op: str, path: str, child_paths: list[str], child_sorts: list[Optional[Sort]]
    ) -> Optional[Sort]:
        """All operands numeric and of one sort; returns that sort or ``None``."""
        known = [self._numeric_operand(op, cp, cs) for cp, cs in zip(child_paths, child_sorts)]
        if any(sort is None for sort in known):
            return None
        distinct = set(known)
        if len(distinct) > 1:
            self._report(
                DiagnosticCode.SORT_MISMATCH,
                f"{op!r} mixes Int and Real operands; convert Int operands explicitly with 'to_real'",
                path,
            )
            return None
        return known[0]

    def _check_arity(self, node: Any, path: str) -> None:
        if len(node.args) > self.limits.max_nary_args:
            self._report(
                DiagnosticCode.TOO_MANY_ARGS,
                f"{node.op!r} has {len(node.args)} arguments; limit is {self.limits.max_nary_args}",
                path,
            )

    # -- compound nodes ----------------------------------------------------- #

    def _ite(self, node: Ite, path: str, child_paths: list[str], child_sorts: list[Optional[Sort]]) -> Optional[Sort]:
        self._expect_bool("ite", child_paths[0], child_sorts[0])
        then_sort, else_sort = child_sorts[1], child_sorts[2]
        if then_sort is None or else_sort is None:
            return None
        if then_sort != else_sort:
            self._report(
                DiagnosticCode.SORT_MISMATCH,
                f"'ite' branches have different sorts ({then_sort} vs {else_sort})",
                path,
            )
            return None
        return then_sort

    def _nary_arith(
        self, node: Union[Add, Mul], path: str, child_paths: list[str], child_sorts: list[Optional[Sort]]
    ) -> Optional[Sort]:
        self._check_arity(node, path)
        sort = self._same_numeric(node.op, path, child_paths, child_sorts)
        if isinstance(node, Mul) and not self.limits.allow_nonlinear:
            non_constant = sum(1 for factor in node.args if not _is_closed_term(factor))
            if non_constant >= 2:
                self._report(
                    DiagnosticCode.NONLINEAR_TERM,
                    f"'mul' has {non_constant} non-constant factors; only linear arithmetic is supported",
                    path,
                )
        return sort

    def _real_division(
        self, node: Div, path: str, child_paths: list[str], child_sorts: list[Optional[Sort]]
    ) -> Optional[Sort]:
        if not self.limits.allow_real_division:
            self._report(DiagnosticCode.THEORY_UNSUPPORTED, "real division ('div') is disabled by policy", path)
        left_sort, right_sort = child_sorts
        if left_sort is not None and left_sort != "Real":
            self._report(
                DiagnosticCode.SORT_MISMATCH,
                f"'div' expects Real operands, got {left_sort}; use 'idiv' for integers or 'to_real'",
                child_paths[0],
            )
        self._check_constant_divisor(node.right, "div", RealConst, "Real", child_paths[1], right_sort)
        return "Real"

    def _int_division(
        self, node: Union[IntDiv, Mod], path: str, child_paths: list[str], child_sorts: list[Optional[Sort]]
    ) -> Optional[Sort]:
        if not self.limits.allow_int_division:
            self._report(DiagnosticCode.THEORY_UNSUPPORTED, f"integer division ({node.op!r}) is disabled by policy", path)
        left_sort, right_sort = child_sorts
        if left_sort is not None and left_sort != "Int":
            self._report(
                DiagnosticCode.SORT_MISMATCH,
                f"{node.op!r} expects Int operands, got {left_sort}; use 'div' for reals",
                child_paths[0],
            )
        self._check_constant_divisor(node.right, node.op, IntConst, "Int", child_paths[1], right_sort)
        return "Int"

    def _check_constant_divisor(
        self,
        divisor: Any,
        op: str,
        const_type: type,
        sort_name: str,
        divisor_path: str,
        divisor_sort: Optional[Sort],
    ) -> None:
        """Policy v1: the divisor must be a non-zero literal of the operand sort."""
        if not isinstance(divisor, const_type):
            if divisor_sort is None:
                return
            if divisor_sort == sort_name:
                self._report(
                    DiagnosticCode.NONCONSTANT_DIVISOR,
                    f"{op!r} requires a non-zero {sort_name} literal as divisor",
                    divisor_path,
                )
            else:
                self._report(
                    DiagnosticCode.SORT_MISMATCH,
                    f"{op!r} expects a {sort_name} divisor, got {divisor_sort}",
                    divisor_path,
                )
            return
        if _literal_is_zero(divisor.value) is True:
            self._report(DiagnosticCode.ZERO_DIVISOR, f"{op!r} divisor is zero", divisor_path)

    def _to_real(self, child_path: str, child_sort: Optional[Sort]) -> Optional[Sort]:
        if child_sort is not None and child_sort != "Int":
            self._report(DiagnosticCode.SORT_MISMATCH, f"'to_real' expects an Int operand, got {child_sort}", child_path)
            return None if child_sort == "Bool" else "Real"
        return "Real"

    def _compare(self, node: Compare, path: str, child_paths: list[str], child_sorts: list[Optional[Sort]]) -> None:
        if "Bool" in child_sorts:
            for child_path, child_sort in zip(child_paths, child_sorts):
                if child_sort == "Bool":
                    self._report(
                        DiagnosticCode.SORT_MISMATCH,
                        f"{node.op!r} compares numbers; use 'iff' (or 'not'/'iff') for Boolean equivalence",
                        child_path,
                    )
            return
        self._same_numeric(node.op, path, child_paths, child_sorts)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def infer_sort(expr: Any, symbols: dict[str, Sort], *, limits: Limits = DEFAULT_LIMITS) -> Sort:
    """Infer the sort of ``expr`` under the declared ``symbols``.

    Raises :class:`SortError` carrying the first diagnostic (undeclared symbol,
    sort mismatch, bad literal, unsupported construct or policy violation).
    """
    diagnostics: list[Diagnostic] = []
    sort, _count, _depth = _Checker(symbols, limits, diagnostics).infer(expr, "expr")
    if diagnostics:
        raise SortError(diagnostics[0])
    if sort is None:  # pragma: no cover - defensive; an unknown sort always carries a diagnostic
        raise SortError(Diagnostic(code=DiagnosticCode.INTERNAL.value, message="sort could not be inferred", path="expr"))
    return sort


def _status_for(diagnostics: Sequence[Diagnostic]) -> Optional[VerificationStatus]:
    """E1xx/E3xx -> INVALID_FORMALIZATION; only E2xx -> UNSUPPORTED; none -> None."""
    if not diagnostics:
        return None
    codes = {d.code for d in diagnostics}
    if any(not code.startswith("E2") for code in codes):
        return VerificationStatus.INVALID_FORMALIZATION
    return VerificationStatus.UNSUPPORTED


def _diag(code: DiagnosticCode, message: str, path: Optional[str]) -> Diagnostic:
    return Diagnostic(code=code.value, message=message[:_MAX_MESSAGE_CHARS], path=path)


def _check_header(problem: Problem, limits: Limits, diagnostics: list[Diagnostic]) -> None:
    if problem.ir_version != IR_VERSION:
        diagnostics.append(
            _diag(DiagnosticCode.UNSUPPORTED_IR_VERSION, f"ir_version {problem.ir_version!r} is not supported; expected {IR_VERSION!r}", "ir_version")
        )
    if len(problem.symbols) > limits.max_symbols:
        diagnostics.append(
            _diag(DiagnosticCode.TOO_MANY_SYMBOLS, f"{len(problem.symbols)} symbols declared; limit is {limits.max_symbols}", "symbols")
        )
    if len(problem.premises) > limits.max_premises:
        diagnostics.append(
            _diag(DiagnosticCode.TOO_MANY_PREMISES, f"{len(problem.premises)} premises; limit is {limits.max_premises}", "premises")
        )
    if problem.query == "entailment" and problem.conclusion is None:
        diagnostics.append(_diag(DiagnosticCode.MISSING_CONCLUSION, "entailment query requires a conclusion", "conclusion"))
    if problem.query != "entailment" and problem.conclusion is not None:
        diagnostics.append(
            _diag(DiagnosticCode.UNEXPECTED_CONCLUSION, f"{problem.query} query must not carry a conclusion", "conclusion")
        )


def _symbol_table(problem: Problem, diagnostics: list[Diagnostic]) -> dict[str, Sort]:
    symbols: dict[str, Sort] = {}
    for index, symbol in enumerate(problem.symbols):
        path = f"symbols[{index}].name"
        if not isinstance(symbol.name, str) or not IDENT_RE.fullmatch(symbol.name):
            diagnostics.append(_diag(DiagnosticCode.SCHEMA_VIOLATION, "symbol name is not a valid identifier", path))
            continue
        if symbol.sort not in ("Bool", "Int", "Real"):
            diagnostics.append(_diag(DiagnosticCode.SCHEMA_VIOLATION, f"unknown sort {symbol.sort!r}", f"symbols[{index}].sort"))
            continue
        if symbol.name in symbols:
            diagnostics.append(_diag(DiagnosticCode.DUPLICATE_IDENTIFIER, f"symbol {symbol.name!r} declared more than once", path))
            continue
        symbols[symbol.name] = symbol.sort
    return symbols


def _assertions(problem: Problem) -> list[tuple[str, Assertion]]:
    items = [(f"premises[{i}]", assertion) for i, assertion in enumerate(problem.premises)]
    if problem.conclusion is not None:
        items.append(("conclusion", problem.conclusion))
    return items


def _mentions_symbol(expr: Any) -> bool:
    """True when ``expr`` contains at least one ``var`` node (iterative walk; no recursion)."""
    stack = [expr]
    while stack:
        node = stack.pop()
        op = getattr(node, "op", None)
        if op == "var":
            return True
        for name in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(node, name, None)
            if child is not None:
                stack.append(child)
        stack.extend(getattr(node, "args", None) or [])
    return False


def validate_problem(problem: Problem, limits: Limits = DEFAULT_LIMITS) -> ValidationOutcome:
    """Validate a schema-conformant ``Problem`` against identifier, sort, policy and limit rules.

    Collects every diagnostic it can find. The outcome is ``ok`` only when the
    diagnostic list is empty; the compiler must never be called otherwise.
    """
    diagnostics: list[Diagnostic] = []
    _check_header(problem, limits, diagnostics)
    symbols = _symbol_table(problem, diagnostics)
    checker = _Checker(symbols, limits, diagnostics)

    seen_ids: set[str] = set()
    sorts: dict[str, Sort] = {}
    total_nodes = 0
    deepest = 0
    for base, assertion in _assertions(problem):
        if not isinstance(assertion.id, str) or not ASSERTION_ID_RE.fullmatch(assertion.id):
            diagnostics.append(_diag(DiagnosticCode.SCHEMA_VIOLATION, "assertion id is not valid", f"{base}.id"))
        elif assertion.id in seen_ids:
            diagnostics.append(_diag(DiagnosticCode.DUPLICATE_IDENTIFIER, f"assertion id {assertion.id!r} used more than once", f"{base}.id"))
        seen_ids.add(assertion.id)

        expr_path = f"{base}.expr"
        sort, count, depth = checker.infer(assertion.expr, expr_path)
        total_nodes += count
        deepest = max(deepest, depth)
        if depth > limits.max_depth:
            diagnostics.append(_diag(DiagnosticCode.TOO_DEEP, f"expression depth {depth} exceeds max_depth {limits.max_depth}", expr_path))
        if sort is not None:
            sorts[assertion.id] = sort
            if sort != "Bool":
                diagnostics.append(_diag(DiagnosticCode.NON_BOOLEAN_ASSERTION, f"assertion must be Bool, got {sort}", expr_path))

    if total_nodes > limits.max_nodes:
        diagnostics.append(_diag(DiagnosticCode.TOO_MANY_NODES, f"problem has {total_nodes} expression nodes; limit is {limits.max_nodes}", None))
    if problem.conclusion is not None and not _mentions_symbol(problem.conclusion.expr):
        diagnostics.append(_diag(
            DiagnosticCode.CLOSED_CONCLUSION,
            "conclusion is a closed term that mentions no declared symbol: it is a tautology or a contradiction, not a claim about the encoded premises",
            "conclusion.expr",
        ))

    status = _status_for(diagnostics)
    return ValidationOutcome(
        ok=status is None,
        status=status,
        diagnostics=diagnostics,
        node_count=total_nodes,
        max_depth=deepest,
        sorts=sorts,
    )


# --------------------------------------------------------------------------- #
# JSON parsing
# --------------------------------------------------------------------------- #


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON number {name} is not allowed")


_strict_pairs = strict_object_pairs  # shared with the service envelope and provider-output parsers


def _failed(diagnostics: list[Diagnostic]) -> ValidationOutcome:
    return ValidationOutcome(ok=False, status=_status_for(diagnostics), diagnostics=diagnostics)


def _decode_text(raw: Union[bytes, str], max_bytes: int, diagnostics: list[Diagnostic]) -> Optional[str]:
    """Enforce the byte budget and decode UTF-8; returns ``None`` after recording a diagnostic."""
    if isinstance(raw, bytes):
        if len(raw) > max_bytes:
            diagnostics.append(_diag(DiagnosticCode.PAYLOAD_TOO_LARGE, f"payload is {len(raw)} bytes; limit is {max_bytes}", None))
            return None
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            diagnostics.append(_diag(DiagnosticCode.SCHEMA_VIOLATION, "payload is not valid UTF-8", None))
            return None
    try:
        size = len(raw.encode("utf-8"))
    except UnicodeEncodeError:
        # a lone surrogate (a str that is not valid Unicode text): an invalid payload, never an internal error
        diagnostics.append(_diag(DiagnosticCode.SCHEMA_VIOLATION, "payload contains a lone surrogate: it is not valid Unicode text", None))
        return None
    if size > max_bytes:
        diagnostics.append(_diag(DiagnosticCode.PAYLOAD_TOO_LARGE, f"payload is {size} bytes; limit is {max_bytes}", None))
        return None
    return raw


def _load_object(raw: Union[bytes, str, dict], max_bytes: int, diagnostics: list[Diagnostic]) -> Optional[dict]:
    """Turn raw input into a JSON object (dict) or record why it cannot be."""
    if isinstance(raw, dict):
        try:
            size = len(json.dumps(raw, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8"))
        except RecursionError:
            diagnostics.append(_diag(DiagnosticCode.TOO_DEEP, "document nesting is too deep to process", None))
            return None
        except (TypeError, ValueError):
            diagnostics.append(_diag(DiagnosticCode.SCHEMA_VIOLATION, "document is not representable as JSON", None))
            return None
        if size > max_bytes:
            diagnostics.append(_diag(DiagnosticCode.PAYLOAD_TOO_LARGE, f"document is {size} bytes; limit is {max_bytes}", None))
            return None
        return raw
    if not isinstance(raw, (bytes, str)):
        diagnostics.append(_diag(DiagnosticCode.SCHEMA_VIOLATION, "payload must be bytes, str or a JSON object", None))
        return None
    text = _decode_text(raw, max_bytes, diagnostics)
    if text is None:
        return None
    try:
        obj = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_strict_pairs)
    except RecursionError:
        diagnostics.append(_diag(DiagnosticCode.TOO_DEEP, "JSON nesting is too deep to parse", None))
        return None
    except ValueError as exc:  # json.JSONDecodeError is a ValueError
        diagnostics.append(_diag(DiagnosticCode.SCHEMA_VIOLATION, f"payload is not valid JSON: {exc}", None))
        return None
    if not isinstance(obj, dict):
        diagnostics.append(_diag(DiagnosticCode.SCHEMA_VIOLATION, "top-level JSON value must be an object", None))
        return None
    return obj


def _loc_to_path(loc: Sequence[Any]) -> Optional[str]:
    """Render a pydantic error location as an IR path, dropping discriminator tags."""
    parts: list[str] = []
    previous: Any = None
    for component in loc:
        if isinstance(component, int):
            parts.append(f"[{component}]")
        elif isinstance(component, str) and component in ALLOWED_OPS and (
            isinstance(previous, int) or previous in _EXPR_FIELDS
        ):
            previous = component
            continue  # union tag inserted by pydantic for discriminated unions
        else:
            parts.append(f".{component}" if parts else str(component))
        previous = component
    return "".join(parts) or None


def _pydantic_diagnostics(exc: ValidationError) -> list[Diagnostic]:
    """Map pydantic errors to E100 (schema) or E303 (parser depth) diagnostics."""
    diagnostics: list[Diagnostic] = []
    for error in exc.errors(include_url=False, include_input=False):
        if error.get("type") == "recursion_loop":
            code, message = DiagnosticCode.TOO_DEEP, "nesting exceeds the parser depth limit"
        else:
            code, message = DiagnosticCode.SCHEMA_VIOLATION, f"{error.get('msg', 'schema violation')} ({error.get('type', 'unknown')})"
        diagnostics.append(_diag(code, message, _loc_to_path(error.get("loc", ()))))
    return diagnostics


def parse_and_validate(
    raw: Union[bytes, str, dict],
    limits: Limits = DEFAULT_LIMITS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[Optional[Problem], ValidationOutcome]:
    """Parse untrusted JSON into a ``Problem`` and validate it.

    Returns ``(None, outcome)`` when the payload is oversized (``E306``), not a
    JSON object, malformed, too deeply nested (``E303``) or violates the schema
    (``E100`` per pydantic error, with its location path). Otherwise returns the
    parsed ``Problem`` together with the outcome of :func:`validate_problem`;
    callers must check ``outcome.ok`` before compiling.
    """
    diagnostics: list[Diagnostic] = []
    obj = _load_object(raw, max_bytes, diagnostics)
    if obj is None:
        return None, _failed(diagnostics)
    try:
        problem = Problem.model_validate(obj, strict=True)
    except ValidationError as exc:
        return None, _failed(_pydantic_diagnostics(exc))
    except RecursionError:
        return None, _failed([_diag(DiagnosticCode.TOO_DEEP, "document nesting is too deep to validate", None)])
    return problem, validate_problem(problem, limits)
