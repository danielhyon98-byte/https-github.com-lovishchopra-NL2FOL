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
step), ``sol`` (stated roots; also a decimal the answer states in prose for a quantity it named by the
symbol, ``_described_roots``), ``cnv`` (a unit conversion), ``cmp`` (a stated order, or an
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

import re
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Optional

from .boolean import BoolRelation, TruthTable
from .calculus import derivative, polynomial, polynomial_node
from .chem import ELEMENTS, ChemEquation
from .limits import DEFAULT_LIMITS, StemLimits, StemProfile
from .nodes import (
    Abs, Apply, BinOp, BoolOp, Chain, Degrees, Func, Magnification, Neg, Node, Num, Operand, Percent, PlusMinus, Pow, Quantity, Ratio, RealPower, Root,
    Sym, Unsupported, WithUnit, align, is_closed, is_value, render, replace_symbol, shape_key, symbols, unsupported_reasons, value_of, walk,
)
from .numbers import ExactNumber, exact_based, exact_integer, is_ascii_digit, scan_number
from .parser import ParseIssue
from .models import (
    all_symbols, application_of, applications, has_exponential, is_model_expression, model_link_sides, relaxation_fits, render_model, resolve_model,
    substitute,
)
from .scope import Binding, Formula, Model, Scope
from .tolerance import approx_qualifies
from .constants import constants_for_symbol, match_written
from .reference import (
    as_written_reading, booklet_formulas, booklet_laws, coefficient_free_dimension, difference_witness, differs_as_function, dimension_text, fixed_quantity,
    enclose_node, pure_coefficient_dimension, quantities_for, unit_scale, unit_written_once,
)
from .reference_data import (
    ABSOLUTE_TEMPERATURE_LAWS, CHANGE_MARKERS, COMPARISON_PHRASES, DEFINITION_GIVENS_LAWS, EXTRAPOLATION_CAVEATS, GIVENS_LAWS, MEASUREMENT_NOUNS, NOUN_PHRASE_STOPWORDS, OBJECT_ORDINALS, TARGET_BOUNDS,
    TARGET_EXCEED_VERBS, TARGET_MISS_VERBS, TARGET_NOUNS, TARGET_REACH_VERBS, WORKING_COMMANDS, WORKING_CUES,
)
from .units import DIMENSIONLESS, Dimension, UnitAtom, UnitExpr, UnitReading, is_unit_atom, parse_unit

__all__ = [
    "CHECK_KINDS", "FrontEndFinding", "MathItem", "ProseValue", "Relation", "RequestIntent", "RequestReading", "ST_SEVERITY", "ShowThatTarget",
    "dimension_of", "named_quantities", "plan_relations",
]

#: the most readings of one model link: one per combination of the definitions of the letters it applies
MAX_MODEL_READINGS = 4
#: check kinds in the order of section 8.1
CHECK_KINDS = ("eq", "sub", "alg", "sol", "mod", "cnv", "cmp", "res", "giv", "tgt", "chem", "bool", "tt", "base")
#: severity of every front-end code (section 8.2); none is an error
ST_SEVERITY = {
    "ST-PARSE-001": "warning", "ST-PARSE-002": "warning", "ST-UNDEC-001": "warning", "ST-UNDEC-002": "warning", "ST-UNDEF-001": "warning",
    "ST-UNIT-001": "warning", "ST-UNIT-002": "info", "ST-DIM-001": "warning", "ST-DIM-002": "warning", "ST-ALG-001": "warning",
    "ST-CHEM-001": "warning", "ST-CODE-001": "info", "ST-SCOPE-001": "info", "ST-LIM-001": "warning", "ST-LIM-002": "warning",
    "ST-INTERNAL-001": "warning",
    # the named STEM diagnostics of section 24 (each carries its canonical defect label: named.NAMED_CODES)
    "ST-REF-001": "warning", "ST-STEP-002": "info", "ST-RANGE-001": "warning", "ST-WORK-001": "warning", "ST-GIVEN-002": "warning",
    "ST-SCOPE-002": "warning", "ST-REF-002": "warning", "ST-GIVEN-003": "warning", "ST-GIVEN-004": "warning", "ST-STEP-003": "warning",
}
_EQUALITY = frozenset({"=", "≈", "≃", "≡"})
_APPROX = frozenset({"≈", "≃"})
_ORDER = frozenset({"<", ">", "≤", "≥", "≠"})
_STEP_WORDS = ("⇒", "∴", "so", "hence", "therefore", "thus", "gives", "giving", "rearranging", "rearranged", "which gives", "implies", "then",
               "get", "obtain", "yields", "leads to")
_COMPLETE_PHRASES = ("only solution", "only root", "the solution is", "the solutions are", "is the solution", "are the solutions", "the roots are",
                     "solutions are", "roots are", "the only value", "is the only")
_RESTRICT_WORDS = ("reject", "positive", "non-negative", "nonnegative", "x > 0", "x ≥ 0", "> 0", "≥ 0", "length", "time", "only the positive",
                   "cannot be negative", "must be positive", "domain", "≠ 0", "≠0", "non-zero", "nonzero", "not zero")
_RESULT_CUES = ("therefore", "hence", "thus", "so", "the answer is", "the result is")
#: the one-word result cues, and the words that open a phrase stating an input after one ('so, with fixed costs of $40,000')
_RESULT_CUE_WORDS = frozenset({"therefore", "hence", "thus", "so", "answer", "result"})
_INPUT_WORDS = frozenset({"with", "using", "given", "for", "if", "when", "assuming", "taking", "at", "from"})
#: words that name an identity ('Factorising, x² + 5x + 6 = …', 'Expand (a + b)²', 'which simplifies to')
_IDENTITY_CUES = ("factoris", "factoriz", "expand", "expanding", "expansion", "simplif", "identity", "identical")
#: a numeral of binary digits, and one the text names as binary ('the binary number 11010110', '11010110 in binary', '(11010110)')
_BINARY_DIGITS_RE = re.compile(r"[01]{4,32}")
_BINARY_NAMED_RE = re.compile(r"\bbinary\b(?:\s+(?:number|numeral|value|string|integer|representation|pattern|code|form))?(?:\s+(?:of|is|was))?[\s:]{1,3}([01]{4,32})\b"
                              r"|\b([01]{4,32})\s*(?:in\s+binary|\(binary\)|binary\b)", re.IGNORECASE)
#: a 0-and-1 numeral the text calls a two's complement number ("the 8-bit two's complement number 10110110", "10110110 in two's
#: complement"): its value is signed, the leading digit weighing −2ⁿ⁻¹ (repair round 2, holdout2 CS class)
_TWOS_NAMED_RE = re.compile(r"\btwo['’]?s[\s-]+complement\b(?:\s+(?:binary\s+)?(?:number|numeral|value|integer|representation|pattern|form))?"
                            r"(?:\s+(?:of|is|was))?[\s:]{1,3}([01]{4,32})\b|\b([01]{4,32})\s+(?:[a-z]{2,12}\s+){0,2}?(?:in|as)\s+(?:(?:an?\s+)?\d{1,2}-bit\s+)?"
                            r"two['’]?s[\s-]+complement\b",
                            re.IGNORECASE)
#: a request that asks for the solutions of an equation ("Solve x² = 8", "Find all values of x", "find the roots")
_SOLVE_REQUEST_RE = re.compile(r"\b(?:solve|find\s+all|find\s+the\s+(?:values|solutions|roots)|find\s+every)\b")
#: a root the statement itself calls one of several ('x = 3 is one solution'): the statement claims no full set
_PARTIAL_ROOT_PHRASES = ("is a solution", "is one solution", "is a root", "is one root", "one solution is", "one root is", "a solution is",
                         "a root is", "one of the solutions", "one of the roots", "another solution", "another root", "is also a solution",
                         "is also a root")
#: a stated root set continued by bare values after its first member ('x = 0, 2 or −2', 'x = 2 or 3'): the separator before a
#: further member, and what may follow one (the end of the statement, punctuation, or the next separator)
_MEMBER_SEP_RE = re.compile(r",[ \t]*(?:(?:or|and)[ \t]+)?|[ \t]+(?:or|and)[ \t]+")
_MEMBER_END_RE = re.compile(r"[ \t]*(?:$|[,.;:!?)\]]|(?:or|and)\b)")
#: a step cue right before a chain ('so', 'giving', 'hence', '⇒')
_STEP_CUE_RE = re.compile(r"(?:\b(?:so|giving|gives|hence|thus|therefore|then)\b|⇒|∴)\W*$", re.IGNORECASE)
#: words after a comparison that say it does not hold ("the final test (2 <= 1) fails", "2 <= 1 no, so the loop ends", "2 <= 1,
#: which is false")
_FAILS_RE = re.compile(r"[ \t)\]]{0,4}(?:,[ \t]{0,3}(?:which|that|and\s+this|so\s+this|this)[ \t]+)?(?:fails\b|failed\b|is\s+false\b|evaluates\s+to\s+false\b|"
                       r"gives\s+false\b|returns\s+false\b|is\s+not\s+true\b|does\s+not\s+hold\b|doesn't\s+hold\b|(?:no|false)[ \t]*(?:[,;.)|]|$))",
                       re.IGNORECASE)
#: named scales a value may be written in ("a fall of 0.1 pH unit"): such a value restates only a value in the same scale
_SCALE_NAMES = frozenset({"pH", "pOH", "pKa", "pKb", "pKw"})
#: a trace step that gives a variable a value in prose ("so low moves to 2", "high becomes 4", "i is set to 3")
_ASSIGN_STEP_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_]{0,30})\s+(?:moves\s+to|becomes|is\s+set\s+to|is\s+updated\s+to|changes\s+to)\s*$")
#: a sentence stated under a condition on a variable ("For 0 < t < 2, both factors are positive, so v > 0.", "If x > 3,
#: ...", "When t ≥ 2, ..."): its order relations bound the variable or state a property under the bound
_CONDITIONAL_RE = re.compile(r"^\W*(?:for|if|when|whenever|while|where|wherever|provided|suppose|supposing|assuming|unless|as\s+long\s+as)\b", re.IGNORECASE)
_RESULT_VERBS = frozenset({"is", "are", "was", "were", "equals", "equal", "=", "≈", "gives", "becomes", "carries", "delivers", "has", "of", "reaches",
                           "comes", "be", "makes", "totals", "needs", "need", "requires"})
#: participles after which 'at' or 'as' introduces the result, not a condition
_RESULT_PARTICIPLES = frozenset({"estimated", "calculated", "computed", "determined", "evaluated", "found", "out"})
_QUALIFIERS = frozenset({"about", "approximately", "roughly", "around", "nearly", "almost", "≈", "~", "only", "exactly", "just"})
_PREPOSITIONS = frozenset({"at", "in", "for", "with", "by", "from", "after", "before", "per", "to", "on", "into", "over", "under", "within", "than", "below",
                           "above"})
#: a symbol the answer names by a description, in a statement of its own text: 'Let $M$ be the monthly payment in euros',
#: 'let x be the width of the garden', 'where $Q$ is the useful energy', 'with $k$ the spring constant', '$n$ is the number
#: of years' (one letter, in inline maths or not; the verb its lead word allows; a determiner; then words only: the
#: description stops at the first figure, sign or bracket)
_SYMBOL_PART = r"(?:\$|\\\()?[ \t]*(?P<sym>[A-Za-z])[ \t]*(?:\$|\\\))?"
_DESCRIPTION_PART = r"(?P<det>(?i:the|a|an))\s+(?P<desc>[^\W\d_](?:[^\W\d_]|['\- ]){0,79})"
_DEFINITION_RES = (
    re.compile(r"(?:^|(?<=[\s(]))(?i:let|letting)\s+" + _SYMBOL_PART + r"\s+(?i:be|denote|represent|stand\s+for)\s+" + _DESCRIPTION_PART),
    re.compile(r"(?:^|(?<=[\s(,]))(?i:where|with)\s+" + _SYMBOL_PART + r"\s+(?:(?:(?i:is|denotes|represents|stands\s+for)|=)\s+)?" + _DESCRIPTION_PART),
    re.compile(r"^[ \t]*" + _SYMBOL_PART + r"\s+(?i:is|denotes|represents|stands\s+for)\s+" + _DESCRIPTION_PART),
)
#: the characters of a statement a definition is looked for in (bounded work per statement)
_DEFINITION_WINDOW = 2000
#: where a description stops: a relative clause or a conjunction ('the useful energy that vaporises the water')
_DESCRIPTION_STOP_RE = re.compile(r"\s+(?:which|that|who|whose|where|when|whenever|while|and|or|but|so|because|if|as|then|thus|hence|therefore)\b.*$",
                                  re.IGNORECASE | re.DOTALL)
#: a trailing unit of a description ('the monthly payment in euros' also names 'the monthly payment')
_DESCRIPTION_UNIT_RE = re.compile(r"\s+in\s+[^\W\d_]{1,16}$")
#: the clause before a value that states it for a described quantity: an optional connective, a determiner or possessive,
#: the description, a verb of identity, an optional currency sign; nothing else (no qualifier, negation or condition)
_DESCRIBED_VALUE_RE = re.compile(r"^\s*(?:(?:so|thus|hence|therefore|and|then)\s*,?\s+)?(?:(?:the|her|his|their|its|our|your|my|this|that|each|a|an)\s+)?"
                                 r"(?P<desc>[^\W\d_](?:[^\W\d_]|['\- ]){0,79}?)\s+(?:is|was|=|equals|will\s+be|would\s+be|comes\s+to)\s*(?:[€$£¥])?\s*$",
                                 re.IGNORECASE)
#: the words that may name what a described value counts, right after it ('is 352.19 euros', 'is 7 years'): currencies, units
#: of time and count nouns; any other word after the value ('more', 'times', 'when') leaves it unread
_COUNT_WORDS = ("euros|euro|eur|dollars|dollar|usd|pounds|pound|gbp|yen|cents|cent|pence|seconds|second|minutes|minute|hours|hour|days|day|weeks|week|"
                "months|month|years|year|people|persons|students|items|units|tickets|marks|points|cells|individuals")
#: what may follow such a value up to the end of its sentence: one of those words, a rounding note, a mark annotation
_DESCRIBED_TAIL_RE = re.compile(r"^\s*(?:(?:" + _COUNT_WORDS + r")(?![^\W\d_]))?\s*"
                                r"(?:\(?(?:to\s+)?(?:\d{1,2}\s*(?:d\.?\s*p\.?|s\.?\s*f\.?|decimal\s+places?|significant\s+figures?)"
                                r"|the\s+nearest\s+[^\W\d_]{1,12})\)?)?\s*(?:\(?[MARN]\d{1,2}\)?\s*)?(?:[.!;]|$)", re.IGNORECASE)
#: the end of the sentence after a value: a full stop before a capital or at the end (not the stops of 'd.p.' or 's.f.'),
#: or another clause or sentence mark
_SENTENCE_STOP_RE = re.compile(r"\.(?=\s+[A-Z(]|\s*$)|[;!?\n]")
#: an operation the answer states for a solving step (ST-STEP-001): bounded alternatives over at most 240 characters of prose
_OPERAND = r"(?P<k>[^\s,;:.][^,;:.]{0,23}?)"
_OPERATION_RES = (
    ("add", re.compile(r"\b(?:add|adding|added|adds)\s+" + _OPERAND + r"\s+(?:on\s+)?to\s+(?:both|each)\s+sides?\b", re.IGNORECASE)),
    ("sub", re.compile(r"\b(?:subtract|subtracting|subtracted|subtracts|take|taking|takes)\s+" + _OPERAND + r"\s+(?:away\s+)?from\s+(?:both|each)\s+sides?\b",
                       re.IGNORECASE)),
    ("mul", re.compile(r"\b(?:multiply|multiplying|multiplied|multiplies)\s+(?:both\s+sides\s+|each\s+side\s+|through\s+)?by\s+" + _OPERAND
                       + r"(?=\s*(?:[,;:]|$)|\s+(?:gives|giving|yields|we|to|so|then|leads|and)\b)", re.IGNORECASE)),
    # cancelling a common factor divides both sides by it ("Cancelling x, x = 5": repair round 3, stem-soundness-11 variant)
    ("div", re.compile(r"\b(?:(?:divide|dividing|divided|divides)\s+(?:both\s+sides\s+|each\s+side\s+|through\s+)?by"
                       r"|(?:cancel|cancels|cancelling|canceling|cancelled|canceled)(?:\s+(?:the|a|common|factor|factors|of))*)\s+" + _OPERAND
                       + r"(?=\s*(?:[,;:]|$)|\s+(?:gives|giving|yields|we|to|so|then|leads|and|from|on|out)\b)", re.IGNORECASE)),
    ("sq", re.compile(r"\b(?:square|squaring|squared|squares)\s+both\s+sides\b", re.IGNORECASE)),
)
#: a stated guard that a divisor is not zero (ST-STEP-002 stays silent)
_NONZERO_CUES = ("≠ 0", "≠0", "!= 0", "not zero", "non-zero", "nonzero", "not equal to zero", "not equal to 0", "> 0", "≥ 0", "positive")


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
    #: the other statements the item covers: every row of a table (each row is a statement of its own)
    cover_ids: tuple[str, ...] = ()

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
    with the statement prose before it (for the result cue) and after it (what qualifies it)."""

    statement_id: str
    statement_index: int
    part: str
    node: Node
    start: int
    end: int
    before: str
    after: str = ""


@dataclass(frozen=True)
class ShowThatTarget:
    node: Node
    approx: bool
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class RequestIntent:
    """What one statement of the request says about the precision of the answer: ``exact`` ("Calculate 1/2 exactly, without
    rounding.") or ``rounded`` ("to 2 decimal places", "correct to 3 s.f."; it wins when a statement says both), with the
    phrase and the part label in force (empty when the request has none)."""

    part: str
    kind: str
    phrase: str


@dataclass(frozen=True)
class RequestReading:
    """What the request states: bindings, quantities (prose and math), relations, show-that targets and precision intents."""

    bindings: tuple[Binding, ...] = ()
    quantities: tuple[tuple[Node, int, int], ...] = ()
    relations: tuple[tuple[Operand, str, Operand], ...] = ()
    targets: tuple[ShowThatTarget, ...] = ()
    text: str = ""
    restricts_domain: bool = False
    intents: tuple[RequestIntent, ...] = ()
    #: data series the request gives: (unit as written, the values) for three or more values of one unit in one statement
    series: tuple[tuple[str, tuple[Fraction, ...]], ...] = ()
    #: the years the request's data name (four-digit integers from 1000 to 2999 written as years in its prose), in order
    years: tuple[Fraction, ...] = ()
    #: every value the request's prose states, with or without a unit (per cents and bare numbers too), and its offsets
    values: tuple[tuple[Node, int, int], ...] = ()


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
    #: an ``alg`` identity read from the relation's shape alone (a factorised form against an expanded one), which no word of
    #: the answer or the request names: its failure is a warning (repair round 4, rerun-stem-soundness-12)
    inferred: bool = False
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
    #: symbols that stand for a power of e (``e^(−k)`` for ``e^(−8k)``): positive, a side condition the checks stage adds
    positive: tuple[str, ...] = ()
    #: ``sol``: the root is a value the answer states in prose for the quantity it named by the symbol (a prose value,
    #: approximate by nature: the checks stage compares it within the '=' band, τ = 1/100 beyond its half-width)
    described: bool = False
    #: a ``unit`` companion (ST-UNIT-003): the index of the check it accompanies, and its case: ``written`` (the written units
    #: contradict the as-written reading) or ``traced`` (bare numbers repeat the numbers of bindings in non-SI units)
    companion_of: int = -1
    unit_case: str = ""
    #: for a ``traced`` companion: (start, end, the binding whose number the bare numeral repeats) per numeral
    traced: tuple[tuple[int, int, Binding], ...] = ()
    #: for a ``traced`` companion of a bare stated value: the unit the answer's prose gives that value ("= 2000. The energy
    #: stored is 2000 J": J), read with the stated numeral
    stated_unit: Optional[UnitExpr] = None
    #: why the as-written reading is not admissible beside the SI reading (a ``unit`` companion, and the check it accompanies)
    unit_reason: str = ""
    #: an ``op`` check (ST-STEP-001): the operation the answer states for the step (``add``, ``sub``, ``mul``, ``div``, ``sq``),
    #: its operand (None for squaring) and the phrase as written
    operation: str = ""
    operation_arg: Optional[Node] = None
    operation_text: str = ""
    #: a ``sys`` check: the equations of the system and the values the answer states for its unknowns
    equation_set: tuple[tuple[Operand, str, Operand], ...] = ()
    #: a ``cmp`` check the answer says fails ("the final test (2 <= 1) fails", "2 <= 1 no, so the loop ends"): the check is
    #: that the comparison does not hold
    negated: bool = False
    values: tuple[tuple[str, Node], ...] = ()
    #: the span of a repeated head symbol that stands between the two sides of the link (a computation continued by its head on
    #: the next line: 'v = 8.4 / 2.0', then 'v = 5.2 m/s'); the checks stage reads the gap between the sides without it
    head_gap: tuple[int, int] = ()

    @property
    def is_check(self) -> bool:
        return self.outcome == "check"


# ----------------------------------------------------------------------------------------- dimensions


def dimension_of(node: Node, scope: Scope, notes: Optional[list[tuple[Node, Dimension, Dimension]]] = None, *,
                 coefficients: bool = False, substitutions: bool = False) -> Optional[Dimension]:
    """The dimension of ``node`` when every part of it is known (units read unambiguously, bound
    symbols with one dimension, exact fractions and π dimensionless); None when unknown. A sum of
    two known, different dimensions is recorded in ``notes`` (ST-DIM-002) and yields None.

    With ``coefficients`` (a symbolic side such as ``½mv²`` or ``2as``, where a written integer is
    a pure coefficient), an exact integer is dimensionless too. A bare number on a numeric side
    stays "unitless as written" (unknown), so ``120 / 8 = 15 m s⁻¹`` is never a dimension finding.

    With ``substitutions`` a symbol bound nowhere is read from the values the answer substituted for it when every one carries
    a unit (the request's unit for a numeral the request states: 'radius 3.0 m' for r; repair round 4, ADV4-11)."""
    return _dim(node, scope, notes, 0, coefficients, substitutions)


def _dim(node: Node, scope: Scope, notes: Optional[list], depth: int, coefficients: bool = False, substitutions: bool = False) -> Optional[Dimension]:
    if depth > 64:
        return None
    rec = lambda n: _dim(n, scope, notes, depth + 1, coefficients, substitutions)  # noqa: E731
    if isinstance(node, Quantity):
        return node.unit.dim if not node.unit.unknown else None
    if isinstance(node, WithUnit):
        return node.unit.dim if not node.unit.unknown else None
    if isinstance(node, Num):
        n = node.number
        if n.vulgar or (coefficients and n.exact and not n.has_point and not n.scientific and not n.based):
            return DIMENSIONLESS
        if coefficients and not n.based and n.base == 10 and not _booklet_literal(n):
            return DIMENSIONLESS  # a written coefficient whatever its spelling (0.5 × m × v, like ½mv); a written constant (9.81) is not one
        return None
    if isinstance(node, Sym):
        if node.kind == "constant":
            return DIMENSIONLESS
        dims = set()
        readings = scope.bindings_for(node.name) or (tuple(scope.substitutions.get(node.name, ())) if substitutions else ())
        for b in readings:
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


def _booklet_literal(n: ExactNumber) -> bool:
    """A written numeral that matches a data-booklet constant at its precision (``9.81``, ``6.63 × 10⁻³⁴``): it may carry the
    constant's unit, so it is no pure coefficient."""
    if n.value == 0:
        return False
    try:
        return match_written(n.value, n.half_width, n.sig_figs, None, unit_given=False) is not None
    except Exception:  # the match only refines a dimension reading; a literal it cannot match is a coefficient
        return False


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


#: A numeral of the request's prose for the trend reading of ST-RANGE-001 ('giving 6.0, 10.0 and 14.0 units'): digits with an
#: optional decimal part, not inside a word or a longer numeral.
_REQUEST_NUMERAL_RE = re.compile(r"(?<![\w.,])\d{1,9}(?:\.\d{1,9})?(?![\w]|[.,]\d)")


def _request_numerals(text: str) -> frozenset[Fraction]:
    """The values of the numerals the request writes (its first 4,000 characters), years and counts included: a statement whose
    arithmetic repeats one of them works from the request's data."""
    out = set()
    for m in _REQUEST_NUMERAL_RE.finditer((text or "")[:4000]):
        try:
            out.add(abs(Fraction(m.group(0))))
        except (ValueError, ZeroDivisionError):
            continue
    return frozenset(out)


def _unsupported_syms(node: Node) -> set[str]:
    """The symbols inside the parts of ``node`` the encodings do not read (the exponent of a symbolic power: 'T' of
    '2^(T/10)'), which :func:`walk` does not enter; bounded by the node count."""
    out: set[str] = set()
    stack = [node]
    seen = 0
    while stack and seen < 4096:
        seen += 1
        cur = stack.pop()
        for n in walk(cur):
            if isinstance(n, Sym):
                out.add(n.name)
            if isinstance(n, Unsupported):
                stack.extend(x for x in (getattr(n, "arg", None), getattr(n, "base", None)) if isinstance(x, Node))
    return out


#: The wrapper of a binding that reads a temperature written on an offset scale (°C, °F) in kelvin (repair round 4, ADV4-01):
#: its number is the value converted, and :func:`.checks._with_units` writes the numeral of the working with that number.
KELVIN_READING = "kelvin"
#: Subscripts a symbol may carry over its base letter ("T₁", "V_2", "p2", "Tᵢ").
_SUBSCRIPT_TAIL_RE = re.compile(r"(?:_\w+|[₀-₉ₐ-ₜᵢⱼ]+|\d+)$")


def is_affine_unit_expr(unit: Optional[UnitExpr]) -> bool:
    """A temperature on an offset scale: a unit expression that is exactly °C or °F (:func:`.to_ir.is_affine_unit`)."""
    return unit is not None and not unit.unknown and any(r.affine is not None for r in unit.readings)


_KELVIN = parse_unit("K")
_TEMPERATURE_DIM = _KELVIN.dim if _KELVIN is not None else None


def _kelvin_binding(bd: Binding, node: Node) -> Optional[Binding]:
    """``bd`` (a temperature written in °C or °F) as the same temperature in kelvin, its number the converted value with the
    written numeral's half-width (the offset is exact), wrapped :data:`KELVIN_READING`; None when the unit has no single
    offset reading."""
    if _KELVIN is None or not isinstance(node, Num) or len(bd.unit.readings) != 1 or bd.unit.readings[0].affine is None:
        return None
    factor, offset = bd.unit.readings[0].affine
    kv = (node.number.value + offset) * factor
    text = f"{float(kv):.6g}"
    number = replace(node.number, text=text, value=kv)
    return Binding(bd.symbol, kv, number, _KELVIN, bd.source, bd.statement_id, bd.start, bd.end, bd.order, wrapper=KELVIN_READING)


def base_symbol(name: str) -> str:
    """The base letter of a symbol, its subscript set aside ("T₁" -> "T", "V_2" -> "V"; "ΔG" stays "ΔG")."""
    base = _SUBSCRIPT_TAIL_RE.sub("", name or "")
    return base or name


def applies_absolute_temperature_law(names: set[str]) -> bool:
    """Whether a law of the working whose symbols are ``names`` is one in which the temperature is absolute
    (:data:`.reference_data.ABSOLUTE_TEMPERATURE_LAWS`): its base symbols are among one row's and include T."""
    bases = {base_symbol(n) for n in names}
    return "T" in bases and any(bases <= row for row in ABSOLUTE_TEMPERATURE_LAWS)


#: integer powers written as superscripts, for the text of a unit worked from the request's quantities
_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def _first(op: Optional[Operand]) -> Optional[Node]:
    return op.readings[0] if op is not None and op.readings else None


#: The most digits a miscopied value may have (a value of more is compared digit by digit up to here only).
_MAX_MISCOPY_DIGITS = 12


def _miscopy_digits(text: str) -> str:
    """The significant digits of a numeral as written ('8.55' -> '855', '0.020' -> '20', '2.5 × 10³' -> '25'): its mantissa
    without sign, point, grouping or leading zeros."""
    mantissa = text.replace("\u2212", "-").split("×")[0].split("x10")[0].split("e")[0].split("E")[0]
    return "".join(ch for ch in mantissa if ch.isdigit()).lstrip("0")[:_MAX_MISCOPY_DIGITS + 1]


def _miscopied(value_text: str, quantity_text: str, value: Optional[Fraction] = None, quantity: Optional[Fraction] = None) -> bool:
    """Whether a value differs from a request quantity as a miscopy of it does (accuracy round 2, V1-STEM-GIV-FA): the same
    number of significant digits, and the same digits in another order ('8.55' for 5.85) or one digit changed ('15' for 10,
    '30' for 20), and, when both values are given, the same sign and a size within a factor of ten of it. A value of another
    size ('340' for 20, '100' for 25, '3.0 × 10⁸' for 20) is the answer's own value, often one the subject supplies. Linear in
    the digits."""
    a, b = _miscopy_digits(value_text), _miscopy_digits(quantity_text)
    if not a or not b or len(a) != len(b) or len(a) > _MAX_MISCOPY_DIGITS or a == b:
        return False
    if value is not None and quantity is not None:
        if not value or not quantity or (value < 0) != (quantity < 0) or not Fraction(1, 10) < abs(value / quantity) < 10:
            return False
    return sorted(a) == sorted(b) or sum(1 for x, y in zip(a, b) if x != y) == 1


def _restates_unrounded(rounding: dict, node: Node) -> bool:
    """Whether ``node`` states the value a rounding rounded (its ``u``), alike (both with the same unit, or both bare; a per
    cent with a per cent): a comparison of that value with a bound is made before the rounding, whatever the bound equals
    (accuracy round 2, V1I-04: '30.4 m s⁻¹, which rounds to 30 m s⁻¹; but 30.4 m s⁻¹ exceeds 30 m s⁻¹' compares the speed
    itself with the limit)."""
    u, v = value_of(_first(rounding.get("u"))), value_of(node)
    if u is None or v is None or u[0] != v[0] or u[3] != v[3] or (u[2] is None) != (v[2] is None):
        return False
    return u[2] is None or " ".join(u[2].text.split()) == " ".join(v[2].text.split())


def _is_lone(node: Optional[Node]) -> bool:
    return isinstance(node, (Sym, Apply)) and not (isinstance(node, Sym) and node.kind in ("constant", "bond", "continuation"))


def _syms(node: Optional[Node]) -> set[str]:
    return set(symbols(node)) if node is not None else set()


def _substitute_bits(node: Node, values: dict[str, int]) -> Node:
    """``node`` (a Boolean expression) with each letter of ``values`` replaced by its 0/1 numeral at the letter's place."""
    if isinstance(node, Sym) and node.name in values:
        return Num(exact_integer(values[node.name]), node.start, node.end)
    if isinstance(node, BoolOp):
        return replace(node, args=tuple(_substitute_bits(a, values) for a in node.args))
    return node


def _has_func_of(node: Node, unknown: set[str]) -> bool:
    for n in walk(node):
        if isinstance(n, (Func, Root)) and _syms(n.arg) & unknown:
            if isinstance(n, Root):
                continue  # a square root of an unknown is algebra (encoded with an auxiliary), not a function of an unknown
            return True
    return False


def _exact_degree(node: Node, x: str) -> Optional[int]:
    """The exact degree of a polynomial ``node`` in ``x`` (a sum takes the larger degree, which a cancellation could lower:
    read as written), or None when it is no polynomial in ``x`` (a division by it, a root or a function of it)."""
    if x not in _syms(node):
        return 0
    if isinstance(node, Sym):
        return 1 if node.name == x else 0
    if isinstance(node, Neg):
        return _exact_degree(node.arg, x)
    if isinstance(node, BinOp):
        a, b = _exact_degree(node.left, x), _exact_degree(node.right, x)
        if a is None or b is None:
            return None
        if node.op in "+-":
            return max(a, b)
        if node.op == "*":
            return a + b
        return a if node.op == "/" and b == 0 else None
    if isinstance(node, Pow):
        d = _exact_degree(node.base, x)
        return None if d is None or node.exp < 0 else d * node.exp
    return None


def _factorised(node: Node, names: set[str]) -> bool:
    """Whether ``node`` holds a factorised form of the unknowns: a product whose factors both hold an unknown and one of which
    is a sum, or a power (two or more) of a sum that holds an unknown."""
    for n in walk(node):
        if isinstance(n, BinOp) and n.op == "*" and _syms(n.left) & names and _syms(n.right) & names and (
                (isinstance(n.left, BinOp) and n.left.op in "+-") or (isinstance(n.right, BinOp) and n.right.op in "+-")):
            return True
        if isinstance(n, Pow) and n.exp >= 2 and isinstance(n.base, BinOp) and n.base.op in "+-" and _syms(n.base) & names:
            return True
    return False


def _identity_shape(lnode: Node, rnode: Node, names: set[str]) -> bool:
    """A relation that states an identity by its shape: one side factorised and the other not (:func:`_factorised`), and
    the same exact degree in every unknown on both sides (:func:`_exact_degree`): '(a − b)² = a² − b²', 'x² − 9 = (x −
    3)(x − 3)'. An equation to solve ('2x + 3 = x + 7', '(x + 1)² = x + 5') has no such shape."""
    if _factorised(lnode, names) == _factorised(rnode, names):
        return False
    for x in names:
        a, b = _exact_degree(lnode, x), _exact_degree(rnode, x)
        if a is None or b is None or a != b or a < 1:
            return False
    return True


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
    """The prose before a chain qualifies it as approximate (whole words that qualify this chain, :func:`approx_qualifies`)."""
    return approx_qualifies(text)


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
                 limits: StemLimits, statement_order: dict[str, int], code_items: list[tuple[str, int, int, str]], request_mode: bool,
                 definitions: Optional[list[tuple[int, str, str, frozenset[str], str]]] = None, reading: str = "") -> None:
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
        #: every chain of the answer in order: (statement order, part, the final-value entry or None)
        #: (statement order, part, final-value entry or None, offset where the chain's last operand ends)
        self.chain_ends: list[tuple[int, str, Optional[dict], int]] = []
        self.equations: list[dict] = []
        #: the final stated value of the chain each operand stands in (by the operand's identity): a law's chain result
        self.final_of_operand: dict[int, dict] = {}
        #: the points the answer evaluates at ('At t = 12 min,'): they bind nothing, and are the inputs ST-RANGE-001 reads
        self.conditions: list[Binding] = []
        #: the reference checks of section 24 run (off while the closed table of booklet laws is itself read)
        self.reference_checks = True
        self.unit_reported: set[tuple[str, str]] = set()
        self.request_relations: list[tuple[Operand, str, Operand]] = []
        self._root_groups: dict[tuple[str, str], int] = {}
        #: the last root line of each (unknown, equation): (statement order, the sol relation's index)
        self._root_lines: dict[tuple[str, tuple[str, ...]], tuple[int, int]] = {}
        #: the sol relations whose stated set goes on with a value this reading does not take (their full set is never claimed)
        self._unread_root_sets: set[int] = set()
        #: the extents of stated roots that bare listed members follow ('x = 0' in 'x = 0, 2 or −2'): a step to such a root
        #: concludes the stated set, not the one value
        self._listed_root_extents: set[tuple[int, int]] = set()
        #: chains that end in a rounding ('… = 0.246 s ≈ 0.25 s'): the value before the ≈ and the rounded value (ST-ROUND-001)
        self.roundings: list[dict] = []
        #: the arithmetic links by the span of their bare stated value (their index in ``relations``), and how many relations
        #: the index has read: kept as the relations grow, so each relation is read once (:meth:`_derived_binding`)
        self._eq_by_stated: dict[tuple[int, int], int] = {}
        self._eq_indexed = 0
        #: the whole answer, lower-cased (for the extrapolation caveats), and as written (for the word after a prose value);
        #: set by plan_relations
        self.answer_lower = ""
        self.answer_text = ""
        #: Boolean names the answer defines ('M = (A ∧ B) ∨ …'): name -> (expression, statement id)
        self.bool_defs: dict[str, tuple[Node, str]] = {}
        self._seen_findings: set[tuple] = set()
        self._request_lower = request.text[:4000].lower()
        #: the part each statement with maths stands in
        self.part_of: dict[str, str] = {it.statement_id: it.part for it in items}
        #: symbols the answer names by a description (:func:`named_quantities`): (statement order, part, symbol, description
        #: variants, statement id)
        self.named: list[tuple[int, str, str, frozenset[str], str]] = list(definitions or ())
        #: the reading view the items come from (offsets are absolute in it): a model's application is a letter glued to its bracket
        self.reading = reading
        #: the arguments of every glued application of a one-letter symbol in this text, by letter (a model's variable is read from them)
        self.app_args: dict[str, list[Node]] = {}
        #: the head nodes that define a model (``C(t) = …``): the definition itself is no check
        self.model_heads: set[int] = set()
        #: the models a link being read applies, with their variables (filled by ``_expand_model``)
        self._applied: list[tuple[Model, str]] = []
        #: the readable definitions of each letter the link being read applies, and the one each reading takes
        self._candidates: dict[str, list[tuple[Model, str, Node]]] = {}
        self._choice: dict[str, int] = {}

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
        if self.reading:
            for item in self.items:
                for ch in item.chains:
                    for op in ch.operands:
                        if op.readings:
                            for letter, arg in applications(op.readings[0], self.reading):
                                self.app_args.setdefault(letter, []).append(arg)
                    letter = self._function_definition(ch)
                    if letter:
                        self.scope.functions.add(letter)
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
            self._root_set_members()
            self._defined_columns()
            self._results()
            self._described_roots()
            self._assignments()
            self._givens()
            self._targets()
            self._reference_formulas()
            self._systems()
            self._rounding_comparisons()
            self._extrapolation()
            self._working()
            self._rebindings()
            self._unlabelled_rebindings()
            self._probabilities()
            self._overdetermined_givens()
            self._set_counts()
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
        head_gap: tuple[int, int] = ()
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
        elif self._repeats_head(item, chain):
            # 'v = 8.4 / 2.0', then 'v = 5.2 m/s': the value of the computation the previous chain left unevaluated, as '= 5.2 m/s'
            # on the next line states it
            prev = self.prev_chain
            head_gap = (chain.operands[0].start, chain.operands[0].end)
            operands = [prev.operands[-1]] + operands[1:]
            base_pos = len(prev.ops)
            continued = True
            full_operands = prev.operands + operands[1:]
            full_ops = prev.ops + ops
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
        self._record_model(full_operands, full_ops)
        approx_ctx = _approx_context(item.gap_before)
        first_rel, first_finding = len(self.relations), len(self.findings)
        for k in range(len(ops)):
            left, lsid = operands[k]
            right, rsid = operands[k + 1]
            pos = base_pos + k
            self._link(item, left, lsid, ops[k], right, rsid, pos, lone and pos == 0, lone_head if lone else None, approx_ctx, full_operands, full_ops,
                       head_gap=head_gap if k == 0 else ())
        if not self.request_mode and full_ops and all(o in _EQUALITY for o in full_ops):
            self._chain_dimension(full_operands, lone, first_rel, first_finding)
        if full_ops and not continued:
            self._sequence(item, chain, full_operands, full_ops, lone, lone_head, bound_before)
        self.prev_chain = _ChainState(full_operands, full_ops, item, chain.start)
        # remember the final value of the chain (for restatements and show-that targets)
        last = _first(full_operands[-1][0]) if full_operands else None
        entry: Optional[dict] = None
        if last is not None and is_value(last) and full_ops and full_ops[-1] in _EQUALITY:
            entry = {"node": last, "operand": full_operands[-1][0], "sid": full_operands[-1][1], "part": item.part,
                     "order": self.order.get(full_operands[-1][1], 0), "symbol": lone_head.name if isinstance(lone_head, Sym) else "",
                     # a computation: more than one link, or a first side that is no lone symbol ('mid = 4' only states a value)
                     "computed": len(full_ops) > 1 or not (lone and isinstance(lone_head, Sym))}
            self.final_values.append(entry)
        if full_operands:
            self.chain_ends.append((self.order.get(full_operands[-1][1], 0), item.part, entry, full_operands[-1][0].end))
            if entry is not None:
                for op, _sid in full_operands:
                    self.final_of_operand[id(op)] = entry
        if not self.request_mode and len(full_operands) >= 2 and full_ops and full_ops[-1] in _APPROX:
            u_op, r_op = full_operands[-2][0], full_operands[-1][0]
            un, rn = _first(u_op), _first(r_op)
            if un is not None and rn is not None and is_closed(un) and is_value(rn):
                self.roundings.append({"u": u_op, "r": r_op, "sid": full_operands[-1][1], "part": item.part, "order": self.order.get(full_operands[-1][1], 0),
                                       "symbol": lone_head.name if lone and isinstance(lone_head, Sym) else "", "end": r_op.end})

    def _repeats_head(self, item: MathItem, chain: Chain) -> bool:
        """A chain that states a value for the lone symbol heading the previous chain, when the previous chain ends in a
        computation it left unevaluated: 'v = 8.4 / 2.0' then 'v = 5.2 m/s' (on the next line, or after 'so'), 'E = ½kx²',
        'E = ½ × 250 × 0.040²', 'E = 0.20 J'. The value is the computation's, as '= 5.2 m/s' opening the next line would state
        it, so the chain continues the previous one and the arithmetic is checked (repair round 2, holdout2 unit class: a
        computation set out over lines was read as a computation and a separate binding, and nothing checked the value). The
        previous chain must be of the same part, at most two statements before, made of equalities only, and headed by the
        same symbol; its last operand must be closed (no symbol) and not yet a value; the new chain's first link must state a
        value. A law ('v = d/t') ends in symbols and is no computation: it is substituted as before."""
        prev = self.prev_chain
        if self.request_mode or prev is None or chain.lead or not chain.ops or not prev.ops or len(chain.operands) < 2:
            return False
        if prev.item.part != item.part or self.order.get(item.statement_id, 0) - self.order.get(prev.item.statement_id, 0) > 2:
            return False
        if chain.ops[0] not in _EQUALITY or any(o not in _EQUALITY for o in prev.ops):
            return False
        head, prev_head = _first(chain.operands[0]), _first(prev.operands[0][0])
        if not (isinstance(head, Sym) and isinstance(prev_head, Sym) and head.kind in ("symbol", "word") and prev_head.kind == head.kind
                and head.name == prev_head.name):
            return False
        last, value = _first(prev.operands[-1][0]), _first(chain.operands[1])
        return (last is not None and value is not None and is_closed(last) and not is_value(last) and not unsupported_reasons(last)
                and is_value(value))

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
            d = dimension_of(node, self.scope, coefficients=True, substitutions=True)
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
        if isinstance(first, Unsupported) and first.reason == "a derivative" and first.name and isinstance(first.arg, Sym) and ops and ops[0] in _EQUALITY:
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
        elif rhs is not None and unsupported_reasons(rhs) and not self.request_mode:
            # 'a = dv/dt = 6 − 6t': through a link outside the encodings (which stays undecided) the answer states its own
            # formula a = 6 − 6t, kept for the evaluations it writes later ('At t = 1: a = 6 − 6(1)')
            for k in range(2, len(operands)):
                if ops[k - 1] not in _EQUALITY:
                    break
                cand = _first(operands[k][0])
                if cand is not None and not is_closed(cand) and not unsupported_reasons(cand) and head.name not in _syms(cand):
                    self.scope.add_formula(Formula(head.name, cand, operands[k][1], "law", start=getattr(cand, "start", 0), end=getattr(cand, "end", 0)))
                    break
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
                # 'At x = 1:' evaluates at a point; it binds nothing beyond its statement (the point is kept for ST-RANGE-001)
                self.conditions.append(Binding(head.name, value, number, unit, "condition", operands[k][1], getattr(node, "start", 0),
                                               getattr(node, "end", 0), wrapper=wrapper))
                return
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

    def _bound_in_part(self, name: str, part: str) -> bool:
        """``name`` has a value an order relation of ``part`` may compare: one the answer stated in the same part (before the
        relation, as the scope is built in document order; a stated root is no value), or else the one value the request and
        the earlier parts give it. A symbol given several values elsewhere ("at t = 0 and t = 8", then ``t > 40`` in part (c))
        is a variable sampled at points: the order relation is about the unknown, not a comparison of stated values."""
        blist = [b for b in self.scope.bindings.get(name, ()) if b.source != "root"]
        if any(b.source != "request" and self.part_of.get(b.statement_id, "") == part for b in blist):
            return True
        return bool(blist) and all(b.same_as(blist[0]) for b in blist[1:])

    def _false_rewrite(self, base: dict, item: MathItem, lnode: Node, rnode: Node, pos: int, full_operands: list) -> bool:
        """ST-STEP-003 (stem_invalid_step): a link of a chain that rewrites an expression of the unknown with a function in it
        into another, the chain going on after it ('log₁₀ x + log₁₀ 5 = log₁₀(x + 5) = 2'), is an identity the working uses;
        when the two sides are proven to differ at a sample point of the unknown (their rational enclosures are disjoint
        there, :func:`.reference.difference_witness`) the rewrite is no identity, and every step after it rests on a false
        one (repair round 3, V3-H2-STEM-MISSES: 'log x + log 5' is 'log(5x)', not 'log(x + 5)'). A link that ends its chain
        is the equation to solve, never an identity ('e^(2x) = e^(x + 3)'), and agreement at the sample points proves
        nothing, so such links stay undecided."""
        if pos + 2 >= len(full_operands):
            return False
        names = frozenset(self._unbound(lnode)) | frozenset(self._unbound(rnode))
        if not names or set(self._unbound(lnode)) != set(self._unbound(rnode)):
            return False
        witness = difference_witness(lnode, rnode, names)
        if witness is None:
            return False
        at = ", ".join(f"{n} = {v.numerator if v.denominator == 1 else f'{v.numerator}/{v.denominator}'}" for n, v in sorted(witness.items()))
        self.finding("ST-STEP-003", f"invalid step (stem_invalid_step): '{render(lnode)} = {render(rnode)}' is no identity: the two sides differ at {at} "
                                    f"(rational enclosures of both sides are disjoint there), so the working after it rests on a false rewrite",
                     base["statement_ids"], base["start"], base["end"])
        self.add(kind="link", outcome="context", reason="ST-STEP-003: a rewrite that is no identity (its sides differ at a sample point)", **base)
        return True

    def _unbound(self, node: Node) -> tuple[str, ...]:
        return tuple(n for n in symbols(node) if not self.scope.is_given(n))

    def _link(self, item: MathItem, left: Operand, lsid: str, op: str, right: Operand, rsid: str, pos: int, lone_first: bool, head: Optional[Node],
              approx_ctx: bool, full_operands: list, full_ops: list, *, head_gap: tuple[int, int] = ()) -> None:
        head_is_lone = head is not None
        sids = tuple(dict.fromkeys((lsid, rsid)))
        start, end = min(left.start, right.start), max(left.end, right.end)
        base = dict(statement_ids=sids, start=start, end=end, op=op, left=left, right=right, part=item.part, position=pos,
                    approx=op in _APPROX or approx_ctx, head_gap=head_gap)
        if self.request_mode:
            return
        if not left.readings or not right.readings:
            bad = left if not left.readings else right
            self.add(kind="link", outcome="undecided", code=bad.code or "ST-PARSE-001", reason=bad.error or "an operand could not be read", **base)
            return
        if self.profile.computer_science:
            left, right = self._binary_operand(left), self._binary_operand(right)
            base.update(left=left, right=right)
        lnode, rnode = left.readings[0], right.readings[0]
        if pos == 0 and op in _EQUALITY and isinstance(lnode, Unsupported) and lnode.reason == "a derivative" and lnode.name and lnode.arg is not None \
                and is_closed(lnode.arg) \
                and is_closed(rnode) and not unsupported_reasons(rnode):
            # f′(2) = 3 × 2² − 2: the derivative's stated formula evaluated at the argument (no formula stated: undecided)
            if self._evaluation(base, item, lnode.name, lnode.arg, rnode, derivative=True):
                return
        if op in _EQUALITY and self._antiderivative(base, lnode, rnode):
            return
        if op == "=" and self._model_link(base, lnode, rnode, pos):
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
        if op in _ORDER and "symbolic" in (lc, rc) and self.profile.is_mathematics:
            if any(isinstance(n, Abs) and _syms(n.arg) for side in (lnode, rnode) for n in walk(side)):
                self._undecided("ST-UNDEC-001", "an inequality in the absolute value of an unknown", base, item)
                return
            if pos == 1 and sum(1 for o in full_ops if o in _ORDER) >= 2 and _STEP_CUE_RE.search(item.gap_before[-40:]):
                # '…, so −3 < x − 1 < 3, giving −2 < x < 5': a step to a chained inequality, which no check derives
                self._undecided("ST-UNDEC-001", "a step to a chained inequality (a < x < b)", base, item)
                return
        if op in _ORDER and item.source == "condition":
            # 'The loop runs if and only if n > 0', 'none if Δ < 0': the comparison is the condition of a stated rule, not a claim
            # that it holds for the values the answer states
            self.add(kind="link", outcome="context", reason="an order relation the answer states as the condition of a rule (after 'if', 'when', "
                                                            "'unless'), not as holding", **base)
            return
        if op in _ORDER:
            if "bound" in (lc, rc) and not all(self._bound_in_part(n, item.part) for n in _syms(lnode) | _syms(rnode)):
                # 't > 40' in part (c) after 't = 0 h' and 't = 8 h' stated elsewhere: the symbol has no value of this part, so the
                # relation is about an unknown (an inequality's solution), not a comparison of stated values (section 4.6)
                self.add(kind="link", outcome="context", reason="an order relation about a symbol with no value stated in its own part (an inequality "
                                                                "about an unknown); another part's value is not compared here", **base)
                return
            if "bound" in (lc, rc) and lc != "symbolic" and rc != "symbolic" and _CONDITIONAL_RE.match(item.statement_text):
                # 'For 2 < t ≤ 3, 2 − t is negative, so v < 0.': the bound of a variable, or a property under it, never a
                # claim about the values the answer stated for the symbol elsewhere (t = 1 in part (a), v = 0 at rest)
                self.add(kind="link", outcome="context", reason="an order relation of a sentence stated under a condition on a variable: a bound of "
                                                                "the variable or a property under it, not a claim about the symbol's stated values", **base)
                return
            if lc in ("value", "closed", "bound") and rc in ("value", "closed", "bound"):
                self._dimension_check(base, item, lnode, rnode)
                negated = pos == len(full_ops) - 1 and self._said_to_fail(end)
                self.add(kind="cmp", outcome="check", negated=negated,
                         reason="a comparison the answer says fails (the words after it): the check is that it does not hold" if negated else "", **base)
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
                if f is not None and self._evaluated_formula(base, item, f, rnode):
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
            self._unit_companion(len(self.relations) - 1, lnode, rnode, chain_sub=self._chain_sub(left), head=head,
                                 chain_end=_rounded_chain_end(pos, full_operands, full_ops))
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
            if self._false_rewrite(base, item, lnode, rnode, pos, full_operands):
                return
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
        if self._cued_identity(op, lnode, rnode, full_ops, item):
            # 'Factorising, x² + 5x + 6 = (x + 2)(x + 4)', '(a + b)² = a² + b²' for 'Expand (a + b)²': an identity the words name;
            # checked as a step from the trivially true 'P = P', so it holds iff the two sides agree for every value of the unknowns
            self.add(kind="alg", outcome="check", premise_left=left, premise_op="=", premise_right=left, premise_ids=sids, explicit=True,
                     reason="an identity the answer or the request names (a factorisation, an expansion or a simplification): the two sides are "
                            "the same polynomial", **base)
            return
        if self._cued_identity(op, lnode, rnode, full_ops, item, shape_only=True):
            # '(a − b)² = a² − b²', 'x² − 9 = (x − 3)(x − 3)' under a request that names no factorising: a factorised form stated
            # equal to an expanded one of the same degree in every unknown is an identity claim by its shape; checked as one, its
            # failure a warning (the reading is inferred), so a wrong identity is never dropped silently (repair round 4,
            # rerun-stem-soundness-12)
            self.add(kind="alg", outcome="check", premise_left=left, premise_op="=", premise_right=left, premise_ids=sids, explicit=True,
                     inferred=True,
                     reason="an identity by its shape (a factorised form stated equal to an expanded form of the same degree in every unknown, "
                            "with no word naming it): the two sides must be the same polynomial", **base)
            return
        self.add(kind="stated", outcome="context", reason="a relation stated without a preceding relation to derive it from", **base)

    def _record_model(self, operands: list[tuple[Operand, str]], ops: list[str]) -> None:
        """``P = P₀e^(kt)`` (no variable named: the answer's applications name it) or ``C(t) = C0 e^(−kt)`` (the letter glued
        to a bracket holding one symbol): a model of one variable, kept for the ``mod`` checks of its applications. The right
        side must hold a power whose exponent holds symbols and nothing a ``mod`` check cannot read; a definition in which
        the model's own letter appears on the right is no model."""
        if len(operands) < 2 or not ops or ops[0] != "=" or not operands[0][0].readings or not operands[1][0].readings:
            return
        head, rhs = operands[0][0].readings[0], operands[1][0].readings[0]
        name, var = "", ""
        if isinstance(head, Sym) and head.kind == "symbol":
            name = head.name
        elif isinstance(head, BinOp) and head.op == "*" and isinstance(head.left, Sym) and isinstance(head.right, Sym) and head.right.kind == "symbol" \
                and application_of(head.left, head.right, self.reading):
            name, var = head.left.name, head.right.name
        if not name or not is_model_expression(rhs):
            return
        names = all_symbols(rhs)
        if name in names or (var and var not in names):
            return
        self.scope.add_model(Model(name, var, rhs, operands[1][1], "request" if self.request_mode else "answer", getattr(rhs, "start", 0),
                                   getattr(rhs, "end", 0)))
        if var:
            self.model_heads.add(id(head))

    def _function_definition(self, chain: Chain) -> str:
        """The letter a chain defines as a function of one variable, or ''. ``C(t) = 5t + 3`` and ``N(t) = 800 × (1/2)^(t/5)``:
        the letter glued to a bracket that holds one symbol, which the right side uses and the letter does not. ``P = P₀e^(kt)``
        and ``V = 20000 × 0.8^t``: a one-letter symbol set equal to an expression with a power whose exponent holds symbols
        (a model, exact or not). Only the letters matter, so the definition is read from the written text alone."""
        if not self.reading or len(chain.operands) < 2 or not chain.ops or chain.ops[0] != "=":
            return ""
        a, b = chain.operands[0], chain.operands[1]
        if not a.readings or not b.readings:
            return ""
        head, rhs = a.readings[0], b.readings[0]
        names = all_symbols(rhs)
        if isinstance(head, BinOp) and head.op == "*" and isinstance(head.left, Sym) and isinstance(head.right, Sym) and head.right.kind == "symbol" \
                and application_of(head.left, head.right, self.reading) and head.right.name in names and head.left.name not in names:
            return head.left.name
        if isinstance(head, Sym) and head.kind == "symbol" and len(head.name) == 1 and head.name not in names and has_exponential(rhs):
            return head.name
        return ""

    def _function_letters(self) -> set[str]:
        return self.scope.functions | set(self.scope.models)

    def _function_application(self, node: Optional[Node]) -> Optional[Node]:
        """The argument when ``node`` is an application of a function the text defines (``N(15)`` after ``N(t) = …``,
        ``P(6)`` after the request's ``P = P₀e^(kt)``: the letter glued to its bracket), else None."""
        if node is None or not self.reading or not isinstance(node, BinOp) or node.op != "*" or not isinstance(node.left, Sym):
            return None
        if node.left.name in self._function_letters() and application_of(node.left, node.right, self.reading):
            return node.right
        return None

    def _applies_function(self, *nodes: Optional[Node]) -> bool:
        """Some node holds an application of a function the text defines (``2N(t)``, ``P(t + 1)/P(t)``)."""
        letters = self._function_letters()
        return bool(self.reading and letters) and any(letter in letters for n in nodes if n is not None for letter, _a in applications(n, self.reading))

    def _model_candidates(self, name: str) -> list[tuple[Model, str, Node]]:
        """Every distinct definition of the model ``name`` in scope whose variable is named (:func:`resolve_model`), as
        ``(model, variable, expression)``. A letter the request or the answer defines as two models (``Model A: N =
        100e^(t/5)``, ``Model B: N = 100 × 2^(t/3)``) has two, and an application of it may mean either; a definition whose
        variable nothing names (``P = 250e^(6k)``, an evaluation written as a definition) is none."""
        letters = {n for n in self.scope.names if len(n) == 1 and n.isalpha()}
        out: list[tuple[Model, str, Node]] = []
        seen: set[tuple[str, str]] = set()
        for m in self.scope.models.get(name, ()):
            resolved = resolve_model(m, self.app_args.get(name, []), letters)
            if resolved is None:
                continue
            var, expr = resolved
            key = (var, render_model(expr))
            if key not in seen:
                seen.add(key)
                out.append((m, var, expr))
        return out

    def _expand_model(self, name: str, arg: Node) -> Optional[Node]:
        cands = self._candidates.get(name)
        if not cands:
            return None
        m, var, expr = cands[self._choice.get(name, 0)]
        out = substitute(expr, var, arg)
        if out is not None:
            self._applied.append((replace(m, expr=expr, var=var), var))
        return out

    def _model_link(self, base: dict, lnode: Node, rnode: Node, pos: int) -> bool:
        """``P(t + 4) = P₀e^(k(t + 1))``, ``P(6) = 250e^(6k)``, ``C(40) = 1600 × 2^(−5)``: an equality with an application of a
        model, read as the model's expression at the written argument (``models.py``), becomes a ``mod`` check: some value
        of the model's variable, of every symbol with no stated value and of the stated symbols within their values must
        satisfy it. False (the link keeps its old reading) when no model is applied or the link is not one a ``mod`` check
        reads, and for the model's own definition (``C(t) = C0 e^(−kt)``)."""
        if not self.scope.models or not self.reading or self.request_mode or (pos == 0 and id(lnode) in self.model_heads):
            return False
        self._candidates = {}
        for letter in sorted({letter for n in (lnode, rnode) for letter, _a in applications(n, self.reading)}):
            cands = self._model_candidates(letter)
            if cands:
                self._candidates[letter] = cands
        if not self._candidates:
            return False
        letters = sorted(self._candidates)
        combos: list[tuple[int, ...]] = [()]
        for n in letters:  # every combination of the letters' definitions, one index per letter
            combos = [c + (i,) for c in combos for i in range(len(self._candidates[n]))]
            if len(combos) > MAX_MODEL_READINGS:
                return False
        # one reading of the link per combination of definitions: the link must hold in some reading, so no definition is
        # chosen for the answer, and every reading must be one the check reads (else the link keeps its old reading)
        pairs: list[tuple[Node, Node]] = []
        applied: list[tuple[Model, str]] = []
        for combo in combos:
            self._choice = dict(zip(letters, combo))
            self._applied = []
            sides = model_link_sides(lnode, rnode, self.reading, self._expand_model)
            if sides is None or not self._applied:
                return False
            pairs.append((sides[0], sides[1]))
            applied += self._applied
        if len(pairs) > 1 and not relaxation_fits(*(n for pair in pairs for n in pair)):
            return False
        names = set().union(*(all_symbols(lr) | all_symbols(rr) for lr, rr in pairs))
        variables = {v for _m, v in applied if v in names}
        variables |= {n for n in names if not self.scope.has_reading(n)}
        m, var = applied[0]
        formula = Formula(m.name, m.expr, m.statement_id if m.source == "answer" else "request", m.source, params=(var,), start=m.start, end=m.end)
        b = dict(base)
        b["left"] = Operand(tuple(lr for lr, _rr in pairs), base["left"].start, base["left"].end)
        b["right"] = Operand(tuple(rr for _lr, rr in pairs), base["right"].start, base["right"].end)
        used = list(dict.fromkeys((mm.name, vv, render_model(mm.expr)[:80], "the request" if mm.source == "request" else mm.statement_id) for mm, vv in applied))
        if len(used) == 1:
            reason = f"an evaluation of the model {used[0][0]}({used[0][1]}) = {used[0][2]} (stated in {used[0][3]}) at the written argument, against the other side"
        else:
            reason = ("an evaluation of the models " + "; ".join(f"{a}({v}) = {e} (stated in {w})" for a, v, e, w in used)
                      + " at the written argument, against the other side"
                      + ("; each definition of a letter is one reading of the link, which must hold in some reading" if len(pairs) > 1 else ""))
        self.add(kind="mod", outcome="check", unbound=tuple(sorted(variables)), formula=formula, reason=reason, **b)
        return True

    def _antiderivative(self, base: dict, lnode: Node, rnode: Node) -> bool:
        """``∫6t dt = 3t²`` (an integral with no limits and the antiderivative the answer states, both polynomials in the
        integration variable, a constant of integration allowed): the derivative of the stated antiderivative, formed by
        the STEM pack by the power rule (``calculus``), against the integrand, for every value of the variable (an
        ``alg`` check from the trivially true premise ``D = D``, so it holds iff the two polynomials agree). Any other
        integral stays outside the encodings (False: nothing planned)."""
        for integral, stated in ((lnode, rnode), (rnode, lnode)):
            if not (isinstance(integral, Unsupported) and integral.reason == "an integral" and integral.name.startswith("∫") and integral.arg is not None):
                continue
            if unsupported_reasons(stated):
                return False
            x = integral.name[1:]
            p, q = polynomial(integral.arg, x), polynomial(stated, x)
            if p is None or q is None or p[1]:
                return False
            d = polynomial_node(derivative(q[0]), x, getattr(stated, "start", 0), getattr(stated, "end", 0))
            dop = Operand((d,), getattr(stated, "start", 0), getattr(stated, "end", 0))
            b = dict(base)
            b["left"] = dop
            b["right"] = Operand((integral.arg,), getattr(integral, "start", 0), getattr(integral, "end", 0))
            self.add(kind="alg", outcome="check", premise_left=dop, premise_op="=", premise_right=dop, premise_ids=base["statement_ids"], explicit=True,
                     reason=f"an antiderivative: the derivative of the stated antiderivative (formed by the STEM pack by the power rule, not by the engine) "
                            f"against the integrand, for every value of {x}", **b)
            return True
        return False

    def _evaluated_formula(self, base: dict, item: MathItem, f: Formula, rnode: Node) -> bool:
        """``a = 6 − 6(1)`` written for a symbol whose formula the answer stated in this part (``a = 6 − 6t``) but whose shape
        the written expression does not repeat: the written expression is the formula evaluated at stated values, so the
        formula under the bindings of its symbols is set against it (a ``sub`` check that evaluates; some binding of each
        symbol must give the written value). False (nothing planned) when the formula comes from another part, has a
        symbol with no stated value, or uses notation outside the encodings."""
        if not f.statement_id or self.part_of.get(f.statement_id, "") != item.part or unsupported_reasons(f.expr) or f.params \
                or any(isinstance(n, PlusMinus) for n in walk(f.expr)):
            return False  # a formula with ± has two values: a written root takes one of them (the roots are checked by stem-sol)
        names = [n for n in _syms(f.expr) if not n.endswith("()")]
        if not names or any(not self.scope.has_reading(n) for n in names) or any(isinstance(n, Apply) for n in walk(f.expr)):
            return False
        b = dict(base)
        b["left"] = Operand((f.expr,), base["start"], base["end"])
        b["right"] = Operand((rnode,), base["right"].start, base["right"].end)
        b["statement_ids"] = tuple(dict.fromkeys((f.statement_id,) + base["statement_ids"]))
        self._dimension_check(base, item, f.expr, rnode)
        self.add(kind="sub", outcome="check", evaluate=True, formula=f,
                 reason=f"the formula of '{f.name}' stated in {f.statement_id} under the stated values of {', '.join(names)}, against the written expression", **b)
        self._unit_companion(len(self.relations) - 1, f.expr, rnode)
        return True

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
                if isinstance(n, (Func, RealPower, Root, Apply, Abs, PlusMinus, Unsupported, Percent, Quantity, WithUnit)):
                    return False
                if isinstance(n, BinOp) and n.op == "/" and x in _syms(n.right):
                    return False
                if isinstance(n, Pow) and (n.exp < 0 or n.exp > 4):
                    return False
        return max(_degree(lnode, x), _degree(rnode, x)) >= 1

    def _cued_identity(self, op: str, lnode: Node, rnode: Node, full_ops: list, item: MathItem, *, shape_only: bool = False) -> bool:
        """A one-link relation between two polynomials in the same one to three unknowns (none of them bound) that the words
        call an identity: '≡', or a factorisation, expansion or simplification named in its own statement ('Factorising,
        x² + 5x + 6 = …') or by a request that asks for one and solves nothing ('Expand (a + b)²'). With ``shape_only`` the
        words are not read: the relation is an identity by its shape when one side is factorised (a product of sums, or a
        power of a sum, holding the unknowns) and the other is not, both sides have the same exact degree in every unknown, and
        the request asks to solve nothing (:func:`_identity_shape`)."""
        if not self.profile.is_mathematics or len(full_ops) != 1 or op not in ("=", "≡"):
            return False
        names = _syms(lnode)
        if not 1 <= len(names) <= 3 or _syms(rnode) != names or any(self.scope.bindings.get(n) for n in names):
            return False
        for side in (lnode, rnode):
            for n in walk(side):
                if isinstance(n, (Func, Root, Apply, Abs, PlusMinus, Unsupported, Percent, Quantity, WithUnit)):
                    return False
                if isinstance(n, Sym) and n.kind != "symbol":
                    return False
                if isinstance(n, BinOp) and n.op == "/" and _syms(n.right):
                    return False
                if isinstance(n, Pow) and (n.exp < 0 or n.exp > 4):
                    return False
        if shape_key(lnode) == shape_key(rnode) or not any(max(_degree(lnode, x), _degree(rnode, x)) >= 1 for x in names):
            return False
        if op == "≡":
            return True
        req = self._request_lower
        prev = self.prev_rel
        prev_right = _first(prev["right"]) if prev is not None and prev["item"].part == item.part and prev["syms"] & names else None
        if prev_right is not None and shape_key(prev_right) == shape_key(rnode):
            # the relation keeps the right side of the equation before it and rewrites its left ('(x + 2)² = x² + 4.
            # Expanding, x² + 4x + 4 = x² + 4'): a step from that equation, not an identity claim (repair round 4)
            return False
        if shape_only:
            # a request that sets an equation or asks for the values that satisfy one makes the relation an equation to solve
            asks_values = any(w in req for w in ("solve", "root", "find the value", "for which", "such that", "satisf", "value of x", "values of"))
            return not asks_values and "=" not in req and _identity_shape(lnode, rnode, names)
        low = item.statement_text.lower()
        if any(c in low for c in _IDENTITY_CUES):
            return True
        return any(c in req for c in _IDENTITY_CUES) and "solve" not in req and "=" not in req

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
        self._unit_companion(len(self.relations) - 1, sym_side, num_side)

    def _given_in_another_part(self, name: str, node: Node, part: str) -> bool:
        """True when the answer reuses the symbol ``name`` in this part for a quantity the request gives: every binding of
        the symbol stands in another part, and the value substituted here is a value the request states, with the same
        dimension (``R = 2.4 Ω`` in part (a), then ``P = (9.93 V)² / 6.0 Ω`` in part (d) for "the 6.0 ohm resistor" of the
        question). The value is then read for the symbol in this part, not checked against the other part's bindings; a
        value the request does not give is still checked against them."""
        blist = self.scope.bindings.get(name, ())
        if not part or not blist or any(self.part_of.get(b.statement_id, "") in ("", part) for b in blist):
            return False
        v = value_of(node)
        if v is None or v[1] is None:
            return False
        here = Binding(name, v[0], v[1], v[2], "substitution", "", wrapper=v[3])
        dim = v[2].dim if v[2] is not None else None
        for qnode, _a, _b in self.request.quantities[:64]:
            q = value_of(qnode)
            if q is None or q[1] is None or (q[2].dim if q[2] is not None else None) != dim:
                continue
            if here.same_as(Binding(name, q[0], q[1], q[2], "request", "request", wrapper=q[3])):
                return True
        return False

    def _substitution(self, base: dict, item: MathItem, sym_side: Node, num_side: Node, pairs: list, formula: Optional[Formula] = None) -> None:
        checkable: list[tuple[str, Node]] = []
        introduced: list[tuple[str, Node]] = []
        for s, n in pairs:
            name = getattr(s, "name", "")
            if isinstance(s, Apply):
                name = s.name + "()"
            if not name or (isinstance(n, Sym) and n.name == name):
                continue
            if self.scope.is_bound(name) and not self._given_in_another_part(name, n, item.part):
                checkable.append((name, n))
            else:
                introduced.append((name, n))
        sid = base["statement_ids"][-1]
        for name, n in introduced:
            v = value_of(n)
            if v is not None and v[1] is not None:
                unit = v[2]
                if unit is None and not v[3]:
                    # a bare numeral for a symbol bound nowhere else, which the request states with an SI unit ('radius 3.0 m',
                    # 'A mass of 0.50 kg'): the substitution carries the request's unit, so the law's dimension is read (repair
                    # round 4, ADV4-11: '2πr' for an area went unread when r was given only in the request)
                    q = fixed_quantity(name, self.profile.key, request_text=self.request.text)
                    rq = self._request_quantity_for(n, q.dimension if q is not None else None)
                    if rq is not None and rq.unit is not None and unit_scale(rq.unit) == 1:
                        unit = rq.unit
                self.scope.add(Binding(name, v[0], v[1], unit, "substitution", sid, getattr(n, "start", 0), getattr(n, "end", 0), wrapper=v[3]))
        self._dimension_check(base, item, sym_side, num_side)
        if not checkable:
            self.add(kind="sub", outcome="binding", pairs=tuple(introduced), formula=formula,
                     reason="values substituted into symbols the report binds nowhere else (they introduce the values)", **base)
            return
        self.add(kind="sub", outcome="check", pairs=tuple(checkable), formula=formula,
                 unbound=tuple(n for n, _x in introduced),
                 reason="substituted values against the stated bindings" + (f" of the formula in {formula.statement_id}" if formula else ""), **base)

    # -------------------------------------------------------------- units: the as-written reading (ST-UNIT-003)
    def _symbol_scale(self, name: str) -> Optional[Fraction]:
        """The one SI factor of the values the answer states for ``name`` (bindings, else substitution readings): 1 for
        values without a unit, 1/100 for per cents; None when they differ or a unit has no exact factor."""
        blist = [b for b in self.scope.bindings.get(name, ()) if b.source != "root"] or list(self.scope.substitutions.get(name, ()))
        if not blist:
            return None
        scales = set()
        for b in blist:
            s = unit_scale(b.unit)
            if s is None:
                return None
            scales.add(s / 100 if b.unit is None and b.wrapper == "%" else s)
        return scales.pop() if len(scales) == 1 else None

    def _written_dim(self, name: str) -> Optional[Dimension]:
        """The dimension of a symbol for the as-written reading (:func:`.reference.as_written_reading`): its bindings' units,
        and dimensionless when every binding of it is a bare number (``M = 400``, a magnification): a factor with no unit
        changes no dimension, so ``I/M`` with ``I = 12 mm`` is a length in millimetres."""
        d = self._symbol_dim(name)
        if d is not None:
            return d
        blist = [b for b in self.scope.bindings.get(name, ()) if b.source != "root"]
        if blist and all(b.unit is None and not b.wrapper for b in blist):
            return DIMENSIONLESS
        return None

    def _symbol_dim(self, name: str) -> Optional[Dimension]:
        dims = set()
        for b in [b for b in self.scope.bindings.get(name, ()) if b.source != "root"] or list(self.scope.substitutions.get(name, ())):
            if b.unit is None or b.unit.unknown or b.unit.dim is None:
                return None
            dims.add(b.unit.dim)
        return dims.pop() if len(dims) == 1 else None

    def _chain_sub(self, operand: Operand) -> Optional[Relation]:
        """The substitution planned for the link just before this one in its chain (``v = 2.5/10`` before ``2.5/10 = 0.25 m s⁻¹``):
        its numeric side is this link's left operand (bounded look-back)."""
        for r in reversed(self.relations[-8:]):
            if r.kind == "sub" and (r.right is operand or r.left is operand):
                return r
        return None

    def _unit_companion(self, idx: int, computed: Node, stated: Node, *, chain_sub: Optional[Relation] = None, head: Optional[Node] = None,
                        chain_end: Optional[Node] = None) -> None:
        """Plan the ``unit`` companion (ST-UNIT-003) of the check just added at ``idx``, when its two readings genuinely
        differ and the answer's own units say which one it means:

        * ``written``: the as-written reading is not admissible beside the SI reading (:func:`.reference.as_written_reading`:
          both sides carry units of one dimension whose factors differ, or a per cent sign that converts one side only). The
          check then decides the relation under both readings, and the companion that the as-written reading never holds
          where the SI reading fails; together they decide the SI reading exactly, and a failure is labelled a unit error
          (``stem_unit_error``) when the numbers are right as written and a slip otherwise;
        * ``traced``: the computed side is bare, the stated value carries a unit, and bare numerals of it repeat the numbers
          of bindings stated in non-SI units (``d = 2.5 km``, then ``v = 2.5/10 = 0.25 m s⁻¹``): the companion reads each
          such numeral in its binding's unit. That reading is the report's own only by inference, so its failure is a
          warning."""
        if self.request_mode or self.profile.computer_science:
            return
        rel = self.relations[idx]
        if any(isinstance(n, (Quantity, WithUnit)) and (n.unit.unknown or not n.unit.readings) for side in (computed, stated) for n in walk(side)):
            return  # an unrecognised unit: the relation is checked as written only (ST-UNIT-001)
        if (chain_sub is not None and self._request_states_law(chain_sub)) or (isinstance(head, Sym) and head.name in self._request_law_heads()):
            # a model the request states in its own units ('algal cover A (%) fits the line A = 3.5N + 10, where N is ... in
            # mg/l'): its coefficients are fitted to those units, so its numbers, and the per cent its output is given in, are
            # read as the request writes them; no SI reading applies (repair round 2: '3.5 × 8 + 10 = 38%' was a false unit error)
            return
        if rel.op in _APPROX and unit_written_once(computed, stated) is not None:
            # a rounding link that writes the unit (or the per cent sign) once, after the rounded value ('= 52.4 ≈ 52%'): the
            # bare value before the rounding is in that unit too (a rounding converts nothing), so its as-written and SI
            # readings coincide and no unit companion is planned; the link itself is still checked as a rounding (repair
            # round 3, ADV3-03: correct percentage working was named stem_unit_error at error)
            return
        try:
            ok, why = as_written_reading(computed, stated, symbol_scale=self._symbol_scale, symbol_dim=self._written_dim, profile_key=self.profile.key)
        except Exception:  # the companion only adds a check; a reading it cannot make adds none
            return
        if not ok:
            self.relations[idx] = rel = replace(rel, unit_reason=why)
            self.relations.append(replace(rel, index=len(self.relations), kind="unit", companion_of=idx, unit_case="written",
                                          reason=f"ST-UNIT-003: the as-written reading is not admissible beside the SI reading ({why}); this companion "
                                                 f"of the check decides that the numbers do not hold as written while failing in SI"))
            return
        # a bare stated value is read too when the working is a ratio of one kind of quantity given in two units ('M = I/A =
        # 40/20 = 2' with I = 40 mm and A = 20 µm: as written 2, in SI 2000; repair round 2, holdout2 magnification class)
        bare = _stated_bare(stated)
        if chain_sub is None:
            self._request_traced_companion(idx, rel, computed, stated)
            return
        if not (_stated_with_unit(stated) or bare) or any(isinstance(n, (Quantity, WithUnit, Percent)) for n in walk(computed)):
            return
        traced: list[tuple[int, int, Binding]] = []
        #: every numeral the working substitutes whose unit is known: (start, end) -> the binding, or the request's quantity, it repeats
        accounted: dict[tuple[int, int], Binding] = {}
        leaves = {(getattr(n, "start", -1), getattr(n, "end", -1)): n for n in walk(computed) if isinstance(n, Num)}
        # the values the substitution substitutes into symbols bound nowhere else are read too: they are recorded as
        # substitution bindings, not as pairs of the check ('ΔEp = mgΔh = 250 × 9.8 × 2.0' with only g bound: m and Δh
        # introduce 250 and 2.0; repair round 2, own probes of the unit class)
        introduced = [(b.symbol, leaves[(b.start, b.end)]) for name in chain_sub.unbound for b in self.scope.substitutions.get(name, ())
                      if b.statement_id in chain_sub.statement_ids and (b.start, b.end) in leaves]
        # the law the working applies, by its symbols: a temperature it substitutes is absolute when the law is one of the closed
        # table's (pV = nRT, the gas laws, ΔG = ΔH − TΔS, ...), so a value written in °C is read in kelvin (repair round 4, ADV4-01)
        law_head = _first(chain_sub.left) if chain_sub.right is not None and _first(chain_sub.right) is computed else _first(chain_sub.right)
        law_names = _syms(law_head) | {n for n, _node in chain_sub.pairs} | ({head.name} if isinstance(head, Sym) else set())
        if chain_sub.formula is not None:
            law_names |= _syms(chain_sub.formula.expr) | {chain_sub.formula.name}
        absolute = applies_absolute_temperature_law(law_names)
        kelvin_used = False
        si_form: set[tuple[int, int]] = set()
        for name, written in [*chain_sub.pairs, *introduced]:
            ends = self._written_change(written)
            if ends is not None:
                # a change written as the difference of the request's two ends ('ΔT = (70 − 20)' for 'from 20 °C to 70 °C'):
                # both numerals are read in their unit, kelvin for an offset scale, so the difference is the change (repair
                # round 5, ADV5-03)
                for leaf, bd in ends:
                    if (leaf.start, leaf.end) in leaves:
                        accounted[(leaf.start, leaf.end)] = replace(bd, symbol=name)
                continue
            # a negative numeral substitutes a negative quantity ('−92.0' for ΔH = −92.0 kJ mol⁻¹): its numeral is read with its sign
            node, sign = (written.arg, -1) if isinstance(written, Neg) and isinstance(written.arg, Num) else (written, 1)
            if not isinstance(node, Num) or (node.start, node.end) not in leaves:
                continue
            blist = [b for b in self.scope.bindings.get(name, ()) if b.source != "root"]
            same = [b for b in blist if b.value == sign * node.number.value]
            if same and all(b.unit is None and not b.wrapper for b in same) or not same:
                # the answer gives the number no unit ('Given d = 1.8', or the substitution itself): the request's quantity
                # with that number, when there is exactly one (units given only in the task)
                q = fixed_quantity(name, self.profile.key, request_text=self.request.text)
                rq = self._request_quantity_for(written, q.dimension if q is not None else None)
                if rq is None and same:
                    # a bare result the answer worked from the request's quantities alone ('A = 20 × 20 = 400' for a square
                    # of side 20 cm): read in the unit those quantities give it (accuracy round 1, ADV6-03)
                    rq = self._derived_binding(name, node, sign)
                same = [replace(rq, symbol=name)] if rq is not None else []
            if not same and name.startswith("Δ"):
                # a change the request states only by its two ends ('from 20 °C to 70 °C', then ΔT as 50): read in their unit,
                # kelvin for an offset scale (repair round 5, ADV5-03)
                diff = self._request_difference_for(node, sign)
                if diff is not None:
                    same = [replace(diff, symbol=name)]
            if not same:
                # the working substitutes a quantity already converted to SI ('180 000' for the request's '180 kJ', '2000' for
                # '2.0 kW'): the numeral is accounted for, read as written (repair round 4, ADV4-02: the other numerals of such a
                # working were left unread, so a time given only in minutes went unconverted unseen)
                si = self._si_form_binding(name, written)
                if si is not None:
                    accounted[(node.start, node.end)] = si
                    si_form.add((node.start, node.end))
                continue
            affine = [b for b in same if b.unit is not None and is_affine_unit_expr(b.unit)]
            if affine:
                # a temperature written in °C (or °F), substituted for the T of a law that needs the absolute temperature: read
                # in kelvin; in any other law it is left unread (a temperature on an offset scale may be a difference)
                kb = _kelvin_binding(affine[-1], node) if absolute and base_symbol(name) == "T" and len(affine) == len(same) else None
                if kb is None:
                    continue
                accounted[(node.start, node.end)] = kb
                traced.append((node.start, node.end, kb))
                kelvin_used = True
                continue
            with_unit = [b for b in same if b.unit is not None and b.unit.dim is not None and unit_scale(b.unit) is not None]
            if not with_unit or len(with_unit) != len(same) or len({unit_scale(b.unit) for b in with_unit}) != 1:
                continue
            bd = with_unit[-1]
            accounted[(node.start, node.end)] = bd
            if unit_scale(bd.unit) != 1:
                traced.append((node.start, node.end, bd))
        for sub in walk(computed):
            # a change written as the difference of the request's two ends ('× (70 − 20)' for 'from 20 °C to 70 °C'), whatever
            # symbol it stands for: both numerals are read in their unit, kelvin for an offset scale (repair round 5, ADV5-03)
            ends = self._written_change(sub) if isinstance(sub, BinOp) and sub.op == "-" else None
            for leaf, bd in ends or ():
                if (leaf.start, leaf.end) in leaves and (leaf.start, leaf.end) not in accounted:
                    accounted[(leaf.start, leaf.end)] = bd
        if traced:
            # every numeral of the working must be accounted for (read in its binding's unit, or a coefficient the law writes):
            # a bare number whose unit nothing says (4.18 for c in J g⁻¹ K⁻¹) may carry the conversion the others lack
            spots = dict(accounted)
            sym_node = _first(chain_sub.left) if chain_sub.right is not None and _first(chain_sub.right) is computed else _first(chain_sub.right)
            coeffs = {n.number.value for n in walk(sym_node) if isinstance(n, Num)} if sym_node is not None else set()
            if chain_sub.formula is not None:
                # the substitution of a law stated on a line of its own ('E = ½kx²', then 'E = ½ × 250 × 4.0² = 2000 J'): the
                # coefficients are the law's (repair round 2, holdout2 unit class)
                coeffs |= {n.number.value for n in walk(chain_sub.formula.expr) if isinstance(n, Num)}
            if any((key not in spots) and leaf.number.value not in coeffs for key, leaf in leaves.items()):
                return
            target = stated.unit.dim if isinstance(stated, Quantity) else (stated.arg.unit.dim if isinstance(stated, Neg) and isinstance(stated.arg, Quantity) else None)
            prose_unit = self._prose_unit_of(rel, stated) if bare else None
            if prose_unit is None and bare and isinstance(chain_end, Quantity) and chain_end.unit.dim is not None and unit_scale(chain_end.unit) is not None:
                # the chain writes its unit once, after rounding the bare value ('= 2.5 / 10 = 0.25 ≈ 0.3 m s⁻¹'): the bare value is
                # in that unit too (repair round 3, ADV3-03 class: the unit written once after the rounded value)
                prose_unit = chain_end.unit
            if prose_unit is not None:
                # a bare result whose unit the answer gives in its prose ('E = ½kx² = ½ × 250 × 4.0² = 2000. The elastic potential
                # energy stored is 2000 J.'): the stated value is read in that unit (repair round 2, holdout2 unit class)
                target = prose_unit.dim
            elif bare:
                # the ratio's readings differ only when its quantities are given in units of different factors
                if len({unit_scale(b.unit) for key, b in accounted.items() if b.unit is not None and key not in si_form}) < 2:
                    return
                target = DIMENSIONLESS
            if kelvin_used and target is not None and target.same_physical(_TEMPERATURE_DIM):
                return  # a temperature result read from offset values: whether it is a temperature or a difference is not stated
            read = coefficient_free_dimension(computed, lambda _n: None,
                                              num_dim=lambda n: spots[(n.start, n.end)].unit.dim if (n.start, n.end) in spots else DIMENSIONLESS)
            if target is None or read is None or not read.same_physical(target):
                return  # read in the bindings' units the working does not give the stated value's dimension: the reading is incomplete
            shown = ", ".join(f"{b.symbol} = {b.number.text} {b.unit.text}" + (" (the request's quantity)" if b.source == "request" else "")
                              + (" (a temperature written in °C or °F, read in kelvin for a law of absolute temperature)" if b.wrapper == KELVIN_READING else "")
                              for _a, _b, b in traced if b.unit is not None)
            self.relations.append(replace(rel, index=len(self.relations), kind="unit", companion_of=idx, unit_case="traced", traced=tuple(traced),
                                          stated_unit=prose_unit,
                                          reason=f"ST-UNIT-003: bare numbers of the working repeat the numbers of bindings, or of the request's quantities, "
                                                 f"stated in non-SI units ({shown}); this companion reads them in those units"
                                                 + (f", and the stated value in the unit the answer's prose gives it ({prose_unit.text})" if prose_unit else "")))

    def _derived_binding(self, name: str, numeral: Num, sign: int = 1) -> Optional[Binding]:
        """The one binding of ``name`` with the numeral's value, a bare number, read in the unit the request's quantities give
        it when the answer worked it from those quantities alone: it is the stated end of an arithmetic link whose computed
        side repeats only the request's quantities (each one number with one unit, none on an offset scale; nothing else, no
        symbol), combined by products, quotients, integer powers and sums of one unit ('A = 20 × 20 = 400' for a square of side
        20 cm is 400 cm²). None otherwise. Accuracy round 1, ADV6-03: a pressure worked from that area as if in m² passed."""
        value = sign * numeral.number.value
        same = [b for b in self.scope.bindings.get(name, ()) if b.source != "root" and b.value == value]
        if len(same) != 1 or same[0].unit is not None or same[0].wrapper or same[0].source != "result":
            return None
        bd = same[0]
        # the arithmetic links by the span of their bare stated value, indexed once each as the relations grow (linear)
        for k in range(self._eq_indexed, len(self.relations)):
            stated = _first(self.relations[k].right)
            if self.relations[k].kind == "eq" and isinstance(stated, Num):
                self._eq_by_stated.setdefault((stated.start, stated.end), k)
        self._eq_indexed = len(self.relations)
        k = self._eq_by_stated.get((bd.start, bd.end))
        r = self.relations[k] if k is not None else None
        if r is not None and r.kind == "eq" and r.outcome == "check":
            computed = _first(r.left)
            if computed is None or _syms(computed) or any(isinstance(n, (Quantity, WithUnit, Percent)) for n in walk(computed)):
                return None
            atoms = self._request_unit_atoms(computed, 0)
            if atoms is None:
                return None
            merged: dict[tuple[str, str], UnitAtom] = {}
            for a in atoms:
                key = (a.text, a.prefix)
                prev = merged.get(key)
                merged[key] = a if prev is None else replace(prev, power=prev.power + a.power)
            kept = tuple(a for a in merged.values() if a.power != 0)
            dim, factor = DIMENSIONLESS, Fraction(1)
            for a in kept:
                if a.dim is None or a.factor is None:
                    return None
                dim, factor = dim * a.dim, factor * a.factor
            text = " ".join(a.text + ("" if a.power == 1 else str(a.power).translate(_SUPERSCRIPT)) for a in kept)
            unit = UnitExpr(text=text, readings=(UnitReading(atoms=tuple(replace(a, text=a.text) for a in kept), dim=dim, factor=factor),))
            return replace(bd, unit=unit)
        return None

    def _request_unit_atoms(self, node: Node, depth: int) -> Optional[list[UnitAtom]]:
        """The unit atoms (with their powers) of a closed working whose numerals all repeat the request's quantities, each one
        number with one unit of one exact reading and no offset; None for anything else (another numeral, a function, a sum
        of two units). Bounded by depth."""
        if depth > 32:
            return None
        if isinstance(node, Num):
            rq = self._request_quantity_for(node)
            if rq is None or rq.unit is None or is_affine_unit_expr(rq.unit) or unit_scale(rq.unit) is None or len(rq.unit.readings) != 1:
                return None
            return list(rq.unit.readings[0].atoms)
        if isinstance(node, Neg):
            return self._request_unit_atoms(node.arg, depth + 1)
        if isinstance(node, Pow):
            inner = self._request_unit_atoms(node.base, depth + 1)
            if inner is None or not 1 <= node.exp <= 4:
                return None
            return [replace(a, power=a.power * node.exp) for a in inner]
        if isinstance(node, BinOp) and node.op in ("*", "/", "+", "-"):
            left = self._request_unit_atoms(node.left, depth + 1)
            right = self._request_unit_atoms(node.right, depth + 1)
            if left is None or right is None:
                return None
            if node.op == "*":
                return left + right
            if node.op == "/":
                return left + [replace(a, power=-a.power) for a in right]
            # a sum or difference: its terms in one unit as written
            sig = lambda atoms: sorted((a.text, a.prefix, a.power) for a in atoms)  # noqa: E731
            return left if sig(left) == sig(right) else None
        return None

    #: the most numerals a working with no substitution before it may have for its numerals to be read in the request's units
    _MAX_REQUEST_TRACED_LEAVES = 12

    def _request_traced_companion(self, idx: int, rel: Relation, computed: Node, stated: Node) -> None:
        """The ``traced`` companion (ST-UNIT-003) of a working that substitutes into no symbol: the numbers combined directly
        ('Total = 2.5 + 300 = 302.5 J' for the request's 2.5 kJ and 300 J; 'A = 30 × 20 = 600 m²' for a tile of 30 cm by
        20 cm). It is planned only when the reading is the request's own: the stated value carries a unit of one exact factor;
        every numeral of the computed side repeats exactly one of the request's quantities (:meth:`_request_quantity_for`:
        one number, one unit), or states one of them converted to SI (:meth:`_si_form_binding`, read as written); none is on
        an offset scale (°C, °F); at least one is in a unit whose factor is not 1; and read in those units the working has the
        stated value's dimension. A working with any other numeral (a coefficient, a conversion factor, a number of its own)
        is left as it is. The companion reads each repeated numeral in its quantity's unit, so the numbers combined without
        their conversion fail it (``stem_unit_error``, at warning: the units are the request's, not the report's). Accuracy
        round 1, ADV6-03: these workings passed as plain arithmetic."""
        target_node = stated.arg if isinstance(stated, Neg) else stated
        if not _stated_with_unit(stated) or not isinstance(target_node, Quantity) or _syms(computed):
            return
        if any(isinstance(n, (Quantity, WithUnit, Percent)) for n in walk(computed)):
            return
        leaves = [n for n in walk(computed) if isinstance(n, Num)]
        if not leaves or len(leaves) > self._MAX_REQUEST_TRACED_LEAVES:
            return
        spots: dict[tuple[int, int], Binding] = {}
        traced: list[tuple[int, int, Binding]] = []
        for leaf in leaves:
            rq = self._request_quantity_for(leaf)
            if rq is None:
                si = self._si_form_binding("", leaf)
                if si is None:
                    return  # a numeral the request does not state: its unit is not known, so no reading is made
                spots[(leaf.start, leaf.end)] = si
                continue
            if rq.unit is None or is_affine_unit_expr(rq.unit) or unit_scale(rq.unit) is None or rq.unit.dim is None:
                return
            spots[(leaf.start, leaf.end)] = rq
            if unit_scale(rq.unit) != 1:
                traced.append((leaf.start, leaf.end, rq))
        if not traced:
            return
        read = coefficient_free_dimension(computed, lambda _n: None,
                                          num_dim=lambda n: spots[(n.start, n.end)].unit.dim if (n.start, n.end) in spots else None)
        if read is None or not read.same_physical(target_node.unit.dim):
            return
        shown = ", ".join(f"{b.number.text} {b.unit.text}" for _a, _b, b in traced if b.unit is not None)
        self.relations.append(replace(rel, index=len(self.relations), kind="unit", companion_of=idx, unit_case="traced", traced=tuple(traced),
                                      reason=f"ST-UNIT-003: the numbers of the working repeat the request's quantities stated in non-SI units "
                                             f"({shown}); this companion reads them in those units"))

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
        operands, positive = self._exp_reading(operands)
        first, last = _first(operands[0][0]), _first(operands[-1][0])
        if first is None or last is None or chain.lead == "label":
            self.prev_rel = None
            return
        rel_op = "=" if all(o == "=" for o in ops) else next((o for o in ops if o in _ORDER), ops[0])
        unknown = {n for n in _syms(first) | _syms(last) if not (n in bound_before and self.scope.is_given(n))}
        info = {"left": operands[0][0], "op": rel_op, "right": operands[-1][0], "sid": operands[0][1], "sids": tuple(dict.fromkeys(s for _o, s in operands)),
                "unknown": unknown, "syms": _syms(first) | _syms(last), "item": item, "lone": lone, "head": head, "order": self.order.get(item.statement_id, 0),
                "connective": chain.connective, "is_formula": lone and isinstance(head, Sym) and bool(_syms(last) - {getattr(head, "name", "")}),
                "positive": positive}
        # roots: x = value (or a closed expression) after an equation in x
        if lone and isinstance(head, Sym) and rel_op == "=" and len(operands) >= 2:
            rhs = _first(operands[1][0])
            solved = head.name not in bound_before or not self.scope.is_given(head.name)
            if rhs is not None and is_closed(rhs) and solved:
                self._roots_candidate(item, chain, head, operands)
        prev = self.prev_rel
        if prev is None and not self.request_mode and lone and isinstance(head, Sym) and rel_op == "=" and info["unknown"]:
            # the answer's first line states the operation it applies to the request's own equation ("Solve 2x = 8." then
            # "Subtracting 4 from both sides gives x = 8 − 4 = 4"): that equation is the line the operation is applied to
            req = self._request_equation(info["unknown"])
            if req is not None and any(rx.search(item.gap_before or "") for _n, rx in _OPERATION_RES):
                l_op, r_op = req
                syms = _syms(_first(l_op)) | _syms(_first(r_op))
                prev = {"left": l_op, "op": "=", "right": r_op, "sid": "request", "sids": ("request",), "unknown": syms & info["unknown"] or syms,
                        "syms": syms, "item": item, "lone": False, "head": None, "order": info["order"] - 1, "connective": "", "is_formula": False,
                        "positive": ()}
                self._step(item, prev, info, operands, rel_op, True)
                prev = None
        if prev is not None and info["unknown"] and prev["unknown"] and prev["item"].part == item.part and rel_op != "≠" and prev["op"] != "≠":
            # a stated operation before the line ("Dividing by x, x² = 4") says it is a step from the line before as plainly as "so"
            explicit = chain.connective in ("⇒", "∴") or any(w in chain.connective.split() for w in ("so", "hence", "therefore", "thus", "gives")) \
                or _has_step_word(item.gap_before) or (len(item.gap_before or "") <= 240 and any(rx.search(item.gap_before or "") for _n, rx in _OPERATION_RES))
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
                or (lone and isinstance(head, Apply) and is_closed(head.arg)) \
                or is_closed(self._function_application(head) or Sym("?"))  # f(2) = …, N(15) = … evaluate a function: no step
            if shares and not evaluation and not or_joined and not new_formula and ((explicit and (same_span or info["order"] - prev["order"] <= 1)) or (adjacent and pure)):
                if _has_func_of(_first(prev["left"]) or Sym("?"), prev["unknown"]) or _has_func_of(_first(prev["right"]) or Sym("?"), prev["unknown"]) \
                        or _has_func_of(first, info["unknown"]) or _has_func_of(last, info["unknown"]):
                    self._undecided("ST-UNDEC-001", "a step involving a function of an unknown",
                                    dict(statement_ids=tuple(dict.fromkeys(prev["sids"] + info["sids"])), start=operands[0][0].start, end=operands[-1][0].end,
                                         op=rel_op, left=operands[0][0], right=operands[-1][0], part=item.part, position=0, approx=False), item)
                elif self._applies_function(_first(prev["left"]), _first(prev["right"]), *(_first(op) for op, _s in operands)):
                    # N(t + 1) = 2N(t), then N(t + 2) = 4N(t): the parser reads each application as a product (N·(t + 2)), which
                    # no step may be decided on; an equality that applies a model is checked by itself (stem-mod)
                    self._undecided("ST-UNDEC-001", "a step involving an application of a function the text defines (its letter glued to a "
                                    "bracket, read as the function only in a model evaluation)",
                                    dict(statement_ids=tuple(dict.fromkeys(prev["sids"] + info["sids"])), start=operands[0][0].start, end=operands[-1][0].end,
                                         op=rel_op, left=operands[0][0], right=operands[-1][0], part=item.part, position=0, approx=False), item)
                else:
                    self._premise_substitution(item, prev, operands)
                    self._step(item, prev, info, operands, rel_op, explicit)
        # equations remembered for roots ('v = 3.0 m s⁻¹' binds v: it is no equation whose solutions follow)
        if rel_op == "=" and unknown and not (lone and isinstance(head, Sym) and is_closed(last)):
            self.equations.append(info)
        self.prev_rel = info

    @staticmethod
    def _exp_reading(operands: list[tuple[Operand, str]]) -> tuple[list[tuple[Operand, str]], tuple[str, ...]]:
        """A relation in which one unknown appears only in powers of e with integer multiples of it of one sign
        (``800 = 1600 e^(−8k)``, ``e^(−8k) = 1/2``) is read in ``u = e^(−k)``: ``e^(−8k)`` is ``u⁸``, an exact change of
        variable (every real k gives one u > 0 and back), so a step between two such relations is an algebra step in u,
        with ``u > 0``. Any other relation is returned as it is (its powers of e stay outside the encodings)."""
        nodes = [op.readings[0] for op, _sid in operands if op.readings]
        if len(nodes) != len(operands) or len(operands) < 2:
            return operands, ()
        names: set[str] = set()
        signs: set[int] = set()
        for node in nodes:
            for n in walk(node):
                k = _exp_unknown(n)
                if k is None:
                    continue
                names.add(k)
                c = _integer_multiple(n.arg, k)  # type: ignore[union-attr]
                signs.add(1 if c and c > 0 else -1)
        if len(names) != 1 or len(signs) != 1:
            return operands, ()
        name, sign = next(iter(names)), next(iter(signs))
        u = Sym(f"e^({'' if sign > 0 else '−'}{name})")
        out: list[tuple[Operand, str]] = []
        for (op, sid), node in zip(operands, nodes):
            new = _exp_rewrite(node, name, sign, u)
            if new is None:
                return operands, ()
            out.append((Operand((new,), op.start, op.end, op.error, op.code), sid))
        return out, (u.name,)

    def _premise_substitution(self, item: MathItem, prev: dict, operands: list[tuple[Operand, str]]) -> None:
        """A line that writes the preceding relation's right side with values put in for its symbols ("1/R = 1/R₁ + 1/R₂",
        then "1/R = 1/4.0 Ω + 1/6.0 Ω"): the written values are read for those symbols (substitution readings, as a
        substitution inside one chain reads them), so the step is checked with the values the answer substitutes, never
        for every value the symbols could take. A symbol the answer binds keeps its bindings."""
        pr = _first(prev["right"])
        cr = _first(operands[1][0]) if len(operands) > 1 else _first(operands[-1][0])
        if pr is None or cr is None or is_closed(pr):
            return
        pairs = align(pr, cr)
        if not pairs:
            return
        sid = item.statement_id
        for s, n in pairs:
            if not isinstance(s, Sym) or isinstance(n, Sym) or not is_value(n) or self.scope.is_bound(s.name):
                continue
            v = value_of(n)
            if v is not None and v[1] is not None:
                self.scope.add(Binding(s.name, v[0], v[1], v[2], "substitution", sid, getattr(n, "start", 0), getattr(n, "end", 0), wrapper=v[3]))

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
                if rel_op == "=" and prev["op"] == "=":
                    self._stated_operation(item, prev, left_op, right_op, sids, unknown, note_only=True)
                return
        kind = "cmp" if (rel_op in _ORDER or prev["op"] in _ORDER) else "alg"
        positive = tuple(dict.fromkeys(tuple(prev.get("positive", ())) + tuple(info.get("positive", ()))))
        self.add(kind=kind, outcome="check", statement_ids=sids, start=left_op.start, end=right_op.end, op=rel_op, left=left_op, right=right_op,
                 premise_left=prev["left"], premise_op=prev["op"], premise_right=prev["right"], premise_ids=prev["sids"], explicit=explicit, part=item.part,
                 principal_root=principal, positive=positive,
                 reason="the step follows from the preceding relation" + (" (stated with a connective)" if explicit else " (consecutive lines)")
                 + ("; the principal (non-negative) root is taken" if principal else "")
                 + ("; read in " + ", ".join(f"{n} > 0" for n in positive) + " (each power of e of the unknown is a power of it)" if positive else ""))
        if kind == "alg" and rel_op == "=" and prev["op"] == "=":
            self._stated_operation(item, prev, left_op, right_op, sids, unknown)

    def _binary_operand(self, op: Operand) -> Operand:
        """In Computer Science, a numeral of 0s and 1s (four digits or more) that the request or the answer names as binary
        ("Convert the binary number 11010110 to denary", "11010110 in binary") is that binary numeral, not the denary
        number its digits would spell: the operand is read as the based numeral (exact), so the relation it stands in is
        checked as a base conversion."""
        if len(op.readings) != 1 or not isinstance(op.readings[0], Num):
            return op
        num = op.readings[0].number
        digits = num.text.strip()
        named = self._binary_literals()
        if num.based or num.base != 10 or not _BINARY_DIGITS_RE.fullmatch(digits) or digits not in named:
            return op
        based = exact_based(f"{digits}₂", digits, 2)
        if based is not None and named[digits] == "twos" and digits[0] == "1":
            # a two's complement pattern: the leading 1 weighs −2ⁿ⁻¹ ('10110110' is −74), read exactly
            based = replace(based, text=f"{digits}₂ (two's complement)", value=based.value - (1 << len(digits)))
        return Operand((Num(based, op.readings[0].start, op.readings[0].end),), op.start, op.end) if based is not None else op

    def _binary_literals(self) -> dict[str, str]:
        """The 0-and-1 numerals the request or the answer calls binary (``"unsigned"``) or a two's complement number
        (``"twos"``, which wins when a text calls it both), cached per document."""
        cached = getattr(self, "_binary_cache", None)
        if cached is None:
            text = (self.request.text[:20000] + "\n" + self.answer_text[:100_000])
            cached = {m.group(1) or m.group(2): "unsigned" for m in _BINARY_NAMED_RE.finditer(text)}
            cached.update({m.group(1) or m.group(2): "twos" for m in _TWOS_NAMED_RE.finditer(text)})
            self._binary_cache = cached
        return cached

    def _request_equation(self, unknown: set[str]) -> Optional[tuple[Operand, Operand]]:
        """The request's one equation in the given unknowns (``Solve 2x = 8``), or None when it states none or several."""
        found = []
        for l_op, op, r_op in self.request.relations:
            ln, rn = _first(l_op), _first(r_op)
            if op != "=" or ln is None or rn is None:
                continue
            if (_syms(ln) | _syms(rn)) & unknown:
                found.append((l_op, r_op))
        return found[0] if len(found) == 1 else None

    def _operand_at(self, item: MathItem, a: int, b: int, text: str) -> Optional[Node]:
        """The operand of a stated operation, written at ``[a, b)`` in prose: a value read there (a prose value), or one
        symbol the answer uses (``dividing by x``); None for anything else (nothing is guessed)."""
        vals = [pv for pv in self.prose_values if pv.statement_id == item.statement_id and a <= pv.start and pv.end <= b]
        if len(vals) == 1 and not text[: vals[0].start - a].strip() and not text[vals[0].end - a:].strip():
            return vals[0].node
        word = text.strip()
        if 1 <= len(word) <= 3 and word.isalpha() and word.isascii():
            return Sym(word, "symbol", a, b)
        return None

    def _stated_operation(self, item: MathItem, prev: dict, left_op: Operand, right_op: Operand, sids: tuple[str, ...], unknown: set[str], *,
                          note_only: bool = False) -> None:
        """ST-STEP-001: the prose before a step states the operation applied to the preceding equation ("adding 4 to both
        sides gives …", "dividing both sides by 2", "squaring both sides"): an ``op`` check (decided by the engine as an
        identity: the stated operation applied to each side of the preceding equation must give the next line's sides, in
        either order, for every value of the unknowns). ST-STEP-002 (info) records a division by an expression of the
        unknown that the answer states no guard for: a solution where it is zero may be lost (the step's own check decides
        whether the solution sets differ)."""
        gap = item.gap_before
        if not gap or len(gap) > 240:
            return
        hits = [(name, m) for name, rx in _OPERATION_RES for m in [rx.search(gap)] if m is not None]
        if len(hits) != 1:
            return  # no stated operation, or several (only one is read; a combined one is not guessed)
        name, m = hits[0]
        gap_start = _gap_start(item)
        arg: Optional[Node] = None
        if name != "sq":
            ka, kb = m.span("k")
            arg = self._operand_at(item, gap_start + ka, gap_start + kb, m.group("k"))
            if arg is None:
                return
        phrase = " ".join(m.group(0).split())
        if name == "div" and arg is not None and _syms(arg) & unknown:
            context = (item.context() + " " + prev["item"].context() + " " + self._request_lower)
            if not any(c in context for c in _NONZERO_CUES):
                self.finding("ST-STEP-002", f"the step '{phrase}' divides by {render(arg)}, an expression of the unknown, and no '{render(arg)} ≠ 0' is "
                                            f"stated: a solution where it is zero may be lost (stem_invalid_step; the step's own check decides whether "
                                            f"the solution sets differ)", sids, left_op.start, right_op.end)
        if note_only:
            return
        self.add(kind="op", outcome="check", statement_ids=sids, start=left_op.start, end=right_op.end, op="=", left=left_op, right=right_op,
                 premise_left=prev["left"], premise_op=prev["op"], premise_right=prev["right"], premise_ids=prev["sids"], part=item.part, explicit=True,
                 operation=name, operation_arg=arg, operation_text=phrase,
                 reason=f"ST-STEP-001: the stated operation '{phrase}' applied to the preceding equation must give the next line")

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
        """The symbol is the one unknown of an equation of the answer, or of the request's own equation of degree two or more
        (whose roots the answer states: 'Solve 2x² − 3x − 1 = 0', then 'x = … or x = …')."""
        if any(name in eq["unknown"] and len(eq["unknown"]) == 1 for eq in self.equations[-8:]):
            return True
        for l_op, op, r_op in self.request.relations[:16]:
            ln, rn = _first(l_op), _first(r_op)
            if op == "=" and ln is not None and rn is not None and (_syms(ln) | _syms(rn)) == {name} and max(_degree(ln, name), _degree(rn, name)) >= 2:
                return True
        return False

    def _roots_candidate(self, item: MathItem, chain: Chain, head: Sym, operands: list[tuple[Operand, str]]) -> None:
        root = _first(operands[1][0])
        if root is None or not is_closed(root):
            return
        x = head.name
        eq = None
        for cand in reversed(self.equations[-12:]):
            if cand["unknown"] == {x} and cand["item"].part == item.part:
                l, r = _first(cand["left"]), _first(cand["right"])
                # an equation of degree two or more, or one that carries '±' (two equations: 'x − 1 = ±2' has the roots 3
                # and −1; repair round 5, rerun-stem-soundness-10 variant)
                if l is not None and r is not None and (max(_degree(l, x), _degree(r, x)) >= 2
                                                        or any(isinstance(n, PlusMinus) for side in (l, r) for n in walk(side))):
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
        order = self.order.get(sid, 0)
        group = self._root_groups
        key = (sid, x)
        stmt_text = item.context()
        complete_phrase = any(p in stmt_text for p in _COMPLETE_PHRASES)
        restricted = any(w in stmt_text for w in _RESTRICT_WORDS) or self.request.restricts_domain
        # a root the statement calls one of several claims no full set, however the line is laid out or the request is worded
        partial = not complete_phrase and any(p in stmt_text for p in _PARTIAL_ROOT_PHRASES)
        # bare values that continue the stated set ('x = 0, 2 or −2'); a continuation this reading cannot take as a plain number
        # leaves the set read in part, so its completeness is never claimed (it would be decided on members the answer did not state)
        members, listed, unread = self._listed_members(item, operands[1][0].end)
        if members:
            self._listed_root_extents.add((operands[1][0].start, operands[1][0].end))
        stated_end = max([operands[1][0].end] + [getattr(m, "end", 0) for m in members])     # the set's extent, its listed members included
        eq_key = (x, tuple(eq["sids"]))
        last = self._root_lines.get(eq_key)
        if key not in group and last is not None and last[0] == order - 1:
            group[key] = last[1]  # consecutive root lines of one equation state one set ('x = 2' on a line, 'x = −2' on the next)
        if source == "answer" and self.profile.is_mathematics:
            self._division_note(item, x, root)
        if key in group:
            idx = group[key]
            rel = self.relations[idx]
            if unread:
                self._unread_root_sets.add(idx)
            new = replace(rel, roots=rel.roots + (root,) + members, end=max(rel.end, stated_end),
                          statement_ids=tuple(dict.fromkeys(rel.statement_ids + (sid,))),
                          complete=(rel.complete or chain.connective in ("or", "and") or "or" in item.gap_before.lower().split() or listed)
                          and not restricted and not partial and idx not in self._unread_root_sets)
            self.relations[idx] = new
            self._root_lines[eq_key] = (order, idx)
            return
        # in Mathematics a root line written right after its equation (on the next line, or after a step such as 'dividing by x')
        # answers it, so it claims the full set, as '⇒' does: 'x² = 3x', then 'Dividing by x, x = 3' loses the root x = 0
        next_line = (self.profile.is_mathematics and source == "answer" and order - int(eq.get("order", -9)) == 1 and eq["item"].part == item.part
                     and _opens_statement(item))
        # in Mathematics a root stated for a request that asks to solve the equation (or for all its values, solutions or roots)
        # is the answer's solution set: 'Solve the equation.' answered by 'x² = 4^{1.5}, so x = 2√2' loses the root −2√2
        concluded = self.profile.is_mathematics and bool(_SOLVE_REQUEST_RE.search(self._request_lower))
        complete = (complete_phrase or chain.connective in ("∴", "⇒") or next_line or concluded or listed) and not restricted and not partial and not unread
        rel = self.add(kind="sol", outcome="check", statement_ids=tuple(dict.fromkeys(eq["sids"] + (sid,))) if source == "answer" else (sid,),
                       start=operands[0][0].start, end=stated_end, op="=", left=operands[0][0], right=operands[1][0], part=item.part,
                       premise_left=eq["left"], premise_op="=", premise_right=eq["right"], premise_ids=eq["sids"], root_symbol=x, roots=(root,) + members,
                       complete=complete, restricted=restricted,
                       reason=f"stated roots of the equation in {', '.join(eq['sids'])}" + ("; the full solution set is claimed" if complete else "")
                       + (" (the root line follows its equation directly)" if next_line and not complete_phrase else "")
                       + ("; the stated set goes on with a value not read as a plain number, so no full set is claimed" if unread else "")
                       + ("; the statement calls the root one of several, so no full set is claimed" if partial else ""))
        if unread:
            self._unread_root_sets.add(rel.index)
        group[key] = rel.index
        self._root_lines[eq_key] = (order, rel.index)

    def _listed_members(self, item: MathItem, end: int) -> tuple[tuple[Node, ...], bool, bool]:
        """The bare values that continue a stated root in its statement, after its first member: 'x = 0, 2 or −2' gives 2 and
        −2, 'x = 2 or 3' gives 3, 'x = 1, ±2' gives 2 and −2. Returns the members, whether a separator was 'or' or 'and' (a
        set stated as alternatives, read as the full set, as 'x = 2 or x = 3' is), and whether the list goes on with a value
        this reading cannot take as a plain number ('x = 0, 2√2', 'x = 4, 3 s.f.'): the set is then read in part, and the
        caller claims no full set. Bounded: one scan of at most 200 characters and eight members."""
        text = item.statement_text
        off = end - item.statement_start
        if off < 0 or off >= len(text):
            return (), False, False
        tail = text[off:off + 200]
        members: list[Node] = []
        listed = False
        i = 0
        while len(members) < 8:
            m = _MEMBER_SEP_RE.match(tail, i)
            if m is None:
                break
            j = m.end()
            sign = tail[j] if j < len(tail) and tail[j] in "-+±" else ""
            k = j + len(sign)
            while sign and k < len(tail) and tail[k] in " \t":
                k += 1
            if not (k < len(tail) and is_ascii_digit(tail[k])):
                if sign:
                    return (), False, True          # a sign with no numeral after it: not a plain value
                break                               # no bare value follows ('x = 3, so y = 9'): the set ends at the root
            scan = scan_number(tail, k, limits=self.lim)
            if scan is None or scan.number is None or _MEMBER_END_RE.match(tail, scan.end) is None:
                return (), False, True              # '2√2', '2x', '3 s.f.': a value this reading does not take
            a, b = item.statement_start + off + k, item.statement_start + off + scan.end
            num: Node = Num(scan.number, a, b)
            if sign == "-":
                members.append(Neg(num, item.statement_start + off + j, b))
            elif sign == "±":
                members.extend((num, Neg(num, item.statement_start + off + j, b)))
            else:
                members.append(num)
            listed = listed or bool(re.search(r"\b(?:or|and)\b", m.group(0)))
            i = scan.end
        return tuple(members), listed, False

    def _division_note(self, item: MathItem, x: str, root: Node) -> None:
        """ST-STEP-002 (info) for a root line whose stated step divides by the unknown ('Dividing by x, x = 3') with no guard:
        the root where the divisor is zero may be lost; the root check (stem-sol) decides whether the set is complete."""
        gap = item.gap_before
        rx = dict(_OPERATION_RES)["div"]
        m = rx.search(gap) if gap and len(gap) <= 240 else None
        if m is None:
            return
        arg = m.group("k").strip()
        if arg != x and not (len(arg) <= 12 and x in arg):
            return
        context = item.context() + " " + self._request_lower
        if any(c in context for c in _NONZERO_CUES):
            return
        self.finding("ST-STEP-002", f"the step '{' '.join(m.group(0).split())}' divides by {arg}, an expression of the unknown, and no '{arg} ≠ 0' is "
                                    f"stated: a solution where it is zero may be lost (stem_invalid_step; the root check decides whether the stated set "
                                    f"is complete)", (item.statement_id,), item.start, item.end)

    def _root_set_members(self) -> None:
        """``x² = 4 ⇒ x = −2 or x = 2`` (or the same set over two lines): the connective binds the equation to the whole
        stated root set, but the chain reading takes it for a step to its first member alone, which a square-root step
        checks under the principal-root condition ``x ≥ 0``, so the verdict hung on the order the roots were written in.
        Once a root set of two or more members is recognised (``stem-sol``, which checks every member against the
        equation and, when the full set is claimed, that the equation has no other root), a step from that equation to one
        member is that set read one member at a time: it is recorded as context (``case``), not checked on its own, and
        its ST-ALG-001 note (only the non-negative root taken) is withdrawn, because the statement does state the other
        root. The same set therefore gets the same checks in any order (``x = 2 or x = −2``, ``x = ±2``).

        A step to a root that bare members follow (``x(x² − 4) = 0, so x = 0 or x² = 4, giving x = 0, 2 or −2``) concludes
        the stated set, not its first value, whichever equation the step is read from: checked on the first value alone
        (``x² = 4`` to ``x = 0``) it failed on correct work. It is context too when its set is checked as a whole; a wrong
        member still fails that set's check."""
        sets = [s for s in self.relations if s.kind == "sol" and s.outcome == "check" and len(s.roots) >= 2 and s.root_symbol]
        if not sets:
            return
        # the steps that conclude 'symbol = closed value' from an equation, keyed once (few; each key one canonical render)
        steps: list[tuple[int, Relation, str, str, frozenset[str]]] = []
        for idx, rel in enumerate(self.relations):
            if rel.kind not in ("alg", "cmp") or rel.outcome != "check" or rel.op != "=":
                continue
            cl, cr = _first(rel.left), _first(rel.right)
            pl, pr = _first(rel.premise_left), _first(rel.premise_right)
            if isinstance(cl, Sym) and cr is not None and is_closed(cr) and pl is not None and pr is not None:
                steps.append((idx, rel, cl.name, shape_key(cr), frozenset({shape_key(pl), shape_key(pr)})))
        # every checked step of the answer as (premise sides, conclusion sides, part, statements): the relations a chain derives
        # from a root set's equation
        derivations: list[tuple[frozenset[str], frozenset[str], str, frozenset[str]]] = []
        for rel in self.relations:
            if rel.kind != "alg" or rel.outcome != "check":
                continue
            pl, pr, cl, cr = _first(rel.premise_left), _first(rel.premise_right), _first(rel.left), _first(rel.right)
            if None not in (pl, pr, cl, cr):
                derivations.append((frozenset({shape_key(pl), shape_key(pr)}), frozenset({shape_key(cl), shape_key(cr)}), rel.part,
                                    frozenset(rel.statement_ids)))
        for sol in sets:
            members = {shape_key(r) for r in sol.roots}
            eq_keys = frozenset(shape_key(n) for n in (_first(sol.premise_left), _first(sol.premise_right)) if n is not None)
            # the equation, and every relation the chain derives from it in the set's own statements: a step from one of them to a
            # member is the set read one member at a time too ('(x − 1)² = 4 ⇒ x − 1 = ±2 ⇒ x = 3 or x = −1': the step 'x − 1 =
            # ±2 ⇒ x = 3' takes one sign; repair round 5, rerun-stem-soundness-10 variant). Each derived relation keeps its own step
            # check, and every member is checked against the equation by stem-sol.
            reach = {eq_keys}
            grew = True
            while grew and len(reach) <= len(derivations):
                grew = False
                for pk, ck, part, sids in derivations:
                    if pk in reach and ck not in reach and part == sol.part and sids & set(sol.statement_ids):
                        reach.add(ck)
                        grew = True
            for idx, rel, name, member, premise in steps:
                listed_target = rel.right is not None and (rel.right.start, rel.right.end) in self._listed_root_extents
                if name != sol.root_symbol or member not in members or (premise not in reach and not listed_target) or rel.part != sol.part \
                        or not set(rel.statement_ids) & set(sol.statement_ids) or self.relations[idx].outcome != "check":
                    continue
                self.relations[idx] = replace(rel, kind="case", outcome="context", principal_root=False,
                                              reason=f"one member of the root set stated for {sol.root_symbol} ({', '.join(render(r) for r in sol.roots)}); the set "
                                                     f"is checked as a whole by stem-sol (each member, and the full set when it is claimed), so this member "
                                                     f"is not checked on its own as a step")
                tag = f"#{idx}"
                self.findings = [f for f in self.findings if not (f.code == "ST-ALG-001" and f.check_id == tag)]

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
        lv, rv = _syms(br.left), _syms(br.right)
        if bool(lv) != bool(rv) and not isinstance(br.left if lv else br.right, Sym):
            # a substitution link of an evaluation chain ('NOT (A AND B) = NOT (1 AND 0)'): no identity, so it is checked with
            # the 0/1 values the request or the answer states for its letters ('Using A = 1 and B = 0'), the letters replaced
            # by those values; with a letter that has no stated value it is context, not checked (repair round 2)
            side = br.left if lv else br.right
            values = self._boolean_values(lv | rv)
            if values is None:
                self.add(kind="formula", outcome="context", statement_ids=(item.statement_id,), start=br.start, end=br.end, op=br.op, part=item.part,
                         left=Operand((br.left,), br.start, br.end), right=Operand((br.right,), br.start, br.end),
                         reason="a substitution step of a Boolean chain whose letters have no stated 0/1 values")
                return
            put = _substitute_bits(side, values)
            br = replace(br, left=put, right=br.right) if lv else replace(br, left=br.left, right=put)
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

    def _boolean_values(self, names: set[str]) -> Optional[dict[str, int]]:
        """The 0/1 value the answer or the request binds to each of ``names`` (one value each), or None when one has none
        or two different ones."""
        out: dict[str, int] = {}
        for name in names:
            seen: set[Fraction] = set()
            for b in list(self.scope.bindings.get(name, ())) + [b for b in self.request.bindings if b.symbol == name]:
                seen.add(b.value)
            if len(seen) != 1 or next(iter(seen)) not in (0, 1):
                return None
            out[name] = int(next(iter(seen)))
        return out

    def _table(self, item: MathItem) -> None:
        t = item.table
        if t is None:
            return
        sids = tuple(dict.fromkeys((item.statement_id,) + item.cover_ids))  # every row of the table
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
        """A prose value after a result cue restates the last chain before it in its part ("… = 6.0 m s⁻². The acceleration
        is therefore 6.0 m s⁻²."): checked against that chain's final value when the chain computes it. The last chain may
        stand in the value's own statement, before it ("= 25.9%, so about 26%", also inside a quotation): that chain, not an
        older one, is what the value restates. When the last chain before the value states no value (it ends on an order
        relation: "… > 6000, so the answer is 12 years") or only states one for a symbol ("mid = 4"), the prose value restates
        nothing a chain computed, and no older chain is reached for instead. A restatement is of the same quantity: values
        with units have units of one dimension, and a value written in the units of a named scale ("a fall of 0.1 pH unit")
        restates only a value in that scale. A value of the other sign than its own statement's chain ("= −5.0 m s⁻², so the
        deceleration is 5.0 m s⁻²"; "= −9.0 J, so friction does 9.0 J of work against the motion") states the magnitude, in
        the words of a direction, and is not read as a restatement of the signed value (close round 1, ADV6-02); a chain of an
        earlier statement is read as before."""
        for pv in self.prose_values:
            if not _result_cue(pv.before):
                continue
            v = value_of(pv.node)
            if v is None:
                continue
            best = None
            last_chain = next((e for order, part, e, end in reversed(self.chain_ends)
                               if (order < pv.statement_index or (order == pv.statement_index and end <= pv.start))
                               and not (pv.part and part and pv.part != part)), None)
            for fv in reversed(self.final_values):
                if fv is not last_chain or not fv.get("computed", True):
                    continue
                if fv["order"] > pv.statement_index or (fv["order"] == pv.statement_index and fv["operand"].end > pv.start):
                    continue
                if pv.part and fv["part"] and pv.part != fv["part"]:
                    continue
                fvv = value_of(fv["node"])
                if fvv is None:
                    continue
                if fv["order"] == pv.statement_index and (fvv[0] < 0) != (v[0] < 0) and fvv[0] != 0 and v[0] != 0:
                    break  # its own chain's value of the other sign: the prose states a magnitude, no restatement of the signed value
                if v[2] is not None and fvv[2] is not None:
                    d1, d2 = v[2].dim, fvv[2].dim
                    if d1 is None or d2 is None:
                        # a unit the table does not know ('kJ m⁻² yr⁻¹') pairs only with the same unit written the same way
                        if d1 is not None or d2 is not None or " ".join(v[2].text.split()) != " ".join(fvv[2].text.split()):
                            continue
                    elif not d1.same_physical(d2):
                        continue
                if self._scale_after(pv.end) != self._scale_after(fv["operand"].end):
                    continue  # '0.1 pH unit' is a step on the pH scale, not the restated 25.9% of a chain
                best = fv
                break
            if best is None:
                continue
            self.add(kind="res", outcome="check", statement_ids=tuple(dict.fromkeys((best["sid"], pv.statement_id))), start=pv.start, end=pv.end, op="=",
                     left=best["operand"], right=Operand((pv.node,), pv.start, pv.end), part=pv.part,
                     reason=f"a prose restatement against the final value of the chain in {best['sid']}")

    def _described_roots(self) -> None:
        """A value the answer states in prose for a quantity it named by a symbol ('Let $M$ be the monthly payment in
        euros.', then 'Her monthly payment is €352.19.') is the root it states for an equation in that symbol: the latest
        equation before it, in the same part, whose one unknown is the symbol (``18 000 = M × (1 − 1.0054…^−60)/0.0054…``).
        Checked like any stated root (``stem-sol``, membership; R10: a root of the equation lies in the value's rounding
        interval). Read only when every condition holds, so a misreading never decides anything:

        * the clause that states the value is the description itself, with at most a connective and a determiner or
          possessive before it, a verb of identity and a currency sign after it ('Her monthly payment is €', '…, so the
          monthly payment is'), its sentence opens with no condition ('If …', 'When …'), and nothing follows the value but
          a currency, time or count word, a rounding note or a mark annotation up to the end of its sentence (no
          qualifier, no negation, no comparison);
        * the description is the one the answer gave the symbol earlier in the same part (or with no part), word for word;
        * the value is a decimal (a whole number in prose may be a count the context rounds up or down) with no unit,
          the symbol has no value stated in maths anywhere in the answer, and the equation, written before the value,
          holds no unit, no sign choice, no construct outside the encodings and no function of the unknown."""
        if not self.named:
            return
        for pv in self.prose_values:
            num = pv.node.arg if isinstance(pv.node, Neg) else pv.node
            if not isinstance(num, Num) or num.number.based or not num.number.has_point:
                continue  # a plain decimal (or one with a minus sign): no unit, no per cent; a whole number in prose may be a count
                # the context rounds up or down ('16 tickets' for 15.3), so it is never read as a root
            cut = max(pv.before.rfind("."), pv.before.rfind(";"), pv.before.rfind(":"), pv.before.rfind("\n"), pv.before.rfind("?"), pv.before.rfind("!"))
            sentence = pv.before[cut + 1:]
            if _CONDITIONAL_RE.match(sentence):
                continue  # 'If the rate is 5%, the monthly payment is €400.50': a value under a condition
            clause = sentence[sentence.rfind(",") + 1:]  # '…, so the monthly payment is €': the clause that states the value
            m = _DESCRIBED_VALUE_RE.match(clause)
            if m is None:
                continue
            stop = _SENTENCE_STOP_RE.search(pv.after)
            if not _DESCRIBED_TAIL_RE.match(pv.after[:stop.end()] if stop is not None else pv.after):
                continue
            desc = " ".join(m.group("desc").lower().split())
            named = next((n for n in reversed(self.named) if n[0] < pv.statement_index and desc in n[3] and (n[1] == pv.part or not n[1])), None)
            if named is None:
                continue
            _order, _part, x, _variants, def_sid = named
            if self.scope.bindings.get(x) or self.scope.substitutions.get(x):
                continue  # a value stated in maths: the answer's own relations already read it
            eq = None
            for cand in reversed(self.equations):
                before_value = cand["order"] < pv.statement_index or (cand["order"] == pv.statement_index and cand["item"].end <= pv.start)
                if not before_value or cand["item"].part != pv.part or cand["unknown"] != {x}:
                    continue
                l, r = _first(cand["left"]), _first(cand["right"])
                if l is None or r is None or max(_degree(l, x), _degree(r, x)) < 1:
                    continue
                if any(isinstance(n, (Quantity, WithUnit, Percent, Degrees, PlusMinus)) for side in (l, r) for n in walk(side)):
                    break  # the latest equation in the symbol holds a unit or a sign choice: nothing is read
                if unsupported_reasons(l) or unsupported_reasons(r) or _has_func_of(l, {x}) or _has_func_of(r, {x}):
                    break
                eq = cand
                break
            if eq is None:
                continue
            a = pv.start - len(clause) + (len(clause) - len(clause.lstrip()))
            self.add(kind="sol", outcome="check", statement_ids=tuple(dict.fromkeys(eq["sids"] + (pv.statement_id,))), start=a, end=pv.end, op="=",
                     left=Operand((Sym(x, start=pv.start, end=pv.start),), pv.start, pv.start), right=Operand((pv.node,), pv.start, pv.end), part=pv.part,
                     premise_left=eq["left"], premise_op="=", premise_right=eq["right"], premise_ids=eq["sids"], root_symbol=x, roots=(pv.node,),
                     described=True,
                     reason=f"the value the answer states in {pv.statement_id} for '{desc}', the quantity it names {x} in {def_sid}: a stated root of the "
                            f"equation in {x} in {', '.join(eq['sids'])}")

    def _said_to_fail(self, end: int) -> bool:
        """The words right after a comparison say it does not hold: "(2 <= 1) fails", "2 <= 1 no, so …", "x > 5 is false"
        (a bounded, anchored match on at most 40 characters after it)."""
        return 0 <= end < len(self.answer_text) and _FAILS_RE.match(self.answer_text, end, min(len(self.answer_text), end + 40)) is not None

    def _scale_after(self, end: int) -> str:
        """The named scale a value is written in, from the word right after it ("0.1 pH unit" -> "pH"), else ''."""
        word = self.answer_text[end:end + 12].lstrip(" ").split(" ")[0].rstrip(".,;:)") if 0 <= end < len(self.answer_text) else ""
        return word if word in _SCALE_NAMES else ""

    def _assignments(self) -> None:
        """Computer Science: a trace step that gives a variable a value in prose ("mid = 1 gives 3 < 9, so low moves to 2")
        applies the update rule the answer states for that variable earlier in the part ("low = mid + 1"): when the step's
        own clause states a value for every other variable of the rule before it, the rule under the stated values is set
        against the value the step gives (a ``sub`` check that evaluates; some stated value of each variable must give it).
        A step whose clause states none ("the next middle item is 7, so low moves to 3") is not read."""
        if not self.profile.computer_science:
            return
        for pv in self.prose_values:
            m = _ASSIGN_STEP_RE.search(pv.before[-80:])
            if m is None or not is_value(pv.node):
                continue
            f = self.scope.formula_for(m.group(1))
            if f is None or f.params or unsupported_reasons(f.expr) or self.part_of.get(f.statement_id, "") != pv.part \
                    or self.order.get(f.statement_id, 0) > pv.statement_index:
                continue
            names = [n for n in _syms(f.expr) if not n.endswith("()")]
            cut = max(pv.before.rfind(";"), pv.before.rfind(":"), pv.before.rfind(". "))
            clause_start = pv.start - (len(pv.before) - cut - 1)
            starts = [min((b.start for b in self.scope.bindings.get(n, ()) if b.statement_id == pv.statement_id and clause_start <= b.start < pv.start),
                          default=-1) for n in names]
            if not names or min(starts) < 0:
                continue
            clause = pv.before[cut + 1:]
            a = clause_start + len(clause) - len(clause.lstrip())  # the step's clause: 'mid = 1 gives 3 < 9, so low moves to 2'
            self.add(kind="sub", outcome="check", evaluate=True, formula=f, statement_ids=tuple(dict.fromkeys((f.statement_id, pv.statement_id))),
                     start=a, end=pv.end, op="=", left=Operand((f.expr,), a, pv.end), right=Operand((pv.node,), pv.start, pv.end), part=pv.part,
                     reason=f"a trace step: the update rule of '{f.name}' stated in {f.statement_id} under the values its clause states, against the value "
                            f"the step gives")

    # -------------------------------------------------------------- systems of equations
    def _systems(self) -> None:
        """A statement that gives values to two or more unknowns ("so x = 5 and y = 3") after a system of equations in them
        (the answer's, in the same part and at most three statements before, or the request's): one ``sys`` check, every
        equation with every stated value put in. The steps from one equation to one of those values, which took the answer's
        other stated values as their premises, are recorded as context: the solution is checked as a whole, and the answer's
        own value of one unknown is never a premise for another."""
        stated: dict[str, list[tuple[str, Operand, int]]] = {}
        for rel in self.relations:
            if rel.kind != "binding" or rel.outcome != "binding" or rel.reason != "a value stated for a symbol":
                continue
            head, val = _first(rel.left), _first(rel.right)
            if isinstance(head, Sym) and head.kind == "symbol" and val is not None and is_value(val) and rel.right is not None:
                sid = rel.statement_ids[-1]
                if all(n != head.name for n, _o, _i in stated.get(sid, ())):
                    stated.setdefault(sid, []).append((head.name, rel.right, rel.index))
        for sid, vals in stated.items():
            names = {n for n, _o, _i in vals}
            if len(names) < 2:
                continue
            order = self.order.get(sid, 0)
            part = self.part_of.get(sid, "")
            eqs: list[tuple[Operand, str, Operand, tuple[str, ...]]] = []
            for info in self.equations:
                unk = set(info["unknown"])
                if info["op"] != "=" or not unk or not unk <= names or info["item"].part != part or not 0 <= order - int(info.get("order", -9)) <= 3:
                    continue
                if any(_has_func_of(n, unk) for n in (_first(info["left"]), _first(info["right"])) if n is not None):
                    continue
                eqs.append((info["left"], "=", info["right"], tuple(info["sids"])))
            if not eqs:
                for l_op, op, r_op in self.request.relations[:16]:
                    l, r = _first(l_op), _first(r_op)
                    if op == "=" and l is not None and r is not None and (_syms(l) | _syms(r)) and (_syms(l) | _syms(r)) <= names:
                        eqs.append((l_op, "=", r_op, ("request",)))
            covered = set().union(*(_syms(_first(a)) | _syms(_first(c)) for a, _op, c, _s in eqs)) if eqs else set()
            if len(eqs) < len(names) or covered != names or not any(len(_syms(_first(a)) | _syms(_first(c))) >= 2 for a, _op, c, _s in eqs):
                continue
            # the steps to one stated value from one equation of the system: context (checked as a whole below)
            eq_keys = [frozenset(shape_key(n) for n in (_first(a), _first(c)) if n is not None) for a, _op, c, _s in eqs]
            for idx, r in enumerate(self.relations):
                if r.kind not in ("alg", "cmp", "op") or r.outcome != "check" or sid not in r.statement_ids:
                    continue
                cl = _first(r.left)
                prem = frozenset(shape_key(n) for n in (_first(r.premise_left), _first(r.premise_right)) if n is not None)
                if isinstance(cl, Sym) and cl.name in names and prem in eq_keys:
                    self.relations[idx] = replace(r, outcome="context", kind="case",
                                                  reason="one value of the stated solution of the system; the solution is checked as a whole (stem-sys), "
                                                         "so no other stated value is taken as its premise")
            ops = [o for _n, o, _i in vals]
            sids = tuple(dict.fromkeys(tuple(x for _a, _o, _c, ss in eqs for x in ss if x != "request") + (sid,)))
            self.add(kind="sys", outcome="check", statement_ids=sids, start=min(o.start for o in ops), end=max(o.end for o in ops), op="=",
                     left=ops[0], right=ops[-1], part=part, equation_set=tuple((a, o, c) for a, o, c, _s in eqs),
                     values=tuple((n, o.node) for n, o, _i in vals if o.node is not None),
                     reason=f"the stated solution ({', '.join(n for n, _o, _i in vals)}) against every equation of the system")

    # -------------------------------------------------------------- named STEM diagnostics (section 24)
    def _rounding_comparisons(self) -> None:
        """ST-ROUND-001 (engine-decided): a comparison against a threshold ("0.25 s is not less than 0.25 s", or a stated
        order between values) uses a value the working itself rounded (the end of a chain '… = 0.246 s ≈ 0.25 s'). A ``rnd``
        check asks the engine whether the same comparison still holds with the value before the rounding; its failure is
        a warning (stem_rounding_changes_conclusion)."""
        self._worded_roundings()
        if not self.roundings:
            return
        planned: set[tuple[int, int]] = set()
        by_sid: dict[str, list[ProseValue]] = {}
        for pv in self.prose_values:
            by_sid.setdefault(pv.statement_id, []).append(pv)
        self._compared_roundings(planned)
        for sid, pvs in by_sid.items():
            for a_pv, b_pv in zip(pvs, pvs[1:]):
                gap = b_pv.start - a_pv.end
                if not 0 < gap <= 48 or gap > len(b_pv.before):
                    continue
                cmp = _prose_comparison(b_pv.before[len(b_pv.before) - gap:])
                if cmp is None:
                    continue
                op, negated = cmp
                for rounded, threshold, flip in ((a_pv, b_pv, False), (b_pv, a_pv, True)):
                    hit = self._rounded_source(rounded.node, rounded.part, rounded.statement_index)
                    if hit is None or (rounded.start, rounded.end) in planned:
                        continue
                    if _restates_unrounded(hit, threshold.node):
                        # the other side is the value before the rounding ("which rounds to 30 m s⁻¹; but 30.4 m s⁻¹ exceeds 30
                        # m s⁻¹"): the comparison is made with it, and the bound only equals the rounded value (accuracy round
                        # 2, V1I-04)
                        continue
                    planned.add((rounded.start, rounded.end))
                    use_op = _FLIP_ORDER.get(op, op) if flip else op
                    self.add(kind="rnd", outcome="check", statement_ids=tuple(dict.fromkeys((hit["sid"], sid))), start=a_pv.start, end=b_pv.end,
                             op=_IR_ORDER_SIGN[use_op], left=Operand((rounded.node,), rounded.start, rounded.end),
                             right=Operand((threshold.node,), threshold.start, threshold.end), premise_left=hit["u"], premise_right=hit["r"],
                             premise_ids=(hit["sid"],), part=rounded.part, explicit=negated,
                             reason=f"ST-ROUND-001: the comparison uses the value the working rounded in {hit['sid']}; it must keep its truth with the value "
                                    f"before the rounding")
                    break

    def _worded_roundings(self) -> None:
        """A rounding stated in words after a chain's result (repair round 2, ADV2-06): '= 0.694, which is 0.7 to one significant
        figure', '= 0.694. To 1 s.f. this is 0.7', '0.694 (0.69 to 2 d.p.)'. The prose value is a rounding of the chain's last
        value when the words name a rounding (significant figures or decimal places) right before or after it and the value is
        within half a unit of its last written digit of the chain's value, and differs from it; it is then recorded as the
        chain's rounding (the value before the rounding is the chain's value)."""
        if self.request_mode:
            return
        text = self.answer_text
        previous: Optional[ProseValue] = None
        for pv in self.prose_values[:512]:
            prev, previous = previous, pv
            before = pv.before[-48:].lower()
            after = text[pv.end:pv.end + 48].lower() if 0 <= pv.end <= len(text) else ""
            if not (_ROUNDING_WORDS_BEFORE_RE.search(before) or _ROUNDING_WORDS_AFTER_RE.match(after)):
                continue
            v = value_of(pv.node)
            if v is None or v[1] is None:
                continue
            source = self._prose_rounding_source(prev, pv, v)
            if source is not None:
                # the value rounded is the one the prose states right before it ('38.4 °C to the nearest whole number is 38 °C'):
                # recorded as that value's rounding (accuracy round 1, ADV6-05)
                self.roundings.append({"u": source, "r": Operand((pv.node,), pv.start, pv.end), "sid": pv.statement_id, "part": pv.part,
                                       "order": pv.statement_index, "symbol": "", "end": pv.end})
                continue
            if not self.final_values:
                continue
            last = next((e for e in reversed(self.final_values) if e.get("operand") is not None and e["operand"].end <= pv.start
                         and (not pv.part or not e.get("part") or e["part"] == pv.part)), None)
            if last is None or pv.start - last["operand"].end > 160:
                continue
            u = value_of(last["node"])
            if u is None or u[0] == v[0] or (u[2] is None) != (v[2] is None) or abs(u[0] - v[0]) > v[1].half_width:
                continue
            self.roundings.append({"u": last["operand"], "r": Operand((pv.node,), pv.start, pv.end), "sid": pv.statement_id, "part": pv.part,
                                   "order": pv.statement_index, "symbol": last.get("symbol", ""), "end": pv.end})

    def _prose_rounding_source(self, prev: Optional[ProseValue], pv: ProseValue, v: tuple) -> Optional[Operand]:
        """The value a rounding in prose rounds when the prose states it right before the rounded value, in the same
        statement and part, with only a rounding phrase between them (:data:`_PROSE_ROUNDING_BETWEEN_RE`: '38.4 °C to the
        nearest whole number is 38 °C', '13.3 A, which rounds to 13 A'), stated alike (both with a unit or both bare), not
        equal to it and within half a unit of the rounded value's last written digit; else None (accuracy round 1, ADV6-05)."""
        if prev is None or prev.statement_id != pv.statement_id or (prev.part or "") != (pv.part or "") or not 0 < pv.start - prev.end <= 64:
            return None
        text = self.answer_text
        if pv.start > len(text) or not _PROSE_ROUNDING_BETWEEN_RE.fullmatch(text, prev.end, pv.start):
            return None
        u = value_of(prev.node)
        if u is None or u[1] is None or u[0] == v[0] or (u[2] is None) != (v[2] is None) or u[3] != v[3]:
            return None
        if u[2] is not None and " ".join(u[2].text.split()) != " ".join(v[2].text.split()):
            return None
        if abs(u[0] - v[0]) > v[1].half_width:
            return None
        return Operand((prev.node,), prev.start, prev.end)

    def _compared_roundings(self, planned: set[tuple[int, int]]) -> None:
        """Comparisons of a rounded value written outside a prose pair (repair round 2, ADV2-06): a comparison in symbols
        ('Since 0.7 ≥ 0.70'), one of the symbol whose chain was rounded ('η = 0.694 ≈ 0.7, so η ≥ 0.70'), and a comparison
        clause right after the rounded value ('≈ 0.7, which is not less than 0.70'). Each is an ``rnd`` check like the prose one."""
        for rel in list(self.relations):
            if rel.kind != "cmp" or rel.outcome != "check" or rel.left is None or rel.right is None or rel.op not in _MATH_ORDER_OPS:
                continue
            for rounded_op, threshold_op, flip in ((rel.left, rel.right, False), (rel.right, rel.left, True)):
                rn, tn = _first(rounded_op), _first(threshold_op)
                if rn is None or tn is None or not is_value(tn):
                    continue
                order = self.order.get(rel.statement_ids[0], 0) if rel.statement_ids else 0
                if isinstance(rn, Sym):
                    hit = next((rd for rd in reversed(self.roundings) if rd.get("symbol") == rn.name and rd["order"] <= order
                                and (not rel.part or not rd["part"] or rd["part"] == rel.part)), None)
                    value_op = hit["r"] if hit is not None else None
                elif is_value(rn):
                    hit = self._rounded_source(rn, rel.part, order)
                    value_op = rounded_op
                else:
                    continue
                if hit is None or value_op is None or (value_op.start, value_op.end) in planned:
                    continue
                if _restates_unrounded(hit, tn):
                    continue  # compared with the value before the rounding (accuracy round 2, V1I-04)
                planned.add((value_op.start, value_op.end))
                op = _FLIP_MATH.get(rel.op, rel.op) if flip else rel.op
                self.add(kind="rnd", outcome="check", statement_ids=tuple(dict.fromkeys((hit["sid"], *rel.statement_ids))), start=rel.start, end=rel.end,
                         op=op, left=value_op, right=threshold_op, premise_left=hit["u"], premise_right=hit["r"], premise_ids=(hit["sid"],),
                         part=rel.part, explicit=False,
                         reason=f"ST-ROUND-001: the comparison uses the value the working rounded in {hit['sid']}; it must keep its truth with the value "
                                f"before the rounding")
                break
        text = self.answer_text
        for rd in self.roundings:
            end = rd.get("end", -1)
            if end < 0 or (rd["r"].start, rd["r"].end) in planned:
                continue
            nxt = next((pv for pv in self.prose_values if 0 < pv.start - end <= 48 and (not pv.part or not rd["part"] or pv.part == rd["part"])), None)
            if nxt is None or not is_value(nxt.node):
                continue
            between = text[end:nxt.start]
            between = between.lstrip(" ,")
            if between.lower().startswith("which "):
                between = between[6:]
            cmp = _prose_comparison(between, subject=True)
            if cmp is None:
                continue
            op, negated = cmp
            planned.add((rd["r"].start, rd["r"].end))
            self.add(kind="rnd", outcome="check", statement_ids=tuple(dict.fromkeys((rd["sid"], nxt.statement_id))), start=rd["r"].start, end=nxt.end,
                     op=_IR_ORDER_SIGN[op], left=rd["r"], right=Operand((nxt.node,), nxt.start, nxt.end), premise_left=rd["u"], premise_right=rd["r"],
                     premise_ids=(rd["sid"],), part=rd["part"], explicit=negated,
                     reason=f"ST-ROUND-001: the comparison uses the value the working rounded in {rd['sid']}; it must keep its truth with the value "
                            f"before the rounding")
        self._symbol_prose_comparisons(planned)
        self._target_roundings(planned)

    def _symbol_prose_comparisons(self, planned: set[tuple[int, int]]) -> None:
        """A comparison in prose whose subject is the symbol a chain rounded (repair round 3, ADV3-09): 'R = 2.0 + 1.96 = 3.96 ≈
        4.0 Ω. R is not below 4.0 Ω, so the component fails.' The clause before a stated value names the symbol and compares it
        (:func:`_prose_comparison`: "is not below", "is less than", "exceeds"); the symbol's value there is the rounded one, so
        the same ``rnd`` check as the other comparisons asks whether the statement keeps its truth with the value before the
        rounding. Read within the rounding's part, at most 400 characters after it; one check per rounding."""
        text = self.answer_text
        for rd in self.roundings:
            name = rd.get("symbol") or ""
            end = rd.get("end", -1)
            if not name or end < 0 or (rd["r"].start, rd["r"].end) in planned:
                continue
            for pv in self.prose_values:
                if pv.start <= end or pv.start - end > 400 or (pv.part and rd["part"] and pv.part != rd["part"]) or not is_value(pv.node):
                    continue
                head = text[max(end, pv.start - 64):pv.start]
                m = re.search(r"(?<![\w.])" + re.escape(name) + r"(?![\w'’])(?P<cmp>[^.;:!?\n=<>≤≥]{1,48})$", head)
                if m is None:
                    continue
                cmp = _prose_comparison(m.group("cmp"))
                if cmp is None:
                    continue
                op, negated = cmp
                planned.add((rd["r"].start, rd["r"].end))
                self.add(kind="rnd", outcome="check", statement_ids=tuple(dict.fromkeys((rd["sid"], pv.statement_id))), start=rd["r"].start, end=pv.end,
                         op=_IR_ORDER_SIGN[op], left=rd["r"], right=Operand((pv.node,), pv.start, pv.end), premise_left=rd["u"], premise_right=rd["r"],
                         premise_ids=(rd["sid"],), part=rd["part"], explicit=negated,
                         reason=f"ST-ROUND-001: the comparison of {name} uses the value the working rounded in {rd['sid']}; it must keep its truth with "
                                f"the value before the rounding")
                break

    def _target_roundings(self, planned: set[tuple[int, int]]) -> None:
        """A rounded value the answer says meets or misses a target (repair round 2, holdout2 rounding class): '= 78.96% ≈ 80%, so
        the target of at least 80% is met', '≈ 80%, which meets the 80% target', '≈ 0.7, so it does not reach the threshold'.
        The clause after the rounded value, up to the end of its sentence, names a target (``TARGET_NOUNS``) and says the value
        reaches it, goes beyond it or misses it (``TARGET_REACH_VERBS``, ``TARGET_EXCEED_VERBS``, ``TARGET_MISS_VERBS``, the
        passive "is met", a negation, "fails to", "falls short of"). The target's value is the one value the clause states
        beside the noun, else the one value the request states beside a target noun, with the bound written before it ("at
        least", "more than", ...: ``TARGET_BOUNDS``; none means at least). Reaching it is "value ≥ target" under that bound,
        missing it the negation, exceeding it "value > target". The same ``rnd`` check as the prose comparisons then asks
        whether the statement keeps its truth with the value before the rounding. A clause that names no target, no verb, or
        no single target value plans nothing."""
        text = self.answer_text
        for rd in self.roundings:
            end = rd.get("end", -1)
            if end < 0 or (rd["r"].start, rd["r"].end) in planned or end > len(text):
                continue
            lead = _ROUNDING_WORDS_AFTER_RE.match(text, end, min(len(text), end + 48))
            if lead is not None:
                # the rounding stated in words after the rounded value ('30 m s⁻¹ to 2 s.f., so ...'): its abbreviation's full stops
                # end no clause, and the target clause follows it (repair round 5, ADV5-05)
                end = lead.end()
                while end < len(text) and text[end] in ".)":
                    end += 1
            seg = text[end:end + 160]
            cut = next((i for i, ch in enumerate(seg) if ch == "\n" or (ch in ".!?;" and not (0 < i < len(seg) - 1 and seg[i - 1].isdigit()
                                                                                              and seg[i + 1].isdigit()))), len(seg))
            seg = seg[:cut]
            found = _target_noun(seg)
            condition = None
            restated: Optional[ProseValue] = None
            if found is None:
                # the rounded value restated at the start of the next sentence ('≈ 90%. The yield is 90%, so the batch passes
                # the above-90% requirement'): the target clause follows the restatement (repair round 2, holdout2 class)
                rv0 = value_of(_first(rd["r"]))
                again = next((pv for pv in self.prose_values if end + cut < pv.start <= end + cut + 120 and rv0 is not None
                              and (w := value_of(pv.node)) is not None and w[0] == rv0[0] and (w[2] is None) == (rv0[2] is None) and w[3] == rv0[3]), None)
                if again is not None:
                    end = again.end
                    seg = text[end:end + 160]
                    cut = next((i for i, ch in enumerate(seg) if ch == "\n" or (ch in ".!?;" and not (0 < i < len(seg) - 1 and seg[i - 1].isdigit()
                                                                                                      and seg[i + 1].isdigit()))), len(seg))
                    seg = seg[:cut]
                    found = _target_noun(seg)
                    if found is not None and _IS_THE_TARGET_RE.match(seg[:found[0]]):
                        restated = again  # '≈ 50%. Since 50% is the pass mark, ...': the restated value is the target's value
                if found is None:
                    # the request's own condition ('The method is acceptable only if the mean titre is at least 24.45 cm³') and
                    # the answer's clause asserting or denying its predicate ('≈ 24.45 cm³, so the method is acceptable': repair
                    # round 2, own probes of the rounding class)
                    condition = self._request_condition()
                    said_condition = _predicate_said(seg, condition[2]) if condition is not None else None
                    if said_condition is None:
                        continue
            if condition is not None:
                a = b = 0
                kind, negated = "reach", said_condition
            else:
                a, b = found
                said = _target_verb(seg[:a], seg[b:])
                if said is None:
                    continue
                kind, negated = said
            rv = value_of(_first(rd["r"]))
            if rv is None:
                continue
            pvs = [pv for pv in self.prose_values if end <= pv.start and pv.end <= end + cut] if condition is None else []
            threshold: Optional[Operand] = None
            bound = "ge"
            glued = _glued_target_value(seg[:a], end) if not pvs and condition is None else None
            if condition is not None:
                node, bound = condition[0], condition[1]
                threshold = Operand((node,), 0, 0)  # read from the request: no span of the answer
            elif glued is not None:
                # the value written into the target's noun phrase with its bound ('the above-90% requirement', 'the at-least-70%
                # standard'), which the prose reader does not read as a value of its own (repair round 2)
                node, bound = glued
                threshold = Operand((node,), 0, 0)  # read from the noun phrase's words: no span of maths in the answer
            elif pvs:
                if len(pvs) != 1:
                    continue
                pv = pvs[0]
                threshold = Operand((pv.node,), pv.start, pv.end)
                bound = _target_bound(text[max(end, pv.start - 24):pv.start])
            else:
                hit = self._request_target()
                if hit is None and restated is not None:
                    # the answer itself names the restated rounded value as the target ('≈ 75%. 75% is the threshold, so the batch
                    # meets it'), and the request states no target value: the target is that value, to be reached (repair round 3,
                    # ADV3-03 variants)
                    hit = (restated.node, "ge")
                if hit is None:
                    # the request states its limit only as the condition of a predicate ('Drinking water is unsafe if its nitrate
                    # concentration exceeds 50 mg dm⁻³', then '≈ 50 mg dm⁻³, so the water does not exceed the limit'): the limit's
                    # value is the condition's one value, with its bound (accuracy round 1, ADV6-05)
                    cond = self._request_condition()
                    hit = (cond[0], cond[1]) if cond is not None else None
                if hit is None:
                    continue
                node, bound = hit
                threshold = Operand((node,), 0, 0)  # read from the request: no span of the answer
            tv = value_of(_first(threshold))
            if tv is None or (tv[2] is None) != (rv[2] is None) or tv[3] != rv[3]:
                continue  # the target and the rounded value must be stated alike (both per cents, both with a unit, or both bare)
            if kind == "reach":
                op, neg = bound, negated
            elif kind == "miss":
                op, neg = bound, not negated
            elif bound in ("ge", "gt"):
                op, neg = "gt", negated
            else:
                continue  # going beyond an upper bound: what is claimed is not plain enough to check
            inclusive = ""
            if op in ("gt", "lt") and not neg and tv[0] == rv[0]:
                # the rounded value IS the strict bound ('≈ 80%, so it passes the above-80% requirement'): the answer can only be
                # counting reaching the bound as passing, so its comparison is read inclusively; with the value before the
                # rounding even that reading fails (the strict one fails with both, a target finding of its own)
                op = "ge" if op == "gt" else "le"
                inclusive = " (read inclusively: the rounded value equals the strict bound the answer says it passes)"
            planned.add((rd["r"].start, rd["r"].end))
            self.add(kind="rnd", outcome="check", statement_ids=(rd["sid"],), start=rd["r"].start, end=end + cut, op=_IR_ORDER_SIGN[op],
                     left=rd["r"], right=threshold, premise_left=rd["u"], premise_right=rd["r"], premise_ids=(rd["sid"],), part=rd["part"],
                     explicit=neg,
                     reason=f"ST-ROUND-001: the answer says the value the working rounded in {rd['sid']} {'misses' if neg else 'meets'} a target{inclusive}; "
                            f"that must keep its truth with the value before the rounding")

    def _request_condition(self) -> Optional[tuple[Node, str, str]]:
        """The one condition the request sets on a value: a predicate made conditional ('The method is acceptable only if the
        mean titre is at least 24.45 cm³', 'is accepted provided that', 'as long as') and the one value later in that sentence,
        with the bound written before it: ``(value, bound, predicate word)``; None when there is none or more than one."""
        req = self.request.text[:4000]
        found = []
        for rx in (_CONDITION_RE, _CONDITION_EXTRA_RE):
            # the further shapes ('has a fever if', 'can safely carry') are read only when the first find no condition, so no
            # request that states one of the first gains a second (accuracy round 1, ADV6-05)
            for m in rx.finditer(req):
                pred = (m.groupdict().get("pred") or m.groupdict().get("pred2") or m.groupdict().get("pred3") or m.groupdict().get("pred4") or "").lower()
                if pred in _CONDITION_STOP:
                    continue
                stop = next((k for k in range(m.end(), len(req)) if req[k] in ".!?\n"), len(req))
                vals = [(node, qa) for node, qa, _qb in self.request.values[:256] if m.end() <= qa < stop]
                if len({(value_of(n) or (None,))[0] for n, _qa in vals}) == 1:
                    node, qa = vals[0]
                    before = req[max(0, qa - 24):qa]
                    # 'exceeds 38.0 °C' is a strict bound (accuracy round 1, ADV6-05), any other bound as a target writes it
                    bound = "gt" if _EXCEEDS_BEFORE_RE.search(before) else _target_bound(before)
                    found.append((node, bound, pred))
            if found:
                break
        return found[0] if len(found) == 1 else None

    def _request_target(self) -> Optional[tuple[Node, str]]:
        """The one value the request states beside a target noun ('a target of at least 80%', 'an 80% target'), with the bound
        written before it; None when there is none or more than one."""
        req = self.request.text
        low = req.lower()
        spots = []
        for noun in TARGET_NOUNS:
            k = low.find(noun)
            while 0 <= k < 4000:
                spots.append((k, k + len(noun)))
                k = low.find(noun, k + 1)
        found = []

        def one_sentence(a: int, b: int) -> bool:
            # no sentence end between the noun and the value: 'scored 124 out of 250. The pass mark is 50%' states one target
            # value, not 250 as well (repair round 3, ADV3-03)
            return not any(c in ".!?\n" for c in req[a:b])

        for node, qa, qb in self.request.values[:256]:
            # beside the noun ('a target of at least 80%', 'an 80% target'), or later in the noun's own sentence ('meets the standard
            # only if its efficiency is at least 70%': repair round 2)
            if any((nb <= qa <= nb + 32 and one_sentence(nb, qa)) or (0 <= na - qb <= 12 and one_sentence(qb, na))
                   or (nb <= qa <= nb + 100 and one_sentence(nb, qa)) for na, nb in spots):
                found.append((node, qa))
        if len({(value_of(n) or (None,))[0] for n, _qa in found}) != 1:
            return None
        node, qa = found[0]
        return node, _target_bound(req[max(0, qa - 24):qa])

    def _rounded_source(self, node: Node, part: str, statement_index: int) -> Optional[dict]:
        """The rounding of an earlier chain (same part, not after the value) whose rounded value is ``node`` as written."""
        v = value_of(node)
        if v is None:
            return None
        for rd in reversed(self.roundings):
            if rd["order"] > statement_index or (part and rd["part"] and rd["part"] != part):
                continue
            rv = value_of(_first(rd["r"]))
            if rv is None or rv[0] != v[0] or rv[3] != v[3]:
                continue
            if (rv[2] is None) != (v[2] is None) or (rv[2] is not None and v[2] is not None and " ".join(rv[2].text.split()) != " ".join(v[2].text.split())):
                continue
            return rd
        return None

    def _extrapolation(self) -> None:
        """ST-RANGE-001 (stem_extrapolation): a model the answer states (a law ``y = f(x)`` read earlier, or a substitution into
        one) is evaluated at an input outside [min, max] of the request's data: a series of one quantity in one unit (three or
        more values in one statement), or the years the request's data cover (two or more). The input is read from the
        statement that evaluates the model: a binding of a variable of the law there or in the statement before it ("For
        F = 20 N", "At t = 12 min"), a value with a unit in its prose ("At 20 N"), or a year ("In 2100"). Silent when the
        answer or the request states a caveat that is not negated ("This is not an extrapolation" is none). In Mathematics only
        a dated series is data (the years variant)."""
        if _caveat_stated(self.answer_lower) or _caveat_stated(self._request_lower):
            return
        self._request_law_ranges()
        # Mathematics reads the years of a dated series only (a model of a time series past its last year, "estimate the
        # population in 2060" from 2010 and 2020: repair round 2, own probes): a sequence's terms or a function's inputs are
        # no data, so its other series are not read
        sciences = self.profile.mode == "sciences"
        dated = self.profile.mode == "mathematics" and len(self._dated_years()) >= 2
        if not (sciences or dated) or (not self.request.series and len(self.request.years) < 2):
            return
        series: dict[str, set[Fraction]] = {}
        units: dict[str, str] = {}
        for unit_text, vals in (self.request.series if sciences else ()):
            key = " ".join(unit_text.split())
            series.setdefault(key, set()).update(vals)
            units[key] = unit_text
        years = set(self.request.years) if sciences else set(self._dated_years())
        # the laws the answer states (head -> variables), and the statements that evaluate one
        laws: dict[str, set[str]] = {}
        for r in self.relations:
            # a law the encodings cannot check ('Rate = 0.05 × 2^(T/10)': a symbolic power) is still a model of its variable
            undecided_law = r.outcome == "undecided" and r.kind == "link" and (r.op or "=") in ("=", "≈") and _is_lone(_first(r.left))
            if (undecided_law or (r.outcome == "formula" and r.kind in ("formula", "label"))) and r.left is not None and r.right is not None:
                head, rhs = _first(r.left), _first(r.right)
                name = getattr(head, "name", "")
                variables = (_syms(rhs) | (_unsupported_syms(rhs) if undecided_law and rhs is not None else set())) - {name} if rhs is not None else set()
                if name and rhs is not None and (undecided_law or not is_closed(rhs)) and variables:
                    laws.setdefault(name.split()[-1], set()).update(variables)
        evaluated: dict[str, set[str]] = {}
        for r in self.relations:
            if r.kind == "sub" and r.outcome in ("check", "binding") and (r.pairs or r.evaluate):
                for sid in r.statement_ids:
                    evaluated.setdefault(sid, set()).update(n for n, _x in r.pairs)
                continue
            if r.outcome in ("binding", "check") and r.left is not None and r.right is not None:
                head, rhs = _first(r.left), _first(r.right)
                name = getattr(head, "name", "").split()[-1] if getattr(head, "name", "") else ""
                if name in laws and rhs is not None and is_closed(rhs):
                    for sid in r.statement_ids:
                        evaluated.setdefault(sid, set()).update(laws[name])
        # the trend stepped in arithmetic, with no formula in the variable ('the rate at 60 °C is 14.0 + 3 × 4.0 = 26 units',
        # 'at 90 °C the rate is 0.80 × 2⁵'), or a stated law evaluated in words ('at T = 90 °C the rate would be 0.05 × 2⁹'):
        # a statement whose written arithmetic uses a value of the request's data, or binds a variable of a stated law, evaluates
        # the trend there (repair round 2, ADV2-08); its input is read as for any other evaluation below
        data_values = ({v for _u, vals in self.request.series for v in vals} | _request_numerals(self.request.text)) if sciences else set(years)
        law_vars = {v for vs in laws.values() for v in vs}
        for r in self.relations:
            if r.kind != "eq" or r.outcome != "check":
                continue
            numerals = {abs(v[0]) for op in (r.left, r.right) for node in ([_first(op)] if _first(op) is not None else [])
                        for n in walk(node) if is_value(n) and (v := value_of(n)) is not None}
            for sid in r.statement_ids:
                bound_vars = {b.symbol for b in self.conditions if b.statement_id == sid and b.symbol in law_vars}
                bound_vars |= {name for name in law_vars for b in self.scope.bindings.get(name, ()) if b.statement_id == sid}
                if bound_vars or (numerals & data_values):
                    evaluated.setdefault(sid, set()).update(bound_vars)
        if not evaluated:
            return
        order_of = self.order
        by_order = {o: sid for sid, o in order_of.items()}
        reported: set[str] = set()

        def report(sid: str, shown: str, lo: Fraction, hi: Fraction, unit: str, start: int = 0, end: int = 0) -> None:
            if sid in reported:
                return
            reported.add(sid)
            self.finding("ST-RANGE-001", f"extrapolation (stem_extrapolation): the model is evaluated at {shown}{(' ' + unit) if unit else ''}, outside the "
                                         f"range of the request's data ({_show_value(lo)} to {_show_value(hi)}{(' ' + unit) if unit else ''}), and the answer "
                                         f"states no caveat that the relation may not hold there", (sid,), start, end)

        for sid, variables in evaluated.items():
            # bindings of the law's variables in the evaluating statement or the one before it (same part)
            prev = by_order.get(order_of.get(sid, 0) - 1)
            near = {sid} | ({prev} if prev is not None and self.part_of.get(prev, "") == self.part_of.get(sid, "") else set())
            for name in sorted(variables):
                for b in list(self.scope.bindings.get(name, ())) + [c for c in self.conditions if c.symbol == name]:
                    if b.statement_id not in near or b.wrapper:
                        continue
                    if b.unit is not None:
                        key = " ".join(b.unit.text.split())
                        vs = series.get(key)
                        if vs and not min(vs) <= b.value <= max(vs):
                            report(sid, b.number.text, min(vs), max(vs), units[key], b.start, b.end)
                    elif _is_year(b.value) and years and not min(years) <= b.value <= max(years):
                        report(sid, b.number.text, min(years), max(years), "", b.start, b.end)
            for pv in self.prose_values:
                if pv.statement_id != sid:
                    continue
                v = value_of(pv.node)
                if v is None or v[3]:
                    continue
                if not _INPUT_BEFORE_RE.search(pv.before[-80:]) or _RATE_AFTER_RE.match(pv.after):
                    # a value in prose is where the model is evaluated only when the prose gives it as the input ("at 60 °C", "for
                    # a storm of 120 mm", "when the temperature is 90 °C"); a rate ("rises by 0.08 °C per year"), a step, a result
                    # ("which is 13 A") or a value of the model's output is none (close round 1, ADV6-07)
                    continue
                if v[2] is not None:
                    key = " ".join(v[2].text.split())
                    vs = series.get(key)
                    if vs and not min(vs) <= v[0] <= max(vs):
                        report(sid, v[1].text if v[1] else str(v[0]), min(vs), max(vs), units[key], pv.start, pv.end)
            if years:
                text = self._statement_text(sid)
                for m in _YEAR_INPUT_RE.finditer(text[:4000]):
                    y = Fraction(int(m.group("y")))
                    if not min(years) <= y <= max(years):
                        report(sid, m.group("y"), min(years), max(years), "")
                        break

    def _dated_years(self) -> tuple[Fraction, ...]:
        """The request's data years that a time word dates ("in 2010", "from 2010 to 2020", "between 2010 and 2020", "by
        2020"): the years Mathematics reads as data. A four-digit amount ("1000 dollars", "put 2000 into an account") is no
        year there."""
        text = self.request.text[:20000]
        out = []
        for y in self.request.years:
            n = str(int(y))
            if re.search(rf"\b(?:in|from|to|between|and|since|by|until|during|of)\s+(?:the\s+(?:year|end\s+of)\s+)?{n}\b", text, re.IGNORECASE) \
                    or re.search(rf"\b{n}\s*(?:-|–|—|to)\s*\d{{4}}\b", text):
                out.append(y)
        return tuple(out)

    def _prose_unit_of(self, rel: Relation, stated: Node) -> Optional[UnitExpr]:
        """The unit the answer's prose gives a bare stated value: a prose value of the same number with a unit of one exact
        factor, in the relation's statement or the next one ("= 2000. The energy stored is 2000 J."); None otherwise."""
        v = value_of(stated)
        if v is None or v[2] is not None or v[3]:
            return None
        sid = rel.statement_ids[-1] if rel.statement_ids else ""
        o = self.order.get(sid, 0)
        near = {s for s, k in self.order.items() if k in (o, o + 1) and self.part_of.get(s, "") == self.part_of.get(sid, "")}
        for pv in self.prose_values:
            if pv.statement_id not in near:
                continue
            w = value_of(pv.node)
            if w is not None and w[0] == v[0] and w[2] is not None and w[2].dim is not None and unit_scale(w[2]) is not None and not w[3]:
                return w[2]
        return None

    def _request_law_heads(self) -> frozenset[str]:
        """The symbols the request defines by a law of other symbols ("A = 3.5N + 10"), cached per document."""
        cached = getattr(self, "_law_heads_cache", None)
        if cached is None:
            out = set()
            for l_op, op, r_op in self.request.relations:
                head, rhs = _first(l_op), _first(r_op)
                if op == "=" and isinstance(head, Sym) and rhs is not None and not is_closed(rhs) and _syms(rhs) - {head.name}:
                    out.add(head.name)
            cached = frozenset(out)
            self._law_heads_cache = cached
        return cached

    def _request_states_law(self, sub: Relation) -> bool:
        """Whether the symbolic side of a substitution is a law the request itself writes (the same expression as the right
        side of one of the request's equations, by its shape)."""
        sides = [_first(sub.left), _first(sub.right)]
        sym = next((n for n in sides if n is not None and not is_closed(n)), None)
        if sym is None:
            return False
        key = shape_key(sym)
        for _l_op, op, r_op in self.request.relations:
            rhs = _first(r_op)
            if op == "=" and rhs is not None and not is_closed(rhs) and shape_key(rhs) == key:
                return True
        return False

    def _request_law_ranges(self) -> None:
        """ST-RANGE-001 (stem_extrapolation) for a model the REQUEST states ("the peak discharge fits the line Q = 1.6R + 4,
        where R is the storm rainfall in mm", "the regression line s = 4.8h + 41") with the range of its input stated in
        words ("rainfall totals between 10 mm and 40 mm", "hours of revision h (from 2 to 10 hours)"): the answer substitutes
        a value of that input outside the range and states no caveat (repair round 2, holdout2 class; any STEM profile).
        A range belongs to a variable of the law when it follows the variable's symbol within 40 characters, or carries the
        unit the request states for the variable ("R is ... in mm"), or is the request's only stated range and the law's
        only variable. The value is read from the answer's substitution into the law (its pairs)."""
        text = self.request.text[:20000]
        laws: dict[str, set[str]] = {}
        for l_op, op, r_op in self.request.relations:
            head, rhs = _first(l_op), _first(r_op)
            if op != "=" or not isinstance(head, Sym) or rhs is None or is_closed(rhs):
                continue
            variables = _syms(rhs) - {head.name}
            if variables:
                laws.setdefault(head.name, set()).update(variables)
        if not laws:
            return
        ranges = []
        for m in _prose_ranges(text):
            lo_t = m.group("lo") or m.group("lo2") or m.group("lo3")
            hi_t = m.group("hi") or m.group("hi2") or m.group("hi3")
            try:
                ranges.append((Fraction(lo_t.replace(",", "")), Fraction(hi_t.replace(",", "")), (m.group("u") or "").strip(), m.start(), m.end()))
            except (ValueError, ZeroDivisionError, AttributeError):
                continue
        ranges = [r for r in ranges if r[0] < r[1]]
        if not ranges:
            return
        variables = {v for vs in laws.values() for v in vs}

        def range_for(name: str) -> Optional[tuple[Fraction, Fraction, str]]:
            for m in re.finditer(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])", text):
                near = [r for r in ranges if 0 <= r[3] - m.end() <= 40]
                if near:
                    return near[0][:3]
                unit = _VARIABLE_UNIT_RE.match(text, m.end())
                if unit is not None:
                    u = unit.group(1)
                    same = [r for r in ranges if r[2] and (r[2] == u or r[2].rstrip("s") == u.rstrip("s"))]
                    if same:
                        return same[0][:3]
            if len(ranges) == 1 and len(variables) == 1:
                return ranges[0][:3]
            return None
        for r in self.relations:
            if r.kind != "sub" or not r.pairs:
                continue
            for name, node in r.pairs:
                if name not in variables:
                    continue
                v = value_of(node)
                rng = range_for(name)
                if v is None or rng is None:
                    continue
                lo, hi, unit = rng
                if not lo <= v[0] <= hi:
                    sid = r.statement_ids[-1]
                    self.finding("ST-RANGE-001", f"extrapolation (stem_extrapolation): the request's model is evaluated at {name} = {v[1].text if v[1] else v[0]}"
                                                 f"{(' ' + unit) if unit else ''}, outside the range of the request's data ({_show_value(lo)} to "
                                                 f"{_show_value(hi)}{(' ' + unit) if unit else ''}), and the answer states no caveat that the relation "
                                                 "may not hold there", (sid,), r.start, r.end)
                    return

    def _statement_text(self, sid: str) -> str:
        """The text of statement ``sid`` (from its maths items; '' when it holds none)."""
        for it in self.items:
            if it.statement_id == sid:
                return it.statement_text
        return ""

    def _working(self) -> None:
        """ST-WORK-001 (stem_missing_working): the request asks for working ("show your working", or a calculate, determine or
        show item worth two or more marks), and the answer states a result with no formula, substitution or working line:
        no relation is read, no written expression, and at most one value, or only the figures the request itself states (a
        'show that' answered by restating what was to be shown: "The curve has a local maximum at (1, 4)"). In Computer
        Science only a request that names the working ("showing your method") asks for it (repair round 3,
        V3-H2-STEM-MISSES: a conversion answered "−74" alone)."""
        req = self._request_lower
        if not req:
            return
        asks = any(c in req for c in WORKING_CUES)
        if not asks and self.profile.computer_science:
            return
        judgement = False
        if not asks:
            marks = [int(m.group(1) or m.group(2)) for m in _MARKS_RE.finditer(req[:4000])]
            commands = [w for w in WORKING_COMMANDS if re.search(rf"\b{w}\b", req[:4000])]
            asks = bool(marks) and max(marks) >= 2 and bool(commands)
            # "Show that 13 is prime", "Show that √2 is irrational": a property of a number, shown by an argument; an answer
            # that gives its reasons ("..., so 13 is prime") has the working such a request asks for (repair round 5,
            # ADV5-10). "Calculate whether ..." asks for a judgement, reached by a calculation or by an argument.
            if asks and commands == ["show"] and not self.request.targets and _PROPERTY_SHOW_RE.search(req[:4000]) and _REASONED_RE.search(self.answer_lower or self.answer_text.lower()):
                return
            judgement = asks and all(re.search(rf"\b{w}\s+(?:whether|if)\b", req[:4000]) for w in commands)
        if not asks:
            return
        # working is a relation the answer writes beyond its result: a check of its own lines, a law, a written expression. A
        # check of the stated result against the request (its roots of the request's equation, a Given or a target) is none.
        working = any((r.outcome in ("check", "formula", "undecided") and r.premise_ids != ("request",) and r.kind not in ("giv", "tgt"))
                      or (r.outcome == "binding" and not is_value(_first(r.right) or Sym("?"))) for r in self.relations)
        working = working or any(op in ("+", "-", "*", "/") for it in self.items for ch in it.chains for o in ch.operands for n in o.readings[:1]
                                 for op in [n.op if isinstance(n, BinOp) else ""])
        values = {(pv.statement_id, pv.start) for pv in self.prose_values}
        results = [(r.statement_ids[-1], v[0]) for r in self.relations if r.kind == "binding" and r.outcome == "binding" and r.right is not None
                   and (n := _first(r.right)) is not None and is_value(n) and (v := value_of(n)) is not None]
        if working:
            return
        if values:
            distinct = {abs(value_of(pv.node)[0]) for pv in self.prose_values if value_of(pv.node) is not None}
            if len(distinct) > 1 and not distinct <= _request_numerals(self.request.text):
                return
            if judgement and distinct <= _request_numerals(self.request.text):
                return  # a yes/no question answered with the request's own figures and an argument: no value result is stated
            sids = tuple(dict.fromkeys(pv.statement_id for pv in self.prose_values))
        elif results and len({v for _sid, v in results}) <= 2:
            # the result written as a value for a symbol ('x = 5.', 'x = 5 or x = −5'): one result, or the two roots of one
            sids = tuple(dict.fromkeys(sid for sid, _v in results))
        else:
            return
        self.finding("ST-WORK-001", "missing working (stem_missing_working): the request asks for working, and the answer states its result with no formula, "
                                    "substitution or working line, so nothing of how it was reached can be checked", sids)

    def _rebindings(self) -> None:
        """ST-GIVEN-002 (stem_contradictory_givens): a symbol of a Given or Data statement is bound again to another value in
        the same part (the same symbol: no subscript or prime), and a later substitution uses the second value.
        ST-SCOPE-002 (stem_symbol_conflict): a symbol bound twice in one part to different values whose noun phrases name
        different quantities ("The car's speed is v = …", "The speed of sound is v = …"), with no change marker before the
        second, and a later substitution uses one of them."""
        subs = [r for r in self.relations if r.kind == "sub" and r.outcome == "check" and r.pairs]
        for name, blist in self.scope.bindings.items():
            # a Given value the answer's own computation contradicts: 'Given … v = 12 m s⁻¹', then 'v = 100/10.0 = 10 m s⁻¹'
            givens = [b for b in blist if b.source == "given"]
            for b2 in [b for b in blist if b.source == "result"]:
                b1 = next((g for g in givens if self.order.get(g.statement_id, 0) < self.order.get(b2.statement_id, 0)
                           and self.part_of.get(g.statement_id, "") == self.part_of.get(b2.statement_id, "")), None)
                if b1 is None or self._change_marked(b2) or (b1.unit is None) != (b2.unit is None):
                    continue
                if b1.unit is not None and b2.unit is not None and (b1.unit.dim is None or b2.unit.dim is None or not b1.unit.dim.same_physical(b2.unit.dim)
                                                                    or unit_scale(b1.unit) != unit_scale(b2.unit)):
                    continue
                computed = self._computed_interval(b2)
                if computed is None:
                    continue
                lo, hi = b1.value - b1.half_width, b1.value + b1.half_width
                if not (computed.hi < lo or hi < computed.lo):
                    continue  # the computation agrees with the Given within their rounding
                shown = lambda b: f"{b.number.text}{' ' + b.unit.text if b.unit else ''}"  # noqa: E731
                self.finding("ST-GIVEN-002", f"contradictory givens (stem_contradictory_givens): '{name}' is given as {shown(b1)} in {b1.statement_id}, and "
                                             f"the answer's own calculation from the other givens gives {shown(b2)} in {b2.statement_id}: the givens cannot "
                                             f"all hold", tuple(dict.fromkeys((b1.statement_id, b2.statement_id))))
                break
            answer = [b for b in blist if b.source in ("given", "statement", "let")]
            derived = [b for b in blist if b.source == "result"]
            for i, b1 in enumerate(answer):
                for b2 in answer[i + 1:] + [d for d in derived if self.order.get(d.statement_id, 0) > self.order.get(b1.statement_id, 0)]:
                    if b1.same_as(b2) or self.part_of.get(b1.statement_id, "") != self.part_of.get(b2.statement_id, ""):
                        continue
                    o2 = self.order.get(b2.statement_id, 0)
                    users = [r for r in subs if self.order.get(r.statement_ids[-1], 0) >= o2 and any(
                        s_name == name and (v := value_of(n)) is not None and v[0] in (b1.value, b2.value) for s_name, n in r.pairs)]
                    if not users:
                        continue
                    used = users[0]
                    sids = tuple(dict.fromkeys((b1.statement_id, b2.statement_id) + tuple(used.statement_ids)))
                    shown = lambda b: f"{b.number.text}{' ' + b.unit.text if b.unit else ''}"  # noqa: E731
                    if b1.source == "given" and b2.source != "result":
                        self.finding("ST-GIVEN-002", f"contradictory givens (stem_contradictory_givens): '{name}' is given as {shown(b1)} in {b1.statement_id} "
                                                     f"and bound again to {shown(b2)} in {b2.statement_id} with no new symbol, and the working uses "
                                                     f"'{name}' in {used.statement_ids[-1]}", sids)
                        continue
                    np1, np2 = self._object_words(b1), self._object_words(b2)
                    if not np1 or not np2 or np1 <= np2 or np2 <= np1 or self._change_marked(b2):
                        continue
                    verdicts = [self._scoped_use(name, b1, b2, np1, np2, r) for r in users]
                    wrong = next((r for r, v in zip(users, verdicts) if v[0] == "conflict"), None)
                    if wrong is not None:
                        why = next(v[1] for r, v in zip(users, verdicts) if r is wrong)
                        sids = tuple(dict.fromkeys((b1.statement_id, b2.statement_id) + tuple(wrong.statement_ids)))
                        self.finding("ST-SCOPE-002", f"symbol conflict (stem_symbol_conflict): '{name}' stands for {shown(b1)} ('{' '.join(sorted(np1))}') in "
                                                     f"{b1.statement_id} and for {shown(b2)} ('{' '.join(sorted(np2))}') in {b2.statement_id}, two different "
                                                     f"quantities, and {why}", sids)
                        continue
                    if b2.source == "result" or all(v[0] == "consistent" for v in verdicts):
                        continue  # every use takes the value of the object its working names: the symbol is scoped, no conflict
                    self.finding("ST-SCOPE-002", f"symbol conflict (stem_symbol_conflict): '{name}' stands for {shown(b1)} ('{' '.join(sorted(np1))}') in "
                                                 f"{b1.statement_id} and for {shown(b2)} ('{' '.join(sorted(np2))}') in {b2.statement_id}, two different "
                                                 f"quantities, and the working uses '{name}' in {used.statement_ids[-1]} without saying which", sids)
        self._dimension_rebindings(subs)

    def _dimension_rebindings(self, subs: list[Relation]) -> None:
        """ST-SCOPE-002 by the units (repair round 5, ADV5-07): a symbol bound twice in one part to values whose units have
        different dimensions ('P = F/A = … = 400 Pa', then 'P = W/t = … = 300 W') stands for two different quantities whatever
        the noun phrases say; when the working then uses the symbol (a substitution, or a statement of its value after both
        bindings: 'F = PA = 300 × 0.10', 'So P = 300.') without a change marker before the second binding, which quantity it
        means is not said. Every reading is of the units the answer writes; nothing is inferred."""
        seen: set[str] = set()
        shown = lambda b: f"{b.number.text}{' ' + b.unit.text if b.unit else ''}"  # noqa: E731
        for name, blist in self.scope.bindings.items():
            dimmed = [b for b in blist if b.source not in ("root", "substitution", "request") and b.unit is not None and not b.unit.unknown
                      and b.unit.dim is not None]
            for i, b1 in enumerate(dimmed):
                if name in seen:
                    break
                for b2 in dimmed[i + 1:]:
                    if b1.unit.dim.same_physical(b2.unit.dim) or self.part_of.get(b1.statement_id, "") != self.part_of.get(b2.statement_id, ""):
                        continue
                    if self._change_marked(b2):
                        continue
                    o2 = self.order.get(b2.statement_id, 0)
                    part = self.part_of.get(b2.statement_id, "")
                    users = [r for r in subs if self.order.get(r.statement_ids[-1], 0) >= o2 and r.statement_ids[-1] != b2.statement_id
                             and self.part_of.get(r.statement_ids[-1], "") == part and any(s_name == name for s_name, _n in r.pairs)]
                    later = [b for b in blist if b.source in ("statement", "result", "let") and self.order.get(b.statement_id, 0) > o2
                             and self.part_of.get(b.statement_id, "") == part]
                    if not users and not later:
                        continue
                    where = users[0].statement_ids[-1] if users else later[0].statement_id
                    sids = tuple(dict.fromkeys((b1.statement_id, b2.statement_id, where)))
                    self.finding("ST-SCOPE-002", f"symbol conflict (stem_symbol_conflict): '{name}' stands for {shown(b1)} in {b1.statement_id} and for "
                                                 f"{shown(b2)} in {b2.statement_id}, quantities of different dimensions, and the working uses '{name}' in "
                                                 f"{where} without saying which", sids)
                    seen.add(name)
                    break

    def _request_states(self, b: Binding) -> Optional[bool]:
        """Whether the request states binding ``b``'s value: True when one of the request's bindings of the same symbol, or one
        of its quantities of the same physical dimension, equals it within rounding; False when the request states such
        values and none equals it; None when it states none (or ``b`` has no unit of a known dimension and the request binds
        no such symbol)."""
        cands = [r for r in self.request.bindings if r.symbol == b.symbol]
        if b.unit is not None and b.unit.dim is not None and not b.unit.unknown:
            for node, a0, b0 in self.request.quantities:
                v = value_of(node)
                if v is None or v[1] is None or v[2] is None or v[2].dim is None or not v[2].dim.same_physical(b.unit.dim):
                    continue
                cands.append(Binding(b.symbol, v[0], v[1], v[2], "request", "request", a0, b0, wrapper=v[3]))
        if not cands:
            return None
        return any(b.same_as(c) for c in cands)

    def _uses_value(self, rel: Relation, name: str, b: Binding) -> bool:
        """Whether substitution ``rel`` uses ``b``'s value for ``name``: a written pair (``name`` = the value), or an evaluation
        whose symbolic side holds ``name`` and whose numeric side holds the value as written ("a = (v − u)/t = 20 / 4.0")."""
        if rel.kind != "sub":
            return False
        if any(s_name == name and (v := value_of(n)) is not None and v[0] == b.value for s_name, n in rel.pairs):
            return True
        if not rel.evaluate or rel.left is None or rel.right is None:
            return False
        if not any(name in symbols(n) for n in rel.left.readings):
            return False
        return any(is_value(x) and (v := value_of(x)) is not None and v[0] == b.value for n in rel.right.readings for x in walk(n))

    def _unlabelled_rebindings(self) -> None:
        """Two bindings of one symbol in one part, to different values, neither of which says what it is about (no noun phrase,
        no scope phrase, no change marker before the second; repair round 2, holdout2 givens and symbol-conflict classes):

        * ST-GIVEN-002 when the request states the first value and not the second, and a later substitution uses the second:
          "u = 0, v = 20 m s⁻¹, t = 5.0 s, and t = 4.0 s. a = (v − u)/t = 20 / 4.0" for a request that gives 5.0 s;
        * ST-SCOPE-002 when two symbols are bound so in parallel and one substitution takes them from different sets of
          values (:meth:`_mixed_groups`): "m = 2.0 kg and v = 3.0 m s⁻¹, and m = 1.0 kg and v = 5.0 m s⁻¹. Ek = ½ × 2.0 × 5.0²".

        A Given statement's rebinding is :meth:`_rebindings`'s; a value the answer derives is no binding of this kind."""
        subs = [r for r in self.relations if r.kind == "sub" and r.outcome == "check"]
        shown = lambda b: f"{b.number.text}{' ' + b.unit.text if b.unit else ''}"  # noqa: E731
        reported: set[frozenset[str]] = set()
        for name, blist in self.scope.bindings.items():
            answer = [b for b in blist if b.source in ("statement", "let")]
            for i, b1 in enumerate(answer):
                for b2 in answer[i + 1:]:
                    if (not _distinct(b1, b2) or self.part_of.get(b1.statement_id, "") != self.part_of.get(b2.statement_id, "")
                            or self._change_marked(b2) or self._object_words(b1) or self._object_words(b2)):
                        continue
                    o2 = self.order.get(b2.statement_id, 0)
                    later = [r for r in subs if self.order.get(r.statement_ids[-1], 0) >= o2]
                    late = next((r for r in later if self._uses_value(r, name, b2)), None)
                    if late is not None and self._request_states(b1) is True and self._request_states(b2) is False:
                        sids = tuple(dict.fromkeys((b1.statement_id, b2.statement_id) + tuple(late.statement_ids)))
                        self.finding("ST-GIVEN-002", f"contradictory givens (stem_contradictory_givens): '{name}' is bound to {shown(b1)} in "
                                                     f"{b1.statement_id}, the value the request states, and again to {shown(b2)} in {b2.statement_id}, "
                                                     f"which the request does not state, with no new symbol, and the working uses {shown(b2)} in "
                                                     f"{late.statement_ids[-1]}", sids)
                        continue
                    users = [r for r in later if r.pairs and any(s_name == name for s_name, _n in r.pairs)]
                    mixed = self._mixed_groups(name, b1, b2, users)
                    if mixed is None or frozenset((name, mixed[1])) in reported:
                        continue
                    rel, other = mixed
                    reported.add(frozenset((name, other)))
                    sids = tuple(dict.fromkeys((b1.statement_id, b2.statement_id) + tuple(rel.statement_ids)))
                    self.finding("ST-SCOPE-002", f"symbol conflict (stem_symbol_conflict): '{name}' stands for {shown(b1)} and for {shown(b2)}, and "
                                                 f"'{other}' for two values bound beside them, with nothing saying which object each is about, and the "
                                                 f"working in {rel.statement_ids[-1]} takes '{name}' from one set of values and '{other}' from the "
                                                 "other (mixed values)", sids)

    def _mixed_groups(self, name: str, b1: Binding, b2: Binding, users: list[Relation]) -> Optional[tuple[Relation, str]]:
        """A substitution that takes ``name`` from one of its two bindings and another symbol from the other of that symbol's
        two bindings, where the two symbols are bound in parallel (each twice in the same part, to different values, the
        first bindings of both before the second bindings of both: "m = 2.0 kg and v = 3.0 m s⁻¹, and m = 1.0 kg and v = 5.0
        m s⁻¹") and each occurs once in the substitution: ``(the substitution, the other symbol)``, or None. A substitution
        that keeps to one set of values ("½ × 2.0 × 3.0²") mixes nothing; one that uses a symbol twice (a collision's
        ``m u + m u``) pairs its own values and is not read."""
        part = self.part_of.get(b1.statement_id, "")
        for rel in users:
            counts: dict[str, int] = {}
            for s_name, _n in rel.pairs:
                counts[s_name] = counts.get(s_name, 0) + 1
            if counts.get(name) != 1:
                continue
            mine = next(((1 if v[0] == b1.value else 2 if v[0] == b2.value else 0) for s_name, n in rel.pairs
                         if s_name == name and (v := value_of(n)) is not None), 0)
            if not mine:
                continue
            for s_name, n in rel.pairs:
                if s_name == name or counts.get(s_name) != 1 or (v := value_of(n)) is None:
                    continue
                own = [b for b in self.scope.bindings.get(s_name, ()) if b.source in ("given", "statement", "let")
                       and self.part_of.get(b.statement_id, "") == part]
                if len(own) != 2 or not _distinct(own[0], own[1]) or self._object_words(own[0]) or self._object_words(own[1]):
                    continue
                c1, c2 = sorted(own, key=lambda b: b.order)
                if not (max(b1.order, c1.order) < min(b2.order, c2.order)):
                    continue  # not bound in parallel
                theirs = 1 if v[0] == c1.value else 2 if v[0] == c2.value else 0
                if theirs and theirs != mine:
                    return rel, s_name
        return None

    def _computed_interval(self, b: Binding):
        """The value of the expression the answer computed a result binding from (the closed side of the link that states
        it: ``100/10.0`` for ``v = 100/10.0 = 10 m s⁻¹``), every decimal by its rounding interval and every integer exact, as
        a rational interval; None when no such link or no enclosure."""
        for r in self.relations:
            if r.kind not in ("eq", "unit") or r.left is None or r.right is None or b.statement_id not in r.statement_ids:
                continue
            rn = _first(r.right)
            if rn is None or getattr(rn, "start", -1) != b.start:
                continue
            ln = _first(r.left)
            if ln is None or not is_closed(ln) or any(isinstance(n, (Quantity, WithUnit, Percent)) for n in walk(ln)):
                return None
            return enclose_node(ln, {}, decimal_widths=True)
        return None

    def _overdetermined_givens(self) -> None:
        """ST-GIVEN-004 (stem_contradictory_givens): the values the answer states for the symbols of one part fix every
        variable of a law of uniform motion (:data:`.reference_data.GIVENS_LAWS`: ``v = u + at``, ``s = ut + ½at²``,
        ``s = ½(u + v)t``), the request or the answer says the motion is uniform, and the law fails beyond the rounding of
        the stated values: the givens cannot all hold, and the working uses them without saying so ("from rest at 4.0
        m s⁻² for 6.0 s, reaching 20 m s⁻¹": u + at = 24 m s⁻¹, not 20; repair round 2, holdout2 class). A free fall ("dropped",
        "falls freely") is uniform too, unless air resistance, drag or friction is said to act (and not to be neglected). Each symbol has
        one stated value in the part (two different ones are ST-GIVEN-002's), a unit whose dimension is the law's, or
        the value 0; the law's two sides are compared over the corners of the stated values' rounding intervals. An answer
        that says the givens disagree states the contradiction itself (no finding)."""
        if self.profile.computer_science or self.profile.is_mathematics or not self.scope.bindings:
            return
        if _INCONSISTENCY_NOTED_RE.search(self.answer_text[:100_000]):
            return
        both = self.request.text[:20000] + "\n" + self.answer_text[:100_000]
        uniform = bool(_UNIFORM_MOTION_RE.search(both)) and not (_RESISTED_MOTION_RE.search(both) and not _RESISTANCE_NEGLECTED_RE.search(both))
        laws = [law for law in booklet_laws(self.profile.key) if (law.text in GIVENS_LAWS and uniform) or law.text in DEFINITION_GIVENS_LAWS]
        if not laws:
            return
        by_part: dict[str, dict[str, Optional[Binding]]] = {}
        for name, blist in self.scope.bindings.items():
            for b in blist:
                if b.source not in ("given", "statement", "let"):
                    continue
                slot = by_part.setdefault(self.part_of.get(b.statement_id, ""), {})
                if name in slot and (slot[name] is None or not slot[name].same_as(b)):
                    slot[name] = None
                elif name not in slot:
                    slot[name] = b
        for part, slot in by_part.items():
            for law in laws:
                names = {law.lhs} | set(law.variables)
                if not names <= slot.keys() or any(slot[n] is None for n in names):
                    continue
                dims = DEFINITION_GIVENS_LAWS.get(law.text)
                # a whole number whose trailing zeros are ambiguous ("20") is read to its units digit when another given of the
                # law is written with a decimal point ("4.0", "6.0"): the givens state their precision in figures, so "20" is
                # 20 ± 0.5, not 20 ± 5 (repair round 3, V3-H2-STEM-MISSES: "from rest at 4.0 m s⁻² for 6.0 s, reaching 20 m s⁻¹")
                decimals = any("." in slot[n].number.text for n in names)
                corners: list[dict[str, Fraction]] = [{}]
                ok = True
                for n in sorted(names):
                    b = slot[n]
                    q = fixed_quantity(n, self.profile.key, request_text=self.request.text)
                    if b.value == 0 and b.unit is None:
                        lo = hi = Fraction(0)
                    else:
                        si = b.si
                        if dims is not None:
                            fits = b.unit is not None and b.unit.dim is not None and tuple(b.unit.dim.exps) == dims.get(n) and not b.unit.dim.angle
                        else:
                            fits = b.unit is not None and b.unit.dim is not None and q is not None and b.unit.dim.same_physical(q.dimension)
                        if si is None or not fits:
                            ok = False
                            break
                        factor = si / b.value if b.value else Fraction(1)
                        half = b.half_width
                        text = b.number.text.strip()
                        if decimals and "." not in text and text.rstrip("0") != text and text.lstrip("-+−").isdigit() and half > Fraction(1, 2):
                            half = Fraction(1, 2)
                        h = half * abs(factor)
                        lo, hi = si - h, si + h
                    corners = [dict(c, **{n: x}) for c in corners for x in ({lo, hi} if n != law.lhs else {(lo + hi) / 2})]
                    if n == law.lhs:
                        lhs_lo, lhs_hi = lo, hi
                if not ok:
                    continue
                vals = [enclose_node(law.rhs, c) for c in corners]
                if any(v is None for v in vals):
                    continue
                r_lo, r_hi = min(v.lo for v in vals), max(v.hi for v in vals)
                gap = max(r_lo - lhs_hi, lhs_lo - r_hi)
                if gap <= 0 or gap <= abs(lhs_hi) / 50:
                    continue  # the law holds within the givens' rounding (or within 2%)
                shown = ", ".join(f"{n} = {slot[n].number.text}{' ' + slot[n].unit.text if slot[n].unit else ''}" for n in sorted(names))
                sids = tuple(dict.fromkeys(slot[n].statement_id for n in sorted(names)))
                self.finding("ST-GIVEN-004", f"contradictory givens (stem_contradictory_givens): the stated values {shown} do not satisfy {law.text} "
                                             f"(the right side is {float(r_lo):.4g} to {float(r_hi):.4g} in SI units, the left {float(lhs_lo):.4g} to "
                                             f"{float(lhs_hi):.4g}): they cannot all hold, and the working uses them without saying so", sids)
                return

    def _set_counts(self) -> None:
        """ST-GIVEN-004 (stem_contradictory_givens), on two sets: the request gives a total ("In a group of 120 students"),
        a count for each of two sets ("70 study French, 65 study Spanish"), the count in both and the count in neither, and
        they do not add up (a + b − both + neither is not the total, or both exceeds a set's count), while the answer
        computes with them without saying so (repair round 2, holdout2 class). Read from one sentence of the request by a
        closed pattern (:data:`_SET_TOTAL_RE`, :data:`_SET_COUNT_RE`): exactly two named sets, one 'both', one 'neither'.
        The counts are whole numbers, compared exactly."""
        text = self.request.text[:20000]
        if not text or _INCONSISTENCY_NOTED_RE.search(self.answer_text[:100_000]):
            return
        for sm in _PLAIN_SENTENCE_RE.finditer(text):
            sent = sm.group(0)
            total = _SET_TOTAL_RE.search(sent)
            if total is None:
                continue
            named: dict[str, int] = {}
            both = neither = None
            for m in _SET_COUNT_RE.finditer(sent):
                n, what = int(m.group(1)), m.group(2).lower()
                if what == "both":
                    both = n if both is None else -1
                elif what in ("neither", "none"):
                    neither = n if neither is None else -1
                else:
                    named[what] = n if what not in named else -1
            if both is None or neither is None or both < 0 or neither < 0 or len(named) != 2 or any(v < 0 for v in named.values()):
                continue
            (x, nx), (y, ny) = sorted(named.items())
            n_total = int(total.group(1) or total.group(2))
            implied = nx + ny - both + neither
            if implied == n_total and both <= min(nx, ny):
                continue
            used = {str(v) for v in (n_total, nx, ny, both, neither)} & set(_NUMERAL_RE.findall(self.answer_text[:100_000]))
            if not used:
                continue
            sids = tuple(dict.fromkeys(r.statement_ids[-1] for r in self.relations if r.statement_ids and r.outcome == "check")) or ("s1.1",)
            why = (f"{nx} + {ny} − {both} + {neither} = {implied}, not {n_total}" if implied != n_total else f"{both} in both exceeds a set's count")
            self.finding("ST-GIVEN-004", f"contradictory givens (stem_contradictory_givens): the request's counts of the two sets cannot all hold "
                                         f"({x} {nx}, {y} {ny}, both {both}, neither {neither}, total {n_total}: {why}), and the working computes with "
                                         f"them without saying so", sids[:4])
            return

    def _probabilities(self) -> None:
        """ST-GIVEN-003 (stem_contradictory_givens), on probabilities: (a) the answer states a probability (a chain whose head is
        written ``P(…)``) whose value lies outside [0, 1] (or a per cent outside [0, 100]); (b) the answer states that two
        events are mutually exclusive while the request gives their intersection a non-zero probability, or that they are
        independent while the request's P(A ∩ B) is not P(A)·P(B) within the given figures' rounding. A statement the answer
        negates ("A and B are not mutually exclusive") states nothing. Read from the chains and closed text patterns only."""
        if self.profile.computer_science:
            return
        for e in self.final_values:
            head = " ".join((e.get("symbol") or "").split())
            if not _PROBABILITY_HEAD_RE.search(head):
                continue
            v = value_of(e["node"])
            if v is None or v[2] is not None:
                continue
            value = v[0] / 100 if v[3] == "%" else v[0]
            if 0 <= value <= 1:
                continue
            self.finding("ST-GIVEN-003", f"contradictory givens (stem_contradictory_givens): the answer states {head} = {render(e['node'])[:40]}, a probability "
                                         f"outside [0, 1]; the values or the assumption it was computed from cannot all hold", (e["sid"],))
        req = self.request.text[:20000]
        singles = {m.group(1): m.group(2) for m in _PROB_SINGLE_RE.finditer(req)}
        for m in _PROB_JOINT_RE.finditer(req):
            a, b, joint = m.group(1), m.group(2), m.group(3)
            pair = f"{a} and {b}"
            try:
                pj = Fraction(joint)
            except (ValueError, ZeroDivisionError):
                continue
            stated = _stated_relation(self.answer_lower, a.lower(), b.lower())
            if stated == "exclusive" and pj != 0:
                self.finding("ST-GIVEN-003", f"contradictory givens (stem_contradictory_givens): the answer treats {pair} as mutually exclusive, but the "
                                             f"request gives P({a} ∩ {b}) = {joint}, which is not 0", self._answer_sids())
            elif stated == "independent" and a in singles and b in singles:
                try:
                    pa, pb = Fraction(singles[a]), Fraction(singles[b])
                except (ValueError, ZeroDivisionError):
                    continue
                # a request's probabilities are exact as given; the joint one is compared within half a unit of its last digit
                if abs(pa * pb - pj) > _half_unit(joint):
                    self.finding("ST-GIVEN-003", f"contradictory givens (stem_contradictory_givens): the answer treats {pair} as independent, but the "
                                                 f"request gives P({a} ∩ {b}) = {joint}, while P({a})·P({b}) = {_show_value(pa * pb)}", self._answer_sids())

    def _answer_sids(self) -> tuple[str, ...]:
        """The statement ids of the answer's maths (the first few), for a finding about the whole answer."""
        return tuple(dict.fromkeys(it.statement_id for it in self.items))[:4]

    def _binding_prefix(self, b: Binding) -> str:
        """The statement's text before the binding's value (bounded), or ''."""
        for it in self.items:
            if it.statement_id == b.statement_id and it.statement_start <= b.start <= it.statement_end:
                a = max(0, b.start - it.statement_start - 160)
                return it.statement_text[a:b.start - it.statement_start]
        return ""

    def _binding_suffix(self, b: Binding) -> str:
        """The statement's text after the binding's value (bounded), or ''."""
        for it in self.items:
            if it.statement_id == b.statement_id and it.statement_start <= b.start <= it.statement_end:
                a = b.end - it.statement_start
                return it.statement_text[a:a + 160] if 0 <= a <= len(it.statement_text) else ""
        return ""

    def _noun_phrase(self, b: Binding) -> frozenset[str]:
        """The content words of the noun phrase a binding names: the words before its symbol in its clause ("The car's speed
        is v = 12": car, speed), with an object's label after its noun ("trolley A", "car 2": 'trolley a') and, in a chemistry
        profile, an element symbol ("of Mg"). The clause starts after sentence punctuation (not a decimal point), a comma, a
        colon or semicolon, an earlier relation sign or a joining conjunction ("and", "while", "whereas", "but"), so the second
        of two coordinated bindings ("The mass of trolley A is m = 2.0 kg and the mass of trolley B is m = 1.0 kg") names only
        its own phrase. When nothing before the symbol names a quantity ("Let m = 2.0 kg be the mass of trolley A", "m = 2.0 kg
        (trolley A)"), the words after the value up to the end of its clause name it, unit words left out (repair round 2,
        holdout2 symbol-conflict class: objects told apart by a label, or named after the value, were read as one phrase)."""
        text = self._binding_prefix(b)
        k = text.rfind(b.symbol)
        if k >= 0:
            text = text[:k]
        words = _phrase_words(_clause_tail(text), self.profile.chemistry)
        if words:
            return words
        return _phrase_words(_clause_head(self._binding_suffix(b)), self.profile.chemistry, units=self.profile)

    def _object_words(self, b: Binding) -> frozenset[str]:
        """What a binding is about (ST-SCOPE-002): its noun phrase (:meth:`_noun_phrase`), the scope phrase that opens its
        statement ("For trolley A, m = 2.0 kg and v = 3.0 m s⁻¹": 'trolley', 'trolley a') and the object a qualifier after
        its value names ("n = 0.0300 mol of HNO₃": 'HNO₃'); repair round 2, holdout2 symbol-conflict class."""
        out = set(self._noun_phrase(b)) | set(self._lead_words(b.statement_id))
        m = _OF_OBJECT_RE.match(self._binding_suffix(b))
        if m is not None:
            out.add(m.group(1))
        return frozenset(out)

    def _lead_words(self, sid: str) -> frozenset[str]:
        """The words of the scope phrase that opens statement ``sid`` (up to its first comma or colon, before any relation
        sign: "For car P,", "Momentum of the heavier ball:"), labels after "of"/"for" kept ('of A': 'a'); empty when none."""
        for it in self.items:
            if it.statement_id != sid:
                continue
            m = _LEAD_SCOPE_RE.match(it.statement_text[:160])
            if m is None:
                return frozenset()
            lead = m.group(1)
            return _phrase_words(lead, self.profile.chemistry) | {x.lower() for x in _BARE_LABEL_RE.findall(lead)}
        return frozenset()

    def _scoped_use(self, name: str, b1: Binding, b2: Binding, np1: frozenset[str], np2: frozenset[str], used: Relation) -> tuple[str, str]:
        """Whether one substitution uses ``name`` with the value of the object its working is about: ``("consistent" |
        "conflict" | "unknown", why)``. The object is the one its statement's scope phrase names ("Momentum of A:", "For car
        P,"), else, for a working that names none, the one its other twice-bound symbols take their values from (one object
        for all: consistent; two: mixed), else the one the request asks about ("the time for the sound", "the momentum of
        trolley A"). A use whose object is not decided is unknown. After a value the answer derived for another object
        ("n = 0.0300 / 2 = 0.0150 mol of Ca(OH)₂"), using the earlier value with no object named is a conflict (the stale
        quantity)."""
        value = next((v[0] for s_name, n in used.pairs if s_name == name and (v := value_of(n)) is not None), None)
        if value is None:
            return "unknown", ""
        mine = 1 if value == b1.value else 2 if value == b2.value else 0
        if not mine:
            return "unknown", ""
        d1, d2 = _distinctive(np1, np2), _distinctive(np2, np1)
        where = used.statement_ids[-1]
        named = self._lead_words(where) | _phrase_words(self._relation_head(used), self.profile.chemistry)
        side = _matches_object(named, d1, d2)
        if side:
            if side == mine:
                return "consistent", ""
            return "conflict", (f"the working for the {'first' if side == 1 else 'second'} ('{' '.join(sorted(named))[:80]}') in {where} substitutes "
                                f"the value of the other for '{name}'")
        others = []
        for s_name, n in used.pairs:
            if s_name == name or (v := value_of(n)) is None:
                continue
            ob = [b for b in self.scope.bindings.get(s_name, ()) if b.source in ("given", "statement", "let") and self.part_of.get(b.statement_id, "") ==
                  self.part_of.get(b1.statement_id, "")]
            sides = {_matches_object(self._object_words(b), d1, d2) for b in ob if b.value == v[0]} - {0}
            if len(sides) == 1:
                others.append(next(iter(sides)))
        if others:
            if all(o == mine for o in others):
                return "consistent", ""
            return "conflict", f"the working in {where} takes '{name}' from one object and its other symbols from the other (mixed values)"
        if b2.source == "result" and mine == 1:
            return "conflict", (f"after deriving {b2.number.text} for the second in {b2.statement_id}, the working in {where} substitutes the earlier "
                                f"value of '{name}' with no object named")
        asked = self._asked_object_words()
        side = _matches_object(asked, d1, d2)
        if side:
            if side == mine:
                return "consistent", ""
            return "conflict", (f"the request asks about the {'first' if side == 1 else 'second'} ('{' '.join(sorted(asked & (d1 | d2)))[:80]}'), "
                                f"and the working in {where} substitutes the value of the other for '{name}'")
        return "unknown", ""

    def _relation_head(self, rel: Relation) -> str:
        """The text of the relation's statement before the relation (bounded), or ''."""
        sid = rel.statement_ids[-1] if rel.statement_ids else ""
        for it in self.items:
            if it.statement_id == sid and it.statement_start <= rel.start <= it.statement_end:
                a = max(0, rel.start - it.statement_start - 120)
                return _clause_tail(it.statement_text[a:rel.start - it.statement_start])
        return ""

    def _asked_object_words(self) -> frozenset[str]:
        """The words (and labels) of what the request asks to calculate: its sentences that open with a command word or a
        question word ("Calculate the momentum of trolley A", "the time for the sound to reach a wall")."""
        cached = getattr(self, "_asked_cache", None)
        if cached is None:
            out: set[str] = set()
            for m in _ask_sentences(self.request.text[:20000]):
                out |= _phrase_words(m.group(0), self.profile.chemistry) | {x.lower() for x in _BARE_LABEL_RE.findall(m.group(0))}
            cached = frozenset(out)
            self._asked_cache = cached
        return cached

    def _change_marked(self, b: Binding) -> bool:
        """A change marker before the binding ("later", "now", "the second reading"): an ordinal before an object noun ("the
        second trolley's mass") names another object, so it marks no change of the same quantity."""
        words = "".join(c.lower() if c.isalpha() else " " for c in self._binding_prefix(b)[-120:].replace("'s", " ").replace("’s", " ")).split()
        return any(w in CHANGE_MARKERS and not _object_ordinal(words, k) for k, w in enumerate(words))

    # -------------------------------------------------------------- reference knowledge (section 24)
    def _law_symbol_dim(self, name: str, traced: Optional[dict[str, Dimension]] = None) -> Optional[Dimension]:
        """The dimension of a symbol of a law: from the units the answer states for it, else from the request's quantity the
        working substitutes for it (``traced``), else from its reference quantity when that is fixed; None when none says."""
        d = self._symbol_dim(name)
        if d is not None:
            return d
        if traced and name in traced:
            return traced[name]
        q = fixed_quantity(name, self.profile.key, request_text=self.request.text)
        return q.dimension if q is not None else None

    def _stated_values(self) -> frozenset[Fraction]:
        """The values (as written) of every quantity the answer or the request states with a unit: a numeral of a law equal to
        one of them may be that quantity substituted, so it is no pure coefficient (:func:`.reference.pure_coefficient_dimension`)."""
        out: set[Fraction] = set()
        for pv in self.prose_values:
            v = value_of(pv.node)
            if v is not None and v[2] is not None:
                out.add(abs(v[0]))
        for blist in self.scope.bindings.values():
            for b in blist:
                if b.unit is not None:
                    out.add(abs(b.value))
        for node, _a, _b in self.request.quantities[:256]:
            v = value_of(node)
            if v is not None and v[2] is not None:
                out.add(abs(v[0]))
        return frozenset(out)

    def _si_form_binding(self, name: str, node: Node) -> Optional[Binding]:
        """The binding of ``name``, or else the request's quantity, that the bare numeral ``node`` states in SI: its value in its
        unit times the unit's factor is the numeral ('180 000' for '180 kJ', '2000' for '2.0 kW'), one dimension among the
        candidates (and the symbol's reference dimension, when the reference fixes one). The working then substitutes the
        quantity converted, so the numeral is read as written (repair round 4, ADV4-02)."""
        v = value_of(node)
        if v is None or v[2] is not None or v[3] or v[1] is None:
            return None
        value = v[0]
        found = [b for b in self.scope.bindings.get(name, ()) if b.source != "root" and b.unit is not None and not b.wrapper
                 and unit_scale(b.unit) not in (None, Fraction(1)) and b.value * unit_scale(b.unit) == value]
        if not found:
            q = fixed_quantity(name, self.profile.key, request_text=self.request.text)
            dim = q.dimension if q is not None else None
            for qnode, a, b in self.request.quantities[:256]:
                qv = value_of(qnode)
                if qv is None or qv[1] is None or qv[2] is None or qv[2].unknown or qv[2].dim is None or qv[3]:
                    continue
                scale = unit_scale(qv[2])
                if scale is None or scale == 1 or qv[0] * scale != value or (dim is not None and not qv[2].dim.same_physical(dim)):
                    continue
                found.append(Binding(name, qv[0], qv[1], qv[2], "request", "request", a, b))
        if not found or len({bd.unit.dim for bd in found if bd.unit is not None}) != 1:
            return None
        return found[-1]

    def _request_quantity_for(self, node: Node, dim: Optional[Dimension] = None) -> Optional[Binding]:
        """The request's quantity a bare numeral of the working repeats: the request states that number with a unit, every
        such quantity has one dimension (``dim`` when the symbol's reference quantity fixes one), and the answer gave the number
        no unit of its own. The working's number then stands for the request's quantity (units given only in the task)."""
        v = value_of(node)
        if v is None or v[2] is not None or v[3] or v[1] is None:
            return None
        found: list[Binding] = []
        for qnode, a, b in self.request.quantities[:256]:
            q = value_of(qnode)
            if q is None or q[1] is None or q[2] is None or q[2].unknown or q[2].dim is None or q[3] or q[0] != v[0]:
                continue
            if dim is not None and not q[2].dim.same_physical(dim):
                continue
            found.append(Binding("", q[0], q[1], q[2], "request", "request", a, b))
        dims = {bd.unit.dim for bd in found if bd.unit is not None}
        if not found or len(dims) != 1 or len({" ".join(bd.unit.text.split()) for bd in found if bd.unit is not None}) != 1:
            return None
        return found[0]

    def _written_change(self, written: Node) -> Optional[list[tuple[Num, Binding]]]:
        """The two numerals of a substituted difference ``(a − b)`` when each repeats a quantity the request states in one unit
        (both in °C, or both in m s⁻¹), each as a binding in that unit (kelvin for an offset scale: a difference of two Celsius
        temperatures is the same difference in kelvin), else None."""
        node = written
        if not (isinstance(node, BinOp) and node.op == "-" and isinstance(node.left, Num) and isinstance(node.right, Num)):
            return None
        out: list[tuple[Num, Binding]] = []
        units: set[str] = set()
        for leaf in (node.left, node.right):
            rq = self._request_quantity_for(leaf)
            if rq is None or rq.unit is None:
                return None
            units.add(" ".join(rq.unit.text.split()))
            unit = _KELVIN if is_affine_unit_expr(rq.unit) else rq.unit
            if unit is None:
                return None
            out.append((leaf, replace(rq, unit=unit, wrapper="")))
        return out if len(units) == 1 else None

    def _request_difference_for(self, numeral: Num, sign: int = 1) -> Optional[Binding]:
        """The change a bare numeral of the working states between two of the request's quantities of one unit ("from 20 °C to
        70 °C" for a ΔT of 50, "from 5.0 to 20 m s⁻¹" for a Δv of 15): exactly one pair of the request's quantities in one unit
        differs by ``value``. A change on an offset scale (°C, °F) is the same change in kelvin. Returns the change as a binding
        in that unit (in kelvin for an offset scale), else None (repair round 5, ADV5-03: the ΔT of Q = mcΔT left the working's
        200 g unread, so 200 × 4200 × 50 passed with the request's c in J kg⁻¹ K⁻¹). The binding's number is the working's own
        numeral."""
        value = sign * numeral.number.value
        found: list[Binding] = []
        quants = []
        for qnode, a, b in self.request.quantities[:64]:
            q = value_of(qnode)
            if q is None or q[1] is None or q[2] is None or q[2].unknown or q[2].dim is None or q[3]:
                continue
            quants.append((q, a, b))
        for i, (qa, a1, b1) in enumerate(quants):
            for qb, _a2, b2 in quants[i + 1:]:
                if " ".join(qa[2].text.split()) != " ".join(qb[2].text.split()) or abs(qb[0] - qa[0]) != value or value == 0:
                    continue
                unit = _KELVIN if is_affine_unit_expr(qa[2]) else qa[2]
                if unit is None:
                    continue
                found.append(Binding("", value, numeral.number, unit, "request", "request", a1, b2))
        return found[0] if len(found) == 1 else None

    def _law_uses(self, rel: Relation) -> list[Relation]:
        """The substitutions that apply the law ``rel`` states: a ``sub`` planned for its recorded formula, or the next link of
        its own chain (``BMI = m/h = 81/1.80``)."""
        head = _first(rel.left)
        name = head.name if isinstance(head, Sym) else ""
        out = []
        for r in self.relations:
            if r.kind != "sub":
                continue
            if (r.formula is not None and r.formula.name == name and r.formula.statement_id in rel.statement_ids) or r.left is rel.right:
                out.append(r)
        return out

    def _traced_dims(self, uses: list[Relation], variables: set[str]) -> dict[str, Dimension]:
        """The dimension of each variable of a law that the working substitutes by a bare numeral the request states with a
        unit (:meth:`_request_quantity_for`); a variable the answer binds with a unit is read from its binding instead."""
        out: dict[str, Dimension] = {}
        for r in uses:
            for name, node in r.pairs:
                if name not in variables or name in out or self._symbol_dim(name) is not None:
                    continue
                q = fixed_quantity(name, self.profile.key, request_text=self.request.text)
                bd = self._request_quantity_for(node, q.dimension if q is not None else None)
                if bd is not None and bd.unit is not None and bd.unit.dim is not None:
                    out[name] = bd.unit.dim
        return out

    def _reference_formulas(self) -> None:
        """The reference checks of a law the answer states (``Y = f``, Sciences and Mathematics profiles):

        * ST-REF-001 (stem_wrong_formula): the symbol's reference quantity is fixed (:func:`.reference.fixed_quantity`, by the
          symbol itself, the unit of a result stated for it, or the request) and ``f`` has another dimension. The dimension is
          read only when every numeral of ``f`` is a pure coefficient (:func:`.reference.pure_coefficient_dimension`), from the
          units the answer states, the request's quantities the working substitutes, or the reference quantities;
        * ST-REF-002 (stem_wrong_formula): the quantity is fixed, ``f`` has exactly the variables of one or more data-booklet
          laws for it (:func:`.reference.booklet_laws`), and differs from every one of them as a function (disjoint
          enclosures at a sample point, :func:`.reference.differs_as_function`): ``S_n = n(u₁ + u_n)`` for ``(n/2)(u₁ + u_n)``,
          ``T = 2π√(g/l)`` for ``2π√(l/g)``, ``P = IR`` for ``I²R``;
        * ST-DIM-001 (stem_dimension_error): a chain that applies the law states a result whose unit has another dimension
          than ``f`` under the same readings (``p = mv``, then ``p = 4.0 × 3.0 = 12 N``), when no ST-REF-001 names the law.

        A symbol the table does not fix, or a side whose dimension is unknown, gives nothing (a miss, never a false alarm)."""
        if self.profile.mode not in ("sciences", "mathematics") or not self.reference_checks:
            return
        seen: set[tuple[str, str]] = set()
        stated = self._stated_values()
        for rel in self.relations:
            if rel.kind != "formula" or rel.outcome != "formula":
                continue
            head, rhs = _first(rel.left), _first(rel.right)
            if not isinstance(head, Sym) or head.kind != "symbol" or rhs is None or unsupported_reasons(rhs) or is_closed(rhs):
                continue
            name = head.name
            if name in _syms(rhs):
                continue  # a relation that holds the symbol on both sides is an equation, not a law for it
            key = (name, shape_key(rhs))
            if key in seen:
                continue
            seen.add(key)
            uses = self._law_uses(rel)
            results = [e for e in (self.final_of_operand.get(id(rel.right)),) + tuple(self.final_of_operand.get(id(u.right)) for u in uses) if e is not None]
            result_nodes = [e["node"] for e in results]
            stated_b = [b for b in self.scope.bindings.get(name, ()) if b.source != "root"]
            result_dims = tuple(dict.fromkeys([b.unit.dim for b in stated_b if b.unit is not None and not b.unit.unknown and b.unit.dim is not None]
                                              + [v[2].dim for n in result_nodes if (v := value_of(n)) is not None and v[2] is not None
                                                 and not v[2].unknown and v[2].dim is not None]))
            q = fixed_quantity(name, self.profile.key, result_dims=result_dims, request_text=self.request.text)
            variables = _syms(rhs)
            traced = self._traced_dims(uses, variables)
            d = None
            if self.profile.mode == "sciences":
                d = pure_coefficient_dimension(rhs, lambda n: self._law_symbol_dim(n, traced), stated_values=stated)
            if q is not None and d is not None and not d.same_physical(q.dimension):
                booklet = booklet_formulas(q.key, self.profile.key)
                named = "; the data booklet gives " + " and ".join(f.text for f in booklet) if booklet else ""
                self.finding("ST-REF-001", f"wrong formula (stem_wrong_formula): the law '{name} = {render(rhs)[:120]}' gives {name} the dimension "
                                           f"{dimension_text(d)}, but {name} is the {q.name} ({q.si_unit}; {dimension_text(q.dimension)}){named}. The STEM "
                                           f"reference fixes what the symbol is; the dimension is read from the stated units, every numeral a pure "
                                           f"coefficient", rel.statement_ids, rel.start, rel.end)
                continue
            if q is not None and self._booklet_form(rel, name, q, variables, traced):
                continue
            if d is None:
                continue
            for node in result_nodes:
                v = value_of(node)
                if v is None or v[2] is None or v[2].unknown or v[2].dim is None or v[2].dim.same_physical(d):
                    continue
                if any(f.code == "ST-DIM-001" and getattr(node, "start", -1) >= f.start and getattr(node, "end", -1) <= f.end
                       or f.code == "ST-DIM-001" and f.start == getattr(node, "start", -1) for f in self.findings):
                    break  # the chain's own dimension finding already names this result
                self.finding("ST-DIM-001", f"the law '{name} = {render(rhs)[:120]}' gives {name} the dimension {dimension_text(d)} under the stated "
                                           f"units, but the working states '{render(node)[:80]}' ({dimension_text(v[2].dim)}) for it", tuple(dict.fromkeys(
                                               rel.statement_ids + tuple(x for u in uses for x in u.statement_ids))), rel.start, rel.end)
                break

    def _booklet_form(self, rel: Relation, name: str, q, variables: set[str], traced: dict[str, Dimension]) -> bool:
        """ST-REF-002 for the law ``rel`` of the fixed quantity ``q``: True when it was named. Silent when no booklet law of the
        quantity has exactly its variables, when one of them agrees with it at both sample points, or when a variable's
        stated dimension is not the dimension the reference gives that letter (the answer uses the letter for another
        quantity)."""
        laws = [law for law in booklet_laws(self.profile.key) if law.quantity == q.key and law.variables == frozenset(variables)]
        if not laws:
            return False
        for var in variables:
            known = self._symbol_dim(var) or traced.get(var)
            ref = {r.dimension for r in quantities_for(var, self.profile.key)}
            if known is not None and ref and not any(known.same_physical(r) for r in ref):
                return False
        readings = [n for n in rel.right.readings if n is not None]
        if not readings or any(not differs_as_function(reading, law.rhs, frozenset(variables)) for reading in readings for law in laws):
            return False
        shown = " or ".join(dict.fromkeys(law.text for law in laws))
        self.finding("ST-REF-002", f"wrong formula (stem_wrong_formula): the law '{name} = {render(readings[0])[:120]}' has the variables of the data "
                                   f"booklet's {shown} for the {q.name}, but it is a different function of them (they differ at a sample value of "
                                   f"{', '.join(sorted(variables))}). The STEM reference fixes what the symbol is; the comparison is exact interval "
                                   f"arithmetic on the two laws", rel.statement_ids, rel.start, rel.end)
        return True

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
        self._inline_givens(req_by_symbol)

    def _inline_givens(self, req_by_symbol: dict[str, list[Binding]]) -> None:
        """Givens the answer writes inline (repair round 5, ADV5-04): a value with a unit that the working substitutes for a
        symbol the answer binds nowhere else ('F = ma = 2.0 kg × 4.0 m s⁻²'), or a plain value statement the working then
        substitutes ('c = 0.200 mol dm⁻³ and V = 0.0400 dm³, so n = cV = 0.200 × 0.0400'), is read against the request's
        binding of the symbol or its quantities of the same dimension, as a Given is (``giv``, a warning: the identity of a
        symbol across the request and the answer is a reading). A value the answer derives is no given: none is read when a
        chain of the answer ends in a value of that dimension, or when the value is the end of a chain."""
        derived_dims: list = []
        derived_values: set = set()
        for fv in self.final_values:
            v = value_of(fv["node"])
            if v is None:
                continue
            if not fv.get("computed"):
                continue  # 'c = 0.200 mol dm⁻³' states a value; it derives nothing
            if v[2] is not None and not v[2].unknown and v[2].dim is not None:
                derived_dims.append(v[2].dim)
            derived_values.add((v[0], " ".join(v[2].text.split()) if v[2] is not None else ""))

        def candidates(name: str, unit) -> list[Binding]:
            cands = list(req_by_symbol.get(name, []))
            if not cands:
                for qnode, a0, b0 in self.request.quantities[:64]:
                    q = value_of(qnode)
                    if q is None or q[2] is None or q[1] is None or q[2].unknown or q[2].dim is None:
                        continue
                    if q[2].dim.same_physical(unit.dim):
                        cands.append(Binding(name, q[0], q[1], q[2], "request", "request", a0, b0, wrapper=q[3]))
            return cands

        seen: set[tuple[str, int]] = set()
        for name, blist in list(self.scope.bindings.items()):
            if any(b.source == "given" for b in blist):
                continue  # read as a Given above
            for b in blist:
                if b.source not in ("statement", "let") or b.unit is None or b.unit.unknown or b.unit.dim is None:
                    continue
                if any(d.same_physical(b.unit.dim) for d in derived_dims) or (b.value, " ".join(b.unit.text.split())) in derived_values:
                    continue
                if not any(r.kind == "sub" and any(n == name for n, _w in r.pairs) and r.start > b.start for r in self.relations):
                    continue  # a value the working never substitutes is no given of it
                cands = candidates(name, b.unit)
                if not cands or (name, b.start) in seen:
                    continue
                seen.add((name, b.start))
                node = Quantity(b.number, b.unit, b.start, b.end)
                self.add(kind="giv", outcome="check", statement_ids=(b.statement_id,), start=b.start, end=b.end, op="=", right=Operand((node,), b.start, b.end),
                         left=Operand((Sym(name, start=b.start, end=b.start),), b.start, b.start), candidates=tuple(cands[:8]),
                         reason=f"the value stated for {name} and substituted by the working, against " + (
                             "the request's binding of the same symbol" if name in req_by_symbol else "the request's quantities of the same dimension"))
        for rel in list(self.relations):
            if rel.kind != "sub":
                continue
            for name, written in rel.pairs:
                node = written.arg if isinstance(written, Neg) else written
                if not isinstance(node, Quantity) or node.unit is None or node.unit.unknown or node.unit.dim is None:
                    continue
                if [b for b in self.scope.bindings.get(name, ()) if b.source not in ("substitution", "root")]:
                    continue  # the answer binds the symbol itself: that binding is what is read
                if any(d.same_physical(node.unit.dim) for d in derived_dims):
                    continue
                v = value_of(written)
                if v is None or (v[0], " ".join(node.unit.text.split())) in derived_values or (name, node.start) in seen:
                    continue
                cands = candidates(name, node.unit)
                if not cands:
                    continue
                seen.add((name, node.start))
                self.add(kind="giv", outcome="check", statement_ids=rel.statement_ids, start=node.start, end=node.end, op="=",
                         right=Operand((written,), node.start, node.end), left=Operand((Sym(name, start=node.start, end=node.start),), node.start, node.start),
                         candidates=tuple(cands[:8]),
                         reason=f"the value the working substitutes for {name} ({node.number.text} {node.unit.text}) against " + (
                             "the request's binding of the same symbol" if name in req_by_symbol else "the request's quantities of the same dimension"))
        self._bare_givens(req_by_symbol, seen, derived_values)

    #: the most quantities of one dimension (or one unit, for a change) the request may state for a bare value of the working
    #: to be read against the one of them the working leaves unused
    _MAX_BARE_GIVEN_POOL = 2
    #: the most values one substitution may introduce for its bare values to be read against the request
    _MAX_BARE_GIVEN_PAIRS = 16

    def _bare_givens(self, req_by_symbol: dict[str, list[Binding]], seen: set[tuple[str, int]], derived_values: set) -> None:
        """Bare values the working uses in place of one of the request's quantities (accuracy round 1, ADV6-04: '(v − u)/t =
        (25 − 15)/5.0' for a car that speeds up from 10 m s⁻¹ to 25 m s⁻¹; 'n = m/M = 8.55/58.5' for 5.85 g of the solid;
        'ΔT = 80 − 30' for water heated from 20 °C to 80 °C). Two shapes are read, each against exactly one quantity of the
        request, the one the working leaves unused:

        * a bare numeral substituted for a symbol the answer binds nowhere else, whose quantity the STEM reference fixes (no
          constant: g, c, R ...): every other value of the substitution repeats one of the request's quantities (a
          substitution of the request's givens), the request states at most two quantities of the numeral's dimension, the
          working's other numerals repeat all of them but one, and the numeral repeats none;
        * a change written as the difference of two bare numerals ('ΔT = 80 − 30', or substituted for a Δ symbol): one end
          repeats one of exactly two quantities the request states in one unit, the other end repeats neither.

        A numeral is never read so when it repeats the quantity as written, converted to SI or as a change of two of them;
        when it lies within a factor of 10ⁿ, 2 × 10ⁿ or ½ × 10ⁿ of it (a unit the reference does not convert, a radius from a
        diameter); when it is zero (from rest); or when the answer states the number anywhere else (its prose, any binding,
        a value it derives). The numeral is then compared with that quantity, read in its unit (``giv``, a warning: the
        identity of a symbol across the request and the answer is a reading)."""
        if self.request_mode or self.profile.computer_science:
            return
        quants: list[Binding] = []
        for qnode, a0, b0 in self.request.quantities[:64]:
            q = value_of(qnode)
            if q is None or q[1] is None or q[2] is None or q[2].unknown or q[2].dim is None or q[3]:
                continue
            quants.append(Binding("", q[0], q[1], q[2], "request", "request", a0, b0))
        if not quants:
            return
        stated: set[Fraction] = set()
        for pv in self.prose_values:
            v = value_of(pv.node)
            if v is not None:
                stated.add(abs(v[0]))
        for blist in self.scope.bindings.values():
            stated |= {abs(b.value) for b in blist if b.source not in ("substitution", "root")}
        stated |= {abs(v) for v, _u in derived_values}

        def repeats(value: Fraction, q: Binding) -> bool:
            scale = unit_scale(q.unit)
            return value == q.value or (scale is not None and value == q.value * scale)

        def near(value: Fraction, q: Binding) -> bool:
            # within a factor of 10ⁿ, 2 × 10ⁿ or ½ × 10ⁿ of the quantity (bounded: |n| ≤ 24)
            if value == 0 or q.value == 0:
                return True
            r = abs(value / q.value)
            for _ in range(24):
                if r >= 10:
                    r /= 10
                elif r < 1:
                    r *= 10
                else:
                    break
            return r in (1, 2, 5)

        def unusable(value: Fraction, cand: Binding) -> bool:
            return value == 0 or abs(value) in stated or near(value, cand) or any(repeats(value, q) for q in quants)

        def plan(name: str, numeral: Num, cand: Binding, rel_ids: tuple[str, ...], why: str) -> None:
            if (name, numeral.start) in seen:
                return
            if not _miscopied(numeral.number.text, cand.number.text, numeral.number.value, cand.number.value):
                # a value of another size than a miscopy of the request's quantity ('340' for the 20 m s⁻¹ of a moving car, the
                # speed of sound; '100' for a room at 25 °C, the boiling point) is a value of the answer's own, often from subject
                # knowledge, not the request's quantity written wrongly (accuracy round 2, V1-STEM-GIV-FA)
                return
            seen.add((name, numeral.start))
            node = Quantity(numeral.number, cand.unit, numeral.start, numeral.end)
            number = cand.number
            if number.trailing_zeros and not number.has_point and not number.scientific:
                # the integer trailing-zero rule (section 5.1): the request's whole number with trailing zeros ('10 m s⁻¹') is
                # read to the smallest significant-figure count of its other measured quantities ('25 m s⁻¹', '5.0 s')
                sigs = [q.number.sig_figs for q in quants if q is not cand and not (q.number.trailing_zeros and not q.number.has_point and not q.number.scientific)]
                if sigs:
                    place = min(number.trailing_zeros, max(number.digit_count - max(1, min(sigs)), 0))
                    number = replace(number, trailing_zeros=place)
            self.add(kind="giv", outcome="check", statement_ids=rel_ids, start=numeral.start, end=numeral.end, op="=",
                     right=Operand((node,), numeral.start, numeral.end), left=Operand((Sym(name, start=numeral.start, end=numeral.start),), numeral.start, numeral.start),
                     candidates=(replace(cand, symbol=name, number=number),),
                     reason=f"the bare value {numeral.number.text} the working uses for {name}, read in the unit of the request's {cand.number.text} "
                            f"{cand.unit.text if cand.unit is not None else ''} ({why})")

        def change_ends(name: str, node: Node, rel_ids: tuple[str, ...]) -> None:
            if not (name.startswith("Δ") and isinstance(node, BinOp) and node.op == "-" and isinstance(node.left, Num) and isinstance(node.right, Num)):
                return
            ends = [(leaf, self._request_quantity_for(leaf)) for leaf in (node.left, node.right)]
            known = [(leaf, rq) for leaf, rq in ends if rq is not None]
            if len(known) != 1 or known[0][1].unit is None:
                return
            unit_text = " ".join(known[0][1].unit.text.split())
            same_unit = [q for q in quants if " ".join(q.unit.text.split()) == unit_text]
            if len(same_unit) != self._MAX_BARE_GIVEN_POOL:
                return
            others = [q for q in same_unit if q.value != known[0][0].number.value]
            [odd] = [leaf for leaf, rq in ends if rq is None]
            if len(others) != 1 or unusable(odd.number.value, others[0]):
                return
            plan(name, odd, others[0], rel_ids, "the other end of a change whose one end repeats the request's quantity in that unit")

        for rel in list(self.relations):
            if rel.kind == "binding" and rel.outcome == "binding":
                head, body = _first(rel.left), _first(rel.right)
                if isinstance(head, Sym) and body is not None:
                    change_ends(head.name, body, rel.statement_ids)
                continue
            if rel.kind != "sub":
                continue
            # the values the substitution introduces for symbols bound nowhere else are recorded as substitution bindings, not
            # as pairs of the check ('n = m/M = 8.55/58.5' with only M bound: m introduces 8.55)
            leaves = {(n.start, n.end): n for side in (_first(rel.left), _first(rel.right)) if side is not None for n in walk(side) if isinstance(n, Num)}
            introduced = [(b.symbol, leaves[(b.start, b.end)]) for name in rel.unbound for b in self.scope.substitutions.get(name, ())
                          if b.statement_id in rel.statement_ids and (b.start, b.end) in leaves]
            pairs = [*rel.pairs, *introduced]
            if len(pairs) > self._MAX_BARE_GIVEN_PAIRS:
                continue  # a substitution of more values than a working writes by hand is not read (bounded: pairs × pairs)
            numerals = [w for _n, w in pairs if isinstance(w, Num)]
            for name, written in pairs:
                change_ends(name, written, rel.statement_ids)
                if not isinstance(written, Num) or name in req_by_symbol:
                    continue
                if [b for b in self.scope.bindings.get(name, ()) if b.source not in ("substitution", "root")]:
                    continue  # the answer binds the symbol itself: that binding is what is read
                q = fixed_quantity(name, self.profile.key, request_text=self.request.text)
                if q is None or q.dimension is None:
                    continue
                if any(c.dim.same_physical(q.dimension) for c in constants_for_symbol(name, self.profile.key)):
                    continue  # a constant (g, c, R ...): its value is the data booklet's, not the request's
                pool = [b for b in quants if b.unit is not None and b.unit.dim is not None and b.unit.dim.same_physical(q.dimension)
                        and not is_affine_unit_expr(b.unit)]
                if not pool or len(pool) > self._MAX_BARE_GIVEN_POOL:
                    continue
                if name.startswith("Δ") and self._request_difference_for(written) is not None:
                    continue
                if not all(any(repeats(other.number.value, q) for q in quants) for other in numerals if other is not written):
                    # another value of the substitution is none of the request's (the answer's own result carried on, a
                    # conversion factor: 'E = 6.0 × 3.6 × 10⁶' after 'E = Pt = 2.0 × 3.0 = 6.0 kW h'): the working is no
                    # substitution of the request's givens, so none of its values is read as one
                    continue
                left = [b for b in pool if not any(other is not written and repeats(other.number.value, b) for other in numerals)]
                if len(left) != 1 or unusable(written.number.value, left[0]):
                    continue
                plan(name, written, left[0], rel.statement_ids, "the one quantity of that dimension the working's other values leave unused")

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


def _distinct(b1: Binding, b2: Binding) -> bool:
    """Two bindings of one symbol that state different values as written (in SI when both units read exactly): "R = 10 Ω"
    and "R = 20 Ω" are two values, although a whole number with a trailing zero read at one significant figure would let
    them meet within rounding (:meth:`.scope.Binding.same_as`); "t = 5.0 s" and "t = 5000 ms" are one."""
    a, b = b1.si, b2.si
    if a is not None and b is not None and b1.unit is not None and b2.unit is not None:
        return a != b
    return b1.value != b2.value or (b1.unit is None) != (b2.unit is None)


#: the largest multiple of the unknown in an exponent that the exponential reading turns into a power (the parser's bound)
_MAX_EXP_MULTIPLE = 12


def _integer_multiple(node: Node, name: str) -> Optional[int]:
    """``c`` when ``node`` is ``c·name`` with ``c`` a non-zero integer (``−8k``, ``k``, ``−k``, ``3k``, ``k × 2``), else None."""
    sign = 1
    cur = node
    while isinstance(cur, Neg):
        sign, cur = -sign, cur.arg
    if isinstance(cur, Sym) and cur.name == name and cur.kind == "symbol":
        return sign
    if isinstance(cur, BinOp) and cur.op == "*":
        a, b = cur.left, cur.right
        if isinstance(a, Sym):
            a, b = b, a
        coeff_sign = 1
        while isinstance(a, Neg):
            coeff_sign, a = -coeff_sign, a.arg
        if isinstance(a, Num) and isinstance(b, Sym) and b.name == name and b.kind == "symbol" and a.number.value.denominator == 1 and a.number.value:
            return sign * coeff_sign * int(a.number.value)
    return None


def _exp_unknown(node: Node) -> Optional[str]:
    """The one symbol of the exponent of a symbolic power of e (``e^(−8k)``: k), when the exponent is an integer multiple of it."""
    if not (isinstance(node, Unsupported) and node.name == "exp" and node.arg is not None):
        return None
    names = [n for n in symbols(node.arg)]
    if len(names) != 1:
        return None
    return names[0] if _integer_multiple(node.arg, names[0]) is not None else None


def _exp_rewrite(node: Node, name: str, sign: int, u: Sym, depth: int = 0) -> Optional[Node]:
    """``node`` with every ``e^(c·name)`` written as ``u^|c|`` (``u = e^(sign·name)``, every ``c`` of that sign); None when
    ``name`` stands anywhere else, a multiple has the other sign or is beyond the bound, or a node is outside the rewrite."""
    if depth > 64:
        return None
    if isinstance(node, Unsupported):
        if node.name != "exp" or node.arg is None:
            return None
        c = _integer_multiple(node.arg, name)
        if c is None or (c > 0) != (sign > 0) or abs(c) > _MAX_EXP_MULTIPLE:
            return None
        return u if abs(c) == 1 else Pow(u, abs(c), node.start, node.end)
    if isinstance(node, Sym):
        return None if node.name == name else node
    if isinstance(node, (Num, Quantity)):
        return node
    if isinstance(node, BinOp):
        left, right = _exp_rewrite(node.left, name, sign, u, depth + 1), _exp_rewrite(node.right, name, sign, u, depth + 1)
        return None if left is None or right is None else BinOp(node.op, left, right, node.start, node.end, node.written, node.implicit)
    if isinstance(node, Neg):
        arg = _exp_rewrite(node.arg, name, sign, u, depth + 1)
        return None if arg is None else Neg(arg, node.start, node.end)
    if isinstance(node, Pow):
        base = _exp_rewrite(node.base, name, sign, u, depth + 1)
        return None if base is None else Pow(base, node.exp, node.start, node.end)
    if isinstance(node, Func):
        arg = _exp_rewrite(node.arg, name, sign, u, depth + 1)
        return None if arg is None or name in symbols(node.arg) else Func(node.name, arg, node.base, node.start, node.end)
    if isinstance(node, Root):
        arg = _exp_rewrite(node.arg, name, sign, u, depth + 1)
        return None if arg is None else Root(arg, node.index, node.start, node.end)
    return None


#: marks the request gives an item ('[2 marks]', '[3]', '(2 marks)')
#: (security round 1) Every quantifier of the bracket forms possessive: each is followed by a token its own characters cannot
#: begin (digits by a space, a plus, 'marks' or the closing bracket; a space by a digit, a plus, 'marks' or the bracket), so its
#: longest reading is the only one the rest can follow and the same annotations are read. The spaces after '[1' were split
#: between two or three quantifiers before failing (quadratic in the run) (tests/channel/test_security_round1_marks.py).
_MARKS_RE = re.compile(r"\[\s*+(\d{1,2}+)\s*+(?:marks?+)?+\s*+\]|\(\s*+(\d{1,2}+)\s*+marks?+\s*+\)")
#: A show-that request about a property of a number ("Show that 13 is prime", "... that √2 is irrational", "... that 91 is
#: not prime"): a proof, whose working is its reasons (repair round 5, ADV5-10).
#: (security round 1) Read as a yes or no only. The words between 'that' and 'is' were read by three quantifiers that all take
#: white space, so a request of 'Show that', a long run of spaces, 'is', another run and a word was split between them in every
#: way before failing (10 s on a 4,000-character request). The same requests are shown: either the space after 'that' runs
#: (three characters or more) right up to 'is', or what stands between that space and the space before 'is' is one to forty
#: characters that start and end with a visible character; each space is read once
#: (tests/stem/test_security_round1_relations.py).
_PROPERTY_SHOW_RE = re.compile(r"\bshow\s+that(?:\s{3,}+|\s++[^.?!\s](?:[^.?!]{0,38}[^.?!\s])?\s+)(?:is|are)\s+(?:not\s+)?(?:an?\s+)?(?:prime|composite"
                               r"|irrational|rational|even|odd|integer|whole\s+number|natural\s+number|perfect\s+(?:square|cube)|multiple\s+of|factor\s+of"
                               r"|divisible\s+by)\b")
#: A reason word in an answer ("so", "because", "since", "therefore", "hence", "thus", "it follows").
_REASONED_RE = re.compile(r"\b(?:so|because|since|therefore|hence|thus|it\s+follows|as\s+it)\b")
_IR_ORDER_SIGN = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥", "eq": "="}
#: Order signs of a comparison in symbols, and each with its sides swapped.
_MATH_ORDER_OPS = frozenset({"<", "≤", ">", "≥", "⩽", "⩾"})
_FLIP_MATH = {"<": ">", ">": "<", "≤": "≥", "≥": "≤", "⩽": "⩾", "⩾": "⩽"}
#: Words that name a rounding right before a value ('To 1 s.f. this is', 'rounded to 2 d.p., it is', 'to two significant figures:')
#: or right after it ('0.7 to one significant figure', '0.69 (2 d.p.)').
_ROUNDING_WORDS_BEFORE_RE = re.compile(r"(?:\bto\s+(?:\d|one|two|three|four)\s*(?:s\.?\s?f\.?|sig(?:nificant)?\.?\s*fig(?:ure)?s?|d\.?\s?p\.?|decimal places?)"
                                       r"|\brounded(?:\s+(?:off|up|down))?"
                                       # 'which rounds to 50 mg dm⁻³', '38.4 °C to the nearest whole number is 38 °C' (accuracy round 1, ADV6-05)
                                       r"|\brounds(?:\s{1,3}(?:off|up|down))?|\bto\s{1,3}the\s{1,3}nearest\b)[^.;]{0,24}$")
#: a rounding's place: 'the nearest whole number', 'the nearest degree', '2 s.f.', 'two decimal places'
_ROUNDING_PLACE = (r"(?:the\s{1,3}nearest(?:\s{1,3}[a-z]{1,12}){1,2}|(?:\d|one|two|three|four)\s{0,3}(?:s\.?\s?f\.?|sig(?:nificant)?\.?\s{0,3}fig(?:ure)?s?|"
                   r"d\.?\s?p\.?|decimal\s{1,3}places?))")
#: the words between a value and its rounding stated in prose ('38.4 °C to the nearest whole number is 38 °C', '13.3 A, which
#: rounds to 13 A', '0.694 rounded to 2 s.f. is 0.69'): a rounding phrase with its place, or 'rounds to' / 'rounded to', then
#: at most a copula or a verb of result; nothing else (a plain 'to' between two values is a range or a change, never read).
#: Bounded: every quantifier is bounded and the text between is at most 64 characters
_PROSE_ROUNDING_BETWEEN_RE = re.compile(
    r"\s{0,3},?\s{0,3}(?:which\s{1,3})?(?:(?:is|was)\s{1,3})?"
    r"(?:(?:rounded|rounds)(?:\s{1,3}(?:off|up|down))?\s{1,3}to(?:\s{1,3}" + _ROUNDING_PLACE + r")?|to\s{1,3}" + _ROUNDING_PLACE + r")"
    r"\s{0,3},?\s{0,3}(?:(?:this|that|it)\s{1,3})?(?:(?:is|was|gives|becomes)\s{0,3})?",
    re.IGNORECASE)
_ROUNDING_WORDS_AFTER_RE = re.compile(r"\s*\(?\s*(?:to|correct to)?\s*(?:\d|one|two|three|four)\s*(?:s\.?\s?f\.?|sig(?:nificant)?\.?\s*fig(?:ure)?s?|"
                                      r"d\.?\s?p\.?|decimal places?)\b")
_FLIP_ORDER = {"lt": "gt", "le": "ge", "gt": "lt", "ge": "le", "eq": "eq"}


#: What gives a value in prose as the input a model is evaluated at (ST-RANGE-001): a preposition or conjunction of a
#: condition, with at most a determiner and three words between it and the value ("at 60 °C", "for a storm of 120 mm", "at a
#: temperature of 90 °C", "when the temperature is 90 °C"); "for every 10 °C" is a step, not an input.
_INPUT_BEFORE_RE = re.compile(r"\b(?:at|for|when|if|with)\s+(?!(?:every|each|per)\b)(?:(?:a|an|the)\s+)?(?:[^\W\d_]+\s+){0,3}$", re.IGNORECASE)
#: A value followed by "per ...", "/", "a year", "each" or "every" is a rate or a step ("0.08 °C per year", "2 ppm a year").
_RATE_AFTER_RE = re.compile(r"\s*(?:per\b|/|an?\s+(?:year|month|week|day|hour|minute|second|decade|century)\b|each\b|every\b)", re.IGNORECASE)
#: a year an evaluating statement names as the model's input: "In 2100", "by 2050", "for the year 2030", "t = 2100", "(2100 − 2000)"
_YEAR_INPUT_RE = re.compile(r"(?:\b(?:in|by|for|at|until|till|reach(?:es|ed)?|year|t\s*=|y\s*=)\s+(?:the\s+year\s+)?|\(\s*)(?P<y>1[0-9]{3}|2[0-9]{3})(?![\d.,]\d)",
                            re.IGNORECASE)
#: words before a caveat cue that negate it ("This is not an extrapolation", "the spring is not unreliable")
_CAVEAT_NEGATION_RE = re.compile(r"\b(?:not|no|never|nothing|hardly|without|isn['’]t|aren['’]t|wasn['’]t|is\s+n['’]t)\b[^.;:!?]{0,24}$", re.IGNORECASE)


#: a probability written as the head of a chain: "P(A ∪ B)", "P(A|B)", "P(X = 2)", "the probability"
_PROBABILITY_HEAD_RE = re.compile(r"(?:^|\s)P\s*\(.{1,40}\)\s*$|\bprobability\b", re.IGNORECASE)
#: the request's probabilities of one event and of two events together ("P(A) = 0.6", "P(A ∩ B) = 0.3", "P(A and B) = 0.3")
_PROB_SINGLE_RE = re.compile(r"\bP\s*\(\s*([A-Z])\s*\)\s*=\s*(\d+(?:\.\d+)?|\.\d+)")
_PROB_JOINT_RE = re.compile(r"\bP\s*\(\s*([A-Z])\s*(?:∩|⋂|\\cap|and|n)\s*([A-Z])\s*\)\s*=\s*(\d+(?:\.\d+)?|\.\d+)")
_NEGATED_BEFORE_RE = re.compile(r"\b(?:not|never|no|n['’]t|neither|nor)\b[^.;:!?]{0,24}$")


def _stated_relation(answer_lower: str, a: str, b: str) -> str:
    """``exclusive`` or ``independent`` when the answer states that the events are so (not negated in the words before the
    cue), else ''. Bounded: the first 64 occurrences of each cue in the first 400,000 characters."""
    for cue, kind in (("mutually exclusive", "exclusive"), ("independent", "independent")):
        k = answer_lower.find(cue)
        seen = 0
        while k >= 0 and seen < 64:
            seen += 1
            before = answer_lower[max(0, k - 60):k]
            if not _NEGATED_BEFORE_RE.search(before) and (f"{a} and {b}" in before or f"{b} and {a}" in before or "events" in before or "they" in before):
                return kind
            k = answer_lower.find(cue, k + len(cue))
    return ""


def _half_unit(text: str) -> Fraction:
    """Half a unit in the last written digit of a decimal written as ``text`` (``0.3`` -> 1/20; an integer is exact)."""
    if "." not in text:
        return Fraction(0)
    return Fraction(1, 2 * 10 ** len(text.split(".", 1)[1]))


def _gap_start(item: MathItem) -> int:
    """The offset at which the item's prose gap (``gap_before``) begins: located in the statement's text right before the item,
    so a delimiter between the prose and the maths (``$``, ``\\(``) is not counted as part of it."""
    gap = item.gap_before
    rel = item.start - item.statement_start
    k = item.statement_text.rfind(gap, 0, max(rel, 0)) if gap else -1
    return item.statement_start + k if k >= 0 else item.start - len(gap)


#: the total of a two-set count statement: "In a group of 120 students", "Of the 80 pupils in a class", "A survey of 200 people"
_SET_TOTAL_RE = re.compile(r"\b(?:group|class|sample|survey|school|club|set|year|population|team)\s+of\s+(\d{1,6})\b|\b[Oo]f\s+(?:the\s+)?(\d{1,6})\s+"
                           r"(?:students|pupils|people|members|children|adults|customers|patients|participants|workers|employees|voters)\b")
#: a count of a two-set count statement: "70 study French", "65 study Spanish", "20 study both", "10 study neither", "10 play none"
_SET_COUNT_RE = re.compile(r"\b(\d{1,6})\s+(?:of\s+them\s+)?(?:study|studies|take|takes|like|likes|play|plays|own|owns|have|has|speak|speaks|chose|"
                           r"choose|prefer|prefers|use|uses|read|reads|watch|watches|eat|eats|drink|drinks|visit|visited|attend|attends|do|does|keep|keeps)\s+"
                           r"(both|neither|none|[A-Z][a-z]{1,20}|[a-z]{3,20})\b")
_NUMERAL_RE = re.compile(r"(?<![\d.])\d{1,6}(?![\d.])")
#: a sentence of plain prose: up to its full stop, question mark, exclamation mark or line break (bounded by the caller)
_PLAIN_SENTENCE_RE = re.compile(r"[^.!?\n]{1,2000}[.!?]?")
#: a range of data stated in words: "between 10 mm and 40 mm", "from 2 to 10 hours", "(from 2 to 10 hours)", "10–40 mm"
_PROSE_RANGE_RE = re.compile(r"(?:\bbetween\s+(?P<lo>\d[\d,]*(?:\.\d+)?)\s*(?:[A-Za-z°µ%][A-Za-z°µ%/²³⁻¹]{0,11}\s+)?and\s+(?P<hi>\d[\d,]*(?:\.\d+)?)"
                             r"|\bfrom\s+(?P<lo2>\d[\d,]*(?:\.\d+)?)\s*(?:[A-Za-z°µ%][A-Za-z°µ%/²³⁻¹]{0,11}\s+)?to\s+(?P<hi2>\d[\d,]*(?:\.\d+)?)"
                             r"|(?P<lo3>\d[\d,]*(?:\.\d+)?)\s*[–-]\s*(?P<hi3>\d[\d,]*(?:\.\d+)?))\s*(?P<u>[A-Za-z°µ%][A-Za-z°µ%/²³⁻¹]{0,11})?")
#: (security round 1) Where a stated range can start ('between', 'from' or a digit), and a run of digits and commas.
_PROSE_RANGE_START_RE = re.compile(r"\bbetween|\bfrom|\d")
_DIGIT_COMMA_RUN_RE = re.compile(r"[\d,]*+")


def _prose_ranges(text: str) -> list[re.Match]:
    """The matches ``_PROSE_RANGE_RE.finditer(text)`` gives, in linear time (security round 1).

    A range in figures ('10–40') starts at a digit and reads the digits and commas after it to the end of their run, then
    what follows the run: every digit of one run reaches the same end and the same text after it, so a range starts at all of
    them or at none, and the scan tried each in turn, reading the run again each time (quadratic: 11 s on a 20,000-digit
    request). Here the pattern is tried where a range can start; when a digit of a run starts none, the rest of the run is
    passed over, which the scan would have tried and failed. The matches are the pattern's own, at the places the scan finds
    them (tests/stem/test_security_round1_relations.py)."""
    out: list[re.Match] = []
    pos = 0
    while (c := _PROSE_RANGE_START_RE.search(text, pos)) is not None:
        m = _PROSE_RANGE_RE.match(text, c.start())
        if m is not None:
            out.append(m)
            pos = m.end()
        elif c.group().isalpha():
            pos = c.start() + 1
        else:
            pos = _DIGIT_COMMA_RUN_RE.match(text, c.start()).end()
    return out
#: the unit a request states for a variable right after its symbol: "R is the storm rainfall in mm", "h (in hours)"
_VARIABLE_UNIT_RE = re.compile(r"[^.;\n]{0,60}?\bin\s+([A-Za-z°µ%][A-Za-z°µ%/²³⁻¹]{0,11})")
#: words that say the givens of a question disagree: the answer states the contradiction itself (ST-GIVEN-004)
_INCONSISTENCY_NOTED_RE = re.compile(r"\b(?:inconsistent|contradict\w*|do(?:es)?\s+not\s+(?:agree|match|fit)|cannot\s+all\s+(?:hold|be\s+true)|"
                                     r"impossible|not\s+consistent|incompatible)\b", re.IGNORECASE)
#: the motion is uniform (the laws of uniform motion apply): ST-GIVEN-004
_UNIFORM_MOTION_RE = re.compile(r"\b(?:uniform(?:ly)?|constant\s+(?:acceleration|deceleration|rate)|steadily|at\s+a\s+steady\s+rate"
                                r"|free(?:ly)?[\s-]+fall(?:s|ing)?|falls?\s+freely|in\s+free\s+fall|dropped|released\s+from\s+rest|under\s+gravity)\b",
                                re.IGNORECASE)
#: A motion that the request or the answer says meets air resistance or drag is not uniform, unless it says to neglect it
#: (ST-GIVEN-004: a fall is uniform acceleration only without air resistance; repair round 2, own probes).
_RESISTED_MOTION_RE = re.compile(r"\b(?:air\s+resistance|drag|terminal\s+(?:velocity|speed)|friction)\b", re.IGNORECASE)
_RESISTANCE_NEGLECTED_RE = re.compile(r"\b(?:neglect(?:ing)?|ignor(?:e|ing)|no|without|negligible)\s+(?:the\s+)?(?:any\s+)?(?:air\s+resistance|drag|friction)\b"
                                      r"|\b(?:air\s+resistance|drag|friction)\s+(?:is|are|can\s+be)\s+(?:negligible|neglected|ignored)\b", re.IGNORECASE)
#: the scope phrase opening a statement: text with no relation sign up to its first comma or colon ("For car P,", "Momentum
#: of A:"), at most 80 characters (ST-SCOPE-002)
_LEAD_SCOPE_RE = re.compile(r"\s*([^=<>≤≥≈,:;\n]{2,80}?)\s*[,:]")
#: an object label after "of", "for" or "in" ("of A", "for B", "in car 2"): a lone capital letter or a one- or two-digit number
_BARE_LABEL_RE = re.compile(r"\b(?:of|for|in|on)\s+(?:the\s+)?(?:[a-z]+\s+)?([A-Z]|\d{1,2})(?![\w.])")
#: the object a qualifier after a value names: "mol of HNO₃", "kg (trolley A)": a chemical formula or a capitalised name
_OF_OBJECT_RE = re.compile(r"\s*(?:[A-Za-zµμ°⁻¹²³]{1,6}\s+){0,3}?(?:of|for)\s+([A-Z][A-Za-z0-9₀-₉()]{0,15})")
#: a sentence of the request that asks for something: it opens with a command or question word
_ASK_SENTENCE_RE = re.compile(r"(?:^|(?<=[.!?\n]))\s*(?:\(?[a-z]\)\s*)?(?:Calculate|Find|Determine|Work out|Compare|Explain|Show|State|Estimate|"
                              r"Predict|What|Which|How)\b[^.!?\n]{0,200}", re.IGNORECASE)
#: (security round 1) A sentence's end mark or line break, after which an asking sentence can start, and a run of white space.
_ASK_BOUNDARY_RE = re.compile(r"[.!?\n]")
_WHITE_RUN_RE = re.compile(r"\s*+")


def _ask_sentences(text: str) -> list[re.Match]:
    """The matches ``_ASK_SENTENCE_RE.finditer(text)`` gives, in linear time (security round 1).

    An asking sentence starts at the text's start or after an end mark or a line break, and reads the white space there
    before its command word. Every start inside one run of white space (each line break of a run of blank lines) reads the
    same space to the same end, and the same text after it, so all of them fail when the first fails, and so does the start
    at the end of the run; the scan tried each in turn, reading the run again each time (quadratic: 30 s on a request of
    20,000 line breaks). Here, when a start fails, the starts in its run of white space and at its end are passed over. The
    matches are the pattern's own, at the places the scan finds them (tests/stem/test_security_round1_relations.py)."""
    out: list[re.Match] = []
    start: Optional[int] = 0
    while start is not None and start <= len(text):
        m = _ASK_SENTENCE_RE.match(text, start)
        if m is not None:
            out.append(m)
            pos = m.end()
        else:
            pos = _WHITE_RUN_RE.match(text, start).end() + 1
        b = _ASK_BOUNDARY_RE.search(text, pos - 1)
        start = b.end() if b is not None else None
    return out


def _distinctive(mine: frozenset[str], other: frozenset[str]) -> frozenset[str]:
    """The words of one object's phrase that the other's lacks, with each label's last word ('trolley a': 'a') too."""
    d = mine - other
    return frozenset(d | {w.rsplit(" ", 1)[1] for w in d if " " in w})


def _matches_object(named: frozenset[str], d1: frozenset[str], d2: frozenset[str]) -> int:
    """1 or 2 when the words ``named`` share a distinctive word with exactly one of the two objects, else 0."""
    labels = named | {w.rsplit(" ", 1)[1] for w in named if " " in w}
    one, two = bool(labels & d1), bool(labels & d2)
    return 1 if one and not two else 2 if two and not one else 0


#: conjunctions that join two coordinated clauses, each of which may bind a symbol (ST-SCOPE-002)
_CLAUSE_JOINS = (" and ", " while ", " whereas ", " but ")


def _clause_cut(text: str, i: int) -> bool:
    """``text[i]`` ends a clause: a comma, colon, semicolon, line break or relation sign, or sentence punctuation that is no
    decimal point ('2.0')."""
    ch = text[i]
    if ch in ";:\n,=":
        return True
    return ch in ".!?" and not (0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit())


def _clause_tail(text: str) -> str:
    """The last clause of ``text`` (bounded by the caller): after its last clause cut and its last joining conjunction."""
    cut = next((i for i in range(len(text) - 1, -1, -1) if _clause_cut(text, i)), -1)
    tail = text[cut + 1:]
    j = max(tail.lower().rfind(w) for w in _CLAUSE_JOINS)
    return tail[j + 1:] if j >= 0 else tail


def _clause_head(text: str) -> str:
    """The first clause of ``text`` (bounded by the caller): up to its first clause cut or joining conjunction."""
    end = next((i for i in range(len(text)) if _clause_cut(text, i)), len(text))
    head = text[:end]
    js = [j for j in (head.lower().find(w) for w in _CLAUSE_JOINS) if j >= 0]
    return head[:min(js)] if js else head


def _phrase_words(clause: str, chemistry: bool, *, units: Optional[StemProfile] = None) -> frozenset[str]:
    """The content words of a clause (ST-SCOPE-002): words of three or more letters that are no stopword and no change marker
    (an ordinal before an object noun is kept), an object's label right after a kept word ('trolley A', 'car 2'), and in a
    chemistry profile a one- or two-letter element symbol ('Mg'). With ``units`` (a profile), the clause follows a value,
    and the value's own unit at its start ('kg', 'mol dm⁻³') is left out."""
    toks: list[str] = []
    cur = ""
    for c in clause.replace("'s", " ").replace("’s", " "):  # bounded: the caller's clause is at most 160 characters
        if c.isascii() and (c.isalpha() or c.isdigit()) and (not cur or cur[-1].isdigit() == c.isdigit()):
            cur += c
            continue
        if cur:
            toks.append(cur)
        cur = c if c.isascii() and (c.isalpha() or c.isdigit()) else ""
    if cur:
        toks.append(cur)
    lowered = [t.lower() for t in toks]
    first = 0
    while units is not None and first < len(toks) and (toks[first].isdigit() or is_unit_atom(toks[first], bare_m=units.bare_m, tonne=units.tonne)):
        first += 1  # the value's unit, with its digits ('cm3')
    out: set[str] = set()
    for k in range(first, len(toks)):
        t, w = toks[k], lowered[k]
        if k > first and lowered[k - 1] in out and ((len(t) == 1 and t.isupper()) or (t.isdigit() and len(t) <= 2)):
            out.add(f"{lowered[k - 1]} {w}")  # an object's label: 'trolley A', 'car 2'
        elif t.isalpha() and len(w) >= 3 and w not in NOUN_PHRASE_STOPWORDS and (w not in CHANGE_MARKERS or _object_ordinal(lowered, k)):
            out.add(w)
        elif chemistry and t.isalpha() and t[:1].isupper() and len(t) <= 2 and t in ELEMENTS:
            out.add(t)  # an element symbol: 'of Mg'
    return frozenset(out)


def _rounded_chain_end(pos: int, full_operands: list, full_ops: list) -> Optional[Node]:
    """The value with a unit (or a per cent) that ends a chain after the stated value of its link ``pos`` when every later
    link is a rounding (``≈``) of a bare value: ``2.5 / 10 = 0.25 ≈ 0.3 m s⁻¹`` gives ``0.3 m s⁻¹`` for the link ``2.5 / 10 =
    0.25``. Each rounded value must lie within half a unit of its last written digit, or within a tenth, of the value before
    it, so a conversion made in a rounding step (``0.524 ≈ 52%``) ends nothing. None otherwise."""
    k = pos + 1
    if k >= len(full_operands):
        return None
    cur = _first(full_operands[k][0])
    while k < len(full_ops) and full_ops[k] in _APPROX and k + 1 < len(full_operands):
        nxt = _first(full_operands[k + 1][0])
        cv, nv = value_of(cur) if cur is not None else None, value_of(nxt) if nxt is not None else None
        if cv is None or nv is None or cv[2] is not None or cv[3] or nv[1] is None:
            return None
        gap = abs(cv[0] - nv[0])
        if gap > nv[1].half_width and gap > abs(nv[0]) / 10:
            return None
        if nv[2] is not None or nv[3] == "%":
            return nxt if k + 1 == len(full_operands) - 1 else None
        cur, k = nxt, k + 1
    return None


def _target_noun(seg: str) -> Optional[tuple[int, int]]:
    """The span of the first target noun (``TARGET_NOUNS``) written as a word in ``seg`` (bounded by the caller), or None."""
    low = seg.lower()
    best: Optional[tuple[int, int]] = None
    for noun in TARGET_NOUNS:
        k = low.find(noun)
        while k >= 0:
            if (k == 0 or not low[k - 1].isalpha()) and (k + len(noun) >= len(low) or not low[k + len(noun)].isalpha() or low[k + len(noun)] == "s"):
                if best is None or k < best[0]:
                    best = (k, k + len(noun))
                break
            k = low.find(noun, k + 1)
    return best


def _target_verb(before: str, after: str) -> Optional[tuple[str, bool]]:
    """What a clause says of a value and a target: ``("reach" | "exceed" | "miss", negated)``, read from the last six words
    before the target noun ('so it meets the', 'which does not reach the', 'falls short of the') or the passive after it ('the
    target of at least 80% is met', 'the target is not reached'); None when it says neither."""
    words = " ".join("".join(c.lower() if c.isalpha() or c == "'" else " " for c in before).split()).split()[-6:]
    tail = " ".join("".join(c.lower() if c.isalpha() or c == "'" else " " for c in after[:64]).split()).split()
    def kind_of(w: str) -> Optional[str]:
        if w in TARGET_REACH_VERBS:
            return "reach"
        if w in TARGET_EXCEED_VERBS:
            return "exceed"
        if w in TARGET_MISS_VERBS:
            return "miss"
        return None
    negation = ("not", "never", "fails", "failed", "fail", "failing")
    if len(words) >= 2 and words[-2:] in (["at", "the"], ["at", "its"], ["on", "the"], ["right", "at"]) or words[-1:] == ["at"]:
        # a value "at the limit" (the target): it equals, so reaches, it (repair round 5, ADV5-05: 'so the car's average speed was at
        # the limit')
        k = len(words) - 2
        return "reach", any(w in negation or w.endswith("n't") for w in words[:max(k, 0)])
    for k in range(len(words) - 1, -1, -1):
        kind = kind_of(words[k])
        if kind is not None:
            neg = any(w in negation or w.endswith("n't") for w in words[:k])
            return kind, neg
    # the passive after the noun and its own description: 'is met', 'of at least 80% is met', 'was not reached', 'has been exceeded'
    copulas = ("is", "was", "are", "were", "has", "have", "isn't", "wasn't", "aren't", "weren't", "hasn't", "haven't")
    c = next((k for k, w in enumerate(tail[:10]) if w in copulas), None)
    if c is not None:
        for k in range(c + 1, min(len(tail), c + 6)):
            w = tail[k]
            if w in ("been", "be", "not", "never", "therefore", "so", "also", "still", "clearly", "just", "only", "easily", "comfortably"):
                continue
            kind = kind_of(w)
            if kind is None or w in ("above", "over", "below", "under", "short"):
                break
            neg = any(x in negation or x.endswith("n't") for x in tail[c:k])
            return kind, neg
    # the outcome stated after the target in the active voice ('Since 50% is the pass mark, the student passed', '..., so
    # the batch meets it'): the first verb of reaching, exceeding or missing in the next eight words, never a preposition
    # that describes the target ('above', 'below'); negated by a negation in the three words before it (repair round 3,
    # ADV3-03: the rounding of a percentage to the pass mark itself was read as no target statement)
    for k, w in enumerate(tail[:8]):
        if w in ("above", "over", "below", "under", "short"):
            continue
        kind = kind_of(w)
        if kind is not None:
            neg = any(x in negation or x == "no" or x.endswith("n't") for x in tail[max(0, k - 3):k])
            return kind, neg
    return None


#: a restated value named as a target: '50% is the pass mark', '75% was the threshold', '80% equals the target' (ST-ROUND-001)
_IS_THE_TARGET_RE = re.compile(r"^\s*(?:is|was|equals|is\s+equal\s+to|is\s+exactly)\s+(?:the|our|its|their|this|that)?\s*$", re.IGNORECASE)
#: a predicate the request makes conditional on a value: 'acceptable only if', 'is accepted provided that', 'safe as long as'
_CONDITION_RE = re.compile(r"\b(?P<pred>[A-Za-z]{4,})\s+(?:only\s+if|provided(?:\s+that)?|as\s+long\s+as)\b"
                           # a plain "if" after a copula ('The method is accepted if the yield is at least 60%', 'A beam is safe if the
                           # load on it is at most 50 kN'): the predicate the request makes conditional (repair round 5, ADV5-05)
                           r"|\b(?:is|are|was|were|be|been|deemed|considered|counts\s+as)\s+(?P<pred2>[A-Za-z]{4,})\s+(?:if|when)\b")
#: further predicates a request makes conditional on a value, read only when :data:`_CONDITION_RE` finds none (accuracy round
#: 1, ADV6-05): 'A patient has a fever if their temperature exceeds 38.0 °C', 'A cable can safely carry a current of at most 13 A'
#: (the predicate of an adverb is its adjective: 'safely' is 'safe')
_CONDITION_EXTRA_RE = re.compile(r"\b(?:has|have|had)\s{1,3}(?:a\s{1,3}|an\s{1,3})?(?P<pred3>[A-Za-z]{4,24})\s{1,3}(?:if|when)\b"
                                 r"|\b(?:can|may)\s{1,3}(?P<pred4>[A-Za-z]{3,24}?)ly\s{1,3}[A-Za-z]{2,24}\b")
#: a value's bound written as 'exceeds' right before it: a strict bound
_EXCEEDS_BEFORE_RE = re.compile(r"\bexceeds?\s{0,3}$", re.IGNORECASE)
#: words before 'only if' that name no predicate of a value ('is only if', 'and only if')
_CONDITION_STOP = frozenset({"only", "that", "this", "these", "those", "then", "true", "holds", "when", "will", "would", "could", "should", "must",
                             "also", "there", "their", "which", "with", "from", "into", "than", "even", "else", "unless"})


def _predicate_said(seg: str, pred: str) -> Optional[bool]:
    """Whether the clause ``seg`` asserts the conditional predicate (False: it holds; True: it is denied by a negation in the
    four words before it, or by the prefix "un"), or None when the clause does not state it. A word shares the predicate
    when it shares its first five letters ('accepted' and 'acceptable')."""
    words = " ".join("".join(c.lower() if c.isalpha() or c == "'" else " " for c in seg).split()).split()
    key = pred[:5]
    for k, w in enumerate(words):
        if w.startswith(key) or (w.startswith("un") and w[2:].startswith(key)):
            negated = w.startswith("un") and not pred.startswith("un")
            if any(x in ("not", "never", "no", "fails", "failed") or x.endswith("n't") for x in words[max(0, k - 4):k]):
                negated = not negated
            return negated
    return None


def _target_bound(before: str) -> str:
    """The bound a target writes right before its value ('of at least', 'a maximum of'): an IR order operator, 'ge' when none."""
    low = " " + " ".join("".join(c.lower() if c.isalpha() else " " for c in before[-24:]).split()) + " "
    for phrase, op in TARGET_BOUNDS:
        if low.endswith(" " + phrase + " ") or low.endswith(" " + phrase + " of ") or low.endswith(" a " + phrase + " "):
            return op
    return "ge"


#: a target's value written into its noun phrase with a hyphenated bound: 'above-90%', 'at-least-70%', 'over-5 kg' (ST-ROUND-001)
_GLUED_TARGET_RE = re.compile(r"(?P<bound>at[- ]least|no[- ]less[- ]than|not[- ]less[- ]than|more[- ]than|greater[- ]than|above|over|at[- ]most|"
                              r"no[- ]more[- ]than|less[- ]than|below|under|minimum(?:[- ]of)?|maximum(?:[- ]of)?)?[- ]?(?P<n>\d+(?:\.\d+)?)\s?(?P<pct>%)?[- ]?\s*$",
                              re.IGNORECASE)


def _glued_target_value(before_noun: str, offset: int) -> Optional[tuple[Node, str]]:
    """The value (and its bound) written right before a target noun: '... the above-90% requirement' gives (90 %, 'gt'); None
    when the noun phrase writes no value. The node has no span (it is read from words, not from a maths span); ``offset`` is
    the phrase's place in the answer, kept for the caller."""
    m = _GLUED_TARGET_RE.search(before_noun[-40:])
    if m is None:
        return None
    k = len(before_noun) - len(before_noun[-40:]) + m.start("n")
    scan = scan_number(before_noun, k)
    if scan is None or scan.number is None:
        return None
    node: Node = Num(scan.number, 0, 0)
    if m.group("pct"):
        node = Percent(node, 0, 0)
    words = " ".join((m.group("bound") or "").lower().replace("-", " ").split())
    bound = next((op for phrase, op in TARGET_BOUNDS if words == phrase or words == phrase.replace(" of", "")), "ge")
    return node, bound


def _object_ordinal(words: list[str], k: int) -> bool:
    """``words[k]`` is an ordinal before an object noun ("second trolley"), not before a measurement noun ("second reading")."""
    if words[k] not in OBJECT_ORDINALS or k + 1 >= len(words):
        return False
    nxt = words[k + 1]
    return nxt not in MEASUREMENT_NOUNS and nxt not in NOUN_PHRASE_STOPWORDS and nxt not in CHANGE_MARKERS


def _is_year(value: Fraction) -> bool:
    return value.denominator == 1 and 1000 <= value <= 2999


def _caveat_stated(text: str) -> bool:
    """A caveat cue (:data:`.reference_data.EXTRAPOLATION_CAVEATS`) that no negating word governs in its clause: "This is an
    extrapolation, so it may not hold" states one; "This is not an extrapolation" and "the spring is not unreliable" do not.
    Bounded: every occurrence of every cue in the first 400,000 characters, a 40-character look-back each."""
    low = text[:400_000]
    for cue in EXTRAPOLATION_CAVEATS:
        k = low.find(cue)
        seen = 0
        while k >= 0 and seen < 64:
            seen += 1
            before = low[max(0, k - 40):k]
            if not _CAVEAT_NEGATION_RE.search(before):
                return True
            k = low.find(cue, k + len(cue))
    return False


_COMPARISON_FILLERS = frozenset({"is", "are", "was", "were", "not", "isn't", "aren't", "still", "also", "therefore", "so", "then", "never", "be", "remains"})
#: The subject a comparison clause may name after a rounded value ('≈ 0.7, so the efficiency is at least 0.70', 'so it is at
#: least 90%'): a pronoun, or 'the' and at most three words (the quantity the rounded value is the value of).
_COMPARISON_PRONOUNS = frozenset({"it", "this", "that"})


def _prose_comparison(between: str, *, subject: bool = False) -> Optional[tuple[str, bool]]:
    """``(IR order operator, negated)`` for the prose between two values that compares them ("is not less than",
    "is greater than", "exceeds", "is below"), else None. With ``subject`` (a comparison clause right after a rounded value)
    the clause may name what is compared before its verb: a pronoun or 'the' and up to three words ('so the efficiency is at
    least'; repair round 2). Bounded: the text between is at most 48 characters."""
    low = " " + " ".join("".join(c.lower() if c.isalpha() or c == "'" else " " for c in between[:48]).split()) + " "
    for phrase, op in COMPARISON_PHRASES:
        k = low.find(" " + phrase + " ")
        if k < 0 or low[k + len(phrase) + 2:].strip():
            continue
        head = low[:k].split()
        if subject:
            lead = [w for w in head if w not in _COMPARISON_FILLERS]
            copula = next((i for i, w in enumerate(head) if w in ("is", "are", "was", "were", "remains", "isn't", "aren't")), None)
            named = head[:copula] if copula is not None else []
            named = [w for w in named if w not in ("so", "therefore", "then", "thus", "hence", "and")]
            if lead and not (copula is not None and named == lead and (named[0] in _COMPARISON_PRONOUNS and len(named) == 1
                                                                        or named[0] == "the" and 2 <= len(named) <= 4)):
                return None
            head = [w for w in head if w not in lead]
        if any(w not in _COMPARISON_FILLERS for w in head):
            return None
        negated = any(w in ("not", "isn't", "aren't", "never") for w in head)
        return op, negated
    return None


def _show_value(v: Fraction) -> str:
    return str(v.numerator) if v.denominator == 1 else str(float(v))


def _opens_statement(item: MathItem) -> bool:
    """The item opens its statement: nothing but a few words of a step or a stated operation stand before it ('so', 'Dividing
    by x,', 'hence')."""
    gap = item.gap_before.strip(" ,:;\t").lower()
    if not gap:
        return True
    words = gap.split()
    return len(words) <= 6 and (_has_step_word(gap) or any(rx.search(gap) for _n, rx in _OPERATION_RES))


def _stated_bare(node: Node) -> bool:
    """A stated value written as a bare number (a ratio: a magnification, a fraction of one kind of quantity)."""
    cur = node
    while isinstance(cur, Neg):
        cur = cur.arg
    return isinstance(cur, Num)


def _stated_with_unit(node: Node) -> bool:
    """A stated value written with a unit of one exact factor (``0.25 m s⁻¹``)."""
    cur = node
    while isinstance(cur, Neg):
        cur = cur.arg
    return isinstance(cur, Quantity) and unit_scale(cur.unit) is not None and cur.unit.dim is not None


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
    # a value inside a phrase that states an input after the cue is a given, not the result restated: 'So, with fixed costs of
    # $40,000, …', 'therefore, using g = 9.8 …', 'hence at a load of 20 N …'
    cue_at = max((i for i, w in enumerate(words) if w in _RESULT_CUE_WORDS), default=-1)
    if cue_at >= 0 and any(w in _INPUT_WORDS and not (w in ("at", "as") and i > 0 and words[i - 1] in _RESULT_PARTICIPLES)
                           for i, w in enumerate(words) if i > cue_at):
        return False  # ('is therefore estimated at 240' keeps its result participle)
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


def named_quantities(statement_text: str) -> list[tuple[str, frozenset[str]]]:
    """The symbols one statement names by a description, each with its description's variants: 'Let $M$ be the monthly
    payment in euros.' gives ``("M", {"monthly payment in euros", "monthly payment"})``. A symbol is one letter, in inline
    maths or not, after 'let' or 'letting' (with be, denote, represent or stand for), after 'where' or 'with' (with is, =,
    denotes, represents, stands for, or no verb), or opening the statement (with is, denotes, represents or stands for); a
    determiner follows, then words only. The description stops at the first figure, sign or bracket and before a relative
    clause or a conjunction ('the useful energy that vaporises the water'), and a trailing 'in <unit>' also gives the
    shorter name. Bounded: the first 2,000 characters of the statement, a fixed number of patterns."""
    text = statement_text[:_DEFINITION_WINDOW]
    out: list[tuple[str, frozenset[str]]] = []
    for pattern in _DEFINITION_RES:
        for m in pattern.finditer(text):
            desc = _DESCRIPTION_STOP_RE.sub("", " ".join(m.group("desc").lower().split())).strip(" -'")
            if not desc or len(desc.split()) > 8:
                continue
            variants = {desc}
            short = _DESCRIPTION_UNIT_RE.sub("", desc)
            if short and short != desc:
                variants.add(short)
            out.append((m.group("sym"), frozenset(variants)))
    return out


def _equations_solved_later(rels: list[Relation], scope: Scope) -> list[Relation]:
    """An identity read by its shape alone (``Relation.inferred``) whose unknown the answer then solves for (a later
    relation of the same statement order states a root of it, or the scope binds it as a root) was an equation to solve,
    not an identity claim: it is kept as context, never checked as an identity (repair round 4)."""
    out = list(rels)
    for k, r in enumerate(out):
        if not r.inferred or r.outcome != "check":
            continue
        names = _syms(_first(r.left)) | _syms(_first(r.right))
        solved = any(b.source == "root" for n in names for b in scope.bindings.get(n, ())) or any(
            later.kind == "sol" and later.root_symbol in names and later.start >= r.end for later in out[k + 1:])
        if solved:
            out[k] = replace(r, kind="stated", outcome="context", inferred=False,
                             reason="an equation the answer solves for its unknown (read as an identity by its shape, then solved)")
    return out


def plan_relations(items: list[MathItem], prose_values: list[ProseValue], scope: Scope, request: RequestReading, profile: StemProfile, *,
                   limits: StemLimits = DEFAULT_LIMITS, statement_order: Optional[dict[str, int]] = None,
                   code_items: Optional[list[tuple[str, int, int, str]]] = None, request_mode: bool = False,
                   definitions: Optional[list[tuple[int, str, str, frozenset[str], str]]] = None,
                   reading: str = "", answer_text: str = "", reference_checks: bool = True) -> tuple[list[Relation], list[FrontEndFinding], list]:
    """Classify every link of ``items`` (in document order), record bindings and formulas in
    ``scope``, plan the checks and assign stable ids. Returns ``(relations, findings,
    request relations)``; the request mode records bindings, formulas and relations only. ``definitions`` are the
    symbols the answer names by a description (:func:`named_quantities`, with each statement's order, part and id): a
    decimal it states in prose for one of them is a stated root of the equation in it (``_described_roots``). ``reading``
    is the reading view the items were read from: a model's application is told apart from a product by it (the letter
    glued to its bracket, ``models.application_of``); without it no application is read. ``answer_text`` (the whole
    answer) is read for the extrapolation caveats of section 24. ``reference_checks`` False leaves the reference checks out
    (the closed table of booklet laws is read with them off, :func:`.reference.booklet_laws`)."""
    order = statement_order or {}
    planner = _Planner(items, prose_values, scope, request, profile, limits, order, code_items or [], request_mode, definitions, reading)
    planner.answer_lower = answer_text[:400_000].lower()
    planner.answer_text = answer_text[:400_000]
    planner.reference_checks = reference_checks
    planner.run()
    rels = _equations_solved_later(planner.relations, planner.scope)
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
        if r.kind == "unit":
            # a unit companion (ST-UNIT-003) carries the id of the check it accompanies with a 'u': 'stem-eq-3u'
            if r.companion_of not in assigned:
                continue
            cid = assigned[r.companion_of] + "u"
        else:
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
