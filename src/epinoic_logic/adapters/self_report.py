"""Thin names over the one self-certification reader (``epinoic_logic.selfcert``; round-10 hold remedy c3b, rules ``selfcert-1``).

An agent's statement that its own answer was checked, verified, confirmed, reviewed, approved, scored or is correct is a
self-certification: advisory, never evidence, never a reason to deliver, select or label an answer (repository ``CLAUDE.md``).
Every round before c3b added the phrasings the last push check listed to readers here; the next push check found new ones. Those
readers (about 250 layered patterns) are deleted: every function below is ONE call into :mod:`epinoic_logic.selfcert`, which reads
the class by meaning (theme and scope, evaluator, polarity, mood and frame, over closed classes of words). The names and signatures
are kept so the parsers, the packs, the overseer and the integration kit keep importing them unchanged.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from .. import selfcert as _sc
from ..selfcert import Context
from ..selfcert.pieces import MODEL_MARKS_RULE, blank_model_marks, model_mark_ranges, quotation_only, report_texts

__all__ = ["claims_a_check", "wholly_self_report", "label_self_report", "report_field_texts", "report_field_self_reports",
           "mask_outside_quotations", "quotation_in_scope", "reading_form", "template_form", "normalise_reading", "is_self_report",
           "class_self_report", "not_a_self_report", "self_report_pieces", "is_worked_check", "reading_sentences", "self_report_places",
           "self_report_spots", "quotation_only", "claim_is_self_report", "names_self_report_in", "SELF_REPORT_STATUS",
           "model_mark_ranges", "blank_model_marks", "MODEL_MARKS_RULE", "label_on_content", "self_report_note", "task_context", "answered_self_question"]

#: The advisory status a parser sets on a claim holding a self-certification (the hub names it INT-HANDOFF-006).
SELF_REPORT_STATUS = "self-certified in the response text"

_LABEL_FORMS = frozenset({"label_before", "label_after", "label_inside", "whole", "symbol"})


_DEFAULT_CTX = Context()


def task_context(ctx: Optional[Context] = None) -> Context:
    """The context a parser reads its sentences in: ``ctx`` when the caller gives one, else the default context with ``marking``
    set from the task the channel set from the router's plan (``markdown.feedback_task``; none set: False), the same context the
    core pack names the self-certifications in (``CorePack._self_certification``), so a parser's roles and the gate read every
    sentence alike (design 4.0 principle 1). The report's own task type field never sets it."""
    if ctx is not None and ctx != _DEFAULT_CTX:
        return ctx
    from .markdown import feedback_task
    try:
        return Context(marking=True) if feedback_task() else _DEFAULT_CTX
    except Exception:  # noqa: BLE001 - the strict default context
        return _DEFAULT_CTX


def is_self_report(sentence: str, ctx: Optional[Context] = None) -> bool:
    """Whether ``sentence`` (or a piece of it) is a self-certification (``selfcert.is_self_certification``), read in
    :func:`task_context`."""
    return _sc.is_self_certification(sentence, task_context(ctx))


def class_self_report(s: str) -> bool:
    return _sc.is_self_certification(s)


def not_a_self_report(s: str) -> bool:
    """The negation of the one reader: True when ``s`` holds no self-certification."""
    return not _sc.is_self_certification(s)


def claim_is_self_report(text: str, split: Optional[Callable[[str], list[str]]] = None, ctx: Optional[Context] = None) -> bool:
    """Whether the claim ``text`` holds a self-certification (read in :func:`task_context`); a claim that is nothing but a
    quotation drawn from a sentence is read in that sentence, not here (:func:`quotation_only`)."""
    if not isinstance(text, str) or not text.strip() or quotation_only(text):
        return False
    return _sc.is_self_certification(text, task_context(ctx))


def names_self_report_in(text: str, split: Callable[[str], list[str]], ctx: Context = Context()) -> bool:
    if _sc.is_self_certification(text, ctx):
        return True
    return any(_sc.is_self_certification(s, ctx) for s in split(text))


def label_self_report(text: str, ctx: Context = Context()) -> bool:
    """Whether ``text`` carries a verification label, a status word or a mark (a hit of a label form or of the STATUS or MARK
    family)."""
    return any(h.form in _LABEL_FORMS or h.family in ("STATUS", "MARK") for h in _sc.read(text, ctx).hits)


#: The forms of a hit attached to content (design 3.7 G6: "Verified: <content>", "<content> (verified).", "x = 4 ✓").
_ON_CONTENT_FORMS = frozenset({"label_before", "label_after", "label_inside"})
_MARKUP_RE = re.compile(r"[*_#>`~|\[\](){}]+")
_RELATION_SIGN_RE = re.compile(r"\w\s*[=<>≤≥≠≈]\s*[\w(−-]")
_STATES_RE = re.compile(r"\b(?:is|are|was|were|has|have|had|be|been|being|equals?|gives?|shows?|means?|es|son|fue|fueron|está|están)\b|\w\wed\b",
                        re.IGNORECASE)


def _states_content(rest: str) -> bool:
    """Whether ``rest`` (what is left of a sentence once its labels are set aside) states something: a relation, a value with a
    word, or a clause of at least four words, or three with a finite verb."""
    rest = _MARKUP_RE.sub(" ", rest or "")
    if _RELATION_SIGN_RE.search(rest):
        return True
    words = [w for w in rest.split() if any(c.isalpha() for c in w)]
    if any(c.isdigit() for c in rest) and words:
        return True
    return len(words) >= 4 or (len(words) >= 3 and _STATES_RE.search(rest) is not None)


def label_on_content(text: str, ctx: Optional[Context] = None) -> bool:
    """Whether every self-certification of ``text`` is a label or a mark ON content (design 3.7 G6 and the label forms of G4:
    "Verified: The constitution was adopted in 1919.", "The treaty was signed in 1919 (verified).", "x = 4 ✓",
    "**Word count: 348** The narrator ...") and content is left once the labels are set aside. Such a sentence keeps the role and
    the materiality its content has (design 3.13: a label never takes content out of the checks); the label is still the
    self-report (CORE-SELF-001 names it, the claim carries the advisory status, its outcome never shows success). A hit inside
    a label's span (the "verified" of "(verified)") is that label's word, not a hit of its own."""
    if not isinstance(text, str) or not text.strip():
        return False
    ctx = task_context(ctx)
    try:
        r = _sc.read(text, ctx)
    except Exception:  # noqa: BLE001 - fail closed: a sentence the reader cannot read is never content kept by a label
        return False
    if not r.hits or r.unread:
        return False
    # (linear in the hits and the text: a run of thousands of marks "✓ ✓ ✓ ..." is thousands of labels, and a membership test of
    # each hit against the list of labels, or a blanking pass per label, was quadratic; design 2.9)
    is_label = [h.form in _ON_CONTENT_FORMS or h.rule == "G6" for h in r.hits]
    labels = [h for h, lab in zip(r.hits, is_label) if lab]
    if not labels:
        return False
    from bisect import bisect_right
    spans = sorted((h.start, h.end) for h in labels)
    starts = [a for a, _b in spans]
    reach: list[int] = []
    best = -1
    for _a, b in spans:
        best = max(best, b)
        reach.append(best)
    for h, lab in zip(r.hits, is_label):
        if lab:
            continue
        j = bisect_right(starts, h.start) - 1
        if j < 0 or reach[j] < h.end:
            return False  # a hit outside every label's span: more than a label
    n = len(text)
    diff = [0] * (n + 1)
    for h in labels:
        a0, b0 = max(0, h.start), min(n, h.end)
        if a0 < b0:
            diff[a0] += 1
            diff[b0] -= 1
    chars = list(text)
    depth = 0
    for i in range(n):
        depth += diff[i]
        if depth > 0:
            chars[i] = " "
    candidates = ["".join(chars)]
    seen_k: set[int] = set()
    for h in labels:
        if h.form == "label_before" and len(seen_k) < 2:
            # a label whose span runs on past its key ("Word count: 348** The narrator ..."): the content is what follows the key
            k = text.find(":", h.start, h.end)
            if 0 <= k < h.end and k not in seen_k:
                seen_k.add(k)
                candidates.append(text[k + 1:])
    for c in candidates:
        try:
            # (a score said in words after a score label, "Graded: top of the band.", is the label's value: one verdict, no
            # content; check round 9 of c3c)
            if _states_content(c) and not _sc.is_self_certification(c, ctx) and _subject_words(c, ctx) and \
                    not _sc._score_value(c.strip()):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _subject_words(text: str, ctx: Context) -> bool:
    """Whether ``text`` holds a word of the subject matter (not only the answer's and the pipeline's meta vocabulary): what a label
    is ON must be content ("The audit trail for this answer reads: ..." with its status word set aside is no content; attack
    round 3). Bounded: the first 4,000 characters."""
    from ..selfcert.reader import _merge, _tokens, _mark_initials
    from ..selfcert.meaning import _content_at
    from ..selfcert.normalise import fold
    from ..selfcert.pieces import work_string
    w = work_string(fold(text[:4000]).text)
    toks = _merge(_tokens(w, 0, len(w)))
    _mark_initials(toks)
    words = [t for t in toks if not t.punct]
    return any(_content_at(words, k, ctx) for k in range(len(words)))


def self_report_note(text: str, ctx: Optional[Context] = None) -> bool:
    """Whether ``text`` is a self-certification a parser roles as a note (``other``): it holds a self-certification
    (:func:`is_self_report`, read in :func:`task_context`) that is not only a label on content (:func:`label_on_content`). The
    gate reads the TEXT, not this role (design 3.13): a labelled content sentence is still named and still never shown as a
    success."""
    ctx = task_context(ctx)
    if _sc.is_self_certification(text, ctx) and not label_on_content(text, ctx):
        return True
    # text the reader cannot read (CORE-SELF-002: letter-like symbols, hidden characters, a script with no vocabulary) is never
    # content either: it is set aside as a note, role other, never material (attack round 3; fail closed)
    try:
        return bool(isinstance(text, str) and text.strip() and _sc.read(text, ctx).unread)
    except Exception:  # noqa: BLE001
        return True


def answered_self_question(question: str, answer: str, ctx: Optional[Context] = None) -> bool:
    """Whether the question ``question`` and the sentence ``answer`` after it are one answered self-question (design 3.7 G8:
    "What needs fixing here? Nothing.", "Is there anything to fix in this answer? No, not a single slip."): read together, the
    pair holds a G8 hit that neither sentence holds alone. A parser sets both sentences aside, as one self-report."""
    if not (isinstance(question, str) and isinstance(answer, str)) or not question.rstrip().endswith("?") or not answer.strip():
        return False
    if len(question) + len(answer) > 4000:
        return False
    try:
        pair = question.rstrip() + " " + answer.strip()
        return any(h.rule == "G8" for h in _sc.read(pair, task_context(ctx)).hits)
    except Exception:  # noqa: BLE001 - a pair the reader cannot read is read sentence by sentence
        return False


def claims_a_check(text: str, ctx: Context = Context()) -> bool:
    return _sc.claims_a_check(text, ctx)


def wholly_self_report(text: str, ctx: Context = Context()) -> bool:
    return _sc.wholly_self_certification(text, ctx)


def self_report_spots(text: str, split: Optional[Callable[[str], list[str]]] = None, ctx: Context = Context()) -> list[tuple[int, str]]:
    """``(paragraph, piece)`` for each self-certification of the answer ``text`` (hits only; unread runs are
    ``selfcert.unread_text_runs``), smallest piece first. ``split`` is accepted for compatibility and not needed."""
    out: list[tuple[int, str]] = []
    for n, piece, item in _sc.text_spots(text, ctx):
        if isinstance(item, _sc.Hit) and (n, piece) not in out:
            out.append((n, piece))
    return out


def self_report_places(text: str, split: Optional[Callable[[str], list[str]]] = None, ctx: Context = Context()) -> list[int]:
    return sorted({n for n, _p in self_report_spots(text, split, ctx)})


def self_report_pieces(text: str) -> list[str]:
    """The pieces of ``text`` read on their own as well as together: the text, each line, each table cell."""
    if not isinstance(text, str) or not text:
        return []
    out = [text]
    for ln in [x for x in text.split("\n") if x.strip()]:
        out.append(ln)
        if ln.count("|") >= 2:
            out += [c for c in ln.split("|") if c.strip() and c.strip("-: ")]
    return list(dict.fromkeys(out))


def report_field_texts(report) -> list[tuple[str, Optional[str], str]]:
    return report_texts(report)


def report_field_self_reports(report, ctx: Context = Context()) -> list[tuple[str, Optional[str]]]:
    """``(where, claim id or None)`` for each of the specialist's own fields beside the response (assumptions, unresolved issues,
    assessment criteria) that holds a self-certification or an unread run. A field too long to read is named (fail closed)."""
    out: list[tuple[str, Optional[str]]] = []
    for where, cid, text in report_texts(report):
        try:
            if len(text) > 4000 * 64 or _sc.read(text, ctx).refuses():
                out.append((where, cid))
        except Exception:  # noqa: BLE001 - fail closed
            out.append((where, cid))
    return out


def quotation_in_scope(inner: str, ctx: Optional[Context] = None) -> bool:
    """Whether the words of a quotation are a self-certification of THIS answer, whoever it is attributed to: the one reader gates
    them (``selfcert.read``) and they place their theme in this answer, by the reader's own classes of answer reference: an anchor
    idiom ("in this answer", "all of the above", "everything here"), a place anchor ("here", "above") or an anaphoric place ("every
    figure in it"). Such a quotation is never masked. Generic checking words alone ("the answer was checked", "QA: pass", "verified by
    the system", "all the figures in this report") name no place in this answer: a source's quotation of them stays the source's."""
    from ..selfcert.reader import _merge, _tokens
    if not isinstance(inner, str) or not inner.strip() or len(inner) > 4000:
        return False
    try:
        if not _sc.read(inner, ctx if ctx is not None else _DEFAULT_CTX).hits:
            return False
        s = _sc.visible_form(inner)
        toks = _merge(_tokens(s, 0, len(s)))
    except Exception:  # noqa: BLE001 - fail closed: a quotation the reader cannot read is never masked
        return True
    for k, t in enumerate(toks):
        if t.has("C:anchor_idioms") and t.w != "so far":
            return True
        if t.has("C:anchor"):
            return True
        if t.has("C:anaph") and not t.has("C:det", "C:demonstrative") and k > 0 and toks[k - 1].has("C:prep"):
            return True
    return False


def mask_outside_quotations(text: str) -> str:
    """``text`` with every quotation masked whose frame credits an outside party and whose words do not refer to this answer (the
    auditor's FID-005 reads analysis of a supplied text this way); its marks become blanks and its words "x"."""
    from .markdown import find_quotation_spans
    from ..selfcert.reader import _frame_reporter, _mark_initials, _merge, _tokens
    if not isinstance(text, str) or not text:
        return text or ""
    spans = find_quotation_spans(text)
    if not spans:
        return text
    toks = _merge(_tokens(text, 0, len(text)))
    _mark_initials(toks)
    out = list(text)
    for a, b, inner in spans[:256]:
        frame = [t for t in toks if t.b <= a][-12:] + [t for t in toks if t.a >= b][:8]
        if quotation_in_scope(inner) or _frame_reporter(frame, Context()) != "OUT":
            continue
        for i in range(a, b):
            if not out[i].isspace() and out[i] not in ".!?":
                out[i] = "x"
        out[a] = " "
        out[b - 1] = " "
    return "".join(out)


def reading_form(text: str) -> str:
    return _sc.reading_form(text)


def normalise_reading(text: str) -> str:
    return _sc.visible_form(text)


def template_form(text: str) -> str:
    """The reading form with EVERY quotation masked (the structural detectors read a quoted self-report as the quoted text's)."""
    from .markdown import find_quotation_spans
    s = _sc.reading_form(text or "")
    chars = list(s)
    for a, b, _inner in find_quotation_spans(s):
        for i in range(a, b):
            if not chars[i].isspace() and chars[i] not in ".!?":
                chars[i] = "x"
    return " ".join("".join(chars).split())


def reading_sentences(s: str) -> list[str]:
    from ..selfcert.pieces import sentence_spans
    if not isinstance(s, str) or not s.strip():
        return []
    return [s[a:b].strip() for a, b in sentence_spans(s, 0, len(s))] or [s]


def is_worked_check(text: str) -> bool:
    """Whether ``text`` shows a worked computation (a relation with an arithmetic operation and its result) and names no checking
    tool: working for the engine to verify, never a self-certification (rule X1)."""
    from ..selfcert.reader import _computation, _merge, _tokens
    if not isinstance(text, str) or not text.strip():
        return False
    s = _sc.reading_form(text)
    toks = _merge(_tokens(s, 0, len(s)))
    return _computation(toks) and not any(t.has("C:tool") for t in toks)
