"""The translator's circularity check beyond a restatement as written (E112, round-8 clearance c1).

The engine's ``E112`` and the pipeline's step 4c read a conclusion as restated only when it, or each of its conjuncts, is a
premise or a conjunct of one AS WRITTEN (or in an equivalent normal form), and only when the restating premises are the
writer's own by their grounding kind. The transfer auditor reads more (``overseer.checks.translation``, rules
``semantic-restatement``, ``grounded-transcription``, ``receipt-disclosure`` and ``restatement-necessity``), so in round c1
seven encodings it confirmed circular (OVS-TRN-006) reached the router displayed ENTAILED, a verdict the overseer refuted
afterwards: maa-t14 m6.1 ("x − 4 > 0" proves "x > 4"), ch-t14 s2.12 ("e_h = 6" proves "1 × e_h = 6"), cs-t14 c18.2 and c25.1
(a task-labelled Boolean definition no check verified proves the claim by its Boolean structure), ph-p8b s1.1 and bi-t14 s1.2
and s4.7 (part of the conclusion restated by a task figure no check verified, on which the result rests).

This module applies those rules, simplified and never looser than the translator's own, BEFORE the verdict is displayed.
The clearance's second pass corrected them where the round's translation-fidelity lens, judging claim by claim, found the
auditor's labels false (m6.1 and c18.2 are faithful checks of the claim's own step) and where the first pass's reading broke
committed tests (the end-to-end fixture cs_entailed; the argument-diagnosis cases packed in one premise): a premise's own
link is an argument, and a definitional identity or the claim's stated step input is no restatement (below), as the
auditor's rules definitional-identity and stated-step read them.

* **semantic restatement**: a conjunct of the conclusion (negation pushed inward; a conjunct that holds with no premise
  needs none) is restated by a premise when it follows from the premise alone by its Boolean structure, every comparison
  and arithmetic term an opaque atom and every implication of the premise too ("e or e", "not not e", "(e and b) or (e and
  c)"; never "b and (b implies e)", a link and its antecedent packed in one premise, which argues and which the engine and
  the argument rules decide), or when a
  conjunct of the premise that writes the same figures (0 and 1 aside) is equivalent to it by the arithmetic of the
  conjunct's own symbols, each number exact and every arithmetic of numbers alone one opaque value, a division of it by a
  number kept as such ("x − 4 > 0" for "x > 4", "e_h = 6" for "1 × e_h = 6", "g × 11560000000000 = G × M" for "g = G × M /
  11560000000000", G and M figures). A premise that gives a conjunct only by the computation it writes on numbers ("a =
  (20 − 0)/4.0" beside "a = 5.0"), by a computation that writes a new figure ("p = 1.60" beside "p × 100 = 160"), or that
  entails it without being equivalent to it ("x = 5" beside "x > 3") is a derivation the engine checks, never a
  restatement. Rule ``unstated-scaling`` (round-9 clearance c2, given the figures the claim's sources state): a premise
  equivalent to the conjunct whose extra figures are numbers one of which no source states ("6000 × vsq = 54096", general
  knowledge, beside "vsq = 9.016" for the claim "v² = 2 × 9.8 × 0.46 = 9.016") is the conjunct scaled or moved across by
  the translation's own figures, a restatement: the engine would check the translation's arithmetic, never the claim's;
* **standing**: a restating premise is data when a check in this process verified it (``verified=True``: a located
  quotation, a task figure the task record states for that quantity) or located the excerpt it cites in a supplied text
  (whether the excerpt states its figures is the grounding check's own finding). It is the writer's own when it has no
  grounding, an inferential kind, a grounding a check refuted, an unverified ``arithmetic_fact`` or quotation (the
  engine's own rule, ``assumed_grounding``), or a task label (``task_setting``, ``rubric_rule``) on content no check reads
  in the task: a Boolean statement, a relation, or a structural figure 0 or 1 (the transfer auditor's rule
  ``data-standing``). A task label on other figures, or a source label, that no check verified stays what it was: an
  unverified dependency the engine lists and the release rule refuses, never the claim assumed;
* **full restatement**: every conjunct that needs a premise is restated, at least one restating premise is the writer's
  own, and without those premises the conclusion no longer follows (or it cannot be decided): the claim is assumed;
* **partial restatement**: some conjuncts are derived, but a premise of a task-given kind (``task_setting``,
  ``rubric_rule``, ``arithmetic_fact``) that only gives symbols values ("k = 50") and that no check verified restates
  another, and without such premises the conclusion no longer follows: the receipt would present an assumed part of the
  claim as a figure given with the task. A relation or computation under such a label is a step the engine checks.
* **exemptions** (never for a restatement as written): a premise that only NAMES an expression (``v iff E`` or ``v = E``,
  ``v`` in no other premise) the conclusion is an identity of ("X ↔ (A ∧ B) ∨ (¬A ∧ C)" beside "¬A → (X ↔ C)"; a
  simplification "(A AND B) OR (A AND NOT B) is equivalent to A") is a definition the engine checks the identity of, and a
  premise the claim itself writes before its step marker, with the restated conjunct written after it ("Domain: x + 4 > 0
  and x − 4 > 0, so x > 4"), is the input of the claim's stated step.

Two more rules read the claim's own text beside its encoding (round-8 clearance c1, the translation-fidelity lens: four
encodings that prove nothing about their claim were displayed ENTAILED; ph-t14 s3.2 is the arithmetic rule above):

* **result asserted** (rule ``result-asserted``): a premise of the writer's own that only gives a symbol a value, the value
  being the result of a calculation the claim writes ("r³ = (5.000 × 10⁶ m)³ = 1.250 × 10²⁰ m³", ph-t14 s4.4: the cube
  asserted as an ``arithmetic_fact``), restates a conjunct that follows from it alone and checks a figure within 1/100 of
  that value (the stated figure's band, never a further quantity): the engine would check only that the result rounds to
  itself, never compute the calculation. Such a row joins the full restatement above. A value used to compute another
  quantity ("a = 5" beside "F = 2 × a = 10") or a conclusion about another figure ("x = 5" beside "x > 3") is untouched;
* **consequence asserted** (rule ``consequence-asserted``): the claim draws a consequence by a connective ("..., so A",
  "therefore A", "A because R"), and a premise that is the writer's own step (no grounding, ``specialist_inference`` or
  ``assumption``, no check verifying it; a law stated from subject knowledge is a rule the encoding applies) that states
  a fact (no link, no value assignment) and whose label (its own words, after the claim's id) states that consequence
  rather than the reason (at least three content stems of the consequence clause, two thirds of its words outside the
  reason clause) is needed for the conclusion: the encoding assumes the claim's own inference instead of deriving it
  (hi-t14 h1.12, "A war of three years
  and one month therefore ended with the original aims of both sides abandoned, which is the mark of limited
  objectives", the main clause asserted as the premise 'h1.12-reason'; ph-p8b s6.2, "the speed is zero, so the total
  energy is elastic potential energy", the energy relation asserted under the label of the claim's link). A premise that
  states the reason, a stated figure ("revenue fell from $10m to $8m" beside its percentage) or a link is untouched, and so
  is a premise the other premises derive anyway.

Each is the translator's ``E112`` (INVALID_FORMALIZATION, fed back once): the verdict is withheld, never displayed
ENTAILED. Every solver check runs under a fixed resource limit; a check left undecided is no restatement (the encoding is
then decided by the engine as before). Data on data: nothing of the problem is evaluated by Python, and every reader of
the claim's text is one pass over it.
"""
from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable, Optional

import z3

from .. import lexis
from ..engine.compiler import CompileError, compile_problem
from ..ir.schema import Problem

__all__ = ["Restatement", "semantic_restatement", "consequence_clauses", "calculation_results", "RESTATEMENT_RLIMIT", "MAX_RESTATEMENT_CHECKS"]

#: Z3 resource limit of one restatement or necessity check (deterministic, unlike a wall-clock timeout).
RESTATEMENT_RLIMIT = 400_000
#: At most this many pairwise checks per problem; beyond it no further restatement is sought (none is then reported).
MAX_RESTATEMENT_CHECKS = 160
#: Grounding kinds that claim the task's own authority: restating part of a conclusion under such a label presents an
#: assumed part of the claim as given with the task (rule receipt-disclosure).
_TASK_GIVEN = frozenset({"task_setting", "rubric_rule", "arithmetic_fact"})
_COMPARE = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})
_ARITH = frozenset({"add", "sub", "mul", "neg", "div", "idiv", "mod", "to_real"})
_LITERAL = frozenset({"int", "real"})


@dataclass(frozen=True)
class Restatement:
    """What the check found: ``kind`` is ``"full"``, ``"partial"`` or ``"consequence"``; ``premises`` the restating premises
    the decision rests on (the writer's own, or the unverified task-given ones), each with how it restates which conjunct
    (for ``"consequence"``, the consequence clause the premise states)."""
    kind: str
    premises: tuple[str, ...]
    how: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)  # (premise id, way, conjunct as JSON or clause)


def _dump(node) -> dict:
    return node.model_dump(mode="json", exclude_none=True) if hasattr(node, "model_dump") else node


def _key(node: dict) -> str:
    return json.dumps(node, sort_keys=True, separators=(",", ":"))


def _nnf_conjuncts(node: dict, negate: bool = False) -> list[dict]:
    """The conjuncts of ``node`` (IR JSON) with negation pushed inward through ``not``, ``and``, ``or`` and ``implies``."""
    op = node.get("op")
    if op == "not":
        return _nnf_conjuncts(node["arg"], not negate)
    if op == "and" and not negate:
        return [c for a in node["args"] for c in _nnf_conjuncts(a)]
    if op == "or" and negate:
        return [c for a in node["args"] for c in _nnf_conjuncts(a, True)]
    if op == "implies" and negate:
        return _nnf_conjuncts(node["left"]) + _nnf_conjuncts(node["right"], True)
    return [{"op": "not", "arg": node} if negate else node]


def _plain_conjuncts(node: dict) -> list[dict]:
    if node.get("op") == "and":
        return [c for a in node["args"] for c in _plain_conjuncts(a)]
    return [node]


def _vars(node, out: Optional[set] = None) -> set[str]:
    out = set() if out is None else out
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("op") == "var":
                out.add(n["name"])
            for k, v in n.items():
                if k not in ("op", "name", "value"):
                    stack.append(v)
        elif isinstance(n, list):
            stack.extend(n)
    return out


class _Abstraction:
    """Fresh opaque symbols for one family of checks: comparison atoms (Boolean structure) or closed arithmetic terms."""

    def __init__(self, taken: set[str]) -> None:
        self.taken = set(taken)
        self.atoms: dict[str, tuple[str, str]] = {}   # canonical key -> (symbol name, sort)

    def fresh(self, key: str, sort: str, stem: str) -> dict:
        if key not in self.atoms:
            i = len(self.atoms)
            name = f"{stem}{i}"
            while name in self.taken:
                i += 1
                name = f"{stem}{i}"
            self.taken.add(name)
            self.atoms[key] = (name, sort)
        return {"op": "var", "name": self.atoms[key][0]}

    def boolean(self, node: dict, *, links_opaque: bool = False) -> dict:
        """``node`` with every comparison and every other non-Boolean atom replaced by an opaque Boolean symbol. With
        ``links_opaque`` (a premise's reading) each implication is one opaque atom too: a premise that states a link and
        its antecedent ("b and (b implies e)", a packed modus ponens, affirming the consequent or denying the antecedent
        packed in one premise) argues for the conclusion, which the engine and the argument rules decide; it restates
        nothing. A link written the same way in the conclusion is still the same atom (a restatement as written)."""
        op = node.get("op")
        if op in ("not",):
            return {"op": "not", "arg": self.boolean(node["arg"], links_opaque=links_opaque)}
        if op in ("and", "or"):
            return {"op": op, "args": [self.boolean(a, links_opaque=links_opaque) for a in node["args"]]}
        if op == "implies" and links_opaque:
            return self.fresh(_key(node), "Bool", "atom_")
        if op in ("implies", "iff"):
            return {"op": op, "left": self.boolean(node["left"], links_opaque=links_opaque), "right": self.boolean(node["right"], links_opaque=links_opaque)}
        if op in ("var", "bool"):
            return node
        return self.fresh(_key(node), "Bool", "atom_")

    def arithmetic(self, node: dict, sorts: dict[str, str]) -> dict:
        """``node`` with every closed arithmetic term (no symbol below it, not a lone literal) one opaque value."""
        op = node.get("op")
        if op in _ARITH and not _vars(node):
            if op == "neg" and node.get("arg", {}).get("op") in _LITERAL:
                return node
            if op == "div" and node.get("right", {}).get("op") in _LITERAL:
                # a closed value divided by a number stays a division by that number ("G × M / 11560000000000" is the
                # same opaque product as in "g × 11560000000000 = G × M", divided): moving a factor across is arithmetic
                left = node["left"]
                return {"op": "div", "left": left if left.get("op") in _LITERAL else self.fresh(_key(left), _closed_sort(left), "closed_"),
                        "right": node["right"]}
            return self.fresh(_key(node), _closed_sort(node), "closed_")
        out = {}
        for k, v in node.items():
            if isinstance(v, dict):
                out[k] = self.arithmetic(v, sorts)
            elif isinstance(v, list):
                out[k] = [self.arithmetic(x, sorts) if isinstance(x, dict) else x for x in v]
            else:
                out[k] = v
        return out


def _closed_sort(node: dict) -> str:
    """The sort of a closed arithmetic term: Real when a real literal, a division or a conversion occurs in it."""
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("op") in ("real", "div", "to_real"):
                return "Real"
            stack.extend(v for k, v in n.items() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(n)
    return "Int"


class _Checker:
    """Solver checks on IR expressions of one problem, each under :data:`RESTATEMENT_RLIMIT`."""

    def __init__(self, problem: Problem) -> None:
        self.problem = problem
        self.symbols = [s.model_dump(mode="json", exclude_none=True) for s in problem.symbols]
        self.sorts = {s["name"]: s["sort"] for s in self.symbols}
        self.checks = 0

    def _compile(self, exprs: list[dict], extra: dict[str, str]):
        data = {"problem_id": "restatement-check", "request_id": self.problem.request_id, "claim_id": self.problem.claim_id, "query": "consistency",
                "symbols": [{"name": s["name"], "sort": s["sort"]} for s in self.symbols] + [{"name": n, "sort": t} for n, t in extra.items()],
                "premises": [{"id": f"e{i}", "expr": e} for i, e in enumerate(exprs)]}
        return compile_problem(Problem.model_validate(data))

    def unsat(self, exprs: list[dict], extra: Optional[dict[str, str]] = None) -> Optional[bool]:
        """True when the conjunction of ``exprs`` has no model, False when it has one, None when undecided."""
        if self.checks >= MAX_RESTATEMENT_CHECKS:
            return None
        self.checks += 1
        try:
            compiled = self._compile(exprs, extra or {})
            solver = z3.Solver(ctx=compiled.ctx)
            solver.set("rlimit", RESTATEMENT_RLIMIT)
            for term in compiled.premises.values():
                solver.add(term)
            r = solver.check()
        except (CompileError, z3.Z3Exception, ValueError):
            return None
        except Exception:  # an expression outside the schema's bounds: nothing is read from it
            return None
        if r == z3.unsat:
            return True
        if r == z3.sat:
            return False
        return None

    def valid(self, expr: dict) -> bool:
        return self.unsat([{"op": "not", "arg": expr}]) is True

    def boolean_entails(self, premise: dict, conjunct: dict) -> bool:
        """``premise`` alone entails ``conjunct`` by its Boolean structure (comparisons and arithmetic opaque, and the
        premise's own links opaque: a link is an argument, never a restatement)."""
        ab = _Abstraction(set(self.sorts))
        p, k = ab.boolean(premise, links_opaque=True), ab.boolean(conjunct)
        extra = {name: sort for name, sort in ab.atoms.values()}
        return self.unsat([p, {"op": "not", "arg": k}], extra) is True

    def arithmetic_equivalent(self, part: dict, conjunct: dict) -> bool:
        """``part`` is equivalent to ``conjunct`` by the arithmetic of the conjunct's own symbols (closed terms opaque)."""
        ab = _Abstraction(set(self.sorts))
        p, k = ab.arithmetic(part, self.sorts), ab.arithmetic(conjunct, self.sorts)
        extra = {name: sort for name, sort in ab.atoms.values()}
        return self.unsat([{"op": "not", "arg": {"op": "iff", "left": p, "right": k}}], extra) is True


def _restates(checker: _Checker, premise: dict, conjunct: dict, unstated: Optional[Callable[[Fraction], bool]] = None) -> Optional[str]:
    """How ``premise`` restates ``conjunct`` ("as written", "by Boolean structure", "by arithmetic"), or None. With
    ``unstated`` (whether no source states a value) a premise scaled by figures of the translation's own is read too
    (rule ``unstated-scaling``, :func:`_scaled_by_unstated`)."""
    ck = _key(conjunct)
    parts = _plain_conjuncts(premise)
    if any(_key(p) == ck for p in parts) or _key(premise) == ck:
        return "as written"
    kv = _vars(conjunct)
    if not kv or not (kv & _vars(premise)):
        return None
    if checker.boolean_entails(premise, conjunct):
        return "by Boolean structure"
    if conjunct.get("op") in _COMPARE or (conjunct.get("op") == "not" and conjunct["arg"].get("op") in _COMPARE):
        figures = _figures(conjunct)
        for part in parts:
            if _vars(part) != kv:
                continue
            written = _figures(part)
            if written == figures and checker.arithmetic_equivalent(part, conjunct):
                return "by the arithmetic of the conjunct's own symbols"
            if unstated is not None and _scaled_by_unstated(written, figures, unstated) and checker.arithmetic_equivalent(part, conjunct):
                return ("by the arithmetic of the conjunct's own symbols, scaled or moved across with figure(s) no source states "
                        "(rule unstated-scaling)")
    return None


def _scaled_by_unstated(written: frozenset, figures: frozenset, unstated: Callable[[Fraction], bool]) -> bool:
    """Rule ``unstated-scaling`` (round-9 clearance c2, c2 ph-t15 s2.4: "6000 × vsq = 54096", a general-knowledge premise,
    proved "vsq = 9.016" for the claim "v² = 2 × 9.8 × 0.46 = 9.016"): the figures a premise writes beyond the conjunct's
    (``written`` minus ``figures``, as :func:`_figures` reads them) are numbers, not a computation, and one of them is stated
    by no source (``unstated``: neither the claim, nor another claim of the report, nor a supplied text, nor the task): the
    premise is the conjunct itself, scaled or with its terms moved across by the translation's own figures, so the engine
    checks only the translation's arithmetic, never the claim's. A premise whose extra figures some source states ("2x + 3
    = 7" written on an earlier line, beside "x = 2"; "p = 1.60" beside "p × 100 = 160") is a derivation the engine checks,
    as before."""
    extra = written - figures
    if not extra or not all(isinstance(v, Fraction) for v in extra):
        return False
    return any(unstated(v) for v in extra)


def _figures(node: dict) -> frozenset:
    """The numbers a term writes outside its closed arithmetic, as exact values, 0, 1 and -1 left out (a factor of 1 or a
    term of 0 adds no figure): "x − 4 > 0" and "x > 4" both write 4, while "p × 100 = 160" writes figures "p = 1.60" does
    not, so it is a computation the engine checks, not a restatement."""
    from fractions import Fraction
    out: set = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        op = n.get("op")
        if op in _LITERAL:
            try:
                v = Fraction(str(n.get("value")))
            except (ValueError, ZeroDivisionError):
                continue
            if abs(v) not in (0, 1):
                out.add(abs(v))
            continue
        if op in _ARITH and not _vars(n):
            if op == "div" and n.get("right", {}).get("op") in _LITERAL:
                stack.extend([n["left"], n["right"]])  # a closed value divided by a number, as the abstraction reads it
            elif op == "neg" and n.get("arg", {}).get("op") in _LITERAL:
                stack.append(n["arg"])
            else:
                out.add(_key(n))  # a closed term is one opaque value
            continue
        for k, v in n.items():
            if isinstance(v, dict):
                stack.append(v)
            elif isinstance(v, list):
                stack.extend(x for x in v if isinstance(x, dict))
    return frozenset(out)


def _is_number(node: dict) -> bool:
    return node.get("op") in _LITERAL or (node.get("op") == "neg" and node.get("arg", {}).get("op") in _LITERAL)


def _assigns_values(node: dict, *, structural: bool = True) -> bool:
    """Whether ``node`` only gives symbols values ("k = 50", "area = 1 and n = 20"): a task figure presented as given, never
    a relation or a computation the engine checks. With ``structural=False`` a value 0 or 1 (a structural figure no check
    reads in its source) does not count."""
    from fractions import Fraction
    parts = _plain_conjuncts(node)
    for p in parts:
        if p.get("op") != "eq":
            return False
        if p["left"].get("op") == "var" and _is_number(p["right"]):
            num = p["right"]
        elif p["right"].get("op") == "var" and _is_number(p["left"]):
            num = p["left"]
        else:
            return False
        if not structural:
            lit = num["arg"] if num.get("op") == "neg" else num
            try:
                if abs(Fraction(str(lit.get("value")))) in (0, 1):
                    return False
            except (ValueError, ZeroDivisionError):
                return False
    return bool(parts)


def _follows_without(problem: Problem, removed: set[str]) -> Optional[bool]:
    """Whether the conclusion still follows from the premises outside ``removed`` (None when undecided)."""
    kept = [p for p in problem.premises if p.id not in removed]
    data = problem.model_dump(mode="json", exclude_none=True)
    data["premises"] = [p.model_dump(mode="json", exclude_none=True) for p in kept]
    try:
        compiled = compile_problem(Problem.model_validate(data))
        if compiled.conclusion is None:
            return None
        solver = z3.Solver(ctx=compiled.ctx)
        solver.set("rlimit", RESTATEMENT_RLIMIT * 4)
        for term in compiled.premises.values():
            solver.add(term)
        solver.add(z3.Not(compiled.conclusion))
        r = solver.check()
    except Exception:
        return None
    if r == z3.unsat:
        return True
    if r == z3.sat:
        return False
    return None


def _standing(grounding, expr: dict, located: bool) -> str:
    """``data`` (a check verified it, or located its excerpt), ``own`` (the writer's own: no grounding, an inferential
    kind, a refuted grounding, an unverified figure or quotation, a task label on content no check reads: a Boolean
    statement, a relation or a structural figure 0 or 1) or ``label`` (a task label on figures, or a source label, that no
    check verified: the engine lists it as an unverified dependency, as before)."""
    g = grounding
    if g is None or g.kind in ("assumption", "specialist_inference", "general_knowledge"):
        return "own"
    if g.verified is True or located:
        return "data"  # a located excerpt whose figures the check refutes is the grounding check's finding, not a circle
    if g.verified is False:
        return "own"
    if g.kind in ("arithmetic_fact", "quotation"):
        return "own"
    if g.kind in ("task_setting", "rubric_rule"):
        return "label" if _assigns_values(expr, structural=False) else "own"
    return "label"


def semantic_restatement(problem: Problem, located: frozenset[str] | set[str] = frozenset(), claim_text: Optional[str] = None, *,
                         unstated: Optional[Callable[[Fraction], bool]] = None, prior_texts=()) -> Optional[Restatement]:
    """The full or partial restatement of ``problem``'s conclusion this module's rules find (see the module docstring), or
    None. ``located`` names the premises whose cited excerpt the grounding check located in a supplied text: such a premise
    is presented with its source, so restating it is a transcription check (whether it transcribes its figures is the
    grounding check's own finding), never the claim assumed. With ``claim_text`` (the claim the problem encodes) the rules
    ``result-asserted`` and ``consequence-asserted`` read it too. With ``unstated`` (whether no source of the claim states a
    value: the claim, the report's other claims, the supplied texts, the task) rule ``unstated-scaling`` reads a premise
    that is a conjunct scaled by figures of the translation's own (:func:`_scaled_by_unstated`); without it that rule does
    not apply. ``prior_texts`` (the claim's previous lines of working: the report's claims before it and the claims it cites)
    lets rule ``previous-line-step`` exempt the input of the step the claim writes from them (:func:`_previous_line_step`).
    The caller sets aside premises that contradict each other and a conclusion that holds alone."""
    if problem.query != "entailment" or problem.conclusion is None or not problem.premises:
        return None
    checker = _Checker(problem)
    conjuncts = [c for c in _nnf_conjuncts(_dump(problem.conclusion.expr)) if not checker.valid(c)]
    if not conjuncts:
        return None
    premises = [(p.id, _dump(p.expr), p.grounding) for p in problem.premises]
    results = calculation_results(claim_text) if claim_text else ()
    restated: dict[int, list[tuple[str, str]]] = {}
    for i, k in enumerate(conjuncts):
        for pid, expr, _g in premises:
            how = _restates(checker, expr, k, unstated)
            if how is None and results:
                how = _result_restates(checker, expr, k, results)
            if how is not None:
                restated.setdefault(i, []).append((pid, how))
    by_id = {pid: g for pid, _e, g in premises}
    exprs = {pid: e for pid, e, _g in premises}

    def standing(pid: str) -> str:
        return _standing(by_id.get(pid), exprs[pid], pid in located)

    restated = _without_exempt(problem, conjuncts, restated, exprs, checker, claim_text, prior_texts)
    found = _restated(problem, conjuncts, restated, by_id, exprs, standing) if restated else None
    if found is None and claim_text:
        found = _asserted_consequence(problem, claim_text, by_id, exprs, standing, frozenset(located), checker=checker)
    return found


# ------------------------------------------------------------------------------------------------------- exemptions
# Round-8 clearance c1 (the translation-fidelity lens judged maa-t14 m6.1 and cs-t14 c18.2 faithful step checks, the transfer
# auditor's rules stated-step and definitional-identity exempt them, and the committed end-to-end fixture cs_entailed and the
# argument-diagnosis cases packed in one premise need them): a premise the readings above name only in another form than as
# written is no restatement when it only NAMES an expression the conclusion is an identity of, or when it is the input of the
# step the claim itself states.

#: The words and signs with which a claim draws a step's result from its stated input ("x − 4 > 0, so x > 4").
_STEP_MARKER_RE = re.compile(r"(?:,[ \t]*|[ \t])(?:so|therefore|hence|thus|giving|gives)\b|⇒|=>|∴", re.IGNORECASE)
#: A claim longer than this is not read for its stated step (the exemption then applies to nothing).
_STEP_TEXT_MAX = 4_000
_TEXT_SIGNS = {"−": "-", "–": "-", "×": "*", "·": "*", "⋅": "*", "≥": ">=", "≤": "<=", "÷": "/"}
_REL_SIGNS = {"eq": "=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}


def _substituted(node, name: str, value: dict):
    """``node`` (IR JSON) with every ``var`` named ``name`` replaced by ``value`` (data only)."""
    if isinstance(node, dict):
        if node.get("op") == "var" and node.get("name") == name:
            return value
        return {k: (_substituted(v, name, value) if k != "value" else v) for k, v in node.items()}
    if isinstance(node, list):
        return [_substituted(v, name, value) for v in node]
    return node


def _definitional_identity(problem: Problem, pid: str, exprs: dict[str, dict], checker: "_Checker") -> bool:
    """Whether premise ``pid`` only NAMES an expression (``v iff E`` or ``v = E``, ``E`` over other symbols, ``v`` in no
    other premise and in the conclusion) and the conclusion with ``v`` replaced by ``E`` holds for every assignment: the
    claim is an identity of the named expression (a simplification, a circuit's case analysis), which the engine checks
    (the transfer auditor's rule ``definitional-identity``). A value given a name (``v = 5``) is no definition."""
    expr = exprs.get(pid) or {}
    if expr.get("op") not in ("iff", "eq") or problem.conclusion is None:
        return False
    conclusion = _dump(problem.conclusion.expr)
    for name_side, value_side in (("left", "right"), ("right", "left")):
        v, e = expr.get(name_side), expr.get(value_side)
        if not (isinstance(v, dict) and v.get("op") == "var" and isinstance(e, dict)):
            continue
        name = str(v.get("name"))
        others = _vars(e)
        if name in others or not others or name not in _vars(conclusion):
            continue
        if any(name in _vars(other) for q, other in exprs.items() if q != pid):
            continue
        if checker.valid(_substituted(conclusion, name, e)):
            return True
    return False


def _number_text(value: Fraction) -> str:
    """An exact number as a claim writes it: a whole number, a terminating decimal, else ``a/b``."""
    if value.denominator == 1:
        return str(value.numerator)
    den, twos, fives = value.denominator, 0, 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    if den != 1:
        return f"{value.numerator}/{value.denominator}"
    places = max(twos, fives)
    text = f"{abs(value) * 10 ** places:.0f}"
    text = text.rjust(places + 1, "0")
    out = (text[:-places] + "." + text[-places:]).rstrip("0").rstrip(".")
    return ("-" if value < 0 else "") + out


def _render(node: dict, depth: int = 0) -> Optional[str]:
    """A comparison or term over symbols and numbers as a claim may write it, with no blanks ("x+4>0"), or None for
    anything else (bounded; nothing is evaluated)."""
    if depth > 24 or not isinstance(node, dict):
        return None
    op = node.get("op")
    if op == "var":
        return str(node.get("name"))
    value = _number_value(node)
    if value is not None:
        return _number_text(value)
    if op in _REL_SIGNS:
        left, right = _render(node.get("left"), depth + 1), _render(node.get("right"), depth + 1)
        return None if left is None or right is None else left + _REL_SIGNS[op] + right
    if op in ("add", "mul"):
        parts = [_render(a, depth + 1) for a in node.get("args", [])]
        if not parts or any(p is None for p in parts):
            return None
        if op == "mul":
            parts = [f"({p})" if any(c in p for c in "+-") else p for p in parts]
        return ("+" if op == "add" else "*").join(parts)
    if op in ("sub", "div"):
        left, right = _render(node.get("left"), depth + 1), _render(node.get("right"), depth + 1)
        if left is None or right is None:
            return None
        if op == "div" and any(c in right for c in "+-*/"):
            right = f"({right})"
        return left + ("-" if op == "sub" else "/") + right
    if op == "neg":
        arg = _render(node.get("arg"), depth + 1)
        return None if arg is None else "-" + arg
    return None


def _canon_text(text: str) -> str:
    """``text`` with its signs written one way and no blanks, for :func:`_stated_step`."""
    out = "".join(_TEXT_SIGNS.get(ch, ch) for ch in text)
    return "".join(out.split())


def _stated_step(claim_text: Optional[str], premise: dict, conjuncts: list[dict]) -> bool:
    """Whether ``premise`` (IR JSON) is the input of the step the claim states (the transfer auditor's rule
    ``stated-step``): the claim writes each conjunct of the premise before its first step marker ("so", "therefore",
    "hence", "thus", "giving", ⇒, ∴) and each restated ``conjunct`` after it, and none of those conjuncts before it (a claim
    that writes "x > 4, so x > 4" states no step). The engine then checks the claim's own step from its stated input. Read
    on the text as written (signs written one way, blanks dropped); a form the reader cannot render exempts nothing."""
    if not claim_text or len(claim_text) > _STEP_TEXT_MAX or not conjuncts:
        return False
    m = _STEP_MARKER_RE.search(claim_text)
    if m is None:
        return False
    before, after = _canon_text(claim_text[:m.start()]), _canon_text(claim_text[m.end():])
    inputs = [_render(q) for q in _plain_conjuncts(premise)]
    results = [_render(c) for c in conjuncts]
    if not inputs or any(x is None for x in inputs + results):
        return False
    return all(x in before for x in inputs) and all(r in after for r in results) and not any(r in before for r in results)


def _loose(text: str) -> str:
    """``text`` in :func:`_canon_text`'s form with the multiplication signs and brackets dropped as well, so a relation reads
    alike however a writer groups or juxtaposes it ("36 − 4k > 0" and the rendering "36-4*k>0"; "x + 1 = (x − 3)/2" and
    "x+1=x-3/2")."""
    return _canon_text(text).replace("*", "").replace("(", "").replace(")", "")


#: How many claims before a claim are read as its previous lines of working (the transfer auditor's ``PRIOR_LINES``).
PRIOR_LINES = 3


def _previous_line_step(prior_texts, claim_text: Optional[str], premise: dict, conjuncts: list[dict]) -> bool:
    """Rule ``previous-line-step`` (round-9 clearance c2, second fix pass; the translation-fidelity lens: maa-t15 m2.4 "4k <
    36" from m2.3 "36 − 4k > 0", and m7.2 "2x + 2 = x − 3" from m7.1 "x + 1 = (x − 3)/2", faithful step checks refused as
    restatements; the transfer auditor's rule ``stated-input`` exempts the same): whether ``premise`` (IR JSON) is the input of
    the step the claim writes, written on the claim's previous lines of working (``prior_texts``: the claims before it in the
    report and the claims it cites) and not in the claim itself, while the claim writes each restated ``conjunct``. Read on the
    texts as written (:func:`_loose`); a form the reader cannot render exempts nothing, and a claim that writes its input
    again states no step. The engine then checks the claim's own step from its stated previous line."""
    if not claim_text or len(claim_text) > _STEP_TEXT_MAX or not conjuncts:
        return False
    priors = [_loose(t) for t in prior_texts if t and len(t) <= _STEP_TEXT_MAX]
    if not priors:
        return False
    inputs = [_render(q) for q in _plain_conjuncts(premise)]
    results = [_render(c) for c in conjuncts]
    if not inputs or any(x is None for x in inputs + results):
        return False
    own = _loose(claim_text)
    loose_inputs = [_loose(x) for x in inputs]  # type: ignore[arg-type]
    loose_results = [_loose(r) for r in results]  # type: ignore[arg-type]
    if any(x in own for x in loose_inputs) or not all(r in own for r in loose_results):
        return False
    return all(any(x in p for p in priors) for x in loose_inputs)


def _without_exempt(problem: Problem, conjuncts: list[dict], restated: dict[int, list[tuple[str, str]]], exprs: dict[str, dict],
                    checker: "_Checker", claim_text: Optional[str], prior_texts=()) -> dict[int, list[tuple[str, str]]]:
    """``restated`` without the rows of a premise that is a definitional identity, the claim's stated step input, or the
    input of the step the claim writes from its previous line (``prior_texts``, rule ``previous-line-step``); a premise
    that restates a conjunct as written is never exempt."""
    if not restated:
        return restated
    ways: dict[str, set[str]] = {}
    for rows in restated.values():
        for pid, way in rows:
            ways.setdefault(pid, set()).add(way)
    exempt: set[str] = set()
    for pid, kinds in ways.items():
        if "as written" in kinds:
            continue
        mine = [conjuncts[i] for i, rows in restated.items() if any(p == pid for p, _w in rows)]
        if _definitional_identity(problem, pid, exprs, checker) or _stated_step(claim_text, exprs[pid], mine) \
                or _previous_line_step(prior_texts, claim_text, exprs[pid], mine):
            exempt.add(pid)
    if not exempt:
        return restated
    out = {i: [(p, w) for p, w in rows if p not in exempt] for i, rows in restated.items()}
    return {i: rows for i, rows in out.items() if rows}


def _restated(problem: Problem, conjuncts: list[dict], restated: dict[int, list[tuple[str, str]]], by_id: dict, exprs: dict[str, dict],
              standing) -> Optional[Restatement]:
    """The full or partial restatement the rows ``restated`` (conjunct index -> restating premises) show, or None."""
    how = tuple((pid, way, _key(conjuncts[i])) for i, rows in sorted(restated.items()) for pid, way in rows)
    if len(restated) == len(conjuncts):
        own = {pid for rows in restated.values() for pid, _w in rows if standing(pid) == "own"}
        # a conjunct with a restating premise that is no writer's own (data, or a label the engine lists as unverified) is a
        # transcription check; one restated only by the writer's own premises is assumed
        if not own or all(any(standing(pid) != "own" for pid, _w in rows) for rows in restated.values()):
            return None
        if _follows_without(problem, own) is True:
            return None  # redundant: the other premises derive the conclusion too
        return Restatement("full", tuple(sorted(own)), tuple(h for h in how if h[0] in own))
    task_given = {pid for rows in restated.values() for pid, _w in rows
                  if standing(pid) == "own" and by_id.get(pid) is not None and by_id[pid].kind in _TASK_GIVEN and _assigns_values(exprs[pid])}
    if not task_given:
        return None
    if _follows_without(problem, task_given) is True:
        return None
    return Restatement("partial", tuple(sorted(task_given)), tuple(h for h in how if h[0] in task_given))


# --------------------------------------------------------------------------------------------- rule result-asserted

#: A value is read as the result a calculation states when it lies within this share of it (the stated figure's band).
_RESULT_BAND = Fraction(1, 100)


def _number_value(node: dict) -> Optional[Fraction]:
    """The exact value of a numeral node (``int``, ``real`` or the negation of one), or None."""
    neg = node.get("op") == "neg"
    lit = node.get("arg", {}) if neg else node
    if lit.get("op") not in _LITERAL:
        return None
    try:
        v = Fraction(str(lit.get("value")))
    except (ValueError, ZeroDivisionError):
        return None
    return -v if neg else v


def _literal_values(node: dict) -> list[Fraction]:
    """Every numeral a term writes, as exact values (one pass)."""
    out: list[Fraction] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            v = _number_value(n)
            if v is not None:
                out.append(v)
                continue
            stack.extend(v for k, v in n.items() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(n)
    return out


def calculation_results(claim_text: Optional[str]) -> tuple[tuple[Fraction, str], ...]:
    """``(value, written)`` for every figure ``claim_text`` states as the result of a calculation it writes
    (``quantities._calculation_result``: "(5.000 × 10⁶ m)³ = 1.250 × 10²⁰ m³", "1 ÷ 8.40 = US$0.1190"), each as written and
    in its SI unit or ratio ("25%" also as 1/4). One pass over the text's figures."""
    from .quantities import SourceText, _calculation_result, figures_in, sentence_of
    text = claim_text or ""
    out: list[tuple[Fraction, str]] = []
    for f in figures_in(SourceText("claim", "claim", text)):
        if _calculation_result(text, f, sentence_of(text, f.start, f.end)) is None:
            continue
        values = {f.scaled}
        if f.unit_factor not in (None, 1):
            values.add(f.scaled * f.unit_factor)
        out += [(v, f.written) for v in sorted(values)]
    return tuple(out)


def _result_restates(checker: _Checker, premise: dict, conjunct: dict, results: tuple[tuple[Fraction, str], ...]) -> Optional[str]:
    """How ``premise`` restates ``conjunct`` by asserting the result of a calculation the claim writes (rule
    ``result-asserted``), or None: the premise only gives symbols values, the conjunct mentions only symbols it assigns,
    one assigned value is such a result, every numeral of the conjunct lies within :data:`_RESULT_BAND` of it (a check of
    that figure's band, not of a further quantity) and the conjunct follows from the premise alone."""
    if not _assigns_values(premise):
        return None
    assigned: dict[str, Fraction] = {}
    for part in _plain_conjuncts(premise):
        var, num = (part["left"], part["right"]) if part["left"].get("op") == "var" else (part["right"], part["left"])
        v = _number_value(num)
        if v is None:
            return None
        assigned[var["name"]] = v
    names = _vars(conjunct)
    if not names or not names <= set(assigned):
        return None
    figures = _literal_values(conjunct)
    for name in sorted(names):
        value = assigned[name]
        written = next((w for r, w in results if r == value), None)
        if written is None or not figures or any(abs(f - value) > abs(value) * _RESULT_BAND for f in figures):
            continue
        if checker.unsat([premise, {"op": "not", "arg": conjunct}]) is True:
            return (f"by asserting the result its written calculation states ('{written[:60]}') as a value, so the engine checks only that "
                    "the result rounds to itself and never computes the calculation (rule result-asserted)")
    return None


# ----------------------------------------------------------------------------------------- rule consequence-asserted

#: Cues after which the claim states the consequence it draws ("..., so A", "therefore A", "it follows that A").
_CONSEQUENCE_AFTER = lexis.cue_table(("so", "therefore", "thus", "hence", "consequently", "it follows that", "which means", "this means"))
#: Cues before which the claim states the consequence and after which its reason ("A because R").
_CONSEQUENCE_BEFORE = lexis.cue_table(("because",))
#: Words after which "so" is no connective ("so that", "so far", "so much", "so as to").
_SO_NOT_CONNECTIVE = frozenset({"that", "far", "much", "many", "long", "as", "on", "called", "too", "to", "few", "little", "often", "well"})
#: Marks before a clause-opening "so" (", so", "; so", "and so").
_SO_OPENERS = ",;:—–("
#: The sentence marks that end a clause for this reader ("." between digits is a decimal point).
_CLAUSE_END = frozenset(".!?;")
#: A label's leading claim id ("h1.12:", "h1.10 (supporting):", "g2.3@business-management-specialist:").
_LABEL_ID_RE = re.compile(r"\s{0,4}([A-Za-z]{1,4}[0-9]{1,4}(?:[.-][A-Za-z0-9]{1,12}){0,4}(?:@[A-Za-z0-9_-]{1,64})?)(?:\s{0,4}\([^()\n]{0,60}\))?\s{0,4}:\s")
#: The least content stems a premise shares with the consequence clause (and two thirds of its words outside the reason).
_MIN_SHARED = 3


def _clause_ends(text: str) -> list[int]:
    n = len(text)
    return [k for k, ch in enumerate(text) if ch in _CLAUSE_END and not (ch == "." and 0 < k < n - 1 and text[k - 1].isdigit() and text[k + 1].isdigit())]


def consequence_clauses(claim_text: Optional[str]) -> Optional[tuple[frozenset[str], frozenset[str], tuple[str, ...]]]:
    """``(reason stems, consequence stems, consequence clauses)`` of the first consequence cue of each sentence of
    ``claim_text`` (:data:`_CONSEQUENCE_AFTER`, :data:`_CONSEQUENCE_BEFORE`; quotations masked), or None when it draws no
    consequence. A "so" counts only where it opens a clause (after a comma, semicolon, colon, dash or "and", or at a
    sentence start) and is not "so that", "so far" and the like; "because of" is a cause phrase. One pass over the text:
    the tokens, the cues and the clause ends are each read once, and each token is read in one sentence."""
    from .diag_argument import mask_quotations
    text = claim_text or ""
    masked = mask_quotations(text)
    spans = lexis.token_spans(masked)
    if not spans:
        return None
    toks = tuple(t for _s, _e, t in spans)
    starts = [s for s, _e, _t in spans]
    ends = _clause_ends(masked)
    reason: set[str] = set()
    consequence: set[str] = set()
    shown: list[str] = []
    seen: set[int] = set()
    cues = [(i, c, False) for i, c in lexis.find_cues(toks, _CONSEQUENCE_AFTER)] + [(i, c, True) for i, c in lexis.find_cues(toks, _CONSEQUENCE_BEFORE)]
    for i, cue, before in sorted(cues):
        at = spans[i][0]
        sentence = bisect.bisect_left(ends, at)
        if sentence in seen:
            continue
        lo = ends[sentence - 1] if sentence > 0 else -1
        hi = ends[sentence] if sentence < len(ends) else len(masked)
        nxt = toks[i + len(cue)] if i + len(cue) < len(toks) and starts[i + len(cue)] < hi else ""
        if cue == ("so",):
            if nxt in _SO_NOT_CONNECTIVE:
                continue
            # the mark right before the cue, read backwards over the blanks before it only (each blank is read for one cue
            # at most: the scan stops at the token before it), never a copy of the sentence up to the cue
            j = at - 1
            while j > lo and masked[j].isspace():
                j -= 1
            if not (j <= lo or masked[j] in _SO_OPENERS or (i > 0 and toks[i - 1] == "and" and starts[i - 1] > lo)):
                continue
        if cue == ("because",) and nxt == "of":
            continue
        k0 = bisect.bisect_right(starts, lo)
        k1 = bisect.bisect_left(starts, hi)
        first, last = toks[k0:i], toks[i + len(cue):k1]
        cons, rea = (first, last) if before else (last, first)
        if not cons:
            continue
        seen.add(sentence)
        reason |= set(lexis.content_stems(rea))
        consequence |= set(lexis.content_stems(cons))
        a, stop = (k0, at) if before else (i + len(cue), hi)
        if a < len(spans) and spans[a][0] < stop:
            shown.append(" ".join(text[spans[a][0]:stop].split()).rstrip(" ,;:.!?")[:200])
    if not consequence:
        return None
    return frozenset(reason), frozenset(consequence), tuple(shown)


def _own_words(label: Optional[str], claim_id: str) -> Optional[str]:
    """The words of a premise's label after a leading claim id, when the id is the claim's own or absent; None when the
    label names another claim ("h1.10 (supporting): ..."), whose content is that claim's, not this one's."""
    text = label or ""
    m = _LABEL_ID_RE.match(text)
    if m is None:
        return text
    own = {claim_id, claim_id.split("@", 1)[0]}
    if m.group(1) not in own and m.group(1).split("@", 1)[0] not in own:
        return None
    return text[m.end():]


def _is_link(node: dict, sorts: dict[str, str]) -> bool:
    """Whether a premise states a link (an implication, a biconditional, a disjunction, an equivalence of propositions)
    rather than a fact."""
    op = node.get("op")
    if op in ("implies", "iff", "or"):
        return True
    if op == "not":
        return _is_link(node.get("arg", {}), sorts)
    if op == "and":
        return any(_is_link(a, sorts) for a in node.get("args", []))
    if op in ("eq", "ne"):
        return any((s.get("op") == "var" and sorts.get(s.get("name")) == "Bool") or s.get("op") in ("and", "or", "not", "implies", "iff", "bool")
                   for s in (node.get("left", {}), node.get("right", {})))
    return False


#: The grounding kinds of a writer's own step (``engine.argument_cues.WRITER_STEP_KINDS``; None is no grounding): a fact stated
#: from subject knowledge ("the total energy is kinetic plus potential energy") is a rule the encoding applies, never the
#: consequence the claim draws.
_STEP_KINDS = frozenset({None, "specialist_inference", "assumption"})


def _asserted_consequence(problem: Problem, claim_text: str, by_id: dict, exprs: dict[str, dict], standing,
                          located: frozenset[str] = frozenset(), *, checker: Optional["_Checker"] = None) -> Optional[Restatement]:
    """Rule ``consequence-asserted`` (module docstring): the premises of the writer's own steps (:data:`_STEP_KINDS`, no
    check verifying them and no excerpt of theirs located: a source that states the consequence makes it data) that state,
    as a fact, the consequence the claim draws, when the conclusion needs them; or None."""
    clauses = consequence_clauses(claim_text)
    if clauses is None:
        return None
    reason, consequence, shown = clauses
    sorts = {s.name: s.sort for s in problem.symbols}
    glosses = {s.name: s.meaning or "" for s in problem.symbols}
    hits: list[str] = []
    for p in problem.premises:
        expr = exprs[p.id]
        g = by_id.get(p.id)
        if (g.kind if g is not None else None) not in _STEP_KINDS or (g is not None and g.verified is True) or p.id in located:
            continue
        if standing(p.id) != "own" or _is_link(expr, sorts) or _assigns_values(expr):
            continue
        if checker is not None and _definitional_identity(problem, p.id, exprs, checker):
            continue  # a definition the conclusion is an identity of names an expression; it asserts no consequence
        words = _own_words(p.label, problem.claim_id)
        if words is None:
            continue
        if not words.strip():
            words = " ".join(glosses.get(n, "") for n in sorted(_vars(expr)))
        stems = set(lexis.content_stems(words)) - reason
        shared = stems & consequence
        if len(shared) >= _MIN_SHARED and 3 * len(shared) >= 2 * len(stems):
            hits.append(p.id)
    if not hits or _follows_without(problem, set(hits)) is not False:
        return None
    clause = shown[0] if shown else ""
    return Restatement("consequence", tuple(sorted(hits)), tuple((pid, "states the consequence the claim draws as a fact", clause) for pid in sorted(hits)))
