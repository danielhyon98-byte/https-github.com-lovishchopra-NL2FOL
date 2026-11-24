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
from .markdown import INSTEAD_OF_WORDS as _MD_INSTEAD_OF_WORDS
from .markdown import CORRECTION_IMPERATIVES as _MD_CORRECTION_IMPERATIVES
from .markdown import INSTEAD_IMPERATIVE_GAP_RE as _MD_INSTEAD_IMPERATIVE_GAP_RE
from .markdown import INSTEAD_OF_LEAD_RE as _MD_INSTEAD_OF_LEAD_RE
from .markdown import _BECOMES_GAP_RE as _MD_BECOMES_GAP_RE
from .markdown import _BUT_GAP_RE as _MD_BUT_GAP_RE
from .markdown import _CHANGE_BEFORE_RE as _MD_CHANGE_BEFORE_RE
from .markdown import _FEEDBACK_BEFORE_RE as _MD_FEEDBACK_BEFORE_RE
from .markdown import _NOT_BEFORE_RE as _MD_NOT_BEFORE_RE
from .markdown import _WORD_CORRECTION_GAP_RE as _MD_WORD_CORRECTION_GAP_RE
from .markdown import feedback_task
from .markdown import CORRECTION_RIGHT_LABELS as _MD_CORRECTION_RIGHT_LABELS
from .markdown import _FORM_JOIN_RE as _MD_FORM_JOIN_RE
from .markdown import _FORM_NAMED_AFTER_RE as _MD_FORM_NAMED_AFTER_RE
from .markdown import _GLOSS_BEFORE_RE as _MD_GLOSS_BEFORE_RE
from .markdown import _INVENTED_EXAMPLE_RE as _MD_INVENTED_EXAMPLE_RE
from .markdown import _MODAL_FORM_BEFORE_RE as _MD_MODAL_FORM_BEFORE_RE
from .markdown import _TRIGGER_AFTER_RE as _MD_TRIGGER_AFTER_RE
from .markdown import find_quotation_spans

__all__ = ["OWN_MODEL_RULE", "OWN_TEXT_RULE", "OWN_FORM", "OWN_FRAME", "CORRECTION_FREE", "CORRECTION_QUOTATION", "correction_originals", "correction_pairs",
           "correction_reading", "credits_own_text", "own_model_spans", "quotes_own_wording", "unquoted_text", "own_text_kinds",
           "own_text_spans"]

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
#: (check round 9 of c3c: also a long or plain arrow, "-->", "—>", ">", and a "Right:" or "Correct form:" label after the replaced
#: wording, '- Wrong: "x". Right: "y"')
#: (c3d, the c3c leftover 'Wrong: "x". Right: "y"' on a marking answer: the class is a LABELLED correction pair in any language the
#: specialists write: 'Incorrect: "x". Correct: "y"', 'Before: "x". After: "y"', 'Weak: "x". Stronger: "y"', 'Mal: "x". Bien:
#: "y"', 'Incorrecto: "x". Correcto: "y"', 'Faux : "x". Juste : "y"'; the label of the correction right after the replaced span)
_RIGHT_LABELS = _MD_CORRECTION_RIGHT_LABELS  # one class for both readers (``markdown.CORRECTION_RIGHT_LABELS``; c3e)
_CORRECTION_MARKS = (r"(?:→|-{1,2}>|—>|=>|⇒|⟶|⟹|➔|➜|➝|>|\bshould[ \t]{1,3}be\b[ \t:]{0,3}|\bbecomes\b[ \t:]{0,3}|"
                     # (c3e: an arrow may stand before the label, '"x" → Bien: "y"', 'Mal: "x" -> Correct: "y"')
                     r"[.;,]?[ \t]{0,3}(?:(?:→|-{1,2}>|—>|=>|⇒|⟶|⟹|➔|➜|➝)[ \t]{0,3})?(?:" + _RIGHT_LABELS + r")[ \t]{0,3}:[ \t]{0,3})")
_CORRECTION_BEFORE_RE = re.compile(r"[\"'”’»][*_ \t]{0,6}" + _CORRECTION_MARKS + r"[ \t*_]{0,6}\Z", re.IGNORECASE)
#: The longest text :data:`_CORRECTION_BEFORE_RE` matches is 50 characters (44 before c3e added the arrow before a label), and it
#: ends at the window's end (``\Z``): the search starts this many characters before the end (repair 1 after clearance c3c:
#: searching the whole window from every quotation mark in it doubled the cost of this pattern on a paragraph of thousands of
#: quotations; the reading is the same).
_CORRECTION_TAIL = 56
#: A model, topic or line of inquiry under its label at the start of a line or sentence; a parenthesis of at most 200 characters may
#: follow the label ("Model (one sentence, to show range with your own content; not a replacement for your text):").
_OWN_LABEL_BEFORE_RE = re.compile(r"(?:^|[\n.!?;])[ \t*_>#-]{0,8}(?:an?[ \t]{1,3})?(?:model|rewrite|rewritten|corrected|correction|"
                                  r"improved|revised|alternative|suggested|suggestion|topic|line[ \t]{1,3}of[ \t]{1,3}inquiry|better|stronger|right|correct|"
                                  # (c3e leftovers, ll-t16: '- Weak: "x"' over '- Strong: "y"', 'Draft: "x". Final: "y"'; never a part of a
                                  # text, 'Final line:', 'Strong opening:')
                                  r"(?:strong|final)(?![ \t]{1,3}(?:line|opening|paragraph|sentence|stanza|verse|words?))|"
                                  # the correction's label in Spanish and French (c3d: 'Mal: "x". Bien: "y"', 'Correcto: "y"', 'Juste : "y"')
                                  r"bien|correct[oa]|corregid[oa]|correcci[oó]n|mejor|(?:forma|versi[oó]n|frase)[ \t]{1,3}(?:correcta|corregida)|"
                                  r"juste|corrig[ée]e?|mieux|"
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
#: (push check of a9129c78: in every language the specialists write, ``markdown.INSTEAD_OF_WORDS``: 'en vez de', 'au lieu de')
_PHRASE_AFTER_RE = re.compile(r"\A[ \t,]{0,3}(?:" + _MD_INSTEAD_OF_WORDS + r")(?!\w)", re.IGNORECASE)
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
    cues: dict[tuple[str, str, str], tuple[bool, bool]] = {}
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
        key = (before[-60:], line_before[-120:], text[b:b + 120])
        cue = cues.get(key)
        if cue is None:
            # (pure functions of the windows: read once per distinct window, the readings unchanged; check round 13 of c3g)
            after = text[b:b + 120]
            cue = (bool(_MD_GLOSS_BEFORE_RE.search(before[-60:]) or _MD_MODAL_FORM_BEFORE_RE.search(line_before[-120:])
                        or _MD_FORM_NAMED_AFTER_RE.match(after, 0, 80)), _MD_TRIGGER_AFTER_RE.match(after) is not None)
            cues[key] = cue
        if cue[0]:
            out[k] = True
        elif cue[1]:
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


#: The writer's recommended form offered against another, after an imperative ('Use "y", not "x"', 'Say "y", not "x"', 'Escribe
#: "y", no "x"'; c3e check round 11, the overseer fixer's handoff): the first span is the writer's FRAME and the second the wording it
#: replaces (:data:`_REPLACED_GAP_RE`). Only the whole pair is read: an imperative before a lone quotation ('Use "x" in your essay')
#: names a quotation of a text, which stays one.
_USE_BEFORE_RE = re.compile(r"(?:^|[\n.!?;:(])[ \t*_>#-]{0,8}(?:(?:so|then|instead|now|rather|please),?[ \t]{1,3})?"
                            r"(?:use|say|write|try|prefer|usa|di|escribe|pon)[ \t]{0,3}:?[ \t]{0,3}\Z", re.IGNORECASE)
_NOT_THE_OTHER_AFTER_RE = re.compile(r"\A[*_ \t]{0,3},?[ \t]{0,3}(?:not|no)[ \t:]{1,3}[\"“‘«']", re.IGNORECASE)


#: What may stand before a feedback frame's lead in the gap between two spans ('"x"; a stronger version is "y"').
#: (follow-up c3g: also a conjunction and the pronoun that resumes the student's wording, '"x"; it should be "y"', '"x", but it
#: should be "y"', '«x», pero debería ser «y»', '"x" - this should read "y"', which the role reader reads as a correction in a feedback
#: task: the auditor named the correction OVS-FID-004 and failed correct marking feedback)
_FEEDBACK_LEAD_PREFIX_RE = re.compile(r"[\s*_`,;:.—–-]*+(?:(?:but|and|so|yet|pero|y|mais|et)[ \t]{1,3})?"
                                      r"(?:(?:it|this|that|this[ \t]{1,3}one|esto|eso|ça|cela|il|elle)[ \t]{1,3})?"
                                      r"(?:(?:a|an|the|una?|la|el|une|le)[ \t]{1,3})?", re.IGNORECASE)
#: How many characters a feedback correction's gap may hold.
_FEEDBACK_GAP_MAX = 60


#: A feedback lead that names the span after it as the corrected wording in any task ('a stronger version is', 'the corrected sentence
#: reads', 'lo correcto es', 'la forme correcte est'): it says what the writer recommends, never what a text does.
_LEAD_ANY_TASK_RE = re.compile(r"(?:(?:stronger|better|clearer|improved|corrected|correct|right|revised|more[ \t]{1,3}\w+)[ \t]{1,3}(?:version|form|sentence|"
                               r"phrase|phrasing|wording|word|option|line|clause)s?|lo[ \t]{1,3}(?:correcto|mejor)|(?:forma|versi[oó]n|frase|opci[oó]n)[ \t]{1,3}"
                               r"(?:correcta|corregida|mejor)|mejor[ \t]{1,3}(?:forma|versi[oó]n|frase|opci[oó]n)|bonne[ \t]{1,3}forme|forme[ \t]{1,3}correcte|"
                               r"meilleure[ \t]{1,3}(?:version|forme|phrase))\b", re.IGNORECASE)


def _feedback_pair(text: str, spans: Sequence[tuple[int, int, str]], r: int, c: int, fb: bool) -> bool:
    """Whether span ``c`` corrects span ``r`` right before it on its line by a correction written in words (c3e leftovers on ll-t16 and
    sp-t16), the frames the role reader reads in a feedback task (``markdown._span_roles``). In any task: an imperative of changing
    before the replaced wording ('Change "x" to "y"', 'Replace "x" with "y"', 'Rewrite "x" as "y"', 'Cambia "x" por "y"', 'Remplace
    « x » par « y »'), 'Instead of "x", write "y"', and a lead that names the corrected wording ('You wrote "x"; a stronger version is
    "y"', 'Escribiste «x»; lo correcto es «y»'); they say what the writer recommends, never what a text does. In a feedback task only
    (``fb``, ``markdown.feedback_task``): '"x" becomes "y"', 'Your sentence "x" could become "y"' and 'Not "x" but "y"', 'No «x» sino
    «y»', which in an analysis describe the text ('the "rose" becomes a "canker"', 'not "angry" but "resigned"'), so both spans stay
    quotations there. The replaced span is then the wording an own correction replaces (:func:`correction_pairs`) and the correction a
    FRAME, both decided with the supplied texts in view as any own correction (``sources.own_model_words``, INV-Q1). Bounded windows."""
    if not (0 <= r < c < len(spans)) or spans[r][1] > spans[c][0]:
        return False
    gap = text[spans[r][1]:spans[c][0]]
    if len(gap) > _FEEDBACK_GAP_MAX or "\n" in gap:
        return False
    before_r = text[max(0, spans[r][0] - 60):spans[r][0]].rstrip(" \t*_`")
    if _MD_WORD_CORRECTION_GAP_RE.match(gap):
        word = gap.strip(" \t*_`:,").lower()
        if word in ("to", "into", "with", "by", "as", "por", "par", "con", "en"):
            return _MD_CHANGE_BEFORE_RE.search(before_r) is not None
        return fb
    if _MD_BECOMES_GAP_RE.match(gap):
        return fb
    if _MD_BUT_GAP_RE.match(gap):
        return fb and _MD_NOT_BEFORE_RE.search(before_r) is not None
    if _MD_INSTEAD_IMPERATIVE_GAP_RE.fullmatch(gap):
        return _MD_INSTEAD_OF_LEAD_RE.search(text, max(0, spans[r][0] - 60), spans[r][0]) is not None
    if _WROTE_THEN_WRITE_GAP_RE.fullmatch(gap):
        # 'You wrote "x"; write "y" instead', 'Escribiste «x»; escribe «y»' (check round 12 of c3f, sp-t16): the student's wording,
        # then the imperative that gives its correction, in any task
        return _STUDENT_WROTE_BEFORE_RE.search(before_r) is not None
    lead = _MD_FEEDBACK_BEFORE_RE.search(gap)
    if lead is None or _FEEDBACK_LEAD_PREFIX_RE.fullmatch(gap, 0, lead.start()) is None:
        return False
    return fb or _LEAD_ANY_TASK_RE.match(gap, lead.start()) is not None


#: The student's own words, credited to the student in a feedback task ('You wrote "x"', 'Escribiste «x»', 'Tu as écrit « x »'): the
#: wording a correction replaces, which an own correction may pair (:func:`_replaced_partner`), never a text's.
_STUDENT_WROTE_BEFORE_RE = re.compile(r"(?:\byou(?:[ \t]{1,3}have)?[ \t]{1,3}(?:wrote|written|write|put|said)|\b(?:escribiste|pusiste|dijiste|has[ \t]{1,3}escrito)"
                                      r"|\btu[ \t]{1,3}as[ \t]{1,3}(?:écrit|mis|dit)|\bvous[ \t]{1,3}avez[ \t]{1,3}(?:écrit|mis|dit))[ \t]{0,3}[,:]?\Z", re.IGNORECASE)


#: The gap between the student's wording and the imperative that gives its correction ('You wrote "x"; write "y" instead').
#: (follow-up c3g: a colon or a dash may stand before the imperative, 'You wrote "x": write "y"'; the imperatives are the role reader's
#: class, ``markdown.CORRECTION_IMPERATIVES``)
_WROTE_THEN_WRITE_GAP_RE = re.compile(r"[\s*_`]*+[;,.:—–-][ \t]{0,3}(?:(?:so|then|instead|please|alors|puis|mejor),?[ \t]{1,3})?(?:"
                                      + _MD_CORRECTION_IMPERATIVES + r")[ \t]{0,3}:?[\s*_`]*+", re.IGNORECASE)


def own_text_kinds(text: str, spans: Optional[Sequence[tuple[int, int, str]]] = None) -> list[Optional[str]]:
    """THE reader of the writer's own quoted words (rules ``own-model`` and ``own-text``; round-10 leftover R10-OWN-TEXT-ONE-READER:
    the channel, the packs and the transfer auditor read them with this one function): per quotation span of ``text`` (``spans``,
    default :func:`markdown.find_quotation_spans`), :data:`OWN_FORM`, :data:`OWN_FRAME` or None (a quotation of a text, or words of
    no fixed owner: the wording a correction replaces, which :func:`correction_pairs` names). A FORM is a cue of :func:`_form_flags`
    or of the gloss, base-form, language-form, recommended-form, named-phrase, class and invented-example cues read around the span; a
    FRAME is a correction after an arrow, a labelled model, rewrite, topic or line of inquiry, a model lead, or a span offered
    "instead of" or "rather than" another; a list continuing an own span takes its kind. One pass over the
    spans, each reading bounded windows before and after it; the paragraphs and the invented-example sentences are found in one pass
    each (linear)."""
    text = text or ""
    spans = list(find_quotation_spans(text) if spans is None else spans)
    if not spans:
        return []
    form = _form_flags(text, spans)
    fb = feedback_task(None)
    breaks = [m.end() for m in _PARAGRAPH_BREAK_RE.finditer(text)]
    invented = [m.start() for m in _INVENTED_EXAMPLE_RE.finditer(text)]
    kinds: list[Optional[str]] = [OWN_FORM if f else None for f in form]
    # (the window cues are pure functions of the window's characters: read once per distinct window, so a run of equal spans, '"a"
    # "a" "a" ...', reads each window once; the readings are unchanged. Optimisation of check round 13 of c3g: the meta-note reader's
    # hostile run of 4,900 quotations stood under 25% of its time bound)
    window_kind: dict[tuple[str, str, str], Optional[str]] = {}
    for i, (start, end, inner) in enumerate(spans):
        if not inner.strip():
            kinds[i] = None
            continue
        if kinds[i] is not None:
            continue
        before = text[max(0, start - _OWN_TEXT_BEFORE):start]
        after = text[end:end + _OWN_TEXT_AFTER]
        model_window = text[max(0, start - _OWN_MODEL_WINDOW):start]
        key = (before, after, model_window)
        cue = window_kind.get(key, "")
        if cue == "":
            if (_GLOSS_BEFORE_RE.search(before) or _FORM_BEFORE_RE.search(before) or _LANGUAGE_BEFORE_RE.search(before)
                    or _SUGGEST_BEFORE_RE.search(before) or _PHRASE_ONLY_AFTER_RE.match(after)):
                cue = OWN_FORM
            elif (_CORRECTION_BEFORE_RE.search(before, max(0, len(before) - _CORRECTION_TAIL)) or _OWN_LABEL_BEFORE_RE.search(before)
                  or _PHRASE_AFTER_RE.match(after) or _OWN_MODEL_LEAD_RE.search(model_window)
                  or (_USE_BEFORE_RE.search(before) and _NOT_THE_OTHER_AFTER_RE.match(after))):
                cue = OWN_FRAME
            else:
                cue = None
            window_kind[key] = cue
        if cue == OWN_FORM:
            kinds[i] = OWN_FORM
        elif cue == OWN_FRAME or (i > 0 and _feedback_pair(text, spans, i - 1, i, fb)):
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


#: The gap between the wording a correction replaces and its correction: an arrow, "should be" or "becomes" and nothing else
#: ('"x" -> "y"', '"x" should be "y"'). The span after the gap is the correction (a FRAME, :data:`_CORRECTION_BEFORE_RE`).
_CORRECTION_GAP_RE = re.compile(r"\A[*_ \t]{0,6}" + _CORRECTION_MARKS + r"[ \t*_]{0,6}\Z", re.IGNORECASE)
#: The gap between the writer's own form and the wording it replaces, offered after it ('"y" rather than "x"', '"y" instead of "x"',
#: '"y", not "x"').
_REPLACED_GAP_RE = re.compile(r"\A[*_ \t]{0,3},?[ \t]{0,3}(?:" + _MD_INSTEAD_OF_WORDS + r"|(?:et[ \t]{1,3})?(?:not|no|non|pas))[ \t:]{0,3}\Z",
                              re.IGNORECASE)


#: The label of the wording a correction replaces, at the start of a line or sentence ('- Wrong: "x"', 'Incorrect form: "x"',
#: 'Weak: "x"', 'Mal: "x"', 'Incorrecto: "x"', 'Faux : "x"'; c3d, the c3c leftover 'Wrong: "x". Right: "y"'): the span after it is the wording
#: an own correction replaces even when its correction stands in the next sentence, which a parser reading one sentence at a time
#: does not see. A neutral label ('Before:', 'Original:', 'Antes:', 'Avant :') marks it only with its correction in view
#: (:data:`_CORRECTION_GAP_RE`: '"x". After: "y"').
_REPLACED_LABEL_BEFORE_RE = re.compile(r"(?:^|[\n.!?;])[ \t*_>#-]{0,8}(?:wrong|incorrect|error|mistake|avoid|weak(?:er)?|poor(?:er)?|mal|incorrect[oa]|"
                                       r"err[oó]ne[oa]|evitar?|d[eé]bil|faux|fausse|incorrecte|erreur|faible|[àa][ \t]{1,3}[ée]viter)"
                                       r"(?:[ \t]{1,3}(?:form|version|sentence|wording|forma|versi[oó]n|frase))?[ \t]{0,3}"
                                       r"(?:\([^()\n\"“”]{0,200}\))?[*_]{0,2}[ \t]{0,3}:[ \t]{0,3}[*_]{0,2}\Z", re.IGNORECASE)


#: An instruction to write, which credits nothing ('Write "x" -> "y"', 'Instead, write: "x" -> "y"').
_IMPERATIVE_WRITE_BEFORE_RE = re.compile(r"(?:^|[\n.!?;:(])[ \t*_>#-]{0,8}(?:(?:so|then|instead|now|here|rather|please),?[ \t]{1,3})?write[ \t]{0,3}[,:]?\Z",
                                         re.IGNORECASE)


#: The partner :func:`_replaced_partner` gives a replaced span whose correction stands outside the text read.
_UNSEEN = -1


def _replaced_partner(text: str, spans: Sequence[tuple[int, int, str]], kinds: Sequence[Optional[str]], i: int) -> Optional[int]:
    """The index of the correction that replaces span ``i`` (a span :func:`own_text_kinds` read as neither a FORM nor a FRAME), or
    None: the FRAME right after an arrow, "should be", "becomes" or a correction's label that follows it ('"x" -> "y"', '"x".
    Right: "y"'), or the writer's own form it follows after "rather than", "instead of" or ", not" ('"y" rather than "x"');
    :data:`_UNSEEN` for a span under the label of a replaced wording ('Wrong: "x"', 'Mal: "x"') whose correction is not in the text
    read (the next sentence). A span the sentence credits to a text ('your email says "x" -> "y"', 'the poem reads "x"') is a
    quotation of that text, never wording the answer's own correction replaces."""
    start, end, inner = spans[i]
    if not inner.strip() or kinds[i] is not None:
        return None
    before = text[max(0, start - 40):start].rstrip(" \t*_")
    fb = feedback_task(None)
    if (_ATTRIBUTION_BEFORE_RE.search(before) and not _IMPERATIVE_WRITE_BEFORE_RE.search(before)
            and not _STUDENT_WROTE_BEFORE_RE.search(before)):
        return None
    if (i + 1 < len(spans) and kinds[i + 1] == OWN_FRAME and end <= spans[i + 1][0]
            and (_CORRECTION_GAP_RE.match(text[end:spans[i + 1][0]][:_OWN_TEXT_BEFORE]) or _feedback_pair(text, spans, i, i + 1, fb))):
        return i + 1  # '"x" -> "y"'
    if (i > 0 and kinds[i - 1] is not None and spans[i - 1][1] <= start
            and _REPLACED_GAP_RE.match(text[spans[i - 1][1]:start][:_OWN_TEXT_BEFORE])):
        return i - 1  # '"y" rather than "x"'
    if _REPLACED_LABEL_BEFORE_RE.search(text, max(0, start - _OWN_TEXT_BEFORE), start):
        return _UNSEEN  # 'Wrong: "x".' (its 'Right: "y"' in the next sentence)
    return None


def correction_pairs(text: str, spans: Optional[Sequence[tuple[int, int, str]]] = None,
                     kinds: Optional[Sequence[Optional[str]]] = None) -> list[tuple[int, Optional[int]]]:
    """The answer's OWN corrections among the quotation spans of ``text`` (``spans``, default :func:`markdown.find_quotation_spans`;
    ``kinds`` as :func:`own_text_kinds` reads them), as ``(replaced, correction)`` span indices (push check of 2ff70224, item
    R10-OWN-TEXT-ONE-READER still partial: in '"x" -> "y"' the reader named "y" the writer's FRAME and left "x" a quotation, which the
    English parser credited to the text under analysis, so the channel charged it INT-REQ-003 and the English pack ES-SRC-001 at error
    level). The replaced span (:func:`_replaced_partner`) keeps its kind None, words of no fixed owner: the answer's own wording, or the
    student's or a text's words it corrects. The channel decides it with the sources in view, as it decides a FRAME
    (``sources.own_model_words``: a supplied text that holds its words, altered or not, keeps it a quotation, checked as any other;
    INV-Q1; ``bus._uncredited_quotations`` still reads it against the request), and the transfer auditor keeps it a quotation. A span
    the sentence credits to a text ('your email says "x" -> "y"') is never part of an own correction. A span under the label of a
    replaced wording ('Wrong: "x"', 'Incorrect: "x"', 'Mal: "x"', :data:`_REPLACED_LABEL_BEFORE_RE`) whose correction stands
    outside ``text`` (a parser reads 'Wrong: "x".' and 'Right: "y".' as two sentences) pairs with None. Linear in the spans."""
    text = text or ""
    spans = list(find_quotation_spans(text) if spans is None else spans)
    kinds = list(own_text_kinds(text, spans) if kinds is None else kinds)
    out: list[tuple[int, Optional[int]]] = []
    for i in range(len(spans)):
        j = _replaced_partner(text, spans, kinds, i)
        if j is not None:
            out.append((i, None if j == _UNSEEN else j))
    return out


#: The roles :func:`correction_reading` gives the halves of an own correction.
CORRECTION_FREE = "free"
CORRECTION_QUOTATION = "quotation"
#: A neutral label of the replaced half ('Before:', 'Original:', 'Draft:', 'Antes:', 'Borrador:', 'Avant :'): it does not call the
#: wording wrong, so it never disclaims it (an altered quotation of a supplied text under it stays a quotation, INV-Q1).
_NEUTRAL_LABEL_BEFORE_RE = re.compile(r"(?:^|[\n.!?;])[ \t*_>#-]{0,8}(?:before|original|draft|first[ \t]{1,3}draft|antes|original|borrador|avant|"
                                      r"brouillon)(?:[ \t]{1,3}(?:version|sentence|wording|versi[oó]n|frase))?[ \t]{0,3}[*_]{0,2}[ \t]{0,3}:[ \t]{0,3}[*_]{0,2}\Z",
                                      re.IGNORECASE)
#: Fewest words of a corrected half read against the supplied texts (a shorter one is a phrase any text may share).
_SOURCE_CORRECTION_MIN_WORDS = 3


def correction_reading(text: str, docs: "dict[str, str]", spans: Optional[Sequence[tuple[int, int, str]]] = None,
                       kinds: Optional[Sequence[Optional[str]]] = None, *, task_type: Optional[str] = None) -> dict[int, str]:
    """The halves of the answer's own corrections read by ROLE against the supplied texts (``docs``: document id -> text), by span
    index of ``text`` (``spans``, default :func:`markdown.find_quotation_spans`). Push check of a9129c78 (the critical-fixes lens and the
    challenger, ll-t16): the replaced half and the corrected half were read alike, so a correction that restores a source's exact
    wording ('Wrong: "Not every kitchen has a home." Right: "Not every kitchen has a door."') was charged ES-SRC-001 and INT-REQ-003 at
    error on its replaced half, while a corrected half that alters the source ('Mal: "Made with love." Bien: "Made with care. Finished
    with care."') drew nothing. Now, for each pair of :func:`correction_pairs` with both halves in ``text``:

    * :data:`CORRECTION_FREE` for the replaced half when the corrected half presents a supplied text's wording EXACTLY (of three
      words or more) and the replaced half is a near version of that text (all its words but one or two) that no supplied text
      holds: the writer's own example of the misquotation it corrects. A neutral label ('Before:', 'Original:', 'Draft:') does not
      call the wording wrong, so it frees nothing (INV-Q1: an altered quotation under it stays one);
    * :data:`CORRECTION_QUOTATION` for the corrected half when it presents the SOURCE's wording, so it is checked against the source
      like any quotation: it is of three words or more, no supplied text holds it, a supplied text holds all its words but one or two
      (an altered quotation of that text), and the replaced half is not the student's own wording a supplied text holds outside its
      quotation marks (a marking correction of the student's email, 'Mal: "El primer semana fue difícil". Bien: "La primera semana
      fue difícil"', is the writer's correction): either no supplied text holds the replaced half, or one holds it inside its own
      quotation marks (the advert's slogan the notes quote, 'Before: "Every kitchen has a story." After: "Every kitchen has a
      secret."'), whose wording is the quoted source's and never the student's to correct.

    Every other half keeps its reading. Linear in the spans; each half is read against each text once. ``task_type`` as for
    :func:`own_text_spans` (follow-up c3g)."""
    if task_type is not None:
        from .markdown import quotation_task
        with quotation_task(task_type):
            return correction_reading(text, docs, spans, kinds)
    from ..translate.grounding import locate_excerpt
    from .sources import SuppliedText, nearest_text
    text = text or ""
    if not docs:
        return {}
    spans = list(find_quotation_spans(text) if spans is None else spans)
    pairs = [(r, c) for r, c in correction_pairs(text, spans, kinds) if c is not None]
    if not pairs:
        return {}
    supplied = {d: SuppliedText(document_id=d, title=None, author=None, text=t) for d, t in docs.items()}
    quoted_cache: dict[str, list[str]] = {}

    def strip(ex: str) -> str:
        return ex.strip().strip(".,;:!?").strip()

    def held(ex: str) -> list[str]:
        return [d for d, t in docs.items() if locate_excerpt(ex, t) is not None]

    def near(ex: str) -> Optional[str]:
        words = len(ex.split())
        doc, missing = nearest_text(ex, supplied)
        return doc if doc is not None and 0 < len(missing) <= 2 and len(missing) < words else None

    def held_quoted(ex: str, doc_id: str) -> bool:
        if doc_id not in quoted_cache:
            quoted_cache[doc_id] = [inner.casefold() for _a, _b, inner in find_quotation_spans(docs[doc_id])]
        key = ex.casefold()
        return any(key in inner for inner in quoted_cache[doc_id])

    def near_quoted(ex: str, doc_id: str) -> bool:
        # whether the text's wording ``ex`` varies stands inside the text's own quotation marks (a quoted source's wording, the
        # advert's slogan, never the student's own to correct)
        inner = " … ".join(i for _a, _b, i in find_quotation_spans(docs[doc_id]))
        if not inner:
            return False
        doc, missing = nearest_text(ex, {doc_id: SuppliedText(document_id=doc_id, title=None, author=None, text=inner)})
        return doc is not None and len(missing) <= 2

    out: dict[int, str] = {}
    for r, c in pairs:
        ex_r, ex_c = strip(spans[r][2]), strip(spans[c][2])
        if not ex_r or not ex_c or len(ex_c.split()) < _SOURCE_CORRECTION_MIN_WORDS:
            continue
        holders_r, holders_c = held(ex_r), held(ex_c)
        if holders_c and not holders_r:
            if near(ex_r) in holders_c and not _NEUTRAL_LABEL_BEFORE_RE.search(text, max(0, spans[r][0] - _OWN_TEXT_BEFORE), spans[r][0]):
                out[r] = CORRECTION_FREE
            continue
        if holders_c:
            continue
        if holders_r and not any(held_quoted(ex_r, d) for d in holders_r):
            continue  # the student's own wording corrected: the writer's correction
        near_c = near(ex_c)
        if not holders_r and near_c is not None and near(ex_r) == near_c and not near_quoted(ex_c, near_c):
            # both halves are versions of one text's wording, neither exact ('Wrong: "La primer semana fue difícil". Right: "La primera
            # semana fue difícil"' on the student's "El primer semana fue difícil"): the replaced half is the misquotation, charged as
            # one, and the corrected half the writer's correction of it (check round 13 of c3g)
            continue
        if near_c is not None:
            out[c] = CORRECTION_QUOTATION
    return out


def correction_originals(text: str, spans: Optional[Sequence[tuple[int, int, str]]] = None,
                         kinds: Optional[Sequence[Optional[str]]] = None) -> list[bool]:
    """Per quotation span of ``text``, whether it is the wording one of the answer's own corrections replaces (:func:`correction_pairs`)."""
    text = text or ""
    spans = list(find_quotation_spans(text) if spans is None else spans)
    out = [False] * len(spans)
    for i, _j in correction_pairs(text, spans, kinds):
        out[i] = True
    return out


#: Shortest quotation read as the answer quoting its own wording (a shorter span is a phrase any text may share).
_OWN_WORDING_MIN_WORDS = 4
#: How far before a quotation's opening mark its sentence is read for who it credits the words to.
_CREDIT_WINDOW = 80
#: A quotation its sentence presents as the reader's, the task's or a text's words, in any language the specialists write ('your
#: draft says', 'you wrote', 'the task asks for', 'The instructions say', 'The exam paper says', 'La consigna dice', 'El enunciado
#: pide:', 'Le sujet dit', 'the passage reads'): the request's or a text's words, never the answer's own. Push check of af6dfe04
#: (reason 5): the English-only 'you/your/the task|request|question|prompt|student|brief' frame let 'La consigna dice "..."', 'The
#: instructions say "..."' and 'The exam paper says "..."' pass as the answer's own wording once the answer also wrote the altered
#: words in its own voice. Push check of 2be42c48 (critical_open 3): the class is every person or paper that SETS the task, and every
#: verb of asking or instructing, in any frame and language: the teacher, the examiner or the marker ('Our teacher wrote', 'Mi
#: profesora escribió:', 'Le professeur demande'), and the request itself by its verb, active, passive or impersonal ('Se nos pide lo
#: siguiente:', 'We were asked', 'On nous demande', 'Nos piden'). The cue may stand anywhere in the clause before the opening mark (no
#: sentence end or quotation mark between).
_READER_CREDIT_BEFORE_RE = re.compile(
    r"(?<![\w'’])(?:you|your|yours|yourself|"
    # the task and its parts (English)
    r"task|tasks|request|question|questions|prompt|student|students|brief|instruction|instructions|rubric|exam|examination|paper|"
    r"assignment|stimulus|mark[ \t]{1,3}scheme|markscheme|syllabus|"
    # who sets or marks the task (English)
    r"teacher|teachers|tutor|tutors|lecturer|professor|instructor|examiner|examiners|marker|markers|"
    # a verb of asking or instructing: the request, active, passive or impersonal (English)
    r"ask|asks|asked|asking|request|requests|requested|require|requires|required|instruct|instructs|instructed|told|"
    # a text under analysis (English)
    r"text|texts|source|sources|passage|extract|excerpt|poem|novel|play|transcript|document|"
    # Spanish
    r"tu|tus|tuyo|tuya|usted|ustedes|vosotros|vosotras|vuestro|vuestra|vuestros|vuestras|consigna|enunciado|instrucciones|instrucción|"
    r"tarea|pregunta|preguntas|examen|prueba|alumno|alumna|alumnos|estudiante|estudiantes|texto|textos|fragmento|pasaje|fuente|fuentes|"
    r"poema|documento|"
    r"profesor|profesora|profesores|profesoras|profe|maestro|maestra|maestros|maestras|docente|docentes|tutor|tutora|examinador|"
    r"examinadora|examinadores|corrector|correctora|"
    r"pide|piden|pidió|pidieron|pedía|pedían|pedido|pedida|pregunta|preguntan|preguntó|solicita|solicitan|solicitó|exige|exigen|"
    r"indica|indican|indicó|"
    # French
    r"ton|ta|tes|votre|vos|vous|consigne|énoncé|sujet|élève|étudiant|étudiante|texte|textes|extrait|poème|"
    r"professeur|professeure|professeurs|prof|enseignant|enseignante|enseignants|examinateur|examinatrice|correcteur|correctrice|"
    r"demande|demandent|demandé|demandée|exige|exigent)"
    r"(?!\w)[^.!?\n\"“”«»]{0,72}\Z", re.IGNORECASE)
#: The kinds and the parts of a piece of writing, in the languages the specialists write: the nouns :data:`_OWN_TEXT_CREDIT_BEFORE_RE`
#: and :data:`_OWN_PART_CREDIT_BEFORE_RE` read.
_OWN_KIND_NOUNS = (r"article|letter|e-?mail|essay|model|speech|blog|post|entry|review|story|report|answer|response|reply|version|piece|"
                   r"draft|words|wording|"
                   r"artículo|carta|correo|ensayo|modelo|discurso|entrada|reseña|respuesta|versión|borrador|palabras|"
                   r"lettre|courriel|essai|modèle|discours|réponse|brouillon|mots")
_OWN_PART_NOUNS = (r"headline|title|byline|heading|paragraph|sentence|line|opening|introduction|conclusion|ending|closing|greeting|"
                   r"sign-off|"
                   r"titular|título|encabezado|párrafo|frase|oración|línea|apertura|introducción|conclusión|cierre|saludo|despedida|"
                   r"titre|paragraphe|phrase|ligne")
#: A quotation its sentence credits to the ANSWER'S OWN text, in the answer's OWN voice (push check of 2be42c48, critical_open 3):
#: a first-person possessive before a kind or a part of a piece of writing, at most two words between ('my closing line', 'mi
#: carta', 'mon article', 'our model'; never a possessive before any other noun: 'our teacher', 'mi profesora', and 'nos' before a
#: verb in 'Se nos pide', which the af6dfe04 reader took for the French possessive), a first-person verb of writing or saying ('as I
#: wrote', 'as I said above', 'I opened with', 'como escribí'), or a kind of the answer's own writing named as the text quoted ('The
#: article opens with', 'The model opens with', 'Mi artículo empieza con'). A part alone ('the heading', 'the opening line', 'la
#: primera línea') may be the task's as well as the answer's: :data:`_OWN_PART_CREDIT_BEFORE_RE` reads it. A word that only points
#: back ('above', 'arriba', 'Como se indica arriba:') credits nothing by itself: the task may stand above too. Only such a frame lets
#: the answer's own wording stand for the source of a quotation the request holds all but one or two words of: a bare quotation, or
#: one credited to the task in any frame, is checked against the task whatever the answer writes elsewhere (push check of af6dfe04,
#: reason 5). A cue of :data:`_READER_CREDIT_BEFORE_RE` in the same clause overrides it ('the first sentence of the task').
_OWN_TEXT_CREDIT_BEFORE_RE = re.compile(
    r"(?<![\w'’])(?:"
    # a kind of the answer's own writing
    r"(?:" + _OWN_KIND_NOUNS + r")|"
    # a first-person possessive before a kind or a part of a piece of writing, at most two words between
    r"(?:my|our|mi|mis|nuestro|nuestra|nuestros|nuestras|mon|ma|mes|notre|nos)(?:[ \t]{1,3}[^\W\d_][\w'’-]{0,24}){0,2}[ \t]{1,3}"
    r"(?:" + _OWN_KIND_NOUNS + r"|" + _OWN_PART_NOUNS + r")|"
    # a first-person verb of writing or saying
    r"(?:i|we)[ \t]{1,3}(?:wrote|said|opened|began|started|ended|closed|put|stated|argued|noted|mentioned|explained|used)|"
    r"(?:escribí|dije|empecé|comencé|terminé|abrí|cerré|escribimos|dijimos|"
    r"j['’][ \t]{0,2}ai[ \t]{1,3}(?:écrit|dit|commencé|terminé)))"
    r"(?!\w)[^.!?\n\"“”«»]{0,72}\Z", re.IGNORECASE)
#: A verb that presents a text's words as that text's saying ('reads', 'says', 'states', 'dice', 'reza', 'indique'): after a part
#: alone ('The heading reads "..."', 'La primera línea dice: "..."') the part is the task's as much as the answer's.
_TEXT_SAYS = (r"reads?|read|says?|said|states?|stated|writes?|wrote|puts[ \t]{1,3}it|goes|runs|"
              r"dice|decía|dijo|pone|ponía|reza|rezaba|lee|leía|escribe|escribió|plantea|planteaba|afirma|señala|"
              r"dit|disait|écrit|indique|énonce|annonce")
#: A part of a piece of writing ('The second sentence, "..."', 'The opening of the second paragraph: "..."'), in a clause with no
#: verb presenting the words as a text's saying (:data:`_TEXT_SAYS`; push check of 2be42c48, critical_open 3: 'The heading reads
#: "..."' credited the task's heading to the answer's own text).
_OWN_PART_CREDIT_BEFORE_RE = re.compile(
    r"(?<![\w'’])(?:" + _OWN_PART_NOUNS + r")(?!\w)(?:(?!(?<![\w'’])(?:" + _TEXT_SAYS + r")(?!\w))[^.!?\n\"“”«»]){0,72}\Z",
    re.IGNORECASE)


def credits_own_text(sentence: str, span_start: int) -> bool:
    """Whether ``sentence`` credits the quotation whose opening mark is at ``span_start`` to the answer's OWN text
    (:data:`_OWN_TEXT_CREDIT_BEFORE_RE`) and to no reader, task or text under analysis (:data:`_READER_CREDIT_BEFORE_RE`): 'The
    article opens with "..."', 'The second sentence, "...", ...', 'As I said above, "..."'. A bare quotation credits nothing. One
    bounded window before the opening mark."""
    before = (sentence or "")[max(0, span_start - _CREDIT_WINDOW):span_start]
    if _READER_CREDIT_BEFORE_RE.search(before):
        return False
    return bool(_OWN_TEXT_CREDIT_BEFORE_RE.search(before) or _OWN_PART_CREDIT_BEFORE_RE.search(before))


def unquoted_text(text: str) -> str:
    """``text`` with every quotation span (:func:`markdown.find_quotation_spans`, marks included) blanked to spaces: the words the
    answer writes in its own voice. One pass over the spans."""
    text = text or ""
    parts: list[str] = []
    at = 0
    for start, end, _inner in find_quotation_spans(text):
        if start < at:
            continue
        parts.append(text[at:start])
        parts.append(" " * (end - start))
        at = end
    parts.append(text[at:])
    return "".join(parts)


def quotes_own_wording(own_unquoted: str, sentence: str, span_start: int, excerpt: str, *, credited: bool = False) -> bool:
    """Whether the quotation ``excerpt`` (its opening mark at ``span_start`` of ``sentence``) is the answer quoting its OWN earlier
    wording (round-8 attack, Language B: 'The article opens with "Cada verano, nuestra ciudad se llena de turistas".' quotes the
    first sentence of the answer's own model article word for word, and the channel charged it INT-REQ-003 as an altered quotation of
    the request): ``own_unquoted`` (:func:`unquoted_text` of the whole answer) holds its words exactly (case and blanks aside), it
    has at least four words, and its sentence does not present it as the reader's, the task's or a text's words in any language
    (:data:`_READER_CREDIT_BEFORE_RE`: 'your draft says', 'you wrote', 'the task asks for', 'The instructions say', 'La consigna
    dice'). With ``credited`` the sentence must also credit it to the answer's own text (:func:`credits_own_text`: 'The article
    opens with', 'The second sentence, "..."'): the channel asks this of a quotation the request holds all but one or two words of,
    so a bare quotation, or one credited to the task in any frame and language, is checked against the task whatever the answer
    writes elsewhere (push check of af6dfe04, reason 5). The caller keeps it checked against the supplied texts (a supplied text
    that holds it, altered or not, keeps it a quotation of that text: INV-Q1)."""
    from ..translate.grounding import locate_excerpt
    if len(re.findall(r"\w+", excerpt or "")) < _OWN_WORDING_MIN_WORDS:
        return False
    before = (sentence or "")[max(0, span_start - _CREDIT_WINDOW):span_start]
    if _READER_CREDIT_BEFORE_RE.search(before):
        return False
    if credited and not credits_own_text(sentence, span_start):
        return False
    if locate_excerpt(excerpt, own_unquoted or "") is not None:
        return True
    # (case aside, as the docstring says: a quotation that lowers the first letter of the sentence it takes up, 'Fix the agreement
    # first. In short, "fix the agreement first".', quotes the answer's own wording all the same; check round 10 of c3d)
    return locate_excerpt(excerpt.casefold(), (own_unquoted or "").casefold()) is not None


def own_text_spans(text: str, *, task_type: Optional[str] = None) -> list[tuple[int, int, str]]:
    """Rule ``own-text`` (round-10 clearance c3): the quotation spans ``text`` presents as the writer's own words, as ``(start, end,
    inner)``: every span :func:`own_text_kinds` reads as a FORM or a FRAME (rule ``own-model``'s included); the wording a
    correction replaces stays out (the auditor's control: the original of a correction stays a quotation). The transfer auditor
    reads these; the channel reads the same kinds (``markdown.own_form_flags`` the FORMs, ``sources.own_model_words`` the FRAMEs
    with the supplied texts in view). Linear in the spans. ``task_type`` (follow-up c3g) reads the frames in that task when no
    enclosing call set one (``markdown.quotation_task``; a reader outside the channel, the transfer auditor, has none in context, so a
    feedback-only frame such as '"x"; it should be "y"' was read as in no task)."""
    if task_type is not None:
        from .markdown import quotation_task
        with quotation_task(task_type):
            return own_text_spans(text)
    text = text or ""
    spans = find_quotation_spans(text)
    return [sp for sp, kind in zip(spans, own_text_kinds(text, spans)) if kind is not None]
