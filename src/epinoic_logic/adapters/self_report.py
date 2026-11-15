"""The one self-report reader every release path uses (rule ``self-certification-gate``; round-9 push-check hold on the c2
clearance commit, hold-fix round 2).

An agent's statement that its own answer was checked, verified, confirmed or recalculated is a self-report: advisory, never
evidence, never a reason to deliver, select or label an answer (repository ``CLAUDE.md``). The hold's lenses showed that a reader
built from listed phrasings does not converge: each fix named the phrasings it listed and missed the next ones. This module reads
by vocabulary CLASS instead, after normalising the text as the student sees it, and names what a self-report is NOT by the same
classes, so correct work stays deliverable.

Normalisation (:func:`reading_form`): format characters are removed (soft hyphen, zero-width space and joiners, word joiner,
bidirectional marks: every Unicode ``Cf`` character, and the combining grapheme joiner), the text is NFKC-normalised (fullwidth
forms, ligatures, superscripts), Cyrillic and Greek look-alike letters are folded to Latin, emphasis and heading marks are
removed, a quotation attributed to a source or analysed is masked, and the marks of an unattributed quotation are removed (an
unattributed quoted sentence and a scare quote inside the writer's own sentence are the writer's words), and reported speech of
an outside party ("The narrator claims that he checked ...") is masked.

The class reading (:func:`class_self_report`), clause by clause, around each CHECKING word (verify, check, double-check,
cross-check, confirm, validate, audit, prove, recalculate, review, test, go back over, run through, match, agree, and their
inflections; Spanish verificar, comprobar, validar, revisar, confirmar, recalcular, repasar, cotejar): a self-report when the
check is positive (no negation, modal, question, condition or infinitive before it in its clause) and

* its agent is an INTERNAL checker (I, we, my or our anything, an unnamed or generic checking tool: the system, the engine, Z3, a
  calculator, a GDC, the solver, the AI, Wolfram Alpha, software, a teacher or tutor) and what it checked is the answer, one of
  its parts (figures, values, numbers, calculations, steps, points, facts, answers, working, ...), a pronoun for them, or
  nothing named (a label: "Checked by Z3."); or
* it has no agent and what was checked is the answer or its parts ("The calculations were verified.", "All values confirmed
  correct.", "This has been double-checked.", "## All figures verified"); a weak checking word (review, test, match, agree, go
  back over) needs an internal checker or a correctness word in the sentence as well;

and a status label ("Self-check: passed.", "Accuracy: 100%", "Accuracy check: all correct.") is one. A sentence is NOT a
self-report when the check is a NAMED OUTSIDE party's (an agent with content of its own: the census office, the National Audit
Office, independent auditors, a study, Source A, he, she, they; a tool qualified by its subject matter: the Hollerith tabulating
system, data-logging software, a static type checker), when the items checked belong to an outside source ("the figures in Source
B", "his figures", "the company's figures"), when the check is negated, questioned, conditional or modal ("It is unclear whether
the figures above were ever checked.", "Each step can be verified by differentiating."), when it is a worked check that shows its
computation ("Check: 2(4) + 3 = 11 ✓": working for the engine to verify), or a reading strategy ("When we re-read it ..."). An
explicit reference to the writer's own answer ("in this answer") keeps an outside party's check a self-report about the answer.

Hold-fix round 3 widened the classes, not the phrasings: an internal checker is read by the class of its head (a personal
computing tool whatever its make or model, an unnamed person who marks the student's work, a check itself, an engine named by a
product name), the checking words take sign-off, vetting, vouching, re-running, reproducing and cross-referencing, an answer that
passed or holds up under a check, a first-person performative ("I can vouch for"), a tool's relayed verdict ("Z3 says every step is
valid."), and a correctness word said of the answer or its own items in its own clause ("There are no errors in this answer.").
Each sentence of a piece is read on its own. A named outside party's check narrated in the active voice or in the past is evidence
(only the perfect or present passive of the answer's own items states their status), and a worked check that shows
an arithmetic operation with its result is working whoever narrates it (:func:`is_worked_check`).

Second remedy of the round-9 hold (the assurance-scope reading below) and its round 2: a double negation, a "made sure to" check,
engine-result and status leads, a question the writer answers itself, a relayed verdict of an internal reporter, a check label on the
answer's lead, a participle label opening a sentence, and other languages are read as classes (:func:`_round2_self_report`,
:func:`_answered_check_question`); a quotation is masked only when an outside party is its source in its own clause
(:func:`_outside_attributed`); and whole-sentence vetoes (:func:`_subject_matter`: an outside context, a rejected value with its
working, an outside finding restated, a process described, the subject matter examined) hold for every reader, including
:func:`not_a_self_report`.

Round 3 of the second remedy reads the class by a property, not by phrasings (:func:`_meta_assurance`): a sentence of meta-vocabulary
only (checking, verdicts, defects, checkers, the answer and its parts, grading, function words, numbers) says nothing about the subject,
so with an assurance mark and no negation, condition, question or instruction it can only be about the answer; a quotation or report
of such a sentence is read whoever is credited with it when its words default to the answer (:func:`_relayed_meta`); a sentence in a
script the reader has no vocabulary for fails closed (:func:`_unread_script`); and content that uses the words of checking (rubric
text, a step proved earlier, a theorem's conditions, essay signposting, a research construct) is vetoed (:func:`_round3_subject_matter`).

The reader the translator's branches have read since round 9 (``markdown._template_self_certification``) is kept, so nothing it
named is lost, and its positives are held to the same vetoes (:func:`not_a_self_report`). :func:`is_self_report` is that union;
``markdown.is_self_certification`` is this function, and every caller (the parsers, the core pack's CORE-SELF-001, the overseer's
gate through the public API ``epinoic_logic.api.adapters``, the combinator's release and the service's turn checker) reads it.
Pure functions of the text, cached per piece, every window bounded.
"""
from __future__ import annotations

import functools
import re
import unicodedata
from typing import Callable, Optional

__all__ = ["claims_a_check", "wholly_self_report", "label_self_report", "report_field_texts", "report_field_self_reports", "mask_outside_quotations", "quotation_in_scope", "reading_form", "template_form", "normalise_reading", "is_self_report", "class_self_report", "not_a_self_report", "self_report_pieces",
           "is_worked_check", "reading_sentences",
           "self_report_places", "self_report_spots", "quotation_only", "claim_is_self_report", "names_self_report_in", "SELF_REPORT_STATUS"]

#: The advisory status a parser sets on a claim holding a self-report (the hub names it INT-HANDOFF-006).
SELF_REPORT_STATUS = "self-certified in the response text"

#: Longest piece read in one go; a longer piece is read clause by clause in windows of this size (the windows overlap).
_PIECE_MAX = 4000

# ============================================================================================ normalisation
#: Cyrillic and Greek letters that look like Latin ones, folded for reading only (the stored text is never changed).
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ԛ": "q", "ԝ": "w",
    "һ": "h", "ӏ": "l", "ғ": "f", "ɡ": "g", "ⅰ": "i",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X", "У": "Y", "І": "I",
    "Ј": "J", "Ѕ": "S", "Ԁ": "D", "Ԛ": "Q", "Ԝ": "W", "Һ": "H",
    "α": "a", "ο": "o", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "ϲ": "c", "ϳ": "j",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y",
    "Χ": "X", "Ϲ": "C",
    "’": "'", "‘": "'", "ʼ": "'", "′": "'",
    "‐": "-", "‑": "-", "‒": "-", "−": "-",
    " ": " ", " ": " ", " ": " ",
})
_INVISIBLE = frozenset({"͏", "ᅟ", "ᅠ", "ㅤ", "ﾠ"})


def normalise_reading(text: str) -> str:
    """``text`` as the student sees it, for reading only: every format character (Unicode ``Cf``: soft hyphen, zero-width space
    and joiners, word joiner, bidirectional marks, tag characters) and the invisible fillers removed, NFKC applied (fullwidth
    letters, ligatures, superscripts), and Cyrillic and Greek look-alike letters folded to Latin. Typographic apostrophes and
    hyphens become ASCII ones (a curly quotation mark is kept: it may delimit a quotation)."""
    if not text:
        return ""
    if text.isascii():
        return text
    kept = "".join(ch for ch in text if ch not in _INVISIBLE and unicodedata.category(ch) != "Cf")
    return unicodedata.normalize("NFKC", kept).translate(_CONFUSABLES)


_HEADING_RE = re.compile(r"^[ \t]*(?:#{1,6}[ \t]+|>+[ \t]*|(?:[-*+•]|\d{1,3}[.)])[ \t]+)")
_EMPHASIS_CHARS_RE = re.compile(r"\*{1,3}|_{2,3}|(?<!\w)_|_(?!\w)|`+|~~")

# ---- quotations: attributed (masked) or the writer's own (marks removed)
#: A reporting or analysing frame outside a quotation: the quotation is a source's words (masked), not the writer's.
_ATTRIBUTION_RE = re.compile(
    r"\b(?:says?|said|claims?|claimed|writes?|wrote|written|states?|stated|argues?|argued|insists?|insisted|declares?|declared|reports?"
    r"|reported|asserts?|asserted|tells?|told|reassures?|reassured|recalls?|recalled|notes?|noted|remarks?|remarked|boasts?|boasted"
    r"|promises?|promised|maintains?|maintained|admits?|admitted|explains?|explained|announces?|announced|adds?|added|repl(?:y|ies|ied)"
    r"|thinks?|thought|believes?|believed|swears?|swore|sworn|quotes?|quoted|cites?|cited|calls?|called|describes?|described|exclaims?"
    r"|exclaimed|cries|cried|shouts?|shouted|whispers?|whispered|mutters?|muttered|proclaims?|proclaimed|according\s+to|in\s+the\s+words\s+of"
    r"|puts?\s+it|phrase|phrases|words?|line|lines|image|imagery|metaphor|simile|term|title|motto|slogan|headline|caption|source|sources"
    r"|document|memoir|diary|letter|speech|extract|passage|text|poem|novel|play|stanza|verse|narrator|speaker|author|poet|character|minister"
    r"|writer|historian|article|advert(?:isement)?|suggests?|shows?|implies|implied|conveys?|reveals?|highlights?|emphasi[sz]es|illustrates?"
    r"|captures?|evokes?|depicts?|presents?|portrays?|signals?|indicates?|echo(?:es|ed)?|contrasts?|dice|dijo|afirma|afirm[oó]|seg[uú]n"
    r"|escribe|escribi[oó]|declara|declar[oó])\b", re.IGNORECASE)
#: A reporting frame whose reporter is the writer or an internal checker ('I can confirm: "..."', '"..." says the system'): the
#: quotation is still the writer's own.
_INTERNAL_REPORTER_RE = re.compile(
    r"\b(?:I|we)\s+(?:\w+\s+){0,2}(?:say|said|note|noted|confirm|confirmed|state|stated|report|reported|add|added|write|wrote)\b"
    r"|\b(?:says?|said|notes?|noted|reports?|reported|states?|stated|confirms?|confirmed)\s+(?:the\s+|my\s+|our\s+)?"
    r"(?:system|engine|z3|solver|calculator|gdc|checker|verifier|hub|overseer|teacher|tutor)\b"
    r"|\baccording\s+to\s+(?:the\s+|my\s+|our\s+)?(?:system|engine|z3|solver|calculator|gdc|checker|verifier|hub|overseer|teacher|tutor|me|us)\b",
    re.IGNORECASE)


def _quotations_read(text: str) -> str:
    """``text`` with each quotation masked only when an OUTSIDE party is its source in its own clause (:func:`_outside_attributed`:
    a reporting or analysing word with a named person, body or source document: "Stalin claimed that", "The narrator's line,",
    "The advert's tagline,", "printed on the packaging") AND its words are outside the answer's own scope (:func:`quotation_in_scope`);
    otherwise only its marks are removed. A frame noun alone ("Headline:", "The bottom line:", "In plain text:", "My verdict, in a
    word:"), a self-framing phrase ("In other words") or an internal reporter (the writer, a tool, an examiner, a reviewer, the
    overseer) is no outside source: the quotation is the writer's own words (second remedy of the round-9 hold, round 2: masking
    required only a frame word, so the writer's own quoted headline, line, caption or verdict was masked and delivered)."""
    from .markdown import find_quotation_spans
    spans = find_quotation_spans(text)
    if not spans:
        return text
    masked, kept = [], []
    for i, sp in enumerate(spans):
        if not quotation_in_scope(sp[2]) and _outside_attributed(_local_frame(text, spans, i), strict=True):
            masked.append(sp)
        else:
            kept.append(sp)
    out = _masked(text, masked) if masked else text
    return _unmarked(out, kept) if kept else out


#: Where the clause of a quotation's frame begins or ends: a sentence mark, a semicolon, or a coordination that opens a new clause
#: ("What the extract shows is clear, and "every figure has been verified."": the quotation stands in the writer's own clause).
_FRAME_BOUND_RE = re.compile(r"[.!?;]\s|;|,\s+(?:and|but|so|yet)\s+|\s+(?:and|but)\s+(?=(?:so|then|thus|hence|here|now)\b)", re.IGNORECASE)


def _local_frame(text: str, spans: list, i: int) -> str:
    """The words around the ``i``-th quotation in its own clause (bounded by its neighbouring quotations, so an answer of many
    quotations is read in linear time): what attributes or frames it."""
    a, b, _inner = spans[i]
    lo = spans[i - 1][1] if i > 0 else 0
    hi = spans[i + 1][0] if i + 1 < len(spans) else len(text)
    before = text[max(lo, a - 400):a]
    starts = [m.end() for m in _FRAME_BOUND_RE.finditer(before)]
    before = before[starts[-1]:] if starts else before
    after = text[b:min(hi, b + 400)]
    m = _FRAME_BOUND_RE.search(after)
    after = after[:m.start()] if m else after
    return before + " \u2026 " + after


#: Outside parties a quotation can be attributed to: people and bodies with content of their own, and source documents.
_OUTSIDE_SOURCE_RE = re.compile(
    r"\b(?:narrator|speaker|author|poet|novelist|playwright|character|protagonist|minister|president|prime\s+minister|king|queen|emperor|general"
    r"|government|ministry|regime|press|newspaper|journal|magazine|editor|journalist|reporter|historian|historians|scholar|scholars"
    r"|critic|critics|writer|economist|economists|scientist|scientists|researchers?|official|officials|spokesman|spokeswoman|spokesperson"
    r"|company|firm|manufacturer|brand|advert(?:isement)?|advertiser|tagline|slogan|brochure|packaging|leaflet|pamphlet|poster|propaganda"
    r"|manifesto|website|source|sources|document|memoir|diary|letter|speech|extract|passage|poem|novel|stanza|verse|article|report"
    r"|press\s+release|log|logbook|ledger|records|archive|inscription|placard|cartoon|textbook|witness|soldier|officer"
    r"|quartermaster|clerk|citizen|worker|workers|peasant|peasants|he|she|they|his|her|their|il|elle|él|ella|ellos)\b", re.IGNORECASE)
#: Words after a capital that show it names a party ("Stalin claimed", "Haig wrote", "Professor Lin wrote").
_NAMED_PARTY_RE = re.compile(r"(?:^|[\s(,\u2026])(?:(?:as|per)\s+)?(?P<name>[A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+){0,3})(?:'s?|\u2019s?)?\s+"
                             r"(?:claimed|claims|said|says|wrote|writes|stated|states|argued|argues|insisted|insists|declared|declares|reported|reports"
                             r"|asserted|asserts|told|tells|noted|notes|remarked|remarks|added|adds|replied|replies|announced|announces|boasted|boasts"
                             r"|promised|promises|admitted|admits|explained|explains|put\s+it|puts\s+it|recalled|recalls|proclaimed|proclaims|maintained"
                             r"|maintains|believed|believes|thought|thinks|swore|swears|dice|dijo|escribe|escribi[oó]|afirma|afirm[oó]|declara|declar[oó])\b")
#: Words before a quotation that only frame it (a line, a headline, a caption, a phrase, a verdict, a summary): no source by themselves.
_POSSESSIVE_PARTY_RE = re.compile(r"\b(?!(?:it|one|that|what|here|there|let|he|she|who|this)['\u2019]s\b)[A-Za-z][\w-]*['\u2019]s?\b(?=\s+[a-z])")


#: A word that attributes or presents a quotation as a source's (a reporting or analysing word, or a source's own medium: "reads",
#: "printed on", "tagline", "label"): the release reader masks a quotation only with one (:func:`_outside_attributed`).
_PRESENTS_RE = re.compile(r"\b(?:reads?|printed|inscribed|stamped|written|tagline|labels?|logs?|entry|entries|headline\s+of|motto\s+of)\b", re.IGNORECASE)


def _outside_attributed(frame: str, strict: bool = False) -> bool:
    """Whether the quotation's own clause ``frame`` attributes it to an outside party: a named person or body, a third person, a
    possessive source or a source document; never a self-framing phrase, the writer or an internal reporter (a tool, an examiner,
    a reviewer, the overseer). ``strict`` (the release reader) also needs a word that attributes or presents the quotation
    (:data:`_ATTRIBUTION_RE`, :data:`_PRESENTS_RE`, a possessive): 'The brochure builds trust ...: "Every figure in this brochure has
    been independently verified."' is read as written by the release reader, and masked by :func:`mask_outside_quotations`, the
    reading of a caller that decides a quotation is analysis (the auditor's FID-005)."""
    if not frame.strip(" \u2026") or _SELF_FRAME_RE.search(frame) or _INTERNAL_REPORTER_RE.search(frame) or _internal_reporter(frame) \
            or _HUB_REPORTER_RE.search(frame):
        return False
    if strict and not (_ATTRIBUTION_RE.search(frame) or _PRESENTS_RE.search(frame) or _NAMED_PARTY_RE.search(frame)
                       or re.search(r"[A-Za-z]['\u2019]s\b", frame)):
        return False  # the release reader: a source named with no word that attributes the quotation to it leaves it the writer's
    if _OUTSIDE_SOURCE_RE.search(frame) or _NAMED_PARTY_RE.search(frame):
        return True
    for pm in _POSSESSIVE_PARTY_RE.finditer(frame):
        owner = pm.group(0).lower().rstrip("s'\u2019")
        if owner in ("answer", "essay", "response", "summary", "working", "solution", "verdict", "conclusion", "paragraph", "reply", "text",
                     "headline", "caption", "line", "note") or re.search(r"\b(?:my|our|this|the\s+answer)\s+$", frame[:pm.start()], re.IGNORECASE):
            continue  # "My summary's last line:", "this answer's headline": the writer's own words
        return True  # "The quartermaster's log", "The plan's figures": a party's own words
    m = re.search(r"\baccording\s+to\s+(?P<np>[^,;:\u2026]{1,60})", frame, re.IGNORECASE)
    return m is not None and _agent_kind(m.group("np")) == "outside"


#: The hub's own agents and checks as a quotation's reporter ("The overseer wrote:", "As the reviewer noted,", "The audit
#: reported:", "according to my checks"): the quotation relays a check of this answer, never an outside source's words.
_HUB_REPORTER_RE = re.compile(r"\b(?:the|our|my|an?)\s+(?:own\s+)?(?:overseer|reviewer|auditor|audit|hub|router|combinator|grader|qa\s+(?:team|agent|check|process)"
                              r"|checks?|verification|validation|logic\s+engine|engine|solver|prover|checker|verifier|system)s?\b|\bepinoic\b", re.IGNORECASE)


#: Phrases with which the writer restates its own words: no attribution ("In other words, "..."", "To put it simply: "..."").
_SELF_FRAME_RE = re.compile(r"\b(?:in\s+other\s+words|in\s+(?:my|our)\s+(?:own\s+)?words|(?:to\s+)?put\s+(?:it\s+)?(?:simply|briefly|plainly|differently"
                            r"|another\s+way|bluntly|shortly)|simply\s+put|that\s+is(?:\s+to\s+say)?|in\s+short|in\s+sum(?:mary)?|to\s+sum\s+up"
                            r"|to\s+summari[sz]e|as\s+(?:I|we)\s+(?:\w+\s+){0,2}?(?:said|say|wrote|write|noted|note|put\s+it|stated|state)|en\s+otras\s+palabras"
                            r"|autrement\s+dit|en\s+d'autres\s+termes)\b", re.IGNORECASE)
#: Words of a quotation that refer to THIS answer: the answer or the text above named, its parts anchored in it ("every figure
#: here", "every figure in it", "so far"). Such a quotation is read whoever it is attributed to. Generic checking words ("proved",
#: "receipts", "QA", "the answer") do not by themselves make a source's quotation the writer's (second remedy, round 2: a
#: source under analysis, Stalin's "all the figures in this report ... proved", a quartermaster's "All receipts checked", a
#: package's "QA: pass", was read as the writer's self-certification).
_QUOTE_SCOPE_RE = re.compile(
    r"\b(?:this|my|our)\s+(?:whole\s+|entire\s+|final\s+|own\s+)?(?:answer|response|reply|essay|explanation|working|solution|output|submission)\b"
    r"|\b(?:the\s+)?(?:text|answer|response|working|steps?|claims?|values?|figures?|calculations?|points?|everything|all|dates?|numbers?|quotations?"
    r"|results?|facts?)\s+(?:written\s+|given\s+|shown\s+|stated\s+)?(?:above|here)\b"
    r"|\b(?:the|all\s+of\s+the|everything)\s+above\b|\bso\s+far\b|\bin\s+(?:this|my|our)\s+(?:answer|response|reply|working|solution)\b"
    r"|\b(?:every|each|all|any)\s+(?:\w+\s+){0,2}?(?:in|of)\s+it\b|\besta\s+respuesta\b|\bcette\s+r[ée]ponse\b|\bdiese[rs]?\s+antwort\b|\bquesta\s+risposta\b",
    re.IGNORECASE)


def mask_outside_quotations(text: str) -> str:
    """``text`` with every quotation masked that an outside party is the source of in its own clause (:func:`_outside_attributed`)
    and whose words are outside the answer's own scope (:func:`quotation_in_scope`): the reading of a caller that decides whether
    quoted words are analysis of a supplied text (the auditor's FID-005: a brochure's "Every figure in this brochure has been
    independently verified." quoted in an analysis is the brochure's) or whether a field beside the response copies a quotation.
    A quotation that refers to this answer, the text above or its parts is never masked, nor one whose frame names no outside party
    (the writer's own headline or caption). Never used by a release gate, which reads :func:`is_self_report`."""
    if not isinstance(text, str) or not text:
        return text or ""
    from .markdown import find_quotation_spans
    spans = find_quotation_spans(text)
    if not spans:
        return text
    masked = [sp for i, sp in enumerate(spans) if not quotation_in_scope(sp[2]) and _outside_attributed(_local_frame(text, spans, i))]
    return _masked(text, masked) if masked else text


def quotation_in_scope(inner: str) -> bool:
    """Whether the words of a quotation are in the answer's own scope (:data:`_QUOTE_SCOPE_RE`): such a quotation is never
    masked, whoever it is attributed to."""
    return bool(inner) and _QUOTE_SCOPE_RE.search(normalise_reading(inner)) is not None


#: The heads a reporter is read by in a quotation's frame: tools and the people and agents that check a student's work.
def _internal_reporter(frame: str) -> bool:
    """Whether the frame of a quotation names the writer or an internal checker as its reporter ("As my colleague put it",
    "As the examiner wrote", "The checker reported:", "Another agent noted:"): the quotation is then the writer's own report."""
    if re.search(r"(?:^|\s)(?:I|we)\b", frame):
        return True
    for m in _REPORTER_NP_RE.finditer(frame):
        if _agent_kind(m.group(0)) == "internal" or _PIPELINE_HEAD_RE.search(m.group(0)):
            return True
    return False


def _masked(text: str, spans: list) -> str:
    """``text`` with each quotation's words masked; its marks become spaces and its sentence marks stay, so a sentence that
    ends inside the quotation still ends there."""
    out = list(text)
    for a, b, _inner in spans:
        for i in range(a, b):
            if not out[i].isspace() and out[i] not in ".!?":
                out[i] = "x"
        out[a] = " "
        out[b - 1] = " "
    return "".join(out)


def _unmarked(text: str, spans: list) -> str:
    out = list(text)
    for a, b, _inner in spans:
        out[a] = " "
        out[b - 1] = " "
    return "".join(out)


def template_form(text: str) -> str:
    """``text`` as the template rules read it (:func:`markdown._template_self_certification`, and the auditor's independent
    structural detector): normalised and unmarked as :func:`reading_form` reads it, but with EVERY quotation masked (a quoted
    self-report is the quoted text's for these rules; the class reading reads an unattributed one), and an outside party's
    reported speech masked."""
    from .markdown import find_quotation_spans
    s = normalise_reading(text or "")
    s = "\n".join(_HEADING_RE.sub("", ln) for ln in s.split("\n")) if ("#" in s or ">" in s or "\n" in s or s[:1] in "-*+•0123456789") else s
    s = _EMPHASIS_CHARS_RE.sub("", s) if any(c in s for c in "*_`~") else s
    s = " ".join(s.split())
    spans = find_quotation_spans(s)
    s = _masked(s, spans) if spans else s
    return " ".join(_reported_speech_masked(s).split())


# ---- reported speech of an outside party, unquoted
_REPORTER_VERBS = (r"(?:claims?|claimed|says?|said|insists?|insisted|asserts?|asserted|states?|stated|argues?|argued|tells?\s+\w+|told\s+\w+"
                   r"|reassures?\s+\w+|reassured\s+\w+|reports?|reported|writes?|wrote|maintains?|maintained|boasts?|boasted|declares?|declared"
                   r"|believes?|believed|thinks?|thought|swears?|swore|promises?|promised|admits?|admitted|recalls?|recalled|explains?|explained"
                   r"|alleges?|alleged|suggests?|suggested|implies|implied)")
_REPORTED_SPEECH_RE = re.compile(rf"^(?P<reporter>[^;:.!?]{{1,120}}?)\s+{_REPORTER_VERBS}(?:\s*[,:]|\s+that\b|(?=\s+(?:he|she|they|it|the|his|her|their|its"
                                 rf"|all|every|each|these|this|those|none|nothing|everything|a|an)\b))", re.IGNORECASE)


def _reported_speech_masked(text: str) -> str:
    """``text`` with the complement of an outside party's reported speech masked ("The narrator claims that he has checked every
    figure himself, ..." keeps only "The narrator claims"): what a third party says about its own checking is the source's claim,
    analysed or reported, not the writer's self-report. A reporter that is the writer or an internal checker ("I", "the system",
    "my teacher") is no outside party, and its report is read."""
    m = _REPORTED_SPEECH_RE.match(text)
    if m is None:
        return text
    reporter = m.group("reporter")
    if _agent_kind(reporter) != "outside" or _ANSWER_REF_RE.search(reporter) or _internal_reporter(reporter):
        return text
    if _QUOTE_SCOPE_RE.search(text, m.end()):
        return text  # what the party is reported to say refers to this answer or names a checking engine: read (second remedy)
    end = len(text)
    tail = _WRITER_RESUMES_RE.search(text, m.end())
    if tail is not None:
        end = tail.start()
    return text[:m.end()] + " " + "x" * max(0, end - m.end() - 1) + text[end:]


#: Where the writer's own words resume after a reported complement ("..., but I have rechecked all of them").
_WRITER_RESUMES_RE = re.compile(r"[;]\s|,\s+(?:but|and|yet|so)\s+(?:I|we|my|our|there|this|that|it|everything|nothing|all|every|each)\b|\.\s"
                                r"|\s[—–]\s?|\s-{1,2}\s|\s?[(\[](?=\s*(?:all\s+|fully\s+)?(?:note|nb|n\.b\.|ps|p\.s\.|verified|checked|confirmed|validated|double-checked|cross-checked|correct|accurate|100)\b)|[,:]\s*(?=(?:note|nb|n\.b\.|ps|p\.s\.)\b)", re.IGNORECASE)
# (hold-fix round 3: a dash, a parenthesis or a note lead after the complement, and ", and there is ...", hand the sentence back to the
# writer: "The tuning suggests ... temporary — note: nothing in this answer needs fixing." certifies the writer's answer)


def reading_form(text: str) -> str:
    """``text`` as every self-report reading reads it: :func:`normalise_reading`, heading, list, blockquote and emphasis marks
    removed, quotations read by attribution (:func:`_quotations_read`), an outside party's reported speech masked
    (:func:`_reported_speech_masked`), whitespace collapsed."""
    s = normalise_reading(text or "")
    s = "\n".join(_HEADING_RE.sub("", ln) for ln in s.split("\n")) if ("#" in s or ">" in s or "\n" in s or s[:1] in "-*+•0123456789") else s
    s = _EMPHASIS_CHARS_RE.sub("", s) if any(c in s for c in "*_`~") else s
    s = " ".join(s.split())
    s = _quotations_read(s)
    s = _reported_speech_masked(s)
    return " ".join(s.split())


# ============================================================================================ vocabulary classes
#: Answer-part nouns: the answer itself and the items it is made of.
_PART = (r"(?:answers?|responses?|repl(?:y|ies)|explanations?|essays?|paragraphs?|workings?|solutions?|calculations?|computations?|figures?"
         r"|values?|numbers?|steps?|points?|facts?|dates?|statistics?|stats|totals?|sums?|quotations?|quotes?|citations?|claims?|marks?"
         r"|arithmetic|conversions?|substitutions?|units?|work|equations?|answer\s+key|figures\s+and\s+dates|dates\s+and\s+figures"
         r"|results?|data|readings|measurements?|percentages?|ratios?|amounts?|statements?|details?|parts?|items?|sections?|lines?|entries"
         r"|c[aá]lculos?|pasos?|valor(?:es)?|cifras?|datos?|resultados?|respuestas?|operaci(?:ón|on|ones)|n[uú]meros?|fechas?|textos?)")
#: Parts that are often the subject matter itself (an experiment's results, a survey's data): read as the answer's own only with
#: a quantifier, a demonstrative or a possessive of the writer, or an anchor in the answer.
_WEAK_PART_RE = re.compile(r"^(?:results?|data|readings|measurements?|percentages?|ratios?|amounts?|statements?|details?|parts?|items?"
                           r"|sections?|lines?|entries|claims?|dates?|marks?|units?|equations?|resultados?|datos?|fechas?|textos?)$", re.IGNORECASE)
_PART_RE = re.compile(rf"\b{_PART}\b", re.IGNORECASE)
#: Modifiers that leave a part the answer's own ("the final values", "the calculated totals", "the numerical answers").
_PART_MODIFIERS = frozenset("""accuracy correctness validity reliability precision above final key numerical numeric main individual relevant other remaining different calculated computed written
given stated quoted cited listed shown following preceding important whole entire single new corrected revised resulting intermediate worked
own same various several many some both two three four five six seven eight nine ten various total overall exact quantitative numerical
historical given used mentioned made presented provided included supplied required requested and of the these those my our every each all
this that one ones last first second third""".split())
_DETERMINERS = frozenset("all every each these those this that my our the both either any whole entire todo todos toda todas cada este esta "
                         "estos estas mi mis nuestro nuestra nuestros nuestras el la los las un una".split())
_STRONG_DETERMINERS = frozenset("all every each these those this my our both whole entire todo todos toda todas cada este esta estos estas mi "
                                "mis nuestro nuestra nuestros nuestras".split())
#: Pronouns that stand for the answer or its parts as what was checked.
_THEME_PRONOUN_RE = re.compile(r"^(?:lo|los|las|this|these|those|everything|everything\s+(?:above|here|else)|all(?:\s+of\s+(?:it|them|this|these|the\s+above))?"
                               r"|all\s+(?:above|here)|each(?:\s+one)?|every\s+one(?:\s+of\s+them)?|both|the\s+above|it\s+all|them\s+all"
                               r"|they(?:\s+all)?|it|them|todo|todos|todas|esto|estos|estas)$", re.IGNORECASE)
#: The writer's own answer named explicitly.
_ANSWER_REF_RE = re.compile(
    r"\b(?:this|my|our)\s+(?:whole\s+|entire\s+|final\s+|own\s+)?(?:answer|response|reply|essay|explanation|working|solution|paragraph|work"
    r"|calculation|report|text)\b|\bthe\s+(?:whole|entire)\s+(?:answer|response|essay|working|solution|text)\b|\bthe\s+answer\s+above\b"
    r"|\b(?:esta|mi|nuestra)\s+respuesta\b|\beste\s+texto\b", re.IGNORECASE)
#: An anchor in the answer ("above", "here", "in the table below").
_ANCHOR_RE = re.compile(r"^(?:above|here|below|given|stated|shown|listed|made\s+here|in\s+(?:this|the|my|our)\s+(?:answer|response|working|solution"
                        r"|paragraph|essay|explanation|table|list|calculation)(?:\s+(?:above|below))?|of\s+(?:this|my|our)\s+(?:answer|response"
                        r"|working|solution|essay|explanation|calculation)|de\s+(?:esta|mi)\s+respuesta|de\s+arriba)\b", re.IGNORECASE)

#: Nouns of a check (hold-fix round 3): what an answer "passed" or "holds up under" ("Every claim above has passed verification.",
#: "The calculations above hold up under scrutiny."). Peer review is an outside party's and is not one of them.
_CHECK_NOUNS = (r"(?:verification|validation|checks?|checking|cross-?checking|double-?checking|fact-?checking|scrutiny|testing|tests?"
                r"|proof-?reading|inspection|comprobaci[oó]n|verificaci[oó]n|revisi[oó]n)")
#: Checking words. ``strong``: a check by itself; ``weak``: a check only with an internal checker or a correctness word. Read by
#: class (hold-fix round 3): every inflection and prefix of a checking verb (re-, double-, cross-, fact-, self-, spot-, sanity-),
#: its gerund where it is a re-doing ("Recalculating everything ..."), sign-off and vouching verbs, re-running and reproducing,
#: an answer passing or holding up under a check, and the Spanish stems with their first-person and participle endings.
_CHECK_RE = re.compile(
    r"\b(?P<strong>(?:re-?|double-?|cross-?|fact-?|self-?|spot-?|sanity-?|triple-?)?(?:verified|verifies|checked|confirmed|confirms|validated|validates"
    r"|audited|audits)|re-?checks|double-?checks|cross-?checks|proven|proved|re-?calculated|re-?computed|re-?worked|re-?done|re-?did"
    r"|proof-?read|certified|corroborated|vetted|signed[\s-]+off(?:\s+on)?|vouched\s+for|vouches\s+for|guaranteed|attested(?:\s+to)?"
    r"|cross-?referenced|reconciled|re-?ran|re-?run|re-?runs|re-?verified|made\s+sure|ensured|checks?\s+out|checked\s+out"
    r"|re-?(?:checking|calculating|computing|working|doing|running|verifying)|double-?checking|cross-?checking"
    r"|(?:passed|pass(?:es)?|survived?|withstood|withstands?|undergone|underwent|stood\s+up\s+to|stands?\s+up\s+to|holds?\s+up\s+(?:well\s+)?(?:under|to)"
    r"|held\s+up\s+(?:well\s+)?(?:under|to)|been\s+(?:through|subjected\s+to))\s+(?:(?:a|an|the|every|each|all|my|our|independent|careful|full"
    r"|further|thorough|rigorous|formal|final|second|automated|\w+-?step)\s+){0,3}" + _CHECK_NOUNS + r")\b"
    r"|\b(?P<weak>reviewed|reviews|tested|matched|matches|match|agrees?|agreed|tallies|tallied|tally|gone\s+(?:back\s+)?over|went\s+(?:back\s+)?over"
    r"|go(?:ne)?\s+through|went\s+through|r[au]n\s+(?:\w+\s+){0,4}?through|(?:put|fed|feed|entered|typed)\s+(?:\w+\s+){0,4}?(?:through|into)"
    r"|(?:gives?|gave|give|got|get|gets|yields?|yielded|produced?|produces)\s+(?:\w+\s+){0,2}?(?:the\s+same|identical)"
    r"|comes?\s+out\s+(?:\w+\s+)?the\s+same|came\s+out\s+(?:\w+\s+)?the\s+same|reproduced|approved|compared)\b"
    r"|\b(?P<es>(?:verific|comprob|valid|revis|confirm|chequ|cotej|repas|recalcul|corrobor|constat|certific|aprob|asegur|contrast)"
    r"(?:ad[oa]s?|ó|é|amos|aron|a|an)"
    r"|he\s+(?:revisado|comprobado|verificado|validado|confirmado|recalculado|repasado|cotejado|corroborado|constatado|contrastado)"
    r"|hemos\s+(?:revisado|comprobado|verificado|validado|confirmado|recalculado|repasado|cotejado|corroborado|constatado|contrastado)"
    r"|verifiqu[eé]|comprob[eé]|certifiqu[eé]"
    r"|(?:he|hemos|ha|han)\s+vuelto\s+a\s+(?:hacer|calcular|comprobar|revisar|verificar|repasar)|volv(?:í|i|imos)\s+a\s+(?:hacer|calcular|comprobar|revisar"
    r"|verificar|repasar)|rehice|rehicimos|rehecho|calcul(?:é|e|amos)\s+(?:dos\s+veces|de\s+nuevo|otra\s+vez))\b"
    r"|\b(?P<esweak>coinciden?|coincid(?:ió|ieron)|da\s+lo\s+mismo|dan\s+lo\s+mismo|dio\s+lo\s+mismo|salen?\s+(?:igual|lo\s+mismo))\b"
    r"|\b(?P<used>(?:used|employed)\s+to\s+(?:verify|check|confirm|validate|recalculate|recompute|test|prove|audit|double-check|cross-check))\b"
    r"|\b(?P<perf>confirm|verify|certify|guarantee|attest(?:\s+to)?|vouch\s+for|assure\s+you)\b",
    re.IGNORECASE)
#: A first-person performative before a bare checking verb ("I confirm", "I can vouch for", "we hereby certify"): an assertion
#: that the check is done, never a modal hedge (a base form after anything else is an instruction or a method: "Verify by ...").
_PERFORMATIVE_RE = re.compile(r"\b(?:I|we)\s+(?:(?:can|could|hereby|also|now|fully|personally|do|herewith|happily|gladly)\s+){0,3}$", re.IGNORECASE)
#: A construction whose object stands inside the checking words ("ran every figure through", "put each value into").
_THROUGH_RE = re.compile(r"^(?:r[au]n|put|fed|feed|entered|typed)\s+(?P<inner>.+?)\s+(?:through|into)$", re.IGNORECASE)
#: Correctness words: a verdict on the answer that, with a check or an internal checker, makes the sentence a self-report.
_CORRECT_RE = re.compile(
    r"\b(?:correct(?:ly)?|right|accurate|error[- ]free|flawless|faultless|impeccable|without\s+(?:any\s+|a\s+single\s+)?(?:errors?|mistakes?|slips?)"
    r"|no\s+(?:errors?|mistakes?|slips?|problems?|inaccurac(?:y|ies)|discrepanc(?:y|ies))|not\s+a\s+single\s+(?:error|mistake|slip)"
    r"|free\s+(?:of|from)\s+(?:errors?|mistakes?)"
    r"|nothing\s+(?:was\s+|is\s+)?(?:wrong|amiss|incorrect|missing|changed)|found\s+nothing\s+wrong|all\s+(?:good|fine|ok|okay|clear)|spot\s+on"
    r"|nothing\s+(?:\w+\s+){0,3}?(?:needs?|needed|requires?|required|calls?\s+for)\s+(?:any\s+)?(?:fixing|correcting|correction|changing|amending"
    r"|amendment|to\s+be\s+(?:fixed|corrected|changed|amended))|nothing\s+(?:left\s+)?to\s+(?:fix|correct|change|amend)"
    r"|word\s+for\s+word|verbatim|correct[oa]s?|bien|sin\s+errores"
    r"|no\s+(?:tiene|contiene|hay|presenta)\s+(?:ning[uú]n\s+)?errores?)\b|\b100\s*%", re.IGNORECASE)
#: A correctness word used attributively ("the correct answer", "an accurate figure from Source A"): it names a value, it does not
#: certify one.
_ATTRIBUTIVE_RE = re.compile(r"^\s*(?:[\w-]+\s+)?(?:answers?|values?|figures?|numbers?|results?|solutions?|ones?|way|method|order|formula|units?|choice"
                             r"|options?|words?|form|time|date|amount|sign|reading|interpretation|approach|response|equation|term|spelling)\b", re.IGNORECASE)
#: Words that may follow a predicative correctness word ("correct to 3 s.f.", "accurate and complete", "correct throughout").
_AFTER_PREDICATE = frozenset("""to and or but in on at for with by as when so because here there now too enough again throughout overall
apart except given since if although though while within up y o en a para""".split())
#: The answer's own items as what a correctness word is said of (hold-fix round 3: "There are no errors in this answer.", "Nothing
#: above needs fixing.", "Every claim above is correct."): the answer named, items anchored in it ("above", "here"), or items
#: quantified as the writer's ("all the values", "every figure", "my calculations").
_STRONG_PART = (r"(?:calculations?|computations?|figures?|values?|numbers?|steps?|answers?|workings?|sums?|totals?|quotations?|quotes?|facts?"
                r"|statistics?|conversions?|substitutions?|claims?|points?|dates?|c[aá]lculos?|valor(?:es)?|cifras?|n[uú]meros?|pasos?|respuestas?"
                r"|datos?|resultados?|operaci(?:ón|on|ones))")
_SELF_THEME_RE = re.compile(
    rf"\b(?:{_PART}|everything|nothing|anything|all(?:\s+of\s+(?:it|them|this))?|it\s+all|each\s+one)\s+(?:(?:written|stated|given|shown|listed"
    rf"|quoted|made|set\s+out|presented)\s+)?(?:above|here)\b"
    rf"|\b(?:all|every|each|my|our|todos?|todas?|cada|mis)\s+(?:(?:of\s+)?(?:the|my|our|these|los|las|mis)\s+)?(?:[\w-]+\s+)?{_STRONG_PART}\b"
    rf"(?!\s+(?:in|of|from|on|de|en)\s+(?!(?:this|my|our|esta|mi)\s+(?:answer|response|working|solution|essay|respuesta)|the\s+(?:answer\s+)?above\b))"
    rf"|\b(?:everything|nothing|todo|nada)\s+(?:in|of|en|de)\s+(?:this|my|esta|mi)\b", re.IGNORECASE)
#: A tool's relayed verdict on the answer ("Z3 says every step is valid.", "My calculator shows all of them are correct."): a
#: verdict the engine never signed, so a self-report.
_VERDICT_TOOL = (r"(?:z3|smt|solvers?|provers?|engines?|systems?|calculators?|gdcs?|cas|wolfram(?:\s*alpha)?|checkers?|verifiers?|software|apps?"
                 r"|spreadsheets?|excel|desmos|geogebra|calculadoras?|sistema|motor)")
_VERDICT_RE = re.compile(
    rf"(?:^|[,;:(]\s*|\band\s+|\bas\s+)(?P<np>(?:(?:the|my|our|a|an|el|la|mi)\s+)?(?:[\w-]+\s+){{0,2}}?{_VERDICT_TOOL})\s+(?:\w+ly\s+)?(?:says?|said|shows?|puts?\s+it|has\s+it"
    rf"|showed|reports?|reported|finds|found|returns?|returned|gives?|gave|outputs?|states?|stated|marks?|marked|rates?|rated|deems?|deemed"
    rf"|calls?|called|considers?|judges?|judged|agrees?|agreed|dice|indica|muestra|confirma)\b(?P<rest>[^.;!?]{{0,200}})", re.IGNORECASE)
_VALID_RE = re.compile(r"\b(?:valid|sound|consistent|true|sat(?:isfiable)?|proven|entailed|v[aá]lid[oa]s?|correct[oa]s?)\b", re.IGNORECASE)
_VERDICT_THEME_RE = re.compile(rf"\b(?:it|this|these|everything|all|each|every|both|todo|todos|todas|cada|{_STRONG_PART})\b", re.IGNORECASE)
#: A status label: "Self-check: passed.", "Accuracy: 100%", "Accuracy check: all correct.", "Verification: OK", "Status: verified",
#: "Status — verified ✓" (any dash as the separator).
_STATUS_LABEL_RE = re.compile(
    r"^\W*(?:self[- ]?check(?:ed)?|accuracy(?:\s+check)?|verification|validation|check(?:ing)?\s+status|status|review|fact[- ]check"
    r"|cross[- ]check|double[- ]check|sanity[- ]check|check|comprobaci[oó]n|verificaci[oó]n|estado)\s*[:=\-—–]+\s*(?:all\s+|fully\s+|todo\s+)?"
    r"(?:passed|pass|ok|okay|correct|confirmed|verified|validated|done|complete|completed|100\s*%|no\s+errors?|accurate|true|yes|✓|✔|correcto"
    r"|verificado|comprobado|superad[oa])(?!\w)", re.IGNORECASE)

#: Internal checkers: the writer, its possessions, and unnamed or generic checking tools and people.
#: Internal checkers by class (hold-fix round 3: a reader built from listed modifiers missed "a TI-84 calculator", "a Casio fx-991
#: calculator", "the Z3 theorem prover", "an experienced IB examiner", "a colleague", "an independent check").
#: Personal computing tools: whatever their make or model, a tool the writer used, never a party with content of its own.
_PERSONAL_TOOL_HEAD = (r"(?:calculators?|gdcs?|cas|wolfram(?:\s*alpha)?|desmos|geogebra|excel|spreadsheets?|z3|smt|solvers?|provers?|symbolab|epinoic"
                       r"|photomath|matlab|calculadoras?|hojas?\s+de\s+c[aá]lculo|casio|numworks|(?<![\w-])ti-[\w-]+|nspire|(?<![\w-])fx-[\w-]+"
                       r"|hp[\s-]?prime|python|(?<![\w-])(?:ti|fx|hp|cfx|cg|el)-?\d{2,4}[a-z+]{0,4})")  # a calculator's make or model code ("a TI-Nspire", "a Casio", "an fx-991")
#: Unnamed people who check a student's work: internal unless they are another party's ("his tutor", "Darwin's tutor").
_PERSON_HEAD = (r"(?:teachers?|tutors?|instructors?|examiners?|markers?|moderators?|colleagues?|classmates?|peers?|friends?|parents?|proofreaders?|reviewer|grader|assessor"
                r"|supervisors?|profesor(?:a|es|as)?|maestr[oa]s?|compañer[oa]s?|tutor[ae]s?)")
#: Generic tools: internal only with modifiers of a checking tool, or (an engine, a checker) a product name; otherwise qualified by
#: their subject matter ("the Hollerith tabulating system", "data-logging software", "a static type checker"): content.
_GENERIC_TOOL_HEAD = (r"(?:systems?|engines?|software|computers?|ai|models?|checkers?|verifiers?|programs?|programmes?|apps?|assistants?|chatbots?"
                      r"|sistemas?|motor|ordenador|computadora|verificador|herramienta)")
#: Generic heads that take a product name as an internal checker ("the Epinoic engine").
_NAMED_TOOL_HEAD_RE = re.compile(r"^(?:engines?|checkers?|verifiers?|assistants?|chatbots?|ai|apps?|motor|verificador)$", re.IGNORECASE)
#: A check as the agent ("validated by an independent check", "confirmed by a second verification"): the writer's own check unless
#: another party's ("the ONS's check").
_CHECK_NOUN_HEAD = (r"(?:checks?|cross-?checks?|double-?checks?|re-?checks?|recalculations?|recomputations?|verifications?|re-?checking|audit"
                    r"|comprobaci[oó]n|verificaci[oó]n)")
_TOOL_HEAD = rf"(?:{_PERSONAL_TOOL_HEAD}|{_PERSON_HEAD}|{_GENERIC_TOOL_HEAD}|{_CHECK_NOUN_HEAD})"
_TOOL_MODIFIERS = frozenset("""the a an my our this that same own ai automated automatic verification verifying logic checking graphing graphic
scientific online formal z3 smt built-in internal maths math calculator answer marking teaching class ai-powered automated-checking epinoic
independent second third final further separate quick careful full manual extra additional
el la mi nuestro nuestra un una de del verificación""".split())
_FIRST_PERSON_RE = re.compile(r"^(?:i|we|i've|we've|i'd|we'd|i'm|we're|me|us|myself|ourselves|yo|nosotros|nosotras)$", re.IGNORECASE)
_THIRD_PERSON_RE = re.compile(r"^(?:he|she|they|one|someone|somebody|people|others|he's|she's|they've|they'd|he'd|she'd)$", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\W_][\w'-]*", re.UNICODE)


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


#: The hub's own infrastructure as a word: neither an internal checker this reader names (the template rules read it) nor an outside
#: party (a plantation's overseer, a railway hub: content).
_INFRA_RE = re.compile(r"\b(?:overseer|overseers|hub|router|translator|combinator|channel|pipeline)\b", re.IGNORECASE)
#: Words a noun phrase does not end with: a coordination or a preposition before the check.
_CONNECTIVES = frozenset("and or but nor with to of in on at by for from that which who whom then so as than when while y o que de en con por a".split())
#: Finite verbs that show the words before a check are a clause, not a party's name.
_FINITE = frozenset("is are was were be been being has have had do does did read reads seems seem appears appear es son fue fueron".split())
#: People nouns that name a party even alone ("historians confirmed", "auditors verified").
_PEOPLE = frozenset("historians scholars scientists researchers officials experts auditors inspectors clerks officers critics studies authorities "
                    "economists analysts statisticians commentators archaeologists sources witnesses investigators".split())


#: Words that open a sentence with a capital but name no party.
_NOT_A_NAME = frozenset("""all every each this these those that it they we i everything nothing both none some any most many which what
then so thus hence also here there checked verified confirmed validated audited calculations figures values numbers steps answers
todo todos todas cada esto estos""".split())


def _proper_subject(np: str, clause: str) -> bool:
    """Whether ``np``, the words before an active check with an object, is one capitalised name opening its clause ("Eurostat",
    "Gallup"): a named outside party, though its capital may only mark the sentence's start."""
    raw = _WORD_RE.findall(np)
    if len(raw) != 1:
        return False
    w = raw[0]
    if not w[:1].isupper() or w.lower() in _NOT_A_NAME or re.fullmatch(_PART, w, re.IGNORECASE) or re.fullmatch(_TOOL_HEAD, w, re.IGNORECASE):
        return False
    return clause.lstrip(" \"'([*").startswith(w)


def _sentence_initial(np: str, word: str) -> bool:
    """Whether ``word`` is the first word of ``np`` (a capital that may only mark the sentence's start)."""
    return np.strip().split()[0].strip("\"'([") == word


@functools.lru_cache(maxsize=65536)
def _agent_kind(np: str) -> Optional[str]:
    """``internal`` (the writer, its possessions, an unnamed or generic checking tool or person), ``outside`` (a party with content
    of its own: a named body, a person, a study, a source, a tool qualified by its subject matter), or None (nothing that can act)."""
    raw = _WORD_RE.findall(np)[-6:]
    ws = [w.lower() for w in raw]
    if not ws:
        return None
    if any(_FIRST_PERSON_RE.match(w) for w in ws) or ws[0] in ("my", "our", "mi", "mis", "nuestro", "nuestra"):
        return "internal"
    if ws[-1] in ("hand", "mano") and len(ws) <= 3:
        return "internal"  # by hand
    joined = " ".join(ws)
    head = re.search(rf"\b{_TOOL_HEAD}$", joined, re.IGNORECASE)
    if head is not None:
        n_head = len(head.group(0).split())
        mods_raw = raw[:len(raw) - n_head]
        # modifiers before the tool's head, from the nearest determiner on
        cut = max((i for i, w in enumerate(mods_raw) if w.lower() in ("the", "a", "an", "my", "our", "this", "el", "la", "un", "una", "mi")), default=-1)
        mods_raw = mods_raw[cut + 1:] if cut >= 0 else mods_raw[-2:]
        mods = [w.lower() for w in mods_raw]
        h = head.group(0)
        another_party = any(m in ("his", "her", "their", "its", "su", "sus") for m in mods) or any(
            r.endswith(("'s", "s'")) and r[:1].isupper() for r in mods_raw)
        if re.fullmatch(_PERSONAL_TOOL_HEAD, h, re.IGNORECASE):
            return "internal"  # a calculator, a GDC, Z3, a prover, a spreadsheet: whatever its make or model ("a TI-84 calculator")
        if re.fullmatch(_PERSON_HEAD, h, re.IGNORECASE) or re.fullmatch(_CHECK_NOUN_HEAD, h, re.IGNORECASE):
            return "outside" if another_party else "internal"  # "an experienced IB examiner", "a colleague", "an independent check"
        named_ok = _NAMED_TOOL_HEAD_RE.match(h) is not None
        if all(m in _TOOL_MODIFIERS or (named_ok and (r[:1].isupper() or any(ch.isdigit() for ch in r))) for m, r in zip(mods, mods_raw)):
            return "internal"
        return "outside"
    if _INFRA_RE.search(" ".join(ws)):
        return None  # the hub's own infrastructure (router, overseer, hub, channel): read by the template rules, never vetoed here
    if _THIRD_PERSON_RE.match(ws[-1]) or _THIRD_PERSON_RE.match(ws[0]):
        return "outside"
    if ws[-1] in _CONNECTIVES:
        return None  # "... the supplied poem and matches": the subject stands before the coordination, not here
    if any(w in _FINITE for w in ws):
        return None  # "... an apostrophe are read, checked": a clause, not a noun phrase that names a party
    if ws[-1] in ("it", "this", "that", "these", "those", "which", "who", "all", "everything", "each", "both", "them"):
        return None
    if re.fullmatch(_PART, ws[-1], re.IGNORECASE):
        return None  # a part of the answer cannot check itself
    if ws[-1].endswith("ing") and len(ws) <= 4:
        return None  # a method ("by substituting", "by repeating the experiment"): no agent named
    raw = _WORD_RE.findall(np)[-6:]
    if len(ws) == 1:
        # one word names a party only as a people noun ("historians"), an acronym ("ONS") or a proper noun inside the sentence
        # ("Engels"); "accuracy confirmed", "As verified", "Formally proven" name none
        word = raw[-1] if raw else ""
        if not (ws[0] in _PEOPLE or (len(word) > 1 and word.isupper()) or (word[:1].isupper() and not _sentence_initial(np, word))):
            return None
    return "outside"


# ---- clauses and the windows around a check
_CLAUSE_SPLIT_RE = re.compile(r"[;:()\[\]—–|]|\s-\s|,\s+(?=(?:but|yet|so|which|while|whereas|although|though|because|since|and\s+(?:I|we|it|they|the|this|these|my|our|nothing|all|every|each))\b)"
                              r"|\.\s+|[.!?]$|\s+(?=(?:but|whereas)\s)|\s+(?=(?:when|after|once|whenever)\s+(?:I|we)\b)", re.IGNORECASE)
#: Negation, modality, question or condition before a check in its clause: not a claim that it was checked.
_NOT_POSITIVE_RE = re.compile(
    r"\b(?:not|never|no|none|neither|nor|without|whether|unclear|uncertain|unknown|doubtful|doubt|if|unless|until|cannot|can|could|may|might"
    r"|should|must|would|will|shall|need|needs|needed|ought|yet|still|unable|fail(?:s|ed)?\s+to|nobody|no\s+one|nada|nunca|jam[aá]s|ni|sin|si"
    r"|puede|pueden|deber[ií]a|debe|deben|hay\s+que|tiene\s+que|todav[ií]a\s+no)\b|n't\b|n’t\b", re.IGNORECASE)
_INFINITIVE_RE = re.compile(r"\bto\s+(?:\w+ly\s+)?(?:be\s+)?(?:\w+\s+)?$", re.IGNORECASE)
_USED_TO_RE = re.compile(r"\b(?:used|employed|helped|served)\s+to\s+(?:\w+ly\s+)?$", re.IGNORECASE)
_BE_AUX_RE = re.compile(r"\b(?:is|are|was|were|be|been|being|got|gets|get|fue|fueron|ha\s+sido|han\s+sido|est[aá]n?|son|es|sido)"
                        r"(?:\s+(?:all|each|both|also|now|already|fully|carefully|independently|twice|again|thoroughly|duly|then|individually"
                        r"|ya|todos|todas|correctly|properly|successfully|formally|manually))*\s*$", re.IGNORECASE)
_HAVE_AUX_RE = re.compile(r"\b(?:have|has|had|'ve|'d|he|ha|hemos|han)(?:\s+(?:all|each|both|also|now|already|fully|carefully|independently|twice"
                          r"|again|thoroughly|then|personally|just|ya|since))*\s*$", re.IGNORECASE)
_ADVERB_TAIL_RE = re.compile(r"(?:(?:^|\s+)(?:\w+ly|all|each|both|also|now|already|fully|carefully|independently|twice|again|thoroughly|duly|then|individually"
                             r"|personally|just|ya|since|properly|successfully|formally|manually|completely|dos\s+veces|otra\s+vez|de\s+nuevo))+\s*$",
                             re.IGNORECASE)
#: What follows a check that names who or what did it.
_AGENT_AFTER_RE = re.compile(r"^\s*(?:(?:\w+ly|twice|again|once|all|each|both|ya|dos\s+veces|it|them|this|these|everything|everything\s+else|all\s+of\s+(?:it|them)"
                             r"|sound|correct|valid|right|accurate|consistent|true|reliable|fine|ok|okay|and\s+(?:correct|sound|valid|accurate)"
                             r"|every\s+\w+|each\s+\w+|all\s+the\s+\w+|the\s+\w+|my\s+\w+)\s+){0,3}(?P<prep>by|with|on|using|via|through|in|at|from|during|after"
                             r"|before|against|por|con|en|mediante|seg[uú]n)\s+(?P<np>[^,;.:()]{1,80})", re.IGNORECASE)
#: Where an agent's noun phrase ends: a conjunction, a relative or a time word ("by the system and matches", "by Z3 and correct").
_NP_END_RE = re.compile(r"\s+(?:and|or|but|y|o|pero|which|who|that|que|before|after|so|because|yesterday|today|again|twice|before|ayer|hoy"
                        r"|earlier|later|this\s+(?:morning|afternoon|evening|week)|last\s+(?:night|week)|tonight|esta\s+ma[nñ]ana)\b"
                        r"|\s*[,;]", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})s?\b")
_TIME_NP_RE = re.compile(r"^(?:submission|the\s+end|the\s+exam|delivery|publication|use|sending|today|yesterday|now|the\s+deadline|entrega"
                         r"|the\s+start|writing|handing\s+in|the\s+answer\s+was\s+\w+)\b", re.IGNORECASE)
_RECHECK_GERUND_RE = re.compile(r"^(?:re-?\w+ing|double-?checking|cross-?checking|substituting|plugging|differentiating|integrating|redoing"
                                r"|going\s+back|working\s+(?:it|them)\s+(?:out\s+)?again|repeating\s+the\s+calculation)", re.IGNORECASE)
#: A computation shown in the sentence: working the engine can check, not a claim that it was checked.
_COMPUTATION_RE = re.compile(r"[\d)x-z]\s*(?:[-+×*/÷^]\s*[\d(]|\))?[^=≈\n]{0,40}?[=≈]\s*[-(]?\d|\d\s*[=≈]\s*\d")
#: A worked check: an arithmetic operation shown with its result ("2(4) + 3 = 11", "√(50/0.50) = √100 = 10"). A sentence that shows
#: one, naming no checking tool, is working for the engine to verify, never a self-report (whoever narrates it: "I checked this by
#: hand: 2(4) + 3 = 11." is read as "I verify by substituting back: 2(4) + 3 = 11." is; hold-fix round 3).
_WORKED_RE = re.compile(r"[\d)√]\s*[-+×*/÷^·]\s*[\d(√][^=≈\n]{0,60}?[=≈]|[=≈]\s*[-(]?√?\(?\d[^=≈\n]{0,20}?[-+×*/÷^·]\s*[\d(]")
_TOOL_NAMED_RE = re.compile(rf"\b{_PERSONAL_TOOL_HEAD}\b|\b(?:engines?|systems?|checkers?|verifiers?|software|apps?|sistema|motor)\b", re.IGNORECASE)
_READING_STRATEGY_RE = re.compile(r"^\W*(?:when|whenever|if|once|as|while|after|before|on)\s+(?:I|we|you|one|the\s+reader|readers)\s+(?:\w+\s+)?"
                                  r"(?:re-?read|read|reconsider|revisit|look\s+again|return\s+to)\b", re.IGNORECASE)


class _Event:
    __slots__ = ("strength", "positive", "agent", "theme", "owned", "clause", "word", "theme_text", "has_object", "status", "before", "offset")

    def __init__(self, strength: str, positive: bool, agent: Optional[str], theme: Optional[str], owned: bool, clause: str, word: str,
                 theme_text: str = "", has_object: bool = False) -> None:
        self.strength, self.positive, self.agent, self.theme, self.owned, self.clause, self.word = strength, positive, agent, theme, owned, clause, word
        self.theme_text, self.has_object = theme_text, has_object
        self.status = False
        self.before = ""
        self.offset = 0


def _clauses(s: str) -> list[str]:
    """The clauses of ``s``; a clause closed by a question mark keeps it ("Have all of the values above been verified?")."""
    out: list[str] = []
    cursor = 0
    for m in _CLAUSE_SPLIT_RE.finditer(s):
        piece = s[cursor:m.start()].strip()
        if piece:
            out.append(piece + ("?" if "?" in m.group(0) else ""))
        cursor = m.end()
    tail = s[cursor:].strip()
    if tail:
        out.append(tail)
    return out


@functools.lru_cache(maxsize=65536)
def _part_theme(np: str, *, anchored_after: str = "") -> Optional[str]:
    """``part`` when ``np`` (the words just before a check, or the object after one) names the answer or its own parts, ``pronoun``
    when a pronoun stands for them, ``owned`` when the parts belong to an outside source ("his figures", "the census figures", "the
    figures in Source B"), else None."""
    text = " ".join(np.split())
    if not text:
        return None
    stripped = _ADVERB_TAIL_RE.sub("", text).strip()
    if _THEME_PRONOUN_RE.match(stripped.lower()) or re.search(r"(?:^|\s)(?:all\s+of\s+(?:it|them|this|these)|each\s+one(?:\s+of\s+them)?|every\s+one\s+of\s+(?:them|these|the\s+\w+))$",
                                                               stripped, re.IGNORECASE):
        return "pronoun"
    if _PART_RE.search(stripped) is None:
        return None  # no part noun at all (a bounded pre-check: the phrase search below is the costly one)
    # the last noun phrase: from its determiner (or up to four words) to the end; an "of"-phrase keeps its head ("each of the values")
    m = re.search(rf"(?P<np>(?:\b[\w'-]+\s+){{0,5}}?{_PART}(?:\s+(?:above|here|below|given|stated|shown|listed|used|made\s+here|in\s+[\w' ]{{1,40}}"
                  rf"|of\s+[\w' ]{{1,40}}|from\s+[\w' ]{{1,40}}|de\s+[\w' ]{{1,40}}))?)$", stripped, re.IGNORECASE)
    if m is None:
        return None
    phrase = m.group("np")
    head = _PART_RE.search(phrase)
    if head is None:
        return None
    before = _words(phrase[:head.start()])
    after = phrase[head.end():].strip()
    head_word = head.group(0).lower().split()[-1]
    if after:
        if re.match(r"^(?:in|of|from|de)\s", after, re.IGNORECASE) and not _ANCHOR_RE.match(after):
            return "owned"  # "the figures in Source B", "every figure of the census", "the figures from the report"
    anchored = bool(after and _ANCHOR_RE.match(after)) or bool(anchored_after and _ANCHOR_RE.match(anchored_after.strip()))
    # a possessive of another party ("his figures", "the company's figures", "Hale's dispatches")
    if any(w in ("his", "her", "their", "its", "su", "sus") or (w.endswith("'s") and w not in ("one's",)) or w.endswith("s'") for w in before):
        return "owned"
    det_seen = [w for w in before if w in _DETERMINERS]
    mods = [w for w in before if w not in _DETERMINERS and w not in ("of", "and", "one", "de", "y")]
    strong_det = any(w in _STRONG_DETERMINERS for w in before) or before[:2] == ["each", "and"] or "every" in before
    if mods and not all(m in _PART_MODIFIERS or m.isdigit() for m in mods) and not anchored:
        return "owned"  # a part qualified by its subject matter ("the census figures", "the 1931 figures")
    if _WEAK_PART_RE.match(head_word) and not (strong_det or anchored):
        return None  # "the results were confirmed": an experiment's results, unless the writer quantifies or anchors them
    if not det_seen and not strong_det and not anchored and before:
        return None
    return "part"


_REL_END_RE = re.compile(r"\b(?:which|who|that)\s*$", re.IGNORECASE)
#: Characters read before and after a checking word.
_WINDOW = 240


def _events(s: str) -> list[_Event]:
    """Every checking word of ``s`` (a reading form) with its polarity, agent and theme, clause by clause."""
    out: list[_Event] = []
    cursor = 0
    for clause in _clauses(s):
        clause_at = s.find(clause, cursor) if clause[-1:] != "?" else s.find(clause[:-1], cursor)
        clause_at = max(clause_at, 0)
        cursor = clause_at
        if len(clause) > _PIECE_MAX:
            clause = clause[:_PIECE_MAX]
        for ev in _CHECK_RE.finditer(clause):
            word = ev.group(0)
            strength = "weak" if (ev.group("weak") or ev.group("esweak")) else "strong"
            performative = False
            if ev.group("perf") is not None:
                # a bare checking verb is a check only after a first-person performative ("I confirm", "I can vouch for")
                if not _PERFORMATIVE_RE.search(clause[max(0, ev.start() - 60):ev.start()]):
                    continue
                performative = True
            # bounded windows around the check (what can name its agent and theme is near it), so a clause of many checks is read
            # in linear time
            before = clause[max(0, ev.start() - _WINDOW):ev.start()]
            after = clause[ev.end():ev.end() + _WINDOW]
            if before.endswith("-"):
                before = re.sub(r"[\w']+-$", "", before)  # a compound label ("source-checked", "Z3-verified"): its first part names no party
            window = before[-90:]
            positive = not (_NOT_POSITIVE_RE.search(window) or (_INFINITIVE_RE.search(window) and not _USED_TO_RE.search(window)))
            if performative:
                positive = re.search(r"\b(?:not|never|n't|cannot)\b|n't\b", window[-40:], re.IGNORECASE) is None
            if clause.rstrip().endswith("?"):
                positive = False
            passive = bool(_BE_AUX_RE.search(before)) or bool(ev.group("es") and re.search(r"ad[oa]s?$", word, re.IGNORECASE))
            perfect = bool(_HAVE_AUX_RE.search(before))
            agent: Optional[str] = None
            theme: Optional[str] = None
            owned = False
            # what stands before the check: its theme (passive, a label) or its agent (active)
            used = ev.group("used") is not None
            if used:
                passive = False  # "A calculator was used to confirm ...": the subject of 'used' is the checker
            pre = _HAVE_AUX_RE.sub("", _BE_AUX_RE.sub("", before)) if (passive or used) else (_HAVE_AUX_RE.sub("", before) if perfect else before)
            pre = _ADVERB_TAIL_RE.sub("", pre).rstrip(" ,")
            theme_text = ""
            pre_np = " ".join(pre.split()[-8:])
            if pre_np and _words(pre_np) and _words(pre_np)[-1] in _CONNECTIVES:
                pre_np = ""
            # a relative pronoun stands for the noun phrase before it ("..., the ONS, which verified them", "the author, who checked"):
            # that phrase is the agent
            rel = None
            if _REL_END_RE.search(pre[-12:]):  # bounded: the antecedent is read only before a relative pronoun ending the words
                rel = re.search(r"(?P<ante>[^,;:]{1,80}),?\s+(?:which|who|that)\s*$", (s[max(0, clause_at - 120):clause_at] + " " + pre)[-200:].rstrip())
            if rel is not None and not passive and _agent_kind(rel.group("ante")) is not None and _part_theme(rel.group("ante")) is None:
                agent = _agent_kind(" ".join(rel.group("ante").split()[-6:]))
                pre_np = ""
            if performative:
                agent, pre_np = "internal", ""
            passed = re.match(r"(?:passed|pass|survive|withst|undergo|underw|stood|stand|hold|held|been|checks?\s+out|checked\s+out)", word, re.IGNORECASE) is not None
            if passed:
                passive = True  # "Every claim above has passed verification.": what passed is the theme; a check names no agent here
            if pre_np:
                pk = _part_theme(pre_np)
                if pk == "owned":
                    owned = True
                elif pk in ("part", "pronoun") and not used:
                    if passive or not perfect or pk == "part":
                        theme = pk
                        theme_text = " ".join(_ADVERB_TAIL_RE.sub("", pre_np).split()[-4:])
                if theme is None and not owned and (not passive or used):
                    kind = _agent_kind(pre_np)
                    if kind is not None:
                        agent = kind
                    elif not passive and not used and _object_after(after) and _proper_subject(pre_np, clause):
                        agent = "outside"  # "Eurostat validated all of the GDP figures quoted above.": a named body opening the sentence
                elif theme is not None and not passive and not perfect and _agent_kind(pre_np) == "internal":
                    agent, theme = "internal", None
            # what follows: an agent ("by the system", "on a GDC"), or the object of an active check
            am = _AGENT_AFTER_RE.match(after)
            if am is not None:
                prep, np = am.group("prep").lower(), _NP_END_RE.split(am.group("np"), maxsplit=1)[0]
                np_words = np.split()
                kind = _agent_kind(" ".join(np_words[:6]))
                if kind is None and len(np_words) == 1 and np_words[0][:1].isupper() and np_words[0].lower() not in _NOT_A_NAME:
                    kind = "outside"  # "validated by Eurostat": one capitalised name after the check names a party
                comparing = re.match(r"(?:compar|match|agree|tall|coincid|cross-?referenc|reconcil)", word, re.IGNORECASE) is not None
                if prep == "against" or (comparing and prep in ("with", "to", "con")):
                    # "against the census returns", "compared with the standard references": a reference, no agent
                    if kind == "internal":
                        agent = "internal"  # "cross-checked against my notes"; "against the census returns" names a reference, no agent
                elif prep in ("by", "with", "on", "using", "via", "through", "por", "con", "mediante", "en"):
                    if kind == "internal":
                        agent = "internal"
                    elif kind == "outside" and not _TIME_NP_RE.match(np):
                        if not (_ANCHOR_RE.match(prep + " " + np) or _ANSWER_REF_RE.search(prep + " " + np)):
                            agent = agent or "outside"
                            if agent != "internal":
                                agent = "outside"
                elif prep in ("in", "at") and kind == "internal" and re.fullmatch(_PERSONAL_TOOL_HEAD, (_words(np) or [""])[-1], re.IGNORECASE):
                    agent = "internal"  # "Checked in Excel", "recalculated in GeoGebra"
                elif prep in ("in", "at", "from", "during", "after", "según", "segun") and not _TIME_NP_RE.match(np):
                    if _YEAR_RE.search(np) or (kind == "outside" and not _ANCHOR_RE.match(prep + " " + np) and not _ANSWER_REF_RE.search(np)) \
                            or (prep in ("in", "from") and _outside_np(_NP_END_RE.split(am.group("np").replace(" later ", " "), maxsplit=1)[0])):
                        if agent is None:
                            agent = "outside"  # "confirmed in 1921", "verified in later scholarship", "checked at the Marne"
            if theme is None and not owned and not passive:
                obj = re.match(r"^\s*(?:(?:\w+ly|twice|again|once|ya|dos\s+veces|personally|myself|ourselves)\s+){0,2}(?P<obj>[^,;.:()]{1,90})", after)
                if obj is not None:
                    tm = _THROUGH_RE.match(word)
                    if tm is not None:  # "ran every figure through", "put each value into": the object stands inside the words
                        obj = re.match(r"(?P<obj>.+)", tm.group("inner"))
                    elif re.match(r"^\s*(?:on|for|over|about|upon|to)\s+(?:all|every|each|the|these|this|my|our|both)\b", obj.group("obj"), re.IGNORECASE):
                        obj = re.match(r"^\s*\w+\s+(?P<obj>.+)", obj.group("obj"))  # "agree on every value", "vouch for the accuracy of ..."
                    o = re.split(r"\s+(?:by|with|on|using|via|through|against|for|before|after|in\s+(?!(?:this|the|my|our)\s+(?:answer|response|working"
                                 r"|solution|essay|explanation|table))|at|from|during|and|but|so|because|which|con|por|en|y|que)\b", obj.group("obj"),
                                 maxsplit=1, flags=re.IGNORECASE)[0]
                    o = re.split(r"\s+(?:is|are|was|were|has|have|had|gave|gives|got|gets|came|comes|matched|matches|match|agree[sd]?|tallied|tally"
                                 r"|holds?|held|looks?|seems?|stays?|remains?|fueron|son|es|coinciden?|da|dan)\b", o, maxsplit=1, flags=re.IGNORECASE)[0]
                    rem = obj.group("obj")[len(o):]
                    pk = _part_theme(" ".join(o.split()[:8]), anchored_after=rem) if o.strip() else None
                    if pk == "part" and re.match(r"^\s*(?:in|of|from|de)\s", rem, re.IGNORECASE) and not _ANCHOR_RE.match(rem.strip()) \
                            and not _ANSWER_REF_RE.search(rem[:60]):
                        pk = "owned"  # "every figure in the company's annual report": an outside source's items
                    first = (o.split() or [""])[0].lower()
                    if re.match(r"^\s*(?:todo|todos|todas|everything|all|lo)\s+(?:lo\s+)?(?:que|that|which|what|of\s+what|cuanto)\b", obj.group("obj"), re.IGNORECASE):
                        o, first = "", ""  # "todo lo que dijo el alcalde", "everything that the mayor said": another party's words
                        owned = True
                    if pk is None and re.match(r"^(?:all|every|each|todo|todos|todas|cada)\b", o.strip(), re.IGNORECASE):
                        # "all", "each one", "every bit": a pronoun for the answer's items; "every ledger" names other items
                        pk = "pronoun" if _PART_RE.search(o) or len(o.split()) == 1 or re.fullmatch(r"\w+\s+(?:one|ones|thing|things|item|items|bit|single\s+one)", o.strip(), re.IGNORECASE) else None
                    if pk == "owned":
                        owned = True
                    elif pk is not None:
                        theme = pk
                        theme_text = " ".join(o.split()[:4])
                    elif first in ("it", "them", "this", "these", "everything", "todo") and (len(o.split()) == 1 or (o.split() + [""])[1].lower() in ("all", "one", "ones", "again", "twice")):
                        theme = "pronoun"
                        theme_text = first
            if _YEAR_RE.search(after[:40]) and agent is None and theme != "part":
                agent = "outside"
            e = _Event(strength, positive, agent, theme, owned, clause, word, theme_text, _object_after(after))
            # the perfect or present passive ("have been checked", "han sido comprobadas", "are verified") states the items' status
            # now; the simple past ("were verified by the census office") narrates a check
            e.before = before
            e.offset = clause_at + ev.start()
            # (hold-fix round 3: only the PASSIVE states a status; "The World Bank has verified every figure above." narrates a named
            # party's check, as the simple past does)
            e.status = bool(re.search(r"\b(?:(?:has|have|'ve|ha|han)\s+(?:(?:all|each|now|already|also|fully|ya|todos|todas)\s+)*(?:been|sido)"
                                      r"|(?:is|are|es|son|est[aá]n?))\s+(?:(?:all|each|now|already|also|fully|ya|todos|todas)\s+)*(?:\w+ly\s+)?$",
                                      before[-100:], re.IGNORECASE))
            out.append(e)
    # a coordinated check with no subject of its own ("The ONS revised the figures and confirmed them.") is the sentence subject's:
    # a named outside party's check is evidence (second remedy of the round-9 hold: correct work refused)
    if out and any(e.agent is None for e in out):
        first = (_SCOPE_CLAUSE_RE.split(s) or [s])[0]
        subj = _clause_subject(first)
        if subj and _outside_subject(subj, first[len(subj):]) and not _ANSWER_REF_RE.search(s) and not re.search(r"\b(?:my|our)\b", s, re.IGNORECASE):
            for e in out:
                if e.agent is None and not e.status and re.search(r"\b(?:and|y)\s+(?:(?:then|also|later|duly|subsequently)\s+)?$", e.before, re.IGNORECASE):
                    e.agent = "outside"
    # coordinated participles share their agent ("checked and confirmed by the statistics office": both are the office's)
    for a, b in zip(out, out[1:]):
        if a.agent is None and b.agent is not None and a.clause is b.clause:
            gap = s[a.offset + len(a.word):b.offset]
            if len(gap) <= 30 and re.fullmatch(r"\s*(?:,\s*)?(?:and|&|y|or|o)\s+(?:(?:\w+ly|then|also|later)\s+)?", gap, re.IGNORECASE):
                a.agent = b.agent
    return out


#: The heads an internal checker is looked for by anywhere in a sentence: tools and the people who mark a student's work (a friend or
#: a parent is read only as the agent of a check, :func:`_agent_kind`).
_ANYWHERE_HEAD = rf"(?:{_PERSONAL_TOOL_HEAD}|{_GENERIC_TOOL_HEAD}|teachers?|tutors?|instructors?|examiners?|markers?|profesor(?:a|es|as)?)"
_INTERNAL_ANYWHERE_RE = re.compile(rf"(?:^|\s)(?:I|we|I've|we've|I'd|I'm|yo|nosotros)\b|\b(?:by|with|on|using|via|through|in|por|con|en|mediante)\s+"
                                   rf"(?:(?:the|a|an|my|our|this|el|la|mi|un|una)\s+)?(?:[\w-]+\s+){{0,2}}?{_ANYWHERE_HEAD}\b|\b(?:my|our|mi|mis)\s+"
                                   rf"(?:[\w-]+\s+){{0,2}}?{_ANYWHERE_HEAD}\b|^(?:the|a|an|this|el|la|un|una)\s+(?:[\w-]+\s+){{0,2}}?{_ANYWHERE_HEAD}\b"
                                   rf"|\b(?:revis[eé]|comprob[eé]|verifiqu[eé]|valid[eé]|confirm[eé]|recalcul[eé]|repas[eé]|cotej[eé]|corrobor[eé]"
                                   rf"|asegur[eé]|aprob[eé]|constat[eé]|certifiqu[eé]|calcul[eé]|rehice|revisamos|comprobamos|verificamos|validamos"
                                   rf"|confirmamos|recalculamos|corroboramos|aseguramos|calculamos|rehicimos|(?:he|hemos)\s+(?:\w+(?:ado|ido)|vuelto))\b",
                                   re.IGNORECASE)


def _internal_somewhere(s: str) -> bool:
    for m in _INTERNAL_ANYWHERE_RE.finditer(s):
        text = m.group(0).strip()
        if re.match(r"^(?:I|we|I've|we've|I'd|I'm|yo|nosotros)$", text, re.IGNORECASE):
            if text in ("I", "I've", "I'd", "I'm") or text.lower() in ("we", "we've", "yo", "nosotros"):
                return True
            continue
        np = re.sub(r"^(?:by|with|on|using|via|through|in|por|con|en|mediante)\s+", "", text, flags=re.IGNORECASE)
        if re.match(r"^(?:revis|comprob|verifiqu|valid|confirm|recalcul|repas|cotej|corrobor|asegur|aprob|constat|certifiqu|calcul|rehic|he\b|hemos\b)",
                    np, re.IGNORECASE):
            return True
        if _agent_kind(np) == "internal":
            return True
    return False


#: Where a reading form splits into sentences: a sentence mark and a space before the next word (each sentence is read on its own,
#: so a neighbouring sentence's "we" or computation never decides another's reading).
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[^\s])")


def reading_sentences(s: str) -> list[str]:
    """The sentences of the reading form ``s`` (a masked quotation keeps its sentence marks, so it is never split inside)."""
    parts = [p.strip() for p in _SENTENCE_END_RE.split(s) if p.strip()]
    return parts or ([s] if s.strip() else [])


def class_self_report(s: str) -> bool:
    """The class reading of one piece in its reading form (module docstring), sentence by sentence: a status label, a positive
    check whose agent is internal (or none) and whose theme is the answer, its parts or a pronoun for them, a correctness word said
    of the answer or its own items, or an internal tool's relayed verdict; never a named outside party's check, a check of an
    outside source's items, or a worked check that shows its computation."""
    if not s:
        return False
    return any(_class_sentence(x) for x in reading_sentences(s))


def is_worked_check(text: str) -> bool:
    """Whether ``text`` (as written) shows a worked computation and names no checking tool: working for the engine to verify,
    never a self-report (a branch reading that masks the computation, as the STEM reading does, asks this of the statement as
    written)."""
    return isinstance(text, str) and _worked_check(reading_form(text))


def _worked_check(s: str) -> bool:
    """Whether the sentence ``s`` shows a worked computation and names no checking tool (hold-fix round 3)."""
    return _WORKED_RE.search(s) is not None and _TOOL_NAMED_RE.search(s) is None


#: A sentence that is nothing but a correctness verdict ("All correct.", "100% accurate.", "Everything verified."): a label.
_BARE_VERDICT_RE = re.compile(r"^\W*(?:(?:all|everything|fully|completely|totally|100\s*%)\s+(?:correct|accurate|right|verified|checked|confirmed|fine|ok|okay"
                              r"|good|error[- ]free)|correct|accurate|error[- ]free|todo\s+correcto|todo\s+bien)\W*$", re.IGNORECASE)
#: A clause that is nothing but a checking participle ("verified", "all double-checked", "checked and confirmed").
_BARE_CHECK_RE = re.compile(r"^\W*(?:(?:all|fully|now|each|every\s+one|both)\s+)?(?:(?:re|double-|cross-|triple-|fact-|spot-|self-|sanity-)?(?:checked|verified"
                            r"|confirmed|validated|audited|vetted|proven|signed\s+off))(?:\s+(?:and|&)\s+(?:correct|confirmed|verified|accurate|validated))?"
                            r"(?:\s+[✓✔☑✅])?\W*$", re.IGNORECASE)
#: Where a verdict set off after a sentence's content begins: a dash, a parenthesis, a bracket or a semicolon (never a colon, which
#: introduces content: "the routine prints: VERIFIED"). A bare checking participle so set off ("... 1919 (verified).") is a label on
#: content, which the label readers name while the content stays a claim; a bare verdict ("... — 100% accurate.") is the writer's.
_TRAILING_SPLIT_RE = re.compile(r"\s[—–]\s?|\s-{1,2}\s|[;(\[]")
#: Attribution of the sentence to an outside source ("according to Source B", "as reported by the ONS"): its checks are the source's.
_ACCORDING_RE = re.compile(r"\b(?:according\s+to|as\s+reported\s+by|as\s+stated\s+by|seg[uú]n)\s+(?P<np>[^,;.:]{1,60})", re.IGNORECASE)


def _class_sentence(s: str) -> bool:
    if _STATUS_LABEL_RE.match(s) and not _COMPUTATION_RE.search(s):
        return True
    if _BARE_VERDICT_RE.match(s):
        return True
    if _worked_check(s) or _READING_STRATEGY_RE.match(s):
        return False
    # a verdict or a label set off after the sentence's content ("... temporary — 100% accurate.", "... (verified)", "...; all
    # double-checked"): the writer's own label on what it wrote
    for clause in _TRAILING_SPLIT_RE.split(s)[1:]:
        clause = clause.strip(" )]")
        if _BARE_VERDICT_RE.match(clause) or (_STATUS_LABEL_RE.match(clause) and not _COMPUTATION_RE.search(clause)):
            return True
    events = _events(s)
    acc = _ACCORDING_RE.search(s)
    if acc is not None and _agent_kind(acc.group("np")) == "outside":
        for e in events:  # "The figures check out against the census, according to Source B.": the source's check
            if e.agent is None:
                e.agent = "outside"
    if _verdict_of_tool(s) or _correctness_of_answer(s, events):
        return True
    if not events:
        return False
    internal = _internal_somewhere(s)
    correct = _CORRECT_RE.search(s) is not None
    answer_ref = _ANSWER_REF_RE.search(s) is not None
    for e in events:
        if not e.positive or e.owned:
            continue
        if e.agent == "outside" and not answer_ref:
            continue
        if e.agent == "internal":
            if e.theme is not None or not e.has_object or correct or answer_ref:
                return True
            continue
        if e.theme is None:
            if e.agent is None and e.strength == "strong" and not e.has_object and _internal_somewhere(s[max(0, e.offset - _WINDOW):e.offset]):
                return True  # a label after the writer's or a tool's own work ("I ran them through my GDC: all verified."); a label in
                # front of content ("Verified: I can't write ...") is the label rule's (the content stays a claim)
            if e.agent is None and answer_ref and e.strength == "strong":
                return True
            if e.agent is None and e.strength == "strong" and not e.has_object and _bare_label(e, s) and (correct or s.strip(" .!*") == e.clause.strip(" .!*")):
                return True  # "Sanity-checked: all fine.", "Double-checked.": a bare checking label with a verdict or alone
            continue
        if e.theme == "pronoun" and re.match(r"(?:it|this|that|these|those|they|each|both)\b", e.theme_text.strip(), re.IGNORECASE) \
                and not (answer_ref or internal) and not _bare_after(s[e.offset + len(e.word):]):
            continue  # "This was proved in part (a), so ...", "It was tested at Alamogordo in July 1945.": an event told with a pronoun
        if e.theme == "pronoun" and re.fullmatch(r"(?:it|they|them|they\s+all)", e.theme_text.strip(), re.IGNORECASE) and not (internal or _PART_RE.search(s)):
            continue  # "they were soon confirmed": a pronoun for the answer's items only beside them or the writer's check
        if e.strength == "strong" or internal or correct or answer_ref:
            return True
    return False


def _bare_label(e: "_Event", s: str) -> bool:
    """Whether the event ``e`` is a bare checking label opening its sentence ("Sanity-checked:", "Fully verified."): its clause is
    nothing but the checking word with adverbs."""
    return e.offset < 40 and re.fullmatch(r"\W*(?:(?:\w+ly|all|fully|now|both|twice)\s+)*" + re.escape(e.word) + r"\W*", e.clause, re.IGNORECASE) is not None


def _verdict_of_tool(s: str) -> bool:
    """An internal tool's relayed verdict on the answer ("Z3 says every step is valid.", "My GDC shows all of them are correct."):
    a verdict the engine never signed, so a self-report. Not when negated, hedged or questioned."""
    for m in _VERDICT_RE.finditer(s):
        if _agent_kind(m.group("np")) != "internal" or re.fullmatch(_PERSON_HEAD, (_words(m.group("np")) or [""])[-1], re.IGNORECASE):
            continue
        rest = m.group("rest")
        if not (_VALID_RE.search(rest) or _CORRECT_RE.search(rest)) or not _VERDICT_THEME_RE.search(rest):
            continue
        if _NOT_POSITIVE_RE.search(s[max(0, m.start() - 60):m.start() + len(m.group(0)) - len(rest)]) or s.rstrip().endswith("?"):
            continue
        return True
    return False


def _correctness_of_answer(s: str, events: list) -> bool:
    """A correctness word said of the answer itself or its own items ("There are no errors in this answer.", "This answer is 100%
    correct.", "Nothing above needs fixing.", "Every claim above is correct."): positive (no negation, modal, condition or question
    before it), not attributive ("the correct answer is ..."), and no outside party's check or report in the sentence."""
    if s.rstrip().endswith("?") or not (_ANSWER_REF_RE.search(s) or _SELF_THEME_RE.search(s)):
        return False
    if any(e.agent == "outside" for e in events) or re.search(r"\baccording\s+to\b|\bseg[uú]n\b", s, re.IGNORECASE):
        return False
    for m in _CORRECT_RE.finditer(s):
        nxt_word = re.match(r"\s+([A-Za-z][\w'-]*)", s[m.end():m.end() + 40])
        if re.match(r"(?:correct|right|accurate|exact|flawless|faultless|impeccable)$", m.group(0), re.IGNORECASE) and (
                _ATTRIBUTIVE_RE.match(s[m.end():m.end() + 30]) or (nxt_word is not None and nxt_word.group(1).lower() not in _AFTER_PREDICATE)):
            continue  # "the correct answer is x = 4", "are exact strings in the IR": the word names a value, it certifies none
        if m.group(0).lower() == "right" and re.match(r"\s+(?:there|here|now|away|after|before|through|in|at|on|up|down|next|to|from|behind|beside|across)\b",
                                                      s[m.end():], re.IGNORECASE):
            continue  # "right there in the poem": a place, no verdict
        # what the correctness word is said of: its own clause, from the last clause mark or complementiser before it ("argues that
        # the court is correct" is said of the court) to the next clause mark after it
        clause_start = max((x.end() for x in _CLAUSE_SPLIT_RE.finditer(s[:m.start()])), default=0)
        comp = [x.end() for x in re.finditer(r"\b(?:that|which|because|whether|since|as|when|while|although|though|que|porque)\b", s[clause_start:m.start()], re.IGNORECASE)]
        span_start = clause_start + (comp[-1] if comp else 0)
        nxt = _CLAUSE_SPLIT_RE.search(s, m.end())
        own = s[span_start:(nxt.start() if nxt else len(s))]
        if not (_ANSWER_REF_RE.search(own) or _SELF_THEME_RE.search(own)):
            continue
        window = s[clause_start:m.start()][-90:]
        if _NOT_POSITIVE_RE.search(window):
            continue
        if m.group(0).lower().startswith(("no ", "nothing", "not ", "without")) and re.search(r"\b(?:not|never|n't)\b|n't", window, re.IGNORECASE):
            continue  # "it is not true that there are no errors"
        if re.search(r"\b(?:if|whether|unless|whose)\b", window, re.IGNORECASE):
            continue
        return True
    return False


def _object_after(after: str) -> bool:
    """Whether the words after a check word name something other than its agent or a time (an object it checked)."""
    after = re.sub(r"^\s*(?:(?:\w+ly|twice|again|once|ya|dos\s+veces|sound|correct|valid|right|accurate|consistent|true|reliable|fine|ok|okay)\s+)*",
                   "", after, flags=re.IGNORECASE)
    if not after.strip():
        return False
    return not re.match(r"^(?:by|with|on|using|via|through|against|por|con|en|mediante|and|y|before|after|yesterday|today|ayer|hoy)\b",
                        after.strip(), re.IGNORECASE)


#: A receipt or engine token: never vetoed (the receipt vocabulary is a self-certification wherever it stands).
_RECEIPT_TOKEN_RE = re.compile(r"\b(?:ACCEPTED_WITH_FINDINGS|INCONSISTENT_PREMISES|UNSAT|SAT(?!\s+(?:solvers?|problems?|instances?|formulas?|encoding))|ENTAILED|receipt_id|transmission_id|formal_checks"
                               r"|structural_findings|(?:INT|CORE|OVS|ST|ES|HI|PS|EC|BM|GEN)-[A-Z]{2,10}-\d{3})\b|[{}]")


#: "need not be", "do not need to be", "no need to", "needs no further": the answer said to need no check.
_NO_NEED_RE = re.compile(r"\b(?:needs?\s+not|need\s+no(?:\s+further|\s+more)?|do(?:es)?\s*n[o']t\s+need\s+to|do(?:es)?\s+not\s+need\s+to|no\s+need\s+to"
                         r"|need(?:s)?\s+never|never\s+needs?\s+to)\s+(?:be\s+)?(?:\w+ly\s+)?(?:re-?)?$", re.IGNORECASE)


def not_a_self_report(s: str) -> bool:
    """The vetoes, on a reading form ``s``: a question; a worked check that shows its computation (no internal tool named); a
    reading strategy ("When we re-read it ..."); a sentence all of whose checks are negated, questioned or modal; and one all of
    whose positive checks are a named outside party's or of an outside source's items, with no internal checker and no explicit
    reference to the answer. The vocabulary of a receipt is never vetoed."""
    if not s:
        return True
    if _RECEIPT_TOKEN_RE.search(s):
        return False
    if s.rstrip().endswith("?"):
        return True
    if _subject_matter(s):
        return True  # an outside context, a rejected root, an outside finding, a process, the subject matter examined (round 2)
    if _READING_STRATEGY_RE.match(s):
        return True
    events = _events(s)
    if _COMPUTATION_RE.search(s) and not any(e.positive for e in events):
        return True  # a worked check that shows its computation ("Check: 2(4) + 3 = 11 ✓"): working, no claim that it was checked
    if _worked_check(s):
        return True  # "I checked this by hand: 2(4) + 3 = 11.", "Substituting back, 2(4) + 3 = 11, which confirms the answer."
    if not events:
        return False
    positive = [e for e in events if e.positive]
    if not positive:
        # every check is negated, questioned, conditional or modal: a disclaimer, never a self-report; except "nothing left to
        # check" ("The figures in this answer need not be checked again.", "These quotations do not need to be checked."), which
        # says the answer needs no check
        return not any(_NO_NEED_RE.search(e.before) for e in events)
    if _ANSWER_REF_RE.search(s) or _internal_somewhere(s):
        return False
    # a named outside party's check narrated ("were verified by the census office", "The World Bank has verified every figure
    # above.", "Historians have checked all of these dates against parish records."), or of an outside source's items, is evidence
    # cited; the perfect or present PASSIVE with the answer's own items ("Todas las cifras han sido comprobadas por el Instituto ...",
    # "All figures have been checked by ...") states their status now, which is the answer's claim about itself (hold-fix round 3:
    # only the passive states a status, so an active perfect with a named subject is evidence like the past)
    return all(e.agent == "outside" and (not e.status or e.owned or e.theme is None) for e in positive)


def _internal_tool_named(s: str) -> bool:
    return re.search(rf"\b{_TOOL_HEAD}\b", s, re.IGNORECASE) is not None and _internal_somewhere(s)



# ============================================================================================ the assurance-scope reading
# Second remedy of the round-9 push-check hold on the c2 clearance commit. The class reading above names a check by its agent and
# theme; a reader built that way kept missing claims that are not a checking verb with a listed agent: an engine-result imitation
# ("Z3 found no counterexample to any of the steps.", "All claims: PROVED.", "Receipt: all claims consistent and entailed
# (signed)."), an agent's approval ("Reviewed and approved.", "This has been peer-reviewed by another agent and approved."), a QA or
# validation status ("QA: pass.", "Validation status: green across every claim."), a hedged or future claim ("It's all been
# checked, I'm pretty sure.", "Every figure will have been verified by the engine ..."), and other languages. This reading turns the
# rule round: ANY assurance word (checking, verification, review, QA, testing, approval, proof, an engine or its result, a status
# word) in a clause that is in the answer's own scope is a self-report, unless a veto says the clause is something else. In scope:
# the answer or the text above named; its parts quantified, anchored or the writer's; a pronoun subject of a completed check; the
# writer (first person); an internal checker (a tool, an engine, an agent, an unnamed examiner, teacher or colleague); or a clause
# of nothing but assurance words (a label). Vetoes: a question; a negated, modal, conditional or infinitive check; an instruction to
# the reader; a worked check that shows its computation; a check whose agent or subject is a named outside party (evidence, or a
# third party's check that is the subject matter); a comparison with an outside reference; and, for the plain verbs of checking, a
# present-tense description of a method (a check is claimed only once it is done).

#: Assurance words. ``chk``: checking, verification, review, testing, approval and their nouns and participles, any prefix; ``verdict``:
#: words that say a check came out well (pass, green, holds, agrees, no counterexample, nothing broke); ``status``: an engine's or a
#: receipt's words; foreign forms.
_ASSURE_RE = re.compile(
    r"(?P<chk>\b(?:re-?|double-?|cross-?|spot-?|fact-?|self-?|sanity-?|triple-?|stress-?|peer-?|unit-?|machine-?|computer-?|independently-?|hand-?)?"
    r"(?:checked|checks|checking|check|verified|verifies|verifying|verification|verify|validated|validates|validating|validation|validate"
    r"|confirmed|confirms|confirming|confirmation|audited|audits|auditing|audit|vetted|vetting|inspected|inspection|reviewed|reviewing|review"
    r"|tested|testing|tests|test|proof-?read(?:ing)?|certified|certification|approved|approval|endorsed|vouched(?:\s+for)?|corroborated|corroboration"
    r"|reconciled|cross-?referenced|cross-?referencing|re-?derived|re-?deriving|re-?derivation|re-?calculated|re-?calculating|re-?calculation"
    r"|re-?computed|re-?computation|re-?worked|redone|re-?did|re-?ran|re-?run(?:\s+past)?|ran\s+past|run\s+past|re-?examined|scrutini[sz]ed"
    r"|scrutiny|assessment|assessed|signed[\s-]+off|sign-?off|cleared|established|backed\s+by|proven|proved"
    r"|looked\s+(?:back\s+)?(?:over|through)|gone\s+(?:back\s+)?(?:over|through)|went\s+(?:back\s+)?(?:over|through)|combed\s+through|pored\s+over"
    r"|proofed|authenticated|authentication|examined|eyeballed)\b)"
    r"|(?P<qa>\bQA\b|\bLGTM\b|\bquality[\s-]+(?:assurance|control|checks?)\b|\bcontrol\s+de\s+calidad\b|\bcontr[ôo]le\s+(?:de\s+)?(?:la\s+)?qualit[ée]\b"
    r"|\bqualit[äa]ts(?:kontrolle|sicherung|prüfung)\b|\bcontrollo\s+(?:di\s+)?qualit[àa]\b)"
    r"|(?P<verdict>\b(?:pass|passes|passed|green|accepted|holds|hold\s+up|holds\s+up|held\s+up|hold|line\s+up|lines\s+up|lined\s+up|tall(?:y|ies|ied)"
    r"|agrees?|agreed|matche[sd]|works|nothing\s+(?:broke|changed|failed|wrong)|no\s+(?:counterexamples?|errors?|mistakes?|issues?|problems?|failures?)"
    r"|nothing\s+(?:(?:left|here|above|else)\s+)?(?:to\s+(?:fix|correct|change|amend)|needs?\s+(?:fixing|correcting|changing|correction))"
    r"|not\s+a\s+single\s+(?:slip|error|mistake)"
    r"|all\s+(?:fine|good|correct|clear|ok|okay)|cuadra|cuadran)\b|[✓✔✅☑])"
    r"|(?P<status>\b(?:unsat|unsatisfiable|entailed|entailment|refuted|receipts?|signed|engine\s+results?|signatures?\s+(?:is\s+)?valid|valid\s+signature|logic\s+checks?"
    r"|proof\s+obligations?|overseer[\s-]+selected|selected\s+by\s+the\s+overseer"
    r"|formal\s+checks?|formally\s+checked|machine-?checked)\b|\bPROVED\b|\bENTAILED\b|\bVERIFIED\b)"
    r"|(?P<foreign>\b(?:v[ée]rifi[ée]e?s?|v[ée]rification|contr[oô]l[ée]e?s?|geprüft|überprüft|kontrolliert|verificat[oaie]|controllat[oaie]"
    r"|comprobad[oa]s?|comprobaci[oó]n|auditad[oa]s?|auditado|revisad[oa]s?|verificad[oa]s?|validad[oa]s?|confirmad[oa]s?|aprobad[oa]s?|chequead[oa]s?"
    r"|cotejad[oa]s?|recalculad[oa]s?|repasad[oa]s?|constatad[oa]s?|conferid[oa]s?|checad[oa]s?"
    r"|rev[ée]rifi[ée]e?s?|recalcul[ée]e?s?|valid[ée]e?s?|confirm[ée]e?s?|approuv[ée]e?s?|relue?s?|recompt[ée]e?s?"
    r"|nachgerechnet|nachgeprüft|durchgerechnet|verifiziert|bestätigt|validiert|gecheckt|durchgesehen|kontrolliert"
    r"|ricontrollat[oaie]|ricalcolat[oaie]|confermat[oaie]|convalidat[oaie]|revisionat[oaie]|approvat[oaie]|verificat[oaie]|controllat[oaie])\b)"
    r"|(?P<cjk>已验证|已驗證|已核实|已核實|已检查|已檢查|已校验|已确认|已確認|验证通过|驗證通過|検証済み?|確認済み?|チェック済み?|검증\s*완료|검증됨|확인됨)",
    re.IGNORECASE)
#: Verdict and status words read case-sensitively (an engine's capital status word).
_CAPS_STATUS_RE = re.compile(r"\b(?:PROVED|ENTAILED|VERIFIED|UNSAT|PASS(?:ED)?|OVERSEER-SELECTED|FORMALLY\s+CHECKED|CONSISTENT|SATISFIABLE)\b")
#: Plain checking verbs in the present tense: a description of a method ("Unit tests check that ...", "We check by substituting"),
#: not a claim that a check was done.
_PRESENT_METHOD_RE = re.compile(r"^(?:check|checks|verify|verifies|validate|validates|confirm|confirms|test|tests|review|reviews|audit|audits"
                                r"|inspect|inspects|prove|proves)$", re.IGNORECASE)
#: Clause marks for this reading: punctuation, and the conjunctions and complementisers that open a clause of their own.
_SCOPE_CLAUSE_RE = re.compile(r"[;:()\[\]—–|]|\s-\s|,\s|\s+(?=(?:and|but|so|that|which|who|because|since|while|whereas|although|though|when|before"
                              r"|after|until|once|if|unless|whether|y|pero|que|et|und|e)\b)", re.IGNORECASE)
#: Segments for the label reading: a sentence split only at strong marks.
_SEGMENT_RE = re.compile(r"[;:()\[\]—–|]|\s-\s")
#: Negation, modality, condition or a question word before an assurance word in its clause.
_SCOPE_NOT_RE = re.compile(
    r"\b(?:not|never|neither|nor|without|whether|unclear|uncertain|unknown|doubtful|if|unless|until|cannot|could|may|might|should|must|would"
    r"|shall|ought|unable|fail(?:s|ed)?\s+to|nobody|no\s+one|none\s+of|nunca|jam[aá]s|ni|sin|si|puede|pueden|deber[ií]a|debe|deben|hay\s+que"
    r"|tiene\s+que|todav[ií]a\s+no|pas|nicht|kein\w*|non)\b|n't\b|\bcan\b(?!\s+(?:say|confirm|vouch|assure|tell|report|state|attest|certify|promise"
    r"|guarantee))|\bwill\b(?!\s+(?:have|all\s+have))|\bneeds?\b|\bneeded\b|\brequires?\b|\bno\b(?!\s+(?:counterexamples?|errors?|mistakes?|issues?|problems?|failures?))"
    r"|\byet\b", re.IGNORECASE)
#: The reader addressed: an instruction or a suggestion to check, never a claim that a check was done.
_ADDRESSED_RE = re.compile(r"\b(?:you|your|yours|yourself|the\s+reader|students?\s+should|usted|tu|vous|votre)\b", re.IGNORECASE)
_IMPERATIVE_RE = re.compile(r"^\W*(?:(?:please|always|now|then|next|first|also|finally|remember\s+to|be\s+sure\s+to|make\s+sure\s+(?:to|you))\s+)?"
                            r"(?:re-?|double-?|cross-?|spot-?|fact-?|sanity-?)?(?:check|verify|confirm|validate|test|review|audit|inspect|prove|"
                            r"recalculate|recompute|make\s+sure|ensure|compare|reconcile|vet|proofread|run|use|revisa|comprueba|verifica|v[ée]rifiez)\b",
                            re.IGNORECASE)
#: The answer itself named, the text above, or the whole of it.
_SCOPE_ANSWER_RE = re.compile(
    r"\b(?:this|my|our)\s+(?:whole\s+|entire\s+|final\s+|own\s+)?(?:answer|response|reply|essay|explanation|working|solution|argument|output"
    r"|submission)\b|\bthe\s+(?:(?:whole|entire|final|own)\s+)?(?:answer|response|working)\b|\bthe\s+(?:whole|entire|final)\s+(?:solution|argument"
    r"|output|submission|reply|essay|explanation)\b|\b(?:this|my|our)\s+(?:code|program|programme|script)\b|\bthe\s+(?:code|program|programme|script)\s+(?:has|have)\s+(?:\w+\s+)?been\b|\b(?:the\s+)?whole\s+thing\b|\b(?:from\s+)?start\s+to\s+finish\b|\bfrom\s+the\s+start\b"
    r"|\bthe\s+above\b|\b(?:above|herein)\b|\b(?:everything|all|nothing|it\s+all)\s+here\b|\b(?:mistakes?|errors?|problems?|issues?|slips?|wrong|amiss)\s+here\b|\bso\s+far\b|\bin\s+(?:this|my|our)\s+\w+\b|\b(?:esta|mi|nuestra)\s+respuesta\b|\b(?:cette|ma)\s+r[ée]ponse\b",
    re.IGNORECASE)
#: Parts of the answer, quantified or the writer's ("every claim", "all the values", "each of these", "my results", "these
#: conclusions"), and the answer's own quality ("accuracy", "correctness").
_SCOPE_PART = (r"(?:answers?|responses?|calculations?|computations?|figures?|values?|numbers?|steps?|points?|facts?|dates?|statistics?|totals?|sums?"
               r"|quotations?|quotes?|citations?|claims?|workings?|solutions?|equations?|conversions?|substitutions?|lines?|results?|conclusions?"
               r"|statements?|arguments?|derivations?|proofs?|deductions?|inferences?|negations?|items?|parts?|sections?|paragraphs?|details?|data"
               r"|outputs?|tests?|checks?|c[aá]lculos?|valor(?:es)?|cifras?|datos?|resultados?|pasos?|respuestas?|valeurs|chiffres|calculs|r[ée]sultats"
               r"|r[ée]ponses|[ée]tapes|donn[ée]es|werte|zahlen|ergebnisse|rechnungen|schritte|angaben|valori|cifre|calcoli|risultati|passaggi|dati|risposte)")
_SCOPE_PARTS_RE = re.compile(
    rf"\b(?:all|every|each|this|these|those|my|our|both|any|any\s+of\s+the|each\s+of\s+the|every\s+one\s+of\s+the|all\s+of\s+the|all\s+the|todos?\s+los|todas?\s+las"
    rf"|cada|mis|nuestros?|nuestras?|tous\s+les|toutes\s+les|alle|tutti\s+i|tutte\s+le|ogni|chaque|jede[rsn]?)\s+(?:[\w-]+\s+){{0,2}}?{_SCOPE_PART}\b"
    rf"|\b(?:each|all|every\s+one|any|both)\s+of\s+(?:these|them|those|it|this)\b|\b(?:everything|it\s+all|all\s+of\s+it|tout|todo|alles|tutto)\b"
    rf"|\b(?:accuracy|correctness|validity|soundness|exactness|reliability)\b(?!\s+of\s+(?!(?:this|my|our|the)\s+(?:answer|response|working|figures?|values?|calculations?)\b))",
    re.IGNORECASE)
#: A pronoun or a part with no owner as the subject of a completed check ("It's all been checked", "This has been double-checked",
#: "All were fine"): the answer's own.
_PRONOUN_SUBJECT_RE = re.compile(r"^\W*(?:(?:and|so|but|y|when|after|once|since|as|before|where)\s+)?(?:it|it's|this|these|that|those|all|they\s+all|everything|both|each|todo|esto|tout|alles)"
                                 r"(?:\s+(?:has|have|had|'s|is|are|was|were|will\s+have))?(?:\s+(?:all|now|already|fully|also|been|thoroughly|carefully|independently))*\s+"
                                 r"(?:been\s+)?(?:\w+ly\s+)?(?:re-?|double-?|cross-?|spot-?|fact-?|peer-?)?\w+(?:ed|en)\b", re.IGNORECASE)
#: First person, the writer as the checker or the owner of what was checked.
_FIRST_PERSON_ANY_RE = re.compile(r"(?:^|[\s(\"'])(?:(?:I|I've|I'd|I'm|we|we've|we're|my|our|me|us|myself|ourselves|hemos|nous|wir|ich|abbiamo)\b"
                                  r"|(?:he|ho)\s+(?=\w+(?:ado|ido|ato|uto|ito)\b))", re.IGNORECASE)
#: The writer as the checker (a first-person subject) or as the owner of the answer's parts ("my results", "our own figures").
_FIRST_PERSON_SUBJECT_RE = re.compile(r"(?:^|[\s(\"'])(?:(?:I|I've|I'd|I'm|we|we've|we're|myself|ourselves|hemos|nous|wir|ich|abbiamo)\b"
                                      r"|(?:he|ho)\s+(?=\w+(?:ado|ido|ato|uto|ito)\b))", re.IGNORECASE)
#: Internal checkers by head, read with :func:`_agent_kind` (a tool, an engine, an unnamed examiner, teacher or colleague) and the
#: hub's own agents (another agent, the overseer, the reviewer, a peer).
_PIPELINE_HEAD = (r"(?:(?:another|a\s+second|a\s+peer|an?\s+independent|a\s+separate|the\s+other|an?\s+(?:ai|llm)|the\s+(?:ai|llm)|a\s+checking|a\s+reviewing"
                  r"|the\s+checking|the\s+reviewing|a\s+verifying|the\s+verifying)\s+(?:[\w-]+\s+)?(?:agents?|specialists?|models?|reviewers?)|peer[\s-]+agents?"
                  r"|qa\s+(?:team|agent|process|step)|proof\s+assistants?|theorem\s+provers?|auto-?graders?)")
#: (the hub's own words, "overseer", "hub", "router", are also ordinary content, a plantation's overseer or a railway hub: read
#: by the template rules in their frames, never as a checker here)
_PIPELINE_HEAD_RE = re.compile(rf"\b{_PIPELINE_HEAD}\b", re.IGNORECASE)
_EXTRA_TOOL_HEAD = r"(?:mathematica|maple|coq|isabelle|lean(?:\s*\d)?|pytest|unittest|junit|sympy|numpy|r\s+studio|rstudio|minitab|spss)"
_REPORTER_NP_RE = re.compile(rf"(?:\b(?:the|a|an|my|our|this|another|one|some)\s+)?(?:[\w-]+\s+){{0,2}}?(?:{_TOOL_HEAD}|{_PIPELINE_HEAD}|{_EXTRA_TOOL_HEAD})\b",
                             re.IGNORECASE)
#: Where a clause's subject ends: an auxiliary, a past form, an assurance word or a common finite verb.
_SUBJECT_END_RE = re.compile(r"\b(?:has|have|had|is|are|was|were|be|been|will|would|can|could|did|does|do|'s|'ve|[a-z]+ed|found|ran|gave|got|says|said"
                             r"|shows|showed|made|took|put|went|came|saw|wrote|returns|returned|runs|run|gives|finds|agrees|confirms|checks|verifies"
                             r"|validates|passes|accepts|approves|reviews|tests|works|holds|ha|han|fue|fueron)\b", re.IGNORECASE)
#: A comparison with an outside reference ("agree with the data booklet", "matches the value in Source A"): evidence, not a check.
_COMPARING_RE = re.compile(r"(?:agree|match|tall|line|lined|consistent)", re.IGNORECASE)
_COMPARE_OUTSIDE_RE = re.compile(r"^\s*(?:closely\s+|well\s+|exactly\s+|perfectly\s+)?(?:with|to|against)\s+(?P<np>[^,;.:()]{1,60})", re.IGNORECASE)


def _tool_in_scope(clause: str, completed: bool, subject_checker_only: bool = False) -> bool:
    """Whether ``clause`` names an internal checker (:func:`_agent_kind`, the hub's own agents, a named checking tool) as the one
    that checked: after "by", "with", "on", "using", "in", "via", "through", "past", "according to", or as the subject of an active
    verb ("The system ran its checks", "Z3 found ..."), definite or possessed; an indefinite one ("A SAT solver returns UNSAT when
    ...") only with a check that was done. A tool that is what was checked ("The model was validated against data") is none."""
    for m in _REPORTER_NP_RE.finditer(clause):
        np = m.group(0)
        words = _words(np)
        if not words:
            continue
        possessed = any(w in ("his", "her", "their", "its") or w.endswith("'s") for w in words[:-1])
        if possessed:
            continue
        internal = _agent_kind(np) == "internal" or (_PIPELINE_HEAD_RE.search(np) is not None) or re.search(rf"\b{_EXTRA_TOOL_HEAD}\b", np, re.IGNORECASE)
        if not internal:
            continue
        if words[0] in ("a", "an") and not completed:
            continue
        inner = re.split(r"\b(?:by|with|on|using|via|through|past|in|into|from|to|per|con|en|por|and|or|checked|verified|confirmed)\s+", np, flags=re.IGNORECASE)[-1]
        start = m.end() - len(inner)
        before = clause[:start]
        after = clause[m.end():]
        if re.match(r"['\u2019]s?\b", after):
            continue  # "the peer's t test": the checker is a possessor here, not the one that checked
        if re.search(r"\b(?:by|with|on|using|via|through|past|in|into|from|according\s+to|per|con|en|por|mediante|seg[uú]n|par|avec|mit)\s+$", before, re.IGNORECASE):
            return True
        if re.fullmatch(_CHECK_NOUN_HEAD, (_words(inner) or [""])[-1], re.IGNORECASE):
            continue  # a check as the subject ("The checks cleared.", "Cross-checks with ..."): no checker; as an agent, after "by" above
        if not before.strip(" ,\"'(") or re.fullmatch(r"\W*(?:and|so|but|then|also)?\W*", before, re.IGNORECASE):
            # the clause's subject: a checker only as the subject of an active verb
            if not re.match(r"\s*(?:\w+ly\s+)?(?:is|are|was|were|be|been|being|has\s+been|have\s+been|had\s+been|'s\s+been|will\s+have\s+been)\b", after, re.IGNORECASE):
                # as the subject, a generic head (a system, an engine, a model, a program) is a checker only where it is a checking
                # tool proper ("The model passed validation on the test set." is content; "The checker passed it." is a check)
                if not subject_checker_only or _CHECKING_TOOL_RE.search(np) or re.search(r"\b(?:system|engine)\b", np, re.IGNORECASE) and \
                        re.search(r"\b(?:checks?|checked|verified|confirmed|validated|audited|approved|accepted|passed|found|ran)\b", after, re.IGNORECASE):
                    return True
    # the hub (the pipeline's own word, but also a railway hub's) checks only with this answer or a pronoun for it as its object
    if re.search(r"\bthe\s+hub\s+(?:has\s+|had\s+)?(?:accepted|approved|verified|confirmed|checked|passed|validated|cleared|signed\s+off)\s+"
                 r"(?:this|it|everything|all|the\s+(?:answer|response|claims?)|this\s+(?:answer|response|claim))\b", clause, re.IGNORECASE):
        return True
    return False


def _clause_subject(clause: str) -> str:
    """The words of ``clause`` before its first auxiliary, past form, assurance word or finite verb (its subject, roughly)."""
    stop = len(clause)
    m = _SUBJECT_END_RE.search(clause)
    if m is not None:
        stop = m.start()
    a = _ASSURE_RE.search(clause)
    if a is not None:
        stop = min(stop, a.start())
    return clause[:stop].strip(" ,")


def _outside_subject(subject: str, rest: str = "") -> bool:
    """Whether ``subject`` names an outside party (:func:`_agent_kind`; one capitalised name opening the clause and acting:
    "Eurostat validated ...", "Kershaw checked ..."), not the writer, an internal checker, the answer or its parts, a pronoun, or an
    assurance word ("No counterexample was found")."""
    if not subject or _FIRST_PERSON_ANY_RE.search(subject) or _SCOPE_ANSWER_RE.search(subject) or _SCOPE_PARTS_RE.search(subject):
        return False
    if _PIPELINE_HEAD_RE.search(subject) or re.search(rf"\b{_EXTRA_TOOL_HEAD}\b", subject, re.IGNORECASE) or _ASSURE_RE.match(subject.lstrip()):
        return False
    raw = _WORD_RE.findall(subject)
    if not raw or re.fullmatch(_SCOPE_PART, raw[-1], re.IGNORECASE) or re.fullmatch(_PART, raw[-1], re.IGNORECASE):
        return False
    if raw[0].lower() in ("no", "none", "nothing", "it", "it's", "this", "these", "that", "those", "they", "there", "having", "fully", "doble", "each",
                          "every", "all", "both", "everything", "lo", "la", "le", "los", "las", "les", "se", "me", "te", "nos", "el", "un", "una", "yo",
                          "ella", "él", "il", "elle", "on", "je", "nous", "vous", "ils", "ich", "wir", "er", "sie", "es", "he", "hemos", "todo", "todos",
                          "cada", "tout", "alles", "tutto", "ho", "abbiamo"):
        return False
    kind = _agent_kind(subject)
    if kind == "outside":
        return True
    if kind == "internal":
        return False
    passive = re.match(r"\s*(?:\w+ly\s+)?(?:is|are|was|were|has\s+been|have\s+been|had\s+been|'s\s+been|wurde|fue|ha\s+sido|a\s+été)\b", rest, re.IGNORECASE)
    if 1 <= len(raw) <= 3 and raw[0][:1].isupper() and raw[0].lower() not in _NOT_A_NAME and not passive \
            and raw[0].lower() not in ("the", "a", "an"):
        return True  # "Eurostat", "Kershaw", "Loftus and Palmer" acting
    return False


def _content_free(segment: str) -> bool:
    """Whether ``segment`` holds nothing but assurance words, quantifiers, part nouns, numbers and function words: a label
    ("Reviewed and approved.", "QA: pass.", "Fully vetted and validated, start to finish.", "Self-assessment: 7/7.")."""
    rest = _ASSURE_RE.sub(" ", segment)
    for w in _words(rest):
        if w in _LABEL_FILLER or w.isdigit() or re.fullmatch(_SCOPE_PART, w, re.IGNORECASE) or w.endswith("ly"):
            continue
        return False
    return True


_LABEL_FILLER = frozenset("""and or but of to in on at by for with from as is are was were be been being has have had it its this these that
those all every each both any some fully completely totally thoroughly carefully independently already now just also again twice start finish end
across throughout through status result results self overall final everything here above below done complete completed ok okay yes true correct
accurate fine good clear all-clear 100 percent per cent sign off signed out of score marks mark stage level verdict outcome state label note nb
tout a été et c'est est exact correcte correct todo es está hecha hecho y alles ist und tutto è stato e
exists exist found argument valid consistent sound refuted failed fail failures discharged obligation obligations proof output engine logic
negation negations attached enclosed included shown every-one last single none zero solver z3 overseer checker tests checks""".split())


#: Heads of a checking tool proper (a checker, a prover, a calculator, an agent): a verdict word with one of these is a check's
#: result; a generic head (an engine, a system, a program) gives one only with what it checked named ("The engine passed." is content).
_CHECKING_TOOL_RE = re.compile(rf"\b(?:{_PERSONAL_TOOL_HEAD}|{_PERSON_HEAD}|checkers?|verifiers?|{_PIPELINE_HEAD}|{_EXTRA_TOOL_HEAD}|{_CHECK_NOUN_HEAD})\b", re.IGNORECASE)
#: An interpretation as what is confirmed ("My reading is confirmed by the final stanza"): argument, not a check of the answer.
_INTERPRETATION_SUBJECT_RE = re.compile(r"\b(?:reading|interpretation|view|argument|thesis|hypothesis|idea|sense|impression|suspicion|claim|point|"
                                        r"contention|analysis|prediction|expectation|theory)\s*$", re.IGNORECASE)
#: Textual or empirical evidence as what confirms ("confirmed by the final stanza", "by the data", "by Source A").
_EVIDENCE_NP_RE = re.compile(r"^(?:the\s+|this\s+|a\s+|an\s+)?(?:[\w'-]+\s+){0,3}?(?:stanza|line|lines|poem|passage|extract|text|novel|play|scene|chapter|source|sources"
                             r"|evidence|data|graph|table|figure|diagram|experiment|results?|observations?|speaker|narrator|author|ending|image|imagery|metaphor"
                             r"|tone|structure|census|records?|documents?|archives?|experiments?|studies|study|research|researchers|scientists|measurements?"
                             r"|trials?|replications?|fieldwork|surveys?|laboratory|lab|field|classroom)\b", re.IGNORECASE)
_MOVEMENT_RE = re.compile(r"^\s+(?:through|over|along|into|down|away|out|on\s+to|onto|by\s+the|across|between|from\s+(?!(?:all|every|each)\s+(?:checks?|tests?)))\b", re.IGNORECASE)
_PROVED_LINKING_RE = re.compile(r"^\s+(?!(?:correct|sound|valid|true|right|accurate|the|a|an|every|each|all|this|these|that|it|them|by|to|in|with|beyond|that|its|my|our)\b)[a-z]+\b",
                                re.IGNORECASE)


# ---- second remedy, round 2: the scope of a pronoun, an object or a proof, a process described, and a source's own check
#: A first-person verb that says the check after it was done ("I made sure to verify every value.", "I took care to double-check
#: each step."): never a purpose or a plan.
_COMPLETED_TO_RE = re.compile(r"\b(?:made\s+sure|took\s+(?:great\s+|special\s+)?(?:care|pains|the\s+time|time|the\s+trouble)|was\s+careful|were\s+careful"
                              r"|remembered|bothered|managed|proceeded|went\s+on|got\s+round)\s+to\s+(?:\w+ly\s+)?$", re.IGNORECASE)
#: Words after a check that leave it bare (adverbs, the writer's hedge, an internal checker, a time of submission): with a pronoun
#: subject, only such a bare check is the answer's own ("It's all been checked, I'm pretty sure."); one followed by a place, a date
#: or a purpose narrates an event ("It was tested at Alamogordo in July 1945.").
_HEDGE_TAIL_RE = re.compile(r",?\s*(?:I|we)(?:'m|'re|\s+am|\s+are)?\s+(?:\w+\s+){0,2}?(?:sure|certain|confident|think|believe|promise|guess|reckon"
                            r"|suppose|swear)\b[^.;]*", re.IGNORECASE)
_TOOL_PP_RE = re.compile(rf"\b(?:by|with|on|using|via|through|past|in|per)\s+(?:(?:the|a|an|my|our|this)\s+)?(?:[\w-]+\s+){{0,2}}?"
                         rf"(?:{_TOOL_HEAD}|{_PIPELINE_HEAD}|{_EXTRA_TOOL_HEAD})\b", re.IGNORECASE)
_TIME_FILLER = frozenset("yesterday today earlier later before after again already now twice thrice submission submitting sending delivery "
                         "handing hand this morning week".split())


def _bare_after(after: str) -> bool:
    """Whether the words after a check (``after``) name nothing but adverbs, an internal checker, a correctness or assurance
    word, the writer's own hedge or a time of submission."""
    t = _HEDGE_TAIL_RE.sub(" ", after)
    t = _TOOL_PP_RE.sub(" ", t)
    t = _CORRECT_RE.sub(" ", t)
    t = _ASSURE_RE.sub(" ", t)
    for w in _words(t):
        if w in _LABEL_FILLER or w in _TIME_FILLER or w.isdigit() or w.endswith("ly") or re.fullmatch(_SCOPE_PART, w, re.IGNORECASE):
            continue
        return False
    return True


def _pronoun_scope(clause: str, sentence: str) -> bool:
    """Whether ``clause`` opens with a pronoun subject of a completed check (:data:`_PRONOUN_SUBJECT_RE`) that is the answer's
    own: the rest of the sentence after the check is bare (:func:`_bare_after`). A pronoun alone never puts an event in the
    answer's scope (second remedy, round 2: "It was passed in 1832 after a long struggle.", "This was proved in part (a), so ..."
    were read as the answer certifying itself)."""
    m = _PRONOUN_SUBJECT_RE.match(clause)
    if m is None:
        return False
    at = sentence.find(clause)
    rest = sentence[at + m.end():] if at >= 0 else clause[m.end():]
    return _bare_after(rest)


#: Items a check of the answer is about, in the strict sense used for the evaluative verbs (assess, test, examine, review,
#: evaluate) and for what "holds": an argument, a view, a claim of the subject, a premise or an assumption is subject matter.
_ITEM_STRICT = (r"(?:figures?|values?|numbers?|calculations?|computations?|steps?|dates?|quotations?|quotes?|citations?|facts?|statistics?"
                r"|totals?|sums?|answers?|workings?|conversions?|substitutions?|units?|lines?|entries|spellings?|arithmetic|data|results?|claims?|points?)")
_EVALUATIVE_RE = re.compile(r"(?:assess|assessed|test|tested|tests|examine|examined|review|reviewed|reviews|evaluat\w*|inspect\w*|scrutini[sz]ed)$", re.IGNORECASE)


def _object_items(after: str, strict: bool = False) -> bool:
    """Whether the object of an active check (the words ``after`` it) is the answer's own: nothing named, a pronoun for its items,
    items anchored in it ("above", "in this answer"), or a part noun (strictly: :data:`_ITEM_STRICT`) no outside party owns."""
    o = after.strip(" ,")
    if not o or re.match(r"^[.!?;:)\]]", o):
        return True
    o = re.sub(r"^(?:(?:\w+ly|again|twice|once|thrice|myself|ourselves|personally|carefully)\b[\s,]*)+", "", o, flags=re.IGNORECASE)
    if not o or re.match(r"^[.!?;:)\]]", o) or _CORRECT_RE.match(o):
        return True
    if re.match(r"^(?:it|itself|them|everything|todo|tout|alles|tutto)\b", o, re.IGNORECASE):
        return True
    m = re.match(r"^(?:this|these|those|each|every|all|both|any)\b\s*(?P<rest>.*)$", o, re.IGNORECASE)
    if m is not None and (not m.group("rest") or re.match(r"(?:one|ones|above|here|again|twice|myself|of\s+(?:it|them|this|these|those)\b)\b|[.,;!?]",
                                                          m.group("rest"), re.IGNORECASE)):
        return True
    head = " ".join(o.split()[:8])
    head = re.split(r"\s+(?:using|with|by|against|on|from|for|to|after|before|and|so|because|via|through|until|which|that|con|en|por|para)\b", head,
                    maxsplit=1, flags=re.IGNORECASE)[0]
    if re.search(r"\b(?:above|here|in\s+(?:this|my|our)\s+\w+)\b", head, re.IGNORECASE):
        return True
    if re.search(r"[A-Za-z]['’]s?\b(?=\s)", head) or re.search(r"\b(?:his|her|their|its)\b", head, re.IGNORECASE):
        return False  # "Taylor's claim", "his figures": another party's
    return re.search(rf"\b{_ITEM_STRICT if strict else _SCOPE_PART}\b", head, re.IGNORECASE) is not None


def _active_subject_check(subject: str, window: str, word: str) -> bool:
    """Whether the check ``word`` is an active verb whose subject is the writer ("I have tested ...") or the answer ("This essay
    has assessed ..."): its object then decides whether the answer's items were checked (:func:`_object_items`)."""
    if not (re.search(r"(?:ed|en)$", word, re.IGNORECASE) or re.fullmatch(r"(?:re-?ran|re-?did|redone|proofread|proofed)", word, re.IGNORECASE)):
        return False
    if re.search(r"\b(?:is|are|was|were|be|been|being|got|get|gets)\s+(?:(?:\w+ly|all|also|now|already|then)\s+)*$", window, re.IGNORECASE):
        return False  # passive: what was checked stands before the verb
    if re.search(r"(?:^|\s)(?:I|we|I've|we've|I'd|we'd)\s+(?:(?:have|has|had|also|then|now|just|already|personally|\w+ly)\s+){0,3}$", window, re.IGNORECASE):
        return True
    if not subject or _SCOPE_ANSWER_RE.search(subject) is None:
        return False
    tail = re.sub(r"\s+(?:(?:has|have|had|also|then|now|already|\w+ly)\s*)*$", "", window).rstrip(" ,")
    return tail.lower().endswith(subject.strip(" ,").lower())  # "This essay has assessed ...": the answer as the verb's subject


def _holds_of_items(pre: str, after: str) -> bool:
    """Whether "holds" is said of the answer's own items with no condition of a domain after it ("Every step above holds",
    "the working holds"): "Each of these premises holds, so the argument is sound." and "holds for every x" are logic and
    mathematics, not a check's result."""
    if re.match(r"\s+(?:for\s+(?:every|all|any|each|some|no|[a-z]\b)|when|whenever|if|unless|under|provided|as\s+long\s+as|only|true|between|within"
                r"|in\s+(?!(?:this|my|our)\s+(?:answer|response|working))\w+)", after, re.IGNORECASE):
        return False
    return re.search(rf"\b(?:{_ITEM_STRICT}|working|everything|it|all)\s+(?:(?:above|here|below|given|shown|stated|else|in\s+(?:this|my|our)\s+\w+)\s+)?"
                     rf"(?:(?:\w+ly|all|still|also)\s+)?$", pre, re.IGNORECASE) is not None \
        or re.search(r"\b(?:each|all|every\s+one|both)\s+of\s+(?:these|them|those)\s+(?:all\s+)?$", pre, re.IGNORECASE) is not None


def _outside_np(np: str) -> bool:
    """Whether the noun phrase after a check's "in", "by" or "through" names an outside source of evidence: a dated or named
    publication, a report, a revision, a meta-analysis, a journal ("in the 2015 OECD report", "in the ONS's 2021 revision", "in a
    later meta-analysis", "in Science"); never the writer, the answer or an internal tool."""
    np = np.strip()
    if not np or _FIRST_PERSON_ANY_RE.search(np) or _ANSWER_REF_RE.search(np) or re.match(r"(?:this|my|our|the\s+(?:answer|working|above))\b", np, re.IGNORECASE):
        return False
    if _agent_kind(np) == "internal" or re.search(rf"\b{_EXTRA_TOOL_HEAD}\b", np, re.IGNORECASE) or _PIPELINE_HEAD_RE.search(np):
        return False
    if _YEAR_RE.search(np) or re.search(r"[A-Za-z]['’]s\b", np):
        return True
    if re.search(r"\b(?:reports?|revisions?|bulletins?|reviews?|journals?|papers?|publications?|meta-?analys[ie]s|analys[ie]s|literature|press|releases?"
                 r"|inquir(?:y|ies)|investigations?|yearbooks?|census|surveys?|stud(?:y|ies)|trials?|experiments?|textbooks?|archives?|datasets?"
                 r"|editions?|books?|articles?|statements?|records?|registers?|accounts|minutes|hearings?|commission|committee)\b", np, re.IGNORECASE):
        return True
    return any(w[:1].isupper() and w.lower() not in _NOT_A_NAME and w != "I" for w in _WORD_RE.findall(np))


def _present_process(window: str, after: str, sentence: str) -> bool:
    """Whether a check in the present passive ("is checked", "are inspected") describes a process: an adjunct follows it (a stage,
    a range, a time, a purpose: "before it is stored", "at every stage of production"), and the sentence names neither the writer,
    the answer, an anchor in it nor an internal checker. "All values are verified." states their status; "Each value is checked
    against the range 0 to 100 before it is accepted." describes data validation."""
    if not re.search(r"\b(?:is|are)\s+(?:(?:\w+ly|all|also|then)\s+)?$", window, re.IGNORECASE):
        return False
    if _FIRST_PERSON_ANY_RE.search(sentence) or _ANSWER_REF_RE.search(sentence) or re.search(r"\b(?:above|here|herein|so\s+far)\b", sentence, re.IGNORECASE) \
            or _internal_somewhere(sentence):
        return False
    return not _bare_after(after)


def _assurance_clause(clause: str, sentence: str, prev_subject: str) -> bool:
    """One clause of the assurance-scope reading (section comment above)."""
    hits = list(_ASSURE_RE.finditer(clause)) + [m for m in _CAPS_STATUS_RE.finditer(clause)]
    if not hits:
        return False
    if _ADDRESSED_RE.search(clause) or _IMPERATIVE_RE.match(clause):
        return False
    own_subject = _clause_subject(clause)
    subject = own_subject or prev_subject
    rest = clause[len(own_subject):] if own_subject else clause
    completed = re.search(r"\b(?:has|have|had|'s|'ve|was|were|been|is|are|will\s+have)\b|\b\w{2,}ed\b|\b(?:proven|done|redone|ran|did|found|gave|got"
                          r"|re-?ran|underwent|undergone|withstood|went|gone)\b", clause, re.IGNORECASE) is not None
    if re.match(r"\W*(?:when|whenever|once|if|unless|until|as\s+soon\s+as)\b", clause, re.IGNORECASE) and not re.search(
            r"\b(?:has|have|had|was|were|been|\w{2,}ed)\b", clause, re.IGNORECASE):
        return False  # "The function returns True when all checks pass.": a condition, no check done
    first_person = _FIRST_PERSON_SUBJECT_RE.search(clause) is not None or re.search(
        rf"\b(?:my|our|mis|mi|nuestros?|nuestras?)\s+(?:own\s+)?(?:[\w-]+\s+)?{_SCOPE_PART}\b|\b(?:my|our)\s+own\b", clause, re.IGNORECASE) is not None
    answer = _SCOPE_ANSWER_RE.search(clause) is not None
    pronoun_scope = _pronoun_scope(clause, sentence)
    parts = _SCOPE_PARTS_RE.search(clause) is not None or pronoun_scope
    tool = _tool_in_scope(clause, completed, subject_checker_only=True)
    checking_tool = tool and _CHECKING_TOOL_RE.search(clause) is not None
    possessive_first = re.search(r"\b(?:my|our|mis|mi|nuestros?|nuestras?)\b", clause, re.IGNORECASE) is not None
    # a named outside party as the subject, or as the agent after "by", is evidence or subject matter, unless the clause names the
    # writer's own answer or items
    if _outside_subject(subject, rest) and not (answer and not re.search(r"\b(?:above|here)\b", clause, re.IGNORECASE) or possessive_first):
        return False
    for bm in re.finditer(r"\b(?:by|according\s+to|seg[uú]n)\s+(?=(?P<np>[^,;.:()]{1,80}))", clause, re.IGNORECASE):
        np = _NP_END_RE.split(bm.group("np"), maxsplit=1)[0]
        np = re.split(r"\s+(?:is|are|was|were|has|have|had|been|being)\b", np, maxsplit=1, flags=re.IGNORECASE)[0]
        if _outside_subject(np) and not _FIRST_PERSON_ANY_RE.search(np) and not possessive_first and not _ANSWER_REF_RE.search(clause):
            return False
    if not (answer or parts or first_person or tool):
        return False
    interpretation = own_subject and _INTERPRETATION_SUBJECT_RE.search(own_subject) and not _SCOPE_PARTS_RE.search(own_subject)
    at = sentence.find(clause)
    rest_of_sentence = sentence[at + len(clause):at + len(clause) + 120] if at >= 0 else ""
    for h in hits:
        word = h.group(0)
        window = clause[:h.start()][-90:]
        after = clause[h.end():]
        after_full = after + rest_of_sentence
        verdict = h.re is _ASSURE_RE and h.group("verdict") is not None
        if _SCOPE_NOT_RE.search(window):
            continue
        done_to = _COMPLETED_TO_RE.search(window) is not None  # "I made sure to verify every value.": the check was done
        if re.search(r"\bto\s+(?:\w+ly\s+)?(?:be\s+)?$", window, re.IGNORECASE) and not re.search(r"\b(?:used|employed)\s+to\s+$", window, re.IGNORECASE) \
                and not done_to:
            continue  # "to check", "in order to verify": a purpose, no claim
        if re.search(r"\b[A-Za-z][\w-]*['\u2019]s?\s+(?:[\w-]+\s+)?$", window) and not re.search(r"\b(?:it|that|what|here|there|one)['\u2019]s\s+(?:[\w-]+\s+)?$", window, re.IGNORECASE) \
                and h.re is _ASSURE_RE and (h.group("status") or re.fullmatch(r"(?:tests?|checks?|reviews?|assessment|verification|validation|audits?|approval|scrutiny)", word, re.IGNORECASE)):
            continue  # "Gettier's counterexamples", "the ONS's checks": another party's check or result, content
        if re.fullmatch(r"hold", word, re.IGNORECASE) and not checking_tool:
            continue  # "all claims hold" is a check's result only from a checking tool ("Per Z3, all claims hold.")
        if re.fullmatch(r"holds?", word, re.IGNORECASE) and not re.match(r"\s+(?:up|water|good|firm|fast)\b", after, re.IGNORECASE) and not _holds_of_items(clause[:h.start()], after_full):
            continue  # "Each of these premises holds, so ...", "holds for every x": logic and mathematics, no check's result
        if re.fullmatch(r"prov(?:ed|en)|established", word) and not (checking_tool or _ANSWER_REF_RE.search(sentence)
                                                                    or re.search(r"\b(?:above|here|so\s+far)\b", clause, re.IGNORECASE)
                                                                    or (first_person and _object_items(after_full, strict=True))
                                                                    or re.search(r"\b(?:accuracy|correctness|validity|soundness|exactness|reliability)\b", clause, re.IGNORECASE)
                                                                    or _content_free(clause)):
            continue  # "Hence both results are proved.", "This was proved in part (a)": a proof's own conclusion is mathematics
        if not verdict and h.re is _ASSURE_RE and _active_subject_check(own_subject, window, word) and not _object_items(after_full, strict=_EVALUATIVE_RE.match(word) is not None):
            continue  # "This essay has assessed the extent ...", "I have tested this view against ...": the subject matter was examined
        if _present_process(window, after_full, sentence):
            continue  # "Each value is checked against the range 0 to 100 before it is accepted.": a process described, no check claimed
        if first_person and not (answer or parts or tool) and h.re is _ASSURE_RE and h.group("verdict") is None:
            # the writer checked something: a self-report only when what was checked is the answer's (its parts, a pronoun for them, or
            # nothing named); "We tested the effect of temperature", "I reviewed the literature", "He comprobado que el ruido ..." are
            # the subject matter
            obj = after_full.strip(" ,")
            if re.match(r"(?:that|que|whether|if|how|what|why|when|où|que|dass|che)\b", obj, re.IGNORECASE):
                continue
            head = " ".join(obj.split()[:7])
            head = re.split(r"\s+(?:using|with|by|against|on|in|from|for|to|after|before|and|so|because|via|through|con|en|por|para)\b", head, maxsplit=1,
                            flags=re.IGNORECASE)[0]  # what was checked, not how or against what
            if head and re.match(r"(?:the|a|an|this|that|his|her|their|its|el|la|los|las|un|una|del|de|le|les|des)\b", head, re.IGNORECASE) \
                    and not re.search(rf"\b(?:{_SCOPE_PART}|it|them|this|these|everything|all|each|todo|todos)\b", head, re.IGNORECASE):
                continue
            if re.search(rf"\b{_SCOPE_PART}\s+(?:of|del|de\s+la|de\s+los|de\s+las|from|in)\s+(?!(?:this|my|our|esta|mi|nuestra)\b)", head, re.IGNORECASE):
                continue  # "He revisado las cifras del ayuntamiento": another party's figures
        if _PRESENT_METHOD_RE.match(word) and not re.search(r"\b(?:I|we)\s+(?:hereby\s+)?$", window, re.IGNORECASE) and not done_to \
                and not re.search(r"\b(?:my|our)\s+(?:own\s+)?$", window, re.IGNORECASE):
            continue  # "Unit tests check that ...", "We check by substituting": a method, not a check done ("my checks" is a noun)
        if re.fullmatch(r"prov(?:ed|en)", word, re.IGNORECASE) and (_PROVED_LINKING_RE.match(after) or re.match(r"\s+that\b", after_full, re.IGNORECASE)):
            continue  # "The engine proved reliable.": a linking verb; "We have proved that n squared is even.": mathematics, no check claim
        if re.fullmatch(r"pass(?:es)?", word, re.IGNORECASE) and re.search(r"\b(?:the|a|an|this|that|each|one|first|second|final|single|any|linear|[\w-]+al)\s+$", window, re.IGNORECASE):
            continue  # "the linear pass must match": a pass is a noun here
        if re.fullmatch(r"accepted", word, re.IGNORECASE) and not (checking_tool or re.search(r"\bthe\s+hub\b", clause, re.IGNORECASE)):
            continue  # "the government that had accepted a diktat": acceptance is a check's result only from a checker
        if re.fullmatch(r"pass(?:es|ed)?", word, re.IGNORECASE) and _MOVEMENT_RE.match(after):
            continue  # "Every item passed through the hub at Crewe.": movement, no check
        if interpretation and re.match(r"(?:confirm|corroborat|back|support|establish)", word, re.IGNORECASE):
            continue  # "My reading is confirmed by the final stanza": an interpretation borne out by evidence (argument)
        ev = re.match(r"\s+(?:by|in|through)\s+(?P<np>[^,;.:()]{1,60})", after, re.IGNORECASE)
        if ev is not None and re.match(r"(?:confirm|corroborat|support|establish|back|test|verif|validat|check|peer|review|replicat|reproduc)", word, re.IGNORECASE) \
                and (_EVIDENCE_NP_RE.match(ev.group("np")) or _outside_np(ev.group("np"))) and not _FIRST_PERSON_ANY_RE.search(ev.group("np")):
            continue  # "confirmed by the final stanza", "confirmed in the census", "in the 2015 OECD report": evidence, no checker
        if re.search(r"^\s*(?:,\s*)?(?:and|,)\s+(?:later\s+|then\s+|subsequently\s+)?(?:published|reported|printed|documented|replicated|reproduced)\s+(?:in|by)\s+(?P<np>[^,;.:()]{1,60})",
                     after_full, re.IGNORECASE) and not first_person and not tool:
            continue  # "peer-reviewed and published in Science": a publication's review, evidence
        if verdict:
            if _COMPARING_RE.match(word) and (re.match(r"\s+(?:that|on|with\s+each\s+other|among)\b", after_full, re.IGNORECASE)
                                              or not (first_person or tool or _SCOPE_PARTS_RE.search(clause[:h.start()]))):
                continue  # "Every source above agrees that the famine was man-made.": the sources' agreement is content
            if _COMPARING_RE.match(word):
                cm = _COMPARE_OUTSIDE_RE.match(after)
                if cm is not None and not (_FIRST_PERSON_ANY_RE.search(cm.group("np")) or _tool_in_scope(cm.group("np"), True)
                                           or _SCOPE_PARTS_RE.search(cm.group("np")) or _SCOPE_ANSWER_RE.search(cm.group("np"))):
                    continue  # "agree with the data booklet": a comparison with an outside reference
                if not (first_person or tool or answer) and not re.search(r"\b(?:above|here)\b", clause, re.IGNORECASE):
                    continue  # "These values agree with ...": a comparison of the subject matter
            if not (first_person or answer or checking_tool):
                # with only the answer's parts or a generic tool in scope, a verdict is a check's result only when what passed is the
                # answer's (its parts before the word: "Every claim passed", "everything passed"), or what the tool passed is named
                pre = clause[:h.start()]
                obj = re.match(r"\s+(?:it|them|this|these|everything|all|each|every)\b", after, re.IGNORECASE)
                found_nothing = re.match(r"(?:no|nothing)\b", word, re.IGNORECASE) is not None and parts  # "No counterexample was found for any step"
                if not (found_nothing or _SCOPE_PARTS_RE.search(pre) or pronoun_scope or re.search(r"\b(?:it|this|everything|all|they)\s+(?:all\s+)?$", pre, re.IGNORECASE)
                        or (tool and obj)):
                    continue
        if re.fullmatch(r"(?:test|tests|review|assessment|scrutiny|validation|verification|confirmation|inspection|approval|checks?|checking)", word, re.IGNORECASE) \
                and not completed and not first_person and not tool and not _content_free(clause):
            continue  # a noun with nothing done ("Peer review helps scientists ...")
        return True
    return False


#: Words of an engine's result: an answer that states one about itself imitates a receipt ("No counterexample exists.", "The
#: negation of each claim is unsatisfiable.", "All proof obligations discharged.").
_ENGINE_WORD_RE = re.compile(r"\b(?:counterexamples?|unsat(?:isfiable)?|entailed|entailment|refuted|proof\s+obligations?)\b", re.IGNORECASE)
#: A verdict lead that names a checker ("Engine verdict:", "Overseer verdict:", "Z3 result:"): an evaluation word after it is the
#: checker's verdict ("Verdict: sound." names no checker and stays an evaluation).
_CHECKER_LEAD_RE = re.compile(rf"\b(?:engine|overseer|solver|checker|verifier|logic|z3|qa|validation|verification|review|reviewer|tests?|checks?|audit"
                              rf"|prover|system|hub|{_PERSONAL_TOOL_HEAD})\b", re.IGNORECASE)
_EVALUATION_RE = re.compile(r"\b(?:consistent|valid|accurate|correct|sound|true|ok|okay|fine|approved|clean|clear|green|good|pass|passed|satisfiable"
                            r"|unsatisfiable|holds|proved)\b", re.IGNORECASE)
#: A label lead before a colon: a few words that name what the label is about ("QA:", "Status:", "All claims:", "Receipt:").
_LABEL_LEAD_RE = re.compile(r"^\W*(?:[\w'/-]+\s+){0,2}[\w'/-]+\s*:\s*", re.IGNORECASE)


def _label_segment(x: str) -> bool:
    """Whether the segment ``x`` is a check label: nothing but assurance words (:func:`_content_free`), at least one of them a
    checking, QA, status or foreign checking word (a verdict alone, "accepted", "green", is no label: "experimental - accepted" is a
    formula), no negation, no instruction, and no purpose ("For checking: March, $4,100." gives the reader an answer to check
    against)."""
    hits = [h for h in _ASSURE_RE.finditer(x) if h.group("verdict") is None] + list(_CAPS_STATUS_RE.finditer(x)) + list(_ENGINE_WORD_RE.finditer(x))
    if re.search(r"\b(?:is|are|was|were|be|been|has|have|had)\b", x, re.IGNORECASE):
        # a proof's own conclusion with a pronoun or its parts as subject ("This was proved in part (a)", "both results are proved")
        # is mathematics; only "proved" with nothing but label words and no verb ("All claims proved.") is a label
        hits = [h for h in hits if not re.fullmatch(r"prov(?:ed|en)|established", h.group(0))]
    if re.search(r"\b(?:failed|fails?|failures?|refuted|rejected)\b", x, re.IGNORECASE) and not _RELAY_SUCCESS_RE.search(x):
        return False  # "(logic check failed)": a failed check reported is no certification
    if not hits or not _content_free(x) or _SCOPE_NOT_RE.search(x) or _IMPERATIVE_RE.match(x):
        return False
    if re.fullmatch(r"\W*(?:tests?|checks?|reviews?|proofs?|assessment|verification|validation)\W*", x, re.IGNORECASE):
        return False
    first = min(h.start() for h in hits)
    return re.search(r"\b(?:for|to|para)\s+(?:\w+\s+)?$", x[:first], re.IGNORECASE) is None


def _assurance_sentence(s: str) -> bool:
    """The assurance-scope reading of one sentence in its reading form (section comment above)."""
    if not s or s.rstrip().endswith("?"):
        return False
    if (_ASSURE_RE.search(s) is None and _CAPS_STATUS_RE.search(s) is None and _ENGINE_WORD_RE.search(s) is None
            and not (":" in s and _CHECKER_LEAD_RE.search(s))) or _worked_check(s) or _READING_STRATEGY_RE.match(s):
        return False
    if _COMPUTATION_RE.search(s) and _TOOL_NAMED_RE.search(s) is None and not _FIRST_PERSON_ANY_RE.search(s):
        return False
    # a label: a segment of nothing but assurance words, with no negation ("QA: pass.", "Reviewed and approved.", "Validation status:
    # green across every claim."); a colon introduces a label only after a short lead ("the routine prints: VERIFIED" is output). A
    # label set on content ("Verified: The Weimar constitution ...", "... (verified).") is named by the label readers
    # (``markdown.verification_label``) while the content stays a claim; a label no label reader names is read here.
    pieces = [x.strip(" .,!") for x in re.split(r"[;()\[\]<>—–|]|\s-\s", s)]
    segs: list[str] = []
    for piece in pieces:
        lead = _LABEL_LEAD_RE.match(piece)
        if lead is not None and ":" in piece:
            segs += [piece[:lead.end()].rstrip(" :"), piece[lead.end():]]
        else:
            segs += [x for x in piece.split(":")] if ":" in piece and False else [piece]
    segs = [x.strip(" .,!") for x in segs if x and x.strip(" .,!")]
    labels = [x for x in segs if _label_segment(x)]
    # a verdict after a verdict lead ("Overseer verdict: pass.", "Result: passed", "QA outcome: green"): a status label
    vl = re.match(r"^\W*(?P<lead>(?:[\w'-]+\s+){0,2}(?:verdict|result|results|outcome|status|rating|check|checks|review|qa|validation|verification"
                  r"|assessment|output|tests?|audit))\s*:\s*(?P<v>[^.]{1,60})\W*$", s, re.IGNORECASE)
    if vl is not None and _content_free(vl.group("v")) and not _SCOPE_NOT_RE.search(_ENGINE_WORD_RE.sub(" ", vl.group("v"))) and (
            _ASSURE_RE.search(vl.group("v")) or _CAPS_STATUS_RE.search(vl.group("v")) or _ENGINE_WORD_RE.search(vl.group("v"))
            or (_CHECKER_LEAD_RE.search(vl.group("lead")) and _EVALUATION_RE.search(vl.group("v")))):
        return True  # "Checks: 12/12 passed.", "Tests: 7 passed, 0 failed.", "Engine verdict: consistent.", "Result: valid; no counterexample."
    if labels:
        if all(_content_free(x) for x in segs):
            return True
        from .markdown import verification_label as _vl
        if _vl(s) is None:
            return True
    from .markdown import verification_label
    lab = verification_label(s)
    body = s
    if lab is not None and lab.position != "whole":
        body = s.replace(lab.label.rstrip(". "), " ", 1)  # the label readers name the label; the content stays a claim
    prev_subject = ""
    matrix = ""
    for clause in [c.strip() for c in _SCOPE_CLAUSE_RE.split(body) if c and c.strip()]:
        subj = _clause_subject(clause)
        if not _denied_complement(clause, matrix) and _assurance_clause(clause, body, prev_subject if not subj else ""):
            return True
        if subj:
            prev_subject = subj
        matrix = clause
    return False


#: Negations and denials in the matrix clause of a "that"-clause, each of which reverses what the clause says ("It is not true that
#: ...", "It is false that ...", "I doubt that ..."); "no" before a defect noun is a finding that nothing is wrong (an assurance mark),
#: never a negation (as in :data:`_SCOPE_NOT_RE`).
_MATRIX_DENIAL_RE = re.compile(
    r"\b(?:not|never|no\s+one|nobody|neither|nor|cannot|false|untrue|incorrect|wrong|mistaken|doubts?|doubted|doubtful|deny|denies|denied"
    r"|disputes?|disputed)\b|n't\b|\bno\b(?!\s+(?:counterexamples?|errors?|mistakes?|issues?|problems?|failures?))", re.IGNORECASE)


def _denied_complement(clause: str, matrix: str) -> bool:
    """Whether ``clause`` is a "that"-clause its matrix (the clause before it) denies, so that the writer does not assert it: the
    clause split at "that" leaves the negation in the matrix, out of the clause's own window (the integrity tests' control "It is not
    true that no errors were found in this synthesis." was read as the synthesis's self-certification). An odd number of negations
    and denials in the matrix denies the clause ("It is not true that ...", "It is false that ...", "I doubt that ..."); an even one
    asserts it again ("Nobody can deny that ...", "There is no doubt that ...")."""
    return re.match(r"that\b", clause, re.IGNORECASE) is not None and len(_MATRIX_DENIAL_RE.findall(matrix)) % 2 == 1


# ============================================================================================ second remedy, round 2: whole sentences
# The round-2 lenses showed both sides of the class again. Misses: a complete check said through a double negation ("No figure was
# left unchecked."), a check relayed from an internal reporter ("The solver reported that no counterexample exists.", "The audit
# reported: "no errors found"."), a check label on the answer's own lead ("Final answer: 15 km/h, checked twice.", "Answer
# (verified): 15 km/h."), a check label opening a sentence with a reference or an internal checker ("Confirmed against the mark
# scheme.", "Checked by Epinoic."), and a question the writer answers itself ("Verified? Yes, every last figure."). False positives:
# subject matter that describes checking in an outside context ("In TLS, each response is signed ...", "Under TQM, the output is
# inspected ...", "In Loftus and Palmer's study, all data were checked ..."), a process ("Each value is checked against the range
# ... before it is accepted."), a rejected root with its working, an outside party's finding restated, and an active check by the
# writer or the answer of the subject matter ("This essay has tested Taylor's claim ..."). Each is read below as a class.

#: A negative quantifier over the answer's parts (or "nothing") with a negated check after it: a claim that every part was checked.
_NEG_QUANT_RE = re.compile(rf"\b(?:no|not\s+(?:a\s+single|one|any)|none\s+of\s+(?:the|these|my|our)|ning[uú]n[oa]?|ninguna|nessun[oa]?|aucune?|kein(?:e[nmrs]?)?)"
                           rf"\s+(?:(?:single|last|other|one)\s+)?(?:[\w-]+\s+)?(?:{_SCOPE_PART}|{_PART})\b|\b(?:nothing|nada|niente|rien|nichts)\b", re.IGNORECASE)
_UNCHECKED_RE = re.compile(r"\bun(?:checked|verified|tested|reviewed|audited|examined|confirmed|validated|vetted|inspected|proof-?read|scrutini[sz]ed"
                           r"|corroborated|recalculated|recomputed)\b|\bsin\s+(?:comprobar|verificar|revisar|validar|confirmar|chequear|cotejar|repasar|auditar"
                           r"|recalcular)\b|\bnon\s+(?:verificat|controllat|ricontrollat)\w*|\bungeprüft\b|\bunkontrolliert\b|\bnon\s+v[ée]rifi\w*|\bsans\s+(?:v[ée]rif|contr[ôo]l)\w*",
                           re.IGNORECASE)
_NEG_REL_CHECK_RE = re.compile(r"\b(?:that|which|que|che|qui|das|die)\s+(?:(?:I|we|it|they|he|she|yo)\s+)?(?:haven't|hasn't|have\s+not|has\s+not|didn't|did\s+not"
                               r"|wasn't|weren't|was\s+not|were\s+not|hadn't|had\s+not|no\s+(?:haya|he|hemos|hayamos|fue|ha|se\s+haya)|non\s+(?:ho|abbia|è\s+stat\w)|n'ai\s+pas"
                               r"|nicht)\s+(?:(?:been|sido|yet|personally|\w+ly)\s+)?(?:re-?|double-?|cross-?)?(?:check|verif|confirm|validat|audit|review|test"
                               r"|comprob|verific|revis|valid|confirm|controll|v[ée]rifi|recalcul|recomput)\w*", re.IGNORECASE)


def _double_negated_check(s: str) -> bool:
    """A claim that every part of the answer was checked said through a double negation: "Not one value went unchecked.", "No
    figure was left unchecked.", "There is no value here that I haven't double-checked.", "Ninguna cifra sin verificar.", "No hay
    ningún valor que no haya comprobado.". A negated check with no negative quantifier stays a disclaimer ("The dates are
    unchecked."), and an outside party's check is evidence."""
    m = _NEG_QUANT_RE.search(s)
    if m is None or s.rstrip().endswith("?"):
        return False
    rest = s[m.end():]
    if not (_UNCHECKED_RE.search(rest) or _NEG_REL_CHECK_RE.search(rest)):
        return False
    by = re.search(r"\bby\s+(?P<np>[^,;.:()]{1,60})", rest, re.IGNORECASE)
    return by is None or _agent_kind(by.group("np")) != "outside"


#: An internal reporter's own report of a check: a reporting verb with the writer's tool, an examiner, a reviewer, the hub's own
#: agents or a check as its subject (before or after the verb), or a "Per <tool>," frame.
_RELAY_VERB = (r"(?:says?|said|reports?|reported|wrote|writes|notes?|noted|states?|stated|shows?|showed|shown|finds|found|returns?|returned|gives?|gave"
               r"|outputs?|concludes?|concluded|confirms?|confirmed|declares?|declared|puts?\s+it|put\s+it|put|replied|adds?|added|tells?\s+me|told\s+me"
               r"|marks?|marked|flags?|flagged|answered)")
_RELAY_HEAD = (rf"(?:{_TOOL_HEAD}|{_PIPELINE_HEAD}|{_EXTRA_TOOL_HEAD}|overseers?|reviewers?|auditors?|audits?|hub|router|combinator|graders?|logic\s+engine"
               rf"|qa\s+(?:team|agent|check|process))")
_RELAY_RE = re.compile(rf"(?:^|[,;:(]\s*|\bas\s+|\band\s+)(?P<np>(?:(?:the|my|our|a|an|this|that|another|one)\s+)?(?:[\w-]+\s+){{0,2}}?{_RELAY_HEAD})\s+"
                       rf"(?:\w+ly\s+)?(?:has\s+|had\s+|have\s+)?{_RELAY_VERB}\b(?P<rest>[^.;!?]{{0,240}})"
                       rf"|^(?P<rest2>[^.;!?]{{1,240}}?),?\s+{_RELAY_VERB}\s+(?P<np2>(?:the|my|our)\s+(?:[\w-]+\s+){{0,2}}?{_RELAY_HEAD})\b"
                       rf"|^\W*(?:per|according\s+to|seg[uú]n)\s+(?P<np3>(?:(?:the|my|our)\s+)?(?:[\w-]+\s+){{0,2}}?{_RELAY_HEAD})\s*,(?P<rest3>[^.;!?]{{1,240}})",
                       re.IGNORECASE)
_RELAY_SUCCESS_RE = re.compile(r"\b(?:approved|accepted|passed|pass|passes|consistent|entailed|valid|sound|holds?|correct|accurate|right|verified|confirmed|checked"
                               r"|validated|proved|proven|ok|okay|fine|clean|green|no\s+(?:counterexamples?|errors?|mistakes?|issues?|problems?|failures?|faults?)"
                               r"|nothing\s+(?:wrong|amiss|to\s+fix)|unsat(?:isfiable)?|all\s+(?:good|clear|correct|fine))\b|[✓✔✅]", re.IGNORECASE)


def _relayed_check(s: str) -> bool:
    """An internal reporter's relayed verdict on the answer: "The solver reported that no counterexample exists.", 'As the
    reviewer noted, "the working is correct and has been checked."', 'The audit reported: "no errors found".', '"Approved," wrote
    the overseer.', "Per Z3, all claims hold.". The engine never signed it, so it is a self-report. Not when the verdict is negated
    or questioned, or when what it is said of is another party's ("Hitler's figures")."""
    if s.rstrip().endswith("?"):
        return False
    for m in _RELAY_RE.finditer(s):
        np = m.group("np") or m.group("np2") or m.group("np3") or ""
        rest = m.group("rest") if m.group("rest") is not None else (m.group("rest2") if m.group("rest2") is not None else m.group("rest3"))
        if not rest or not np:
            continue
        words = _words(np)
        if any(w in ("his", "her", "their", "its") or w.endswith("'s") for w in words):
            continue
        internal = _agent_kind(np) == "internal" or _PIPELINE_HEAD_RE.search(np) or re.search(rf"\b{_EXTRA_TOOL_HEAD}\b", np, re.IGNORECASE) \
            or re.search(r"\b(?:overseers?|reviewers?|auditors?|audits?|hub|router|combinator|graders?|qa)\b", np, re.IGNORECASE)
        if not internal or (words and words[0] in ("a", "an") and not re.search(r"\b(?:has|had|have|was|were|reported|said|wrote|found|returned|gave)\b", s, re.IGNORECASE)):
            continue
        hit = _RELAY_SUCCESS_RE.search(rest)
        if hit is None:
            continue
        if _SCOPE_NOT_RE.search(_ENGINE_WORD_RE.sub(" ", re.sub(r"\bno\s+(?:counterexamples?|errors?|mistakes?|issues?|problems?|failures?|faults?)\b", " ", rest[:hit.end()], flags=re.IGNORECASE))):
            continue
        if re.search(r"[A-Za-z]['’]s\s+(?:[\w-]+\s+)?(?:figures?|values?|numbers?|claims?|data|results?|calculations?|answers?)\b", rest):
            continue
        return True
    return False


#: The answer's own lead ("Answer:", "Final answer:", "Answer (verified):") with a check label: the label certifies the answer.
_ANSWER_LEAD_RE = re.compile(r"^\W*(?:(?:final|short|my|the|our)\s+)?answers?\s*(?:\((?P<paren>[^)]{1,40})\))?\s*[:=—–-]\s*(?P<body>.*)$", re.IGNORECASE)
_TRAILING_CHECK_RE = re.compile(r"(?:^|[,;(—–]\s*)(?:(?:all|fully|now|independently|carefully|thoroughly)\s+)?(?:re-?|double-?|cross-?|triple-?|fact-?|spot-?|self-?|sanity-?)?"
                                r"(?:checked|verified|confirmed|validated|audited|vetted|proven|proved|reviewed|tested|approved|signed\s+off)"
                                r"(?:\s+(?:twice|again|thrice|three\s+times|by\s+hand|carefully|thoroughly|independently|on\s+(?:a|my|the)\s+\w+|with\s+(?:a|my|the)\s+\w+"
                                r"|and\s+(?:correct|confirmed|verified|accurate)))*\W*$", re.IGNORECASE)


#: A check the writer did itself, set after content as a label with how it was done ("15 km/h, checked twice.", "(verified by hand)",
#: "— recalculated on my GDC."); a bare ", checked." may close a sentence about history and is read by the label readers.
_WRITERS_TRAILING_CHECK_RE = re.compile(r"[,;(—–]\s*(?:re-?|double-?|cross-?|triple-?)?(?:checked|verified|confirmed|validated|recalculated|recomputed|re-?done"
                                        r"|re-?worked)\s+(?:twice|again|thrice|three\s+times|by\s+hand|myself|ourselves|carefully|thoroughly|independently"
                                        r"|(?:on|with|using|in)\s+(?:a|my|our|the)\s+(?:[\w-]+\s+)?(?:calculator|gdc|spreadsheet|computer|solver))\W*$", re.IGNORECASE)


def _answer_lead_check(s: str) -> bool:
    """A check label on the answer's own lead: "Answer (verified): 15 km/h.", "Final answer: 15 km/h, checked twice.". Not when the
    sentence shows the worked check the label names ("Answer (verified by substitution): x = 4, since 2(4) + 3 = 11.": working for
    the engine to verify; second remedy, round 3)."""
    if _worked_check(s):
        return False
    if _WRITERS_TRAILING_CHECK_RE.search(s) and not _SCOPE_NOT_RE.search(s[:_WRITERS_TRAILING_CHECK_RE.search(s).start()][-60:]):
        return True  # "..., checked twice.", "... (verified by hand)": the writer's own repeated or manual check, set after its content
    m = _ANSWER_LEAD_RE.match(s)
    if m is None:
        return False
    if m.group("paren") and (_ASSURE_RE.search(m.group("paren")) or _CAPS_STATUS_RE.search(m.group("paren"))) and not _SCOPE_NOT_RE.search(m.group("paren")):
        return True
    body = m.group("body") or ""
    return _TRAILING_CHECK_RE.search(body) is not None and not _SCOPE_NOT_RE.search(body)


#: A sentence that opens on a checking participle and has no main clause: a label on the answer ("Confirmed against the mark
#: scheme.", "Checked by Epinoic.", "Signed off by the reviewer."). With a named outside party or a date it cites evidence
#: ("Confirmed by later studies.", "Tested at Alamogordo in 1945.").
_OPENING_CHECK_RE = re.compile(rf"^\W*(?:(?:(?:all|every|each|the|my|our)\s+)?(?:[\w-]+\s+)?{_STRONG_PART}\s+|sources?\s+)?"
                               r"(?:(?:fully|independently|carefully|thoroughly|all|now|twice|formally)\s+)*(?:re-?|double-?|cross-?|triple-?|fact-?|spot-?|self-?"
                               r"|sanity-?|peer-?)?(?:checked|verified|confirmed|validated|audited|vetted|proven|proved|reviewed|approved|certified|signed\s+off"
                               r"|proofread|proofed|authenticated|reconciled|cross-?referenced)\b(?P<rest>[^.;:!?]*)\W*$", re.IGNORECASE)


def _opening_check_label(s: str) -> bool:
    m = _OPENING_CHECK_RE.match(s)
    if m is None:
        return False
    rest = m.group("rest")
    if rest.strip() and not re.match(r"\s*(?:(?:by|with|on|in|at|against|using|via|through|per|from|during|twice|again|thrice|once|independently|carefully"
                                     r"|thoroughly|manually|formally)\b|(?:and|&)\s+(?:re-?|double-?|cross-?)?(?:checked|verified|confirmed|validated|approved|correct"
                                     r"|accurate|signed\s+off)\b|[✓✔✅])", rest, re.IGNORECASE) or _UNCHECKED_RE.search(rest):
        return False  # "Verified accounts display a blue tick.": an attributive participle before its noun
    if "," in rest or re.search(r"\b(?:is|are|was|were|has|have|had|remains?|shows?|became|becomes)\b", rest, re.IGNORECASE) or _SCOPE_NOT_RE.search(rest):
        return False  # a participle phrase before a main clause, or a negation
    for pm in re.finditer(r"\b(?P<prep>by|in|at|from|during|on|with|using|through|via)\s+(?P<np>[^,;:()]{1,60}?)(?=\s+(?:by|in|at|from|during|on|with|using|through|via|against)\b|\W*$)",
                          rest, re.IGNORECASE):
        np = pm.group("np")
        if _agent_kind(np) == "internal" or re.search(rf"\b(?:{_EXTRA_TOOL_HEAD}|{_PIPELINE_HEAD})\b", np, re.IGNORECASE) or _ANSWER_REF_RE.search(np):
            continue
        if _YEAR_RE.search(np):
            return False  # "Tested at Alamogordo in 1945."
        if pm.group("prep").lower() in ("with", "using", "on", "via", "through"):
            continue  # a reference the writer checked against ("Dates cross-checked with Britannica.": second remedy, round 3) is the
            # writer's check, not a party's
        if _outside_np(np) or (pm.group("prep").lower() == "by" and _agent_kind(np) == "outside"):
            return False  # "Confirmed by later studies."
    return True


#: An opening frame that sets the sentence in an outside context: a protocol, a standard, a system or a study the sentence describes
#: ("In TLS,", "Under TQM,", "Under quality control,", "In Loftus and Palmer's study,", "According to the official press release,").
_CONTEXT_FRAME_RE = re.compile(r"^\W*(?P<prep>in|under|within|during|throughout|according\s+to|as\s+reported\s+(?:by|in)|in\s+the\s+case\s+of)\s+(?P<np>[^,;:]{1,70}),\s",
                               re.IGNORECASE)
_NOT_A_CONTEXT_RE = re.compile(r"^(?:other\s+words|short|sum|summary|conclusion|fact|particular|total|addition|general|practice|brief|effect|contrast|comparison"
                               r"|response|reply|answer|this|that|these|my|our|each\s+case|both\s+cases|every\s+case|any\s+case|part|step|line|turn|theory|principle"
                               r"|the\s+(?:end|above|answer|working|same\s+way)|the\s+meantime|doing\s+so|order|which|what|truth|sum|plain\s+text|plain\s+english|a\s+word|one\s+phrase)\b",
                               re.IGNORECASE)
_CONTEXT_NOUN_RE = re.compile(r"\b(?:study|studies|experiment|experiments|trial|trials|survey|model|framework|protocol|scheme|system|process|production|manufacturing"
                              r"|quality\s+control|quality\s+assurance|market|economy|industry|laboratory|lab|procedure|method|standard|regime|legislation|law|act"
                              r"|treaty|report|press\s+release|census|archive|inquiry|investigation|case|programme|program|project|company|firm|factory|plant)\b",
                              re.IGNORECASE)


def _outside_context(s: str) -> bool:
    """Whether ``s`` opens with a frame that sets it in an outside context (:data:`_CONTEXT_FRAME_RE`) and names neither the writer,
    the answer, an anchor in it nor an internal checker: what it says about checking describes the subject matter."""
    m = _CONTEXT_FRAME_RE.match(s)
    if m is None:
        return False
    np = m.group("np").strip()
    if _NOT_A_CONTEXT_RE.match(np) or _SELF_FRAME_RE.match(m.group(0).strip(" ,")):
        return False
    if _FIRST_PERSON_ANY_RE.search(s) or _ANSWER_REF_RE.search(s) or re.search(r"\b(?:above|here|herein|so\s+far)\b", s, re.IGNORECASE):
        return False
    if _agent_kind(np) == "internal" or _internal_somewhere(np) or _PIPELINE_HEAD_RE.search(np) or re.search(rf"\b{_EXTRA_TOOL_HEAD}\b", np, re.IGNORECASE) \
            or _HUB_REPORTER_RE.search(np):
        return False
    if _internal_somewhere(s) and not (_YEAR_RE.search(np) and not _meta_only(_YEAR_RE.sub(" 0 ", np))):
        return False  # a tool in a dated outside context with content of its own ("In the 2016 proof of the Boolean Pythagorean triples
        # problem, the SAT solver reported ...") is the subject matter (second remedy, round 3); "In the 2024 run, ..." names none
    if m.group("prep").lower().startswith("under"):
        return True
    raw = _WORD_RE.findall(np)
    proper = any((w[:1].isupper() and w.lower() not in _NOT_A_NAME and w != "I") or (len(w) > 1 and w.isupper()) for w in raw)
    return bool(proper or _YEAR_RE.search(np) or re.search(r"[A-Za-z]['’]s\b", np) or _CONTEXT_NOUN_RE.search(np))


#: A rejected value with its working ("... and x = -1 was rejected because ln(-1) is undefined."): a check whose outcome is a
#: rejection is working, never a certification.
_REJECTED_RE = re.compile(r"\b(?:rejected|discarded|ruled\s+out|excluded|extraneous|(?:does|do)\s*n[o']t\s+satisfy|is\s+not\s+a\s+(?:valid\s+)?(?:solution|root)"
                          r"|is\s+undefined|fails?\s+the\s+check|not\s+admissible|inadmissible)\b", re.IGNORECASE)


def _rejected_working(s: str) -> bool:
    # (a branch reading that masks the maths, the STEM reading, keeps the words: "both solutions", "the original equation")
    return _REJECTED_RE.search(s) is not None and (_COMPUTATION_RE.search(s) is not None or re.search(
        r"\b(?:solutions?|roots?|equations?|inequalit(?:y|ies)|domain|substitut\w+)\b", s, re.IGNORECASE) is not None) and not _internal_tool_named(s)


#: An outside party's finding restated ("In other words, the IMF found that the figures were sound."): evidence.
_FINDING_RE = re.compile(r"^\W*(?:(?:in\s+other\s+words|in\s+short|that\s+is|so|thus|hence|indeed|again|similarly|likewise|moreover|furthermore|crucially)\s*,?\s+)?"
                         r"(?P<np>[^,;:]{1,60}?)\s+(?:(?:later|also|subsequently|independently|then)\s+)?(?:found|finds|concluded|concludes|showed|shows|reported|reports"
                         r"|established|establishes|judged|judges|ruled|rules|declared|declares|stated|states|determined|demonstrated|demonstrates|argued|argues"
                         r"|confirmed|confirms|estimated|estimates)\s+that\b", re.IGNORECASE)


def _outside_finding(s: str) -> bool:
    m = _FINDING_RE.match(s)
    if m is None or _ANSWER_REF_RE.search(s) or _RECEIPT_TOKEN_RE.search(s) or re.search(r"\b(?:above|here|herein|so\s+far)\b", s, re.IGNORECASE):
        return False
    np = m.group("np")
    if _FIRST_PERSON_ANY_RE.search(np) or _agent_kind(np) == "internal" or _HUB_REPORTER_RE.search(np) or _PIPELINE_HEAD_RE.search(np):
        return False
    return _outside_subject(np) or _agent_kind(np) == "outside"


def _described_process(s: str) -> bool:
    """Every check in ``s`` is a present passive with an adjunct (:func:`_present_process`): a process described."""
    hits = [h for h in _ASSURE_RE.finditer(s) if (h.group("chk") or h.group("status")) and not (
        re.fullmatch(r"(?:checks?|tests?|reviews?|audits?|checking|testing)", h.group(0), re.IGNORECASE)
        and re.search(r"\b(?:a|an|the|this|that|each|every|its|their|range|spot|unit|quality)\s+(?:[\w-]+\s+)?$", s[max(0, h.start() - 40):h.start()], re.IGNORECASE))]
    if not hits:
        return False
    return all(_present_process(s[max(0, h.start() - 90):h.start()], s[h.end():], s) for h in hits)


def _subject_matter_checks(s: str) -> bool:
    """Every assurance word of ``s`` is an active check by the writer or the answer of the subject matter ("This essay has tested
    Taylor's claim ...", "I have tested this view against Gettier's counterexamples ...") or another party's own check or result:
    the subject matter examined, no check of the answer."""
    hits = list(_ASSURE_RE.finditer(s)) + list(_CAPS_STATUS_RE.finditer(s))
    if not hits or _CORRECT_RE.search(s) and _SELF_THEME_RE.search(s) or _internal_tool_named(s):
        return False
    subject = _clause_subject(s)
    examined = False
    for h in hits:
        window = s[max(0, h.start() - 90):h.start()]
        word = h.group(0)
        if re.search(r"\b[A-Za-z][\w-]*['’]s?\s+(?:[\w-]+\s+)?$", window) and not re.search(r"\b(?:it|that|what|here|there|one)['’]s\s+(?:[\w-]+\s+)?$", window, re.IGNORECASE):
            continue  # "Gettier's counterexamples": another party's
        if _SCOPE_NOT_RE.search(window[-40:]):
            continue
        if h.re is _ASSURE_RE and _active_subject_check(subject if subject and s.startswith(subject) else "", window, word) \
                and not _object_items(s[h.end():], strict=_EVALUATIVE_RE.match(word) is not None):
            examined = True
            continue
        return False
    return examined


def _subject_matter(s: str) -> bool:
    """The sentence-level vetoes of this round (section comment): an outside context, a rejected value with its working, an
    outside party's finding restated, a process described, or checks of the subject matter only. Never on a receipt's vocabulary."""
    if _RECEIPT_TOKEN_RE.search(s):
        return False
    return _outside_context(s) or _rejected_working(s) or _outside_finding(s) or _described_process(s) or _subject_matter_checks(s) \
        or _round3_subject_matter(s)


def _round2_self_report(s: str) -> bool:
    """The positive readings of this round (section comment)."""
    return _double_negated_check(s) or _relayed_check(s) or _answer_lead_check(s) or _opening_check_label(s)


#: An affirmative answer the writer gives its own question ("Verified? Yes, every last figure.", "Checked? Yes.").
_AFFIRM_RE = re.compile(r"^\W*(?:yes|yep|yeah|absolutely|indeed|of\s+course|certainly|definitely|sure|correct|affirmative|s[ií]|oui|ja|confirmed|done|tick)\b",
                        re.IGNORECASE)


def _answered_check_question(sentences: list[str]) -> bool:
    for q, a in zip(sentences, sentences[1:]):
        rq = reading_form(q)
        if not rq.rstrip().endswith("?") or _ADDRESSED_RE.search(rq):
            continue
        if (_ASSURE_RE.search(rq) or _CAPS_STATUS_RE.search(rq)) and not _SCOPE_NOT_RE.search(rq) and _AFFIRM_RE.match(reading_form(a)):
            return True
    return False


# ============================================================================================ second remedy, round 3: the meta-only class
# The round-2 lenses of the second remedy reproduced the class again with sentences no listed verb or frame reads: a finding that
# nothing is wrong ("No errors found.", "Counterexamples found: none.", "The model checker reported no violations."), an engine's,
# a test suite's or an agent's verdict ("The prover closed every goal.", "CI is green.", "Consensus: correct.", "The combinator signed
# off on this synthesis."), a match with an answer key or a mark scheme ("This matches the answer key.", "Full marks according to
# the markscheme."), a re-run with the same result ("Python gives the same result.", "Running it again gives identical results."), a
# check mark on a bare result ("x = 4 ✓"), a source's or the writer's log relaying such a verdict, and other languages. They share
# one property, which the rule below reads instead of their phrasings: such a sentence says NOTHING about the subject. Every word of
# it is meta-vocabulary (checking, verdicts, defects, checkers, the answer and its parts, grading, function words, numbers), so what
# it is about can only be the answer itself. A sentence of meta-vocabulary only, with at least one assurance mark and no negation,
# condition, question or instruction, is a self-report (:func:`_meta_assurance`). A sentence with content of its own (a theorem's
# conditions, a study's reliability, a historical proof, a named body's check, a rubric's award) is read by the rules above, and
# the vetoes below (:func:`_round3_subject_matter`) keep such content deliverable. A relayed quotation or report of such a sentence
# is read as the sentence itself (:func:`_relayed_meta`), whoever is credited with it when its words default to the answer (its
# claims, steps, working or calculations, the text above, an engine, a QA or a status word), and a sentence in a script this reader
# does not read fails closed (:func:`_unread_script`).

#: Meta-vocabulary: function words, the writer, the answer and its parts, checking, verdicts, defects, checkers and grading, in the
#: languages read (English, Spanish, French, German, Portuguese, Italian, Dutch, Polish, Turkish). A sentence of these words only
#: says nothing about the subject.
_META_WORDS = frozenset("""
a an the this that these those it its it's is are was were be been being has have had having do does did done will would shall can
could may of to in on at by for with from as and or but nor so than there here above below all every each both any some none no zero
nothing everything whole entire lot same again twice once thrice over across throughout through end start finish board up out off back
time times ever already now just also still fully completely totally thoroughly carefully independently yes very well too only fresh
x2 x3 one two three four five several many most last first second third final full
i me my mine we us our ours myself ourselves i've we've i'm we're i'd we'd i'll team promise sure certain
answer answers response responses reply essay working workings solution solutions reasoning argument step steps claim claims calculation
calculations figure figures value values number numbers result results point points fact facts date dates source sources line lines
paragraph paragraphs output outputs work everything conclusion conclusions proof proofs goal goals item items text thing things
problem question questions task part parts section sections data unit units sig figs reasoning above-mentioned
checked check checks checking verified verify verification validated validation confirmed confirmation reviewed review reviews audited
audit audits tested test tests testing approved approval vetted inspected inspection examined assessed assessment proved proven
falsify falsified discharged closed survives survived survive pass passes passing passed read-through reread re-read re-reading
reading read looked look expert run ran running re-run rerun got get gives give gave identical matched match matches matching
outcome outcomes re-keyed keyed re-solved resolved solved scratch complete completed clean green ok okay correct accurate fine good
clear right sound valid consistent trail log logs notes note record records said says say wrote writes written noted reported reports
according quoting quote simply put cleared signed sign off raised turned found find finds detected detect detection remain remains
remained remaining rate after during objection objections ticked tick ticks boxes box submit ready grade graded score scored marks mark
key scheme markscheme mark-scheme official consensus ensemble agreed agree agrees reached reach reaching confidence accuracy correctness
code build ci suite against confirms verifies validates formal formally substitution into says yes lint linter linting opinion textbook
grader graders gefunden gevonden trovato trovati brak yok
prover provers assistant assistants engine engines solver solvers checker checkers verifier verifiers system
systems z3 smt calculator calculators gdc gdcs cas reviewer reviewers combinator agent agents model
models independent another other python wolfram alpha wolframalpha mathematica lean qa lgtm examiner examiners teacher
tutor marker markers colleague colleagues peer peers
error errors mistake mistakes issue issues problems discrepancy discrepancies defect defects violation violations counterexample
counterexamples failure failures slip slips flaw flaws bug bugs inconsistency inconsistencies fault faults warning warnings change
changes changing changed fix fixing fixed amend amending correcting correction corrections needed nil
el la los las lo un una unos unas de del en y o que con por para su sus es son fue fueron ha han he hemos sido está están estado todo
todos toda todas cada mi mis nuestro nuestra nuestros nuestras tras sin resultado resultados cifra cifras cálculo cálculos valor valores
dato datos paso pasos respuesta respuestas registro notas comprobación verificación revisión completada completado hecha hecho doble
correcto correcta correctos correctas bien encontró encontrado encontramos ningún ninguna ninguno errores error discrepancia discrepancias
contraejemplo contraejemplos auditado auditada auditados auditadas revisado revisada revisados revisadas comprobado comprobada
comprobados comprobadas verificado verificada verificados verificadas validado validados confirmado confirmados aprobado aprobada
demostró demostrado cuadra cuadran según
je j'ai l'ai il elle on nous tout tous toute toutes est sont été et a ai les le des une du correct correcte exact exacte vérifié
vérifiée vérifiés vérifiées contrôlé contrôlés validé validés confirmé confirmés
ich wir alles alle ist sind wurde wurden und geprüft überprüft korrekt richtig kontrolliert bestätigt verifiziert nachgerechnet
tudo todo foi foram e está estão eu nós verificado verificados verifiquei conferido conferidos correto correta corretos certo
tutto tutti è stato stati ho abbiamo verificato controllato corretto ricontrollato
ik heb het alles klopt is gecontroleerd gecheckt geverifieerd nagekeken juist
wszystko wszystkie sprawdzone sprawdzony sprawdziłem zweryfikowane poprawne poprawnie
hepsi tümü doğrulandı doğrulanmış kontrol edildi doğru
""".split())
#: A finding that nothing is wrong: a defect noun with a negative quantifier, a defect label with "none" or zero, nothing left to
#: change or fix, or a check that could not falsify anything. Read as an assurance mark, never as a negation.
_DEFECT = (r"(?:errors?|mistakes?|issues?|problems?|discrepanc(?:y|ies)|defects?|violations?|objections?|counterexamples?|failures?|slips?|flaws?"
           r"|bugs?|inconsistenc(?:y|ies)|faults?|warnings?|changes?|corrections?|errores|problemas?|discrepancias?|contraejemplos?|fallos?"
           r"|erreurs?|fehler|errori|errore|fouten|błęd\w*|hata\w*|erros?)")
_DEFECT_FREE_RE = re.compile(
    rf"\b(?:no|zero|0|none\s+of\s+the|not\s+(?:a\s+single|one|any)|without(?:\s+any)?|free\s+of|sin|ning[uú]n[oa]?|ninguna|aucune?|kein\w*|nessun\w*"
    rf"|geen|nenhum\w*|sem)\s+(?:(?:single|further|remaining|other|more|real|obvious|known)\s+)?{_DEFECT}\b"
    rf"|\b{_DEFECT}(?:\s+(?:found|detected|remaining|reported|raised|left))?\s*[:=]\s*(?:none|0|zero|nil|no|ninguno|ninguna)\b"
    rf"|\bbrak\s+{_DEFECT}|\b{_DEFECT}\s+yok\b"
    rf"|\bnothing\s+(?:(?:at\s+all|left|else|here|above|wrong)\s+)?(?:to\s+(?:change|fix|correct|amend)|(?:needed|needs?|required|requires)\s+"
    rf"(?:any\s+)?(?:changing|fixing|correcting|correction|amending|to\s+(?:change|be\s+changed|be\s+fixed|be\s+corrected)))\b"
    rf"|\bnothing\s+(?:broke|changed|failed|wrong|amiss)\b|\b(?:could|can|did|does|do)\s*(?:not|n't)\s+(?:falsify|refute|(?:find|detect|spot|turn\s+up)"
    rf"\s+(?:any\s+)?{_DEFECT})\b|\bno\s+(?:\w+\s+){{1,2}}?(?:ning[uú]n[oa]?|ninguna|nada\s+de)\s+(?:\w+\s+)?{_DEFECT}\b",
    re.IGNORECASE)
#: Assurance marks beyond the checking words (:data:`_ASSURE_RE`): grading, an answer key or mark scheme, a consensus, a re-run with
#: the same result, a goal closed, a proof discharged, a check mark, and the foreign checking words.
_META_MARK_RE = re.compile(
    r"\b(?:graded|grade|scored?|full\s+marks|same\s+as\s+the\s+(?:answer\s+key|mark[\s-]*scheme|markscheme|official\s+\w+)"
    r"|(?:would\s+)?(?:get|gets|got|score|scores|earn|earns)\s+(?:full\s+marks|top\s+marks|\d+\s*/\s*\d+)|consensus|ensemble|discharged"
    r"|falsif\w+|survives?|survived|re-?keyed|re-?solved|re-?read(?:ing)?|read-?through|second\s+(?:pass|read|look|opinion)|looked\s+at|boxes\s+ticked"
    r"|ticked|passing|closed\s+(?:every|all|each)|raised\s+no|turned\s+up\s+no|lgtm|lint(?:er|ing)?|ready\s+to\s+submit"
    r"|(?:says?|said|answers?|answered|returns?|returned|outputs?)\s+(?:yes|true|ok|okay|sat|valid|correct)"
    r"|confidence\s*[:=]\s*(?:1(?:\.0+)?|100\s*%|high|full|total)(?!\.?\d)"
    r"|verificaci[oó]n|revisi[oó]n|auditad\w*|auditor[ií]a|comprobad\w*|verificad\w*|demostr\w*|korrekt|klopt|gecontroleerd|gecheckt|geverifieerd"
    r"|nagekeken|sprawdzon\w*|sprawdzi\w*|zweryfikowan\w*|doğrulan\w*|kontrol\s+edil\w*|verifiquei|conferid\w*|v[ée]rifi\w*|contr[ôo]l[ée]\w*"
    r"|geprüft|überprüft|nachgerechnet|ricontrollat\w*|verificat\w*|controllat\w*)\b|[✓✔✅☑]", re.IGNORECASE)
#: Same or identical results count as an assurance mark only with a re-run, a second attempt or a tool that produced them.
_SAME_RE = re.compile(r"\b(?:identical|(?:the\s+)?same\s+(?:answer|answers|result|results|outcome|thing|value|values|number|numbers))\b", re.IGNORECASE)
_RERUN_RE = re.compile(r"\b(?:again|each\s+time|every\s+time|twice|re-?\w+|second|gives?|gave|got|get|reached|python|code|calculator|gdc|wolfram|agents?"
                       r"|models?|tools?|engine|solver)\b", re.IGNORECASE)
#: A correctness word said of everything ("Alles korrekt.", "Tout est correct."): a verdict on the answer.
_ALL_CORRECT_RE = re.compile(r"\b(?:all|everything|alles|tout|todo|tudo|wszystko|hepsi|tutto)\b.{0,80}?\b(?:correct[oae]?|korrekt|corret[oa]|corrett[oa]|juist"
                             r"|poprawn\w*|doğru|right|accurate|fine|exact[oa]?|bien|richtig|klopt)\b", re.IGNORECASE)
#: OK as a verdict: in a label (after a colon), bracketed ("[OK]", "(OK)") or with a check mark. A bare "OK" or "Okay" opening a
#: sentence is a discourse marker ("OK. Let us look at the poem.", "Okay, so the answer is 5."), never a status label: the rule of the
#: label readers (``markdown._LABEL_MARK_BRACKETED``: only a bracketed "OK" is a check mark written in letters).
_OK_RE = re.compile(r"(?::\s*|^\W*[\[(]\s*)(?:ok|okay)\b|\b(?:ok|okay)\s*[✓✔✅☑]", re.IGNORECASE)
#: Negation, condition, modality or a pending check left after the findings that nothing is wrong are taken out.
_META_NOT_RE = re.compile(
    r"\b(?:not|never|neither|nor|without|unless|if|whether|cannot|should|must|might|may|could|yet|until|pending|unverified|unchecked|untested"
    r"|no|none|nobody|nothing|ningún|ninguna|ninguno|nada|ni|sin|pas|nicht|kein\w*|nie|değil|não|nao|geen|niet|sem)\b|n't\b"
    r"|\bwould\b(?!\s+(?:get|score|earn|receive|achieve))|\bneeds?\b|\bneeded\b|\bto\s+be\b", re.IGNORECASE)
#: A bare result ("x = 4", "y = -2.5"): an answer's value, not content of its own; with an operation it is working (vetoed).
_BARE_RESULT_RE = re.compile(r"(?<![\w.])[A-Za-z]\s*=\s*-?\d+(?:\.\d+)?(?![\w.]*\s*[-+×*/÷^])")
#: A labelled reference ("Source A", "Figure 2", "Statement B"): content of its own, never meta-vocabulary.
_LABELLED_REF_RE = re.compile(r"\b(?:source|document|figure|table|appendix|extract|text|statement|option|part|question|graph|diagram|fig)\.?\s+(?:[A-Z]|\d+)\b",
                              re.IGNORECASE)
#: Prefixes of checking words ("re-", "double-", "cross-", "sanity-"), read as meta-vocabulary inside a hyphenated word.
_META_PREFIXES = frozenset("re double cross triple spot fact self sanity peer stress unit machine hand computer independently".split())
_NUMBER_TOKEN_RE = re.compile(r"\d+(?:[.,/:]\d+)*%?")
_YEAR_TOKEN_RE = re.compile(r"(?:1[0-9]{3}|20[0-9]{2})s?")


#: The hub's own words, also ordinary content (a plantation's overseer, a railway hub): meta-vocabulary only where the sentence names
#: the answer itself or the word leads a label ("Overseer: no objections.", "This answer cleared the overseer's review.").
_HUB_WORDS = frozenset("overseer overseers hub router".split())


def _meta_only(s: str) -> bool:
    """Whether every word of the sentence ``s`` (a reading form) is meta-vocabulary (:data:`_META_WORDS`) or a number that is not a
    year, a bare result ("x = 4") or a check mark: the sentence says nothing about the subject."""
    hub_ok = _SCOPE_ANSWER_RE.search(s) is not None
    lead = re.match(r"^\W{0,8}((?:[\w'-]{1,40}\s){0,2}[\w'-]{1,40})\s{0,4}:\s{0,4}\S", s)  # bounded: linear on a hostile run
    if lead is not None and all(w.rstrip("'s") in _HUB_WORDS or w in _META_WORDS for w in _words(lead.group(1))):
        hub_ok = True  # a label lead ("Overseer:", "Audit trail:") names who or what the label is
    t = _LABELLED_REF_RE.sub(" CONTENTREF ", s)
    t = _BARE_RESULT_RE.sub(" ", t)
    t = re.sub(r"[\"“”«»‘’`]", " ", t)
    words = _WORD_RE.findall(t)
    if not words:
        return True
    for w in words:
        lw = w.lower().strip("'-")
        if lw.endswith(("'s", "s'")) and len(lw) > 3:
            lw = lw[:-2]
        if not lw:
            continue
        if _YEAR_TOKEN_RE.fullmatch(lw):
            return False
        if _NUMBER_TOKEN_RE.fullmatch(lw) or lw in _META_WORDS or re.fullmatch(r"x\d", lw) or (hub_ok and lw in _HUB_WORDS):
            continue
        if "-" in lw and all(p in _META_WORDS or p in _META_PREFIXES for p in lw.split("-") if p):
            continue
        if lw.endswith("ly") and lw[:-2] in ("ful", "complete", "careful", "thorough", "independent", "exact", "perfect", "close", "full", "entire",
                                              "final", "formal", "manual", "automatic", "general", "total"):
            continue
        return False
    return True


def _meta_marked(s: str) -> bool:
    """Whether the sentence ``s`` carries an assurance mark: a checking, verdict, status or foreign checking word, an engine's word,
    a finding that nothing is wrong, grading, an answer key, a consensus, a re-run with the same result, a check mark."""
    if _DEFECT_FREE_RE.search(s) or _META_MARK_RE.search(s) or _CAPS_STATUS_RE.search(s) or _ENGINE_WORD_RE.search(s) or _OK_RE.search(s):
        return True
    if _ASSURE_RE.search(s) or _ALL_CORRECT_RE.search(s):
        return True
    return _SAME_RE.search(s) is not None and _RERUN_RE.search(_SAME_RE.sub(" ", s)) is not None


#: A worked computation with an operator the shared worked-check reading does not list (floor division, a remainder, a power, mod or
#: div: "As a check, 17 // 5 = 3."): working that shows its computation, never a meta-only self-report.
_WORKED_OP_RE = re.compile(r"\d\s*(?://|%(?=\s*\d)|\*\*|\bmod\b|\bdiv\b)\s*\d[^=≈\n]{0,40}?[=≈]\s*-?\d", re.IGNORECASE)
#: A generic thing as the subject of a bare verdict, with nothing checked named ("The engine passed.", "The system works."): content.
_OBJECT_VERDICT_RE = re.compile(r"\W*(?:(?:the|this|our|my|a|an|its|their)\s+)?(?:engines?|systems?|models?|programs?|programmes?|machines?|cars?|motors?"
                                r"|devices?|designs?|plans?|bills?|motions?|candidates?|checks|cheques)\s+(?:(?:has|have|had)\s+)?(?:passed|pass(?:es)?|works?"
                                r"|worked|holds?|held|agrees?|agreed|accepted|cleared)(?:\s+(?:the|a|an)\s+(?!answer|response|working|claims?|steps?)[\w-]+)?\W*",
                                re.IGNORECASE)


def _meta_assurance(s: str) -> bool:
    """The meta-only class (section comment): a sentence of meta-vocabulary only that carries an assurance mark, with no negation,
    condition, modality or pending check (once the findings that nothing is wrong are taken out), no question, no instruction to the
    reader and no worked computation."""
    if not s or s.rstrip().endswith("?") or _ADDRESSED_RE.search(s) or _worked_check(s) or _WORKED_OP_RE.search(s):
        return False
    if _IMPERATIVE_RE.match(s) and not re.match(r"^\W*[\w-]+(?:\s+[\w-]+)?\s*:", s):
        return False  # "Check every value." is an instruction; "Audit: clean." is a label
    if _OBJECT_VERDICT_RE.fullmatch(s) or re.search(r"\bsources?\s+(?:all\s+|both\s+)?(?:agree|agrees|agreed|concur|concurs|differ|disagree)\b", s, re.IGNORECASE):
        return False  # "The engine passed.": a generic thing that passed or works is content (a car's engine, a system of government)
    if not _meta_only(_DEFECT_FREE_RE.sub(" ", s)) or not _meta_marked(s):
        return False
    if _META_NOT_RE.search(_DEFECT_FREE_RE.sub(" ", s)):
        return False
    return not _rubric(s)


# ---- relayed: a quotation or report credited to a reporter
_RELAY_VERBS3 = (r"(?:wrote|writes|write|says|said|say|reported|reports|report|noted|notes|note|stated|states|claims?|claimed|puts?\s+it|put\s+it"
                 r"|records?|recorded|reads|read|shows?|showed|concluded|concludes|declares?|declared|insists?|insisted|added|adds|replied|replies"
                 r"|confirms?|confirmed|agrees?|agreed|dice|dijo|escribe|escribi[oó]|afirma|afirm[oó]|indica|muestra)")
_RELAY_LEAD_RE = re.compile(
    rf"^[\s(\[*>]*(?:according\s+to|per|quoting|citing|seg[uú]n|from|to\s+quote|in\s+the\s+words\s+of)\s+(?P<np2>[^\"“”«»:;,]{{1,70}}?)\s*[,:]\s*(?P<rest2>.+)$"
    rf"|^[\s(\[*>]*as\s+(?:noted|reported|stated|written|said|recorded|put|confirmed|shown)\s+(?:by|in)\s+(?P<np3>[^\"“”«»:;,]{{1,70}}?)\s*,\s*(?P<rest3>.+)$"
    rf"|^[\s(\[*>]*in\s+(?P<np7>[^\"“”«»:;,]{{1,60}}?)['\u2019]s?\s+(?:own\s+)?words\s*[,:]\s*(?P<rest7>.+)$"
    rf"|^[\s(\[*>]*(?:(?:as|per)\s+)?(?P<np>[A-Za-z][^\"“”«»:;,]{{0,70}})\s+(?:\w+ly\s+)?{_RELAY_VERBS3}(?:\s+(?:it\s+)?this\s+way|\s+that)?\s*[,:]?\s+(?P<rest>.+)$"
    rf"|^[\s(\[*>]*(?P<np5>[A-Za-z][^\"“”«»:;,]{{0,50}}?)\s*:\s*(?P<rest5>[\"“«'‘].+)$"
    rf"|^(?P<rest4>.+?)\s*,?\s*as\s+(?P<np4>[^\"“”«»:;,]{{1,70}}?)\s+{_RELAY_VERBS3}\W*$"
    rf"|^(?P<rest6>[\"“«'‘].+?[\"”»'’])\s*,?\s*(?:{_RELAY_VERBS3})\s+(?P<np6>[^\"“”«»:;,]{{1,60}}?)\W*$"
    rf"|^(?P<rest8>[\"“«'‘].+?[\"”»'’])\s*(?:[—–-]+\s*|\(\s*)(?P<np8>[^\"“”«»:;,()]{{1,60}}?)\)?\W*$",
    re.IGNORECASE)
#: Reporters that are the writer's own records or the pipeline's: the writer's log, notes, records or output, unpossessed or the
#: writer's ("the log", "my notes", "the QA log", "the run output").
_OWN_RECORD_RE = re.compile(r"^(?:(?:the|my|our|this)\s+)?(?:own\s+)?(?:[\w-]+\s+){0,2}?(?:log|logs|notes|records?|registro|output|printout|transcript"
                            r"|checklist|worksheet|summary|draft)$", re.IGNORECASE)
#: Words of a relayed sentence that default to this answer whoever is credited with it: its claims, steps, working, calculations or
#: reasoning, the text above, an engine, a QA or a status word, or a label of assurance words only.
_DEFAULT_SCOPE_RE = re.compile(
    r"(?i:\b(?:claims?|steps?|workings?|calculations?|reasoning|answer|response|proofs?|everything|all\s+of\s+(?:it|this|the\s+above)|above|here|so\s+far"
    r"|qa|counterexamples?|unsat\w*|entailed|z3|engine|solver|prover|system|overseer|reviewer|checks?\s+passed|tests?\s+pass\w*|approved|reviewed"
    r"|pasos?|c[aá]lculos?|todo)\b)|\b(?:PROVED|ENTAILED|VERIFIED|PASS(?:ED)?)\b")
#: Item nouns a relayed sentence may name: one that names none ("verified and correct", "Reviewed and approved.") is a bare label,
#: whose scope defaults to the answer.
_NAMES_ITEMS_RE = re.compile(rf"\b{_PART}\b|\b{_SCOPE_PART}\b", re.IGNORECASE)
_FRAME_FINITE_RE = re.compile(r"\b(?:have|has|had|was|were|is|are|and|which|who|that|because|so|but)\b", re.IGNORECASE)


def _light_form(text: str) -> str:
    """``text`` normalised as :func:`reading_form` normalises it, with its quotations neither masked nor unmarked."""
    s = normalise_reading(text or "")
    s = "\n".join(_HEADING_RE.sub("", ln) for ln in s.split("\n")) if ("#" in s or ">" in s or "\n" in s or s[:1] in "-*+•0123456789") else s
    s = _EMPHASIS_CHARS_RE.sub("", s) if any(c in s for c in "*_`~") else s
    return " ".join(s.split())


def _relayed_meta(piece: str, depth: int = 0) -> bool:
    """A quotation or a report credited to a reporter whose words, read as the writer's own, are a self-report: from the writer's
    own records or an internal checker, whatever they say; from anyone else, when they are meta-vocabulary only and default to this
    answer (:data:`_DEFAULT_SCOPE_RE`: 'The ONS reported: "All claims: PROVED."', 'Smith (2019) wrote: "Z3 found no counterexample to
    any of the steps."', 'As Kershaw wrote, all claims: PROVED.'). A source's quotation with content of its own ('The quartermaster's
    log reads: "All receipts checked and signed."', 'The press release claims that "every figure in this report has been
    checked".') is the source's, and one under analysis (a sentence that goes on after it) is read by the rules above. A relay inside a
    relay is unwrapped at most :data:`_RELAY_DEPTH` times (a hostile run of nested frames is read in bounded time)."""
    if depth > _RELAY_DEPTH:
        return False
    s = _light_form(piece)
    m = _RELAY_LEAD_RE.match(s)
    if m is None:
        m2 = _SELF_FRAME_RE.match(s.lstrip(" \"'“”"))
        if m2 is None or m2.start() > 2:
            return False
        rest = s.lstrip(" \"'“”")[m2.end():].lstrip(" ,:")
        np = "I"
    else:
        np = next(m.group(k) for k in ("np", "np2", "np3", "np4", "np5", "np6", "np7", "np8") if m.group(k) is not None)
        rest = next(m.group(k) for k in ("rest", "rest2", "rest3", "rest4", "rest5", "rest6", "rest7", "rest8") if m.group(k) is not None)
    np = np.strip(" ,")
    if len(_words(np)) > 6 or (_FRAME_FINITE_RE.search(np) and not _SELF_FRAME_RE.search(np)):
        return False  # a clause, not a reporter: "Historians such as Kershaw have checked these figures and confirmed them."
    inner = rest.strip().strip("\"'“”«»‘’ ").strip()
    inner = re.sub(r"^[\"'“”«»‘’]|[\"'“”«»‘’](?=\W{0,8}$)", "", inner).strip(" \"'“”«»‘’")
    if not inner or len(inner) < 3:
        return False
    r = reading_form(inner)
    if not r.strip() or r.rstrip().endswith("?"):
        return False
    own = _OWN_RECORD_RE.match(np.strip()) is not None and not re.search(r"[A-Za-z]['’]s\b", np)
    internal = own or np == "I" or _internal_reporter(np) or _HUB_REPORTER_RE.search(np) is not None or _SELF_FRAME_RE.search(np) is not None
    if not internal and not (_meta_only(r) and (_DEFAULT_SCOPE_RE.search(r) or not _NAMES_ITEMS_RE.search(r))):
        return False
    return _meta_assurance(r) or (_meta_only(r) or internal) and _read_sentence(inner, depth + 1)


#: How many relays inside a relay are unwrapped.
_RELAY_DEPTH = 2


#: A party that endorses the whole answer ("Another model agreed with all of this.", "The reviewer approved this answer."): whoever it is, the
#: endorsement of this answer is a relayed verdict no check established.
_ENDORSES_WHOLE_RE = re.compile(
    r"^\W*(?P<np>[^,;:]{1,40}?)\s+(?:has\s+|had\s+|have\s+)?(?:fully\s+|also\s+)?(?:agreed|agrees|concurred|concurs|approved|approves|endorsed|endorses"
    r"|signed\s+off\s+on|vouched\s+for|vouches\s+for)\s+(?:with\s+)?(?:all\s+of\s+(?:this|it|the\s+above)|everything\s+(?:above|here|in\s+(?:this|my)\s+\w+)"
    r"|the\s+above|this\s+(?:answer|response|working|synthesis|solution)|my\s+(?:answer|response|working|solution)|it\s+all)\W*$", re.IGNORECASE)


def _endorses_whole(s: str) -> bool:
    m = _ENDORSES_WHOLE_RE.match(s)
    return m is not None and not _META_NOT_RE.search(m.group("np"))


# ---- a script the reader does not read: fail closed
def _unread_script(s: str) -> bool:
    """Whether most letters of ``s`` (a reading form; at least two) are in a script this reader has no vocabulary for (Cyrillic,
    Arabic, Hebrew, Devanagari, Han, kana, Hangul, Thai, ...: anything but Latin, and Greek, whose letters are mathematics): the
    sentence cannot be read, so it fails closed (named) rather than pass ("Все вычисления проверены и верны.", "すべて確認済み。")."""
    latin = other = 0
    for ch in s:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if name.startswith(("LATIN", "GREEK")) or ch.isascii():
            latin += 1
        else:
            other += 1
    return other >= 2 and other >= latin


# ---- vetoes: content of the subject that uses the words of checking
#: A rubric or mark scheme: what earns a mark, what to accept, what examiners do ("Award [1] for verifying the answer by
#: substitution.", "Mark scheme: accept any answer that is verified by substitution.", "Examiners check that each date is correct.").
_RUBRIC_RE = re.compile(
    r"^\W*(?:(?:mark\s*-?\s*scheme|markscheme|rubric|marking\s+(?:criteria|guidance|notes?)|assessment\s+criteri(?:on|a)|criteri(?:on|a)|examiner(?:'s|s')?\s+"
    r"(?:notes?|guidance|report))\s*[:—–-]\s*)?(?:(?:do\s+not|don't|never|only)\s+)?(?:award|accept|credit|allow|deduct|penali[sz]e|reward|give\s+(?:\[?\d|one|two|full|no)"
    r"|withhold)\b"
    r"|^\W*(?:the\s+)?(?:examiners?|markers?|moderators?|assessors?|graders?)\s+(?:will\s+|should\s+|must\s+|usually\s+|always\s+|also\s+|then\s+|may\s+)?"
    r"(?:check|look\s+for|verify|expect|award|accept|reward|credit|want|confirm|ensure)\b", re.IGNORECASE)


def _rubric(s: str) -> bool:
    if _RUBRIC_RE.match(s) is None:
        return False
    if re.match(r"^\W*(?:the\s+)?(?:examiner|marker|moderator|assessor|grader)\b", s, re.IGNORECASE):
        return False  # one examiner's check is a relayed check; a rubric speaks of examiners in general
    return not (_ANSWER_REF_RE.search(s) or re.search(r"\b(?:above|here|so\s+far)\b", s, re.IGNORECASE) or _FIRST_PERSON_SUBJECT_RE.search(s))


#: A step proved earlier in the same answer, cited ("As proved above, f is increasing on [0, 2].", "As shown in part (a), ...").
_PROOF_BACK_REF_RE = re.compile(
    r"^\W*(?:as|since|because|by\s+what\s+was)\s+(?:(?:we|I)\s+(?:have\s+)?)?(?:proved|proven|shown|established|derived|demonstrated|found)\s+"
    r"(?:above|earlier|before|previously|in\s+(?:the\s+)?(?:previous\s+)?(?:part|step|section|question|lemma|theorem|example|exercise|case|line)\b[^,]{0,12})\s*,\s*(?P<rest>.+)$",
    re.IGNORECASE)
#: A check by the writer that a statement of the subject holds ("We have verified that the conditions of the theorem hold, so ...").
_CHECKED_THAT_RE = re.compile(r"^\W*(?:(?:I|we)\s+(?:have\s+|had\s+)?(?:now\s+|also\s+|first\s+)?|it\s+(?:has\s+been|was|is)\s+)(?:verified|checked|confirmed"
                              r"|shown|established)\s+that\s+(?P<rest>.+)$", re.IGNORECASE)
#: Discussion verbs whose object is the subject matter ("I have gone through the main arguments for and against free will.").
_DISCOURSE_RE = re.compile(r"\b(?:have\s+|has\s+|had\s+)?(?:gone|went|go|going|looked|look|looking)\s+(?:back\s+)?(?:through|over)\s+(?P<obj>[^.;:!?]+)",
                           re.IGNORECASE)
#: A research construct as what was checked ("Inter-rater reliability was checked by having two observers ...").
_CONSTRUCT_RE = re.compile(
    r"^\W*(?:the\s+)?(?:(?:inter-?rater|inter-?observer|inter-?coder|test-?retest|internal|external|ecological|construct|content|face|concurrent|predictive"
    r"|criterion|population|split-?half|temporal|statistical)\s+)?(?:reliability|validity|normality|homogeneity|significance|consistency)\b(?:\s+of\s+the\s+"
    r"(?!answer|response|working|figures|values|calculations)[\w\s-]{1,40}?)?\s+(?:was|were|is|are|has\s+been|had\s+been|have\s+been)\s+(?:\w+ly\s+)?"
    r"(?:checked|assessed|tested|established|measured|confirmed|verified|examined|evaluated|estimated|ensured|maximi[sz]ed|improved)\b", re.IGNORECASE)


def _content_rest(rest: str) -> bool:
    """Whether ``rest`` states content of the subject: not meta-vocabulary only, and naming neither the answer, an anchor in it nor
    the answer's own items."""
    return not _meta_only(rest) and not (_ANSWER_REF_RE.search(rest) or _SCOPE_ANSWER_RE.search(rest) or _SELF_THEME_RE.search(rest)
                                         or re.search(r"\b(?:above|here|so\s+far)\b", rest, re.IGNORECASE))


def _round3_subject_matter(s: str) -> bool:
    """The vetoes of this round (section comment), on a reading form ``s``: a rubric, a step proved earlier in the same answer cited
    before content, the writer's check that a statement of the subject holds, discussion of the subject matter ("gone through the
    main arguments"), a research construct checked, and a named outside body as the agent of a Spanish passive ("por el INE")."""
    if _RECEIPT_TOKEN_RE.search(s) or _meta_assurance(s):
        return False
    if _rubric(s):
        return True
    m = _PROOF_BACK_REF_RE.match(s)
    if m is not None and _content_rest(m.group("rest")) and not _ASSURE_RE.search(m.group("rest")):
        return True
    m = _CHECKED_THAT_RE.match(s)
    if m is not None and _content_rest(m.group("rest")) and not _CORRECT_RE.search(m.group("rest")):
        return True
    if _CONSTRUCT_RE.match(s) and not (_FIRST_PERSON_ANY_RE.search(s) or _ANSWER_REF_RE.search(s) or re.search(r"\b(?:above|here)\b", s, re.IGNORECASE)
                                       or _internal_somewhere(s)):
        return True
    d = _DISCOURSE_RE.search(s)
    if d is not None and re.search(r"(?:^|\s)(?:I|we|I've|we've)\b|\b(?:this|the|my|our)\s+essay\b", s[:d.start()], re.IGNORECASE) and _discourse_of_subject(s, d):
        return True
    return _por_outside(s)


def _discourse_of_subject(s: str, d: "re.Match") -> bool:
    """"Gone through" or "looked over" with the subject matter as its object (arguments, causes, criticisms, interpretations), and
    no other assurance word in the sentence."""
    obj = d.group("obj")
    head = re.split(r"\s+(?:of|for|in|on|about|from|against|with|above|and|that|which|to|before|after|between|behind|,)\b|,", obj, maxsplit=1, flags=re.IGNORECASE)[0]
    hw = _words(head)
    if not hw:
        return False
    last = hw[-1]
    if re.fullmatch(_ITEM_STRICT, last, re.IGNORECASE) or last in ("it", "them", "everything", "lot", "all", "each", "this", "these", "those", "answer",
                                                                     "working", "workings", "work", "essay", "response", "solution", "draft", "text"):
        return False
    rest = s[:d.start()] + " " + s[d.end():]
    return not (_ASSURE_RE.search(rest) or _CORRECT_RE.search(rest) or _DEFECT_FREE_RE.search(rest) or _internal_somewhere(d.group(0)))


#: People and bodies in Spanish that name a party ("los inspectores de la UE", "los historiadores").
_ES_PEOPLE = frozenset("inspectores historiadores expertos científicos cientificos auditores investigadores autoridades funcionarios economistas "
                       "estadísticos estadisticos analistas periodistas jueces tribunales organismos".split())


def _por_outside(s: str) -> bool:
    """A Spanish past passive whose agent after "por" is a named outside party ("Todo fue comprobado por el INE en 2021.", "Todo fue
    revisado por la Comisión Europea en 2019."): evidence cited, as "Everything was checked by EU inspectors." is in English; never
    with the writer's own answer named. The perfect passive ("Todas las cifras han sido comprobadas por el Instituto ...") states the
    items' status now, the answer's claim about itself, as "All figures have been checked by ..." does."""
    m = re.search(r"\b(?:fue|fueron|había\s+sido|habían\s+sido)\s+(?:\w+mente\s+)?(?:comprobad|verificad|revisad|validad"
                  r"|confirmad|auditad|chequead|cotejad|corroborad|aprobad|controlad|certificad)[oa]s?\s+por\s+(?P<np>[^,;.:()]{1,60})", s, re.IGNORECASE)
    if m is None or _ANSWER_REF_RE.search(s) or re.search(r"\b(?:esta|mi|nuestra)\s+respuesta\b", s, re.IGNORECASE) or _FIRST_PERSON_ANY_RE.search(s):
        return False
    raw = _WORD_RE.findall(m.group("np"))
    raw = [w for w in raw if w.lower() not in ("el", "la", "los", "las", "un", "una", "unos", "unas")]
    if not raw or _agent_kind(m.group("np")) == "internal" or re.search(rf"\b{_PERSONAL_TOOL_HEAD}\b", m.group("np"), re.IGNORECASE):
        return False
    w = raw[0]
    return w.lower() in _ES_PEOPLE or w[:1].isupper() or (len(w) > 1 and w.isupper())


def _round3_self_report(s: str, piece: str) -> bool:
    """The positive readings of this round (section comment): the meta-only class, a whole-answer endorsement and an unread script."""
    return _meta_assurance(s) or _endorses_whole(s) or _unread_script(s)


# ============================================================================================ the one reader
def _template(s: str) -> bool:
    from .markdown import _template_self_certification
    return _template_self_certification(s)


@functools.lru_cache(maxsize=16384)
def _read_piece(piece: str) -> bool:
    """One piece, sentence by sentence: a sentence is read on its own, so a neighbouring sentence's "we" or computation never
    decides another's reading (hold-fix round 3: a maths step's "we" was taken as the checker of a source author's check in the next
    sentence)."""
    sentences = _raw_sentences(piece)
    if len(sentences) > 1:
        return any(_read_sentence(x) for x in sentences) or _answered_check_question(sentences)
    return _read_sentence(piece)


def _raw_sentences(piece: str) -> list[str]:
    """``piece`` split at sentence marks outside its quotations (a quotation of several sentences stays with its attribution)."""
    from .markdown import find_quotation_spans
    spans = find_quotation_spans(piece) if any(q in piece for q in "\"“”«»'‘’") else []
    out: list[str] = []
    cursor = 0
    for m in _SENTENCE_END_RE.finditer(piece):
        if any(a < m.start() < b for a, b, _i in spans):
            continue
        out.append(piece[cursor:m.start()])
        cursor = m.end()
    out.append(piece[cursor:])
    return [x for x in out if x.strip()]


def _read_sentence(piece: str, depth: int = 0) -> bool:
    s = reading_form(piece)
    if not s:
        return False
    if _relayed_meta(piece, depth) or _meta_assurance(s):
        return True  # a relayed self-report, read before the quotation masking decides, and a sentence with no content of its own
        # (second remedy, round 3): no veto for content applies to a sentence that has none
    if _subject_matter(s):
        return False
    if _round2_self_report(s) or _round3_self_report(s, piece):
        return True
    if class_self_report(s):
        return True
    if any(_assurance_sentence(x) for x in reading_sentences(s)):
        return True
    for inner in _unmarked_quotations(piece, s):
        r = reading_form(inner)
        if r and (class_self_report(r) or any(_assurance_sentence(x) for x in reading_sentences(r))):
            return True
    t = template_form(piece)
    if t.strip() and _template(t):
        return not not_a_self_report(s)
    return False


def _unmarked_quotations(piece: str, reading: str) -> list[str]:
    """The quotations of ``piece`` its reading form left unmasked (the writer's own words, or words in the answer's scope), each
    read on its own as well: a label quoted after a frame ('In other words, "Reviewed and approved."') is a label."""
    if not any(q in piece for q in "\"“”«»'‘’"):
        return []
    from .markdown import find_quotation_spans
    flat = " ".join(reading.split())
    out = []
    for _a, _b, inner in find_quotation_spans(" ".join(normalise_reading(piece).split())):
        words = " ".join(inner.split()).strip(" \"'“”‘’«»")
        if len(words) >= 3 and words[:40] in flat:
            out.append(words)
    return out


def self_report_pieces(text: str) -> list[str]:
    """The pieces of ``text`` read on their own as well as together: the text, each of its lines, each cell of a table row, and
    each parenthesis, so a self-report after a line break, in a table cell or in brackets is read by itself."""
    if not text:
        return []
    out = [text]
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) > 1:
        out += lines
    for ln in lines:
        if "|" in ln:
            out += [c for c in ln.split("|") if c.strip() and c.strip("-: ")]
    seen: set[str] = set()
    uniq: list[str] = []
    for p in out:
        k = " ".join(p.split())
        if k and k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def _window_starts(piece: str) -> list[int]:
    """Starts of the overlapping windows a long piece is read in, each moved to the next word boundary (a window that opened
    inside "unchecked" read "checked ..."; round 2 of the second remedy)."""
    out = []
    for i in range(0, len(piece), _PIECE_MAX // 2):
        if i and piece[i - 1].isalnum() and piece[i].isalnum():
            m = re.compile(r"\W").search(piece, i, min(len(piece), i + 64))
            i = m.end() if m else i
        out.append(i)
    return out


def is_self_report(sentence: str) -> bool:
    """The one self-report reader (module docstring): True when ``sentence`` (a sentence, a line, a heading, a table row, a claim)
    or one of its pieces (:func:`self_report_pieces`) claims that this answer, its parts or the writer's own work in it were checked
    or are correct, or that an internal checker checked them. Normalised first (:func:`reading_form`); quotations masked only where
    attributed or analysed. Never raises on a string; anything else is no sentence."""
    if not isinstance(sentence, str) or not sentence.strip():
        return False
    for piece in self_report_pieces(sentence):
        if len(piece) > _PIECE_MAX:
            if any(_read_piece(piece[i:i + _PIECE_MAX]) for i in _window_starts(piece)):
                return True
            continue
        if _read_piece(piece):
            return True
    return False


def quotation_only(text: str) -> bool:
    """Whether ``text`` (a claim) is nothing but one quotation, its marks included ("\"I checked every lock twice.\""): a quotation
    a parser drew out of a sentence as evidence. Its words are read in that sentence, where its attribution stands (the narrator,
    the minister), never alone: alone it would read as the writer's."""
    from .markdown import find_quotation_spans
    t = (text or "").strip()
    if len(t) < 3:
        return False
    spans = find_quotation_spans(t)
    return len(spans) == 1 and spans[0][0] == 0 and t[spans[0][1]:].strip(" .,;:!?") == ""


def claim_is_self_report(text: str, split: Optional[Callable[[str], list[str]]] = None) -> bool:
    """Whether the claim ``text`` holds a self-report: :func:`is_self_report` names it or one of its sentences; a claim that is
    nothing but a quotation drawn from a sentence (:func:`quotation_only`) is read in that sentence, not here."""
    if not isinstance(text, str) or not text.strip() or quotation_only(text):
        return False
    if split is None:
        from .english_specialist.parser import split_sentences as split
    return names_self_report_in(text, split)


def names_self_report_in(text: str, split: Callable[[str], list[str]]) -> bool:
    """Whether :func:`is_self_report` names ``text`` or any sentence of it as ``split`` splits it."""
    if is_self_report(text):
        return True
    return any(is_self_report(s) for s in split(text))


_PARAGRAPH_RE = re.compile(r"\n[ \t]*\n")


def self_report_spots(text: str, split: Optional[Callable[[str], list[str]]] = None) -> list[tuple[int, str]]:
    """The self-reports of the answer ``text`` as written, independently of every parser and role: ``(paragraph, piece)`` for each
    sentence, line or table cell (:func:`self_report_pieces`) of each blank-line paragraph (1-based) that :func:`is_self_report`
    names, the smallest piece first. ``split`` splits a paragraph into sentences (default: the English parser's splitter). Bounded:
    each piece is read once (cached)."""
    if not isinstance(text, str) or not text.strip():
        return []
    if split is None:
        from .english_specialist.parser import split_sentences as split
    out: list[tuple[int, str]] = []
    for i, para in enumerate([p for p in _PARAGRAPH_RE.split(text) if p.strip()], start=1):
        pieces: list[str] = []
        for line in [ln for ln in para.split("\n") if ln.strip()]:
            pieces += [c for c in line.split("|") if c.strip() and c.strip("-: ")] if "|" in line else [line]
        pieces += list(split(para))
        found = [p for p in dict.fromkeys(" ".join(x.split()) for x in pieces) if p and is_self_report(p)]
        if not found and is_self_report(para):
            found = [" ".join(para.split())]
        for p in sorted(found, key=len)[:1] + [q for q in sorted(found, key=len)[1:] if not any(r in q for r in found if r != q)]:
            out.append((i, p))
    return out


def self_report_places(text: str, split: Optional[Callable[[str], list[str]]] = None) -> list[int]:
    """The 1-based numbers of the paragraphs of ``text`` that hold a self-report (:func:`self_report_spots`)."""
    return sorted({i for i, _p in self_report_spots(text, split)})


# ============================================================================================ the report's own fields
#: Notes the platform's own parsers and adapters write into a report's ``unresolved_issues`` (never the specialist's words): read
#: apart, so a note that names a self-report the parser found is not read as one more.
_PLATFORM_NOTE_RE = re.compile(
    r"^(?:\d+ (?:claims|sentences) beyond the report's claim limit \(\d+\) were merged into claim \S+ and were not individually roled or checked"
    r"|no supplied text was given: quotations could not be attributed to a document$"
    r"|the answer contains meta-text \(a check label, a narrated step or a pasted receipt\); it was excluded from the argument$"
    r"|the answer contains note paragraphs \(a from-memory label, a task note or self-certification\); their sentences are roled 'other' and are not material$"
    r"|paragraph \d+: the sentence '.{0,120}' certifies the answer's own verification or imitates a receipt; it was roled 'other'"
    r"|paragraph \d+: \d+ sentence\(s\) carrying verification-status language were roled other and count as no material claim; "
    r"|paragraph\(s\) [\d, ]+ carry an unbalanced quotation mark; "
    r"|the answer holds no prose sentence \(only a pasted JSON fragment or markup\); "
    r"|the STEM front end produced no statements \("
    r"|supplied_texts were provided by the agent, not by the platform; quotations were checked against the agent's own texts$"
    r"|quotation with no supplied text to check it against: "
    r"|inline label recorded, not part of the claim: "
    r"|\d+ statement\(s\) carrying verification-status language were roled other and count as no material claim: "
    r"|the sentence attributes this view to a peer specialist; "
    r"|the statement has an unbalanced quotation mark; "
    r"|a quotation mark in this sentence cannot be paired; "
    r"|the sentence carries a verification-status label or self-certification inline \("
    r"|the sentence carries the method's own label inline \("
    r"|\d+ quotation\(s\) of the merged claims are carried as this claim's source references"
    r"|\d+ further quotation\(s\) of the merged claims could not be carried"
    r"|numeric relations of this statement are decided by the STEM pack checks "
    r"|the answer's list of sources: provenance meta-text, not a claim of the answer"
    r"|the quotation is a label relayed in a note, not evidence for the argument)", re.DOTALL)


def _field(obj, name: str):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def report_field_texts(report) -> list[tuple[str, Optional[str], str]]:
    """``(where, claim id or None, text)`` for each text of a specialist report, other than its response and its claims' texts, that
    is the specialist's own (the channel's ``_report_texts`` reads the same fields for its text rules): the report's assumptions and
    unresolved issues, and each claim's assumptions and assessment criteria. Notes the platform's own parsers wrote
    (:data:`_PLATFORM_NOTE_RE`) are not the specialist's. Works on a report object or its mapping (a payload); anything unreadable
    yields nothing here (the callers fail closed on what they cannot read)."""
    out: list[tuple[str, Optional[str], str]] = []
    if report is None:
        return out
    response = _field(report, "original_response")
    written = " ".join(response.split()) if isinstance(response, str) else ""

    # the response as every gate reads it: an outside party's quotation masked (round 2 of the second remedy: a field whose words
    # were the response's MASKED quotation was dropped as a copy, so a self-certification beside the response was never read)
    read_response = " ".join(mask_outside_quotations(response).split()) if isinstance(response, str) else ""

    def own(t) -> bool:
        # the specialist's own words beside the response: not a note the platform's parsers wrote, and not words copied from the
        # part of the response every gate reads as written already
        if not isinstance(t, str) or not t.strip() or _PLATFORM_NOTE_RE.match(t.strip()):
            return False
        flat = " ".join(t.split())
        if written and flat in written and flat in read_response:
            return False
        # a note whose words after its lead are the response's own ("<lead>: <words of the response>") is a record only when the
        # lead itself claims nothing ("All checked and confirmed correct: <sentence>" and "QA passed: <sentence>" are self-reports)
        lead, sep, rest = flat.partition(": ")
        rest = rest.strip(" \"'“”‘’")
        if sep and written and len(lead) <= 80 and len(rest) >= 12 and rest in read_response:
            return bool(_ASSURE_RE.search(lead) or _CAPS_STATUS_RE.search(lead) or _ENGINE_WORD_RE.search(lead) or _CORRECT_RE.search(lead)
                        or is_self_report(lead))
        return True
    for name, where in (("assumptions", "an assumption of the report"), ("unresolved_issues", "an unresolved issue of the report")):
        for t in list(_field(report, name) or [])[:128]:
            if own(t):
                out.append((where, None, t))
    for c in list(_field(report, "claims") or [])[:512]:
        cid = _field(c, "claim_id")
        for name, where in (("assumptions", "an assumption of claim"), ("assessment_criteria", "an assessment criterion of claim")):
            for t in list(_field(c, name) or [])[:64]:
                if own(t):
                    out.append((where, str(cid) if cid is not None else None, t))
    return out


def report_field_self_reports(report) -> list[tuple[str, Optional[str]]]:
    """Second remedy of the round-9 push-check hold: ``(where, claim id or None)`` for each of the specialist's own fields
    (:func:`report_field_texts`) that :func:`claim_is_self_report` names. The gate read only the response, the claims' texts and
    their advisory status, so "All values were verified on a GDC and are confirmed correct." written only in a report's or a claim's
    assumptions, unresolved issues or assessment criteria was delivered NOT CHECKED and OVERSEER-SELECTED. Never raises on a
    readable report; a field that cannot be read is named (fail closed)."""
    out: list[tuple[str, Optional[str]]] = []
    for where, cid, text in report_field_texts(report):
        try:
            if _field_self_report(text):
                out.append((where, cid))
        except Exception:  # noqa: BLE001 - fail closed
            out.append((where, cid))
    return out


#: The longest field read whole; a longer one is read in overlapping windows of this size, and one longer than
#: :data:`_FIELD_READ_MAX` is named as a whole (fail closed), never cut short.
_FIELD_WINDOW = _PIECE_MAX * 4
_FIELD_READ_MAX = _PIECE_MAX * 64


def _field_self_report(text: str) -> bool:
    """Whether a field beside the response holds a self-report: the one reader on the field (an outside party's quotation masked)
    or a verification label on it (:func:`label_self_report`). A field longer than one window is read in overlapping windows (round 2
    of the second remedy: the reader read only its first 16000 characters, so a self-certification after filler was delivered); one
    too long to read is named (fail closed)."""
    if len(text) > _FIELD_READ_MAX:
        return True
    if len(text) <= _FIELD_WINDOW:
        return _text_self_report(text)
    step = _FIELD_WINDOW // 2
    return any(_text_self_report(text[i:i + _FIELD_WINDOW]) for i in range(0, len(text) - step, step))


def _text_self_report(text: str) -> bool:
    masked = mask_outside_quotations(text)
    if claim_is_self_report(masked) or label_self_report(masked):
        return True
    # a field's lead before content ("All checked and confirmed correct: <sentence>", "QA passed: <sentence>") is the specialist's
    # own note on that content: a certifying lead is a self-report beside the response
    lead, sep, _rest = " ".join(masked.split()).partition(": ")
    return bool(sep) and len(lead) <= 80 and (is_self_report(lead) or is_self_report(lead + "."))


def label_self_report(text: str) -> bool:
    """Whether a sentence of ``text`` carries a verification label or the receipt vocabulary as the core pack's CORE-SELF-001 reads
    them (``markdown.verification_label``, ``markdown.self_cert_vocabulary``), held to the vetoes (:func:`not_a_self_report`): "Answer
    (verified): 15 km/h.", "Signed receipt attached: VERIFIED.". The outcome, the eligibility rule and the report's own fields read
    this with the one reader, so every path names what the packs name (round 2 of the second remedy: the outcome showed ENTAILED for
    a claim the hub refused)."""
    if not isinstance(text, str) or not text.strip():
        return False
    from .markdown import self_cert_vocabulary, verification_label
    from .english_specialist.parser import split_sentences
    for sent in [text] + list(split_sentences(text)):
        r = reading_form(sent)
        if not r.strip() or not_a_self_report(r):
            continue
        if self_cert_vocabulary(r) is not None or verification_label(r) is not None:
            return True
    return False


# ============================================================================================ a claim of a check, for the outcome
def claims_a_check(text: str) -> bool:
    """Whether the claim ``text`` is a self-report (:func:`claim_is_self_report`) that claims a check, a verification, a review, a
    QA or engine result, a proof or the answer's correctness (an assurance or correctness word is in it): the claims whose outcome
    must never show a success status. A structural note the template rules read as meta-text ("The paragraph has 320 words.") makes
    no such claim."""
    if not isinstance(text, str) or not text.strip():
        return False
    if not claim_is_self_report(text):
        return label_self_report(text)  # a verification label or the receipt vocabulary, as the core pack names it
    r = reading_form(text)
    return bool(_ASSURE_RE.search(r) or _CAPS_STATUS_RE.search(text) or _CORRECT_RE.search(r) or _CHECK_RE.search(r) or _ENGINE_WORD_RE.search(r)
                or _verdict_of_tool(r) or _relayed_check(r) or (_CHECKER_LEAD_RE.search(r) is not None and _EVALUATION_RE.search(r) is not None)
                or _meta_marked(r) or _unread_script(r) or _relayed_meta(text))


_CLAIM_PIECE_RE = re.compile(r"(?<=[.!?;])\s+")


def wholly_self_report(text: str) -> bool:
    """Whether every sentence and every ';'-clause of the claim ``text`` is a self-report and the claim claims a check
    (:func:`claims_a_check`): a claim with nothing else to check ("All values were verified on a GDC and are confirmed correct."),
    never a solver question. A claim that also states content ("Given x = 5, x < y for any integer y; I checked 3 values.") keeps
    its content's check, and its outcome never shows a success status (:func:`claims_a_check`)."""
    if not claims_a_check(text) or re.search(r"[=<>≤≥≠≈]", text):
        return False  # a relation is content to check ("Given x = 5, x < y, as I checked for 12 values of y.")
    pieces = [p for p in _CLAIM_PIECE_RE.split(text.strip()) if p.strip(" .;!?")]
    # a verification label set on content ("Verified: The constitution was adopted in 1919.") leaves the content a claim to check:
    # only a claim that is nothing but self-reports is kept from the solver; its outcome never shows a success (:func:`claims_a_check`)
    return all(claim_is_self_report(p) or (label_self_report(p) and not _label_on_content(p)) for p in pieces)


def _label_on_content(text: str) -> bool:
    from .markdown import verification_label
    lab = verification_label(reading_form(text))
    return lab is not None and lab.position != "whole" and bool(_words(reading_form(text).replace(lab.label.rstrip(". "), " ", 1)))
