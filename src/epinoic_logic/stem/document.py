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
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from types import MappingProxyType
from typing import Mapping, Optional

from .boolean import is_boolean_context, parse_boolean, parse_truth_table
from .chem import latex_to_chem, parse_equation
from .datatables import parse_data_tables
from .lexer import Token, lex
from .limits import DEFAULT_LIMITS, StemLimits, StemProfile, profile_for
from .nodes import Neg, Num, Percent, Sym, is_value, value_of
from .normalize import reading_view
from .numbers import scan_number
from .parser import ParseContext, parse_math
from .relations import (
    FrontEndFinding, MathItem, ProseValue, Relation, RequestReading, ShowThatTarget, ST_SEVERITY, _inline_restatement, _name_words, _word_after,
    named_quantities, plan_relations,
)
from .scope import Binding, Formula, Scope, prescan_names
from .segment import Segmentation, Statement, segment_statements
from .spans import Span, SpanSet, find_spans

__all__ = ["StemDocument", "build_document", "clear_document_cache", "document_cache_info"]

_GIVEN_HEADS = ("given", "data", "known", "we know")
#: rule prose-given (STEM repair 6): a Given statement whose head ends with a colon, a data list ('Given:', 'Data:', 'Known values:',
#: 'We know:', 'Given (from the question):'): every value its prose states is a Given value
_GIVEN_LIST_RE = re.compile(r"(?:given|data|known|we[ \t]+know)(?:[ \t]+[a-z()'’\-]+){0,3}?[ \t]*:", re.IGNORECASE)
#: a Given clause with no colon after its head ('Given that the emf is 15 V, …', 'We know the internal resistance was 0.40 Ω.'): the values
#: of its first clause, up to the first comma, semicolon or colon, are Given values (what follows is the statement's own: a result)
_GIVEN_CLAUSE_RE = re.compile(r"(?:given|known|we[ \t]+know)\b", re.IGNORECASE)
_CLAUSE_END_RE = re.compile(r"[,;:]")
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
    #: rule changed-value (STEM repair 4): the values the prose gives a symbol at the end of a change it states, which a substitution
    #: stated after them, in their statement or in their part may take (never premises of their own check)
    changes: Mapping[str, tuple[Binding, ...]] = field(default_factory=lambda: MappingProxyType({}))

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
                   limits: StemLimits = DEFAULT_LIMITS, data: "tuple[str, ...] | list[str]" = ()) -> StemDocument:
    """The memoised :class:`StemDocument` of ``text`` (and the request it answers) under a
    STEM profile key (``physics``, ``chemistry``, ``mathematics_aa``, ``computer_science``, ...).
    ``data`` are the texts supplied with the request: their tables are read as the request's data
    (rule ``table-data``, :mod:`.datatables`) and the values their prose states too (rule ``supplied-values``, STEM repair 3).
    Repeated calls with the same arguments return the same object."""
    prof = profile_for(profile)
    return _cached(text, request_text or "", prof, limits, tuple(t for t in data if t and t.strip())[:8])


@lru_cache(maxsize=DEFAULT_LIMITS.document_cache_entries)
def _cached(text: str, request_text: str, profile: StemProfile, limits: StemLimits, data: tuple[str, ...] = ()) -> StemDocument:
    try:
        return _build(text, request_text, profile, limits, data)
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
        in_given_list = given_paragraph == st.paragraph and st.list_item
        source = "given" if (is_given or in_given_list) else "statement"
        given_part = None if request else _prose_given_part(st_text, st.start, in_given_list)
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
            elif item_source == "given" and last_word in _CONDITION_WORDS and not request and (si, row) != st.spans[-1]:
                # STEM repair 3 (rule value-at): 'Given: at t = 8 h, C = 820 counts min⁻¹': the first value is the condition the next
                # one is given under, never a Given of its own (it was set against the request's t = 32 h and failed)
                item_source = "condition"
            base = dict(index=len(items), statement_id=st.id, statement_index=k, part=st.part, stmt_kind=st.kind, span_kind=sp.kind, start=a, end=b,
                        label=sp.label, gap_before=gap, source=item_source, statement_text=st_text, statement_start=st.start, statement_end=st.end)
            if sp.kind == "quantity":
                node = _quantity_node(reading, text, sp, profile, limits, names)
                if node is not None:
                    prose_values.append(ProseValue(st.id, k, st.part, node, sp.start, sp.end, _prose_before(seg.prose, st.start, sp.start),
                                                   _prose_after(seg.prose, sp.end, st.end), given=_in_part(given_part, sp.start)))
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
                prose_values.append(ProseValue(st.id, k, st.part, lone, a, b, _prose_before(seg.prose, st.start, sp.start), _prose_after(seg.prose, b, st.end),
                                               given=_in_part(given_part, a)))
            cursor = max(cursor, sp.end)
        # bare numbers written in prose (outside every span) are prose values too; on a line of working only a number restated after
        # the chain it closes ('= 4773.74, so 4775.'; STEM repair 4, rule inline-restatement)
        for node, a0, b0 in _prose_numbers(reading, text, st, spans, profile, limits):
            before, after = _prose_before(seg.prose, st.start, a0), _prose_after(seg.prose, b0, st.end)
            if st.kind == "derivation" and not (_inline_restatement(before) and _CLAUSE_TAIL_RE.match(after[:60])):
                continue
            prose_values.append(ProseValue(st.id, k, st.part, node, a0, b0, before, after, given=_in_part(given_part, a0)))
    prose_values.sort(key=lambda pv: pv.start)
    return _Read(text, reading, spans, seg, items, prose_values, code_items, order, skipped, tuple(skipped_ids))


#: STEM repair 4: what may follow a number restated on a line of working: the line's end or a full stop, a stated rounding, a bracket
_CLAUSE_TAIL_RE = re.compile(r"^\s*(?:[.;)]\s*$|$|[,(]?\s*\(?\s*(?:to|correct\s+to|rounded\s+to)\s)", re.IGNORECASE)
#: rule unread-relation (STEM repair 2): the relation signs a statement may hold that no span read
_RELATION_SIGNS = frozenset("=≈≠≤≥≡<>")
#: at most this many unread signs are looked at per statement (the first is named)
_MAX_UNREAD_SCAN = 4000


def _unread_relation_signs(rd: _Read) -> list[FrontEndFinding]:
    """Rule ``unread-relation`` (STEM repair 2): a relation sign in a statement that no span of the reader holds (code, markup and
    headings are blanked first; a table, a chemical equation, maths in LaTeX or prose all count as read) is named, ST-PARSE-001, so a
    relation the reader cannot see ('17 % 5 = 2' outside Computer Science, a sign between words) is never silently unchecked. An
    ASCII arrow or a comparison sign between two words or brackets ('->', '=>', '<-', '<<') is no relation sign here."""
    view = rd.spans.math_view or rd.reading
    covered = bytearray(len(view) + 1)
    for sp in rd.spans.spans:
        a, b = max(0, sp.start), min(len(view), sp.end)
        if b > a:
            covered[a:b] = b"\x01" * (b - a)
    out: list[FrontEndFinding] = []
    for st in rd.seg.statements:
        hit = None
        for k in range(st.start, min(st.end, st.start + _MAX_UNREAD_SCAN, len(view))):
            ch = view[k]
            if ch not in _RELATION_SIGNS or covered[k]:
                continue
            prev = view[k - 1] if k > 0 else " "
            nxt = view[k + 1] if k + 1 < len(view) else " "
            if prev in "-=<>!" or nxt in "-=<>":
                continue  # an ASCII arrow or a doubled sign ('->', '=>', '<-', '<<', '=='), read by the spans when it is maths
            if prev.isalpha() and nxt.isalpha():
                continue  # a bond 'O=O', 'C=O', 'N≡N' (a sign glued between two letters names no relation of values)
            if not (_operand_char(view, k, -1) and _operand_char(view, k, 1)):
                continue  # a sign between words ('Corrected count rate = measured count rate − background', '(== and <)') names no maths
            hit = k
            break
        if hit is None:
            continue
        excerpt = " ".join(rd.text[max(st.start, hit - 30):min(st.end, hit + 30)].split())
        out.append(FrontEndFinding("ST-PARSE-001", ST_SEVERITY["ST-PARSE-001"], f"a relation sign in {st.id} that the branch read no relation at ('…{excerpt}…'): "
                                   "it is written in a form outside the grammar, and it is not checked", (st.id,), hit, hit + 1))
    return out


def _operand_char(view: str, k: int, step: int) -> bool:
    """Maths next to position ``k`` (after at most two spaces) in direction ``step``: a digit, a bracket, a superscript or a symbol
    of one letter (a Greek letter, or a Latin letter that is no part of a word), never a word. An amount written after a currency
    sign ('$5000', '€4000') is no maths the reader holds, so a sign beside one names nothing (the corpus's correct
    '$7052.99 − $5000 = $2052.99' carries no finding)."""
    j = k + step
    for _ in range(3):
        if not (0 <= j < len(view)):
            return False
        c = view[j]
        if c in " \t":
            j += step
            continue
        if c.isdigit() or c in "()[]⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉":
            return True
        if not c.isalpha():
            return False
        m = j
        while 0 <= m + step < len(view) and view[m + step].isalpha():
            m += step
        run = view[min(j, m):max(j, m) + 1]
        return len(run) == 1 or not run.isascii()
    return False


def _relocate(eq, a: int, b: int):
    """A chemical equation read from a LaTeX rewrite carries the span's offsets."""
    return replace(eq, start=a, end=b, left=tuple(replace(sp, start=a, end=b) for sp in eq.left), right=tuple(replace(sp, start=a, end=b) for sp in eq.right))


def _strip_label(text: str) -> str:
    t = text.lstrip(" *#>-•\t")
    if t.startswith("(") and ")" in t[:6]:
        t = t[t.index(")") + 1:].lstrip()
    return t


def _prose_given_part(st_text: str, st_start: int, in_given_list: bool) -> Optional[tuple[int, int]]:
    """Rule ``prose-given`` (STEM repair 6): the offsets of the part of a statement whose prose values are Given values, else None. A
    statement whose head (after a list marker or a part label) is "Given", "Data", "Known" or "We know" and ends with a colon within three
    more words is a data list: the whole statement ('Data: emf 15 V, internal resistance 0.50 Ω.'); a statement of the list a line
    "Given:" opens is one too. A statement that begins "Given", "Known" or "We know" with no such colon is a Given clause: its first
    clause, up to the first comma, semicolon or colon ('We know the internal resistance was 0.40 Ω.'; in 'Given that the half-life is
    8.0 h, the decay constant is 0.087 h⁻¹.' the decay constant is the statement's result). "Data" with no colon heads no Given clause
    ('**Data analysis** rewards records …'). Only prose values are read here: the values given with "=" in a Given statement are read
    by the Given statement's maths, as before."""
    if in_given_list:
        return st_start, st_start + len(st_text)
    stripped = _strip_label(st_text)
    lead = len(st_text) - len(stripped)
    if _GIVEN_LIST_RE.match(stripped):
        return st_start, st_start + len(st_text)
    m = _GIVEN_CLAUSE_RE.match(stripped)
    if m is None:
        return None
    end = _CLAUSE_END_RE.search(stripped, m.end())
    return st_start + lead, st_start + lead + (end.start() if end is not None else len(stripped))


def _in_part(part: Optional[tuple[int, int]], at: int) -> bool:
    return part is not None and part[0] <= at < part[1]


def _last_word(text: str) -> str:
    words = [w for w in "".join(c if c.isalpha() else " " for c in text.lower()).split()]
    return words[-1] if words else ""


#: how much statement prose before a value is kept for the result cue (bounded work per value)
_BEFORE_WINDOW = 240


def _prose_before(prose: str, a: int, b: int) -> str:
    return prose[max(a, b - _BEFORE_WINDOW):b] if b > a else ""


#: how much statement prose after a value is kept (what qualifies it: a unit word, a rounding note such as "60%, to 2 s.f.", a condition)
_AFTER_WINDOW = 120


def _prose_after(prose: str, a: int, b: int) -> str:
    return prose[a:min(b, a + _AFTER_WINDOW)] if b > a else ""


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
    if st.kind not in ("sentence", "list_item", "derivation"):
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


def _request_reading(request_text: str, profile: StemProfile, limits: StemLimits, names: frozenset[str],
                     tables: tuple = ()) -> tuple[RequestReading, Scope]:
    scope = Scope(limits=limits)
    if not request_text.strip():
        return RequestReading(tables=tables), scope
    rd = _read(request_text, profile, limits, names, request=True)
    _rels, _findings, req_relations = plan_relations(rd.items, rd.prose_values, scope, RequestReading(), profile, limits=limits, statement_order=rd.order,
                                                     request_mode=True, reading=rd.reading)
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
    values = _request_values(request_text, rd)
    return RequestReading(bindings=bindings, quantities=tuple(quantities), relations=tuple(req_relations), targets=tuple(targets), text=request_text,
                          restricts_domain=restricts, tables=tables, values=values, named_quantities=_named_quantities(request_text, quantities)), scope


def _request_values(request_text: str, rd: "_Read") -> tuple:
    """Every value the request states, with the word written after it (rule given-kinds, STEM repair 2)."""
    out: list[tuple] = []
    seen: set[tuple[int, int]] = set()
    for item in rd.items:
        for ch in item.chains:
            for op in ch.operands:
                node = op.node
                if node is not None and is_value(node) and (op.start, op.end) not in seen:
                    seen.add((op.start, op.end))
                    out.append((node, op.start, op.end, _word_after(request_text, op.end)))
    for pv in rd.prose_values:
        if (pv.start, pv.end) not in seen:
            seen.add((pv.start, pv.end))
            out.append((pv.node, pv.start, pv.end, _word_after(request_text, pv.end)))
    return tuple(sorted(out, key=lambda x: x[1]))


#: the words that end the name of a request quantity read backwards from its number (rule named-given)
_NAME_BREAK_RE = re.compile(r"[.;:!?()\[\]\n]|\d")
#: STEM repair 9: the prepositions that end the object a request's quantity is of ('a battery of emf 12 V': the emf)
_NAME_OF_WORDS = frozenset({"of", "in", "on", "at", "for", "with", "from", "across", "through", "between", "to", "by", "into", "over", "under",
                            "within"})


def _named_quantities(request_text: str, quantities: list) -> tuple:
    """The request's quantities with the words that name them (rule named-given, STEM repair 2): the last three content words before
    the number, back to punctuation or another number, a preposition right before the number skipped ('a battery of emf 12 V' -> emf;
    'internal resistance 0.50 ohm' -> internal, resistance); a quantity listed after another with 'and' or a comma takes its name.
    STEM repair 9: the words after a preposition that stands between the name and the words before it are the name, the words before
    the preposition the object it is of ('a battery of emf 12 V' -> emf, as this docstring said; the code had kept 'battery, emf', so
    "the emf is 9.0 V" matched no request quantity: rules named-given and named-result)."""
    out: list[tuple] = []
    prev_words: list[str] = []
    prev_end = -10
    for node, a0, b0 in sorted(quantities, key=lambda q: q[1]):
        w0 = max(0, a0 - 60)
        window = request_text[w0:a0]
        cut = max((m.end() for m in _NAME_BREAK_RE.finditer(window)), default=0)
        if w0 <= prev_end <= a0:
            # STEM repair 11: the words of the previous quantity's unit are no name ('two resistors of 4.0 ohm and 6.0 ohm' had named the
            # 6.0 ohm 'ohm', the 4.0 ohm's unit, so it was no second value of the two resistors): the name starts after that quantity
            cut = max(cut, prev_end - w0)
        gap = window[cut:]
        tokens = gap.split()[-4:]
        # STEM repair 9: a preposition with name words after it ends what is before it ('a battery of emf' -> emf); one right before
        # the number is skipped as before ('two resistors of 4.0 ohm' -> two, resistors)
        k = max((i for i, t in enumerate(tokens[:-1]) if t.lower() in _NAME_OF_WORDS and any(w.isalpha() for w in tokens[i + 1:])), default=-1)
        if k >= 0 and _name_words(" ".join(tokens[k + 1:])):
            tokens = tokens[k + 1:]
        if len(tokens) >= 2 and tokens[-1].lower() in ("a", "an", "the") and tokens[-2].lower() in _NAME_OF_WORDS:
            # STEM repair 9: a preposition and an article right before the number open a new noun phrase whose name follows the value
            # ('the horizontal component of a 10 N force', 'the power dissipated in the 6.0 ohm resistor'): the words before name
            # something of it, never the value (the 10 N force had been named 'horizontal component')
            tokens = []
        words = _name_words(" ".join(tokens))
        if not words and 0 <= a0 - prev_end <= 8 and request_text[prev_end:a0].strip().lower() in ("and", ",", "or"):
            words = prev_words
        if words:
            out.append((node, a0, b0, tuple(words[-3:])))
        prev_words, prev_end = words, b0
    return tuple(out)


#: rule supplied-values (STEM repair 3): how much of each text supplied with the request is read for its values, and how many values
_MAX_SUPPLIED_CHARS = 6000
_MAX_SUPPLIED_VALUES = 64
#: a unit atom written with an ASCII exponent right after a number or another unit ('50.0 cm3', '0.10 mol dm-3')
_ASCII_UNIT_EXP_RE = re.compile(r"(?<![A-Za-zµμ])([A-Za-zµμ]{1,3})(-?)([1-4])(?![\w.])")
_SUPERSCRIPTS = str.maketrans("-1234", "⁻¹²³⁴")
#: a value right after a colon: its name is the sentence's head before its first comma or colon ('Background count rate, measured …:')
_LABEL_HEAD_RE = re.compile(r"(?:^|(?<=[.\n]))\s*(?P<head>[A-Za-z][A-Za-z ’'-]{2,60}?)\s*[,:]")


def _supplied_units(text: str) -> str:
    """A supplied text's units written with ASCII exponents, in superscripts ('50.0 cm3' -> '50.0 cm³', 'mol dm-3' -> 'mol dm⁻³'), and
    '+/-' as '±': the forms the unit reader reads. Only an atom the table of units knows, right after a number or another unit, is
    rewritten (a formula 'H2O' or a label 'Q1' is not). The answer's own text is never rewritten; this is the supplied data's reading."""
    from .units import is_unit_atom, parse_unit
    out: list[str] = []
    last = 0
    for m in _ASCII_UNIT_EXP_RE.finditer(text):
        atom = m.group(1)
        if not is_unit_atom(atom):
            continue
        prev = re.search(r"(\S+)\s+$", text[max(0, m.start() - 24):m.start()])
        if prev is None:
            continue
        p = prev.group(1).rstrip(",;")
        if not (p[-1:].isdigit() or is_unit_atom(p) or parse_unit(_supplied_units_atom(p)) is not None):
            continue
        out.append(text[last:m.start()])
        out.append(atom + (m.group(2) + m.group(3)).translate(_SUPERSCRIPTS))
        last = m.end()
    out.append(text[last:])
    return "".join(out).replace("+/-", "±")


def _supplied_units_atom(word: str) -> str:
    m = re.fullmatch(r"([A-Za-zµμ]{1,3})(-?)([1-4])", word)
    return m.group(1) + (m.group(2) + m.group(3)).translate(_SUPERSCRIPTS) if m else word


def _sentence_words(text: str, pos: int) -> frozenset[str]:
    """The content words of the sentence (or line) of a supplied text that holds ``pos``, lower case, four letters or more (rule
    supplied-values: a Given is set against a supplied value only when its name shares one: 'volume of thiosulfate' and 'Each trial:
    50.0 cm3 of … sodium thiosulfate solution')."""
    lo = max(0, pos - 400)
    starts = [m.end() for m in _SENTENCE_END_RE.finditer(text, lo, pos)]
    a = starts[-1] if starts else lo
    m = _SENTENCE_END_RE.search(text, pos, min(len(text), pos + 400))
    b = m.start() if m else min(len(text), pos + 400)
    return frozenset(w for w in (x.lower() for x in re.findall(r"[A-Za-z]+", text[a:b])) if len(w) >= 4)


#: the end of a sentence or a line of a supplied text: never the point of a decimal ('50.0 cm3')
_SENTENCE_END_RE = re.compile(r"[.;!?](?=\s|$)|\n")


def _uncertainty_before(text: str, start: int) -> bool:
    """The value at ``start`` is written as an uncertainty ('±0.5 °C', '+/- 2%'): no value of a quantity."""
    before = text[max(0, start - 6):start].rstrip()
    return before.endswith(("±", "+/-", "∓"))


#: the words right after an uncertainty's number, up to a clause's end (rule given-uncertainty)
_UNC_UNIT_RE = re.compile(r"[ \t]*([^\s;,()]+(?:[ \t]+[^\s;,()]+){0,3})")


def _uncertainty_unit(text: str, end: int):
    """The unit written after an uncertainty's number ('±0.5 °C; stopwatch …' -> °C): the longest run of at most four words from
    ``end`` that the table of units reads with a dimension, a final full stop dropped; None when there is none."""
    from .units import parse_unit
    m = _UNC_UNIT_RE.match(text, end, min(len(text), end + 80))
    if m is None:
        return None
    words = m.group(1).split()
    for k in range(len(words), 0, -1):
        cand = " ".join(words[:k])
        cand = cand[:-1] if cand.endswith(".") else cand
        u = parse_unit(cand) if cand else None
        if u is not None and u.dim is not None and not u.unknown:
            return u
    return None


def _supplied_reading(data: tuple[str, ...], profile: StemProfile, limits: StemLimits, names: frozenset[str]) -> tuple[tuple, tuple, tuple, tuple]:
    """Rule ``supplied-values`` (STEM repair 3): the values the texts supplied with the request state in their prose, outside their
    tables (which rule table-data reads): quantities with a unit the table of units reads, and percentages. A value written as an
    uncertainty ('±0.5 °C') is none: it is one of the uncertainties the texts state (rule given-uncertainty), with the unit written
    after it, as ``(node, start, end, unit, wrapper, sentence words)``. Each quantity is also named by the words before it (as the
    request's are), or, right after a colon, by its sentence's head ('Background count rate, measured before …: 20 counts per
    minute' -> background count rate). Bounded: the first characters of at most eight texts, a fixed number of values. Never raises
    on text."""
    quantities: list[tuple] = []
    values: list[tuple] = []
    named: list[tuple] = []
    uncertainties: list[tuple] = []
    for raw in data[:8]:
        prose = "\n".join(line for line in (raw or "")[:_MAX_SUPPLIED_CHARS].split("\n") if "|" not in line)
        if not prose.strip():
            continue
        prose = _supplied_units(prose)
        rd = _read(prose, profile, limits, names, request=True)
        found: list[tuple] = []
        for item in rd.items:
            for ch in item.chains:
                for op in ch.operands:
                    if op.node is not None and is_value(op.node):
                        found.append((op.node, op.start, op.end))
        for pv in rd.prose_values:
            found.append((pv.node, pv.start, pv.end))
        qs: list[tuple] = []
        seen: set[tuple[int, int]] = set()
        for node, a0, b0 in sorted(found, key=lambda q: q[1]):
            if (a0, b0) in seen:
                continue
            if _uncertainty_before(prose, a0):
                # rule given-uncertainty (STEM repair 3): the uncertainties the text states ('Uncertainties: thermometer ±0.5 °C')
                seen.add((a0, b0))
                v = value_of(node)
                if v is None or v[1] is None:
                    continue
                if v[2] is None and (v[3] == "%" or _word_after(prose, b0) == "%"):
                    uncertainties.append((node, a0, b0, None, "%", _sentence_words(prose, a0)))
                    continue
                unit = v[2] if v[2] is not None else _uncertainty_unit(prose, b0)
                if unit is not None and unit.dim is not None and not unit.unknown:
                    uncertainties.append((node, a0, b0, unit, "", _sentence_words(prose, a0)))
                continue
            seen.add((a0, b0))
            v = value_of(node)
            if v is None or v[1] is None:
                continue
            words = _sentence_words(prose, a0)
            if v[2] is not None and v[2].dim is not None and not v[2].unknown:
                qs.append((node, a0, b0))
                quantities.append((node, a0, b0, words))
            elif v[2] is None and (v[3] == "%" or _word_after(prose, b0) == "%"):
                values.append((node, a0, b0, "%", words))
        named.extend(_named_quantities(prose, qs))
        for node, a0, b0 in qs:
            head = prose[max(0, a0 - 160):a0].rstrip()
            if not head.endswith(":"):
                continue
            sentence = re.split(r"(?<=[.\n])\s", head)[-1]
            m = _LABEL_HEAD_RE.match(sentence)
            words = _name_words(m.group("head")) if m else []
            if words:
                named.append((node, a0, b0, tuple(words[:4])))
    return (tuple(quantities[:_MAX_SUPPLIED_VALUES]), tuple(values[:_MAX_SUPPLIED_VALUES]), tuple(named[:_MAX_SUPPLIED_VALUES]),
            tuple(uncertainties[:_MAX_SUPPLIED_VALUES]))


def _build(text: str, request_text: str, profile: StemProfile, limits: StemLimits, data: tuple[str, ...] = ()) -> StemDocument:
    key = (_sha(text), _sha(request_text) if request_text else "", profile.key) + ((_sha("\x00".join(data)),) if data else ())
    if len(text) > limits.max_response_chars:
        return _empty(text, request_text, profile, limits, f"the response has {len(text)} characters; the report contract allows {limits.max_response_chars}",
                      code="ST-LIM-001")
    reading = reading_view(text)
    names = prescan_names(reading, limits=limits, cs=profile.computer_science)
    req_names = prescan_names(reading_view(request_text), limits=limits, cs=profile.computer_science) if request_text else frozenset()
    all_names = names | req_names
    request, req_scope = _request_reading(request_text, profile, limits, all_names, parse_data_tables(data) if data else ())
    if data and request_text.strip():
        sq, sv, sn, su = _supplied_reading(data, profile, limits, all_names)
        request = replace(request, supplied_quantities=sq, supplied_values=sv, supplied_named=sn, supplied_uncertainties=su)
    if request_text.strip() and any(mark in request_text for mark in ("±", "+/-", "∓")):
        # rule given-uncertainty (STEM repair 3): the uncertainties the request itself states, read as a supplied text's are
        request = replace(request, request_uncertainties=_supplied_reading((request_text,), profile, limits, all_names)[3])
    rd = _read(text, profile, limits, all_names, reading=reading)
    scope = Scope(limits=limits)
    for b in request.bindings:
        scope.add(b)
    for name, flist in req_scope.formulas.items():
        for f in flist:
            scope.add_formula(f)
    for name, mlist in req_scope.models.items():
        for m in mlist:
            scope.add_model(m)
    scope.functions |= req_scope.functions
    scope.notes.clear()
    # the symbols the answer names by a description ('Let $M$ be the monthly payment'), each with its statement
    definitions = [(rd.order[st.id], st.part, sym, variants, st.id) for st in rd.seg.statements if st.kind in ("sentence", "list_item")
                   for sym, variants in named_quantities(reading[st.start:st.end])]
    relations, findings, _ = plan_relations(rd.items, rd.prose_values, scope, request, profile, limits=limits, statement_order=rd.order,
                                            code_items=rd.code_items, definitions=definitions, reading=rd.reading, text=reading)
    findings.extend(_unread_relation_signs(rd))
    if rd.skipped:
        findings.append(FrontEndFinding("ST-LIM-002", ST_SEVERITY["ST-LIM-002"], f"{rd.skipped} math spans beyond the per-report bound of "
                                        f"{limits.max_math_items} were not read; their relations are not checked (first statements: {', '.join(rd.skipped_ids)})",
                                        rd.skipped_ids))
    bindings = MappingProxyType({k: tuple(v) for k, v in scope.bindings.items()})
    formulas = MappingProxyType({k: tuple(v) for k, v in scope.formulas.items()})
    substitutions = MappingProxyType({k: tuple(v) for k, v in scope.substitutions.items()})
    changes = MappingProxyType({k: tuple(v) for k, v in scope.changes.items()})
    by_id = MappingProxyType({st.id: st for st in rd.seg.statements})
    return StemDocument(text=text, request_text=request_text, profile=profile, key=key, reading=reading, prose=rd.seg.prose, spans=rd.spans,
                        statements=rd.seg.statements, paragraphs=rd.seg.paragraphs, items=tuple(rd.items), relations=tuple(relations),
                        findings=tuple(findings), bindings=bindings, formulas=formulas, substitutions=substitutions, names=frozenset(all_names | set(scope.names)), request=request,
                        prose_values=tuple(rd.prose_values), overflow=rd.seg.overflow, limits=limits, _by_id=by_id, changes=changes)
