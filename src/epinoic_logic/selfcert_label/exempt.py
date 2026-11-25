"""The exemptions code may decide on a located span (meaning-check design 2.5.5; separate-call design 4.2; overseer-side 3.4).

Code may set aside a span the label named only when every condition of one frame below holds, read from the span's sentence by
shape alone. Any doubt keeps the span. An answer-scope anchor word ("this answer", "above", "here", "my", "esta respuesta", ...)
or a STATUS form (a status word in capitals, a check mark, or any STATUS or MARK hit of the rule reader on the span) in the span
overrides every exemption. An exemption never frees anything the rule reader gates: on the delivery path the label is asked only
about answers the reader passed, and the gate is ``reader OR label``.

=========  ===========================================================================================================
E-Q        an unanswered question: the sentence is a question (an interrogative opener, ending in "?", no tag, no rhetorical
           or negative frame such as "how could anyone doubt that"), the first sentence after it that is no question, in this
           paragraph or the next, does not answer it (G8), and the category is CHECK
E-IMP      an imperative method step: the sentence opens with an imperative check verb used as a verb (its object follows at
           once: never a noun opener such as "Cross-check with ... gave", "Test of ..."), the span lies in that clause, the
           category is CHECK, and no completed-act or outcome marker (done, holds, gave, identical, a check mark, ...) is in
           the sentence
E-WORK     a worked check (X1): the sentence is a relation with an operator and numerals on both sides and nothing else beyond
           a check key ("Check: 3 × 5 = 15", "Comprobación: 25 % de 80 = 20")
E-OUT      a known source's check about the subject matter: a known source FROM THE REQUEST, named as a whole word, is the
           EVALUATOR of the check (its subject or its "by" agent, not the reference the writer checked against), no anchor,
           self, tool, agent or assessor word is in the sentence, and the category is CHECK, AGREE or OUTCOME
E-GLOSS    the span lies inside the quoted object of a gloss frame: a word or phrase of at most four words named as a word,
           term or phrase before its quotation marks and glossed after them ("The French word 'vérifié' means checked.")
E-CORR     marking context only, an actual correction pair (a wrong member that names something, followed by its right
           member): the span is the wrong key ("Mal:", "Wrong:") or lies in the wrong member; never the right one
E-CMD      the span is exactly a command term of the request's items in a sentence about the command term (or quoted), or
           a quotation of at most three words governed by "command term"
=========  ===========================================================================================================

Everything else stays with the model: negation and double negation, litotes, hedges, irony, relays, outside bodies not in the
request, other languages, narrative third-party checks, mark-allocation codes and end-of-proof marks. When a quote occurs more
than once in its sentence, every occurrence must be exempt, or the span stays named at an occurrence that is not
(:func:`epinoic_logic.selfcert_label.validate.validate_reply`). The frames' words are data
(``exemptions.json``), covered by :func:`epinoic_logic.selfcert_label.label_digest`. Each function is linear in its sentence.
"""
from __future__ import annotations

import functools
import json
import pathlib
import re
from typing import Optional

from .. import selfcert
from .scope import OwnScope, Segment

__all__ = ["EXEMPTIONS", "decide", "overridden", "exemption_data"]

_HERE = pathlib.Path(__file__).resolve().parent
EXEMPTION_DATA = "exemptions.json"
EXEMPTIONS = ("E-Q", "E-IMP", "E-WORK", "E-OUT", "E-GLOSS", "E-CORR", "E-CMD")


@functools.lru_cache(maxsize=1)
def exemption_data() -> dict:
    return json.loads((_HERE / EXEMPTION_DATA).read_text(encoding="utf-8"))


def _rf(s: str) -> str:
    return selfcert.reading_form(s)


@functools.lru_cache(maxsize=None)
def _words_re(name: str, form: str = "reading") -> "re.Pattern[str]":
    words = exemption_data()[name]
    if form == "reading":
        words = [_rf(w) for w in words]
    words = sorted({w for w in words if w}, key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)", re.IGNORECASE)


@functools.lru_cache(maxsize=None)
def _status_words() -> frozenset:
    return frozenset(selfcert.visible_form(w) for w in exemption_data()["status_words"])


_TOKEN_RE = re.compile(r"[^\W_]+(?:\.[^\W_]+)*")


def overridden(span_text: str) -> bool:
    """Whether ``span_text`` holds an answer-scope anchor or a STATUS form, which overrides every exemption."""
    if not span_text:
        return False
    rf = _rf(span_text)
    if _words_re("anchors").search(rf):
        return True
    if any(m in span_text for m in exemption_data()["status_marks"]) or "zzmark" in rf:
        return True
    vis = selfcert.visible_form(span_text)
    words = _status_words()
    for m in _TOKEN_RE.finditer(vis):
        t = m.group(0)
        if t.isupper() and (t in words or t.rstrip(".") in words):
            return True
    try:
        reading = selfcert.read(span_text)
    except Exception:  # noqa: BLE001 - fail closed: an unreadable span is never exempt
        return True
    return any(h.family in ("STATUS", "MARK") for h in reading.hits) or bool(reading.unread)


# ----------------------------------------------------------------------------------------------------- the frames
_LIST_MARK_RE = re.compile(r"\A\s*(?:[-*•>#]+|\d{1,3}[.)]|[a-zA-Z][.)]|\(\w{1,3}\))?\s*[*_]{0,2}\s*")
_END_Q_RE = re.compile(r"\?[\"'”’»)\]*_]*\s*\Z")


def _body(text: str) -> tuple[int, str]:
    m = _LIST_MARK_RE.match(text)
    k = m.end() if m else 0
    return k, text[k:]


def _is_question(seg: Segment) -> bool:
    return bool(_END_Q_RE.search(seg.text))


def _answered(seg: Segment, scope: OwnScope) -> bool:
    """G8: whether the question ``seg`` is answered after it (in its paragraph or the next): the first sentence after it that is
    no question (at most :data:`_LOOKAHEAD` sentences on) is short, or opens with an answer word or an echo ("Yes.", "They were,
    twice."). Nothing after it: unanswered. A run of questions longer than the reach counts as answered (doubt keeps the
    span; attack round 16: an answer in the next paragraph was not read)."""
    segs = scope.segments
    k = seg.index + 1
    for _ in range(_LOOKAHEAD):
        if k >= len(segs):
            return False
        nxt = segs[k]
        if not _is_question(nxt):
            words = nxt.text.split()
            return len(words) <= 6 or bool(_words_re("answer_words").match(_rf(nxt.text)))
        k += 1
    return True


#: Sentences read after a question for its answer (G8).
_LOOKAHEAD = 8


def _question(seg: Segment, scope: OwnScope, a: int, b: int, category: str) -> bool:
    if category != "CHECK":
        return False
    text = seg.text
    if not _END_Q_RE.search(text):
        return False
    _k, body = _body(text)
    lead = _rf(body.split(None, 1)[0]) if body.split() else ""
    if not (body.lstrip().startswith("¿") or _words_re("question_openers").fullmatch(lead or "")):
        return False
    if body.count("?") != 1 or any(c in body for c in ".!;"):
        return False
    comma = body.rfind(",")
    if comma >= 0 and len(body[comma + 1:].split()) <= 3:
        return False  # a tag question ("..., hasn't it?") asserts
    rf = _rf(body)
    if _words_re("rhetorical_markers").search(rf) or _NEG_CONTRACTION_RE.search(body):
        return False  # a rhetorical or negative question presupposes the check ("How could anyone doubt that ...?")
    if _answered(seg, scope):
        return False  # an answered self-question (G8) stays gated, in its paragraph or the next
    return True


_NEG_CONTRACTION_RE = re.compile(r"n['’]t(?!\w)", re.IGNORECASE)


def _first_clause_end(text: str) -> int:
    ends = [text.find(br) for br in exemption_data()["clause_breaks"]]
    ends = [e for e in ends if e > 0]
    return min(ends) if ends else len(text)


def _imperative(seg: Segment, a: int, b: int, category: str) -> bool:
    """E-IMP: the sentence opens with an imperative check verb USED AS A VERB, that is followed at once by its object or
    complement (a determiner, a pronoun, "that", "whether", a variable or a numeral: ``imperative_objects``). A noun opener
    ("Cross-check with a second method gave ...", "Test of every line came back clean", "Check complete: ...") is no
    imperative, and a report of an outcome anywhere in the sentence (``completed_markers``, ``report_markers``) keeps the span:
    the reader's IMPERATIVE class is not public yet, so this frame is the narrow shape the memo's condition allows."""
    if category != "CHECK":
        return False
    text = seg.text
    if "?" in text:
        return False
    k, body = _body(text)
    head = _rf(body[:64]) if body else ""
    m = _words_re("imperative_check_verbs").match(head)
    if not m:
        return False
    rest = head[m.end():]
    if not rest[:1].isspace():
        return False  # "Check:", "Check-list", "Verify," : a key or a noun, no instruction
    nm = _NEXT_WORD_RE.match(rest)
    if not nm:
        return False
    nxt = nm.group(1)
    if not (_words_re("imperative_objects").fullmatch(nxt) or _VARIABLE_RE.fullmatch(nxt)):
        return False
    end = k + _first_clause_end(body)
    if not (a >= k and b <= end):
        return False
    rf = _rf(text)
    if _words_re("completed_markers").search(rf) or _words_re("report_markers").search(rf) or "zzmark" in rf:
        return False
    if any(mk in text for mk in exemption_data()["status_marks"]):
        return False
    return True


_NEXT_WORD_RE = re.compile(r"\s+([^\s,;:.!?()\[\]\"'“”‘’«»]+)")
#: A variable or a numeral as the object ("Substitute x = 2", "Check 3 × 5").
_VARIABLE_RE = re.compile(r"[a-zA-Z]|\d+(?:[.,]\d+)*")


_NUM = r"\d+(?:[.,]\d+)*"
_OPS = "+\\-\u2212\u00d7*\u00b7/\u00f7^"
_RELS = "=\u2248\u2260<>\u2264\u2265"
_RELATION_RE = re.compile("[" + _RELS + "]")
_OPERATOR_RE = re.compile("[" + _OPS + "%]")
_DIGIT_RE = re.compile(r"\d")


@functools.lru_cache(maxsize=1)
def _expression_re() -> "re.Pattern[str]":
    """A worked check's expression: numerals, operators, relation signs, brackets, single-letter variables, and a percent sign
    optionally followed by "of" or "de" ("25 % de 80"); nothing else. One regular expression, so the scan is linear."""
    of = "|".join(re.escape(w) for w in exemption_data()["percent_of"])
    return re.compile(r"(?:\s+|" + _NUM + "|[" + _OPS + "]|[" + _RELS + r"]|[()\[\]]|%(?:\s*(?:" + of + r")(?![^\W\d_]))?|"
                      r"[A-Za-z](?![A-Za-z]))+", re.IGNORECASE)


def _worked(seg: Segment) -> bool:
    text = seg.text.strip()
    while text and text[-1] in ".;":
        text = text[:-1].rstrip()
    _k, body = _body(text)
    m = _words_re("check_keys", "plain").match(body)
    if m:
        rest = body[m.end():].lstrip()
        if not rest.startswith(":"):
            return False
        body = rest[1:]
    body = body.strip()
    rel = _RELATION_RE.search(body) if body else None
    if rel is None or not _expression_re().fullmatch(body):
        return False
    left, right = body[:rel.start()], body[rel.end():]
    if not (_DIGIT_RE.search(left) and _DIGIT_RE.search(right)):
        return False
    return _OPERATOR_RE.search(body) is not None


@functools.lru_cache(maxsize=256)
def _source_re(src: str) -> "Optional[re.Pattern[str]]":
    s = " ".join(str(src).split())
    if len(s) < 3:
        return None
    parts = [re.escape(w) for w in s.split(" ")]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


_DETERMINER_ONLY_RE = re.compile(r"\s*(?:(?:the|el|la|los|las)\s+)?\Z", re.IGNORECASE)
_BY_AGENT_RE = re.compile(r"\s*(?:by|por)\s+(?:(?:the|el|la|los|las)\s+)?", re.IGNORECASE)


_BY_AGENT_END_RE = re.compile(r"(?<!\w)(?:by|por)\s+(?:(?:the|el|la|los|las)\s+)?\Z", re.IGNORECASE)


def _evaluator_at(text: str, s0: int, s1: int, a: int, b: int) -> bool:
    """Whether the known source named at ``[s0, s1)`` is the EVALUATOR of the check named by the span ``[a, b)``: its subject
    ("The ONS confirmed the figures", with at most an adverb between, ``source_gap``) or its agent ("were confirmed by the
    ONS"). A source named as the reference of the writer's own check ("cross-checked against the ONS census", "made from the
    ONS bulletin") is no evaluator."""
    if s1 <= a:
        gap = text[s1:a]
        return _source_gap_ok(gap)
    if b <= s0:
        return bool(_BY_AGENT_RE.fullmatch(text[b:s0]))
    # the source lies inside the span: the span opens with it (a determiner at most before it) and a check follows it, or the
    # span names it as the agent ("... confirmed by the ONS")
    if a <= s0 and s1 <= b:
        if _DETERMINER_ONLY_RE.fullmatch(text[a:s0]):
            return True
        return bool(_BY_AGENT_END_RE.search(text[a:s0]))
    return False


def _source_gap_ok(gap: str) -> bool:
    words = _rf(gap).split()
    if len(words) > 3 or any(c in gap for c in ",;:()[]"):
        return False
    allowed = _words_re("source_gap")
    return all(allowed.fullmatch(w) for w in words)


def _known_source(seg: Segment, a: int, b: int, category: str, scope: OwnScope) -> bool:
    """E-OUT: a known source FROM THE REQUEST, named as a whole word, is the evaluator of the check (:func:`_evaluator_at`);
    the rest of the sentence names no anchor, self, tool, agent or assessor (attack round 16: "ONS" was matched inside
    "proportions", and a source named anywhere freed the writer's own check against it)."""
    if category not in ("CHECK", "AGREE", "OUTCOME") or not scope.known_sources:
        return False
    text = seg.text
    found = None
    for src in scope.known_sources:
        rx = _source_re(str(src))
        if rx is None:
            continue
        for m in rx.finditer(text):
            if _evaluator_at(text, m.start(), m.end(), a, b):
                found = m
                break
        if found is not None:
            break
    if found is None:
        return False
    rest = text[:found.start()] + " " + text[found.end():]
    rf = _rf(rest)
    if _words_re("anchors").search(rf) or _words_re("self_and_internal_evaluators").search(rf):
        return False
    return not overridden(rest)


def _gloss(seg: Segment, a: int, b: int) -> bool:
    """E-GLOSS: the span lies inside the quoted OBJECT of a gloss frame: a word or short phrase (at most four words) named as a
    word, term or phrase right before its quotation marks ("The French word 'vérifié' means checked.") and glossed right after
    them. A quoted own claim followed by "means" is no gloss (attack round 16)."""
    from ..api.adapters import find_quotation_spans
    text = seg.text
    try:
        spans = find_quotation_spans(text, min_single_words=1)
    except Exception:  # noqa: BLE001
        return False
    verbs = _words_re("gloss_verbs")
    nouns = _words_re("gloss_nouns")
    for qs, qe, inner in spans:
        ia = text.find(inner, qs, qe)
        if ia < 0 or not (ia <= a and b <= ia + len(inner)):
            continue
        if len(inner.split()) > 4:
            continue
        before = _rf(text[max(0, qs - 40):qs]).rstrip(" ,:")
        tail = before.rsplit(" ", 1)[-1] if before else ""
        if not (tail and nouns.fullmatch(tail)):
            continue
        after = text[qe:qe + 60].lstrip(" ,\t")
        if after and verbs.match(_rf(after)):
            return True
    return False


@functools.lru_cache(maxsize=None)
def _key_re(name: str) -> "re.Pattern[str]":
    words = sorted(exemption_data()[name], key=len, reverse=True)
    return re.compile(r"(?:(?<=[\s*_(>\-])|\A)(?:" + "|".join(re.escape(w) for w in words) + r")[ \t]*[*_]{0,2}[ \t]*:",
                      re.IGNORECASE)


def _key_regions(text: str, name: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _key_re(name).finditer(text)]


def _correction(seg: Segment, prev: Optional[Segment], nxt: Optional[Segment], a: int, b: int, scope: OwnScope) -> bool:
    """E-CORR, marking context only: an actual correction pair, that is a wrong key ("Mal:", "Wrong:") whose member names
    something (no "none", "nothing", "ninguno") and is followed by its right member (a right key or an arrow in the same
    sentence, or a right key opening the next sentence of the paragraph). The span is the wrong key or lies in the wrong
    member, which ends at the right member, an arrow or a semicolon. The right member is never exempt. "Mistake: none; the
    engine verified every mark" is no pair (attack round 16)."""
    if not scope.marking:
        return False
    text = seg.text
    wrong = _key_regions(text, "wrong_keys")
    right = _key_regions(text, "right_keys")
    next_right = nxt is not None and nxt.paragraph == seg.paragraph and bool(_key_re("right_keys").match(_body(nxt.text)[1]))
    for ka, kb in wrong:
        stops = [ra for ra, _rb in right if ra >= kb] + [x for x in (text.find("→", kb), text.find("->", kb)) if x >= 0]
        semi = text.find(";", kb)
        pair_end = min(stops) if stops else (len(text) if next_right else -1)
        if pair_end < 0:
            continue  # no right member: no correction pair
        member_end = min(pair_end, semi) if semi >= 0 else pair_end
        member = text[kb:member_end]
        if not member.strip() or _words_re("none_words").match(_rf(member.strip(" *_\t\"'“”‘’«»"))):
            continue
        if ka <= a and b <= kb:
            return True
        if kb <= a and b <= member_end:
            return True
    paired = bool(wrong) or (prev is not None and prev.paragraph == seg.paragraph and _key_regions(prev.text, "wrong_keys"))
    if paired:
        for ra, rb in right:
            if ra <= a and b <= rb:
                return True  # the right member's key; the right member itself is never exempt
    return False


def _command_term(seg: Segment, a: int, b: int, scope: OwnScope) -> bool:
    """E-CMD: the span is the command term itself: a token equal to a command term of the request's items, named in a
    sentence that speaks of the command term (or quoted), or a quotation of at most three words governed by "command term"
    ("the command term 'verify'", "the command term is 'verify'", "'verify' is the command term"). Any other quotation in a
    sentence that mentions a command term is not freed (attack round 16)."""
    text = seg.text
    span = text[a:b]
    norm = " ".join(span.strip(" \t\"'“”‘’«».,;:!?()[]*_").split()).casefold()
    is_term = bool(norm) and norm in scope.command_terms
    low = text.casefold()
    framed = any(f.casefold() in low for f in exemption_data()["command_term_frames"]) and \
        _words_re("command_term_frames").search(_rf(text)) is not None
    if not (framed or is_term):
        return False  # (the quotation scan below is made only when a frame or a term could free the span)
    from ..api.adapters import find_quotation_spans
    try:
        spans = find_quotation_spans(text, min_single_words=1)
    except Exception:  # noqa: BLE001
        return False
    if is_term and (framed or any(qs <= a and b <= qe for qs, qe, _i in spans)):
        return True
    if not framed:
        return False
    for qs, qe, inner in spans:
        if not (qs <= a and b <= qe) or len(inner.split()) > 3:
            continue
        before = text[max(0, qs - 40):qs]
        after = text[qe:qe + 50]
        if _CMD_BEFORE_RE.search(before) or _CMD_AFTER_RE.match(after):
            return True
    return False


_CMD_FRAME = r"(?:command\s+terms?|t[ée]rminos?\s+de\s+instrucci[oó]n)"
_CMD_BEFORE_RE = re.compile(_CMD_FRAME + r"(?:\s+(?:here|used|is|was|es|aqu[ií]))*\s*[:,]?\s*\Z", re.IGNORECASE)
_CMD_AFTER_RE = re.compile(r"\s*,?\s*(?:is|was|es)\s+(?:the|el)\s+" + _CMD_FRAME, re.IGNORECASE)


def decide(seg: Segment, a: int, b: int, category: str, scope: OwnScope, *, prev: Optional[Segment] = None,
           nxt: Optional[Segment] = None) -> Optional[str]:
    """The exemption that sets aside the located span ``[a, b)`` (rendered offsets of ``seg``) of ``category``, or None."""
    try:
        span = seg.text[a:b]
        found: Optional[str] = None
        if _question(seg, scope, a, b, category):
            found = "E-Q"
        elif _imperative(seg, a, b, category):
            found = "E-IMP"
        elif _worked(seg):
            found = "E-WORK"
        elif _known_source(seg, a, b, category, scope):
            found = "E-OUT"
        elif _gloss(seg, a, b):
            found = "E-GLOSS"
        elif _correction(seg, prev, nxt, a, b, scope):
            found = "E-CORR"
        elif _command_term(seg, a, b, scope):
            found = "E-CMD"
        if found is None or overridden(span):
            return None
        return found
    except Exception:  # noqa: BLE001 - any doubt keeps the span
        return None
