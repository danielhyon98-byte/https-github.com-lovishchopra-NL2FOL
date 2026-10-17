"""Whether the source asserts what an under-determined encoding leaves open.

Two encoding shapes leave a figure open: a premise that only DEFINES an atom by a comparison of a figure no other
premise mentions (``b <-> (n = 17)``, the engine's E110 shape), and a conclusion that compares symbols no premise
mentions (``x < y`` with ``y`` free, the E111 shape). Either can be a translation that omitted what the source
asserts, or the faithful encoding of a question that leaves the figure open on purpose ("define b iff n = 17:
does b necessarily hold?"; "for an arbitrary integer y"; "if n equals 17, b holds; so b necessarily holds").
Formula shape alone cannot tell the two apart, and neither can the presence of a numeral in the source, so the
translation layer reads what the sources STATE about the figure (:mod:`.assertion`):

* a definition's figure is **source-asserted** when a source (the claim, a supporting claim, a supplied text, the
  task record) states that figure as a fact: in a clause the reader POSITIVELY recognises as the writer's own
  statement (not a question, a condition, a supposition, a hypothesis, a definition, a possibility or hedge, reported
  speech, a claim put forward to be tested, a negation, a quantification or a disjunction, nor a symbolic implication
  or biconditional, and not one end of a range; a construction the reader does not recognise asserts nothing); with what
  the definition compares (a source's "more than 17" asserts no ``n = 17``; its "nearly 790,000" asserts ``n <
  790000``); and about the definition's symbols (the clause names them as a formula does, or shares the words that
  describe them: their meanings, the definition's label, the source's own clauses that name them);
* a free conclusion symbol is **source-constrained** when a source (the claim, a supporting claim, a supplied text, the
  task record) asserts, about that symbol, a figure that no literal of the encoding corresponds to (the encoding omitted
  it); dates are no such figure, and neither is a figure that counts something else ("I checked 3 values"). A figure of
  a supplied text or of the task must be in a clause about the symbol (it names it, counts what describes it, or shares
  the words that describe it); the answer's own figures may also link by their value alone when nothing describes it.

Only then is the engine's counterexample no verdict on the claim (the pipeline rejects the definition shape and
feeds back the source evidence; the outcome layer withholds an E110 or E111 counterexample). Otherwise the
counterexample stands, with a :class:`~.contracts.CoverageNote` as an advisory coverage warning that names the
mentions it found and why none asserts the figure. A translator is never told to add a premise because adding it
would produce entailment: only because a source asserts it; and a retry may add only that (the pipeline checks it).

One decision, two records. The engine cannot see the sources, so the pipeline hands this decision to it as an
application record (:func:`apply_coverage_evidence`): every symbol an under-determined shape leaves open gets its
``verified`` flag from this check alone. A figure the source asserts carries a grounding verified in this process
with the asserting clauses as its references (the engine then reports ``E110``/``E111``: no verdict); any other
symbol of the shape carries no verified grounding, even when the grounding check located the translator's own
excerpt for it (a located sentence that defines, supposes or conditions the figure is no evidence that the source asserts it),
so the engine reports the advisory ``W110``/``W111`` and the counterexample stands. The signed engine result, the
pipeline's rejection, the outcome's display and the release check therefore always agree.

Notes are bound to :func:`coverage_digest`, a digest of the problem's formulas (labels and grounding flags aside),
so a note always describes the formulas it was computed for.
"""
from __future__ import annotations

import json
from fractions import Fraction
from typing import Optional, Sequence

from ..engine.runner import FigureDefinition
from ..ir.canonical import sha256_hex
from ..ir.schema import Grounding, GroundingKind, Problem, SourceRef
from .assertion import Target, asserting_clause, assertion_at, content_words, describing_units, link, relation_at, relation_implies
from .common import truncate
from .contracts import CoverageNote, GroundingCheck
from .quantities import TRIVIAL_VALUES, SourceText, declared_reading, figures_in, is_year_like, literal_matches

__all__ = ["coverage_digest", "assess_definitions", "assess_unconstrained", "source_asserted", "asserting_spans", "apply_coverage_evidence",
           "free_conclusion_symbols", "definition_target"]

_NUMERIC = frozenset({"Int", "Real"})
#: The grounding kind an evidence record takes when the symbol had no grounding of its own, by the source that asserts it:
#: a supplied text, the task record, or the specialist's own answer (the claim and its supporting claims).
_EVIDENCE_KIND: dict[str, GroundingKind] = {"supplied_text": "supplied_text", "task": "task_setting", "claim": "specialist_inference",
                                            "supporting_claim": "specialist_inference"}


def coverage_digest(problem: Problem) -> str:
    """sha256 over the problem's query, symbol sorts and assertion expressions: what an encoding leaves open depends on
    its formulas only, so labels, glosses and grounding flags do not change it."""
    data = {
        "query": problem.query,
        "symbols": sorted((s.name, s.sort) for s in problem.symbols),
        "premises": [(p.id, p.expr.model_dump(mode="json", exclude_none=True)) for p in problem.premises],
        "conclusion": None if problem.conclusion is None else (problem.conclusion.id, problem.conclusion.expr.model_dump(mode="json", exclude_none=True)),
    }
    return sha256_hex(json.dumps(data, sort_keys=True, separators=(",", ":")))


def _vars(expr) -> set[str]:
    """Every symbol name ``expr`` mentions (an iterative walk)."""
    out: set[str] = set()
    stack = [expr]
    while stack:
        node = stack.pop()
        if getattr(node, "op", None) == "var":
            out.add(node.name)  # type: ignore[attr-defined]
            continue
        for key in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(node, key, None)
            if child is not None:
                stack.append(child)
        stack.extend(getattr(node, "args", None) or ())
    return out


def _expr_literals(expr, keep_compared: frozenset[str] = frozenset()) -> list[tuple[str, Fraction, Optional[str]]]:
    """``(literal as written, value, symbol it is compared with)`` for every non-trivial numeric literal of ``expr``, and
    for a trivial one (0, 1, 10, 100, 1000) compared directly with a symbol in ``keep_compared``: there it is the figure
    itself ("only one territory": ``n = 1``), not a constant a conversion brings in."""
    out: list[tuple[str, Fraction, Optional[str]]] = []
    stack: list[tuple[object, Optional[str]]] = [(expr, None)]
    while stack:
        node, compared = stack.pop()
        op = getattr(node, "op", None)
        if op in ("int", "real"):
            try:
                value = Fraction(node.value)  # type: ignore[attr-defined]
            except (ValueError, ZeroDivisionError):
                continue
            if abs(value) not in TRIVIAL_VALUES or compared in keep_compared:
                out.append((node.value, value, compared))  # type: ignore[attr-defined]
            continue
        if op in ("eq", "ne", "lt", "le", "gt", "ge"):
            left, right = node.left, node.right  # type: ignore[attr-defined]
            stack.append((left, right.name if getattr(right, "op", None) == "var" else None))
            stack.append((right, left.name if getattr(left, "op", None) == "var" else None))
            continue
        for key in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(node, key, None)
            if child is not None:
                stack.append((child, None))
        stack.extend((a, None) for a in (getattr(node, "args", None) or ()))
    return out


#: The relation a comparison states about its symbol, read from the symbol's side ("17 > n" is "n < 17").
_FLIPPED = {"eq": "eq", "ne": "ne", "lt": "gt", "le": "ge", "gt": "lt", "ge": "le"}


def _definition_literals(expr, figures: frozenset[str]) -> list[tuple[str, Fraction, Optional[str], Optional[str]]]:
    """``(literal as written, value, figure symbol it is compared with, what the comparison requires of that symbol)`` for
    every literal of a definition's comparison (:func:`_expr_literals` decides which literals count). The requirement is
    the comparison read from the symbol's side (``eq``, ``lt``, ``le``, ``gt``, ``ge``; ``eq`` for a literal compared with
    a compound term); it is ``None`` under a negation or a disjunction (or for ``ne``), where asserting the figure does
    not establish the defined atom, so no source statement of it is evidence that the encoding omitted an assertion."""
    out: list[tuple[str, Fraction, Optional[str], Optional[str]]] = []
    stack: list[tuple[object, bool]] = [(expr, True)]
    while stack:
        node, safe = stack.pop()
        op = getattr(node, "op", None)
        if op in ("eq", "ne", "lt", "le", "gt", "ge"):
            left, right = node.left, node.right  # type: ignore[attr-defined]
            for written, value, compared in _expr_literals(node, figures):
                if compared is not None and compared not in figures:
                    continue
                required: Optional[str] = None
                if safe and op != "ne":
                    if compared is not None and getattr(left, "op", None) == "var" and left.name == compared:  # type: ignore[attr-defined]
                        required = op
                    elif compared is not None and getattr(right, "op", None) == "var" and right.name == compared:  # type: ignore[attr-defined]
                        required = _FLIPPED[op]
                    else:
                        required = "eq"
                out.append((written, value, compared, required))
            continue
        if op in ("not", "or", "implies", "iff", "ite"):
            safe = False
        for key in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(node, key, None)
            if child is not None:
                stack.append((child, safe))
        stack.extend((a, safe) for a in (getattr(node, "args", None) or ()))
    return out


def _comparison_side(expr, atom: str):
    """The side of a definition ``atom <-> comparison`` that is not the atom."""
    left, right = getattr(expr, "left", None), getattr(expr, "right", None)
    if getattr(left, "op", None) == "var" and left.name == atom:  # type: ignore[union-attr]
        return right
    return left


def _ref(src: SourceText, start: int, end: int) -> SourceRef:
    """A reference to characters ``start``-``end`` of ``src`` (the claim, a supporting claim, a supplied text or the task)."""
    clause = src.text[start:end].strip(" ,;:\n\t")
    return SourceRef(document_id=src.ident[:200], locator=f"{src.kind} characters {start}-{end}"[:200], excerpt=clause[:2000] or None)


def asserting_spans(value: Fraction, meaning: Optional[str], sources: Sequence[SourceText], target: Optional[Target] = None,
                    relation: Optional[str] = None, passed_over: Optional[list[str]] = None) -> list[tuple[str, SourceRef]]:
    """``(description, reference)`` for each figure of ``sources`` equal to ``value`` (typed, in the reading ``meaning``
    declares) that its source ASSERTS (:func:`.assertion.assertion_at`: a clause that is no question, condition,
    supposition, definition, possibility, negation, quantification or disjunction, and the figure no end of a range); with
    ``relation``, only a figure stated so that it establishes that comparison (:func:`.assertion.relation_implies`: "more
    than 17" establishes no ``n = 17``); with ``target``, only a figure about those symbols (:func:`.assertion.link`). The
    reference is the asserting clause. Mentions of the value that are passed over are described in ``passed_over`` (with
    the construction that decided it) when a list is given."""
    declared = declared_reading(meaning)
    out: list[tuple[str, SourceRef]] = []
    for src in sources:
        matches, _ = literal_matches(value, figures_in(src), declared)
        # the reading of a clause is computed once per text and looked up per figure (linear in an untrusted text)
        refs: dict[tuple[int, int], SourceRef] = {}
        for m in matches:
            f = m.figure
            reading = assertion_at(src.text, f.start, f.end)
            unit = reading.unit
            if not reading.asserted:
                if passed_over is not None:
                    passed_over.append(f"{f.where()}: {reading.describe()}")
                continue
            if relation is not None:
                stated = relation_at(src.text, f.start, f.end)
                if not relation_implies(stated, relation):
                    if passed_over is not None:
                        passed_over.append(f"{f.where()}: states {stated}, not {relation}")
                    continue
            if target is not None and link(src.text, f.start, f.end, unit, target) is None:
                if passed_over is not None:
                    passed_over.append(f"{f.where()}: not about {', '.join(target.names[:3])}")
                continue
            clause = asserting_clause(src.text, f.start, f.end)
            if clause not in refs:
                refs[clause] = _ref(src, *clause)
            ref = refs[clause]
            out.append((f"{f.where()} in {(ref.excerpt or '')[:160]!r}", ref))
    return out


def source_asserted(value: Fraction, meaning: Optional[str], sources: Sequence[SourceText]) -> list[str]:
    """The spans of ``sources`` that assert a figure equal to ``value`` (typed, in the reading ``meaning`` declares): see
    :func:`asserting_spans`."""
    return [text for text, _ref in asserting_spans(value, meaning, sources)]


def definition_target(problem: Problem, d: FigureDefinition, sources: Sequence[SourceText]) -> Target:
    """What a figure must be about to be evidence for definition ``d``: its atom and figure symbols, described by their
    meanings, the label of the premise that defines them, and the source clauses that name them."""
    names = (d.atom, *d.figures)
    meanings = {s.name: s.meaning for s in problem.symbols}
    words: set[str] = set()
    for name in names:
        words |= content_words(meanings.get(name)) | content_words(name)
    words |= content_words(d.label)
    described, named = describing_units([s.text for s in sources], names)
    return Target(names=names, words=frozenset(words | described), named=named)


def assess_definitions(problem: Problem, defs: Sequence[FigureDefinition], sources: Sequence[SourceText]) -> list[CoverageNote]:
    """One note per unasserted figure definition: source-asserted when a source asserts one of its figures, with what the
    definition compares, about the definition's symbols (:func:`asserting_spans`)."""
    digest = coverage_digest(problem)
    meanings = {s.name: s.meaning for s in problem.symbols}
    by_id = {p.id: p for p in problem.premises}
    notes: list[CoverageNote] = []
    for d in defs:
        premise = by_id.get(d.premise_id)
        if premise is None:
            continue
        literals = _definition_literals(_comparison_side(premise.expr, d.atom), frozenset(d.figures))
        target = definition_target(problem, d, sources)
        spans: list[tuple[str, SourceRef]] = []
        passed: list[str] = []
        for written, value, compared, required in literals:
            if required is None:
                passed.append(f"literal {written}: under a negation or a disjunction, asserting the figure does not establish {d.atom}")
                continue
            spans += asserting_spans(value, meanings.get(compared) if compared else None, sources, target=target, relation=required, passed_over=passed)
        evidence = list(dict.fromkeys(text for text, _r in spans))
        refs = list({(r.document_id, r.locator): r for _t, r in spans}.values())
        asserted = bool(evidence)
        figures = [w for w, _v, _c, _r in literals]
        if asserted:
            detail = (f"premise {d.premise_id} defines {d.atom} by a comparison of {', '.join(d.figures)} that no premise asserts, while the source asserts "
                      f"it: {'; '.join(evidence[:3])}")
        else:
            seen = "; ".join(dict.fromkeys(passed)) if passed else "no source states the figure"
            detail = (f"premise {d.premise_id} defines {d.atom} by a comparison of {', '.join(d.figures)} that no premise asserts, and no source clause "
                      "asserts it (a clause that only defines, supposes, conditions, asks, allows, negates or quantifies a figure asserts nothing, nor does "
                      f"one about something else): {truncate(seen, 900)}. Leaving it open may be the question's own reading, so a counterexample that "
                      "reassigns it is the verdict on the encoding (advisory coverage warning)")
        notes.append(CoverageNote(kind="unasserted_definition", problem_digest=digest, assertion_ids=[d.premise_id], symbols=[d.atom, *d.figures],
                                  figures=figures, source_asserted=asserted, evidence=evidence[:8], detail=detail[:2000],
                                  source_refs=refs[:16] if asserted else [], evidence_symbols=list(d.figures) if asserted else []))
    return notes


#: The sources that are the specialist's own answer: their figures are about what the answer compares, so an asserted
#: figure of a symbol nothing describes links by its value alone (:func:`.assertion.link`). A supplied text or the task
#: record is read more strictly: its figure must be in a clause about the symbol (a name, a count or shared words).
_OWN_SOURCES = frozenset({"claim", "supporting_claim"})


def assess_unconstrained(problem: Problem, sources: Sequence[SourceText]) -> Optional[CoverageNote]:
    """A note when the conclusion compares numeric symbols no premise mentions: source-constrained when a source (the
    claim, a supporting claim, a supplied text, the task record) asserts, about one of those symbols, a figure no literal
    of the encoding corresponds to (see :func:`asserting_spans`; a figure that counts something else, "I checked 3
    values", is about no symbol). The answer's own figures link to a symbol as before (by its value when nothing describes
    it); a figure of a supplied text or of the task links only when its clause is about the symbol: it names it ("Here x =
    5 and y = 9."), counts what describes it, or shares the words that describe it (:data:`_OWN_SOURCES`)."""
    if problem.conclusion is None or problem.query != "entailment" or not problem.premises:
        return None
    sorts = {s.name: s.sort for s in problem.symbols}
    meanings = {s.name: s.meaning for s in problem.symbols}
    premise_vars: set[str] = set()
    for p in problem.premises:
        premise_vars |= _vars(p.expr)
    free = sorted(v for v in _vars(problem.conclusion.expr) - premise_vars if sorts.get(v) in _NUMERIC)
    if not free:
        return None
    own_texts = [s.text for s in sources if s.kind in _OWN_SOURCES]
    all_texts = [s.text for s in sources]
    own_targets: dict[str, Target] = {}
    record_targets: dict[str, Target] = {}
    for v in free:
        base = content_words(meanings.get(v)) | content_words(v)
        described, named = describing_units(own_texts, (v,))
        own_targets[v] = Target(names=(v,), words=base | described, named=named)
        if len(own_texts) < len(all_texts):
            described, named = describing_units(all_texts, (v,))
            record_targets[v] = Target(names=(v,), words=base | described, named=named)
    literals = [v for a in [*problem.premises, problem.conclusion] for _w, v, _c in _expr_literals(a.expr)]
    omitted: list[str] = []
    passed: list[str] = []
    stated: list[str] = []
    refs: dict[tuple[str, str], SourceRef] = {}
    for src in sources:
        own = src.kind in _OWN_SOURCES
        targets = own_targets if own else record_targets
        for f in figures_in(src):
            if is_year_like(f) or (abs(f.value) in TRIVIAL_VALUES and f.scale == 1 and not f.is_percent_like):
                continue
            if any(literal_matches(v, [f])[0] for v in literals):
                continue
            reading = assertion_at(src.text, f.start, f.end)
            if not reading.asserted:
                passed.append(f"{f.where()}: {reading.describe()}")
                continue
            about = [v for v in free if link(src.text, f.start, f.end, reading.unit, targets[v], value_only=own) is not None]
            if not about:
                passed.append(f"{f.where()}: not about {', '.join(free)}")
                continue
            ref = _ref(src, *asserting_clause(src.text, f.start, f.end))
            omitted.append(f"{f.where()} in {(ref.excerpt or '')[:160]!r}")
            stated += about
            refs.setdefault((ref.document_id, ref.locator or ""), ref)
    omitted = list(dict.fromkeys(omitted))
    constrained = bool(omitted)
    if constrained:
        detail = (f"the conclusion compares {', '.join(free)}, which no premise mentions, while the source asserts about them figure(s) the encoding "
                  f"omits: {'; '.join(omitted[:4])}")
    else:
        seen = "; ".join(dict.fromkeys(passed)) if passed else "every figure the sources state is encoded"
        detail = (f"the conclusion compares {', '.join(free)}, which no premise mentions, and no source (the claim, its supporting claims, the supplied "
                  f"texts, the task record) asserts a figure about them that the encoding omits ({truncate(seen, 900)}): the source leaves these symbols "
                  "open, so a counterexample that reassigns them is the verdict on the encoding (advisory coverage warning)")
    return CoverageNote(kind="unconstrained_symbol", problem_digest=coverage_digest(problem), assertion_ids=[problem.conclusion.id], symbols=free,
                        figures=[], source_asserted=constrained, evidence=omitted[:8], detail=detail[:2000],
                        source_refs=list(refs.values())[:16] if constrained else [],
                        evidence_symbols=list(dict.fromkeys(stated)) if constrained else [])


def free_conclusion_symbols(problem: Problem) -> list[str]:
    """The symbols the conclusion mentions and no premise does, of every sort: the symbols the engine's E111/W111 check
    reads evidence on (empty unless the problem has the E111 shape: an entailment over premises whose conclusion compares
    a numeric symbol no premise mentions)."""
    if problem.conclusion is None or problem.query != "entailment" or not problem.premises:
        return []
    sorts = {s.name: s.sort for s in problem.symbols}
    premise_vars: set[str] = set()
    for p in problem.premises:
        premise_vars |= _vars(p.expr)
    free = sorted(_vars(problem.conclusion.expr) - premise_vars)
    return free if any(sorts.get(v) in _NUMERIC for v in free) else []


def _evidence_grounding(existing: Optional[Grounding], refs: Sequence[SourceRef], kinds: Sequence[str], detail: str) -> Grounding:
    """The application record a coverage check puts on a symbol whose figure a source asserts: verified in this process,
    its references the asserting spans. The kind stays the translator's when it gave one (coverage evidence says where a
    statement is, not that it is established); otherwise it names the source (a supplied text, the task, the answer)."""
    kind: GroundingKind = existing.kind if existing is not None else _EVIDENCE_KIND.get(kinds[0] if kinds else "claim", "specialist_inference")
    note = "coverage evidence (application record of the translation layer): " + detail
    if existing is not None and existing.source_refs:
        note += f"; replaces the translation's own {len(existing.source_refs)} reference(s) (their checks are in grounding_checks)"
    return Grounding(kind=kind, source_refs=list(refs)[:16], certainty=existing.certainty if existing is not None else "established", verified=True,
                     note=truncate(note, 1000))


def apply_coverage_evidence(problem: Problem, notes: Sequence[CoverageNote]) -> tuple[Problem, list[GroundingCheck]]:
    """Hand the coverage decision to the engine (see the module docstring): ``(problem with the symbols' coverage flags
    set, the checks that set them)``.

    Every symbol of an under-determined shape (each unasserted definition's atom and figures, and every free conclusion
    symbol of the E111 shape) gets ``verified`` from the notes alone: a symbol in the ``evidence_symbols`` of a
    source-asserted note gets a grounding verified in this process whose references are the asserting spans; any other
    symbol of the shape keeps its grounding with ``verified`` cleared when the grounding check had set it (the
    translator's excerpt was located, but no source clause asserts the figure). Notes bound to other formulas are
    ignored. Symbols outside these shapes are untouched. The engine reads nothing else as coverage evidence, so its
    E110/E111 (no verdict) or W110/W111 (advisory) is this decision."""
    digest = coverage_digest(problem)
    current = [n for n in notes if n.problem_digest == digest]
    if not current:
        return problem, []
    involved: set[str] = set()
    stated: dict[str, list[tuple[CoverageNote, SourceRef]]] = {}
    for n in current:
        involved |= set(n.symbols)
        if n.kind == "unconstrained_symbol":
            involved |= set(free_conclusion_symbols(problem))
        if n.source_asserted:
            for name in n.evidence_symbols:
                stated.setdefault(name, []).extend((n, r) for r in n.source_refs)
    checks: list[GroundingCheck] = []
    symbols = []
    for sym in problem.symbols:
        g = sym.grounding
        if sym.name in stated and stated[sym.name]:
            refs = list({(r.document_id, r.locator): r for _n, r in stated[sym.name]}.values())
            kinds = [(r.locator or "").split(" ", 1)[0] for r in refs]
            ids = sorted({a for n, _r in stated[sym.name] for a in n.assertion_ids})
            what = f"a source asserts the figure that {sym.name} stands for, which the encoding leaves open ({', '.join(ids)})"
            record = _evidence_grounding(g, refs, kinds, what + ": " + "; ".join(f"{r.document_id} ({r.locator})" for r in refs[:4]))
            checks.append(GroundingCheck(target_id=sym.name, kind=record.kind, method="asserts_figure", verified=True, document_id=refs[0].document_id,
                                         detail=truncate(f"{what}: " + "; ".join(e for n, _r in stated[sym.name][:1] for e in n.evidence[:3]), 2000)))
            symbols.append(sym.model_copy(update={"grounding": record}))
        elif sym.name in involved and g is not None and g.verified is True:
            checks.append(GroundingCheck(target_id=sym.name, kind=g.kind, method="asserts_figure", verified=None,
                                         document_id=g.source_refs[0].document_id if g.source_refs else None,
                                         detail=("the translator's excerpt for this symbol was located, but no source clause asserts the figure the "
                                                 "encoding leaves open (the source defines, supposes, conditions or does not state it): no evidence that the "
                                                 "encoding omitted an assertion, so it is not coverage evidence")))
            symbols.append(sym.model_copy(update={"grounding": g.model_copy(update={"verified": None})}))
        else:
            symbols.append(sym)
    return problem.model_copy(update={"symbols": symbols}), checks
