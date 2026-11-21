"""The Language B pack (D9/D10, decision D35): what a specialist states about a production, checked against that production, on the
``language_b`` branch (every Language B and ab initio course).

The branch keeps the generic parser (claim ids, roles and materiality as on the generic branch) and runs the shared core pack first
(with the shared self-certification gate, CORE-SELF-001, which no model-text region exempts anything from). This pack reads the answer
as written into regions (:func:`model_regions`: a practice disclaimer, the model text with its headline, byline, greeting and
closing, an inline model sentence, the English meta paragraphs, and in a marking task the student's supplied text), and builds engine
problems from the specialist's own statements about those productions:

=========================  =====================================================================  ===================================
kind                       statement read                                                         failure
=========================  =====================================================================  ===================================
``lb_word_count``          a word count stated about a production ("Word count: about 513")        INT-SUBJ-001 (unique production);
                                                                                                  INT-SUBJ-004 (a disjunction)
``lb_word_range_claim``    a production said to lie inside (or outside) a range                    INT-SUBJ-001
``lb_course_word_range``   a convention: an SL / HL Paper 1 model with no bound in the request     INT-SUBJ-004
``lb_quoted_form``         a form the answer says the model (or an inline model) contains          INT-SUBJ-004
``lb_address_form``        the address form (tú, vos, usted, vosotros, ustedes) a production uses  INT-SUBJ-004
``lb_listed_count``        a count of items the answer lists itself (corrections, connectors)      INT-SUBJ-004
``lb_percent_change``      a Spanish change with its from-to pair ("pasó de 1.250 a 212 ...")      INT-SUBJ-001
``supplied_figure``        a Spanish figure with its noun read against the supplied text           INT-SUBJ-001 credited (or a numbered
                                                                                                  reading answer); INT-SUBJ-004
``worked_arithmetic``      every worked equation, as on the generic branch                         as there
=========================  =====================================================================  ===================================

Measured counts are premises grounded in the answer or the supplied text as written (a deterministic measurement, as the channel's own
word-bound problems are). Words are counted with the channel's own counter (``request_parser.count_words``), so pack and channel never
count differently. The Spanish readers (:mod:`.spanish_lexicon`) act only on Spanish text; other Language B courses get the
language-neutral checks. The pack never judges register, accuracy or text-type fit (the profile's ``cannot_check``), never attempts
morphology, and never counts a model's own content. Every reader is bounded and linear in the answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from ..translate.contracts import SpecialistReport, StructuralFinding
from . import spanish_lexicon as es
from .base import FormalCheck
from .geography import _real, _var, make_check

__all__ = ["LanguageBPack", "Regions", "classify_task", "model_regions"]

MAX_TEXT = 200_000
MAX_REQUEST = 20_000
MAX_CHECKS = 200
MAX_FORMS = 32
MAX_FORM_CHARS = 200
MAX_REGION = 60_000
#: Course conventions for a Paper 1 production when the request sets no bound (a working rule, never a bound the request set).
COURSE_RANGES = {"SL": (250, 400), "HL": (450, 600)}
_PARA_RE = re.compile(r"\n[ \t]*\n")

_EN_NUMBERS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
                                          "eighteen nineteen twenty".split())}
_ES_NUMBERS = {w: i for i, w in enumerate("cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis diecisiete "
                                          "dieciocho diecinueve veinte".split())}
_ES_NUMBERS["una"] = 1
_NUMBER_WORD = "|".join(sorted(set(_EN_NUMBERS) | set(_ES_NUMBERS), key=len, reverse=True))


def _count_value(w: str) -> Optional[int]:
    w = (w or "").casefold()
    if w.isdigit():
        return int(w)
    return _EN_NUMBERS.get(w, _ES_NUMBERS.get(w))


_WORDS_MEMO: dict[tuple[int, int], tuple[str, int]] = {}


def _words(text: str) -> int:
    """The channel's word count of ``text``; the same production is measured once however many statements name it (a count per
    statement over the whole answer was O(statements x answer))."""
    from ..channel.request_parser import count_words
    t = (text or "")[:MAX_REGION]
    key = (id(text), len(t))
    got = _WORDS_MEMO.get(key)
    if got is not None and got[0] is text:
        return got[1]
    n = count_words(t)
    if len(_WORDS_MEMO) >= 64:
        _WORDS_MEMO.clear()
    _WORDS_MEMO[key] = (text, n)
    return n


# ------------------------------------------------------------------------------------------------------------------ regions
@dataclass
class Regions:
    """The regions of an answer as written (paragraph indices are 0-based over blank-line paragraphs)."""
    paragraphs: list[str] = field(default_factory=list)
    disclaimer: set[int] = field(default_factory=set)
    model: list[int] = field(default_factory=list)
    headline: str = ""
    byline: str = ""
    greeting: list[str] = field(default_factory=list)
    closing: list[str] = field(default_factory=list)
    model_text: str = ""
    body_text: str = ""
    inline_models: list[str] = field(default_factory=list)
    meta: list[int] = field(default_factory=list)
    student_text: Optional[str] = None
    spanish: bool = False


_DISCLAIMER_RE = re.compile(r"\b(?:practi[cs]e|practicar|pr[aá]ctica|fictional|ficti(?:ci)?[oa]s?|invented|inventad[oa]s?|imaginari[oa]s?|made[- ]up)\b", re.IGNORECASE)
_ITALIC_RE = re.compile(r"^\s*+[*_][^*_\n].{0,600}[*_]\s*+$", re.DOTALL)
_INLINE_MODEL_RE = re.compile(r"^[ \t]*+(?:\*\*)?(?:model|modelo|example|ejemplo|level[- ]up)\b[^:\n]{0,120}:[ \t]*+(?:\*\*)?[ \t]*+[\"“«](?P<q>[^\"”»\n]{3,600})[\"”»]",
                              re.IGNORECASE | re.MULTILINE)
_META_OPEN_RE = re.compile(r"^\s*+(?:\**)(?:word\s*count|recuento|next\s+step|sources?|note|nota|assumptions?|i\s+have\s+assumed|level|nivel)\b", re.IGNORECASE)


def _is_english(para: str) -> bool:
    en, sp, n = es.english_ratio(para)
    return en >= 2 and en > sp


def _target(para: str, spanish: bool) -> bool:
    """A paragraph of the target language: Spanish when the answer is Spanish, else any paragraph that is not English."""
    if _META_OPEN_RE.match(para):
        return False
    if spanish:
        en, sp, n = es.english_ratio(para)
        return en <= sp and (es.is_spanish(para) or (sp >= 3 and sp * 4 >= n) or (("¿" in para or "¡" in para) and sp >= 2) or (n and sp * 6 >= n and n >= 12))
    en, sp, n = es.english_ratio(para)
    return n >= 8 and en * 10 < n


def _short_part(para: str) -> bool:
    """A short paragraph that may be a model's headline, byline, greeting or closing (absorbed when it touches the model)."""
    lines = [x for x in para.split("\n") if x.strip()]
    return 0 < len(lines) <= 3 and len(para.split()) <= 20 and not _META_OPEN_RE.match(para) and not _is_english(para)


def model_regions(text: str, *, task: str = "notes", supplied: tuple = (), request_text: Optional[str] = None, spanish_context: bool = False) -> Regions:
    """The regions of ``text`` (the module docstring). One pass over its paragraphs; a headline or byline test reads a first line only."""
    r = Regions()
    r.paragraphs = [p.strip() for p in _PARA_RE.split((text or "")[:MAX_TEXT]) if p.strip()][:2000]
    r.spanish = spanish_context or es.is_spanish(text)
    for i, p in enumerate(r.paragraphs[:3]):
        if _ITALIC_RE.match(p) and _DISCLAIMER_RE.search(p) and len(p) < 600:
            r.disclaimer.add(i)
    for m in _INLINE_MODEL_RE.finditer((text or "")[:MAX_TEXT]):
        r.inline_models.append(m.group("q"))
        if len(r.inline_models) >= 16:
            break
    if task == "marking":
        r.student_text = _student_text(supplied, request_text)
    if task in ("writing",) or (task == "notes" and r.spanish):
        flags = [(i not in r.disclaimer) and _target(p, r.spanish) for i, p in enumerate(r.paragraphs)]
        best: tuple[int, int] = (0, -1)
        i = 0
        while i < len(flags):
            if not flags[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(flags) and flags[j + 1]:
                j += 1
            if j - i > best[1] - best[0] or best[1] < 0:
                best = (i, j)
            i = j + 1
        if best[1] >= 0:
            lo, hi = best
            while lo - 1 >= 0 and lo - 1 not in r.disclaimer and _short_part(r.paragraphs[lo - 1]):
                lo -= 1
            while hi + 1 < len(r.paragraphs) and _short_part(r.paragraphs[hi + 1]):
                hi += 1
            model = list(range(lo, hi + 1))
            if sum(len(r.paragraphs[k].split()) for k in model) >= 40 and (task == "writing" or len(model) >= 2):
                r.model = model
    in_model = set(r.model)
    r.meta = [i for i in range(len(r.paragraphs)) if i not in in_model and i not in r.disclaimer]
    if r.model:
        lines = [ln for k in r.model for ln in r.paragraphs[k].split("\n") if ln.strip()]
        body: list[str] = []
        for n, ln in enumerate(lines):
            s = ln.strip()
            if n == 0 and len(s.split()) <= 14 and not s.endswith(".") and not es.greeting_line(s) and not es.byline(s):
                r.headline = s
            elif not r.byline and n <= 2 and es.byline(s):
                r.byline = s
            elif es.greeting_line(s) or es.header_line(s):
                r.greeting.append(s)
            elif es.closing_line(s):
                r.closing.append(s)
            elif r.closing and len(s.split()) <= 4 and n == len(lines) - 1:
                r.closing.append(s)  # the signature after the closing formula
            else:
                body.append(s)
        r.model_text = "\n\n".join(r.paragraphs[k] for k in r.model)
        r.body_text = "\n".join(body)
    return r


def _student_text(supplied: tuple, request_text: Optional[str]) -> Optional[str]:
    """The one supplied text the student wrote (author 'Student', a title 'My ...', or the request's 'my email / my text / pasted below'),
    or None when there is not exactly one."""
    docs = [t for t in supplied if not (t.document_id or "").startswith("peer:")]
    own = [t for t in docs if (t.author or "").strip().casefold() in ("student", "the student", "me") or (t.title or "").strip().casefold().startswith(("my ", "mi "))]
    if len(own) == 1:
        return own[0].text or ""
    if len(docs) == 1 and re.search(r"\b(?:my\s+(?:email|e-mail|text|essay|letter|article|draft|writing|composition)|pasted\s+below|mi\s+(?:texto|correo|redacción))\b",
                                    (request_text or "")[:MAX_REQUEST], re.IGNORECASE):
        return docs[0].text or ""
    return None


# ------------------------------------------------------------------------------------------------------------------ task
_WRITING_REQUEST_RE = re.compile(r"\b(?:escrib[ea]|redact[ae])\s+(?:un|una)\b|\bwrite\s+(?:the\s+full\s+|a\s+full\s+|a\s+|an\s+)?(?:model\s+)?(?:formal\s+|informal\s+)?"
                                 r"(?:letter|email|e-mail|article|blog|diary|speech|leaflet|report|interview|review|proposal|text|model)\b", re.IGNORECASE)
_MARKING_REQUEST_RE = re.compile(r"\b(?:mark|grade|correct|assess|give\s+(?:me\s+)?feedback\s+on|corrige|corrígeme|evalúa)\b", re.IGNORECASE)
_READING_REQUEST_RE = re.compile(r"\bread\s+the\s+(?:article|text|passage|extract)\b|\bseg[uú]n\s+el\s+texto\b|\bindica\b|¿verdadero\s+o\s+falso\?|\bverdaderas?\s+\(V\)", re.IGNORECASE)


def classify_task(report: SpecialistReport, request_text: Optional[str]) -> str:
    """``writing``, ``marking``, ``reading`` or ``notes`` (design section 6.2): by the task type first, then by the request."""
    tt = (report.task_type or "").casefold()
    if tt in ("marking_feedback", "feedback", "marking"):
        return "marking"
    if tt in ("reading_comprehension", "reading"):
        return "reading"
    if tt in ("writing_task", "writing"):
        return "writing"
    req = (request_text or "")[:MAX_REQUEST]
    if _MARKING_REQUEST_RE.search(req) and _student_text(tuple(report.supplied_texts), req) is not None:
        return "marking"
    if report.supplied_texts and _READING_REQUEST_RE.search(req):
        return "reading"
    if _WRITING_REQUEST_RE.search(req) and tt not in ("language_notes", "notes"):
        return "writing"
    return "notes"


def _spanish_context(report: SpecialistReport) -> bool:
    label = f"{report.subject or ''} {report.agent_id or ''}".casefold()
    return "spanish" in label or "español" in label or "espanol" in label


# ------------------------------------------------------------------------------------------------------------------ statements
@dataclass(frozen=True)
class _Stmt:
    paragraph: int
    text: str
    line_start: int     # offset of the statement in the answer (for 'nearest before')


def _statements(r: Regions, text: str) -> list[_Stmt]:
    """The sentences of the meta regions (every paragraph outside the model and the disclaimer), line by line, each split with the shared
    splitter. Bounded."""
    from ..adapters.history_specialist.sentences import split_sentences
    out: list[_Stmt] = []
    pos = 0
    for i, para in enumerate(r.paragraphs):
        at = text.find(para[:80], pos) if para else -1
        base = at if at >= 0 else pos
        pos = base + len(para) if at >= 0 else pos
        if i not in r.meta:
            continue
        offset = 0
        for line in para.split("\n"):
            for sent in split_sentences(line):
                s = sent.strip()
                if s:
                    out.append(_Stmt(i, s, base + offset + max(0, line.find(s[:40]))))
                    if len(out) >= 4000:
                        return out
            offset += len(line) + 1
    return out


# ------------------------------------------------------------------------------------------------------------------ checks
_APPROX_WORDS = r"about|approximately|approx\.|around|roughly|some|nearly|almost|unas|unos|alrededor\s+de|aproximadamente|cerca\s+de|casi"
_WC_LABEL_RE = re.compile(r"\b(?:word\s*count|words?\s+used|length)\s*+[:=]\s*+|\brecuento(?:\s+de\s+palabras)?\s*+:\s*+", re.IGNORECASE)
_WC_NUMBER_RE = re.compile(r"(?:(?P<approx>" + _APPROX_WORDS + r")\s+)?(?<![\d.,–—-])(?P<n>\d{1,2}(?:[,.]\d{3})|\d{1,5})(?![\d,.]\d|\d|\s*+[–—-]\s*+\d|\s*+(?:to|y|and|a)\s+\d)"
                            r"(?P<after>[^,;()\n]{0,60})", re.IGNORECASE)
_PROD = (r"(?P<prod>your\s+(?:email|e-mail|text|draft|composition|essay|letter|article|piece|answer|writing|redacción|correo|blog(?:\s+post)?|speech|diary\s+entry)"
         r"|(?:the|this|my)\s+(?:model(?:\s+(?:text|article|answer|email|letter))?|text|article|email|e-mail|letter|speech|blog(?:\s+post)?|piece|draft|composition|answer)"
         r"|tu\s+(?:texto|correo|redacción|carta|artículo)|el\s+(?:texto|modelo|correo|artículo))")
_PROD_COUNT_RE = re.compile(_PROD + r"\s+(?:is|was|has|comes\s+to|runs\s+to|contains|tiene|es\s+de)\s+(?:(?P<approx>" + _APPROX_WORDS + r")\s+)?(?P<n>\d{1,5})\s+(?:words|palabras)\b",
                            re.IGNORECASE)
_PAREN_COUNT_RE = re.compile(r"\((?:(?P<approx>" + _APPROX_WORDS + r"|aprox\.)\s+)?(?P<n>\d{1,5})\s+(?:words|palabras)\)", re.IGNORECASE)
_WHOLE_RE = re.compile(r"\b(?:including|with|incl\.?|counting)\s+(?:the\s+)?(?:headline|title|byline|heading|greeting|signature)|\bincluyendo\s+(?:el\s+)?t[ií]tulo", re.IGNORECASE)
_BODY_RE = re.compile(r"\b(?:in|of)\s+the\s+(?:body|main\s+text)\b|\bbody\b|\bexcluding\s+(?:the\s+)?(?:headline|title|byline)\b|\bsin\s+(?:el\s+)?t[ií]tulo", re.IGNORECASE)
_RANGE_RE = re.compile(r"(?<![\d.,])(?P<lo>\d{2,4})\s*+(?:[–—-]|to)\s*+(?P<hi>\d{2,4})(?![\d.,]\d)|\bbetween\s+(?P<lo2>\d{2,4})\s+and\s+(?P<hi2>\d{2,4})\s+words\b"
                       r"|\bentre\s+(?P<lo3>\d{2,4})\s+y\s+(?P<hi3>\d{2,4})\s+palabras\b", re.IGNORECASE)
#: A bound written in words ("de 450 a 600", "entre 450 y 600", "between 450 and 600", "from 450 to 600"): its figures are the
#: limits of a range, never a stated count (attack round 6: the lower bound was read as the count).
_BOUND_BEFORE_RE = re.compile(r"\b(?:de|del|entre|between|from)\s*+$", re.IGNORECASE)
_RANGE_WORDS_RE = re.compile(r"\s*+(?:-?\s*+word|words|palabras|range|limit|band)\b", re.IGNORECASE)
_IN_RANGE_RE = re.compile(r"\b(?:inside|within)\s+(?:the\s+)?(?:\d{2,4}\s*+[–—-]\s*+\d{2,4}|range|limit|band|bounds?|word\s+(?:range|limit))"
                          r"|\b(?:is|are|lies|falls|sits|stays|comes\s+in)\s+(?:well\s+|comfortably\s+|safely\s+|just\s+)?(?:inside|within)\b"
                          r"|\b(?:the\s+)?length\s+is\s+(?:right|fine|correct|appropriate|ok|okay|good|spot\s+on)\b"
                          r"|\b(?:est[aá]|queda)\s+dentro\s+del?\s+(?:l[ií]mite|rango)", re.IGNORECASE)
_OUT_RANGE_RE = re.compile(r"\b(?:outside|exceeds?|too\s+long|too\s+short|over\s+the\s+(?:limit|maximum)|under\s+the\s+minimum|below\s+the\s+minimum|fuera\s+del?\s+l[ií]mite)\b",
                           re.IGNORECASE)
_LEVEL_RE = re.compile(r"\b(?P<l>SL|HL|NM|NS)\b|\b(?P<w>standard|higher)\s+level\b|\bnivel\s+(?P<e>medio|superior)\b", re.IGNORECASE)
_PAPER1_RE = re.compile(r"\bpaper\s*+1\b|\bprueba\s*+1\b|\bwriting\b|\bescrib[ea]\b|\bredact[ae]\b", re.IGNORECASE)


@dataclass
class _Ctx:
    report: SpecialistReport
    request_text: str
    task: str
    regions: Regions
    text: str
    checks: list = field(default_factory=list)
    #: checks the bound left unbuilt, by kind (attack round 3: named on the receipt by :func:`_bound_finding`, never silent)
    dropped: dict = field(default_factory=dict)
    #: the productions and their folded forms and marker counts, computed once per build (attack round 3: the address-form
    #: reader rebuilt them per statement, statements x answer length)
    memo: dict = field(default_factory=dict)

    def add(self, kind: str, build) -> None:
        if len(self.checks) >= MAX_CHECKS:
            self.dropped[kind] = self.dropped.get(kind, 0) + 1
            return
        n = sum(1 for c in self.checks if c.kind == kind) + 1
        self.checks.append(build(f"language-b-{kind.replace('lb_', '').replace('_', '-')}-{n}"))

    def claims(self, statement: str, phrase: str) -> tuple[str, ...]:
        from .geography import _claims
        return _claims(self.report, statement, phrase)


def _production(ctx: _Ctx, sentence: str, which: str = "default") -> list[tuple[str, str]]:
    """The production(s) a statement is about: ``[(name, text)]``; two entries when the statement leaves two readings open (the model with
    or without its headline and byline)."""
    r = ctx.regions
    m = re.search(_PROD, sentence, re.IGNORECASE)
    prod = (m.group("prod").casefold() if m else "")
    if ctx.task == "marking":
        if r.student_text is not None and (not prod or prod.startswith(("your", "tu", "the email", "the text", "the letter", "the draft", "the e-mail"))):
            return [("the student's text", r.student_text)]
        return []
    # the rest depends on ``which`` alone: computed once per build (attack round 3: rebuilt per statement, statements x answer length)
    key = ("production", which)
    hit = ctx.memo.get(key)
    if hit is None:
        hit = ctx.memo[key] = _production_of(ctx, which)
    return list(hit)


def _production_of(ctx: _Ctx, which: str) -> list[tuple[str, str]]:
    r = ctx.regions
    if not r.model:
        if ctx.task in ("reading", "notes") and r.paragraphs:
            # no production but the answer itself: the answer without its meta paragraphs (word count, next step, sources, notes), or the
            # whole answer; two readings, so a failure is only a warning
            body = "\n\n".join(p for p in r.paragraphs if not _META_OPEN_RE.match(p))
            whole = "\n\n".join(r.paragraphs)
            return [("the answer without its notes", body), ("the whole answer", whole)]
        return []
    whole = r.model_text
    body = r.body_text or whole
    if which == "whole":
        return [("the model with its headline and byline", whole)]
    if which == "body":
        return [("the model's body", body)]
    if _words(whole) == _words(body):
        return [("the model", whole)]
    return [("the model with its headline and byline", whole), ("the model's body", body)]


def _tolerance(n: int, approx: bool) -> Fraction:
    return Fraction(n, 10) if approx else max(Fraction(5), Fraction(n, 50))


_COUNT_WORDS_RE = re.compile(r"(?:(?P<approx>" + _APPROX_WORDS + r")\s+)?(?P<w>[^\W\d_][^\W\d_ ]*(?:\s+(?:y\s+)?[^\W\d_]+){0,5}?)\s+"
                             r"(?P<u>palabras|words)\b", re.IGNORECASE)


def _word_count_in_words(s: str, at: int) -> list[tuple[int, bool, str, "re.Match[str]"]]:
    """A word count written in Spanish number words right after a word-count label, as :func:`_word_counts` reads digits."""
    m = _COUNT_WORDS_RE.search(s, at, min(len(s), at + 120))
    if m is None:
        return []
    figs = es.spanish_number_figures(m.group("w"))
    if len(figs) != 1:
        return []
    value = int(Fraction(figs[0][2]))
    if value <= 0:
        return []
    after = s[m.end():m.end() + 60]
    which = "whole" if _WHOLE_RE.search(after) else "body" if _BODY_RE.search(after) else "default"
    return [(value, bool(m.group("approx")), which, m)]


def _word_counts(ctx: _Ctx, st: _Stmt) -> list[tuple[int, bool, str, "re.Match[str]"]]:
    """``(stated count, approximate, which production ('whole', 'body', 'default'), match)`` of the word counts a statement gives."""
    out = []
    s = st.text
    lab = _WC_LABEL_RE.search(s)
    if lab is not None:
        first = True
        for m in _WC_NUMBER_RE.finditer(s, lab.end()):
            after = m.group("after") or ""
            if _RANGE_RE.match(s, m.start("n")) or _BOUND_BEFORE_RE.search(s[max(0, m.start("n") - 10):m.start("n")]) and \
                    re.match(r"\s*+(?:a|y|and|to|[–—-])\s*+\d", s[m.end("n"):m.end("n") + 8], re.IGNORECASE):
                continue
            if re.search(r"(?:\b(?:a|y|and|to)|[–—-])\s*+$", s[max(0, m.start("n") - 5):m.start("n")]) and \
                    _BOUND_BEFORE_RE.search(s[max(0, m.start("n") - 24):m.start("n")].rsplit(" ", 3)[0] + " "):
                continue  # the upper bound of "de 450 a 600"
            n = int(m.group("n").replace(",", "").replace(".", ""))
            if 1000 <= n <= 2100 and not re.match(r"\s*+(?:words|palabras)", after, re.IGNORECASE):
                continue  # a year, not a count
            tagged = re.match(r"\s*+(?:words|palabras)\b", after, re.IGNORECASE) or _WHOLE_RE.search(after) or _BODY_RE.search(after)
            if not (first or tagged):
                continue
            which = "whole" if _WHOLE_RE.search(after) else "body" if _BODY_RE.search(after) else "default"
            out.append((n, bool(m.group("approx")), which, m))
            first = False
            if len(out) >= 4:
                break
        if not out:
            # a count written in number words after the label ("Recuento: unas cuatrocientas palabras", "Word count: about four hundred
            # words": attack round 5), read with the words that follow it
            out = _word_count_in_words(s, lab.end())
        return out
    for rx in (_PROD_COUNT_RE, _PAREN_COUNT_RE):
        for m in rx.finditer(s):
            after = s[m.end():m.end() + 60]
            which = "whole" if _WHOLE_RE.search(after) else "body" if _BODY_RE.search(after) else "default"
            out.append((int(m.group("n")), bool(m.group("approx")), which, m))
    return out[:4]


def _count_problem(ctx: _Ctx, st: _Stmt, n: int, approx: bool, prods: list[tuple[str, str]], phrase: str) -> None:
    tol = _tolerance(n, approx)
    measured = [(name, _words(t)) for name, t in prods]
    options = [{"op": "and", "args": [{"op": "ge", "left": _var(f"m{k + 1}"), "right": _real(Fraction(n) - tol)},
                                      {"op": "le", "left": _var(f"m{k + 1}"), "right": _real(Fraction(n) + tol)}]} for k in range(len(measured))]
    unique = len(measured) == 1
    inputs = [(f"m{k + 1}", Fraction(c), f"the words of {name}, counted as the channel counts them ({c})") for k, (name, c) in enumerate(measured)]
    rule = "within 10% (an approximate count)" if approx else "within 5 words or 2%, whichever is larger"
    ctx.add("lb_word_count", lambda cid: make_check(
        ctx.report, check_id=cid, kind="lb_word_count", inputs=inputs, conclusion=options[0] if unique else {"op": "or", "args": options},
        label=f"stated count {'about ' if approx else ''}{n} words against {' or '.join(f'{nm} ({c})' for nm, c in measured)}",
        description=(f"{st.text[:220]} [a word count stated about a production equals the measured count {rule}"
                     f"{'' if unique else '; the statement leaves two productions open, so either one holding is enough'}]"),
        claim_ids=ctx.claims(st.text, phrase), severity="error" if unique else "warning", defect="invented_figure"))


def _range_for(ctx: _Ctx, st: _Stmt, near: Optional["re.Match[str]"]) -> Optional[tuple[int, int, str]]:
    if near is not None:
        lo, hi = _range_values(near)
        return lo, hi, "the range the statement states"
    before = ctx.text[max(0, st.line_start - 4000):st.line_start]
    last = None
    for m in _RANGE_RE.finditer(before):
        if m.group("lo") is None or _RANGE_WORDS_RE.match(before, m.end()):
            last = m
    if last is not None:
        lo, hi = _range_values(last)
        return lo, hi, "the range the answer states before it"
    from ..channel.request_parser import extract_constraints
    cs = extract_constraints(ctx.request_text)
    mins = [int(c.value) for c in cs if c.kind == "min_words" and c.value]
    maxs = [int(c.value) for c in cs if c.kind == "max_words" and c.value]
    if mins and maxs:
        return min(mins), max(maxs), "the request's word bound"
    level = _level(ctx.request_text)
    if level:
        lo, hi = COURSE_RANGES[level]
        return lo, hi, f"the course convention for {level} (a working rule, not a bound the request set)"
    return None


def _range_values(m: "re.Match[str]") -> tuple[int, int]:
    for a, b in (("lo", "hi"), ("lo2", "hi2"), ("lo3", "hi3")):
        if m.group(a):
            return int(m.group(a)), int(m.group(b))
    raise ValueError("no range")


def _level(request_text: str) -> Optional[str]:
    m = _LEVEL_RE.search(request_text or "")
    if m is None:
        return None
    w = (m.group("l") or m.group("w") or m.group("e") or "").casefold()
    return "HL" if w in ("hl", "ns", "higher", "superior") else "SL"


def _word_checks(ctx: _Ctx, statements: list[_Stmt]) -> None:
    for st in statements:
        counts = _word_counts(ctx, st)
        first_prods = None
        for n, approx, which, m in counts:
            prods = _production(ctx, st.text, which)
            if not prods:
                continue
            first_prods = first_prods or prods
            _count_problem(ctx, st, n, approx, prods, m.group(0))
        in_range, out_range = _IN_RANGE_RE.search(st.text), _OUT_RANGE_RE.search(st.text)
        if not (in_range or out_range):
            continue
        if not counts and not re.search(_PROD + r"|\bthe\s+length\b|\bit\s+(?:is|lies|falls|sits|stays)\b", st.text, re.IGNORECASE):
            continue
        prods = first_prods or _production(ctx, st.text)
        if not prods:
            continue
        near = None
        for rm in _RANGE_RE.finditer(st.text):
            if rm.group("lo") is None or (in_range and abs(rm.start() - in_range.start()) < 40) or _RANGE_WORDS_RE.match(st.text, rm.end()):
                near = rm
        rng = _range_for(ctx, st, near)
        if rng is None:
            continue
        lo, hi, where = rng
        negated = out_range is not None and in_range is None
        measured = [(name, _words(t)) for name, t in prods]
        inside = [{"op": "and", "args": [{"op": "ge", "left": _var(f"m{k + 1}"), "right": _real(Fraction(lo))},
                                         {"op": "le", "left": _var(f"m{k + 1}"), "right": _real(Fraction(hi))}]} for k in range(len(measured))]
        concl = inside[0] if len(inside) == 1 else {"op": "or", "args": inside}
        if negated:
            concl = {"op": "not", "arg": concl}
        unique = len(measured) == 1
        inputs = [(f"m{k + 1}", Fraction(c), f"the words of {name}, counted as the channel counts them ({c})") for k, (name, c) in enumerate(measured)]
        phrase = (in_range or out_range).group(0)
        ctx.add("lb_word_range_claim", lambda cid, inputs=inputs, concl=concl, lo=lo, hi=hi, where=where, negated=negated, measured=measured, unique=unique, st=st, phrase=phrase:
                make_check(ctx.report, check_id=cid, kind="lb_word_range_claim", inputs=inputs, conclusion=concl,
                           label=f"{' or '.join(nm for nm, _ in measured)} {'outside' if negated else 'inside'} {lo}-{hi} words ({where})",
                           description=f"{st.text[:220]} [a production said to lie {'outside' if negated else 'inside'} a word range: {lo}-{hi}, {where}]",
                           claim_ids=ctx.claims(st.text, phrase), severity="error" if unique else "warning", defect="invented_figure"))


def _course_range(ctx: _Ctx) -> None:
    from ..channel.request_parser import extract_constraints
    r = ctx.regions
    if ctx.task != "writing" or not r.model:
        return
    req = ctx.request_text
    level = _level(req)
    if level is None or not _PAPER1_RE.search(req):
        return
    if any(c.kind in ("min_words", "max_words") for c in extract_constraints(req)):
        return  # the channel checks the request's own bound
    lo, hi = COURSE_RANGES[level]
    m = _words(r.model_text)
    ctx.add("lb_course_word_range", lambda cid: make_check(
        ctx.report, check_id=cid, kind="lb_course_word_range", inputs=[("m1", Fraction(m), f"the words of the model, counted as the channel counts them ({m})")],
        conclusion={"op": "and", "args": [{"op": "ge", "left": _var("m1"), "right": _real(Fraction(lo))}, {"op": "le", "left": _var("m1"), "right": _real(Fraction(hi))}]},
        label=f"the model within {lo}-{hi} words ({level} Paper 1)",
        description=(f"the model text against the {level} Paper 1 range of {lo}-{hi} words: a course convention (working rule), not a bound the request set "
                     "[the request states the level and the paper but no word bound]"),
        claim_ids=(), severity="warning"))


_MODEL_REF_RE = re.compile(r"\b(?:the|my|this|our)\s+(?:model(?:\s+(?:text|article|answer|email|letter|sentence))?|article|sample(?:\s+text)?)\s+"
                           r"(?:uses?|used|includes?|included|contains?|has|writes?|wrote|shows?|employs?|features?|address(?:es)?|addressed)\b"
                           r"|\b(?:el\s+(?:modelo|texto\s+modelo|art[ií]culo))\s+(?:usa|utiliza|emplea|incluye|contiene|tiene)\b", re.IGNORECASE)
_ITALIC_FORM_RE = re.compile(r"(?<![*\w])\*(?!\*)([^*\n]{1,80})\*(?!\*)")


def _norm(form: str) -> str:
    f = form.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return " ".join(f.casefold().split())


def _occurs(form: str, text: str) -> int:
    """How often ``form`` occurs in ``text`` (case folded, typographic quotes unified, diacritics kept); a form with an ellipsis occurs when
    its parts occur in order. A ``str.find`` loop: k forms by n characters with k bounded."""
    parts = [p for p in re.split(r"\s*+(?:\.\.\.|…)\s*+", _norm(form)) if p]
    hay = _norm(text[:MAX_REGION])
    if not parts:
        return 0
    count, pos = 0, 0
    while count < 64:
        start = hay.find(parts[0], pos)
        if start < 0:
            break
        end = start + len(parts[0])
        ok = True
        for p in parts[1:]:
            k = hay.find(p, end)
            if k < 0:
                ok = False
                break
            end = k + len(p)
        if not ok:
            break
        count += 1
        pos = start + 1
    return count


def _quoted_forms(ctx: _Ctx, statements: list[_Stmt]) -> None:
    from ..adapters.markdown import find_quotation_spans
    r = ctx.regions
    if not r.model and not r.inline_models:
        return
    seen = 0
    for st in statements:
        m = _MODEL_REF_RE.search(st.text)
        if m is None:
            continue
        sentence_ref = "sentence" in m.group(0).casefold()
        target = ("the inline model", "\n".join(r.inline_models)) if (sentence_ref or not r.model) and r.inline_models else ("the model", r.model_text)
        forms = [q for _a, _b, q in find_quotation_spans(st.text, min_single_words=1) if 0 < len(q) <= MAX_FORM_CHARS]
        forms += [x.group(1) for x in _ITALIC_FORM_RE.finditer(st.text) if len(x.group(1)) <= MAX_FORM_CHARS]
        forms = list(dict.fromkeys(forms))[:MAX_FORMS - seen]
        if not forms:
            continue
        seen += len(forms)
        counts = [(f, _occurs(f, target[1])) for f in forms]
        inputs = [(f"f{k + 1}", Fraction(c), f"occurrences of «{f[:80]}» in {target[0]} ({c})") for k, (f, c) in enumerate(counts)]
        concl = {"op": "and", "args": [{"op": "ge", "left": _var(f"f{k + 1}"), "right": _real(Fraction(1))} for k in range(len(counts))]} if len(counts) > 1 else \
            {"op": "ge", "left": _var("f1"), "right": _real(Fraction(1))}
        ctx.add("lb_quoted_form", lambda cid, inputs=inputs, concl=concl, counts=counts, target=target, st=st, m=m: make_check(
            ctx.report, check_id=cid, kind="lb_quoted_form", inputs=inputs, conclusion=concl,
            label=f"{target[0]} contains {', '.join('«' + f[:60] + '»' for f, _ in counts)}",
            description=f"{st.text[:220]} [a form the answer says {target[0]} contains occurs in it at least once (case folded, diacritics kept)]",
            claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="altered_quotation"))
        if seen >= MAX_FORMS:
            return


_ADDRESS_CLAIM_RE = re.compile(r"\b(?:you|your\s+(?:email|e-mail|text|letter|draft)|the\s+(?:model|email|e-mail|letter|text|article|speech)|tu\s+(?:texto|correo|carta)|el\s+(?:modelo|correo|texto))"
                               r"\b[^.;\n]{0,60}?\b(?:write|writes|wrote|use|uses|used|keep|keeps|kept|address|addresses|addressed|employ|employs|mix|mixes|mixed|switch|switches|"
                               r"usa|utiliza|mezcla|emplea|tutea|mantiene)\b", re.IGNORECASE)
_HYPOTHETICAL_RE = re.compile(r"\b(?:would|could|should|might|may|can|if|debería|podría|deberías|podrías)\b", re.IGNORECASE)
_CONSISTENT_RE = re.compile(r"\b(?:consistently|throughout|all\s+the\s+way|from\s+first\s+line\s+to\s+last|en\s+todo\s+el\s+texto|siempre|de\s+principio\s+a\s+fin)\b", re.IGNORECASE)
_BACKREF_RE = re.compile(r"\b(?:it|them|this|these|that\s+form|those\s+forms|this\s+form)\b", re.IGNORECASE)


def _memo(ctx: _Ctx, key: tuple, compute):
    """``compute()`` once per build for ``key`` (the production's text is one object per build, so its hash is computed once)."""
    if key not in ctx.memo:
        ctx.memo[key] = compute()
    return ctx.memo[key]


def _address_checks(ctx: _Ctx, statements: list[_Stmt]) -> None:
    from ..adapters.markdown import find_quotation_spans
    if not (ctx.regions.spanish or _spanish_context(ctx.report)):
        return
    previous: Optional[tuple[str, int]] = None
    for st in statements:
        names = [es.address_name(x.group("f")) for x in es.ADDRESS_NAME_RE.finditer(st.text)]
        names = [n for n in names if n]
        claim = _ADDRESS_CLAIM_RE.search(st.text)
        consistent = _CONSISTENT_RE.search(st.text)
        form = None
        if claim and len(set(names)) == 1 and not _HYPOTHETICAL_RE.search(st.text[:claim.end()]):
            form = names[0]
        elif claim and not names and consistent and _BACKREF_RE.search(st.text) and previous and previous[1] == st.paragraph:
            form = previous[0]
        if form is None:
            previous = None if names else previous
            continue
        previous = (form, st.paragraph)
        prods = _production(ctx, st.text)
        if len(prods) > 1:
            prods = prods[:1]
        examples = [q for _a, _b, q in find_quotation_spans(st.text, min_single_words=1) if 0 < len(q) <= MAX_FORM_CHARS][:8] if names else []
        inputs: list[tuple[str, Fraction, str]] = []
        parts: list[dict] = []
        prod_fold = _memo(ctx, ("fold", prods[0][1]), lambda: " ".join(prods[0][1].casefold().split())) if prods else ""
        for k, ex in enumerate(examples):
            c = len(es.address_markers(ex, form))
            inputs.append((f"e{k + 1}", Fraction(c), f"unambiguous {form} markers in «{ex[:60]}» ({c})"))
            parts.append({"op": "ge", "left": _var(f"e{k + 1}"), "right": _real(Fraction(1))})
            if prods:
                # the example must be the production's own words: an example found nowhere in it proves nothing about it
                ex_fold = " ".join(ex.casefold().split())
                occ = _memo(ctx, ("occurs", prods[0][1], ex_fold), lambda: 1 if ex_fold in prod_fold else 0)
                inputs.append((f"o{k + 1}", Fraction(occ), f"«{ex[:60]}» occurs in {prods[0][0]} ({'yes' if occ else 'no'})"))
                parts.append({"op": "ge", "left": _var(f"o{k + 1}"), "right": _real(Fraction(1))})
        if prods and examples:
            own = _memo(ctx, ("markers", prods[0][1], form), lambda: len(es.address_markers(prods[0][1], form)))
            inputs.append(("named", Fraction(own), f"unambiguous {form} markers in {prods[0][0]} ({own})"))
            parts.append({"op": "ge", "left": _var("named"), "right": _real(Fraction(1))})
        if consistent and prods:
            other = sum(_memo(ctx, ("markers", prods[0][1], f), lambda f=f: len(es.address_markers(prods[0][1], f))) for f in es.ADDRESS_FORMS if f != form)
            inputs.append(("others", Fraction(other), f"unambiguous markers of the other address forms in {prods[0][0]} ({other})"))
            parts.append({"op": "eq", "left": _var("others"), "right": _real(Fraction(0))})
        if not parts:
            continue
        concl = parts[0] if len(parts) == 1 else {"op": "and", "args": parts}
        ctx.add("lb_address_form", lambda cid, inputs=inputs, concl=concl, form=form, st=st, examples=examples: make_check(
            ctx.report, check_id=cid, kind="lb_address_form", inputs=inputs, conclusion=concl,
            label=f"the production uses {form}" + (f" (examples {', '.join('«' + e[:40] + '»' for e in examples)})" if examples else "") + (" consistently" if consistent else ""),
            description=(f"{st.text[:220]} [an address form named for a production: each example carries an unambiguous marker of it, and 'consistently' means "
                         "no unambiguous marker of another form; su, sus, le, les and third-person verbs are ambiguous and never counted]"),
            claim_ids=ctx.claims(st.text, st.text[:60]), severity="warning"))


_ARROW_LINE_RE = re.compile(r"^[ \t]*+(?:[-*•]|\d{1,2}[.)])?[ \t]*+[«\"“'‘][^\n]{1,300}?[»\"”'’][ \t]*+(?:→|->|=>|⟶)[ \t]*+[«\"“'‘]", re.MULTILINE)
_LISTED_RE = re.compile(r"\b(?:fix|correct|check|review|revise|make|work\s+on|corrige|revisa|repasa)\s+(?:the|these|those|all(?:\s+the)?|los|las|estos|estas)\s+"
                        r"(?P<n>" + _NUMBER_WORD + r"|\d{1,2})\s+(?P<noun>points|corrections|changes|errors|mistakes|fixes|puntos|correcciones|errores|cambios)\b"
                        r"|\b(?:the|these|those|las|los|estas|estos)\s+(?P<n2>" + _NUMBER_WORD + r"|\d{1,2})\s+(?P<noun2>corrections|correcciones)\b", re.IGNORECASE)
#: (up to six words may stand between the noun and the list's colon or bracket: "four connectors to organise the argument: ...", attack
#: round 7)
_CONNECTOR_LIST_RE = re.compile(r"\b(?P<n>" + _NUMBER_WORD + r"|\d{1,2})\s+(?:connectors|conectores|linking\s+words|connectives)"
                                r"(?:\s{1,3}[^\W\d_]{1,20}){0,6}?\s*+(?:\(|:)(?P<rest>[^\n]{0,400})", re.IGNORECASE)


def _listed_counts(ctx: _Ctx, statements: list[_Stmt]) -> None:
    from ..adapters.markdown import find_quotation_spans
    model = set(ctx.regions.model)
    lines = [m.group(0) for m in _ARROW_LINE_RE.finditer(ctx.text[:MAX_TEXT])]
    for st in statements:
        if st.paragraph in model:
            continue
        for m in _LISTED_RE.finditer(st.text):
            if not lines:
                break
            n = _count_value(m.group("n") or m.group("n2"))
            if n is None:
                continue
            listed = len(lines)
            noun = m.group("noun") or m.group("noun2")
            ctx.add("lb_listed_count", lambda cid, n=n, listed=listed, noun=noun, st=st, m=m: make_check(
                ctx.report, check_id=cid, kind="lb_listed_count", inputs=[("listed", Fraction(listed), f"the correction lines the answer lists ({listed})")],
                conclusion={"op": "eq", "left": _var("listed"), "right": _real(Fraction(n))},
                label=f"the {n} {noun} the answer names against the {listed} correction lines it lists",
                description=f"{st.text[:220]} [a count of items the answer lists itself (its 'x' -> 'y' correction lines) equals the number listed]",
                claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="invented_figure"))
        for m in _CONNECTOR_LIST_RE.finditer(st.text):
            n = _count_value(m.group("n"))
            rest = m.group("rest")
            items = [q for _a, _b, q in find_quotation_spans(rest, min_single_words=1)] + [x.group(1) for x in _ITALIC_FORM_RE.finditer(rest)]
            if n is None or not items:
                continue
            listed = len(dict.fromkeys(_norm(x) for x in items))
            ctx.add("lb_listed_count", lambda cid, n=n, listed=listed, st=st, m=m: make_check(
                ctx.report, check_id=cid, kind="lb_listed_count", inputs=[("listed", Fraction(listed), f"the connectors the sentence lists ({listed})")],
                conclusion={"op": "eq", "left": _var("listed"), "right": _real(Fraction(n))},
                label=f"{n} connectors against the {listed} the sentence lists",
                description=f"{st.text[:220]} [a count of the connectors a sentence lists equals the number it lists]",
                claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="invented_figure"))


_ES_NUM = r"\d{1,3}(?:[.   ]\d{3})++(?:,\d{1,6})?|\d{1,3}(?:,\d{3})++|\d{1,12}(?:,\d{1,6})?"
_ES_YEAR = r"(?:1[89]\d{2}|20\d{2})"
#: A change from one figure to another after its verb. Between the verb and the pair: up to four words or a stated per cent ("creció un
#: 36 %, de 212 a 268"); between the two figures: up to three words or a year ("de 212 vecinos en 2015 a 268 personas") (attack round 3).
_ES_FROM_TO_RE = re.compile(r"\b(?:pas(?:ó|a|aron|an)|ha\s+pasado|(?:ha|han)\s+(?:ca[ií]do|bajado|subido|aumentado|crecido|descendido|disminuido)|"
                            r"se\s+ha(?:n)?\s+(?:reducido|duplicado|triplicado)|cay(?:ó|eron)|baj(?:ó|aron)|subi(?:ó|eron)|aument(?:ó|aron)|creci(?:ó|eron)|descendi(?:ó|eron)|"
                            r"disminuy(?:ó|eron)|se\s+redujo|se\s+redujeron|se\s+duplic(?:ó|aron)|se\s+triplic(?:ó|aron))\s+"
                            r"(?:(?:[^\W\d_]{1,20}|(?:" + _ES_NUM + r")\s*+(?:%|por\s+ciento)),?\s+){0,4}?de\s+"
                            r"(?P<a>" + _ES_NUM + r")(?:\s+(?:[^\W\d_]{1,20}|" + _ES_YEAR + r")){0,3}?\s+a\s+(?P<b>" + _ES_NUM + r")(?![\d,.]\d)", re.IGNORECASE)
#: After a from-to pair: the size of the change ("..., es decir, en 1.138 personas", "..., una caída de 1.038 habitantes").
_ES_DIFF_AFTER_RE = re.compile(r"(?:\s+[^\W\d_]{1,20}){0,2}\s*+,?\s*+(?:es\s+decir|o\s+sea|en\s+total)?\s*+,?\s*+"
                               r"(?:en|una?\s+(?:ca[ií]da|bajada|subida|diferencia|p[eé]rdida|aumento|descenso|ganancia)\s+de)\s+"
                               r"(?P<ap>unos\s+|unas\s+|casi\s+|aproximadamente\s+)?(?P<n>" + _ES_NUM + r")(?![\d,.]\d)\s+[^\W\d_]{2,20}", re.IGNORECASE)
_ES_PCT_RE = re.compile(r"(?P<p>" + _ES_NUM + r")\s*+(?:%|por\s+ciento)", re.IGNORECASE)
_FALL_ES = re.compile(r"\b(?:ca[ií]da|descenso|reducci[oó]n|bajada|disminuci[oó]n|p[eé]rdida|baj[oó]|cay[oó]|descendi[oó]|disminuy[oó]|se\s+redujo)\b", re.IGNORECASE)
_RISE_ES = re.compile(r"\b(?:aumento|subida|crecimiento|incremento|alza|subi[oó]|aument[oó]|creci[oó])\b", re.IGNORECASE)
_FOLD_ES = {"la mitad": Fraction(1, 2), "el doble": Fraction(2), "el triple": Fraction(3), "se duplicó": Fraction(2), "se duplicaron": Fraction(2),
            "se triplicó": Fraction(3), "se triplicaron": Fraction(3), "cuatro veces": Fraction(4)}
_FOLD_ES_RE = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in _FOLD_ES) + r")\b", re.IGNORECASE)
_POINT_FLOOR = Fraction(1, 2)
_PCT_TOL = Fraction(1, 20)


def _percent_changes(ctx: _Ctx) -> None:
    from ..adapters.history_specialist.sentences import split_sentences
    if not (ctx.regions.spanish or _spanish_context(ctx.report)):
        return
    for para in ctx.regions.paragraphs:
        if not re.search(r"\d", para):
            continue
        for sent in split_sentences(para):
            en, sp, _n = es.english_ratio(sent)
            if en > sp:
                continue
            for m in _ES_FROM_TO_RE.finditer(sent):
                clause = sent[m.start():m.end() + 120]
                if _YEAR_RE.match(m.group("a")) and _YEAR_RE.match(m.group("b")):
                    continue  # "de 2015 a 2020": a period, read by the dated reader, never a pair of values
                A = es.spanish_numeral_readings(m.group("a").replace(" ", " "), "es")
                B = es.spanish_numeral_readings(m.group("b").replace(" ", " "), "es")
                if not A or not B:
                    continue
                # the stated per cent after the pair, or before it between the verb and the pair ("creció un 36 %, de 212 a 268")
                pct = _ES_PCT_RE.search(clause, m.end() - m.start()) or _ES_PCT_RE.search(clause, 0, m.start("a") - m.start())
                fold = _FOLD_ES_RE.search(sent[max(0, m.start() - 40):m.end() + 80])
                if pct is not None:
                    P = es.spanish_numeral_readings(pct.group("p"), "es")
                    if not P:
                        continue
                    stated = min(P)
                    fall = bool(_FALL_ES.search(clause)) and not _RISE_ES.search(clause[:pct.start()][-40:])
                    signed = -stated if fall else stated
                    options = []
                    for a in sorted(A):
                        for b in sorted(B):
                            if a == 0:
                                continue
                            c = (b - a) / a * 100
                            slack = max(_POINT_FLOOR, abs(c) * _PCT_TOL)
                            options.append({"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _real(c)}, "right": _real(slack)},
                                                                  {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _real(c)}, "right": _real(-slack)}]})
                    if not options:
                        continue
                    what = f"{'caída' if fall else 'aumento'} del {pct.group('p')} %"
                    ctx.add("lb_percent_change", lambda cid, options=options, signed=signed, what=what, sent=sent, m=m: make_check(
                        ctx.report, check_id=cid, kind="lb_percent_change", inputs=[("stated", signed, f"the change stated in per cent ({what})")],
                        conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
                        label=f"stated {what} against (b - a) / a x 100 from {m.group('a')} to {m.group('b')} (every reading of the numerals)",
                        description=(f"{sent[:220]} [a percentage change against its from-to pair: within 5% of the computed change or half a point; "
                                     "a numeral is read every way it can be read and one reading holding is enough]"),
                        claim_ids=ctx.claims(sent, m.group(0)), defect="stem_arithmetic_slip"))
                elif _ES_DIFF_AFTER_RE.match(sent, m.end()):
                    # the size of the change after its pair ("cayó de 1.250 a 212 habitantes, es decir, en 1.138 personas"): the stated
                    # difference equals |b - a| for one reading of the numerals (attack round 4)
                    dm = _ES_DIFF_AFTER_RE.match(sent, m.end())
                    D = es.spanish_numeral_readings(dm.group("n"), "es")
                    if not D:
                        continue
                    tol = Fraction(1, 2) if not dm.group("ap") else None
                    options = []
                    for a in sorted(A):
                        for b in sorted(B):
                            d = abs(b - a)
                            t = tol if tol is not None else max(Fraction(1, 2), d * _PCT_TOL)
                            options.append({"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _real(d)}, "right": _real(t)},
                                                                  {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _real(d)}, "right": _real(-t)}]})
                    stated = min(D)
                    ctx.add("lb_percent_change", lambda cid, options=options, stated=stated, sent=sent, m=m, dm=dm: make_check(
                        ctx.report, check_id=cid, kind="lb_percent_change", inputs=[("stated", stated, f"the size of the change stated ({dm.group('n')})")],
                        conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
                        label=f"stated change {dm.group('n')} against |b - a| from {m.group('a')} to {m.group('b')} (every reading of the numerals)",
                        description=(f"{sent[:220]} [the size of a change stated after its from-to pair equals their difference, within half a unit "
                                     "(5% after 'unos'); a numeral is read every way it can be read and one reading holding is enough]"),
                        claim_ids=ctx.claims(sent, m.group(0)), defect="stem_arithmetic_slip"))
                elif fold is not None:
                    k = _FOLD_ES[" ".join(fold.group(0).casefold().split())]
                    options = [{"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("later"), "right": _real(a * k)}, "right": _real(abs(a * k) * _PCT_TOL)},
                                                      {"op": "ge", "left": {"op": "sub", "left": _var("later"), "right": _real(a * k)}, "right": _real(-abs(a * k) * _PCT_TOL)}]}
                               for a in sorted(A)]
                    for b in sorted(B)[:1]:
                        ctx.add("lb_percent_change", lambda cid, options=options, b=b, sent=sent, m=m, fold=fold, k=k: make_check(
                            ctx.report, check_id=cid, kind="lb_percent_change", inputs=[("later", b, f"the later figure ({m.group('b')})")],
                            conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
                            label=f"'{fold.group(0)}' (x{float(k):g}) from {m.group('a')} to {m.group('b')}",
                            description=f"{sent[:220]} [a fold change against its from-to pair, within 5%; every reading of the numerals]",
                            claim_ids=ctx.claims(sent, m.group(0)), defect="stem_arithmetic_slip"))


# ------------------------------------------------------------------------------------------------------------------ dated series
#: Nouns of one series however the text names it (the population: "1.250 habitantes", "212 vecinos", "268 personas", "la población").
_POPULATION_STEMS = frozenset({"habit", "vecin", "perso", "pobla", "resid"})
_POPULATION_RE = re.compile(r"\b(?:poblaci[oó]n|habitantes|vecinos|personas|residentes)\b", re.IGNORECASE)
_NOW_POINT = r"hoy|la\s+actualidad|ahora"
_PERIOD_RE = re.compile(r"\b(?:entre\s+(?P<p1>" + _ES_YEAR + r")\s+y\s+(?P<p2>" + _ES_YEAR + r"|" + _NOW_POINT + r")|"
                        r"(?:de|desde)\s+(?P<q1>" + _ES_YEAR + r")\s+(?:a|hasta)\s+(?P<q2>" + _ES_YEAR + r"|" + _NOW_POINT + r"))\b", re.IGNORECASE)
_PCT_BOUND_RE = re.compile(r"\b(?P<cmp>m[aá]s|menos)\s+(?:del?|de\s+un)\s*+$", re.IGNORECASE)
_LOSS_RE = re.compile(r"\b(?:perdi[oó]|perdieron)\b", re.IGNORECASE)
_DIFF_RE = re.compile(r"(?<![\d.,])(?P<n>" + _ES_NUM + r")(?![\d,.]\d)\s+(?:[^\W\d_]{1,20}\s+)?(?P<cmp>m[aá]s|menos)\s+que\s+(?:en\s+|l[oa]s\s+de\s+)?"
                      r"(?P<p>" + _ES_YEAR + r"|" + _NOW_POINT + r")\b", re.IGNORECASE)
_DOUBLE_RE = re.compile(r"\b(?P<cmp>m[aá]s\s+del\s+doble|menos\s+de\s+la\s+mitad)\s+(?:que|de)\s+(?:l[oa]s\s+)?(?:(?P<n>" + _ES_NUM + r")(?![\d,.]\d)|"
                        r"(?:[^\W\d_]{1,20}\s+){0,2}?(?:de\s+|en\s+)?(?P<p>" + _ES_YEAR + r"))", re.IGNORECASE)
_PLAIN_NUM_RE = re.compile(r"(?<![\d.,])(?P<n>" + _ES_NUM + r")(?![\d,.]\d)")


def _is_more(word: str) -> bool:
    """Whether a comparative opens with "más" ("más del doble", "56 más que"), not "menos"."""
    return word.casefold().startswith(("más", "mas"))


def _series_key(noun: str) -> str:
    return "population" if noun[:5] in _POPULATION_STEMS else _stem(noun)


def _point(word: Optional[str]) -> Optional[str]:
    if not word:
        return None
    w = " ".join(word.casefold().split())
    return "hoy" if w in ("hoy", "la actualidad", "ahora") else w


def _timeline(ctx: _Ctx) -> dict:
    """The supplied texts' dated figures, by series and point in time (a year, or "hoy" for a figure the text gives for today): only points
    with one value (a point the text gives two values for is left out). Memoised per build."""
    def compute():
        docs = [t for t in ctx.report.supplied_texts if not (t.document_id or "").startswith("peer:") and t.text and es.is_spanish(t.text)]
        if ctx.regions.student_text is not None:
            docs = [t for t in docs if t.text != ctx.regions.student_text]
        seen: dict = {}
        for d in docs:
            for f in _figures(d.text, "es", [], sentence_years=True):
                point = f.year or ("hoy" if any(w in ("hoy", "actualmente", "ahora") for w in f.context[-4:]) else None)
                if point:
                    seen.setdefault(_series_key(f.noun), {}).setdefault(point, set()).add(f.values)
        return {k: {p: next(iter(v)) for p, v in pts.items() if len(v) == 1} for k, pts in seen.items()}
    return _memo(ctx, ("timeline",), compute)


def _within(var: str, value, slack) -> dict:
    return {"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var(var), "right": _real(value)}, "right": _real(slack)},
                                  {"op": "ge", "left": {"op": "sub", "left": _var(var), "right": _real(value)}, "right": _real(-slack)}]}


def _dated_changes(ctx: _Ctx) -> None:
    """Attack round 3 (sp-t14): arithmetic over the supplied text's dated figures that the answer states without its from-to pair: a per
    cent change over a period ("la población bajó un 73 % entre 1960 y 2015"), a difference against a dated figure ("268 personas, 66 más
    que en 2015", "892 menos que en 1960") and a fold comparison ("más del doble que los 212 vecinos de 2015"). A per cent after "más del"
    or "menos del" is a one-sided bound. Decided against every reading of the text's numerals; a series the text gives no single figure for
    at a point is left unread."""
    from ..adapters.history_specialist.sentences import split_sentences
    if not (ctx.regions.spanish or _spanish_context(ctx.report)):
        return
    line = _timeline(ctx)
    if not line:
        return
    r = ctx.regions
    excluded = set(r.model) | set(r.disclaimer)
    for pi, para in enumerate(r.paragraphs):
        if pi in excluded or not re.search(r"\d", para):
            continue
        for sent in split_sentences(para):
            en, sp, _n = es.english_ratio(sent)
            if en > sp or _ES_FROM_TO_RE.search(sent):
                continue
            series = line.get("population") if _POPULATION_RE.search(sent) else None
            if series is None:
                for key, pts in line.items():
                    if key != "population" and re.search(r"\b" + re.escape(key), sent, re.IGNORECASE):
                        series = pts
                        break
            if not series:
                continue
            sev = "error" if es.SPANISH_CREDIT_RE.search(sent) is not None else "warning"
            _dated_percent(ctx, sent, series, sev)
            _dated_differences(ctx, sent, series, sev)
            _period_size(ctx, sent, series, sev)
            _fold_comparisons(ctx, sent, series, sev)


def _dated_percent(ctx: _Ctx, sent: str, series: dict, sev: str) -> None:
    per = _PERIOD_RE.search(sent)
    pct = _ES_PCT_RE.search(sent)
    if per is None or pct is None:
        return
    p1 = _point(per.group("p1") or per.group("q1"))
    p2 = _point(per.group("p2") or per.group("q2"))
    P = es.spanish_numeral_readings(pct.group("p"), "es")
    if p1 not in series or p2 not in series or not P:
        return
    stated = min(P)
    fall = bool(_FALL_ES.search(sent) or _LOSS_RE.search(sent))
    bound = _PCT_BOUND_RE.search(sent[:pct.start()])
    options = []
    for a in sorted(series[p1]):
        for b in sorted(series[p2]):
            if a == 0:
                continue
            c = (b - a) / a * 100
            size = -c if fall else c
            if bound is not None:
                options.append({"op": "gt" if _is_more(bound.group("cmp")) else "lt", "left": _real(size), "right": _var("stated")})
            else:
                options.append(_within("stated", size, max(_POINT_FLOOR, abs(c) * _PCT_TOL)))
    if not options:
        return
    what = f"{bound.group(0).strip() + ' ' if bound else ''}{pct.group('p')} % ({'caída' if fall else 'aumento'}) {per.group(0)}"
    ctx.add("lb_dated_change", lambda cid: make_check(
        ctx.report, check_id=cid, kind="lb_dated_change", inputs=[("stated", stated, f"the change stated in per cent ({what})")],
        conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
        label=f"stated {what} against the supplied text's figures for {p1} and {p2} (every reading of the numerals)",
        description=(f"{sent[:220]} [a percentage change over a period against the supplied text's figures for its two points: within 5% of the "
                     "computed change or half a point; after 'más del' or 'menos del' a one-sided bound]"),
        claim_ids=ctx.claims(sent, per.group(0)), severity=sev, defect="stem_arithmetic_slip"))


#: The size of a change over a period ("Entre 2015 y hoy el pueblo ganó 66 vecinos", "Entre 1960 y 2015 Valdeoca perdió 1.038 habitantes").
_PERIOD_SIZE_RE = re.compile(r"\b(?:gan[oó]|ganaron|perdi[oó]|perdieron|(?:creci[oó]|cay[oó]|aument[oó]|disminuy[oó]|baj[oó]|subi[oó])\s+en)\s+"
                             r"(?P<ap>unos\s+|unas\s+|casi\s+|aproximadamente\s+)?(?P<n>" + _ES_NUM + r")(?![\d,.]\d)\s+(?:[^\W\d_]{2,20})", re.IGNORECASE)


def _period_size(ctx: _Ctx, sent: str, series: dict, sev: str) -> None:
    """Attack round 4 (sp-t14): the size of a change over a period against the supplied text's figures for its two points: |b - a|
    within half a unit (5% after "unos"), every reading of the numerals. A bound ("más de mil") is left to the bound readers."""
    per = _PERIOD_RE.search(sent)
    m = _PERIOD_SIZE_RE.search(sent)
    if per is None or m is None or re.search(r"\b(?:m[aá]s|menos)\s+de\s*+$", sent[:m.start("n")]):
        return
    p1 = _point(per.group("p1") or per.group("q1"))
    p2 = _point(per.group("p2") or per.group("q2"))
    N = es.spanish_numeral_readings(m.group("n"), "es")
    if p1 not in series or p2 not in series or not N:
        return
    options = []
    for a in sorted(series[p1]):
        for b in sorted(series[p2]):
            d = abs(b - a)
            options.append(_within("stated", d, max(Fraction(1, 2), d * _PCT_TOL) if m.group("ap") else Fraction(1, 2)))
    if not options:
        return
    stated = min(N)
    ctx.add("lb_dated_change", lambda cid: make_check(
        ctx.report, check_id=cid, kind="lb_dated_change", inputs=[("stated", stated, f"the size of the change stated ({m.group(0).strip()})")],
        conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
        label=f"stated change {m.group('n')} {per.group(0)} against the supplied text's figures for {p1} and {p2} (every reading of the numerals)",
        description=(f"{sent[:220]} [the size of a change over a period equals the difference of the supplied text's figures for its two "
                     "points, within half a unit (5% after 'unos')]"),
        claim_ids=ctx.claims(sent, m.group(0)), severity=sev, defect="stem_arithmetic_slip"))


def _dated_differences(ctx: _Ctx, sent: str, series: dict, sev: str) -> None:
    base_point = "hoy" if _NOW_RE.search(sent) else None
    for m in _DIFF_RE.finditer(sent):
        ref = _point(m.group("p"))
        base = base_point
        if base is None:
            years = [y for y in re.findall(_ES_YEAR, sent[:m.start()]) if y != ref]
            base = years[-1] if years else None
        N = es.spanish_numeral_readings(m.group("n"), "es")
        if base is None or base == ref or base not in series or ref not in series or not N or _YEAR_RE.match(m.group("n")):
            continue
        more = _is_more(m.group("cmp"))
        options = [_within("stated", (a - b) if more else (b - a), Fraction(1, 2)) for a in sorted(series[base]) for b in sorted(series[ref])]
        n = min(N)
        ctx.add("lb_dated_change", lambda cid, options=options, n=n, m=m, base=base, ref=ref: make_check(
            ctx.report, check_id=cid, kind="lb_dated_change", inputs=[("stated", n, f"the difference stated ({m.group(0)})")],
            conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
            label=f"'{m.group(0)}' against the supplied text's figures for {base} and {ref}",
            description=f"{sent[:220]} [a difference against a dated figure equals the supplied text's figures for the two points, within half a unit]",
            claim_ids=ctx.claims(sent, m.group(0)), severity=sev, defect="stem_arithmetic_slip"))


def _fold_comparisons(ctx: _Ctx, sent: str, series: dict, sev: str) -> None:
    for m in _DOUBLE_RE.finditer(sent):
        before = [x for x in _PLAIN_NUM_RE.finditer(sent[:m.start()]) if not _YEAR_RE.match(x.group("n"))]
        if not before:
            continue
        X = es.spanish_numeral_readings(before[-1].group("n"), "es")
        if m.group("n") and not _YEAR_RE.match(m.group("n")):
            Y = es.spanish_numeral_readings(m.group("n"), "es")
        else:
            yp = m.group("p") or (re.findall(_ES_YEAR, sent[m.end():m.end() + 30]) or [None])[0]
            Y = series.get(_point(yp)) if yp else None
        if not X or not Y:
            continue
        double = _is_more(m.group("cmp"))
        options = [{"op": "gt" if double else "lt", "left": _var("x"), "right": _real(y * 2 if double else y / 2)} for y in sorted(Y)]
        xs = before[-1].group("n")
        ctx.add("lb_dated_change", lambda cid, options=options, x=min(X), m=m, xs=xs: make_check(
            ctx.report, check_id=cid, kind="lb_dated_change", inputs=[("x", x, f"the figure compared ({xs})")],
            conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
            label=f"{xs} is {m.group('cmp')} the figure it is compared with",
            description=f"{sent[:220]} ['más del doble' or 'menos de la mitad' compares two figures: the first exceeds twice, or falls short of half, the second]",
            claim_ids=ctx.claims(sent, m.group(0)), severity=sev, defect="stem_arithmetic_slip"))


# ------------------------------------------------------------------------------------------------------------------ supplied figures
_TOK_RE = re.compile(r"(?P<num>" + _ES_NUM + r")(?![\d,.]\d)|(?P<word>[^\W\d_]{1,40})")
_STOP_NOUNS = frozenset("de del en la el los las por con para que y a o al un una veces por ciento".split())
_CONTEXT_STOP = frozenset("de del en la el los las por con para que y a o al un una se su sus lo le les es son más muy".split())
_YEAR_RE = re.compile(r"^(?:1[89]\d{2}|20\d{2})$")
_NUMBERED_RE = re.compile(r"^\s*+(?:\d{1,2}[.)]|[a-h]\))\s", re.IGNORECASE)


@dataclass(frozen=True)
class _Fig:
    values: frozenset
    shown: str
    noun: str
    year: Optional[str]
    context: tuple[str, ...]
    start: int
    #: the content words after the noun (attack round 3: a figure that opens its sentence, "Quince alumnos volvieron a la escuela", has
    #: no words before it to tell two figures of one noun apart)
    after: tuple = ()
    #: every year near the figure (the nearest is ``year``): "1.250 habitantes en 1960 y 212 vecinos en 2015" puts both years near 212
    near_years: tuple = ()


#: Small Spanish number words read before a plural noun ("tres hijos", "diez viviendas", "once puestos"): the ledger's reader reads them
#: only after a word of quantity, since alone they are also English words or pronouns (attack round 3).
_ES_SMALL_COUNT = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11}
_SENTENCE_END_RE = re.compile(r"[.!?;]\s")


def _figures(text: str, language: Optional[str], skip: list[tuple[int, int]], sentence_years: bool = False) -> list[_Fig]:
    """Figures (numerals and Spanish number words) followed by a noun, with the nearest year (within four tokens) and the four content words
    before them. One token pass; bounded."""
    toks = [(m.start(), m.end(), m.group("num"), m.group("word")) for m in _TOK_RE.finditer(text[:MAX_REGION])][:20000]
    words = {a: (b, v) for a, b, v in es.spanish_number_figures(text[:MAX_REGION])}
    out: list[_Fig] = []
    k = 0
    # the skip spans walked once, in order, with the tokens (a test of every span per token was O(tokens x spans))
    spans = sorted(skip)
    from bisect import bisect_right
    sk_starts = [x for x, _y in spans]
    sk_reach: list[int] = []
    best = -1
    for _x, y in spans:
        best = max(best, y)
        sk_reach.append(best)
    sent_years: dict[int, Optional[str]] = {}
    if language == "es" and sentence_years:
        # (a supplied text only: an answer's figure keeps its own nearby year) the one year of a sentence dates every figure of the sentence that has no year of its own nearby ("En 1960, Valdeoca tenía
        # 1.250 habitantes, dos panaderías y una escuela con más de cien alumnos.")
        starts = [0] + [m.end() for m in _SENTENCE_END_RE.finditer(text[:MAX_REGION])]
        for i, st in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(text)
            ys = set(re.findall(r"(?<!\d)(?:1[89]\d{2}|20\d{2})(?!\d)", text[st:end]))
            sent_years[st] = next(iter(ys)) if len(ys) == 1 else None
        sent_starts = starts
    while k < len(toks) and len(out) < 400:
        a, b, num, word = toks[k]
        j = bisect_right(sk_starts, a) - 1
        if j >= 0 and sk_reach[j] > a:
            k += 1
            continue
        vals, shown, nxt = None, None, k + 1
        if num is not None and not _YEAR_RE.match(num):
            vals = es.spanish_numeral_readings(num, language)
            shown = num
        elif word is not None and a in words:
            end, v = words[a]
            vals = frozenset({Fraction(v)})
            shown = text[a:end]
            while nxt < len(toks) and toks[nxt][0] < end:
                nxt += 1
        elif (word is not None and language == "es" and word.casefold() in _ES_SMALL_COUNT and nxt < len(toks) and toks[nxt][3]
              and toks[nxt][3].casefold().endswith("s") and len(toks[nxt][3]) >= 4 and word[0].islower() == word.islower()):
            vals = frozenset({Fraction(_ES_SMALL_COUNT[word.casefold()])})
            shown = word
        if vals and nxt < len(toks) and toks[nxt][3] and toks[nxt][3].casefold() not in _STOP_NOUNS and len(toks[nxt][3]) >= 4:
            noun = toks[nxt][3].casefold()
            years = [(abs(j - k), toks[j][2]) for j in range(max(0, k - 4), min(len(toks), nxt + 4)) if toks[j][2] and _YEAR_RE.match(toks[j][2])]
            year = min(years)[1] if years else None
            if year is None and sent_years:
                from bisect import bisect_right as _br
                year = sent_years.get(sent_starts[_br(sent_starts, a) - 1])
            ctx_words = tuple(t[3].casefold() for t in toks[max(0, k - 8):k] if t[3] and t[3].casefold() not in _CONTEXT_STOP)
            after = tuple(t[3].casefold() for t in toks[nxt + 1:nxt + 9] if t[3] and t[3].casefold() not in _CONTEXT_STOP)
            out.append(_Fig(vals, shown, noun, year, ctx_words[-6:], a, after[:6], tuple(y for _d, y in years)))
        k = nxt if vals else k + 1
    return out


def _stem(w: str) -> str:
    return w[:5]


def _supplied_figures(ctx: _Ctx) -> None:
    from ..adapters.markdown import find_quotation_spans
    if not (ctx.regions.spanish or _spanish_context(ctx.report)):
        return
    docs = [t for t in ctx.report.supplied_texts if not (t.document_id or "").startswith("peer:") and t.text]
    if not docs:
        return
    if ctx.regions.student_text is not None:
        docs = [t for t in docs if t.text != ctx.regions.student_text] or []
    if not docs:
        return
    index: dict[str, list[tuple[_Fig, str]]] = {}
    # every figure the texts state with no noun of its own (any noun may be its own), and the series each noun-bound figure belongs
    # to: a figure the text states under ANOTHER series is no figure of this one (attack round 3: "doce viviendas" passed because the
    # text has "doce puestos")
    stated_values: set[Fraction] = set()
    stated_series: dict[Fraction, set] = {}
    for d in docs:
        if not es.is_spanish(d.text):
            continue
        figs = _figures(d.text, "es", [], sentence_years=True)
        bound_at = {f.start for f in figs}
        for f in figs:
            index.setdefault(_stem(f.noun), []).append((f, d.document_id))
            for v in f.values:
                stated_series.setdefault(v, set()).add(_series_key(f.noun))
        for m in _TOK_RE.finditer(d.text[:MAX_REGION]):
            if m.group("num") and m.start() not in bound_at:
                stated_values |= es.spanish_numeral_readings(m.group("num"), "es")
        stated_values |= {Fraction(v) for a, _b, v in es.spanish_number_figures(d.text) if a not in bound_at}
    if not index:
        return
    r = ctx.regions
    excluded = set(r.model) | set(r.disclaimer)
    for pi, para in enumerate(r.paragraphs):
        if pi in excluded:
            continue
        for line in para.split("\n"):
            en, sp, _n = es.english_ratio(line)
            if en > sp or not re.search(r"\d|[^\W\d_]", line):
                continue
            if any(q in line for q in r.inline_models):
                continue
            skip = [(a, b) for a, b, _q in find_quotation_spans(line, min_single_words=1)]
            credited = es.SPANISH_CREDIT_RE.search(line) is not None or (ctx.task == "reading" and _NUMBERED_RE.match(line) is not None)
            for f in _figures(line, "es", skip):
                cands = index.get(_stem(f.noun), [])
                if not cands or len(cands) > 64:
                    continue
                if _derived_figure(line, f, cands):
                    continue  # a difference, a change or a bound worked out from the text's figures: no figure taken from it
                if any(f.values & c.values for c, _d in cands):
                    match = [(c, d) for c, d in cands if f.values & c.values]
                    pick = match[0]
                    if f.year and all(c.year and c.year not in f.near_years for c, _d in match):
                        _add_year(ctx, line, f, pick[0], pick[1], credited)  # the text's figure, given for another year
                        continue
                elif f.values & stated_values or any(_series_key(f.noun) in stated_series.get(v, ()) for v in f.values):
                    continue  # the text states the answer's figure (with no noun, or in this figure's series): nothing misread
                else:
                    pool = cands
                    if f.year:
                        dated = [(c, d) for c, d in cands if c.year == f.year]
                        pool = dated or cands
                    else:
                        undated = [(c, d) for c, d in cands if not c.year]
                        pool = undated or cands
                    distinct = {frozenset(c.values) for c, _d in pool}
                    if len(distinct) > 1:
                        mine = {_stem(w) for w in f.context + f.after}
                        scored = sorted(((len(mine & {_stem(w) for w in c.context + c.after}), c, d) for c, d in pool), key=lambda x: -x[0])
                        if not scored or scored[0][0] == 0 or (len(scored) > 1 and scored[1][0] == scored[0][0] and frozenset(scored[1][1].values) != frozenset(scored[0][1].values)):
                            continue
                        pool = [(scored[0][1], scored[0][2])]
                    pick = pool[0]
                cell, doc = pick
                _add_figure(ctx, line, f, cell, doc, credited)


#: A verb of change before a figure ("perdió 1.038 habitantes", "creció en 56 personas", "cayó ... en 1.038"): the figure is the size of
#: the change, worked out from two figures of the text, never one the text states.
_CHANGE_VERB_RE = re.compile(r"\b(?:perdi[oó]|perdieron|gan[oó]|ganaron|creci[oó]|crecieron|cay[oó]|cayeron|baj[oó]|bajaron|subi[oó]|subieron|"
                             r"aument[oó]|aumentaron|disminuy[oó]|disminuyeron|descendi[oó]|descendieron|se\s+redujo|se\s+redujeron|"
                             r"lost|gained|grew|fell|rose|dropped|increased|decreased|declined)\b", re.IGNORECASE)
_COMPARATIVE_AFTER_RE = re.compile(r"^\s*+(?:[^\W\d_]{1,20}\s+){0,2}?(?:m[aá]s|menos|more|fewer|less)\s+(?:que|de\s+los\s+que|than)\b",
                                   re.IGNORECASE)
_NOW_RE = re.compile(r"\b(?:hoy|ahora|actualmente|en\s+la\s+actualidad|today|now|currently)\b", re.IGNORECASE)


#: An apposition that restates a worked figure: "es decir", "o sea", "en total", "that is", "i.e.", "in total", "in all".
_APPOSITION_RE = re.compile(r"(?:\bes\s+decir|\bo\s+sea|\ben\s+total|\bthat\s+is|\bi\.e\.|\bin\s+(?:total|all))\s*+,?\s*+(?:en\s+|unos\s+|unas\s+|about\s+|some\s+)?$",
                            re.IGNORECASE)


#: After a figure (and its noun): its operands in brackets in the same sentence ("(2009 y 2021)", "(desde 2009)", "(268 frente a 212)"),
#: a duration's relation word ("años después del cierre", "years later") or a quotient ("solicitudes por puesto", "per post").
_WORKED_AFTER_RE = re.compile(r"^[^.;!?()]{0,80}?\((?:[^()]{0,30}?\d[\d.,]{0,8}\s*+(?:y|e|frente\s+a|a|–|—|-|and|to|vs\.?|contra|menos|−)\s*+"
                              r"\d[\d.,]{0,8}|\s*+(?:desde|since|from)\s++\d{4})[^()]{0,20}\)|"
                              r"^\s*+(?:[^\W\d_]{1,20}\s+){0,2}?(?:despu[eé]s|antes|m[aá]s\s+tarde|later|earlier|after|before)\b|"
                              r"^\s*+(?:[^\W\d_]{1,20}\s+){0,2}?(?:por|per)\s+(?:cada\s+)?[^\W\d_]{3,20}\b", re.IGNORECASE)


def _derived_figure(line: str, f: _Fig, cands: list) -> bool:
    """Attack round 3 (sp-t14): a figure the answer works out from the text's figures, not one it takes from the text: a difference
    ("56 personas más que en 2015", "892 menos"), the size of a change ("perdió 1.038 habitantes", "creció en 56 personas", "es decir,
    en 1.038 personas"), a bound on a change ("perdió más de mil habitantes"), or a figure of today where the text dates every figure of
    that noun ("hoy hay 1 panadería" against the 1960 count). Such a figure is left to the arithmetic readers, never compared with a
    figure the text states."""
    at = max(0, min(f.start, len(line)))
    tail = line[at:at + 80]
    # the figure's own token, then what follows it
    m = re.match(r"\S+(?:\s+\S+)?", tail)
    after = tail[m.end():] if m else tail
    if _COMPARATIVE_AFTER_RE.match(after) or _COMPARATIVE_AFTER_RE.match(tail[len(tail.split(" ", 1)[0]):]):
        return True
    head = line[max(0, at - 60):at]
    if _CHANGE_VERB_RE.search(head) and not re.search(r"(?<!m[aá]s )(?<!menos )\bde\s*+$|\bfrom\s*+$|\ba\s*+$|\bto\s*+$", head):
        # (the from-to pair of a change, "cayó de 1.250 a 212", are the text's own figures, read as such)
        return True
    if _APPOSITION_RE.search(head[-40:]):
        return True  # "es decir, cinco personas", "o sea, unos 86 alumnos menos": a figure the answer works out and restates (attack round 4)
    if _WORKED_AFTER_RE.match(after) or _WORKED_AFTER_RE.match(tail[len(tail.split(" ", 1)[0]):]):
        return True  # a figure stated with its operands ("doce años después del cierre (2009 y 2021)", "seis años cerrada (desde 2009)",
        # "treinta solicitudes por puesto", attack round 5): worked out from the text's figures, never one taken from it
    if re.search(r"\b(?:llevaba|llevaban|lleva|llevan|hace|hacía|desde\s+hac[ií]a)\s*+$", head[-20:], re.IGNORECASE):
        return True  # "llevaba seis años cerrada", "hace doce años": a duration worked out from the text's dates
    if _NOW_RE.search(head[-30:]) and not f.year and cands and not any(
            any(w in ("hoy", "ahora", "actualmente", "today", "now") for w in c.context) for c, _d in cands):
        return True  # a figure of today against figures the text gives for other times
    return False


_CLAUSE_SPLIT_RE = re.compile(r"[.!?;:,]\s|\n")
_YEAR_IN_RE = re.compile(r"(?<![\d.,])(?:1[89]\d{2}|20\d{2})(?![\d.,]\d|\d)")
_EVENT_STOP = frozenset("según texto artículo dice cuenta afirma hace había tenía años pueblo".split())


def _content_stems(clause: str) -> set:
    return {_stem(w.casefold()) for w in re.findall(r"[^\W\d_]{4,40}", clause) if w.casefold() not in _CONTEXT_STOP and
            w.casefold() not in _EVENT_STOP}


def _event_years(ctx: _Ctx) -> None:
    """Attack round 3 (sp-t14): the year of an event the answer credits to the text ("Según el texto, la fibra óptica llegó en 2019")
    against the year the text gives it ("En 2021 llegó por fin la fibra óptica"): the text's clause holding exactly one year and sharing
    at least two content words with the answer's clause is the event's; a year the clause does not hold is named. A clause of the text
    that matches as well as another one with a different year leaves the event unread."""
    if not (ctx.regions.spanish or _spanish_context(ctx.report)):
        return
    docs = [t for t in ctx.report.supplied_texts if not (t.document_id or "").startswith("peer:") and t.text and es.is_spanish(t.text)]
    if ctx.regions.student_text is not None:
        docs = [t for t in docs if t.text != ctx.regions.student_text]
    events = []
    for d in docs:
        for clause in _CLAUSE_SPLIT_RE.split(d.text[:MAX_REGION])[:2000]:
            ys = set(_YEAR_IN_RE.findall(clause))
            if len(ys) == 1:
                stems = _content_stems(clause)
                if len(stems) >= 2:
                    events.append((stems, next(iter(ys)), set(_YEAR_IN_RE.findall(clause)), d.document_id))
    if not events:
        return
    r = ctx.regions
    excluded = set(r.model) | set(r.disclaimer)
    for pi, para in enumerate(r.paragraphs):
        if pi in excluded or not _YEAR_IN_RE.search(para):
            continue
        for line in para.split("\n"):
            en, sp, _n = es.english_ratio(line)
            if en > sp or es.SPANISH_CREDIT_RE.search(line) is None:
                continue
            for clause in _CLAUSE_SPLIT_RE.split(line):
                ys = _YEAR_IN_RE.findall(clause)
                if len(ys) != 1 or re.search(r"\d", _YEAR_IN_RE.sub("", clause)):
                    continue  # a clause with a figure besides its year is the figure readers'
                mine = _content_stems(clause)
                scored = sorted(((len(mine & st), y, doc) for st, y, _all, doc in events), key=lambda x: -x[0])
                if not scored or scored[0][0] < 2 or (len(scored) > 1 and scored[1][0] == scored[0][0] and scored[1][1] != scored[0][1]):
                    continue
                _n2, year, doc = scored[0]
                stated = ys[0]
                ctx.add("supplied_figure", lambda cid, year=year, stated=stated, clause=clause, doc=doc, line=line: make_check(
                    ctx.report, check_id=cid, kind="supplied_figure", inputs=[("year", int(year), f"the year the supplied text gives this event ({year})")],
                    conclusion={"op": "eq", "left": _var("year"), "right": _real(int(stated))},
                    label=f"the year {stated} the answer credits to the text for '{clause.strip()[:80]}' equals the year {year} in {doc}",
                    description=(f"an event's year credited to a supplied text: '{line[:200]}' against {doc} ({year}) [rule: an event taken from a "
                                 "supplied text keeps the text's year]"),
                    claim_ids=ctx.claims(line, stated), severity="error", defect="source_mismatch"))


def _add_year(ctx: _Ctx, line: str, f: _Fig, cell: _Fig, doc: str, credited: bool) -> None:
    """Attack round 3 (sp-t14): a figure the text gives, dated by the answer with another year than the text's ("1.250 habitantes en
    1950" against "En 1960, Valdeoca tenía 1.250 habitantes")."""
    ctx.add("supplied_figure", lambda cid: make_check(
        ctx.report, check_id=cid, kind="supplied_figure", inputs=[("year", int(cell.year), f"the year the supplied text gives for {cell.shown} {cell.noun}")],
        conclusion={"op": "eq", "left": _var("year"), "right": _real(int(f.year))},
        label=f"the year {f.year} the answer gives for {f.shown} {f.noun} equals the supplied text's year {cell.year} in {doc}",
        description=(f"a dated figure taken from a supplied text: {f.shown} {f.noun} ({f.year}) in '{line[:200]}' against {doc}: {cell.shown} {cell.noun} "
                     f"({cell.year}) ({'credited to the text' if credited else 'not credited'}) [rule: a figure taken from a supplied text keeps the "
                     "text's year]"),
        claim_ids=ctx.claims(line, f.shown), severity="error" if credited else "warning", defect="source_mismatch"))


def _add_figure(ctx: _Ctx, line: str, f: _Fig, cell: _Fig, doc: str, credited: bool) -> None:
    options = []
    for v in sorted(f.values):
        for c in sorted(cell.values):
            half = Fraction(1, 2)
            options.append({"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _real(v), "right": _var("cell")}, "right": _real(half)},
                                                  {"op": "ge", "left": {"op": "sub", "left": _real(v), "right": _var("cell")}, "right": _real(-half)}]})
    held = min(cell.values)
    concl = options[0] if len(options) == 1 else {"op": "or", "args": options}
    ctx.add("supplied_figure", lambda cid: make_check(
        ctx.report, check_id=cid, kind="supplied_figure", inputs=[("cell", held, f"the supplied figure beside '{cell.noun}' ({cell.shown}{', ' + cell.year if cell.year else ''})")],
        conclusion=concl,
        label=f"the figure {f.shown} {f.noun} equals the supplied figure {cell.shown} {cell.noun} in {doc} (every reading of the numerals)",
        description=(f"a figure taken from a supplied text: {f.shown} {f.noun} in '{line[:200]}' against {doc}: {cell.shown} {cell.noun}"
                     f"{' (' + cell.year + ')' if cell.year else ''} ({'credited to the text' if credited else 'not credited'}) [rule: a figure taken from a "
                     "supplied text equals it within half a unit; a numeral is read every way it can be read]"),
        claim_ids=ctx.claims(line, f.shown), severity="error" if credited else "warning", defect="source_mismatch"))


# ------------------------------------------------------------------------------------------------------------------ quotation speakers
_SAY_ES = r"dice|dijo|cuenta|contó|afirma|afirmó|explica|explicó|añade|añadió|asegura|aseguró|recuerda|recordó|comenta|comentó|responde|respondió|admite|admitió|reconoce|reconoció|señala|señaló|insiste|insistió|lamenta|lamentó|confiesa|confesó"
_SAY_EN = r"says|said|tells|told|puts\s+it|writes|wrote|adds|added|explains|explained|recalls|recalled|admits|admitted|insists|insisted|remarks|remarked"
_QUOTE_RE = re.compile(r"«(?P<a>[^»\n]{3,600})»|\"(?P<b>[^\"\n]{3,600})\"|“(?P<c>[^”\n]{3,600})”")
_AFTER_SAY_RE = re.compile(r"^\s*+,?\s*+(?:" + _SAY_ES + r"|" + _SAY_EN + r")\s++(?P<who>[^.;:«»\"“”\n]{2,120})", re.IGNORECASE)
_BEFORE_SAY_RE = re.compile(r"(?P<who>[^.;«»\"“”\n]{2,120}?)\s++(?:" + _SAY_ES + r"|" + _SAY_EN + r")(?:\s++que)?(?:\s++that)?(?:\s++the\s+\w+)?\s*+[,:]?\s*+$", re.IGNORECASE)
_SEGUN_RE = re.compile(r"(?:\bseg[uú]n|\bas|\baccording\s+to)\s++(?P<who>[^.;:«»\"“”\n]{2,120}?)(?:\s++puts\s+it)?\s*+,\s*+$", re.IGNORECASE)
_SAID_BY_RE = re.compile(r"^\s*+\((?:said|spoken|written|dicho|dicha)\s+(?:by|por)\s+(?P<who>[^)\n]{2,120})\)", re.IGNORECASE)
_WHO_STOP = frozenset("the a an la el los las un una as según segun according to que that of de del who which quien this these it his her its "
                      "sus su ha has had sido been".split())


def _norm_quote(q: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", q.casefold()))


def _speaker_words(who: str) -> tuple[set, set]:
    """(names, words) of a speaker phrase: names are the capitalised words, words every content word, case folded."""
    toks = re.findall(r"[^\W\d_]+", who)
    names = {t.casefold() for t in toks if t[:1].isupper() and t.casefold() not in _WHO_STOP}
    words = {t.casefold() for t in toks if t.casefold() not in _WHO_STOP and t.casefold() not in _CONTEXT_STOP and len(t) >= 3}
    return names, words


def _quote_speakers(text: str) -> list[tuple[str, str]]:
    """``(normalised quotation, speaker phrase)`` for every quotation of ``text`` a speech verb credits (after it, before it, "Según X,"
    or "(said by X)"); an unframed quotation that follows a framed one in the same paragraph continues its speaker. Bounded."""
    out: list[tuple[str, str]] = []
    last_who, last_end = None, -10
    for m in list(_QUOTE_RE.finditer(text[:MAX_REGION]))[:400]:
        q = m.group("a") or m.group("b") or m.group("c")
        if len(q.split()) < 3:
            continue
        after = text[m.end():m.end() + 160]
        start = max(text.rfind("\n", 0, m.start()), text.rfind(". ", 0, m.start()), text.rfind("» ", 0, m.start()) - 1) + 1
        before = text[max(start, m.start() - 160):m.start()]
        who = None
        for rx, part in ((_SAID_BY_RE, after), (_AFTER_SAY_RE, after)):
            x = rx.search(part)
            if x:
                who = x.group("who")
                break
        if who is None:
            x = _BEFORE_SAY_RE.search(before) or _SEGUN_RE.search(before)
            if x:
                who = x.group("who")
        if who is None and last_who is not None and "\n\n" not in text[last_end:m.start()] and len(text[last_end:m.start()].strip(" .,")) <= 3:
            who = last_who  # «...», cuenta X. «...»: the next quotation is X's too
        if who is not None:
            out.append((_norm_quote(q), who))
            last_who = who
            end = m.end() + (x.end() if (x := _AFTER_SAY_RE.search(after)) else 0)
            last_end = end
    return out


def _speakers(ctx: _Ctx) -> None:
    """Attack round 3 (sp-t14): the speaker a quotation is credited to against the supplied text. A quotation of at least three words
    that the answer credits to a speaker (a speech verb before or after it, "Según X,", "As X puts it,", "(said by X)") and that the
    supplied text credits to a speaker too is compared by name (the capitalised words) or, with no name, by the speaker's description;
    a name or description the text gives no speaker leaves the quotation undecided."""
    if not (ctx.regions.spanish or _spanish_context(ctx.report)):
        return
    docs = [t for t in ctx.report.supplied_texts if not (t.document_id or "").startswith("peer:") and t.text]
    if ctx.regions.student_text is not None:
        docs = [t for t in docs if t.text != ctx.regions.student_text]
    source: list[tuple[str, str, str]] = []
    for d in docs:
        source += [(q, who, d.document_id) for q, who in _quote_speakers(d.text)]
    if not source:
        return
    all_names, all_words = set(), set()
    for _q, who, _d in source:
        n, w = _speaker_words(who)
        all_names |= n
        all_words |= w
    r = ctx.regions
    excluded = set(r.model) | set(r.disclaimer)
    for pi, para in enumerate(r.paragraphs):
        if pi in excluded:
            continue
        for q, who in _quote_speakers(para):
            if len(q.split()) < 3:
                continue
            hits = [(sw, d) for sq, sw, d in source if q in sq or sq in q]
            if not hits:
                continue
            names, words = _speaker_words(who)
            names &= all_names
            words &= all_words
            if not names and not words:
                continue  # a speaker the text names nowhere: undecided
            doc_who, doc = hits[0]
            dn, dw = _speaker_words(doc_who)
            same = bool(names & dn) if names else bool(words & dw)
            line = next((ln for ln in para.split("\n") if who in ln), para)[:300]
            ctx.add("lb_quote_speaker", lambda cid, same=same, who=who, doc_who=doc_who, doc=doc, line=line, q=q: make_check(
                ctx.report, check_id=cid, kind="lb_quote_speaker", inputs=[("same", Fraction(1 if same else 0),
                                                                            f"whether the speaker the answer names ({who.strip()[:60]}) is the one {doc} names ({doc_who.strip()[:60]})")],
                conclusion={"op": "eq", "left": _var("same"), "right": _real(Fraction(1))},
                label=f"the quotation «{q[:60]}» is credited to the speaker {doc} credits it to",
                description=(f"{line[:200]} [a quotation of a supplied text keeps the text's speaker: compared by name, or by description where no "
                             "name is given]"),
                claim_ids=ctx.claims(line, who.strip()[:40]), severity="error" if es.SPANISH_CREDIT_RE.search(line) else "warning",
                defect="source_mismatch"))


# ------------------------------------------------------------------------------------------------------------------ the pack
_CACHE: dict[tuple, tuple[list, list]] = {}
_CACHE_MAX = 32


def _inputs_key(report: SpecialistReport, request_text: Optional[str]) -> str:
    """A digest of everything the build reads: the response, every claim's text, the request and every supplied text's content,
    title and author (a cache keyed by ids alone served one document's verdict for another's figures)."""
    import hashlib
    h = hashlib.sha256()
    for part in ([report.original_response or "", request_text or "", str(report.task_type or "")] +
                 [getattr(c, "claim_text", "") or "" for c in report.claims] +
                 [f"{t.document_id}\x1f{t.title or ''}\x1f{getattr(t, 'author', '') or ''}\x1f{t.text}" for t in report.supplied_texts]):
        h.update(part.encode("utf-8", "surrogatepass"))
        h.update(b"\x1e")
    return h.hexdigest()


def _build(report: SpecialistReport, request_text: Optional[str]) -> tuple[list[FormalCheck], list[StructuralFinding]]:
    req = (request_text or "")[:MAX_REQUEST]
    key = (report.report_id, report.response_sha256, _inputs_key(report, req))
    hit = _CACHE.get(key)
    if hit is not None:
        return list(hit[0]), list(hit[1])
    text = (report.original_response or "")[:MAX_TEXT]
    task = classify_task(report, req)
    spanish = es.is_spanish(text)
    regions = model_regions(text, task=task, supplied=tuple(report.supplied_texts), request_text=req, spanish_context=spanish)
    ctx = _Ctx(report, req, task, regions, text)
    statements = _statements(regions, text)
    failures: list[StructuralFinding] = []
    for stage, step in (("word counts and ranges", lambda: _word_checks(ctx, statements)), ("course range", lambda: _course_range(ctx)),
                        ("quoted forms", lambda: _quoted_forms(ctx, statements)), ("address forms", lambda: _address_checks(ctx, statements)),
                        ("listed counts", lambda: _listed_counts(ctx, statements)), ("percentage changes", lambda: _percent_changes(ctx)), ("dated changes", lambda: _dated_changes(ctx)),
                        ("supplied figures", lambda: _supplied_figures(ctx)), ("event years", lambda: _event_years(ctx)), ("quotation speakers", lambda: _speakers(ctx))):
        try:
            step()
        except ArithmeticError:
            continue  # an arithmetic edge (a zero base) is no statement the reader can check
        except Exception as exc:  # noqa: BLE001 - reported on the receipt (BR-INTERNAL-001), never silent; the other readers still run
            failures.append(StructuralFinding(code="BR-INTERNAL-001", severity="warning",
                                              message=(f"pack 'language_b' failed internally ({type(exc).__name__}) during {stage}; its checks are missing from "
                                                       "this receipt, and the router must not treat the pack as passed"),
                                              rule_source="branch infrastructure: a pack failure is named, never silent"))
    if ctx.dropped:
        n = sum(ctx.dropped.values())
        kinds = ", ".join(f"{k.replace('lb_', '').replace('_', ' ')} ({v})" for k, v in sorted(ctx.dropped.items()))
        failures.append(StructuralFinding(
            code="CORE-QNT-001", severity="warning", claim_ids=[],
            message=(f"the Language B pack's reading bound was reached ({MAX_CHECKS} checks): {n} further statement(s) were left unread and "
                     f"are not checked [{kinds}]"),
            rule_source="Language B pack: a statement the bound leaves unread is named undecided, never dropped silently"))
    built = (list(ctx.checks), failures)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = built
    return built


class LanguageBPack:
    """The Language B pack: GEN-STR-001 (unknown supporting claims) and the formal checks of the module docstring. It never reads,
    filters or re-words a self-report, and no region exempts a sentence from the core pack's shared gate."""
    name = "language_b"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        from .packs import unknown_supports
        return unknown_supports(report) + _build(report, request_text)[1]

    def formal_checks_for(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[FormalCheck]:
        from .packs import _worked_checks
        out = list(_build(report, request_text)[0])
        try:
            out += _worked_checks(report, "language-b-worked", set())
        except Exception:  # noqa: BLE001 - the core pack's undecided reader still names every worked equation
            pass
        return out

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return self.formal_checks_for(report, None)
