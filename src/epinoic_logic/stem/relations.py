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
symbols; a bare number is "unitless as written". A relation whose sides' dimensions are not
both known because of bare numbers is read again by rule ``bare-factor`` (:func:`bare_factor_dimensions`):
each bare number read as a pure factor, or as the dimension of the symbol the answer substituted it
for, of an equal value the answer or the request states with a unit, or of the data-booklet constant
it matches, a bare term of a sum taking the sum's dimension; a side with no operand that carries a
unit stays unknown (``120 / 8 = 15 m s⁻¹`` is never a finding). ST-DIM-001 is raised when every
such reading gives the two sides different dimensions (``0.693 × 8.0 h = 5.5 h⁻¹``). Across an equality
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
from typing import Iterable, Optional

from .boolean import BoolRelation, TruthTable
from .calculus import antiderivative, derivative, polynomial, polynomial_node
from .chem import ELEMENTS, ChemEquation
from .limits import DEFAULT_LIMITS, StemLimits, StemProfile
from .nodes import (
    Abs, Apply, BinOp, BoolOp, Chain, Degrees, Func, Magnification, Neg, Node, Num, Operand, Percent, PlusMinus, Pow, Quantity, Ratio, RealPower, Root,
    Sym, Unsupported, WithUnit, align, children, is_closed, is_value, render, replace_symbol, shape_key, symbols, unsupported_reasons, value_of, walk,
)
from .numbers import ExactNumber, exact_based, scan_number
from .parser import ParseIssue
from .models import (
    all_symbols, application_of, applications, has_exponential, is_model_expression, model_link_sides, relaxation_fits, render_model, resolve_model,
    substitute,
)
from .scope import Binding, Formula, Model, Scope, si_value
from .tolerance import approx_word_before
from .constants import constants_for_symbol
from .reference import (
    as_written_reading, booklet_formulas, booklet_laws, coefficient_free_dimension, difference_witness, differs_as_function, dimension_text, fixed_quantity,
    enclose_node, pure_coefficient_dimension, quantities_for, unit_scale, unit_written_once,
)
from .reference_data import (
    ABSOLUTE_TEMPERATURE_LAWS, CHANGE_MARKERS, COMPARISON_PHRASES, DEFINITION_GIVENS_LAWS, EXTRAPOLATION_CAVEATS, GIVENS_LAWS, MEASUREMENT_NOUNS, NOUN_PHRASE_STOPWORDS, OBJECT_ORDINALS, TARGET_BOUNDS,
    TARGET_EXCEED_VERBS, TARGET_MISS_VERBS, TARGET_NOUNS, TARGET_REACH_VERBS, WORKING_COMMANDS, WORKING_CUES,
)
from .units import DIMENSIONLESS, Dimension, UnitAtom, UnitExpr, UnitReading, is_unit_atom, parse_unit

#: rule ``bare-factor``: the most readings of a relation's bare numbers that are compared
_MAX_BARE_READINGS = 64

__all__ = [
    "CHECK_KINDS", "FrontEndFinding", "MathItem", "ProseValue", "Relation", "RequestReading", "ST_SEVERITY", "ShowThatTarget", "dimension_of",
    "named_quantities", "plan_relations",
]

#: the most readings of one model link: one per combination of the definitions of the letters it applies
MAX_MODEL_READINGS = 4
#: check kinds in the order of section 8.1
CHECK_KINDS = ("eq", "sub", "alg", "sol", "mod", "cnv", "cmp", "res", "giv", "tgt", "chem", "bool", "tt", "base")
#: severity of every front-end code (section 8.2); none is an error
ST_SEVERITY = {
    "ST-PARSE-001": "warning", "ST-PARSE-002": "warning", "ST-UNDEC-001": "warning", "ST-UNDEC-002": "warning", "ST-UNDEC-003": "warning",
    "ST-UNDEF-001": "warning",
    "ST-UNIT-001": "warning", "ST-UNIT-002": "info", "ST-DIM-001": "warning", "ST-DIM-002": "warning", "ST-ALG-001": "warning",
    "ST-CHEM-001": "warning", "ST-CODE-001": "info", "ST-SCOPE-001": "info", "ST-LIM-001": "warning", "ST-LIM-002": "warning",
    "ST-INTERNAL-001": "warning",
    # the named STEM diagnostics of the argument diagnostics (docs/ARGUMENT_DIAGNOSTICS.md section 3.4; each carries its canonical
    # defect label: named.NAMED_CODES)
    "ST-REF-001": "warning", "ST-STEP-002": "info", "ST-RANGE-001": "warning", "ST-WORK-001": "warning", "ST-GIVEN-002": "warning",
    "ST-SCOPE-002": "warning", "ST-REF-002": "warning", "ST-GIVEN-003": "warning", "ST-GIVEN-004": "warning", "ST-STEP-003": "warning",
    # the codes of the engine-decided named checks (a ``unit`` companion, an ``op`` and an ``rnd`` check): never front-end findings,
    # named in their checks' statements; a failure reaches the receipt as INT-SUBJ-001 or INT-SUBJ-004 carrying the defect
    "ST-UNIT-003": "warning", "ST-STEP-001": "warning", "ST-ROUND-001": "warning",
}
_EQUALITY = frozenset({"=", "≈", "≃", "≡"})
#: rule ``fragment`` (STEM repair 2): words that join a math run to an operand written before it in words, so that a run starting right
#: after one holds only the tail of its expression ('17 is divided by 5 = 2', '20% of 50 = 10', '12 over 4 = 3')
_JOINING_WORDS = frozenset({"of", "by", "over", "into", "per", "times", "plus", "minus", "mod", "modulo", "div", "rem", "than", "from", "to", "and",
                            "twice", "double", "triple", "thrice", "add", "subtract", "multiply", "divide", "divided", "multiplied", "remainder"})
_TRAILING_WORD_RE = re.compile(r"([A-Za-z]+)[ \t]*$")
#: rule ``question`` (STEM repair 2): a relation followed by a question mark, and the answer the answer gives it
_QUESTION_RE = re.compile(r"[ \t]*\?[ \t]*(?:[(\[:—–-][ \t]*)?(yes|no|true|false)?(?![A-Za-z])", re.IGNORECASE)
_YES_WORDS = frozenset({"yes", "true"})
#: stem-precision-8: the words after a comparison that state it is false
_STATED_FALSE_RE = re.compile(r"[ \t]*\)?[ \t]*,?[ \t]*(?:(?:which|this|that|it)[ \t]+)?(?:(?:is|was|evaluates[ \t]+to|returns|gives|is[ \t]+evaluated[ \t]+as)"
                              r"[ \t]+(?:false|not[ \t]+true)|fails|is[ \t]+not[ \t]+true)(?![A-Za-z])", re.IGNORECASE)
#: rule premise-cue (STEM repair 2): the words that introduce a relation another one on the same line is derived from
_PREMISE_CUE_RE = re.compile(r"(?:^|[\s(])(?:from|since|because|as|using|rearranging|by)[ \t]*$", re.IGNORECASE)
#: rule restated-binding (STEM repair 2): the word that makes a value stated for a symbol the restatement of the chain before it
#: rule prose-conversion (STEM repair 5): the words between a value the prose states and its restatement in another unit
_PROSE_RESTATE_RE = re.compile(r"^[ \t]*(?:(?:[,;:][ \t]*|[—–][ \t]*)?(?:i\.[ \t]?e\.|ie|that[ \t]+is|that[’']s|which[ \t]+is(?:[ \t]+(?:equal[ \t]+to|"
                               r"the[ \t]+same[ \t]+as|equivalent[ \t]+to))?|which[ \t]+equals|equal[ \t]+to|equivalent[ \t]+to|or[ \t]+equivalently)"
                               r"|[,;][ \t]*or)[ \t]*,?[ \t]*(?P<about>about|approximately|roughly|nearly)?[ \t]*$"
                               r"|^[ \t]*(?P<bracket>\()[ \t]*(?:(?:or|i\.[ \t]?e\.|ie|that[ \t]+is)[ \t]*,?[ \t]*)?"
                               r"(?P<about_b>about|approximately|roughly|nearly)?[ \t]*$"
                               r"|^[ \t]*,?[ \t]*(?P<verb>is|equals|is[ \t]+equal[ \t]+to|is[ \t]+equivalent[ \t]+to|is[ \t]+the[ \t]+same[ \t]+as|converts[ \t]+to"
                               r"|is[ \t]+converted[ \t]+to|converted[ \t]+to)[ \t]+(?P<about_v>about|approximately|roughly|nearly)?[ \t]*$"
                               r"|^[ \t]*,[ \t]*(?P<about_c>about|approximately|roughly|nearly)[ \t]+$", re.IGNORECASE)
#: rule adjacent-restatement (STEM repair 5): 'of' and a pronoun right after a value, which makes the value a part of the quantity before
#: it ('4.4 W of it is lost'), never its restatement
_PART_OF_IT_RE = re.compile(r"^[ \t]*of[ \t]+(?:it|this|that|them|these|those)\b", re.IGNORECASE)
#: rule rounding-cue (STEM repair 5): the words between a value the prose states and its restatement with a stated rounding
_PROSE_ROUNDED_RE = re.compile(r"^[ \t]*,[ \t]*(?:so|which[ \t]+is|or|i\.[ \t]?e\.|that[ \t]+is)[ \t]*,?[ \t]*$", re.IGNORECASE)
#: rule prose-conversion (STEM repair 5): the value restated in a unit the prose names between the two values ('Converting 55.0 cm³ to
#: dm³ gives 0.0550 dm³.', '55.0 cm³ in dm³ is 0.0550 dm³.', '55.0 cm³, which in dm³ is 0.0550 dm³.'); the named unit must be the
#: restated value's own, written the same way
_PROSE_TO_UNIT_RE = re.compile(r"^[ \t]*,?[ \t]*(?:which[ \t]+)?(?:to|into|in)[ \t]+(?P<unit>[^\s,;:.()]{1,12}(?:[ \t][^\s,;:.()\d]{1,8}){0,2})[ \t]*,?[ \t]*"
                               r"(?:gives|is|equals|makes|comes[ \t]+to)[ \t]+(?P<about_u>about|approximately|roughly|nearly)?[ \t]*$", re.IGNORECASE)
#: rule prose-base (STEM repair 10): the words that name a number base, and the base each names
_BASE_WORD = r"(?:binary|octal|denary|decimal|hexadecimal|hex|base[ \t-]?(?:2|8|10|16|two|eight|ten|sixteen))"
_BASE_OF = {"binary": 2, "octal": 8, "denary": 10, "decimal": 10, "hexadecimal": 16, "hex": 16, "2": 2, "8": 8, "10": 10, "16": 16, "two": 2,
            "eight": 8, "ten": 10, "sixteen": 16}
#: '… in binary' (or 'as', 'into') right after a value: the base it is written in
_BASE_AFTER_RE = re.compile(r"^[ \t]*(?:in|as|into)[ \t]+(?P<b>" + _BASE_WORD + r")(?![A-Za-z0-9])", re.IGNORECASE)
#: 'the binary number 110010₂', 'the denary number 50', 'denary 50' right before a value: the base it is written in
_BASE_BEFORE_RE = re.compile(r"(?:^|[\s(,:;])(?:(?:the|a)[ \t]+)?(?P<b>" + _BASE_WORD + r")(?:[ \t]+(?:number|numeral|value|integer|digit))?[ \t]+$",
                             re.IGNORECASE)
#: 'the binary representation of 50 is …': the base of the value the prose restates it as
_BASE_OF_RE = re.compile(r"(?:^|[\s(,:;])(?:(?:the|a|its)[ \t]+)?(?P<b>" + _BASE_WORD + r")[ \t]+(?:representation|form|equivalent|version)[ \t]+of[ \t]+$",
                         re.IGNORECASE)
#: STEM repair 11 (rule prose-base): a base the prose names once, opening the clause before both numerals ('In binary, 1000 is 1111101000.',
#: 'In base 2, 13 is 1101.', 'Written in hexadecimal, 255 is FF'): which numeral it is the base of is read either way, as for '10 in binary is 1010'
#: STEM repair 12: the phrase may name what follows it ('In hexadecimal, the number 1000 is 3E8.', 'In binary the number 5 is 101.')
_BASE_OPEN_RE = re.compile(r"(?:^|[\n.;:(])[ \t]*(?:(?:written|expressed|converted|shown)[ \t]+)?(?:in|into|to|as)[ \t]+(?P<b>" + _BASE_WORD
                           + r")[ \t]*,?[ \t]*(?:(?:the|a)[ \t]+(?:number|numeral|value|integer)[ \t]+)?$", re.IGNORECASE)
#: STEM repair 12 (rule prose-base): a hexadecimal numeral with letter digits and no base marker: upper-case digits with at least one
#: letter ('3E8', 'FF', '1F4', 'A'), or lower-case ones with at least one letter and one decimal digit ('3e8', '1f4'; never a word such as
#: 'face' or 'a'), bounded by no letter, digit, underscore, base subscript or decimal point; read only where words name base 16 for it
_HEX_WORD_RE = re.compile(r"(?<![0-9A-Za-z_.$€£¥'’-])(?:(?=[0-9A-F]*[A-F])[0-9A-F]{1,16}|(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{2,16})"
                          r"(?![0-9A-Za-z_₀-₉]|\.\d)")
_HEX_DIGITS_RE = re.compile(r"[0-9A-Fa-f]{1,16}")
#: the words between a value and its restatement in another base ('110010₂ is 50 in denary', '110010 in binary equals 50', '50 in
#: denary, that is 110010₂'), with the base of the first value when they name it
_BASE_BETWEEN_RE = re.compile(r"^[ \t]*(?:(?:in|as)[ \t]+(?P<ab>" + _BASE_WORD + r")[ \t]*)?,?[ \t]*(?:is|equals|is[ \t]+equal[ \t]+to|is[ \t]+written[ \t]+"
                              r"(?:as[ \t]+)?|which[ \t]+is|that[ \t]+is|i\.[ \t]?e\.|=|gives|converts[ \t]+to|is[ \t]+converted[ \t]+to|becomes)[ \t]*,?[ \t]*$",
                              re.IGNORECASE)
#: the words that make a value the end of a range, the last of a list or one side of a comparison: what follows may restate the range
#: ('from 20.0 °C to 60.0 °C, that is 40.0 K'), so no conversion of that value is read
_RANGE_END_RE = re.compile(r"(?:^|[\s(])(?:to|and|or|nor|than|plus|minus|[-−–—+×])[ \t]*$", re.IGNORECASE)
#: rule bound-relation (STEM repair 5): the verb by which the prose gives a maths run as the value of the quantity it names
_PROSE_HEAD_VERB_RE = re.compile(r"(?:^|[\s(])(?:(?:is|are|was|were)(?:[ \t]+(?:then|now|therefore|thus|hence|also))?(?:[ \t]+(?:equal[ \t]+to|given[ \t]+by))?"
                                  r"|equals?)[ \t]*$", re.IGNORECASE)
#: words that name an equation or a law rather than a quantity ('The equation is 2x + 3 = 7')
_EQUATION_WORDS = frozenset({"equation", "expression", "formula", "identity", "inequality", "condition", "relation", "relationship", "law", "rule",
                             "statement", "step", "constraint", "model"})
_RESTATE_SO_RE = re.compile(r"(?:^|[\s,;(“”\"’)])(?:so|i\.e\.|ie|hence|thus|giving)[ \t]*$", re.IGNORECASE)
#: STEM repair 5 (rule rearranged-formula's companion): the words that introduce a relation as the inverse's equation, the variables
#: swapped ('Swap x and y: x = 2y + 1', 'For the inverse, x = 2y + 1'), never a step from the relation before it
_SWAP_RE = re.compile(r"\b(?:swap(?:s|ped|ping)?|interchang(?:e|es|ed|ing)|inverse)\b", re.IGNORECASE)
#: rule boolean-values (STEM repair 4): a statement that continues the one before it, whose values its Boolean relations take
_BOOL_CONTINUE_RE = re.compile(r"^\W*(?:then|so|hence|thus|therefore)\b", re.IGNORECASE)
#: a statement that sets up values for the statements after it ('Let A = 1 and B = 0.', 'Take A = 1.'), and how far back it is looked for
_BOOL_SETUP_RE = re.compile(r"^\W*(?:(?:now|here)\s+)?(?:let|take|taking|suppose|set|assume|consider|given|using|with|when|if|for)\b", re.IGNORECASE)
_BOOL_SETUP_REACH = 6
#: the words a statement of nothing but Boolean input values may hold besides them ('Here A = 1 and B = 0.', 'The inputs are A = 1, B = 0.')
_BOOL_VALUE_WORDS = frozenset({"and", "here", "now", "set", "the", "input", "inputs", "value", "values", "are", "is", "with", "where"})
#: an opening label ending with ':' ('Test case: A = 1, B = 0.')
_BOOL_LABEL_RE = re.compile(r"^\s*[A-Za-z][A-Za-z0-9 ]{0,40}:")
_NEGATION = {"=": "≠", "≠": "=", "<": "≥", ">": "≤", "≤": ">", "≥": "<"}
_APPROX = frozenset({"≈", "≃"})
_ORDER = frozenset({"<", ">", "≤", "≥", "≠"})
_STEP_WORDS = ("⇒", "∴", "so", "hence", "therefore", "thus", "gives", "giving", "rearranging", "rearranged", "which gives", "implies", "then",
               "get", "obtain", "yields", "leads to",
               # STEM repair 5 (rule rearranged-formula): the phrases that state a rearrangement of the relation before ('Making R the
               # subject, R = V²/P.', 'Solving for R, R = V²/P.', 'Transposing, R = V²/P.'): the relation after them is a step from it
               "the subject", "solving for", "solve for", "solved for", "transposing", "transposed")
_APPROX_WORDS = ("approximately", "approx.", "about", "roughly", "estimate", "around", "nearly")
_COMPLETE_PHRASES = ("only solution", "only root", "the solution is", "the solutions are", "is the solution", "are the solutions", "the roots are",
                     "solutions are", "roots are", "the only value", "is the only")
#: stem-precision-1: the words that open the clause of a restated value, and the words of such a clause that name no quantity
_CUE_WORDS = frozenset({"so", "therefore", "thus", "hence", "giving", "gives", "then", "consequently", "which", "means"})
_CLAUSE_STOP_WORDS = frozenset({
    "the", "and", "are", "was", "were", "this", "that", "its", "their", "his", "her", "our", "for", "with", "from", "into", "equal", "equals",
    "about", "approximately", "roughly", "nearly", "around", "rounded", "exactly", "just", "only", "now", "here", "also", "still", "get", "gets",
    "got", "answer", "result", "results", "value", "values", "final", "total", "overall", "required", "comes", "becomes", "works", "out", "is",
    "be", "been", "being", "has", "have", "had", "will", "would", "can", "could", "may", "might", "must", "should", "one", "two", "number",
    "figure", "amount", "quantity", "calculated", "computed", "obtained", "found", "worked", "correct", "correctly", "answers", "given", "use",
    "using", "used", "decimal", "places", "place", "significant", "figures", "nearest", "whole", "per", "cent", "percent", "percentage",
    "there", "these", "those", "they", "them", "than", "when", "where", "what", "each", "every", "all", "both", "some", "any", "such", "more",
    "less", "most", "least", "very", "much", "many", "you", "your", "our", "which", "whose",
})
#: words that name a factorisation, an expansion or a simplification (stem-soundness-12)
_IDENTITY_WORDS = ("factoris", "factoriz", "expand", "expansion", "simplif")
#: words that name a system of simultaneous equations (stem-soundness-5)
_SYSTEM_WORDS = ("simultaneous", "system of", "the system", "equations (1)", "(1) and (2)", "both equations")
#: words that make a root line state one root of several (stem-soundness-11): such a line claims no full set
_PARTIAL_ROOT_WORDS = (" one ", " a root", " a solution", " another ", " other ", " also ", " either ", " one of ", " first ", " second ")
_RESTRICT_WORDS = ("reject", "positive", "non-negative", "nonnegative", "x > 0", "x ≥ 0", "> 0", "≥ 0", "length", "time", "only the positive",
                   "cannot be negative", "must be positive", "domain")
_RESULT_CUES = ("therefore", "hence", "thus", "so", "the answer is", "the result is")
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
    #: the statement's prose right after the value (bounded): a rounding stated after it ("60%, to 2 s.f.")
    after: str = ""
    #: rule prose-given (STEM repair 6): the value stands in the Given part of a Given statement ('Data: emf 15 V, …', 'Given: the mass of
    #: seeds is 12 g.', the first clause of 'We know the internal resistance was 0.40 Ω, …'), so it is a Given value
    given: bool = False


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
    #: the tables of the texts supplied with the request (:mod:`.datatables`, rule table-data)
    tables: tuple = ()
    #: every value the request states (STEM repair 2, rule given-kinds): ``(node, start, end, word)``, ``word`` the word written right
    #: after the number ('euro' for '4000 euros', '%' for '3.6 per cent'), plurals folded, empty when none
    values: tuple = ()
    #: the request's quantities named by the words before them (STEM repair 2, rule named-given): ``(node, start, end, words)``
    named_quantities: tuple = ()
    #: STEM repair 3 (rule supplied-values): the quantities the texts supplied with the request state in their prose (outside their
    #: tables), with a unit the table of units reads ('Background count rate …: 20 counts per minute', '50.0 cm3 of … thiosulfate'),
    #: as ``(node, start, end, sentence words)``; the percentages they state, as ``(node, start, end, word, sentence words)``; and those
    #: named by words, as ``(node, start, end, words)``. Uncertainties ('+/-0.5 °C') are no values. Offsets are into the supplied text.
    supplied_quantities: tuple = ()
    supplied_values: tuple = ()
    supplied_named: tuple = ()
    #: STEM repair 3 (rule given-uncertainty): the uncertainties the supplied texts, and the request itself, state ('Uncertainties:
    #: thermometer +/-0.5 °C', '+/-2%'), as ``(node, start, end, unit, wrapper, sentence words)``, the unit the one written after the
    #: number (None for a percentage, whose wrapper is '%')
    supplied_uncertainties: tuple = ()
    request_uncertainties: tuple = ()
    #: argument diagnostics (ST-RANGE-001): data series the request gives, (unit as written, the values) for three or more values of one
    #: unit in one statement, and the years the request's data name (four-digit integers from 1000 to 2999 written as years), in order
    series: tuple[tuple[str, tuple[Fraction, ...]], ...] = ()
    years: tuple[Fraction, ...] = ()


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
    #: ``base`` by rule prose-base (STEM repair 10): the other reading of the two numerals ('10 in binary is 1010': 10 written in
    #: binary is 1010, or 10 in binary is the number 1010), as (left, right) nodes; the check holds when either reading does
    alternative: tuple[Node, Node] = ()
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
    #: an ``alg`` identity from the trivially true premise (rule identity-variable, STEM repair 12: a derivative, an antiderivative, a
    #: definite integral's antiderivative, a Given function against the request's, a factorisation in one chain): the variables it is
    #: stated for every value of. The checks stage never binds them, never gives them a formula and counts them connected (the identity
    #: itself quantifies them): before, a variable the formed side lacks ('d/dt (6 − 6t) = −6t', the formed side −6) took the request's
    #: value 't = 1' and the identity was checked at that one value only, so a wrong derivative was ENTAILED
    identity: tuple[str, ...] = ()
    #: ``res``: the half-width a rounding the prose states gives the restated value ("to the nearest whole number": 1/2; "to
    #: 2 s.f." of 60: 1/2; "to 1 d.p.": 1/20), in the restated value's written unit, and the phrase that states it
    rounding: Optional[Fraction] = None
    rounding_phrase: str = ""
    #: ``sub``: the statements (other than its own) that state the values the substitution is checked against, latest first
    #: (rule related-statements, STEM repair 1): a failure names them too, so a value a later line contradicts is named
    #: where it is stated. They are not statement ids of the relation (the parser's roles read those).
    related_ids: tuple[str, ...] = ()
    #: ``res`` by rule named-change: the words of the quantity the prose names ("external resistance"), by which its value
    #: before the change it states is matched to the value stated earlier (a reading: the check fails at warning severity)
    named: str = ""
    #: ``giv`` by rule table-data: the candidates are the supplied table's cells (or their difference), data taken as written
    #: (exact), so only the stated value's half-width bands the comparison
    exact_candidates: bool = False
    #: ``res`` by rule restated-binding (STEM repair 2): the symbol (or function value) the answer gives the value just computed
    #: after "so" ('… = 800 ± 16 counts min⁻¹” (so C(8) = 800)'); the symbol is matched to that value by the word "so", a reading
    #: (the check fails at warning severity)
    restates: str = ""
    #: a ``label`` binding by rule value-at (STEM repair 3): the condition the value is stated under ('oxygen uptake at 30 °C = 80 mm³':
    #: 30 °C; 'the count rate at t = 8 h = 820 counts min⁻¹': 8 h, with ``condition_symbol`` t), never one side of a relation
    condition: Optional[Operand] = None
    condition_symbol: str = ""
    #: a check planned by a rule that sets a written line against a definition (STEM repair 3: rules percentage-change and half-lives):
    #: the title its statement opens with instead of the kind's own ("the written arithmetic" is the line itself)
    title: str = ""
    #: ``bool`` by rule boolean-values (STEM repair 4): the values its statement gives the expression's inputs ('With A = 1 and B = 0,
    #: NOT A OR B = 0': A = 1, B = 0), so the relation is the expression evaluated there, never an identity over every assignment; an
    #: input given no value stays free (the relation must hold for each of its values)
    assignment: tuple[tuple[str, bool], ...] = ()
    #: ``sub`` by rule part-value (STEM repair 5): the substituted symbols whose every binding stands in another part (``reused``: the
    #: answer may reuse the symbol here for another quantity, 'I' for the current in the 6.0 Ω resistor of part (d) after the battery's
    #: 'I = 4.1 A' of part (b)), and the values the relation's part states, before it, for the quantity its chain computes
    #: (``head_values`` of ``head_symbol``: 'P = … = 16.4 W' before 'As a check, P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W'; with no lone
    #: head, or none with such a value, the part's own results of the numeric side's dimension, ``head_symbol`` empty). Such a symbol's
    #: value matches when it matches a binding, or when the line's numeric side gives one of those values. ``part_stated``: for each
    #: reused symbol, the results its part computes before the relation with the symbol's dimension ('The current in it is 9.93 V ÷
    #: 6.0 Ω = 1.655 A.' before 'P = I²R = (1.655 A)² × 6.0 Ω'), which its value may match as it matches a binding
    reused: tuple[str, ...] = ()
    head_values: tuple[Binding, ...] = ()
    head_symbol: str = ""
    part_stated: tuple[tuple[str, tuple[Binding, ...]], ...] = ()
    #: ``sub`` by rule bound-relation (STEM repair 5): the quantity the prose names as the value of the run ('battery power output' of
    #: 'The battery's power output is 12 V × I = 60 W.'), read as the head of the chain
    prose_head: str = ""
    #: rule fraction-unit (STEM repair 6): the fractions of the relation whose trailing unit is read as the fraction's own ('1/40 s⁻¹' as
    #: (1/40) s⁻¹), each as written, for the check's statement
    fraction_units: tuple[str, ...] = ()
    #: ``sub`` by rule part-given (STEM repair 6): the values of the symbols' dimension that the relation's part's question states (the
    #: 6.0 ohm of "the power dissipated in the 6.0 ohm resistor"), when the substituted value is another value the request states that
    #: neither that question nor the part's working before the line gives: the substitution is checked at warning severity against the
    #: symbol's stated values, these and rule part-value's readings
    part_given: tuple[Binding, ...] = ()
    #: ``res`` by rule finer-restatement (STEM repair 7): a value restated with a stated rounding finer than the chain's stated final value
    #: ('To 3 s.f., V = 9.90 V.' after '… = 9.9 V'), set against the value the chain's written arithmetic gives (``left`` is that
    #: expression, its numerals as written: a reading, so the check fails at warning severity)
    finer: bool = False
    #: ``sub`` by rule solved-law (STEM repair 7): for a symbol with no binding, the values substituted for it before the line, which its
    #: value is set against as the algebra step this reading replaces had pinned it ('ω = 2πf so f = 3.0/(2π)' after '2π/ω = 2π/4.0')
    prior_readings: tuple[tuple[str, tuple[Binding, ...]], ...] = ()
    #: ``eq`` by rule inequality-solution (STEM repair 11): the offsets of the numerals of the computed bound that the answer writes with
    #: their digits cut ('135.36…'): each ranges over [w − u/2, w + u] (cut, or rounded, digits), u a unit in its last written digit
    cut_spans: tuple[tuple[int, int], ...] = ()
    #: ``sol``: the root is a value the answer states in prose for the quantity it named by the symbol (a prose value,
    #: approximate by nature: the checks stage compares it within the '=' band, τ = 1/100 beyond its half-width)
    described: bool = False
    #: argument diagnostics (docs/ARGUMENT_DIAGNOSTICS.md section 3.4): a ``unit`` companion (ST-UNIT-003): the index of the check it
    #: accompanies, and its case: ``written`` (the written units contradict the as-written reading) or ``traced`` (bare numbers repeat the
    #: numbers of bindings in non-SI units)
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
    #: ``sol`` of simultaneous equations (stem-soundness-5, round 7): the equations of the system (left, right operands) and the value the
    #: answer states for each unknown; the stated values are checked against every equation of the system together, never as an algebra
    #: step from one equation that takes another stated value of the same conclusion as a premise
    simultaneous: tuple[tuple[Operand, Operand], ...] = ()
    simultaneous_values: tuple[tuple[str, Node], ...] = ()

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


def _bare(node: Node) -> bool:
    """Only bare numerals (no unit), constants (π, e), per cents and functions of them: nothing that carries a unit or names a
    quantity."""
    for n in walk(node):
        if isinstance(n, (Quantity, WithUnit, Degrees, Unsupported, Apply, Ratio, Magnification, PlusMinus)):
            return False
        if isinstance(n, Sym) and n.kind != "constant":
            return False
    return True


def _bare_leaves(node: Node) -> list[Num]:
    """The bare numerals of ``node``: ``Num`` leaves outside every unit-bearing group (``(40 − 20) K`` carries its unit)."""
    out: list[Num] = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, (WithUnit, Quantity)):
            continue
        if isinstance(cur, Num):
            if not (cur.number.based or cur.number.base != 10):
                out.append(cur)
            continue
        stack.extend(reversed(children(cur)))
    return out


def _carries_unit(node: Node, scope: Scope) -> bool:
    """Some operand of ``node`` carries a unit read unambiguously: a quantity, a group with a unit, or a symbol bound with one."""
    for n in walk(node):
        if isinstance(n, (Quantity, WithUnit)) and not n.unit.unknown and n.unit.dim is not None:
            return True
        if isinstance(n, Sym) and n.kind != "constant" and _dim(n, scope, None, 0) is not None:
            return True
    return False


def _dim_with(node: Node, scope: Scope, leaf_dims: dict[tuple[int, int], Dimension], depth: int = 0) -> Optional[Dimension]:
    """The dimension of ``node`` with each bare numeral read as ``leaf_dims`` gives it (rule ``bare-factor``); a bare term of a sum
    takes the sum's dimension (a value written without the unit its sum carries)."""
    if depth > 64:
        return None
    rec = lambda n: _dim_with(n, scope, leaf_dims, depth + 1)  # noqa: E731
    if isinstance(node, Num):
        return leaf_dims.get((node.start, node.end))
    if isinstance(node, (Quantity, WithUnit)):
        return node.unit.dim if not node.unit.unknown else None
    if isinstance(node, Sym):
        return _dim(node, scope, None, depth)
    if isinstance(node, (Neg, Abs, Percent)):
        return rec(node.arg)
    if isinstance(node, BinOp) and node.op in "+-":
        da, db = rec(node.left), rec(node.right)
        if da is None or db is None:
            return None
        if da.same_physical(db):
            return da
        bare_a, bare_b = _bare(node.left), _bare(node.right)
        if bare_a and not bare_b:
            return db
        if bare_b and not bare_a:
            return da
        return None
    if isinstance(node, BinOp):
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


def bare_factor_dimensions(a: Node, b: Node, scope: Scope, leaf_readings: dict[tuple[int, int], Optional[tuple[Dimension, ...]]]) -> Optional[tuple[Dimension, Dimension]]:
    """Rule ``bare-factor`` (STEM repair 1): ``(dimension of a, dimension of b)`` when every reading of the bare numerals of the
    relation ``a = b`` gives the two sides different dimensions, else None. ``leaf_readings`` maps each bare numeral (by offsets)
    to the dimensions it may carry besides a pure factor's (the symbol it was substituted for, an equal value stated with a unit,
    the booklet constant it matches), or to None when it stands for a quantity of unknown dimension (nothing is then decided).
    A side with no operand that carries a unit stays unknown, so a relation of bare numbers against a quantity
    (``120 / 8 = 15 m s⁻¹``) is never a finding. Integer-vector arithmetic only; nothing is evaluated."""
    if not (_carries_unit(a, scope) and _carries_unit(b, scope)):
        return None
    leaves = _bare_leaves(a) + _bare_leaves(b)
    if not leaves:
        return None
    options: list[tuple[tuple[int, int], tuple[Dimension, ...]]] = []
    total = 1
    for leaf in leaves:
        key = (leaf.start, leaf.end)
        extra = leaf_readings.get(key, ())
        if extra is None:
            return None
        dims = (DIMENSIONLESS,) + tuple(d for d in dict.fromkeys(extra) if d != DIMENSIONLESS)
        options.append((key, dims))
        total *= len(dims)
        if total > _MAX_BARE_READINGS:
            return None
    first: Optional[tuple[Dimension, Dimension]] = None
    combos: list[dict[tuple[int, int], Dimension]] = [{}]
    for key, dims in options:
        combos = [{**c, key: d} for c in combos for d in dims]
    for combo in combos:
        da, db = _dim_with(a, scope, combo), _dim_with(b, scope, combo)
        if da is None or db is None:
            continue
        if da.same_physical(db):
            return None
        if first is None:
            first = (da, db)
    return first


def _compact_slash(text: str, divisor: Quantity) -> bool:
    """The divisor's numeral is written right after a slash that has no space on either side (``1/40 s⁻¹``, ``(ln 2)/8 h⁻¹``):
    a fraction written as one figure, which a unit may follow as the fraction's own. A spaced slash (``1 / 0.087 h⁻¹``) or ``÷``
    divides by the whole operand written after it, its unit included."""
    a = divisor.start
    return 2 <= a <= len(text) and text[a - 1] == "/" and not text[a - 2].isspace()


def fraction_unit_node(node: Node, text: str, scope: Scope, depth: int = 0) -> Optional[Node]:
    """Rule ``fraction-unit`` (STEM repair 6): ``node`` with every compact fraction whose divisor is a numeral written with a unit
    (``1/40 s⁻¹``, ``(ln 2)/8 h⁻¹``, ``0.693/8.0 h``), and whose dividend carries no unit and names no quantity, read with the unit
    as the fraction's own: ``(1/40) s⁻¹``. None when ``node`` holds no such fraction (or a node type this does not rebuild).
    Integer-vector arithmetic decides which reading a relation takes (:meth:`_Planner._fraction_units`); nothing is evaluated."""
    if depth > 64:
        return None
    rec = lambda n: fraction_unit_node(n, text, scope, depth + 1)  # noqa: E731
    if isinstance(node, BinOp):
        if node.op == "/" and isinstance(node.right, Quantity) and not node.right.unit.unknown and node.right.unit.dim is not None \
                and not (node.right.number.based or node.right.number.base != 10) and is_closed(node.left) and not _carries_unit(node.left, scope) \
                and _compact_slash(text, node.right):
            q = node.right
            left = rec(node.left) or node.left
            frac = replace(node, left=left, right=Num(q.number, q.start, q.end))
            return WithUnit(frac, q.unit, getattr(node, "start", 0), getattr(node, "end", 0) or q.end)
        a, b = rec(node.left), rec(node.right)
        if a is None and b is None:
            return None
        return replace(node, left=a or node.left, right=b or node.right)
    if isinstance(node, (Neg, Abs, Percent, Degrees, Root, Func, WithUnit)):
        a = rec(node.arg)
        return None if a is None else replace(node, arg=a)
    if isinstance(node, Pow):
        b = rec(node.base)
        return None if b is None else replace(node, base=b)
    if isinstance(node, PlusMinus):
        a = rec(node.left) if node.left is not None else None
        b = rec(node.right)
        if a is None and b is None:
            return None
        return replace(node, left=a or node.left, right=b or node.right)
    return None


def _pure_factor_dimension(node: Node, scope: Scope) -> Optional[Dimension]:
    """The dimension of ``node`` with its bare numerals read as pure factors (rule ``bare-factor``'s first reading), else None."""
    return _dim_with(node, scope, {(n.start, n.end): DIMENSIONLESS for n in _bare_leaves(node)})


def _fraction_texts(node: Node, text: str) -> tuple[str, ...]:
    """The compact fractions of ``node`` read with their trailing unit (rule fraction-unit), as written."""
    out = []
    for n in walk(node):
        if isinstance(n, WithUnit) and isinstance(n.arg, BinOp) and n.arg.op == "/" and isinstance(n.arg.right, Num) \
                and 0 <= n.start < n.end <= len(text):
            a = n.start
            while a > 0 and text[a - 1] in "([{" and text[a:n.end].count(")") + text[a:n.end].count("]") + text[a:n.end].count("}") \
                    > text[a:n.end].count("(") + text[a:n.end].count("[") + text[a:n.end].count("{"):
                a -= 1  # a bracketed dividend: '(ln 2)/8 h⁻¹'
            out.append(" ".join(text[a:n.end].split())[:60])
    return tuple(dict.fromkeys(out))


# ----------------------------------------------------------------------------------------- helpers


def _first(op: Optional[Operand]) -> Optional[Node]:
    return op.readings[0] if op is not None and op.readings else None


def _function_value(node: Optional[Node], text: str) -> Optional[Node]:
    """A function value written ``C(8)`` (a symbol glued to a bracketed number), which the grammar reads as the product ``C·8`` unless
    the letter is f, g or h: the node, else None (rule restated-binding reads it as the value's name)."""
    if not (isinstance(node, BinOp) and node.op == "*" and node.implicit and isinstance(node.left, Sym) and node.left.kind == "symbol"
            and isinstance(node.right, (Num, Quantity))):
        return None
    gap = text[getattr(node.left, "end", 0):getattr(node.right, "start", 0)] if 0 <= getattr(node.left, "end", -1) <= len(text) else ""
    after = text[getattr(node.right, "end", 0):getattr(node.right, "end", 0) + 1]
    return node if gap == "(" and after == ")" else None


def _applied_value(node: Optional[Node], text: str) -> Optional[tuple[str, Node]]:
    """Rule given-function (STEM repair 9): a function's value written applied to a value, ``v(1)`` (the grammar's product of a letter
    glued to a bracketed number: :func:`_function_value`) or ``f(2)`` (f, g or h applied): ``(name, argument)``, else None."""
    if isinstance(node, Apply) and node.arg is not None and is_closed(node.arg) and not isinstance(node.arg, Sym):
        return node.name, node.arg
    fv = _function_value(node, text)
    if fv is not None:
        return fv.left.name, fv.right  # type: ignore[union-attr]
    return None


def _glued_bracket(node: Optional[Node], text: str) -> Optional[tuple[str, Node]]:
    """Rule given-function (STEM repair 9): a letter glued to a bracketed expression, ``v(1/2)``, ``v(−1)`` or ``v(t + 1)`` (the grammar's
    implicit product of the letter and the bracket, the bracket closing right after the expression): ``(letter, expression)``, else
    None. A bracketed number is :func:`_function_value`'s; a bracketed lone letter is a function's variable
    (:func:`_function_definition`)."""
    if not (isinstance(node, BinOp) and node.op == "*" and node.implicit and isinstance(node.left, Sym) and node.left.kind == "symbol"
            and node.right is not None and not isinstance(node.right, (Num, Quantity, Sym))):
        return None
    a, b, e = getattr(node.left, "end", -1), getattr(node.right, "start", -1), getattr(node.right, "end", -1)
    if not (0 <= a <= b <= e < len(text)) or text[a:b] != "(" or text[e:e + 1] != ")":
        return None
    return node.left.name, node.right


def _function_definition(node: Optional[Node], text: str) -> Optional[tuple[str, str]]:
    """Rule given-function (STEM repair 9): a function written applied to its variable before '=', ``v(t)`` (the grammar's product of a
    letter glued to a bracketed letter) or ``f(x)`` (f, g or h applied to a symbol): ``(name, variable)``, else None."""
    if isinstance(node, Apply) and isinstance(node.arg, Sym) and node.arg.kind == "symbol":
        return node.name, node.arg.name
    if isinstance(node, BinOp) and node.op == "*" and node.implicit and isinstance(node.left, Sym) and node.left.kind == "symbol" \
            and isinstance(node.right, Sym) and node.right.kind == "symbol":
        a, b, e = node.left.end, node.right.start, node.right.end
        if 0 <= a <= b <= e <= len(text) and text[a:b] == "(" and text[e:e + 1] == ")":
            return node.left.name, node.right.name
    return None


_WORD_AFTER_RE = re.compile(r"[ \t]*([A-Za-z]+)(?:[ \t]+(cent)\b)?")
#: a group of three digits written after a number with a space ('4 000'): a thousands group, so the number before it is no value
_THOUSANDS_AFTER_RE = re.compile(r"[ \u00a0\u202f]\d{3}(?![\d.,])")
#: words written after a number that name no kind of value
_NO_KIND_WORDS = frozenset({"and", "or", "the", "a", "an", "is", "so", "with", "for", "at", "in", "of", "to", "on", "by", "as", "if", "then", "but",
                            "from", "when", "per", "each", "this", "that", "which", "where", "while", "after", "before"})


#: STEM repair 4 (rule rounding-cue): a part of a unit a task counts in, that a rounding may name ('to the nearest cent' for a value in
#: euros), with its size in that unit
_SUBUNITS = {"cent": {"euro": Fraction(1, 100), "dollar": Fraction(1, 100)}, "penny": {"pound": Fraction(1, 100)},
             "pence": {"pound": Fraction(1, 100)}}


def _singular(word: str) -> str:
    """A word with a plural 's' folded ('euros' -> 'euro', 'years' -> 'year'; 'class' kept), lower case (STEM repair 4)."""
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _word_after(text: str, end: int) -> str:
    """The word written right after a number at ``end`` (rule given-kinds): 'euro' for '4000 euros', 'year' for '5 years', '%' for
    'per cent' or 'percent'; empty when a sign, punctuation or a word that names no kind follows."""
    m = _WORD_AFTER_RE.match(text, end) if 0 <= end <= len(text) else None
    if m is None:
        return ""
    w = m.group(1).lower()
    if (w == "per" and m.group(2)) or w in ("percent", "pc"):
        return "%"
    if w in _NO_KIND_WORDS:
        return ""
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _unset_reason(b: Binding, word: str, percent: bool, supplied_unnamed: bool = False) -> str:
    """Why a Given could not be set against the request (ST-UNDEC-003, rule given-kinds)."""
    if b.unit is not None:
        if b.unit.dim is None or b.unit.unknown:
            return f"its unit {b.unit.text} is one the unit table does not read"
        if supplied_unnamed:
            return (f"the request states no quantity in {b.unit.text}; a supplied text states one, but in no sentence that holds a word of the Given's "
                    "name; and no supplied table names it")
        return f"the request states no quantity in {b.unit.text}, and no supplied table names it"
    if percent:
        return "the request states no percentage"
    if word:
        return f"the request states no number written with '{word}'"
    return "a bare number the request does not state"


#: rule named-given (STEM repair 2): the name of a quantity right before a copula and the value ("The battery's emf is ")
_NAMED_GIVEN_RE = re.compile(r"(?P<name>(?:[A-Za-z][A-Za-z’'-]*[ \t]+){0,3}[A-Za-z][A-Za-z’'-]*)[ \t]+(?:is|was|of|equals|=)[ \t]*$")
_NAME_STOP = frozenset({"the", "a", "an", "its", "their", "this", "that", "so", "and", "then", "therefore", "thus", "hence", "here", "now", "also",
                        "which", "whose", "each", "new", "value", "of"})


def _name_words(text: str) -> list[str]:
    """The content words of a quantity's name, possessives and plurals folded ("battery's emf" -> battery, emf)."""
    out = []
    for w in re.findall(r"[A-Za-z]+(?:[’'][a-z]+)?", text):
        w = w.lower().replace("’s", "").replace("'s", "")
        if w in _NAME_STOP or len(w) < 2:
            continue
        out.append(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)
    return out


#: rule value-at (STEM repair 3): a condition word right before a maths run ('oxygen uptake at 30 °C = …', 'the rate when t = 8 h = …'); STEM
#: repair 8 adds the words that state a time or an extent the value holds under ('speed after 2.0 s = …', 'the energy in 10 s = …', 'the
#: resistance for 2.0 m = …'), never a word that joins an operand written in words (rule fragment: 'by', 'over', 'of', 'to', 'from')
_VALUE_AT_RE = re.compile(r"(?:^|[^A-Za-z])(?:at|when|after|before|during|within|until|for|in)[ \t]*$", re.IGNORECASE)
#: rule name-list (STEM repair 8): the prose right before a maths run ends with a list or a range of values ('Mean of 18, 27 and ', 'the
#: difference between 18 and ', 'Mean of 18 mm³, 27 mm³ and ', 'from 20.0 °C to '), so the run's first value is the list's last item
_NAME_LIST_RE = re.compile(r"(?:^|[\s(])[−-]?\d+(?:\.\d+)?(?:[ \t]*(?:%|[^\s\d,;:=()\[\]]{1,12})){0,3}[ \t]*(?:,[ \t]*(?:and|or)?|and|or|&|to|[–—])[ \t]*$",
                           re.IGNORECASE)
#: rule item-label (STEM repair 8): the noun of a numbered item right before a maths run whose first operand is a whole number ('Time for
#: trial 2 = 33.1 s', 'Year 5 = 4000 × 1.036⁵ = 4773.74'): the number names the item
_ITEM_LABEL_RE = re.compile(r"(?:^|[^A-Za-z])(?:trial|run|repeat|replicate|test|sample|station|tube|day|week|month|year|pass|step|stage|experiment|"
                            r"reading|measurement|quadrat|plot|attempt|term|generation)[ \t]*$", re.IGNORECASE)
#: the words before a condition word that name no quantity
_AT_NAME_STOP = frozenset({"the", "a", "an", "and", "or", "its", "their", "this", "that", "these", "those", "so", "then", "hence", "therefore", "thus", "also",
                           "of", "is", "are", "was", "were", "be", "value", "values", "given", "data", "known", "we", "know", "for", "with", "in", "on",
                           "while", "but", "both", "which", "where", "here", "now", "same", "mean", "average"})


def _at_name(gap: str) -> list[str]:
    """Rule value-at: the content words of the quantity named right before the condition word, back to a clause boundary ('Given:
    oxygen uptake at ' -> oxygen, uptake; 'the count rate at ' -> count, rate; ', and at ' -> none). At most four, lower case."""
    m = _VALUE_AT_RE.search(gap[-24:])
    head = gap[:len(gap) - len(gap[-24:]) + m.start()] if m is not None else gap
    for sep in (".", ";", ":", "\n", ",", "(", ")", "—", "–"):
        k = head.rfind(sep)
        if k >= 0:
            head = head[k + 1:]
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z’'-]*", head[-80:])]
    words = [w[:-2] if w.endswith(("’s", "'s")) else w for w in words]
    return [w for w in words if w not in _AT_NAME_STOP and len(w) >= 2][-4:]


#: rule name-list (STEM repair 8): the list or the range of values the prose ends with right before a maths run, and each of its numbers
_LIST_TAIL_RE = re.compile(r"(?:(?<=[\s(])|^)(?:[−-]?\d+(?:\.\d+)?(?:[ \t]*(?:%|[^\s\d,;:=()\[\]]{1,12})){0,3}[ \t]*(?:,[ \t]*(?:and|or)?|and|or|&|to|[–—])[ \t]*)+$",
                           re.IGNORECASE)
_LIST_NUMBER_RE = re.compile(r"(?<![\w.−-])\d+(?:\.\d+)?")


def _list_values(before: str) -> tuple[ExactNumber, ...]:
    """Rule name-list (STEM repair 8): the numbers of the list or range the prose ``before`` a maths run ends with ('Mean of 18, 27 and ' ->
    18, 27), as written (a signed number is left out); empty when it ends with none."""
    m = _LIST_TAIL_RE.search(before)
    if m is None:
        return ()
    out: list[ExactNumber] = []
    for n in _LIST_NUMBER_RE.finditer(m.group(0)):
        scan = scan_number(n.group(0), 0)
        if scan is not None and scan.number is not None and scan.end == len(n.group(0)):
            out.append(scan.number)
    return tuple(out)


def _additive_groups(node: Node) -> list[tuple[Node, list[Node]]]:
    """STEM repair 8 (rules name-list, table-terms): every sum or difference of ``node`` (a maximal run of '+' and '−'), with its terms,
    signs taken off: '(18 + 27 + 40) ÷ 3' -> [(18 + 27 + 40, [18, 27, 40])], '1620 − 20' -> [(1620 − 20, [1620, 20])]. A term that is no
    single value (a product, a power) is kept as it is, and the sums inside it are groups of their own."""
    out: list[tuple[Node, list[Node]]] = []
    stack: list[Node] = [node]
    seen = 0
    while stack and seen < 400:
        seen += 1
        cur = stack.pop()
        if isinstance(cur, BinOp) and cur.op in ("+", "-"):
            terms: list[Node] = []
            inner = [cur]
            while inner:
                t = inner.pop()
                if isinstance(t, BinOp) and t.op in ("+", "-"):
                    inner.append(t.right)
                    inner.append(t.left)
                elif isinstance(t, Neg):
                    inner.append(t.arg)
                else:
                    terms.append(t)
            out.append((cur, terms))
            stack.extend(t for t in terms if not isinstance(t, (Num, Quantity)))
            continue
        stack.extend(children(cur))
    return out


def _orders(items: list) -> list[list]:
    """Rule law-values (STEM repair 8): every order of ``items`` (at most five: 120 orders), for pairing a line's values with a law's
    symbols."""
    if len(items) <= 1:
        return [list(items)]
    out: list[list] = []
    for i, first in enumerate(items):
        for rest in _orders(items[:i] + items[i + 1:]):
            out.append([first] + rest)
    return out


def _power_of(a: Dimension, b: Dimension) -> bool:
    """STEM repair 8: ``a`` is ``b`` raised to a whole power other than zero (V² of V, s⁻¹ of s; a dimensionless ``b`` gives nothing)."""
    if b.is_dimensionless:
        return False
    k = next((x // y for x, y in zip(a.exps, b.exps) if y != 0), None)
    if k is None or k == 0:
        return False
    return all(x == y * k for x, y in zip(a.exps, b.exps)) and a.angle == b.angle * k


def _law_dims(expr: Node, target: Dimension, known: dict[str, Dimension]) -> dict[str, Dimension]:
    """Rule law-values (STEM repair 8): the dimensions of a law's symbols, those its symbols' stated values give (``known``) and those the
    law's own structure gives from the dimension of the value it takes (``target``): every term of a sum has the sum's dimension, and
    a factor or a divisor whose partner's dimension is known has the one that makes the product's ('V = ε + Ir', V in volts and I in
    amperes: ε in volts, r in ohms). Exact integer arithmetic on the exponents; a power whose exponents do not divide is left unknown."""
    dims = dict(known)

    def dim_of(n: Node, depth: int = 0) -> Optional[Dimension]:
        if depth > 40:
            return None
        if isinstance(n, Sym):
            return DIMENSIONLESS if n.kind == "constant" else dims.get(n.name)
        if isinstance(n, Num):
            return DIMENSIONLESS
        if isinstance(n, Neg):
            return dim_of(n.arg, depth + 1)
        if isinstance(n, Func):
            return DIMENSIONLESS
        if isinstance(n, Pow):
            b = dim_of(n.base, depth + 1)
            return b.power(n.exp) if b is not None and isinstance(n.exp, int) else None
        if isinstance(n, BinOp):
            a, b = dim_of(n.left, depth + 1), dim_of(n.right, depth + 1)
            if n.op in ("+", "-"):
                return a if a is not None else b
            if a is None or b is None:
                return None
            return a * b if n.op == "*" else a / b if n.op == "/" else None
        return None

    def root(d: Dimension, k: int) -> Optional[Dimension]:
        if k == 0 or any(e % k for e in d.exps) or d.angle % k:
            return None
        return Dimension(tuple(e // k for e in d.exps), d.angle // k)  # type: ignore[arg-type]

    def push(n: Node, t: Dimension, depth: int = 0) -> None:
        if depth > 40:
            return
        if isinstance(n, Sym):
            if n.kind == "symbol":
                dims.setdefault(n.name, t)
            return
        if isinstance(n, Neg):
            push(n.arg, t, depth + 1)
            return
        if isinstance(n, Pow) and isinstance(n.exp, int) and n.exp > 0:
            r = root(t, n.exp)
            if r is not None:
                push(n.base, r, depth + 1)
            return
        if isinstance(n, BinOp):
            if n.op in ("+", "-"):
                push(n.left, t, depth + 1)
                push(n.right, t, depth + 1)
                return
            a, b = dim_of(n.left), dim_of(n.right)
            if n.op == "*":
                if a is not None and b is None:
                    push(n.right, t / a, depth + 1)
                elif b is not None and a is None:
                    push(n.left, t / b, depth + 1)
            elif n.op == "/":
                if a is not None and b is None:
                    push(n.right, a / t, depth + 1)
                elif b is not None and a is None:
                    push(n.left, t * b, depth + 1)

    for _ in range(3):
        push(expr, target)
    return dims


#: rules name-list and item-label (STEM repair 8): the words of a clause that name no quantity
_NAME_HEAD_STOP = frozenset({"the", "a", "an", "of", "and", "or", "to", "between", "from", "for", "at", "in", "on", "is", "are", "was", "were", "so", "then",
                             "hence", "therefore", "thus", "also", "its", "their", "this", "that", "these", "those", "with", "we", "it"})


def _name_head(text: str) -> list[str]:
    """Rules name-list and item-label (STEM repair 8): the content words of the clause right before a list's last value or an item's
    number ('Mean of 18, 27 and ' -> mean; 'The difference between 18 and ' -> difference; 'Time for trial ' -> time, trial), back to a
    clause boundary, numbers and units left out. At most four, lower case."""
    head = text
    for sep in (". ", ";", ":", "\n", "(", ")", "—"):
        k = head.rfind(sep)
        if k >= 0:
            head = head[k + len(sep):]
    head = re.sub(r"[−-]?\d+(?:\.\d+)?(?:[ \t]*(?:%|[^\s\d,;:=()\[\]]{1,12}))?", " ", head[-100:])  # the listed values and their units
    words = [w.lower() for w in re.findall(r"(?<![\w.])[A-Za-z][A-Za-z’'-]{1,}", head)]
    words = [w[:-2] if w.endswith(("’s", "'s")) else w for w in words]
    return [w for w in words if w not in _NAME_HEAD_STOP][:4]


def _condition_and_value(cond: Node, value: Node, *, symbol: bool) -> bool:
    """Rule value-at: the condition and the value are values of different kinds, so the '=' between them states the quantity's value
    under the condition and relates no two sides: two units of different dimensions (30 °C and 80 mm³; 8 h and 820 counts min⁻¹), a
    unit beside a bare value, or a unit that is not the condition's and that the table does not read. A condition written for a
    symbol ('at x = 2 = 5') may also be two bare values that differ."""
    c, v = value_of(cond), value_of(value)
    if c is None or v is None:
        return False
    cu, vu = c[2], v[2]
    cd = cu.dim if cu is not None and not cu.unknown else None
    vd = vu.dim if vu is not None and not vu.unknown else None
    if cu is not None and vu is not None:
        if cd is not None and vd is not None:
            return not cd.same_physical(vd)
        return (cd is not None or vd is not None) and " ".join(cu.text.split()) != " ".join(vu.text.split())
    if cu is not None:
        return cd is not None and c[3] != "%"
    if vu is not None:
        return symbol and vd is not None
    return symbol and c[0] != v[0] and not c[3] and not v[3]


def _percent_against_quantity(a: tuple, b: tuple) -> bool:
    """One of two values (``value_of`` tuples) is a percentage with no unit and the other a quantity whose unit has a dimension: no
    restatement of one by the other (STEM repair 3: '… = 820 counts min⁻¹' and a later '2%' had been paired, a false INT-SUBJ-001)."""
    for x, y in ((a, b), (b, a)):
        if x[2] is None and x[3] == "%" and y[2] is not None and y[2].dim is not None and not y[2].unknown and y[2].dim != DIMENSIONLESS:
            return True
    return False


def _temperature(unit: UnitExpr) -> bool:
    """A unit of temperature alone (K, °C, °F): a change written in kelvin and one written in degrees Celsius are the same number."""
    d = unit.dim
    return d is not None and d.exps[4] != 0 and not any(e for i, e in enumerate(d.exps) if i != 4)


def _unit_fits(col_unit: Optional[UnitExpr], w_unit: Optional[UnitExpr]) -> bool:
    """A supplied table's column unit and a stated value's unit of one dimension, or either one not read."""
    if col_unit is None or w_unit is None or col_unit.dim is None or w_unit.dim is None or w_unit.unknown:
        return True
    return col_unit.dim.same_physical(w_unit.dim)


def _cell_unit(col_unit: Optional[UnitExpr], w_unit: Optional[UnitExpr]) -> Optional[UnitExpr]:
    """The unit a supplied table's cell is compared in (STEM repair 3): its column's, when the stated value carries a unit of that
    dimension, so a value restated in another unit ('18 cm³ per g per hour' for the table's 18 mm3 per g per hour) is compared in SI
    and fails; else none, the cell taken as written as before."""
    if col_unit is None or w_unit is None or col_unit.dim is None or w_unit.dim is None or w_unit.unknown or not col_unit.dim.same_physical(w_unit.dim):
        return None
    return col_unit


#: rule given-uncertainty (STEM repair 3): the words that name a Given as an uncertainty of its quantity
_UNCERTAINTY_WORDS = frozenset({"uncertainty", "uncertainties", "precision", "resolution", "tolerance"})


def _given_name_words(item: Optional["MathItem"], name: str) -> list[str]:
    """The content words a Given names its value by (rule supplied-values): its label, or the words before its symbol after the
    statement's head ('Given: background count rate = 30' -> background, count, rate), and the symbol when it is a word."""
    gap = item.gap_before if item is not None else ""
    k = gap.rfind(":")
    gap = gap[k + 1:] if k >= 0 else gap
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", gap[-80:] + " " + name)]
    return [w for w in words if len(w) >= 4 and w not in _AT_NAME_STOP and w not in _NAME_STOP]


#: rule prose-given (STEM repair 6): what ends an item of a Given list before a value (a comma, a semicolon, a colon, a bracket, a line,
#: "and"), a value masked in the prose view, the words that open a Given statement or a name, and the words that join a name to its value
_GIVEN_ITEM_SEP_RE = re.compile(r"[,;:(\n•]|[ \t](?:and|&)(?=[ \t]|$)")
_GIVEN_AFTER_END_RE = re.compile(r"[,;:.()\n•]|[ \t](?:and|&)[ \t]")
_MASKED_RUN_RE = re.compile(r"(?<![A-Za-z])Xx*(?![A-Za-z])")
_GIVEN_ITEM_TOKEN_RE = re.compile(r"(?<![A-Za-z])Xx*(?![A-Za-z])|[A-Za-z][A-Za-z’'\-]*")
_GIVEN_NAME_LEADS = frozenset({"given", "data", "known", "we", "know", "that", "the", "a", "an", "its", "our", "their", "this", "these", "those", "each",
                               "and", "also", "then"})
_GIVEN_NAME_LINKS = frozenset({"is", "was", "are", "were", "be", "being", "equals", "equal", "to", "of", "about", "approximately", "roughly", "around",
                               "nearly", "exactly", "as"})
_GIVEN_CONDITION_WORDS = frozenset({"at", "when", "if", "whenever"})
_GIVEN_COPULAS = frozenset({"is", "was", "are", "were", "equals"})
#: a prose Given written as an uncertainty ('Given: thermometer uncertainty ±0.5 °C', '+/-0.5 °C'), and the unit written after its number
_PROSE_PLUS_MINUS_RE = re.compile(r"(?:±|\+[ \t]*/[ \t]*-)[ \t]*$")
_UNIT_AFTER_RE = re.compile(r"^[ \t]*([^\s,;.()\d][^,;()\n]{0,23}?)[ \t]*(?=$|[,;.()\n]|[ \t](?:and|&|or)[ \t])")
#: what a prose Given is never read after: a currency sign (an amount is no number the branch reads, D31), or a digit group and a space (the
#: number continues a numeral written with a thousands space, never read in part: 'P = 4 000 euros')
_CURRENCY_BEFORE_RE = re.compile(r"[$€£¥₹₩₽¢][ \t]?$")
_THOUSANDS_BEFORE_RE = re.compile(r"\d[ \u00a0\u202f\u2009]$")


def _given_item(before: str, after: str) -> tuple[str, list[str], bool, Optional[int]]:
    """Rule ``prose-given`` (STEM repair 6): the item of a Given list a prose value stands in, read from the statement's prose before it
    (``before``, values masked) and after it: ``(the name as written, its words, whether the value is a condition, the offset in
    ``before`` of the condition it is stated under or None)``. The name is the item's words before the value, from the last comma,
    semicolon, colon, bracket or "and" ('Data: emf 15 V, internal resistance 0.50 Ω': emf; internal resistance), its opening words
    and the words joining it to the value left out ('Given: the mass of seeds is 12 g', 'Given: mass of seeds: 12 g': mass of seeds); a
    value written first is named by the words after it ('Given: 15.0 cm³ of acid': acid). A value right after "at", "when" or "if" is
    the condition another value is stated under ('Given: the uptake at 30 °C is 80 mm³ per g per hour'), never a Given."""
    tail = before.rstrip()
    if tail.endswith(":"):
        tail = tail[:-1]  # 'mass of seeds: 12 g': the item's own colon
    seps = list(_GIVEN_ITEM_SEP_RE.finditer(tail))
    base = seps[-1].end() if seps else 0
    tail = tail[base:]
    tokens = [(m.group(0), m.start() + base) for m in _GIVEN_ITEM_TOKEN_RE.finditer(tail)]
    if tokens and tokens[-1][0].lower() in _GIVEN_CONDITION_WORDS:
        return "", [], True, None
    # another value of the item, not a condition, ends the words before it ('emf 15 V internal resistance 0.50 Ω'); words after it that
    # open with "of" are that value's own ('50.0 cm³ of thiosulfate with 5.0 cm³ of acid')
    last = max((i for i, (w, _a) in enumerate(tokens) if _MASKED_RUN_RE.fullmatch(w)
                and not (i > 0 and tokens[i - 1][0].lower() in _GIVEN_CONDITION_WORDS)), default=None)
    if last is not None:
        tokens = tokens[last + 1:]
        if tokens and tokens[0][0].lower() == "of":
            tokens = []
    cond: Optional[int] = None
    words: list[str] = []
    k = 0
    while k < len(tokens):
        w, at = tokens[k]
        if w.lower() in _GIVEN_CONDITION_WORDS and k + 1 < len(tokens) and _MASKED_RUN_RE.fullmatch(tokens[k + 1][0]):
            cond = tokens[k + 1][1]
            k += 2
            continue
        if not _MASKED_RUN_RE.fullmatch(w):
            words.append(w)
        k += 1
    while words and words[-1].lower() in _GIVEN_NAME_LINKS | _GIVEN_NAME_LEADS:
        words = words[:-1]
    copula = max((i for i, w in enumerate(words) if w.lower() in _GIVEN_COPULAS), default=None)
    if copula is not None and copula + 1 < len(words):
        words = words[copula + 1:]  # 'each value is the mean of 4 repeats': the quantity the copula names (mean)
    while words and words[0].lower() in _GIVEN_NAME_LEADS:
        words = words[1:]
    if not words:
        m = _GIVEN_AFTER_END_RE.search(after)
        seg = after[:m.start()] if m is not None else after
        mv = _MASKED_RUN_RE.search(seg)
        seg = seg[:mv.start()] if mv is not None else seg  # up to the next value ('50.0 cm³ of thiosulfate with 5.0 cm³ of acid')
        words = [w for w in _GIVEN_ITEM_TOKEN_RE.findall(seg[:80]) if not _MASKED_RUN_RE.fullmatch(w)]
        cut = next((i for i, w in enumerate(words) if w.lower() in _GIVEN_CONDITION_WORDS), None)
        words = words[:cut] if cut is not None else words
        while words and words[0].lower() in _GIVEN_NAME_LINKS | _GIVEN_NAME_LEADS:
            words = words[1:]
        while words and words[-1].lower() in _GIVEN_NAME_LINKS | _GIVEN_NAME_LEADS | _NAME_PREPOSITIONS:
            words = words[:-1]
    return " ".join(words)[:60], words, False, cond


def _label_head(rel: "Relation") -> list[str]:
    """The words of a label binding's name ('oxygen uptake')."""
    head = rel.left.node if rel.left is not None else None
    return [w.lower() for w in re.findall(r"[A-Za-z]+", head.name)] if isinstance(head, Sym) else []


def _central_value(node: Node) -> Optional[Node]:
    """The central value of a value written with its absolute uncertainty (``1600 ± 32 counts min⁻¹``: 1600 counts min⁻¹, the unit
    written after the uncertainty being the value's too), else None."""
    if not isinstance(node, PlusMinus) or node.sign != "±" or node.left is None:
        return None
    value, unc = node.left, node.right
    if not isinstance(value, (Num, Quantity)) or not isinstance(unc, (Num, Quantity)):
        return None
    if isinstance(unc, Quantity):
        if isinstance(value, Quantity):
            return value if " ".join(value.unit.text.split()) == " ".join(unc.unit.text.split()) else None
        return Quantity(value.number, unc.unit, value.start, value.end)
    return value


def _stated_value(node: Optional[Node]) -> Optional[Node]:
    """The value a node states: itself, or the central value of a value written with its uncertainty (``1620 ± 32``, ``20.0 ± 0.5 °C``
    and, STEM repair 4, ``1620 ± 2%``), so rule value-at reads 'the count rate at t = 0 h = 1620 ± 2%' as the value at the condition."""
    if isinstance(node, PlusMinus) and node.sign == "±" and node.left is not None:
        mid = _central_value(node)
        if mid is None and isinstance(node.left, (Num, Quantity)) and _percent_number(node.right):
            mid = node.left
        return mid
    return node


def _percent_number(node: Optional[Node]) -> bool:
    """A number written with a per cent sign (``3%``): a relative uncertainty after '±' (STEM repair 4)."""
    return isinstance(node, Percent) and isinstance(node.arg, Num)


def _value_with_uncertainty(node: Optional[Node]) -> bool:
    """A value written with its uncertainty, ``S ± u`` (``12 ± 0.1 V``, ``1620 ± 2%``), or an uncertainty alone, ``±u`` (STEM
    repair 4): data, not an expression to evaluate."""
    if not isinstance(node, PlusMinus) or node.sign != "±" or node.right is None or not is_value(node.right):
        return False
    return node.left is None or is_value(node.left)


def _same_quantity(left: Node, right: Node) -> bool:
    """Two values that are one quantity twice: a unit conversion (two units of one dimension) or the same number written twice."""
    lv, rv = value_of(left), value_of(right)
    if lv is None or rv is None:
        return False
    lu, ru = lv[2], rv[2]
    if lu is not None and ru is not None:
        return lu.dim is not None and ru.dim is not None and lu.dim.same_physical(ru.dim) and (" ".join(lu.text.split()) != " ".join(ru.text.split())
                                                                                              or lv[0] == rv[0])
    return lu is None and ru is None and lv[0] == rv[0] and lv[3] == rv[3]


def _signless(node: Node) -> Node:
    """``node`` without a leading minus or '±' ('±2%' is 2%, '−0.02' is 0.02)."""
    while isinstance(node, Neg) or (isinstance(node, PlusMinus) and node.left is None):
        node = node.arg if isinstance(node, Neg) else node.right
    return node


def _percentage_of(node: Node, leaf: Node, percents: frozenset[Fraction]) -> bool:
    """STEM repair 5 (rule processed-data): ``leaf`` is a factor, in ``node``, of a product with a percentage: one written with '%' ('2% ×
    1620', '1620 × 2%', '±2% × 1620'), or a decimal or a ratio over 100 whose per cent value is one of ``percents`` ('0.02 × 1620' where
    the answer or the supplied text states 2%; '2/100 × 1620'); or the dividend of a division by a number N with 100/N one of
    ``percents`` ('1620/50', 2% of 1620)."""
    for n in walk(node):
        if isinstance(n, BinOp) and n.op == "/" and any(x is leaf for x in walk(n.left)) and is_value(_signless(n.right)):
            d = value_of(_signless(n.right))
            if d is not None and d[2] is None and not d[3] and d[0] > 1 and Fraction(100) / d[0] in percents:
                return True
        if not isinstance(n, BinOp) or n.op != "*":
            continue
        factors: list[Node] = []
        stack: list[Node] = [n]
        while stack and len(factors) < 32:
            cur = stack.pop()
            if isinstance(cur, BinOp) and cur.op == "*":
                stack.extend((cur.right, cur.left))
            else:
                factors.append(cur)
        if not any(f is leaf for f in factors):
            continue
        for f in factors:
            if f is leaf:
                continue
            f = _signless(f)
            if isinstance(f, Percent):
                return True
            if isinstance(f, BinOp) and f.op == "/" and is_value(f.left) and is_value(f.right):
                a, b = value_of(f.left), value_of(f.right)
                if a is not None and b is not None and a[2] is None and b[2] is None and b[0] == 100 and abs(a[0]) in percents:
                    return True
                continue
            v = value_of(f) if is_value(f) else None
            if v is not None and v[2] is None and v[3] != "%" and 0 < abs(v[0]) < 1 and abs(v[0]) * 100 in percents:
                return True
    return False


def _ratio_of(node: Node, leaf: Node, values: frozenset[Fraction]) -> bool:
    """STEM repair 5 (rule processed-data): ``leaf`` stands in a division, in ``node``, whose other side also holds a value of the same
    quantity (another of ``values``): a ratio of two values of the quantity ('1620/820', '20/1620', '(1620 − 20)/1620'), a pure number,
    never a value of the quantity; or ``leaf`` is (in) the divisor: a value set over the raw cell ('32.4/1620 = 0.020', the fractional
    uncertainty of the measured value) is a ratio to it, never a value of its quantity."""
    for n in walk(node):
        if not isinstance(n, BinOp) or n.op != "/":
            continue
        if any(x is leaf for x in walk(n.right)):
            return True
        sides = (n.left, n.right)
        for k, side in enumerate(sides):
            if not any(x is leaf for x in walk(side)):
                continue
            other = sides[1 - k]
            for x in walk(other):
                if isinstance(x, (Num, Quantity)) and x is not leaf and x.number.value in values:
                    return True
    return False


#: how deep the exact evaluation of rule processed-data's shapes follows a written expression
_CELL_EVAL_DEPTH = 48


def _exact_eval(node: Node, cell: Optional[Fraction] = None, x: Fraction = Fraction(0), depth: int = 0) -> Optional[Fraction]:
    """The exact value of a written expression of numerals as written (``+ − × ÷``, integer powers up to 12, signs, a per cent as its
    fraction, a '±' before a value read as '+', every unit as written), with each numeral of value ``cell`` replaced by ``x``; None for
    anything else (a symbol, a function, π, a division by zero). Exact rational bookkeeping for rule processed-data's shapes (STEM
    repair 5): it decides no relation."""
    if depth > _CELL_EVAL_DEPTH:
        return None
    if isinstance(node, (Num, Quantity)):
        return x if cell is not None and node.number.value == cell else node.number.value
    if isinstance(node, WithUnit):
        return _exact_eval(node.arg, cell, x, depth + 1)
    if isinstance(node, Neg):
        v = _exact_eval(node.arg, cell, x, depth + 1)
        return None if v is None else -v
    if isinstance(node, PlusMinus) and node.left is None:
        return _exact_eval(node.right, cell, x, depth + 1)
    if isinstance(node, Percent):
        v = _exact_eval(node.arg, cell, x, depth + 1)
        return None if v is None else v / 100
    if isinstance(node, Pow):
        v = _exact_eval(node.base, cell, x, depth + 1)
        if v is None or abs(node.exp) > 12 or (v == 0 and node.exp <= 0):
            return None
        return v ** node.exp
    if isinstance(node, BinOp) and node.op in ("+", "-", "*", "/"):
        a = _exact_eval(node.left, cell, x, depth + 1)
        b = _exact_eval(node.right, cell, x, depth + 1)
        if a is None or b is None:
            return None
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        return None if b == 0 else a / b
    return None


def _cell_linear(node: Node, cell: Fraction) -> Optional[tuple[Fraction, Fraction]]:
    """STEM repair 5 (rule processed-data): ``node`` as a function of the raw cell: every written numeral of value ``cell`` replaced by
    x and the expression evaluated exactly at x = 0, 1 and 2; ``(a, b)`` when it is a·x + b (a share of the cell, the cell plus or minus
    a number), else None (a symbol, a function, a power of the cell, a division by it)."""
    values = [_exact_eval(node, cell, Fraction(k)) for k in (0, 1, 2)]
    if any(v is None for v in values):
        return None
    e0, e1, e2 = values
    a, b = e1 - e0, e0
    if e2 != 2 * a + b:
        return None
    return a, b


def _share_or_bound_of(node: Node, leaf: Node, percents: frozenset[Fraction]) -> bool:
    """STEM repair 5 (rule processed-data): the line takes, in any arithmetic form, a stated percentage of the raw cell ('1620 × 2 ÷ 100',
    '1620 ÷ 100 × 2': a·x with a = p/100, p a percentage the answer, the request or its supplied texts state), or the cell with that
    percentage of it added or taken away, the bounds of the measured value ('1620 × 1.02', '1620 + 0.02 × 1620': a = 1 ± p/100; '1620 +
    32.4', '1620 − 32': the cell plus or minus a number that is p% of it, within half a unit in that number's last written digit)."""
    if not percents:
        return False
    lin = _cell_linear(node, leaf.number.value)
    if lin is None:
        return False
    a, b = lin
    shares = {p / 100 for p in percents if 0 < p < 100}  # never 100% ('× 100%' makes a ratio a percentage): the cell itself is no share
    if not shares:
        return False
    if b == 0:
        return a in shares or (a - 1) in shares or (1 - a) in shares
    if a != 1:
        return False
    others = [n for n in walk(node) if isinstance(n, (Num, Quantity)) and n.number.value != leaf.number.value]
    h = others[0].number.half_width if len(others) == 1 and abs(others[0].number.value) == abs(b) else Fraction(0)
    return any(abs(abs(b) - abs(leaf.number.value) * s) <= h for s in shares)


def _processed_inline(node: Node, leaf: Node, processed: Fraction) -> bool:
    """STEM repair 5 (rule processed-data): the line processes the raw cell itself, inside its own arithmetic ('C = (1620 − 20) × (1/2)⁴
    = 100 counts min⁻¹'): a sub-expression that holds the cell, written with numerals only, is exactly the processed value."""
    for n in walk(node):
        if n is leaf or not isinstance(n, (BinOp, WithUnit)) or not any(x is leaf for x in walk(n)):
            continue
        v = _exact_eval(n)
        if v is not None and v == processed:
            return True
    return False


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


#: rule solved-law (STEM repair 7): how many operations the isolation of a symbol in a law follows
_SOLVE_DEPTH = 24


def _occurrences(node: Node, name: str) -> int:
    return sum(1 for n in walk(node) if isinstance(n, Sym) and n.kind == "symbol" and n.name == name)


def _solve_for(left: Node, right: Node, name: str, *, roots: bool) -> Optional[Node]:
    """Rule ``solved-law`` (STEM repair 7): the law ``left = right`` solved for the symbol ``name`` by exact inverse operations, or None.
    The symbol must occur once in the law, reached through sums, differences, products, quotients, signs and square roots, and, with
    ``roots``, a square (whose principal root is taken, as the physical quantity's evaluation takes it): ``ε = I(R + r)`` gives
    ``ε/(R + r)`` for I, ``λT½ = ln 2`` gives ``ln 2/T½`` for λ, ``V² = PR`` gives ``V²/R`` for P, ``1/R = 1/R₁ + 1/R₂`` gives
    ``1/(1/R₁ + 1/R₂)`` for R. A symbol twice in the law (a quadratic in it) or under a function is never isolated (None): such a law is an
    equation the next line solves, read as before. The expression is the stated law rearranged, never a new claim of the answer."""
    nl = _occurrences(left, name)
    if nl + _occurrences(right, name) != 1:
        return None
    side, other = (left, right) if nl else (right, left)
    a = min(getattr(left, "start", 0), getattr(right, "start", 0))
    b = max(getattr(left, "end", 0), getattr(right, "end", 0))
    for _ in range(_SOLVE_DEPTH):
        if isinstance(side, Sym):
            return other if side.kind == "symbol" and side.name == name else None
        if isinstance(side, Neg):
            side, other = side.arg, Neg(other, a, b)
            continue
        if isinstance(side, BinOp) and side.op in ("+", "-", "*", "/"):
            in_left = _occurrences(side.left, name) == 1
            if side.op == "+":
                other = BinOp("-", other, side.right if in_left else side.left, a, b)
            elif side.op == "*":
                other = BinOp("/", other, side.right if in_left else side.left, a, b)
            elif side.op == "-":
                other = BinOp("+", other, side.right, a, b) if in_left else BinOp("-", side.left, other, a, b)
            else:
                other = BinOp("*", other, side.right, a, b) if in_left else BinOp("/", side.left, other, a, b)
            side = side.left if in_left else side.right
            continue
        if isinstance(side, Pow) and side.exp == 1:
            side = side.base
            continue
        if isinstance(side, Pow) and side.exp == 2 and roots:
            side, other = side.base, Root(other, 2, a, b)
            continue
        if isinstance(side, Root) and side.index == 2:
            side, other = side.arg, Pow(other, 2, a, b)
            continue
        return None
    return None


def _computed_operand(operands: list[tuple[Operand, str]], ops: list[str]) -> Optional[Operand]:
    """Rule ``finer-restatement`` (STEM repair 7): the operand a chain's last '=' evaluates to its stated final value ('12 V − (4.14 A ×
    0.50 Ω)' of 'V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V'), when it is closed and read one way; else None."""
    if len(operands) < 2 or not ops or ops[-1] != "=":
        return None
    op = operands[-2][0]
    node = op.readings[0] if len(op.readings) == 1 else None
    if node is None or not is_closed(node) or unsupported_reasons(node):
        return None
    return op


def _formula_words(formula: Formula) -> str:
    """How a substitution's reason names the formula it is read against (rule solved-law, STEM repair 7: a law solved for the symbol)."""
    if formula.source == "solved":
        return f" of the law in {formula.statement_id} solved for {formula.name} (rule solved-law)"
    return f" of the formula in {formula.statement_id}"


def _limit_value(node: Node) -> Optional[Fraction]:
    """Rule definite-integral (STEM repair 10): the value of a whole-number limit (a number, or its negation)."""
    v = value_of(node)
    return None if v is None else v[0]


def _limit_text(node: Node) -> str:
    """Rule definite-integral (STEM repair 10): a limit as written in a check's statement ('1', '−1')."""
    return ("−" + node.arg.number.text) if isinstance(node, Neg) and isinstance(node.arg, Num) else getattr(getattr(node, "number", None), "text", render(node))


#: rule unbound-substitution (STEM repair 11): a significant-figure count no written integer reaches (every trailing zero of a whole number counts)
_EVERY_DIGIT_R = 10_000


def _fraction_text(v: Fraction) -> str:
    """A decimal value as a terminating decimal when it is one ('0.036', '1.036'), else as a fraction."""
    for k in range(0, 13):
        scaled = v * 10 ** k
        if scaled.denominator == 1:
            if k == 0:
                return str(scaled.numerator)
            digits = str(abs(scaled.numerator)).rjust(k + 1, "0")
            return ("-" if v < 0 else "") + digits[:-k] + "." + digits[-k:]
    return f"{v.numerator}/{v.denominator}"


def _shape_slots(node: Node, depth: int = 0) -> Optional[tuple[str, tuple[tuple[Fraction, Optional[Node]], ...]]]:
    """Rule ``same-shape`` (STEM repair 11): the shape of a closed expression of written numerals (its operators, the units written and
    its integer powers, each numeral a slot) and its slots in order, ``(value as written, numeral)`` or ``(exponent, None)`` for an integer
    power; None for anything else (a symbol, a function, a constant, notation outside the encodings)."""
    if depth > 40:
        return None
    if isinstance(node, Num):
        if node.number.based or node.number.base != 10 or node.number.vulgar:
            return None
        return "#", ((node.number.value, node),)
    if isinstance(node, Quantity):
        return "#" + " ".join(node.unit.text.split()), ((node.number.value, node),)
    if isinstance(node, Neg):
        inner = _shape_slots(node.arg, depth + 1)
        return None if inner is None else ("−(" + inner[0] + ")", inner[1])
    if isinstance(node, Percent):
        inner = _shape_slots(node.arg, depth + 1)
        return None if inner is None else ("(" + inner[0] + ")%", inner[1])
    if isinstance(node, BinOp):
        a, b = _shape_slots(node.left, depth + 1), _shape_slots(node.right, depth + 1)
        if a is None or b is None:
            return None
        return f"({a[0]}{node.op}{b[0]})", a[1] + b[1]
    if isinstance(node, Pow):
        a = _shape_slots(node.base, depth + 1)
        return None if a is None else (f"({a[0]})^#", a[1] + ((Fraction(node.exp), None),))
    return None


def _ellipsis_value(node: Node) -> Optional[Num]:
    """Rule ellipsis-rounding (STEM repair 10): the decimal written with an ellipsis after it ('4787.58\\ldots'), which the grammar reads as
    the number beside the ellipsis marker, the marker taking nothing after it; None for anything else (a cut value inside an expression,
    '0.333… × 3', is no cut value)."""
    if isinstance(node, BinOp) and node.op == "*" and getattr(node, "implicit", False) and isinstance(node.left, Num) and node.left.number.has_point \
            and isinstance(node.right, Unsupported) and node.right.reason == "an ellipsis" \
            and node.right.end - node.right.start == len(node.right.text or ""):
        return node.left
    return None


def _contains_based(node: Node) -> bool:
    return any(isinstance(n, Num) and (n.number.based or n.number.base != 10) for n in walk(node))


def _approx_context(text: str) -> bool:
    """An approximation word, as a whole word, directly before the item (stem-soundness-6, round 7: never a substring, never a word
    qualifying another quantity earlier in the sentence)."""
    return approx_word_before(text)


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
                 definitions: Optional[list[tuple[int, str, str, frozenset[str], str]]] = None, reading: str = "", text: str = "") -> None:
        self.text = text
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
        #: values stated for a lone symbol or function value ('C0 = 1600'), for rule restated-binding: (item, head, value operand, start)
        self.stated_values: list[tuple] = []
        #: every chain of the answer in order: (statement order, part, the final-value entry or None, the chain's end offset)
        self.chain_ends: list[tuple[int, str, Optional[dict], int]] = []
        self.equations: list[dict] = []
        self.unit_reported: set[tuple[str, str]] = set()
        self.request_relations: list[tuple[Operand, str, Operand]] = []
        self._root_groups: dict[tuple[str, str], int] = {}
        #: stem-soundness-5: the equations of the current system of simultaneous equations (infos), and the sol relation of its stated solution
        self._system: list[dict] = []
        self._system_sol: Optional[int] = None
        #: stem-soundness-11: (equation, letter) -> (the sol relation its next-line roots extend, the order of the last root line)
        self._line_roots: dict[tuple[int, str], tuple[int, int]] = {}
        #: Boolean names the answer defines ('M = (A ∧ B) ∨ …'): name -> (expression, statement id)
        self.bool_defs: dict[str, tuple[Node, str]] = {}
        #: rule boolean-values (STEM repair 4): every value a statement gives a Boolean name ('A = 1'), in document order: (name, value,
        #: statement id, offset), and the constant relations themselves ((name, value, statement id, relation index)) a defined name
        #: may be given under stated inputs ('With A = 1 and B = 1, X = 1' after 'X = A AND B')
        self.bool_values: list[tuple[str, bool, str, int]] = []
        self.bool_constants: list[tuple[str, bool, str, int, Node]] = []
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
        #: relations whose sides' dimensions bare numbers left unknown: read by rule bare-factor once every binding is known
        self._bare_dimension_links: list[tuple[dict, Node, Node, int]] = []
        #: rule value-at: the name of each statement's last quantity stated under a condition ('…, and at 30 °C = 80' takes it)
        self._at_names: dict[str, str] = {}
        #: rule part-value (STEM repair 5): the lone symbol the chain whose links are being read computes ('P' of 'P = I²R = …'), else None
        self._chain_head: Optional[Sym] = None
        #: rule bound-relation (STEM repair 5): relations read as an equation whose symbols all have stated values, for the post-pass
        self._bound_equations: list[tuple[int, MathItem, Node, Node]] = []
        #: rule function-value (STEM repair 11): the names of the functions the request defines (read once)
        self._request_fn_names: Optional[frozenset[str]] = None
        #: rule rearranged-formula (STEM repair 5): the last formula the answer states for each symbol, as the sequence reads it
        self._formula_infos: dict[str, dict] = {}
        #: rule fraction-unit (STEM repair 6): the operands read with a compact fraction's trailing unit as the fraction's own (by
        #: id), and the fractions so read, as written
        self._fraction_read: dict[int, tuple[str, ...]] = {}
        #: rule solved-law (STEM repair 7): while a chain is read, the law before it solved for the symbol the chain evaluates, else None
        self._solved: Optional[Formula] = None
        #: rule law-values (STEM repair 8): while a chain's links are read, its operands and relation signs (a law it states and evaluates)
        self._chain_ctx: Optional[tuple[list, list]] = None
        #: rule value-at for a computing chain (STEM repair 8): each run that computes a quantity's value under a condition, (statement
        #: id, the condition, the offsets of the computation and of the run's end), for rule table-operands
        self._computed_at_runs: list[tuple[str, Node, int, int]] = []
        # argument diagnostics, the named STEM method faults (docs/ARGUMENT_DIAGNOSTICS.md section 3.4):
        #: the final stated value of the chain each operand stands in (by the operand's identity): a law's chain result
        self.final_of_operand: dict[int, dict] = {}
        #: the points the answer evaluates at ('At t = 12 min,'): they bind nothing, and are the inputs ST-RANGE-001 reads
        self.conditions: list[Binding] = []
        #: the reference checks run (off while the closed table of booklet laws is itself read, :func:`.reference.booklet_laws`)
        self.reference_checks = True
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

    # -------------------------------------------------------------- output helpers
    def add(self, **kw: object) -> Relation:
        if self._fraction_read and "fraction_units" not in kw:
            read = tuple(t for side in (kw.get("left"), kw.get("right")) if side is not None for t in self._fraction_read.get(id(side), ()))
            if read:
                kw["fraction_units"] = tuple(dict.fromkeys(read))
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
            self._bound_relations()
            self._boolean_values()
            self._bare_factor_dimensions()
            self._defined_columns()
            self._results()
            self._prose_conversions()
            self._prose_bases()
            self._restated_bindings()
            self._rounded_bindings()
            self._rounded_prose_values()
            self._rounded_digits()
            self._named_changes()
            self._changed_values()
            self._table_values()
            self._value_at_tables()
            self._row_values()
            self._named_components()
            self._table_operands()
            self._processed_data()
            self._percentage_changes()
            self._half_lives()
            self._condition_results()
            self._statistics_prose()
            self._stated_uncertainties()
            self._described_roots()
            self._assignments()
            self._givens()
            self._given_functions()
            self._function_values()
            self._same_shapes()
            self._unbound_substitutions()
            self._named_givens()
            self._named_results()
            self._restated_units()
            self._targets()
            # argument diagnostics: the named STEM method faults (docs/ARGUMENT_DIAGNOSTICS.md section 3.4)
            self._reference_formulas()
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
        if not self.request_mode and chain.ops and not chain.lead and self._question(item, chain):
            return
        if not self.request_mode and chain.ops and not chain.lead and self._stated_false(item, chain):
            return
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
        if not self.request_mode:
            reread = self._fraction_units(full_operands, full_ops)
            if reread:
                operands = [(reread.get(id(op), op), sid) for op, sid in operands]
                full_operands = [(reread.get(id(op), op), sid) for op, sid in full_operands]
        lone_head = _first(full_operands[0][0]) if full_operands else None
        lone = _is_lone(lone_head) or (chain.lead == "label" and not continued)
        if not continued and not self.request_mode and self._statistic_run(item, chain, full_operands, full_ops):
            return  # rule statistics (STEM repair 9): a statistic stated for values the prose lists or for a supplied table's column
        at = None if continued else self._value_at(item, chain, full_operands, full_ops)
        if at is None and not continued:
            at = self._named_value(item, chain, full_operands, full_ops)  # rules name-list and item-label (STEM repair 8)
        if at is not None:
            self._value_at_chain(item, chain, full_operands, full_ops, at)
            return
        # the symbols bound before this chain: a chain's own values must not make its unknowns look bound to the step logic
        chain_syms: set[str] = set()
        for op, _sid in full_operands:
            for r in op.readings:
                chain_syms |= _syms(r)
        bound_before = frozenset(n for n in chain_syms if self.scope.bindings.get(n))
        # rule solved-law (STEM repair 7): the law before the chain solved for the symbol it evaluates (read by its first link)
        self._solved = None if continued else self._solved_law(item, chain, full_operands, full_ops, lone, lone_head, bound_before)
        # bindings first: a later link's substitution may rely on this chain's own values
        self._chain_bindings(item, full_operands, full_ops, lone, lone_head)
        self._record_model(full_operands, full_ops)
        approx_ctx = _approx_context(item.gap_before)
        first_rel, first_finding = len(self.relations), len(self.findings)
        self._chain_head = lone_head if lone and isinstance(lone_head, Sym) and lone_head.kind == "symbol" else None
        self._chain_ctx = (full_operands, full_ops)
        for k in range(len(ops)):
            left, lsid = operands[k]
            right, rsid = operands[k + 1]
            pos = base_pos + k
            self._link(item, left, lsid, ops[k], right, rsid, pos, lone and pos == 0, lone_head if lone else None, approx_ctx, full_operands, full_ops)
        self._chain_head = None
        self._chain_ctx = None
        if not self.request_mode and full_ops and all(o in _EQUALITY for o in full_ops):
            self._chain_dimension(full_operands, lone, first_rel, first_finding)
        if full_ops and not continued:
            self._sequence(item, chain, full_operands, full_ops, lone, lone_head, bound_before)
        self._solved = None
        self.prev_chain = _ChainState(full_operands, full_ops, item, chain.start)
        # remember the final value of the chain (for restatements and show-that targets)
        last = _first(full_operands[-1][0]) if full_operands else None
        entry: Optional[dict] = None
        final_operand = full_operands[-1][0] if full_operands else None
        central = _central_value(last) if last is not None else None
        if central is not None and full_ops and full_ops[-1] in ("=", "≈"):
            # '1620 − 20 = 1600 ± 32 counts min⁻¹': the value the chain states is the central one, with its uncertainty (STEM repair 2)
            last = central
            final_operand = Operand((central,), full_operands[-1][0].start, full_operands[-1][0].end)
        if last is not None and is_value(last) and full_ops and full_ops[-1] in _EQUALITY and final_operand is not None:
            entry = {"node": last, "operand": final_operand, "sid": full_operands[-1][1], "part": item.part,
                     "order": self.order.get(full_operands[-1][1], 0), "symbol": lone_head.name if isinstance(lone_head, Sym) else "",
                     # a computation: more than one link, or a first side that is no lone symbol ('mid = 4' only states a value)
                     "computed": len(full_ops) > 1 or not (lone and isinstance(lone_head, Sym)),
                     "syms": set().union(*(_syms(o.readings[0]) for o, _s in full_operands if o.readings)),
                     # rule finer-restatement (STEM repair 7): the closed expression the chain's last '=' evaluates, as written
                     "expr": _computed_operand(full_operands, full_ops)}
            if central is None:
                self.final_values.append(entry)  # a value with its uncertainty is restated by name only (rule restated-binding)
        if full_operands:
            self.chain_ends.append((self.order.get(full_operands[-1][1], 0), item.part, entry, full_operands[-1][0].end))
            if entry is not None:
                for op_, _sid in full_operands:
                    self.final_of_operand[id(op_)] = entry  # argument diagnostics: a law's chain result (ST-REF-001)
        if not self.request_mode and len(full_operands) >= 2 and full_ops and full_ops[-1] in _APPROX:
            # argument diagnostics (ST-ROUND-001): a chain that ends in a rounding ('… = 0.246 s ≈ 0.25 s')
            u_op, r_op = full_operands[-2][0], full_operands[-1][0]
            un, rn = _first(u_op), _first(r_op)
            if un is not None and rn is not None and is_closed(un) and is_value(rn):
                self.roundings.append({"u": u_op, "r": r_op, "sid": full_operands[-1][1], "part": item.part, "order": self.order.get(full_operands[-1][1], 0),
                                       "symbol": lone_head.name if lone and isinstance(lone_head, Sym) else "", "end": r_op.end})
        head_value = lone_head if lone and isinstance(lone_head, (Sym, Apply)) else _function_value(_first(full_operands[0][0]), self.text)
        if not continued and head_value is not None and len(full_ops) == 1 and full_ops[0] in _EQUALITY and last is not None and is_value(last) \
                and central is None:
            self.stated_values.append((item, head_value, full_operands[-1][0], full_operands[0][0].start))

    def _fraction_units(self, operands: list[tuple[Operand, str]], ops: list[str]) -> dict[int, Operand]:
        """Rule ``fraction-unit`` (STEM repair 6): a unit written right after a fraction whose slash has no space on either side
        (``1/40 s⁻¹``, ``(ln 2)/8 h⁻¹``) is the divisor's (``0.693/8.0 h = 0.087 h⁻¹``) or the whole fraction's (``k = (ln 2)/8 h⁻¹ =
        0.0866 h⁻¹``, the recorded answer's own notation). An operand is read with the fraction's unit when, its bare numbers read as
        pure factors, that reading gives it the dimension of every neighbour in the chain whose dimension is known, and the divisor's
        reading does not: the relation is then checked so (its arithmetic in SI too, its `detail` naming the rule), and no ST-DIM-001
        is raised. Before, rule bare-factor raised ST-DIM-001 on such correct working, and its SI arithmetic could fail
        ('(ln 2)/8 h⁻¹ = 2.4 × 10⁻⁵ s⁻¹'). A spaced slash (``1 / 0.087 h⁻¹ = 11.5 h⁻¹``) or ``÷`` keeps the divisor's unit, and a
        reading that agrees with no neighbour changes nothing. ``{id(old operand): re-read operand}``."""
        out: dict[int, Operand] = {}
        for k, (op, _sid) in enumerate(operands):
            node = _first(op)
            if node is None or len(op.readings) != 1 or op.error:
                continue
            alt = fraction_unit_node(node, self.text, self.scope)
            if alt is None:
                continue
            d0, d1 = _pure_factor_dimension(node, self.scope), _pure_factor_dimension(alt, self.scope)
            if d1 is None:
                continue
            agree = True
            differs = False
            seen = False
            for j in (k - 1, k + 1):
                if not 0 <= j < len(operands) or ops[min(k, j)] in ("→", "⇌", "∝", "⇔"):
                    continue
                other = _first(operands[j][0])
                dn = _pure_factor_dimension(other, self.scope) if other is not None else None
                if dn is None:
                    continue
                seen = True
                if not d1.same_physical(dn):
                    agree = False
                if d0 is None or not d0.same_physical(dn):
                    differs = True
            if not (seen and agree and differs):
                continue
            new_op = Operand((alt,), op.start, op.end, op.error, op.code)
            out[id(op)] = new_op
            self._fraction_read[id(new_op)] = _fraction_texts(alt, self.text)
        return out

    def _question(self, item: MathItem, chain: Chain) -> bool:
        """Rule ``question`` (STEM repair 2): a relation the answer asks ("Is 38 = 67? No", a trace's "38 = 67? no; 38 < 67") is
        no claim of it. Answered "no" or "false", its negation is checked (``38 ≠ 67``); answered "yes" or "true", the relation
        itself; with no answer it is context, nothing claimed. A chain of more than one link asked as a question is context.
        True when the chain was handled here."""
        if not (0 <= chain.end <= len(self.text)):
            return False
        m = _QUESTION_RE.match(self.text, chain.end)
        if m is None:
            return False
        answer = (m.group(1) or "").lower()
        sid = item.statement_id
        first, last = chain.operands[0], chain.operands[-1]
        base = dict(statement_ids=(sid,), start=first.start, end=last.end, op=chain.ops[0], left=first, right=last, part=item.part, position=0)
        if len(chain.ops) != 1 or not answer or chain.ops[0] not in _NEGATION:
            self.add(kind="question", outcome="context", reason="a relation the answer asks as a question, with no answer the branch reads: nothing "
                                                              "is claimed", **base)
            return True
        op = chain.ops[0] if answer in _YES_WORDS else _NEGATION[chain.ops[0]]
        lead = first.node if not chain.lead else None
        before = len(self.relations)
        self._link(item, first, sid, op, last, sid, 0, _is_lone(lead), lead if _is_lone(lead) else None, False, [(first, sid), (last, sid)], [op])
        for k in range(before, len(self.relations)):
            r = self.relations[k]
            note = f"a relation asked as a question and answered '{m.group(1)}': {'its negation' if op != chain.ops[0] else 'the relation'} is checked"
            self.relations[k] = replace(r, reason=(r.reason + "; " if r.reason else "") + note)
        return True

    def _stated_false(self, item: MathItem, chain: Chain) -> bool:
        """stem-precision-8 (round 7): a comparison of one link the text says is false ('2 <= 1, which is false', 'Since 5 > 8 is false',
        '(2 <= 1) fails') claims its negation: the negation is checked, as rule question checks a relation answered "no" (it had been
        checked as asserted, and every loop trace that states a failing test got INT-SUBJ-001). True when the chain was handled here."""
        if len(chain.ops) != 1 or chain.ops[0] not in _NEGATION or chain.ops[0] in _EQUALITY or not (0 <= chain.end <= len(self.text)):
            return False
        m = _STATED_FALSE_RE.match(self.text, chain.end)
        if m is None:
            return False
        sid = item.statement_id
        first, last = chain.operands[0], chain.operands[-1]
        op = _NEGATION[chain.ops[0]]
        lead = first.node if not chain.lead else None
        before = len(self.relations)
        self._link(item, first, sid, op, last, sid, 0, _is_lone(lead), lead if _is_lone(lead) else None, False, [(first, sid), (last, sid)], [op])
        for k in range(before, len(self.relations)):
            r = self.relations[k]
            note = f"a comparison the text states is false ('{' '.join(m.group(0).split())[:40]}'): its negation is checked"
            self.relations[k] = replace(r, reason=(r.reason + "; " if r.reason else "") + note)
        return True

    def _value_at(self, item: MathItem, chain: Chain, operands: list[tuple[Operand, str]], ops: list[str]) -> Optional[tuple[int, list[str], Operand, str]]:
        """Rule ``value-at`` (STEM repair 3): a maths run right after a condition word ('at', 'when') that opens with the condition
        and then states the named quantity's value: 'oxygen uptake at 30 °C = 80 mm³ per g per hour', 'the count rate at t = 8 h =
        820 counts min⁻¹', 'time at 30.0 °C = 33.1 s'. The '=' after the condition says what the quantity is under it; it relates
        no two sides (before: '30 °C = 80 mm³' was a unit conversion and failed, an INT-SUBJ-001 on correct work). Read only when the
        condition and the value are values of different kinds (two dimensions, or a bare value beside a quantity), so 'at 25 °C =
        298 K' stays a conversion of the condition. Returns ``(index of the value operand, the quantity's name words, the condition
        operand, the condition's symbol)``, else None."""
        if self.request_mode or chain.lead or not ops or not operands or item.span_kind not in ("math_run", "latex_inline"):
            return None
        if operands[0][0].start > item.start + 1 or not _VALUE_AT_RE.search(item.gap_before[-24:]):
            return None
        first = _first(operands[0][0])
        if isinstance(first, Sym) and first.kind == "symbol" and len(ops) >= 2 and ops[0] == "=" and ops[1] in ("=", "≈"):
            v, w = _first(operands[1][0]), _stated_value(_first(operands[2][0]))
            if v is not None and w is not None and is_value(v) and is_value(w) and _condition_and_value(v, w, symbol=True):
                return 2, _at_name(item.gap_before), operands[1][0], first.name
            if v is not None and is_value(v) and self._computed_at(operands, ops, 2, v, symbol=True):
                return 2, _at_name(item.gap_before), operands[1][0], first.name
            return None
        if first is not None and is_value(first) and ops[0] in ("=", "≈"):
            w = _stated_value(_first(operands[1][0]))
            if w is not None and is_value(w) and _condition_and_value(first, w, symbol=False):
                return 1, _at_name(item.gap_before), operands[0][0], ""
            if self._computed_at(operands, ops, 1, first, symbol=False):
                return 1, _at_name(item.gap_before), operands[0][0], ""
        return None

    def _computed_at(self, operands: list[tuple[Operand, str]], ops: list[str], widx: int, cond: Node, *, symbol: bool) -> bool:
        """Rule value-at for a computing chain (STEM repair 8): after the condition the run computes the named quantity's value, a written
        expression with no symbol and then, usually, the value it gives ('mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s',
        'I at t = 5 s = 12 V / 4.5 Ω = 2.7 A', 'uptake at 30 °C = 2 × 40 = 80', 'the corrected rate at t = 40 h = 1600 counts min⁻¹ × (1/2)⁵
        = 50 counts min⁻¹'), every link after the condition written '=' or '≈'. The condition and the value are of different kinds as for a
        plain value (rule value-at): the value the chain states last against the condition, or, when it states none, the expression's own
        dimension (a written expression with no unit beside a condition with one). Before, the '=' after the condition was read as a relation
        between the condition and the expression and failed (INT-SUBJ-001 on correct working, with ST-DIM-001). A conversion of the condition
        ('T at 25 °C = 25 + 273 = 298 K', the value of the condition's dimension) is read as before."""
        if widx >= len(operands) or any(o not in ("=", "≈") for o in ops[widx - 1:]):
            return False
        node = _first(operands[widx][0])
        if node is None or is_value(node) or not is_closed(node) or unsupported_reasons(node) or _value_with_uncertainty(node):
            return False
        if widx + 1 < len(operands):
            last = _stated_value(_first(operands[-1][0]))
            return last is not None and is_value(last) and _condition_and_value(cond, last, symbol=symbol)
        c = value_of(cond)
        cd = c[2].dim if c is not None and c[2] is not None and not c[2].unknown else None
        if cd is None or (c is not None and c[3] == "%"):
            return False
        if not any(isinstance(n, (Quantity, WithUnit)) for n in walk(node)):
            return True  # a written expression with no unit beside a condition with one ('uptake at 30 °C = 2 × 40')
        d = dimension_of(node, self.scope)
        return d is not None and not cd.same_physical(d)

    def _statistic_run(self, item: MathItem, chain: Chain, operands: list[tuple[Operand, str]], ops: list[str]) -> bool:
        """Rule ``statistics`` (STEM repair 9): a maths run that states a statistic's value with no working, for values the prose lists
        right before it ('Median of 18, 27, 40, 58, 80, 92 and 61 = 61', the run starting at the list's last value) or for a supplied
        table's column its label names ('Median uptake = 61 mm³ per g per hour'): the value is set against the statistic of those values
        (:meth:`_plan_statistic`); a statistic outside the encodings (a standard deviation, a quartile …) is named ST-UNDEC-001. Before,
        the list's last value was read as a side of a relation ('61 = 61', which held) or as a relation written partly in words
        (ST-PARSE-001), and the label as a defined name: a wrong median was neither checked nor named. True when handled."""
        if item.span_kind not in ("math_run", "latex_inline") or not ops or len(operands) != 2 or ops[0] not in ("=", "≈"):
            return False
        sid = item.statement_id
        stated_op = operands[1][0]
        stated = _first(stated_op)
        if stated is None or not is_value(stated) or _value_with_uncertainty(stated):
            return False
        if chain.lead == "label":
            m = _STAT_RE.search(item.label or "")
            if m is None:
                return False
            words = [w for w in _label_words((item.label[:m.start()] + " " + item.label[m.end():])) if w not in _STAT_FILLER]
            k = item.statement_text.rfind(item.label, 0, max(0, item.start - item.statement_start + 1))
            at = item.statement_start + k if k >= 0 else operands[0][0].start
            return self._plan_statistic(m, None, words, stated_op, sid, item.part, at, stated_op.end, item.statement_id)
        first_op = operands[0][0]
        first = _first(first_op)
        if first is None or not is_value(first) or first_op.start > item.start + 1 or not (0 <= item.start <= len(self.text)):
            return False
        before = self.text[max(item.statement_start, item.start - 200, 0):item.start]
        m = _STAT_LIST_RUN_RE.search(before)
        if m is None:
            return False
        base_at = item.start - len(before)
        entries = [(sc, base_at + m.start("list") + n.start(), base_at + m.start("list") + n.end()) for n in _LIST_NUMBER_RE.finditer(m.group("list"))
                   for sc in (scan_number(n.group(0), 0),) if sc is not None and sc.number is not None and sc.end == len(n.group(0))]
        fv = value_of(first)
        if fv is None or fv[1] is None:
            return False
        nodes: list[Node] = [Num(sc.number, a, b) for sc, a, b in entries] + [first]
        return self._plan_statistic(m, nodes, [], stated_op, sid, item.part, base_at + m.start(), stated_op.end, item.statement_id)

    def _statistics_prose(self) -> None:
        """Rule ``statistics`` (STEM repair 9) for a value the prose states: 'The median of 18, 27, 40, 58, 80, 92 and 61 is 61.' (the
        values it lists between 'of' and the copula), 'The median uptake is 61 mm³ per g per hour.' (a supplied table's column its words
        name, with no row named). As :meth:`_statistic_run` does for a maths run."""
        if not self.prose_values:
            return
        planned = {(r.start, r.end) for r in self.relations if r.outcome == "check"}
        for pv in self.prose_values:
            if (pv.start, pv.end) in planned or pv.given:
                continue
            tail = pv.before[-220:]
            m = _STAT_LIST_PROSE_RE.search(tail)
            base_at = pv.start - len(tail)
            if m is not None:
                nodes = [q.node for q in self.prose_values if q.statement_id == pv.statement_id and base_at + m.start("list") <= q.start
                         and q.end <= base_at + m.end("list")]
                if len(nodes) < 2:
                    continue
                self._plan_statistic(m, nodes, [], Operand((pv.node,), pv.start, pv.end), pv.statement_id, pv.part, base_at + m.start(), pv.end,
                                     pv.statement_id)
                continue
            m = _STAT_COLUMN_PROSE_RE.search(tail)
            if m is None or not self.request.tables:
                continue
            if any(w.lower() in _NAME_PREPOSITIONS for w in m.group("words").split()):
                continue  # 'the mean uptake at C is …': a row's value, never the column's statistic
            words = [w for w in _label_words(m.group("words")) if w not in _STAT_FILLER]
            self._plan_statistic(m, None, words, Operand((pv.node,), pv.start, pv.end), pv.statement_id, pv.part, base_at + m.start(), pv.end,
                                 pv.statement_id)

    def _plan_statistic(self, m: "re.Match[str]", nodes: Optional[list[Node]], words: list[str], stated_op: Operand, sid: str, part: str,
                        start: int, end: int, at_sid: str) -> bool:
        """Rule statistics (STEM repair 9): plan the check of a statistic's stated value. ``nodes``: the values the prose lists; else
        ``words`` name a supplied table's column (exactly one value column whose name holds them, no row named), whose cells are the
        values. The statistic is formed by the STEM pack from the values as written: the median by ordering them (the middle one, or the
        mean of the middle two), the mode by counting them (one value occurring most often, more than once), the range as the largest
        minus the smallest, the mean as their sum over their count; an ``eq`` check of it against the stated value, the engine deciding
        the comparison under the tolerance rule, at warning severity (which values the statistic is of is a reading). A standard deviation,
        a variance, a quartile, a percentile or an interquartile range is named ST-UNDEC-001, unchecked, and so is a mode the values do
        not have (none repeated, or two most frequent). True when the run or the value is handled."""
        name = " ".join(m.group("stat").lower().split())
        kind = _STAT_COMPUTED.get(name)
        if kind is None:
            self.finding("ST-UNDEC-001", f"a relation outside the encodings: a statistic ({name}); the relation in {sid} is not checked", (sid,), start, end)
            self.add(kind="link", outcome="undecided", statement_ids=(sid,), start=start, end=end, part=part, code="ST-UNDEC-001",
                     reason=f"a relation outside the encodings: a statistic ({name}) (rule statistics)")
            return True
        what = "the values the prose lists"
        if nodes is None:
            if not words:
                return False
            hits = [(t, j) for t in self.request.tables for j in t.value_columns() if t.columns[j].words and set(words) <= t.columns[j].words]
            if len(hits) != 1:
                return False
            table, j = hits[0]
            nodes = [Num(row[j][1], start, start) for row in table.rows if row[j][1] is not None]
            what = f"the supplied table's {table.columns[j].name}"
        values = [value_of(n) for n in nodes]
        if len(nodes) < 2 or any(v is None or v[1] is None for v in values):
            return False
        order = sorted(range(len(nodes)), key=lambda k: values[k][0])  # type: ignore[index]
        k = len(nodes)
        formed: Optional[Node] = None
        shown = ""
        if kind == "median":
            if k % 2:
                formed = nodes[order[k // 2]]
                shown = f"the middle one of the {k} values in order, {render(formed)[:30]}"
            else:
                a, b = nodes[order[k // 2 - 1]], nodes[order[k // 2]]
                formed = BinOp("/", BinOp("+", a, b, start, end), _exact_num(2, start), start, end)
                shown = f"the mean of the middle two of the {k} values in order, ({render(a)[:20]} + {render(b)[:20]})/2"
        elif kind == "range":
            formed = BinOp("-", nodes[order[-1]], nodes[order[0]], start, end)
            shown = f"the largest of the {k} values minus the smallest, {render(nodes[order[-1]])[:20]} − {render(nodes[order[0]])[:20]}"
        elif kind == "mean":
            total: Node = nodes[0]
            for n in nodes[1:]:
                total = BinOp("+", total, n, start, end)
            formed = BinOp("/", total, _exact_num(k, start), start, end)
            shown = f"the sum of the {k} values over {k}"
        else:  # the mode
            counts: dict[Fraction, int] = {}
            for v in values:
                counts[v[0]] = counts.get(v[0], 0) + 1  # type: ignore[index]
            top = max(counts.values())
            modes = [x for x, c in counts.items() if c == top]
            if top < 2 or len(modes) != 1:
                self.finding("ST-UNDEC-001", f"a relation outside the encodings: a mode the values do not have as one value ({'no value occurs twice' if top < 2 else 'two values occur most often'}); "
                                             f"the relation in {sid} is not checked", (sid,), start, end)
                self.add(kind="link", outcome="undecided", statement_ids=(sid,), start=start, end=end, part=part, code="ST-UNDEC-001",
                         reason="a relation outside the encodings: a mode the values do not have as one value (rule statistics)")
                return True
            formed = next(n for n, v in zip(nodes, values) if v[0] == modes[0])  # type: ignore[index]
            shown = f"the value that occurs most often ({top} times), {render(formed)[:30]}"
        self.add(kind="eq", outcome="check", statement_ids=(sid,), start=start, end=end, op="=", left=Operand((formed,), start, end), right=stated_op,
                 part=part, title=f"the {name} of {what}, formed by the STEM pack, against the stated value",
                 reason=f"the {name} of {what} ({shown}) against the value the answer states (rule statistics)")
        return True

    def _named_value(self, item: MathItem, chain: Chain, operands: list[tuple[Operand, str]], ops: list[str]) -> Optional[tuple]:
        """Rules ``name-list`` and ``item-label`` (STEM repair 8): the run's first operand is a value the prose before it uses to name the
        quantity whose value the run gives, never a side of a relation: the last value of a list or a range the prose writes right before
        the run ('Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3', 'Difference between 18 and 40 = 40 − 18 = 22', 'The rise from 20.0 °C
        to 30.0 °C = 30.0 − 20.0 = 10.0 K'), or the whole number of a numbered item ('Time for trial 2 = 33.1 s', 'Year 5 = 4000 × 1.036⁵ =
        4773.74'). Before, the first '=' related that value to the expression or the value after it and failed (INT-SUBJ-001 on correct
        working: '40 = (18 + 27 + 40) ÷ 3'). The chain after it is the named quantity's value, its links checked as in any chain; the list
        or the item is part of the name and is not set against the working. A list or a range is read so only when the run goes on to
        compute (a written expression after the '='): '… 18, 27 and 40 = 28.3' stays a relation written partly in words (rule fragment,
        ST-PARSE-001). ``(1, name words, None, '', rule)``, else None."""
        if self.request_mode or chain.lead or not ops or len(operands) < 2 or item.span_kind not in ("math_run", "latex_inline"):
            return None
        if operands[0][0].start > item.start + 1 or any(o not in ("=", "≈") for o in ops):
            return None
        first, second = _first(operands[0][0]), _first(operands[1][0])
        if first is None or second is None or not is_value(first) or len(operands[0][0].readings) != 1:
            return None
        v = value_of(first)
        if v is None or v[1] is None:
            return None
        if isinstance(first, Num) and not v[3] and v[0] > 0 and v[0].denominator == 1 and "." not in first.number.text \
                and _ITEM_LABEL_RE.search(item.gap_before[-30:]):
            return 1, _name_head(item.gap_before) + [first.number.text], None, "", "item-label"
        if is_value(second) or not is_closed(second) or unsupported_reasons(second) or _value_with_uncertainty(second):
            return None
        before = self.text[max(item.statement_start, item.start - 160, 0):item.start] if 0 <= item.start <= len(self.text) else ""
        if not _NAME_LIST_RE.search(before):
            return None
        return 1, _name_head(before), None, "", "name-list", _list_values(before) + (v[1],)

    def _value_at_chain(self, item: MathItem, chain: Chain, operands: list[tuple[Operand, str]], ops: list[str], at: tuple) -> None:
        """Rule ``value-at``: the value stated for the named quantity under its condition is a binding of that quantity (a ``label``
        binding carrying the condition), never a relation between the condition and the value; the condition binds nothing (its
        symbol keeps its other values). The links after the value ('= 0.080 cm³') are read as in any chain. A clause that names no
        quantity ('…, and at 30 °C = 80 mm³') takes the name of the statement's last such clause. Given values and values of a
        supplied table's rows are set against the request by rules given-kinds and table-data."""
        widx, words, cond_op, cond_sym = at[:4]
        rule = at[4] if len(at) > 4 else "value-at"
        sid = item.statement_id
        w_op = operands[widx][0]
        w_node = _first(w_op)
        # STEM repair 8: the run computes the value (a written expression after the condition, the list's last value or the item's number)
        computing = w_node is not None and not is_value(w_node) and _stated_value(w_node) is w_node
        if cond_op is not None:
            name = " ".join(words) or self._at_names.get(sid, "")
            if name:
                self._at_names[sid] = name
            cond_node = _first(cond_op)
            shown = f"{cond_sym} = " if cond_sym else ""
            at_start = cond_op.start
            reason = (f"the value of '{name or 'the quantity'}' at {shown}{render(cond_node)[:40] if cond_node is not None else ''}: "
                      + ("a value the run computes for the quantity under the condition, its links checked as in any chain"
                         if computing else "a value stated for the quantity under the condition")
                      + ", not a relation between the condition and the value (rule value-at)")
        else:
            # rules name-list and item-label (STEM repair 8): the run's first value is part of the quantity's name
            name = " ".join(words)
            first_op = operands[0][0]
            at_start = first_op.start
            written = render(_first(first_op))[:40] if _first(first_op) is not None else ""
            reason = (f"the value of '{name or 'the quantity'}': {written} ends the list or the range of values that names the quantity, never a side "
                      "of a relation; the run computes its value, its links checked as in any chain (rule name-list)" if rule == "name-list" else
                      f"the value of '{name or 'the quantity'}': {written} numbers the item the prose names, never a side of a relation "
                      + ("; the run computes its value, its links checked as in any chain" if computing else "") + " (rule item-label)")
        label = Sym(name or "the quantity", kind="label", start=at_start, end=at_start)
        base = dict(statement_ids=(sid,), start=at_start, end=w_op.end, op=ops[widx - 1], left=Operand((label,), at_start, at_start),
                    right=w_op, part=item.part, position=0)
        if not computing or widx + 1 >= len(operands):
            self._value_notes(base, w_node)  # a computing chain's links note their own sides' dimensions and units
        self.add(kind="label", outcome="binding", condition=cond_op, condition_symbol=cond_sym, reason=reason, **base)
        approx_ctx = _approx_context(item.gap_before)
        for k in range(widx, len(ops)):
            left, lsid = operands[k]
            right, rsid = operands[k + 1]
            self._link(item, left, lsid, ops[k], right, rsid, k, False, None, approx_ctx, operands, ops)
        if computing and w_node is not None:
            if cond_op is not None:
                self._condition_value(item, cond_op, w_node, sid)
                if _first(cond_op) is not None:
                    self._computed_at_runs.append((sid, _first(cond_op), w_op.start, operands[-1][0].end))  # type: ignore[arg-type]
            elif rule == "name-list" and len(at) > 5:
                self._list_terms(item, at[5], operands[0][0], w_node, sid)
        self.prev_chain = _ChainState(operands, ops, item, chain.start)
        self.prev_rel = None
        last = _first(operands[-1][0])
        entry: Optional[dict] = None
        if last is not None and is_value(last) and ops[-1] in _EQUALITY:
            entry = {"node": last, "operand": operands[-1][0], "sid": operands[-1][1], "part": item.part, "order": self.order.get(operands[-1][1], 0),
                     "symbol": "", "computed": False, "syms": set()}
            if computing and widx + 1 < len(operands):
                # STEM repair 8: the value a computing chain gives is a computed final value (a restatement of it is read as of any chain's)
                entry["computed"] = True
                entry["expr"] = _computed_operand(operands[widx:], ops[widx:])
            self.final_values.append(entry)
        self.chain_ends.append((self.order.get(operands[-1][1], 0), item.part, entry, operands[-1][0].end))

    def _condition_value(self, item: MathItem, cond_op: Operand, node: Node, sid: str) -> None:
        """Rule ``condition-value`` (STEM repair 8): when a run read by rule value-at computes its value ('speed after 2.0 s = 9.8 m s⁻² ×
        2.0 s = 19.6 m s⁻¹') and its computation takes exactly one value of the condition's dimension (by its written unit; several
        occurrences of one value count once), that value stands for the condition: it is set against the condition's value, both
        half-widths banding the comparison, in SI, at warning severity (which value of the computation is the condition is a reading).
        '… × 3.0 s' fails against 'after 2.0 s'. Nothing is read when the condition has no unit (or is a percentage), or the computation
        takes no value, or more than one value, of the condition's dimension ('9.8 m s⁻² × (4.0 s − 1.0 s)')."""
        cond = _first(cond_op)
        c = value_of(cond) if cond is not None else None
        if c is None or c[1] is None or c[2] is None or c[2].unknown or c[2].dim is None or c[3]:
            return
        if si_value(c[0], c[2], c[3]) is None:
            return  # a condition with no exact SI reading ('at 25 °C', an affine unit) is compared with nothing
        hits = [n for n in walk(node) if isinstance(n, Quantity) and not n.unit.unknown and n.unit.dim is not None and n.unit.dim.same_physical(c[2].dim)]
        if not hits:
            return
        si = {si_value(n.number.value, n.unit, "") for n in hits}
        if len(si) != 1 or None in si:
            return
        leaf = hits[0]
        cand = Binding("the condition", c[0], c[1], c[2], "statement", sid, cond_op.start, cond_op.end, wrapper=c[3])
        self.add(kind="giv", outcome="check", statement_ids=(sid,), start=leaf.start, end=leaf.end, op="=", right=Operand((leaf,), leaf.start, leaf.end),
                 left=Operand((Sym("the condition", start=leaf.start, end=leaf.start),), leaf.start, leaf.start), candidates=(cand,), part=item.part,
                 title="the value the computation takes for its condition against the condition",
                 reason=f"the value {render(leaf)[:40]} the run's computation takes of the dimension of the condition it is stated under, against that "
                        f"condition ({render(cond)[:40]}) (rule condition-value)")

    def _list_terms(self, item: MathItem, listed: tuple[ExactNumber, ...], first_op: Operand, node: Node, sid: str) -> None:
        """Rule ``name-list``'s check (STEM repair 8): in a run read by rule name-list ('Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3'),
        the terms of each sum or difference of the computation that takes one of the listed values stand for listed values: a term that
        is no listed value (as written) is set against the list's values, taken as written, at warning severity (which listed value it
        stands for is a reading): '(18 + 27 + 41) ÷ 3' fails. A computation that takes none of them as a term ('85 ÷ 3', the sum carried)
        is not read."""
        if not listed:
            return
        values = {n.value for n in listed}
        planned: set[tuple[int, int]] = set()
        for _whole, terms in _additive_groups(node):
            leaves = [t for t in terms if isinstance(t, (Num, Quantity))]
            if not any(t.number.value in values for t in leaves):
                continue
            for t in leaves:
                if t.number.value in values or (t.start, t.end) in planned or t.number.value in (100, 1000):
                    continue
                planned.add((t.start, t.end))
                cands = tuple(Binding("the listed value", n.value, n, None, "statement", sid, first_op.start, first_op.end) for n in listed[:8])
                self.add(kind="giv", outcome="check", statement_ids=(sid,), start=t.start, end=t.end, op="=", right=Operand((t,), t.start, t.end),
                         left=Operand((Sym("the listed value", start=t.start, end=t.start),), t.start, t.start), candidates=cands, part=item.part,
                         exact_candidates=True, named="the list the prose names",
                         title="a value the computation takes against the values the prose lists",
                         reason=f"the value {t.number.text} the computation takes beside the listed values, against the values the prose lists before the "
                                f"run ({', '.join(n.text for n in listed[:8])}) (rule name-list)")

    def _cut_left(self, item: MathItem, left: Operand) -> str:
        """Rule ``fragment`` (STEM repair 2): the word right before a math run whose first operand opens the run, when it is a word
        that joins the run to an operand written before it in words ("17 is divided by 5 = 2", "20% of 50 = 10", "the square root
        of 16 = 4", "12 over 4 = 3"): the run's left side is then only the tail of its expression. Empty otherwise."""
        if item.span_kind != "math_run" or left.start != item.start:
            return ""
        m = _TRAILING_WORD_RE.search(item.gap_before[-40:])
        if m is None:
            return ""
        w = m.group(1).lower()
        return w if w in _JOINING_WORDS else ""

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
                # 'At x = 1:' evaluates at a point; it binds nothing beyond its statement (the point is kept for ST-RANGE-001,
                # argument diagnostics)
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
        if pos == 0 and op in _EQUALITY and isinstance(lnode, Unsupported) and lnode.reason == "a derivative" and lnode.name and lnode.arg is not None \
                and is_closed(lnode.arg) \
                and is_closed(rnode) and not unsupported_reasons(rnode):
            # f′(2) = 3 × 2² − 2: the derivative's stated formula evaluated at the argument (no formula stated: undecided)
            if self._evaluation(base, item, lnode.name, lnode.arg, rnode, derivative=True):
                return
        if op in _EQUALITY and self._derivative(base, lnode, rnode):
            return  # STEM repair 11 (rule derivative): 'dv/dt = 6 − 6t', 'd/dt (3t²) = 6t', 'f′(x) = 3x²' after 'f(x) = x³'
        if op in _EQUALITY and self._definite(base, lnode, rnode):
            return  # STEM repair 10 (rule definite-integral): ∫₀¹ 6t dt = [3t²]₀¹ = 3
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
        if reasons == ("an ellipsis",) and op == "=" and self._ellipsis_restatement(base, item, lnode, rnode, right):
            return  # STEM repair 10 (rule ellipsis-rounding): '= 4787.58\ldots = 4788 euros, to the nearest euro'
        if reasons == ("an ellipsis",) and op in ("=", "≈", "≃") and self._ellipsis_cut(base, lnode, rnode):
            return  # STEM repair 10 (rule ellipsis-rounding): '8/3 = 2.66…', '0.333… = 1/3', '8/3 ≈ 2.66…'
        if reasons:
            self._undecided("ST-UNDEC-001", "a relation outside the encodings: " + "; ".join(reasons), base, item)
            return
        if op in ("→", "⇌", "∝", "⇔") and not (op == "⇔" and self.profile.computer_science):
            what = {"→": "an arrow (a limit, a mapping or a reaction outside a chemistry reading)", "⇌": "an equilibrium arrow outside a chemistry reading",
                    "∝": "a proportionality", "⇔": "an equivalence between relations"}[op]
            self._undecided("ST-UNDEC-001", what, base, item)
            return
        if any(isinstance(n, Ratio) for n in (lnode, rnode)) and not all(isinstance(n, Ratio) for n in (lnode, rnode)):
            other = rnode if isinstance(lnode, Ratio) else lnode
            if self._cls(other) in ("value", "closed"):
                # STEM repair 5 (D31: what the branch reads and cannot check, it names): a ratio set against a number ('The ratio of the
                # resistances is 4.0 : 6.0 = 0.67') had neither a check nor an ST code
                self._undecided("ST-UNDEC-001", "a ratio set against a number", base, item)
                return
            self.add(kind="link", outcome="context", reason="a ratio set against a non-ratio", **base)
            return
        lc, rc = self._cls(lnode), self._cls(rnode)
        if pos == 0 and lc == "value" and rc == "value" and (op in _EQUALITY or op in _ORDER):
            word = self._cut_left(item, left)
            if word and not _same_quantity(lnode, rnode):
                # '17 is divided by 5 = 2' read as '5 = 2': the left side is written partly in words (rule fragment, STEM repair 2)
                self._undecided("ST-PARSE-001", f"the left side of '{render(lnode)[:60]} {op} {render(rnode)[:60]}' continues the words before it "
                                                f"('… {word}'): the relation is written partly in words, outside the grammar", base, item)
                return
        if op in _ORDER:
            if "bound" in (lc, rc) and lc != "symbolic" and rc != "symbolic" and _CONDITIONAL_RE.match(item.statement_text):
                # 'For 2 < t ≤ 3, 2 − t is negative, so v < 0.': the bound of a variable, or a property under it, never a
                # claim about the values the answer stated for the symbol elsewhere (t = 1 in part (a), v = 0 at rest)
                self.add(kind="link", outcome="context", reason="an order relation of a sentence stated under a condition on a variable: a bound of "
                                                                "the variable or a property under it, not a claim about the symbol's stated values", **base)
                return
            if lc in ("value", "closed", "bound") and rc in ("value", "closed", "bound"):
                self._dimension_check(base, item, lnode, rnode)
                self.add(kind="cmp", outcome="check", **base)
            elif self.profile.is_mathematics and _has_step_word(item.gap_before) and (
                    sum(1 for o in full_ops if o in _ORDER) >= 2 or any(isinstance(n, Abs) for n in walk(lnode)) or any(isinstance(n, Abs) for n in walk(rnode))):
                # stem-soundness-12 (round 7): a chained inequality ('so −3 < x − 1 < 3, giving −2 < x < 5') or an inequality of an absolute
                # value that a step word says follows is a step the encodings do not read: named, never silent
                self._undecided("ST-UNDEC-001", "a step to a chained inequality or an inequality of an absolute value, outside the encodings", base, item)
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
                if pos == 0 and isinstance(head, Sym) and self._solved is not None and self._solved.name == head.name:
                    # rule solved-law (STEM repair 7): 'ε = I(R + r)' then 'I = 12 V / 2.9 Ω': the line evaluates the law before it solved
                    # for I, exactly as it would evaluate 'I = ε/(R + r)' stated there
                    f = self._solved
                if f is not None and item.source == "given" and _value_with_uncertainty(rnode):
                    # STEM repair 4: 'Given: ε = 12 ± 0.1 V.' after the part's 'ε = I(R + r)' restates data, a value with its
                    # uncertainty: a Given value (set against the request), never the formula evaluated at it (which left the Given
                    # with neither its stem_given check nor an ST-UNDEC-003)
                    f = None
                pairs = align(f.expr, rnode) if f is not None else None
                if f is not None and pairs:
                    self._substitution(base, item, f.expr, rnode, pairs, formula=f)
                    return
                if f is not None and self._evaluated_formula(base, item, f, rnode):
                    return
                if f is not None:
                    # rule law-values (STEM repair 8): the law at the values the line puts in, against the value it states
                    self._law_values(base, item, f, rnode, full_operands, full_ops)
                self._value_notes(base, rnode)
                self.add(kind="binding", outcome="binding", reason="a symbol defined as a written expression", **base)
                return
            if isinstance(head, Apply):
                self.add(kind="formula", outcome="formula", reason=f"a definition of the function {head.name}", **base)
                return
            self.add(kind="formula", outcome="formula", reason="a law or definition (its truth is out of scope)", **base)
            return
        if op == "=" and lc == "value" and (rc == "value" or self._hex_written(item, right)) and self._worded_base(base, item, lnode, rnode, right):
            return  # STEM repair 12 (rule prose-base): '1000 = 3E8 in hexadecimal.', '1000 = 1111101000 in binary.', '255 = FF in hexadecimal.'
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
            rounding = self._result_rounding(item, right, rnode) if pos == len(full_ops) - 1 and rc == "value" else None
            if rounding is not None:
                self.add(kind="eq", outcome="check", rounding=rounding[0], rounding_phrase=rounding[1], **base)
            else:
                self.add(kind="eq", outcome="check", **base)
            # argument diagnostics: the ST-UNIT-003 companion of the written arithmetic (section 3.4)
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
                return  # argument diagnostics: ST-STEP-003, a rewrite inside a chain that is no identity
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
                     identity=tuple(sorted(_syms(lnode))),
                     reason="a factorisation or expansion stated inside one chain (the two sides are the same polynomial)", **base)
            return
        if pos == 0 and len(full_ops) == 1 and op in _EQUALITY and self._stated_identity(item, lnode, rnode):
            # stem-soundness-12 (round 7): a factorisation or expansion the words state ('Factorising, x² + 5x + 6 = (x + 2)(x + 4).',
            # 'Expand (a + b)²': '(a + b)² = a² + b²') is an identity of polynomials, checked for every value of its variables from the
            # trivially true premise; it had been context, so a wrong factorisation was named nowhere
            names = tuple(sorted(_syms(lnode) | _syms(rnode)))
            self.add(kind="alg", outcome="check", premise_left=left, premise_op="=", premise_right=left, premise_ids=sids, explicit=True,
                     identity=names, reason="a factorisation or expansion the words state (the two sides are the same polynomial)", **base)
            return
        self.add(kind="stated", outcome="context", reason="a relation stated without a preceding relation to derive it from", **base)

    def _stated_identity(self, item: MathItem, lnode: Node, rnode: Node) -> bool:
        """Both sides are polynomials in the same letters (at most three) and the statement, or the request, names a factorisation, an
        expansion or a simplification (stem-soundness-12)."""
        if not self.profile.is_mathematics:
            return False
        words = item.context() + " " + self._request_lower
        if not any(w in words for w in _IDENTITY_WORDS):
            return False
        names = _syms(lnode) | _syms(rnode)
        if not names or len(names) > 3 or not _syms(lnode) or not _syms(rnode):
            return False
        for side in (lnode, rnode):
            for n in walk(side):
                if isinstance(n, (Func, RealPower, Root, Apply, Abs, PlusMinus, Unsupported, Percent, Quantity, WithUnit, Degrees, Ratio)):
                    return False
                if isinstance(n, Sym) and n.kind not in ("symbol",):
                    return False
                if isinstance(n, BinOp) and n.op == "/" and _syms(n.right):
                    return False
                if isinstance(n, Pow) and (n.exp < 0 or n.exp > 4):
                    return False
        return max(max(_degree(lnode, x), _degree(rnode, x)) for x in names) >= 1 and shape_key(lnode) != shape_key(rnode)

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
            if integral.lo is not None:
                continue  # a definite integral is a number, never an antiderivative (rule definite-integral, STEM repair 10)
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
                     identity=(x,),
                     reason=f"an antiderivative: the derivative of the stated antiderivative (formed by the STEM pack by the power rule, not by the engine) "
                            f"against the integrand, for every value of {x} (rule antiderivative)", **b)
            return True
        return False

    def _function_of(self, name: str, x: str, before: int) -> Optional[tuple[Node, str, str]]:
        """Rule ``derivative`` (STEM repair 11): the expression in ``x`` of the function ``name``: the answer's own, stated before offset
        ``before`` (a formula of the letter in that one variable, 'v = 3t(2 − t)', or a definition 'v(t) = 6t − 3t²', 'f(x) = x³'), else the
        request's ('v(t) = 6t - 3t^2'): ``(expression, 'answer' or 'request', statement)``, else None."""
        for f in reversed(self.scope.formulas.get(name, ())):
            if f.source in ("derivative", "request") or f.start >= before:
                continue
            if f.params:
                if len(f.params) != 1 or _syms(f.expr) - {f.params[0]}:
                    continue
                expr = f.expr if f.params[0] == x else replace_symbol(f.expr, f.params[0], Sym(x))
            else:
                if _syms(f.expr) - {x}:
                    continue
                expr = f.expr
            if expr is not None:
                return expr, "answer", f.statement_id
        for n, param, expr, off, sid in reversed(self._answer_functions()):
            if n == name and off < before:
                e = expr if param == x else replace_symbol(expr, param, Sym(x))
                if e is not None:
                    return e, "answer", sid
        rf = self._request_functions().get(name) if self.request.text.strip() else None
        if rf is not None:
            param, expr, _a, _b = rf
            e = expr if param == x else replace_symbol(expr, param, Sym(x))
            if e is not None:
                return e, "request", ""
        return None

    def _derivative(self, base: dict, lnode: Node, rnode: Node) -> bool:
        """Rule ``derivative`` (STEM repair 11): a derivative of a polynomial in one variable set equal to a polynomial in it: the derivative
        is formed by the STEM pack by the power rule (``calculus``, as rule antiderivative forms the derivative of a stated antiderivative,
        not by the engine) and set against the stated expression for every value of the variable (an ``alg`` check from the trivially true
        premise, so it holds iff the two polynomials agree). What is differentiated: the bracketed expression of the operator form ('d/dt
        (3t²) = 6t'); the function a letter stands for ('dv/dt = 6 − 6t', 'd²s/dt² = …', 'f′(x) = 3x² − 2', 'v′(t) = …'), the answer's own
        before the line or, failing that, the request's (then at warning severity: that the letter is the request's function is a reading);
        a derivative evaluated at a number ('f′(2) = 12') with no formula of its own stated, at that number (an ``eq`` check). Before, every
        derivative was ST-UNDEC-001 whatever its value, so a wrong derivative ('d/dt (3t²) = 3t', 'a = dv/dt = 6 − 3t') was named only as
        unchecked. Anything that is no polynomial in the one variable stays outside the encodings (False: nothing planned)."""
        for der, stated, d_op, s_op in ((lnode, rnode, base["left"], base["right"]), (rnode, lnode, base["right"], base["left"])):
            if not (isinstance(der, Unsupported) and der.reason == "a derivative") or der.arg is None:
                continue
            if unsupported_reasons(stated) or any(isinstance(n, (Quantity, WithUnit, Apply, Func, Root, PlusMinus)) for n in walk(stated)):
                return False
            at: Optional[Node] = None
            if der.var:
                x, order = der.var, max(1, der.order)
                if isinstance(der.arg, Sym):
                    found = self._function_of(der.arg.name, x, base["start"])
                    if found is None:
                        return False
                    expr, source, fsid = found
                    what = f"the {'request' if source == 'request' else 'answer'}'s {der.arg.name} = {render(expr)[:50]}"
                else:
                    expr, source, fsid = der.arg, "written", ""
                    what = f"the written {render(expr)[:50]}"
            elif der.name:
                fname = der.name.rstrip("'")
                order = len(der.name) - len(fname)
                if order < 1:
                    return False
                if isinstance(der.arg, Sym) and der.arg.kind == "symbol":
                    x = der.arg.name
                elif is_closed(der.arg) and not unsupported_reasons(der.arg):
                    at = der.arg
                    rf = self._request_functions().get(fname) if self.request.text.strip() else None
                    own = [f for f in self.scope.formulas.get(fname, ()) if f.params and len(f.params) == 1 and f.start < base["start"]]
                    x = own[-1].params[0] if own else (rf[0] if rf is not None else "")
                    if not x:
                        return False
                else:
                    return False
                found = self._function_of(fname, x, base["start"])
                if found is None:
                    return False
                expr, source, fsid = found
                what = f"the {'request' if source == 'request' else 'answer'}'s {fname}({x}) = {render(expr)[:50]}"
            else:
                return False
            p = polynomial(expr, x)
            if p is None or p[1]:
                return False
            coeffs = p[0]
            for _ in range(order):
                coeffs = derivative(coeffs)
            dnode = polynomial_node(coeffs, x, d_op.start, d_op.end)
            tag = " (rule derivative, the request's function)" if source == "request" else " (rule derivative)"
            sids = tuple(dict.fromkeys(base["statement_ids"] + ((fsid,) if fsid else ())))
            nth = {1: "", 2: "second ", 3: "third "}.get(order, f"order-{order} ")
            if at is not None:
                value = replace_symbol(dnode, x, at)
                if value is None or not is_closed(stated):
                    return False
                b = dict(base)
                b["left"], b["right"], b["statement_ids"] = Operand((value,), d_op.start, d_op.end), Operand((stated,), s_op.start, s_op.end), sids
                self.add(kind="eq", outcome="check", title="the derivative formed by the power rule at the written argument, against the value stated",
                         reason=f"the {nth}derivative of {what} (formed by the STEM pack by the power rule, not by the engine) at {x} = "
                                f"{render(at)[:20]}, against the stated value{tag}", **b)
                return True
            q = polynomial(stated, x)
            if q is None or q[1]:
                return False
            if not any(k > 0 for k in q[0]) and any(k > 0 for k, c in coeffs.items() if c):
                # 'f′(x) = 0' at a stationary point, 'dy/dx = 3': the derivative set equal to a number where it is no constant states an
                # equation in the variable to solve, never an identity (it had failed as one)
                return False
            dop = Operand((dnode,), d_op.start, d_op.end)
            b = dict(base)
            b["left"], b["right"], b["statement_ids"] = dop, Operand((stated,), s_op.start, s_op.end), sids
            self.add(kind="alg", outcome="check", premise_left=dop, premise_op="=", premise_right=dop, premise_ids=base["statement_ids"], explicit=True,
                     identity=(x,), title="the derivative formed by the power rule, against the derivative stated",
                     reason=f"a derivative: the {nth}derivative of {what} (formed by the STEM pack by the power rule, not by the engine) against "
                            f"the stated expression, for every value of {x}{tag}", **b)
            return True
        return False

    def _result_rounding(self, item: MathItem, right: Operand, rnode: Node) -> Optional[tuple[Fraction, str]]:
        """Rule ``result-rounding`` (STEM repair 11): the rounding a line states for its own result, the value that closes its chain, right
        after it ('(92 − 61) ÷ 92 × 100 = 34% to 2 s.f.', '= 330 (to 2 s.f.)', '= 34% (to the nearest whole number)', '= 16.5 W (3 s.f.)') or
        in its clause before it ('To 2 s.f., 1000 ÷ 3 = 330'), read as rule rounding-cue reads a restated value's: ``(half-width in the
        value's written unit, phrase)``, else None. The arithmetic check then takes that half-width for the stated value (never less than
        half a unit in its last written digit), and rule rounded-digits sets the place the value is written to against the place the rounding
        names. Before, a rounding written for the chain's own result was read by no rule: a whole number rounded at a stated significant
        figure ('= 330 to 2 s.f.') failed in exact mode, and a value not written to the rounding it states ('= 33.7% to 2 s.f.') passed."""
        v = value_of(rnode) if is_value(rnode) else None
        if v is None or v[1] is None or v[1].vulgar or v[1].based or v[1].base != 10:
            return None
        off = item.statement_start
        after = re.sub(r"^[ \t]*\$+", "", item.statement_text[max(0, right.end - off):][:160])
        before = item.statement_text[:max(0, right.start - off)]
        pv = ProseValue(item.statement_id, item.statement_index, item.part, rnode, right.start, right.end, before, after)
        cue = _rounding_cue("", after, v[0], self._unit_words(pv, v))
        if cue is None and _rounding_opens_clause(before):
            # a rounding before the chain is its result's only when it opens the chain's clause ('To 2 s.f., 1000 ÷ 3 = 330'): one that
            # closes an earlier value's restatement ('so 5902 euros to the nearest euro, and $4000(1.036)^{12} = 6114.73$') is that value's
            cue = _rounding_cue(before, "", v[0], self._unit_words(pv, v))
        return cue

    def _ellipsis_restatement(self, base: dict, item: MathItem, lnode: Node, rnode: Node, right: Operand) -> bool:
        """Rule ``ellipsis-rounding`` (STEM repair 10): a link that restates a value written with an ellipsis (its digits cut: '4787.58…',
        as the grammar reads it, the number beside the ellipsis marker) as a value, with or without a rounding its statement states after
        it ('$= 4787.58\\ldots$ (A1)' then '$= 4788$ euros, to the nearest euro'), is the restatement of the cut value: a ``res`` check of
        the restated value against the written digits, with the stated rounding's half-width (or the restated value's own, R8) and a whole
        unit in the cut value's last written digit added to the band (the digits cut can make it up to a unit more, and a rounded reading
        half a unit either way). Before, the link was named ST-UNDEC-001 ('an ellipsis') whatever the rounding, so '= 4787 euros, to the
        nearest euro' after '4787.58…' passed. The cut value's own link (a power beyond 12 before it) stays outside the encodings."""
        w = _ellipsis_value(lnode)
        if w is None or not is_value(rnode):
            return False
        sv = value_of(rnode)
        if sv is None or sv[1] is None or (sv[2] is not None) or sv[3]:
            return False  # a restated value with a unit or a per cent: not read (the cut value is a bare number)
        off = item.statement_start
        after = re.sub(r"^[ \t]*\$+", "", item.statement_text[max(0, right.end - off):][:160])
        before = item.statement_text[:max(0, right.start - off)]
        pv = ProseValue(item.statement_id, item.statement_index, item.part, rnode, right.start, right.end, before, after)
        rounding = _rounding_cue("", after, sv[0], self._unit_words(pv, sv))
        self.add(kind="res", outcome="check", rounding=rounding[0] if rounding else None, rounding_phrase=rounding[1] if rounding else "",
                 title="the value restated from the cut value before it",
                 reason=f"a value restated{' ' + repr(rounding[1]) if rounding else ''} from a value written with an ellipsis ({w.number.text}…): "
                        f"the restated value against the written digits, a whole unit in their last digit added to the band (rule ellipsis-rounding)",
                 **dict(base, left=Operand((w,), getattr(w, "start", base["left"].start), getattr(w, "end", base["left"].end))))
        return True

    def _ellipsis_cut(self, base: dict, lnode: Node, rnode: Node) -> bool:
        """Rule ``ellipsis-rounding`` (STEM repair 10): a closed expression set equal to a value written with its digits cut ('8/3 = 2.66…',
        '\\frac{8}{3} = 2.66\\ldots') states the leading digits of the value it computes: an ``eq`` check of the computed value against the
        cut value, within the band the cut digits and a rounded reading allow ([w − u/2, w + u], u a unit in the last written digit; τ by
        rule operand-precision). Before, a plain '…' ended the run, so '2.66' was read as a rounded value and the correct line failed, and
        with '\\ldots' the link was ST-UNDEC-001 whatever its value. The cut value may stand on either side ('0.333… = 1/3', '2.66… = 8/3':
        the closed expression is the computed side), and the link may be approximate ('8/3 ≈ 2.66…', 'A = 4787.58… ≈ 4788': τ = 1/20, R2)."""
        w, closed, side = _ellipsis_value(rnode), lnode, "right"
        if w is None:
            w, closed, side = _ellipsis_value(lnode), rnode, "left"
        if w is None or not is_closed(closed) or unsupported_reasons(closed):
            return False
        bb = dict(base)
        if side == "left":
            bb["left"] = base["right"]  # the closed expression is the computed side, the cut value the stated one
        bb["right"] = Operand((w,), getattr(w, "start", base[side].start), getattr(w, "end", base[side].end))
        self.add(kind="eq", outcome="check", title="the computed value against the value written with its digits cut",
                 reason=f"the computed value against {w.number.text}…, a value written with its digits cut: from half a unit below to a whole unit "
                        f"above its last written digit (rule ellipsis-rounding)", **bb)
        return True

    def _definite(self, base: dict, lnode: Node, rnode: Node) -> bool:
        """Rule ``definite-integral`` (STEM repair 10): a definite integral with whole-number limits and an evaluation bracket, read as the
        antiderivative check reads an indefinite integral:

        * a definite integral of a polynomial against the evaluation bracket of the antiderivative the answer states, between the same
          limits (``∫₀¹ 6t dt = [3t²]₀¹``): the derivative of the stated antiderivative (formed by the STEM pack by the power rule) against
          the integrand, for every value of the variable (an ``alg`` check, as for ``∫6t dt = 3t²``);
        * an evaluation bracket of a polynomial in one variable against a closed expression (``[3t²]₀¹ = 6``, ``[3t² − t³]₀² = (12 − 8) −
          0``): the bracket's antiderivative at the upper limit minus at the lower one, formed by substitution, against it (an ``eq`` check);
        * a definite integral of a polynomial against a closed expression (``∫₀¹ 6t dt = 6``): the antiderivative the STEM pack forms by the
          power rule taken the other way, evaluated between the limits, against it (an ``eq`` check).

        Before, each was named ST-UNDEC-001 ('an integral', 'the evaluation of an antiderivative between limits') whatever its value, so a
        wrong value and the right one gave the same receipt. An integrand or a bracket that is no polynomial in one variable (a symbol
        standing for a function, ``∫₀² v dt``), other limits on the two sides, and limits that are not whole numbers stay outside the
        encodings (False: nothing planned). A limit may carry a minus sign (``∫₋₁¹ x dx = 0``, ``∫_{-1}^{1} x dx = 0``), and the limits may
        be written after an underscore and a caret in plain text (``∫_0^1 x dx``): before, the span reader ended at such a limit, so the
        relation had no check and no ST code at all."""
        def definite(n: Node) -> bool:
            return isinstance(n, Unsupported) and n.reason == "an integral" and n.lo is not None and n.hi is not None and n.arg is not None \
                and n.name.startswith("∫")

        def bracket(n: Node) -> bool:
            return isinstance(n, Unsupported) and n.reason == "the evaluation of an antiderivative between limits" and n.lo is not None \
                and n.hi is not None and n.arg is not None

        def closed(n: Node) -> bool:
            return is_closed(n) and not unsupported_reasons(n)

        def between(f: Node, x: str, lo: Node, hi: Node) -> Optional[Node]:
            up, down = replace_symbol(f, x, hi), replace_symbol(f, x, lo)
            if up is None or down is None:
                return None
            return BinOp("-", up, down, getattr(f, "start", 0), getattr(f, "end", 0), "−")

        for a, b, a_op, b_op in ((lnode, rnode, base["left"], base["right"]), (rnode, lnode, base["right"], base["left"])):
            if definite(a) and bracket(b):
                if _limit_value(a.lo) != _limit_value(b.lo) or _limit_value(a.hi) != _limit_value(b.hi):  # type: ignore[union-attr,arg-type]
                    return False
                x = a.name[1:]  # type: ignore[union-attr]
                p, q = polynomial(a.arg, x), polynomial(b.arg, x)  # type: ignore[arg-type]
                if p is None or q is None or p[1] or q[1]:
                    return False
                start, end = getattr(b.arg, "start", 0), getattr(b.arg, "end", 0)
                dop = Operand((polynomial_node(derivative(q[0]), x, start, end),), start, end)
                bb = dict(base)
                bb["left"] = dop
                # the integrand at the integral's span: its limits stand right before it ('\\int_0^2 3x^2\\,dx'), never digits of a longer numeral
                bb["right"] = Operand((a.arg,), a_op.start, a_op.end)  # type: ignore[arg-type]
                self.add(kind="alg", outcome="check", premise_left=dop, premise_op="=", premise_right=dop, premise_ids=base["statement_ids"], explicit=True,
                         identity=(x,),
                         reason=f"a definite integral against the evaluation of the antiderivative the answer states, between the same limits: the "
                                f"derivative of the stated antiderivative (formed by the STEM pack by the power rule, not by the engine) against the "
                                f"integrand, for every value of {x} (rule definite-integral)", **bb)
                return True
            if bracket(a) and closed(b):
                syms = [n for n in symbols(a.arg) if not n.endswith("()")]  # type: ignore[arg-type]
                if len(syms) != 1:
                    return False
                q = polynomial(a.arg, syms[0])  # type: ignore[arg-type]
                if q is None or q[1]:
                    return False
                ev = between(a.arg, syms[0], a.lo, a.hi)  # type: ignore[arg-type]
                if ev is None:
                    return False
                bb = dict(base)
                bb["left"], bb["right"] = Operand((ev,), a_op.start, a_op.end), Operand((b,), b_op.start, b_op.end)  # computed, then stated
                self.add(kind="eq", outcome="check", title="the antiderivative evaluated between its limits",
                         reason=f"the evaluation bracket: its antiderivative at {_limit_text(a.hi)} minus at {_limit_text(a.lo)}, formed by substitution, "  # type: ignore[union-attr,arg-type]
                                f"against the written value (rule definite-integral)", **bb)
                return True
            if definite(a) and closed(b):
                x = a.name[1:]  # type: ignore[union-attr]
                p = polynomial(a.arg, x)  # type: ignore[arg-type]
                if p is None or p[1]:
                    return False
                anti = antiderivative(p[0])
                if anti is None:
                    return False
                ev = between(polynomial_node(anti, x, a.start, a.end), x, a.lo, a.hi)  # type: ignore[arg-type,union-attr]
                if ev is None:
                    return False
                bb = dict(base)
                bb["left"], bb["right"] = Operand((ev,), a_op.start, a_op.end), Operand((b,), b_op.start, b_op.end)  # computed, then stated
                self.add(kind="eq", outcome="check", title="the definite integral of a polynomial",
                         reason=f"the definite integral from {_limit_text(a.lo)} to {_limit_text(a.hi)}: the antiderivative the STEM pack forms by the "  # type: ignore[union-attr,arg-type]
                                f"power rule taken the other way (not the engine), evaluated between the limits, against the written value (rule "
                                f"definite-integral)", **bb)
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
        if self._another_relation(names, rnode):
            return False
        b = dict(base)
        b["left"] = Operand((f.expr,), base["start"], base["end"])
        b["right"] = Operand((rnode,), base["right"].start, base["right"].end)
        b["statement_ids"] = tuple(dict.fromkeys((f.statement_id,) + base["statement_ids"]))
        self._dimension_check(base, item, f.expr, rnode)
        self.add(kind="sub", outcome="check", evaluate=True, formula=f,
                 reason=(f"the law stated in {f.statement_id} solved for '{f.name}' (rule solved-law)" if f.source == "solved" else
                         f"the formula of '{f.name}' stated in {f.statement_id}")
                 + f" under the stated values of {', '.join(names)}, against the written expression", **b)
        self._unit_companion(len(self.relations) - 1, f.expr, rnode)  # argument diagnostics: ST-UNIT-003 (section 3.4)
        return True

    def _another_relation(self, names: list[str], rnode: Node) -> bool:
        """STEM repair 8 (beside rule law-values): the line takes a value whose dimension is that of no symbol of the formula, nor a power of
        one, every symbol's dimension being known from its stated values ('P = 9.93 V × 1.655 A = 16.4 W' right after 'P = V²/R': a current,
        where the formula has a potential difference and a resistance): the line evaluates another relation (P = VI), so it is no evaluation
        of the formula at stated values (it had been set against V²/R under the stated values and failed, INT-SUBJ-001 on correct working).
        False when a symbol's dimension is unknown."""
        dims = [dimension_of(Sym(n), self.scope) for n in names]
        if not dims or any(d is None for d in dims):
            return False
        for q in walk(rnode):
            if not isinstance(q, (Quantity, WithUnit)) or q.unit.unknown or q.unit.dim is None or q.unit.dim.is_dimensionless:
                continue
            if not any(_power_of(q.unit.dim, d) for d in dims if d is not None):
                return True
        return False

    def _law_values(self, base: dict, item: MathItem, f: Formula, rnode: Node, full_operands: list, full_ops: list, *, same_line: bool = False) -> bool:
        """Rule ``law-values`` (STEM repair 8): a line that evaluates a symbol right after its part states a law for it ('V = ε + Ir' then
        'V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V'), whose written expression neither repeats the law's shape (no substitution pairs a symbol
        with each value) nor can be checked as the law under its symbols' stated values (a symbol with no stated value: ε): the line's
        values with units are paired with the law's symbols, one distinct value for each symbol and every such value used, so that each
        symbol whose dimension is known (from its stated values, or from the law itself: :func:`_law_dims`) gets a value of that dimension
        and the law at those values has the dimension of the value the line states (several such pairings are read only when they give one
        value: the current and the resistance of 'Ir' either way), and the law at those values is set against the value the line states,
        under the tolerance rule (an ``eq`` check naming the law's statement and the line's, at warning severity: which value stands for
        which symbol is a reading).
        A law the line does not follow fails it: 'V = ε + Ir' gives 14.07 V where the line states 9.9 V; the law the line evaluates holds
        ('V = ε − Ir': 9.93 V). Before, such a line was only a symbol defined as a written expression, its arithmetic checked: the law it
        contradicts was named by nothing. Nothing is planned when the law stands in another part, has a parameter, a ± or notation outside
        the encodings or more than five symbols, when a symbol is dimensionless, when the line's values with units do not stand one for
        each symbol, when no pairing (or more than one value) agrees with the dimensions, or when the chain states no value with a unit."""
        if self.request_mode or (base.get("position", 0) != 0 and not same_line) or not f.statement_id \
                or self.part_of.get(f.statement_id, "") != item.part or f.params or unsupported_reasons(f.expr) \
                or any(isinstance(n, (PlusMinus, Apply)) for n in walk(f.expr)):
            return False
        if not full_ops or any(o not in ("=", "≈") for o in full_ops) or len(full_operands) < 3:
            return False
        stated_op = full_operands[-1][0]
        if is_value(rnode) or rnode is _first(stated_op):
            return False  # the line states the value itself ('F = 2 × k = 6 N'): no values put in for the law's symbols
        stated = _stated_value(_first(stated_op))
        sv = value_of(stated) if stated is not None and is_value(stated) else None
        if sv is None or sv[1] is None or sv[2] is None or sv[2].unknown or sv[2].dim is None:
            return False
        names = [n for n in symbols(f.expr) if not n.endswith("()")]
        if not names:
            return False
        known = {n: d for n in names for d in (dimension_of(Sym(n), self.scope),) if d is not None}
        inferred = _law_dims(f.expr, sv[2].dim, known)
        if any(d.is_dimensionless for d in inferred.values()):
            return False
        distinct: dict[tuple[Fraction, str], Node] = {}
        for n in walk(rnode):
            if isinstance(n, Quantity) and not n.unit.unknown and n.unit.dim is not None:
                distinct.setdefault((n.number.value, " ".join(n.unit.text.split())), n)
        if len(distinct) != len(names) or len(names) > 5:
            return False  # every value with a unit stands for one symbol of the law, each symbol for one value
        consistent: list[tuple[dict[str, Node], Node]] = []
        for perm in _orders(list(distinct.values())):
            assign = dict(zip(names, perm))
            if any(name in inferred and not node.unit.dim.same_physical(inferred[name]) for name, node in assign.items()):  # type: ignore[union-attr]
                continue
            evaluated: Optional[Node] = f.expr
            for name, node in assign.items():
                evaluated = replace_symbol(evaluated, name, node) if evaluated is not None else None
            if evaluated is None or not is_closed(evaluated) or unsupported_reasons(evaluated):
                continue
            d = dimension_of(evaluated, self.scope, coefficients=True)
            if d is None or not d.same_physical(sv[2].dim):
                continue
            consistent.append((assign, evaluated))
        if not consistent:
            return False
        if len(consistent) > 1:
            # several pairings agree with the dimensions ('I·r': the current and the resistance either way): read only when they give one value
            vals = {_exact_eval(ev) for _a, ev in consistent}
            if None in vals or len(vals) != 1:
                return False
        pairs, evaluated = consistent[0]
        sid = base["statement_ids"][-1]
        shown = ", ".join(f"{n} = {render(v)[:30]}" for n, v in pairs.items())
        b = dict(base)
        b["statement_ids"] = tuple(dict.fromkeys((f.statement_id,) + tuple(base["statement_ids"])))
        b["left"] = Operand((evaluated,), base["start"], base["end"])
        b["right"] = stated_op
        b["end"] = max(base["end"], stated_op.end)
        b["op"] = full_ops[-1]
        self.add(kind="eq", outcome="check", title=f"the law stated in {f.statement_id} at the values the line puts in",
                 reason=f"the law {f.name} = {render(f.expr)[:60]} stated in {f.statement_id}, at the values the line in {sid} puts in, each paired with "
                        f"the law's symbol by its dimension ({shown}), against the value the line states (rule law-values)", **b)
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

    def _sub_or_equation(self, base: dict, item: MathItem, sym_side: Node, num_side: Node, pos: int, head_is_lone: bool) -> None:
        """A symbolic side against a numeric side. In a chain that computes a named quantity (its
        head is a lone symbol: ``n(NaOH) = c × V = c × 0.0250 = …``) this is a substitution or an
        evaluation under the bindings. In an equation chain (``2x = 14``, ``(x − 4)(x + 2) = 0``)
        an unknown with no binding is solved for, not substituted: unless the trees align (a
        written substitution such as ``b² − 4ac = 4² − 4 × 1 × 6``), it is a stated equation."""
        if not head_is_lone and not align(sym_side, num_side) and not (isinstance(sym_side, Sym) and self.scope.is_given(sym_side.name)):
            rel = self.add(kind="stated", outcome="context", reason="an equation in an unknown (solved by the steps that follow, not substituted)", **base)
            if not self.request_mode and pos == 0 and _syms(sym_side) and self._cls(sym_side) in ("bound", "symbolic") \
                    and self._prose_head(item, base["start"]):
                # rule bound-relation (STEM repair 5): the prose names the quantity this run is the value of, so this may be no equation at
                # all ('The battery's power output is 12 V × I = 60 W.': every symbol has a stated value; 'The energy is 0.5 × k × 0.04 =
                # 1.0 J.': k has none, which is named); decided once the whole answer is read (whether its part solves it for a symbol)
                self._bound_equations.append((rel.index, item, sym_side, num_side))
            return
        self._sub_link(base, item, sym_side, num_side, pos)

    def _prose_head(self, item: MathItem, start: int) -> str:
        """Rule ``bound-relation`` (STEM repair 5): the quantity the prose names, right before a maths run, as the run's value ('The battery's
        power output is 12 V × I = 60 W.': battery power output; 'The lost volts are 0.50 Ω × I = 3.0 V.'). Empty when the run does not open
        its item at ``start``, when its clause names nothing before 'is', 'are', 'was', 'were', 'equals' or 'equal' (also 'is equal to' and
        'is given by'), or when it names an equation, an expression or a law rather than a quantity ('The equation is 2x + 3 = 7')."""
        if start > item.start + 1:
            return ""
        gap = item.gap_before
        tail = gap[-28:]
        m = _PROSE_HEAD_VERB_RE.search(tail)
        if m is None:
            return ""
        head = gap[:len(gap) - len(tail) + m.start()]
        for sep in (".", ";", ":", "\n", ",", "(", ")", "—", "–", "?", "!", "="):
            k = head.rfind(sep)
            if k >= 0:
                head = head[k + 1:]
        words = _name_words(head[-80:])
        if not words or any(w in _EQUATION_WORDS for w in words):
            return ""
        return " ".join(words)

    def _bound_relations(self) -> None:
        """Rule ``bound-relation`` (STEM repair 5): a maths run the prose gives as the value of a quantity it names ('The battery's power
        output is 12 V × I = 60 W.', 'The lost volts are 0.50 Ω × I = 3.0 V.'), whose symbolic side has only symbols with stated values,
        is read as a chain headed by that quantity ('P = 12 V × I = 60 W', 'Power output = 12 V × I = 60 W'): its symbolic side under
        the stated bindings against its numeric side, a ``sub`` check. Before, it was read as an equation in an unknown that the steps
        after it solve, so a wrong value passed with neither a check nor an ST code, while the same line written with a symbol or a word
        label before it was checked. Not when its part goes on to give one of its symbols a value after it (it is then an equation solved
        for that symbol: 'The power is 16.4 W = I² × 6.0 Ω, so I = 1.65 A'), in a statement or in its prose ('…, giving a current of 1.65
        A': a value of the symbol's dimension that matches none of its stated values), and not when one of its symbols has its stated
        values only in other parts and its numeric side is a result its part already states ('The power in it is I² × 6.0 Ω = 16.4 W.'
        after 'P = … = 16.4 W': an equation for the current in this part, which may be another quantity than part (b)'s I); both stay as
        before (no check)."""
        for idx, item, sym_side, num_side in self._bound_equations:
            rel = self.relations[idx]
            if rel.kind != "stated" or rel.outcome != "context":
                continue
            names = _syms(sym_side)
            solved = False
            for name in names:
                for b in tuple(self.scope.bindings.get(name, ())) + tuple(self.scope.substitutions.get(name, ())):
                    if b.source != "request" and b.start >= rel.end and self.part_of.get(b.statement_id, "") == rel.part:
                        solved = True
                        break
                if solved:
                    break
            if solved or self._solved_in_prose(rel, names) or self._equation_of_part_result(rel, names, num_side) \
                    or self._equation_of_asked_quantity(rel, names, self._prose_head(item, rel.start)):
                continue
            unbound = tuple(n for n in symbols(sym_side) if not self.scope.has_reading(n))
            if unbound and any(pv.statement_id in rel.statement_ids and pv.start >= rel.end for pv in self.prose_values):
                continue  # 'The energy is 0.5 × k × 0.04 = 1.0 J, so the spring constant is 50 N m⁻¹.': solved in its own statement
            if unbound and any(isinstance(n, Sym) and n.name in unbound and self.text[n.end:n.end + 1] == "(" and self._defines_function(n.name)
                               for n in walk(sym_side)):
                continue  # 'the cost of 12 items is C(12) = …' after 'C(x) = 40 + 2.5x': a function written as applied, never a symbol with no value
            base = dict(statement_ids=rel.statement_ids, start=rel.start, end=rel.end, op=rel.op, left=rel.left, right=rel.right, part=rel.part,
                        position=rel.position, approx=rel.approx)
            self._dimension_check(base, item, sym_side, num_side, index=idx)
            head = self._prose_head(item, rel.start)
            self.relations[idx] = replace(rel, kind="sub", outcome="check", evaluate=True, unbound=unbound, pairs=(), prose_head=head,
                                          reason=f"the symbolic side under the stated bindings against the numeric side: the prose gives the run as "
                                                 f"the value of the {head or 'quantity it names'}, "
                                                 + (f"and {', '.join(unbound)} has no stated value" if unbound else "and every symbol has a stated value")
                                                 + " (rule bound-relation)")

    def _defines_function(self, name: str) -> bool:
        """Rule ``bound-relation`` (STEM repair 5): the answer or the request defines ``name`` as a function, written applied to a symbol
        before '=' ('C(x) = 40 + 2.5x'): 'C(12)' is then the function applied, while 'k(0.20)²' with no such definition is k times 0.20
        squared, k a symbol with no stated value (named ST-UNDEC-002)."""
        pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"[ \t]*\([ \t]*[A-Za-z][A-Za-z0-9_]*[ \t]*\)[ \t]*=")
        return bool(pattern.search(self.text[:200_000]) or pattern.search(self.request.text[:20_000]))

    def _reused_symbols(self, names, part: str) -> list[str]:
        """Rule ``part-value`` (STEM repair 5): the symbols of ``names`` whose every stated value stands in another part than ``part`` (none
        in the request): the answer may reuse them in ``part`` for another quantity."""
        return [n for n in sorted(names) if self.scope.bindings.get(n)
                and all(b.source != "request" and self.part_of.get(b.statement_id, "") not in ("", part) for b in self.scope.bindings.get(n, ()))]

    def _equation_of_asked_quantity(self, rel: Relation, names: set[str], head: str) -> bool:
        """Rule ``bound-relation`` (STEM repair 5): the prose gives the run as the value of the quantity its part's question asks for
        (every word of the name the prose gives it is a word of that question: 'The power in the 6.0 Ω resistor is 9.93 V × I = 16.4 W.'
        in '(d) Calculate the power dissipated in the 6.0 ohm resistor'), and one of its symbols has its stated values only in other
        parts: the run is the part's answer written as an equation in that symbol, which the part may reuse for its own quantity (the
        current in the 6.0 Ω resistor, not part (b)'s current in the battery), so it is not read, as before this repair. Checked under
        part (b)'s I it had failed (INT-SUBJ-001) on correct working. A run that names another quantity than the part asks for ('The
        battery's power output is 12 V × I = 60 W.' in part (d)) is still checked."""
        if not rel.part or not head:
            return False
        question = _part_questions(self.request.text).get(rel.part, "")
        if not question or not self._reused_symbols(names, rel.part):
            return False
        asked = {_singular(w) for w in _label_words(question)}
        words = {_singular(w) for w in _label_words(head)}
        return bool(words) and words <= asked

    def _solved_in_prose(self, rel: Relation, names: set[str]) -> bool:
        """Rule ``bound-relation`` (STEM repair 5): the prose of the relation's part, after it, gives a value of the dimension of one of its
        symbols that matches none of that symbol's stated values ('So 16.4 W = I² × 6.0 Ω, giving a current of 1.65 A.'): the relation is
        an equation solved for that symbol."""
        for name in names:
            blist = tuple(self.scope.bindings.get(name, ()))
            dims = {b.unit.dim for b in blist if b.unit is not None and not b.unit.unknown and b.unit.dim is not None}
            if len(dims) != 1:
                continue
            dim = next(iter(dims))
            for pv in self.prose_values:
                if pv.start < rel.end or (rel.part and pv.part != rel.part) or (not rel.part and pv.statement_id not in rel.statement_ids):
                    continue
                v = value_of(pv.node)
                if v is None or v[1] is None or v[2] is None or v[2].unknown or v[2].dim is None or not v[2].dim.same_physical(dim):
                    continue
                here = Binding(name, v[0], v[1], v[2], "statement", pv.statement_id, wrapper=v[3])
                if not any(b.same_as(here) for b in blist):
                    return True
        return False

    def _equation_of_part_result(self, rel: Relation, names: set[str], num_side: Node) -> bool:
        """Rule ``bound-relation`` (STEM repair 5): one of the relation's symbols has its stated values only in other parts, and its numeric
        side is a value its part already states, before it, as a result of that dimension ('The power in it is I² × 6.0 Ω = 16.4 W.' after
        'P = … = 16.4 W' in part (d), I being bound only in part (b)): the line is an equation in that symbol about the part's own result
        (the symbol may stand for another quantity in this part, rule part-value), not a claim under the other part's value."""
        if not rel.part or not is_value(num_side):
            return False
        reused = [n for n in names if self.scope.bindings.get(n)
                  and all(b.source != "request" and self.part_of.get(b.statement_id, "") not in ("", rel.part) for b in self.scope.bindings.get(n, ()))]
        if not reused:
            return False
        v = value_of(num_side)
        if v is None or v[1] is None or v[2] is None or v[2].unknown or v[2].dim is None:
            return False
        here = Binding("", v[0], v[1], v[2], "statement", "", wrapper=v[3])
        return any(b.same_as(here) for b in self._part_results(rel.part, rel.start, set(rel.statement_ids), v[2].dim, results_only=True))

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
        self._unit_companion(len(self.relations) - 1, sym_side, num_side)  # argument diagnostics: ST-UNIT-003 (section 3.4)
        if remaining and self._chain_head is not None and self._chain_ctx is not None and not self.request_mode:
            # rule law-values (STEM repair 8): the chain states a law and evaluates it in one line ('V = ε + Ir = 12 V − (4.14 A × 0.50 Ω) =
            # 9.9 V'), a symbol of the law with no stated value: the law at the values the line puts in, against the value it states
            sid = base["statement_ids"][0]
            self._law_values(base, item, Formula(self._chain_head.name, sym_side, sid, "law"), num_side, *self._chain_ctx, same_line=True)

    def _given_in_another_part(self, name: str, node: Node, part: str) -> str:
        """How the answer may reuse the symbol ``name`` in this part for a quantity the request gives, when every binding of the
        symbol stands in another part and the value substituted here is a value the request states with the same dimension
        (``R = 2.4 Ω`` in part (a), then ``P = (9.93 V)² / 6.0 Ω`` in part (d) for "the 6.0 ohm resistor" of its question):

        * ``"read"``: the value is read for the symbol in this part, not checked against the other part's bindings: the part's
          question states it, or states no value of its dimension (nothing tells which of the request's values the part uses), or
          the part's working states it before the substitution ('With only the 4.0 Ω resistor, …');
        * ``"reading"`` (rule ``part-given``, STEM repair 6): the part's question states values of its dimension and this is none of
          them, and the part's working states it nowhere before the line (``P = (9.93 V)² / 4.0 Ω`` in the part that asks for the
          power in the 6.0 ohm resistor; before, any value the request states passed, the other resistor and the internal
          resistance too, with no word): the substitution is checked at warning severity (:meth:`_substitution`);
        * ``""``: not such a reuse (a value the request does not give is checked against the bindings, as before)."""
        blist = self.scope.bindings.get(name, ())
        if not part or not blist or any(self.part_of.get(b.statement_id, "") in ("", part) for b in blist):
            return ""
        v = value_of(node)
        if v is None or v[1] is None:
            return ""
        here = Binding(name, v[0], v[1], v[2], "substitution", "", wrapper=v[3])
        dim = v[2].dim if v[2] is not None else None
        given = False
        for qnode, _a, _b in self.request.quantities[:64]:
            q = value_of(qnode)
            if q is None or q[1] is None or (q[2].dim if q[2] is not None else None) != dim:
                continue
            if here.same_as(Binding(name, q[0], q[1], q[2], "request", "request", wrapper=q[3])):
                given = True
                break
        if not given:
            return ""
        asked = self._part_question_values(part, dim)
        if not asked or any(here.same_as(b) for b in asked):
            return "read"
        start = getattr(node, "start", 0)
        if any(here.same_as(b) for b in self._part_stated_before(part, start, dim)):
            return "read"
        return "reading"

    def _part_question_values(self, part: str, dim: Optional[Dimension]) -> tuple[Binding, ...]:
        """Rule ``part-given`` (STEM repair 6): the values of the dimension ``dim`` that the request's question for ``part`` states
        ("(d) Calculate the power dissipated in the 6.0 ohm resistor.": 6.0 ohm), as request bindings; empty when the request has no
        question for the part or it states none."""
        if dim is None or not part:
            return ()
        span = _part_question_spans(self.request.text).get(part)
        if span is None:
            return ()
        out: list[Binding] = []
        for qnode, a0, b0 in self.request.quantities[:64]:
            if not (span[0] <= a0 < span[1]):
                continue
            q = value_of(qnode)
            if q is None or q[1] is None or q[2] is None or q[2].dim != dim:
                continue
            out.append(Binding(" ".join(q[2].text.split())[:40] or "the request", q[0], q[1], q[2], "request", "request", a0, b0, wrapper=q[3]))
        return tuple(out)

    def _part_stated_before(self, part: str, start: int, dim: Optional[Dimension]) -> tuple[Binding, ...]:
        """Rule ``part-given`` (STEM repair 6): the values of the dimension ``dim`` that the working of ``part`` states before ``start``:
        the values its prose states ('only the 4.0 Ω resistor remains'), the values its statements give any symbol and the final
        values of its chains."""
        out: list[Binding] = []

        def take(node: Optional[Node], sid: str, a: int, b: int) -> None:
            v = value_of(node) if node is not None and is_value(node) else None
            if v is None or v[1] is None or v[2] is None or v[2].dim != dim:
                return
            out.append(Binding("", v[0], v[1], v[2], "part", sid, a, b, wrapper=v[3]))

        for pv in self.prose_values:
            if pv.part == part and pv.end <= start:
                take(pv.node, pv.statement_id, pv.start, pv.end)
        for blist in self.scope.bindings.values():
            for b in blist:
                if b.source not in ("request", "root") and self.part_of.get(b.statement_id, "") == part and b.end <= start and b.unit is not None \
                        and b.unit.dim == dim:
                    out.append(b)
        for fv in self.final_values:
            op = fv.get("operand")
            if fv.get("part") == part and op is not None and op.end <= start:
                take(fv.get("node"), fv.get("sid", ""), op.start, op.end)
        return tuple(out)

    def _computed_in_line(self, name: str, node: Node, part: str) -> bool:
        """Rule ``part-value`` (STEM repair 5): the answer writes, for a symbol whose every stated value stands in another part, a
        computation of values with units in its place ('P = I²R = (9.93 V ÷ 6.0 Ω)² × 6.0 Ω = 16.4 W' in part (d), I stated as 4.1 A in
        part (b)): the line computes the symbol's value in this part, which may be another quantity there (the current in the 6.0 Ω
        resistor), so the computation is read for the symbol, as a value the request gives is (``_given_in_another_part``), and not set
        against the other part's values; its arithmetic is checked with the line's. A single value written there is still set against
        them."""
        blist = self.scope.bindings.get(name, ())
        if not part or not blist or is_value(node) or not is_closed(node) \
                or not all(b.source != "request" and self.part_of.get(b.statement_id, "") not in ("", part) for b in blist):
            return False
        leaves = [x for x in walk(node) if isinstance(x, (Quantity, WithUnit))]
        if len(leaves) < 2 or not isinstance(node, (BinOp, Pow, Neg)) and not any(isinstance(x, BinOp) for x in walk(node)):
            return False
        dims = {b.unit.dim for b in blist if b.unit is not None and not b.unit.unknown and b.unit.dim is not None}
        dim = dimension_of(node, self.scope, [])
        return len(dims) == 1 and dim is not None and dim.same_physical(next(iter(dims)))

    def _substitution(self, base: dict, item: MathItem, sym_side: Node, num_side: Node, pairs: list, formula: Optional[Formula] = None) -> None:
        checkable: list[tuple[str, Node]] = []
        introduced: list[tuple[str, Node]] = []
        #: rule part-given (STEM repair 6): reused symbols given a value the request states that their part names nowhere
        part_given: list[tuple[str, Node]] = []
        #: rule solved-law (STEM repair 7): a symbol with no binding but values substituted for it before the line
        prior: list[tuple[str, tuple[Binding, ...]]] = []
        for s, n in pairs:
            name = getattr(s, "name", "")
            if isinstance(s, Apply):
                name = s.name + "()"
            if not name or (isinstance(n, Sym) and n.name == name):
                continue
            if not self.scope.is_bound(name):
                earlier = tuple(b for b in self.scope.substitutions.get(name, ()) if b.end <= base["start"]) \
                    if formula is not None and formula.source == "solved" and is_closed(n) else ()
                if earlier:
                    # rule solved-law (STEM repair 7): the algebra step this evaluation replaces pinned such a symbol to the value
                    # substituted for it before ('T = 2π/ω = 2π/4.0', then 'ω = 2πf so f = 3.0/(2π)'): its value is set against those
                    # values, so the reading is never weaker than the step
                    checkable.append((name, n))
                    prior.append((name, earlier))
                    continue
                introduced.append((name, n))
                continue
            reuse = self._given_in_another_part(name, n, item.part)
            if reuse == "read" or self._computed_in_line(name, n, item.part):
                introduced.append((name, n))
            elif reuse == "reading":
                part_given.append((name, n))
            else:
                checkable.append((name, n))
        sid = base["statement_ids"][-1]
        for name, n in introduced:
            v = value_of(n)
            if v is not None and v[1] is not None:
                unit = v[2]
                if unit is None and not v[3]:
                    # argument diagnostics (ST-REF-001): a bare numeral for a symbol bound nowhere else, which the request states with an SI
                    # unit ('radius 3.0 m', 'A mass of 0.50 kg'): the substitution carries the request's unit, so the law's dimension is read
                    q = fixed_quantity(name, self.profile.key, request_text=self.request.text)
                    rq = self._request_quantity_for(n, q.dimension if q is not None else None)
                    if rq is not None and rq.unit is not None and unit_scale(rq.unit) == 1:
                        unit = rq.unit
                self.scope.add(Binding(name, v[0], v[1], unit, "substitution", sid, getattr(n, "start", 0), getattr(n, "end", 0), wrapper=v[3]))
        self._dimension_check(base, item, sym_side, num_side)
        if not checkable and not part_given:
            self.add(kind="sub", outcome="binding", pairs=tuple(introduced), formula=formula,
                     reason="values substituted into symbols the report binds nowhere else (they introduce the values)", **base)
            return
        if checkable:
            reused, head_values, head_symbol, part_stated = self._part_values(base, item, checkable, num_side)
            self.add(kind="sub", outcome="check", pairs=tuple(checkable), formula=formula, prior_readings=tuple(prior),
                     unbound=tuple(n for n, _x in introduced), reused=reused, head_values=head_values, head_symbol=head_symbol, part_stated=part_stated,
                     reason="substituted values against the stated bindings" + (_formula_words(formula) if formula else "")
                     + (f"; rule part-value for {', '.join(reused)}" if reused else ""), **base)
        if part_given:
            # rule part-given (STEM repair 6): a check of its own, at warning severity, so a reading never lowers the severity of a
            # symbol checked against its bindings in the same line
            dims = {value_of(n)[2].dim for _nm, n in part_given if value_of(n) is not None and value_of(n)[2] is not None}
            asked = tuple(b for d in dims for b in self._part_question_values(item.part, d))
            reused, head_values, head_symbol, part_stated = self._part_values(base, item, part_given, num_side)
            self.add(kind="sub", outcome="check", pairs=tuple(part_given), formula=formula,
                     unbound=tuple(n for n, _x in introduced), reused=reused, head_values=head_values, head_symbol=head_symbol, part_stated=part_stated,
                     part_given=asked,
                     reason="substituted values the request states, set against the stated bindings and the values the part's question states (rule "
                            f"part-given for {', '.join(n for n, _x in part_given)})" + (f"; rule part-value for {', '.join(reused)}" if reused else ""),
                     **base)

    def _part_values(self, base: dict, item: MathItem, checkable: list[tuple[str, Node]], num_side: Optional[Node] = None
                     ) -> tuple[tuple[str, ...], tuple[Binding, ...], str, tuple[tuple[str, tuple[Binding, ...]], ...]]:
        """Rule ``part-value`` (STEM repair 5): a substituted symbol whose every binding stands in another part may be reused in this part
        for another quantity ('I = 4.1 A', the battery's current in part (b); in part (d), 'As a check, P = I²R = (1.655 A)² × 6.0 Ω = 16.4
        W.', where I is the current in the 6.0 Ω resistor). When its substituted value matches none of its stated values, it also
        matches

        * when the line's numeric side gives a value its part has already given, before this line, to the quantity the chain computes:
          its lone head's value (P = 16.4 W in the line before), or, with no lone head or none with such a value, a result of the part
          of the numeric side's dimension ('As a check, I²R = (1.655 A)² × 6.0 Ω = 16.4 W.'): the line then re-derives the part's own
          result, which the engine decides;
        * a value its part computes before this line with the symbol's dimension, as the result of a chain ('The current in it is
          9.93 V ÷ 6.0 Ω = 1.655 A.', then 'P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W'). A value its prose only states is not one: it may
          restate the other part's quantity ('the terminal potential difference, 9.93 V' against part (c)'s V), which the substitution
          must still be set against.

        ``(reused symbols, the values of the chain's quantity in this part, its symbol or "", the values each reused symbol's part
        states)``; all empty when no reused symbol has such a value to match, so a symbol substituted with a value no statement of its
        part gives (a wrong given: 1.565 A) is still set against its bindings alone, and a value that already matches a binding changes
        nothing. Before, the reused symbol was set against the battery's current and correct working failed (INT-SUBJ-001)."""
        if not item.part:
            return (), (), "", ()
        head = self._chain_head
        sids = set(base["statement_ids"])
        start = base["start"]
        candidates: list[tuple[str, Node, Binding]] = []
        for name, node in checkable:
            blist = self.scope.bindings.get(name, ())
            if (head is not None and name == head.name) or not blist:
                continue
            if not all(b.source != "request" and self.part_of.get(b.statement_id, "") not in ("", item.part) for b in blist):
                continue
            v = value_of(node) if is_value(node) else None
            if v is None or v[1] is None:
                continue
            here = Binding(name, v[0], v[1], v[2], "substitution", "", wrapper=v[3])
            if any(b.same_as(here) for b in blist):
                continue  # its value matches a stated one: nothing to read
            candidates.append((name, node, here))
        if not candidates:
            return (), (), "", ()
        # the values the chain's quantity has in this part, before the line
        head_values: tuple[Binding, ...] = ()
        head_symbol = ""
        if head is not None:
            head_values = tuple(b for b in self.scope.bindings.get(head.name, ()) if b.source not in ("root", "request") and b.statement_id not in sids
                                and self.part_of.get(b.statement_id, "") == item.part and b.end <= start)
            if not head_values:
                # the value the answer states for the head in another part, which the line re-derives ('V = IR = 1.655 A × 6.0 Ω = 9.93 V' in
                # part (d), V = 9.9 V stated in part (c)): the line gives a stated value of the quantity it computes
                head_values = tuple(b for b in self.scope.bindings.get(head.name, ()) if b.source not in ("root", "request") and b.statement_id not in sids
                                    and b.end <= start)[-4:]
            head_symbol = head.name if head_values else ""
        if not head_values and num_side is not None:
            dim = dimension_of(num_side, self.scope, [])
            if dim is not None:
                head_values = self._part_results(item.part, start, sids, dim, results_only=True)
        part_stated: list[tuple[str, tuple[Binding, ...]]] = []
        labels: Optional[list[tuple[dict, frozenset[str]]]] = None
        for name, _node, here in candidates:
            dims = {b.unit.dim for b in self.scope.bindings.get(name, ()) if b.unit is not None and not b.unit.unknown and b.unit.dim is not None}
            if len(dims) != 1 or here.unit is None or here.unit.unknown or here.unit.dim is None or not here.unit.dim.same_physical(next(iter(dims))):
                continue
            stated = tuple(Binding(name, b.value, b.number, b.unit, "part", b.statement_id, b.start, b.end, wrapper=b.wrapper)
                           for b in self._part_results(item.part, start, frozenset(), next(iter(dims)), results_only=True))
            if labels is None:
                labels = self._labelled_values()
            stated += self._prose_named_other(name, item.part, start, next(iter(dims)), labels)
            if stated:
                part_stated.append((name, stated))
        reused = tuple(name for name, _n, _h in candidates if head_values or name in dict(part_stated))
        if not reused:
            return (), (), "", ()
        return reused, head_values, head_symbol, tuple(part_stated)

    def _prose_named_other(self, name: str, part: str, start: int, dim, labels: list[tuple[dict, frozenset[str]]]) -> tuple[Binding, ...]:
        """Rule ``part-value`` (STEM repair 5): the values the prose of ``part`` states before ``start`` with the dimension ``dim`` for a
        quantity it names with a word that the names of the symbol's stated values do not hold ('The current in the 6.0 Ω resistor is
        1.655 A.': current, resistor, where part (b)'s I = 4.1 A is named by its question, the current in the battery). The prose then
        names another quantity than the one the symbol was stated for, which the symbol may stand for in this part. Nothing when a stated
        value of the symbol has no name (the label words of its chain: a bracketed label, the statement's label, its word label, or its
        part's question for the part's last computed value), and nothing for a value named only by words of the stated quantity ('The
        current in it is 1.655 A.', 'the terminal potential difference, 9.93 V'): it may restate that quantity, which the substitution
        must still be set against. The value itself is not checked (the prose states it, Dossier guide D31)."""
        stated_words: set[str] = set()
        for b in self.scope.bindings.get(name, ()):
            words = next((w for fv, w in labels if fv["sid"] == b.statement_id and fv.get("symbol") == name), None)
            if not words:
                return ()
            stated_words |= {_singular(w) for w in words}
        out: list[Binding] = []
        for pv in self.prose_values:
            if pv.part != part or pv.end > start:
                continue
            v = value_of(pv.node)
            if v is None or v[1] is None or v[2] is None or v[2].unknown or v[2].dim is None or not v[2].dim.same_physical(dim) or v[3]:
                continue
            named = {_singular(w) for w in _label_words(_prose_value_name(pv.before))} - _PROSE_NAME_STOP
            if not named or named <= stated_words:
                continue
            out.append(Binding(name, v[0], v[1], v[2], "part", pv.statement_id, pv.start, pv.end, wrapper=v[3]))
        return tuple(out[-4:])

    def _part_results(self, part: str, start: int, sids: set, dim, *, results_only: bool, limit: int = 6) -> tuple[Binding, ...]:
        """Rule ``part-value`` (STEM repair 5): the values ``part`` states before ``start`` with the dimension ``dim``, outside the
        statements ``sids``: the final values of its chains (with ``results_only``, those of a computation), and, without it, the values
        its prose states; each once, at most ``limit`` (the latest)."""
        out: list[Binding] = []
        seen: set[tuple] = set()

        def take(node: Node, sid: str, a: int, b: int) -> None:
            v = value_of(node) if node is not None and is_value(node) else None
            if v is None or v[1] is None or v[2] is None or v[2].unknown or v[2].dim is None or not v[2].dim.same_physical(dim) or v[3]:
                return
            key = (v[0], " ".join(v[2].text.split()))
            if key in seen:
                return
            seen.add(key)
            out.append(Binding("", v[0], v[1], v[2], "part", sid, a, b, wrapper=v[3]))

        for fv in self.final_values:
            op = fv.get("operand")
            if fv.get("part") != part or fv.get("sid") in sids or op is None or op.end > start or (results_only and not fv.get("computed")):
                continue
            take(fv["node"], fv["sid"], op.start, op.end)
        if not results_only:
            for pv in self.prose_values:
                if pv.part == part and pv.end <= start and pv.statement_id not in sids:
                    take(pv.node, pv.statement_id, pv.start, pv.end)
        out.sort(key=lambda b: b.start)
        return tuple(out[-limit:])

    def _dimension_check(self, base: dict, item: MathItem, a: Node, b: Node, index: Optional[int] = None) -> None:
        """ST-DIM-001/002 and unit notes for the relation about to be added (its index is the next one), or for the relation at ``index``."""
        notes: list = []
        da = dimension_of(a, self.scope, notes)
        db = dimension_of(b, self.scope, notes)
        sids = base["statement_ids"]
        nxt = len(self.relations) if index is None else index
        for whole, d1, d2 in notes:
            self.finding("ST-DIM-002", f"a sum or difference of terms with different dimensions ({d1} and {d2}) in '{render(whole)[:160]}'", sids,
                         getattr(whole, "start", 0), getattr(whole, "end", 0), check_index=nxt)
        if da is not None and db is not None and not da.same_physical(db):
            self.finding("ST-DIM-001", f"the two sides of '{render(a)[:120]} {base.get('op', '=')} {render(b)[:120]}' have different dimensions ({da} and {db})",
                         sids, base["start"], base["end"], check_index=nxt)
        elif (da is None or db is None) and not notes and not self.request_mode:
            self._bare_dimension_links.append((dict(base), a, b, nxt))
        for node in (a, b):
            for n in walk(node):
                if isinstance(n, (Quantity, WithUnit)):
                    self._unit_notes(n.unit, sids, getattr(n, "start", 0), getattr(n, "end", 0), nxt)

    def _bare_factor_dimensions(self) -> None:
        """Rule ``bare-factor`` (:func:`bare_factor_dimensions`) on every relation whose sides' dimensions bare numbers left
        unknown, once the answer's bindings and substitutions are all known: ST-DIM-001 when no reading of its bare numbers (a
        pure factor, the symbol it was substituted for, an equal value the answer or the request states with a unit, the
        booklet constant it matches) makes the two sides agree."""
        if not self._bare_dimension_links:
            return
        from .constants import match_written  # the booklet table (a leaf module: no cycle)
        traced: dict[tuple[int, int], str] = {}
        for rel in self.relations:
            if rel.kind == "sub":
                for name, node in rel.pairs:
                    if isinstance(node, Num):
                        traced[(node.start, node.end)] = name
        stated: dict[Fraction, set[Dimension]] = {}
        for blist in self.scope.bindings.values():
            for bd in blist:
                if bd.unit is not None and not bd.unit.unknown and bd.unit.dim is not None:
                    stated.setdefault(abs(bd.value), set()).add(bd.unit.dim)
        for node, _a0, _b0 in self.request.quantities:
            v = value_of(node)
            if v is not None and v[2] is not None and not v[2].unknown and v[2].dim is not None:
                stated.setdefault(abs(v[0]), set()).add(v[2].dim)

        def readings_of(leaf: Num) -> Optional[tuple[Dimension, ...]]:
            name = traced.get((leaf.start, leaf.end))
            if name is not None:
                d = _dim(Sym(name), self.scope, None, 0)
                return None if d is None else (d,)  # substituted for a quantity: its dimension, or nothing is decided
            out = list(stated.get(abs(leaf.number.value), ()))
            if leaf.number.value != 0:
                m = match_written(leaf.number.value, leaf.number.half_width, leaf.number.sig_figs, None, unit_given=False, profile_key=self.profile.key)
                if m is not None:
                    out.append(m.constant.dim)
            return tuple(out)

        for base, a, b, idx in self._bare_dimension_links:
            leaves = _bare_leaves(a) + _bare_leaves(b)
            found = bare_factor_dimensions(a, b, self.scope, {(n.start, n.end): readings_of(n) for n in leaves})
            if found is None:
                continue
            da, db = found
            shown = ", ".join(dict.fromkeys(n.number.text for n in leaves))[:80]
            self.finding("ST-DIM-001", f"the two sides of '{render(a)[:120]} {base.get('op', '=')} {render(b)[:120]}' have different dimensions ({da} and {db}) "
                                       f"with the bare number(s) {shown} read as pure factors; no value the answer or the request states with a unit and no "
                                       f"data-booklet constant gives them a dimension that makes the sides agree (rule bare-factor)",
                         base["statement_ids"], base["start"], base["end"], check_index=idx)

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
        unknown = {n for n in _syms(first) | _syms(last) if not (n in bound_before and self._given_in(n, item.part))}
        info = {"left": operands[0][0], "op": rel_op, "right": operands[-1][0], "sid": operands[0][1], "sids": tuple(dict.fromkeys(s for _o, s in operands)),
                "unknown": unknown, "syms": _syms(first) | _syms(last), "item": item, "lone": lone, "head": head, "order": self.order.get(item.statement_id, 0),
                "connective": chain.connective, "is_formula": lone and isinstance(head, Sym) and bool(_syms(last) - {getattr(head, "name", "")}),
                "positive": positive, "operands": operands, "stepped": False}
        # roots: x = value (or a closed expression) after an equation in x
        rooted: Optional[dict] = None
        if lone and isinstance(head, Sym) and rel_op == "=" and len(operands) >= 2:
            rhs = _first(operands[1][0])
            solved = head.name not in bound_before or not self._given_in(head.name, item.part)
            if rhs is not None and is_closed(rhs) and solved:
                rooted = self._roots_candidate(item, chain, head, operands)
        prev = self.prev_rel
        if prev is None and lone and isinstance(head, Sym) and rel_op == "=" and info["unknown"]:
            # argument diagnostics (ST-STEP-001): the answer's first line states the operation it applies to the request's own equation
            # ("Solve 2x = 8." then "Subtracting 4 from both sides gives x = 8 − 4 = 4"): that equation is the line the operation is
            # applied to
            req = self._request_equation(info["unknown"])
            if req is not None and _operation_hits(item.gap_before or ""):
                l_op, r_op = req
                syms = _syms(_first(l_op)) | _syms(_first(r_op))
                prev = {"left": l_op, "op": "=", "right": r_op, "sid": "request", "sids": ("request",), "unknown": syms & info["unknown"] or syms,
                        "syms": syms, "item": item, "lone": False, "head": None, "order": info["order"] - 1, "connective": "", "is_formula": False,
                        "positive": ()}
                self._step(item, prev, info, operands, rel_op, True)
                prev = None
        if self._system_step(item, chain, info, operands, rel_op, lone, head, rooted, prev):
            prev = None
        # STEM repair 11 (rule root-statement): a root stated for the equation of an earlier line ('t = 0 or t = 2' after 'Both values lie in
        # 0 ≤ t ≤ 3.') is checked against that equation (stem-sol), never as a step from the line between them (it had been read as a step from
        # the domain statement, a false failure, once the letter is an unknown of its part)
        if rooted is not None and rooted.get("sids") != ("request",) and prev is not None and prev is not rooted and prev["op"] in _ORDER:
            prev = None
        if isinstance(first, Unsupported) and first.reason == "a derivative":
            # STEM repair 11 (rule derivative): a derivative line ('f′(x) = 3x² − 2' after 'f(x) = x³ − 2x') is checked against the derivative
            # the power rule forms, never as an algebra step from the line before (such a step was never encodable: ST-UNDEC-001 only)
            prev = None
        if prev is not None and info["unknown"] and prev["unknown"] and prev["item"].part == item.part and rel_op != "≠" and prev["op"] != "≠":
            explicit, adjacent, same_span, or_joined = self._step_cues(item, chain, prev)
            # rule premise-cue (STEM repair 2): 'From c = n/V, n = c/V', 'Since c = n/V, n = cV': a relation introduced by a premise word and
            # then, after a comma on the same line, another relation of exactly its symbols is a step from it (a rearrangement), not a list
            link_syms = _syms(first) | (_syms(_first(operands[1][0])) if len(operands) > 1 else set())  # the step is the chain's first link
            premise_cue = (prev["item"].statement_id == item.statement_id and _PREMISE_CUE_RE.search(prev["item"].gap_before[-24:]) is not None
                           and item.gap_before.strip() in (",", "") and link_syms == prev["syms"] and bool(link_syms))
            if premise_cue:
                or_joined, explicit = False, True
            pure = all(n in prev["syms"] or n in bound_before for n in info["syms"])
            new_formula = info["is_formula"] and getattr(head, "name", "") not in prev["syms"]
            shares = bool(info["unknown"] & prev["syms"])
            evaluation = (lone and isinstance(head, Sym) and prev["lone"] and getattr(prev["head"], "name", None) == head.name
                          and len(operands) > 1 and is_closed(_first(operands[1][0]) or Sym("?"))) \
                or (lone and isinstance(head, Apply) and is_closed(head.arg)) \
                or is_closed(self._function_application(head) or Sym("?")) \
                or (lone and isinstance(head, Sym) and self._solved is not None and self._solved.name == head.name) \
                or item.source == "given" or self._defined_function_value(first)
            # f(2) = …, N(15) = … evaluate a function: no step; rule solved-law (STEM repair 7): neither does the evaluation of the law before it, nor
            # a Given statement, which states data ('Given: ε = 12 V.' after 'I = ε/(R + r)' had failed as a step from the law)
            # STEM repair 5: a relation the prose introduces as the inverse's equation, its variables swapped ('y = 2x + 1', then 'Swap x
            # and y: x = 2y + 1'), is a new relation, never a step from the one before (it had failed as a step: INT-SUBJ-001)
            swapped = info["swapped"] = _SWAP_RE.search(item.gap_before[-80:]) is not None and info["syms"] == prev["syms"]
            rearranged = False
            if not evaluation and lone and isinstance(head, Sym) and len(operands) > 1 and is_closed(_first(operands[1][0]) or Sym("?")) \
                    and self._rearranges_formula_of(head.name, prev):
                # rule rearranged-formula (STEM repair 5): 'P = V²/R', 'From P = V²/R, R = V²/P.', then 'P = (9.93 V)² / 6.0 Ω': the line
                # evaluates the formula of P (its substitution is checked against it), never a step from the rearrangement
                evaluation = rearranged = True
            if shares and not evaluation and not or_joined and not new_formula and not swapped \
                    and ((explicit and (same_span or info["order"] - prev["order"] <= 1)) or (adjacent and pure)):
                info["stepped"] = True
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
            if rearranged:
                self._rearrangement_step(head.name, prev)
        if prev is not None and rooted is None and not self.request_mode:
            # STEM repair 11 (rule inequality-solution): a solved form joined by a step word to a relation linear in its one letter
            self._inequality_solution(item, chain, prev, info, operands, rel_op, lone, head)
        # rule given-function (STEM repair 9): a Given of a function's value ('Given: v(1) = 3.', 'Given: C(8) = 800 counts min⁻¹.') states
        # data, the function's value at that argument, never an equation in the letter: it is no relation a later line is a step from
        # (read as the product v·1 = 3, it had made 'v(2) = 6(2) − 3(2)²' a failing step from it, INT-SUBJ-001 on correct working), and
        # no equation whose roots follow
        if rel_op == "=" and ((item.source == "given" and self._given_function_value(first)) or self._defined_function_value(first)):
            # STEM repair 11 (rule function-value): so is a function's value stated anywhere for a function the request or the answer defines
            # ('At t = 2 the particle is at rest: v(2) = 1.' then 'So v(2) = 6(2) − 3(2)² = 0.' had been a failing step from it)
            self.prev_rel = None
            return
        # equations remembered for roots ('v = 3.0 m s⁻¹' binds v: it is no equation whose solutions follow)
        if rel_op == "=" and unknown and not (lone and isinstance(head, Sym) and is_closed(last)):
            self.equations.append(info)
        if info["is_formula"] and rel_op == "=":
            self._formula_infos[head.name] = info
        if rooted is not None and rooted.get("item") is not None and rooted.get("sids") != ("request",) and rooted["item"].part == item.part:
            # STEM repair 11 (rule root-statement): a root the answer states for an equation ('Factorising, rather than dividing by t, keeps t =
            # 0.' after '6t − 3t² = 0') is no relation the next line steps from: the equation stays it, at the root's line for adjacency, so the
            # factorised line after it ('3t(2 − t) = 0') is a step from the equation. Before, the root became the premise and the factorisation
            # followed from 't = 0' whatever its factors (a wrong factor was named nowhere)
            self.prev_rel = dict(rooted, order=info["order"], kept_by=item.statement_id)
            return
        self.prev_rel = info

    def _system_equation(self, info: dict, operands: list[tuple[Operand, str]], rel_op: str, lone: bool, head: Optional[Node]) -> bool:
        """An equation of a system of simultaneous equations: one link '=' in two or more unknowns, no solved form ('y = 10 − x')."""
        if rel_op != "=" or len(operands) != 2 or len(info["unknown"]) < 2:
            return False
        if lone and isinstance(head, Sym) and head.name not in _syms(_first(operands[1][0]) or Sym("?")):
            return False
        return not any(isinstance(n, (Unsupported, Apply)) for op, _s in operands for n in walk(_first(op) or Sym("?")))

    def _system_cue(self, item: MathItem, chain: Chain, info: dict, last: dict) -> bool:
        """What makes two equations the equations of one system rather than a line and its rearrangement: the words 'simultaneous' or
        'system' in the request or around them, 'and' joining them in one statement, or the request stating both."""
        before = (self.text[max(0, last["item"].start - 160):last["item"].start] if self.text else "").lower()
        if "simultaneous" in self._request_lower or any(w in item.context() or w in last["item"].context() or w in before for w in _SYSTEM_WORDS):
            return True
        if last["item"].statement_id == item.statement_id and (chain.connective in ("and", ",", ";")
                                                               or item.gap_before.strip().lower() in ("and", ",", ";", ", and")):
            return True
        stated = {(shape_key(l), shape_key(r)) for l_op, op, r_op in self.request.relations if op == "=" for l, r in [(_first(l_op), _first(r_op))]
                  if l is not None and r is not None}
        both = 0
        for e in (last, info):
            l, r = _first(e["left"]), _first(e["right"])
            if l is not None and r is not None and ((shape_key(l), shape_key(r)) in stated or (shape_key(r), shape_key(l)) in stated):
                both += 1
        return both == 2

    def _system_step(self, item: MathItem, chain: Chain, info: dict, operands: list[tuple[Operand, str]], rel_op: str, lone: bool,
                     head: Optional[Node], rooted: Optional[dict], prev: Optional[dict]) -> bool:
        """stem-soundness-5 (round 7): simultaneous equations. Consecutive equations of one part in the same two or more unknowns form a system
        (no line of it is a step from the one before unless a connective says so: '2x + y = 7', then 'x − y = 2', had failed as an algebra
        step); the values the answer then states for its unknowns ('so x = 5 and y = 3') are its stated solution, planned as one ``sol``
        check against every equation of the system (a wrong pair satisfying one equation only had passed, as a step that took the other stated
        value as a premise). Returns True when the line must not be read as a step from ``prev``."""
        if self._system_equation(info, operands, rel_op, lone, head):
            last = self._system[-1] if self._system else None
            joined = (last is not None and last["item"].part == item.part and info["order"] - last["order"] <= 1
                      and bool(info["unknown"] & last["unknown"]) and self._system_cue(item, chain, info, last))
            if joined:
                explicit = prev is not None and prev is last and self._step_cues(item, chain, prev)[0]
                self._system.append(info)
                return not explicit
            self._system = [info]
            self._system_sol = None
            return False
        if not self._system or len(self._system) < 2 or rooted is not None:
            return False
        unknowns = set().union(*(e["unknown"] for e in self._system))
        if not (lone and isinstance(head, Sym) and head.name in unknowns and rel_op == "=" and len(operands) == 2):
            return False
        value = _first(operands[1][0])
        if value is None or not is_closed(value) or self._system[-1]["item"].part != item.part:
            return False
        x = head.name
        sid = item.statement_id
        eq_sids = tuple(dict.fromkeys(s for e in self._system for s in e["sids"]))
        if self._system_sol is not None:
            rel = self.relations[self._system_sol]
            if x not in dict(rel.simultaneous_values) and info["order"] - self.order.get(rel.statement_ids[-1], -10) <= 1:
                self.relations[self._system_sol] = replace(rel, roots=rel.roots + (value,), simultaneous_values=rel.simultaneous_values + ((x, value),),
                                                           statement_ids=tuple(dict.fromkeys(rel.statement_ids + (sid,))), end=max(rel.end, operands[1][0].end))
                return prev is not None and len(prev["unknown"]) >= 2
            return False
        if info["order"] - self._system[-1]["order"] > 3:
            return False
        first = self._system[0]
        rel = self.add(kind="sol", outcome="check", statement_ids=tuple(dict.fromkeys(eq_sids + (sid,))), start=operands[0][0].start,
                       end=operands[1][0].end, op="=", left=operands[0][0], right=operands[1][0], part=item.part, premise_left=first["left"],
                       premise_op="=", premise_right=first["right"], premise_ids=eq_sids, root_symbol=x, roots=(value,),
                       simultaneous=tuple((e["left"], e["right"]) for e in self._system), simultaneous_values=((x, value),),
                       reason=f"the stated solution of the simultaneous equations in {', '.join(eq_sids)}, against every equation of the system")
        self._system_sol = rel.index
        # the value is no step from one equation of the system with another stated value as a premise
        return prev is not None and len(prev["unknown"]) >= 2

    def _given_in(self, name: str, part: str) -> bool:
        """Rule ``part-condition`` (STEM repair 11): ``name`` is given for a relation of ``part``: bound by something other than a stated root
        (:meth:`Scope.is_given`), a value the request states inside the question of another part not counting in mathematics ('(a) Find the acceleration
        of the particle when t = 1.' binds t in part (a) only). A condition the answer states ('At t = 1:') binds nothing beyond its own
        statement; the request's condition of one part now binds nothing beyond that part, so another part's equation in the letter ('(b)
        Find the values of t for which the particle is at rest': '6t − 3t² = 0') is an equation in an unknown there, its steps and its
        roots checked. Before, the request's 't = 1' made t given everywhere, and part (b)'s factorisation and roots had no check at all."""
        blist = self.scope.bindings.get(name, ())
        if not blist:
            return False
        spans = None
        for b in blist:
            if b.source == "root":
                continue
            if b.source == "request" and part and self.request.text and self.profile.is_mathematics:
                # in mathematics only (a letter of the sciences is a quantity, whose value a later part may use as given)
                if spans is None:
                    spans = _part_question_spans(self.request.text)
                other = next((p for p, (a0, b0) in spans.items() if a0 <= b.start < b0), "")
                if other and other != part:
                    continue
            return True
        return False

    def _part_condition_note(self, names: Iterable[str], part: str) -> str:
        """Rule ``part-condition`` (STEM repair 11): the clause a step or a root check of ``part`` adds to its reason for each of its
        letters that only a value the request states in another part's question binds: that value is given in its own part, so the letter
        is an unknown of this part's equations (the check's statement names the reading)."""
        if not part or not self.request.text or not self.profile.is_mathematics:
            return ""
        spans = None
        out: list[str] = []
        for name in sorted(names):
            if self._given_in(name, part):
                continue
            for b in self.scope.bindings.get(name, ()):
                if b.source != "request":
                    continue
                if spans is None:
                    spans = _part_question_spans(self.request.text)
                other = next((p for p, (a0, b0) in spans.items() if a0 <= b.start < b0), "")
                if other and other != part:
                    shown = f"{b.number.text}{(' ' + b.unit.text) if b.unit is not None else ''}"
                    out.append(f"{name} is an unknown of this part's equations: the request's {name} = {shown} stands in the question of part "
                               f"{other}, so it gives {name} that value in part {other} only (rule part-condition)")
                    break
        return "".join("; " + x for x in out)

    def _inequality_solution(self, item: MathItem, chain: Chain, prev: dict, info: dict, operands: list[tuple[Operand, str]], rel_op: str,
                             lone: bool, head: Optional[Node]) -> bool:
        """Rule ``inequality-solution`` (STEM repair 11, mathematics): a solved form ``x ⋈ d`` (the letter alone, a closed value; ⋈ an order
        sign or '=') that a step word joins to the relation before it in its part ('$12n > 135.36\\ldots$, so $n > 11.28\\ldots$'), where
        that relation is linear in the one letter, ``a·x + b ⋈′ c`` with closed a, b and c (either side), states the bound the step solves
        for: an ``eq`` check of ``(c − b)/a`` against ``d`` (a value written with its digits cut ranging over [w − u/2, w + u] on either
        side, τ = 0), when the direction ⋈ is the one dividing by a gives; a direction against it is a ``cmp`` step from the relation
        before, the cut values read at their written digits (it fails whatever they are). Read whatever values the answer states for the
        letter elsewhere (the student's solver result 'n = 11.46' had made n given, so the step had no check), and when no other step is
        planned. Before, a wrong bound ('n > 13.28…') had neither a check nor a finding of its own (the relation stayed ST-UNDEC-001, as the
        right one)."""
        if not self.profile.is_mathematics or not lone or not isinstance(head, Sym) or len(operands) != 2 or info.get("stepped"):
            return False
        groups = {"<": "lt", "≤": "lt", ">": "gt", "≥": "gt", "=": "eq"}
        if rel_op not in groups or prev["op"] not in groups or (groups[rel_op] == "eq") != (groups[prev["op"]] == "eq"):
            return False
        if prev["item"].part != item.part or prev["item"].statement_id not in (item.statement_id,) and info["order"] - prev["order"] > 1:
            return False
        explicit, _adjacent, _same, or_joined = self._step_cues(item, chain, prev)
        if not explicit or or_joined:
            return False
        x = head.name
        d_node = _first(operands[1][0])
        if d_node is None:
            return False
        d_cut = _ellipsis_value(d_node)
        d_val = d_cut if d_cut is not None else d_node
        if d_cut is None and (not is_closed(d_node) or unsupported_reasons(d_node)):
            return False
        pl, pr = _first(prev["left"]), _first(prev["right"])
        if pl is None or pr is None:
            return False
        for lin, other, x_left in ((pl, pr, True), (pr, pl, False)):
            if _syms(lin) != {x} or _syms(other) or isinstance(lin, Sym):
                continue  # (the relation before already solved for the letter: a restatement, not a step that solves)
            poly = polynomial(lin, x)
            if poly is None or poly[1] or set(poly[0]) - {0, 1} or not poly[0].get(1):
                continue
            a, b = poly[0][1], poly[0].get(0, Fraction(0))
            c_cut = _ellipsis_value(other)
            c_val = c_cut if c_cut is not None else other
            if c_cut is None and (not is_closed(other) or unsupported_reasons(other)):
                return False
            start, end = min(prev["left"].start, operands[0][0].start), max(prev["right"].end, operands[1][0].end)
            sids = tuple(dict.fromkeys(prev["sids"] + info["sids"]))
            num = BinOp("-", c_val, polynomial_node({0: b}, x, getattr(other, "start", 0), getattr(other, "start", 0)), getattr(other, "start", 0),
                        getattr(other, "end", 0), "−") if b else c_val
            bound = BinOp("/", num, polynomial_node({0: a}, x, getattr(lin, "start", 0), getattr(lin, "start", 0)), getattr(other, "start", 0),
                          getattr(other, "end", 0), "/")
            op_prev = prev["op"] if x_left else {"<": ">", "≤": "≥", ">": "<", "≥": "≤", "=": "="}[prev["op"]]
            expected = op_prev if a > 0 else {"<": ">", "≤": "≥", ">": "<", "≥": "≤", "=": "="}[op_prev]
            def as_written(n: Node) -> str:
                w = _ellipsis_value(n)
                return (w.number.text + "…") if w is not None else render(n)[:40]

            shown = f"{as_written(pl)} {prev['op']} {as_written(pr)}"
            if groups[expected] == groups[rel_op]:
                self.add(kind="eq", outcome="check", statement_ids=sids, start=start, end=end, op="=",
                         left=Operand((bound,), getattr(other, "start", start), getattr(other, "end", end)),
                         right=Operand((d_val,), operands[1][0].start, operands[1][0].end), part=item.part,
                         title="the bound the inequality step solves for, against the bound it states" if groups[rel_op] != "eq" else
                         "the value the equation step solves for, against the value it states",
                         cut_spans=((getattr(c_cut, "start", 0), getattr(c_cut, "end", 0)),) if c_cut is not None else (),
                         reason=f"the step from {shown} to {x} {rel_op} {render(d_val)[:40]}{'…' if d_cut is not None else ''}: the relation before it, linear "
                                f"in {x}, solved for {x} (({as_written(other)}{' − ' + render(polynomial_node({0: b}, x)) if b else ''}) / {render(polynomial_node({0: a}, x))}), "
                                f"against the value the step states (rule inequality-solution)"
                                + (" (rule ellipsis-rounding)" if d_cut is not None else ""))
            else:
                self.add(kind="cmp", outcome="check", statement_ids=sids, start=start, end=end, op=rel_op,
                         left=Operand((head,), operands[0][0].start, operands[0][0].end),
                         right=Operand((d_val,), operands[1][0].start, operands[1][0].end), part=item.part,
                         premise_left=Operand((pl if _ellipsis_value(pl) is None else _ellipsis_value(pl),), prev["left"].start, prev["left"].end),
                         premise_op=prev["op"],
                         premise_right=Operand((pr if _ellipsis_value(pr) is None else _ellipsis_value(pr),), prev["right"].start, prev["right"].end),
                         premise_ids=prev["sids"], explicit=True,
                         reason=f"the step from {shown} to {x} {rel_op} {render(d_val)[:40]}: dividing by {render(polynomial_node({0: a}, x))} "
                                f"gives the direction {expected}, so the step is checked as a step from the relation before it, any value written "
                                f"with its digits cut read at its written digits (rule inequality-solution)")
            # the two relations the step joins are checked through it: an order relation that is undecided only for its cut value ('12n >
            # 135.36…', 'n > 11.28…') is context now, its ST-UNDEC-001 withdrawn (it said the relation was not checked)
            lo_span, hi_span = prev["left"].start, operands[1][0].end
            for k, r in enumerate(self.relations):
                if r.kind == "link" and r.outcome == "undecided" and r.code == "ST-UNDEC-001" and r.reason == "a relation outside the encodings: an ellipsis" \
                        and lo_span <= r.start and r.end <= hi_span:
                    self.relations[k] = replace(r, outcome="context", code="", reason=r.reason + "; the step it belongs to is checked (rule inequality-solution)")
                    self.findings = [f for f in self.findings if not (f.code == "ST-UNDEC-001" and f.start == r.start and f.end == r.end)]
            info["stepped"] = True
            return True
        return False

    def _step_cues(self, item: MathItem, chain: Chain, prev: dict) -> tuple[bool, bool, bool, bool]:
        """What joins a chain to the relation before it for the step logic: ``explicit`` (a connective or step word: ⇒, ∴, so, hence,
        therefore, thus, gives, rearranging, …), ``adjacent`` (the next statement, each opening its own line of working), ``same_span``
        (the same maths item) and ``or_joined`` (an alternative, 'or', 'and' or a comma). Shared by the sequence and rule solved-law."""
        explicit = chain.connective in ("⇒", "∴") or any(w in chain.connective.split() for w in ("so", "hence", "therefore", "thus", "gives")) \
            or _has_step_word(item.gap_before) \
            or (len(item.gap_before or "") <= 240 and bool(_operation_hits(item.gap_before or "")))
        # argument diagnostics (ST-STEP-001): a stated operation before the line ("Dividing by x, x² = 4") says it is a step from the
        # line before as plainly as "so"
        opens = item.stmt_kind in ("derivation", "display_row") or (item.stmt_kind == "sentence" and not item.gap_before.strip())
        prev_opens = prev["item"].stmt_kind in ("derivation", "display_row") or (prev["item"].stmt_kind == "sentence" and not prev["item"].gap_before.strip()) \
            or prev["item"].ends_statement
        adjacent = self.order.get(item.statement_id, 0) - prev["order"] == 1 and opens and prev_opens
        same_span = prev["item"] is item
        or_joined = chain.connective in ("or", "and") or item.gap_before.strip().lower() in ("or", "and", ",")
        return explicit, adjacent, same_span, or_joined

    def _solved_law(self, item: MathItem, chain: Chain, operands: list[tuple[Operand, str]], ops: list[str], lone: bool, head: Optional[Node],
                    bound_before: frozenset[str]) -> Optional[Formula]:
        """Rule ``solved-law`` (STEM repair 7): the law the chain evaluates, solved for the symbol it gives a value, else None.

        A chain that gives a symbol S a value by a written expression ('I = 12 V / 2.9 Ω = 4.1 A', 'λ = 0.693/8.0 h = 0.087 h⁻¹') right
        after a law that states S but not on its own ('ε = I(R + r)'; 'λT½ = ln 2', reached from 'T½ = ln 2/λ'; 'V² = PR'), where the
        sequence would read it as an algebra step from the law, evaluates the law solved for S: the line's first link is read against
        that formula ('I = ε/(R + r)', 'λ = ln 2/T½', 'P = V²/R') exactly as against a formula the answer states for S, and no step is
        read. As a step it was decided exactly, with each other symbol of the law pinned to one value from anywhere in the answer, though
        the line writes rounded constants (0.693 for ln 2) and the values of its own part: correct working failed (INT-SUBJ-001). A value
        alone ('I = 4.1 A') after such a law is a value stated for S when the law has another symbol with no given value; when every
        other symbol has one, the law is an equation in S and the value its solution, a step within the value's band, as before.

        Not read: a Given statement, a law in which S occurs twice or under a function (a quadratic in S, ``e^(−λt)``: an equation the
        line solves, as before), a law with no other symbol, a law whose formula of S the answer states (rule rearranged-formula), an
        alternative ('or'), and anything the sequence would not read as a step (no new check is ever added). In mathematics, solving for a
        squared S takes its principal root, which ST-ALG-001 names when no domain restriction is stated, as for the step it replaces."""
        if self.request_mode or chain.lead or item.source == "given" or not lone or not isinstance(head, Sym) or head.kind != "symbol" \
                or not ops or ops[0] not in _EQUALITY or len(operands) < 2:
            return None
        rhs = _first(operands[1][0])
        prev = self.prev_rel
        name = head.name
        if rhs is None or not is_closed(rhs) or unsupported_reasons(rhs) or prev is None or prev.get("op") != "=" or prev["item"].part != item.part \
                or prev.get("swapped") or prev.get("positive") or name not in prev["syms"] or not prev["unknown"]:
            return None
        if prev["lone"] and getattr(prev["head"], "name", None) == name:
            return None  # the formula of S itself: its evaluation is read by the rule before this one
        if name in bound_before and self.scope.is_given(name):
            return None  # S already has a value: the sequence reads no step to it
        others = set(prev["syms"]) - {name}
        if not others or (is_value(rhs) and not (set(prev["unknown"]) - {name})):
            return None  # an equation in S alone, or a value solving the law in S: a step, as before
        explicit, adjacent, same_span, or_joined = self._step_cues(item, chain, prev)
        if or_joined or not ((explicit and (same_span or self.order.get(item.statement_id, 0) - prev["order"] <= 1)) or adjacent):
            return None  # no step was read here: nothing changes
        if self._rearranges_formula_of(name, prev):
            return None  # rule rearranged-formula: the formula the answer states for S is evaluated
        pl, pr = _first(prev["left"]), _first(prev["right"])
        if pl is None or pr is None or _has_func_of(pl, set(prev["unknown"])) or _has_func_of(pr, set(prev["unknown"])):
            return None  # a law with a function of an unknown: no step is decided (ST-UNDEC-001), as before
        solved = _solve_for(pl, pr, name, roots=True)
        if solved is None or unsupported_reasons(solved):
            return None
        if self.profile.is_mathematics and sum(isinstance(n, Root) for n in walk(solved)) > sum(isinstance(n, Root) for n in walk(pl)) \
                + sum(isinstance(n, Root) for n in walk(pr)):
            # solving took the principal square root of a squared symbol ('A = πr²' then 'r = √(50/π)'): as the algebra step this reading
            # replaces, mathematics names that no domain restriction is stated (ST-ALG-001), unless the line writes ± or one is stated
            rhs_node = _first(operands[1][0])
            text = item.context() + " " + prev["item"].context() + " " + self._request_lower
            if not any(isinstance(n, PlusMinus) for n in walk(rhs_node)) and not any(w in text for w in _RESTRICT_WORDS):
                sids = tuple(dict.fromkeys(prev["sids"] + (item.statement_id,)))
                self.finding("ST-ALG-001", f"the evaluation '{render(head)} = {render(rhs_node)}' takes only the non-negative square root of the law it "
                                           f"solves (rule solved-law) and no domain restriction is stated; its substitution is checked under that side "
                                           f"condition", sids, operands[0][0].start, operands[1][0].end, check_index=len(self.relations))
        return Formula(name, solved, prev["sid"], "solved", start=getattr(pl, "start", 0), end=getattr(pr, "end", 0))

    def _rearrangement_step(self, name: str, rel: dict) -> None:
        """Rule ``rearranged-formula`` (STEM repair 5): the relation ``rel``, which the line after it shows to be a rearrangement of the
        formula of ``name`` (that line evaluates the formula), is a step from that formula when no step was read for it yet, whatever
        words state it ('P = V²/R', then 'This rearranges to R = V²/P.', 'P = V²/R, i.e. R = V²/P', 'or R = V²/P', 'Equivalently, R =
        V²/P.'): the formula stated in its part, in its statement or the one before, in exactly the rearrangement's symbols. Before
        this repair the evaluation was read as a step from the rearrangement, which failed correct working; reading the evaluation as
        the formula's substitution left a wrong rearrangement in such words with no check (it had been caught through the evaluation),
        so it is checked here, as a step from the formula."""
        if rel.get("stepped") or rel.get("swapped"):
            return
        f = self._formula_infos.get(name)
        if f is None or f is rel or f.get("op") != "=" or rel.get("op") != "=" or f["item"].part != rel["item"].part \
                or not 0 <= rel["order"] - f["order"] <= 1 or set(f["syms"]) != set(rel["syms"]) or not rel.get("operands"):
            return
        operands = rel["operands"]
        first, last = _first(operands[0][0]), _first(operands[-1][0])
        if first is None or last is None:
            return
        rel["stepped"] = True
        if _has_func_of(_first(f["left"]) or Sym("?"), f["unknown"]) or _has_func_of(_first(f["right"]) or Sym("?"), f["unknown"]) \
                or _has_func_of(first, rel["unknown"]) or _has_func_of(last, rel["unknown"]):
            self._undecided("ST-UNDEC-001", "a step involving a function of an unknown",
                            dict(statement_ids=tuple(dict.fromkeys(f["sids"] + rel["sids"])), start=operands[0][0].start, end=operands[-1][0].end,
                                 op=rel["op"], left=operands[0][0], right=operands[-1][0], part=rel["item"].part, position=0, approx=False), rel["item"])
            return
        self._step(rel["item"], f, rel, operands, rel["op"], True,
                   note="; a rearrangement of the formula, which the next line evaluates (rule rearranged-formula)")

    def _rearranges_formula_of(self, name: str, prev: dict) -> bool:
        """Rule ``rearranged-formula`` (STEM repair 5): the preceding relation rearranges a formula the answer states for ``name``
        ('P = V²/R', then 'From P = V²/R, R = V²/P.', 'Rearranging, R = V²/P.', 'V² = P × R' or 'V²/P = R'; 'V = ε − Ir', then
        'Rearranging, I = (ε − V)/r.' or 'I × r = ε − V'): an equation in exactly the formula's symbols with ``name``, solved for another
        of them (a lone other symbol of the formula on its left) or written with neither side the lone ``name``. A line that then gives
        ``name`` a value, or writes its formula with values put in ('P = (9.93 V)² / 6.0 Ω'), evaluates the formula, as it does right after
        the formula itself: its substitution is checked against the formula, and it is never an algebra step from the rearrangement. Read
        as a step, it had the other symbols pinned to their values from other parts (R = 2.4 Ω, V = 9.9 V), so correct working failed.
        The formula's own statement is no rearrangement of it (the line after it is its evaluation by the rule before this one)."""
        if prev.get("op") != "=":
            return False
        ph = prev.get("head")
        if prev.get("lone") and (not isinstance(ph, Sym) or ph.name == name):
            return False
        for f in self.scope.formulas.get(name, ()):
            fs = _syms(f.expr)
            if (not prev.get("lone") or ph.name in fs) and len(fs - {name}) >= 1 and (fs | {name}) == set(prev["syms"]):
                return True
        return False

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

    def _step(self, item: MathItem, prev: dict, info: dict, operands: list[tuple[Operand, str]], rel_op: str, explicit: bool, note: str = "") -> None:
        """Plan an algebra (or inequality) step from ``prev`` to the relation of this chain. The
        relation of a chain for a step is its first link when that link is symbolic (``t = √(2s_y/g)``
        in ``t = √(2s_y/g) = √(2 × 45.0 / 9.81) = 3.03 s``), else the whole chain (first and last operands). ``note`` is added to
        the step's reason (rule rearranged-formula)."""
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
                    self._stated_operation(item, prev, left_op, right_op, sids, unknown, note_only=True)  # argument diagnostics: ST-STEP-002
                return
        kind = "cmp" if (rel_op in _ORDER or prev["op"] in _ORDER) else "alg"
        positive = tuple(dict.fromkeys(tuple(prev.get("positive", ())) + tuple(info.get("positive", ()))))
        # STEM repair 11: the readings the step rests on are named in its statement (rules part-condition and root-statement)
        note = self._part_condition_note(unknown, item.part) + note
        if prev.get("kept_by"):
            note = (f"; the step is from the equation in {', '.join(prev['sids'])}, which the root stated in {prev['kept_by']} solves and leaves as "
                    f"the relation the next line steps from (rule root-statement)") + note
        self.add(kind=kind, outcome="check", statement_ids=sids, start=left_op.start, end=right_op.end, op=rel_op, left=left_op, right=right_op,
                 premise_left=prev["left"], premise_op=prev["op"], premise_right=prev["right"], premise_ids=prev["sids"], explicit=explicit, part=item.part,
                 principal_root=principal, positive=positive,
                 reason="the step follows from the preceding relation" + (" (stated with a connective)" if explicit else " (consecutive lines)")
                 + ("; the principal (non-negative) root is taken" if principal else "")
                 + ("; read in " + ", ".join(f"{n} > 0" for n in positive) + " (each power of e of the unknown is a power of it)" if positive else "")
                 + note)
        if kind == "alg" and rel_op == "=" and prev["op"] == "=":
            self._stated_operation(item, prev, left_op, right_op, sids, unknown)  # argument diagnostics: ST-STEP-001 and ST-STEP-002

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

    def _roots_candidate(self, item: MathItem, chain: Chain, head: Sym, operands: list[tuple[Operand, str]]) -> Optional[dict]:
        """A stated root of an equation of degree two or more in the letter (stem-sol): the equation it is recorded for (STEM repair 11,
        rule root-statement: the sequence keeps it as the relation the next line steps from), else None."""
        root = _first(operands[1][0])
        if root is None or not is_closed(root):
            return None
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
            return None
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
            return eq
        line_key = (id(eq), x)
        if source == "answer" and line_key in self._line_roots:
            # stem-soundness-11 (round 7): a further root on the line right after the last root line of the same equation ('x = 2', then
            # 'x = −2') belongs to the same stated set
            idx, last_order = self._line_roots[line_key]
            rel = self.relations[idx]
            if self.order.get(sid, -10) == last_order + 1:
                self.relations[idx] = replace(rel, roots=rel.roots + (root,), statement_ids=tuple(dict.fromkeys(rel.statement_ids + (sid,))),
                                              end=max(rel.end, operands[1][0].end))
                self._line_roots[line_key] = (idx, self.order.get(sid, -10))
                group[key] = idx
                return eq
        # stem-soundness-11 (round 7): roots stated as values on the line right after their equation ('x² = 3x', then 'Dividing by x,
        # x = 3') claim the solution set as '⇒' does, unless the line says it gives one root of several or a domain restriction is stated;
        # before, only membership was checked, so a root lost by dividing by x passed. A root written as an expression (one sign of the
        # quadratic formula, '(5 + 1)/2', or a principal root '√(50/π)', which ST-ALG-001 names) and a formula's evaluation claim no set;
        # in the sciences a root is a quantity whose other root the context rejects, as before
        follows = (self.profile.is_mathematics and source == "answer" and eq is self.prev_rel and sid not in eq["sids"] and is_value(root)
                   and not eq.get("is_formula")
                   and not any(w in f" {stmt_text.lower()} " for w in _PARTIAL_ROOT_WORDS))
        complete = (complete_phrase or chain.connective in ("∴", "⇒") or follows) and not restricted
        rel = self.add(kind="sol", outcome="check", statement_ids=tuple(dict.fromkeys(eq["sids"] + (sid,))) if source == "answer" else (sid,),
                       start=operands[0][0].start, end=operands[1][0].end, op="=", left=operands[0][0], right=operands[1][0], part=item.part,
                       premise_left=eq["left"], premise_op="=", premise_right=eq["right"], premise_ids=eq["sids"], root_symbol=x, roots=(root,),
                       complete=complete, restricted=restricted,
                       reason=f"stated roots of the equation in {', '.join(eq['sids'])}" + ("; the full solution set is claimed" if complete else "")
                       + self._part_condition_note((x,), item.part))
        group[key] = rel.index
        if follows:
            self._line_roots[line_key] = (rel.index, self.order.get(sid, -10))
        return eq

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
                rel = self.add(kind="formula", outcome="formula", statement_ids=(item.statement_id,), start=br.start, end=br.end, op=br.op, part=item.part,
                               left=Operand((br.left,), br.start, br.end), right=Operand((br.right,), br.start, br.end),
                               reason=f"a Boolean definition of '{name_side.name}'")
                if isinstance(expr_side, Num) and expr_side.number.value in (0, 1):
                    # rule boolean-values (STEM repair 4): 'A = 1' gives the input A a value, which the statement's Boolean relations
                    # are evaluated under (and a name defined earlier, 'X = A AND B', is given a value there: 'X = 1')
                    value = expr_side.number.value == 1
                    self.bool_values.append((name_side.name, value, item.statement_id, br.start))
                    self.bool_constants.append((name_side.name, value, item.statement_id, rel.index, expr_side))
                return
        self.add(kind="bool", outcome="check", statement_ids=(item.statement_id,), start=br.start, end=br.end, op=br.op, bool_rel=br, part=item.part,
                 left=Operand((br.left,), br.start, br.end), right=Operand((br.right,), br.start, br.end), reason="a Boolean identity")

    def _boolean_values(self) -> None:
        """Rule ``boolean-values`` (STEM repair 4): a Boolean relation whose statement gives values to its inputs ('With A = 1 and B = 0,
        NOT A OR B = 0.', 'If A = 1, then NOT A = 0.', 'NOT A OR B = 0 when A = 1 and B = 0.') is the expression evaluated under those
        values, never an identity over every assignment: each input takes the value the statement gives it (the latest before the
        relation, else the first after it), and an input given no value stays free, so 'With A = 1, A OR B = 1' must hold for each value
        of B. When the relation's statement gives none of its inputs a value, the nearest earlier statement of its paragraph that gives
        one does, if it sets values up for the statements after it (it ends with a colon, opens with a setup word, 'Let', 'Take',
        'Suppose', 'Assume', 'Given', 'With', 'When', 'If', 'For', or states nothing but such values: 'A = 1, B = 0.', 'Here A = 1 and
        B = 0.', 'Test case: A = 1, B = 0.'), or if it is the statement right before and the relation's own opens with 'Then', 'So',
        'Hence', 'Thus' or 'Therefore'; a setup ending with a colon also sets up the paragraphs after it, across Boolean display lines
        only ('For A = 1 and B = 0:' then 'NOT A = 0.' then 'NOT A OR B = 0.'); the check then names both statements. A statement that
        says more than the values ('A = 0 is the reset state.', 'The register holds A = 1 after the reset.') sets nothing up: the
        relation after it is an identity. A name the answer defined earlier by an expression of other inputs ('X = A AND B') that a statement gives a
        value under the values it states ('With A = 1 and B = 1, X = 1') is that expression evaluated there (a check naming both
        statements). Before, every such relation was checked as an identity, so correct evaluations failed (INT-SUBJ-001), and a
        defined name's value went unchecked. A relation no statement gives a value is an identity, as before."""
        if not self.bool_values:
            return
        by_sid: dict[str, list[tuple[str, bool, int]]] = {}
        for name, value, sid, start in self.bool_values:
            by_sid.setdefault(sid, []).append((name, value, start))
        text_of = {it.statement_id: it.statement_text for it in self.items}

        def stated(names: set[str], sid: str, a: int, b: int) -> dict[str, bool]:
            out: dict[str, bool] = {}
            vals = by_sid.get(sid, [])
            for n in sorted(names):
                before = [(s, v) for nm, v, s in vals if nm == n and s < a]
                after = [(s, v) for nm, v, s in vals if nm == n and s >= b]
                if before:
                    out[n] = max(before)[1]
                elif after:
                    out[n] = min(after)[1]
            return out

        constant_rels = {ridx for _n, _v, _sid, ridx, _c in self.bool_constants}
        # the statements with maths in document order, and where each statement's text starts
        order = list(dict.fromkeys(it.statement_id for it in self.items))
        pos = {s: i for i, s in enumerate(order)}
        start_of: dict[str, int] = {}
        for it in self.items:
            start_of.setdefault(it.statement_id, it.statement_start)

        def words_outside(sid: str, spans: list[tuple[int, int]]) -> set[str]:
            # the words of a statement outside the given document spans, an opening label ending with ':' left out
            text, start = text_of.get(sid, ""), start_of.get(sid, 0)
            chars = list(text)
            for a, b in spans:
                for i in range(max(0, a - start), min(len(chars), b - start)):
                    chars[i] = " "
            rest = _BOOL_LABEL_RE.sub("", "".join(chars), count=1)
            return {w.lower() for w in re.findall(r"[A-Za-z]+", rest)}

        def only_values(sid: str) -> bool:
            # a statement that states nothing but values of Boolean inputs ('A = 1, B = 0.', 'Here A = 1 and B = 0.', 'Now set
            # A = 0.', 'Test case: A = 1, B = 0.'): every relation it holds gives an input a value, and no word but a connective
            # stands outside them; 'A = 0 is the reset state.' or 'The register holds A = 1 after the reset.' sets nothing up
            rels = [r for r in self.relations if sid in r.statement_ids and r.kind not in ("span", "continuation")]
            if not rels or not all(r.index in constant_rels for r in rels):
                return False
            return words_outside(sid, [(r.start, r.end) for r in rels]) <= _BOOL_VALUE_WORDS

        def display_line(sid: str) -> bool:
            # a statement of nothing but Boolean relations ('NOT A = 0.'), which a setup ending with ':' may introduce
            rels = [r for r in self.relations if sid in r.statement_ids and r.kind in ("bool", "formula") and r.bool_rel is not None]
            rels += [r for r in self.relations if sid in r.statement_ids and r.index in constant_rels]
            return bool(rels) and words_outside(sid, [(r.start, r.end) for r in rels]) <= _BOOL_VALUE_WORDS

        def previous(sid: str, names: set[str]) -> Optional[str]:
            # the nearest earlier statement of the paragraph that gives one of the inputs a value: it sets them up for the
            # statements after it when it ends with a colon, opens with a setup word ('Let A = 1 and B = 0.') or states nothing
            # but such values, and for the statement right after it when that one opens with a continuation word ('Then NOT A OR
            # B = 0.'). A setup ending with ':' introduces the paragraphs after it too ('For A = 1 and B = 0:' over the display
            # lines 'NOT A = 0.' and 'NOT A OR B = 0.' that follow it), when only Boolean display lines stand between
            m = re.fullmatch(r"s(\d+)\.(\d+)", sid)
            i = pos.get(sid)
            if m is None or i is None:
                return None
            para, k = m.group(1), int(m.group(2))
            crossed = False
            for j in range(i - 1, max(-1, i - 1 - _BOOL_SETUP_REACH), -1):
                prev = order[j]
                if prev.split(".", 1)[0] != order[j + 1].split(".", 1)[0]:
                    crossed = True
                gives = any(nm in names for nm, _v, _s in by_sid.get(prev, ()))
                head = text_of.get(prev, "")
                if crossed:
                    if gives:
                        return prev if head.rstrip().endswith(":") else None
                    if not display_line(prev):
                        return None
                    continue
                if not gives:
                    continue
                if head.rstrip().endswith(":") or _BOOL_SETUP_RE.match(head) or only_values(prev):
                    return prev
                if prev == f"s{para}.{k - 1}" and _BOOL_CONTINUE_RE.match(text_of.get(sid, "")):
                    return prev
                return None
            return None

        for idx, rel in enumerate(list(self.relations)):
            if rel.kind != "bool" or rel.outcome != "check" or rel.bool_rel is None or rel.assignment:
                continue
            sid = rel.statement_ids[0]
            names = _syms(rel.bool_rel.left) | _syms(rel.bool_rel.right)
            got = stated(names, sid, rel.start, rel.end)
            sids: tuple[str, ...] = (sid,)
            if not got:
                prev = previous(sid, names)
                if prev is not None:
                    got = stated(names, prev, 1 << 60, 1 << 60)
                    sids = (sid, prev)
            if not got:
                continue
            shown = ", ".join(f"{n} = {int(v)}" for n, v in sorted(got.items()))
            free = sorted(names - set(got))
            self.relations[idx] = replace(rel, assignment=tuple(sorted(got.items())), statement_ids=sids,
                                          reason=f"a Boolean expression evaluated under the values its statement states ({shown})"
                                                 + (f"; the inputs {', '.join(free)} are given no value, so it must hold for each of theirs" if free else "")
                                                 + " (rule boolean-values)")
        # a name defined earlier by an expression of other inputs, given a value under the inputs its statement states
        for name, value, sid, ridx, const in self.bool_constants:
            d = self.bool_defs.get(name)
            if d is None or d[1] == sid or isinstance(d[0], Num):
                continue
            expr, def_sid = d
            names = _syms(expr)
            if not names or name in names:
                continue
            rel = self.relations[ridx]
            got = stated(names, sid, rel.start, rel.end)
            if not got:
                continue
            br = BoolRelation(expr, "=", const, rel.start, rel.end)
            shown = ", ".join(f"{n} = {int(v)}" for n, v in sorted(got.items()))
            free = sorted(names - set(got))
            self.add(kind="bool", outcome="check", statement_ids=tuple(dict.fromkeys((sid, def_sid))), start=rel.start, end=rel.end, op="=", bool_rel=br,
                     part=rel.part, left=Operand((expr,), rel.start, rel.end), right=Operand((br.right,), rel.start, rel.end), assignment=tuple(sorted(got.items())),
                     reason=f"the value its statement gives '{name}' against its definition in {def_sid}, evaluated under the values the statement states "
                            f"({shown})" + (f"; the inputs {', '.join(free)} are given no value, so it must hold for each of theirs" if free else "")
                            + " (rule boolean-values)")

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
        is therefore 6.0 m s⁻²."): checked against that chain's final value when the chain computes it. When the last chain
        before the value states no value (it ends on an order relation: "… > 6000, so the answer is 12 years") or only
        states one for a symbol ("mid = 4"), the prose value restates nothing a chain computed, and no older chain is reached
        for instead."""
        for pv in self.prose_values:
            v = value_of(pv.node)
            if v is None:
                continue
            noun_ok = self._unit_words(pv, v)
            rounding = _rounding_cue(pv.before, pv.after, v[0], noun_ok)
            inline = _inline_restatement(pv.before) and _clause_ends(pv.after, noun_ok)
            if inline and not _INLINE_CONNECTIVE_RE.search(pv.before[-150:]) \
                    and not any(order == pv.statement_index and end <= pv.start and not (pv.part and part and pv.part != part)
                                for order, part, _e, end in self.chain_ends):
                # STEM repair 12: a value after an approximation word that no chain of its own statement closes before ('So each photon
                # carries 4.0 × 10⁻¹⁹ J, which is about 2.5 eV.': a prose quantity, not a chain, stands before the connective) is no inline
                # restatement: the other cues decide, as they did before 'which is about' was read as a connective. A value after one of
                # the connectives read before keeps that reading ('The power is 16.4 W, so 16 W to 2 s.f.': rule rounding-cue's)
                inline = False
            if not (_result_cue(pv.before) or (rounding is not None and _restating_word(pv.before)) or inline):
                continue
            if not inline and _PART_OF_IT_RE.match(pv.after or ""):
                # rule adjacent-restatement (STEM repair 5): the value after the cue is a part of the quantity before it ('So 4.4 W of it is
                # lost as heat in the wires.'): a consequence, never a restatement of the chain before it (it had been set against '= 16.4
                # W': INT-SUBJ-001 on correct working)
                continue
            best = None
            if inline:
                # rule inline-restatement (STEM repair 1): '… = 16.4 W, so 16 W' restates the chain the same statement just closed
                last_chain = next((e for order, part, e, end in reversed(self.chain_ends)
                                   if order == pv.statement_index and end <= pv.start and not (pv.part and part and pv.part != part)), None)
            else:
                # STEM repair 5: the last chain before the value is the last one that ends before it, in its own statement too when that
                # chain computes a value ('Also log₂ 1000 ≈ 9.97, so 10 passes.'): a value after such a chain that is no inline
                # restatement of it restates nothing, and no older chain is reached for (it had been set against '1,000 ÷ 2^10 = 0.98'
                # two paragraphs before). A value or a formula its own statement gives a symbol before it ('at $x = 1$ is 5', 'the curve
                # y = 3x² + 1 … is therefore 10') names a condition or an object of the sentence, never the chain it restates
                found = next(((order, e) for order, part, e, end in reversed(self.chain_ends)
                              if (order < pv.statement_index or (order == pv.statement_index and end <= pv.start and e is not None and e.get("computed")))
                              and not (pv.part and part and pv.part != part)), None)
                last_chain = found[1] if found is not None else None
                if found is not None and v[2] is None and not v[3] and found[0] < pv.statement_index - 1:
                    # rule adjacent-restatement (STEM repair 5): a bare number (no unit, no per cent sign) restates a chain of its own
                    # statement or of the statement right before it, never one further back ('With n = 1000 items, so 10 passes are
                    # needed.' had been set against '1,000 ÷ 2^10 = 0.98' three statements before, naming its genuine claim); a value with a
                    # unit or a per cent sign still reaches the last chain of its part, its dimension guarding the pairing
                    last_chain = None
                if last_chain is not None and found is not None and found[0] < pv.statement_index and self._own_value_before(pv, v, last_chain):
                    # rule adjacent-restatement (STEM repair 5): the value's own statement states, before it, another value of its kind,
                    # which the chain did not compute ('The measured rate at t = 0 h is 1620 counts min⁻¹, so the corrected rate is 1600
                    # counts min⁻¹.' after '… = 100 counts min⁻¹'): the cue follows that value, and no earlier chain is restated (it had
                    # been set against the 100: INT-SUBJ-001 on correct working)
                    last_chain = None
            for fv in reversed(self.final_values):
                # STEM repair 3: a stated value restated on its own line with the rounding the prose states ('R = 2.4 Ω (the external
                # resistance), or 3 Ω to one significant figure') is checked like a computed one
                if fv is not last_chain or not (fv.get("computed", True) or (inline and rounding is not None)):
                    continue
                if fv["order"] > pv.statement_index or (fv["order"] == pv.statement_index and not inline):
                    continue
                if pv.part and fv["part"] and pv.part != fv["part"]:
                    continue
                fvv = value_of(fv["node"])
                if fvv is None:
                    continue
                if _percent_against_quantity(v, fvv):
                    continue  # STEM repair 3: a percentage never restates a quantity of a dimension ('… = 6.0 m. So the uncertainty is 2%')
                if v[2] is None and fvv[2] is None and not v[3] and not fvv[3] and not inline and v[0].denominator == 1 \
                        and v[1] is not None and not v[1].has_point and fvv[0].denominator != 1 and self._restates_other_quantity(pv, fv):
                    # stem-precision-1 (round 7): a whole number with no unit after a chain whose value is no whole number is the chain's
                    # value only when the prose names nothing else: 'so the degrees of freedom are 3' after 'χ² = … = 384.864', 'so the
                    # loan lasts 60 months' after 'r = 0.035/12 = 0.0029167' count other quantities, and had been set against the chain
                    # (INT-SUBJ-001 on correct working)
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
            h_round, phrase = rounding if rounding is not None else (None, "")
            how = (f", rounded as the prose states ({phrase})" if phrase else "") + (" on the same line" if inline else "")
            self.add(kind="res", outcome="check", statement_ids=tuple(dict.fromkeys((best["sid"], pv.statement_id))), start=pv.start, end=pv.end, op="=",
                     left=best["operand"], right=Operand((pv.node,), pv.start, pv.end), part=pv.part, rounding=h_round, rounding_phrase=phrase,
                     reason=f"a prose restatement against the final value of the chain in {best['sid']}{how}")
            if h_round is not None:
                self._finer_restatement(best, Operand((pv.node,), pv.start, pv.end), pv.statement_id, pv.part, h_round, phrase)

    def _restates_other_quantity(self, pv: ProseValue, fv: dict) -> bool:
        """The clause between the result cue and the prose value ``pv`` names a quantity in words that the chain ``fv`` names nowhere
        (its symbol and its statement's words): the value is no restatement of the chain (stem-precision-1). 'so there are 4 half-lives'
        and 'therefore the answer is 6' name none and keep the check."""
        chain_text = next((it.statement_text.lower() for it in self.items if it.statement_id == fv.get("sid")), "")
        chain_words = set(_words(chain_text))
        if fv.get("symbol"):
            chain_words.add(fv["symbol"].lower())
        clause: list[str] = []
        for w in reversed(_words(pv.before[-120:])):
            if w in _CUE_WORDS:
                break
            clause.append(w)
        content = [w for w in clause if len(w) >= 3 and w not in _CLAUSE_STOP_WORDS and w.isalpha()]
        return any(w not in chain_words and w.rstrip("s") not in chain_words for w in content)

    def _own_value_before(self, pv: ProseValue, v: tuple, fv: dict) -> bool:
        """Rule ``adjacent-restatement`` (STEM repair 5): the statement of the prose value ``pv`` (value ``v``) states, before it, a prose
        value of the same kind (both of one dimension, or both bare numbers, per cent or not alike) that does not match the final value
        of the chain ``fv`` an earlier statement closed: the statement is about its own value ('The measured rate at t = 0 h is 1620
        counts min⁻¹, so …'), so the value after its cue restates nothing older. A statement that restates the chain's value before its
        cue ('The power is 16.4 W, so 16 W to 2 s.f.' after '= 16.4 W') keeps the pairing."""
        fvv = value_of(fv["node"])
        if fvv is None or fvv[1] is None:
            return False
        chain_value = Binding("", fvv[0], fvv[1], fvv[2], "statement", fv.get("sid", ""), wrapper=fvv[3])
        for q in self.prose_values:
            if q is pv or q.statement_id != pv.statement_id or q.end > pv.start:
                continue
            vq = value_of(q.node)
            if vq is None or vq[1] is None:
                continue
            if (vq[2] is None) != (v[2] is None) or bool(vq[3]) != bool(v[3]):
                continue
            if vq[2] is not None and (vq[2].dim is None or v[2].dim is None or not vq[2].dim.same_physical(v[2].dim)):
                continue
            if not Binding("", vq[0], vq[1], vq[2], "statement", q.statement_id, wrapper=vq[3]).same_as(chain_value):
                return True
        return False

    def _unit_words(self, pv: ProseValue, v: tuple):
        """STEM repair 4 (rule rounding-cue): which words name the unit of the prose value ``pv`` (value ``v``): for a bare value, the
        word written right after it ('5903 euros') and the words the request writes right after its numbers ('4000 euros': euro); for
        a value with a unit, that unit spelled out ('to the nearest volt' for a value in V). Only such a word may stand between the
        value and a rounding after it. A rounding 'to the nearest <word>' is read for the value's whole unit (its place 1), a part of
        the unit a bare value counts in ('to the nearest cent' for euros or dollars, 'penny' for pounds: 1/100), or another unit of a
        value's dimension ('to the nearest millimetre' for a value in m: 1/1000); the half-width is half that place. ``(word,
        unit_word) -> bool`` for a unit word, ``-> place or False`` for a rounding's word."""
        own = _WORD_AFTER_RE.match(pv.after or "")
        after_word = _singular(own.group(1)) if own is not None else ""
        task = {w for _n, _a, _b, w in self.request.values if w and w != "%"}
        unit = v[2]

        def ok(word: str, unit_word: bool):
            w = _singular(word.strip())
            if not w or w in _NO_KIND_WORDS:
                return False
            if unit is not None:
                if unit_word:
                    return False  # the unit is written with the value already
                u = parse_unit(w)
                if u is None:
                    u = parse_unit(w + "s")
                if not (u is not None and not u.unknown and u.dim is not None and unit.dim is not None and u.dim.same_physical(unit.dim)
                        and u.readings and unit.readings and u.readings[0].factor and unit.readings[0].factor):
                    return False
                # the value's own unit ('to the nearest ampere' for a value in A: 1), or another unit of its dimension, its size in the
                # value's unit ('to the nearest milliampere': 1/1000)
                return u.readings[0].factor / unit.readings[0].factor
            if unit_word:
                return w in task  # a word the task counts in ('euros'), never any word after the value ('so 12 N in total')
            counted = (after_word,) if after_word and after_word not in _NO_KIND_WORDS else tuple(sorted(task))
            if w in counted:
                return Fraction(1)  # 'to the nearest euro': the whole unit the value counts in
            # 'to the nearest cent' for a value in euros: a part of that unit
            return next((_SUBUNITS[w][c] for c in counted if c in _SUBUNITS.get(w, {})), False)

        return ok

    def _restated_bindings(self) -> None:
        """Rule ``restated-binding`` (STEM repair 2): a value the answer states for a symbol or a function value right after "so"
        (or "i.e.", "hence", "thus", "giving") that follows a chain on the same line ('“t = 8 h: 820 − 20 = 800 ± 16 counts min⁻¹” (so
        C(8) = 800)', '… = 0.087 h⁻¹, so k = 0.087 h⁻¹') names the value that chain just computed: a ``res`` check of the stated
        value against the chain's final value (its central value when the chain states an uncertainty), at warning severity (the
        word "so" pairs them). Not when the symbol is one of the chain's own ('1/R = 0.417 Ω⁻¹, so R = 2.4 Ω' solves for R), when no
        chain computes on the line before it, or when the two values have different dimensions."""
        for item, head, value_op, start in self.stated_values:
            if not _RESTATE_SO_RE.search(item.gap_before[-24:]):
                continue
            prev = next((e for order, _part, e, end in reversed(self.chain_ends) if order == item.statement_index and end <= start), "none")
            if prev == "none" or prev is None or not prev.get("computed"):
                continue
            if prev.get("expr") is None and prev["syms"] and not any(self.scope.bindings.get(s) or self.scope.substitutions.get(s) for s in prev["syms"]):
                # a chain whose computing side is no closed expression and none of whose symbols has a stated value states a relation
                # between unknowns ('$C/Y = 12$', a finance solver's setting, before 'giving $FV = -11\,491.11$'): it computes no value
                # that a 'so' or 'giving' after it could restate (found when the overseer build was merged with the translator's
                # LaTeX thin-space reading, which made the stated value readable)
                continue
            name = head.name if isinstance(head, Sym) else head.name + "()" if isinstance(head, Apply) else head.left.name
            if name in prev["syms"] or (isinstance(head, Sym) and head.name == prev.get("symbol")):
                continue
            node = value_op.readings[0] if value_op.readings else None
            v, fv = value_of(node) if node is not None else None, value_of(prev["node"])
            if v is None or fv is None:
                continue
            if v[2] is not None and fv[2] is not None and (v[2].dim is None or fv[2].dim is None or not v[2].dim.same_physical(fv[2].dim)):
                continue
            shown = render(head)[:40] if not isinstance(head, BinOp) else " ".join(self.text[head.start:head.end + 1].split())[:40]  # 'C(8)
            self.add(kind="res", outcome="check", statement_ids=tuple(dict.fromkeys((prev["sid"], item.statement_id))), start=value_op.start,
                     end=value_op.end, op="=", left=prev["operand"], right=value_op, part=item.part, restates=shown,
                     reason=f"the value stated for {shown} after 'so' against the final value of the chain before it on the same line, in "
                            f"{prev['sid']} (rule restated-binding)")

    def _prose_conversions(self) -> None:
        """Rule ``prose-conversion`` (STEM repair 5): a value the prose states and restates right after it in another unit of the same
        dimension, after 'that is', 'i.e.', 'which is', 'which equals', 'which is equal to', 'equal to', 'equivalent to', 'or equivalently'
        (after a comma, a semicolon, a colon or a dash, or none) or ', or' (a comma before it: '10 Ω or 1 kΩ' may name two resistors), in
        brackets (alone, or after 'or', 'i.e.' or 'that is'), or after 'is', 'equals', 'is equal to', 'is equivalent to', 'is the same
        as', 'converts to' or 'is converted to', or after a comma and 'about', when the restated value ends its clause ('The mixture is
        55.0 cm³, that is 0.0550 dm³.', '55.0 cm³ (0.0550 dm³)', '55.0 cm³ is 0.0550 dm³.', '55.0 cm³, about 0.06 dm³.'), each
        optionally with 'about', 'approximately', 'roughly' or 'nearly' (τ = 1/20), is a unit conversion: a ``cnv`` check of
        the two values, as when they are written with '=' ('55.0 cm³ = 0.0550 dm³'). Before, no relation was read, so a wrong conversion
        ('55.0 cm³, that is 0.550 dm³') had neither a check nor an ST code. Two values written in one unit, values of two dimensions, a
        unit the table does not read, anything else between them, a restated value its clause goes on after ('2.0 km is 500 m more than
        1.5 km'), and a first value that ends a range, a list or a comparison ('from 20.0 °C to 60.0 °C, that is 40.0 K' may restate the
        change) are not read. STEM repair 10: whether the restated value ends its clause is read in its own statement (its prose after
        the value, up to the statement's end); before, a window of the whole text was read, so a conversion written with a verb, with
        'gives' after the unit it names or after ', about' was read only when it ended the answer: followed by any other statement ('A
        time of 45 s is 0.45 min.' then 'Two reminders.') it had neither a check nor an ST code."""
        if len(self.prose_values) < 2 or not self.text:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind in ("res", "cnv")}
        pvs = self.prose_values
        for a, b in zip(pvs, pvs[1:]):
            if a.statement_id != b.statement_id or a.end > b.start or (b.start, b.end) in planned or b.start - a.end > 40:
                continue
            between = self.text[a.end:b.start]
            m = _PROSE_RESTATE_RE.match(between)
            mu = _PROSE_TO_UNIT_RE.match(between) if m is None else None
            if (m is None and mu is None) or _RANGE_END_RE.search(a.before[-24:]):
                continue
            close = re.match(r"[ \t]*\)", self.text[b.end:b.end + 4]) if m is not None and m.group("bracket") else None
            if m is not None and m.group("bracket") and close is None:
                continue  # a bracket holds the restated value alone: '55.0 cm³ (0.0550 dm³)'
            if (mu is not None or m.group("verb") or m.group("about_c")) and not _clause_ends(b.after):
                # '55.0 cm³ is 0.0550 dm³.' ends its clause; '2.0 km is 500 m more than …' compares two values. STEM repair 10: the prose
                # after the value in its own statement (b.after ends at the statement's end), never the text of the statements after it
                continue
            va, vb = value_of(a.node), value_of(b.node)
            if va is None or vb is None or va[1] is None or vb[1] is None or va[2] is None or vb[2] is None:
                continue
            ua, ub = va[2], vb[2]
            if ua.unknown or ub.unknown or ua.dim is None or ub.dim is None or not ua.dim.same_physical(ub.dim):
                continue
            if " ".join(ua.text.split()) == " ".join(ub.text.split()):
                continue
            if mu is not None and " ".join(mu.group("unit").split()) != " ".join(ub.text.split()):
                continue  # 'in <unit> is': the unit the prose names is the restated value's own
            approx = bool(mu.group("about_u")) if mu is not None else bool(m.group("about") or m.group("about_b") or m.group("about_v") or m.group("about_c"))
            # a rule's check from two places of the prose: its title says so, and its operands are where they are written (never cut)
            self.add(kind="cnv", outcome="check", statement_ids=(a.statement_id,), start=a.start, end=b.end + (close.end() if close else 0),
                     op="≈" if approx else "=", left=Operand((a.node,), a.start, a.end), right=Operand((b.node,), b.start, b.end), part=a.part,
                     approx=approx, title="the unit conversion the prose states",
                     reason="a value the prose restates right after it in another unit of the same dimension: a unit conversion (rule prose-conversion)")

    def _prose_bases(self) -> None:
        """Rule ``prose-base`` (STEM repair 10): a whole number the prose states in one base and restates right after it in another, each
        base written (a base subscript, 'in binary', 'in denary', 'in hexadecimal', 'in base 8', or 'the binary number', 'the denary
        number' before the value; 'the binary representation of 50 is …' gives the restated value's base), after 'is', 'equals', 'is
        equal to', 'is written as', 'which is', 'that is', 'i.e.', '=', 'gives', 'converts to', 'is converted to' or 'becomes', when the
        restated value ends its clause ('The binary number 110010₂ is 48 in denary.', '110010 in binary is 50 in denary.', 'The denary number
        50 is 110010 in binary.'), is a based-numeral conversion: a ``base`` check of the two numerals as exact integers, as when they are
        written with '=' ('110010₂ = 50₁₀'). A value written without a base marker beside a restatement that names one is decimal. Before,
        no relation was read, so a wrong conversion had neither a check nor an ST code. Two values in one base, a digit the base does not
        have, a value with a point, a unit or a per cent, and a restated value its clause goes on after are not read.

        STEM repair 12: a hexadecimal numeral with letter digits is read too: one with no base marker ('3E9', 'FF', '1F4'; the lexer reads
        it as letters, or as e-notation) where the words beside it, or a base phrase opening the clause, name base 16 for it
        (:data:`_HEX_WORD_RE`, computer science only, and never as decimal), and a base phrase opening the clause, or named right after the
        first numeral, is read as either numeral's when the other carries a base marker ('In hexadecimal, 1000 is 3E9₁₆.': the second's).
        Before, 'In hexadecimal, 1000 is 3E9.', 'In hexadecimal, 1000 is 3E9₁₆.', '1000 in denary is 3E9 in hexadecimal.' and 'The
        hexadecimal number 3E9 is 1000 in denary.' had neither a check nor an ST code."""
        hexwords = self._hex_words() if self.profile.computer_science and self.text else []
        if len(self.prose_values) + len(hexwords) < 2 or not self.text:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind in ("res", "cnv", "base", "giv")}
        unmarked = {(h.start, h.end) for h in hexwords}

        def bv(pv: ProseValue, words: list[str]) -> Optional[Num]:
            if (pv.start, pv.end) in unmarked:
                # a hexadecimal numeral written with letter digits and no marker: base 16 only where the words name it
                named = {_BASE_OF.get(re.sub(r"^base[ \t-]?", "", w.lower()), 0) for w in words}
                return pv.node if named == {16} and isinstance(pv.node, Num) else None
            return self._based_value(pv.node, words)

        pvs = self.prose_values
        pairs = list(zip(pvs, pvs[1:])) + self._hex_word_pairs(pvs, hexwords)
        pairs.sort(key=lambda ab: (ab[0].start, ab[1].start))
        for a, b in pairs:
            if a.statement_id != b.statement_id or a.end > b.start or b.start - a.end > 48 or (b.start, b.end) in planned:
                continue
            m = _BASE_BETWEEN_RE.match(self.text[a.end:b.start])
            if m is None:
                continue
            tail = _BASE_AFTER_RE.match(b.after)
            if not _clause_ends(b.after[tail.end():] if tail is not None else b.after):
                continue  # '110010₂ is 50 in denary.' ends its clause; '110010₂ is 50 more than …' compares
            restated_of = _BASE_OF_RE.search(a.before[-48:])
            before = _BASE_BEFORE_RE.search(a.before[-48:]) if restated_of is None else None
            if before is not None and not m.group("ab") and _BASE_OPEN_RE.search(a.before):
                # STEM repair 12: the base word right before the first numeral ends a phrase opening the clause ('In binary 1000 is 1111101000.',
                # 'In hexadecimal 1000 is 3E8.', with no comma): read as the opening phrase it is, either numeral's (before, it was read as the
                # first numeral's base only, as in 'the binary number 1000', so correct working failed, 'In octal 64 is 100.' among it)
                before = None
            # STEM repair 11: a base named once, opening the clause before both numerals ('In binary, 1000 is 1111101100.'): before, no base was
            # read at all (the base word is not right before the value), so the two numerals were read as decimal and nothing was planned
            opening = _BASE_OPEN_RE.search(a.before) if (restated_of is None and before is None and not m.group("ab")) else None
            words_a = [w for w in ((m.group("ab"),) if m.group("ab") else ()) + ((before.group("b"),) if before is not None else ())
                       + ((opening.group("b"),) if opening is not None else ()) if w]
            words_b = [w for w in ((tail.group("b"),) if tail is not None else ()) + ((restated_of.group("b"),) if restated_of is not None else ()) if w]
            alternative: tuple[Node, Node] = ()
            if (m.group("ab") or opening is not None) and before is None and not words_b and isinstance(a.node, Num) and isinstance(b.node, Num):
                # '10 in binary is 1010': the base named right after the first numeral may be the first's ('1010 in binary is 10') or
                # the base the first is written in by the second ('10 in binary is 1010', '100 in octal is 144'): either reading, each
                # numeral's digits allowing it, and the check holds when either does (reading the first only had failed correct working).
                # STEM repair 11: a base opening the clause ('In binary, 1000 is 1111101000') is read the same two ways. STEM repair 12: a
                # numeral with a base marker keeps its own base in both readings, so 'In hexadecimal, 1000 is 3E9₁₆' names the second's base
                # (before, the phrase was read as the first's only, the two came out in one base and nothing was planned), and a numeral with
                # letter digits is read in base 16 only where the phrase names it
                first = (bv(a, words_a), bv(b, []))
                second = (bv(a, []), bv(b, words_a))
                readings = [r for r in (first, second) if r[0] is not None and r[1] is not None and r[0].number.base != r[1].number.base]
                if not readings:
                    continue
                (na, nb), alternative = readings[0], (readings[1] if len(readings) > 1 else ())
            else:
                na, nb = bv(a, words_a), bv(b, words_b)
                if na is None or nb is None or na.number.base == nb.number.base or 10 == na.number.base == nb.number.base:
                    continue
                if not (na.number.based or nb.number.based or words_a or words_b):
                    continue  # no base is written: two decimal numbers
            lettered = any((x.start, x.end) in unmarked or (isinstance(x.node, Num) and x.node.number.scientific) for x in (a, b))
            self.add(kind="base", outcome="check", statement_ids=(a.statement_id,), start=a.start, end=b.end + (tail.end() if tail is not None else 0), op="=",
                     left=Operand((na,), a.start, a.end), right=Operand((nb,), b.start, b.end), part=a.part, title="the base conversion the prose states",
                     alternative=alternative,
                     reason="a whole number the prose restates right after it in another base, each base written: a based-numeral conversion "
                            + ("(the base named right after the first numeral read as its own or as the second's, either reading) " if alternative
                               else "")
                            + ("(a numeral with letter digits read in base 16, which the words beside it name) " if lettered else "") + "(rule prose-base)")
            planned.add((b.start, b.end))

    def _worded_base(self, base: dict, item: MathItem, lnode: Node, rnode: Node, right: Operand) -> bool:
        """Rule ``prose-base`` (STEM repair 12): a whole number set equal, with '=', to a numeral whose base the words right after it name, its
        clause ending there ('1000 = 3E8 in hexadecimal.', '1000 = 1111101000 in binary.'), is a based-numeral conversion: a ``base`` check
        of the two numerals as exact integers, each in its own base (the first, with no marker and no words naming its base, decimal).
        Before, the line was written arithmetic on the numerals read as decimal ('3E8' as 3 × 10⁸), so correct working failed
        (INT-SUBJ-001) and a wrong conversion failed for the wrong reason. True when the check is added."""
        off = item.statement_start
        after = item.statement_text[max(0, right.end - off):]
        tail = _BASE_AFTER_RE.match(after[:40])
        if tail is None or not _clause_ends(after[tail.end():tail.end() + 160]):
            return False
        na = self._based_value(lnode, [])
        hexed = self._hex_written(item, right)
        if hexed:
            # letters alone ('FF', 'FE') the parser reads as a product of symbols: the numeral as written, read in base 16 only where the words
            # right after it name that base
            written = item.statement_text[max(0, right.start - off):max(0, right.end - off)].strip()
            named = _BASE_OF.get(re.sub(r"^base[ \t-]?", "", tail.group("b").lower()), 0)
            value = exact_based(written, written, 16, limits=self.lim) if named == 16 else None
            nb = Num(value, right.start, right.end) if value is not None else None
        else:
            nb = self._based_value(rnode, [tail.group("b")])
        if na is None or nb is None or na.number.base == nb.number.base:
            return False
        lettered = hexed or (isinstance(rnode, Num) and rnode.number.scientific)
        left = base["left"]
        self.add(kind="base", outcome="check", **{**base, "end": right.end + tail.end(), "left": Operand((na,), left.start, left.end),
                                                  "right": Operand((nb,), right.start, right.end)},
                 title="the base conversion the line states",
                 reason="a whole number set equal to a numeral whose base the words right after it name: a based-numeral conversion "
                        + ("(a numeral with letter digits read in base 16, which the words beside it name) " if lettered else "") + "(rule prose-base)")
        return True

    def _hex_written(self, item: MathItem, op: Operand) -> bool:
        """Rule prose-base (STEM repair 12): the operand of ``item`` is written as one hexadecimal numeral with letter digits and no marker
        (:data:`_HEX_WORD_RE`), in a computer-science answer."""
        off = item.statement_start
        if not self.profile.computer_science or op.end <= op.start or op.start < off:
            return False
        return bool(_HEX_WORD_RE.fullmatch(item.statement_text[op.start - off:op.end - off].strip()))

    def _hex_words(self) -> list[ProseValue]:
        """Rule prose-base (STEM repair 12): the hexadecimal numerals with letter digits and no base marker the prose writes outside every
        prose value ('3E8' the lexer reads as e-notation is a prose value already; 'FF', '1F4', '7D0' are letters to it), each as a
        candidate value in base 16 (:data:`_HEX_WORD_RE`). The candidate's statement and context come from the prose value it is paired
        with (:meth:`_hex_word_pairs`); this only reads where they are. Bounded: at most 64, each of at most 16 digits."""
        covered = [(pv.start, pv.end) for pv in self.prose_values]
        out: list[ProseValue] = []
        for mt in _HEX_WORD_RE.finditer(self.text):
            if len(out) >= 64:
                break
            a, b = mt.start(), mt.end()
            if any(x < b and a < y for x, y in covered):
                continue
            value = exact_based(mt.group(0), mt.group(0), 16, limits=self.lim)
            if value is None:
                continue
            out.append(ProseValue("", 0, "", Num(value, a, b), a, b, "", ""))
        return out

    def _hex_word_pairs(self, pvs: list[ProseValue], hexwords: list[ProseValue]) -> list[tuple[ProseValue, ProseValue]]:
        """Rule prose-base (STEM repair 12): each hexadecimal word paired with the prose value right before it and with the one right
        after it, at most 48 characters away (the pairing reads only the words between), the word given that value's statement, part
        and the prose before or after it within the value's window."""
        out: list[tuple[ProseValue, ProseValue]] = []
        for h in hexwords:
            prev = next((p for p in reversed(pvs) if p.end <= h.start), None)
            nxt = next((p for p in pvs if p.start >= h.end), None)
            if prev is not None and h.start - prev.end <= 48 and h.end - prev.end <= len(prev.after):
                hv = replace(h, statement_id=prev.statement_id, statement_index=prev.statement_index, part=prev.part,
                             before=(prev.before + self.text[prev.start:h.start])[-240:], after=prev.after[h.end - prev.end:])
                out.append((prev, hv))
            if nxt is not None and nxt.start - h.end <= 48 and nxt.start - h.start <= len(nxt.before):
                hv = replace(h, statement_id=nxt.statement_id, statement_index=nxt.statement_index, part=nxt.part,
                             before=nxt.before[:len(nxt.before) - (nxt.start - h.start)], after=self.text[h.end:nxt.start])
                out.append((hv, nxt))
        return out

    def _based_value(self, node: Node, words: list[str]) -> Optional[Num]:
        """Rule prose-base: the numeral ``node`` as an exact integer in the base its base marker writes (a subscript) or the words beside it
        name (each naming the same base); a numeral with neither is decimal. None for anything but a bare whole numeral, for two bases,
        and for a digit the base does not have. STEM repair 12: a numeral the lexer read in e-notation whose characters are all
        hexadecimal digits ('3E9', '1E3') is that hexadecimal numeral when the words name base 16 for it (never otherwise)."""
        if not isinstance(node, Num):
            return None
        n = node.number
        named = {_BASE_OF.get(re.sub(r"^base[ \t-]?", "", w.lower()), 0) for w in words}
        if 0 in named or len(named) > 1:
            return None
        if named == {16} and n.scientific and not n.based and _HEX_DIGITS_RE.fullmatch(n.text.strip() or "-"):
            value = exact_based(n.text, n.text.strip(), 16, limits=self.lim)
            return Num(value, node.start, node.end) if value is not None else None
        if n.has_point or n.scientific or n.vulgar or n.power_of_ten or n.value.denominator != 1 or n.value < 0:
            return None
        if n.based or n.base != 10:
            return node if not named or named == {n.base} else None
        base = next(iter(named)) if named else 10
        if base == 10:
            return node
        digits = re.sub(r"[^0-9A-Fa-f]", "", n.text)
        if not digits or digits != n.text.strip():
            return None  # '1,010' or a sign: not the digits of one based numeral
        value = exact_based(n.text, digits, base, limits=self.lim)
        return Num(value, node.start, node.end) if value is not None else None

    def _rounded_bindings(self) -> None:
        """Rule ``rounding-cue`` for a value stated for a symbol (STEM repair 5): a statement that gives a symbol a value with a rounding it
        states ('To 3 s.f., P = 16.4 W.', 'P = 16 W to 2 s.f.') restates the symbol's last computed value in its part (the final value of a
        chain that gives that symbol a value, in an earlier statement of the part): a ``res`` check with the stated rounding, as when the
        prose names the quantity ('To 3 s.f., the power is 16.4 W.'). Before, it was read as a value given to the symbol, with neither a
        check nor an ST code, so 'To 3 s.f., P = 16.5 W.' after 'P = … = 16.4 W' passed."""
        if not self.stated_values or not self.final_values:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind == "res"}
        for item, head, value_op, _start in self.stated_values:
            if not isinstance(head, Sym) or head.kind != "symbol" or (value_op.start, value_op.end) in planned:
                continue
            node = value_op.readings[0] if value_op.readings else None
            v = value_of(node) if node is not None else None
            if v is None or v[1] is None:
                continue
            off = item.statement_start
            before = item.statement_text[:max(0, value_op.start - off)]
            after = item.statement_text[max(0, value_op.end - off):][:160]
            pv = ProseValue(item.statement_id, item.statement_index, item.part, node, value_op.start, value_op.end, before, after)
            rounding = _rounding_cue(before, after, v[0], self._unit_words(pv, v))
            if rounding is None:
                continue
            prev = next((fv for fv in reversed(self.final_values) if fv.get("symbol") == head.name and fv.get("computed")
                         and fv["order"] < item.statement_index and not (item.part and fv["part"] and fv["part"] != item.part)), None)
            if prev is None:
                continue
            fvv = value_of(prev["node"])
            if fvv is None or _percent_against_quantity(v, fvv):
                continue
            if v[2] is not None and fvv[2] is not None and (v[2].dim is None or fvv[2].dim is None or not v[2].dim.same_physical(fvv[2].dim)):
                continue
            h_round, phrase = rounding
            self.add(kind="res", outcome="check", statement_ids=tuple(dict.fromkeys((prev["sid"], item.statement_id))), start=value_op.start,
                     end=value_op.end, op="=", left=prev["operand"], right=value_op, part=item.part, rounding=h_round, rounding_phrase=phrase,
                     reason=f"the value stated for {head.name} with the rounding the statement states ({phrase}), against the final value of the chain "
                            f"that computes {head.name} in {prev['sid']} (rule rounding-cue)")
            self._finer_restatement(prev, value_op, item.statement_id, item.part, h_round, phrase)

    def _finer_restatement(self, fv: dict, stated: Operand, sid: str, part: str, h_round: Fraction, phrase: str) -> None:
        """Rule ``finer-restatement`` (STEM repair 7): a value restated with a rounding the prose states that is finer than the place of the
        chain's stated final value ('To 3 s.f., V = 9.90 V.' or 'To three significant figures, V = 9.94 V.' after 'V = 12 V − (4.14 A ×
        0.50 Ω) = 9.9 V') states figures the final value does not carry: they can only come from the chain's written arithmetic. So, beside
        the rounding-cue check against the final value (|S − S′| ≤ h(S) + h(S′), which both had passed), the restated value is set against
        the value the expression the chain's last '=' evaluates gives (9.93), within the stated rounding's half-width alone, its numerals as
        written (a carried result or a written constant over its interval, as in written arithmetic): a reading the answer did not state
        (it may have computed with figures its working does not show), so the check fails at warning severity. Nothing is added when the
        rounding is not finer, the chain writes no closed expression before its value, or the two values' units cannot be compared."""
        expr = fv.get("expr")
        sv, fvv = value_of(stated.readings[0]) if stated.readings else None, value_of(fv["node"])
        if expr is None or sv is None or fvv is None or fvv[1] is None:
            return
        h_prev = fvv[1].half_width
        num = sv[1]
        if num is None:
            return
        # the restated value's own precision: the stated rounding, never finer than its last written digit ('To 3 s.f., V = 9.8 V' is 9.8)
        h_eff = h_round if (num.vulgar or num.power_of_ten or num.based) else max(h_round, Fraction(1, 2) * Fraction(10) ** num.last_place)
        f_s, f_p = Fraction(1), Fraction(1)
        if sv[2] is not None or fvv[2] is not None:
            if sv[2] is None or fvv[2] is None:
                return
            if " ".join(sv[2].text.split()) != " ".join(fvv[2].text.split()):
                rs, rp = sv[2].readings, fvv[2].readings
                if len(rs) != 1 or len(rp) != 1 or rs[0].factor is None or rp[0].factor is None or rs[0].affine is not None or rp[0].affine is not None:
                    return
                f_s, f_p = abs(rs[0].factor), abs(rp[0].factor)
        if not h_eff * f_s < h_prev * f_p:
            return
        self.add(kind="res", outcome="check", statement_ids=tuple(dict.fromkeys((fv["sid"], sid))), start=stated.start, end=stated.end, op="=",
                 left=expr, right=stated, part=part, rounding=h_round, rounding_phrase=phrase, finer=True,
                 reason=f"the value restated with the rounding the prose states ({phrase}), finer than the final value of the chain in {fv['sid']}, "
                        "against the value that chain's written arithmetic gives (rule finer-restatement)")

    def _rounded_prose_values(self) -> None:
        """Rule ``rounding-cue`` for a value the prose states (STEM repair 5): a value the prose restates right after a value it states in
        the same clause, after ', so', ', which is', ', or', ', i.e.' or ', that is', in the same unit, with a rounding the prose states
        ('The power is 16.4 W, so 16 W to 2 s.f.', '…, which is 16 W to two significant figures'), restates that value: a ``res`` check
        with the stated rounding, as for a chain's final value ('= 16.4 W, so 16 W to 2 s.f.'). Before, nothing was read, so 'The power
        is 16.4 W, so 17 W to 2 s.f.' passed. Values of two kinds, and a restatement with no stated rounding, are not read."""
        if len(self.prose_values) < 2 or not self.text:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind in ("res", "cnv")}
        pvs = self.prose_values
        for q, pv in zip(pvs, pvs[1:]):
            if q.statement_id != pv.statement_id or q.end > pv.start or (pv.start, pv.end) in planned or pv.start - q.end > 24:
                continue
            if not _PROSE_ROUNDED_RE.match(self.text[q.end:pv.start]):
                continue
            v, vq = value_of(pv.node), value_of(q.node)
            if v is None or vq is None or v[1] is None or vq[1] is None or (v[2] is None) != (vq[2] is None) or bool(v[3]) != bool(vq[3]):
                continue
            if v[2] is not None and (v[2].unknown or vq[2].unknown or " ".join(v[2].text.split()) != " ".join(vq[2].text.split())):
                continue
            noun_ok = self._unit_words(pv, v)
            rounding = _rounding_cue(pv.before, pv.after, v[0], noun_ok)
            if rounding is None:
                continue
            h_round, phrase = rounding
            self.add(kind="res", outcome="check", statement_ids=(pv.statement_id,), start=pv.start, end=pv.end, op="=",
                     left=Operand((q.node,), q.start, q.end), right=Operand((pv.node,), pv.start, pv.end), part=pv.part, rounding=h_round,
                     rounding_phrase=phrase,
                     reason=f"a value the prose restates right after the value it states, with the rounding the prose states ({phrase}) (rule rounding-cue)")

    def _rounded_digits(self) -> None:
        """Rule ``rounded-digits`` (STEM repair 9): a value the answer states with a rounding the prose states for it is written to that
        rounding: the place of its last written digit is the place the rounding names (a whole number's trailing zeros may stand for it:
        '60' is written to the units or to the tens). Read for every value rule rounding-cue reads (a restated result, a value restated
        on its own line or after ', so' or ', which is', a value stated for a symbol), and for a value the prose states after a copula
        with a stated rounding in its clause whatever it restates ('To 3 s.f. the external resistance is 2.4 Ω.'). An ``eq`` check of the
        rounding's place against the places the value is written to (its readings), exact, at warning severity (which value the rounding
        is of is read from the prose). '= 60.4% decrease, which is 60.4% to 2 s.f.' fails (written to the tenths, the rounding names the
        units), so does 'To 3 s.f. the external resistance is 2.4 Ω.' (the tenths, against the hundredths: 2.40); '60% to 2 s.f.' and
        '2.40 Ω to 3 s.f.' hold. Before, a value restated at a stated rounding without being rounded passed: the rounding-cue check sets
        the value against the chain's within the rounding's half-width, which an unrounded value always meets."""
        seen: set[tuple[int, int]] = set()
        targets: list[tuple[Node, int, int, Fraction, str, str, str]] = []
        for r in self.relations:
            # STEM repair 11 (rule result-rounding): a chain's own result with the rounding its line states is written to that rounding too
            if r.kind in ("res", "eq") and r.outcome == "check" and r.rounding is not None and not r.finer and r.right is not None \
                    and r.right.node is not None and not (r.kind == "eq" and r.title):
                key = (r.right.start, r.right.end)
                if key not in seen:
                    seen.add(key)
                    targets.append((r.right.node, r.right.start, r.right.end, r.rounding, r.rounding_phrase, r.statement_ids[-1], r.part))
        for pv in self.prose_values:
            if (pv.start, pv.end) in seen or pv.given:
                continue
            v = value_of(pv.node)
            if v is None or v[1] is None:
                continue
            rounding = _rounding_cue(pv.before, pv.after, v[0], self._unit_words(pv, v))
            if rounding is None or not (_restating_word(pv.before) and _PROSE_HEAD_VERB_RE.search(pv.before[-28:])):
                continue
            seen.add((pv.start, pv.end))
            targets.append((pv.node, pv.start, pv.end, rounding[0], rounding[1], pv.statement_id, pv.part))
        for item, head, value_op, _start in self.stated_values:
            node = value_op.readings[0] if value_op.readings else None
            if node is None or (value_op.start, value_op.end) in seen or not isinstance(head, Sym) or item.source == "given":
                continue
            v = value_of(node)
            if v is None or v[1] is None:
                continue
            off = item.statement_start
            pv = ProseValue(item.statement_id, item.statement_index, item.part, node, value_op.start, value_op.end,
                            item.statement_text[:max(0, value_op.start - off)], item.statement_text[max(0, value_op.end - off):][:160])
            rounding = _rounding_cue(pv.before, pv.after, v[0], self._unit_words(pv, v))
            if rounding is None:
                continue
            seen.add((value_op.start, value_op.end))
            targets.append((node, value_op.start, value_op.end, rounding[0], rounding[1], item.statement_id, item.part))
        for node, a, b, h_round, phrase, sid, part in targets:
            v = value_of(node)
            if v is None or v[1] is None or h_round <= 0:
                continue
            num = v[1]
            if num.vulgar or num.power_of_ten or num.based or num.base != 10:
                continue
            place = 2 * h_round
            if num.has_point or num.scientific:
                places = [Fraction(10) ** num.last_place]
            else:
                places = [Fraction(10) ** k for k in range(0, num.trailing_zeros + 1)]
            right = Operand(tuple(_exact_place(p, a) for p in places), a, b)
            self.add(kind="eq", outcome="check", statement_ids=(sid,), start=a, end=b, op="=", left=Operand((_exact_place(place, a),), a, b),
                     right=right, part=part, title="the place the rounding the prose states names, against the place the value is written to",
                     reason=f"the value {num.text} is written to the place of {', or '.join(_show_place(p) for p in places)}; the prose states '{phrase}', "
                            f"which rounds it to the place of {_show_place(place)} (rule rounded-digits)")

    def _labelled_values(self) -> list[tuple[dict, frozenset[str]]]:
        """Each final value of a chain with the words that name its quantity (rule named-change): a label in brackets right
        after the value ('R = 2.4 Ω (the external resistance)'), the statement's label before its chain ('Total resistance of
        the circuit, including the internal resistance: R + r = … = 2.9 Ω'), a word label the chain itself carries
        ('Percentage decrease = …'), and, for the value that answers its part's question, the request's question of that part ('(b)
        Calculate the current in the battery.'). STEM repair 9 (rule part-answer, :meth:`_part_answers`): that value is the last one
        the part computes that is no check of a value and names no other quantity; before, it was the last one whatever it was, so a
        correct check or side line at the end of a part ('As a check, ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V.', 'The lost volts are
        4.14 A × 0.50 Ω = 2.07 V.') took the question's words, and a change stated later from the part's result ('… rises, from 9.9 V
        to 10.7 V') was set against it (a false INT-SUBJ-004 on correct working)."""
        items_of = self._items_by_statement()
        questions = _part_questions(self.request.text)
        answers = self._part_answers(questions, items_of)
        out: list[tuple[dict, frozenset[str]]] = []
        for fv in self.final_values:
            words = set(self._own_label_words(fv, items_of))
            if answers.get(fv["part"]) is fv and fv["part"] in questions:
                words |= set(_label_words(questions[fv["part"]]))
            if words:
                out.append((fv, frozenset(words)))
        return out

    def _items_by_statement(self) -> dict[str, list[MathItem]]:
        items_of: dict[str, list[MathItem]] = {}
        for it in self.items:
            items_of.setdefault(it.statement_id, []).append(it)
        return items_of

    @staticmethod
    def _item_of(fv: dict, items_of: dict[str, list[MathItem]]) -> Optional[MathItem]:
        """The math item that holds the final value ``fv``, else None."""
        op = fv["operand"]
        return next((it for it in items_of.get(fv["sid"], []) if it.start <= op.start <= it.end or it.start <= op.end <= it.end), None)

    def _own_label_words(self, fv: dict, items_of: dict[str, list[MathItem]]) -> list[str]:
        """The label words a final value's own line gives it (rule named-change): a label in brackets right after the value, the
        statement's label before a colon ahead of its chain, a word label the chain carries."""
        words: list[str] = []
        op = fv["operand"]
        for it in items_of.get(fv["sid"], []):
            if it.start <= op.start <= it.end or it.start <= op.end <= it.end:
                after = it.statement_text[max(0, op.end - it.statement_start):][:80]
                m = _BRACKET_LABEL_RE.match(after)
                if m:
                    words += _label_words(m.group(1))
                head = it.statement_text[:max(0, it.start - it.statement_start)]
                if head.rstrip().endswith(":"):
                    words += _label_words(head)
                if it.label:
                    words += _label_words(it.label)
        return words

    def _check_cue(self, it: MathItem) -> bool:
        """Rule ``part-answer`` (STEM repair 9): the item's line says it checks a value ('As a check, ε = …', 'Check: 4.1 A × 2.9 Ω =
        11.9 V', '… = 12.0 V, which checks'): the cue in the statement's prose right before the item, or, for the statement's last item,
        right after it."""
        if _CHECK_CUE_RE.search(it.gap_before[-80:]):
            return True
        if any(o.statement_id == it.statement_id and o.start > it.start for o in self.items):
            return False
        return bool(_CHECK_CUE_RE.search(it.statement_text[max(0, it.end - it.statement_start):][:80]))

    def _part_answers(self, questions: dict[str, str], items_of: dict[str, list[MathItem]]) -> dict[str, dict]:
        """Rule ``part-answer`` (STEM repair 9): the final value that answers each part's question, whose words label it: the last value
        the part computes, leaving out, from the end of the part back,
        * a line that says it checks a value (:meth:`_check_cue`);
        * a line whose own words name another quantity: the words of its label (:meth:`_own_label_words`) or of the prose naming its
          run's value right before it (rule bound-relation's reading, 'The lost volts are …'), when they neither hold every word of the
          question's quantity (its name up to its first preposition: 'terminal potential difference' of '(c) Calculate the terminal
          potential difference of the battery.') nor are all words of the question;
        * a line that gives its value to a quantity the request names (rule named-result, :meth:`_request_quantity`: 'So the emf is …',
          or a symbol the answer substituted the request's value for, 'ε = …') that the part's question does not name.
        A part with no such value has none (the question's words then label nothing). A part with no question keeps its last value."""
        by_part: dict[str, list[dict]] = {}
        for fv in self.final_values:
            if fv.get("computed", True) and fv["part"]:
                by_part.setdefault(fv["part"], []).append(fv)
        out: dict[str, dict] = {}
        for part, fvs in by_part.items():
            q = questions.get(part)
            if q is None:
                out[part] = fvs[-1]
                continue
            q_words = {_singular(w) for w in _label_words(q)}
            q_head = {_singular(w) for w in _question_head(q)}
            for fv in reversed(fvs):
                if not self._names_other_quantity(fv, items_of, q_words, q_head):
                    out[part] = fv
                    break
        return out

    def _names_other_quantity(self, fv: dict, items_of: dict[str, list[MathItem]], q_words: set[str], q_head: set[str]) -> bool:
        it = self._item_of(fv, items_of)
        if it is not None and self._check_cue(it):
            return True
        own = {_singular(w) for w in self._own_label_words(fv, items_of)}
        if it is not None:
            own |= {_singular(w) for w in self._prose_head(it, it.start).split() if len(w) >= 3}
        own -= _LABEL_STOP
        if own and not (q_head and q_head <= own) and not own <= q_words:
            return True
        tie = self._request_quantity(fv, items_of)
        return tie is not None and not set(tie[3]) <= q_words

    def _request_quantity(self, fv: dict, items_of: dict[str, list[MathItem]]) -> Optional[tuple[str, tuple[Binding, ...], str, tuple[str, ...]]]:
        """Rule ``named-result`` (STEM repair 9): the quantity the request names whose value the final value ``fv`` gives, as ``(its name,
        the request's values of it, how the answer names it, the request's words)``, else None. The answer names the quantity
        * by the prose right before the value's run (rule bound-relation's reading: 'So the internal resistance is (12 V + 9.93 V)/4.14 A =
          5.3 Ω.' names 'internal resistance'), or by its label's first words, up to a preposition or a comma ('Internal resistance: r =
          …'): the request's quantity whose every word the name holds, as rule named-given matches a prose value;
        * by its lone symbol, when the symbol has no value of its own before the line (no binding in the answer, none in the request) and
          every value the answer substituted for it before the line is the request's value of one named quantity ('V = 12 V − (4.14 A ×
          0.50 Ω)' put the request's 0.50 ohm for r, so 'r = … = 5.3 Ω' gives the internal resistance a value).
        Only a value with a unit is read, against the request's values of its dimension (a bare number names no quantity of its own)."""
        v = value_of(fv["node"])
        if v is None or v[1] is None or v[2] is None or v[2].unknown or v[2].dim is None or v[3]:
            return None
        named = [(q, "request") for q in self.request.named_quantities] + [(q, "supplied") for q in self.request.supplied_named]
        if not named:
            return None

        def candidates(words: set[str]) -> list[tuple[Binding, tuple[str, ...]]]:
            found = []
            for (qnode, a0, b0, qwords), source in named:
                qv = value_of(qnode)
                if qv is None or qv[1] is None or qv[2] is None or qv[2].dim is None or not qwords or not set(qwords) <= words \
                        or not qv[2].dim.same_physical(v[2].dim):
                    continue
                found.append((Binding(" ".join(qwords), qv[0], qv[1], qv[2], source, source, a0, b0, wrapper=qv[3]), tuple(qwords)))
            return found

        it = self._item_of(fv, items_of)
        name: set[str] = set()
        how = ""
        if it is not None:
            name = set(self._prose_head(it, it.start).split())
            how = "words" if name else ""
        if not name:
            first = self._own_label_head(fv, items_of)
            if first:
                name, how = set(first), "label"
        if name:
            found = candidates({_singular(w) for w in name} | name)
            if not found:
                return None
            qwords = found[0][1]
            shown = " ".join(sorted(set().union(*(set(b.symbol.split()) for b, _w in found))))
            return shown, tuple(b for b, _w in found[:8]), how, qwords
        sym = fv.get("symbol") or ""
        if not sym:
            return None
        order = fv["order"]
        if any(b.source == "request" or self.order.get(b.statement_id, 10 ** 9) < order for b in self.scope.bindings.get(sym, ())):
            return None  # the symbol has a value of its own before the line: it is the answer's own quantity
        subs = [b for b in self.scope.substitutions.get(sym, ()) if self.order.get(b.statement_id, 10 ** 9) < order]
        if not subs:
            return None
        tied: Optional[list[tuple[Binding, tuple[str, ...]]]] = None
        for (qnode, a0, b0, qwords), source in named:
            qv = value_of(qnode)
            if qv is None or qv[1] is None or qv[2] is None or qv[2].dim is None or not qwords or not qv[2].dim.same_physical(v[2].dim):
                continue
            qb = Binding(" ".join(qwords), qv[0], qv[1], qv[2], source, source, a0, b0, wrapper=qv[3])
            if all(s.unit is not None and s.value == qb.value and " ".join(s.unit.text.split()) == " ".join(qv[2].text.split())
                   or (s.si is not None and s.si == qb.si) for s in subs):
                tied = (tied or []) + [(qb, tuple(qwords))]
        if not tied or len({(b.value, b.unit.text if b.unit else "") for b, _w in tied}) != 1:
            return None
        qwords = tied[0][1]
        shown = " ".join(sorted(set().union(*(set(b.symbol.split()) for b, _w in tied))))
        return shown, tuple(b for b, _w in tied[:8]), f"symbol {sym}", qwords

    def _own_label_head(self, fv: dict, items_of: dict[str, list[MathItem]]) -> list[str]:
        """Rule named-result (STEM repair 9): the first words of a final value's own label (its bracketed label, the statement's label
        before a colon, its word label), up to a preposition or a comma: the quantity the label names ('Total resistance of the
        circuit, including the internal resistance:' names 'total resistance', never the internal resistance it includes)."""
        op = fv["operand"]
        for it in items_of.get(fv["sid"], []):
            if not (it.start <= op.start <= it.end or it.start <= op.end <= it.end):
                continue
            after = it.statement_text[max(0, op.end - it.statement_start):][:80]
            m = _BRACKET_LABEL_RE.match(after)
            texts = [m.group(1)] if m else []
            head = it.statement_text[:max(0, it.start - it.statement_start)]
            if head.rstrip().endswith(":"):
                texts.append(head.rstrip()[:-1])
            if it.label:
                texts.append(it.label)
            for t in texts:
                words = _label_head_words(t)
                if words:
                    return words
        return []

    def _named_changes(self) -> None:
        """Rule ``named-change`` (STEM repair 1): a value the prose gives as the start of a change of a quantity it names ("The
        external resistance rises from 2.4 Ω to 4.0 Ω") is that quantity's value before the change, so it restates the value
        the answer stated for the quantity earlier: the final value of a chain whose label words hold every word of the
        quantity's name ('R = 2.4 Ω (the external resistance)'). A ``res`` check at warning severity (the quantity is matched
        by its words, a reading the answer did not state), naming both statements; nothing when no earlier value, or more
        than one, carries the name with the same dimension. The value after the change is never checked. STEM repair 10: nor a value
        the change states under a condition of its own ('The corrected rate falls from 1131 counts min⁻¹ at 4 h to …', after the corrected
        count rate at 32 h was computed): the quantity's value under another condition is another value (it was failed against the 32 h
        one); rule condition-result sets values under one condition against each other."""
        if not self.prose_values or not self.final_values:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind == "res"}
        labelled: Optional[list[tuple[dict, frozenset[str]]]] = None
        for pv in self.prose_values:
            if (pv.start, pv.end) in planned:
                continue
            tail = pv.before[-120:]
            m = _CHANGE_FROM_RE.search(tail)
            if m is None:
                continue
            v = value_of(pv.node)
            if v is None or v[2] is None or v[2].dim is None:
                continue
            cond = _TRAILING_CONDITION_RE.match(self.text[pv.end:pv.end + 60])
            if cond is not None and _condition_si(cond.group("num"), cond.group("unit")) is not None:
                continue  # STEM repair 10: the value the change starts from is stated under a condition of its own
            name = _changed_quantity(tail[:m.start()])
            if not name:
                continue
            if labelled is None:
                labelled = self._labelled_values()
            cands = []
            for fv, words in labelled:
                if fv["order"] >= pv.statement_index or not set(name) <= words:
                    continue
                fvv = value_of(fv["node"])
                if fvv is None or fvv[2] is None or fvv[2].dim is None or not fvv[2].dim.same_physical(v[2].dim):
                    continue
                cands.append(fv)
            if not cands or len({(value_of(c["node"])[0], value_of(c["node"])[2].text) for c in cands}) != 1:
                continue
            best = cands[-1]
            shown = " ".join(name)
            self.add(kind="res", outcome="check", statement_ids=tuple(dict.fromkeys((best["sid"], pv.statement_id))), start=pv.start, end=pv.end, op="=",
                     left=best["operand"], right=Operand((pv.node,), pv.start, pv.end), part=pv.part, named=shown,
                     reason=f"the value the prose gives for the {shown} before the change it states, against the value stated for it in {best['sid']} "
                            f"(matched by its words: rule named-change)")

    def _changed_values(self) -> None:
        """Rule ``changed-value`` (STEM repair 4): the value the prose gives a quantity at the end of a change it states ('the current from
        the cell falls, from 4.1 A to 2.7 A', 'the current falls to 2.7 A', 'the current becomes 2.7 A', 'the current is now 2.7 A') is the
        quantity's new value. When the quantity is matched by its words to one symbol the answer computed earlier (the final value of a
        chain that gives that symbol a value, whose label words hold every word of the name, of the same dimension: rule named-change's
        reading), a substitution stated after the change, in its statement or anywhere in its part may take the new value, as it takes a
        binding of the symbol (``Scope.changes``); one in an earlier part never does.
        Before, such a substitution in a later part was set against the symbol's earlier values only, and correct working failed
        (INT-SUBJ-001: 'V = 12 V − 2.7 A × 0.50 Ω = 10.65 V' after 'falls, from 4.1 A to 2.7 A'). The value itself is not checked (the
        prose computes it, D31), it never becomes a binding of the scope (no rebinding note, no carried value, no premise of its own
        check), and nothing is recorded when the name fits no symbol, or several."""
        if not self.prose_values or not self.final_values:
            return
        labelled: Optional[list[tuple[dict, frozenset[str]]]] = None
        for pv in self.prose_values:
            tail = pv.before[-160:]
            m = _CHANGE_TO_RE.search(tail)
            if m is None:
                continue
            v = value_of(pv.node)
            if v is None or v[1] is None or v[2] is None or v[2].dim is None or v[2].unknown:
                continue
            name = _changed_quantity(tail[:m.start()])
            if not name:
                continue
            if labelled is None:
                labelled = self._labelled_values()
            symbols_found: set[str] = set()
            for fv, words in labelled:
                if fv["order"] >= pv.statement_index or not set(name) <= words or not fv.get("symbol"):
                    continue
                fvv = value_of(fv["node"])
                if fvv is None or fvv[2] is None or fvv[2].dim is None or not fvv[2].dim.same_physical(v[2].dim):
                    continue
                symbols_found.add(fv["symbol"])
            if len(symbols_found) != 1:
                continue
            sym = symbols_found.pop()
            if not self.scope.bindings.get(sym):
                continue
            self.scope.add_change(Binding(sym, v[0], v[1], v[2], "change", pv.statement_id, pv.start, pv.end, wrapper=v[3]))

    def _table_values(self) -> None:
        """Rule ``table-data`` (STEM repair 1): a value the prose gives from the request's supplied table is set against the
        table's cells: a change between two rows ("between 25 °C and 30 °C, an increase of 22 mm³ per g per hour": the difference
        of the two rows' cells, its direction by the word), and a value at a row ("from 18 mm³ per g per hour at 10 °C to 92 mm³
        per g per hour at 35 °C"). The rows are named by their key (a number with the key column's unit, or a site's letter) and
        the column is the table's only column of numbers, or the one whose name the clause states. A ``giv`` check at warning
        severity (which rows and which column the prose means is a reading); nothing when a row, the column or the unit is not
        read unambiguously. STEM repair 10: the clause is the value's own statement, never a 200-character window across statements,
        and a clause that names a processed quantity the column's name does not ('The corrected rate falls from 1131 counts min⁻¹ at 4 h
        to 566 counts min⁻¹ at 12 h.': :func:`_names_processed`) is not set against the raw column (it failed against 1151 and 586)."""
        if not self.request.tables or not self.text or not self.prose_values:
            return
        by_start = {pv.start: pv for pv in self.prose_values}
        planned = {(r.start, r.end) for r in self.relations if r.kind in ("res", "giv")}
        for pv in self.prose_values:
            if (pv.start, pv.end) in planned:
                continue
            v = value_of(pv.node)
            if v is None or v[1] is None:
                continue
            # STEM repair 10: the words around the value are its own statement's (its prose before it, and after it to the statement's
            # end), never a neighbouring statement's: a statement before the line that named another column left the line unread (two
            # columns named), and one that named a column could have chosen the line's
            st_start = max(0, pv.start - len(pv.before)) if pv.before else pv.start
            window = self.text[st_start:pv.start]
            after = self.text[pv.end:pv.end + len(pv.after)] if pv.after else ""
            change = _TABLE_CHANGE_BEFORE_RE.search(window)
            if change is not None:
                self._table_check(pv, v, change, window + self.text[pv.start:pv.end] + after[:80], keys=(change, "k1", "k2"), direction=change.group("dir"))
                continue
            at = _TABLE_FROM_AT_RE.match(after) if _FROM_END_RE.search(window[-12:]) else None
            if at is not None:
                clause = window[-160:] + self.text[pv.start:pv.end] + after[:at.end()]
                self._table_check(pv, v, at, clause, keys=(at, "k1", None))
                b_pv = by_start.get(pv.end + at.start("b"))
                if b_pv is not None and (b_pv.start, b_pv.end) not in planned:
                    bv = value_of(b_pv.node)
                    if bv is not None and bv[1] is not None:
                        self._table_check(b_pv, bv, at, clause, keys=(at, "k2", None))
                        planned.add((b_pv.start, b_pv.end))

    def _row_values(self) -> None:
        """Rule ``row-value`` (STEM repair 4): a value a statement or the prose gives at a row of a supplied table, named by its key (a
        site's letter, or a number with the key column's unit), in a column its words name, is set against that cell: 'Dissolved oxygen
        at site C = 3.8 g dm⁻³.' (the run 'C = …' after 'at site' names the row, not a symbol's value only), 'The nitrate at E is 4.1
        mg dm⁻³.', 'nitrate at E (2.3 mg dm⁻³)', 'At site C, dissolved oxygen is 3.8 mg dm⁻³.', '… at C (2.0 km), where it reaches 3.8 mg
        dm⁻³' (the quantity the sentence names before the row), 'site A has the least nitrate (1.2 mg dm⁻³)', and the same with a
        number for a row ('The uptake at 30 °C is 80 mm³ per g per hour.'). A ``giv`` check against the cell taken as written, in SI when
        the value and the column's header carry units of one dimension, at warning severity (which row and which column the statement
        means is a reading). Nothing is planned unless the row and exactly one column are read: the column every word of whose name the
        phrase holds, or the table's only column of numbers when the value's unit fits it. Before, only a Given, a value at a numbered
        row written '=' and a change or a range between two rows were read, so a value at a site restated in another unit, or another
        site's value, went unchecked."""
        if not self.request.tables or not self.text:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind in ("res", "giv", "cnv")}
        given_sids = {it.statement_id for it in self.items if it.source == "given"}
        lettered = any(_lettered(t) for t in self.request.tables)
        if lettered:
            # '<column> at site C = 3.8 g dm⁻³': a run that states a value for a site's letter
            for rel in list(self.relations):
                if rel.kind != "binding" or rel.outcome != "binding" or rel.left is None or rel.right is None or set(rel.statement_ids) & given_sids:
                    continue
                head, node = rel.left.node, rel.right.node
                if not isinstance(head, Sym) or len(head.name) != 1 or not head.name.isupper() or node is None or not is_value(node):
                    continue
                if (rel.right.start, rel.right.end) in planned:
                    continue
                item = next((it for it in self.items if it.statement_id == rel.statement_ids[-1] and it.start <= rel.start <= it.end), None)
                if item is None or not _ROW_RUN_BEFORE_RE.search(item.gap_before[-40:]):
                    continue
                phrase = _clause_tail(item.gap_before)
                if self._row_check(head.name, None, node, rel.right.start, rel.right.end, phrase, rel.statement_ids[-1], rel.part):
                    planned.add((rel.right.start, rel.right.end))
        for pv in self.prose_values:
            if (pv.start, pv.end) in planned:
                continue
            v = value_of(pv.node)
            if v is None or v[1] is None:
                continue
            head, tail = self._value_clause(pv)
            if _ROW_COMPARE_AFTER_RE.match(tail):
                continue  # STEM repair 10: 'Dissolved oxygen at site C is 5.8 mg dm⁻³ lower than at A.' states a difference, no cell
            if _unstated(head, tail):
                continue  # STEM repair 10: 'If nitrate at site B fell to 4.0 mg dm⁻³, …' states no value of the row
            window = self.text[max(0, pv.start - 200):pv.start]
            for pattern in _ROW_PROSE_RES:
                m = pattern.search(window)
                if m is None:
                    continue
                key, unit = m.group("k") or m.groupdict().get("kn") or "", (m.groupdict().get("u") or "").strip()
                if not key:
                    continue
                col = m.groupdict().get("col") or ""
                if not col:
                    # '… greatest at C (2.0 km), where it reaches …': the quantity the sentence names before the row
                    st_start = max(0, pv.start - (len(pv.before) if pv.before else 0))
                    col = self.text[st_start:max(st_start, pv.start - len(window) + m.start())]
                if self._row_check(key, unit, pv.node, pv.start, pv.end, col, pv.statement_id, pv.part, phrase_only=bool(m.groupdict().get("col")),
                                   clause=head + " " + tail):
                    planned.add((pv.start, pv.end))
                break
        # STEM repair 10: the shapes below read a numbered row too ('a measured count rate of 568 counts min⁻¹ at 12 h'), and the clause
        # reading takes what every shape leaves
        self._row_values_more(planned, given_sids)
        self._row_values_clause(planned)

    def _row_values_more(self, planned: set[tuple[int, int]], given_sids: set[str]) -> None:
        """Rule row-value (STEM repair 10): the shapes of a value at a site's row the reading above left unread, each with its column
        named as the rule reads it (every word of its name, its counted quantity, or its counted quantity's last word): the value right
        after the clause's subject with the column after it ('Site A has 43 mayfly nymphs per kick sample.', 'Site A has 2.1 mg dm⁻³ of
        nitrate.'); a column joined to the clause's first ('site A has the least nitrate (1.2 mg dm⁻³) and the most nymphs (34)'); a count
        the clause leaves its column out of ('while site B has the most nitrate (8.4 mg dm⁻³) and only 9': the table's only column with no
        unit); the column before 'of' and the row after the value ('a nitrate concentration of 6.9 mg dm⁻³ at site C'); the column and the
        row after the value ('There were 9 mayfly nymphs at site B.'); and a run labelled by the column after the row ('At site A, mayfly
        nymphs = 43.'). Before, each had neither a check nor an ST code, while D31 said a value at a site's row is read. Within its own
        statement only, never across statements; nothing when the row or the column is not read unambiguously. The shapes that name the
        row after 'at', 'for' or 'in' read a numbered row too ('a measured count rate of 568 counts min⁻¹ at 12 h', 'At t = 12 h, measured
        count rate = 568 counts min⁻¹'), a table keyed by numbers having had only the shapes of :data:`_ROW_PROSE_RES`."""
        for rel in list(self.relations):
            # 'At site A, mayfly nymphs = 43.': a run whose label names the column, after the row
            if rel.kind not in ("label", "binding") or rel.outcome != "binding" or rel.condition is not None or rel.left is None or rel.right is None \
                    or set(rel.statement_ids) & given_sids:
                continue
            head, node = rel.left.node, rel.right.node
            if not isinstance(head, Sym) or node is None or not is_value(node) or (rel.right.start, rel.right.end) in planned:
                continue
            item = next((it for it in self.items if it.statement_id == rel.statement_ids[-1] and it.start <= rel.start <= it.end), None)
            # the statement's text before the run (STEM repair 10: not only the prose after the span before it, which leaves out a row
            # written as a quantity, 'At 12 h, …')
            gap = self.text[max(item.statement_start, item.start - 200, 0):item.start].rstrip() if item is not None else ""
            name = head.name
            if head.kind == "label":
                if gap.lower().endswith(head.name.lower()):
                    gap = gap[:len(gap) - len(head.name)]  # the label is the prose right before the run ('At site A, mayfly nymphs = 43')
            elif len(head.name) >= 3 and head.name.isalpha() and head.name.islower():
                # STEM repair 10: 'At 12 h, measured count rate = 568 counts min⁻¹.': the run binds the label's last word ('rate'); the words of
                # the label before it are the prose right before the run
                lead = re.search(r"(?:[A-Za-z][A-Za-z’'\-]*\s+){1,4}$", gap + " ")
                if lead is None:
                    continue
                name = (lead.group(0) + head.name).strip()
                gap = gap[:lead.start()]
            else:
                continue
            m = _ROW_AT_LABEL_RE.search(gap[-48:]) if gap else None
            if m is not None and self._row_check(*_row_key_of(m), node, rel.right.start, rel.right.end, name, rel.statement_ids[-1], rel.part):
                planned.add((rel.right.start, rel.right.end))
        for pv in self.prose_values:
            if (pv.start, pv.end) in planned:
                continue
            v = value_of(pv.node)
            if v is None or v[1] is None:
                continue
            head, tail = self._value_clause(pv)
            if _ROW_COMPARE_AFTER_RE.match(tail):
                continue  # a value followed by a comparison or an operation ('7 times that at A') is no cell
            if _unstated(head, tail):
                continue  # a value under a condition, a hypothesis, a target, a bound or a modal verb is no value of the row
            before = self.text[max(0, pv.start - len(pv.before)):pv.start] if pv.before else ""
            after = pv.after
            raw_after = self.text[pv.end:pv.end + len(pv.after)] if pv.after else ""  # a numbered row's key is a quantity, masked in the prose
            found: Optional[tuple[str, Optional[str], str, bool]] = None  # (row key, its unit, the phrase naming the column, a bare count)
            m = _ROW_HAS_VALUE_RE.search(before[-60:])
            if m is not None:
                tail = re.split(r"[.,;:()\[\]]|\b(?:and|but|while|whereas|so|which|than|against)\b", after, maxsplit=1)[0]
                if re.search(r"[A-Za-z]{3}", tail):
                    found = (m.group("k"), None, tail, False)
            if found is None:
                m = _ROW_HAS_AND_RE.search(before[-200:])
                if m is not None:
                    found = (m.group("k"), None, m.group("col"), False)
            if found is None:
                m = _ROW_HAS_ELLIPSIS_RE.search(before[-200:])
                if m is not None and re.match(r"^\s*(?:\[\s*\d+(?:\s+spare)?\s*\])?\s*(?:[.,;)]|$)", after):
                    found = (m.group("k"), None, "", True)
            if found is None:
                mc, ma = _ROW_COL_OF_RE.search(before[-80:]), _ROW_AT_AFTER_RE.match(raw_after)
                if mc is not None and ma is not None:
                    found = (*_row_key_of(ma), mc.group("col"), False)
            if found is None:
                ma = _ROW_VALUE_COL_AT_RE.match(raw_after)
                if ma is not None:
                    found = (*_row_key_of(ma), ma.group("col"), False)
            if found is None:
                continue
            key, unit, phrase, bare = found
            if self._row_check(key, unit, pv.node, pv.start, pv.end, phrase, pv.statement_id, pv.part, bare_count=bare, clause=head + " " + tail):
                planned.add((pv.start, pv.end))

    def _row_check(self, key: str, unit: Optional[str], node: Node, start: int, end: int, phrase: str, sid: str, part: str, *,
                   phrase_only: bool = True, bare_count: bool = False, clause: str = "") -> bool:
        """Rule row-value: plan the ``giv`` check of the value ``node`` against the cell of the supplied table's row ``key`` in the
        column ``phrase`` names; False when the row or the column is not read unambiguously. STEM repair 10: a column is also named by
        its counted quantity's last word alone when no other column has it ('the most nymphs' for 'Mayfly nymphs per kick sample'), a
        word in the singular or the plural ('nymph', 'nymphs'), and a bare count whose column the clause leaves out (``bare_count``:
        'and only 9') is the cell of the table's only column of numbers with no unit. Nothing is planned when the phrase or the value's
        ``clause`` names a processed quantity the column's name does not (:func:`_names_processed`: 'The corrected count rate at 12 h
        is 566 counts min⁻¹.' is no cell of 'Measured count rate', and was failed against 586)."""
        v = value_of(node)
        if v is None or v[1] is None:
            return False
        words = set(re.findall(r"[a-z]+", phrase.lower()))
        words |= {w[:-1] for w in words if len(w) >= 5 and w.endswith("s")} | {w + "s" for w in words if len(w) >= 4}
        num = _key_number(key)
        for table in self.request.tables:
            if num is None and not _lettered(table):
                continue
            if num is not None:
                ku = parse_unit(unit.replace(" ", "")) if unit else None
                kc = table.columns[0].unit
                if ku is None or kc is None or ku.dim is None or kc.dim is None or not ku.dim.same_physical(kc.dim):
                    continue
            row = table.row_for(key, num)
            if row is None:
                continue
            values = table.value_columns()
            partial = False  # the column named by a part of its name only
            cols = [j for j in values if table.columns[j].words and table.columns[j].words <= words]
            low = phrase.lower()
            # STEM repair 10: columns whose names differ only by a number ('Time, trial 1 / s', 'Time, trial 2 / s') are told apart by the word
            # and number the phrase writes ('the time for trial 2')
            by_number = [j for j in values if any(re.search(rf"\b{w}\s*{d}(?!\d)", low)
                                                  for w, d in re.findall(r"([a-z]{3,})\s*(\d+)", table.columns[j].name.lower()))]
            if len(cols) > 1 and len([j for j in by_number if j in cols]) == 1:
                cols = [j for j in by_number if j in cols]
            if not cols and len(by_number) == 1 and _unit_fits(table.columns[by_number[0]].unit, v[2]):
                cols, partial = by_number, True  # 'Trial 2 at 30.0 °C took 43.0 s.'
            if not cols:
                # the quantity a column counts, the words of its name before 'per' ('Mayfly nymphs per kick sample': mayfly, nymphs)
                heads = {j: _count_head_words(table.columns[j].name) for j in values}
                cols = [j for j, hw in heads.items() if hw and hw != table.columns[j].words and hw <= words]
            if not cols and words:
                # STEM repair 10: the last word of a column's counted quantity (or of its name), when the phrase holds it and no other column's
                # name has it ('the most nymphs (34)': nymphs)
                last = {j: _column_head_word(table.columns[j].name) for j in values}
                cols = [j for j, w in last.items() if w and w in words and not any(w in table.columns[k].words for k in values if k != j)]
                partial = bool(cols)
            if not cols and len(values) == 1 and (not phrase_only or words & set(table.columns[values[0]].words)) \
                    and _unit_fits(table.columns[values[0]].unit, v[2]):
                cols, partial = values, True
            if not cols and bare_count and v[2] is None and not v[3] and v[0].denominator == 1 and v[0] >= 0:
                # STEM repair 10: 'site B has the most nitrate (8.4 mg dm⁻³) and only 9': a bare count, the table's only column with no unit
                cols = [j for j in values if not table.columns[j].unit_text and table.columns[j].unit is None]
            if len(cols) != 1:
                continue
            col = table.columns[cols[0]]
            if _names_processed(phrase + " " + clause, col) or (partial and not _modifiers_fit(phrase, col)):
                continue
            # the value is the column's quantity only when its unit, or the unit written right after a bare number ('at C (2.0 km)': a
            # distance, not the dissolved oxygen), has the column's dimension
            unit_of_value = v[2] if v[2] is not None else _unit_written_after(self.text, end)
            if unit_of_value is not None and col.unit is not None and (unit_of_value.dim is None or col.unit.dim is None
                                                                       or not unit_of_value.dim.same_physical(col.unit.dim)):
                continue
            if unit_of_value is not None and col.unit is None:
                continue
            cell = table.rows[row][cols[0]][1]
            if cell is None:
                continue
            cand = Binding(col.name[:40] or "table", cell.value, cell, _cell_unit(col.unit, v[2]), "request", "request", 0, 0)
            self.add(kind="giv", outcome="check", statement_ids=(sid,), start=start, end=end, op="=", right=Operand((node,), start, end),
                     left=Operand((Sym(col.name[:40] or "table", start=start, end=start),), start, start), candidates=(cand,), part=part,
                     exact_candidates=True, named=col.name[:60],
                     reason=f"the value the statement gives at the supplied table's row {table.rows[row][0][0]} against {col.name} there ({cell.text}): "
                            "the supplied data, taken as written (rule table-data, rule row-value)")
            return True
        return False

    def _value_clause(self, pv: ProseValue) -> tuple[str, str]:
        """Rule row-value (STEM repair 10): a prose value's clause, bounded by its statement: the text from the clause's start to the
        value, and from the value to the clause's end (:data:`_VALUE_CLAUSE_START_RE`, :data:`_VALUE_CLAUSE_END_RE`)."""
        st_start = max(0, pv.start - len(pv.before)) if pv.before else pv.start
        before = self.text[st_start:pv.start]
        after = self.text[pv.end:pv.end + len(pv.after)] if pv.after else ""
        cut = 0
        for m in _VALUE_CLAUSE_START_RE.finditer(before):
            cut = m.end()
        m = _VALUE_CLAUSE_END_RE.search(after)
        return before[cut:], (after[:m.start()] if m is not None else after)

    def _clause_rows(self, clause: str, lettered: list, numbered: list) -> set[tuple[str, Optional[str]]]:
        """Rule row-value, the clause reading (STEM repair 10): the rows ``clause`` names, as (key, unit): each site's letter of a lettered
        table ('site C', 'sites B and C', 'at C', "C's", 'C has'), and each number written with a unit of a numbered table's key dimension
        ('12 h', 't = 12 h'); a bare number listed before another ('8 and 16 h') makes the rows more than one."""
        out: set[tuple[str, Optional[str]]] = set()
        if lettered:
            for m in _ROW_LETTER_MENTION_RE.finditer(clause):
                if m.group("a"):
                    out.update((x, None) for x in re.findall(r"[A-Z]", m.group("a")))
                elif m.group("b") or m.group("c"):
                    out.add((m.group("b") or m.group("c"), None))
                elif m.group("d") and any(t.row_for(m.group("d"), None) is not None for t in lettered):
                    out.add((m.group("d"), None))
        if numbered:
            for m in _ROW_NUMBER_MENTION_RE.finditer(clause):
                u = parse_unit(m.group("u").replace(" ", ""))
                if u is not None and u.dim is not None and any(t.columns[0].unit.dim.same_physical(u.dim) for t in numbered):
                    out.add((m.group("kn"), m.group("u").strip()))
            if _ROW_NUMBER_LIST_RE.search(clause):
                out.add(("", None))  # a list of numbers: never one row
        return out

    def _row_values_clause(self, planned: set[tuple[int, int]]) -> None:
        """Rule row-value (STEM repair 10), the clause reading: a prose value every shape above leaves unread is set against a supplied
        table's cell when its own clause (bounded by its statement: :meth:`_value_clause`) states it, names exactly one row and names the
        column as rule row-value reads a column, in any order: the value stated right after 'is', 'was', '=', 'has', 'of', 'reaches', 'falls
        to', an opening bracket or an apposition's comma (an adverb such as 'only' or 'about' between), the row a site's letter ('site C',
        'at C', "C's") or a number with a numbered table's key unit ('at 12 h', 'at t = 12 h'). 'Dissolved oxygen was 3.9 mg dm⁻³ at site C.',
        'At site C dissolved oxygen is 3.9 mg dm⁻³.', "Site C's dissolved oxygen is only 3.9 mg dm⁻³.", 'The dissolved oxygen of site C is
        3.9 mg dm⁻³.', 'Dissolved oxygen at site C, 3.9 mg dm⁻³, is the lowest.', 'The measured count rate was 568 counts min⁻¹ at 12 h.'
        each had neither a check nor an ST code: the shapes above fix the order of the row, the column and the verb, and a statement
        written in another order escaped them. A clause that compares, or states a change, a range, a ratio, a share or a processed quantity
        (:data:`_ROW_CLAUSE_SKIP_RE`, :func:`_names_processed`), and a value followed by a comparison or an operation, are not read."""
        lettered = [t for t in self.request.tables if _lettered(t)]
        numbered = [t for t in self.request.tables if not _lettered(t) and t.columns and t.columns[0].unit is not None
                    and t.columns[0].unit.dim is not None]
        if not lettered and not numbered:
            return
        for pv in self.prose_values:
            if (pv.start, pv.end) in planned:
                continue
            v = value_of(pv.node)
            if v is None or v[1] is None or v[3]:
                continue
            head, tail = self._value_clause(pv)
            lead = _ROW_LEAD_ADVERBS_RE.sub("", head)
            states = _ROW_STATES_RE.search(lead)
            if states is None:
                continue
            if lead[states.start():].strip() == "," and not re.match(r"\s*[,)]", tail):
                continue  # a comma states the value only as an apposition, which a comma or a bracket closes
            if _ROW_CLAUSE_SKIP_RE.search(lead[:states.start()] + " " + tail) or _ROW_COMPARE_AFTER_RE.match(tail) or _unstated(head, tail):
                continue
            clause = head + " " + tail
            rows = self._clause_rows(clause, lettered, numbered)
            if len(rows) != 1:
                continue
            key, unit = next(iter(rows))
            if key and self._row_check(key, unit, pv.node, pv.start, pv.end, clause, pv.statement_id, pv.part, clause=clause):
                planned.add((pv.start, pv.end))

    def _condition_results(self) -> None:
        """Rule ``condition-result`` (STEM repair 10): a value the answer computes for a symbol under a condition it states (right after
        the value, '… = 1597 counts min⁻¹ at 32 h'; before the run, 'At t = 32 h, C = …'; or, for its part's answer, the one condition the
        part's question states, '(d) Predict the corrected count rate at t = 32 h.') is set against the value it computed for the same
        symbol under the same condition before: a ``res`` check (R8, τ = 0) at warning severity (that the two values are of one quantity is
        a reading). A wrong law whose arithmetic is right ('Using C = C₀ − λt, C = 1600 − 0.087 × 32 = 1597 counts min⁻¹ at 32 h.') had held
        its substitution and its arithmetic, with only an info note that C took another value, while part (d) had computed 100 counts
        min⁻¹ at 32 h. Values of two dimensions, two conditions, a condition of no unit and a symbol with no earlier value under its
        condition are not read."""
        if len(self.final_values) < 2 or not self.text:
            return
        items_of = self._items_by_statement()
        questions = _part_questions(self.request.text)
        answers = self._part_answers(questions, items_of)
        q_cond: dict[str, tuple[Fraction, Dimension, str]] = {}
        for part, q in questions.items():
            hits = [c for c in (_condition_si(m.group("num"), m.group("unit")) for m in _QUESTION_CONDITION_RE.finditer(q[:600])) if c is not None]
            if len(hits) == 1:
                q_cond[part] = hits[0]
        planned = {(r.start, r.end) for r in self.relations if r.kind == "res"}
        seen: list[tuple[dict, tuple[Fraction, Dimension, str]]] = []
        for fv in self.final_values:
            if not fv.get("symbol") or not fv.get("computed", True):
                continue
            cond: Optional[tuple[Fraction, Dimension, str]] = None
            it = self._item_of(fv, items_of)
            op = fv["operand"]
            if it is not None:
                m = _TRAILING_CONDITION_RE.match(self.text[op.end:min(it.statement_end, op.end + 60)])
                if m is not None:
                    cond = _condition_si(m.group("num"), m.group("unit"))
            if cond is None:
                for rsid, cnode, _start, rend in self._computed_at_runs:
                    cv = value_of(cnode) if cnode is not None else None
                    if rsid == fv["sid"] and rend == op.end and cv is not None and cv[1] is not None and cv[2] is not None:
                        cond = _condition_si(cv[1].text, cv[2].text)
                        break
            if cond is None and it is not None:
                # 'At t = 32 h, C = …': the condition item right before the run in its statement (rule value-at's reading)
                cv = value_of(c) if (c := self._condition_before(it)) is not None else None
                if cv is not None and cv[1] is not None and cv[2] is not None:
                    cond = _condition_si(cv[1].text, cv[2].text)
            if cond is None and answers.get(fv["part"]) is fv:
                cond = q_cond.get(fv["part"])
            if cond is None:
                continue
            v = value_of(fv["node"])
            if v is None or v[1] is None:
                continue
            prev = next((e for e, c in reversed(seen) if e["symbol"] == fv["symbol"] and c[1] == cond[1] and c[0] == cond[0]), None)
            seen.append((fv, cond))
            if prev is None or (op.start, op.end) in planned:
                continue
            pv_ = value_of(prev["node"])
            if pv_ is None or pv_[1] is None or (v[2] is None) != (pv_[2] is None) or (v[2] is not None and (v[2].dim is None or pv_[2].dim is None
                                                                                                              or not v[2].dim.same_physical(pv_[2].dim))):
                continue
            planned.add((op.start, op.end))
            self.add(kind="res", outcome="check", statement_ids=tuple(dict.fromkeys((fv["sid"], prev["sid"]))), start=op.start, end=op.end, op="=",
                     left=prev["operand"], right=op, part=fv["part"],
                     title=f"the value computed for {fv['symbol']} at {cond[2]} against the value computed for it there before",
                     reason=f"the value the line computes for {fv['symbol']} under its condition ({cond[2]}) against the value {prev['sid']} computed for "
                            f"{fv['symbol']} under the same condition (rule condition-result)")

    def _named_components(self) -> None:
        """Rule ``named-component`` (STEM repair 10): a statement that names the component whose quantity it computes by the component's
        value ('The power dissipated in the 4.0 Ω resistor is P = …', 'The current through the 6.0 Ω resistor is I = …': a value of a
        dimension before the component's noun, after 'in', 'through', 'across', 'of', 'by', 'on', 'for', 'into' or 'onto' and an article)
        and whose working, after the name, substitutes values of that dimension only from the request, none of them the component's: the
        first such value is set against the component's (a ``giv`` check at warning severity: that the working's value stands for the
        named component is a reading). 'P = (9.93 V)² / 6.0 Ω = 16.4 W' for the 4.0 Ω resistor substituted the request's other resistor and
        held, its arithmetic and its substitution both right, with neither a check nor an ST code naming it. The component must be one
        the request states, the only one of that dimension the statement names; a working that takes the component's value anywhere
        ('I = 12 V / (4.0 Ω + 0.50 Ω)'), or a value the request does not state (a total the answer computed: 'I = 12 V / 4.5 Ω'), is
        not read."""
        if not self.prose_values or not self.request.quantities:
            return
        req: list[tuple[Fraction, Fraction]] = []  # the request's values in SI, with their half-widths in SI
        for node, _a, _b in self.request.quantities:
            rv = value_of(node)
            if rv is None or rv[1] is None or rv[2] is None or rv[2].unknown or rv[2].dim is None or not rv[2].readings:
                continue
            si = si_value(rv[0], rv[2], rv[3])
            if si is not None and rv[2].readings[0].factor is not None:
                req.append((si, rv[1].half_width * abs(rv[2].readings[0].factor)))
        if not req:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind in ("giv", "res", "cnv")}
        by_sid: dict[str, list[tuple[ProseValue, tuple, str]]] = {}
        for pv in self.prose_values:
            v = value_of(pv.node)
            if v is None or v[1] is None or v[2] is None or v[2].unknown or v[2].dim is None or not v[2].readings or v[2].readings[0].factor is None:
                continue
            m = _COMPONENT_AFTER_RE.match(pv.after)
            if m is None or m.group("noun").lower() not in _COMPONENT_NOUNS or not _COMPONENT_BEFORE_RE.search(pv.before[-24:]):
                continue
            by_sid.setdefault(pv.statement_id, []).append((pv, v, m.group("noun").lower()))

        def si_of(q: Quantity) -> Optional[tuple[Fraction, Fraction]]:
            if q.unit.unknown or not q.unit.readings or q.unit.readings[0].factor is None:
                return None
            si = si_value(q.number.value, q.unit, "")
            return None if si is None else (si, q.number.half_width * abs(q.unit.readings[0].factor))

        for sid, named in by_sid.items():
            for pv, v, noun in named:
                dim = v[2].dim
                if sum(1 for _q, w, _n in named if w[2].dim.same_physical(dim)) != 1:
                    continue  # two components of one dimension named: which one the working is of is not read
                c_si, c_h = si_value(v[0], v[2], v[3]), v[1].half_width * abs(v[2].readings[0].factor)
                if c_si is None or not any(abs(c_si - r_si) <= c_h + r_h for r_si, r_h in req):
                    continue  # the component is none of the request's
                leaves: list[Quantity] = []
                for it in self.items:
                    if it.statement_id != sid or it.start < pv.end:
                        continue
                    for ch in it.chains:
                        for op in ch.operands:
                            for n in (walk(op.readings[0]) if op.readings else ()):
                                if isinstance(n, Quantity) and not n.unit.unknown and n.unit.dim is not None and n.unit.dim.same_physical(dim):
                                    leaves.append(n)
                if not leaves:
                    continue
                read = [si_of(q) for q in leaves]
                if any(x is None for x in read):
                    continue
                if any(abs(x[0] - c_si) <= x[1] + c_h for x in read):
                    continue  # the working takes the component's value
                if not all(any(abs(x[0] - r_si) <= x[1] + r_h for r_si, r_h in req) for x in read):
                    continue  # a value the request does not state: something the answer computed (a total, a combination)
                leaf = leaves[0]
                if (leaf.start, leaf.end) in planned:
                    continue
                shown = " ".join(self.text[pv.start:pv.end].split())
                name = f"the {shown} {noun}"
                cand = Binding(name[:40], v[0], v[1], v[2], "statement", sid, pv.start, pv.end, wrapper=v[3])
                self.add(kind="giv", outcome="check", statement_ids=(sid,), start=leaf.start, end=leaf.end, op="=", right=Operand((leaf,), leaf.start, leaf.end),
                         left=Operand((Sym(name[:40], start=leaf.start, end=leaf.start),), leaf.start, leaf.start), candidates=(cand,), part=pv.part,
                         reason=f"the value {' '.join(self.text[leaf.start:leaf.end].split())} the working substitutes, another of the request's values, "
                                f"against {name}, the component whose quantity the statement computes (rule named-component)")
                planned.add((leaf.start, leaf.end))

    def _value_at_cells(self, words: set[str], cond: Node, value: Node, *, given: bool) -> Optional[tuple[tuple[Binding, ...], str, str]]:
        """Rule table-data for a value stated under a condition (rule value-at, STEM repair 3): the supplied table's row whose key the
        condition gives (a number with the key column's unit: 'at 30 °C', 'at t = 8 h'), in the column the quantity's name names
        (every word of a column's name: 'oxygen uptake' names 'Mean oxygen uptake'), or the table's only column of numbers. A Given
        must be set against the request or named (rule given-kinds), so when its name fits several columns or none, the row's cells
        of every column whose unit has the value's dimension are its candidates (one of them must match: 'time at 30.0 °C = 33.1 s'
        against the three trials). A prose value is read only when the row and the column are both read unambiguously. Each cell
        carries its column's unit when the header gives one the table of units reads, so a value restated in another unit is
        compared in SI. ``(candidates, what they are, the column's name)``, else None."""
        cv, wv = value_of(cond), value_of(value)
        if cv is None or wv is None or cv[1] is None:
            return None
        for table in self.request.tables:
            key = table.columns[0]
            if cv[2] is not None:
                if key.unit is None or key.unit.dim is None or cv[2].dim is None or not cv[2].dim.same_physical(key.unit.dim):
                    continue
            row = table.row_for(cv[1].text, cv[0])
            if row is None:
                continue
            values = table.value_columns()
            cols = [j for j in values if table.columns[j].words and table.columns[j].words <= words]
            if not cols and len(values) == 1:
                cols = values
            if len(cols) != 1:
                if not given:
                    continue
                cols = [j for j in (cols or values) if _unit_fits(table.columns[j].unit, wv[2])]
                if not cols:
                    continue
            cands = []
            for j in cols:
                cell = table.rows[row][j][1]
                if cell is not None:
                    cands.append(Binding(table.columns[j].name[:40] or "table", cell.value, cell, _cell_unit(table.columns[j].unit, wv[2]), "request", "request", 0, 0))
            if not cands:
                continue
            names = [table.columns[j].name for j in cols]
            what = (f"{names[0]} at the supplied table's row {table.rows[row][0][0]} ({cands[0].number.text})" if len(cands) == 1 else
                    f"the supplied table's row {table.rows[row][0][0]}, one of its cells " + ", ".join(f"{n} {c.number.text}" for n, c in zip(names, cands)) +
                    " (the name fits no single column)")
            return tuple(cands[:8]), what, names[0][:60]
        return None

    def _value_at_tables(self) -> None:
        """Rule table-data for the values a statement gives under a condition outside a Given (rule value-at, STEM repair 3: 'The
        uptake at 20 °C = 40 mm³ per g per hour'): set against the supplied table's cell at the row and in the column they name, at
        warning severity (which row and which column the statement means is a reading); nothing when either is not read
        unambiguously. Givens are set against the request by rule given-kinds."""
        if not self.request.tables:
            return
        given_sids = {it.statement_id for it in self.items if it.source == "given"}
        for rel in list(self.relations):
            if rel.kind != "label" or rel.outcome != "binding" or rel.condition is None or set(rel.statement_ids) & given_sids:
                continue
            cond, node = _first(rel.condition), _stated_value(_first(rel.right))
            if cond is None or node is None:
                continue
            found = self._value_at_cells(set(_label_head(rel)), cond, node, given=False)
            if found is None:
                continue
            cands, what, named = found
            self.add(kind="giv", outcome="check", statement_ids=rel.statement_ids, start=rel.right.start, end=rel.right.end, op="=",
                     right=Operand((node,), rel.right.start, rel.right.end), left=Operand((Sym(named[:40] or "table", start=rel.right.start, end=rel.right.start),),
                                                                                         rel.right.start, rel.right.start),
                     candidates=cands, part=rel.part, exact_candidates=True, named=named,
                     reason=f"the value the statement gives under its condition against {what}: the supplied data, taken as written (rule table-data, "
                            "rule value-at)")

    def _table_operands(self) -> None:
        """Rule ``table-operands`` (STEM repair 2): a value a line of working takes from a supplied table is a cell of the rows the
        line names ('From A to C the fall is 9.6 − 3.8 = 5.8 mg dm⁻³'), or, when the line names none, of the rows its part's question
        names ('(a) Calculate the percentage decrease in dissolved oxygen between site A and site C.'). Each numeral of the computed
        side of an arithmetic link that is a cell of the column the line or the question names (or the table's only column of numbers)
        is set against the cells of the named rows in that column, data taken as written: a ``giv`` check at warning severity (which
        rows and which column the working means is a reading). Another row's value put in its place ('(9.6 − 6.1) ÷ 9.6 × 100' for A to
        C, 6.1 being site B's) fails it. Nothing is planned when no row, or no single column, is named, or when the working takes another
        number of different cells of that column than the rows named: a line over three cells ('(18 + 27 + 40)/3 = 28.3', a mean) in a
        part whose question names two rows computes something else, over rows nobody named."""
        if not self.request.tables:
            return
        questions = _part_questions(self.request.text)
        text_of = {it.statement_id: it.statement_text for it in self.items}
        planned: set[tuple[str, Fraction]] = set()
        term_planned: set[tuple[int, int]] = set()
        for rel in list(self.relations):
            if rel.kind != "eq" or rel.outcome != "check" or rel.title or rel.left is None or rel.left.node is None:
                continue
            sid = rel.statement_ids[-1] if rel.statement_ids else ""
            stmt = text_of.get(sid, "")
            question = questions.get(rel.part, "") if rel.part else ""
            leaves = [n for n in walk(rel.left.node) if isinstance(n, (Num, Quantity))]
            if not leaves:
                continue
            for table in self.request.tables:
                line_rows = _named_rows(stmt, table)
                rows = line_rows or (_named_rows(question, table) if question else [])
                if not rows:
                    continue
                words = set(re.findall(r"[a-z]+", (stmt + " " + question).lower()))
                cols = [j for j in table.value_columns() if table.columns[j].words and table.columns[j].words <= words]
                if line_rows and len(cols) > 1:
                    # STEM repair 10: a line that names its rows and its column is read in its own column, whatever column its part's
                    # question names ('From A to D the nitrate falls by (8.4 − 4.1) ÷ 8.4 × 100' in a part asking about dissolved oxygen:
                    # the line's words named the nitrate and the question's the oxygen, two columns, so nothing was read), when the line
                    # takes a cell of that column; a line that names no rows is the question's, as before
                    line_words = set(re.findall(r"[a-z]+", stmt.lower()))
                    own = [j for j in cols if table.columns[j].words <= line_words]
                    if len(own) == 1 and any(leaf.number.value in {table.rows[r][own[0]][1].value for r in range(len(table.rows))
                                                                   if table.rows[r][own[0]][1] is not None} and leaf.number.value not in (100, 1000)
                                             for leaf in leaves):
                        cols = own
                if not cols and len(table.value_columns()) == 1:
                    cols = table.value_columns()
                if len(cols) != 1:
                    # rule row-terms (STEM repair 9): a line that takes the repeats of the one row it names ('Mean time at 30.0 °C = (33.1 s +
                    # 34.0 s + 32.5 s) ÷ 3', the row's three trial columns)
                    if len(rows) == 1 and self._row_terms(rel, sid, table, rows[0], bool(line_rows), term_planned):
                        break
                    continue
                col = cols[0]
                cells = {table.rows[r][col][1].value for r in range(len(table.rows)) if table.rows[r][col][1] is not None}
                # STEM repair 8: a named row whose cell the line states as its own value is the row of its result ('Uptake at 30 °C = 2 × 40 =
                # 80': the uptake at 30 °C computed from the uptake at 20 °C), never a row the working takes a value from (the 40 had been
                # set against the 80 there, a false INT-SUBJ-004 on correct working)
                stated = _stated_value(rel.right.node) if rel.right is not None and rel.right.node is not None else None
                sv = value_of(stated) if stated is not None and is_value(stated) else None
                if sv is not None and sv[1] is not None and not sv[3] and _unit_fits(table.columns[col].unit, sv[2]):
                    rows = [r for r in rows if table.rows[r][col][1] is None or table.rows[r][col][1].value != sv[0]]
                    if not rows:
                        continue
                # STEM repair 8 (rule value-at for a computing chain): the row a run's condition names is the row of the run's result when the
                # working takes a cell of the column and not that row's ('Uptake at 30 °C = 2 × 40 = 90': the uptake at 30 °C computed, with a
                # slip, from the 20 °C row's 40), never a row the working takes a value from (the 40 was set against the 30 °C row's 80, a
                # reading of the condition as the operands' row beside the slip's own failure)
                cond_row = self._computed_at_row(rel, sid, table)
                if cond_row is not None and cond_row in rows:
                    cond_cell = table.rows[cond_row][col][1]
                    took = {leaf.number.value for leaf in leaves if leaf.number.value in cells and leaf.number.value not in (100, 1000)}
                    if cond_cell is not None and took and cond_cell.value not in took:
                        rows = [r for r in rows if r != cond_row]
                        if not rows:
                            continue
                named = [(table.rows[r][0][0], table.rows[r][col][1]) for r in rows if table.rows[r][col][1] is not None]
                if not named:
                    continue
                taken = {leaf.number.value for leaf in leaves if leaf.number.value in cells and leaf.number.value not in (100, 1000)}
                if len(taken) < len(named):
                    # rule table-terms (STEM repair 8): a named row's value copied wrongly ('t = 12 h: 568 − 20' for the table's 586)
                    if self._table_terms(rel, sid, table, col, rows, cells, bool(line_rows), term_planned):
                        break
                    continue
                if len(taken) != len(named):
                    continue  # the working takes another number of cells than the rows named: another computation (a mean, a sum)
                for leaf in leaves:
                    v = leaf.number.value
                    if v not in cells or v in (100, 1000) or (sid, v) in planned:
                        continue
                    planned.add((sid, v))  # one check per value a line takes from the table
                    name = table.columns[col].name
                    cands = tuple(Binding(name[:40] or "table", cell.value, cell, None, "request", "request", 0, 0) for _k, cell in named)
                    shown = ", ".join(f"{k}: {cell.text}" for k, cell in named)
                    self.add(kind="giv", outcome="check", statement_ids=(sid,), start=leaf.start, end=leaf.end, op="=", right=Operand((leaf,), leaf.start, leaf.end),
                             left=Operand((Sym(name[:40] or "table", start=leaf.start, end=leaf.start),), leaf.start, leaf.start), candidates=cands[:8],
                             exact_candidates=True, named=name[:60], part=rel.part,
                             reason=f"the value {leaf.number.text} the working takes from the supplied table's {name} against the rows "
                                    f"{'the line' if _named_rows(stmt, table) else 'its part question'} names ({shown}) (rule table-operands)")
                # rule table-terms (STEM repair 8): another number the working adds to or takes from those values ('220 − 25', the background)
                self._table_terms(rel, sid, table, col, rows, cells, bool(line_rows), term_planned)
                break

    def _row_terms(self, rel: Relation, sid: str, table, r: int, by_line: bool, planned: set[tuple[int, int]]) -> bool:
        """Rule ``row-terms`` (STEM repair 9): the values a line of working takes from the repeats of the one row of a supplied table it
        names (its line, a run's condition, or else its part's question: 'Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s', the
        row's cells in the columns 'Time, trial 1 / s', 'Time, trial 2 / s' and 'Time, trial 3 / s'): the columns a table writes one quantity
        in, repeated (:func:`_repeat_columns`: names that differ only by a trial's number, one unit). In each sum or difference of the
        working that takes a cell of the row's repeats,
        * a term that is a cell of the repeats in another row is set against the named row's cells of the repeats (another row's value
          taken: rule table-operands' reading for the repeats);
        * a term that is no cell of the repeats, when it is the only one and exactly one repeat of the row is taken nowhere, is that repeat
          copied wrongly: it is set against that cell (rule table-terms' reading: '(33.1 s + 43.0 s + 32.5 s) ÷ 3' against 34.0).
        Each a ``giv`` check at warning severity (which row's values the working means is a reading), the data taken as written. Before,
        a line over a row's repeats named no single column, so nothing it took from the table was read: only its arithmetic was checked."""
        if rel.left is None or rel.left.node is None:
            return False
        groups = _repeat_columns(table)
        cells_of = {j: table.rows[r][j][1] for g in groups for j in g if table.rows[r][j][1] is not None}
        if not cells_of:
            return False
        done = False
        key = table.rows[r][0][0]
        for _whole, terms in _additive_groups(rel.left.node):
            leaves = [t for t in terms if isinstance(t, (Num, Quantity))]
            if len(leaves) < 2:
                continue
            group = next((g for g in groups if any(table.rows[i][j][1] is not None and table.rows[i][j][1].value == t.number.value
                                                   for t in leaves for i in range(len(table.rows)) for j in g)), None)
            if group is None or not any(j in cells_of for j in group):
                continue
            unit = table.columns[group[0]].unit
            if any(isinstance(t, Quantity) and (t.unit.unknown or t.unit.dim is None or unit is None or unit.dim is None
                                                or not t.unit.dim.same_physical(unit.dim)) for t in leaves):
                continue  # a term with a unit of another dimension: no sum of the repeats' quantity
            row_vals = {cells_of[j].value for j in group if j in cells_of}
            other_vals = {table.rows[i][j][1].value for i in range(len(table.rows)) if i != r for j in group if table.rows[i][j][1] is not None}
            name = re.sub(r"\s*,?\s*\b(?:trial|repeat|run|replicate|reading|measurement|test)\s*\d+\b", "", table.columns[group[0]].name, flags=re.IGNORECASE) \
                or table.columns[group[0]].name
            cands = tuple(Binding(name[:40] or "table", cells_of[j].value, cells_of[j], None, "request", "request", 0, 0) for j in group if j in cells_of)
            shown = ", ".join(cells_of[j].text for j in group if j in cells_of)
            for t in leaves:
                v = t.number.value
                if v in row_vals or v not in other_vals or (t.start, t.end) in planned:
                    continue
                planned.add((t.start, t.end))
                self.add(kind="giv", outcome="check", statement_ids=(sid,), start=t.start, end=t.end, op="=", right=Operand((t,), t.start, t.end),
                         left=Operand((Sym(name[:40] or "table", start=t.start, end=t.start),), t.start, t.start), candidates=cands[:8],
                         exact_candidates=True, named=name[:60], part=rel.part,
                         reason=f"the value {t.number.text} the working takes from the supplied table's {name} against the repeats of the row "
                                f"{'the line' if by_line else 'its part question'} names ({key}: {shown}) (rule table-operands; rule row-terms)")
                done = True
            loose = [t for t in leaves if t.number.value not in row_vals and t.number.value not in other_vals and t.number.value not in (100, 1000)]
            missing = [j for j in group if j in cells_of and not any(cells_of[j].value == t.number.value for t in leaves)]
            if len(loose) != 1 or len(missing) != 1 or (loose[0].start, loose[0].end) in planned:
                continue
            t, j = loose[0], missing[0]
            planned.add((t.start, t.end))
            cell = cells_of[j]
            cand = Binding(table.columns[j].name[:40] or "table", cell.value, cell, None, "request", "request", 0, 0)
            self.add(kind="giv", outcome="check", statement_ids=(sid,), start=t.start, end=t.end, op="=", right=Operand((t,), t.start, t.end),
                     left=Operand((Sym(table.columns[j].name[:40] or "table", start=t.start, end=t.start),), t.start, t.start), candidates=(cand,),
                     exact_candidates=True, named=table.columns[j].name[:60], part=rel.part,
                     reason=f"the value {t.number.text} the working takes in place of the supplied table's {table.columns[j].name} at row {key} "
                            f"({cell.text}), the one repeat of the row {'the line' if by_line else 'its part question'} names that the working takes "
                            "nowhere (rule table-terms; rule row-terms)")
            done = True
        return done

    def _computed_at_row(self, rel: Relation, sid: str, table) -> Optional[int]:
        """Rule value-at for a computing chain (STEM repair 8): the row of ``table`` that the condition of the run ``rel`` is a link of names
        (its key column's unit fits the condition's), else None."""
        for rsid, cond, start, end in self._computed_at_runs:
            if rsid != sid or not (start <= rel.start and rel.end <= end):
                continue
            cv = value_of(cond)
            if cv is None or cv[1] is None:
                return None
            key = table.columns[0]
            if cv[2] is not None and (key.unit is None or key.unit.dim is None or cv[2].dim is None or not cv[2].dim.same_physical(key.unit.dim)):
                return None
            return table.row_for(cv[1].text, cv[0])
        return None

    def _table_quantity_values(self, column, cells: set[Fraction]) -> list[Binding]:
        """Rule table-terms (STEM repair 8): the values the request and its supplied texts state outside the supplied table for the quantity
        of its ``column`` (its unit's dimension: the background '20 counts per minute' beside 'Measured count rate / counts per minute'),
        each value of a cell left out."""
        unit = column.unit
        if unit is None or unit.unknown or unit.dim is None:
            return []
        f_col = unit.readings[0].factor if len(unit.readings) == 1 and unit.readings[0].factor is not None and unit.readings[0].affine is None else None
        cell_si = {c * f_col for c in cells} if f_col is not None else set()
        out: list[Binding] = []
        seen: set[Fraction] = set()
        for entry, source in [(q, "supplied") for q in self.request.supplied_quantities] + [(q, "request") for q in self.request.quantities]:
            node, a0, b0 = entry[0], entry[1], entry[2]
            v = value_of(node)
            if v is None or v[1] is None or v[2] is None or v[2].unknown or v[2].dim is None or not v[2].dim.same_physical(unit.dim) or v[3]:
                continue
            si = si_value(v[0], v[2], v[3])
            if si is None or si in cell_si or si in seen:
                continue
            seen.add(si)
            out.append(Binding("the supplied text" if source == "supplied" else "the request", v[0], v[1], v[2], source, source, a0, b0))
        return out[:8]

    def _table_terms(self, rel: Relation, sid: str, table, col: int, rows: list[int], cells: set[Fraction], by_line: bool,
                     planned: set[tuple[int, int]]) -> bool:
        """Rule ``table-terms`` (STEM repair 8): the numbers a line of working adds to or takes from values of a supplied table's column
        (the line read by rule table-operands: its rows named by the line, else by its part's question, and its column read). The terms
        of each sum or difference of the working that holds a value of the column's quantity (a cell of the column, a value the request
        or its supplied texts state for that quantity outside the table, or, the whole computed side, when the line states its value with
        the column's unit) are the values the working takes of that quantity; a term that is none of those values (as written) is read:

        * when the line takes the cells of all its named rows but one, and exactly one such term stands in it, the term is that row's
          value copied wrongly: it is set against the row's cell, taken as written ('t = 12 h: 568 − 20 = 548 ± 11 counts min⁻¹' against
          the table's 586 at 12 h; '(9.6 − 3.9) ÷ 9.6 × 100' against site C's 3.8 for the decrease from A to C);
        * when the line takes the cell of every named row, the term is set against the values the request and its supplied texts state
          for that quantity outside the table, when they state any ('t = 24 h: 220 − 25 = 195 ± 4' against the background of 20 counts
          per minute), unless the line's own value is such a value or a cell (the line computes it: '586 − 566 = 20') or the term is a
          stated percentage of the cell (a bound of the measured value: '586 + 11.72', rule processed-data's reading).

        Each is a ``giv`` check at warning severity (which value the number stands for is a reading). Nothing is read when more than one
        named row's value or more than one term is unaccounted for, when a term carries a unit of another dimension than the column's, or
        when the column's quantity has no unit and no value of it is stated outside the table. Before, a number that was no cell of the
        column was never read (a value copied wrongly, its arithmetic consistent, passed with only its arithmetic checked). True when a
        check is planned."""
        if rel.left is None or rel.left.node is None:
            return False
        column = table.columns[col]
        req = self._table_quantity_values(column, cells)
        unit = column.unit
        f_col = unit.readings[0].factor if (unit is not None and len(unit.readings) == 1 and unit.readings[0].factor is not None
                                            and unit.readings[0].affine is None) else None
        req_si = {b.si for b in req if b.si is not None}

        def stated_quantity(t: Node) -> bool:
            if f_col is None or not req_si:
                return False
            tv = value_of(t)
            if tv is None:
                return False
            si = si_value(tv[0], tv[2], tv[3]) if tv[2] is not None else tv[0] * f_col
            return si in req_si

        stated = _stated_value(rel.right.node) if rel.right is not None and rel.right.node is not None else None
        sv = value_of(stated) if stated is not None and is_value(stated) else None
        whole_fits = (sv is not None and sv[2] is not None and not sv[2].unknown and sv[2].dim is not None and unit is not None and unit.dim is not None
                      and sv[2].dim.same_physical(unit.dim))
        loose: list[Node] = []
        cell_leaves: list[Node] = []
        for whole, terms in _additive_groups(rel.left.node):
            leaves = [t for t in terms if isinstance(t, (Num, Quantity))]
            if any(isinstance(t, Quantity) and (t.unit.unknown or t.unit.dim is None or unit is None or unit.dim is None
                                                or not t.unit.dim.same_physical(unit.dim)) for t in leaves):
                continue  # a term with a unit of another dimension: no sum of the column's quantity
            in_cells = [t for t in leaves if t.number.value in cells]
            if not in_cells and not any(stated_quantity(t) for t in leaves) and not (whole is rel.left.node and whole_fits):
                continue
            cell_leaves += in_cells
            loose += [t for t in leaves if t.number.value not in cells and t.number.value not in (100, 1000) and not stated_quantity(t)]
        if not loose:
            return False
        name = column.name
        values = {t.number.value for t in loose}
        row_cells = {r: table.rows[r][col][1] for r in rows if table.rows[r][col][1] is not None}
        missing = [r for r, cell in row_cells.items() if not any(leaf.number.value == cell.value for leaf in cell_leaves)]
        if missing:
            if len(missing) != 1 or len(values) != 1:
                return False
            r = missing[0]
            cell = row_cells[r]
            t = loose[0]
            if (t.start, t.end) in planned:
                return False
            planned.add((t.start, t.end))
            cand = Binding(name[:40] or "table", cell.value, cell, None, "request", "request", 0, 0)
            self.add(kind="giv", outcome="check", statement_ids=(sid,), start=t.start, end=t.end, op="=", right=Operand((t,), t.start, t.end),
                     left=Operand((Sym(name[:40] or "table", start=t.start, end=t.start),), t.start, t.start), candidates=(cand,), exact_candidates=True,
                     named=name[:60], part=rel.part,
                     reason=f"the value {t.number.text} the working takes in place of the supplied table's {name} at row {table.rows[r][0][0]} "
                            f"({cell.text}), the one row {'the line' if by_line else 'its part question'} names whose value the working takes nowhere "
                            "(rule table-terms)")
            return True
        if not req or sv is None or sv[1] is None:
            return False
        if sv[0] in cells or stated_quantity(stated):
            return False  # the line computes a cell or the stated value of the quantity ('586 − 566 = 20'): no value it takes is read
        percents = self._stated_percentages()
        if any(_share_or_bound_of(rel.left.node, leaf, percents) for leaf in cell_leaves):
            return False  # a bound of the measured value ('586 + 11.72', 2% of 586 added): rule processed-data's reading
        done = False
        for t in loose:
            if (t.start, t.end) in planned:
                continue
            planned.add((t.start, t.end))
            node = t if isinstance(t, Quantity) or unit is None else Quantity(t.number, unit, t.start, t.end)
            shown = ", ".join(f"{b.number.text} {b.unit.text}" if b.unit is not None else b.number.text for b in req[:4])
            self.add(kind="giv", outcome="check", statement_ids=(sid,), start=t.start, end=t.end, op="=", right=Operand((node,), t.start, t.end),
                     left=Operand((Sym(name[:40] or "table", start=t.start, end=t.start),), t.start, t.start), candidates=tuple(req), exact_candidates=True,
                     named=name[:60], part=rel.part,
                     reason=f"the value {t.number.text} the working adds to or takes from the supplied table's {name}, against the values the request "
                            f"and its supplied texts state for that quantity outside the table ({shown}) (rule table-terms)")
            done = True
        return done

    def _percentage_changes(self) -> None:
        """Rule ``percentage-change`` (STEM repair 3): a line that computes a percentage increase or decrease as a difference of two
        values over one of them, times 100 ('Percentage decrease = (9.6 − 3.8) ÷ 9.6 × 100 = 60.4% decrease'), is set against the
        definition: the written change over the starting value, times 100. The starting value of a decrease is the larger of the
        two, of an increase the smaller; the direction is the word its statement or its part's question writes beside 'percentage'
        (decrease, fall, drop, reduction, decline; increase, rise, gain, growth). Dividing by the other value ('(9.6 − 3.8) ÷ 3.8 ×
        100 = 152.6% decrease') keeps the arithmetic right and the formula wrong: the line divided by the starting value is set
        against the stated value, and fails, at warning severity (the direction is read from the words). A line that divides by
        the starting value is the definition itself, decided by its own arithmetic check: nothing more is planned. Nothing either
        when both or neither direction is written, or a value is not positive."""
        questions = _part_questions(self.request.text)
        text_of = {it.statement_id: it.statement_text for it in self.items}
        for rel in list(self.relations):
            if rel.kind != "eq" or rel.outcome != "check" or rel.title or rel.left is None or rel.right is None or rel.left.node is None \
                    or rel.right.node is None:
                continue
            shape = _percentage_shape(rel.left.node)
            if shape is None:
                continue
            diff, a, b, divisor = shape
            av, bv = a.number.value, b.number.value
            if av <= 0 or bv <= 0 or av == bv:
                continue
            sid = rel.statement_ids[-1] if rel.statement_ids else ""
            words = (text_of.get(sid, "") + " " + questions.get(rel.part, "")).lower()
            if not _PCT_WORD_RE.search(words):
                continue
            dec = bool(_PCT_DECREASE_RE.search(words))
            inc = bool(_PCT_INCREASE_RE.search(words))
            if dec == inc:
                continue
            start = (a if av > bv else b) if dec else (a if av < bv else b)
            if divisor.number.value == start.number.value:
                continue  # the line divides by the starting value: it is the definition, and its own arithmetic check decides it
            expr = _replace_node(rel.left.node, divisor, start)
            if expr is None:
                continue
            what = "decrease" if dec else "increase"
            self.add(kind="eq", outcome="check", statement_ids=rel.statement_ids, start=rel.start, end=rel.end, op=rel.op,
                     left=Operand((expr,), rel.left.start, rel.left.end), right=rel.right, part=rel.part, approx=rel.approx, position=rel.position,
                     title="the percentage change as defined (the written change over the starting value, × 100)",
                     reason=f"a percentage {what}: the change over the starting value {start.number.text} (the {'larger' if dec else 'smaller'} of "
                            f"{a.number.text} and {b.number.text}), × 100, against the stated value (rule percentage-change)")

    def _stated_uncertainties(self) -> None:
        """Rule ``stated-uncertainty`` (STEM repair 4): when the answer states how it obtains the uncertainty of its values as a
        percentage of a value it names ('each corrected value has an absolute uncertainty of 2% of the measured value'), a later line of
        the same part that writes its value with an absolute uncertainty, ``S ± u``, and takes exactly one cell of a column of a supplied
        table whose name holds that word ('t = 4 h: 1151 − 20 = 1131 ± 23 counts min⁻¹', the measured count rate 1151), is set against
        the rule: u against that percentage of the cell (2% of 1151 is 23.02), the cell taken as written, only u's own half-width
        banding it (a ``giv`` check at warning severity: which value the percentage is of is a reading). Before, u was never checked
        (rule central-value), so '1131 ± 33' passed. An uncertainty the answer states no such rule for, or one a line propagates from
        several measured values, is not checked (rule central-value, as before)."""
        if not self.request.tables or not self.text or not self.prose_values:
            return
        rules: list[tuple[Fraction, str, frozenset[str], ProseValue]] = []
        for pv in self.prose_values:
            v = value_of(pv.node)
            if v is None or v[1] is None or v[3] != "%" or v[2] is not None or v[0] <= 0:
                continue
            before = self.text[max(0, pv.start - 80):pv.start]
            after = self.text[pv.end:pv.end + 80]
            mb, ma = _UNC_RULE_BEFORE_RE.search(before), _UNC_RULE_AFTER_RE.match(after)
            if mb is None or ma is None:
                continue
            words = frozenset(w for w in re.findall(r"[a-z]+", ma.group("name").lower()) if len(w) >= 3 and w not in _LABEL_STOP)
            if words:
                rules.append((v[0], v[1].text, words, pv))
        if not rules:
            return
        for rel in list(self.relations):
            if rel.kind != "eq" or rel.outcome != "check" or rel.title or rel.left is None or rel.right is None or rel.left.node is None:
                continue
            node = rel.right.node
            if not isinstance(node, PlusMinus) or node.sign != "±" or node.left is None or not isinstance(node.right, (Num, Quantity)):
                continue
            unc = node.right
            leaves = [n for n in walk(rel.left.node) if isinstance(n, (Num, Quantity))]
            for p, p_text, words, pv in rules:
                if pv.end > rel.start or (pv.part and rel.part != pv.part):
                    continue
                cells: list[Node] = []
                named = ""
                for table in self.request.tables:
                    for j in range(1, len(table.columns)):
                        name_words = set(re.findall(r"[a-z]+", table.columns[j].name.lower()))
                        if not words <= name_words:
                            continue
                        values = {table.rows[r][j][1].value for r in range(len(table.rows)) if table.rows[r][j][1] is not None}
                        hits = [leaf for leaf in leaves if leaf.number.value in values]
                        if hits:
                            named = table.columns[j].name
                        cells.extend(hits)
                if len(cells) != 1:
                    continue
                cell = cells[0]
                expected = p / 100 * cell.number.value
                text = _show_fraction(expected)
                number = ExactNumber(text=text, value=expected, sig_figs=max(1, len(text.replace(".", "").lstrip("0"))), last_place=0, exact=False,
                                     has_point="." in text)
                cand = Binding(f"{p_text}% of {cell.number.text}", expected, number, unc.unit if isinstance(unc, Quantity) else None, "request", "request", 0, 0)
                self.add(kind="giv", outcome="check", statement_ids=rel.statement_ids, start=unc.start, end=unc.end, op="=", right=Operand((unc,), unc.start, unc.end),
                         left=Operand((Sym("the stated uncertainty", start=unc.start, end=unc.start),), unc.start, unc.start), candidates=(cand,),
                         part=rel.part, exact_candidates=True, named=named[:60], title="the stated uncertainty against the rule the answer states for it",
                         reason=f"the uncertainty written with the value, against {p_text}% of the value {cell.number.text} the line takes from {named[:60]}, "
                                f"as the answer states in {pv.statement_id} (rule stated-uncertainty)")
                break

    def _half_lives(self) -> None:
        """Rule ``half-lives`` (STEM repair 3): a number of half-lives the prose states is set against what the answer computes with
        it. A time stated to be that many half-lives ('32 h is 4 half-lives') is the number times the half-life the answer states
        (a symbol T½, t½ or T_{1/2}, its latest value before the statement): an ``eq`` check of n × T½ against the time. A power of
        ½ (or 0.5) written after the phrase in the same statement, the decay over those half-lives ('so C = 1600 counts min⁻¹ ×
        (1/2)⁴'), has the number as its exponent: an ``eq`` check of the exponent against the number. Both at warning severity (the
        prose is read). Nothing when no half-life is stated (the first) or no power of ½ follows (the second)."""
        if not self.prose_values and not self.items:
            return
        by_sid: dict[str, MathItem] = {}
        for it in self.items:
            by_sid.setdefault(it.statement_id, it)
        for sid, it in by_sid.items():
            text = it.statement_text
            if "half" not in text.lower():
                continue
            for m in _HALF_LIVES_RE.finditer(text[:4000]):
                n = _small_number(m.group("n"))
                if n is None or n <= 0 or n > 100:
                    continue
                pos = it.statement_start + m.start()
                end = it.statement_start + m.end()
                n_node = Num(ExactNumber(text=m.group("n"), value=Fraction(n), sig_figs=len(str(n)), last_place=0, exact=True,
                                         digit_count=len(str(n))), pos, pos + len(m.group("n")))
                # the time the prose says is that many half-lives
                pv = next((p for p in reversed(self.prose_values) if p.statement_id == sid and p.end <= pos
                           and _TIME_IS_RE.match(self.text[p.end:pos] if 0 <= p.end <= pos <= len(self.text) else "")), None)
                half = self._half_life_before(pos)
                if pv is not None and half is not None:
                    tv = value_of(pv.node)
                    if tv is not None and tv[2] is not None and tv[2].dim is not None and half.unit is not None and half.unit.dim is not None \
                            and tv[2].dim.same_physical(half.unit.dim):
                        h_node = Quantity(half.number, half.unit, half.start, half.end)
                        self.add(kind="eq", outcome="check", statement_ids=tuple(dict.fromkeys((half.statement_id, sid))), start=pv.start, end=end, op="=",
                                 left=Operand((BinOp("*", n_node, h_node, pos, end),), pos, end), right=Operand((pv.node,), pv.start, pv.end), part=it.part,
                                 title="the number of half-lives the prose states, times the half-life",
                                 reason=f"{m.group('n')} half-lives of {half.number.text} {half.unit.text} (the half-life stated in {half.statement_id}) against "
                                        f"the time the prose says they make (rule half-lives)")
                # the decay over those half-lives: the power of 1/2 written after the phrase in the statement
                after = [rel for rel in list(self.relations) if rel.kind == "eq" and rel.outcome == "check" and not rel.title and sid in rel.statement_ids
                         and rel.left is not None and rel.left.node is not None and rel.start >= end]
                if not any(isinstance(x, Pow) and _is_half(x.base) for rel in after for x in walk(rel.left.node)):
                    # rule decay-law (STEM repair 9): the line computes the value the quantity decays to over those half-lives with no power
                    # of ½ ('At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 5 = 320 counts min⁻¹'): the decay law at the one value of the
                    # result's dimension the line takes is set against its stated value
                    for rel in after:
                        if self._decay_law(rel, it, sid, n, n_node, m.group(0)):
                            break
                for rel in after:
                    power = next((x for x in walk(rel.left.node) if isinstance(x, Pow) and _is_half(x.base)), None)
                    if power is None:
                        continue
                    k_node = Num(ExactNumber(text=str(power.exp), value=Fraction(power.exp), sig_figs=len(str(abs(power.exp))), last_place=0, exact=True,
                                             digit_count=len(str(abs(power.exp)))), power.start, power.end)
                    p0 = power.start - 1 if 0 < power.start <= len(self.text) and self.text[power.start - 1] == "(" else power.start  # '(1/2)⁴'
                    self.add(kind="eq", outcome="check", statement_ids=(sid,), start=p0, end=power.end, op="=",
                             left=Operand((n_node,), pos, pos + len(m.group("n"))), right=Operand((k_node,), p0, power.end), part=it.part,
                             title="the power of ½ in the decay against the number of half-lives the prose states",
                             reason=f"the power of ½ written after '{m.group(0)}' ({power.exp}) against the {m.group('n')} half-lives (rule half-lives)")
                    break

    def _decay_law(self, rel: Relation, it: MathItem, sid: str, n: int, n_node: Node, phrase: str) -> bool:
        """Rule ``decay-law`` (STEM repair 9, beside rule half-lives): a line after the prose states a number of half-lives, in its
        statement, that computes the value a quantity decays to without a power of ½ ('At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹
        ÷ 5 = 320 counts min⁻¹'): its computed side takes exactly one value of the dimension of the value it states (the value before the
        decay, 1600 counts min⁻¹), so the decay law over those half-lives, that value × (½)ⁿ, is set against the stated value: an ``eq``
        check at warning severity (that the line computes the decay over the half-lives the prose states is a reading). '÷ 5' gives 320
        where the law gives 50: it fails; '÷ 32' and '÷ 2⁵' hold. Nothing when the line writes a power of ½ (rule half-lives checks its
        exponent), states no value with a unit, or takes no value, or more than one, of that value's dimension. True when planned."""
        if rel.right is None or rel.right.node is None:
            return False
        stated = _stated_value(rel.right.node)
        sv = value_of(stated) if stated is not None and is_value(stated) else None
        if sv is None or sv[1] is None or sv[2] is None or sv[2].unknown or sv[2].dim is None or sv[3]:
            return False
        starts = [q for q in walk(rel.left.node) if isinstance(q, Quantity) and not q.unit.unknown and q.unit.dim is not None
                  and q.unit.dim.same_physical(sv[2].dim)]
        if len(starts) != 1 or is_value(rel.left.node):
            return False
        c0 = starts[0]
        one = Num(ExactNumber(text="1", value=Fraction(1), sig_figs=1, last_place=0, exact=True, digit_count=1), c0.start, c0.start)
        two = Num(ExactNumber(text="2", value=Fraction(2), sig_figs=1, last_place=0, exact=True, digit_count=1), c0.start, c0.start)
        law = BinOp("*", c0, Pow(BinOp("/", one, two, c0.start, c0.start), n, c0.start, c0.start), c0.start, c0.end)
        b = dict(statement_ids=(sid,), start=rel.start, end=rel.end, op=rel.op, left=Operand((law,), rel.left.start, rel.left.end), right=rel.right,
                 part=it.part)
        self.add(kind="eq", outcome="check", title="the decay over the half-lives the prose states, against the line's value",
                 reason=f"the decay law over the {n} half-lives of '{phrase}', {render(c0)[:40]} × (½)^{n}, against the value the line states "
                        "(rule decay-law)", **b)
        return True

    def _half_life_before(self, pos: int) -> Optional[Binding]:
        """The latest value of a half-life symbol (T½, t½, T_{1/2}: one name the reader gives T_half) the answer or the request states
        before ``pos``."""
        best: Optional[Binding] = None
        for name, blist in self.scope.bindings.items():
            if name.lower() not in _HALF_LIFE_NAMES:
                continue
            for bd in blist:
                if bd.unit is None or (bd.source != "request" and bd.end > pos):
                    continue
                if best is None or (bd.source != "request" and (best.source == "request" or bd.end > best.end)):
                    best = bd
        return best

    def _processed_data(self) -> None:
        """Rule ``processed-data`` (STEM repair 3): a line of working that processes one cell of a supplied table into another value
        of its quantity ('t = 0 h: 1620 − 20 = 1600 ± 32 counts min⁻¹', the corrected count rate of the row t = 0 h) states the
        processed value of that row. A line of a later part whose question (or the line itself) names the processed quantity by
        the word that sets it apart from the table's column ('(d) Predict the corrected count rate at t = 32 h': corrected) and
        that takes the raw cell instead ('C = 1620 counts min⁻¹ × (1/2)⁴') is set against the processed value: a ``giv`` check at
        warning severity (which of the two values the line means is a reading), which fails. The words that set the processed
        quantity apart are those of the processing part's question and of a word formula stated in it ('Corrected count rate =
        measured count rate − background') that the column's name, the key column's name and the command words do not hold. A
        line of the processing part itself (an uncertainty of the measured value), a part that names no such word, a cell
        whose value two rows hold, and (STEM repair 5) a line that takes a percentage of the raw cell ('2% of 1620 is 0.02 × 1620 =
        32.4 counts min⁻¹': the percentage written with '%', or as the decimal of a percentage the answer, the request or its
        supplied texts state, in any arithmetic form: '1620 × 2 ÷ 100'), the cell with that percentage of it added or taken away (the
        bounds of the measured value: '1620 × 1.02', '1620 + 32.4'), a ratio of it to another value of its quantity, and a line that
        processes the cell inside its own arithmetic ('C = (1620 − 20) × (1/2)⁴ = 100 counts min⁻¹') are not read."""
        if not self.request.tables:
            return
        questions = _part_questions(self.request.text)
        text_of = {it.statement_id: it.statement_text for it in self.items}
        formula_words: dict[str, set[str]] = {}
        for rel in self.relations:
            if rel.kind == "label" and rel.outcome == "formula" and rel.left is not None and isinstance(rel.left.node, Sym):
                formula_words.setdefault(rel.part, set()).update(_label_words(rel.left.node.name))
        eqs = sorted((r for r in self.relations if r.kind == "eq" and r.outcome == "check" and not r.title and r.left is not None and r.left.node is not None
                      and r.right is not None and r.right.node is not None), key=lambda r: (r.start, r.index))
        processed: dict[tuple[int, int, int], tuple[Relation, Node, frozenset[str], frozenset[str]]] = {}
        planned: set[tuple[int, int]] = set()
        percents: Optional[frozenset[Fraction]] = None
        for rel in eqs:
            sid = rel.statement_ids[-1] if rel.statement_ids else ""
            stmt = text_of.get(sid, "")
            leaves = [n for n in walk(rel.left.node) if isinstance(n, (Num, Quantity))]
            stated = _central_value(rel.right.node) or rel.right.node
            sv = value_of(stated) if is_value(stated) else None
            for ti, table in enumerate(self.request.tables):
                key_words = set(table.columns[0].words)
                for col in table.value_columns():
                    rows_of: dict[Fraction, list[int]] = {}
                    for r, row in enumerate(table.rows):
                        if row[col][1] is not None:
                            rows_of.setdefault(row[col][1].value, []).append(r)
                    taken = [leaf for leaf in leaves if leaf.number.value in rows_of and leaf.number.value not in (100, 1000)]
                    if not taken:
                        continue
                    column = table.columns[col]
                    # the line processes the cell: it takes this one cell of the column and states another value of its quantity
                    if len(taken) == 1 and len(rows_of[taken[0].number.value]) == 1 and sv is not None and sv[0] != taken[0].number.value \
                            and _unit_fits(column.unit, sv[2]):
                        r = rows_of[taken[0].number.value][0]
                        named = _named_rows(stmt, table)
                        if (not named or named == [r]) and (ti, col, r) not in processed:
                            words = set(_label_words(questions.get(rel.part, ""))) | formula_words.get(rel.part, set())
                            apart = frozenset(w for w in words - set(column.words) - key_words - _PROCESSED_STOP if len(w) >= 4)
                            # STEM repair 5: the words that set the raw quantity apart from the processed one (the column's 'measured')
                            raw_apart = frozenset(w for w in set(_label_words(column.name)) - words - key_words - _PROCESSED_STOP if len(w) >= 4)
                            if apart:
                                processed[(ti, col, r)] = (rel, stated, apart, raw_apart)
                            continue
                    # a later line of another part that takes the raw cell where the answer processed it
                    for leaf in taken:
                        rows = rows_of[leaf.number.value]
                        if len(rows) != 1 or (leaf.start, leaf.end) in planned:
                            continue
                        hit = processed.get((ti, col, rows[0]))
                        if hit is None:
                            continue
                        proc, pnode, apart, raw_apart = hit
                        if proc is rel or proc.part == rel.part or proc.end > rel.start:
                            continue
                        here = set(re.findall(r"[a-z]+", (stmt + " " + questions.get(rel.part, "")).lower()))
                        if not apart & here:
                            continue
                        own = set(re.findall(r"[a-z]+", stmt.lower()))
                        if raw_apart & own and not apart & own:
                            # STEM repair 5: the line names the raw quantity itself by the word that sets it apart ('The measured rate fell by
                            # 1620 − 820 = 800 counts min⁻¹', 'The mean of the first two measured rates is (1620 + 1151)/2'): it takes the
                            # measured value on purpose, never the processed one
                            continue
                        pv = value_of(pnode)
                        if pv is None or pv[1] is None:
                            continue
                        # the line must compute a value of the column's quantity from the raw cell: a ratio or a percentage of it
                        # ('20/1620 × 100 = 1.2% of the first reading') takes the measured value on purpose, and a line that processes
                        # the raw cell again into the processed value ('C₀ = 1620 − 20 = 1600 counts min⁻¹') substitutes nothing (its
                        # own arithmetic is checked)
                        if sv is None or sv[1] is None or not _unit_fits(column.unit, sv[2]) or (sv[3] == "%" and column.unit is not None):
                            continue
                        if percents is None:
                            percents = self._stated_percentages()
                        quantity_values = self._quantity_values(rows_of, column) | frozenset(
                            value_of(node)[0] for (t, c, _r), (_p, node, _a, _ra) in processed.items() if t == ti and c == col and value_of(node) is not None)
                        if _percentage_of(rel.left.node, leaf, percents) or _ratio_of(rel.left.node, leaf, quantity_values) \
                                or _share_or_bound_of(rel.left.node, leaf, percents) or _processed_inline(rel.left.node, leaf, pv[0]):
                            # STEM repair 5: a percentage of the raw cell ('2% of 1620 is 0.02 × 1620 = 32.4 counts min⁻¹', the uncertainty
                            # of the measured value by the answer's own rule; '1620 × 2 ÷ 100'), the bounds of the measured value ('1620 ×
                            # 1.02', '1620 + 32.4'), or a ratio of it to another value of its quantity ('1620/820 = 1.98') takes the measured
                            # value on purpose, and a line that processes the cell inside its own arithmetic ('(1620 − 20) × (1/2)⁴') takes
                            # the processed value: not read
                            continue
                        psid = proc.statement_ids[-1] if proc.statement_ids else ""
                        if Binding("stated", sv[0], sv[1], sv[2], "statement", sid, wrapper=sv[3]).same_as(
                                Binding("processed", pv[0], pv[1], pv[2], "statement", psid, wrapper=pv[3])):
                            continue
                        planned.add((leaf.start, leaf.end))
                        word = sorted(apart & here)[0]
                        cand = Binding(f"{word} {column.name}"[:40], pv[0], pv[1], pv[2], "statement", psid, getattr(pnode, "start", 0), getattr(pnode, "end", 0),
                                       wrapper=pv[3])
                        self.add(kind="giv", outcome="check", statement_ids=tuple(dict.fromkeys((sid, psid))), start=leaf.start, end=leaf.end, op="=",
                                 right=Operand((leaf,), leaf.start, leaf.end), left=Operand((Sym(f"{word} value", start=leaf.start, end=leaf.start),),
                                                                                           leaf.start, leaf.start),
                                 candidates=(cand,), part=rel.part,
                                 title="the value taken from the supplied table against the value the answer processed it into",
                                 reason=f"the value {leaf.number.text} the working takes is the supplied table's {column.name} at row {table.rows[rows[0]][0][0]}, "
                                        f"which the answer processed into {render(pnode)[:40]} in {psid}; the part asks for the {word} value "
                                        f"(rule processed-data)")
        return

    def _quantity_values(self, rows_of: dict, column) -> frozenset[Fraction]:
        """STEM repair 5 (rule processed-data): the values of a supplied table column's quantity: its cells, and the quantities the request
        and its supplied texts state with the column's dimension (the background '20 counts per minute' beside the count rates)."""
        out = set(rows_of)
        dim = column.unit.dim if column.unit is not None and not column.unit.unknown else None
        if dim is not None:
            for node, _a, _b, *_rest in tuple(self.request.supplied_quantities) + tuple(self.request.quantities):
                v = value_of(node)
                if v is not None and v[2] is not None and v[2].dim is not None and v[2].dim.same_physical(dim):
                    out.add(v[0])
        return frozenset(out)

    def _stated_percentages(self) -> frozenset[Fraction]:
        """STEM repair 5 (rule processed-data): every percentage the answer, the request and its supplied texts state ('2%' of the answer's
        uncertainty rule, the supplied '+/-2%'), as the per cent value (2 for 2%)."""
        out: set[Fraction] = set()
        for pv in self.prose_values:
            v = value_of(pv.node)
            if v is not None and v[2] is None and v[3] == "%":
                out.add(abs(v[0]))
        for it in self.items:
            for chain in it.chains:
                for op in chain.operands:
                    for node in op.readings[:1]:
                        for n in walk(node):
                            if isinstance(n, Percent):
                                v = value_of(n)
                                if v is not None:
                                    out.add(abs(v[0]))
        for entry in tuple(self.request.values) + tuple(self.request.supplied_values):
            v = value_of(entry[0])
            if v is not None and v[2] is None and (v[3] == "%" or (len(entry) > 3 and entry[3] == "%")):
                out.add(abs(v[0]))
        for entry in tuple(self.request.supplied_uncertainties) + tuple(self.request.request_uncertainties):
            v = value_of(entry[0])
            if v is not None and len(entry) > 4 and entry[4] == "%":
                out.add(abs(v[0]))
        return frozenset(out)

    def _table_check(self, pv: ProseValue, v: tuple, m: "re.Match[str]", clause: str, *, keys: tuple, direction: Optional[str] = None) -> None:
        match, first, second = keys
        for table in self.request.tables:
            rows = []
            for name in (first, second):
                if name is None:
                    continue
                key = match.group(name)
                unit = (match.group(name.replace("k", "u")) or "").strip()
                num = _key_number(key)
                if num is not None and unit and table.columns[0].unit is not None:
                    ku = parse_unit(unit)
                    if ku is None or ku.dim is None or table.columns[0].unit.dim is None or not ku.dim.same_physical(table.columns[0].unit.dim):
                        rows = []
                        break
                r = table.row_for(key, num)
                if r is None:
                    rows = []
                    break
                rows.append(r)
            if not rows or (second is not None and len(rows) != 2):
                continue
            cols = table.value_columns()
            if len(cols) > 1:
                words = set(re.findall(r"[a-z]+", clause.lower()))
                cols = [j for j in cols if table.columns[j].words and table.columns[j].words <= words]
            if len(cols) != 1:
                continue
            col = table.columns[cols[0]]
            if _names_processed(clause, col, allow=(direction.lower(),) if direction else ()):
                continue  # STEM repair 10: 'The corrected rate falls from 1131 counts min⁻¹ at 4 h …' is no cell of the measured column
            if v[2] is not None and col.unit is not None and not col.unit_ascii and (v[2].dim is None or col.unit.dim is None
                                                                                     or not v[2].dim.same_physical(col.unit.dim)):
                continue
            cells = [table.rows[r][cols[0]][1] for r in rows]
            if any(c is None for c in cells):
                continue
            if second is not None:
                diff = cells[1].value - cells[0].value
                if direction is not None and direction.lower() in _DECREASE_WORDS:
                    diff = -diff
                elif direction is not None and direction.lower() in _NEUTRAL_CHANGE_WORDS:
                    diff = abs(diff)
                what = (f"the {direction.lower() if direction else 'change'} in {col.name} between the supplied table's rows "
                        f"{table.rows[rows[0]][0][0]} and {table.rows[rows[1]][0][0]} ({cells[1].text} − {cells[0].text})")
                number = ExactNumber(text=_show_fraction(diff), value=diff, sig_figs=1, last_place=0, exact=True)
            else:
                what = f"{col.name} at the supplied table's row {table.rows[rows[0]][0][0]} ({cells[0].text})"
                number = cells[0]
            # STEM repair 3: the cell carries its column's unit when the stated value has a unit of that dimension, so a value restated in
            # another unit ('from 18 cm³ per g per hour at 10 °C' for the table's 18 mm3 per g per hour) is compared in SI and fails
            cand = Binding(col.name[:40] or "table", number.value, number, _cell_unit(col.unit, v[2]), "request", "request", 0, 0)
            node = pv.node
            self.add(kind="giv", outcome="check", statement_ids=(pv.statement_id,), start=pv.start, end=pv.end, op="=", right=Operand((node,), pv.start, pv.end),
                     left=Operand((Sym(col.name[:40] or "table", start=pv.start, end=pv.start),), pv.start, pv.start), candidates=(cand,), part=pv.part,
                     exact_candidates=True, named=col.name[:60],
                     reason=f"the value the prose gives against {what}: the supplied data, taken as written (rule table-data)")
            return

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

    def _givens(self) -> None:
        """Every Given value is set against the request (STEM repair 2, rule given-kinds), or named unchecked. Its candidates are the
        request's values of its kind, the first kind that has any: the request's binding of the same symbol; the request's quantities
        of the same dimension (a Given with a unit the table reads); the request's percentages (a Given written with %, "per cent" or
        "percent"); the request's numbers written with the same word after them ('5000 euros' against '4000 euros', '6 years' against
        '5 years'); for a bare Given (no unit, no per cent sign, no word after it), the request's number it equals, written bare or with
        a word: a bare number that equals none is no contradiction the branch can read (0.036 for 3.6%, 12 for "monthly", 60 for five
        years of months are bare too), so it is named unchecked, never failed. A Given that names a row of a supplied table and one of
        its columns ('Given: dissolved oxygen at C = 3.5 mg dm⁻³') is set against that cell (rule table-data). A Given with none of
        these, no data-booklet constant it states and a value other than zero (a zero the request states in words: 'dropped from
        rest') is ST-UNDEC-003, one finding per statement naming each such Given: it is not checked against the request, and the
        receipt says so. With no request (the relay form) no Given is set against anything and none is named."""
        if not self.request.text.strip():
            return  # the relay form: no request to set a Given against (stem-giv is not built there)
        req_by_symbol: dict[str, list[Binding]] = {}
        for b in self.request.bindings:
            req_by_symbol.setdefault(b.symbol, []).append(b)
        givens: list[tuple[str, Binding]] = [(name, b) for name, blist in list(self.scope.bindings.items()) for b in blist if b.source == "given"]
        given_sids = {it.statement_id for it in self.items if it.source == "given"}
        #: rule value-at (STEM repair 3): a Given stated under a condition ('Given: oxygen uptake at 30 °C = 80 mm³ per g per hour')
        conditioned: dict[int, Relation] = {}
        #: rule given-uncertainty (STEM repair 3): the Givens written with their uncertainty ('T = 20.0 ± 0.5 °C': the central value is the
        #: Given value) and those written as an uncertainty ('Δθ = ±0.5 °C')
        central: set[int] = set()
        spread: set[int] = set()
        #: STEM repair 4 (rule given-uncertainty): the uncertainty a Given written with its value states ('T = 20.0 ± 0.5 °C', 'C = 1620 ±
        #: 2%'): set against the uncertainties the request and its supplied texts state when they state one of its kind, else not read
        paired: set[int] = set()
        for rel in list(self.relations):
            # a Given written with a word label ('Given: DO_C = 3.5 mg dm⁻³'): a value the answer presents as given all the same
            if rel.kind not in ("label", "binding") or rel.outcome != "binding" or not set(rel.statement_ids) & given_sids or rel.left is None or rel.right is None:
                continue
            head, node = rel.left.node, rel.right.node
            if rel.kind == "binding" or isinstance(node, PlusMinus):
                # a Given written with '±' (STEM repair 3): no value node, so no binding of the scope either
                if not isinstance(head, Sym) or not isinstance(node, PlusMinus) or node.sign != "±":
                    continue
                mid = _central_value(node)
                rel_unc = node.left is not None and isinstance(node.left, (Num, Quantity)) and _percent_number(node.right)
                if mid is None and rel_unc:
                    mid = node.left  # STEM repair 4: '1620 ± 2%', a value with its relative uncertainty: the value is the central one
                if node.left is None:
                    # '±0.5 °C', and (STEM repair 4) '±3%': a Given written as an uncertainty (a per cent one had neither check nor ST code)
                    target = node.right if isinstance(node.right, (Num, Quantity)) or _percent_number(node.right) else None
                else:
                    target = mid
                v = value_of(target) if target is not None else None
                if v is None or v[1] is None:
                    continue
                # the check quotes the whole value as written ('25.0 ± 0.5 °C', '±0.5 °C')
                givens.append((head.name, Binding(head.name, v[0], v[1], v[2], "given", rel.statement_ids[-1], node.start or getattr(target, "start", rel.start),
                                                  node.end or getattr(target, "end", rel.end), wrapper=v[3])))
                (central if mid is not None else spread).add(len(givens) - 1)
                if rel.condition is not None and mid is not None:
                    conditioned[len(givens) - 1] = rel  # STEM repair 4: 'Given: count rate at t = 0 h = 1620 ± 2%' (rule value-at)
                unc = node.right if mid is not None else None
                if mid is not None and target is not unc and (isinstance(unc, (Num, Quantity)) or _percent_number(unc)):
                    if isinstance(unc, Num) and isinstance(mid, Quantity):
                        unc = Quantity(unc.number, mid.unit, unc.start, unc.end)  # '25.0 °C ± 0.5': the uncertainty in the value's unit
                    u = value_of(unc)
                    if u is not None and u[1] is not None:
                        givens.append((head.name, Binding(head.name, u[0], u[1], u[2], "given", rel.statement_ids[-1], node.start or rel.start,
                                                          node.end or rel.end, wrapper=u[3])))
                        spread.add(len(givens) - 1)
                        paired.add(len(givens) - 1)
                continue
            v = value_of(node) if node is not None else None
            if not isinstance(head, Sym) or v is None or v[1] is None:
                continue
            givens.append((head.name, Binding(head.name, v[0], v[1], v[2], "given", rel.statement_ids[-1], getattr(node, "start", rel.start),
                                              getattr(node, "end", rel.end), wrapper=v[3])))
            if rel.condition is not None:
                conditioned[len(givens) - 1] = rel
        #: rule prose-given (STEM repair 6): the Given values a Given statement states in prose ('Data: emf 15 V, internal resistance 0.50
        #: Ω.', 'Given: the mass of seeds is 12 g.', 'Given: 15.0 cm³ of acid.'), each read as the same Given written with '=': index ->
        #: (its name's words, the condition it is stated under, the request's quantities its words name: rule named-given)
        prose_meta: dict[int, tuple[list[str], Optional[Node], list[Binding]]] = {}
        planned = {(r.start, r.end) for r in self.relations if r.outcome == "check"}
        named_q = [(q, "request") for q in self.request.named_quantities] + [(q, "supplied") for q in self.request.supplied_named]
        for pv in self.prose_values:
            if not pv.given or (pv.start, pv.end) in planned:
                continue
            v = value_of(pv.node)
            if v is None or v[1] is None:
                continue
            ahead = self.text[max(0, pv.start - 2):pv.start]
            if _CURRENCY_BEFORE_RE.search(ahead) or _THOUSANDS_BEFORE_RE.search(ahead):
                continue  # 'P = €4000' (an amount), 'P = 4 000 euros' (named ST-PARSE-001 on its first group): never read
            name, words, condition, cond_at = _given_item(pv.before, pv.after)
            if condition:
                continue  # 'at 30 °C': the condition a Given is stated under, never a Given
            cond_node = self._prose_condition(pv, cond_at)
            pm = _PROSE_PLUS_MINUS_RE.search(pv.before)
            as_uncertainty = pm is not None
            g_start, g_end = (pv.start - (len(pv.before) - pm.start())) if pm is not None else pv.start, pv.end
            if as_uncertainty and v[2] is None and not v[3]:
                # 'Given: thermometer uncertainty ±0.5 °C': the prose reads the number alone; its unit is the one written after it
                um = _UNIT_AFTER_RE.match(pv.after)
                unit = parse_unit(um.group(1).strip(), bare_m=self.profile.bare_m, tonne=self.profile.tonne) if um is not None else None
                if unit is not None and not unit.unknown and unit.dim is not None:
                    v = (v[0], v[1], unit, v[3])
                    g_end = pv.end + um.end(1)
            singular = set(_name_words(" ".join(words)))
            named: list[Binding] = []
            if v[2] is not None and v[2].dim is not None and not v[2].unknown and singular:
                for (qnode, a0, b0, qwords), source in named_q:
                    qv = value_of(qnode)
                    if qv is None or qv[2] is None or qv[2].dim is None or not qwords or not set(qwords) <= singular or not qv[2].dim.same_physical(v[2].dim):
                        continue
                    named.append(Binding(" ".join(qwords), qv[0], qv[1], qv[2], source, source, a0, b0, wrapper=qv[3]))
            label = name or "the quantity"
            givens.append((label, Binding(label, v[0], v[1], v[2], "given", pv.statement_id, g_start, g_end, wrapper=v[3])))
            if as_uncertainty:
                spread.add(len(givens) - 1)  # a Given written as an uncertainty (rule given-uncertainty)
            prose_meta[len(givens) - 1] = ([w.lower() for w in words if len(w) >= 4 and w.lower() not in _AT_NAME_STOP and w.lower() not in _NAME_STOP],
                                           cond_node, named)
        unset: dict[str, list[tuple[str, str, int, int]]] = {}
        for gi, (name, b) in enumerate(givens):
            meta = prose_meta.get(gi)
            group = _THOUSANDS_AFTER_RE.match(self.text, b.end)
            if group is not None and b.number.value.denominator == 1 and len(b.number.text) <= 3:
                # 'P = 4 000 euros': the value may be a numeral written with a thousands space, read here as 4; it is not read
                shown = self.text[b.start:group.end()]
                self.finding("ST-PARSE-001", f"the Given value of {name} ('{shown}') in {b.statement_id} may be a numeral written with a thousands "
                                             "space; it is not read, and it is not checked against the request", (b.statement_id,), b.start, b.end)
                continue
            span_item = next((it for it in self.items if it.statement_id == b.statement_id and it.start <= b.start <= it.end), None)
            if span_item is not None and any(iss.code in ("ST-PARSE-001", "ST-PARSE-002") for iss in span_item.issues):
                # STEM repair 4: a Given in a maths span the branch cannot read whole ('Given: count rate at t = 0 h = 1620 ± 2% counts
                # min⁻¹': a unit after a per cent sign) is never read in part, as a thousands-space numeral is not: its ST-PARSE code
                # names the statement. Before, the condition 't = 0 h' was read as a Given and failed against the request's t = 32 h.
                continue
            word = _word_after(self.text, b.end)
            percent = b.wrapper == "%" or word == "%"
            base: Node = Quantity(b.number, b.unit, b.start, b.end) if b.unit is not None else Num(b.number, b.start, b.end)
            node = Percent(base, b.start, b.end) if percent and b.unit is None else base
            at_rel = conditioned.get(gi)
            item = next((it for it in self.items if it.statement_id == b.statement_id and it.start <= b.start <= it.end), None)
            name_words = meta[0] if meta is not None else _given_name_words(item, name)
            if gi in spread or set(name_words) & _UNCERTAINTY_WORDS:
                # rule given-uncertainty (STEM repair 3): an uncertainty is no value of its quantity ('Given: thermometer uncertainty =
                # 0.5 °C' failed against the request's 20 °C and 60 °C); it is set against the uncertainties the request and its
                # supplied texts state, of its dimension (or percentages), or named
                cands_u = self._uncertainty_candidates(name, b, percent)
                if cands_u:
                    what = (f"the uncertainty of the Given value of {name}, written with it," if gi in paired else f"the Given value of {name}, an uncertainty,")
                    self.add(kind="giv", outcome="check", statement_ids=(b.statement_id,), start=b.start, end=b.end, op="=",
                             right=Operand((node,), b.start, b.end), left=Operand((Sym(name, start=b.start, end=b.start),), b.start, b.start),
                             candidates=tuple(cands_u[:8]), reason=f"{what} against the uncertainties the request "
                                                                   "and its supplied texts state (rule given-uncertainty)"
                                                                   + ("; the Given written in prose (rule prose-given)" if meta is not None else ""))
                    continue
                if gi in paired:
                    continue  # the uncertainty written with a Given value: checked when the request states one of its kind, else not read
                if b.value == 0:
                    continue
                shown = f"{'±' if gi in spread else ''}{b.number.text}{'%' if percent and b.unit is None else ''}{(' ' + b.unit.text) if b.unit is not None else ''}"
                unset.setdefault(b.statement_id, []).append((f"{name} = {shown} (an uncertainty: the request and its supplied texts state no uncertainty "
                                                             f"{'in per cent' if percent and b.unit is None else ('in ' + b.unit.text) if b.unit is not None else 'of its kind'})",
                                                             name, b.start, b.end))
                continue
            if meta is not None:
                cond_node = meta[1]
            else:
                cond_node = at_rel.condition.node if at_rel is not None and at_rel.condition is not None else self._condition_before(item)
            if cond_node is not None:
                # rule value-at: a Given stated under a condition ('oxygen uptake at 30 °C = 80 …', 'at t = 8 h, C = 820 …') is set against
                # the supplied table's cell at the row the condition names
                found = self._value_at_cells(set(_label_head(at_rel)) if at_rel is not None else set(name_words), cond_node, node, given=True)
                if found is not None:
                    cands_at, what, named = found
                    self.add(kind="giv", outcome="check", statement_ids=(b.statement_id,), start=b.start, end=b.end, op="=", right=Operand((node,), b.start, b.end),
                             left=Operand((Sym(named[:40] or "table", start=b.start, end=b.start),), b.start, b.start), candidates=cands_at,
                             exact_candidates=True, named=named,
                             reason=f"the Given value stated under its condition against {what}: the supplied data, taken as written (rule table-data, "
                                    "rule value-at" + ("; the Given written in prose: rule prose-given)" if meta is not None else ")"))
                    continue
            if meta is not None and meta[2]:
                # rule prose-given with rule named-given: the request names the quantity by the words of the Given's item ('Data: emf 15 V'
                # against 'a battery of emf 12 V'), so the Given is set against that quantity's value
                shown_q = " ".join(sorted(set().union(*(set(c.symbol.split()) for c in meta[2]))))
                self.add(kind="giv", outcome="check", statement_ids=(b.statement_id,), start=b.start, end=b.end, op="=", right=Operand((node,), b.start, b.end),
                         left=Operand((Sym(shown_q[:40], start=b.start, end=b.start),), b.start, b.start), candidates=tuple(meta[2][:8]), named=shown_q[:60],
                         reason=f"the Given value of {name}, written in prose, against the request's {shown_q} (matched by its words: rule named-given; rule "
                                "prose-given)")
                continue
            if meta is not None and not req_by_symbol.get(name):
                cands, against = self._given_candidates(name, b, word, percent, {}, frozenset(name_words))
                against += " (the Given written in prose: rule prose-given)"
            else:
                cands, against = self._given_candidates(name, b, word, percent, req_by_symbol, frozenset(name_words))
            if cands:
                mid_note = " (its central value, the Given being written with its uncertainty: rule central-value)" if gi in central else ""
                self.add(kind="giv", outcome="check", statement_ids=(b.statement_id,), start=b.start, end=b.end, op="=",
                         right=Operand((node,), b.start, b.end), left=Operand((Sym(name, start=b.start, end=b.start),), b.start, b.start),
                         candidates=tuple(cands[:8]), reason=f"the Given value of {name} against {against}{mid_note}")
                continue
            if meta is None and self._table_given(name, b, node):
                continue
            if b.value == 0:
                continue  # a zero the request states in words ('dropped from rest': u = 0), never a number it writes
            if b.unit is not None and b.unit.dim is not None and not b.unit.unknown:
                from .constants import match_written  # the booklet table (a leaf module: no cycle)
                f = b.unit.readings[0].factor if b.unit.readings and b.unit.readings[0].factor is not None else None
                if f is not None and match_written(b.value * f, b.number.half_width * abs(f), b.number.sig_figs, b.unit.dim, unit_given=True,
                                                   profile_key=self.profile.key) is not None:
                    continue  # a data-booklet constant (g = 9.81 m s⁻²): the booklet's value, not the request's
            shown = f"{b.number.text}{'%' if percent and b.unit is None else ''}{(' ' + b.unit.text) if b.unit is not None else ''}"
            unnamed = b.unit is not None and b.unit.dim is not None and any(
                (value_of(n) or (0, None, None, ""))[2] is not None and value_of(n)[2].dim is not None and value_of(n)[2].dim.same_physical(b.unit.dim)
                for n, _a, _b, _w in self.request.supplied_quantities)
            unset.setdefault(b.statement_id, []).append((f"{name} = {shown} ({_unset_reason(b, word, percent, unnamed)})", name, b.start, b.end))
        for sid, items in unset.items():
            many = len(items) > 1
            listed = ", ".join(x[0] for x in items[:-1]) + (" and " if many else "") + items[-1][0]
            self.finding("ST-UNDEC-003", f"the Given value{'s' if many else ''} {listed} in {sid} could not be set against the request: "
                                         f"{'they are' if many else 'it is'} not checked against the request", (sid,), items[0][2], items[-1][3])
        self._inline_givens(req_by_symbol)  # argument diagnostics: a given written inline in a substitution (section 3.4)

    def _request_functions(self) -> dict[str, tuple[str, Node, int, int]]:
        """Rule ``given-function`` (STEM repair 9): each function the request defines of one variable, written applied to that variable
        before '=' ('v(t) = 6t - 3t^2' in 'Its velocity, v m s^-1, at time t seconds is given by v(t) = 6t - 3t^2'), whose expression has
        no other symbol: name -> (its variable, its expression, the offsets of the definition in the request). The grammar reads a letter
        other than f, g or h applied to a bracket as a product, so the definition is read from that shape and the request's own text (as
        rule bound-relation reads a definition, :meth:`_defines_function`). A name defined twice keeps its first definition."""
        out: dict[str, tuple[str, Node, int, int]] = {}
        rtext = self.request.text
        for l_op, op, r_op in self.request.relations:
            if op != "=":
                continue
            left, right = _first(l_op), _first(r_op)
            fd = _function_definition(left, rtext)
            if fd is None or right is None or unsupported_reasons(right) or any(isinstance(n, (Apply, PlusMinus, Quantity, WithUnit)) for n in walk(right)):
                continue
            name, param = fd
            if name in out or not _syms(right) or _syms(right) - {param}:
                continue
            out[name] = (param, right, l_op.start, r_op.end)
        return out

    def _request_function_unit(self, name: str) -> Optional[UnitExpr]:
        """Rule given-function (STEM repair 9): the unit the request's prose states for the values of its function ``name`` ('Its velocity,
        v m s^-1, at time t seconds', 'v (m s⁻¹)', 'v, in m s⁻¹,'), else None."""
        text = self.request.text[:20_000]
        pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?:[ \t]*,?[ \t]*in|[ \t]*\()?[ \t]+(?P<u>[A-Za-zµμΩ°%][^,;:()\n=]{0,24}?)[ \t]*[,;)]")
        for m in pattern.finditer(text):
            unit = parse_unit(m.group("u").strip(), bare_m=self.profile.bare_m, tonne=self.profile.tonne)
            if unit is not None and not unit.unknown and unit.dim is not None:
                return unit
        return None

    def _given_function_value(self, node: Optional[Node]) -> bool:
        """Rule given-function (STEM repair 9): ``node`` writes a function's value at a number, ``v(1)``, ``v(1/2)``, ``f(2)`` (a letter glued
        to a bracketed closed expression, or f, g or h applied to one)."""
        if _applied_value(node, self.text) is not None:
            return True
        glued = _glued_bracket(node, self.text)
        return glued is not None and is_closed(glued[1])

    def _given_functions(self) -> None:
        """Rule ``given-function`` (STEM repair 9): a Given statement that gives a function's value ('Given: v(1) = 4 m s⁻¹.') or a
        function ('Given: v(t) = 6t − 2t².', and 'Given: v = 6t − 2t².' for a function the request defines) restates the request's data
        too, so it is set against the request's function of that name (:meth:`_request_functions`), as every Given is set against the
        request (rule given-kinds):
        * a function's value: the request's function at the Given's argument against the Given value, an ``eq`` check (the engine
          evaluates the request's expression), every written digit of the Given counting and τ = 0, in the unit the request's prose
          states for the function's values (a Given written with a unit the request states none for, or another dimension, is not read);
        * a function: the Given's expression against the request's, its variable renamed, for every value of the variable, an ``alg``
          check from the trivially true premise (it holds exactly when the two expressions agree everywhere, as rule antiderivative's).
        Both at warning severity (that the Given restates the request's function is a reading). A Given of a function's value or of a
        function the request defines none of (or defines with other symbols than its variable) is ST-UNDEC-003, as any Given the request
        states no value of its kind for. Before, the grammar read 'v(1)' and 'v(t)' as products, the statements as equations in
        unknowns, and they had neither a check nor an ST code, while the pack said every Given has one or the other."""
        if not self.request.text.strip():
            return
        given_sids = {it.statement_id for it in self.items if it.source == "given"}
        if not given_sids:
            return
        funcs: Optional[dict[str, tuple[str, Node, int, int]]] = None
        unset: dict[str, list[tuple[str, int, int]]] = {}
        done: set[tuple[int, int]] = set()
        for rel in list(self.relations):
            if not set(rel.statement_ids) & given_sids or rel.left is None or rel.right is None or rel.outcome == "check":
                continue
            left, right = rel.left.node, rel.right.node
            if left is None or right is None or (rel.start, rel.end) in done:
                continue
            value = _applied_value(left, self.text)
            glued = _glued_bracket(left, self.text) if value is None else None
            if glued is not None and is_closed(glued[1]):
                value, glued = glued, None  # 'v(1/2)', 'v(−1)': a function's value at a number written as an expression
            symbolic = glued or ((left.name, left.arg) if isinstance(left, Apply) and left.arg is not None and not is_closed(left.arg)
                                 and not isinstance(left.arg, Sym) else None)
            fdef = None if value is not None or symbolic is not None else _function_definition(left, self.text)
            lone = left.name if (value is None and fdef is None and symbolic is None and isinstance(left, Sym) and left.kind == "symbol"
                                 and rel.kind == "formula") else None
            if value is None and fdef is None and lone is None and symbolic is None:
                continue
            if funcs is None:
                funcs = self._request_functions()
            if symbolic is not None:
                # 'v(t + 1) = 4 m s⁻¹' for a function the request defines: a Given of its value at an argument that holds a symbol, so no
                # value of the request's function to set it against (a letter the request defines no function of is a product, as before)
                if symbolic[0] in funcs:
                    done.add((rel.start, rel.end))
                    shown_s = " ".join(self.text[rel.start:rel.end].split())[:80] if 0 <= rel.start < rel.end <= len(self.text) else render(left)
                    unset.setdefault(rel.statement_ids[-1], []).append((f"function value {shown_s} (its argument holds a symbol, so it names no "
                                                                       f"value of the request's {symbolic[0]})", rel.start, rel.end))
                continue
            sid = rel.statement_ids[-1]
            shown = " ".join(self.text[rel.start:rel.end].split())[:80] if 0 <= rel.start < rel.end <= len(self.text) else render(left)
            name = value[0] if value is not None else fdef[0] if fdef is not None else lone
            definition = funcs.get(name or "")
            if lone is not None and definition is None:
                continue  # a Given formula of a symbol the request defines no function of: no Given value (as before)
            done.add((rel.start, rel.end))
            base = dict(statement_ids=(sid,), start=rel.start, end=rel.end, part=rel.part, op="=")
            if definition is None:
                unset.setdefault(sid, []).append((f"{'function value' if value is not None else 'function'} {shown} (the request defines no "
                                                  f"function {name} of one variable)", rel.start, rel.end))
                continue
            param, rexpr, _a, _b = definition
            where = f"the request's {name}({param}) = {render(rexpr)[:60]}"
            if value is not None:
                arg = value[1]
                if any(isinstance(n, (Quantity, WithUnit)) for n in walk(arg)) or not is_closed(arg):
                    unset.setdefault(sid, []).append((f"function value {shown} (its argument is written with a unit, while the request's "
                                                      f"variable {param} is written bare)", rel.start, rel.end))
                    continue
                w = value_of(right) if is_value(right) else None
                if w is None or w[1] is None or w[3]:
                    continue  # the Given states no single value for it ('v(1) = 6(1) − 3(1)²' is an evaluation, not a Given value)
                unit = self._request_function_unit(name)
                evaluated = replace_symbol(rexpr, param, arg)
                if evaluated is None or not is_closed(evaluated):
                    continue
                if w[2] is not None:
                    if unit is None or w[2].unknown or w[2].dim is None or not w[2].dim.same_physical(unit.dim):
                        why = ("the request states no unit for the values of " + name if unit is None
                               else f"its unit is not of the dimension of the request's unit for {name}, {unit.text}")
                        unset.setdefault(sid, []).append((f"function value {shown} ({why})", rel.start, rel.end))
                        continue
                    evaluated = WithUnit(evaluated, unit, rel.start, rel.start)
                b = dict(base)
                b["left"] = Operand((evaluated,), rel.left.start, rel.left.end)
                b["right"] = rel.right
                self.add(kind="eq", outcome="check", title="the request's function at the Given's argument, against the Given value",
                         reason=f"the Given value of {name}({render(arg)[:12]}) against {where} at {param} = {render(arg)[:20]}"
                                + (f", its values in {unit.text} as the request states" if w[2] is not None and unit is not None else "")
                                + " (rule given-function)", **b)
                continue
            gparam = fdef[1] if fdef is not None else param
            why = ("its expression is written with a unit" if any(isinstance(n, (Quantity, WithUnit)) for n in walk(right))
                   else f"its expression has symbols other than its variable {gparam}" if _syms(right) - {gparam}
                   else "its expression is outside the encodings" if unsupported_reasons(right) or any(isinstance(n, (Apply, PlusMinus)) for n in walk(right))
                   else "")
            if why:
                unset.setdefault(sid, []).append((f"function {shown} ({why})", rel.start, rel.end))
                continue
            renamed = replace_symbol(rexpr, param, Sym(gparam)) if gparam != param else rexpr
            if renamed is None:
                continue
            gop = Operand((right,), rel.right.start, rel.right.end)
            b = dict(base)
            b["left"] = gop
            b["right"] = Operand((renamed,), rel.right.start, rel.right.end)
            self.add(kind="alg", outcome="check", premise_left=gop, premise_op="=", premise_right=gop, premise_ids=(sid,), explicit=True,
                     identity=(gparam,), title="the Given function against the request's function",
                     reason=f"the Given function {shown} against {where}, for every value of {gparam} (rule given-function)", **b)
        for sid, items in unset.items():
            many = len(items) > 1
            listed = ", ".join(x[0] for x in items[:-1]) + (" and " if many else "") + items[-1][0]
            self.finding("ST-UNDEC-003", f"the Given {listed} in {sid} could not be set against the request: {'they are' if many else 'it is'} not "
                                         "checked against the request", (sid,), items[0][1], items[-1][2])

    def _answer_values_before(self, pos: int) -> list[tuple[Fraction, Optional[UnitExpr], Fraction]]:
        """Rule same-shape and rule unbound-substitution (STEM repair 11): the values the answer states before offset ``pos`` (a value given
        to any symbol, a chain's result, a value its prose states), as ``(value as written, unit, half-width)``."""
        out: list[tuple[Fraction, Optional[UnitExpr], Fraction]] = []
        for blist in self.scope.bindings.values():
            for b in blist:
                if b.source not in ("request", "substitution") and b.end <= pos:
                    out.append((b.value, b.unit, b.number.half_width))
        for pv in self.prose_values:
            if pv.end <= pos:
                v = value_of(pv.node)
                if v is not None and v[1] is not None:
                    out.append((v[0], v[2], v[1].half_width))
        return out

    def _same_shapes(self) -> None:
        """Rule ``same-shape`` (STEM repair 11): a line of working puts, where another evaluation of the same expression in the answer (or
        the request) writes a value the request states, a value that neither the request nor the answer states before the line ('$4500(1.036)^{11}
        = 6640.03$' beside '$4000(1.036)^{12} = 6114.73$', the request's principal 4000 euros): the two computed sides have one shape (the same
        operators, units and integer powers, each numeral a slot) and differ in that slot and at most one other (the argument the answer
        varies, the 11 and 12 years). The numeral is set against the request's value (a ``giv`` check, the data as written, at warning
        severity: that the line evaluates the same expression with the request's datum in that place is a reading). Before, a wrong given
        substituted in a line with no symbol had neither a check nor an ST code (the line's arithmetic holds). A line under a condition or a
        hypothesis ('If Kai invested 4500 euros, …') is not read."""
        req: dict[Fraction, tuple[ExactNumber, Optional[UnitExpr], str]] = {}
        for node, _a, _b, _w in self.request.values:
            v = value_of(node)
            if v is None or v[1] is None:
                continue
            shown = " ".join(self.request.text[_a:_b].split())[:30]
            if v[3] == "%" and v[2] is None:
                # a per cent the request states is data in its decimal and in the growth and decay factors 1 ± the decimal (as rule
                # operand-precision for given data reads it: '3.6%' gives 0.036, 1.036 and 0.964)
                p = v[0] / 100
                # the forms are written to the per cent's own precision (3.6% is 0.036 ± 0.0005, so 1.036 ± 0.0005): rule given-data reads a
                # value against them as the data written there, every digit of the per cent counting
                place = (v[1].last_place if (v[1].has_point or v[1].scientific) else 0) - 2
                for form in (p, 1 + p, 1 - p):
                    shown_form = _fraction_text(form)
                    digits = shown_form.lstrip("-").replace(".", "").lstrip("0") or "0"
                    req.setdefault(form, (ExactNumber(text=shown_form, value=form, sig_figs=len(digits), last_place=place, exact=False, has_point=True,
                                                      digit_count=len(digits)), None, f"{shown}, as {shown_form}"))
                continue
            if v[3]:
                continue
            req.setdefault(v[0], (v[1], v[2], shown))
        if not req:
            return
        shapes: list[tuple[str, tuple[tuple[Fraction, Optional[Node]], ...], Relation]] = []
        for rel in self.relations:
            for op in (rel.left, rel.right):
                node = op.node if op is not None else None
                if node is None or not is_closed(node) or is_value(node):
                    continue
                sh = _shape_slots(node)
                if sh is not None and len(sh[1]) >= 2:
                    shapes.append((sh[0], sh[1], rel))
        planned = {(r.start, r.end) for r in self.relations if r.kind == "giv"}
        for rel in list(self.relations):
            if rel.kind != "eq" or rel.outcome != "check" or rel.title or rel.left is None or rel.left.node is None or rel.position != 0:
                continue
            sh = _shape_slots(rel.left.node)
            if sh is None or len(sh[1]) < 2:
                continue
            st = self._statement_head(rel.statement_ids[-1], rel.start) if rel.statement_ids else ""
            if _UNSTATED_RE.search(st[-160:]):
                continue
            stated = self._answer_values_before(rel.start)
            for shape, slots, other in shapes:
                if other is rel or shape != sh[0] or len(slots) != len(sh[1]):
                    continue
                diffs = [k for k, (x, y) in enumerate(zip(sh[1], slots)) if x[0] != y[0]]
                shared = [k for k, (x, y) in enumerate(zip(sh[1], slots)) if x[0] == y[0] and x[1] is not None]
                if not 1 <= len(diffs) <= 2 or not shared:
                    continue  # the two evaluations share a written numeral (the same data) and differ in at most two places
                for k in diffs:
                    a_val, a_node = sh[1][k]
                    r_val, _rn = slots[k]
                    if a_node is None or not isinstance(a_node, (Num, Quantity)) or r_val not in req or a_val in req:
                        continue
                    if any(sv == a_val for sv, _u, _h in stated):
                        continue  # a value the answer states before the line (a result it carries): no datum replaced
                    if (a_node.start, a_node.end) in planned:
                        continue
                    num, unit, shown = req[r_val]
                    cand = Binding("the request's value", r_val, num, unit, "request", "request")
                    osid = other.statement_ids[-1] if other.statement_ids else ""
                    self.add(kind="giv", outcome="check", statement_ids=rel.statement_ids, start=a_node.start, end=a_node.end, op="=",
                             right=Operand((a_node,), a_node.start, a_node.end), left=Operand((Sym("the datum", start=a_node.start, end=a_node.start),),
                                                                                             a_node.start, a_node.start),
                             candidates=(cand,), part=rel.part,
                             title="the value the working writes, against the request's value its other evaluation of the expression writes there",
                             reason=f"the value {a_node.number.text} the working puts where its evaluation of the same expression in {osid} writes the "
                                    f"request's value ({shown}), a value neither the request nor the answer states before the line, against that "
                                    f"value (rule same-shape)")
                    planned.add((a_node.start, a_node.end))

    def _unbound_substitutions(self) -> None:
        """Rule ``unbound-substitution`` (STEM repair 11): a symbol the answer gives no value stands for one quantity, so the values the
        answer substitutes for it must agree. When the answer substitutes for it, elsewhere, the request's value of a quantity the request
        names with one value ('V = 12 V − (4.14 A × 0.50 Ω)' puts the request's internal resistance, 0.50 ohm, for r), every other value it
        substitutes for that symbol that is none of the request's values of its dimension and none the answer states before the line ('R + r =
        2.4 Ω + 0.40 Ω') is set against that request value (a ``giv`` check, the data as written, at warning severity: that the symbol stands
        for that quantity throughout is a reading). Before, a symbol with no binding matched nothing, so another value in place of the given
        held (its arithmetic right), named one line later at best. A value the working derives without stating it (a total volume, 50.0 cm³ +
        5.0 cm³, put for V) is not read: nothing ties the symbol to one request value. Nor is a symbol whose request-value substitutions are of
        a quantity the request gives two values ('two resistors of 4.0 ohm and 6.0 ohm': R stands for each in turn), a zero, a value with no
        unit, or a substitution under a condition or a hypothesis."""
        named = [(q, "request") for q in self.request.named_quantities] + [(q, "supplied") for q in self.request.supplied_named]
        if not named:
            return
        by_name: dict[tuple[str, ...], list[Binding]] = {}
        for (qnode, a0, b0, qwords), source in named:
            qv = value_of(qnode)
            if qv is None or qv[1] is None or qv[2] is None or qv[2].unknown or qv[2].dim is None or not qwords:
                continue
            by_name.setdefault(tuple(qwords), []).append(Binding(" ".join(qwords), qv[0], qv[1], qv[2], source, source, a0, b0, wrapper=qv[3]))
        req = [b for bs in by_name.values() for b in bs if b.si is not None]
        if not req:
            return

        def h_si(bd: Binding) -> Fraction:
            f = abs(bd.unit.readings[0].factor) if bd.unit is not None and bd.unit.readings and bd.unit.readings[0].factor is not None else 1
            return bd.number.half_width_for(_EVERY_DIGIT_R) * f

        def request_match(bd: Binding, si: Fraction) -> list[Binding]:
            return [b for b in req if b.unit is not None and b.unit.dim is not None and b.unit.dim.same_physical(bd.unit.dim)
                    and abs(si - b.si) <= h_si(bd)]

        planned = {(r.start, r.end) for r in self.relations if r.kind == "giv"}
        heads: dict[str, str] = {}
        for name, readings in self.scope.substitutions.items():
            if self.scope.bindings.get(name):
                continue
            usable: list[tuple[Binding, Fraction]] = []
            for bd in readings:
                unit = bd.unit
                if unit is None or unit.unknown or unit.dim is None or bd.value == 0 or not unit.readings or unit.readings[0].factor is None:
                    continue
                si = si_value(bd.value, unit, bd.wrapper)
                if si is None:
                    continue
                if bd.statement_id not in heads:
                    heads[bd.statement_id] = self._statement_head(bd.statement_id, bd.start)
                if _UNSTATED_RE.search(heads[bd.statement_id][-160:]):
                    continue
                usable.append((bd, si))
            # the symbol's tie: the request quantities, named with one value each, whose value the answer substitutes for it
            ties: dict[tuple[str, ...], Binding] = {}
            for bd, si in usable:
                for b in request_match(bd, si):
                    words = tuple(b.symbol.split())
                    values = {x.si for x in by_name.get(words, [])}
                    if len(values) == 1:
                        ties[words] = b
            if len(ties) != 1 or len({b.si for b in ties.values()}) != 1:
                continue
            tie = next(iter(ties.values()))
            tie_sids = sorted({bd.statement_id for bd, si in usable if request_match(bd, si)})
            for bd, si in usable:
                if (bd.start, bd.end) in planned or request_match(bd, si):
                    continue  # the request's value: the data as written
                if bd.unit is None or tie.unit is None or not bd.unit.dim.same_physical(tie.unit.dim):
                    continue
                stated = self._answer_values_before(bd.start)
                if any(u is not None and not u.unknown and u.dim is not None and u.dim.same_physical(bd.unit.dim) and u.readings
                       and u.readings[0].factor is not None and si_value(v, u, "") is not None
                       and abs(si - si_value(v, u, "")) <= h_si(bd) + h * abs(u.readings[0].factor) for v, u, h in stated):
                    continue  # a value the answer states before the line
                node = Quantity(bd.number, bd.unit, bd.start, bd.end)
                sid = bd.statement_id
                shown = " ".join(self.request.text[tie.start:tie.end].split())[:40] if tie.source == "request" else tie.symbol
                self.add(kind="giv", outcome="check", statement_ids=(sid,), start=bd.start, end=bd.end, op="=",
                         right=Operand((node,), bd.start, bd.end), left=Operand((Sym(name, start=bd.start, end=bd.start),), bd.start, bd.start),
                         candidates=(tie,), part=self.part_of.get(sid, ""),
                         title="the value the working substitutes for a symbol with no value, against the request's value it substitutes for the "
                               "symbol elsewhere",
                         reason=f"the value {' '.join(self.text[bd.start:bd.end].split())} the working substitutes for {name}, a symbol the answer "
                                f"gives no value, against the request's {tie.symbol} ({shown}), the value the answer substitutes for {name} in "
                                f"{', '.join(tie_sids[:3])}: it is no request value and no value the answer states before the line "
                                f"(rule unbound-substitution)")
                planned.add((bd.start, bd.end))

    def _statement_head(self, sid: str, pos: int) -> str:
        """The text of the answer's statement ``sid`` before offset ``pos`` (empty when unknown): the clause a value is stated under."""
        for it in self.items:
            if it.statement_id == sid:
                return it.statement_text[:max(0, pos - it.statement_start)]
        return ""

    def _answer_functions(self) -> list[tuple[str, str, Node, int, str]]:
        """Rule ``function-value`` (STEM repair 11): the functions the answer defines of one variable, written applied to it before '='
        ('v(t) = 6t − 3t²', 'f(x) = x² + 1'), whose expression has no other symbol: ``(name, variable, expression, offset, statement)``, in
        document order."""
        out: list[tuple[str, str, Node, int, str]] = []
        for rel in self.relations:
            if rel.left is None or rel.right is None or rel.op != "=" or rel.position != 0:
                continue
            left, right = rel.left.node, rel.right.node
            fd = _function_definition(left, self.text)
            if fd is None or right is None or unsupported_reasons(right) or any(isinstance(n, (Apply, PlusMinus, Quantity, WithUnit)) for n in walk(right)):
                continue
            if not _syms(right) or _syms(right) - {fd[1]}:
                continue
            out.append((fd[0], fd[1], right, rel.start, rel.statement_ids[-1]))
        return out

    def _defined_function_value(self, node: Optional[Node]) -> bool:
        """Rule function-value (STEM repair 11): ``node`` writes the value at a number of a function the request or the answer defines of one
        variable (``v(1)``, ``v(1/2)``): a function's value, never a product of a letter and a number."""
        if not self._given_function_value(node):
            return False
        name = (_applied_value(node, self.text) or _glued_bracket(node, self.text) or ("",))[0]
        if not name:
            return False
        if self._request_fn_names is None:
            self._request_fn_names = frozenset(self._request_functions())
        return name in self._request_fn_names or any(n == name for n, *_r in self._answer_functions())

    def _function_values(self) -> None:
        """Rule ``function-value`` (STEM repair 11): a statement, any statement, that states the value of a function at a number ('The velocity
        at t = 1 is v(1) = 4 m s⁻¹.', 'At t = 2 the particle is at rest: v(2) = 1.', 'v(2) = 6(2) − 3(2)²') for a function of one variable the
        answer defines before it ('v(t) = 6t − 3t²') or, failing that, the request defines ('v(t) = 6t - 3t^2'): an ``eq`` check of the
        function's expression at the written argument (the engine evaluates it) against the stated value or expression, the stated value's
        unit the one the request's prose states for the function's values. Against the answer's own definition a failure is an error; against
        the request's, a warning (that the answer's letter is the request's function is a reading). Rule given-function read Given
        statements only; before, the grammar read 'v(1)' as the product v·1, the statement as an equation in an unknown, and a wrong value
        of the request's function stated in the working had neither a check nor an ST code. A function's value at an argument holding a
        symbol, and a letter neither defines as a function, are not read (as before)."""
        if self.request_mode:
            return
        given_sids = {it.statement_id for it in self.items if it.source == "given"}
        rfuncs: Optional[dict[str, tuple[str, Node, int, int]]] = None
        afuncs: Optional[list[tuple[str, str, Node, int, str]]] = None
        done: set[tuple[int, int]] = set()
        for rel in list(self.relations):
            if rel.left is None or rel.right is None or rel.outcome == "check" or rel.position != 0 or set(rel.statement_ids) & given_sids:
                continue
            if rel.op != "=" or (rel.start, rel.end) in done:
                continue
            left, right = rel.left.node, rel.right.node
            if left is None or right is None:
                continue
            value = _applied_value(left, self.text)
            if value is None:
                glued = _glued_bracket(left, self.text)
                value = glued if glued is not None and is_closed(glued[1]) else None
            if value is None:
                continue
            name, arg = value
            if any(isinstance(n, (Quantity, WithUnit)) for n in walk(arg)) or not is_closed(arg) or unsupported_reasons(arg):
                continue
            if not is_closed(right) or unsupported_reasons(right):
                continue
            if afuncs is None:
                afuncs = self._answer_functions()
            own = [f for f in afuncs if f[0] == name and f[3] < rel.start]
            if own:
                _n, param, expr, _a, fsid = own[-1]
                where, request_fn, unit = f"the answer's {name}({param}) = {render(expr)[:60]} in {fsid}", False, None
            else:
                if rfuncs is None:
                    rfuncs = self._request_functions()
                if name not in rfuncs:
                    continue
                param, expr, _a, _b = rfuncs[name]
                where, request_fn, unit = f"the request's {name}({param}) = {render(expr)[:60]}", True, self._request_function_unit(name)
            evaluated = replace_symbol(expr, param, arg)
            if evaluated is None or not is_closed(evaluated):
                continue
            w = value_of(right) if is_value(right) else None
            if w is not None and w[2] is not None:
                if unit is None or w[2].unknown or w[2].dim is None or not w[2].dim.same_physical(unit.dim):
                    continue  # a stated value with a unit the function's values are not stated in: not read
                evaluated = WithUnit(evaluated, unit, rel.start, rel.start)
            elif any(isinstance(n, (Quantity, WithUnit)) for n in walk(right)):
                continue
            done.add((rel.start, rel.end))
            sids = rel.statement_ids if request_fn else tuple(dict.fromkeys(rel.statement_ids + (fsid,)))
            b = dict(statement_ids=sids, start=rel.start, end=rel.end, part=rel.part, op="=",
                     left=Operand((evaluated,), rel.left.start, rel.left.end), right=rel.right)
            self.add(kind="eq", outcome="check", title="the function's value at the written argument, against the value stated",
                     reason=f"the value of {name}({render(arg)[:12]}) the statement gives, against {where} at {param} = {render(arg)[:20]}"
                            + (f", its values in {unit.text} as the request states" if w is not None and w[2] is not None and unit is not None else "")
                            + (" (rule function-value, the request's function)" if request_fn else " (rule function-value)"), **b)

    def _uncertainty_candidates(self, name: str, b: Binding, percent: bool) -> list[Binding]:
        """Rule given-uncertainty (STEM repair 3): the uncertainties the request and its supplied texts state that a Given uncertainty
        may restate: those of its dimension for a Given with a unit, the percentages for one written with a per cent sign. Which one
        it restates is a reading (the check holds when it matches any)."""
        out: list[Binding] = []
        for source, rows in (("request", self.request.request_uncertainties), ("supplied", self.request.supplied_uncertainties)):
            for node, a0, b0, unit, wrapper, _words in rows:
                v = value_of(node)
                if v is None or v[1] is None:
                    continue
                if percent and b.unit is None:
                    if wrapper == "%" or v[3] == "%":
                        out.append(Binding(name, v[0], v[1], None, source, source, a0, b0, wrapper="%"))
                elif b.unit is not None and b.unit.dim is not None and not b.unit.unknown and unit is not None and unit.dim is not None \
                        and unit.dim.same_physical(b.unit.dim):
                    out.append(Binding(name, v[0], v[1], unit, source, source, a0, b0))
        return out

    def _condition_before(self, item: Optional[MathItem]) -> Optional[Node]:
        """The condition a Given of a statement is stated under (rule value-at): the value of the condition item ('at t = 8 h') that
        comes right before the Given's item in its statement, joined by a comma or 'then' ('Given: at t = 8 h, C = 820 …')."""
        if item is None or item.index == 0:
            return None
        prev = self.items[item.index - 1] if item.index - 1 < len(self.items) else None
        if prev is None or prev.statement_id != item.statement_id or prev.source != "condition" or item.gap_before.strip(" ,;").lower() not in ("", "then"):
            return None
        for ch in prev.chains:
            if len(ch.operands) == 2 and ch.ops and ch.ops[0] == "=":
                v = _first(ch.operands[1])
                if v is not None and is_value(v):
                    return v
        return None

    def _prose_condition(self, pv: ProseValue, cond_at: Optional[int]) -> Optional[Node]:
        """Rule ``prose-given`` (STEM repair 6): the value of the condition a prose Given is stated under (``cond_at``, its offset in the
        value's ``before``): the prose value or the maths run ('at t = 8 h') written there, else None."""
        if cond_at is None:
            return None
        at = pv.start - len(pv.before) + cond_at
        for other in self.prose_values:
            if other.statement_id == pv.statement_id and other.start == at:
                return other.node
        for it in self.items:
            if it.statement_id == pv.statement_id and it.start == at:
                for ch in it.chains:
                    if len(ch.operands) == 2 and ch.ops and ch.ops[0] == "=":
                        v = _first(ch.operands[1])
                        if v is not None and is_value(v):
                            return v
        return None

    def _given_candidates(self, name: str, b: Binding, word: str, percent: bool, req_by_symbol: dict,
                          name_words: frozenset[str] = frozenset()) -> tuple[list[Binding], str]:
        cands: list[Binding] = list(req_by_symbol.get(name, []))
        if cands:
            return cands, "the request's binding of the same symbol"
        # STEM repair 3 (rule supplied-values): a value a supplied text states is a candidate when the Given's name shares a word with its
        # sentence ('volume of thiosulfate' and 'Each trial: 50.0 cm3 of … sodium thiosulfate solution'); a Given that names nothing the
        # supplied text writes (a symbol alone: 'C0 = 1600 counts min⁻¹') is not set against it
        supplied_q = [(n, a0, b0) for n, a0, b0, ws in self.request.supplied_quantities if name_words & ws]
        supplied_v = [(n, a0, b0, w) for n, a0, b0, w, ws in self.request.supplied_values if name_words & ws]
        values = [(x, "request") for x in self.request.values] + [(x, "supplied") for x in supplied_v]
        if b.unit is not None and b.unit.dim is not None and not b.unit.unknown:
            supplied = False
            for source, quantities in (("request", self.request.quantities), ("supplied", supplied_q)):
                for node, a0, b0 in quantities:
                    v = value_of(node)
                    if v is None or v[2] is None or v[1] is None or v[2].dim is None:
                        continue
                    if v[2].dim.same_physical(b.unit.dim):
                        cands.append(Binding(name, v[0], v[1], v[2], source, source, a0, b0, wrapper=v[3]))
                        supplied = supplied or source == "supplied"
            # STEM repair 3 (rule supplied-values): the quantities a text supplied with the request states in its prose are the request's too
            return cands, "the request's quantities of the same dimension" + (" (with those its supplied texts state: rule supplied-values)" if supplied else "")
        if b.unit is not None:
            return [], ""  # a unit the table does not read: its kind is unknown
        def pick(test) -> list[Binding]:
            out = []
            for (node, a0, b0, w), source in values:
                v = value_of(node)
                if v is None or v[1] is None or not test(v, w):
                    continue
                out.append(Binding(name, v[0], v[1], v[2], source, source, a0, b0, wrapper="%" if (v[3] == "%" or w == "%") else v[3]))
            return out
        if percent:
            got = pick(lambda v, w: v[2] is None and (v[3] == "%" or w == "%"))
            return got, "the request's percentages (rule given-kinds)" + (" (with those its supplied texts state: rule supplied-values)"
                                                                           if any(c.source == "supplied" for c in got) else "")
        if word:
            return pick(lambda v, w: v[2] is None and v[3] != "%" and w == word), f"the request's numbers written with '{word}' (rule given-kinds)"
        same = [c for c in pick(lambda v, w: (v[2] is None or v[2].dim is None) and v[3] != "%" and w != "%") if c.value == b.value and c.source == "request"]
        return same, "the request's number it equals, which a bare Given restates (rule given-kinds)"

    def _table_given(self, name: str, b: Binding, node: Node) -> bool:
        """Rule table-data for a Given (STEM repair 2): a Given whose symbol is the key of a row of a supplied table and whose label
        names one of its columns ('Given: dissolved oxygen at C = 3.5 mg dm⁻³') is set against that cell, the data taken as written."""
        if not self.request.tables:
            return False
        item = next((it for it in self.items if it.statement_id == b.statement_id and it.start <= b.start <= it.end), None)
        label = (item.gap_before if item is not None else "")[-120:]
        words = set(re.findall(r"[a-z]+", label.lower()))
        for table in self.request.tables:
            row = table.row_for(name, None)
            if row is None:
                continue
            cols = [j for j in table.value_columns() if table.columns[j].words and table.columns[j].words <= words]
            if len(cols) != 1:
                continue
            col = table.columns[cols[0]]
            if b.unit is not None and col.unit is not None and not col.unit_ascii and (b.unit.dim is None or col.unit.dim is None
                                                                                       or not b.unit.dim.same_physical(col.unit.dim)):
                continue
            cell = table.rows[row][cols[0]][1]
            if cell is None:
                continue
            cand = Binding(col.name[:40] or "table", cell.value, cell, _cell_unit(col.unit, b.unit), "request", "request", 0, 0)
            self.add(kind="giv", outcome="check", statement_ids=(b.statement_id,), start=b.start, end=b.end, op="=", right=Operand((node,), b.start, b.end),
                     left=Operand((Sym(col.name[:40] or "table", start=b.start, end=b.start),), b.start, b.start), candidates=(cand,),
                     exact_candidates=True, named=col.name[:60],
                     reason=f"the Given value against {col.name} at the supplied table's row {table.rows[row][0][0]} ({cell.text}): the supplied data, "
                            "taken as written (rule table-data)")
            return True
        return False

    def _named_givens(self) -> None:
        """Rule ``named-given`` (STEM repair 2): a value the prose states for a quantity the request names by its words ("The battery's
        emf is 9.0 V" for "a battery of emf 12 V"; "the internal resistance is 0.40 Ω" for "internal resistance 0.50 ohm") is set
        against the request's value of that name and dimension, at warning severity (the quantity is matched by its words). The
        prose names the quantity right before a copula ('is', 'was', 'of', '=') and the value; nothing when no request quantity, or
        more than one with different values, carries every word of the name."""
        named = [(q, "request") for q in self.request.named_quantities] + [(q, "supplied") for q in self.request.supplied_named]
        if not named or not self.prose_values:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind in ("res", "giv")}
        for pv in self.prose_values:
            if (pv.start, pv.end) in planned:
                continue
            m = _NAMED_GIVEN_RE.search(pv.before[-80:])
            if m is None:
                continue
            v = value_of(pv.node)
            if v is None or v[2] is None or v[2].dim is None:
                continue
            words = set(_name_words(m.group("name")))
            cands = []
            for (node, a0, b0, qwords), source in named:
                qv = value_of(node)
                if qv is None or qv[2] is None or qv[2].dim is None or not qwords or not set(qwords) <= words or not qv[2].dim.same_physical(v[2].dim):
                    continue
                cands.append(Binding(" ".join(qwords), qv[0], qv[1], qv[2], source, source, a0, b0, wrapper=qv[3]))
            if not cands:
                continue
            shown = " ".join(sorted(set().union(*(set(c.symbol.split()) for c in cands))))
            self.add(kind="giv", outcome="check", statement_ids=(pv.statement_id,), start=pv.start, end=pv.end, op="=", right=Operand((pv.node,), pv.start, pv.end),
                     left=Operand((Sym(shown[:40], start=pv.start, end=pv.start),), pv.start, pv.start), candidates=tuple(cands[:8]), named=shown[:60],
                     part=pv.part, reason=f"the value the prose states for the {shown} against the request's {shown} (matched by its words: rule named-given)")

    def _named_results(self) -> None:
        """Rule ``named-result`` (STEM repair 9): the value the answer gives a quantity the request names, as the final value of a chain
        (computed, or stated for a symbol) whose quantity the answer names by the prose right before its run, by its label, or by a symbol
        it substituted the request's value for (:meth:`_request_quantity`), is set against the request's value of that quantity, as rule
        named-given sets a value the prose states: a ``giv`` check at warning severity (which quantity the value is of is a reading), every
        written digit counting. 'So r = (ε + V)/I = (12 V + 9.93 V)/4.14 A = 5.3 Ω.', 'r = (12 V + 9.93 V)/4.14 A = 5.3 Ω' and 'So the
        internal resistance is (12 V + 9.93 V)/4.14 A = 5.3 Ω.' fail against the request's internal resistance of 0.50 ohm; before, only
        their arithmetic was checked, which holds, while 'So the internal resistance is 5.3 Ω.' was named (rule named-given). A Given
        statement is set against the request by rule given-kinds instead; nothing is read with no request (the relay form)."""
        if not self.request.text.strip() or not (self.request.named_quantities or self.request.supplied_named) or not self.final_values:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind in ("giv", "res", "tgt") and r.outcome == "check"}
        given_sids = {it.statement_id for it in self.items if it.source == "given"}
        items_of = self._items_by_statement()
        for fv in self.final_values:
            op = fv["operand"]
            if fv["sid"] in given_sids or (op.start, op.end) in planned:
                continue
            tie = self._request_quantity(fv, items_of)
            if tie is None:
                continue
            shown, cands, how, _qwords = tie
            planned.add((op.start, op.end))
            node = fv["node"]
            by = ("by its words" if how == "words" else "by its label" if how == "label"
                  else f"by the symbol {how.split(' ', 1)[1]}, for which the answer substituted the request's value")
            self.add(kind="giv", outcome="check", statement_ids=(fv["sid"],), start=op.start, end=op.end, op="=", right=Operand((node,), op.start, op.end),
                     left=Operand((Sym(shown[:40], start=op.start, end=op.start),), op.start, op.start), candidates=cands, named=shown[:60],
                     part=fv["part"], reason=f"the value the answer gives the {shown} against the request's {shown} (matched {by}: rule named-result)")

    def _restated_units(self) -> None:
        """Rule ``restated-unit`` (STEM repair 3): a value the answer states (in prose, or for a symbol or a named quantity outside a
        Given) whose number is the number of a quantity the request or a text supplied with it states, with a unit of the same
        dimension but another size ('the background of 20 counts s⁻¹' where the task states 20 counts per minute), restates that
        quantity with the wrong unit: a ``giv`` check against it in SI, at warning severity (that the value restates the task's
        quantity is a reading), which fails. A value written with the task's own unit, or with another number, plans nothing (a
        conversion states another number); temperatures are left out (a change of 20 K is a change of 20 °C)."""
        quantities = [(q, "request") for q in self.request.quantities] + [((n, a0, b0), "supplied") for n, a0, b0, _w in self.request.supplied_quantities]
        if not quantities:
            return
        planned = {(r.start, r.end) for r in self.relations if r.kind in ("res", "giv", "cnv")}
        given_sids = {it.statement_id for it in self.items if it.source == "given"}
        stated: list[tuple[str, Node, int, int, str, str]] = []
        for pv in self.prose_values:
            stated.append((pv.statement_id, pv.node, pv.start, pv.end, pv.part, "the value the prose states"))
        for rel in self.relations:
            if rel.outcome == "binding" and rel.kind in ("binding", "label") and rel.right is not None and rel.right.node is not None \
                    and is_value(rel.right.node) and not set(rel.statement_ids) & given_sids:
                stated.append((rel.statement_ids[-1], rel.right.node, rel.right.start, rel.right.end, rel.part, "the value the answer states"))
        for sid, node, a, b, part, what in stated:
            if (a, b) in planned:
                continue
            v = value_of(node)
            u = v[2] if v is not None else None
            if u is None or u.unknown or u.dim is None or len(u.readings) != 1 or u.readings[0].factor is None or u.readings[0].affine is not None \
                    or _temperature(u):
                continue
            cands = []
            for (qnode, a0, b0), source in quantities:
                q = value_of(qnode)
                qu = q[2] if q is not None else None
                if qu is None or qu.unknown or qu.dim is None or len(qu.readings) != 1 or qu.readings[0].factor is None or qu.readings[0].affine is not None \
                        or _temperature(qu) or not qu.dim.same_physical(u.dim) or q[1] is None or q[1].value != v[1].value or q[0] != v[0]:
                    continue
                if qu.readings[0].factor == u.readings[0].factor:
                    cands = []
                    break  # the task's own unit (or its spelling): the value restates the quantity, nothing to check
                cands.append(Binding(" ".join(qu.text.split())[:40], q[0], q[1], qu, source, source, a0, b0, wrapper=q[3]))
            if not cands:
                continue
            planned.add((a, b))
            src = "a text supplied with the request" if all(c.source == "supplied" for c in cands) else "the request"
            shown = ", ".join(f"{c.number.text} {c.unit.text}" for c in cands[:3])
            self.add(kind="giv", outcome="check", statement_ids=(sid,), start=a, end=b, op="=", right=Operand((node,), a, b),
                     left=Operand((Sym("the task's quantity", start=a, end=a),), a, a), candidates=tuple(cands[:8]), part=part,
                     title="the stated value against the task's quantity of the same number",
                     reason=f"{what}, {render(node)[:60]}, against the quantity {src} states with the same number ({shown}): the same number "
                            "written with another unit of that dimension (rule restated-unit)")

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

    # --------------------------------------------------------------------------- argument diagnostics: STEM method faults (section 3.4)

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

    def _chain_sub(self, operand: Operand) -> Optional[Relation]:
        """The substitution planned for the link just before this one in its chain (``v = 2.5/10`` before ``2.5/10 = 0.25 m s⁻¹``):
        its numeric side is this link's left operand (bounded look-back)."""
        for r in reversed(self.relations[-8:]):
            if r.kind == "sub" and (r.right is operand or r.left is operand):
                return r
        return None

    def _symbol_dim(self, name: str) -> Optional[Dimension]:
        dims = set()
        for b in [b for b in self.scope.bindings.get(name, ()) if b.source != "root"] or list(self.scope.substitutions.get(name, ())):
            if b.unit is None or b.unit.unknown or b.unit.dim is None:
                return None
            dims.add(b.unit.dim)
        return dims.pop() if len(dims) == 1 else None

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
            # Port onto the integrated translator (docs/ARGUMENT_DIAGNOSTICS.md section 20.7): the integrated check admits no as-written
            # reading its own units contradict (``checks._as_written_consistent``), so it already decides this relation in SI alone and
            # fails on the unit error; a ``written`` companion would only repeat that verdict, and none is planned
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
        hits = _operation_hits(gap)
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
                vals = [(node, qa) for node, qa, _qb, _w in self.request.values[:256] if m.end() <= qa < stop]
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

        for node, qa, qb, _w in self.request.values[:256]:
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
                data_figures = self._supplied_data_figures()
                for m in _YEAR_INPUT_RE.finditer(text[:4000]):
                    y = Fraction(int(m.group("y")))
                    if y in data_figures:
                        # a figure of the supplied data ('The uncertainty in 1620 is ±2% × 1620', a count rate of the table) is no year the
                        # model is evaluated at (port onto the integrated translator, which reads the supplied texts' tables and values)
                        continue
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

    def _supplied_data_figures(self) -> frozenset:
        """The figures the texts supplied with the request state as data (their tables' cells, their values and quantities): read
        once per document (port onto the integrated translator)."""
        cached = getattr(self, "_data_figures_cache", None)
        if cached is None:
            out: set = set()
            for table in self.request.tables:
                for row in table.rows:
                    for _text, num in row:
                        if num is not None:
                            out.add(num.value)
            for entry in tuple(self.request.supplied_values) + tuple(self.request.supplied_quantities):
                v = value_of(entry[0]) if entry and entry[0] is not None else None
                if v is not None:
                    out.add(v[0])
            cached = self._data_figures_cache = frozenset(out)
        return cached

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
        # a Given restates the request's data: it is no result the answer reached (port onto the integrated translator: an answer
        # made only of Givens states no result, so it lacks no working)
        given_sids = {it.statement_id for it in self.items if it.source == "given"}
        # so does a value the integrated readings set against the request's own value of that quantity (a Given in prose, rule
        # named-given: "The battery's emf is 12 V."): a restatement of the data, checked by its ``giv`` check, not a result
        given_sids |= {sid for r in self.relations if r.kind == "giv" for sid in r.statement_ids}
        prose_values = [pv for pv in self.prose_values if pv.statement_id not in given_sids]
        values = {(pv.statement_id, pv.start) for pv in prose_values}
        results = [(r.statement_ids[-1], v[0]) for r in self.relations if r.kind == "binding" and r.outcome == "binding" and r.right is not None
                   and r.statement_ids[-1] not in given_sids
                   and (n := _first(r.right)) is not None and is_value(n) and (v := value_of(n)) is not None]
        if working:
            return
        if values:
            distinct = {abs(value_of(pv.node)[0]) for pv in prose_values if value_of(pv.node) is not None}
            if len(distinct) > 1 and not distinct <= _request_numerals(self.request.text):
                return
            if judgement and distinct <= _request_numerals(self.request.text):
                return  # a yes/no question answered with the request's own figures and an argument: no value result is stated
            sids = tuple(dict.fromkeys(pv.statement_id for pv in prose_values))
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
        words = _phrase_words(_named_clause_tail(text), self.profile.chemistry)
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
                return _named_clause_tail(it.statement_text[a:rel.start - it.statement_start])
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
            # the values the answer substitutes for the symbol with a unit say what it stands for too ('V = 12 V − (4.14 A × 0.50 Ω)'
            # after 'V = ε − Ir': r is a resistance, never the radius the table gives the letter; port onto the integrated translator)
            stated_b = [b for b in self.scope.bindings.get(name, ()) if b.source != "root"] + list(self.scope.substitutions.get(name, ()))
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
            if len({b.value for b in blist if b.source in ("statement", "let")}) > 1:
                # a symbol the answer states several values of is a variable it tabulates or evaluates at ('t = 0 h', 't = 4 h', ...
                # rows of the answer's own table), never one given (port onto the integrated translator, recorded arena answer
                # ph-p7b); a symbol bound twice to two values is read by the rebinding checks instead
                continue
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

    _MAX_BARE_GIVEN_POOL = 2


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


#: rule named-change (STEM repair 1): a change the prose states with its starting value ("rises from 2.4 Ω", "falls, from 4.1 A")
_CHANGE_FROM_RE = re.compile(r"\b(?:rises|rose|risen|falls|fell|fallen|increases|increased|decreases|decreased|drops|dropped|changes|changed|grows|grew|"
                             r"reduces|reduced|climbs|climbed|declines|declined|goes\s+(?:up|down)|went\s+(?:up|down))\s*,?\s*from\s*$", re.IGNORECASE)
#: rule stated-uncertainty (STEM repair 4): 'an absolute uncertainty of 2% of the measured value'
_UNC_RULE_BEFORE_RE = re.compile(r"\buncertaint(?:y|ies)\s+(?:of\s+)?(?:about\s+|approximately\s+)?(?:±\s*|\+/-\s*)?$", re.IGNORECASE)
_UNC_RULE_AFTER_RE = re.compile(r"^\s*of\s+(?:the|each|its|every)\s+(?P<name>[A-Za-z][A-Za-z \-]{1,40}?)\s+(?:values?|readings?|counts?\s+rates?|rates?|"
                                r"measurements?)\b", re.IGNORECASE)
#: rule changed-value (STEM repair 4): the value a change ends at ('falls, from 4.1 A to 2.7 A', 'falls to 2.7 A', 'becomes 2.7 A', 'is now 2.7 A')
_CHANGE_TO_RE = re.compile(r"\b(?:(?:rises|rose|risen|falls|fell|fallen|increases|increased|decreases|decreased|drops|dropped|changes|changed|grows|grew|"
                           r"reduces|reduced|climbs|climbed|declines|declined|goes\s+(?:up|down)|went\s+(?:up|down))\s*,?\s*(?:from\s+(?:X+x*|\d[\d.]*)\s+)?to"
                           r"|becomes|became|is\s+now|is\s+reduced\s+to|is\s+increased\s+to)\s*$", re.IGNORECASE)
#: a label in brackets right after a value: 'R = 2.4 Ω (the external resistance)'
_BRACKET_LABEL_RE = re.compile(r"^\s*\(\s*((?:the\s+|a\s+|an\s+)?[A-Za-z][A-Za-z \-]{2,60})\s*\)")
#: a part question of the request: '(b) Calculate the current in the battery. [2]'
_PART_QUESTION_RE = re.compile(r"\((?P<p>[a-h]|i{1,3}|iv|vi{0,3}|ix|x)\)\s*(?P<q>[^\[\n]{3,240}?)(?=\s*\[\d+\]|\s*\((?:[a-h]|i{1,3}|iv|vi{0,3})\)|\n|$)")
_COMMAND_WORDS = frozenset({"calculate", "determine", "find", "state", "deduce", "estimate", "predict", "work", "out", "write", "down", "give", "show",
                            "that", "explain", "describe", "evaluate", "outline", "suggest", "identify", "using", "use", "hence", "sketch", "draw"})
_LABEL_STOP = frozenset({"the", "and", "for", "with", "its", "this", "that", "from", "into", "including", "each", "which", "what", "your", "their", "there",
                         "then", "than", "also", "only", "both", "all", "any", "are", "was", "were", "has", "have", "had", "not", "but", "per", "via"})
_NAME_PREPOSITIONS = frozenset({"of", "from", "in", "across", "through", "at", "on", "for", "with", "between", "by", "into", "to", "over", "under", "within",
                                "after", "before", "along", "around"})
#: words before a quantity's name that are not part of it; STEM repair 4 adds the subordinating words ('…, because the current from
#: the cell falls, from 4.1 A to 2.7 A' names 'current', not 'because current')
_NAME_LEADS = frozenset({"the", "a", "an", "and", "so", "then", "therefore", "thus", "hence", "while", "but", "its", "their", "this", "that",
                         "because", "since", "as", "when", "whereas", "once", "now", "here", "if"})


def _label_words(text: str) -> list[str]:
    """The content words of a label (lower case, three letters or more, no command term or function word)."""
    return [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 3 and w not in _LABEL_STOP and w not in _COMMAND_WORDS]


#: rule part-value (STEM repair 5): words of a prose value's clause that name no quantity (a verb of stating, a preposition, a cue)
_PROSE_NAME_STOP = frozenset({"equals", "equal", "becomes", "become", "carries", "carry", "carried", "through", "across", "about", "approximately",
                              "roughly", "nearly", "around", "therefore", "thus", "hence", "here", "now", "value", "values", "given", "gives", "giving",
                              "taken", "found", "remains", "stays", "still", "just", "exactly", "say", "says"})


def _prose_value_name(before: str) -> str:
    """Rule ``part-value`` (STEM repair 5): the words that name the quantity a prose value is stated for, its clause right before it
    ('The current in the 6.0 Ω resistor is ' -> 'The current in the 6.0 Ω resistor is'); in an apposition, the clause before the comma
    ('…, so the terminal potential difference, ' -> ' so the terminal potential difference')."""
    seg = before.rstrip()
    if seg.endswith(","):
        seg = seg[:-1]
    for sep in (". ", ";", ":", "\n", ",", "(", ")", "—", "–"):
        k = seg.rfind(sep)
        if k >= 0:
            seg = seg[k + len(sep):]
    return seg[-120:]


def _changed_quantity(before_verb: str) -> list[str]:
    """The name of the quantity a change is stated for: the words of its clause right before the verb, from the last masked
    maths or clause boundary, up to the first preposition ('the current from the cell' names 'current'; 'the external
    resistance' names 'external resistance')."""
    seg = before_verb
    for sep in (",", ";", ":", "\n", ". "):
        k = seg.rfind(sep)
        if k >= 0:
            seg = seg[k + len(sep):]
    k = seg.rfind("X")
    if k >= 0:
        seg = seg[k + 1:].lstrip("x")
    words = re.findall(r"[a-z]+", seg.lower())
    while words and words[0] in _NAME_LEADS:
        words = words[1:]
    head: list[str] = []
    for w in words:
        if w in _NAME_PREPOSITIONS:
            break
        head.append(w)
    return [w for w in head if len(w) >= 3 and w not in _LABEL_STOP][:4]


#: rule part-answer (STEM repair 9): a line that says it checks a value ('As a check, …', 'Check: …', '…, which checks', 'To verify, …')
_CHECK_CUE_RE = re.compile(r"\b(?:check(?:s|ed|ing)?|cross[- ]?check(?:s|ed|ing)?|verif(?:y|ies|ied|ying|ication)|confirm(?:s|ed|ing|ation)?)\b",
                           re.IGNORECASE)


def _question_head(question: str) -> list[str]:
    """Rule part-answer (STEM repair 9): the name of the quantity a part's question asks for, up to its first preposition, its command
    words and leading words left out ('Calculate the terminal potential difference of the battery.' -> terminal, potential, difference;
    'Calculate the current in the battery.' -> current). At most six words of three letters or more."""
    words = re.findall(r"[a-z]+", question.lower()[:240])
    while words and (words[0] in _COMMAND_WORDS or words[0] in _NAME_LEADS):
        words = words[1:]
    head: list[str] = []
    for w in words:
        if w in _NAME_PREPOSITIONS:
            break
        if len(w) >= 3 and w not in _LABEL_STOP and w not in _COMMAND_WORDS:
            head.append(w)
    return head[:6]


def _label_head_words(text: str) -> list[str]:
    """Rule named-result (STEM repair 9): the words a label names its quantity by: its first clause, up to its first preposition
    ('Total resistance of the circuit, including the internal resistance' -> total, resistance; 'Internal resistance' -> internal,
    resistance), leading words left out, plurals folded."""
    first = re.split(r"[,;(]", text, maxsplit=1)[0]
    words = re.findall(r"[a-z]+", first.lower()[:120])
    while words and words[0] in _NAME_LEADS:
        words = words[1:]
    head: list[str] = []
    for w in words:
        if w in _NAME_PREPOSITIONS:
            break
        if len(w) >= 3 and w not in _LABEL_STOP and w not in _COMMAND_WORDS:
            head.append(_singular(w))
    return head[:6]


def _part_questions(request_text: str) -> dict[str, str]:
    """The question of each part of the request, by its label ('(b)': 'Calculate the current in the battery.')."""
    out: dict[str, str] = {}
    for m in _PART_QUESTION_RE.finditer(request_text[:8000]):
        out.setdefault(f"({m.group('p')})", m.group("q").strip())
    return out


def _part_question_spans(request_text: str) -> dict[str, tuple[int, int]]:
    """Rule part-given (STEM repair 6): the offsets of each part's question in the request text, by its label (as
    :func:`_part_questions` reads them)."""
    out: dict[str, tuple[int, int]] = {}
    for m in _PART_QUESTION_RE.finditer(request_text[:8000]):
        out.setdefault(f"({m.group('p')})", (m.start("q"), m.end("q")))
    return out


#: rule table-data (STEM repair 1): a change between two rows of a supplied table, and a value at a row
_KEY_PATTERN = r"(?:(?:site|sample|station|point|row|tube|group)\s+)?(?P<{k}>[-−]?\d+(?:\.\d+)?|[A-Z])(?P<{u}>\s*(?:°\s?C|°\s?F|[A-Za-zµμΩ%][A-Za-zµμΩ%³²⁻¹·/ ]{{0,10}}?))?"
_TABLE_CHANGE_BEFORE_RE = re.compile(
    r"between\s+" + _KEY_PATTERN.format(k="k1", u="u1") + r"\s+and\s+" + _KEY_PATTERN.format(k="k2", u="u2")
    + r"\s*,?\s*(?:there\s+is\s+|is\s+|with\s+|shows\s+)?(?:an?\s+|the\s+)?(?P<dir>increase|decrease|rise|fall|drop|change|difference|reduction|gain|decline)"
    r"\s+(?:is\s+)?of\s*$", re.IGNORECASE)
_FROM_END_RE = re.compile(r"\bfrom\s*$", re.IGNORECASE)
_TABLE_FROM_AT_RE = re.compile(
    r"^(?P<ua>[^,;.()\d]{0,40}?)\s+at\s+" + _KEY_PATTERN.format(k="k1", u="u1") + r"\s+to\s+(?P<b>[-−]?\d+(?:\.\d+)?)(?P<ub>[^,;.()\d]{0,40}?)\s+at\s+"
    + _KEY_PATTERN.format(k="k2", u="u2") + r"(?![\w.])", re.IGNORECASE)
_DECREASE_WORDS = frozenset({"decrease", "fall", "drop", "reduction", "decline"})
_NEUTRAL_CHANGE_WORDS = frozenset({"change", "difference"})


#: rule percentage-change (STEM repair 3): a percentage, and the words that say which way it changes
_PCT_WORD_RE = re.compile(r"\bpercentage\b|\bper\s?cent\b|\bpercent\b|%")
_PCT_DECREASE_RE = re.compile(r"\b(?:decrease[sd]?|fall(?:s|en)?|fell|drop(?:s|ped)?|reduction|reduced|decline[sd]?|loss)\b")
_PCT_INCREASE_RE = re.compile(r"\b(?:increase[sd]?|rise[sn]?|rose|gain(?:s|ed)?|growth|grew)\b")
#: rule half-lives (STEM repair 3): a number of half-lives the prose states, and the copula joining a time to it
_HALF_LIVES_RE = re.compile(r"(?<![\w.])(?P<n>\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s+half[\s-]?li(?:fe|ves)\b", re.IGNORECASE)
_TIME_IS_RE = re.compile(r"^\s*,?\s*(?:is|are|=|equals|makes|is\s+equal\s+to|corresponds\s+to|is\s+exactly|is\s+about)\s*$", re.IGNORECASE)
#: the names the reader gives a half-life symbol (T½, t½, T_{1/2}, t_{1/2})
_HALF_LIFE_NAMES = frozenset({"t_half", "t½", "t_{1/2}", "t1/2", "t_1/2"})
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _small_number(text: str) -> Optional[int]:
    t = text.lower()
    return int(t) if t.isdigit() else _NUMBER_WORDS.get(t)


def _is_half(node: Node) -> bool:
    """½, 1/2, (1/2) or 0.5 as written."""
    if isinstance(node, Num):
        return node.number.value == Fraction(1, 2)
    return isinstance(node, BinOp) and node.op == "/" and isinstance(node.left, Num) and isinstance(node.right, Num) \
        and node.left.number.value == 1 and node.right.number.value == 2


def _percentage_shape(node: Node) -> Optional[tuple[Node, Num, Num, Num]]:
    """``(the difference, its first value, its second value, the divisor)`` when ``node`` is a difference of two written values over
    one of them, times 100, in any order of the product (``(a − b) ÷ c × 100``, ``100 × (a − b)/c``), else None (rule
    percentage-change)."""
    num: list[Node] = []
    den: list[Node] = []

    def flat(n: Node, inverted: bool, depth: int = 0) -> bool:
        if depth > 8:
            return False
        if isinstance(n, BinOp) and n.op in "*/":
            return flat(n.left, inverted, depth + 1) and flat(n.right, inverted != (n.op == "/"), depth + 1)
        (den if inverted else num).append(n)
        return True

    if not flat(node, False) or len(den) != 1 or len(num) != 2:
        return None
    hundred = [x for x in num if isinstance(x, Num) and x.number.value == 100]
    diffs = [x for x in num if isinstance(x, BinOp) and x.op == "-" and isinstance(x.left, (Num, Quantity)) and isinstance(x.right, (Num, Quantity))]
    divisor = den[0]
    if len(hundred) != 1 or len(diffs) != 1 or not isinstance(divisor, (Num, Quantity)):
        return None
    diff = diffs[0]
    a, b = diff.left, diff.right
    if divisor.number.value not in (a.number.value, b.number.value):
        return None
    return diff, a, b, divisor  # type: ignore[return-value]


def _replace_node(node: Node, old: Node, new: Node, depth: int = 0) -> Optional[Node]:
    """``node`` with the subtree ``old`` (the very node) replaced by ``new``; None past the depth bound."""
    if depth > 64:
        return None
    if node is old:
        return new
    if isinstance(node, BinOp):
        left, right = _replace_node(node.left, old, new, depth + 1), _replace_node(node.right, old, new, depth + 1)
        return None if left is None or right is None else replace(node, left=left, right=right)
    return node


#: rule processed-data (STEM repair 3): words of a part's question that never set a processed quantity apart from its column
_PROCESSED_STOP = frozenset({"table", "data", "value", "values", "row", "rows", "column", "graph", "results", "result", "each", "every", "time", "times",
                             "answer", "working", "units", "unit", "clearly", "give", "given", "using", "student", "mathematics", "model"})
#: rule table-operands (STEM repair 2): a row of a supplied table named by its letter key after a cue ('between site A and site C',
#: 'from A to C', 'at C'), or by its numeric key with the key column's unit ('t = 8 h', 'at 30 °C')
_LETTER_ROW_RE = re.compile(r"\b(?i:sites?|samples?|stations?|points?|rows?|from|to|at|between|and|of|than|by)\s+(?:(?i:sites?)\s+)?([A-Z])(?![A-Za-z0-9])")
_NUMBER_UNIT_RE = re.compile(r"(?<![\w.])([-−]?\d+(?:\.\d+)?)\s*(°\s?C|°\s?F|[A-Za-zµμΩ][A-Za-zµμΩ⁻¹²³]{0,6})?")


def _unit_written_after(text: str, end: int) -> Optional[UnitExpr]:
    """The unit written right after a bare number at ``end`` ('2.0 km)', '2.3 mg dm⁻³)'), read by the table of units (two words before
    one), with a known dimension; None when none follows (STEM repair 4, rule row-value)."""
    m = re.match(r"[ \t]*([A-Za-zµμΩ°][A-Za-zµμΩ°⁻¹²³⁴·/]{0,10})(?:[ \t]+([A-Za-zµμΩ][A-Za-zµμΩ⁻¹²³⁴·/]{0,10}))?", text[end:end + 40])
    if m is None:
        return None
    for cand in ((m.group(1) + " " + m.group(2)) if m.group(2) else None, m.group(1)):
        if not cand:
            continue
        u = parse_unit(cand)
        if u is not None and not u.unknown and u.dim is not None:
            return u
    return None


def _count_head_words(name: str) -> frozenset[str]:
    """The content words of a column name before ' per ' (the quantity it counts: 'Mayfly nymphs per kick sample' gives mayfly and
    nymphs); empty when the name has no ' per ' (STEM repair 4, rule row-value)."""
    k = name.lower().find(" per ")
    if k <= 0:
        return frozenset()
    return frozenset(w for w in re.findall(r"[a-z]+", name[:k].lower()) if len(w) >= 3 and w not in _LABEL_STOP)


#: rule row-value (STEM repair 10): words that measure a quantity rather than name it ('Number of seeds', 'Mass of the precipitate')
_MEASURE_WORDS = frozenset({"number", "mass", "volume", "amount", "count", "concentration", "percentage", "proportion", "length", "height", "width",
                            "area", "rate", "level", "value", "total"})


def _column_head_word(name: str) -> str:
    """Rule row-value (STEM repair 10): the last content word of the quantity a column names: its counted quantity before ' per ' or
    the name before its first preposition ('Mayfly nymphs per kick sample' gives nymphs, 'Distance from the outlet' distance, 'Dissolved
    oxygen' oxygen), the word after 'of' when the name opens with a word that measures ('Number of seeds' gives seeds); empty when
    none."""
    low = " ".join(name.lower().split())
    k = low.find(" per ")
    head = low[:k] if k > 0 else low
    words = re.findall(r"[a-z]+", head)
    for i, w in enumerate(words):
        if w in ("from", "of", "in", "at", "by", "with", "for", "to", "on") and i > 0:
            if w == "of" and all(x in _MEASURE_WORDS or x in _LABEL_STOP for x in words[:i]):
                rest = [x for x in words[i + 1:] if len(x) >= 3 and x not in _LABEL_STOP]
                return rest[-1] if rest else ""
            words = words[:i]
            break
    content = [w for w in words if len(w) >= 3 and w not in _LABEL_STOP]
    return content[-1] if content else ""


def _lettered(table) -> bool:
    """A supplied table whose rows are named by letters (sites 'A' to 'E'; STEM repair 4, rule row-value)."""
    return bool(table.rows) and all(re.fullmatch(r"[A-Z]", (row[0][0].strip().split(" ") or [""])[0]) for row in table.rows)


def _clause_tail(text: str) -> str:
    """The words of ``text`` after its last clause boundary (rule row-value: the phrase that names a column)."""
    cut = max(text.rfind(","), text.rfind(";"), text.rfind(":"), text.rfind(". "), text.rfind("\n"))
    return text[cut + 1:] if cut >= 0 else text


#: rule row-value (STEM repair 4): a run that states a site's value: '… at site C = …', '… at C = …', 'site C = …'
_ROW_RUN_BEFORE_RE = re.compile(r"(?:\b(?:at|for|in|by)\s+(?:(?:site|sample|station|point)\s+)?|\b(?:site|sample|station|point)\s+)$", re.IGNORECASE)
#: a numbered row's key: a number with the key column's unit, written alone or after the key's symbol and '=' ('12 h', 't = 12 h',
#: '30.0 °C'; the symbol form is STEM repair 10's)
_ROW_NUM_KEY = r"(?:[A-Za-zθ]\s*=\s*)?(?P<kn>[-−]?\d+(?:\.\d+)?)\s*(?P<u>°\s?C|°\s?F|[A-Za-zµμΩ][A-Za-zµμΩ⁻¹²³]{0,5})"
_ROW_KEY = (r"(?:(?i:site|sample|station|point|tube|trial)\s+)?(?:(?P<k>[A-Z])(?![A-Za-z0-9])|" + _ROW_NUM_KEY + r")")
_ROW_COPULA = r"(?:is|was|=|of|equals|reaches|reached|falls\s+to|fell\s+to|rises\s+to|rose\s+to|drops\s+to|dropped\s+to|stands\s+at|stood\s+at" \
              r"|numbers?|numbered|totals?|totall?ed|amounts?\s+to|amounted\s+to|comes?\s+to|came\s+to)"
_ROW_COL = r"(?P<col>[A-Za-z][A-Za-z’' \-]{2,60}?)"
_ROW_PROSE_RES = tuple(re.compile(p) for p in (
    # 'The nitrate at E is …', 'the uptake at 30 °C is …'
    _ROW_COL + r"\s+(?i:at|for|in)\s+" + _ROW_KEY + r"\s+(?i:" + _ROW_COPULA + r")\s*$",
    # 'nitrate at E (…', 'dissolved oxygen recovers by D (…'
    _ROW_COL + r"\s+(?i:at|for|in|by)\s+" + _ROW_KEY + r"\s*\(\s*$",
    # 'At site C, dissolved oxygen is …', 'At 30 °C, the uptake is …'
    r"(?:^|(?<=[\s(]))(?i:at|for|in)\s+" + _ROW_KEY + r"\s*,\s*(?i:the\s+)?" + _ROW_COL + r"\s+(?i:" + _ROW_COPULA + r")\s*$",
    # '… greatest at C (2.0 km), where it reaches …' (the quantity named before the row)
    r"\b(?i:at|by)\s+" + _ROW_KEY + r"\s*(?:\([^()]{0,40}\))?\s*,\s*(?i:where)\s+(?i:it)\s+(?i:" + _ROW_COPULA + r")\s*$",
    # 'site A has the least nitrate (…'
    r"\b(?i:site|sample|station|point)\s+(?P<k>[A-Z])\s+(?i:has|had)\s+(?i:the\s+)?(?:(?i:least|most|highest|lowest|greatest|smallest|largest|fewest"
    r"|maximum|minimum)\s+)?" + _ROW_COL + r"\s*\(\s*$",
))


#: rule row-value (STEM repair 10): the shapes that name the row before the value and the column elsewhere. The subject of the clause:
#: 'site A has …' (a site of a lettered table), with no other site named between it and the value
_ROW_SUBJECT = r"\b(?i:site|sample|station|point)\s+(?P<k>[A-Z])\s+(?i:has|had)\s+"
_ROW_NO_SITE = r"(?:(?!\b(?i:sites?|samples?|stations?|points?)\s+[A-Z](?![A-Za-z0-9]))[^;!?\n])"
_ROW_SUPERLATIVE = r"(?:(?i:least|most|highest|lowest|greatest|smallest|largest|fewest|maximum|minimum)\s+)"
#: 'Site A has 43 …': the value right after the clause's subject (the column the words after it name)
_ROW_HAS_VALUE_RE = re.compile(_ROW_SUBJECT + r"(?:(?i:only|just|about|approximately|nearly|roughly|around|exactly)\s+)?$")
#: 'site A has the least nitrate (1.2 mg dm⁻³) and the most nymphs (': a column joined to the clause's first
_ROW_HAS_AND_RE = re.compile(_ROW_SUBJECT + _ROW_NO_SITE + r"{0,160}?\b(?i:and|but|with|plus)\s+(?i:the\s+)?" + _ROW_SUPERLATIVE + r"?" + _ROW_COL + r"\s*\(\s*$")
#: 'site B has the most nitrate (8.4 mg dm⁻³) and only ': a count whose column the clause leaves out
_ROW_HAS_ELLIPSIS_RE = re.compile(_ROW_SUBJECT + _ROW_NO_SITE + r"{0,160}?\)\s*,?\s*(?i:and|but)\s+(?:(?i:only|just|about|nearly|the)\s+){0,2}"
                                  + _ROW_SUPERLATIVE + r"?$")
#: '… nitrate concentration of ' before a value whose row the words after it name ('… of 6.9 mg dm⁻³ at site C')
_ROW_COL_OF_RE = re.compile(_ROW_COL + r"\s+(?i:of)\s+$")
#: a row named after 'at', 'for' or 'in': a numbered row's key ('12 h', 't = 12 h') or a site's letter ('site C', 'C')
_ROW_AT_KEY = r"(?:" + _ROW_NUM_KEY + r"(?![A-Za-z0-9])|(?:(?i:site|sample|station|point)\s+)?(?P<k>[A-Z])(?![A-Za-z0-9]))"
#: ' at site C' (or 'for', 'in'; ' at 12 h') right after a value
_ROW_AT_AFTER_RE = re.compile(r"^\s*(?i:at|for|in)\s+" + _ROW_AT_KEY)
#: ' mayfly nymphs at site B' (or ' of dissolved oxygen at B') right after a value: its column, then its row
_ROW_VALUE_COL_AT_RE = re.compile(r"^\s*(?i:of\s+)?" + _ROW_COL + r"\s+(?i:at|for|in)\s+" + _ROW_AT_KEY)
#: 'At site A, ' (or 'At 12 h, ') right before a run whose label names the column ('At site A, mayfly nymphs = 43.')
_ROW_AT_LABEL_RE = re.compile(r"(?:^|[\s(])(?i:at|for|in)\s+" + _ROW_AT_KEY + r"\s*,\s*(?:(?i:the)\s+)?$")


def _row_key_of(m: "re.Match[str]") -> tuple[str, Optional[str]]:
    """Rule row-value (STEM repair 10): the row key a match names and the unit written with a numbered key (None for a site's letter)."""
    kn = m.groupdict().get("kn")
    return (kn, (m.group("u") or "").strip() or None) if kn else (m.group("k"), None)


#: rule row-value and rule table-data (STEM repair 10): words that make the quantity a clause names a processed one, not the supplied
#: table's column ('the corrected count rate', 'the mean', 'the uncertainty in', 'after correction'), unless the column's own name holds them
_PROCESSED_QUALIFIERS = frozenset({"corrected", "correction", "correcting", "adjusted", "adjustment", "net", "mean", "average", "averaged", "median",
                                   "total", "sum", "expected", "predicted", "prediction", "theoretical", "calculated", "estimated", "estimate",
                                   "relative", "normalised", "normalized", "fitted", "extrapolated", "interpolated", "processed", "background",
                                   "uncertainty", "uncertainties", "error", "errors", "residual", "percentage", "change", "difference", "ratio",
                                   "gradient"})


def _names_processed(text: str, column, *, allow: Iterable[str] = ()) -> bool:
    """Rule row-value and rule table-data (STEM repair 10): ``text`` (the value's clause) names a processed quantity the supplied table's
    ``column`` does not: a word of :data:`_PROCESSED_QUALIFIERS` its name lacks ('The corrected count rate at 12 h is 566 counts min⁻¹.'
    for the column 'Measured count rate'). Such a value is not the column's cell, and was set against it (a false failure)."""
    words = set(re.findall(r"[a-z]+", text.lower()))
    return bool((words & _PROCESSED_QUALIFIERS) - set(re.findall(r"[a-z]+", column.name.lower())) - set(allow))


#: rule row-value (STEM repair 10): the words that may stand before the word of a column's name a phrase names it by (determiners and
#: superlatives), and the words that end that noun phrase going back (prepositions, verbs, conjunctions)
_NAME_MODIFIERS_FREE = frozenset({"the", "a", "an", "its", "their", "this", "that", "these", "those", "his", "her", "our", "your", "my", "same",
                                  "most", "least", "highest", "lowest", "greatest", "smallest", "largest", "fewest", "maximum", "minimum", "peak"})
_NAME_BOUNDARY = frozenset({"at", "in", "of", "on", "for", "from", "to", "by", "with", "into", "is", "was", "are", "were", "be", "has", "had", "have",
                            "and", "or", "but", "so", "while", "where", "which", "when", "as", "than", "reaches", "reached", "falls", "fell",
                            "rises", "rose", "drops", "dropped", "shows", "showed", "gives", "gave", "records", "recorded", "there", "then"})


def _modifiers_fit(phrase: str, column) -> bool:
    """Rule row-value (STEM repair 10): a phrase that names a supplied table's column by a part of its name only (its last word, or a word
    it shares with the table's only column of numbers) names that column only when the words right before that word, back to the noun
    phrase's start, are words of the column's name, determiners or superlatives: 'the count rate' and 'the most nymphs' do, 'the decay
    rate' and 'the water uptake' name other quantities (set against the column they were failed)."""
    name = set(re.findall(r"[a-z]+", column.name.lower()))
    words = re.findall(r"[a-z]+", phrase.lower())

    def named(w: str) -> bool:
        return w in name or (w.endswith("s") and w[:-1] in name) or w + "s" in name
    anchors = [i for i, w in enumerate(words) if named(w)]
    if not anchors:
        return True
    j = anchors[-1] - 1
    while j >= 0:
        w = words[j]
        if named(w) or w in _NAME_MODIFIERS_FREE:
            j -= 1
            continue
        return w in _NAME_BOUNDARY or len(w) <= 2
    return True


#: rule row-value, the clause reading (STEM repair 10): where a value's clause begins (after the last of these before it) and ends (at the
#: first after it): a sentence's or a clause's end, a comma before a word that opens a clause, or such a word
_CLAUSE_OPENERS = r"(?:while|whilst|whereas|but|although|though|because|since|yet|which|where|when|unlike)"
_VALUE_CLAUSE_START_RE = re.compile(r"[;:!?\n]|\.(?=\s)|,(?=\s*(?i:" + _CLAUSE_OPENERS + r"|and|so|as|then)\b)|\b(?i:" + _CLAUSE_OPENERS + r")\b")
_VALUE_CLAUSE_END_RE = re.compile(r"[;:!?\n]|\.(?=\s|$)|,(?=\s*(?i:" + _CLAUSE_OPENERS + r"|and|so|as|then)\b)|\b(?i:" + _CLAUSE_OPENERS
                                  + r"|and|so|then)\b")
#: the words that state the value right before it (after any of the adverbs below): a verb of being or reaching, 'has', 'of', '=', an
#: opening bracket, or the comma of an apposition
_ROW_STATES_RE = re.compile(
    r"(?:\b(?i:is|are|was|were|be|been|becomes?|became|equals?|equalled|equaled|reaches|reached|reaching|stands?\s+at|stood\s+at|standing\s+at"
    r"|(?:falls?|fell|falling|rises?|rose|rising|drops?|dropped|dropping|climbs?|climbed|sinks?|sank)\s+to|numbers?|numbered|totals?|totall?ed"
    r"|amounts?\s+to|amounted\s+to|comes?\s+to|came\s+to|has|had|have|having|with|of|records?|recorded|recording|shows?|showed|showing"
    r"|gives?|gave|giving|measures?|measured|measuring|contains?|contained|holds?|held|sees|saw|took|takes|taking|lasted|lasts)|=|≈|\(|,)\s*$")
_ROW_LEAD_ADVERBS_RE = re.compile(r"(?:\s+(?i:only|just|about|approximately|around|roughly|nearly|almost|exactly|still|now|then|also|precisely"
                                  r"|merely|barely|some))+\s*$")
#: a clause that compares, states a change, a range, a ratio or a share: its value is no cell of one row
_ROW_CLAUSE_SKIP_RE = re.compile(
    r"\b(?i:than|against|compared|comparison|versus|vs|between|from|increase[sd]?|increasing|decrease[sd]?|decreasing|rises?|rising|risen|rose"
    r"|falls?|falling|fallen|fell|drops?|dropped|dropping|changes?|changed|changing|differences?|differs?|reduction|reduced|reduces|gains?"
    r"|loss|losses|declines?|declined|declining|grows?|growth|grew|lower|higher|more|less|fewer|greater|smaller|larger|bigger|times|twice"
    r"|double|doubled|halves|halved|ratio|factor|per\s*cent|percent|percentage|average|mean|total|sum|each|every|all|both|range|ranges|ranged"
    r"|ranging)\b|[%×÷]")
#: rule row-value (STEM repair 10): a value its clause states under a condition, a hypothesis, a target or a modal verb is no value the
#: supplied row has ('If nitrate at site B fell to 4.0 mg dm⁻³, …', 'A target of 9.0 mg dm⁻³ of dissolved oxygen at site C would need …',
#: 'Dissolved oxygen at site C would have to rise to 6.0 mg dm⁻³ …', 'Had trial 2 at 30.0 °C taken 36.0 s, …'), nor is a bound written right
#: before it ('is below 4.0 mg dm⁻³', 'exceeds 8.0 mg dm⁻³')
_UNSTATED_RE = re.compile(
    r"^\s*(?i:had|were|should)\b"
    r"|\b(?i:if|unless|suppose|supposing|assuming|assume|imagine|would|could|might|must|should|shall|will|ought|needs?\s+to|has\s+to|have\s+to"
    r"|had\s+to|target|targets|goal|aim|aims|threshold|limit|limits|guideline|required|requirement|recommended|hoped?|hopes|wants?|wanted)\b")
_UNSTATED_AFTER_RE = re.compile(r"\b(?i:if|unless|would|could|might|must|should|shall|will|ought|needs?\s+to|has\s+to|have\s+to|had\s+to)\b")
_BOUND_BEFORE_RE = re.compile(r"\b(?i:above|below|under|over|beyond|within|up\s+to|at\s+least|at\s+most|no\s+more\s+than|no\s+less\s+than"
                              r"|exceeds?|exceeded|exceeding)\s*$")


def _unstated(head: str, tail: str) -> bool:
    """Rule row-value (STEM repair 10): the value's clause states it under a condition, a hypothesis, a target or a modal verb (``head``,
    the clause before the value; a condition or a modal verb in ``tail`` after it, read to its first comma), or a bound stands right
    before it: no value the supplied row has. Each such value had been set against the cell and failed (a false INT-SUBJ-004)."""
    return bool(_UNSTATED_RE.search(head) or _BOUND_BEFORE_RE.search(_ROW_LEAD_ADVERBS_RE.sub("", head))
                or _UNSTATED_AFTER_RE.search(tail.split(",", 1)[0]))


#: a value followed by a comparison or an operation: no cell
_ROW_COMPARE_AFTER_RE = re.compile(r"^\s*\)?\s*(?:(?i:more|less|fewer|lower|higher|greater|smaller|larger|above|below|over|under|than|times|fold"
                                   r"|up|down|out\s+of|of\s+the|per\s*cent|percent)\b|[%×/÷+−-]|x\b)")
#: the rows a clause names: a site's letter after 'site' (a list of them), after a preposition, as a possessive or as the clause's subject
_ROW_LETTER_MENTION_RE = re.compile(
    r"\b(?i:sites?|samples?|stations?|points?)\s+(?P<a>[A-Z](?:\s*(?:,|and|or|to|–|-)\s*[A-Z])*)(?![A-Za-z0-9])"
    r"|\b(?i:at|for|in|by|of|from|to|between|than|and|or|with|beyond|past|near|towards?|until|after|before)\s+(?P<b>[A-Z])(?![A-Za-z0-9'’])"
    r"|\b(?P<c>[A-Z])['’]s\b"
    r"|(?:^|[\s(])(?P<d>[A-Z])\s+(?i:has|had|is|was|shows?|showed|records?|recorded|contains?|reaches|reached|gives?|gave|holds?|held)\b")
#: a number with a unit (a numbered row's key when the unit has the key column's dimension), and a bare number listed before another
_ROW_NUMBER_MENTION_RE = re.compile(r"(?<![\w.])" + _ROW_NUM_KEY + r"(?![A-Za-z0-9])")
_ROW_NUMBER_LIST_RE = re.compile(r"(?<![\w.])[-−]?\d+(?:\.\d+)?\s*(?:,|and|or|to|–|-)\s*(?=[-−]?\d)")


#: rule named-component (STEM repair 10): a component the prose names by its value ('the power dissipated in the 4.0 Ω resistor'): the
#: preposition and article before the value, and the component's noun right after it
_COMPONENT_NOUNS = frozenset({"resistor", "capacitor", "inductor", "lamp", "bulb", "heater", "wire", "cable", "coil", "spring", "block", "mass", "load",
                              "cell", "motor", "ball", "trolley", "car", "conductor", "filament", "thermistor", "component", "weight", "sphere",
                              "cylinder", "plate", "pendulum", "bob", "ring", "disc", "puck", "cart", "sled", "box", "crate", "stone", "body"})
_COMPONENT_BEFORE_RE = re.compile(r"\b(?:in|through|across|of|by|on|for|into|onto)[ \t]+(?:the|this|that|each)[ \t]+$", re.IGNORECASE)
_COMPONENT_AFTER_RE = re.compile(r"^[ \t]+(?P<noun>[A-Za-z]{3,12})(?![A-Za-z])")


#: rule condition-result (STEM repair 10): the condition a statement states right after the value it computes ('… = 1597 counts min⁻¹ at
#: 32 h', '… at t = 32 h'), and the one condition a part's question states ('(d) Predict the corrected count rate at t = 32 h.')
_TRAILING_CONDITION_RE = re.compile(r"^[ \t]*,?[ \t]*(?:at|when|after)[ \t]+(?:[A-Za-z][A-Za-z0-9₀-₉]{0,3}[ \t]*=[ \t]*)?(?P<num>[−-]?\d+(?:\.\d+)?)[ \t]*"
                                    r"(?P<unit>°[ \t]?C|°[ \t]?F|[A-Za-zµμΩ][A-Za-zµμΩ⁻¹²³]{0,7})(?![A-Za-z0-9])", re.IGNORECASE)
_QUESTION_CONDITION_RE = re.compile(r"\b(?:at|when|after)[ \t]+(?:[A-Za-z][A-Za-z0-9₀-₉]{0,3}[ \t]*=[ \t]*)?(?P<num>[−-]?\d+(?:\.\d+)?)[ \t]*"
                                    r"(?P<unit>°[ \t]?C|°[ \t]?F|[A-Za-zµμΩ][A-Za-zµμΩ⁻¹²³]{0,7})(?![A-Za-z0-9])", re.IGNORECASE)


def _condition_si(num: str, unit: str) -> Optional[tuple[Fraction, Dimension, str]]:
    """Rule condition-result (STEM repair 10): a condition written as a number and a unit, in SI, with its dimension and as written; None
    when the unit is not read or is dimensionless."""
    value = _key_number(num)
    u = parse_unit(" ".join(unit.split()))
    if value is None or u is None or u.unknown or u.dim is None or u.dim == DIMENSIONLESS or not u.readings:
        return None
    si = si_value(value, u, "")
    return None if si is None else (si, u.dim, f"{num} {' '.join(unit.split())}")


#: rule statistics (STEM repair 9): the statistics the STEM pack forms from listed values, and the others (named ST-UNDEC-001)
_STAT_COMPUTED = {"median": "median", "mode": "mode", "modal value": "mode", "range": "range", "mean": "mean", "average": "mean",
                  "arithmetic mean": "mean"}
_STAT_WORDS = (r"arithmetic\s+mean|modal\s+value|interquartile\s+range|standard\s+deviation|lower\s+quartile|upper\s+quartile|mean\s+deviation|"
               r"median|mode|range|mean|average|variance|quartile|percentile|IQR|s\.\s?d\.")
_STAT_RE = re.compile(r"(?<![A-Za-z])(?P<stat>" + _STAT_WORDS + r")(?![A-Za-z])", re.IGNORECASE)
_STAT_FILLER = frozenset({"value", "values", "data"})
#: the listed values of a statistic: numbers (each with up to two words of its unit) joined by commas and 'and'
_STAT_LIST = r"[−-]?\d+(?:\.\d+)?(?:[ \t]+[A-Za-zµμΩ°%][^\s\d,;:=()\[\]]{0,10}){0,2}"
#: 'Median of 18, 27, 40, 58, 80, 92 and ' before a maths run that starts at the list's last value
_STAT_LIST_RUN_RE = re.compile(r"(?<![A-Za-z])(?P<stat>" + _STAT_WORDS + r")[ \t]+of[ \t]+(?:the[ \t]+(?:values|numbers|data|readings|results)[ \t]+)?"
                               r"(?P<list>(?:" + _STAT_LIST + r"[ \t]*(?:,[ \t]*(?:and[ \t]+)?|[ \t]+and[ \t]+))+)$", re.IGNORECASE)
#: 'The median of 18, 27, 40, 58, 80, 92 and 61 is ' before a value the prose states
_STAT_LIST_PROSE_RE = re.compile(r"(?<![A-Za-z])(?P<stat>" + _STAT_WORDS + r")[ \t]+of[ \t]+(?:the[ \t]+(?:values|numbers|data|readings|results)[ \t]+)?"
                                 r"(?P<list>" + _STAT_LIST + r"(?:[ \t]*(?:,[ \t]*(?:and[ \t]+)?|[ \t]+and[ \t]+)" + _STAT_LIST + r")+)[ \t]*,?[ \t]*"
                                 r"(?:is|was|=|equals|:)[ \t]*$", re.IGNORECASE)
#: 'The median uptake is ' / 'The range of the uptake is ' before a value the prose states: a supplied table's column named, no row
_STAT_COLUMN_PROSE_RE = re.compile(r"(?<![A-Za-z])(?P<stat>" + _STAT_WORDS + r")[ \t]+(?:of[ \t]+)?(?:the[ \t]+)?(?P<words>[A-Za-z][A-Za-z \t-]{1,40}?)[ \t]+"
                                   r"(?:is|was|=|equals)[ \t]*$", re.IGNORECASE)


def _exact_place(place: Fraction, at: int) -> Num:
    """Rule rounded-digits (STEM repair 9): a place (a power of ten, or a part of a unit) as an exact number the STEM pack writes."""
    text = _show_place(place)
    return Num(ExactNumber(text=text, value=place, sig_figs=1, last_place=0, exact=True, digit_count=1), at, at)


def _show_place(place: Fraction) -> str:
    """A place as a decimal ('0.01', '1', '100'), or a/b when it is none."""
    if place.denominator == 1:
        return str(place.numerator)
    d = place.denominator
    k = 0
    while d % 10 == 0:
        d //= 10
        k += 1
    if d == 1 and place.numerator == 1:
        return "0." + "0" * (k - 1) + "1"
    return f"{place.numerator}/{place.denominator}"


def _exact_num(n: int, at: int) -> Num:
    """An exact whole number the STEM pack writes into a formed expression (a count, the 2 of a mean of two)."""
    return Num(ExactNumber(text=str(n), value=Fraction(n), sig_figs=len(str(n)), last_place=0, exact=True, digit_count=len(str(n))), at, at)


def _repeat_columns(table) -> list[list[int]]:
    """Rule row-terms (STEM repair 9): the groups of a supplied table's value columns that write one quantity, repeated: names that differ
    only by a trial's (a repeat's, a run's) number, and one unit ('Time, trial 1 / s', 'Time, trial 2 / s', 'Time, trial 3 / s'); two
    columns at least. Columns of different quantities in one unit (nitrate and dissolved oxygen, both mg dm-3) are no such group."""
    by_key: dict[tuple[str, str], list[int]] = {}
    for j in table.value_columns():
        col = table.columns[j]
        m = _REPEAT_NAME_RE.search(col.name)
        if m is None:
            continue
        stem = " ".join(_REPEAT_NAME_RE.sub(" ", col.name).lower().replace(",", " ").split())
        by_key.setdefault((stem, " ".join(col.unit_text.split())), []).append(j)
    return [g for g in by_key.values() if len(g) >= 2]


#: rule row-terms (STEM repair 9): a repeat's number in a column's name ('Time, trial 2', 'Reading 3', 'Run 1')
_REPEAT_NAME_RE = re.compile(r"\b(?:trial|repeat|run|replicate|reading|measurement|test|attempt)\s*\d+\b", re.IGNORECASE)


def _named_rows(text: str, table) -> list[int]:
    """The rows of ``table`` that ``text`` names (rule table-operands), in table order."""
    if not text:
        return []
    hits: set[int] = set()
    key_col = table.columns[0]
    for m in _LETTER_ROW_RE.finditer(text[:4000]):
        r = table.row_for(m.group(1), None)
        if r is not None:
            hits.add(r)
    if key_col.unit is not None and key_col.unit.dim is not None:
        for m in _NUMBER_UNIT_RE.finditer(text[:4000]):
            unit = (m.group(2) or "").strip()
            if not unit:
                continue
            u = parse_unit(unit.replace(" ", ""))
            if u is None or u.dim is None or not u.dim.same_physical(key_col.unit.dim):
                continue
            num = _key_number(m.group(1))
            r = table.row_for(m.group(1), num) if num is not None else None
            if r is not None:
                hits.add(r)
    return sorted(hits)


def _key_number(key: str) -> Optional[Fraction]:
    """The value of a numeric row key as written (``25``, ``−0.5``), None for a letter."""
    t = key.replace("−", "-")
    try:
        return Fraction(t) if any(ch.isdigit() for ch in t) else None
    except (ValueError, ZeroDivisionError):
        return None


def _show_fraction(v: Fraction) -> str:
    """A display of an exact difference of two cells (a decimal when it is one, else a/b)."""
    if v.denominator == 1:
        return str(v.numerator)
    d = v.denominator
    k = 0
    while d % 10 == 0 or d % 2 == 0 or d % 5 == 0:
        if d % 10 == 0:
            d //= 10
        elif d % 2 == 0:
            d //= 2
        else:
            d //= 5
        k += 1
        if k > 30:
            break
    if d == 1:
        q = v * Fraction(10) ** k
        if q.denominator == 1:
            sign = "-" if q < 0 else ""
            digits = str(abs(q.numerator)).rjust(k + 1, "0")
            return f"{sign}{digits[:-k]}.{digits[-k:]}".rstrip("0").rstrip(".") if k else f"{sign}{digits}"
    return f"{v.numerator}/{v.denominator}"


#: the most statements a substitution names as stating the values it is checked against (rule related-statements)
_MAX_RELATED = 4
#: binding sources that are statements of the answer (a request value is no claim of the report)
_ANSWER_SOURCES = frozenset({"given", "let", "statement", "result", "root", "substitution"})


def _related_statements(rel: Relation, scope: Scope) -> tuple[str, ...]:
    """Rule ``related-statements`` (STEM repair 1): for each symbol the substitution substitutes (the paired symbols, or every
    symbol of the symbolic side it evaluates), the one statement of the answer that states a value of it before the
    substitution, latest first: the substitution is checked against that value, so when it fails the statement whose value
    it contradicts is named too ('V = … = 14.1 V' in part (c) when part (d) substitutes 9.93 V for V). A symbol is passed
    over when the relation's own statements state a value of it (the step's own clause gives it), or when several
    statements do (which one the substitution contradicts is then not read): no statement is named on a guess. STEM repair 8:
    the statement of the formula the substitution evaluates comes first, when another statement states it (the law the line
    does not follow is named where it is stated)."""
    names: list[str] = [name for name, _n in rel.pairs]
    if rel.evaluate or not names:
        side = rel.formula.expr if rel.formula is not None else _first(rel.left)
        if side is not None:
            names += [n for n in symbols(side) if n not in names]
    own = set(rel.statement_ids)
    found: list[tuple[int, str]] = []
    for name in dict.fromkeys(names):
        stated = [b for b in scope.bindings.get(name, ()) if b.source in _ANSWER_SOURCES]
        if any(b.statement_id in own for b in stated):
            continue
        before = [b for b in stated if b.end <= rel.start]
        if len({b.statement_id for b in before}) != 1:
            continue
        found.append((before[-1].start, before[-1].statement_id))
    found.sort(reverse=True)
    out = tuple(dict.fromkeys(sid for _start, sid in found))
    # STEM repair 8: the statement of the formula the substitution evaluates, when another statement states it ('P = V/R' then 'P = (9.93
    # V)² / 6.0 Ω'): a failure contradicts that law as much as the values, so the law is named first ('V = ε + Ir' had been named by nothing)
    fsid = rel.formula.statement_id if rel.formula is not None and rel.formula.source != "request" else ""
    if fsid and fsid not in own:
        out = (fsid,) + tuple(s for s in out if s != fsid)
    return out[:_MAX_RELATED]


#: rule rounding-cue (STEM repair 1): a rounding the prose states for a value it restates
_ROUND_WORDS = {"whole number": 0, "integer": 0, "unit": 0, "one": 0, "ten": -1, "hundred": -2, "thousand": -3, "tenth": 1, "hundredth": 2, "thousandth": 3}
_ROUND_PHRASE = (r"(?:(?:correct|accurate|rounded|rounding|rounds|round|given|written)\s+)?(?:to|at)\s+(?:"
                 # STEM repair 4: a word naming the value's unit may follow the place ('to the nearest ten euros'; validated by the caller)
                 r"the\s+nearest\s+(?P<word>whole\s+number|integer|unit|one|ten|hundred|thousand|tenth|hundredth|thousandth)\b(?:\s+(?P<placeunit>[A-Za-z]{2,20})\b)?"
                 r"|(?P<n>\d{1,2}|one|two|three|four|five|six)\s*(?P<kind>s\.\s?f\.?|sf\b|sig\.?\s*figs?\.?|significant\s+figures?|d\.\s?p\.?|dp\b|decimal\s+places?|decimal\s+place)"
                 # STEM repair 4: 'to the nearest euro', 'to the nearest whole year': the whole unit the value counts in (validated by the caller:
                 # the word written after the value, a word the task writes after its numbers, or the value's own unit spelled out)
                 r"|the\s+nearest\s+(?:whole\s+)?(?P<noun>[A-Za-z]{2,20})\b)")
_ROUND_BEFORE_RE = re.compile(_ROUND_PHRASE, re.IGNORECASE)
#: a rounding right after the value, a word naming the value's unit between them ('5903 euros to the nearest euro'; STEM repair 4)
_ROUND_AFTER_RE = re.compile(r"^\s*(?P<unitword>[A-Za-z]{2,20}(?=[\s,(]))?\s*[,(]?\s*(?:\(\s*)?(?P<phrase>" + _ROUND_PHRASE + ")", re.IGNORECASE)
#: STEM repair 5 (rule rounding-cue): a precision in brackets right after the value, with no "to" ('P = 16.5 W (3 s.f.)', '0.0866 (3 sf)')
_ROUND_BRACKET_RE = re.compile(r"^\s*\(\s*(?P<phrase>(?P<n>\d{1,2}|one|two|three|four|five|six)\s*(?P<kind>s\.\s?f\.?|sf\b|sig\.?\s*figs?\.?|"
                               r"significant\s+figures?|d\.\s?p\.?|dp\b|decimal\s+places?))\s*\)", re.IGNORECASE)
_SMALL_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
#: rule inline-restatement: a value after a connective right after the chain its statement closes ('= 16.4 W, so 16 W'); STEM repair 8: up
#: to three words that say what the value is may stand between the chain and a comma before the connective ('= 60.4% decrease, so 61% to 2
#: s.f.', '= 4773.74 euros, so 4774 euros to the nearest euro'), never a word that opens a clause of its own (a verb, a connective)
_INLINE_WORD = r"[ \t]+(?!(?:so|and|or|but|then|which|that|this|these|is|are|was|were|be|has|have|had|gives|giving|rounded|i\.e|ie|hence|thus|therefore)\b)[A-Za-z][A-Za-z’'-]{0,24}"
#: STEM repair 12 (rule inline-restatement): an approximation word after the connective ('= 2.67 A, which is about 2.7 A', 'i.e.
#: approximately', 'or roughly', 'that is, about') or on its own after the comma ('= 2.67 A, about 2.7 A to 2 s.f.', '= 37.7%, about 38%')
#: marks the value as the chain's result restated, rounded: R8, with no τ (the word names the rounding, it never widens the band). Before,
#: only 'or about', 'so about' and 'so approximately' were read, so a wrong rounding after ', which is about' or ', about' had no check
_APPROX_RESTATE = r"(?:about|approximately|approx\.?|roughly|around|nearly)"
#: The rounding the line states may also be a verb ('= 2.67 A, which rounds to 2.7 A', '…, rounded to 2.7 A'), the approximation word may
#: say 'equal to' ('…, which is approximately equal to 2.7 A'), and the value may stand in brackets after it ('= 2.67 A (about 2.7 A)')
_INLINE_RESTATE_RE = re.compile(r"X+x*(?:(?:" + _INLINE_WORD + r"){1,3}[ \t]*(?=,))?(?P<label>\s*\([^()\n]{1,80}\))?\s*,?\s*(?:(?:so|i\.\s?e\.|ie|that\s+is|"
                                r"which\s+is|or|giving|rounded)(?:\s*,?\s*" + _APPROX_RESTATE + r")?|" + _APPROX_RESTATE
                                + r"|(?:which\s+)?rounds?\s+(?:up\s+|down\s+)?to|rounded\s+(?:up\s+|down\s+)?to"
                                + r"|(?:(?:which|that)\s+is\s+)?" + _APPROX_RESTATE + r"\s+equal\s+to|\(\s*" + _APPROX_RESTATE + r")\s*$", re.IGNORECASE)
#: the connectives rule inline-restatement read before STEM repair 12 (an approximation word only in 'or about', 'so about', 'so
#: approximately'): a value after one of these keeps that reading whatever stands before it in its statement
_INLINE_CONNECTIVE_RE = re.compile(r"X+x*(?:(?:" + _INLINE_WORD + r"){1,3}[ \t]*(?=,))?(?P<label>\s*\([^()\n]{1,80}\))?\s*,?\s*(?:so|i\.\s?e\.|ie|that\s+is|"
                                   r"which\s+is|or|giving|rounded|or\s+about|so\s+about|so\s+approximately)\s*$", re.IGNORECASE)


def _round_half_width(m: "re.Match[str]", value: Fraction, unit_place: Optional[Fraction] = None) -> Optional[Fraction]:
    """The half-width of a value rounded as ``m`` states it (in the value's written unit), or None. ``unit_place``: the size, in the
    value's unit, of the unit a rounding 'to the nearest <unit>' names (the caller validated it)."""
    word = m.groupdict().get("word")
    if word:
        place = _ROUND_WORDS[" ".join(word.lower().split())]
        return Fraction(1, 2) * Fraction(10) ** (-place)
    if m.groupdict().get("noun"):
        # STEM repair 4: 'to the nearest euro', the value's whole unit; 'to the nearest cent', a part of it
        return None if not unit_place else Fraction(1, 2) * unit_place
    n_text, kind = m.group("n"), (m.group("kind") or "").lower()
    n = int(n_text) if n_text.isdigit() else _SMALL_NUMBERS.get(n_text.lower())
    if n is None or n > 15:
        return None
    if kind.startswith("d"):
        return Fraction(1, 2) * Fraction(10) ** (-n)
    if n < 1 or value == 0:
        return None
    a = abs(value)
    k = 0  # the power of ten of the value's leading digit (exact, by comparison)
    while a >= 10 and k < 400:
        a /= 10
        k += 1
    while a < 1 and k > -400:
        a *= 10
        k -= 1
    return Fraction(1, 2) * Fraction(10) ** (k - n + 1)


#: STEM repair 5: an abbreviation whose full stop ends no sentence ('To 3 s.f. the power is 16.5 W': the clause holds the rounding)
_ABBREV_END_RE = re.compile(r"(?:\bs\.\s?f|\bd\.\s?p|\bi\.\s?e|\be\.\s?g|\bapprox|\bsig|\bfigs?|\bsf|\bdp)$", re.IGNORECASE)


def _last_sentence_end(before: str) -> int:
    """The index of the last full stop followed by a space in ``before`` that ends a sentence (never the full stop of 's.f.', 'd.p.',
    'i.e.', 'e.g.', 'approx.', 'sig. fig.'), or -1."""
    k = before.rfind(". ")
    while k >= 0 and _ABBREV_END_RE.search(before[max(0, k - 8):k]):
        k = before.rfind(". ", 0, k)
    return k


def _rounding_opens_clause(before: str) -> bool:
    """Rule ``result-rounding`` (STEM repair 11): the last rounding the prose states in the clause before a chain's result (as rule
    rounding-cue cuts the clause) opens that clause, with no number before it: 'To 2 s.f., 1000 ÷ 3 = 330' (the rounding is the
    result's), never 'so 5902 euros to the nearest euro, and $4000(1.036)^{12} = 6114.73$' (the rounding closes the restatement of
    5902, and the next chain's result is written to the cent)."""
    cut = max(_last_sentence_end(before), before.rfind(";"), before.rfind("\n"), before.rfind(":"))
    clause = (before[cut + 1:] if cut >= 0 else before)[-200:]
    found = None
    for m in _ROUND_BEFORE_RE.finditer(clause):
        found = m
    return found is not None and re.search(r"\d", clause[:found.start()]) is None


def _rounding_cue(before: str, after: str, value: Fraction, noun_ok=None) -> Optional[tuple[Fraction, str]]:
    """Rule ``rounding-cue`` (STEM repair 1): a rounding the prose states for a restated value, in its clause before it ("To the
    nearest whole number, the decrease is 61%") or right after it ("60%, to 2 s.f."): ``(half-width, phrase)``, else None. A
    value inside the phrase itself (the 2 of "to 2 s.f.") is never a restated value: the phrase must be complete before it.
    STEM repair 4: a word naming the value's unit may stand between the value and a rounding after it ('5903 euros to the nearest
    euro'), and a rounding to the nearest whole unit names that unit ('to the nearest euro'); ``noun_ok(word, unit_word)`` says
    whether a word names the value's unit (no word is read without it)."""
    cut = max(_last_sentence_end(before), before.rfind(";"), before.rfind("\n"), before.rfind(":"))
    clause = before[cut + 1:] if cut >= 0 else before
    found = None
    for m in _ROUND_BEFORE_RE.finditer(clause[-200:]):
        found = m
    if found is None and after:
        found = _ROUND_AFTER_RE.match(after[:120])
        if found is not None and found.group("unitword") and not (noun_ok is not None and noun_ok(found.group("unitword"), True)):
            found = None
        if found is None:
            found = _ROUND_BRACKET_RE.match(after[:40])  # STEM repair 5: '16.5 W (3 s.f.)'
    if found is None:
        return None
    noun = found.groupdict().get("noun")
    place = noun_ok(noun, False) if noun and noun_ok is not None else None
    if noun and not place:
        return None
    h = _round_half_width(found, value, place)
    shown = found.group("phrase") if "phrase" in found.re.groupindex else found.group(0)
    return None if h is None else (h, " ".join(shown.split()))


def _restating_word(before: str) -> bool:
    """The word right before the value is not a preposition (``at 300 K`` is a condition), so a rounding cue may restate it."""
    words = _words(before[-120:])
    k = len(words) - 1
    while k >= 0 and words[k] in _QUALIFIERS:
        k -= 1
    return k >= 0 and words[k] not in _PREPOSITIONS


#: what may follow an inline restatement in its statement: punctuation, a bracket, a stated rounding
_CLAUSE_END_RE = re.compile(r"^\s*(?:[.;,)]|\(\s*(?:to\s+)?\d{1,2}\s*(?:s\.\s?f\.?|sf|d\.\s?p\.?|dp)\s*\)|(?:to\s+)?\d{1,2}\s*(?:s\.\s?f\.?|d\.\s?p\.?)|"
                            r"\(?\s*" + _ROUND_PHRASE + r"\s*\)?)?\s*[.;]?\s*$", re.IGNORECASE)


#: STEM repair 4: a stated rounding after the value, a word naming its unit before it, and then the statement's end or a new clause
#: ('5903 euros to the nearest euro, and …'): the stated rounding marks the value as a restatement
_ROUNDED_TAIL_RE = re.compile(r"^\s*(?P<unitword>[A-Za-z]{2,20}(?=[\s,(]))?\s*,?\s*\(?\s*" + _ROUND_PHRASE + r"\s*\)?\s*(?:[.;]?\s*$|[,;])", re.IGNORECASE)


#: STEM repair 4: a word naming the value's unit, then nothing but the statement's end ('so 4775 euros.')
_UNIT_WORD_END_RE = re.compile(r"^\s*(?P<unitword>[A-Za-z]{2,20})\s*[.;)]?\s*$")


def _clause_ends(after: str, noun_ok=None) -> bool:
    """Nothing but punctuation, a closing bracket or a stated rounding follows the value in its statement (``so 16 W`` but never
    ``so 12 N in total``: a consequence, not a restatement). STEM repair 4: a stated rounding after the value, with a word naming the
    value's unit before it, may be followed by a new clause ('so 5903 euros to the nearest euro, and …'); ``noun_ok(word, unit_word)``
    says whether a word names the value's unit (a rounding to the nearest of anything else ends nothing)."""
    m = _CLAUSE_END_RE.match(after[:60])
    if m is not None and not (m.groupdict().get("noun") and not (noun_ok is not None and noun_ok(m.group("noun"), False))) \
            and not (m.groupdict().get("placeunit") and not (noun_ok is not None and noun_ok(m.group("placeunit"), True))):
        return True
    if noun_ok is None:
        return False
    m = _UNIT_WORD_END_RE.match(after[:60])
    if m is not None:
        return noun_ok(m.group("unitword"), True)  # 'so 4775 euros.': the word the task counts in, then the statement's end
    m = _ROUNDED_TAIL_RE.match(after[:120])
    if m is None:
        return False
    if m.group("unitword") and not noun_ok(m.group("unitword"), True):
        return False
    if m.groupdict().get("placeunit") and not noun_ok(m.group("placeunit"), True):
        return False  # 'to the nearest ten euros': the word after the place must name the value's unit too
    return not (m.groupdict().get("noun") and not noun_ok(m.group("noun"), False))


def _inline_restatement(before: str) -> bool:
    """Rule ``inline-restatement``: the value follows the chain its statement just closed, after a connective only."""
    return bool(_INLINE_RESTATE_RE.search(before[-150:]))


def plan_relations(items: list[MathItem], prose_values: list[ProseValue], scope: Scope, request: RequestReading, profile: StemProfile, *,
                   limits: StemLimits = DEFAULT_LIMITS, statement_order: Optional[dict[str, int]] = None,
                   code_items: Optional[list[tuple[str, int, int, str]]] = None, request_mode: bool = False,
                   definitions: Optional[list[tuple[int, str, str, frozenset[str], str]]] = None,
                   reading: str = "", text: str = "", answer_text: str = "", reference_checks: bool = True) -> tuple[list[Relation], list[FrontEndFinding], list]:
    """Classify every link of ``items`` (in document order), record bindings and formulas in
    ``scope``, plan the checks and assign stable ids. Returns ``(relations, findings,
    request relations)``; the request mode records bindings, formulas and relations only. ``definitions`` are the
    symbols the answer names by a description (:func:`named_quantities`, with each statement's order, part and id): a
    decimal it states in prose for one of them is a stated root of the equation in it (``_described_roots``). ``reading``
    is the reading view the items were read from: a model's application is told apart from a product by it (the letter
    glued to its bracket, ``models.application_of``); without it no application is read. ``answer_text`` (the whole
    answer) is read for the extrapolation caveats of the argument diagnostics. ``reference_checks`` False leaves the reference
    checks out (the closed table of booklet laws is read with them off, :func:`.reference.booklet_laws`)."""
    order = statement_order or {}
    planner = _Planner(items, prose_values, scope, request, profile, limits, order, code_items or [], request_mode, definitions, reading, text)
    planner.answer_lower = answer_text[:400_000].lower()
    planner.answer_text = answer_text[:400_000]
    planner.reference_checks = reference_checks
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
        out.append(replace(r, check_id=cid, capped=cid in capped_set, related_ids=_related_statements(r, scope) if cid and r.kind == "sub" else ()))
    if capped_ids:
        findings.append(FrontEndFinding("ST-LIM-002", ST_SEVERITY["ST-LIM-002"], f"{total} STEM checks were planned; the cap is {limits.max_checks_per_report}, so "
                                        f"{len(capped_ids)} are not checked (first unchecked: {', '.join(capped_ids[:8])})",
                                        tuple(dict.fromkeys(s for r in out if r.capped for s in r.statement_ids))[:32]))
    # findings that named a planned relation by its index now name its check id
    by_index = {r.index: r.check_id for r in out}
    findings = [replace(f, check_id=by_index.get(int(f.check_id[1:]), "")) if f.check_id.startswith("#") else f for f in findings]
    return out, findings, planner.request_relations


# ----------------------------------------------------------------------------------------------- argument diagnostics: STEM method faults
# Ported from the argument diagnostics line (docs/ARGUMENT_DIAGNOSTICS.md, sections 3.4 and 20): the readers of the named STEM
# method faults (ST-REF, ST-UNIT-003, ST-STEP, ST-ROUND, ST-RANGE, ST-WORK, ST-GIVEN and ST-SCOPE-002).


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


#: words right before a stated operation that say the step does NOT apply it ('Factorising, rather than dividing by t, keeps t = 0'):
#: the operation is a mention, never a step (port onto the integrated translator, recorded arena answer maa-t13)
_NEGATED_OPERATION_RE = re.compile(r"\b(?:rather\s+than|instead\s+of|without|not|never|avoid|avoiding)\s*$", re.IGNORECASE)


def _operation_hits(gap: str) -> list:
    """The operations ``gap`` states (:data:`_OPERATION_RES`), each as (name, match), leaving out one the prose negates."""
    return [(name, m) for name, rx in _OPERATION_RES for m in [rx.search(gap)]
            if m is not None and not _NEGATED_OPERATION_RE.search(gap[max(0, m.start() - 24):m.start()])]


_NONZERO_CUES = ("≠ 0", "≠0", "!= 0", "not zero", "non-zero", "nonzero", "not equal to zero", "not equal to 0", "> 0", "≥ 0", "positive")


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


KELVIN_READING = "kelvin"


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


_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


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


def _distinct(b1: Binding, b2: Binding) -> bool:
    """Two bindings of one symbol that state different values as written (in SI when both units read exactly): "R = 10 Ω"
    and "R = 20 Ω" are two values, although a whole number with a trailing zero read at one significant figure would let
    them meet within rounding (:meth:`.scope.Binding.same_as`); "t = 5.0 s" and "t = 5000 ms" are one."""
    a, b = b1.si, b2.si
    if a is not None and b is not None and b1.unit is not None and b2.unit is not None:
        return a != b
    return b1.value != b2.value or (b1.unit is None) != (b2.unit is None)


_MARKS_RE = re.compile(r"\[\s*+(\d{1,2}+)\s*+(?:marks?+)?+\s*+\]|\(\s*+(\d{1,2}+)\s*+marks?+\s*+\)")


_PROPERTY_SHOW_RE = re.compile(r"\bshow\s+that(?:\s{3,}+|\s++[^.?!\s](?:[^.?!]{0,38}[^.?!\s])?\s+)(?:is|are)\s+(?:not\s+)?(?:an?\s+)?(?:prime|composite"
                               r"|irrational|rational|even|odd|integer|whole\s+number|natural\s+number|perfect\s+(?:square|cube)|multiple\s+of|factor\s+of"
                               r"|divisible\s+by)\b")


_REASONED_RE = re.compile(r"\b(?:so|because|since|therefore|hence|thus|it\s+follows|as\s+it)\b")


_IR_ORDER_SIGN = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥", "eq": "="}


_MATH_ORDER_OPS = frozenset({"<", "≤", ">", "≥", "⩽", "⩾"})


_FLIP_MATH = {"<": ">", ">": "<", "≤": "≥", "≥": "≤", "⩽": "⩾", "⩾": "⩽"}


_ROUNDING_WORDS_BEFORE_RE = re.compile(r"(?:\bto\s+(?:\d|one|two|three|four)\s*(?:s\.?\s?f\.?|sig(?:nificant)?\.?\s*fig(?:ure)?s?|d\.?\s?p\.?|decimal places?)"
                                       r"|\brounded(?:\s+(?:off|up|down))?"
                                       # 'which rounds to 50 mg dm⁻³', '38.4 °C to the nearest whole number is 38 °C' (accuracy round 1, ADV6-05)
                                       r"|\brounds(?:\s{1,3}(?:off|up|down))?|\bto\s{1,3}the\s{1,3}nearest\b)[^.;]{0,24}$")


_ROUNDING_PLACE = (r"(?:the\s{1,3}nearest(?:\s{1,3}[a-z]{1,12}){1,2}|(?:\d|one|two|three|four)\s{0,3}(?:s\.?\s?f\.?|sig(?:nificant)?\.?\s{0,3}fig(?:ure)?s?|"
                   r"d\.?\s?p\.?|decimal\s{1,3}places?))")


_PROSE_ROUNDING_BETWEEN_RE = re.compile(
    r"\s{0,3},?\s{0,3}(?:which\s{1,3})?(?:(?:is|was)\s{1,3})?"
    r"(?:(?:rounded|rounds)(?:\s{1,3}(?:off|up|down))?\s{1,3}to(?:\s{1,3}" + _ROUNDING_PLACE + r")?|to\s{1,3}" + _ROUNDING_PLACE + r")"
    r"\s{0,3},?\s{0,3}(?:(?:this|that|it)\s{1,3})?(?:(?:is|was|gives|becomes)\s{0,3})?",
    re.IGNORECASE)


_ROUNDING_WORDS_AFTER_RE = re.compile(r"\s*\(?\s*(?:to|correct to)?\s*(?:\d|one|two|three|four)\s*(?:s\.?\s?f\.?|sig(?:nificant)?\.?\s*fig(?:ure)?s?|"
                                      r"d\.?\s?p\.?|decimal places?)\b")


_FLIP_ORDER = {"lt": "gt", "le": "ge", "gt": "lt", "ge": "le", "eq": "eq"}


_INPUT_BEFORE_RE = re.compile(r"\b(?:at|for|when|if|with)\s+(?!(?:every|each|per)\b)(?:(?:a|an|the)\s+)?(?:[^\W\d_]+\s+){0,3}$", re.IGNORECASE)


_RATE_AFTER_RE = re.compile(r"\s*(?:per\b|/|an?\s+(?:year|month|week|day|hour|minute|second|decade|century)\b|each\b|every\b)", re.IGNORECASE)


_YEAR_INPUT_RE = re.compile(r"(?:\b(?:in|by|for|at|until|till|reach(?:es|ed)?|year|t\s*=|y\s*=)\s+(?:the\s+year\s+)?|\(\s*)(?P<y>1[0-9]{3}|2[0-9]{3})(?![\d.,]\d)",
                            re.IGNORECASE)


_CAVEAT_NEGATION_RE = re.compile(r"\b(?:not|no|never|nothing|hardly|without|isn['’]t|aren['’]t|wasn['’]t|is\s+n['’]t)\b[^.;:!?]{0,24}$", re.IGNORECASE)


_PROBABILITY_HEAD_RE = re.compile(r"(?:^|\s)P\s*\(.{1,40}\)\s*$|\bprobability\b", re.IGNORECASE)


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


_SET_TOTAL_RE = re.compile(r"\b(?:group|class|sample|survey|school|club|set|year|population|team)\s+of\s+(\d{1,6})\b|\b[Oo]f\s+(?:the\s+)?(\d{1,6})\s+"
                           r"(?:students|pupils|people|members|children|adults|customers|patients|participants|workers|employees|voters)\b")


_SET_COUNT_RE = re.compile(r"\b(\d{1,6})\s+(?:of\s+them\s+)?(?:study|studies|take|takes|like|likes|play|plays|own|owns|have|has|speak|speaks|chose|"
                           r"choose|prefer|prefers|use|uses|read|reads|watch|watches|eat|eats|drink|drinks|visit|visited|attend|attends|do|does|keep|keeps)\s+"
                           r"(both|neither|none|[A-Z][a-z]{1,20}|[a-z]{3,20})\b")


_NUMERAL_RE = re.compile(r"(?<![\d.])\d{1,6}(?![\d.])")


_PLAIN_SENTENCE_RE = re.compile(r"[^.!?\n]{1,2000}[.!?]?")


_PROSE_RANGE_RE = re.compile(r"(?:\bbetween\s+(?P<lo>\d[\d,]*(?:\.\d+)?)\s*(?:[A-Za-z°µ%][A-Za-z°µ%/²³⁻¹]{0,11}\s+)?and\s+(?P<hi>\d[\d,]*(?:\.\d+)?)"
                             r"|\bfrom\s+(?P<lo2>\d[\d,]*(?:\.\d+)?)\s*(?:[A-Za-z°µ%][A-Za-z°µ%/²³⁻¹]{0,11}\s+)?to\s+(?P<hi2>\d[\d,]*(?:\.\d+)?)"
                             r"|(?P<lo3>\d[\d,]*(?:\.\d+)?)\s*[–-]\s*(?P<hi3>\d[\d,]*(?:\.\d+)?))\s*(?P<u>[A-Za-z°µ%][A-Za-z°µ%/²³⁻¹]{0,11})?")


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


_VARIABLE_UNIT_RE = re.compile(r"[^.;\n]{0,60}?\bin\s+([A-Za-z°µ%][A-Za-z°µ%/²³⁻¹]{0,11})")


_INCONSISTENCY_NOTED_RE = re.compile(r"\b(?:inconsistent|contradict\w*|do(?:es)?\s+not\s+(?:agree|match|fit)|cannot\s+all\s+(?:hold|be\s+true)|"
                                     r"impossible|not\s+consistent|incompatible)\b", re.IGNORECASE)


_UNIFORM_MOTION_RE = re.compile(r"\b(?:uniform(?:ly)?|constant\s+(?:acceleration|deceleration|rate)|steadily|at\s+a\s+steady\s+rate"
                                r"|free(?:ly)?[\s-]+fall(?:s|ing)?|falls?\s+freely|in\s+free\s+fall|dropped|released\s+from\s+rest|under\s+gravity)\b",
                                re.IGNORECASE)


_RESISTED_MOTION_RE = re.compile(r"\b(?:air\s+resistance|drag|terminal\s+(?:velocity|speed)|friction)\b", re.IGNORECASE)


_RESISTANCE_NEGLECTED_RE = re.compile(r"\b(?:neglect(?:ing)?|ignor(?:e|ing)|no|without|negligible)\s+(?:the\s+)?(?:any\s+)?(?:air\s+resistance|drag|friction)\b"
                                      r"|\b(?:air\s+resistance|drag|friction)\s+(?:is|are|can\s+be)\s+(?:negligible|neglected|ignored)\b", re.IGNORECASE)


_LEAD_SCOPE_RE = re.compile(r"\s*([^=<>≤≥≈,:;\n]{2,80}?)\s*[,:]")


_BARE_LABEL_RE = re.compile(r"\b(?:of|for|in|on)\s+(?:the\s+)?(?:[a-z]+\s+)?([A-Z]|\d{1,2})(?![\w.])")


_OF_OBJECT_RE = re.compile(r"\s*(?:[A-Za-zµμ°⁻¹²³]{1,6}\s+){0,3}?(?:of|for)\s+([A-Z][A-Za-z0-9₀-₉()]{0,15})")


_ASK_SENTENCE_RE = re.compile(r"(?:^|(?<=[.!?\n]))\s*(?:\(?[a-z]\)\s*)?(?:Calculate|Find|Determine|Work out|Compare|Explain|Show|State|Estimate|"
                              r"Predict|What|Which|How)\b[^.!?\n]{0,200}", re.IGNORECASE)


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


_CLAUSE_JOINS = (" and ", " while ", " whereas ", " but ")


def _clause_cut(text: str, i: int) -> bool:
    """``text[i]`` ends a clause: a comma, colon, semicolon, line break or relation sign, or sentence punctuation that is no
    decimal point ('2.0')."""
    ch = text[i]
    if ch in ";:\n,=":
        return True
    return ch in ".!?" and not (0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit())


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


_IS_THE_TARGET_RE = re.compile(r"^\s*(?:is|was|equals|is\s+equal\s+to|is\s+exactly)\s+(?:the|our|its|their|this|that)?\s*$", re.IGNORECASE)


_CONDITION_RE = re.compile(r"\b(?P<pred>[A-Za-z]{4,})\s+(?:only\s+if|provided(?:\s+that)?|as\s+long\s+as)\b"
                           # a plain "if" after a copula ('The method is accepted if the yield is at least 60%', 'A beam is safe if the
                           # load on it is at most 50 kN'): the predicate the request makes conditional (repair round 5, ADV5-05)
                           r"|\b(?:is|are|was|were|be|been|deemed|considered|counts\s+as)\s+(?P<pred2>[A-Za-z]{4,})\s+(?:if|when)\b")


_CONDITION_EXTRA_RE = re.compile(r"\b(?:has|have|had)\s{1,3}(?:a\s{1,3}|an\s{1,3})?(?P<pred3>[A-Za-z]{4,24})\s{1,3}(?:if|when)\b"
                                 r"|\b(?:can|may)\s{1,3}(?P<pred4>[A-Za-z]{3,24}?)ly\s{1,3}[A-Za-z]{2,24}\b")


_EXCEEDS_BEFORE_RE = re.compile(r"\bexceeds?\s{0,3}$", re.IGNORECASE)


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


def _named_clause_tail(text: str) -> str:
    """The last clause of ``text`` (bounded by the caller): after its last clause cut and its last joining conjunction."""
    cut = next((i for i in range(len(text) - 1, -1, -1) if _clause_cut(text, i)), -1)
    tail = text[cut + 1:]
    j = max(tail.lower().rfind(w) for w in _CLAUSE_JOINS)
    return tail[j + 1:] if j >= 0 else tail


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
