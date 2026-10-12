"""``StemDocument``: the one reading of a STEM answer that every reader shares (principle P1).

:func:`build_document` runs the front end once per (answer text, request text, profile):

    reading view ─► name pre-pass ─► spans ─► statements ─► lexer ─► parser ─► ASTs
    ─► scope (request bindings first) ─► relations ─► planned checks (stable ids, claim ids)

The STEM parser (claims), ``StemPack`` (checks) and ``CorePack`` in SI reading all read the
same document, so claim ids, sentence numbers and check ids cannot diverge. Documents are
memoised in an LRU cache of ``document_cache_entries`` (64); the key is the exact text, the
exact request text (or none) and the profile, and ``StemDocument.key`` records it as
``(sha256(text), sha256(request) or "", profile)``.

The original text is never altered: every statement, span and relation carries offsets
into it. Nothing here evaluates text; every bound of :class:`~epinoic_logic.stem.limits.StemLimits`
holds, and :func:`build_document` never raises on agent text (an internal failure becomes an
ST-INTERNAL-001 finding on an otherwise empty document).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from functools import lru_cache
from types import MappingProxyType
from typing import Mapping, Optional

from .boolean import is_boolean_context, parse_boolean, parse_truth_table
from .chem import latex_to_chem, parse_equation
from .lexer import Token, lex
from .limits import DEFAULT_LIMITS, StemLimits, StemProfile, profile_for
from .nodes import Neg, Num, Percent, Sym, is_value, value_of
from .normalize import reading_view
from .numbers import scan_number
from .parser import ParseContext, parse_math
from .relations import FrontEndFinding, MathItem, ProseValue, Relation, RequestReading, ShowThatTarget, ST_SEVERITY, plan_relations
from .scope import Binding, Formula, Scope, prescan_names
from .segment import Segmentation, Statement, segment_statements
from .spans import Span, SpanSet, find_spans

__all__ = ["StemDocument", "build_document", "clear_document_cache", "document_cache_info"]

_GIVEN_HEADS = ("given", "data", "known", "we know")
_LET_WORDS = frozenset({"taking", "take", "let", "using", "use", "with", "assume", "assuming", "where"})
#: a value after these words in an answer is an evaluation point ('At x = 1:'), not a binding of the symbol
_CONDITION_WORDS = frozenset({"at", "when", "if", "whenever"})
_RESTRICT = ("positive", "x > 0", "x ≥ 0", "non-negative", "nonnegative", "length", "time", "> 0", "≥ 0")


@dataclass(frozen=True)
class StemDocument:
    """The shared reading of one answer. See the module docstring.

    * ``statements``: in document order (``s<paragraph>.<n>``; ``s.tail`` when merged);
    * ``spans``: every extracted span; ``items``: every read math span or display row, its
      chains (ASTs, one or two readings per operand), chemistry, Boolean relations and tables;
    * ``bindings``/``formulas``: the final scope (request bindings included);
    * ``relations``: every recognised relation with its outcome; :attr:`checks` are the planned
      checks (stable ids, claim ids) within the per-report cap;
    * ``findings``: front-end findings (ST-*), none of error severity;
    * ``request``: what the request states (bindings, quantities, relations, show-that targets).
    """

    text: str
    request_text: str
    profile: StemProfile
    key: tuple[str, str, str]
    reading: str
    prose: str
    spans: SpanSet
    statements: tuple[Statement, ...]
    paragraphs: tuple[tuple[int, int], ...]
    items: tuple[MathItem, ...]
    relations: tuple[Relation, ...]
    findings: tuple[FrontEndFinding, ...]
    bindings: Mapping[str, tuple[Binding, ...]]
    formulas: Mapping[str, tuple[Formula, ...]]
    #: values the answer substituted into symbols it binds nowhere else (readings, never premises of their own check)
    substitutions: Mapping[str, tuple[Binding, ...]]
    names: frozenset[str]
    request: RequestReading
    prose_values: tuple[ProseValue, ...]
    overflow: int = 0
    limits: StemLimits = DEFAULT_LIMITS
    _by_id: Mapping[str, Statement] = field(default_factory=dict, repr=False, compare=False)

    @property
    def checks(self) -> tuple[Relation, ...]:
        """Planned checks within the per-report cap, in id order of planning (document order)."""
        return tuple(sorted((r for r in self.relations if r.outcome == "check" and not r.capped), key=lambda r: (r.start, r.end, r.index)))

    @property
    def unchecked(self) -> tuple[Relation, ...]:
        """Planned checks beyond the cap (named by ST-LIM-002)."""
        return tuple(r for r in self.relations if r.outcome == "check" and r.capped)

    def statement(self, sid: str) -> Optional[Statement]:
        return self._by_id.get(sid)

    def statement_text(self, sid: str) -> str:
        st = self._by_id.get(sid)
        return "" if st is None else self.text[st.start:st.end]

    def check(self, check_id: str) -> Optional[Relation]:
        for r in self.relations:
            if r.check_id == check_id:
                return r
        return None

    def checks_for(self, sid: str) -> tuple[Relation, ...]:
        return tuple(r for r in self.checks if sid in r.statement_ids)

    def relations_for(self, sid: str) -> tuple[Relation, ...]:
        return tuple(r for r in self.relations if sid in r.statement_ids)

    def findings_for(self, sid: str) -> tuple[FrontEndFinding, ...]:
        return tuple(f for f in self.findings if sid in f.statement_ids)

    def items_for(self, sid: str) -> tuple[MathItem, ...]:
        return tuple(it for it in self.items if it.statement_id == sid)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


def build_document(text: str, request_text: Optional[str] = None, profile: "str | StemProfile" = "physics", *,
                   limits: StemLimits = DEFAULT_LIMITS) -> StemDocument:
    """The memoised :class:`StemDocument` of ``text`` (and the request it answers) under a
    STEM profile key (``physics``, ``chemistry``, ``mathematics_aa``, ``computer_science``, ...).
    Repeated calls with the same arguments return the same object."""
    prof = profile_for(profile)
    return _cached(text, request_text or "", prof, limits)


@lru_cache(maxsize=DEFAULT_LIMITS.document_cache_entries)
def _cached(text: str, request_text: str, profile: StemProfile, limits: StemLimits) -> StemDocument:
    try:
        return _build(text, request_text, profile, limits)
    except Exception as exc:  # defensive: the front end must never raise on agent text
        return _empty(text, request_text, profile, limits, f"the STEM front end failed internally ({type(exc).__name__}); its relations are missing")


def clear_document_cache() -> None:
    _cached.cache_clear()


def document_cache_info():
    return _cached.cache_info()


def _with_values(tokens: tuple[Token, ...], reading: str, text: str, profile: StemProfile, limits: StemLimits) -> tuple[Token, ...]:
    """The synthetic tokens of a verbal span with their numerals read: the span finder lexes for
    extents only, so each numeral is lexed again over its own range (the one numeral reader)."""
    out: list[Token] = []
    for t in tokens:
        if t.kind == "NUM" and t.value is None:
            again = lex(reading, t.start, t.end, mode="plain", orig=text, cs=profile.computer_science, limits=limits, max_tokens=2).tokens
            if len(again) == 1 and again[0].kind in ("NUM", "NUMERR") and again[0].end == t.end:
                t = again[0]
            else:
                t = t._replace(kind="NUMERR", value=("ST-PARSE-001", f"the numeral {t.text!r} could not be read"))
        out.append(t)
    return tuple(out)


def _empty(text: str, request_text: str, profile: StemProfile, limits: StemLimits, message: str, code: str = "ST-INTERNAL-001") -> StemDocument:
    finding = FrontEndFinding(code, ST_SEVERITY.get(code, "warning"), message, ())
    return StemDocument(text=text, request_text=request_text, profile=profile, key=(_sha(text), _sha(request_text) if request_text else "", profile.key),
                        reading=text, prose=text, spans=SpanSet(spans=(), lines=()), statements=(), paragraphs=(), items=(), relations=(),
                        findings=(finding,), bindings=MappingProxyType({}), formulas=MappingProxyType({}), substitutions=MappingProxyType({}),
                        names=frozenset(), request=RequestReading(),
                        prose_values=(), limits=limits)


@dataclass
class _Read:
    """One read text (the answer or the request): spans, statements, items, prose values."""

    text: str
    reading: str
    spans: SpanSet
    seg: Segmentation
    items: list[MathItem]
    prose_values: list[ProseValue]
    code_items: list[tuple[str, int, int, str]]
    order: dict[str, int]
    skipped: int = 0
    skipped_ids: tuple[str, ...] = ()


def _read(text: str, profile: StemProfile, limits: StemLimits, names: frozenset[str], *, request: bool = False,
          reading: Optional[str] = None) -> _Read:
    reading = reading_view(text) if reading is None else reading
    spans = find_spans(text, reading, profile=profile, limits=limits, names=names)
    seg = segment_statements(text, spans, names=names, limits=limits, reading=reading)
    order = {st.id: k for k, st in enumerate(seg.statements)}
    items: list[MathItem] = []
    prose_values: list[ProseValue] = []
    code_items: list[tuple[str, int, int, str]] = []
    given_paragraph: Optional[int] = None
    skipped = 0
    skipped_ids: list[str] = []
    for k, st in enumerate(seg.statements):
        st_text = reading[st.start:st.end]
        head = _strip_label(st_text).lower()
        is_given = head.startswith(_GIVEN_HEADS)
        if is_given and st_text.rstrip().endswith(":") and not st.spans:
            given_paragraph = st.paragraph
        elif given_paragraph is not None and st.paragraph != given_paragraph:
            given_paragraph = None
        source = "given" if (is_given or (given_paragraph == st.paragraph and st.list_item)) else "statement"
        cursor = st.start
        for si, row in st.spans:
            sp = spans.spans[si]
            if sp.kind in ("code_block", "code_inline"):
                if sp.kind == "code_block" or "=" in reading[sp.start:sp.end]:
                    code_items.append((st.id, sp.start, sp.end, sp.lang))
                continue
            a, b = sp.rows[row] if sp.rows else (sp.start, sp.end)
            gap = reading[max(cursor, sp.start - _BEFORE_WINDOW):sp.start] if sp.start >= cursor else ""
            item_source = source
            last_word = _last_word(gap)
            if item_source == "statement" and last_word in _LET_WORDS:
                item_source = "let"
            elif item_source == "statement" and last_word in _CONDITION_WORDS and not request:
                item_source = "condition"
            base = dict(index=len(items), statement_id=st.id, statement_index=k, part=st.part, stmt_kind=st.kind, span_kind=sp.kind, start=a, end=b,
                        label=sp.label, gap_before=gap, source=item_source, statement_text=st_text, statement_start=st.start, statement_end=st.end)
            if sp.kind == "quantity":
                node = _quantity_node(reading, text, sp, profile, limits, names)
                if node is not None:
                    prose_values.append(ProseValue(st.id, k, st.part, node, sp.start, sp.end, _prose_before(seg.prose, st.start, sp.start)))
                cursor = max(cursor, sp.end)
                continue
            if sp.kind == "data_line":
                cursor = max(cursor, sp.end)
                continue
            if sp.error:
                items.append(MathItem(error=sp.error, code=sp.code, **base))
                cursor = max(cursor, sp.end)
                continue
            if sp.kind == "table":
                table = parse_truth_table(text, sp.rows, limits=limits, computer_science=profile.computer_science)
                if table is not None:
                    rows = tuple(o.id for o in seg.covering(sp.start, sp.end) if o.id != st.id)  # each row is a statement
                    items.append(MathItem(table=table, cover_ids=rows, **base))
                cursor = max(cursor, sp.end)
                continue
            if sp.kind == "chem":
                eq = parse_equation(text[a:b], start=a, limits=limits)
                if eq is not None:
                    items.append(MathItem(chem=eq, **base))
                cursor = max(cursor, sp.end)
                continue
            if len(items) >= limits.max_math_items:
                skipped += 1
                if len(skipped_ids) < 8 and st.id not in skipped_ids:
                    skipped_ids.append(st.id)
                cursor = max(cursor, sp.end)
                continue
            mode = "latex" if sp.mode == "latex" else "plain"
            if sp.kind == "verbal":
                toks: tuple[Token, ...] = _with_values(sp.tokens, reading, text, profile, limits)
                overflow = False
            else:
                lx = lex(reading, a, b, mode=mode, orig=text, cs=profile.computer_science, limits=limits, max_tokens=limits.max_tokens_per_span + 1)
                toks, overflow = lx.tokens, lx.overflow
            if overflow or len(toks) > limits.max_tokens_per_span:
                items.append(MathItem(error=f"the span has more than {limits.max_tokens_per_span} tokens", code="ST-LIM-001", **base))
                cursor = max(cursor, sp.end)
                continue
            # chemistry written in LaTeX: \mathrm{CH_3COOH + NaOH \rightarrow ...}
            if profile.chemistry and mode == "latex" and (any(t.kind == "REL" and t.text in ("→", "⇌") for t in toks) or _wrapped_arrow(reading, a, b)):
                eq = parse_equation(latex_to_chem(reading[a:b]), start=a, limits=limits)
                if eq is not None and (eq.readable or not any(t.kind == "REL" and t.text == "=" for t in toks)):
                    items.append(MathItem(chem=_relocate(eq, a, b), **base))
                    cursor = max(cursor, sp.end)
                    continue
            if is_boolean_context(toks, profile.computer_science):
                rels, issues = parse_boolean(toks, limits=limits)
                items.append(MathItem(booleans=rels, issues=issues, **base))
                cursor = max(cursor, sp.end)
                continue
            pm = parse_math(toks, ParseContext(s=reading, names=names, profile=profile, limits=limits, mode=mode, lead_label=sp.label or None))
            items.append(MathItem(chains=pm.chains, issues=pm.issues, unparsed=pm.unparsed, **base))
            # a lone value written as inline maths ('is therefore $2.6\,\text{m s}^{-2}$') is a prose value like '2.6 m s⁻²'
            lone = _lone_value(pm) if sp.kind == "latex_inline" and not pm.issues and not pm.unparsed else None
            if lone is not None:
                prose_values.append(ProseValue(st.id, k, st.part, lone, a, b, _prose_before(seg.prose, st.start, sp.start)))
            cursor = max(cursor, sp.end)
        # bare numbers written in prose (outside every span) are prose values too
        for node, a0, b0 in _prose_numbers(reading, text, st, spans, profile, limits):
            prose_values.append(ProseValue(st.id, k, st.part, node, a0, b0, _prose_before(seg.prose, st.start, a0)))
    prose_values.sort(key=lambda pv: pv.start)
    return _Read(text, reading, spans, seg, items, prose_values, code_items, order, skipped, tuple(skipped_ids))


def _relocate(eq, a: int, b: int):
    """A chemical equation read from a LaTeX rewrite carries the span's offsets."""
    return replace(eq, start=a, end=b, left=tuple(replace(sp, start=a, end=b) for sp in eq.left), right=tuple(replace(sp, start=a, end=b) for sp in eq.right))


def _strip_label(text: str) -> str:
    t = text.lstrip(" *#>-•\t")
    if t.startswith("(") and ")" in t[:6]:
        t = t[t.index(")") + 1:].lstrip()
    return t


def _last_word(text: str) -> str:
    words = [w for w in "".join(c if c.isalpha() else " " for c in text.lower()).split()]
    return words[-1] if words else ""


#: how much statement prose before a value is kept for the result cue (bounded work per value)
_BEFORE_WINDOW = 240


def _prose_before(prose: str, a: int, b: int) -> str:
    return prose[max(a, b - _BEFORE_WINDOW):b] if b > a else ""


_CHEM_ARROWS = ("\\rightarrow", "\\longrightarrow", "\\rightleftharpoons", "\\leftrightharpoons", "\\to", "→", "⇌")


def _wrapped_arrow(reading: str, a: int, b: int) -> bool:
    """A reaction arrow inside a text wrapper (``$\\mathrm{2H_2 + O_2 \\rightarrow 2H_2O}$``), which the lexer reads as text."""
    seg = reading[a:b]
    return ("\\mathrm{" in seg or "\\text{" in seg or "\\ce{" in seg or "\\textrm{" in seg) and any(x in seg for x in _CHEM_ARROWS)


def _inside_brackets(text: str, a: int, b: int) -> bool:
    """An open round bracket between ``a`` and ``b`` that has not closed by ``b`` (bounded by ``b - a``)."""
    depth = 0
    for ch in text[a:b]:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
    return depth > 0


def _lone_value(pm):
    """The value of an inline maths span that holds exactly one value and no relation, else None."""
    if len(pm.chains) != 1 or pm.chains[0].links or len(pm.chains[0].operands) != 1 or len(pm.chains[0].operands[0].readings) != 1:
        return None
    node = pm.chains[0].operands[0].readings[0]
    return node if is_value(node) else None


def _quantity_node(reading: str, text: str, sp: Span, profile: StemProfile, limits: StemLimits, names: frozenset[str]):
    toks = lex(reading, sp.start, sp.end, mode="plain", orig=text, cs=profile.computer_science, limits=limits).tokens
    pm = parse_math(toks, ParseContext(s=reading, names=names, profile=profile, limits=limits))
    if len(pm.chains) != 1 or pm.chains[0].links or not pm.chains[0].operands or not pm.chains[0].operands[0].readings:
        return None
    node = pm.chains[0].operands[0].readings[0]
    return node if is_value(node) else None


def _prose_numbers(reading: str, text: str, st: Statement, spans: SpanSet, profile: StemProfile, limits: StemLimits) -> list:
    """Numbers written in the statement's prose, outside every span (``is 120 snails``)."""
    covered = [(spans.spans[si].start, spans.spans[si].end) for si, _r in st.spans]
    out = []
    if st.kind not in ("sentence", "list_item"):
        return out
    toks = lex(reading, st.start, st.end, mode="plain", orig=text, cs=profile.computer_science, limits=limits, max_tokens=2000, values=False).tokens
    for i, t in enumerate(toks):
        if t.kind != "NUM" or any(a <= t.start < b for a, b in covered):
            continue
        if t.value is None:
            scan = scan_number(reading, t.start, limits=limits, orig=text)
            if scan is None or scan.number is None or scan.end != t.end:
                continue
            t = t._replace(value=scan.number)
        prev = toks[i - 1] if i > 0 else None
        signed = False
        if prev is not None and not t.space and prev.kind == "OP" and prev.text in ("-", "−") and (prev.space or i == 1) \
                and not (i >= 2 and toks[i - 2].kind in ("NUM", "IDENT") and not prev.space):
            signed = True  # 'is therefore −0.70': a minus written before a prose number is its sign
        elif prev is not None and not prev.space and prev.kind in ("IDENT", "OP", "OTHER"):
            continue  # 'helium-4', 'H2', '$5000'
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if nxt is not None and not nxt.space and nxt.kind in ("IDENT",):
            continue
        node: object = Num(t.value, t.start, t.end)
        if signed:
            node = Neg(node, prev.start, t.end)
        if nxt is not None and nxt.kind == "PERCENT":
            node = Percent(node, getattr(node, "start", t.start), nxt.end)
        out.append((node, getattr(node, "start", t.start), getattr(node, "end", t.end)))
    return out


def _request_reading(request_text: str, profile: StemProfile, limits: StemLimits, names: frozenset[str]) -> tuple[RequestReading, Scope]:
    scope = Scope(limits=limits)
    if not request_text.strip():
        return RequestReading(), scope
    rd = _read(request_text, profile, limits, names, request=True)
    _rels, _findings, req_relations = plan_relations(rd.items, rd.prose_values, scope, RequestReading(), profile, limits=limits, statement_order=rd.order,
                                                     request_mode=True)
    bindings = tuple(b for lst in scope.bindings.values() for b in lst)
    quantities: list[tuple] = []
    for item in rd.items:
        for ch in item.chains:
            for op in ch.operands:
                node = op.node
                if node is not None and is_value(node):
                    v = value_of(node)
                    if v is not None and v[2] is not None:
                        quantities.append((node, op.start, op.end))
    for pv in rd.prose_values:
        v = value_of(pv.node)
        if v is not None and v[2] is not None:
            quantities.append((pv.node, pv.start, pv.end))
    targets: list[ShowThatTarget] = []
    for st in rd.seg.statements:
        st_text = rd.reading[st.start:st.end]
        low = st_text.lower()
        k = low.find("show that")
        if k < 0:
            continue
        cands: list[tuple[int, object]] = []
        for pv in rd.prose_values:
            pv_value = value_of(pv.node)
            if pv.statement_id == st.id and pv.start >= st.start + k and pv_value is not None and pv_value[2] is not None:
                cands.append((pv.start, pv.node))  # a quantity with its unit; a bare number in the prose is no target
        for item in rd.items:
            if item.statement_id != st.id:
                continue
            if item.start < st.start + k:
                continue
            for ch in item.chains:
                if ch.links == 1 and ch.operands[0].node is not None and isinstance(ch.operands[0].node, Sym) and ch.operands[1].node is not None \
                        and is_value(ch.operands[1].node):
                    cands.append((ch.operands[1].start, ch.operands[1].node))
        # a value inside brackets after the target is data ('Show that 4.0 g is 0.10 mol (M = 40.0 g mol⁻¹).'), not the target
        cands = [c for c in cands if not _inside_brackets(rd.reading, st.start + k, c[0])] or cands
        if cands:
            cands.sort(key=lambda c: c[0])
            pos, node = cands[-1]
            approx = any(w in low for w in ("about", "approximately", "roughly", "≈", "~")) or "≈" in st_text
            targets.append(ShowThatTarget(node=node, approx=approx, text=st_text, start=getattr(node, "start", pos), end=getattr(node, "end", pos)))
    restricts = any(w in request_text.lower() for w in _RESTRICT)
    return RequestReading(bindings=bindings, quantities=tuple(quantities), relations=tuple(req_relations), targets=tuple(targets), text=request_text,
                          restricts_domain=restricts), scope


def _build(text: str, request_text: str, profile: StemProfile, limits: StemLimits) -> StemDocument:
    key = (_sha(text), _sha(request_text) if request_text else "", profile.key)
    if len(text) > limits.max_response_chars:
        return _empty(text, request_text, profile, limits, f"the response has {len(text)} characters; the report contract allows {limits.max_response_chars}",
                      code="ST-LIM-001")
    reading = reading_view(text)
    names = prescan_names(reading, limits=limits, cs=profile.computer_science)
    req_names = prescan_names(reading_view(request_text), limits=limits, cs=profile.computer_science) if request_text else frozenset()
    all_names = names | req_names
    request, req_scope = _request_reading(request_text, profile, limits, all_names)
    rd = _read(text, profile, limits, all_names, reading=reading)
    scope = Scope(limits=limits)
    for b in request.bindings:
        scope.add(b)
    for name, flist in req_scope.formulas.items():
        for f in flist:
            scope.add_formula(f)
    scope.notes.clear()
    relations, findings, _ = plan_relations(rd.items, rd.prose_values, scope, request, profile, limits=limits, statement_order=rd.order,
                                            code_items=rd.code_items)
    if rd.skipped:
        findings.append(FrontEndFinding("ST-LIM-002", ST_SEVERITY["ST-LIM-002"], f"{rd.skipped} math spans beyond the per-report bound of "
                                        f"{limits.max_math_items} were not read; their relations are not checked (first statements: {', '.join(rd.skipped_ids)})",
                                        rd.skipped_ids))
    bindings = MappingProxyType({k: tuple(v) for k, v in scope.bindings.items()})
    formulas = MappingProxyType({k: tuple(v) for k, v in scope.formulas.items()})
    substitutions = MappingProxyType({k: tuple(v) for k, v in scope.substitutions.items()})
    by_id = MappingProxyType({st.id: st for st in rd.seg.statements})
    return StemDocument(text=text, request_text=request_text, profile=profile, key=key, reading=reading, prose=rd.seg.prose, spans=rd.spans,
                        statements=rd.seg.statements, paragraphs=rd.seg.paragraphs, items=tuple(rd.items), relations=tuple(relations),
                        findings=tuple(findings), bindings=bindings, formulas=formulas, substitutions=substitutions, names=frozenset(all_names | set(scope.names)), request=request,
                        prose_values=tuple(rd.prose_values), overflow=rd.seg.overflow, limits=limits, _by_id=by_id)
