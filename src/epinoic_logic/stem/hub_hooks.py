"""Hub hooks of the STEM branches (docs/STEM_DESIGN.md, section 11.2).

The channel's request-fidelity heuristics were written for prose answers. Four readings let a
STEM answer, which is mostly equations, be judged on what it says. ``branches.base.BranchHooks``
is the protocol; :data:`STEM_HOOKS` is attached to the ``sciences``, ``mathematics`` and
``computer_science`` branches only, so every other branch behaves exactly as before.

* :meth:`StemHooks.coverage_terms`: words a claim offers the item-coverage heuristic
  (INT-REQ-004) beyond its own words: the names of the dimensions of its quantities and of the
  bound symbols it uses (m s⁻² gives "acceleration"; N gives "force", "weight", "tension"; J gives
  "energy", "work"), the names of their units ("mm" gives "millimetre", "%" gives "percentage"),
  what its relations produce (stated roots give "root" and "solution", an order relation
  "inequality", a balanced equation "equation" and "reaction", a truth table "truth table", a
  base conversion "binary", "denary", "hexadecimal", an equation in one unknown its degree:
  ``x² = 4`` "quadratic"), a derivative's "gradient", a component's direction (``F_x``:
  "horizontal component") and an operation written in notation that a request names in words
  (``|−2|`` "absolute", "modulus"; ``log`` "logarithm"), so ``a = (20 − 0)/4.0 = 5.0 m s⁻²`` covers
  "Calculate the acceleration". A claim that holds a planned computation (an engine check of its
  arithmetic, substitution, conversion, algebra, roots, balance, Boolean identity or based
  numeral) also offers the computing command words (calculate, determine, find, convert, solve,
  ...): it does compute. The channel never counts those command words as evidence on their own
  for an item that names what it wants (STEM review S3): "2 + 2 = 4" covers no "Calculate the
  acceleration". The method stays a lexical heuristic.
* :meth:`StemHooks.topic_evidence`: whether a computing claim is about a request item beyond the
  words they share: it gives a value to a symbol the item asks for ("Find S₁₀" and
  ``S_{10} = 210``; "Calculate v if ..."; a show-that target; the unknowns of an equation the
  item asks to solve; never a symbol the item gives a value for, an input), or it computes with
  enough of the item's own figures (shared figures weighing three, where a single-digit whole
  number weighs one and any other figure two, or the item's only figure when that is no
  single-digit whole number: "Find the gradient of the line through (1, 3) and (5, 7)" and
  ``m = (7 − 3)/(5 − 1) = 1``; "2 + 2 = 4" is no evidence for "4 m/s in 2 s"), unless the units it
  states name another quantity than any the item names in words (it computes something else
  from the same data). For an item that names what it asks for in notation only, a claim that
  writes the item's own expression token for token is about it ("Calculate 1/2 exactly" and
  ``1/2 = 0.50``, whose figures 1 and 2 are single digits; "2 + 2 = 4" writes nothing of
  "Simplify 2³ × 2⁴").
* :meth:`StemHooks.names_notation`: whether an item whose words are all command words names
  what it asks for in maths ("Solve 3x + 5 = 20", "Simplify √50", "Find u₆ and S₅"): the
  channel then counts a claim as addressing it only when :meth:`StemHooks.topic_evidence` finds
  the claim about that notation (its unknowns, its figures), so "2 + 2 = 4" addresses no
  "Solve 3x + 5 = 20"; "Find the final value", which names nothing, keeps the plain reading.
* :meth:`StemHooks.echo_exempt`: an answer that holds at least one planned computation link
  (``stem-eq``, ``stem-alg`` or ``stem-sol``) whose text is not in the request is never a
  restatement of the request (INT-REQ-011), so the show-that answer ``n = m/M = 36 g / 18 g mol⁻¹
  = 2.0 mol`` to "Show that 36 g of water is 2.0 mol" is an answer.
* :attr:`StemHooks.request_imperatives`: determine, deduce, derive, state, find, solve, sketch,
  estimate, predict, verify, show (each at the start of a sentence or after a part label), so a
  multi-part STEM question becomes one item per part.
* :meth:`StemHooks.word_count_view`: the text a word bound is measured on: each maths span and
  each code block counts as one word, and LaTeX control words are not words.

Every method reads the shared memoised :class:`~.document.StemDocument`, never raises on agent
text (a failure falls back to the channel's own reading), and evaluates nothing.
"""
from __future__ import annotations

import re
from fractions import Fraction
from typing import Optional

from .document import StemDocument, build_document
from .lexer import lex
from .limits import PROFILES
from .nodes import Abs, BinOp, Func, Neg, Num, Percent, Pow, Quantity, Sym, WithUnit, walk
from .units import Dimension

__all__ = ["STEM_HOOKS", "StemHooks", "STEM_IMPERATIVES", "dimension_terms", "unit_terms"]

STEM_IMPERATIVES = ("determine", "deduce", "derive", "state", "find", "solve", "sketch", "estimate", "predict", "verify", "show")
_MATH_KINDS = frozenset({"latex_display", "latex_inline", "math_run", "verbal", "chem"})
_CODE_KINDS = frozenset({"code_block", "code_inline"})
_ECHO_KINDS = frozenset({"eq", "alg", "sol", "sys", "bool", "tt", "base", "cnv"})
#: the tokens an item's expression must hold for a claim that writes it to be about an item that also names a topic in words
_LONG_EXPRESSION_TOKENS = 5
#: planned check kinds that are computations, and the command words a computing claim offers the coverage heuristic (a unit
#: companion, a stated operation and a system's solution compute what their own check does)
_COMPUTE_KINDS = frozenset({"eq", "sub", "alg", "sol", "cnv", "cmp", "res", "chem", "bool", "tt", "base", "unit", "op", "sys"})
_COMPUTE_TERMS = ("calculate", "calculation", "determine", "find", "compute", "work", "show", "solve", "deduce", "derive", "estimate", "verify",
                  "convert", "simplify", "expand", "factorise", "factorize", "balance", "rearrange", "evaluate", "evaluation")
#: what the relations of a claim produce, by relation kind: words a request may use for that output
_KIND_TERMS = {
    "sol": ("root", "roots", "solution", "solutions", "zero", "zeros"),
    "sys": ("simultaneous", "system", "solution", "solutions", "equations"),
    "tt": ("truth", "table"),
    "bool": ("boolean", "Boolean", "expression", "identity", "logic"),  # "Boolean" as a request writes it (read like the item's word)
    "chem": ("equation", "balanced", "reaction"),
    "base": ("binary", "denary", "decimal", "hexadecimal", "octal", "base", "bases"),
}
_ORDER_OPS = frozenset({"<", ">", "≤", "≥", "<=", ">="})
_INEQUALITY_TERMS = ("inequality", "inequalities")
#: a percentage written in the claim (a % sign, "per cent", "percent"): what it computes is a percentage
_PERCENT_RE = re.compile(r"%|\bper\s?cent\b|\bpercent(?:age)?\b", re.IGNORECASE)
_PERCENT_TERMS = ("percentage", "percent", "cent")
#: a derivative written in the claim (f′(2), f'(x), f''(x), dy/dx, \frac{dy}{dx}, \prime; never a possessive such as
#: "Morgan's"): what it computes is a gradient
_DERIVATIVE_RE = re.compile(r"(?<![A-Za-z])[A-Za-z][′']{1,2}\s*\(|\bd[A-Za-z]?\s*/\s*d[A-Za-z]\b|\\frac\{d[A-Za-z]?\}\{d[A-Za-z]\}|\\prime")
_DERIVATIVE_TERMS = ("gradient", "derivative", "slope", "tangent", "differentiate", "rate")
#: the conventional direction of a component written as a subscript (F_x, v_y)
_COMPONENT_TERMS = {"x": ("component", "horizontal"), "y": ("component", "vertical")}
#: operations a request names in words while an answer writes them in notation ("the absolute value" and ``|−2| = 2``,
#: "the logarithm" and ``log 20``, "the sine" and ``sin 30°``), by node (``Abs``) or function name
_NOTATION_TERMS = {"abs": ("absolute", "modulus"), "ln": ("logarithm", "logarithms"), "log": ("logarithm", "logarithms"),
                   "log10": ("logarithm", "logarithms"), "sin": ("sine",), "cos": ("cosine",)}
#: the degree of a polynomial equation in one unknown, as a request names it ("Solve the quadratic equation" and
#: ``x² = 4 ⇒ x = ±2``)
_DEGREE_TERMS = {1: ("linear",), 2: ("quadratic",), 3: ("cubic",), 4: ("quartic",)}
#: maths tokens of an item's own expression (``1/2``, ``2³ × 2⁴``, ``√50``, ``|x − 1|``) and the operators that make one;
#: an operand is a numeral or a one-letter symbol (a word of prose ends the run)
_RUN_OPERANDS = frozenset({"NUM", "IDENT"})
_RUN_OPERATORS = frozenset({"OP", "FUNC", "SUP", "CARET", "BAR", "BANG"})
_RUN_KINDS = _RUN_OPERANDS | _RUN_OPERATORS | {"LPAR", "RPAR"}
_OP_KEYS = {"×": "*", "·": "*", "*": "*", "÷": "/", "/": "/", "−": "-", "-": "-", "+": "+", "±": "±", "∓": "∓"}
_MAX_RUNS = 16
_MAX_RUN_TOKENS = 64
#: SI prefix symbols as words, for unit names ("km" -> "kilometre")
_PREFIX_NAMES = {"k": "kilo", "M": "mega", "G": "giga", "T": "tera", "m": "milli", "µ": "micro", "μ": "micro", "u": "micro", "n": "nano", "p": "pico",
                 "c": "centi", "d": "deci", "h": "hecto", "da": "deca"}
#: unit names that are no word a request uses for them, with the words it does use
_UNIT_NAME_TERMS = {"per cent": ("percentage", "percent", "cent"), "degree Celsius": ("celsius", "degree", "degrees"),
                    "degree Fahrenheit": ("fahrenheit", "degree", "degrees"), "degree": ("degree", "degrees", "angle")}
#: a numeral of an item or a claim (ASCII digits; a superscript run is read as a figure of its own: 2³ writes 2 and 3)
_FIGURE_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
_SUPERSCRIPT_RUN_RE = re.compile("[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
#: the label an item opens with ("(a)", "1.", "ii)", "Question 2:", "Part (b)") and the instructions on the form of its
#: answer ("[2 marks]", "(3 marks)", "to 3 significant figures", "3 s.f.", "2 d.p."): their figures are no data of the item
_ITEM_LEAD_RE = re.compile(r"^\W{0,4}(?:(?:part|question|q)\s*)?(?:\(?(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|\d{1,2}[.):]|\(\d{1,2}\))(?=[\s*:—–-]|$)",
                           re.IGNORECASE)
#: (security round 1) Every quantifier of the bracket forms possessive: each is followed by a token its own characters cannot
#: begin (digits by a space, a plus, 'marks' or the closing bracket; a space by a digit, a plus, 'marks' or the bracket), so its
#: longest reading is the only one the rest can follow and the same annotations are read. The spaces after '[1' were split
#: between two or three quantifiers before failing (quadratic in the run) (tests/channel/test_security_round1_marks.py).
_FORM_RE = re.compile(r"\[\s*+\d++\s*+(?:marks?+)?+\s*+\]|\(\s*+\d++\s*+marks?+\s*+\)"
                      r"|\b\d+\s*(?:significant\s+figures?|sig\.?\s*figs?\.?|s\.\s?f\.?|sf\b|decimal\s+places?|d\.\s?p\.?|dp\b)", re.IGNORECASE)
#: the kinds of symbol node that name a quantity (never a \text{} label, a chemical formula, a bond or π)
_SYMBOL_KINDS = frozenset({"symbol", "word"})
#: a show-that item names its target after these words ("Show that its gradient is m = 1")
_SHOW_THAT_RE = re.compile(r"\bshow\s+that\b", re.IGNORECASE)
#: a symbol an item names with a subscript: S₁₀, u₆, v₀, S_10, S_{10}, F_x (normalised as the front end names them: S_10)
_SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_ITEM_SYMBOL_RE = re.compile(r"(?<![A-Za-z\\])([A-Za-zα-ωΑ-Ω])(?:([₀-₉]+)|_\{?([A-Za-z0-9]{1,4})\}?)")
_SYMBOL = r"([A-Za-zα-ωΑ-Ω])(?:([₀-₉]+)|_\{?([A-Za-z0-9]{1,4})\}?)?"
#: a symbol an item gives a value for ("if d = 120 m", "u₁ = 3"): an input
#: (security round 1) The space around '=' and the sign read possessively: '=', a sign and a digit cannot begin with white space,
#: so each run's longest reading is the only one the rest can follow, and the same inputs are read; the space after '=' was split
#: between two quantifiers before failing (quadratic in the run) (tests/channel/test_security_round1_marks.py).
_GIVEN_RE = re.compile(r"(?<![\w′'.)\\])" + _SYMBOL + r"\s*+=\s*+[-−+]?\s*+\d")
#: a symbol an item asks for in its words, right after a command word ("Calculate v if ...", "Find x.", "Solve for x",
#: "Find the value of k", "Calculate Kc" for K_c); never the article "a"
_ASKED_RE = re.compile(
    r"\b(?:calculate|find|determine|evaluate|work\s+out|estimate|deduce|derive|obtain|write\s+down|solve\s+for)\s+"
    r"(?:(?:the\s+)?(?:exact\s+)?values?\s+of\s+)?(?!a\b|I\b)"
    r"(?:(?-i:(?P<head>[A-Z])(?P<low>[a-z]))|(?P<letter>[A-Za-zα-ωΑ-Ω])(?:(?P<digits>[₀-₉]+)|_\{?(?P<sub>[A-Za-z0-9]{1,4})\}?)?)"
    r"(?![\w′'(\\])", re.IGNORECASE)
#: an item that asks to solve an equation: the unknowns of its equations are what it asks for
_SOLVE_RE = re.compile(r"\bsolve\b", re.IGNORECASE)
_LATEX_WORD_RE = re.compile(r"\\[A-Za-z]+")
_MAX_TERMS = 128


def _d(m: int = 0, kg: int = 0, s: int = 0, a: int = 0, k: int = 0, mol: int = 0, cd: int = 0) -> tuple[int, ...]:
    return (m, kg, s, a, k, mol, cd)


#: dimension (exponents over m, kg, s, A, K, mol, cd) -> words a request may use for such a quantity
_DIMENSION_TERMS: dict[tuple[int, ...], tuple[str, ...]] = {
    _d(m=1): ("length", "distance", "displacement", "height", "width", "radius", "diameter", "wavelength", "extension", "position", "depth", "range",
              "amplitude", "compression", "hypotenuse", "side", "sides", "perimeter", "circumference"),
    _d(kg=1): ("mass", "weight"),
    _d(s=1): ("time", "period", "duration", "interval", "half-life"),
    _d(a=1): ("current",),
    _d(k=1): ("temperature",),
    _d(mol=1): ("amount", "moles", "mole", "mol", "substance"),
    _d(m=1, s=-1): ("speed", "velocity"),
    _d(m=1, s=-2): ("acceleration", "deceleration", "gravitational", "field", "strength"),
    _d(m=1, kg=1, s=-2): ("force", "weight", "tension", "thrust", "friction", "drag", "reaction", "resultant", "load", "gravitational", "electric",
                          "electrostatic", "magnetic", "frictional", "normal", "centripetal", "buoyant", "upthrust", "applied", "net"),
    _d(m=2, kg=1, s=-2): ("energy", "work", "heat", "kinetic", "potential", "enthalpy", "torque", "moment"),
    _d(m=2, kg=1, s=-2, mol=-1): ("enthalpy", "energy", "change"),
    _d(m=2, kg=1, s=-3): ("power", "rate"),
    _d(m=-1, kg=1, s=-2): ("pressure", "stress"),
    _d(s=-1): ("frequency", "activity", "rate", "angular"),
    _d(s=1, a=1): ("charge",),
    _d(m=2, kg=1, s=-3, a=-1): ("voltage", "potential", "difference", "emf", "electromotive"),
    _d(m=2, kg=1, s=-3, a=-2): ("resistance",),
    _d(m=3): ("volume", "capacity"),
    _d(m=2): ("area", "surface"),
    _d(m=-3, kg=1): ("density",),
    _d(m=-3, mol=1): ("concentration", "molarity"),
    _d(m=1, kg=1, s=-1): ("momentum", "impulse"),
    _d(kg=1, mol=-1): ("molar", "mass"),
    _d(m=2, s=-2, k=-1): ("specific", "heat", "capacity"),
    _d(kg=1, s=-2, a=-1): ("magnetic", "field", "flux", "density"),
    _d(m=2, kg=1, s=-2, k=-1): ("heat", "capacity", "entropy"),
    _d(m=3, kg=-1, s=-2): ("gravitational", "constant"),
}


def dimension_terms(dim: Optional[Dimension]) -> tuple[str, ...]:
    """The words of :data:`_DIMENSION_TERMS` for a dimension (the angle exponent is ignored)."""
    if dim is None:
        return ()
    return _DIMENSION_TERMS.get(tuple(dim.exps), ())


def unit_terms(unit) -> tuple[str, ...]:
    """The names of the atoms of a unit expression as a request writes them ("mm" -> "millimetre", "metre"; "kg" ->
    "kilogram", "gram"; "%" -> "percentage", "percent"; "°C" -> "celsius"), from the first reading of the table."""
    if unit is None or not getattr(unit, "readings", None):
        return ()
    out: list[str] = []
    for atom in unit.readings[0].atoms:
        u = atom.unit
        if u is None:
            continue
        name = u.name
        if name in _UNIT_NAME_TERMS:
            out.extend(_UNIT_NAME_TERMS[name])
            continue
        out.append(name)
        if atom.prefix:
            word = _PREFIX_NAMES.get(atom.prefix, atom.prefix if atom.prefix.isalpha() and len(atom.prefix) > 2 else "")
            if word:
                out.append(word + name)
    return tuple(out)


def _figures(text: str) -> set[Fraction]:
    out: set[Fraction] = set()
    text = _SUPERSCRIPT_RUN_RE.sub(lambda m: " " + m.group(0).translate(_SUPERSCRIPT_DIGITS) + " ", text)
    for m in _FIGURE_RE.finditer(text):
        tok = m.group(0)
        if len(tok) <= 40:
            out.add(Fraction(tok))
    return out


def _weight(value: Fraction) -> int:
    """How much a figure an item and a claim share says about the claim: a single-digit whole number (0, 2, 4) is common
    enough to coincide ("2 + 2 = 4" and "4 m/s in 2 s"), so it counts one; any other figure (20, 4.5, 0.25, 1500) two."""
    return 1 if value.denominator == 1 and abs(value) <= 9 else 2


def _node_figures(nodes) -> set[Fraction]:
    """The figures maths nodes write: their numbers and the exponents of their powers (``2³ × 2⁴`` writes 2, 3 and 4)."""
    out: set[Fraction] = set()
    for root in nodes:
        for n in walk(root):
            if isinstance(n, (Num, Quantity)):
                out.add(n.number.value)
            elif isinstance(n, Pow):
                out.add(Fraction(n.exp))
    return out


def _dimensions(nodes) -> set[Dimension]:
    """The dimensions of the quantities maths nodes write with a known unit."""
    return {n.unit.dim for root in nodes for n in walk(root)
            if isinstance(n, (Quantity, WithUnit)) and n.unit is not None and not n.unit.unknown and n.unit.dim is not None}


def _item_text(item_text: str) -> str:
    """The item without its opening label and the instructions on the form of its answer (:data:`_FORM_RE`)."""
    return _FORM_RE.sub(" ", _ITEM_LEAD_RE.sub(" ", item_text, count=1))


def _symbol_name(m: re.Match) -> str:
    """A matched symbol (letter, subscript digits or ``_{...}``) as the STEM front end names it: S₁₀ and S_{10} are S_10."""
    sub = (m.group(2) or "").translate(_SUBSCRIPT_DIGITS) or (m.group(3) or "")
    return f"{m.group(1)}_{sub}" if sub else m.group(1)


def _item_symbols(item_text: str) -> set[str]:
    """The symbols an item names with a subscript ("Find S₁₀", "Find u₆ and S₅", "the x-component F_x") or right after a
    command word ("Calculate v if ...", "Find x", "Calculate Kc"), normalised as the STEM front end names them (S₁₀ and
    S_{10} are both S_10; Kc is K_c)."""
    out = {_symbol_name(m) for m in _ITEM_SYMBOL_RE.finditer(item_text) if m.group(2) or m.group(3)}
    for m in _ASKED_RE.finditer(item_text):
        if m.group("head"):
            out.add(f"{m.group('head')}_{m.group('low')}")
        else:
            sub = (m.group("digits") or "").translate(_SUBSCRIPT_DIGITS) or (m.group("sub") or "")
            out.add(f"{m.group('letter')}_{sub}" if sub else m.group("letter"))
    return out


#: An item that writes a Boolean expression: a Boolean operator word or sign.
_BOOLEAN_ITEM_RE = re.compile(r"\b(?:NOT|AND|OR|XOR|NAND|NOR)\b|[∧∨¬⊕]")
#: A Boolean letter: a lone capital letter.
_BOOLEAN_LETTER_RE = re.compile(r"(?<![A-Za-z])([A-Z])(?![A-Za-z])")


def _formula_subjects(item_doc: StemDocument) -> set[str]:
    """The symbols an item defines by a formula it gives: the lone symbol on the left of an equation whose right side is
    a formula rather than a value ("Calculate Simpson's index D = 1 − Σn(n − 1)/(N(N − 1))" asks for D; "Use v = u + at"
    for v), never one given a value ("Given R = 12 Ω"). Repair round 2, holdout2 coverage class."""
    out: set[str] = set()
    for it in item_doc.items:
        for chain in it.chains:
            ops = chain.operands
            if len(ops) < 2 or not ops[0].readings or not isinstance(ops[0].readings[0], Sym):
                continue
            head = ops[0].readings[0]
            if head.kind in _SYMBOL_KINDS and any(op.readings and not _plain_value(op.readings[0]) for op in ops[1:]):
                out.add(head.name)
    return out


def _plain_value(node) -> bool:
    """A value as written (a numeral, a quantity, a per cent, a signed one): what an item gives, not a formula."""
    while isinstance(node, Neg):
        node = node.arg
    return isinstance(node, (Num, Quantity, WithUnit, Percent))


def named_quantity_symbols(item_text: str, profile_key: str) -> set[str]:
    """The symbols of the reference quantities (:data:`.reference_data.QUANTITIES`, those of the profile) that an item
    names in words: "Calculate the pH" asks for ``pH``, "Calculate the kinetic energy" for ``E_k`` (and its other booklet
    spellings), so a claim that gives ``pH`` a value is about the item although no word of it is shared (repair round 2,
    holdout2 coverage class: a one-line ``pH = −log₁₀[H⁺] = 2.60`` left "Calculate the pH" unaddressed). Whole words
    only, case folded; bounded by the first 2,000 characters of the item."""
    from .reference_data import QUANTITIES  # the booklet table, read lazily (it is large)
    low = (item_text or "")[:2000].casefold()
    out: set[str] = set()
    for q in QUANTITIES:
        if profile_key not in q.profiles:
            continue
        for name in q.names:
            k = low.find(name.casefold())
            while k >= 0:
                end = k + len(name)
                if (k == 0 or not low[k - 1].isalpha()) and (end >= len(low) or not low[end].isalpha()):
                    out.add(q.symbol)
                    break
                k = low.find(name.casefold(), k + 1)
    return out


def _given_symbols(item_text: str) -> set[str]:
    """The symbols an item gives a value for ("if d = 120 m and t = 8 s", "u₁ = 3")."""
    return {_symbol_name(m) for m in _GIVEN_RE.finditer(item_text)}


def _token_key(tok) -> tuple:
    """A token as the expression comparison reads it: a numeral by its exact value, a symbol by its name and marks, an
    operator by its meaning (× · * are one), anything else by its kind and text."""
    if tok.kind == "NUM":
        value = getattr(tok.value, "value", None)
        return ("NUM", value if value is not None else tok.text)
    if tok.kind == "IDENT":
        return ("IDENT", tok.text, tok.sub, tok.primes, tok.delta)
    if tok.kind == "OP":
        return ("OP", _OP_KEYS.get(tok.text, tok.text))
    if tok.kind == "SUP":
        return ("SUP", tok.value)
    if tok.kind in ("LPAR", "RPAR", "BAR", "CARET", "BANG"):
        return (tok.kind,)
    return (tok.kind, tok.text)


def _expression_runs(text: str) -> list[tuple[tuple, ...]]:
    """The expressions ``text`` writes, as runs of token keys (one linear pass over its tokens): maximal runs of numerals,
    one-letter symbols, operators and brackets that write an operation (a binary operator between two operands, or a
    function, power, bar or factorial of one: ``1/2``, ``2³ × 2⁴``, ``√50``, ``3x + 5``), never a lone figure or a sign
    (``−5``). A word of prose, a relation sign or two operands set apart by a space with no operator end a run."""
    runs: list[tuple[tuple, ...]] = []
    current: list = []

    def close() -> None:
        operands = sum(1 for t in current if t.kind in _RUN_OPERANDS)
        binary = any(t.kind == "OP" for t in current) and operands >= 2
        unary = any(t.kind in ("FUNC", "SUP", "CARET", "BAR", "BANG") for t in current) and operands >= 1
        if (binary or unary) and len(runs) < _MAX_RUNS:
            runs.append(tuple(_token_key(t) for t in current[:_MAX_RUN_TOKENS]))
        current.clear()

    for tok in lex(text).tokens:
        word = tok.kind == "IDENT" and (len(tok.text) > 1 and not tok.sub)
        if tok.kind not in _RUN_KINDS or word:
            close()
            continue
        if current and tok.kind in _RUN_OPERANDS and tok.space and current[-1].kind in _RUN_OPERANDS:
            close()  # '4 m' or 'a 2': two operands set apart, no operation between them
        current.append(tok)
    close()
    return runs


def _writes_expression(claim_text: str, item_runs: list[tuple[tuple, ...]]) -> bool:
    """True when the claim writes one of the item's own expressions token for token (``1/2 = 0.50`` writes the ``1/2`` of
    "Calculate 1/2 exactly"; ``2 + 2 = 4`` writes nothing of "Simplify 2³ × 2⁴")."""
    if not item_runs:
        return False
    for run in _expression_runs(claim_text):
        for wanted in item_runs:
            n = len(wanted)
            if any(run[i:i + n] == wanted for i in range(len(run) - n + 1)):
                return True
    return False


def _polynomial_degree(node) -> Optional[int]:
    """The degree of ``node`` as a polynomial in its symbols (``x²`` 2, ``2x + 3`` 1, ``4`` 0), or None when it is no
    polynomial (a function, root, absolute value or division by a symbol). The parser bounds an expression's depth."""
    if isinstance(node, (Num, Quantity)):
        return 0
    if isinstance(node, Sym):
        return 0 if node.kind == "constant" else 1
    if isinstance(node, Neg):
        return _polynomial_degree(node.arg)
    if isinstance(node, WithUnit):
        return _polynomial_degree(node.arg)
    if isinstance(node, Pow):
        base = _polynomial_degree(node.base)
        return base * node.exp if base is not None and isinstance(node.exp, int) and node.exp >= 0 else None
    if isinstance(node, BinOp):
        left, right = _polynomial_degree(node.left), _polynomial_degree(node.right)
        if left is None or right is None:
            return None
        if node.op in ("+", "-"):
            return max(left, right)
        if node.op == "*":
            return left + right
        if node.op == "/":
            return left if right == 0 else None
    return None


def _equation_degree(left, right) -> Optional[int]:
    """The degree of an equation in its one unknown (``x² = 4`` is 2, ``2x + 3 = 7`` is 1), or None: no symbol or more than
    one, a value merely stated for a symbol (``x = 2``), or a side that is no polynomial."""
    if left is None or right is None:
        return None
    if isinstance(left, Sym) or isinstance(right, Sym):
        return None  # a value stated for a symbol, or a symbol named equal to an expression: no equation to solve
    names = {n.name for side in (left, right) for n in walk(side) if isinstance(n, Sym) and n.kind in _SYMBOL_KINDS}
    if len(names) != 1:
        return None
    degrees = [_polynomial_degree(left), _polynomial_degree(right)]
    if any(d is None for d in degrees):
        return None
    return max(degrees)


def _profile(key: str) -> str:
    return key if key in PROFILES else "stem"


class StemHooks:
    """The STEM branches' :class:`~epinoic_logic.branches.base.BranchHooks` (module docstring)."""

    request_imperatives: tuple[str, ...] = STEM_IMPERATIVES

    @staticmethod
    def _doc(report_text: str, request_text: Optional[str], profile_key: str) -> StemDocument:
        return build_document(report_text, request_text, _profile(profile_key))

    def coverage_terms(self, claim_text: str, report_text: str, request_text: Optional[str], profile_key: str) -> frozenset[str]:
        """Dimension words of the quantities and bound symbols of the statement(s) holding ``claim_text``."""
        try:
            if not claim_text or not report_text:
                return frozenset()
            doc = self._doc(report_text, request_text, profile_key)
            at = report_text.find(claim_text)
            if at < 0:
                return frozenset()
            end = at + len(claim_text)
            sids = [st.id for st in doc.statements if st.start < end and at < st.end]
            terms: list[str] = []
            if any(r.kind in _COMPUTE_KINDS for sid in sids for r in doc.checks_for(sid)):
                terms.extend(_COMPUTE_TERMS)
            for sid in sids:
                for r in doc.relations_for(sid):
                    terms.extend(_KIND_TERMS.get(r.kind, ()))
                    if r.op in _ORDER_OPS or getattr(r, "premise_op", "") in _ORDER_OPS:
                        terms.extend(_INEQUALITY_TERMS)
                    # the kind of equation it states or solves ("quadratic" for x² = 4): what a request calls it
                    for op, left, right in ((r.op, r.left, r.right), (r.premise_op, r.premise_left, r.premise_right)):
                        if op == "=" and left is not None and right is not None:
                            terms.extend(_DEGREE_TERMS.get(_equation_degree(left.node, right.node), ()))
            if _DERIVATIVE_RE.search(claim_text):
                terms.extend(_DERIVATIVE_TERMS)
            if _PERCENT_RE.search(claim_text):
                terms.extend(_PERCENT_TERMS)
            for sid in sids:
                for item in doc.items_for(sid):
                    for chain in item.chains:
                        for op in chain.operands:
                            for reading in op.readings:
                                for node in walk(reading):
                                    terms.extend(self._node_terms(node, doc))
                for pv in doc.prose_values:
                    if pv.statement_id == sid:
                        for node in walk(pv.node):
                            terms.extend(self._node_terms(node, doc))
                if len(terms) > _MAX_TERMS:
                    break
            return frozenset(terms[:_MAX_TERMS])
        except Exception:  # a heuristic aid: on any failure the channel's own reading stands
            return frozenset()

    @staticmethod
    def _node_terms(node: object, doc: StemDocument) -> tuple[str, ...]:
        if isinstance(node, (Quantity, WithUnit)):
            unit = node.unit
            return dimension_terms(unit.dim) + unit_terms(unit) if unit is not None and not unit.unknown else ()
        if isinstance(node, Percent):
            return _PERCENT_TERMS
        if isinstance(node, Abs):
            return _NOTATION_TERMS["abs"]
        if isinstance(node, Func):
            return _NOTATION_TERMS.get(node.name, ())
        if isinstance(node, Sym):
            out: list[str] = []
            for b in doc.bindings.get(node.name, ()):
                if b.unit is not None and not b.unit.unknown:
                    out.extend(dimension_terms(b.unit.dim))
            head, _, sub = node.name.partition("_")
            if head and sub in _COMPONENT_TERMS:
                out.extend(_COMPONENT_TERMS[sub])
            return tuple(out)
        return ()

    def topic_evidence(self, item_text: str, claim_text: str, report_text: str, request_text: Optional[str], profile_key: str,
                       notation_only: bool = False) -> bool:
        """True when the claim holding ``claim_text`` is about the request item ``item_text`` beyond the words they share
        (module docstring): it gives a value to a symbol the item asks for, or it computes with enough of the item's own
        figures (:func:`_weight`: shared figures weighing three, or the item's only figure when that is no single-digit
        whole number) and the units it states name no other quantity than the item names in words. ``notation_only``:
        the item names what it asks for in maths only (:meth:`names_notation`), so the unknowns of its equations count
        as asked symbols and the claim's units are set against no word of it. Never raises (False on any failure)."""
        try:
            if not item_text or not claim_text or not report_text:
                return False
            doc = self._doc(report_text, request_text, profile_key)
            at = report_text.find(claim_text)
            if at < 0:
                return False
            end = at + len(claim_text)
            sids = [st.id for st in doc.statements if st.start < end and at < st.end]
            if not any(doc.checks_for(sid) for sid in sids):
                return False  # only a claim that computes something can be about what an item asks to compute
            item = _item_text(item_text)
            if self._asked_symbols(item, profile_key, notation_only) & self._symbols(doc, sids):
                return True
            # a claim that computes with the item's own expression, token for token: for an item that names what it asks for
            # in notation only, any expression ("Calculate 1/2 exactly" and ``1/2 = 0.50``); for an item that also names a topic
            # in words, only an expression long enough to be the item's own ("Simplify the Boolean expression A.B + A.C" and
            # ``A.B + A.C = A.(B + C)``: five tokens or more), so a short one ("the acceleration of 1/2") leaves its topic words
            # to decide
            runs = _expression_runs(item)
            if _writes_expression(claim_text, runs if notation_only else [r for r in runs if len(r) >= _LONG_EXPRESSION_TOKENS]):
                return True
            if _BOOLEAN_ITEM_RE.search(item) and any(r.kind in ("bool", "tt") for sid in sids for r in doc.checks_for(sid)):
                # a Boolean item ("verify that NOT (A AND B) = (NOT A) OR (NOT B)"): a claim that checks a Boolean relation over
                # the item's own letters is about it (the expression runs above read arithmetic only; repair round 2)
                if set(_BOOLEAN_LETTER_RE.findall(item)) & set(_BOOLEAN_LETTER_RE.findall(claim_text)):
                    return True
            asked = _figures(item) | _node_figures(self._nodes(self._doc(item, None, profile_key)))
            # an item that names nothing in words names no quantity the claim's units could contradict ("Calculate v if
            # d = 120 m and t = 8 s" asks for a speed and writes a length and a time)
            if not asked or not (notation_only or self._names_same_quantity(item, doc, sids)):
                return False
            shared = asked & (_figures(claim_text) | _node_figures(self._nodes(doc, sids)))
            if len(asked) == 1:
                return bool(shared) and _weight(next(iter(asked))) >= 2
            return sum(_weight(v) for v in shared) >= 3
        except Exception:  # a heuristic aid: on any failure the channel's own reading stands
            return False

    def names_notation(self, item_text: str, profile_key: str) -> bool:
        """True when the item writes what it asks for in maths: a figure that is no label, mark or precision instruction,
        or a symbol ("Solve 3x + 5 = 20", "Simplify √50", "Find u₆ and S₅"); False for "Find the final value". The
        channel asks it of an item whose words are all command words: such an item is addressed only by a claim
        :meth:`topic_evidence` finds about its notation. Never raises (False on any failure)."""
        try:
            item = _item_text(item_text or "")
            if not item.strip():
                return False
            item_doc = self._doc(item, None, profile_key)
            return bool(_figures(item) or _item_symbols(item) or self._symbols(item_doc) or _node_figures(self._nodes(item_doc)))
        except Exception:
            return False

    def _asked_symbols(self, item: str, profile_key: str, notation_only: bool) -> set[str]:
        """The symbols an item asks for: a subscripted name ("Find S₁₀"), a symbol right after a command word ("Calculate
        v if ...", "Find the value of k"), the target of a show-that item ("Show that its gradient is m = 1", though it
        states the value) and, for an item that asks to solve an equation or names nothing in words, the unknowns of its
        equations ("Solve 3x + 5 = 20"); never a symbol the item gives a value for ("if d = 120 m and t = 8 s", "Given
        that t = 8 s, show that ..."), which is an input."""
        show = _SHOW_THAT_RE.search(item)
        if show:
            target = item[show.end():]
            return _item_symbols(target) | self._symbols(self._doc(target, None, profile_key))
        item_doc = self._doc(item, None, profile_key)
        formula = _formula_subjects(item_doc)
        asked = _item_symbols(item) | named_quantity_symbols(item, profile_key) | formula
        if notation_only or _SOLVE_RE.search(item):  # the unknowns of the equations it writes
            asked |= self._symbols(item_doc)
        # a symbol the item defines by a formula ("D = 1 − Σ...") is asked, though the given reader sees "D = 1"
        return asked - set(item_doc.bindings) - (_given_symbols(item) - formula)

    def _names_same_quantity(self, item: str, doc: StemDocument, sids: list[str]) -> bool:
        """False when the units the claim states name another quantity than any the item names in words (a word of its
        dimension): a claim computing something else from the same data ("s = ½ × 20 × 4.0 = 40 m" is no answer to "the
        acceleration from 20 m/s in 4.0 s")."""
        stated = _dimensions(self._nodes(doc, sids, prose=False))  # what the claim's maths states (its prose may describe the data)
        terms = {t for dim in stated for t in dimension_terms(dim)}
        return not terms or bool(terms & {w.casefold() for w in re.findall(r"[A-Za-z]+", item)})

    @staticmethod
    def _nodes(doc: StemDocument, sids: Optional[list[str]] = None, prose: bool = True):
        """The maths nodes of a document (or of some of its statements): every reading of every operand and, with
        ``prose``, the values its prose states."""
        items = doc.items if sids is None else [it for sid in sids for it in doc.items_for(sid)]
        for item in items:
            for chain in item.chains:
                for op in chain.operands:
                    yield from op.readings
        if prose:
            for pv in doc.prose_values:
                if sids is None or pv.statement_id in sids:
                    yield pv.node

    @classmethod
    def _symbols(cls, doc: StemDocument, sids: Optional[list[str]] = None) -> set[str]:
        """The symbols the maths of a document (or of some of its statements) writes for quantities."""
        return {n.name for root in cls._nodes(doc, sids) for n in walk(root) if isinstance(n, Sym) and n.kind in _SYMBOL_KINDS}

    def echo_exempt(self, report_text: str, request_text: str, profile_key: str) -> bool:
        """True when the answer holds a planned computation link whose text the request does not contain."""
        try:
            doc = self._doc(report_text, request_text, profile_key)
            ask = " ".join((request_text or "").split())
            for rel in doc.checks:
                if rel.kind not in _ECHO_KINDS:
                    continue
                link = " ".join(report_text[rel.start:rel.end].split())
                if link and link not in ask:
                    return True
            return False
        except Exception:
            return False

    def word_count_view(self, text: str, profile_key: str) -> str:
        """``text`` with each maths span and code block replaced by one word (its newlines kept, so
        paragraphs do not move) and LaTeX control words outside them removed. A line that is nothing but written
        arithmetic (numerals, with thousands grouped by spaces or apostrophes or cut by an ellipsis, operators and '=':
        '21 131.40 − 18 000.00 = 3 131.40') is one maths word too, as the same line with its digits run together is."""
        try:
            doc = self._doc(text, None, profile_key)
            spans = sorted((sp.start, sp.end, sp.kind) for sp in doc.spans.spans if sp.kind in _MATH_KINDS or sp.kind in _CODE_KINDS)
            parts: list[str] = []
            pos = 0
            for a, b, kind in spans:
                if a < pos:
                    continue
                parts.append(_LATEX_WORD_RE.sub(" ", text[pos:a]))
                word = "Xcode" if kind in _CODE_KINDS else "Xmath"
                parts.append(f" {word} " + "\n" * text.count("\n", a, b))
                pos = b
            parts.append(_LATEX_WORD_RE.sub(" ", text[pos:]))
            view = "".join(parts)
            lines, originals = view.split("\n"), text.split("\n")
            if len(lines) == len(originals):
                view = "\n".join(" Xmath " if _WORKING_LINE_RE.match(o) and "=" in o and any(ch.isdigit() for ch in o) else v
                                  for v, o in zip(lines, originals))
            return view
        except Exception:
            return text


#: a line of nothing but written arithmetic: numerals (grouped by spaces or apostrophes, cut by an ellipsis), operators, '='
_WORKING_LINE_RE = re.compile(r"^[ \t]*[0-9][0-9 \t.,'’…+\-−×÷*/·=≈()]{0,400}$")


STEM_HOOKS = StemHooks()
