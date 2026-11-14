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

__all__ = ["reading_form", "template_form", "normalise_reading", "is_self_report", "class_self_report", "not_a_self_report", "self_report_pieces",
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
    """``text`` with each quotation masked when the sentence attributes or analyses it (a reporting frame or an analysing noun or
    verb outside it, :data:`_ATTRIBUTION_RE`, whose reporter is no internal checker), and otherwise with only its marks removed: an
    unattributed quoted sentence and a scare quote in the writer's own sentence are the writer's words."""
    from .markdown import find_quotation_spans
    spans = find_quotation_spans(text)
    if not spans:
        return text
    outside = []
    cursor = 0
    for a, b, _inner in spans:
        outside.append(text[cursor:a])
        outside.append(" ")
        cursor = b
    outside.append(text[cursor:])
    frame = "".join(outside)
    attributed = _ATTRIBUTION_RE.search(frame) is not None and _INTERNAL_REPORTER_RE.search(frame) is None
    return _masked(text, spans) if attributed else _unmarked(text, spans)


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
    if _agent_kind(reporter) != "outside" or _ANSWER_REF_RE.search(reporter):
        return text
    end = len(text)
    tail = _WRITER_RESUMES_RE.search(text, m.end())
    if tail is not None:
        end = tail.start()
    return text[:m.end()] + " " + "x" * max(0, end - m.end() - 1) + text[end:]


#: Where the writer's own words resume after a reported complement ("..., but I have rechecked all of them").
_WRITER_RESUMES_RE = re.compile(r"[;]\s|,\s+(?:but|and|yet|so)\s+(?:I|we|my|our|there|this|that|it|everything|nothing|all|every|each)\b|\.\s"
                                r"|\s[—–]\s?|\s-{1,2}\s|\s?\((?=\s*(?:all\s+|fully\s+)?(?:note|nb|n\.b\.|ps|p\.s\.|verified|checked|confirmed|validated|double-checked|cross-checked|correct|accurate|100)\b)|[,:]\s*(?=(?:note|nb|n\.b\.|ps|p\.s\.)\b)", re.IGNORECASE)
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
         r"|c[aá]lculos?|pasos?|valores?|cifras?|datos?|resultados?|respuestas?|operaciones?|n[uú]meros?|fechas?|textos?)")
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
    r"\b(?:correct(?:ly)?|right|accurate|exact|error[- ]free|flawless|faultless|impeccable|without\s+(?:any\s+|a\s+single\s+)?(?:errors?|mistakes?|slips?)"
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
                r"|statistics?|conversions?|substitutions?|claims?|points?|dates?|c[aá]lculos?|valores?|cifras?|n[uú]meros?|pasos?|respuestas?"
                r"|datos?|resultados?|operaciones?)")
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
    rf"(?:^|[,;:(]\s*|\band\s+)(?P<np>(?:(?:the|my|our|a|an|el|la|mi)\s+)?(?:[\w-]+\s+){{0,2}}?{_VERDICT_TOOL})\s+(?:\w+ly\s+)?(?:says?|said|shows?"
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
_PERSONAL_TOOL_HEAD = (r"(?:calculators?|gdcs?|cas|wolfram(?:\s*alpha)?|desmos|geogebra|excel|spreadsheets?|z3|smt|solvers?|provers?|symbolab"
                       r"|photomath|matlab|calculadoras?|hojas?\s+de\s+c[aá]lculo|casio|numworks|(?<![\w-])ti-[\w-]+|nspire|(?<![\w-])fx-[\w-]+"
                       r"|hp[\s-]?prime|python|(?<![\w-])(?:ti|fx|hp|cfx|cg|el)-?\d{2,4}[a-z+]{0,4})")  # a calculator's make or model code ("a TI-Nspire", "a Casio", "an fx-991")
#: Unnamed people who check a student's work: internal unless they are another party's ("his tutor", "Darwin's tutor").
_PERSON_HEAD = (r"(?:teachers?|tutors?|instructors?|examiners?|markers?|moderators?|colleagues?|classmates?|peers?|friends?|parents?|proofreaders?"
                r"|supervisors?|profesor(?:a|es|as)?|maestr[oa]s?|compañer[oa]s?|tutor[ae]s?)")
#: Generic tools: internal only with modifiers of a checking tool, or (an engine, a checker) a product name; otherwise qualified by
#: their subject matter ("the Hollerith tabulating system", "data-logging software", "a static type checker"): content.
_GENERIC_TOOL_HEAD = (r"(?:systems?|engines?|software|computers?|ai|models?|checkers?|verifiers?|programs?|programmes?|apps?|assistants?|chatbots?"
                      r"|sistemas?|motor|ordenador|computadora|verificador|herramienta)")
#: Generic heads that take a product name as an internal checker ("the Epinoic engine").
_NAMED_TOOL_HEAD_RE = re.compile(r"^(?:engines?|checkers?|verifiers?|assistants?|chatbots?|ai|apps?|motor|verificador)$", re.IGNORECASE)
#: A check as the agent ("validated by an independent check", "confirmed by a second verification"): the writer's own check unless
#: another party's ("the ONS's check").
_CHECK_NOUN_HEAD = (r"(?:checks?|cross-?checks?|double-?checks?|re-?checks?|recalculations?|recomputations?|verifications?|re-?checking"
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
                    if _YEAR_RE.search(np) or (kind == "outside" and not _ANCHOR_RE.match(prep + " " + np) and not _ANSWER_REF_RE.search(np)):
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
                    elif first in ("it", "them", "this", "these", "everything", "todo") and len(o.split()) <= 2:
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
_RECEIPT_TOKEN_RE = re.compile(r"\b(?:ACCEPTED_WITH_FINDINGS|INCONSISTENT_PREMISES|UNSAT|SAT|ENTAILED|receipt_id|transmission_id|formal_checks"
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
        return any(_read_sentence(x) for x in sentences)
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


def _read_sentence(piece: str) -> bool:
    s = reading_form(piece)
    if not s:
        return False
    if class_self_report(s):
        return True
    t = template_form(piece)
    if t.strip() and _template(t):
        return not not_a_self_report(s)
    return False


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


def is_self_report(sentence: str) -> bool:
    """The one self-report reader (module docstring): True when ``sentence`` (a sentence, a line, a heading, a table row, a claim)
    or one of its pieces (:func:`self_report_pieces`) claims that this answer, its parts or the writer's own work in it were checked
    or are correct, or that an internal checker checked them. Normalised first (:func:`reading_form`); quotations masked only where
    attributed or analysed. Never raises on a string; anything else is no sentence."""
    if not isinstance(sentence, str) or not sentence.strip():
        return False
    for piece in self_report_pieces(sentence):
        if len(piece) > _PIECE_MAX:
            if any(_read_piece(piece[i:i + _PIECE_MAX]) for i in range(0, len(piece), _PIECE_MAX // 2)):
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
