"""Bounded Pratt (precedence-climbing) parser over the closed grammar of section 4.5.

::

    sequence  := chain ( connective chain )*        connective: ⇒ ∴ , ; or and so hence gives ... (\\text{or})
    chain     := expr ( relop expr ){1,12}           (a chain may open with a relop: a continuation or a prose label)
    expr      := term ( ( + | - | ± | ∓ ) term )*
    term      := unary ( ( × | · | * | / | ÷ | juxtaposition ) unary )*
    unary     := ( - | + | ± | ¬ ) unary | power
    power     := postfix [ ( ^ | ** | superscript ) exponent ]       right-associative
    exponent  := signed integer literal (|n| ≤ 12) | ½ | 1/2          (½ is a square root)
               | a closed exponent that is no integer, over a closed base (``10^(−8.2)``, ``2^{1/3}``: a RealPower)
               | an integer beyond 12 and up to 1000, over a closed base (``1.003^{144}``: a RealPower)
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
operand: the next token is an operator, a relation, a close, a separator or the end. A Latin
prefix written right before a Greek unit symbol (``kΩ``, ``MΩ``, ``mΩ``) is one prefixed unit,
like ``μF`` the other way round. ``m = 2.0 kg``: ``m`` is a symbol, ``kg`` a unit. A glued unit (``1.5kg``) is read only for a
common multi-letter unit that does not also split into names in scope, so ``2as`` stays
``2·a·s``. After a known unit atom, an unknown atom with an exponent (``yr⁻¹``) is kept as
an unknown unit (ST-UNIT-001).

A power whose exponent is no integer is one value (``RealPower``) when both its base and its exponent are closed and carry
no unit (``10^(−8.2)``, ``10^(8.2 − 7.8)``, ``(3465/250)^(1/6)``): written figures, signs, brackets and ``\\frac`` in the
exponent, no symbol, unit, angle or per cent in either; the encoder writes its exact value when that is rational
(``16^(3/4)`` is 8) and decides any other through an enclosure. An integer power beyond 12 (up to 1000) of such a base
is one value too (``(1 + 0.065/12)^{-60}``).

Unsupported constructs are nodes, not failures: a symbolic power or a non-integer power of anything else, ``!``,
``Σ``, ``∫``, ``lim``, ``d/dx`` and ``dy/dx``, ``f′(x)``, vectors, matrices, a tuple
``(x, y)``, ``i`` beside a number (complex), ``O(…)`` in Computer Science, an evaluation
bracket ``[F(x)]₀²``, infinity, an integer power beyond 12 of anything but a closed value, a cube root. The relation that
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

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from .chem import ELEMENTS, canonical_formula, latex_to_chem, parse_species
from .lexer import COMPLETE_UNSUP, Token
from .limits import DEFAULT_LIMITS, PROFILES, StemLimits, StemProfile
from .nodes import (
    Abs, Apply, BinOp, BoolOp, Chain, Degrees, Func, IntOp, Magnification, Neg, Node, Num, Operand, Percent, PlusMinus, Pow, Quantity, Ratio,
    RealPower, Root, Sym, Unsupported, WithUnit, depth, replace_symbol, shape_key, walk,
)
from .numbers import ExactNumber, exact_based, exact_integer
from .units import UnitExpr, compound_part, english_word_atom, is_unit_atom, lookup_atom, parse_unit, prefixed_greek_unit, unit_group

__all__ = ["CONNECTIVE_WORDS", "ParseContext", "ParseIssue", "ParsedMath", "STEM_NAMES", "parse_math", "segment", "symbol_name"]

#: multi-letter names every STEM reading knows (section 4.6)
STEM_NAMES = frozenset({"KE", "PE", "GPE", "EPE", "EMF", "emf", "pH", "pOH", "pKa", "pKb", "Ka", "Kb", "Kw", "Kc", "Kp", "Mr", "Ar", "NA", "Ek", "Ep",
                        "RMM", "RFM", "NPP", "GPP", "SV", "HR", "BMI", "RQ"})
#: words that join two relations inside one math span (``\\text{or}``) or in a chain of statements
CONNECTIVE_WORDS = frozenset({"or", "and", "so", "hence", "therefore", "thus", "gives", "giving", "where", "with", "for", "if", "since", "because",
                              "then", "i.e.", "ie", "e.g.", "which", "as", "when", "implies", "or equivalently"})
_CONNECTIVE_RELS = frozenset({"⇒", "∴"})
#: connective words read as a bare letter run (no ``\\text``) when spaced off: never ``as``, ``if`` or ``for`` (a unit, a condition, a label)
_IDENT_CONNECTIVES = frozenset({"or", "and", "so", "hence", "therefore", "thus", "gives", "giving", "then", "implies"})
_ADD_OPS = frozenset({"+", "-", "±", "∓"})
_MUL_OPS = frozenset({"×", "·", "*", "/", "÷"})
#: the integer remainder and quotient (the lexer reads them between two operands only)
_INT_OPS = frozenset({"mod", "div"})
#: the words of a stated quotient's remainder (``17 ÷ 5 = 3 remainder 2``)
_REMAINDER_WORDS = frozenset({"remainder", "rem"})
_END_OF_OPERAND = frozenset({"REL", "OP", "RPAR", "RGROUP", "COMMA", "SEMI", "PUNCT", "AMP", "ROWSEP", "COLON", "BANG", "BOOL", "BAR", "QUOTE"})
_COMMON_GLUED_UNITS = frozenset({"kg", "km", "cm", "mm", "mol", "kJ", "kN", "kPa", "MPa", "MJ", "MW", "kW", "Hz", "kHz", "MHz", "eV", "keV", "MeV",
                                 "GeV", "mA", "mV", "kV", "µm", "μm", "nm", "Pa", "ms", "µs", "ns", "dm", "mL", "cm³", "min"})
_FUNCTION_LETTERS = frozenset({"f", "g", "h"})
#: the reasons ``_read_exponent`` gives for an exponent that is no integer and names no symbol: over a closed base the power
#: is one value (``RealPower``)
_NON_INTEGER_EXPONENTS = frozenset({"a fractional or decimal power", "a fractional power"})
#: the tokens a closed non-integer exponent may hold: figures, signs and operators, brackets and groups, ``\\frac``
_CLOSED_EXPONENT_TOKENS = frozenset({"NUM", "OP", "LPAR", "RPAR", "LGROUP", "RGROUP", "LATEX"})
#: the tokens an exponent in symbols over a closed base may hold for the power to keep its parts (``1.05^(t+1)``)
_SYMBOLIC_EXPONENT_TOKENS = _CLOSED_EXPONENT_TOKENS | {"IDENT"}
_MAX_AMBIGUITY_REPARSES = 16
#: the largest integer exponent beyond ``max_int_power`` read as one value over a closed base (``1.003^{144}``, a mortgage's
#: ``(1 + r)^{-360}``); a larger one (``10^10^10``) stays unsupported, with the integer-power reason
_MAX_CLOSED_INT_POWER = 1000
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



def _signed_limit(n: int, start: int, end: int) -> Node:
    """STEM repair 10 (rule definite-integral): a whole-number limit as a node, a negative one as the negation of its digits."""
    return Num(exact_integer(n), start, end) if n >= 0 else Neg(Num(exact_integer(-n), start, end), start, end)

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
        self.pending: list[Chain] = []

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
        while self.i < len(self.t) or self.pending:
            if self.pending:
                chains.append(self.pending.pop(0))  # the remainder relation of '17 ÷ 5 = 3 remainder 2' (STEM repair 2)
                continue
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
        rem = self._remainder()
        if rem is not None:
            return self._quotient_and_remainder(operands, ops, rem, lead, connective)
        if "≡" in ops:
            cong = self._congruence(operands, ops, lead, connective)
            if cong is not None:
                return cong
        start = operands[0].start if operands else (first.start if first else 0)
        end = max((o.end for o in operands), default=start)
        return Chain(operands=tuple(operands), ops=tuple(ops), start=start, end=end, lead=lead, connective=connective, truncated=truncated)

    def _congruence(self, operands: list[Operand], ops: list[str], lead: str, connective: str) -> Optional[Chain]:
        """``a ≡ b (mod n)`` or ``a ≡ b mod n`` (STEM repair 2): a congruence, read as ``a mod n = b mod n`` (the remainders of
        whole numbers; the encodings name anything else undecided). Never the equality ``a = b``. None when no modulus follows."""
        a0, a1, a2, a3 = self.peek(), self.peek(1), self.peek(2), self.peek(3)
        modulus = None
        if a0 is not None and a1 is not None and a2 is not None and a3 is not None and a0.kind == "LPAR" and a0.text == "(" and a1.kind == "IDENT" \
                and a1.text.lower() in ("mod", "modulo") and a2.kind == "NUM" and a2.value is not None and a3.kind == "RPAR" and a3.text == ")":
            self.i += 4
            modulus = self._count(Num(a2.value, a2.start, a2.end))
            right = operands[-1].node
        elif operands and isinstance(operands[-1].node, IntOp) and operands[-1].node.op == "mod" and ops[-1] == "≡":
            modulus = operands[-1].node.right
            right = operands[-1].node.left
        if modulus is None:
            return None
        start = operands[0].start
        if len(ops) != 1 or lead or operands[0].node is None or right is None:
            bad = Operand((), operands[-1].start, self.t[self.i - 1].end, error="a congruence of more than two sides", code="ST-PARSE-001")
            self.issues.append(ParseIssue("ST-PARSE-001", bad.error, bad.start, bad.end))
            return Chain(operands=tuple(operands[:-1]) + (bad,), ops=tuple(ops), start=start, end=bad.end, lead=lead, connective=connective)
        left = operands[0].node
        lmod = self._count(IntOp("mod", left, modulus, _start(left), _end(left), written="mod"))
        rmod = self._count(IntOp("mod", right, modulus, _start(right), _end(right), written="mod"))
        end = self.t[self.i - 1].end
        return Chain(operands=(Operand((lmod,), operands[0].start, operands[0].end), Operand((rmod,), operands[-1].start, end)), ops=("=",), start=start,
                     end=end, lead=lead, connective=connective)

    def _modulus_ahead(self) -> bool:
        """``(mod 5)`` next: the modulus of a congruence, never a factor."""
        a0, a1, a2, a3 = self.peek(), self.peek(1), self.peek(2), self.peek(3)
        return (a0 is not None and a1 is not None and a2 is not None and a3 is not None and a0.kind == "LPAR" and a0.text == "(" and a1.kind == "IDENT"
                and a1.text.lower() in ("mod", "modulo") and a2.kind == "NUM" and a3.kind == "RPAR" and a3.text == ")")

    def _at_remainder(self) -> bool:
        a, b = self.peek(), self.peek(1)
        return (a is not None and b is not None and a.kind == "IDENT" and a.space and a.text in _REMAINDER_WORDS and not (a.sub or a.primes or a.delta)
                and b.kind == "NUM" and b.space and b.value is not None)

    def _remainder(self) -> Optional[tuple[Token, Token]]:
        """``remainder 2`` or ``rem 2`` right after a chain's last operand (``17 ÷ 5 = 3 remainder 2``): the word and the numeral."""
        a, b = self.peek(), self.peek(1)
        if a is not None and b is not None and a.kind == "IDENT" and a.space and a.text in _REMAINDER_WORDS and not (a.sub or a.primes or a.delta) \
                and b.kind == "NUM" and b.space and b.value is not None:
            self.i += 2
            return a, b
        return None

    def _quotient_and_remainder(self, operands: list[Operand], ops: list[str], rem: tuple[Token, Token], lead: str, connective: str) -> Chain:
        """``a ÷ b = q remainder r`` (STEM repair 2): the stated quotient and remainder of a division of whole numbers, read as the
        two relations ``a div b = q`` and ``a mod b = r`` (a second chain of the span). Any other shape states a remainder of
        nothing the grammar reads: the last operand is unreadable (ST-PARSE-001), never checked as a plain quotient."""
        word, num = rem
        quotient = operands[-1].node if operands else None
        division = operands[-2].node if len(operands) >= 2 else None
        start = operands[0].start if operands else word.start
        ok = (len(ops) >= 1 and ops[-1] == "=" and isinstance(division, BinOp) and division.op == "/" and quotient is not None
              and isinstance(quotient, Num) and not lead)
        if not ok:
            bad = Operand((), operands[-1].start if operands else word.start, num.end,
                          error=f"a stated value with a remainder ('{word.text} {num.text}') after something other than the division of two "
                                "numbers", code="ST-PARSE-001")
            self.issues.append(ParseIssue("ST-PARSE-001", bad.error, bad.start, bad.end))
            return Chain(operands=tuple(operands[:-1]) + (bad,), ops=tuple(ops), start=start, end=num.end, lead=lead, connective=connective)
        a, b = division.left, division.right
        div = self._count(IntOp("div", a, b, _start(division), _end(division), written="div"))
        mod = self._count(IntOp("mod", a, b, _start(division), _end(division), written="mod"))
        r_node = self._count(Num(num.value, num.start, num.end))
        q_chain = Chain(operands=tuple(operands[:-2]) + (Operand((div,), operands[-2].start, operands[-2].end), operands[-1]), ops=tuple(ops),
                        start=start, end=operands[-1].end, lead=lead, connective=connective)
        self.pending.append(Chain(operands=(Operand((mod,), operands[-2].start, operands[-2].end), Operand((r_node,), num.start, num.end)), ops=("=",),
                                  start=operands[-2].start, end=num.end, connective=word.text))
        return q_chain

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
            if tok is not None and not (tok.kind == "REL" or self.is_connective(tok) or tok.kind in ("AMP", "PUNCT") or self._at_remainder()
                                        or self._modulus_ahead()):
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
            if tok.kind == "OP" and tok.text in _INT_OPS:
                # '17 mod 5', '(low + high) // 2': an integer remainder or quotient, at the precedence of × and / (STEM repair 2)
                self.i += 1
                right = self.unary(d)
                written = self.ctx.s[tok.start:tok.end] if self.ctx.s else tok.text
                left = self._count(IntOp(tok.text, left, right, _start(left), _end(right), written=written))
                continue
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
            if tok.kind == "LPAR" and tok.text == "(" and tok.space and _is_value_node(left) and self._alternative_form_at(self.i):
                # stem-precision-6 (round 7): '0.870 (87%)', '3/8 = 0.375 (37.5%)': a bracketed per cent right after a value, ending the
                # operand, restates it in another form; it is no factor (read as the product 0.870·87%, the correct link failed)
                self.i = self._close_index(self.i) + 1
                return left
            if self._juxtaposable(tok, left):
                if tok.kind == "IDENT" and tok.text == "i" and not tok.sub and not tok.space and _ends_in_number(left):
                    self.i += 1
                    left = self._count(Unsupported("a complex number", "i", _start(left), tok.end))
                    continue
                right = self.power(d)
                left = self._count(BinOp("*", left, right, _start(left), _end(right), written="", implicit=True))
                continue
            return left

    def _alternative_form_at(self, k: int) -> bool:
        """The bracket at ``k`` holds only a per cent ('(87%)', '(87 %)', '(37.5%)') and the operand ends right after it."""
        c = self._close_index(k)
        if c is None or c != k + 3:
            return False
        a, b = self.t[k + 1], self.t[k + 2]
        return a.kind == "NUM" and b.kind == "PERCENT" and self._ends_operand(c + 1)

    def _juxtaposable(self, tok: Token, left: Node) -> bool:
        if self.is_connective(tok):
            return False
        if tok.kind in ("FUNC", "LATEX", "LGROUP", "UNSUP", "INF"):
            return True
        if tok.kind == "LPAR":
            return tok.text in "([" and not self._modulus_ahead()
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
            if isinstance(tok.value, tuple):  # parser-safety-1: a superscript run beyond the numeral bound (the lexer never converts it)
                raise self._err(tok.value[0], tok.value[1], tok)
            self.i += 1
            if self.ctx.profile.mode != "sciences" and isinstance(base, Sym) and base.name == "e" and base.kind == "symbol" and isinstance(tok.value, int):
                return self._count(Func("exp", Num(exact_integer(tok.value), tok.start, tok.end), None, _start(base), tok.end))  # e² is exp(2)
            node = self._make_pow(base, tok.value, tok.end, exp_span=(tok.start, tok.end))
            return self._nested_power_check(node)
        if tok.kind in ("CARET", "DSTAR"):
            euler = self._euler_power(base, d)
            if euler is not None:
                return euler
            self.i += 1
            first = self.i
            exp = self._exponent(d)
            if isinstance(exp, Unsupported):
                real = self._real_power(base, first, exp, d)
                if real is not None:
                    return self._nested_power_check(real)
                kept = self._symbolic_power(base, first, exp, d)
                if kept is not None:
                    return self._nested_power_check(kept)
                return self._count(Unsupported(exp.reason, exp.text, _start(base), exp.end))
            value, end = exp
            node = self._make_pow(base, value, end, exp_span=(self.t[first].start if first < len(self.t) else end, end))
            return self._nested_power_check(node)
        return base

    def _euler_power(self, base: Node, d: int) -> Optional[Node]:
        """``e^{2(0.693)}``, ``e^{1.386}``, ``e^-0.5`` in a mathematics or Computer Science reading: Euler's number raised
        to a closed exponent is the exponential of that exponent (``Func("exp")``, decided through an enclosure). The
        caret is at ``self.i``; returns None (nothing consumed) for any other base or exponent."""
        if self.ctx.profile.mode == "sciences" or not isinstance(base, Sym) or base.name != "e" or base.kind != "symbol":
            return None
        save = self.i
        nxt = self.peek(1)
        if nxt is None:
            return None
        try:
            if nxt.kind in ("LGROUP", "LPAR"):
                close = self._close_index(self.i + 1)
                if close is None:
                    return None
                self.i += 2
                arg = self.expr(self._descend(d))
                if self.i != close:
                    self.i = save
                    return None
                self.i = close + 1
                end = self.t[close].end
            elif nxt.kind == "NUM" and nxt.value is not None and not nxt.value.based:
                self.i += 2
                arg = Num(nxt.value, nxt.start, nxt.end)
                end = nxt.end
            elif nxt.kind == "OP" and nxt.text == "-" and self.peek(2) is not None and self.peek(2).kind == "NUM" and self.peek(2).value is not None:
                num = self.peek(2)
                self.i += 3
                arg = Neg(Num(num.value, num.start, num.end), nxt.start, num.end)
                end = num.end
            else:
                return None
        except _OperandError:
            self.i = save
            return None
        if any(isinstance(n, (Unsupported, Quantity, WithUnit)) for n in walk(arg)):
            self.i = save
            return None
        if any(isinstance(n, Sym) and n.kind != "constant" for n in walk(arg)):
            # e^(−8k): a symbolic power, outside the encodings as a value; the node keeps its exponent so a step between two
            # relations in which an unknown appears only in such powers can be read in one variable (relations._exp_reading)
            return self._count(Unsupported("a symbolic power", "e^…", _start(base), end, name="exp", arg=arg))
        return self._count(Func("exp", arg, None, _start(base), end))

    def _real_power(self, base: Node, first: int, exp: Unsupported, d: int) -> Optional[Node]:
        """``10^(−8.2)``, ``10^0.4``, ``2^{1/3}``: a closed base with no unit raised to a closed exponent that is no integer
        (the tokens ``self.t[first:self.i]`` that ``_exponent`` read), as one ``RealPower`` value. None (the power stays
        unsupported, with the exponent reader's reason) when the exponent names a symbol or a function, holds anything but
        figures, signs, brackets and ``\\frac``, or when either side is not a closed value with no unit."""
        if exp.reason not in _NON_INTEGER_EXPONENTS or not _closed_value(base):
            return None
        toks = self.t[first:self.i]
        if not toks or any(t.kind not in _CLOSED_EXPONENT_TOKENS for t in toks):
            return None
        if toks[0].kind in ("LPAR", "LGROUP") and self._close_index(first) == self.i - 1:
            toks = toks[1:-1]
        node = self._sub_expression(toks, d)
        if node is None or not _closed_value(node):
            return None
        return self._count(RealPower(base, node, _start(base), exp.end))

    def _symbolic_power(self, base: Node, first: int, exp: Unsupported, d: int) -> Optional[Node]:
        """``1.05^t``, ``2^(t/3)``, ``0.5^{n-1}``: a closed base with no unit raised to an exponent that holds symbols. The
        power stays outside the encodings as a value (``Unsupported``, 'a symbolic power', as before), but the node keeps its
        base and exponent (``name`` "pow") so a model evaluation can read it (``models.py``). None (the plain node) when the
        exponent holds anything but figures, symbols, signs, operators, brackets and ``\\frac``, or the base is not closed."""
        if exp.reason != "a symbolic power" or not _closed_value(base):
            return None
        toks = self.t[first:self.i]
        if not toks or any(t.kind not in _SYMBOLIC_EXPONENT_TOKENS for t in toks):
            return None
        if toks[0].kind in ("LPAR", "LGROUP") and self._close_index(first) == self.i - 1:
            toks = toks[1:-1]
        node = self._sub_expression(toks, d)
        if node is None or any(isinstance(n, (Unsupported, Quantity, WithUnit, Percent, Degrees, PlusMinus, Apply, Magnification, Ratio, BoolOp))
                               for n in walk(node)):
            return None
        if not any(isinstance(n, Sym) and n.kind == "symbol" for n in walk(node)):
            return None
        return self._count(Unsupported("a symbolic power", exp.text, _start(base), exp.end, name="pow", arg=node, base=base))

    def _sub_expression(self, toks: tuple[Token, ...], d: int) -> Optional[Node]:
        """``toks`` (a slice of this span's tokens) read as exactly one expression, or None. The parser's position and token
        list are restored whatever happens, and nothing it records is kept unless the slice reads as one expression."""
        if not toks:
            return None
        saved_t, saved_i, saved_amb, saved_issues = self.t, self.i, len(self.amb), len(self.issues)
        self.t, self.i = tuple(toks), 0
        try:
            node: Optional[Node] = self.expr(d)
            ok = self.i == len(self.t)
        except _OperandError:
            node, ok = None, False
        finally:
            self.t, self.i = saved_t, saved_i
        if not ok:
            del self.amb[saved_amb:]
            del self.issues[saved_issues:]
            return None
        return node

    def _nested_power_check(self, node: Node) -> Node:
        tok = self.peek()
        if tok is not None and (tok.kind in ("CARET", "DSTAR") or (tok.kind == "SUP" and not tok.space)):
            end = self._skip_operand()
            return self._count(Unsupported("a nested power (a power of a power without brackets)", "", _start(node), end))
        return node

    def _make_pow(self, base: Node, value: "int | str", end: int, exp_span: Optional[tuple[int, int]] = None) -> Node:
        """``base ^ value`` for an exponent the exponent reader read as an integer (or ``"half"``, a square root). An integer
        power beyond ``max_int_power`` of a closed value with no unit (``(1 + 0.065/12)^{-60}``, ``1.003^{144}``, ``2^{20}``) is
        one value, a ``RealPower`` whose exponent is the written integer (``exp_span``: where the exponent is written), up to
        an exponent of 1000: the encoder writes it exactly when its value fits a literal and otherwise encloses it, as it
        does a non-integer power. The bound still holds for every other base (a power of an expression in symbols or with a
        unit is a polynomial of that degree) and for a larger exponent: beyond it the power is unsupported."""
        if value == "half":
            return self._count(Root(base, 2, _start(base), end))
        if not isinstance(value, int):
            return self._count(Unsupported("a symbolic power", "", _start(base), end))
        if abs(value) > self.lim.max_int_power:
            if exp_span is not None and abs(value) <= _MAX_CLOSED_INT_POWER and _closed_value(base):
                a, b = exp_span
                magnitude: Node = Num(exact_integer(abs(value)), a, b)
                exponent = Neg(magnitude, a, b) if value < 0 else magnitude
                return self._count(RealPower(base, exponent, _start(base), end))
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
            if tok.value in COMPLETE_UNSUP:
                self.i += 1  # a whole combination or permutation count: the token is the operand (it applies to nothing after it)
                return self._count(Unsupported(str(tok.value), tok.text, tok.start, tok.end))
            finite = self._finite_sum(tok, d) if tok.value == "a sum (Σ)" else None
            if finite is not None:
                return finite
            integral = self._indefinite_integral(tok, d) if tok.value == "an integral" and tok.text in ("∫", "\\int") else None
            if integral is None and tok.value == "an integral" and tok.text in ("∫", "\\int"):
                integral = self._definite_integral(tok, d)  # STEM repair 10 (rule definite-integral): ∫₀¹ 6t dt
            if integral is not None:
                return integral
            if tok.value == "an ellipsis" and self.i > 0 and self.t[self.i - 1].kind == "NUM" and "." in self.t[self.i - 1].text:
                # STEM repair 10 (rule ellipsis-rounding): an ellipsis right after a decimal cuts its digits ('0.333…', '2.66\ldots') and
                # applies to nothing after it: '0.333… × 3 = 1' multiplies the cut value by 3. Taking '× 3' as the marker's operand had
                # read the product as the cut value itself, restated as 1, and the correct line failed
                self.i += 1
                return self._count(Unsupported(str(tok.value), tok.text, tok.start, tok.end))
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

    def _limits(self, j: int) -> Optional[tuple[Node, Node, int]]:
        """STEM repair 10 (rule definite-integral): the limits written at token ``j``, a lower limit as a subscript and an upper one as a
        superscript (``₀¹``, ``_0^1``, ``_{0}^{2}``, ``_0^{2}``, and with a sign: ``₋₁¹``, ``_{-1}^{1}``, ``₋₂⁻¹``, ``_{-2}^{-1}``), each a
        whole number written with digits alone and at most a minus sign (a decimal or a symbol is no limit read: None), as ``(lower,
        upper, the index just past them)``."""
        sub = self.t[j] if j < len(self.t) else None
        if sub is None or sub.kind != "SUB" or sub.space:
            return None
        raw = self.ctx.s[sub.start:sub.end]
        value = str(sub.value or "")
        if not re.fullmatch(r"_?\{?\s*[-−]?\s*\d{1,3}\s*\}?|₋?[₀-₉]{1,3}", raw) or not re.fullmatch(r"-?\d{1,3}", value):
            return None
        lo = _signed_limit(int(value), sub.start, sub.end)
        nxt = self.t[j + 1] if j + 1 < len(self.t) else None
        if nxt is None or nxt.space:
            return None
        if nxt.kind == "SUP" and isinstance(nxt.value, int) and re.fullmatch(r"⁻?[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,3}", self.ctx.s[nxt.start:nxt.end]):
            return lo, _signed_limit(nxt.value, nxt.start, nxt.end), j + 2
        if nxt.kind != "CARET":
            return None
        k = j + 2
        opened = k < len(self.t) and self.t[k].kind in ("LGROUP", "LPAR") and self.t[k].text in ("{", "(")
        if opened:
            k += 1
        sign = 1
        if k < len(self.t) and self.t[k].kind == "OP" and self.t[k].text in ("-", "−"):
            sign, k = -1, k + 1
        num = self.t[k] if k < len(self.t) else None
        if num is None or num.kind != "NUM" or num.value is None or not re.fullmatch(r"\d{1,3}", num.text):
            return None
        k += 1
        if opened:
            if k >= len(self.t) or self.t[k].kind not in ("RGROUP", "RPAR"):
                return None
            k += 1
        return lo, _signed_limit(sign * int(num.text), self.t[j + 2].start, num.end), k

    def _definite_integral(self, tok: Token, d: int) -> Optional[Node]:
        """STEM repair 10 (rule definite-integral): ``∫₀¹ 6t dt``, ``\\int_0^2 (3x^2 + 1)\\,dx``: an integral with whole-number limits, its
        integrand, its variable and its limits kept on the node (``name`` "∫t", ``arg`` the integrand, ``lo`` and ``hi``), so the relations
        stage can set it against its evaluation (the antiderivative the STEM pack forms by the power rule, or the one the answer states
        in an evaluation bracket). The node stays an integral (outside the encodings as a value). The integrand is the stretch between
        the limits and the differential, as for an indefinite integral; anything else (other limits, no differential) returns None, and
        the integral is read as before."""
        lim = self._limits(self.i + 1)
        if lim is None:
            return None
        lo, hi, start = lim
        depth_ = 0
        j = start
        diff: Optional[int] = None
        while j < len(self.t) and j - start <= _MAX_SCAN:
            tk = self.t[j]
            if tk.kind in ("LPAR", "LGROUP"):
                depth_ += 1
            elif tk.kind in ("RPAR", "RGROUP"):
                if depth_ == 0:
                    break
                depth_ -= 1
            elif depth_ == 0 and (tk.kind == "REL" or self.is_connective(tk)):
                break
            elif depth_ == 0 and tk.kind == "IDENT" and len(tk.text) == 2 and tk.text[0] == "d" and tk.text[1].isalpha() and not tk.sub and not tk.primes:
                diff = j
                break
            j += 1
        if diff is None or diff == start:
            return None
        inner = _Parser(self.t[start:diff], self.ctx, {})
        inner.nodes = self.nodes
        try:
            body = inner.expr(self._descend(d))
        except _OperandError:
            return None
        if inner.i != diff - start or any(isinstance(n, (Unsupported, Quantity, WithUnit, Apply)) for n in walk(body)):
            return None
        self.nodes = inner.nodes
        self.i = diff + 1
        return self._count(Unsupported("an integral", tok.text, tok.start, self.t[diff].end, name="∫" + self.t[diff].text[1], arg=body, lo=lo, hi=hi))

    def _indefinite_integral(self, tok: Token, d: int) -> Optional[Node]:
        """``∫6t dt``, ``∫(6t − 3t²) dt``, ``\\int x\\,dx``: an integral with no limits, its integrand and its variable kept on
        the node (``name`` "∫t", ``arg`` the integrand), so a stated antiderivative can be set against it (relations: the
        derivative of the stated antiderivative against the integrand). The node stays an integral (outside the encodings as
        a value). The integrand is the whole stretch between the sign and the differential (a bounded scan for ``d`` and a
        letter at bracket depth 0). Returns None (nothing consumed) for limits or any other shape."""
        nxt = self.peek(1)
        if nxt is None or nxt.kind in ("SUB", "SUP", "CARET"):
            return None
        depth_ = 0
        j = self.i + 1
        diff: Optional[int] = None
        while j < len(self.t) and j - self.i <= _MAX_SCAN:
            tk = self.t[j]
            if tk.kind in ("LPAR", "LGROUP"):
                depth_ += 1
            elif tk.kind in ("RPAR", "RGROUP"):
                if depth_ == 0:
                    break
                depth_ -= 1
            elif depth_ == 0 and (tk.kind == "REL" or self.is_connective(tk)):
                break
            elif depth_ == 0 and tk.kind == "IDENT" and len(tk.text) == 2 and tk.text[0] == "d" and tk.text[1].isalpha() and not tk.sub and not tk.primes:
                diff = j
                break
            j += 1
        if diff is None or diff == self.i + 1:
            return None
        inner = _Parser(self.t[self.i + 1:diff], self.ctx, {})
        inner.nodes = self.nodes
        try:
            body = inner.expr(self._descend(d))
        except _OperandError:
            return None
        if inner.i != diff - self.i - 1 or any(isinstance(n, (Unsupported, Quantity, WithUnit, Apply)) for n in walk(body)):
            return None
        self.nodes = inner.nodes
        self.i = diff + 1
        return self._count(Unsupported("an integral", tok.text, tok.start, self.t[diff].end, name="∫" + self.t[diff].text[1], arg=body))

    def _finite_sum(self, tok: Token, d: int) -> Optional[Node]:
        """``\\sum_{k=1}^{4} k^2``, ``Σ_{k=1}^{4} k²``: a sum over written integer bounds is the explicit finite sum of
        its terms (the index replaced by each integer), so it is decided as arithmetic; Σ with symbolic bounds stays
        unsupported (section 7.8). Bounded: at most ``_MAX_SUM_TERMS`` terms, and the node bound holds. Returns None
        (nothing consumed) for any other shape."""
        save = self.i
        j = self.i + 1
        sub = self.t[j] if j < len(self.t) else None
        if sub is None or sub.kind != "SUB":
            return None
        raw = self.ctx.s[sub.start:sub.end].replace("{", "").replace("}", "").lstrip("_").replace(" ", "")
        name, eqs, lo_text = raw.partition("=")
        if not eqs or not (len(name) == 1 and name.isalpha() and name.isascii()) or not _signed_digits(lo_text):
            return None
        j += 1
        hi_val: Optional[int] = None
        nxt = self.t[j] if j < len(self.t) else None
        if nxt is not None and nxt.kind == "SUP" and isinstance(nxt.value, int) and not nxt.space:
            hi_val, j = nxt.value, j + 1
        elif nxt is not None and nxt.kind == "CARET":
            g = self.t[j + 1] if j + 1 < len(self.t) else None
            if g is not None and g.kind == "NUM" and g.value is not None and g.value.exact and not g.value.based and g.value.value.denominator == 1:
                hi_val, j = int(g.value.value), j + 2
            elif g is not None and g.kind in ("LGROUP", "LPAR"):
                c = self._close_index(j + 1)
                inner = self.t[j + 2:c] if c is not None else ()
                if c is not None and len(inner) == 1 and inner[0].kind == "NUM" and inner[0].value is not None and inner[0].value.exact \
                        and not inner[0].value.based and inner[0].value.value.denominator == 1:
                    hi_val, j = int(inner[0].value.value), c + 1
        if hi_val is None:
            return None
        lo_val = int(lo_text)
        if hi_val < lo_val or hi_val - lo_val + 1 > _MAX_SUM_TERMS:
            return None
        self.i = j
        try:
            body = self.term(self._descend(d))
        except _OperandError:
            self.i = save
            return None
        if any(isinstance(n, (Unsupported, Quantity, WithUnit, Apply)) for n in walk(body)):
            self.i = save
            return None
        end = getattr(body, "end", tok.end)
        total: Optional[Node] = None
        for v in range(lo_val, hi_val + 1):
            term_node = _substitute_index(body, name, v)
            if term_node is None:
                self.i = save
                return None
            total = term_node if total is None else self._count(BinOp("+", total, term_node, tok.start, end))
        return total

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
            node: Node = self._count(Quantity(num, expr, tok.start, end))
            # stem-precision-5 (round 7): a compound quantity ('4 min 30 s', '1 kg 250 g', '1 h 2 min 3 s') is the sum of its parts, never
            # its last part: each part a numeral and one unit atom of the same dimension, strictly smaller than the one before
            while self.i < len(self.t) and self.t[self.i].kind == "NUM" and self.t[self.i].space and compound_part(self.t, self.i) \
                    and self.t[self.i].value is not None:
                ntok = self.t[self.i]
                more = self._unit_after(self.i + 1, glued_ok=False)
                if more is None or more[1] != self.i + 2:
                    break
                part = self._count(Quantity(ntok.value, more[0], ntok.start, self.t[more[1] - 1].end))
                self.i = more[1]
                node = self._count(BinOp("+", node, part, tok.start, _end(part), written="+", implicit=True))  # juxtaposed parts: a sum
            return node
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
        elif self._greek_prefixed_at(j) and (first.space or glued_ok):
            k = j + 2  # a Latin prefix glued to a Greek unit symbol: 'kΩ', 'MΩ', 'mΩ' (the lexer reads Ω as a token of its own)
        elif first.kind == "IDENT" and not first.sub and not first.primes and not first.delta:
            word = first.text
            if first.space and english_word_atom(word):
                return None  # 'x = 5 as before', '10 am': an English word, never an atto-prefixed unit
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
            e = self._ascii_unit_exponent(k)
            if e is not None:
                k = e
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
                if english_word_atom(tk.text):
                    break  # 'mg dm⁻³ at A': the word ends the unit
                if is_unit_atom(tk.text, bare_m=prof.bare_m, tonne=prof.tonne):
                    k += 1
                    continue
                if tk.text.lower() == "per" and k + 1 < n and toks[k + 1].kind == "IDENT" and toks[k + 1].space and not toks[k + 1].sub \
                        and not english_word_atom(toks[k + 1].text) and is_unit_atom(toks[k + 1].text, bare_m=prof.bare_m, tonne=prof.tonne):
                    k += 2  # 'mm³ per g per hour', 'counts per minute': a unit divided by the atom after 'per' (STEM repair 3)
                    continue
                if self._greek_prefixed_at(k):
                    k += 2  # a further prefixed Greek atom: 'A kΩ'
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
                if tk.text == "/" and nx.kind == "IDENT" and not nx.space and not nx.delta and not nx.primes and self._glued_digit_power(nx) \
                        and is_unit_atom(nx.text, bare_m=prof.bare_m, tonne=prof.tonne, glued=False) and self._ascii_unit_end(k + 2):
                    k += 2  # 'm/s2', 'kg/m3': a digit glued to a one-letter unit after a slash is its power (the lexer reads it as a subscript)
                    continue
                if self._greek_prefixed_at(k + 1) and not (tk.text == "*" and nx.space):
                    k += 3  # 'V/kΩ', 'mA·kΩ'
                    continue
                if nx.kind == "TEXT" or (nx.kind == "DEGREE" and nx.text in ("°C", "°F")):
                    k += 2
                    continue
                if tk.text == "/" and nx.kind == "LPAR" and nx.text == "(":
                    c = self._close_index(k + 1)
                    if c is not None and c > k + 2 and (all(x.kind in ("IDENT", "SUP", "OP") for x in toks[k + 2:c]) or unit_group(toks, k + 2, c, prof)):
                        k = c + 1
                        continue
                break
            if tk.kind == "DEGREE" and tk.text in ("°C", "°F") and tk.space:
                k += 1
                continue
            break
        if not self._ends_operand(k) and not (k < n and toks[k].kind == "NUM" and toks[k].space and compound_part(toks, k)):
            return None  # (a compound quantity's next part may follow: stem-precision-5)
        text = self.ctx.s[toks[j].start:toks[k - 1].end]
        expr = parse_unit(text, bare_m=prof.bare_m, tonne=prof.tonne, ascii_exponents=True)  # only the forms read above carry a glued digit
        if expr is None:
            return None
        if expr.readings and expr.readings[0].atoms and expr.readings[0].atoms[0].unit is None:
            return None
        return expr, k

    def _ascii_unit_exponent(self, k: int) -> Optional[int]:
        """The index after an ASCII exponent glued to the unit atom at ``k - 1`` (``3 m s-1``, ``1 mol dm-3``, ``J kg-1 K-1``: a
        hyphen-minus or plus and one digit; ``25 cm3``, ``mol2 dm-6``: one digit 2 to 9 after an atom of two or more letters), or
        None. Before this reading ``3 m s-1`` was ``3 m s − 1``, a subtraction of a bare number from a quantity. Never read: more
        digits or a decimal (``300 K-273``, ``5 m-1.5``), a digit with a space on either side of the sign (``5 m - 3``), a sign
        followed by an atom of the same dimension (``5 m-3 m`` is a subtraction of lengths), and a one-letter atom's glued digit
        outside a denominator (``2 m2`` may be 2·m₂, and ``H2`` a formula: the lexer reads it as a subscript)."""
        toks = self.t
        n = len(toks)
        if k <= 0 or k >= n:
            return None
        prev, tk = toks[k - 1], toks[k]
        if prev.kind != "IDENT" or prev.sub or prev.primes or prev.delta or not (prev.text.isalpha() or prev.text in ("Ω", "μ", "µ")):
            return None
        if tk.kind == "OP" and tk.text in ("-", "+") and not tk.space and k + 1 < n and toks[k + 1].kind == "NUM" and not toks[k + 1].space \
                and _one_digit(toks[k + 1], low=1):
            end = k + 2
        elif tk.kind == "NUM" and not tk.space and len(prev.text) >= 2 and _one_digit(tk, low=2):
            end = k + 1
        else:
            return None
        if not self._ascii_unit_end(end):
            return None
        after = toks[end] if end < n else None
        if tk.kind == "OP" and after is not None and after.kind == "IDENT" and after.space and not after.sub:
            prof = self.ctx.profile
            here = lookup_atom(prev.text, bare_m=prof.bare_m, tonne=prof.tonne)
            there = lookup_atom(after.text, bare_m=prof.bare_m, tonne=prof.tonne)
            if here and there and here[0].dim is not None and there[0].dim is not None and here[0].dim.same_physical(there[0].dim):
                return None  # '5 m-3 m': a subtraction of two lengths, not m⁻³ m
        return end

    def _ascii_unit_end(self, k: int) -> bool:
        """An ASCII exponent ends here: the operand ends, or a spaced unit atom (or a slash, a product sign) continues the unit."""
        toks = self.t
        if k >= len(toks):
            return True
        tk = toks[k]
        if tk.kind == "IDENT" and tk.space:
            return True
        if tk.kind == "OP" and tk.text in ("/", "·", "*") and not tk.space:
            return True
        return self._ends_operand(k)

    def _glued_digit_power(self, tok: Token) -> bool:
        """A one-letter identifier whose 'subscript' is one digit 2 to 9 written right after the letter (``s2``, not ``s_2``)."""
        sub = tok.sub
        if len(sub) != 1 or not "2" <= sub <= "9" or len(tok.text) != 1:
            return False
        at = tok.start + len(tok.text)
        return at < len(self.ctx.s) and self.ctx.s[at] == sub

    def _greek_prefixed_at(self, j: int) -> bool:
        """Tokens ``j`` and ``j + 1`` are a Latin SI prefix and a Greek unit symbol written together (``k`` + ``Ω``), with
        nothing attached to either (no subscript, prime or Δ) and no space between them (:func:`.units.prefixed_greek_unit`)."""
        toks = self.t
        if j + 1 >= len(toks):
            return False
        a, b = toks[j], toks[j + 1]
        return (a.kind == "IDENT" and b.kind == "IDENT" and not b.space and not a.sub and not a.primes and not a.delta and not b.sub and not b.primes
                and not b.delta and prefixed_greek_unit(a.text, b.text))

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

    def _leibniz_read(self, tok: Token, j: int, d: int) -> Optional[Node]:
        """Rule ``derivative`` (STEM repair 11): a Leibniz derivative from token ``self.i`` to ``j`` read with what it is of: the letter
        differentiated and the variable ('dv/dt', 'd²s/dt²', 'dθ/dt'), or, for the operator form, the bracketed expression right after it
        ('d/dt (3t²)', 'd/dx(x³ − 2x)'). The node keeps them (``arg``, ``var``, ``order``) for the relations' derivative check and is never
        encoded itself. None (the earlier reading: the rest of the operand skipped, nothing kept) when the derivative is not the whole
        operand (an operator or anything else follows it before a relation sign, a connective or punctuation)."""
        parts = _leibniz_parts(self.t, self.i, j)
        if parts is None:
            return None
        letter, var, order = parts

        def ends(k: int) -> bool:
            return k >= len(self.t) or self.t[k].kind in _DERIVATIVE_ENDS or self.is_connective(self.t[k])

        if letter:
            if not ends(j):
                return None
            self.i = j
            return self._count(Unsupported("a derivative", f"d{letter}/d{var}", tok.start, self.t[j - 1].end,
                                           arg=Sym(letter, "symbol", tok.start, self.t[j - 1].end), var=var, order=order))
        if j >= len(self.t) or self.t[j].kind != "LPAR" or self.t[j].text != "(":
            return None
        close = self._close_index(j)
        if close is None or close == j + 1 or not ends(close + 1):
            return None
        saved = self.i
        try:
            arg = self._sub_parse(j, close, tuple(self.t[j + 1:close]), self._descend(d))
        except _OperandError:
            self.i = saved
            return None
        self.i = close + 1
        return self._count(Unsupported("a derivative", f"d/d{var}(…)", tok.start, self.t[close].end, arg=arg, var=var, order=order))

    def _ident(self, tok: Token, d: int) -> Node:
        prof = self.ctx.profile
        word = tok.text
        nxt = self.peek(1)
        # a limit written as a word
        if word == "lim" and not tok.sub:
            self.i += 1
            end = self._skip_operand()
            return self._count(Unsupported("a limit", "lim", tok.start, max(end, tok.end)))
        # derivatives: d/dx, dy/dx (plain). Rule leibniz (STEM repair 7): any one letter or Greek letter differentiated, of any order
        # written with its marker ('dN/dt', 'dθ/dt', 'd²v/dt²', 'd^2y/dx^2', 'd2y/dx2', 'd²/dx²'), not only dy, dv, ds and dx: read as
        # products of symbols ('d²v/dt²' was d²·v/(d·t²), "an equation in an unknown"), they had neither a check nor an ST code
        leibniz = _leibniz_end(self.t, self.i)
        if leibniz is not None or (word in ("d", "dy", "dx", "dt", "dv", "ds") and nxt is not None and nxt.kind == "OP" and nxt.text == "/"
                                   and self.peek(2) is not None and self.peek(2).kind == "IDENT" and self.peek(2).text.startswith("d")
                                   and len(self.peek(2).text) >= 2):
            read = self._leibniz_read(tok, leibniz, d) if leibniz is not None else None
            if read is not None:
                return read
            self.i += 1
            end = self._skip_operand()
            return self._count(Unsupported("a derivative", word + "/d…", tok.start, max(end, tok.end)))
        # f′(x), f'(1): a derivative, never encoded. With one plain argument the node keeps the name and the argument, so the
        # relations can set an evaluation f′(2) = 3 × 2² − 2 against a formula f′(x) = 3x² − 2 the answer states (the stated
        # formula itself stays undecided: differentiation is outside the encodings). Rule prime-derivative (STEM repair 7): any one
        # letter or Greek letter with primes written applied to a bracket ('v′(t)', "v'(1)", 's″(t)', 'θ′(t)'), not only f, g and h:
        # read as a primed symbol times the bracket ("v'·t"), it had neither a check nor an ST code
        if tok.primes and (word in _FUNCTION_LETTERS or len(word) == 1) and nxt is not None and nxt.kind == "LPAR" and nxt.text == "(" and not nxt.space:
            close = self._close_index(self.i + 1)
            if close is None:
                raise self._err("ST-PARSE-001", "an unbalanced bracket", nxt)
            inner_toks = self.t[self.i + 2:close]
            if not tok.sub and _single_argument(inner_toks):
                self.i += 2
                arg = self.expr(self._descend(d))
                self.i = close + 1
                return self._count(Unsupported("a derivative", word + "'" * tok.primes + "(…)", tok.start, self.t[close].end,
                                               name=symbol_name(word, "", tok.primes), arg=arg))
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
            if isinstance(nxt.value, tuple):  # parser-safety-1: an overlong superscript run
                raise self._err(nxt.value[0], nxt.value[1], nxt)
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
            # STEM repair 10 (rule definite-integral): whole-number limits that end the operand are kept on the node with the bracketed
            # antiderivative ('[3t²]₀¹'), so the relations stage can evaluate it between them; the node stays outside the encodings
            lim = self._limits(self.i) if limits else None
            ends = lim is not None and (lim[2] >= len(self.t) or self.t[lim[2]].kind in ("REL", "PUNCT", "AMP") or self.is_connective(self.t[lim[2]]))
            end = self._skip_operand()
            reason = "the evaluation of an antiderivative between limits" if limits else "a subscript on a bracketed expression"
            if ends and lim is not None and not any(isinstance(n, (Unsupported, Quantity, WithUnit, Apply)) for n in walk(node)):
                return self._count(Unsupported(reason, "", _start(node), end, arg=node, lo=lim[0], hi=lim[1]))
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
            # \frac{d}{dx} and \frac{dy}{dx}: a derivative (rule leibniz, STEM repair 7: \frac{dN}{dt}, \frac{d\theta}{dt}, \frac{d^2y}{dx^2},
            # \frac{d^{2}}{dx^{2}} too: the two groups read as one Leibniz form)
            (a0, a1, num_t), (b0, b1, den_t) = args
            joined = tuple(num_t) + (Token("OP", "/", num_t[-1].end, num_t[-1].end),) + tuple(den_t)
            if (len(num_t) <= 3 and num_t[0].kind == "IDENT" and num_t[0].text in ("d", "dy", "dv", "ds", "dx") and len(den_t) == 1 and den_t[0].kind == "IDENT"
                    and den_t[0].text.startswith("d") and len(den_t[0].text) == 2) or _leibniz_end(joined, 0) == len(joined):
                # STEM repair 11 (rule derivative): \frac{dv}{dt}, and \frac{d}{dt} before a bracketed expression, keep what they are of
                parts = _leibniz_parts(joined, 0, len(joined)) if _leibniz_end(joined, 0) == len(joined) else None
                if parts is not None:
                    letter, var, order = parts
                    k = self.i
                    if letter and (k >= len(self.t) or self.t[k].kind in _DERIVATIVE_ENDS or self.is_connective(self.t[k])):
                        return self._count(Unsupported("a derivative", f"d{letter}/d{var}", tok.start, self.t[b1].end,
                                                       arg=Sym(letter, "symbol", tok.start, self.t[b1].end), var=var, order=order))
                    if not letter and k < len(self.t) and self.t[k].kind == "LPAR" and self.t[k].text == "(":
                        close = self._close_index(k)
                        if close is not None and close > k + 1 and (close + 1 >= len(self.t) or self.t[close + 1].kind in _DERIVATIVE_ENDS
                                                                     or self.is_connective(self.t[close + 1])):
                            try:
                                arg = self._sub_parse(k, close, tuple(self.t[k + 1:close]), self._descend(d))
                            except _OperandError:
                                arg = None
                            if arg is not None:
                                self.i = close + 1
                                return self._count(Unsupported("a derivative", f"d/d{var}(…)", tok.start, self.t[close].end, arg=arg, var=var,
                                                               order=order))
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


def _closed_value(node: Node) -> bool:
    """A closed value with no unit: figures, arithmetic, closed functions and π (``10``, ``3465/250``, ``(8.04 × 10⁸)``), never
    a symbol, a unit, an angle, a per cent, a ``±`` or anything unsupported (the base and exponent of a ``RealPower``)."""
    for n in walk(node):
        if isinstance(n, Sym) and n.kind == "constant":
            continue
        if isinstance(n, (Sym, Apply, Unsupported, Quantity, WithUnit, Degrees, Percent, PlusMinus, Ratio, BoolOp, Magnification)):
            return False
    return True


#: the most terms a Σ over written integer bounds is expanded into (section 4.9 keeps the node bound too)
_MAX_SUM_TERMS = 24


def _signed_digits(text: str) -> bool:
    t = text[1:] if text[:1] in "-−" else text
    return 0 < len(t) <= 4 and t.isascii() and t.isdigit()


def _substitute_index(node: Node, name: str, value: int) -> Optional[Node]:
    """``node`` with the index ``name`` replaced by the exact integer ``value``."""
    num: Node = Num(exact_integer(abs(value)))
    return replace_symbol(node, name, Neg(num) if value < 0 else num)


def _is_digit_tokens(toks: tuple[Token, ...], digit: str) -> bool:
    return len(toks) == 1 and toks[0].kind == "NUM" and toks[0].text == digit


def _one_digit(tok: Token, *, low: int) -> bool:
    """A numeral of exactly one ASCII digit from ``low`` to 9 (an ASCII unit exponent: ``s-1``, ``cm3``)."""
    num = tok.value
    return len(tok.text) == 1 and "0" <= tok.text <= "9" and int(tok.text) >= low and num is not None and not num.has_point \
        and not num.scientific and num.base == 10


#: rule leibniz (STEM repair 7): the orders a derivative's marker may state ('d²v/dt²' … 'd⁹y/dx⁹')
_LEIBNIZ_ORDERS = range(2, 10)


def _order_marker(toks: "tuple[Token, ...] | list[Token]", k: int) -> tuple[int, int]:
    """Rule ``leibniz`` (STEM repair 7): the order a Leibniz marker written right after token ``k - 1`` states (``²``, ``^2``, ``^{2}``,
    ``**2``, or a digit glued on, as in ``d2y/dx2``) and the index after it; ``(1, k)`` when no marker is written there."""
    n = len(toks)
    if k >= n or toks[k].space:
        return 1, k
    t = toks[k]
    if t.kind == "SUP" and isinstance(t.value, int) and t.value in _LEIBNIZ_ORDERS:
        return t.value, k + 1
    if t.kind in ("CARET", "DSTAR") and k + 1 < n and not toks[k + 1].space:
        u = toks[k + 1]
        if u.kind == "NUM" and u.text.isdigit() and len(u.text) == 1 and int(u.text) in _LEIBNIZ_ORDERS:
            return int(u.text), k + 2
        if (u.kind == "LGROUP" or (u.kind == "LPAR" and u.text == "{")) and k + 3 < n and toks[k + 2].kind == "NUM" and toks[k + 2].text.isdigit() \
                and len(toks[k + 2].text) == 1 and int(toks[k + 2].text) in _LEIBNIZ_ORDERS \
                and (toks[k + 3].kind == "RGROUP" or (toks[k + 3].kind == "RPAR" and toks[k + 3].text == "}")):
            return int(toks[k + 2].text), k + 4  # '^{2}', in LaTeX or written in plain text
    if t.kind == "NUM" and t.text.isdigit() and len(t.text) == 1 and int(t.text) in _LEIBNIZ_ORDERS:
        return int(t.text), k + 1
    return 1, k


def _one_letter(t: Token) -> bool:
    """A symbol of one Latin or Greek letter (its subscript allowed), with no prime and no Δ."""
    return t.kind == "IDENT" and len(t.text) == 1 and t.text.isalpha() and not t.primes and not t.delta


def _d_letter(t: Token) -> bool:
    """``dv``, ``dN``, ``dt``: the letter d glued to one Latin letter, as the lexer reads it (its subscript allowed: ``dv₁``)."""
    return t.kind == "IDENT" and len(t.text) == 2 and t.text[0] == "d" and t.text[1].isascii() and t.text[1].isalpha() and not t.primes and not t.delta


def _leibniz_end(toks: "tuple[Token, ...] | list[Token]", i: int) -> Optional[int]:
    """Rule ``leibniz`` (STEM repair 7): the index just past a derivative written in Leibniz notation that starts at token ``i``, or None.

    The numerator is d with an optional order marker and one letter or Greek letter differentiated (``d²v``, ``d^2y``, ``d2y``, ``dθ``),
    a glued ``dv`` or ``dN``, or d alone with its marker (the operator ``d/dx``, ``d²/dx²``); the denominator is d and one letter or Greek
    letter (``dt``, ``dθ``) with the SAME order marker, so ``d²v/dt²`` is the second derivative and ``d²v/dt`` no Leibniz form at all.
    Bounded: it reads at most a dozen tokens from ``i``."""
    n = len(toks)
    if i >= n:
        return None
    t0 = toks[i]
    if t0.kind != "IDENT" or t0.primes or t0.delta:
        return None
    j = i + 1
    order = 1
    if t0.text == "d" and not t0.sub:
        order, j = _order_marker(toks, j)
        if j < n and _one_letter(toks[j]) and toks[j].text != "d" and (not toks[j].space or order > 1):
            j += 1  # the letter differentiated: 'd²v', 'dθ' (a space only after a marker: 'd^2 v/dt^2')
    elif not _d_letter(t0):
        return None
    if j >= n or toks[j].kind != "OP" or toks[j].text != "/":
        return None
    j += 1
    if j >= n:
        return None
    den = toks[j]
    if _d_letter(den):
        j += 1
    elif den.kind == "IDENT" and den.text == "d" and not den.sub and not den.primes and j + 1 < n and _one_letter(toks[j + 1]) \
            and toks[j + 1].text != "d" and not toks[j + 1].space:
        j += 2  # 'dθ' in the denominator
    else:
        return None
    order2, j = _order_marker(toks, j)
    return j if order2 == order else None


#: rule derivative (STEM repair 11): what may follow a Leibniz derivative read as a whole operand
_DERIVATIVE_ENDS = frozenset({"REL", "RPAR", "RGROUP", "COMMA", "SEMI", "PUNCT", "AMP", "ROWSEP", "COLON"})


def _leibniz_parts(toks: "tuple[Token, ...] | list[Token]", i: int, j: int) -> Optional[tuple[str, str, int]]:
    """Rule ``derivative`` (STEM repair 11): ``(letter differentiated, variable, order)`` of the Leibniz form from token ``i`` to ``j``
    (:func:`_leibniz_end`): ``dv/dt`` gives ('v', 't', 1), ``d²s/dt²`` ('s', 't', 2), the operator ``d/dx`` ('', 'x', 1); None when a
    part carries a subscript, a prime or a Δ (not read)."""
    n = min(len(toks), j)
    if i >= n:
        return None
    t0 = toks[i]
    k = i + 1
    letter = ""
    order = 1
    if t0.text == "d" and not t0.sub:
        order, k = _order_marker(toks, k)
        if k < n and _one_letter(toks[k]) and toks[k].text != "d":
            if toks[k].sub:
                return None
            letter = toks[k].text
            k += 1
    elif _d_letter(t0):
        if t0.sub:
            return None
        letter = t0.text[1]
    else:
        return None
    if k >= n or toks[k].kind != "OP" or toks[k].text != "/":
        return None
    k += 1
    if k >= n:
        return None
    den = toks[k]
    if _d_letter(den):
        if den.sub:
            return None
        var = den.text[1]
    elif den.text == "d" and k + 1 < n and _one_letter(toks[k + 1]) and not toks[k + 1].sub:
        var = toks[k + 1].text
    else:
        return None
    return letter, var, order


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
