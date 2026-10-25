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
from .enclosures import EnclosureError, Interval, cross_check, e_interval, enclose
from .models import MAX_MONOMIALS, all_symbols as model_symbols, denominators as model_denominators, exact_value, exponent_polynomial, exponential, monomial_node
from .models import render_model
from .models import _walk as model_nodes
from .nodes import (
    Abs, BinOp, BoolOp, Degrees, Func, IntOp, Neg, Node, Num, Operand, Percent, PlusMinus, Pow, Quantity, Ratio, RealPower, Root, Sym, Unsupported, WithUnit,
    children, is_closed, is_value, render, symbols, value_of, walk,
)
from .numbers import ExactNumber
from .relations import ST_SEVERITY, Relation
from .scaling import LiteralTooLong, Term, align as align_terms, floor_log10, frame_for, lit, literal_in_frame, literal_text, nary, real, to_frame, var_term
from .scope import Binding, si_value
from .tolerance import SHORT_RULE, TAU_APPROX, TAU_EQUAL, approx_word_before, approx_word_in, band_expr, half_width, is_measured
from .to_ir import IR_LIMITS, EncodeError, Encoder, IntervalLeaf, ProblemBuilder, Reading, SymbolDomain, _round_out, grounding, inspect_ir, real_power_value
from .units import DIMENSIONLESS, Dimension, UnitAtom, UnitExpr, parse_unit

__all__ = ["CHECK_KIND_NAMES", "CheckFinding", "CheckPlan", "PlannedCheck", "build_check", "build_checks"]

#: planned kind -> the FormalCheck kind (section 8.1)
CHECK_KIND_NAMES = {
    "eq": "stem_arithmetic", "sub": "stem_substitution", "alg": "stem_algebra", "sol": "stem_solution", "mod": "stem_model", "cnv": "stem_conversion",
    "cmp": "stem_comparison", "res": "stem_result", "giv": "stem_given", "tgt": "stem_target", "chem": "stem_balance", "bool": "stem_boolean",
    "tt": "stem_truth_table", "base": "stem_base",
}
_TITLES = {
    "eq": "the written arithmetic", "sub": "the substitution", "alg": "the algebraic step", "sol": "the stated roots", "mod": "the model evaluation",
    "cnv": "the unit conversion",
    "cmp": "the stated comparison", "res": "the restated result", "giv": "the Given value against the request", "tgt": "the final value against the show-that target",
    "chem": "the element and charge balance", "bool": "the Boolean identity", "tt": "the stated truth-table rows", "base": "the based-numeral conversion",
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
    #: statements stating values the check relies on beside its own (a substitution's earlier stated values): a failure names
    #: them too (``Relation.related_ids``)
    related_ids: tuple[str, ...] = ()


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
        note = _question_note(rel)
        if note:
            ctx.detail(note)
        builder(ctx)
        if rel.fraction_units:
            # rule fraction-unit (STEM repair 6): the statement says which reading of a unit written after a fraction it decided
            ctx.detail("the unit written after " + ", ".join(f"'{t}'" for t in rel.fraction_units) + " is read as the fraction's own, the reading under "
                       "which the two sides have one dimension (rule fraction-unit)")
        return ctx.finish()
    except EncodeError as exc:
        return _finding(exc.code, exc.reason, rel)
    except (LiteralTooLong,) as exc:
        return _finding("ST-LIM-001", str(exc), rel)
    except EnclosureError as exc:
        return _finding(exc.code, exc.reason, rel)
    except Exception as exc:  # defensive: one check's failure never takes the others down
        return _finding("ST-INTERNAL-001", f"the STEM pack failed internally while building this check ({type(exc).__name__})", rel)


def _question_note(rel: Relation) -> str:
    """Rule ``question`` (STEM repair 2): a relation the answer asks and answers is checked as answered, its negation for "no"; the
    check's statement says which relation it decides, so '67 = 67' answered "No" reads as the claim 67 ≠ 67."""
    reason = rel.reason or ""
    k = reason.find("a relation asked as a question")
    rule = "rule question"
    if k < 0:
        k = reason.find("a comparison the text states is false")  # stem-precision-8 (round 7)
        rule = "round 7, stated false"
    if k < 0:
        return ""
    note = reason[k:].split(";", 1)[0]
    if rel.left is not None and rel.right is not None and rel.left.node is not None and rel.right.node is not None:
        note += f" (the relation decided: {render(rel.left.node)[:60]} {rel.op} {render(rel.right.node)[:60]})"
    return note + f" ({rule})"


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
    ever withholds a check; it never decides one."""
    if rel.title:
        return ""  # a check a rule built from two places of the text (STEM repair 3): its operands are where they are written, never cut
    text = doc.text
    n = len(text)
    if "request" not in rel.premise_ids and 0 <= rel.start < rel.end <= n:
        # stem-soundness-4 (round 7): a relation glued by a full stop to a letter or a bracket on either side ('A.B = B.C' read from
        # 'B = B') is a fragment of a longer expression (a dot written for AND or a product): deciding the fragment could fail correct
        # work or pass a wrong identity
        glued_before = rel.start >= 2 and text[rel.start - 1] == "." and (text[rel.start - 2].isalpha() or text[rel.start - 2] in ")]'′")
        glued_after = rel.end + 1 < n and text[rel.end] == "." and (text[rel.end + 1].isalpha() or text[rel.end + 1] in "([¬")
        if glued_before or glued_after:
            shown = " ".join(text[max(0, rel.start - 8):min(n, rel.end + 8)].split())[:80]
            return (f"the relation is read from a fragment of '{shown}' (a full stop glued to the expression on its "
                    f"{'left' if glued_before else 'right'}), so it is not checked")
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
            q = m
            while q >= 0 and text[q] in " \t" and m - q < 4:
                q -= 1
            if q >= 0 and text[q].isdigit() and token.lower() not in _SHORT_WORDS:
                # stem-precision-9 (round 7): a numeral and a count noun before the sign ('4 categories − 1 = 3'): the left operand is the
                # numeral the noun counts, so the sign is binary; read from the sign, the relation was '− 1 = 3' and failed
                return (f"the operand '{shown}' opens with a sign right after '{text[max(0, q - 6):j + 1].strip()}', a numeral and the noun it "
                        "counts: the left operand is written partly in words, so the relation is not checked")
    if rel.kind in _CHAIN_KINDS and rel.left is not None and rel.right is not None and rel.left.end <= rel.right.start <= n:
        gap = _strip_relation_text(text[rel.left.end:rel.right.start])
        if _REMAINDER_GAP_RE.fullmatch(text[rel.left.end:rel.right.start]):
            gap = ""  # '17 ÷ 5 = 3 remainder 2': the remainder relation of a stated quotient (the parser's own second relation)
        if any(ch.isalnum() for ch in gap):
            return f"prose ('{' '.join(gap.split())[:40]}') stands between the two sides of the relation, so they may not belong together; the relation is not checked"
    return ""


#: what may precede an operand that opens with a sign: a relation sign, an opening bracket, a separator, LaTeX alignment
_OPENERS = frozenset("=<>≤≥≈≃≠⇒→∴:([{$&,;|±∓\\")
#: kinds whose two sides are adjacent operands of one chain
_CHAIN_KINDS = frozenset({"eq", "cnv", "cmp", "sub", "base"})
#: the text between a division and the remainder the answer states for it ('17 ÷ 5 = 3 remainder 2'; STEM repair 2)
_REMAINDER_GAP_RE = re.compile(r"\s*=\s*\d{1,40}\s+(?:remainder|rem)\s+")
_RELATION_WORDS = ("is equal to", "equals", "equal", "gives", "approximately", "approx", "about", "roughly", "is", "makes")


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
        if policy == "nonlinear":
            b.note("policy: nonlinear")
            problem = b.problem(self.query, self.conclusion)
        desc = self.description(policy)
        return PlannedCheck(
            check_id=self.rel.check_id, kind=CHECK_KIND_NAMES[self.rel.kind], description=desc, claim_ids=tuple(self.rel.statement_ids), problem=problem,
            expected_if_sound=self.expected, policy=policy, failure_severity=self.severity, inconsistent_is_failure=False, form=self.form,
            relation_kind=self.rel.kind, readings=tuple(self.readings), related_ids=tuple(self.rel.related_ids),
        )

    def excerpt(self) -> str:
        rel = self.rel
        text = self.doc.text[rel.start:rel.end] if 0 <= rel.start < rel.end <= len(self.doc.text) else ""
        if not text and rel.left is not None and rel.left.node is not None:
            text = render(rel.left.node) + f" {rel.op} " + (render(rel.right.node) if rel.right is not None and rel.right.node is not None else "")
        text = " ".join(text.split())
        return text if len(text) <= _MAX_EXCERPT else text[:_MAX_EXCERPT - 1] + "…"

    def description(self, policy: str) -> str:
        rel = self.rel
        form = {"E": "Form E (entailment, expected ENTAILED)", "S": "Form S (satisfiability, expected SATISFIABLE: some admissible reading gives the "
                "stated value; it does not mean the value is true)", "B": "satisfiability, expected UNSATISFIABLE (a witness distinguishes the sides)"}[self.form]
        if rel.kind == "mod":
            form = ("Form S (satisfiability, expected SATISFIABLE: some value of the variables, and of the stated symbols within their stated "
                    "values, satisfies the relation; it does not mean the relation holds for every value)")
        title = rel.title or ("the Boolean evaluation" if rel.kind == "bool" and rel.assignment else _TITLES[rel.kind])
        head = f"{title}: '{self.excerpt()}' [claims {', '.join(rel.statement_ids)}] [{SHORT_RULE}]"
        parts = [form, f"policy {policy}"]
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


#: STEM repair 12: an approximation word right before a restated value ('which is about 2.7 A', ', about 37%')
_APPROX_BEFORE_RE = re.compile(r"\b(?:about|approximately|approx\.?|roughly|around|nearly)(?:[ \t]+equal[ \t]+to)?[ \t]*$", re.IGNORECASE)


def _approx(ctx: _Ctx) -> bool:
    if ctx.rel.approx:
        return True
    sid = ctx.rel.statement_ids[-1] if ctx.rel.statement_ids else ""
    st = ctx.doc.statement(sid)
    if st is None:
        return False
    # stem-soundness-6 (round 7): a whole approximation word directly before the relation, or between its two sides ('= about 6.3');
    # before, any substring of the 120 characters before it ('linearly', 'thoroughly', 'for about 3 s, and v = …') gave τ = 1/20
    before = ctx.doc.text[max(st.start, ctx.rel.start - 120):ctx.rel.start]
    if approx_word_before(before):
        return True
    rel = ctx.rel
    if rel.left is not None and rel.right is not None and rel.left.end <= rel.right.start <= len(ctx.doc.text):
        return approx_word_in(ctx.doc.text[rel.left.end:rel.right.start])
    return False


#: a significant-figure count no written integer reaches: with it, every trailing zero of a whole number counts (R1)
_EVERY_DIGIT = 10_000


def _value_half_width(node: Node, *, min_sf: Optional[int] = None, exact_mode: bool = False) -> Fraction:
    v = value_of(node)
    if v is None or v[1] is None:
        return Fraction(0)
    return half_width(v[1], min_sig_figs=min_sf, exact_mode=exact_mode)


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
    if v[3] == "%" and (reading.si or reading.percent):
        factor /= 100
    if v[3] == "°" and reading.degrees_si:
        factor *= _DEGREE_UPPER  # a half-width in degrees, in radians (stem-soundness-8): rounded up, so never narrower than it is
    return factor


#: a rational upper bound of π/180 (0.01745329…)
_DEGREE_UPPER = Fraction(174533, 10 ** 7)


def _operand_combos(*ops: Optional[Operand]) -> list[tuple[Node, ...]]:
    combos: list[tuple[Node, ...]] = [()]
    for op in ops:
        if op is None or not op.readings:
            raise EncodeError("ST-PARSE-001", "an operand of the relation could not be read")
        combos = [c + (r,) for c in combos for r in op.readings]
    return combos


#: the written unit of an expression: (dimension, SI factor, whether a unit or a per cent is written in it)
_WrittenUnit = tuple[Dimension, Fraction, bool]
_NO_UNIT: _WrittenUnit = (DIMENSIONLESS, Fraction(1), False)


def _written_unit(node: Node, depth: int = 0) -> Optional[_WrittenUnit]:
    """The units written in ``node``, read multiplicatively (a bare numeral is a pure number): the dimension, the exact SI factor and
    whether any unit or per cent is written. None when it cannot be told: a symbol, an unknown, ambiguous, affine or inexact unit (the
    degree), terms of a sum written in different units, a power of a unit that is no integer (stem-soundness-1, round 7)."""
    if depth > 64:
        return None
    if isinstance(node, Num):
        return _NO_UNIT
    if isinstance(node, (Quantity, WithUnit)):
        unit = node.unit
        if unit.unknown or len(unit.readings) != 1:
            return None
        r = unit.readings[0]
        if r.dim is None or r.factor is None or r.affine is not None:
            return None
        inner = _NO_UNIT if isinstance(node, Quantity) else _written_unit(node.arg, depth + 1)
        if inner is None:
            return None
        return inner[0] * r.dim, inner[1] * r.factor, True
    if isinstance(node, Percent):
        inner = _written_unit(node.arg, depth + 1)
        return None if inner is None else (inner[0], inner[1] / 100, True)
    if isinstance(node, (Neg, Abs)):
        return _written_unit(node.arg, depth + 1)
    if isinstance(node, Sym):
        return _NO_UNIT if node.kind == "constant" else None
    if isinstance(node, (Func, RealPower, IntOp)):
        return _NO_UNIT if not any(isinstance(m, (Quantity, WithUnit, Percent, Degrees)) for m in walk(node)) else None
    if isinstance(node, Pow):
        inner = _written_unit(node.base, depth + 1)
        if inner is None:
            return None
        return inner[0].power(node.exp), inner[1] ** node.exp, inner[2]
    if isinstance(node, BinOp):
        a, b = _written_unit(node.left, depth + 1), _written_unit(node.right, depth + 1)
        if a is None or b is None:
            return None
        if node.op == "*":
            return a[0] * b[0], a[1] * b[1], a[2] or b[2]
        if node.op == "/":
            return a[0] / b[0], a[1] / b[1], a[2] or b[2]
        if not a[2]:
            return b  # a bare term of a sum is taken in the other terms' unit
        if not b[2]:
            return a
        return a if (a[0], a[1]) == (b[0], b[1]) else None
    return None


def _bare_factors(node: Node) -> list[tuple[Fraction, int]]:
    """The values of the bare numerals multiplying (exponent 1) or dividing (−1) ``node`` at its top level ('× 1000', '/ 60')."""
    out: list[tuple[Fraction, int]] = []
    stack: list[tuple[Node, int]] = [(node, 1)]
    while stack and len(out) <= 16:
        cur, e = stack.pop()
        if isinstance(cur, BinOp) and cur.op in ("*", "/"):
            stack.append((cur.left, e))
            stack.append((cur.right, e if cur.op == "*" else -e))
            continue
        v = None
        if isinstance(cur, Num):
            v = cur.number.value
        elif isinstance(cur, Pow) and isinstance(cur.base, Num):
            v = cur.base.number.value ** cur.exp if cur.base.number.value or cur.exp > 0 else None
        if v:
            out.append((Fraction(v), e))
    return out


def _as_written_consistent(cnode: Node, snode: Node) -> bool:
    """Whether the reading as written (every unit read as a factor of 1) is a consistent reading of ``cnode = snode``
    (stem-soundness-1, round 7). Read as written, a bare numeral stands in some unit of its own; the reading is admitted unless the
    units written on the two sides differ by a pure number other than 1 that no bare conversion factor written in the computation
    supplies: '3 × 2.0 kg = 6.0 g', '2.0 kW × 3.0 = 6.0 W', '300/400 = 0.75 %' and '80 × 25 % = 2000' are read in SI only, while
    '2.5 kg × 1000 = 2500 g', '4.5 min × 60 = 270 s', '0.75 × 100 = 75 %' and '120/4.0 = 30 km/h' (the bare numerals stand in km and h)
    keep it. A ratio that has a dimension leaves the reading as before, and so does any unit that cannot be told."""
    lu, ru = _written_unit(cnode), _written_unit(snode)
    if lu is None or ru is None:
        return True
    dim = ru[0] / lu[0]
    if any(dim.exps) or dim.angle:
        return True
    need = lu[1] / ru[1]  # the bare conversion factor that turns the computed side's written units into the stated value's
    if need == 1:
        return True
    factors = _bare_factors(cnode)[:8]
    for mask in range(1, 1 << len(factors)):
        prod = Fraction(1)
        for k, (v, e) in enumerate(factors):
            if mask >> k & 1:
                prod *= v if e > 0 else 1 / v
        if prod == need:
            return True
    return False


def _reading_modes(nodes: list[Node], *, symbol_units: bool = False, force: Optional[str] = None,
                   pairs: Optional[list[tuple[Node, Node]]] = None, symbol_factors: bool = False) -> tuple[list[str], bool, list[UnitExpr]]:
    """Section 6.4. Returns the unit modes (``aw``, ``si``), whether an unknown unit restricts the
    check to the reading as written, and the ambiguous units (two readings each). ``pairs`` (computed side, stated side) admit the
    reading as written only where its units are consistent (:func:`_as_written_consistent`)."""
    units = [u for n in nodes for u in _units_in(n)]
    unknown = any(u.unknown for u in units)
    if unknown:
        return ["aw"], True, []
    percent = any(_has_percent(n) for n in nodes)
    if force:
        return [force], False, [u for u in units if len(u.readings) > 1]
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
    if not _si_differs(nodes) and not symbol_factors:
        return ["aw"], False, []  # every unit factor is 1 and no per cent: SI and as written coincide
    if not bare and (units or percent):
        return ["si"], False, ambiguous
    aw = ["aw"] if (pairs is None or all(_as_written_consistent(c, sn) for c, sn in pairs)) else []
    if _percent_factor(nodes) and _unit_factor_differs(nodes):
        # STEM repair 5: a per cent taken of a bare number beside a unit whose SI factor is not 1 ('1620 × 2% = 32.4 counts min⁻¹'): as
        # written reads 2% as 2 and SI converts the unit of one side only, so the per cent is also read as its fraction with the units as
        # written
        return aw + ["si", "awp"], False, ambiguous
    return aw + ["si"], False, ambiguous


def _percent_factor(nodes: list[Node]) -> bool:
    """A per cent is a factor of a product or a division with another operand ('1620 × 2%', '2% × 1620', '2% of' written '×'), not a
    stated value or the '× 100%' that makes a ratio a percentage."""
    for node in nodes:
        for n in walk(node):
            if isinstance(n, BinOp) and n.op in ("*", "/"):
                for side in (n.left, n.right):
                    while isinstance(side, Neg) or (isinstance(side, PlusMinus) and side.left is None):
                        side = side.arg if isinstance(side, Neg) else side.right  # '±2% × 1620'
                    if isinstance(side, Percent):
                        v = value_of(side)
                        if v is not None and v[0] != 100:
                            return True
    return False


def _unit_factor_differs(nodes: list[Node]) -> bool:
    """Some unit of the nodes has an SI factor other than 1 (or no exact factor, or an affine offset), in any of its readings."""
    for node in nodes:
        for n in walk(node):
            if isinstance(n, (Quantity, WithUnit)):
                for r in n.unit.readings:
                    if r.factor is None or r.factor != 1 or r.affine is not None:
                        return True
    return False


def _si_differs(nodes: list[Node]) -> bool:
    """True when the SI reading changes some value: a unit with a factor other than 1 (in any of its
    readings) or no exact factor, or a per cent sign."""
    for node in nodes:
        for n in walk(node):
            if isinstance(n, Percent):
                return True
            if isinstance(n, (Quantity, WithUnit)):
                for r in n.unit.readings:
                    if r.factor is None or r.factor != 1 or r.affine is not None:
                        return True
    return False


def _needs_angle(nodes: list[Node]) -> bool:
    for node in nodes:
        for n in walk(node):
            if isinstance(n, Func):
                if n.name in ("arcsin", "arccos", "arctan"):
                    return True
                if n.name in ("sin", "cos", "tan") and not isinstance(n.arg, Degrees) and not any(isinstance(m, Sym) and m.kind == "constant" for m in walk(n.arg)):
                    return True
    return False


#: an angle the text writes in degrees, or a mention of radians (stem-soundness-9)
_DEGREE_TEXT_RE = re.compile(r"°(?![ \t]?[CF](?![A-Za-z]))|\\circ|(?<![A-Za-z])degrees?(?![A-Za-z])(?![ \t]+(?:of[ \t]+freedom|celsius|fahrenheit|C\b|F\b))",
                             re.IGNORECASE)
_RADIAN_TEXT_RE = re.compile(r"(?<![A-Za-z])(?:rad|radians?)(?![A-Za-z])|π|\\pi", re.IGNORECASE)
#: a whole number of radians beyond a full turn is no angle a calculation writes as a bare number
_FULL_TURN = Fraction(63, 10)


def _trig_angles(nodes: list[Node], doc: Optional[StemDocument]) -> list[str]:
    """The angle readings of a trigonometric function of a bare number (stem-soundness-9, round 7). Degrees only when the request or the
    answer writes an angle in degrees and the answer never mentions radians ('a 10 N force at 60°' … '10 cos 60 = −9.5 N' is the
    radian-mode slip and fails), or when every such argument is a whole number beyond a full turn (cos 60); otherwise both, as before."""
    if not _needs_angle(nodes):
        return ["rad"]
    args = [n.arg for node in nodes for n in walk(node) if isinstance(n, Func) and n.name in ("sin", "cos", "tan") and not isinstance(n.arg, Degrees)]
    if doc is not None:
        text = doc.text + "\n" + (doc.request_text or "")
        if _DEGREE_TEXT_RE.search(text) and not _RADIAN_TEXT_RE.search(doc.text):
            return ["deg"]
    whole = [value_of(a) for a in args]
    if whole and all(v is not None and v[2] is None and not v[3] and v[0].denominator == 1 and abs(v[0]) > _FULL_TURN for v in whole):
        return ["deg"]
    return ["deg", "rad"]


def _readings(nodes: list[Node], *, symbol_units: bool = False, force: Optional[str] = None, affine: tuple[bool, ...] = (False,),
              degrees_si: bool = False, pairs: Optional[list[tuple[Node, Node]]] = None,
              doc: Optional[StemDocument] = None, symbol_factors: bool = False) -> tuple[list[Reading], bool]:
    """Every reading of a check (at most 4: ST-PARSE-002 beyond) and whether it is restricted to the
    reading as written by an unknown unit."""
    modes, unknown, ambiguous = _reading_modes(nodes, symbol_units=symbol_units, force=force, pairs=pairs, symbol_factors=symbol_factors)
    angles = _trig_angles(nodes, doc)
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
                    parts = ["SI" if mode == "si" else "as written, per cent as a fraction" if mode == "awp" else "as written"]
                    if len(angles) > 1 or (ang == "deg" and _needs_angle(nodes)):
                        parts.append("angles in degrees" if ang == "deg" else "angles in radians")
                    if ch:
                        parts.append(", ".join(f"unit reading {i + 1}" for _s, i in ch))
                    if len(affine) > 1 or aff:
                        parts.append("with the affine offset" if aff else "without the affine offset (a change)")
                    out.append(Reading(si=mode == "si", units=ch, angle=ang, affine=aff, degrees_si=degrees_si and mode == "si", percent=mode == "awp",
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


#: how deep rule exact-carry follows a carried operand of a carried operand
_EXACT_CARRY_DEPTH = 3


def _exact_as_written(node: Node, unit_text: Optional[str]) -> Optional[Fraction]:
    """The exact value of a closed expression of written numerals as written (``+ − × ÷``, integer powers, signs), when every
    numeral is bare or carries the unit ``unit_text``; None for anything else (a symbol, a function, π, a per cent, a mixed unit, a
    division by zero). Exact rational bookkeeping on the written numerals, as the encoder's pre-checks do: it decides no relation."""
    stack = [node]
    seen = 0
    while stack:
        cur = stack.pop()
        seen += 1
        if seen > 512:
            return None
        if isinstance(cur, Quantity) and (unit_text is None or " ".join(cur.unit.text.split()) != unit_text):
            return None
        if isinstance(cur, (Sym, Func, Root, Percent, Degrees, PlusMinus, IntOp, Ratio, BoolOp)) or not isinstance(cur, (Num, Quantity, Neg, BinOp, Pow, WithUnit)):
            return None
        if isinstance(cur, WithUnit) and (unit_text is None or " ".join(cur.unit.text.split()) != unit_text):
            return None
        stack.extend(children(cur))
    return _rational(node)


def _written_figures(node: Node) -> int:
    """STEM repair 11 (rule exact-rounding): the significant figures of the value ``node`` as written, every trailing zero of an integer
    counting (``80`` -> 2, ``2`` -> 1, ``0.67`` -> 2); 0 for a value with no numeral."""
    v = value_of(node)
    if v is None or v[1] is None:
        return 0
    num = v[1]
    return num.sig_figs if (num.has_point or num.scientific) else num.digit_count


def _rational_form(node: Node) -> bool:
    """STEM repair 11 (rule exact-rounding): ``node`` is rational arithmetic of numerals and symbols (``+ − × ÷``, integer powers, signs):
    no function value, root, constant, application, integer operation or notation outside the encodings, whose exact value the arithmetic
    would not give as a fraction."""
    for n in walk(node):
        if isinstance(n, Sym) and n.kind == "constant":
            return False
        if not isinstance(n, (Num, Sym, Neg, BinOp, Pow)):
            return False
    return True


def _rational(node: Node) -> Optional[Fraction]:
    if isinstance(node, (Num, Quantity)):
        return node.number.value
    if isinstance(node, WithUnit):
        return _rational(node.arg)
    if isinstance(node, Neg):
        v = _rational(node.arg)
        return None if v is None else -v
    if isinstance(node, Pow):
        v = _rational(node.base)
        if v is None or (v == 0 and node.exp <= 0) or abs(node.exp) > 12:
            return None
        return v ** node.exp
    if isinstance(node, BinOp):
        a, b = _rational(node.left), _rational(node.right)
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


def _exact_result(doc: StemDocument, node: Node, depth: int = 0) -> bool:
    """Rule ``exact-carry`` (STEM repair 2): the stated value ``node`` closes written arithmetic that gives it exactly, as written, from
    numerals none of which carries a rounded result (``C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹``, ``820 − 20 = 800``): the
    value was never rounded, so a later line that carries it, or a restatement set against it, has no rounding interval to widen."""
    if depth > _EXACT_CARRY_DEPTH or not isinstance(node, (Num, Quantity)):
        return False
    a, b = getattr(node, "start", -1), getattr(node, "end", -1)
    unit_text = " ".join(node.unit.text.split()) if isinstance(node, Quantity) else None
    for rel in doc.relations:
        if rel.kind != "eq" or rel.outcome != "check" or rel.right is None or rel.left is None or not rel.left.readings or rel.op not in ("=", "≡"):
            continue
        if not (rel.right.start <= a and b <= rel.right.end) or rel.right.node is None or getattr(rel.right.node, "start", -2) != a:
            continue
        left = rel.left.readings[0]
        value = _exact_as_written(left, unit_text)
        if value is None and _exact_mode_chain(doc, rel, left, node):
            # STEM repair 4: 'T = ln 2 ÷ ((ln 2)/8) = 8' is exact working too: every operand and the stated value are exact, so its own
            # check decides it in exact mode (τ = 0, h = 0, function values over enclosures no wider than 10⁻¹⁵); the 8 was never rounded,
            # and a later line that carries it has no rounding interval (it had [7.5, 8.5], which passed a 12% slip)
            return True
        if value is None or value != node.number.value:
            return False
        for leaf in _leaves(left):
            if _carried(doc, leaf) is not None and not _exact_result(doc, _leaf_binding_node(doc, leaf), depth + 1):
                return False
        return True
    return False


def _exact_mode_chain(doc: StemDocument, rel: Relation, left: Node, node: Node) -> bool:
    """Rule ``exact-carry`` (STEM repair 4): the link ``left = node`` is decided in exact mode, as its own check builds it (``_eq``):
    written '=' (or '≡'), no approximate cue, and every numeral of both sides exact as written (no point, no scientific notation, no
    unit), function values and constants included; so its stated value is the exact value of its expression or the check fails."""
    if rel.op not in ("=", "≡") or rel.approx or not isinstance(node, Num) or not _all_exact(left) or not _all_exact(node):
        return False
    st = doc.statement(rel.statement_ids[-1]) if rel.statement_ids else None
    if st is not None:
        before = doc.text[max(st.start, rel.start - 120):rel.start]
        if approx_word_before(before):
            return False
    return True


def _leaf_binding_node(doc: StemDocument, leaf: Node) -> Optional[Node]:
    """The stated value of the earlier result a carried numeral carries (rule exact-carry follows it)."""
    b = _carried(doc, leaf)
    if b is None:
        return None
    for rel in doc.relations:
        if rel.right is not None and rel.right.node is not None and getattr(rel.right.node, "start", -1) == b.start and getattr(rel.right.node, "end", -1) == b.end:
            return rel.right.node
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
        if carried is not None and hw > 0 and _exact_result(ctx.doc, _leaf_binding_node(ctx.doc, leaf)):
            ctx.detail(f"the written {num.text} carries the answer's earlier result for '{carried.symbol}' ({carried.statement_id}), which its "
                       f"arithmetic gives exactly: no rounding interval (rule exact-carry)")
            continue
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


def _binding_range(b: Binding) -> tuple[Fraction, Fraction, Optional[tuple[Fraction, Fraction]]]:
    """``(lo, hi)`` as written and in SI of one binding: a point when it is exact (an integer or fraction
    with no unit), else its rounding interval."""
    exact = b.unit is None and not b.number.has_point and not b.number.scientific
    h = Fraction(0) if exact else b.number.half_width
    lo, hi = b.value - h, b.value + h
    si = None
    s = b.si
    if s is not None and b.unit is not None and b.unit.readings and b.unit.readings[0].factor is not None:
        f = abs(b.unit.readings[0].factor)
        si = (s - h * f, s + h * f)
    elif b.unit is None and b.wrapper == "%":
        si = (lo / 100, hi / 100)
    return lo, hi, si


def _domain_from_bindings(name: str, blist: tuple[Binding, ...]) -> SymbolDomain:
    d = SymbolDomain(name)
    for b in blist:
        lo, hi, si = _binding_range(b)
        g = grounding("request") if b.source == "request" else grounding("figure", f"value of '{name}' stated in {b.statement_id} ({b.source})")
        d.add(lo, hi, si, g, f"{name} = {b.number.text}{(' ' + b.unit.text) if b.unit else ''} ({b.source}, {b.statement_id})")
    return d


def _substitution_domain(ctx: _Ctx, name: str) -> Optional[SymbolDomain]:
    """A symbol the answer binds nowhere but gives a value by substitution (``mg = 5.0 × 9.81`` reads
    m as 5.0): its readings, each widened to the other values of its product group (a substitution
    written in another order)."""
    subs = ctx.doc.substitutions.get(name)
    if not subs:
        return None
    d = SymbolDomain(name)
    seen: set[tuple[Fraction, Fraction]] = set()
    for b in subs:
        lo, hi, si = _binding_range(b)
        if (lo, hi) not in seen:
            seen.add((lo, hi))
            d.add(lo, hi, si, grounding("figure", f"value substituted for '{name}' in {b.statement_id}"), f"{name} = {b.number.text} (substituted in {b.statement_id})")
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
    hit = ctx.cache.get(("domains", tag, reading.si))
    if hit is not None:
        return hit
    b = ctx.builder
    env: dict[str, Term] = {}
    hulls: dict[str, Interval] = {}
    needs_s: set[str] = set()
    for name, dom in domains.items():
        ranges = dom.ranges(reading.si)
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
    ctx.cache[("domains", tag, reading.si)] = out
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
        for b in ctx.doc.bindings.get(n, ()) + ctx.doc.substitutions.get(n, ()):
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
             h_scale_nodes: Optional[list[tuple[Node, Node]]] = None, same_place: bool = False) -> None:
    """Build a Form E or Form S comparison ``|C − S| <= h + τ·|C|`` over every reading (OR) and every
    sign choice of a ``±`` (AND). ``pairs`` are (computed node, stated node) per operand combination;
    ``h_written`` their half-widths as written. ``env_for(reading, tag)`` installs symbol domains. With ``same_place`` (rule same-place,
    STEM repair 5: a restatement with a stated rounding), a stated value whose band equals the half-width of the value it is set
    against (the same last place, in the reading's units) must equal it: h is 0, never the two half-widths added."""
    b = ctx.builder
    bands: list[dict] = []
    uses_intervals = force_form_s
    errors: list[EncodeError] = []
    total = len(pairs) * len(readings) * len(signs)
    idx = 0
    frames: set[int] = set()
    labels: list[str] = []
    for ci, (cnode, snode) in enumerate(pairs):
        for ri, reading in enumerate(readings):
            sign_bands: list[dict] = []
            failed = False
            for sign in signs:
                idx += 1
                rd = Reading(si=reading.si, units=reading.units, angle=reading.angle, affine=reading.affine, sign=sign, degrees_si=reading.degrees_si,
                             percent=reading.percent,
                             label=reading.label + ("" if len(signs) == 1 else (", + branch" if sign > 0 else ", − branch")))
                tag = "" if ri == 0 else f"r{ri + 1}"
                try:
                    env, hulls, needs_s = env_for(rd, tag) if env_for is not None else ({}, {}, frozenset())
                    enc = Encoder(b, rd, env=env, intervals=intervals, symbol_hulls=hulls, interval_symbols=needs_s, cache=ctx.cache)
                    c = enc.term(cnode)
                    s = enc.term(snode)
                    scale = _scale_for(snode, rd, enc)
                    h = h_written[ci] * scale
                    if h_scale_nodes is not None:
                        extra_node = h_scale_nodes[ci][0]
                        if extra_node is not None:
                            extra = _value_half_width(extra_node) * _scale_for(extra_node, rd, enc)
                            if same_place and h > 0 and extra == h:
                                h = Fraction(0)
                                ctx.detail("the restated value is rounded to the place the value it restates is written to, so it must equal it: h = 0 "
                                           "(rule same-place)")
                            else:
                                h += extra
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
            labels.append(reading.label + (f" (operand reading {ci + 1})" if len(pairs) > 1 else ""))
    if not bands:
        raise errors[0] if errors else EncodeError("ST-UNDEC-001", "no reading of the relation could be encoded")
    ctx.readings = list(dict.fromkeys(labels))
    nonzero = sorted(f for f in frames if f != 0)
    if nonzero:
        b.note("decimal exponent factored: " + ", ".join(f"10^{f}" for f in nonzero))
        ctx.detail("decimal exponent factored: " + ", ".join(f"10^{f}" for f in nonzero))
    b.note("readings: " + "; ".join(ctx.readings))
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


#: STEM repair 3: why a check a rule sets against a definition fails at warning severity (rules percentage-change and half-lives)
_TITLED_WARNINGS = {
    "rule percentage-change": "which of the two values is the starting one is read from the word the statement or its part's question writes (increase or "
                              "decrease), a reading the answer did not state as a formula (rule percentage-change)",
    "rule half-lives": "the number of half-lives is read from the prose, and the half-life is the value the answer states for its half-life symbol "
                       "(rule half-lives)",
    # STEM repair 8
    "rule law-values": "which of the line's values stands for which symbol of the law is read from their dimensions, a reading the answer did not "
                       "state (rule law-values)",
    # STEM repair 9
    "rule given-function": "that the Given restates the request's function at its argument is a reading (rule given-function)",
    # STEM repair 11
    "rule function-value, the request's function": "that the function whose value the statement gives is the request's function of that name is a "
                                                   "reading (rule function-value)",
    "rule derivative, the request's function": "that the letter differentiated is the request's function of that name is a reading (rule derivative)",
    "rule decay-law": "the number of half-lives is read from the prose, and the value before the decay is the one value of the result's dimension "
                      "the line takes (rule decay-law)",
    "rule statistics": "which values the statistic is of is read from the prose (the values it lists, or the supplied table's column its words name), "
                       "and the STEM pack forms the statistic from them (rule statistics)",
    "rule rounded-digits": "which value the rounding the prose states is of is read from the prose, and the place a value is written to from its "
                           "numeral (rule rounded-digits)",
}


def _eq(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.title:
        # a line set against a definition by a rule (STEM repair 3): what is compared, and why a failure is a warning
        ctx.detail(f"compared: {rel.reason}")
        why = next((w for k, w in _TITLED_WARNINGS.items() if k in (rel.reason or "")), None)
        if why is not None:
            ctx.warn(why)
    combos = _operand_combos(rel.left, rel.right)
    if combos and all(isinstance(c, Ratio) and isinstance(sn, Ratio) for c, sn in combos):
        # a:b = c:d is a·d = b·c over closed terms (design section 7.4): the cross products are compared
        combos = [(BinOp("*", c.left, sn.right, c.start, c.end), BinOp("*", c.right, sn.left, sn.start, sn.end)) for c, sn in combos]
        ctx.detail("a ratio equality a:b = c:d, compared as a·d = b·c")
    angle = bool(combos) and all(_top_degrees(c) != _top_degrees(sn) for c, sn in combos)
    if angle:
        # stem-soundness-8 (round 7): an angle in degrees set equal to one in radians or to a number ('θ = 30° = 0.524 rad', '2 rad = 115°',
        # '180° = π rad') is a conversion: compared in SI, the degree read as π/180 rad (an enclosure of π); before, the two numbers were
        # compared as written (30 against 0.524) and every correct conversion failed
        combos = [(_degree_units_as_degrees(c), _degree_units_as_degrees(sn)) for c, sn in combos]
        ctx.detail("an angle in degrees set against one in radians (or a number): compared in radians, a degree read as π/180 rad")
    scaled = [_antilog_as_concentration(c, sn) for c, sn in combos]
    scale_unit = bool(combos) and all(x is not None for x in scaled)
    if scale_unit:
        combos = [x for x in scaled if x is not None]  # [H⁺] = 10^(−8.2) = 6.31 × 10⁻⁹ mol dm⁻³: the power is read in mol dm⁻³
    approx = _approx(ctx)
    pairs: list[tuple[Node, Node]] = []
    hs: list[Fraction] = []
    extra: list[tuple[Node, Node]] = []
    intervals: dict[tuple[int, int], IntervalLeaf] = {}
    exact_modes = []
    rounded_exact: list[bool] = []
    stated_rounding: list[str] = []
    for cnode, snode in combos:
        unc = _uncertainty(cnode, snode) if rel.op in ("=", "≈") else None
        if unc is not None:
            # STEM repair 3 (rule central-value): '586 − 20 = 556 ± 12' states 556 as the value of 586 − 20 and 12 as its uncertainty. The
            # computed value is set against the central value under R1 to R4, the band never widening h: a slip within the stated
            # uncertainty (566 written 556) had passed. The uncertainty itself is not checked, and the statement says so.
            snode = unc[0]
            ctx.detail(f"the stated value carries an absolute uncertainty (± {render(unc[1])[:40]}): the computed value is set against its central value "
                       f"{render(unc[0])[:40]} under the tolerance rule, the uncertainty never widening the band, and the uncertainty itself is not checked "
                       "(rule central-value)")
        exact = rel.op in ("=", "≡") and not approx and _all_exact(cnode) and _all_exact(snode)
        exact_modes.append(exact)
        if exact:
            # STEM repair 11 (rule exact-rounding): in exact mode τ = 0, and a stated value closing rational written arithmetic has half a unit in
            # its last written digit, every trailing zero counting (1/2 for a whole number): a whole computed value is still stated exactly (two
            # whole numbers within 1/2 are equal), while one that is not whole may be stated at the nearest whole number ('(92 − 18) ÷ 18 × 100 =
            # 411%', '1,000 ÷ 3 = 333'). Before, h was 0, so every such rounded quotient failed as an error (INT-SUBJ-001 on correct working). A
            # side with a function value or a constant (ln, √, π), an exact fraction or a surd stated keeps h = 0 (exact work, rule exact-carry)
            # (rule rounded-digits sets places against places: exact by nature, so its h stays 0). A stated value of one significant figure
            # shows no rounding ('7/3 = 2', '2 ÷ 3 = 0.7'), as a one-figure value is no written constant either (constants.match_written): it
            # keeps h = 0 unless the line states its rounding (rule result-rounding)
            h = _value_half_width(snode, min_sf=_EVERY_DIGIT) if (is_value(snode) and _exact_as_written(cnode, None) is not None
                                                                   and _written_figures(snode) >= 2
                                                                   and "(rule rounded-digits)" not in (rel.reason or "")) else Fraction(0)
            if h:
                rounded_exact.append(True)
        else:
            h = _value_half_width(snode, min_sf=_min_sig_figs(cnode)) if is_value(snode) else Fraction(0)
        if rel.rounding is not None and not rel.title and is_value(snode):
            # STEM repair 11 (rule result-rounding): the line states the rounding of its own result ('= 34% to 2 s.f.', '= 330 (to 2 s.f.)', '= 34%
            # (to the nearest whole number)'): its half-width is that rounding's, never less than half a unit in its last written digit, every zero
            # counted (as rule rounding-cue reads a restated value's); before, a stated rounding was read for restated values only
            h = max(h, rel.rounding, _value_half_width(snode, min_sf=_EVERY_DIGIT))
            stated_rounding.append(rel.rounding_phrase)
        pairs.append((cnode, snode))
        hs.append(h)
        extra.append((cnode if (is_value(cnode) and not exact) else None, snode))  # type: ignore[arg-type]
        intervals.update(_interval_leaves(ctx, cnode, exact_mode=exact))
    if rel.cut_spans:
        # STEM repair 11 (rule inequality-solution): a numeral of the computed bound written with its digits cut ('135.36…') ranges over
        # [w − u/2, w + u] (cut, or rounded, digits), u a unit in its last written digit
        for cnode, _s in pairs:
            for leaf in _leaves(cnode):
                if (leaf.start, leaf.end) in rel.cut_spans and isinstance(leaf, Num):
                    u = 2 * leaf.number.half_width_for(_EVERY_DIGIT)
                    intervals[(leaf.start, leaf.end)] = IntervalLeaf(leaf.number.value - u / 2, leaf.number.value + u, "carried",
                                                                     f"the {leaf.number.text}… the answer writes with its digits cut ranges over "
                                                                     f"[w − u/2, w + u] (rule inequality-solution)")
    exact_mode = all(exact_modes)
    tau = Fraction(0) if exact_mode else (TAU_APPROX if approx else TAU_EQUAL)
    if rel.title and "(rule inequality-solution)" in (rel.reason or ""):
        tau, exact_mode = Fraction(0), False  # the bound is the relation before it solved exactly: no relative slack (its cut values are intervals)
    precision = None
    if not exact_mode and not approx and rel.op in ("=", "≡") and not intervals and (not rel.title or "(rule statistics)" in (rel.reason or "")
                                                                                     or "(rule definite-integral)" in (rel.reason or "")
                                                                                     or "(rule ellipsis-rounding)" in (rel.reason or "")):
        precision = _operand_rounding_tau(pairs, _given_exact(ctx.doc))
        if precision is not None and precision < tau:
            # STEM repair 4 (rule operand-precision): τ covers operands written to fewer digits than were used; when every operand is a
            # written numeral (no carried result, no constant, no symbol or function), what their rounding can move the computed value is
            # bounded exactly, and a slip beyond twice that bound fails though it is under 1/100 ('4000 × 1.036³ = 4467.74', 0.45%)
            tau = precision
        else:
            precision = None
    if rel.title and "(rule given-function)" in (rel.reason or ""):
        # STEM repair 9 (rule given-function): a Given restates the request's data as written: the request's function at the Given's
        # argument against the Given value with τ = 0, every written digit of the Given counting (rule given-digits)
        tau, precision, exact_mode = Fraction(0), None, False
        hs = [_value_half_width(snode, min_sf=_EVERY_DIGIT) if is_value(snode) else Fraction(0) for _c, snode in pairs]
        extra = [(None, snode) for _c, snode in pairs]
        ctx.detail("a Given restates the request's data as written: τ = 0, every written digit of the Given counting (rule given-digits)")
    if rel.title and "(rule ellipsis-rounding)" in (rel.reason or ""):
        # STEM repair 10 (rule ellipsis-rounding): the stated value is written with its digits cut ('8/3 = 2.66…', w with u a unit in its last
        # written digit): the computed value lies in [w, w + u) read as cut, or in [w − u/2, w + u/2] read as rounded, so in their hull
        # [w − u/2, w + u]: |C − (w + u/4)| ≤ 3u/4 (+ τ·|C|, τ by rule operand-precision)
        units = [2 * _value_half_width(snode, min_sf=_EVERY_DIGIT) for _c, snode in pairs]
        pairs = [(cnode, BinOp("+", snode, Num(ExactNumber(text=_ratio(u / 4), value=u / 4, sig_figs=1, last_place=0, exact=True), getattr(snode, "start", 0),
                                                getattr(snode, "end", 0)), getattr(snode, "start", 0), getattr(snode, "end", 0), "+"))
                 for (cnode, snode), u in zip(pairs, units)]
        hs = [3 * u / 4 for u in units]
        extra = [(None, None) for _p in pairs]  # type: ignore[misc]
        ctx.detail("the value written with its digits cut ranges over [w − u/2, w + u] (cut, or rounded, digits), u a unit in its last written digit: "
                   "the computed value is set against the centre w + u/4 within 3u/4")
    nodes = [n for p in pairs for n in p]
    for n in dict.fromkeys(m for cnode, _s in pairs for m in walk(cnode) if isinstance(m, IntOp)):
        ctx.detail(f"integer arithmetic: {render(n)[:80]} is the {'remainder' if n.op == 'mod' else 'integer quotient'} of whole numbers "
                   "(read from the words mod, div, the signs %, // or a stated remainder)")
    # stem-precision-5: a compound quantity ('4 min 30 s') has a value in SI only (as written its parts would be added as plain numbers)
    compound = any(isinstance(m, BinOp) and m.op == "+" and m.implicit for n in nodes for m in walk(n))
    readings, unknown = _readings(nodes, force="si" if (scale_unit or angle or compound) else None, pairs=pairs, degrees_si=angle, doc=ctx.doc)
    if unknown:
        ctx.warn("a unit is not recognised (ST-UNIT-001); the relation is checked as written only")
    elif scale_unit:
        readings = [replace(r, label=r.label + ", the power of ten read in mol dm⁻³") for r in readings]
        ctx.detail("an antilogarithm stated as a concentration (a lone power of ten whose exponent is no integer, 10^(−pH)) is the concentration "
                   "in mol dm⁻³, the unit the pH, pOH, pKa and pKb scales are defined in, and is compared with the stated value in SI; it is never "
                   "read as a bare number in SI, which would take a unit prefix (an integer power of ten) for a change of the exponent")
    if stated_rounding:
        ctx.detail(f"the line states the rounding of its result ({stated_rounding[0]}): h is that rounding's, never less than half a unit in the "
                   "value's last written digit (rule result-rounding)")
    if exact_mode and rounded_exact:
        ctx.detail("exact mode: every operand and the stated value are exact (τ = 0); the stated value, of two or more significant figures, closes "
                   "rational written arithmetic, so h is half a unit in its last written digit, every trailing zero counting: a whole computed value "
                   "must be stated exactly, one that is not whole may be stated to that digit (rule exact-rounding)")
    elif exact_mode:
        ctx.detail("exact mode: every operand and the stated value are exact (τ = 0, h = 0)")
    elif precision is not None:
        ctx.detail(f"τ = {_ratio(tau)}: twice the largest relative change the rounding of the written operands can make to the computed value, "
                   "below 1/100 (rule operand-precision)")
    elif not (rel.title and "(rule given-function)" in (rel.reason or "")):
        ctx.detail(f"τ = {_ratio(tau)}")
    signs = (1, -1) if _has_plus_minus(*nodes) else (1,)
    _compare(ctx, pairs, kind="eq", tau=tau, h_written=hs, readings=readings, intervals=intervals, signs=signs, h_scale_nodes=extra)


def _degree_unit(unit: UnitExpr) -> bool:
    """A unit that is exactly the degree (°, 'degrees')."""
    return len(unit.readings) == 1 and len(unit.readings[0].atoms) == 1 and unit.readings[0].atoms[0].unit is not None \
        and unit.readings[0].atoms[0].unit.angle_degrees == 1 and unit.readings[0].atoms[0].power == 1


def _top_degrees(node: Node) -> bool:
    """``node`` writes an angle in degrees outside a function's argument (``30°``, ``30 degrees``; not ``sin 30°``)."""
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, (Func, Unsupported)):
            continue
        if isinstance(n, Degrees) or (isinstance(n, Quantity) and _degree_unit(n.unit)):
            return True
        stack.extend(children(n))
    return False


def _degree_units_as_degrees(node: Node) -> Node:
    """A value written with the unit 'degrees' (or °) as the degree node the encoder converts to radians (``Degrees``)."""
    if isinstance(node, Quantity) and _degree_unit(node.unit):
        return Degrees(Num(node.number, node.start, node.end), node.start, node.end)
    if isinstance(node, Neg):
        inner = _degree_units_as_degrees(node.arg)
        return node if inner is node.arg else Neg(inner, node.start, node.end)
    return node


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


#: rule operand-precision (STEM repair 4): τ is rounded up to this granularity
_PRECISION_GRAIN = 10 ** 6


def _given_exact(doc: StemDocument) -> tuple[frozenset[Fraction], frozenset[Fraction]]:
    """Rule ``operand-precision`` for given data (STEM repair 10): the values the request states, taken as written (R3), so a numeral of a
    computed side that writes one of them is exact, not rounded: ``(numbers with no unit, quantities in SI)``. A per cent the request
    states gives its decimal and the growth and decay factors 1 ± the decimal ('3.6%' gives 0.036, 1.036 and 0.964: '4000(1.036)^{12}'
    takes the request's rate as written)."""
    nums: set[Fraction] = set()
    qty: set[Fraction] = set()
    for node, _a, _b, _w in doc.request.values:
        v = value_of(node)
        if v is None or v[1] is None:
            continue
        if v[3] == "%" and v[2] is None:
            p = v[0] / 100
            nums.update((p, 1 + p, 1 - p))
        elif v[2] is None and not v[3]:
            nums.add(v[0])
        elif v[2] is not None and not v[2].unknown and not v[3]:
            si = si_value(v[0], v[2], "")
            if si is not None:
                qty.add(si)
    return frozenset(nums), frozenset(qty)


def _operand_rounding_tau(pairs: list[tuple[Node, Node]], given: tuple[frozenset[Fraction], frozenset[Fraction]] = (frozenset(), frozenset())
                          ) -> Optional[Fraction]:
    """Rule ``operand-precision`` (STEM repair 4): twice the largest relative change that rounding the written measured operands of a
    computed side can make to its value (each operand ranging over [w − h(w), w + h(w)], an exact operand over its value), rounded up
    to a millionth; None when a side is not an expression of written numerals (``+ − × ÷``, integer powers, signs, per cents) whose
    units all have the factor 1, or when its value is zero. Exact interval arithmetic on the written numerals, as the encoder's
    pre-checks do: it decides no relation; the engine decides the band. STEM repair 10: a numeral that writes a value the request
    states (``given``, :func:`_given_exact`) is given data, taken as written (R3): it is exact, never rounded, so '4000(1.036)^{12} =
    6141.73' fails though it is within 1/100 (the request's 3.6% makes 1.036 exact; before, its rounding left τ at 1/100)."""
    worst = Fraction(0)
    for cnode, snode in pairs:
        if _trailing_zero_whole(snode):
            return None  # '1000 ÷ 3 = 330': a whole number's trailing zero may be a rounding place, which τ = 1/100 leaves room for
        rb = _rounding_bound(cnode, 0, given)
        if rb is None or rb[0] == 0:
            return None
        dev = rb[1]
        if not is_value(snode):
            # STEM repair 10: a stated side that is itself an expression of written numerals ('1/4.0 Ω + 1/6.0 Ω = 0.250 Ω⁻¹ + 0.167 Ω⁻¹')
            # carries their rounding too (it has no half-width of its own in the band): it is added to the computed side's
            sb = _rounding_bound(snode, 0, given)
            if sb is None:
                return None
            dev += sb[1]
        worst = max(worst, 2 * dev / abs(rb[0]))
    grain = _PRECISION_GRAIN
    return Fraction(-((-worst.numerator * grain) // worst.denominator), grain) if worst else Fraction(0)


def _trailing_zero_whole(node: Node) -> bool:
    """A stated value (or the central value of ``S ± u``) that is a whole number written without a point and ending in zero (rule
    operand-precision leaves its τ at 1/100: which of its zeros are significant is not written)."""
    if isinstance(node, PlusMinus) and node.left is not None:
        node = node.left
    while isinstance(node, Neg):
        node = node.arg
    if not isinstance(node, (Num, Quantity)):
        return False
    n = node.number
    return not n.has_point and not n.scientific and n.value.denominator == 1 and n.value != 0 and n.value % 10 == 0


def _rounding_bound(node: Node, depth: int, given: tuple[frozenset[Fraction], frozenset[Fraction]] = (frozenset(), frozenset())
                    ) -> Optional[tuple[Fraction, Fraction]]:
    """``(value, the largest deviation the rounding of its written measured numerals can cause)`` for an expression of written numerals
    (rule operand-precision), else None. A numeral that writes a value the request states is exact (STEM repair 10)."""
    if depth > 48:
        return None
    if isinstance(node, Num):
        n = node.number
        return n.value, (n.half_width if is_measured(n, False) and n.value not in given[0] else Fraction(0))
    if isinstance(node, Quantity):
        u = node.unit
        if u.unknown or len(u.readings) != 1 or u.readings[0].factor != 1 or u.readings[0].affine is not None:
            return None
        return node.number.value, (Fraction(0) if node.number.value in given[1] else node.number.half_width)
    if isinstance(node, Neg):
        a = _rounding_bound(node.arg, depth + 1, given)
        return None if a is None else (-a[0], a[1])
    if isinstance(node, Percent):
        a = _rounding_bound(node.arg, depth + 1, given)
        return None if a is None else (a[0] / 100, a[1] / 100)
    if isinstance(node, Pow):
        a = _rounding_bound(node.base, depth + 1, given)
        if a is None or node.exp == 0 or abs(node.exp) > 12:
            return None
        v, e = a
        k = abs(node.exp)
        top = (abs(v) + e) ** k - abs(v) ** k
        if node.exp > 0:
            return v ** k, top
        if abs(v) <= e:
            return None
        lo = (abs(v) - e) ** k
        return 1 / v ** k, (abs(v) ** k - lo) / (abs(v) ** k * lo)
    if isinstance(node, BinOp) and node.op in "+-*/":
        a, b = _rounding_bound(node.left, depth + 1, given), _rounding_bound(node.right, depth + 1, given)
        if a is None or b is None:
            return None
        (va, ea), (vb, eb) = a, b
        if node.op == "+":
            return va + vb, ea + eb
        if node.op == "-":
            return va - vb, ea + eb
        if node.op == "*":
            return va * vb, abs(va) * eb + abs(vb) * ea + ea * eb
        if abs(vb) <= eb or vb == 0:
            return None
        return va / vb, (abs(va) * eb + abs(vb) * ea) / (abs(vb) * (abs(vb) - eb))
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
    if rel.title:
        # rule prose-conversion (STEM repair 5): a value the prose restates right after it in another unit ('55.0 cm³, that is 0.0550 dm³')
        ctx.detail("a value the prose states and restates right after it in another unit of the same dimension (rule prose-conversion)")
    tau = TAU_APPROX if approx else Fraction(0)
    left, right = combos[0]
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
    affine_units = any(r.affine is not None for r in lu.readings) or any(r.affine is not None for r in ru.readings)
    affine: tuple[bool, ...] = (False,)
    if affine_units:
        change = _change_context(ctx)
        affine = (False,) if change else (True,)
        ctx.detail("°C/°F offset " + ("not applied: the statement speaks of a change" if change else "applied (an explicit temperature conversion)"))
    degrees_si = (lv[3] == "°" or rv[3] == "°") and ((lu.dim is not None and lu.dim.angle) or (ru.dim is not None and ru.dim.angle))
    readings, _unknown = _readings([left, right], force="si", affine=affine, degrees_si=bool(degrees_si))
    _compare(ctx, [(left, right)], kind="cnv", tau=tau, h_written=[_value_half_width(right)], readings=readings, intervals={},
             h_scale_nodes=[(left, right)], label="value converted to SI", stated_label="stated value in SI")


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


def _res_finer(ctx: _Ctx) -> None:
    """Rule ``finer-restatement`` (STEM repair 7): a value restated with a rounding the prose states that is finer than the chain's stated
    final value, set against the value the chain's written arithmetic gives: |C − S| ≤ h(S), h the stated rounding's half-width (never
    less than half a unit in S's last written digit), τ = 0, C from the numerals as written (a carried result or a written constant over
    its interval: Form S then). Failing it is a warning: that the restated value is the line's arithmetic as written is a reading the answer
    did not state."""
    rel = ctx.rel
    pairs = [(l, r) for l, r in _operand_combos(rel.left, rel.right)]
    readings, unknown = _readings([n for p in pairs for n in p])
    if unknown:
        ctx.warn("a unit is not recognised (ST-UNIT-001); the restatement is checked as written only")
    hs = [max(rel.rounding or Fraction(0), _value_half_width(r, min_sf=_EVERY_DIGIT)) for _l, r in pairs]
    intervals: dict[tuple[int, int], IntervalLeaf] = {}
    for cnode, _s in pairs:
        intervals.update(_interval_leaves(ctx, cnode, exact_mode=False))
    ctx.detail(f"the restated value is rounded as the prose states ({rel.rounding_phrase}): h = {_ratio(hs[0])}, finer than the final value of the "
               "chain, so it is set against the value the chain's written arithmetic gives, its numerals as written (rule finer-restatement)")
    ctx.warn("that the restated value is the value the line's arithmetic gives as written is a reading the answer did not state (it may have "
             "computed with figures its working does not show; rule finer-restatement)")
    _compare(ctx, pairs, kind="res", tau=Fraction(0), h_written=hs, readings=readings, intervals=intervals,
             label="value the chain's written arithmetic gives", stated_label="restated value")


def _res(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.finer:
        _res_finer(ctx)
        return
    combos = _operand_combos(rel.left, rel.right)
    pairs = [(l, r) for l, r in combos]
    readings, unknown = _readings([n for p in pairs for n in p])
    if unknown:
        ctx.warn("a unit is not recognised (ST-UNIT-001); the restatement is checked as written only")
    if rel.named:
        ctx.warn(f"the prose names the quantity ('{rel.named}') whose value before the change it states; the earlier value is matched to it by "
                 "those words (rule named-change), a reading the answer did not state")
    if rel.restates:
        ctx.warn(f"the value stated for {rel.restates} after 'so' is read as the value the chain before it on the same line computed (rule "
                 "restated-binding), a reading the answer did not state")
    hs = [_value_half_width(r) for _l, r in pairs]
    if rel.rounding is not None:
        # rule rounding-cue: the prose states the rounding of the restated value, so its half-width is that rounding's. The stated
        # rounding says which trailing zeros of a whole number are significant ("to the nearest whole number, 60%" is 59.5 to 60.5,
        # not 55 to 65); it never narrows the band below half a unit in the value's last written digit, every zero counted
        hs = [max(rel.rounding, _value_half_width(r, min_sf=_EVERY_DIGIT)) for _l, r in pairs]
        ctx.detail(f"the restated value is rounded as the prose states ({rel.rounding_phrase}): h = {_ratio(rel.rounding)}")
    exact = [_exact_result(ctx.doc, l) for l, _r in pairs]
    if "(rule ellipsis-rounding)" in (rel.reason or ""):
        # STEM repair 10 (rule ellipsis-rounding): the value before the restated one is written with its digits cut ('4787.58…', w with u a unit
        # in its last written digit): it lies in [w, w + u) read as cut, or in [w − u/2, w + u/2] read as rounded, so in their hull [w − u/2, w + u].
        # The restated value must be within its own half-width (or its stated rounding's) of some value of the hull: |(w + u/4) − S| ≤ h + 3u/4
        ctx.detail(f"compared: {rel.reason}")
        units = [2 * _value_half_width(l, min_sf=_EVERY_DIGIT) for l, _r in pairs]
        centred = [(BinOp("+", l, Num(ExactNumber(text=_ratio(u / 4), value=u / 4, sig_figs=1, last_place=0, exact=True), getattr(l, "start", 0),
                                      getattr(l, "end", 0)), getattr(l, "start", 0), getattr(l, "end", 0), "+"), r) for (l, r), u in zip(pairs, units)]
        hs = [h + 3 * u / 4 for h, u in zip(hs, units)]
        ctx.detail("the value written with its digits cut ranges over [w − u/2, w + u] (cut, or rounded, digits), u a unit in its last written digit: "
                   "the restated value is set against the centre w + u/4 with 3u/4 added to its band")
        _compare(ctx, centred, kind="res", tau=Fraction(0), h_written=hs, readings=readings, intervals={}, h_scale_nodes=[(None, r) for _l, r in pairs],
                 label="value written with its digits cut", stated_label="restated value", same_place=False)
        return
    if any(exact):
        ctx.detail("the chain's final value is given exactly by its written arithmetic: it carries no rounding, so its half-width is 0 (rule exact-carry)")
    prose = "the prose restates right after the value it states" in (rel.reason or "")  # rule rounding-cue (STEM repair 5)
    if "(rule condition-result)" in (rel.reason or ""):
        # STEM repair 10 (rule condition-result): two values the answer computes for one symbol under one condition
        ctx.detail(f"compared: {rel.reason}")
        ctx.warn("that the two values the answer computes for the symbol under the same condition are values of one quantity is a reading (rule "
                 "condition-result)")
    if prose:
        ctx.detail("against the value the prose states right before it, restated with the rounding the prose states (rule rounding-cue)")
    if _APPROX_BEFORE_RE.search(ctx.doc.text[max(0, rel.start - 40):rel.start]):
        # STEM repair 12 (rule inline-restatement): an approximation word right before the restated value names its rounding; R2's 1/20 never
        # applies to a restated result (R8), and the detail says so, since the bracketed short form says "1/20 for ≈/about, any check". A value
        # on the line of the chain it restates names the reading it rests on ('= 2.67 A, which is about 2.7 A')
        ctx.detail("τ = 0 (a restated result: the approximation word before it names its rounding, R8)"
                   + (", on the line of working it restates (rule inline-restatement)" if "on the same line" in (rel.reason or "") else ""))
    _compare(ctx, pairs, kind="res", tau=Fraction(0), h_written=hs, readings=readings, intervals={},
             h_scale_nodes=[(None if ex else l, r) for (l, r), ex in zip(pairs, exact)],
             label="value the prose states" if prose else "final value of the chain", stated_label="restated value", same_place=rel.rounding is not None)


def _tgt(ctx: _Ctx) -> None:
    rel = ctx.rel
    combos = _operand_combos(rel.left, rel.right)
    pairs = [(l, r) for l, r in combos]
    readings, _unknown = _readings([n for p in pairs for n in p])
    tau = TAU_APPROX if rel.approx else Fraction(0)
    hs = [_value_half_width(r) for _l, r in pairs]
    ctx.warn("the show-that target is the request's reading of the answer")
    _compare(ctx, pairs, kind="tgt", tau=tau, h_written=hs, readings=readings, intervals={}, h_scale_nodes=[(l, r) for l, r in pairs],
             label="answer's final value", stated_label="show-that target")
    _regound_stated(ctx, "request")


def _regound_stated(ctx: _Ctx, kind: str) -> None:
    """The stated side of a target or given check is the request's value: ground it as such."""
    for p in ctx.builder.premises:
        if p["id"] == "R" or p["id"].startswith("R_"):
            p["grounding"] = grounding(kind)


#: STEM repair 8: the ``giv`` checks that set a value the working takes against values other than the request's Givens (rules
#: condition-value, name-list and table-terms, the last for a row's value and for a value of the table's quantity the request states): why
#: a failure is a warning, what the pinned value is, what each candidate is and states, and what the conclusion says
_GIV_RULES: dict[str, dict[str, str]] = {
    "condition-value": {
        "why": "which value of the run's computation stands for the condition the run is stated under is a reading (rule condition-value)",
        "w": "the value the computation takes for its condition", "cand": "the condition", "states": "the run is stated under",
        "concl": "the value the computation takes for its condition matches that condition (R7)"},
    "name-list": {
        "why": "which of the values the prose lists the computation's value stands for is a reading (rule name-list)",
        "w": "the value the computation takes", "cand": "the listed value", "states": "the prose lists",
        "concl": "the value the computation takes is one of the values the prose lists, as written (R7)"},
    "table-terms-row": {
        "why": "which row's value the working's number stands for is a reading: the one row its line or its part's question names whose value the "
               "working takes nowhere (rule table-terms)",
        "w": "the value the working takes", "cand": "the supplied table's", "states": "the supplied table gives",
        "concl": "the value the working takes matches the supplied table's data (R7, the data exact)"},
    # STEM repair 9 (rule row-terms): a value a line takes in place of one repeat of the row it names
    "row-terms": {
        "why": "which of the row's repeats the working's number stands for is a reading: the one repeat of the row its line or its part's question "
               "names that the working takes nowhere (rule row-terms)",
        "w": "the value the working takes", "cand": "the supplied table's", "states": "the supplied table gives",
        "concl": "the value the working takes matches the supplied table's data (R7, the data exact)"},
    # STEM repair 10 (rule named-component): the value a working substitutes against the component its statement names by its value
    "named-component": {
        "why": "which component the working's value stands for is a reading: the component the statement names by its value, whose quantity the "
               "working computes (rule named-component)",
        "w": "the value the working substitutes", "cand": "the component the statement names,", "states": "the statement names the component",
        "concl": "the value the working substitutes is the value of the component the statement names (R7)"},
    # STEM repair 11 (rule same-shape): a value in the place where the answer's other evaluation of the same expression writes the request's
    "same-shape": {
        "why": "that the line evaluates the same expression as the answer's other line, with the request's value in that place, is a reading "
               "(rule same-shape)",
        "w": "the value the working writes", "cand": "the request's value", "states": "the request states",
        "concl": "the value the working writes is the request's value its other evaluation of the expression writes in that place (R7, the data "
                 "exact)"},
    # STEM repair 11 (rule unbound-substitution): a value substituted for a symbol the answer gives no value, against the request's value
    # the answer substitutes for that symbol elsewhere
    "unbound-substitution": {
        "why": "that the symbol stands for the request's quantity whose value the answer substitutes for it elsewhere is a reading (rule "
               "unbound-substitution)",
        "w": "the value the working substitutes", "cand": "the request's value", "states": "the request states",
        "concl": "the value the working substitutes is the request's value the answer substitutes for the symbol elsewhere (R7, the data exact)"},
    "table-terms-quantity": {
        "why": "that the working's number stands for a value the request or its supplied texts state for the table's quantity is a reading "
               "(rule table-terms)",
        "w": "the value the working takes", "cand": "the value the supplied texts state", "states": "the request or its supplied texts state",
        "concl": "the value the working takes matches a value the request or its supplied texts state for that quantity (R7, the data exact)"},
}


def _giv(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.right is None or rel.right.node is None or not rel.candidates:
        raise EncodeError("ST-UNDEC-001", "a Given value with no request value to compare")
    node = rel.right.node
    v = value_of(node)
    if v is None or v[1] is None:
        raise EncodeError("ST-UNDEC-001", "a Given value that is not a single value")
    if rel.reason:
        ctx.detail(f"compared: {rel.reason}")  # STEM repair 2: which request or table values the stated value is set against
    reason = rel.reason or ""
    r8 = (_GIV_RULES["condition-value"] if "(rule condition-value)" in reason else _GIV_RULES["name-list"] if "(rule name-list)" in reason else
          _GIV_RULES["named-component"] if "(rule named-component)" in reason else
          _GIV_RULES["same-shape"] if "(rule same-shape)" in reason else _GIV_RULES["unbound-substitution"] if "(rule unbound-substitution)" in reason else
          _GIV_RULES["row-terms"] if "rule row-terms)" in reason and "in place of the supplied table's" in reason else
          _GIV_RULES["table-terms-row" if "in place of the supplied table's" in reason else "table-terms-quantity"] if "(rule table-terms)" in reason
          else None)
    if r8 is not None:
        ctx.warn(r8["why"])
    elif "rule stated-uncertainty" in rel.reason:
        ctx.warn("which value the percentage the answer states is of, the one value the line takes from that column, is a reading (rule stated-uncertainty)")
    elif rel.exact_candidates and "rule table-operands" in rel.reason:
        ctx.warn(f"which rows of the supplied table ({rel.named}) the value the working takes belongs to is a reading: the rows its line or its part's "
                 "question names (rule table-operands)")
    elif rel.exact_candidates:
        ctx.warn(f"which rows and which column of the supplied table the prose means ({rel.named}) is a reading (rule table-data)")
    elif "rule processed-data" in rel.reason:
        ctx.warn("which value the working means, the supplied table's or the one the answer processed it into, is a reading (rule processed-data)")
    elif rel.named:
        pass  # rule named-given: its own reading is stated below
    elif "rule restated-unit" in rel.reason:
        ctx.warn("that the value restates the task's quantity of the same number is a reading (rule restated-unit)")
    elif "rule given-uncertainty" in rel.reason:
        ctx.warn("which of the uncertainties the request and its supplied texts state the Given restates is a reading (rule given-uncertainty)")
    elif "rule given-kinds" in rel.reason:
        ctx.warn("that the Given restates one of the request's values of its kind is a reading (rule given-kinds)")
    elif "of the same dimension" in rel.reason:
        ctx.warn("that the Given restates one of the request's quantities of the same dimension is a reading")
    else:
        ctx.warn("symbol identity across the request and the answer is a reading")
    b = ctx.builder
    w_aw, w_num, w_unit, w_wrap = v
    w_si = si_value(w_aw, w_unit, w_wrap)
    # STEM repair 3 (rule given-digits): a Given restates its data as written, so every written digit of a whole number counts, on
    # both sides. Under R1's rule for a value set against a value no trailing zero counted, and 'Given: background = 30 counts
    # min⁻¹' held against the supplied 20 counts per minute (h 5 each, a band of 10)
    # STEM repair 8: a value the prose states for a quantity the request names by its words restates the request's data as written too ('the
    # background count rate of 25 counts min⁻¹' had held against the supplied 20 counts per minute, h 5 for the 20 and 1/2 for the 25)
    named_given = "rule named-given)" in (rel.reason or "") and not rel.exact_candidates
    # STEM repair 9 (rule named-result): the value the answer gives a quantity the request names, as a chain's final value, is compared as
    # rule named-given compares a value the prose states
    named_result = "rule named-result)" in (rel.reason or "") and not rel.exact_candidates
    # STEM repair 8: the value a line's working takes for data its line names (the condition, a listed value, the supplied table's or the
    # supplied texts' value) restates that data as written too ('in 10 s' against '× 20 s' had held, h 5 each)
    given = (rel.reason or "").startswith("the Given value") or "(rule processed-data)" in (rel.reason or "") or named_given or named_result \
        or r8 is not None
    h_w = w_num.half_width_for(_EVERY_DIGIT) if given else w_num.half_width
    if given and any(n.half_width_for(_EVERY_DIGIT) != n.half_width for n in [w_num] + [c.number for c in rel.candidates]):
        ctx.detail("a value the answer gives a quantity the request names restates the request's data as written: every written digit of a whole "
                   "number counts, its trailing zeros too (rule given-digits)" if named_result else
                   "a value the prose states for a quantity the request names restates the request's data as written: every written digit of a whole "
                   "number counts, its trailing zeros too (rule given-digits)" if named_given else
                   "the value the working takes stands for data its line names (its condition, a listed value, the supplied data), as written: every "
                   "written digit of a whole number counts, its trailing zeros too (rule given-digits)" if r8 is not None else
                   "a Given, or a value the working takes from the data, restates the data as written: every written digit of a whole number counts, "
                   "its trailing zeros too (rule given-digits)")
    f_w = abs(w_unit.readings[0].factor) if (w_unit is not None and w_unit.readings and w_unit.readings[0].factor is not None) else Fraction(1)
    if w_unit is None and w_wrap == "%":
        f_w = Fraction(1, 100)  # a per cent in SI is its hundredth, and so is its half-width (STEM repair 2: it was compared at 100 times)
    disjuncts: list[dict] = []
    exact_pairs: list[str] = []
    w_written = f"{w_num.text}{(' ' + w_unit.text) if w_unit else ''}"
    wname = b.declare("w", meaning=(f"{r8['w']} {w_written}" if r8 is not None else
                                    f"the value the answer gives {w_written}" if named_result else
                                    f"the {'stated' if rel.exact_candidates else 'Given'} value {w_written}"), role="pinned")
    frame = _frame([w_aw] + ([w_si] if w_si is not None else []) + [c.value for c in rel.candidates])
    # one pinned symbol in SI when every value has an SI reading, else as written
    use_si = w_si is not None and all(c.si is not None for c in rel.candidates)
    w_val = w_si if use_si else w_aw
    held = rel.left.node.name if rel.left and isinstance(rel.left.node, Sym) else "the symbol"  # type: ignore[union-attr]
    b.premise("W", {"op": "eq", "left": {"op": "var", "name": wname}, "right": literal_in_frame(w_val, frame)},
              (f"{r8['w']} ({w_written})" if r8 is not None else
               f"the value the answer gives the {rel.named}" if named_result else
               f"the uncertainty the line states" if "rule stated-uncertainty" in (rel.reason or "") else
               f"the value the prose gives for {held}" if rel.exact_candidates else f"the Given value of {held}"), grounding("figure"))
    for i, cand in enumerate(rel.candidates, 1):
        stated_rule = "rule stated-uncertainty" in (rel.reason or "")
        c_written = f"{cand.number.text}{(' ' + cand.unit.text) if cand.unit else ''}"
        cname = b.declare(f"b_{i}", meaning=(f"{r8['cand']} {c_written}" if r8 is not None else
                                            f"{cand.symbol}: the uncertainty the answer's stated rule gives" if stated_rule else
                                            f"the supplied table's {cand.number.text}{(' ' + cand.unit.text) if cand.unit else ''}" if rel.exact_candidates else
                                            f"the {'supplied text' if cand.source == 'supplied' else 'request'}'s {cand.number.text}"
                                            f"{(' ' + cand.unit.text) if cand.unit else ''}"), role="pinned")
        c_val = cand.si if use_si else cand.value
        f_c = abs(cand.unit.readings[0].factor) if (use_si and cand.unit is not None and cand.unit.readings and cand.unit.readings[0].factor is not None) else Fraction(1)
        if use_si and cand.unit is None and cand.wrapper == "%":
            f_c = Fraction(1, 100)
        h_c = cand.number.half_width_for(_EVERY_DIGIT) if given else cand.number.half_width
        # STEM repair 11 (rule given-data): the request's and the supplied texts' values are data, taken as written (R3): a value that restates
        # one matches it only when one of the two is the other rounded to its own last written digit, |w − b| ≤ max(h(w), h(b)) ('0.5 Ω' and
        # '0.500 Ω' restate 0.50 ohm). Before, R7 added the two half-widths, an inclusive band that held a Given one unit off in its last
        # written digit ('r = 0.49 Ω' for the request's 0.50 ohm, 'r = 3.5%' for its 3.6%, 'ε = 13 V' for its 12 V): two values that are only
        # roundings of a common third. A supplied table's cells stay exact (R9, |w − b| ≤ h(w)); a value the answer computes for a quantity the
        # request names (rule named-result) keeps R7's band: it carries its own rounding
        h_wf = h_w * (f_w if use_si else 1)
        tol = h_wf if rel.exact_candidates else (h_c * f_c + h_wf) if named_result else max(h_c * f_c, h_wf)
        if _exact_written(w_num, w_unit) and _exact_written(cand.number, cand.unit):
            tol = Fraction(0)  # exact work: a whole number with no unit against a whole number with no unit ('5000 euros' and '4000 euros')
            exact_pairs.append(cand.number.text)
        b.premise(f"B_{i}", {"op": "eq", "left": {"op": "var", "name": cname}, "right": literal_in_frame(c_val, frame)},
                  (f"{r8['states']} {c_written}" if r8 is not None else
                   f"{cand.symbol} is {cand.number.text}{(' ' + cand.unit.text) if cand.unit else ''} (the rule the answer states, on the supplied table's value)"
                   if stated_rule else
                   f"the supplied table gives {cand.number.text}{(' ' + cand.unit.text) if cand.unit else ''}" if rel.exact_candidates else
                   f"the {'supplied text' if cand.source == 'supplied' else 'request'} states {cand.number.text}{(' ' + cand.unit.text) if cand.unit else ''}"),
                  grounding("request"))
        disjuncts.append(band_expr({"op": "var", "name": wname}, {"op": "var", "name": cname}, literal_in_frame(tol, frame), Fraction(0)))
    ctx.readings = ["SI" if use_si else "as written"]
    if not rel.exact_candidates and not named_result:
        ctx.detail("the request's values are data, taken as written: the stated value matches one only when one of the two is the other rounded "
                   "to its own last written digit, |w − b| ≤ max(h(w), h(b)) (rule given-data)")
    if exact_pairs:
        ctx.detail("exact mode: the value and " + ", ".join(exact_pairs[:4]) + " are whole numbers with no unit (τ = 0, h = 0)")
    if named_result:
        how = ("by the symbol the answer substituted the request's value for" if "matched by the symbol" in (rel.reason or "") else
               "by its label" if "matched by its label" in (rel.reason or "") else "by its words")
        ctx.warn(f"the answer gives a value to the quantity ('{rel.named}') the request names; the request's value is matched to it {how} (rule "
                 "named-result), a reading the answer did not state")
    elif rel.named and not rel.exact_candidates:
        ctx.warn(f"the prose names the quantity ('{rel.named}'); the request's value is matched to it by those words (rule named-given), a reading "
                 "the answer did not state")
    if frame:
        b.note(f"decimal exponent factored: 10^{frame}")
    ctx.conclusion = ("MATCHES", nary("or", disjuncts) if len(disjuncts) > 1 else disjuncts[0],
                      r8["concl"] if r8 is not None else
                      "the stated value matches the supplied table's data (R7, the data exact)" if rel.exact_candidates else
                      "the value the answer gives matches the request's value of that quantity (R7)" if named_result else
                      "the Given value matches a value of the request (R7)")


def _exact_written(num: ExactNumber, unit: Optional[UnitExpr]) -> bool:
    """A whole number written with no point, no exponent form and no unit: exact as written (R1's exact work)."""
    return unit is None and num.exact and not num.has_point and not num.scientific and num.value.denominator == 1


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
        blist = ctx.doc.bindings.get(name, ())
        if not blist:
            raise EncodeError("ST-UNDEC-002", f"'{name}' has no stated value")
        domains[name] = _domain_from_bindings(name, blist)
    symbol_units = any(b.unit is not None for n in names for b in ctx.doc.bindings.get(n, ()))
    readings, unknown = _readings(nodes, symbol_units=symbol_units, doc=ctx.doc)
    if unknown:
        ctx.warn("a unit is not recognised (ST-UNIT-001); the comparison is checked as written only")
    op = _CMP_OPS.get(rel.op)
    if op is None:
        raise EncodeError("ST-UNDEC-001", f"the relation sign {rel.op!r}")
    b = ctx.builder
    alts: list[dict] = []
    uses_s = any(len(d.values_aw) > 1 for d in domains.values())
    idx = 0
    total = len(combos) * len(readings)
    for (lnode, rnode) in combos:
        for ri, rd in enumerate(readings):
            idx += 1
            tag = "" if ri == 0 else f"r{ri + 1}"
            try:
                env, hulls, needs = _install_domains(ctx, domains, rd, tag)
                enc = Encoder(b, rd, env=env, symbol_hulls=hulls, interval_symbols=needs, cache=ctx.cache)
                lt, rt = enc.term(lnode), enc.term(rnode)
            except EncodeError:
                if idx == total and not alts:
                    raise
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
    expr = nary("or", alts) if len(alts) > 1 else alts[0]
    ctx.detail("exact comparison (R6): no slack")
    if uses_s:
        ctx.form, ctx.query, ctx.expected = "S", "satisfiability", "SATISFIABLE"
        b.premise("ORDER", expr, "the stated order holds under some admissible reading", grounding("figure"))
    else:
        ctx.conclusion = ("STATED", expr, "the stated order holds")


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
    sym_side = rel.left.node if (rel.left is not None and rel.left.node is not num_side) else (rel.right.node if rel.right is not None else None)
    b = ctx.builder
    defined: dict[tuple[int, bool], tuple[str, int]] = {}
    checked: list[str] = []
    #: (symbol, the node written opposite it, its alternatives, {id(alternative): "matches a binding" expression})
    entries: list[tuple[str, Node, list[Node], dict[int, dict]]] = []
    changed: list[str] = []
    part_stated = dict(rel.part_stated)
    prior = dict(rel.prior_readings)
    mode = ctx.doc.profile.mode
    rescaled: set[str] = set()
    for name, node in rel.pairs:
        if not is_closed(node):
            continue
        # rule solved-law (STEM repair 7): a symbol with no binding is set against the values substituted for it before the line
        blist = tuple(x for x in ctx.doc.bindings.get(name, ())) + tuple(prior.get(name, ()))
        if not blist:
            continue
        later = _changes_before(ctx, name)
        if later:
            # rule changed-value (STEM repair 4): the value the prose gives the symbol at the end of a change it states before this
            # substitution ('the current … falls, from 4.1 A to 2.7 A') is one the substitution may take, as it takes a binding
            blist = blist + later
            changed.append(name)
        stated_here = part_stated.get(name, ())
        if stated_here:
            # rule part-value (STEM repair 5): a symbol whose every binding stands in another part may take a value its part states before
            # the line with its dimension ('The current in it is 9.93 V ÷ 6.0 Ω = 1.655 A.' before 'P = I²R = (1.655 A)² × 6.0 Ω')
            blist = blist + tuple(stated_here)
        if rel.part_given:
            # rule part-given (STEM repair 6): the values of its dimension the part's question states, which the symbol may stand for there
            blist = blist + tuple(b for b in rel.part_given if b.unit is not None and value_of(node) is not None and value_of(node)[2] is not None
                                  and b.unit.dim == value_of(node)[2].dim)
        alternatives = [node] + _non_coefficient_factors(node, groups.get(id(node), []), _written_coefficients(sym_side, name))
        per_alt: dict[int, dict] = {}
        for alt in alternatives:
            disj: list[dict] = []
            av = value_of(alt)
            h_w = av[1].half_width if (av is not None and av[1] is not None) else Fraction(0)
            w_unit = av[2] if av is not None else None
            for si in (False, True):
                key = (id(alt), si)
                if key not in defined:
                    try:
                        rd = Reading(si=si, label="SI" if si else "as written")
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
                    # STEM repair 11 (rule given-data): a value the request or a text supplied with it states, or the answer's Given restates,
                    # is data, taken as written (R3): the substituted numeral matches it only when one of the two is the other rounded to its own
                    # last written digit, |w − b| ≤ max(h(w), h(b)); R7's band h(b) + h(w) had held a value one unit off in its last written
                    # digit ('0.49 Ω' for the request's r = 0.50 Ω, '2.1 kg' for its m = 2.0 kg). The answer's other values keep R7 (a carried
                    # result is rounded, and two roundings of it may differ by a unit)
                    data = bd.source in ("request", "supplied", "given")
                    if si:
                        bval = bd.si if bd.unit is not None else bd.value
                        if bval is None:
                            continue
                        f_b = abs(bd.unit.readings[0].factor) if (bd.unit is not None and bd.unit.readings and bd.unit.readings[0].factor is not None) else Fraction(1)
                        tol = max(_match_h(bd, mode) * f_b, h_w * f_w) if data else _match_h(bd, mode) * f_b + h_w * f_w
                    else:
                        if w_unit is not None and (bd.unit is None or bd.unit.text != w_unit.text):
                            continue
                        bval = bd.value
                        tol = max(_match_h(bd, mode), h_w) if data else _match_h(bd, mode) + h_w
                    try:
                        disj.append(band_expr({"op": "var", "name": wname}, literal_in_frame(bval, k), literal_in_frame(tol, k), Fraction(0)))
                    except LiteralTooLong:
                        continue
            if w_unit is None and (id(alt), False) in defined:
                # stem-precision-2 (round 7): a bare substituted value may be the binding converted to another unit of its dimension that the
                # line's other values are written in ('V = 25.0 cm³' put in as 0.0250 beside 'c = 0.100 mol dm⁻³': V in dm³); before, it
                # was matched as written and in SI only, so the standard concentration step failed as an error
                wname, k = defined[(id(alt), False)]
                for bd in blist:
                    if bd.unit is None or bd.si is None or not bd.unit.readings or bd.unit.readings[0].factor is None:
                        continue
                    f_b = abs(bd.unit.readings[0].factor)
                    data = bd.source in ("request", "supplied", "given")
                    for f in _rescale_factors(ctx, bd, rel):
                        tol = max(_match_h(bd, mode) * f_b / f, h_w) if data else _match_h(bd, mode) * f_b / f + h_w
                        try:
                            disj.append(band_expr({"op": "var", "name": wname}, literal_in_frame(bd.si / f, k), literal_in_frame(tol, k), Fraction(0)))
                        except LiteralTooLong:
                            continue
                        rescaled.add(name)
            if disj:
                per_alt[id(alt)] = nary("or", disj) if len(disj) > 1 else disj[0]
        if per_alt:
            entries.append((name, node, alternatives, per_alt))
            checked.append(name)
    if not entries:
        raise EncodeError("ST-UNDEC-001", "no substituted value could be set against a binding")
    part_value = _part_value_expr(ctx, num_side) if rel.reused and rel.head_values else None
    if part_value is not None:
        # rule part-value (STEM repair 5): a symbol whose every binding stands in another part also matches when the line's numeric side
        # gives the value its part states for the quantity the chain computes (the line re-derives the part's own result)
        for name, _node, _alts, per_alt in entries:
            if name in rel.reused:
                for key in list(per_alt):
                    per_alt[key] = nary("or", [per_alt[key], part_value])
        if rel.head_symbol:
            shown = "; ".join(f"{rel.head_symbol} = {hb.number.text}{(' ' + hb.unit.text) if hb.unit else ''} ({hb.statement_id})" for hb in rel.head_values[:4])
            ctx.detail(f"rule part-value: {', '.join(rel.reused)} may be reused in this part for another quantity (every binding stands in another "
                       f"part), so its value also matches when the numeric side gives the value this part states for '{rel.head_symbol}': {shown}")
        else:
            shown = "; ".join(f"{hb.number.text}{(' ' + hb.unit.text) if hb.unit else ''} ({hb.statement_id})" for hb in rel.head_values[:4])
            ctx.detail(f"rule part-value: {', '.join(rel.reused)} may be reused in this part for another quantity (every binding stands in another "
                       f"part), so its value also matches when the numeric side gives a result this part states before the line with the numeric "
                       f"side's dimension: {shown}")
    stated_names = [n for n in checked if part_stated.get(n)]
    if stated_names:
        shown = "; ".join(f"{n} = " + ", ".join(f"{b.number.text}{(' ' + b.unit.text) if b.unit else ''} ({b.statement_id})" for b in part_stated[n][:4])
                          for n in stated_names)
        ctx.detail(f"rule part-value: {', '.join(stated_names)} may be reused in this part for another quantity (every binding stands in another "
                   f"part), so its value also matches a value this part states before the line with its dimension: {shown}")
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
    if prior:
        ctx.detail("rule solved-law: " + ", ".join(n for n in checked if n in prior) + " has no stated value; it is set against the values substituted "
                   "for it before this line, which the algebra step this evaluation replaces had pinned")
    ctx.detail("a value matches any binding of its symbol, as written or in SI; a factor written in another order matches too (R7)"
               + ("; each factor stands for one symbol only" if ordered else ""))
    if rescaled:
        ctx.detail("a bare value put in for " + ", ".join(sorted(rescaled)) + " also matches its binding converted to another unit of its dimension "
                   "that the line's other values are written in (dm³ beside mol dm⁻³)")
    if any(bd.source in ("request", "supplied", "given") for name in checked for bd in ctx.doc.bindings.get(name, ())):
        ctx.detail("the request's values and the Given values that restate them are data, taken as written: a value substituted for one matches "
                   "it only when one of the two is the other rounded to its own last written digit, |w − b| ≤ max(h(w), h(b)) (rule given-data)")
    changed = [n for n in changed if n in checked]
    if changed:
        ctx.detail("the value the prose gives " + ", ".join(f"'{n}'" for n in changed) + " at the end of a change it states before this substitution "
                   "matches too (rule changed-value)")
    if rel.part_given:
        asked = ", ".join(f"{b.number.text}{(' ' + b.unit.text) if b.unit else ''}" for b in rel.part_given[:4])
        ctx.detail(f"rule part-given: {', '.join(checked)} reused here for a value the request gives; its part's question states {asked}, which it "
                   "matches too")
        ctx.warn("the request's value a reused symbol stands for in this part is a reading (rule part-given)")
    if rel.formula is not None:
        ctx.detail(_formula_detail(rel.formula))
    ctx.readings = ["as written or SI per value"]
    ctx.conclusion = ("SUBSTITUTED", nary("and", conj) if len(conj) > 1 else conj[0], "every substituted value matches a binding of its symbol")


def _rescale_factors(ctx: _Ctx, bd: Binding, rel: Relation) -> list[Fraction]:
    """The SI factors of the units of ``bd``'s dimension formed from a unit atom another value of the relation is written in (a binding of
    another substituted symbol, or a value stated in the relation's own statements): 'dm⁻³' of 'mol dm⁻³' gives dm³ for a volume
    (stem-precision-2). The binding's own unit and SI are left out; at most four."""
    dim = bd.unit.dim if bd.unit is not None else None
    if dim is None or not any(dim.exps):
        return []
    own = bd.unit.readings[0].factor if bd.unit.readings else None
    pool: list[Binding] = []
    for name, _node in rel.pairs:
        pool.extend(ctx.doc.bindings.get(name, ()))
    sids = set(rel.statement_ids)
    for blist in ctx.doc.bindings.values():
        pool.extend(b for b in blist if b.statement_id in sids)
    out: list[Fraction] = []
    for b2 in pool:
        if b2.unit is None or b2.symbol == bd.symbol:
            continue
        for r in b2.unit.readings:
            for a in r.atoms:
                if a.unit is None or a.unit.factor is None or a.unit.affine:
                    continue
                base = UnitAtom(a.text, a.unit, a.prefix, 1).factor
                if base is None:
                    continue
                for e in (1, 2, 3, -1, -2, -3):
                    if a.unit.dim.power(e) == dim:
                        f = base ** e
                        if f not in (1, own) and f not in out:
                            out.append(f)
    return out[:4]


def _written_coefficients(sym_side: Optional[Node], name: str) -> list[Fraction]:
    """The values of the closed factors (or terms) the symbolic side writes beside ``name`` in its flattened product (or sum): the 4 of
    ``4x + 1``, the ½ of ``½mv²`` (stem-soundness-3, round 7)."""
    if sym_side is None:
        return []
    for n in walk(sym_side):
        if isinstance(n, BinOp) and n.op in "*+":
            items = _flatten_same(n, n.op)
            if not any(not is_closed(m) and name in symbols(m) and not isinstance(m, BinOp) for m in items):
                continue
            out = []
            for m in items:
                v = value_of(m) if is_closed(m) else None
                if v is not None and v[2] is None and not v[3]:
                    out.append(v[0])
            return out
    return []


def _non_coefficient_factors(node: Node, group: list[Node], coefficients: list[Fraction]) -> list[Node]:
    """The other closed factors of ``node``'s product (or terms of its sum) that a symbol written in another order may stand opposite,
    without the numerals that write the symbolic side's own coefficients (stem-soundness-3, round 7: in 'y = 4x + 1 = 4 × 9 + 1' with
    x = 4 the 4 is the formula's coefficient, so x stands for 9 only; before, x matched the written 4 and the wrong substitution held).
    One numeral per coefficient is removed, never ``node`` itself."""
    others = [m for m in group if m is not node]
    for c in coefficients:
        for k, m in enumerate(others):
            v = value_of(m)
            if v is not None and v[2] is None and not v[3] and v[0] == c:
                del others[k]
                break
    return others


def _part_value_expr(ctx: _Ctx, num_side: Node) -> Optional[dict]:
    """Rule ``part-value`` (STEM repair 5): the numeric side of the substitution, read in SI, lies in the band of one of the values its part
    states for the quantity the chain computes (``rel.head_values``): ``|N − H| ≤ h(H) + τ·|N|``, τ that of written arithmetic (1/100, or
    1/20 after an approximate cue). The value N is pinned to the numeric side's own term, so the engine decides it; None when the side
    cannot be encoded."""
    rel = ctx.rel
    b = ctx.builder
    try:
        t = Encoder(b, Reading(si=True, label="SI"), cache=ctx.cache).term(num_side)
    except EncodeError:
        return None
    k = t.k
    tau = TAU_APPROX if _approx(ctx) else TAU_EQUAL
    disj: list[dict] = []
    vname = ""
    for hb in rel.head_values:
        value = hb.si if hb.unit is not None else hb.value
        if value is None:
            continue
        f_b = abs(hb.unit.readings[0].factor) if (hb.unit is not None and hb.unit.readings and hb.unit.readings[0].factor is not None) else Fraction(1)
        try:
            lit_v, lit_h = literal_in_frame(value, k), literal_in_frame(_match_h(hb, ctx.doc.profile.mode) * f_b, k)
        except LiteralTooLong:
            continue
        if not vname:
            vname = b.fresh("n", meaning=f"the numeric side '{render(num_side)[:120]}' in SI (rule part-value)", role="pinned")
            b.premise(f"N_{vname}", {"op": "eq", "left": {"op": "var", "name": vname}, "right": to_frame(t, k)},
                      f"{vname} is the numeric side {render(num_side)[:200]} in SI", grounding("figure"))
        disj.append(band_expr({"op": "var", "name": vname}, lit_v, lit_h, tau))
    if not disj:
        return None
    return nary("or", disj) if len(disj) > 1 else disj[0]


def _changes_before(ctx: _Ctx, name: str) -> tuple[Binding, ...]:
    """Rule ``changed-value`` (STEM repair 4): the values the prose gives ``name`` at the end of a change it states that the relation
    being checked may take: one written before it, in its own statement ('V = 12 V − 2.7 A × 0.50 Ω = 10.65 V, because the current
    falls, from 4.1 A to 2.7 A'), or anywhere in its own part (the change belongs to that part's situation). A substitution in an
    earlier part never takes a value the prose gives in a later one ('V = 12 V − 2.7 A × 0.50 Ω' in part (c) still fails)."""
    changes = getattr(ctx.doc, "changes", None) or {}
    rel = ctx.rel
    out = []
    for b in changes.get(name, ()):
        st = ctx.doc.statement(b.statement_id)
        same_part = bool(rel.part) and st is not None and st.part == rel.part
        if b.end <= rel.start or b.statement_id in rel.statement_ids or same_part:
            out.append(b)
    return tuple(out)


def _formula_detail(formula) -> str:
    """The statement of the formula a substitution is read against: a formula the answer states, or (rule solved-law, STEM repair 7) the
    law the line evaluates, solved for its symbol by exact inverse operations ('ε = I(R + r)' solved for I is ε/(R + r))."""
    if formula.source == "solved":
        return (f"the line evaluates the law stated in {formula.statement_id} solved for '{formula.name}': {formula.name} = {render(formula.expr)[:160]} "
                "(rule solved-law; never an algebra step from the law)")
    return f"the formula of '{formula.name}' stated in {formula.statement_id}"


def _match_h(bd: Binding, mode: str = "") -> Fraction:
    """The half-width a binding's value matches with (R7). An exact integer or fraction stated with no unit in Mathematics or Computer
    Science ('Let x = 3') is that number and nothing near it: h = 0, so a substituted 4 no longer matches it (stem-soundness-2, round 7;
    before, an integer kept half a unit, and with the substituted integer's own half a unit the next integer matched). A computed
    result keeps its half unit: it may be a rounding."""
    exact = bd.unit is None and not bd.number.has_point and not bd.number.scientific and bd.source != "request"
    if exact and (bd.number.vulgar or (mode in ("mathematics", "computer_science") and bd.wrapper != "%" and bd.source != "result")):
        return Fraction(0)
    return bd.number.half_width


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
    for name in names:
        blist = ctx.doc.bindings.get(name, ())
        if blist:
            later = _changes_before(ctx, name)
            if later:
                ctx.detail(f"the value the prose gives '{name}' at the end of a change it states before this substitution is one of its values too "
                           "(rule changed-value)")
            domains[name] = _domain_from_bindings(name, tuple(blist) + later)
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
    symbol_units = any(bd.unit is not None for n in names for bd in ctx.doc.bindings.get(n, ())) or bool(booklet_used)
    # stem-precision-3 (round 7): a symbol bound in a unit whose SI factor is not 1 ('t = 4.5 min') makes the SI reading differ even when
    # the written sides carry no unit ('Pt = 2200 × 4.5 × 60', the conversion factor written out); before, only the reading as written was
    # offered, so correct working failed
    symbol_factors = any(bd.unit is not None and any(r.factor is None or r.factor != 1 or r.affine is not None for r in bd.unit.readings)
                         for n in names for bd in ctx.doc.bindings.get(n, ()))
    nodes = [n for p in pairs for n in p]
    approx = _approx(ctx)
    exact_mode = rel.op in ("=", "≡") and not approx and all(_all_exact(n) for n in nodes) and all(
        not d.is_interval and not d.booklet for d in domains.values()) and not symbol_units
    tau = Fraction(0) if exact_mode else (TAU_APPROX if approx else TAU_EQUAL)
    readings, unknown = _readings(nodes, symbol_units=symbol_units, doc=ctx.doc, symbol_factors=symbol_factors)
    if unknown:
        ctx.warn("a unit is not recognised (ST-UNIT-001); the relation is checked as written only")
    # STEM repair 11 (rule exact-rounding): a stated value of two or more significant figures against a rational symbolic side under exact
    # bindings is stated to its last written digit, as in written arithmetic (a whole value exactly, one that is not whole at the nearest whole
    # number); a one-figure value keeps h = 0
    hs = [(_value_half_width(num, min_sf=_EVERY_DIGIT) if (exact_mode and _rational_form(sym) and _written_figures(num) >= 2)
           else _value_half_width(num, exact_mode=exact_mode)) if is_value(num) else Fraction(0) for num, sym in pairs]

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
    if rel.formula is not None and rel.formula.source == "solved":
        ctx.detail(_formula_detail(rel.formula))
    if rel.prose_head:
        # rule bound-relation (STEM repair 5): a run the prose gives as the value of a quantity it names, read as a chain headed by it
        ctx.detail(f"the prose gives the run as the value of the {rel.prose_head[:60]}"
                   + (" and every symbol has a stated value" if not rel.unbound else "") + ": no equation in an unknown (rule bound-relation)")
    ctx.detail("the symbolic side under the stated bindings" + (" (and readings from the written substitution)" if anchors else "") + f"; τ = {_ratio(tau)}")
    signs = (1, -1) if _has_plus_minus(*nodes) else (1,)
    _compare(ctx, pairs, kind="sub", tau=tau, h_written=hs, readings=readings, intervals={}, env_for=env_for, signs=signs, force_form_s=many,
             label="written numeric side", stated_label="symbolic side under the bindings")


# --------------------------------------------------------------------------- alg and inequality steps


def _side_value_node(node: Node) -> Optional[Node]:
    return node if is_value(node) else None


def _reading_notes(ctx: _Ctx, rules: tuple[str, ...]) -> None:
    """STEM repair 11: the clauses of the relation's reason that name one of ``rules`` (rules root-statement and part-condition: the
    reading that made the relation a step, or its letter an unknown, of its part), stated in the check's detail."""
    for seg in (ctx.rel.reason or "").split("; "):
        if any(f"(rule {r})" in seg for r in rules):
            ctx.detail(seg)


def _step(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.premise_left is None or rel.premise_right is None:
        raise EncodeError("ST-UNDEC-001", "a step without a preceding relation")
    if "(rule definite-integral)" in (rel.reason or ""):
        # STEM repair 10 (rule definite-integral): the antiderivative check of a definite integral states what it compares
        ctx.detail(f"compared: {rel.reason}")
    _reading_notes(ctx, ("root-statement", "part-condition"))
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
    # rule identity-variable (STEM repair 12): an identity from the trivially true premise (a derivative, an antiderivative, a Given
    # function against the request's, a factorisation) is stated for every value of its own variables, so they take no binding and no
    # formula, and the identity connects them. Before, the variable of 'd/dt (6 − 6t) = −6t' (the formed side −6 has none) took the
    # request's 't = 1' as a substituted value, so the identity was decided at that value only: −6 = −6(1), ENTAILED
    quantified = set(rel.identity)
    reading = Reading(si=False, label="as written")
    # the value of a symbol that appears on one side only (a value the step substitutes): one value, pinned, so the
    # entailment is never asked to hold for every value the symbol takes elsewhere in the answer
    bound: dict[str, SymbolDomain] = {}
    written = {abs(v[0]) for side in (cl0, cr0) for leaf in _leaves(side) if (v := value_of(leaf)) is not None}
    for name in sorted(diff - quantified):
        bd = _step_binding(ctx, name, written)
        if bd is not None:
            dom = SymbolDomain(name)
            dom.add(bd.value, bd.value, None, grounding("request") if bd.source == "request" else grounding("figure", f"value of '{name}' stated in {bd.statement_id}"),
                    f"{name} = {bd.number.text} ({bd.source}, {bd.statement_id})")
            bound[name] = dom
    # formulas of symbols on one side only
    formulas: list[tuple[str, Node, str]] = []
    for name in sorted(diff - quantified):
        if name in bound:
            continue
        for f in ctx.doc.formulas.get(name, ())[-2:]:
            if len(formulas) >= ctx.doc.limits.max_formulas_per_step:
                break
            if any(n.endswith("()") for n in symbols(f.expr)):
                continue
            formulas.append((name, f.expr, f.statement_id))
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
    connected = set(prem_syms) | set(bound) | quantified
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
    if quantified & diff:
        ctx.detail("an identity, stated for every value of " + ", ".join(sorted(quantified & diff)) + ": no binding or formula of it is included, "
                   "so it is decided for every value (rule identity-variable)")
    if "rule rearranged-formula" in (rel.reason or ""):
        # STEM repair 5: a rearrangement of the formula before it, which the line after it evaluates: checked as a step from the formula
        ctx.detail("a rearrangement of the formula, which the next line evaluates (rule rearranged-formula)")
    if "(rule derivative" in (rel.reason or ""):
        # STEM repair 11 (rule derivative): the derivative the STEM pack forms by the power rule against the derivative the line states
        ctx.detail(f"compared: {rel.reason}; from the trivially true premise, so it holds exactly when the two expressions agree for every value "
                   "of the variable")
        if "(rule derivative, the request's function)" in (rel.reason or ""):
            ctx.warn("that the letter differentiated is the request's function of that name is a reading (rule derivative)")
    if "(rule antiderivative)" in (rel.reason or ""):
        # STEM repair 12: an antiderivative's check states what it compares, as a derivative's does, its variable named (rule identity-statement
        # reads it there); before, its detail said only "the algebraic step"
        ctx.detail(f"compared: {rel.reason}; from the trivially true premise, so it holds exactly when the two expressions agree for every value "
                   "of the variable")
    if "(rule given-function)" in (rel.reason or ""):
        # STEM repair 9: a Given function against the request's function of that name, for every value of its variable
        ctx.detail(f"compared: {rel.reason}; from the trivially true premise, so it holds exactly when the two expressions agree for every value "
                   "of the variable")
        ctx.warn("that the Given restates the request's function is a reading (rule given-function)")
    unrelated = sorted(conc_syms - connected)
    if unrelated:
        ctx.warn("the step brings in symbols that no premise, binding or included formula connects (" + ", ".join(unrelated) + ")")
    ctx.readings = ["as written"]
    ctx.conclusion = ("STEP", nary("or", conc_alts) if len(conc_alts) > 1 else conc_alts[0], "the next relation follows from the preceding one")


def _step_binding(ctx: _Ctx, name: str, written: set[Fraction]) -> Optional[Binding]:
    """The one value of ``name`` a step uses: a binding (or, failing that, a substitution reading) whose
    value the step writes, else the latest stated before the step."""
    blist = [b for b in ctx.doc.bindings.get(name, ()) if b.source != "root"] or list(ctx.doc.substitutions.get(name, ()))
    if not blist:
        return None
    hits = [b for b in blist if abs(b.value) in written]
    pool = hits or blist
    before = [b for b in pool if b.end <= ctx.rel.start]
    return (before or pool)[-1]


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
    # stem-soundness-10 (round 7): a rounded value written with '±' ('x = ±1.41') is a rounded value of each sign: its band applies to both
    # branches (with h = 0 the + branch read 1.41 as exact, so x² = 2 ⇒ x = ±1.41 failed on correct work)
    unsigned = lambda n: n.right if isinstance(n, PlusMinus) and n.left is None else n  # noqa: E731
    value_side = cr if is_value(unsigned(cr)) else (cl if is_value(unsigned(cl)) else None)
    h = Fraction(0)
    if value_side is not None:
        v = value_of(unsigned(value_side))
        if v is not None and v[1] is not None and (v[1].has_point or v[1].scientific):
            h = v[1].half_width
    approx = ctx.rel.approx
    if cop == "eq" and (h > 0 or approx):
        tau = TAU_APPROX if approx else TAU_EQUAL
        ctx.detail("a rounded value in the step: compared within its band (R4)")
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


def _root_is_exact(node: Node) -> bool:
    if not _all_exact(node):
        return False
    return not any(isinstance(n, Func) or _irrational_power(n) or (isinstance(n, Sym) and n.kind == "constant") for n in walk(node))


def _irrational_power(node: Node) -> bool:
    """A ``RealPower`` the encoder writes as an enclosure: an irrational value (``10^0.4``, ``2^(−3.5)``), or an integer
    power beyond the integer-power bound whose exact value is too long for a literal (``(1 + 0.065/12)^(−60)``). Only a
    tolerance band can compare such a value with a written figure (``16^(3/4)`` is exactly 8 and ``2^20`` exactly 1048576:
    neither is such a power)."""
    return isinstance(node, RealPower) and real_power_value(node) is None


def _sol_system(ctx: _Ctx) -> None:
    """stem-soundness-5 (round 7): the stated solution of simultaneous equations against every equation of the system together. Each
    stated value is its exact value (an exact root) or ranges over its rounding interval (R10); an unknown the answer states no value for
    is free, and a parameter takes its stated values outside the solution's own statements (never a value of the same conclusion). Exact
    values: Form E, every equation holds at them; otherwise Form S, some point of the values' intervals satisfies every equation."""
    rel = ctx.rel
    values = dict(rel.simultaneous_values)
    eqs: list[tuple[Node, Node]] = []
    for lop, rop in rel.simultaneous:
        if lop.node is None or rop.node is None:
            raise EncodeError("ST-PARSE-001", "an equation of the system could not be read")
        eqs.append((lop.node, rop.node))
    names = sorted(set().union(*(set(symbols(a)) | set(symbols(c)) for a, c in eqs)))
    if any(n.endswith("()") for n in names):
        raise EncodeError("ST-UNDEC-001", "a function of an unknown")
    b = ctx.builder
    reading = Reading(si=False, label="as written")
    solution_sids = set(rel.statement_ids) - set(rel.premise_ids)
    env: dict[str, Term] = {}
    hulls: dict[str, Interval] = {}
    exact = True
    free: list[str] = []
    for name in names:
        if name in values:
            node = values[name]
            enc = Encoder(b, reading, cache={})
            if _root_is_exact(node):
                t = enc.term(node)
                var = b.user_symbol(name, role="pinned", meaning=f"'{name}' at the stated solution {render(node)[:80]}")
                b.premise(f"V_{var}", {"op": "eq", "left": {"op": "var", "name": var}, "right": to_frame(t, 0)},
                          f"the stated value {name} = {render(node)[:120]}", grounding("figure"))
                iv = enc.interval(node)
            else:
                lo, hi = _root_interval(ctx, node, reading, {})
                var = b.user_symbol(name, role="interval", meaning=f"'{name}' within the rounding interval of the stated {render(node)[:80]} (R10)")
                b.premise(f"V_LO_{var}", {"op": "ge", "left": {"op": "var", "name": var}, "right": real(lo)}, f"the stated value {name} = {render(node)[:120]}",
                          grounding("figure"))
                b.premise(f"V_HI_{var}", {"op": "le", "left": {"op": "var", "name": var}, "right": real(hi)}, f"the stated value {name} = {render(node)[:120]}",
                          grounding("figure"))
                iv = Interval(lo, hi)
                exact = False
            env[name] = var_term(var)
            hulls[name] = iv
            continue
        blist = tuple(x for x in ctx.doc.bindings.get(name, ()) if x.statement_id not in solution_sids)
        if blist:
            dom = _domain_from_bindings(name, blist)
            denv, dhulls, needs = _install_domains(ctx, {name: dom}, reading, "")
            env.update(denv)
            hulls.update(dhulls)
            exact = exact and not needs
            continue
        var = b.user_symbol(name, role="aux", meaning=f"the unknown '{name}' of the system, for which the answer states no value")
        env[name] = var_term(var)
        free.append(name)
        exact = False
    conj: list[dict] = []
    for i, (lt_node, rt_node) in enumerate(eqs, 1):
        enc = Encoder(b, reading, env=env, symbol_hulls=hulls, cache={})
        lt, rtt = enc.term(lt_node), enc.term(rt_node)
        (le, re_), _k = align_terms(lt, rtt)
        conj.append({"op": "eq", "left": le, "right": re_})
        if not exact:
            b.premise(f"EQ_{i}", {"op": "eq", "left": le, "right": re_}, f"the equation {render(lt_node)[:160]} = {render(rt_node)[:160]} of the system",
                      grounding("figure", f"the equations stated in {', '.join(rel.premise_ids)}"))
    shown = ", ".join(f"{n} = {render(v)[:40]}" for n, v in rel.simultaneous_values)
    ctx.readings = ["as written"]
    ctx.detail(f"the stated solution ({shown}) set against every equation of the system ({len(eqs)} equations), never one equation with another "
               "stated value as a premise")
    if free:
        ctx.detail("no value is stated for " + ", ".join(free) + ": it ranges over every value")
    if exact:
        ctx.detail("exact values: every equation of the system must hold at them")
        ctx.conclusion = ("SOLUTION", nary("and", conj) if len(conj) > 1 else conj[0], "the stated values satisfy every equation of the system")
        return
    ctx.form, ctx.query, ctx.expected = "S", "satisfiability", "SATISFIABLE"
    ctx.detail("membership: some point of the stated values' rounding intervals (R10) satisfies every equation of the system")


def _sol(ctx: _Ctx) -> None:
    rel = ctx.rel
    if rel.simultaneous:
        _sol_system(ctx)
        return
    if rel.premise_left is None or rel.premise_right is None or not rel.roots:
        raise EncodeError("ST-UNDEC-001", "stated roots without an equation")
    eq_l, eq_r = rel.premise_left.node, rel.premise_right.node
    if eq_l is None or eq_r is None:
        raise EncodeError("ST-PARSE-001", "the equation could not be read")
    x = rel.root_symbol
    _reading_notes(ctx, ("part-condition",))
    roots = _expand_roots(rel.roots)
    others = sorted((set(symbols(eq_l)) | set(symbols(eq_r))) - {x})
    if any(n.endswith("()") for n in others):
        raise EncodeError("ST-UNDEC-001", "a function of an unknown")
    domains: dict[str, SymbolDomain] = {}
    for name in others:
        blist = ctx.doc.bindings.get(name, ())
        if not blist:
            raise EncodeError("ST-UNDEC-002", f"'{name}' in the equation has no stated value")
        domains[name] = _domain_from_bindings(name, blist)
    params_exact = all(not d.is_interval and len(d.values_aw) == 1 for d in domains.values())
    exact_roots = [_root_is_exact(r) and not rel.described for r in roots]
    b = ctx.builder
    reading = Reading(si=False, label="as written")
    env, hulls, needs = _install_domains(ctx, domains, reading, "") if domains else ({}, {}, frozenset())
    eq_ground = grounding("request") if rel.premise_ids == ("request",) else grounding("figure", f"the equation stated in {', '.join(rel.premise_ids)}")
    complete = rel.complete and not rel.restricted and params_exact
    ctx.readings = ["as written"]
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
            enc = Encoder(b, reading, env=env_i, symbol_hulls=hulls, cache={})
            lt, rtt = enc.term(eq_l), enc.term(eq_r)
            (le, re_), _k = align_terms(lt, rtt)
            ln = b.declare(f"l_{i}", meaning=f"the left side of the equation at {x} = {render(root)[:120]}", role="aux")
            rn = b.declare(f"r_{i}", meaning=f"the right side of the equation at {x} = {render(root)[:120]}", role="aux")
            b.premise(f"L_DEF_{i}", {"op": "eq", "left": {"op": "var", "name": ln}, "right": le}, f"{ln}: the equation's left side at the stated root", grounding("device"))
            b.premise(f"R_DEF_{i}", {"op": "eq", "left": {"op": "var", "name": rn}, "right": re_}, f"{rn}: the equation's right side at the stated root", grounding("device"))
            conj.append({"op": "eq", "left": {"op": "var", "name": ln}, "right": {"op": "var", "name": rn}})
        ctx.detail("membership: each exact root substituted into the equation (exact)")
        if complete:
            xv = b.user_symbol(x, role="free", meaning=f"the unknown '{x}' of the equation")
            env_x = dict(env)
            env_x[x] = var_term(xv)
            enc = Encoder(b, reading, env=env_x, symbol_hulls=hulls, cache={})
            lt, rtt = enc.term(eq_l), enc.term(eq_r)
            (le, re_), _k = align_terms(lt, rtt)
            b.premise("EQ", {"op": "eq", "left": le, "right": re_}, f"the equation {render(eq_l)[:200]} = {render(eq_r)[:200]}", eq_ground)
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
        enc = Encoder(b, reading, env=env_x, symbol_hulls=hulls, cache=ctx.cache)
        lt, rtt = enc.term(eq_l), enc.term(eq_r)
        (le, re_), _k = align_terms(lt, rtt)
        b.premise("EQ", {"op": "eq", "left": le, "right": re_}, f"the equation {render(eq_l)[:200]} = {render(eq_r)[:200]}", eq_ground)
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
        enc = Encoder(b, reading, env=env_i, symbol_hulls=hulls, interval_symbols=needs, cache={})
        lt, rtt = enc.term(eq_l), enc.term(eq_r)
        (le, re_), _k = align_terms(lt, rtt)
        b.premise(f"EQ_{i}", {"op": "eq", "left": le, "right": re_}, f"the equation holds at the stated root {render(root)[:200]}", eq_ground)
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
    b = ctx.builder
    values = dict(ctx.rel.assignment)
    for name, val in sorted(values.items()):
        # rule boolean-values (STEM repair 4): each value the statement gives an input is a premise, so the relation is decided under
        # those values ('With A = 1 and B = 0, NOT A OR B = 0'), never as an identity over every assignment
        v = b.user_symbol(name, sort="Bool", role="pinned", meaning=f"the Boolean input '{name}', given the value {int(val)} by its statement")
        b.premise(f"VAL_{v}", {"op": "var", "name": v} if val else {"op": "not", "arg": {"op": "var", "name": v}},
                  f"the statement gives '{name}' the value {int(val)}", grounding("figure", f"the value the statement gives '{name}'"))
    lhs, rhs = _bool_expr(ctx, br.left), _bool_expr(ctx, br.right)
    free = sorted((set(symbols(br.left)) | set(symbols(br.right))) - set(values))
    b.premise("NEG", {"op": "not", "arg": {"op": "iff", "left": lhs, "right": rhs}},
              "the two sides differ for some assignment" + (" of the inputs given no value, under the values the statement gives" if values else ""),
              grounding("figure"))
    ctx.form, ctx.query, ctx.expected = "B", "satisfiability", "UNSATISFIABLE"
    ctx.readings = ["Boolean"]
    if values:
        ctx.detail("evaluated under the values the statement gives its inputs: " + ", ".join(f"{n} = {int(v)}" for n, v in sorted(values.items()))
                   + (f"; {', '.join(free)} given no value, so the relation must hold for each of {'their' if len(free) > 1 else 'its'} values" if free else "")
                   + " (rule boolean-values)")
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
    if rel.title:
        # rule prose-base (STEM repair 10): a whole number the prose restates right after it in another base ('110010₂ is 50 in denary')
        ctx.detail(f"compared: {rel.reason}")
    combos = _operand_combos(rel.left, rel.right)
    lnode, rnode = combos[0]
    li, ri = _int_expr(lnode), _int_expr(rnode)
    b = ctx.builder
    alt = getattr(rel, "alternative", ()) or ()
    li2, ri2 = (_int_expr(alt[0]), _int_expr(alt[1])) if alt else (None, None)
    if li is not None and ri is not None and alt and li2 is not None and ri2 is not None:
        # rule prose-base (STEM repair 10): '10 in binary is 1010' read both ways (the first numeral in the base named after it, or the
        # second written in it): the conversion holds when either reading does
        b.declare("c", sort="Int", meaning=f"the value of {render(lnode)[:200]} (first reading)", role="pinned")
        b.declare("r", sort="Int", meaning=f"the value of {render(rnode)[:200]} (first reading)", role="pinned")
        b.declare("c2", sort="Int", meaning=f"the value of {render(alt[0])[:200]} (second reading)", role="pinned")
        b.declare("r2", sort="Int", meaning=f"the value of {render(alt[1])[:200]} (second reading)", role="pinned")
        for name, node, expr in (("C_DEF", lnode, li), ("R", rnode, ri), ("C2_DEF", alt[0], li2), ("R2", alt[1], ri2)):
            b.premise(name, {"op": "eq", "left": {"op": "var", "name": name.split("_")[0].lower()}, "right": expr},
                      f"{name.split('_')[0].lower()} is {render(node)[:300]}", grounding("figure"))
        ctx.readings = ["exact integers, the first numeral in the named base", "exact integers, the second numeral in the named base"]
        ctx.detail("either reading of the base the prose names right after the first numeral: the first numeral's own, or the base the "
                   "second writes the first in")
        ctx.conclusion = ("STATED", nary("or", [{"op": "eq", "left": {"op": "var", "name": "c"}, "right": {"op": "var", "name": "r"}},
                                                 {"op": "eq", "left": {"op": "var", "name": "c2"}, "right": {"op": "var", "name": "r2"}}]),
                          "the two numerals are equal under one of the two readings")
        return
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


_BUILDERS = {
    "eq": _eq, "cnv": _cnv, "res": _res, "tgt": _tgt, "giv": _giv, "cmp": _cmp, "sub": _sub, "alg": _step, "sol": _sol, "chem": _chem, "bool": _bool,
    "tt": _tt, "base": _base, "mod": _mod,
}
