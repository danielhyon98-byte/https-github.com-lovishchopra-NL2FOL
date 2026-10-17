"""What a premise's numeric content is, and whether a record STATES it: the whole-content rule of task and source authority.

A grounding check may confer task or source authority on a premise (``grounding.verified=True``: established) only when it
verifies the premise's WHOLE content, never only that the premise's numerals occur in a record. Numeric content comes in
two shapes (:func:`numeric_shape`):

* an **assignment**: every conjunct compares one symbol with one literal (``d = 120``, ``limit = 350``, ``n >= 5``). Its
  content is that the symbol takes the stated figure (or keeps the stated bound). A record verifies it when it states the
  figure (typed: value, unit, the reading the symbol declares) in a way that establishes the comparison
  (:func:`stated_as`): an equality on a figure stated plainly, approximately or as an inclusive bound (the bound's own
  value: "at most 350 words" states ``limit = 350``); a bound on a figure stated so that it implies that bound ("at least
  5" or "5" states ``n >= 5``), or at an end of the interval a figure stated as rounded states ("x is 0.33 to 2 decimal
  places" states ``x >= 0.325 and x < 0.335``, both ends from that one figure); never on a figure stated as a strict
  bound for an equality ("more than 17" states no ``n = 17``), on a figure negated or excluded where it stands ("≠ 17",
  "other than 17"), or on one option of a disjunction or one end of a range ("17 or 18", "between 15 and 17");
* a **relation**: every other premise with numeric content: arithmetic over symbols or figures (``speed = d * 8``), a
  comparison of two terms (``words <= limit``), an inequation (``x != 5``), a comparison inside a logical formula
  (``(n = 17) -> b``). A figure of a relation that occurs in a record says nothing about the relation: the ``8`` of "120
  km in 8 hours" is no evidence for ``speed = d * 8`` (nor for ``speed = d / 8``). A record verifies a relation only when
  it STATES the same relation as a formula (:func:`stated_relation`), as a given.

The formula reader is closed and evaluates nothing: identifiers, numbers, ``+ - − × * · / ÷``, parentheses and ``= ≠ <
> ≤ ≥ <= >= !=``; implicit multiplication (``2t``), powers, roots and anything else end or void a formula. A stated
formula is compared with the premise's expression as a term (:func:`relation_key`): sums and products in any order, ``a
- b`` as ``a + (-1)·b``, ``a / b`` as ``a · b⁻¹``, numbers by exact value (``d / 8`` is ``0.125 · d``), ``>`` and ``>=``
read from the other side; its identifiers are the problem's symbol names (case aside). It counts only where its sentence
gives it: asserted (the assertion reader positively recognises the clause, :func:`.assertion.assertion_at`), or opened by
an instruction or supposition that sets the task's terms ("Let", "Use", "Define", "Suppose", ...). A formula in a
question, a claim to test or prove ("Show that", "Check whether"), a condition, a negation, a possibility, an attribution
or any construction the reader does not recognise states nothing.

Premises with no numeric content (propositions) keep the span rule of :mod:`.grounding`: a located excerpt is the
reference, and fidelity to it is the reviewer's question. Cost: a text's formulas are found once per text (bounded by
:data:`~.quantities.MAX_TEXT_CHARS`, each formula by :data:`MAX_FORMULA_TOKENS`) and cached.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Literal, Optional, Sequence

from .quantities import MAX_TEXT_CHARS, SourceText

__all__ = ["NumericShape", "numeric_shape", "assignment_parts", "relation_key", "StatedRelation", "stated_relation", "writes_relation",
           "formulas_in", "MAX_FORMULA_TOKENS", "GIVEN_WORDS", "TEST_WORDS"]

NumericShape = Literal["none", "assignment", "relation"]

#: Operators of the IR's arithmetic and comparison (a node with any of them has numeric content).
_ARITH = frozenset({"add", "sub", "mul", "neg", "div", "idiv", "mod", "to_real"})
_COMPARE = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})
_LITERAL = frozenset({"int", "real"})
#: The comparison an assignment states, read from the symbol's side ("17 > n" is "n < 17").
_FLIP = {"eq": "eq", "ne": "ne", "lt": "gt", "le": "ge", "gt": "lt", "ge": "le"}
#: The longest operand of a stated formula, in tokens (a longer one is not read).
MAX_FORMULA_TOKENS = 64
#: Sentence-opening words that set the task's terms: a formula they open is a given of the task.
GIVEN_WORDS = frozenset("""
let lets let's suppose supposing assume assuming define denote take put use set fix write call label treat regard interpret consider imagine say
""".split())
#: Instructions that make what follows a claim to test, prove or explain, never a given.
TEST_WORDS = frozenset("""
show prove verify check decide determine evaluate test disprove explain justify confirm establish deduce derive demonstrate examine investigate
assess discuss find calculate compute estimate solve
""".split())


def _children(node) -> list:
    out = []
    for key in ("arg", "left", "right", "cond", "then", "otherwise"):
        child = getattr(node, key, None)
        if child is not None:
            out.append(child)
    out.extend(getattr(node, "args", None) or ())
    return out


def _has_numeric(node) -> bool:
    stack = [node]
    while stack:
        n = stack.pop()
        op = getattr(n, "op", None)
        if op in _LITERAL or op in _ARITH or op in _COMPARE:
            return True
        stack.extend(_children(n))
    return False


def _symbol_of(node) -> Optional[str]:
    op = getattr(node, "op", None)
    if op == "var":
        return node.name
    if op == "to_real" and getattr(node.arg, "op", None) == "var":
        return node.arg.name
    return None


def _is_literal(node) -> bool:
    op = getattr(node, "op", None)
    if op in _LITERAL:
        return True
    return op == "neg" and getattr(node.arg, "op", None) in _LITERAL


def _conjuncts(expr) -> list:
    out, stack = [], [expr]
    while stack:
        n = stack.pop()
        if getattr(n, "op", None) == "and":
            stack.extend(reversed(n.args))
        else:
            out.append(n)
    return out


def assignment_parts(expr) -> Optional[list[tuple[str, str, object]]]:
    """``[(symbol, comparison from the symbol's side, literal node)]`` when every conjunct of ``expr`` compares one symbol
    with one literal by ``eq``, ``lt``, ``le``, ``gt`` or ``ge`` (an assignment); otherwise None. An inequation (``ne``) is
    a relation: a figure stated in a record establishes no exclusion of it."""
    parts: list[tuple[str, str, object]] = []
    for c in _conjuncts(expr):
        op = getattr(c, "op", None)
        if op not in _COMPARE or op == "ne":
            return None
        left, right = c.left, c.right
        if _symbol_of(left) is not None and _is_literal(right):
            parts.append((_symbol_of(left), op, right))  # type: ignore[arg-type]
        elif _symbol_of(right) is not None and _is_literal(left):
            parts.append((_symbol_of(right), _FLIP[op], left))  # type: ignore[arg-type]
        else:
            return None
    return parts or None


def numeric_shape(expr) -> NumericShape:
    """``none`` (no literal, no arithmetic, no comparison: a proposition), ``assignment`` (:func:`assignment_parts`) or
    ``relation`` (any other numeric content)."""
    if not _has_numeric(expr):
        return "none"
    return "assignment" if assignment_parts(expr) is not None else "relation"


# ------------------------------------------------------------------ terms

def _key(term) -> str:
    kind = term[0]
    if kind == "num":
        return f"n:{term[1]}"
    if kind == "var":
        return f"v:{term[1]}"
    if kind == "inv":
        return f"i({_key(term[1])})"
    return f"{kind}({','.join(_key(t) for t in term[1])})"


def _num(v: Fraction):
    return ("num", v)


def _add(terms):
    flat = []
    for t in terms:
        if t is None:
            return None
        flat.extend(t[1] if t[0] == "add" else (t,))
    total = sum((t[1] for t in flat if t[0] == "num"), Fraction(0))
    rest = sorted((t for t in flat if t[0] != "num"), key=_key)
    if total != 0 or not rest:
        rest = rest + [_num(total)]
    return rest[0] if len(rest) == 1 else ("add", tuple(sorted(rest, key=_key)))


def _mul(terms):
    flat = []
    for t in terms:
        if t is None:
            return None
        flat.extend(t[1] if t[0] == "mul" else (t,))
    product = Fraction(1)
    for t in flat:
        if t[0] == "num":
            product *= t[1]
    if product == 0:
        return _num(Fraction(0))
    rest = sorted((t for t in flat if t[0] != "num"), key=_key)
    if product != 1 or not rest:
        rest = rest + [_num(product)]
    return rest[0] if len(rest) == 1 else ("mul", tuple(sorted(rest, key=_key)))


def _inv(t):
    if t is None:
        return None
    if t[0] == "num":
        return None if t[1] == 0 else _num(1 / t[1])
    if t[0] == "inv":
        return t[1]
    if t[0] == "mul":
        return _mul([_inv(x) for x in t[1]])
    return ("inv", t)


def _neg(t):
    return _mul([_num(Fraction(-1)), t])


def _ir_term(node, depth: int = 0):
    """The canonical term of an IR arithmetic expression, or None (an operation no stated formula can write)."""
    if depth > 60:
        return None
    op = getattr(node, "op", None)
    if op == "var":
        return ("var", node.name)
    if op in _LITERAL:
        try:
            return _num(Fraction(node.value))
        except (ValueError, ZeroDivisionError):
            return None
    if op == "neg":
        inner = _ir_term(node.arg, depth + 1)
        return None if inner is None else _neg(inner)
    if op == "to_real":
        return _ir_term(node.arg, depth + 1)
    if op == "add":
        return _add([_ir_term(a, depth + 1) for a in node.args])
    if op == "sub":
        left, right = _ir_term(node.left, depth + 1), _ir_term(node.right, depth + 1)
        return None if left is None or right is None else _add([left, _neg(right)])
    if op == "mul":
        return _mul([_ir_term(a, depth + 1) for a in node.args])
    if op == "div":
        left, right = _ir_term(node.left, depth + 1), _ir_term(node.right, depth + 1)
        return None if left is None or right is None else _mul([left, _inv(right)])
    return None


def _relation(op: str, left, right) -> Optional[str]:
    if left is None or right is None:
        return None
    if op in ("gt", "ge"):
        op, left, right = {"gt": "lt", "ge": "le"}[op], right, left
    if op in ("eq", "ne"):
        a, b = sorted((_key(left), _key(right)))
        return f"{op}[{a}|{b}]"
    return f"{op}[{_key(left)}|{_key(right)}]"


def relation_key(expr) -> Optional[str]:
    """The canonical form of a premise that is one comparison of arithmetic terms (see the module docstring), or None
    when the premise is no such comparison (a logical formula over comparisons, an integer division, a remainder)."""
    op = getattr(expr, "op", None)
    if op not in _COMPARE:
        return None
    return _relation(op, _ir_term(expr.left), _ir_term(expr.right))


# ------------------------------------------------------------------ stated formulas

_TOKEN_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)"
    r"|(?P<ident>[A-Za-z][A-Za-z0-9_]*)"
    r"|(?P<rel><=|>=|!=|≤|≥|≠|=|<|>)"
    r"|(?P<op>[+\-−–×*·⋅/÷])"
    r"|(?P<lp>\()|(?P<rp>\))"
    r"|(?P<ws>[ \t]+)"
    r"|(?P<other>.)", re.S)
_OPS = {"+": "+", "-": "-", "−": "-", "–": "-", "×": "*", "*": "*", "·": "*", "⋅": "*", "/": "/", "÷": "/"}
#: Punctuation that may stand before or after a formula; any other sign beside it is part of a notation the reader does
#: not read, so no formula is read there.
_OPENERS = frozenset("([{\"'“‘,;:")
_CLOSERS = frozenset(")]}\"'”’.,;:!?")
_RELS = {"=": "eq", "!=": "ne", "≠": "ne", "<": "lt", ">": "gt", "<=": "le", "≤": "le", ">=": "ge", "≥": "ge"}


@dataclass(frozen=True)
class _Tok:
    kind: str
    text: str
    start: int
    end: int
    space_before: bool


@dataclass(frozen=True)
class Formula:
    """A comparison a text writes, as the closed reader parses it: ``key`` (:func:`relation_key` form), the characters it
    spans and the start of its right-hand side (where its sentence is read)."""
    key: str
    start: int
    end: int
    right_start: int
    right_end: int


def _tokens(text: str) -> list[_Tok]:
    out: list[_Tok] = []
    space = True
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup or "other"
        if kind == "ws":
            space = True
            continue
        out.append(_Tok(kind, m.group(0), m.start(), m.end(), space))
        space = kind == "other"
    return out


class _Parse:
    """A recursive-descent reader of one operand over tokens ``[i, j)``: sums of products of signed atoms (numbers,
    identifiers, parenthesised operands). It builds a term; it evaluates nothing."""

    def __init__(self, toks: list[_Tok], i: int, j: int) -> None:
        self.toks, self.i, self.j, self.depth = toks, i, j, 0

    def peek(self) -> Optional[_Tok]:
        return self.toks[self.i] if self.i < self.j else None

    def expr(self):
        self.depth += 1
        if self.depth > 24:
            raise ValueError("too deep")
        terms = [self.term()]
        while (t := self.peek()) is not None and t.kind == "op" and _OPS[t.text] in "+-":
            self.i += 1
            nxt = self.term()
            terms.append(nxt if _OPS[t.text] == "+" else _neg(nxt))
        self.depth -= 1
        return _add(terms)

    def term(self):
        factors = [self.unary()]
        while (t := self.peek()) is not None and t.kind == "op" and _OPS[t.text] in "*/":
            self.i += 1
            nxt = self.unary()
            factors.append(nxt if _OPS[t.text] == "*" else _inv(nxt))
        return _mul(factors)

    def unary(self):
        t = self.peek()
        if t is not None and t.kind == "op" and _OPS[t.text] == "-":
            self.i += 1
            return _neg(self.unary())
        return self.atom()

    def atom(self):
        t = self.peek()
        if t is None:
            raise ValueError("operand expected")
        self.i += 1
        if t.kind == "num":
            nxt = self.peek()
            if nxt is not None and not nxt.space_before and nxt.kind in ("ident", "num", "lp"):
                raise ValueError("implicit multiplication")
            return _num(Fraction(t.text))
        if t.kind == "ident":
            nxt = self.peek()
            if nxt is not None and not nxt.space_before and nxt.kind in ("num", "lp"):
                raise ValueError("a function or an implicit product")
            return ("var", t.text.lower())
        if t.kind == "lp":
            inner = self.expr()
            close = self.peek()
            if close is None or close.kind != "rp":
                raise ValueError("unbalanced")
            self.i += 1
            nxt = self.peek()
            if nxt is not None and not nxt.space_before and nxt.kind in ("ident", "num", "lp"):
                raise ValueError("implicit multiplication")
            return inner
        raise ValueError("operand expected")


def _operand_end(toks: list[_Tok], i: int, limit: int) -> int:
    """The end of the longest operand that starts at token ``i`` (operands and binary operators alternating, signs and
    balanced parentheses allowed), or ``i`` when none starts there."""
    k, need_operand, depth, last_ok = i, True, 0, i
    while k < limit:
        t = toks[k]
        if need_operand:
            if t.kind == "op" and _OPS[t.text] == "-":
                k += 1  # a sign
                continue
            if t.kind in ("num", "ident"):
                k += 1
                need_operand = False
                if depth == 0:
                    last_ok = k
                continue
            if t.kind == "lp":
                depth += 1
                k += 1
                continue
            break
        if t.kind == "rp" and depth > 0:
            depth -= 1
            k += 1
            if depth == 0:
                last_ok = k
            continue
        if t.kind == "op":
            k += 1
            need_operand = True
            continue
        break
    return last_ok


def _operand_start(toks: list[_Tok], j: int, limit: int) -> int:
    """The start of the longest operand that ends right before token ``j`` (read backwards), or ``j`` when none does."""
    k, need_operand, depth, first_ok = j - 1, True, 0, j
    while k >= limit:
        t = toks[k]
        if need_operand:
            if t.kind in ("num", "ident"):
                need_operand = False
                if depth == 0:
                    first_ok = k
                k -= 1
                continue
            if t.kind == "rp":
                depth += 1
                k -= 1
                continue
            break
        # an operand has just been read (backwards): an opening parenthesis, a sign or a binary operator may come before it
        if t.kind == "lp" and depth > 0:
            depth -= 1
            if depth == 0:
                first_ok = k
            k -= 1
            continue
        if t.kind == "op":
            prev = toks[k - 1] if k - 1 >= limit else None
            if _OPS[t.text] == "-" and (prev is None or prev.kind not in ("num", "ident", "rp")):
                if depth == 0:
                    first_ok = k  # a sign: "-d" is still one operand
                k -= 1
                continue
            k -= 1
            need_operand = True
            continue
        break
    return first_ok


def _adjoins_before(prev: _Tok, first: _Tok) -> bool:
    """Whether the token before an operand could be a factor of it written without an operator ("2 v", "2v", "(x) v",
    "a v"): a number, a closing parenthesis, a one-letter identifier, or anything glued to it."""
    if not first.space_before:
        return prev.kind in ("num", "ident", "rp")
    return prev.kind in ("num", "rp") or (prev.kind == "ident" and len(prev.text) == 1)


def _adjoins_after(last: _Tok, nxt: _Tok) -> bool:
    """Whether the token after an operand could be a factor of it written without an operator ("s = 2 t", "s = 2t",
    "v = d t", "v = d (2)"): a number, an opening parenthesis, a one-letter identifier, or anything glued to it."""
    if not nxt.space_before:
        return nxt.kind in ("num", "ident", "lp")
    return nxt.kind in ("num", "lp") or (nxt.kind == "ident" and len(nxt.text) == 1)


@lru_cache(maxsize=256)
def formulas_in(text: str) -> tuple[Formula, ...]:
    """Every comparison of two operands ``text`` writes (see the module docstring), in order. An operand that adjoins a
    further operand without an operator ("s = 2 t", "2v = d") makes the reading uncertain, so no formula is read there."""
    toks = _tokens(text[:MAX_TEXT_CHARS])
    out: list[Formula] = []
    for r, tok in enumerate(toks):
        if tok.kind != "rel":
            continue
        lo = max(0, r - MAX_FORMULA_TOKENS)
        hi = min(len(toks), r + 1 + MAX_FORMULA_TOKENS)
        a = _operand_start(toks, r, lo)
        b = _operand_end(toks, r + 1, hi)
        if a == r or b == r + 1:
            continue
        if a > 0 and _adjoins_before(toks[a - 1], toks[a]):
            continue
        if b < len(toks) and _adjoins_after(toks[b - 1], toks[b]):
            continue
        if a > 0 and toks[a - 1].kind in ("rel", "op"):
            continue  # a chained comparison or an arrow ("a = b = c", "=>"): no single relation is stated
        if b < len(toks) and toks[b].kind in ("rel", "op"):
            continue
        if a > 0 and toks[a - 1].kind == "other" and toks[a - 1].text not in _OPENERS:
            continue  # a sign the reader does not read ("√x = 2", "|x| = 2")
        if b < len(toks) and toks[b].kind == "other" and toks[b].text not in _CLOSERS:
            continue  # a power, a root, a percentage, a factorial ("v = d ^ 2", "A = s²", "p = 5%")
        try:
            left_p = _Parse(toks, a, r)
            left = left_p.expr()
            right_p = _Parse(toks, r + 1, b)
            right = right_p.expr()
        except (ValueError, ZeroDivisionError):
            continue
        if left_p.i != r or right_p.i != b or left is None or right is None:
            continue
        key = _relation(_RELS[tok.text], left, right)
        if key is not None:
            out.append(Formula(key=key, start=toks[a].start, end=toks[b - 1].end, right_start=toks[r + 1].start, right_end=toks[b - 1].end))
    return tuple(out)


@dataclass(frozen=True)
class StatedRelation:
    """Where a record states a premise's relation as a given: the source, the formula's characters and its words."""
    source: SourceText
    start: int
    end: int

    @property
    def written(self) -> str:
        return self.source.text[self.start:self.end]

    def where(self) -> str:
        label = {"claim": "claim", "supporting_claim": "supporting claim", "supplied_text": "supplied text", "task": "task"}.get(self.source.kind, self.source.kind)
        return f"{label} {self.source.ident} characters {self.start}-{self.end} ({self.written!r})"


def _given(text: str, f: Formula) -> bool:
    """Whether the sentence that writes formula ``f`` gives it: asserted (the reader positively recognises the clause), or
    governed only by the word that opens the sentence and sets the task's terms (:data:`GIVEN_WORDS`, never one of
    :data:`TEST_WORDS`: "Let c = 3 + 2 × k", not "Show that c = 3 + 2 × k"); a supposition reported inside a sentence
    ("students assume c = ...") gives nothing."""
    from .assertion import assertion_at, sentence_cue_at  # imported here: the reader imports this package's quantities
    reading = assertion_at(text, f.right_start, f.right_end)
    if reading.asserted:
        return True
    opening = sentence_cue_at(text, f.right_start)
    if opening is None or reading.mood not in ("instruction", "supposition") or reading.cue_start != opening[2]:
        return False
    word = opening[1].lower()
    return word in GIVEN_WORDS and word not in TEST_WORDS


def writes_relation(expr, text: str) -> bool:
    """Whether ``text`` writes the relation of premise ``expr`` as a formula at all (given or not): used to require that an
    elided quotation's own words hold the relation it is cited for."""
    key = relation_key(expr)
    if key is None:
        return False
    quoted = text.replace("...", " ; ").replace("\u2026", " ; ")  # an elision mark separates fragments, as a semicolon would
    return any(f.key == key for f in formulas_in(quoted))


def stated_relation(expr, sources: Sequence[SourceText], *, within: Optional[tuple[int, int]] = None) -> Optional[StatedRelation]:
    """Where one of ``sources`` states the relation of premise ``expr`` as a given (module docstring), or None. With
    ``within`` only formulas inside those characters of each source count (a located excerpt)."""
    key = relation_key(expr)
    if key is None:
        return None
    for src in sources:
        for f in formulas_in(src.text):
            if f.key != key:
                continue
            if within is not None and not (within[0] <= f.start and f.end <= within[1]):
                continue
            if _given(src.text, f):
                return StatedRelation(source=src, start=f.start, end=f.end)
    return None
