"""The writer's own words in quotation marks: one reader for the channel side and the transfer auditor (round-10 clearance c3, overseer
handoff 1(b); the round's critical records on the writer's own quoted text).

A specialist puts its own words in quotation marks as well as the words of a text: a correction after an arrow, a labelled model, topic
or line of inquiry, a gloss, a dictionary or base form, a form a language uses, a recommended form, a class of forms, a list continuing
any of them, and every span of a paragraph after a sentence calling its example invented (rules ``own-model`` and ``own-text``). The
transfer auditor wrote this reader (``epinoic_overseer.checks.fidelity``, OVS-FID-004 and rule feedback-hold); it lives here so the
auditor imports it through the public API (``epinoic_logic.api.adapters``) and the two sides never drift. Since the round-10 hold remedy
c3b the channel reads it too (:func:`own_text_kinds`, one reader: ``markdown.own_form_flags`` reads its FORMs, ``sources.own_model_words``
its FRAMEs with the supplied texts in view, so an altered quotation framed as a model or a correction outside a feedback task is still
checked there: repair round 4, INV-Q1). The spans are returned as written; a caller normalises their inner text as it compares.

Every pattern reads a bounded window right before a span's opening mark (anchored at the window's end) or right after its closing mark
(anchored at the window's start); the paragraphs and the invented-example sentences are found in one pass each, so the reading is
linear in the number of spans.
"""
from __future__ import annotations

import bisect
import re

from typing import Optional, Sequence

from .markdown import _ATTRIBUTION_BEFORE_RE
from .markdown import _FORM_JOIN_RE as _MD_FORM_JOIN_RE
from .markdown import _FORM_NAMED_AFTER_RE as _MD_FORM_NAMED_AFTER_RE
from .markdown import _GLOSS_BEFORE_RE as _MD_GLOSS_BEFORE_RE
from .markdown import _INVENTED_EXAMPLE_RE as _MD_INVENTED_EXAMPLE_RE
from .markdown import _MODAL_FORM_BEFORE_RE as _MD_MODAL_FORM_BEFORE_RE
from .markdown import _TRIGGER_AFTER_RE as _MD_TRIGGER_AFTER_RE
from .markdown import find_quotation_spans

__all__ = ["OWN_MODEL_RULE", "OWN_TEXT_RULE", "OWN_FORM", "OWN_FRAME", "own_model_spans", "own_text_kinds", "own_text_spans"]

#: The two kinds of the writer's own quoted words (:func:`own_text_kinds`; round-10 leftover R10-OWN-TEXT-ONE-READER, one reader for
#: the channel, the packs and the auditor). A FORM is never a quotation of a text in any task: a gloss, a base or standard form, a
#: form the writer says a text would use, a named phrase, a class of trigger forms, a list continuing one, a span of a paragraph
#: after an invented example. A FRAME presents the span as the writer's own wording by its position: a correction after an arrow,
#: a labelled model, rewrite, topic or line of inquiry, a model lead, a span offered "instead of" or "rather than" another. Outside a
#: feedback task the channel decides a frame with the supplied texts in view (``sources.own_model_words``, repair round 4, INV-Q1):
#: words a supplied text holds all but one or two of, framed that way, stay an altered quotation and are checked.
OWN_FORM = "form"
OWN_FRAME = "frame"

#: Rule ``own-model`` (round-9 clearance c2): a quotation right after a model, example or suggested-wording lead.
OWN_MODEL_RULE = "own-model"
_OWN_MODEL_LEAD_RE = re.compile(r"(?:^|[\n.!?])[ \t*_>#-]{0,8}(?:an?[ \t]{1,3})?(?:model(?:[ \t]{1,3}(?:answer|sentence|paragraph|response))?|"
                                r"(?:example|sample|suggested|exemplar)[ \t]{1,3}(?:answer|sentence|wording|response|paragraph)|rewrite|rewritten|"
                                r"suggested[ \t]{1,3}rewrite|(?:for[ \t]{1,3}example,?[ \t]{1,3})?you[ \t]{1,3}could[ \t]{1,3}write|"
                                r"for[ \t]{1,3}example,?[ \t]{1,3}write)[*_]{0,2}[ \t]{0,3}:[ \t]{0,3}[*_]{0,2}$", re.IGNORECASE)
_OWN_MODEL_WINDOW = 80


#: Rule ``own-text`` (round-10 clearance c3, FID-004): the cues with which an answer presents a quoted span as its own words (module
#: docstring). Each is read in a bounded window right before the span's opening mark (anchored at the window's end) or right after its
#: closing mark (anchored at the window's start); every run of blanks and every free gap is bounded, so the reading is linear in the
#: number of spans.
OWN_TEXT_RULE = "own-text"
_OWN_TEXT_BEFORE = 160
_OWN_TEXT_AFTER = 96
#: The corrected form: a quoted original, an arrow (or "should be", "becomes"), then the span.
_CORRECTION_BEFORE_RE = re.compile(r"[\"'”’»][*_ \t]{0,6}(?:→|->|=>|⇒|⟶|⟹|➔|➜|➝|\bshould[ \t]{1,3}be\b[ \t:]{0,3}|\bbecomes\b[ \t:]{0,3})"
                                   r"[ \t*_]{0,6}\Z", re.IGNORECASE)
#: A model, topic or line of inquiry under its label at the start of a line or sentence; a parenthesis of at most 200 characters may
#: follow the label ("Model (one sentence, to show range with your own content; not a replacement for your text):").
_OWN_LABEL_BEFORE_RE = re.compile(r"(?:^|[\n.!?;])[ \t*_>#-]{0,8}(?:an?[ \t]{1,3})?(?:model|rewrite|rewritten|corrected|correction|"
                                  r"improved|revised|alternative|suggested|suggestion|topic|line[ \t]{1,3}of[ \t]{1,3}inquiry|better|stronger|"
                                  r"research[ \t]{1,3}question)(?:[ \t]{1,3}(?:answer|sentence|paragraph|response|version|wording|form|"
                                  r"opening|line|thesis|statement|introduction|conclusion|topic[ \t]{1,3}sentence))?[ \t]{0,3}(?:\([^()\n\"“”]{0,200}\))?[*_]{0,2}[ \t]{0,3}:[ \t]{0,3}[*_]{0,2}\Z",
                                  re.IGNORECASE)
#: A gloss: the meaning of a quoted word or phrase in the writer's own words.
_GLOSS_BEFORE_RE = re.compile(r"(?:\bmeans?|\bmeaning|\btranslates?[ \t]{1,3}(?:as|to)|\btranslated[ \t]{1,3}as|\bglossed[ \t]{1,3}as|\bliterally|"
                              r"\bin[ \t]{1,3}english[ \t]{1,3}(?:is|means))[ \t:,]{0,4}(?:something[ \t]{1,3}like[ \t]{1,3}|roughly[ \t]{1,3})?\Z",
                              re.IGNORECASE)
#: A dictionary form: the base form, a contraction's full form, a grammatical form of a quoted word.
_FORM_BEFORE_RE = re.compile(r"(?:\b(?:imperative|infinitive|lemma|root|stem|participle|gerund|conjugation|contraction|form|plural|singular)"
                             r"[ \t]{1,3}of|\bcontracts|\babbreviates|\bshortens|\bis[ \t]{1,3}short[ \t]{1,3}for)[ \t:]{0,3}\Z", re.IGNORECASE)
#: A form a language uses: "Standard Spanish says", "Mexican Spanish uses", "English would say".
_LANGUAGE_BEFORE_RE = re.compile(r"\b(?:spanish|english|french|german|italian|portuguese|catalan|latin)[ \t]{1,3}(?:says|uses|prefers|"
                                 r"would[ \t]{1,3}(?:say|use))[ \t:]{0,3}\Z", re.IGNORECASE)
#: A form the sentence recommends: "would normally use ustedes:", "would say", "could write"; at most two words before a colon.
_SUGGEST_BEFORE_RE = re.compile(r"\b(?:would|could|should|might)[ \t]{1,3}(?:normally[ \t]{1,3}|usually[ \t]{1,3}|instead[ \t]{1,3}|"
                                r"rather[ \t]{1,3})?(?:use|say|write)(?:[ \t]{1,3}[^\s\"“”‘’«»:.!?]{1,24}){0,2}[ \t]{0,2}:?[ \t]{0,3}\Z",
                                re.IGNORECASE)
#: After the span: a fixed phrase, an expression or an idiom; a suggested replacement ("instead of", "rather than").
_PHRASE_ONLY_AFTER_RE = re.compile(r"\A[ \t]{0,3}(?:is|are)[ \t]{1,3}(?:an?[ \t]{1,3})?(?:fixed[ \t]{1,3}|set[ \t]{1,3}|common[ \t]{1,3}|idiomatic[ \t]{1,3}|"
                                   r"colloquial[ \t]{1,3}|informal[ \t]{1,3}|everyday[ \t]{1,3})?(?:phrase|expression|idiom|collocation)s?\b", re.IGNORECASE)
#: After the span: a suggested replacement ("instead of", "rather than"): a FRAME (:func:`own_text_kinds`).
_PHRASE_AFTER_RE = re.compile(r"\A[ \t,]{0,3}(?:instead[ \t]{1,3}of|rather[ \t]{1,3}than)\b", re.IGNORECASE)
#: After the span: members of a class of forms ("and other wish or hope phrases").
_CLASS_AFTER_RE = re.compile(r"\A[ \t,]{0,3}(?:and|or)[ \t]{1,3}other[ \t]{1,3}(?:[^\W\d_][\w-]{0,19}[ \t]{1,3}){0,4}(?:phrases|words|verbs|"
                             r"expressions|forms|triggers|structures|connectives|conjunctions)\b", re.IGNORECASE)
#: The gap between two spans of one list: a comma, semicolon or slash, "or" or "and" (one joiner at least: two spans with only a
#: blank between them are two sentences, not a list).
_LIST_GAP_RE = re.compile(r"\A[ \t]{0,3}(?:[,;/][ \t]{0,3}(?:(?:or|and)[ \t]{1,3})?|(?:or|and)[ \t]{1,3})\Z", re.IGNORECASE)
#: A sentence that calls its example invented ("An example on a different, invented body of work").
_INVENTED_EXAMPLE_RE = re.compile(r"\b(?:example|model|illustration|sample)\b[^.!?\n]{0,60}\b(?:invented|made[- ]up|hypothetical|imaginary)\b"
                                  r"|\b(?:invented|made[- ]up|hypothetical|imaginary)\b[^.!?\n]{0,30}\b(?:example|model|illustration|sample)\b",
                                  re.IGNORECASE)
_PARAGRAPH_BREAK_RE = re.compile(r"\n[ \t]*\n")




def own_model_spans(text: str) -> list[tuple[int, int, str]]:
    """Rule ``own-model`` (round-9 clearance c2, the c2 results-audit, adversarial and communication lenses: four false OVS-FID-004 errors
    failed the correct ec-t15 answer, and its feedback told the specialist to remove the quotation marks): the quotation spans ``text``
    presents as the writer's own model, example or suggested wording (:data:`_OWN_MODEL_LEAD_RE` right before the opening mark), as
    ``(start, end, inner)``. Such a span quotes no supplied text: it is the writer's own words in quotation marks. One pass over the
    quotation spans, each reading a bounded window."""
    text = text or ""
    return [(start, end, inner) for start, end, inner in find_quotation_spans(text)
            if inner.strip() and _OWN_MODEL_LEAD_RE.search(text[max(0, start - _OWN_MODEL_WINDOW):start])]


def _form_flags(text: str, spans: Sequence[tuple[int, int, str]]) -> list[bool]:
    """The FORM cues the channel read first (``markdown`` clearance c3: a gloss or an expansion, a base or standard form, a form the
    text would or should use, a form named as a fixed phrase or a base form, every span of a paragraph after an invented example is
    announced, a list of trigger forms closed by "and other ... phrases", and a span joined by a comma, "or" or "and" to one of
    them). A span attributed to a text keeps being a quotation wherever a frame names the text ("your email says", "the poem's"):
    those frames stand before the span, never these. Linear: each span reads bounded windows; the paragraph breaks are found once
    and the invented-example announcement is searched once over each paragraph."""
    n = len(spans)
    out = [False] * n
    para_start = 0
    invented_at: Optional[int] = None
    scanned_to = 0
    breaks = [m.start() for m in _PARAGRAPH_BREAK_AT_RE.finditer(text)]
    for k, (a, b, _inner) in enumerate(spans):
        i = bisect.bisect_left(breaks, a - 1)  # the last break that ends before the span ('\n\n' wholly before a)
        p = breaks[i - 1] if i > 0 else -1
        if p != para_start:
            para_start, invented_at, scanned_to = p, None, max(0, p)
        before = text[max(0, a - 160):a]
        line_before = before[before.rfind("\n") + 1:] if "\n" in before else before
        if invented_at is None:
            # from the last span on, with an overlap of an announcement's length, and never more than 4,000 characters back
            m = _MD_INVENTED_EXAMPLE_RE.search(text, max(max(0, para_start), scanned_to - _INVENTED_OVERLAP, a - 4000), a)
            scanned_to = max(scanned_to, a)
            if m is not None:
                invented_at = m.start()
        if invented_at is not None and invented_at < a:
            out[k] = True
            continue
        if (_MD_GLOSS_BEFORE_RE.search(before[-60:]) or _MD_MODAL_FORM_BEFORE_RE.search(line_before[-120:])
                or _MD_FORM_NAMED_AFTER_RE.match(text, b, b + 80)):
            out[k] = True
        elif _MD_TRIGGER_AFTER_RE.match(text, b, b + 120):
            out[k] = True
            j = k  # the forms listed before it belong to the list
            while j > 0 and spans[j - 1][1] <= spans[j][0] and _MD_FORM_JOIN_RE.match(text[spans[j - 1][1]:spans[j][0]]):
                out[j - 1] = True
                j -= 1
        elif k and out[k - 1] and spans[k - 1][1] <= a and _MD_FORM_JOIN_RE.match(text[spans[k - 1][1]:a]) and not _ATTRIBUTION_BEFORE_RE.search(before[-40:]):
            out[k] = True  # 'means "the new one" or "the newcomer"', '"¿Cómo están?", "su casa", "los echo mucho de menos"'
    return out


#: A paragraph break, read once per text by :func:`_form_flags`.
_PARAGRAPH_BREAK_AT_RE = re.compile(r"\n(?=\n)")
#: How far back :func:`_form_flags` reads again for an announcement cut by the previous span's position (longer than any announcement).
_INVENTED_OVERLAP = 200


def own_text_kinds(text: str, spans: Optional[Sequence[tuple[int, int, str]]] = None) -> list[Optional[str]]:
    """THE reader of the writer's own quoted words (rules ``own-model`` and ``own-text``; round-10 leftover R10-OWN-TEXT-ONE-READER:
    the channel, the packs and the transfer auditor read them with this one function): per quotation span of ``text`` (``spans``,
    default :func:`markdown.find_quotation_spans`), :data:`OWN_FORM`, :data:`OWN_FRAME` or None (a quotation of a text). A FORM is a
    cue of :func:`_form_flags` or of the gloss, base-form, language-form, recommended-form, named-phrase, class and invented-example
    cues read around the span; a FRAME is a correction after an arrow, a labelled model, rewrite, topic or line of inquiry, a model
    lead, or a span offered "instead of" or "rather than" another; a list continuing an own span takes its kind. One pass over the
    spans, each reading bounded windows before and after it; the paragraphs and the invented-example sentences are found in one pass
    each (linear)."""
    text = text or ""
    spans = list(find_quotation_spans(text) if spans is None else spans)
    if not spans:
        return []
    form = _form_flags(text, spans)
    breaks = [m.end() for m in _PARAGRAPH_BREAK_RE.finditer(text)]
    invented = [m.start() for m in _INVENTED_EXAMPLE_RE.finditer(text)]
    kinds: list[Optional[str]] = [OWN_FORM if f else None for f in form]
    for i, (start, end, inner) in enumerate(spans):
        if not inner.strip():
            kinds[i] = None
            continue
        if kinds[i] is not None:
            continue
        before = text[max(0, start - _OWN_TEXT_BEFORE):start]
        after = text[end:end + _OWN_TEXT_AFTER]
        if (_GLOSS_BEFORE_RE.search(before) or _FORM_BEFORE_RE.search(before) or _LANGUAGE_BEFORE_RE.search(before)
                or _SUGGEST_BEFORE_RE.search(before) or _PHRASE_ONLY_AFTER_RE.match(after)):
            kinds[i] = OWN_FORM
        elif (_CORRECTION_BEFORE_RE.search(before) or _OWN_LABEL_BEFORE_RE.search(before) or _PHRASE_AFTER_RE.match(after)
              or _OWN_MODEL_LEAD_RE.search(text[max(0, start - _OWN_MODEL_WINDOW):start])):
            kinds[i] = OWN_FRAME
        elif i > 0 and kinds[i - 1] is not None and _LIST_GAP_RE.match(text[spans[i - 1][1]:start][:_OWN_TEXT_BEFORE]):
            kinds[i] = kinds[i - 1]  # a list continuing an own span ('"Y" or "Z"', '"a", "b", "c"')
        if invented and kinds[i] is None:
            para = breaks[bisect.bisect_right(breaks, start) - 1] if breaks and breaks[0] <= start else 0
            k = bisect.bisect_left(invented, para)
            if k < len(invented) and invented[k] < start:
                kinds[i] = OWN_FORM
        if _CLASS_AFTER_RE.match(after):
            kinds[i] = OWN_FORM
            j = i  # the class names every member of the list it closes ('"espero que", "me gustaría que" and other ... phrases')
            while j > 0 and _LIST_GAP_RE.match(text[spans[j - 1][1]:spans[j][0]][:_OWN_TEXT_BEFORE]):
                j -= 1
                kinds[j] = OWN_FORM
    return kinds


def own_text_spans(text: str) -> list[tuple[int, int, str]]:
    """Rule ``own-text`` (round-10 clearance c3): the quotation spans ``text`` presents as the writer's own words, as ``(start, end,
    inner)``: every span :func:`own_text_kinds` reads as a FORM or a FRAME (rule ``own-model``'s included). The transfer auditor
    reads these; the channel reads the same kinds (``markdown.own_form_flags`` the FORMs, ``sources.own_model_words`` the FRAMEs
    with the supplied texts in view). Linear in the spans."""
    text = text or ""
    spans = find_quotation_spans(text)
    return [sp for sp, kind in zip(spans, own_text_kinds(text, spans)) if kind is not None]
