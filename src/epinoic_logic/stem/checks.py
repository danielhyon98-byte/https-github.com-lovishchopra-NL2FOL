"""Planned STEM checks: every planned relation of a :class:`~.document.StemDocument` becomes a
:class:`PlannedCheck` (an IR 1.0 problem the engine decides) or an ST finding that names it
as undecided, with the reason (docs/STEM_DESIGN.md, sections 5, 7 and 8).

:func:`build_checks` is the entry point. For each planned check of the document (ids
``stem-<kind>-<n>``, planned by the front end in document order) it builds one problem:

=========  ==================================  =============================  =========  ==========
id kind    what is decided                      form, expected                 policy     severity
=========  ==================================  =============================  =========  ==========
``eq``     a numeric link ``E = S`` (and ≈)     E: ENTAILED; S: SATISFIABLE   as needed  error*
``sub``    substituted values against the      E: ENTAILED (pairs); E or S    as needed  error*
           bindings (R7), or the symbolic       (evaluation)
           side under its bindings
``alg``    the step follows from the            E: ENTAILED                    as needed  error, or
           preceding relation                                                             warning**
``sol``    stated roots: membership and,        E: ENTAILED; S: SATISFIABLE   as needed  error
           when the full set is claimed,
           completeness
``cnv``    an explicit unit conversion (R5)     E: ENTAILED                    linear     error*
``cmp``    a stated order (R6), or an           E: ENTAILED                    as needed  error
           inequality step
``res``    a prose restatement (R8)             E: ENTAILED                    linear     error*
``giv``    a Given value against the request    E: ENTAILED                    linear     warning
``tgt``    the final value against a            E: ENTAILED                    linear     warning
           show-that target
``chem``   element and charge balance           E: ENTAILED (Int or Real)      linear     error
``bool``   a Boolean identity                   satisfiability: UNSATISFIABLE  linear     error
``tt``     every stated truth-table row         E: ENTAILED                    linear     error
``base``   a based-numeral conversion           E: ENTAILED (Int)              linear     error
=========  ==================================  =============================  =========  ==========

\\* warning when a booklet value was supplied for an unstated symbol (D3b) or a unit was not
recognised (ST-UNIT-001). \\** warning when the step brings in symbols that no premise, binding
or included formula connects (an unstated law may be at work).

Every check carries an id, a description of at most 1,200 characters (what was checked, the
statement, the claims, the short rule, the readings, the factored exponent, the supplied
constants and the side conditions), the claim ids of the statements that hold the relation,
a named policy (``linear`` or ``nonlinear``, chosen exactly when the encoding multiplies two
terms that hold variables), ``failure_severity`` and ``inconsistent_is_failure=False`` (design
D13: inconsistent premises of a STEM check point to an earlier line or a domain outside the
encodings, so they are undecided, never an error). Problems are plain IR data; the branch stage
validates them with ``Problem.model_validate`` and the engine validates them again inside
``verify``. The STEM pack itself emits no error-severity finding: every error is an engine result.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Optional

from .boolean import TruthTable
from .constants import BookletReading, booklet_reading, constants_for_symbol, match_written
from .document import StemDocument
from .enclosures import EnclosureError, Interval, cross_check, e_interval, enclose, pi_interval
from .lexer import writes_constant_dot
from .models import MAX_MONOMIALS, all_symbols as model_symbols, denominators as model_denominators, exact_value, exponent_polynomial, exponential, monomial_node
from .models import render_model
from .models import _walk as model_nodes
from .numbers import ExactNumber
from .nodes import (
    Abs, BinOp, BoolOp, Degrees, Func, Neg, Node, Num, Operand, Percent, PlusMinus, Pow, Quantity, Ratio, RealPower, Root, Sym, WithUnit, is_closed,
    is_value, render, symbols, value_of, walk,
)
from .reference import unit_written_once
from .relations import ST_SEVERITY, Relation, RequestIntent
from .scaling import LiteralTooLong, Term, align as align_terms, floor_log10, frame_for, lit, literal_in_frame, literal_text, nary, real, to_frame, var_term
from .scope import Binding, si_value
from .tolerance import SHORT_RULE, TAU_APPROX, TAU_EQUAL, approx_qualifies, band_expr, exactness_phrase, half_width, is_measured, rounding_phrase
from .to_ir import IR_LIMITS, AffineUndecided, EncodeError, Encoder, IntervalLeaf, ProblemBuilder, Reading, SymbolDomain, _round_out, grounding, inspect_ir, real_power_value
from .units import DIMENSIONLESS, Dimension, UnitAtom, UnitExpr, parse_unit

__all__ = ["CHECK_KIND_NAMES", "CheckFinding", "CheckPlan", "PlannedCheck", "build_check", "build_checks"]

#: planned kind -> the FormalCheck kind (section 8.1)
CHECK_KIND_NAMES = {
    "eq": "stem_arithmetic", "sub": "stem_substitution", "alg": "stem_algebra", "sol": "stem_solution", "mod": "stem_model", "cnv": "stem_conversion",
    "cmp": "stem_comparison", "res": "stem_result", "giv": "stem_given", "tgt": "stem_target", "chem": "stem_balance", "bool": "stem_boolean",
    "tt": "stem_truth_table", "base": "stem_base",
    # the unit companion of an eq or sub check (ST-UNIT-003): a failure names a unit error
    "unit": "stem_conversion",
    # a stated operation of a solving step (ST-STEP-001) and the stated solution of a system of equations
    "op": "stem_algebra", "sys": "stem_solution",
    # a comparison that uses a value the working rounded (ST-ROUND-001)
    "rnd": "stem_comparison",
}
_TITLES = {
    "eq": "the written arithmetic", "sub": "the substitution", "alg": "the algebraic step", "sol": "the stated roots", "mod": "the model evaluation",
    "cnv": "the unit conversion",
    "cmp": "the stated comparison", "res": "the restated result", "giv": "the Given value against the request", "tgt": "the final value against the show-that target",
    "chem": "the element and charge balance", "bool": "the Boolean identity", "tt": "the stated truth-table rows", "base": "the based-numeral conversion",
    "unit": "ST-UNIT-003, the units of the written arithmetic",
    "op": "ST-STEP-001, the stated operation of the step", "sys": "the stated solution of the system of equations",
    "rnd": "ST-ROUND-001, a comparison made with a rounded value",
}
_MAX_DESCRIPTION = 1200
_MAX_EXCERPT = 160
_CMP_OPS = {"<": "lt", ">": "gt", "≤": "le", "≥": "ge", "≠": "ne", "=": "eq", "≈": "eq", "≃": "eq", "≡": "eq"}
_CHANGE_WORDS = ("change", "difference", "rise", "fall", "increase", "decrease", "Δ", "drop", "gain")


@dataclass(frozen=True)
class PlannedCheck:
    """One engine check of a STEM statement. ``problem`` is IR 1.0 data (a ``dict`` that
    ``Problem.model_validate`` accepts). The branch stage turns it into a ``FormalCheck``."""

    check_id: str
    kind: str
    description: str
    claim_ids: tuple[str, ...]
    problem: dict
    expected_if_sound: str
    policy: str
    failure_severity: str
    inconsistent_is_failure: bool = False
    form: str = "E"
    relation_kind: str = ""
    readings: tuple[str, ...] = ()
    #: the tolerance policy that decided the check and where it came from (the request, the answer's own words, the written form)
    tolerance: str = ""
    #: the canonical defect label (``named.DEFECT_LABELS``) a failure of this check names, when its kind alone does not say it
    #: (a unit companion: ``stem_unit_error``); empty otherwise
    defect: str = ""


@dataclass(frozen=True)
class CheckFinding:
    """An ST finding of the checks stage: a planned check that is not built (undecided, with the
    reason), or a note about one. ``severity`` comes from :data:`~.relations.ST_SEVERITY`; it is never
    ``error``."""

    code: str
    severity: str
    message: str
    statement_ids: tuple[str, ...]
    check_id: str = ""


@dataclass(frozen=True)
class CheckPlan:
    checks: tuple[PlannedCheck, ...] = ()
    findings: tuple[CheckFinding, ...] = ()

    def check(self, check_id: str) -> Optional[PlannedCheck]:
        for c in self.checks:
            if c.check_id == check_id:
                return c
        return None

    def finding_for(self, check_id: str) -> Optional[CheckFinding]:
        for f in self.findings:
            if f.check_id == check_id:
                return f
        return None


def _finding(code: str, message: str, rel: Relation) -> CheckFinding:
    return CheckFinding(code, ST_SEVERITY.get(code, "warning"), f"{rel.check_id}: {message}"[:1200], tuple(rel.statement_ids), rel.check_id)


def _ident(text: str, limit: int = 128) -> str:
    if len(text) <= limit:
        return text
    digest = hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()[:12]
    return text[:limit - 13] + "-" + digest


def build_checks(doc: StemDocument, *, report_id: str = "report", request_id: Optional[str] = None, relay: bool = False) -> CheckPlan:
    """A :class:`PlannedCheck` for every planned check of ``doc`` that the encodings express, and an ST
    finding naming every one they do not. On relay (no request) ``giv`` and ``tgt`` are not built.
    Never raises on agent text: an internal failure of one check is ST-INTERNAL-001 for that check."""
    checks: list[PlannedCheck] = []
    findings: list[CheckFinding] = []
    for rel in doc.checks:
        if relay and rel.kind in ("giv", "tgt"):
            continue
        out = build_check(doc, rel, report_id=report_id, request_id=request_id)
        if isinstance(out, PlannedCheck):
            checks.append(out)
        else:
            findings.append(out)
    return CheckPlan(tuple(checks), tuple(findings))


def build_check(doc: StemDocument, rel: Relation, *, report_id: str = "report", request_id: Optional[str] = None) -> "PlannedCheck | CheckFinding":
    """The check for one planned relation, or the finding that names it undecided."""
    try:
        builder = _BUILDERS.get(rel.kind)
        if builder is None:
            return _finding("ST-UNDEC-001", f"no encoding for a relation of kind {rel.kind!r}", rel)
        cut = _truncated_operand(doc, rel)
        if cut:
            return _finding("ST-PARSE-001", cut, rel)
        ctx = _Ctx(doc, rel, report_id, request_id or report_id)
        builder(ctx)
        return ctx.finish()
    except EncodeError as exc:
        return _finding(exc.code, exc.reason, rel)
    except (LiteralTooLong,) as exc:
        return _finding("ST-LIM-001", str(exc), rel)
    except EnclosureError as exc:
        return _finding(exc.code, exc.reason, rel)
    except Exception as exc:  # defensive: one check's failure never takes the others down
        return _finding("ST-INTERNAL-001", f"the STEM pack failed internally while building this check ({type(exc).__name__})", rel)


_ARITH = frozenset("+-−×*/·÷^")
_SIGNS = frozenset("+-−")
#: short words after which a signed expression may start a relation in prose ("so −2x > 4")
_SHORT_WORDS = frozenset({"so", "is", "as", "to", "of", "or", "if", "at", "by", "we", "it", "be", "in", "on", "ie", "eg", "and", "the", "get", "has"})


def _truncated_operand(doc: StemDocument, rel: Relation) -> str:
    """A reason when an operand of the relation was cut from a longer expression in the text, else
    empty. The front end then read only part of it (``xy + y = …`` read as ``+ y = …``), and deciding
    the part could fail correct work. An operand is cut when an arithmetic operator adjoins it, or
    when it opens with a sign right after a symbol-like token on the same line (not after a relation
    sign, a bracket or a prose word). Operands read from the request are not looked at. This only
    ever withholds a check; it never decides one. The text is read in the reading view (the same length), so the
    magnification notation '= ×2', whose times sign the view reads as the number it marks, adjoins no operator."""
    text = doc.reading if len(doc.reading) == len(doc.text) else doc.text
    n = len(text)
    # a Computer Science answer that writes a Boolean constant with the AND dot ('P.0') is read without the AND dot
    # (lexer.writes_constant_dot), as before that reading: its full stops between letters are read as before too, so a
    # relation glued to one is checked as it was (close round 2, DIFF-04)
    boolean_dots_off = doc.profile.computer_science and writes_constant_dot(doc.text)
    ops = [rel.left, rel.right]
    if "request" not in rel.premise_ids:
        ops += [rel.premise_left, rel.premise_right]
    if rel.kind in ("tgt", "giv", "res"):
        ops = [rel.left] if rel.kind in ("tgt", "res") else []  # the other side is a single value read from prose or the request
    for op in ops:
        if op is None or op.end <= op.start or op.end > n or not op.readings:
            continue
        node = op.readings[0]
        if isinstance(node, Sym) and node.kind in ("continuation", "label"):
            continue
        j = op.start - 1
        while j >= 0 and op.start - j <= 8 and text[j] in " \t":
            j -= 1
        k = op.end
        while k < n and k - op.end < 8 and text[k] in " \t":
            k += 1
        before = text[j] if 0 <= j < n and text[j] != "\n" else ""
        after = text[k] if k < n and text[k] != "\n" else ""
        shown = " ".join(text[op.start:op.end].split())[:80]
        if (before and before in _ARITH) or (after and after in _ARITH):
            return f"the operand '{shown}' is cut from a longer expression (an arithmetic operator adjoins it), so the relation is not checked"
        if before == "." and j == op.start - 1 and j >= 1 and text[j - 1].isalpha() and not boolean_dots_off:
            return (f"the operand '{shown}' is glued to '{text[max(0, j - 6):j + 1].strip()}' (a dot between two letters, as in 'A.B'), so it is likely "
                    f"cut from a longer expression; the relation is not checked")
        if ("0" <= after <= "9" and after != "") or ("0" <= before <= "9" and before != ""):
            return (f"the operand '{shown}' is adjoined by more digits ('{' '.join(text[max(0, op.start - 6):min(n, op.end + 8)].split())}'), so it may be "
                    f"part of a longer numeral such as a thousands group written with a space; the relation is not checked")
        if text[op.start] in _SIGNS and before and before not in _OPENERS:
            m = j
            while m >= 0 and text[m].isalpha() and j - m < 32:
                m -= 1
            token = text[m + 1:j + 1]
            if not (token.isalpha() and (len(token) >= 3 or token.lower() in _SHORT_WORDS)):
                return f"the operand '{shown}' opens with a sign right after '{text[max(0, j - 8):j + 1].strip()}', so it is likely cut from a longer expression; the relation is not checked"
    if rel.kind in _CHAIN_KINDS and rel.left is not None and rel.right is not None and rel.left.end <= rel.right.start <= n:
        gap = _without_markup(doc, rel.left.end, rel.right.start)
        if len(rel.head_gap) == 2 and rel.left.end <= rel.head_gap[0] <= rel.head_gap[1] <= rel.right.start:
            # a computation continued by its repeated head ('v = 8.4 / 2.0', then 'v = 5.2 m/s'): the head is no prose between the sides
            a, b = rel.head_gap
            gap = _without_markup(doc, rel.left.end, a) + " " + _without_markup(doc, b, rel.right.start)
        gap = _strip_relation_text(gap)
        if any(ch.isalnum() for ch in gap):
            return f"prose ('{' '.join(gap.split())[:40]}') stands between the two sides of the relation, so they may not belong together; the relation is not checked"
    return ""


#: what may precede an operand that opens with a sign: a relation sign, an opening bracket, a separator, LaTeX alignment
_OPENERS = frozenset("=<>≤≥≈≃≠⇒→∴:([{$&,;|±∓\\")
#: kinds whose two sides are adjacent operands of one chain
_CHAIN_KINDS = frozenset({"eq", "cnv", "cmp", "sub", "base"})
_RELATION_WORDS = ("is equal to", "equals", "equal", "gives", "approximately", "approx", "about", "roughly", "is", "makes")


def _without_markup(doc: StemDocument, a: int, b: int) -> str:
    """``doc.text[a:b]`` with the answer's mark annotations blanked (``M1`` or ``[1]`` at a line end between two lines of
    one chain is furniture, not prose between the sides)."""
    seg = list(doc.text[a:b])
    marks = doc.spans.markup  # sorted by start
    lo, hi = 0, len(marks)
    while lo < hi:  # the first mark that ends after a (binary search: a mark never nests in another)
        mid = (lo + hi) // 2
        if marks[mid][1] <= a:
            lo = mid + 1
        else:
            hi = mid
    k = lo
    while k < len(marks) and marks[k][0] < b:
        x, y = marks[k]
        for i in range(max(x, a), min(y, b)):
            seg[i - a] = " "
        k += 1
    return "".join(seg)


def _strip_relation_text(gap: str) -> str:
    """The gap between two operands of one link without its relation sign: LaTeX commands, alignment
    marks, relation symbols and the words of verbal arithmetic removed."""
    out = []
    i = 0
    while i < len(gap):
        ch = gap[i]
        if ch == "\\":
            j = i + 1
            while j < len(gap) and gap[j].isalpha():
                j += 1
            i = max(j, i + 2)
            continue
        out.append(ch)
        i += 1
    rest = " " + "".join(out).lower() + " "
    for w in _RELATION_WORDS:
        rest = rest.replace(" " + w + " ", " ")
    return rest.strip()


# --------------------------------------------------------------------------- per-check context


@dataclass
class _Ctx:
    doc: StemDocument
    rel: Relation
    report_id: str
    request_id: str
    builder: ProblemBuilder = field(init=False)
    query: str = "entailment"
    conclusion: Optional[tuple[str, dict, str]] = None
    expected: str = "ENTAILED"
    severity: str = "error"
    form: str = "E"
    details: list[str] = field(default_factory=list)
    readings: list[str] = field(default_factory=list)
    cache: dict = field(default_factory=dict)
    #: the tolerance policy recorded on the check (description, notes and ``PlannedCheck.tolerance``)
    tolerance: str = ""
    #: the comparison is exact because the request or the answer states exactness (section 5.2, R2)
    exact_intent: bool = False
    #: the request or the answer states a rounding: a stated value is a rounding whatever its spelling (R2)
    rounded_intent: bool = False
    #: a step has a measured operand outside its stated value (a decimal, a unit, a constant or a function): R2's τ = 1/100
    step_measured: bool = False
    #: the canonical defect label the check's failure names (``PlannedCheck.defect``)
    defect: str = ""

    def __post_init__(self) -> None:
        rel = self.rel
        kind = rel.kind
        n = rel.check_id.rsplit("-", 1)[-1] if rel.check_id else "0"
        pid = _ident(f"stem-{kind}-{self.report_id}-{n}")
        first = rel.statement_ids[0] if rel.statement_ids else "s"
        self.builder = ProblemBuilder(pid, _ident(self.request_id), _ident(f"{self.report_id}:{first}"))

    @property
    def profile_key(self) -> str:
        return self.doc.profile.key

    def detail(self, text: str) -> None:
        if text and text not in self.details:
            self.details.append(text)

    def warn(self, why: str) -> None:
        self.severity = "warning"
        self.detail(f"failure severity warning: {why}")

    def finish(self) -> PlannedCheck:
        b = self.builder
        if self.query == "entailment" and self.conclusion is None:
            raise EncodeError("ST-INTERNAL-001", "an entailment problem without a conclusion")
        problem = b.problem(self.query, self.conclusion)
        rep = inspect_ir(problem)
        if rep.symbols > IR_LIMITS["symbols"]:
            raise EncodeError("ST-LIM-001", f"the encoding needs {rep.symbols} symbols; the bound per check is {IR_LIMITS['symbols']}")
        if rep.premises > IR_LIMITS["premises"]:
            raise EncodeError("ST-LIM-001", f"the encoding needs {rep.premises} premises; the bound is {IR_LIMITS['premises']}")
        if rep.nodes > IR_LIMITS["nodes"]:
            raise EncodeError("ST-LIM-001", f"the encoding has {rep.nodes} IR nodes; the bound is {IR_LIMITS['nodes']}")
        if rep.depth > IR_LIMITS["depth"]:
            raise EncodeError("ST-LIM-001", f"the encoding is {rep.depth} levels deep; the bound is {IR_LIMITS['depth']}")
        if rep.max_digits > IR_LIMITS["digits"]:
            raise EncodeError("ST-LIM-001", f"a literal has {rep.max_digits} digits after factoring; the bound is {IR_LIMITS['digits']}")
        if rep.nonlinear and rep.degree > IR_LIMITS["degree"]:
            raise EncodeError("ST-LIM-001", f"the encoding has polynomial degree {rep.degree}; the nonlinear policy allows {IR_LIMITS['degree']}")
        if self.form == "S":
            free = [n for n, role in b.roles.items() if role == "free"]
            if free:
                raise EncodeError("ST-INTERNAL-001", f"a satisfiability problem with a free symbol ({free[0]})")
        policy = "nonlinear" if rep.nonlinear else "linear"
        tolerance = self.tolerance or _TOLERANCE_BY_KIND.get(self.rel.kind, "")
        if tolerance:
            b.note(f"tolerance policy: {tolerance}")
        if policy == "nonlinear":
            b.note("policy: nonlinear")
        problem = b.problem(self.query, self.conclusion)
        desc = self.description(policy, tolerance)
        return PlannedCheck(
            check_id=self.rel.check_id, kind=CHECK_KIND_NAMES[self.rel.kind], description=desc, claim_ids=tuple(self.rel.statement_ids), problem=problem,
            expected_if_sound=self.expected, policy=policy, failure_severity=self.severity, inconsistent_is_failure=False, form=self.form,
            relation_kind=self.rel.kind, readings=tuple(self.readings), tolerance=tolerance, defect=self.defect,
        )

    def excerpt(self) -> str:
        rel = self.rel
        text = self.doc.text[rel.start:rel.end] if 0 <= rel.start < rel.end <= len(self.doc.text) else ""
        if not text and rel.left is not None and rel.left.node is not None:
            text = render(rel.left.node) + f" {rel.op} " + (render(rel.right.node) if rel.right is not None and rel.right.node is not None else "")
        text = " ".join(text.split())
        return text if len(text) <= _MAX_EXCERPT else text[:_MAX_EXCERPT - 1] + "…"

    def description(self, policy: str, tolerance: str = "") -> str:
        rel = self.rel
        form = {"E": "Form E (entailment, expected ENTAILED)", "S": "Form S (satisfiability, expected SATISFIABLE: some admissible reading gives the "
                "stated value; it does not mean the value is true)", "B": "satisfiability, expected UNSATISFIABLE (a witness distinguishes the sides)"}[self.form]
        if rel.kind == "mod":
            form = ("Form S (satisfiability, expected SATISFIABLE: some value of the variables, and of the stated symbols within their stated "
                    "values, satisfies the relation; it does not mean the relation holds for every value)")
        title = "the comparison the answer says fails" if rel.kind == "cmp" and rel.negated else _TITLES[rel.kind]
        head = f"{title}: '{self.excerpt()}' [claims {', '.join(rel.statement_ids)}] [{SHORT_RULE}]"
        parts = [form, f"policy {policy}"]
        if tolerance:
            parts.append(f"tolerance policy: {tolerance}")
        if self.readings:
            parts.append("readings: " + "; ".join(self.readings))
        parts.extend(self.details)
        text = head + " " + "; ".join(parts)
        if len(text) > _MAX_DESCRIPTION:
            text = text[:_MAX_DESCRIPTION - 1] + "…"
        return text


# --------------------------------------------------------------------------- shared helpers


def _leaves(node: Node) -> list[Node]:
    """Numerals of ``node`` (``Num`` and ``Quantity``), in order."""
    return [n for n in walk(node) if isinstance(n, (Num, Quantity))]


def _units_in(node: Node) -> list[UnitExpr]:
    return [n.unit for n in walk(node) if isinstance(n, (Quantity, WithUnit))]


def _has_percent(node: Node) -> bool:
    return any(isinstance(n, Percent) for n in walk(node))


def _inside_unit(node: Node) -> set[int]:
    """ids of numerals that carry a unit or a per cent sign (directly, or inside ``(…) unit``)."""
    out: set[int] = set()
    for n in walk(node):
        if isinstance(n, Quantity):
            out.add(id(n))
        elif isinstance(n, (WithUnit, Percent)):
            for m in walk(n.arg):
                if isinstance(m, (Num, Quantity)):
                    out.add(id(m))
    return out


def _min_sig_figs(node: Node) -> Optional[int]:
    """The smallest significant-figure count among the measured numerals of ``node`` (section 5.1)."""
    figs = [n.number.sig_figs for n in _leaves(node) if is_measured(n.number, isinstance(n, Quantity))]  # type: ignore[union-attr]
    return min(figs) if figs else None


def _all_exact(node: Node) -> bool:
    """Every numeral is exact as written (no point, no scientific notation, no unit)."""
    for n in walk(node):
        if isinstance(n, (Quantity, WithUnit)):
            return False
        if isinstance(n, Num) and (n.number.has_point or n.number.scientific):
            return False
    return True


def _has_plus_minus(*nodes: Node) -> bool:
    return any(isinstance(n, PlusMinus) for node in nodes for n in walk(node))


def _approx(ctx: _Ctx) -> bool:
    if ctx.rel.approx:
        return True
    sid = ctx.rel.statement_ids[-1] if ctx.rel.statement_ids else ""
    st = ctx.doc.statement(sid)
    if st is None:
        return False
    before = ctx.doc.text[max(st.start, ctx.rel.start - 120):ctx.rel.start]
    return approx_qualifies(before)  # whole words that qualify this relation ('linearly' holds no 'nearly')


# --------------------------------------------------------------------------- tolerance policy (section 5.2, R2): intent first, then the written form

#: the policy recorded on a check whose kind fixes its own tolerance
_TOLERANCE_BY_KIND = {
    "sub": "written substitution (R7): a substituted value matches a binding within the two half-widths, τ = 0",
    "cmp": "exact comparison (R6): no slack",
    "res": "restatement (R8): within the two half-widths, τ = 0",
    "giv": "Given value (R7): within the two half-widths, τ = 0",
    "tgt": "show-that target: within the two half-widths (τ = 1/20 for an approximate target)",
    "alg": "algebra step: exact; a rounded value written in the step within h of its last digit, with τ = 1/100 only beside a measured operand (R4, R2)",
    "sol": "roots (R10): an exact root exactly, a decimal root within its rounding interval",
    "cnv": "conversion (R5): exact table factors, τ = 0, within the two half-widths",
    "chem": "exact: integer or fractional coefficients", "bool": "exact: Boolean", "tt": "exact: Boolean", "base": "exact: integers",
    "op": "identity: every value of the unknowns (a rounded value written on the next line within h of its last digit)",
    "sys": "exact values exactly; a decimal value within its rounding interval (R10)",
    "rnd": "exact comparison (R6) with the rounded value and with the value before the rounding",
}


def _part_key(label: str) -> str:
    """A part label reduced to what identifies it: ``(a)``, ``Part (a)`` and ``**a)**`` are all ``a``."""
    low = label.lower().replace("part", " ").replace("question", " ")
    return "".join(c for c in low if c.isalnum())


def _clause_window(ctx: "_Ctx") -> str:
    """The relation's own clause in the answer: its statement's text before it (back to a sentence or clause boundary, at
    most 160 characters) and after it (to the next boundary, at most 48 characters)."""
    rel = ctx.rel
    st = ctx.doc.statement(rel.statement_ids[-1]) if rel.statement_ids else None
    if st is None or not (st.start <= rel.start <= rel.end <= st.end):
        return ""
    text = ctx.doc.text
    before = text[max(st.start, rel.start - 160):rel.start]
    cut = max(before.rfind(". "), before.rfind(";"), before.rfind("\n"), before.rfind(":"))
    before = before[cut + 1:] if cut >= 0 else before
    after = text[rel.end:min(st.end, rel.end + 48)]
    stops = [k for k in (after.find(". "), after.find(";"), after.find("\n"), after.find(", ")) if k >= 0]
    after = after[:min(stops)] if stops else after
    return before + " " + after


def _request_intent(ctx: "_Ctx") -> Optional[RequestIntent]:
    """The request's precision intent for the relation's part: its own part's statements and the request's statements
    outside any part (a request without parts applies whole). A rounding instruction wins over exactness, so a request
    that asks for both ("the exact value, then to 3 s.f.") keeps the rounded tolerance."""
    intents = ctx.doc.request.intents
    if not intents:
        return None
    part = _part_key(ctx.rel.part)
    applicable = [i for i in intents if not part or not i.part or _part_key(i.part) == part]
    return next((i for i in applicable if i.kind == "rounded"), None) or next((i for i in applicable if i.kind == "exact"), None)


def _intent_policy(ctx: "_Ctx", nodes: list[Node], *, approx: bool, has_units: bool = False) -> tuple[str, str]:
    """``(kind, label)`` of the tolerance policy the task or the answer states for this relation, or ``("", "")`` when the
    written form decides (section 5.2, R2). In order:

    * ``approximate``: ``≈`` or an approximation word beside the relation (τ = 1/20);
    * ``exact``: the answer states exactness beside the relation ("Exactly 1/2 = 0.51.", "= 0.51 exactly");
    * ``rounded``: the answer states a rounded value beside it ("(to 2 d.p.)");
    * the request (its part, or the whole request): ``rounded`` when it asks for rounding ("to 2 decimal places"), which
      keeps the tolerance of the written digits; ``exact`` when it states exactness ("exactly", "without rounding", "the
      exact value") and the relation is between pure numbers. A quantity with a unit is a measurement: a request's
      exactness does not make it exact (the answer's own "exactly" still does).

    Under ``exact`` the stated value must equal the computed value: τ = 0 and h = 0, whatever its spelling, so ``0.51`` and
    ``51/100`` get the same verdict, and a decimal never earns the slack of its last digit. Under ``rounded`` the stated
    value is a rounding whatever its spelling (:func:`_stated_half_width`): exact mode does not apply, so ``7/3 = 2`` under
    "to the nearest integer" and ``1/3 = 33/100`` under "to 2 decimal places" are checked as ``1/3 = 0.33`` is."""
    if approx:
        return "approximate", "approximate (≈ or an approximation word beside the relation): τ = 1/20"
    window = _clause_window(ctx)
    phrase = exactness_phrase(window)
    if phrase:
        return "exact", f"exact, as the answer states ('{phrase}'): τ = 0 and h = 0, whatever the spelling of the stated value"
    phrase = rounding_phrase(window)
    if phrase:
        return "rounded", f"rounded, as the answer states ('{phrase}'): {_ROUNDED_H}"
    intent = _request_intent(ctx)
    if intent is not None:
        if intent.kind == "rounded":
            return "rounded", f"rounded, as the request asks ('{intent.phrase}'): {_ROUNDED_H}"
        if not has_units and not any(_units_in(n) for n in nodes):
            return "exact", f"exact, as the request states ('{intent.phrase}'): τ = 0 and h = 0, whatever the spelling of the stated value"
        ctx.detail(f"the request states exactness ('{intent.phrase}') but the relation is between measured quantities (units): the written form decides")
    return "", ""


def _clause_states_exactness(ctx: "_Ctx") -> bool:
    """The answer itself states exactness beside the relation (not only the request)."""
    return bool(exactness_phrase(_clause_window(ctx)))


def _measured_numerals(node: Node) -> bool:
    """A numeral of ``node`` is measured as written: a decimal point, scientific notation or a unit."""
    for n in walk(node):
        if isinstance(n, WithUnit):
            return True
        if isinstance(n, (Num, Quantity)) and is_measured(n.number, isinstance(n, Quantity)):
            return True
    return False


def _value_half_width(node: Node, *, min_sf: Optional[int] = None, exact_mode: bool = False) -> Fraction:
    v = value_of(node)
    if v is None or v[1] is None:
        return Fraction(0)
    return half_width(v[1], min_sig_figs=min_sf, exact_mode=exact_mode)


#: the half-width rule of a stated rounding, recorded in the tolerance policy
_ROUNDED_H = "h is half a unit in the stated value's last digit, whatever its spelling (a fraction's in its decimal expansion); no exact mode"


def _written_fraction(node: Node) -> Optional[Fraction]:
    """The value of a stated fraction of two written integers (``33/100``, ``−5/2``), else None."""
    sign, cur = 1, node
    if isinstance(cur, Neg):
        sign, cur = -1, cur.arg
    if not (isinstance(cur, BinOp) and cur.op == "/" and isinstance(cur.left, Num) and isinstance(cur.right, Num)):
        return None
    a, b = cur.left.number, cur.right.number
    if any(n.has_point or n.scientific or n.base != 10 or n.value.denominator != 1 for n in (a, b)) or b.value == 0:
        return None
    return sign * a.value / b.value


def _expansion_half_width(value: Fraction) -> Fraction:
    """Half a unit in the last digit of the terminating decimal expansion of ``value`` (``33/100`` is 0.33: 1/200; ``5/2``
    is 2.5: 1/20; an integer: 1/2); 0 when the expansion does not terminate (``1/3``) or runs past 30 places."""
    den = value.denominator
    places = 0
    for p in (2, 5):
        k = 0
        while den % p == 0 and k <= 120:
            den //= p
            k += 1
        places = max(places, k)
    if den != 1 or places > 30:
        return Fraction(0)
    return Fraction(1, 2 * 10 ** places)


#: a precision label written right after a stated value: "(1 s.f.)", "to 3 sig figs", "(2 d.p.)", "correct to 2 decimal places"
_PRECISION_LABEL_RE = re.compile(r"^[\s,]{0,3}\(?\s*(?:(?:correct\s+)?to\s+)?(?P<n>\d{1,2})\s*(?P<kind>s\.?\s*f\.?|sig(?:nificant)?\.?\s*fig(?:ure)?s?|"
                                 r"d\.?\s*p\.?|decimal\s+places?)(?![A-Za-z])", re.IGNORECASE)


def _precision_label_after(ctx: "_Ctx") -> Optional[tuple[str, int]]:
    """``("sf" | "dp", n)`` when the stated value of the relation is followed at once by a precision label ("= 4400 (1 s.f.)")."""
    text = ctx.doc.text
    rel = ctx.rel
    m = _PRECISION_LABEL_RE.match(text[rel.end:rel.end + 40])
    if m is None:
        return None
    kind = "dp" if m.group("kind").lower().replace(" ", "").startswith(("d", "decimal")) else "sf"
    n = int(m.group("n"))
    return (kind, n) if 1 <= n <= 15 else None


def _labelled_half_width(ctx: "_Ctx", node: Node, label: tuple[str, int], h: Fraction) -> Fraction:
    """The half-width of a stated value that carries a precision label: half a unit of the labelled place. A value the label
    cannot describe ("4400 (1 s.f.)": 4400 is no value to one significant figure) is no rounding at that precision, so it
    must equal the computed value exactly (h = 0)."""
    v = value_of(node)
    if v is None or v[1] is None or v[0] == 0:
        return h
    kind, n = label
    if kind == "dp":
        e = -n
    else:
        mag = abs(v[0])
        k = 0
        while mag >= 10 and k < 400:
            mag /= 10
            k += 1
        while mag < 1 and k > -400:
            mag *= 10
            k -= 1
        e = k - n + 1
    unit = Fraction(10) ** e
    if (v[0] / unit).denominator != 1:
        ctx.detail(f"the stated value {render(node)[:40]} is labelled {n} {'d.p.' if kind == 'dp' else 's.f.'}, a precision it is not written to: "
                   f"it must equal the computed value exactly")
        return Fraction(0)
    ctx.detail(f"the stated value {render(node)[:40]} is labelled {n} {'d.p.' if kind == 'dp' else 's.f.'}: h is half a unit of that place")
    return unit / 2


def _stated_half_width(node: Node, *, min_sf: Optional[int] = None, exact_mode: bool = False, rounded: bool = False) -> Fraction:
    """R1 for a stated value (0 in exact mode, and for anything that is not a single value). Under a stated rounding (R2,
    ``rounded``) every spelling of the value is a rounding: a fraction of two written integers or a vulgar fraction has the
    half-width of its terminating decimal expansion (``33/100`` as ``0.33``), so equivalent spellings get one verdict."""
    if exact_mode:
        return Fraction(0)
    if rounded:
        frac = _written_fraction(node)
        if frac is not None:
            return _expansion_half_width(frac)
        v = value_of(node)
        if v is not None and v[1] is not None and v[1].vulgar:
            return _expansion_half_width(v[0])
    return _value_half_width(node, min_sf=min_sf) if is_value(node) else Fraction(0)


def _scale_for(node: Node, reading: Reading, enc: Encoder) -> Fraction:
    """The factor that turns a written half-width of the value ``node`` into this reading's units."""
    v = value_of(node)
    if v is None:
        return Fraction(1)
    factor = Fraction(1)
    if v[2] is not None and reading.si:
        cur = node
        while isinstance(cur, (Neg, Percent, Degrees)):
            cur = cur.arg
        start = getattr(cur, "start", 0)
        factor = abs(enc._factor_of(v[2], start))
    if v[3] == "%" and reading.si:
        factor /= 100
    if v[3] == "°" and reading.si and reading.degrees_si:
        factor *= _PI_DEGREE_HI  # a half-width written in degrees, in radians (rounded up)
    return factor


def _operand_combos(*ops: Optional[Operand]) -> list[tuple[Node, ...]]:
    combos: list[tuple[Node, ...]] = [()]
    for op in ops:
        if op is None or not op.readings:
            raise EncodeError("ST-PARSE-001", "an operand of the relation could not be read")
        combos = [c + (r,) for c in combos for r in op.readings]
    return combos


def _reading_modes(nodes: list[Node], *, symbol_units: bool = False, force: Optional[str] = None,
                   sym_units: tuple[UnitExpr, ...] = (), both: bool = False) -> tuple[list[str], bool, list[UnitExpr]]:
    """Section 6.4. Returns the unit modes (``aw``, ``si``), whether an unknown unit restricts the
    check to the reading as written, and the ambiguous units (two readings each). ``sym_units`` are the
    units of the bindings of the symbols in ``nodes``: a symbol bound with a unit is compared in SI like a
    value written with one (``m₁ = 500 g`` against ``m₂ = 1.0 kg`` is 0.5 kg against 1.0 kg, never 500 against 1.0)."""
    units = [u for n in nodes for u in _units_in(n)]
    unknown = any(u.unknown for u in units)
    if unknown:
        return ["aw"], True, []
    percent = any(_has_percent(n) for n in nodes)
    if force:
        return [force], False, [u for u in units if len(u.readings) > 1]
    if both:
        # the as-written reading is not admissible beside the SI one (a unit companion decides which holds): both, each its own
        return ["aw", "si"], False, [u for u in units if len(u.readings) > 1]
    if not units and not percent and not symbol_units:
        return ["aw"], False, []
    carried = set()
    for n in nodes:
        carried |= _inside_unit(n)
    bare = False
    for n in nodes:
        for leaf in _leaves(n):
            if id(leaf) in carried or leaf.number.vulgar:
                continue
            bare = True
    ambiguous = [u for u in units if len(u.readings) > 1]
    if not _si_differs(nodes) and not any(_unit_differs(u) for u in sym_units if not u.unknown):
        return ["aw"], False, []  # every unit factor is 1 and no per cent: SI and as written coincide
    if not bare and (units or percent or symbol_units):
        return ["si"], False, ambiguous
    return ["aw", "si"], False, ambiguous


def _unit_differs(unit: UnitExpr) -> bool:
    """The SI reading changes a value written in ``unit``: a factor other than 1 (in any of its readings), no exact factor,
    or an offset scale."""
    return any(r.factor is None or r.factor != 1 or r.affine is not None for r in unit.readings)


def _si_differs(nodes: list[Node]) -> bool:
    """True when the SI reading changes some value: a unit with a factor other than 1 (in any of its
    readings) or no exact factor, or a per cent sign."""
    for node in nodes:
        for n in walk(node):
            if isinstance(n, Percent):
                return True
            if isinstance(n, (Quantity, WithUnit)) and _unit_differs(n.unit):
                return True
    return False


def _temperature_scale(unit: Optional[UnitExpr]) -> Optional[str]:
    """The temperature scale a unit writes a value on: ``°C`` or ``°F`` (an offset scale), ``K`` for kelvin (and its
    prefixed forms), None for anything that is not a temperature (``J kg⁻¹ °C⁻¹`` included)."""
    if unit is None or unit.unknown or not unit.readings:
        return None
    for r in unit.readings:
        if r.affine is not None:
            atom = r.atoms[0] if r.atoms else None
            return atom.unit.symbol if atom is not None and atom.unit is not None else unit.text
    d = unit.dim
    if d is not None and d.exps == (0, 0, 0, 0, 1, 0, 0) and not d.angle:
        return "K"
    return None


def _affine_mode(ctx: "_Ctx", nodes: list[Node], sym_units: tuple[UnitExpr, ...] = ()) -> tuple[bool, ...]:
    """Section 6.1: whether a temperature on an offset scale (°C, °F) in this relation is read as a temperature (the
    offset applied, ``(True,)``) or as a difference (``(False,)``), with the reason recorded in the description.

    * No such temperature: nothing to decide.
    * The statement speaks of a change (Δ, change, difference, rise, fall, ...): every one is a difference.
    * Every temperature of the relation is written on the same offset scale: compared on that scale, where an offset cancels.
    * Otherwise (a temperature set against kelvin or the other offset scale): a temperature, converted once as a whole
      quantity on each side (``Encoder._affine_point``): a unit written after a group applies to the evaluated group, so
      ``(20 + 5) °C`` is 298.15 K exactly as ``25 °C`` is; a side that combines it with other terms is not converted."""
    scales = [s for n in nodes for m in walk(n) if isinstance(m, (Quantity, WithUnit)) and (s := _temperature_scale(m.unit)) is not None]
    scales += [s for u in sym_units if (s := _temperature_scale(u)) is not None]
    if not any(s != "K" for s in scales):
        return (False,)
    if _change_context(ctx):
        ctx.detail("°C/°F offset not applied: the statement speaks of a change, so a temperature on an offset scale is a difference")
        return (False,)
    if len(set(scales)) == 1:
        ctx.detail(f"every temperature of the relation is written in {scales[0]}: compared on that scale, where an offset cancels")
        return (False,)
    ctx.detail("°C/°F offset applied (absolute temperatures): once to each side that is one temperature, on its evaluated value, never term "
               "by term")
    return (True,)


# --------------------------------------------------------------------------- binding scope: parts and statement order (section 4.6)


def _scope_maps(ctx: "_Ctx") -> tuple[dict[str, int], dict[str, str]]:
    hit = ctx.cache.get(("scope-maps",))
    if hit is None:
        hit = ({st.id: i for i, st in enumerate(ctx.doc.statements)}, {st.id: st.part for st in ctx.doc.statements})
        ctx.cache[("scope-maps",)] = hit
    return hit


def _scoped(ctx: "_Ctx", pool: tuple[Binding, ...], *, in_force: bool) -> tuple[tuple[Binding, ...], bool]:
    """The bindings of one symbol that the relation of this check may use, and whether the choice among them is a reading.

    A binding holds in its own part from where it is stated: a calculation sees the bindings of its own part stated
    before it or in its own statements (``…, where x = 2``); another part's value only when its own part states none
    before it (a value carried forward from an earlier part); a value stated after it in its own part only when nothing
    else is in scope (the value given on the next line); never a later part's value. The request's values hold everywhere.
    So a binding stated in one part never validates a calculation in another part that states its own value.

    ``in_force`` (an evaluation that writes no value for the symbol: the symbolic side under its bindings, an order between
    bound symbols, an equation's parameters) keeps only the value in force: the latest stated before the calculation in
    its part (a whole root set when that is the latest), with those of its own statements. When the answer stated
    another value of the symbol before it in the same part, which of them the calculation meant is a reading the answer
    did not state, so the second element is True and a failure of the check is a warning (INT-SUBJ-004), never an error.
    Otherwise (a written substitution, R7) every value in scope may match: the written value shows which one was meant."""
    request = [b for b in pool if b.source == "request"]
    answer = [b for b in pool if b.source != "request"]
    if not answer:
        return tuple(request), False
    order, part_of = _scope_maps(ctx)
    rel = ctx.rel
    rel_ids = set(rel.statement_ids)
    rel_order = max((order.get(s, -1) for s in rel.statement_ids), default=len(order))
    rel_part = rel.part

    def bo(b: Binding) -> int:
        return order.get(b.statement_id, -1)

    def bp(b: Binding) -> str:
        return part_of.get(b.statement_id, "")

    same = [b for b in answer if b.statement_id in rel_ids]
    own = [b for b in answer if b.statement_id not in rel_ids and bp(b) == rel_part and bo(b) < rel_order]
    earlier = [b for b in answer if b.statement_id not in rel_ids and bp(b) != rel_part and bo(b) < rel_order]
    later = [b for b in answer if b.statement_id not in rel_ids and bp(b) == rel_part and bo(b) > rel_order]
    if same or own:
        pool_in_scope, alternatives = own, same
    elif earlier:
        pool_in_scope, alternatives = earlier, []
    else:
        pool_in_scope, alternatives = later, []
    if not in_force:
        return tuple(request + pool_in_scope + alternatives), False
    picked = list(alternatives)
    rebound = False
    if pool_in_scope:
        last = max(pool_in_scope, key=lambda b: (bo(b), b.start)) if pool_in_scope is not later else min(pool_in_scope, key=lambda b: (bo(b), b.start))
        group = [b for b in pool_in_scope if b.source == "root" and b.statement_id == last.statement_id] if last.source == "root" else [last]
        picked = group + picked
        rest = [b for b in pool_in_scope if b not in group]
        rebound = any(not any(b.same_as(c) for c in picked) for b in rest)
    return tuple(request + picked), rebound


def _visible_bindings(ctx: "_Ctx", name: str, *, in_force: bool = False) -> tuple[Binding, ...]:
    """The bindings of ``name`` the relation of this check may use (:func:`_scoped`)."""
    return _scoped(ctx, tuple(ctx.doc.bindings.get(name, ())), in_force=in_force)[0]


def _visible_substitutions(ctx: "_Ctx", name: str) -> tuple[Binding, ...]:
    """The values the answer substituted for ``name`` (readings of a symbol it binds nowhere), scoped as bindings are."""
    return _scoped(ctx, tuple(ctx.doc.substitutions.get(name, ())), in_force=False)[0]


def _in_force(ctx: "_Ctx", name: str) -> tuple[Binding, ...]:
    """The value in force of ``name`` for an evaluation (:func:`_scoped`); a rebinding earlier in the part makes the check's
    failure a warning, with the reason in the description."""
    blist, rebound = _scoped(ctx, tuple(ctx.doc.bindings.get(name, ())), in_force=True)
    if rebound:
        ctx.warn(f"'{name}' was given another value earlier in this part; the check uses the value in force (the latest stated before it), "
                 f"and which one the calculation meant is a reading")
    return blist


def _needs_angle(nodes: list[Node]) -> bool:
    for node in nodes:
        for n in walk(node):
            if isinstance(n, Func):
                if n.name in ("arcsin", "arccos", "arctan"):
                    return True
                if n.name in ("sin", "cos", "tan") and not isinstance(n.arg, Degrees) and not any(isinstance(m, Sym) and m.kind == "constant" for m in walk(n.arg)):
                    return True
    return False


#: π/180 rounded up to seven significant figures: turns a half-width written in degrees into radians (a short literal that is
#: never narrower than the true factor, 0.01745329…)
_PI_DEGREE_HI = Fraction(174533, 10 ** 7)
assert _PI_DEGREE_HI >= pi_interval().hi / 180


def _angle_hint(ctx: "_Ctx", nodes: list[Node]) -> str:
    """``deg`` (``rad``) when every bare number a sin, cos or tan of the relation takes is written in degrees (in radians)
    somewhere in the answer or the request ('a force at 60° to the horizontal' and '10 cos 60'), so that unit is its only
    reading; '' when an angle is written in neither, both, or is no plain numeral (both readings stay)."""
    args: list[str] = []
    for node in nodes:
        for n in walk(node):
            if isinstance(n, Func) and n.name in ("sin", "cos", "tan") and isinstance(n.arg, Num):
                args.append(" ".join(n.arg.number.text.split()))
    if not args:
        return ""
    texts = [ctx.doc.text[:200_000]] + ([ctx.doc.request_text[:200_000]] if ctx.doc.request_text else [])
    hints = set()
    for a in dict.fromkeys(args):
        if not re.fullmatch(r"\d{1,6}(?:\.\d{1,6})?", a):
            return ""
        deg = any(re.search(rf"(?<![\d.]){re.escape(a)}\s?(?:°|degrees?\b)", t) for t in texts)
        rad = any(re.search(rf"(?<![\d.]){re.escape(a)}\s?(?:rad\b|radians?\b)", t) for t in texts)
        if deg == rad:
            return ""
        hints.add("deg" if deg else "rad")
    return hints.pop() if len(hints) == 1 else ""


def _whole_value(node: Node) -> bool:
    """A value written as a whole number with no point and no power of ten (``30°``, ``2 rad``)."""
    v = value_of(node)
    return v is not None and v[1] is not None and not v[1].has_point and not v[1].scientific and v[1].base == 10


def _degrees_against_radians(pairs: list[tuple[Node, Node]]) -> bool:
    """A value in degrees on one side of the relation and a radian measure (a value with a unit of angle, or π) on the
    other, with no degrees there: '30° = 0.524 rad', '2 rad = 115°', '180° = π rad'. Such sides are never compared as
    written; the degrees are converted with the π/180 enclosure."""
    def has_deg(n: Node) -> bool:
        return any(isinstance(m, Degrees) for m in walk(n))

    def has_rad(n: Node) -> bool:
        for m in walk(n):
            if isinstance(m, Sym) and m.kind == "constant" and m.name == "π":
                return True
            if isinstance(m, Quantity) and not m.unit.unknown and len(m.unit.readings) == 1:
                r = m.unit.readings[0]
                if r.dim is not None and r.dim.angle and not any(r.dim.exps) and r.factor == 1:
                    return True
        return False
    for c, sn in pairs:
        dc, ds = has_deg(c), has_deg(sn)
        if dc != ds and has_rad(sn if dc else c):
            return True
    return False


def _readings(nodes: list[Node], *, symbol_units: bool = False, force: Optional[str] = None, affine: tuple[bool, ...] = (False,),
              degrees_si: bool = False, sym_units: tuple[UnitExpr, ...] = (), both: bool = False, angle_hint: str = "") -> tuple[list[Reading], bool]:
    """Every reading of a check (at most 4: ST-PARSE-002 beyond) and whether it is restricted to the
    reading as written by an unknown unit. ``both`` keeps the as-written and the SI readings apart (a unit companion).
    ``angle_hint`` (``deg`` or ``rad``, :func:`_angle_hint`): the unit the answer or the request writes a trig function's
    bare angle in, which is then its only reading."""
    modes, unknown, ambiguous = _reading_modes(nodes, symbol_units=symbol_units, force=force, sym_units=sym_units, both=both)
    needs = _needs_angle(nodes)
    angles = ([angle_hint] if angle_hint in ("deg", "rad") else ["deg", "rad"]) if needs else ["rad"]
    unit_choices: list[tuple[tuple[int, int], ...]] = [()]
    starts: list[tuple[int, int]] = []
    for node in nodes:
        for n in walk(node):
            if isinstance(n, Quantity) and len(n.unit.readings) > 1:
                starts.append((n.start, len(n.unit.readings)))
    for start, count in starts:
        unit_choices = [c + ((start, i),) for c in unit_choices for i in range(count)]
    out: list[Reading] = []
    for mode in modes:
        for ang in angles:
            choices = unit_choices if mode == "si" else [()]
            for ch in choices:
                for aff in (affine if mode == "si" else (False,)):
                    parts = ["SI" if mode == "si" else "as written"]
                    if len(angles) > 1 or (needs and angle_hint):
                        parts.append("angles in degrees" if ang == "deg" else "angles in radians")
                    if ch:
                        parts.append(", ".join(f"unit reading {i + 1}" for _s, i in ch))
                    if len(affine) > 1 or aff:
                        parts.append("with the affine offset" if aff else "without the affine offset (a change)")
                    out.append(Reading(si=mode == "si", units=ch, angle=ang, affine=aff, degrees_si=degrees_si and mode == "si",
                                       label=", ".join(parts)))
    if len(out) > 4:
        raise EncodeError("ST-PARSE-002", f"the relation has {len(out)} readings (units, angles, ambiguous unit symbols); the bound per check is 4")
    return out, unknown


# --------------------------------------------------------------------------- interval readings (R3)


def _traced_symbols(doc: StemDocument) -> dict[tuple[int, int], str]:
    """Numerals the answer substituted for a symbol (``m·a = 3.0 × 5`` traces 5 to a), by offsets."""
    out: dict[tuple[int, int], str] = {}
    for rel in doc.relations:
        if rel.kind != "sub":
            continue
        for sym, node in rel.pairs:
            if isinstance(node, (Num, Quantity)):
                out[(node.start, node.end)] = sym
    return out


def _carried(doc: StemDocument, leaf: Node, traced: Optional[dict[tuple[int, int], str]] = None) -> Optional[Binding]:
    """The answer's own earlier result that the numeral ``leaf`` carries: traced by symbol (the numeral
    was substituted for a symbol whose earlier result has this value), or by an equal numeral with the
    same unit (a bare numeral may drop the unit). Only ever widens what the engine accepts."""
    num = leaf.number  # type: ignore[attr-defined]
    unit = leaf.unit if isinstance(leaf, Quantity) else None
    sym = (traced or {}).get((getattr(leaf, "start", -1), getattr(leaf, "end", -1)))
    for blist in doc.bindings.values():
        for b in blist:
            if b.source != "result" or b.end > getattr(leaf, "start", 0):
                continue
            if abs(b.value) != abs(num.value):
                continue
            if sym is not None and b.symbol == sym:
                return b
            if unit is None or b.unit is None or b.unit.text == unit.text or (b.si is not None and b.si == si_value(num.value, unit)):
                return b
    return None


def _interval_leaves(ctx: _Ctx, node: Node, *, exact_mode: bool) -> dict[tuple[int, int], IntervalLeaf]:
    """R3 interval readings of the numerals of the computed side: carried intermediates and written
    constants (D3a). At most ``max_interval_operands`` (ST-LIM-001 beyond)."""
    out: dict[tuple[int, int], IntervalLeaf] = {}
    if exact_mode:
        return out
    traced = _traced_symbols(ctx.doc)
    for leaf in _leaves(node):
        num = leaf.number
        unit = leaf.unit if isinstance(leaf, Quantity) else None
        if num.value == 0:
            continue
        hw = num.half_width
        key = (leaf.start, leaf.end)
        carried = _carried(ctx.doc, leaf, traced)
        if carried is not None and hw > 0:
            out[key] = IntervalLeaf(num.value - hw, num.value + hw, "carried",
                                    f"the written {num.text} carries the answer's earlier result for '{carried.symbol}' ({carried.statement_id}); "
                                    f"it ranges over its rounding interval")
            continue
        factor = Fraction(1)
        dim = None
        if unit is not None:
            if unit.unknown or len(unit.readings) != 1 or unit.readings[0].factor is None:
                continue
            factor = unit.readings[0].factor
            dim = unit.readings[0].dim
        m = match_written(num.value * factor, hw * abs(factor), num.sig_figs, dim, unit_given=unit is not None, profile_key=ctx.profile_key)
        if m is not None:
            lo, hi = m.interval()
            out[key] = IntervalLeaf(lo / factor if factor > 0 else hi / factor, hi / factor if factor > 0 else lo / factor, "constant", m.note)
            ctx.detail(f"written constant: {num.text} read as {m.constant.name} (rounding interval and booklet value)")
    if len(out) > ctx.doc.limits.max_interval_operands:
        raise EncodeError("ST-LIM-001", f"{len(out)} operands with interval readings; the bound per check is {ctx.doc.limits.max_interval_operands}")
    return out


# --------------------------------------------------------------------------- symbol domains


def _product_groups(node: Node) -> dict[int, list[Node]]:
    """For each direct factor of a flattened product (and term of a flattened sum) of ``node``, the
    closed siblings in that product: a substitution written in another order still matches."""
    groups: dict[int, list[Node]] = {}
    for n in walk(node):
        if isinstance(n, BinOp) and n.op in "*+":
            items = _flatten_same(n, n.op)
            closed = [m for m in items if is_closed(m)]
            for m in items:
                groups.setdefault(id(m), closed)
    return groups


def _flatten_same(node: Node, op: str) -> list[Node]:
    out: list[Node] = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, BinOp) and cur.op == op:
            stack.append(cur.right)
            stack.append(cur.left)
        else:
            out.append(cur)
    return out


def _affine_si(value: Fraction, unit: Optional[UnitExpr]) -> Optional[tuple[Fraction, Fraction]]:
    """For a value written on an offset scale (``unit`` exactly °C or °F): ``(f·v, f·(v + o))``, the value as a temperature
    difference and as a temperature, both in kelvin; None for any other unit."""
    if unit is None or unit.unknown or len(unit.readings) != 1 or unit.readings[0].affine is None:
        return None
    f, o = unit.readings[0].affine
    return f * value, f * (value + o)


def _binding_range(b: Binding) -> tuple[Fraction, Fraction, Optional[tuple[Fraction, Fraction]], Optional[tuple[Fraction, Fraction]]]:
    """``(lo, hi)`` as written and in SI of one binding: a point when it is exact (an integer or fraction
    with no unit), else its rounding interval. The fourth element is the absolute temperature in kelvin of a value on
    an offset scale (°C, °F), whose SI range is then the difference reading (section 6.1); None otherwise."""
    exact = b.unit is None and not b.number.has_point and not b.number.scientific
    h = Fraction(0) if exact else b.number.half_width
    lo, hi = b.value - h, b.value + h
    si = None
    si_abs = None
    s = b.si
    if s is not None and b.unit is not None and b.unit.readings and b.unit.readings[0].factor is not None:
        f = abs(b.unit.readings[0].factor)
        si = (s - h * f, s + h * f)
    elif b.unit is None and b.wrapper == "%":
        si = (lo / 100, hi / 100)
    elif (lo_t := _affine_si(lo, b.unit)) is not None and (hi_t := _affine_si(hi, b.unit)) is not None:
        si, si_abs = (lo_t[0], hi_t[0]), (lo_t[1], hi_t[1])  # the factor of °C and °F is positive
    return lo, hi, si, si_abs


def _domain_from_bindings(name: str, blist: tuple[Binding, ...]) -> SymbolDomain:
    d = SymbolDomain(name)
    for b in blist:
        lo, hi, si, si_abs = _binding_range(b)
        g = grounding("request") if b.source == "request" else grounding("figure", f"value of '{name}' stated in {b.statement_id} ({b.source})")
        d.add(lo, hi, si, g, f"{name} = {b.number.text}{(' ' + b.unit.text) if b.unit else ''} ({b.source}, {b.statement_id})", si_abs=si_abs)
    return d


def _substitution_domain(ctx: _Ctx, name: str) -> Optional[SymbolDomain]:
    """A symbol the answer binds nowhere but gives a value by substitution (``mg = 5.0 × 9.81`` reads
    m as 5.0): its readings, each widened to the other values of its product group (a substitution
    written in another order), scoped by part and statement order as bindings are."""
    subs = _visible_substitutions(ctx, name)
    if not subs:
        return None
    d = SymbolDomain(name)
    seen: set[tuple[Fraction, Fraction]] = set()
    for b in subs:
        lo, hi, si, si_abs = _binding_range(b)
        if (lo, hi) not in seen:
            seen.add((lo, hi))
            d.add(lo, hi, si, grounding("figure", f"value substituted for '{name}' in {b.statement_id}"), f"{name} = {b.number.text} (substituted in {b.statement_id})",
                  si_abs=si_abs)
        for alt in _group_alternatives(ctx, b):
            v = value_of(alt)
            if v is None or v[1] is None:
                continue
            h = v[1].half_width
            key = (v[0] - h, v[0] + h)
            if key in seen:
                continue
            seen.add(key)
            si_alt = None
            s = si_value(v[0], v[2], v[3])
            if s is not None and v[2] is not None and v[2].readings and v[2].readings[0].factor is not None:
                f = abs(v[2].readings[0].factor)
                si_alt = (s - h * f, s + h * f)
            d.add(key[0], key[1], si_alt, grounding("figure", f"a value of the product in which '{name}' was substituted ({b.statement_id})"),
                  f"{name} = {v[1].text} (another factor of the same substitution, {b.statement_id})")
    return d


def _group_alternatives(ctx: _Ctx, b: Binding) -> list[Node]:
    for rel in ctx.doc.relations:
        if rel.kind != "sub" or not rel.pairs:
            continue
        for sym, node in rel.pairs:
            if sym == b.symbol and getattr(node, "start", -1) == b.start:
                num_side = _numeric_side(rel)
                if num_side is None:
                    return []
                return [m for m in _product_groups(num_side).get(id(node), []) if m is not node]
    return []


def _numeric_side(rel: Relation) -> Optional[Node]:
    left, right = rel.left.node if rel.left else None, rel.right.node if rel.right else None
    if right is not None and is_closed(right):
        return right
    if left is not None and is_closed(left):
        return left
    return None


def _install_domains(ctx: _Ctx, domains: dict[str, SymbolDomain], reading: Reading, tag: str) -> tuple[dict[str, Term], dict[str, Interval], frozenset[str]]:
    """Declare one IR variable per symbol for this reading, with its domain premise (an OR of equalities
    or intervals). Returns the encoder's environment, the Python hulls and the symbols that need Form S."""
    hit = ctx.cache.get(("domains", tag, reading.si, reading.affine))
    if hit is not None:
        return hit
    b = ctx.builder
    env: dict[str, Term] = {}
    hulls: dict[str, Interval] = {}
    needs_s: set[str] = set()
    for name, dom in domains.items():
        ranges = dom.ranges(reading.si, reading.si and reading.affine)
        hull = Interval(min(r[0] for r in ranges), max(r[1] for r in ranges))
        hulls[name] = hull
        pinned = len(ranges) == 1 and ranges[0][0] == ranges[0][1]
        role = "pinned" if pinned else "interval"
        var = b.user_symbol(name, role=role, tag=tag, meaning=f"'{name}' ({'; '.join(dom.labels)[:600]})" + (f" [{reading.label}]" if tag else ""))
        m = max(abs(hull.lo), abs(hull.hi))
        k = 0
        if m != 0:
            e = floor_log10(m)
            k = 0 if -12 <= e < 12 else e
        scale = Fraction(10) ** k
        alts = []
        for lo, hi in ranges:
            v = {"op": "var", "name": var}
            if lo == hi:
                alts.append({"op": "eq", "left": v, "right": real(lo / scale)})
            else:
                alts.append({"op": "and", "args": [{"op": "ge", "left": v, "right": real(lo / scale)}, {"op": "le", "left": v, "right": real(hi / scale)}]})
        expr = nary("or", alts) if len(alts) > 1 else alts[0]
        ground = dom.groundings[0] if len({str(g) for g in dom.groundings}) == 1 else grounding("figure", "values stated for the symbol in the report or the request")
        if dom.booklet:
            ground = dom.groundings[0]
        b.premise(f"B_{var}", expr, "; ".join(dom.labels)[:1000], ground)
        env[name] = var_term(var, k)
        if not pinned:
            needs_s.add(name)
    out = (env, hulls, frozenset(needs_s))
    ctx.cache[("domains", tag, reading.si, reading.affine)] = out
    return out


def _dim_of(node: Node, dims: dict[str, Optional[Dimension]]) -> Optional[Dimension]:
    """The dimension of ``node`` from its units and the dimensions of its symbols; None when any part is unknown."""
    if isinstance(node, Quantity):
        return None if node.unit.unknown else node.unit.dim
    if isinstance(node, WithUnit):
        return None if node.unit.unknown else node.unit.dim
    if isinstance(node, Num):
        return DIMENSIONLESS
    if isinstance(node, Sym):
        if node.kind == "constant":
            return DIMENSIONLESS
        return dims.get(node.name)
    if isinstance(node, (Neg, Abs)):
        return _dim_of(node.arg, dims)
    if isinstance(node, Percent):
        return DIMENSIONLESS
    if isinstance(node, BinOp):
        a, b = _dim_of(node.left, dims), _dim_of(node.right, dims)
        if a is None or b is None:
            return None
        if node.op in "+-":
            return a if a.same_physical(b) else None
        return a * b if node.op == "*" else a / b
    if isinstance(node, Pow):
        a = _dim_of(node.base, dims)
        return None if a is None else a.power(node.exp)
    if isinstance(node, Root):
        a = _dim_of(node.arg, dims)
        if a is None or any(e % 2 for e in a.exps):
            return None
        return Dimension(tuple(e // 2 for e in a.exps), a.angle // 2)  # type: ignore[arg-type]
    if isinstance(node, Func):
        return DIMENSIONLESS
    return None


def _symbol_dims(ctx: _Ctx, names: list[str]) -> dict[str, Optional[Dimension]]:
    out: dict[str, Optional[Dimension]] = {}
    for n in names:
        ds = set()
        ok = True
        for b in _visible_bindings(ctx, n) + _visible_substitutions(ctx, n):
            if b.unit is None or b.unit.unknown or b.unit.dim is None:
                ok = False
                break
            ds.add(b.unit.dim)
        out[n] = ds.pop() if ok and len(ds) == 1 else None
    return out


def _booklet_for(ctx: _Ctx, name: str, sym_side: Node, num_side: Node) -> Optional[BookletReading]:
    """D3b: a booklet reading of the unbound ``name`` whose dimension the stated relation confirms."""
    names = [n for n in symbols(sym_side) if n != name]
    dims = _symbol_dims(ctx, names)
    target = _dim_of(num_side, {})
    if target is None or not _units_in(num_side):
        return None
    fits = []
    for c in constants_for_symbol(name, ctx.profile_key):
        trial = dict(dims)
        trial[name] = c.dim
        d = _dim_of(sym_side, trial)
        if d is not None and d.same_physical(target):
            fits.append(c)
    if len(fits) != 1:
        return None
    return booklet_reading(name, ctx.profile_key, fits[0].dim)


# --------------------------------------------------------------------------- comparison problems (eq, cnv, res, tgt, sub evaluation)


@dataclass
class _Side:
    """One computed/stated pair under one reading and sign."""

    c: Term
    s: Term
    h: Fraction
    s_value: Optional[Fraction]


def _compare(ctx: _Ctx, pairs: list[tuple[Node, Node]], *, kind: str, tau: Fraction, h_written: list[Fraction], readings: list[Reading],
             intervals: dict[tuple[int, int], IntervalLeaf], env_for: Optional[callable] = None, signs: tuple[int, ...] = (1,),
             label: str = "computed value", stated_label: str = "stated value", force_form_s: bool = False,
             h_scale_nodes: Optional[list[tuple[Node, Node]]] = None, affine_symbols: frozenset[str] = frozenset(),
             combine: str = "or", si_pairs: Optional[list[tuple[Node, Node]]] = None, h_max: bool = False, h_of_computed: bool = False) -> None:
    """Build a Form E or Form S comparison ``|C − S| <= h + τ·|C|`` over every reading (OR) and every
    sign choice of a ``±`` (AND). ``pairs`` are (computed node, stated node) per operand combination;
    ``h_written`` their half-widths as written. ``env_for(reading, tag)`` installs symbol domains;
    ``affine_symbols`` are the symbols bound to a temperature on an offset scale (section 6.1).

    A unit companion (ST-UNIT-003) passes ``combine="implies"``: the conclusion is that the as-written readings imply the SI
    readings (Form E), so the check fails exactly when the numbers hold as written and fail in SI; under interval readings
    (Form S) it is the SI readings alone. ``si_pairs`` replaces ``pairs`` in the SI readings (bare numerals read in the units
    of the bindings they repeat). ``h_max`` combines the two half-widths of a value set against a value (``h_scale_nodes``)
    by their maximum, not their sum: one value must be a rounding of the other (R7, R8). ``h_of_computed``: the half-width is
    the computed node's (a substitution compares its written numeric side, set as the computed node, with the symbolic side
    under the bindings), so it is turned into each reading's units by that node's unit."""
    b = ctx.builder
    bands: list[dict] = []
    band_si: list[bool] = []
    uses_intervals = force_form_s
    errors: list[EncodeError] = []
    total = len(pairs) * len(readings) * len(signs)
    idx = 0
    frames: set[int] = set()
    labels: list[str] = []
    for ci, (cnode0, snode0) in enumerate(pairs):
        for ri, reading in enumerate(readings):
            cnode, snode = si_pairs[ci] if (si_pairs is not None and reading.si) else (cnode0, snode0)
            sign_bands: list[dict] = []
            failed = False
            for sign in signs:
                idx += 1
                rd = Reading(si=reading.si, units=reading.units, angle=reading.angle, affine=reading.affine, sign=sign, degrees_si=reading.degrees_si,
                             label=reading.label + ("" if len(signs) == 1 else (", + branch" if sign > 0 else ", − branch")))
                tag = "" if ri == 0 else f"r{ri + 1}"
                try:
                    env, hulls, needs_s = env_for(rd, tag) if env_for is not None else ({}, {}, frozenset())
                    enc = Encoder(b, rd, env=env, intervals=intervals, symbol_hulls=hulls, interval_symbols=needs_s, cache=ctx.cache,
                                  affine_symbols=affine_symbols)
                    c = enc.term(cnode)
                    s = enc.term(snode)
                    scale = _scale_for(cnode if h_of_computed else snode, rd, enc)
                    h = h_written[ci] * scale
                    if h_scale_nodes is not None:
                        extra_node = h_scale_nodes[ci][0]
                        if extra_node is not None:
                            h_other = _value_half_width(extra_node) * _scale_for(extra_node, rd, enc)
                            h = max(h, h_other) if h_max else h + h_other
                    uses_intervals |= enc.uses_intervals
                    if enc.enclosures:
                        ctx.detail("function values and constants as numeric enclosures computed by the STEM pack (width at most 10⁻¹⁵ relative), not "
                                   "engine results; the engine decides the stated relation over every value in them: " + ", ".join(dict.fromkeys(enc.enclosures)))
                    if enc.exact_used:
                        ctx.detail("exact values: " + ", ".join(dict.fromkeys(enc.exact_used)))
                except EncodeError as exc:
                    errors.append(exc)
                    failed = True
                    break
                suffix = "" if total == 1 else f"_{idx}"
                frame = _common_frame(c, s)
                frames.add(frame)
                cname = b.declare(f"c{suffix}", meaning=f"the {label} ({rd.label})", role="pinned")
                rname = b.declare(f"r{suffix}", meaning=f"the {stated_label} ({rd.label})", role="pinned")
                note = _FIGURE_SI if (rd.si and _si_differs([cnode, snode])) else ""
                b.premise(f"C_DEF{suffix}", {"op": "eq", "left": {"op": "var", "name": cname}, "right": to_frame(c, frame)},
                          f"{cname} is the {label}, {render(cnode)[:400]} ({rd.label})", grounding("figure", note))
                b.premise(f"R{suffix}", {"op": "eq", "left": {"op": "var", "name": rname}, "right": to_frame(s, frame)},
                          f"{rname} is the {stated_label}, {render(snode)[:400]} ({rd.label})", grounding("figure", note))
                sign_bands.append(band_expr({"op": "var", "name": cname}, {"op": "var", "name": rname}, literal_in_frame(h, frame), tau))
            if failed:
                continue
            bands.append(nary("and", sign_bands) if len(sign_bands) > 1 else sign_bands[0])
            band_si.append(reading.si)
            labels.append(reading.label + (f" (operand reading {ci + 1})" if len(pairs) > 1 else ""))
    if not bands:
        raise errors[0] if errors else EncodeError("ST-UNDEC-001", "no reading of the relation could be encoded")
    if any(isinstance(e, AffineUndecided) for e in errors):
        ctx.warn("the SI reading is not established (a temperature on an offset scale combined with other terms); the relation is checked in "
                 "its other readings only")
    ctx.readings = list(dict.fromkeys(labels))
    nonzero = sorted(f for f in frames if f != 0)
    if nonzero:
        b.note("decimal exponent factored: " + ", ".join(f"10^{f}" for f in nonzero))
        ctx.detail("decimal exponent factored: " + ", ".join(f"10^{f}" for f in nonzero))
    b.note("readings: " + "; ".join(ctx.readings))
    if combine == "implies":
        aw = [x for x, si in zip(bands, band_si) if not si]
        si_bands = [x for x, si in zip(bands, band_si) if si]
        if not aw or not si_bands:
            raise EncodeError("ST-UNDEC-001", "the unit companion needs both an as-written and an SI reading")
        aw_band = nary("or", aw) if len(aw) > 1 else aw[0]
        si_band = nary("or", si_bands) if len(si_bands) > 1 else si_bands[0]
        if uses_intervals:
            ctx.form, ctx.query, ctx.expected = "S", "satisfiability", "SATISFIABLE"
            ctx.detail("interval readings: the companion is the SI reading alone (Form S); the check beside it covers the as-written reading")
            b.premise("BAND", si_band, "the stated value lies in its tolerance band under some admissible SI reading", grounding("figure"))
        else:
            ctx.form, ctx.query, ctx.expected = "E", "entailment", "ENTAILED"
            ctx.conclusion = ("UNITS", {"op": "implies", "left": aw_band, "right": si_band},
                              "the numbers do not hold as written while failing in SI (the units are converted)")
        return
    band = nary("or", bands) if len(bands) > 1 else bands[0]
    if uses_intervals:
        ctx.form = "S"
        ctx.query = "satisfiability"
        ctx.expected = "SATISFIABLE"
        b.premise("BAND", band, "the stated value lies in its tolerance band under some admissible reading", grounding("figure"))
    else:
        ctx.form = "E"
        ctx.query = "entailment"
        ctx.expected = "ENTAILED"
        ctx.conclusion = ("STATED", band, "the stated value lies in its tolerance band")


_FIGURE_SI = "figure stated in the report itself, converted to SI by exact unit-table factors"


def _common_frame(c: Term, s: Term) -> int:
    sv = s.value
    for f in (0, c.k, s.k):
        try:
            to_frame(c, f)
            to_frame(s, f)
            if sv is not None:
                literal_in_frame(sv, f)
            return f
        except LiteralTooLong:
            continue
    if sv is not None:
        return frame_for(c, sv)
    raise LiteralTooLong("no decimal frame holds both sides within the literal bound")


# --------------------------------------------------------------------------- eq


def _unit_role(ctx: _Ctx) -> str:
    """How the ST-UNIT-003 companion bears on this check: ``written``/``traced`` for the companion itself, ``main`` for the
    check a ``written`` companion accompanies (it then decides the relation under the as-written and the SI reading alike),
    '' otherwise."""
    rel = ctx.rel
    if rel.kind == "unit":
        return rel.unit_case or "written"
    return "main" if rel.unit_reason else ""


def _unit_setup(ctx: _Ctx, unit: str, pairs: list[tuple[Node, Node]]) -> Optional[list[tuple[Node, Node]]]:
    """Record what the unit companion decides (description, severity, defect) and, for a ``traced`` companion, the pairs of
    its SI readings: the bare numerals read in the units of the bindings they repeat."""
    rel = ctx.rel
    if unit == "main":
        ctx.detail(f"the as-written reading is not admissible beside the SI reading ({rel.unit_reason}): both are decided here, and the "
                   f"companion check {rel.check_id}u decides that the numbers do not hold as written while failing in SI")
        return None
    if unit not in ("written", "traced"):
        return None
    ctx.defect = "stem_unit_error"
    if unit == "written":
        ctx.detail(f"ST-UNIT-003: {rel.unit_reason}; this check fails when the numbers hold as written and fail in SI (stem_unit_error); the "
                   f"check {rel.check_id[:-1]} beside it decides the relation under both readings")
        return None
    units = {(a, b): bd for a, b, bd in rel.traced}
    ctx.warn("the bare numbers are read in the units of the bindings whose numbers they repeat, which the report did not state")
    # a numeral that substitutes into no symbol repeats the request's quantity itself (relations._request_traced_companion)
    ctx.detail("ST-UNIT-003: the working uses the bare numbers of " + ", ".join((f"{bd.symbol} = " if bd.symbol else "the request's ")
                                                                             + f"{bd.number.text} {bd.unit.text}" for bd in units.values()
                                                                             if bd.unit is not None)
               + "; read in those units the stated value must still hold (stem_unit_error)")
    if rel.stated_unit is not None:
        ctx.detail(f"the stated value is read in the unit the answer's prose gives it ({rel.stated_unit.text})")
    return [(_with_units(c, units), _stated_in(s, rel.stated_unit)) for c, s in pairs]


def _stated_in(node: Node, unit) -> Node:
    """A bare stated numeral written in ``unit`` (the unit the answer's prose gives it); any other node as it is."""
    if unit is None:
        return node
    if isinstance(node, Num):
        return Quantity(node.number, unit, node.start, node.end)
    if isinstance(node, Neg) and isinstance(node.arg, Num):
        return Neg(Quantity(node.arg.number, unit, node.arg.start, node.arg.end), node.start, node.end)
    return node


def _with_units(node: Node, units: dict) -> Node:
    """``node`` with each numeral at the offsets of ``units`` written in its binding's unit (a :class:`Quantity`), every other
    node as it is. Each node type is rebuilt explicitly."""
    if isinstance(node, Num):
        bd = units.get((node.start, node.end))
        if bd is None or bd.unit is None:
            return node
        # a temperature written in °C read in kelvin carries the converted value (relations.KELVIN_READING)
        return Quantity(bd.number if bd.wrapper == "kelvin" else node.number, bd.unit, node.start, node.end)
    if isinstance(node, BinOp):
        return BinOp(node.op, _with_units(node.left, units), _with_units(node.right, units), node.start, node.end, node.written, node.implicit)
    if isinstance(node, Neg):
        return Neg(_with_units(node.arg, units), node.start, node.end)
    if isinstance(node, Pow):
        return Pow(_with_units(node.base, units), node.exp, node.start, node.end)
    if isinstance(node, Root):
        return Root(_with_units(node.arg, units), node.index, node.start, node.end)
    if isinstance(node, Abs):
        return Abs(_with_units(node.arg, units), node.start, node.end)
    return node


def _uncertainty(cnode: Node, snode: Node) -> Optional[tuple[Node, Node]]:
    """``(value, uncertainty)`` when the stated side is a value with its absolute uncertainty (``1600 ± 32 counts min⁻¹``):
    a binary ``±`` between two written values, stated for a computed side that has no ``±``. A computed value has one
    value, so a stated pair can only be its uncertainty range; ``(3 ± √17)/4`` and ``x = ±2i`` are no such form. A unit
    written after the uncertainty is the value's too."""
    if not isinstance(snode, PlusMinus) or snode.sign != "±" or snode.left is None or _has_plus_minus(cnode):
        return None
    value, unc = snode.left, snode.right
    if not isinstance(value, (Num, Quantity)) or not isinstance(unc, (Num, Quantity)):
        return None
    if isinstance(unc, Quantity):
        if isinstance(value, Quantity) and value.unit.text != unc.unit.text:
            return None
        value = Quantity(value.number, unc.unit, value.start, unc.end) if isinstance(value, Num) else value
    return value, unc


def _eq(ctx: _Ctx) -> None:
    rel = ctx.rel
    combos = _operand_combos(rel.left, rel.right)
    if combos and all(isinstance(c, Ratio) and isinstance(sn, Ratio) for c, sn in combos):
        # a:b = c:d is a·d = b·c over closed terms (design section 7.4): the cross products are compared
        combos = [(BinOp("*", c.left, sn.right, c.start, c.end), BinOp("*", c.right, sn.left, sn.start, sn.end)) for c, sn in combos]
        ctx.detail("a ratio equality a:b = c:d, compared as a·d = b·c")
    scaled = [_antilog_as_concentration(c, sn) for c, sn in combos]
    scale_unit = bool(combos) and all(x is not None for x in scaled)
    if scale_unit:
        combos = [x for x in scaled if x is not None]  # [H⁺] = 10^(−8.2) = 6.31 × 10⁻⁹ mol dm⁻³: the power is read in mol dm⁻³
    approx = _approx(ctx)
    intent, intent_label = _intent_policy(ctx, [n for c in combos for n in c], approx=approx)
    exact_intent = intent == "exact" and rel.op in ("=", "≡")
    ctx.exact_intent = exact_intent
    # a stated rounding reads the stated value as a rounding whatever its spelling: no exact mode (R2)
    rounded = intent == "rounded"
    pairs: list[tuple[Node, Node]] = []
    hs: list[Fraction] = []
    extra: list[tuple[Node, Node]] = []
    intervals: dict[tuple[int, int], IntervalLeaf] = {}
    exact_modes = []
    uncertainty = False
    for cnode, snode in combos:
        width = Fraction(0)
        unc = _uncertainty(cnode, snode) if rel.op in ("=", "≈") else None
        if unc is not None:
            snode, width = unc[0], abs(unc[1].number.value)
            uncertainty = True
            ctx.detail(f"the stated value carries an absolute uncertainty (± {render(unc[1])[:40]}): the computed value must lie within it")
        exact = rel.op in ("=", "≡") and not approx and (exact_intent or (not rounded and _all_exact(cnode) and _all_exact(snode)))
        exact_modes.append(exact)
        h = _stated_half_width(snode, min_sf=_min_sig_figs(cnode), exact_mode=exact, rounded=rounded) + width
        label = _precision_label_after(ctx)
        if label is not None and is_value(snode) and not unc:
            h = _labelled_half_width(ctx, snode, label, h)
        pairs.append((cnode, snode))
        hs.append(h)
        extra.append((cnode if (is_value(cnode) and not exact) else None, snode))  # type: ignore[arg-type]
        intervals.update(_interval_leaves(ctx, cnode, exact_mode=exact))
    exact_mode = all(exact_modes)
    # R2: the relative slack absorbs constants and data written to fewer digits, so it needs a measured operand (a decimal,
    # scientific notation or a unit in the computed expression, or in a stated expression such as 3.912/0.6931; a stated value
    # with a unit; a rounded intermediate or constant); over exact operands a single stated decimal is read as rounded to its
    # last digit (h) and gets no slack from its spelling
    measured = uncertainty or bool(intervals) or any(_measured_numerals(c) for c, _s in pairs) or any(
        _units_in(sn) or (not is_value(sn) and _measured_numerals(sn)) for _c, sn in pairs)
    tau = Fraction(0) if exact_mode else (TAU_APPROX if approx else (TAU_EQUAL if measured else Fraction(0)))
    nodes = [n for p in pairs for n in p]
    unit = _unit_role(ctx)
    hint = _angle_hint(ctx, nodes)
    degrad = not unit and _degrees_against_radians(pairs)
    if degrad:
        # '30° = 0.524 rad': a conversion (R5). The degrees in radians through the π/180 enclosure, never the numbers as
        # written; τ = 0 (the enclosure carries π), and a whole-number angle on the converted side is a given angle (no h)
        readings, unknown = _readings(nodes, force="si", degrees_si=True, angle_hint=hint)
        if not exact_mode:
            tau = TAU_APPROX if approx else Fraction(0)
        extra = [(None if (c is not None and _whole_value(c)) else c, sn) for c, sn in extra]
        ctx.detail("a value in degrees set against a radian measure: the degrees are converted with the π/180 enclosure, never compared as written")
    else:
        readings, unknown = _readings(nodes, force="si" if scale_unit else None, affine=_affine_mode(ctx, nodes), both=bool(unit), angle_hint=hint)
    if hint and _needs_angle(nodes):
        ctx.detail(f"the trig function's angle is written in {'degrees' if hint == 'deg' else 'radians'} in the answer or the request: that reading only")
    if unknown:
        ctx.warn("a unit is not recognised (ST-UNIT-001); the relation is checked as written only")
    elif scale_unit:
        readings = [replace(r, label=r.label + ", the power of ten read in mol dm⁻³") for r in readings]
        ctx.detail("an antilogarithm stated as a concentration (a lone power of ten whose exponent is no integer, 10^(−pH)) is the concentration "
                   "in mol dm⁻³, the unit the pH, pOH, pKa and pKb scales are defined in, and is compared with the stated value in SI; it is never "
                   "read as a bare number in SI, which would take a unit prefix (an integer power of ten) for a change of the exponent")
    if exact_intent:
        ctx.tolerance = intent_label
    elif degrad and not exact_mode:
        ctx.tolerance = ("a conversion between degrees and radians (R5): π/180 as an enclosure, τ = " + _ratio(tau)
                         + "; h of the stated value, and of a converted value written with a decimal point")
    elif exact_mode:
        ctx.tolerance = "exact, by the written form: every operand and the stated value are written exactly (τ = 0, h = 0)"
    elif intent:
        ctx.tolerance = intent_label + ("" if approx else f"; τ = {_ratio(tau)}")
    elif measured:
        ctx.tolerance = "measured, by the written form: a measured operand (a decimal, scientific notation, a unit or a rounded value); τ = 1/100"
    else:
        ctx.tolerance = ("rounded to its stated digits, by the written form: the operands are exact, so the stated value may differ from the computed "
                         "one by half a unit in its last digit (h) and no more (τ = 0)")
    if exact_mode:
        ctx.detail("exact mode: τ = 0, h = 0")
    else:
        ctx.detail(f"τ = {_ratio(tau)}")
    signs = (1, -1) if _has_plus_minus(*nodes) else (1,)
    si_pairs = _unit_setup(ctx, unit, pairs)
    _compare(ctx, pairs, kind="eq", tau=tau, h_written=hs, readings=readings, intervals=intervals, signs=signs, h_scale_nodes=extra,
             combine="implies" if ctx.rel.kind == "unit" else "or", si_pairs=si_pairs)


def _antilog(node: Node) -> bool:
    """``10^(−8.2)``, ``10^{-5.8}``, ``10**-3.3``, ``10^(8.2 − 7.8)``, ``10^(−7)``: a lone power of ten with no unit, the
    antilogarithm of a logarithmic scale (pH, pOH, pKa, ...). An integer exponent is read too (``10^(−7)`` is a bare power
    of ten as the number scanner reads it): pH 7 is as common as pH 8.2. Only where the other side is a concentration is it
    read as one (:func:`_antilog_as_concentration`)."""
    if isinstance(node, Num):
        return node.number.power_of_ten
    return isinstance(node, RealPower) and isinstance(node.base, Num) and node.base.number.value == 10


#: the dimension of a concentration (amount per volume)
_CONCENTRATION = Dimension((-3, 0, 0, 0, 0, 1, 0))
#: the unit the antilogarithm of a concentration scale is in: pH, pOH, pKa and pKb are defined for concentrations in mol dm⁻³
_SCALE_UNIT = parse_unit("mol dm⁻³")


def _concentration_value(node: Node) -> bool:
    """A written value whose unit is a concentration in every reading (``6.31 × 10⁻⁹ mol dm⁻³``, ``0.501 mmol dm⁻³``, ``5.01e-4 M`` in
    chemistry), with no per cent; an unknown or ambiguous unit (``M`` as molar or mega in physics) is not one."""
    unit: Optional[UnitExpr] = None
    if is_value(node):
        v = value_of(node)
        if v is None or v[3]:
            return False
        unit = v[2]
    elif isinstance(node, WithUnit) and is_closed(node.arg):
        unit = node.unit
    if unit is None or unit.unknown or not unit.readings:
        return False
    return all(r.dim is not None and r.dim.same_physical(_CONCENTRATION) and r.factor is not None for r in unit.readings)


def _antilog_as_concentration(cnode: Node, snode: Node) -> Optional[tuple[Node, Node]]:
    """``[H⁺] = 10^(−8.2) = 6.31 × 10⁻⁹ mol dm⁻³``: one side an antilogarithm with no unit, the other a value in a concentration unit.
    The pair with the antilogarithm read in mol dm⁻³ (section 6.4), or None. Read as a bare number in SI it would match the stated
    value in mol m⁻³, a factor of 10³ that an exponent 3 too small reproduces exactly (``10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³``,
    ``10^(−4) = 1.0 × 10⁻⁷ mol dm⁻³``)."""
    if _SCALE_UNIT is None:
        return None
    if _antilog(cnode) and _concentration_value(snode):
        return WithUnit(cnode, _SCALE_UNIT, getattr(cnode, "start", 0), getattr(cnode, "end", 0)), snode
    if _antilog(snode) and _concentration_value(cnode):
        return cnode, WithUnit(snode, _SCALE_UNIT, getattr(snode, "start", 0), getattr(snode, "end", 0))
    return None


def _ratio(t: Fraction) -> str:
    return f"{t.numerator}/{t.denominator}" if t.denominator != 1 else str(t.numerator)


# --------------------------------------------------------------------------- cnv


def _partial_unit(unit: UnitExpr) -> Optional[tuple[Fraction, tuple]]:
    """The factor of the recognised atoms and the signature of the unknown ones (so ``kJ m⁻² yr⁻¹`` and
    ``MJ m⁻² yr⁻¹`` convert though ``yr`` is not in the table)."""
    if not unit.readings:
        return None
    r = unit.readings[0]
    factor = Fraction(1)
    unknown = []
    for a in r.atoms:
        if a.unit is None:
            unknown.append((a.text, a.power))
            continue
        f = a.factor
        if f is None:
            return None
        factor *= f
    return factor, tuple(sorted(unknown))


def _cnv(ctx: _Ctx) -> None:
    rel = ctx.rel
    combos = _operand_combos(rel.left, rel.right)
    approx = _approx(ctx)
    tau = TAU_APPROX if approx else Fraction(0)
    left, right = combos[0]
    intent, intent_label = _intent_policy(ctx, [left, right], approx=approx)
    if intent:
        ctx.tolerance = intent_label
    if intent == "exact" and rel.op in ("=", "≡"):
        # the answer states the conversion is exact: the two values must agree exactly, with no half-widths
        ctx.exact_intent = True
        _exact_conversion(ctx, left, right)
        return
    lv, rv = value_of(left), value_of(right)
    if lv is None or rv is None or lv[2] is None or rv[2] is None:
        raise EncodeError("ST-UNDEC-001", "a conversion between values without units")
    lu, ru = lv[2], rv[2]
    if lu.unknown or ru.unknown:
        pl, pr = _partial_unit(lu), _partial_unit(ru)
        if pl is None or pr is None or pl[1] != pr[1]:
            ctx.warn("a unit is not recognised (ST-UNIT-001); the conversion is checked as written only")
            readings = [Reading(si=False, label="as written")]
            _compare(ctx, [(left, right)], kind="cnv", tau=tau, h_written=[_value_half_width(right)], readings=readings, intervals={},
                     h_scale_nodes=[(left, right)])
            return
        ctx.detail("the unrecognised unit atoms (" + ", ".join(f"{t}^{p}" for t, p in pl[1]) + ") are the same on both sides and cancel")
        _partial_conversion(ctx, left, right, pl[0], pr[0], tau)
        return
    affine = _affine_mode(ctx, [left, right])
    degrees_si = (lv[3] == "°" or rv[3] == "°") and ((lu.dim is not None and lu.dim.angle) or (ru.dim is not None and ru.dim.angle))
    readings, _unknown = _readings([left, right], force="si", affine=affine, degrees_si=bool(degrees_si))
    _compare(ctx, [(left, right)], kind="cnv", tau=tau, h_written=[_value_half_width(right)], readings=readings, intervals={},
             h_scale_nodes=[(left, right)], label="value converted to SI", stated_label="stated value in SI")


def _exact_conversion(ctx: _Ctx, left: Node, right: Node) -> None:
    """A conversion the answer states is exact: the two values agree in SI with no half-widths and τ = 0 (R5, R2)."""
    lv, rv = value_of(left), value_of(right)
    if lv is None or rv is None or lv[2] is None or rv[2] is None or lv[2].unknown or rv[2].unknown:
        raise EncodeError("ST-UNDEC-001", "an exact conversion between values whose units are not both recognised")
    lu, ru = lv[2], rv[2]
    affine = _affine_mode(ctx, [left, right])
    degrees_si = (lv[3] == "°" or rv[3] == "°") and ((lu.dim is not None and lu.dim.angle) or (ru.dim is not None and ru.dim.angle))
    readings, _unknown = _readings([left, right], force="si", affine=affine, degrees_si=bool(degrees_si))
    _compare(ctx, [(left, right)], kind="cnv", tau=Fraction(0), h_written=[Fraction(0)], readings=readings, intervals={},
             label="value converted to SI", stated_label="stated value in SI")


def _change_context(ctx: _Ctx) -> bool:
    """The relation's own clause speaks of a change (a Δ-prefixed symbol, change, difference, rise,
    fall, ...): the clause runs from the last clause boundary before the relation to its end."""
    rel = ctx.rel
    st = ctx.doc.statement(rel.statement_ids[-1]) if rel.statement_ids else None
    lo = st.start if st is not None else max(0, rel.start - 200)
    head = ctx.doc.text[lo:rel.start]
    cut = max(head.rfind(","), head.rfind(";"), head.rfind(". "), head.rfind(" and "), head.rfind("\n"))
    clause = (head[cut + 1:] if cut >= 0 else head) + ctx.doc.text[rel.start:rel.end]
    low = clause.lower()
    return "Δ" in clause or any(w in low for w in _CHANGE_WORDS if w != "Δ")


def _partial_conversion(ctx: _Ctx, left: Node, right: Node, fl: Fraction, fr: Fraction, tau: Fraction) -> None:
    lv, rv = value_of(left), value_of(right)
    assert lv is not None and rv is not None and lv[1] is not None and rv[1] is not None
    c_val, s_val = lv[0] * fl, rv[0] * fr
    h = rv[1].half_width * abs(fr) + lv[1].half_width * abs(fl)
    b = ctx.builder
    c, s = lit(c_val), lit(s_val)
    frame = _common_frame(c, s)
    b.declare("c", meaning="the left value in the recognised SI factors", role="pinned")
    b.declare("r", meaning="the stated value in the recognised SI factors", role="pinned")
    b.premise("C_DEF", {"op": "eq", "left": {"op": "var", "name": "c"}, "right": to_frame(c, frame)}, f"c is {render(left)}", grounding("figure"))
    b.premise("R", {"op": "eq", "left": {"op": "var", "name": "r"}, "right": to_frame(s, frame)}, f"r is {render(right)}", grounding("figure"))
    ctx.readings = ["SI for the recognised unit atoms"]
    if frame:
        b.note(f"decimal exponent factored: 10^{frame}")
    ctx.conclusion = ("STATED", band_expr({"op": "var", "name": "c"}, {"op": "var", "name": "r"}, literal_in_frame(h, frame), tau),
                      "the converted value lies in the stated value's band")


# --------------------------------------------------------------------------- res, tgt, giv


def _res(ctx: _Ctx) -> None:
    rel = ctx.rel
    combos = _operand_combos(rel.left, rel.right)
    pairs = [(l, r) for l, r in combos]
    nodes = [n for p in pairs for n in p]
    readings, unknown = _readings(nodes, affine=_affine_mode(ctx, nodes))
    if unknown:
        ctx.warn("a unit is not recognised (ST-UNIT-001); the restatement is checked as written only")
    intent, intent_label = _intent_policy(ctx, nodes, approx=False)
    exact = intent == "exact" and _clause_states_exactness(ctx)
    hs = [Fraction(0) if exact else _value_half_width(r) for _l, r in pairs]
    if exact:
        ctx.tolerance = intent_label
        ctx.exact_intent = True
    _compare(ctx, pairs, kind="res", tau=Fraction(0), h_written=hs, readings=readings, intervals={},
             h_scale_nodes=None if exact else [(l, r) for l, r in pairs], label="final value of the chain", stated_label="restated value", h_max=True)


def _tgt(ctx: _Ctx) -> None:
    rel = ctx.rel
    combos = _operand_combos(rel.left, rel.right)
    pairs = [(l, r) for l, r in combos]
    nodes = [n for p in pairs for n in p]
    readings, _unknown = _readings(nodes, affine=_affine_mode(ctx, nodes))
    tau = TAU_APPROX if rel.approx else Fraction(0)
    hs = [_value_half_width(r) for _l, r in pairs]
    ctx.warn("the show-that target is the request's reading of the answer")
    _compare(ctx, pairs, kind="tgt", tau=tau, h_written=hs, readings=readings, intervals={}, h_scale_nodes=[(l, r) for l, r in pairs],
             label="answer's final value", stated_label="show-that target", h_max=True)
    _regound_stated(ctx, "request")


def _regound_stated(ctx: _Ctx, kind: str) -> None:
    """The stated side of a target or given check is the request's value: ground it as such."""
    for p in ctx.builder.premises:
        if p["id"] == "R" or p["id"].startswith("R_"):
            p["grounding"] = grounding(kind)


def _giv(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.right is None or rel.right.node is None or not rel.candidates:
        raise EncodeError("ST-UNDEC-001", "a Given value with no request value to compare")
    node = rel.right.node
    v = value_of(node)
    if v is None or v[1] is None:
        raise EncodeError("ST-UNDEC-001", "a Given value that is not a single value")
    ctx.warn("symbol identity across the request and the answer is a reading")
    b = ctx.builder
    w_aw, w_num, w_unit, w_wrap = v
    # a Given temperature on an offset scale (°C, °F) is a temperature, unless the symbol or the statement names a change
    given = rel.left.node.name if rel.left is not None and isinstance(rel.left.node, Sym) else ""
    absolute = not given.startswith("Δ") and not _change_context(ctx)

    def si_of(value: Fraction, unit: Optional[UnitExpr], wrapper: str) -> Optional[Fraction]:
        out = si_value(value, unit, wrapper)
        if out is None and (temp := _affine_si(value, unit)) is not None:
            out = temp[1] if absolute else temp[0]
        return out

    w_si = si_of(w_aw, w_unit, w_wrap)
    if _affine_si(w_aw, w_unit) is not None or any(_affine_si(c.value, c.unit) is not None for c in rel.candidates):
        ctx.detail("°C/°F " + ("as temperatures, with the offset" if absolute else "as temperature differences (a change)"))
    h_w = w_num.half_width
    f_w = abs(w_unit.readings[0].factor) if (w_unit is not None and w_unit.readings and w_unit.readings[0].factor is not None) else Fraction(1)
    disjuncts: list[dict] = []
    wname = b.declare("w", meaning=f"the Given value {w_num.text}{(' ' + w_unit.text) if w_unit else ''}", role="pinned")
    frame = _frame([w_aw] + ([w_si] if w_si is not None else []) + [c.value for c in rel.candidates])
    # one pinned symbol in SI when every value has an SI reading, else as written
    cand_si = [si_of(c.value, c.unit, c.wrapper) for c in rel.candidates]
    use_si = w_si is not None and all(c is not None for c in cand_si)
    w_val = w_si if use_si else w_aw
    b.premise("W", {"op": "eq", "left": {"op": "var", "name": wname}, "right": literal_in_frame(w_val, frame)}, f"the Given value of {rel.left.node.name if rel.left and isinstance(rel.left.node, Sym) else 'the symbol'}",  # type: ignore[union-attr]
              grounding("figure"))
    for i, cand in enumerate(rel.candidates, 1):
        cname = b.declare(f"b_{i}", meaning=f"the request's {cand.number.text}{(' ' + cand.unit.text) if cand.unit else ''}", role="pinned")
        c_val = cand_si[i - 1] if use_si else cand.value
        f_c = abs(cand.unit.readings[0].factor) if (use_si and cand.unit is not None and cand.unit.readings and cand.unit.readings[0].factor is not None) else Fraction(1)
        tol = max(cand.number.half_width * f_c, h_w * (f_w if use_si else 1))  # one value is a rounding of the other (R7)
        b.premise(f"B_{i}", {"op": "eq", "left": {"op": "var", "name": cname}, "right": literal_in_frame(c_val, frame)},
                  f"the request states {cand.number.text}{(' ' + cand.unit.text) if cand.unit else ''}", grounding("request"))
        disjuncts.append(band_expr({"op": "var", "name": wname}, {"op": "var", "name": cname}, literal_in_frame(tol, frame), Fraction(0)))
    ctx.readings = ["SI" if use_si else "as written"]
    if frame:
        b.note(f"decimal exponent factored: 10^{frame}")
    ctx.conclusion = ("MATCHES", nary("or", disjuncts) if len(disjuncts) > 1 else disjuncts[0], "the Given value matches a value of the request (R7)")


def _frame(values: list[Optional[Fraction]]) -> int:
    vs = [abs(v) for v in values if v is not None and v != 0]
    if not vs:
        return 0
    lo, hi = floor_log10(min(vs)), floor_log10(max(vs))
    if -12 <= lo and hi < 12:
        return 0
    return lo


# --------------------------------------------------------------------------- cmp (values)


def _cmp(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.premise_left is not None:
        _step(ctx)
        return
    combos = _operand_combos(rel.left, rel.right)
    nodes = [n for c in combos for n in c]
    names = sorted({s for n in nodes for s in symbols(n)})
    domains: dict[str, SymbolDomain] = {}
    for name in names:
        blist = _in_force(ctx, name)
        if not blist:
            raise EncodeError("ST-UNDEC-002", f"'{name}' has no stated value")
        domains[name] = _domain_from_bindings(name, blist)
    sym_units = tuple(b.unit for name in names for b in _in_force(ctx, name) if b.unit is not None)
    symbol_units = bool(sym_units)
    readings, unknown = _readings(nodes, symbol_units=symbol_units, sym_units=sym_units, affine=_affine_mode(ctx, nodes, sym_units),
                                  angle_hint=_angle_hint(ctx, nodes))
    if unknown:
        ctx.warn("a unit is not recognised (ST-UNIT-001); the comparison is checked as written only")
    affine_symbols = frozenset(n for n, d in domains.items() if d.affine)
    op = _CMP_OPS.get(rel.op)
    if op is None:
        raise EncodeError("ST-UNDEC-001", f"the relation sign {rel.op!r}")
    b = ctx.builder
    alts: list[dict] = []
    uses_s = any(len(d.values_aw) > 1 for d in domains.values())
    affine_refused = False
    idx = 0
    total = len(combos) * len(readings)
    for (lnode, rnode) in combos:
        for ri, rd in enumerate(readings):
            idx += 1
            tag = "" if ri == 0 else f"r{ri + 1}"
            try:
                env, hulls, needs = _install_domains(ctx, domains, rd, tag)
                enc = Encoder(b, rd, env=env, symbol_hulls=hulls, interval_symbols=needs, cache=ctx.cache, affine_symbols=affine_symbols)
                lt, rt = enc.term(lnode), enc.term(rnode)
            except EncodeError as exc:
                if idx == total and not alts:
                    raise
                if isinstance(exc, AffineUndecided):
                    affine_refused = True
                continue
            uses_s |= enc.uses_intervals or bool(needs)
            (le, re_), _k = align_terms(lt, rt)
            suffix = "" if total == 1 else f"_{idx}"
            ln = b.declare(f"l{suffix}", meaning=f"the left side ({rd.label})", role="pinned")
            rn = b.declare(f"r{suffix}", meaning=f"the right side ({rd.label})", role="pinned")
            b.premise(f"L_DEF{suffix}", {"op": "eq", "left": {"op": "var", "name": ln}, "right": le}, f"{ln} is {render(lnode)[:300]}", grounding("figure"))
            b.premise(f"R_DEF{suffix}", {"op": "eq", "left": {"op": "var", "name": rn}, "right": re_}, f"{rn} is {render(rnode)[:300]}", grounding("figure"))
            alts.append({"op": op, "left": {"op": "var", "name": ln}, "right": {"op": "var", "name": rn}})
            ctx.readings.append(rd.label)
    if not alts:
        raise EncodeError("ST-UNDEC-001", "no reading of the comparison could be encoded")
    if affine_refused:
        ctx.warn("the SI reading is not established (a temperature on an offset scale combined with other terms); the comparison is checked in "
                 "its other readings only")
    if rel.negated:
        # 'the final test (2 <= 1) fails': the answer says the comparison does not hold, so that is what is checked
        alts = [{"op": "not", "arg": a} for a in alts]
        ctx.detail("the answer says this comparison fails (the words after it): the check is that it does not hold")
    expr = nary("or", alts) if len(alts) > 1 else alts[0]
    ctx.detail("exact comparison (R6): no slack")
    held = "fails, as the answer says," if rel.negated else "holds"
    if uses_s:
        ctx.form, ctx.query, ctx.expected = "S", "satisfiability", "SATISFIABLE"
        b.premise("ORDER", expr, f"the stated order {held} under some admissible reading", grounding("figure"))
    else:
        ctx.conclusion = ("STATED", expr, f"the stated order {held}")


# --------------------------------------------------------------------------- sub


def _sub(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.evaluate:
        _sub_evaluate(ctx)
    else:
        _sub_pairs(ctx)


_MAX_ORDERINGS = 120


def _injective(options: list[list[int]], limit: int = _MAX_ORDERINGS) -> Optional[list[tuple[int, ...]]]:
    """Every choice of one candidate per entry with no candidate chosen twice (a matching), in order; None when
    there would be more than ``limit`` of them. Bounded: at most ``limit`` choices are ever built."""
    out: list[tuple[int, ...]] = []

    def rec(i: int, used: tuple[int, ...]) -> bool:
        if i == len(options):
            out.append(used)
            return len(out) <= limit
        for c in options[i]:
            if c not in used and not rec(i + 1, used + (c,)):
                return False
        return True

    return out if rec(0, ()) else None


def _sub_pairs(ctx: _Ctx) -> None:
    rel = ctx.rel
    num_side = _numeric_side(rel)
    if num_side is None:
        raise EncodeError("ST-UNDEC-001", "a substitution with no closed side")
    groups = _product_groups(num_side)
    sym_side = rel.left.node if rel.right is not None and rel.right.node is num_side else (rel.right.node if rel.right is not None else None)
    # a numeral written opposite a literal coefficient of the law (the 4 of 4x, the ½ of ½mv²) is that coefficient, never
    # the value of a symbol: it is no alternative for a symbol's factor written in another order
    coefficients = _coefficient_ids(sym_side, num_side) if sym_side is not None else set()
    b = ctx.builder
    defined: dict[tuple[int, bool, bool], tuple[str, int]] = {}
    checked: list[str] = []
    #: (symbol, the node written opposite it, its alternatives, {id(alternative): "matches a binding" expression})
    entries: list[tuple[str, Node, list[Node], dict[int, dict]]] = []
    for name, node in rel.pairs:
        if not is_closed(node):
            continue
        blist = _visible_bindings(ctx, name)
        if not blist:
            continue
        # a temperature on an offset scale: a temperature in kelvin with the offset, unless the symbol names a change (ΔT)
        absolute = not name.startswith("Δ")
        alternatives = [node] + [m for m in groups.get(id(node), []) if m is not node and id(m) not in coefficients]
        per_alt: dict[int, dict] = {}
        for alt in alternatives:
            disj: list[dict] = []
            av = value_of(alt)
            h_w = av[1].half_width if (av is not None and av[1] is not None) else Fraction(0)
            w_unit = av[2] if av is not None else None
            for si in (False, True):
                key = (id(alt), si, si and absolute)
                if key not in defined:
                    try:
                        rd = Reading(si=si, affine=si and absolute, label="SI" if si else "as written")
                        enc = Encoder(b, rd, cache=ctx.cache)
                        t = enc.term(alt)
                    except EncodeError:
                        continue
                    wname = b.fresh("w", meaning=f"the value substituted at '{render(alt)[:120]}' ({'SI' if si else 'as written'})", role="pinned")
                    k = 0 if t.k == 0 else t.k
                    b.premise(f"W_{wname}", {"op": "eq", "left": {"op": "var", "name": wname}, "right": to_frame(t, k)},
                              f"{wname} is the substituted {render(alt)[:200]}", grounding("figure"))
                    defined[key] = (wname, k)
                wname, k = defined[key]
                f_w = Fraction(1)
                if si and w_unit is not None and w_unit.readings and w_unit.readings[0].factor is not None:
                    f_w = abs(w_unit.readings[0].factor)
                for bd in blist:
                    if si:
                        bval = bd.si if bd.unit is not None else bd.value
                        if bval is None and (temp := _affine_si(bd.value, bd.unit)) is not None:
                            bval = temp[1] if absolute else temp[0]
                        if bval is None:
                            continue
                        f_b = abs(bd.unit.readings[0].factor) if (bd.unit is not None and bd.unit.readings and bd.unit.readings[0].factor is not None) else Fraction(1)
                        tol = max(_match_h(ctx, bd) * f_b, h_w * f_w)  # one value is a rounding of the other (R7)
                    else:
                        if w_unit is not None and (bd.unit is None or bd.unit.text != w_unit.text):
                            continue
                        bval = bd.value
                        tol = max(_match_h(ctx, bd), h_w)
                        if w_unit is None and bd.unit is not None and bd.si is not None:
                            # a bare value may be the binding in the unit another value of the same working uses: 25.0 cm³
                            # substituted as 0.0250 beside c = 0.100 mol dm⁻³ (V in dm³, the volume unit of c)
                            f_b = abs(bd.unit.readings[0].factor) if bd.unit.readings and bd.unit.readings[0].factor is not None else None
                            for f_s in (_sibling_factors(ctx, bd) if f_b is not None else ()):
                                try:
                                    disj.append(band_expr({"op": "var", "name": wname}, literal_in_frame(bd.si / f_s, k),
                                                          literal_in_frame(max(_match_h(ctx, bd) * f_b / f_s, h_w), k), Fraction(0)))
                                    ctx.detail(f"'{name}' may be substituted in the unit the working uses for its dimension (factor {_ratio(f_s)} to SI)")
                                except LiteralTooLong:
                                    continue
                    try:
                        disj.append(band_expr({"op": "var", "name": wname}, literal_in_frame(bval, k), literal_in_frame(tol, k), Fraction(0)))
                    except LiteralTooLong:
                        continue
            if disj:
                per_alt[id(alt)] = nary("or", disj) if len(disj) > 1 else disj[0]
        if per_alt:
            entries.append((name, node, alternatives, per_alt))
            checked.append(name)
    if not entries:
        raise EncodeError("ST-UNDEC-001", "no substituted value could be set against a binding")
    # Symbols of one product (or sum) may be written in another order, but each must match a factor of its own: the
    # same written factor never stands for two symbols ('SV × HR = 70 × 42' with SV = 70 and HR = 72 does not hold
    # because 70 also lies near 72).
    by_group: dict[tuple[int, ...], list[tuple[str, Node, list[Node], dict[int, dict]]]] = {}
    for e in entries:
        by_group.setdefault(tuple(sorted(id(a) for a in e[2])), []).append(e)
    conj: list[dict] = []
    ordered = False
    for members in by_group.values():
        if len(members) == 1:
            exprs = list(members[0][3].values())
            conj.append(nary("or", exprs) if len(exprs) > 1 else exprs[0])
            continue
        choices = _injective([list(m[3]) for m in members])
        if choices:
            options = [nary("and", [m[3][c] for m, c in zip(members, choice)]) for choice in choices]
            conj.append(nary("or", options) if len(options) > 1 else options[0])
            ordered = True
            continue
        for m in members:  # no matching to enumerate (too many orderings, or a factor that could not be encoded): per symbol
            exprs = list(m[3].values())
            conj.append(nary("or", exprs) if len(exprs) > 1 else exprs[0])
    ctx.detail("substituted symbols: " + ", ".join(checked))
    ctx.detail("a value matches a binding of its symbol in force in its part (stated before it in the part, else carried from an earlier part), as "
               "written or in SI; a factor written in another order matches too (R7)"
               + ("; each factor stands for one symbol only" if ordered else ""))
    if rel.formula is not None:
        ctx.detail(f"the formula of '{rel.formula.name}' stated in {rel.formula.statement_id}")
    ctx.readings = ["as written or SI per value"]
    ctx.conclusion = ("SUBSTITUTED", nary("and", conj) if len(conj) > 1 else conj[0], "every substituted value matches a binding of its symbol")


def _sibling_factors(ctx: _Ctx, bd: Binding) -> list[Fraction]:
    """The SI factors of the units of ``bd``'s dimension that the same working uses elsewhere: in the units of the other
    bindings of the substitution and in the quantities its statements write (``dm⁻³`` of ``mol dm⁻³`` gives the volume unit
    dm³, factor 1/1000). The binding's own unit's factor is left out."""
    if bd.unit is None or bd.unit.dim is None or not bd.unit.readings or bd.unit.readings[0].factor is None:
        return []
    own = abs(bd.unit.readings[0].factor)
    want = bd.unit.dim
    units: list[UnitExpr] = []
    for name, _node in ctx.rel.pairs:
        if name != bd.symbol:
            units.extend(b.unit for b in _visible_bindings(ctx, name) if b.unit is not None)
    for sid in ctx.rel.statement_ids:
        for it in ctx.doc.items_for(sid):
            for ch in it.chains[:8]:
                for op in ch.operands[:16]:
                    node = op.node
                    if node is not None:
                        units.extend(_units_in(node))
    out: list[Fraction] = []
    for u in units[:32]:
        if u.unknown or len(u.readings) != 1:
            continue
        for atom in u.readings[0].atoms:
            if atom.unit is None or atom.power == 0:
                continue
            whole = UnitAtom(atom.text, atom.unit, atom.prefix, abs(atom.power))
            f, d = whole.factor, whole.dim
            if f is None or d is None or not d.same_physical(want) or d.angle != want.angle or f == own or f in out:
                continue
            out.append(f)
    return out[:4]


def _coefficient_ids(symbolic: Node, numeric: Node) -> set[int]:
    """The ids of the numerals of ``numeric`` that stand opposite a numeral of ``symbolic`` when the two trees are aligned as
    :func:`~.nodes.align` aligns them (products and sums as flattened, ordered lists). Bounded like ``align``."""
    out: set[int] = set()
    stack: list[tuple[Node, Node]] = [(symbolic, numeric)]
    steps = 0
    while stack and steps < 4096:
        steps += 1
        a, b = stack.pop()
        if isinstance(a, (Num, Quantity)):
            if isinstance(b, (Num, Quantity)):
                out.add(id(b))
            continue
        if isinstance(a, BinOp) and isinstance(b, BinOp) and a.op == b.op:
            if a.op in "+*":
                la, lb = _flatten_same(a, a.op), _flatten_same(b, b.op)
                if len(la) == len(lb):
                    stack.extend(zip(la, lb))
                continue
            stack.extend(((a.left, b.left), (a.right, b.right)))
            continue
        if isinstance(a, (Neg, Abs, Root)) and type(a) is type(b):
            stack.append((a.arg, b.arg))  # type: ignore[union-attr]
        elif isinstance(a, Pow) and isinstance(b, Pow) and a.exp == b.exp:
            stack.append((a.base, b.base))
    return out


def _match_h(ctx: _Ctx, bd: Binding) -> Fraction:
    """The half-width a binding contributes to a substitution match: none for a vulgar fraction, nor for an exact integer
    the answer states in Mathematics (``Let x = 3`` is 3, not anything that rounds to it); half a unit in its last digit
    otherwise (R1)."""
    exact = bd.unit is None and not bd.number.has_point and not bd.number.scientific and bd.source != "request"
    if exact and (bd.number.vulgar or (ctx.doc.profile.is_mathematics and bd.number.value.denominator == 1 and bd.wrapper == "")):
        return Fraction(0)
    return bd.number.half_width


def _request_count(ctx: _Ctx, name: str, names: list[str], sym_side: Node, num_side: Node) -> Optional[Fraction]:
    """The value of the one symbol of a substitution that nothing binds, read from the request (repair round 5, ADV5-18: 'N =
    N₀ × (½)³ = 800 / 8' for "A sample contains 800 undecayed nuclei" left N₀ unbound): the request states a bare count (a
    whole number with no unit), the written numeric side uses that numeral, and it is the only numeral of the numeric side
    the request states that the symbolic side does not write itself; every other symbol of the symbolic side is bound.
    None otherwise (the substitution stays undecided, as before)."""
    from .relations import _request_numerals
    others = [n for n in names if n != name]
    if any(not _in_force(ctx, n) for n in others):
        return None
    request = ctx.doc.request.text or ""
    if not request:
        return None
    stated = _request_numerals(request)
    with_units = {value_of(q)[0] for q, _a, _b in ctx.doc.request.quantities[:256] if value_of(q) is not None and value_of(q)[2] is not None}
    own = {value_of(leaf)[0] for leaf in _leaves(sym_side) if value_of(leaf) is not None}
    written = {value_of(leaf)[0] for leaf in _leaves(num_side) if value_of(leaf) is not None and value_of(leaf)[2] is None}
    counts = [v for v in written if v in stated and v not in with_units and v not in own and v.denominator == 1 and v > 1]
    return counts[0] if len(counts) == 1 else None


def _sub_evaluate(ctx: _Ctx) -> None:
    rel = ctx.rel
    combos = _operand_combos(rel.left, rel.right)
    pairs: list[tuple[Node, Node]] = []
    for lnode, rnode in combos:
        if is_closed(rnode) and not is_closed(lnode):
            sym_side, num_side = lnode, rnode
        elif is_closed(lnode) and not is_closed(rnode):
            sym_side, num_side = rnode, lnode
        else:
            raise EncodeError("ST-UNDEC-001", "a substitution with no closed side")
        pairs.append((num_side, sym_side))
    num0, sym0 = pairs[0]
    names = [n for n in symbols(sym0) if not n.endswith("()")]
    if any(n.endswith("()") for n in symbols(sym0)):
        raise EncodeError("ST-UNDEC-001", "a function of an unknown")
    anchors = dict(rel.pairs)
    domains: dict[str, SymbolDomain] = {}
    booklet_used: list[BookletReading] = []
    in_force: dict[str, tuple[Binding, ...]] = {}
    for name in names:
        blist = _in_force(ctx, name)
        if blist:
            in_force[name] = blist
            domains[name] = _domain_from_bindings(name, blist)
            continue
        if name in anchors:
            v = value_of(anchors[name])
            if v is not None and v[1] is not None:
                d = SymbolDomain(name)
                h = Fraction(0) if (not v[1].has_point and not v[1].scientific) else v[1].half_width
                si = si_value(v[0], v[2], v[3])
                d.add(v[0] - h, v[0] + h, None if si is None else (si - h, si + h), grounding("figure", f"value of '{name}' read from the written substitution"),
                      f"{name} = {render(anchors[name])} (read from the written substitution)")
                domains[name] = d
                continue
        sub = _substitution_domain(ctx, name)
        if sub is not None:
            domains[name] = sub
            continue
        if name == "e" and ctx.doc.profile.mode != "sciences":
            continue  # Euler's number: an enclosure (below)
        count = _request_count(ctx, name, names, sym0, num0)
        if count is not None:
            d = SymbolDomain(name)
            d.add(count, count, None, grounding("request"), f"{name} = {_ratio(count)} (the request's count, which the written substitution uses)")
            domains[name] = d
            continue
        reading = _booklet_for(ctx, name, sym0, num0)
        if reading is None:
            raise EncodeError("ST-UNDEC-002", f"'{name}' has no stated value and no admissible booklet reading (no dimension check confirms one)")
        d = SymbolDomain(name, booklet=True)
        g = grounding("booklet", reading.note)
        d.add(reading.lo, reading.hi, (reading.lo, reading.hi), g, f"{name}: booklet value of the {reading.constant.name}")
        domains[name] = d
        booklet_used.append(reading)
    if booklet_used:
        ctx.warn("a booklet value was supplied for " + ", ".join(f"'{r.symbol}' ({r.constant.name})" for r in booklet_used) + " (D3b)")
        ctx.detail("booklet readings: " + "; ".join(r.note for r in booklet_used))
    euler = "e" in names and "e" not in domains
    sym_units = tuple(bd.unit for blist in in_force.values() for bd in blist if bd.unit is not None)
    symbol_units = bool(sym_units) or bool(booklet_used)
    nodes = [n for p in pairs for n in p]
    approx = _approx(ctx)
    intent, intent_label = _intent_policy(ctx, nodes, approx=approx, has_units=symbol_units)
    exact_intent = intent == "exact" and rel.op in ("=", "≡")
    ctx.exact_intent = exact_intent
    rounded = intent == "rounded"   # a stated rounding: the written value is a rounding whatever its spelling (R2)
    exact_mode = rel.op in ("=", "≡") and not approx and (exact_intent or (not rounded and all(_all_exact(n) for n in nodes) and all(
        not d.is_interval and not d.booklet for d in domains.values()) and not symbol_units))
    # R2 as for written arithmetic: the relative slack needs a measured operand; the written numeric side alone, a single
    # stated value, is read as rounded to its last digit
    measured = symbol_units or any(d.is_interval or d.booklet for d in domains.values()) or any(
        _measured_numerals(sym) or _units_in(num) or (not is_value(num) and _measured_numerals(num)) for num, sym in pairs)
    tau = Fraction(0) if exact_mode else (TAU_APPROX if approx else (TAU_EQUAL if measured else Fraction(0)))
    if exact_intent:
        ctx.tolerance = intent_label
    elif exact_mode:
        ctx.tolerance = "exact, by the written form: every operand, binding and the written value are exact (τ = 0, h = 0)"
    elif intent:
        ctx.tolerance = intent_label + ("" if approx else f"; τ = {_ratio(tau)}")
    elif measured:
        ctx.tolerance = "measured, by the written form: a measured value (a unit, a rounded binding, a booklet value or a decimal); τ = 1/100"
    else:
        ctx.tolerance = "rounded to its stated digits, by the written form: exact operands and bindings; h from the written value's last digit, τ = 0"
    unit = _unit_role(ctx)
    readings, unknown = _readings(nodes, symbol_units=symbol_units, sym_units=sym_units, affine=_affine_mode(ctx, nodes, sym_units), both=bool(unit),
                                  angle_hint=_angle_hint(ctx, nodes))
    if unknown:
        ctx.warn("a unit is not recognised (ST-UNIT-001); the relation is checked as written only")
    hs = [_stated_half_width(num, exact_mode=exact_mode, rounded=rounded) for num, _sym in pairs]
    _unit_setup(ctx, unit, pairs)

    def env_for(rd: Reading, tag: str):
        env, hulls, needs = _install_domains(ctx, domains, rd, tag)
        if euler:
            env, hulls = dict(env), dict(hulls)
            enc = Encoder(ctx.builder, rd, cache=ctx.cache)
            env["e"] = enc._enclosure_symbol("e", None, e_interval(), "Euler's number e")
            hulls["e"] = e_interval()
            needs = needs | {"e"}
        return env, hulls, needs

    many = any(len(d.values_aw) > 1 for d in domains.values())
    ctx.detail("the symbolic side under the stated bindings" + (" (and readings from the written substitution)" if anchors else "") + f"; τ = {_ratio(tau)}")
    signs = (1, -1) if _has_plus_minus(*nodes) else (1,)
    _compare(ctx, pairs, kind="sub", tau=tau, h_written=hs, readings=readings, intervals={}, env_for=env_for, signs=signs, force_form_s=many,
             label="written numeric side", stated_label="symbolic side under the bindings", h_of_computed=True,
             affine_symbols=frozenset(n for n, d in domains.items() if d.affine), combine="implies" if ctx.rel.kind == "unit" else "or")


# --------------------------------------------------------------------------- alg and inequality steps


def _side_value_node(node: Node) -> Optional[Node]:
    return node if is_value(node) else None


def _step(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.premise_left is None or rel.premise_right is None:
        raise EncodeError("ST-UNDEC-001", "a step without a preceding relation")
    if getattr(rel, "inferred", False):
        ctx.warn("the relation is read as an identity by its shape (a factorised form stated equal to an expanded one), which no word of "
                 "the report or the request names")
    combos = _operand_combos(rel.premise_left, rel.premise_right, rel.left, rel.right)
    if len(combos) > ctx.doc.limits.max_readings_per_check:
        raise EncodeError("ST-PARSE-002", f"the step has {len(combos)} readings; the bound per check is {ctx.doc.limits.max_readings_per_check}")
    irrational = next((n for c in combos for side in c for n in walk(side) if _irrational_power(n)), None)
    if irrational is not None:
        # A step is decided exactly (only a side that is one written value gets a band), so an enclosed power next to a
        # rounded coefficient ('I₀ × 2^(−3.5) = 0.088 I₀') could only fail correct work: undecided, as before such a
        # power was read at all. Its arithmetic is still decided wherever it is written with figures (stem-eq).
        raise EncodeError("ST-UNDEC-001", f"an algebra step that holds a power with an irrational value or one too long to write exactly "
                                          f"('{render(irrational)[:60]}', encoded through an enclosure): a step is compared exactly, and such a value "
                                          "only within a tolerance band")
    b = ctx.builder
    pl0, pr0, cl0, cr0 = combos[0]
    prem_syms = set(symbols(pl0)) | set(symbols(pr0))
    conc_syms = set(symbols(cl0)) | set(symbols(cr0))
    if any(n.endswith("()") for n in prem_syms | conc_syms):
        raise EncodeError("ST-UNDEC-001", "a function of an unknown")
    diff = (prem_syms ^ conc_syms)
    intent, intent_label = _intent_policy(ctx, [n for c in combos for n in c], approx=bool(rel.approx))
    if intent:
        ctx.tolerance = intent_label
    ctx.exact_intent = intent == "exact" and (rel.op or "=") in ("=", "≡")
    ctx.rounded_intent = intent == "rounded"
    # R2 in a step: the relative slack of a rounded value needs a measured operand in the preceding relation (the
    # conclusion's other side is added per comparison in _step_conclusion)
    ctx.step_measured = any(_measured_numerals(n) or _has_enclosure(n) for c in combos for n in c[:2])
    reading = Reading(si=False, label="as written")
    # the value of a symbol that appears on one side only (a value the step substitutes): one value, pinned, so the
    # entailment is never asked to hold for every value the symbol takes elsewhere in the answer
    bound: dict[str, SymbolDomain] = {}
    written = {abs(v[0]) for side in (cl0, cr0) for leaf in _leaves(side) if (v := value_of(leaf)) is not None}
    own = {name: _step_binding(ctx, name, written) for name in sorted(diff)}
    from_request = _request_step_bindings(ctx, [n for n, bd in own.items() if bd is None], (cl0, cr0))
    for name in sorted(diff):
        bd = own[name] or from_request.get(name)
        if bd is not None:
            ctx.step_measured |= bd.unit is not None or bd.number.has_point or bd.number.scientific
            dom = SymbolDomain(name)
            dom.add(bd.value, bd.value, None, grounding("request") if bd.source == "request" else grounding("figure", f"value of '{name}' stated in {bd.statement_id}"),
                    f"{name} = {bd.number.text} ({bd.source}, {bd.statement_id})")
            bound[name] = dom
    # formulas of symbols on one side only
    formulas: list[tuple[str, Node, str]] = []
    for name in sorted(diff):
        if name in bound:
            continue
        for f in ctx.doc.formulas.get(name, ())[-2:]:
            if len(formulas) >= ctx.doc.limits.max_formulas_per_step:
                break
            if any(n.endswith("()") for n in symbols(f.expr)):
                continue
            formulas.append((name, f.expr, f.statement_id))
            ctx.step_measured |= _measured_numerals(f.expr) or _has_enclosure(f.expr)
    env: dict[str, Term] = {}
    all_syms = set(prem_syms | conc_syms)
    for _n, expr, _s in formulas:
        all_syms |= set(symbols(expr))
    for name in sorted(all_syms):
        role = "pinned" if name in bound else "free"
        env[name] = var_term(b.user_symbol(name, role=role))
    for name, dom in bound.items():
        var = env[name].expr["name"]
        alts = [{"op": "eq", "left": {"op": "var", "name": var}, "right": real(lo)} for lo, _hi in dom.values_aw]
        b.premise(f"B_{var}", nary("or", alts) if len(alts) > 1 else alts[0], "; ".join(dom.labels)[:1000], dom.groundings[0])
    enc = Encoder(b, reading, env=env, cache=ctx.cache)
    connected = set(prem_syms) | set(bound)
    for name, expr, sid in formulas:
        ft = enc.term(expr)
        (lhs, rhs), _k = align_terms(env[name], ft)
        b.premise("FORMULA", {"op": "eq", "left": lhs, "right": rhs}, f"the formula {name} = {render(expr)[:300]} stated in {sid}", grounding("law"))
        connected |= {name} | set(symbols(expr))
    # the preceding relation
    pop = _CMP_OPS.get(rel.premise_op or "=")
    cop = _CMP_OPS.get(rel.op or "=")
    if pop is None or cop is None:
        raise EncodeError("ST-UNDEC-001", f"a step between relation signs {rel.premise_op!r} and {rel.op!r}")
    prem_alts, conc_alts = [], []
    signs = (1, -1) if _has_plus_minus(pl0, pr0, cl0, cr0) else (1,)
    for pl, pr, cl, cr in combos:
        for sign in signs:
            rd = Reading(si=False, sign=sign, label="as written")
            e2 = Encoder(b, rd, env=env, cache=ctx.cache)
            lt, rt = e2.term(pl), e2.term(pr)
            (le, re_), _k = align_terms(lt, rt)
            prem_alts.append({"op": pop, "left": le, "right": re_})
            cl_t, cr_t = e2.term(cl), e2.term(cr)
            conc_alts.append(_step_conclusion(ctx, cop, cl, cr, cl_t, cr_t, len(conc_alts)))
    b.premise("PREV", nary("or", prem_alts) if len(prem_alts) > 1 else prem_alts[0],
              f"the preceding relation {render(pl0)[:200]} {rel.premise_op} {render(pr0)[:200]} ({', '.join(rel.premise_ids)})", grounding("law"))
    # side conditions: the principal root
    if rel.principal_root:
        for side in (cl0, cr0):
            if is_closed(side) or any(isinstance(n, Root) for n in walk(side)):
                continue
            st = enc.term(side)
            b.premise("SIDE_ROOT", {"op": "ge", "left": st.expr, "right": {"op": "real", "value": "0"}},
                      f"side condition: the principal (non-negative) root is taken, so {render(side)[:200]} ≥ 0", grounding("side"))
            ctx.detail(f"side condition: {render(side)[:80]} ≥ 0 (the principal root)")
    # side conditions: a symbol that stands for a power of e (the exponential reading of the planner) is positive
    for name in rel.positive:
        if name in env:
            b.premise("SIDE_POS", {"op": "gt", "left": env[name].expr, "right": {"op": "real", "value": "0"}},
                      f"side condition: {name} is a power of e, so {name} > 0", grounding("side"))
            ctx.detail(f"the unknown appears only in powers of e: read in {name} > 0 (an exact change of variable)")
    guards = [p for p in b.premises if p["id"].startswith("GUARD")]
    if guards:
        ctx.detail("side conditions: every divisor is non-zero")
    if formulas:
        ctx.detail("formulas included: " + ", ".join(f"{n} ({s})" for n, _e, s in formulas))
    if bound:
        ctx.detail("bindings included: " + ", ".join(sorted(bound)))
    unrelated = sorted(conc_syms - connected)
    if unrelated:
        ctx.warn("the step brings in symbols that no premise, binding or included formula connects (" + ", ".join(unrelated) + ")")
    ctx.readings = ["as written"]
    ctx.conclusion = ("STEP", nary("or", conc_alts) if len(conc_alts) > 1 else conc_alts[0], "the next relation follows from the preceding one")


def _has_enclosure(node: Node) -> bool:
    """A constant (π, e), a function or a root: a value known only by its enclosure, as a rounded constant is (R3)."""
    return any(isinstance(n, (Func, Root)) or (isinstance(n, Sym) and n.kind == "constant") for n in walk(node))


def _step_value(node: Node, rounded: bool) -> Optional[Node]:
    """The stated value on one side of a step: a single value, also after a leading ``±`` (``x = ±1.41``), or under a
    stated rounding a fraction of two written integers; None otherwise."""
    cur = node
    if isinstance(cur, PlusMinus) and cur.left is None:
        cur = cur.right
    if is_value(cur) or (rounded and _written_fraction(cur) is not None):
        return cur
    return None


def _step_binding(ctx: _Ctx, name: str, written: set[Fraction]) -> Optional[Binding]:
    """The one value of ``name`` a step uses: a binding (or, failing that, a substitution reading) whose
    value the step writes, else the latest stated before the step."""
    blist = [b for b in _visible_bindings(ctx, name) if b.source != "root"] or list(_visible_substitutions(ctx, name))
    if not blist:
        return None
    hits = [b for b in blist if abs(b.value) in written]
    pool = hits or blist
    before = [b for b in pool if b.end <= ctx.rel.start]
    return (before or pool)[-1]


_SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def _symbol_base(name: str) -> tuple[str, Optional[int]]:
    """``(base letter(s), index)`` of a symbol with a numeric subscript ('m₁' and 'm_1' are ('m', 1)); ``(name, None)`` otherwise."""
    plain = name.translate(_SUBSCRIPT_DIGITS)
    head = plain.rstrip("0123456789")
    if head.endswith("_"):
        head = head[:-1]
    digits = plain[len(head):].lstrip("_")
    if head and digits.isdecimal() and len(digits) <= 2 and head != plain:
        return head, int(digits)
    return name, None


def _request_step_bindings(ctx: _Ctx, names: list[str], sides: tuple[Node, ...]) -> dict[str, Binding]:
    """The request's values of the symbols a step substitutes and the answer binds nowhere (repair round 2, ADV2-02: 'V = IR,
    so R = 6.0 / 0.50' with 6.0 V and 0.50 A given only in the request; 'm₁u₁ = m₂v₂, so v₂ = 0.20 × 10 / 1.0' for a ball
    of 0.20 kg at 10 m s⁻¹ and a block of 1.0 kg). A symbol's dimensions are those of its reference quantities in the profile
    (:func:`.reference.quantities_for`, read for the base letter of a subscripted symbol: 'm₁' is a mass); a bare numeral the step
    writes stands for a request quantity when the request states that number with a unit (and no other quantity of the same
    value). A symbol takes the one such numeral whose dimension is one of its own; symbols of one base letter numbered 1, 2,
    ... ('m₁', 'm₂') take the request's quantities of their dimension in the order the request states them, when the step
    writes exactly as many. Each request quantity binds one symbol. A symbol with none, or with several possible values, stays
    free (and the step is checked for every value, as before)."""
    if not names:
        return {}
    from .reference import quantities_for
    profile = ctx.doc.profile.key
    numerals: list[Binding] = []  # the request quantities the step's bare numerals repeat, in the request's order
    seen: set[Fraction] = set()
    for side in sides:
        for leaf in _leaves(side):
            v = value_of(leaf)
            if v is None or v[1] is None or v[2] is not None or v[3] or v[0] in seen:
                continue
            seen.add(v[0])
            found = []
            for qnode, a, b in ctx.doc.request.quantities[:256]:
                rq = value_of(qnode)
                if rq is None or rq[1] is None or rq[2] is None or rq[2].unknown or rq[2].dim is None or rq[3] or rq[0] != v[0]:
                    continue
                found.append(Binding("", rq[0], rq[1], rq[2], "request", "request", a, b))
            if len(found) == 1:
                numerals.append(found[0])
    numerals.sort(key=lambda bd: bd.start)

    def dims_of(base: str) -> list[Dimension]:
        return [q.dimension for q in quantities_for(base, profile) if q.dimension is not None]

    def fits(bd: Binding, dims: list[Dimension]) -> bool:
        return bd.unit is not None and bd.unit.dim is not None and any(bd.unit.dim.same_physical(d) for d in dims)
    out: dict[str, Binding] = {}
    groups: dict[str, list[tuple[int, str]]] = {}
    for name in names:
        base, index = _symbol_base(name)
        if index is not None:
            groups.setdefault(base, []).append((index, name))
            continue
        hits = [bd for bd in numerals if fits(bd, dims_of(name))]
        if len(hits) == 1:
            out[name] = replace(hits[0], symbol=name)
    for base, members in groups.items():
        dims = dims_of(base)
        hits = [bd for bd in numerals if fits(bd, dims)]
        if not hits:
            continue
        if len(members) == 1 and len(hits) == 1:
            out[members[0][1]] = replace(hits[0], symbol=members[0][1])
        elif len(members) == len(hits) and len({i for i, _n in members}) == len(members):
            for (_i, name), bd in zip(sorted(members), hits):
                out[name] = replace(bd, symbol=name)
    used: dict[tuple[int, int], str] = {}
    for name, bd in sorted(out.items()):
        if (bd.start, bd.end) in used:  # one request quantity binds one symbol: two claims on it leave both free
            out.pop(used[(bd.start, bd.end)], None)
            out.pop(name, None)
            continue
        used[(bd.start, bd.end)] = name
    return out


def _step_conclusion(ctx: _Ctx, cop: str, cl: Node, cr: Node, lt: Term, rt: Term, n: int) -> dict:
    """``l op r`` with ``L_DEF``/``R_DEF`` so the proof always uses a premise (no vacuous result). A side
    written as a rounded decimal value is compared within its band (an evaluation step), and an order
    against a rounded value is widened by the value's half-width."""
    b = ctx.builder
    (le, re_), k = align_terms(lt, rt)
    suffix = "" if n == 0 else f"_{n + 1}"
    ln = b.declare(f"l{suffix}", meaning=f"the left side of the step: {render(cl)[:200]}", role="aux")
    rn = b.declare(f"r{suffix}", meaning=f"the right side of the step: {render(cr)[:200]}", role="aux")
    b.premise(f"L_DEF{suffix}", {"op": "eq", "left": {"op": "var", "name": ln}, "right": le}, f"{ln} is {render(cl)[:300]}", grounding("device"))
    b.premise(f"R_DEF{suffix}", {"op": "eq", "left": {"op": "var", "name": rn}, "right": re_}, f"{rn} is {render(cr)[:300]}", grounding("device"))
    lv, rv = {"op": "var", "name": ln}, {"op": "var", "name": rn}
    # the stated value of the step: a single value, also after a leading ± (x = ±1.41 states two rounded values), and under
    # a stated rounding a fraction of two written integers
    vr, vl = _step_value(cr, ctx.rounded_intent), _step_value(cl, ctx.rounded_intent)
    value_side = cr if vr is not None else (cl if vl is not None else None)
    value_node = vr if vr is not None else vl
    h = Fraction(0)
    if value_node is not None and not ctx.exact_intent:
        v = value_of(value_node)
        if v is not None and v[1] is not None and (v[1].has_point or v[1].scientific):
            h = v[1].half_width
        elif ctx.rounded_intent:
            h = _stated_half_width(value_node, rounded=True)
    approx = ctx.rel.approx and not ctx.exact_intent
    if cop == "eq" and (h > 0 or approx):
        other = cl if value_side is cr else cr
        measured = ctx.step_measured or _measured_numerals(other) or _has_enclosure(other)
        tau = TAU_APPROX if approx else (TAU_EQUAL if measured else Fraction(0))
        if not ctx.tolerance:
            ctx.tolerance = ("approximate step (≈): h of the stated value's last digit and τ = 1/20" if approx else
                             "a rounded value in the step beside a measured operand: h of its last digit and τ = 1/100" if measured else
                             "a rounded value in the step over exact operands: h of its last digit and τ = 0 (its spelling earns no slack)")
        ctx.detail(f"a rounded value in the step: compared within its band (R4), τ = {_ratio(tau)}")
        return band_expr(lv, rv, literal_in_frame(h, k), tau)
    if cop in ("lt", "le", "gt", "ge") and h > 0:
        hv = literal_in_frame(h, k)
        ctx.detail("an order against a rounded value: widened by its half-width")
        if value_side is cr:
            shifted = {"op": "add", "args": [rv, hv]} if cop in ("lt", "le") else {"op": "sub", "left": rv, "right": hv}
            return {"op": cop, "left": lv, "right": shifted}
        shifted = {"op": "sub", "left": lv, "right": hv} if cop in ("lt", "le") else {"op": "add", "args": [lv, hv]}
        return {"op": cop, "left": shifted, "right": rv}
    return {"op": cop, "left": lv, "right": rv}


# --------------------------------------------------------------------------- sol


def _expand_roots(roots: tuple[Node, ...]) -> list[Node]:
    out: list[Node] = []
    for r in roots:
        if _has_plus_minus(r):
            out.append(_choose_sign(r, 1))
            out.append(_choose_sign(r, -1))
        else:
            out.append(r)
    return out


def _choose_sign(node: Node, sign: int) -> Node:
    """``node`` with every ``±`` resolved to ``sign`` (``∓`` to the opposite)."""
    if isinstance(node, PlusMinus):
        s = sign if node.sign == "±" else -sign
        right = _choose_sign(node.right, sign)
        if node.left is None:
            return right if s > 0 else Neg(right, node.start, node.end)
        return BinOp("+" if s > 0 else "-", _choose_sign(node.left, sign), right, node.start, node.end)
    if isinstance(node, BinOp):
        return BinOp(node.op, _choose_sign(node.left, sign), _choose_sign(node.right, sign), node.start, node.end, node.written, node.implicit)
    if isinstance(node, Neg):
        return Neg(_choose_sign(node.arg, sign), node.start, node.end)
    if isinstance(node, Pow):
        return Pow(_choose_sign(node.base, sign), node.exp, node.start, node.end)
    if isinstance(node, Root):
        return Root(_choose_sign(node.arg, sign), node.index, node.start, node.end)
    if isinstance(node, Abs):
        return Abs(_choose_sign(node.arg, sign), node.start, node.end)
    return node


def _root_is_exact(node: Node, *, decimals: bool = False) -> bool:
    """A root written exactly (integers, fractions, surds), or with ``decimals`` any root of plain numerals (no unit, no
    function, no constant)."""
    if decimals:
        if any(isinstance(n, (Quantity, WithUnit, Percent)) for n in walk(node)):
            return False
    elif not _all_exact(node):
        return False
    return not any(isinstance(n, Func) or _irrational_power(n) or (isinstance(n, Sym) and n.kind == "constant") for n in walk(node))


def _irrational_power(node: Node) -> bool:
    """A ``RealPower`` the encoder writes as an enclosure: an irrational value (``10^0.4``, ``2^(−3.5)``), or an integer
    power beyond the integer-power bound whose exact value is too long for a literal (``(1 + 0.065/12)^(−60)``). Only a
    tolerance band can compare such a value with a written figure (``16^(3/4)`` is exactly 8 and ``2^20`` exactly 1048576:
    neither is such a power)."""
    return isinstance(node, RealPower) and real_power_value(node) is None


def _sol(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.premise_left is None or rel.premise_right is None or not rel.roots:
        raise EncodeError("ST-UNDEC-001", "stated roots without an equation")
    eq_l, eq_r = rel.premise_left.node, rel.premise_right.node
    if eq_l is None or eq_r is None:
        raise EncodeError("ST-PARSE-001", "the equation could not be read")
    x = rel.root_symbol
    roots = _expand_roots(rel.roots)
    others = sorted((set(symbols(eq_l)) | set(symbols(eq_r))) - {x})
    if any(n.endswith("()") for n in others):
        raise EncodeError("ST-UNDEC-001", "a function of an unknown")
    domains: dict[str, SymbolDomain] = {}
    for name in others:
        blist = _in_force(ctx, name)
        if not blist:
            raise EncodeError("ST-UNDEC-002", f"'{name}' in the equation has no stated value")
        domains[name] = _domain_from_bindings(name, blist)
    params_exact = all(not d.is_interval and len(d.values_aw) == 1 for d in domains.values())
    intent, intent_label = _intent_policy(ctx, list(roots) + [eq_l, eq_r], approx=False)
    if intent:
        ctx.tolerance = intent_label
    ctx.exact_intent = intent == "exact"
    # under a stated exactness a decimal root is the value it states, not a rounding: x = 1.41 is no root of x² = 2; a value the
    # answer states in prose for a described quantity (``_described_roots``) is always read through its rounding interval
    exact_roots = [_root_is_exact(r, decimals=ctx.exact_intent) and not rel.described for r in roots]
    b = ctx.builder
    reading = Reading(si=False, label="as written")
    env, hulls, needs = _install_domains(ctx, domains, reading, "") if domains else ({}, {}, frozenset())
    eq_ground = grounding("request") if rel.premise_ids == ("request",) else grounding("figure", f"the equation stated in {', '.join(rel.premise_ids)}")
    complete = rel.complete and not rel.restricted and params_exact
    ctx.readings = ["as written"]
    # an equation that carries '±' is two equations, one per sign ('x − 1 = ±2' holds at 3 and at −1): a root satisfies one of
    # them, and the roots of both are its roots (repair round 5, rerun-stem-soundness-10 variant)
    sign_readings = ([Reading(si=False, sign=1, label="as written"), Reading(si=False, sign=-1, label="as written")]
                     if _has_plus_minus(eq_l, eq_r) else [reading])
    if len(sign_readings) > 1:
        ctx.detail("the equation carries ±: it is read as two equations, one per sign")

    def equation(env_e: dict, cache: dict) -> list[tuple[dict, dict]]:
        out = []
        for rd in sign_readings:
            enc_e = Encoder(b, rd, env=env_e, symbol_hulls=hulls, interval_symbols=needs, cache=cache if len(sign_readings) == 1 else {})
            lt_e, rt_e = enc_e.term(eq_l), enc_e.term(eq_r)
            (le_e, re_e), _k_e = align_terms(lt_e, rt_e)
            out.append((le_e, re_e))
        return out

    if all(exact_roots) and params_exact:
        # Form E: linear membership (each exact root substituted as written), and completeness when the full set is claimed
        conj: list[dict] = []
        root_terms: list[Term] = []
        for i, root in enumerate(roots, 1):
            enc0 = Encoder(b, reading, env=env, symbol_hulls=hulls, cache=ctx.cache)
            rt = enc0.term(root)
            root_terms.append(rt)
            env_i = dict(env)
            env_i[x] = rt
            alts = []
            for k, (le, re_) in enumerate(equation(env_i, {})):
                tag = "" if k == 0 else "_m"
                ln = b.declare(f"l_{i}{tag}", meaning=f"the left side of the equation at {x} = {render(root)[:120]}", role="aux")
                rn = b.declare(f"r_{i}{tag}", meaning=f"the right side of the equation at {x} = {render(root)[:120]}", role="aux")
                b.premise(f"L_DEF_{i}{tag}", {"op": "eq", "left": {"op": "var", "name": ln}, "right": le}, f"{ln}: the equation's left side at the stated root", grounding("device"))
                b.premise(f"R_DEF_{i}{tag}", {"op": "eq", "left": {"op": "var", "name": rn}, "right": re_}, f"{rn}: the equation's right side at the stated root", grounding("device"))
                alts.append({"op": "eq", "left": {"op": "var", "name": ln}, "right": {"op": "var", "name": rn}})
            conj.append(nary("or", alts) if len(alts) > 1 else alts[0])
        ctx.detail("membership: each exact root substituted into the equation (exact)")
        if complete:
            xv = b.user_symbol(x, role="free", meaning=f"the unknown '{x}' of the equation")
            env_x = dict(env)
            env_x[x] = var_term(xv)
            eqs = [{"op": "eq", "left": le, "right": re_} for le, re_ in equation(env_x, {})]
            b.premise("EQ", nary("or", eqs) if len(eqs) > 1 else eqs[0], f"the equation {render(eq_l)[:200]} = {render(eq_r)[:200]}", eq_ground)
            disj = []
            for rt in root_terms:
                (a, c), _k2 = align_terms(var_term(xv), rt)
                disj.append({"op": "eq", "left": a, "right": c})
            conj.append(nary("or", disj) if len(disj) > 1 else disj[0])
            ctx.detail("completeness: the equation entails the disjunction of the stated roots")
        elif rel.complete:
            ctx.detail("completeness not checked: " + ("a domain restriction is stated" if rel.restricted else "the equation has measured parameters"))
        ctx.conclusion = ("ROOTS", nary("and", conj) if len(conj) > 1 else conj[0], "the stated roots satisfy the equation" + (" and are all its roots" if complete else ""))
        return
    if complete:
        # decimal roots and the full set claimed: completeness as an entailment over the roots' rounding intervals (membership not checked here)
        xv = b.user_symbol(x, role="free", meaning=f"the unknown '{x}' of the equation")
        env_x = dict(env)
        env_x[x] = var_term(xv)
        eqs = [{"op": "eq", "left": le, "right": re_} for le, re_ in equation(env_x, ctx.cache)]
        b.premise("EQ", nary("or", eqs) if len(eqs) > 1 else eqs[0], f"the equation {render(eq_l)[:200]} = {render(eq_r)[:200]}", eq_ground)
        disj = []
        for root in roots:
            lo, hi = _root_interval(ctx, root, reading, hulls)
            disj.append({"op": "and", "args": [{"op": "ge", "left": {"op": "var", "name": xv}, "right": real(lo)},
                                               {"op": "le", "left": {"op": "var", "name": xv}, "right": real(hi)}]})
        ctx.detail("completeness: every root of the equation lies in a stated root's rounding interval (R10); membership of the decimal roots is not "
                   "part of this check")
        ctx.conclusion = ("ROOTS", nary("or", disj) if len(disj) > 1 else disj[0], "every root of the equation is a stated root")
        return
    # Form S membership: each stated root's interval holds a root of the equation (R10), parameters over their intervals
    ctx.form, ctx.query, ctx.expected = "S", "satisfiability", "SATISFIABLE"
    if rel.described:
        ctx.detail(f"the root is the value the answer states in prose for the quantity it names {x}: compared within the '=' band "
                   f"(its half-width plus τ = 1/100 of it), as a prose value is approximate by nature")
    for i, root in enumerate(roots, 1):
        lo, hi = _root_interval(ctx, root, reading, hulls, prose=rel.described)
        rv = b.fresh("root", meaning=f"a root of the equation near the stated {render(root)[:120]}", role="interval")
        b.premise(f"X_LO_{rv}", {"op": "ge", "left": {"op": "var", "name": rv}, "right": real(lo)}, f"the stated root {render(root)[:200]} (rounding interval)",
                  grounding("figure"))
        b.premise(f"X_HI_{rv}", {"op": "le", "left": {"op": "var", "name": rv}, "right": real(hi)}, f"the stated root {render(root)[:200]} (rounding interval)",
                  grounding("figure"))
        env_i = dict(env)
        env_i[x] = var_term(rv)
        eqs = [{"op": "eq", "left": le, "right": re_} for le, re_ in equation(env_i, {})]
        b.premise(f"EQ_{i}", nary("or", eqs) if len(eqs) > 1 else eqs[0], f"the equation holds at the stated root {render(root)[:200]}", eq_ground)
    ctx.detail("membership: a root of the equation lies in each stated root's rounding interval (R10)")
    if rel.complete:
        ctx.detail("completeness not checked: " + ("a domain restriction is stated" if rel.restricted else "decimal roots or measured parameters"))


def _root_interval(ctx: _Ctx, root: Node, reading: Reading, hulls: dict[str, Interval], *, prose: bool = False) -> tuple[Fraction, Fraction]:
    """R10: a decimal root ranges over ``[r − h(r), r + h(r)]``; a root written as an expression with
    decimals over its value's enclosure widened by τ = 1/100. A root stated in prose for a named quantity (``prose``)
    also gets τ = 1/100 of its value beyond its half-width (the '=' band of R2)."""
    enc = Encoder(ctx.builder, reading, symbol_hulls=hulls, cache={})
    iv = enc.interval(root)
    if is_value(root):
        h = _value_half_width(root)
        if prose:
            h += TAU_EQUAL * max(abs(iv.lo), abs(iv.hi))
        lo, hi = iv.lo - h, iv.hi + h
    else:
        slack = TAU_EQUAL * max(abs(iv.lo), abs(iv.hi))
        lo, hi = iv.lo - slack, iv.hi + slack
    return _round_out(lo, "down"), _round_out(hi, "up")


# --------------------------------------------------------------------------- chem


def _chem(ctx: _Ctx) -> None:
    eq = ctx.rel.chem
    if eq is None or not eq.readable:
        raise EncodeError("ST-CHEM-001", "the chemical equation cannot be read")
    species = list(eq.left) + list(eq.right)
    fractional = any(sp.coefficient.denominator != 1 for sp in species)
    sort = "Real" if fractional else "Int"
    b = ctx.builder

    def literal(v: Fraction) -> dict:
        if sort == "Int":
            return {"op": "int", "value": str(int(v))}
        return real(v)

    ks: list[str] = []
    for i, sp in enumerate(species, 1):
        k = b.declare(f"k_{i}", sort=sort, meaning=f"the coefficient of {sp.text}", role="pinned")
        ks.append(k)
        b.premise(f"K_{i}", {"op": "eq", "left": {"op": "var", "name": k}, "right": literal(sp.coefficient)}, f"the written coefficient of {sp.text}",
                  grounding("figure"))
    nl = len(eq.left)
    tallies: list[tuple[str, list[tuple[int, int]], list[tuple[int, int]]]] = []
    for el in eq.elements():
        left = [(i, n) for i, sp in enumerate(species) if i < nl for e, n in sp.atoms if e == el]
        right = [(i, n) for i, sp in enumerate(species) if i >= nl for e, n in sp.atoms if e == el]
        tallies.append((el.lower(), left, right))
    charged = any(sp.charge for sp in species) or any(sp.electron for sp in species)
    if charged:
        tallies.append(("charge", [(i, species[i].charge if not species[i].electron else -1) for i in range(nl) if species[i].charge or species[i].electron],
                        [(i, species[i].charge if not species[i].electron else -1) for i in range(nl, len(species)) if species[i].charge or species[i].electron]))
    conj: list[dict] = []
    for name, left, right in tallies:
        for side, items in (("l", left), ("r", right)):
            t = b.declare(f"t_{name}_{side}", sort=sort, meaning=f"the {'charge' if name == 'charge' else name.capitalize() + ' atoms'} on the "
                                                                 f"{'left' if side == 'l' else 'right'}", role="aux")
            terms = []
            for i, n in items:
                kv = {"op": "var", "name": ks[i]}
                terms.append(kv if n == 1 else {"op": "mul", "args": [literal(Fraction(n)), kv]})
            expr = nary("add", terms) if len(terms) > 1 else (terms[0] if terms else literal(Fraction(0)))
            b.premise(f"T_{name}_{side}".upper(), {"op": "eq", "left": {"op": "var", "name": t}, "right": expr},
                      f"tally of {name} on the {'left' if side == 'l' else 'right'}", grounding("device"))
        conj.append({"op": "eq", "left": {"op": "var", "name": f"t_{name}_l"}, "right": {"op": "var", "name": f"t_{name}_r"}})
    if not conj:
        raise EncodeError("ST-CHEM-001", "an equation with no element to balance")
    ctx.readings = [f"{sort} coefficients"]
    ctx.detail("elements: " + ", ".join(eq.elements()) + ("; charge" if charged else ""))
    ctx.conclusion = ("BALANCE", nary("and", conj) if len(conj) > 1 else conj[0], "every element and the charge balance")


# --------------------------------------------------------------------------- bool, tt, base


def _bool_expr(ctx: _Ctx, node: Node, row: Optional[dict[str, bool]] = None) -> dict:
    b = ctx.builder
    if isinstance(node, Sym):
        if row is not None:
            if node.name not in row:
                raise EncodeError("ST-UNDEC-001", f"a truth-table output names '{node.name}', which is not an input")
            return {"op": "bool", "value": row[node.name]}
        return {"op": "var", "name": b.user_symbol(node.name, sort="Bool", role="free", meaning=f"the Boolean input '{node.name}'")}
    if isinstance(node, Num):
        if node.number.value not in (0, 1):
            raise EncodeError("ST-UNDEC-001", f"the numeral {node.number.text} in a Boolean expression")
        return {"op": "bool", "value": node.number.value == 1}
    if isinstance(node, BoolOp):
        args = [_bool_expr(ctx, a, row) for a in node.args]
        if node.op == "not":
            return {"op": "not", "arg": args[0]}
        if node.op in ("and", "or"):
            return nary(node.op, args) if len(args) > 1 else args[0]
        if node.op == "xor":
            out = args[0]
            for a in args[1:]:
                out = {"op": "not", "arg": {"op": "iff", "left": out, "right": a}}
            return out
    raise EncodeError("ST-UNDEC-001", f"a construct outside the Boolean encodings ({type(node).__name__})")


def _bool(ctx: _Ctx) -> None:
    br = ctx.rel.bool_rel
    if br is None:
        raise EncodeError("ST-UNDEC-001", "a Boolean relation that could not be read")
    lhs, rhs = _bool_expr(ctx, br.left), _bool_expr(ctx, br.right)
    ctx.builder.premise("NEG", {"op": "not", "arg": {"op": "iff", "left": lhs, "right": rhs}}, "the two sides differ for some assignment", grounding("figure"))
    ctx.form, ctx.query, ctx.expected = "B", "satisfiability", "UNSATISFIABLE"
    ctx.readings = ["Boolean"]
    ctx.detail("a satisfying assignment of NEG distinguishes the two sides")


def _tt(ctx: _Ctx) -> None:
    t: Optional[TruthTable] = ctx.rel.table
    if t is None or t.error:
        raise EncodeError("ST-UNDEC-001", "a truth table that could not be read")
    b = ctx.builder
    nin = len(t.inputs)
    cols = [(j, head, expr) for j, (head, expr) in enumerate(t.outputs) if expr is not None]
    if not cols:
        raise EncodeError("ST-UNDEC-001", "no output column of the truth table names an expression of its inputs")
    budget = IR_LIMITS["symbols"]
    keep = max(1, budget // max(1, len(t.rows)))
    if len(cols) > keep:
        ctx.detail(f"only the first {keep} output columns are checked (symbol bound)")
        cols = cols[:keep]
    conj: list[dict] = []
    for r, row in enumerate(t.rows, 1):
        inputs = {name: row[i] for i, name in enumerate(t.inputs)}
        pins = []
        for j, head, expr in cols:
            o = b.declare(f"o_{r}_{j + 1}", sort="Bool", meaning=f"the stated output '{head}' in row {r}", role="pinned")
            val = row[nin + j]
            pins.append({"op": "var", "name": o} if val else {"op": "not", "arg": {"op": "var", "name": o}})
            conj.append({"op": "iff", "left": {"op": "var", "name": o}, "right": _bool_expr(ctx, expr, inputs)})
        b.premise(f"ROW_{r}", nary("and", pins) if len(pins) > 1 else pins[0], f"the stated outputs of row {r}", grounding("figure"))
    ctx.readings = ["Boolean"]
    ctx.detail(f"{len(t.rows)} rows, {len(cols)} output column(s)")
    ctx.conclusion = ("ROWS", nary("and", conj) if len(conj) > 1 else conj[0], "every stated output equals its expression on the row's inputs")


def _int_expr(node: Node) -> Optional[dict]:
    """An Int encoding of an expression of integers with ``+ − ×`` and integer powers, else None."""
    if isinstance(node, Num):
        if node.number.value.denominator != 1 or node.number.has_point:
            return None
        return {"op": "int", "value": str(int(node.number.value))}
    if isinstance(node, Neg):
        a = _int_expr(node.arg)
        return None if a is None else {"op": "neg", "arg": a}
    if isinstance(node, BinOp) and node.op in "+-*":
        a, c = _int_expr(node.left), _int_expr(node.right)
        if a is None or c is None:
            return None
        if node.op == "+":
            return {"op": "add", "args": [a, c]}
        if node.op == "-":
            return {"op": "sub", "left": a, "right": c}
        return {"op": "mul", "args": [a, c]}
    if isinstance(node, Pow) and 2 <= node.exp <= 12:
        a = _int_expr(node.base)
        return None if a is None else {"op": "mul", "args": [a] * node.exp}
    return None


def _base(ctx: _Ctx) -> None:
    rel = ctx.rel
    combos = _operand_combos(rel.left, rel.right)
    lnode, rnode = combos[0]
    li, ri = _int_expr(lnode), _int_expr(rnode)
    b = ctx.builder
    if li is not None and ri is not None:
        b.declare("c", sort="Int", meaning=f"the value of {render(lnode)[:200]}", role="pinned")
        b.declare("r", sort="Int", meaning=f"the value of {render(rnode)[:200]}", role="pinned")
        b.premise("C_DEF", {"op": "eq", "left": {"op": "var", "name": "c"}, "right": li}, f"c is {render(lnode)[:300]}", grounding("figure"))
        b.premise("R", {"op": "eq", "left": {"op": "var", "name": "r"}, "right": ri}, f"r is {render(rnode)[:300]}", grounding("figure"))
        ctx.readings = ["exact integers"]
        ctx.conclusion = ("STATED", {"op": "eq", "left": {"op": "var", "name": "c"}, "right": {"op": "var", "name": "r"}}, "the two numerals are equal")
        return
    reading = Reading(si=False, label="as written")
    _compare(ctx, [(lnode, rnode)], kind="base", tau=Fraction(0), h_written=[Fraction(0)], readings=[reading], intervals={})


# --------------------------------------------------------------------------- mod


def _fraction_node(v: Fraction) -> Node:
    """An exact rational as a numeral node (a sign as ``Neg``), for the closed factors a model check builds."""
    a = abs(v)
    text = str(a.numerator) if a.denominator == 1 else f"{a.numerator}/{a.denominator}"
    num = Num(ExactNumber(text=text, value=a, sig_figs=max(1, len(str(a.numerator))), last_place=0, exact=True, vulgar=a.denominator != 1))
    return Neg(num) if v < 0 else num


def _monomial_hull(m: tuple, hulls: dict[str, Interval]) -> Optional[Interval]:
    """The interval of a monomial over the hulls of its symbols, or None when a symbol has none (a variable)."""
    out = Interval.point(Fraction(1))
    for name, power in m:
        h = hulls.get(name)
        if h is None:
            return None
        out = out * h.power(power)
    return out


def _power_bounds(base: Optional[Fraction], x: Interval) -> tuple[Fraction, Fraction]:
    """``[B^x.lo, B^x.hi]`` (``base`` None for e) as outward enclosures, each endpoint cross-checked against the math library."""
    lnb = None if base is None else enclose("ln", Interval.point(base))
    ends = []
    for xe in (x.lo, x.hi):
        y = Interval.point(xe) if lnb is None else lnb.scale(xe)
        iv = enclose("exp", y)
        if not cross_check("exp", y, iv):
            raise EncodeError("ST-INTERNAL-001", "the enclosure of a power bound failed its cross-check against the math library")
        ends.append(iv)
    lo, hi = min(ends[0].lo, ends[1].lo), max(ends[0].hi, ends[1].hi)
    return _round_out(lo, "down"), _round_out(hi, "up")


def _mod(ctx: _Ctx) -> None:
    """A model evaluation (``models.py``): some value of the variables (the model's variable and every symbol with no
    stated value), and of the stated symbols within their stated values, must satisfy the link, the model applied at the
    written argument. Every power of an exponent in symbols is read through positive variables: ``B^X`` with
    ``X = c + Σ qᵢ·mᵢ`` is ``B^c · Π uᵢ^(qᵢ/sᵢ)``, ``uᵢ = B^(sᵢ·mᵢ) > 0`` (``sᵢ`` the step of mᵢ's coefficients; bounded by the
    enclosure of ``B^(sᵢ·range)`` when the symbols of ``mᵢ`` all have stated values). Every real solution gives such ``uᵢ``,
    so UNSATISFIABLE proves that no value satisfies the link; SATISFIABLE never proves that it holds for every value. Form S.
    A letter defined as more than one model gives one pair of sides per definition (``rel.left.readings[i]`` with
    ``rel.right.readings[i]``), and the link must hold in some pair."""
    rel = ctx.rel
    if rel.left is None or rel.right is None or not rel.left.readings or len(rel.left.readings) != len(rel.right.readings):
        raise EncodeError("ST-PARSE-001", "an operand of the relation could not be read")
    pairs = list(zip(rel.left.readings, rel.right.readings))
    variables = set(rel.unbound)
    names = sorted(set().union(*(model_symbols(left) | model_symbols(right) for left, right in pairs)))
    domains: dict[str, SymbolDomain] = {}
    for n in names:
        if n in variables:
            continue
        blist = ctx.doc.bindings.get(n, ())
        dom = _domain_from_bindings(n, blist) if blist else _substitution_domain(ctx, n)
        if dom is None:
            variables.add(n)
        else:
            domains[n] = dom
    # the powers of an exponent in symbols, by base; one positive variable per (base, monomial)
    powers: list[tuple[Node, Optional[Fraction], dict]] = []
    for side in (n for pair in pairs for n in pair):
        for n in model_nodes(side):
            e = exponential(n)
            if e is None:
                continue
            poly = exponent_polynomial(e.exponent)
            base = None if e.base is None else exact_value(e.base)
            if poly is None or (e.base is not None and (base is None or base <= 0)):
                raise EncodeError("ST-UNDEC-001", f"a power outside the readings of a model check ('{render(n)[:80]}')")
            powers.append((n, base, poly))
    by_base: dict[Optional[Fraction], list[dict]] = {}
    for _n, base, poly in powers:
        by_base.setdefault(base, []).append(poly)
    dens = {base: model_denominators(polys) for base, polys in by_base.items()}
    if any(len(d) > MAX_MONOMIALS for d in dens.values()):
        raise EncodeError("ST-LIM-001", f"a model relation with more than {MAX_MONOMIALS} monomials in the exponents of one base")
    keys: dict[tuple, str] = {}
    for base, d in dens.items():
        for m in sorted(d):
            if base == 1:
                continue
            keys[(base, m)] = f"\u0000u{len(keys) + 1}"

    def relaxed(node: Node) -> Node:
        e = exponential(node)
        if e is not None:
            poly = exponent_polynomial(e.exponent)
            base = None if e.base is None else exact_value(e.base)
            assert poly is not None
            factors: list[Node] = []
            c = poly.get((), Fraction(0))
            if base == 1:
                return _fraction_node(Fraction(1))
            if c != 0:
                factors.append(Func("exp", _fraction_node(c)) if base is None else RealPower(_fraction_node(base), _fraction_node(c)))
            for m, q in sorted(poly.items()):
                if not m:
                    continue
                n_exp = q / dens[base][m]
                assert n_exp.denominator == 1
                k = int(n_exp)
                if abs(k) > IR_LIMITS["degree"]:
                    raise EncodeError("ST-LIM-001", f"a power of {k} of one variable in a model relation; the nonlinear policy allows degree {IR_LIMITS['degree']}")
                u = Sym(keys[(base, m)])
                factors.append(u if k == 1 else Pow(u, k))
            out: Node = factors[0] if factors else _fraction_node(Fraction(1))
            for f in factors[1:]:
                out = BinOp("*", out, f)
            return out
        if isinstance(node, (Num, Sym)):
            return node
        if isinstance(node, BinOp):
            return BinOp(node.op, relaxed(node.left), relaxed(node.right), node.start, node.end, node.written, node.implicit)
        if isinstance(node, Neg):
            return Neg(relaxed(node.arg), node.start, node.end)
        if isinstance(node, Pow):
            return Pow(relaxed(node.base), node.exp, node.start, node.end)
        if isinstance(node, Root):
            return Root(relaxed(node.arg), node.index, node.start, node.end)
        return node  # closed functions and powers: encoded as they stand

    relaxed_pairs = [(relaxed(left), relaxed(right)) for left, right in pairs]
    used = {n.name for pair in relaxed_pairs for side in pair for n in walk(side) if isinstance(n, Sym) and n.kind == "symbol" and not n.name.startswith("\u0000")}
    si_differs = any(dom.ranges(True) != dom.ranges(False) for dom in domains.values())
    readings = [Reading(si=False, label="as written")] + ([Reading(si=True, label="SI")] if si_differs else [])
    b = ctx.builder
    disjuncts: list[dict] = []
    labels: list[str] = []
    errors: list[EncodeError] = []
    for ri, reading in enumerate(readings):
        tag = "" if ri == 0 else f"r{ri + 1}"
        try:
            env, hulls, needs_s = _install_domains(ctx, {n: d for n, d in domains.items() if n in used}, reading, tag)
            hulls = dict(hulls)
            for n, dom in domains.items():
                hulls.setdefault(n, dom.hull(reading.si))
            env = dict(env)
            for v in sorted(variables & used):
                name = b.user_symbol(v, role="variable", tag=tag, meaning=f"'{v}': a variable of the relation (any real value)" + (f" [{reading.label}]" if tag else ""))
                env[v] = var_term(name, 0)
            interval_syms = set(needs_s)
            for (base, m), key in keys.items():
                step = dens[base][m]
                shown = f"{'e' if base is None else literal_text(base)}^(" + ("" if step == 1 else f"{literal_text(step)}·") + f"{render_model(monomial_node(m))})"
                hull = _monomial_hull(m, hulls) if not (set(s for s, _p in m) & variables) else None
                uname = b.fresh("u", meaning=f"{shown}, a positive variable" + (f" [{reading.label}]" if tag else ""), role="interval")
                if hull is None:
                    b.premise(f"U_POS_{uname}", {"op": "gt", "left": {"op": "var", "name": uname}, "right": {"op": "real", "value": "0"}},
                              f"{shown} is positive", grounding("device"))
                    env[key] = var_term(uname, 0)
                    continue
                lo, hi = _power_bounds(base, hull.scale(step))
                k = Encoder._frame_of(lo, hi)
                scale = Fraction(10) ** k
                note = f"{shown} for the stated values of {', '.join(s for s, _p in m)}: [{literal_text(lo / scale)}, {literal_text(hi / scale)}]" + (f" × 10^{k}" if k else "")
                b.premise(f"U_LO_{uname}", {"op": "ge", "left": {"op": "var", "name": uname}, "right": real(lo / scale)}, note, grounding("enclosure"))
                b.premise(f"U_HI_{uname}", {"op": "le", "left": {"op": "var", "name": uname}, "right": real(hi / scale)}, note, grounding("enclosure"))
                env[key] = var_term(uname, k)
                interval_syms.add(key)
            enc = Encoder(b, reading, env=env, symbol_hulls=hulls, interval_symbols=frozenset(interval_syms), cache=ctx.cache)
            terms = [(enc.term(lrel), enc.term(rrel)) for lrel, rrel in relaxed_pairs]  # every pair, or the reading is dropped
            if enc.enclosures:
                ctx.detail("function values and powers of figures as numeric enclosures computed by the STEM pack: " + ", ".join(dict.fromkeys(enc.enclosures)))
            for pi, (lt, rt) in enumerate(terms):
                frame = _common_frame(lt, rt)
                disjuncts.append({"op": "eq", "left": to_frame(lt, frame), "right": to_frame(rt, frame)})
                labels.append(reading.label + (f", definition {pi + 1} of {len(terms)}" if len(terms) > 1 else ""))
        except EncodeError as exc:
            errors.append(exc)
    if not disjuncts:
        raise errors[0] if errors else EncodeError("ST-UNDEC-001", "no reading of the model relation could be encoded")
    shown = "; ".join(f"{render_model(left)[:300]} = {render_model(right)[:300]}" for left, right in pairs)
    b.premise("REL", nary("or", disjuncts) if len(disjuncts) > 1 else disjuncts[0],
              f"the relation {shown[:700]} holds" + (" under some reading" if len(disjuncts) > 1 else ""), grounding("figure"))
    ctx.readings = labels
    ctx.form = "S"
    ctx.query = "satisfiability"
    ctx.expected = "SATISFIABLE"
    ctx.detail(rel.reason)
    ctx.detail("as read: " + "; or ".join(f"{render_model(left)[:200]} = {render_model(right)[:200]}" for left, right in pairs))
    if variables & used or any(set(s for s, _p in m) & variables for (_b, m) in keys):
        ctx.detail("variables (any real value): " + ", ".join(sorted(variables & (used | {s for (_b, m) in keys for s, _p in m}))))
    if keys:
        ctx.detail("each power of an exponent in symbols is read through positive variables, one per base and monomial of the exponents (a "
                   "relaxation that only widens the solutions: UNSATISFIABLE proves that no value satisfies the relation; SATISFIABLE does not "
                   "show that it holds for every value)")
    b.note("STEM model evaluation: SATISFIABLE means some value of the variables satisfies the relation under the relaxation, never that it holds")


def _op_half_width(node: Node) -> Fraction:
    """A rounded value written on the next line of a step keeps half a unit of its last digit; anything else is exact."""
    v = value_of(node) if is_value(node) else None
    if v is None or v[1] is None or not (v[1].has_point or v[1].scientific):
        return Fraction(0)
    return v[1].half_width


def _op(ctx: _Ctx) -> None:
    """ST-STEP-001 (stem_invalid_step): the operation the answer states for a step ("adding 4 to both sides gives …"),
    applied to each side of the preceding equation, against the next line's sides, in either order. The engine decides it
    as an identity: a satisfiability query of "the sides differ" over every value of the unknowns (under the divisors' guards),
    expected UNSATISFIABLE; a closed pair is compared as values (a rounded value on the next line within h of its last
    digit). A witness shows a value of the unknowns where the stated operation does not give the line written."""
    rel = ctx.rel
    sides = [op.node if op is not None else None for op in (rel.premise_left, rel.premise_right, rel.left, rel.right)]
    if any(n is None for n in sides):
        raise EncodeError("ST-PARSE-001", "a side of the step could not be read")
    pl, pr, nl, nr = sides  # type: ignore[misc]
    k = rel.operation_arg
    if rel.operation != "sq" and k is None:
        raise EncodeError("ST-UNDEC-001", "a stated operation without its operand")
    sign = {"add": "+", "sub": "-", "mul": "*", "div": "/"}

    def apply(side: Node) -> Node:
        if rel.operation == "sq":
            return Pow(side, 2, getattr(side, "start", 0), getattr(side, "end", 0))
        return BinOp(sign[rel.operation], side, k, getattr(side, "start", 0), getattr(side, "end", 0))  # type: ignore[arg-type]

    lp, rp = apply(pl), apply(pr)
    names = sorted({n for node in (pl, pr, nl, nr) + ((k,) if k is not None else ()) for n in symbols(node)})
    if any(n.endswith("()") for n in names):
        raise EncodeError("ST-UNDEC-001", "a function of an unknown")
    b = ctx.builder
    env = {n: var_term(b.user_symbol(n, role="free", meaning=f"'{n}', any value")) for n in names}
    enc = Encoder(b, Reading(si=False, label="as written"), env=env, cache=ctx.cache)

    def differ(written: Node, result: Node) -> dict:
        tw, tr = enc.term(written), enc.term(result)
        (ew, er), k2 = align_terms(tw, tr)
        if is_closed(written) and is_closed(result):
            return {"op": "not", "arg": band_expr(er, ew, literal_in_frame(_op_half_width(written), k2), Fraction(0))}
        return {"op": "ne", "left": ew, "right": er}

    straight = nary("or", [differ(nl, lp), differ(nr, rp)])
    swapped = nary("or", [differ(nl, rp), differ(nr, lp)])
    b.premise("DIFFER", nary("and", [straight, swapped]),
              f"the stated operation '{rel.operation_text[:120]}' applied to {render(pl)[:120]} = {render(pr)[:120]} differs from the next line "
              f"{render(nl)[:120]} = {render(nr)[:120]} for some value", grounding("figure"))
    ctx.form, ctx.query, ctx.expected = "B", "satisfiability", "UNSATISFIABLE"
    ctx.readings = ["as written"]
    ctx.defect = "stem_invalid_step"
    ctx.warn("the operation is read from the answer's prose")
    ctx.detail(f"ST-STEP-001: '{rel.operation_text[:120]}' applied to the preceding equation ({', '.join(rel.premise_ids)}) must give the next line, "
               f"either side order; a witness distinguishes them (stem_invalid_step)")


def _sys(ctx: _Ctx) -> None:
    """The stated solution of a system of equations against every equation (section 24): each unknown takes the value the
    answer states (an exact value exactly; a rounded decimal over its rounding interval, R10), and every equation must hold.
    Form E (ENTAILED) for exact values; Form S (SATISFIABLE: some values within the rounding intervals satisfy them all) for
    rounded ones."""
    rel = ctx.rel
    if not rel.equation_set or not rel.values:
        raise EncodeError("ST-UNDEC-001", "a stated solution without its system")
    b = ctx.builder
    env: dict[str, Term] = {}
    interval = False
    for name, node in rel.values:
        v = value_of(node)
        if v is None or v[1] is None or v[2] is not None or v[3]:
            raise EncodeError("ST-UNDEC-001", f"the stated value of '{name}' is not a plain number")
        rounded = v[1].has_point or v[1].scientific
        var = b.user_symbol(name, role="interval" if rounded else "pinned", meaning=f"'{name}', the value the answer states ({v[1].text})")
        env[name] = var_term(var)
        if rounded:
            interval = True
            h = v[1].half_width
            b.premise(f"V_{var}", {"op": "and", "args": [{"op": "ge", "left": {"op": "var", "name": var}, "right": real(v[0] - h)},
                                                          {"op": "le", "left": {"op": "var", "name": var}, "right": real(v[0] + h)}]},
                      f"{name} = {v[1].text}, over its rounding interval", grounding("figure"))
        else:
            b.premise(f"V_{var}", {"op": "eq", "left": {"op": "var", "name": var}, "right": real(v[0])}, f"{name} = {v[1].text}", grounding("figure"))
    enc = Encoder(b, Reading(si=False, label="as written"), env=env, cache=ctx.cache)
    eqs = []
    for left, _op, right in rel.equation_set:
        if left.node is None or right.node is None:
            raise EncodeError("ST-PARSE-001", "an equation of the system could not be read")
        if any(n not in env for n in set(symbols(left.node)) | set(symbols(right.node))):
            raise EncodeError("ST-UNDEC-002", "an equation of the system has an unknown with no stated value")
        (le, re_), _k = align_terms(enc.term(left.node), enc.term(right.node))
        eqs.append({"op": "eq", "left": le, "right": re_})
    system = nary("and", eqs) if len(eqs) > 1 else eqs[0]
    ctx.readings = ["as written"]
    ctx.detail(f"{len(eqs)} equations, every stated value put in")
    if interval:
        ctx.form, ctx.query, ctx.expected = "S", "satisfiability", "SATISFIABLE"
        b.premise("SYSTEM", system, "every equation holds for some values within the stated values' rounding intervals", grounding("figure"))
    else:
        ctx.conclusion = ("SYSTEM", system, "every equation of the system holds for the stated values")


def _rnd(ctx: _Ctx) -> None:
    """ST-ROUND-001 (stem_rounding_changes_conclusion): the answer compares a value its working rounded (the end of a chain
    '… = 0.246 s ≈ 0.25 s') with a threshold ("0.25 s is not less than 0.25 s"). The engine decides that the comparison, as
    the answer states it, holds with the value before the rounding whenever it holds with the rounded value (Form E,
    expected ENTAILED); a counterexample shows the rounding turned the conclusion."""
    rel = ctx.rel
    nodes = [op.node if op is not None else None for op in (rel.premise_left, rel.left, rel.right)]
    if any(n is None for n in nodes):
        raise EncodeError("ST-PARSE-001", "a value of the comparison could not be read")
    u, r, t = nodes  # type: ignore[misc]
    op = _CMP_OPS.get(rel.op)
    if op is None:
        raise EncodeError("ST-UNDEC-001", f"the comparison {rel.op!r}")
    once = unit_written_once(u, r)
    if once is not None:
        # the chain writes its unit (or its per cent sign) once, after the rounded value ('= 24.447 ≈ 24.45 cm³', '= 78.96 ≈
        # 79%'): the value before the rounding, as close to the rounded one as written, is in that unit too, so a bare 24.447
        # is never compared in SI with 24.45 cm³ read in m³ (repair round 2, own probes: the bare value made a near-threshold
        # comparison hold for 'acceptable' and fail for 'not acceptable'); a bare value of another scale ('= 0.7896 ≈ 79%',
        # a conversion in the rounding step) keeps its own reading
        u = once
    readings, unknown = _readings([u, r, t], affine=(False,))  # type: ignore[list-item]
    if unknown:
        raise EncodeError("ST-UNIT-001", "a unit of the comparison is not recognised")
    rd = next((x for x in readings if x.si), readings[0])
    b = ctx.builder
    enc = Encoder(b, rd, cache=ctx.cache)
    names = {}
    for key, node, what in (("u", u, "the value before the rounding"), ("r", r, "the rounded value the comparison uses"), ("t", t, "the threshold")):
        term = enc.term(node)
        var = b.declare(key, meaning=f"{what}: {render(node)[:200]} ({rd.label})", role="pinned")
        frame = 0 if term.k == 0 else term.k
        b.premise(f"{key.upper()}_DEF", {"op": "eq", "left": {"op": "var", "name": var}, "right": to_frame(term, frame)}, f"{var} is {render(node)[:300]}",
                  grounding("figure", _FIGURE_SI if rd.si and _si_differs([node]) else ""))
        names[key] = var

    def stated(x: str) -> dict:
        e = {"op": op, "left": {"op": "var", "name": names[x]}, "right": {"op": "var", "name": names["t"]}}
        return {"op": "not", "arg": e} if rel.explicit else e

    ctx.readings = [rd.label]
    ctx.defect = "stem_rounding_changes_conclusion"
    ctx.warn("the comparison is read from the answer's prose and its rounding")
    ctx.detail(f"ST-ROUND-001: the stated comparison ({'not ' if rel.explicit else ''}{rel.op} the threshold) with the rounded value "
               f"{render(r)[:60]} must also hold with the value before the rounding, {render(u)[:60]} ({', '.join(rel.premise_ids)})")
    ctx.conclusion = ("ROUNDING", {"op": "implies", "left": stated("r"), "right": stated("u")},
                      "the stated comparison keeps its truth with the value before the rounding")


def _unit(ctx: _Ctx) -> None:
    """The ST-UNIT-003 companion of an eq check, or of a sub check that evaluates (section 24)."""
    if ctx.rel.evaluate:
        _sub_evaluate(ctx)
    else:
        _eq(ctx)


_BUILDERS = {
    "eq": _eq, "cnv": _cnv, "res": _res, "tgt": _tgt, "giv": _giv, "cmp": _cmp, "sub": _sub, "alg": _step, "sol": _sol, "chem": _chem, "bool": _bool,
    "tt": _tt, "base": _base, "mod": _mod, "unit": _unit, "op": _op, "sys": _sys, "rnd": _rnd,
}
