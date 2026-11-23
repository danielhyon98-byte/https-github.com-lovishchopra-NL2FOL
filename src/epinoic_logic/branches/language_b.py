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
``lb_word_range_claim``    a production said to lie inside (or outside) a range or a limit, and    INT-SUBJ-001
                           a word range the answer credits to the task
``lb_course_word_range``   a convention: an SL / HL Paper 1 model with no bound in the request     INT-SUBJ-004
``lb_quoted_form``         a form the answer says the model (or an inline model) contains          INT-SUBJ-004
``lb_address_form``        the address form (tú, vos, usted, vosotros, ustedes) a production uses  INT-SUBJ-004
``lb_listed_count``        a count of items the answer lists itself (corrections, connectors)      INT-SUBJ-004
``lb_percent_change``      a Spanish change with its from-to pair ("pasó de 1.250 a 212 ...")      INT-SUBJ-001
``lb_share``               a share of a total with its part ("El 25 % de 80 es 20"), or with the   INT-SUBJ-001
                           fraction it is worked from ("75% of the available marks (21/30)")
``supplied_figure``        a Spanish figure with its noun read against the supplied text           INT-SUBJ-001 credited (or a numbered
                                                                                                  reading answer); INT-SUBJ-004
``lb_structure_count``     a count of a text's paragraphs, stanzas or lines                        INT-SUBJ-004
``lb_occurrence_count``    how often a quoted form occurs in a text ('three times in a row')       INT-SUBJ-004
``lb_quote_speaker``       the speaker of a quotation, of unquoted words or of a paraphrase        INT-SUBJ-001 credited; INT-SUBJ-004
                           (by kin word or by name; a text's speaker named after the words or by
                           a description it sets a name beside)
``worked_arithmetic``      every worked equation, as on the generic branch                         as there
=========================  =====================================================================  ===================================

Attack round 8 widened the readers: the change readers read a currency sign and Spanish number words; ``lb_quoted_form`` reads "opens
with", "says", the byline and a paraphrase located at a line; ``lb_listed_count`` reads a count of the model's or the student's items
(their own count or their ordinals) and of the answer's corrections by category; ``supplied_figure`` reads a count across languages (the
closed bilingual gloss :func:`.spanish_lexicon.concept`), a duration with a quoted form and an event's year stated in English or with no
credit (a warning).

The c3d follow-up widened them again: ``lb_quoted_form`` reads a reporting verb of the model ('The model proposes that ... "..."') and
what the byline is said to state with no name first (its capitalised words and figures: 'a student in 1.º de Bachillerato'); the word
count reads the answer's own notes ('These notes are about 400 words') and a one-sided limit ('within the 250-word limit'); the
cross-language counts read the scenario a writing or marking task sets in the target language ('tres semanas de intercambio'; a
reading task's request sets statements to judge, never facts).

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
from functools import lru_cache
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
         # (c3e: "el texto modelo", "el artículo modelo" too)
         r"|tu\s+(?:texto|correo|redacción|carta|artículo)|el\s+(?:texto|correo|artículo)(?:\s+modelo)?|el\s+modelo"
         # the answer's own notes or reply (c3d, sp-p10d: "These notes are about 400 words, within the 250-word limit.")
         r"|(?:these|the|my|our)\s+notes|this\s+(?:response|reply)|estas\s+notas)")
_PROD_COUNT_RE = re.compile(_PROD + r"\s+(?:is|was|are|were|has|have|comes\s+to|come\s+to|runs?\s+to|contains?|tiene|tienen|es\s+de|son)\s+(?:(?P<approx>" + _APPROX_WORDS + r")\s+)?(?P<n>\d{1,5})\s+(?:words|palabras)\b",
                            re.IGNORECASE)
#: A count after a word range in the same sentence, its noun left out ("La consigna pide entre 450 y 600 palabras, y el texto modelo tiene
#: 300": c3e, the branches-policy lens).
_PROD_COUNT_ELLIPTIC_RE = re.compile(_PROD + r"\s+(?:is|was|has|comes\s+to|runs?\s+to|contains?|tiene|es\s+de)\s+(?:(?P<approx>" + _APPROX_WORDS
                                     + r")\s+)?(?P<n>\d{2,5})(?![\d.,]\d|\s*+(?:%|words|palabras|[^\W\d_]))", re.IGNORECASE)
_PAREN_COUNT_RE = re.compile(r"\((?:(?P<approx>" + _APPROX_WORDS + r"|aprox\.)\s+)?(?P<n>\d{1,5})\s+(?:words|palabras)\)", re.IGNORECASE)
_WHOLE_RE = re.compile(r"\b(?:including|with|incl\.?|counting)\s+(?:the\s+)?(?:headline|title|byline|heading|greeting|signature)|\bincluyendo\s+(?:el\s+)?t[ií]tulo", re.IGNORECASE)
_BODY_RE = re.compile(r"\b(?:in|of)\s+the\s+(?:body|main\s+text)\b|\bbody\b|\bexcluding\s+(?:the\s+)?(?:headline|title|byline)\b|\bsin\s+(?:el\s+)?t[ií]tulo", re.IGNORECASE)
_RANGE_RE = re.compile(r"(?<![\d.,])(?P<lo>\d{2,4})\s*+(?:[–—-]|to)\s*+(?P<hi>\d{2,4})(?![\d.,]\d)|\bbetween\s+(?P<lo2>\d{2,4})\s+and\s+(?P<hi2>\d{2,4})\s+words\b"
                       r"|\bentre\s+(?P<lo3>\d{2,4})\s+y\s+(?P<hi3>\d{2,4})\s+palabras\b", re.IGNORECASE)
#: A bound written in words ("de 450 a 600", "entre 450 y 600", "between 450 and 600", "from 450 to 600"): its figures are the
#: limits of a range, never a stated count (attack round 6: the lower bound was read as the count).
_BOUND_BEFORE_RE = re.compile(r"\b(?:de|del|entre|between|from)\s*+$", re.IGNORECASE)
_RANGE_WORDS_RE = re.compile(r"\s*+(?:-?\s*+word|words|palabras|range|limit|band)\b", re.IGNORECASE)
_IN_RANGE_RE = re.compile(r"\b(?:inside|within)\s+(?:the\s+|your\s+|a\s+)?(?:\d{2,4}\s*+[–—-]\s*+\d{2,4}|\d{2,4}(?:-|\s)word\s+(?:limit|maximum|cap)|range|limit|band|bounds?|word\s+(?:range|limit))"
                          r"|\b(?:is|are|lies|falls|sits|stays|comes\s+in)\s+(?:well\s+|comfortably\s+|safely\s+|just\s+)?(?:inside|within)\b"
                          r"|\b(?:the\s+)?length\s+is\s+(?:right|fine|correct|appropriate|ok|okay|good|spot\s+on)\b"
                          r"|\b(?:est[aá]|queda)\s+dentro\s+del?\s+(?:l[ií]mite|rango)", re.IGNORECASE)
#: A one-sided word limit a statement states ("within the 250-word limit", "a 250-word maximum"): the range 0 to the limit (c3d).
_WORD_CAP_RE = re.compile(r"(?<![\d.,–—-])(?P<n>\d{2,4})(?:-|\s)word\s+(?:limit|maximum|cap)\b", re.IGNORECASE)
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
    elliptic = [m for m in _PROD_COUNT_ELLIPTIC_RE.finditer(s) if re.search(r"\b(?:words|palabras)\b", s[:m.start()], re.IGNORECASE)]
    for rx in (_PROD_COUNT_RE, _PAREN_COUNT_RE, elliptic):
        for m in (rx if isinstance(rx, list) else rx.finditer(s)):
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
        cap = _WORD_CAP_RE.search(st.text)
        rng = (0, int(cap.group("n")), "the limit the statement states") if near is None and cap is not None else _range_for(ctx, st, near)
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


#: A word bound the answer credits to the task ("The task asks for between 250 and 400 words", "La consigna pide entre 450 y 600 palabras",
#: "your task sets a 450–600-word range"): c3d, sp-t15.
_TASK_WORDS_RE = re.compile(r"\b(?:the|your|this|tu|la|el)\s+(?:task|question|request|brief|prompt|instructions?|assignment|consigna|tarea|enunciado)\s+"
                            r"(?:asks\s+for|asked\s+for|requires?|required|sets?|wants?|wanted|calls?\s+for|specifies|specified|says|said|gives?|pide|exige|marca)\s+"
                            r"(?:an?\s+|a\s+range\s+of\s+|a\s+length\s+of\s+)?(?:between\s+(?P<a>\d{2,4})\s+and\s+(?P<b>\d{2,4})|entre\s+(?P<c>\d{2,4})\s+y\s+(?P<d>\d{2,4})|"
                            r"(?:from\s+)?(?P<e>\d{2,4})\s*+(?:[–—-]|to|a)\s*+(?P<f>\d{2,4}))(?:-|\s+)(?:words?|palabras)\b", re.IGNORECASE)


def _task_word_claims(ctx: _Ctx, statements: list[_Stmt]) -> None:
    """c3d (sp-t15): a word range the answer credits to the task is the range the request sets (its min_words and max_words, or a range
    it writes before 'words' / 'palabras'); a request with no bound leaves it unread."""
    from ..channel.request_parser import extract_constraints
    req = ctx.request_text or ""
    cs = extract_constraints(req) if req else []
    mins = [int(c.value) for c in cs if c.kind == "min_words" and c.value]
    maxs = [int(c.value) for c in cs if c.kind == "max_words" and c.value]
    sev, source = "error", "the request's"
    if not (mins and maxs):
        r = next((m for m in _RANGE_RE.finditer(req) if m.group("lo") is None or _RANGE_WORDS_RE.match(req, m.end())), None)
        if r is not None:
            lo_r, hi_r = _range_values(r)
        elif not mins and not maxs and ctx.task in ("writing", "marking") and _level(req) and re.search(r"\bpaper\s*+1\b|\bprueba\s*+1\b", req, re.IGNORECASE):
            # c3e (check round 10 of c3d, sp-t16): a Paper 1 request that sets no bound: the course's range for its level is the task's (a
            # convention, so a warning: "The task sets a length of 300 to 450 words" of an SL Paper 1 task, whose range is 250-400)
            lo_r, hi_r = COURSE_RANGES[_level(req)]
            sev, source = "warning", f"the {_level(req)} Paper 1 course convention's"
        else:
            return
    else:
        lo_r, hi_r = min(mins), max(maxs)
    for st in statements:
        for m in _TASK_WORDS_RE.finditer(st.text):
            ga, gb = next((a, b) for a, b in (("a", "b"), ("c", "d"), ("e", "f")) if m.group(a))
            lo, hi = int(m.group(ga)), int(m.group(gb))
            ctx.add("lb_word_range_claim", lambda cid, lo=lo, hi=hi, m=m, st=st: make_check(
                ctx.report, check_id=cid, kind="lb_word_range_claim", inputs=[("lo", Fraction(lo), f"the lower bound credited to the task ({lo})"),
                                                                              ("hi", Fraction(hi), f"the upper bound credited to the task ({hi})")],
                conclusion={"op": "and", "args": [{"op": "eq", "left": _var("lo"), "right": _real(Fraction(lo_r))},
                                                  {"op": "eq", "left": _var("hi"), "right": _real(Fraction(hi_r))}]},
                label=f"the task's range {lo}-{hi} words against {source} {lo_r}-{hi_r}",
                description=(f"{st.text[:220]} [a word range credited to the task is the range the request sets ({lo_r}-{hi_r} words), or for a "
                             "Paper 1 request that sets none, the course's range for its level]"),
                claim_ids=ctx.claims(st.text, m.group(0)), severity=sev, defect="source_mismatch"))


def _task_word_bounds(ctx: _Ctx, statements: list[_Stmt]) -> None:
    """Check round 10 of c3d (sp-p10d): a single word figure the answer credits to the task or the teacher ("Your teacher set a limit of
    350 words." where the request says "Write no more than 250 words.") is one of the request's own word figures (its min_words and
    max_words, or a figure it writes before "words" / "palabras"); a request with no word figure leaves it unread."""
    from ..channel.request_parser import extract_constraints
    from .geography import REQ_WORDS_CREDIT, _REQ_WORDS_RE
    req = ctx.request_text or ""
    if not req:
        return
    asked = {int(c.value) for c in extract_constraints(req) if c.kind in ("min_words", "max_words") and c.value}
    for r in list(_REQ_WORDS_RE.finditer(req[:20_000]))[:16]:
        asked.add(int(r.group("a").replace(",", "")))
        if r.group("b"):
            asked.add(int(r.group("b").replace(",", "")))
    if not asked:
        return
    credit = re.compile(REQ_WORDS_CREDIT, re.IGNORECASE)
    shown = ", ".join(str(x) for x in sorted(asked))
    for st in statements:
        for m in credit.finditer(st.text):
            n = int(m.group("p").replace(",", ""))
            if any(abs(n - x) <= max(5, x // 50) for x in asked):
                continue
            options = [{"op": "eq", "left": _var("stated"), "right": _real(Fraction(x))} for x in sorted(asked)]
            ctx.add("lb_word_range_claim", lambda cid, n=n, m=m, st=st, options=options: make_check(
                ctx.report, check_id=cid, kind="lb_word_range_claim", inputs=[("stated", Fraction(n), f"the word figure credited to the task ({n})")],
                conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
                label=f"{n} words credited to the task against the request's {shown} words",
                description=f"{st.text[:220]} [a word figure credited to the task is one the request states ({shown} words)]",
                claim_ids=ctx.claims(st.text, m.group(0)), severity="error", defect="source_mismatch"))


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


_MODEL_REF_RE = re.compile(r"\b(?:the|my|this|our)\s+(?:model(?:\s+(?:text|article|answer|email|letter|sentence))?|article|sample(?:\s+text)?|"
                           r"(?:opening|closing|first|last|final)\s+(?:line|sentence|question|paragraph)|headline|title|writer|author)\s+"
                           r"(?:uses?|used|includes?|included|contains?|has|writes?|wrote|shows?|employs?|features?|address(?:es)?|addressed|"
                           r"says?|said|states?|stated|reads?|asks?|asked|puts?\s+it|"
                           # a reporting verb of what the model proposes or argues ("The model proposes that terraces close "..."": c3d)
                           r"propos(?:es|ed|e)|suggest(?:s|ed)?|argu(?:es|ed|e)|recommend(?:s|ed)?|claim(?:s|ed)?|mention(?:s|ed)?|calls?\s+for|called\s+for|"
                           r"describ(?:es|ed|e)|explain(?:s|ed)?|not(?:es|ed)|insist(?:s|ed)?|warn(?:s|ed)?|urg(?:es|ed)|demand(?:s|ed)?|"
                           r"(?P<pos>opens?|begins?|starts?|ends?|closes?|finishes?)\s+with|opened\s+with|"
                           r"began\s+with|ended\s+with|closed\s+with)\b"
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
        pos = (m.groupdict().get("pos") or "").casefold()
        if pos and target[0] == "the model" and r.body_text:
            # "opens with" / "ends with": the form stands at the start (end) of the model's body, not merely somewhere in it (attack round 8)
            body = _norm(r.body_text)
            counts = [(f, 1 if (body.startswith(_norm(f).rstrip(".")) if pos.startswith(("open", "begin", "start")) else body.rstrip(" .!?»\"”").endswith(_norm(f).rstrip(" .!?»\"”"))) else 0)
                      for f in forms]
        else:
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


_ADDRESS_CLAIM_RE = re.compile(r"\b(?:you|your\s+(?:email|e-mail|text|letter|draft)|the\s+(?:model|email|e-mail|letter|text|article|speech|writer|author|headline|"
                               r"(?:opening|closing|first|last|final)\s+(?:line|sentence|question|paragraph))|tu\s+(?:texto|correo|carta)|el\s+(?:modelo|correo|texto))"
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


_ARROW_LINE_RE = re.compile(r"^[ \t]*+(?:[-*•]|\d{1,2}[.)])?[ \t]*+(?:[«\"“'‘][^\n]{1,300}?[»\"”'’][ \t]*+"
                            # (check round 9 of c3c: any arrow, "-->", "⇒", ">", "becomes", "should be", or a "Correct form:" label after
                            # the replaced wording)
                            r"(?:→|-{1,2}>|—>|=>|⇒|⟶|>|becomes|should\s+be|[.;,]?[ \t]*+(?:correct(?:ed)?(?:\s+(?:form|version|sentence))?|right)\s*+:)"
                            r"[ \t]*+[«\"“'‘]|"
                            # 'Write "y", not "x"': the correction first, the replaced wording after it
                            r"(?:write|use|say)\s+[«\"“'‘][^\n]{1,300}?[»\"”'’][ \t]*+,?[ \t]*+not\s+[«\"“'‘]|"
                            # a correction written with labels (attack round 8): 'Wrong: "x". Right: "y"', 'Incorrect: "x" Correct: "y"',
                            # 'Instead of "x", write "y"', 'Not "x" but "y"'
                            r"(?:wrong|incorrect|error|original|you\s+wrote|student)\s*+:[ \t]*+[«\"“'‘][^\n]{1,300}?[»\"”'’][ \t.;,]*+"
                            r"(?:right|correct(?:ed)?|corrected\s+form|better|should\s+be|fix)\s*+:[ \t]*+[«\"“'‘]|"
                            r"instead\s+of\s+[«\"“'‘][^\n]{1,300}?[»\"”'’][ \t,]*+(?:write|use|say)\s+[«\"“'‘])", re.MULTILINE | re.IGNORECASE)
_LISTED_RE = re.compile(r"\b(?:fix|correct|check|review|revise|make|work\s+on|corrige|revisa|repasa)\s+(?:the|these|those|all(?:\s+the)?|los|las|estos|estas)\s+"
                        r"(?P<n>" + _NUMBER_WORD + r"|\d{1,2})\s+(?P<noun>points|corrections|changes|errors|mistakes|fixes|puntos|correcciones|errores|cambios)\b"
                        r"|\b(?:the|these|those|las|los|estas|estos|there\s+are|hay)\s+(?P<n2>" + _NUMBER_WORD + r"|\d{1,2})\s+(?P<noun2>corrections|correcciones)\b",
                        re.IGNORECASE)  # ("There are seven corrections above.": check round 9 of c3c)
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
                            r"disminuy(?:ó|eron)|se\s+redujo|se\s+redujeron|se\s+duplic(?:ó|aron)|se\s+triplic(?:ó|aron)|"
                            # (the present too, "Si un alquiler sube de 500 € a 650 €, sube un 20 %": check round 9 of c3c)
                            r"sube|suben|baja|bajan|cae|caen|crece|crecen|aumenta|aumentan|disminuye|disminuyen|desciende|descienden)\s+"
                            # (the pair may stand in brackets after the per cent: "ha crecido un 36 % (de 212 a 268 vecinos)"; check round 10 of c3d)
                            r"(?:(?:[^\W\d_]{1,20}|(?:" + _ES_NUM + r")\s*+(?:%|por\s+ciento)),?\s+){0,4}?\(?de\s+"
                            r"(?P<a>" + _ES_NUM + r")(?:\s+(?:[^\W\d_]{1,20}|" + _ES_YEAR + r")){0,3}?\s+a\s+(?P<b>" + _ES_NUM + r")(?![\d,.]\d)", re.IGNORECASE)
#: After a from-to pair: the size of the change ("..., es decir, en 1.138 personas", "..., una caída de 1.038 habitantes").
_ES_DIFF_AFTER_RE = re.compile(r"(?:\s+[^\W\d_]{1,20}){0,2}\s*+,?\s*+(?:es\s+decir|o\s+sea|en\s+total)?\s*+,?\s*+"
                               r"(?:en|una?\s+(?:ca[ií]da|bajada|subida|diferencia|p[eé]rdida|aumento|descenso|ganancia)\s+de)\s+"
                               r"(?P<ap>unos\s+|unas\s+|casi\s+|aproximadamente\s+)?(?P<n>" + _ES_NUM + r")(?![\d,.]\d)\s+[^\W\d_]{2,20}", re.IGNORECASE)
_ES_PCT_RE = re.compile(r"(?P<p>" + _ES_NUM + r")\s*+(?:%|por\s+ciento)", re.IGNORECASE)
_FALL_ES = re.compile(r"\b(?:ca[ií]da|descenso|reducci[oó]n|bajada|disminuci[oó]n|p[eé]rdida|baj[oó]|cay[oó]|descendi[oó]|disminuy[oó]|se\s+redujo|"
                      r"(?:ha|han)\s+(?:ca[ií]do|bajado|disminuido|descendido)|se\s+han?\s+reducido)\b", re.IGNORECASE)
_RISE_ES = re.compile(r"\b(?:aumento|subida|crecimiento|incremento|alza|subi[oó]|aument[oó]|creci[oó])\b", re.IGNORECASE)
_FOLD_ES = {"la mitad": Fraction(1, 2), "el doble": Fraction(2), "el triple": Fraction(3), "se duplicó": Fraction(2), "se duplicaron": Fraction(2),
            "se triplicó": Fraction(3), "se triplicaron": Fraction(3), "cuatro veces": Fraction(4)}
_FOLD_ES_RE = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in _FOLD_ES) + r")\b", re.IGNORECASE)
_POINT_FLOOR = Fraction(1, 2)
_PCT_TOL = Fraction(1, 20)


#: A Spanish number word that may open a figure (a cheap test before the number-word reader runs on a paragraph).
_ES_NUMBER_WORD_HINT_RE = re.compile(r"\b(?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|veint\w*|treinta|cuarenta|cincuenta|"
                                     r"sesenta|setenta|ochenta|noventa|cien|ciento|\w+cientos|\w+cientas|quinientos|quinientas|mil)\b", re.IGNORECASE)
_CURRENCY_SIGN_RE = re.compile(r"(?:US\$|[€$£¥])")


def _normalise_es_figures(sent: str) -> str:
    """The sentence with its figures as digits for the change readers (attack round 8, the push check's open item): "por ciento" as '%', a
    currency sign before or after a figure as a blank ("de 600 € a 900 €", "de €600 a €900"), and a figure written in Spanish words as its
    digits ("de seiscientos a novecientos euros, una subida del treinta por ciento"). The words are read by the shared number-word reader,
    never evaluated; a sentence of no such figure is returned unchanged."""
    out = re.sub(r"\bpor\s+ciento\b", "%", sent, flags=re.IGNORECASE)
    out = _CURRENCY_SIGN_RE.sub(" ", out)
    if _ES_NUMBER_WORD_HINT_RE.search(out):
        spans = es.spanish_number_figures(out)
        for a, b, v in sorted(spans, reverse=True):
            out = out[:a] + str(v) + out[b:]
    return " ".join(out.split()) if out != sent else sent


def _percent_changes(ctx: _Ctx) -> None:
    from ..adapters.history_specialist.sentences import split_sentences
    if not (ctx.regions.spanish or _spanish_context(ctx.report)):
        return
    for para in ctx.regions.paragraphs:
        if not re.search(r"\d", para) and not _ES_NUMBER_WORD_HINT_RE.search(para):
            continue
        for orig in split_sentences(para):
            en, sp, _n = es.english_ratio(orig)
            if en > sp:
                continue
            sent = _normalise_es_figures(orig)
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
                        description=(f"{orig[:220]} [a percentage change against its from-to pair: within 5% of the computed change or half a point; "
                                     "a numeral is read every way it can be read and one reading holding is enough]"),
                        claim_ids=ctx.claims(orig, orig[:60]), defect="stem_arithmetic_slip"))
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
                        description=(f"{orig[:220]} [the size of a change stated after its from-to pair equals their difference, within half a unit "
                                     "(5% after 'unos'); a numeral is read every way it can be read and one reading holding is enough]"),
                        claim_ids=ctx.claims(orig, orig[:60]), defect="stem_arithmetic_slip"))
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
                            description=f"{orig[:220]} [a fold change against its from-to pair, within 5%; every reading of the numerals]",
                            claim_ids=ctx.claims(orig, orig[:60]), defect="stem_arithmetic_slip"))


# ------------------------------------------------------------------------------------------------------------------ shares (c3e)
_SHARE_PCT = r"\s*+(?:%|por\s+ciento\b|per\s*+cent\b|percent\b)"
_SHARE_ART = r"(?:(?:los|las|el|la|unos|unas|the|a|an)\s++)?"
_SHARE_AP = r"(?P<ap>(?:unos|unas|aproximadamente|alrededor\s+de|casi|about|around|roughly|approximately|nearly|some)\s++)?"
#: A share of a total and the part it gives: "El 25 % de 80 es 20", "el 25 % de los 80 alumnos, es decir 20 alumnos", "25% of 80 is 20".
_SHARE_RE = re.compile(r"(?<![\d.,])(?P<p>" + _ES_NUM + r")" + _SHARE_PCT + r"\s++(?:de|of)\s++" + _SHARE_ART + r"(?<![\d.,])(?P<n>" + _ES_NUM + r")(?![\d,.]\d)"
                       r"(?:\s++[^\W\d_]{2,20}){0,3}?\s*+,?\s*+(?:es\s+decir|o\s+sea|that\s+is|i\.\s*+e\.|es|son|serían?|da|dan|is|are|was|were|would\s+be|"
                       r"makes?|gives?|comes\s+to|equals)\s*+,?\s*+" + _SHARE_AP + r"(?<![\d.,])(?P<y>" + _ES_NUM + r")(?![\d,.]\d|\s*+(?:%|por\s+ciento))",
                       re.IGNORECASE)
#: The part first: "20 alumnos son el 25 % de 80", "20 is 25% of 80".
_SHARE_PART_FIRST_RE = re.compile(r"(?<![\d.,%])(?P<y>" + _ES_NUM + r")(?![\d,.]\d)(?:\s++[^\W\d_]{2,20}){0,2}?\s++(?:es|son|era|eran|is|are|was|were|"
                                  r"representan?|represents?|makes?\s+up|make\s+up|constituyen?)\s++(?:el\s++|un\s++|the\s++)?" + _SHARE_AP
                                  + r"(?<![\d.,])(?P<p>" + _ES_NUM + r")" + _SHARE_PCT + r"\s++(?:de|of)\s++" + _SHARE_ART
                                  + r"(?<![\d.,])(?P<n>" + _ES_NUM + r")(?![\d,.]\d|\s*+(?:%|por\s+ciento))", re.IGNORECASE)
#: A share with the fraction it is worked from in brackets: "75% of the available marks (21/30)", "el 70 % de la nota (21 de 30)".
_SHARE_FRACTION_RE = re.compile(r"(?<![\d.,])(?P<p>" + _ES_NUM + r")" + _SHARE_PCT + r"\s++(?:de|of)\s++(?:[^\W\d_]{1,20}\s++){0,4}?\(\s*+(?P<a>" + _ES_NUM
                                + r")\s*+(?:/|de|of|out\s+of)\s*+(?P<b>" + _ES_NUM + r")\s*+\)", re.IGNORECASE)


def _band(value: Fraction, tol: Fraction) -> dict:
    return {"op": "and", "args": [{"op": "le", "left": {"op": "sub", "left": _var("stated"), "right": _real(value)}, "right": _real(tol)},
                                  {"op": "ge", "left": {"op": "sub", "left": _var("stated"), "right": _real(value)}, "right": _real(-tol)}]}


def _readings(token: str, spanish: bool) -> list[Fraction]:
    return sorted(es.spanish_numeral_readings(token, "es" if spanish else None))


_SHARE_FUNCTION_WORDS = frozenset("de del of in en y and es son is are was were the los las el la a an que that which por for".split())
_SHARE_YEAR_RE = re.compile(r"(?:1[5-9]|20)\d{2}")
_SHARE_AGE_AFTER_RE = re.compile(r"\s*+(?:or|o|y)\s++(?:older|more|over|above|younger|less|under|below|m[aá]s|mayores|menos)\b", re.IGNORECASE)


def _share_part_of_total(sent: str, m: "re.Match[str]") -> bool:
    """Whether the part ``y`` of a share match is a number OF THE SAME TOTAL: never a year ("En 2023 los jóvenes eran el 25 % de los 80
    vecinos"), an age ("18 or older", "65 años"), a rating ("4 estrellas") or a count of another noun ("o sea 300 camas" of 150
    hoteles); a noun after the part is the total's own noun ("es decir 30 alumnos" of 80 alumnos) or there is none (check round 11 of
    c3e)."""
    y = m.group("y")
    if _SHARE_YEAR_RE.fullmatch(y.strip()):
        return False
    if _SHARE_AGE_AFTER_RE.match(sent, m.end("y")):
        return False
    after = re.match(r"\s*+([^\W\d_]+)", sent[m.end("y"):m.end("y") + 40])
    if after is None or after.group(1).lower() in _SHARE_FUNCTION_WORDS:
        return True
    noun = re.match(r"\s*+([^\W\d_]+)", sent[m.end("n"):m.end("n") + 40])
    if noun is None or noun.group(1).lower() in _SHARE_FUNCTION_WORDS:
        return False  # (a noun of the part's own and none of the total's: "es 4 estrellas")
    return after.group(1).lower()[:4] == noun.group(1).lower()[:4]


def _shares(ctx: _Ctx) -> None:
    """c3e (the push check's branch miss; c3d left it undone): a share of a total stated with the part it gives, in Spanish or English
    ("El 25 % de 80 es 30", "El 25 % de los 80 alumnos, es decir 30 alumnos", "20 is 25% of 80"), or with the fraction it is worked
    from ("75% of the available marks (21/30)"). The part equals per cent × total / 100 (half a unit of the part as written, 5% after
    'unos' or 'about'); the per cent equals the fraction × 100 (half a point). A numeral is read every way it can be read (one reading
    holding is enough); Spanish number words and 'por ciento' are read as figures first."""
    from ..adapters.history_specialist.sentences import split_sentences
    for para in ctx.regions.paragraphs:
        if "%" not in para and not re.search(r"\bpor\s+ciento\b|\bper\s*+cent\b|\bpercent\b", para, re.IGNORECASE):
            continue
        for orig in split_sentences(para):
            en, sp, _n = es.english_ratio(orig)
            spanish = sp >= en
            sent = _normalise_es_figures(orig) if spanish else orig
            for rx in (_SHARE_RE, _SHARE_PART_FIRST_RE):
                for m in rx.finditer(sent):
                    P, N, Y = _readings(m.group("p"), spanish), _readings(m.group("n"), spanish), _readings(m.group("y"), spanish)
                    if not P or not N or not Y or (_YEAR_RE.match(m.group("n")) and not m.group("n").startswith("0")):
                        continue
                    if not _share_part_of_total(sent, m):
                        continue
                    from .grounded_figures import _half
                    y_shown = m.group("y")
                    half = _half(y_shown.replace(".", "").replace(",", ".") if spanish else y_shown.replace(",", ""))
                    options = []
                    for p in P:
                        for n in N:
                            v = p * n / 100
                            options.append(_band(v, max(half, abs(v) * _PCT_TOL if m.group("ap") else half)))
                    stated = Y[0]
                    ctx.add("lb_share", lambda cid, options=options, stated=stated, m=m, orig=orig: make_check(
                        ctx.report, check_id=cid, kind="lb_share", inputs=[("stated", stated, f"the part stated ({m.group('y')})")],
                        conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
                        label=f"{m.group('y')} against {m.group('p')} % of {m.group('n')} (every reading of the numerals)",
                        description=(f"{orig[:220]} [a share of a total gives the part per cent × total / 100, within half a unit of the part as written "
                                     "(5% after an approximation word); a numeral is read every way it can be read and one reading holding is enough]"),
                        claim_ids=ctx.claims(orig, orig[:60]), defect="stem_arithmetic_slip"))
            for m in _SHARE_FRACTION_RE.finditer(sent):
                P, A, B = _readings(m.group("p"), spanish), _readings(m.group("a"), spanish), _readings(m.group("b"), spanish)
                options = [_band(a / b * 100, _POINT_FLOOR) for a in A for b in B if b != 0]
                if not P or not options:
                    continue
                stated = P[0]
                ctx.add("lb_share", lambda cid, options=options, stated=stated, m=m, orig=orig: make_check(
                    ctx.report, check_id=cid, kind="lb_share", inputs=[("stated", stated, f"the per cent stated ({m.group('p')} %)")],
                    conclusion=options[0] if len(options) == 1 else {"op": "or", "args": options},
                    label=f"{m.group('p')} % against {m.group('a')} / {m.group('b')} × 100 (every reading of the numerals)",
                    description=(f"{orig[:220]} [a per cent stated with the fraction it is worked from in brackets equals that fraction × 100, within "
                                 "half a point; one reading of the numerals holding is enough]"),
                    claim_ids=ctx.claims(orig, orig[:60]), defect="stem_arithmetic_slip"))


# ------------------------------------------------------------------------------------------------------------------ dated series
#: Nouns of one series however the text names it (the population: "1.250 habitantes", "212 vecinos", "268 personas", "la población").
_POPULATION_STEMS = frozenset({"habit", "vecin", "perso", "pobla", "resid"})
_POPULATION_RE = re.compile(r"\b(?:poblaci[oó]n|habitantes|vecinos|personas|residentes)\b", re.IGNORECASE)
_NOW_POINT = r"hoy|la\s+actualidad|ahora"
_PERIOD_RE = re.compile(r"\b(?:entre\s+(?P<p1>" + _ES_YEAR + r")\s+y\s+(?P<p2>" + _ES_YEAR + r"|" + _NOW_POINT + r")|"
                        r"(?:de|desde)\s+(?P<q1>" + _ES_YEAR + r")\s+(?:a|hasta)\s+(?P<q2>" + _ES_YEAR + r"|" + _NOW_POINT + r")|"
                        # c3e: 'desde 2015' alone with a present perfect runs to today ("Desde 2015 la población ha crecido un 36 %")
                        r"desde\s+(?:el\s+(?:año\s+)?)?(?P<s1>" + _ES_YEAR + r")(?!\s+(?:a|hasta|y)\b))\b", re.IGNORECASE)
_PRESENT_PERFECT_RE = re.compile(r"\b(?:ha|han)\s+[^\W\d_]{2,20}(?:ado|ido|ído|to|cho)\b", re.IGNORECASE)


def _period_points(per: "re.Match[str]", sent: str) -> tuple[Optional[str], Optional[str]]:
    """The two points of a period: its two years (or a year and today); 'desde' a year alone only with a present perfect (to today)."""
    if per.group("s1"):
        return (_point(per.group("s1")), "hoy") if _PRESENT_PERFECT_RE.search(sent) else (None, None)
    return _point(per.group("p1") or per.group("q1")), _point(per.group("p2") or per.group("q2"))
_PCT_BOUND_RE = re.compile(r"\b(?P<cmp>m[aá]s|menos)\s+(?:del?|de\s+un)\s*+$", re.IGNORECASE)
_LOSS_RE = re.compile(r"\b(?:perdi[oó]|perdieron|(?:ha|han)\s+perdido)\b", re.IGNORECASE)
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


_SINCE_RE = re.compile(r"\b(?:en|in)\s+(?P<y1>(?:1[5-9]|20)\d{2})\b[^.;\n]{0,80}?\b(?:llevaba(?:n)?|hac[ií]a|had\s+been\s+\w+\s+for)\s+"
                       r"(?P<n>\d{1,3}|[^\W\d_]{2,12}(?:\s+y\s+[^\W\d_]{2,8})?)\s+(?:años|years)\b[^.;\n]{0,60}?\(?\s*(?:desde|since)\s+(?:el\s+)?(?P<y0>(?:1[5-9]|20)\d{2})\b",
                       re.IGNORECASE)


#: A duration stated with the two years it spans in brackets (c3e, check round 10 of c3d: "La fibra óptica llegó diez años después del
#: cierre de la escuela (de 2009 a 2021)", "twelve years later (2009 to 2021)").
_YEARS_PAIR_RE = re.compile(r"(?<![\d.,])(?P<n>\d{1,3}|[^\W\d_]{2,12}(?:\s+y\s+[^\W\d_]{2,8})?)\s+(?:años|years)\b[^.;()\n]{0,80}?\(\s*+(?:(?:de|desde|from|entre|between)\s+)?"
                            r"(?P<y0>(?:1[5-9]|20)\d{2})\s*+(?:a|hasta|y|to|and|–|—|-)\s*+(?P<y1>(?:1[5-9]|20)\d{2})\s*+\)", re.IGNORECASE)


_AGE_BEFORE_RE = re.compile(r"(?:,\s*+de|\b(?:con|a\s+los|ten[ií]a|tiene|ten[ií]an|tienen|cumpli[oó]|cumple|aged|at\s+age|at\s+the\s+age\s+of))\s++$",
                            re.IGNORECASE)
_AGE_AFTER_RE = re.compile(r"\s+(?:años|years)\s+(?:de\s+edad|old)\b|-year-old", re.IGNORECASE)


def _durations_since(ctx: _Ctx) -> None:
    """Check round 9 of c3c (sp-t14): a duration stated at a year and counted from another ("En 2015 la escuela llevaba nueve años
    cerrada (desde 2009)."): the difference of the two years. Number words are read as their digits."""
    from ..adapters.history_specialist.sentences import split_sentences
    for para in ctx.regions.paragraphs:
        if not re.search(r"\d{4}", para):
            continue
        for orig in split_sentences(para):
            sent = _normalise_es_figures(orig)
            for m in _SINCE_RE.finditer(sent):
                n = int(m.group("n")) if m.group("n").isdigit() else _small(m.group("n"))
                y1, y0 = int(m.group("y1")), int(m.group("y0"))
                if n is None or y1 < y0:
                    continue
                ctx.add("lb_dated_change", lambda cid, n=n, y1=y1, y0=y0, m=m, sent=sent: make_check(
                    ctx.report, check_id=cid, kind="lb_dated_change", inputs=[("stated", Fraction(n), f"the duration stated ({m.group('n')} years)")],
                    conclusion={"op": "eq", "left": _var("stated"), "right": _real(Fraction(y1 - y0))},
                    label=f"the duration stated ({n} years) against {y1} − {y0} = {y1 - y0}",
                    description=f"{sent[:220]} [a duration at one year counted from another is the difference of the two years]",
                    claim_ids=ctx.claims(orig, m.group(0)[:60]), severity="warning", defect="stem_arithmetic_slip"))
            for m in _YEARS_PAIR_RE.finditer(sent):
                n = int(m.group("n")) if m.group("n").isdigit() else _small(m.group("n"))
                y0, y1 = sorted((int(m.group("y0")), int(m.group("y1"))))
                if n is None or _AGE_BEFORE_RE.search(sent, max(0, m.start() - 30), m.start()) or \
                        _AGE_AFTER_RE.match(sent, m.start("n") + len(m.group("n"))):
                    continue  # a person's age ("Mi tía, de 40 años, ...", "Con 30 años se fue ...", "aged 40", "40 years old"): no
                    # duration of the bracketed years (check round 11 of c3e)
                ctx.add("lb_dated_change", lambda cid, n=n, y1=y1, y0=y0, m=m, sent=sent: make_check(
                    ctx.report, check_id=cid, kind="lb_dated_change", inputs=[("stated", Fraction(n), f"the duration stated ({m.group('n')} years)")],
                    conclusion={"op": "eq", "left": _var("stated"), "right": _real(Fraction(y1 - y0))},
                    label=f"the duration stated ({n} years) against its bracketed years {y1} − {y0} = {y1 - y0}",
                    description=f"{sent[:220]} [a duration stated with the two years it spans in brackets is their difference]",
                    claim_ids=ctx.claims(orig, m.group(0)[:60]), severity="warning", defect="stem_arithmetic_slip"))


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
        if pi in excluded or not (re.search(r"\d", para) or _ES_NUMBER_WORD_HINT_RE.search(para)):
            continue
        for sent in split_sentences(para):
            en, sp, _n = es.english_ratio(sent)
            if en > sp:
                continue
            # (a per cent or a difference in Spanish number words, "cayó un treinta y ocho por ciento", is read as its digits, as the
            # from-to readers read it: the push check's still-partial item, check round 9 of c3c)
            sent = _normalise_es_figures(sent)
            if _ES_FROM_TO_RE.search(sent) or not re.search(r"\d", sent):
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
    p1, p2 = _period_points(per, sent)
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
_PERIOD_SIZE_RE = re.compile(r"\b(?:gan[oó]|ganaron|perdi[oó]|perdieron|(?:ha|han)\s+(?:ganado|perdido)|(?:creci[oó]|cay[oó]|aument[oó]|disminuy[oó]|baj[oó]|subi[oó]|"
                             r"(?:ha|han)\s+(?:crecido|ca[ií]do|aumentado|disminuido|bajado|subido))\s+en)\s+"
                             r"(?P<ap>unos\s+|unas\s+|casi\s+|aproximadamente\s+)?(?P<n>" + _ES_NUM + r")(?![\d,.]\d)\s+(?:[^\W\d_]{2,20})", re.IGNORECASE)


def _period_size(ctx: _Ctx, sent: str, series: dict, sev: str) -> None:
    """Attack round 4 (sp-t14): the size of a change over a period against the supplied text's figures for its two points: |b - a|
    within half a unit (5% after "unos"), every reading of the numerals. A bound ("más de mil") is left to the bound readers."""
    per = _PERIOD_RE.search(sent)
    m = _PERIOD_SIZE_RE.search(sent)
    if per is None or m is None or re.search(r"\b(?:m[aá]s|menos)\s+de\s*+$", sent[:m.start("n")]):
        return
    p1, p2 = _period_points(per, sent)
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
                             # (c3e: the present perfect too, "Desde 2015 el pueblo ha ganado 56 vecinos")
                             r"(?:ha|han)\s+(?:perdido|ganado|crecido|ca[ií]do|bajado|subido|aumentado|disminuido|descendido)|se\s+han?\s+reducido|"
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
    # (each word by its concept in the closed bilingual gloss, else its first five letters: "The school had been closed since 2003"
    # meets "la escuela llevaba cerrada desde 2009", attack round 8)
    return {es.concept(w) for w in re.findall(r"[^\W\d_]{4,40}", clause) if w.casefold() not in _CONTEXT_STOP and
            w.casefold() not in _EVENT_STOP and w.casefold() not in _EN_EVENT_STOP}


_RELATIVE_YEAR_RE = re.compile(r"\b(?:despu[eé]s|antes|after|before|later|earlier|tras)\s+(?:de\s+|of\s+|than\s+)?(?:1[89]\d{2}|20\d{2})\b", re.IGNORECASE)
_EN_EVENT_STOP = frozenset("text article says said that this with from have been were when where there their which".split())


_ES_YEAR_WORDS_RE = re.compile(r"\b(?:dos\s+mil|mil\s+(?:novecientos|ochocientos))\b", re.IGNORECASE)


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
        if pi in excluded or not (_YEAR_IN_RE.search(para) or _ES_YEAR_WORDS_RE.search(para)):
            continue
        for orig in para.split("\n"):
            # c3e (check round 10 of c3d): a year written in Spanish words is read as its digits ("La fibra óptica llegó en dos mil
            # veintidós"); the claim is still found by the line as written
            line = _normalise_es_figures(orig) if _ES_YEAR_WORDS_RE.search(orig) else orig
            # a line credited to the text is an error when wrong; an uncredited line, Spanish or English, a warning (attack round 8:
            # "La fibra óptica llegó en 2012.", "The school had been closed since 2003.")
            credited = es.SPANISH_CREDIT_RE.search(line) is not None or re.search(r"\b(?:according\s+to|the\s+(?:text|article)\s+(?:says|states))\b", line, re.IGNORECASE) is not None
            if _ARROW_LINE_RE.match(line) or (ctx.task not in ("reading", "notes") and not credited):
                continue
            for clause in _CLAUSE_SPLIT_RE.split(line):
                ys = _YEAR_IN_RE.findall(clause)
                if len(ys) != 1 or re.search(r"\d", _YEAR_IN_RE.sub("", clause)) or _RELATIVE_YEAR_RE.search(clause):
                    continue  # a clause with a figure besides its year is the figure readers'; "seis años después de 2015": the year is the
                    # reference point of a relative date, never the event's (attack round 8)
                mine = _content_stems(clause)
                scored = sorted(((len(mine & st), y, doc) for st, y, _all, doc in events), key=lambda x: -x[0])
                if not scored or scored[0][0] < 2 or (len(scored) > 1 and scored[1][0] == scored[0][0] and scored[1][1] != scored[0][1]):
                    continue
                _n2, year, doc = scored[0]
                stated = ys[0]
                ctx.add("supplied_figure", lambda cid, year=year, stated=stated, clause=clause, doc=doc, line=line, credited=credited: make_check(
                    ctx.report, check_id=cid, kind="supplied_figure", inputs=[("year", int(year), f"the year the supplied text gives this event ({year})")],
                    conclusion={"op": "eq", "left": _var("year"), "right": _real(int(stated))},
                    label=f"the year {stated} the answer credits to the text for '{clause.strip()[:80]}' equals the year {year} in {doc}",
                    description=(f"an event's year credited to a supplied text: '{line[:200]}' against {doc} ({year}) [rule: an event taken from a "
                                 "supplied text keeps the text's year]"),
                    claim_ids=ctx.claims(orig, orig[:60] if line is not orig else stated), severity="error" if credited else "warning", defect="source_mismatch"))


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


# ------------------------------------------------------------------------------------------------------------------ attack round 8
#: A count written in digits or in a small English or Spanish number word.
_SMALL_COUNT = r"\d{1,3}|" + "|".join(sorted((w for w in es.SMALL_NUMBER_WORDS if len(w) > 2), key=len, reverse=True))


def _small(w: str) -> Optional[int]:
    w = w.casefold()
    return int(w) if w.isdigit() else es.SMALL_NUMBER_WORDS.get(w)


def _target_texts(ctx: _Ctx) -> list[tuple[str, str]]:
    """``(name, text)`` of the productions and texts a statement can be about: the student's text, the supplied texts, the model."""
    out = []
    if ctx.regions.student_text is not None:
        out.append(("the student's text", ctx.regions.student_text))
    for t in ctx.report.supplied_texts:
        if not (t.document_id or "").startswith("peer:") and t.text and t.text != ctx.regions.student_text:
            out.append((t.document_id, t.text[:MAX_REGION]))
    if ctx.regions.model_text:
        out.append(("the model", ctx.regions.model_text))
    return out


def _subject_text(ctx: _Ctx, subject: str) -> Optional[tuple[str, str]]:
    """The one text a statement's subject names: 'your email' / 'tu correo' the student's text, 'the model' / 'the article' the model
    (a writing task) or the one supplied text, 'the poem' / 'the text' / 'the extract' the one supplied text."""
    s = " ".join(subject.casefold().split())
    docs = [(t.document_id, t.text[:MAX_REGION]) for t in ctx.report.supplied_texts
            if not (t.document_id or "").startswith("peer:") and t.text and t.text != ctx.regions.student_text]
    if s.startswith(("your", "tu ", "the student")) and ctx.regions.student_text is not None:
        return "the student's text", ctx.regions.student_text
    if ("model" in s or (ctx.task == "writing" and ("article" in s or "text" in s or "email" in s or "letter" in s))) and ctx.regions.model_text:
        return "the model", ctx.regions.model_text
    if len(docs) == 1 and not s.startswith(("your", "tu ")):
        return docs[0]
    return None


def _blocks(text: str) -> list[list[str]]:
    """The blank-line blocks of a text, each its non-empty lines."""
    return [[ln for ln in b.split("\n") if ln.strip()] for b in _PARA_RE.split(text[:MAX_REGION]) if b.strip()][:2000]


#: A structural count of a production or a supplied text: "Your email has seven paragraphs between the greeting and the sign-off", "The
#: poem has five stanzas", "The poem has twenty lines in four stanzas of six lines".
_STRUCT_SUBJ = (r"(?P<subj>your\s+(?:email|e-mail|text|letter|essay|draft|article|composition)|tu\s+(?:correo|texto|carta|redacción)|"
                r"the\s+(?:poem|text|extract|passage|song|article|email|e-mail|letter|model(?:\s+(?:text|article|email|letter))?|story)|el\s+(?:poema|texto|modelo|correo))")
_STRUCT_RE = re.compile(r"\b" + _STRUCT_SUBJ + r"\s+(?:has|had|contains|consists\s+of|is\s+made\s+up\s+of|is\s+divided\s+into|is\s+written\s+in|runs\s+to|tiene|consta\s+de)"
                        r"\s+(?P<body>[^.;\n]{1,160})", re.IGNORECASE)
_STRUCT_UNIT_RE = re.compile(r"(?P<n>" + _SMALL_COUNT + r")\s+(?P<u>paragraphs?|stanzas?|verses?|lines?|párrafos?|estrofas?|versos?|líneas?)"
                             r"(?:\s+(?:of|de)\s+(?P<m>" + _SMALL_COUNT + r")\s+(?P<mu>lines?|versos?|líneas?))?", re.IGNORECASE)
_BODY_ONLY_RE = re.compile(r"\bbetween\s+the\s+greeting\s+and\s+the\s+(?:sign-?off|closing)|\bin\s+the\s+body\b|\bentre\s+el\s+saludo\s+y\s+la\s+despedida", re.IGNORECASE)
#: "The body of the article has ...", "el cuerpo del artículo tiene ...": the article's own paragraphs (check round 9 of c3c).
_ARTICLE_BODY_RE = re.compile(r"\b(?:the\s+body\s+of|el\s+cuerpo\s+del?)\s+(?:the\s+|la\s+|el\s+)?(?:article|model|text|artículo|modelo|texto)\b", re.IGNORECASE)


def _structure(text: str, poem: bool) -> dict:
    """The structural counts of a text: its blocks (paragraphs or stanzas) whole and between a greeting and a closing, and its lines. A
    first block of one short line with no end mark is a title (a poem's), never a stanza."""
    blocks = _blocks(text)
    if blocks and len(blocks[0]) == 1 and len(blocks[0][0].split()) <= 8 and not re.search(r"[.!?:]\s*$", blocks[0][0]) and len(blocks) > 1:
        blocks = blocks[1:]
    body = list(blocks)
    if body and (es.greeting_line(body[0][0]) or es.header_line(body[0][0])) and len(body[0]) == 1:
        body = body[1:]
    if body and any(es.closing_line(ln) for ln in body[-1][:2]):
        body = body[:-1]
    # an article's body (check round 9 of c3c): its paragraphs of prose, without a note in italics, a headline, a byline or a note
    # after it (a word count, a bracketed note) — "The body of the article has seven paragraphs"
    art = [b for b in blocks if not _apparatus_block(b)]
    return {"blocks": len(blocks), "body": len(body), "article": len(art), "lines": sum(len(b) for b in blocks),
            "sizes": [len(b) for b in blocks]}


_BYLINE_RE = re.compile(r"^\s*(?:por|by|de|autor(?:a)?\s*:|author\s*:)\s+\S", re.IGNORECASE)
_NOTE_BLOCK_RE = re.compile(r"^\s*(?:\*[^*\n].*\*|_[^_\n].*_|\(.*\)|\[.*\]|(?:word\s+count|words|palabras|número\s+de\s+palabras|nota|note)\b.*)\s*$",
                            re.IGNORECASE)


def _apparatus_block(block: list[str]) -> bool:
    """A block that is no paragraph of an article's body: one line that is a headline (short, no end stop), a byline, or a note
    (in italics or brackets, a word count)."""
    if len(block) != 1:
        return False
    ln = block[0].strip()
    if _NOTE_BLOCK_RE.match(ln) or _BYLINE_RE.match(ln):
        return True
    return len(ln.split()) <= 12 and not re.search(r"[.!:]\s*$", ln)


def _structural_counts(ctx: _Ctx, statements: list[_Stmt]) -> None:
    for st in statements:
        m = _STRUCT_RE.search(st.text)
        if m is None:
            continue
        target = _subject_text(ctx, m.group("subj"))
        if target is None:
            continue
        name, text = target
        poem = "poem" in m.group("subj").casefold() or "poema" in m.group("subj").casefold()
        info = _memo(ctx, ("structure", name), lambda text=text, poem=poem: _structure(text, poem))
        body_only = _BODY_ONLY_RE.search(st.text) is not None
        for u in _STRUCT_UNIT_RE.finditer(m.group("body")):
            n = _small(u.group("n"))
            unit = es.concept(u.group("u"))
            if n is None or unit not in ("paragraph", "stanza", "line"):
                continue
            if unit == "line":
                measured = [info["lines"]]
                what = "lines"
            elif _ARTICLE_BODY_RE.search(st.text):
                measured = [info["article"]]
                what = "body paragraphs (without its headline, byline and notes)"
            else:
                measured = [info["body"]] if body_only else sorted({info["blocks"], info["body"], info["article"]})
                what = "blocks between the greeting and the closing" if body_only else "blocks (with or without a greeting and a closing)"
            inputs = [("stated", Fraction(n), f"the count stated ({u.group(0)})")]
            options = [{"op": "eq", "left": _var("stated"), "right": _real(Fraction(c))} for c in measured]
            concl = options[0] if len(options) == 1 else {"op": "or", "args": options}
            if u.group("m"):
                mm = _small(u.group("m"))
                if mm is not None:
                    odd = sum(1 for size in info["sizes"] if size != mm)
                    inputs.append(("odd", Fraction(odd), f"the blocks of {name} not of {mm} lines ({odd})"))
                    concl = {"op": "and", "args": [concl, {"op": "eq", "left": _var("odd"), "right": _real(Fraction(0))}]}
            ctx.add("lb_structure_count", lambda cid, inputs=inputs, concl=concl, st=st, u=u, name=name, what=what, measured=measured: make_check(
                ctx.report, check_id=cid, kind="lb_structure_count", inputs=inputs, conclusion=concl,
                label=f"{u.group(0)} against {name}'s {what} ({', '.join(str(x) for x in measured)})",
                description=f"{st.text[:220]} [a count of a text's paragraphs, stanzas or lines equals the count of the text as written]",
                claim_ids=ctx.claims(st.text, u.group(0)), severity="warning", defect="invented_figure"))


#: How often a quoted form occurs in a text: '"ándale" appears three times in a row in the poem'.
_OCCURS_RE = re.compile(r"[«\"“](?P<q>[^»\"”\n]{1,80})[»\"”]\s+(?:appears|occurs|is\s+used|is\s+repeated|is\s+said|comes|aparece|se\s+repite)\s+"
                        r"(?P<k>once|twice|(?:" + _SMALL_COUNT + r")\s+times|una\s+vez|dos\s+veces|(?:" + _SMALL_COUNT + r")\s+veces)(?P<row>\s+in\s+a\s+row|\s+seguid[oa]s?)?"
                        r"(?:\s+in\s+(?P<subj>the\s+(?:poem|text|extract|passage|song|article|model)|your\s+(?:email|text|letter)))?", re.IGNORECASE)


def _occurrence_counts(ctx: _Ctx, statements: list[_Stmt]) -> None:
    for st in statements:
        for m in _OCCURS_RE.finditer(st.text):
            target = _subject_text(ctx, m.group("subj") or "the text")
            if target is None:
                continue
            k = m.group("k").casefold().split()
            n = 1 if k[0] in ("once", "una") else 2 if k[0] in ("twice",) else _small(k[0])
            if n is None:
                continue
            form = _norm_quote(m.group("q"))
            if not form:
                continue
            words = re.findall(r"[^\W_]+", target[1].casefold())
            fw = form.split()
            hits = [i for i in range(len(words) - len(fw) + 1) if words[i:i + len(fw)] == fw][:400] if len(fw) <= 6 else []
            if m.group("row"):
                best, run = 0, 0
                for j, i in enumerate(hits):
                    run = run + 1 if j and i == hits[j - 1] + len(fw) else 1
                    best = max(best, run)
                measured = best
            else:
                measured = len(hits)
            ctx.add("lb_occurrence_count", lambda cid, n=n, measured=measured, m=m, st=st, target=target: make_check(
                ctx.report, check_id=cid, kind="lb_occurrence_count", inputs=[("found", Fraction(measured), f"occurrences of «{m.group('q')[:60]}» in {target[0]}"
                                                                                                      f"{' in a row' if m.group('row') else ''} ({measured})")],
                conclusion={"op": "eq", "left": _var("found"), "right": _real(Fraction(n))},
                label=f"«{m.group('q')[:60]}» occurs {m.group('k')}{m.group('row') or ''} in {target[0]}",
                description=f"{st.text[:220]} [how often a quoted form occurs in a text equals the count of the text as written (whole words, case folded)]",
                claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="invented_figure"))


#: A count of items a text lists by ordinals: "Tu correo da cuatro cosas que aprendiste", "Your email gives four things you learned".
_ENUM_CLAIM_RE = re.compile(r"\b(?P<subj>tu\s+(?:correo|texto|carta)|your\s+(?:email|e-mail|text|letter|draft)|the\s+(?:model|article))\s+"
                            r"(?:da|menciona|incluye|tiene|presenta|explica|enumera|propone|gives|lists|mentions|includes|has|names|explains|offers|proposes|"
                            r"suggests|makes|puts\s+forward)\s+(?P<n>" + _SMALL_COUNT + r")\s+(?P<noun>[^\W\d_]{4,20})", re.IGNORECASE)
_ORDINALS = ("primero", "segundo", "tercero", "cuarto", "quinto", "sexto", "first", "second", "third", "fourth", "fifth", "sixth",
             "en primer lugar", "en segundo lugar", "en tercer lugar", "en cuarto lugar", "firstly", "secondly", "thirdly", "fourthly")
_ORDINAL_RE = re.compile(r"(?:^|(?<=[.!?:\n]))\s*+(?P<o>en\s+(?:primer|segundo|tercer|cuarto|quinto)\s+lugar|primero|segundo|tercero|cuarto|quinto|sexto|"
                         r"first(?:ly)?|second(?:ly)?|third(?:ly)?|fourth(?:ly)?|fifth(?:ly)?)\s*+,", re.IGNORECASE)
_ORDINAL_PROPOSAL_RE = re.compile(r"\b(?:mi|la|una|the|my)\s+(?P<o>primera|segunda|tercera|cuarta|quinta|first|second|third|fourth|fifth)\s+(?:propuesta|medida|"
                                  r"raz[oó]n|idea|proposal|measure|reason)\b", re.IGNORECASE)
_ORDINAL_RANK = {"primer": 1, "primero": 1, "primera": 1, "first": 1, "firstly": 1, "segundo": 2, "segunda": 2, "second": 2, "secondly": 2,
                 "tercer": 3, "tercero": 3, "tercera": 3, "third": 3, "thirdly": 3, "cuarto": 4, "cuarta": 4, "fourth": 4, "fourthly": 4,
                 "quinto": 5, "quinta": 5, "fifth": 5, "fifthly": 5, "sexto": 6, "sixth": 6}
#: A count the text states of its own items ("propongo dos medidas", "two measures").
_OWN_COUNT_RE = re.compile(r"(?P<n>" + _SMALL_COUNT + r")\s+(?P<noun>[^\W\d_]{4,20})", re.IGNORECASE)


def _enumerated_counts(ctx: _Ctx, statements: list[_Stmt]) -> None:
    for st in statements:
        for m in _ENUM_CLAIM_RE.finditer(st.text):
            n = _small(m.group("n"))
            target = _subject_text(ctx, m.group("subj"))
            if n is None or target is None:
                continue
            noun = es.concept(m.group("noun"))
            if noun in ("paragraph", "stanza", "line", "word"):
                continue  # a count of a text's parts or words: the structure and word-count readers'
            name, text = target
            # the text's own count of the same items ("propongo dos medidas"), else the highest rank of its ordinals ("Primero, ...
            # Segundo, ... Tercero, ...", "En primer lugar ... Mi segunda propuesta")
            own = {(_small(x.group("n"))) for x in _OWN_COUNT_RE.finditer(text) if es.concept(x.group("noun")) == noun and _small(x.group("n"))}
            ranks = [_ORDINAL_RANK.get(o.group("o").casefold().split()[-2] if o.group("o").casefold().startswith("en ") else o.group("o").casefold(), 0)
                     for o in _ORDINAL_RE.finditer(text)]
            ranks += [_ORDINAL_RANK.get(o.group("o").casefold(), 0) for o in _ORDINAL_PROPOSAL_RE.finditer(text)]
            if len(own) == 1:
                measured, how = own.pop(), f"the count {name} states itself"
            elif ranks and max(ranks) >= 2:
                measured, how = max(ranks), f"the ordinals {name} lists its items by (up to the {max(ranks)}th)"
            else:
                continue
            ctx.add("lb_listed_count", lambda cid, n=n, measured=measured, how=how, m=m, st=st: make_check(
                ctx.report, check_id=cid, kind="lb_listed_count", inputs=[("listed", Fraction(measured), f"{how} ({measured})")],
                conclusion={"op": "eq", "left": _var("listed"), "right": _real(Fraction(n))},
                label=f"{m.group('n')} {m.group('noun')} against {how} ({measured})",
                description=f"{st.text[:220]} [a count of the items a text gives equals the count the text states, or the ordinals it lists them by]",
                claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="invented_figure"))


#: The categories of the answer's own corrections, by the words of each correction's explanation (subjunctive first, then ser/estar,
#: then agreement, then tense, spelling and accents).
_CATEGORIES = (("subjunctive", re.compile(r"\bsubjunctive|subjuntivo", re.IGNORECASE)),
               ("ser/estar", re.compile(r"\bser\s*+/\s*+estar|\btakes\s+(?:ser|estar)\b|\b(?:ser|estar)\s+(?:for|is\s+used)|\bser\s+and\s+estar", re.IGNORECASE)),
               ("agreement", re.compile(r"\bagree|\bagreement|\bfeminine|\bmasculine|\bplural|\bsingular|\bgender\b|concordancia", re.IGNORECASE)),
               ("tense", re.compile(r"\bpreterite|\bimperfect|\btense\b|pret[eé]rito", re.IGNORECASE)),
               ("spelling", re.compile(r"\bspell|\baccent|ortograf|\btilde", re.IGNORECASE)))
_CAT_WORD = r"(?P<cat>agreement|concordancia|(?:the\s+)?subjunctive|subjuntivo|ser\s*+/\s*+estar|ser\s+and\s+estar|tenses?|spelling|accents?)"
_CAT_COUNT_RES = (re.compile(r"\b" + _CAT_WORD + r"\b[^()\n.;]{0,50}?\((?P<n>" + _SMALL_COUNT + r")\)", re.IGNORECASE),
                  re.compile(r"\b(?P<n>" + _SMALL_COUNT + r")\s+(?:for|in|on|with)\s+(?:the\s+)?" + _CAT_WORD + r"\b", re.IGNORECASE),
                  re.compile(r"\b(?P<n>" + _SMALL_COUNT + r")\s+" + _CAT_WORD + r"\s+(?:errors?|mistakes?|corrections?|points?)\b", re.IGNORECASE))
_TOTAL_PARTS_RE = re.compile(r"\b(?P<n>" + _SMALL_COUNT + r")\s+(?:corrections|errors|mistakes|points)\b[^:\n]{0,40}:\s*+(?P<parts>[^.\n]{3,240})", re.IGNORECASE)


def _category_of(explanation: str) -> Optional[str]:
    for name, rx in _CATEGORIES:
        if rx.search(explanation):
            return name
    return None


def _cat_key(word: str) -> str:
    w = " ".join(word.casefold().replace("the ", "").split())
    if "subj" in w:
        return "subjunctive"
    if "ser" in w and "estar" in w:
        return "ser/estar"
    if w.startswith(("agree", "concord")):
        return "agreement"
    if w.startswith("tense"):
        return "tense"
    return "spelling"


def _category_counts(ctx: _Ctx, statements: list[_Stmt]) -> None:
    """Attack round 8 (sp-t16): a count of the answer's own corrections by category ("agreement (three)", "two for the subjunctive", "one
    ser/estar error"), and a total stated with its parts ("six corrections above: four for agreement, two ... and one ..."), against the
    correction lines the answer lists, each categorised by the words of its explanation."""
    lines = [ctx.text[m.start():ctx.text.find("\n", m.start()) if ctx.text.find("\n", m.start()) >= 0 else len(ctx.text)]
             for m in _ARROW_LINE_RE.finditer(ctx.text[:MAX_TEXT])][:200]
    if not lines:
        return
    counts: dict[str, int] = {}
    for ln in lines:
        expl = ln[ln.rfind("(") :] if "(" in ln else ln
        cat = _category_of(expl)
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    model = set(ctx.regions.model)
    for st in statements:
        if st.paragraph in model:
            continue
        seen: set[tuple[int, str]] = set()
        for rx in _CAT_COUNT_RES:
            for m in rx.finditer(st.text):
                n = _small(m.group("n"))
                cat = _cat_key(m.group("cat"))
                if n is None or (m.start(), cat) in seen:
                    continue
                seen.add((m.start(), cat))
                have = counts.get(cat, 0)
                ctx.add("lb_listed_count", lambda cid, n=n, have=have, cat=cat, m=m, st=st: make_check(
                    ctx.report, check_id=cid, kind="lb_listed_count", inputs=[("listed", Fraction(have), f"the answer's {cat} corrections ({have})")],
                    conclusion={"op": "eq", "left": _var("listed"), "right": _real(Fraction(n))},
                    label=f"{m.group('n')} {cat} corrections against the {have} the answer lists",
                    description=f"{st.text[:220]} [a count of the answer's own corrections of a category equals the correction lines of that category]",
                    claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="invented_figure"))
        for m in _TOTAL_PARTS_RE.finditer(st.text):
            total = _small(m.group("n"))
            parts = [_small(x) for x in re.findall(r"\b(" + _SMALL_COUNT + r")\s+(?:for|in|on|with)\b", m.group("parts"), re.IGNORECASE)]
            if total is None or len(parts) < 2 or any(p is None for p in parts):
                continue
            s = sum(parts)
            ctx.add("lb_listed_count", lambda cid, total=total, s=s, m=m, st=st: make_check(
                ctx.report, check_id=cid, kind="lb_listed_count", inputs=[("parts", Fraction(s), f"the sum of the parts stated ({s})")],
                conclusion={"op": "eq", "left": _var("parts"), "right": _real(Fraction(total))},
                label=f"the parts stated sum to the total {m.group('n')}",
                description=f"{st.text[:220]} [a total stated with its parts equals their sum]",
                claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="invented_figure"))


#: A byline claim: "The byline names Marta Ruiz Pérez as the author", "written by ...", "The author is ...".
_NAME = r"(?P<{g}>[A-ZÁÉÍÓÚÑ][\wáéíóúñ'’-]{{1,30}}+(?:\s[A-ZÁÉÍÓÚÑ][\wáéíóúñ'’-]{{1,30}}+){{0,3}})"
_BYLINE_VERB = r"(?:names|gives|credits|reads|says|shows|lists|identifies|describes|presents|attributes\s+it\s+to|puts)"
_BYLINE_CLAIM_RE = re.compile(r"\bbyline\s+" + _BYLINE_VERB + r"\s+" + _NAME.format(g="a") + r"|\b(?:written|signed)\s+by\s+" + _NAME.format(g="b")
                              + r"|\bthe\s+(?:author|writer)\s+(?:is|was)\s+" + _NAME.format(g="c")
                              # what else the byline is said to state, with no name first ("The byline credits a student in 1.º de Bachillerato": c3d):
                              # its capitalised words and its figures (a course year, an ordinal) are the byline's own
                              + r"|\bbyline\s+" + _BYLINE_VERB + r"\s+(?P<d>(?:an?|the|one)\s[^.;\n]{2,120})")
_BYLINE_FIGURE_RE = re.compile(r"\d{1,4}")


def _byline_claims(ctx: _Ctx, statements: list[_Stmt]) -> None:
    byline = ctx.regions.byline
    if not byline:
        return
    held = {w.casefold() for w in re.findall(r"[^\W\d_]+", byline)} | set(_BYLINE_FIGURE_RE.findall(byline))
    for st in statements:
        for m in _BYLINE_CLAIM_RE.finditer(st.text):
            name = m.group("a") or m.group("b") or m.group("c")
            if name is None:
                name = m.group("d").strip()
                words = [w for w in re.findall(r"[^\W\d_]+", name) if w[:1].isupper()] + _BYLINE_FIGURE_RE.findall(name)
                if not words:
                    continue
            else:
                words = [w for w in re.findall(r"[^\W\d_]+", name)]
            missing = [w for w in words if w.casefold() not in held]
            ctx.add("lb_quoted_form", lambda cid, missing=missing, name=name, st=st, m=m: make_check(
                ctx.report, check_id=cid, kind="lb_quoted_form", inputs=[("missing", Fraction(len(missing)), f"words of '{name}' not in the byline ({', '.join(missing) or 'none'})")],
                conclusion={"op": "eq", "left": _var("missing"), "right": _real(Fraction(0))},
                label=f"the byline names {name}",
                description=f"{st.text[:220]} [a name the answer gives the model's byline is the byline's own: every word of it stands in the byline ('{byline[:80]}')]",
                claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="altered_quotation"))


#: A speaker named for a paraphrase of a text: "In your email your father says that Tomás can stay at your house.", or by name or title
#: ("Señora Rojas says that Tomás can stay at your house": c3d, sp-t16).
_KIN = r"father|dad|mother|mum|mom|grandmother|grandma|granny|grandfather|grandad|grandpa|brother|sister|friend|teacher"
_TITLE = r"(?:(?:Señora|Señor|Señorita|Sra\.|Sr\.|Srta\.|Mrs\.?|Mr\.?|Ms\.?|Miss|Doña|Don|Dr\.?)\s+)"
_CAP = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñ]{1,30}+"
_PARAPHRASE_RE = re.compile(r"(?:\b(?i:(?:it\s+is|it\s+was|it['’]s)\s+))?(?:\b(?i:(?:your|the\s+(?:student's|writer's|narrator's))\s+(?P<kin>" + _KIN + r"))|(?<![\w'’])(?P<name>"
                            + _TITLE + r"?" + _CAP + r"(?:\s" + _CAP + r")?))(?i:\s+(?:who|that))?\s+(?i:says|said|tells|told|thinks|thought|writes|wrote)\s+(?i:you\s+|us\s+)?"
                            r"(?i:that\s+)?(?P<content>[^.;\n]{3,200})")
#: Capitalised words that open a sentence or name no one: never a speaker's name.
_NOT_A_NAME = frozenset("the this that these those it he she they we you your i in on at as and but so then however also here there what which who when "
                        "where why how my our his her their its one some all each both every no not if because although while el la los las un una "
                        "ella él ellos ellas yo tu su mi".split())
_ES_KIN = r"padre|madre|abuela|abuelo|hermano|hermana|amigo|amiga|profesor|profesora|maestro|maestra|papá|mamá"
_ES_SPEECH_RE = re.compile(r"\b(?:(?:[Mm]i|[Tt]u|[Ss]u)\s+(?P<kin>" + _ES_KIN + r")|(?P<pron>[ÉE]l|Ella)|(?:(?:la|el)\s+)?(?P<name>(?:(?:[Ss]eñora|[Ss]eñor|[Dd]oña|[Dd]on)\s+)?"
                           + _CAP + r"))\s+(?:me\s+|nos\s+|le\s+|les\s+)?(?:dice|dijo|cuenta|contó|piensa|pensaba|cree|creía|explica|explicó)\s+(?:que\s+)?(?P<content>[^.;\n]{3,200})")
_ES_KIN_RE = re.compile(r"\b(?:mi|tu|su)\s+(?P<kin>" + _ES_KIN + r")\b", re.IGNORECASE)
#: The same in Spanish (c3e: "Tu abuelo dijo que los colores de las casas eran preciosos" was never read; the cleft "Es tu abuela quien dice
#: que ..." too).
_ES_PARAPHRASE_RE = re.compile(r"(?:\b(?i:(?:es|fue|era)\s+))?(?:\b(?i:(?:tu|su|el|la)\s+(?P<kin>" + _ES_KIN + r"))|(?<![\w'’])(?P<name>" + _TITLE + r"?" + _CAP
                               + r"(?:\s" + _CAP + r")?))(?i:\s+(?:quien|la\s+que|el\s+que))?\s+(?i:te\s+|le\s+|os\s+|les\s+|nos\s+)?(?i:dice|dijo|cuenta|contó|"
                               r"piensa|pensaba|cree|creía|escribe|escribió|explica|explicó|comenta|comentó)\s+(?i:que\s+)?(?P<content>[^.;\n]{3,200})")
_PARAPHRASE_STOP = frozenset(("your", "their", "that", "with", "this"))


def _name_key(name: str) -> str:
    """A named speaker's key: its capitalised words other than a title, case folded ('Señora Rojas' -> 'name:rojas')."""
    words = [w.casefold() for w in re.findall(r"[^\W\d_]+", name) if w[:1].isupper()]
    words = [w for w in words if w not in ("señora", "señor", "señorita", "sra", "sr", "srta", "mrs", "mr", "ms", "miss", "doña", "don", "dr")] or words
    return "name:" + " ".join(sorted(words))


def _cognates(text: str) -> set:
    """The content words of ``text`` as cognate keys: the concept of the closed gloss cut to four letters ('colours' and 'colores' meet as
    'colo', 'houses' and 'casas' as 'hous'), so a paraphrase across the two languages is matched by its shared stems (c3d)."""
    return {es.concept(w)[:4] for w in re.findall(r"[^\W\d_]{4,}", text) if w.casefold() not in _PARAPHRASE_STOP}


def _paraphrase_speakers(ctx: _Ctx, statements: list[_Stmt]) -> None:
    text = ctx.regions.student_text
    if text is None:
        return
    frames = []
    for m in _ES_SPEECH_RE.finditer(text[:MAX_REGION]):
        if m.group("name"):
            if m.group("name").split()[-1].casefold() in _NOT_A_NAME:
                continue
            who = _name_key(m.group("name"))
        else:
            kin = m.group("kin")
            if kin is None:
                prev = list(_ES_KIN_RE.finditer(text, max(0, m.start() - 300), m.start()))
                if not prev:
                    continue
                kin = prev[-1].group("kin")
            who = "kin:" + es.concept(kin)
        frames.append((who, _cognates(m.group("content"))))
        if len(frames) >= 64:
            break
    if not frames:
        return
    # a name the text sets beside a kin word ('mi madre, Ana,' / 'Ana, mi madre'): the same speaker
    linked: dict[str, set] = {}
    for x in re.finditer(r"\b(?:mi|tu|su)\s+(?P<kin>" + _ES_KIN + r")\s*+,\s*+(?P<n>" + _TITLE + r"?" + _CAP + r")|(?P<n2>" + _TITLE + r"?" + _CAP
                         + r")\s*+,\s*+(?:mi|tu|su)\s+(?P<kin2>" + _ES_KIN + r")\b", text[:MAX_REGION], re.IGNORECASE):
        k = "kin:" + es.concept(x.group("kin") or x.group("kin2"))
        linked.setdefault(k, set()).add(_name_key(x.group("n") or x.group("n2")))
    for st in statements:
        for m in [*_PARAPHRASE_RE.finditer(st.text), *_ES_PARAPHRASE_RE.finditer(st.text)]:
            if m.group("name"):
                first = m.group("name").split()[0].casefold()
                if first in _NOT_A_NAME or m.group("name").split()[-1].casefold() in _NOT_A_NAME:
                    continue
                claimed = _name_key(m.group("name"))
            else:
                claimed = "kin:" + es.concept(m.group("kin"))
            mine = _cognates(m.group("content"))
            scored = sorted(((len(mine & c), k) for k, c in frames), reverse=True)
            if not scored or scored[0][0] < 1 or (len(scored) > 1 and scored[1][0] == scored[0][0] and scored[1][1] != scored[0][1]):
                continue
            said_by = scored[0][1]
            same = claimed == said_by or claimed in linked.get(said_by, set()) or said_by in linked.get(claimed, set())
            who = m.group("kin") or m.group("name")
            shown = said_by.split(":", 1)[1]
            ctx.add("lb_quote_speaker", lambda cid, same=same, who=who, shown=shown, m=m, st=st: make_check(
                ctx.report, check_id=cid, kind="lb_quote_speaker", inputs=[("same", Fraction(1 if same else 0),
                                                                            f"whether the speaker named ({who}) is the one the student's text gives ({shown})")],
                conclusion={"op": "eq", "left": _var("same"), "right": _real(Fraction(1))},
                label=f"the paraphrase is credited to the speaker the student's text gives it ({shown})",
                description=(f"{st.text[:220]} [a paraphrase of the student's text keeps the text's speaker (the reported-speech frame its words match "
                             "best, by shared stems across the two languages; a name is that speaker only when the text sets it beside the kin word)]"),
                claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="source_mismatch"))


#: A quotation of a supplied text credited to a speaker the text gives with no quotation marks: '"¡Ojo, que quema!" is said by Doña Celia'.
_SAID_BY_CLAIM_RE = re.compile(r"[«\"“](?P<q>[^»\"”\n]{2,120})[»\"”]\s*+(?:,\s*+)?(?:is|was)\s+(?:said|spoken|shouted|whispered|called\s+out|used)\s+by\s+(?P<who>[^.;\n]{2,80})"
                               r"|(?<![\w'’])(?P<who2>[A-ZÁÉÍÓÚÑ][\wáéíóúñ]{1,30}+(?:\s[A-ZÁÉÍÓÚÑ][\wáéíóúñ]{1,30}+){0,2})\s+(?:says|said|shouts|tells\s+(?:him|her|them|the\s+narrator))\s+"
                               r"[«\"“](?P<q2>[^»\"”\n]{2,120})[»\"”]")
_EN_SAY_RE = re.compile(r"\b(?:said|says|told|tells|shouted|shouts|whispered|called|asked|asks|answered|replied|say)\b", re.IGNORECASE)


_SPEAKER_SKIP = frozenset(("I", "On", "For", "When", "The", "And", "But", "Tonight", "Nobody"))
_SAY_AFTER_FORM_RE = re.compile(r"[\s,.;:!¡?¿»\"”’]*+(?:(?P<pron>he|she|they|it)\s+(?:said|says|told|tells|shouted|shouts|whispered|called|asked|asks|"
                                r"answered|replied)\b|(?:said|says|told|shouted|whispered|called|asked|answered|replied)\s+(?P<nm>" + _CAP + r"(?:\s" + _CAP + r")?))")
_NAMED_DESCRIPTION_RE = re.compile(r"\bthe\s+(?P<d>(?:[a-z]{2,20}\s+){0,2}[a-z]{2,20})\s*+,\s*+(?P<n>" + _CAP + r"(?:\s" + _CAP + r")?)\s*+,")


@lru_cache(maxsize=16)
def _appositions(text: str) -> tuple[tuple[str, str], ...]:
    """``(description, name)`` of every 'the <description>, <Name>,' of a text, read once per text (at most 64)."""
    return tuple((a.group("d").casefold(), a.group("n")) for a in _NAMED_DESCRIPTION_RE.finditer(text))[:64]


def _capitalised(span: str) -> list[str]:
    return [w for w in re.findall(r"[^\W\d_]+", span) if w[:1].isupper() and w.casefold() not in _WHO_STOP and w not in _SPEAKER_SKIP
            and w.casefold() not in _NOT_A_NAME]


def _text_speaker(text: str, start: int, at: int, end: int) -> set:
    """The names a text gives the speaker of the words at ``text[at:end]``: the names before the speech verb of their sentence
    (``text[start:at]``); a speaker the sentence describes ('the grill cook ... says to me, ... échale ganas, mijo') named where the
    text sets a name beside that description ('the grill cook, Rubén,'); or a speech verb right after the words ('Ya merito, / she told
    it'), its pronoun the last name before them (c3d, sp-p10d). Empty when the text names none."""
    span = text[start:at]
    verbs = list(_EN_SAY_RE.finditer(span))
    if verbs:
        names = {w.casefold() for w in _capitalised(span[:verbs[-1].start()])}
        if names:
            return names
        head = span[:verbs[-1].start()].casefold()
        described = {n for d, n in _appositions(text[:MAX_REGION]) if re.search(r"\bthe\s+" + re.escape(d) + r"\b", head)}
        if len(described) == 1:
            return {w.casefold() for w in described.pop().split()}
        return set()
    after = _SAY_AFTER_FORM_RE.match(text, end, min(len(text), end + 60))
    if after is None:
        return set()
    if after.group("nm"):
        return {w.casefold() for w in after.group("nm").split()}
    if after.group("pron").casefold() == "it":
        return set()
    runs = re.findall(r"(?:" + _CAP + r")(?:\s" + _CAP + r")*", text[max(0, at - 300):at])
    runs = [r for r in runs if _capitalised(r)]
    return {w.casefold() for w in _capitalised(runs[-1])} if runs else set()


def _unquoted_speakers(ctx: _Ctx, statements: list[_Stmt]) -> None:
    docs = [(t.document_id, t.text[:MAX_REGION]) for t in ctx.report.supplied_texts if not (t.document_id or "").startswith("peer:") and t.text]
    if not docs:
        return
    for st in statements:
        for m in _SAID_BY_CLAIM_RE.finditer(st.text):
            q, who = (m.group("q") or m.group("q2")), (m.group("who") or m.group("who2"))
            claimed = {w.casefold() for w in re.findall(r"[^\W\d_]+", who) if w[:1].isupper()}
            if not claimed:
                continue
            for doc, text in docs:
                at = text.casefold().find(q.casefold().strip(" ¡!¿?.,"))
                if at < 0:
                    continue
                start = max(text.rfind(".", 0, at), text.rfind("\n\n", 0, at), text.rfind("!", 0, max(0, at - 1)), at - 300) + 1
                names = _text_speaker(text, start, at, at + len(q.strip(" ¡!¿?.,")))
                if not names:
                    break
                same = bool(claimed & names)
                ctx.add("lb_quote_speaker", lambda cid, same=same, who=who, names=names, doc=doc, st=st, q=q: make_check(
                    ctx.report, check_id=cid, kind="lb_quote_speaker", inputs=[("same", Fraction(1 if same else 0),
                                                                                f"whether the speaker named ({who.strip()[:60]}) is one {doc} gives ({', '.join(sorted(names))})")],
                    conclusion={"op": "eq", "left": _var("same"), "right": _real(Fraction(1))},
                    label=f"«{q[:60]}» is credited to the speaker {doc} gives it",
                    description=f"{st.text[:220]} [words of a supplied text keep the text's speaker: the names before the speech verb of their sentence]",
                    claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="source_mismatch"))
                break


#: A duration attached to a quoted form: 'The narrator was "el nuevo" for a month' against 'For a week I was el nuevo'.
_DURATION = r"(?P<GGn>a|an|one|" + _SMALL_COUNT + r")\s+(?P<GGu>days?|weeks?|months?|years?|nights?|hours?|días?|semanas?|mes(?:es)?|años?|noches?|horas?)"
_QUOTE_DURATION_RE = re.compile(r"[«\"“](?P<q>[^»\"”\n]{2,80})[»\"”][^.;\n]{0,40}?\b(?:for|during|durante)\s+" + _DURATION.replace("GG", "a")
                                + r"|\b(?:for|during|durante)\s+" + _DURATION.replace("GG", "b") + r"[^.;\n]{0,40}?[«\"“](?P<q2>[^»\"”\n]{2,80})[»\"”]", re.IGNORECASE)
_TEXT_DURATION_RE = re.compile(r"\b(?:for|during|durante)\s+" + _DURATION.replace("GG", "t"), re.IGNORECASE)


def _quote_durations(ctx: _Ctx, statements: list[_Stmt]) -> None:
    docs = _target_texts(ctx)
    for st in statements:
        for m in _QUOTE_DURATION_RE.finditer(st.text):
            q = m.group("q") or m.group("q2")
            n, u = (m.group("an"), m.group("au")) if m.group("q") else (m.group("bn"), m.group("bu"))
            stated = (_small(n), es.concept(u.rstrip("s") if u.endswith("s") and not u.endswith(("es", "as")) else u))
            for name, text in docs:
                at = text.casefold().find(q.casefold())
                if at < 0:
                    continue
                start = max(text.rfind(".", 0, at), text.rfind("\n\n", 0, at), at - 200) + 1
                end_ = min(x for x in (text.find(".", at), at + 200, len(text)) if x >= 0)
                given = [(_small(x.group("tn")), es.concept(x.group("tu"))) for x in _TEXT_DURATION_RE.finditer(text, start, end_)]
                if len(given) != 1 or None in given[0] or None in stated:
                    break
                same = given[0] == stated
                ctx.add("supplied_figure", lambda cid, same=same, given=given, m=m, st=st, name=name, q=q: make_check(
                    ctx.report, check_id=cid, kind="supplied_figure", inputs=[("same", Fraction(1 if same else 0), f"whether the duration stated is the one {name} gives "
                                                                                                                  f"with «{q[:40]}» ({given[0][0]} {given[0][1]})")],
                    conclusion={"op": "eq", "left": _var("same"), "right": _real(Fraction(1))},
                    label=f"the duration stated with «{q[:40]}» is the one {name} gives",
                    description=f"{st.text[:220]} [a duration stated with a quoted form is the one the text gives in the sentence that holds the form]",
                    claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="source_mismatch"))
                break


#: A count with its noun, in digits or in a small English or Spanish number word ("three bakeries", "tres palabras", "hace dos semanas").
#: (c3e: a hyphenated count too, "a two-week stay" is a count of weeks)
_COUNT_NOUN_RE = re.compile(r"(?<![\w.,-])(?P<n>" + _SMALL_COUNT + r")(?:\s+|-)(?P<noun>[^\W\d_]{4,20})\b", re.IGNORECASE)


def _worked_out(line: str, start: int, end: int) -> bool:
    """Whether the count at ``line[start:end]`` is worked out from the text's figures (a difference, the size of a change, a restatement,
    a figure with its operands): the frames of :func:`_derived_figure` other than a duration, which a text states as such ("hace dos
    semanas")."""
    after = line[end:end + 80]
    head = line[max(0, start - 60):start]
    if _COMPARATIVE_AFTER_RE.match(after) or _WORKED_AFTER_RE.match(after) or _APPOSITION_RE.search(head[-40:]):
        return True
    return bool(_CHANGE_VERB_RE.search(head) and not re.search(r"\bde\s*+$|\bfrom\s*+$|\ba\s*+$|\bto\s*+$", head))


_CC_SENT_RE = re.compile(r"[.!?;]\s|\n")
_CC_STOP = frozenset("that this with from have were their there which what when where they them then than your about into also some more "
                     "para pero como cuando donde porque desde hasta entre sobre todo todos este esta esto muy más años semanas".split())


def _cc_concepts(text: str) -> set:
    """The concepts of the content words of ``text`` (four letters or more, function words set aside; a bounded window)."""
    return {es.concept(w) for w in re.findall(r"[^\W\d_]{4,30}", text[:600]) if w.casefold() not in _CC_STOP and w.casefold() not in _CONTEXT_STOP}


def _request_task_text(request_text: str) -> str:
    """The sentences of the request written in Spanish (the task as set: 'Has pasado tres semanas de intercambio con una familia ...'),
    joined; '' when it writes none."""
    from ..adapters.history_specialist.sentences import split_sentences
    out = []
    for sent in split_sentences((request_text or "")[:MAX_REQUEST]):
        en_, sp_, _n = es.english_ratio(sent)
        if sp_ > en_:
            out.append(sent.strip(" '\"‘’“”"))
        if len(out) >= 40:
            break
    return " ".join(out)


def _cross_counts(ctx: _Ctx) -> None:
    """Attack round 8: a count the answer states with its noun against the count a text gives with the same noun, when the answer and the
    text are written in different languages ("three bakeries" against "dos panaderías", "tres palabras" against "two words": the closed
    bilingual gloss of :func:`.spanish_lexicon.concept`), or the text is the student's own (the core figure reader reads the other
    texts). Only a noun the text gives exactly one count for is read; a figure worked out from the text's figures (a difference, a change)
    is not compared."""
    texts = []
    targets = [(n, t) for n, t in _target_texts(ctx) if n != "the model"]
    task = _request_task_text(ctx.request_text) if ctx.task in ("writing", "marking") else ""
    if task:
        # the scenario a writing or marking task sets in the target language ("Has pasado tres semanas de intercambio ..."): a text the
        # answer's counts restate too ("The exchange lasted two weeks": c3d, sp-t16). A reading task's request sets statements to judge
        # ("La escuela volvió a abrir con más de veinte alumnos": a false statement), never facts, so it is not read
        targets.append(("the request's task", task))
    for name, text in targets:
        # each count with the concepts of its sentence: a count is compared only with the text's counts of a sentence that shares a
        # content word with the answer's line (attack round 8: "El intercambio duró tres semanas" is no restatement of "Ya hace dos semanas
        # que volví a Inglaterra")
        counts: dict[str, list] = {}
        body = text[:MAX_REGION]
        bounds = [0] + [x.end() for x in _CC_SENT_RE.finditer(body)] + [len(body)]
        ctx_of: dict[int, frozenset] = {}
        import bisect
        for m in _COUNT_NOUN_RE.finditer(body):
            v = _small(m.group("n"))
            if v is None or _YEAR_RE.match(m.group("n")) or m.group("noun").casefold() in _STOP_NOUNS:
                continue
            j = bisect.bisect_right(bounds, m.start()) - 1
            if j not in ctx_of:
                ctx_of[j] = frozenset(_cc_concepts(body[bounds[j]:bounds[min(j + 1, len(bounds) - 1)]]))
            key = es.concept(m.group("noun"))
            counts.setdefault(key, []).append((v, ctx_of[j] - {key}))
        # (c3e: the task's scenario is compared in either language, "El intercambio duró dos semanas" against "tres semanas de
        # intercambio": the core figure reader reads supplied texts, never the request)
        texts.append((name, es.is_spanish(text), counts, name in ("the student's text", "the request's task")))
    if not texts:
        return
    r = ctx.regions
    excluded = set(r.model) | set(r.disclaimer)
    for pi, para in enumerate(r.paragraphs):
        if pi in excluded:
            continue
        for line in para.split("\n"):
            if _ARROW_LINE_RE.match(line):
                continue  # a correction line quotes the student's forms, never a count of the text
            from bisect import bisect_right

            from ..adapters.markdown import find_quotation_spans
            quoted = sorted((a, b) for a, b, _q in find_quotation_spans(line, min_single_words=1))
            q_starts = [a for a, _b in quoted]
            q_reach: list[int] = []
            for _a, b in quoted:
                q_reach.append(max(b, q_reach[-1]) if q_reach else b)
            en_, sp_, _n = es.english_ratio(line)
            line_spanish = sp_ > en_
            for m in _COUNT_NOUN_RE.finditer(line):
                k = bisect_right(q_starts, m.start()) - 1  # (inside a quotation, by bisection: a scan of every span per figure was quadratic)
                if (k >= 0 and q_reach[k] > m.start()) or m.group("n").casefold() in ("a", "an", "un", "una", "uno", "one"):
                    continue
                v = _small(m.group("n"))
                key = es.concept(m.group("noun"))
                if v is None or len(key) < 4 or _worked_out(line, m.start(), m.end()):
                    continue
                mine = None
                for name, spanish, counts, own in texts:
                    if not own and spanish == line_spanish:
                        continue  # one language on both sides of another text: the core figure reader's
                    entries = counts.get(key, [])
                    if not entries or any(ev == v for ev, _c in entries):
                        continue  # the text gives the answer's count with this noun: nothing misread
                    if mine is None:
                        mine = frozenset(_cc_concepts(line)) - {key}
                    held = {ev for ev, c in entries if c & mine}
                    if len(held) != 1:
                        continue
                    h = next(iter(held))
                    ctx.add("supplied_figure", lambda cid, v=v, h=h, m=m, line=line, name=name: make_check(
                        ctx.report, check_id=cid, kind="supplied_figure", inputs=[("held", Fraction(h), f"the count {name} gives with this noun ({h})")],
                        conclusion={"op": "eq", "left": _var("held"), "right": _real(Fraction(v))},
                        label=f"{m.group(0)} against the count {name} gives ({h})",
                        description=f"{line[:200]} [a count stated with its noun equals the count the text gives with the same noun (a closed bilingual gloss)]",
                        claim_ids=ctx.claims(line, m.group(0)), severity="warning", defect="source_mismatch"))
                    break


#: A paraphrase located at a line of a text: 'The narrator puts a whole arm into the oven in the last line.'
_LINE_LOC_RE = re.compile(r"\b(?:in|on|at)\s+the\s+(?P<w>last|final|first|opening|closing)\s+line\b|\bin\s+line\s+(?P<k>\d{1,2})\b", re.IGNORECASE)
_LOC_STOP = frozenset("the a an in on at of to into onto and or his her their its my your last final first opening closing line poem narrator speaker "
                      "poet text writer says said does did is was are were has have had into with from".split())


def _line_paraphrases(ctx: _Ctx, statements: list[_Stmt]) -> None:
    docs = [(t.document_id, t.text[:MAX_REGION]) for t in ctx.report.supplied_texts if not (t.document_id or "").startswith("peer:") and t.text]
    if len(docs) != 1:
        return
    name, text = docs[0]
    blocks = _blocks(text)
    if blocks and len(blocks[0]) == 1 and len(blocks) > 1:
        blocks = blocks[1:]
    lines = [ln for b in blocks for ln in b]
    if not lines:
        return
    all_words = set(re.findall(r"[^\W\d_]+", text.casefold()))
    for st in statements:
        m = _LINE_LOC_RE.search(st.text)
        if m is None or es.english_ratio(st.text)[0] < es.english_ratio(st.text)[1]:
            continue
        w = (m.group("w") or "").casefold()
        idx = len(lines) - 1 if w in ("last", "final", "closing") else 0 if w in ("first", "opening") else int(m.group("k")) - 1
        if not 0 <= idx < len(lines):
            continue
        claim = st.text[:m.start()] + st.text[m.end():]
        mine = [x for x in re.findall(r"[^\W\d_]{3,}", claim.casefold()) if x not in _LOC_STOP]
        located = set(re.findall(r"[^\W\d_]+", lines[idx].casefold()))
        shared = [x for x in mine if x in located or x.rstrip("s") in located]
        absent = [x for x in mine if x not in all_words and x.rstrip("s") not in all_words and x + "s" not in all_words]
        if len(shared) < 2:
            continue
        ctx.add("lb_quoted_form", lambda cid, absent=absent, st=st, m=m, idx=idx: make_check(
            ctx.report, check_id=cid, kind="lb_quoted_form", inputs=[("absent", Fraction(len(absent)), f"words of the paraphrase found nowhere in {name} ({', '.join(absent) or 'none'})")],
            conclusion={"op": "eq", "left": _var("absent"), "right": _real(Fraction(0))},
            label=f"the paraphrase of line {idx + 1} of {name} keeps its words",
            description=f"{st.text[:220]} [a paraphrase located at a line of a text keeps that line's content: a content word the text never has is a misreading]",
            claim_ids=ctx.claims(st.text, m.group(0)), severity="warning", defect="altered_quotation"))


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
    for stage, step in (("word counts and ranges", lambda: _word_checks(ctx, statements)), ("course range", lambda: _course_range(ctx)), ("task word ranges", lambda: _task_word_claims(ctx, statements)),
                        ("task word bounds", lambda: _task_word_bounds(ctx, statements)),
                        ("quoted forms", lambda: _quoted_forms(ctx, statements)), ("address forms", lambda: _address_checks(ctx, statements)),
                        ("listed counts", lambda: _listed_counts(ctx, statements)), ("percentage changes", lambda: _percent_changes(ctx)), ("shares", lambda: _shares(ctx)), ("dated changes", lambda: _dated_changes(ctx)), ("durations since a year", lambda: _durations_since(ctx)),
                        ("supplied figures", lambda: _supplied_figures(ctx)), ("event years", lambda: _event_years(ctx)), ("quotation speakers", lambda: _speakers(ctx)),
                        ("structural counts", lambda: _structural_counts(ctx, statements)), ("occurrence counts", lambda: _occurrence_counts(ctx, statements)),
                        ("enumerated counts", lambda: _enumerated_counts(ctx, statements)), ("correction categories", lambda: _category_counts(ctx, statements)),
                        ("bylines", lambda: _byline_claims(ctx, statements)), ("paraphrase speakers", lambda: _paraphrase_speakers(ctx, statements)),
                        ("unquoted speakers", lambda: _unquoted_speakers(ctx, statements)), ("quoted durations", lambda: _quote_durations(ctx, statements)),
                        ("cross-language counts", lambda: _cross_counts(ctx)), ("line paraphrases", lambda: _line_paraphrases(ctx, statements))):
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
