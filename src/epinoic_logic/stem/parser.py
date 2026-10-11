"""Bounded Pratt (precedence-climbing) parser over the closed grammar of section 4.5.

::

    sequence  := chain ( connective chain )*        connective: ⇒ ∴ , ; or and so hence gives ... (\\text{or})
    chain     := expr ( relop expr ){1,12}           (a chain may open with a relop: a continuation or a prose label)
    expr      := term ( ( + | - | ± | ∓ ) term )*
    term      := unary ( ( × | · | * | / | ÷ | juxtaposition ) unary )*
    unary     := ( - | + | ± | ¬ ) unary | power
    power     := postfix [ ( ^ | ** | superscript ) exponent ]       right-associative
    exponent  := signed integer literal (|n| ≤ 12) | ½ | 1/2          (½ is a square root)
    postfix   := primary [ % | ° | ! | × (magnification) | base subscript ]
    primary   := number [unit] | symbol | func_app | ( expr ) [unit] | { expr } | [ expr ]
               | \\frac{expr}{expr} | \\sqrt{expr} | √primary | | expr | | number : number

Implicit multiplication. A letter run (``mgh``, ``at``, ``xy``, ``PV``) is segmented by
the longest prefix over the names in scope (declared symbols, formula left-hand sides,
the STEM name table, recorded by the document's pre-pass); a run that matches no name
splits into single letters, except an all-capital run of three or four letters (``GPP``),
which is one name. When two segmentations both match the scope, both are kept as two
readings of the operand; with more than two, ST-PARSE-002 and the operand is not read.

Units. After a number (or a closing group that contains a number) a unit is read when the
unit token follows a space (or is ``\\text{…}``/``\\mathrm{…}``, ``Ω``, ``°C``) and ends the
operand: the next token is an operator, a relation, a close, a separator or the end. ``m
= 2.0 kg``: ``m`` is a symbol, ``kg`` a unit. A glued unit (``1.5kg``) is read only for a
common multi-letter unit that does not also split into names in scope, so ``2as`` stays
``2·a·s``. After a known unit atom, an unknown atom with an exponent (``yr⁻¹``) is kept as
an unknown unit (ST-UNIT-001).

Unsupported constructs are nodes, not failures: a fractional or symbolic power, ``!``,
``Σ``, ``∫``, ``lim``, ``d/dx`` and ``dy/dx``, ``f′(x)``, vectors, matrices, a tuple
``(x, y)``, ``i`` beside a number (complex), ``O(…)`` in Computer Science, an evaluation
bracket ``[F(x)]₀²``, infinity, an integer power beyond 12, a cube root. The relation that
holds one is named undecided (ST-UNDEC-001) with the reason.

Bounds. Token count (``max_tokens_per_span``), links per chain (``max_chain_links``),
nodes per operand (``max_ast_nodes``) and nesting depth (``max_ast_depth``, checked before
each descent, so recursion is bounded however deep the input nests). A broken bound or an
unreadable operand makes that operand an error (ST-LIM-001 / ST-PARSE-001) and the parser
resynchronises at the next relation sign; an unknown LaTeX command or a confusable letter
makes the whole span Unparsed (ST-PARSE-001, the command named). Nothing raises out of
:func:`parse_math`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from .chem import ELEMENTS, canonical_formula, latex_to_chem, parse_species
from .lexer import Token
from .limits import DEFAULT_LIMITS, PROFILES, StemLimits, StemProfile
from .nodes import (
    Abs, Apply, BinOp, BoolOp, Chain, Degrees, Func, Magnification, Neg, Node, Num, Operand, Percent, PlusMinus, Pow, Quantity, Ratio, Root,
    Sym, Unsupported, WithUnit, depth, shape_key, walk,
)
from .numbers import ExactNumber, exact_based, exact_integer
from .units import UnitExpr, is_unit_atom, parse_unit

__all__ = ["CONNECTIVE_WORDS", "ParseContext", "ParseIssue", "ParsedMath", "STEM_NAMES", "parse_math", "segment", "symbol_name"]

#: multi-letter names every STEM reading knows (section 4.6)
STEM_NAMES = frozenset({"KE", "PE", "GPE", "EPE", "EMF", "emf", "pH", "pOH", "pKa", "pKb", "Ka", "Kb", "Kw", "Kc", "Kp", "Mr", "Ar", "NA", "Ek", "Ep",
                        "RMM", "RFM", "NPP", "GPP"})
#: words that join two relations inside one math span (``\\text{or}``) or in a chain of statements
CONNECTIVE_WORDS = frozenset({"or", "and", "so", "hence", "therefore", "thus", "gives", "giving", "where", "with", "for", "if", "since", "because",
                              "then", "i.e.", "ie", "e.g.", "which", "as", "when", "implies", "or equivalently"})
_CONNECTIVE_RELS = frozenset({"⇒", "∴"})
#: connective words read as a bare letter run (no ``\\text``) when spaced off: never ``as``, ``if`` or ``for`` (a unit, a condition, a label)
_IDENT_CONNECTIVES = frozenset({"or", "and", "so", "hence", "therefore", "thus", "gives", "giving", "then", "implies"})
_ADD_OPS = frozenset({"+", "-", "±", "∓"})
_MUL_OPS = frozenset({"×", "·", "*", "/", "÷"})
_END_OF_OPERAND = frozenset({"REL", "OP", "RPAR", "RGROUP", "COMMA", "SEMI", "PUNCT", "AMP", "ROWSEP", "COLON", "BANG", "BOOL", "BAR", "QUOTE"})
_COMMON_GLUED_UNITS = frozenset({"kg", "km", "cm", "mm", "mol", "kJ", "kN", "kPa", "MPa", "MJ", "MW", "kW", "Hz", "kHz", "MHz", "eV", "keV", "MeV",
                                 "GeV", "mA", "mV", "kV", "µm", "μm", "nm", "Pa", "ms", "µs", "ns", "dm", "mL", "cm³", "min"})
_FUNCTION_LETTERS = frozenset({"f", "g", "h"})
_MAX_AMBIGUITY_REPARSES = 16
_MAX_SCAN = 4000


@dataclass(frozen=True)
class ParseIssue:
    code: str
    message: str
    start: int
    end: int


@dataclass(frozen=True)
class ParsedMath:
    """The chains of one math span with the issues found. ``unparsed`` is set when the whole span
    could not be read (an unknown LaTeX command, a confusable letter, too many tokens)."""

    chains: tuple[Chain, ...]
    issues: tuple[ParseIssue, ...] = ()
    unparsed: bool = False

    @property
    def relations(self) -> int:
        return sum(c.links for c in self.chains)


@dataclass(frozen=True)
class ParseContext:
    """What the parser needs besides the tokens: the reading view (for unit and label text),
    the names in scope, the profile, the bounds, the mode, and the prose label of a chain that
    opens with a relation sign (``Energy absorbed = …``)."""

    s: str
    names: frozenset[str] = frozenset()
    profile: StemProfile = field(default_factory=lambda: PROFILES["physics"])
    limits: StemLimits = DEFAULT_LIMITS
    mode: Literal["plain", "latex"] = "plain"
    lead_label: Optional[str] = None


class _OperandError(Exception):
    def __init__(self, code: str, message: str, start: int, end: int) -> None:
        super().__init__(message)
        self.code, self.message, self.start, self.end = code, message, start, end


def symbol_name(letters: str, sub: str = "", primes: int = 0, delta: bool = False) -> str:
    """The canonical name of a symbol: ``Δ`` prefix, letters, ``_sub``, primes (``Δv``, ``v_0``, ``E_k``, ``f'``)."""
    return ("Δ" if delta else "") + letters + (f"_{sub}" if sub else "") + ("'" * primes)


def segment(word: str, names: frozenset[str], limits: StemLimits = DEFAULT_LIMITS) -> list[tuple[str, ...]]:
    """Segmentations of a letter run over ``names`` (longest prefix first), at most three
    (the caller reports more than two as ST-PARSE-002). A run that matches no name splits into
    single letters, except an all-capital run of three or four letters, which is one name."""
    n = len(word)
    if n <= 1:
        return [(word,)]
    if n > limits.max_letter_run:
        return [(word,)]
    results: list[tuple[str, ...]] = []
    dead: set[int] = set()

    def rec(i: int, acc: list[str]) -> bool:
        if len(results) >= 3:
            return True
        if i == n:
            results.append(tuple(acc))
            return True
        if i in dead:
            return False
        found = False
        for length in range(n - i, 0, -1):
            piece = word[i:i + length]
            if piece in names:
                acc.append(piece)
                if rec(i + length, acc):
                    found = True
                acc.pop()
                if len(results) >= 3:
                    return True
        if not found:
            dead.add(i)
        return found

    rec(0, [])
    if results:
        return results
    if word.isupper() and 3 <= n <= 4:
        return [(word,)]
    return [tuple(word)]


class _Parser:
    def __init__(self, toks: tuple[Token, ...], ctx: ParseContext, choices: dict[int, int]) -> None:
        self.t = toks
        self.i = 0
        self.ctx = ctx
        self.lim = ctx.limits
        self.choices = choices
        self.amb: list[tuple[int, int, int, int]] = []  # (token index, alternatives, chain index, operand index)
        self.issues: list[ParseIssue] = []
        self.nodes = 0
        self.where = (0, 0)
        self.ambiguity_overflow: set[tuple[int, int]] = set()

    # ------------------------------------------------------------------ helpers
    def peek(self, k: int = 0) -> Optional[Token]:
        j = self.i + k
        return self.t[j] if 0 <= j < len(self.t) else None

    def _err(self, code: str, message: str, tok: Optional[Token] = None) -> _OperandError:
        tok = tok or self.peek() or (self.t[-1] if self.t else None)
        a = tok.start if tok else 0
        b = tok.end if tok else 0
        return _OperandError(code, message, a, b)

    def _count(self, node: Node) -> Node:
        self.nodes += 1
        if self.nodes > self.lim.max_ast_nodes:
            raise self._err("ST-LIM-001", f"the expression has more than {self.lim.max_ast_nodes} nodes")
        return node

    def _descend(self, d: int) -> int:
        if d > self.lim.max_ast_depth:
            raise self._err("ST-LIM-001", f"the expression nests deeper than {self.lim.max_ast_depth}")
        return d + 1

    def is_connective(self, tok: Optional[Token]) -> bool:
        if tok is None:
            return False
        if tok.kind == "REL" and (tok.text in _CONNECTIVE_RELS or (tok.text == "⇔" and not self.ctx.profile.computer_science)):
            return True
        if tok.kind in ("COMMA", "SEMI", "ROWSEP"):
            return True
        if tok.kind == "TEXT" and _connective_word(tok.text):
            return True
        if tok.kind == "IDENT" and tok.space and tok.text in _IDENT_CONNECTIVES and not (tok.sub or tok.primes or tok.delta) \
                and tok.text not in self.ctx.names:
            return True  # 'x = 2 or x = 3' inside one span: a word between two relations, never a product o·r
        return False

    def _close_index(self, j: int) -> Optional[int]:
        """Index of the token closing the bracket or group opened at ``j`` (bounded scan)."""
        opener = self.t[j]
        pairs = {"(": ")", "[": "]", "{": "}"}
        want_kind = "RGROUP" if opener.kind == "LGROUP" else "RPAR"
        depth_ = 0
        k = j
        while k < len(self.t) and k - j <= _MAX_SCAN:
            tk = self.t[k]
            if tk.kind in ("LPAR", "LGROUP"):
                depth_ += 1
            elif tk.kind in ("RPAR", "RGROUP"):
                depth_ -= 1
                if depth_ == 0:
                    if tk.kind == want_kind and (opener.kind == "LGROUP" or tk.text == pairs.get(opener.text, tk.text)):
                        return k
                    return None
            k += 1
        return None

    def _skip_operand(self) -> int:
        """Advance to the end of the current operand (a relation or connective at depth 0); returns the end offset."""
        depth_ = 0
        last_end = self.t[self.i - 1].end if self.i > 0 else 0
        while self.i < len(self.t):
            tk = self.t[self.i]
            if depth_ == 0 and ((tk.kind == "REL") or self.is_connective(tk) or tk.kind in ("AMP", "PUNCT")):
                break
            if tk.kind in ("LPAR", "LGROUP"):
                depth_ += 1
            elif tk.kind in ("RPAR", "RGROUP"):
                if depth_ == 0:
                    break
                depth_ -= 1
            last_end = tk.end
            self.i += 1
        return last_end

    # ------------------------------------------------------------------ sequence and chains
    def run(self) -> list[Chain]:
        chains: list[Chain] = []
        connective = ""
        guard = 0
        while self.i < len(self.t):
            guard += 1
            if guard > len(self.t) * 4 + 8:
                break
            tok = self.t[self.i]
            if self.is_connective(tok):
                word = tok.text if tok.kind != "TEXT" else _connective_word(tok.text)
                connective = (connective + " " + word).strip() if connective else word
                self.i += 1
                continue
            if tok.kind in ("AMP",):
                self.i += 1
                continue
            if tok.kind == "PUNCT":
                connective = "."
                self.i += 1
                continue
            before = self.i
            chain = self.chain(len(chains), connective)
            connective = ""
            if self.i == before:  # nothing consumed: skip the token, naming it
                self.issues.append(ParseIssue("ST-PARSE-001", f"unexpected {tok.text!r}", tok.start, tok.end))
                self.i += 1
                continue
            chains.append(chain)
        return chains

    def chain(self, ci: int, connective: str) -> Chain:
        operands: list[Operand] = []
        ops: list[str] = []
        first = self.peek()
        lead = ""
        truncated = False
        if first is not None and first.kind == "REL" and not self.is_connective(first):
            lead = "label" if self.ctx.lead_label else "continuation"
            name = self.ctx.lead_label or ""
            operands.append(Operand((Sym(name, kind=lead, start=first.start, end=first.start),), first.start, first.start))
        else:
            operands.append(self.operand(ci, 0))
        while True:
            while self.peek() is not None and self.peek().kind == "AMP":
                self.i += 1  # an alignment mark of a display row ('y(x + 1) &= 3x - 2') is dropped
            tok = self.peek()
            if tok is None or tok.kind != "REL" or self.is_connective(tok):
                break
            if len(ops) >= self.lim.max_chain_links:
                start = tok.start
                self.i += 1
                end = self._skip_rest_of_chain()
                self.issues.append(ParseIssue("ST-LIM-001", f"a chain of more than {self.lim.max_chain_links} links: the links after the "
                                              f"{self.lim.max_chain_links}th were not read", start, end))
                truncated = True
                break
            ops.append(tok.text)
            self.i += 1
            operands.append(self.operand(ci, len(operands)))
        start = operands[0].start if operands else (first.start if first else 0)
        end = max((o.end for o in operands), default=start)
        return Chain(operands=tuple(operands), ops=tuple(ops), start=start, end=end, lead=lead, connective=connective, truncated=truncated)

    def _skip_rest_of_chain(self) -> int:
        end = self.t[self.i - 1].end if self.i else 0
        while self.i < len(self.t) and not self.is_connective(self.t[self.i]):
            end = self.t[self.i].end
            self.i += 1
        return end

    def operand(self, ci: int, oi: int) -> Operand:
        self.where = (ci, oi)
        self.nodes = 0
        start_i = self.i
        first = self.peek()
        start = first.start if first else (self.t[-1].end if self.t else 0)
        try:
            if first is None or first.kind == "REL" or self.is_connective(first):
                raise self._err("ST-PARSE-001", "a relation sign with no operand")
            self._tally_label(oi)
            node = self.expr(0)
            tok = self.peek()
            if tok is not None and not (tok.kind == "REL" or self.is_connective(tok) or tok.kind in ("AMP", "PUNCT")):
                raise self._err("ST-PARSE-001", f"unexpected {tok.text!r} after an operand", tok)
            if depth(node) > self.lim.max_ast_depth:
                raise self._err("ST-LIM-001", f"the expression nests deeper than {self.lim.max_ast_depth}")
            end = self.t[self.i - 1].end if self.i > start_i else start
            return Operand((node,), start, end)
        except _OperandError as exc:
            self.issues.append(ParseIssue(exc.code, exc.message, exc.start, exc.end))
            self.i = start_i
            end = self._skip_operand()
            if self.i == start_i and self.i < len(self.t) and not (self.t[self.i].kind == "REL" or self.is_connective(self.t[self.i])):
                self.i += 1
                end = self.t[self.i - 1].end
            return Operand((), start, max(end, start), error=exc.message, code=exc.code)

    def _tally_label(self, oi: int) -> None:
        """An atom tally in a chemistry profile: ``C 3 = 3``, ``H 8 = 4 × 2 = 8``: the element label is not a factor."""
        if oi != 0 or not self.ctx.profile.chemistry:
            return
        a, b = self.peek(), self.peek(1)
        if a is not None and b is not None and a.kind == "IDENT" and a.text in ELEMENTS and not a.sub and not a.primes and not a.delta \
                and b.kind == "NUM" and b.space:
            self.i += 1

    # ------------------------------------------------------------------ expressions
    def expr(self, d: int) -> Node:
        d = self._descend(d)
        left = self.term(d)
        while True:
            tok = self.peek()
            if tok is None or tok.kind != "OP" or tok.text not in _ADD_OPS:
                return left
            self.i += 1
            right = self.term(d)
            if tok.text in ("±", "∓"):
                left = self._count(PlusMinus(tok.text, left, right, _start(left), _end(right)))
            else:
                left = self._count(BinOp(tok.text, left, right, _start(left), _end(right), written=tok.text))

    def term(self, d: int) -> Node:
        left = self.unary(d)
        while True:
            tok = self.peek()
            if tok is None:
                return left
            if tok.kind == "OP" and tok.text in _MUL_OPS:
                if tok.text == "×" and _is_value_node(left) and self._ends_operand(self.i + 1):
                    self.i += 1
                    left = self._count(Magnification(left, _start(left), tok.end))
                    continue
                self.i += 1
                right = self.unary(d)
                op = "/" if tok.text in ("/", "÷") else "*"
                left = self._count(BinOp(op, left, right, _start(left), _end(right), written=tok.text))
                continue
            if self._juxtaposable(tok, left):
                if tok.kind == "IDENT" and tok.text == "i" and not tok.sub and not tok.space and _ends_in_number(left):
                    self.i += 1
                    left = self._count(Unsupported("a complex number", "i", _start(left), tok.end))
                    continue
                right = self.power(d)
                left = self._count(BinOp("*", left, right, _start(left), _end(right), written="", implicit=True))
                continue
            return left

    def _juxtaposable(self, tok: Token, left: Node) -> bool:
        if self.is_connective(tok):
            return False
        if tok.kind in ("FUNC", "LATEX", "LGROUP", "UNSUP", "INF"):
            return True
        if tok.kind == "LPAR":
            return tok.text in "(["
        if tok.kind == "IDENT":
            if not tok.space:
                return True
            if tok.delta or tok.sub or len(tok.text) == 1 or tok.text in self.ctx.names or tok.text in STEM_NAMES:
                return True
            return len(tok.text) <= 3 and tok.text.isalpha() and self.ctx.mode == "latex"
        if tok.kind == "TEXT" and not _connective_word(tok.text) and self.ctx.mode == "latex":
            return False
        return False

    def unary(self, d: int) -> Node:
        tok = self.peek()
        if tok is not None and tok.kind == "OP" and tok.text in ("-", "+", "±", "∓"):
            d = self._descend(d)
            self.i += 1
            arg = self.unary(d)
            if tok.text == "-":
                return self._count(Neg(arg, tok.start, _end(arg)))
            if tok.text == "+":
                return arg
            return self._count(PlusMinus(tok.text, None, arg, tok.start, _end(arg)))
        if tok is not None and tok.kind == "BOOL" and tok.text == "¬":
            d = self._descend(d)
            self.i += 1
            arg = self.unary(d)
            return self._count(BoolOp("not", (arg,), tok.start, _end(arg)))
        return self.power(d)

    def power(self, d: int) -> Node:
        return self.power_of(self.postfix(d), d)

    def power_of(self, base: Node, d: int) -> Node:
        tok = self.peek()
        if tok is None:
            return base
        if tok.kind == "SUP" and not tok.space:
            if tok.value is None:
                raise self._err("ST-PARSE-001", f"a superscript sign {tok.text!r} with no digits (a charge outside a formula)", tok)
            self.i += 1
            node = self._make_pow(base, tok.value, tok.end)
            return self._nested_power_check(node)
        if tok.kind in ("CARET", "DSTAR"):
            self.i += 1
            exp = self._exponent(d)
            if isinstance(exp, Unsupported):
                return self._count(Unsupported(exp.reason, exp.text, _start(base), exp.end))
            value, end = exp
            node = self._make_pow(base, value, end)
            return self._nested_power_check(node)
        return base

    def _nested_power_check(self, node: Node) -> Node:
        tok = self.peek()
        if tok is not None and (tok.kind in ("CARET", "DSTAR") or (tok.kind == "SUP" and not tok.space)):
            end = self._skip_operand()
            return self._count(Unsupported("a nested power (a power of a power without brackets)", "", _start(node), end))
        return node

    def _make_pow(self, base: Node, value: "int | str", end: int) -> Node:
        if value == "half":
            return self._count(Root(base, 2, _start(base), end))
        if not isinstance(value, int):
            return self._count(Unsupported("a symbolic power", "", _start(base), end))
        if abs(value) > self.lim.max_int_power:
            return self._count(Unsupported(f"an integer power beyond {self.lim.max_int_power} ({value})", "", _start(base), end))
        return self._count(Pow(base, value, _start(base), end))

    def _exponent(self, d: int) -> "Unsupported | tuple[int | str, int]":
        tok = self.peek()
        if tok is None:
            raise self._err("ST-PARSE-001", "a power sign with no exponent")
        if tok.kind in ("LPAR", "LGROUP"):
            close = self._close_index(self.i)
            if close is None:
                raise self._err("ST-PARSE-001", "an unbalanced bracket in an exponent", tok)
            inner = self.t[self.i + 1:close]
            end = self.t[close].end
            self.i = close + 1
            return _read_exponent(inner, end)
        if tok.kind == "OP" and tok.text in "-+" and self.peek(1) is not None and self.peek(1).kind == "NUM":
            num = self.peek(1)
            self.i += 2
            return _read_exponent((tok, num), num.end)
        if tok.kind == "NUM":
            self.i += 1
            return _read_exponent((tok,), tok.end)
        if tok.kind == "NUMERR":
            code, message = tok.value
            raise self._err(code, message, tok)
        if tok.kind in ("IDENT", "FUNC", "LATEX"):
            self.i += 1
            if tok.kind == "LATEX" and tok.text == "\\frac":
                # \frac{1}{2} as an exponent: a half is a square root, anything else is a fractional power
                start_i = self.i
                ends = []
                for _ in range(2):
                    if self.peek() is None or self.peek().kind != "LGROUP":
                        break
                    c = self._close_index(self.i)
                    if c is None:
                        break
                    ends.append((self.i, c))
                    self.i = c + 1
                if len(ends) == 2:
                    num_t = self.t[ends[0][0] + 1:ends[0][1]]
                    den_t = self.t[ends[1][0] + 1:ends[1][1]]
                    if _is_digit_tokens(num_t, "1") and _is_digit_tokens(den_t, "2"):
                        return ("half", self.t[ends[1][1]].end)
                    return Unsupported("a fractional power", "", tok.start, self.t[ends[1][1]].end)
                self.i = start_i
            return Unsupported("a symbolic power", tok.text, tok.start, tok.end)
        raise self._err("ST-PARSE-001", f"an unreadable exponent {tok.text!r}", tok)

    def postfix(self, d: int) -> Node:
        node = self.primary(d)
        while True:
            tok = self.peek()
            if tok is None:
                return node
            if tok.kind == "PERCENT":
                self.i += 1
                node = self._count(Percent(node, _start(node), tok.end))
                continue
            if tok.kind == "DEGREE" and tok.text == "°":
                self.i += 1
                node = self._count(Degrees(node, _start(node), tok.end))
                continue
            if tok.kind == "BANG" and not tok.space:
                self.i += 1
                node = self._count(Unsupported("a factorial (!)", "!", _start(node), tok.end))
                continue
            return node

    # ------------------------------------------------------------------ primaries
    def primary(self, d: int) -> Node:
        tok = self.peek()
        if tok is None:
            raise self._err("ST-PARSE-001", "an expression ends where an operand was expected")
        k = tok.kind
        if k == "NUM":
            return self._number(tok)
        if k == "NUMERR":
            code, message = tok.value
            raise self._err(code, message, tok)
        if k == "IDENT":
            return self._ident(tok, d)
        if k == "FUNC":
            return self._function(tok, d)
        if k == "LPAR":
            return self._paren(tok, d)
        if k == "LGROUP":
            d = self._descend(d)
            close = self._close_index(self.i)
            if close is None:
                raise self._err("ST-PARSE-001", "an unbalanced group {", tok)
            self.i += 1
            node = self.expr(d)
            if self.i != close:
                raise self._err("ST-PARSE-001", "an unexpected token inside a group", self.peek())
            self.i = close + 1
            return node
        if k == "LATEX":
            return self._latex(tok, d)
        if k == "BAR":
            d = self._descend(d)
            self.i += 1
            node = self.expr(d)
            close = self.peek()
            if close is None or close.kind != "BAR":
                raise self._err("ST-PARSE-001", "an absolute value bar without its closing bar", tok)
            self.i += 1
            return self._count(Abs(node, tok.start, close.end))
        if k == "UNSUP":
            self.i += 1
            end = self._skip_operand()
            return self._count(Unsupported(str(tok.value), tok.text, tok.start, max(end, tok.end)))
        if k == "INF":
            self.i += 1
            return self._count(Unsupported("infinity", "∞", tok.start, tok.end))
        if k == "TEXT":
            self.i += 1
            text = " ".join(tok.text.replace("\\,", " ").replace("\\ ", " ").split())
            chem = _chem_label_text(tok.text)
            if chem is not None:
                return self._count(Sym(chem, kind="chem", start=tok.start, end=tok.end))
            if not text:
                raise self._err("ST-PARSE-001", "an empty \\text{}", tok)
            return self._count(Sym(text, kind="label", start=tok.start, end=tok.end))
        if k == "BOOL":
            raise self._err("ST-PARSE-001", f"a Boolean operator {tok.text!r} outside a Boolean expression", tok)
        raise self._err("ST-PARSE-001", f"unexpected {tok.text!r}", tok)

    def _number(self, tok: Token) -> Node:
        self.i += 1
        num: ExactNumber = tok.value
        nxt = self.peek()
        # ratio a : b
        if nxt is not None and nxt.kind == "COLON" and self.peek(1) is not None and self.peek(1).kind == "NUM":
            other = self.peek(1)
            self.i += 2
            return self._count(Ratio(self._count(Num(num, tok.start, tok.end)), self._count(Num(other.value, other.start, other.end)), tok.start, other.end))
        unit = self._unit_after(self.i, glued_ok=True)
        if unit is not None:
            expr, j = unit
            end = self.t[j - 1].end
            self.i = j
            return self._count(Quantity(num, expr, tok.start, end))
        return self._count(Num(num, tok.start, tok.end))

    def _unit_after(self, j: int, *, glued_ok: bool) -> Optional[tuple[UnitExpr, int]]:
        """A unit expression starting at token ``j`` that ends the operand: ``(UnitExpr, index after it)``."""
        toks = self.t
        n = len(toks)
        if j >= n:
            return None
        first = toks[j]
        prof = self.ctx.profile
        if first.kind == "DEGREE" and first.text in ("°C", "°F"):
            k = j + 1
        elif first.kind == "TEXT":
            k = j + 1
        elif first.kind == "PRIME" and not first.space and first.value in (1, 2):
            k = j + 1
        elif first.kind == "IDENT" and first.text == "μ" and not first.sub and j + 1 < n and toks[j + 1].kind == "IDENT" and not toks[j + 1].space \
                and is_unit_atom("μ" + toks[j + 1].text, bare_m=prof.bare_m, tonne=prof.tonne, glued=False) and (first.space or self._glued_unit_ok("μm", glued_ok)):
            k = j + 2
        elif first.kind == "IDENT" and not first.sub and not first.primes and not first.delta:
            word = first.text
            if not first.space:
                if not self._glued_unit_ok(word, glued_ok):
                    return None
            if not (is_unit_atom(word, bare_m=prof.bare_m, tonne=prof.tonne, glued=False) or word in ("Ω", "μ", "µ")):
                if not (is_unit_atom(word, bare_m=prof.bare_m, tonne=prof.tonne) and len(word) > 1):
                    return None
            k = j + 1
        else:
            return None
        # extend over further atoms, exponents and separators
        while k < n:
            tk = toks[k]
            if tk.kind == "SUP" and not tk.space and tk.value is not None:
                k += 1
                continue
            if tk.kind in ("CARET", "DSTAR") and not tk.space:
                e = self._unit_exponent_end(k + 1)
                if e is None:
                    break
                k = e
                continue
            if tk.kind == "TEXT" and not _connective_word(tk.text):
                k += 1
                continue
            if tk.kind == "IDENT" and tk.space and not tk.sub and not tk.primes and not tk.delta:
                if is_unit_atom(tk.text, bare_m=prof.bare_m, tonne=prof.tonne):
                    k += 1
                    continue
                # an unknown atom after a known one, carrying an exponent: 'yr⁻¹'
                after = toks[k + 1] if k + 1 < n else None
                if len(tk.text) >= 2 and after is not None and not after.space and (after.kind == "SUP" and after.value is not None or after.kind in ("CARET", "DSTAR")):
                    k += 1
                    continue
                break
            if tk.kind == "OP" and tk.text in ("/", "·", "*") and k + 1 < n:
                nx = toks[k + 1]
                if nx.kind == "IDENT" and not nx.sub and not nx.delta and is_unit_atom(nx.text, bare_m=prof.bare_m, tonne=prof.tonne) and not (tk.text == "*" and nx.space):
                    k += 2
                    continue
                if nx.kind == "TEXT" or (nx.kind == "DEGREE" and nx.text in ("°C", "°F")):
                    k += 2
                    continue
                if tk.text == "/" and nx.kind == "LPAR" and nx.text == "(":
                    c = self._close_index(k + 1)
                    if c is not None and all(x.kind in ("IDENT", "SUP", "OP") for x in toks[k + 2:c]) and c > k + 2:
                        k = c + 1
                        continue
                break
            if tk.kind == "DEGREE" and tk.text in ("°C", "°F") and tk.space:
                k += 1
                continue
            break
        if not self._ends_operand(k):
            return None
        text = self.ctx.s[toks[j].start:toks[k - 1].end]
        expr = parse_unit(text, bare_m=prof.bare_m, tonne=prof.tonne)
        if expr is None:
            return None
        if expr.readings and expr.readings[0].atoms and expr.readings[0].atoms[0].unit is None:
            return None
        return expr, k

    def _unit_exponent_end(self, k: int) -> Optional[int]:
        toks = self.t
        n = len(toks)
        if k >= n:
            return None
        tk = toks[k]
        if tk.kind in ("LGROUP", "LPAR"):
            c = self._close_index(k)
            return None if c is None else c + 1
        if tk.kind == "OP" and tk.text in "-+" and k + 1 < n and toks[k + 1].kind == "NUM":
            return k + 2
        if tk.kind == "NUM":
            return k + 1
        return None

    def _glued_unit_ok(self, word: str, glued_ok: bool) -> bool:
        if not glued_ok:
            return False
        if word in ("Ω",):
            return True
        if word not in _COMMON_GLUED_UNITS:
            return False
        segs = segment(word, self.ctx.names, self.lim)
        return not any(all(p in self.ctx.names for p in seg) for seg in segs)

    def _ends_operand(self, k: int) -> bool:
        if k >= len(self.t):
            return True
        tk = self.t[k]
        if tk.kind in _END_OF_OPERAND or self.is_connective(tk):
            return True
        return False

    def _ident(self, tok: Token, d: int) -> Node:
        prof = self.ctx.profile
        word = tok.text
        nxt = self.peek(1)
        # a limit written as a word
        if word == "lim" and not tok.sub:
            self.i += 1
            end = self._skip_operand()
            return self._count(Unsupported("a limit", "lim", tok.start, max(end, tok.end)))
        # derivatives: d/dx, dy/dx (plain)
        if word in ("d", "dy", "dx", "dt", "dv", "ds") and nxt is not None and nxt.kind == "OP" and nxt.text == "/" and self.peek(2) is not None \
                and self.peek(2).kind == "IDENT" and self.peek(2).text.startswith("d") and len(self.peek(2).text) >= 2:
            self.i += 1
            end = self._skip_operand()
            return self._count(Unsupported("a derivative", word + "/d…", tok.start, max(end, tok.end)))
        # f′(x), f'(1): a derivative
        if tok.primes and word in _FUNCTION_LETTERS and nxt is not None and nxt.kind == "LPAR" and nxt.text == "(" and not nxt.space:
            close = self._close_index(self.i + 1)
            if close is None:
                raise self._err("ST-PARSE-001", "an unbalanced bracket", nxt)
            self.i = close + 1
            return self._count(Unsupported("a derivative", word + "'" * tok.primes + "(…)", tok.start, self.t[close].end))
        # chemistry labels n(H₂O), M(CaCO₃), ΔH_c(H₂), ΣΔH_f(products): a label, not a product
        if nxt is not None and nxt.kind == "LPAR" and nxt.text == "(" and not nxt.space:
            close = self._close_index(self.i + 1)
            if close is not None and close > self.i + 2:
                inner = self.ctx.s[nxt.end:self.t[close].start]
                label = _label_content(inner)
                if label is not None:
                    name = symbol_name(word, tok.sub, tok.primes, tok.delta) + "(" + label + ")"
                    self.i = close + 1
                    return self._count(Sym(name, kind="chem", start=tok.start, end=self.t[close].end))
                # f(x), g(2): a named function applied to one symbol or number
                inner_toks = self.t[self.i + 2:close]
                if word in _FUNCTION_LETTERS and not tok.sub and _single_argument(inner_toks):
                    self.i += 2
                    arg = self.expr(self._descend(d))
                    self.i = close + 1
                    return self._count(Apply(word, arg, tok.start, self.t[close].end))
                if prof.computer_science and word == "O" and not tok.sub:
                    self.i = close + 1
                    return self._count(Unsupported("asymptotic notation", "O(…)", tok.start, self.t[close].end))
        # bond notation in chemistry: O=O, C–H, N≡N
        if prof.chemistry and word in ELEMENTS and not tok.sub and not tok.primes and nxt is not None and not nxt.space \
                and ((nxt.kind == "REL" and nxt.text in ("=", "≡")) or (nxt.kind == "OP" and nxt.text == "-") or (nxt.kind == "OTHER" and nxt.text in "–—")):
            other = self.peek(2)
            if other is not None and other.kind == "IDENT" and other.text in ELEMENTS and not other.space and not other.sub:
                self.i += 3
                return self._count(Sym(f"{word}{nxt.text}{other.text}", kind="bond", start=tok.start, end=other.end))
        self.i += 1
        if word in ("π",):
            return self._count(Sym("π", kind="constant", start=tok.start, end=tok.end))
        if len(word) == 1 or tok.delta and len(word) == 1 or not word.isascii():
            return self._count(Sym(symbol_name(word, tok.sub, tok.primes, tok.delta), start=tok.start, end=tok.end))
        names = self.ctx.names | STEM_NAMES
        alternatives = segment(word, names, self.lim)
        if len(alternatives) == 1 and len(word) >= 4 and word.isascii() and word.islower() and not all(p in names for p in alternatives[0]):
            # a word written as a symbol ('actual / theoretical × 100'): one name, not a product of its letters
            return self._count(Sym(symbol_name(word, tok.sub, tok.primes, tok.delta), kind="word", start=tok.start, end=tok.end))
        if len(alternatives) > 1:
            self.amb.append((self.i - 1, len(alternatives), *self.where))
        pick = alternatives[min(self.choices.get(self.i - 1, 0), len(alternatives) - 1)]
        pieces: list[Node] = []
        pos = tok.start + (1 if tok.delta else 0)
        for idx, piece in enumerate(pick):
            last = idx == len(pick) - 1
            name = symbol_name(piece, tok.sub if last else "", tok.primes if last else 0, tok.delta and idx == 0)
            a = tok.start if idx == 0 else pos
            b = tok.end if last else pos + len(piece)
            pieces.append(self._count(Sym(name, start=a, end=b)))
            pos += len(piece)
        if len(pieces) > 1:
            # a power written after the run raises its last letter only: ½gt² is ½·g·t²
            nxt = self.peek()
            if nxt is not None and not nxt.space and (nxt.kind == "SUP" and nxt.value is not None or nxt.kind in ("CARET", "DSTAR")):
                pieces[-1] = self.power_of(pieces[-1], d)
        node = pieces[0]
        for p in pieces[1:]:
            node = self._count(BinOp("*", node, p, _start(node), _end(p), implicit=True))
        return node

    def _function(self, tok: Token, d: int) -> Node:
        self.i += 1
        d = self._descend(d)
        name = tok.text
        power_after: Optional[int] = None
        nxt = self.peek()
        if nxt is not None and nxt.kind == "SUP" and nxt.value is not None and not nxt.space and name not in ("sqrt",):
            power_after = nxt.value  # sin²θ
            self.i += 1
        if name == "sqrt":
            arg = self._function_argument(d)
            return self._count(Root(arg, 2, tok.start, _end(arg)))
        if name == "cbrt":
            arg = self._function_argument(d)
            return self._count(Unsupported("a cube root", "∛", tok.start, _end(arg)))
        arg = self._function_argument(d)
        node: Node = self._count(Func(name, arg, tok.value if name == "log" else None, tok.start, _end(arg)))
        if power_after is not None:
            node = self._make_pow(node, power_after, _end(arg))
        return node

    def _function_argument(self, d: int) -> Node:
        tok = self.peek()
        if tok is None:
            raise self._err("ST-PARSE-001", "a function with no argument")
        if tok.kind in ("LPAR", "LGROUP"):
            return self.postfix(d)
        if tok.kind == "OP" and tok.text == "-":
            self.i += 1
            arg = self.postfix(d)
            return self._count(Neg(arg, tok.start, _end(arg)))
        arg = self.power(d)
        # 'sin 2θ', 'ln 2x': glued factors belong to the argument; a spaced factor or another function does not
        while True:
            nxt = self.peek()
            if nxt is None or nxt.space or nxt.kind not in ("IDENT", "LPAR") or (nxt.kind == "LPAR" and nxt.text != "("):
                return arg
            right = self.power(d)
            arg = self._count(BinOp("*", arg, right, _start(arg), _end(right), implicit=True))

    def _paren(self, tok: Token, d: int) -> Node:
        d = self._descend(d)
        close = self._close_index(self.i)
        if close is None:
            raise self._err("ST-PARSE-001", f"an unbalanced bracket {tok.text!r}", tok)
        inner_toks = self.t[self.i + 1:close]
        if not inner_toks:
            raise self._err("ST-PARSE-001", "empty brackets", tok)
        # a concentration [H⁺] or [\mathrm{NH_3}]
        if tok.text == "[":
            inner = self.ctx.s[tok.end:self.t[close].start]
            label = _chem_label_text(inner)
            if label is not None and _looks_like_species(inner):
                self.i = close + 1
                node: Node = self._count(Sym("[" + label + "]", kind="chem", start=tok.start, end=self.t[close].end))
                return self._evaluation_bracket_check(node)
        # a tuple, coordinate pair, vector or set
        depth_ = 0
        for x in inner_toks:
            if x.kind in ("LPAR", "LGROUP"):
                depth_ += 1
            elif x.kind in ("RPAR", "RGROUP"):
                depth_ -= 1
            elif depth_ == 0 and x.kind in ("COMMA", "SEMI"):
                self.i = close + 1
                reason = "a set" if tok.text == "{" else "a coordinate pair, vector or list"
                return self._count(Unsupported(reason, "", tok.start, self.t[close].end))
            elif depth_ == 0 and x.kind == "REL" and x.text not in ("<", ">") and not self._is_bond_sign(x):
                raise self._err("ST-PARSE-001", "a relation sign inside brackets", x)
        self.i += 1
        node = self.expr(d)
        if self.i != close:
            raise self._err("ST-PARSE-001", f"unexpected {self.peek().text!r} inside brackets" if self.peek() else "unbalanced brackets", self.peek())
        self.i = close + 1
        # a base subscript: (255)₁₀, (1010)₂; the digits are read again in the stated base
        sub, after = self.peek(), self.peek(1)
        if sub is not None and sub.kind == "SUB" and not sub.space and sub.value in ("2", "8", "10", "16") and isinstance(node, Num) \
                and not (after is not None and not after.space and after.kind in ("CARET", "SUP")):
            num = node.number
            plain = num.text.isascii() and num.text.isdigit()
            based = exact_based(self.ctx.s[tok.start:sub.end], num.text, int(sub.value), limits=self.lim) if plain else None
            if based is None:
                raise self._err("ST-PARSE-001", f"{num.text!r} is no numeral in base {sub.value}", sub)
            self.i += 1
            return self._count(Num(based, tok.start, sub.end))
        node = self._evaluation_bracket_check(node)
        # a unit after a closing group that contains a number: (40 − 20) K
        if any(isinstance(x, (Num, Quantity)) for x in walk(node)):
            unit = self._unit_after(self.i, glued_ok=False)
            if unit is not None and self.peek() is not None and self.peek().space:
                expr, j = unit
                self.i = j
                return self._count(WithUnit(node, expr, tok.start, self.t[j - 1].end))
        return node

    def _is_bond_sign(self, x: Token) -> bool:
        """``=`` or ``≡`` glued between two element symbols in a chemistry profile (``O=O``)."""
        if not self.ctx.profile.chemistry or x.text not in ("=", "≡") or x.space:
            return False
        try:
            k = self.t.index(x)
        except ValueError:
            return False
        a = self.t[k - 1] if k > 0 else None
        b = self.t[k + 1] if k + 1 < len(self.t) else None
        return a is not None and b is not None and a.kind == "IDENT" and a.text in ELEMENTS and b.kind == "IDENT" and b.text in ELEMENTS and not b.space

    def _evaluation_bracket_check(self, node: Node) -> Node:
        nxt, after = self.peek(), self.peek(1)
        if nxt is not None and not nxt.space and nxt.kind == "SUB":
            limits = after is not None and not after.space and after.kind in ("CARET", "SUP")
            end = self._skip_operand()
            reason = "the evaluation of an antiderivative between limits" if limits else "a subscript on a bracketed expression"
            return self._count(Unsupported(reason, "", _start(node), end))
        return node

    def _latex(self, tok: Token, d: int) -> Node:
        d = self._descend(d)
        self.i += 1
        if tok.text == "\\frac":
            args = []
            for _ in range(2):
                g = self.peek()
                if g is None:
                    raise self._err("ST-PARSE-001", "\\frac with a missing argument", tok)
                if g.kind == "LGROUP":
                    close = self._close_index(self.i)
                    if close is None:
                        raise self._err("ST-PARSE-001", "\\frac with an unbalanced group", g)
                    inner = self.t[self.i + 1:close]
                    if not inner:
                        raise self._err("ST-PARSE-001", "\\frac with an empty argument", g)
                    args.append((self.i, close, inner))
                    self.i = close + 1
                elif g.kind in ("NUM", "IDENT") and len(g.text) == 1:
                    args.append((self.i, self.i, (g,)))
                    self.i += 1
                else:
                    raise self._err("ST-PARSE-001", "\\frac without braced arguments", g)
            # \frac{d}{dx} and \frac{dy}{dx}: a derivative
            (a0, a1, num_t), (b0, b1, den_t) = args
            if len(num_t) <= 3 and num_t[0].kind == "IDENT" and num_t[0].text in ("d", "dy", "dv", "ds", "dx") and len(den_t) == 1 and den_t[0].kind == "IDENT" \
                    and den_t[0].text.startswith("d") and len(den_t[0].text) == 2:
                end = self._skip_operand()
                return self._count(Unsupported("a derivative", "d/dx", tok.start, max(end, self.t[b1].end)))
            num = self._sub_parse(a0, a1, num_t, d)
            den = self._sub_parse(b0, b1, den_t, d)
            frac = self._count(BinOp("/", num, den, tok.start, self.t[b1].end, written="/"))
            # a unit after a fraction of numbers: \frac{5}{12}\ \Omega^{-1}
            if any(isinstance(x, (Num, Quantity)) for x in walk(frac)) and self.peek() is not None and self.peek().space:
                unit = self._unit_after(self.i, glued_ok=False)
                if unit is not None:
                    expr, j = unit
                    self.i = j
                    return self._count(WithUnit(frac, expr, tok.start, self.t[j - 1].end))
            return frac
        if tok.text == "\\sqrt":
            g = self.peek()
            index = 2
            if g is not None and g.kind == "LPAR" and g.text == "[":
                close = self._close_index(self.i)
                if close is None:
                    raise self._err("ST-PARSE-001", "\\sqrt with an unbalanced index", g)
                inner = self.t[self.i + 1:close]
                if not (len(inner) == 1 and inner[0].kind == "NUM" and inner[0].value.value.denominator == 1):
                    raise self._err("ST-PARSE-001", "\\sqrt with an unreadable index", g)
                index = int(inner[0].value.value)
                self.i = close + 1
            g = self.peek()
            if g is None:
                raise self._err("ST-PARSE-001", "\\sqrt with no argument", tok)
            if g.kind == "LGROUP":
                close = self._close_index(self.i)
                if close is None:
                    raise self._err("ST-PARSE-001", "\\sqrt with an unbalanced group", g)
                arg = self._sub_parse(self.i, close, self.t[self.i + 1:close], d)
                self.i = close + 1
                end = self.t[close].end
            else:
                arg = self.primary(d)
                end = _end(arg)
            if index != 2:
                return self._count(Unsupported(f"a root of index {index}", "\\sqrt", tok.start, end))
            return self._count(Root(arg, 2, tok.start, end))
        raise self._err("ST-PARSE-001", f"unexpected {tok.text}", tok)

    def _sub_parse(self, open_i: int, close_i: int, inner: tuple[Token, ...], d: int) -> Node:
        """Parse the tokens of a TeX group as one expression (the group's own index range)."""
        if open_i == close_i:  # a single-token argument
            saved = self.i
            self.i = open_i
            node = self.primary(d)
            self.i = saved
            return node
        saved = self.i
        self.i = open_i + 1
        node = self.expr(d)
        if self.i != close_i:
            raise self._err("ST-PARSE-001", "an unexpected token inside a group", self.peek())
        self.i = saved
        return node


def _start(node: Node) -> int:
    return getattr(node, "start", 0)


def _end(node: Node) -> int:
    return getattr(node, "end", 0)


def _ends_in_number(node: Node) -> bool:
    cur = node
    for _ in range(64):
        if isinstance(cur, (Num, Quantity)):
            return True
        if isinstance(cur, (Neg,)):
            cur = cur.arg
        elif isinstance(cur, PlusMinus):
            cur = cur.right
        elif isinstance(cur, BinOp):
            cur = cur.right
        else:
            return False
    return False


def _is_value_node(node: Node) -> bool:
    return isinstance(node, (Num, Quantity))


def _is_digit_tokens(toks: tuple[Token, ...], digit: str) -> bool:
    return len(toks) == 1 and toks[0].kind == "NUM" and toks[0].text == digit


def _single_argument(toks: tuple[Token, ...]) -> bool:
    if len(toks) == 1 and toks[0].kind in ("IDENT", "NUM"):
        return toks[0].kind == "NUM" or len(toks[0].text) == 1
    if len(toks) == 2 and toks[0].kind == "OP" and toks[0].text == "-" and toks[1].kind == "NUM":
        return True
    return False


def _read_exponent(toks: "tuple[Token, ...] | list[Token]", end: int) -> "Unsupported | tuple[int | str, int]":
    """An exponent's tokens: a signed integer, ½, 1/2 (a square root); anything else is unsupported."""
    toks = tuple(toks)
    start = toks[0].start if toks else end
    sign = 1
    body = toks
    if body and body[0].kind == "OP" and body[0].text in "-+":
        sign = -1 if body[0].text == "-" else 1
        body = body[1:]
    if len(body) == 1 and body[0].kind == "NUM":
        num: ExactNumber = body[0].value
        if num.vulgar and num.value == exact_integer(1).value / 2 and sign == 1:
            return ("half", end)
        if not num.has_point and not num.scientific and num.value.denominator == 1 and num.base == 10:
            return (sign * int(num.value), end)
        return Unsupported("a fractional or decimal power", "", start, end)
    if len(body) == 3 and body[0].kind == "NUM" and body[1].kind == "OP" and body[1].text == "/" and body[2].kind == "NUM" \
            and body[0].text == "1" and body[2].text == "2" and sign == 1:
        return ("half", end)
    if any(t.kind in ("IDENT", "FUNC") for t in body):
        return Unsupported("a symbolic power", "", start, end)
    return Unsupported("a fractional power", "", start, end)


def _connective_word(text: str) -> str:
    w = " ".join(text.replace("\\,", " ").replace("\\ ", " ").split()).lower().strip(",;:")
    return w if w in CONNECTIVE_WORDS else ""


def _looks_like_species(text: str) -> bool:
    t = text.strip()
    return bool(t) and (t[0].isupper() or t.startswith("\\mathrm") or t.startswith("\\text"))


def _chem_label_text(text: str) -> Optional[str]:
    """``text`` (plain or LaTeX) as a chemical species without a coefficient, or None."""
    plain = latex_to_chem(text).strip() if "\\" in text else text.strip()
    if not plain or len(plain) > 60 or " " in plain:
        return None
    try:
        parse_species(plain, allow_coefficient=False)
    except ValueError:
        return None
    return canonical_formula(plain)


def _label_content(inner: str) -> Optional[str]:
    """The content of a label's brackets: a chemical species (``H₂O``, ``\\mathrm{NaOH}``) or one
    prose word of three or more letters (``products``)."""
    chem = _chem_label_text(inner)
    if chem is not None and _looks_like_species(inner):
        return chem
    w = inner.strip()
    if 3 <= len(w) <= 24 and w.isalpha() and w.isascii() and w.islower():
        return w
    return None


def parse_math(tokens: "tuple[Token, ...] | list[Token]", ctx: ParseContext) -> ParsedMath:
    """Parse the tokens of one math span into chains, with one or two readings per operand.
    Never raises: every failure is a :class:`ParseIssue` (ST-PARSE-001, ST-PARSE-002,
    ST-LIM-001) and an operand that could not be read carries the error."""
    toks = tuple(tokens)
    lim = ctx.limits
    if not toks:
        return ParsedMath(chains=(), issues=(), unparsed=False)
    a, b = toks[0].start, toks[-1].end
    if len(toks) > lim.max_tokens_per_span:
        return ParsedMath((), (ParseIssue("ST-LIM-001", f"the span has more than {lim.max_tokens_per_span} tokens", a, b),), unparsed=True)
    unread = next((t for t in toks if t.kind == "NUM" and t.value is None), None)
    if unread is not None:  # tokens lexed for extents only (values=False) are never parsed
        return ParsedMath((), (ParseIssue("ST-PARSE-001", f"a numeral without a value: {unread.text!r}", unread.start, unread.end),), unparsed=True)
    errors = [t for t in toks if t.kind == "ERROR"]
    if errors:
        first = errors[0]
        more = f" (and {len(errors) - 1} more)" if len(errors) > 1 else ""
        return ParsedMath((), (ParseIssue("ST-PARSE-001", f"notation outside the grammar: {first.value}{more}", first.start, first.end),), unparsed=True)
    try:
        base = _Parser(toks, ctx, {})
        chains = base.run()
    except RecursionError:  # defensive: the depth bound makes this unreachable
        return ParsedMath((), (ParseIssue("ST-LIM-001", "the expression nests too deeply", a, b),), unparsed=True)
    issues = list(base.issues)
    readings: dict[tuple[int, int], list[Node]] = {}
    for ci, ch in enumerate(chains):
        for oi, op in enumerate(ch.operands):
            if op.readings:
                readings[(ci, oi)] = list(op.readings)
    too_many: dict[tuple[int, int], str] = {}
    seen_points: dict[tuple[int, int], int] = {}
    for idx, (tok_i, count, ci, oi) in enumerate(base.amb):
        key = (ci, oi)
        seen_points[key] = seen_points.get(key, 0) + 1
        if count > 2 or seen_points[key] > 1 or idx >= _MAX_AMBIGUITY_REPARSES:
            too_many[key] = f"the letter run {toks[tok_i].text!r} has more readings than the bound allows" if count > 2 else \
                "the operand has more than one ambiguous letter run (more than two readings)"
            continue
        alt = _Parser(toks, ctx, {tok_i: 1})
        alt_chains = alt.run()
        if len(alt_chains) != len(chains) or any(x.ops != y.ops for x, y in zip(alt_chains, chains)):
            too_many[key] = f"the two readings of {toks[tok_i].text!r} give different relations"
            continue
        alt_node = alt_chains[ci].operands[oi].node if oi < len(alt_chains[ci].operands) else None
        if alt_node is None:
            continue
        keys = {shape_key(x) for x in readings.get(key, [])}
        if shape_key(alt_node) not in keys:
            readings.setdefault(key, []).append(alt_node)
    # unit readings count toward the per-expression bound
    out_chains: list[Chain] = []
    for ci, ch in enumerate(chains):
        ops: list[Operand] = []
        for oi, op in enumerate(ch.operands):
            key = (ci, oi)
            rs = readings.get(key, [])
            if key in too_many:
                issues.append(ParseIssue("ST-PARSE-002", too_many[key], op.start, op.end))
                ops.append(Operand((), op.start, op.end, error=too_many[key], code="ST-PARSE-002"))
                continue
            if rs:
                unit_readings = max(_unit_reading_count(r) for r in rs)
                if len(rs) * unit_readings > lim.max_readings_per_expression:
                    msg = f"the operand has {len(rs) * unit_readings} readings (implicit multiplication and ambiguous units); the bound is {lim.max_readings_per_expression}"
                    issues.append(ParseIssue("ST-PARSE-002", msg, op.start, op.end))
                    ops.append(Operand((), op.start, op.end, error=msg, code="ST-PARSE-002"))
                    continue
                ops.append(Operand(tuple(rs), op.start, op.end))
            else:
                ops.append(op)
        out_chains.append(Chain(operands=tuple(ops), ops=ch.ops, start=ch.start, end=ch.end, lead=ch.lead, connective=ch.connective, truncated=ch.truncated))
    return ParsedMath(chains=tuple(out_chains), issues=tuple(issues), unparsed=False)


def _unit_reading_count(node: Node) -> int:
    count = 1
    for n in walk(node):
        if isinstance(n, (Quantity, WithUnit)):
            count *= max(1, len(n.unit.readings))
    return count
