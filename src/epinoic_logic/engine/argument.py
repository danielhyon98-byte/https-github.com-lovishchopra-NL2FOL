"""The argument stage of ``verify``: named diagnostics decided from the bound problem and its result (rules ``argdiag-2``).

The runner calls :func:`diagnose` after the decision and before the result is bound and signed, inside the memory window
of the verification, unless the caller passed ``diagnose=False`` (the internal probes, cross checks, branch formal checks
and constraint checks do). Its two outputs become ``VerificationResult.named_diagnostics`` and
``VerificationResult.argument_rules``; both are covered by the result's signature, and the runner applies the caller's
``severity_cap`` (an ambiguous translation's reading) before signing, so every copy of a diagnostic has one severity.

Contract of :func:`diagnose` (the engine rules of the code table, ``named.NAMED_CODES`` with layer ``engine``):

* inputs: the validated problem, the procedure outcome (status, unsat core, model), the compiled problem, the solver
  configuration, the enforced validation limits and the engine diagnostics already on the result (E108, E110, E111,
  E112, W110, W111, the solver codes);
* output: ``(diagnostics, argument_rules)``. ``argument_rules`` is :data:`~epinoic_logic.version.ARG_RULES_VERSION` when
  the diagnosis finished, even when it found nothing, and ``named.incomplete_rules(<reason>)`` when a budget ran out or a
  derived run was undecided (an exhausted budget is recorded, never read as "none found"); every diagnostic is an
  engine-layer :class:`~epinoic_logic.named.NamedDiagnostic` made with ``named.named_diagnostic``;
* the rules decide only from the bound problem: expressions, recorded grounding kinds and ``verified`` flags (a premise is
  established only by ``authority.has_authority``, never by its label), meanings and labels read through
  :mod:`epinoic_logic.lexis`, and derived engine runs. A derived problem is built only by copying validated expression
  dicts into the allowlisted wrappers ``implies``, ``not``, ``and`` and ``iff``, passes the engine validator and is
  recorded by digest (``derived_problem_digests``); nothing is evaluated or executed;
* bounds (:data:`MAX_DERIVED_RUNS`, :func:`run_budget_ms`): at most 24 derived runs per result, each under
  ``min(config.timeout_ms, 1000)`` ms and the configuration's rlimit under the same enforced limits, and at most
  ``min(4 * config.timeout_ms, 8000)`` ms in all. A derived TIMEOUT or UNKNOWN fires nothing;
* diagnostics only add: :func:`diagnose` never changes the status, the dependency lists or the engine diagnostics.

How a derived run is decided. Each derived problem is built as data from the bound problem (a subset of its premises,
copied, plus any new step), validated by the engine validator under the enforced limits and digested. It is then decided
on the bound problem's own compiled terms, in one Z3 context for the whole diagnosis: the premises it keeps reuse their
compiled terms, a new step and its conclusion are compiled by ``compiler.compile_expr``, and one fresh solver per run
checks, under tracking literals and the run's timeout, rlimit and seed, first that its premises are consistent and then
whether they entail its conclusion, exactly as ``procedures.run_entailment`` decides a problem. Only the context and the
compiled premise terms are shared, so a run costs a few milliseconds instead of a fresh context and compilation.

What the rules are (``engine/ARGUMENT.md`` has each rule with its control):

* **From the engine's own status** (derivation ``engine_status``): ARG-CONTRA-001 for INCONSISTENT_PREMISES (the
  conflicting core is named), ARG-VAC-001 for E108 (a warning on an ENTAILED proof that uses none of its premises; an info
  record on a result over no premise at all: a counterexample shows only that nothing the claim rests on was encoded, and
  a proof only that the point is a logical truth, such as an identity the task asks to show), ARG-CIRC-001 for
  E112 (an info record when every restating premise is a fact stated from subject knowledge and no reason is offered:
  the encoding transcribes a bare factual sentence). Nothing else runs on a no-verdict result.
* **R0, the re-check of an ENTAILED point** (derivation ``engine_recheck``). The point is decided again from the premises
  a check established (``V``). When that is not ENTAILED, the premises of the proof's core that no check established
  (``W``; the core falls back to every premise) are minimised by deletion (at most :data:`MAX_MINIMISED`, in premise
  order; the rest stay and the record says "partly minimised"), and what is left (``W*``) is split into the writer's
  links (implications, biconditionals, disjunctions, numeric relations that combine symbols: read from the expression,
  never from the label) and facts. ARG-LINK-001 (info) names each link with its missing link, ARG-FACT-001 (info) lists
  the facts. The pattern rules then read ``W*``: ARG-CIRC-002 (the point is equivalent to one unestablished premise,
  decided by a derived validity check), ARG-CIRC-003 (the writer's link derives the point from a fact whose gloss only
  restates it), ARG-AC-001 b and ARG-DA-001 b (the writer's link is the converse or the inverse of a stated rule),
  ARG-FD-001 (the writer's either/or, no tautology, options not complementary), ARG-HG-001 i (an open universal drawn
  from instance facts), ARG-CL-001 (a cause read into a sequence in time, with no control cue anywhere in the problem)
  and ARG-EQ-003 (a link defines the bare noun that a symbol's meaning qualifies by sense).
* **A COUNTEREXAMPLE's shape**: ARG-REFUTE-001 (the established premises entail the negated point), ARG-AC-001 a and
  ARG-DA-001 a (adding the converse or the inverse of a stated rule, which the facts match, makes the point follow),
  ARG-HG-001 ii (a universal point from instance facts no premise links to it), ARG-NS-001 (no premise mentions the
  point), ARG-NS-002 with ARG-EQ-002 (one bridge from a stated fact to the antecedent of a stated rule makes it follow:
  the missing link; an equivocation when the two meanings share a head noun one of them qualifies by sense),
  ARG-PART-001 (info: the falsified conjuncts are unlinked judgements and the rest follows) and ARG-INV-001 (it does
  not follow from reasons that mention it, and no more specific shape is named; only when every derived run of the
  diagnosis was decided, since an undecided run could have named a more specific shape). A counterexample that rests on
  figures the encoding leaves open (W110, W111) gets only ARG-REFUTE-001, and one over a purely numeric point only
  ARG-REFUTE-001 and ARG-PART-001: its counterexample is the arithmetic verdict, not a leap in logic.

The generic warnings (ARG-NS-001, ARG-NS-002, ARG-INV-001) give way to a more specific warning on the same assertions
(``named.suppress_dominated``, applied by the runner). Messages say what the encoding shows; they never call a premise
true, a step right or the claim settled. Like every result, a diagnostic concerns the encoding and this code only.
"""
from __future__ import annotations

import functools
import json
import re
import time
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Iterable, Optional, Sequence

import z3
from pydantic import ValidationError

from .. import lexis
from ..ir.canonical import canonical_json, problem_digest
from ..ir.schema import Problem
from ..named import NAMED_CODES, EvidenceSpan, MissingLink, NamedDiagnostic, incomplete_rules, model_text, named_diagnostic
from ..version import ARG_RULES_VERSION
from . import argument_cues as cues
from .authority import has_authority
from .compiler import Compiled, CompileError, compile_expr, compile_problem
from .errors import ADVISORY_CODES, NO_VERDICT_CODES, DiagnosticCode
from .procedures import ProcedureOutcome, extract_model
from .statuses import VerificationStatus
from .validator import validate_problem

__all__ = ["ENGINE_CODES", "MAX_DERIVED_RUNS", "RUN_TIMEOUT_MS", "TOTAL_BUDGET_MS", "MAX_MINIMISED", "MAX_BRIDGES", "MAX_CONVERSES",
           "MAX_EQUIVALENCES", "MAX_TAUTOLOGIES", "MAX_LINK_DIAGNOSTICS", "run_budget_ms", "diagnose", "gloss"]

#: The engine-layer codes of the table (the codes :func:`diagnose` may emit).
ENGINE_CODES: tuple[str, ...] = tuple(sorted(code for code, spec in NAMED_CODES.items() if "engine" in spec.layers and not spec.finding_only))
#: At most this many derived runs per result.
MAX_DERIVED_RUNS = 24
#: Ceiling of one derived run, and of all derived runs of one result, in milliseconds.
RUN_TIMEOUT_MS = 1000
TOTAL_BUDGET_MS = 8000
#: R0 minimises at most this many of the writer's premises by deletion; any beyond stay in W* ("partly minimised").
MAX_MINIMISED = 16
#: At most this many bridge runs (ARG-NS-002) and converse or inverse runs (ARG-AC-001 a, ARG-DA-001 a).
MAX_BRIDGES = 8
MAX_CONVERSES = 4
#: At most this many equivalence runs (ARG-CIRC-002) and tautology runs (ARG-FD-001).
MAX_EQUIVALENCES = 4
MAX_TAUTOLOGIES = 4
#: ARG-LINK-001 is one diagnostic per writer's link for this many links; the rest share one more.
MAX_LINK_DIAGNOSTICS = 8

_E108 = DiagnosticCode.VACUOUS_RESULT.value
_E112 = DiagnosticCode.CIRCULAR_PREMISES.value
_S = VerificationStatus
_LINK_OPS = frozenset({"implies", "iff", "or"})
_COMPARE = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})
_ARITH = frozenset({"add", "sub", "mul", "neg", "div", "idiv", "mod", "to_real", "ite"})
_LITERALS = frozenset({"int", "real"})
_OP_TEXT = {"eq": "=", "ne": "≠", "lt": "<", "le": "≤", "gt": ">", "ge": "≥", "add": "+", "sub": "-", "mul": "×", "div": "/", "idiv": "div", "mod": "mod"}
_COMPLEMENT = {"lt": "ge", "ge": "lt", "le": "gt", "gt": "le", "eq": "ne", "ne": "eq"}
_PART_CHARS = 300
_SHOW_VALUES = 6
_DECIDED = (_S.ENTAILED, _S.COUNTEREXAMPLE, _S.INCONSISTENT_PREMISES)


def run_budget_ms(config: Any) -> tuple[int, int]:
    """``(per derived run, in all)`` in milliseconds for a solver configuration: ``min(timeout_ms, 1000)`` and
    ``min(4 * timeout_ms, 8000)``."""
    timeout = int(getattr(config, "timeout_ms", RUN_TIMEOUT_MS) or RUN_TIMEOUT_MS)
    return min(timeout, RUN_TIMEOUT_MS), min(4 * timeout, TOTAL_BUDGET_MS)


# ----------------------------------------------------------------------------------------------- IR as data

def _canon(node: Any) -> str:
    return json.dumps(node, sort_keys=True, separators=(",", ":"))


def _base(node: dict) -> tuple[str, bool]:
    """``(canonical form without leading negations, odd number of them)``."""
    negated = False
    while isinstance(node, dict) and node.get("op") == "not":
        node, negated = node["arg"], not negated
    return _canon(node), negated


def _same(a: dict, b: dict) -> bool:
    return _base(a) == _base(b)


def _negation_of(a: dict, b: dict) -> bool:
    (ca, na), (cb, nb) = _base(a), _base(b)
    return ca == cb and na != nb


def _vars(node: Any) -> set[str]:
    out: set[str] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("op") == "var" and isinstance(n.get("name"), str):
                out.add(n["name"])
                continue
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(n)
    return out


def _conjuncts(node: dict) -> list[dict]:
    out: list[dict] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict) and n.get("op") == "and":
            stack.extend(reversed(n.get("args") or []))
        else:
            out.append(n)
    return out


def _atom(node: dict) -> Optional[tuple[str, bool]]:
    """``(symbol, negated)`` for a Bool atom or its negation, else None."""
    negated = False
    while isinstance(node, dict) and node.get("op") == "not":
        node, negated = node["arg"], not negated
    if isinstance(node, dict) and node.get("op") == "var":
        return node["name"], negated
    return None


def _has_op(node: Any, ops: frozenset) -> bool:
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("op") in ops:
                return True
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(n)
    return False


def _literal_values(node: Any) -> frozenset:
    """The values of the numeric literals of an expression (exact: "26" and "26.0" are one value)."""
    out: set = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("op") in _LITERALS:
                try:
                    out.add(Fraction(str(n.get("value"))))
                except (ValueError, ZeroDivisionError):
                    out.add(str(n.get("value")))
                continue
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(n)
    return frozenset(out)


def _symbol_side(node: dict) -> Optional[str]:
    if node.get("op") == "var":
        return node.get("name")
    if node.get("op") == "to_real" and isinstance(node.get("arg"), dict) and node["arg"].get("op") == "var":
        return node["arg"].get("name")
    return None


def _literal_side(node: dict) -> bool:
    if node.get("op") in _LITERALS:
        return True
    return node.get("op") == "neg" and isinstance(node.get("arg"), dict) and node["arg"].get("op") in _LITERALS


def _numeric_shape(node: dict) -> str:
    """``none`` (a proposition), ``assignment`` (each conjunct compares one symbol with one literal by eq, lt, le, gt or
    ge) or ``relation`` (any other numeric content: a relation that combines symbols, an inequation). The same reading
    as ``translate.relations.numeric_shape``, which the translation layer's premise roles use."""
    if not (_has_op(node, _COMPARE) or _has_op(node, _ARITH) or _has_op(node, _LITERALS)):
        return "none"
    for c in _conjuncts(node):
        op = c.get("op")
        if op not in _COMPARE or op == "ne":
            return "relation"
        left, right = c.get("left") or {}, c.get("right") or {}
        if not ((_symbol_side(left) and _literal_side(right)) or (_symbol_side(right) and _literal_side(left))):
            return "relation"
    return "assignment"


def _is_link_shape(node: dict) -> bool:
    """A link-shaped expression, read from the expression only: an implication, a biconditional, a disjunction or a numeric
    relation that combines symbols."""
    return node.get("op") in _LINK_OPS or _numeric_shape(node) == "relation"


def _link_parts(node: dict) -> list[dict]:
    """The link-shaped parts of a premise: the expression itself when it is link-shaped, else its link-shaped conjuncts (a
    writer's step hidden in a conjunction, "Nairobi grew, and two cities growing means every city grew": re-run review
    ADV-11 c). Empty for a fact."""
    if _is_link_shape(node):
        return [node]
    if node.get("op") == "and":
        return [c for c in _conjuncts(node) if isinstance(c, dict) and _is_link_shape(c)]
    return []


def _is_link(node: dict) -> bool:
    """A link-shaped premise (:func:`_link_parts` is not empty)."""
    return bool(_link_parts(node))


def _implies(a: dict, b: dict) -> dict:
    return {"op": "implies", "left": a, "right": b}


def _not(a: dict) -> dict:
    return a["arg"] if a.get("op") == "not" else {"op": "not", "arg": a}


def _and(args: Sequence[dict]) -> dict:
    return args[0] if len(args) == 1 else {"op": "and", "args": list(args)}


def _iff(a: dict, b: dict) -> dict:
    return {"op": "iff", "left": a, "right": b}


def _complementary(a: dict, b: dict) -> bool:
    """``p`` and ``not p``, or two comparisons of the same sides that exclude each other and cover every case."""
    if _negation_of(a, b):
        return True
    if a.get("op") in _COMPLEMENT and b.get("op") == _COMPLEMENT[a["op"]]:
        return _canon(a.get("left")) == _canon(b.get("left")) and _canon(a.get("right")) == _canon(b.get("right"))
    return False


# ----------------------------------------------------------------------------------------------- glosses

def _cut(text: str, limit: int = _PART_CHARS) -> str:
    """Model text (a gloss, a meaning, a label) as a message or a missing link shows it: one line, the forgery words
    masked, cut to ``limit`` (:func:`epinoic_logic.named.model_text`). Evidence spans keep the text: :func:`_raw`."""
    return model_text(text, limit)


def _raw(text: str, limit: int = _PART_CHARS) -> str:
    """Text as an evidence span keeps it: whitespace runs collapsed, cut to ``limit``."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def gloss(node: dict, meanings: dict[str, str], *, in_term: bool = False, depth: int = 0) -> str:
    """The words of an expression: an atom is its symbol's meaning (else its name); ``not``, ``and``, ``or``,
    ``implies`` and ``iff`` are words; a comparison is ``lhs op rhs`` with the meanings in parentheses. Cut to 300
    characters by the callers. Nothing is evaluated."""
    if depth > 48 or not isinstance(node, dict):
        return "..."
    op = node.get("op")
    d = depth + 1
    if op == "var":
        name = str(node.get("name"))
        meaning = (meanings.get(name) or "").strip()
        if in_term:
            return f"{name} ({_cut(meaning, 120)})" if meaning else name
        return meaning or name
    if op == "bool":
        return "true" if node.get("value") else "false"
    if op in _LITERALS:
        return str(node.get("value"))
    if op == "not":
        return f"not ({gloss(node['arg'], meanings, in_term=in_term, depth=d)})"
    if op == "and":
        return " and ".join(gloss(a, meanings, in_term=in_term, depth=d) for a in node.get("args") or [])
    if op == "or":
        return "either " + " or ".join(gloss(a, meanings, in_term=in_term, depth=d) for a in node.get("args") or [])
    if op == "implies":
        return f"if {gloss(node['left'], meanings, depth=d)} then {gloss(node['right'], meanings, depth=d)}"
    if op == "iff":
        return f"{gloss(node['left'], meanings, depth=d)} exactly when {gloss(node['right'], meanings, depth=d)}"
    if op in _COMPARE or op in ("sub", "div", "idiv", "mod"):
        return f"{gloss(node['left'], meanings, in_term=True, depth=d)} {_OP_TEXT[op]} {gloss(node['right'], meanings, in_term=True, depth=d)}"
    if op in ("add", "mul"):
        return "(" + f" {_OP_TEXT[op]} ".join(gloss(a, meanings, in_term=True, depth=d) for a in node.get("args") or []) + ")"
    if op == "neg":
        return f"-{gloss(node['arg'], meanings, in_term=True, depth=d)}"
    if op == "to_real":
        return gloss(node["arg"], meanings, in_term=True, depth=d)
    if op == "ite":
        return (f"({gloss(node['then'], meanings, in_term=True, depth=d)} if {gloss(node['cond'], meanings, depth=d)}, "
                f"else {gloss(node['otherwise'], meanings, in_term=True, depth=d)})")
    return str(op)


# ----------------------------------------------------------------------------------------------- lexical readings

def _tokens(text: Optional[str]) -> tuple[str, ...]:
    return _tokens_of(text or "")


@functools.lru_cache(maxsize=4096)
def _tokens_of(text: str) -> tuple[str, ...]:
    """``lexis.tokens`` of one gloss, read once: every rule reads the same meanings and labels (re-run review ADV-08)."""
    return tuple(lexis.tokens(text))


def _is_year(token: str) -> bool:
    return len(token) == 4 and token.isdecimal() and 1000 <= int(token) <= 2100


def _is_number(token: str) -> bool:
    return token.replace(",", "").replace(".", "").isdecimal() or token in cues.NUMBER_WORDS


def _open_universal(text: Optional[str]) -> Optional[str]:
    """The first open universal cue of ``text``: not closed by a number within the next three tokens ("all three",
    "each of the four"), and an "any" not in the scope of an earlier negation ("cannot find any")."""
    toks = _tokens(text)
    for i, cue in lexis.find_cues(toks, cues.UNIVERSAL):
        after = toks[i + len(cue): i + len(cue) + 3]
        if any(_is_number(t) for t in after):
            continue
        if cue == ("any",) and lexis.negation_markers(toks[:i]):
            continue
        return " ".join(cue)
    return None


def _majority(text: Optional[str]) -> Optional[str]:
    """The first majority cue of ``text`` (:data:`~.argument_cues.MAJORITY`) not closed by a number within the next three
    tokens ("most of the 12" speaks of the sample itself)."""
    toks = _tokens(text)
    for i, cue in lexis.find_cues(toks, cues.MAJORITY):
        if any(_is_number(t) for t in toks[i + len(cue): i + len(cue) + 3]):
            continue
        return " ".join(cue)
    return None


#: Cases named by a list after their plural noun: "the inputs 1, 2 and 3", "the towns A, B or C" (repair round 5, ADV5-15 a:
#: a universal drawn from the inputs tested was read as no instance fact).
_ENUMERATED_CASES_RE = re.compile(r"\b[^\W\d_]{3,}s\s+(?:\d+|[A-Z][\w-]*)(?:\s*,\s*(?:\d+|[A-Z][\w-]*))*\s*,?\s*(?:and|or)\s+(?:\d+|[A-Z][\w-]*)\b")
#: One case named by its label: a closed noun of a tested or sampled case and its number ("for input 7", "in trial 2",
#: "patient 12"): one labelled case, an instance as a list of them is. "Case" and "example" are left out: a proof by cases
#: names its cases so ("in case 1 ..., in case 2 ...") and covers them all.
_LABELLED_CASE_RE = re.compile(r"\b(?:input|test|trial|run|sample|patient|participant|quadrat|plot|site|station)\s+\d+\b", re.IGNORECASE)


def _instance(text: Optional[str]) -> bool:
    """A gloss that states an instance: an instance cue, a possessive (a named person or study), a year, a proper name (a
    capitalised word inside the gloss: "King John was cruel"; repair round 3, ADV3-13: a universal drawn in two steps from one
    named case), cases named by a list ("for the inputs 1, 2 and 3", :data:`_ENUMERATED_CASES_RE`) or one by its label ("for
    input 7", :data:`_LABELLED_CASE_RE`), or a sample of cases (:func:`_sample`)."""
    toks = _tokens(text)
    if lexis.has_cue(toks, cues.INSTANCE):
        return True
    if text and (_ENUMERATED_CASES_RE.search(text[:1000]) or _LABELLED_CASE_RE.search(text[:1000])):
        return True
    if any(t.endswith("'s") or _is_year(t) for t in toks):
        return True
    raw = text or ""
    if any(k > 0 and raw[a:a + 1].isupper() and tok.isalpha() and tok not in ("i",) and tok not in cues.MONTHS
           for k, (a, _b, tok) in enumerate(lexis.token_spans(raw[:1000]))):
        return True
    return _sample(toks)


#: Sample quantifiers that speak of a share of a population, not of the cases looked at: "many middle-class Germans lost
#: faith" states how many, it describes no sample (repair round 3, ADV3-05).
_QUANTITY_ONLY = frozenset({("many",), ("most",), ("a", "majority", "of"), ("certain",)})


def _looked_at(text: Optional[str]) -> bool:
    """A gloss that states what held for the cases looked at (:func:`_sample_fact`) by more than a quantity word: a sampling
    participle or unit, a count out of a total, a number that counts cases, or a sample quantifier other than "many", "most",
    "a majority of" and "certain"."""
    toks = _tokens(text)
    if not _sample_fact(text):
        return False
    if any(t in cues.SAMPLE_PARTICIPLES or t in cues.SAMPLING_UNITS for t in toks):
        return True
    if any(cue not in _QUANTITY_ONLY for _i, cue in lexis.find_cues(toks, cues.SAMPLE)):
        return True
    if any(_is_number(t) and not _is_year(t) and _counts_cases(toks, i) for i, t in enumerate(toks)):
        return True
    for i in range(len(toks) - 2):  # a count out of a total ("four of the five")
        if (_is_number(toks[i]) or toks[i] in cues.NUMBER_WORDS) and toks[i + 1] == "of":
            return True
    return False


def _sampling_marked(texts: Sequence[str]) -> bool:
    """Whether the texts mark the cases they count as a sample: a sampling participle or unit ("asked", "surveyed", "the
    survey"), or a sample quantifier short of a count ("some", "a few", "several")."""
    for text in texts:
        toks = _tokens(text)
        if any(t in cues.SAMPLE_PARTICIPLES or t in cues.SAMPLING_UNITS for t in toks):
            return True
        if any(cue not in _QUANTITY_ONLY for _i, cue in lexis.find_cues(toks, cues.SAMPLE)):
            return True
    return False


def _population_added(consequent: str, cue: str, ante_texts: Sequence[str]) -> list[str]:
    """The words the population of a majority claim adds to the counted cases' own words ("most students in the country"
    against "9 of the 12 students in our class": "country"): the words after the majority cue, from its first content word
    up to the first later content word the antecedent also holds (the predicate the count was taken of), less the
    antecedent's words."""
    have = {lexis.root(t) for text in ante_texts for t in _tokens(text)}
    toks = list(_tokens(consequent))
    cue_toks = tuple(cue.split())
    start = next((i + len(cue_toks) for i in range(len(toks)) if tuple(toks[i:i + len(cue_toks)]) == cue_toks), None) if cue_toks else 0
    if start is None:
        return []
    added: list[str] = []
    head_seen = False
    for t in toks[start:start + 16]:
        if t in lexis.FUNCTION_WORDS or not t.isalpha():
            continue
        r = lexis.root(t)
        if head_seen and r in have:
            break
        head_seen = True
        if r not in have and t not in added:
            added.append(t)
    return added


def _counts_cases(toks: Sequence[str], i: int) -> bool:
    """Whether the number at ``toks[i]`` counts cases: a plural noun follows it within three tokens, past function words
    and one modifier ("two cyclists", "12 participants", "three of the schools"), and no measurement word comes first
    ("5 metres", "12 per cent", "two years")."""
    for t in toks[i + 1: i + 4]:
        if t in cues.MEASURE_WORDS or _is_number(t):
            return False
        if t in cues.IRREGULAR_PLURALS or (t.isalpha() and len(t) > 3 and t.endswith("s") and not t.endswith("ss") and t not in lexis.FUNCTION_WORDS):
            return True
    return False


def _sample(toks: Sequence[str]) -> bool:
    """A gloss that states what held for a sample of cases (re-run review A-INF-HG): a sample quantifier ("some", "a few",
    "most": :data:`~.argument_cues.SAMPLE`) or a number that counts cases ("two cyclists"). A gloss that also holds a
    universal cue ("all thirty students") enumerates a whole, so it is no sample."""
    if lexis.has_cue(toks, cues.UNIVERSAL):
        return False
    if lexis.has_cue(toks, cues.SAMPLE):
        return True
    return any(_is_number(t) and not _is_year(t) and _counts_cases(toks, i) for i, t in enumerate(toks))


def _sample_fact(text: Optional[str]) -> bool:
    """A gloss that states what held for the cases looked at (repair round 2, holdout2 hasty class): a sample (:func:`_sample`),
    a sampling participle or unit ("the one quadrat sampled", "the five people interviewed": :data:`~.argument_cues.SAMPLE_PARTICIPLES`,
    :data:`~.argument_cues.SAMPLING_UNITS`), or a count out of a total ("four of the five", "9 of 12")."""
    toks = _tokens(text)
    if _sample(toks) or any(t in cues.SAMPLE_PARTICIPLES or t in cues.SAMPLING_UNITS for t in toks):
        return True
    for i in range(len(toks) - 2):
        if (_is_number(toks[i]) or toks[i] in cues.NUMBER_WORDS) and toks[i + 1] == "of":
            nxt = toks[i + 3] if toks[i + 2] == "the" and i + 3 < len(toks) else toks[i + 2]
            if _is_number(nxt) or nxt in cues.NUMBER_WORDS:
                return True
    return False


def _generalises(fact_text: Optional[str], point_text: Optional[str]) -> bool:
    """Whether the point states a sample fact's finding of a wider population (repair round 2, holdout2 hasty class): the fact is
    a sample (:func:`_sample_fact`) not said to stand for its population (:data:`~.argument_cues.REPRESENTATIVE`), the point
    keeps none of the sample's markers (its numbers, sampling participles and units), shares two of its content words (what
    was found) and adds one of its own (the wider whole: "the meadow", "pupils across Norway"). A point about the very
    cases looked at, or about most of them, adds no word ("4 of 5 students in our class passed, so most students in our
    class passed")."""
    if not fact_text or not point_text or not _looked_at(fact_text):
        return False
    ftoks, ptoks = _tokens(fact_text), _tokens(point_text)
    if lexis.has_cue(ftoks, cues.REPRESENTATIVE):
        return False
    if not _sampling_marked([fact_text]) and not _population_added(point_text, "", [fact_text]):
        # the fact counts a whole ("of the town's 1,000 residents") that the point speaks of again with no word of its own
        # in its subject: a census restated, not a sample generalised (repair round 3, ADV3-05)
        return False
    markers = {t for t in ftoks if _is_number(t) or t in cues.NUMBER_WORDS or t in cues.SAMPLE_PARTICIPLES or t in cues.SAMPLING_UNITS}
    if not markers or markers & set(ptoks):
        return False
    marker_stems = {lexis.root(t) for t in markers}
    fs, ps = set(lexis.content_stems(fact_text)) - marker_stems, set(lexis.content_stems(point_text))
    return len(fs & ps) >= 2 and bool(ps - fs - marker_stems)


#: A causative verb whose object is given a new degree ("sports drinks make runners faster", "the policy made firms more
#: profitable"): the verb, then one or two words, then a comparative (repair round 5, ADV5-15 b).
_CAUSATIVE_VERBS = frozenset({"make", "makes", "made", "making"})
_RESULT_COMPARATIVES = cues.COMPARATIVES | frozenset({"healthier", "fitter", "happier", "smarter", "safer", "cleaner", "quicker", "cheaper"})


def _causal(text: Optional[str]) -> Optional[str]:
    toks = _tokens(text)
    found = lexis.find_cues(toks, cues.CAUSAL)
    if found:
        return " ".join(found[0][1])
    for i, t in enumerate(toks):
        if t in _CAUSATIVE_VERBS:
            for k in (i + 2, i + 3):
                if k < len(toks) and toks[k] in _RESULT_COMPARATIVES:
                    return " ".join([t] + ["*"] * (k - i - 1) + [toks[k]])  # "make * faster": the object is no causal word
    return None


def _sequence(text: Optional[str]) -> Optional[str]:
    """The first cue of a sequence in time in ``text``. "since" counts only before a year, and "then" not after an "if"
    (the consequent of a conditional is no later time)."""
    toks = _tokens(text)
    for i, cue in lexis.find_cues(toks, cues.SEQUENCE):
        if cue == ("then",) and "if" in toks[:i]:
            continue
        return " ".join(cue)
    for i, t in enumerate(toks[:-1]):
        if t == "since" and _is_year(toks[i + 1]):
            return f"since {toks[i + 1]}"
    return None


def _correlation(text: Optional[str]) -> Optional[str]:
    """The correlation ``text`` states, as written, or None (causal leap, repair round 2): a correlation cue
    (:data:`~.argument_cues.CORRELATION`: "correlated with", "associated with", "tend to"), or two comparatives after a
    population noun and the relative or "with" clause that opens on it ("countries that eat more chocolate win more Nobel
    prizes", "towns with more ice cream sales have more drownings"), or one comparative in the main clause after such a
    clause of two words or more ("students who eat breakfast have higher grades"). A property of a physical class ("gases
    with more energy have faster particles") names no population, so it states none."""
    toks = _tokens(text)
    found = lexis.find_cues(toks, cues.CORRELATION)
    if found:
        return " ".join(found[0][1])
    for i, t in enumerate(toks[:-2]):
        if t not in cues.POPULATIONS or toks[i + 1] not in ("that", "who", "which", "with", "where", "whose"):
            continue
        comps = [k for k in range(i + 2, min(len(toks), i + 24)) if toks[k] in cues.COMPARATIVES and not (k + 1 < len(toks) and toks[k + 1] == "than")]
        if len(comps) >= 2 and comps[-1] - comps[0] >= 2:
            return " ".join(toks[i:comps[1] + 1])
        if len(comps) == 1 and comps[0] - (i + 1) >= 4:
            # one comparative in the main clause, after a relative clause of two words or more that sets a group apart by a
            # trait ("students who eat breakfast have higher grades": the group compared with the rest; repair round 4,
            # ADV4-08 a). A comparative inside a short clause ("students who scored higher passed") compares nothing yet.
            return " ".join(toks[i:comps[0] + 1])
    return None


def _cause_presupposed(cue: str, ante_texts: Sequence[str]) -> bool:
    """Whether the antecedent already holds the consequent's causal word ("effect", "cause", "result", ...): the point then
    says something of an effect the antecedent speaks of, not a cause read into what preceded it."""
    # the degree a causative gives its object ("faster" in "make * faster") is the effect itself, never a causal word
    words = {lexis.root(t) for t in _tokens(cue) if t not in lexis.FUNCTION_WORDS and t != "*" and t not in _RESULT_COMPARATIVES}
    if not words:
        return False
    have: set[str] = set()
    for text in ante_texts:
        have |= {lexis.root(t) for t in _tokens(text)}
    return bool(words & have)


def _two_times(texts: Sequence[str]) -> Optional[str]:
    """``"<time> and <time>"`` when the texts date their events at two different times (two different years, or two different
    months), else None."""
    years: list[str] = []
    months: list[str] = []
    for text in texts:
        for t in _tokens(text):
            if _is_year(t) and t not in years:
                years.append(t)
            elif t in cues.MONTHS and t not in months:
                months.append(t)
    if len(years) >= 2:
        return f"dated {years[0]} and {years[1]}"
    if len(months) >= 2:
        return f"dated {months[0]} and {months[1]}"
    return None


def _offers_reason(text: Optional[str]) -> bool:
    """Whether ``text`` holds a reason connective ("because of" is a cause phrase, not one)."""
    toks = _tokens(text)
    for i, cue in lexis.find_cues(toks, cues.REASON_CONNECTIVES):
        if cue == ("because",) and i + 1 < len(toks) and toks[i + 1] == "of":
            continue
        return True
    return False


def _control(text: Optional[str]) -> Optional[str]:
    """The first control cue of ``text`` that states a control (re-run review ADV-06): not negated by a word of
    :data:`~.argument_cues.CONTROL_NEGATORS` in the three tokens before it ("there was no control group"), and, for
    "compared with" and "compared to", not a comparison with another time ("compared with the months before April": a
    before-and-after comparison is the sequence in time itself)."""
    toks = _tokens(text)
    for i, cue in lexis.find_cues(toks, cues.CONTROL):
        if any(t in cues.CONTROL_NEGATORS for t in toks[max(0, i - 3):i]):
            continue
        if cue[0] == "compared":
            after = toks[i + len(cue): i + len(cue) + 4]
            if any(t in cues.TIME_WORDS or _is_year(t) for t in after):
                continue
        return " ".join(cue)
    return None


def _differ_only_by_date(a: Optional[str], b: Optional[str]) -> bool:
    """Two meanings equal word for word except where both have a year or a month: one quantity at two times."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or len(ta) != len(tb) or ta == tb:
        return False
    for x, y in zip(ta, tb):
        if x != y and not ((_is_year(x) and _is_year(y)) or (x in cues.MONTHS and y in cues.MONTHS)):
            return False
    return True


def _content_word(token: str) -> bool:
    return token.isalpha() and len(token) > 2 and token not in lexis.FUNCTION_WORDS and token not in cues.SENSE_EXCLUDED_HEADS


def _sense_gloss(inner: str) -> bool:
    """Whether a parenthetical glosses a sense ("theory (well-substantiated explanation)", "(a hunch)", "(scientific
    theory)") rather than naming a referent: it holds a sense qualifier or the word "sense", or it is a gloss in common
    words, with at least one content word, no number and no capitalised word (a name, a title, a date or a figure
    identifies what the noun refers to, never which sense of the noun is meant: "surge (the 1930 Reichstag election)")."""
    spans = lexis.token_spans(inner)
    toks = [t for _s, _e, t in spans]
    if any(t in cues.SENSE_QUALIFIERS or t == "sense" for t in toks):
        return True
    if not any(_content_word(t) for t in toks):
        return False
    for start, _end, tok in spans:
        if not tok.isalpha() or inner[start].isupper():
            return False
    return True


def _qualified_heads(meaning: Optional[str]) -> dict[str, str]:
    """``{stem of a head noun: its sense marker}`` for every noun a meaning qualifies by sense: a sense qualifier right
    before it ("scientific theory"), "in the ... sense" right after it, or a parenthetical gloss of its sense right after
    it ("theory (scientific theory)"; :func:`_sense_gloss`). Linear in the meaning."""
    text = meaning or ""
    spans = lexis.token_spans(text)
    toks = [t for _s, _e, t in spans]
    heads: dict[str, str] = {}
    for i in range(len(toks) - 1):
        if toks[i] in cues.SENSE_QUALIFIERS and _content_word(toks[i + 1]):
            heads.setdefault(lexis.stem(toks[i + 1]), f"{toks[i]} {toks[i + 1]}")
    for i in range(1, len(toks) - 2):
        if toks[i] == "in" and toks[i + 1] == "the" and "sense" in toks[i + 2: i + 6] and _content_word(toks[i - 1]):
            j = i + 2 + toks[i + 2: i + 6].index("sense")
            heads.setdefault(lexis.stem(toks[i - 1]), " ".join(toks[i - 1: j + 1]))
    closes = [k for k, ch in enumerate(text) if ch == ")"]
    c = 0
    for _start, end, tok in spans:
        gap = end
        while gap < len(text) and gap < end + 3 and text[gap] == " ":
            gap += 1
        if gap >= len(text) or text[gap] != "(" or not _content_word(tok):
            continue
        while c < len(closes) and closes[c] <= gap:
            c += 1
        if c >= len(closes):
            continue  # an unclosed parenthesis glosses nothing
        inner = text[gap + 1:closes[c]]
        if _sense_gloss(inner):
            heads.setdefault(lexis.stem(tok), f"{tok} ({_cut(inner, 80)})")
    return heads


def _bare_definition(label: Optional[str], head: str) -> bool:
    """A label that is a bare generic definition of the noun ``head`` (a stem): the noun with no determiner or with a
    generic one ("a", "an", "every", "all", "any", "each"), then a definition verb ("a theory is an unproven guess",
    "theories are guesses"), and no sense qualifier, no "sense" and no parenthetical. "The X is ..." speaks of one X,
    so it defines nothing."""
    text = label or ""
    toks = _tokens(text)
    i = 1 if toks and toks[0] in cues.DEFINITION_DETERMINERS else 0
    if not (i + 1 < len(toks) and lexis.stem(toks[i]) == head and toks[i + 1] in cues.DEFINITION_VERBS):
        return False
    return not (any(t in cues.SENSE_QUALIFIERS for t in toks) or "sense" in toks or "(" in text)


def _closed_literals(node: Any) -> Optional[list]:
    """The literal values of an expression that mentions no symbol (a closed constant term), else None."""
    if _vars(node):
        return None
    return list(_literal_values(node))


def _computation(node: dict) -> bool:
    """A step of working: an equality of a lone symbol and a closed term over two or more figures other than 0 and 1
    ("rate = 2.0 + 0.40 x 60"). An equation the symbol stands inside ("2 x dt = 82") computes nothing."""
    if node.get("op") != "eq":
        return False
    for side, other in ((node.get("left") or {}), (node.get("right") or {})), ((node.get("right") or {}), (node.get("left") or {})):
        if _symbol_side(side) is None:
            continue
        values = _closed_literals(other)
        if values is not None and _has_op(other, _ARITH) and sum(1 for v in values if v not in (0, 1)) >= 2:
            return True
    return False


def _root(token: str) -> str:
    """The shared concept root (:func:`epinoic_logic.lexis.root`)."""
    return lexis.root(token)


def _concept_token(token: str) -> bool:
    return (token.isalpha() or token[:1].isdecimal()) and token not in lexis.FUNCTION_WORDS and token not in lexis.FRAME_WORDS \
        and token not in cues.NEGATING_WORDS and not (token in lexis.NEGATION_WORDS or token.endswith("n't") or token == "non")


def _prefix_negated(token: str, other_roots: set[str]) -> Optional[str]:
    """The root of ``token`` without a negating prefix when the prefix negates it (:data:`epinoic_logic.lexis.NEGATING_PREFIXES`):
    the rest is a word of the other text ("unstable" against "stability"), or, for "un" and "non", the rest has at least
    four letters and the word is not one of :data:`~.argument_cues.NOT_PREFIXED`. None otherwise."""
    for prefix in lexis.NEGATING_PREFIXES:
        if not token.startswith(prefix) or len(token) - len(prefix) < 4:
            continue
        rest = _root(token[len(prefix):])
        if rest in other_roots:
            return rest
        if prefix in ("un", "non") and not token.startswith(cues.NOT_PREFIXED):
            return rest
        return None
    return None


def _definition_roots() -> tuple[tuple[str, tuple[frozenset[str], ...]], ...]:
    return tuple((_root(head), tuple(frozenset(_root(w) for w in words) for words in defs)) for head, defs in cues.DEFINITIONS.items())


def _synonym_roots() -> dict[str, str]:
    out: dict[str, str] = {}
    for group in cues.SYNONYM_GROUPS:
        first = _root(group[0])
        for word in group:
            out.setdefault(_root(word), first)
    return out


_DEFINITION_ROOTS = _definition_roots()
_SYNONYM_ROOTS = _synonym_roots()
#: :data:`~.argument_cues.COMPLEMENTARY_PAIRS` read as concept roots, so an inflected form of a pair is the pair.
_COMPLEMENTARY_ROOTS = frozenset(frozenset(_root(w) for w in pair) for pair in cues.COMPLEMENTARY_PAIRS if len({_root(w) for w in pair}) == 2)


def _concept(text: str, other: str) -> tuple[frozenset[str], bool, bool]:
    """``(the concept roots of text, whether it is negated, whether a closed definition was read)`` for the paraphrase
    reading of ``text`` against ``other`` (:func:`_restates`). Negation is counted from negation words, the closed
    negating words ("lacked", "without") and negating prefixes (lexis's own, and :func:`_prefix_negated`); a closed
    definition replaces its words by its head ("achieved what it set out to achieve" reads as "success"), and a synonym
    is read as its group's first member. Linear in the two texts."""
    toks = _tokens(text)
    other_roots = {_root(t) for t in _tokens(other) if _concept_token(t)}
    # a negating prefix also negates a word whose rest is a synonym of the other text's word ("ineffective" against "did not
    # work": "work" is read as "effective"; repair round 4, ADV4-08 c)
    other_roots |= {_SYNONYM_ROOTS[r] for r in tuple(other_roots) if r in _SYNONYM_ROOTS}
    negations = 0
    roots: set[str] = set()
    for t in toks:
        if t in cues.NEGATING_WORDS or t in lexis.NEGATION_WORDS or t.endswith("n't") or t == "non":
            negations += 1
            continue
        if not _concept_token(t):
            continue
        if lexis.negation_markers((t,)):
            negations += 1  # a negating prefix the light stemmer drops ("unreliable" is "rely")
            roots.add(_root(t))
            continue
        r = _root(t)
        if r not in other_roots:
            bare = _prefix_negated(t, other_roots)
            if bare is not None:
                negations += 1
                r = bare
        roots.add(r)
    used = False
    for head, definitions in _DEFINITION_ROOTS:
        for words in definitions:
            if words <= roots:
                roots = (roots - words) | {head}
                used = True
                break
    return frozenset(_SYNONYM_ROOTS.get(r, r) for r in roots), negations % 2 == 1, used


def _qualifier_roots(text: str, shared: frozenset[str]) -> frozenset[str]:
    """The roots of ``text`` that only qualify what both glosses name (repair round 2, MISS-CIRC-PARAPHRASE): a name (a word
    written with a capital inside the gloss: "Weimar"), a number or year ("2024"), and a word right before a shared word
    that modifies it ("marketing" in "the 2024 marketing campaign"). A restatement may drop them by anaphora ("the
    Republic", "the campaign") without saying anything new."""
    out: set[str] = set()
    spans = lexis.token_spans(text or "")
    for k, (a, _b, tok) in enumerate(spans):
        if not _concept_token(tok):
            continue
        r = _root(tok)
        if r in shared:
            continue
        nxt = spans[k + 1][2] if k + 1 < len(spans) else ""
        raw = text[a:a + 1]
        if tok[:1].isdecimal() or (raw.isupper() and k > 0) or (nxt and _concept_token(nxt) and _SYNONYM_ROOTS.get(_root(nxt), _root(nxt)) in shared):
            out.add(_SYNONYM_ROOTS.get(r, r))
    return frozenset(out)


#: Quantifier words whose change between two glosses changes what is claimed of how many (:func:`_quantity_words`).
_QUANTIFIER_WORDS = frozenset("all every each most many some few several none half majority minority both either neither".split())


#: The stems of the words a link's label holds when it records only the connective ("so", "therefore", "link: so", "rule"),
#: no rule: set aside when :meth:`_Diagnosis.unmarked_knowledge` asks whether a label writes a rule.
_LINK_LABEL_STEMS: frozenset[str] = frozenset(lexis.content_stems("so therefore thus hence consequently because since link rule step follows"))


def _quantity_words(text: str) -> frozenset[str]:
    """The words of a gloss that say how many: numerals that are no year, number words and quantifiers."""
    return frozenset(t for t in _tokens(text) if (_is_number(t) and not _is_year(t)) or t in cues.NUMBER_WORDS or t in _QUANTIFIER_WORDS)


def _restates(a_text: str, a_negated: bool, c_text: str, c_negated: bool) -> bool:
    """Whether the fact gloss ``a_text`` only restates the point gloss ``c_text`` (ARG-CIRC-003): the same content stems
    with the same polarity, or the same concepts read through the closed paraphrase tables (:func:`_concept`) with the
    same polarity, at least two of them unless a closed definition was read. The concepts may differ only by qualifiers one
    gloss names and the other drops by anaphora (:func:`_qualifier_roots`: "the Republic" for "the Weimar Republic", "the
    campaign" for "the 2024 marketing campaign"), while at least two concepts (or a closed definition) are shared.
    ``*_negated``: the IR negates the atom."""
    if _quantity_words(a_text) != _quantity_words(c_text):
        # a change of quantity ('three of the four shoppers asked' against 'most of the shoppers asked') is an inference about
        # the cases, not a restatement of the point (repair round 2: a valid step from a count to 'most' read as a circle)
        return False
    a_stems, c_stems = set(lexis.content_stems(a_text)), set(lexis.content_stems(c_text))
    if len(c_stems) >= 2 and a_stems == c_stems and (lexis.negated(a_text) != a_negated) == (lexis.negated(c_text) != c_negated):
        return True
    a_roots, a_neg, a_def = _concept(a_text, c_text)
    c_roots, c_neg, c_def = _concept(c_text, a_text)
    if not c_roots or not a_roots or (a_neg != a_negated) != (c_neg != c_negated):
        return False
    if a_roots != c_roots:
        shared = a_roots & c_roots
        if len(shared) < 2 and not (shared and (a_def or c_def)):
            return False
        if not (a_roots - shared <= _qualifier_roots(a_text, shared) and c_roots - shared <= _qualifier_roots(c_text, shared)):
            return False
        return True
    return len(c_roots) >= 2 or a_def or c_def


def _complementary_meanings(a: str, b: str) -> bool:
    """Two option glosses that exclude each other and cover every case: the same tokens but for one pair of
    :data:`~.argument_cues.COMPLEMENTARY_PAIRS` (a pair of :data:`~.argument_cues.COMPLEMENTARY_CONTEXT` only where a
    gloss holds one of its context words: "the bit b is 0" / "the bit b is 1"), or but for one negation word ("n is
    even" / "n is not even")."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb or ta == tb:
        return False
    if abs(len(ta) - len(tb)) == 1:
        longer, shorter = (ta, tb) if len(ta) > len(tb) else (tb, ta)
        for i, t in enumerate(longer):
            if t in lexis.NEGATION_WORDS and longer[:i] + longer[i + 1:] == shorter:
                return True
        return False
    if len(ta) != len(tb):
        return False
    diffs = [(x, y) for x, y in zip(ta, tb) if x != y]
    if len(diffs) != 1:
        return False
    pair = frozenset(diffs[0])
    context = cues.COMPLEMENTARY_CONTEXT.get(pair)
    if context is not None:
        return bool(set(ta) & context)
    # an inflected form of a listed pair is the pair ('passed' / 'failed', 'converges' / 'diverges': repair round 2, ADV2-04)
    return pair in cues.COMPLEMENTARY_PAIRS or frozenset(_root(x) for x in diffs[0]) in _COMPLEMENTARY_ROOTS


def _root_seq(words: Sequence[str]) -> tuple[str, ...]:
    return tuple(_root(w) for w in words)


_PARTITION_ROOTS: tuple[tuple[frozenset[tuple[str, ...]], ...], ...] = tuple(
    tuple(frozenset(_root_seq(lexis.tokens(phrase)) for phrase in slot) for slot in partition) for partition in cues.EXHAUSTIVE_PARTITIONS)
_ORDER_PHRASES: tuple[tuple[tuple[str, ...], str], ...] = tuple((tuple(lexis.tokens(phrase)), op) for phrase, op in cues.ORDER_WORDS)
#: Sets of order operators that cover every case without overlap: an either/or of them over one quantity and one value.
_ORDER_PARTITIONS = (frozenset({"gt", "le"}), frozenset({"lt", "ge"}), frozenset({"eq", "ne"}), frozenset({"lt", "eq", "gt"}))


def _distinct_parts(texts: Sequence[str], *, keep_end: bool = False) -> Optional[list[tuple[str, ...]]]:
    """The tokens by which each option gloss differs from the others: what is left of each after the tokens they all share at
    the start and (unless ``keep_end``) at the end. None when an option has nothing of its own."""
    toks = [list(_tokens(t)) for t in texts]
    if len(toks) < 2 or any(not t for t in toks):
        return None
    pre = 0
    while all(pre < len(t) for t in toks) and len({t[pre] for t in toks}) == 1:
        pre += 1
    suf = 0
    while not keep_end and all(suf < len(t) - pre for t in toks) and len({t[len(t) - 1 - suf] for t in toks}) == 1:
        suf += 1
    parts = [tuple(t[pre:len(t) - suf]) for t in toks]
    if any(not p for p in parts):
        return None
    return parts


def _order_of(part: Sequence[str]) -> Optional[tuple[str, str]]:
    """``(operator, value)`` for an option written as a comparison in words with one number ("greater than 3", "at most 3")."""
    words = [w for w in part if w not in ("is", "are", "was", "were", "be", "it", "or", "than") or w == "than"]
    for phrase, op in _ORDER_PHRASES:
        n = len(phrase)
        for i in range(len(words) - n + 1):
            if tuple(words[i:i + n]) == phrase:
                rest = [w for w in words[i + n:] if w not in ("to",)]
                if len(rest) == 1 and _is_number(rest[0]) and not words[:i]:
                    return op, rest[0]
                return None
    return None


def _exhaustive_options(texts: Sequence[str]) -> bool:
    """Whether the option glosses of an either/or exhaust what they speak of (repair round 3, ADV3-04): they are the same words
    but for one part each, and the parts take every slot of one closed partition once (:data:`~.argument_cues.EXHAUSTIVE_PARTITIONS`:
    "positive, negative or zero", "moving or at rest", "exothermic or endothermic"), or they compare one quantity with one
    value by operators that cover every case without overlap ("greater than 3" or "at most 3"; "less than", "equal to" or
    "greater than"). Read from the closed tables only: an either/or outside them stays a candidate false dilemma."""
    parts = _distinct_parts(texts)
    if parts is None:
        return False
    keys = [_root_seq(p) for p in parts]
    for partition in _PARTITION_ROOTS:
        if len(partition) != len(keys):
            continue
        slots = [next((k for k, slot in enumerate(partition) if key in slot), None) for key in keys]
        if None not in slots and len(set(slots)) == len(partition):
            return True
    tails = _distinct_parts(texts, keep_end=True) or []
    orders = [_order_of(p) for p in tails]
    if orders and all(o is not None for o in orders) and len({o[1] for o in orders}) == 1:  # type: ignore[index]
        ops = [o[0] for o in orders]  # type: ignore[index]
        if len(set(ops)) == len(ops) and frozenset(ops) in _ORDER_PARTITIONS:
            return True
    return False


def _selecting_cue(text: str, table: lexis.CueTable) -> Optional[str]:
    """The first cue of ``table`` in ``text`` that no negation precedes within three tokens ("not necessarily the
    strongest" selects no sense), else None."""
    toks = _tokens(text)
    for i, cue in lexis.find_cues(toks, table):
        if any(lexis.negation_markers((t,)) for t in toks[max(0, i - 3):i]):
            continue
        return " ".join(cue)
    return None


# ----------------------------------------------------------------------------------------------- derived runs

@dataclass
class _Run:
    """The answer of one derived run: its status (None when undecided or not run), the digest of its derived problem, the
    counterexample values when asked for, and the premises (by id) of its unsat core when ENTAILED."""
    status: Optional[VerificationStatus] = None
    digest: Optional[str] = None
    model: dict = field(default_factory=dict)
    core: list[str] = field(default_factory=list)


@dataclass
class _Runs:
    """The derived runs of one diagnosis, within their bounds (module docstring). Every derived problem is a deterministic
    function of the bound problem, the rule version and the rule's tag; it passes the validator and its digest is
    recorded. Runs are decided on the bound problem's compiled terms, in one context."""
    base: dict
    problem: Problem
    config: Any
    limits: Any
    per_run: int
    total: int
    compiled: Optional[Compiled] = None
    count: int = 0
    started: float = field(default_factory=time.perf_counter)
    incomplete: list[str] = field(default_factory=list)
    _premises: dict = field(default_factory=dict)
    _literals: int = 0
    #: Decided runs by their content (premises, conclusion, added steps): an identical derived problem is decided once
    #: (re-run review ADV-08; R0's last minimisation trial is often the established set itself, already decided as d0).
    _decided: dict = field(default_factory=dict)
    #: Each bound premise's tracking literal and ``Implies(literal, term)``, built once and asserted in every run's solver.
    _tracked: dict = field(default_factory=dict)
    _conclusion_key: Optional[str] = None
    #: The one incremental solver the runs that need no model share: every implication is asserted in it once and each
    #: run decides under its own assumptions (the tracking literals of its premises), so a literal not assumed leaves its
    #: premise out. A run that reports a model (R0's d0, whose counterexample values a message shows) has its own solver.
    _shared: Any = None
    _in_shared: set = field(default_factory=set)
    _negations: dict = field(default_factory=dict)
    #: The bound problem's premises are consistent: the engine's own consistency check found them satisfiable (its status
    #: is ENTAILED or COUNTEREXAMPLE). Then every run made only of bound premises is consistent too (a subset of a
    #: satisfiable set is satisfiable), so its consistency check is not repeated; a run that adds a step is checked as
    #: before (repair round 5, ADV5-13: half the derived solver calls were these repeated checks).
    consistent: bool = False

    @classmethod
    def of(cls, problem: Problem, config: Any, limits: Any, compiled: Any = None) -> "_Runs":
        per_run, total = run_budget_ms(config)
        base = problem.model_dump(mode="json", exclude_none=True)
        reuse = compiled if isinstance(compiled, Compiled) and compiled.problem is problem else None
        conclusion = (base.get("conclusion") or {}).get("expr")
        return cls(base=base, problem=problem, config=config, limits=limits, per_run=per_run, total=total, compiled=reuse,
                   _premises={str(p.get("id")): p for p in base.get("premises") or []},
                   _conclusion_key=canonical_json(conclusion) if conclusion is not None else None)

    def _missing(self, reason: str) -> None:
        if reason not in self.incomplete:
            self.incomplete.append(reason)

    @staticmethod
    def _fresh_id(stem: str, taken: set[str]) -> str:
        aid = stem
        while aid in taken:
            aid += "_"
        taken.add(aid)
        return aid

    def _context(self) -> Optional[Compiled]:
        if self.compiled is None:
            try:
                self.compiled = compile_problem(self.problem)
            except CompileError:
                self._missing("derived_invalid")
                return None
        return self.compiled

    def _new_solver(self, ctx: z3.Context) -> z3.Solver:
        solver = z3.Solver(ctx=ctx)
        solver.set("timeout", max(1, int(self.per_run)))
        if getattr(self.config, "rlimit", None) is not None:
            solver.set("rlimit", int(self.config.rlimit))
        solver.set("random_seed", int(getattr(self.config, "random_seed", 0) or 0))
        return solver

    def _solver(self, ctx: z3.Context) -> z3.Solver:
        """The shared incremental solver (:attr:`_shared`), made on first use with the per-run bounds."""
        if self._shared is None:
            self._shared = self._new_solver(ctx)
        return self._shared

    def _literal(self, ctx: z3.Context) -> z3.BoolRef:
        """A fresh tracking literal (IR identifiers never start with an underscore, so none can clash)."""
        self._literals += 1
        return z3.Bool(f"__argdiag_{self._literals}", ctx)

    def entail(self, premise_ids: Sequence[str], conclusion: dict, tag: str, extra: Sequence[dict] = (), *, model: bool = False) -> _Run:
        """Decide the bound problem's premises ``premise_ids`` (copied) plus ``extra`` (new steps, validated IR data)
        against ``conclusion`` (an expression), consistency first. The run's status is None when it was undecided, not
        valid or out of budget (recorded in ``incomplete``)."""
        kept_ids = [pid for pid in dict.fromkeys(premise_ids) if pid in self._premises]
        concl_key = canonical_json(conclusion)
        key = (tuple(sorted(kept_ids)), concl_key, canonical_json(list(extra)))
        hit = self._decided.get(key)
        if hit is not None and (not model or hit.status is not _S.COUNTEREXAMPLE or hit.model):
            return hit  # the same derived problem, already decided: no run is spent on it
        if self.count >= MAX_DERIVED_RUNS:
            self._missing("derived_runs_exhausted")
            return _Run()
        if (time.perf_counter() - self.started) * 1000.0 >= self.total:
            self._missing("budget_exhausted")
            return _Run()
        self.count += 1
        run = self._decide(kept_ids, conclusion, concl_key, tag, extra, model)
        if run.status is not None:
            self._decided[key] = run
        return run

    def _decide(self, kept_ids: list[str], conclusion: dict, concl_key: str, tag: str, extra: Sequence[dict], model: bool) -> _Run:
        """One derived run (:meth:`entail`). A run made only of bound premises and the bound conclusion is a part of a
        problem the validator already passed, so it is not validated again; any other is."""
        kept = [self._premises[pid] for pid in kept_ids]
        taken = {str(p.get("id")) for p in self._premises.values()}
        concl_id = str((self.base.get("conclusion") or {}).get("id") or "argdiag_point")
        taken.add(concl_id)
        data = {k: v for k, v in self.base.items() if k not in ("premises", "conclusion", "notes")}
        data["problem_id"] = f"{self.base.get('problem_id', 'p')}#{ARG_RULES_VERSION}:{tag}"[-128:]
        data["query"] = "entailment"
        added = [{"id": self._fresh_id(f"argdiag_{tag}_{i}".replace(":", "_"), taken), "expr": e} for i, e in enumerate(extra)]
        data["premises"] = [dict(p) for p in kept] + added
        data["conclusion"] = {"id": concl_id, "expr": conclusion}
        part_of_bound = not added and concl_key == self._conclusion_key
        try:
            derived = Problem.model_validate(data)
        except (ValidationError, ValueError, RecursionError):
            self._missing("derived_invalid")
            return _Run()
        if not part_of_bound and not validate_problem(derived, self.limits).ok:
            self._missing("derived_invalid")
            return _Run()
        digest = problem_digest(derived)
        compiled = self._context()
        if compiled is None:
            return _Run(digest=digest)
        ctx = compiled.ctx
        try:
            terms: list[tuple[str, z3.BoolRef]] = [(str(p["id"]), compiled.premises[str(p["id"])]) for p in kept]
            for k, assertion in enumerate(derived.premises[len(kept):]):
                terms.append((assertion.id, compile_expr(assertion.expr, compiled.symbols, ctx, f"premises[{len(kept) + k}].expr")))
            goal = (compiled.conclusion if part_of_bound and compiled.conclusion is not None
                    else compile_expr(derived.conclusion.expr, compiled.symbols, ctx, "conclusion.expr"))  # type: ignore[union-attr]
        except (CompileError, KeyError, z3.Z3Exception):
            self._missing("derived_invalid")
            return _Run(digest=digest)
        if not all(z3.is_bool(t) for _p, t in terms) or not z3.is_bool(goal):
            self._missing("derived_invalid")
            return _Run(digest=digest)
        shared = not model
        solver = self._solver(ctx) if shared else self._new_solver(ctx)
        tracks: list[tuple[str, z3.BoolRef]] = []
        for k, (pid, term) in enumerate(terms):
            if k < len(kept):  # a bound premise: its literal and implication are built once for every run
                if pid not in self._tracked:
                    lit = self._literal(ctx)
                    self._tracked[pid] = (lit, z3.Implies(lit, term, ctx))
                lit, implication = self._tracked[pid]
                if not shared or pid not in self._in_shared:
                    solver.add(implication)
                    if shared:
                        self._in_shared.add(pid)
            else:
                lit = self._literal(ctx)
                solver.add(z3.Implies(lit, term, ctx))
            tracks.append((pid, lit))
        if added or not self.consistent:
            first = solver.check(*[lit for _p, lit in tracks])
            if first == z3.unsat:
                return _Run(status=_S.INCONSISTENT_PREMISES, digest=digest)
            if first != z3.sat:
                self._missing("derived_undecided")
                return _Run(digest=digest)
        if shared and part_of_bound and concl_key in self._negations:
            neg = self._negations[concl_key]
        else:
            neg = self._literal(ctx)
            solver.add(z3.Implies(neg, z3.Not(goal, ctx), ctx))
            if shared and part_of_bound:
                self._negations[concl_key] = neg
        second = solver.check(*[lit for _p, lit in tracks], neg)
        if second == z3.unsat:
            core = list(solver.unsat_core())
            return _Run(status=_S.ENTAILED, digest=digest, core=[pid for pid, lit in tracks if any(lit.eq(c) for c in core)])
        if second == z3.sat:
            values = extract_model(compiled, solver.model(), True) if model else {}
            return _Run(status=_S.COUNTEREXAMPLE, digest=digest, model=values)
        self._missing("derived_undecided")
        return _Run(digest=digest)


# ----------------------------------------------------------------------------------------------- the diagnosis

@dataclass
class _R0:
    """What R0 found: the established premises, the writer's premises the proof needs (``links``, ``facts``) and the
    counterexample the established premises alone leave."""
    established: list[str]
    links: list[str]
    facts: list[str]
    partly: bool
    model: dict
    digests: list[str]


class _Diagnosis:
    def __init__(self, problem: Problem, proc: ProcedureOutcome, compiled: Any, config: Any, limits: Any, codes: set[str]) -> None:
        self.problem = problem
        self.proc = proc
        self.codes = codes
        self.runs = _Runs.of(problem, config, limits, compiled)
        self.runs.consistent = proc.status in (_S.ENTAILED, _S.COUNTEREXAMPLE)  # consistency before entailment: checked by the engine
        self.meanings = {s.name: (s.meaning or "") for s in problem.symbols}
        self.sorts = {s.name: s.sort for s in problem.symbols}
        self.premises = list(problem.premises)
        self.ids = [p.id for p in self.premises]
        self.dumps = {p.id: p.expr.model_dump(mode="json", exclude_none=True) for p in self.premises}
        self.by_id = {p.id: p for p in self.premises}
        self.conclusion = problem.conclusion.expr.model_dump(mode="json", exclude_none=True) if problem.conclusion is not None else None
        self.concl_id = problem.conclusion.id if problem.conclusion is not None else None
        self.established = [p.id for p in self.premises if has_authority(p.grounding)]
        self.out: list[NamedDiagnostic] = []

    # -------------------------------------------------------------------------------- helpers

    def kind(self, pid: str) -> Optional[str]:
        g = self.by_id[pid].grounding
        return g.kind if g is not None else None

    def label(self, pid: str) -> str:
        return (self.by_id[pid].label or "").strip()

    def g(self, node: dict, limit: int = _PART_CHARS) -> str:
        return _cut(gloss(node, self.meanings), limit)

    def named(self, pid: str) -> str:
        """``l_so ('the label')``: a premise for a message."""
        label = self.label(pid)
        return f"{pid} ({_cut(label, 120)!r})" if label else pid

    def span_of(self, pid: str) -> list[EvidenceSpan]:
        label = self.label(pid)
        return [EvidenceSpan(source_kind="premise_label", source_id=pid[:200], text=_raw(label))] if label else []

    def meaning_span(self, name: str) -> list[EvidenceSpan]:
        meaning = self.meanings.get(name, "").strip()
        return [EvidenceSpan(source_kind="symbol_meaning", source_id=name[:200], text=_raw(meaning))] if meaning else []

    def link_of(self, premise_ids: Sequence[str], node: dict) -> MissingLink:
        """The missing link a link-shaped expression states (``if A then B``; ``either a or b, and nothing else``)."""
        op = node.get("op")
        if op == "implies":
            a, b = self.g(node["left"]), self.g(node["right"])
            text = f"if {a} then {b}"
        elif op == "iff":
            a, b = self.g(node["left"]), self.g(node["right"])
            text = f"{a} exactly when {b}"
        elif op == "or":
            opts = [self.g(x, 140) for x in node.get("args") or []]
            a, b = opts[0] if opts else "", " or ".join(opts[1:])
            text = f"either {' or '.join(opts)}, and nothing else"
        else:
            a, b = self.g(node), ""
            text = a
        return MissingLink(premise_ids=list(premise_ids)[:16], antecedent=_cut(a), consequent=_cut(b), text=_cut(text, 600), expr=node)

    def values(self, model: Optional[dict], names: Iterable[str]) -> str:
        model = model or {}
        shown = [f"{n}={model[n]}" for n in sorted(set(names)) if n in model][:_SHOW_VALUES]
        return ", ".join(shown)

    def emit(self, code: str, message: str, *, assertion_ids: Sequence[str] = (), missing_link: Optional[MissingLink] = None,
             evidence: Sequence[EvidenceSpan] = (), derivation: str = "ir_structure", digests: Sequence[Optional[str]] = (), severity: Optional[str] = None) -> None:
        ids = list(dict.fromkeys(a for a in assertion_ids if a))[:128]
        self.out.append(named_diagnostic(code, severity=severity, claim_ids=[self.problem.claim_id], assertion_ids=ids, missing_link=missing_link,
                                         evidence=list(evidence)[:8], derivation=derivation, derived_problem_digests=list(dict.fromkeys(d for d in digests if d))[:24],
                                         message=message))

    # -------------------------------------------------------------------------------- the engine's own status

    def status_rules(self) -> None:
        status = self.proc.status
        if status is _S.INCONSISTENT_PREMISES:
            core = [pid for pid in self.proc.core if pid in self.by_id] or list(self.ids)
            shown = "; ".join(self.named(pid) for pid in core[:6]) + (f"; and {len(core) - 6} more" if len(core) > 6 else "")
            self.emit("ARG-CONTRA-001", f"the encoded premises contradict each other: {shown} cannot all hold together, so nothing follows from them "
                                        "(the engine's unsat core over the premises)",
                      assertion_ids=core, evidence=[s for pid in core[:8] for s in self.span_of(pid)], derivation="engine_status")
        if _E108 in self.codes:
            # Only a proof that holds whatever the premises say is a vacuous argument. A counterexample (or another query)
            # over no premise at all says that nothing the claim rests on was encoded: a record, never an accusation.
            if status is _S.ENTAILED and self.problem.premises:
                self.emit("ARG-VAC-001", "vacuous: the point holds whatever the premises say, so no reason given is used (E108)",
                          assertion_ids=[self.concl_id] if self.concl_id else [], derivation="engine_status")
            elif status is _S.ENTAILED:
                # A proof over no premise at all shows only that the point is a logical truth: an identity the task asks to
                # show ("Show that A·B + A·NOT B = A") holds by its form, and no reason of the claim is in the encoding to go
                # unused. A record, never an accusation (repair round 4, E2E-CS-IDENTITY-PROOF-NAMED-VACUOUS).
                self.emit("ARG-VAC-001", "no premise is encoded and the point holds whatever the premises say (E108): it is a logical truth "
                                         "(an identity or a tautology), and no reason of the claim is in the encoding, so nothing shows an "
                                         "argument whose reasons go unused", severity="info",
                          assertion_ids=[self.concl_id] if self.concl_id else [], derivation="engine_status")
            else:
                what = "the counterexample only says that the point is no tautology" if status is _S.COUNTEREXAMPLE else \
                    f"the {self.problem.query} query's answer asserts nothing"
                self.emit("ARG-VAC-001", f"no premise is encoded, so {what} (E108): the claim's reasons are not in the encoding, which shows "
                                         "nothing about the claim", severity="info",
                          assertion_ids=[self.concl_id] if self.concl_id else [], derivation="engine_status")
        if _E112 in self.codes and self.conclusion is not None:
            restating = self._restating()
            shown = "; ".join(self.named(pid) for pid in restating[:6]) or "a premise"
            if restating and self._bare_restatement(restating):
                self.emit("ARG-CIRC-001", f"the premise(s) {shown} restate the point (E112); each is a fact stated from subject knowledge and none "
                                          "is offered as a reason for it, so the restatement is the encoding's, not a circle shown in the argument: "
                                          "no verdict either way", severity="info",
                          assertion_ids=restating + ([self.concl_id] if self.concl_id else []), evidence=[s for pid in restating[:8] for s in self.span_of(pid)],
                          derivation="engine_status")
            else:
                self.emit("ARG-CIRC-001", f"circular: the premise(s) {shown} restate the point, and no check in this process established them "
                                          "(whatever their label), so the point is assumed, not derived (E112)",
                          assertion_ids=restating + ([self.concl_id] if self.concl_id else []), evidence=[s for pid in restating[:8] for s in self.span_of(pid)],
                          derivation="engine_status")

    def _bare_restatement(self, restating: Sequence[str]) -> bool:
        """Whether the restating premises only transcribe a bare factual statement: every one is a fact stated from subject
        knowledge (``general_knowledge``), and neither their labels nor the conclusion's offer a reason (no reason
        connective). A restatement by the writer's own step, an assumption, no grounding or a source or task label no
        check established is the circle the code names."""
        if not all(self.kind(pid) == cues.KNOWLEDGE_KIND for pid in restating):
            return False
        labels = [self.label(pid) for pid in restating] + [(self.problem.conclusion.label or "") if self.problem.conclusion is not None else ""]
        return not any(_offers_reason(text) for text in labels)

    def _restating(self) -> list[str]:
        """The core's premises that restate the point (it, or each of its conjuncts, is one of them or one of their
        conjuncts): the syntactic test of E112."""
        core = set(self.proc.core) or set(self.by_id)
        owner: dict[str, str] = {}
        for p in self.premises:
            if p.id not in core:
                continue
            node = self.dumps[p.id]
            owner.setdefault(_canon(node), p.id)
            for c in _conjuncts(node):
                owner.setdefault(_canon(c), p.id)
        needed = [_canon(c) for c in _conjuncts(self.conclusion)] if self.conclusion is not None else []
        return list(dict.fromkeys(owner[n] for n in needed if n in owner))

    # -------------------------------------------------------------------------------- R0 and the ENTAILED rules

    def r0(self) -> Optional[_R0]:
        """Decide the point again from the established premises; minimise the writer's premises the proof needs."""
        if self.conclusion is None:
            return None
        core = [pid for pid in self.proc.core if pid in self.by_id] or list(self.ids)
        core_set = set(core)
        established = set(self.established)
        writers = [pid for pid in self.ids if pid in core_set and pid not in established]
        if not writers:
            return None
        d0 = self.runs.entail(self.established, self.conclusion, "d0", model=True)
        if d0.status is not _S.COUNTEREXAMPLE:
            return None  # ENTAILED: the core was not minimal; undecided: recorded as incomplete and nothing fires
        digests = [d0.digest] if d0.digest else []
        kept = list(writers)
        for i, w in enumerate(writers[:MAX_MINIMISED]):
            trial = self.runs.entail([*self.established, *(x for x in kept if x != w)], self.conclusion, f"min{i}")
            if trial.digest:
                digests.append(trial.digest)
            if trial.status is None:
                return None  # an undecided minimisation fires nothing (recorded as incomplete)
            if trial.status is _S.ENTAILED:
                kept.remove(w)
        links = [w for w in kept if _is_link(self.dumps[w])]
        facts = [w for w in kept if w not in links]
        return _R0(established=list(self.established), links=links, facts=facts, partly=len(writers) > MAX_MINIMISED, model=d0.model, digests=digests)

    def entailed_rules(self) -> None:
        found = self.r0()
        if found is None:
            return
        self.circ_equivalent(found)
        self.circ_paraphrase(found)
        self.converse_links(found)
        self.false_dilemma(found)
        self.hasty_links(found)
        self.causal_links(found)
        self.sense_definition(found)
        if not any(d.code == "ARG-EQ-003" for d in self.out):
            self.symbol_senses(found)
        self.link_records(found)

    def writer_step(self, pid: str) -> bool:
        return self.kind(pid) in cues.WRITER_STEP_KINDS

    def parts(self, pid: str) -> list[dict]:
        """The link-shaped parts of a premise (:func:`_link_parts`): the steps a pattern rule reads."""
        return _link_parts(self.dumps[pid])

    def unmarked_knowledge(self, pid: str) -> bool:
        """A premise labelled as subject knowledge (``general_knowledge``) that the translation did not mark as a rule the
        writer states (no grounding note "rule", translate_v3 rule 2): a step whose label says knowledge while nothing
        marks it as a stated rule (re-run review ADV-11 a, b). The note is the translation's word, so a premise whose label
        records no rule (a bare connective: "so", "therefore", "link") is unmarked too: a rule the writer states is written
        somewhere, and a label of fewer than two content words writes none (repair round 3, ADV3-13: a leap noted "rule"
        lost its missing link)."""
        g = self.by_id[pid].grounding
        if g is None or g.kind != cues.KNOWLEDGE_KIND:
            return False
        if not (g.note or "").strip().casefold().startswith("rule"):
            return True
        return len(set(lexis.content_stems(self.label(pid) or "")) - _LINK_LABEL_STEMS) < 2

    def unsourced_writer(self, pid: str) -> bool:
        """The writer's own premise that cites no source: a writer's kind (or no grounding) and no source reference."""
        g = self.by_id[pid].grounding
        return g is None or (g.kind in cues.WRITER_STEP_KINDS and not g.source_refs)

    def figure_relation(self, pid: str) -> bool:
        """A premise whose every link-shaped part is a numeric relation between quantities (``x > y``, ``rate = 2.0 + 0.40
        x t``; the translation's ``figure_relation`` role), with no implication, biconditional or either/or: it states how
        quantities relate, not a step from a reason to the point, so it has no antecedent and consequent to give as a missing
        link. R0 still needs it, and a rule the writer states from subject knowledge stays an unchecked rule (ARG-LINK-002);
        otherwise it is listed with the facts no check established (ARG-FACT-001), never as a leap (repair round 5,
        INV-LINK-1: 'x > y' and 'y > z' for 'x > z' were each named the writer's own link with an empty consequent)."""
        parts = self.parts(pid)
        if not parts or any(node.get("op") in _LINK_OPS for node in parts):
            return False
        return not (self.kind(pid) == cues.KNOWLEDGE_KIND and not self.unmarked_knowledge(pid))

    def link_records(self, r: _R0) -> None:
        verified = ", ".join(r.established[:6]) or "none"
        relations = [w for w in r.links if self.figure_relation(w)]
        links = [w for w in r.links if w not in relations]
        concl_vars = _vars(self.conclusion)
        names = concl_vars | {n for w in links for n in _vars(self.dumps[w])}
        ce = self.values(r.model, names)
        partly = "; the writer's premises were partly minimised (the first 16 were tested)" if r.partly else ""
        alone = f" (with them alone the counterexample sets {ce})" if ce else ""
        for w in links[:MAX_LINK_DIAGNOSTICS]:
            k = self.kind(w)
            parts = self.parts(w)
            if any(node.get("op") == "implies" and _causal(" ".join(self.meanings.get(n, "") for n in sorted(_vars(node["right"]))))
                   and self.warranting_control(w, node) for node in parts):
                continue  # a causal link its own stated controlled comparison warrants ('randomly assigned'): no missing link (repair round 2)
            if k == cues.KNOWLEDGE_KIND and not self.unmarked_knowledge(w):
                # a rule the writer states from subject knowledge, marked as stated (translate_v3 rule 2): no missing link, but a
                # knowledge claim no check established (repair round 2, NAME-LINK-NONDISCRIMINATING)
                self.emit("ARG-LINK-002", f"the point does not follow from the premises a check verified ({verified}){alone}; it follows with the "
                                          f"rule {self.named(w)} that the writer states from subject knowledge, which no check established{partly}",
                          assertion_ids=[w], evidence=self.span_of(w), derivation="engine_recheck", digests=r.digests)
                continue
            if k in cues.WRITER_STEP_KINDS:
                whose = f"the writer's own link {w}, which no source or check states"
            elif k == "general_knowledge":
                whose = f"the link {w}, a rule stated from subject knowledge that no check established"
            else:
                whose = f"the link {w}, labelled {k}, which no check located in a source"
            hidden = "" if parts and parts[0] is self.dumps[w] else " (a step inside a conjunction)"
            self.emit("ARG-LINK-001", f"the point does not follow from the premises a check verified ({verified}){alone}; it follows only with "
                                      f"{whose}{hidden}{partly}",
                      assertion_ids=[w], missing_link=self.link_of([w], parts[0] if len(parts) == 1 else self.dumps[w]), evidence=self.span_of(w),
                      derivation="engine_recheck", digests=r.digests)
        rest = links[MAX_LINK_DIAGNOSTICS:]
        if rest:
            self.emit("ARG-LINK-001", f"the point also needs {len(rest)} more link(s) no check established: {', '.join(rest[:12])}"
                                      + (" and more" if len(rest) > 12 else "") + partly,
                      assertion_ids=rest, missing_link=self.link_of(rest, self.dumps[rest[0]]), derivation="engine_recheck", digests=r.digests)
        listed = [*r.facts, *relations]
        if listed:
            shown = "; ".join(self.named(f) for f in listed[:6]) + (f"; and {len(listed) - 6} more" if len(listed) > 6 else "")
            related = (f" ({', '.join(relations[:12])}{' and more' if len(relations) > 12 else ''} relate quantities: a figure relation states no "
                       "step from a reason to the point, so it gives no missing link)") if relations else ""
            self.emit("ARG-FACT-001", f"the proof also needs fact premise(s) that no check established: {shown}{related}; the evidence rules grade "
                                      f"them{partly}",
                      assertion_ids=listed, evidence=[s for f in listed[:8] for s in self.span_of(f)], derivation="engine_recheck", digests=r.digests)

    def circ_equivalent(self, r: _R0) -> None:
        """ARG-CIRC-002: the point is equivalent to one unestablished premise of W*, though not the same expression. Only a
        restatement is read: the two use the same symbols, and the premise uses the point's literal values and computes
        nothing (no arithmetic), or it is the writer's own premise that cites no source and is no computation of the
        point's figure (re-run review, fidelity-4 variant: "2 x dt = 82" for "dt = 41"). A computation, "rate = 2.0 + 0.40
        x 60" for "rate = 26" (a lone symbol equal to a term over two or more figures other than 0 and 1), is a step of
        working, never a circle; so is any premise that cites a source or claims an authority."""
        if _has_op(self.conclusion, _ARITH):
            return
        concl_vars = _vars(self.conclusion)
        concl_literals = _literal_values(self.conclusion)
        target = _canon(self.conclusion)
        tried = 0
        for w in r.links + r.facts:
            node = self.dumps[w]
            if _vars(node) != concl_vars or _canon(node) == target or tried >= MAX_EQUIVALENCES:
                continue
            restates = not _has_op(node, _ARITH) and _literal_values(node) == concl_literals
            if not restates and not (self.unsourced_writer(w) and not _computation(node)):
                continue
            tried += 1
            run = self.runs.entail([], _iff(node, self.conclusion), f"equiv{tried}")
            if run.status is _S.ENTAILED:
                self.emit("ARG-CIRC-002", f"circular: the point is equivalent to the premise {self.named(w)}, which no check established (a derived "
                                          "check finds 'premise exactly when point' holds under every assignment): the point is assumed in other words",
                          assertion_ids=[w, self.concl_id or ""], evidence=self.span_of(w), derivation="engine_recheck", digests=[*r.digests, run.digest])
                return

    def circ_paraphrase(self, r: _R0) -> None:
        """ARG-CIRC-003: the writer's link A -> C derives the point C from a fact atom A whose gloss only restates C's: the
        same content words, or the same concepts read through the closed paraphrase tables (:func:`_same_concept`: another
        voice or tense, another part of speech, a negating word for a negating prefix, a closed definition or synonym of an
        evaluative word), with the same polarity."""
        point = _atom(self.conclusion)
        if point is None:
            return
        established = set(self.established)
        for w in r.links:
            for node in self.parts(w):
                if node.get("op") != "implies" or not _same(node["right"], self.conclusion):
                    continue
                ante = _atom(node["left"])
                if ante is None or ante[0] == point[0]:
                    continue
                asserting = [p.id for p in self.premises if _atom(self.dumps[p.id]) == ante]
                if not asserting or any(pid in established for pid in asserting):
                    continue  # A is asserted by no premise, or a check established it (a paraphrase of a source is a transcription)
                a_text, c_text = self.meanings.get(ante[0], ""), self.meanings.get(point[0], "")
                if not _restates(a_text, ante[1], c_text, point[1]):
                    continue
                self.emit("ARG-CIRC-003", f"circular by paraphrase: the writer's link {w} derives the point ({_cut(c_text, 160)!r}) from the fact "
                                          f"{', '.join(asserting[:3])} ({_cut(a_text, 160)!r}), whose words only restate the point's: no reason is given",
                          assertion_ids=[w, *asserting[:3]], missing_link=self.link_of([w], node),
                          evidence=[*self.span_of(w), *self.meaning_span(ante[0]), *self.meaning_span(point[0])], derivation="ir_glosses", digests=r.digests)
                return

    def _rules(self) -> list[tuple[str, dict]]:
        """``(premise id, implication)`` for every implication a premise states (or holds as a conjunct) that is not the
        writer's own step."""
        return [(pid, node) for pid in self.ids if not self.writer_step(pid) for node in self.parts(pid) if node.get("op") == "implies"]

    def converse_links(self, r: _R0) -> None:
        """ARG-AC-001 b / ARG-DA-001 b: the link the proof needs is the converse (Q -> P) or the inverse (not P -> not Q) of
        a rule P -> Q the problem states as something other than the writer's own step, or of a chain of such rules (a
        derived check: the rules entail P -> Q and do not entail the link; re-run review ADV-11 d). The writer's own link
        is named at warning. A link labelled as subject knowledge (``general_knowledge``) that the translation did not mark
        as a stated rule (:meth:`unmarked_knowledge`) and that is the converse or the inverse of a single stated rule is
        named at info (ADV-11 a): its label claims knowledge, so the shape is recorded, not charged. A rule marked as
        stated ("rule") is the writer's statement of a biconditional and is never read."""
        rules = self._rules()
        tried = 0
        for w in r.links:
            writer = self.writer_step(w)
            if not writer and not self.unmarked_knowledge(w):
                continue
            severity = None if writer else "info"
            whose = f"the writer's link {self.named(w)}" if writer else f"the link {self.named(w)}, labelled general_knowledge,"
            for node in self.parts(w):
                if node.get("op") != "implies":
                    continue
                named = False
                for c, rule in rules:
                    if c == w:
                        continue
                    if _same(node["left"], rule["right"]) and _same(node["right"], rule["left"]):
                        self.emit("ARG-AC-001", f"affirming the consequent: {whose} ({self.g(node, 200)}) is the converse of the "
                                                f"stated rule {self.named(c)} ({self.g(rule, 200)}); the rule does not give it, so concluding "
                                                f"{self.g(rule['left'], 120)!r} from {self.g(rule['right'], 120)!r} affirms the consequent",
                                  assertion_ids=[w, c], missing_link=self.link_of([w], node), evidence=[*self.span_of(w), *self.span_of(c)],
                                  derivation="ir_structure", digests=r.digests, severity=severity)
                        named = True
                        break
                    if _negation_of(node["left"], rule["left"]) and _negation_of(node["right"], rule["right"]):
                        self.emit("ARG-DA-001", f"denying the antecedent: {whose} ({self.g(node, 200)}) is the inverse of the "
                                                f"stated rule {self.named(c)} ({self.g(rule, 200)}); the rule does not give it, so concluding "
                                                f"{self.g(node['right'], 120)!r} from {self.g(node['left'], 120)!r} denies the antecedent",
                                  assertion_ids=[w, c], missing_link=self.link_of([w], node), evidence=[*self.span_of(w), *self.span_of(c)],
                                  derivation="ir_structure", digests=r.digests, severity=severity)
                        named = True
                        break
                if not named:
                    named = self.packed_converse(w, node, whose, severity, r)
                if named or not writer or len(rules) < 2 or tried >= MAX_CONVERSES:
                    continue
                tried += 1
                self.converse_chain(w, node, rules, r, tried)

    def packed_converse(self, w: str, node: dict, whose: str, severity: Optional[str], r: _R0) -> bool:
        """ARG-AC-001 b / ARG-DA-001 b inside one premise (repair round 2, ADV2 probes ya04 and za03): a conjunction that holds
        a rule P -> Q, the fact the step starts from, and the step itself, the converse (Q -> P, from the fact Q) or the
        inverse (not P -> not Q, from the fact not P) of that rule: "if a plant gets light it grows, and this plant gets no
        light, and so it will not grow" as one premise. The fact must stand in the same conjunction, so a stated
        biconditional written as two implications (no fact) is not read."""
        parts = _conjuncts(self.dumps[w])
        if len(parts) < 3 or not any(_same(x, node["left"]) for x in parts if x is not node):
            return False
        for rule in self.parts(w):
            if rule is node or rule.get("op") != "implies":
                continue
            if _same(node["left"], rule["right"]) and _same(node["right"], rule["left"]):
                code, shape, what, start, end = "ARG-AC-001", "affirming the consequent", "the converse", rule["right"], rule["left"]
            elif _negation_of(node["left"], rule["left"]) and _negation_of(node["right"], rule["right"]):
                code, shape, what, start, end = "ARG-DA-001", "denying the antecedent", "the inverse", node["left"], node["right"]
            else:
                continue
            self.emit(code, f"{shape}: {whose} holds the rule ({self.g(rule, 200)}), the fact {self.g(node['left'], 120)!r} and the step "
                            f"({self.g(node, 200)}), which is {what} of that rule; the rule does not give it, so concluding {self.g(end, 120)!r} from "
                            f"{self.g(start, 120)!r} {'affirms the consequent' if code == 'ARG-AC-001' else 'denies the antecedent'} (the steps are "
                            "joined in one conjunction)",
                      assertion_ids=[w], missing_link=self.link_of([w], node), evidence=self.span_of(w), derivation="ir_structure", digests=r.digests,
                      severity=severity)
            return True
        return False

    def converse_chain(self, w: str, node: dict, rules: list[tuple[str, dict]], r: _R0, tried: int) -> None:
        """ARG-AC-001 b / ARG-DA-001 b over a chain of stated rules (ADV-11 d): the rules entail the reverse direction of the
        writer's link (``P -> Q`` for the link ``Q -> P``; ``P -> Q`` for the inverse link ``not P -> not Q``) and do not
        entail the link itself. Two derived runs, each over the rule premises only."""
        rule_ids = list(dict.fromkeys(c for c, _rule in rules if c != w))
        mentioned: set[str] = set()
        for c in rule_ids:
            mentioned |= _vars(self.dumps[c])
        if not _vars(node) <= mentioned:
            return
        left, right = node["left"], node["right"]
        inverse = left.get("op") == "not" and right.get("op") == "not"
        reverse = _implies(left["arg"], right["arg"]) if inverse else _implies(right, left)
        back = self.runs.entail(rule_ids, reverse, f"chain{tried}")
        if back.status is not _S.ENTAILED:
            return
        forth = self.runs.entail(rule_ids, node, f"chainlink{tried}")
        if forth.status is not _S.COUNTEREXAMPLE:
            return
        shown = ", ".join(rule_ids[:6])
        if inverse:
            self.emit("ARG-DA-001", f"denying the antecedent: the writer's link {self.named(w)} ({self.g(node, 200)}) is the inverse of what the "
                                    f"stated rules {shown} give together ({self.g(reverse, 200)}); they do not give the link, so concluding "
                                    f"{self.g(right, 120)!r} from {self.g(left, 120)!r} denies the antecedent",
                      assertion_ids=[w, *rule_ids[:8]], missing_link=self.link_of([w], node), evidence=self.span_of(w), derivation="engine_recheck",
                      digests=[*r.digests, back.digest, forth.digest])
            return
        self.emit("ARG-AC-001", f"affirming the consequent: the writer's link {self.named(w)} ({self.g(node, 200)}) is the converse of what the "
                                f"stated rules {shown} give together ({self.g(reverse, 200)}); they do not give the link, so concluding "
                                f"{self.g(right, 120)!r} from {self.g(left, 120)!r} affirms the consequent",
                  assertion_ids=[w, *rule_ids[:8]], missing_link=self.link_of([w], node), evidence=self.span_of(w), derivation="engine_recheck",
                  digests=[*r.digests, back.digest, forth.digest])

    def false_dilemma(self, r: _R0) -> None:
        """ARG-FD-001: the proof needs an either/or that no check established, which is no tautology and whose options are
        not complementary, as expressions (``p`` / ``not p``) or as meanings (the same words but for one complementary pair,
        "n is even" / "n is odd", or one negation: :func:`_complementary_meanings`, re-run review ADV-13). The writer's own
        either/or is named at warning; one labelled as subject knowledge and not marked as a stated rule at info (ADV-11 b:
        :meth:`unmarked_knowledge`; the label claims knowledge, so the shape is recorded, not charged). A disjunction stated
        by a source, or marked as a stated rule, never fires."""
        tried = 0
        for w in r.links:
            writer = self.writer_step(w)
            if not writer and not self.unmarked_knowledge(w):
                continue
            for node in self.parts(w):
                if node.get("op") != "or" or tried >= MAX_TAUTOLOGIES:
                    continue
                args = node.get("args") or []
                if any(_complementary(a, b) or self.complementary_meanings(a, b) for i, a in enumerate(args) for b in args[i + 1:]):
                    continue
                if _exhaustive_options([gloss(a, self.meanings)[:400] for a in args]):
                    continue  # the options exhaust what they speak of (a closed partition, or comparisons that cover every case)
                tried += 1
                run = self.runs.entail([], node, f"taut{tried}")
                if run.status is not _S.COUNTEREXAMPLE:
                    continue  # a tautology (or undecided: recorded) is no false dilemma
                options = "; ".join(self.g(a, 120) for a in args[:4])
                whose = "the writer's either/or" if writer else "the either/or, labelled general_knowledge,"
                self.emit("ARG-FD-001", f"false dilemma: the proof needs {whose} {self.named(w)} (options: {options}), which no check "
                                        "established; it is no tautology and its options are not complementary, so nothing shows they are the only ones",
                          assertion_ids=[w], missing_link=self.link_of([w], node), evidence=self.span_of(w), derivation="engine_recheck",
                          digests=[*r.digests, run.digest], severity=None if writer else "info")

    def complementary_meanings(self, a: dict, b: dict) -> bool:
        """Two options whose meanings exclude each other and cover every case (:func:`_complementary_meanings`)."""
        # the glosses as the meanings write them: self.g cuts and masks for display ('passed' would read as '[...]')
        return _complementary_meanings(gloss(a, self.meanings)[:400], gloss(b, self.meanings)[:400])

    def hasty_links(self, r: _R0) -> None:
        """ARG-HG-001 i: the writer's link draws an open universal from instance facts (an instance, a dated case, a named
        study or a sample of cases: :func:`_instance`)."""
        for w in r.links:
            if not self.writer_step(w):
                continue
            for node in self.parts(w):
                if node.get("op") != "implies":
                    continue
                consequent = " ".join(self.meanings.get(n, "") for n in sorted(_vars(node["right"])))
                cue = _open_universal(consequent)
                atoms = sorted(_vars(node["left"]))
                ante_texts = [self.meanings.get(n, "") for n in atoms]
                if cue is None and atoms and all(_instance(t) for t in ante_texts):
                    # a majority claim from a sample (repair round 2, ADV2-10): it generalises unless it keeps every word of the
                    # sample's own description ('9 of 12 students in the class passed, so most students in the class passed')
                    cue = _majority(consequent)
                    if cue is not None and any(lexis.has_cue(_tokens(t), cues.REPRESENTATIVE) for t in ante_texts):
                        cue = None  # a sample said to stand for its population (a random or representative sample, a census)
                    elif cue is not None and not _sampling_marked(ante_texts):
                        # the cases counted are a whole the point speaks of again, not a sample of it ('700 of the town's 1,000
                        # residents supported it, so most residents supported it'): it generalises only when its population adds
                        # words of its own ('most students in the country' from the students in our class: repair round 3, ADV3-05)
                        if not _population_added(consequent, cue, ante_texts):
                            cue = None
                    elif cue is not None:
                        kept = set(lexis.content_stems(consequent))
                        numbers = {lexis.root(w) for w in cues.NUMBER_WORDS}
                        if all(set(st for st in lexis.content_stems(t) if not st[:1].isdecimal() and st not in numbers) <= kept for t in ante_texts):
                            cue = None
                sampled = False
                if cue is None and atoms and all(_generalises(t, consequent) for t in ante_texts):
                    # the finding of the cases looked at stated of a wider whole, with no universal word ('the one quadrat sampled
                    # contained no orchids, so the meadow contains no orchids': repair round 2, holdout2 hasty class)
                    cue, sampled = "the wider whole", True
                if cue is None or not atoms:
                    continue
                if not sampled and (any(_open_universal(t) for t in ante_texts) or not all(_instance(t) for t in ante_texts)):
                    continue
                self.emit("ARG-HG-001", f"hasty generalisation: the writer's link {self.named(w)} draws the universal '{cue} ...' "
                                        f"({self.g(node['right'], 160)!r}) from the instance fact(s) {', '.join(atoms[:4])}, which state no such generality",
                          assertion_ids=[w], missing_link=self.link_of([w], node),
                          evidence=[*self.span_of(w), *[s for n in atoms[:3] for s in self.meaning_span(n)]], derivation="ir_glosses", digests=r.digests)
                break

    def warranting_control(self, w: str, node: dict) -> Optional[str]:
        """The control cue (:func:`_control`) that warrants the causal step ``node`` of the writer's link ``w``, read only where
        it bears on that step: the link's own label, the meanings of the link's symbols, and the labels of the premises (and
        the point) that share a symbol with the link. A control cue elsewhere in the problem ("the shop was chosen randomly by
        the marketing team", "the department uses a control group in its experiments") controls nothing about this cause
        (repair round 3, ADV3-06: a decoy anywhere made the writer's causal assumption disappear from the diagnosis)."""
        names = _vars(self.dumps[w]) | _vars(node)
        texts = [self.label(w)] + [self.meanings.get(n, "") for n in sorted(names)]
        texts += [p.label or "" for p in self.premises if p.id != w and _vars(self.dumps[p.id]) & names]
        if self.problem.conclusion is not None and self.conclusion is not None and _vars(self.conclusion) & names:
            texts.append(self.problem.conclusion.label or "")
        return next((c for c in (_control(t) for t in texts) if c), None)

    def causal_links(self, r: _R0) -> None:
        """ARG-CL-001: the writer's link reads a cause into a sequence in time or a correlation, the cause is new to its
        antecedent, and nothing that bears on the step states a control (:meth:`warranting_control`)."""
        for w in r.links:
            if not self.writer_step(w):
                continue
            for node in self.parts(w):
                if node.get("op") != "implies":
                    continue
                consequent = " ".join(self.meanings.get(n, "") for n in sorted(_vars(node["right"])))
                cause = _causal(consequent)
                if cause is None or self.warranting_control(w, node) is not None:
                    continue
                ante = set(_vars(node["left"]))
                fact_labels = [p.label or "" for p in self.premises if p.id != w and _vars(self.dumps[p.id]) and set(_vars(self.dumps[p.id])) <= ante]
                ante_texts = [self.meanings.get(n, "") for n in sorted(ante)] + fact_labels
                if _cause_presupposed(cause, ante_texts):
                    # the antecedent already speaks of the effect ("the effect was no longer detectable after seven days"): the
                    # step infers a property of it (how long it lasts), not a cause from a sequence (repair round 3,
                    # V3-FALSE-CAUSAL-EFFECT-DURATION)
                    continue
                numeric = sorted(n for n in ante if self.sorts.get(n) in ("Int", "Real"))
                pair = next(((a, b) for i, a in enumerate(numeric) for b in numeric[i + 1:] if _differ_only_by_date(self.meanings.get(a), self.meanings.get(b))), None)
                # a sequence cue in the link's label, or in the antecedent's own meanings and facts ('sales rose after the advert
                # ran in May'), or the antecedent's events dated at two different times ('the club began in 2019', 'attendance
                # rose in 2020'): repair round 3, ADV3-07
                seq = _sequence(self.label(w)) or next((c for c in (_sequence(t) for t in ante_texts) if c), None) or _two_times(ante_texts)
                # a cause read into a correlation (repair round 2): the antecedent's meanings, or a fact premise that asserts them
                corr = None if pair or seq else next((c for c in (_correlation(t) for t in ante_texts) if c), None)
                if pair is None and seq is None and corr is None:
                    continue
                if corr is not None:
                    shape = f"correlation ('{model_text(corr)[:120]}')"
                else:
                    when = (f"{pair[0]} and {pair[1]} are one quantity at two times" if pair else "") + ("; " if pair and seq else "") + \
                           (("the events are " + seq if seq.startswith("dated") else f"the step says '{seq}'") if seq else "")
                    shape = f"sequence in time ({when})"
                self.emit("ARG-CL-001", f"causal leap: the writer's link {self.named(w)} reads a cause ('{cause}': {self.g(node['right'], 140)!r}) into a "
                                        f"{shape}, and nothing that bears on the step states a control or comparison that rules out another cause",
                          assertion_ids=[w], missing_link=self.link_of([w], node), evidence=self.span_of(w), derivation="ir_glosses", digests=r.digests)
                break

    def sense_definition(self, r: _R0) -> None:
        """ARG-EQ-003: one symbol, two senses. Either a symbol's meaning qualifies a head noun by sense and the writer's link
        that uses it is labelled with the bare generic definition of that noun, or the writer's link uses a word of the
        closed table of equivocal terms in both of its senses (:meth:`equivocal_term`, re-run review A-INF-EQ)."""
        for w in r.links:
            if not self.writer_step(w):
                continue
            label = self.label(w)
            fired = False
            for name in sorted(_vars(self.dumps[w])):
                heads = _qualified_heads(self.meanings.get(name))
                head = next((h for h in sorted(heads) if _bare_definition(label, h)), None)
                if head is None:
                    continue
                self.emit("ARG-EQ-003", f"equivocation: the symbol {name} means {_cut(self.meanings.get(name, ''), 160)!r}, a qualified sense "
                                        f"({heads[head]}), but the link {w} rests on the bare generic definition {_cut(label, 160)!r}: one symbol "
                                        "carries two senses of the word",
                          assertion_ids=[w], missing_link=MissingLink(premise_ids=[w], antecedent=_cut(heads[head]), consequent=_cut(label),
                                                                      text=_cut(f"the sense '{heads[head]}' is the same as the sense of {label!r}", 600)),
                          evidence=[*self.span_of(w), *self.meaning_span(name)], derivation="ir_glosses", digests=r.digests)
                fired = True
                break
            if not fired:
                self.equivocal_term(w, r)

    def equivocal_term(self, w: str, r: _R0) -> None:
        """ARG-EQ-003 by the closed table (:data:`~.argument_cues.EQUIVOCAL_TERMS`): among the texts of the writer's link
        (its label and the meanings of its symbols), one that holds the word selects its technical sense and one that
        holds it selects its everyday sense (they may be one text: the label), each by a cue that no negation precedes.
        A link whose label or consequent is negated contrasts the senses ("it takes effort, so no work is done") and is not
        read."""
        label = self.label(w)
        for node in self.parts(w):
            if lexis.negated(label):
                return
            if node.get("op") == "implies":
                right = node["right"]
                if right.get("op") == "not" or any(lexis.negated(self.meanings.get(n, "")) for n in _vars(right)):
                    continue
            texts = [("label", w, label)] + [("meaning", n, self.meanings.get(n, "")) for n in sorted(_vars(node))]
            for term in cues.EQUIVOCAL_TERMS:
                held = [(where, ident, text) for where, ident, text in texts if text and any(t in term.forms for t in _tokens(text))]
                if not held:
                    continue
                tech = next(((ident, cue) for _wh, ident, text in held for cue in [_selecting_cue(text, term.technical_cues)] if cue), None)
                every = next(((ident, cue) for _wh, ident, text in held for cue in [_selecting_cue(text, term.everyday_cues)] if cue), None)
                if tech is None or every is None:
                    continue
                word = next(t for _wh, _i, text in held for t in _tokens(text) if t in term.forms)
                self.emit("ARG-EQ-003", f"equivocation: the writer's link {self.named(w)} uses '{word}' in its {term.technical} sense ('{tech[1]}', in "
                                        f"{tech[0]}) and in its {term.everyday} sense ('{every[1]}', in {every[0]}): one word carries two senses, so the "
                                        "step holds only if the two senses are the same",
                          assertion_ids=[w], missing_link=MissingLink(premise_ids=[w], antecedent=_cut(f"'{word}' in the {term.technical} sense"),
                                                                      consequent=_cut(f"'{word}' in the {term.everyday} sense"),
                                                                      text=_cut(f"'{word}' in the {term.technical} sense is the same as '{word}' in the "
                                                                                f"{term.everyday} sense", 600)),
                          evidence=[*self.span_of(w), *[s for _wh, ident, _t in held if _wh == "meaning" for s in self.meaning_span(ident)]][:8],
                          derivation="ir_glosses", digests=r.digests)
                return

    def symbol_senses(self, r: _R0) -> None:
        """ARG-EQ-003 across premises (repair round 2, MISS-EQUIV-PHYS): one symbol carries both senses of a word of the closed
        table (:data:`~.argument_cues.EQUIVOCAL_TERMS`) when, among its meaning and the labels of the premises (and the point)
        that use it, one text selects the technical sense and another the everyday sense ("Pushing a wall all day is hard
        work" and "In physics, work is done whenever a force moves an object", both encoded with ``does_work``), each by a cue
        no negation precedes. A negated text contrasts the senses and is not read. The point then follows only if the two
        senses are the same."""
        users: dict[str, list[tuple[str, str, str]]] = {}
        for pid in self.ids:
            label = self.label(pid)
            if label and not lexis.negated(label):
                for name in _vars(self.dumps[pid]):
                    users.setdefault(name, []).append(("premise", pid, label))
        if self.conclusion is not None and self.concl_id:
            label = self.label(self.concl_id) if self.concl_id in self.by_id else (getattr(self.problem.conclusion, "label", None) or "")
            if label and not lexis.negated(label):
                for name in _vars(self.conclusion):
                    users.setdefault(name, []).append(("point", self.concl_id, label))
        for name in sorted(users):
            meaning = self.meanings.get(name, "")
            texts = ([("meaning", name, meaning)] if meaning and not lexis.negated(meaning) else []) + users[name]
            if len({ident for _w, ident, _t in texts}) < 2:
                continue
            token_sets = [(where, ident, text, frozenset(_tokens(text))) for where, ident, text in texts]  # each text read once
            for term in cues.EQUIVOCAL_TERMS:
                held = [(where, ident, text) for where, ident, text, toks in token_sets if not toks.isdisjoint(term.forms)]
                if len(held) < 2:
                    continue
                tech = next(((ident, cue) for _wh, ident, text in held for cue in [_selecting_cue(text, term.technical_cues)] if cue), None)
                every = next(((ident, cue) for _wh, ident, text in held for cue in [_selecting_cue(text, term.everyday_cues)] if cue), None)
                if tech is None or every is None or tech[0] == every[0]:
                    continue
                word = next(t for _wh, _i, text in held for t in _tokens(text) if t in term.forms)
                ids = [i for _wh, i, _t in held if i in self.by_id]
                self.emit("ARG-EQ-003", f"equivocation: the symbol {name} carries '{word}' in its {term.technical} sense ('{tech[1]}', in {tech[0]}) and in "
                                        f"its {term.everyday} sense ('{every[1]}', in {every[0]}): one symbol joins two senses of the word, so the point "
                                        "follows only if the two senses are the same",
                          assertion_ids=ids, missing_link=MissingLink(premise_ids=ids[:8], antecedent=_cut(f"'{word}' in the {term.everyday} sense"),
                                                                      consequent=_cut(f"'{word}' in the {term.technical} sense"),
                                                                      text=_cut(f"'{word}' in the {term.everyday} sense is the same as '{word}' in the "
                                                                                f"{term.technical} sense", 600)),
                          evidence=[s for i in ids[:4] for s in self.span_of(i)][:8], derivation="ir_glosses", digests=r.digests)
                return

    # -------------------------------------------------------------------------------- the COUNTEREXAMPLE rules

    def counterexample_rules(self) -> None:
        if self.conclusion is None or not self.premises:
            return
        concl = self.conclusion
        named_specific = self.refute()
        if self.codes & ADVISORY_CODES:
            return  # the counterexample rests on figures the encoding leaves open: no argument shape is read into it
        propositional = any(self.sorts.get(n) == "Bool" for n in _vars(concl))
        premise_vars: set[str] = set()
        for pid in self.ids:
            premise_vars |= _vars(self.dumps[pid])
        parts = _conjuncts(concl)
        linked = [c for c in parts if _vars(c) & premise_vars]
        unlinked = [c for c in parts if not (_vars(c) & premise_vars)]
        if propositional and not named_specific:
            named_specific = self.affirming(concl) or named_specific
            named_specific = self.denying(concl) or named_specific
        if not linked:
            if propositional:
                self.hasty_point(concl)
                self.emit("ARG-NS-001", f"no premise mentions any symbol of the point ({self.g(concl, 200)!r}): none of the reasons given touches it, "
                                        "so the point does not follow from them",
                          assertion_ids=[self.concl_id or ""], derivation="ir_structure")
            return
        if named_specific:
            return
        if unlinked and self.partial(linked, unlinked):
            return  # the linked part follows: the counterexample only falsifies the unlinked judgement
        target = concl if not unlinked else _and(linked)
        if propositional and self.bridge(target, bool(unlinked)):
            return
        if propositional and not self.runs.incomplete:
            self.emit("ARG-INV-001", "the point does not follow from its encoded reasons, which mention it" + (" (its linked part does not follow either)" if unlinked else "")
                                     + f"; no more specific shape is named (the counterexample sets {self.values(self.proc.model, _vars(concl)) or 'its symbols'})",
                      assertion_ids=[self.concl_id or ""], derivation="engine_recheck" if self.runs.count else "ir_structure")

    def refute(self) -> bool:
        """ARG-REFUTE-001: the premises a check verified entail the negated point."""
        if not self.established:
            return False
        run = self.runs.entail(self.established, _not(self.conclusion), "neg")
        if run.status is not _S.ENTAILED:
            return False
        self.emit("ARG-REFUTE-001", f"the premises a check verified ({', '.join(self.established[:6])}) entail the negation of the point "
                                    f"({self.g(self.conclusion, 200)!r}): the stated evidence refutes it",
                  assertion_ids=[*self.established[:16], self.concl_id or ""], evidence=[s for pid in self.established[:8] for s in self.span_of(pid)],
                  derivation="engine_recheck", digests=[run.digest])
        return True

    def _conditionals(self) -> list[str]:
        return [pid for pid in self.ids if self.dumps[pid].get("op") == "implies"]

    def _facts(self) -> list[str]:
        return [pid for pid in self.ids if not _is_link(self.dumps[pid])]

    def affirming(self, concl: dict) -> bool:
        """ARG-AC-001 a: a rule P -> Q, a stated fact Q and the point P; the converse would make it follow."""
        tried = 0
        facts = self._facts()
        for c in self._conditionals():
            rule = self.dumps[c]
            if not _same(concl, rule["left"]):
                continue
            # the fact states the rule's consequent alone or as one of its conjuncts ('the peso appreciated by 6% and exports fell':
            # repair round 2, holdout2 class)
            fact = next((f for f in facts if any(_same(x, rule["right"]) for x in _conjuncts(self.dumps[f]))), None)
            if fact is None or tried >= MAX_CONVERSES:
                continue
            tried += 1
            converse = _implies(rule["right"], rule["left"])
            run = self.runs.entail(self.ids, concl, f"conv{tried}", extra=[converse])
            if run.status is _S.ENTAILED:
                self.emit("ARG-AC-001", f"affirming the consequent: from the rule {self.named(c)} ({self.g(rule, 200)}) and the stated fact "
                                        f"{self.named(fact)} the point concludes {self.g(rule['left'], 120)!r}; only the converse, which no premise states, "
                                        "would give it",
                          assertion_ids=[c, fact, self.concl_id or ""], missing_link=self.link_of([], converse),
                          evidence=[*self.span_of(c), *self.span_of(fact)], derivation="engine_recheck", digests=[run.digest])
                return True
        return False

    def denying(self, concl: dict) -> bool:
        """ARG-DA-001 a: a rule P -> Q, a stated fact not P and the point not Q; the inverse would make it follow."""
        tried = 0
        facts = self._facts()
        for c in self._conditionals():
            rule = self.dumps[c]
            if not _negation_of(concl, rule["right"]):
                continue
            fact = next((f for f in facts if any(_negation_of(x, rule["left"]) for x in _conjuncts(self.dumps[f]))), None)
            if fact is None or tried >= MAX_CONVERSES:
                continue
            tried += 1
            inverse = _implies(_not(rule["left"]), _not(rule["right"]))
            run = self.runs.entail(self.ids, concl, f"inv{tried}", extra=[inverse])
            if run.status is _S.ENTAILED:
                self.emit("ARG-DA-001", f"denying the antecedent: from the rule {self.named(c)} ({self.g(rule, 200)}) and the stated fact "
                                        f"{self.named(fact)} the point concludes {self.g(concl, 120)!r}; only the inverse, which no premise states, would "
                                        "give it",
                          assertion_ids=[c, fact, self.concl_id or ""], missing_link=self.link_of([], inverse),
                          evidence=[*self.span_of(c), *self.span_of(fact)], derivation="engine_recheck", digests=[run.digest])
                return True
        return False

    def hasty_point(self, concl: dict) -> None:
        """ARG-HG-001 ii: a universal point no premise links to, drawn from instance facts."""
        point_text = " ".join(self.meanings.get(n, "") for n in sorted(_vars(concl)))
        cue = _open_universal(point_text)
        facts = self._facts()
        if len(facts) != len(self.premises):
            return
        texts = [" ".join(self.meanings.get(n, "") for n in sorted(_vars(self.dumps[f]))) for f in facts]
        if cue is None:
            # no universal word, but the point states a sample's finding of a wider whole ('four of the five pupils
            # interviewed never cycle to school' for 'pupils across Norway no longer cycle to school': repair round 2)
            if texts and all(_sample_fact(t) for t in texts) and any(_generalises(t, point_text) for t in texts):
                cue = "the wider whole"
            else:
                return
        elif not all(_instance(t) and not _open_universal(t) for t in texts):
            return
        self.emit("ARG-HG-001", f"hasty generalisation: the universal point '{cue} ...' ({self.g(concl, 160)!r}) is drawn from instance fact(s) "
                                f"{', '.join(facts[:6])}, and no premise links them to it",
                  assertion_ids=[self.concl_id or "", *facts[:16]], evidence=[s for f in facts[:6] for s in self.span_of(f)], derivation="ir_glosses")

    def bridge(self, target: dict, part: bool) -> bool:
        """ARG-NS-002 (with ARG-EQ-002): one bridge E -> A from a stated fact E to the antecedent A of a stated rule whose
        consequent shares the point's symbols makes the point follow; that bridge is the missing link."""
        point_vars = _vars(target)
        facts = self._facts()
        tried = 0
        for c in self._conditionals():
            rule = self.dumps[c]
            if not (_vars(rule["right"]) & point_vars):
                continue
            # the part of the antecedent no fact states is what a bridge must reach ("E -> A" when A has stated conjuncts)
            needed = [a for a in _conjuncts(rule["left"]) if not any(_same(a, self.dumps[f]) for f in facts)]
            if not needed:
                continue
            for f in facts:
                fact = self.dumps[f]
                if any(_same(fact, a) for a in needed) or tried >= MAX_BRIDGES:
                    continue
                tried += 1
                link_expr = _implies(fact, _and(needed))
                run = self.runs.entail(self.ids, target, f"bridge{tried}", extra=[link_expr])
                if run.status is not _S.ENTAILED:
                    continue
                link = self.link_of([], link_expr)
                which = "the linked part of the point" if part else "the point"
                if self.reversed_rule_bridge(f, c, fact, _and(needed), link, run.digest):
                    return True
                self.emit("ARG-NS-002", f"{which} does not follow; the bridge '{link.text}' from the stated fact {self.named(f)} to the antecedent of "
                                        f"{self.named(c)} would make it follow, and no premise states it: that bridge is the missing link",
                          assertion_ids=[f, c], missing_link=link, evidence=[*self.span_of(f), *self.span_of(c)], derivation="engine_recheck",
                          digests=[run.digest])
                self.equivocation_bridge(f, c, fact, _and(needed), run.digest)
                return True
        return False

    def reversed_rule_bridge(self, fid: str, cid: str, fact: dict, needed: dict, link: MissingLink, digest: Optional[str]) -> bool:
        """ARG-AC-001 / ARG-DA-001 b (repair round 2, holdout2 class): the one missing bridge from a stated fact to the antecedent of
        a rule is the converse (Q -> P) or the inverse (not P -> not Q) of another stated rule P -> Q: the argument needs the
        converse or the inverse of what it states ("had the treaty been ratified, the dispute would have ended"; the treaty was
        not ratified; "an unresolved dispute led to rearmament": the step 'not ratified -> not ended' is the inverse)."""
        for c2 in self._conditionals():
            if c2 == cid:
                continue
            rule = self.dumps[c2]
            if _same(fact, rule["right"]) and _same(needed, rule["left"]):
                code, shape, what = "ARG-AC-001", "affirming the consequent", "the converse"
            elif _negation_of(fact, rule["left"]) and _negation_of(needed, rule["right"]):
                code, shape, what = "ARG-DA-001", "denying the antecedent", "the inverse"
            else:
                continue
            self.emit(code, f"{shape}: the point follows only through the step '{link.text}' from the stated fact {self.named(fid)} to the antecedent "
                            f"of {self.named(cid)}, and that step is {what} of the rule {self.named(c2)} ({self.g(rule, 160)}), which no premise states: "
                            "that step is the missing link",
                      assertion_ids=[c2, fid, cid, self.concl_id or ""], missing_link=link,
                      evidence=[*self.span_of(c2), *self.span_of(fid), *self.span_of(cid)], derivation="engine_recheck", digests=[digest])
            return True
        return False

    def equivocation_bridge(self, fid: str, cid: str, fact: dict, antecedent: dict, digest: Optional[str]) -> None:
        """ARG-EQ-002: the bridge joins two symbols whose meanings share a head noun that one of them qualifies by sense."""
        a, b = _atom(fact), _atom(antecedent)
        if a is None or b is None or a[0] == b[0]:
            return
        ma, mb = self.meanings.get(a[0], ""), self.meanings.get(b[0], "")
        ha, hb = _qualified_heads(ma), _qualified_heads(mb)
        stems_a, stems_b = set(lexis.content_stems(ma)), set(lexis.content_stems(mb))
        shared = sorted((set(ha) & stems_b) | (set(hb) & stems_a))
        if not shared:
            self.equivocal_bridge_term(fid, cid, fact, antecedent, a[0], b[0], ma, mb, digest)
            return
        noun = shared[0]
        marker = ha.get(noun) or hb.get(noun) or noun
        text = f"the two senses of '{noun}' are the same"
        self.emit("ARG-EQ-002", f"equivocation: the missing bridge joins two senses of '{noun}' ({marker}): {_cut(ma, 140)!r} and {_cut(mb, 140)!r}; "
                                f"the argument needs {text}, which nothing states",
                  assertion_ids=[fid, cid], missing_link=MissingLink(premise_ids=[], antecedent=_cut(ma), consequent=_cut(mb), text=text,
                                                                     expr=_implies(fact, antecedent)),
                  evidence=[*self.meaning_span(a[0]), *self.meaning_span(b[0])], derivation="engine_recheck", digests=[digest])

    def equivocal_bridge_term(self, fid: str, cid: str, fact: dict, antecedent: dict, na: str, nb: str, ma: str, mb: str, digest: Optional[str]) -> None:
        """ARG-EQ-002 by the closed table (repair round 2, holdout2 class): the missing bridge joins a symbol whose meaning holds a
        word of :data:`~.argument_cues.EQUIVOCAL_TERMS` in one sense and a symbol whose meaning selects the word's other sense by
        a cue ("effective demand (willingness and ability to pay) for housing has risen" and "many residents want a larger flat
        (desire)"): the bridge equates the two senses of the word. Negated meanings contrast the senses and are not read."""
        if lexis.negated(ma) or lexis.negated(mb):
            return
        for term in cues.EQUIVOCAL_TERMS:
            in_a, in_b = any(t in term.forms for t in _tokens(ma)), any(t in term.forms for t in _tokens(mb))
            if not (in_a or in_b):
                continue
            ta, ea = _selecting_cue(ma, term.technical_cues), _selecting_cue(ma, term.everyday_cues)
            tb, eb = _selecting_cue(mb, term.technical_cues), _selecting_cue(mb, term.everyday_cues)
            if ta and eb and not tb and (in_a or in_b):
                senses = ((na, term.technical, ta), (nb, term.everyday, eb))
            elif tb and ea and not ta and (in_a or in_b):
                senses = ((nb, term.technical, tb), (na, term.everyday, ea))
            else:
                continue
            word = next(t for text in (ma, mb) for t in _tokens(text) if t in term.forms)
            text = f"'{word}' in the {senses[1][1]} sense is the same as '{word}' in the {senses[0][1]} sense"
            self.emit("ARG-EQ-002", f"equivocation: the missing bridge joins {senses[0][0]}, '{word}' in its {senses[0][1]} sense ('{senses[0][2]}'), and "
                                    f"{senses[1][0]}, in its {senses[1][1]} sense ('{senses[1][2]}'): the argument needs {text}, which nothing states",
                      assertion_ids=[fid, cid], missing_link=MissingLink(premise_ids=[], antecedent=_cut(ma), consequent=_cut(mb), text=_cut(text, 600),
                                                                         expr=_implies(fact, antecedent)),
                      evidence=[*self.meaning_span(na), *self.meaning_span(nb)], derivation="engine_recheck", digests=[digest])
            return

    def partial(self, linked: list[dict], unlinked: list[dict]) -> bool:
        """ARG-PART-001 (info): the falsified conjuncts are judgements no premise mentions, and the rest follows."""
        run = self.runs.entail(self.ids, _and(linked), "part")
        if run.status is not _S.ENTAILED:
            return False
        names = sorted({n for c in unlinked for n in _vars(c)})
        judgement = "; ".join(self.g(c, 160) for c in unlinked[:4])
        self.emit("ARG-PART-001", f"the conjunct(s) {judgement!r} of the point share no symbol with any premise, while the rest of the point follows "
                                  "from the encoded premises: the encoding gives that judgement no reason, so the counterexample only falsifies the "
                                  "unlinked part",
                  assertion_ids=[self.concl_id or ""], evidence=[s for n in names[:8] for s in self.meaning_span(n)], derivation="engine_recheck",
                  digests=[run.digest])
        return True


def diagnose(problem: Any, proc: Any, compiled: Any, config: Any, limits: Any, diagnostics: Optional[list] = None) -> tuple[list[NamedDiagnostic], str]:
    """The engine's named diagnostics for one decided problem and the rule version that produced them (module docstring).
    ``argument_rules`` is ``argdiag-2``, or ``argdiag-2/incomplete:<reason>`` when a derived run was undecided, invalid or
    out of budget (the rule that needed it fired nothing)."""
    codes = {getattr(d, "code", None) for d in diagnostics or []} - {None}
    found = _Diagnosis(problem, proc, compiled, config, limits, codes)
    found.status_rules()
    if problem.query == "entailment" and problem.conclusion is not None and not (codes & NO_VERDICT_CODES):
        if proc.status is _S.ENTAILED:
            found.entailed_rules()
        elif proc.status is _S.COUNTEREXAMPLE:
            found.counterexample_rules()
    rules = incomplete_rules(found.runs.incomplete[0]) if found.runs.incomplete else ARG_RULES_VERSION
    return found.out, rules
