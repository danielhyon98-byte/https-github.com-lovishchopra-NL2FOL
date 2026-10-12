"""Link classification and check planning (section 4.7 of docs/STEM_DESIGN.md).

A chain ``L0 op1 E1 … opk Ek`` may continue across lines (a line that opens with a relation
sign continues the previous line's chain). Each link is classified by its two endpoints:
*value* (a number or quantity), *closed* (no symbol), *bound* (every symbol has a binding)
or *symbolic* (a symbol with no binding). Every recognised relation ends in exactly one
outcome:

==============  ===========================================================================
``check``       a planned engine check with a stable id (``stem-<kind>-<n>``, per kind, in
                document order) and the claim ids of the statements that hold its endpoints
``binding``     a value stated for a symbol (``m = 2.0 kg``), or a symbol defined as a
                closed expression; not a check
``formula``     a law or definition (``F = ma``); recorded in scope, its truth out of scope
``context``     a relation stated without a premise to check it against (the first line of
                a derivation, a domain condition ``x > 3``)
``undecided``   a recognised relation the encodings cannot decide, with its ST code and
                reason (ST-UNDEC-001, ST-PARSE-001/002, ST-LIM-001, ST-CHEM-001)
==============  ===========================================================================

Check kinds: ``eq`` (numeric = value), ``sub`` (substitution fidelity), ``alg`` (an algebra
step), ``sol`` (stated roots), ``cnv`` (a unit conversion), ``cmp`` (a stated order, or an
inequality step), ``res`` (a prose restatement of a result), ``giv`` (a Given value against
the request), ``tgt`` (a show-that target), ``chem`` (a balance), ``bool`` (a Boolean
identity), ``tt`` (a truth table), ``base`` (a based numeral).

Front-end findings (``FrontEndFinding``) carry an ST code from :data:`ST_SEVERITY`; the
front end emits no error-severity finding. Dimension findings (ST-DIM-001, ST-DIM-002) come
from integer-vector arithmetic on units read unambiguously or on the units of bound
symbols; a bare number is "unitless as written" and never triggers one. Across an equality
chain, a symbolic operand whose dimension the bindings fix (``ma`` with m in kg and a in
m s⁻²) is compared with every value written with a unit (``= 6.0 kg``). The written side of a
binding gets the same ST-DIM-002 and unit notes (``F = 2.0 kg + 3.0 m``), though no check is
planned for it. An aligned substitution may set a symbol opposite another single symbol
(``u + at = 0 + g × 2.0``): it is a (partial) substitution, never an identity to prove.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Optional

from .boolean import BoolRelation, TruthTable
from .chem import ChemEquation
from .limits import DEFAULT_LIMITS, StemLimits, StemProfile
from .nodes import (
    Abs, Apply, BinOp, BoolOp, Chain, Degrees, Func, Magnification, Neg, Node, Num, Operand, Percent, PlusMinus, Pow, Quantity, Ratio, Root, Sym,
    Unsupported, WithUnit, align, is_closed, is_value, render, replace_symbol, shape_key, symbols, unsupported_reasons, value_of, walk,
)
from .numbers import ExactNumber
from .parser import ParseIssue
from .scope import Binding, Formula, Scope
from .units import DIMENSIONLESS, Dimension, UnitExpr

__all__ = [
    "CHECK_KINDS", "FrontEndFinding", "MathItem", "ProseValue", "Relation", "RequestReading", "ST_SEVERITY", "ShowThatTarget", "dimension_of",
    "plan_relations",
]

#: check kinds in the order of section 8.1
CHECK_KINDS = ("eq", "sub", "alg", "sol", "cnv", "cmp", "res", "giv", "tgt", "chem", "bool", "tt", "base")
#: severity of every front-end code (section 8.2); none is an error
ST_SEVERITY = {
    "ST-PARSE-001": "warning", "ST-PARSE-002": "warning", "ST-UNDEC-001": "warning", "ST-UNDEC-002": "warning", "ST-UNDEF-001": "warning",
    "ST-UNIT-001": "warning", "ST-UNIT-002": "info", "ST-DIM-001": "warning", "ST-DIM-002": "warning", "ST-ALG-001": "warning",
    "ST-CHEM-001": "warning", "ST-CODE-001": "info", "ST-SCOPE-001": "info", "ST-LIM-001": "warning", "ST-LIM-002": "warning",
    "ST-INTERNAL-001": "warning",
}
_EQUALITY = frozenset({"=", "≈", "≃", "≡"})
_APPROX = frozenset({"≈", "≃"})
_ORDER = frozenset({"<", ">", "≤", "≥", "≠"})
_STEP_WORDS = ("⇒", "∴", "so", "hence", "therefore", "thus", "gives", "giving", "rearranging", "rearranged", "which gives", "implies", "then",
               "get", "obtain", "yields", "leads to")
_APPROX_WORDS = ("approximately", "approx.", "about", "roughly", "estimate", "around", "nearly")
_COMPLETE_PHRASES = ("only solution", "only root", "the solution is", "the solutions are", "is the solution", "are the solutions", "the roots are",
                     "solutions are", "roots are", "the only value", "is the only")
_RESTRICT_WORDS = ("reject", "positive", "non-negative", "nonnegative", "x > 0", "x ≥ 0", "> 0", "≥ 0", "length", "time", "only the positive",
                   "cannot be negative", "must be positive", "domain")
_RESULT_CUES = ("therefore", "hence", "thus", "so", "the answer is", "the result is")
_RESULT_VERBS = frozenset({"is", "are", "was", "were", "equals", "equal", "=", "≈", "gives", "becomes", "carries", "delivers", "has", "of", "reaches",
                           "comes", "be", "makes", "totals", "needs", "need", "requires"})
#: participles after which 'at' or 'as' introduces the result, not a condition
_RESULT_PARTICIPLES = frozenset({"estimated", "calculated", "computed", "determined", "evaluated", "found", "out"})
_QUALIFIERS = frozenset({"about", "approximately", "roughly", "around", "nearly", "almost", "≈", "~", "only", "exactly", "just"})
_PREPOSITIONS = frozenset({"at", "in", "for", "with", "by", "from", "after", "before", "per", "to", "on", "into", "over", "under", "within", "than", "below",
                           "above"})


@dataclass(frozen=True)
class FrontEndFinding:
    """A front-end finding (ST-*): ``code`` and ``severity`` from :data:`ST_SEVERITY`, the
    statements it names, and the planned check id when it concerns one."""

    code: str
    severity: str
    message: str
    statement_ids: tuple[str, ...]
    check_id: str = ""
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class MathItem:
    """One read math span (or display row) in document order, with its statement and context.
    ``gap_before`` is the statement's prose between the previous item and this one;
    ``source`` is the binding source its values carry (``given``, ``let``, ``statement``,
    ``request``)."""

    index: int
    statement_id: str
    statement_index: int
    part: str
    stmt_kind: str
    span_kind: str
    start: int
    end: int
    chains: tuple[Chain, ...] = ()
    issues: tuple[ParseIssue, ...] = ()
    unparsed: bool = False
    label: str = ""
    gap_before: str = ""
    source: str = "statement"
    booleans: tuple[BoolRelation, ...] = ()
    chem: Optional[ChemEquation] = None
    table: Optional[TruthTable] = None
    error: str = ""
    code: str = ""
    statement_text: str = ""
    statement_start: int = 0
    statement_end: int = 0

    @property
    def ends_statement(self) -> bool:
        """Nothing but punctuation or a connective word follows this item in its statement (``(m₁ + m₂)v = p:``)."""
        a = max(0, self.end - self.statement_start)
        if len(self.statement_text) - a > 24:
            return False
        tail = self.statement_text[a:].strip().strip(".:;,").strip().lower()
        return tail in ("", "so", "then", "hence", "therefore", "thus", "giving", "which gives")

    def context(self, width: int = 240) -> str:
        """The statement's text around this item, lower-cased, at most ``width`` characters on each side
        (bounded work per item however long the statement is)."""
        a = max(0, self.start - self.statement_start - width)
        b = min(len(self.statement_text), self.end - self.statement_start + width)
        return self.statement_text[a:b].lower()


@dataclass(frozen=True)
class ProseValue:
    """A value written in prose (outside any math span): a quantity, a per cent or a number,
    with the statement prose before it (for the result cue)."""

    statement_id: str
    statement_index: int
    part: str
    node: Node
    start: int
    end: int
    before: str


@dataclass(frozen=True)
class ShowThatTarget:
    node: Node
    approx: bool
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class RequestReading:
    """What the request states: bindings, quantities (prose and math), relations and show-that targets."""

    bindings: tuple[Binding, ...] = ()
    quantities: tuple[tuple[Node, int, int], ...] = ()
    relations: tuple[tuple[Operand, str, Operand], ...] = ()
    targets: tuple[ShowThatTarget, ...] = ()
    text: str = ""
    restricts_domain: bool = False


@dataclass(frozen=True)
class Relation:
    """One recognised relation and its outcome (see the module docstring). Fields beyond the
    endpoints are set per kind:

    * ``sub``: ``pairs`` (symbol -> substituted subtree) when the trees align, ``evaluate`` when
      the whole symbolic side is compared under its bindings, ``unbound`` (symbols with no
      binding: the checks stage takes a booklet reading or reports ST-UNDEC-002), ``formula``
      when the symbolic side is a recorded formula (``v = u + at`` then ``v = 0 + 9.8 × 3.0``);
    * ``alg`` and step ``cmp``: ``premise_left``/``premise_op``/``premise_right`` (the relation the
      step starts from) and ``premise_ids``; ``explicit`` when a connective (⇒, ∴, so, gives) says so;
    * ``sol``: ``root_symbol``, ``roots``, the equation in ``premise_*``, ``complete`` (the full set
      is claimed), ``restricted`` (a domain restriction is stated);
    * ``res``: ``right`` is the prose value, ``left`` the chain's final value;
    * ``giv``/``tgt``: ``candidates`` (request bindings or quantities), ``right`` the stated value;
    * ``chem``/``bool``/``tt``: ``chem``/``bool_rel``/``table``.
    """

    index: int
    kind: str
    outcome: str
    statement_ids: tuple[str, ...]
    start: int
    end: int
    op: str = ""
    left: Optional[Operand] = None
    right: Optional[Operand] = None
    check_id: str = ""
    code: str = ""
    reason: str = ""
    approx: bool = False
    part: str = ""
    pairs: tuple[tuple[str, Node], ...] = ()
    unbound: tuple[str, ...] = ()
    evaluate: bool = False
    formula: Optional[Formula] = None
    premise_left: Optional[Operand] = None
    premise_op: str = ""
    premise_right: Optional[Operand] = None
    premise_ids: tuple[str, ...] = ()
    explicit: bool = False
    root_symbol: str = ""
    roots: tuple[Node, ...] = ()
    complete: bool = False
    restricted: bool = False
    candidates: tuple[Binding, ...] = ()
    chem: Optional[ChemEquation] = None
    bool_rel: Optional[BoolRelation] = None
    table: Optional[TruthTable] = None
    capped: bool = False
    position: int = 0
    #: an algebra step that takes the principal (non-negative) root: the checks stage adds that side condition
    principal_root: bool = False

    @property
    def is_check(self) -> bool:
        return self.outcome == "check"


# ----------------------------------------------------------------------------------------- dimensions


def dimension_of(node: Node, scope: Scope, notes: Optional[list[tuple[Node, Dimension, Dimension]]] = None, *,
                 coefficients: bool = False) -> Optional[Dimension]:
    """The dimension of ``node`` when every part of it is known (units read unambiguously, bound
    symbols with one dimension, exact fractions and π dimensionless); None when unknown. A sum of
    two known, different dimensions is recorded in ``notes`` (ST-DIM-002) and yields None.

    With ``coefficients`` (a symbolic side such as ``½mv²`` or ``2as``, where a written integer is
    a pure coefficient), an exact integer is dimensionless too. A bare number on a numeric side
    stays "unitless as written" (unknown), so ``120 / 8 = 15 m s⁻¹`` is never a dimension finding."""
    return _dim(node, scope, notes, 0, coefficients)


def _dim(node: Node, scope: Scope, notes: Optional[list], depth: int, coefficients: bool = False) -> Optional[Dimension]:
    if depth > 64:
        return None
    rec = lambda n: _dim(n, scope, notes, depth + 1, coefficients)  # noqa: E731
    if isinstance(node, Quantity):
        return node.unit.dim if not node.unit.unknown else None
    if isinstance(node, WithUnit):
        return node.unit.dim if not node.unit.unknown else None
    if isinstance(node, Num):
        n = node.number
        if n.vulgar or (coefficients and n.exact and not n.has_point and not n.scientific and not n.based):
            return DIMENSIONLESS
        return None
    if isinstance(node, Sym):
        if node.kind == "constant":
            return DIMENSIONLESS
        dims = set()
        for b in scope.bindings_for(node.name):
            if b.unit is None or b.unit.unknown or b.unit.dim is None:
                return None
            dims.add(b.unit.dim)
        return dims.pop() if len(dims) == 1 else None
    if isinstance(node, (Neg, Abs)):
        return rec(node.arg)
    if isinstance(node, PlusMinus):
        if node.left is None:
            return rec(node.right)
        return _sum_dim(node.left, node.right, scope, notes, depth, node, coefficients)
    if isinstance(node, BinOp):
        if node.op in "+-":
            return _sum_dim(node.left, node.right, scope, notes, depth, node, coefficients)
        a, b = rec(node.left), rec(node.right)
        if a is None or b is None:
            return None
        return a * b if node.op == "*" else a / b
    if isinstance(node, Pow):
        a = rec(node.base)
        return None if a is None else a.power(node.exp)
    if isinstance(node, Root):
        a = rec(node.arg)
        if a is None or any(e % 2 for e in a.exps) or a.angle % 2:
            return None
        return Dimension(tuple(e // 2 for e in a.exps), a.angle // 2)  # type: ignore[arg-type]
    if isinstance(node, Func):
        return DIMENSIONLESS if rec(node.arg) is not None else None
    if isinstance(node, Degrees):
        return Dimension((0, 0, 0, 0, 0, 0, 0), 1)
    return None


def _sum_dim(a: Node, b: Node, scope: Scope, notes: Optional[list], depth: int, whole: Node, coefficients: bool = False) -> Optional[Dimension]:
    da, db = _dim(a, scope, notes, depth + 1, coefficients), _dim(b, scope, notes, depth + 1, coefficients)
    if da is None or db is None:
        return None
    if not da.same_physical(db):
        if notes is not None:
            notes.append((whole, da, db))
        return None
    return da


# ----------------------------------------------------------------------------------------- helpers


def _first(op: Optional[Operand]) -> Optional[Node]:
    return op.readings[0] if op is not None and op.readings else None


def _is_lone(node: Optional[Node]) -> bool:
    return isinstance(node, (Sym, Apply)) and not (isinstance(node, Sym) and node.kind in ("constant", "bond", "continuation"))


def _syms(node: Optional[Node]) -> set[str]:
    return set(symbols(node)) if node is not None else set()


def _has_func_of(node: Node, unknown: set[str]) -> bool:
    for n in walk(node):
        if isinstance(n, (Func, Root)) and _syms(n.arg) & unknown:
            if isinstance(n, Root):
                continue  # a square root of an unknown is algebra (encoded with an auxiliary), not a function of an unknown
            return True
    return False


def _degree(node: Node, x: str) -> int:
    """A coarse degree of ``node`` in ``x``: 0, 1, 2 for a polynomial beyond linear, 3 for anything
    that is not a polynomial in ``x`` (a division by it, a root or function of it)."""
    if x not in _syms(node):
        return 0
    if isinstance(node, Sym):
        return 1 if node.name == x else 0
    if isinstance(node, (Neg, Percent)):
        return _degree(node.arg, x)
    if isinstance(node, BinOp):
        a, b = _degree(node.left, x), _degree(node.right, x)
        if node.op in "+-":
            return max(a, b)
        if node.op == "*":
            return 3 if 3 in (a, b) else min(2, a + b)
        return 3 if b else a
    if isinstance(node, Pow):
        d = _degree(node.base, x)
        if d == 3 or node.exp < 0:
            return 3
        return min(2, d * max(1, node.exp))
    return 3


def _contains_based(node: Node) -> bool:
    return any(isinstance(n, Num) and (n.number.based or n.number.base != 10) for n in walk(node))


def _approx_context(text: str) -> bool:
    low = text[-160:].lower()
    return any(w in low for w in _APPROX_WORDS)


def _words(text: str) -> list[str]:
    out = []
    word = []
    for ch in text[-400:].lower():
        if ch.isalpha() or ch in "≈~=":
            word.append(ch)
        else:
            if word:
                out.append("".join(word))
                word = []
    if word:
        out.append("".join(word))
    return out


def _has_step_word(text: str) -> bool:
    low = " " + " ".join(_words(text)) + " "
    if "⇒" in text or "∴" in text:
        return True
    return any(f" {w} " in low for w in _STEP_WORDS if w.isalpha() or " " in w)


@dataclass
class _ChainState:
    operands: list[tuple[Operand, str]]  # operand, statement id
    ops: list[str]
    item: MathItem
    start: int


class _Planner:
    def __init__(self, items: list[MathItem], prose_values: list[ProseValue], scope: Scope, request: RequestReading, profile: StemProfile,
                 limits: StemLimits, statement_order: dict[str, int], code_items: list[tuple[str, int, int, str]], request_mode: bool) -> None:
        self.items = items
        self.prose_values = prose_values
        self.scope = scope
        self.request = request
        self.profile = profile
        self.lim = limits
        self.order = statement_order
        self.code_items = code_items
        self.request_mode = request_mode
        self.relations: list[Relation] = []
        self.findings: list[FrontEndFinding] = []
        self.prev_chain: Optional[_ChainState] = None
        self.prev_rel: Optional[dict] = None
        self.final_values: list[dict] = []
        self.equations: list[dict] = []
        self.unit_reported: set[tuple[str, str]] = set()
        self.request_relations: list[tuple[Operand, str, Operand]] = []
        self._root_groups: dict[tuple[str, str], int] = {}
        #: Boolean names the answer defines ('M = (A ∧ B) ∨ …'): name -> (expression, statement id)
        self.bool_defs: dict[str, tuple[Node, str]] = {}
        self._seen_findings: set[tuple] = set()
        self._request_lower = request.text[:4000].lower()

    # -------------------------------------------------------------- output helpers
    def add(self, **kw: object) -> Relation:
        rel = Relation(index=len(self.relations), **kw)  # type: ignore[arg-type]
        self.relations.append(rel)
        return rel

    def finding(self, code: str, message: str, statement_ids: tuple[str, ...], start: int = 0, end: int = 0, check_index: Optional[int] = None) -> None:
        key = (code, message[:200], tuple(statement_ids))
        if key in self._seen_findings:
            return
        self._seen_findings.add(key)
        self.findings.append(FrontEndFinding(code=code, severity=ST_SEVERITY.get(code, "warning"), message=message[:1200],
                                             statement_ids=tuple(dict.fromkeys(statement_ids)), start=start, end=end,
                                             check_id=f"#{check_index}" if check_index is not None else ""))

    # -------------------------------------------------------------- main loop
    def run(self) -> None:
        for item in self.items:
            if item.error:
                self.finding(item.code or "ST-LIM-001", item.error, (item.statement_id,), item.start, item.end)
                self.add(kind="span", outcome="undecided", statement_ids=(item.statement_id,), start=item.start, end=item.end, code=item.code or "ST-LIM-001",
                         reason=item.error, part=item.part)
                continue
            for iss in item.issues:
                self.finding(iss.code, iss.message, (item.statement_id,), iss.start, iss.end)
            if item.chem is not None:
                self._chem(item)
                continue
            if item.table is not None:
                self._table(item)
                continue
            if item.booleans:
                for br in item.booleans:
                    self._boolean(item, br)
                continue
            if item.unparsed:
                self.add(kind="span", outcome="undecided", statement_ids=(item.statement_id,), start=item.start, end=item.end,
                         code=item.issues[0].code if item.issues else "ST-PARSE-001", reason=item.issues[0].message if item.issues else "unparsed",
                         part=item.part)
                continue
            for ci, chain in enumerate(item.chains):
                self._chain(item, ci, chain)
        if not self.request_mode:
            self._defined_columns()
            self._results()
            self._givens()
            self._targets()
            for sid, a, b, lang in self.code_items:
                self.finding("ST-CODE-001", f"a code block{(' (' + lang + ')') if lang else ''} is present; it was not executed and not checked", (sid,), a, b)
            for note in self.scope.notes:
                self.finding(note.code, note.message, note.statement_ids)

    # -------------------------------------------------------------- chains
    def _chain(self, item: MathItem, ci: int, chain: Chain) -> None:
        sid = item.statement_id
        operands: list[tuple[Operand, str]] = [(op, sid) for op in chain.operands]
        ops = list(chain.ops)
        base_pos = 0
        continued = False
        if chain.lead == "continuation":
            prev = self.prev_chain
            if prev is not None and prev.item.part == item.part and self.order.get(sid, 0) - self.order.get(prev.item.statement_id, 0) <= 2:
                operands = [prev.operands[-1]] + operands[1:]
                base_pos = len(prev.ops)
                continued = True
                full_operands = prev.operands + operands[1:]
                full_ops = prev.ops + ops
            else:
                self.add(kind="continuation", outcome="context", statement_ids=(sid,), start=chain.start, end=chain.end, part=item.part,
                         reason="a line that opens with a relation sign and has no preceding chain to continue")
                operands = operands[1:]
                ops = ops[1:]
                full_operands, full_ops = operands, ops
        else:
            full_operands, full_ops = operands, ops
        lone_head = _first(full_operands[0][0]) if full_operands else None
        lone = _is_lone(lone_head) or (chain.lead == "label" and not continued)
        # the symbols bound before this chain: a chain's own values must not make its unknowns look bound to the step logic
        chain_syms: set[str] = set()
        for op, _sid in full_operands:
            for r in op.readings:
                chain_syms |= _syms(r)
        bound_before = frozenset(n for n in chain_syms if self.scope.bindings.get(n))
        # bindings first: a later link's substitution may rely on this chain's own values
        self._chain_bindings(item, full_operands, full_ops, lone, lone_head)
        approx_ctx = _approx_context(item.gap_before)
        first_rel, first_finding = len(self.relations), len(self.findings)
        for k in range(len(ops)):
            left, lsid = operands[k]
            right, rsid = operands[k + 1]
            pos = base_pos + k
            self._link(item, left, lsid, ops[k], right, rsid, pos, lone and pos == 0, lone_head if lone else None, approx_ctx, full_operands, full_ops)
        if not self.request_mode and full_ops and all(o in _EQUALITY for o in full_ops):
            self._chain_dimension(full_operands, lone, first_rel, first_finding)
        if full_ops and not continued:
            self._sequence(item, chain, full_operands, full_ops, lone, lone_head, bound_before)
        self.prev_chain = _ChainState(full_operands, full_ops, item, chain.start)
        # remember the final value of the chain (for restatements and show-that targets)
        last = _first(full_operands[-1][0]) if full_operands else None
        if last is not None and is_value(last) and full_ops and full_ops[-1] in _EQUALITY:
            self.final_values.append({"node": last, "operand": full_operands[-1][0], "sid": full_operands[-1][1], "part": item.part,
                                      "order": self.order.get(full_operands[-1][1], 0), "symbol": lone_head.name if isinstance(lone_head, Sym) else ""})

    def _chain_dimension(self, operands: list[tuple[Operand, str]], lone: bool, first_rel: int, first_finding: int) -> None:
        """ST-DIM-001 across an equality chain: a symbolic operand whose dimension the stated bindings
        fix (``ma`` with m in kg and a in m s⁻²) against a value written with a unit of another
        dimension further along (``= 6.0 kg``). The head of a computing chain is skipped: its
        binding is the chain's own result."""
        ref: Optional[tuple[Node, Dimension]] = None
        for k, (op, _sid) in enumerate(operands):
            node = _first(op)
            if node is None or (k == 0 and lone) or is_value(node) or is_closed(node) or unsupported_reasons(node):
                continue
            d = dimension_of(node, self.scope, coefficients=True)
            if d is not None:
                ref = (node, d)
                break
        if ref is None:
            return
        flagged = {f.check_id for f in self.findings[first_finding:] if f.code == "ST-DIM-001"}
        for op, sid in operands:
            node = _first(op)
            if node is None or not isinstance(node, (Quantity, WithUnit)) or node.unit.unknown or node.unit.dim is None:
                continue
            if node.unit.dim.same_physical(ref[1]):
                continue
            idx = next((i for i in range(first_rel, len(self.relations)) if self.relations[i].outcome == "check" and self.relations[i].right is op), None)
            if idx is not None and f"#{idx}" in flagged:
                continue  # the link itself already names the mismatch
            self.finding("ST-DIM-001", f"'{render(ref[0])[:120]}' has the dimension {ref[1]} under the stated bindings, but the chain states "
                                       f"'{render(node)[:120]}' ({node.unit.dim})", tuple(dict.fromkeys(s for _o, s in operands)),
                         getattr(node, "start", 0), getattr(node, "end", 0), check_index=idx)

    def _order_bindings(self, item: MathItem, operands: list[tuple[Operand, str]], ops: list[str]) -> None:
        """``T₁ = 300 K > T₂ = 250 K``: a lone symbol right after an order sign and stated equal to a value is bound to it,
        so the comparison is between the two stated values (section 4.7, stem-cmp)."""
        for k in range(1, len(operands) - 1):
            if ops[k - 1] not in _ORDER or ops[k] not in _EQUALITY:
                continue
            sym, val = _first(operands[k][0]), _first(operands[k + 1][0])
            if not isinstance(sym, Sym) or sym.kind != "symbol" or val is None or not is_value(val):
                continue
            v = value_of(val)
            if v is None or v[1] is None:
                continue
            value, number, unit, wrapper = v
            self.scope.add(Binding(sym.name, value, number, unit, "request" if self.request_mode else "statement", operands[k + 1][1],
                                   getattr(val, "start", 0), getattr(val, "end", 0), wrapper=wrapper))

    def _chain_bindings(self, item: MathItem, operands: list[tuple[Operand, str]], ops: list[str], lone: bool, head: Optional[Node]) -> None:
        if any(o in _ORDER for o in ops):
            self._order_bindings(item, operands, ops)
        first = _first(operands[0][0]) if operands else None
        if isinstance(first, Unsupported) and first.name and isinstance(first.arg, Sym) and ops and ops[0] in _EQUALITY:
            # f′(x) = 3x² − 2: the answer's own formula of its derivative, kept for evaluations (the relation stays undecided)
            for k in range(1, len(operands)):
                rhs = _first(operands[k][0])
                if rhs is not None and not is_closed(rhs) and not unsupported_reasons(rhs) and _syms(rhs) <= {first.arg.name}:
                    self.scope.add_formula(Formula(first.name, rhs, operands[k][1], "derivative", params=(first.arg.name,),
                                                   start=getattr(rhs, "start", 0), end=getattr(rhs, "end", 0)))
                    break
        if not lone or not isinstance(head, Sym) or head.kind in ("label", "continuation") or not ops:
            # a function definition f(x) = ... or a law with a label: formulas only
            if lone and isinstance(head, Apply) and len(operands) > 1:
                rhs = _first(operands[1][0])
                if rhs is not None:
                    self.scope.add_formula(Formula(head.name, rhs, operands[0][1], "definition", params=tuple(symbols(head.arg)), start=head.start, end=head.end))
            return
        if ops[0] not in _EQUALITY:
            return
        rhs = _first(operands[1][0])
        root = self._is_root_symbol(head.name) and rhs is not None and is_closed(rhs)
        if rhs is not None and not is_value(rhs) and not is_closed(rhs) and not isinstance(rhs, Unsupported) and not unsupported_reasons(rhs):
            src = "request" if self.request_mode else "law"
            self.scope.add_formula(Formula(head.name, rhs, operands[1][1], src, start=getattr(rhs, "start", 0), end=getattr(rhs, "end", 0)))
        for k in range(1, len(operands)):
            if ops[k - 1] not in _EQUALITY:
                break
            node = _first(operands[k][0])
            if node is not None and not is_value(node):
                node = _exact_fraction(node)
            if node is None or not is_value(node):
                continue
            v = value_of(node)
            if v is None or v[1] is None:
                continue
            value, number, unit, wrapper = v
            source = item.source if k == 1 else "result"
            if root:
                source = "root"  # 'x = 7' after an equation in x states a solution
            if source == "condition":
                return  # 'At x = 1:' evaluates at a point; it binds nothing beyond its statement
            if self.request_mode:
                source = "request"
            self.scope.add(Binding(head.name, value, number, unit, source, operands[k][1], getattr(node, "start", 0), getattr(node, "end", 0), wrapper=wrapper))

    def _cls(self, node: Node) -> str:
        if is_value(node):
            return "value"
        if is_closed(node):
            return "closed"
        names = _syms(node)
        if all(self.scope.is_given(n) for n in names):
            return "bound"
        return "symbolic"

    def _unbound(self, node: Node) -> tuple[str, ...]:
        return tuple(n for n in symbols(node) if not self.scope.is_given(n))

    def _link(self, item: MathItem, left: Operand, lsid: str, op: str, right: Operand, rsid: str, pos: int, lone_first: bool, head: Optional[Node],
              approx_ctx: bool, full_operands: list, full_ops: list) -> None:
        head_is_lone = head is not None
        sids = tuple(dict.fromkeys((lsid, rsid)))
        start, end = min(left.start, right.start), max(left.end, right.end)
        base = dict(statement_ids=sids, start=start, end=end, op=op, left=left, right=right, part=item.part, position=pos,
                    approx=op in _APPROX or approx_ctx)
        if self.request_mode:
            return
        if not left.readings or not right.readings:
            bad = left if not left.readings else right
            self.add(kind="link", outcome="undecided", code=bad.code or "ST-PARSE-001", reason=bad.error or "an operand could not be read", **base)
            return
        lnode, rnode = left.readings[0], right.readings[0]
        if pos == 0 and op in _EQUALITY and isinstance(lnode, Unsupported) and lnode.name and lnode.arg is not None and is_closed(lnode.arg) \
                and is_closed(rnode) and not unsupported_reasons(rnode):
            # f′(2) = 3 × 2² − 2: the derivative's stated formula evaluated at the argument (no formula stated: undecided)
            if self._evaluation(base, item, lnode.name, lnode.arg, rnode, derivative=True):
                return
        reasons = tuple(dict.fromkeys(unsupported_reasons(lnode) + unsupported_reasons(rnode)))
        if reasons and lone_first and head is not None and not unsupported_reasons(lnode) and not is_closed(rnode) and op in _EQUALITY \
                and _syms(rnode) - {getattr(head, "name", "")}:
            # a law written with notation outside the encodings (its truth is out of scope anyway); a value written that way
            # ('x = ±2i', 'z = 3 + 4i': nothing but the unsupported construct is free) is a statement, named undecided below
            self.add(kind="formula", outcome="formula", reason="a law or definition written with notation outside the encodings (" + "; ".join(reasons) + ")",
                     **base)
            return
        if reasons:
            self._undecided("ST-UNDEC-001", "a relation outside the encodings: " + "; ".join(reasons), base, item)
            return
        if op in ("→", "⇌", "∝", "⇔") and not (op == "⇔" and self.profile.computer_science):
            what = {"→": "an arrow (a limit, a mapping or a reaction outside a chemistry reading)", "⇌": "an equilibrium arrow outside a chemistry reading",
                    "∝": "a proportionality", "⇔": "an equivalence between relations"}[op]
            self._undecided("ST-UNDEC-001", what, base, item)
            return
        if any(isinstance(n, Ratio) for n in (lnode, rnode)) and not all(isinstance(n, Ratio) for n in (lnode, rnode)):
            self.add(kind="link", outcome="context", reason="a ratio set against a non-ratio", **base)
            return
        lc, rc = self._cls(lnode), self._cls(rnode)
        if op in _ORDER:
            if lc in ("value", "closed", "bound") and rc in ("value", "closed", "bound"):
                self._dimension_check(base, item, lnode, rnode)
                self.add(kind="cmp", outcome="check", **base)
            else:
                self.add(kind="link", outcome="context", reason="an inequality about an unknown (a condition, or a step checked between relations)", **base)
            return
        if op not in _EQUALITY:
            self.add(kind="link", outcome="context", reason=f"a relation sign {op!r} that is not checked", **base)
            return
        # equalities
        if lone_first and isinstance(head, Apply) and rc in ("value", "closed") and is_closed(head.arg):
            if self._evaluation(base, item, head.name, head.arg, rnode):
                return
        if lone_first and head is not None:
            if isinstance(head, Sym) and head.kind == "label":
                if rc in ("value", "closed"):
                    self.add(kind="label", outcome="binding", reason=f"the quantity named '{head.name}' is defined by the written expression", **base)
                else:
                    self.add(kind="label", outcome="formula", reason=f"a word formula for '{head.name}'", **base)
                return
            if rc == "value":
                self._value_notes(base, rnode)
                self.add(kind="binding", outcome="binding", reason="a value stated for a symbol", **base)
                return
            if rc == "closed":
                f = self.scope.formula_for(head.name) if isinstance(head, Sym) else None
                pairs = align(f.expr, rnode) if f is not None else None
                if f is not None and pairs:
                    self._substitution(base, item, f.expr, rnode, pairs, formula=f)
                    return
                self._value_notes(base, rnode)
                self.add(kind="binding", outcome="binding", reason="a symbol defined as a written expression", **base)
                return
            if isinstance(head, Apply):
                self.add(kind="formula", outcome="formula", reason=f"a definition of the function {head.name}", **base)
                return
            self.add(kind="formula", outcome="formula", reason="a law or definition (its truth is out of scope)", **base)
            return
        if _contains_based(lnode) or _contains_based(rnode):
            self.add(kind="base", outcome="check", **base)
            return
        if lc in ("value", "closed") and rc in ("value", "closed"):
            self._dimension_check(base, item, lnode, rnode)
            if lc == "value" and rc == "value":
                lv, rv = value_of(lnode), value_of(rnode)
                if lv is not None and rv is not None and lv[2] is not None and rv[2] is not None:
                    self.add(kind="cnv", outcome="check", **base)
                    return
            self.add(kind="eq", outcome="check", **base)
            return
        if lc in ("bound", "symbolic") and rc in ("value", "closed"):
            self._sub_or_equation(base, item, lnode, rnode, pos, head_is_lone)
            return
        if lc in ("value", "closed") and rc in ("bound", "symbolic"):
            self._sub_or_equation(dict(base), item, rnode, lnode, pos, head_is_lone)
            return
        # both sides carry symbols: a partial substitution, or an identity step inside the chain
        pairs = align(lnode, rnode)
        if pairs:
            useful = [(s, n) for s, n in pairs if not (isinstance(n, Sym) and isinstance(s, (Sym, Apply)) and n.name == getattr(s, "name", ""))]
            # a written substitution, possibly partial: each symbol stands opposite a value or a single symbol
            # ('u + at = 0 + g × 2.0' reads u as 0, a as g, t as 2.0): never an identity to prove
            if useful and all(is_closed(n) or isinstance(n, Sym) for _s, n in useful) and any(is_closed(n) for _s, n in useful):
                self._substitution(base, item, lnode, rnode, useful)
                return
        if _has_func_of(lnode, set(self._unbound(lnode))) or _has_func_of(rnode, set(self._unbound(rnode))):
            self._undecided("ST-UNDEC-001", "a function of an unknown", base, item)
            return
        if pos > 0:
            self.add(kind="alg", outcome="check", premise_left=full_operands[0][0], premise_op=full_ops[0], premise_right=left, premise_ids=sids,
                     explicit=True, reason="an identity step inside one chain", **base)
            return
        if self._factorisation(lnode, rnode, full_operands, full_ops):
            # 'x² − 7x + 12 = (x − 3)(x − 4) = 0': the first link states that the two sides are the same polynomial;
            # checked as a step from the trivially true 'P = P', so it holds iff the identity holds for every x
            self.add(kind="alg", outcome="check", premise_left=left, premise_op="=", premise_right=left, premise_ids=sids, explicit=True,
                     reason="a factorisation or expansion stated inside one chain (the two sides are the same polynomial)", **base)
            return
        self.add(kind="stated", outcome="context", reason="a relation stated without a preceding relation to derive it from", **base)

    def _evaluation(self, base: dict, item: MathItem, fname: str, arg: Node, rnode: Node, *, derivative: bool = False) -> bool:
        """``f(2) = 2² + 1`` after ``f(x) = x² + 1`` (or ``f′(2) = 3 × 2² − 2`` after ``f′(x) = 3x² − 2``): the stated formula
        with its parameter replaced by the written argument is set against the written right side (an ``eq`` check, closed on
        both sides). False (nothing planned) when no usable formula of one parameter is stated."""
        f = next((x for x in reversed(self.scope.formulas.get(fname, ())) if len(x.params) == 1 and not unsupported_reasons(x.expr)
                  and not any(isinstance(n, Apply) for n in walk(x.expr)) and _syms(x.expr) <= set(x.params)), None)
        evaluated = replace_symbol(f.expr, f.params[0], arg) if f is not None else None
        if evaluated is None or not is_closed(evaluated):
            return False
        left = Operand((evaluated,), base["start"], base["end"])
        b = dict(base)
        b["left"] = left
        b["statement_ids"] = tuple(dict.fromkeys(base["statement_ids"] + ((f.statement_id,) if f.statement_id else ())))
        self.add(kind="eq", outcome="check", reason=f"the evaluation of {fname} at the written argument against the formula stated in {f.statement_id}"
                 + (" (the formula is the answer's own derivative; differentiation itself is not checked)" if derivative else ""), **b)
        return True

    def _factorisation(self, lnode: Node, rnode: Node, full_operands: list, full_ops: list) -> bool:
        """The first link of a mathematics chain ``P = F = 0`` in one unknown, both sides polynomials: a factorisation
        or an expansion, an identity in that unknown (never a law, which has several symbols and no zero end)."""
        if not self.profile.is_mathematics or len(full_ops) < 2 or not all(o in _EQUALITY for o in full_ops):
            return False
        last = _first(full_operands[-1][0])
        v = value_of(last) if last is not None and is_value(last) else None
        if v is None or v[0] != 0 or v[2] is not None:
            return False
        names = _syms(lnode)
        if len(names) != 1 or _syms(rnode) != names:
            return False
        x = next(iter(names))
        for side in (lnode, rnode):
            for n in walk(side):
                if isinstance(n, (Func, Root, Apply, Abs, PlusMinus, Unsupported, Percent, Quantity, WithUnit)):
                    return False
                if isinstance(n, BinOp) and n.op == "/" and x in _syms(n.right):
                    return False
                if isinstance(n, Pow) and (n.exp < 0 or n.exp > 4):
                    return False
        return max(_degree(lnode, x), _degree(rnode, x)) >= 1

    def _sub_or_equation(self, base: dict, item: MathItem, sym_side: Node, num_side: Node, pos: int, head_is_lone: bool) -> None:
        """A symbolic side against a numeric side. In a chain that computes a named quantity (its
        head is a lone symbol: ``n(NaOH) = c × V = c × 0.0250 = …``) this is a substitution or an
        evaluation under the bindings. In an equation chain (``2x = 14``, ``(x − 4)(x + 2) = 0``)
        an unknown with no binding is solved for, not substituted: unless the trees align (a
        written substitution such as ``b² − 4ac = 4² − 4 × 1 × 6``), it is a stated equation."""
        if not head_is_lone and not align(sym_side, num_side) and not (isinstance(sym_side, Sym) and self.scope.is_given(sym_side.name)):
            self.add(kind="stated", outcome="context", reason="an equation in an unknown (solved by the steps that follow, not substituted)", **base)
            return
        self._sub_link(base, item, sym_side, num_side, pos)

    def _undecided(self, code: str, reason: str, base: dict, item: MathItem) -> None:
        rel = self.add(kind="link", outcome="undecided", code=code, reason=reason, **base)
        self.finding(code, f"{reason}; the relation in {', '.join(rel.statement_ids)} is not checked", rel.statement_ids, rel.start, rel.end)

    def _sub_link(self, base: dict, item: MathItem, sym_side: Node, num_side: Node, pos: int) -> None:
        if isinstance(sym_side, Sym) and sym_side.kind not in ("constant",):
            if self.scope.is_bound(sym_side.name):
                self._substitution(base, item, sym_side, num_side, [(sym_side, num_side)])
            else:
                self.add(kind="binding", outcome="binding", reason="a symbol defined by the written expression", **base)
            return
        pairs = align(sym_side, num_side)
        if pairs:
            self._substitution(base, item, sym_side, num_side, pairs)
            return
        unbound = tuple(n for n in symbols(sym_side) if not self.scope.has_reading(n))
        # the writer's own substitution inside matching function applications reads the unknown: mg sin θ against 49.05 ÷ sin 30° reads θ as 30°
        anchors = [(n, v) for n, v in _anchor_pairs(sym_side, num_side) if n in unbound]
        anchored = {n for n, _v in anchors}
        remaining = tuple(n for n in unbound if n not in anchored)
        self._dimension_check(base, item, sym_side, num_side)
        if _has_func_of(sym_side, set(remaining)):
            self._undecided("ST-UNDEC-001", "a function of an unknown", base, item)
            return
        reason = "the symbolic side under the stated bindings against the numeric side"
        if anchors:
            reason += "; read from the written substitution: " + ", ".join(f"{n} = {render(v)}" for n, v in anchors)
        if remaining:
            reason += f"; no binding for {', '.join(remaining)}"
        self.add(kind="sub", outcome="check", evaluate=True, unbound=remaining, pairs=tuple(anchors), reason=reason, **base)

    def _substitution(self, base: dict, item: MathItem, sym_side: Node, num_side: Node, pairs: list, formula: Optional[Formula] = None) -> None:
        checkable: list[tuple[str, Node]] = []
        introduced: list[tuple[str, Node]] = []
        for s, n in pairs:
            name = getattr(s, "name", "")
            if isinstance(s, Apply):
                name = s.name + "()"
            if not name or (isinstance(n, Sym) and n.name == name):
                continue
            if self.scope.is_bound(name):
                checkable.append((name, n))
            else:
                introduced.append((name, n))
        sid = base["statement_ids"][-1]
        for name, n in introduced:
            v = value_of(n)
            if v is not None and v[1] is not None:
                self.scope.add(Binding(name, v[0], v[1], v[2], "substitution", sid, getattr(n, "start", 0), getattr(n, "end", 0), wrapper=v[3]))
        self._dimension_check(base, item, sym_side, num_side)
        if not checkable:
            self.add(kind="sub", outcome="binding", pairs=tuple(introduced), formula=formula,
                     reason="values substituted into symbols the report binds nowhere else (they introduce the values)", **base)
            return
        self.add(kind="sub", outcome="check", pairs=tuple(checkable), formula=formula,
                 unbound=tuple(n for n, _x in introduced),
                 reason="substituted values against the stated bindings" + (f" of the formula in {formula.statement_id}" if formula else ""), **base)

    def _dimension_check(self, base: dict, item: MathItem, a: Node, b: Node) -> None:
        """ST-DIM-001/002 and unit notes for the relation about to be added (its index is the next one)."""
        notes: list = []
        da = dimension_of(a, self.scope, notes)
        db = dimension_of(b, self.scope, notes)
        sids = base["statement_ids"]
        nxt = len(self.relations)
        for whole, d1, d2 in notes:
            self.finding("ST-DIM-002", f"a sum or difference of terms with different dimensions ({d1} and {d2}) in '{render(whole)[:160]}'", sids,
                         getattr(whole, "start", 0), getattr(whole, "end", 0), check_index=nxt)
        if da is not None and db is not None and not da.same_physical(db):
            self.finding("ST-DIM-001", f"the two sides of '{render(a)[:120]} {base.get('op', '=')} {render(b)[:120]}' have different dimensions ({da} and {db})",
                         sids, base["start"], base["end"], check_index=nxt)
        for node in (a, b):
            for n in walk(node):
                if isinstance(n, (Quantity, WithUnit)):
                    self._unit_notes(n.unit, sids, getattr(n, "start", 0), getattr(n, "end", 0), nxt)

    def _value_notes(self, base: dict, node: Node) -> None:
        """ST-DIM-002 and unit notes for the written side of a binding (no check is planned for a
        binding, so these name the binding's statement only): '2.0 kg + 3.0 m', 'yr⁻¹', 'ms⁻¹'."""
        notes: list = []
        dimension_of(node, self.scope, notes)
        sids = base["statement_ids"]
        for whole, d1, d2 in notes:
            self.finding("ST-DIM-002", f"a sum or difference of terms with different dimensions ({d1} and {d2}) in '{render(whole)[:160]}'", sids,
                         getattr(whole, "start", 0), getattr(whole, "end", 0))
        for n in walk(node):
            if isinstance(n, (Quantity, WithUnit)):
                self._unit_notes(n.unit, sids, getattr(n, "start", 0), getattr(n, "end", 0))

    def _unit_notes(self, unit: UnitExpr, sids: tuple[str, ...], a: int, b: int, check_index: Optional[int] = None) -> None:
        key_sid = sids[-1] if sids else ""
        if unit.unknown and (key_sid, unit.text) not in self.unit_reported:
            self.unit_reported.add((key_sid, unit.text))
            self.finding("ST-UNIT-001", f"the unit '{unit.text}' is not recognised ({', '.join(unit.unknown)}); the relation is checked as written only", sids, a, b,
                         check_index=check_index)
        if unit.ambiguity_code == "ST-UNIT-002" and (key_sid, "amb:" + unit.text) not in self.unit_reported:
            self.unit_reported.add((key_sid, "amb:" + unit.text))
            self.finding("ST-UNIT-002", f"an ambiguous unit: {unit.ambiguity}; both readings are checked", sids, a, b, check_index=check_index)

    # -------------------------------------------------------------- sequences: steps and roots
    def _sequence(self, item: MathItem, chain: Chain, operands: list[tuple[Operand, str]], ops: list[str], lone: bool, head: Optional[Node],
                  bound_before: frozenset[str] = frozenset()) -> None:
        if self.request_mode:
            self.request_relations.append((operands[0][0], ops[0], operands[-1][0]))
            return
        first, last = _first(operands[0][0]), _first(operands[-1][0])
        if first is None or last is None or chain.lead == "label":
            self.prev_rel = None
            return
        rel_op = "=" if all(o == "=" for o in ops) else next((o for o in ops if o in _ORDER), ops[0])
        unknown = {n for n in _syms(first) | _syms(last) if not (n in bound_before and self.scope.is_given(n))}
        info = {"left": operands[0][0], "op": rel_op, "right": operands[-1][0], "sid": operands[0][1], "sids": tuple(dict.fromkeys(s for _o, s in operands)),
                "unknown": unknown, "syms": _syms(first) | _syms(last), "item": item, "lone": lone, "head": head, "order": self.order.get(item.statement_id, 0),
                "connective": chain.connective, "is_formula": lone and isinstance(head, Sym) and bool(_syms(last) - {getattr(head, "name", "")})}
        # roots: x = value (or a closed expression) after an equation in x
        if lone and isinstance(head, Sym) and rel_op == "=" and len(operands) >= 2:
            rhs = _first(operands[1][0])
            solved = head.name not in bound_before or not self.scope.is_given(head.name)
            if rhs is not None and is_closed(rhs) and solved:
                self._roots_candidate(item, chain, head, operands)
        prev = self.prev_rel
        if prev is not None and info["unknown"] and prev["unknown"] and prev["item"].part == item.part and rel_op != "≠" and prev["op"] != "≠":
            explicit = chain.connective in ("⇒", "∴") or any(w in chain.connective.split() for w in ("so", "hence", "therefore", "thus", "gives")) \
                or _has_step_word(item.gap_before)
            opens = item.stmt_kind in ("derivation", "display_row") or (item.stmt_kind == "sentence" and not item.gap_before.strip())
            prev_opens = prev["item"].stmt_kind in ("derivation", "display_row") or (prev["item"].stmt_kind == "sentence" and not prev["item"].gap_before.strip()) \
                or prev["item"].ends_statement
            adjacent = info["order"] - prev["order"] == 1 and opens and prev_opens
            same_span = prev["item"] is item
            or_joined = chain.connective in ("or", "and") or item.gap_before.strip().lower() in ("or", "and", ",")
            pure = all(n in prev["syms"] or n in bound_before for n in info["syms"])
            new_formula = info["is_formula"] and getattr(head, "name", "") not in prev["syms"]
            shares = bool(info["unknown"] & prev["syms"])
            evaluation = (lone and isinstance(head, Sym) and prev["lone"] and getattr(prev["head"], "name", None) == head.name
                          and len(operands) > 1 and is_closed(_first(operands[1][0]) or Sym("?"))) \
                or (lone and isinstance(head, Apply) and is_closed(head.arg))  # f(2) = … evaluates a function: no step
            if shares and not evaluation and not or_joined and not new_formula and ((explicit and (same_span or info["order"] - prev["order"] <= 1)) or (adjacent and pure)):
                if _has_func_of(_first(prev["left"]) or Sym("?"), prev["unknown"]) or _has_func_of(_first(prev["right"]) or Sym("?"), prev["unknown"]) \
                        or _has_func_of(first, info["unknown"]) or _has_func_of(last, info["unknown"]):
                    self._undecided("ST-UNDEC-001", "a step involving a function of an unknown",
                                    dict(statement_ids=tuple(dict.fromkeys(prev["sids"] + info["sids"])), start=operands[0][0].start, end=operands[-1][0].end,
                                         op=rel_op, left=operands[0][0], right=operands[-1][0], part=item.part, position=0, approx=False), item)
                else:
                    self._step(item, prev, info, operands, rel_op, explicit)
        # equations remembered for roots ('v = 3.0 m s⁻¹' binds v: it is no equation whose solutions follow)
        if rel_op == "=" and unknown and not (lone and isinstance(head, Sym) and is_closed(last)):
            self.equations.append(info)
        self.prev_rel = info

    def _step(self, item: MathItem, prev: dict, info: dict, operands: list[tuple[Operand, str]], rel_op: str, explicit: bool) -> None:
        """Plan an algebra (or inequality) step from ``prev`` to the relation of this chain. The
        relation of a chain for a step is its first link when that link is symbolic (``t = √(2s_y/g)``
        in ``t = √(2s_y/g) = √(2 × 45.0 / 9.81) = 3.03 s``), else the whole chain (first and last operands)."""
        left_op = operands[0][0]
        # the step is the chain's first link; later links evaluate it (x = ln 50 / ln 2 = … = 5.64: the step is x = ln 50 / ln 2)
        right_op = operands[1][0] if len(operands) > 1 else operands[-1][0]
        sids = tuple(dict.fromkeys(prev["sids"] + info["sids"]))
        pl, pr = _first(prev["left"]), _first(prev["right"])
        cl, cr = _first(left_op), _first(right_op)
        if pl is None or pr is None or cl is None or cr is None:
            return
        unknown = prev["unknown"] | info["unknown"]
        principal = False
        has_root = any(isinstance(n, Root) for n in walk(cl)) or any(isinstance(n, Root) for n in walk(cr))
        square_form = self._square_root_step(pl, pr, cl, cr)
        if has_root or square_form:
            principal = True
            plus_minus = any(isinstance(n, PlusMinus) for n in walk(cr)) or any(isinstance(n, PlusMinus) for n in walk(cl))
            text = item.context() + " " + prev["item"].context() + " " + self._request_lower
            restricted = any(w in text for w in _RESTRICT_WORDS)
            if self.profile.is_mathematics and not plus_minus and not restricted:
                self.finding("ST-ALG-001", f"the step to '{render(cl)} = {render(cr)}' takes only the non-negative square root and no domain restriction is "
                                           f"stated; the algebra is checked under that side condition", sids, left_op.start, right_op.end,
                             check_index=len(self.relations))
        elif len(unknown) == 1:
            x = next(iter(unknown))
            dp, dc = max(_degree(pl, x), _degree(pr, x)), max(_degree(cl, x), _degree(cr, x))
            if dp == 2 and dc < dp:
                self.add(kind="case", outcome="context", statement_ids=sids, start=left_op.start, end=right_op.end, op=rel_op, left=left_op, right=right_op,
                         part=item.part, premise_left=prev["left"], premise_op=prev["op"], premise_right=prev["right"], premise_ids=prev["sids"],
                         reason="one case of the solutions of the preceding equation (its roots are checked by stem-sol)")
                return
        kind = "cmp" if (rel_op in _ORDER or prev["op"] in _ORDER) else "alg"
        self.add(kind=kind, outcome="check", statement_ids=sids, start=left_op.start, end=right_op.end, op=rel_op, left=left_op, right=right_op,
                 premise_left=prev["left"], premise_op=prev["op"], premise_right=prev["right"], premise_ids=prev["sids"], explicit=explicit, part=item.part,
                 principal_root=principal,
                 reason="the step follows from the preceding relation" + (" (stated with a connective)" if explicit else " (consecutive lines)")
                 + ("; the principal (non-negative) root is taken" if principal else ""))

    @staticmethod
    def _square_root_step(pl: Node, pr: Node, cl: Node, cr: Node) -> bool:
        """``E² = c`` followed by ``E = d`` (either side order): the step takes one square root."""
        for a, b in ((pl, pr), (pr, pl)):
            if isinstance(a, Pow) and a.exp == 2 and is_closed(b):
                base_key = shape_key(a.base)
                for x, y in ((cl, cr), (cr, cl)):
                    if shape_key(x) == base_key and is_closed(y):
                        return True
        return False

    def _is_root_symbol(self, name: str) -> bool:
        return any(name in eq["unknown"] and len(eq["unknown"]) == 1 for eq in self.equations[-8:])

    def _roots_candidate(self, item: MathItem, chain: Chain, head: Sym, operands: list[tuple[Operand, str]]) -> None:
        root = _first(operands[1][0])
        if root is None or not is_closed(root):
            return
        x = head.name
        eq = None
        for cand in reversed(self.equations[-12:]):
            if cand["unknown"] == {x} and cand["item"].part == item.part:
                l, r = _first(cand["left"]), _first(cand["right"])
                if l is not None and r is not None and max(_degree(l, x), _degree(r, x)) >= 2:
                    eq = cand
                    break
        source = "answer"
        if eq is None:
            for l_op, op, r_op in self.request.relations:
                l, r = _first(l_op), _first(r_op)
                if op == "=" and l is not None and r is not None and (_syms(l) | _syms(r)) == {x} and max(_degree(l, x), _degree(r, x)) >= 2:
                    eq = {"left": l_op, "op": "=", "right": r_op, "sids": ("request",), "item": item}
                    source = "request"
                    break
        if eq is None:
            return
        # group the roots of this statement: chains of the same item joined by 'or'/'and', or chains of the same statement
        sid = item.statement_id
        group = self._root_groups
        key = (sid, x)
        stmt_text = item.context()
        complete_phrase = any(p in stmt_text for p in _COMPLETE_PHRASES)
        restricted = any(w in stmt_text for w in _RESTRICT_WORDS) or self.request.restricts_domain
        if key in group:
            idx = group[key]
            rel = self.relations[idx]
            new = replace(rel, roots=rel.roots + (root,), end=max(rel.end, operands[1][0].end), complete=(rel.complete or chain.connective in ("or", "and")
                                                                                                             or "or" in item.gap_before.lower().split()) and not restricted)
            self.relations[idx] = new
            return
        complete = (complete_phrase or chain.connective in ("∴", "⇒")) and not restricted
        rel = self.add(kind="sol", outcome="check", statement_ids=tuple(dict.fromkeys(eq["sids"] + (sid,))) if source == "answer" else (sid,),
                       start=operands[0][0].start, end=operands[1][0].end, op="=", left=operands[0][0], right=operands[1][0], part=item.part,
                       premise_left=eq["left"], premise_op="=", premise_right=eq["right"], premise_ids=eq["sids"], root_symbol=x, roots=(root,),
                       complete=complete, restricted=restricted,
                       reason=f"stated roots of the equation in {', '.join(eq['sids'])}" + ("; the full solution set is claimed" if complete else ""))
        group[key] = rel.index

    # -------------------------------------------------------------- chemistry, Boolean, tables
    def _chem(self, item: MathItem) -> None:
        eq = item.chem
        if eq is None:
            return
        sids = (item.statement_id,)
        if not eq.readable:
            self.finding("ST-CHEM-001", f"the chemical equation '{eq.text[:120]}' cannot be read: {eq.error}; its balance is not checked", sids, eq.start, eq.end)
            self.add(kind="chem", outcome="undecided", statement_ids=sids, start=eq.start, end=eq.end, code="ST-CHEM-001", reason=eq.error, chem=eq, part=item.part)
            return
        if self.request_mode:
            return
        self.add(kind="chem", outcome="check", statement_ids=sids, start=eq.start, end=eq.end, op=eq.arrow, chem=eq, part=item.part,
                 reason="element and charge balance of the equation as written")

    def _boolean(self, item: MathItem, br: BoolRelation) -> None:
        if self.request_mode:
            return
        for name_side, expr_side in ((br.left, br.right), (br.right, br.left)):
            if br.op in ("=", "≡", "⇔") and isinstance(name_side, Sym) and name_side.name not in _syms(expr_side) and not isinstance(expr_side, Sym):
                # 'M = (A ∧ B) ∨ (A ∧ C) ∨ (B ∧ C)': a name given to an expression is a definition, not an identity to prove
                # (as a law is in arithmetic); a truth table whose column carries the name is checked against it
                self.bool_defs.setdefault(name_side.name, (expr_side, item.statement_id))
                self.add(kind="formula", outcome="formula", statement_ids=(item.statement_id,), start=br.start, end=br.end, op=br.op, part=item.part,
                         left=Operand((br.left,), br.start, br.end), right=Operand((br.right,), br.start, br.end),
                         reason=f"a Boolean definition of '{name_side.name}'")
                return
        self.add(kind="bool", outcome="check", statement_ids=(item.statement_id,), start=br.start, end=br.end, op=br.op, bool_rel=br, part=item.part,
                 left=Operand((br.left,), br.start, br.end), right=Operand((br.right,), br.start, br.end), reason="a Boolean identity")

    def _table(self, item: MathItem) -> None:
        t = item.table
        if t is None:
            return
        sids = (item.statement_id,)
        if t.error:
            self.finding(t.code or "ST-UNDEC-001", f"a truth table that cannot be checked: {t.error}", sids, t.start, t.end)
            self.add(kind="tt", outcome="undecided", statement_ids=sids, start=t.start, end=t.end, code=t.code or "ST-UNDEC-001", reason=t.error, table=t,
                     part=item.part)
            return
        if self.request_mode:
            return
        self.add(kind="tt", outcome="check", statement_ids=sids, start=t.start, end=t.end, table=t, part=item.part, reason="every stated row of the truth table")

    def _defined_columns(self) -> None:
        """A truth-table column headed by a name the answer defines as a Boolean expression of the table's other columns
        (``| A | B | C | M |`` with ``M = (A ∧ B) ∨ (A ∧ C) ∨ (B ∧ C)``) is that expression's output column."""
        if not self.bool_defs:
            return
        for idx, rel in enumerate(self.relations):
            t = rel.table
            if rel.kind != "tt" or rel.outcome != "check" or t is None or t.error:
                continue
            for j, name in enumerate(t.inputs):
                d = self.bool_defs.get(name)
                if d is None:
                    continue
                expr, sid = d
                others = set(t.inputs) - {name}
                if not _syms(expr) or not _syms(expr) <= others:
                    continue
                n_in = len(t.inputs)
                rows = tuple(r[:j] + r[j + 1:n_in] + (r[j],) + r[n_in:] for r in t.rows)
                table = replace(t, inputs=tuple(x for x in t.inputs if x != name), outputs=((name, expr),) + tuple(t.outputs), rows=rows)
                self.relations[idx] = replace(rel, table=table, statement_ids=tuple(dict.fromkeys(rel.statement_ids + (sid,))),
                                              reason=rel.reason + f"; the column '{name}' is checked against its definition in {sid}")
                break

    # -------------------------------------------------------------- prose results, givens, targets
    def _results(self) -> None:
        for pv in self.prose_values:
            if not _result_cue(pv.before):
                continue
            v = value_of(pv.node)
            if v is None:
                continue
            best = None
            for fv in reversed(self.final_values):
                if fv["order"] >= pv.statement_index:
                    continue
                if pv.part and fv["part"] and pv.part != fv["part"]:
                    continue
                fvv = value_of(fv["node"])
                if fvv is None:
                    continue
                if v[2] is not None and fvv[2] is not None:
                    d1, d2 = v[2].dim, fvv[2].dim
                    if d1 is None or d2 is None:
                        # a unit the table does not know ('kJ m⁻² yr⁻¹') pairs only with the same unit written the same way
                        if d1 is not None or d2 is not None or " ".join(v[2].text.split()) != " ".join(fvv[2].text.split()):
                            continue
                    elif not d1.same_physical(d2):
                        continue
                best = fv
                break
            if best is None:
                continue
            self.add(kind="res", outcome="check", statement_ids=tuple(dict.fromkeys((best["sid"], pv.statement_id))), start=pv.start, end=pv.end, op="=",
                     left=best["operand"], right=Operand((pv.node,), pv.start, pv.end), part=pv.part,
                     reason=f"a prose restatement against the final value of the chain in {best['sid']}")

    def _givens(self) -> None:
        req_by_symbol: dict[str, list[Binding]] = {}
        for b in self.request.bindings:
            req_by_symbol.setdefault(b.symbol, []).append(b)
        for name, blist in list(self.scope.bindings.items()):
            for b in blist:
                if b.source != "given":
                    continue
                cands: list[Binding] = list(req_by_symbol.get(name, []))
                if not cands and b.unit is not None and b.unit.dim is not None and not b.unit.unknown:
                    for node, a0, b0 in self.request.quantities:
                        v = value_of(node)
                        if v is None or v[2] is None or v[1] is None or v[2].dim is None:
                            continue
                        if v[2].dim.same_physical(b.unit.dim):
                            cands.append(Binding(name, v[0], v[1], v[2], "request", "request", a0, b0, wrapper=v[3]))
                if not cands:
                    continue
                node = Quantity(b.number, b.unit, b.start, b.end) if b.unit is not None else Num(b.number, b.start, b.end)
                self.add(kind="giv", outcome="check", statement_ids=(b.statement_id,), start=b.start, end=b.end, op="=", right=Operand((node,), b.start, b.end),
                         left=Operand((Sym(name, start=b.start, end=b.start),), b.start, b.start), candidates=tuple(cands[:8]),
                         reason=f"the Given value of {name} against " + ("the request's binding of the same symbol" if name in req_by_symbol else
                                                                          "the request's quantities of the same dimension"))

    def _targets(self) -> None:
        for tgt in self.request.targets:
            tv = value_of(tgt.node)
            if tv is None:
                continue
            best = None
            for fv in reversed(self.final_values):
                fvv = value_of(fv["node"])
                if fvv is None:
                    continue
                if tv[2] is not None and fvv[2] is not None:
                    d1, d2 = tv[2].dim, fvv[2].dim
                    if d1 is None or d2 is None or not d1.same_physical(d2):
                        continue
                best = fv
                break
            if best is None:
                continue
            self.add(kind="tgt", outcome="check", statement_ids=(best["sid"],), start=best["operand"].start, end=best["operand"].end, op="≈" if tgt.approx else "=",
                     left=best["operand"], right=Operand((tgt.node,), tgt.start, tgt.end), approx=tgt.approx,
                     reason=f"the answer's final value against the show-that target '{tgt.text[:80]}'")


def _exact_fraction(node: Node) -> Optional[Node]:
    """``1/3``, ``-2/3``, ``\frac{5}{12}``: a fraction of two written integers as one exact number
    (built from the integer pair, never by evaluating text). None for anything else."""
    sign = 1
    cur = node
    if isinstance(cur, Neg):
        sign, cur = -1, cur.arg
    if not (isinstance(cur, BinOp) and cur.op == "/" and isinstance(cur.left, Num) and isinstance(cur.right, Num)):
        return None
    a, b = cur.left.number, cur.right.number
    if a.has_point or b.has_point or a.scientific or b.scientific or a.base != 10 or b.base != 10 or b.value == 0 or a.value.denominator != 1 \
            or b.value.denominator != 1:
        return None
    value = Fraction(int(a.value), int(b.value)) * sign
    text = f"{'-' if sign < 0 else ''}{a.text}/{b.text}"
    return Num(ExactNumber(text=text, value=value, sig_figs=max(a.sig_figs, b.sig_figs), last_place=0, exact=True, vulgar=True), getattr(node, "start", 0),
               getattr(node, "end", 0))


def _anchor_pairs(sym_side: Node, num_side: Node) -> list[tuple[str, Node]]:
    """Symbol readings from function applications that match by name and order on both sides
    (``sin θ`` against ``sin 30°`` reads θ as 30°), when the whole trees do not align."""
    fa = [n for n in walk(sym_side) if isinstance(n, Func)]
    fb = [n for n in walk(num_side) if isinstance(n, Func)]
    if not fa or len(fa) != len(fb) or any(x.name != y.name or x.base != y.base for x, y in zip(fa, fb)):
        return []
    out: list[tuple[str, Node]] = []
    for x, y in zip(fa, fb):
        pairs = align(x.arg, y.arg)
        if not pairs:
            continue
        for s, n in pairs:
            name = getattr(s, "name", "")
            if name and is_closed(n):
                out.append((name, n))
    return out


def _result_cue(before: str) -> bool:
    """A result cue (therefore, so, hence, thus, the answer is) in the same clause as the value and
    at most twelve words before it, and right before the value the cue itself, a verb or a
    qualifier, never a preposition (``so at 700 K`` is a condition)."""
    cut = max(before.rfind("."), before.rfind(";"), before.rfind("\n"), before.rfind(":"))
    clause = before[cut + 1:] if cut >= 0 else before
    words = _words(clause)[-12:]
    if not words:
        return False
    low = " ".join(words)
    if not any((" " + c + " ") in (" " + low + " ") for c in _RESULT_CUES):
        return False
    k = len(words) - 1
    while k >= 0 and words[k] in _QUALIFIERS:
        k -= 1
    if k < 0:
        return False
    last = words[k]
    if last in ("at", "as") and k >= 1 and words[k - 1] in _RESULT_PARTICIPLES:
        return True  # 'is therefore estimated at 240', 'works out at 3.2', 'is calculated as 0.42'
    if last in _PREPOSITIONS:
        return False
    return last in _RESULT_VERBS or last in ("therefore", "hence", "thus", "so") or last.endswith("s") and last not in _PREPOSITIONS


def plan_relations(items: list[MathItem], prose_values: list[ProseValue], scope: Scope, request: RequestReading, profile: StemProfile, *,
                   limits: StemLimits = DEFAULT_LIMITS, statement_order: Optional[dict[str, int]] = None,
                   code_items: Optional[list[tuple[str, int, int, str]]] = None, request_mode: bool = False) -> tuple[list[Relation], list[FrontEndFinding], list]:
    """Classify every link of ``items`` (in document order), record bindings and formulas in
    ``scope``, plan the checks and assign stable ids. Returns ``(relations, findings,
    request relations)``; the request mode records bindings, formulas and relations only."""
    order = statement_order or {}
    planner = _Planner(items, prose_values, scope, request, profile, limits, order, code_items or [], request_mode)
    planner.run()
    rels = planner.relations
    findings = list(planner.findings)
    if request_mode:
        return rels, findings, planner.request_relations
    # stable ids in document order, per kind; the per-report cap
    ordered = sorted((r for r in rels if r.outcome == "check"), key=lambda r: (r.start, r.end, r.index))
    counters: dict[str, int] = {}
    assigned: dict[int, str] = {}
    total = 0
    capped_ids: list[str] = []
    for r in ordered:
        counters[r.kind] = counters.get(r.kind, 0) + 1
        cid = f"stem-{r.kind}-{counters[r.kind]}"
        assigned[r.index] = cid
        total += 1
        if total > limits.max_checks_per_report:
            capped_ids.append(cid)
    out: list[Relation] = []
    capped_set = set(capped_ids)
    for r in rels:
        cid = assigned.get(r.index, "")
        out.append(replace(r, check_id=cid, capped=cid in capped_set))
    if capped_ids:
        findings.append(FrontEndFinding("ST-LIM-002", ST_SEVERITY["ST-LIM-002"], f"{total} STEM checks were planned; the cap is {limits.max_checks_per_report}, so "
                                        f"{len(capped_ids)} are not checked (first unchecked: {', '.join(capped_ids[:8])})",
                                        tuple(dict.fromkeys(s for r in out if r.capped for s in r.statement_ids))[:32]))
    # findings that named a planned relation by its index now name its check id
    by_index = {r.index: r.check_id for r in out}
    findings = [replace(f, check_id=by_index.get(int(f.check_id[1:]), "")) if f.check_id.startswith("#") else f for f in findings]
    return out, findings, planner.request_relations
