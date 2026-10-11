"""Boolean expressions and truth tables (Computer Science; section 4.8 of docs/STEM_DESIGN.md).

* Expressions with ``∧ ∨ ¬ ⊕``, the words ``AND OR NOT XOR`` (the lexer reads them in the
  Computer Science profile), and ``·``, ``*`` and ``+`` in Boolean context, negation by
  ``¬``, ``NOT``, a postfix prime (``A′``, ``A'``) or an overline (``\\overline{A}``).
  Variables are single capital letters; a glued run of capitals (``AB``) is their AND.
  Precedence, lowest first: equivalence (``=``, ``≡``, ``⇔``) between two expressions, OR,
  XOR, AND, NOT.
* Boolean context: the profile is Computer Science and the span uses a Boolean operator,
  or every identifier is a single capital letter (with primes) and every number is 0 or 1.
* Truth tables of at most ``max_truth_table_inputs`` inputs (32 rows): a Markdown table or
  a plain block whose header names the input letters and one or more output expressions
  and whose rows hold 0/1 or T/F. Each stated output becomes part of one ``stem-tt`` check.
* Based numerals (``FF₁₆``, ``0b1010``) are read by the lexer; ``FF₁₆ = 255`` is a
  ``stem-base`` relation.

Code is never read for meaning (ST-CODE-001 info). Nothing is evaluated here: the engine
decides every identity and every row.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .lexer import Token, lex
from .limits import DEFAULT_LIMITS, StemLimits
from .nodes import BoolOp, Node, Num, Sym
from .numbers import exact_integer
from .parser import ParseIssue

__all__ = ["BoolRelation", "TruthTable", "is_boolean_context", "parse_boolean", "parse_truth_table", "truth_table_shape"]

_EQUIV = frozenset({"=", "≡", "⇔"})
_TRUE = frozenset({"1", "T", "t", "true", "True", "TRUE"})
_FALSE = frozenset({"0", "F", "f", "false", "False", "FALSE"})


@dataclass(frozen=True)
class BoolRelation:
    left: Node
    op: str
    right: Node
    start: int
    end: int


@dataclass(frozen=True)
class TruthTable:
    """``inputs`` (letters), ``outputs`` (header text, parsed expression or None), ``rows`` of
    booleans (inputs then outputs). ``error`` with ``code`` is set when the table cannot be read
    or breaks the bound (ST-UNDEC-001 beyond five inputs)."""

    inputs: tuple[str, ...]
    outputs: tuple[tuple[str, Optional[Node]], ...]
    rows: tuple[tuple[bool, ...], ...]
    start: int
    end: int
    error: str = ""
    code: str = ""


def is_boolean_context(tokens: "tuple[Token, ...] | list[Token]", computer_science: bool) -> bool:
    if not computer_science or not tokens:
        return False
    if any(t.kind == "BOOL" for t in tokens):
        return True
    has_rel = any(t.kind == "REL" and t.text in _EQUIV for t in tokens)
    if not has_rel:
        return False
    for t in tokens:
        if t.kind == "IDENT" and not (t.text.isascii() and t.text.isupper() and not t.sub):
            return False
        if t.kind == "NUM" and t.text not in ("0", "1"):
            return False
        if t.kind in ("FUNC", "SUP", "CARET", "DSTAR", "LATEX", "TEXT"):
            return False
        if t.kind == "OP" and t.text not in ("+", "·", "*"):
            return False
    return any(t.kind == "IDENT" for t in tokens)


class _BoolParser:
    def __init__(self, toks: tuple[Token, ...], limits: StemLimits) -> None:
        self.t = toks
        self.i = 0
        self.lim = limits
        self.nodes = 0

    def peek(self) -> Optional[Token]:
        return self.t[self.i] if self.i < len(self.t) else None

    def _count(self, node: Node) -> Node:
        self.nodes += 1
        if self.nodes > self.lim.max_ast_nodes:
            raise ValueError(f"more than {self.lim.max_ast_nodes} nodes")
        return node

    def expr(self, d: int) -> Node:
        if d > self.lim.max_ast_depth:
            raise ValueError(f"nested deeper than {self.lim.max_ast_depth}")
        left = self.xor(d)
        while True:
            t = self.peek()
            if t is not None and ((t.kind == "BOOL" and t.text == "∨") or (t.kind == "OP" and t.text == "+")):
                self.i += 1
                right = self.xor(d)
                left = self._count(BoolOp("or", (left, right), _s(left), _e(right)))
            else:
                return left

    def xor(self, d: int) -> Node:
        left = self.conj(d)
        while True:
            t = self.peek()
            if t is not None and t.kind == "BOOL" and t.text == "⊕":
                self.i += 1
                right = self.conj(d)
                left = self._count(BoolOp("xor", (left, right), _s(left), _e(right)))
            else:
                return left

    def conj(self, d: int) -> Node:
        left = self.unary(d)
        while True:
            t = self.peek()
            if t is not None and ((t.kind == "BOOL" and t.text == "∧") or (t.kind == "OP" and t.text in ("·", "*"))):
                self.i += 1
                right = self.unary(d)
                left = self._count(BoolOp("and", (left, right), _s(left), _e(right)))
            elif t is not None and t.kind in ("IDENT", "LPAR", "UNSUP") and not (t.kind == "UNSUP" and t.text != "\\overline"):
                right = self.unary(d)  # juxtaposition: AB, A(B + C)
                left = self._count(BoolOp("and", (left, right), _s(left), _e(right)))
            else:
                return left

    def unary(self, d: int) -> Node:
        t = self.peek()
        if t is None:
            raise ValueError("an expression ends where an operand was expected")
        if t.kind == "BOOL" and t.text == "¬":
            self.i += 1
            arg = self.unary(d + 1)
            return self._count(BoolOp("not", (arg,), t.start, _e(arg)))
        node = self.primary(d)
        while True:
            p = self.peek()
            if p is not None and p.kind == "PRIME" and not p.space:
                self.i += 1
                for _ in range(int(p.value or 1) % 2):
                    node = self._count(BoolOp("not", (node,), _s(node), p.end))
                continue
            return node

    def primary(self, d: int) -> Node:
        t = self.peek()
        if t is None:
            raise ValueError("an expression ends where an operand was expected")
        if t.kind == "IDENT" and t.text.isascii() and t.text.isupper() and not t.sub:
            self.i += 1
            letters: list[Node] = [self._count(Sym(ch, start=t.start + k, end=t.start + k + 1)) for k, ch in enumerate(t.text)]
            if t.primes % 2 == 1:  # AB′ is A·(B′): the prime negates the letter it follows
                letters[-1] = self._count(BoolOp("not", (letters[-1],), _s(letters[-1]), t.end))
            node = letters[0]
            for nxt in letters[1:]:
                node = self._count(BoolOp("and", (node, nxt), _s(node), _e(nxt)))
            return node
        if t.kind == "NUM" and t.text in ("0", "1"):
            self.i += 1
            return self._count(Num(exact_integer(int(t.text)), t.start, t.end))
        if t.kind in ("LPAR", "LGROUP"):
            self.i += 1
            node = self.expr(d + 1)
            close = self.peek()
            if close is None or close.kind not in ("RPAR", "RGROUP"):
                raise ValueError("an unbalanced bracket")
            self.i += 1
            return node
        if t.kind == "UNSUP" and t.text in ("\\overline", "\\bar"):
            self.i += 1
            g = self.peek()
            if g is None or g.kind != "LGROUP":
                raise ValueError("an overline without a group")
            self.i += 1
            node = self.expr(d + 1)
            close = self.peek()
            if close is None or close.kind != "RGROUP":
                raise ValueError("an unbalanced overline group")
            self.i += 1
            return self._count(BoolOp("not", (node,), t.start, close.end))
        raise ValueError(f"unexpected {t.text!r} in a Boolean expression")


def _s(n: Node) -> int:
    return getattr(n, "start", 0)


def _e(n: Node) -> int:
    return getattr(n, "end", 0)


def parse_boolean(tokens: "tuple[Token, ...] | list[Token]", *, limits: StemLimits = DEFAULT_LIMITS) -> tuple[tuple[BoolRelation, ...], tuple[ParseIssue, ...]]:
    """Parse ``lhs (= | ≡ | ⇔) rhs`` relations (several separated by commas or connectives).
    Returns the relations and the issues (ST-PARSE-001); never raises."""
    toks = tuple(tokens)
    rels: list[BoolRelation] = []
    issues: list[ParseIssue] = []
    if len(toks) > limits.max_tokens_per_span:
        return (), (ParseIssue("ST-LIM-001", f"the span has more than {limits.max_tokens_per_span} tokens", toks[0].start, toks[-1].end),)
    # split at commas, semicolons and connective relations
    segments: list[list[Token]] = [[]]
    for t in toks:
        if t.kind in ("COMMA", "SEMI") or (t.kind == "REL" and t.text in ("⇒", "∴")) or (t.kind == "TEXT"):
            segments.append([])
        else:
            segments[-1].append(t)
    for seg in segments:
        if not seg:
            continue
        rel_idx = [k for k, t in enumerate(seg) if t.kind == "REL" and t.text in _EQUIV]
        if len(rel_idx) != 1:
            if rel_idx:
                issues.append(ParseIssue("ST-PARSE-001", "a Boolean chain with more than one equivalence sign", seg[0].start, seg[-1].end))
            continue
        k = rel_idx[0]
        try:
            lp = _BoolParser(tuple(seg[:k]), limits)
            left = lp.expr(0)
            if lp.i != k:
                raise ValueError("unexpected tokens before the equivalence sign")
            rp = _BoolParser(tuple(seg[k + 1:]), limits)
            right = rp.expr(0)
            if rp.i != len(seg) - k - 1:
                raise ValueError("unexpected tokens after the expression")
        except (ValueError, AssertionError) as exc:
            issues.append(ParseIssue("ST-PARSE-001", f"a Boolean expression outside the grammar: {exc}", seg[0].start, seg[-1].end))
            continue
        rels.append(BoolRelation(left, seg[k].text, right, seg[0].start, seg[-1].end))
    return tuple(rels), tuple(issues)


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")] if "|" in line else s.split()


def truth_table_shape(lines: list[str]) -> bool:
    """True when ``lines`` look like a truth table: a header of single-letter inputs followed by
    output expressions, then rows of 0/1 or T/F of the same width (a Markdown separator row is
    allowed)."""
    if len(lines) < 2:
        return False
    header = _cells(lines[0])
    if len(header) < 2 or not header[0].isalpha() or len(header[0]) != 1 or not header[0].isupper():
        return False
    body = [ln for ln in lines[1:] if not set(ln.strip()) <= set("|-: ")]
    if not body:
        return False
    for ln in body:
        cells = _cells(ln)
        if len(cells) != len(header) or not all(c in _TRUE or c in _FALSE for c in cells):
            return False
    return True


def parse_truth_table(text: str, rows: tuple[tuple[int, int], ...], *, limits: StemLimits = DEFAULT_LIMITS, computer_science: bool = True) -> Optional[TruthTable]:
    """Read a truth table from ``rows`` (line ranges of ``text``). None when the lines are not a
    truth table at all; a table with ``error`` when it is one but cannot be read in full."""
    lines = [text[a:b] for a, b in rows]
    if not truth_table_shape(lines):
        return None
    start, end = rows[0][0], rows[-1][1]
    header = _cells(lines[0])
    n_inputs = 0
    for h in header:
        if len(h) == 1 and h.isupper() and h.isalpha():
            n_inputs += 1
        else:
            break
    if n_inputs == 0:
        return None
    inputs = tuple(header[:n_inputs])
    if n_inputs > limits.max_truth_table_inputs:
        return TruthTable(inputs, (), (), start, end, error=f"a truth table with {n_inputs} inputs (bound {limits.max_truth_table_inputs})", code="ST-UNDEC-001")
    outputs: list[tuple[str, Optional[Node]]] = []
    error = ""
    header_line_start = rows[0][0]
    for h in header[n_inputs:]:
        k = text.find(h, header_line_start, rows[0][1])
        toks = lex(text, k, k + len(h), mode="plain", cs=computer_science, limits=limits).tokens if k >= 0 else ()
        node: Optional[Node] = None
        try:
            p = _BoolParser(tuple(toks), limits)
            node = p.expr(0) if toks else None
            if node is not None and p.i != len(toks):
                node = None
        except (ValueError, AssertionError):
            node = None
        if node is None:
            error = error or f"the output column {h!r} is not a Boolean expression of the inputs"
        outputs.append((h, node))
    body = [ln for ln in lines[1:] if not set(ln.strip()) <= set("|-: ")]
    table_rows: list[tuple[bool, ...]] = []
    width = len(header)
    for ln in body[: 2 ** n_inputs + 8]:
        cells = _cells(ln)
        if len(cells) != width:
            error = error or f"a row with {len(cells)} cells under a header of {width}"
            continue
        bad = next((c for c in cells if c not in _TRUE and c not in _FALSE), None)
        if bad is not None:
            error = error or f"a cell {bad[:12]!r} that is neither 0/1 nor T/F"
            continue
        table_rows.append(tuple(c in _TRUE for c in cells))
    if len(body) > 2 ** n_inputs + 8:
        error = error or f"more rows than a table of {n_inputs} inputs has"
    return TruthTable(inputs, tuple(outputs), tuple(table_rows), start, end, error=error, code="ST-UNDEC-001" if error else "")
